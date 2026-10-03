"""Canonical in-memory ACP conversation state (Plan 11.25 Task 5)."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from urllib.parse import unquote, urlparse

from optimus.acp.settlement import EffectState
from optimus_security.sanitization import (
    EVIDENCE_REDACTION_POLICY,
    PathAliasRule,
    sanitize_for_persistence,
)

CONVERSATION_MAX_BYTES = 524_288
WARNING_FIRST_BYTE = 419_431  # used * 5 >= cap * 4
INERT_PLAN_OPEN = "<<inert_historical_plan>>"
INERT_PLAN_CLOSE = "<</inert_historical_plan>>"

_RECORD_FIELD_ORDER = (
    "user_prompt",
    "plan_text",
    "completion_text",
    "outcome",
    "effect_state",
)


class ConversationDisposition(StrEnum):
    OPEN = "open"
    CAP_CLOSED = "cap_closed"
    DELIVERY_INDETERMINATE = "delivery_indeterminate"


class ConversationOutcome(StrEnum):
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """Five-field turn record. turn_seq is the map key, not a sixth field."""

    user_prompt: str
    plan_text: str
    completion_text: str
    outcome: ConversationOutcome
    effect_state: EffectState

    def as_record_dict(self) -> dict[str, str]:
        plan = mark_inert_plan(self.plan_text) if self.plan_text else ""
        return {
            "user_prompt": self.user_prompt,
            "plan_text": plan,
            "completion_text": self.completion_text,
            "outcome": self.outcome.value,
            "effect_state": self.effect_state.value,
        }


@dataclass(frozen=True, slots=True)
class ConversationSanitizerInputs:
    known_secrets: tuple[str, ...]
    path_aliases: tuple[PathAliasRule, ...]
    known_pii: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    admitted: bool
    sanitized_user_prompt: str
    projected_bytes: int
    turn_seq: int | None
    refuse_reason: str | None = None
    crosses_warning: bool = False


@dataclass(frozen=True, slots=True)
class CommitDecision:
    commit: bool
    turn_seq: int
    projected_bytes: int
    closes_cap: bool
    crosses_warning: bool
    record: ConversationTurn


@dataclass(frozen=True, slots=True)
class UsageGauge:
    used: int
    size: int
    cost: Decimal | None


def mark_inert_plan(plan_text: str) -> str:
    if not plan_text:
        return ""
    return f"{INERT_PLAN_OPEN}{plan_text}{INERT_PLAN_CLOSE}"


def extract_uri_passwords(*uris: str) -> tuple[str, ...]:
    secrets: list[str] = []
    for uri in uris:
        if not uri or not uri.strip():
            continue
        password = urlparse(uri.strip()).password
        if not password:
            continue
        secrets.append(password)
        decoded = unquote(password)
        if decoded and decoded != password:
            secrets.append(decoded)
    return tuple(secrets)


def build_conversation_sanitizer_inputs(
    environ: Mapping[str, str],
    *,
    workspace_root: Path,
) -> ConversationSanitizerInputs:
    secrets: list[str] = []
    api_key = environ.get("OPTIMUS_API_KEY", "").strip()
    if api_key:
        secrets.append(api_key)
    secrets.extend(
        extract_uri_passwords(
            environ.get("OPTIMUS_GATEWAY_URL", ""),
            environ.get("OPTIMUS_REDIS_URL", ""),
        )
    )
    # Deduplicate while preserving order; longest-first is applied by sanitizer.
    deduped: list[str] = []
    seen: set[str] = set()
    for secret in secrets:
        if secret and secret not in seen:
            seen.add(secret)
            deduped.append(secret)
    root = workspace_root.resolve()
    alias = PathAliasRule(source_root=str(root), alias="<workspace>")
    return ConversationSanitizerInputs(
        known_secrets=tuple(deduped),
        path_aliases=(alias,),
        known_pii=(),
    )


class ConversationSanitizer:
    def __init__(self, inputs: ConversationSanitizerInputs) -> None:
        self._inputs = inputs

    @property
    def inputs(self) -> ConversationSanitizerInputs:
        return self._inputs

    def sanitize(self, text: str) -> str:
        result = sanitize_for_persistence(
            text,
            known_secrets=self._inputs.known_secrets,
            known_pii=self._inputs.known_pii,
            path_aliases=self._inputs.path_aliases,
            policy=EVIDENCE_REDACTION_POLICY,
        )
        value = result.value
        if not isinstance(value, str):
            return str(value)
        return value


def render_conversation_envelope(records: Mapping[int, ConversationTurn]) -> str:
    """Deterministic UTF-8 JSON: turn_seq keys wrap five-field records."""
    payload: dict[str, dict[str, str]] = {}
    for turn_seq in sorted(records):
        record = records[turn_seq].as_record_dict()
        # Stable field order in object literals.
        ordered = {key: record[key] for key in _RECORD_FIELD_ORDER}
        payload[str(turn_seq)] = ordered
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def render_model_conversation(records: Mapping[int, ConversationTurn]) -> str:
    """Model-facing history (Plan 12.2 Task 3, F3): turns in numeric order, fields in `_RECORD_FIELD_ORDER`.

    `render_conversation_envelope` sorts its keys, so turn 10 precedes turn 2 and the fields come out
    alphabetically. This renderer emits the same keys and values in their real order, so its byte
    length is identical; the storage serializer alone still measures the floor.
    """
    payload: dict[str, dict[str, str]] = {}
    for turn_seq in sorted(records):
        record = records[turn_seq].as_record_dict()
        payload[str(turn_seq)] = {key: record[key] for key in _RECORD_FIELD_ORDER}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def rendered_byte_length(records: Mapping[int, ConversationTurn]) -> int:
    return len(render_conversation_envelope(records).encode("utf-8"))


def provisional_turn(sanitized_user_prompt: str) -> ConversationTurn:
    """The record an admitted prompt is measured as before it has a plan or reply. Admission and the
    attached engine's pure floor probe (Plan 12.2 Task 9) measure the same record."""
    return ConversationTurn(
        user_prompt=sanitized_user_prompt,
        plan_text="",
        completion_text="",
        outcome=ConversationOutcome.COMPLETED,
        effect_state=EffectState.NONE,
    )


def crosses_warning_threshold(used_bytes: int, source_max_bytes: int = CONVERSATION_MAX_BYTES) -> bool:
    return used_bytes * 5 >= source_max_bytes * 4


class ConversationState:
    """Session-owned transient conversation map, budget, cost, and disposition.

    The engine-absent storage class: `CONVERSATION_MAX_BYTES` and no reservation. An attached Context
    Engine session uses `AttachedConversationState`, which sets its own class.
    """

    # The storage class (Plan 12.2 Task 9). Class-level, so the Plan 11.26 H4-pinned `__init__`,
    # `prepare_commit` and `commit_after_final_flush` stay byte-identical for engine-absent sessions.
    _source_max_bytes: int = CONVERSATION_MAX_BYTES
    _record_reservation_bytes: int = 0
    # Plan 12.2 Task 11 (Codex CP3 ruling R2): each turn's cost as projected from its settled
    # receipts, keyed by turn id. Replaced, never mutated in place, so a reader on another thread
    # always sees one consistent mapping; class-level so the H4-pinned `__init__` stays unchanged.
    _projected_costs: Mapping[str, tuple[Decimal, bool]] = MappingProxyType({})

    def __init__(self, sanitizer: ConversationSanitizer) -> None:
        self._sanitizer = sanitizer
        self._records: dict[int, ConversationTurn] = {}
        self._next_turn_seq = 1
        self._disposition = ConversationDisposition.OPEN
        self._warning_crossed = False
        self._warning_confirmed = False
        self._session_cost = Decimal("0")
        self._cost_complete = True
        self._cost_applied_turns: set[int] = set()

    @property
    def disposition(self) -> ConversationDisposition:
        return self._disposition

    @property
    def records(self) -> Mapping[int, ConversationTurn]:
        return self._records

    @property
    def used_bytes(self) -> int:
        return rendered_byte_length(self._records)

    @property
    def known_cost_usd(self) -> Decimal:
        """Every known cost applied so far, a subtotal when `cost_complete` is False."""
        return self._cost_totals()[0]

    @property
    def source_max_bytes(self) -> int:
        return self._source_max_bytes

    @property
    def generation(self) -> int:
        """A history revision's committed generation: one record is committed per turn, never
        replaced or removed, so the record count advances with every commit."""
        return len(self._records)

    @property
    def sanitizer(self) -> ConversationSanitizer:
        return self._sanitizer

    @property
    def warning_confirmed(self) -> bool:
        return self._warning_confirmed

    @property
    def cost_complete(self) -> bool:
        return self._cost_totals()[1]

    def project_turn_cost(self, turn_id: str, *, known_usd: Decimal, complete: bool) -> None:
        """Set one turn's cost from its settled receipts (Codex CP3 ruling R2).

        A projection, never a debit: the turn's entry is replaced, so the same facts applied twice
        change nothing, and facts that arrive later - after the turn's terminal finalization, from a
        worker left behind by transport teardown - update it to the truth, known subtotal and
        incompleteness alike. Callers serialize projections of one session (its settlement's lock)."""
        self._projected_costs = MappingProxyType({**self._projected_costs, turn_id: (known_usd, complete)})

    def _cost_totals(self) -> tuple[Decimal, bool]:
        projected = self._projected_costs  # one consistent snapshot
        known = self._session_cost + sum((cost for cost, _ in projected.values()), Decimal("0"))
        return known, self._cost_complete and all(complete for _, complete in projected.values())

    def sanitize_text(self, text: str) -> str:
        return self._sanitizer.sanitize(text)

    def prepare_admission(self, raw_user_prompt: str) -> AdmissionDecision:
        sanitized = self._sanitizer.sanitize(raw_user_prompt)
        if self._disposition is not ConversationDisposition.OPEN:
            return AdmissionDecision(
                admitted=False,
                sanitized_user_prompt=sanitized,
                projected_bytes=self.used_bytes,
                turn_seq=None,
                refuse_reason=self._disposition.value,
            )
        turn_seq = self._next_turn_seq
        provisional = dict(self._records)
        provisional[turn_seq] = provisional_turn(sanitized)
        projected = rendered_byte_length(provisional)
        if projected > self._source_max_bytes:
            self._disposition = ConversationDisposition.CAP_CLOSED
            return AdmissionDecision(
                admitted=False,
                sanitized_user_prompt=sanitized,
                projected_bytes=projected,
                turn_seq=None,
                refuse_reason="cap",
                crosses_warning=False,
            )
        if projected + self._record_reservation_bytes > self._source_max_bytes:
            shortest = dict(self._records)
            shortest[turn_seq] = provisional_turn("")
            if rendered_byte_length(shortest) + self._record_reservation_bytes > self._source_max_bytes:
                # Even an empty prompt leaves no room for a reply: genuine exhaustion, which latches
                # (Fable CP3 review MINOR-1).
                self._disposition = ConversationDisposition.CAP_CLOSED
                return AdmissionDecision(
                    admitted=False,
                    sanitized_user_prompt=sanitized,
                    projected_bytes=projected,
                    turn_seq=None,
                    refuse_reason="cap",
                    crosses_warning=False,
                )
            # Not exhaustion: a shorter prompt may still leave room for its reply. Nothing latches.
            return AdmissionDecision(
                admitted=False,
                sanitized_user_prompt=sanitized,
                projected_bytes=projected,
                turn_seq=None,
                refuse_reason="reservation",
                crosses_warning=False,
            )
        return AdmissionDecision(
            admitted=True,
            sanitized_user_prompt=sanitized,
            projected_bytes=projected,
            turn_seq=turn_seq,
            crosses_warning=crosses_warning_threshold(projected, self._source_max_bytes) and not self._warning_confirmed,
        )

    def allocate_turn_seq(self) -> int:
        turn_seq = self._next_turn_seq
        self._next_turn_seq += 1
        return turn_seq

    def apply_planning_cost_once(
        self,
        turn_seq: int,
        *,
        cost_usd: Decimal | None,
        cost_complete: bool,
    ) -> None:
        if turn_seq in self._cost_applied_turns:
            return
        self._cost_applied_turns.add(turn_seq)
        # The known subtotal keeps every known cost, before and after an unknown one (Plan 12.2 Task
        # 11); only the definitive total is withheld once anything is unknown.
        if cost_usd is not None:
            self._session_cost += cost_usd
        if not cost_complete or cost_usd is None:
            self._cost_complete = False

    def prepare_commit(
        self,
        turn_seq: int,
        *,
        sanitized_user_prompt: str,
        sanitized_plan_text: str,
        sanitized_completion_text: str,
        outcome: ConversationOutcome,
        effect_state: EffectState,
    ) -> CommitDecision:
        record = ConversationTurn(
            user_prompt=sanitized_user_prompt,
            plan_text=sanitized_plan_text,
            completion_text=sanitized_completion_text,
            outcome=outcome,
            effect_state=effect_state,
        )
        provisional = dict(self._records)
        provisional[turn_seq] = record
        projected = rendered_byte_length(provisional)
        closes_cap = projected > CONVERSATION_MAX_BYTES
        crosses = crosses_warning_threshold(projected) and not self._warning_confirmed
        return CommitDecision(
            commit=True,
            turn_seq=turn_seq,
            projected_bytes=projected,
            closes_cap=closes_cap,
            crosses_warning=crosses,
            record=record,
        )

    def commit_after_final_flush(self, decision: CommitDecision) -> None:
        self._records[decision.turn_seq] = decision.record
        if decision.turn_seq >= self._next_turn_seq:
            self._next_turn_seq = decision.turn_seq + 1
        if self._disposition is ConversationDisposition.DELIVERY_INDETERMINATE:
            return
        if decision.closes_cap:
            if self._disposition is ConversationDisposition.OPEN:
                self._disposition = ConversationDisposition.CAP_CLOSED

    def latch_delivery_indeterminate(self) -> None:
        self._disposition = ConversationDisposition.DELIVERY_INDETERMINATE

    def note_warning_threshold_for_attempt(self, projected_bytes: int) -> bool:
        """Return True once when a first warning attempt should be scheduled."""
        if self._warning_confirmed or self._warning_crossed:
            return False
        if not crosses_warning_threshold(projected_bytes, self._source_max_bytes):
            return False
        self._warning_crossed = True
        return True

    def rearm_warning_attempt(self) -> None:
        """A warning attempt was not confirmed as delivered: let the next crossing try again.
        A no-op once the warning has been confirmed."""
        if not self._warning_confirmed:
            self._warning_crossed = False

    def confirm_warning_flushed(self) -> None:
        self._warning_confirmed = True
        self._warning_crossed = True

    def usage_gauge(self) -> UsageGauge:
        used = self.used_bytes // 4
        size = self._source_max_bytes // 4
        known, complete = self._cost_totals()
        return UsageGauge(used=used, size=size, cost=known if complete else None)

    def planner_envelope(self) -> str:
        return render_model_conversation(self._records)


COMPLETION_TRUNCATION_MARKER = (
    "\n[This reply was shortened to fit this conversation's storage; outcomes, effects and approvals are kept exactly.]"
)
_LONGEST_OUTCOME = max(ConversationOutcome, key=lambda outcome: len(outcome.value))
_LONGEST_EFFECT = max(EffectState, key=lambda effect: len(effect.value))


class AttachedConversationState(ConversationState):
    """An attached Context Engine session's storage class (Plan 12.2 Task 9; design spec 4.2).

    Its own measured source limit and a per-turn record reservation, fixed at creation and kept
    through any engine fault. Exceeding the source limit is genuine exhaustion and closes the thread
    as before; a prompt that leaves too little room for its reply's reservation is refused
    recoverably, and the thread stays OPEN.

    A committed result must fit: `plan_fits` is checked before approval, against the plan, the
    longest outcome and effect values and the truncation marker. At commit, a reply message that
    would overflow is shortened, with a marker, to fit; the plan, outcome and effect are never
    shortened (Fable CP3 review MAJOR-1).
    """

    def __init__(self, sanitizer: ConversationSanitizer, *, source_max_bytes: int, record_reservation_bytes: int) -> None:
        if source_max_bytes <= 0 or not 0 <= record_reservation_bytes < source_max_bytes:
            raise ValueError("a conversation needs a positive source limit and a reservation below it")
        super().__init__(sanitizer)
        self._source_max_bytes = source_max_bytes
        self._record_reservation_bytes = record_reservation_bytes

    def prepare_commit(
        self,
        turn_seq: int,
        *,
        sanitized_user_prompt: str,
        sanitized_plan_text: str,
        sanitized_completion_text: str,
        outcome: ConversationOutcome,
        effect_state: EffectState,
    ) -> CommitDecision:
        def measure(completion: str) -> CommitDecision:
            return super(AttachedConversationState, self).prepare_commit(
                turn_seq,
                sanitized_user_prompt=sanitized_user_prompt,
                sanitized_plan_text=sanitized_plan_text,
                sanitized_completion_text=completion,
                outcome=outcome,
                effect_state=effect_state,
            )

        decision = measure(sanitized_completion_text)
        if decision.projected_bytes > self._source_max_bytes and sanitized_completion_text:
            decision = self._shortened(measure, sanitized_completion_text, decision)
        projected = decision.projected_bytes
        return dataclasses.replace(
            decision,
            closes_cap=projected > self._source_max_bytes,
            crosses_warning=crosses_warning_threshold(projected, self._source_max_bytes) and not self._warning_confirmed,
        )

    def _shortened(self, measure, completion: str, overflowing: CommitDecision) -> CommitDecision:
        """The longest prefix of `completion` that fits with the marker; the overflowing decision
        when not even the marker fits (genuine exhaustion)."""
        best = measure(COMPLETION_TRUNCATION_MARKER)
        if best.projected_bytes > self._source_max_bytes:
            return overflowing
        low, high = 0, len(completion)
        while low < high:
            middle = (low + high + 1) // 2
            candidate = measure(completion[:middle] + COMPLETION_TRUNCATION_MARKER)
            if candidate.projected_bytes <= self._source_max_bytes:
                low, best = middle, candidate
            else:
                high = middle - 1
        return best

    def plan_fits(self, turn_seq: int, *, sanitized_user_prompt: str, sanitized_plan_text: str) -> bool:
        """Whether this turn's record can keep its plan and still commit a result: measured with the
        longest outcome and effect values and only the truncation marker as the reply."""
        decision = super().prepare_commit(
            turn_seq,
            sanitized_user_prompt=sanitized_user_prompt,
            sanitized_plan_text=sanitized_plan_text,
            sanitized_completion_text=COMPLETION_TRUNCATION_MARKER,
            outcome=_LONGEST_OUTCOME,
            effect_state=_LONGEST_EFFECT,
        )
        return decision.projected_bytes <= self._source_max_bytes
