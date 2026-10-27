"""Contained signal peer: no parent-console attachment or host-process signalling."""
from __future__ import annotations

import ctypes
import json
import os
import signal
import sys
import time
from pathlib import Path


def capability_target(receipt: Path) -> int:
    def interrupt(_number: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, interrupt)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    if not kernel.GetConsoleWindow() or not kernel.SetConsoleCtrlHandler(None, False):
        return 76
    receipt.write_text(json.dumps({"pid": os.getpid(), "ready": True}), encoding="utf-8")
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            time.sleep(0.02)
    except KeyboardInterrupt:
        return 130
    return 77


def send_owned_sigint(target: int, receipt: Path) -> int:
    if os.name != "nt" or target <= 0 or target == os.getpid():
        return 76
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    # CREATE_NO_WINDOW can still allocate a private console. Detach only an exclusive own console.
    members = (ctypes.c_ulong * 4)()
    count = kernel.GetConsoleProcessList(members, len(members))
    if count:
        if count != 1 or members[0] != os.getpid() or not kernel.FreeConsole():
            return 76
    if not kernel.AttachConsole(target):
        return 76
    try:
        count = kernel.GetConsoleProcessList(members, len(members))
        actual = set(members[:count]) if 0 < count <= len(members) else set()
        expected = {target, os.getpid()}
        if actual != expected or not kernel.SetConsoleCtrlHandler(None, True):
            return 76
        receipt.write_text(json.dumps({"target": target, "sender": os.getpid(), "members": sorted(actual)}), encoding="utf-8")
        if not kernel.GenerateConsoleCtrlEvent(0, 0):
            return 76
        return 0
    finally:
        kernel.FreeConsole()


def serve_peer(workspace: Path, mode: str, scenario: str, packages: str, root: str) -> int:
    import site

    site.addsitedir(packages)
    sys.path.insert(0, root)
    sys.path.insert(0, str(Path(root) / "src"))
    from tests.support import child_tripwire

    child_tripwire.install()
    import asyncio

    from optimus.acp import server as server_module
    from optimus.acp.__main__ import _run_serving_process
    from optimus.acp.lifecycle import TurnControl
    from optimus.acp.process_lifecycle import ProcessLifecycle, signal_handlers
    from optimus.acp.server import StdioByteReader, StdioByteWriter, StdioNdjsonLineReader, StdioNdjsonLineWriter
    from optimus.acp.spec import AcpDuplexAdapter, AcpPromptTurn
    from tests.integration.acp.test_server_stream import configured_test_agent_server

    assert Path(server_module.__file__).resolve() == Path(root) / "src/optimus/acp/server.py"

    if os.name == "nt":
        assert ctypes.WinDLL("kernel32", use_last_error=True).SetConsoleCtrlHandler(None, False)

    def mark(name: str, value: object) -> None:
        temporary = workspace / (name + ".tmp")
        temporary.write_text(json.dumps(value), encoding="utf-8")
        temporary.replace(workspace / name)

    def wait_release() -> None:
        deadline = time.monotonic() + 10
        while not (workspace / "release").exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("owned fixture release missing")
            time.sleep(0.01)

    class Output:
        def write(self, payload):
            if scenario == "writer":
                mark("held.json", {"stage": "writer"})
                wait_release()
            return sys.stdout.buffer.write(payload)

        def flush(self):
            return sys.stdout.buffer.flush()

    attempts = []
    worker_calls = []
    worker_tasks = []
    original_close = AcpDuplexAdapter.aclose
    original_init = AcpDuplexAdapter.__init__

    def worker():
        worker_calls.append("entered")
        mark("held.json", {"stage": "worker"})
        wait_release()
        worker_calls.append("returned")

    def with_worker(adapter, *args, **kwargs):
        original_init(adapter, *args, **kwargs)
        session = adapter._sessions.create(cwd=workspace)
        turn = AcpPromptTurn(session_id=session.session_id, turn_seq=1,
            turn_control=TurnControl(session_id=session.session_id, turn_seq=1))
        worker_tasks.append(asyncio.create_task(adapter._in_worker(session, turn, worker)))

    async def held_close(adapter):
        attempts.append("adapter")
        mark("held.json", {"stage": "adapter"})
        deadline = time.monotonic() + 10
        while not (workspace / "release").exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("owned fixture release missing")
            await asyncio.sleep(0.01)
        await original_close(adapter)

    if scenario in {"mcp", "term-clean"}:
        AcpDuplexAdapter.aclose = held_close
    if scenario == "worker":
        AcpDuplexAdapter.__init__ = with_worker
    configured = configured_test_agent_server(workspace, output_text="unused")
    lifecycle = ProcessLifecycle()
    framed = mode == "framed"
    reader = StdioByteReader(sys.stdin.buffer) if framed else StdioNdjsonLineReader(sys.stdin.buffer)
    physical_read = reader._owner._operation

    def acknowledged_read(*args):
        if not (workspace / "ready.json").exists():
            mark("ready.json", {"pid": os.getpid()})
        return physical_read(*args)

    reader._owner._operation = acknowledged_read
    writer = StdioByteWriter(Output()) if framed else StdioNdjsonLineWriter(Output())
    try:
        with signal_handlers(lifecycle):
            code = asyncio.run(_run_serving_process(configured.server, lifecycle=lifecycle, framed=framed,
                reader=reader, writer=writer, observation_seconds=0.25))
        mark("result.json", {"code": code, "reason": lifecycle.reason, "state": lifecycle.state,
            "complete": lifecycle.observation.complete, "pending": lifecycle.observation.pending,
            "signals": lifecycle.signal_count, "attempts": attempts, "worker_calls": worker_calls})
        return code
    finally:
        AcpDuplexAdapter.aclose = original_close
        AcpDuplexAdapter.__init__ = original_init


if __name__ == "__main__":
    if len(sys.argv) == 7 and sys.argv[1] == "--serve":
        raise SystemExit(serve_peer(Path(sys.argv[2]), *sys.argv[3:]))
    if len(sys.argv) == 3 and sys.argv[1] == "--capability-target":
        raise SystemExit(capability_target(Path(sys.argv[2])))
    if len(sys.argv) == 4 and sys.argv[1] == "--send-owned-sigint":
        raise SystemExit(send_owned_sigint(int(sys.argv[2]), Path(sys.argv[3])))
    raise SystemExit(76)
