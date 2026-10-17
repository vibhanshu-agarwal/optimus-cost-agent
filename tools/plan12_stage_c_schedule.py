"""Plan 12.2 Task 13 (Stage C): the executable claim-to-case schedule, computed offline (Codex scope
agreement, 2026-10-11, section 5; Codex completion review R3 and R4).

Nothing here calls a model, starts a service or touches the operator's ledger. Three figures are kept apart:

- the conservative complete-case bound, the one an envelope is sized against. Each case's model calls are
  bounded by host limits read from source: the approved planning-turn limit, the attached turn-wide
  maintenance allowance (shared by a turn's view and its repack), the scenario's zero-call and cancellation
  turns, and a sliding view's lack of maintenance. Each call is bounded by the most its request can reserve:
  an answer or planning request at the route's usable input (the Gateway refuses more before any attempt)
  and its full output cap; a summary request at the engine's maintenance input limit inside the summary
  prompt and its full summary cap; at the registry's conservative prices. Dollars count one potentially
  billed attempt per call (a resend follows only a proven unbilled attempt); attempts count both;
- measured allocations: the attached cases run through the real ACP adapter, the real Context Engine and the
  real attached Stage C composition (seed, limits, scenario controls) with a fake Gateway and planner whose
  replies have a stated size, so each call's input is the real packing of the pinned seed and of the earlier
  replies. Several reply sizes show how replies move later packing, checkpoint reuse and maintenance. Each
  is one fixed-fake path's allocation: never a bound, never a prediction;
- expected spend: informational only. No Agent or Chat expectation is derived from summary observations.

The runbook is executable with the installed acpx 0.12.0 (no install or upgrade) and Zed. acpx starts the
qualification Stage C host from the reviewed executable directly. The denied Agent case is a one-shot `exec`. The Chat case creates a
fresh named session, saves Chat as its mode and prompts: Optimus advertises no session/load, so the
prompt's own host starts a fresh runtime session and acpx replays the saved mode on it before the prompt (a
failed replay fails the command). An explicit close ends it. A custody check (no Gateway listening, ledger
lock free, no host left; the same window and non-decreasing totals as the previous check) follows every
launch, and every launch shares the one release ledger and window. A schedule is a ceiling, not a promise
that every case finishes: a guard stop, an expired window or a failed case leaves the rest UNRUN.

The generated workspace prepares every case target's folder (the writer creates none) and holds no target;
`--verify-workspace` checks exactly that before the first launch.

Schedule v6 (release r5; Codex's r5 proposal of 2026-10-15) keeps every v5 case and its bound. Every launch
path (acpx's agent and both Zed entries) enables the host's existing `--debug-trace`, so a dispatched
request's typed attempt statuses reach the workspace's `.optimus/debug-acp.ndjson`. Each completed launch's
runtime logs and ledger are copied before its custody check, so no later launch mixes into its evidence.

Schedule v7 (after r5 stopped at A6; Codex's review f381e730) keeps every case and its bound. r5's A6 never
started: acpx splits its --agent value itself, treating a backslash as an escape except inside single quotes,
and runs a .cmd agent through cmd. So acpx now launches the reviewed optimus-agent.exe directly, every part
single-quoted; the runbook declares the shell its acpx commands run from; and its first step requires a fresh,
passing real-client launch rehearsal (tools/plan12_stage_c_launch_rehearsal.py) before the operator's hour.

Schedule v8 (after r6 stopped at A5; Codex's ruling 6216185282) keeps every case, claim and bound and changes only
A5's execution context. Zed 1.24.2 reuses an empty thread when asked for a new one (no session/new), and Optimus opens
every session in Agent, so a new session showing Agent proves no persistence. A5 now runs in A4's content-bearing
thread, ends on Chat (the non-default) and opens its new session from that thread; Zed applies a persisted
non-default mode with session/set_config_option right after session/new (r6's trace), which is the evidence. Zed also
restores the last thread's agent when it starts (r7's offline walk), so before L2 the qualification entry is hidden and
only the attached entry can start.

Schedule v9 (after r7 stopped at A2; Codex's r8 proposal c500fc61) keeps every case, claim and bound and makes A2's
handshake explicit: r7's permission request was approved within seconds, before its required capture. The driver
tells the operator to leave the request pending, captures and checks it, then signals "capture taken \u2014 approve
now" in its own chat; only on that signal does the operator approve the exact artifact.

Schedule v10 (after r8 stopped at B7.6 on a charged reply refusal; Codex's proposal 235d7b7e, operator-approved
2026-10-17) keeps every case, prompt, criterion and the bound. r6, r7 and r8 each stopped at their first failed case,
so one paid hour found one defect. Absolute stops stay absolute and now name every condition that ends the run. Any
other failure is recorded FAILED and never retried, and the run continues only with cases whose predecessors ran and
whose state preconditions are proved: each case names them, and one whose precondition is missing is BLOCKED and never
sent. After a charged, fully settled reply refusal, one qualification Zed restart may run the L1 cases not yet run; the
attached launch is never relaunched (a new attached host reseeds its first session and restarts its live-turn count).
Claude starts each Zed launch itself through an ordinary shortcut; B2 may run right after B3.1 when inert evidence
proves Zed returns to T1 without a new or loaded session.

Usage: python tools/plan12_stage_c_schedule.py --out <dir> [--summary-bytes N] [--reply-bytes N ...]
           [--agent-exe <optimus-agent.exe>] [--evidence <dir>]
       python tools/plan12_stage_c_schedule.py --verify-workspace <workspace>
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any

from context_engine.summary import SECTIONS, build_summary_prompt
from optimus.acp import stage_c as host
from optimus.acp.conversation import ConversationOutcome, ConversationTurn, render_conversation_envelope
from optimus.acp.launch_policy import DEFAULT_MAX_PLANNING_TURNS
from optimus.acp.session_config import STRATEGY_CONFIG_ID
from optimus.acp.settlement import EffectState
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.acp.test_composition import compose_test_composition
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.runtime.modes import ExecutionMode
from optimus_model_policy import stage_c
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.binding import MAX_ROUTE_ATTEMPTS, approval_literal

REPO_ROOT = Path(__file__).resolve().parents[1]
HAIKU = "anthropic/claude-haiku-5.5"
T0 = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
CAPACITY_PROMPT_BYTES = 430_000  # over the request capacity (229,376 input tokens) and the 80% storage warning, under storage
STORAGE_PROMPT_BYTES = 530_000  # over the 524,288-byte absent-engine storage limit
SCHEDULE_VERSION = "stage-c-schedule-v10"
RUNTIME_FILES = ("debug-acp.ndjson", "telemetry.jsonl", "local-gateway.log", "launch-audit.ndjson")  # under <workspace>/.optimus
REPLY_SIZES = (3, 8_192, 32_768, 131_072)  # fake reply bytes per measured path; 131,072 = the 32,768-token cap at 4 bytes a token
DEFAULT_UNRUN = "the guard refuses a call, the window ends or an earlier required case failed"
CENT = Decimal("0.000001")
A7_SESSION = "stage-c-a7"
# Schedule v10: B2 (an unseeded second session) runs right after B3.1, then the driver returns to T1, so a later failure on
# T1 cannot block it. Its session is not the seeded one, so the live-turn count and every other case are unchanged. The
# branch is chosen before technical acceptance, from sealed inert evidence that returning to T1 makes no session/load and
# no new session; without that proof it is False (B2 last), never changed during a run.
B2_AFTER_FIRST_TURN = True
# B2 ran in Chat with Hybrid while it ran last (Zed persisted both from T1). After B3.1, T1's strategy is still the initial
# Compaction, so the driver sets Hybrid on T2 before B2's prompt: its criterion and conditions are unchanged.
B2_STRATEGY = "hybrid"
# The pinned Zed client Claude starts through an ordinary shortcut (explorer.exe), so Zed gets the user's environment.
ZED_CLIENT = {
    "version": "1.24.2",
    "exe": r"%LOCALAPPDATA%\Programs\Zed\Zed.exe",
    "sha256": "87a6f2c652ef9d66902c870942cee1d9a6186acfdf2ca9f94e6f9149eaeb1195",  # pragma: allowlist secret - public file digest
}

# --- Prompts, files and cases ---------------------------------------------------------------------------------


def _filler(label: str, size: int) -> str:
    line = f"{label}: synthetic Stage C paste text with no secret and no instruction. "
    return (line * (size // len(line) + 1))[:size]


PROMPT_FILES = {
    "capacity-prompt.txt": _filler("capacity", CAPACITY_PROMPT_BYTES),
    "storage-prompt.txt": _filler("storage", STORAGE_PROMPT_BYTES),
}
WORKSPACE_FILES = {
    "README.md": "# Stage C synthetic workspace\n\nA scratch workspace for the Plan 12.2 Stage C editor evidence. No real data.\n",
    "notes/calculator.md": "Calculator notes: use Decimal for every amount; round with ROUND_HALF_EVEN to two places.\n",
}
# The writer creates no parent folder, so every case target's folder is prepared (r2's A2 stopped on a missing
# scratch/); without it the absence checks of A6 and A7 would hold whatever the client did.
WORKSPACE_DIRS = ("notes", "scratch")
A1_PROMPT = "Create a file named notes/chat-should-not-write.md containing the word hello."
A2_PROMPT = "Create scratch/stage-c-agent.txt containing the single word ready."
A6_PROMPT = "Create scratch/acpx-denied.txt containing denied."
A7_PROMPT = "Write scratch/acpx-chat.txt containing hello."


def _target(prompt: str) -> str:
    match = re.search(r"\b[\w-]+/[\w.-]+\.\w+", prompt)
    if match is None:
        raise ValueError(f"no file target in {prompt!r}")
    return match.group(0)


# The files the A cases name: none exists before the first launch.
WORKSPACE_TARGETS = tuple(_target(prompt) for prompt in (A1_PROMPT, A2_PROMPT, A6_PROMPT, A7_PROMPT))

# Live attached turns of the designated (seeded) session, in order: (live turn, case, strategy set before it, prompt).
ATTACHED_TURNS = (
    (1, "B3", None, "Live turn 1: summarize where the calculator work stands, in three bullet points."),
    (2, "B4", None, "Live turn 2: which rounding rule is current, and since which step?"),
    (3, "B5", "sliding_window", "Live turn 3: list the last two steps you can see."),
    (4, "B6", "compaction", "Live turn 4: what changed most recently?"),
    (5, "B6", None, "Live turn 5: try again: what changed most recently?"),
    (6, "B7", None, "Live turn 6: confirm the current rounding rule in one sentence."),
    (7, "B8", "hybrid", "Live turn 7: summarize the whole history again (this turn will be cancelled during maintenance)."),
)
SMALL_SESSION_PROMPT = "In one sentence: what is this scratch workspace for?"
# The meter follows a committed, dispatched turn (design spec 8.4): a refused turn dispatches and commits
# nothing, so it sends no new reading (r3's A3 stopped on the opposite expectation), and a turn that makes no
# call leaves no ledger record to collect.
METER_READING = (
    "the request meter after the committed turn: the largest dispatched planning or answer input against its usable capacity, "
    "separate from any storage notice"
)
NO_METER_READING = "no new request-meter reading: a refused turn dispatches and commits nothing, so it sends none (design spec 8.4)"
NO_LEDGER_RECORD = "no Gateway reserve/settle record for the turn: the engine refuses before any call"
# The host records the approved mutation but not the path a permission request named, so A2's exact artifact is
# captured from the request itself, before the click (r3's A2 evidence showed only the completed write).
A2_PERMISSION_CAPTURE = "a screenshot of the permission request taken before approval, naming exactly scratch/stage-c-agent.txt"
# Schedule v9: the operator approves A2 only on the driver's explicit signal, given after the capture (r7's A2 was approved
# before its capture; Codex's r8 proposal c500fc61).
A2_SIGNAL = "capture taken \u2014 approve now"
# Key isolation (Plan 9.9): the environment passed to acpx holds no provider key; the host takes it from the OS
# keyring. Recorded as variable names only, never values.
KEY_ISOLATION_CHECK = (
    "no provider key in the environment acpx passes to the agent: the names (never the values) of its key-like variables, "
    "none a provider key; the host takes the key from the OS keyring"
)
_B_EXPECTED = {
    "B3": ["the attached picker shows Mode and Context strategy", "a compaction view of the 576 KiB seeded history", METER_READING],
    "B4": ["the next turn reuses the checkpoint"],
    "B5": ["the sliding-window warning on the first admitted sliding turn"],
    "B6": [host.UNAVAILABLE_NOTICE, "the readable unavailable refusal: above the 512 KiB floor no full-history fallback"],
    "B7": ["a healthy compaction turn"],
    "B8": ["the pause notice after the turn's first summary call", "the turn ends cancelled after the operator presses Cancel", "no second summary call; the first charge kept"],
}
_B_CLAIMS = {
    "B3": ["attached-history-over-512kib", "attached-picker", "meter-versus-storage-notices"], "B4": ["checkpoint-reuse"], "B5": ["sliding-warning"],
    "B6": ["repeated-engine-unavailability"], "B7": ["healthy-recovery"], "B8": ["cancellation-between-maintenance-calls"],
}  # fmt: skip


@dataclass
class Call:
    kind: str  # "planning", "chat", "summary"
    input_tokens: int
    output_cap: int
    note: str = ""

    def reserve_usd(self, prices: tuple[Decimal, Decimal]) -> Decimal:
        return stage_c.reservation_usd(input_tokens=self.input_tokens, output_tokens=self.output_cap, input_usd_per_million=prices[0], output_usd_per_million=prices[1])

    def row(self, prices: tuple[Decimal, Decimal]) -> dict[str, Any]:
        reserve = str(self.reserve_usd(prices).quantize(CENT, ROUND_CEILING))
        return {"kind": self.kind, "input_tokens": self.input_tokens, "output_cap": self.output_cap, "reserve_usd": reserve, "note": self.note}


@dataclass
class Case:
    case: str
    launch: str
    client: str
    session: str
    steps: list[str]
    expected: list[str]
    artifacts: list[str]
    claims: list[str]
    bound: tuple[int, int, str]  # (answer or planning calls, summary calls, basis)
    unrun_if: str = ""
    after: tuple[str, ...] = ()  # the cases whose run supplies this case's state (any verdict), in run order
    requires: list[str] = field(default_factory=list)  # the state and evidence proved before it runs, never inferred
    needs_route: bool = True  # whether its criterion needs its launch's Gateway route unstopped

    def __post_init__(self) -> None:
        self.unrun_if = self.unrun_if or DEFAULT_UNRUN


# Schedule v10: each case's predecessors, its state preconditions (proved from evidence; a submitted prompt proves
# nothing) and whether it needs its launch's route (Codex's proposal 235d7b7e).
_DEPENDENCIES: dict[str, tuple[tuple[str, ...], list[str], bool]] = {
    "A1": ((), ["the exact L1 qualification launch, started by Claude, with a fresh S1 (Zed's first new thread); entry custody CLEAR"], True),
    "A2": (("A1",), ["S1 active in this launch, or a fresh S1 after the one eligible qualification restart", "an available qualification route",
                     "scratch/stage-c-agent.txt absent", "the operator present for the genuine exact-artifact approval"], True),
    "A3": (("A1",), ["an available qualification route: A3's criterion is the Gateway's own preflight capacity refusal",
                     "a fresh Chat session opened from a proved content-bearing thread (S1, or the restart's first thread)", "the exact capacity-prompt.txt"], True),
    "A4": (("A3",), ["a fresh Chat session opened from A3's proved content-bearing thread", "the exact storage-prompt.txt; no state repair"], False),
    "A5": (("A4",), ["A4's actual content-bearing thread", "the original Agent, Chat, Chat switches and a distinct new session; no extra prompt"], False),
    "A6": ((), ["the L1 Zed launch closed with custody CLEAR", "a fresh qualification acpx host for the denied-artifact exec"], True),
    "A7": ((), ["custody CLEAR after A6", "its own sessions new, set-mode, prompt and close in order: set-mode needs sessions new and the prompt needs "
                "set-mode; close and cleanup run even after a failure"], True),
    "B3.1": ((), ["the exact attached launch, started by Claude", "T1 designated with its seed accepted", "live turn 1 of T1"], True),
    "B2": (("B3.1",), ["an available attached route", "a distinct unseeded T2 opened from content-bearing T1 (B3.1's prompt admitted)",
                       "T2 in Chat with Hybrid (Zed's persisted Chat and, when B2 runs right after B3.1, the explicit Hybrid setter); no maintenance"], True),
    "B4.2": (("B3.1",), ["the same T1 at live turn 2", "B3.1 committed with its published checkpoint (proved from the trace and receipts, not from its prompt)"], True),
    "B5.3": (("B4.2",), ["the same T1 with live turns 1-2 actually admitted", "the original sliding_window change"], True),
    "B6.4": (("B5.3",), ["the same T1 with live turns 1-3 actually admitted, so this is turn 4", "the original unavailability criterion and fixture state"], False),
    "B6.5": (("B6.4",), ["the same T1 with live turns 1-4 actually admitted, so this is turn 5"], False),
    "B7.6": (("B6.5",), ["the same T1 with live turns 1-5 actually admitted (the scheduled turn-4/5 unavailability exercised), so this is turn 6"], True),
    "B8.7": (("B7.6",), ["the same T1 with live turns 1-6 actually admitted, so this is turn 7", "the original hybrid change and the pause/cancel criterion"], True),
}  # fmt: skip


def _cases(b2_early: bool = B2_AFTER_FIRST_TURN) -> list[Case]:
    zed_absent, zed_attached, acpx_absent = "L1 qualification launch (Zed)", "L2 attached launch (Zed)", "L1 qualification launch (acpx)"
    planning = (DEFAULT_MAX_PLANNING_TURNS, 0, f"at most {DEFAULT_MAX_PLANNING_TURNS} planning requests (the approved planning-turn limit)")
    chat = (1, 0, "one Chat answer request")
    cases = [
        Case("A1", zed_absent, "zed", "absent session 1 (Chat)", ["Switch the session to Chat.", f"Prompt: {A1_PROMPT}"],
             ["a Chat answer; no permission request"], ["the workspace has no notes/chat-should-not-write.md"], ["chat-non-mutation"], chat),
        Case("A2", zed_absent, "zed", "absent session 1 (Agent)",
             [f'Before the prompt, tell the operator to leave the coming permission request pending until the driver\'s explicit signal "{A2_SIGNAL}" '
              "(never on silence or another chat's message).",
              "Switch the session to Agent.", f"Prompt: {A2_PROMPT}",
              "Capture the pending permission request at once, before anything else: it must name exactly scratch/stage-c-agent.txt with content ready.",
              f'Then signal "{A2_SIGNAL}" in the driver\'s chat, linked to the saved capture.',
              "Only on that signal, the operator approves the exact artifact in the permission request."],
             ["a session/request_permission naming exactly scratch/stage-c-agent.txt", "the turn completes after approval"],
             [A2_PERMISSION_CAPTURE, f'the driver\'s "{A2_SIGNAL}" signal, given after the capture', "scratch/stage-c-agent.txt contains ready"],
             ["agent-exact-artifact-approval"], planning),
        Case("A3", zed_absent, "zed", "absent session 2 (Chat)", ["Paste the whole of capacity-prompt.txt as one prompt."],
             ["the 80% storage warning notice", "the readable request-capacity refusal (INPUT_EXCEEDS_CAPACITY text)", NO_METER_READING],
             ["zero upstream attempts for the turn in the Gateway ledger"], ["request-capacity-refusal", "meter-versus-storage-notices"],
             (0, 0, "the Gateway refuses the over-capacity input before any attempt")),
        Case("A4", zed_absent, "zed", "absent session 3 (Chat)", ["Paste the whole of storage-prompt.txt as one prompt."],
             ["the storage refusal (not the request-capacity refusal)"], ["zero upstream attempts"], ["storage-refusal"],
             (0, 0, "the host refuses the over-storage input before any request")),
        # The engine-absent profile advertises Mode alone (Agent, Chat); no profile enables model selection
        # (session_config.py), so A5 never asks for a model picker (Codex schedule v4 review M1).
        # Schedule v8: Zed reuses an empty thread for a new one, and Optimus opens every session in Agent, so A5 runs in A4's
        # content-bearing thread and ends on the non-default Chat before opening its new session (Codex's ruling 6216185282).
        Case("A5", zed_absent, "zed", "A4's session 3 (content-bearing; Chat), then a new session 4 opened from it",
             ["In A4's thread (session 3, holding A4's refusal), open the Mode selector and capture the advertised Agent and Chat choices with "
              "Chat selected. Change to Agent, then reopen Mode and capture both choices with Agent selected. Then change back to Chat and "
              "capture Chat selected.",
              "Confirm the engine-absent profile advertises neither Context strategy nor a model selector; do not require controls that the "
              "profile does not enable.",
              "From that content-bearing thread, open a new qualification thread (never from an empty thread: Zed reuses it and opens no "
              "session). Capture the new session's selected mode. Send no prompt."],
             ["Mode continues to offer Agent and Chat after switching; its selected value is correct.",
              "Context strategy and model selection are absent under this exact qualification profile.",
              "The persisted mode reaches the new session: a distinct session/new, then Zed's session/set_config_option mode=chat on that "
              "new session, and Chat selected on screen.",
              "A stale setter on session 3, a client label alone or the Agent default cannot pass."],
             ["Screenshots of Mode in session 3 (Chat, Agent, Chat) and of the new session's Chat selection.",
              "A content-free observation of the advertised selector set (Mode only).",
              "The debug trace's session/new for the new session and the session/set_config_option that follows it."],
             ["absent-picker-and-persisted-default"], (0, 0, "no prompt is sent")),
        Case("A6", acpx_absent, "acpx", "acpx one-shot session (Agent, denied)",
             ["Before the exec, record the names (never the values) of the key-like variables the command's environment holds: none may be a provider key.",
              "The runbook's A6 exec command (one-shot, its own fresh session, every permission denied)."],
             ["a permission request answered deny", "no file written"], ["acpx JSON transcript", "scratch/acpx-denied.txt absent", KEY_ISOLATION_CHECK],
             ["agent-exact-artifact-approval", "key-isolation"], planning),
        Case("A7", acpx_absent, "acpx", f"acpx named session {A7_SESSION} (Chat)", ["The runbook's A7 commands: a fresh named session, its mode set to Chat, the prompt, the close."],
             ["the Chat mode applied to the prompt's fresh runtime session before the prompt", "a Chat answer; no permission request"],
             ["acpx JSON transcripts", "scratch/acpx-chat.txt absent"], ["chat-non-mutation"], chat),
    ]  # fmt: skip
    schedule = stage_c.STAGE_C_SCENARIOS[stage_c.STAGE_C_ATTACHED_SCENARIO]["schedule"]
    strategy = "compaction"  # the attached composition's initial strategy
    for live, case_id, change, text in ATTACHED_TURNS:
        strategy = change or strategy
        if live in schedule["engine_unavailable_turns"]:
            bound = (0, 0, "a scheduled unavailable turn: the engine refuses before any call")
        elif live == schedule["cancel_pause_turn"]:
            bound = (
                1,
                schedule["cancel_pause_before_call"] - 1,
                "the cancellation turn: its maintenance calls before the pause (the turn's next call, a repack's included, waits for the cancel; "
                "cancelled or UNRUN, nothing follows); a turn that never reaches the paused call answers once",
            )
        elif strategy == "sliding_window":
            bound = (1, 0, "a sliding view makes no maintenance call; one answer")
        else:
            bound = (1, host.MAX_MAINTENANCE_CALLS, f"at most the turn-wide maintenance allowance ({host.MAX_MAINTENANCE_CALLS}, view and repack together), then one answer")
        steps = ([f"Set Context strategy to {change}."] if change else []) + [f"Prompt: {text}"]
        if case_id == "B8":
            steps.append("When the pause notice appears, press Cancel within 30 seconds.")
        ledger = "the Gateway ledger's reserve/settle records for the turn" if bound[0] + bound[1] else NO_LEDGER_RECORD
        cases.append(
            Case(f"{case_id}.{live}", zed_attached, "zed", "seeded session (Chat; the launch's first new session)", steps, _B_EXPECTED[case_id],
                 [ledger, "the session's cost settlement"], _B_CLAIMS[case_id], bound,
                 f"cancellation not exercised within 30 s, or {DEFAULT_UNRUN}" if case_id == "B8" else DEFAULT_UNRUN)  # fmt: skip
        )
    b2_steps = (
        [f"After B3.1, open a second thread T2 from the content-bearing T1 (Zed applies its persisted Chat); set Context strategy to {B2_STRATEGY} on T2 "
         f"(B2's original Chat/Hybrid state); Prompt: {SMALL_SESSION_PROMPT}",
         "Then return to T1 through Zed's thread history (no new thread) for B4.2."]
        if b2_early else [f"Open a second session; Prompt: {SMALL_SESSION_PROMPT}"]
    )  # fmt: skip
    b2 = Case("B2", zed_attached, "zed", "attached session 2 (Chat; unseeded)", b2_steps, ["an attached answer with no maintenance"],
              ["no summary calls for the turn"], ["attached-small-session"],
              (1, 0, "the unseeded session's first turn: its history is its prompt alone, inside every allowance, so no maintenance runs"))  # fmt: skip
    if b2_early:
        cases.insert(next(n for n, case in enumerate(cases) if case.case == "B3.1") + 1, b2)
    else:
        cases.append(b2)
    for case in cases:
        case.after, case.requires, case.needs_route = _DEPENDENCIES[case.case]
    return cases


# --- The offline attached run --------------------------------------------------------------------------------


class _Gateway:
    """Answers every summary request with a summary of `summary_bytes` and records the full request input."""

    def __init__(self, summary_bytes: int) -> None:
        body = "\n".join(f"## {name}\nNone." for name in SECTIONS)
        pad = max(0, summary_bytes - len(body.encode("utf-8")) - 1)
        self.summary = body + ("\n" + "s" * pad if pad else "")
        self.inputs: list[int] = []

    def create_response(self, *, model, input_text, metadata=None, route_binding=None, **kwargs):
        self.inputs.append(len(input_text.encode("utf-8")))
        usage = GatewayUsage(
            gateway_request_id=f"gw-{len(self.inputs)}", provider="fake", provider_request_id=f"pr-{len(self.inputs)}", resolved_provider="Anthropic",
            resolved_model=HAIKU, model_version=None, billing_units=1, cost_usd=Decimal("0"), input_tokens=1, output_tokens=1, cached_tokens=0,
            reasoning_tokens=0, total_tokens=2,
        )  # fmt: skip
        return GatewayResponse(output_text=self.summary, gateway_usage=usage, raw={}, finish_reason="stop")


class _Planner:
    """Records each answer request's history view; answers Chat with a reply of `reply_bytes`."""

    def __init__(self, reply_bytes: int) -> None:
        self.reply = "r" * reply_bytes
        self.requests: list[Any] = []

    def run(self, request, **kwargs):
        self.requests.append(request)
        return AgentRunResult(
            execution_mode=ExecutionMode.CHAT, status=AgentRunStatus.COMPLETED, final_state="CHAT_ONLY", output_text=self.reply,
            total_cost_usd=Decimal("0"), run_id=request.run_id, session_id=request.session_id, tool_calls=(), mutation_count=0, provider_keys_resolvable=(),
        )  # fmt: skip


async def _attached_run(summary_bytes: int, reply_bytes: int, b2_early: bool = B2_AFTER_FIRST_TURN) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="stage-c-schedule-") as tmp:
        root = Path(tmp)
        ledger = stage_c.stage_c_ledger_path(root / ".optimus")
        envelope = stage_c.compose_stage_c_envelope(ledger=ledger)
        stage_c.initialize_stage_c_ledger(ledger, envelope, clock=lambda: T0)
        stage_c.StageCGuard.open(ledger, envelope, clock=lambda: T0).close()
        composition = compose_test_composition("attached", approved_literal=approval_literal(profiles.compose_test_profile_snapshot("attached")))
        gateway, planner = _Gateway(summary_bytes), _Planner(reply_bytes)
        paused, cancel_sent = threading.Event(), threading.Event()

        def sleep(_seconds: float) -> None:
            paused.set()  # the operator cancels at the first wake of the pause
            cancel_sent.wait(10)

        attachment, scenario = host.compose_stage_c_attachment(
            composition=composition, gateway_client=gateway, shared_secret="schedule", launch=host.StageCLaunch(envelope, ledger), clock=lambda: T0, sleep=sleep
        )
        outbound = RecordingOutboundChannel()
        adapter = AcpDuplexAdapter(
            runner=planner, workspace_root=root, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound, context_attachment=attachment, session_seeder=scenario.seed
        )  # fmt: skip

        async def rpc(method: str, params: dict[str, Any], rid: str) -> dict[str, Any]:
            return (await adapter.handle_client_request({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})).response

        async def chat_session() -> str:
            session_id = (await rpc("session/new", {"cwd": str(root), "mcpServers": []}, "new"))["result"]["sessionId"]
            await rpc("session/set_mode", {"sessionId": session_id, "modeId": "chat"}, "mode")
            return session_id

        seeded = await chat_session()
        cancel_turn = stage_c.STAGE_C_SCENARIOS[stage_c.STAGE_C_ATTACHED_SCENARIO]["schedule"]["cancel_pause_turn"]
        turns: list[dict[str, Any]] = []
        small_envelopes: list[int] = []
        small_after = 1 if b2_early else len(ATTACHED_TURNS)

        async def small_session() -> None:
            small = await chat_session()
            if b2_early:  # B2's original Chat/Hybrid state (Zed persisted Hybrid from T1 when B2 ran last)
                await rpc("session/set_config_option", {"sessionId": small, "configId": STRATEGY_CONFIG_ID, "value": B2_STRATEGY}, "small-strategy")
            before = len(planner.requests)
            await rpc("session/prompt", {"sessionId": small, "prompt": [{"type": "text", "text": SMALL_SESSION_PROMPT}]}, "small")
            small_envelopes.extend(len((r.conversation_envelope or "").encode("utf-8")) for r in planner.requests[before:])

        for live, case_id, strategy, text in ATTACHED_TURNS:
            if strategy is not None:
                await rpc("session/set_config_option", {"sessionId": seeded, "configId": STRATEGY_CONFIG_ID, "value": strategy}, f"s{live}")
            before_inputs, before_answers = len(gateway.inputs), len(planner.requests)
            task = asyncio.create_task(rpc("session/prompt", {"sessionId": seeded, "prompt": [{"type": "text", "text": text}]}, f"p{live}"))
            pause_started = False
            if live == cancel_turn:
                while not task.done() and not paused.is_set():
                    await asyncio.sleep(0.01)
                pause_started = paused.is_set()
                if pause_started:
                    await adapter.handle_client_notification({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": seeded}})
                cancel_sent.set()
            response = await task
            turns.append(
                {
                    "live": live,
                    "case": case_id,
                    "strategy": strategy,
                    "prompt": text,
                    "stop": response["result"]["stopReason"] if "result" in response else f"error {response['error']['code']}",
                    "pause_started": pause_started if live == cancel_turn else None,
                    "summary_inputs": gateway.inputs[before_inputs:],
                    "answer_envelopes": [len((r.conversation_envelope or "").encode("utf-8")) for r in planner.requests[before_answers:]],
                }
            )
            if live == small_after:
                await small_session()  # B2's unseeded session: never a live attached turn of the seeded one
        return {"reply_bytes": reply_bytes, "summary_bytes": summary_bytes, "turns": turns, "small_session_envelopes": small_envelopes,
                "small_session_after_turn": small_after, "events": list(scenario.events)}  # fmt: skip


# --- The schedule ---------------------------------------------------------------------------------------------


def _fixed_material() -> dict[str, int]:
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import measure_context_engine_limits as limits  # the reviewed measurement of each request's fixed material

    return limits.fixed_request_material()


def _tokens(utf8_bytes: int, profile: Any) -> int:
    return math.ceil(profile.tokens_per_byte * utf8_bytes) + profile.per_message_tokens + profile.fixed_tokens


def _sum(calls: list[Call], prices: tuple[Decimal, Decimal]) -> Decimal:
    return sum((call.reserve_usd(prices) for call in calls), Decimal(0))


@dataclass(frozen=True)
class RunbookPaths:
    """The operator's actual paths: the installed `optimus-agent` executable, the synthetic workspace (the Zed
    project and acpx `--cwd`) and the folder live evidence is saved under."""

    agent_exe: Path
    workspace: Path
    evidence: Path


# The shell every acpx command is run from, exactly as written: its quoting is part of the command's contract, and the
# launch rehearsal runs the commands through this shell and the pinned acpx (r5's A6 failed at that boundary).
ACPX_SHELL = {"name": "bash (Git for Windows)", "executable": r"C:\Program Files\Git\bin\bash.exe"}
_UNQUOTABLE = re.compile(r"""['"$`]""")


def _acpx_agent(paths: RunbookPaths) -> dict[str, Any]:
    """acpx's --agent value: the reviewed optimus-agent.exe and its qualification launch arguments, launched directly.

    acpx splits this value itself, treating a backslash as an escape except inside single quotes, and runs a .cmd
    agent through cmd; so there is no wrapper and every part is single-quoted. The value sits inside the declared
    shell's double quotes, so a path holding a quote, `$` or a backtick cannot be carried and is refused."""
    argv = [str(paths.agent_exe), "--workspace-root", str(paths.workspace), "--plan12-test-profile", "qualification", "--plan12-stage-c", "--debug-trace"]
    for part in argv:
        if _UNQUOTABLE.search(part):
            raise ValueError(f"a launch path that cannot be quoted for acpx: {part!r}")
    value = " ".join(f"'{part}'" for part in argv)
    return {"argv": argv, "value": value, "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest()}


def _runbook(paths: RunbookPaths, b2_early: bool = B2_AFTER_FIRST_TURN) -> dict[str, Any]:
    ws, ev, agent = paths.workspace, paths.evidence, _acpx_agent(paths)
    shortcut = ws.parent / "launch" / "zed-workspace.lnk"
    zed_start = (
        f"Claude starts Zed: recheck {ZED_CLIENT['exe']} (Zed {ZED_CLIENT['version']}, SHA-256 {ZED_CLIENT['sha256']}), the Zed settings and the "
        f'keymap; then run explorer.exe "{shortcut}" (a shortcut whose target is that Zed.exe and whose argument is the workspace), so Zed gets the '
        "user's ordinary environment; verify one Zed PID and its window, and no Optimus or acpx process or 8765 listener before the first thread. "
        "Codex drives Zed's UI; the operator never opens it."
    )
    acpx = f'acpx --format json --cwd "{ws}" --agent "{agent["value"]}"'
    steps: list[dict[str, Any]] = []
    checks: list[str] = []

    def step(kind: str, title: str, commands: list[str], evidence: list[str], note: str = "") -> None:
        steps.append({"kind": kind, "title": title, "commands": commands, "evidence": evidence, "note": note})

    runtime = ws / ".optimus"
    copied = ", ".join(str(runtime / name) for name in RUNTIME_FILES) + f" and {runtime / 'plan12-stage-c' / f'{stage_c.STAGE_C_RELEASE_ID}.jsonl'}"

    def capture(label: str) -> None:
        out = str(ev / "runtime" / f"{len(checks):02d}-{label}")
        step("capture", f"capture runtime logs {len(checks):02d}: {label}",
             [f"Copy {copied} into the new folder {out} (never overwrite an existing copy); record each file's SHA-256."], [out],
             "Taken after the launch ends and before its custody check, so no later launch mixes into it; the source logs are append-only. "
             "Each model request the launch dispatched must have its debug_trace.py:log_provider_attempts record in debug-acp.ndjson (a "
             "zero-dispatch refusal has none); a missing required record is an evidence failure, never a reason to rerun. Secret-scan the "
             "copies before sealing.")  # fmt: skip

    def check(label: str, *, after_launch: bool = False) -> None:
        if after_launch:
            capture(label)
        out = str(ev / "checks" / f"{len(checks):02d}-{label}.json")
        command = f'python tools/plan12_stage_c_transition_check.py --workspace-root "{ws}" --out {out}' + (f" --previous {checks[-1]}" if checks else "")
        step("custody-check", f"custody check {len(checks):02d}: {label}", [command], [out],
             "Must print 'custody clear' (exit 0) before the next step; otherwise stop: the remaining cases are UNRUN.")  # fmt: skip
        checks.append(out)

    def zed_args(profile: str) -> str:
        return json.dumps(
            {"command": str(paths.agent_exe), "args": ["--workspace-root", str(ws), "--plan12-test-profile", profile, "--plan12-stage-c", "--debug-trace"]}
        )

    receipt = ev / "rehearsal" / "receipt.json"
    step("rehearsal-gate", "launch rehearsal receipt (before asking for the operator's hour)",
         [f'python tools/plan12_stage_c_launch_rehearsal.py --verify "{receipt}" --schedule "{ws.parent / "stage-c-schedule.json"}"'], [str(receipt)],
         "Must print 'rehearsal receipt fresh' (exit 0): a passing real-client rehearsal of this schedule's acpx commands, made in release "
         "preparation with today's acpx, Node and shell; otherwise stop before the operator's hour is requested.")  # fmt: skip
    step("pre-launch-check", "stop the prior host",
         ["Claude checks that no earlier Optimus host, Zed, acpx process or 8765 listener is running (process names and PIDs only)."], [],
         "No acpx session or other client state from earlier runs is relied on.")  # fmt: skip
    step("approval", "L1 release approval (qualification)", [f'optimus-trust --workspace-root "{ws}" approve --mode durable --plan12-test-profile qualification --plan12-stage-c'],
         [str(ev / "L1" / "approve-console.txt")], "TTY 'y'. Creates the release ledger once; the window starts at the first Gateway open.")  # fmt: skip
    step("fixture-check", "workspace fixture check (before L1)", [f'python tools/plan12_stage_c_schedule.py --verify-workspace "{ws}"'],
         [str(ev / "checks" / "00-workspace-fixture.txt")],
         "Must print 'workspace fixture clear' (exit 0): the fixture files unchanged, notes/ and scratch/ present, no case target written "
         "yet and nothing else but the ceremony's .optimus; otherwise stop before any launch.")  # fmt: skip
    check("before-L1")
    step("zed-launch", "L1 Zed launch (qualification)", [f"Zed settings agent_servers Optimus: {zed_args('qualification')}", zed_start],
         [str(ev / "L1" / "zed-agent-server.json"), str(ev / "L1" / "zed-start.json")],
         "Open the workspace in Zed and start a new Optimus thread: the host starts its own Gateway; the 60-minute window starts.")  # fmt: skip
    step("operator", "cases A1-A5 in Zed", ["Run cases A1, A2, A3, A4 and A5 as listed."], [str(ev / case) for case in ("A1", "A2", "A3", "A4", "A5")])
    stopped_capture, stopped_check = ev / "runtime" / "01a-L1-route-stop", ev / "checks" / "01a-L1-route-stop.json"
    step("zed-restart", "qualification Zed restart (conditional, at most once)",
         [f"Only if A1 or A2 ends in a charged, fully settled reply-policy refusal (Gateway 422 with its usage kept; every charge known and settled; "
          "no halt; custody clear; window, budget and attempts still open), at most once: record that case FAILED with its evidence; quit Zed; copy "
          f"{copied} into the new folder {stopped_capture}; run python tools/plan12_stage_c_transition_check.py --workspace-root \"{ws}\" --out "
          f"{stopped_check} --previous {checks[-1]}; then Claude starts Zed again exactly as for L1, and Codex runs only the L1 cases not yet run (A2 "
          "if the stop came in A1, then A3, A4 and A5), never A1 or A2 again. Continue with 'end the L1 Zed launch'; its custody check then uses "
          f"--previous {stopped_check}."],
         [str(stopped_capture), str(stopped_check)],
         "Under the same r9 L1 durable approval (its digest must still validate; any mismatch is an absolute stop), the same ledger, totals, deadline "
         "and limits. Never after UPSTREAM_ATTEMPT_UNCERTAIN, a halt, an unknown charge or any absolute stop, and never for the attached launch: a new "
         "attached host reseeds its first session and restarts its live-turn count.")  # fmt: skip
    step("operator", "end the L1 Zed launch", ["Quit Zed (File > Quit): it stops the agent server; the host closes its Gateway."], [])
    check("after-L1-zed", after_launch=True)
    step("acpx-launch", "A6: one-shot denied Agent turn", [f'acpx --format json --deny-all --cwd "{ws}" --agent "{agent["value"]}" exec "{A6_PROMPT}"'], [str(ev / "A6" / "exec.ndjson")],
         "exec is one-shot: its own host and fresh session, closed when the command ends. Save stdout as the evidence.")  # fmt: skip
    check("after-A6", after_launch=True)
    step("acpx-launch", "A7: fresh named session", [f"{acpx} sessions new --name {A7_SESSION}"], [str(ev / "A7" / "sessions-new.json")],
         "Creates a fresh record (any earlier record of that name is soft-closed); acpx closes its host when the command ends.")  # fmt: skip
    check("after-A7-sessions-new", after_launch=True)
    step("acpx-launch", "A7: save Chat as the session's mode", [f"{acpx} set-mode chat -s {A7_SESSION}"], [str(ev / "A7" / "set-mode.json")],
         "Optimus advertises no session/load: acpx starts a host, a fresh runtime session, applies session/set_mode chat and saves it as the desired mode.")  # fmt: skip
    check("after-A7-set-mode", after_launch=True)
    step("acpx-launch", "A7: the Chat prompt", [f'{acpx} --ttl 0 prompt -s {A7_SESSION} "{A7_PROMPT}"'], [str(ev / "A7" / "prompt.ndjson")],
         "The prompt's own host starts a fresh runtime session; acpx replays the saved Chat mode on it before the prompt (a failed replay fails the "
         "command: A7 is UNRUN). --ttl 0 keeps its queue owner until the explicit close.")  # fmt: skip
    step("acpx-close", "A7: close the session", [f"{acpx} sessions close {A7_SESSION}"], [str(ev / "A7" / "sessions-close.json")],
         "Terminates the queue owner and its host; the host closes its Gateway.")  # fmt: skip
    check("after-A7-close", after_launch=True)
    step("zed-settings", "isolate the attached launch",
         ["With Zed not running, hide the qualification entry from Zed's agent_servers so only the attached entry is visible, and verify "
          "that entry against the L2 launch below."], [str(ev / "L2" / "zed-isolation.json")],
         "Zed restores the last thread's agent when it starts, so a visible qualification entry would relaunch the qualification profile "
         "before the attached one is selected (r7's offline walk). The hidden entry comes back only with the other temporary settings "
         "after the run.")  # fmt: skip
    step("approval", "L2 release approval (attached)", [f'optimus-trust --workspace-root "{ws}" approve --mode durable --plan12-test-profile attached --plan12-stage-c'],
         [str(ev / "L2" / "approve-console.txt")], "TTY 'y'. The ledger is kept as it is (never reset); the window does not restart.")  # fmt: skip
    check("before-L2")
    step("zed-launch", "L2 Zed launch (attached)", [f"Zed settings agent_servers Optimus: {zed_args('attached')}", zed_start],
         [str(ev / "L2" / "zed-agent-server.json"), str(ev / "L2" / "zed-start.json")], "Start Zed; the first new Optimus thread is the seeded session.")  # fmt: skip
    if b2_early:
        step("operator", "cases B3.1, B2, then B4.2-B8.7 in Zed",
             ["Run B3.1 in the seeded thread T1; then open T2 from T1, set Hybrid on T2 and run B2; return to T1 through Zed's thread history (no new "
              "thread) and run B4.2 to B8.7 in order."], [str(ev / "L2" / "cases")])  # fmt: skip
    else:
        step("operator", "cases B3-B8 then B2 in Zed", ["Run cases B3.1 to B8.7 in order in the seeded thread, then B2 in a second new thread."], [str(ev / "L2" / "cases")])
    step("operator", "end the L2 Zed launch", ["Quit Zed."], [])
    check("final", after_launch=True)
    return {
        "paths": {"agent_exe": str(paths.agent_exe), "workspace": str(ws), "evidence": str(ev)},
        "acpx_agent": agent,
        "acpx_shell": ACPX_SHELL,
        "zed_client": {**ZED_CLIENT, "shortcut": str(shortcut)},
        "acpx": {
            "version": "0.12.0",
            "inspection_sha256": {  # the installed client the launch rehearsal checks; recheck before live use
                "acpx": "805200badb253f80c442dad64453fbaf761848d32de691d8048fcba7607c321d",  # pragma: allowlist secret - public file digest
                "acpx.cmd": "212da5e557d5d621af89e5bf7f86dbe59e674ba69595c14038bbcdde39c37f79",  # pragma: allowlist secret - public file digest
                "dist/cli.js": "7da1d8b2fe0fc19696febddb3486729ce82b04b2a64a367e16df0691776483a4",  # pragma: allowlist secret - public file digest
                "dist/live-checkpoint-ClPCSdrW.js": "d92153086f058880623af7297a6867166068e27f9b2cc97a7b94c6a80e2b20da",  # pragma: allowlist secret - public file digest
            },
        },
        "steps": steps,
        "preconditions": [
            "Every launch (Zed, acpx, optimus-trust) runs with the same OPTIMUS_* environment the approvals captured; a difference refuses "
            "with SNAPSHOT_MISMATCH before any service starts.",
            "Recheck the installed acpx identity before live use; no install or upgrade.",
            f"Run every acpx command from the declared shell, {ACPX_SHELL['name']} ({ACPX_SHELL['executable']}), exactly as written.",
            f"Every launch path (acpx's --agent and both Zed entries) passes the existing --debug-trace option: the host traces into {runtime / 'debug-acp.ndjson'}.",
            "On any stop, capture the current launch's runtime logs and ledger at once (the capture step's list), before any other step.",
        ],
    }


def build_schedule(
    *, summary_bytes: int = 8_192, reply_sizes: tuple[int, ...] = REPLY_SIZES, paths: RunbookPaths, b2_early: bool = B2_AFTER_FIRST_TURN
) -> dict[str, Any]:
    snapshot = profiles.compose_test_profile_snapshot("attached")
    entry = snapshot.policy.models[HAIKU]
    profile = snapshot.policy.estimators[entry.route.estimator]
    prices = (entry.prices.input_usd_per_million, entry.prices.output_usd_per_million)
    answer_cap, summary_cap = snapshot.policy.output_reserve_tokens["implementer"], snapshot.policy.output_reserve_tokens["summarizer"]
    limits = host.stage_c_limits(snapshot, HAIKU)
    fixed = _fixed_material()

    # The bound: each call at the most its request can reserve.
    widest_summary = build_summary_prompt("x" * math.floor(limits.limits.maintenance_input_tokens / profile.tokens_per_byte))
    max_answer = Call("answer", limits.usable_input_tokens, answer_cap, "the route's usable input: the Gateway refuses more before any attempt")
    max_summary = Call("summary", limits.estimate_request(widest_summary), summary_cap, "the maintenance input limit inside the summary prompt")
    answer_usd = max_answer.reserve_usd(prices).quantize(CENT, ROUND_CEILING)  # rounded up: still a bound
    summary_usd = max_summary.reserve_usd(prices).quantize(CENT, ROUND_CEILING)
    cases = _cases(b2_early)
    rows, bound_total, bound_calls = [], Decimal(0), 0
    for case in cases:
        answers, summaries, basis = case.bound
        total = answers * answer_usd + summaries * summary_usd
        bound_total += total
        bound_calls += answers + summaries
        rows.append(
            {
                "case": case.case, "launch": case.launch, "client": case.client, "session": case.session, "steps": case.steps, "expected": case.expected,
                "artifacts": case.artifacts, "claims": case.claims, "unrun_if": case.unrun_if,
                "after": list(case.after), "requires": case.requires, "needs_route": case.needs_route,
                "bound": {"answer_calls": answers, "summary_calls": summaries, "basis": basis, "billed_attempt_bound_usd": str(total.quantize(CENT, ROUND_CEILING)),
                          "physical_attempts_max": (answers + summaries) * MAX_ROUTE_ATTEMPTS, "cumulative_usd": str(bound_total.quantize(CENT, ROUND_CEILING))},
            }
        )  # fmt: skip
    limit_usd, limit_attempts = stage_c.STAGE_C_LIMIT_USD, stage_c.STAGE_C_MAX_ATTEMPTS
    bound = {
        "assumptions": [
            f"The approved launch environment keeps OPTIMUS_MAX_PLANNING_TURNS at its default {DEFAULT_MAX_PLANNING_TURNS} (bound by the launch approval).",
            f"Every answer or planning request is at most the route's usable input ({limits.usable_input_tokens} tokens; more is refused by the Gateway "
            f"before any attempt) with its full {answer_cap}-token output cap.",
            f"Every summary request is at most the engine's maintenance input limit ({limits.limits.maintenance_input_tokens} tokens) inside the summary "
            f"prompt ({max_summary.input_tokens} request tokens) with its full {summary_cap}-token cap.",
            f"An attached turn makes at most {host.MAX_MAINTENANCE_CALLS} maintenance calls (its view and repack share the allowance; a larger plan "
            "is refused before any call) and one answer; a sliding view makes no maintenance call.",
            "The scheduled unavailable turns make no call; the cancellation turn makes its calls before the pause and nothing after it (cancelled "
            "or UNRUN), or answers once if it never reaches the paused call.",
            "A3 and A4 are refused before any attempt; A5 sends no prompt; B2's first turn holds only its prompt, so no maintenance runs.",
            "Dollars count one potentially billed attempt per call (a resend follows only a proven unbilled attempt); physical attempts count two.",
            f"Prices are the registry's conservative ${prices[0]}/${prices[1]} per million tokens; the estimator is "
            f"{profile.tokens_per_byte} token per UTF-8 byte plus framing.",
            "Each prompt is the one listed: a different or longer prompt is outside this bound.",
            "The one eligible qualification restart adds no case and no request: it runs only cases not yet run, and no case runs twice.",
            "A BLOCKED case sends no prompt, and an UNRUN case sends none.",
            f"B2 runs {'right after B3.1' if b2_early else 'last'}: its unseeded session is never a live attached turn of the seeded session, so its "
            "place changes no allocation.",
        ],
        "per_call": {"answer": max_answer.row(prices), "summary": max_summary.row(prices)},
        "totals": {
            "calls": bound_calls,
            "billed_attempt_bound_usd": str(bound_total.quantize(CENT, ROUND_CEILING)),
            "physical_attempts_planned_max": [bound_calls, bound_calls * MAX_ROUTE_ATTEMPTS],
            "fits_usd": bound_total <= limit_usd,
            "fits_attempts_planned": bound_calls <= limit_attempts,
            "fits_attempts_max": bound_calls * MAX_ROUTE_ATTEMPTS <= limit_attempts,
            "usd_shortfall": str(max(Decimal(0), bound_total.quantize(CENT, ROUND_CEILING) - limit_usd)),
        },
    }

    def answer(prompt: str, envelope_bytes: int, kind: str = "chat", note: str = "") -> Call:
        material = fixed["planning"] if kind == "planning" else fixed["chat"]
        return Call(kind, _tokens(material + len(prompt.encode("utf-8")) + envelope_bytes, profile), answer_cap, note)

    paths_measured = []
    for reply_bytes in reply_sizes:
        run = asyncio.run(_attached_run(summary_bytes, reply_bytes, b2_early))
        a1 = ConversationTurn(A1_PROMPT, "", "r" * reply_bytes, ConversationOutcome.COMPLETED, EffectState.NONE)
        a1_history = len(render_conversation_envelope({1: a1}).encode("utf-8"))
        planning_note = "planning turn {n} of at most %d (later planning turns' own outputs are not simulated)" % DEFAULT_MAX_PLANNING_TURNS
        calls_by_case: dict[str, list[Call]] = {
            "A1": [answer(A1_PROMPT, 0)],
            "A2": [answer(A2_PROMPT, a1_history, "planning", planning_note.format(n=n)) for n in range(1, DEFAULT_MAX_PLANNING_TURNS + 1)],
            "A3": [], "A4": [], "A5": [],
            "A6": [answer(A6_PROMPT, 0, "planning", planning_note.format(n=n)) for n in range(1, DEFAULT_MAX_PLANNING_TURNS + 1)],
            "A7": [answer(A7_PROMPT, 0)],
        }  # fmt: skip
        for turn in run["turns"]:
            live = turn["live"]
            calls = [Call("summary", _tokens(size, profile), summary_cap, f"maintenance call {n} of live turn {live}") for n, size in enumerate(turn["summary_inputs"], 1)]
            calls += [answer(turn["prompt"], size, "chat", f"answer of live turn {live}") for size in turn["answer_envelopes"]]
            calls_by_case[f"{turn['case']}.{live}"] = calls
        calls_by_case["B2"] = [answer(SMALL_SESSION_PROMPT, size) for size in run["small_session_envelopes"]]
        every = [call for calls in calls_by_case.values() for call in calls]
        allocation = _sum(every, prices)
        paths_measured.append(
            {
                "reply_bytes": reply_bytes,
                "summary_bytes": summary_bytes,
                "turns": run["turns"],
                "small_session_envelopes": run["small_session_envelopes"],
                "small_session_after_turn": run["small_session_after_turn"],
                "events": run["events"],
                "calls_by_case": {case: [call.row(prices) for call in calls] for case, calls in calls_by_case.items()},
                "totals": {
                    "calls": len(every),
                    "billed_attempt_allocation_usd": str(allocation.quantize(CENT, ROUND_CEILING)),
                    "physical_attempts_planned_max": [len(every), len(every) * MAX_ROUTE_ATTEMPTS],
                },
            }
        )

    claims = sorted({claim for case in cases for claim in case.claims})
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True, check=False).stdout.strip())
    return {
        "schedule": SCHEDULE_VERSION,
        "source": {"head": head, "dirty": dirty, "attached_hash": snapshot.effective_hash, "qualification_hash": profiles.TEST_PROFILES["qualification"].effective_hash,
                   "scenario_catalogue": stage_c.scenario_catalogue_digest(), "seed": stage_c.STAGE_C_SCENARIOS[stage_c.STAGE_C_ATTACHED_SCENARIO]["seed"]},  # fmt: skip
        "envelope": {
            "release": stage_c.STAGE_C_RELEASE_ID,
            "usd": str(limit_usd),
            "physical_attempts": limit_attempts,
            "window_minutes": stage_c.STAGE_C_WINDOW_SECONDS // 60,
        },
        "fixed_request_material_bytes": fixed,
        "prompt_files": {name: {"bytes": len(text.encode("utf-8")), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()} for name, text in PROMPT_FILES.items()},
        "workspace_files": {name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in WORKSPACE_FILES.items()},
        "workspace_dirs": list(WORKSPACE_DIRS),
        "workspace_targets": list(WORKSPACE_TARGETS),
        "cases": rows,
        "claims": {claim: [case.case for case in cases if claim in case.claims] for claim in claims},
        "bound": bound,
        "measured": {
            "basis": (
                "Each path is the allocation of one fixed-fake run (fake replies of the stated size, summaries of the stated size), priced like the "
                "bound per call. It shows how replies move later packing, checkpoint reuse and maintenance; it is not a bound and not a prediction."
            ),
            "paths": paths_measured,
        },
        "expected_spend": {
            "basis": (
                "Informational only, never a ceiling. The accepted v6 paid run's two summary calls (sealed evidence stage-b-qualification-v6, "
                "manifest b2cbf077) used 881 and 1,596 input tokens and 1,462 and 1,776 output tokens against the 8,192 cap, costing $0.0008191 "
                "and $0.0010476. The seed's real tokenization is unmeasured offline; the estimator bounds it at one token per byte. No Agent or "
                "Chat expectation is derived from summary observations."
            )
        },
        "runbook": _runbook(paths, b2_early),
        "stop_rules": [
            "Absolute stops: a Gateway guard refusal (budget, attempts or window); a ledger halt, write divergence or overrun; an unknown, outstanding or "
            "unresolved charge (an uncertain attempt included); an accounting-integrity failure; a custody check that is not clear; a security, approval, "
            "source or fixture mismatch; unauthorized or uncertain effects; uncertain permission provenance or isolation. Each stops all dispatch at once: "
            "every later case is UNRUN and no restart clears it. Capture, check custody, restore and seal.",
            "Any other case failure (a behaviour or evidence failure): capture at once and record the case FAILED with its evidence. It is never retried, "
            "given a substitute prompt or repaired, and its criterion is never removed.",
            "Continue only with cases whose predecessors (after) ran and whose state preconditions (requires) are proved from evidence: a submitted prompt "
            "proves nothing by itself. A case whose precondition is missing is BLOCKED with the named cause and its prompt is never sent, not even to "
            "advance a count.",
            "On the experimental route a refused or unverifiable reply stops every later call on that launch's Gateway: every later case on that launch "
            "that needs the route is BLOCKED (route stopped). The attached launch is never relaunched: a new attached host reseeds its first session and "
            "restarts its live-turn count, so earlier state cannot resume.",
            "At most one qualification Zed restart, only after a charged, fully settled reply-policy refusal (422 with its usage kept, every charge known "
            "and settled, no halt), with custody clear and the window, budget and attempts still open. It runs only the qualification Zed cases not yet "
            "run, under the same r9 L1 durable approval, ledger, totals, deadline and limits (runbook step 'qualification Zed restart').",
            "Any required case FAILED, BLOCKED or UNRUN means the run is not full Stage C acceptance; budget or window exhaustion is never acceptance. No "
            "case is removed and no limit is lowered to fit.",
        ],
    }


def _markdown(schedule: Mapping[str, Any]) -> str:
    bound, totals = schedule["bound"], schedule["bound"]["totals"]
    lines = [
        f"# Stage C executable schedule ({schedule['schedule']})",
        "",
        f"Source {schedule['source']['head'][:12]}{' (dirty)' if schedule['source']['dirty'] else ''}; envelope {schedule['envelope']['release']}: ${schedule['envelope']['usd']} / "
        f"{schedule['envelope']['physical_attempts']} attempts / {schedule['envelope']['window_minutes']} minutes.",
        "",
        "## Conservative complete-case bound",
        "",
        "| Case | Launch | Calls (answer + summary) | Bound | Cumulative | Attempts max | Basis | Claims |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in schedule["cases"]:
        b = row["bound"]
        lines.append(
            f"| {row['case']} | {row['launch']} | {b['answer_calls']} + {b['summary_calls']} | ${b['billed_attempt_bound_usd']} | ${b['cumulative_usd']} | "
            f"{b['physical_attempts_max']} | {b['basis']} | {', '.join(row['claims'])} |"
        )
    lines += [
        "",
        f"**Bound:** {totals['calls']} calls; ${totals['billed_attempt_bound_usd']} (one billed attempt per call); attempts {totals['physical_attempts_planned_max'][0]}-"
        f"{totals['physical_attempts_planned_max'][1]}. Fits ${schedule['envelope']['usd']}: {totals['fits_usd']} (shortfall ${totals['usd_shortfall']}); fits "
        f"{schedule['envelope']['physical_attempts']} attempts planned: {totals['fits_attempts_planned']}, at maximum: {totals['fits_attempts_max']}.",
        "",
        "Assumptions:",
        "",
    ]
    lines += [f"- {text}" for text in bound["assumptions"]]
    lines += ["", "## Measured fixed-fake allocations (not a bound)", "", schedule["measured"]["basis"], "", "| Reply bytes | Calls | Allocation | Attempts |", "|---:|---:|---:|---|"]
    for path in schedule["measured"]["paths"]:
        t = path["totals"]
        lines.append(f"| {path['reply_bytes']} | {t['calls']} | ${t['billed_attempt_allocation_usd']} | {t['physical_attempts_planned_max'][0]}-{t['physical_attempts_planned_max'][1]} |")
    lines += ["", "## Expected spend (informational)", "", schedule["expected_spend"]["basis"], "", "## Runbook", ""]
    for n, step in enumerate(schedule["runbook"]["steps"], 1):
        lines.append(f"{n}. **{step['title']}** ({step['kind']}): " + " / ".join(f"`{command}`" for command in step["commands"]))
        if step["note"]:
            lines.append(f"   {step['note']}")
        if step["evidence"]:
            lines.append("   Evidence: " + ", ".join(step["evidence"]))
    lines += ["", "## Dependencies (schedule v10)", "", "| Case | After | Needs route | Requires |", "|---|---|---|---|"]
    for row in schedule["cases"]:
        lines.append(f"| {row['case']} | {', '.join(row['after']) or '-'} | {'yes' if row['needs_route'] else 'no'} | {'; '.join(row['requires'])} |")
    lines += ["", "## Stop rules", ""] + [f"- {rule}" for rule in schedule["stop_rules"]]
    return "\n".join(lines) + "\n"


def verify_workspace(workspace: Path) -> list[str]:
    """The workspace before the first launch: the fixture files unchanged, the prepared folders present, no case
    target written yet and nothing else (the release ceremony's .optimus folder aside). Returns the problems."""
    if not workspace.is_dir():
        return [f"{workspace} is not a directory"]
    problems = [f"{name} differs from the fixture" for name, text in WORKSPACE_FILES.items()
                if not (workspace / name).is_file() or (workspace / name).read_bytes() != text.encode("utf-8")]  # fmt: skip
    problems += [f"{name}/ is missing" for name in WORKSPACE_DIRS if not (workspace / name).is_dir()]
    problems += [f"{target} already exists" for target in WORKSPACE_TARGETS if (workspace / target).exists()]
    expected = {*WORKSPACE_FILES, *WORKSPACE_DIRS, *WORKSPACE_TARGETS, ".optimus"}
    entries = sorted(path.relative_to(workspace).as_posix() for path in workspace.rglob("*"))
    problems += [f"unexpected workspace entry: {entry}" for entry in entries if entry not in expected and not entry.startswith(".optimus/")]
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="a new folder for the schedule, its prompt files and the workspace")
    parser.add_argument("--verify-workspace", type=Path, help="check a generated workspace before the first launch and exit (0 only when it is the fixture)")
    parser.add_argument("--summary-bytes", type=int, default=8_192, help="the summary size each fake summary call returns (8192 is the bound)")
    parser.add_argument("--reply-bytes", type=int, nargs="+", default=list(REPLY_SIZES), help="fake reply sizes, one measured path each")
    parser.add_argument("--agent-exe", type=Path, default=REPO_ROOT / ".venv" / "Scripts" / "optimus-agent.exe", help="the installed optimus-agent executable")
    parser.add_argument("--evidence", type=Path, default=None, help="where live evidence is saved (default: <out>/live-evidence)")
    args = parser.parse_args(argv)
    if args.verify_workspace is not None:
        problems = verify_workspace(args.verify_workspace)
        print("\n".join(problems) if problems else "workspace fixture clear")
        return 1 if problems else 0
    if args.out is None:
        parser.error("--out is required unless --verify-workspace is given")
    if args.out.exists():
        parser.error(f"{args.out} exists; every schedule gets a new folder")
    out = args.out.resolve()
    paths = RunbookPaths(agent_exe=args.agent_exe.resolve(), workspace=out / "workspace", evidence=(args.evidence or out / "live-evidence").resolve())
    schedule = build_schedule(summary_bytes=args.summary_bytes, reply_sizes=tuple(args.reply_bytes), paths=paths)
    args.out.mkdir(parents=True)
    for name in WORKSPACE_DIRS:
        (args.out / "workspace" / name).mkdir(parents=True)
    for name, text in {**PROMPT_FILES, **{f"workspace/{k}": v for k, v in WORKSPACE_FILES.items()}}.items():
        target = args.out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    (args.out / "stage-c-schedule.json").write_text(json.dumps(schedule, indent=2, default=str) + "\n", encoding="utf-8", newline="\n")
    (args.out / "stage-c-schedule.md").write_text(_markdown(schedule), encoding="utf-8", newline="\n")
    print(json.dumps({"bound": schedule["bound"]["totals"], "measured": [p["totals"] | {"reply_bytes": p["reply_bytes"]} for p in schedule["measured"]["paths"]]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
