from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import json
from pydantic import BaseModel
from app.models.data import (
    NewspaperConfig,
    NewspaperOutput,
    ScrapedArticle,
    GenerateFromContentRequest,
    GenerateFromKeypointsRequest,
    GenerateResponse,
    MergeRequest,
    NewspaperPage,
    NewspaperPageConfig,
)
from app.services.newspaper_ai_service import NewspaperAIService
from app.services.scraper_service_sync import ScraperService
from app.services.grid_calculator import GridCalculator
from app.core.database import get_db
from datetime import datetime
import json

router = APIRouter(prefix="/newspaper", tags=["newspaper"])

newspaper_ai = NewspaperAIService()
scraper = ScraperService()
grid_calc = GridCalculator()


from typing import List


@router.post("/generate", response_model=GenerateResponse)
async def generate_newspaper_article(config: NewspaperConfig):
    """
    Generate a newspaper article following strict layout and editorial rules

    Accepts a NewspaperConfig JSON with:
    - Page/slot/column settings
    - Headline configuration
    - Word count rules
    - Editorial filters
    - Source restrictions

    Returns a validated NewspaperOutput with structured sections
    """
    try:
        print(f"[AI] Generating newspaper article for topic: {config.topic}")

        # Auto-calculate word count rules if not provided
        if config.word_count_rules is None:
            config.word_count_rules = grid_calc.get_word_count_rules(
                config.slot_config.column_span,
                config.slot_config.slot_count,
                not config.headline_config.single_line,
            )
            print(
                f"✅ Auto-calculated word count rules for {config.slot_config.column_span} columns, {config.slot_config.slot_count} slot(s)"
            )

        # Scrape articles
        print(f"[SCRAPE] Scraping articles for: {config.topic}")
        # Pass allowed_sources directly to scraper to filter at source
        articles = await scraper.scrape_topic(
            config.topic, limit_per_site=config.limit, allowed_sites=config.allowed_sources
        )

        if not articles:
            # If specific sources were requested but nothing found, return specific error
            if config.allowed_sources:
                return [
                    NewspaperOutput(
                        topic=config.topic,
                        config_used=config,
                        headline="Selected sources insufficient – unable to generate verified news.",
                        intro="",
                        body="",
                        validation_passed=False,
                        validation_errors=["Insufficient authorized sources"],
                    )
                ]

            raise HTTPException(
                status_code=404, detail="No articles found for this topic"
            )

        print(
            f"✅ Found {len(articles)} articles from {len(set(a.source for a in articles))} sources"
        )

        # Generator for each article
        print(f"[AI] Processing {len(articles)} articles in batch...")

        # Batch generation
        outputs = await newspaper_ai.generate_batch_newspaper_articles(articles, config)

        # Add metadata back to results
        from app.services.image_service import ImageService
        img_service = ImageService()
        results = []
        for i, output in enumerate(outputs):
            if i < len(articles):
                output.source = articles[i].source
                output.url = articles[i].url
                
                # --- SMART IMAGE FALLBACK ---
                # If scraper found NO image, try a quick headline search
                image_url = articles[i].image_url
                if not image_url or len(image_url) < 5:
                    print(f"[AI-IMAGE] No photo scraped for '{output.headline[:30]}...', trying search fallback...")
                    try:
                        search_query = " ".join(output.headline.split()[:8])
                        results_imgs = await img_service.get_images(search_query, max_results=1)
                        if results_imgs and len(results_imgs) > 0:
                            image_url = results_imgs[0].get("image_url")
                            print(f"[AI-IMAGE] Fallback found: {image_url[:60] if image_url else 'None'}")
                    except Exception as e:
                        print(f"[AI-IMAGE] Fallback failed: {e}")

                # --- PERSIST IMAGE LOCALLY ---
                # Download to local disk so it always loads (no hotlink issues)
                if image_url and image_url.startswith("http"):
                    try:
                        local_url = await img_service.persist_scraped_image(image_url)
                        image_url = local_url
                    except Exception as e:
                        print(f"[AI-IMAGE] Persist failed, using original URL: {e}")

                output.image_url = image_url
            results.append(output)

        # Save results to history
        history_id = ""
        try:
            db = get_db()
            history_item = {
                "topic": config.topic,
                "articles": [r.dict() for r in results],
                "created_at": datetime.utcnow(),
                "config_used": config.dict(),
                "final_article": None,
            }
            res = await db["history"].insert_one(history_item)
            history_id = str(res.inserted_id)
            print(f"[OK] Saved history for: {config.topic}")
        except Exception as e:
            print(f"[WARN] Failed to save history: {e}")

        return GenerateResponse(articles=results, history_id=history_id)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrape-stream")
async def scrape_articles_stream(config: NewspaperConfig):
    """
    Step 1 (Streaming): Scrape articles site by site and stream progress
    """
    async def event_generator():
        sites = config.allowed_sources if config.allowed_sources else scraper.SITES
        
        try:
            print(f"[STREAM] Starting scrape for {len(sites)} sites...")
            # 1. Start streaming from scraper service
            async for result in scraper.scrape_topic_stream(
                config.topic, limit_per_site=config.limit, allowed_sites=sites
            ):
                site_name = result["site"]
                articles_list = result["articles"]
                
                event_generator.counter = getattr(event_generator, 'counter', 0) + 1
                i = event_generator.counter - 1
                
                # Send Heartbeat/Progress
                yield json.dumps({
                    "type": "progress", 
                    "site": site_name, 
                    "index": i, 
                    "total": len(sites),
                    "percentage": int(((i + 1) / len(sites)) * 100)
                }) + "\n"
                
                # Send Result
                yield json.dumps({
                    "type": "site_done", 
                    "site": site_name, 
                    "articles": [a.dict() for a in articles_list]
                }) + "\n"
                
                print(f"[STREAM] Successfully pushed results for {site_name}")

        except Exception as e:
            print(f"[CRITICAL_ERROR] Stream processing failed: {e}")
            yield json.dumps({"type": "error", "message": f"Global error: {str(e)}"}) + "\n"

        yield json.dumps({"type": "all_done", "percentage": 100}) + "\n"
        print(f"[STREAM] Scrape-stream completed.")

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


@router.post("/scrape", response_model=List[ScrapedArticle])
async def scrape_articles_only(config: NewspaperConfig):
    """
    Step 1: Scrape articles for a given topic
    """
    try:
        print(f"[SCRAPE] Scraping articles for: {config.topic}")
        articles = await scraper.scrape_topic(
            config.topic, limit_per_site=config.limit, allowed_sites=config.allowed_sources
        )

        if not articles and config.allowed_sources:
            # Return empty list instead of 404 so frontend can handle it gracefully if needed,
            # or we can raise 404. Let's raise 404 to match original behavior.
            pass

        if not articles:
            raise HTTPException(
                status_code=404, detail="No articles found for this topic"
            )

        print(f"[OK] Found {len(articles)} articles")
        return articles

    except Exception as e:
        print(f"[ERROR] Error scraping articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-from-content", response_model=GenerateResponse)
async def generate_from_content(request: GenerateFromContentRequest):
    """
    Step 2: Generate articles from scraped content
    """
    try:
        config = request.config
        articles = request.articles

        if not articles:
            raise HTTPException(status_code=400, detail="No articles provided")

        print(f"[AI] Processing {len(articles)} articles in batch...")

        # Auto-calculate word count rules if not provided (safety check)
        if config.word_count_rules is None:
            config.word_count_rules = grid_calc.get_word_count_rules(
                config.slot_config.column_span,
                config.slot_config.slot_count,
                not config.headline_config.single_line,
            )

        # Batch generation
        outputs = await newspaper_ai.generate_batch_newspaper_articles(articles, config)

        # Add metadata back to results (including image!)
        from app.services.image_service import ImageService
        img_service = ImageService()
        results = []
        for i, output in enumerate(outputs):
            if i < len(articles):
                output.source = articles[i].source
                output.url = articles[i].url

                # Carry scraped image URL
                image_url = articles[i].image_url

                # Fallback: search for image using headline if scraper found nothing
                if not image_url or len(image_url) < 5:
                    print(f"[AI-IMAGE] No photo for '{output.headline[:30]}...', trying search...")
                    try:
                        search_query = " ".join(output.headline.split()[:8])
                        imgs = await img_service.get_images(search_query, max_results=1)
                        if imgs:
                            image_url = imgs[0].get("image_url")
                            print(f"[AI-IMAGE] Found fallback: {image_url[:60] if image_url else 'None'}")
                    except Exception as e:
                        print(f"[AI-IMAGE] Fallback search failed: {e}")

                # Save image locally so it always loads (bypasses hotlinks)
                if image_url and image_url.startswith("http"):
                    try:
                        image_url = await img_service.persist_scraped_image(image_url)
                    except Exception as e:
                        print(f"[AI-IMAGE] Persist failed, using original: {e}")

                output.image_url = image_url
            results.append(output)

        # Save to history
        history_id = ""
        try:
            db = get_db()
            history_item = {
                "topic": config.topic,
                "articles": [
                    r.dict() for r in results if r.headline != "Generation Error"
                ],
                "created_at": datetime.utcnow(),
                "config_used": config.dict(),
                "final_article": None,
            }
            if history_item["articles"]:
                res = await db["history"].insert_one(history_item)
                history_id = str(res.inserted_id)
                print(f"[OK] Saved search history for: {config.topic}")
        except Exception as e:
            print(f"[WARN] Failed to save history: {e}")

        return GenerateResponse(articles=results, history_id=history_id)

    except Exception as e:
        print(f"[ERROR] Error generating from content: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-from-keypoints", response_model=GenerateResponse)
async def generate_from_keypoints_endpoint(request: GenerateFromKeypointsRequest):
    """
    Generate news article from user-provided keypoints
    """
    try:
        config = request.config
        keypoints = request.keypoints

        if not keypoints:
            raise HTTPException(status_code=400, detail="No keypoints provided")

        # Auto-calculate word count rules
        if config.word_count_rules is None:
            config.word_count_rules = grid_calc.get_word_count_rules(
                config.slot_config.column_span,
                config.slot_config.slot_count,
                not config.headline_config.single_line,
            )

        # Generate single article
        output = await newspaper_ai.generate_from_keypoints(keypoints, config)

        # Save to history
        history_id = ""
        try:
            db = get_db()
            history_item = {
                "topic": output.headline,
                "keypoints": keypoints,              # ← Store original keypoints
                "articles": [output.dict()],
                "created_at": datetime.utcnow(),
                "config_used": config.dict(),
                "final_article": None,
            }
            res = await db["editor_history"].insert_one(history_item)
            history_id = str(res.inserted_id)
            print(f"[OK] Saved NEW EDITOR history for: {output.headline}")
        except Exception as e:
            print(f"[WARN] Failed to save history: {e}")

        return GenerateResponse(articles=[output], history_id=history_id)

    except Exception as e:
        print(f"[ERROR] Error generating from keypoints: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rewrite", response_model=GenerateResponse)
async def high_quality_rewrite_endpoint(request: GenerateFromKeypointsRequest):
    """
    Rewrite text using the Senior Gujarati Editor prompt
    """
    try:
        config = request.config
        text = request.keypoints  # Use keypoints field for input text
        
        output = await newspaper_ai.high_quality_rewrite(text, config)
        
        # Save to history
        history_id = request.history_id or ""
        try:
            db = get_db()
            from bson import ObjectId
            if history_id:
                try:
                    existing = await db["editor_history"].find_one({"_id": ObjectId(history_id)})
                    if existing:
                        # Append the new version to 'articles' and update relevant fields
                        await db["editor_history"].update_one(
                            {"_id": ObjectId(history_id)},
                            {
                                "$push": {"articles": output.dict()},
                                "$set": {
                                    "topic": output.headline,
                                    "config_used": config.dict()
                                }
                            }
                        )
                        print(f"[OK] Appended senior edit to existing history item: {history_id}")
                    else:
                        history_id = ""
                except Exception as ex:
                    print(f"[WARN] Error updating existing history: {ex}")
                    history_id = ""
            
            if not history_id:
                history_item = {
                    "topic": output.headline,
                    "keypoints": text,              # ← Store original text for restore
                    "articles": [output.dict()],
                    "created_at": datetime.utcnow(),
                    "config_used": config.dict(),
                    "final_article": None,
                }
                res = await db["editor_history"].insert_one(history_item)
                history_id = str(res.inserted_id)
                print(f"[OK] Saved NEW SENIOR EDITOR history for: {output.headline}")
        except Exception as e:
            print(f"[WARN] Failed to save history: {e}")
            
        return GenerateResponse(articles=[output], history_id=history_id)
        
    except Exception as e:
        print(f"[ERROR] Error in High-quality rewrite: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/validate-config")
async def validate_config(config: NewspaperConfig):
    """
    Validate a newspaper configuration without generating

    Returns calculated dimensions and word count rules
    """
    try:
        # Calculate dimensions
        width_cm = grid_calc.calculate_column_width(config.slot_config.column_span)
        height_cm = grid_calc.calculate_slot_height(config.slot_config.slot_count)
        area_cm2 = grid_calc.calculate_total_area(
            config.slot_config.column_span, config.slot_config.slot_count
        )

        # Get word count rules
        word_rules = grid_calc.get_word_count_rules(
            config.slot_config.column_span,
            config.slot_config.slot_count,
            not config.headline_config.single_line,
        )

        return {
            "valid": True,
            "dimensions": {
                "width_cm": width_cm,
                "height_cm": height_cm,
                "area_cm2": area_cm2,
            },
            "word_count_rules": word_rules.dict(),
            "message": "Configuration is valid",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ExampleConfigRequest(BaseModel):
    column_span: int
    slot_count: int


@router.post("/example-config")
async def get_example_config(request: ExampleConfigRequest):
    """
    Get an example configuration for given column/slot combination

    Returns a complete NewspaperConfig with auto-calculated word counts
    """
    from app.models.data import (
        SlotConfig,
        HeadlineConfig,
        EditorialFilters,
        PageSettings,
    )

    try:
        # Get word count rules
        word_rules = grid_calc.get_word_count_rules(
            request.column_span, request.slot_count
        )

        # Build example config
        example = NewspaperConfig(
            page_settings=PageSettings(),
            slot_config=SlotConfig(
                slot_count=request.slot_count, column_span=request.column_span
            ),
            headline_config=HeadlineConfig(),
            word_count_rules=word_rules,
            editorial_filters=EditorialFilters(),
            allowed_sources=["sandesh.com", "gujaratsamachar.com"],
            topic="અમદાવાદમાં વરસાદ",  # Example topic
        )

        return example.dict()

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class RefineRequest(BaseModel):
    selected_article: NewspaperOutput
    config: NewspaperConfig


@router.post("/refine", response_model=NewspaperOutput)
async def refine_article(request: RefineRequest):
    """
    Refine a selected article to match strict editorial standards
    """
    try:
        if not request.selected_article:
            raise HTTPException(status_code=400, detail="No article selected")

        print(f"[AI] Refining article for topic: {request.config.topic}")

        # Call refinement service
        refined_output = await newspaper_ai.refine_newspaper_article(
            request.selected_article, request.config
        )

        return refined_output

    except Exception as e:
        print(f"[ERROR] Error refining article: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Removed local MergeRequest definition (now in data.py)


@router.post("/merge-refine", response_model=NewspaperOutput)
async def merge_articles(request: MergeRequest):
    """
    Merge multiple selected drafts into one final polished article
    """
    try:
        if not request.selected_articles or len(request.selected_articles) == 0:
            raise HTTPException(status_code=400, detail="No articles selected to merge")

        print(
            f"✨ Merging {len(request.selected_articles)} articles for topic: {request.config.topic}"
        )

        # Ensure word count rules exist
        if request.config.word_count_rules is None:
            print("[WARN] Word count rules missing in merge request, recalculating...")
            request.config.word_count_rules = grid_calc.get_word_count_rules(
                request.config.slot_config.column_span,
                request.config.slot_config.slot_count,
                not request.config.headline_config.single_line,
            )

        # Call merge service
        final_output = await newspaper_ai.merge_and_refine_articles(
            request.selected_articles, request.config
        )

        # Update history with final report
        try:
            db = get_db()
            if request.history_id:
                # Update existing record
                from bson import ObjectId

                await db["history"].update_one(
                    {"_id": ObjectId(request.history_id)},
                    {
                        "$set": {"final_article": final_output.dict()},
                        "$push": {"final_reports": final_output.dict()},
                    },
                )
                print(
                    f"[OK] Updated history {request.history_id} with another final merge"
                )
            else:
                # Fallback: create a new record if no history_id
                history_item = {
                    "topic": f"Merged: {request.config.topic}",
                    "articles": request.selected_articles,
                    "final_article": final_output.dict(),
                    "final_reports": [final_output.dict()],
                    "created_at": datetime.utcnow(),
                    "config_used": request.config.dict(),
                }
                await db["history"].insert_one(history_item)
                print(f"[OK] Saved NEW merged history for: {request.config.topic}")
        except Exception as e:
            print(f"[WARN] Failed to update history: {e}")

        return final_output

    except Exception as e:
        import traceback

        print(f"[ERROR] Error merging articles: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save-page", response_model=dict)
async def save_newspaper_page(page: NewspaperPage):
    """Save a full newspaper page with multiple articles"""
    try:
        db = get_db()
        page_dict = page.dict()
        page_dict["created_at"] = datetime.utcnow()
        res = await db["newspaper_pages"].insert_one(page_dict)
        return {"id": str(res.inserted_id), "status": "success"}
    except Exception as e:
        print(f"[ERROR] Failed to save page: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pages", response_model=List[dict])
async def list_newspaper_pages():
    """List all saved newspaper pages"""
    try:
        db = get_db()
        cursor = db["newspaper_pages"].find().sort("created_at", -1)
        pages = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            pages.append(doc)
        return pages
    except Exception as e:
        print(f"[ERROR] Failed to list pages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/page/{page_id}", response_model=dict)
async def get_newspaper_page(page_id: str):
    """Get a specific newspaper page by ID"""
    try:
        from bson import ObjectId
        db = get_db()
        doc = await db["newspaper_pages"].find_one({"_id": ObjectId(page_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Page not found")
        doc["_id"] = str(doc["_id"])
        return doc
    except Exception as e:
        print(f"[ERROR] Failed to get page: {e}")
        raise HTTPException(status_code=500, detail=str(e))
