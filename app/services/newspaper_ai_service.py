from typing import List, Optional
from app.models.data import ScrapedArticle, NewspaperConfig, NewspaperOutput
from app.services.grid_calculator import GridCalculator
from app.services.headline_engineer import HeadlineEngineer
from app.services.newspaper_validator import NewspaperValidator
from app.services.ai_service import AIService
from app.core.config import settings
import asyncio
import re

class NewspaperAIService:
    """AI service specialized for newspaper article generation"""
    
    def __init__(self):
        self.base_ai = AIService()
        self.grid_calc = GridCalculator()
        self.headline_eng = HeadlineEngineer()
        self.validator = NewspaperValidator()
    
    def build_newspaper_prompt(self, 
                              articles: List[ScrapedArticle],
                              config: NewspaperConfig) -> str:
        """
        Build comprehensive newspaper generation prompt
        
        Args:
            articles: Scraped articles to synthesize
            config: Newspaper configuration with all rules
            
        Returns:
            Structured prompt for AI
        """
        # Combine article content
        combined_text = "\n\n".join([
            f"SOURCE: {a.source}\nTITLE: {a.title}\nCONTENT: {a.body}" 
            for a in articles
        ])
        
        # Get word count rules
        rules = config.word_count_rules
        
        # Build editorial filter instructions
        filter_instructions = []
        if config.editorial_filters.localization:
            filter_instructions.append("- Emphasize local/city relevance and impact on local readers")
        if config.editorial_filters.reader_psychology:
            filter_instructions.append("- Focus on 'What happens to me?' - reader impact")
        if config.editorial_filters.active_voice:
            filter_instructions.append("- Use ACTIVE voice only - avoid passive constructions")
        if config.editorial_filters.gujarati_tone:
            filter_instructions.append("- Maintain Gujarati newsroom tone - fact-based, concise, authoritative")
        if config.editorial_filters.highlight_numbers:
            filter_instructions.append("- Highlight numbers, percentages, currency with **bold** format")
        
        editorial_section = "\n".join(filter_instructions) if filter_instructions else "- Standard editorial tone"
        
        # Build headline instructions
        headline_instructions = []
        if config.headline_config.use_punch_words:
            punch_examples = ", ".join(HeadlineEngineer.PUNCH_WORDS_GUJ[:5])
            headline_instructions.append(f"- START with a PUNCH WORD (e.g., {punch_examples})")
        headline_instructions.append("- Follow formula: [PUNCH] + [WHO] + [WHAT] + [IMPACT]")
        if config.headline_config.lr_structure:
            headline_instructions.append("- Use L-R structure: Left=Subject, Middle=Event, Right=Impact")
        headline_instructions.append("- Use STRONG action verbs - avoid weak passive verbs")
        headline_instructions.append(f"- EXACTLY {rules.heading_min}-{rules.heading_max} words")
        
        headline_section = "\n".join(headline_instructions)
        
        # Build source restriction
        if config.allowed_sources:
            source_list = ", ".join(config.allowed_sources)
            source_restriction = f"""
CRITICAL SOURCE RESTRICTION:
You may ONLY use information from these authorized sources: {source_list}

If the provided content does NOT contain sufficient verified information from these sources:
Return EXACTLY this message:
"Sandesh authorised sources insufficient – unable to generate verified news."

Do NOT fabricate information.
Do NOT use Google, Wikipedia, or Social Media.
"""
        else:
            source_restriction = "Use all provided sources."
        
        # Build complete prompt
        prompt = f"""
You are an AI-powered Gujarati newspaper layout and news-writing engine.

TOPIC: {config.topic}

{source_restriction}

MANDATORY OUTPUT STRUCTURE:
You MUST output sections in this EXACT order with these EXACT labels:

HEADLINE:
[Your headline here - {rules.heading_min}-{rules.heading_max} words]
"""
        
        if config.headline_config.use_headline_cap:
            prompt += f"""
HEADLINE CAP:
[Headline cap here - {rules.heading_min}-{rules.heading_max} words]
"""
        
        if config.headline_config.use_subheading:
            prompt += f"""
SUB HEADING:
[Subheading here - {rules.subheading_min}-{rules.subheading_max} words]
"""
        
        prompt += f"""
INTRO PARAGRAPH:
[Intro paragraph here - {rules.intro_min}-{rules.intro_max} words]

BODY PARAGRAPH:
[Body paragraphs here - {rules.body_min}-{rules.body_max} words total]
"""
        
        if rules.info_box_min and rules.info_box_max:
            prompt += f"""
INFO BOX:
[Info box here - {rules.info_box_min}-{rules.info_box_max} words]
"""
        
        prompt += f"""

HEADLINE ENGINEERING RULES:
{headline_section}

EDITORIAL FILTERS:
{editorial_section}

WORD COUNT REQUIREMENTS (STRICT):
- Heading: {rules.heading_min}-{rules.heading_max} words
- Subheading: {rules.subheading_min}-{rules.subheading_max} words
- Intro: {rules.intro_min}-{rules.intro_max} words
- Body: {rules.body_min}-{rules.body_max} words
"""
        
        if rules.info_box_min:
            prompt += f"- Info Box: {rules.info_box_min}-{rules.info_box_max} words\n"
        
        prompt += f"""

CRITICAL RULES:
1. Output ONLY in Gujarati
2. Stay STRICTLY within word count limits
3. Use the EXACT section labels shown above
4. No additional commentary or explanations
5. No markdown formatting
6. Plain newspaper format only
7. No repetition of words/phrases
8. Fact-based and verified information only

SOURCE CONTENT:
{combined_text}

Generate the newspaper article now following ALL rules above.
"""
        
        return prompt
    
    async def generate_newspaper_article(self,
                                        articles: List[ScrapedArticle],
                                        config: NewspaperConfig,
                                        max_attempts: int = 3) -> NewspaperOutput:
        """
        Generate newspaper article with validation and retry
        
        Args:
            articles: Scraped articles
            config: Newspaper configuration
            max_attempts: Maximum generation attempts
            
        Returns:
            Validated NewspaperOutput
        """
        for attempt in range(max_attempts):
            print(f"📰 Generation attempt {attempt + 1}/{max_attempts}...")
            
            # Build prompt
            prompt = self.build_newspaper_prompt(articles, config)
            
            # Generate content
            raw_output = await self.base_ai.generate_content(prompt)
            
            # Parse output
            parsed = self._parse_output(raw_output, config)
            
            # Validate
            is_valid, validation_results = self.validator.comprehensive_validation(
                parsed, config
            )
            
            if is_valid:
                print("✅ Validation passed!")
                parsed.validation_passed = True
                return parsed
            else:
                # Collect all errors
                all_errors = []
                for category, errors in validation_results.items():
                    all_errors.extend(errors)
                
                print(f"⚠️ Validation failed: {', '.join(all_errors[:3])}")
                parsed.validation_errors = all_errors
                
                if attempt < max_attempts - 1:
                    print("🔄 Regenerating...")
                    await asyncio.sleep(2)  # Brief pause before retry
        
        # Return last attempt even if invalid
        print("❌ Max attempts reached - returning last output with errors")
        return parsed
    
    def _parse_output(self, raw_output: str, config: NewspaperConfig) -> NewspaperOutput:
        """
        Parse AI output into structured NewspaperOutput
        
        Args:
            raw_output: Raw AI generated text
            config: Configuration used
            
        Returns:
            Parsed NewspaperOutput
        """
        sections = {
            "headline": "",
            "headline_cap": None,
            "subheading": None,
            "intro": "",
            "body": "",
            "info_box": None
        }
        
        # Split by section labels
        lines = raw_output.split('\n')
        current_section = None
        current_content = []
        
        for line in lines:
            line_upper = line.strip().upper()
            
            if line_upper.startswith("HEADLINE:"):
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = "headline"
                current_content = [line.replace("HEADLINE:", "").strip()]
            elif line_upper.startswith("HEADLINE CAP:"):
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = "headline_cap"
                current_content = [line.replace("HEADLINE CAP:", "").strip()]
            elif line_upper.startswith("SUB HEADING:"):
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = "subheading"
                current_content = [line.replace("SUB HEADING:", "").strip()]
            elif line_upper.startswith("INTRO PARAGRAPH:"):
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = "intro"
                current_content = [line.replace("INTRO PARAGRAPH:", "").strip()]
            elif line_upper.startswith("BODY PARAGRAPH:"):
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = "body"
                current_content = [line.replace("BODY PARAGRAPH:", "").strip()]
            elif line_upper.startswith("INFO BOX:"):
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = "info_box"
                current_content = [line.replace("INFO BOX:", "").strip()]
            elif current_section and line.strip():
                current_content.append(line)
        
        # Save last section
        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()
        
        return NewspaperOutput(
            topic=config.topic,
            config_used=config,
            headline=sections["headline"] or "શીર્ષક ઉપલબ્ધ નથી",
            headline_cap=sections["headline_cap"],
            subheading=sections["subheading"],
            intro=sections["intro"] or "પરિચય ઉપલબ્ધ નથી",
            body=sections["body"] or "સામગ્રી ઉપલબ્ધ નથી",
            info_box=sections["info_box"],
            validation_passed=False,
            validation_errors=[]
        )
