from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs/sources/local-gateway-architecture-v3/tools/validate_publication.py"
)
# The focused inventory tests do not exercise SVG font measurement. Keep the
# validator importable in the minimal docs-test environment without changing
# the production dependency boundary.
if "PIL" not in sys.modules:
    pil = types.ModuleType("PIL")
    pil_image_font = types.ModuleType("PIL.ImageFont")
    pil_image_font.ImageFont = object
    sys.modules["PIL"] = pil
    sys.modules["PIL.ImageFont"] = pil_image_font
if "pypdf" not in sys.modules:
    pypdf = types.ModuleType("pypdf")
    pypdf.PdfReader = object
    sys.modules["pypdf"] = pypdf
SPEC = importlib.util.spec_from_file_location("validate_publication", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
validate_publication = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validate_publication
SPEC.loader.exec_module(validate_publication)


def test_inventory_diff_reports_missing_and_added_markers() -> None:
    source = """
    # 12. Guardrail contracts
    ## 12A. Permission & Pre-Tool Enforcement
    `PreToolGuard`
    """
    candidate = """
    # 12. Guardrail contracts
    `max_budget_tokens`
    """

    diff = validate_publication.inventory_diff(source, candidate)

    assert "heading:12A" in diff.missing
    assert "identifier:PreToolGuard" in diff.missing
    assert "identifier:max_budget_tokens" in diff.added


def test_inventory_diff_accepts_code_marker_surviving_without_markdown_ticks() -> None:
    diff = validate_publication.inventory_diff(
        "`build_tool_dependencies()` and `LoopStopReason`",
        "build_tool_dependencies()\nLoopStopReason",
    )

    assert not diff.missing


def test_authorized_inventory_change_requires_known_redline_entry() -> None:
    source = "# 7. Controls\n`old_budget_field`"
    candidate = "# 7. Controls\n`new_budget_field`"

    with pytest.raises(AssertionError, match="unknown redline entry"):
        validate_publication.assert_inventory_complete(
            source,
            candidate,
            exceptions=[
                {
                    "marker": "identifier:new_budget_field",
                    "entry_id": "NOT-A-REDLINE-ENTRY",
                }
            ],
            known_entry_ids={"GR-1"},
        )


def test_authorized_inventory_change_can_be_scoped_to_redline_entry() -> None:
    source = "# 7. Controls\n`old_budget_field`"
    candidate = "# 7. Controls\n`new_budget_field`"

    validate_publication.assert_inventory_complete(
        source,
        candidate,
        exceptions=[
            {"marker": "identifier:new_budget_field", "entry_id": "GR-1"},
            {"marker": "identifier:old_budget_field", "entry_id": "GR-1"},
        ],
        known_entry_ids={"GR-1"},
    )


def test_forbidden_marker_fails_even_when_source_and_candidate_match() -> None:
    with pytest.raises(AssertionError, match="forbidden inventory markers"):
        validate_publication.assert_inventory_complete(
            "# 7. Controls\n`max_budget_tokens`",
            "# 7. Controls\n`max_budget_tokens`",
            exceptions=[],
            known_entry_ids={"GR-1"},
            forbidden_markers={"identifier:max_budget_tokens"},
        )
