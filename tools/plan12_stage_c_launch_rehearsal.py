"""Plan 12.2 Stage C: the real-client launch rehearsal (Codex's review f381e730; the operator's approval cc95ec24).

r5's A6 never started: acpx splits its --agent value itself, treating a backslash as an escape except inside
single quotes. This tool runs the release schedule's own A6 and A7 acpx commands through the declared shell and
the pinned acpx shim, CLI and launch bundle, against the inert ACP double (tools/plan12_stage_c_acp_double.py)
packed as optimus-agent.exe with the already-installed distlib launcher, at an executable path and a workspace
path that both contain spaces. Only the executable and the workspace are substituted, explicitly, and every
command is checked to be exactly the generator's for those paths. It first reproduces r5's defect: the old
backslash path to a .cmd wrapper, in a folder without spaces as r5's was, must fail before the double starts.
No Optimus host, Gateway, model, provider, credential or network is involved.

It proves acpx's launch mechanics only - the argv, the working folder, initialize, A6's denied permission, A7's
Chat mode replayed before the prompt without session/load, and the close with no double left running - never
Optimus behaviour. `--schedule S --out R` writes the receipt: the acpx, Node, shell and double identities, the
commands, every outcome and problem. `--verify R --schedule S` is the release gate before the operator's hour:
it passes only for a passing receipt of exactly this schedule, made in the last 24 hours with today's acpx,
Node, shell and double.

Usage: python tools/plan12_stage_c_launch_rehearsal.py --schedule <stage-c-schedule.json> --out <receipt.json>
       python tools/plan12_stage_c_launch_rehearsal.py --verify <receipt.json> --schedule <stage-c-schedule.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import plan12_stage_c_acp_double as double
from tools import plan12_stage_c_schedule as schedule_tool

RECEIPT_SCHEMA = "stage-c-launch-rehearsal-v1"
MAX_AGE = timedelta(hours=24)
PERMISSION_DENIED_EXIT = 5  # acpx 0.12.0 EXIT_CODES.PERMISSION_DENIED
DENIAL = {"outcome": "selected", "optionId": "cancel"}  # --deny-all choosing Optimus's reject_once option
A6, NEW, MODE, PROMPT, CLOSE = (
    "A6: one-shot denied Agent turn", "A7: fresh named session", "A7: save Chat as the session's mode", "A7: the Chat prompt", "A7: close the session",
)  # fmt: skip
TITLES = (A6, NEW, MODE, PROMPT, CLOSE)
NPM = Path(os.environ.get("APPDATA", "")) / "npm"
ACPX_FILES = {
    "acpx": "acpx",  # the shim the declared bash runs
    "acpx.cmd": "acpx.cmd",
    "dist/cli.js": "node_modules/acpx/dist/cli.js",
    "dist/live-checkpoint-ClPCSdrW.js": "node_modules/acpx/dist/live-checkpoint-ClPCSdrW.js",  # --agent parsing and spawning
}
DOUBLE_SOURCE = Path(double.__file__)
# r5's form, replicated for the negative control only: a backslash path to a .cmd wrapper, as schedule v6 wrote it.
V6_WRAPPER = '@echo off\r\n"{exe}" --workspace-root "{workspace}" --plan12-test-profile qualification --plan12-stage-c --debug-trace\r\n'
V6_A6 = 'acpx --format json --deny-all --cwd "{workspace}" --agent "{wrapper}" exec "{prompt}"'


class RehearsalError(RuntimeError):
    """The rehearsal cannot be run as specified."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --- The commands ---------------------------------------------------------------------------------------------------


def rehearsal_commands(schedule: dict[str, Any], *, agent_exe: Path, workspace: Path) -> list[tuple[str, str]]:
    """The schedule's own A6 and A7 commands with only the agent executable and the workspace substituted. Each must
    equal the generator's command for those paths, so nothing else differs from what the operator's run uses."""
    runbook = schedule["runbook"]
    real_exe, real_workspace = runbook["paths"]["agent_exe"], runbook["paths"]["workspace"]
    paths = schedule_tool.RunbookPaths(agent_exe=agent_exe, workspace=workspace, evidence=Path(runbook["paths"]["evidence"]))
    generated = {step["title"]: step["commands"][0] for step in schedule_tool._runbook(paths)["steps"]}
    commands = []
    for step in runbook["steps"]:
        if step["kind"] in {"acpx-launch", "acpx-close"}:
            command = step["commands"][0].replace(real_exe, str(agent_exe)).replace(real_workspace, str(workspace))
            if command != generated.get(step["title"]):
                raise RehearsalError(f"{step['title']}: the schedule's command is not the generator's (only the executable and workspace may differ)")
            commands.append((step["title"], command))
    if tuple(title for title, _ in commands) != TITLES:
        raise RehearsalError(f"the schedule's acpx steps are {[t for t, _ in commands]}, not A6 then the A7 sequence")
    return commands


# --- Judging the outcomes -------------------------------------------------------------------------------------------


def _same_path(left: str, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(str(right)))


def _check_launch(title: str, events: list[dict[str, Any]], agent_exe: Path, workspace: Path, expected_args: list[str]) -> list[str]:
    if not events or events[0]["event"] != "start":
        return [f"{title}: no start record for its double"]
    start, problems = events[0], []
    if not _same_path(start["argv0"], agent_exe):
        problems.append(f"{title}: executable {start['argv0']!r} is not {str(agent_exe)!r}")
    if start["args"] != expected_args:
        problems.append(f"{title}: argv {start['args']!r} is not the generated {expected_args!r}")
    if not _same_path(start["cwd"], workspace):
        problems.append(f"{title}: working folder {start['cwd']!r} is not {str(workspace)!r}")
    requests = [event for event in events if event["event"] == "request"]
    methods = [event["method"] for event in requests]
    if not requests or methods[0] != "initialize" or requests[0].get("protocolVersion") != 1:
        problems.append(f"{title}: initialize at protocol 1 did not come first ({methods})")
    if "session/new" not in methods:
        problems.append(f"{title}: no session/new")
    permissions = [event.get("outcome") for event in events if event["event"] == "permission"]
    prompts = [event for event in requests if event["method"] == "session/prompt"]
    if title == A6:
        if "session/set_mode" in methods or [p.get("mode") for p in prompts] != ["agent"]:
            problems.append(f"{title}: expected one Agent prompt and no mode change ({methods})")
        if permissions != [DENIAL]:
            problems.append(f"{title}: the write permission outcome {permissions} is not a denial")
    elif title == NEW and methods != ["initialize", "session/new"]:
        problems.append(f"{title}: expected only initialize and session/new ({methods})")
    elif title == MODE and (methods != ["initialize", "session/new", "session/set_mode"] or requests[-1].get("modeId") != "chat"):
        problems.append(f"{title}: expected initialize, session/new and set_mode chat ({methods})")
    elif title == PROMPT:
        modes_before = [r.get("modeId") for r in requests[: methods.index("session/prompt")]] if prompts else []
        if len(prompts) != 1 or "chat" not in modes_before or prompts[0].get("mode") != "chat":
            problems.append(f"{title}: Chat was not replayed before the one prompt ({methods})")
        if permissions:
            problems.append(f"{title}: a permission was asked in Chat ({permissions})")
    return problems


_STDOUT = {NEW: ('"action":"session_ensured"', '"created":true'), MODE: ('"action":"mode_set"',), CLOSE: ('"action":"session_closed"',)}


def check(runs: list[dict[str, Any]], records: list[dict[str, Any]], *, agent_exe: Path, workspace: Path, alive: Callable[[int], bool]) -> list[str]:
    """Every problem with a rehearsal's launches: acpx's exits and results, each double's argv, executable, working
    folder and ACP exchange, any session/load, and any double still running after the close."""
    expected_args = schedule_tool._acpx_agent(schedule_tool.RunbookPaths(agent_exe=agent_exe, workspace=workspace, evidence=workspace))["argv"][1:]
    events: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        events[record["pid"]].append(record)
    problems = []
    if [run["title"] for run in runs] != list(TITLES):
        problems.append(f"the launches ran were {[run['title'] for run in runs]}, not {list(TITLES)}")
    for run in runs:
        title = run["title"]
        expected_exit = PERMISSION_DENIED_EXIT if title == A6 else 0
        if run["exit_code"] != expected_exit:
            problems.append(f"{title}: acpx exit {run['exit_code']}, expected {expected_exit}")
        expected_launches = 0 if title == CLOSE else 1
        if len(run["started_pids"]) != expected_launches:
            problems.append(f"{title}: {len(run['started_pids'])} agent launches, expected {expected_launches}")
        problems += [p for pid in run["started_pids"] for p in _check_launch(title, events[pid], agent_exe, workspace, expected_args)]
        compact = run["stdout"].replace(" ", "")
        problems += [f"{title}: acpx did not report {marker}" for marker in _STDOUT.get(title, ()) if marker not in compact]
    if any(record.get("method") == "session/load" for record in records):
        problems.append("a launch asked session/load, which Optimus does not offer")
    problems += [f"double {pid} is still running after the close" for pid in events if alive(pid)]
    return problems


def check_negative_control(run: dict[str, Any], *, started: int, wrapper: Path) -> list[str]:
    """r5's defect, reproduced: the old backslash path to a .cmd wrapper must fail at startup with the path's
    backslashes stripped, before the double starts. The wrapper's folder has no space, as r5's had none."""
    if " " in str(wrapper):
        raise RehearsalError("the negative control mirrors r5's wrapper path, which had no space")
    problems = []
    if run["exit_code"] == 0:
        problems.append("negative control: acpx succeeded")
    if started:
        problems.append("negative control: the double started, so r5's defect was not reproduced")
    if "AGENT_STARTUP_FAILED" not in run["stdout"]:
        problems.append("negative control: acpx did not report AGENT_STARTUP_FAILED")
    if str(wrapper).replace("\\", "") not in run["stdout"]:
        problems.append("negative control: the error does not show the wrapper path with its backslashes stripped")
    return problems


# --- The gate before the operator's hour ----------------------------------------------------------------------------


def verify(receipt_path: Path, schedule_path: Path, *, now: datetime, identity: Callable[[dict[str, Any]], dict[str, Any]]) -> list[str]:
    """Problems keeping the operator's hour from being requested: no passing receipt of exactly this schedule from
    the last 24 hours, or a changed acpx, Node, shell or double since."""
    if not Path(receipt_path).is_file():
        return [f"no rehearsal receipt at {receipt_path}"]
    if not Path(schedule_path).is_file():
        return [f"no schedule at {schedule_path}"]
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    if receipt.get("schema") != RECEIPT_SCHEMA:
        return [f"{receipt_path} is not a launch rehearsal receipt"]
    problems = []
    if receipt.get("passed") is not True:
        problems.append(f"the rehearsal did not pass: {receipt.get('problems')}")
    age = now - datetime.fromisoformat(receipt["created_at"])
    if not timedelta(0) <= age <= MAX_AGE:
        problems.append(f"stale: made {age} before the gate (limit {MAX_AGE})")
    if receipt["schedule"]["sha256"] != sha256_file(schedule_path):
        problems.append("the receipt rehearsed another schedule")
    current = identity(json.loads(Path(schedule_path).read_text(encoding="utf-8")))
    problems += [f"{part} changed since the rehearsal" for part in ("acpx", "node", "shell", "double_source_sha256") if receipt["identity"].get(part) != current.get(part)]
    return problems


# --- Running it -------------------------------------------------------------------------------------------------------


def _shell(schedule: dict[str, Any]) -> str:
    return schedule["runbook"]["acpx_shell"]["executable"]


def current_identity(schedule: dict[str, Any]) -> dict[str, Any]:
    """Today's acpx files, the Node the shim runs under the declared shell, that shell, and the double's source."""
    shell = _shell(schedule)
    node = subprocess.run([shell, "-c", 'node -e "console.log(process.execPath); console.log(process.version)"'], capture_output=True, text=True, timeout=60)
    node_path, node_version = (node.stdout.strip().splitlines() + ["", ""])[:2]
    shell_version = subprocess.run([shell, "--version"], capture_output=True, text=True, timeout=60).stdout.splitlines()[:1]
    return {
        "acpx": {name: sha256_file(NPM / relative) if (NPM / relative).is_file() else None for name, relative in ACPX_FILES.items()},
        "node": {"path": node_path, "version": node_version, "sha256": sha256_file(Path(node_path)) if node_path and Path(node_path).is_file() else None},
        "shell": {"executable": shell, "version": shell_version[0] if shell_version else None, "sha256": sha256_file(Path(shell))},
        "double_source_sha256": sha256_file(DOUBLE_SOURCE),
    }


def build_double(root: Path) -> Path:
    """The double packed as optimus-agent.exe by the already-installed distlib launcher, under a path with spaces."""
    from distlib.scripts import ScriptMaker

    source, scripts = root / "double source", root / "venv with spaces" / "Scripts"
    source.mkdir(parents=True)
    scripts.mkdir(parents=True)
    (source / "optimus-agent.py").write_text("#!python\n" + DOUBLE_SOURCE.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    maker = ScriptMaker(str(source), str(scripts), add_launchers=True)
    maker.executable = sys.executable
    exe = scripts / "optimus-agent.exe"
    if [Path(made) for made in maker.make("optimus-agent.py")] != [exe] or not exe.is_file():
        raise RehearsalError("distlib did not build the double's optimus-agent.exe launcher")
    return exe


def _execute(shell: str, command: str, env: dict[str, str]) -> dict[str, Any]:
    proc = subprocess.run([shell, "-c", command], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=180)
    return {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def _records(record: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in record.read_text(encoding="utf-8").splitlines() if line.strip()] if record.is_file() else []


def _started(record: Path) -> list[int]:
    return [entry["pid"] for entry in _records(record) if entry["event"] == "start"]


def _alive(pid: int) -> bool:
    """Whether a process still runs, by a query handle (never a signal: os.kill(pid, 0) broadcasts Ctrl-C on Windows)."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def run(schedule_path: Path, out: Path) -> int:
    if sys.platform != "win32":
        raise RehearsalError("the launch rehearsal runs on the operator's Windows host only")
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    identity = current_identity(schedule)
    pins = schedule["runbook"]["acpx"]["inspection_sha256"]
    problems = [f"acpx {name} is {identity['acpx'].get(name)}, not the pinned {digest}" for name, digest in pins.items() if identity["acpx"].get(name) != digest]
    shell = _shell(schedule)
    with tempfile.TemporaryDirectory(prefix="plan12-rehearsal-", ignore_cleanup_errors=True) as temporary:
        base = Path(temporary)
        root = base / "rehearsal root with spaces"
        exe = build_double(root)
        workspace = root / "work space"
        for folder in schedule_tool.WORKSPACE_DIRS:
            (workspace / folder).mkdir(parents=True)
        record = base / "double-record.jsonl"
        env = {**os.environ, double.RECORD_ENV: str(record)}
        wrapper = base / "negative-control" / "run-optimus-agent.cmd"
        wrapper.parent.mkdir()
        wrapper.write_text(V6_WRAPPER.format(exe=exe, workspace=workspace), encoding="ascii", newline="")
        old = V6_A6.format(workspace=workspace, wrapper=wrapper, prompt=schedule_tool.A6_PROMPT)
        negative = {"command": old, **_execute(shell, old, env), "started": len(_started(record))}
        negative["problems"] = check_negative_control(negative, started=negative["started"], wrapper=wrapper)
        problems += negative["problems"]
        record.unlink(missing_ok=True)
        runs = []
        for title, command in rehearsal_commands(schedule, agent_exe=exe, workspace=workspace):
            before = set(_started(record))
            result = _execute(shell, command, env)
            runs.append({"title": title, "command": command, **result, "started_pids": [pid for pid in _started(record) if pid not in before]})
        records = _records(record)
        problems += check(runs, records, agent_exe=exe, workspace=workspace, alive=_alive)
        double_exe = {"path_shape": str(exe.relative_to(base)), "sha256": sha256_file(exe)}
        substitution = {"agent_exe": [schedule["runbook"]["paths"]["agent_exe"], str(exe)], "workspace": [schedule["runbook"]["paths"]["workspace"], str(workspace)]}
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "passed": not problems,
        "problems": problems,
        "schedule": {"path": str(schedule_path), "sha256": sha256_file(schedule_path), "version": schedule["schedule"]},
        "identity": identity,
        "pins": pins,
        "generator_sha256": sha256_file(Path(schedule_tool.__file__)),
        "double": {"source": str(DOUBLE_SOURCE), "exe": double_exe, "builder": "distlib ScriptMaker t64 launcher"},
        "substitution": substitution,
        "negative_control": negative,
        "runs": runs,
        "double_records": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(receipt, indent=2) + "\n")
    print("launch rehearsal passed" if not problems else "launch rehearsal FAILED:\n" + "\n".join(problems))
    return 0 if not problems else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schedule", type=Path, required=True, help="the release's stage-c-schedule.json")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--out", type=Path, help="run the rehearsal and write a new receipt here")
    action.add_argument("--verify", type=Path, help="check a receipt is fresh, matching and passing; exit 0 only then")
    args = parser.parse_args(argv)
    if args.verify is not None:
        problems = verify(args.verify, args.schedule, now=datetime.now(UTC), identity=current_identity)
        print("rehearsal receipt fresh" if not problems else "\n".join(problems))
        return 0 if not problems else 1
    if args.out.exists():
        parser.error(f"{args.out} exists; every rehearsal writes a new receipt")
    return run(args.schedule, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
