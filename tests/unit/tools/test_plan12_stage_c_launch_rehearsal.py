"""Plan 12.2 Stage C: the real-client launch rehearsal (Codex's review f381e730; the operator's approval cc95ec24).

r5's A6 never started: acpx splits its --agent value itself. The rehearsal runs the schedule's own A6 and A7
commands through the declared shell and the pinned acpx against an inert ACP double packed as the agent
executable, with only the executable and workspace substituted, explicitly. These tests pin its judgement:
what a passing launch looks like, each way it can fail (lost backslashes, a split path or argument, the wrong
profile or workspace, a missing stage or debug flag, a missing denial or mode replay, a session/load, a child left
behind), the reproduced r5 defect, the substitution, the double's protocol, and the freshness gate before the
operator's hour. No acpx run happens here unless explicitly requested: a skipped run is never evidence, the
tool's receipt is.
"""

from __future__ import annotations

import copy
import io
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tools import plan12_stage_c_acp_double as double
from tools import plan12_stage_c_launch_rehearsal as rehearsal
from tools import plan12_stage_c_schedule as schedule_tool

EXE = Path(r"C:\rehearsal root with spaces\venv with spaces\Scripts\optimus-agent.exe")
WS = Path(r"C:\rehearsal root with spaces\work space")
ARGS = ["--workspace-root", str(WS), "--plan12-test-profile", "qualification", "--plan12-stage-c", "--debug-trace"]
A6, NEW, MODE, PROMPT, CLOSE = (
    "A6: one-shot denied Agent turn", "A7: fresh named session", "A7: save Chat as the session's mode", "A7: the Chat prompt", "A7: close the session",
)  # fmt: skip


def _start(pid: int, args: list[str] | None = None, cwd: Path = WS) -> dict:
    return {"pid": pid, "event": "start", "argv0": str(EXE), "args": list(ARGS if args is None else args), "cwd": str(cwd)}


def _request(pid: int, method: str, **fields) -> dict:
    return {"pid": pid, "event": "request", "method": method, **fields}


def _passing() -> tuple[list[dict], list[dict]]:
    """A passing rehearsal as the spike observed it: A6 denied (acpx exit 5), then the A7 sequence."""
    records = [
        _start(1), _request(1, "initialize", protocolVersion=1), _request(1, "session/new", cwd=str(WS)),
        _request(1, "session/prompt", mode="agent"), {"pid": 1, "event": "permission", "outcome": {"outcome": "selected", "optionId": "cancel"}},
        {"pid": 1, "event": "exit"},
        _start(2), _request(2, "initialize", protocolVersion=1), _request(2, "session/new", cwd=str(WS)), {"pid": 2, "event": "exit"},
        _start(3), _request(3, "initialize", protocolVersion=1), _request(3, "session/new", cwd=str(WS)), _request(3, "session/set_mode", modeId="chat"),
        {"pid": 3, "event": "exit"},
        _start(4), _request(4, "initialize", protocolVersion=1), _request(4, "session/new", cwd=str(WS)), _request(4, "session/set_mode", modeId="chat"),
        _request(4, "session/prompt", mode="chat"), {"pid": 4, "event": "exit"},
    ]  # fmt: skip
    runs = [
        {"title": A6, "exit_code": 5, "stdout": '{"result":{"stopReason":"end_turn"}}', "started_pids": [1]},
        {"title": NEW, "exit_code": 0, "stdout": '{"action":"session_ensured","created":true}', "started_pids": [2]},
        {"title": MODE, "exit_code": 0, "stdout": '{"action":"mode_set","modeId":"chat"}', "started_pids": [3]},
        {"title": PROMPT, "exit_code": 0, "stdout": '{"result":{"stopReason":"end_turn"}}', "started_pids": [4]},
        {"title": CLOSE, "exit_code": 0, "stdout": '{"action":"session_closed"}', "started_pids": []},
    ]
    return runs, records


def _check(runs, records, alive=lambda pid: False) -> list[str]:
    return rehearsal.check(runs, records, agent_exe=EXE, workspace=WS, alive=alive)


def test_a_passing_rehearsal_has_no_problem() -> None:
    assert _check(*_passing()) == []


def _with_args(records: list[dict], pid: int, args: list[str]) -> list[dict]:
    return [{**r, "args": args} if r["event"] == "start" and r["pid"] == pid else r for r in records]


@pytest.mark.parametrize(
    "args",
    [
        [ARGS[0], str(WS).replace("\\", ""), *ARGS[2:]],  # r5's lost backslashes
        [ARGS[0], r"C:\rehearsal", r"root with spaces\work space", *ARGS[2:]],  # a split path
        [*ARGS[:3], "attached", *ARGS[4:]],  # the wrong profile
        [ARGS[0], r"C:\elsewhere", *ARGS[2:]],  # the wrong workspace
        [a for a in ARGS if a != "--plan12-stage-c"],  # no stage flag
        [a for a in ARGS if a != "--debug-trace"],  # no debug flag
        [*ARGS, "--debug-trace"],  # an extra argument
    ],
    ids=["lost-backslashes", "split-path", "wrong-profile", "wrong-workspace", "no-stage-flag", "no-debug-flag", "extra-argument"],
)
@pytest.mark.parametrize("pid", [1, 4], ids=["A6", "A7-prompt"])
def test_any_argument_other_than_the_generated_ones_is_a_problem(args: list[str], pid: int) -> None:
    runs, records = _passing()
    problems = _check(runs, _with_args(records, pid, args))
    assert any("argv" in p for p in problems), problems


def test_a_different_executable_or_working_folder_is_a_problem() -> None:
    runs, records = _passing()
    moved = [{**r, "argv0": r"C:\other\optimus-agent.exe"} if r["event"] == "start" and r["pid"] == 2 else r for r in records]
    assert any("executable" in p for p in _check(runs, moved))
    elsewhere = [{**r, "cwd": r"C:\elsewhere"} if r["event"] == "start" and r["pid"] == 3 else r for r in records]
    assert any("working folder" in p for p in _check(runs, elsewhere))


@pytest.mark.parametrize(
    "outcome",
    [{"outcome": "selected", "optionId": "approve"}, {"outcome": "cancelled"}, None],
    ids=["approved", "cancelled", "no-permission-asked"],
)
def test_a6_needs_its_permission_actually_denied(outcome) -> None:
    runs, records = _passing()
    records = [r for r in records if r["event"] != "permission"]
    if outcome is not None:
        records.insert(5, {"pid": 1, "event": "permission", "outcome": outcome})
    assert any(p.startswith(A6) and "not a denial" in p for p in _check(runs, records))


def test_a6_needs_acpxs_permission_denied_exit() -> None:
    runs, records = _passing()
    runs[0]["exit_code"] = 0
    assert any("A6" in p and "exit" in p for p in _check(runs, records))


@pytest.mark.parametrize("change", ["no-replay", "replay-after-prompt", "agent-mode-prompt"])
def test_the_a7_prompt_needs_chat_replayed_before_it(change: str) -> None:
    runs, records = _passing()
    if change == "no-replay":
        records = [r for r in records if not (r["pid"] == 4 and r.get("method") == "session/set_mode")]
    elif change == "replay-after-prompt":
        replay = next(r for r in records if r["pid"] == 4 and r.get("method") == "session/set_mode")
        records.remove(replay)
        records.insert(records.index(next(r for r in records if r["pid"] == 4 and r.get("method") == "session/prompt")) + 1, replay)
    else:
        records = [{**r, "mode": "agent"} if r["pid"] == 4 and r.get("method") == "session/prompt" else r for r in records]
    assert any(PROMPT in p for p in _check(runs, records))


def test_a_session_load_or_an_a7_permission_is_a_problem() -> None:
    runs, records = _passing()
    # On A6's launch, whose method list is not otherwise pinned, only the session/load rule can catch it.
    loaded = [*records[:3], _request(1, "session/load"), *records[3:]]
    assert [p for p in _check(runs, loaded)] == ["a launch asked session/load, which Optimus does not offer"]
    asked = [*records, {"pid": 4, "event": "permission", "outcome": {"outcome": "selected", "optionId": "cancel"}}]
    assert any(PROMPT in p and "permission" in p for p in _check(runs, asked))


def test_a_double_left_running_after_the_close_is_a_problem() -> None:
    runs, records = _passing()
    assert any("still running" in p for p in _check(runs, records, alive=lambda pid: pid == 4))


def test_a_missing_or_extra_launch_or_a_wrong_exit_is_a_problem() -> None:
    runs, records = _passing()
    assert any(NEW in p for p in _check([r for r in runs if r["title"] != NEW], records))
    second = copy.deepcopy(runs)
    second[4]["started_pids"] = [5]
    assert any(CLOSE in p for p in _check(second, [*records, _start(5)]))
    failed = copy.deepcopy(runs)
    failed[2]["exit_code"] = 1
    assert any(MODE in p and "exit" in p for p in _check(failed, records))


# --- r5's defect, reproduced at the same boundary ------------------------------------------------------------------


def test_the_negative_control_must_reproduce_r5s_stripped_path() -> None:
    wrapper = Path(r"C:\plan12-rehearsal-x\run-optimus-agent.cmd")
    stripped = str(wrapper).replace("\\", "")
    run = {"exit_code": 1, "stdout": json.dumps({"error": {"message": f"'{stripped}' is not recognized", "data": {"detailCode": "AGENT_STARTUP_FAILED"}}})}
    assert rehearsal.check_negative_control(run, started=0, wrapper=wrapper) == []
    assert rehearsal.check_negative_control({**run, "exit_code": 0}, started=0, wrapper=wrapper)
    assert rehearsal.check_negative_control(run, started=1, wrapper=wrapper)  # the double started: not reproduced
    intact = {"exit_code": 1, "stdout": json.dumps({"error": {"message": f"'{wrapper}' failed", "data": {"detailCode": "AGENT_STARTUP_FAILED"}}})}
    assert rehearsal.check_negative_control(intact, started=0, wrapper=wrapper)
    with pytest.raises(rehearsal.RehearsalError, match="no space"):
        rehearsal.check_negative_control(run, started=0, wrapper=Path(r"C:\with space\run-optimus-agent.cmd"))


# --- The commands: the schedule's own, with only the executable and workspace substituted ------------------------


def _schedule(real_exe: Path, real_ws: Path) -> dict:
    return {"runbook": schedule_tool._runbook(schedule_tool.RunbookPaths(agent_exe=real_exe, workspace=real_ws, evidence=Path(r"C:\ev")))}


def test_the_rehearsal_runs_the_schedules_own_commands_with_only_the_executable_and_workspace_substituted() -> None:
    real = _schedule(Path(r"C:\venv\Scripts\optimus-agent.exe"), Path(r"C:\run\workspace"))
    commands = rehearsal.rehearsal_commands(real, agent_exe=EXE, workspace=WS)
    assert [title for title, _ in commands] == [A6, NEW, MODE, PROMPT, CLOSE]
    generated = {s["title"]: s["commands"][0] for s in _schedule(EXE, WS)["runbook"]["steps"]}
    assert all(command == generated[title] for title, command in commands)


def test_a_hand_edited_schedule_command_is_refused() -> None:
    real = _schedule(Path(r"C:\venv\Scripts\optimus-agent.exe"), Path(r"C:\run\workspace"))
    a6 = next(s for s in real["runbook"]["steps"] if s["title"] == A6)
    a6["commands"] = [a6["commands"][0].replace("--deny-all", "--approve-all")]
    with pytest.raises(rehearsal.RehearsalError, match="not the generator's"):
        rehearsal.rehearsal_commands(real, agent_exe=EXE, workspace=WS)


# --- The inert double, in process ----------------------------------------------------------------------------------


def _drive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, lines: list[dict]) -> tuple[list[dict], list[dict]]:
    record = tmp_path / "record.jsonl"
    monkeypatch.setenv(double.RECORD_ENV, str(record))
    out = io.StringIO()
    monkeypatch.setattr(double.sys, "stdout", out)
    assert double.Double(io.StringIO("".join(json.dumps(line) + "\n" for line in lines))).run() == 0
    sent = [json.loads(line) for line in out.getvalue().splitlines()]
    return sent, [json.loads(line) for line in record.read_text(encoding="utf-8").splitlines()]


def test_the_double_answers_as_optimus_advertises_and_records_the_denial(monkeypatch, tmp_path) -> None:
    sent, records = _drive(monkeypatch, tmp_path, [
        {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": 1}},
        {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": "C:\\w"}},
        {"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": {"sessionId": f"double-{os.getpid()}-1"}},
        {"jsonrpc": "2.0", "id": double.PERMISSION_ID, "result": {"outcome": {"outcome": "selected", "optionId": "cancel"}}},
    ])  # fmt: skip
    initialize = sent[0]["result"]
    assert initialize["protocolVersion"] == 1 and "loadSession" not in initialize["agentCapabilities"] and initialize["authMethods"] == []
    assert [m["id"] for m in sent[1]["result"]["modes"]["availableModes"]] == ["agent", "chat"]
    permission = sent[2]
    assert permission["method"] == "session/request_permission" and [o["kind"] for o in permission["params"]["options"]] == ["allow_once", "reject_once"]
    assert sent[-1] == {"jsonrpc": "2.0", "id": 2, "result": {"stopReason": "end_turn"}}
    assert [r["event"] for r in records] == ["start", "request", "request", "request", "permission", "exit"]
    assert records[4]["outcome"] == {"outcome": "selected", "optionId": "cancel"}


def test_the_double_answers_chat_without_asking_and_refuses_what_it_does_not_offer(monkeypatch, tmp_path) -> None:
    session = f"double-{os.getpid()}-1"
    sent, records = _drive(monkeypatch, tmp_path, [
        {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": "C:\\w"}},
        {"jsonrpc": "2.0", "id": 2, "method": "session/set_mode", "params": {"sessionId": session, "modeId": "chat"}},
        {"jsonrpc": "2.0", "id": 3, "method": "session/prompt", "params": {"sessionId": session}},
        {"jsonrpc": "2.0", "id": 4, "method": "session/load", "params": {}},
    ])  # fmt: skip
    assert not any(m.get("method") == "session/request_permission" for m in sent)
    assert {"jsonrpc": "2.0", "id": 3, "result": {"stopReason": "end_turn"}} in sent
    assert next(m for m in sent if m.get("id") == 4)["error"]["code"] == -32601
    assert [r.get("method") for r in records if r["event"] == "request"] == ["session/new", "session/set_mode", "session/prompt", "session/load"]


WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="the rehearsal packs and runs Windows launchers on the operator's host")


@WINDOWS_ONLY
def test_the_double_is_packed_as_a_real_executable_under_a_path_with_spaces(tmp_path) -> None:
    """distlib's launcher makes the double a real optimus-agent.exe, the shape acpx spawns directly; driven over stdio
    here (no acpx), it answers initialize and records its exact argv."""
    exe = rehearsal.build_double(tmp_path / "root with spaces")
    assert exe.name == "optimus-agent.exe" and " " in str(exe) and exe.read_bytes()[:2] == b"MZ"
    record = tmp_path / "record.jsonl"
    request = json.dumps({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": 1}}) + "\n"
    proc = subprocess.run([str(exe), "--workspace-root", r"C:\a b"], input=request, capture_output=True, text=True, timeout=60,
                          env={**os.environ, double.RECORD_ENV: str(record)})  # fmt: skip
    assert proc.returncode == 0 and json.loads(proc.stdout.splitlines()[0])["result"]["protocolVersion"] == 1
    start = json.loads(record.read_text(encoding="utf-8").splitlines()[0])
    assert start["args"] == ["--workspace-root", r"C:\a b"] and Path(start["argv0"]) == exe


_PIDS = {A6: 1, NEW: 2, MODE: 3, PROMPT: 4}
_STDOUTS = {A6: "", NEW: '{"action":"session_ensured","created":true}', MODE: '{"action":"mode_set"}', PROMPT: "", CLOSE: '{"action":"session_closed"}'}


def _fake_execute(shell: str, script: Path, env: dict) -> dict:
    """acpx and the double as the spike observed them, keyed off each command (read from the script the tool wrote):
    the records carry the command's own executable and workspace, so a passing outcome needs exactly those."""
    command = Path(script).read_text(encoding="utf-8").rstrip("\n")
    record = Path(env[double.RECORD_ENV])
    agent = command.split('--agent "')[1].split('"')[0]
    if agent.endswith("run-optimus-agent.cmd"):  # the negative control
        message = f"'{agent.replace(chr(92), '')}' is not recognized"
        return {"exit_code": 1, "stdout": json.dumps({"error": {"message": message, "data": {"detailCode": "AGENT_STARTUP_FAILED"}}}), "stderr": ""}
    title = next(t for marker, t in ((" exec ", A6), ("sessions new", NEW), ("set-mode", MODE), (" prompt ", PROMPT), ("sessions close", CLOSE)) if marker in command)
    if title in _PIDS:
        exe, workspace = agent.split("'")[1], command.split('--cwd "')[1].split('"')[0]
        _, records = _passing()
        with record.open("a", encoding="utf-8") as handle:
            for entry in records:
                if entry["pid"] == _PIDS[title]:
                    if entry["event"] == "start":
                        entry = {**entry, "argv0": exe, "cwd": workspace, "args": [ARGS[0], workspace, *ARGS[2:]]}
                    handle.write(json.dumps(entry) + "\n")
    return {"exit_code": 5 if title == A6 else 0, "stdout": _STDOUTS[title], "stderr": ""}


@WINDOWS_ONLY
def test_run_writes_one_new_receipt_with_every_outcome(tmp_path, monkeypatch) -> None:
    schedule_path = tmp_path / "stage-c-schedule.json"
    schedule = {"schedule": "stage-c-schedule-v7", **_schedule(Path(r"C:\venv\Scripts\optimus-agent.exe"), Path(r"C:\run\workspace"))}
    schedule_path.write_text(json.dumps(schedule), encoding="utf-8")
    pins = schedule["runbook"]["acpx"]["inspection_sha256"]
    monkeypatch.setattr(rehearsal, "current_identity", lambda _s, _env=None: {**IDENTITY, "acpx": {**IDENTITY["acpx"], "files": dict(pins)}})

    def build(root: Path) -> Path:
        exe = root / "venv with spaces" / "Scripts" / "optimus-agent.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"MZ")
        return exe

    monkeypatch.setattr(rehearsal, "build_double", build)
    monkeypatch.setattr(rehearsal, "_execute", _fake_execute)
    monkeypatch.setattr(rehearsal, "_alive", lambda pid: False)
    out = tmp_path / "rehearsal" / "receipt.json"

    assert rehearsal.run(schedule_path, out) == 0
    receipt = json.loads(out.read_text(encoding="utf-8"))
    assert (receipt["schema"], receipt["passed"], receipt["problems"]) == (rehearsal.RECEIPT_SCHEMA, True, [])
    assert receipt["schedule"]["sha256"] == rehearsal.sha256_file(schedule_path) and receipt["pins"] == pins
    assert [r["title"] for r in receipt["runs"]] == [A6, NEW, MODE, PROMPT, CLOSE] and receipt["negative_control"]["started"] == 0
    assert receipt["substitution"]["agent_exe"][0] == r"C:\venv\Scripts\optimus-agent.exe" and receipt["executions"] == 6
    with pytest.raises(FileExistsError):
        rehearsal.run(schedule_path, out)  # a receipt is never overwritten


@WINDOWS_ONLY
def test_a_command_reaches_the_declared_shell_exactly_as_written(tmp_path) -> None:
    r"""Passed with -c on the Windows command line, MSYS would turn `\\` into `\` and `\"` into `"` before bash saw the
    command; the rehearsal runs each command from a script file, so the shell sees it byte for byte."""
    script = tmp_path / "command.sh"
    script.write_text(r"""printf '%s|' 'single\\double' "quote\"inside" 'C:\plain\path'""" + "\n", encoding="utf-8", newline="\n")
    result = rehearsal._execute(schedule_tool.ACPX_SHELL["executable"], script, dict(os.environ))
    assert (result["exit_code"], result["stdout"]) == (0, r'single\\double|quote"inside|C:\plain\path|')


def _client_off_pins(change: str) -> dict:
    """IDENTITY's client with one required binding broken."""
    acpx, node = copy.deepcopy(IDENTITY["acpx"]), copy.deepcopy(IDENTITY["node"])
    kind, _, name = change.partition(":")
    if kind == "mismatched":
        acpx["files"][name] = "9" * 64
    elif kind == "missing":
        acpx["files"][name] = None
    elif kind == "type":
        acpx["type"] = name
    else:
        node["path"] = node["sha256"] = None
    return {**IDENTITY, "acpx": acpx, "node": node}


@WINDOWS_ONLY
@pytest.mark.parametrize(
    "change",
    [*(f"{kind}:{name}" for kind in ("mismatched", "missing") for name in rehearsal.ACPX_FILES), "type:function", "type:alias", "type:", "node:"],
)
def test_a_client_off_its_pins_stops_the_rehearsal_before_any_execution(tmp_path, monkeypatch, change: str) -> None:
    """Codex's review of c1134e1, M1.2: an unverified client is never executed. A missing, mismatched, unresolvable or
    unsupported client (a shell function or alias, no acpx on PATH, no Node runtime) fails with zero executions."""
    schedule_path = tmp_path / "stage-c-schedule.json"
    schedule = {"schedule": "stage-c-schedule-v7", **_schedule(Path(r"C:\venv\Scripts\optimus-agent.exe"), Path(r"C:\run\workspace"))}
    schedule["runbook"]["acpx"]["inspection_sha256"] = dict(PINS)
    schedule_path.write_text(json.dumps(schedule), encoding="utf-8")
    monkeypatch.setattr(rehearsal, "current_identity", lambda _s, _env=None: _client_off_pins(change))
    executed: list[str] = []
    monkeypatch.setattr(rehearsal, "_execute", lambda shell, command, env: executed.append(command) or pytest.fail("an unverified client was executed"))
    monkeypatch.setattr(rehearsal, "build_double", lambda root: pytest.fail("the rehearsal started after a client problem"))
    out = tmp_path / "receipt.json"

    assert rehearsal.run(schedule_path, out) == 1
    receipt = json.loads(out.read_text(encoding="utf-8"))
    assert (receipt["passed"], receipt["executions"], receipt["runs"], receipt["negative_control"]) == (False, 0, [], None)
    assert receipt["problems"] and executed == []


# --- The gate before the operator's hour ---------------------------------------------------------------------------


PINS = {name: digit * 64 for name, digit in zip(rehearsal.ACPX_FILES, "abce", strict=True)}
IDENTITY = {
    "acpx": {"type": "file", "shim": r"C:\npm\acpx", "files": dict(PINS)},
    "node": {"branch": "path", "path": r"C:\nodejs\node.exe", "version": "v26.5.0", "sha256": "f" * 64},
    "shell": {"version": "5.3.15"},
    "double_source_sha256": "d" * 64,
}


def _receipt(tmp_path: Path, *, pins: dict | None = None, **changes) -> tuple[Path, Path]:
    schedule = tmp_path / "stage-c-schedule.json"
    body = {"schedule": "stage-c-schedule-v7", "runbook": {"acpx_shell": schedule_tool.ACPX_SHELL, "acpx": {"inspection_sha256": dict(pins or PINS)}}}
    schedule.write_text(json.dumps(body) + "\n", encoding="utf-8")
    receipt = tmp_path / "rehearsal" / "receipt.json"
    receipt.parent.mkdir(exist_ok=True)
    body = {
        "schema": rehearsal.RECEIPT_SCHEMA, "created_at": (NOW - timedelta(hours=1)).isoformat(), "passed": True, "problems": [],
        "schedule": {"sha256": rehearsal.sha256_file(schedule)}, "identity": IDENTITY,
    }  # fmt: skip
    body.update(changes)
    receipt.write_text(json.dumps(body), encoding="utf-8")
    return receipt, schedule


NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


def _verify(receipt: Path, schedule: Path, identity=IDENTITY) -> list[str]:
    return rehearsal.verify(receipt, schedule, now=NOW, identity=lambda _schedule: identity)


def test_a_fresh_matching_passing_receipt_opens_the_gate(tmp_path) -> None:
    assert _verify(*_receipt(tmp_path)) == []


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"passed": False, "problems": ["A6: x"]}, "did not pass"),
        ({"created_at": (NOW - timedelta(hours=25)).isoformat()}, "stale"),
        ({"created_at": (NOW + timedelta(minutes=5)).isoformat()}, "stale"),
        ({"schedule": {"sha256": "0" * 64}}, "another schedule"),
        ({"schema": "other"}, "not a launch rehearsal receipt"),
    ],
    ids=["failed", "older-than-a-day", "from-the-future", "other-schedule", "other-schema"],
)
def test_a_failed_stale_or_mismatched_receipt_keeps_the_gate_shut(tmp_path, changes: dict, expected: str) -> None:
    assert any(expected in p for p in _verify(*_receipt(tmp_path, **changes)))


@pytest.mark.parametrize("part", ["acpx", "node", "shell", "double_source_sha256"])
def test_a_changed_client_shell_runtime_or_double_keeps_the_gate_shut(tmp_path, part: str) -> None:
    changed = {**IDENTITY, part: "changed"}
    assert any(part in p for p in _verify(*_receipt(tmp_path), identity=changed))


@pytest.mark.parametrize("change", ["mismatched:dist/cli.js", "missing:dist/live-checkpoint-ClPCSdrW.js", "type:function", "node:"])
def test_the_gate_refuses_a_client_off_its_pins_even_when_the_receipt_saw_the_same(tmp_path, change: str) -> None:
    current = _client_off_pins(change)
    assert _verify(*_receipt(tmp_path, identity=current), identity=current)


def _fake_client(folder: Path, *, adjacent_node: bool) -> None:
    """An inert stand-in for an npm-installed acpx: the bash shim, the cmd shim, the CLI and the launch bundle, and
    optionally an adjacent `node` the shim would prefer. Nothing here is ever executed but the fake `node`, which
    only prints a version and its own path."""
    dist = folder / "node_modules" / "acpx" / "dist"
    dist.mkdir(parents=True)
    (folder / "acpx").write_text("#!/bin/sh\necho inert acpx stand-in\n", encoding="utf-8", newline="\n")
    (folder / "acpx.cmd").write_text("@echo off\r\n", encoding="ascii", newline="")
    (dist / "cli.js").write_text(f"// cli {folder.name}\n", encoding="utf-8")
    (dist / "live-checkpoint-ClPCSdrW.js").write_text(f"// bundle {folder.name}\n", encoding="utf-8")
    if adjacent_node:
        (folder / "node").write_text(f"#!/bin/sh\nprintf '%s\\n' 'node_version=v0.0.0-adjacent' 'node_exec={folder / 'node'}'\n", encoding="utf-8", newline="\n")


def _env_with(*folders: Path) -> dict[str, str]:
    return {**os.environ, "PATH": ";".join([*(str(folder) for folder in folders), os.environ["PATH"]])}


@WINDOWS_ONLY
def test_the_client_is_resolved_as_the_declared_bash_runs_it_and_a_path_shadow_shuts_the_gate(tmp_path) -> None:
    """Codex's review of c1134e1, M1.1, reproduced: an `acpx` earlier on PATH is what bash runs, so it is the client.
    Its shim, the CLI and bundle beside it and the Node it would use (its adjacent-runtime branch here) are bound; a
    receipt for the installed client opens the gate, and the same receipt under the shadow keeps it shut."""
    shell = schedule_tool.ACPX_SHELL["executable"]
    installed, shadow = tmp_path / "installed client", tmp_path / "shadow"
    _fake_client(installed, adjacent_node=True)
    shadow.mkdir()
    (shadow / "acpx").write_text("#!/bin/sh\necho shadow\n", encoding="utf-8", newline="\n")

    client = rehearsal.resolve_client(shell, _env_with(installed))
    assert (client["type"], Path(client["shim"])) == ("file", installed / "acpx")
    assert (client["node"]["branch"], client["node"]["version"], Path(client["node"]["path"])) == ("adjacent", "v0.0.0-adjacent", installed / "node")
    assert client["files"]["dist/cli.js"] == rehearsal.sha256_file(installed / "node_modules" / "acpx" / "dist" / "cli.js")
    shadowed = rehearsal.resolve_client(shell, _env_with(shadow, installed))
    assert Path(shadowed["shim"]) == shadow / "acpx" and shadowed["files"]["dist/cli.js"] is None

    pins = dict(client["files"])
    schedule = {"runbook": {"acpx_shell": schedule_tool.ACPX_SHELL, "acpx": {"inspection_sha256": pins}}}
    receipt, schedule_path = _receipt(tmp_path, pins=pins, identity=rehearsal.current_identity(schedule, _env_with(installed)))
    assert rehearsal.verify(receipt, schedule_path, now=NOW, identity=lambda s: rehearsal.current_identity(s, _env_with(installed))) == []
    refused = rehearsal.verify(receipt, schedule_path, now=NOW, identity=lambda s: rehearsal.current_identity(s, _env_with(shadow, installed)))
    assert any("acpx" in p for p in refused)


@WINDOWS_ONLY
def test_a_shell_function_or_no_acpx_on_path_is_not_a_bound_client(tmp_path) -> None:
    shell = schedule_tool.ACPX_SHELL["executable"]
    installed = tmp_path / "installed client"
    _fake_client(installed, adjacent_node=True)
    function = rehearsal.resolve_client(shell, {**_env_with(installed), "BASH_FUNC_acpx%%": "() {  echo function\n}"})
    assert function["type"] == "function" and any("function" in p for p in rehearsal.client_problems(_identity_of(function), {}))
    git_only = {**os.environ, "PATH": str(Path(shell).parents[1] / "usr" / "bin")}
    absent = rehearsal.resolve_client(shell, git_only)
    assert absent["type"] == "" and any("not on the declared shell's PATH" in p for p in rehearsal.client_problems(_identity_of(absent), {}))


def _identity_of(client: dict) -> dict:
    return {**IDENTITY, "acpx": {k: client[k] for k in ("type", "shim", "files")}, "node": client["node"]}


def test_a_missing_receipt_or_schedule_keeps_the_gate_shut(tmp_path) -> None:
    receipt, schedule = _receipt(tmp_path)
    assert _verify(tmp_path / "absent.json", schedule) and _verify(receipt, tmp_path / "absent.json")


def test_the_gate_command_prints_fresh_only_when_it_opens(tmp_path, monkeypatch, capsys) -> None:
    receipt, schedule = _receipt(tmp_path)
    monkeypatch.setattr(rehearsal, "verify", lambda *a, **k: [])
    assert rehearsal.main(["--verify", str(receipt), "--schedule", str(schedule)]) == 0
    assert capsys.readouterr().out.strip() == "rehearsal receipt fresh"
    monkeypatch.setattr(rehearsal, "verify", lambda *a, **k: ["stale: made 25 h ago"])
    assert rehearsal.main(["--verify", str(receipt), "--schedule", str(schedule)]) == 1
    assert "stale" in capsys.readouterr().out


# --- The real rehearsal, only when explicitly requested -------------------------------------------------------------


@pytest.mark.skipif(os.environ.get("PLAN12_RUN_LAUNCH_REHEARSAL") != "1", reason="explicit only: a skip is never rehearsal evidence; the receipt is")
def test_the_real_rehearsal_passes_through_the_pinned_acpx(tmp_path) -> None:
    schedule = Path(os.environ["PLAN12_REHEARSAL_SCHEDULE"])
    receipt = tmp_path / "receipt.json"
    assert rehearsal.main(["--schedule", str(schedule), "--out", str(receipt)]) == 0
    assert json.loads(receipt.read_text(encoding="utf-8"))["passed"] is True
