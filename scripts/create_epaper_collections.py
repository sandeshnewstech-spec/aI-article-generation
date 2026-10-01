import os
import sys
import argparse
import logging
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PayloadSchemaType

# Add workspace to path
WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(WORKSPACE)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("create_collections")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recreate", action="store_true")
    args = parser.parse_args()
    
    load_dotenv(os.path.join(WORKSPACE, ".env"))
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")
    env = os.getenv("QDRANT_ENV", "dev")
    base = os.getenv("EPAPER_COLLECTION_BASE", "epaper_items")
    target_collection = f"{env}_{base}"
    
    client = QdrantClient(url=url, api_key=api_key)
    
    collections = client.get_collections().collections
    names = [c.name for c in collections]
    
    if target_collection in names and not args.recreate:
        logger.info(f"Collection {target_collection} already exists. Skipping creation.")
        return
        
    logger.info(f"Creating collection {target_collection}...")
    client.recreate_collection(
        collection_name=target_collection,
        vectors_config={
            "full": VectorParams(size=1024, distance=Distance.COSINE),
            "headline": VectorParams(size=1024, distance=Distance.COSINE)
        }
    )
    
    # Create indexes
    logger.info("Creating payload indexes...")
    indexes = [
        ("doc_type", PayloadSchemaType.KEYWORD),
        ("category", PayloadSchemaType.KEYWORD),
        ("edition", PayloadSchemaType.KEYWORD),
        ("ad_type", PayloadSchemaType.KEYWORD),
        ("column_span", PayloadSchemaType.INTEGER),
        ("slot_count", PayloadSchemaType.INTEGER),
        ("page_no", PayloadSchemaType.INTEGER),
        ("date", PayloadSchemaType.DATETIME),
        ("text_source", PayloadSchemaType.KEYWORD),
        ("content_hash", PayloadSchemaType.KEYWORD),
        ("source_file", PayloadSchemaType.KEYWORD)
    ]
    
    for field, schema in indexes:
        client.create_payload_index(
            collection_name=target_collection,
            field_name=field,
            field_schema=schema
        )
        
    logger.info("Collection creation complete.")

if __name__ == "__main__":
    main()
