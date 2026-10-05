import re
from typing import Optional

def parse_output(raw_output: str):
    sections = {
        "headline": "",
        "headline_cap": None,
        "alternative_headlines": None,
        "subheading": None,
        "dateline": None,
        "intro": "",
        "body": "",
        "info_box": None,
        "ankda": None,
        "editorial_notes": None,
    }

    patterns = {
        "headline_cap":          r"(?i)^\s*[\*\#\-\s\d\.]*(?:HEADLINE\s*CAP|કેપ\s*હેડિંગ)\s*[:\-\—]*",
        "alternative_headlines": r"(?i)^\s*[\*\#\-\s\d\.]*(?:ALT(?:ERNATIVE)?\s*HEADLINES?|વિકલ્પો?|મુખ્ય હેડિંગના.*વિકલ્પ)\s*[:\-\—]*",
        "editorial_notes":       r"(?i)^\s*[\*\#\-\s\d\.]*(?:EDITORIAL\s*NOTES?|એડિટોરિયલ નોટ|ડેસ્ક નોંધ|નોંધ)[^\n]*",
        "headline":              r"(?i)^\s*[\*\#\-\s\d\.]*(?:HEADLINE|HEADING|TOPIC|હેડલાઇન|શીર્ષક|મુખ્ય\s*હેડિંગ|મુખ્ય સમાચાર)\s*[:\-\—]*",
        "subheading":            r"(?i)^\s*[\*\#\-\s\d\.]*(?:SUB\s*HEADING|SUBTITLE|સબહેડલાઇન|સબ-હેડલાઇન|ગૌણ શીર્ષક|પેટા\s*હેડિંગ)\s*[:\-\—]*",
        "dateline":              r"(?i)^\s*[\*\#\-\s\d\.]*(?:DATELINE|ડેટલાઇન)\s*[:\-\—]*",
        "intro":                 r"(?i)^\s*[\*\#\-\s\d\.]*(?:INTRO|INTRODUCTION|LEAD|ઇન્ટ્રો|પ્રસ્તાવના|શરૂઆત)(?:\s*(?:PARAGRAPH|પેરેગ્રાફ))?\s*[:\-\—]*",
        "body":                  r"(?i)^\s*[\*\#\-\s\d\.]*(?:BODY|CONTENT|MAIN|STORY|ARTICLE|બોડી\s*કોપી|બોડી|વિષયવસ્તુ|મુખ્ય લખાણ|કોપી|મુખ્ય કોપી)(?:\s*(?:PARAGRAPH|પેરેગ્રાફ))?\s*[:\-\—]*",
        "info_box":              r"(?i)^\s*[\*\#\-\s\d\.]*(?:INFO|KEY|SUMMARY|HIGHLIGHTS|ઇન્ફો|મુખ્ય મુદ્દા)(?:\s*(?:BOX|POINTS|HIGHLIGHTS|બોક્સ))?\s*[:\-\—]*",
        "ankda":                 r"(?i)^\s*[\*\#\-\s\d\.]*(?:ANKDA|STATS|STATISTICS|આંકડા|આંકડાકીય માહિતી)\s*[:\-\—]*",
    }

    lines = raw_output.split("\n")
    current_section = None
    current_content = []

    ordered_keys = [
        "headline_cap", "alternative_headlines", "editorial_notes",
        "subheading", "dateline", "intro", "body", "info_box", "ankda", "headline"
    ]

    for line in lines:
        clean_line = line.strip()
        if not clean_line:
            if current_section:
                current_content.append("")
            continue

        found_new = False
        is_list_item = re.match(r"^\s*(?:[\-\*•]|\d+[\.\)\-])\s+", clean_line)
        
        if current_section != "editorial_notes" and not is_list_item:
            for key in ordered_keys:
                pattern = patterns[key]
                match = re.search(pattern, clean_line)
                if match and match.start() < 10:  
                    if key == "alternative_headlines" and "1." in clean_line and "વિકલ્પ" not in clean_line:
                        continue
                        
                    if current_section:
                        sections[current_section] = "\n".join(current_content).strip()

                    current_section = key
                    content_part = clean_line[match.end():].strip()
                    current_content = [content_part] if content_part else []
                    found_new = True
                    break

        if not found_new and current_section:
            current_content.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_content).strip()

    def clean_markdown(text):
        if not text:
            return text
        text = re.sub(r"[\*\#\_]+", "", text).strip()
        # If text is only dashes, return empty
        if not text.replace("-", "").replace("—", "").strip():
            return ""
        return text

    for k, v in sections.items():
        if v is not None:
            sections[k] = clean_markdown(v)
            
    return sections

test_a = """
### 1. કેપ હેડિંગ
મારી કેપ

### 7. બોડી કોપી
આ મારી બોડી છે
જેમાં --- આવે છે.
"""

test_b = """
### 1. કેપ હેડિંગ
—

### 7. બોડી કોપી
—
---

### 8. એડિટોરિયલ નોટ — પ્રકાશન માટે નહીં
આ નોટ છે.
"""

test_c = """
### 7. બોડી કોપી
કોપી

—
---
"""

print("Test A:", parse_output(test_a)["body"])
print("Test B:", parse_output(test_b)["body"])
print("Test C:", parse_output(test_c)["body"])
