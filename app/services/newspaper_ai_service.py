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

        Args:
            articles: Scraped articles to synthesize
            config: Newspaper configuration with all rules

        Returns:
            Structured prompt for AI
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
INTRO PARAGRAPH: [Gujarati Intro - {rules.intro_min}-{rules.intro_max} words]
BODY PARAGRAPH: [Gujarati Body - {rules.body_min}-{rules.body_max} words]

COMMON RULES FOR ALL ARTICLES:
1. Output ONLY in Gujarati
2. Stick strictly to the word limits
3. Use the content ONLY from the specific source block
4. {editorial_section}

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

        Args:
            articles: Scraped articles
            config: Newspaper configuration

        Returns:
            NewspaperOutput with generated content
        """
        # Build prompt
        prompt = self.build_newspaper_prompt(articles, config)

        # Generate content
        # We only do one pass now since we want to show the user the content
        # regardless of validation status
        try:
            print(f"📰 Generating content (Single Pass)...")
            raw_output = await self.base_ai.generate_content(prompt)

            # Parse output
            parsed = self._parse_output(raw_output, config)

            # We explicitly skip validation here as requested
            # User wants to see the content first, then select/validate later
            parsed.validation_passed = True  # Assume valid for display purposes
            parsed.validation_errors = []

            return parsed

        except Exception as e:
            print(f"❌ Generation failed: {e}")
            # Return empty/error structure
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
        self, articles: List[ScrapedArticle], config: NewspaperConfig
    ) -> List[NewspaperOutput]:
        """
        Generate multiple articles in a single AI call to save quota
        """
        if not articles:
            return []

        print(f"📰 Generating batch of {len(articles)} articles in ONE call...")

        # Build batch prompt
        prompt = self.build_batch_newspaper_prompt(articles, config)

        try:
            # Single AI Call
            raw_output = await self.base_ai.generate_content(prompt)

            # Parse the batch response
            results = []

            # Split by article markers
            # Regex to find blocks like === ARTICLE START: 0 === ...content... === ARTICLE END ===
            # The pattern needs to be robust
            article_blocks = re.split(r"=== ARTICLE START: (\d+) ===", raw_output)

            # The split result will be [preamble, id1, content1, id2, content2, ...]
            # We skip index 0 (preamble)

            processed_indices = set()

            for i in range(1, len(article_blocks), 2):
                if i + 1 >= len(article_blocks):
                    break

                source_idx_str = article_blocks[i].strip()
                content = article_blocks[i + 1]

                # clean validation markers from content if present
                content = content.replace("=== ARTICLE END ===", "").strip()

                try:
                    idx = int(source_idx_str)
                    if idx < len(articles):
                        # Parse individual article structure
                        parsed_output = self._parse_output(content, config)
                        processed_indices.add(idx)
                        results.append(parsed_output)
                except ValueError:
                    continue

            # Fill in failures for any missing indices
            for i in range(len(articles)):
                if i not in processed_indices:
                    print(f"⚠️ Failed to parse article for source {i}")
                    # Return error object
                    results.append(
                        NewspaperOutput(
                            topic=config.topic,
                            config_used=config,
                            headline="Generation Error",
                            intro="Could not parse generation result.",
                            body="",
                            validation_passed=False,
                            validation_errors=["Parsing failed"],
                        )
                    )

            # Reorder results to match input order
            # The loop above might result in out-of-order if regex match order varies,
            # but usually it's sequential. We'll map them carefully if needed,
            # but simple append is risky if IDs are skipped.
            # Let's map by ID to be safe

            final_ordered_results = []
            result_map = {}  # map idx -> output

            # Re-process cleanly
            for i in range(1, len(article_blocks), 2):
                if i + 1 >= len(article_blocks):
                    break
                try:
                    s_idx = int(article_blocks[i].strip())
                    content = (
                        article_blocks[i + 1].replace("=== ARTICLE END ===", "").strip()
                    )
                    result_map[s_idx] = self._parse_output(content, config)
                except:
                    pass

            for i in range(len(articles)):
                if i in result_map:
                    output = result_map[i]
                else:
                    output = NewspaperOutput(
                        topic=config.topic,
                        config_used=config,
                        headline="Generation Failed",
                        intro="Article missing from batch response.",
                        body="",
                        validation_passed=False,
                        validation_errors=["Missing in batch"],
                    )
                final_ordered_results.append(output)

            return final_ordered_results

        except Exception as e:
            print(f"❌ Batch generation failed: {e}")
            # Return all errors
            return [
                NewspaperOutput(
                    topic=config.topic,
                    config_used=config,
                    headline="Batch Generation Error",
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
        Merge multiple articles into one cohesive piece following strict rules
        """
        if not articles:
            raise ValueError("No articles provided for merging")

        print(f"✨ Merging {len(articles)} articles...")
        print(f"📝 Config Rules: {config.word_count_rules}")

        if config.word_count_rules is None:
            raise ValueError("Word count rules are missing from config")

        # Aggregate content
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

        # Build prompt
        prompt = f"""
You are an expert Gujarati Chief Editor.
Your task is to MERGE the following source articles into ONE single, cohesive, and high-quality news report.

SOURCE MATERIAL:
{combined_content}

MANDATORY EDITORIAL RULES:
1. MERGE facts from all sources into a unified narrative.
2. RESOLVE any conflicting information (prioritize specific details over general ones).
3. FLOW nicely between paragraphs (use transition words).
4. MAINTAIN a neutral, authoritative news tone.
5. STRICTLY FOLLOW the word count limits below.

WORD COUNT REQUIREMENTS (STRICT):
- HEADLINE: {rules.heading_min}-{rules.heading_max} words. Punchy, active voice.
- INTRO: {rules.intro_min}-{rules.intro_max} words. Summarize the key event.
- BODY: {rules.body_min}-{rules.body_max} words. detailed reporting.
- INFO BOX: {rules.info_box_min}-{rules.info_box_max} words (if applicable).

OUTPUT FORMAT (STRICT):
HEADLINE: [Merged Headline]
INTRO PARAGRAPH: [Merged Intro]
BODY PARAGRAPH: [Merged Body]
INFO BOX: [Merged Info Box or None]

Generate the merged article now.
"""

        try:
            # Generate content
            raw_output = await self.base_ai.generate_content(prompt)

            # Parse output
            parsed = self._parse_output(raw_output, config)

            # Set metadata
            parsed.source = "Merged Report"
            parsed.url = "merged"

            # Validate
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
            print(f"❌ Merge failed: {e}")
            raise e

    async def refine_newspaper_article(
        self, draft: NewspaperOutput, config: NewspaperConfig
    ) -> NewspaperOutput:
        """
        Refine a selected draft article to strictly meet requirements
        """
        print(f"✨ Refining article from source: {draft.source or 'Unknown'}")

        rules = config.word_count_rules

        # Build prompt
        prompt = f"""
You are an expert Gujarati Chief Editor.
Your task is to REWRITE and POLISH the draft article below to strictly meet all editorial standards and word count limits.

DRAFT CONTENT:
HEADLINE: {draft.headline}
INTRO: {draft.intro}
BODY: {draft.body}
INFO BOX: {draft.info_box or "None"}

TARGET REQUIREMENTS (STRICT):
1. HEADLINE: {rules.heading_min}-{rules.heading_max} words. Punchy, active voice.
2. INTRO: {rules.intro_min}-{rules.intro_max} words. Summarize the key event.
3. BODY: {rules.body_min}-{rules.body_max} words. Fact-based, neutral tone.
4. INFO BOX: {rules.info_box_min}-{rules.info_box_max} words (if applicable).
5. LANGUAGE: Gujarati only.
6. FORMAT: Return strictly structured sections.

OUTPUT FORMAT:
HEADLINE: [Refined Headline]
INTRO PARAGRAPH: [Refined Intro]
BODY PARAGRAPH: [Refined Body]
INFO BOX: [Refined Info Box or None]

Rewrite the article now.
"""

        try:
            # Generate content
            raw_output = await self.base_ai.generate_content(prompt)

            # Parse output
            parsed = self._parse_output(raw_output, config)

            # Keep metadata
            parsed.source = draft.source
            parsed.url = draft.url

            # Validate (we can be strict here if desired, or lenient)
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
            print(f"❌ Refinement failed: {e}")
            return draft  # Return original if refinement fails

    def _parse_output(
        self, raw_output: str, config: NewspaperConfig
    ) -> NewspaperOutput:
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
            "info_box": None,
        }

        # Split by section labels
        lines = raw_output.split("\n")
        current_section = None
        current_content = []

        for line in lines:
            clean_line = line.strip()
            line_upper = clean_line.upper()

            # Check Headers - Order matters (Longer matches first)
            matched_header = None
            new_section = None

            if line_upper.startswith("HEADLINE CAP:"):
                matched_header = "HEADLINE CAP:"
                new_section = "headline_cap"
            elif line_upper.startswith("HEADLINE:"):
                matched_header = "HEADLINE:"
                new_section = "headline"
            elif line_upper.startswith("SUB HEADING:") or line_upper.startswith(
                "SUBHEADING:"
            ):
                matched_header = (
                    "SUB HEADING:"
                    if line_upper.startswith("SUB HEADING:")
                    else "SUBHEADING:"
                )
                new_section = "subheading"
            elif line_upper.startswith("INTRO PARAGRAPH:") or line_upper.startswith(
                "INTRO:"
            ):
                matched_header = (
                    "INTRO PARAGRAPH:"
                    if line_upper.startswith("INTRO PARAGRAPH:")
                    else "INTRO:"
                )
                new_section = "intro"
            elif (
                line_upper.startswith("BODY PARAGRAPH:")
                or line_upper.startswith("BODY:")
                or line_upper.startswith("CONTENT:")
            ):
                if line_upper.startswith("BODY PARAGRAPH:"):
                    matched_header = "BODY PARAGRAPH:"
                elif line_upper.startswith("BODY:"):
                    matched_header = "BODY:"
                else:
                    matched_header = "CONTENT:"
                new_section = "body"
            elif line_upper.startswith("INFO BOX:") or line_upper.startswith(
                "INFOBOX:"
            ):
                matched_header = (
                    "INFO BOX:" if line_upper.startswith("INFO BOX:") else "INFOBOX:"
                )
                new_section = "info_box"

            if new_section:
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = new_section
                # Extract content after header
                # We use len(matched_header) which corresponds to the upper case version
                content_part = clean_line[len(matched_header) :].strip()
                current_content = [content_part] if content_part else []
            elif current_section and line.strip():
                current_content.append(line)

        # Save last section
        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

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
            validation_errors=[],
        )
