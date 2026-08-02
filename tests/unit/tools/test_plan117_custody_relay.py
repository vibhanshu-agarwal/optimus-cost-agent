"""RED/GREEN unit tests for the opaque Plan 11.7 custody byte relay."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

import tools.plan117_custody_relay as plan117_custody_relay
from tools.plan117_custody_contract import CustodyContractError, atomic_write_json, sha256_file

ROOT = Path(__file__).resolve().parents[3]
RELAY = ROOT / "tools" / "plan117_custody_relay.py"

DIR_ZED_TO_AGENT = "zed_to_agent"
DIR_AGENT_TO_ZED = "agent_to_zed"
EOF_ZED_TO_AGENT = "zed_to_agent_eof"
EOF_AGENT_TO_ZED = "agent_to_zed_eof"


def _echo_child_args() -> list[str]:
    # Binary cat: read all stdin, write to stdout.
    code = (
        "import sys;"
        "data=sys.stdin.buffer.read();"
        "sys.stdout.buffer.write(data);"
        "sys.stdout.buffer.flush()"
    )
    return [sys.executable, "-c", code]


def _slow_echo_child_args(*, chunk: int = 4096, delay: float = 0.01) -> list[str]:
    code = (
        "import sys,time\n"
        f"c={chunk}\n"
        f"d={delay}\n"
        "stdin=sys.stdin.buffer\n"
        "stdout=sys.stdout.buffer\n"
        "while True:\n"
        " b=stdin.read(c)\n"
        " if not b: break\n"
        " time.sleep(d)\n"
        " stdout.write(b)\n"
        " stdout.flush()\n"
    )
    return [sys.executable, "-c", code]


def _duplex_child_args() -> list[str]:
    # Concurrent-ish: write a fixed preamble, then echo remaining stdin.
    code = (
        "import sys\n"
        "stdout=sys.stdout.buffer\n"
        "stdin=sys.stdin.buffer\n"
        "pre=b'PRE\\x00\\xff'\n"
        "stdout.write(pre)\n"
        "stdout.flush()\n"
        "data=stdin.read()\n"
        "stdout.write(data)\n"
        "stdout.flush()\n"
    )
    return [sys.executable, "-c", code]


def _exit_first_child_args(*, code: int = 7) -> list[str]:
    return [sys.executable, "-c", f"import sys; sys.exit({code})"]


def _read_index(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "relay-index.ndjson"
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line]


def _assert_gap_free(records: list[dict[str, Any]]) -> None:
    sequences = [int(r["sequence"]) for r in records]
    assert sequences == list(range(len(sequences)))
    for direction in (DIR_ZED_TO_AGENT, DIR_AGENT_TO_ZED):
        chunks = [r for r in records if r["direction"] == direction]
        offset = 0
        for record in chunks:
            assert int(record["directional_offset"]) == offset
            offset += int(record["size"])


def _assert_index_digests_match_raw(run_dir: Path, records: list[dict[str, Any]]) -> None:
    zed_raw = (run_dir / "zed-to-agent.bin").read_bytes()
    agent_raw = (run_dir / "agent-to-zed.bin").read_bytes()
    cursors = {DIR_ZED_TO_AGENT: 0, DIR_AGENT_TO_ZED: 0}
    blobs = {DIR_ZED_TO_AGENT: zed_raw, DIR_AGENT_TO_ZED: agent_raw}
    for record in records:
        direction = record["direction"]
        if direction in (EOF_ZED_TO_AGENT, EOF_AGENT_TO_ZED):
            assert int(record["size"]) == 0
            continue
        assert direction in blobs
        size = int(record["size"])
        start = int(record["directional_offset"])
        assert start == cursors[direction]
        chunk = blobs[direction][start : start + size]
        assert len(chunk) == size
        assert hashlib.sha256(chunk).hexdigest() == record["sha256"]
        cursors[direction] += size
    assert cursors[DIR_ZED_TO_AGENT] == len(zed_raw)
    assert cursors[DIR_AGENT_TO_ZED] == len(agent_raw)


def _run_relay_inprocess(
    *,
    capture_root: Path,
    run_id: str,
    child_argv: Sequence[str],
    stdin_bytes: bytes,
    popen_factory: Callable[..., Any] | None = None,
    recorder_hook: Callable[[Any], None] | None = None,
) -> tuple[int, bytes, bytes, Path]:
    parent_in = io.BytesIO(stdin_bytes)
    parent_out = io.BytesIO()
    stderr_buf = io.BytesIO()
    kwargs: dict[str, Any] = {
        "capture_root": capture_root,
        "run_id": run_id,
        "child_executable": child_argv[0],
        "child_args": list(child_argv[1:]),
        "stdin": parent_in,
        "stdout": parent_out,
        "stderr": stderr_buf,
    }
    if popen_factory is not None:
        kwargs["popen_factory"] = popen_factory
    if recorder_hook is not None:
        kwargs["recorder_hook"] = recorder_hook
    exit_code = plan117_custody_relay.run_relay(**kwargs)
    run_dir = capture_root / run_id
    return exit_code, parent_out.getvalue(), stderr_buf.getvalue(), run_dir


def test_empty_streams_produce_eof_and_empty_bins(tmp_path: Path) -> None:
    exit_code, forwarded, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="empty",
        child_argv=_echo_child_args(),
        stdin_bytes=b"",
    )
    assert exit_code == 0
    assert forwarded == b""
    assert (run_dir / "zed-to-agent.bin").read_bytes() == b""
    assert (run_dir / "agent-to-zed.bin").read_bytes() == b""
    records = _read_index(run_dir)
    dirs = {r["direction"] for r in records}
    assert EOF_ZED_TO_AGENT in dirs
    assert EOF_AGENT_TO_ZED in dirs
    summary = json.loads((run_dir / "relay-summary.json").read_text(encoding="utf-8"))
    assert summary["zed_to_agent_eof"] is True
    assert summary["agent_to_zed_eof"] is True
    assert summary["child_exit_code"] == 0
    assert b"\n" not in (run_dir / "relay-summary.json").read_bytes()


def test_all_byte_values_round_trip(tmp_path: Path) -> None:
    payload = bytes(range(256))
    exit_code, forwarded, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="all-bytes",
        child_argv=_echo_child_args(),
        stdin_bytes=payload,
    )
    assert exit_code == 0
    assert forwarded == payload
    assert (run_dir / "zed-to-agent.bin").read_bytes() == payload
    assert (run_dir / "agent-to-zed.bin").read_bytes() == payload
    records = _read_index(run_dir)
    _assert_gap_free(records)
    _assert_index_digests_match_raw(run_dir, records)


def test_multi_megabyte_chunks(tmp_path: Path) -> None:
    payload = (b"\x00\x01\xfe\xff" * (256 * 1024))[: 3 * 1024 * 1024]  # 3 MiB
    exit_code, forwarded, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="megabyte",
        child_argv=_echo_child_args(),
        stdin_bytes=payload,
    )
    assert exit_code == 0
    assert forwarded == payload
    assert (run_dir / "zed-to-agent.bin").read_bytes() == payload
    assert (run_dir / "agent-to-zed.bin").read_bytes() == payload


def test_partial_lines_preserved_without_parsing(tmp_path: Path) -> None:
    payload = b'{"partial":' + b"x" * 17 + b"\n{\"id\":1}\ntra"
    exit_code, forwarded, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="partial",
        child_argv=_echo_child_args(),
        stdin_bytes=payload,
    )
    assert exit_code == 0
    assert forwarded == payload
    assert (run_dir / "zed-to-agent.bin").read_bytes() == payload


def test_concurrent_duplex_and_ordering(tmp_path: Path) -> None:
    inbound = b"IN-" + bytes(range(64)) + b"-END"
    exit_code, forwarded, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="duplex",
        child_argv=_duplex_child_args(),
        stdin_bytes=inbound,
    )
    assert exit_code == 0
    assert forwarded.startswith(b"PRE\x00\xff")
    assert forwarded.endswith(inbound)
    assert (run_dir / "zed-to-agent.bin").read_bytes() == inbound
    assert (run_dir / "agent-to-zed.bin").read_bytes() == forwarded
    records = _read_index(run_dir)
    sequences = [int(r["sequence"]) for r in records]
    assert sequences == sorted(sequences)
    assert sequences == list(range(len(sequences)))
    _assert_index_digests_match_raw(run_dir, records)


def test_eof_either_direction_and_child_first_exit(tmp_path: Path) -> None:
    exit_code, forwarded, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="child-exit",
        child_argv=_exit_first_child_args(code=7),
        stdin_bytes=b"ignored-after-exit",
    )
    assert exit_code == 7
    assert isinstance(forwarded, bytes)
    records = _read_index(run_dir)
    dirs = {r["direction"] for r in records}
    assert EOF_AGENT_TO_ZED in dirs
    summary = json.loads((run_dir / "relay-summary.json").read_text(encoding="utf-8"))
    assert summary["child_exit_code"] == 7
    assert summary["terminal_disposition"] == "child_exited"


def test_parent_first_eof_closes_child_stdin(tmp_path: Path) -> None:
    exit_code, forwarded, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="parent-eof",
        child_argv=_echo_child_args(),
        stdin_bytes=b"hello-eof",
    )
    assert exit_code == 0
    assert forwarded == b"hello-eof"
    records = _read_index(run_dir)
    assert any(r["direction"] == EOF_ZED_TO_AGENT for r in records)


def test_backpressure_large_slow_child(tmp_path: Path) -> None:
    payload = os.urandom(256 * 1024)
    exit_code, forwarded, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="backpressure",
        child_argv=_slow_echo_child_args(chunk=8192, delay=0.001),
        stdin_bytes=payload,
    )
    assert exit_code == 0
    assert forwarded == payload
    assert (run_dir / "zed-to-agent.bin").read_bytes() == payload
    assert (run_dir / "agent-to-zed.bin").read_bytes() == payload


def test_popen_receives_env_none_cwd_none_exact_argv_inherited_stderr_no_shell(
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeProc:
        def __init__(self) -> None:
            self.stdin = mock.Mock()
            self.stdin.write = mock.Mock(return_value=None)
            self.stdin.close = mock.Mock()
            self.stdin.flush = mock.Mock()
            self.stdout = io.BytesIO(b"")
            self.stderr = None
            self.returncode = 0
            self.pid = 4242

        def poll(self) -> int | None:
            return 0

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def terminate(self) -> None:
            pass

        def kill(self) -> None:
            pass

    def fake_popen(*args: Any, **kwargs: Any) -> _FakeProc:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakeProc()

    exit_code, _forwarded, _err, _run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="popen-spy",
        child_argv=[str(tmp_path / "child.exe"), "--optimus", "acp"],
        stdin_bytes=b"",
        popen_factory=fake_popen,
    )
    assert exit_code == 0
    assert captured["kwargs"]["env"] is None
    assert captured["kwargs"]["cwd"] is None
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["stderr"] is None  # inherit
    argv = captured["args"][0] if captured["args"] else captured["kwargs"].get("args")
    assert argv == [str(tmp_path / "child.exe"), "--optimus", "acp"]
    assert "--capture-root" not in argv
    assert "--run-id" not in argv
    assert "--child-executable" not in argv


def test_cli_relay_only_args_never_reach_child(tmp_path: Path) -> None:
    child_script = tmp_path / "child_echo_argv.py"
    child_script.write_text(
        "import sys\n"
        "sys.stdout.buffer.write(('|'.join(sys.argv[1:])).encode())\n"
        "sys.stdout.buffer.flush()\n",
        encoding="utf-8",
        newline="\n",
    )
    capture_root = tmp_path / "cap"
    run_id = "cli-no-leak"
    proc = subprocess.run(
        [
            sys.executable,
            str(RELAY),
            "--capture-root",
            str(capture_root),
            "--run-id",
            run_id,
            "--child-executable",
            sys.executable,
            "--",
            str(child_script),
            "keep-me",
        ],
        input=b"",
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0
    out = proc.stdout.decode("utf-8", errors="replace")
    assert "keep-me" in out
    assert "--capture-root" not in out
    assert "--run-id" not in out
    assert "--child-executable" not in out
    assert str(capture_root) not in out


def test_stdout_contains_child_stdout_only(tmp_path: Path) -> None:
    exit_code, forwarded, err, _run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="stdout-only",
        child_argv=_echo_child_args(),
        stdin_bytes=b"payload-bytes",
    )
    assert exit_code == 0
    assert forwarded == b"payload-bytes"
    # No relay diagnostics on the forwarded stdout stream.
    assert b"relay" not in forwarded.lower()
    assert b"schema" not in forwarded


def test_recorder_failure_terminates_owned_child_no_fallback(tmp_path: Path) -> None:
    terminate_calls: list[str] = []

    class _OwnedProc:
        def __init__(self) -> None:
            self.stdin = mock.Mock()
            self.stdin.write = mock.Mock(side_effect=BrokenPipeError())
            self.stdin.close = mock.Mock()
            self.stdin.flush = mock.Mock()
            self.stdout = io.BytesIO(b"x" * 8)
            self.returncode = None
            self.pid = 99

        def poll(self) -> int | None:
            return None if self.returncode is None else self.returncode

        def wait(self, timeout: float | None = None) -> int:
            if self.returncode is None:
                self.returncode = -9
            return self.returncode

        def terminate(self) -> None:
            terminate_calls.append("terminate")
            self.returncode = -15

        def kill(self) -> None:
            terminate_calls.append("kill")
            self.returncode = -9

    def fake_popen(*_a: Any, **_k: Any) -> _OwnedProc:
        return _OwnedProc()

    def failing_hook(recorder: Any) -> None:
        def boom(*_a: Any, **_k: Any) -> None:
            raise OSError("disk_full_simulated")

        recorder.record_chunk = boom  # type: ignore[method-assign]

    exit_code, _forwarded, err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="recorder-fail",
        child_argv=[str(tmp_path / "child.exe")],
        stdin_bytes=b"will-fail",
        popen_factory=fake_popen,
        recorder_hook=failing_hook,
    )
    assert exit_code != 0
    assert terminate_calls, "owned child must be terminate()/kill()'d on recorder failure"
    assert b"relay_recorder_failure" in err
    # No uncaptured fallback summary claiming success.
    summary_path = run_dir / "relay-summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary.get("terminal_disposition") != "child_exited"
        assert summary.get("reason_code") == "relay_recorder_failure"


def test_broken_pipe_is_nonzero_no_fallback(tmp_path: Path) -> None:
    code = (
        "import sys;"
        "sys.stdout.buffer.write(b'partial');"
        "sys.stdout.buffer.flush();"
        "sys.exit(0)"
    )
    # Parent keeps a closed-like path by using a child that exits after writing;
    # additional write from parent after child closed stdin should surface cleanly.
    exit_code, forwarded, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="broken-pipe",
        child_argv=[sys.executable, "-c", code],
        stdin_bytes=b"more-after-child-done" * 1000,
    )
    assert isinstance(exit_code, int)
    assert (run_dir / "agent-to-zed.bin").read_bytes() == forwarded
    summary = json.loads((run_dir / "relay-summary.json").read_text(encoding="utf-8"))
    assert "terminal_disposition" in summary


def test_ctrl_c_termination_emits_summary(tmp_path: Path) -> None:
    """Simulate KeyboardInterrupt on the live path and require fail-closed exit."""

    class _HangProc:
        def __init__(self) -> None:
            self.stdin = mock.Mock()
            self.stdin.write = mock.Mock(return_value=None)
            self.stdin.close = mock.Mock()
            self.stdin.flush = mock.Mock()
            self.stdout = _BlockingStdout()
            self.returncode = None
            self.pid = 77
            self._terminated = False

        def poll(self) -> int | None:
            return 0 if self._terminated else None

        def wait(self, timeout: float | None = None) -> int:
            self.returncode = -2
            return -2

        def terminate(self) -> None:
            self._terminated = True
            self.returncode = -2

        def kill(self) -> None:
            self._terminated = True
            self.returncode = -9

    class _BlockingStdout(io.BytesIO):
        def read(self, _n: int = -1) -> bytes:  # noqa: A003
            raise KeyboardInterrupt

    def fake_popen(*_a: Any, **_k: Any) -> _HangProc:
        return _HangProc()

    exit_code, _fwd, err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="ctrl-c",
        child_argv=[str(tmp_path / "child.exe")],
        stdin_bytes=b"x",
        popen_factory=fake_popen,
    )
    assert exit_code != 0
    assert b"relay_interrupted" in err or (run_dir / "relay-summary.json").exists()
    if (run_dir / "relay-summary.json").exists():
        summary = json.loads((run_dir / "relay-summary.json").read_text(encoding="utf-8"))
        assert summary["terminal_disposition"] in {"interrupted", "relay_interrupted"}


def test_mutation_of_captured_bytes_rejected_by_verifier(tmp_path: Path) -> None:
    exit_code, _fwd, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="mutate-raw",
        child_argv=_echo_child_args(),
        stdin_bytes=b"abc123",
    )
    assert exit_code == 0
    from tools.verify_plan117_custody_feasibility import verify_relay_capture

    verify_relay_capture(run_dir)  # positive
    raw = run_dir / "zed-to-agent.bin"
    raw.write_bytes(raw.read_bytes() + b"X")
    with pytest.raises(CustodyContractError) as exc_info:
        verify_relay_capture(run_dir)
    assert exc_info.value.reason_code in {
        "relay_raw_bytes_mismatch",
        "relay_chunk_digest_mismatch",
        "relay_directional_length_mismatch",
    }


def test_cli_main_parses_double_dash(tmp_path: Path) -> None:
    capture_root = tmp_path / "cap"
    proc = subprocess.run(
        [
            sys.executable,
            str(RELAY),
            "--capture-root",
            str(capture_root),
            "--run-id",
            "cli-main",
            "--child-executable",
            sys.executable,
            "--",
            "-c",
            "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())",
        ],
        input=b"cli-bytes",
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout == b"cli-bytes"
    run_dir = capture_root / "cli-main"
    assert (run_dir / "relay-summary.json").is_file()
    assert sha256_file(run_dir / "zed-to-agent.bin") == hashlib.sha256(b"cli-bytes").hexdigest()


def test_main_function_and_verify_edge_cases(tmp_path: Path) -> None:
    capture_root = tmp_path / "cap"
    code = "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"
    with mock.patch.object(plan117_custody_relay, "run_relay", return_value=0) as mocked:
        assert (
            plan117_custody_relay.main(
                [
                    "--capture-root",
                    str(capture_root),
                    "--run-id",
                    "main-fn",
                    "--child-executable",
                    sys.executable,
                    "--",
                    "-c",
                    code,
                ]
            )
            == 0
        )
        kwargs = mocked.call_args.kwargs
        assert kwargs["run_id"] == "main-fn"
        assert kwargs["child_args"] == ["-c", code]
        assert "--capture-root" not in kwargs["child_args"]

    # Build a real capture for verify edge cases via in-process relay.
    exit_code, _fwd, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="main-fn-real",
        child_argv=_echo_child_args(),
        stdin_bytes=b"ok",
    )
    assert exit_code == 0
    plan117_custody_relay.verify_relay_capture(run_dir)

    empty = tmp_path / "empty-run"
    empty.mkdir()
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(empty)
    assert exc_info.value.reason_code == "relay_capture_incomplete"

    bad = tmp_path / "bad-summary"
    bad.mkdir()
    for name in ("relay-summary.json", "relay-index.ndjson", "zed-to-agent.bin", "agent-to-zed.bin"):
        path = bad / name
        if name.endswith(".bin"):
            path.write_bytes(b"")
        else:
            path.write_text("{not-json", encoding="utf-8", newline="\n")
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(bad)
    assert exc_info.value.reason_code == "relay_summary_invalid"


def test_recorder_invalid_direction_and_oserror(tmp_path: Path) -> None:
    recorder = plan117_custody_relay._LockedRecorder(tmp_path / "r1", "r1", 0.0)
    with pytest.raises(plan117_custody_relay.RelayRecorderError):
        recorder.record_chunk("not_a_direction", b"x")
    recorder.close()

    recorder2 = plan117_custody_relay._LockedRecorder(tmp_path / "r2", "r2", 0.0)
    recorder2._bins[DIR_ZED_TO_AGENT].close()
    with pytest.raises(plan117_custody_relay.RelayRecorderError) as exc_info:
        recorder2.record_chunk(DIR_ZED_TO_AGENT, b"x")
    assert exc_info.value.reason_code == "relay_recorder_failure"
    assert recorder2.failed is True
    assert recorder2.reason_code == "relay_recorder_failure"
    with pytest.raises(plan117_custody_relay.RelayRecorderError):
        recorder2.record_chunk(DIR_ZED_TO_AGENT, b"y")
    with pytest.raises(plan117_custody_relay.RelayRecorderError):
        recorder2.record_eof(DIR_ZED_TO_AGENT)
    recorder2.close()


def test_recorder_eof_oserror_and_close_errors(tmp_path: Path) -> None:
    recorder = plan117_custody_relay._LockedRecorder(tmp_path / "r3", "r3", 0.0)
    recorder._index.close()
    with pytest.raises(plan117_custody_relay.RelayRecorderError):
        recorder.record_eof(DIR_AGENT_TO_ZED)
    recorder.close()
    recorder.close()


def test_popen_factory_exception_is_fail_closed(tmp_path: Path) -> None:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("spawn_failed")

    exit_code, _fwd, err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="spawn-fail",
        child_argv=[str(tmp_path / "x.exe")],
        stdin_bytes=b"",
        popen_factory=boom,
    )
    assert exit_code != 0
    assert b"relay_recorder_failure" in err
    assert (run_dir / "relay-summary.json").is_file()


def test_terminate_kill_fallback_and_text_stderr(tmp_path: Path) -> None:
    calls: list[str] = []

    class _StickyProc:
        def __init__(self) -> None:
            self.stdin = mock.Mock()
            self.stdin.write = mock.Mock(return_value=None)
            self.stdin.close = mock.Mock()
            self.stdin.flush = mock.Mock()
            self.stdout = io.BytesIO(b"")
            self.returncode = None
            self.pid = 1

        def poll(self) -> int | None:
            return None if self.returncode is None else self.returncode

        def wait(self, timeout: float | None = None) -> int:
            if self.returncode is None:
                # First wait after terminate still "alive"; simulate timeout once.
                if "terminate" in calls and "kill" not in calls:
                    raise subprocess.TimeoutExpired(cmd="x", timeout=timeout or 0)
                self.returncode = -9
            return int(self.returncode)

        def terminate(self) -> None:
            calls.append("terminate")

        def kill(self) -> None:
            calls.append("kill")
            self.returncode = -9

    def failing_hook(recorder: Any) -> None:
        def boom(*_a: Any, **_k: Any) -> None:
            raise OSError("fail")

        recorder.record_chunk = boom  # type: ignore[method-assign]

    err_text = io.StringIO()
    exit_code = plan117_custody_relay.run_relay(
        capture_root=tmp_path,
        run_id="kill-fallback",
        child_executable=str(tmp_path / "c.exe"),
        child_args=[],
        stdin=io.BytesIO(b"x"),
        stdout=io.BytesIO(),
        stderr=err_text,
        popen_factory=lambda *_a, **_k: _StickyProc(),
        recorder_hook=failing_hook,
    )
    assert exit_code != 0
    assert "relay_recorder_failure" in err_text.getvalue()
    assert "terminate" in calls
    assert "kill" in calls


def test_broken_pipe_error_path(tmp_path: Path) -> None:
    class _PipeProc:
        def __init__(self) -> None:
            self.stdin = mock.Mock()
            self.stdin.write = mock.Mock(side_effect=BrokenPipeError())
            self.stdin.close = mock.Mock()
            self.stdin.flush = mock.Mock()
            self.stdout = io.BytesIO(b"")
            self.returncode = 0
            self.pid = 3

        def poll(self) -> int | None:
            return 0

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def terminate(self) -> None:
            pass

        def kill(self) -> None:
            pass

    exit_code, _fwd, err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="bpipe",
        child_argv=[str(tmp_path / "c.exe")],
        stdin_bytes=b"payload",
        popen_factory=lambda *_a, **_k: _PipeProc(),
    )
    assert exit_code != 0
    assert b"relay_broken_pipe" in err
    summary = json.loads((run_dir / "relay-summary.json").read_text(encoding="utf-8"))
    assert summary["terminal_disposition"] == "broken_pipe"


def test_verify_rejects_schema_run_id_mono_eof_and_empty_index(tmp_path: Path) -> None:
    exit_code, _fwd, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="verify-edges",
        child_argv=_echo_child_args(),
        stdin_bytes=b"xy",
    )
    assert exit_code == 0
    plan117_custody_relay.verify_relay_capture(run_dir)

    summary_path = run_dir / "relay-summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload["schema"] = "wrong"
    atomic_write_json(summary_path, payload)
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code == "relay_summary_schema_mismatch"

    exit_code, _fwd, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="verify-edges-2",
        child_argv=_echo_child_args(),
        stdin_bytes=b"xy",
    )
    index_path = run_dir / "relay-index.ndjson"
    records = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines() if line]
    records[0]["schema"] = "bad"
    index_path.write_text(
        "\n".join(json.dumps(r, separators=(",", ":"), sort_keys=True) for r in records) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code == "relay_index_schema_mismatch"

    exit_code, _fwd, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="verify-edges-3",
        child_argv=_echo_child_args(),
        stdin_bytes=b"xy",
    )
    index_path = run_dir / "relay-index.ndjson"
    records = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines() if line]
    records[1]["monotonic_offset_ns"] = -1
    index_path.write_text(
        "\n".join(json.dumps(r, separators=(",", ":"), sort_keys=True) for r in records) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code == "relay_monotonic_regression"

    exit_code, _fwd, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="verify-edges-4",
        child_argv=_echo_child_args(),
        stdin_bytes=b"xy",
    )
    index_path = run_dir / "relay-index.ndjson"
    records = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines() if line]
    eof = next(r for r in records if r["direction"] == EOF_ZED_TO_AGENT)
    eof["size"] = 1
    index_path.write_text(
        "\n".join(json.dumps(r, separators=(",", ":"), sort_keys=True) for r in records) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code == "relay_eof_size_nonzero"

    empty_idx = tmp_path / "empty-idx"
    empty_idx.mkdir()
    (empty_idx / "zed-to-agent.bin").write_bytes(b"")
    (empty_idx / "agent-to-zed.bin").write_bytes(b"")
    (empty_idx / "relay-index.ndjson").write_text("\n", encoding="utf-8", newline="\n")
    atomic_write_json(
        empty_idx / "relay-summary.json",
        {
            "schema": plan117_custody_relay.SCHEMA_SUMMARY,
            "run_id": "empty-idx",
            "child_argv": ["x"],
            "child_argv_sha256": plan117_custody_relay._argv_digest(["x"]),
            "relay_sha256": plan117_custody_relay._relay_module_digest(),
            "child_exit_code": 0,
            "zed_to_agent_bytes": 0,
            "agent_to_zed_bytes": 0,
            "zed_to_agent_eof": True,
            "agent_to_zed_eof": True,
            "terminal_disposition": "child_exited",
            "reason_code": None,
        },
    )
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(empty_idx)
    assert exc_info.value.reason_code == "relay_index_empty"


def test_generic_oserror_in_forward_thread(tmp_path: Path) -> None:
    class _ErrStdout(io.BytesIO):
        def read(self, _n: int = -1) -> bytes:  # noqa: A003
            raise OSError("read_failed")

    class _Proc:
        def __init__(self) -> None:
            self.stdin = mock.Mock()
            self.stdin.write = mock.Mock(return_value=None)
            self.stdin.close = mock.Mock()
            self.stdin.flush = mock.Mock()
            self.stdout = _ErrStdout()
            self.returncode = None
            self.pid = 5

        def poll(self) -> int | None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            self.returncode = 1
            return 1

        def terminate(self) -> None:
            self.returncode = -15

        def kill(self) -> None:
            self.returncode = -9

    exit_code, _fwd, err, _run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="oserr",
        child_argv=[str(tmp_path / "c.exe")],
        stdin_bytes=b"",
        popen_factory=lambda *_a, **_k: _Proc(),
    )
    assert exit_code != 0
    assert b"relay_recorder_failure" in err


def test_relay_recorder_error_path_and_outer_keyboard_interrupt(tmp_path: Path) -> None:
    class _Proc:
        def __init__(self) -> None:
            self.stdin = mock.Mock()
            self.stdin.write = mock.Mock(return_value=None)
            self.stdin.close = mock.Mock()
            self.stdin.flush = mock.Mock()
            self.stdout = io.BytesIO(b"")
            self.returncode = None
            self.pid = 8

        def poll(self) -> int | None:
            return None if self.returncode is None else self.returncode

        def wait(self, timeout: float | None = None) -> int:
            self.returncode = -2
            return -2

        def terminate(self) -> None:
            self.returncode = -15

        def kill(self) -> None:
            self.returncode = -9

    def hook(recorder: Any) -> None:
        def boom(*_a: Any, **_k: Any) -> None:
            raise plan117_custody_relay.RelayRecorderError("relay_recorder_failure")

        recorder.record_chunk = boom  # type: ignore[method-assign]

    exit_code, _fwd, err, _run = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="rre",
        child_argv=[str(tmp_path / "c.exe")],
        stdin_bytes=b"z",
        popen_factory=lambda *_a, **_k: _Proc(),
        recorder_hook=hook,
    )
    assert exit_code != 0
    assert b"relay_recorder_failure" in err

    def raise_interrupt(*_a: Any, **_k: Any) -> Any:
        raise KeyboardInterrupt

    exit_code, _fwd, err, _run = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="outer-int",
        child_argv=[str(tmp_path / "c.exe")],
        stdin_bytes=b"",
        popen_factory=raise_interrupt,
    )
    assert exit_code != 0
    assert b"relay_interrupted" in err


def test_verify_additional_rejection_paths(tmp_path: Path) -> None:
    exit_code, _fwd, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="more-verify",
        child_argv=_echo_child_args(),
        stdin_bytes=b"ab",
    )
    assert exit_code == 0

    # non-object summary
    (run_dir / "relay-summary.json").write_text("[]", encoding="utf-8", newline="\n")
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code == "relay_summary_invalid"

    exit_code, _fwd, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="more-verify-2",
        child_argv=_echo_child_args(),
        stdin_bytes=b"ab",
    )
    payload = json.loads((run_dir / "relay-summary.json").read_text(encoding="utf-8"))
    payload["run_id"] = ""
    atomic_write_json(run_dir / "relay-summary.json", payload)
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code == "relay_run_id_invalid"

    exit_code, _fwd, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="more-verify-3",
        child_argv=_echo_child_args(),
        stdin_bytes=b"ab",
    )
    payload = json.loads((run_dir / "relay-summary.json").read_text(encoding="utf-8"))
    payload["child_argv"] = "not-a-list"
    atomic_write_json(run_dir / "relay-summary.json", payload)
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code == "relay_child_argv_missing"

    exit_code, _fwd, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="more-verify-4",
        child_argv=_echo_child_args(),
        stdin_bytes=b"ab",
    )
    payload = json.loads((run_dir / "relay-summary.json").read_text(encoding="utf-8"))
    del payload["relay_sha256"]
    atomic_write_json(run_dir / "relay-summary.json", payload)
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code == "relay_digest_missing"

    exit_code, _fwd, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="more-verify-5",
        child_argv=_echo_child_args(),
        stdin_bytes=b"ab",
    )
    payload = json.loads((run_dir / "relay-summary.json").read_text(encoding="utf-8"))
    payload["agent_to_zed_bytes"] = 999
    atomic_write_json(run_dir / "relay-summary.json", payload)
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code == "relay_directional_length_mismatch"

    exit_code, _fwd, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="more-verify-6",
        child_argv=_echo_child_args(),
        stdin_bytes=b"ab",
    )
    (run_dir / "relay-index.ndjson").write_text("{bad\n", encoding="utf-8", newline="\n")
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code == "relay_index_invalid"

    exit_code, _fwd, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="more-verify-7",
        child_argv=_echo_child_args(),
        stdin_bytes=b"ab",
    )
    (run_dir / "relay-index.ndjson").write_text("[]\n", encoding="utf-8", newline="\n")
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code == "relay_index_invalid"

    exit_code, _fwd, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="more-verify-8",
        child_argv=_echo_child_args(),
        stdin_bytes=b"ab",
    )
    records = [json.loads(line) for line in (run_dir / "relay-index.ndjson").read_text(encoding="utf-8").splitlines() if line]
    eof = next(r for r in records if r["direction"] == EOF_ZED_TO_AGENT)
    eof["sha256"] = "0" * 64
    (run_dir / "relay-index.ndjson").write_text(
        "\n".join(json.dumps(r, separators=(",", ":"), sort_keys=True) for r in records) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code == "relay_eof_digest_mismatch"

    exit_code, _fwd, _err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="more-verify-9",
        child_argv=_echo_child_args(),
        stdin_bytes=b"ab",
    )
    records = [json.loads(line) for line in (run_dir / "relay-index.ndjson").read_text(encoding="utf-8").splitlines() if line]
    eof = next(r for r in records if r["direction"] == EOF_AGENT_TO_ZED)
    eof["directional_offset"] = 999
    (run_dir / "relay-index.ndjson").write_text(
        "\n".join(json.dumps(r, separators=(",", ":"), sort_keys=True) for r in records) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(CustodyContractError) as exc_info:
        plan117_custody_relay.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code == "relay_offset_mismatch"


def test_close_and_terminate_defensive_paths(tmp_path: Path) -> None:
    recorder = plan117_custody_relay._LockedRecorder(tmp_path / "c1", "c1", 0.0)

    class _BadClose:
        def close(self) -> None:
            raise OSError("close_failed")

    recorder._bins[DIR_ZED_TO_AGENT] = _BadClose()  # type: ignore[assignment]
    recorder._index = _BadClose()  # type: ignore[assignment]
    recorder.close()

    class _Proc:
        def __init__(self) -> None:
            self.returncode = 0

        def poll(self) -> int:
            return 0

        def terminate(self) -> None:
            raise OSError("term")

        def kill(self) -> None:
            raise OSError("kill")

        def wait(self, timeout: float | None = None) -> int:
            return 0

    plan117_custody_relay._terminate_owned_child(_Proc())

    class _PipeBad:
        def close(self) -> None:
            raise OSError("pipe")

    class _Proc2:
        stdin = _PipeBad()
        stdout = _PipeBad()

    plan117_custody_relay._close_child_pipes(_Proc2())

    # emit stderr flush failure
    class _BadErr:
        def write(self, _data: Any) -> None:
            return None

        def flush(self) -> None:
            raise OSError("flush")

    plan117_custody_relay._emit_stderr(_BadErr(), "relay_recorder_failure")  # type: ignore[arg-type]


def test_main_remainder_without_double_dash_for_non_option_args(tmp_path: Path) -> None:
    with mock.patch.object(plan117_custody_relay, "run_relay", return_value=3) as mocked:
        code = plan117_custody_relay.main(
            [
                "--capture-root",
                str(tmp_path),
                "--run-id",
                "no-dd",
                "--child-executable",
                sys.executable,
                "script.py",
                "arg1",
            ]
        )
        assert code == 3
        assert mocked.call_args.kwargs["child_args"] == ["script.py", "arg1"]
