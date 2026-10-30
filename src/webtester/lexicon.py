"""Cue words as data (v5 plan O6 b, D60): the word lists the v5 rules use, one TOML file per language in
`lexicon/`. WEBTESTER_LANG picks the file (default en); a missing key falls back to English."""

from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path

LEX_DIR = Path(__file__).parent / "lexicon"


@lru_cache(maxsize=8)
def lexicon(lang: str | None = None) -> dict:
    lang = lang or os.environ.get("WEBTESTER_LANG", "en")
    en = tomllib.loads((LEX_DIR / "en.toml").read_text(encoding="utf-8"))
    path = LEX_DIR / f"{lang}.toml"
    if lang == "en" or not path.exists():
        return en
    return {**en, **tomllib.loads(path.read_text(encoding="utf-8"))}


def words(key: str, lang: str | None = None) -> list[str]:
    return list(lexicon(lang).get(key, []))


def alternation(key: str, lang: str | None = None) -> str:
    """The list as one regex alternation (its entries are regex fragments)."""
    return "|".join(words(key, lang))
