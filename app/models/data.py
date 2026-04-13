from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime


class NewspaperPageConfig(BaseModel):
    """Configuration for a full newspaper page"""

    date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    year: str = Field(default_factory=lambda: str(datetime.now().year))
    page_number: int = Field(default=1, ge=1)
    day: str = Field(default="Monday")
    edition: str = Field(default="Ahmedabad")


class NewspaperPage(BaseModel):
    """A full newspaper page containing multiple articles"""

    config: NewspaperPageConfig
    articles: List[NewspaperOutput]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ScrapedArticle(BaseModel):
    source: str
    url: str
    title: str
    body: str
    image_url: Optional[str] = None  # Main article image scraped from the page


class GenerationResult(BaseModel):
    topic: str
    formal_style: str
    conversational_style: str
    analytical_style: str


# ============================================
# NEWSPAPER LAYOUT ENGINE MODELS
# ============================================


class PageSettings(BaseModel):
    """Physical page dimensions and layout settings"""

    height_cm: float = Field(default=80, description="Page height in cm")
    width_cm: float = Field(default=50, description="Page width in cm")
    top_margin_cm: float = Field(default=4, description="Top margin in cm")
    bottom_margin_cm: float = Field(default=3, description="Bottom margin in cm")
    total_columns: int = Field(default=8, description="Total number of columns")
    gutter_space_cm: float = Field(
        default=0.4, description="Space between columns in cm"
    )


class SlotConfig(BaseModel):
    """Slot and column configuration for article placement"""

    slot_count: int = Field(ge=1, le=4, description="Number of vertical slots (1-4)")
    column_span: int = Field(ge=1, le=8, description="Number of columns to span (1-8)")
    position: Optional[str] = Field(default="top-left", description="Position on page")


class HeadlineConfig(BaseModel):
    """Headline generation and formatting rules"""

    use_punch_words: bool = Field(
        default=True, description="Add punch words at beginning"
    )
    use_headline_cap: bool = Field(default=False, description="Include headline cap")
    use_subheading: bool = Field(default=True, description="Include subheading")
    lr_structure: bool = Field(default=True, description="Enforce Left-Right structure")
    single_line: bool = Field(
        default=True, description="Single-line vs double-line heading"
    )


class WordCountRules(BaseModel):
    """Word count constraints for each section"""

    heading_min: int = Field(ge=1, description="Minimum words in heading")
    heading_max: int = Field(ge=1, description="Maximum words in heading")
    subheading_min: int = Field(ge=1, description="Minimum words in subheading")
    subheading_max: int = Field(ge=1, description="Maximum words in subheading")
    intro_min: int = Field(ge=1, description="Minimum words in intro paragraph")
    intro_max: int = Field(ge=1, description="Maximum words in intro paragraph")
    body_min: int = Field(ge=1, description="Minimum words in body")
    body_max: int = Field(ge=1, description="Maximum words in body")
    info_box_min: Optional[int] = Field(
        default=None, description="Minimum words in info box"
    )
    info_box_max: Optional[int] = Field(
        default=None, description="Maximum words in info box"
    )


class EditorialFilters(BaseModel):
    """Editorial style and content filters"""

    localization: bool = Field(
        default=True, description="Emphasize local/city relevance"
    )
    reader_psychology: bool = Field(default=True, description="Focus on reader impact")
    active_voice: bool = Field(default=True, description="Enforce active voice")
    gujarati_tone: bool = Field(
        default=True, description="Maintain Gujarati newsroom tone"
    )
    highlight_numbers: bool = Field(
        default=True, description="Bold numbers, percentages, currency"
    )


class NewspaperConfig(BaseModel):
    """Complete newspaper article configuration"""

    page_settings: PageSettings = Field(default_factory=PageSettings)
    slot_config: SlotConfig
    headline_config: HeadlineConfig = Field(default_factory=HeadlineConfig)
    word_count_rules: Optional[WordCountRules] = Field(
        default=None, description="Auto-calculated if not provided"
    )
    editorial_filters: EditorialFilters = Field(default_factory=EditorialFilters)
    allowed_sources: List[str] = Field(
        default_factory=list, description="Whitelisted source domains"
    )
    topic: str = Field(description="News topic to generate article for")
    limit: int = Field(default=5, ge=1, le=20, description="Max articles to scrape per site")


class GenerateFromContentRequest(BaseModel):
    """Request to generate articles from pre-scraped content"""

    articles: List[ScrapedArticle]
    config: NewspaperConfig


class GenerateFromKeypointsRequest(BaseModel):
    """Request to generate news from manual keypoints/notes"""

    keypoints: str
    config: NewspaperConfig


class NewspaperSection(BaseModel):
    """Individual section of newspaper output"""

    section_type: (
        str  # "headline", "headline_cap", "subheading", "intro", "body", "info_box"
    )
    content: str
    word_count: int


class NewspaperOutput(BaseModel):
    """Structured newspaper article output"""

    topic: str
    config_used: NewspaperConfig
    headline: str
    headline_cap: Optional[str] = None
    subheading: Optional[str] = None
    intro: str
    body: str
    info_box: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None  # Scraped article image from source page
    validation_passed: bool = True
    validation_errors: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

class GenerateResponse(BaseModel):
    articles: List[NewspaperOutput]
    history_id: str

class MergeRequest(BaseModel):
    selected_articles: List[NewspaperOutput]
    config: NewspaperConfig
    history_id: Optional[str] = None

class HistoryItem(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    topic: str
    articles: List[NewspaperOutput]
    final_article: Optional[NewspaperOutput] = None
    final_reports: List[NewspaperOutput] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    config_used: NewspaperConfig

    def to_plain_text(self) -> str:
        """Convert to plain newspaper format"""
        output = []
        output.append(self.headline)
        if self.headline_cap:
            output.append(self.headline_cap)
        if self.subheading:
            output.append(self.subheading)
        output.append("")  # blank line
        output.append(self.intro)
        output.append("")
        output.append(self.body)
        if self.info_box:
            output.append("")
            output.append("━" * 40)
            output.append(self.info_box)
            output.append("━" * 40)
        return "\n".join(output)
