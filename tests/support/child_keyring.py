"""A test's child process never reaches the host's credential store (#540, the child-process residual of #538).

Test support only. The root conftest keeps the pytest process on keyring's `fail` backend, but a child resolves its own
backend: on the operator's Windows host the Credential Manager, under WSLg Secret Service, which can block on a prompt.

`environment(base)` is the control for a child that can reach the keyring: it selects `fail` in that child's own
environment through `PYTHON_KEYRING_BACKEND`, which keyring reads before its config file and before probing any host
backend, and which the child's own children inherit. The child tripwire's environments carry it, so every tripwire
site has it. Nothing is set in this process's environment (#538 rejected a session-wide variable).

`import_closure(...)` is the proof for a child that cannot reach it: every module the child's entry can import, lazy
imports included, read from the repository's own sources. A closure that imports `keyring` nowhere cannot fall back to
it. A dynamic import, `exec` or `runpy` anywhere in the closure leaves it unbounded and the proof fails closed.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

VARIABLE = "PYTHON_KEYRING_BACKEND"
FAIL_BACKEND = "keyring.backends.fail.Keyring"
# The calls that put the control into a child's environment; the site map test looks for one at each controlled site.
CONTROL_CALLS = ("child_keyring.environment", "child_tripwire.environment", "child_tripwire.hooked_environment")

_ROOT = Path(__file__).resolve().parents[2]
_SEARCH = (_ROOT / "src", _ROOT)
# Any reference to these, called or aliased, can load code by a computed name: the closure is then unbounded.
_UNBOUNDED_NAMES = {"import_module", "__import__", "run_path", "run_module", "spec_from_file_location", "module_from_spec",
                    "exec", "eval"}


def environment(base: Mapping[str, str]) -> dict[str, str]:
    """The child environment the test already built, with keyring's `fail` backend selected for that child."""
    return {**base, VARIABLE: FAIL_BACKEND}


def _module_file(name: str) -> Path | None:
    """The module's file, a namespace package's directory, or None when the repository does not hold the name."""
    for base in _SEARCH:
        candidate = base.joinpath(*name.split("."))
        if (candidate / "__init__.py").is_file():
            return candidate / "__init__.py"
        if candidate.with_suffix(".py").is_file():
            return candidate.with_suffix(".py")
        if candidate.is_dir():
            return candidate
    return None


def _imports(tree: ast.AST, package: str) -> tuple[set[str], set[str], list[str]]:
    """Names that must resolve as modules, names that may be attributes (`from x import y`), and unbounded constructs."""
    required: set[str] = set()
    optional: set[str] = set()
    unbounded: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            required.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            stem = node.module or ""
            if node.level:
                parts = package.split(".")[: len(package.split(".")) - node.level + 1]
                stem = ".".join(parts + ([stem] if stem else []))
            required.add(stem)
            optional.update(f"{stem}.{alias.name}" for alias in node.names)
            unbounded.extend(f"{node.lineno}: from {stem} import {alias.name}" for alias in node.names if alias.name in _UNBOUNDED_NAMES)
        elif isinstance(node, ast.Name) and node.id in _UNBOUNDED_NAMES:
            unbounded.append(f"{node.lineno}: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in _UNBOUNDED_NAMES:
            unbounded.append(f"{node.lineno}: {ast.unparse(node)}")
    return {name for name in required if name}, {name for name in optional if name}, unbounded


def _installed(top: str) -> bool:
    if top in sys.stdlib_module_names:  # includes modules of other platforms (pwd, winreg)
        return True
    try:
        return importlib.util.find_spec(top) is not None
    except (ImportError, ValueError):
        return False


def import_closure(entries: Iterable[str]) -> dict[str, list[str]]:
    """The repository modules reachable from `entries`, which of them import `keyring`, and what leaves it unbounded.

    An entry is a dotted module name, a repository-relative `.py` path, or `-c:<program text>`. Namespace packages are
    walked. A name outside the repository is a leaf: keyring is reported wherever it is imported. Fails closed (reported
    as unbounded): a computed import, `exec`, `eval` or `runpy` referenced anywhere, called or aliased; a module name
    the repository should hold but does not; a top-level name neither the repository nor this environment holds (a
    script's own `sys.path` entries, for example).
    """
    seen: dict[str, Path] = {}
    keyring_importers: list[str] = []
    unbounded: list[str] = []
    pending: list[tuple[str, str, bool]] = []  # (importing module, imported name, must resolve)

    def scan(label: str, source: str, package: str) -> None:
        required, optional, dynamic = _imports(ast.parse(source), package)
        unbounded.extend(f"{label}:{item}" for item in dynamic)
        if any(name == "keyring" or name.startswith("keyring.") for name in required | optional):
            keyring_importers.append(label)
        pending.extend([(label, name, True) for name in required] + [(label, name, False) for name in optional])

    for entry in entries:
        if entry.startswith("-c:"):
            scan("<program>", entry[3:], "")
        elif entry.endswith(".py"):
            scan(entry, (_ROOT / entry).read_text(encoding="utf-8"), "")
        else:
            pending.append(("<entry>", entry, True))
    while pending:
        importer, name, must_resolve = pending.pop()
        parts = name.split(".")
        if _module_file(parts[0]) is None:
            if must_resolve and not _installed(parts[0]):
                unbounded.append(f"{importer}: unresolved {name}")
            continue
        for index in range(1, len(parts) + 1):
            prefix = ".".join(parts[:index])
            path = _module_file(prefix)
            if path is None:
                if must_resolve:
                    unbounded.append(f"{importer}: unresolved {name}")
                break
            if prefix not in seen:
                seen[prefix] = path
                if path.suffix == ".py":
                    package = prefix if path.name == "__init__.py" else prefix.rpartition(".")[0]
                    scan(prefix, path.read_text(encoding="utf-8"), package)
    return {"modules": sorted(seen), "keyring_importers": sorted(set(keyring_importers)), "unbounded": sorted(set(unbounded))}


MEASUREMENT_CALLS = ("run_fresh_measurement", "measure_current_entry", "session_measurement_reuse")


def control_measurement_children(monkeypatch) -> None:
    """A Plan 11.26 measurement child is launched by the audit tool itself (`measurement.run_fresh_measurement`), from an
    environment copied from this process, so no test launch site carries it. A test that drives a measurement applies
    the control to that environment for the test's duration (Codex round 1, finding 4)."""
    from tools.plan1126_runtime_audit import measurement  # noqa: PLC0415 - only for the tests that measure

    original = measurement.fresh_child_environment
    monkeypatch.setattr(measurement, "fresh_child_environment", lambda cache_directory: environment(original(cache_directory)))


def control_inherited_children(monkeypatch) -> None:
    """A child that repository code launches with no `env=` inherits this process's environment (`probes.run_contained`).
    A test that reaches such a launch selects `fail` for its own duration (#661); `monkeypatch` restores the environment
    afterwards, so nothing outlives the test and nothing is session-wide (#538 rejected that)."""
    monkeypatch.setenv(VARIABLE, FAIL_BACKEND)
