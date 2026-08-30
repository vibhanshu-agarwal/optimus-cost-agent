"""Binding-presence gate for Plan 11.26 Task 10 session/lease evidence."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from .model import (
    AuditArtifact,
    BaselineScope,
    Classification,
    EvidenceReference,
    Finding,
    GateStatus,
    LiveStatus,
    ReviewerStatus,
)
from .source import SourceTree

H10_SOURCE_PATHS = (
    "src/optimus/acp/launch_policy.py",
    "src/optimus/acp/spec.py",
)

_OWNER = "P11-FEAT-ZED-RESUME"
_NEXT_GATE = "Plan 11.7 binding integration candidate nomination"
_REQUIRED_SYMBOLS = frozenset({"SESSION_LOAD_LEASE_SECONDS", "DEFAULT_ACP_SESSION_TTL_SECONDS"})


class BindingGateOutcome(StrEnum):
    BINDING_PRESENT = "BINDING_PRESENT"
    PROVISIONAL_OVERLAY = "PROVISIONAL_OVERLAY"
    NOT_PRESENT = "NOT_PRESENT"


class DeferredObligationStatus(StrEnum):
    DEFERRED_UNTIL_BINDING = "DEFERRED_UNTIL_BINDING"
    READY = "READY"
    COMPLETE = "COMPLETE"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _is_hex(value: object, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True, slots=True)
class DurableSymbol:
    path: str
    line: int
    symbol: str
    evidence_digest: str

    def __post_init__(self) -> None:
        if self.symbol not in _REQUIRED_SYMBOLS:
            raise ValueError("H10 durable symbol is outside the gate vocabulary")
        if self.line < 1 or not self.path.startswith("src/"):
            raise ValueError("H10 durable symbol citation is invalid")
        if not _is_hex(self.evidence_digest, 64):
            raise ValueError("H10 durable symbol digest is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "symbol": self.symbol,
            "evidence_digest": self.evidence_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DurableSymbol:
        return cls(
            path=payload["path"],
            line=payload["line"],
            symbol=payload["symbol"],
            evidence_digest=payload["evidence_digest"],
        )


class _DurableSymbolVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.symbols: list[DurableSymbol] = []

    def _record(self, target: ast.expr, node: ast.AST) -> None:
        if not isinstance(target, ast.Name) or target.id not in _REQUIRED_SYMBOLS:
            return
        self.symbols.append(DurableSymbol(
            path=self.path,
            line=node.lineno,
            symbol=target.id,
            evidence_digest=_digest({"path": self.path, "line": node.lineno, "symbol": target.id}),
        ))

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._record(target, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._record(node.target, node)
        self.generic_visit(node)


def discover_durable_symbols(source: SourceTree) -> tuple[DurableSymbol, ...]:
    symbols: list[DurableSymbol] = []
    for path in source.paths():
        visitor = _DurableSymbolVisitor(path)
        visitor.visit(ast.parse(source.read_text(path), filename=path))
        symbols.extend(visitor.symbols)
    return tuple(sorted(symbols, key=lambda item: (item.path, item.line, item.symbol)))


@dataclass(frozen=True, slots=True)
class BindingPresenceDecision:
    outcome: BindingGateOutcome
    binding_commit: str | None
    baseline_reconciliation_status: str
    owner: str
    reason: str
    stop_before_runtime: bool
    observed_plan_11_7_heads: tuple[str, ...]
    merged_symbols: tuple[DurableSymbol, ...]
    overlay_symbols: tuple[DurableSymbol, ...]
    intake_digest: str
    executed_predicate_count: int = 0
    runtime_predicates_executed: bool = False
    live_redis_predicates_executed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", BindingGateOutcome(self.outcome))
        object.__setattr__(self, "observed_plan_11_7_heads", tuple(self.observed_plan_11_7_heads))
        object.__setattr__(self, "merged_symbols", tuple(self.merged_symbols))
        object.__setattr__(self, "overlay_symbols", tuple(self.overlay_symbols))
        if self.owner != _OWNER:
            raise ValueError("H10 gate owner must remain P11-FEAT-ZED-RESUME")
        if not self.reason or not self.baseline_reconciliation_status:
            raise ValueError("H10 gate requires reconciliation reason and status")
        if self.observed_plan_11_7_heads != tuple(sorted(set(self.observed_plan_11_7_heads))):
            raise ValueError("H10 Plan 11.7 heads must be sorted and unique")
        if any(not _is_hex(commit, 40) for commit in self.observed_plan_11_7_heads):
            raise ValueError("H10 Plan 11.7 head is invalid")
        if not _is_hex(self.intake_digest, 64):
            raise ValueError("H10 intake digest is invalid")
        if self.binding_commit is not None and not _is_hex(self.binding_commit, 40):
            raise ValueError("H10 binding commit is invalid")
        if self.binding_commit is None:
            if self.outcome is BindingGateOutcome.BINDING_PRESENT or not self.stop_before_runtime:
                raise ValueError("H10 absent binding must stop before runtime")
            if self.executed_predicate_count != 0:
                raise ValueError("H10 absent binding cannot carry executed predicates")
            if self.runtime_predicates_executed or self.live_redis_predicates_executed:
                raise ValueError("H10 absent binding cannot claim runtime or live execution")
        elif self.outcome is not BindingGateOutcome.BINDING_PRESENT:
            raise ValueError("H10 nominated binding must pass the presence gate")
        if self.outcome is BindingGateOutcome.PROVISIONAL_OVERLAY:
            if {item.symbol for item in self.overlay_symbols} != _REQUIRED_SYMBOLS:
                raise ValueError("H10 provisional overlay must contain both durable symbols")
            if self.merged_symbols:
                raise ValueError("H10 provisional overlay symbols must be absent from merged")
        if self.outcome is BindingGateOutcome.NOT_PRESENT and self.overlay_symbols:
            raise ValueError("H10 NOT_PRESENT cannot carry overlay durable symbols")

    @property
    def classification(self) -> Classification:
        if self.outcome is BindingGateOutcome.PROVISIONAL_OVERLAY:
            return Classification.PROVISIONAL_OVERLAY
        if self.outcome is BindingGateOutcome.NOT_PRESENT:
            return Classification.NOT_PRESENT
        return Classification.CANONICAL

    def to_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "binding_commit": self.binding_commit,
            "baseline_reconciliation_status": self.baseline_reconciliation_status,
            "owner": self.owner,
            "reason": self.reason,
            "stop_before_runtime": self.stop_before_runtime,
            "observed_plan_11_7_heads": list(self.observed_plan_11_7_heads),
            "merged_symbols": [item.to_dict() for item in self.merged_symbols],
            "overlay_symbols": [item.to_dict() for item in self.overlay_symbols],
            "intake_digest": self.intake_digest,
            "executed_predicate_count": self.executed_predicate_count,
            "runtime_predicates_executed": self.runtime_predicates_executed,
            "live_redis_predicates_executed": self.live_redis_predicates_executed,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> BindingPresenceDecision:
        return cls(
            outcome=BindingGateOutcome(payload["outcome"]),
            binding_commit=payload["binding_commit"],
            baseline_reconciliation_status=payload["baseline_reconciliation_status"],
            owner=payload["owner"],
            reason=payload["reason"],
            stop_before_runtime=payload["stop_before_runtime"],
            observed_plan_11_7_heads=tuple(payload["observed_plan_11_7_heads"]),
            merged_symbols=tuple(DurableSymbol.from_dict(item) for item in payload["merged_symbols"]),
            overlay_symbols=tuple(DurableSymbol.from_dict(item) for item in payload["overlay_symbols"]),
            intake_digest=payload["intake_digest"],
            executed_predicate_count=payload["executed_predicate_count"],
            runtime_predicates_executed=payload["runtime_predicates_executed"],
            live_redis_predicates_executed=payload["live_redis_predicates_executed"],
        )


def _distinct_plan_heads(intake: Mapping[str, Any]) -> tuple[str, ...]:
    rows = intake.get("observed_plan_11_7_refs")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Task 0 intake lacks observed Plan 11.7 refs")
    tips = tuple(sorted({row["tip"] for row in rows if isinstance(row, Mapping) and "tip" in row}))
    if not tips or any(not _is_hex(commit, 40) for commit in tips):
        raise ValueError("Task 0 intake contains an invalid Plan 11.7 tip")
    return tips


def evaluate_binding_presence_gate(
    *, intake: Mapping[str, Any], merged: SourceTree, overlay: SourceTree,
) -> BindingPresenceDecision:
    binding_commit = intake.get("binding_commit")
    reconciliation = intake.get("baseline_reconciliation_status")
    scope_out = intake.get("binding_scope_out")
    if not isinstance(reconciliation, str) or not isinstance(scope_out, Mapping):
        raise ValueError("Task 0 intake lacks binding reconciliation evidence")
    if scope_out.get("owner") != _OWNER:
        raise ValueError("Task 0 binding scope-out owner disagrees with Plan 11.7 custody")
    reason = scope_out.get("reason")
    if not isinstance(reason, str) or not reason:
        raise ValueError("Task 0 binding scope-out reason is missing")
    merged_symbols = discover_durable_symbols(merged)
    overlay_symbols = discover_durable_symbols(overlay)
    overlay_names = {item.symbol for item in overlay_symbols}
    if binding_commit is not None:
        outcome = BindingGateOutcome.BINDING_PRESENT
        stop = False
    elif overlay_names == _REQUIRED_SYMBOLS and not merged_symbols:
        outcome = BindingGateOutcome.PROVISIONAL_OVERLAY
        stop = True
    else:
        outcome = BindingGateOutcome.NOT_PRESENT
        stop = True
        overlay_symbols = ()
    return BindingPresenceDecision(
        outcome=outcome,
        binding_commit=binding_commit,
        baseline_reconciliation_status=reconciliation,
        owner=_OWNER,
        reason=reason,
        stop_before_runtime=stop,
        observed_plan_11_7_heads=_distinct_plan_heads(intake),
        merged_symbols=merged_symbols,
        overlay_symbols=overlay_symbols,
        intake_digest=_digest(intake),
    )


@dataclass(frozen=True, slots=True)
class DeferredObligation:
    obligation_id: str
    description: str
    planned_execution_count: int
    executed_count: int
    status: DeferredObligationStatus
    owner: str
    next_gate: str
    reachable_after: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", DeferredObligationStatus(self.status))
        if self.planned_execution_count < 0 or self.executed_count < 0:
            raise ValueError("H10 deferred counts cannot be negative")
        if self.executed_count != 0 or self.status is not DeferredObligationStatus.DEFERRED_UNTIL_BINDING:
            raise ValueError("H10 absent-binding obligations must remain unexecuted and deferred")
        if self.owner != _OWNER or self.next_gate != _NEXT_GATE:
            raise ValueError("H10 deferred obligation custody is invalid")
        if not self.obligation_id or not self.description or "binding" not in self.reachable_after.lower():
            raise ValueError("H10 deferred obligation must name binding reachability")

    def to_dict(self) -> dict[str, object]:
        return {
            "obligation_id": self.obligation_id,
            "description": self.description,
            "planned_execution_count": self.planned_execution_count,
            "executed_count": self.executed_count,
            "status": self.status.value,
            "owner": self.owner,
            "next_gate": self.next_gate,
            "reachable_after": self.reachable_after,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DeferredObligation:
        return cls(
            obligation_id=payload["obligation_id"],
            description=payload["description"],
            planned_execution_count=payload["planned_execution_count"],
            executed_count=payload["executed_count"],
            status=DeferredObligationStatus(payload["status"]),
            owner=payload["owner"],
            next_gate=payload["next_gate"],
            reachable_after=payload["reachable_after"],
        )


def _deferred_obligations() -> tuple[DeferredObligation, ...]:
    rows = (
        (
            "derive_session_lease_and_retention_constants",
            "Derive SESSION_LOAD_LEASE_SECONDS and DEFAULT_ACP_SESSION_TTL_SECONDS from the nominated binding tree without aliasing or workspace substitution.",
            0,
        ),
        (
            "lease_boundary_1000_seed_schedule",
            "Run one tick before expiry, exact expiry, and the 1,000 derived-seed ownership-boundary schedule.",
            1_000,
        ),
        (
            "create_acquire_mutate_release_cycles",
            "Run 50 accelerated create/acquire/mutate/release cycles against authorized real Redis.",
            50,
        ),
        (
            "owner_revision_races",
            "Run 100 owner/revision races against authorized real Redis.",
            100,
        ),
        (
            "wall_clock_recovery",
            "Run one wall-clock recovery observation without shortening the production lease.",
            1,
        ),
    )
    return tuple(
        DeferredObligation(
            obligation_id=obligation_id,
            description=description,
            planned_execution_count=count,
            executed_count=0,
            status=DeferredObligationStatus.DEFERRED_UNTIL_BINDING,
            owner=_OWNER,
            next_gate=_NEXT_GATE,
            reachable_after=(
                "Reachable only after Plan 11.7 nominates a binding integration candidate containing or superseding the durable session path."
            ),
        )
        for obligation_id, description, count in rows
    )


@dataclass(frozen=True, slots=True)
class SessionLeaseEvidenceRecord:
    record_id: str
    hypothesis_id: str
    subject: str
    baseline_scope: BaselineScope
    baseline_anchor_commit: str
    overlay_commit: str
    binding_commit: str | None
    gate_outcome: BindingGateOutcome
    classification: Classification
    binding_presence: BindingPresenceDecision
    deferred_obligations: tuple[DeferredObligation, ...]
    executed_predicate_count: int
    runtime_predicates_executed: bool
    live_redis_predicates_executed: bool
    commands: tuple[str, ...]
    ruling: str
    reviewer_status: ReviewerStatus
    content_free_evidence: tuple[EvidenceReference, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "baseline_scope", BaselineScope(self.baseline_scope))
        object.__setattr__(self, "gate_outcome", BindingGateOutcome(self.gate_outcome))
        object.__setattr__(self, "classification", Classification(self.classification))
        object.__setattr__(self, "reviewer_status", ReviewerStatus(self.reviewer_status))
        object.__setattr__(self, "deferred_obligations", tuple(self.deferred_obligations))
        if self.record_id != "ER-H10-SESSION-LEASE-GATE" or self.hypothesis_id != "H10":
            raise ValueError("H10 record identity is invalid")
        if self.binding_commit is not None or self.binding_presence.binding_commit is not None:
            raise ValueError("H10 scoped-out record cannot carry a binding commit")
        if self.gate_outcome is not self.binding_presence.outcome:
            raise ValueError("H10 record gate outcome disagrees with its decision")
        if self.classification is not self.binding_presence.classification:
            raise ValueError("H10 classification disagrees with its gate decision")
        expected_scope = (
            BaselineScope.OVERLAY
            if self.classification is Classification.PROVISIONAL_OVERLAY
            else BaselineScope.MERGED
        )
        if self.baseline_scope is not expected_scope:
            raise ValueError("H10 baseline scope disagrees with classification")
        if self.executed_predicate_count != 0 or self.runtime_predicates_executed or self.live_redis_predicates_executed:
            raise ValueError("H10 scoped-out record cannot claim executed runtime evidence")
        if tuple(item.to_dict() for item in self.deferred_obligations) != tuple(
            item.to_dict() for item in _deferred_obligations()
        ):
            raise ValueError("H10 deferred obligation set is incomplete")

    @property
    def overlay_symbols(self) -> tuple[DurableSymbol, ...]:
        return self.binding_presence.overlay_symbols

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "hypothesis_id": self.hypothesis_id,
            "subject": self.subject,
            "baseline_scope": self.baseline_scope.value,
            "baseline_anchor_commit": self.baseline_anchor_commit,
            "overlay_commit": self.overlay_commit,
            "binding_commit": self.binding_commit,
            "gate_outcome": self.gate_outcome.value,
            "classification": self.classification.value,
            "binding_presence": self.binding_presence.to_dict(),
            "deferred_obligations": [item.to_dict() for item in self.deferred_obligations],
            "executed_predicate_count": self.executed_predicate_count,
            "runtime_predicates_executed": self.runtime_predicates_executed,
            "live_redis_predicates_executed": self.live_redis_predicates_executed,
            "commands": list(self.commands),
            "ruling": self.ruling,
            "reviewer_status": self.reviewer_status.value,
            "content_free_evidence": [item.to_dict() for item in self.content_free_evidence],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SessionLeaseEvidenceRecord:
        return cls(
            record_id=payload["record_id"],
            hypothesis_id=payload["hypothesis_id"],
            subject=payload["subject"],
            baseline_scope=BaselineScope(payload["baseline_scope"]),
            baseline_anchor_commit=payload["baseline_anchor_commit"],
            overlay_commit=payload["overlay_commit"],
            binding_commit=payload["binding_commit"],
            gate_outcome=BindingGateOutcome(payload["gate_outcome"]),
            classification=Classification(payload["classification"]),
            binding_presence=BindingPresenceDecision.from_dict(payload["binding_presence"]),
            deferred_obligations=tuple(DeferredObligation.from_dict(item) for item in payload["deferred_obligations"]),
            executed_predicate_count=payload["executed_predicate_count"],
            runtime_predicates_executed=payload["runtime_predicates_executed"],
            live_redis_predicates_executed=payload["live_redis_predicates_executed"],
            commands=tuple(payload["commands"]),
            ruling=payload["ruling"],
            reviewer_status=ReviewerStatus(payload["reviewer_status"]),
            content_free_evidence=tuple(EvidenceReference.from_dict(item) for item in payload["content_free_evidence"]),
        )


def session_lease_gate_record(
    *, intake: Mapping[str, Any], merged: SourceTree, overlay: SourceTree,
    merged_commit: str, overlay_commit: str,
) -> SessionLeaseEvidenceRecord:
    intake_merged = intake.get("merged_baseline")
    intake_overlay = intake.get("runtime_overlay")
    identities_match = (
        isinstance(intake_merged, Mapping)
        and isinstance(intake_overlay, Mapping)
        and intake_merged.get("commit") == merged_commit
        and intake_overlay.get("accepted_runtime_commit") == overlay_commit
    )
    if not identities_match:
        raise ValueError("H10 intake baseline identities disagree with artifact commits")
    decision = evaluate_binding_presence_gate(intake=intake, merged=merged, overlay=overlay)
    if decision.outcome is BindingGateOutcome.BINDING_PRESENT:
        raise ValueError("H10 binding-present execution requires Steps 2-6 and cannot use the scoped-out builder")
    baseline_scope = (
        BaselineScope.OVERLAY
        if decision.classification is Classification.PROVISIONAL_OVERLAY
        else BaselineScope.MERGED
    )
    gate_digest = _digest(decision.to_dict())
    return SessionLeaseEvidenceRecord(
        record_id="ER-H10-SESSION-LEASE-GATE",
        hypothesis_id="H10",
        subject="Durable session lease, retention, owner/revision, and recovery binding gate",
        baseline_scope=baseline_scope,
        baseline_anchor_commit=merged_commit,
        overlay_commit=overlay_commit,
        binding_commit=None,
        gate_outcome=decision.outcome,
        classification=decision.classification,
        binding_presence=decision,
        deferred_obligations=_deferred_obligations(),
        executed_predicate_count=0,
        runtime_predicates_executed=False,
        live_redis_predicates_executed=False,
        commands=(
            "uv run --frozen pytest tests/unit/acp/test_plan1126_session_lease.py::test_binding_presence_gate_derives_provisional_overlay_and_stops -q",
            "uv run --frozen pytest tests/unit/acp/test_plan1126_session_lease.py -q",
        ),
        ruling=(
            "Plan 11.7 has not nominated a binding integration candidate. The durable path is visible only in the accepted overlay, so H10 is PROVISIONAL_OVERLAY and stops before constant derivation, boundary schedules, Redis mutation, owner/revision races, and wall-clock recovery."
        ),
        reviewer_status=ReviewerStatus.PENDING_G2,
        content_free_evidence=(EvidenceReference("H10-BINDING-GATE", baseline_scope, gate_digest),),
    )


def _finding(record: SessionLeaseEvidenceRecord) -> Finding:
    evidence = record.content_free_evidence[0]
    return Finding(
        finding_id="H10-PROVISIONAL-DURABLE-SESSION-overlay",
        subject="Durable session lease and retention path lacks a nominated binding integration tree",
        classification=record.classification,
        baseline_scope=record.baseline_scope,
        symbols=tuple(
            f"{item.path}:{item.line}:{item.symbol}"
            for item in record.binding_presence.overlay_symbols
        ),
        evidence=(evidence,),
        owner=_OWNER,
        ruling=(
            "The overlay symbols establish provisional presence only. No lease value, boundary behavior, Redis ownership race, or recovery result is promoted until Plan 11.7 nominates a binding tree."
        ),
    )


def build_h10_audit_artifact(
    *, merged: SourceTree, overlay: SourceTree, intake: Mapping[str, Any],
    merged_commit: str, overlay_commit: str,
) -> AuditArtifact:
    from .queue_policy import build_h9_audit_artifact

    base = build_h9_audit_artifact(
        merged=merged,
        overlay=overlay,
        merged_commit=merged_commit,
        overlay_commit=overlay_commit,
    )
    h10_merged = SourceTree({path: merged.read_text(path) for path in H10_SOURCE_PATHS})
    h10_overlay = SourceTree({path: overlay.read_text(path) for path in H10_SOURCE_PATHS})
    record = session_lease_gate_record(
        intake=intake,
        merged=h10_merged,
        overlay=h10_overlay,
        merged_commit=merged_commit,
        overlay_commit=overlay_commit,
    )
    return AuditArtifact(
        schema_version=base.schema_version,
        merged_commit=base.merged_commit,
        overlay_commit=base.overlay_commit,
        binding_commit=base.binding_commit,
        baseline_reconciliation_status=base.baseline_reconciliation_status,
        running_artifact_provenance=base.running_artifact_provenance,
        static_audit_status=LiveStatus.PARTIAL,
        runtime_characterization_status=LiveStatus.PARTIAL,
        live_redis_status=LiveStatus.UNRUN,
        acpx_status=base.acpx_status,
        additional_client_status=base.additional_client_status,
        zed_status=base.zed_status,
        live_interoperability_status=base.live_interoperability_status,
        findings=tuple(base.findings) + (_finding(record),),
        discovered_multipliers=dict(base.discovered_multipliers),
        computed_run_cost=dict(base.computed_run_cost),
        gate_status=GateStatus.INCOMPLETE,
        evidence_records=tuple(base.evidence_records) + (record,),
    )
