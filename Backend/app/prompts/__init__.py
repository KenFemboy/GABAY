"""Versioned prompts. Never edit a released prompt file: add vN+1 and bump the constant.

Each saved AI draft stores the prompt version it was made with.
"""

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent

YEAR_END_PROMPT_VERSION = "year-end-v1"
_FILES = {"year-end-v1": PROMPTS_DIR / "year_end_evaluation" / "v1.md"}


@lru_cache
def load_prompt(version: str = YEAR_END_PROMPT_VERSION) -> str:
    try:
        return _FILES[version].read_text(encoding="utf-8")
    except KeyError as exc:
        raise ValueError(f"Unknown prompt version: {version}") from exc
