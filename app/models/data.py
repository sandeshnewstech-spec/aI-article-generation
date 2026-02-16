from pydantic import BaseModel, Field
from typing import List, Dict, Optional


class ScrapedArticle(BaseModel):
    source: str
    url: str
    title: str
    body: str


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
    column_span: int = Field(ge=1, le=5, description="Number of columns to span (1-5)")
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
    validation_passed: bool
    validation_errors: List[str] = Field(default_factory=list)

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
