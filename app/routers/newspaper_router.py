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

@router.post("/generate", response_model=NewspaperOutput)
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
                not config.headline_config.single_line
            )
            print(f"✅ Auto-calculated word count rules for {config.slot_config.column_span} columns, {config.slot_config.slot_count} slot(s)")
        
        # Scrape articles
        print(f"🔍 Scraping articles for: {config.topic}")
        articles = await scraper.scrape_topic(config.topic, limit_per_site=2)
        
        if not articles:
            raise HTTPException(
                status_code=404,
                detail="No articles found for this topic"
            )
        
        # Filter by allowed sources if specified
        if config.allowed_sources:
            articles = [
                a for a in articles 
                if any(source in a.source for source in config.allowed_sources)
            ]
            
            if not articles:
                # Return the exact error message as specified
                return NewspaperOutput(
                    topic=config.topic,
                    config_used=config,
                    headline="Sandesh authorised sources insufficient – unable to generate verified news.",
                    intro="",
                    body="",
                    validation_passed=False,
                    validation_errors=["Insufficient authorized sources"]
                )
        
        print(f"✅ Found {len(articles)} articles from {len(set(a.source for a in articles))} sources")
        
        # Generate newspaper article
        output = await newspaper_ai.generate_newspaper_article(articles, config)
        
        return output
        
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
            config.slot_config.column_span,
            config.slot_config.slot_count
        )
        
        # Get word count rules
        word_rules = grid_calc.get_word_count_rules(
            config.slot_config.column_span,
            config.slot_config.slot_count,
            not config.headline_config.single_line
        )
        
        return {
            "valid": True,
            "dimensions": {
                "width_cm": width_cm,
                "height_cm": height_cm,
                "area_cm2": area_cm2
            },
            "word_count_rules": word_rules.dict(),
            "message": "Configuration is valid"
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
        SlotConfig, HeadlineConfig, EditorialFilters, PageSettings
    )
    
    try:
        # Get word count rules
        word_rules = grid_calc.get_word_count_rules(
            request.column_span,
            request.slot_count
        )
        
        # Build example config
        example = NewspaperConfig(
            page_settings=PageSettings(),
            slot_config=SlotConfig(
                slot_count=request.slot_count,
                column_span=request.column_span
            ),
            headline_config=HeadlineConfig(),
            word_count_rules=word_rules,
            editorial_filters=EditorialFilters(),
            allowed_sources=["sandesh.com", "gujaratsamachar.com"],
            topic="અમદાવાદમાં વરસાદ"  # Example topic
        )
        
        return example.dict()
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
