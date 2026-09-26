from typing import List, Optional
from app.models.data import ScrapedArticle, NewspaperConfig, NewspaperOutput
from app.services.grid_calculator import GridCalculator
from app.services.headline_engineer import HeadlineEngineer
from app.services.newspaper_validator import NewspaperValidator
from app.services.ai_service import AIService
from app.services.ai_rules_loader import inject_system_prompt
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
HEADLINE CAP: [Gujarati Cap Heading - {rules.cap_heading_min}-{rules.cap_heading_max} words]
HEADLINE: [Gujarati Headline - {rules.heading_min}-{rules.heading_max} words] (CRITICAL: Write exactly between {rules.heading_min} and {rules.heading_max} words)
SUBHEADING: [Gujarati Subheading - {rules.subheading_min}-{rules.subheading_max} words] (CRITICAL: Write exactly between {rules.subheading_min} and {rules.subheading_max} words)
INTRO PARAGRAPH: [Gujarati Intro - {rules.intro_min}-{rules.intro_max} words] (CRITICAL: Because Gujarati words are tokenized differently, you ALWAYS under-generate. To actually reach {rules.intro_min} words, you MUST write at least {rules.intro_min * 6} characters. Expand your sentences professionally.)
BODY PARAGRAPH: [Gujarati Body - {rules.body_min}-{rules.body_max} words] (CRITICAL: You MUST write at least {rules.body_min * 6} characters to reach {rules.body_min} words. If you write less than {rules.body_min * 6} characters, you fail. Expand with relevant journalistic context. Keep standard paragraph formatting.)
INFO BOX: [Gujarati key points summary - {rules.info_box_min}-{rules.info_box_max} words]
ANKDA: [Gujarati statistics or numbers summary]

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
        # Inject the full SANDESH editorial framework as system context
        return inject_system_prompt(prompt)

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

        task_prompt = f"""
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

WORD COUNT REQUIREMENTS (CRITICAL - YOU MUST MEET THESE EXACT TARGETS BASED ON LAYOUT CONFIGURATION):
- HEADLINE CAP: {rules.cap_heading_min}-{rules.cap_heading_max} words
- HEADLINE: {rules.heading_min}-{rules.heading_max} words (CRITICAL: Write exactly between {rules.heading_min} and {rules.heading_max} words)
- SUBHEADING: {rules.subheading_min}-{rules.subheading_max} words (CRITICAL: Write exactly between {rules.subheading_min} and {rules.subheading_max} words)
- INTRO: {rules.intro_min}-{rules.intro_max} words (CRITICAL: Because of Gujarati tokenization, you MUST write at least {max(3, rules.intro_min // 12)} to {max(4, rules.intro_max // 10)} long and detailed sentences to physically reach this word count. Expand professionally.)
- BODY: {rules.body_min}-{rules.body_max} words (CRITICAL: You MUST write at least {max(5, rules.body_min // 12)} to {max(8, rules.body_max // 10)} detailed sentences to physically reach this word count. Structure the body into EXACTLY 2 or 3 large, cohesive paragraphs. DO NOT write tiny or single-sentence paragraphs.)
- INFO BOX: {rules.info_box_min}-{rules.info_box_max} words
- ANKDA: Key numbers/statistics (optional)

OUTPUT FORMAT:
HEADLINE CAP: [Merged Cap Heading]
HEADLINE: [Merged Headline]
SUBHEADING: [Merged Subheading]
INTRO PARAGRAPH: [Merged Intro]
BODY PARAGRAPH: [Merged Body]
INFO BOX: [Merged Info Box or None]
ANKDA: [Merged Ankda stats or None]

Generate the merged article now.
"""
        prompt = inject_system_prompt(task_prompt)
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

        task_prompt = f"""
You are an expert Gujarati Chief Editor.
REWRITE and POLISH the draft article below to strictly meet all standards and word count limits.

DRAFT CONTENT:
HEADLINE: {draft.headline}
INTRO: {draft.intro}
BODY: {draft.body}
INFO BOX: {draft.info_box or "None"}

TARGET REQUIREMENTS (CRITICAL - LAYOUT CONFIGURATION EXACT MATCH):
1. HEADLINE CAP: {rules.cap_heading_min}-{rules.cap_heading_max} words
2. HEADLINE: {rules.heading_min}-{rules.heading_max} words (CRITICAL: Write exactly between {rules.heading_min} and {rules.heading_max} words)
3. SUBHEADING: {rules.subheading_min}-{rules.subheading_max} words (CRITICAL: Write exactly between {rules.subheading_min} and {rules.subheading_max} words)
4. INTRO: {rules.intro_min}-{rules.intro_max} words (CRITICAL: Because of Gujarati tokenization, you MUST write at least {max(3, rules.intro_min // 12)} to {max(4, rules.intro_max // 10)} long and detailed sentences to physically reach this word count. Expand professionally.)
5. BODY: {rules.body_min}-{rules.body_max} words (CRITICAL: You MUST write at least {max(5, rules.body_min // 12)} to {max(8, rules.body_max // 10)} detailed sentences to physically reach this word count. Structure the body into EXACTLY 2 or 3 large, cohesive paragraphs. DO NOT write tiny or single-sentence paragraphs.)
6. INFO BOX: {rules.info_box_min}-{rules.info_box_max} words
7. LANGUAGE: Gujarati only.
8. NO news channel names or source branding in the output.

OUTPUT FORMAT:
HEADLINE CAP: [Refined Cap Heading]
HEADLINE: [Refined Headline]
SUBHEADING: [Refined Subheading]
INTRO PARAGRAPH: [Refined Intro]
BODY PARAGRAPH: [Refined Body]
INFO BOX: [Refined Info Box or None]
ANKDA: [Refined Ankda stats or None]

Rewrite the article now.
"""
        prompt = inject_system_prompt(task_prompt)
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

        task_prompt = f"""
You are an expert Gujarati Chief Editor.
Transform the following RAW KEYPOINTS into a HIGH-QUALITY, professional news report.

USER KEYPOINTS/NOTES:
{keypoints}

⚠️ STRICT FACT DISCIPLINE — THIS IS MANDATORY:
- Use ONLY the facts, names, numbers, dates, and events present in the KEYPOINTS above.
- Do NOT invent, assume, or add ANY information that is not explicitly stated in the keypoints.
- Do NOT add quotes, statistics, background stories, or context that is not in the keypoints.
- If a detail is missing (e.g. exact time, name), leave it out — do NOT guess or fill in.
- Your job is to WRITE, not to RESEARCH or INVENT.

5. LANGUAGE: Strict Gujarati only.
6. TONE: Authoritative news tone.
7. WRITING STYLE: Transform the bullet points into a professional, COHESIVE narrative. Do NOT just list the points.
8. FACTUAL RESTRAINT vs EXPANSION: Do NOT add false claims or fake quotes. HOWEVER, you MUST meet the WORD COUNT TARGETS. If the input is short but the WORD COUNT target is high, you MUST professionally expand the narrative. Add relevant journalistic context, explore the significance of the facts provided, elaborate on the broader implications, and ensure the article is comprehensive enough to hit the EXACT WORD COUNT TARGETS.
9. STRUCTURE: Use all labeled sections below.
10. NO news channel names or source names inside the content.

CRITICAL WORD COUNT REQUIREMENTS (EXACT LAYOUT CONFIGURATION MATCH):
- HEADLINE CAP: {rules.cap_heading_min}-{rules.cap_heading_max} words
- HEADLINE: {rules.heading_min}-{rules.heading_max} words (CRITICAL: Write exactly between {rules.heading_min} and {rules.heading_max} words)
- SUBHEADING: {rules.subheading_min}-{rules.subheading_max} words (CRITICAL: Write exactly between {rules.subheading_min} and {rules.subheading_max} words)
- INTRO: {rules.intro_min}-{rules.intro_max} words (CRITICAL: Because of Gujarati tokenization, you MUST write at least {max(3, rules.intro_min // 12)} to {max(4, rules.intro_max // 10)} long and detailed sentences to physically reach this word count. Expand professionally.)
- BODY: {rules.body_min}-{rules.body_max} words (CRITICAL: You MUST write at least {max(5, rules.body_min // 12)} to {max(8, rules.body_max // 10)} detailed sentences to physically reach this word count. Structure the body into EXACTLY 2 or 3 large, cohesive paragraphs. DO NOT write tiny or single-sentence paragraphs. EXCEPTION: You MAY include HTML tables or bullet lists here if the input data contains a table or list. Use proper HTML tags like <table class="w-full border-collapse border border-gray-300 my-4 text-sm"><thead class="bg-gray-100">...</thead><tbody>...</tbody></table> and NEVER collapse the table into a single line.)
- INFO BOX: {rules.info_box_min}-{rules.info_box_max} words (You MAY include HTML tables here if appropriate, using standard HTML table tags like <table class="w-full border-collapse border border-gray-300 my-2 text-sm">...</table>)
- ANKDA: Key numbers/statistics (optional)

CRITICAL OUTPUT RULES:
- Every section label MUST start on its own NEW LINE.
- HEADLINE line must contain ONLY the headline — nothing else on that line.
- ALTERNATIVE HEADLINES must be on separate lines AFTER the HEADLINE line.
- Do NOT write "3 alternative headlines:" or any number inline after the HEADLINE.
- Do NOT merge multiple sections on one line.

        OUTPUT FORMAT — copy this structure EXACTLY, each label on its own line. Keep the labels in ENGLISH as shown:
HEADLINE CAP: [Gujarati Cap Heading]
HEADLINE: [Best Gujarati Headline only]
ALTERNATIVE HEADLINES:
1. [Alt Headline 1]
2. [Alt Headline 2]
3. [Alt Headline 3]
SUBHEADING: [Gujarati Subheading]
INTRO PARAGRAPH: [Gujarati Intro]
BODY PARAGRAPH: [Gujarati Body Content — only facts from the keypoints]
INFO BOX: [Key points summary in Gujarati]
ANKDA: [Gujarati statistics or numbers summary]
EDITORIAL NOTES: [Note any missing facts]

Generate the complete report now.
"""
        prompt = inject_system_prompt(task_prompt)
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
        self, text: str, config: NewspaperConfig, instruction: Optional[str] = None
    ) -> NewspaperOutput:
        """
        Rewrite story/text into high-quality, polished Gujarati using the Senior Editor prompt
        """
        print(f"[AI] Senior Editor: Polishing content...")
        
        # Ensure word count rules exist
        if config.word_count_rules is None:
            config.word_count_rules = self.grid_calc.get_word_count_rules(
                config.slot_config.column_span,
                config.slot_config.slot_count,
                not config.headline_config.single_line,
            )

        rules = config.word_count_rules
        cap_heading_min = rules.cap_heading_min or 3
        cap_heading_max = rules.cap_heading_max or 10
        heading_min = rules.heading_min or 5
        heading_max = rules.heading_max or 15
        subheading_min = rules.subheading_min or 5
        subheading_max = rules.subheading_max or 25
        intro_min = rules.intro_min or 30
        intro_max = rules.intro_max or 95
        body_min = rules.body_min or 100
        body_max = rules.body_max or 350
        info_box_min = rules.info_box_min or 20
        info_box_max = rules.info_box_max or 60

        # Clean up input text to prevent the AI from repeating "None" or blank values
        cleaned_text = text
        cleaned_text = re.sub(r"(?i)INFO\s*BOX\s*[:\-]*\s*(?:None|none|null|nil|\-)?\s*(?=\n|$)", "INFO BOX: [Generate a fresh professional key points summary here]", cleaned_text)
        cleaned_text = re.sub(r"(?i)SUBHEADING\s*[:\-]*\s*(?:None|none|null|nil|\-)?\s*(?=\n|$)", "SUBHEADING: [Generate an engaging professional subheading here]", cleaned_text)
        
        if "INFO BOX:" not in cleaned_text:
            cleaned_text = cleaned_text.strip() + "\nINFO BOX: [Generate a fresh professional key points summary here]"
        if "SUBHEADING:" not in cleaned_text:
            if "HEADLINE:" in cleaned_text:
                cleaned_text = re.sub(r"(HEADLINE:[^\n]*\n)", r"\1SUBHEADING: [Generate an engaging professional subheading here]\n", cleaned_text, count=1)
            else:
                cleaned_text = "SUBHEADING: [Generate an engaging professional subheading here]\n" + cleaned_text

        user_instruction_block = ""
        if instruction:
            user_instruction_block = (
                f"\n\n⚠️ USER'S CUSTOM INSTRUCTION & NEW DATA:\n"
                f"{instruction}\n"
                f"(You MUST apply this custom instruction to the generated output, keeping the response in Gujarati. "
                f"If the instruction contains new raw data, lists, or tables, intelligently incorporate them into the article. "
                f"CRITICAL: If the user explicitly asks to put the data in the 'content' or 'body' (or below in the content), you MUST place it in the BODY PARAGRAPH. Otherwise, use the INFO BOX or BODY PARAGRAPH as appropriate. When generating tables, ALWAYS use proper HTML table tags (e.g., <table class=\"w-full border-collapse border border-gray-300 my-4 text-sm text-left\"><thead class=\"bg-gray-100\"><tr><th class=\"border px-2 py-1\">...</th></tr></thead><tbody><tr><td class=\"border px-2 py-1\">...</td></tr></tbody></table>). Do NOT use Markdown tables. Do NOT collapse the HTML table into a single line.)\n\n"
            )



        task_prompt = f"""
{user_instruction_block}

⚠️ CRITICAL WORD LIMITS (EXACT LAYOUT CONFIGURATION MATCH):
- CAP HEADING: {cap_heading_min}-{cap_heading_max} words
- HEADLINE: {heading_min}-{heading_max} words (CRITICAL: Write exactly between {heading_min} and {heading_max} words)
- SUBHEADING: {subheading_min}-{subheading_max} words (CRITICAL: Write exactly between {subheading_min} and {subheading_max} words)
- INTRO PARAGRAPH: {intro_min}-{intro_max} words (CRITICAL: Because of Gujarati tokenization, you MUST write at least {max(3, intro_min // 12)} to {max(4, intro_max // 10)} long and detailed sentences to physically reach this word count. Expand professionally.)
- BODY PARAGRAPH: {body_min}-{body_max} words (CRITICAL: You MUST write at least {max(5, body_min // 12)} to {max(8, body_max // 10)} detailed sentences to physically reach this word count. Structure the body into EXACTLY 2 or 3 large, cohesive paragraphs. DO NOT write tiny or single-sentence paragraphs. EXCEPTION: You MAY include HTML tables or bullet lists here if requested or if the input contains raw table data. Always use HTML <table> tags with Tailwind classes like class="w-full border-collapse border border-gray-300 my-4 text-sm", and NEVER collapse them into a single line of text.)

OUTPUT FORMAT:
You MUST follow the exact format below, with each label starting on its own new line. Keep the labels in ENGLISH. Do not add any markdown around labels, just write them as shown:

HEADLINE CAP: [ટોપી હેડિંગ]
HEADLINE: [મુખ્ય હેડિંગ]
ALTERNATIVE HEADLINES:
1. [Option 1]
2. [Option 2]
3. [Option 3]
SUBHEADING: [પેટા હેડિંગ]
INTRO PARAGRAPH: [ડેટલાઇન (દા.ત. અમદાવાદ:) અને ઇન્ટ્રો સળંગ ફકરામાં]
BODY PARAGRAPH: [બોડી સળંગ ફકરામાં]
INFO BOX:
- [બોક્સ મેટર — જો મૂળમાં હોય તો. અહી તમે HTML table પણ વાપરી શકો છો: <table class="w-full border-collapse border border-gray-300 my-2 text-sm">...</table>]
---
EDITORIAL NOTES: [ડેસ્ક નોંધ — પ્રકાશન માટે નહીં. ખરેખર કરેલા સુધારાની ટૂંકી વિગત]

INPUT DRAFT TO AUDIT, POLISH & CORRECT:
{cleaned_text}
"""
        prompt = inject_system_prompt(task_prompt)
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
        sections = {
            "headline": "",
            "headline_cap": None,
            "alternative_headlines": None,
            "subheading": None,
            "intro": "",
            "body": "",
            "info_box": None,
            "ankda": None,
            "editorial_notes": None,
        }

        # Regex patterns for various section headers (very flexible)
        patterns = {
            "headline_cap":          r"(?i)^\s*[\*\#\-\s\d\.]*HEADLINE\s*CAP\s*[:\-]*",
            "alternative_headlines": r"(?i)^\s*[\*\#\-\s\d\.]*ALT(?:ERNATIVE)?\s*HEADLINES?\s*[:\-]*",
            "editorial_notes":       r"(?i)^\s*[\*\#\-\s\d\.]*EDITORIAL\s*NOTES?\s*[:\-]*",
            "headline":              r"(?i)^\s*[\*\#\-\s\d\.]*(?:HEADLINE|HEADING|TOPIC|હેડલાઇન|શીર્ષક|મુખ્ય સમાચાર)\s*[:\-]*",
            "subheading":            r"(?i)^\s*[\*\#\-\s\d\.]*(?:SUB\s*HEADING|SUBTITLE|સબહેડલાઇન|સબ-હેડલાઇન|ગૌણ શીર્ષક)\s*[:\-]*",
            "intro":                 r"(?i)^\s*[\*\#\-\s\d\.]*(?:INTRO|INTRODUCTION|LEAD|ઇન્ટ્રો|પ્રસ્તાવના|શરૂઆત)(?:\s*(?:PARAGRAPH|પેરેગ્રાફ))?\s*[:\-]*",
            "body":                  r"(?i)^\s*[\*\#\-\s\d\.]*(?:BODY|CONTENT|MAIN|STORY|ARTICLE|બોડી|વિષયવસ્તુ|મુખ્ય લખાણ)(?:\s*(?:PARAGRAPH|પેરેગ્રાફ))?\s*[:\-]*",
            "info_box":              r"(?i)^\s*[\*\#\-\s\d\.]*(?:INFO|KEY|SUMMARY|HIGHLIGHTS|ઇન્ફો|મુખ્ય મુદ્દા)(?:\s*(?:BOX|POINTS|HIGHLIGHTS|બોક્સ))?\s*[:\-]*",
            "ankda":                 r"(?i)^\s*[\*\#\-\s\d\.]*(?:ANKDA|STATS|STATISTICS|આંકડા|આંકડાકીય માહિતી)\s*[:\-]*",
        }

        lines = raw_output.split("\n")
        current_section = None
        current_content = []

        # Order matters: check longer/more-specific patterns before shorter ones
        ordered_keys = [
            "headline_cap", "alternative_headlines", "editorial_notes",
            "subheading", "intro", "body", "info_box", "ankda", "headline"
        ]

        for line in lines:
            clean_line = line.strip()
            if not clean_line:
                if current_section:
                    current_content.append("")
                continue

            # Check for new section header
            found_new = False
            # Ensure we don't treat list items/bullet points as section headers
            is_list_item = re.match(r"^\s*(?:[\-\*•]|\d+[\.\)\-])\s+", clean_line)
            
            if current_section != "editorial_notes" and not is_list_item:
                for key in ordered_keys:
                    pattern = patterns[key]
                    match = re.search(pattern, clean_line)
                    if match and match.start() < 10:  # Allow some minor indentation
                        # Save old section
                        if current_section:
                            sections[current_section] = "\n".join(current_content).strip()

                        # Start new section
                        current_section = key
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
        if not sections["headline"] and not sections["body"] and len(lines) >= 1:
            sections["headline"] = lines[0].strip()
            if len(lines) > 1:
                sections["body"] = "\n".join(lines[1:]).strip()
            else:
                sections["body"] = "વિષયવસ્તુ ઉપલબ્ધ નથી"

        # ── Clean markdown bolding (**) from all text fields ──────────────────
        def clean_markdown(text):
            if not text:
                return text
            # Remove bolding, headers, etc.
            text = re.sub(r"[\*\#\_]+", "", text).strip()
            return text

        # ── RESCUE: Missing intro fallback from body ─────────────────────────
        intro = clean_markdown(sections["intro"])
        body = clean_markdown(sections["body"])
        subheading = clean_markdown(sections["subheading"])

        # If intro is missing but body exists, try to extract it
        if (not intro or intro == "પ્રસ્તાવના ઉપલબ્ધ નથી") and body and body != "વિષયવસ્તુ ઉપલબ્ધ નથી":
            # Look for buried labels in body
            buried_sub = re.search(r"(?i)(?:SUB\s*HEADING|સબહેડલાઇન|સબ-હેડલાઇન)\s*[:\-]*\s*(.+?)(?=\n|$)", body)
            buried_intro = re.search(r"(?i)(?:INTRO|INTRODUCTION|ઇન્ટ્રો|પ્રસ્તાવના)(?:\s*(?:PARAGRAPH|પેરેગ્રાફ))?\s*[:\-]*\s*(.+?)(?=\n|$)", body)
            
            if buried_sub and not subheading:
                subheading = buried_sub.group(1).strip()
                body = body.replace(buried_sub.group(0), "").strip()
            
            if buried_intro:
                intro = buried_intro.group(1).strip()
                body = body.replace(buried_intro.group(0), "").strip()
            
            # Final fallback: take the first part of body
            if not intro or intro == "પ્રસ્તાવના ઉપલબ્ધ નથી":
                paragraphs = [p.strip() for p in body.split("\n") if p.strip()]
                if paragraphs:
                    intro = paragraphs[0]
                    if len(intro) > 300:
                        sentences = re.split(r"(?<=[।\.!\?])\s+", intro)
                        intro = " ".join(sentences[:2])
                    if intro in paragraphs[0]:
                        body = "\n\n".join(paragraphs[1:]) if len(paragraphs) > 1 else body

        # Post-process alternative headlines
        alt_headlines = None
        raw_alts = sections.get("alternative_headlines", "")
        if raw_alts:
            alts = re.findall(r"(?:^|\n)\s*\d+[.)\-]\s*(.+)", raw_alts)
            alt_headlines = [a.strip() for a in alts if a.strip()] if alts else [l.strip() for l in raw_alts.split("\n") if l.strip()]

        info_box_val = clean_markdown(sections.get("info_box"))
        if info_box_val and info_box_val.strip().lower() in ["none", ""]:
            info_box_val = None

        return NewspaperOutput(
            topic=config.topic,
            config_used=config,
            headline=clean_markdown(sections["headline"]) or "શીર્ષક ઉપલબ્ધ નથી",
            headline_cap=clean_markdown(sections["headline_cap"]),
            alternative_headlines=alt_headlines,
            subheading=subheading,
            intro=intro or "પ્રસ્તાવના ઉપલબ્ધ નથી",
            body=body or "વિષયવસ્તુ ઉપલબ્ધ નથી",
            info_box=info_box_val,
            ankda=clean_markdown(sections.get("ankda")),
            editorial_notes=clean_markdown(sections.get("editorial_notes")),
            validation_passed=False,
            validation_errors=[],
        )
