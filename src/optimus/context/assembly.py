"""Host prompt assembly for an attached Context Engine (Plan 12.2 Task 9).

Design spec 4.2, 7 and 8; Task 1 contracts 5. An attached turn has three separate inputs:

- the current prompt, which is the task;
- the selection text: the current prompt, the exact head and tail turns and every protected record.
  It alone selects workspace files and skills. A summary or an omitted turn never selects anything,
  so a follow-up that refers only to dropped context gets no file hint (a disclosed limitation);
- the conversation envelope: the rendered view, model history only, with every protected record
  exact, plans inert and any summary inside its host wrapper.

`AttachedTurn` captures the turn's history, strategy and checkpoint synchronously, before any await a
setter could interleave with. It then prepares the view off the event loop. A view the engine cannot
build is checked by `probe_floor`, a pure measure of the full committed history plus the provisional
current prompt. At most `CONVERSATION_MAX_BYTES` falls back to the full history; anything larger is
refused with nothing dispatched, and the caller keeps the thread OPEN. As the runner's `ContextPacker`,
the turn fits every complete request to the route's usable input, repacking the view of the same
captured history within finite repack and maintenance allowances.

The admitted context and its digest never change after admission. A stored plan is bound to that
digest, so applying it reuses the admitted request, never a newly summarized view.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from context_engine import (
    STRATEGIES,
    HistoryRevision,
    HistorySnapshot,
    MaintenanceRequest,
    MaintenanceResult,
    OrdinaryTurn,
    PreparedView,
    StrategyParameters,
    SummaryCheckpoint,
    ViewLimits,
    publish_checkpoint,
)
from context_engine.selection import render_ordinary_turn, render_protected_state
from context_engine.summary import render_summary_block
from optimus.acp.conversation import (
    CONVERSATION_MAX_BYTES,
    ConversationSanitizer,
    ConversationTurn,
    mark_inert_plan,
    provisional_turn,
    rendered_byte_length,
)
from optimus.context.adapter import ApprovalFact, make_history_snapshot
from optimus.context.maintenance import (
    AttemptIntegrityError,
    HostMaintenance,
    MaintenanceIdentity,
    MaintenanceReceipt,
    SummarizerFactory,
    SummarizerRoute,
    first_error,
)
from optimus.runtime.modes import ExecutionMode

__all__ = [
    "AdmittedContext",
    "AttachedTurn",
    "ContextAttachment",
    "ContextFault",
    "ContextOutcome",
    "DispatchReading",
    "SummarizerRoute",
    "admitted_context_digest",
    "build_selection_text",
    "full_history_view",
    "probe_floor",
    "render_context_view",
]

STATE_HEADER = (
    "Exact execution record (host facts for every committed turn; "
    "an earlier approval never authorizes a new change):"
)
_ADMITTED_DOMAIN = b"optimus/admitted-context/v1\x00"


class ViewEngine(Protocol):
    """`context_engine.engine.ContextEngine`, or a host-supplied engine with the same contract."""

    def prepare_view(
        self,
        snapshot: HistorySnapshot,
        *,
        strategy: str,
        parameters: StrategyParameters,
        limits: ViewLimits,
        checkpoint: SummaryCheckpoint | None,
        maintenance: Callable[[MaintenanceRequest], MaintenanceResult],
        cancelled: Callable[[], bool],
    ) -> PreparedView: ...


# --- The pure floor probe ------------------------------------------------------------------------


def probe_floor(records: Mapping[int, ConversationTurn], sanitized_prompt: str, *, turn_seq: int | None = None) -> int:
    """Floor bytes for the full committed history plus the provisional current prompt, measured as
    admission measures them. Pure: it never changes a disposition (design spec 8.2)."""
    seq = turn_seq if turn_seq is not None else max(records, default=0) + 1
    if seq in records:
        raise ValueError(f"turn {seq} is already committed")
    provisional = dict(records)
    provisional[seq] = provisional_turn(sanitized_prompt)
    return rendered_byte_length(provisional)


# --- Rendering and selection ---------------------------------------------------------------------


def _check(snapshot: HistorySnapshot, view: PreparedView) -> dict[int, OrdinaryTurn]:
    if not view.available:
        raise ValueError("an unavailable view has nothing to render")
    if view.protected != snapshot.protected:
        raise ValueError("the view does not carry the snapshot's protected records")
    parts = (*view.head_turn_ids, *view.covered_turn_ids, *view.tail_turn_ids, *view.omitted_turn_ids)
    if tuple(sorted(parts)) != snapshot.ids:
        raise ValueError("the view does not partition the snapshot's turns")
    return {turn.seq: turn for turn in snapshot.turns}


def _ids(ids: Sequence[int]) -> str:
    return ", ".join(str(seq) for seq in ids) if ids else "none"


def _exact_turn(turn: OrdinaryTurn) -> str:
    record = {
        "seq": turn.seq,
        "user_prompt": turn.user_prompt,
        "plan_text": mark_inert_plan(turn.plan_text),
        "completion_text": turn.completion_text,
    }
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def render_context_view(snapshot: HistorySnapshot, view: PreparedView) -> str:
    """The model-facing history for a view: every protected record exact, a manifest of which turns
    are exact, summarized or omitted, then the exact head, the wrapped summary and the exact tail."""
    by_seq = _check(snapshot, view)
    lines = [STATE_HEADER, *(render_protected_state(state) for state in view.protected)]
    exact = (*view.head_turn_ids, *view.tail_turn_ids)
    lines.append(
        f"View: exact turns: {_ids(exact)}; summarized turns: {_ids(view.covered_turn_ids)}; "
        f"omitted turns: {_ids(view.omitted_turn_ids)}."
    )
    lines.extend(_exact_turn(by_seq[seq]) for seq in view.head_turn_ids)
    if view.checkpoint is not None:
        lines.append(render_summary_block(view.checkpoint))
    lines.extend(_exact_turn(by_seq[seq]) for seq in view.tail_turn_ids)
    return "\n".join(lines)


def build_selection_text(prompt: str, snapshot: HistorySnapshot, view: PreparedView) -> str:
    """What selects workspace files and skills: the current prompt first, then the exact turns'
    ordinary text, then every protected record. Never summary text, never an omitted turn."""
    by_seq = _check(snapshot, view)
    parts = [prompt]
    for seq in (*view.head_turn_ids, *view.tail_turn_ids):
        turn = by_seq[seq]
        parts.extend(text for text in (turn.user_prompt, turn.plan_text, turn.completion_text) if text)
    parts.extend(render_protected_state(state) for state in view.protected)
    return "\n".join(parts)


def full_history_view(snapshot: HistorySnapshot) -> PreparedView:
    """Every committed turn exact: the stated fallback when the engine cannot build a view."""
    return PreparedView((), snapshot.ids, None, snapshot.protected, (), (), True, None)


# --- The admitted context ------------------------------------------------------------------------


def _frame(*parts: bytes) -> bytes:
    return b"".join(len(part).to_bytes(8, "big") + part for part in parts)


def admitted_context_digest(
    *,
    mode: ExecutionMode,
    strategy: str,
    applied: str,
    revision: HistoryRevision,
    parameters_digest: str,
    registry_hash: str,
    model_id: str,
    estimator_id: str,
    current_prompt: str,
    selection_text: str,
    conversation_envelope: str,
) -> str:
    """The identity a stored plan is bound to: host-rendered sanitized bytes and the policy and
    revision identities they came from, never a summarizer's claim."""
    fields = (
        mode.value,
        strategy,
        applied,
        revision.session_key,
        str(revision.generation),
        str(revision.last_committed_seq),
        revision.digest,
        parameters_digest,
        registry_hash,
        model_id,
        estimator_id,
        current_prompt,
        selection_text,
        conversation_envelope,
    )
    return hashlib.sha256(_ADMITTED_DOMAIN + _frame(*(field.encode("utf-8") for field in fields))).hexdigest()


@dataclass(frozen=True, slots=True)
class AdmittedContext:
    """What one attached turn was admitted with. `applied` is `view` or `full_history` (fallback)."""

    mode: ExecutionMode
    strategy: str
    applied: str
    revision: HistoryRevision
    view: PreparedView
    current_prompt: str
    selection_text: str
    conversation_envelope: str
    digest: str


@dataclass(frozen=True, slots=True)
class DispatchReading:
    """One planning/answer input actually sent: its estimated size and that request's usable input
    capacity (design spec 8.4)."""

    tokens: int
    capacity: int

    @staticmethod
    def largest(readings: Sequence[DispatchReading]) -> DispatchReading | None:
        """The meter reading for a turn: the largest input sent, the smaller capacity on a tie; None
        when nothing was sent, so no reading is fabricated."""
        if not readings:
            return None
        return max(readings, key=lambda reading: (reading.tokens, -reading.capacity))


# The engine's fixed unavailable reasons, mapped to a bounded diagnostic vocabulary. A reason not
# listed here is reported as "other", never verbatim (Codex CP3 ruling M2).
_REASON_CATEGORIES = {
    "source exceeds limit": "capacity",
    "exact authority exceeds history capacity": "capacity",
    "history capacity too small for a summary": "capacity",
    "maintenance input exceeded": "capacity",
    "turn exceeds maintenance input": "capacity",
    "maintenance unavailable": "maintenance_unavailable",
    "maintenance allowance exceeded": "maintenance_unavailable",
    "maintenance failed": "maintenance_failed",
    "summary exceeds bound": "summary_rejected",
    "summary malformed": "summary_rejected",
}
FAULT_CATEGORIES = frozenset({*_REASON_CATEGORIES.values(), "config_error", "engine_error", "maintenance_error", "other"})


@dataclass(frozen=True, slots=True)
class ContextFault:
    """Why an attached view was not built, content-free (Codex CP3 ruling M2): the phase (`prepare`
    for the admitted view, `repack` for a smaller one) and a bounded category. It never carries
    exception text, history, a summary, a credential or the engine's reason string."""

    phase: Literal["prepare", "repack"]
    category: str

    def __post_init__(self) -> None:
        if self.phase not in {"prepare", "repack"} or self.category not in FAULT_CATEGORIES:
            raise ValueError("a context fault needs a known phase and category")


@dataclass(frozen=True, slots=True)
class ContextOutcome:
    """How preparing a turn's context ended. `unavailable` and `cancelled` dispatch nothing."""

    kind: Literal["view", "fallback", "unavailable", "cancelled"]
    reason: str | None = None
    floor_bytes: int | None = None


# --- Attachment configuration --------------------------------------------------------------------


@dataclass(frozen=True)
class ContextAttachment:
    """A configured attached Context Engine for new sessions.

    Every bound is explicit: the attached source class and per-turn record reservation (D2, measured
    before activation), the policy history allocation and maintenance bounds in `limits`, the
    planning/answer route's usable input and its verified estimator, and a finite repack allowance.
    No production path constructs one yet; activation waits for the measured policy, a qualified
    summarizer receipt and Task 2's production-base proof.
    """

    engine: ViewEngine
    parameters: StrategyParameters
    limits: ViewLimits
    source_max_bytes: int
    record_reservation_bytes: int
    usable_input_tokens: int
    estimate_request: Callable[[str], int]
    registry_hash: str
    model_id: str
    summarizer: SummarizerFactory | None
    summarizer_route: SummarizerRoute | None
    record_receipt: Callable[[MaintenanceReceipt], None]
    max_repacks: int
    initial_strategy: str = "compaction"

    def __post_init__(self) -> None:
        if not isinstance(self.parameters, StrategyParameters) or not isinstance(self.limits, ViewLimits):
            raise ValueError("an attachment needs StrategyParameters and ViewLimits")
        if self.source_max_bytes <= 0:
            raise ValueError("the attached source limit must be positive")
        if not 0 <= self.record_reservation_bytes < self.source_max_bytes:
            raise ValueError("the record reservation must be below the source limit")
        if self.usable_input_tokens <= 0 or self.max_repacks < 0:
            raise ValueError("usable input must be positive and the repack allowance finite")
        if self.initial_strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy {self.initial_strategy!r}")
        if self.summarizer is not None and self.summarizer_route is None:
            raise ValueError("a summarizer needs its exact route identity")


# --- One attached turn ---------------------------------------------------------------------------


class _TurnMaintenance:
    """The engine's maintenance callback for one turn, with a finite turn-wide call allowance shared
    by the admitted view and every repack. Without a summarizer, nothing is ever called."""

    def __init__(self, host: HostMaintenance | None, allowance: int) -> None:
        self._host = host
        self._allowance = allowance
        self.calls = 0
        self.raised = False

    def __call__(self, request: MaintenanceRequest) -> MaintenanceResult:
        if self._host is None:
            return MaintenanceResult(summary_text=None, attempt_ids=(), status="unavailable", finish_status=None)
        if self.calls >= self._allowance:
            return MaintenanceResult(summary_text=None, attempt_ids=(), status="allowance_exhausted", finish_status=None)
        self.calls += 1
        try:
            return self._host(request)
        except BaseException:
            # Lets the engine boundary tell a host maintenance failure from an engine fault.
            self.raised = True
            raise


class AttachedTurn:
    """One attached turn: captured settings and history, its view, and the runner's `ContextPacker`."""

    def __init__(
        self,
        *,
        attachment: ContextAttachment,
        session_key: str,
        records: Mapping[int, ConversationTurn],
        approvals: Mapping[int, tuple[ApprovalFact, ...]],
        generation: int,
        sanitizer: ConversationSanitizer,
        strategy: str,
        mode: ExecutionMode,
        checkpoint: SummaryCheckpoint | None,
        current_prompt: str,
        turn_seq: int,
        cancelled: Callable[[], bool],
        deliver_notice: Callable[[str], bool] | None = None,
        record_receipt: Callable[[MaintenanceReceipt], None] | None = None,
        record_integrity_failure: Callable[[MaintenanceReceipt], None] | None = None,
    ) -> None:
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy {strategy!r}")
        self._attachment = attachment
        self._session_key = session_key
        self._records = records
        self._approvals = approvals
        self._generation = generation
        self._sanitizer = sanitizer
        self._strategy = strategy
        self._mode = mode
        self._checkpoint = checkpoint
        self._current_prompt = current_prompt
        self._turn_seq = turn_seq
        self._cancelled = cancelled
        # A turn without a notice channel can deliver no required notice, so it sends nothing that needs one.
        self._deliver_notice = deliver_notice if deliver_notice is not None else (lambda text: False)
        self._dispatches: list[DispatchReading] = []
        # The turn's own receipt sink (its session's settlement), alongside the attachment's.
        self._record_receipt = record_receipt
        # Told of a receipt the attachment's ledger refused, so the turn's settlement never reads complete.
        self._record_integrity_failure = record_integrity_failure
        self._sink_error: Exception | None = None
        self._snapshot: HistorySnapshot | None = None
        self._maintenance: _TurnMaintenance | None = None
        self._view: PreparedView | None = None
        self._envelope = ""
        self._fallback = False
        self._faults: list[ContextFault] = []
        self._faults_lock = threading.Lock()
        self.admitted: AdmittedContext | None = None
        self.candidate: SummaryCheckpoint | None = None
        self.repacks = 0

    @classmethod
    def capture(
        cls,
        *,
        attachment: ContextAttachment,
        session_key: str,
        records: Mapping[int, ConversationTurn],
        approvals: Mapping[int, Sequence[ApprovalFact]],
        generation: int,
        sanitizer: ConversationSanitizer,
        strategy: str,
        mode: ExecutionMode,
        checkpoint: SummaryCheckpoint | None,
        current_prompt: str,
        turn_seq: int,
        cancelled: Callable[[], bool],
        deliver_notice: Callable[[str], bool] | None = None,
        record_receipt: Callable[[MaintenanceReceipt], None] | None = None,
        record_integrity_failure: Callable[[MaintenanceReceipt], None] | None = None,
    ) -> AttachedTurn:
        """Copy everything the turn depends on now, before any await: later commits and setters
        cannot reach it. Approval facts of a turn that never committed are left out."""
        committed = dict(records)
        return cls(
            attachment=attachment,
            session_key=session_key,
            records=committed,
            approvals={seq: tuple(facts) for seq, facts in approvals.items() if seq in committed},
            generation=generation,
            sanitizer=sanitizer,
            strategy=strategy,
            mode=mode,
            checkpoint=checkpoint,
            current_prompt=current_prompt,
            turn_seq=turn_seq,
            cancelled=cancelled,
            deliver_notice=deliver_notice,
            record_receipt=record_receipt,
            record_integrity_failure=record_integrity_failure,
        )

    @property
    def strategy(self) -> str:
        """The strategy captured at admission; a later setter never changes it."""
        return self._strategy

    @property
    def maintenance_calls(self) -> int:
        return self._maintenance.calls if self._maintenance is not None else 0

    @property
    def fallback(self) -> bool:
        return self._fallback

    def take_faults(self) -> tuple[ContextFault, ...]:
        """The faults recorded since the last call, for the host's content-free diagnostic."""
        with self._faults_lock:
            faults, self._faults = tuple(self._faults), []
        return faults

    def _fault(self, phase: Literal["prepare", "repack"], category: str) -> None:
        with self._faults_lock:
            self._faults.append(ContextFault(phase, category))

    def prepare(self) -> ContextOutcome:
        """Build the snapshot and the turn's view. Synchronous: call it off the event loop."""
        snapshot = make_history_snapshot(
            session_key=self._session_key,
            generation=self._generation,
            records=self._records,
            approvals=self._approvals,
            sanitizer=self._sanitizer,
        )
        self._snapshot = snapshot
        attachment = self._attachment
        host = None
        if attachment.summarizer is not None and attachment.summarizer_route is not None:
            route = attachment.summarizer_route
            identity = MaintenanceIdentity(
                session_id=self._session_key,
                turn_seq=self._turn_seq,
                model_id=route.model_id,
                role=route.role,
                route=route.route,
                reasoning=route.reasoning,
                quantizations=route.quantizations,
                strategy=self._strategy,
                revision_digest=snapshot.revision.digest,
                registry_hash=attachment.registry_hash,
            )
            try:
                call = attachment.summarizer(identity, self._deliver_notice)
            except Exception:  # noqa: BLE001 - a summarizer that cannot bind this identity makes no call
                # Nothing was sent, so nothing is owed; the turn proceeds without summaries and the
                # operator sees a content-free config fault (Codex CP3 ruling R5 and M2).
                self._fault("prepare", "config_error")
            else:
                host = HostMaintenance(
                    call=call,
                    sanitizer=self._sanitizer,
                    identity=identity,
                    record_receipt=self._receipt_sink,
                    cancelled=self._cancelled,
                )
        self._maintenance = _TurnMaintenance(host, attachment.parameters.max_maintenance_calls)
        if self._cancelled():
            return ContextOutcome("cancelled")
        view = self._prepare_view(attachment.limits.history_input_tokens, self._checkpoint, phase="prepare")
        if self._cancelled():
            return ContextOutcome("cancelled")
        if view.available:
            self.candidate = view.checkpoint
            self._admit("view", view)
            return ContextOutcome("view")
        floor = probe_floor(self._records, self._current_prompt, turn_seq=self._turn_seq)
        if floor > CONVERSATION_MAX_BYTES:
            return ContextOutcome("unavailable", reason=view.reason, floor_bytes=floor)
        self._fallback = True
        self._admit("full_history", full_history_view(snapshot))
        return ContextOutcome("fallback", reason=view.reason, floor_bytes=floor)

    def _prepare_view(
        self, history_tokens: int, checkpoint: SummaryCheckpoint | None, *, phase: Literal["prepare", "repack"]
    ) -> PreparedView:
        assert self._snapshot is not None and self._maintenance is not None
        limits = dataclasses.replace(self._attachment.limits, history_input_tokens=history_tokens)
        self._maintenance.raised = False
        try:
            view = self._attachment.engine.prepare_view(
                self._snapshot,
                strategy=self._strategy,
                parameters=self._attachment.parameters,
                limits=limits,
                checkpoint=checkpoint,
                maintenance=self._maintenance,
                cancelled=self._cancelled,
            )
        except Exception as exc:  # noqa: BLE001 - an engine fault is an unavailable view, never a closed thread
            if self._sink_error is not None:
                # Recording a paid attempt failed (for example a conflicting receipt): an accounting
                # integrity error, surfaced rather than hidden as a fallback (Fable CP3 review MAJOR-3).
                raise self._sink_error from exc
            if isinstance(exc, AttemptIntegrityError):
                # A summarizer attempt the Gateway's report cannot attribute: an integrity error,
                # surfaced like a receipt conflict, never hidden as a fallback (Fable CP3 correction
                # review MINOR-1).
                raise
            self._fault(phase, "maintenance_error" if self._maintenance.raised else "engine_error")
            return PreparedView((), (), None, self._snapshot.protected, (), (), False, "engine fault")
        if self._sink_error is not None:
            raise self._sink_error  # an engine that swallowed the failure still cannot hide it
        if not view.available and view.reason != "cancelled":  # a cancelled turn is not a fault
            self._fault(phase, _REASON_CATEGORIES.get(view.reason or "", "other"))
        return view

    def _admit(self, applied: str, view: PreparedView) -> None:
        assert self._snapshot is not None
        envelope = render_context_view(self._snapshot, view)
        selection = build_selection_text(self._current_prompt, self._snapshot, view)
        attachment = self._attachment
        digest = admitted_context_digest(
            mode=self._mode,
            strategy=self._strategy,
            applied=applied,
            revision=self._snapshot.revision,
            parameters_digest=attachment.parameters.digest,
            registry_hash=attachment.registry_hash,
            model_id=attachment.model_id,
            estimator_id=attachment.limits.estimator_id,
            current_prompt=self._current_prompt,
            selection_text=selection,
            conversation_envelope=envelope,
        )
        self.admitted = AdmittedContext(
            mode=self._mode,
            strategy=self._strategy,
            applied=applied,
            revision=self._snapshot.revision,
            view=view,
            current_prompt=self._current_prompt,
            selection_text=selection,
            conversation_envelope=envelope,
            digest=digest,
        )
        self._view, self._envelope = view, envelope

    def checkpoint_to_publish(self, *, current_generation: int, cancelled: bool) -> SummaryCheckpoint | None:
        """The admitted view's checkpoint, if it may be published now: same committed revision and
        parameters, not cancelled. A repack's checkpoint is never published."""
        if self.candidate is None or self._snapshot is None or current_generation != self._generation:
            return None
        published = publish_checkpoint(
            self.candidate,
            current_revision=self._snapshot.revision,
            current_parameters_digest=self._attachment.parameters.digest,
            cancelled=cancelled,
        )
        return self.candidate if published else None

    # --- ContextPacker ---------------------------------------------------------------------------

    def fit(self, build: Callable[[str], str]) -> str | None:
        """The complete request to send, fitted to the route's usable input, or None.

        A full-history fallback is only checked. A view is repacked from the same captured snapshot
        to a smaller history budget, at most `max_repacks` times and within the turn's maintenance
        allowance; the admitted context is unchanged."""
        if self.admitted is None or self._view is None:
            raise RuntimeError("fit() before an admitted view")
        estimate, usable = self._attachment.estimate_request, self._attachment.usable_input_tokens
        text = build(self._envelope)
        over = estimate(text) - usable
        if over <= 0:
            return text
        if self._fallback:
            return None
        view = self._view
        for _ in range(self._attachment.max_repacks):
            if self._cancelled():
                return None
            budget = self._view_cost(view) - over
            if budget < 0:
                return None
            self.repacks += 1
            view = self._prepare_view(budget, view.checkpoint or self._checkpoint, phase="repack")
            if not view.available:
                return None
            assert self._snapshot is not None
            envelope = render_context_view(self._snapshot, view)
            text = build(envelope)
            over = estimate(text) - usable
            if over <= 0:
                self._view, self._envelope = view, envelope
                return text
        return None

    def _receipt_sink(self, receipt: MaintenanceReceipt) -> None:
        # Both sinks are offered the receipt even if the first refuses it, so neither the ledger nor the
        # settlement loses a charge because the other failed; the first failure is then raised as the
        # integrity error it is (Codex CP3 correction ruling C2). A ledger refusal is also reported to the
        # settlement, which would otherwise never learn of it and read complete (Fable CP3 correction-2
        # review MINOR-1).
        errors: list[Exception] = []
        ledger_refused = False
        for sink, is_ledger in ((self._attachment.record_receipt, True), (self._record_receipt, False)):
            if sink is None:
                continue
            try:
                sink(receipt)
            except Exception as exc:  # noqa: BLE001 - offered to both sinks first
                errors.append(exc)
                ledger_refused = ledger_refused or is_ledger
        if ledger_refused and self._record_integrity_failure is not None:
            self._record_integrity_failure(receipt)
        if errors:
            error = first_error(errors)
            if self._sink_error is None:
                self._sink_error = error
            raise error

    def record_dispatch(self, text: str) -> None:
        """The runner is sending `text` as a complete planning/answer request now."""
        self._dispatches.append(DispatchReading(tokens=self._attachment.estimate_request(text), capacity=self._attachment.usable_input_tokens))

    def largest_dispatch(self) -> DispatchReading | None:
        return DispatchReading.largest(self._dispatches)

    def _view_cost(self, view: PreparedView) -> int:
        """A view's history cost as the engine allocates it: authority, exact turns and the summary
        reserve, under the view estimator."""
        assert self._snapshot is not None
        estimate = self._attachment.limits.estimate_history
        by_seq = {turn.seq: turn for turn in self._snapshot.turns}
        cost = sum(estimate(render_protected_state(state)) for state in view.protected)
        cost += sum(estimate(render_ordinary_turn(by_seq[seq])) for seq in (*view.head_turn_ids, *view.tail_turn_ids))
        if view.checkpoint is not None:
            cost += min(self._attachment.parameters.summary_output_tokens, self._attachment.limits.maintenance_output_tokens)
        return cost
