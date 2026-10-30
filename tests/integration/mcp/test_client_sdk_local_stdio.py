"""Real SDK lifetime evidence with one owned child, not independent-server acceptance."""

from __future__ import annotations

import asyncio
import gc
import hashlib
import json
import logging
import sys
import weakref
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


async def test_retiring_one_real_sdk_peer_releases_only_its_owned_graph(monkeypatch, tmp_path, caplog):
    from optimus.acp.session_retention import RetirementReason, RetirementStatus
    from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
    from optimus.mcp.client_config import ClientMcpConfigNormalizer
    from optimus.mcp.client_disposition import ClientMcpDisposition, ClientMcpRuntime
    from optimus.mcp.client_trust import ClientMcpDurableStore, ClientMcpLeaseAuthority
    from tests.support.contract_doubles import checked_agent_runner

    caplog.set_level(logging.WARNING, logger='mcp.client.stdio')
    class NoKeyringWrites:
        def get_password(self, *_args):
            return None
        def set_password(self, *_args):
            raise AssertionError('owned stdio fixture must not write durable trust')
    class UnusedRunner:
        def run(self, request, **kwargs):
            raise AssertionError('this control must not dispatch a model')
    command = Path(sys.executable)
    child_facts = tmp_path / 'launcher-facts'
    child_facts.mkdir()
    if sys.platform != 'win32':
        # The normalizer resolves symlinks. A regular owned launcher preserves the venv
        # interpreter through its shebang instead of dispatching the base Python binary.
        command = tmp_path / 'owned-sdk-peer'
        source = (f'#!{sys.executable}\n'
            'import json, os, runpy, sys\nfrom pathlib import Path\nimport mcp\n'
            f'assert sys.executable == {sys.executable!r}\n'
            f'assert sys.prefix == {sys.prefix!r}\n'
            f'assert Path(mcp.__file__).is_relative_to({sys.prefix!r})\n'
            f'Path({str(child_facts)!r}, str(os.getpid()) + ".json").write_text(json.dumps('
            '{"executable": sys.executable, "prefix": sys.prefix, "mcp": mcp.__file__}))\n'
            f'runpy.run_path({str(peer_script())!r}, run_name="__main__")\n')
        command.write_text(source, encoding='utf-8')
        command.chmod(0o700)
        assert command.read_text().splitlines()[0] == f'#!{sys.executable}'
    print('owned-sdk-launcher:', json.dumps({'command': str(command),
        'command_sha256': hashlib.sha256(command.read_bytes()).hexdigest(),
        'mode': oct(command.stat().st_mode & 0o777), 'interpreter': sys.executable, 'prefix': sys.prefix}))
    watches = []
    original_spawn = sdk_stdio._create_platform_compatible_process
    async def capture_spawn(*args, **kwargs):
        process = await original_spawn(*args, **kwargs)
        watches.append(ProcessWatch(process.pid))
        return process
    monkeypatch.setattr(sdk_stdio, '_create_platform_compatible_process', capture_spawn)
    witness = ContextWitness()
    supervisor = MCPAsyncSupervisor()
    supervisor.start()
    tripwire_records = []
    def transport_context(cap):
        tripwire_record = tmp_path / f'two-peer-tripwire-{len(tripwire_records)}.jsonl'
        tripwire_records.append(tripwire_record)
        parameters = stdio_server_parameters_from_capability(cap)
        parameters.env = child_tripwire.hooked_environment(parameters.env or {}, tripwire_record)
        return stdio_client(parameters)
    sdk = ClientMcpSdkAdapter(supervisor=supervisor, session_factory=lambda _: None,
        http_client_factory=lambda: httpx2.AsyncClient(follow_redirects=False, trust_env=False),
        stdio_transport_factory=lambda _: None, process_control=Mock(spec_set=['terminate_tree']),
        transport_context_factory=witness.wrap(transport_context, 'transport'),
        session_context_factory=witness.wrap(ClientSession, 'session'), operation_timeout_seconds=10)
    disposition = ClientMcpDisposition(normalizer=ClientMcpConfigNormalizer(),
        lease_authority=ClientMcpLeaseAuthority(store=ClientMcpDurableStore(
            keyring_backend=NoKeyringWrites(), hmac_key=b'p' * 32)), hmac_key=b'p' * 32,
        controlled_path=str(Path(sys.executable).parent), workspace_digest='d' * 64)
    runtime = ClientMcpRuntime(disposition=disposition, sdk_adapter=sdk, supervisor=supervisor)
    store = InMemoryAcpSpecSessionStore()
    adapter = AcpDuplexAdapter(runner=checked_agent_runner(UnusedRunner()), workspace_root=tmp_path,
        sessions=store, outbound=RecordingOutboundChannel(), client_mcp_runtime=runtime)
    async def allow(_params):
        return 'allow'
    async def open_peer():
        session = store.create(cwd=tmp_path, conversation=adapter._new_conversation())
        state = await disposition.disposition_for_new_session(session.session_id, tmp_path,
                [{'name': 'owned-peer', 'command': str(command),
                  'args': [str(peer_script())] if sys.platform == 'win32' else []}], allow)
        session.client_mcp_state = state
        disposition.attach_runtime_resolver(state, sdk_adapter=sdk)
        service = await asyncio.to_thread(state.tool_service.ensure_server, 'owned-peer')
        assert service is not None
        assert 'echo' in state.tool_service.list_tools('owned-peer')[0].text
        return session
    try:
        retired, live = await open_peer(), await open_peer()
        assert len(watches) == 2 and all(watch.snapshot().running for watch in watches)
        peer_pids = {watch.pid for watch in watches}
        assert len(peer_pids) == 2
        if sys.platform != 'win32':
            facts = {pid: json.loads((child_facts / f'{pid}.json').read_text()) for pid in peer_pids}
            assert all(fact['executable'] == sys.executable and fact['prefix'] == sys.prefix for fact in facts.values())
            print('owned-sdk-child-identities:', json.dumps(facts, sort_keys=True))
        retired_id = retired.session_id
        connection = next(connection for connection in sdk._connections.values() if connection.session_id == retired_id)
        service = retired.client_mcp_state.tool_service.ensure_server('owned-peer')
        catalog = object.__getattribute__(service, '_catalog')
        refs = tuple(weakref.ref(value) for value in
                     (retired, retired.client_mcp_state.tool_service, catalog, connection))
        adapter.retention.request_retire(retired_id, reason=RetirementReason.EXPLICIT_REMOVE)
        result = await adapter.retention.wait_retired(retired_id)
        assert result is None or result.status is RetirementStatus.RELEASED
        assert connection.closed and connection.owner_terminal
        assert not sdk.has_pending_connections_for_session(retired_id)
        assert sdk.has_pending_connections_for_session(live.session_id)
        assert not watches[0].snapshot().running and watches[1].snapshot().running
        assert [label for label, _ in witness.tasks].count('transport:exit') == 1
        owner_events = [(label, task) for label, task in witness.tasks if task is connection.owner_task]
        assert [label for label, _ in owner_events] == ['transport:enter', 'session:enter', 'session:exit', 'transport:exit']
        del retired, service, catalog, connection, owner_events
        for _ in range(5):
            await asyncio.sleep(0)
            gc.collect()
        assert all(ref() is None for ref in refs)
        output, audit = await asyncio.to_thread(live.client_mcp_state.tool_service.call_tool,
            'owned-peer', 'echo', {'text': 'surviving-peer'})
        assert output.text == 'completed' and audit.authorization_outcome == 'ALLOW'
        live_connection = next(connection for connection in sdk._connections.values() if connection.session_id == live.session_id)
        raw = await asyncio.to_thread(sdk.call, live_connection, 'echo', {'text': 'surviving-peer'})
        assert raw.content[0].text == 'surviving-peer'
        assert len(tripwire_records) == 2
        for record in tripwire_records:
            child_tripwire.assert_no_real_adapter_access(record)
    finally:
        try:
            await adapter.aclose()
        finally:
            try:
                runtime.close()
            finally:
                for watch in watches:
                    try:
                        assert not watch.snapshot().running
                    finally:
                        watch.close()
