"""Immutable-source delivery-settlement characterization for the H4 worked example."""

from __future__ import annotations

import ast
import concurrent.futures
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

from .corpus import derived_seed, literal_seeds
from .inventory import discover_delivery_sites
from .model import (
    AuditArtifact,
    BaselineScope,
    Classification,
    ConstantMetadataNote,
    ContradictionSearchRecord,
    CoverageAssessmentStatus,
    DeliveryObservation,
    DeliveryPhase,
    DiscoveredSite,
    EvidenceRecord,
    EvidenceReference,
    Finding,
    GateStatus,
    LiveStatus,
    MetadataClaimStatus,
    ObservationClosureStatus,
    ReviewerStatus,
    ScheduleObservationSummary,
    ScheduleOperation,
    VocabularyCoverageAssessment,
    VocabularyCoverageStatus,
)
from .source import SourceTree

_SETTLEMENT_PATH = "src/optimus/acp/settlement.py"
_TRANSITION_PATHS = (
    "src/optimus/acp/settlement.py",
    "src/optimus/acp/lifecycle.py",
    "src/optimus/acp/outbound_writer.py",
    "src/optimus/acp/spec.py",
    "src/optimus/acp/conversation.py",
)
H4_SOURCE_PATHS = (
    "src/optimus/acp/outbound_writer.py",
    "src/optimus/acp/lifecycle.py",
    "src/optimus/acp/settlement.py",
    "src/optimus/acp/conversation.py",
    "src/optimus/acp/spec.py",
    "src/optimus/acp/server.py",
)
_VOCABULARY_NAMES = (
    "ConversationCommit",
    "EffectState",
    "FinalDelivery",
    "RpcResponseDelivery",
    "SendOutcome",
    "SendState",
    "Settlement",
)
_COVERAGE_FIELDS = (
    ("conversation_commit", "ConversationCommit"),
    ("effect_state", "EffectState"),
    ("final_delivery", "FinalDelivery"),
    ("rpc_response_delivery", "RpcResponseDelivery"),
    ("send_outcome", "SendOutcome"),
    ("send_state", "SendState"),
    ("settlement", "Settlement"),
)
_COVERAGE_OWNER = "P11-FEAT-ACP-RUNTIME-HARDENING"
_SCOPE_OUTS = {
    "final_delivery": (
        "These H4 scenarios execute start_response_send and never start_terminal_message, "
        "so terminal-message states are unreachable.",
        "G5 terminal-message characterization",
    ),
    "send_state": (
        "Queued and write_started are transient states absent from terminal observation snapshots.",
        "G4 per-group transient-state observation review",
    ),
    "settlement": (
        "The reviewed _placeholder_settlement two-branch producer does not emit cancelled, "
        "failed, or rejected.",
        "G4 per-group settlement-producer review",
    ),
}


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def derive_delivery_vocabulary(merged: SourceTree, overlay: SourceTree) -> dict[str, dict[str, str]]:
    """Derive the settled enums from both immutable baselines and fail closed on drift."""

    def parse(source: SourceTree) -> dict[str, dict[str, str]]:
        tree = ast.parse(source.read_text(_SETTLEMENT_PATH), filename=_SETTLEMENT_PATH)
        result: dict[str, dict[str, str]] = {}
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name not in _VOCABULARY_NAMES:
                continue
            members = {
                statement.targets[0].id: statement.value.value
                for statement in node.body
                if isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            }
            if not members:
                raise ValueError(f"settled vocabulary {node.name} has no literal members")
            result[node.name] = members
        if tuple(sorted(result)) != _VOCABULARY_NAMES:
            raise ValueError("immutable source does not define exactly the seven settled delivery types")
        return result

    before = parse(merged)
    after = parse(overlay)
    if before != after:
        raise ValueError("merged and overlay settled vocabulary diverge")
    return before


def _citation(site: DiscoveredSite) -> str:
    return f"{site.path}:{site.line}:{site.symbol}:{site.reference}"


def _scenario(seed: int) -> str:
    return (
        "success-known-effect",
        "success-unknown-effect",
        "preparation-failure",
        "write-failure",
        "flush-failure",
        "session-cancel-before-protocol-write",
        "cancel-after-publication",
        "transport-teardown",
    )[seed % 8]


@dataclass(frozen=True, slots=True)
class _TransitionExecution:
    operations: tuple[ScheduleOperation, ...]
    scenario: str
    write_attempted: bool
    flush_attempted: bool
    cancellation_timing: str
    cancellation_result: str
    primary_conversation_record_count: int
    send_state: str
    send_outcome: str
    settlement: str
    final_delivery: str
    rpc_response_delivery: str
    conversation_commit: str
    effect_state: str


@dataclass(frozen=True, slots=True)
class _TransitionAuthority:
    send_outcome: object
    turn_control: object
    directive_kind: object
    acp_duplex_adapter: object
    dedicated_outbound_writer: object
    outbound_queue_item: object
    conversation_state: object
    conversation_sanitizer: object
    conversation_sanitizer_inputs: object
    conversation_outcome: object
    effect_state_type: object
    conversation_commit_type: object
    definition_citations: Mapping[str, str]

    @property
    def executed_definition_citations(self) -> frozenset[str]:
        return frozenset(self.definition_citations.values())

    def execute(self, seed: int) -> _TransitionExecution:
        scenario = _scenario(seed)
        SendOutcome = self.send_outcome
        TurnControl = self.turn_control
        DirectiveKind = self.directive_kind
        adapter = self.acp_duplex_adapter
        DedicatedOutboundWriter = self.dedicated_outbound_writer
        OutboundQueueItem = self.outbound_queue_item
        ConversationState = self.conversation_state
        ConversationSanitizer = self.conversation_sanitizer
        ConversationSanitizerInputs = self.conversation_sanitizer_inputs
        ConversationOutcome = self.conversation_outcome
        EffectState = self.effect_state_type
        ConversationCommit = self.conversation_commit_type

        operations: list[ScheduleOperation] = []
        seen: set[DeliveryPhase] = set()

        def record(phase: DeliveryPhase, operation: str, authority_name: str) -> None:
            if phase in seen:
                return
            operations.append(ScheduleOperation(
                phase=phase,
                operation=operation,
                citation=self.definition_citations[authority_name],
            ))
            seen.add(phase)

        mode = seed % 8
        turn = TurnControl(session_id="audit-h4", turn_seq=seed)
        turn.register_operations(((DirectiveKind.WRITE, "write-1"), (DirectiveKind.WRITE, "write-2")))
        if scenario != "session-cancel-before-protocol-write":
            for operation_id in ("write-1", "write-2"):
                turn.try_start(DirectiveKind.WRITE, operation_id)
        effect_done = False

        def exercise_effect() -> None:
            nonlocal effect_done
            if effect_done:
                return
            if scenario == "session-cancel-before-protocol-write":
                record(
                    DeliveryPhase.EFFECT_SETTLEMENT,
                    f"observe_effect_after_session_cancel_{scenario}",
                    "TurnControl.current_settlement_fields",
                )
            elif scenario == "transport-teardown":
                record(
                    DeliveryPhase.EFFECT_SETTLEMENT,
                    f"observe_effect_after_transport_teardown_{scenario}",
                    "TurnControl.request_transport_teardown",
                )
            elif scenario == "success-known-effect":
                turn.complete_directive(DirectiveKind.WRITE, "write-1", "succeeded")
                turn.complete_directive(DirectiveKind.WRITE, "write-2", "succeeded")
                record(
                    DeliveryPhase.EFFECT_SETTLEMENT,
                    f"complete_directives_{scenario}",
                    "TurnControl.complete_directive",
                )
            elif scenario in {"preparation-failure", "write-failure"}:
                turn.complete_directive(DirectiveKind.WRITE, "write-1", "succeeded")
                turn.complete_directive(DirectiveKind.WRITE, "write-2", "failed_effect_known")
                record(
                    DeliveryPhase.EFFECT_SETTLEMENT,
                    f"complete_directives_{scenario}",
                    "TurnControl.complete_directive",
                )
            else:
                turn.complete_directive(DirectiveKind.WRITE, "write-1", "failed_effect_unknown")
                turn.complete_directive(DirectiveKind.WRITE, "write-2", "failed_effect_unknown")
                record(
                    DeliveryPhase.EFFECT_SETTLEMENT,
                    f"complete_directives_{scenario}",
                    "TurnControl.complete_directive",
                )
            effect_done = True

        cancellation_timing: str | None = None
        cancellation_result: str | None = None

        def request_session_cancel(timing: str) -> None:
            nonlocal cancellation_timing, cancellation_result
            if cancellation_timing is not None:
                return
            result = turn.request_session_cancel()
            cancellation_timing = timing
            cancellation_result = result.value
            record(
                DeliveryPhase.CANCELLATION,
                f"session_cancel_{timing}_{result.value}_{scenario}",
                "TurnControl.request_session_cancel",
            )

        def request_transport_teardown(timing: str) -> None:
            nonlocal cancellation_timing, cancellation_result
            if cancellation_timing is not None:
                return
            result = turn.request_transport_teardown()
            cancellation_timing = timing
            cancellation_result = result.value
            record(
                DeliveryPhase.CANCELLATION,
                f"transport_teardown_{timing}_{result.value}_{scenario}",
                "TurnControl.request_transport_teardown",
            )

        if mode == 0:
            exercise_effect()

        lease = turn.start_response_send()
        if not lease.granted or lease.send_key is None:
            raise ValueError("audit transition could not allocate the production response lease")

        class ContentFreeSink:
            def __init__(self, *, write_failure: bool = False, flush_failure: bool = False) -> None:
                self.write_failure = write_failure
                self.flush_failure = flush_failure
                self.write_count = 0
                self.flush_count = 0

            def write_bytes(self, data: bytes) -> None:
                if not data:
                    raise ValueError("audit sink received an empty production write")
                self.write_count += 1
                record(
                    DeliveryPhase.PHYSICAL_WRITE,
                    f"write_attempted_{scenario}",
                    "DedicatedOutboundWriter._process_item",
                )
                if mode == 3:
                    request_session_cancel("during-write")
                if self.write_failure:
                    raise RuntimeError("content-free write failure")

            def flush(self) -> None:
                self.flush_count += 1
                record(
                    DeliveryPhase.FLUSH,
                    f"flush_attempted_{scenario}",
                    "DedicatedOutboundWriter._process_item",
                )
                if mode == 4:
                    request_session_cancel("during-flush")
                if self.flush_failure:
                    raise RuntimeError("content-free flush failure")

        sink = ContentFreeSink(
            write_failure=scenario == "write-failure",
            flush_failure=scenario == "flush-failure",
        )
        writer = DedicatedOutboundWriter(sink)
        writer._started = True  # noqa: SLF001 - execute production admission without a live thread
        future: concurrent.futures.Future[object] = concurrent.futures.Future()
        item = OutboundQueueItem(
            payload={"audit_event": "h4-content-free"},
            send_key=lease.send_key,
            owner=turn,
            source_future=future,
            prepare_error=(
                RuntimeError("content-free preparation failure")
                if scenario == "preparation-failure"
                else None
            ),
        )
        writer.submit(item)
        record(
            DeliveryPhase.QUEUE_ADMISSION,
            f"submit_outbound_item_{scenario}",
            "DedicatedOutboundWriter.submit",
        )

        if mode == 1:
            exercise_effect()
        if scenario == "session-cancel-before-protocol-write":
            request_session_cancel("before-write")
        elif scenario == "transport-teardown":
            request_transport_teardown("before-write")

        queued = writer._queue.get_nowait()  # noqa: SLF001 - item admitted by production submit
        writer._process_item(queued)  # noqa: SLF001 - deterministic local physical boundary
        write_attempted = sink.write_count > 0
        flush_attempted = sink.flush_count > 0
        if not write_attempted:
            record(
                DeliveryPhase.PHYSICAL_WRITE,
                f"write_not_attempted_{scenario}",
                "DedicatedOutboundWriter._process_item",
            )
        if not flush_attempted:
            record(
                DeliveryPhase.FLUSH,
                f"flush_not_attempted_{scenario}",
                "DedicatedOutboundWriter._process_item",
            )

        completion = future.result()
        outcome = completion.outcome
        record(
            DeliveryPhase.PUBLICATION,
            f"primary_completion_{outcome.value}_{scenario}",
            (
                "DedicatedOutboundWriter._process_item"
                if scenario == "transport-teardown"
                else "TurnControl.publish_authoritative"
            ),
        )

        if mode == 6:
            request_session_cancel("after-publication")
        if mode in {2, 3, 4, 6}:
            exercise_effect()
        if cancellation_timing is None:
            request_session_cancel("after-publication")

        turn.seal_final_delivery()
        record(
            DeliveryPhase.FINAL_RESPONSE,
            f"seal_final_delivery_{scenario}",
            "TurnControl.seal_final_delivery",
        )
        if not effect_done:
            exercise_effect()

        snapshot = adapter._placeholder_settlement(  # noqa: SLF001
            None, SimpleNamespace(turn_control=turn)
        )
        conversation = ConversationState(ConversationSanitizer(ConversationSanitizerInputs(
            known_secrets=(), path_aliases=(), known_pii=(),
        )))
        decision = conversation.prepare_commit(
            1,
            sanitized_user_prompt="h4-content-free-user",
            sanitized_plan_text="h4-content-free-plan",
            sanitized_completion_text="h4-content-free-completion",
            outcome=ConversationOutcome.COMPLETED,
            effect_state=EffectState(snapshot.effect_state.value),
        )
        should_commit = outcome is SendOutcome.FLUSHED and scenario not in {
            "session-cancel-before-protocol-write", "transport-teardown",
        }
        if should_commit:
            conversation.commit_after_final_flush(decision)
        primary_conversation_record_count = len(conversation.records)
        conversation_commit = (
            ConversationCommit.COMMITTED
            if decision.turn_seq in conversation.records
            else ConversationCommit.NOT_COMMITTED
        )
        record(
            DeliveryPhase.CONVERSATION_COMMIT,
            (
                f"commit_after_final_flush_{scenario}"
                if conversation_commit is ConversationCommit.COMMITTED
                else f"commit_withheld_after_prepare_{scenario}"
            ),
            (
                "ConversationState.commit_after_final_flush"
                if conversation_commit is ConversationCommit.COMMITTED
                else "ConversationState.prepare_commit"
            ),
        )
        assert cancellation_timing is not None and cancellation_result is not None
        state = turn.send_slot(lease.send_key).authoritative
        return _TransitionExecution(
            operations=tuple(operations),
            scenario=scenario,
            write_attempted=write_attempted,
            flush_attempted=flush_attempted,
            cancellation_timing=cancellation_timing,
            cancellation_result=cancellation_result,
            primary_conversation_record_count=primary_conversation_record_count,
            send_state=state.value,
            send_outcome=outcome.value,
            settlement=snapshot.settlement.value,
            final_delivery=snapshot.final_delivery.value,
            rpc_response_delivery=snapshot.rpc_response_delivery.value,
            conversation_commit=conversation_commit.value,
            effect_state=snapshot.effect_state.value,
        )


def derive_transition_authority(
    merged: SourceTree,
    overlay: SourceTree,
    *,
    repository: Path | None = None,
) -> _TransitionAuthority:
    """Use production transitions only after byte equality with both immutable trees."""

    root = repository or Path(__file__).resolve().parents[2]
    selected_methods = {
        "src/optimus/acp/lifecycle.py": {
            "DirectiveKind": None,
            "TurnControl": {
                "__init__", "current_settlement_fields", "register_operations", "try_start",
                "complete_directive", "request_session_cancel", "seal_final_delivery",
                "start_terminal_message", "start_response_send", "claim_write_started",
                "publish_authoritative", "send_slot", "request_transport_teardown",
                "_apply_send_consequence_locked",
                "_recompute_effect_and_cost_locked",
            },
        },
        "src/optimus/acp/spec.py": {"AcpDuplexAdapter": {"_placeholder_settlement"}},
        "src/optimus/acp/outbound_writer.py": {
            "DedicatedOutboundWriter": {"__init__", "submit", "_process_item"},
        },
        "src/optimus/acp/conversation.py": {
            "ConversationSanitizer": {"__init__"},
            "ConversationState": {"__init__", "prepare_commit", "commit_after_final_flush"},
        },
    }

    def authority_segments(path: str, text: str) -> dict[str, tuple[bytes, int]]:
        tree = ast.parse(text, filename=path)
        segments: dict[str, tuple[bytes, int]] = {}
        for node in tree.body:
            if path == _SETTLEMENT_PATH and isinstance(node, ast.ClassDef) and node.name in _VOCABULARY_NAMES:
                segments[node.name] = (ast.get_source_segment(text, node).encode("utf-8"), node.lineno)
            if path == _SETTLEMENT_PATH and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {
                "_send_outcome_to_delivery_value", "final_delivery_for_outcome",
                "rpc_response_delivery_for_outcome", "compute_effect_state",
            }:
                segments[node.name] = (ast.get_source_segment(text, node).encode("utf-8"), node.lineno)
            if path == "src/optimus/acp/outbound_writer.py" and isinstance(node, ast.FunctionDef) and node.name == "classify_physical_outcome":
                segments[node.name] = (ast.get_source_segment(text, node).encode("utf-8"), node.lineno)
            class_requests = selected_methods.get(path, {})
            requested = class_requests.get(node.name) if isinstance(node, ast.ClassDef) and node.name in class_requests else set()
            if requested is None:
                segments[node.name] = (ast.get_source_segment(text, node).encode("utf-8"), node.lineno)
            elif requested and isinstance(node, ast.ClassDef):
                for statement in node.body:
                    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)) and statement.name in requested:
                        segments[f"{node.name}.{statement.name}"] = (
                            ast.get_source_segment(text, statement).encode("utf-8"),
                            statement.lineno,
                        )
        return segments

    definition_citations: dict[str, str] = {}
    for path in _TRANSITION_PATHS:
        before = authority_segments(path, merged.read_text(path))
        after = authority_segments(path, overlay.read_text(path))
        local = authority_segments(path, (root / path).read_text(encoding="utf-8"))
        before_bytes = {name: segment for name, (segment, _) in before.items()}
        after_bytes = {name: segment for name, (segment, _) in after.items()}
        local_bytes = {name: segment for name, (segment, _) in local.items()}
        if not before or before_bytes != after_bytes or local_bytes != before_bytes:
            raise ValueError(f"production transition authority bytes drifted for {path}")
        definition_citations.update({
            name: f"{path}:{line}:{name}#sha256:{hashlib.sha256(segment).hexdigest()}"
            for name, (segment, line) in before.items()
        })

    from optimus.acp.conversation import (
        ConversationOutcome,
        ConversationSanitizer,
        ConversationSanitizerInputs,
        ConversationState,
    )
    from optimus.acp.lifecycle import DirectiveKind, TurnControl
    from optimus.acp.outbound_writer import (
        DedicatedOutboundWriter,
        OutboundQueueItem,
    )
    from optimus.acp.settlement import (
        ConversationCommit,
        EffectState,
        FinalDelivery,
        RpcResponseDelivery,
        SendOutcome,
        SendState,
        Settlement,
    )
    from optimus.acp.spec import AcpDuplexAdapter

    vocabulary = derive_delivery_vocabulary(merged, overlay)
    for enum_type in (
        SendState, SendOutcome, Settlement, FinalDelivery, RpcResponseDelivery,
        ConversationCommit, EffectState,
    ):
        if {member.name: member.value for member in enum_type} != vocabulary[enum_type.__name__]:
            raise ValueError(f"loaded production {enum_type.__name__} does not match immutable source")
    return _TransitionAuthority(
        send_outcome=SendOutcome,
        turn_control=TurnControl,
        directive_kind=DirectiveKind,
        acp_duplex_adapter=AcpDuplexAdapter,
        dedicated_outbound_writer=DedicatedOutboundWriter,
        outbound_queue_item=OutboundQueueItem,
        conversation_state=ConversationState,
        conversation_sanitizer=ConversationSanitizer,
        conversation_sanitizer_inputs=ConversationSanitizerInputs,
        conversation_outcome=ConversationOutcome,
        effect_state_type=EffectState,
        conversation_commit_type=ConversationCommit,
        definition_citations=definition_citations,
    )


def _observe(
    seed: int,
    *,
    seed_source: str,
    anchor_commit: str,
    vocabulary: Mapping[str, Mapping[str, str]],
    transition_authority: _TransitionAuthority,
) -> DeliveryObservation:
    del vocabulary
    execution = transition_authority.execute(seed)
    operations = execution.operations
    schedule = tuple(operation.phase for operation in operations)
    return DeliveryObservation(
        seed=seed,
        seed_source=seed_source,
        anchor_commit=anchor_commit,
        schedule=schedule,
        operations=operations,
        site_citations=tuple(operation.citation for operation in operations),
        vocabulary_names=_VOCABULARY_NAMES,
        scenario=execution.scenario,
        write_attempted=execution.write_attempted,
        flush_attempted=execution.flush_attempted,
        cancellation_timing=execution.cancellation_timing,
        cancellation_result=execution.cancellation_result,
        primary_conversation_record_count=execution.primary_conversation_record_count,
        send_state=execution.send_state,
        send_outcome=execution.send_outcome,
        settlement=execution.settlement,
        final_delivery=execution.final_delivery,
        rpc_response_delivery=execution.rpc_response_delivery,
        conversation_commit=execution.conversation_commit,
        effect_state=execution.effect_state,
        classification=Classification.CANONICAL,
        contradiction=None,
    )


def delivery_schedule_observations(
    *,
    anchor_commit: str,
    literal: tuple[int, ...] | None = None,
    derived_count: int = 1_000,
    discovered_sites: tuple[DiscoveredSite, ...],
    vocabulary: Mapping[str, Mapping[str, str]],
    transition_authority: _TransitionAuthority,
) -> tuple[DeliveryObservation, ...]:
    frozen = literal_seeds() if literal is None else tuple(literal)
    if frozen != literal_seeds():
        raise ValueError("literal corpus must be replayed unchanged")
    if derived_count != 1_000:
        raise ValueError("H4 requires exactly 1,000 commit-derived seeds")
    if not discovered_sites or any(site.classification is Classification.UNCLASSIFIED for site in discovered_sites):
        raise ValueError("H4 schedules require a complete classified production-derived inventory")
    literal_observations = tuple(
        _observe(
            seed, seed_source="frozen-literal", anchor_commit=anchor_commit,
            vocabulary=vocabulary, transition_authority=transition_authority,
        )
        for seed in frozen
    )
    derived_observations = tuple(
        _observe(
            derived_seed(anchor_commit, "H4-delivery", index),
            seed_source="commit-derived",
            anchor_commit=anchor_commit,
            vocabulary=vocabulary,
            transition_authority=transition_authority,
        )
        for index in range(derived_count)
    )
    return literal_observations + derived_observations


def _coverage_assessments(
    vocabulary: Mapping[str, Mapping[str, str]],
    observations: tuple[DeliveryObservation, ...],
) -> tuple[VocabularyCoverageAssessment, ...]:
    assessments: list[VocabularyCoverageAssessment] = []
    for field_name, type_name in _COVERAGE_FIELDS:
        vocabulary_values = tuple(sorted(set(vocabulary[type_name].values())))
        observed_values = tuple(sorted({getattr(item, field_name) for item in observations}))
        missing_values = tuple(sorted(set(vocabulary_values) - set(observed_values)))
        scope_out = _SCOPE_OUTS.get(field_name)
        if missing_values and scope_out is None:
            raise ValueError(f"missing coverage values require an owned scope-out for {field_name}")
        if not missing_values and scope_out is not None:
            raise ValueError(f"obsolete coverage scope-out for {field_name}")
        assessments.append(VocabularyCoverageAssessment(
            field_name=field_name,
            type_name=type_name,
            vocabulary_values=vocabulary_values,
            observed_values=observed_values,
            missing_values=missing_values,
            status=(
                CoverageAssessmentStatus.SCOPED_OUT
                if missing_values
                else CoverageAssessmentStatus.FULLY_OBSERVED
            ),
            reason=scope_out[0] if scope_out else None,
            owner=_COVERAGE_OWNER if scope_out else None,
            next_gate=scope_out[1] if scope_out else None,
        ))
    return tuple(assessments)


def _constant_metadata_notes() -> tuple[ConstantMetadataNote, ...]:
    return (
        ConstantMetadataNote(
            field_name="classification",
            constant_value=Classification.CANONICAL.value,
            claim_status=MetadataClaimStatus.NOT_A_VOCABULARY_CLAIM,
            reason=(
                "Classification is static-site lineage represented by discovered sites and findings; "
                "schedule rows do not claim classification-vocabulary coverage."
            ),
        ),
        ConstantMetadataNote(
            field_name="complete",
            constant_value=True,
            claim_status=MetadataClaimStatus.NOT_A_VOCABULARY_CLAIM,
            reason=(
                "Complete means closed observation-record shape only; it is not a settled-vocabulary "
                "coverage claim."
            ),
        ),
        ConstantMetadataNote(
            field_name="contradiction",
            constant_value=None,
            claim_status=MetadataClaimStatus.NOT_A_VOCABULARY_CLAIM,
            reason=(
                "Contradiction belongs to the static contradiction search; no schedule row executes a "
                "contradictory site."
            ),
        ),
    )


def build_h4_audit_artifact(
    *, merged: SourceTree, overlay: SourceTree, merged_commit: str, overlay_commit: str,
) -> AuditArtifact:
    vocabulary = derive_delivery_vocabulary(merged, overlay)
    transition_authority = derive_transition_authority(merged, overlay)
    sites = discover_delivery_sites(merged, overlay=overlay)
    observations = delivery_schedule_observations(
        anchor_commit=merged_commit,
        literal=literal_seeds(),
        derived_count=1_000,
        discovered_sites=sites,
        vocabulary=vocabulary,
        transition_authority=transition_authority,
    )
    citations = tuple(sorted(_citation(site) for site in sites))
    contradictory_citations = tuple(sorted(
        _citation(site) for site in sites if site.classification is Classification.CONTRADICTORY
    ))
    inventory_digest = _canonical_digest([site.to_dict() for site in sites])
    schedule_digest = _canonical_digest([observation.to_dict() for observation in observations])
    counts = Counter(observation.classification.value for observation in observations)
    summary = ScheduleObservationSummary(
        literal_seeds=literal_seeds(),
        derived_seed_count=1_000,
        derived_seed_anchor_commit=merged_commit,
        total_observation_count=len(observations),
        complete_observation_count=len(observations),
        observation_closure_status=ObservationClosureStatus.FULLY_STRUCTURALLY_CLOSED,
        vocabulary_coverage_status=VocabularyCoverageStatus.PARTIAL_WITH_SCOPE_OUTS,
        classification_counts={item.value: counts[item.value] for item in Classification},
        digest=schedule_digest,
        vocabulary={name: dict(members) for name, members in vocabulary.items()},
        coverage_assessments=_coverage_assessments(vocabulary, observations),
        constant_metadata_notes=_constant_metadata_notes(),
        observations=observations,
    )
    record = EvidenceRecord(
        record_id="ER-H4-DELIVERY",
        hypothesis_id="H4",
        subject="Delivery settlement from queue admission through effect and conversation commit",
        baseline_scope=BaselineScope.BOTH_ALIGNED,
        baseline_anchor_commit=merged_commit,
        overlay_commit=overlay_commit,
        binding_commit=None,
        vocabulary_names=_VOCABULARY_NAMES,
        symbol_citations=citations,
        discovered_sites=sites,
        contradiction_search=ContradictionSearchRecord(
            searched_reference_count=len(sites),
            contradictory_site_count=len(contradictory_citations),
            contradictory_citations=contradictory_citations,
            conclusion=(
                "Mechanical role and control-flow comparison found classified contradictions; they remain findings pending G2."
                if contradictory_citations
                else "Mechanical role and control-flow comparison found no contradictory delivery paths."
            ),
        ),
        schedule_observations=summary,
        commands=(
            "uv run --frozen pytest tests/unit/acp/test_plan1126_delivery_contract.py::test_delivery_contract_ast_covers_all_send_sites -q",
            "uv run --frozen pytest tests/unit/acp/test_plan1126_delivery_contract.py::test_delivery_contract_model_1000_seed_schedule -q",
        ),
        ruling=(
            "The seven source-derived settled delivery types remain the canonical vocabulary. "
            "Bypasses, divergence, and contradictions remain audit findings pending external G2 review."
        ),
        reviewer_status=ReviewerStatus.PENDING_G2,
        content_free_evidence=(
            EvidenceReference("H4-AST-INVENTORY", BaselineScope.BOTH_ALIGNED, inventory_digest),
            EvidenceReference("H4-SCHEDULE-OBSERVATIONS", BaselineScope.BOTH_ALIGNED, schedule_digest),
        ),
    )
    findings: list[Finding] = []
    for classification, scope in sorted(
        {(site.classification, site.baseline_scope) for site in sites},
        key=lambda item: (item[0].value, item[1].value),
    ):
        group = tuple(
            site for site in sites
            if site.classification is classification and site.baseline_scope is scope
        )
        findings.append(Finding(
            finding_id=f"H4-{classification.value}-{scope.value}",
            subject=f"H4 delivery sites classified {classification.value} with {scope.value} lineage",
            classification=classification,
            baseline_scope=scope,
            symbols=tuple(_citation(site) for site in group),
            evidence=(EvidenceReference(
                f"H4-SITES-{classification.value}-{scope.value}",
                scope,
                _canonical_digest([site.to_dict() for site in group]),
            ),),
            owner="Plan 11.26 / P11-FEAT-ZED-RESUME for baseline reconciliation",
            ruling="Recorded as audit evidence; Plan 11.26 performs no production repair.",
        ))
    return AuditArtifact(
        schema_version="plan-11-26-runtime-audit-v1",
        merged_commit=merged_commit,
        overlay_commit=overlay_commit,
        binding_commit=None,
        baseline_reconciliation_status="UNRESOLVED",
        running_artifact_provenance=None,
        static_audit_status=LiveStatus.PARTIAL,
        runtime_characterization_status=LiveStatus.PARTIAL,
        live_redis_status=LiveStatus.UNRUN,
        acpx_status=LiveStatus.UNRUN,
        additional_client_status=LiveStatus.UNRUN,
        zed_status=LiveStatus.UNRUN,
        live_interoperability_status=LiveStatus.UNRUN,
        findings=tuple(findings),
        discovered_multipliers={"cancellation_points": 0, "queues": 0, "sinks": 0, "close_paths": 0},
        computed_run_cost={
            "cancellation_concurrency_levels": [2, 4, 8],
            "cancellation_schedules": 0,
            "cancellation_control_schedules": 0,
            "queue_admissions": 0,
            "sink_failure_runs": 0,
            "idempotent_close_invocations": 0,
            "scenario_p50_ms": {},
            "scenario_p95_ms": {},
        },
        gate_status=GateStatus.INCOMPLETE,
        evidence_records=(record,),
    )
