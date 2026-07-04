from __future__ import annotations

import unicodedata

from confusable_homoglyphs import confusables


def contains_dangerous_confusable(text: str) -> bool:
    if not text:
        return False
    if "xn--" in text.lower():
        return True
    if _contains_nfkc_spoofing_form(text):
        return True
    return bool(confusables.is_dangerous(text))


def _contains_nfkc_spoofing_form(text: str) -> bool:
    for char in text:
        name = unicodedata.name(char, "")
        if "FULLWIDTH" in name or "HALFWIDTH" in name:
            return True
    return False
