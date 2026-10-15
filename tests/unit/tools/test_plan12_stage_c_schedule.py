"""Plan 12.2 Task 13 (Stage C): the executable claim-to-case schedule (Codex scope agreement, 2026-10-11,
section 5 and S1-S3; Codex completion review R3 and R4).

Three figures are kept apart. The conservative complete-case bound sizes an envelope: each case's calls are
bounded by host limits taken from source (planning turns, the turn-wide maintenance allowance, the
scenario's zero-call and cancellation turns, sliding's no-maintenance view), and each call at the most its
request can reserve (the Gateway refuses more input before any attempt). Measured allocations run the real
adapter, engine and attached composition on fixed fake replies of several sizes: they show how replies move
later packing and maintenance, and are never a bound. Expected spend is informational only.

The runbook is executable with the installed acpx 0.12.0: the reviewed agent executable launched directly, a
one-shot `exec` for the denied Agent case, an explicit fresh named session whose mode acpx replays on the
prompt's own fresh runtime session, an explicit close, and a custody check after every launch, all on one
ledger and window. Schedule v6 (release r5, Codex's r5 proposal of 2026-10-15): every launch path enables the
existing debug trace into the workspace's `.optimus/debug-acp.ndjson`, and each completed launch's runtime logs
and ledger are copied before its custody check, so launches never mix. Schedule v7 (after r5 stopped at A6;
Codex's review f381e730): acpx's --agent value is the reviewed executable with every part single-quoted, the
runbook declares the shell its acpx commands run from, and a fresh launch-rehearsal receipt gates the operator's
hour.
"""

from __future__ import annotations

import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from context_engine.summary import build_summary_prompt
from optimus.acp import __main__ as acp_main
from optimus.acp import stage_c as host
from optimus.acp.conversation import CONVERSATION_MAX_BYTES
from optimus.acp.launch_policy import DEFAULT_MAX_PLANNING_TURNS
from optimus.acp.session_config import STRATEGY_CONFIG_ID, SessionConfigSnapshot, build_session_config_options
from optimus_model_policy import stage_c
from optimus_model_policy import test_profiles as profiles
from tools import plan12_stage_c_schedule as tool

TASK13_CLAIMS = {
    "chat-non-mutation", "agent-exact-artifact-approval", "key-isolation", "attached-picker", "absent-picker-and-persisted-default",
    "sliding-warning", "meter-versus-storage-notices", "request-capacity-refusal", "storage-refusal", "attached-history-over-512kib",
    "repeated-engine-unavailability", "healthy-recovery", "cancellation-between-maintenance-calls", "checkpoint-reuse", "attached-small-session",
}  # fmt: skip
PRICES = (Decimal("0.50"), Decimal("2.50"))


@pytest.fixture(scope="module")
def schedule(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("schedule-paths")
    paths = tool.RunbookPaths(agent_exe=root / "venv" / "optimus-agent.exe", workspace=root / "workspace", evidence=root / "evidence")
    return tool.build_schedule(summary_bytes=8_192, reply_sizes=(3, 32_768), paths=paths)


def _reserve(input_tokens: int, output_cap: int) -> Decimal:
    return stage_c.reservation_usd(input_tokens=input_tokens, output_tokens=output_cap, input_usd_per_million=PRICES[0], output_usd_per_million=PRICES[1])


def test_every_applicable_claim_maps_to_a_case_with_steps_observations_and_artifacts(schedule) -> None:
    assert set(schedule["claims"]) == TASK13_CLAIMS
    for row in schedule["cases"]:
        assert row["steps"] and row["expected"] and row["artifacts"] and row["claims"] and row["unrun_if"], row["case"]
    acpx_claims = {claim for row in schedule["cases"] if row["client"] == "acpx" for claim in row["claims"]}
    assert {"chat-non-mutation", "agent-exact-artifact-approval", "key-isolation"} <= acpx_claims


# --- The conservative complete-case bound ----------------------------------------------------------------------


def test_each_call_is_bounded_by_the_most_its_request_can_reserve(schedule) -> None:
    limits = host.stage_c_limits(profiles.compose_test_profile_snapshot("attached"), tool.HAIKU)
    widest_summary = build_summary_prompt("x" * limits.limits.maintenance_input_tokens)  # one token per byte under the profile
    per_call = schedule["bound"]["per_call"]

    assert (per_call["answer"]["input_tokens"], per_call["answer"]["output_cap"]) == (limits.usable_input_tokens, 32_768) == (229_376, 32_768)
    assert (per_call["summary"]["input_tokens"], per_call["summary"]["output_cap"]) == (limits.estimate_request(widest_summary), 8_192)
    for kind in ("answer", "summary"):  # rounded up to the micro-dollar, so still a bound
        exact = _reserve(per_call[kind]["input_tokens"], per_call[kind]["output_cap"])
        assert Decimal(per_call[kind]["reserve_usd"]) == exact.quantize(Decimal("0.000001"), rounding="ROUND_CEILING") >= exact


def test_each_cases_calls_are_bounded_by_the_host_limits_in_source(schedule) -> None:
    scenario = stage_c.STAGE_C_SCENARIOS[stage_c.STAGE_C_ATTACHED_SCENARIO]["schedule"]
    allowance = host.MAX_MAINTENANCE_CALLS
    bounds = {row["case"]: (row["bound"]["answer_calls"], row["bound"]["summary_calls"]) for row in schedule["cases"]}

    assert bounds["A1"] == bounds["A7"] == (1, 0)
    assert bounds["A2"] == bounds["A6"] == (DEFAULT_MAX_PLANNING_TURNS, 0) == (3, 0)
    assert bounds["A3"] == bounds["A4"] == bounds["A5"] == (0, 0)  # refused before any attempt, or no prompt
    for live, case, strategy, _prompt in tool.ATTACHED_TURNS:
        key = f"{case}.{live}"
        if live in scenario["engine_unavailable_turns"]:
            assert bounds[key] == (0, 0), key
        elif live == scenario["cancel_pause_turn"]:
            assert bounds[key] == (1, scenario["cancel_pause_before_call"] - 1), key  # paused before the turn's 2nd call
        elif strategy == "sliding_window":
            assert bounds[key] == (1, 0), key  # a sliding view makes no maintenance call
        else:
            assert bounds[key] == (1, allowance), key
    assert bounds["B2"] == (1, 0)  # the unseeded session's first turn: its prompt alone, far under every allowance


def test_the_bound_totals_count_one_billed_attempt_and_two_physical_attempts_per_call(schedule) -> None:
    bound, per_call = schedule["bound"], schedule["bound"]["per_call"]
    answer, summary = Decimal(per_call["answer"]["reserve_usd"]), Decimal(per_call["summary"]["reserve_usd"])
    total, calls = Decimal(0), 0
    for row in schedule["cases"]:
        b = row["bound"]
        case_total = b["answer_calls"] * answer + b["summary_calls"] * summary
        assert Decimal(b["billed_attempt_bound_usd"]) == case_total.quantize(Decimal("0.000001"), rounding="ROUND_CEILING")
        assert b["physical_attempts_max"] == 2 * (b["answer_calls"] + b["summary_calls"])
        total += case_total
        calls += b["answer_calls"] + b["summary_calls"]
    totals = bound["totals"]
    assert totals["calls"] == calls and totals["physical_attempts_planned_max"] == [calls, 2 * calls]
    assert Decimal(totals["billed_attempt_bound_usd"]) == total.quantize(Decimal("0.000001"), rounding="ROUND_CEILING")
    limit, attempts = stage_c.STAGE_C_LIMIT_USD, stage_c.STAGE_C_MAX_ATTEMPTS
    assert totals["fits_usd"] is (total <= limit) and totals["fits_attempts_max"] is (2 * calls <= attempts)
    assert Decimal(totals["usd_shortfall"]) == max(Decimal(0), Decimal(totals["billed_attempt_bound_usd"]) - limit)
    assert bound["assumptions"] and all(isinstance(text, str) and text for text in bound["assumptions"])


def test_the_r5_envelope_holds_the_accepted_complete_case_bound(schedule) -> None:
    """The operator's r5 grant of 2026-10-15: $8 rounds the accepted $7.518097 bound up, and 138 attempts is
    exactly its maximum (one safe resend per call). The bound itself is unchanged by the envelope."""
    totals = schedule["bound"]["totals"]
    assert (totals["calls"], totals["billed_attempt_bound_usd"], totals["physical_attempts_planned_max"]) == (69, "7.518097", [69, 138])
    assert schedule["schedule"] == "stage-c-schedule-v7"
    assert schedule["envelope"] == {"release": "plan12-2-stage-c-r5", "usd": "8", "physical_attempts": 138, "window_minutes": 60}
    assert (totals["fits_usd"], totals["fits_attempts_planned"], totals["fits_attempts_max"], totals["usd_shortfall"]) == (True, True, True, "0")


# --- Measured allocations on fixed fake replies -----------------------------------------------------------------


def test_the_measured_paths_are_the_real_packing_of_the_pinned_seed(schedule) -> None:
    [short, long] = schedule["measured"]["paths"]
    assert (short["reply_bytes"], long["reply_bytes"]) == (3, 32_768) and "not a bound" in schedule["measured"]["basis"]
    turns = {turn["live"]: turn for turn in short["turns"]}
    assert len(turns[1]["summary_inputs"]) >= 2 and len(turns[1]["answer_envelopes"]) == 1  # a cold compaction, then the answer
    assert [(turns[n]["summary_inputs"], turns[n]["answer_envelopes"]) for n in (4, 5)] == [([], []), ([], [])]  # zero calls
    assert (turns[7]["stop"], len(turns[7]["summary_inputs"]), turns[7]["answer_envelopes"]) == ("cancelled", 1, [])
    assert schedule["source"]["seed"]["records_bytes"] > CONVERSATION_MAX_BYTES


def test_longer_replies_move_later_packing_and_maintenance(schedule) -> None:
    """Replies become history (Codex completion review R3): on the longer-reply path the steady-state turn no
    longer just reuses the checkpoint, the path makes more calls, and the views change in no fixed direction,
    which is why a measured path is never a bound."""
    short, long = ({turn["live"]: turn for turn in path["turns"]} for path in schedule["measured"]["paths"])
    assert short[2]["summary_inputs"] == [] and len(long[2]["summary_inputs"]) >= 1
    assert long[2]["answer_envelopes"] != short[2]["answer_envelopes"]
    assert sum(len(t["summary_inputs"]) for t in long.values()) > sum(len(t["summary_inputs"]) for t in short.values())
    totals = [path["totals"]["calls"] for path in schedule["measured"]["paths"]]
    assert totals[1] > totals[0]


def test_a2s_history_is_a1s_rendered_record_not_an_allowance(schedule) -> None:
    short, long = schedule["measured"]["paths"]
    a2 = {path["reply_bytes"]: path["calls_by_case"]["A2"][0]["input_tokens"] for path in (short, long)}
    assert a2[32_768] - a2[3] == 32_768 - 3  # exactly A1's longer reply, one token per byte


def test_the_bound_dominates_every_measured_path(schedule) -> None:
    bound = schedule["bound"]
    for path in schedule["measured"]["paths"]:
        assert path["totals"]["calls"] <= bound["totals"]["calls"]
        assert Decimal(path["totals"]["billed_attempt_allocation_usd"]) <= Decimal(bound["totals"]["billed_attempt_bound_usd"])
        for case, calls in path["calls_by_case"].items():
            row = next(r for r in schedule["cases"] if r["case"] == case)["bound"]
            kinds = [c["kind"] for c in calls]
            assert kinds.count("summary") <= row["summary_calls"] and len(kinds) - kinds.count("summary") <= row["answer_calls"], case
            per_call = bound["per_call"]
            assert all(c["input_tokens"] <= per_call["summary" if c["kind"] == "summary" else "answer"]["input_tokens"] for c in calls), case


# --- The executable runbook -----------------------------------------------------------------------------------


def _commands(schedule) -> list[str]:
    return [command for step in schedule["runbook"]["steps"] for command in step["commands"]]


def test_acpx_launches_the_reviewed_executable_directly_with_single_quoted_arguments(schedule) -> None:
    """r5's A6 never started: acpx splits its --agent value itself, treating a backslash as an escape except inside
    single quotes, and runs a .cmd agent through cmd. The value is now the reviewed optimus-agent.exe itself (no
    wrapper), every part single-quoted, carrying exactly the qualification launch arguments; the real-client
    rehearsal proves acpx turns it into exactly that argv."""
    runbook = schedule["runbook"]
    paths, agent = runbook["paths"], runbook["acpx_agent"]
    argv = [paths["agent_exe"], "--workspace-root", paths["workspace"], "--plan12-test-profile", "qualification", "--plan12-stage-c", "--debug-trace"]
    assert agent["argv"] == argv
    assert agent["value"] == " ".join(f"'{part}'" for part in argv)
    assert agent["sha256"] == hashlib.sha256(agent["value"].encode("utf-8")).hexdigest()
    assert "agent_wrapper" not in runbook and all(".cmd" not in command for command in _commands(schedule))


@pytest.mark.parametrize("bad", ["it's", 'a"b', "a$b", "a`b"], ids=["single-quote", "double-quote", "dollar", "backtick"])
def test_a_launch_path_the_quoting_cannot_carry_is_refused(tmp_path: Path, bad: str) -> None:
    for paths in (
        tool.RunbookPaths(agent_exe=tmp_path / bad / "optimus-agent.exe", workspace=tmp_path / "ws", evidence=tmp_path / "ev"),
        tool.RunbookPaths(agent_exe=tmp_path / "optimus-agent.exe", workspace=tmp_path / bad, evidence=tmp_path / "ev"),
    ):
        with pytest.raises(ValueError, match="cannot be quoted"):
            tool._runbook(paths)


def test_the_runbook_pins_the_acpx_shim_cli_and_launch_bundle_the_rehearsal_checks(schedule) -> None:
    """Codex's review, item 3: the pins cover the shim the declared bash runs, the cmd shim, the CLI and the bundle
    that parses and spawns the --agent command, not cli.js alone."""
    pins = schedule["runbook"]["acpx"]["inspection_sha256"]
    assert pins == {
        "acpx": "805200badb253f80c442dad64453fbaf761848d32de691d8048fcba7607c321d",  # pragma: allowlist secret - public file digest
        "acpx.cmd": "212da5e557d5d621af89e5bf7f86dbe59e674ba69595c14038bbcdde39c37f79",  # pragma: allowlist secret - public file digest
        "dist/cli.js": "7da1d8b2fe0fc19696febddb3486729ce82b04b2a64a367e16df0691776483a4",  # pragma: allowlist secret - public file digest
        "dist/live-checkpoint-ClPCSdrW.js": "d92153086f058880623af7297a6867166068e27f9b2cc97a7b94c6a80e2b20da",  # pragma: allowlist secret - public file digest
    }


def test_the_runbook_declares_the_shell_its_acpx_commands_run_from(schedule) -> None:
    runbook = schedule["runbook"]
    assert runbook["acpx_shell"] == {"name": "bash (Git for Windows)", "executable": r"C:\Program Files\Git\bin\bash.exe"}
    assert any("bash (Git for Windows)" in text and "exactly as written" in text for text in runbook["preconditions"])


def test_a_fresh_launch_rehearsal_receipt_gates_the_operators_hour(schedule) -> None:
    """Codex's review, item 3: release preparation must hold a fresh, matching, passing rehearsal receipt before the
    operator's hour is requested; the gate is the runbook's first step, before any approval or launch."""
    steps = schedule["runbook"]["steps"]
    evidence, workspace = schedule["runbook"]["paths"]["evidence"], schedule["runbook"]["paths"]["workspace"]
    receipt, schedule_file = Path(evidence) / "rehearsal" / "receipt.json", Path(workspace).parent / "stage-c-schedule.json"
    assert steps[0]["kind"] == "rehearsal-gate" and [s["kind"] for s in steps].count("rehearsal-gate") == 1
    assert steps[0]["commands"] == [f'python tools/plan12_stage_c_launch_rehearsal.py --verify "{receipt}" --schedule "{schedule_file}"']
    assert steps[0]["evidence"] == [str(receipt)] and "stop" in steps[0]["note"]


ZED_PREFIX = "Zed settings agent_servers Optimus: "


def _launch_argvs(runbook: dict) -> dict[str, list[str]]:
    """Every actual host launch's arguments: acpx's (the generator's intended argv; the rehearsal proves acpx's own
    parsing yields it) and both Zed entries'."""
    exe = runbook["paths"]["agent_exe"]
    assert runbook["acpx_agent"]["argv"][0] == exe
    argvs = {"acpx": runbook["acpx_agent"]["argv"][1:]}
    for step in runbook["steps"]:
        if step["kind"] == "zed-launch":
            entry = json.loads(step["commands"][0].removeprefix(ZED_PREFIX))
            assert entry["command"] == exe
            argvs[step["title"]] = entry["args"]
    return argvs


def test_every_launch_path_writes_the_debug_trace_into_the_workspace(tmp_path: Path) -> None:
    """Codex's r5 proposal, step 4: the flag is in the actual launch arguments, not a README. Parsed by the host's
    own parser and resolved as the host resolves it, each path traces into the workspace's runtime folder, and a
    rejected request through the observer the host wires (bootstrap test) writes its content-free status record."""
    from optimus.acp.debug_trace import log_provider_attempts, reset_debug_trace_context
    from optimus.acp.operator_paths import resolve_operator_paths
    from optimus.agent.models import AgentRunRequest
    from optimus.agent.runner import AgentRunner
    from optimus.gateway.errors import GatewayHttpError
    from optimus.gateway.models import GatewayRouteAttempt
    from optimus.runtime.modes import ExecutionMode

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runbook = tool._runbook(tool.RunbookPaths(agent_exe=tmp_path / "venv" / "optimus-agent.exe", workspace=workspace, evidence=tmp_path / "evidence"))
    argvs = _launch_argvs(runbook)
    assert set(argvs) == {"acpx", "L1 Zed launch (qualification)", "L2 Zed launch (attached)"}
    expected_log = workspace.resolve() / ".optimus" / "debug-acp.ndjson"
    canary = "Authorization: Bearer " + "r5-launch-canary"

    class Rejecting:
        def create_response(self, **_kwargs):
            attempts = (GatewayRouteAttempt(attempt=1, gateway_request_id="gw-1", outcome="rejected", http_status=429),
                        GatewayRouteAttempt(attempt=2, gateway_request_id="gw-2", outcome="rejected", http_status=403))  # fmt: skip
            raise GatewayHttpError(502, canary, gateway_code="UPSTREAM_ATTEMPT_REJECTED", retryable=False, route_attempts=attempts)

    for name, argv in argvs.items():
        args = acp_main.parse_args(argv)
        assert (args.debug_trace, args.debug_log, args.plan12_stage_c, Path(args.workspace_root)) == (True, None, True, workspace), name
        assert args.plan12_test_profile == ("attached" if "attached" in name else "qualification"), name
        expected_log.unlink(missing_ok=True)
        try:
            default = resolve_operator_paths(workspace_root=workspace, environ=dict(os.environ)).debug_log_path
            assert acp_main._apply_debug_trace_args(args, workspace_root=workspace, default_log_path=default) == expected_log, name
            request = AgentRunRequest(run_id="s:1", session_id="s", task="Hello.", workspace_root=workspace, execution_mode=ExecutionMode.CHAT)
            AgentRunner(gateway_client=Rejecting(), model="fake/model", provider_attempt_observer=log_provider_attempts).run(request)
        finally:
            reset_debug_trace_context()
        text = expected_log.read_text(encoding="utf-8")
        [record] = [r for r in map(json.loads, text.splitlines()) if r["location"] == "debug_trace.py:log_provider_attempts"]
        assert [(a["outcome"], a["upstream_http_status"]) for a in record["data"]["attempts"]] == [("rejected", 429), ("rejected", 403)], name
        assert canary not in text, name


RUNTIME_FILES = ("debug-acp.ndjson", "telemetry.jsonl", "local-gateway.log", "launch-audit.ndjson")


def test_each_completed_launchs_runtime_logs_are_captured_before_its_custody_check(schedule) -> None:
    """A copy per completed launch, made before the next step can launch again, so launches never mix; a stop
    captures at once. Each capture names the debug log, telemetry, Gateway log, launch audit and the release
    ledger, into its own evidence folder."""
    steps = schedule["runbook"]["steps"]
    workspace, evidence_root = schedule["runbook"]["paths"]["workspace"], schedule["runbook"]["paths"]["evidence"]
    launches = [n for n, step in enumerate(steps) if step["kind"] in {"zed-launch", "acpx-launch", "acpx-close"}]
    captures = [n for n, step in enumerate(steps) if step["kind"] == "capture"]
    for n in launches:
        next_launch = min((m for m in launches if m > n), default=len(steps))
        check = next(m for m in range(n + 1, len(steps)) if steps[m]["kind"] == "custody-check")
        if check < next_launch:  # the launch has ended by this check: its capture comes right before it
            assert steps[check - 1]["kind"] == "capture", steps[n]["title"]
    assert len(captures) == 6  # after L1 Zed, A6, A7 sessions new, A7 set-mode, A7 close, L2 Zed
    destinations = [steps[n]["evidence"][0] for n in captures]
    assert len(set(destinations)) == len(destinations) and all(d.startswith(evidence_root) for d in destinations)
    for n in captures:
        command = steps[n]["commands"][0]
        assert all(name in command for name in RUNTIME_FILES) and f"{stage_c.STAGE_C_RELEASE_ID}.jsonl" in command
        assert str(Path(workspace) / ".optimus") in command and "never overwrite" in command
    preconditions = " ".join(schedule["runbook"]["preconditions"])
    assert "--debug-trace" in preconditions and "On any stop" in preconditions


def test_the_acpx_cases_never_rely_on_a_saved_or_recovered_session(schedule) -> None:
    commands = [c for c in _commands(schedule) if c.startswith("acpx ")]
    agent = schedule["runbook"]["acpx_agent"]["value"]
    assert all(f'--agent "{agent}"' in c for c in commands)
    exec_steps = [c for c in commands if " exec " in c]
    assert len(exec_steps) == 1 and "--deny-all" in exec_steps[0]  # A6: one-shot, its own fresh session
    named = [c for c in commands if "stage-c-a7" in c]
    kinds = [next(k for k in ("sessions new", "set-mode chat", "prompt", "sessions close") if k in c) for c in named]
    assert kinds == ["sessions new", "set-mode chat", "prompt", "sessions close"]  # fresh, mode saved, replayed, closed
    assert "--ttl 0" in named[2] and "--name stage-c-a7" in named[0]
    assert all("stage-c-a7" in c for c in commands if " prompt " in c or " set-mode " in c)  # never an unnamed saved session


def test_every_launch_is_followed_by_a_custody_check_on_the_same_ledger(schedule) -> None:
    steps = schedule["runbook"]["steps"]
    checks = [n for n, step in enumerate(steps) if step["kind"] == "custody-check"]
    launches = [n for n, step in enumerate(steps) if step["kind"] in {"zed-launch", "acpx-launch"}]
    assert checks[0] < launches[0]  # the prior qualification host is stopped and checked first
    for n in launches:
        assert any(c > n for c in checks), steps[n]["title"]
        next_launch = min((m for m in launches if m > n), default=len(steps))
        assert any(n < c < next_launch for c in checks), f"no custody check between {steps[n]['title']} and the next launch"
    previous = None
    for n in checks:
        command = steps[n]["commands"][0]
        assert command.startswith("python tools/plan12_stage_c_transition_check.py") and "--out" in command
        if previous is not None:
            assert f"--previous {previous}" in command  # the same ledger, window and non-decreasing totals
        previous = steps[n]["evidence"][0]
    approvals = [step for step in steps if step["kind"] == "approval"]
    profiles_approved = [s["commands"][0].split("--plan12-test-profile ")[1].split()[0] for s in approvals]
    assert profiles_approved == ["qualification", "attached"] and all("--plan12-stage-c" in s["commands"][0] for s in approvals)
    evidence_root = schedule["runbook"]["paths"]["evidence"]
    assert all(path.startswith(evidence_root) for step in steps for path in step["evidence"])


def test_the_tool_writes_a_new_folder_and_never_reuses_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schedule) -> None:
    monkeypatch.setattr(tool, "build_schedule", lambda **_kwargs: schedule)
    out = tmp_path / "schedule"
    assert tool.main(["--out", str(out)]) == 0
    written = json.loads((out / "stage-c-schedule.json").read_text(encoding="utf-8"))
    assert written["bound"]["totals"] == json.loads(json.dumps(schedule["bound"]["totals"], default=str))
    assert (out / "capacity-prompt.txt").stat().st_size == schedule["prompt_files"]["capacity-prompt.txt"]["bytes"]
    assert not (out / "run-optimus-agent.cmd").exists()  # no wrapper: acpx launches the reviewed executable directly
    assert (out / "workspace" / "README.md").is_file() and (out / "stage-c-schedule.md").read_text(encoding="utf-8").startswith("# Stage C executable schedule")
    with pytest.raises(SystemExit):
        tool.main(["--out", str(out)])


SCHEDULED_TARGETS = {"notes/chat-should-not-write.md", "scratch/stage-c-agent.txt", "scratch/acpx-denied.txt", "scratch/acpx-chat.txt"}


def _generate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schedule) -> Path:
    monkeypatch.setattr(tool, "build_schedule", lambda **_kwargs: schedule)
    out = tmp_path / "schedule"
    assert tool.main(["--out", str(out)]) == 0
    return out / "workspace"


def test_every_scheduled_file_target_has_its_parent_prepared_and_is_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schedule) -> None:
    # r2's A2 failed: the writer needs an existing parent and the workspace had no scratch/ (Codex A2 stop return,
    # 2026-10-12). Without the parent the absence checks of A6 and A7 would also pass whatever the client did.
    assert set(tool.WORKSPACE_TARGETS) == SCHEDULED_TARGETS
    workspace = _generate(tmp_path, monkeypatch, schedule)
    for target in SCHEDULED_TARGETS:
        assert (workspace / target).parent.is_dir(), target
        assert not (workspace / target).exists(), target
    assert not any((workspace / "scratch").iterdir())
    assert schedule["workspace_dirs"] == ["notes", "scratch"] and sorted(schedule["workspace_targets"]) == sorted(SCHEDULED_TARGETS)


def test_the_workspace_fixture_check_names_every_departure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schedule) -> None:
    workspace = _generate(tmp_path, monkeypatch, schedule)
    (workspace / ".optimus" / "plan12-stage-c").mkdir(parents=True)  # the release ceremony's ledger folder is expected
    assert tool.verify_workspace(workspace) == []
    assert tool.main(["--verify-workspace", str(workspace)]) == 0
    (workspace / "scratch").rmdir()
    (workspace / "scratch-elsewhere.txt").write_text("x", encoding="utf-8")
    (workspace / "notes" / "chat-should-not-write.md").write_text("hello", encoding="utf-8")
    (workspace / "README.md").write_text("changed", encoding="utf-8")
    problems = tool.verify_workspace(workspace)
    assert problems == [
        "README.md differs from the fixture",
        "scratch/ is missing",
        "notes/chat-should-not-write.md already exists",
        "unexpected workspace entry: scratch-elsewhere.txt",
    ]
    assert tool.main(["--verify-workspace", str(workspace)]) == 1
    assert tool.verify_workspace(tmp_path / "absent") == [f"{tmp_path / 'absent'} is not a directory"]


def test_the_runbook_checks_the_workspace_fixture_before_the_first_launch(schedule) -> None:
    steps = schedule["runbook"]["steps"]
    kinds = [step["kind"] for step in steps]
    fixture = kinds.index("fixture-check")
    assert kinds.index("approval") < fixture < kinds.index("custody-check") < kinds.index("zed-launch")
    workspace = schedule["runbook"]["paths"]["workspace"]
    assert steps[fixture]["commands"] == [f'python tools/plan12_stage_c_schedule.py --verify-workspace "{workspace}"']
    assert kinds.count("fixture-check") == 1  # A2 writes its artifact, so later launches cannot expect the targets absent


def _dispatches(row: dict) -> bool:
    return row["bound"]["answer_calls"] + row["bound"]["summary_calls"] > 0


def test_the_meter_is_expected_only_where_a_request_is_dispatched(schedule) -> None:
    # r3's A3 stopped: the schedule expected a request meter on a refused turn, but a refusal dispatches and
    # commits nothing and so sends no reading (design spec 8.4; spec.py _emit_usage_update). The claim's
    # positive check sits on its dispatched turn (Codex r3 stop return, 2026-10-13).
    rows = [row for row in schedule["cases"] if "meter-versus-storage-notices" in row["claims"]]
    assert [row["case"] for row in rows] == ["A3", "B3.1"]
    assert [row["case"] for row in rows if _dispatches(row)] == ["B3.1"]
    for row in schedule["cases"]:
        if _dispatches(row):
            assert tool.NO_METER_READING not in row["expected"], row["case"]
            if row in rows:
                assert tool.METER_READING in row["expected"], row["case"]
        else:
            assert tool.METER_READING not in row["expected"], row["case"]
            if row in rows:
                assert tool.NO_METER_READING in row["expected"], row["case"]
    assert not any("the request meter, separate" in text for row in schedule["cases"] for text in row["expected"])


def test_a_turn_that_makes_no_call_expects_no_ledger_record(schedule) -> None:
    # The same class: a scheduled unavailable turn makes no call, so it has no reserve/settle record to collect.
    for row in schedule["cases"]:
        expects_records = any("reserve/settle records for the turn" in text for text in row["artifacts"])
        assert expects_records == (_dispatches(row) and row["case"].startswith("B") and row["case"] != "B2"), row["case"]
    assert [row["case"] for row in schedule["cases"] if tool.NO_LEDGER_RECORD in row["artifacts"]] == ["B6.4", "B6.5"]


def test_a2_captures_the_permission_request_before_it_is_approved(schedule) -> None:
    # r3's A2 evidence showed only the completed write (Codex r3 stop return): the exact artifact the operator
    # approves is captured from the permission request itself, before the click; the host records no path.
    [a2] = [row for row in schedule["cases"] if row["case"] == "A2"]
    assert tool.A2_PERMISSION_CAPTURE in a2["artifacts"] and "scratch/stage-c-agent.txt" in tool.A2_PERMISSION_CAPTURE
    capture = next(n for n, step in enumerate(a2["steps"]) if step.startswith("Capture the permission request"))
    approve = next(n for n, step in enumerate(a2["steps"]) if step.startswith("Approve"))
    assert capture < approve


def test_a6_names_a_checkable_key_isolation_observation(schedule) -> None:
    # Key isolation (Plan 9.9): no provider key in the environment passed to acpx; the host takes the key from the
    # OS keyring. "The run reports no resolvable provider key" named nothing a working run reports; the check
    # records variable names only, never values, before the exec.
    [a6] = [row for row in schedule["cases"] if row["case"] == "A6"]
    assert tool.KEY_ISOLATION_CHECK in a6["artifacts"]
    assert not any("resolvable provider key" in text for row in schedule["cases"] for text in row["artifacts"] + row["expected"])
    record = next(n for n, step in enumerate(a6["steps"]) if step.startswith("Before the exec, record the names"))
    assert record < next(n for n, step in enumerate(a6["steps"]) if "exec command" in step)


def test_the_picker_cases_expect_only_the_selectors_each_profile_advertises(schedule) -> None:
    # Codex schedule v4 review M1: A5 required a model picker and "both pickers", but the engine-absent profile
    # advertises Mode alone and no profile enables model selection (session_config.py). Checked against the real
    # builders, not only the wording.
    absent = build_session_config_options(SessionConfigSnapshot(mode_id="chat", strategy=None))
    attached = build_session_config_options(SessionConfigSnapshot(mode_id="chat", strategy="compaction"))
    assert [o["id"] for o in absent] == ["mode"] and [o["id"] for o in attached] == ["mode", STRATEGY_CONFIG_ID]
    choices = [option["name"] for option in absent[0]["options"]]
    assert choices == ["Agent", "Chat"]
    [a5] = [row for row in schedule["cases"] if row["case"] == "A5"]
    # Every advertised choice is an expected observation after the switch, not only a word somewhere in A5.
    assert any("after switching" in item and all(name in item for name in choices) for item in a5["expected"])
    assert any("persisted" in item for item in a5["expected"])
    assert any("Context strategy and model selection are absent" in item for item in a5["expected"])
    assert (a5["bound"]["answer_calls"], a5["bound"]["summary_calls"], a5["claims"]) == (0, 0, ["absent-picker-and-persisted-default"])
    [b3] = [row for row in schedule["cases"] if row["case"] == "B3.1"]
    assert "the attached picker shows Mode and Context strategy" in b3["expected"]
    required = [text for row in schedule["cases"] for text in row["steps"] + row["expected"] + row["artifacts"]]
    assert not any(phrase in text for text in required for phrase in ("both pickers", "model options", "model picker"))


def test_the_paste_files_hit_the_refusal_they_are_named_for(schedule) -> None:
    files = schedule["prompt_files"]
    usable = 262_144 - 32_768
    assert usable < files["capacity-prompt.txt"]["bytes"] < CONVERSATION_MAX_BYTES  # over request capacity, inside storage
    assert files["capacity-prompt.txt"]["bytes"] * 5 >= CONVERSATION_MAX_BYTES * 4  # also crosses the 80% storage warning
    assert files["storage-prompt.txt"]["bytes"] > CONVERSATION_MAX_BYTES
