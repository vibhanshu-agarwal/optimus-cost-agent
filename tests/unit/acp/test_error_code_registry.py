from __future__ import annotations

import ast
import json
from pathlib import Path

from optimus.acp.errors import (
    ACP_PROTOCOL_ERROR_CODES,
    AUTHENTICATION_REQUIRED,
    DUPLICATE_REQUEST_ID,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    JSON_RPC_STANDARD_ERROR_CODES,
    METHOD_NOT_FOUND,
    MUTATION_FORBIDDEN,
    OPTIMUS_APPLICATION_ERROR_CODES,
    PARSE_ERROR,
    REQUEST_CANCELLED,
    RESOURCE_NOT_FOUND,
)
from tools.tracked_repository_files import tracked_repository_files

REPO_ROOT = Path(__file__).resolve().parents[3]
ACP_SCHEMA_PATH = REPO_ROOT / "tests/fixtures/acp/acp-v1-schema.json"

RESERVED_MIN, RESERVED_MAX = -32768, -32000


def schema_error_codes() -> frozenset[int]:
    schema = json.loads(ACP_SCHEMA_PATH.read_text(encoding="utf-8"))
    return frozenset(
        item["const"]
        for item in schema["$defs"]["ErrorCode"]["anyOf"]
        if isinstance(item.get("const"), int)
    )


def test_registry_is_unique_and_protocol_aligned() -> None:
    acp_codes = schema_error_codes()
    registry_values = (
        PARSE_ERROR,
        INVALID_REQUEST,
        METHOD_NOT_FOUND,
        INVALID_PARAMS,
        INTERNAL_ERROR,
        AUTHENTICATION_REQUIRED,
        REQUEST_CANCELLED,
        RESOURCE_NOT_FOUND,
        MUTATION_FORBIDDEN,
        DUPLICATE_REQUEST_ID,
    )

    assert len(registry_values) == len(set(registry_values))
    assert JSON_RPC_STANDARD_ERROR_CODES <= ACP_PROTOCOL_ERROR_CODES
    assert ACP_PROTOCOL_ERROR_CODES == acp_codes
    assert frozenset(registry_values) == acp_codes | OPTIMUS_APPLICATION_ERROR_CODES
    assert RESOURCE_NOT_FOUND == -32002
    assert -32910 not in acp_codes
    assert -32911 not in acp_codes
    assert OPTIMUS_APPLICATION_ERROR_CODES.isdisjoint(acp_codes)
    assert all(not (RESERVED_MIN <= code <= RESERVED_MAX) for code in OPTIMUS_APPLICATION_ERROR_CODES)
    assert MUTATION_FORBIDDEN == -32910
    assert DUPLICATE_REQUEST_ID == -32911
    assert OPTIMUS_APPLICATION_ERROR_CODES == frozenset({MUTATION_FORBIDDEN, DUPLICATE_REQUEST_ID})


EXPECTED_LEGACY_ERROR_CODE_SITES: frozenset[tuple[str, str]] = frozenset()
REGISTRY_RELATIVE = "src/optimus/acp/errors.py"


def signed_int(node: ast.expr) -> int | None:
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and type(node.operand.value) is int
    ):
        return -node.operand.value
    return None


def _is_error_code_like(value: int) -> bool:
    if value >= 0:
        return False
    return RESERVED_MIN <= value <= RESERVED_MAX or value in OPTIMUS_APPLICATION_ERROR_CODES


def _target_symbol(target: ast.expr, enclosing: str) -> str:
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return enclosing


class _ErrorCodeLiteralVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.sites: set[tuple[str, str]] = set()
        self._classes: list[str] = []
        self._functions: list[str] = []
        self.relative_path = ""

    def _enclosing(self) -> str:
        if self._functions:
            return self._functions[-1]
        if self._classes:
            return self._classes[-1]
        return "<module>"

    def _record(self, symbol: str) -> None:
        self.sites.add((self.relative_path, symbol))

    def _maybe_record_value(self, value: ast.expr | None, symbol: str) -> None:
        if value is None:
            return
        parsed = signed_int(value)
        if parsed is not None and _is_error_code_like(parsed):
            self._record(symbol)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._classes.append(node.name)
        self.generic_visit(node)
        self._classes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._functions.append(node.name)
        self.generic_visit(node)
        self._functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node: ast.Assign) -> None:
        parsed = signed_int(node.value)
        if parsed is not None and _is_error_code_like(parsed):
            for target in node.targets:
                self._record(_target_symbol(target, self._enclosing()))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._maybe_record_value(node.value, _target_symbol(node.target, self._enclosing()))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        for keyword in node.keywords:
            if keyword.arg == "code":
                self._maybe_record_value(keyword.value, self._enclosing())
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        if func_name in {"JsonRpcError", "AcpOutboundError"} and node.args:
            self._maybe_record_value(node.args[0], self._enclosing())
        self.generic_visit(node)


def find_non_registry_error_code_literals(source_root: Path) -> frozenset[tuple[str, str]]:
    sites: set[tuple[str, str]] = set()
    pathspec = source_root.relative_to(REPO_ROOT).as_posix()
    for path in tracked_repository_files(REPO_ROOT, pathspecs=(pathspec,)):
        if path.suffix != ".py":
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative == REGISTRY_RELATIVE:
            continue
        visitor = _ErrorCodeLiteralVisitor()
        visitor.relative_path = relative
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        sites.update(visitor.sites)
    return frozenset(sites)


def test_production_raw_error_code_allowlist_is_exact_and_empty() -> None:
    actual = find_non_registry_error_code_literals(REPO_ROOT / "src")
    assert actual == EXPECTED_LEGACY_ERROR_CODE_SITES
    assert EXPECTED_LEGACY_ERROR_CODE_SITES == frozenset()
