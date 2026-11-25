from __future__ import annotations

import unicodedata

from confusable_homoglyphs import confusables


def contains_dangerous_confusable(text: str, *, latin_lookalikes_only: bool = False) -> bool:
    """True for punycode, fullwidth Latin beside Latin, or mixed scripts holding a confusable character.

    ``latin_lookalikes_only`` (#596) counts only characters that look like Latin or common ones, so a plain
    non-Latin name beside Latin text passes; the default keeps the strict any-script form.
    """
    if not text:
        return False
    if "xn--" in text.lower():
        return True
    if _contains_nfkc_spoofing_form(text):
        return True
    preferred_aliases = ["latin", "common"] if latin_lookalikes_only else []
    return bool(confusables.is_dangerous(text, preferred_aliases=preferred_aliases))


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
