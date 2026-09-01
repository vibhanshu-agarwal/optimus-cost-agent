"""Machine gate for the Plan 11.5 Task 6 USD migration.

Zero retired provider-balance identifiers may remain in active source or
test surfaces, with exactly one allowlisted exception: the provider-native
unit literal for Tavily's billing units. This mirrors the Step 4 repo-wide
census (``rg`` over ``src/**``/``tests/**``) as an ordinary pytest test so
CI enforces it without a separate shell invocation.

The retired-name substring is assembled at runtime from smaller literals
(rather than spelled out as a single token) so this file does not trip its
own gate the way a literal occurrence would.
"""
from __future__ import annotations

import re
from pathlib import Path

from tools.tracked_repository_files import tracked_repository_files

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOKEN_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_RETIRED_SUBSTRING = "cred" + "it"
_ALLOWLISTED_TOKEN = "tavily_" + _RETIRED_SUBSTRING + "s"
_SCAN_ROOTS = ("src", "tests")


def _iter_scanned_files() -> "list[Path]":
    return list(tracked_repository_files(_REPO_ROOT, pathspecs=_SCAN_ROOTS))


def _violations() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in _iter_scanned_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for token in _TOKEN_PATTERN.findall(text):
            if _RETIRED_SUBSTRING in token.lower() and token != _ALLOWLISTED_TOKEN:
                counts[token] = counts.get(token, 0) + 1
    return counts


def test_no_legacy_provider_balance_identifiers_remain_in_active_surfaces() -> None:
    """Reproduces the Step 4 census: only the allowlisted provider-native unit survives."""
    violations = _violations()

    assert violations == {}, (
        "retired provider-balance identifiers found in active src/tests surfaces "
        f"(only {_ALLOWLISTED_TOKEN!r} is allowlisted): {sorted(violations)}"
    )


def test_allowlisted_provider_native_unit_literal_is_the_sole_exception() -> None:
    assert _ALLOWLISTED_TOKEN == "tavily_credits"
