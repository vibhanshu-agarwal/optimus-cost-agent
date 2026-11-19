"""Keep the public Python reference within its reviewed import and operation boundary."""

from __future__ import annotations

import importlib
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "docs" / "public-python-api.md"
IMPORTS = {
    "context_engine": (
        "STRATEGIES",
        "SUMMARIZING_STRATEGIES",
        "ContractError",
        "HistoryRevision",
        "HistorySnapshot",
        "MaintenanceCallback",
        "MaintenanceRequest",
        "MaintenanceResult",
        "OrdinaryTurn",
        "PreparedView",
        "ProtectedTurnState",
        "ReuseResult",
        "StrategyParameters",
        "SummaryCheckpoint",
        "ViewLimits",
        "history_digest",
        "publish_checkpoint",
        "reuse_checkpoint",
        "turn_source_digest",
    ),
    "context_engine.engine": ("ContextEngine",),
    "optimus_model_policy": (
        "EstimatorProfile",
        "ModelEntry",
        "Origin",
        "Policy",
        "RegistryError",
        "RegistrySnapshot",
        "Role",
        "Tier",
        "ValidationIssue",
        "load_registry",
        "validate_registry",
    ),
    "optimus.telemetry": ("TelemetryEvent", "TelemetryEventKind"),
}
EXPECTED_IMPORTS = {(module, name) for module, names in IMPORTS.items() for name in names}
IMPORT_ROW = re.compile(r"\| \x60([\w.]+)\x60 \| \x60(\w+)\x60 \|")
EXAMPLE = re.compile(r"^### ([^\n]+)\n\n\x60\x60\x60python\n(.*?)^\x60\x60\x60$", re.MULTILINE | re.DOTALL)


def _section(text: str, heading: str) -> str:
    sections = re.findall(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert len(sections) == 1, f"expected exactly one {heading!r} section"
    return sections[0].strip()


def _assert_boundary(text: str) -> None:
    headers = _section(text, "Supported import paths").splitlines()
    assert headers[:2] == ["| Import from | Symbol |", "| --- | --- |"]
    rows = headers[2:]
    matches = [IMPORT_ROW.fullmatch(row) for row in rows]
    assert all(matches), "expected backticked import path and symbol in each row"
    pairs = [match.groups() for match in matches if match is not None]
    assert len(pairs) == len(set(pairs)), "duplicate import pair"
    assert set(pairs) == EXPECTED_IMPORTS, "reference differs from approved import boundary"
    assert _section(text, "Supported operations") == "- `ContextEngine.prepare_view`"


@pytest.fixture
def reference() -> str:
    return REFERENCE.read_text(encoding="utf-8") if REFERENCE.is_file() else ""


def test_reference_matches_approved_boundary(reference: str) -> None:
    assert reference, "public Python API reference is missing"
    _assert_boundary(reference)


def test_approved_reference_imports_resolve() -> None:
    for module, names in IMPORTS.items():
        loaded = importlib.import_module(module)
        assert Path(loaded.__file__).resolve().is_relative_to(ROOT / "src")
        for name in names:
            assert hasattr(loaded, name), f"missing {module}.{name}"
    assert callable(importlib.import_module("context_engine.engine").ContextEngine.prepare_view)


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ("", "approved import boundary"),
        (
            "| `context_engine.engine` | `ContextEngine` |\n| `context_engine.engine` | `Unapproved` |\n",
            "approved import boundary",
        ),
        ("| `context_engine.engine` | `ContextEngine` |\n" * 2, "duplicate import pair"),
        ("| `context_engine` | `ContextEngine` |\n", "approved import boundary"),
    ],
    ids=("missing", "extra", "duplicate", "wrong-module"),
)
def test_reference_rejects_import_drift(reference: str, replacement: str, message: str) -> None:
    original = "| `context_engine.engine` | `ContextEngine` |\n"
    assert reference.count(original) == 1
    with pytest.raises(AssertionError, match=message):
        _assert_boundary(reference.replace(original, replacement))


def test_reference_rejects_duplicate_heading(reference: str) -> None:
    with pytest.raises(AssertionError, match="exactly one 'Supported import paths'"):
        _assert_boundary(reference + "\n## Supported import paths\n")


def test_reference_examples_are_executable(reference: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    section = _section(reference, "Examples")
    examples = EXAMPLE.findall(section)
    assert section.count("```") == 6
    assert [heading for heading, _ in examples] == ["Context view", "Registry inspection", "Telemetry envelope"]
    shutil.copyfile(ROOT / "src" / "optimus_model_policy" / "defaults.yaml", tmp_path / "registry.yaml")
    monkeypatch.chdir(tmp_path)

    results = {}
    for name, code in examples:
        values: dict[str, object] = {}
        exec(compile(code, f"{REFERENCE}: {name}", "exec"), values)
        results[name] = values

    context = results["Context view"]
    assert context["view"].available
    assert context["view"].protected == context["snapshot"].protected
    registry = results["Registry inspection"]
    assert registry["snapshot"].input_hashes[0][0] == "registry.yaml"
    assert registry["issues"] == registry["validate_registry"](registry["snapshot"])
    event = results["Telemetry envelope"]["event"]
    assert event.trace_id == event.run_id
