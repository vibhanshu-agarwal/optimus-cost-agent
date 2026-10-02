"""Plan 12.2 Task 6: the Context Engine stays extractable (ADR-001; design spec 3; Task 1 contracts 1).

`context_engine` imports nothing from the host (`optimus`), the Gateway, security or evidence
packages. Two independent checks must agree: an AST scan of every module, which relative or dynamic
imports cannot evade, and a fresh interpreter that imports only `context_engine`. The registry package
is excluded too: the engine receives explicit parameters and needs no registry.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from importlib import resources
from pathlib import Path

import pytest

from tools.tracked_repository_files import tracked_repository_files

_REPO_ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN = (
    "optimus",
    "optimus_gateway",
    "optimus_security",
    "optimus_model_policy",
    "evidence_handoff",
    "evidence_handoff_runtime",
)


def forbidden_imports(source: str) -> list[str]:
    """Every import in `source` that reaches outside the neutral package or cannot be checked."""
    problems: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            problems += [alias.name for alias in node.names if alias.name.split(".")[0] in FORBIDDEN]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and (node.module or "").split(".")[0] in FORBIDDEN:
                problems.append(str(node.module))
            elif node.level > 1:
                # The package is flat: a parent-relative import can only leave it.
                problems.append("." * node.level + (node.module or ""))
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            if name in {"__import__", "import_module"}:
                problems.append(f"dynamic import via {name}")
    return problems


def _engine_sources() -> list[Path]:
    sources = sorted(p for p in tracked_repository_files(_REPO_ROOT, pathspecs=("src/context_engine",)) if p.suffix == ".py")
    # The scan reads tracked files; every module of the importable package must be among them, so an
    # untracked module cannot escape it.
    modules = sorted(entry.name for entry in resources.files("context_engine").iterdir() if entry.name.endswith(".py"))
    assert [path.name for path in sources] == modules, "every engine module must be tracked and scanned"
    return sources


def test_no_engine_module_imports_a_forbidden_package() -> None:
    offenders = {path.name: forbidden_imports(path.read_text(encoding="utf-8")) for path in _engine_sources()}
    assert {name: found for name, found in offenders.items() if found} == {}


@pytest.mark.parametrize(
    "source",
    [
        "import optimus.acp.spec",
        "from optimus_gateway import responses",
        "from ..optimus import agent",
        "import importlib\nimportlib.import_module('optimus')",
        "__import__('optimus_security')",
        "import optimus_model_policy as policy",
    ],
    ids=["import", "from-import", "parent-relative", "import-module", "dunder-import", "registry"],
)
def test_the_scan_catches_each_way_out(source: str) -> None:
    assert forbidden_imports(source), "the scan must flag this import"


def test_a_package_relative_import_is_allowed() -> None:
    assert forbidden_imports("from .contracts import HistorySnapshot\nfrom . import checkpoints") == []


def test_a_fresh_interpreter_importing_the_engine_loads_no_forbidden_package() -> None:
    probe = (
        "import json, sys\n"
        "import context_engine\n"
        "print(json.dumps(sorted({name.split('.')[0] for name in sys.modules})))\n"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=False, cwd=_REPO_ROOT)
    assert result.returncode == 0, result.stderr
    loaded = set(json.loads(result.stdout))
    assert "context_engine" in loaded
    assert loaded.isdisjoint(FORBIDDEN), sorted(loaded & set(FORBIDDEN))


def test_the_public_api_is_exported() -> None:
    import context_engine

    for name in (
        "HistoryRevision",
        "OrdinaryTurn",
        "ProtectedTurnState",
        "HistorySnapshot",
        "StrategyParameters",
        "ViewLimits",
        "MaintenanceRequest",
        "MaintenanceResult",
        "MaintenanceCallback",
        "SummaryCheckpoint",
        "PreparedView",
        "ContractError",
        "publish_checkpoint",
        "reuse_checkpoint",
        "history_digest",
        "turn_source_digest",
    ):
        assert hasattr(context_engine, name), name
