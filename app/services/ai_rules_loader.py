"""
ai_rules_loader.py
------------------
Reads the senior_editor_full_prompt.md and builds the authoritative
SANDESH newsroom system prompt.
"""

import os
from functools import lru_cache
from pathlib import Path

# ── Path to the rules directory ──────────────────────────────────────────────
_AI_RULES_DIR = Path(__file__).resolve().parent.parent / "ai_rules"


@lru_cache(maxsize=1)
def load_rules_text() -> str:
    """
    Read the senior_editor_full_prompt.md file and return its content.
    """
    filepath = _AI_RULES_DIR / "senior_editor_full_prompt.md"
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return "[senior_editor_full_prompt.md not found]"


@lru_cache(maxsize=1)
def get_sandesh_system_prompt() -> str:
    """
    Return the full SANDESH newsroom system prompt.
    """
    return load_rules_text()


def inject_system_prompt(user_prompt: str) -> tuple[str, str]:
    """
    Returns the system prompt and the user prompt as a tuple.
    """
    system = get_sandesh_system_prompt()
    return system, user_prompt

