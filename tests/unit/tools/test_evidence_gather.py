"""CLI ownership, parser surface, and Task-4 stage behavior."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ENTRY = REPO_ROOT / "tools" / "evidence_gather.py"
SUPPORT = REPO_ROOT / "tools" / "evidence_gather_support"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "evidence" / "scenarios" / "zed-session.toml"
PROMPT_INJECTION_RE = re.compile(r"prompt[_-]?inject", re.IGNORECASE)


def _gather():
    import tools.evidence_gather as gather

    return gather


def test_entry_point_module_exists() -> None:
    assert ENTRY.is_file()
    assert not (SUPPORT / "__main__.py").exists()


def test_parser_exposes_exactly_seven_subcommands() -> None:
    gather = _gather()
    parser = gather.build_parser()
    sub = next(action for action in parser._actions if getattr(action, "choices", None))
    assert set(sub.choices) == {
        "validate",
        "prepare",
        "check",
        "collect",
        "classify",
        "redact",
        "inspect",
    }
    assert "all" not in sub.choices
    assert "run" not in sub.choices


def test_forbidden_commands_are_rejected() -> None:
    gather = _gather()
    with pytest.raises(SystemExit):
        gather.build_parser().parse_args(["all"])
    with pytest.raises(SystemExit):
        gather.build_parser().parse_args(["run"])


def test_no_destination_or_model_defaults_on_parser() -> None:
    gather = _gather()
    help_text = gather.build_parser().format_help().lower()
    assert "--model" not in help_text
    assert " all" not in f" {help_text} "
    prepare = gather.build_parser().parse_args(
        [
            "prepare",
            "--scenario",
            str(FIXTURE.resolve()),
            "--capture-root",
            str((REPO_ROOT / "tmp-capture").resolve()),
        ]
    )
    assert Path(prepare.capture_root).is_absolute()


def test_no_console_script_registration_for_evidence_gather() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    scripts = text.split("[project.scripts]", 1)[1].split("\n[", 1)[0]
    assert "evidence_gather" not in scripts
    assert "evidence-gather" not in scripts
    assert 'optimus-agent = "optimus.acp.__main__:main"' in scripts


def test_support_package_has_no_main_or_prompt_injection_ids() -> None:
    assert SUPPORT.is_dir()
    assert not (SUPPORT / "__main__.py").exists()
    offenders: list[str] = []
    for path in SUPPORT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if PROMPT_INJECTION_RE.search(text):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []


def test_only_entry_point_imports_support_from_outside() -> None:
    allowed = {ENTRY.resolve()}
    offenders: list[str] = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(
                "tools.evidence_gather_support"
            ):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("tools.evidence_gather_support"):
                        offenders.append(path.relative_to(REPO_ROOT).as_posix())
    for path in (REPO_ROOT / "tools").rglob("*.py"):
        if path.resolve() in allowed:
            continue
        if SUPPORT in path.parents or path.parent == SUPPORT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(
                "tools.evidence_gather_support"
            ):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []


def test_validate_without_model_binding_fails_before_side_effects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gather = _gather()
    code = gather.main(
        [
            "validate",
            "--scenario",
            str(FIXTURE.resolve()),
        ]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "missing_binding" in err


def test_validate_with_model_binding_emits_content_free_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    gather = _gather()
    code = gather.main(
        [
            "validate",
            "--scenario",
            str(FIXTURE.resolve()),
            "--bind",
            "model=operator-supplied",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["scenario_id"] == "zed-session"
    assert "scenario_sha256" in payload
    assert payload["client_adapter_id"] == "zed_acp_client"
    assert "operator-supplied" not in out  # content-free: no binding values


def test_prepare_and_check_are_digest_idempotent(tmp_path: Path) -> None:
    gather = _gather()
    capture = (tmp_path / "capture").resolve()
    scenario = str(FIXTURE.resolve())
    bind = ["--bind", "model=operator-supplied"]
    first = gather.main(
        ["prepare", "--scenario", scenario, "--capture-root", str(capture), *bind]
    )
    second = gather.main(
        ["prepare", "--scenario", scenario, "--capture-root", str(capture), *bind]
    )
    assert first == 0
    assert second == 0
    check = gather.main(
        ["check", "--scenario", scenario, "--capture-root", str(capture), *bind]
    )
    assert check == 0


def test_truncated_fixture_marker_fails_prepare_with_stable_code(tmp_path: Path) -> None:
    from evidence_handoff.collector.scenarios import load_scenario, resolve_bindings
    from tools.evidence_gather_support.common import HostError
    from tools.evidence_gather_support.fixtures import prepare_fixtures

    capture = (tmp_path / "capture").resolve()
    run_id = "run-truncated"
    run_dir = capture / run_id
    run_dir.mkdir(parents=True)
    marker = run_dir / "fixture-marker.json"
    # Simulate crash mid-write: on-disk bytes that are not a complete stage document.
    marker.write_text(
        '{"schema":"evidence-fixture-marker-v1","complete":tru',
        encoding="utf-8",
    )
    scenario = load_scenario(FIXTURE)
    bindings = resolve_bindings(scenario, ("model=operator-supplied",))
    with pytest.raises(HostError) as exc_info:
        prepare_fixtures(
            capture_root=capture,
            scenario=scenario,
            bindings=bindings,
            run_id=run_id,
        )
    assert exc_info.value.code in {"invalid_json", "partial_stage"}
    assert "Expecting" not in str(exc_info.value)
    assert "JSONDecode" not in type(exc_info.value).__name__


def test_truncated_fixture_marker_fails_check_without_claiming_ready(
    tmp_path: Path,
) -> None:
    from evidence_handoff.collector.scenarios import load_scenario
    from tools.evidence_gather_support.common import HostError
    from tools.evidence_gather_support.fixtures import run_preconditions

    capture = (tmp_path / "capture").resolve()
    run_id = "run-truncated-check"
    run_dir = capture / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "fixture-marker.json").write_text(
        '{"schema":"evidence-fixture-marker-v1","complete":tru',
        encoding="utf-8",
    )
    scenario = load_scenario(FIXTURE)
    with pytest.raises(HostError) as exc_info:
        run_preconditions(capture_root=capture, scenario=scenario, run_id=run_id)
    assert exc_info.value.code in {"fixture_incomplete", "invalid_json", "partial_stage"}
    result = json.loads((run_dir / "precondition-result.json").read_text(encoding="utf-8"))
    assert result["complete"] is True
    assert "capture_root_ready" not in result["codes"]
    assert any(
        code in {"fixture_incomplete", "invalid_json", "partial_stage", "fixture_missing"}
        for code in result["codes"]
    )


def test_fixture_stage_writes_use_atomic_json_helpers() -> None:
    text = (SUPPORT / "fixtures.py").read_text(encoding="utf-8")
    assert "_atomic_write_json" in text
    assert "_read_complete_json" in text
    assert ".write_text(" not in text


def test_unknown_adapter_fails_before_fixture_mutation(tmp_path: Path) -> None:
    gather = _gather()
    scenario_path = tmp_path / "bad.toml"
    text = FIXTURE.read_text(encoding="utf-8").replace(
        'adapter_id = "hermetic_user_data_fixture"',
        'adapter_id = "unknown_fixture"',
    )
    scenario_path.write_text(text, encoding="utf-8")
    capture = (tmp_path / "capture").resolve()
    code = gather.main(
        [
            "prepare",
            "--scenario",
            str(scenario_path.resolve()),
            "--capture-root",
            str(capture),
            "--bind",
            "model=operator-supplied",
        ]
    )
    assert code == 2
    assert not any(capture.rglob("*")) if capture.exists() else True


def test_unavailable_stages_print_stable_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gather = _gather()
    capture = (tmp_path / "capture").resolve()
    capture.mkdir()
    code = gather.main(
        [
            "classify",
            "--scenario",
            str(FIXTURE.resolve()),
            "--capture-root",
            str(capture),
            "--result",
            str((tmp_path / "result.json").resolve()),
            "--bind",
            "model=operator-supplied",
        ]
    )
    assert code == 2
    assert "stage_unavailable" in capsys.readouterr().err


def test_live_markers_are_registered_and_excluded_by_default() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for marker in (
        "requires_acpx",
        "requires_zed",
        "requires_windows_desktop",
        "evidence_investigation",
    ):
        assert marker in text
    addopts = text.split("addopts", 1)[1].split("]", 1)[0]
    for marker in (
        "requires_acpx",
        "requires_zed",
        "requires_windows_desktop",
        "evidence_investigation",
    ):
        assert f"not {marker}" in addopts or marker in addopts
    # Default selection must exclude the new live markers.
    assert "not requires_acpx" in text
    assert "not requires_zed" in text
    assert "not requires_windows_desktop" in text
    assert "not evidence_investigation" in text


# --- Task 5: NDJSON / ACP / completion / collect ---


def _exit_event(
    *,
    request_id: str = "req-1",
    method: str = "session/prompt",
    has_error: bool = False,
    session_id: str = "debug_abc",
    timestamp: int = 1_000,
) -> dict:
    return {
        "sessionId": session_id,
        "timestamp": timestamp,
        "location": "server.py:process_request:exit",
        "message": "client request handled",
        "data": {
            "request_id": request_id,
            "method": method,
            "has_error": has_error,
            "stop_reason": None if has_error else "end_turn",
        },
        "hypothesisId": "H4",
        "runId": "pre-fix",
    }


def _prompt_entry(
    *,
    session_id: str = "session-aaa",
    request_id: str = "req-1",
    run_id: str = "session-aaa:req-1",
    timestamp: int = 900,
) -> dict:
    return {
        "sessionId": "debug_abc",
        "timestamp": timestamp,
        "location": "spec.py:_handle_session_prompt:entry",
        "message": "session prompt",
        "data": {
            "session_id": session_id,
            "request_id": request_id,
            "run_id": run_id,
        },
        "hypothesisId": "H4",
        "runId": "pre-fix",
    }


def test_ndjson_records_pre_run_byte_offset_and_file_identity(tmp_path: Path) -> None:
    from tools.evidence_gather_support import ndjson as ndjson_mod

    path = tmp_path / "debug-acp.ndjson"
    path.write_text('{"location":"older"}\n', encoding="utf-8")
    snap = ndjson_mod.snapshot_source(path)
    assert snap.byte_offset == path.stat().st_size
    assert snap.identity.size_bytes == path.stat().st_size
    assert snap.identity.path == path.resolve()


def test_ndjson_extracts_ordered_suffix_only(tmp_path: Path) -> None:
    from tools.evidence_gather_support import ndjson as ndjson_mod

    path = tmp_path / "debug-acp.ndjson"
    older = json.dumps({"location": "older", "timestamp": 1}, separators=(",", ":"))
    newer = json.dumps({"location": "newer", "timestamp": 2}, separators=(",", ":"))
    path.write_text(older + "\n", encoding="utf-8")
    snap = ndjson_mod.snapshot_source(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(newer + "\n")
    records = ndjson_mod.read_ordered_suffix(path, snap)
    assert [item["location"] for item in records] == ["newer"]


def test_ndjson_rejects_partial_final_record(tmp_path: Path) -> None:
    from tools.evidence_gather_support import ndjson as ndjson_mod
    from tools.evidence_gather_support.common import HostError

    path = tmp_path / "debug-acp.ndjson"
    path.write_text("", encoding="utf-8")
    snap = ndjson_mod.snapshot_source(path)
    path.write_text('{"location":"partial"', encoding="utf-8")
    with pytest.raises(HostError) as exc_info:
        ndjson_mod.read_ordered_suffix(path, snap)
    assert exc_info.value.code == "partial_ndjson_record"


def test_ndjson_rejects_malformed_interior_record(tmp_path: Path) -> None:
    from tools.evidence_gather_support import ndjson as ndjson_mod
    from tools.evidence_gather_support.common import HostError

    path = tmp_path / "debug-acp.ndjson"
    path.write_text("", encoding="utf-8")
    snap = ndjson_mod.snapshot_source(path)
    path.write_text("{not-json}\n{\"location\":\"ok\"}\n", encoding="utf-8")
    with pytest.raises(HostError) as exc_info:
        ndjson_mod.read_ordered_suffix(path, snap)
    assert exc_info.value.code == "malformed_ndjson_record"


def test_ndjson_rejects_rotation_or_replacement(tmp_path: Path) -> None:
    from tools.evidence_gather_support import ndjson as ndjson_mod
    from tools.evidence_gather_support.common import HostError

    path = tmp_path / "debug-acp.ndjson"
    path.write_text('{"a":1}\n{"a":2}\n', encoding="utf-8")
    snap = ndjson_mod.snapshot_source(path)
    path.write_text('{"r":1}\n', encoding="utf-8")
    with pytest.raises(HostError) as exc_info:
        ndjson_mod.read_ordered_suffix(path, snap)
    assert exc_info.value.code in {"ndjson_rotated", "ndjson_identity_changed"}


def test_ndjson_rejects_foreign_suffix_session(tmp_path: Path) -> None:
    from tools.evidence_gather_support import ndjson as ndjson_mod
    from tools.evidence_gather_support.common import HostError

    path = tmp_path / "debug-acp.ndjson"
    path.write_text("", encoding="utf-8")
    snap = ndjson_mod.snapshot_source(path)
    foreign = _exit_event(session_id="debug_foreign")
    path.write_text(json.dumps(foreign, separators=(",", ":")) + "\n", encoding="utf-8")
    records = ndjson_mod.read_ordered_suffix(path, snap)
    with pytest.raises(HostError) as exc_info:
        ndjson_mod.normalize_completion(
            records,
            correlate_session_id="session-aaa",
            correlate_request_id="req-1",
            correlate_run_id="session-aaa:req-1",
            expected_debug_session_id="debug_abc",
        )
    assert exc_info.value.code == "foreign_ndjson_suffix"


def test_ndjson_bounded_reads_do_not_load_prefix(tmp_path: Path) -> None:
    from tools.evidence_gather_support import ndjson as ndjson_mod

    path = tmp_path / "debug-acp.ndjson"
    prefix = (("x" * 1024) + "\n") * 8
    path.write_text(prefix, encoding="utf-8")
    snap = ndjson_mod.snapshot_source(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"location": "tail"}, separators=(",", ":")) + "\n")
    records = ndjson_mod.read_ordered_suffix(path, snap)
    assert [item["location"] for item in records] == ["tail"]
    # Suffix-only: digest of the full file must differ from suffix digest.
    full = hashlib.sha256(path.read_bytes()).hexdigest()
    assert ndjson_mod.suffix_sha256(path, snap) != full
    assert len(records) == 1


def test_acp_argument_vector_ownership_and_shell_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.evidence_gather_support import acp as acp_mod
    from tools.evidence_gather_support.common import HostError

    seen: dict[str, object] = {}

    def fake_which(name: str) -> str | None:
        return r"C:\tools\acpx.exe" if name == "acpx" else None

    def fake_run(command, **kwargs):
        class Result:
            returncode = 0
            stdout = "acpx 0.1.0\n"
            stderr = ""

        assert kwargs.get("shell") is False
        return Result()

    def fake_popen(command, **kwargs):
        seen["command"] = list(command)
        seen["shell"] = kwargs.get("shell")

        class Proc:
            returncode = 0

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

            def communicate(self, timeout=None):
                return ("", "")

            def kill(self):
                return None

            stdout = None
            stderr = None

        return Proc()

    monkeypatch.setattr(acp_mod.shutil, "which", fake_which)
    monkeypatch.setattr(acp_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(acp_mod.subprocess, "Popen", fake_popen)

    workspace = Path(r"D:\ws").resolve()
    agent = Path(r"D:\bin\optimus-agent.exe").resolve()
    command = acp_mod.build_acpx_command(
        acpx_path=r"C:\tools\acpx.exe",
        workspace_root=workspace,
        agent_executable=agent,
        prompt="ping",
        launch_session_id="launch-1",
    )
    assert command[0] == r"C:\tools\acpx.exe"
    assert "--format" in command and "json" in command
    assert "shell" not in {part.lower() for part in command}
    assert all(not part.startswith("%") for part in command)

    acp_mod.spawn_acpx(command=command, cwd=workspace, env={}, timeout_seconds=5)
    assert seen["shell"] is False
    assert seen["command"] == command

    monkeypatch.setattr(acp_mod.shutil, "which", lambda _name: None)
    with pytest.raises(HostError) as missing:
        acp_mod.resolve_acpx()
    assert missing.value.code == "acpx_not_on_path"


def test_acp_process_timeout_is_content_free(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.evidence_gather_support import acp as acp_mod
    from tools.evidence_gather_support.common import HostError

    class Proc:
        returncode = None

        def poll(self):
            return None

        def wait(self, timeout=None):
            raise acp_mod.subprocess.TimeoutExpired(cmd=["acpx"], timeout=timeout)

        def communicate(self, timeout=None):
            raise acp_mod.subprocess.TimeoutExpired(cmd=["acpx"], timeout=timeout)

        def kill(self):
            self.returncode = -9
            return None

        stdout = None
        stderr = None

    monkeypatch.setattr(acp_mod.subprocess, "Popen", lambda *a, **k: Proc())
    with pytest.raises(HostError) as exc_info:
        acp_mod.spawn_acpx(
            command=["acpx", "exec", "x"],
            cwd=Path(".").resolve(),
            env={},
            timeout_seconds=1,
        )
    assert exc_info.value.code == "acpx_timeout"


def test_completion_matches_exact_location_and_correlation() -> None:
    from tools.evidence_gather_support import ndjson as ndjson_mod

    records = (_prompt_entry(), _exit_event())
    claim = ndjson_mod.normalize_completion(
        records,
        correlate_session_id="session-aaa",
        correlate_request_id="req-1",
        correlate_run_id="session-aaa:req-1",
        expected_debug_session_id="debug_abc",
        scenario_id="zed-session",
        run_id="collector-run-1",
        evidence_sha256=("a" * 64,),
    )
    assert claim.claim_kind.value == "completion_observed"
    assert claim.reason_code == "ok"


def test_completion_rejects_error_bearing_and_older_events() -> None:
    from tools.evidence_gather_support import ndjson as ndjson_mod
    from tools.evidence_gather_support.common import HostError

    with pytest.raises(HostError) as err:
        ndjson_mod.normalize_completion(
            (_prompt_entry(), _exit_event(has_error=True)),
            correlate_session_id="session-aaa",
            correlate_request_id="req-1",
            correlate_run_id="session-aaa:req-1",
            expected_debug_session_id="debug_abc",
            scenario_id="zed-session",
            run_id="collector-run-1",
            evidence_sha256=("a" * 64,),
        )
    assert err.value.code == "completion_has_error"

    with pytest.raises(HostError) as older:
        ndjson_mod.normalize_completion(
            (_prompt_entry(timestamp=2_000), _exit_event(timestamp=1_000)),
            correlate_session_id="session-aaa",
            correlate_request_id="req-1",
            correlate_run_id="session-aaa:req-1",
            expected_debug_session_id="debug_abc",
            scenario_id="zed-session",
            run_id="collector-run-1",
            evidence_sha256=("a" * 64,),
        )
    assert older.value.code in {"completion_ordering", "completion_ambiguous", "completion_missing"}


def test_completion_never_creates_render_observed() -> None:
    from evidence_handoff.collector.models import ClaimKind
    from tools.evidence_gather_support import ndjson as ndjson_mod

    records = (_prompt_entry(), _exit_event())
    claim = ndjson_mod.normalize_completion(
        records,
        correlate_session_id="session-aaa",
        correlate_request_id="req-1",
        correlate_run_id="session-aaa:req-1",
        expected_debug_session_id="debug_abc",
        scenario_id="zed-session",
        run_id="collector-run-1",
        evidence_sha256=("a" * 64,),
    )
    assert claim.claim_kind is ClaimKind.COMPLETION_OBSERVED
    assert claim.claim_kind is not ClaimKind.RENDER_OBSERVED


def test_completion_requires_correlating_prompt_not_request_id_alone() -> None:
    from tools.evidence_gather_support import ndjson as ndjson_mod
    from tools.evidence_gather_support.common import HostError

    # Bare exit with matching request_id but foreign run_id and no prompt entry.
    with pytest.raises(HostError) as exc_info:
        ndjson_mod.normalize_completion(
            (_exit_event(request_id="req-1"),),
            correlate_session_id="session-aaa",
            correlate_request_id="req-1",
            correlate_run_id="totally-different-foreign-run-id",
            expected_debug_session_id="debug_abc",
            scenario_id="zed-session",
            run_id="collector-run-1",
            evidence_sha256=("a" * 64,),
        )
    assert exc_info.value.code in {
        "completion_correlation_missing",
        "completion_missing",
        "foreign_completion",
    }

    # Prompt present but run_id does not match correlate_run_id.
    with pytest.raises(HostError) as foreign:
        ndjson_mod.normalize_completion(
            (
                _prompt_entry(run_id="session-aaa:req-1"),
                _exit_event(request_id="req-1"),
            ),
            correlate_session_id="session-aaa",
            correlate_request_id="req-1",
            correlate_run_id="foreign-run",
            expected_debug_session_id="debug_abc",
            scenario_id="zed-session",
            run_id="collector-run-1",
            evidence_sha256=("a" * 64,),
        )
    assert foreign.value.code in {
        "completion_correlation_missing",
        "completion_missing",
        "foreign_completion",
    }


def test_spawn_acpx_drains_pipes_instead_of_deadlocking(tmp_path: Path) -> None:
    """Large stdout must not hang spawn_acpx for the full timeout window."""
    import os
    import sys
    import time

    from tools.evidence_gather_support import acp as acp_mod

    script = tmp_path / "big_stdout.py"
    script.write_text(
        "import sys\n"
        "sys.stdout.write('x' * 300_000)\n"
        "sys.stdout.flush()\n"
        "sys.stderr.write('y' * 10_000)\n"
        "sys.stderr.flush()\n",
        encoding="utf-8",
    )
    # Inherit a minimal host env so the real interpreter can start; this case
    # is about pipe draining, not launch-env cleanliness.
    env = {key: value for key, value in os.environ.items() if key in {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "PATHEXT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOME",
        "PYTHONPATH",
        "SYSTEMDRIVE",
        "COMSPEC",
    }}
    started = time.monotonic()
    code = acp_mod.spawn_acpx(
        command=[sys.executable, str(script.resolve())],
        cwd=tmp_path.resolve(),
        env=env,
        timeout_seconds=8,
    )
    elapsed = time.monotonic() - started
    assert code == 0
    assert elapsed < 4.0, f"spawn_acpx appeared to deadlock waiting without drain: {elapsed:.2f}s"


def test_collect_handler_is_registered_not_stage_unavailable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    gather = _gather()
    capture = (tmp_path / "capture").resolve()
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    agent = (tmp_path / "optimus-agent").resolve()
    agent.write_text("#!/bin/true\n", encoding="utf-8")
    ndjson_path = workspace / ".optimus" / "debug-acp.ndjson"
    ndjson_path.parent.mkdir(parents=True)
    ndjson_path.write_text("", encoding="utf-8")

    prepare = gather.main(
        [
            "prepare",
            "--scenario",
            str(FIXTURE.resolve()),
            "--capture-root",
            str(capture),
            "--bind",
            "model=operator-supplied",
        ]
    )
    assert prepare == 0
    assert gather.main(
        [
            "check",
            "--scenario",
            str(FIXTURE.resolve()),
            "--capture-root",
            str(capture),
            "--bind",
            "model=operator-supplied",
        ]
    ) == 0

    from tools.evidence_gather_support import acp as acp_mod

    monkeypatch.setattr(acp_mod, "resolve_acpx", lambda: (r"C:\tools\acpx.exe", "acpx 0.1.0"))

    def fake_spawn(*, command, cwd, env, timeout_seconds):
        entry = _prompt_entry()
        exit_event = _exit_event()
        with ndjson_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
            handle.write(json.dumps(exit_event, separators=(",", ":")) + "\n")
        return 0

    monkeypatch.setattr(acp_mod, "spawn_acpx", fake_spawn)
    monkeypatch.setattr(
        acp_mod,
        "build_acpx_command",
        lambda **kwargs: ["acpx", "--format", "json", "exec", "ping"],
    )

    code = gather.main(
        [
            "collect",
            "--scenario",
            str(FIXTURE.resolve()),
            "--capture-root",
            str(capture),
            "--bind",
            "model=operator-supplied",
            "--workspace-root",
            str(workspace),
            "--agent-executable",
            str(agent),
            "--prompt",
            "ping",
            "--timeout-seconds",
            "30",
            "--ndjson-path",
            str(ndjson_path.resolve()),
            "--correlate-session-id",
            "session-aaa",
            "--correlate-request-id",
            "req-1",
            "--correlate-run-id",
            "session-aaa:req-1",
            "--debug-session-id",
            "debug_abc",
        ]
    )
    err = capsys.readouterr().err
    assert "stage_unavailable" not in err
    assert code == 0


# --- Task 6: Zed crash-log collection ---


def _minidump_header() -> bytes:
    return b"MDMP" + (b"\x00" * 28)


def _prepare_collect_workspace(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    capture = (tmp_path / "capture").resolve()
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    agent = (tmp_path / "optimus-agent").resolve()
    agent.write_text("#!/bin/true\n", encoding="utf-8")
    ndjson_path = workspace / ".optimus" / "debug-acp.ndjson"
    ndjson_path.parent.mkdir(parents=True)
    ndjson_path.write_text("", encoding="utf-8")
    return capture, workspace, agent, ndjson_path


def _stub_acp_for_collect(
    monkeypatch: pytest.MonkeyPatch, ndjson_path: Path
) -> None:
    from tools.evidence_gather_support import acp as acp_mod

    monkeypatch.setattr(acp_mod, "resolve_acpx", lambda: (r"C:\tools\acpx.exe", "acpx 0.1.0"))

    def fake_spawn(*, command, cwd, env, timeout_seconds):
        del command, cwd, env, timeout_seconds
        entry = _prompt_entry()
        exit_event = _exit_event()
        with ndjson_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
            handle.write(json.dumps(exit_event, separators=(",", ":")) + "\n")
        return 0

    monkeypatch.setattr(acp_mod, "spawn_acpx", fake_spawn)
    monkeypatch.setattr(
        acp_mod,
        "build_acpx_command",
        lambda **kwargs: ["acpx", "--format", "json", "exec", "ping"],
    )


def test_zed_crash_collector_is_registered() -> None:
    from tools.evidence_gather_support.registry import build_registry

    registry = build_registry()
    assert "zed_crash_collector" in registry.collectors


def test_zed_log_root_missing_is_content_free_host_error(tmp_path: Path) -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod
    from tools.evidence_gather_support.common import HostError

    missing = (tmp_path / "absent-logs").resolve()
    with pytest.raises(HostError) as exc_info:
        zed_mod.require_zed_log_root(missing)
    assert exc_info.value.code == "zed_log_root_missing"


def test_zed_log_root_mismatch_rejects_non_localappdata(tmp_path: Path) -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod
    from tools.evidence_gather_support.common import HostError

    fake_root = (tmp_path / "Zed" / "logs").resolve()
    fake_root.mkdir(parents=True)
    expected = (tmp_path / "expected" / "Zed" / "logs").resolve()
    expected.mkdir(parents=True)
    with pytest.raises(HostError) as exc_info:
        zed_mod.require_zed_log_root(fake_root, expected_live_root=expected)
    assert exc_info.value.code == "zed_log_root_mismatch"


def test_zed_crash_version_mismatch_rejects_unsupported_client() -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod
    from tools.evidence_gather_support.common import HostError

    with pytest.raises(HostError) as exc_info:
        zed_mod.require_supported_client_identity("zed-9.9.9", reported_version="Zed 9.9.9")
    assert exc_info.value.code == "zed_version_mismatch"


def test_zed_crash_version_rejects_prefix_substring_false_friend() -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod
    from tools.evidence_gather_support.common import HostError

    with pytest.raises(HostError) as exc_info:
        zed_mod.require_supported_client_identity(
            "zed-1.13.1",
            reported_version="Zed 1.13.10 aabbccdd",
        )
    assert exc_info.value.code == "zed_version_mismatch"
    zed_mod.require_supported_client_identity(
        "zed-1.13.1",
        reported_version="Zed 1.13.1 00bd72e7838f4b875a913cd112b47a0ebe1ca62b",
    )


def test_zed_crash_pre_run_snapshot_excludes_existing_artifacts(tmp_path: Path) -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod

    root = (tmp_path / "logs").resolve()
    root.mkdir()
    preexisting = root / "already.dmp"
    preexisting.write_bytes(_minidump_header() + b"old")
    snap = zed_mod.snapshot_log_root(root, monotonic_ns=100, wall_clock="1970-01-01T00:00:01Z")
    candidates = zed_mod.list_new_or_changed(snap, root)
    assert candidates == ()
    assert any(record.name == "already.dmp" for record in snap.records)


def test_zed_crash_new_and_changed_identity_are_candidates(tmp_path: Path) -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod

    root = (tmp_path / "logs").resolve()
    root.mkdir()
    rolling = root / "Zed.log"
    rolling.write_text("pre\n", encoding="utf-8")
    snap = zed_mod.snapshot_log_root(root, monotonic_ns=100, wall_clock="1970-01-01T00:00:01Z")
    rolling.write_text("pre\npost\n", encoding="utf-8")
    dump = root / "crash.dmp"
    dump.write_bytes(_minidump_header() + b"new")
    candidates = zed_mod.list_new_or_changed(snap, root)
    names = {item.name for item in candidates}
    assert names == {"Zed.log", "crash.dmp"}


def test_zed_log_versus_dump_roles_are_distinct(tmp_path: Path) -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod

    assert zed_mod.classify_artifact_role("Zed.log", b"hello") == "zed_log"
    assert zed_mod.classify_artifact_role("crash.dmp", _minidump_header()) == "zed_process_dump"
    assert (
        zed_mod.classify_artifact_role("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.json", b'{"panic":true}')
        == "zed_panic_json"
    )


def test_zed_crash_timestamp_bounds_are_recorded(tmp_path: Path) -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod

    root = (tmp_path / "logs").resolve()
    root.mkdir()
    snap = zed_mod.snapshot_log_root(root, monotonic_ns=1_000, wall_clock="1970-01-01T00:00:01Z")
    (root / "new.dmp").write_bytes(_minidump_header())
    batch = zed_mod.build_collection_batch(
        scenario_id="zed-session",
        run_id="run-1",
        monotonic_origin_ns=0,
        snapshot=snap,
        candidates=zed_mod.list_new_or_changed(snap, root),
        digests={"new.dmp": "a" * 64},
        process_pids=(4242,),
        watch_started_ns=1_000,
        watch_ended_ns=2_000,
        wall_started="1970-01-01T00:00:01Z",
        wall_ended="1970-01-01T00:00:02Z",
    )
    assert batch.collector_id == "zed_crash_collector"
    assert batch.observations
    obs = batch.observations[0]
    assert obs.monotonic_offset_ns >= 1_000
    corr = dict(obs.correlation)
    assert corr["watch_started_ns"] == "1000"
    assert corr["watch_ended_ns"] == "2000"
    assert corr["wall_started"] == "1970-01-01T00:00:01Z"
    assert corr["wall_ended"] == "1970-01-01T00:00:02Z"


def test_zed_crash_process_identity_is_correlated(tmp_path: Path) -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod

    zed_mod.correlate_zed_processes(expected_pids=(100,), observed_pids=(100,))
    batch_corr = zed_mod.process_correlation_fields(expected_pids=(100,), observed_pids=(100,))
    assert ("pid", "100") in batch_corr


def test_zed_crash_collect_discovers_observed_pids_independently(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    gather = _gather()
    capture, workspace, agent, ndjson_path = _prepare_collect_workspace(tmp_path)
    log_root = (tmp_path / "Zed" / "logs").resolve()
    log_root.mkdir(parents=True)

    assert (
        gather.main(
            [
                "prepare",
                "--scenario",
                str(FIXTURE.resolve()),
                "--capture-root",
                str(capture),
                "--bind",
                "model=operator-supplied",
            ]
        )
        == 0
    )
    _stub_acp_for_collect(monkeypatch, ndjson_path)

    from tools.evidence_gather_support import acp as acp_mod
    from tools.evidence_gather_support import zed_logs as zed_mod

    seen: dict[str, object] = {}

    def fake_spawn(*, command, cwd, env, timeout_seconds):
        del command, cwd, env, timeout_seconds
        entry = _prompt_entry()
        exit_event = _exit_event()
        with ndjson_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
            handle.write(json.dumps(exit_event, separators=(",", ":")) + "\n")
        (log_root / "post-run.dmp").write_bytes(_minidump_header() + b"post")
        return 0

    def fake_discover() -> tuple[int, ...]:
        seen["discover_called"] = True
        return (4242, 9999)

    monkeypatch.setattr(acp_mod, "spawn_acpx", fake_spawn)
    monkeypatch.setattr(zed_mod, "discover_zed_editor_pids", fake_discover)

    code = gather.main(
        [
            "collect",
            "--scenario",
            str(FIXTURE.resolve()),
            "--capture-root",
            str(capture),
            "--bind",
            "model=operator-supplied",
            "--workspace-root",
            str(workspace),
            "--agent-executable",
            str(agent),
            "--prompt",
            "ping",
            "--timeout-seconds",
            "30",
            "--ndjson-path",
            str(ndjson_path.resolve()),
            "--correlate-session-id",
            "session-aaa",
            "--correlate-request-id",
            "req-1",
            "--correlate-run-id",
            "session-aaa:req-1",
            "--debug-session-id",
            "debug_abc",
            "--zed-log-root",
            str(log_root),
            "--zed-client-identity",
            "zed-1.13.1",
            "--zed-version",
            "Zed 1.13.1 deadbeef",
            "--zed-watch-seconds",
            "1",
            "--zed-pid",
            "4242",
        ]
    )
    err = capsys.readouterr().err
    assert seen.get("discover_called") is True
    assert "zed_multi_instance_ambiguous" in err
    assert code == 2


def test_zed_crash_multiple_instances_are_ambiguous() -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod
    from tools.evidence_gather_support.common import HostError

    with pytest.raises(HostError) as exc_info:
        zed_mod.correlate_zed_processes(expected_pids=(), observed_pids=(1, 2))
    assert exc_info.value.code == "zed_multi_instance_ambiguous"


def test_zed_crash_expected_plus_extra_instance_is_ambiguous() -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod
    from tools.evidence_gather_support.common import HostError

    with pytest.raises(HostError) as exc_info:
        zed_mod.correlate_zed_processes(expected_pids=(100,), observed_pids=(100, 200))
    assert exc_info.value.code == "zed_multi_instance_ambiguous"


def test_zed_crash_unrelated_process_is_rejected() -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod
    from tools.evidence_gather_support.common import HostError

    with pytest.raises(HostError) as exc_info:
        zed_mod.correlate_zed_processes(expected_pids=(100,), observed_pids=(200,))
    assert exc_info.value.code == "zed_unrelated_process"


def test_zed_crash_process_lookup_failure_is_not_a_crash_claim() -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod
    from tools.evidence_gather_support.common import HostError

    with pytest.raises(HostError) as exc_info:
        zed_mod.correlate_zed_processes(expected_pids=(100,), observed_pids=())
    assert exc_info.value.code == "zed_process_lookup_failed"
    assert exc_info.value.code != "client_crash_observed"


def test_zed_crash_clock_ambiguity_is_content_free_failure() -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod
    from tools.evidence_gather_support.common import HostError

    with pytest.raises(HostError) as exc_info:
        zed_mod.require_ordered_watch_window(
            watch_started_ns=2_000,
            watch_ended_ns=1_000,
            wall_started="1970-01-01T00:00:02Z",
            wall_ended="1970-01-01T00:00:01Z",
        )
    assert exc_info.value.code == "zed_clock_ambiguous"


def test_zed_crash_watcher_timeout_is_content_free_failure(tmp_path: Path) -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod
    from tools.evidence_gather_support.common import HostError

    root = (tmp_path / "logs").resolve()
    root.mkdir()
    snap = zed_mod.snapshot_log_root(root, monotonic_ns=100, wall_clock="1970-01-01T00:00:01Z")
    ticks = {"n": 0}

    def fake_monotonic() -> float:
        ticks["n"] += 1
        return 0.0 if ticks["n"] < 3 else 1.0

    with pytest.raises(HostError) as exc_info:
        zed_mod.watch_log_root(
            snap,
            watch_seconds=0.5,
            poll_interval_seconds=0.001,
            sleep=lambda _seconds: None,
            monotonic=fake_monotonic,
        )
    assert exc_info.value.code == "zed_watch_timeout"


def test_zed_crash_changed_file_during_hash_is_raced(tmp_path: Path) -> None:
    from tools.evidence_gather_support import zed_logs as zed_mod
    from tools.evidence_gather_support.common import HostError

    root = (tmp_path / "logs").resolve()
    root.mkdir()
    path = root / "growing.dmp"
    path.write_bytes(_minidump_header() + b"a")
    record = zed_mod.file_record_for(path)
    path.write_bytes(_minidump_header() + b"ab")
    with pytest.raises(HostError) as exc_info:
        zed_mod.digest_stable(path, expected=record)
    assert exc_info.value.code == "zed_hash_raced"


def test_zed_crash_collect_through_entry_point_excludes_pre_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    gather = _gather()
    capture, workspace, agent, ndjson_path = _prepare_collect_workspace(tmp_path)
    log_root = (tmp_path / "Zed" / "logs").resolve()
    log_root.mkdir(parents=True)
    pre = log_root / "pre-run.dmp"
    pre.write_bytes(_minidump_header() + b"pre")

    assert (
        gather.main(
            [
                "prepare",
                "--scenario",
                str(FIXTURE.resolve()),
                "--capture-root",
                str(capture),
                "--bind",
                "model=operator-supplied",
            ]
        )
        == 0
    )
    _stub_acp_for_collect(monkeypatch, ndjson_path)

    def after_spawn(*, command, cwd, env, timeout_seconds):
        from tools.evidence_gather_support import acp as acp_mod

        # Re-use stub body then create a post-start dump.
        code = 0
        entry = _prompt_entry()
        exit_event = _exit_event()
        with ndjson_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
            handle.write(json.dumps(exit_event, separators=(",", ":")) + "\n")
        (log_root / "post-run.dmp").write_bytes(_minidump_header() + b"post")
        del command, cwd, env, timeout_seconds, acp_mod
        return code

    from tools.evidence_gather_support import acp as acp_mod
    from tools.evidence_gather_support import zed_logs as zed_mod

    monkeypatch.setattr(acp_mod, "spawn_acpx", after_spawn)
    monkeypatch.setattr(zed_mod, "discover_zed_editor_pids", lambda: (4242,))

    code = gather.main(
        [
            "collect",
            "--scenario",
            str(FIXTURE.resolve()),
            "--capture-root",
            str(capture),
            "--bind",
            "model=operator-supplied",
            "--workspace-root",
            str(workspace),
            "--agent-executable",
            str(agent),
            "--prompt",
            "ping",
            "--timeout-seconds",
            "30",
            "--ndjson-path",
            str(ndjson_path.resolve()),
            "--correlate-session-id",
            "session-aaa",
            "--correlate-request-id",
            "req-1",
            "--correlate-run-id",
            "session-aaa:req-1",
            "--debug-session-id",
            "debug_abc",
            "--zed-log-root",
            str(log_root),
            "--zed-client-identity",
            "zed-1.13.1",
            "--zed-version",
            "Zed 1.13.1 deadbeef",
            "--zed-watch-seconds",
            "1",
            "--zed-pid",
            "4242",
        ]
    )
    err = capsys.readouterr().err
    assert "stage_unavailable" not in err
    assert code == 0

    run_dirs = [path for path in capture.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    raw = json.loads((run_dirs[0] / "raw-bundle.json").read_text(encoding="utf-8"))
    zed_batches = [batch for batch in raw["batches"] if batch["collector_id"] == "zed_crash_collector"]
    assert len(zed_batches) == 1
    artifact_roles = {item["role"] for item in zed_batches[0]["artifacts"]}
    assert "zed_process_dump" in artifact_roles
    relative_names = {Path(item["relative_locator"]).name for item in zed_batches[0]["artifacts"]}
    assert "post-run.dmp" in relative_names
    assert "pre-run.dmp" not in relative_names
    # Collector emits observations/artifacts only — never a crash claim.
    assert all(
        obs.get("observation_kind") != "client_crash_observed" for obs in zed_batches[0]["observations"]
    )
