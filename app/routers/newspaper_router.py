from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.models.data import NewspaperConfig, NewspaperOutput
from app.services.newspaper_ai_service import NewspaperAIService
from app.services.scraper_service_sync import ScraperService
from app.services.grid_calculator import GridCalculator

router = APIRouter(prefix="/newspaper", tags=["newspaper"])

newspaper_ai = NewspaperAIService()
scraper = ScraperService()
grid_calc = GridCalculator()


from typing import List


@router.post("/generate", response_model=List[NewspaperOutput])
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
        print(f"📰 Generating newspaper article for topic: {config.topic}")

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
        print(f"🔍 Scraping articles for: {config.topic}")
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
        print(f"🤖 Processing processed {len(articles)} articles in batch...")

        # Batch generation
        outputs = await newspaper_ai.generate_batch_newspaper_articles(articles, config)

        # Add metadata back to results
        results = []
        for i, output in enumerate(outputs):
            if i < len(articles):
                output.source = articles[i].source
                output.url = articles[i].url
            results.append(output)

        return results

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error generating newspaper article: {e}")
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

        print(f"✨ Refining article for topic: {request.config.topic}")

        # Call refinement service
        refined_output = await newspaper_ai.refine_newspaper_article(
            request.selected_article, request.config
        )

        return refined_output

    except Exception as e:
        print(f"❌ Error refining article: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class MergeRequest(BaseModel):
    selected_articles: List[NewspaperOutput]
    config: NewspaperConfig


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
            print("⚠️ Word count rules missing in merge request, recalculating...")
            request.config.word_count_rules = grid_calc.get_word_count_rules(
                request.config.slot_config.column_span,
                request.config.slot_config.slot_count,
                not request.config.headline_config.single_line,
            )

        # Call merge service
        final_output = await newspaper_ai.merge_and_refine_articles(
            request.selected_articles, request.config
        )

        return final_output

    except Exception as e:
        import traceback

        print(f"❌ Error merging articles: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
