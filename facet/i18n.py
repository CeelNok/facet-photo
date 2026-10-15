"""Tiny translation layer. Source strings are English; ``lang_hu.HU`` holds the Hungarian ones.

Usage: ``tr("Photos: {n}", n=5)``. The language is chosen once at start-up (Settings → Language).
"""

from __future__ import annotations

from PySide6.QtCore import QLocale

LANGUAGES = {"en": "English", "hu": "Magyar"}
_lang = "en"
_table: dict[str, str] = {}


def system_language() -> str:
    return "hu" if QLocale.system().language() == QLocale.Language.Hungarian else "en"


def set_language(lang: str | None) -> str:
    global _lang, _table
    _lang = lang if lang in LANGUAGES else system_language()
    if _lang == "hu":
        from facet.lang_hu import HU

        _table = HU
    else:
        _table = {}
    return _lang


def language() -> str:
    return _lang


def tr(text: str, **kw) -> str:
    out = _table.get(text, text)
    return out.format(**kw) if kw else out
