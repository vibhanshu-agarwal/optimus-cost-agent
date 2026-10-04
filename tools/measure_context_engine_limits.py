"""Measure the Context Engine's finite limits offline (Plan 12.2 Task 12; design spec 4.2, 6, 9.4).

Evidence for the D1, D2 and D3 policy proposals. Synthetic histories only: no network, no model or
Gateway call, no credential, no service. Every measurement drives the real host code - the attached
storage class, the snapshot projection, the engine, view rendering, selection text and the admitted
digest - and records wall time and the tracemalloc peak. Nothing here is a policy: the report states
measurements and the arithmetic a proposal can be checked against; the operator accepts values.

Token figures are given per estimator ratio (tokens per UTF-8 byte). No route estimator is verified
(the reviewed registry has `estimators: {}`), so none is assumed. A ratio of 1 bounds every byte-level
BPE or byte-fallback tokenizer's content tokens, because each token covers at least one byte; the
per-message framing a route adds is not covered by that bound and is not verified here. Lower ratios
are sensitivity rows only.

Usage: python tools/measure_context_engine_limits.py --out <evidence>/limits.json [--quick]
"""

from __future__ import annotations

import argparse
import dataclasses
import gc
import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import tracemalloc
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

from context_engine import (
    HistorySnapshot,
    MaintenanceRequest,
    MaintenanceResult,
    OrdinaryTurn,
    ProtectedTurnState,
    StrategyParameters,
    SummaryCheckpoint,
    ViewLimits,
)
from context_engine.engine import _SEPARATOR, PRIOR_SUMMARY_HEADER, ContextEngine
from context_engine.selection import render_ordinary_turn, render_protected_state
from context_engine.summary import PROMPT_VERSION, SECTIONS, SUMMARY_FORMAT, build_summary_prompt
from optimus.acp.conversation import (
    CONVERSATION_MAX_BYTES,
    AttachedConversationState,
    CommitDecision,
    ConversationOutcome,
    ConversationSanitizer,
    ConversationSanitizerInputs,
    ConversationState,
    ConversationTurn,
    render_conversation_envelope,
)
from optimus.acp.settlement import EffectState
from optimus.context.adapter import ApprovalDecision, ApprovalFact, make_history_snapshot
from optimus.context.assembly import admitted_context_digest, build_selection_text, full_history_view, probe_floor, render_context_view
from optimus.runtime.modes import ExecutionMode

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA = "context-engine-limits/v1"

ESTIMATOR_RATIOS = (Decimal("1"), Decimal("0.5"), Decimal("0.25"))
"""Tokens per UTF-8 byte. 1 is the byte-level upper bound before framing; the others are sensitivity."""

ALPHABETS: Mapping[str, str] = {
    "ascii": "lorem ipsum dolor sit amet ",
    "latin": "déjà vu été ",  # 2-byte letters, stored as 1 byte per character (Latin-1)
    "cjk": "漢字仮名交じり文。",  # 3 UTF-8 bytes, stored as 2 bytes per character; punctuated like prose
    "emoji": "😀",  # 4 UTF-8 bytes, stored as 4 bytes per character
    "ascii_one_emoji": "",  # ASCII with one emoji per field: widens each whole string to 4 bytes/char
    "escapes": '"\\',  # every byte doubles in the canonical JSON record
}
"""Prose-like text: word runs stay short. One unbroken run of word characters is a separate,
adversarial case (`sanitizer_scaling`): the host sanitizer is quadratic in its length."""

FULL_SIZES_KIB = (64, 256, 512, 1024, 2048, 4096)
QUICK_SIZES_KIB = (16, 32)
TURN_BYTES = 8 * 1024
FULL_CONCURRENCY = (1, 2, 4, 8)
QUICK_CONCURRENCY = (1, 2)
HUGE = 1 << 40  # a source limit no measurement reaches, so nothing is refused while measuring


# --- Synthetic text and histories -------------------------------------------------------------------


def text_of(alphabet: str, utf8_bytes: int) -> str:
    """Text of exactly `utf8_bytes` UTF-8 bytes drawn from `alphabet`, padded with ASCII."""
    if utf8_bytes < 0:
        raise ValueError("a size cannot be negative")
    if alphabet == "ascii_one_emoji":
        head = "😀" if utf8_bytes >= 4 else ""
        return head + text_of("ascii", utf8_bytes - len(head.encode("utf-8")))
    unit = ALPHABETS[alphabet]
    unit_bytes = len(unit.encode("utf-8"))
    whole, rest = divmod(utf8_bytes, unit_bytes)
    text = unit * whole + "x" * rest
    if len(text.encode("utf-8")) != utf8_bytes:
        raise AssertionError("synthetic text missed its byte size")
    return text


def _artifact_hash(seq: int) -> str:
    return hashlib.sha256(f"artifact-{seq}".encode()).hexdigest()


def make_turn(alphabet: str, turn_bytes: int, seq: int) -> ConversationTurn:
    """One complete committed turn: a prompt, an applied WRITE plan and a completion message."""
    quarter = turn_bytes // 4
    header = f"WRITE src/module_{seq}.py\n"
    return ConversationTurn(
        user_prompt=text_of(alphabet, quarter),
        plan_text=header + text_of(alphabet, max(0, turn_bytes - 2 * quarter - len(header))),
        completion_text=text_of(alphabet, quarter),
        outcome=ConversationOutcome.COMPLETED,
        effect_state=EffectState.COMPLETE,
    )


def approval_facts(seq: int, count: int) -> tuple[ApprovalFact, ...]:
    return tuple(
        ApprovalFact(turn_seq=seq, artifact_hash=_artifact_hash(seq * 1000 + index), decision=ApprovalDecision.GRANTED, scope=(f"src/module_{seq}.py",))
        for index in range(count)
    )


def sanitizer() -> ConversationSanitizer:
    return ConversationSanitizer(ConversationSanitizerInputs((), ()))


def build_state(
    alphabet: str,
    target_bytes: int,
    *,
    turn_bytes: int = TURN_BYTES,
    facts_per_turn: int = 1,
    source_max_bytes: int = HUGE,
    record_reservation_bytes: int = 0,
) -> tuple[AttachedConversationState, dict[int, tuple[ApprovalFact, ...]]]:
    """An attached session holding about `target_bytes` of canonical history, built in linear time
    through the state's own commit path (a decision per record, as a finished turn commits)."""
    state = AttachedConversationState(sanitizer(), source_max_bytes=source_max_bytes, record_reservation_bytes=record_reservation_bytes)
    per_turn = len(render_conversation_envelope({1: make_turn(alphabet, turn_bytes, 1), 2: make_turn(alphabet, turn_bytes, 2)}).encode()) - len(
        render_conversation_envelope({1: make_turn(alphabet, turn_bytes, 1)}).encode()
    )
    turns = max(1, round(target_bytes / per_turn))
    approvals: dict[int, tuple[ApprovalFact, ...]] = {}
    for seq in range(1, turns + 1):
        record = make_turn(alphabet, turn_bytes, seq)
        state.commit_after_final_flush(
            CommitDecision(commit=True, turn_seq=seq, projected_bytes=0, closes_cap=False, crosses_warning=False, record=record)
        )
        if facts_per_turn:
            approvals[seq] = approval_facts(seq, facts_per_turn)
    return state, approvals


# --- Measurement ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Reading:
    seconds: float
    peak_bytes: int
    retained_bytes: int

    def as_dict(self) -> dict[str, float | int]:
        return {"seconds": round(self.seconds, 6), "peak_bytes": self.peak_bytes, "retained_bytes": self.retained_bytes}


def measure(action: Callable[[], Any]) -> tuple[Any, Reading]:
    """Run `action` once and read its wall time and tracemalloc peak above the starting level."""
    if not tracemalloc.is_tracing():
        raise RuntimeError("start tracemalloc before measuring")
    gc.collect()
    tracemalloc.reset_peak()
    before, _ = tracemalloc.get_traced_memory()
    start = time.perf_counter()
    result = action()
    seconds = time.perf_counter() - start
    after, peak = tracemalloc.get_traced_memory()
    return result, Reading(seconds=seconds, peak_bytes=max(0, peak - before), retained_bytes=max(0, after - before))


def ratio_estimator(ratio: Decimal) -> Callable[[str], int]:
    def estimate(text: str) -> int:
        return math.ceil(len(text.encode("utf-8")) * ratio)

    return estimate


def summary_max_bytes_for(summary_tokens: int, ratio: Decimal) -> int:
    """`floor(S / r)`: the most UTF-8 bytes a summary within `S` tokens can have under a
    `ceil(r * bytes)` estimator, so the byte bound never rejects what the token bound admits (Codex's
    final corrections C2). Exact rational arithmetic, whatever the decimal context's precision (Fable
    review of the CP4 corrections, NIT-3)."""
    return math.floor(Fraction(summary_tokens) / Fraction(ratio))


def summary_of_tokens(tokens: int, ratio: Decimal) -> str:
    """A valid `context-summary-v1` summary as long as `tokens` allows under `ratio`."""
    bodies = ["synthetic", "-", "-", "-", "-", "-"]
    text = "\n".join(f"## {name}\n{body}" for name, body in zip(SECTIONS, bodies, strict=True))
    budget = math.floor(tokens / ratio) - len(text.encode())
    return text + " x" * max(0, budget // 2)


class SyntheticSummarizer:
    """The engine's maintenance callback with no model: a valid summary of the largest allowed size."""

    def __init__(self, ratio: Decimal) -> None:
        self.ratio = ratio
        self.calls = 0

    def __call__(self, request: MaintenanceRequest) -> MaintenanceResult:
        self.calls += 1
        build_summary_prompt(request.input_text)  # the host builds this buffer for every call
        text = summary_of_tokens(request.max_output_tokens, self.ratio)
        return MaintenanceResult(summary_text=text, attempt_ids=(f"synthetic-{self.calls}",), status="completed", finish_status="stop")


@dataclass(frozen=True, slots=True)
class EngineFixture:
    """Explicit measurement policy (not a proposal): large enough that the machinery, not the policy,
    is what is measured."""

    ratio: Decimal = Decimal("1")
    history_input_tokens: int = 200_000
    tail_tokens: int = 32_768
    summary_tokens: int = 4_096
    maintenance_input_tokens: int = 65_536
    max_calls: int = 1_000
    anchor_tokens: int = 8_192
    hybrid_tail_tokens: int | None = None  # twice the compaction tail when not given
    source_max_bytes: int = HUGE
    transient_max_bytes: int = HUGE

    @classmethod
    def from_proposal(cls, proposal: Mapping[str, Any], *, tier: str = "cheap", ratio: Decimal = Decimal("1")) -> EngineFixture:
        """The proposed values themselves, under a `ceil(ratio * bytes)` estimator (the byte-level bound
        by default), with the proposal's engine source and transient byte bounds."""
        return cls(
            ratio=ratio,
            history_input_tokens=proposal["history_input_tokens_by_tier"][tier],
            tail_tokens=proposal["compaction_tail_input_tokens"],
            summary_tokens=proposal["summary_output_tokens"],
            maintenance_input_tokens=proposal["maintenance_input_tokens"],
            max_calls=proposal["max_maintenance_calls"],
            anchor_tokens=proposal["anchor_input_tokens"],
            hybrid_tail_tokens=proposal["hybrid_tail_input_tokens"],
            source_max_bytes=proposal["view_source_max_bytes"],
            transient_max_bytes=proposal["transient_max_bytes"],
        )

    def parameters(self) -> StrategyParameters:
        return StrategyParameters(
            anchor_input_tokens=self.anchor_tokens,
            compaction_tail_input_tokens=self.tail_tokens,
            hybrid_tail_input_tokens=self.hybrid_tail_tokens if self.hybrid_tail_tokens is not None else self.tail_tokens * 2,
            summary_output_tokens=self.summary_tokens,
            max_maintenance_calls=self.max_calls,
            prompt_version=PROMPT_VERSION,
            format_version=SUMMARY_FORMAT,
        )

    def limits(self, *, source_max_bytes: int | None = None, transient_max_bytes: int | None = None) -> ViewLimits:
        return ViewLimits(
            history_input_tokens=self.history_input_tokens,
            source_max_bytes=self.source_max_bytes if source_max_bytes is None else source_max_bytes,
            transient_max_bytes=self.transient_max_bytes if transient_max_bytes is None else transient_max_bytes,
            maintenance_input_tokens=self.maintenance_input_tokens,
            maintenance_output_tokens=self.summary_tokens,
            summary_max_bytes=summary_max_bytes_for(self.summary_tokens, self.ratio),
            estimate_history=ratio_estimator(self.ratio),
            estimator_id=f"utf8-bytes-ratio:{self.ratio}",
        )


def snapshot_of(state: ConversationState, approvals: Mapping[int, Sequence[ApprovalFact]]) -> HistorySnapshot:
    return make_history_snapshot(session_key="measure", generation=state.generation, records=state.records, approvals=approvals, sanitizer=state.sanitizer)


def turn_pipeline(
    state: AttachedConversationState,
    approvals: Mapping[int, Sequence[ApprovalFact]],
    *,
    strategy: str,
    fixture: EngineFixture,
    checkpoint: SummaryCheckpoint | None = None,
) -> dict[str, Any]:
    """One attached turn's host work, with every intermediate alive at once as in a real turn:
    admission, snapshot, view, rendered envelope, selection text, admitted digest, commit check.
    With `checkpoint`, the engine may reuse it or merge only what it does not cover (the steady
    state); the view's own checkpoint is returned for the next turn. Outside: the host's
    `HostMaintenance` wrapper (summary sanitization, receipts) and the request assembly after the
    admitted view (`fit()` and the Gateway body), roughly two more envelope-sized copies."""
    prompt = text_of("ascii", 2_048)
    admission = state.prepare_admission(prompt)
    snapshot = snapshot_of(state, approvals)
    summarizer = SyntheticSummarizer(fixture.ratio)
    if strategy == "full":
        view = full_history_view(snapshot)
    else:
        view = ContextEngine().prepare_view(
            snapshot, strategy=strategy, parameters=fixture.parameters(), limits=fixture.limits(), checkpoint=checkpoint, maintenance=summarizer,
            cancelled=lambda: False,
        )  # fmt: skip
    reason, fallback = view.reason, False
    if not view.available:
        # The host's own rule: the full history when the floor probe fits, else a refusal.
        if probe_floor(state.records, prompt) > CONVERSATION_MAX_BYTES:
            return {"available": False, "reason": reason, "fallback": "refused", "maintenance_calls": summarizer.calls, "envelope_bytes": 0, "checkpoint": None}
        view, fallback = full_history_view(snapshot), True
    envelope = render_context_view(snapshot, view)
    selection = build_selection_text(prompt, snapshot, view)
    digest = admitted_context_digest(
        mode=ExecutionMode.AGENT, strategy=strategy, applied="view", revision=snapshot.revision, parameters_digest=fixture.parameters().digest,
        registry_hash="0" * 64, model_id="measure/model", estimator_id="measure", current_prompt=prompt, selection_text=selection,
        conversation_envelope=envelope,
    )  # fmt: skip
    decision = state.prepare_commit(
        admission.turn_seq or state.generation + 1, sanitized_user_prompt=prompt, sanitized_plan_text=make_turn("ascii", TURN_BYTES, 0).plan_text,
        sanitized_completion_text="done", outcome=ConversationOutcome.COMPLETED, effect_state=EffectState.COMPLETE,
    )  # fmt: skip
    return {
        "available": not fallback,
        "reason": reason,
        "fallback": "full_history" if fallback else None,
        "maintenance_calls": summarizer.calls,
        "envelope_bytes": len(envelope.encode("utf-8")),
        "projected_bytes": decision.projected_bytes,
        "digest": digest,
        "checkpoint": view.checkpoint,
    }


# --- D2: storage, memory, time and boundaries -------------------------------------------------------


def history_scaling(alphabets: Sequence[str], sizes_kib: Sequence[int], strategies: Sequence[str], fixture: EngineFixture) -> list[dict[str, Any]]:
    """Per alphabet and size: retained memory of the history, then each strategy's whole-turn peak
    and time. `copy_factor` is the turn peak over the canonical history bytes."""
    rows = []
    for alphabet in alphabets:
        for size in sizes_kib:
            (state, approvals), built = measure(lambda a=alphabet, s=size: build_state(a, s * 1024))
            canonical = state.used_bytes
            row: dict[str, Any] = {
                "alphabet": alphabet,
                "target_kib": size,
                "turns": state.generation,
                "canonical_bytes": canonical,
                "engine_source_bytes": sum(len(render_ordinary_turn(t).encode("utf-8")) for t in snapshot_of(state, approvals).turns),
                "history_retained_bytes": built.retained_bytes,
                "strategies": {},
            }
            for strategy in strategies:
                outcome, reading = measure(lambda st=state, ap=approvals, sg=strategy: turn_pipeline(st, ap, strategy=sg, fixture=fixture))
                row["strategies"][strategy] = {
                    **reading.as_dict(),
                    "copy_factor": round(reading.peak_bytes / canonical, 3),
                    "available": outcome["available"],
                    "reason": outcome["reason"],
                    "fallback": outcome["fallback"],
                    "maintenance_calls": outcome["maintenance_calls"],
                    "envelope_bytes": outcome["envelope_bytes"],
                }
            rows.append(row)
            del state, approvals
    return rows


def run_sessions_together(sessions: Sequence[tuple[AttachedConversationState, Mapping[int, Sequence[ApprovalFact]]]], fixture: EngineFixture) -> list[str]:
    """One compaction turn per session, all released at once on their own threads. Returns the
    type of every failure (a turn that raised, or a thread still running after its deadline)."""
    barrier = threading.Barrier(len(sessions))
    failures: list[str] = []

    def work(state: AttachedConversationState, approvals: Mapping[int, Sequence[ApprovalFact]]) -> None:
        try:
            barrier.wait(timeout=60)
            turn_pipeline(state, approvals, strategy="compaction", fixture=fixture)
        except BaseException as error:  # noqa: BLE001 - reported as a failed row
            failures.append(type(error).__name__)

    threads = [threading.Thread(target=work, args=session, name=f"measure-session-{index}") for index, session in enumerate(sessions)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=600)
    return failures + ["Timeout" for thread in threads if thread.is_alive()]


def concurrency(alphabet: str, size_kib: int, levels: Sequence[int], fixture: EngineFixture) -> list[dict[str, Any]]:
    """`k` sessions running one compaction turn each at the same moment on worker threads, as ACP
    sessions do: the process-wide peak and wall time."""
    rows = []
    for level in levels:
        sessions = [build_state(alphabet, size_kib * 1024) for _ in range(level)]
        failures, reading = measure(lambda batch=sessions: run_sessions_together(batch, fixture))
        rows.append(
            {
                "sessions": level,
                "alphabet": alphabet,
                "canonical_bytes_each": sessions[0][0].used_bytes,
                **reading.as_dict(),
                "peak_per_session_bytes": reading.peak_bytes // level,
                "failures": failures,
            }
        )
    return rows


def _attached(history: Mapping[int, ConversationTurn], *, source_max_bytes: int, reservation: int) -> AttachedConversationState:
    state = AttachedConversationState(sanitizer(), source_max_bytes=source_max_bytes, record_reservation_bytes=reservation)
    for seq, record in history.items():
        state.commit_after_final_flush(CommitDecision(commit=True, turn_seq=seq, projected_bytes=0, closes_cap=False, crosses_warning=False, record=record))
    return state


def _absent(history: Mapping[int, ConversationTurn]) -> ConversationState:
    state = ConversationState(sanitizer())
    for seq, record in history.items():
        state.commit_after_final_flush(CommitDecision(commit=True, turn_seq=seq, projected_bytes=0, closes_cap=False, crosses_warning=False, record=record))
    return state


def _admission(make: Callable[[], ConversationState], prompt_chars: int) -> dict[str, Any]:
    decision = make().prepare_admission(text_of("ascii", prompt_chars))
    return {"admitted": decision.admitted, "projected_bytes": decision.projected_bytes, "refuse_reason": decision.refuse_reason}


def storage_boundaries(alphabet: str, *, source_max_bytes: int, reservation: int, history_turns: int = 4) -> dict[str, Any]:
    """Exact admission boundaries on a fresh state per probe (a refusal at the cap latches): an
    attached session at limit minus reservation, one byte over it and one byte over the limit, and
    the engine-absent floor at exactly `CONVERSATION_MAX_BYTES` and one byte over."""
    history = {seq: make_turn(alphabet, 1_024, seq) for seq in range(1, history_turns + 1)}
    base = _attached(history, source_max_bytes=HUGE, reservation=0).prepare_admission("").projected_bytes

    def attached() -> ConversationState:
        return _attached(history, source_max_bytes=source_max_bytes, reservation=reservation)

    def absent() -> ConversationState:
        return _absent(history)

    edge = source_max_bytes - reservation - base
    floor_edge = CONVERSATION_MAX_BYTES - base
    return {
        "alphabet": alphabet,
        "source_max_bytes": source_max_bytes,
        "reservation_bytes": reservation,
        "attached_at_limit_minus_reservation": _admission(attached, edge),
        "attached_one_over_reservation": _admission(attached, edge + 1),
        "attached_one_over_limit": _admission(attached, source_max_bytes - base + 1),
        "absent_at_floor": _admission(absent, floor_edge),
        "absent_one_over_floor": _admission(absent, floor_edge + 1),
    }


def engine_source_boundary(alphabet: str, *, turns: int = 4) -> dict[str, Any]:
    """The engine's own source check is inclusive at `ViewLimits.source_max_bytes`, and it measures
    rendered ordinary turns, not the host's canonical envelope: both figures are reported."""
    state, approvals = build_state(alphabet, turns * TURN_BYTES)
    snapshot = snapshot_of(state, approvals)
    source = sum(len(render_ordinary_turn(turn).encode("utf-8")) for turn in snapshot.turns)
    fixture = EngineFixture()

    def view(limit: int) -> dict[str, Any]:
        result = ContextEngine().prepare_view(
            snapshot, strategy="sliding_window", parameters=fixture.parameters(), limits=fixture.limits(source_max_bytes=limit),
            checkpoint=None, maintenance=SyntheticSummarizer(fixture.ratio), cancelled=lambda: False,
        )  # fmt: skip
        return {"available": result.available, "reason": result.reason}

    return {
        "alphabet": alphabet,
        "engine_source_bytes": source,
        "canonical_bytes": state.used_bytes,
        "engine_over_canonical": round(source / state.used_bytes, 4),
        "at_limit": view(source),
        "one_under_needed": view(source - 1),
    }


def protected_record_bytes(seq: int, facts: int) -> int:
    """One committed turn's exact protected record as the engine renders it (it grows with the turn
    number's digits and with each approval fact)."""
    state = ProtectedTurnState(
        seq=seq, outcome=str(ConversationOutcome.COMPLETED.value), effect_state=str(EffectState.COMPLETE.value),
        approval_facts=tuple(fact.render() for fact in approval_facts(seq, facts)),
    )  # fmt: skip
    return len(render_protected_state(state).encode("utf-8"))


def most_turns_with_exact_authority(facts: int, ratio: Decimal, allocation: int) -> int:
    """The most committed turns whose exact authority alone fits `allocation`, summed per turn
    exactly as the engine estimates it."""
    used, turns = 0, 0
    while True:
        cost = math.ceil(protected_record_bytes(turns + 1, facts) * ratio)
        if used + cost > allocation:
            return turns
        used += cost
        turns += 1


def protected_growth(ratios: Sequence[Decimal], facts_per_turn: Sequence[int], history_tokens: Sequence[int]) -> list[dict[str, Any]]:
    """Exact authority is kept for every committed turn and is never summarized, so it alone can use
    up the history allocation: then no view can be built. Per facts-per-turn, ratio and allocation,
    the most committed turns that still fit."""
    return [
        {
            "facts_per_turn": facts,
            "protected_record_bytes_turn_1": protected_record_bytes(1, facts),
            "protected_record_bytes_turn_1000": protected_record_bytes(1000, facts),
            "ratio": str(ratio),
            "history_tokens": allocation,
            "most_turns_with_exact_authority": most_turns_with_exact_authority(facts, ratio, allocation),
        }
        for facts in facts_per_turn
        for ratio in ratios
        for allocation in history_tokens
    ]


def protected_growth_check(facts: int, ratio: Decimal, allocation: int) -> dict[str, Any]:
    """Prove the arithmetic on the real engine: available at the computed turn count, unavailable
    one turn later, with a tiny ordinary turn so authority is all that grows."""
    fixture = dataclasses.replace(EngineFixture(), ratio=ratio, history_input_tokens=allocation)
    most = most_turns_with_exact_authority(facts, ratio, allocation)

    def view(turns: int) -> dict[str, Any]:
        state = _attached({seq: make_turn("ascii", 64, seq) for seq in range(1, turns + 1)}, source_max_bytes=HUGE, reservation=0)
        approvals = {seq: approval_facts(seq, facts) for seq in range(1, turns + 1)} if facts else {}
        snapshot = snapshot_of(state, approvals)
        result = ContextEngine().prepare_view(
            snapshot, strategy="sliding_window", parameters=fixture.parameters(), limits=fixture.limits(),
            checkpoint=None, maintenance=SyntheticSummarizer(ratio), cancelled=lambda: False,
        )  # fmt: skip
        return {"turns": turns, "available": result.available, "reason": result.reason}

    return {"facts_per_turn": facts, "ratio": str(ratio), "history_tokens": allocation, "computed_most": most, "at_most": view(most), "one_more": view(most + 1)}


def huge_anchor(sizes_kib: Sequence[int], fixture: EngineFixture) -> list[dict[str, Any]]:
    """A first turn of each size followed by small turns: does hybrid pin it, can compaction still
    summarize it (a single turn larger than the maintenance input cannot be), and at what cost."""
    rows = []
    for size in sizes_kib:
        history = {1: make_turn("ascii", size * 1024, 1), **{seq: make_turn("ascii", 2_048, seq) for seq in range(2, 40)}}
        state = _attached(history, source_max_bytes=HUGE, reservation=0)
        approvals = {seq: approval_facts(seq, 1) for seq in history}
        anchor = snapshot_of(state, approvals).turns[0]
        row: dict[str, Any] = {
            "anchor_kib": size,
            "canonical_bytes": state.used_bytes,
            "anchor_estimated_tokens": ratio_estimator(fixture.ratio)(render_ordinary_turn(anchor)),
            "maintenance_input_tokens": fixture.maintenance_input_tokens,
            "anchor_input_tokens": fixture.parameters().anchor_input_tokens,
        }
        for strategy in ("hybrid", "compaction"):
            outcome, reading = measure(lambda sg=strategy, st=state, ap=approvals: turn_pipeline(st, ap, strategy=sg, fixture=fixture))
            row[strategy] = {
                **reading.as_dict(), "available": outcome["available"], "reason": outcome["reason"], "fallback": outcome["fallback"],
                "maintenance_calls": outcome["maintenance_calls"],
            }  # fmt: skip
        rows.append(row)
    return rows


def sanitizer_scaling(prose_kib: Sequence[int], token_kib: Sequence[int]) -> dict[str, Any]:
    """The host sanitizer runs on every admitted prompt and, for an attached turn, on every
    committed record each time the snapshot is projected. Its time per call on prose, and on one
    unbroken run of word characters (base64, minified code, unpunctuated CJK), where it is quadratic:
    `optimus_security.sanitization._URL_USERINFO_RE` retries `\\w+://` from every position of the
    run. The quadratic coefficient is fitted from the measured points, and 512 KiB is extrapolated
    rather than run."""
    clean = sanitizer()

    def timed(text: str) -> float:
        start = time.perf_counter()
        clean.sanitize(text)
        return time.perf_counter() - start

    prose = [{"kib": k, "seconds": round(timed(text_of("ascii", k * 1024)), 6)} for k in prose_kib]
    token = [{"kib": k, "seconds": round(timed("x" * (k * 1024)), 6)} for k in token_kib]
    largest = token[-1]
    coefficient = largest["seconds"] / (largest["kib"] * 1024) ** 2
    per_byte = prose[-1]["seconds"] / (prose[-1]["kib"] * 1024)
    return {
        "prose": prose,
        "single_token": token,
        "prose_seconds_per_mib": round(per_byte * (1 << 20), 4),
        "single_token_seconds_per_byte_squared": coefficient,
        "single_token_512kib_extrapolated_seconds": round(coefficient * (512 * 1024) ** 2, 1),
    }


CHECK_RATIOS = (Decimal("1"), Decimal("0.5"), Decimal("0.25"), Decimal("0.2"))
"""Estimator ratios the call allowance is checked at: the measured ones and 0.2, where the transient
byte bound binds before the token bound (Codex's final corrections C2)."""


def _ceil_tokens(text: str, ratio: Decimal) -> int:
    return math.ceil(len(text.encode("utf-8")) * ratio)


def effective_summary_tokens(proposal: Mapping[str, Any]) -> int:
    """`S`: the engine's summary reserve, the smaller of the strategy's summary cap and the
    maintenance output limit (the summarizer's output reserve)."""
    return min(proposal["summary_output_tokens"], proposal["summarizer_output_reserve"])


def chunk_capacity(proposal: Mapping[str, Any], ratio: Decimal = Decimal("1")) -> dict[str, int]:
    """What one non-first maintenance call can take for turns and their separators, in each budget,
    under a `ceil(ratio * bytes)` estimator: the input less the prior summary at its maximum (header,
    `S` tokens or `floor(S / ratio)` bytes) and one separator (`engine._plan`)."""
    summary_tokens = effective_summary_tokens(proposal)
    summary_bytes = summary_max_bytes_for(summary_tokens, ratio)
    header_bytes, separator_bytes = len(PRIOR_SUMMARY_HEADER.encode("utf-8")), len(_SEPARATOR.encode("utf-8"))
    return {
        "tokens": proposal["maintenance_input_tokens"] - _ceil_tokens(PRIOR_SUMMARY_HEADER, ratio) - summary_tokens - _ceil_tokens(_SEPARATOR, ratio),
        "bytes": proposal["transient_max_bytes"] - header_bytes - summary_bytes - separator_bytes,
        "summary_max_bytes": summary_bytes,
    }


def smallest_rendered_turn_bytes() -> int:
    """No ordinary turn renders shorter than an empty one with sequence 1."""
    return len(render_ordinary_turn(OrdinaryTurn(seq=1, user_prompt="", plan_text="", completion_text="")).encode("utf-8"))


def whole_turn_worst_calls(proposal: Mapping[str, Any], ratio: Decimal) -> dict[str, Any]:
    """A proven bound on the calls a cold rebuild of the whole engine source can need, whole turns
    only, under a `ceil(ratio * bytes)` estimator.

    Greedy packing closes a chunk only when its content plus a separator and the next turn would exceed
    a budget, so any two consecutive chunks together exceed `capacity - separator` in a budget that
    closed the first. With `U` the total cost of all turns and inner separators, `floor(n / 2) <
    U / (capacity - separator)` summed over the budgets that can close a chunk, so `n <= 2 * ceil(X) - 1`.
    A turn's token cost is at least `ratio` times its bytes, so when `ratio * byte capacity >= token
    capacity` a byte overflow is always a token overflow and only the token budget counts. `U` counts
    every turn at its rounded-up token cost and a separator per turn, the number of turns being at
    most the source over the smallest rendered turn."""
    capacity = chunk_capacity(proposal, ratio)
    source = proposal["view_source_max_bytes"]
    turns = source // smallest_rendered_turn_bytes()
    separator_tokens, separator_bytes = _ceil_tokens(_SEPARATOR, ratio), len(_SEPARATOR.encode("utf-8"))
    token_room, byte_room = capacity["tokens"] - separator_tokens, capacity["bytes"] - separator_bytes
    if token_room <= 0 or byte_room <= 0:
        return {"calls": None, "binding": None, **capacity}
    token_cost = math.ceil(ratio * source) + turns + turns * separator_tokens
    byte_cost = source + turns * separator_bytes
    tokens_only = ratio * capacity["bytes"] >= capacity["tokens"]
    x = Fraction(token_cost, token_room) + (0 if tokens_only else Fraction(byte_cost, byte_room))
    return {"calls": 2 * math.ceil(x) - 1, "binding": "tokens" if tokens_only else "tokens or bytes", **capacity}


def largest_summarizable_turn_bytes(proposal: Mapping[str, Any], ratio: Decimal) -> dict[str, int]:
    """The largest single rendered turn a maintenance call can take, in bytes, under a
    `ceil(ratio * bytes)` estimator: after a prior summary (steady state) and as the first turn of a
    cold rebuild (no prior summary)."""
    capacity = chunk_capacity(proposal, ratio)
    tokens_to_bytes = lambda tokens: math.floor(Fraction(tokens) / Fraction(ratio))  # noqa: E731
    return {
        "steady_state": min(tokens_to_bytes(capacity["tokens"]), capacity["bytes"]),
        "oldest_turn_of_a_cold_rebuild": min(tokens_to_bytes(proposal["maintenance_input_tokens"]), proposal["transient_max_bytes"]),
    }


def _history_of_turns(rendered_turn_bytes: int, total_bytes: int) -> tuple[AttachedConversationState, dict[int, tuple[ApprovalFact, ...]]]:
    """Equal whole turns whose rendered ordinary text is `rendered_turn_bytes`, about `total_bytes`
    of canonical history in all."""
    overhead = len(render_ordinary_turn(snapshot_of(*build_state("ascii", 1, turn_bytes=TURN_BYTES)).turns[0]).encode("utf-8")) - TURN_BYTES
    return build_state("ascii", total_bytes, turn_bytes=rendered_turn_bytes - overhead)


def proposed_policy_rows(proposal: Mapping[str, Any], ratios: Sequence[Decimal] = CHECK_RATIOS) -> dict[str, Any]:
    """The proposed values themselves, under each estimator ratio, on a history the attached storage
    class can still admit a turn on: a cold rebuild (a strategy switch, or no reusable checkpoint), the
    steady-state turn that reuses the previous checkpoint, and an adverse whole-turn case (every turn
    just over half of the binding chunk capacity, so each call carries one turn). The engine applies the
    proposal's source and transient byte bounds."""
    return {str(ratio): _proposed_policy_rows_at(proposal, ratio) for ratio in ratios}


def _proposed_policy_rows_at(proposal: Mapping[str, Any], ratio: Decimal) -> dict[str, Any]:
    fixture = EngineFixture.from_proposal(proposal, ratio=ratio)
    history_bytes = proposal["source_max_bytes"] - proposal["record_reservation_bytes"]
    rows: dict[str, Any] = {}

    def row(outcome: Mapping[str, Any], reading: Reading, state: AttachedConversationState) -> dict[str, Any]:
        return {
            **reading.as_dict(), "canonical_bytes": state.used_bytes, "turns": state.generation, "available": outcome["available"],
            "reason": outcome["reason"], "fallback": outcome["fallback"], "maintenance_calls": outcome["maintenance_calls"],
        }  # fmt: skip

    state, approvals = build_state("ascii", history_bytes)
    cold, reading = measure(lambda: turn_pipeline(state, approvals, strategy="compaction", fixture=fixture))
    rows["cold_rebuild_8kib_turns"] = row(cold, reading, state)
    seq = state.generation + 1
    state.commit_after_final_flush(
        CommitDecision(commit=True, turn_seq=seq, projected_bytes=0, closes_cap=False, crosses_warning=False, record=make_turn("ascii", TURN_BYTES, seq))
    )
    approvals[seq] = approval_facts(seq, 1)
    steady, reading = measure(lambda: turn_pipeline(state, approvals, strategy="compaction", fixture=fixture, checkpoint=cold["checkpoint"]))
    rows["steady_state_turn"] = row(steady, reading, state)
    capacity = chunk_capacity(proposal, ratio)
    binding_bytes = min(math.floor(Fraction(capacity["tokens"]) / Fraction(ratio)), capacity["bytes"])
    worst_turn = binding_bytes // 2 + 1
    state, approvals = _history_of_turns(worst_turn, history_bytes)
    worst, reading = measure(lambda: turn_pipeline(state, approvals, strategy="compaction", fixture=fixture))
    rows["cold_rebuild_worst_whole_turns"] = {**row(worst, reading, state), "rendered_turn_bytes": worst_turn}
    return rows


# --- D3: complete WRITE plans and completion status -------------------------------------------------


def tracked_text_files(prefixes: Sequence[str] = ("src/", "tests/", "tools/"), suffixes: Sequence[str] = (".py",)) -> list[str]:
    listing = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True).stdout.decode("utf-8")
    return sorted(path for path in listing.split("\0") if path.startswith(tuple(prefixes)) and path.endswith(tuple(suffixes)))


def write_plan(path: str, content: str) -> str:
    """The complete settled WRITE plan for one file in the directive grammar: one WRITE with the
    file's complete final content, then a TEST."""
    return f"WRITE {path}\n{content}\nTEST pytest tests/unit -q\n"


def record_bytes(plan: str, completion: str = "Applied the approved plan.") -> int:
    """What the plan adds to the canonical history once committed (JSON escaping included)."""
    empty = len(render_conversation_envelope({}).encode("utf-8"))
    turn = ConversationTurn(user_prompt="", plan_text=plan, completion_text=completion, outcome=ConversationOutcome.COMPLETED, effect_state=EffectState.COMPLETE)
    return len(render_conversation_envelope({1: turn}).encode("utf-8")) - empty


def percentiles(values: Sequence[int], points: Sequence[int] = (50, 90, 95, 99, 100)) -> dict[str, int]:
    ordered = sorted(values)
    result = {}
    for point in points:
        index = min(len(ordered) - 1, max(0, math.ceil(point / 100 * len(ordered)) - 1))
        result[f"p{point}"] = ordered[index]
    return result


def plan_and_record_bytes(paths: Sequence[str]) -> tuple[list[int], list[int]]:
    """For each file, its complete WRITE plan's bytes and the bytes that plan adds once committed."""
    plans, records = [], []
    for path in paths:
        plan = write_plan(path, (REPO_ROOT / path).read_text(encoding="utf-8"))
        plans.append(len(plan.encode("utf-8")))
        records.append(record_bytes(plan))
    return plans, records


def write_plan_sizes(paths: Sequence[str], ratios: Sequence[Decimal]) -> dict[str, Any]:
    """Representative complete implementer plans: one per tracked Python file, its whole content.
    Plan bytes give the output a reserve must admit; record bytes give the commit reservation."""
    plans, records = plan_and_record_bytes(paths)
    largest = list(zip(plans, paths, strict=True))
    plan_points = percentiles(plans)
    return {
        "files": len(paths),
        "plan_bytes": plan_points,
        "record_bytes": percentiles(records),
        "largest_plans": [{"path": path, "plan_bytes": size} for size, path in sorted(largest, reverse=True)[:5]],
        "reserve_tokens_by_ratio": {str(r): {name: math.ceil(value * r) for name, value in plan_points.items()} for r in ratios},
        "mean_plan_bytes": round(statistics.fmean(plans)),
        "records_within_bytes": {str(limit): round(sum(1 for b in records if b <= limit) / len(records), 4) for limit in (65_536, 131_072)},
    }


class _FinishGateway:
    """A synthetic Gateway reply with a chosen finish status; the reply itself is a valid plan."""

    def __init__(self, finish: str | None, text: str) -> None:
        self.finish, self.text, self.calls = finish, text, 0

    def create_response(self, **kwargs: Any) -> Any:
        from optimus.gateway.models import GatewayResponse, GatewayUsage

        self.calls += 1
        usage = GatewayUsage(gateway_request_id=f"gw-{self.calls}", provider="synthetic", billing_units=1, cost_usd=Decimal("0"))
        return GatewayResponse(output_text=self.text, gateway_usage=usage, raw={}, finish_reason=self.finish)


def completion_status(finishes: Sequence[str | None] = ("stop", "length", "content_filter", "error", None, "unexpected")) -> list[dict[str, Any]]:
    """How the real runner treats each provider finish status for a complete-looking plan or answer,
    per mode: whether the reply is used, and the stop reason. A missing status is left to the
    verified route contract at activation (spec 9.4), and is shown as the runner treats it today."""
    from optimus.agent.models import AgentRunRequest
    from optimus.agent.runner import AgentRunner

    rows = []
    with tempfile.TemporaryDirectory(prefix="p12-limits-") as scratch:
        workspace = Path(scratch)
        (workspace / "a.py").write_text("x = 1\n", encoding="utf-8")
        for mode, text in ((ExecutionMode.CHAT, "A complete answer."), (ExecutionMode.PLAN, "WRITE a.py\nx = 2\n"), (ExecutionMode.AGENT, "WRITE a.py\nx = 2\n")):
            for finish in finishes:
                gateway = _FinishGateway(finish, text)
                request = AgentRunRequest(run_id="measure:1", session_id="measure", task="Change a.py.", workspace_root=workspace, execution_mode=mode)
                result = AgentRunner(gateway_client=gateway, model="synthetic/model").run(request)
                rows.append(
                    {
                        "mode": mode.value,
                        "finish_reason": finish,
                        "status": str(result.status.value),
                        "stop_reason": result.stop_reason,
                        "plan_for_approval": result.plan_hash is not None,
                        "answer_shown": mode is ExecutionMode.CHAT and result.stop_reason is None,
                        "mutations": result.mutation_count,
                        "gateway_calls": gateway.calls,
                    }
                )
    return rows


# --- D1: request allocations and the compaction trigger ---------------------------------------------


def fixed_request_material() -> dict[str, int]:
    """UTF-8 bytes of each request's non-history material at its existing maximums (no history, no
    current prompt): instructions, workspace files, carried observations, current read evidence and
    MCP evidence for planning; instructions and workspace files for Chat; the summarizer's prompt."""
    from optimus.agent.planning_loop import PLANNING_NEW_READ_MAX_BYTES, PLANNING_OBSERVATION_MAX_BYTES
    from optimus.agent.prompts import _MCP_EVIDENCE_MAX_BYTES, _build_chat_answer_input, build_multi_turn_planner_input
    from optimus.agent.workspace_context import DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES

    planning = build_multi_turn_planner_input(
        "",
        planning_turn=3,
        max_planning_turns=3,
        remaining_wall_clock_minutes=30,
        carried_observations_envelope=text_of("ascii", PLANNING_OBSERVATION_MAX_BYTES),
        current_read_evidence_envelope=text_of("ascii", PLANNING_NEW_READ_MAX_BYTES),
        mcp_evidence_envelope=text_of("ascii", _MCP_EVIDENCE_MAX_BYTES),
        initial_workspace_context=text_of("ascii", DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES),
    )
    chat = _build_chat_answer_input("", workspace_context=text_of("ascii", DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES), conversation_envelope="")
    return {
        "planning": len(planning.encode("utf-8")),
        "chat": len(chat.encode("utf-8")),
        "summarizer": len(build_summary_prompt("").encode("utf-8")),
    }


def load_policy() -> Any:
    from importlib import resources

    from optimus_model_policy.registry import load_registry

    with resources.as_file(resources.files("optimus_model_policy") / "defaults.yaml") as defaults:
        return load_registry(defaults, None).policy


def allocation(*, window: int | None, ceiling: int, reserve: int, fixed_tokens: int, prompt_tokens: int) -> dict[str, Any]:
    """Spec 9.4 for one route: the reserve is counted once; history gets what is left after the
    fixed material and the current prompt."""
    if window is None:
        return {"effective_total": None, "usable_input": None, "history_capacity": None, "reason": "window unrecorded"}
    effective_total = min(ceiling, window)
    usable = effective_total - reserve
    return {"effective_total": effective_total, "usable_input": usable, "history_capacity": usable - fixed_tokens - prompt_tokens}


def adr003_trigger(usable_input: int, tier_target: int) -> int:
    """ADR-003's proposed trigger (open item): the smaller of about 80% of usable input and a
    per-tier history target."""
    return min(usable_input * 4 // 5, tier_target)


def allocations(policy: Any, reserves: Mapping[str, int], fixed: Mapping[str, int], ratios: Sequence[Decimal], prompt_bytes: int, tier_targets: Sequence[int]) -> list[dict[str, Any]]:
    """Per role and model: the capacity-driven history space next to ADR-003's proposed trigger at
    each candidate tier target, with list-price input cost of a history that size (illustrative
    arithmetic; no call is made). Nothing is chosen here."""
    from optimus_model_policy.registry import Role, reserve_class

    rows = []
    for role_name, model_ids in sorted(policy.roles.items()):
        role = Role(role_name)
        reserve_name = reserve_class(role)
        reserve = reserves.get(reserve_name)
        material = fixed["summarizer"] if reserve_name == "summarizer" else fixed["planning"]
        for model_id in model_ids:
            entry = policy.models[model_id]
            windows = [endpoint.context_window_tokens for endpoint in entry.route.endpoints]
            window = None if any(w is None for w in windows) else min(windows)
            for ratio in ratios:
                if reserve is None:
                    continue
                cell = allocation(
                    window=window, ceiling=policy.context_ceiling_tokens, reserve=reserve,
                    fixed_tokens=math.ceil(material * ratio), prompt_tokens=0 if reserve_name == "summarizer" else math.ceil(prompt_bytes * ratio),
                )  # fmt: skip
                price = Decimal(str(entry.prices.input_usd_per_million))
                triggers = []
                if cell["usable_input"] is not None:
                    for target in tier_targets:
                        trigger = adr003_trigger(cell["usable_input"], target)
                        triggers.append({"tier_target": target, "trigger_tokens": trigger, "input_usd_at_trigger": str((price * trigger / 1_000_000).quantize(Decimal("0.0001")))})
                capacity = cell["history_capacity"]
                floor_bytes = CONVERSATION_MAX_BYTES + material  # the floor already includes the current prompt
                rows.append(
                    {
                        "role": role_name,
                        "model": model_id,
                        "tier": str(entry.tier.value),
                        "reserve_class": reserve_name,
                        "ratio": str(ratio),
                        "output_reserve": reserve,
                        **cell,
                        # D7 (ADR-014): an engine-absent request carrying the full 524288-byte floor plus
                        # this path's maximum material must fit; the largest content ratio that allows it.
                        "absent_floor_request_bytes": floor_bytes if reserve_name == "implementer" else None,
                        "absent_floor_fits": None if cell["usable_input"] is None or reserve_name != "implementer" else math.ceil(floor_bytes * ratio) <= cell["usable_input"],
                        "absent_floor_max_ratio": None if cell["usable_input"] is None or reserve_name != "implementer" else round(cell["usable_input"] / floor_bytes, 4),
                        "capacity_input_usd": None if capacity is None else str((price * max(capacity, 0) / 1_000_000).quantize(Decimal("0.0001"))),
                        "adr003_triggers": triggers,
                    }
                )
    return rows


# --- Checking a proposal -----------------------------------------------------------------------------

PROPOSAL_KEYS = (
    "source_max_bytes",
    "record_reservation_bytes",
    "view_source_max_bytes",
    "transient_max_bytes",
    "maintenance_input_tokens",
    "summary_output_tokens",
    "max_maintenance_calls",
    "anchor_input_tokens",
    "compaction_tail_input_tokens",
    "hybrid_tail_input_tokens",
    "implementer_output_reserve",
    "summarizer_output_reserve",
    "history_input_tokens_by_tier",
    "prompt_allowance_bytes",
)
LOWEST_RATIO = Decimal("0.25")
"""The lowest tokens-per-byte ratio the byte bounds are sized for: below it, a byte bound binds before
the token bound would."""


def _route_bounds(policy: Any, roles: Sequence[str]) -> list[dict[str, Any]]:
    rows = []
    for role in roles:
        for model_id in policy.roles.get(role, []):
            endpoints = policy.models[model_id].route.endpoints
            windows = [endpoint.context_window_tokens for endpoint in endpoints]
            outputs = [endpoint.max_output_tokens for endpoint in endpoints]
            rows.append(
                {
                    "role": role,
                    "model": model_id,
                    "tier": str(policy.models[model_id].tier.value),
                    "window": None if None in windows else min(windows),
                    "max_output": None if None in outputs else min(outputs),
                }
            )
    return rows


def check_proposal(proposal: Mapping[str, Any], *, policy: Any, plan_bytes: Sequence[int], record_bytes_measured: Sequence[int], fixed: Mapping[str, int]) -> dict[str, Any]:
    """Every arithmetic relationship a proposed value set must satisfy, checked against the measured
    plans and the registry's recorded routes, at the byte-level bound (ratio 1) unless stated. Returns
    the violations (empty when consistent) and what the values cover. It accepts nothing."""
    missing = [key for key in PROPOSAL_KEYS if key not in proposal]
    if missing:
        return {"violations": [f"missing {key}" for key in missing], "coverage": {}}
    p = proposal
    ceiling = policy.context_ceiling_tokens
    violations: list[str] = []

    def need(condition: bool, message: str) -> None:
        if not condition:
            violations.append(message)

    need(p["source_max_bytes"] > CONVERSATION_MAX_BYTES, "attached source limit must exceed the engine-absent floor (ADR-003 item 1)")
    need(0 <= p["record_reservation_bytes"] < p["source_max_bytes"], "record reservation must be below the source limit")
    need(p["view_source_max_bytes"] >= p["source_max_bytes"], "the engine's source limit must admit every history storage admits")
    need(p["hybrid_tail_input_tokens"] > p["compaction_tail_input_tokens"], "hybrid's exact tail must exceed compaction's (spec 6.3)")
    need(p["implementer_output_reserve"] > 0 and p["summarizer_output_reserve"] > 0, "every output reserve must be positive (spec 9.4)")
    need(p["summary_output_tokens"] <= p["summarizer_output_reserve"], "a summary must fit the summarizer's output reserve")
    need(p["transient_max_bytes"] >= math.ceil(p["maintenance_input_tokens"] / LOWEST_RATIO), "the transient byte bound must not bind before the token bound")
    need(p["max_maintenance_calls"] >= 1, "maintenance needs at least one call")
    # The strategy allocations must be realizable inside the smallest history target (Fable CP4 review
    # MINOR-2): otherwise hybrid's larger tail is only nominal there.
    smallest_target = min(p["history_input_tokens_by_tier"].values())
    need(
        p["anchor_input_tokens"] + p["hybrid_tail_input_tokens"] + p["summary_output_tokens"] <= smallest_target,
        "hybrid's anchor, tail and summary must fit the smallest history target",
    )
    need(p["compaction_tail_input_tokens"] + p["summary_output_tokens"] <= smallest_target, "compaction's tail and summary must fit the smallest history target")
    summary_prompt_tokens = fixed["summarizer"]
    summarizers = _route_bounds(policy, ("summarizer",))
    for route in summarizers:
        if route["window"] is None or route["max_output"] is None:
            continue
        need(p["summarizer_output_reserve"] <= route["max_output"], f"summarizer reserve exceeds {route['model']}'s max output")
        total = min(ceiling, route["window"])
        need(summary_prompt_tokens + p["maintenance_input_tokens"] + p["summarizer_output_reserve"] <= total, f"a maintenance call does not fit {route['model']}")
    implementer_roles = ("easy", "medium", "complex", "escalation")
    implementer_tiers = set()
    binding: dict[str, str] = {}
    for route in _route_bounds(policy, implementer_roles):
        implementer_tiers.add(route["tier"])
        if route["max_output"] is not None:
            need(p["implementer_output_reserve"] <= route["max_output"], f"implementer reserve exceeds {route['model']}'s max output")
        if route["window"] is None:
            continue
        usable = min(ceiling, route["window"]) - p["implementer_output_reserve"]
        target = p["history_input_tokens_by_tier"].get(route["tier"])
        if target is not None:
            # `prompt_allowance_bytes` is an assumed current-prompt size, not a bound: nothing but
            # admission bounds an attached prompt, and an oversized one is refused by `fit()`.
            need(target + fixed["planning"] + p["prompt_allowance_bytes"] <= usable, f"{route['tier']} history target leaves no room for planning material on {route['model']}")
            binding[route["tier"]] = "tier target" if target <= usable * 4 // 5 else "80% of usable input"
    for tier in p["history_input_tokens_by_tier"]:
        need(tier in implementer_tiers, f"history target for {tier} has no active implementer route to check it against")
    # A cold rebuild of the whole attached source, in whole-turn chunks each carrying the prior summary
    # (Fable CP4 review MAJOR-1): the perfect-packing minimum, and the whole-turn worst case, when
    # every turn is just over half a chunk so each call carries one turn. The allowance must cover the
    # worst case, or a strategy switch on such a history is refused.
    # The summary byte bound is derived, floor(S / r), and must sit below the transient bound; the call
    # allowance must cover the proven whole-turn worst case in both budgets (Codex's final corrections C2).
    worst_by_ratio = {str(ratio): whole_turn_worst_calls(p, ratio) for ratio in CHECK_RATIOS}
    for ratio, worst in worst_by_ratio.items():
        need(0 < worst["summary_max_bytes"] < p["transient_max_bytes"], f"the derived summary byte bound at ratio {ratio} must be below the transient bound")
        need(
            worst["calls"] is not None and worst["calls"] <= p["max_maintenance_calls"],
            f"the call allowance cannot rebuild the whole source in its whole-turn worst case at ratio {ratio}",
        )
    worst_calls = worst_by_ratio["1"]["calls"]

    usable_implementer = ceiling - p["implementer_output_reserve"]
    # D7 (ADR-014): the 524288-byte floor already includes the current prompt (admission measures the
    # history plus the provisional turn), so only the path's other material is added (Fable MAJOR-2).
    floor_request = CONVERSATION_MAX_BYTES + fixed["planning"]
    coverage = {
        "plans_within_implementer_reserve": {str(r): round(sum(1 for b in plan_bytes if math.ceil(b * r) <= p["implementer_output_reserve"]) / len(plan_bytes), 4) for r in ESTIMATOR_RATIOS},
        "records_within_reservation": round(sum(1 for b in record_bytes_measured if b <= p["record_reservation_bytes"]) / len(record_bytes_measured), 4),
        "cold_rebuild_whole_turn_worst_by_ratio": worst_by_ratio,
        "cold_rebuild_list_price_usd": _cold_rebuild_cost(p, policy, summarizers, worst_calls, summary_prompt_tokens),
        "absent_floor_max_ratio": round(usable_implementer / floor_request, 4),
        "largest_single_turn_bytes_summarizable_by_ratio": {str(ratio): largest_summarizable_turn_bytes(p, ratio) for ratio in CHECK_RATIOS},
        "trigger_binding_term_by_tier": binding,
    }
    return {"violations": violations, "coverage": coverage}


def _cold_rebuild_cost(p: Mapping[str, Any], policy: Any, summarizers: Sequence[Mapping[str, Any]], calls: int | None, prompt_tokens: int) -> dict[str, str]:
    """Illustrative list-price cost of a worst-case cold rebuild on each summarizer route, at the
    byte-level bound: the whole source once, every later call's prior summary and header, each call's
    fixed prompt; every call's summary as output. No call is made."""
    if calls is None:
        return {}
    header = len(PRIOR_SUMMARY_HEADER.encode("utf-8"))
    input_tokens = p["source_max_bytes"] + (calls - 1) * (header + p["summary_output_tokens"]) + calls * prompt_tokens
    output_tokens = calls * p["summary_output_tokens"]
    costs = {}
    for route in summarizers:
        prices = policy.models[route["model"]].prices
        usd = Decimal(str(prices.input_usd_per_million)) * input_tokens / 1_000_000 + Decimal(str(prices.output_usd_per_million)) * output_tokens / 1_000_000
        costs[route["model"]] = str(usd.quantize(Decimal("0.0001")))
    return costs


# --- Report -------------------------------------------------------------------------------------------


def environment() -> dict[str, Any]:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip())
    return {
        "schema": REPORT_SCHEMA,
        "git_head": head,
        "worktree_dirty": dirty,
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "gil_enabled": getattr(sys, "_is_gil_enabled", lambda: True)(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def run(*, quick: bool, implementer_reserve: int, summarizer_reserve: int, proposal: Mapping[str, Any] | None = None) -> dict[str, Any]:
    sizes = QUICK_SIZES_KIB if quick else FULL_SIZES_KIB
    levels = QUICK_CONCURRENCY if quick else FULL_CONCURRENCY
    alphabets = ("ascii", "emoji") if quick else tuple(ALPHABETS)
    fixture = EngineFixture()
    tracemalloc.start()
    try:
        report: dict[str, Any] = {"environment": environment(), "quick": quick, "fixture": dataclasses.asdict(fixture) | {"ratio": str(fixture.ratio)}}
        report["history_scaling"] = history_scaling(alphabets, sizes, ("full", "sliding_window", "compaction", "hybrid"), fixture)
        report["concurrency"] = concurrency("ascii", sizes[-2] if len(sizes) > 1 else sizes[0], levels, fixture)
        report["storage_boundaries"] = [
            storage_boundaries(a, source_max_bytes=2 * CONVERSATION_MAX_BYTES, reservation=65_536) for a in (("ascii",) if quick else alphabets)
        ]
        report["engine_source_boundary"] = [engine_source_boundary(a) for a in alphabets]
        report["protected_growth"] = protected_growth(ESTIMATOR_RATIOS, (0, 1, 4), (65_536, 131_072, 200_000))
        report["protected_growth_check"] = [protected_growth_check(1, Decimal("1"), 16_384 if quick else 65_536)]
        report["huge_anchor"] = huge_anchor((64,) if quick else (16, 64, 256, 1024), fixture)
        report["sanitizer_scaling"] = sanitizer_scaling((4, 16) if quick else (16, 64, 256, 1024), (2, 4) if quick else (4, 8, 16, 32))
        paths = tracked_text_files()
        report["write_plans"] = write_plan_sizes(paths[:40] if quick else paths, ESTIMATOR_RATIOS)
        report["completion_status"] = completion_status()
        policy = load_policy()
        fixed = fixed_request_material()
        report["fixed_request_material_bytes"] = fixed
        reserves = {"implementer": implementer_reserve, "summarizer": summarizer_reserve}
        report["allocation_inputs"] = {"output_reserves": reserves, "prompt_bytes": 8_192, "tier_targets": [65_536, 100_000, 131_072]}
        report["allocations"] = allocations(policy, reserves, fixed, ESTIMATOR_RATIOS, 8_192, (65_536, 100_000, 131_072))
        if proposal is not None:
            plans, records = plan_and_record_bytes(paths[:40] if quick else paths)
            report["proposal"] = dict(proposal)
            report["proposal_check"] = check_proposal(proposal, policy=policy, plan_bytes=plans, record_bytes_measured=records, fixed=fixed)
            report["proposed_policy_rows"] = proposed_policy_rows(proposal)
        return report
    finally:
        tracemalloc.stop()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="JSON report path")
    parser.add_argument("--quick", action="store_true", help="small sizes, for tests")
    parser.add_argument("--implementer-reserve", type=int, default=32_768, help="candidate implementer output reserve (tokens)")
    parser.add_argument("--summarizer-reserve", type=int, default=4_096, help="candidate summarizer output reserve (tokens)")
    parser.add_argument("--proposal", type=Path, help="a proposed value set (JSON) to check against the measurements")
    args = parser.parse_args(argv)
    proposal = json.loads(args.proposal.read_text(encoding="utf-8")) if args.proposal else None
    report = run(quick=args.quick, implementer_reserve=args.implementer_reserve, summarizer_reserve=args.summarizer_reserve, proposal=proposal)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes((json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
