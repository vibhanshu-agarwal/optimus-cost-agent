from __future__ import annotations

import unicodedata

from confusable_homoglyphs import categories, confusables

# #619: the non-ASCII Latin- and Common-script characters the library's table maps to a single ASCII character
# (U+0131, U+2212, U+2019, U+2002). Accented Latin letters are not in the table.
_ASCII_LOOKALIKES = frozenset(
    char
    for char, entries in confusables.confusables_data.items()
    if len(char) == 1
    and not char.isascii()
    and categories.alias(char) in ("LATIN", "COMMON")
    and any(len(entry["c"]) == 1 and entry["c"].isascii() for entry in entries)
)


def contains_dangerous_confusable(text: str, *, latin_lookalikes_only: bool = False) -> bool:
    """True for punycode, fullwidth Latin beside Latin, or mixed scripts holding a confusable character.

    ``latin_lookalikes_only`` (#596) skips characters of the Latin and Common scripts and flags any other character
    that maps to a Latin or Common one, so a plain non-Latin name beside Latin text passes. It also flags (#619) a
    Latin- or Common-script character that the table maps to ASCII, such as U+0131 or U+2212. The default keeps the
    strict any-script form, without the ASCII look-alike check.
    """
    if not text:
        return False
    if "xn--" in text.lower():
        return True
    if _contains_nfkc_spoofing_form(text):
        return True
    if latin_lookalikes_only:
        if any(char in _ASCII_LOOKALIKES for char in text):
            return True
        return bool(confusables.is_dangerous(text, preferred_aliases=["latin", "common"]))
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
