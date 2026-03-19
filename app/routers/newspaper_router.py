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
            config.topic, limit_per_site=5, allowed_sites=config.allowed_sources
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
        results = []
        for i, output in enumerate(outputs):
            if i < len(articles):
                output.source = articles[i].source
                output.url = articles[i].url
                output.image_url = articles[i].image_url  # carry scraped image
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
        for i, site in enumerate(sites):
            try:
                # 1. Notify progress
                yield json.dumps({
                    "type": "progress", 
                    "site": site, 
                    "index": i, 
                    "total": len(sites),
                    "percentage": int(((i + 1) / len(sites)) * 100)
                }) + "\n"
                
                # 2. Scrape individual site
                articles = await scraper.scrape_topic(
                    config.topic, limit_per_site=5, allowed_sites=[site]
                )
                
                # 3. Send results for this site
                yield json.dumps({
                    "type": "site_done", 
                    "site": site, 
                    "articles": [a.dict() for a in articles]
                }) + "\n"
                
            except Exception as e:
                yield json.dumps({"type": "error", "site": site, "message": str(e)}) + "\n"

        yield json.dumps({"type": "all_done", "percentage": 100}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


@router.post("/scrape", response_model=List[ScrapedArticle])
async def scrape_articles_only(config: NewspaperConfig):
    """
    Step 1: Scrape articles for a given topic
    """
    try:
        print(f"[SCRAPE] Scraping articles for: {config.topic}")
        articles = await scraper.scrape_topic(
            config.topic, limit_per_site=5, allowed_sites=config.allowed_sources
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

        # Add metadata back to results
        results = []
        for i, output in enumerate(outputs):
            if i < len(articles):
                output.source = articles[i].source
                output.url = articles[i].url
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
