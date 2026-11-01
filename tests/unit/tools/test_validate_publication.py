from __future__ import annotations

import importlib.machinery
import importlib.util
import logging
import runpy
import sys
import types
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs/sources/archive/local-gateway-architecture-v3/tools/validate_publication.py"
)
# The focused inventory tests do not exercise SVG font measurement. Keep the
# validator importable in the minimal docs-test environment without changing
# the production dependency boundary. Prefer the real packages when installed
# so sibling unit suites (e.g. evidence_gather redaction) are not poisoned.
try:
    import PIL  # noqa: F401
except ImportError:
    if "PIL" not in sys.modules:
        pil = types.ModuleType("PIL")
        pil_image = types.ModuleType("PIL.Image")
        pil_image.Image = object
        pil_image_font = types.ModuleType("PIL.ImageFont")
        pil_image_font.ImageFont = object
        pil.Image = pil_image
        sys.modules["PIL"] = pil
        sys.modules["PIL.Image"] = pil_image
        sys.modules["PIL.ImageFont"] = pil_image_font
try:
    import pypdf  # noqa: F401
except ImportError:
    if "pypdf" not in sys.modules:
        pypdf = types.ModuleType("pypdf")
        pypdf.PdfReader = object
        sys.modules["pypdf"] = pypdf
SPEC = importlib.util.spec_from_file_location("validate_publication", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
validate_publication = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validate_publication
_previous_logging_threshold = logging.root.manager.disable
try:
    SPEC.loader.exec_module(validate_publication)
finally:
    logging.disable(_previous_logging_threshold)


@pytest.mark.parametrize("threshold", [logging.NOTSET, logging.ERROR], ids=["enabled", "muted"])
@pytest.mark.parametrize("import_fails", [False, True], ids=["success", "failure"])
def test_validator_import_preserves_logging_threshold(threshold: int, import_fails: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    previous_threshold = logging.root.manager.disable
    monkeypatch.setitem(sys.modules, SPEC.name, sys.modules[SPEC.name])
    real_exec = importlib.machinery.SourceFileLoader.exec_module

    def execute_then_fail(loader: importlib.machinery.SourceFileLoader, module: types.ModuleType) -> None:
        real_exec(loader, module)
        if Path(loader.path).resolve() == MODULE_PATH.resolve():
            raise RuntimeError("injected validator import failure")

    try:
        logging.disable(threshold)
        if import_fails:
            monkeypatch.setattr(importlib.machinery.SourceFileLoader, "exec_module", execute_then_fail)
            with pytest.raises(RuntimeError, match="injected validator import failure"):
                runpy.run_path(__file__)
        else:
            runpy.run_path(__file__)
        assert logging.root.manager.disable == threshold
    finally:
        logging.disable(previous_threshold)


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
