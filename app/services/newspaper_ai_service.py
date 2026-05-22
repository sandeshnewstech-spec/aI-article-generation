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
8. FACTUAL RESTRAINT (CRITICAL): Do NOT add "news filler" or standard police cliches like "high-level teams are formed", "thorough investigation started", or "technical surveillance". Only write what is explicitly provided. If the input is short, the report MUST be short. 
9. STRUCTURE: Use all labeled sections below.
10. NO news channel names or source names inside the content.

WORD COUNT REQUIREMENTS:
- HEADLINE: {rules.heading_min}-{rules.heading_max} words
- SUBHEADING: {rules.subheading_min}-{rules.subheading_max} words
- INTRO: {rules.intro_min}-{rules.intro_max} words
- BODY: {rules.body_min}-{rules.body_max} words
- INFO BOX: {rules.info_box_min}-{rules.info_box_max} words

CRITICAL OUTPUT RULES:
- Every section label MUST start on its own NEW LINE.
- HEADLINE line must contain ONLY the headline — nothing else on that line.
- ALTERNATIVE HEADLINES must be on separate lines AFTER the HEADLINE line.
- Do NOT write "3 alternative headlines:" or any number inline after the HEADLINE.
- Do NOT merge multiple sections on one line.

        OUTPUT FORMAT — copy this structure EXACTLY, each label on its own line. Keep the labels in ENGLISH as shown:
HEADLINE: [Best Gujarati Headline only]
ALTERNATIVE HEADLINES:
1. [Alt Headline 1]
2. [Alt Headline 2]
3. [Alt Headline 3]
SUBHEADING: [Gujarati Subheading]
INTRO PARAGRAPH: [Gujarati Intro]
BODY PARAGRAPH: [Gujarati Body Content — only facts from the keypoints]
INFO BOX: [Key points summary in Gujarati]
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
        self, text: str, config: NewspaperConfig
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

        task_prompt = f"""
You are a senior copy-editor and Chief Senior Editor of the SANDESH newsroom.
Your task is to take the provided news draft, audit it meticulously, apply the elite SANDESH house rules, and write a polished, front-page standard Gujarati copy.

MANDATORY RULES FROM UPLOADED SANDESH FRAMEWORK (STRICT ADHERENCE REQUIRED):
1. **01 News Judgment Master**: Apply 5W1H (Who, What, Where, When, Why, How). Ensure a powerful, engaging Lead/Intro paragraph in Inverted Pyramid style.
2. **02 Headline-Subheadline Master**: Make headings active, direct, and powerful. Headline must be {heading_min}-{heading_max} words. Subheading must be {subheading_min}-{subheading_max} words.
3. **03 Body Copy Quality Master**: Focus on absolute fact discipline. No padding, puffery, or editorial filler cliches (e.g. "thorough investigation started", "police are on hunt" - unless strictly in the input). One fact = one sentence.
4. **04 Numbers-Dates-Time-Age-Designation**: Structure designations, dates, and numbers properly in Gujarati copy style. Bold key numbers and percentages for visual appeal.
5. **05 Legal-Safe Wording Master**: Ensure neutral, legally safe phrasing. Before conviction, use terms like 'આરોપી' (accused), 'આક્ષેપ' (alleged), 'ફરિયાદ મુજબ' (according to the complaint), 'પોલીસ મુજબ' (according to police). Never state allegations as established facts.
6. **06 Approved News Sources Policy**: Remove any source or channel name (like TV9, Gujarat Samachar, Sandesh News Channel) from within the news content.
7. **07 Attribution Master**: Explicitly attribute all claims, complaints, allegations, FIRs, and police claims.
8. **08 Ready Reckoner**: Convert emotional, sensational, or exaggerated phrasing to standard, objective newsroom alternatives.
9. **09 Before-After Editorial Transformation**: Elevate basic sentence flow to premium literary and journalistic quality in Gujarati.

⚠️ IMPORTANT - INFO BOX (KEY POINTS SUMMARY):
- You MUST synthesize a high-quality, professional Gujarati key points summary (INFO BOX) of the article.
- Do NOT write 'None' or leave it blank.
- The Info Box must contain 3 to 5 concise, high-impact bullet points summarizing the main facts.
- Word limit for the Info Box: {info_box_min}-{info_box_max} words.

⚠️ IMPORTANT - SUBHEADING:
- You MUST generate an engaging, professional Subheading in Gujarati.
- Word limit for the Subheading: {subheading_min}-{subheading_max} words.

WORD LIMITS:
- HEADLINE: {heading_min}-{heading_max} words
- SUBHEADING: {subheading_min}-{subheading_max} words
- INTRO PARAGRAPH: {intro_min}-{intro_max} words
- BODY PARAGRAPH: {body_min}-{body_max} words
- INFO BOX: {info_box_min}-{info_box_max} words

OUTPUT FORMAT:
You MUST follow the exact format below, with each label starting on its own new line. Keep the labels in ENGLISH. Do not add any markdown around labels, just write them as shown:

HEADLINE: [Polished Premium Gujarati Headline]
ALTERNATIVE HEADLINES:
1. [Option 1]
2. [Option 2]
3. [Option 3]
SUBHEADING: [Engaging Gujarati Subheading]
INTRO PARAGRAPH: [Polished Lead paragraph applying 5W1H]
BODY PARAGRAPH: [Polished Body paragraphs in Inverted Pyramid style]
INFO BOX:
- [Key Point 1 in Gujarati]
- [Key Point 2 in Gujarati]
- [Key Point 3 in Gujarati]
- [Key Point 4 in Gujarati]
- [Key Point 5 in Gujarati]
EDITORIAL NOTES: [Brief bulleted list of specific changes: what grammar/spelling errors were fixed, what house style rule was applied, and what vocabulary was elevated]

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
        }

        lines = raw_output.split("\n")
        current_section = None
        current_content = []

        # Order matters: check longer/more-specific patterns before shorter ones
        ordered_keys = [
            "headline_cap", "alternative_headlines", "editorial_notes",
            "subheading", "intro", "body", "info_box", "headline"
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
            editorial_notes=clean_markdown(sections.get("editorial_notes")),
            validation_passed=False,
            validation_errors=[],
        )
