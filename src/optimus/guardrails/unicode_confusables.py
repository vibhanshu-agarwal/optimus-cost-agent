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


def _contains_latin_letter(text: str) -> bool:
    return any(_is_latin_letter(char) for char in text)


def _is_latin_letter(char: str) -> bool:
    if not char.isalpha():
        return False
    return "LATIN" in unicodedata.name(char, "")


def _contains_fullwidth_or_halfwidth_latin_letter(text: str) -> bool:
    for char in text:
        name = unicodedata.name(char, "")
        if ("FULLWIDTH" in name or "HALFWIDTH" in name) and "LATIN" in name and char.isalpha():
            return True
    return False


def _contains_nfkc_spoofing_form(text: str) -> bool:
    return _contains_latin_letter(text) and _contains_fullwidth_or_halfwidth_latin_letter(text)
