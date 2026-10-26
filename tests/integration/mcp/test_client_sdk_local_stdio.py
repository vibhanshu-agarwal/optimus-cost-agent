"""Real SDK lifetime evidence with one owned child, not independent-server acceptance."""

from __future__ import annotations

import logging
import sys
from contextlib import suppress
from pathlib import Path
from unittest.mock import Mock

import httpx2
import pytest
from mcp import ClientSession
from mcp.client import stdio as sdk_stdio
from mcp.client.stdio import stdio_client

from optimus.mcp.client_sdk import ClientMcpSdkAdapter, stdio_server_parameters_from_capability
from optimus.mcp.client_supervisor import MCPAsyncSupervisor
from tests.support import child_tripwire
from tests.support.idle_mcp import ContextWitness, capability, peer_script
from tools.concurrency_capture import ProcessWatch


@pytest.mark.parametrize("peer_exits_first", [False, True], ids=["adapter-close", "peer-eof-before-close"])
def test_real_sdk_contexts_enter_and_exit_in_same_owner_task(monkeypatch, caplog, peer_exits_first, tmp_path):
    caplog.set_level(logging.WARNING, logger="mcp.client.stdio")
    watches = []
    identities = []
    processes = []
    original_spawn = sdk_stdio._create_platform_compatible_process
    async def capture_spawn(*args, **kwargs):
        process = await original_spawn(*args, **kwargs)
        processes.append(process)
        watches.append(ProcessWatch(process.pid))
        if sys.platform == "win32":
            from tools.testing.run_context_windows import process_identity
            identity = process_identity(process.pid)
            assert identity.live and identity.creation_time is not None
            identities.append((identity.pid, identity.creation_time))
        else:
            fields = Path(f"/proc/{process.pid}/stat").read_text().rsplit(")", 1)[1].split()
            identities.append((process.pid, int(fields[19])))
        return process
    monkeypatch.setattr(sdk_stdio, "_create_platform_compatible_process", capture_spawn)
    witness = ContextWitness()
    supervisor = MCPAsyncSupervisor()
    supervisor.start()
    tripwire_record = tmp_path / "sdk-child-tripwire.jsonl"
    def transport_context(cap):
        parameters = stdio_server_parameters_from_capability(cap)
        parameters.env = child_tripwire.hooked_environment(parameters.env or {}, tripwire_record)
        return stdio_client(parameters)
    transport = witness.wrap(transport_context, "transport")
    session = witness.wrap(ClientSession, "session")
    adapter = ClientMcpSdkAdapter(
        supervisor=supervisor, session_factory=lambda _: None,
        http_client_factory=lambda: httpx2.AsyncClient(follow_redirects=False, trust_env=False),
        stdio_transport_factory=lambda _: None, process_control=Mock(spec_set=["terminate_tree"]),
        transport_context_factory=transport, session_context_factory=session,
        operation_timeout_seconds=10,
    )
    connection = None
    try:
        connection = adapter.open(capability(command=sys.executable, arguments=(str(peer_script()),)), session_id="local")
        assert adapter.discover(connection)[0]["tools"][0]["name"] == "echo"
        assert adapter.call(connection, "echo", {"text": "round-trip"}).content[0].text == "round-trip"
        if peer_exits_first:
            supervisor.submit(processes[0].stdin.aclose(), timeout_seconds=3)
            supervisor.submit(processes[0].wait(), timeout_seconds=3)
            assert not watches[0].snapshot().running
        adapter.close(connection)
        assert [label for label, _ in witness.tasks] == ["transport:enter", "session:enter", "session:exit", "transport:exit"]
        assert len({id(task) for _, task in witness.tasks}) == 1
        assert len(identities) == 1 and identities[0][0] == watches[0].pid
        assert not watches[0].snapshot().running
        child_tripwire.assert_no_real_adapter_access(tripwire_record)
    finally:
        if connection is not None and not connection.closed:
            with suppress(Exception):
                adapter.close(connection)
        supervisor.close()
        for watch in watches:
            watch.close()
