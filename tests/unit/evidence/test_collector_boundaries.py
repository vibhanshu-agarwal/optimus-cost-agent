"""Collector-specific mechanical boundary scans."""

from __future__ import annotations

import ast
import importlib
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
COLLECTOR_ROOT = REPO_ROOT / "src" / "evidence_handoff" / "collector"
SCENARIO_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "evidence" / "scenarios"

FORBIDDEN_COLLECTOR_ROOTS = frozenset(
    {"optimus", "optimus_gateway", "optimus_security", "tools", "PIL"}
)
PROMPT_INJECTION_RE = re.compile(r"prompt[_-]?inject", re.IGNORECASE)
MODEL_LITERAL_RE = re.compile(
    r"""(?ix)
    \bdefault_model\b
    | \bmodel\s*=\s*["'][^"']+["']
    | \b(?:gpt|claude|glm|o1|o3|gemini)[-_/]
    | \bopenai/
    """
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _module_root(name: str | None) -> str | None:
    if not name:
        return None
    return name.split(".", 1)[0]


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _module_root(alias.name)
                if root:
                    roots.add(root)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            root = _module_root(node.module)
            if root:
                roots.add(root)
    return roots


def test_collector_rejects_optimus_security_and_deployable_imports() -> None:
    violations: list[str] = []
    allowed = frozenset({"__future__", "evidence_handoff"}) | sys.stdlib_module_names
    for path in _python_files(COLLECTOR_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for root in _imported_roots(tree):
            if root in allowed:
                continue
            violations.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {root}")
    assert violations == []


def test_collector_source_has_no_prompt_injection_capability() -> None:
    offenders: list[str] = []
    for path in _python_files(COLLECTOR_ROOT):
        text = path.read_text(encoding="utf-8")
        if PROMPT_INJECTION_RE.search(text):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    for path in sorted(SCENARIO_FIXTURES.glob("*")):
        if PROMPT_INJECTION_RE.search(path.read_text(encoding="utf-8")):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []


def test_collector_and_fixtures_have_no_model_literals_or_defaults() -> None:
    offenders: list[str] = []
    scan_paths = _python_files(COLLECTOR_ROOT) + sorted(SCENARIO_FIXTURES.glob("*"))
    for path in scan_paths:
        text = path.read_text(encoding="utf-8")
        if MODEL_LITERAL_RE.search(text):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []


def test_shipped_scenarios_require_model_binding_without_value() -> None:
    from evidence_handoff.collector.scenarios import load_scenario

    for path in (SCENARIO_FIXTURES / "zed-session.toml", SCENARIO_FIXTURES / "zed-session.json"):
        scenario = load_scenario(path)
        assert any(binding.name == "model" and binding.required for binding in scenario.required_bindings)
        assert all(parameter.name != "model" for parameter in scenario.client.parameters)


class _BlockNonStdlibFinder:
    def find_spec(self, fullname: str, path: object = None, target: object = None):  # noqa: ANN001
        root = fullname.split(".", 1)[0]
        if root in FORBIDDEN_COLLECTOR_ROOTS:
            raise ImportError(f"blocked non-portable import: {fullname}")
        return None


def test_isolated_collector_import_blocks_security_and_deployables() -> None:
    portable = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name == "evidence_handoff" or name.startswith("evidence_handoff.")
    }
    blocked = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name.split(".", 1)[0] in FORBIDDEN_COLLECTOR_ROOTS
    }
    finder = _BlockNonStdlibFinder()
    sys.meta_path.insert(0, finder)
    try:
        with pytest.raises(ImportError, match="blocked non-portable import"):
            importlib.import_module("optimus_security")
        with pytest.raises(ImportError, match="blocked non-portable import"):
            importlib.import_module("optimus")
        module = importlib.import_module("evidence_handoff.collector.scenarios")
        assert module.load_scenario.__module__ == "evidence_handoff.collector.scenarios"
    finally:
        sys.meta_path.remove(finder)
        sys.modules.update(blocked)
        sys.modules.update(portable)
