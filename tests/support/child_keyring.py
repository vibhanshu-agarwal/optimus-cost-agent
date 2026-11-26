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
from collections.abc import Iterable, Mapping
from pathlib import Path

VARIABLE = "PYTHON_KEYRING_BACKEND"
FAIL_BACKEND = "keyring.backends.fail.Keyring"
# The calls that put the control into a child's environment; the site map test looks for one at each controlled site.
CONTROL_CALLS = ("child_keyring.environment", "child_tripwire.environment", "child_tripwire.hooked_environment")

_ROOT = Path(__file__).resolve().parents[2]
_SEARCH = (_ROOT / "src", _ROOT)
_UNBOUNDED_CALLS = {"importlib.import_module", "__import__", "import_module", "runpy.run_path", "runpy.run_module", "exec",
                    "importlib.util.spec_from_file_location", "spec_from_file_location"}


def environment(base: Mapping[str, str]) -> dict[str, str]:
    """The child environment the test already built, with keyring's `fail` backend selected for that child."""
    return {**base, VARIABLE: FAIL_BACKEND}


def _module_file(name: str) -> Path | None:
    for base in _SEARCH:
        candidate = base.joinpath(*name.split("."))
        if (candidate / "__init__.py").is_file():
            return candidate / "__init__.py"
        if candidate.with_suffix(".py").is_file():
            return candidate.with_suffix(".py")
    return None


def _imports(tree: ast.AST, package: str) -> tuple[set[str], list[str]]:
    """Every name an import statement anywhere in the tree can load, and every unbounded construct (line: call)."""
    names: set[str] = set()
    unbounded: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            stem = node.module or ""
            if node.level:
                parts = package.split(".")[: len(package.split(".")) - node.level + 1]
                stem = ".".join(parts + ([stem] if stem else []))
            names.add(stem)
            names.update(f"{stem}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call) and ast.unparse(node.func) in _UNBOUNDED_CALLS:
            unbounded.append(f"{node.lineno}: {ast.unparse(node.func)}")
    return {name for name in names if name}, unbounded


def import_closure(entries: Iterable[str]) -> dict[str, list[str]]:
    """The repository modules reachable from `entries`, which of them import `keyring`, and what leaves it unbounded.

    An entry is a dotted module name, a repository-relative `.py` path, or `-c:<program text>`. A name outside the
    repository is a leaf: keyring itself is the only leaf that matters, and it is reported wherever it is imported.
    """
    seen: dict[str, Path] = {}
    keyring_importers: list[str] = []
    unbounded: list[str] = []
    pending: list[tuple[str, str]] = []  # (importing module, imported name)

    def scan(label: str, source: str, package: str) -> None:
        names, dynamic = _imports(ast.parse(source), package)
        unbounded.extend(f"{label}:{item}" for item in dynamic)
        if any(name == "keyring" or name.startswith("keyring.") for name in names):
            keyring_importers.append(label)
        pending.extend((label, name) for name in names)

    for entry in entries:
        if entry.startswith("-c:"):
            scan("<program>", entry[3:], "")
        elif entry.endswith(".py"):
            scan(entry, (_ROOT / entry).read_text(encoding="utf-8"), "")
        else:
            pending.append(("<entry>", entry))
    while pending:
        _, name = pending.pop()
        parts = name.split(".")
        for index in range(1, len(parts) + 1):
            prefix = ".".join(parts[:index])
            path = _module_file(prefix)
            if path is None:
                break
            if prefix not in seen:
                seen[prefix] = path
                package = prefix if path.name == "__init__.py" else prefix.rpartition(".")[0]
                scan(prefix, path.read_text(encoding="utf-8"), package)
    return {"modules": sorted(seen), "keyring_importers": sorted(keyring_importers), "unbounded": sorted(unbounded)}
