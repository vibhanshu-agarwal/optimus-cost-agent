"""Immutable-source telemetry and sink audit for Plan 11.26 Task 8."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import io
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from pydantic import ValidationError

from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.fanout import TelemetryFanout, emit_acp_turn_settlement_contained
from optimus.telemetry.jsonl import JsonlTelemetryWriter
from optimus.telemetry.observability import GatewayObservabilityExporter
from optimus.telemetry.redis_sink import RedisTelemetryEventSink

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

H8_SOURCE_PATHS = (
    "src/optimus/acp/bootstrap.py",
    "src/optimus/acp/debug_trace.py",
    "src/optimus/acp/dispatcher.py",
    "src/optimus/acp/server.py",
    "src/optimus/acp/settlement.py",
    "src/optimus/acp/spec.py",
    "src/optimus/agent/planning_loop.py",
    "src/optimus/telemetry/events.py",
    "src/optimus/telemetry/fanout.py",
    "src/optimus/telemetry/jsonl.py",
    "src/optimus/telemetry/observability.py",
    "src/optimus/telemetry/redaction.py",
    "src/optimus/telemetry/redis_adapter.py",
    "src/optimus/telemetry/redis_sink.py",
    "src/optimus/telemetry/serialization.py",
)


class TelemetrySiteKind(StrEnum):
    EVENT_KIND = "EVENT_KIND"
    EVENT_EMISSION = "EVENT_EMISSION"
    DEBUG_TRACE = "DEBUG_TRACE"
    STDERR = "STDERR"
    REDACTION = "REDACTION"
    SINK = "SINK"


class ContentClass(StrEnum):
    CONTENT_FREE = "CONTENT_FREE"
    CREDENTIAL = "CREDENTIAL"
    PROMPT = "PROMPT"
    RESPONSE = "RESPONSE"
    PATH = "PATH"
    REQUEST_BODY = "REQUEST_BODY"
    MIXED = "MIXED"


class RedactionPath(StrEnum):
    SHARED_SANITIZER = "SHARED_SANITIZER"
    PROTOCOL_SANITIZER = "PROTOCOL_SANITIZER"
    CONTENT_FREE_BY_CONSTRUCTION = "CONTENT_FREE_BY_CONSTRUCTION"
    NONE = "NONE"


class SinkFailureBehavior(StrEnum):
    CONTAINED = "CONTAINED"
    PROPAGATED = "PROPAGATED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SchemaCaseKind(StrEnum):
    VALID = "VALID"
    MISSING_REQUIRED = "MISSING_REQUIRED"
    EXTRA_FIELD = "EXTRA_FIELD"
    INVALID_FIELD = "INVALID_FIELD"


class ValidationOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class ConformanceResult(StrEnum):
    MATCH = "MATCH"
    DIVERGED = "DIVERGED"


class RedactionResult(StrEnum):
    CLEAN = "CLEAN"
    LEAKED = "LEAKED"


class CorrelationResult(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class SinkFailureResult(StrEnum):
    CONTAINED = "CONTAINED"
    PROPAGATED = "PROPAGATED"


_OWNER = "P11-FEAT-ACP-RUNTIME-HARDENING"


_SINK_BY_SYMBOL = {
    "JsonlTelemetryWriter": "jsonl",
    "RedisTelemetryEventSink": "redis",
    "GatewayObservabilityExporter": "gateway_export",
    "acp_debug_log": "debug_trace",
}


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str,
        ).encode("utf-8")
    ).hexdigest()


def _attribute_name(node: ast.expr) -> str:
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _call_name(node: ast.Call) -> str:
    return _attribute_name(node.func)


def _symbol(path: str, functions: list[str]) -> str:
    module = path.removesuffix(".py").replace("/", ".")
    return ".".join((module, *functions)) if functions else module


def _string_key(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _content_class(call: ast.Call) -> ContentClass:
    keys: set[str] = set()
    for node in ast.walk(call):
        if isinstance(node, ast.Dict):
            keys.update(key for child in node.keys if child is not None for key in (_string_key(child),) if key)
    lowered = " ".join(sorted(keys)).lower()
    hits = {
        ContentClass.CREDENTIAL: any(name in lowered for name in ("secret", "credential", "api_key", "authorization")),
        ContentClass.PROMPT: "prompt" in lowered,
        ContentClass.RESPONSE: any(name in lowered for name in ("response", "completion", "message_preview")),
        ContentClass.PATH: any(name in lowered for name in ("path", "cwd", "executable")),
        ContentClass.REQUEST_BODY: any(name in lowered for name in ("request_body", "params", "arguments")),
    }
    matched = [kind for kind, present in hits.items() if present]
    if len(matched) > 1:
        return ContentClass.MIXED
    return matched[0] if matched else ContentClass.CONTENT_FREE


def _redaction_path(path: str, site_kind: TelemetrySiteKind, call: ast.Call | None) -> RedactionPath:
    if site_kind is TelemetrySiteKind.REDACTION:
        return RedactionPath.SHARED_SANITIZER
    if site_kind is TelemetrySiteKind.DEBUG_TRACE:
        return RedactionPath.SHARED_SANITIZER
    if site_kind is TelemetrySiteKind.STDERR and call is not None:
        names = {_call_name(node) for node in ast.walk(call) if isinstance(node, ast.Call)}
        if any(name.endswith("sanitize_protocol_error_message") for name in names):
            return RedactionPath.PROTOCOL_SANITIZER
    if path.endswith("events.py") and site_kind is TelemetrySiteKind.EVENT_KIND:
        return RedactionPath.CONTENT_FREE_BY_CONSTRUCTION
    return RedactionPath.NONE


def _classification(
    *, site_kind: TelemetrySiteKind, content_class: ContentClass, sink_id: str | None,
    redaction_path: RedactionPath,
) -> tuple[Classification, str]:
    if site_kind is TelemetrySiteKind.SINK:
        if sink_id in {"gateway_export", "debug_trace"}:
            return Classification.CANONICAL, "The sink has a source-owned containment boundary."
        return Classification.MISSING, "The sink has no source-owned failure containment boundary."
    if site_kind is TelemetrySiteKind.STDERR and redaction_path is RedactionPath.NONE:
        return Classification.CANONICAL_BYPASSED, "The fallback diagnostic bypasses the protocol sanitizer."
    if content_class not in {ContentClass.CONTENT_FREE, ContentClass.CREDENTIAL} and redaction_path is RedactionPath.NONE:
        return Classification.CANONICAL_BYPASSED, "Content-bearing telemetry reaches a diagnostic boundary without content-class minimization."
    return Classification.CANONICAL, "The site follows the currently visible telemetry or sanitization path."


@dataclass(frozen=True, slots=True)
class RuntimeEventSchema:
    event_kind: str
    factory_name: str
    required_payload_fields: tuple[str, ...]
    optional_payload_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "event_kind": self.event_kind,
            "factory_name": self.factory_name,
            "required_payload_fields": list(self.required_payload_fields),
            "optional_payload_fields": list(self.optional_payload_fields),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RuntimeEventSchema:
        return cls(
            event_kind=payload["event_kind"],
            factory_name=payload["factory_name"],
            required_payload_fields=tuple(payload["required_payload_fields"]),
            optional_payload_fields=tuple(payload["optional_payload_fields"]),
        )


@dataclass(frozen=True, slots=True)
class TelemetrySite:
    path: str
    line: int
    symbol: str
    site_kind: TelemetrySiteKind
    semantic_event: str | None
    correlation_fields: tuple[str, ...]
    content_class: ContentClass
    redaction_path: RedactionPath
    sink_id: str | None
    sink_failure_behavior: SinkFailureBehavior
    baseline_scope: BaselineScope
    classification: Classification
    evidence_digest: str
    ruling: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "symbol": self.symbol,
            "site_kind": self.site_kind.value,
            "semantic_event": self.semantic_event,
            "correlation_fields": list(self.correlation_fields),
            "content_class": self.content_class.value,
            "redaction_path": self.redaction_path.value,
            "sink_id": self.sink_id,
            "sink_failure_behavior": self.sink_failure_behavior.value,
            "baseline_scope": self.baseline_scope.value,
            "classification": self.classification.value,
            "evidence_digest": self.evidence_digest,
            "ruling": self.ruling,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TelemetrySite:
        return cls(
            path=payload["path"], line=payload["line"], symbol=payload["symbol"],
            site_kind=TelemetrySiteKind(payload["site_kind"]), semantic_event=payload["semantic_event"],
            correlation_fields=tuple(payload["correlation_fields"]),
            content_class=ContentClass(payload["content_class"]),
            redaction_path=RedactionPath(payload["redaction_path"]), sink_id=payload["sink_id"],
            sink_failure_behavior=SinkFailureBehavior(payload["sink_failure_behavior"]),
            baseline_scope=BaselineScope(payload["baseline_scope"]),
            classification=Classification(payload["classification"]),
            evidence_digest=payload["evidence_digest"], ruling=payload["ruling"],
        )


@dataclass(frozen=True, slots=True)
class TelemetryInventory:
    sites: tuple[TelemetrySite, ...]
    event_schemas: Mapping[str, RuntimeEventSchema]
    required_correlation_fields: tuple[str, ...]
    expected_site_count: None = None

    @property
    def site_count(self) -> int:
        return len(self.sites)

    @property
    def sink_ids(self) -> tuple[str, ...]:
        return tuple(sorted({site.sink_id for site in self.sites if site.sink_id is not None}))

    @property
    def sink_count(self) -> int:
        return len(self.sink_ids)

    @property
    def event_kind_count(self) -> int:
        return len(self.event_schemas)

    def to_dict(self) -> dict[str, object]:
        return {
            "expected_site_count": self.expected_site_count,
            "site_count": self.site_count,
            "sink_count": self.sink_count,
            "sink_ids": list(self.sink_ids),
            "event_kind_count": self.event_kind_count,
            "required_correlation_fields": list(self.required_correlation_fields),
            "event_schemas": {
                key: value.to_dict() for key, value in sorted(self.event_schemas.items())
            },
            "sites": [site.to_dict() for site in self.sites],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TelemetryInventory:
        if payload.get("expected_site_count") is not None:
            raise ValueError("telemetry inventory expected_site_count must remain null")
        sites = tuple(TelemetrySite.from_dict(item) for item in payload["sites"])
        schemas = {
            key: RuntimeEventSchema.from_dict(value)
            for key, value in payload["event_schemas"].items()
        }
        inventory = cls(
            sites=sites,
            event_schemas=schemas,
            required_correlation_fields=tuple(payload["required_correlation_fields"]),
        )
        if (
            payload["site_count"] != inventory.site_count
            or payload["sink_count"] != inventory.sink_count
            or tuple(payload["sink_ids"]) != inventory.sink_ids
            or payload["event_kind_count"] != inventory.event_kind_count
        ):
            raise ValueError("telemetry inventory derived counts do not match stored sites")
        return inventory


def _payload_schema(function: ast.FunctionDef) -> tuple[str, tuple[str, ...], tuple[str, ...]] | None:
    event_kind: str | None = None
    required: set[str] = set()
    optional: set[str] = set()
    payload_name: str | None = None
    for node in ast.walk(function):
        if isinstance(node, ast.Assign):
            targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if "payload" in targets and isinstance(node.value, ast.Dict):
                payload_name = "payload"
                required.update(key for child in node.value.keys if child is not None for key in (_string_key(child),) if key)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "payload":
            payload_name = "payload"
            if isinstance(node.value, ast.Dict):
                required.update(key for child in node.value.keys if child is not None for key in (_string_key(child),) if key)
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Subscript):
            target = node.targets[0]
            if isinstance(target.value, ast.Name) and target.value.id == payload_name:
                key = _string_key(target.slice)
                if key:
                    optional.add(key)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "cls":
            for keyword in node.keywords:
                if keyword.arg == "kind" and isinstance(keyword.value, ast.Attribute):
                    event_kind = keyword.value.attr
                if keyword.arg == "payload" and isinstance(keyword.value, ast.Dict):
                    required.update(key for child in keyword.value.keys if child is not None for key in (_string_key(child),) if key)
    if event_kind is None:
        return None
    optional &= required | optional
    return event_kind, tuple(sorted(required - optional)), tuple(sorted(optional))


class _TelemetryVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.functions: list[str] = []
        self.sites: list[TelemetrySite] = []
        self.event_schemas: dict[str, RuntimeEventSchema] = {}
        self._event_kind_class = False

    def _add(
        self, *, line: int, kind: TelemetrySiteKind, semantic_event: str | None = None,
        call: ast.Call | None = None, sink_id: str | None = None,
    ) -> None:
        content_class = _content_class(call) if call is not None else ContentClass.CONTENT_FREE
        redaction_path = _redaction_path(self.path, kind, call)
        classification, ruling = _classification(
            site_kind=kind, content_class=content_class, sink_id=sink_id,
            redaction_path=redaction_path,
        )
        correlation_fields = tuple(sorted({
            key for key in ("run_id", "session_id", "request_id", "trace_id", "event_id")
            if call is not None and any(
                isinstance(node, ast.Constant) and node.value == key for node in ast.walk(call)
            )
        }))
        behavior = (
            SinkFailureBehavior.CONTAINED
            if sink_id in {"gateway_export", "debug_trace"}
            else SinkFailureBehavior.PROPAGATED
            if sink_id in {"jsonl", "redis", "stderr"}
            else SinkFailureBehavior.NOT_APPLICABLE
        )
        symbol = _symbol(self.path, self.functions)
        payload = {
            "path": self.path, "line": line, "symbol": symbol, "site_kind": kind.value,
            "semantic_event": semantic_event, "content_class": content_class.value,
            "redaction_path": redaction_path.value, "sink_id": sink_id,
        }
        self.sites.append(TelemetrySite(
            path=self.path, line=line, symbol=symbol, site_kind=kind,
            semantic_event=semantic_event, correlation_fields=correlation_fields,
            content_class=content_class, redaction_path=redaction_path, sink_id=sink_id,
            sink_failure_behavior=behavior, baseline_scope=BaselineScope.MERGED,
            classification=classification, evidence_digest=_digest(payload), ruling=ruling,
        ))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        prior = self._event_kind_class
        self._event_kind_class = self.path.endswith("telemetry/events.py") and node.name == "TelemetryEventKind"
        sink_id = _SINK_BY_SYMBOL.get(node.name)
        if sink_id is not None:
            self.functions.append(node.name)
            self._add(line=node.lineno, kind=TelemetrySiteKind.SINK, sink_id=sink_id)
            self.functions.pop()
        self.generic_visit(node)
        self._event_kind_class = prior

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._event_kind_class:
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    self.functions.append(target.id)
                    self._add(line=node.lineno, kind=TelemetrySiteKind.EVENT_KIND, semantic_event=node.value.value)
                    self.functions.pop()
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append(node.name)
        if self.path.endswith("telemetry/events.py"):
            schema = _payload_schema(node)
            if schema is not None:
                enum_name, required, optional = schema
                self.event_schemas[enum_name] = RuntimeEventSchema(
                    event_kind=enum_name,
                    factory_name=node.name,
                    required_payload_fields=required,
                    optional_payload_fields=optional,
                )
        if self.path.endswith("acp/debug_trace.py") and node.name == "acp_debug_log":
            self._add(line=node.lineno, kind=TelemetrySiteKind.SINK, sink_id="debug_trace")
        self.generic_visit(node)
        self.functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        if name.startswith("TelemetryEvent."):
            self._add(
                line=node.lineno, kind=TelemetrySiteKind.EVENT_EMISSION,
                semantic_event=name.rsplit(".", 1)[-1], call=node,
            )
        if name.endswith("acp_debug_log") and not (
            self.path.endswith("acp/debug_trace.py") and self.functions[-1:] == ["acp_debug_log"]
        ):
            self._add(line=node.lineno, kind=TelemetrySiteKind.DEBUG_TRACE, call=node)
        if name.endswith("redact_for_telemetry"):
            self._add(line=node.lineno, kind=TelemetrySiteKind.REDACTION, call=node)
        if name == "print":
            for keyword in node.keywords:
                if keyword.arg == "file" and _attribute_name(keyword.value) == "sys.stderr":
                    self._add(line=keyword.value.lineno, kind=TelemetrySiteKind.STDERR, call=node, sink_id="stderr")
        self.generic_visit(node)


def _required_trace_fields(source: SourceTree) -> tuple[str, ...]:
    tree = ast.parse(source.read_text("src/optimus/telemetry/observability.py"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "TraceEvent":
            fields: list[str] = []
            for child in node.body:
                if not isinstance(child, ast.AnnAssign) or not isinstance(child.target, ast.Name):
                    continue
                annotation = ast.unparse(child.annotation)
                optional = "None" in annotation
                has_default_none = isinstance(child.value, ast.Constant) and child.value.value is None
                if not optional and not has_default_none:
                    fields.append(child.target.id)
            return tuple(sorted(fields))
    raise ValueError("TraceEvent correlation schema was not found")


def discover_telemetry_inventory(source: SourceTree) -> TelemetryInventory:
    """Derive Task 8 sites and schemas without an expected site list or count."""

    sites: list[TelemetrySite] = []
    schemas_by_enum: dict[str, RuntimeEventSchema] = {}
    enum_values: dict[str, str] = {}
    for path in source.paths():
        if path not in H8_SOURCE_PATHS or not path.endswith(".py"):
            continue
        visitor = _TelemetryVisitor(path)
        visitor.visit(ast.parse(source.read_text(path), filename=path))
        sites.extend(visitor.sites)
        schemas_by_enum.update(visitor.event_schemas)
        for site in visitor.sites:
            if site.site_kind is TelemetrySiteKind.EVENT_KIND and site.semantic_event is not None:
                enum_values[site.symbol.rsplit(".", 1)[-1]] = site.semantic_event
    event_schemas = {
        enum_values[name]: RuntimeEventSchema(
            event_kind=enum_values[name],
            factory_name=schema.factory_name,
            required_payload_fields=schema.required_payload_fields,
            optional_payload_fields=schema.optional_payload_fields,
        )
        for name, schema in schemas_by_enum.items()
        if name in enum_values
    }
    if set(event_schemas) != set(enum_values.values()):
        missing = sorted(set(enum_values.values()) - set(event_schemas))
        raise ValueError(f"runtime event factories are missing for event kinds: {missing}")
    return TelemetryInventory(
        sites=tuple(sorted(sites, key=lambda item: (item.path, item.line, item.site_kind.value))),
        event_schemas=event_schemas,
        required_correlation_fields=_required_trace_fields(source),
    )


@dataclass(frozen=True, slots=True)
class RuntimeEventSchemaObservation:
    case_index: int
    event_kind: str
    case_kind: SchemaCaseKind
    mutated_field: str | None
    expected_outcome: ValidationOutcome
    actual_outcome: ValidationOutcome
    conformance: ConformanceResult
    input_digest: str
    output_digest: str
    complete: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "case_index": self.case_index,
            "event_kind": self.event_kind,
            "case_kind": self.case_kind.value,
            "mutated_field": self.mutated_field,
            "expected_outcome": self.expected_outcome.value,
            "actual_outcome": self.actual_outcome.value,
            "conformance": self.conformance.value,
            "input_digest": self.input_digest,
            "output_digest": self.output_digest,
            "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RuntimeEventSchemaObservation:
        return cls(
            case_index=payload["case_index"], event_kind=payload["event_kind"],
            case_kind=SchemaCaseKind(payload["case_kind"]), mutated_field=payload["mutated_field"],
            expected_outcome=ValidationOutcome(payload["expected_outcome"]),
            actual_outcome=ValidationOutcome(payload["actual_outcome"]),
            conformance=ConformanceResult(payload["conformance"]),
            input_digest=payload["input_digest"], output_digest=payload["output_digest"],
            complete=payload["complete"],
        )


def _schema_value(field: str, index: int) -> object:
    if field in {
        "billing_units", "input_tokens", "output_tokens", "latency_ms", "turn_seq",
        "duration_ms", "attempt", "retry_count", "delay_ms", "iteration", "mutation_count",
        "assumption_count",
    }:
        return index + 1
    if field in {
        "cache_hit", "passed", "reconciled", "requires_human_approval", "post_teardown",
        "provider_attempt_started", "cost_complete", "prior_history_flush",
    }:
        return bool(index % 2)
    if field.endswith("_names") or field.endswith("_tools") or field in {
        "tool_names", "matched_skills", "matched_reasons",
    }:
        return [f"task8-item-{index % 7}"]
    if field.endswith("_ids"):
        return [f"task8-id-{index % 11}"]
    if "cost_usd" in field or field in {"cost_delta_usd", "remaining_budget_usd"}:
        return str((index % 17) + 1)
    if field == "parameters":
        return {"safe": index}
    return f"task8-{field}-{index % 23}"


def runtime_event_schema_observations(
    *, inventory: TelemetryInventory, case_count: int = 10_000,
) -> tuple[RuntimeEventSchemaObservation, ...]:
    """Run 10,000 source-schema cases through the real ``TelemetryEvent`` validator."""

    if case_count != 10_000 or not inventory.event_schemas:
        raise ValueError("runtime event schema characterization requires exactly 10,000 cases and a non-empty inventory")
    event_kinds = tuple(sorted(inventory.event_schemas))
    case_kinds = tuple(SchemaCaseKind)
    rows: list[RuntimeEventSchemaObservation] = []
    occurred_at = datetime(2026, 8, 29, tzinfo=UTC)
    for case_index in range(case_count):
        event_kind = event_kinds[case_index % len(event_kinds)]
        schema = inventory.event_schemas[event_kind]
        case_kind = case_kinds[(case_index // len(event_kinds)) % len(case_kinds)]
        payload = {
            field: _schema_value(field, case_index)
            for field in schema.required_payload_fields
        }
        mutated_field: str | None = None
        if case_kind is SchemaCaseKind.MISSING_REQUIRED:
            mutated_field = schema.required_payload_fields[case_index % len(schema.required_payload_fields)]
            del payload[mutated_field]
        elif case_kind is SchemaCaseKind.EXTRA_FIELD:
            mutated_field = "task8_unreviewed_extra"
            payload[mutated_field] = case_index
        elif case_kind is SchemaCaseKind.INVALID_FIELD:
            mutated_field = schema.required_payload_fields[case_index % len(schema.required_payload_fields)]
            payload[mutated_field] = {"invalid": [case_index]}
        expected = (
            ValidationOutcome.ACCEPTED
            if case_kind is SchemaCaseKind.VALID
            else ValidationOutcome.REJECTED
        )
        event_payload = {
            "schema_version": "1.0",
            "event_id": f"task8-event-{case_index}",
            "trace_id": f"task8-trace-{case_index % 31}",
            "kind": event_kind,
            "run_id": f"task8-run-{case_index % 31}",
            "session_id": f"task8-session-{case_index % 13}",
            "request_id": f"task8-request-{case_index}",
            "occurred_at": occurred_at,
            "payload": payload,
        }
        try:
            event = TelemetryEvent.model_validate(event_payload)
        except ValidationError as exc:
            actual = ValidationOutcome.REJECTED
            output_digest = _digest({"errors": exc.errors(include_url=False)})
        else:
            actual = ValidationOutcome.ACCEPTED
            output_digest = _digest(event.to_json_dict())
        conformance = ConformanceResult.MATCH if actual is expected else ConformanceResult.DIVERGED
        rows.append(RuntimeEventSchemaObservation(
            case_index=case_index, event_kind=event_kind, case_kind=case_kind,
            mutated_field=mutated_field, expected_outcome=expected, actual_outcome=actual,
            conformance=conformance, input_digest=_digest(event_payload),
            output_digest=output_digest,
        ))
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class RuntimeRedactionObservation:
    case_index: int
    content_class: ContentClass
    sink_results: Mapping[str, str]
    overall_result: RedactionResult
    input_digest: str
    output_digest: str
    complete: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "case_index": self.case_index,
            "content_class": self.content_class.value,
            "sink_results": dict(sorted(self.sink_results.items())),
            "overall_result": self.overall_result.value,
            "input_digest": self.input_digest,
            "output_digest": self.output_digest,
            "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RuntimeRedactionObservation:
        return cls(
            case_index=payload["case_index"], content_class=ContentClass(payload["content_class"]),
            sink_results=dict(payload["sink_results"]),
            overall_result=RedactionResult(payload["overall_result"]),
            input_digest=payload["input_digest"], output_digest=payload["output_digest"],
            complete=payload["complete"],
        )


class _CaptureGatewayClient:
    def __init__(self) -> None:
        self.payload: Mapping[str, Any] = {}

    def post_observability_json(self, *, path: str, payload: Mapping[str, Any]) -> dict[str, object]:
        del path
        self.payload = payload
        return {
            "trace_batch_id": "task8-batch",
            "trace_ids": [],
            "delivery_state": "delivered",
            "retry_count": 0,
            "final_disposition": "accepted",
        }


class _UnusedRedisAdapter:
    """A tool-call event must be discarded before any adapter operation."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"tool-call redaction probe unexpectedly reached Redis adapter method {name}")


def _canary(content_class: ContentClass, case_index: int) -> str:
    if content_class is ContentClass.CREDENTIAL:
        return f"OPTIMUS_API_KEY=sk-task8-secret-{case_index:06d}"
    if content_class is ContentClass.PATH:
        return f"D:/task8/workspace/case-{case_index:06d}/document.txt"
    words = content_class.value.lower().replace("_", " ")
    return f"task eight {words} prose case {case_index:06d}"


def _result_for_output(output: str, canary: str) -> str:
    return RedactionResult.LEAKED.value if canary in output else RedactionResult.CLEAN.value


def runtime_redaction_observations(
    *, inventory: TelemetryInventory, case_count: int = 1_000, workspace: str | Path,
) -> tuple[RuntimeRedactionObservation, ...]:
    """Drive nested canaries through every derived terminal sink without persisting content."""

    if case_count != 1_000 or not inventory.sink_ids:
        raise ValueError("runtime redaction characterization requires exactly 1,000 cases and discovered sinks")
    expected_sinks = {"jsonl", "redis", "gateway_export", "debug_trace", "stderr"}
    if set(inventory.sink_ids) != expected_sinks:
        raise ValueError("redaction harness does not cover the complete source-derived sink set")

    from optimus.acp import debug_trace
    from optimus.acp.errors import sanitize_protocol_error_message

    root = Path(workspace)
    jsonl_path = root / "task8-redaction.jsonl"
    debug_path = root / "task8-debug.ndjson"
    writer = JsonlTelemetryWriter(jsonl_path)
    redis_sink = RedisTelemetryEventSink(_UnusedRedisAdapter())  # type: ignore[arg-type]
    capture_client = _CaptureGatewayClient()
    exporter = object.__new__(GatewayObservabilityExporter)
    exporter._client = capture_client  # type: ignore[attr-defined]
    debug_trace.configure_debug_trace(enabled=True, log_path=debug_path, provenance_root=root)
    jsonl_offset = 0
    debug_offset = 0
    rows: list[RuntimeRedactionObservation] = []
    occurred_at = datetime(2026, 8, 29, tzinfo=UTC)
    content_classes = (
        ContentClass.CREDENTIAL, ContentClass.PROMPT, ContentClass.RESPONSE,
        ContentClass.PATH, ContentClass.REQUEST_BODY,
    )
    try:
        for case_index in range(case_count):
            content_class = content_classes[case_index % len(content_classes)]
            canary = _canary(content_class, case_index)
            nested = {
                "mapping": {"value": canary},
                "sequence": ["safe", {"nested": canary}],
                "exception": RuntimeError(canary),
            }
            event = TelemetryEvent.tool_call(
                run_id=f"task8-run-{case_index % 31}",
                session_id=f"task8-session-{case_index % 13}",
                request_id=f"task8-request-{case_index}", occurred_at=occurred_at,
                tool_name="task8-redaction-probe", parameters=nested,
                result_summary=canary, latency_ms=case_index,
                policy_reason=canary, authorization_outcome="ALLOW",
            )

            writer.append(event)
            with jsonl_path.open("rb") as handle:
                handle.seek(jsonl_offset)
                json_line = handle.read().decode("utf-8")
                jsonl_offset = handle.tell()
            exporter.export((event,))
            gateway_output = json.dumps(capture_client.payload, sort_keys=True, default=str)
            redis_sink(event)
            debug_trace.acp_debug_log(
                location="task8:redaction", message=canary, data=nested,
                hypothesis_id="H8", run_id=f"task8-run-{case_index % 31}",
            )
            with debug_path.open("rb") as handle:
                handle.seek(debug_offset)
                debug_output = handle.read().decode("utf-8")
                debug_offset = handle.tell()
            stderr_output = f"optimus.acp: {sanitize_protocol_error_message(str(RuntimeError(canary)))}"
            sink_results = {
                "jsonl": _result_for_output(json_line, canary),
                "redis": RedactionResult.CLEAN.value,
                "gateway_export": _result_for_output(gateway_output, canary),
                "debug_trace": _result_for_output(debug_output, canary),
                "stderr": _result_for_output(stderr_output, canary),
            }
            overall = (
                RedactionResult.CLEAN
                if set(sink_results.values()) == {RedactionResult.CLEAN.value}
                else RedactionResult.LEAKED
            )
            rows.append(RuntimeRedactionObservation(
                case_index=case_index, content_class=content_class, sink_results=sink_results,
                overall_result=overall,
                input_digest=_digest({"content_class": content_class.value, "case_index": case_index}),
                output_digest=_digest(sink_results),
            ))
    finally:
        debug_trace.reset_debug_trace_context()
        for path in (jsonl_path, debug_path):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class RuntimeCorrelationObservation:
    channel: str
    event_kind: str | None
    present_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    result: CorrelationResult
    evidence_digest: str
    complete: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "channel": self.channel,
            "event_kind": self.event_kind,
            "present_fields": list(self.present_fields),
            "missing_fields": list(self.missing_fields),
            "result": self.result.value,
            "evidence_digest": self.evidence_digest,
            "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RuntimeCorrelationObservation:
        return cls(
            channel=payload["channel"], event_kind=payload["event_kind"],
            present_fields=tuple(payload["present_fields"]), missing_fields=tuple(payload["missing_fields"]),
            result=CorrelationResult(payload["result"]), evidence_digest=payload["evidence_digest"],
            complete=payload["complete"],
        )


def runtime_correlation_observations(
    *, inventory: TelemetryInventory,
) -> tuple[RuntimeCorrelationObservation, ...]:
    """Compare typed events and fallback diagnostics to the derived Gateway trace join key."""

    required = set(inventory.required_correlation_fields)
    rows: list[RuntimeCorrelationObservation] = []

    def add(channel: str, event_kind: str | None, present: set[str]) -> None:
        present_fields = tuple(sorted(present & required))
        missing_fields = tuple(sorted(required - present))
        result = CorrelationResult.COMPLETE if not missing_fields else CorrelationResult.INCOMPLETE
        rows.append(RuntimeCorrelationObservation(
            channel=channel, event_kind=event_kind, present_fields=present_fields,
            missing_fields=missing_fields, result=result,
            evidence_digest=_digest({
                "channel": channel, "event_kind": event_kind,
                "present_fields": present_fields, "missing_fields": missing_fields,
            }),
        ))

    occurred_at = datetime(2026, 8, 29, tzinfo=UTC)
    for index, (event_kind, schema) in enumerate(sorted(inventory.event_schemas.items())):
        payload = {field: _schema_value(field, index) for field in schema.required_payload_fields}
        event = TelemetryEvent.model_validate({
            "kind": event_kind,
            "run_id": f"task8-run-{index}",
            "session_id": f"task8-session-{index}",
            "request_id": f"task8-request-{index}",
            "occurred_at": occurred_at,
            "payload": payload,
        })
        encoded = event.to_json_dict()
        add("typed_event", event_kind, {key for key, value in encoded.items() if value is not None})

    for channel, kind in (
        ("debug_trace", TelemetrySiteKind.DEBUG_TRACE),
        ("stderr", TelemetrySiteKind.STDERR),
    ):
        site_fields = [
            set(site.correlation_fields)
            for site in inventory.sites
            if site.site_kind is kind
        ]
        if not site_fields:
            raise ValueError(f"correlation inventory has no {channel} sites")
        present = set.intersection(*site_fields)
        add(channel, None, present)
    add("wire_error", None, {"request_id"})
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class RuntimeSinkFailureObservation:
    sink_id: str
    repeat_index: int
    event_kind: str
    failure_result: SinkFailureResult
    control_digest: str
    failure_digest: str
    complete: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "sink_id": self.sink_id,
            "repeat_index": self.repeat_index,
            "event_kind": self.event_kind,
            "failure_result": self.failure_result.value,
            "control_digest": self.control_digest,
            "failure_digest": self.failure_digest,
            "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RuntimeSinkFailureObservation:
        return cls(
            sink_id=payload["sink_id"], repeat_index=payload["repeat_index"],
            event_kind=payload["event_kind"], failure_result=SinkFailureResult(payload["failure_result"]),
            control_digest=payload["control_digest"], failure_digest=payload["failure_digest"],
            complete=payload["complete"],
        )


class _NoopSink:
    def __call__(self, event: TelemetryEvent) -> None:
        del event

    def append(self, event: TelemetryEvent) -> None:
        del event


class _RaisingSink:
    def __call__(self, event: TelemetryEvent) -> None:
        del event
        raise OSError("task8 injected sink failure")

    def append(self, event: TelemetryEvent) -> None:
        del event
        raise OSError("task8 injected sink failure")

    def export(self, events: tuple[TelemetryEvent, ...]) -> dict[str, object]:
        del events
        raise OSError("task8 injected sink failure")


class _SuccessfulExporter:
    def export(self, events: tuple[TelemetryEvent, ...]) -> dict[str, object]:
        return {
            "trace_batch_id": "task8-control-batch",
            "trace_ids": tuple(event.trace_id for event in events),
            "delivery_state": "delivered",
            "retry_count": 0,
            "final_disposition": "accepted",
        }


class _RaisingTextStream:
    def write(self, value: str) -> int:
        del value
        raise OSError("task8 injected stderr failure")

    def flush(self) -> None:
        return None


class _InvalidNdjsonReader:
    def __init__(self) -> None:
        self._read = False

    async def readline(self) -> bytes:
        if self._read:
            return b""
        self._read = True
        return b'{"task8":\n'


class _NoopNdjsonWriter:
    async def write_line(self, message: Mapping[str, Any]) -> None:
        del message


class _MinimalRunner:
    event_sink = None


def _ordinary_event(index: int) -> TelemetryEvent:
    return TelemetryEvent.error(
        run_id=f"task8-run-{index}", session_id=f"task8-session-{index % 7}",
        request_id=f"task8-request-{index}", occurred_at=datetime(2026, 8, 29, tzinfo=UTC),
        error_type="Task8Probe", message="contained diagnostic", disposition="observed",
    )


def _settlement_event(index: int) -> TelemetryEvent:
    return TelemetryEvent.acp_turn_settlement(
        run_id=f"task8-run-{index}", session_id=f"task8-session-{index % 7}",
        request_id=f"task8-request-{index}", occurred_at=datetime(2026, 8, 29, tzinfo=UTC),
        turn_seq=index + 1, interruption_phase="teardown", settlement="settled",
        final_delivery="not_attempted", rpc_response_delivery="not_required",
        conversation_commit="not_committed", effect_state="none",
        provider_attempt_started=False, cost_complete=True,
        prior_history_flush=False, post_teardown=False,
    )


def _invoke_fanout(fanout: TelemetryFanout, event: TelemetryEvent, *, settlement: bool) -> None:
    if settlement:
        emit_acp_turn_settlement_contained(fanout, event)
    else:
        fanout(event)


def _invoke_stderr(stream: object, workspace: Path) -> None:
    from optimus.acp.dispatcher import JsonRpcDispatcher
    from optimus.acp.server import AcpStreamServer

    server = AcpStreamServer(
        dispatcher=JsonRpcDispatcher(agent_runner=_MinimalRunner(), workspace_root=workspace),  # type: ignore[arg-type]
    )
    previous = sys.stderr
    sys.stderr = stream  # type: ignore[assignment]
    try:
        asyncio.run(
            asyncio.wait_for(
                server.serve_ndjson(_InvalidNdjsonReader(), _NoopNdjsonWriter()),
                timeout=0.1,
            )
        )
    finally:
        sys.stderr = previous


def telemetry_sink_failure_observations(
    *, inventory: TelemetryInventory, repeats: int = 100, workspace: str | Path,
) -> tuple[RuntimeSinkFailureObservation, ...]:
    """Inject 100 real failures per source-derived terminal sink."""

    if repeats != 100 or not inventory.sink_ids:
        raise ValueError("sink containment characterization requires exactly 100 repeats per discovered sink")
    expected_sinks = {"jsonl", "redis", "gateway_export", "debug_trace", "stderr"}
    if set(inventory.sink_ids) != expected_sinks:
        raise ValueError("sink containment harness does not cover the complete source-derived sink set")
    root = Path(workspace)
    rows: list[RuntimeSinkFailureObservation] = []
    from optimus.acp import debug_trace

    for sink_id in inventory.sink_ids:
        for repeat_index in range(repeats):
            settlement = repeat_index % 2 == 1 and sink_id in {"jsonl", "redis", "gateway_export"}
            event = _settlement_event(repeat_index) if settlement else _ordinary_event(repeat_index)
            control_state = "returned"
            failure_state = "returned"
            try:
                if sink_id in {"jsonl", "redis", "gateway_export"}:
                    control = TelemetryFanout(
                        jsonl_writer=_NoopSink(), redis_sink=_NoopSink(),
                        gateway_exporter=_SuccessfulExporter(), batch_size=1,
                    )
                    _invoke_fanout(control, event, settlement=settlement)
                elif sink_id == "debug_trace":
                    control_path = root / "task8-debug-control.ndjson"
                    debug_trace.configure_debug_trace(enabled=True, log_path=control_path, provenance_root=root)
                    debug_trace.acp_debug_log(location="task8:control", message="control")
                    try:
                        os.unlink(control_path)
                    except FileNotFoundError:
                        pass
                    debug_trace.reset_debug_trace_context()
                else:
                    _invoke_stderr(io.StringIO(), root)
            except Exception as exc:  # pragma: no cover - a control failure is itself a failed predicate
                control_state = f"raised:{type(exc).__name__}"

            try:
                if sink_id == "jsonl":
                    failed = TelemetryFanout(
                        jsonl_writer=_RaisingSink(), redis_sink=_NoopSink(),
                        gateway_exporter=_SuccessfulExporter(), batch_size=1,
                    )
                    _invoke_fanout(failed, event, settlement=settlement)
                elif sink_id == "redis":
                    failed = TelemetryFanout(
                        jsonl_writer=_NoopSink(), redis_sink=_RaisingSink(),
                        gateway_exporter=_SuccessfulExporter(), batch_size=1,
                    )
                    _invoke_fanout(failed, event, settlement=settlement)
                elif sink_id == "gateway_export":
                    failed = TelemetryFanout(
                        jsonl_writer=_NoopSink(), redis_sink=_NoopSink(),
                        gateway_exporter=_RaisingSink(), batch_size=1,
                    )
                    _invoke_fanout(failed, event, settlement=settlement)
                elif sink_id == "debug_trace":
                    debug_trace.configure_debug_trace(enabled=True, log_path=root, provenance_root=root)
                    debug_trace.acp_debug_log(location="task8:failure", message="failure")
                    debug_trace.reset_debug_trace_context()
                else:
                    _invoke_stderr(_RaisingTextStream(), root)
            except Exception as exc:
                failure_state = f"raised:{type(exc).__name__}"
            finally:
                debug_trace.reset_debug_trace_context()

            if control_state != "returned":
                raise ValueError(f"sink control failed for {sink_id}: {control_state}")
            result = (
                SinkFailureResult.PROPAGATED
                if failure_state.startswith("raised:")
                else SinkFailureResult.CONTAINED
            )
            rows.append(RuntimeSinkFailureObservation(
                sink_id=sink_id, repeat_index=repeat_index, event_kind=event.kind.value,
                failure_result=result,
                control_digest=_digest({"sink_id": sink_id, "state": control_state, "repeat": repeat_index}),
                failure_digest=_digest({"sink_id": sink_id, "state": failure_state, "repeat": repeat_index}),
            ))
    return tuple(rows)


_Row = RuntimeEventSchemaObservation | RuntimeRedactionObservation | RuntimeCorrelationObservation | RuntimeSinkFailureObservation


@dataclass(frozen=True, slots=True)
class H8ObservationSummary:
    total_observation_count: int
    complete_observation_count: int
    observation_closure_status: ObservationClosureStatus
    vocabulary_coverage_status: VocabularyCoverageStatus
    digest: str
    coverage_assessments: tuple[VocabularyCoverageAssessment, ...]
    rows: tuple[_Row, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_closure_status", ObservationClosureStatus(self.observation_closure_status))
        object.__setattr__(self, "vocabulary_coverage_status", VocabularyCoverageStatus(self.vocabulary_coverage_status))
        object.__setattr__(self, "coverage_assessments", tuple(self.coverage_assessments))
        object.__setattr__(self, "rows", tuple(self.rows))
        if self.total_observation_count != len(self.rows):
            raise ValueError("H8 summary count does not match stored observations")
        if self.complete_observation_count != sum(row.complete for row in self.rows):
            raise ValueError("H8 complete count does not match stored observations")
        if self.complete_observation_count != self.total_observation_count:
            raise ValueError("H8 observations must be structurally complete")
        if self.observation_closure_status is not ObservationClosureStatus.FULLY_STRUCTURALLY_CLOSED:
            raise ValueError("H8 complete observations must be labelled structurally closed")
        if self.digest != _digest([row.to_dict() for row in self.rows]):
            raise ValueError("H8 summary digest does not match stored observations")
        has_scope_out = False
        names: set[str] = set()
        for assessment in self.coverage_assessments:
            if assessment.field_name in names:
                raise ValueError("H8 coverage fields must be unique")
            names.add(assessment.field_name)
            observed = tuple(sorted({
                value.value if isinstance(value, StrEnum) else value
                for row in self.rows
                for value in (getattr(row, assessment.field_name),)
            }))
            missing = tuple(sorted(set(assessment.vocabulary_values) - set(observed)))
            expected_status = CoverageAssessmentStatus.SCOPED_OUT if missing else CoverageAssessmentStatus.FULLY_OBSERVED
            if (
                assessment.observed_values != observed
                or assessment.missing_values != missing
                or assessment.status is not expected_status
            ):
                raise ValueError("H8 coverage assessment disagrees with stored observations")
            has_scope_out = has_scope_out or bool(missing)
        expected_aggregate = (
            VocabularyCoverageStatus.PARTIAL_WITH_SCOPE_OUTS
            if has_scope_out else VocabularyCoverageStatus.FULLY_OBSERVED
        )
        if self.vocabulary_coverage_status is not expected_aggregate:
            raise ValueError("H8 aggregate coverage status disagrees with assessments")

    def to_dict(self) -> dict[str, object]:
        return {
            "total_observation_count": self.total_observation_count,
            "complete_observation_count": self.complete_observation_count,
            "observation_closure_status": self.observation_closure_status.value,
            "vocabulary_coverage_status": self.vocabulary_coverage_status.value,
            "digest": self.digest,
            "coverage_assessments": [item.to_dict() for item in self.coverage_assessments],
            "rows": [row.to_dict() for row in self.rows],
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any], *, row_type: type[_Row],
    ) -> H8ObservationSummary:
        return cls(
            total_observation_count=payload["total_observation_count"],
            complete_observation_count=payload["complete_observation_count"],
            observation_closure_status=ObservationClosureStatus(payload["observation_closure_status"]),
            vocabulary_coverage_status=VocabularyCoverageStatus(payload["vocabulary_coverage_status"]),
            digest=payload["digest"],
            coverage_assessments=tuple(
                VocabularyCoverageAssessment.from_dict(item) for item in payload["coverage_assessments"]
            ),
            rows=tuple(row_type.from_dict(item) for item in payload["rows"]),
        )


def _coverage(
    rows: tuple[_Row, ...],
    specifications: tuple[tuple[str, str, tuple[str, ...]], ...],
) -> tuple[VocabularyCoverageAssessment, ...]:
    assessments: list[VocabularyCoverageAssessment] = []
    for field_name, type_name, vocabulary in specifications:
        observed = tuple(sorted({
            value.value if isinstance(value, StrEnum) else value
            for row in rows for value in (getattr(row, field_name),)
        }))
        vocabulary_values = tuple(sorted(vocabulary))
        missing = tuple(sorted(set(vocabulary_values) - set(observed)))
        assessments.append(VocabularyCoverageAssessment(
            field_name=field_name, type_name=type_name,
            vocabulary_values=vocabulary_values, observed_values=observed, missing_values=missing,
            status=CoverageAssessmentStatus.SCOPED_OUT if missing else CoverageAssessmentStatus.FULLY_OBSERVED,
            reason=(
                "The offline Task 8 matrix did not reach these values; G4 must retain a reviewed negative-path scenario for them."
                if missing else None
            ),
            owner=_OWNER if missing else None,
            next_gate="G4 telemetry negative-path coverage" if missing else None,
        ))
    return tuple(assessments)


def _summary(
    rows: tuple[_Row, ...],
    specifications: tuple[tuple[str, str, tuple[str, ...]], ...],
) -> H8ObservationSummary:
    assessments = _coverage(rows, specifications)
    return H8ObservationSummary(
        total_observation_count=len(rows), complete_observation_count=sum(row.complete for row in rows),
        observation_closure_status=ObservationClosureStatus.FULLY_STRUCTURALLY_CLOSED,
        vocabulary_coverage_status=(
            VocabularyCoverageStatus.PARTIAL_WITH_SCOPE_OUTS
            if any(item.missing_values for item in assessments)
            else VocabularyCoverageStatus.FULLY_OBSERVED
        ),
        digest=_digest([row.to_dict() for row in rows]),
        coverage_assessments=assessments, rows=rows,
    )


@dataclass(frozen=True, slots=True)
class S2Ruling:
    scalar_field: str
    plural_field: str
    relationship: str
    classification: Classification
    symbol_citations: tuple[str, ...]
    evidence_digest: str
    ruling: str

    def to_dict(self) -> dict[str, object]:
        return {
            "scalar_field": self.scalar_field,
            "plural_field": self.plural_field,
            "relationship": self.relationship,
            "classification": self.classification.value,
            "symbol_citations": list(self.symbol_citations),
            "evidence_digest": self.evidence_digest,
            "ruling": self.ruling,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> S2Ruling:
        return cls(
            scalar_field=payload["scalar_field"], plural_field=payload["plural_field"],
            relationship=payload["relationship"], classification=Classification(payload["classification"]),
            symbol_citations=tuple(payload["symbol_citations"]), evidence_digest=payload["evidence_digest"],
            ruling=payload["ruling"],
        )


def _s2_ruling(source: SourceTree) -> S2Ruling:
    citations: list[str] = []
    scalar_count = 0
    plural_count = 0
    append_count = 0
    for path in (
        "src/optimus/acp/dispatcher.py",
        "src/optimus/acp/debug_trace.py",
        "src/optimus/agent/planning_loop.py",
    ):
        tree = ast.parse(source.read_text(path), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "gateway_request_id":
                scalar_count += 1
                citations.append(f"{path}:{node.lineno}:gateway_request_id")
            if isinstance(node, (ast.AnnAssign, ast.Assign)):
                targets: list[ast.expr] = (
                    [node.target] if isinstance(node, ast.AnnAssign) else list(node.targets)
                )
                for target in targets:
                    if isinstance(target, ast.Name) and target.id == "gateway_request_ids":
                        plural_count += 1
                        citations.append(f"{path}:{node.lineno}:gateway_request_ids")
            if isinstance(node, ast.Call) and _call_name(node).endswith("_gateway_request_ids.append"):
                append_count += 1
                citations.append(f"{path}:{node.lineno}:gateway_request_ids.append")
    if not scalar_count or plural_count < 2 or not append_count:
        raise ValueError("S2 source evidence does not establish scalar-attempt to plural-aggregate cardinality")
    citations_tuple = tuple(sorted(set(citations)))
    return S2Ruling(
        scalar_field="gateway_request_id", plural_field="gateway_request_ids",
        relationship="ONE_ATTEMPT_TO_MANY_ATTEMPTS_PER_PLANNING_RUN",
        classification=Classification.CANONICAL, symbol_citations=citations_tuple,
        evidence_digest=_digest({
            "scalar_count": scalar_count, "plural_count": plural_count,
            "append_count": append_count, "citations": citations_tuple,
        }),
        ruling=(
            "S2 is a documented cardinality distinction: gateway_request_id identifies one reported usage attempt, while gateway_request_ids is the ordered aggregate appended across planning attempts."
        ),
    )


@dataclass(frozen=True, slots=True)
class _CombinedCoverage:
    coverage_assessments: tuple[VocabularyCoverageAssessment, ...]


@dataclass(frozen=True, slots=True)
class TelemetryEvidenceRecord:
    record_id: str
    hypothesis_id: str
    subject: str
    baseline_scope: BaselineScope
    baseline_anchor_commit: str
    overlay_commit: str
    binding_commit: str | None
    inventory: TelemetryInventory
    schema_observations: H8ObservationSummary
    redaction_observations: H8ObservationSummary
    correlation_observations: H8ObservationSummary
    sink_failure_observations: H8ObservationSummary
    s2_ruling: S2Ruling
    commands: tuple[str, ...]
    ruling: str
    reviewer_status: ReviewerStatus
    content_free_evidence: tuple[EvidenceReference, ...]

    @property
    def schedule_observations(self) -> _CombinedCoverage:
        return _CombinedCoverage(tuple(
            assessment
            for summary in (
                self.schema_observations, self.redaction_observations,
                self.correlation_observations, self.sink_failure_observations,
            )
            for assessment in summary.coverage_assessments
        ))

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id, "hypothesis_id": self.hypothesis_id,
            "subject": self.subject, "baseline_scope": self.baseline_scope.value,
            "baseline_anchor_commit": self.baseline_anchor_commit, "overlay_commit": self.overlay_commit,
            "binding_commit": self.binding_commit, "inventory": self.inventory.to_dict(),
            "schema_observations": self.schema_observations.to_dict(),
            "redaction_observations": self.redaction_observations.to_dict(),
            "correlation_observations": self.correlation_observations.to_dict(),
            "sink_failure_observations": self.sink_failure_observations.to_dict(),
            "s2_ruling": self.s2_ruling.to_dict(), "commands": list(self.commands),
            "ruling": self.ruling, "reviewer_status": self.reviewer_status.value,
            "content_free_evidence": [item.to_dict() for item in self.content_free_evidence],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TelemetryEvidenceRecord:
        return cls(
            record_id=payload["record_id"], hypothesis_id=payload["hypothesis_id"],
            subject=payload["subject"], baseline_scope=BaselineScope(payload["baseline_scope"]),
            baseline_anchor_commit=payload["baseline_anchor_commit"], overlay_commit=payload["overlay_commit"],
            binding_commit=payload["binding_commit"], inventory=TelemetryInventory.from_dict(payload["inventory"]),
            schema_observations=H8ObservationSummary.from_dict(
                payload["schema_observations"], row_type=RuntimeEventSchemaObservation,
            ),
            redaction_observations=H8ObservationSummary.from_dict(
                payload["redaction_observations"], row_type=RuntimeRedactionObservation,
            ),
            correlation_observations=H8ObservationSummary.from_dict(
                payload["correlation_observations"], row_type=RuntimeCorrelationObservation,
            ),
            sink_failure_observations=H8ObservationSummary.from_dict(
                payload["sink_failure_observations"], row_type=RuntimeSinkFailureObservation,
            ),
            s2_ruling=S2Ruling.from_dict(payload["s2_ruling"]), commands=tuple(payload["commands"]),
            ruling=payload["ruling"], reviewer_status=ReviewerStatus(payload["reviewer_status"]),
            content_free_evidence=tuple(EvidenceReference.from_dict(item) for item in payload["content_free_evidence"]),
        )


def _telemetry_record(
    source: SourceTree, merged_commit: str, overlay_commit: str, workspace: str | Path,
) -> TelemetryEvidenceRecord:
    scoped = SourceTree({path: source.read_text(path) for path in H8_SOURCE_PATHS})
    inventory = discover_telemetry_inventory(scoped)
    schema_rows = runtime_event_schema_observations(inventory=inventory)
    redaction_rows = runtime_redaction_observations(inventory=inventory, workspace=workspace)
    correlation_rows = runtime_correlation_observations(inventory=inventory)
    sink_rows = telemetry_sink_failure_observations(inventory=inventory, workspace=workspace)
    schema = _summary(schema_rows, (
        ("event_kind", "TelemetryEventKind", tuple(sorted(inventory.event_schemas))),
        ("case_kind", "SchemaCaseKind", tuple(item.value for item in SchemaCaseKind)),
        ("expected_outcome", "ValidationOutcome", tuple(item.value for item in ValidationOutcome)),
        ("actual_outcome", "ValidationOutcome", tuple(item.value for item in ValidationOutcome)),
        ("conformance", "ConformanceResult", tuple(item.value for item in ConformanceResult)),
    ))
    redaction = _summary(redaction_rows, (
        ("content_class", "RedactionCanaryClass", tuple(
            item.value for item in (
                ContentClass.CREDENTIAL, ContentClass.PROMPT, ContentClass.RESPONSE,
                ContentClass.PATH, ContentClass.REQUEST_BODY,
            )
        )),
        ("overall_result", "RedactionResult", tuple(item.value for item in RedactionResult)),
    ))
    correlation = _summary(correlation_rows, (
        ("result", "CorrelationResult", tuple(item.value for item in CorrelationResult)),
    ))
    sink_failure = _summary(sink_rows, (
        ("sink_id", "DerivedSinkId", inventory.sink_ids),
        ("failure_result", "SinkFailureResult", tuple(item.value for item in SinkFailureResult)),
    ))
    s2 = _s2_ruling(scoped)
    return TelemetryEvidenceRecord(
        record_id="ER-H8-TELEMETRY-CONTAINMENT", hypothesis_id="H8",
        subject="Telemetry schema, redaction, correlation, and sink containment",
        baseline_scope=BaselineScope.MERGED, baseline_anchor_commit=merged_commit,
        overlay_commit=overlay_commit, binding_commit=None, inventory=inventory,
        schema_observations=schema, redaction_observations=redaction,
        correlation_observations=correlation, sink_failure_observations=sink_failure,
        s2_ruling=s2,
        commands=(
            "uv run --frozen pytest tests/unit/telemetry/test_plan1126_runtime_contract.py::test_runtime_event_schema_generated_10000_cases -q",
            "uv run --frozen pytest tests/unit/telemetry/test_plan1126_runtime_contract.py::test_runtime_redaction_generated_1000_cases -q",
            "uv run --frozen pytest tests/unit/telemetry/test_plan1126_runtime_contract.py::test_runtime_correlation_chain_is_complete -q",
            "uv run --frozen pytest tests/unit/telemetry/test_plan1126_runtime_contract.py::test_telemetry_sink_failures_are_contained -q",
        ),
        ruling=(
            "H8 derives every reviewed event and sink site, separates structural closure from vocabulary coverage, retains schema/redaction/correlation/containment gaps, and rules S2 as canonical one-to-many cardinality without renaming production fields."
        ),
        reviewer_status=ReviewerStatus.PENDING_G2,
        content_free_evidence=(
            EvidenceReference("H8-INVENTORY", BaselineScope.MERGED, _digest(inventory.to_dict())),
            EvidenceReference("H8-SCHEMA", BaselineScope.MERGED, schema.digest),
            EvidenceReference("H8-REDACTION", BaselineScope.MERGED, redaction.digest),
            EvidenceReference("H8-CORRELATION", BaselineScope.MERGED, correlation.digest),
            EvidenceReference("H8-SINK-FAILURES", BaselineScope.MERGED, sink_failure.digest),
            EvidenceReference("H8-S2", BaselineScope.MERGED, s2.evidence_digest),
        ),
    )


def _h8_findings(record: TelemetryEvidenceRecord) -> tuple[Finding, ...]:
    schema_divergence = tuple(
        row.to_dict() for row in record.schema_observations.rows
        if isinstance(row, RuntimeEventSchemaObservation) and row.conformance is ConformanceResult.DIVERGED
    )
    redaction_leaks = tuple(
        row.to_dict() for row in record.redaction_observations.rows
        if isinstance(row, RuntimeRedactionObservation) and row.overall_result is RedactionResult.LEAKED
    )
    propagated = tuple(
        row.to_dict() for row in record.sink_failure_observations.rows
        if isinstance(row, RuntimeSinkFailureObservation) and row.failure_result is SinkFailureResult.PROPAGATED
    )
    incomplete = tuple(
        row.to_dict() for row in record.correlation_observations.rows
        if isinstance(row, RuntimeCorrelationObservation) and row.result is CorrelationResult.INCOMPLETE
    )
    findings: list[Finding] = []
    if schema_divergence:
        findings.append(Finding(
            finding_id="H8-MISSING-EVENT-PAYLOAD-SCHEMAS-merged",
            subject="Most runtime event kinds lack ACP-turn-settlement-grade payload validation",
            classification=Classification.MISSING, baseline_scope=BaselineScope.MERGED,
            symbols=("src/optimus/telemetry/events.py:54:TelemetryEvent",),
            evidence=(EvidenceReference("H8-SCHEMA-DIVERGENCE", BaselineScope.MERGED, _digest(schema_divergence)),),
            owner=_OWNER,
            ruling="Missing, extra, and invalid payload variants are admitted outside the exact-key ACP_TURN_SETTLEMENT boundary.",
        ))
    if redaction_leaks:
        findings.append(Finding(
            finding_id="H8-CANONICAL-BYPASSED-CONTENT-MINIMIZATION-merged",
            subject="Content-bearing telemetry is sanitized for secrets but not minimized by content class",
            classification=Classification.CANONICAL_BYPASSED, baseline_scope=BaselineScope.MERGED,
            symbols=(
                "src/optimus/telemetry/events.py:669:TelemetryEvent.to_json_dict",
                "src/optimus/acp/debug_trace.py:186:acp_debug_log",
            ),
            evidence=(EvidenceReference("H8-REDACTION-LEAKS", BaselineScope.MERGED, _digest(redaction_leaks)),),
            owner=_OWNER,
            ruling="Credential canaries are removed, while prompt, response, path, and request-body canaries remain observable at one or more authorized sinks.",
        ))
    if propagated:
        findings.append(Finding(
            finding_id="H8-MISSING-SINK-CONTAINMENT-merged",
            subject="Ordinary telemetry and stderr sink failures can escape or block runtime control flow",
            classification=Classification.MISSING, baseline_scope=BaselineScope.MERGED,
            symbols=(
                "src/optimus/telemetry/fanout.py:58:TelemetryFanout.__call__",
                "src/optimus/acp/server.py:443:AcpStreamServer.serve_ndjson",
            ),
            evidence=(EvidenceReference("H8-PROPAGATED-SINK-FAILURES", BaselineScope.MERGED, _digest(propagated)),),
            owner=_OWNER,
            ruling="Gateway export and settlement evidence are contained, but ordinary JSONL/Redis failures propagate and failed stderr diagnostics can strand the reader path until timeout.",
        ))
    if incomplete:
        findings.append(Finding(
            finding_id="H8-MISSING-FALLBACK-CORRELATION-merged",
            subject="Fallback diagnostics cannot be deterministically joined to the typed runtime trace chain",
            classification=Classification.MISSING, baseline_scope=BaselineScope.MERGED,
            symbols=(
                "src/optimus/acp/debug_trace.py:186:acp_debug_log",
                "src/optimus/acp/server.py:443:AcpStreamServer.serve_ndjson",
            ),
            evidence=(EvidenceReference("H8-INCOMPLETE-CORRELATION", BaselineScope.MERGED, _digest(incomplete)),),
            owner=_OWNER,
            ruling="Typed events satisfy the required Gateway trace fields, while debug, stderr, and wire-error fallback channels lack the same deterministic join key.",
        ))
    return tuple(findings)


def build_h8_audit_artifact(
    *, merged: SourceTree, overlay: SourceTree, merged_commit: str, overlay_commit: str,
    workspace: str | Path,
) -> AuditArtifact:
    """Build the cumulative H3-H8 artifact without changing production source."""

    from .semantic_errors import build_h7_audit_artifact

    base = build_h7_audit_artifact(
        merged=merged, overlay=overlay, merged_commit=merged_commit, overlay_commit=overlay_commit,
    )
    h8 = _telemetry_record(merged, merged_commit, overlay_commit, workspace)
    multipliers = dict(base.discovered_multipliers)
    multipliers["sinks"] = h8.inventory.sink_count
    cost = dict(base.computed_run_cost)
    cost["sink_failure_runs"] = h8.inventory.sink_count * 100
    return AuditArtifact(
        schema_version=base.schema_version, merged_commit=base.merged_commit, overlay_commit=base.overlay_commit,
        binding_commit=base.binding_commit, baseline_reconciliation_status=base.baseline_reconciliation_status,
        running_artifact_provenance=base.running_artifact_provenance,
        static_audit_status=LiveStatus.PARTIAL, runtime_characterization_status=LiveStatus.PARTIAL,
        live_redis_status=base.live_redis_status, acpx_status=base.acpx_status,
        additional_client_status=base.additional_client_status, zed_status=base.zed_status,
        live_interoperability_status=base.live_interoperability_status,
        findings=tuple(base.findings) + _h8_findings(h8),
        discovered_multipliers=multipliers, computed_run_cost=cost,
        gate_status=GateStatus.INCOMPLETE, evidence_records=tuple(base.evidence_records) + (h8,),
    )
