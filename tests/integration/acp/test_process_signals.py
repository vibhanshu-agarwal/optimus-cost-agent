"""Owned-process tests of the real serving root; no provider, launch authorization or live Redis claim."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import sysconfig
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from optimus.acp.framing import encode_message
from tests.support import child_tripwire

ROOT = Path(__file__).resolve().parents[3]
PEER = Path(__file__).with_name("process_signal_peer.py")


def wait_marker(path, process):
    deadline = time.monotonic() + 15
    read_failures = 0
    codes = []
    while time.monotonic() < deadline:
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            pass
        except PermissionError as exc:
            read_failures += 1
            if len(codes) < 8:
                codes.append({"errno": exc.errno, "winerror": getattr(exc, "winerror", None)})
        else:
            if read_failures:
                path.with_suffix(".read-observations.json").write_text(
                    json.dumps({"read_failures": read_failures, "codes": codes}), encoding="utf-8")
            return result
        assert process.poll() is None, f"child exited {process.returncode} before {path.name}"
        time.sleep(0.01)
    raise AssertionError(f"owned child never reached {path.name}; marker read failures={read_failures}")


def test_marker_wait_observes_sharing_failure_without_relaunch(tmp_path, monkeypatch):
    marker = tmp_path / "ready.json"
    marker.write_text('{"pid": 123}', encoding="utf-8")
    original = Path.read_text
    failures = []

    def read(path, *args, **kwargs):
        if path == marker and not failures:
            failures.append(True)
            raise PermissionError(13, "synthetic sharing observation")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    assert wait_marker(marker, SimpleNamespace(poll=lambda: None)) == {"pid": 123}
    assert json.loads(marker.with_suffix(".read-observations.json").read_text())["read_failures"] == 1


def launch(command, *, environment, stdin, output, console):
    kwargs = {}
    if os.name == "nt":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        kwargs = {"creationflags": subprocess.CREATE_NEW_CONSOLE if console else subprocess.CREATE_NO_WINDOW, "startupinfo": startup}
    else:
        kwargs = {"start_new_session": True}
    return subprocess.Popen(command, cwd=ROOT, env=environment, stdin=stdin, stdout=output, stderr=output, **kwargs)


def deliver_sigint(target, workspace, ordinal, output):
    assert target.poll() is None
    if os.name != "nt":
        os.kill(target.pid, signal.SIGINT)
        return
    receipt = workspace / f"sender-{ordinal}.json"
    broker = launch([sys._base_executable, str(PEER), "--send-owned-sigint", str(target.pid), str(receipt)],
        environment=dict(os.environ), stdin=subprocess.DEVNULL, output=output, console=False)
    try:
        assert broker.wait(timeout=8) == 0, "native delivery refused; never substitute another signal"
        assert set(json.loads(receipt.read_text(encoding="utf-8"))["members"]) == {target.pid, broker.pid}
    finally:
        if broker.poll() is None:
            broker.kill()
            broker.wait(timeout=5)


@pytest.mark.parametrize("mode", ["ndjson", "framed"])
@pytest.mark.parametrize("scenario", ["eof", "read", "writer", "forced"])
def test_owned_process_stop_preserves_actual_disposition(tmp_path, mode, scenario):
    _exercise(tmp_path, mode, scenario)


def test_repeated_native_signal_joins_same_adapter_cleanup(tmp_path):
    _exercise(tmp_path, "ndjson", "mcp")


def test_repeated_native_signal_retains_started_worker_until_return(tmp_path):
    _exercise(tmp_path, "ndjson", "worker")


@pytest.mark.skipif(os.name == "nt", reason="POSIX SIGTERM is a distinct native contract")
@pytest.mark.parametrize("scenario", ["term", "term-clean"])
def test_posix_sigterm_uses_same_owned_cleanup(tmp_path, scenario):
    _exercise(tmp_path, "ndjson", scenario)


def _exercise(workspace, mode, scenario):
    record = workspace / "tripwire.jsonl"
    environment = child_tripwire.environment(dict(os.environ), record)
    with (workspace / "child.log").open("wb") as output:
        target = launch([sys._base_executable, str(PEER), "--serve", str(workspace), mode, scenario,
            sysconfig.get_path("purelib"), str(ROOT)], environment=environment, stdin=subprocess.PIPE, output=output, console=True)
        try:
            assert wait_marker(workspace / "ready.json", target) == {"pid": target.pid}, "signal target must be the real interpreter, not a redirector"
            if scenario == "eof":
                target.stdin.close()
            elif scenario == "forced":
                target.kill()
                target.wait(timeout=5)
                assert not (workspace / "result.json").exists(), "forced termination supplies no cleanup proof"
                return
            elif scenario in {"term", "term-clean"}:
                os.kill(target.pid, signal.SIGTERM)
                if scenario == "term-clean":
                    assert wait_marker(workspace / "signals-1.json", target) == {"signals": 1}
                    wait_marker(workspace / "held.json", target)
                    os.kill(target.pid, signal.SIGTERM)
                    assert wait_marker(workspace / "signals-2.json", target) == {"signals": 2}
                    assert target.poll() is None
                    target.stdin.close()
                    (workspace / "release").touch()
            else:
                if scenario == "worker":
                    wait_marker(workspace / "held.json", target)
                if scenario == "writer":
                    request = {"jsonrpc": "2.0", "id": 1, "method": "optimus.ping"}
                    target.stdin.write(encode_message(request) if mode == "framed" else (json.dumps(request) + "\n").encode())
                    target.stdin.flush()
                    wait_marker(workspace / "held.json", target)
                deliver_sigint(target, workspace, 1, output)
                if scenario in {"writer", "mcp", "worker"}:
                    assert wait_marker(workspace / "signals-1.json", target) == {"signals": 1}
                    wait_marker(workspace / "held.json", target)
                    deliver_sigint(target, workspace, 2, output)
                    assert wait_marker(workspace / "signals-2.json", target) == {"signals": 2}
                    assert target.poll() is None, "second signal must not discard the owned cleanup"
                    target.stdin.close()
                    (workspace / "release").touch()
            expected = 0 if scenario == "eof" else 75 if scenario in {"read", "term"} else 143 if scenario == "term-clean" else 130
            assert target.wait(timeout=15) == expected, (workspace / "child.log").read_text(encoding="utf-8", errors="replace")
            result = json.loads((workspace / "result.json").read_text(encoding="utf-8"))
            assert result["code"] == expected
            assert result["complete"] is (scenario not in {"read", "term"})
            if scenario in {"writer", "mcp", "worker", "term-clean"}:
                assert result["signals"] == 2
            if scenario in {"mcp", "term-clean"}:
                assert result["attempts"] == ["adapter"]
            if scenario == "worker":
                assert result["worker_calls"] == ["entered", "returned"]
        finally:
            (workspace / "release").touch()
            if target.stdin and not target.stdin.closed:
                target.stdin.close()
            if target.poll() is None:
                target.kill()
                target.wait(timeout=5)
            child_tripwire.assert_no_real_adapter_access(record)
