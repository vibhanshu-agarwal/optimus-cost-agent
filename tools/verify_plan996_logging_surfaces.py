"""Verify Plan 9.96 diagnostic persistence and export-sink classifications."""

from __future__ import annotations

import argparse
import ast
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

_VALID_POLICIES = frozenset(
    {"shared-sanitize", "safe-by-construction", "protocol-only", "frozen-nonqualifying"}
)
_REQUIRED_ENTRY_FIELDS = frozenset({"key", "policy", "rationale", "sanitizer", "test_node", "evidence_tier"})


@dataclass(frozen=True)
class SurfaceAuditError(ValueError):
    code: str
    key: str = ""

    def __str__(self) -> str:
        return f"{self.code}: {self.key}" if self.key else self.code


def main(argv: list[str] | None = None) -> int:
    """Validate the checked-in surface audit against the current source tree."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="Path to the surface-audit JSON manifest")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    manifest_path = args.manifest.resolve()
    validate_manifest(discover_surfaces(project_root), load_manifest(manifest_path), project_root=project_root)
    print("Plan 9.96 logging-surface audit passed")
    return 0


def load_manifest(manifest_path: Path) -> list[Mapping[str, str]]:
    """Load the machine-readable surface classifications."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = payload.get("surfaces") if isinstance(payload, dict) else None
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        raise SurfaceAuditError(code="INVALID_MANIFEST_ENTRY")
    return entries


def discover_surfaces(project_root: Path) -> set[str]:
    """Return stable keys for persistence, export, and protocol sink calls."""
    surfaces: set[str] = set()
    for source_path in sorted((project_root / "src").rglob("*.py")):
        module = _module_name(project_root, source_path)
        surfaces.update(_discover_python_surfaces(module, source_path.read_text(encoding="utf-8")))
    tools_root = project_root / "tools"
    for source_path in sorted(tools_root.rglob("*.py")):
        module = _module_name(project_root, source_path)
        surfaces.update(_discover_python_surfaces(module, source_path.read_text(encoding="utf-8")))
    for source_path in sorted((*tools_root.rglob("*.sh"), *tools_root.rglob("*.ps1"))):
        module = _module_name(project_root, source_path)
        surfaces.update(_discover_script_surfaces(module, source_path.read_text(encoding="utf-8")))
    return surfaces


def validate_manifest(
    discovered: set[str], entries: Iterable[Mapping[str, str]], *, project_root: Path
) -> None:
    """Fail closed unless every discovered surface has one valid manifest entry."""
    entries_by_key: dict[str, Mapping[str, str]] = {}
    for entry in entries:
        missing = _REQUIRED_ENTRY_FIELDS.difference(entry)
        if missing:
            raise SurfaceAuditError(code="INVALID_MANIFEST_ENTRY")
        key = entry["key"]
        if key in entries_by_key:
            raise SurfaceAuditError(code="DUPLICATE_MANIFEST_KEY", key=key)
        if entry["policy"] not in _VALID_POLICIES:
            raise SurfaceAuditError(code="INVALID_MANIFEST_POLICY", key=key)
        if not _test_node_resolves(entry["test_node"], project_root):
            raise SurfaceAuditError(code="UNRESOLVED_TEST_NODE", key=key)
        entries_by_key[key] = entry

    stale = set(entries_by_key).difference(discovered)
    if stale:
        raise SurfaceAuditError(code="STALE_MANIFEST_ENTRY", key=sorted(stale)[0])
    unclassified = discovered.difference(entries_by_key)
    if unclassified:
        raise SurfaceAuditError(code="UNCLASSIFIED_SINK", key=sorted(unclassified)[0])


def _discover_python_surfaces(module: str, source: str) -> set[str]:
    tree = ast.parse(source)
    finder = _SurfaceFinder(module)
    finder.visit(tree)
    return finder.surfaces


def _discover_script_surfaces(module: str, source: str) -> set[str]:
    surfaces: set[str] = set()
    if ">" in source and ("acpx" in source or "transcript" in source):
        surfaces.add(f"{module}:script:raw_capture_write")
    if "echo " in source and ">&2" in source or "Write-Error" in source:
        surfaces.add(f"{module}:script:stderr_export")
    return surfaces


def _module_name(project_root: Path, source_path: Path) -> str:
    relative = source_path.relative_to(project_root).with_suffix("")
    return ".".join(relative.parts[1:]) if relative.parts[0] == "src" else ".".join(relative.parts)


def _test_node_resolves(test_node: str, project_root: Path) -> bool:
    path_text, separator, test_name = test_node.partition("::")
    if not separator or not path_text or not test_name:
        return False
    source_path = project_root / path_text
    if not source_path.is_file():
        return False
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    return any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == test_name for node in ast.walk(tree))


class _SurfaceFinder(ast.NodeVisitor):
    def __init__(self, module: str) -> None:
        self.module = module
        self.class_name = ""
        self.function_name = ""
        self.surfaces: set[str] = set()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        previous = self.class_name
        self.class_name = node.name
        self.generic_visit(node)
        self.class_name = previous

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous = self.function_name
        self.function_name = node.name
        self.generic_visit(node)
        self.function_name = previous

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        scope = f"{self.class_name}.{self.function_name}" if self.class_name else self.function_name
        if self.module == "optimus.telemetry.jsonl" and scope == "JsonlTelemetryWriter.append" and call_name.endswith("write"):
            self._add("jsonl_append")
        if call_name.endswith((".hset", ".hmset", ".rpush", ".lpush", ".set")):
            self._add("redis_hash_write")
        if call_name.endswith((".debug", ".info", ".warning", ".error", ".exception", ".critical")):
            self._add("logger_export")
        if call_name in {"str", "repr"} and _is_exception_named_argument(node):
            self._add("exception_export")
        if call_name == "JsonRpcError" and _has_exception_attribute_argument(node):
            self._add("structured_exception_export")
        if self.module == "optimus.acp.dispatcher" and scope == "JsonRpcDispatcher.dispatch" and call_name == "str":
            self._add("jsonrpc_error_response")
        if self.module == "optimus_gateway.responses" and self.function_name == "handle_responses_request" and call_name == "str":
            self._add("http_error_response")
        elif call_name == "print":
            self._add("stderr_export" if _has_file_stderr(node) else "stdout_export")
        elif call_name in {"open", "Path.open"} or call_name.endswith(".open"):
            self._add("file_open")
        elif call_name.endswith("write_text"):
            self._add("text_file_write")
        elif call_name.endswith("write"):
            self._add("text_write")
        elif call_name in {"json.dump", "json.dumps"}:
            self._add("json_serialization")
        self.generic_visit(node)

    def _add(self, sink_kind: str) -> None:
        if self.function_name:
            scope = f"{self.class_name}.{self.function_name}" if self.class_name else self.function_name
            self.surfaces.add(f"{self.module}:{scope}:{sink_kind}")


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _is_exception_named_argument(node: ast.Call) -> bool:
    return bool(node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in {"exc", "e", "err", "error"})


def _has_exception_attribute_argument(node: ast.Call) -> bool:
    """Detect structured exception fields flowing into a JSON-RPC error object."""
    return any(
        keyword.arg in {"message", "data", "detail"}
        and isinstance(keyword.value, ast.Attribute)
        and isinstance(keyword.value.value, ast.Name)
        and keyword.value.value.id in {"exc", "e", "err", "error"}
        and keyword.value.attr in {"message", "data", "detail"}
        for keyword in node.keywords
    )


def _has_file_stderr(node: ast.Call) -> bool:
    return any(
        keyword.arg == "file" and isinstance(keyword.value, ast.Attribute) and keyword.value.attr == "stderr"
        for keyword in node.keywords
    )


if __name__ == "__main__":
    raise SystemExit(main())
