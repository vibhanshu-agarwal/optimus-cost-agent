"""Naming boundary checks for the portable evidence_handoff surface."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_ROOT = REPO_ROOT / "src" / "evidence_handoff"
COLLECTOR_ROOT = EVIDENCE_ROOT / "collector"
SCENARIO_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "evidence" / "scenarios"
TASK_TEST_FILES = (
    REPO_ROOT / "tests/unit/evidence/test_import_boundaries.py",
    REPO_ROOT / "tests/unit/evidence/test_naming_boundaries.py",
    REPO_ROOT / "tests/unit/evidence/test_redaction_models.py",
    REPO_ROOT / "tests/unit/evidence/test_collector_models.py",
    REPO_ROOT / "tests/unit/evidence/test_collector_boundaries.py",
)
PYPROJECT = REPO_ROOT / "pyproject.toml"

FEATURE_ID_RE = re.compile(r"(?<![A-Z0-9-])(?:[A-Z][A-Z0-9]*-)*FEAT-[A-Z0-9]+(?:-[A-Z0-9]+)*(?![A-Z0-9-])")
PLAN_NUMBER_RE = re.compile(r"\bPlan [0-9]|\bplan-[0-9]")


def _scan_paths(paths: list[Path]) -> list[str]:
    hits: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for match in FEATURE_ID_RE.finditer(text):
            hits.append(f"{path.relative_to(REPO_ROOT).as_posix()}: feature-id {match.group(0)}")
        for match in PLAN_NUMBER_RE.finditer(text):
            hits.append(f"{path.relative_to(REPO_ROOT).as_posix()}: scheduling {match.group(0)}")
    return hits


def test_evidence_handoff_source_has_no_feature_id_or_scheduling_numbers() -> None:
    paths = sorted(EVIDENCE_ROOT.rglob("*.py"))
    assert paths, "portable package source must exist"
    assert _scan_paths(paths) == []


def test_task_owned_tests_have_no_feature_id_or_scheduling_numbers() -> None:
    missing = [path for path in TASK_TEST_FILES if not path.is_file()]
    assert missing == [], f"missing task test files: {missing}"
    assert _scan_paths(list(TASK_TEST_FILES)) == []


def test_package_and_module_names_are_descriptive() -> None:
    assert (EVIDENCE_ROOT / "__init__.py").is_file()
    assert (EVIDENCE_ROOT / "redaction" / "models.py").is_file()
    assert (COLLECTOR_ROOT / "__init__.py").is_file()
    assert (COLLECTOR_ROOT / "models.py").is_file()
    assert (COLLECTOR_ROOT / "scenarios.py").is_file()
    names = [path.name for path in EVIDENCE_ROOT.rglob("*.py")]
    assert all("plan-" not in name for name in names)
    assert all("feat_" not in name for name in names)
    assert all(FEATURE_ID_RE.search(name) is None for name in names)


def test_collector_scenarios_and_artifacts_have_no_feature_id_or_scheduling_numbers() -> None:
    paths = sorted(COLLECTOR_ROOT.rglob("*.py"))
    assert paths, "collector package source must exist"
    fixture_paths = sorted(SCENARIO_FIXTURES.glob("*"))
    assert fixture_paths, "scenario fixtures must exist"
    assert _scan_paths(paths + fixture_paths) == []


def test_version_suffix_v1_is_allowed_in_descriptive_names() -> None:
    # Guard against over-broad bans: version suffixes remain legal.
    sample = "evidence-redaction-v1 schema_v1"
    assert PLAN_NUMBER_RE.search(sample) is None
    assert FEATURE_ID_RE.search(sample) is None


def test_pyproject_requires_os_keyring_marker_is_descriptive() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    assert "requires_os_keyring" in text
    assert FEATURE_ID_RE.search(text) is None or "requires_os_keyring" in text
    # Marker name itself must not encode a feature id.
    assert "FEAT-" not in text.split("requires_os_keyring", 1)[0][-80:]
    marker_line = next(line for line in text.splitlines() if "requires_os_keyring" in line)
    assert FEATURE_ID_RE.search(marker_line) is None
    assert PLAN_NUMBER_RE.search(marker_line) is None
