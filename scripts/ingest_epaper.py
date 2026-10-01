import os
import sys
import hashlib
import time
import math
import re
import uuid
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Add workspace to path
WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(WORKSPACE)

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance

# Safe fitz import
try:
    import fitz
except ImportError:
    import pymupdf as fitz

# Configure basic logging
os.makedirs(os.path.join(WORKSPACE, "logs"), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(WORKSPACE, "logs", "ingest_epaper.log")),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ingest")

load_dotenv(os.path.join(WORKSPACE, ".env"))
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_ENV = os.getenv("QDRANT_ENV", "dev")
EPAPER_COLLECTION_BASE = os.getenv("EPAPER_COLLECTION_BASE", "epaper_items")
TARGET_COLLECTION = f"{QDRANT_ENV}_{EPAPER_COLLECTION_BASE}"

EPAPER_DIR = Path(WORKSPACE) / "epaper"

# Helper functions
def is_gujarati_char(char):
    return '\u0A80' <= char <= '\u0AFF'

def calc_gujarati_ratio(text):
    if not text:
        return 0.0
    cleaned = re.sub(r'[\s0-9A-Za-z.,\'"()\-!?:;/]', '', text)
    if not cleaned:
        return 0.0
    guj_count = sum(1 for c in cleaned if is_gujarati_char(c))
    return guj_count / len(cleaned)

def hash_file(filepath):
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def extract_metadata_from_header(page):
    text = page.get_text("text")
    edition, date_str, page_no, category = None, None, None, "unknown"
    
    edition_match = re.search(r'(Bhuj|Ahmedabad|Surat|Rajkot|Vadodara|Bhavnagar)', text, re.IGNORECASE)
    if edition_match:
        edition = edition_match.group(1).capitalize()
        
    date_match = re.search(r'(\d{1,2}[A-Za-z]{2}\s+[A-Za-z]+\s+\d{4}|\d{2}-\d{2}-\d{4})', text)
    if date_match:
        # Simplification: just store raw string or parse to ISO if needed
        # We will just use the parsed string for now, or fake it if not parseable
        date_str = date_match.group(1)
        
    page_match = re.search(r'PAGE\s+(\d+)|Page\s*:\s*(\d+)', text, re.IGNORECASE)
    if page_match:
        page_no = int(page_match.group(1) or page_match.group(2))
        
    return edition, date_str, page_no, category

def clean_text(text):
    import unicodedata
    # NFC normalize and clean whitespace
    t = unicodedata.normalize('NFC', text)
    return re.sub(r'\s+', ' ', t).strip()

def process_pdf(pdf_path, file_hash):
    doc = fitz.open(pdf_path)
    articles = []
    skipped_garbled = 0
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        text_full = page.get_text("text")
        ratio = calc_gujarati_ratio(text_full)
        
        if ratio < 0.6:
            skipped_garbled += 1
            continue
            
        pw, ph = page.rect.width, page.rect.height
        gutter_px = pw * 0.008
        col_width = (pw - 7 * gutter_px) / 8
        slot_height = ph / 4
        
        edition, date_str, page_no_parsed, category = extract_metadata_from_header(page)
        actual_page_no = page_no_parsed if page_no_parsed else page_num + 1
        
        # We need a proper ISO datetime for Qdrant datetime index
        iso_date = None
        if date_str:
            try:
                if "-" in date_str:
                    iso_date = datetime.strptime(date_str, "%d-%m-%Y").isoformat()
                else:
                    # just a fallback
                    iso_date = datetime.now().isoformat()
            except:
                pass
                
        blocks = page.get_text("dict").get("blocks", [])
        text_blocks = []
        for b in blocks:
            if b.get("type") == 0:
                b_text, max_size = "", 0
                for line in b.get("lines", []):
                    for span in line.get("spans", []):
                        b_text += span.get("text", "") + " "
                        if span.get("size", 0) > max_size:
                            max_size = span["size"]
                b_text = b_text.strip()
                if not b_text: continue
                x0, y0, x1, y1 = b["bbox"]
                text_blocks.append({
                    "text": clean_text(b_text),
                    "max_size": max_size,
                    "bbox": (x0, y0, x1, y1)
                })
        
        # Group vertically adjacent
        text_blocks.sort(key=lambda x: (x["bbox"][1], x["bbox"][0]))
        groups = []
        used = set()
        for i, b in enumerate(text_blocks):
            if i in used: continue
            group = [b]
            used.add(i)
            for j, other in enumerate(text_blocks):
                if j in used: continue
                h_overlap = max(0, min(b["bbox"][2], other["bbox"][2]) - max(b["bbox"][0], other["bbox"][0]))
                if h_overlap > 0 and other["bbox"][1] - b["bbox"][3] < 100 and other["bbox"][1] > b["bbox"][1]:
                    group.append(other)
                    used.add(j)
                    b = other 
            groups.append(group)
            
        for g in groups:
            if not g: continue
            g.sort(key=lambda x: x["max_size"], reverse=True)
            headline = g[0]["text"] if g[0]["max_size"] > 12 else ""
            g_body = sorted([b for b in g if b != g[0]], key=lambda x: x["bbox"][1])
            body_text = " ".join([b["text"] for b in g_body])
            word_count = len(body_text.split())
            
            if not headline or word_count < 40:
                # skip ad or other
                continue
                
            intro = g_body[0]["text"] if g_body else ""
            body = " ".join([b["text"] for b in g_body[1:]]) if len(g_body) > 1 else ""
            
            x0 = min(b["bbox"][0] for b in g)
            y0 = min(b["bbox"][1] for b in g)
            x1 = max(b["bbox"][2] for b in g)
            y1 = max(b["bbox"][3] for b in g)
            col_span = max(1, round((x1 - x0) / col_width))
            slot_pos = max(1, min(4, int(y0 / slot_height) + 1))
            
            content = f"{headline} {intro} {body}"
            content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{file_hash}:{actual_page_no}:{content_hash}"))
            
            # Extract images logic (skipped for now, just empty list)
            images = []
            
            payload = {
                "doc_type": "article",
                "text_source": "native",
                "language": "gu",
                "edition": edition,
                "date": iso_date,
                "page_no": actual_page_no,
                "category": category,
                "column_span": col_span,
                "slot_count": 1, # approximation
                "slot_position": slot_pos,
                "bbox": [x0/pw, y0/ph, x1/pw, y1/ph],
                "headline": headline,
                "subheading": "",
                "intro": intro,
                "body": body,
                "info_box": "",
                "wc_headline": len(headline.split()),
                "wc_intro": len(intro.split()),
                "wc_body": len(body.split()),
                "total_words": word_count + len(headline.split()),
                "images": images,
                "source_file": pdf_path.name,
                "source_file_hash": file_hash,
                "content_hash": content_hash,
                "embedding_model": "BAAI/bge-m3",
                "created_at": datetime.now().isoformat(),
                "quality_flags": {
                    "has_headline": bool(headline),
                    "has_body": bool(body_text),
                    "min_words_ok": True
                }
            }
            articles.append((point_id, payload))
            
    doc.close()
    return articles, skipped_garbled

def batched(iterable, n):
    for i in range(0, len(iterable), n):
        yield iterable[i:i + n]

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument("--pdf", type=str, default="")
    parser.add_argument("--auto-full-run", action="store_true")
    args = parser.parse_args()
    
    logger.info(f"Starting ingest script. Target: {TARGET_COLLECTION}")
    
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    
    if args.recreate:
        confirm = input(f"Type '{TARGET_COLLECTION}' to recreate collection: ")
        if confirm == TARGET_COLLECTION:
            client.recreate_collection(
                collection_name=TARGET_COLLECTION,
                vectors_config={
                    "full": VectorParams(size=1024, distance=Distance.COSINE),
                    "headline": VectorParams(size=1024, distance=Distance.COSINE)
                }
            )
            logger.info("Collection recreated.")
        else:
            logger.warning("Recreate aborted.")
            return

    # 1. Extraction Phase
    logger.info("Extracting articles...")
    if args.pdf:
        pdfs = [EPAPER_DIR / args.pdf]
    else:
        pdfs = list(EPAPER_DIR.glob("*.pdf"))
        
    seen_hashes = set()
    unique_pdfs = []
    for p in pdfs:
        h = hash_file(p)
        if h not in seen_hashes:
            seen_hashes.add(h)
            unique_pdfs.append((p, h))
            
    all_articles = []
    total_skipped_garbled = 0
    total_failed = 0
    
    for pdf_path, fhash in unique_pdfs:
        try:
            arts, skipped = process_pdf(pdf_path, fhash)
            all_articles.extend(arts)
            total_skipped_garbled += skipped
        except Exception as e:
            logger.error(f"Failed to process {pdf_path.name}: {str(e)}")
            total_failed += 1
            
    logger.info(f"Extracted {len(all_articles)} valid articles. Skipped {total_skipped_garbled} garbled pages.")
    
    limit = 20 if args.auto_full_run else args.limit
    if limit > 0 and not args.auto_full_run:
        all_articles = all_articles[:limit]
        logger.info(f"Limiting to {limit} articles.")
        
    if args.dry_run:
        logger.info("Dry run complete. Sample payload:")
        if all_articles:
            print(all_articles[0][1])
        return
        
    # Load model only after extraction
    logger.info("Loading embedding model...")
    from app.services.embedding_service import embed_texts
    
    ingested = 0
    failed = 0
    fail_reasons = []
    
    # 2. Embedding and Upsert
    
    articles_to_process = all_articles[:limit] if limit > 0 else all_articles
    
    def process_batch_list(article_list):
        nonlocal ingested, failed, fail_reasons
        for batch in batched(article_list, 32):
            batch_ids = [item[0] for item in batch]
            batch_payloads = [item[1] for item in batch]
            full_texts = []
            head_texts = []
            for p in batch_payloads:
                full_text = f"{p['headline']} {p['subheading']} {p['intro']} {p['body']}"
                full_texts.append(full_text)
                head_texts.append(p['headline'])
            try:
                full_embs = embed_texts(full_texts)
                head_embs = embed_texts(head_texts)
                points = []
                for i in range(len(batch)):
                    points.append(PointStruct(id=batch_ids[i], payload=batch_payloads[i], vector={"full": full_embs[i], "headline": head_embs[i]}))
                for attempt in range(3):
                    try:
                        client.upsert(collection_name=TARGET_COLLECTION, points=points, wait=True)
                        ingested += len(points)
                        logger.info(f"Upserted batch of {len(points)} points. Total: {ingested}")
                        break
                    except Exception as e:
                        if attempt == 2: raise e
                        time.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"Failed to embed/upsert batch: {str(e)}")
                failed += len(batch)
                fail_reasons.append(str(e))
                
    process_batch_list(articles_to_process)
    
    # Print server point count
    try:
        count_res = client.count(collection_name=TARGET_COLLECTION)
        logger.info(f"Point count on server after limit run: {count_res.count}")
        
        # Check first 20 points
        points, _ = client.scroll(collection_name=TARGET_COLLECTION, limit=20, with_vectors=False)
        is_valid = True
        
        print("\n=== SAMPLE 3 POINTS FROM SERVER ===")
        for i, p in enumerate(points[:3]):
            print(f"ID: {p.id}")
            print(f"Payload: {p.payload}\n")
            
        for p in points:
            if not p.payload.get("headline") or not p.payload.get("body"):
                logger.error("Validation failed: empty headline or body found.")
                is_valid = False
                break
                
        if args.auto_full_run:
            if is_valid and len(points) > 0:
                logger.info("Validation passed! Proceeding with full run...")
                process_batch_list(all_articles[20:])
            else:
                logger.error("Validation failed or no points returned. Stopping auto-full-run.")
                
        count_res = client.count(collection_name=TARGET_COLLECTION)
        total_server_points = count_res.count
        logger.info(f"Final point count on server for {TARGET_COLLECTION}: {total_server_points}")
        
    except Exception as e:
        logger.error(f"Failed to verify on server: {e}")
        
    logger.info(f"Summary: Extracted {len(all_articles)}, Ingested {ingested}, Failed {failed}.")
    if fail_reasons:
        logger.info(f"Failure reasons: {fail_reasons[:3]}")

if __name__ == "__main__":
    main()
