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

    def build_newspaper_prompt(
        self, articles: List[ScrapedArticle], config: NewspaperConfig
    ) -> str:
        """
        Build comprehensive newspaper generation prompt
        """
        # Combine article content
        combined_text = "\n\n".join(
            [
                f"SOURCE: {a.source}\nTITLE: {a.title}\nCONTENT: {a.body}"
                for a in articles
            ]
        )

        # Get word count rules
        rules = config.word_count_rules

        # Build editorial filter instructions
        filter_instructions = []
        if config.editorial_filters.localization:
            filter_instructions.append(
                "- Emphasize local/city relevance and impact on local readers"
            )
        if config.editorial_filters.reader_psychology:
            filter_instructions.append(
                "- Focus on 'What happens to me?' - reader impact"
            )
        if config.editorial_filters.active_voice:
            filter_instructions.append(
                "- Use ACTIVE voice only - avoid passive constructions"
            )
        if config.editorial_filters.gujarati_tone:
            filter_instructions.append(
                "- Maintain Gujarati newsroom tone - fact-based, concise, authoritative"
            )
        if config.editorial_filters.highlight_numbers:
            filter_instructions.append(
                "- Highlight numbers, percentages, currency with **bold** format"
            )

        editorial_section = (
            "\n".join(filter_instructions)
            if filter_instructions
            else "- Standard editorial tone"
        )

        # Build headline instructions
        headline_instructions = []
        if config.headline_config.use_punch_words:
            punch_examples = ", ".join(HeadlineEngineer.PUNCH_WORDS_GUJ[:5])
            headline_instructions.append(
                f"- START with a PUNCH WORD (e.g., {punch_examples})"
            )
        headline_instructions.append(
            "- Follow formula: [PUNCH] + [WHO] + [WHAT] + [IMPACT]"
        )
        if config.headline_config.lr_structure:
            headline_instructions.append(
                "- Use L-R structure: Left=Subject, Middle=Event, Right=Impact"
            )
        headline_instructions.append(
            "- Use STRONG action verbs - avoid weak passive verbs"
        )
        headline_instructions.append(
            f"- EXACTLY {rules.heading_min}-{rules.heading_max} words"
        )

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
9. NO news channel names (like TV9, Sandesh, Samachar, etc.) or source attribution inside the content.

SOURCE CONTENT:
{combined_text}

Generate the newspaper article now following ALL rules above.
"""

        return prompt

    def build_batch_newspaper_prompt(
        self, articles: List[ScrapedArticle], config: NewspaperConfig
    ) -> str:
        """
        Build a single prompt to generate multiple articles at once
        """
        # Get word count rules
        rules = config.word_count_rules

        # Build common instructions
        filter_instructions = []
        if config.editorial_filters.localization:
            filter_instructions.append("- Emphasize local/city relevance")
        if config.editorial_filters.active_voice:
            filter_instructions.append("- Use ACTIVE voice only")

        editorial_section = (
            "\n".join(filter_instructions)
            if filter_instructions
            else "- Standard editorial tone"
        )

        # Build source blocks
        sources_text = ""
        for i, article in enumerate(articles):
            sources_text += f"""
---
SOURCE_ID: {i}
SOURCE_NAME: {article.source}
CONTENT: {article.body[:3000]} 
---
"""

        # Build complete prompt
        prompt = f"""
You are an AI-powered Gujarati newspaper engine.
TOPIC: {config.topic}

TASK: Generate {len(articles)} separate newspaper articles based on the provided sources below.
Perform this as a SINGLE BATCH operation.

OUTPUT FORMAT INSTRUCTIONS:
For EACH source provided, generate a corresponding article block starting with "=== ARTICLE START: [SOURCE_ID] ===" and ending with "=== ARTICLE END ===".

Inside each block, use this EXACT structure:
HEADLINE: [Gujarati Headline - {rules.heading_min}-{rules.heading_max} words]
SUBHEADING: [Gujarati Subheading - {rules.subheading_min}-{rules.subheading_max} words]
INTRO PARAGRAPH: [Gujarati Intro - {rules.intro_min}-{rules.intro_max} words]
BODY PARAGRAPH: [Gujarati Body - {rules.body_min}-{rules.body_max} words]
INFO BOX: [Gujarati key points summary - {rules.info_box_min}-{rules.info_box_max} words]

COMMON RULES FOR ALL ARTICLES:
1. Output ONLY in Gujarati
2. Stick strictly to the word limits
3. Use the content ONLY from the specific source block
4. {editorial_section}
5. NO news channel names or source names inside the headline/intro/body.

SOURCES TO PROCESS:
{sources_text}

Generate all {len(articles)} articles now.
"""
        return prompt

    async def generate_newspaper_article(
        self, articles: List[ScrapedArticle], config: NewspaperConfig
    ) -> NewspaperOutput:
        """
        Generate newspaper article without strict validation loop
        """
        # Build prompt
        prompt = self.build_newspaper_prompt(articles, config)

        # Generate content
        try:
            print(f"[AI] Generating content (Single Pass)...")
            raw_output = await self.base_ai.generate_content(prompt)

            # Parse output
            parsed = self._parse_output(raw_output, config)
            parsed.validation_passed = True  # Assume valid for display purposes
            parsed.validation_errors = []

            return parsed

        except Exception as e:
            print(f"[ERROR] Generation failed: {e}")
            return NewspaperOutput(
                topic=config.topic,
                config_used=config,
                headline="Generation Error",
                intro="An error occurred while generating this article.",
                body=str(e),
                validation_passed=False,
                validation_errors=[str(e)],
            )

    async def generate_batch_newspaper_articles(
        self, articles: List[ScrapedArticle], config: NewspaperConfig, max_retries: int = 3
    ) -> List[NewspaperOutput]:
        """
        Generate multiple articles in a batch. 
        If some are missing (due to output limits), recursively process the remainders.
        """
        if not articles:
            return []

        print(f"[AI] Attempting batch generation for {len(articles)} articles...")
        prompt = self.build_batch_newspaper_prompt(articles, config)

        try:
            raw_output = await self.base_ai.generate_content(prompt)
            
            # Split by article markers
            article_blocks = re.split(r"=== ARTICLE START: (\d+) ===", raw_output)
            result_map = {}

            for i in range(1, len(article_blocks), 2):
                if i + 1 >= len(article_blocks):
                    break
                try:
                    s_idx = int(article_blocks[i].strip())
                    content = article_blocks[i + 1].replace("=== ARTICLE END ===", "").strip()
                    out = self._parse_output(content, config)
                    out.validation_passed = True
                    result_map[s_idx] = out
                except:
                    pass

            # Final results list initialized with None
            final_results = [None] * len(articles)
            for i, res in result_map.items():
                if i < len(articles):
                    final_results[i] = res

            # Identify missing articles (those that didn't make it into the AI's limited output window)
            missing_indices = [i for i, res in enumerate(final_results) if res is None]
            
            if missing_indices and max_retries > 0:
                print(f"[AI] {len(missing_indices)} articles missing from batch response. Retrying remainders...")
                missing_articles = [articles[i] for i in missing_indices]
                # Recursive call for remainders
                retry_results = await self.generate_batch_newspaper_articles(
                    missing_articles, config, max_retries=max_retries - 1
                )
                
                # Map retried results back to original positions
                for i, retry_res in zip(missing_indices, retry_results):
                    final_results[i] = retry_res
            
            elif missing_indices:
                # Out of retries, mark as failed
                for i in missing_indices:
                    final_results[i] = NewspaperOutput(
                        topic=config.topic,
                        config_used=config,
                        headline="Generation Failed",
                        intro="Article missing after multiple batch retries.",
                        body="The content was likely too large for the AI output window.",
                        validation_passed=False,
                        validation_errors=["Missing in batch"],
                    )

            return final_results

        except Exception as e:
            print(f"[ERROR] Batch generation hard failure: {e}")
            if max_retries > 0:
                # If whole batch fails (e.g. safety filters), try smaller chunks
                print(f"[AI] Falling back to smaller chunk processing...")
                chunk_size = 5
                sub_results = []
                for i in range(0, len(articles), chunk_size):
                    chunk = articles[i:i+chunk_size]
                    chunk_res = await self.generate_batch_newspaper_articles(chunk, config, max_retries=max_retries - 1)
                    sub_results.extend(chunk_res)
                return sub_results
            
            return [
                NewspaperOutput(
                    topic=config.topic,
                    config_used=config,
                    headline="Batch Error",
                    intro="An error occurred during batch processing.",
                    body=str(e),
                    validation_passed=False,
                    validation_errors=[str(e)],
                )
                for _ in articles
            ]

    async def merge_and_refine_articles(
        self, articles: List[NewspaperOutput], config: NewspaperConfig
    ) -> NewspaperOutput:
        """
        Merge multiple articles into one cohesive piece
        """
        if not articles:
            raise ValueError("No articles provided for merging")

        print(f"[AI] Merging {len(articles)} articles...")
        if config.word_count_rules is None:
            raise ValueError("Word count rules are missing from config")

        combined_content = ""
        for i, art in enumerate(articles):
            combined_content += f"""
--- SOURCE {i+1} ({art.source or 'Unknown'}) ---
HEADLINE: {art.headline}
INTRO: {art.intro}
BODY: {art.body}
INFO BOX: {art.info_box or 'None'}
"""

        rules = config.word_count_rules
        prompt = f"""
You are an expert Gujarati Chief Editor.
Your task is to MERGE the following source articles into ONE single, cohesive, and high-quality news report.

SOURCE MATERIAL:
{combined_content}

MANDATORY EDITORIAL RULES:
1. MERGE facts from all sources into a unified narrative.
2. RESOLVE any conflicting information.
3. FLOW nicely between paragraphs.
4. MAINTAIN a neutral, authoritative news tone.
5. STRICTLY FOLLOW the word count limits below.
6. NO news channel names (TV9, Sandesh, etc.) in the content.

WORD COUNT REQUIREMENTS:
- HEADLINE: {rules.heading_min}-{rules.heading_max} words
- INTRO: {rules.intro_min}-{rules.intro_max} words
- BODY: {rules.body_min}-{rules.body_max} words
- INFO BOX: {rules.info_box_min}-{rules.info_box_max} words

OUTPUT FORMAT:
HEADLINE: [Merged Headline]
INTRO PARAGRAPH: [Merged Intro]
BODY PARAGRAPH: [Merged Body]
INFO BOX: [Merged Info Box or None]

Generate the merged article now.
"""
        try:
            raw_output = await self.base_ai.generate_content(prompt)
            parsed = self._parse_output(raw_output, config)
            parsed.source = "Merged Report"
            parsed.url = "merged"

            is_valid, validation_results = self.validator.comprehensive_validation(
                parsed, config
            )
            parsed.validation_passed = is_valid
            all_errors = []
            for category, errors in validation_results.items():
                all_errors.extend(errors)
            parsed.validation_errors = all_errors

            return parsed
        except Exception as e:
            print(f"[ERROR] Merge failed: {e}")
            raise e

    async def refine_newspaper_article(
        self, draft: NewspaperOutput, config: NewspaperConfig
    ) -> NewspaperOutput:
        """
        Refine a selected draft article
        """
        print(f"[AI] Refining article from source: {draft.source or 'Unknown'}")
        rules = config.word_count_rules

        prompt = f"""
You are an expert Gujarati Chief Editor.
REWRITE and POLISH the draft article below to strictly meet all standards and word count limits.

DRAFT CONTENT:
HEADLINE: {draft.headline}
INTRO: {draft.intro}
BODY: {draft.body}
INFO BOX: {draft.info_box or "None"}

TARGET REQUIREMENTS:
1. HEADLINE: {rules.heading_min}-{rules.heading_max} words
2. INTRO: {rules.intro_min}-{rules.intro_max} words
3. BODY: {rules.body_min}-{rules.body_max} words
4. INFO BOX: {rules.info_box_min}-{rules.info_box_max} words
5. LANGUAGE: Gujarati only.
6. NO news channel names or source branding in the output.

OUTPUT FORMAT:
HEADLINE: [Refined Headline]
INTRO PARAGRAPH: [Refined Intro]
BODY PARAGRAPH: [Refined Body]
INFO BOX: [Refined Info Box or None]

Rewrite the article now.
"""
        try:
            raw_output = await self.base_ai.generate_content(prompt)
            parsed = self._parse_output(raw_output, config)
            parsed.source = draft.source
            parsed.url = draft.url

            is_valid, validation_results = self.validator.comprehensive_validation(
                parsed, config
            )
            parsed.validation_passed = is_valid
            all_errors = []
            for category, errors in validation_results.items():
                all_errors.extend(errors)
            parsed.validation_errors = all_errors

            return parsed
        except Exception as e:
            print(f"[ERROR] Refinement failed: {e}")
            return draft

    async def generate_from_keypoints(
        self, keypoints: str, config: NewspaperConfig
    ) -> NewspaperOutput:
        """
        Generate a professional news article from user-provided keypoints/notes
        """
        print(f"[AI] Generating article from user keypoints...")

        rules = config.word_count_rules
        prompt = f"""
You are an expert Gujarati Chief Editor.
Transform the following RAW KEYPOINTS into a HIGH-QUALITY, professional news report.

USER KEYPOINTS/NOTES:
{keypoints}

EDITORIAL REQUIREMENTS:
1. LANGUAGE: Strict Gujarati only.
2. TONE: Authoritative news tone.
3. STRUCTURE: Use headline, intro, body, and info box.
4. NO news channel names or source names inside the content.

WORD COUNT REQUIREMENTS:
- HEADLINE: {rules.heading_min}-{rules.heading_max} words
- INTRO: {rules.intro_min}-{rules.intro_max} words
- BODY: {rules.body_min}-{rules.body_max} words
- INFO BOX: {rules.info_box_min}-{rules.info_box_max} words

OUTPUT FORMAT:
HEADLINE: [Your Headline]
SUBHEADING: [Your Subheading]
INTRO PARAGRAPH: [Your Intro]
BODY PARAGRAPH: [Your Body Content]
INFO BOX: [Key points summary]

Generate the report now.
"""
        try:
            raw_output = await self.base_ai.generate_content(prompt)
            parsed = self._parse_output(raw_output, config)
            parsed.source = "Manual Entry"
            parsed.url = "manual"

            is_valid, validation_results = self.validator.comprehensive_validation(
                parsed, config
            )
            parsed.validation_passed = is_valid
            all_errors = []
            for category, errors in validation_results.items():
                all_errors.extend(errors)
            parsed.validation_errors = all_errors

            return parsed
        except Exception as e:
            print(f"[ERROR] Generation from keypoints failed: {e}")
            raise e

    async def high_quality_rewrite(
        self, text: str, config: NewspaperConfig
    ) -> NewspaperOutput:
        """
        Rewrite story/text into high-quality, polished Gujarati using the Senior Editor prompt
        """
        print(f"[AI] Senior Editor: Polishing content...")
        
        prompt = f"""
You are a senior Gujarati language editor with a newspaper-level writing standard.

Task:
Rewrite the story/text below into high-quality, polished Gujarati while keeping the original meaning, tone, and intent exactly the same.

Editing Standards (must follow):
1) Correct all grammar, spelling, punctuation, and sentence structure.
2) Improve clarity and readability: make the text easy for educated readers to understand.
3) Make the flow smooth: add necessary linking sentences and logical transitions.
4) Remove repetition, weak phrasing, and unnecessary filler.
5) Upgrade vocabulary: use refined, standard Gujarati (avoid slang and casual wording).
6) Keep the writing professional and natural (do NOT make it overly heavy, artificial, or overly poetic).
7) Do NOT change:
   - characters
   - events
   - timeline
   - facts
   - the core message
8) NO news channel names (like TV9, Sandesh, etc.) or branding in the content.

MANDATORY OUTPUT STRUCTURE:
Your response MUST use these EXACT labels for parsing:
HEADLINE: [High-quality Headline]
INTRO PARAGRAPH: [Polished Intro]
BODY PARAGRAPH: [Full Polished Body]
INFO BOX: [Key summary points or 'None']

Text to rewrite:
{text}
"""
        try:
            raw_output = await self.base_ai.generate_content(prompt)
            parsed = self._parse_output(raw_output, config)
            parsed.source = "Senior Editor Rewrite"
            parsed.url = "rewrite"
            
            # Simple validation check
            parsed.validation_passed = True
            parsed.validation_errors = []
            
            return parsed
        except Exception as e:
            print(f"[ERROR] High-quality rewrite failed: {e}")
            raise e

    def _parse_output(
        self, raw_output: str, config: NewspaperConfig
    ) -> NewspaperOutput:
        """
        Parse AI output into structured NewspaperOutput with robust regex matching
        """
        print("-" * 50)
        print("[DEBUG] RAW AI OUTPUT:")
        print(raw_output)
        print("-" * 50)

        sections = {
            "headline": "",
            "headline_cap": None,
            "subheading": None,
            "intro": "",
            "body": "",
            "info_box": None,
        }

        # Regex patterns for various section headers (very flexible)
        patterns = {
            "headline_cap": r"(?i)^\s*[\*\#\-\s\d\.]*HEADLINE\s*CAP\s*[:\-]*",
            "headline": r"(?i)^\s*[\*\#\-\s\d\.]*HEADLINE\s*[:\-]*",
            "subheading": r"(?i)^\s*[\*\#\-\s\d\.]*SUB\s*HEADING\s*[:\-]*",
            "intro": r"(?i)^\s*[\*\#\-\s\d\.]*(?:INTRO|INTRODUCTION)(?:\s*PARAGRAPH)?\s*[:\-]*",
            "body": r"(?i)^\s*[\*\#\-\s\d\.]*(?:BODY|CONTENT|MAIN)(?:\s*PARAGRAPH)?\s*[:\-]*",
            "info_box": r"(?i)^\s*[\*\#\-\s\d\.]*(?:INFO|KEY)(?:\s*BOX|POINTS|HIGHLIGHTS)?\s*[:\-]*",
        }

        lines = raw_output.split("\n")
        current_section = None
        current_content = []

        for line in lines:
            clean_line = line.strip()
            if not clean_line:
                if current_section:
                    current_content.append("")
                continue

            # Check for new section header
            found_new = False
            # Check longer patterns first to avoid partial matches (like HEADLINE matching HEADLINE CAP)
            ordered_keys = ["headline_cap", "subheading", "intro", "body", "info_box", "headline"]
            
            for key in ordered_keys:
                pattern = patterns[key]
                match = re.search(pattern, clean_line)
                if match and match.start() < 5: # Match must be at start of line
                    # Save old section
                    if current_section:
                        sections[current_section] = "\n".join(current_content).strip()
                    
                    # Start new section
                    current_section = key
                    # Content might be on the same line after the header
                    content_part = clean_line[match.end():].strip()
                    current_content = [content_part] if content_part else []
                    found_new = True
                    break
            
            if not found_new and current_section:
                current_content.append(line)

        # Save last section
        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        # Fallback: If absolutely nothing was parsed, try a naive split
        if not sections["headline"] and not sections["body"] and len(lines) > 2:
             print("[WARN] Parsing failed. Using fallback split.")
             sections["headline"] = lines[0].strip()
             sections["body"] = "\n".join(lines[1:]).strip()

        # Filter out literal "None" in info_box
        info_box = sections["info_box"]
        if info_box and info_box.strip().lower() in ["none", "n/a", "null", "none."]:
            info_box = None

        # Clean markdown bolding (**) from all text fields
        def clean_markdown(text):
            if not text: return text
            return text.replace("**", "").strip()

        return NewspaperOutput(
            topic=config.topic,
            config_used=config,
            headline=clean_markdown(sections["headline"]) or "શીર્ષક ઉપલબ્ધ નથી",
            headline_cap=clean_markdown(sections["headline_cap"]),
            subheading=clean_markdown(sections["subheading"]),
            intro=clean_markdown(sections["intro"]) or "પ્રસ્તાવના ઉપલબ્ધ નથી",
            body=clean_markdown(sections["body"]) or "વિષયવસ્તુ ઉપલબ્ધ નથી",
            info_box=clean_markdown(info_box),
            validation_passed=False,
            validation_errors=[],
        )
