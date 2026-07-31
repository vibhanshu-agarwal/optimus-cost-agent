"""AST import-boundary enforcement for portable evidence_handoff packages."""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

ALLOWED_EVIDENCE_IMPORT_ROOTS = frozenset({"PIL", "optimus_security"})
FORBIDDEN_EVIDENCE_IMPORT_ROOTS = frozenset({"optimus", "optimus_gateway", "tools"})

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_ROOT = REPO_ROOT / "src" / "evidence_handoff"
SECURITY_ROOT = REPO_ROOT / "src" / "optimus_security"


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _module_root(name: str | None) -> str | None:
    if not name:
        return None
    return name.split(".", 1)[0]


def _is_stdlib(root: str) -> bool:
    return root in sys.stdlib_module_names or root == "__future__"


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _module_root(alias.name)
                if root:
                    roots.add(root)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.module:
                # Relative import with module suffix — package-local; handled separately.
                continue
            if node.level and not node.module:
                continue
            root = _module_root(node.module)
            if root:
                roots.add(root)
    return roots


def _has_dynamic_import(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib" or alias.name.startswith("importlib."):
                    return True
        if isinstance(node, ast.ImportFrom) and node.module and (
            node.module == "importlib" or node.module.startswith("importlib.")
        ):
            return True
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "__import__":
                return True
            if isinstance(func, ast.Attribute) and func.attr in {"import_module", "__import__"}:
                return True
    return False


def _relative_import_escapes(tree: ast.AST, *, package_depth: int) -> bool:
    """Reject relative imports that climb above the portable package root."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            # package_depth counts segments under evidence_handoff inclusive of file module.
            # level > package_depth escapes the portable root.
            if node.level > package_depth:
                return True
            if node.module:
                root = _module_root(node.module)
                if root in FORBIDDEN_EVIDENCE_IMPORT_ROOTS:
                    return True
    return False


def _package_depth(path: Path, root: Path) -> int:
    relative = path.relative_to(root)
    # evidence_handoff / optional parents / module → depth from portable root.
    return len(relative.parts)


def test_allowed_and_forbidden_roots_are_enumerated_exactly() -> None:
    assert ALLOWED_EVIDENCE_IMPORT_ROOTS == frozenset({"PIL", "optimus_security"})
    assert FORBIDDEN_EVIDENCE_IMPORT_ROOTS == frozenset({"optimus", "optimus_gateway", "tools"})


def test_evidence_handoff_python_tree_exists_for_scanning() -> None:
    assert EVIDENCE_ROOT.is_dir()
    assert _python_files(EVIDENCE_ROOT), "portable package must contain Python modules"


def test_evidence_handoff_imports_only_stdlib_and_allowlisted_third_party() -> None:
    violations: list[str] = []
    for path in _python_files(EVIDENCE_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for root in _imported_roots(tree):
            if _is_stdlib(root):
                continue
            if root in ALLOWED_EVIDENCE_IMPORT_ROOTS:
                continue
            violations.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {root}")
    assert violations == []


def test_evidence_handoff_rejects_dynamic_imports() -> None:
    offenders: list[str] = []
    for path in _python_files(EVIDENCE_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _has_dynamic_import(tree):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []


def test_evidence_handoff_rejects_relative_imports_escaping_package() -> None:
    offenders: list[str] = []
    for path in _python_files(EVIDENCE_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _relative_import_escapes(tree, package_depth=_package_depth(path, EVIDENCE_ROOT)):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []


def test_optimus_security_remains_stdlib_only() -> None:
    violations: list[str] = []
    for path in _python_files(SECURITY_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for root in _imported_roots(tree):
            if _is_stdlib(root) or root == "optimus_security":
                continue
            violations.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {root}")
    assert violations == []


def test_stdlib_resolution_uses_sys_stdlib_module_names() -> None:
    assert "json" in sys.stdlib_module_names
    assert "pathlib" in sys.stdlib_module_names
    assert "PIL" not in sys.stdlib_module_names
    assert not _is_stdlib("PIL")
    assert _is_stdlib("json")


class _BlockDeployablesFinder:
    """Meta path finder that blocks deployable package imports."""

    def find_spec(self, fullname: str, path: object = None, target: object = None):  # noqa: ANN001
        root = fullname.split(".", 1)[0]
        if root in FORBIDDEN_EVIDENCE_IMPORT_ROOTS:
            raise ImportError(f"blocked deployable import: {fullname}")
        return None


def test_isolated_import_blocks_deployables_and_loads_models() -> None:
    # Unload portable modules and temporarily unload deployables so the blocker runs.
    portable = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name == "evidence_handoff" or name.startswith("evidence_handoff.")
    }
    deployables = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name == "optimus"
        or name.startswith("optimus.")
        or name == "optimus_gateway"
        or name.startswith("optimus_gateway.")
        or name == "tools"
        or name.startswith("tools.")
    }

    finder = _BlockDeployablesFinder()
    sys.meta_path.insert(0, finder)
    try:
        with pytest.raises(ImportError, match="blocked deployable import"):
            importlib.import_module("optimus")
        with pytest.raises(ImportError, match="blocked deployable import"):
            importlib.import_module("optimus_gateway")

        models = importlib.import_module("evidence_handoff.redaction.models")
        assert hasattr(models, "RedactionRequest")
        assert hasattr(models, "PathAliasRule")
    finally:
        sys.meta_path.remove(finder)
        sys.modules.update(deployables)
        sys.modules.update(portable)
