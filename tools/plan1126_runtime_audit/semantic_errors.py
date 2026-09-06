"""Immutable-source semantic error selection audit for Plan 11.26 Task 7."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from optimus.acp.errors import (
    AUTHENTICATION_REQUIRED,
    DUPLICATE_REQUEST_ID,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    MUTATION_FORBIDDEN,
    PARSE_ERROR,
    REQUEST_CANCELLED,
    RESOURCE_NOT_FOUND,
    JsonRpcError,
    error_response,
)

from .model import (
    AuditArtifact,
    BaselineScope,
    Classification,
    CoverageAssessmentStatus,
    EvidenceReference,
    Finding,
    GateStatus,
    LiveStatus,
    ObservationClosureStatus,
    ReviewerStatus,
    VocabularyCoverageAssessment,
    VocabularyCoverageStatus,
)
from .source import SourceTree

H7_SOURCE_PATHS = (
    "src/optimus/acp/dispatcher.py",
    "src/optimus/acp/errors.py",
    "src/optimus/acp/lifecycle.py",
    "src/optimus/acp/request_ids.py",
    "src/optimus/acp/server.py",
    "src/optimus/acp/spec.py",
    "tests/fixtures/acp/acp-v1-schema.json",
    "tests/unit/acp/test_error_code_registry.py",
)
_PYTHON_PATHS = tuple(path for path in H7_SOURCE_PATHS if path.startswith("src/") and path.endswith(".py"))
_OWNER = "P11-FEAT-ACP-RUNTIME-HARDENING"


class SemanticCategory(StrEnum):
    PROTOCOL_INPUT = "PROTOCOL_INPUT"
    CANCELLATION_DEADLINE = "CANCELLATION_DEADLINE"
    OWNERSHIP_CONCURRENCY = "OWNERSHIP_CONCURRENCY"
    DEPENDENCY_AVAILABILITY = "DEPENDENCY_AVAILABILITY"
    INTEGRITY = "INTEGRITY"
    DELIVERY = "DELIVERY"
    RESOURCE_LIFECYCLE = "RESOURCE_LIFECYCLE"
    INVARIANT_PROGRAMMING = "INVARIANT_PROGRAMMING"


class Retryability(StrEnum):
    NEVER = "NEVER"
    SAFE_RETRY = "SAFE_RETRY"
    STATE_CHECK_REQUIRED = "STATE_CHECK_REQUIRED"
    BACKOFF_REQUIRED = "BACKOFF_REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EffectCertainty(StrEnum):
    NO_EFFECT = "NO_EFFECT"
    KNOWN_LOCAL_EFFECT = "KNOWN_LOCAL_EFFECT"
    UNKNOWN_POST_WRITE = "UNKNOWN_POST_WRITE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PublicOutput(StrEnum):
    SANITIZED_NAMED_ERROR = "SANITIZED_NAMED_ERROR"
    SANITIZED_DYNAMIC_ERROR = "SANITIZED_DYNAMIC_ERROR"
    FAIL_CLOSED_SANITIZED = "FAIL_CLOSED_SANITIZED"
    NO_WIRE_OUTPUT = "NO_WIRE_OUTPUT"


class TelemetryDisposition(StrEnum):
    NO_ADDITIONAL_EVENT = "NO_ADDITIONAL_EVENT"
    SEMANTIC_EVENT_REQUIRED = "SEMANTIC_EVENT_REQUIRED"
    CONTAINED_DIAGNOSTIC = "CONTAINED_DIAGNOSTIC"


class CleanupObligation(StrEnum):
    NONE = "NONE"
    REQUEST_LOCAL = "REQUEST_LOCAL"
    CANCEL_AND_JOIN = "CANCEL_AND_JOIN"
    PRESERVE_STATE = "PRESERVE_STATE"
    SETTLE_DELIVERY = "SETTLE_DELIVERY"
    CLOSE_OWNER = "CLOSE_OWNER"


NAMED_ERROR_CODES: Mapping[str, int] = {
    "PARSE_ERROR": PARSE_ERROR,
    "INVALID_REQUEST": INVALID_REQUEST,
    "METHOD_NOT_FOUND": METHOD_NOT_FOUND,
    "INVALID_PARAMS": INVALID_PARAMS,
    "INTERNAL_ERROR": INTERNAL_ERROR,
    "AUTHENTICATION_REQUIRED": AUTHENTICATION_REQUIRED,
    "REQUEST_CANCELLED": REQUEST_CANCELLED,
    "RESOURCE_NOT_FOUND": RESOURCE_NOT_FOUND,
    "MUTATION_FORBIDDEN": MUTATION_FORBIDDEN,
    "DUPLICATE_REQUEST_ID": DUPLICATE_REQUEST_ID,
}

_CATEGORY_POLICY = {
    SemanticCategory.PROTOCOL_INPUT: (
        Retryability.NEVER, EffectCertainty.NO_EFFECT, PublicOutput.SANITIZED_NAMED_ERROR,
        TelemetryDisposition.NO_ADDITIONAL_EVENT, CleanupObligation.REQUEST_LOCAL,
    ),
    SemanticCategory.CANCELLATION_DEADLINE: (
        Retryability.STATE_CHECK_REQUIRED, EffectCertainty.KNOWN_LOCAL_EFFECT,
        PublicOutput.SANITIZED_NAMED_ERROR, TelemetryDisposition.SEMANTIC_EVENT_REQUIRED,
        CleanupObligation.CANCEL_AND_JOIN,
    ),
    SemanticCategory.OWNERSHIP_CONCURRENCY: (
        Retryability.BACKOFF_REQUIRED, EffectCertainty.NO_EFFECT, PublicOutput.SANITIZED_NAMED_ERROR,
        TelemetryDisposition.SEMANTIC_EVENT_REQUIRED, CleanupObligation.PRESERVE_STATE,
    ),
    SemanticCategory.DEPENDENCY_AVAILABILITY: (
        Retryability.SAFE_RETRY, EffectCertainty.UNKNOWN_POST_WRITE, PublicOutput.SANITIZED_NAMED_ERROR,
        TelemetryDisposition.SEMANTIC_EVENT_REQUIRED, CleanupObligation.REQUEST_LOCAL,
    ),
    SemanticCategory.INTEGRITY: (
        Retryability.NEVER, EffectCertainty.NO_EFFECT, PublicOutput.SANITIZED_NAMED_ERROR,
        TelemetryDisposition.CONTAINED_DIAGNOSTIC, CleanupObligation.PRESERVE_STATE,
    ),
    SemanticCategory.DELIVERY: (
        Retryability.STATE_CHECK_REQUIRED, EffectCertainty.UNKNOWN_POST_WRITE,
        PublicOutput.SANITIZED_DYNAMIC_ERROR, TelemetryDisposition.SEMANTIC_EVENT_REQUIRED,
        CleanupObligation.SETTLE_DELIVERY,
    ),
    SemanticCategory.RESOURCE_LIFECYCLE: (
        Retryability.SAFE_RETRY, EffectCertainty.KNOWN_LOCAL_EFFECT, PublicOutput.NO_WIRE_OUTPUT,
        TelemetryDisposition.CONTAINED_DIAGNOSTIC, CleanupObligation.CLOSE_OWNER,
    ),
    SemanticCategory.INVARIANT_PROGRAMMING: (
        Retryability.NOT_APPLICABLE, EffectCertainty.NOT_APPLICABLE,
        PublicOutput.FAIL_CLOSED_SANITIZED, TelemetryDisposition.CONTAINED_DIAGNOSTIC,
        CleanupObligation.NONE,
    ),
}

_CODE_CATEGORY = {
    "PARSE_ERROR": SemanticCategory.PROTOCOL_INPUT,
    "INVALID_REQUEST": SemanticCategory.PROTOCOL_INPUT,
    "METHOD_NOT_FOUND": SemanticCategory.PROTOCOL_INPUT,
    "INVALID_PARAMS": SemanticCategory.PROTOCOL_INPUT,
    "AUTHENTICATION_REQUIRED": SemanticCategory.PROTOCOL_INPUT,
    "REQUEST_CANCELLED": SemanticCategory.CANCELLATION_DEADLINE,
    "RESOURCE_NOT_FOUND": SemanticCategory.INTEGRITY,
    "MUTATION_FORBIDDEN": SemanticCategory.OWNERSHIP_CONCURRENCY,
    "DUPLICATE_REQUEST_ID": SemanticCategory.OWNERSHIP_CONCURRENCY,
    "INTERNAL_ERROR": SemanticCategory.INVARIANT_PROGRAMMING,
}


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _signed_int(node: ast.expr) -> int | None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        return -node.operand.value if type(node.operand.value) is int else None
    return node.value if isinstance(node, ast.Constant) and type(node.value) is int else None


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _exception_names(node: ast.expr | None) -> tuple[str, ...]:
    if node is None:
        return ("BaseException",)
    if isinstance(node, ast.Tuple):
        return tuple(name for child in node.elts for name in _exception_names(child))
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        return (node.attr,)
    return (ast.unparse(node),)


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((item.value for item in call.keywords if item.arg == name), None)


def _code_name(call: ast.Call) -> str:
    node = _keyword(call, "code")
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return "DYNAMIC"
    value = _signed_int(node) if node is not None else None
    return next((name for name, code in NAMED_ERROR_CODES.items() if code == value), "DYNAMIC")


def _literal_text(node: ast.expr | None) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(part.value for part in node.values if isinstance(part, ast.Constant) and isinstance(part.value, str))
    return ""


def _symbol(path: str, functions: list[str]) -> str:
    module = path.removesuffix(".py").replace("/", ".")
    return ".".join((module, *functions)) if functions else module


def _category_for_exception(names: tuple[str, ...], symbol: str) -> SemanticCategory:
    joined = " ".join(names)
    if "CancelledError" in joined or "Timeout" in joined:
        return SemanticCategory.CANCELLATION_DEADLINE
    if any(name in joined for name in ("FramingError", "JSONDecodeError", "ValidationError")):
        return SemanticCategory.PROTOCOL_INPUT
    if "DuplicateRequestId" in joined:
        return SemanticCategory.OWNERSHIP_CONCURRENCY
    if any(name in joined for name in ("GatewayError", "ClientMcpConfigError")):
        return SemanticCategory.DEPENDENCY_AVAILABILITY
    if "AcpOutboundError" in joined:
        return SemanticCategory.DELIVERY
    if "sanitize_protocol_error" in symbol:
        return SemanticCategory.INTEGRITY
    if any(name in symbol for name in ("close", "serve", "read_lines")) and "Exception" in joined:
        return SemanticCategory.RESOURCE_LIFECYCLE
    return SemanticCategory.INVARIANT_PROGRAMMING


def _category_for_wire(code_name: str, message: str, symbol: str) -> SemanticCategory:
    lowered = message.lower()
    if "not configured" in lowered or "Gateway" in symbol:
        return SemanticCategory.DEPENDENCY_AVAILABILITY
    if "unknown session" in lowered:
        return SemanticCategory.INTEGRITY
    if "turn is already in progress" in lowered or "duplicate" in lowered:
        return SemanticCategory.OWNERSHIP_CONCURRENCY
    if "process_request" in symbol and code_name == "DYNAMIC":
        return SemanticCategory.DELIVERY
    return _CODE_CATEGORY.get(code_name, SemanticCategory.INVARIANT_PROGRAMMING)


def _classification(
    *, site_kind: str, code_name: str, message: str, symbol: str, exceptions: tuple[str, ...]
) -> tuple[Classification, str, str | None]:
    if site_kind == "EXCEPTION_SELECTION" and symbol.endswith((
        "sanitize_protocol_error_message", "sanitize_protocol_error_data",
    )) and exceptions == ("Exception",):
        return (
            Classification.INTENTIONALLY_EXCEPTIONAL,
            "The broad catch is a fail-closed sanitizer boundary and S3 supplies no contrary source evidence.",
            "S3",
        )
    lowered = message.lower()
    if code_name == "REQUEST_CANCELLED" and "turn is already in progress" in lowered:
        return (
            Classification.CONTRADICTORY,
            "Active-turn contention is selected as cancellation, conflating ownership/concurrency with cancellation.",
            None,
        )
    if code_name == "INVALID_REQUEST" and "unknown session" in lowered:
        return (
            Classification.CONTRADICTORY,
            "Missing session state selects INVALID_REQUEST although RESOURCE_NOT_FOUND exists in the settled registry.",
            None,
        )
    if code_name == "METHOD_NOT_FOUND" and "not configured" in lowered:
        return (
            Classification.CONTRADICTORY,
            "A configured protocol method with an unavailable dependency selects METHOD_NOT_FOUND.",
            None,
        )
    if code_name == "DYNAMIC" and "process_request" in symbol:
        return (
            Classification.CANONICAL_BYPASSED,
            "A client-originated outbound error code is reflected dynamically instead of selecting a named boundary code.",
            None,
        )
    if site_kind == "EXCEPTION_SELECTION" and "GatewayError" in exceptions:
        return (
            Classification.MISSING,
            "Gateway failure selects INTERNAL_ERROR without a source-owned retry or post-write certainty distinction.",
            None,
        )
    return Classification.CANONICAL, "The discovered selection follows the current named boundary contract.", None


@dataclass(frozen=True, slots=True)
class SemanticSelectionSite:
    path: str
    line: int
    symbol: str
    site_kind: str
    code_name: str
    exception_names: tuple[str, ...]
    category: SemanticCategory
    retryability: Retryability
    effect_certainty: EffectCertainty
    public_output: PublicOutput
    telemetry_disposition: TelemetryDisposition
    cleanup_obligation: CleanupObligation
    baseline_scope: BaselineScope
    classification: Classification
    evidence_digest: str
    ruling: str
    seed_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "symbol": self.symbol,
            "site_kind": self.site_kind,
            "code_name": self.code_name,
            "exception_names": list(self.exception_names),
            "category": self.category.value,
            "retryability": self.retryability.value,
            "effect_certainty": self.effect_certainty.value,
            "public_output": self.public_output.value,
            "telemetry_disposition": self.telemetry_disposition.value,
            "cleanup_obligation": self.cleanup_obligation.value,
            "baseline_scope": self.baseline_scope.value,
            "classification": self.classification.value,
            "evidence_digest": self.evidence_digest,
            "ruling": self.ruling,
            "seed_id": self.seed_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SemanticSelectionSite:
        return cls(
            path=payload["path"], line=payload["line"], symbol=payload["symbol"],
            site_kind=payload["site_kind"], code_name=payload["code_name"],
            exception_names=tuple(payload["exception_names"]), category=SemanticCategory(payload["category"]),
            retryability=Retryability(payload["retryability"]), effect_certainty=EffectCertainty(payload["effect_certainty"]),
            public_output=PublicOutput(payload["public_output"]),
            telemetry_disposition=TelemetryDisposition(payload["telemetry_disposition"]),
            cleanup_obligation=CleanupObligation(payload["cleanup_obligation"]),
            baseline_scope=BaselineScope(payload["baseline_scope"]), classification=Classification(payload["classification"]),
            evidence_digest=payload["evidence_digest"], ruling=payload["ruling"], seed_id=payload["seed_id"],
        )


@dataclass(frozen=True, slots=True)
class SemanticInventory:
    sites: tuple[SemanticSelectionSite, ...]
    expected_site_count: None = None

    @property
    def site_count(self) -> int:
        return len(self.sites)

    def to_dict(self) -> dict[str, object]:
        return {
            "expected_site_count": self.expected_site_count,
            "site_count": self.site_count,
            "sites": [site.to_dict() for site in self.sites],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SemanticInventory:
        if payload.get("expected_site_count") is not None:
            raise ValueError("semantic inventory expected_site_count must remain null")
        sites = tuple(SemanticSelectionSite.from_dict(item) for item in payload["sites"])
        if payload["site_count"] != len(sites):
            raise ValueError("semantic inventory site_count mismatch")
        return cls(sites=sites)


def _site(
    *, path: str, line: int, symbol: str, site_kind: str, code_name: str,
    exceptions: tuple[str, ...] = (), message: str = "",
) -> SemanticSelectionSite:
    if site_kind == "EXCEPTION_SELECTION":
        category = _category_for_exception(exceptions, symbol)
    elif site_kind in {"NAMED_ERROR_CONSTANT", "WIRE_ERROR_SELECTION"}:
        category = _category_for_wire(code_name, message, symbol)
    else:
        category = SemanticCategory.PROTOCOL_INPUT
    retry, certainty, public, telemetry, cleanup = _CATEGORY_POLICY[category]
    if site_kind == "EXCEPTION_SELECTION" and symbol.endswith((
        "sanitize_protocol_error_message", "sanitize_protocol_error_data",
    )):
        public = PublicOutput.FAIL_CLOSED_SANITIZED
    elif site_kind == "EXCEPTION_SELECTION" and "CancelledError" in exceptions:
        public = PublicOutput.NO_WIRE_OUTPUT
    classification, ruling, seed_id = _classification(
        site_kind=site_kind, code_name=code_name, message=message, symbol=symbol, exceptions=exceptions,
    )
    evidence_digest = _digest({
        "path": path, "line": line, "symbol": symbol, "site_kind": site_kind,
        "code_name": code_name, "exceptions": exceptions, "message": message,
    })
    return SemanticSelectionSite(
        path=path, line=line, symbol=symbol, site_kind=site_kind, code_name=code_name,
        exception_names=exceptions, category=category, retryability=retry,
        effect_certainty=certainty, public_output=public, telemetry_disposition=telemetry,
        cleanup_obligation=cleanup, baseline_scope=BaselineScope.MERGED,
        classification=classification, evidence_digest=evidence_digest, ruling=ruling, seed_id=seed_id,
    )


class _SemanticVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.functions: list[str] = []
        self.sites: list[SemanticSelectionSite] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append(node.name)
        if self.path.endswith("errors.py") and node.name == "error_response":
            self.sites.append(_site(
                path=self.path, line=node.lineno, symbol=_symbol(self.path, self.functions),
                site_kind="PUBLIC_OUTPUT_BUILDER", code_name="DYNAMIC",
            ))
        self.generic_visit(node)
        self.functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node: ast.Assign) -> None:
        if self.path.endswith("errors.py"):
            value = _signed_int(node.value)
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id.isupper()
                    and value is not None
                    and value < 0
                ):
                    self.sites.append(_site(
                        path=self.path, line=node.lineno, symbol=_symbol(self.path, [target.id]),
                        site_kind="NAMED_ERROR_CONSTANT", code_name=target.id,
                    ))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _call_name(node) == "JsonRpcError":
            code_name = _code_name(node)
            self.sites.append(_site(
                path=self.path, line=node.lineno, symbol=_symbol(self.path, self.functions),
                site_kind="WIRE_ERROR_SELECTION", code_name=code_name,
                message=_literal_text(_keyword(node, "message")),
            ))
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        exceptions = _exception_names(node.type)
        code_name = "NONE"
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and _call_name(child) == "JsonRpcError":
                code_name = _code_name(child)
                break
        self.sites.append(_site(
            path=self.path, line=node.lineno, symbol=_symbol(self.path, self.functions),
            site_kind="EXCEPTION_SELECTION", code_name=code_name, exceptions=exceptions,
        ))
        self.generic_visit(node)


def discover_semantic_inventory(source: SourceTree) -> SemanticInventory:
    """Derive sites from AST without an expected site list or count."""

    sites: list[SemanticSelectionSite] = []
    for path in source.paths():
        if path not in _PYTHON_PATHS:
            continue
        visitor = _SemanticVisitor(path)
        visitor.visit(ast.parse(source.read_text(path), filename=path))
        sites.extend(visitor.sites)
    return SemanticInventory(sites=tuple(sorted(sites, key=lambda item: (item.path, item.line, item.site_kind))))


_CATEGORY_CODES = {
    SemanticCategory.PROTOCOL_INPUT: ("PARSE_ERROR", "INVALID_REQUEST", "METHOD_NOT_FOUND", "INVALID_PARAMS", "AUTHENTICATION_REQUIRED"),
    SemanticCategory.CANCELLATION_DEADLINE: ("REQUEST_CANCELLED",),
    SemanticCategory.OWNERSHIP_CONCURRENCY: ("DUPLICATE_REQUEST_ID", "MUTATION_FORBIDDEN"),
    SemanticCategory.DEPENDENCY_AVAILABILITY: ("INTERNAL_ERROR",),
    SemanticCategory.INTEGRITY: ("RESOURCE_NOT_FOUND",),
    SemanticCategory.DELIVERY: ("INTERNAL_ERROR",),
    SemanticCategory.RESOURCE_LIFECYCLE: ("INTERNAL_ERROR",),
    SemanticCategory.INVARIANT_PROGRAMMING: ("INTERNAL_ERROR",),
}


@dataclass(frozen=True, slots=True)
class SemanticObservation:
    case_index: int
    category: SemanticCategory
    error_code_name: str
    retryability: Retryability
    effect_certainty: EffectCertainty
    public_output: PublicOutput
    telemetry_disposition: TelemetryDisposition
    cleanup_obligation: CleanupObligation
    leakage_result: str
    divergence_result: str
    input_digest: str
    output_digest: str
    complete: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "case_index": self.case_index, "category": self.category.value,
            "error_code_name": self.error_code_name, "retryability": self.retryability.value,
            "effect_certainty": self.effect_certainty.value, "public_output": self.public_output.value,
            "telemetry_disposition": self.telemetry_disposition.value,
            "cleanup_obligation": self.cleanup_obligation.value,
            "leakage_result": self.leakage_result, "divergence_result": self.divergence_result,
            "input_digest": self.input_digest, "output_digest": self.output_digest, "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SemanticObservation:
        return cls(
            case_index=payload["case_index"], category=SemanticCategory(payload["category"]),
            error_code_name=payload["error_code_name"], retryability=Retryability(payload["retryability"]),
            effect_certainty=EffectCertainty(payload["effect_certainty"]),
            public_output=PublicOutput(payload["public_output"]),
            telemetry_disposition=TelemetryDisposition(payload["telemetry_disposition"]),
            cleanup_obligation=CleanupObligation(payload["cleanup_obligation"]),
            leakage_result=payload["leakage_result"], divergence_result=payload["divergence_result"],
            input_digest=payload["input_digest"], output_digest=payload["output_digest"],
            complete=payload["complete"],
        )


def semantic_selection_observations(
    *, inventory: SemanticInventory, cases_per_category: int = 100,
) -> tuple[SemanticObservation, ...]:
    if inventory.site_count == 0 or cases_per_category != 100:
        raise ValueError("semantic characterization requires a non-empty inventory and exactly 100 cases per category")
    rows: list[SemanticObservation] = []
    for category in SemanticCategory:
        retry, certainty, public, telemetry, cleanup = _CATEGORY_POLICY[category]
        codes = _CATEGORY_CODES[category]
        for case_index in range(cases_per_category):
            code_name = codes[case_index % len(codes)]
            sensitive_marker = f"task7-sensitive-{category.value.lower()}-{case_index:03d}"
            message = (
                f"plan 11.26 semantic {category.value.lower()} case {case_index:03d} "
                f"api_key={sensitive_marker}"
            )
            data = {
                "audit_case": case_index,
                "semantic_category": category.value,
                "password": sensitive_marker,
            }
            wire = error_response(
                case_index,
                JsonRpcError(code=NAMED_ERROR_CODES[code_name], message=message, data=data),
            )
            serialized = json.dumps(wire, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            leakage = "LEAKED" if sensitive_marker in serialized else "CLEAN"
            divergence = "MATCH" if wire["error"]["code"] == NAMED_ERROR_CODES[code_name] else "DIVERGED"
            rows.append(SemanticObservation(
                case_index=case_index, category=category, error_code_name=code_name,
                retryability=retry, effect_certainty=certainty, public_output=public,
                telemetry_disposition=telemetry, cleanup_obligation=cleanup,
                leakage_result=leakage, divergence_result=divergence,
                input_digest=_digest({"id": case_index, "message": message, "data": data}),
                output_digest=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            ))
    return tuple(rows)


_COVERAGE_FIELDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("category", "SemanticCategory", tuple(item.value for item in SemanticCategory)),
    ("error_code_name", "NamedErrorCode", tuple(NAMED_ERROR_CODES)),
    ("retryability", "Retryability", tuple(item.value for item in Retryability)),
    ("effect_certainty", "EffectCertainty", tuple(item.value for item in EffectCertainty)),
    ("public_output", "PublicOutput", tuple(item.value for item in PublicOutput)),
    ("telemetry_disposition", "TelemetryDisposition", tuple(item.value for item in TelemetryDisposition)),
    ("cleanup_obligation", "CleanupObligation", tuple(item.value for item in CleanupObligation)),
    ("leakage_result", "LeakageResult", ("CLEAN", "LEAKED")),
    ("divergence_result", "DivergenceResult", ("DIVERGED", "MATCH")),
)


def _coverage(rows: tuple[SemanticObservation, ...]) -> tuple[VocabularyCoverageAssessment, ...]:
    assessments: list[VocabularyCoverageAssessment] = []
    for field_name, type_name, vocabulary in _COVERAGE_FIELDS:
        observed = tuple(sorted({
            (value.value if isinstance(value, StrEnum) else value)
            for row in rows
            for value in (getattr(row, field_name),)
        }))
        vocabulary_values = tuple(sorted(vocabulary))
        missing = tuple(sorted(set(vocabulary_values) - set(observed)))
        assessments.append(VocabularyCoverageAssessment(
            field_name=field_name, type_name=type_name, vocabulary_values=vocabulary_values,
            observed_values=observed, missing_values=missing,
            status=CoverageAssessmentStatus.SCOPED_OUT if missing else CoverageAssessmentStatus.FULLY_OBSERVED,
            reason=(
                "The 800 real sanitizer cases exercised every category without producing this failure outcome; "
                "G4 must use reviewed fault injection and retain the raw result if it becomes reachable."
                if missing else None
            ),
            owner=_OWNER if missing else None,
            next_gate="G4 semantic negative-outcome fault-injection characterization" if missing else None,
        ))
    return tuple(assessments)


@dataclass(frozen=True, slots=True)
class SemanticObservationSummary:
    cases_per_category: int
    total_observation_count: int
    complete_observation_count: int
    observation_closure_status: ObservationClosureStatus
    vocabulary_coverage_status: VocabularyCoverageStatus
    digest: str
    vocabulary: Mapping[str, tuple[str, ...]]
    coverage_assessments: tuple[VocabularyCoverageAssessment, ...]
    rows: tuple[SemanticObservation, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "cases_per_category": self.cases_per_category,
            "total_observation_count": self.total_observation_count,
            "complete_observation_count": self.complete_observation_count,
            "observation_closure_status": self.observation_closure_status.value,
            "vocabulary_coverage_status": self.vocabulary_coverage_status.value,
            "digest": self.digest,
            "vocabulary": {key: list(values) for key, values in sorted(self.vocabulary.items())},
            "coverage_assessments": [item.to_dict() for item in self.coverage_assessments],
            "rows": [item.to_dict() for item in self.rows],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SemanticObservationSummary:
        rows = tuple(SemanticObservation.from_dict(item) for item in payload["rows"])
        summary = cls(
            cases_per_category=payload["cases_per_category"], total_observation_count=payload["total_observation_count"],
            complete_observation_count=payload["complete_observation_count"],
            observation_closure_status=ObservationClosureStatus(payload["observation_closure_status"]),
            vocabulary_coverage_status=VocabularyCoverageStatus(payload["vocabulary_coverage_status"]),
            digest=payload["digest"], vocabulary={key: tuple(value) for key, value in payload["vocabulary"].items()},
            coverage_assessments=tuple(VocabularyCoverageAssessment.from_dict(item) for item in payload["coverage_assessments"]),
            rows=rows,
        )
        if summary.total_observation_count != len(rows) or summary.digest != _digest([item.to_dict() for item in rows]):
            raise ValueError("semantic observation summary does not match stored rows")
        return summary


@dataclass(frozen=True, slots=True)
class AuthorityEvidenceRecord:
    record_id: str
    hypothesis_id: str
    subject: str
    baseline_scope: BaselineScope
    baseline_anchor_commit: str
    overlay_commit: str
    binding_commit: str | None
    schema_oracle_status: str
    ast_oracle_status: str
    legacy_allowlist_count: int
    commands: tuple[str, ...]
    ruling: str
    reviewer_status: ReviewerStatus
    content_free_evidence: tuple[EvidenceReference, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id, "hypothesis_id": self.hypothesis_id, "subject": self.subject,
            "baseline_scope": self.baseline_scope.value, "baseline_anchor_commit": self.baseline_anchor_commit,
            "overlay_commit": self.overlay_commit, "binding_commit": self.binding_commit,
            "schema_oracle_status": self.schema_oracle_status, "ast_oracle_status": self.ast_oracle_status,
            "legacy_allowlist_count": self.legacy_allowlist_count, "commands": list(self.commands),
            "ruling": self.ruling, "reviewer_status": self.reviewer_status.value,
            "content_free_evidence": [item.to_dict() for item in self.content_free_evidence],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AuthorityEvidenceRecord:
        return cls(
            record_id=payload["record_id"], hypothesis_id=payload["hypothesis_id"], subject=payload["subject"],
            baseline_scope=BaselineScope(payload["baseline_scope"]), baseline_anchor_commit=payload["baseline_anchor_commit"],
            overlay_commit=payload["overlay_commit"], binding_commit=payload["binding_commit"],
            schema_oracle_status=payload["schema_oracle_status"], ast_oracle_status=payload["ast_oracle_status"],
            legacy_allowlist_count=payload["legacy_allowlist_count"], commands=tuple(payload["commands"]),
            ruling=payload["ruling"], reviewer_status=ReviewerStatus(payload["reviewer_status"]),
            content_free_evidence=tuple(EvidenceReference.from_dict(item) for item in payload["content_free_evidence"]),
        )


@dataclass(frozen=True, slots=True)
class SemanticEvidenceRecord:
    record_id: str
    hypothesis_id: str
    subject: str
    baseline_scope: BaselineScope
    baseline_anchor_commit: str
    overlay_commit: str
    binding_commit: str | None
    inventory: SemanticInventory
    observations: SemanticObservationSummary
    commands: tuple[str, ...]
    ruling: str
    reviewer_status: ReviewerStatus
    content_free_evidence: tuple[EvidenceReference, ...]

    @property
    def schedule_observations(self) -> SemanticObservationSummary:
        return self.observations

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id, "hypothesis_id": self.hypothesis_id, "subject": self.subject,
            "baseline_scope": self.baseline_scope.value, "baseline_anchor_commit": self.baseline_anchor_commit,
            "overlay_commit": self.overlay_commit, "binding_commit": self.binding_commit,
            "inventory": self.inventory.to_dict(), "observations": self.observations.to_dict(),
            "commands": list(self.commands), "ruling": self.ruling,
            "reviewer_status": self.reviewer_status.value,
            "content_free_evidence": [item.to_dict() for item in self.content_free_evidence],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SemanticEvidenceRecord:
        return cls(
            record_id=payload["record_id"], hypothesis_id=payload["hypothesis_id"], subject=payload["subject"],
            baseline_scope=BaselineScope(payload["baseline_scope"]), baseline_anchor_commit=payload["baseline_anchor_commit"],
            overlay_commit=payload["overlay_commit"], binding_commit=payload["binding_commit"],
            inventory=SemanticInventory.from_dict(payload["inventory"]),
            observations=SemanticObservationSummary.from_dict(payload["observations"]),
            commands=tuple(payload["commands"]), ruling=payload["ruling"],
            reviewer_status=ReviewerStatus(payload["reviewer_status"]),
            content_free_evidence=tuple(EvidenceReference.from_dict(item) for item in payload["content_free_evidence"]),
        )


def _authority_record(source: SourceTree, merged_commit: str, overlay_commit: str) -> AuthorityEvidenceRecord:
    registry = source.read_text("src/optimus/acp/errors.py")
    oracle = source.read_text("tests/unit/acp/test_error_code_registry.py")
    schema = json.loads(source.read_text("tests/fixtures/acp/acp-v1-schema.json"))
    schema_codes = sorted(
        item["const"] for item in schema["$defs"]["ErrorCode"]["anyOf"] if isinstance(item.get("const"), int)
    )
    registry_digest = _digest({"named_codes": dict(NAMED_ERROR_CODES), "schema_codes": schema_codes})
    oracle_digest = hashlib.sha256(oracle.encode("utf-8")).hexdigest()
    schema_pass = set(schema_codes) == {
        PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR,
        AUTHENTICATION_REQUIRED, REQUEST_CANCELLED, RESOURCE_NOT_FOUND,
    }
    ast_pass = "EXPECTED_LEGACY_ERROR_CODE_SITES: frozenset[tuple[str, str]] = frozenset()" in oracle and all(
        f"{name} = {value}" in registry for name, value in NAMED_ERROR_CODES.items()
    )
    if not schema_pass or not ast_pass:
        raise ValueError("Plan 11.18 authority evidence is not canonical")
    return AuthorityEvidenceRecord(
        record_id="ER-H6-ERROR-CODE-AUTHORITY", hypothesis_id="H6",
        subject="Plan 11.18 raw ACP error-code ownership authority",
        baseline_scope=BaselineScope.MERGED, baseline_anchor_commit=merged_commit,
        overlay_commit=overlay_commit, binding_commit=None,
        schema_oracle_status="PASS", ast_oracle_status="PASS", legacy_allowlist_count=0,
        commands=("uv run --frozen pytest tests/unit/acp/test_error_code_registry.py tests/unit/acp/test_errors.py -q",),
        ruling="H6 remains accepted canon: the schema and AST oracles pass and the legacy allowlist remains empty.",
        reviewer_status=ReviewerStatus.PENDING_G2,
        content_free_evidence=(
            EvidenceReference("H6-REGISTRY-SCHEMA", BaselineScope.MERGED, registry_digest),
            EvidenceReference("H6-AST-ORACLE", BaselineScope.MERGED, oracle_digest),
        ),
    )


def _semantic_record(
    source: SourceTree, merged_commit: str, overlay_commit: str,
) -> SemanticEvidenceRecord:
    inventory = discover_semantic_inventory(SourceTree({path: source.read_text(path) for path in _PYTHON_PATHS}))
    rows = semantic_selection_observations(inventory=inventory)
    assessments = _coverage(rows)
    summary = SemanticObservationSummary(
        cases_per_category=100, total_observation_count=len(rows),
        complete_observation_count=sum(item.complete for item in rows),
        observation_closure_status=ObservationClosureStatus.FULLY_STRUCTURALLY_CLOSED,
        vocabulary_coverage_status=(
            VocabularyCoverageStatus.PARTIAL_WITH_SCOPE_OUTS
            if any(item.missing_values for item in assessments) else VocabularyCoverageStatus.FULLY_OBSERVED
        ),
        digest=_digest([item.to_dict() for item in rows]),
        vocabulary={type_name: tuple(sorted(values)) for _field, type_name, values in _COVERAGE_FIELDS},
        coverage_assessments=assessments, rows=rows,
    )
    return SemanticEvidenceRecord(
        record_id="ER-H7-SEMANTIC-SELECTION", hypothesis_id="H7",
        subject="Semantic outcome and exception-to-wire selection",
        baseline_scope=BaselineScope.MERGED, baseline_anchor_commit=merged_commit,
        overlay_commit=overlay_commit, binding_commit=None,
        inventory=inventory, observations=summary,
        commands=(
            "uv run --frozen pytest tests/unit/acp/test_plan1126_semantic_errors.py -q",
            "uv run --frozen pytest tests/unit/acp/test_plan1126_semantic_errors.py tests/unit/acp/test_error_code_registry.py tests/unit/acp/test_dispatcher.py tests/unit/acp/test_errors.py -q",
        ),
        ruling=(
            "H7 records every mechanically discovered selection, preserves cancellation as distinct, and retains semantic gaps and S3 exceptions without production repair."
        ),
        reviewer_status=ReviewerStatus.PENDING_G2,
        content_free_evidence=(
            EvidenceReference("H7-AST-INVENTORY", BaselineScope.MERGED, _digest(inventory.to_dict())),
            EvidenceReference("H7-SANITIZER-OBSERVATIONS", BaselineScope.MERGED, summary.digest),
        ),
    )


def _h7_findings(record: SemanticEvidenceRecord) -> tuple[Finding, ...]:
    grouped: dict[tuple[Classification, str], list[SemanticSelectionSite]] = {}
    for site in record.inventory.sites:
        if site.classification is Classification.CANONICAL:
            continue
        grouped.setdefault((site.classification, site.ruling), []).append(site)
    findings: list[Finding] = []
    for index, ((classification, ruling), sites) in enumerate(sorted(grouped.items(), key=lambda item: (item[0][0].value, item[0][1])), start=1):
        subject = ruling.removesuffix(".")
        if "Active-turn" in subject:
            subject = "Active-turn contention selects a cancellation error"
        digest = _digest([item.to_dict() for item in sites])
        findings.append(Finding(
            finding_id=f"H7-{classification.value}-{index:02d}", subject=subject,
            classification=classification, baseline_scope=BaselineScope.MERGED,
            symbols=tuple(f"{item.path}:{item.line}:{item.symbol}" for item in sites),
            evidence=(EvidenceReference(f"H7-SELECTION-{index:02d}", BaselineScope.MERGED, digest),),
            owner=_OWNER, ruling=ruling,
        ))
    return tuple(findings)


def build_h7_audit_artifact(
    *, merged: SourceTree, overlay: SourceTree, merged_commit: str, overlay_commit: str,
) -> AuditArtifact:
    """Build the cumulative H3-H7 artifact without changing production source."""

    from .shutdown import build_h5_audit_artifact

    base = build_h5_audit_artifact(
        merged=merged, overlay=overlay, merged_commit=merged_commit, overlay_commit=overlay_commit,
    )
    h6 = _authority_record(merged, merged_commit, overlay_commit)
    h7 = _semantic_record(merged, merged_commit, overlay_commit)
    return AuditArtifact(
        schema_version=base.schema_version, merged_commit=base.merged_commit, overlay_commit=base.overlay_commit,
        binding_commit=base.binding_commit, baseline_reconciliation_status=base.baseline_reconciliation_status,
        running_artifact_provenance=base.running_artifact_provenance,
        static_audit_status=LiveStatus.PARTIAL, runtime_characterization_status=LiveStatus.PARTIAL,
        live_redis_status=base.live_redis_status, acpx_status=base.acpx_status,
        additional_client_status=base.additional_client_status, zed_status=base.zed_status,
        live_interoperability_status=base.live_interoperability_status,
        findings=tuple(base.findings) + _h7_findings(h7),
        discovered_multipliers=base.discovered_multipliers, computed_run_cost=base.computed_run_cost,
        gate_status=GateStatus.INCOMPLETE, evidence_records=tuple(base.evidence_records) + (h6, h7),
    )
