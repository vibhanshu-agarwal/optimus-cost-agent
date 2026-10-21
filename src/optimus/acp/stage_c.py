"""Plan 12.2 Task 13 (Stage C): the attached test profile's real-host engine composition and its fixed
scenario (Codex scope agreement, 2026-10-11, sections 1-3).

Only an approved Stage C launch of the reviewed ``attached`` test composition gets an attached Context
Engine: the existing :class:`ContextAttachment`, the existing engine and Gateway-backed maintenance
(``gateway_summarizer_factory``, ``HostMaintenance``), the accepted numeric limits below, the profile's
estimator, receipt and route identity, and the existing cancellation and per-session accounting. Of the
test compositions, the qualification one and a profile without Stage C stay absent-engine. The ordinary
launch's attachment is separate (``optimus.acp.context_attachment``, Plan 12.2 closure); both import the
one shipped numeric policy (``optimus.context.shipped_policy``), and the product cost policy is unchanged.

The fixed scenario (``optimus_model_policy.stage_c``, bound into the launch approval and the Gateway
manifest through the envelope) adds three controls, none of them a client control surface:

- the first new session of the launch is seeded with a deterministic synthetic history over the 512 KiB
  floor: ordinary turns and two explicitly synthetic approval facts, all labelled ``synthetic``. Facts are
  history, never authority: they authorize no artifact, execute no stored plan, create no operation
  terminal and are no WRITE/TEST proof. Later sessions are not seeded and nothing is reloaded. A session
  whose sanitizer would change the pinned seed is refused with a readable UNRUN reason, and so is every
  later session of the launch: an unseeded session never stands in for the seeded case;
- on the scheduled live turns of that session the engine is unavailable (simulated, and said so in a
  notice): the turn takes the real unavailable path, with no canned summary and no changed limit;
- on the scheduled cancellation turn, after the turn's first maintenance call has completed (its charge
  settled by the Gateway's guard and its receipt recorded by ``HostMaintenance``) and before the turn's
  second call (a repack's included), the turn pauses, off the ACP event loop, with a content-free notice,
  for at most 30 seconds of elapsed time or the rest of the shared window, both rechecked on every wake. A
  real client cancel then suppresses the second call through ``HostMaintenance``'s own cancellation check.
  Without one the case ends UNRUN, keeps its charge and sends no further call. This proves cancellation
  between maintenance calls, not interruption of an in-flight request.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from context_engine.engine import ContextEngine
from optimus.acp.conversation import (
    ConversationOutcome,
    ConversationSanitizer,
    ConversationSanitizerInputs,
    ConversationTurn,
    render_conversation_envelope,
)
from optimus.acp.debug_trace import log_provider_attempts
from optimus.acp.settlement import EffectState
from optimus.context.adapter import ApprovalDecision, ApprovalFact
from optimus.context.assembly import ContextAttachment, SummarizerRoute
from optimus.context.maintenance import gateway_summarizer_factory
from optimus.context.shipped_policy import (
    MAX_MAINTENANCE_CALLS,
    MAX_REPACKS,
    RECORD_RESERVATION_BYTES,
    SOURCE_MAX_BYTES,
    AttachmentLimits,
    attachment_limits,
    no_attachment_ledger,
)
from optimus.gateway.route_binding import registry_route_identity
from optimus_model_policy.binding import BindingError, disclosure_key
from optimus_model_policy.stage_c import (
    STAGE_C_ATTACHED_SCENARIO,
    STAGE_C_LITERAL_NAME,
    STAGE_C_PROFILES,
    STAGE_C_SCENARIOS,
    StageCEnvelope,
    compose_stage_c_envelope,
    ledger_deadline,
    stage_c_ledger_path,
)

__all__ = [
    "MAX_MAINTENANCE_CALLS",
    "RECORD_RESERVATION_BYTES",
    "SOURCE_MAX_BYTES",
    "StageCLaunch",
    "StageCLaunchError",
    "StageCScenario",
    "compose_stage_c_attachment",
    "resolve_stage_c_launch",
    "seed_history",
    "seed_identity",
    "stage_c_limits",
]

# The accepted numeric limits now live in the shared shipped policy (optimus.context.shipped_policy, closure plan
# v3) and are re-exported here unchanged; only the scenario's own cancellation wait is Stage C's.
CANCEL_WAIT_SECONDS = 30.0

UNAVAILABLE_NOTICE = (
    "Stage C test scenario: the context engine is unavailable on this turn by the approved schedule "
    "(simulated). The turn takes the real unavailable path."
)
PAUSE_NOTICE = (
    "Stage C test scenario: maintenance paused after its first summary call was charged. Cancel this turn "
    "now; it waits at most {seconds} seconds and makes no further call until you do."
)
UNRUN_NOTICE = "Stage C test scenario: UNRUN, cancellation not exercised. The first call's charge is kept; no further call is made."
SEED_REFUSED_NOTICE = (
    "Stage C test scenario refused: this session's sanitized seed is not the pinned seed, so the attached cases "
    "are UNRUN. No session of this launch is created; no model call was made."
)

_SEED_PROMPT = "Synthetic Stage C seed turn {n}: summarize the calculator notes for step {n}."
_SEED_WORDS = (
    "synthetic", "calculator", "decimal", "amount", "rounding", "rule", "history", "summary", "turn", "review",
    "result", "check", "note", "plan", "change", "record", "value", "step", "output", "input", "line", "flag",
    "places", "currency", "operator", "negative", "public", "interface", "readme", "section",
)  # fmt: skip


class ScenarioEngineUnavailable(Exception):
    """The scheduled, simulated engine unavailability of the Stage C scenario."""


class ScenarioCancellationNotExercised(Exception):
    """The scheduled cancellation pause ended without a client cancel: the case is UNRUN."""


# --- Limits ------------------------------------------------------------------------------------------------


# The Stage C names for the shared shipped numeric policy (closure plan v3): the attached cases and the ordinary
# attachment use one object.
StageCLimits = AttachmentLimits
stage_c_limits = attachment_limits


# --- The fixed synthetic seed ----------------------------------------------------------------------------------


def _seed_completion(n: int, size: int) -> str:
    words, parts, k = len(_SEED_WORDS), [f"Synthetic seed reply {n}."], 0
    length = len(parts[0]) + 1
    while length < size:
        sentence = " ".join(_SEED_WORDS[(n * 7 + k * 3 + i) % words] for i in range(12)).capitalize() + "."
        parts.append(sentence)
        length += len(sentence) + 1
        k += 1
    return " ".join(parts)


def seed_history(sanitizer: ConversationSanitizer) -> tuple[dict[int, ConversationTurn], dict[int, tuple[ApprovalFact, ...]]]:
    """The scenario's synthetic history, deterministic from its catalogue entry: ordinary completed turns
    with no effect, and explicitly synthetic approval facts that describe no real artifact."""
    seed = STAGE_C_SCENARIOS[STAGE_C_ATTACHED_SCENARIO]["seed"]
    records: dict[int, ConversationTurn] = {}
    for n in range(1, seed["turns"] + 1):
        records[n] = ConversationTurn(
            user_prompt=sanitizer.sanitize(_SEED_PROMPT.format(n=n)),
            plan_text="",
            completion_text=sanitizer.sanitize(_seed_completion(n, seed["completion_bytes"])),
            outcome=ConversationOutcome.COMPLETED,
            effect_state=EffectState.NONE,
        )
    approvals: dict[int, tuple[ApprovalFact, ...]] = {
        seq: (
            ApprovalFact(
                turn_seq=seq,
                artifact_hash=f"synthetic-stage-c-seed-artifact-{seq}",
                decision=ApprovalDecision.GRANTED if index == 0 else ApprovalDecision.DENIED,
                scope=(f"synthetic-seed/notes-{seq}.md",),
            ),
        )
        for index, seq in enumerate(seed["synthetic_approvals"])
    }
    return records, approvals


def _pinned_seed() -> tuple[str, int]:
    seed = STAGE_C_SCENARIOS[STAGE_C_ATTACHED_SCENARIO]["seed"]
    return seed["records_sha256"], seed["records_bytes"]


def seed_identity(records: Mapping[int, ConversationTurn], approvals: Mapping[int, tuple[ApprovalFact, ...]]) -> tuple[str, int]:
    """The seed's SHA-256 and rendered byte count: the storage rendering of its records plus each synthetic
    fact's canonical rendering."""
    rendered = render_conversation_envelope(records)
    facts = json.dumps({str(seq): [fact.render() for fact in approvals[seq]] for seq in sorted(approvals)}, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256((rendered + "\n" + facts).encode("utf-8")).hexdigest(), len(rendered.encode("utf-8"))


# --- The scenario controls -------------------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(UTC)


class StageCScenario:
    """The fixed attached scenario's controls for one launch: designates and seeds the first new session,
    counts its live attached turns and applies the scheduled unavailability and cancellation pause."""

    def __init__(
        self,
        *,
        ledger: Path,
        clock: Callable[[], datetime] = _utc_now,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        poll_seconds: float = 0.05,
    ) -> None:
        spec = STAGE_C_SCENARIOS[STAGE_C_ATTACHED_SCENARIO]
        schedule = spec["schedule"]
        self._unavailable = frozenset(schedule["engine_unavailable_turns"])
        self._cancel_turn = schedule["cancel_pause_turn"]
        self._pause_before = schedule["cancel_pause_before_call"]
        self._wait_seconds = float(schedule["cancel_wait_seconds"])
        self._ledger = ledger
        self._clock = clock
        self._sleep = sleep
        self._monotonic = monotonic
        self._poll = poll_seconds
        self._lock = threading.Lock()
        self._designated: str | None = None
        self._refused: str | None = None
        self._turns = 0
        self._turn_calls: dict[int, int] = {}
        self._notices: dict[int, Callable[[str], bool]] = {}
        self._noticed: set[tuple[int, str]] = set()
        self.events: list[str] = []
        """Content-free record of what the scenario applied, for evidence."""

    @property
    def designated_session(self) -> str | None:
        return self._designated

    def seed(self, session: Any) -> str | None:
        """Seed the launch's first new session; every later session is left as it is. Returns the reason to
        refuse the session instead, when the pinned seed cannot be applied: then every later session of the
        launch is refused too, so an unseeded session never stands in for the seeded case."""
        with self._lock:
            if self._refused is not None:
                return self._refused
            if self._designated is not None:
                return None
            self._designated = session.session_id
        conversation = session.conversation
        records, approvals = seed_history(conversation.sanitizer)
        if seed_identity(records, approvals) != _pinned_seed():
            # The session's sanitizer would change the pinned bytes: never seed anything else.
            with self._lock:
                self._refused = SEED_REFUSED_NOTICE
            self.events.append("seed refused: the session's sanitized seed is not the pinned seed; the attached cases are UNRUN")
            return SEED_REFUSED_NOTICE
        for seq, record in records.items():
            decision = conversation.prepare_commit(
                seq,
                sanitized_user_prompt=record.user_prompt,
                sanitized_plan_text=record.plan_text,
                sanitized_completion_text=record.completion_text,
                outcome=record.outcome,
                effect_state=record.effect_state,
            )
            conversation.commit_after_final_flush(decision)
        session.context_approvals.update(approvals)
        self.events.append(f"seeded session with {len(records)} synthetic turns and {len(approvals)} synthetic approval facts")
        return None

    def current_turn(self, session_key: str) -> int | None:
        with self._lock:
            return self._turns if session_key == self._designated and self._turns else None

    def summarizer(self, factory: Callable[..., Any]) -> Callable[..., Any]:
        """The summarizer factory, counting each live attached turn of the designated session (the factory
        is bound once per turn) and keeping that turn's notice channel."""

        def bind(identity: Any, deliver_notice: Callable[[str], bool]) -> Any:
            with self._lock:
                if identity.session_id == self._designated:
                    self._turns += 1
                    self._notices[self._turns] = deliver_notice
            return factory(identity, deliver_notice)

        return bind

    def _notify(self, turn: int, key: str, text: str) -> None:
        with self._lock:
            if (turn, key) in self._noticed:
                return
            self._noticed.add((turn, key))
            deliver = self._notices.get(turn)
        if deliver is not None:
            deliver(text)

    def engine(self, engine: ContextEngine) -> Any:
        scenario = self

        class _ScenarioEngine:
            def prepare_view(self, snapshot: Any, **kwargs: Any) -> Any:
                turn = scenario.current_turn(snapshot.revision.session_key)
                if turn is not None and turn in scenario._unavailable:
                    scenario._notify(turn, "unavailable", UNAVAILABLE_NOTICE)
                    scenario.events.append(f"turn {turn}: simulated engine unavailability")
                    raise ScenarioEngineUnavailable(f"simulated engine unavailability on live turn {turn}")
                if turn is not None and turn == scenario._cancel_turn:
                    kwargs["maintenance"] = scenario._pausing(turn, kwargs["maintenance"], kwargs["cancelled"])
                return engine.prepare_view(snapshot, **kwargs)

        return _ScenarioEngine()

    def _pausing(self, turn: int, maintenance: Callable[[Any], Any], cancelled: Callable[[], bool]) -> Callable[[Any], Any]:
        """The cancellation turn's maintenance callback. Calls are counted across the turn's views (a
        repack's first call is the turn's next call), and the pause before the scheduled call ends at 30
        seconds of elapsed time or the shared deadline, whichever comes first, rechecked on every wake."""

        def call(request: Any) -> Any:
            with self._lock:
                calls = self._turn_calls[turn] = self._turn_calls.get(turn, 0) + 1
            if calls == self._pause_before:
                deadline = ledger_deadline(self._ledger)

                def window() -> float:
                    return 0.0 if deadline is None else (deadline - self._clock()).total_seconds()

                wait = max(0.0, min(self._wait_seconds, window()))
                self._notify(turn, "pause", PAUSE_NOTICE.format(seconds=int(wait)))
                self.events.append(f"turn {turn}: paused before maintenance call {calls} for at most {wait:.0f} s")
                started = self._monotonic()
                while not cancelled():
                    # Rechecked on every wake; a late wake counts in full and never buys another cycle.
                    remaining = min(self._wait_seconds - (self._monotonic() - started), window())
                    if remaining <= 0:
                        break
                    self._sleep(min(self._poll, remaining))
                if not cancelled():
                    self._notify(turn, "unrun", UNRUN_NOTICE)
                    self.events.append(f"turn {turn}: UNRUN, cancellation not exercised")
                    raise ScenarioCancellationNotExercised("cancellation not exercised")
                self.events.append(f"turn {turn}: cancelled during the pause")
            return maintenance(request)  # HostMaintenance's own cancellation check suppresses the call

        return call


# --- Composition -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class StageCLaunch:
    """One authorized Stage C launch's envelope and its resolved ledger."""

    envelope: StageCEnvelope
    ledger: Path


class StageCLaunchError(Exception):
    """A Stage C launch that must stop before any service starts. ``code`` is stable."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def resolve_stage_c_launch(candidate: Any, composition: Any) -> StageCLaunch:
    """The authorized launch's envelope, recomposed from source and the trusted runtime root. Refuses a
    profile outside the release, an envelope other than the one the approval bound, a ledger the release
    ceremony has not created (a launch never creates one) and, for the attached profile, a seed that is not
    the pinned one."""
    if composition.profile.name not in STAGE_C_PROFILES:
        raise StageCLaunchError("STAGE_C_NEEDS_TEST_PROFILE")
    ledger = stage_c_ledger_path(candidate.operator_paths.runtime_root)
    try:
        envelope = compose_stage_c_envelope(ledger=ledger)
    except BindingError as exc:
        raise StageCLaunchError("STAGE_C_ENVELOPE_INVALID", exc.code) from exc
    if envelope.literal != candidate.security_literals.get(STAGE_C_LITERAL_NAME):
        raise StageCLaunchError("STAGE_C_NOT_APPROVED", "the launch approval does not bind this envelope")
    if ledger.is_symlink() or not ledger.is_file():
        raise StageCLaunchError("STAGE_C_LEDGER_MISSING", "run the Stage C approval ceremony first; a launch never creates the ledger")
    if composition.profile.name == "attached" and seed_identity(*seed_history(_PLAIN_SANITIZER)) != _pinned_seed():
        raise StageCLaunchError("STAGE_C_SEED_MISMATCH")
    return StageCLaunch(envelope=envelope, ledger=ledger)


_PLAIN_SANITIZER = ConversationSanitizer(ConversationSanitizerInputs(known_secrets=(), path_aliases=(), known_pii=()))


_no_attachment_ledger = no_attachment_ledger  # the shared no-op sink; the Gateway's envelope ledger records every attempt


def stage_c_attachment(
    *,
    composition: Any | None,
    launch: StageCLaunch | None,
    gateway_client: Any,
    shared_secret: str,
    attempt_observer: Any = log_provider_attempts,
) -> tuple[ContextAttachment | None, Callable[[Any], str | None] | None]:
    """The launch's Stage C engine and session seeder: only an approved Stage C launch of the attached test
    composition gets them; the qualification composition and a profile without Stage C stay absent-engine.
    An ordinary launch gets the shipped attachment instead (``ordinary_attachment``). ``attempt_observer`` is the
    harness's bound attempt observer (correction plan v4, C4)."""
    if launch is None or composition is None or composition.profile.name != "attached":
        return None, None
    attachment, scenario = compose_stage_c_attachment(
        composition=composition, gateway_client=gateway_client, shared_secret=shared_secret, launch=launch, attempt_observer=attempt_observer
    )
    return attachment, scenario.seed


def compose_stage_c_attachment(
    *,
    composition: Any,
    gateway_client: Any,
    shared_secret: str,
    launch: StageCLaunch,
    clock: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    attempt_observer: Any = log_provider_attempts,
) -> tuple[ContextAttachment, StageCScenario]:
    """The attached Stage C launch's ``ContextAttachment`` and scenario. Refuses any other composition, a
    seed that is not the pinned one and a route the trusted snapshot does not give the summarizer."""
    profile = composition.profile
    if profile.name != "attached":
        raise BindingError("STAGE_C_ATTACHMENT_PROFILE", "only the attached test profile attaches the engine")
    if seed_identity(*seed_history(_PLAIN_SANITIZER)) != _pinned_seed():
        raise BindingError("STAGE_C_SEED_MISMATCH", "the generated seed is not the pinned scenario seed")
    snapshot = composition.snapshot
    model_id = profile.model_id
    limits = stage_c_limits(snapshot, model_id)
    identity = registry_route_identity(snapshot, model_id=model_id, role="summarizer")
    route = SummarizerRoute(
        model_id=identity.model_id, role=identity.role, route=identity.route, reasoning=identity.reasoning, quantizations=identity.quantizations
    )
    factory = gateway_summarizer_factory(
        gateway_client=gateway_client, route=route, snapshot=snapshot, disclosure_key=disclosure_key(shared_secret), attempt_observer=attempt_observer
    )
    scenario = StageCScenario(ledger=launch.ledger, clock=clock, sleep=sleep, monotonic=monotonic)
    attachment = ContextAttachment(
        engine=scenario.engine(ContextEngine()),
        parameters=limits.parameters,
        limits=limits.limits,
        source_max_bytes=SOURCE_MAX_BYTES,
        record_reservation_bytes=RECORD_RESERVATION_BYTES,
        usable_input_tokens=limits.usable_input_tokens,
        estimate_request=limits.estimate_request,
        registry_hash=snapshot.effective_hash,
        model_id=model_id,
        summarizer=scenario.summarizer(factory),
        summarizer_route=route,
        record_receipt=_no_attachment_ledger,
        max_repacks=MAX_REPACKS,
        initial_strategy="compaction",
    )
    return attachment, scenario
