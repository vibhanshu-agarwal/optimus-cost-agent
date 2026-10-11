"""Plan 12.2 Task 13 (Stage C): the executable claim-to-case schedule, computed offline (Codex scope
agreement, 2026-10-11, section 5).

Nothing here calls a model, starts a service or touches the operator's ledger. The attached cases are run
through the real ACP adapter, the real Context Engine and the real attached Stage C composition (seed,
limits, scenario controls), with a fake Gateway that answers summary requests with a summary of a stated
size and a recording planner; so each maintenance call's actual input and each answer's actual history view
come from the real packing of the pinned seed. The absent-engine cases use the planner and Chat request
material at its existing maximums.

Every model call is priced at its full reservation: its input bound under the profile's estimator (one token
per UTF-8 byte plus framing) and its full output cap, at the registry's conservative prices. Under the
enforced resend contract at most one attempt per call can be billed, so the dollar ceiling counts one
billed attempt per call, while the attempt ceiling counts both possible physical attempts. No expected
Agent or Chat spend is derived from the summary-only observations. The schedule is a ceiling, not a
prediction or a promise that every case finishes: a guard stop, an expired window or a failed case leaves
the remaining cases UNRUN.

Usage: python tools/plan12_stage_c_schedule.py --out <dir> [--summary-bytes N]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
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

from context_engine.summary import SECTIONS
from optimus.acp import stage_c as host
from optimus.acp.session_config import STRATEGY_CONFIG_ID
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
SCHEDULE_VERSION = "stage-c-schedule-v1"
DEFAULT_UNRUN = "the guard refuses a call, the window ends or an earlier required case failed"


# --- Prompts, files and the exact schedule ------------------------------------------------------------------


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


@dataclass
class Call:
    kind: str  # "planning", "chat", "summary"
    input_tokens: int
    output_cap: int
    note: str = ""

    def reserve_usd(self, prices: tuple[Decimal, Decimal]) -> Decimal:
        return stage_c.reservation_usd(input_tokens=self.input_tokens, output_tokens=self.output_cap, input_usd_per_million=prices[0], output_usd_per_million=prices[1])


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
    calls: list[Call] = field(default_factory=list)
    unrun_if: str = ""

    def __post_init__(self) -> None:
        self.unrun_if = self.unrun_if or DEFAULT_UNRUN


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
    """Records each answer request's task and history view; answers Chat."""

    def __init__(self) -> None:
        self.requests: list[Any] = []

    def run(self, request, **kwargs):
        self.requests.append(request)
        return AgentRunResult(
            execution_mode=ExecutionMode.CHAT, status=AgentRunStatus.COMPLETED, final_state="CHAT_ONLY", output_text="ok.",
            total_cost_usd=Decimal("0"), run_id=request.run_id, session_id=request.session_id, tool_calls=(), mutation_count=0, provider_keys_resolvable=(),
        )  # fmt: skip


async def _attached_run(summary_bytes: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="stage-c-schedule-") as tmp:
        root = Path(tmp)
        ledger = stage_c.stage_c_ledger_path(root / ".optimus")
        envelope = stage_c.compose_stage_c_envelope(ledger=ledger)
        stage_c.initialize_stage_c_ledger(ledger, envelope, clock=lambda: T0)
        stage_c.StageCGuard.open(ledger, envelope, clock=lambda: T0).close()
        composition = compose_test_composition("attached", approved_literal=approval_literal(profiles.compose_test_profile_snapshot("attached")))
        gateway, planner = _Gateway(summary_bytes), _Planner()
        paused, cancel_sent = threading.Event(), threading.Event()

        def sleep(_seconds: float) -> None:
            paused.set()  # the operator cancels at the first poll of the pause
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
        turns = []
        for live, case_id, strategy, text in ATTACHED_TURNS:
            if strategy is not None:
                await rpc("session/set_config_option", {"sessionId": seeded, "configId": STRATEGY_CONFIG_ID, "value": strategy}, f"s{live}")
            before_inputs, before_answers = len(gateway.inputs), len(planner.requests)
            task = asyncio.create_task(rpc("session/prompt", {"sessionId": seeded, "prompt": [{"type": "text", "text": text}]}, f"p{live}"))
            if live == ATTACHED_TURNS[-1][0]:
                assert await asyncio.to_thread(paused.wait, 30), "the cancellation pause never started"
                await adapter.handle_client_notification({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": seeded}})
                cancel_sent.set()
            response = await task
            answers = planner.requests[before_answers:]
            turns.append(
                {
                    "live": live,
                    "case": case_id,
                    "strategy": strategy,
                    "prompt": text,
                    "stop": response["result"]["stopReason"],
                    "summary_inputs": gateway.inputs[before_inputs:],
                    "answer_envelopes": [len((r.conversation_envelope or "").encode("utf-8")) for r in answers],
                }
            )
        small = await chat_session()
        before_answers = len(planner.requests)
        await rpc("session/prompt", {"sessionId": small, "prompt": [{"type": "text", "text": SMALL_SESSION_PROMPT}]}, "small")
        small_envelopes = [len((r.conversation_envelope or "").encode("utf-8")) for r in planner.requests[before_answers:]]
        return {"turns": turns, "small_session_envelopes": small_envelopes, "events": list(scenario.events), "summary_bytes": summary_bytes}


# --- The schedule ---------------------------------------------------------------------------------------------


def _fixed_material() -> dict[str, int]:
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import measure_context_engine_limits as limits  # the reviewed measurement of each request's fixed material

    return limits.fixed_request_material()


def _tokens(utf8_bytes: int, profile: Any) -> int:
    return math.ceil(profile.tokens_per_byte * utf8_bytes) + profile.per_message_tokens + profile.fixed_tokens


def build_schedule(summary_bytes: int) -> dict[str, Any]:
    snapshot = profiles.compose_test_profile_snapshot("attached")
    entry = snapshot.policy.models[HAIKU]
    profile = snapshot.policy.estimators[entry.route.estimator]
    prices = (entry.prices.input_usd_per_million, entry.prices.output_usd_per_million)
    answer_cap, summary_cap = snapshot.policy.output_reserve_tokens["implementer"], snapshot.policy.output_reserve_tokens["summarizer"]
    fixed = _fixed_material()
    run = asyncio.run(_attached_run(summary_bytes))

    def answer(prompt: str, envelope_bytes: int, kind: str = "chat", note: str = "") -> Call:
        material = fixed["planning"] if kind == "planning" else fixed["chat"]
        return Call(kind, _tokens(material + len(prompt.encode("utf-8")) + envelope_bytes, profile), answer_cap, note)

    zed_absent, zed_attached = "L1 qualification launch (Zed)", "L2 attached launch (Zed)"
    acpx_absent = "L1 qualification launch (acpx)"
    cases = [
        Case("A1", zed_absent, "zed", "absent session 1 (Chat)", ["Switch the session to Chat.", "Prompt: Create a file named notes/chat-should-not-write.md containing the word hello."],
             ["a Chat answer; no permission request"], ["the workspace has no notes/chat-should-not-write.md"], ["chat-non-mutation"],
             [answer("Create a file named notes/chat-should-not-write.md containing the word hello.", 0)]),
        Case("A2", zed_absent, "zed", "absent session 1 (Agent)", ["Switch the session to Agent.", "Prompt: Create scratch/stage-c-agent.txt containing the single word ready.", "Approve the exact artifact in the permission request."],
             ["a session/request_permission naming exactly scratch/stage-c-agent.txt", "the turn completes after approval"], ["scratch/stage-c-agent.txt contains ready"],
             ["agent-exact-artifact-approval"], [answer("Create scratch/stage-c-agent.txt containing the single word ready.", 2_048, "planning", f"planning turn {n} of at most 3") for n in (1, 2, 3)]),
        Case("A3", zed_absent, "zed", "absent session 2 (Chat)", ["Paste the whole of capacity-prompt.txt as one prompt."],
             ["the 80% storage warning notice", "the readable request-capacity refusal (INPUT_EXCEEDS_CAPACITY text)", "the request meter, separate from the storage notice"],
             ["zero upstream attempts for the turn in the Gateway ledger"], ["request-capacity-refusal", "meter-versus-storage-notices"]),
        Case("A4", zed_absent, "zed", "absent session 3 (Chat)", ["Paste the whole of storage-prompt.txt as one prompt."],
             ["the storage refusal (not the request-capacity refusal)"], ["zero upstream attempts"], ["storage-refusal"]),
        Case("A5", zed_absent, "zed", "absent session 4", ["Change the mode, then open the mode and model options again.", "Open a new session and read its persisted default mode."],
             ["every option is still offered after the switch", "the new session shows the persisted default"], ["screenshots of both pickers"], ["absent-picker-and-persisted-default"]),
        Case("A6", acpx_absent, "acpx", "acpx session (Agent, denied)", ["acpx --format json --deny-all --cwd <workspace> --agent run-optimus-agent.cmd exec \"Create scratch/acpx-denied.txt containing denied.\""],
             ["a permission request answered deny", "no file written"], ["acpx JSON transcript", "scratch/acpx-denied.txt absent", "the run reports no resolvable provider key"],
             ["agent-exact-artifact-approval", "key-isolation"], [answer("Create scratch/acpx-denied.txt containing denied.", 0, "planning", f"planning turn {n} of at most 3") for n in (1, 2, 3)]),
        Case("A7", acpx_absent, "acpx", "acpx session (Chat)", ["acpx --cwd <workspace> --agent run-optimus-agent.cmd set-mode chat", "acpx --format json --cwd <workspace> --agent run-optimus-agent.cmd prompt \"Write scratch/acpx-chat.txt containing hello.\""],
             ["a Chat answer; no permission request"], ["acpx JSON transcript", "scratch/acpx-chat.txt absent"], ["chat-non-mutation"],
             [answer("Write scratch/acpx-chat.txt containing hello.", 0)]),
    ]
    for turn in run["turns"]:
        live = turn["live"]
        calls = [Call("summary", _tokens(size, profile), summary_cap, f"maintenance call {n} of live turn {live}") for n, size in enumerate(turn["summary_inputs"], 1)]
        calls += [answer(turn["prompt"], size, "chat", f"answer of live turn {live}") for size in turn["answer_envelopes"]]
        expected = {
            "B3": ["the attached picker shows Mode and Context strategy", "a compaction view of the 576 KiB seeded history"],
            "B4": ["the next turn reuses the checkpoint"],
            "B5": ["the sliding-window warning on the first admitted sliding turn"],
            "B6": [host.UNAVAILABLE_NOTICE, "the readable unavailable refusal: above the 512 KiB floor no full-history fallback"],
            "B7": ["a healthy compaction turn"],
            "B8": ["the pause notice after the first summary call", "the turn ends cancelled after the operator presses Cancel", "no second summary call; the first charge kept"],
        }[turn["case"]]
        steps = ([f"Set Context strategy to {turn['strategy']}."] if turn["strategy"] else []) + [f"Prompt: {turn['prompt']}"]
        if turn["case"] == "B8":
            steps.append("When the pause notice appears, press Cancel within 30 seconds.")
        cases.append(
            Case(f"{turn['case']}.{live}", zed_attached, "zed", "seeded session (Chat; the launch's first new session)", steps, expected,
                 ["the Gateway ledger's reserve/settle records for the turn", "the session's cost settlement"],
                 {"B3": ["attached-history-over-512kib", "attached-picker", "meter-versus-storage-notices"], "B4": ["checkpoint-reuse"], "B5": ["sliding-warning"],
                  "B6": ["repeated-engine-unavailability"], "B7": ["healthy-recovery"], "B8": ["cancellation-between-maintenance-calls"]}[turn["case"]],
                 calls, f"cancellation not exercised within 30 s, or {DEFAULT_UNRUN}" if turn["case"] == "B8" else DEFAULT_UNRUN)  # fmt: skip
        )
    cases.append(
        Case("B2", zed_attached, "zed", "attached session 2 (Chat; unseeded)", [f"Open a second session; Prompt: {SMALL_SESSION_PROMPT}"], ["an attached answer with no maintenance"],
             ["no summary calls for the turn"], ["attached-small-session"], [answer(SMALL_SESSION_PROMPT, size) for size in run["small_session_envelopes"]])
    )
    rows, total_reserve, total_calls = [], Decimal(0), 0
    for case in cases:
        reserve = sum((call.reserve_usd(prices) for call in case.calls), Decimal(0))
        total_reserve += reserve
        total_calls += len(case.calls)
        rows.append(
            {
                "case": case.case, "launch": case.launch, "client": case.client, "session": case.session, "steps": case.steps, "expected": case.expected,
                "artifacts": case.artifacts, "claims": case.claims, "unrun_if": case.unrun_if,
                "calls": [{"kind": c.kind, "input_tokens": c.input_tokens, "output_cap": c.output_cap, "reserve_usd": str(c.reserve_usd(prices).quantize(Decimal("0.000001"), ROUND_CEILING)), "note": c.note} for c in case.calls],
                "billed_attempt_ceiling_usd": str(reserve.quantize(Decimal("0.000001"), ROUND_CEILING)),
                "physical_attempts_planned_max": [len(case.calls), len(case.calls) * MAX_ROUTE_ATTEMPTS],
                "cumulative_ceiling_usd": str(total_reserve.quantize(Decimal("0.000001"), ROUND_CEILING)),
            }
        )  # fmt: skip
    claims = sorted({claim for case in cases for claim in case.claims})
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True, check=False).stdout.strip())
    limit_usd, limit_attempts = stage_c.STAGE_C_LIMIT_USD, stage_c.STAGE_C_MAX_ATTEMPTS
    return {
        "schedule": SCHEDULE_VERSION,
        "source": {"head": head, "dirty": dirty, "attached_hash": snapshot.effective_hash, "scenario_catalogue": stage_c.scenario_catalogue_digest(),
                   "seed": stage_c.STAGE_C_SCENARIOS[stage_c.STAGE_C_ATTACHED_SCENARIO]["seed"], "summary_bytes_assumed": summary_bytes},
        "envelope": {"usd": str(limit_usd), "physical_attempts": limit_attempts, "window_minutes": stage_c.STAGE_C_WINDOW_SECONDS // 60},
        "basis": ("each call at its input bound (one token per UTF-8 byte plus 272 framing tokens) and full output cap at $0.50/$2.50 per million; one potentially "
                  "billed attempt per call for dollars, two physical attempts per call for the attempt count; no expected Agent/Chat spend is derived"),
        "fixed_request_material_bytes": fixed,
        "prompt_files": {name: {"bytes": len(text.encode("utf-8")), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()} for name, text in PROMPT_FILES.items()},
        "workspace_files": {name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in WORKSPACE_FILES.items()},
        "attached_run": run,
        "cases": rows,
        "claims": {claim: [case.case for case in cases if claim in case.claims] for claim in claims},
        "totals": {
            "calls": total_calls,
            "billed_attempt_ceiling_usd": str(total_reserve.quantize(Decimal("0.000001"), ROUND_CEILING)),
            "physical_attempts_planned_max": [total_calls, total_calls * MAX_ROUTE_ATTEMPTS],
            "fits_usd": total_reserve <= limit_usd,
            "fits_attempts_planned": total_calls <= limit_attempts,
            "fits_attempts_max": total_calls * MAX_ROUTE_ATTEMPTS <= limit_attempts,
            "usd_shortfall": str(max(Decimal(0), total_reserve - limit_usd).quantize(Decimal("0.000001"), ROUND_CEILING)),
        },
        "stop_rules": [
            "The Gateway guard refuses any attempt once known charges plus its full reservation would exceed $0.50, at the 25th physical attempt, or when it could not time out inside the window; the refused case and every later one are UNRUN.",
            "An unknown charge, an overrun, a write failure or a restart with an unresolved attempt stops every later dispatch: the remaining cases are UNRUN.",
            "On the experimental route a failed or unverifiable reply stops every later call until the Gateway restarts; a relaunch needs a fresh bound approval and keeps the same ledger, totals and deadline.",
            "No failed case is retried, no case is removed and no limit is lowered to fit; budget or window exhaustion is never Task 13 acceptance.",
        ],
        "launch_order": [
            "optimus-trust approve --mode durable --plan12-test-profile qualification --plan12-stage-c (TTY 'y'; creates the ledger once)",
            "Zed agent_servers command: optimus-agent --workspace-root <workspace> --plan12-test-profile qualification --plan12-stage-c (the window starts at this first Gateway open); cases A1-A5",
            "acpx with run-optimus-agent.cmd running the same qualification Stage C command; cases A6-A7",
            "optimus-trust approve --mode durable --plan12-test-profile attached --plan12-stage-c (TTY 'y'; the ledger is kept)",
            "Zed relaunch with --plan12-test-profile attached --plan12-stage-c; the first new session is the seeded one: cases B3-B8 in order, then B2",
        ],
    }


def _markdown(schedule: Mapping[str, Any]) -> str:
    totals = schedule["totals"]
    lines = [
        f"# Stage C executable schedule ({schedule['schedule']})",
        "",
        f"Source {schedule['source']['head'][:12]}{' (dirty)' if schedule['source']['dirty'] else ''}; envelope ${schedule['envelope']['usd']} / {schedule['envelope']['physical_attempts']} attempts / {schedule['envelope']['window_minutes']} minutes. Basis: {schedule['basis']}.",
        "",
        "| Case | Launch | Steps | Calls | Ceiling | Cumulative | Attempts | Claims |",
        "|---|---|---|---:|---:|---:|---|---|",
    ]
    for row in schedule["cases"]:
        lines.append(
            f"| {row['case']} | {row['launch']} | {'; '.join(row['steps'])} | {len(row['calls'])} | ${row['billed_attempt_ceiling_usd']} | ${row['cumulative_ceiling_usd']} | "
            f"{row['physical_attempts_planned_max'][0]}-{row['physical_attempts_planned_max'][1]} | {', '.join(row['claims'])} |"
        )
    lines += ["", f"**Totals:** {totals['calls']} calls; billed-attempt ceiling ${totals['billed_attempt_ceiling_usd']}; attempts {totals['physical_attempts_planned_max'][0]}-{totals['physical_attempts_planned_max'][1]}.",
              f"Fits $0.50: {totals['fits_usd']} (shortfall ${totals['usd_shortfall']}); fits 24 attempts planned: {totals['fits_attempts_planned']}, at maximum: {totals['fits_attempts_max']}.", ""]  # fmt: skip
    lines += ["## Stop rules", ""] + [f"- {rule}" for rule in schedule["stop_rules"]] + ["", "## Launch order", ""] + [f"{n}. {step}" for n, step in enumerate(schedule["launch_order"], 1)]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="a new folder for the schedule, its prompt files and the workspace files")
    parser.add_argument("--summary-bytes", type=int, default=8_192, help="the summary size each fake summary call returns (8192 is the bound)")
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error(f"{args.out} exists; every schedule gets a new folder")
    schedule = build_schedule(args.summary_bytes)
    args.out.mkdir(parents=True)
    for name, text in {**PROMPT_FILES, **{f"workspace/{k}": v for k, v in WORKSPACE_FILES.items()}}.items():
        target = args.out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    (args.out / "stage-c-schedule.json").write_text(json.dumps(schedule, indent=2, default=str) + "\n", encoding="utf-8", newline="\n")
    (args.out / "stage-c-schedule.md").write_text(_markdown(schedule), encoding="utf-8", newline="\n")
    print(json.dumps(schedule["totals"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
