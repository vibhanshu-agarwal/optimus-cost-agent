"""RED/GREEN contract for ClientMcpDisposition and AcpMcpPermissionBroker (P11-FU-9 Task 6)."""

from __future__ import annotations

import asyncio
import gc
import json
import pickle
import sys
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from mcp.types import CallToolResult, ListToolsResult, TextContent

from optimus.acp.launch_approvals import KeyringApprovalStore
from optimus.acp.shapes import build_client_mcp_permission_params
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolRequest
from optimus.mcp.client_catalog import (
    MAX_CATALOG_PAGES,
    AdapterBackedClientMcpToolService,
    ClientMcpSessionService,
    ClientMcpToolService,
)
from optimus.mcp.client_config import ClientMcpConfigError, ClientMcpConfigNormalizer, ClientMcpSafeIdentity
from optimus.mcp.client_disposition import (
    AcpMcpPermissionBroker,
    ClientMcpDisposition,
    ClientMcpRuntime,
    ClientMcpSessionState,
    ClientMcpShutdownOutcome,
    run_close_hooks,
)
from optimus.mcp.client_sdk import ClientMcpSdkAdapter
from optimus.mcp.client_supervisor import MCPAsyncSupervisor, MCPSupervisorState
from optimus.mcp.client_trust import (
    ClientMcpDurableRecord,
    ClientMcpDurableStore,
    ClientMcpLeaseAuthority,
    compute_identity_fingerprint,
    write_client_mcp_durable_from_fingerprint,
)
from optimus.mcp.local_ipc import LocalIpcError, PendingClientMcpCandidateEndpoint
from optimus.runtime.modes import ExecutionMode, GenerationScope
from tests.support.concurrency import assert_no_offending_rows, assert_threads_stopped

HMAC_KEY = b"p11-fu-9-disposition-test-hmac-key!!"


def test_owned_close_first_empty_claim_is_real_and_repeat_is_not():
    state = ClientMcpSessionState(session_id='empty-owned')
    operation = state.prepare_owned_close()
    assert operation.claim_hooks() == ()
    assert not operation.result.done()
    state.close()
    assert state.prepare_owned_close() is operation
    assert operation.claim_hooks() is None
    assert not operation.result.done()
    operation.finish(())
    assert operation.result.result() == ()


def test_owned_close_failure_is_sticky_and_independent():
    state = ClientMcpSessionState(session_id='failed-owned')
    other = ClientMcpSessionState(session_id='other-owned')
    calls = []

    def fail():
        calls.append('failed')
        raise RuntimeError('private remote detail')

    state.register_close_hook(fail)
    state.close()
    operation = state.prepare_owned_close()
    assert operation.result.result() == ('SESSION_CLOSE_FAILED',)
    state.close()
    assert state.prepare_owned_close() is operation
    operation.finish(())
    assert operation.result.result() == ('SESSION_CLOSE_FAILED',)
    assert calls == ['failed']
    other.close()
    assert other.prepare_owned_close().result.result() == ()


def test_owned_close_legacy_tuple_path_is_unknown():
    state = ClientMcpSessionState(session_id='legacy')
    assert state.prepare_close() == ()
    state.complete_close(())
    state.close()
    assert state.prepare_owned_close().result.result() == ('SESSION_CLOSE_UNKNOWN',)


def _owned_context_sdk(supervisor, operations):
    class Remote(_ControlledRemoteSession):
        async def initialize(self):
            if self.server_name == 'broken':
                operations.append('failed-open')
                raise ValueError('controlled initialize failure')
            return await super().initialize()

    @asynccontextmanager
    async def transport(capability):
        name = capability.safe_identity.server_name
        try:
            yield name, None
        finally:
            if name == 'broken':
                raise OSError(5, 'controlled context exit failure')

    @asynccontextmanager
    async def session(name, _write):
        yield Remote(name, operations, _catalog_pages())

    return ClientMcpSdkAdapter(
        supervisor=supervisor, session_factory=lambda _capability: None,
        http_client_factory=lambda: SimpleNamespace(follow_redirects=False, trust_env=False),
        stdio_transport_factory=lambda _capability: None, process_control=_ControlledProcessControl(),
        transport_context_factory=transport, session_context_factory=session,
    )


async def test_bound_store_failed_sdk_open_without_hook_retains_capacity(tmp_path, sdk_supervisor):
    from time import monotonic

    from optimus.acp.session_retention import (
        RetirementReason,
        RetirementStatus,
        SessionCapacityError,
        SessionRetentionOwner,
        SessionRetentionPolicy,
    )
    from optimus.acp.spec import InMemoryAcpSpecSessionStore

    operations = []
    adapter = _owned_context_sdk(sdk_supervisor, operations)
    disp = _disposition(tmp_path)
    store = InMemoryAcpSpecSessionStore()

    async def unused_close(session, states):
        raise AssertionError('synchronous retirement must not retry')

    owner = SessionRetentionOwner(policy=SessionRetentionPolicy(2), clock=monotonic,
                                  close_session=unused_close, detach_session=store._detach_session)
    store.bind_retention(owner)
    broken, live = store.create(cwd=tmp_path), store.create(cwd=tmp_path)
    bad = broken.client_mcp_state = await disp.disposition_for_new_session(
        broken.session_id, tmp_path, [_http_entry(name='broken')], _allow)
    good = live.client_mcp_state = await disp.disposition_for_new_session(
        live.session_id, tmp_path, [_http_entry()], _allow)
    disp.attach_runtime_resolver(bad, sdk_adapter=adapter)
    disp.attach_runtime_resolver(good, sdk_adapter=adapter)
    bad.tool_service.list_tools('broken')
    assert operations == ['failed-open']
    assert bad._close_hooks == [] and not bad.has_open_peer()
    assert adapter.has_pending_connections_for_session(broken.session_id)
    pending = next(connection for connection in adapter._connections.values()
                   if connection.session_id == broken.session_id)
    assert pending.owner_terminal and isinstance(pending.owner_error, OSError)
    store.remove(broken.session_id)
    assert owner.retained_count == 2
    result, = await owner.drain()
    assert result.status is RetirementStatus.QUARANTINED and result.close.pending
    assert store.get(broken.session_id) is broken
    with pytest.raises(SessionCapacityError):
        store.create(cwd=tmp_path)
    assert bad.prepare_owned_close()._adapter is adapter
    assert bad._resolver_adapter is None
    assert owner.request_retire(broken.session_id, reason=RetirementReason.SHUTDOWN) is RetirementStatus.QUARANTINED
    listed, call = good.tool_service.list_tools('tools')
    assert call.authorization_outcome == 'ALLOW' and 'list_providers' in listed.text
    store.remove(live.session_id)
    assert owner.retained_count == 1 and store.get(live.session_id) is None
    assert adapter.has_pending_connections_for_session(broken.session_id)
    assert not adapter.has_pending_connections_for_session(live.session_id)
    assert good.prepare_owned_close()._adapter is None
    assert await owner.drain() == (result,)
    assert operations.count('failed-open') == 1


async def test_bound_store_sdk_pending_query_error_is_owned_unknown(tmp_path, sdk_supervisor):
    from time import monotonic

    from optimus.acp.session_retention import RetirementStatus, SessionRetentionOwner, SessionRetentionPolicy
    from optimus.acp.spec import InMemoryAcpSpecSessionStore
    from optimus.mcp.client_supervisor import MCPSupervisorError

    adapter = _owned_context_sdk(sdk_supervisor, [])
    disp = _disposition(tmp_path)
    store = InMemoryAcpSpecSessionStore()

    async def unused_close(session, states):
        raise AssertionError('synchronous retirement must not retry')

    owner = SessionRetentionOwner(policy=SessionRetentionPolicy(1), clock=monotonic,
                                  close_session=unused_close, detach_session=store._detach_session)
    store.bind_retention(owner)
    session = store.create(cwd=tmp_path)
    state = session.client_mcp_state = await disp.disposition_for_new_session(
        session.session_id, tmp_path, [_http_entry(name='broken')], _allow)
    disp.attach_runtime_resolver(state, sdk_adapter=adapter)
    state.tool_service.list_tools('broken')
    assert adapter.has_pending_connections_for_session(session.session_id)
    sdk_supervisor.close()
    with pytest.raises(MCPSupervisorError, match='SUPERVISOR_DEAD'):
        store.remove(session.session_id)
    result, = await owner.drain()
    assert result.status is RetirementStatus.QUARANTINED and result.close.pending
    operation = state.prepare_owned_close()
    assert operation._adapter is adapter
    assert operation.failure_fact == {'class': 'MCPSupervisorError', 'errno': None}
    assert owner.retained_count == 1 and store.get(session.session_id) is session
    store.remove(session.session_id)
    assert await owner.drain() == (result,)


async def test_standalone_owned_close_releases_sdk_reference(tmp_path, sdk_supervisor):
    adapter = _owned_context_sdk(sdk_supervisor, [])
    disp = _disposition(tmp_path)
    state = await disp.disposition_for_new_session('standalone', tmp_path, [_http_entry()], _allow)
    disp.attach_runtime_resolver(state, sdk_adapter=adapter)
    listed, call = state.tool_service.list_tools('tools')
    assert call.authorization_outcome == 'ALLOW' and 'list_providers' in listed.text
    adapter_ref = weakref.ref(adapter)
    state.close()
    assert adapter.pending_connections() == ()
    del adapter
    sdk_supervisor.submit(asyncio.sleep(0), timeout_seconds=1)
    gc.collect()
    assert adapter_ref() is None


@pytest.mark.parametrize('failure_point', ['callback', 'candidate'])
async def test_provisional_callback_precedes_registration_and_owned_close_preserves_primary(tmp_path, monkeypatch, failure_point):
    disp = _disposition(tmp_path)
    states, closed = [], []
    primary = ValueError('controlled callback failure') if failure_point == 'callback' else asyncio.CancelledError('controlled candidate cancellation')

    def fail_close():
        closed.append('closed')
        raise OSError('secondary cleanup failure')

    def provisional(state):
        states.append(state)
        state.register_close_hook(fail_close)
        if failure_point == 'callback':
            raise primary

    original = disp._own_candidates

    def candidates(state):
        assert states == [state]
        original(state)
        raise primary

    monkeypatch.setattr(disp, '_own_candidates', candidates)
    with pytest.raises(type(primary)) as caught:
        await disp.disposition_for_new_session('provisional', tmp_path, None, _allow,
                                               on_provisional_state=provisional)
    assert caught.value is primary and closed == ['closed']
    operation = states[0].prepare_owned_close()
    assert operation.result.result() == ('SESSION_CLOSE_FAILED',)
    states[0].close()
    assert states[0].prepare_owned_close() is operation and closed == ['closed']


async def test_provisional_callback_success_precedes_first_permission_await(tmp_path):
    disp = _disposition(tmp_path)
    states = []

    async def permission(params):
        assert len(states) == 1 and states[0]._capabilities
        await asyncio.sleep(0)
        return 'reject'

    state = await disp.disposition_for_new_session('provisional', tmp_path, [_http_entry()], permission,
                                                   on_provisional_state=states.append)
    assert states == [state]
    state.close()
    assert state.prepare_owned_close().result.result() == ()


@pytest.mark.parametrize('failure', [asyncio.CancelledError('cancel'), SystemExit(19)])
def test_owned_close_preserves_control_exception_and_first_failure(failure):
    state = ClientMcpSessionState(session_id='control')
    calls = []

    def fail():
        raise failure

    state.register_close_hook(fail)
    state.register_close_hook(lambda: calls.append('remaining'))
    with pytest.raises(type(failure)) as caught:
        state.close()
    assert caught.value is failure
    assert calls == ['remaining']
    state.close()
    assert state.prepare_owned_close().result.result() == ('SESSION_CLOSE_FAILED',)


def test_split_close_detaches_once_and_records_legacy_hook_failure(tmp_path):
    disposition = _disposition(tmp_path)
    state = ClientMcpSessionState(session_id="split", _record_close_failure=disposition.record_session_close_failure)
    calls = []
    state.register_close_hook(lambda: calls.append("peer"), peer=True)
    state.register_close_hook(lambda: (_ for _ in ()).throw(RuntimeError("private remote details")))
    assert state.has_open_peer()
    state.close()
    state.close()
    assert calls == ["peer"]
    assert disposition.close_failure_recorded
    assert not state.has_open_peer()


async def test_suspend_and_renew_is_atomic_and_replaces_facade(tmp_path):
    disposition = _disposition(tmp_path)
    async def allow(_params):
        return "allow"
    state = await disposition.disposition_for_new_session("renew", tmp_path, [_http_entry(name="one"), _http_entry(name="two")], allow)
    old_facade = state.tool_service
    closed = []
    state.register_close_hook(lambda: closed.append("peer"), peer=True)
    hooks = state.prepare_suspend()
    assert hooks is not None
    assert closed == []
    for hook in hooks:
        hook()
    assert closed == ["peer"]
    assert state.complete_suspend(())
    assert state.suspended and not state.is_leased("one")
    answers = iter(["allow", "reject"])
    async def partial(_params):
        return next(answers)
    assert await disposition.reopen_suspended(state, partial) == "reject"
    assert state.suspended and not state.is_leased("one") and not state.is_leased("two")
    assert await disposition.reopen_suspended(state, allow) == "allow"
    assert state.tool_service is not old_facade
    assert state.is_leased("one") and state.is_leased("two")
    assert not state.suspended


async def test_cancelled_initial_disposition_retires_its_owned_candidate(tmp_path):
    endpoint = PendingClientMcpCandidateEndpoint(authkey=b"cancelled-provisional-session")
    disposition = _disposition(tmp_path)
    disposition._candidate_endpoint = endpoint
    entered = asyncio.Event()
    async def permission(_params):
        entered.set()
        await asyncio.Event().wait()
    task = asyncio.create_task(disposition.disposition_for_new_session("cancelled-new", tmp_path, [_http_entry()], permission))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert endpoint.pending_count == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert endpoint.pending_count == 0
    finally:
        task.cancel()
        endpoint.close()


async def test_answered_candidate_survives_until_session_lifetime_and_denials_stay_bounded(tmp_path):
    endpoint = PendingClientMcpCandidateEndpoint(authkey=b"candidate-lifetime-test")
    disposition = _disposition(tmp_path)
    disposition._candidate_endpoint = endpoint
    async def allow(_params):
        return "allow"
    async def reject(_params):
        return "reject"
    state = await disposition.disposition_for_new_session("candidate-owner", tmp_path, [_http_entry()], allow)
    try:
        assert endpoint.pending_count == 1
        candidate_id = next(iter(endpoint._pending))
        assert endpoint.consume_snapshot(candidate_id).session_id == state.session_id
        state.register_close_hook(lambda: None, peer=True)
        for hook in state.prepare_suspend():
            hook()
        assert state.complete_suspend(())
        for _ in range(5):
            assert await disposition.reopen_suspended(state, reject) == "reject"
            assert endpoint.pending_count == 1
        state.close()
        assert endpoint.pending_count == 0
    finally:
        state.close()
        endpoint.close()


@pytest.mark.parametrize("failure_kind", ["retained", "different", "forged"])
async def test_candidate_retirement_only_separates_typed_retained_listener(tmp_path, monkeypatch, failure_kind):
    endpoint = PendingClientMcpCandidateEndpoint(authkey=b"retirement-classification")
    disposition = _disposition(tmp_path)
    disposition._candidate_endpoint = endpoint
    async def allow(_params):
        return "allow"
    state = await disposition.disposition_for_new_session("retirement", tmp_path, [_http_entry()], allow)
    class ForgedError(RuntimeError):
        code = "client_mcp.ipc_stop_incomplete"
    failure = {
        "retained": LocalIpcError("client_mcp.ipc_stop_incomplete"),
        "different": LocalIpcError("client_mcp.ipc_not_listening"),
        "forged": ForgedError(),
    }[failure_kind]
    real_stop = endpoint._stop_listener
    def incomplete_stop():
        assert endpoint.pending_count == 0, "actual candidate removal must precede the stop"
        raise failure
    try:
        assert endpoint.pending_count == 1
        state.register_close_hook(lambda: None, peer=True)
        with monkeypatch.context() as patch:
            patch.setattr(endpoint, "_stop_listener", incomplete_stop)
            failures = run_close_hooks(state.prepare_suspend())
        assert endpoint.pending_count == 0
        assert state.complete_suspend(failures) is (failure_kind == "retained")
        assert disposition.close_failure_recorded is (failure_kind != "retained")
        assert failures == (() if failure_kind == "retained" else ("SESSION_CLOSE_FAILED",))
    finally:
        monkeypatch.setattr(endpoint, "_stop_listener", real_stop)
        state.close()
        endpoint.close()


class FakeKeyring:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        return self._store.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self._store[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        self._store.pop((service, key), None)


class RecordingTransportProbe:
    """Fails the suite if disposition opens any transport."""

    def __init__(self) -> None:
        self.open_calls = 0

    def open(self, *_a: object, **_k: object) -> None:
        self.open_calls += 1
        raise AssertionError("disposition must never open transport")


def _authority(tmp_path: Path) -> tuple[ClientMcpLeaseAuthority, ClientMcpDurableStore]:
    keyring = FakeKeyring()
    launch = KeyringApprovalStore(keyring_backend=keyring, runtime_root=tmp_path, hmac_key=HMAC_KEY)
    store = ClientMcpDurableStore(keyring_backend=keyring, hmac_key=launch.hmac_key)
    return ClientMcpLeaseAuthority(store=store), store


def _disposition(
    tmp_path: Path,
    *,
    timeout_seconds: float = 30.0,
) -> ClientMcpDisposition:
    authority, _store = _authority(tmp_path)
    return ClientMcpDisposition(
        normalizer=ClientMcpConfigNormalizer(),
        lease_authority=authority,
        hmac_key=HMAC_KEY,
        controlled_path=str(tmp_path / "bin"),
        workspace_digest="d" * 64,
        permission_timeout_seconds=timeout_seconds,
    )


def _http_entry(*, name: str = "tools") -> dict[str, object]:
    return {
        "type": "http",
        "name": name,
        "url": "https://mcp.example.com/v1",
        "headers": [],
    }


def _http_identity(*, name: str = "tools") -> ClientMcpSafeIdentity:
    return ClientMcpSafeIdentity(
        transport="http",
        server_name=name,
        canonical_target="https://mcp.example.com/v1",
        arguments=(),
        credential_name_fingerprints=(),
    )


def _catalog_pages(*, write: bool = False) -> list[dict[str, object]]:
    tools: list[dict[str, object]] = [
        {
            "name": "list_providers",
            "description": "Safe metadata lookup.",
            "inputSchema": {"type": "object"},
        }
    ]
    if write:
        tools.append(
            {
                "name": "delete_resource",
                "description": "Delete a resource.",
                "inputSchema": {"type": "object"},
                "annotations": {"destructiveHint": True},
            }
        )
    return [{"tools": tools}]


def _record_adapter_open_and_discover(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Control only the remote SDK edge while preserving the project adapter type."""
    operations: list[str] = []
    connection = object()

    def open(
        _adapter: ClientMcpSdkAdapter,
        _capability: object,
        *,
        session_id: str,
        proposed_protocol_version: str = "2026-07-28",
    ) -> object:
        assert session_id == "session-1"
        assert proposed_protocol_version == "2026-07-28"
        operations.append("open")
        return connection

    def discover(_adapter: ClientMcpSdkAdapter, actual_connection: object) -> list[dict[str, object]]:
        assert actual_connection is connection
        operations.append("discover")
        return _catalog_pages()

    monkeypatch.setattr(ClientMcpSdkAdapter, "open", open)
    monkeypatch.setattr(ClientMcpSdkAdapter, "discover", discover)
    return operations


class _RecordingDispatchService(ClientMcpToolService):
    def _dispatch(self, tool_name: str, arguments: dict[str, Any]) -> str:
        return f"dispatched:{tool_name}"


def _recording_service_factory(**kwargs: Any) -> ClientMcpToolService:
    return _RecordingDispatchService(**kwargs)


@dataclass
class _ControlledRemoteSession:
    server_name: str
    operations: list[str]
    pages: list[dict[str, object]]
    discover_error: bool = False

    async def initialize(self) -> object:
        self.operations.append(f"open:{self.server_name}")
        return SimpleNamespace(
            protocol_version="2025-11-25",
            instructions="",
            server_info=SimpleNamespace(name=self.server_name, description=""),
        )

    async def list_tools(self, *, params: Any = None) -> Any:
        self.operations.append(f"discover:{self.server_name}")
        if self.discover_error:
            raise RuntimeError("controlled remote discovery failure")
        index = int(params.cursor) if params and params.cursor else 0
        page = dict(self.pages[index])
        if "tools" not in page:
            return page  # Deliberately malformed remote result.
        if index + 1 < len(self.pages):
            page["nextCursor"] = str(index + 1)
        return ListToolsResult.model_validate(page)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        del arguments
        self.operations.append(f"call:{self.server_name}:{name}")
        return CallToolResult(content=[TextContent(type="text", text="remote result must stay hidden")])


@dataclass
class _ControlledProcessControl:
    closes: int = 0

    def terminate_tree(self, *, seam: str) -> None:
        del seam
        self.closes += 1


def _actual_sdk_adapter(
    supervisor: MCPAsyncSupervisor,
    *,
    operations: list[str],
    pages_by_server: dict[str, list[dict[str, object]]] | None = None,
    discover_error_servers: frozenset[str] = frozenset(),
    process_control: _ControlledProcessControl | None = None,
) -> ClientMcpSdkAdapter:
    pages = pages_by_server or {"tools": _catalog_pages(), "docs": _catalog_pages()}

    def session_factory(capability: object) -> _ControlledRemoteSession:
        identity = capability.safe_identity
        return _ControlledRemoteSession(
            server_name=identity.server_name,
            operations=operations,
            pages=pages[identity.server_name],
            discover_error=identity.server_name in discover_error_servers,
        )

    return ClientMcpSdkAdapter(
        supervisor=supervisor,
        session_factory=session_factory,
        http_client_factory=lambda: SimpleNamespace(follow_redirects=False, trust_env=False),
        stdio_transport_factory=lambda _capability: None,
        process_control=process_control or _ControlledProcessControl(),
    )


@pytest.fixture
def sdk_supervisor() -> MCPAsyncSupervisor:
    supervisor = MCPAsyncSupervisor()
    supervisor.start()
    yield supervisor
    supervisor.close()


def _write_request(*, session_id: str, server: str = "tools", arguments: dict[str, Any] | None = None) -> PreToolRequest:
    return PreToolRequest(
        run_id="run-1",
        session_id=session_id,
        execution_mode=ExecutionMode.AGENT,
        tool_surface=ToolSurface.MCP,
        action=f"{server}.delete_resource",
        generation_scope=GenerationScope.INLINE_SNIPPET,
        approval_granted=False,
        mcp_authority="client_session",
        mcp_server_id=server,
        mcp_tool_name="delete_resource",
        mcp_arguments=arguments if arguments is not None else {"id": "abc"},
    )


async def _allow(_params: dict[str, Any]) -> str:
    return "allow"


def _seed_side_effect_durable(tmp_path: Path, *, name: str = "tools") -> tuple[ClientMcpDisposition, RecordingTransportProbe]:
    authority, store = _authority(tmp_path)
    identity = _http_identity(name=name)
    fingerprint = compute_identity_fingerprint(identity, hmac_key=HMAC_KEY)
    write_client_mcp_durable_from_fingerprint(
        store=store,
        workspace_digest="d" * 64,
        identity=identity,
        rendered_fingerprint=fingerprint,
        effect_ceiling="side_effect_eligible",
    )
    probe = RecordingTransportProbe()
    disp = ClientMcpDisposition(
        normalizer=ClientMcpConfigNormalizer(),
        lease_authority=authority,
        hmac_key=HMAC_KEY,
        controlled_path=str(tmp_path / "bin"),
        workspace_digest="d" * 64,
    )
    return disp, probe


@pytest.mark.asyncio
async def test_absent_and_empty_entries_are_exact_noop(tmp_path: Path) -> None:
    probe = RecordingTransportProbe()
    disp = _disposition(tmp_path)
    calls: list[object] = []

    async def request_permission(*_a: object, **_k: object) -> str:
        calls.append("permission")
        return "allow"

    for entries in (None, []):
        state = await disp.disposition_for_new_session(
            "session-1",
            tmp_path,
            entries,
            request_permission,
        )
        assert isinstance(state, ClientMcpSessionState)
        assert state.server_names() == ()
        assert state.tool_service is not None
        assert calls == []
        assert probe.open_calls == 0


@pytest.mark.asyncio
async def test_malformed_and_duplicate_config_rejected_before_transport(tmp_path: Path) -> None:
    probe = RecordingTransportProbe()
    disp = _disposition(tmp_path)
    permission_calls: list[object] = []

    async def request_permission(*_a: object, **_k: object) -> str:
        permission_calls.append("permission")
        return "allow"

    with pytest.raises(ClientMcpConfigError) as duplicate:
        await disp.disposition_for_new_session(
            "session-1",
            tmp_path,
            [_http_entry(name="tools"), _http_entry(name="tools")],
            request_permission,
        )
    assert "duplicate" in str(duplicate.value).lower() or "client_mcp" in str(duplicate.value)

    with pytest.raises(ClientMcpConfigError):
        await disp.disposition_for_new_session(
            "session-1",
            tmp_path,
            [{"type": "http", "name": "bad name!", "url": "https://mcp.example.com/v1"}],
            request_permission,
        )
    assert permission_calls == []
    assert probe.open_calls == 0


@pytest.mark.asyncio
async def test_valid_entry_requests_safe_approval_without_opening_transport(tmp_path: Path) -> None:
    probe = RecordingTransportProbe()
    disp = _disposition(tmp_path)
    seen: list[dict[str, Any]] = []

    async def request_permission(params: dict[str, Any]) -> str:
        seen.append(params)
        return "allow"

    state = await disp.disposition_for_new_session(
        "session-1",
        tmp_path,
        [_http_entry()],
        request_permission,
    )
    assert len(seen) == 1
    params = seen[0]
    assert params["sessionId"] == "session-1"
    assert isinstance(params.get("candidateId"), str) and params["candidateId"]
    assert "headers" not in params
    assert "env" not in params
    assert "url" not in str(params).lower() or "mcp.example.com" not in str(params)
    options = params["options"]
    kinds = {opt["kind"] for opt in options}
    assert kinds == {"allow_once", "reject_once"}
    assert "allow_always" not in kinds
    assert state.is_leased("tools")
    assert state.lease_for("tools") is not None
    assert probe.open_calls == 0


@pytest.mark.asyncio
async def test_timeout_and_outbound_failure_yield_unavailable_not_lease(tmp_path: Path) -> None:
    for outcome in ("timeout", "outbound_failure"):
        probe = RecordingTransportProbe()
        disp = _disposition(tmp_path, timeout_seconds=0.05)

        async def request_permission(_params: dict[str, Any], *, _outcome: str = outcome) -> str:
            if _outcome == "timeout":
                await asyncio.sleep(1.0)
                return "allow"
            raise RuntimeError("outbound failed")

        state = await disp.disposition_for_new_session(
            "session-1",
            tmp_path,
            [_http_entry()],
            request_permission,
        )
        assert not state.is_leased("tools")
        assert state.is_unavailable("tools")
        assert state.lease_for("tools") is None
        assert probe.open_calls == 0


@pytest.mark.asyncio
async def test_reject_leaves_tools_unavailable(tmp_path: Path) -> None:
    probe = RecordingTransportProbe()
    disp = _disposition(tmp_path)

    async def request_permission(_params: dict[str, Any]) -> str:
        return "reject"

    state = await disp.disposition_for_new_session(
        "session-1",
        tmp_path,
        [_http_entry()],
        request_permission,
    )
    assert state.is_unavailable("tools")
    assert not state.is_leased("tools")
    assert probe.open_calls == 0


@pytest.mark.asyncio
async def test_allow_once_creates_session_lease_and_looks_up_durable(tmp_path: Path) -> None:
    authority, store = _authority(tmp_path)
    identity = ClientMcpSafeIdentity(
        transport="http",
        server_name="tools",
        canonical_target="https://mcp.example.com/v1",
        arguments=(),
        credential_name_fingerprints=(),
    )
    fingerprint = compute_identity_fingerprint(identity, hmac_key=HMAC_KEY)
    write_client_mcp_durable_from_fingerprint(
        store=store,
        workspace_digest="d" * 64,
        identity=identity,
        rendered_fingerprint=fingerprint,
        effect_ceiling="side_effect_eligible",
    )
    probe = RecordingTransportProbe()
    disp = ClientMcpDisposition(
        normalizer=ClientMcpConfigNormalizer(),
        lease_authority=authority,
        hmac_key=HMAC_KEY,
        controlled_path=str(tmp_path / "bin"),
        workspace_digest="d" * 64,
    )

    async def request_permission(_params: dict[str, Any]) -> str:
        return "allow"

    state = await disp.disposition_for_new_session(
        "session-1",
        tmp_path,
        [_http_entry()],
        request_permission,
    )
    assert state.is_leased("tools")
    lease = state.lease_for("tools")
    assert lease is not None
    assert lease.session_id == "session-1"
    durable = state.durable_for("tools")
    assert isinstance(durable, ClientMcpDurableRecord)
    assert durable.effect_ceiling == "side_effect_eligible"
    assert probe.open_calls == 0


def test_permission_params_shape_is_opaque_and_names_cli_review() -> None:
    params = build_client_mcp_permission_params(
        session_id="session-1",
        candidate_id="cand-abc",
        server_name="tools",
        transport="http",
        identity_fingerprint="fp-1",
    )
    blob = str(params)
    assert "optimus-trust mcp review" in blob
    assert params["sessionId"] == "session-1"
    assert params["candidateId"] == "cand-abc"
    assert {opt["kind"] for opt in params["options"]} == {"allow_once", "reject_once"}
    assert_no_offending_rows(params["options"], lambda opt: not (opt["kind"] != "allow_always"), 'must hold for all: opt["kind"] != "allow_always"')
    assert "SECRET" not in blob


def test_session_state_close_is_idempotent_and_tracks_once(tmp_path: Path) -> None:
    state = ClientMcpSessionState(session_id="session-1")
    closes = {"count": 0}

    def _close_hook() -> None:
        closes["count"] += 1

    state.register_close_hook(_close_hook)
    state.close()
    state.close()
    assert closes["count"] == 1


@pytest.mark.asyncio
async def test_acp_mcp_permission_broker_allow_once_only(tmp_path: Path) -> None:
    approvals: list[str] = []

    async def send_permission(params: dict[str, Any]) -> dict[str, Any]:
        approvals.append(params["options"][0]["kind"])
        assert {opt["kind"] for opt in params["options"]} == {"allow_once", "reject_once"}
        return {"outcome": {"outcome": "selected", "optionId": "allow_once"}}

    loop = asyncio.get_running_loop()
    broker = AcpMcpPermissionBroker(
        session_id="session-1",
        request_permission=send_permission,
        issue_approval=lambda request: type(
            "Approval",
            (),
            {
                "token": "tok-1",
                "session_id": request.session_id,
                "identity_fingerprint": "fp",
                "tool_name": request.mcp_tool_name,
                "arguments_digest": "digest",
            },
        )(),
        timeout_seconds=30.0,
        loop=loop,
    )
    request = PreToolRequest(
        run_id="run-1",
        session_id="session-1",
        execution_mode=ExecutionMode.AGENT,
        tool_surface=ToolSurface.MCP,
        action="tools.write",
        generation_scope=__import__("optimus.guardrails.permissions", fromlist=["GenerationScope"]).GenerationScope.INLINE_SNIPPET,
        approval_granted=False,
        mcp_authority="client_session",
        mcp_server_id="tools",
        mcp_tool_name="write_thing",
        mcp_arguments={"x": 1},
    )
    approval = await asyncio.to_thread(broker.request_write, request)
    assert approval is not None
    assert approval.token == "tok-1"
    assert approvals == ["allow_once"]


@pytest.mark.asyncio
async def test_acp_mcp_permission_broker_reject_timeout_error_return_none() -> None:
    async def reject(_params: dict[str, Any]) -> dict[str, Any]:
        return {"outcome": {"outcome": "selected", "optionId": "reject_once"}}

    async def boom(_params: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("outbound")

    async def hang(_params: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(10)
        return {"outcome": {"outcome": "selected", "optionId": "allow_once"}}

    loop = asyncio.get_running_loop()
    for request_fn, timeout in ((reject, 30.0), (boom, 30.0), (hang, 0.05)):
        broker = AcpMcpPermissionBroker(
            session_id="session-1",
            request_permission=request_fn,
            issue_approval=lambda _r: None,
            timeout_seconds=timeout,
            loop=loop,
        )
        request = PreToolRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.MCP,
            action="tools.write",
            generation_scope=__import__(
                "optimus.guardrails.permissions", fromlist=["GenerationScope"]
            ).GenerationScope.INLINE_SNIPPET,
            approval_granted=False,
            mcp_authority="client_session",
            mcp_server_id="tools",
            mcp_tool_name="write_thing",
            mcp_arguments={},
        )
        assert await asyncio.to_thread(broker.request_write, request) is None


def test_stdio_entry_helper_available_for_acp_tests(tmp_path: Path) -> None:
    """Sanity: controlled bin used by ACP RED selectors for stdio entries."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / ("demo.exe" if sys.platform == "win32" else "demo")
    exe.write_text("x", encoding="utf-8")
    assert exe.exists()


@pytest.mark.asyncio
async def test_allow_once_stays_transport_free_until_lazy_materialization_registers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter_operations = _record_adapter_open_and_discover(monkeypatch)
    disp, probe = _seed_side_effect_durable(tmp_path)
    state = await disp.disposition_for_new_session(
        "session-1",
        tmp_path,
        [_http_entry()],
        _allow,
    )
    assert state.is_leased("tools")
    assert isinstance(state, ClientMcpSessionState)
    assert isinstance(state.tool_service, ClientMcpSessionService)
    assert adapter_operations == []
    lease = state.lease_for("tools")
    assert lease is not None
    assert lease.effect_ceiling == "side_effect_eligible"
    assert probe.open_calls == 0

    listed, call = state.tool_service.list_tools("tools")
    assert listed.text == "unavailable:unknown_server"
    assert call.authorization_outcome == "BLOCK"

    disp.materialize_tool_service(
        state,
        identity=_http_identity(),
        raw_tools=_catalog_pages(),
        workspace_root=tmp_path,
        service_factory=_recording_service_factory,
    )
    assert probe.open_calls == 0

    listed, call = state.tool_service.list_tools("tools")
    assert call.authorization_outcome == "ALLOW"
    payload = json.loads(listed.text)
    names = {tool["name"] for tool in payload["tools"]}
    assert names == {"list_providers"}
    missing, missing_call = state.tool_service.list_tools("docs")
    assert missing.text == "unavailable:unknown_server"
    assert missing_call.authorization_outcome == "BLOCK"


@pytest.mark.asyncio
async def test_leased_server_static_list_lazily_admits_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sdk_supervisor: MCPAsyncSupervisor,
) -> None:
    """A leased server must be discoverable through the static generic list route.

    The production change that must make this pass is the lazy resolver that opens the
    leased capability, discovers its catalog, and registers the resulting real service.
    Until that resolver exists, the registry correctly fails closed as unknown_server.
    """
    adapter_operations = _record_adapter_open_and_discover(monkeypatch)
    disp, probe = _seed_side_effect_durable(tmp_path)
    state = await disp.disposition_for_new_session(
        "session-1",
        tmp_path,
        [_http_entry()],
        _allow,
    )

    assert isinstance(state, ClientMcpSessionState)
    assert isinstance(state.tool_service, ClientMcpSessionService)
    assert state.is_leased("tools")
    assert probe.open_calls == 0
    adapter = _actual_sdk_adapter(sdk_supervisor, operations=[])
    disp.attach_runtime_resolver(state, sdk_adapter=adapter)

    listed, call = state.tool_service.list_tools("tools")

    assert call.authorization_outcome == "ALLOW"
    payload = json.loads(listed.text)
    assert {tool["name"] for tool in payload["tools"]} == {"list_providers"}
    assert adapter_operations == ["open", "discover"]


@pytest.mark.asyncio
async def test_lazy_resolver_opens_discovers_registers_and_reuses_exact_connection(
    tmp_path: Path,
    sdk_supervisor: MCPAsyncSupervisor,
) -> None:
    """Removing resolver reuse would open or discover the leased server twice."""
    operations: list[str] = []
    process_control = _ControlledProcessControl()
    adapter = _actual_sdk_adapter(
        sdk_supervisor,
        operations=operations,
        process_control=process_control,
    )
    disp, _probe = _seed_side_effect_durable(tmp_path)
    state = await disp.disposition_for_new_session(
        "session-1",
        tmp_path,
        [_http_entry()],
        _allow,
    )

    assert operations == []
    disp.attach_runtime_resolver(state, sdk_adapter=adapter)
    assert operations == []
    with pytest.raises(TypeError, match="not serializable"):
        pickle.dumps(state.tool_service)

    listed, listed_call = state.tool_service.list_tools("tools")
    assert listed_call.authorization_outcome == "ALLOW"
    assert {tool["name"] for tool in json.loads(listed.text)["tools"]} == {"list_providers"}
    assert operations == ["open:tools", "discover:tools"]

    service = state.tool_service.ensure_server("tools")
    assert isinstance(service, AdapterBackedClientMcpToolService)
    assert object.__getattribute__(service, "_adapter") is adapter
    connection = object.__getattribute__(service, "_connection")
    assert connection.session_id == "session-1"

    second, second_call = state.tool_service.list_tools("tools")
    assert second_call.authorization_outcome == "ALLOW"
    assert second.text == listed.text
    assert operations == ["open:tools", "discover:tools"]

    state.close()
    state.close()
    assert connection.closed is True
    assert process_control.closes == 1


@pytest.mark.asyncio
async def test_rejected_lease_never_opens_or_registers(
    tmp_path: Path,
    sdk_supervisor: MCPAsyncSupervisor,
) -> None:
    operations: list[str] = []
    adapter = _actual_sdk_adapter(sdk_supervisor, operations=operations)
    disp = _disposition(tmp_path)

    async def reject(_params: dict[str, Any]) -> str:
        return "reject"

    state = await disp.disposition_for_new_session(
        "session-1",
        tmp_path,
        [_http_entry()],
        reject,
    )
    disp.attach_runtime_resolver(state, sdk_adapter=adapter)

    listed, call = state.tool_service.list_tools("tools")
    assert listed.text == "unavailable:unknown_server"
    assert call.authorization_outcome == "BLOCK"
    assert operations == []
    assert state.tool_service.ensure_server("tools") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("pages", "discover_error"),
    [
        ([{"notTools": []}], False),
        ([{"tools": []}] * (MAX_CATALOG_PAGES + 1), False),
        (_catalog_pages(), True),
    ],
    ids=["malformed-catalog", "over-budget-catalog", "sdk-discovery-error"],
)
async def test_lazy_failure_closes_opened_connection_and_registers_nothing(
    tmp_path: Path,
    sdk_supervisor: MCPAsyncSupervisor,
    pages: list[dict[str, object]],
    discover_error: bool,
) -> None:
    operations: list[str] = []
    process_control = _ControlledProcessControl()
    adapter = _actual_sdk_adapter(
        sdk_supervisor,
        operations=operations,
        pages_by_server={"tools": pages},
        discover_error_servers=frozenset({"tools"}) if discover_error else frozenset(),
        process_control=process_control,
    )
    disp, _probe = _seed_side_effect_durable(tmp_path)
    state = await disp.disposition_for_new_session(
        "session-1",
        tmp_path,
        [_http_entry()],
        _allow,
    )
    disp.attach_runtime_resolver(state, sdk_adapter=adapter)

    listed, call = state.tool_service.list_tools("tools")
    code = "DISCOVERY_FAILED" if discover_error else (
        "CATALOG_BUDGET_EXCEEDED" if len(pages) > MAX_CATALOG_PAGES else "CATALOG_MALFORMED_PAGE"
    )
    assert listed.text == f"unavailable:{code}"
    assert call.authorization_outcome == "BLOCK"
    assert operations == ["open:tools"] + ["discover:tools"] * min(len(pages), MAX_CATALOG_PAGES)
    assert process_control.closes == 1
    assert adapter._connections == {}
    assert state.tool_service._lookup("tools") is None

    repeated, repeated_call = state.tool_service.list_tools("tools")
    assert repeated.text == listed.text
    assert repeated_call.authorization_outcome == "BLOCK"
    assert operations == ["open:tools"] + ["discover:tools"] * min(len(pages), MAX_CATALOG_PAGES)
    assert process_control.closes == 1


@pytest.mark.asyncio
async def test_identity_mismatch_closes_opened_connection_and_registers_nothing(
    tmp_path: Path,
    sdk_supervisor: MCPAsyncSupervisor,
) -> None:
    operations: list[str] = []
    process_control = _ControlledProcessControl()
    adapter = _actual_sdk_adapter(
        sdk_supervisor,
        operations=operations,
        process_control=process_control,
    )
    disp, _probe = _seed_side_effect_durable(tmp_path)
    state = await disp.disposition_for_new_session(
        "session-1",
        tmp_path,
        [_http_entry()],
        _allow,
    )
    lease = state.lease_for("tools")
    assert lease is not None
    state._servers["tools"].lease = replace(lease, identity_fingerprint="mismatch")
    disp.attach_runtime_resolver(state, sdk_adapter=adapter)

    listed, call = state.tool_service.list_tools("tools")
    assert listed.text == "unavailable:SERVICE_UNAVAILABLE"
    assert call.authorization_outcome == "BLOCK"
    assert operations == ["open:tools", "discover:tools"]
    assert process_control.closes == 1
    assert adapter._connections == {}


@pytest.mark.asyncio
async def test_factory_exception_closes_opened_connection_and_registers_nothing(
    tmp_path: Path,
    sdk_supervisor: MCPAsyncSupervisor,
) -> None:
    operations: list[str] = []
    process_control = _ControlledProcessControl()
    adapter = _actual_sdk_adapter(
        sdk_supervisor,
        operations=operations,
        process_control=process_control,
    )
    disp, _probe = _seed_side_effect_durable(tmp_path)
    state = await disp.disposition_for_new_session(
        "session-1",
        tmp_path,
        [_http_entry()],
        _allow,
    )

    def failing_factory_builder(_adapter: object, _connection: object) -> object:
        def fail(**_kwargs: object) -> ClientMcpToolService:
            raise RuntimeError("controlled factory failure")

        return fail

    disp.attach_runtime_resolver(
        state,
        sdk_adapter=adapter,
        service_factory_builder=failing_factory_builder,
    )

    listed, call = state.tool_service.list_tools("tools")
    assert listed.text == "unavailable:DISCOVERY_FAILED"
    assert call.authorization_outcome == "BLOCK"
    assert operations == ["open:tools", "discover:tools"]
    assert process_control.closes == 1
    assert adapter._connections == {}


@pytest.mark.asyncio
async def test_generic_requires_and_call_routes_resolve_before_dispatch(
    tmp_path: Path,
    sdk_supervisor: MCPAsyncSupervisor,
) -> None:
    operations: list[str] = []
    adapter = _actual_sdk_adapter(
        sdk_supervisor,
        operations=operations,
        pages_by_server={"tools": _catalog_pages(write=True)},
    )
    disp, _probe = _seed_side_effect_durable(tmp_path)
    state = await disp.disposition_for_new_session(
        "session-1",
        tmp_path,
        [_http_entry()],
        _allow,
    )
    disp.attach_runtime_resolver(state, sdk_adapter=adapter)

    assert state.tool_service.requires_write_approval("tools", "delete_resource") is True
    assert operations == ["open:tools", "discover:tools"]

    output, call = state.tool_service.call_tool("tools", "list_providers", {})
    assert call.authorization_outcome == "ALLOW"
    assert output.text == "completed"
    assert operations == ["open:tools", "discover:tools", "call:tools:list_providers"]


@pytest.mark.asyncio
async def test_sessions_and_servers_never_share_lazy_connections_or_services(
    tmp_path: Path,
    sdk_supervisor: MCPAsyncSupervisor,
) -> None:
    operations: list[str] = []
    process_control = _ControlledProcessControl()
    adapter = _actual_sdk_adapter(
        sdk_supervisor,
        operations=operations,
        process_control=process_control,
    )
    disp, _probe = _seed_side_effect_durable(tmp_path)
    state_a = await disp.disposition_for_new_session(
        "session-a",
        tmp_path,
        [_http_entry(name="tools"), _http_entry(name="docs")],
        _allow,
    )
    state_b = await disp.disposition_for_new_session(
        "session-b",
        tmp_path,
        [_http_entry(name="tools")],
        _allow,
    )
    disp.attach_runtime_resolver(state_a, sdk_adapter=adapter)
    disp.attach_runtime_resolver(state_b, sdk_adapter=adapter)

    state_a.tool_service.list_tools("tools")
    state_a.tool_service.list_tools("docs")
    state_b.tool_service.list_tools("tools")

    services = (
        state_a.tool_service.ensure_server("tools"),
        state_a.tool_service.ensure_server("docs"),
        state_b.tool_service.ensure_server("tools"),
    )
    assert_no_offending_rows(services, lambda service: not (isinstance(service, AdapterBackedClientMcpToolService)), 'must hold for all: isinstance(service, AdapterBackedClientMcpToolService)')
    assert len({id(service) for service in services}) == 3
    connections = [object.__getattribute__(service, "_connection") for service in services]
    assert len({id(connection) for connection in connections}) == 3
    assert {connection.session_id for connection in connections} == {"session-a", "session-b"}
    assert operations == [
        "open:tools",
        "discover:tools",
        "open:docs",
        "discover:docs",
        "open:tools",
        "discover:tools",
    ]

    state_a.close()
    assert connections[0].closed is True
    assert connections[1].closed is True
    assert connections[2].closed is False
    state_b.close()
    assert connections[2].closed is True
    assert process_control.closes == 3


@pytest.mark.asyncio
async def test_unavailable_and_budget_failure_register_nothing(tmp_path: Path) -> None:
    probe = RecordingTransportProbe()
    disp = _disposition(tmp_path)

    async def reject(_params: dict[str, Any]) -> str:
        return "reject"

    rejected = await disp.disposition_for_new_session(
        "session-1",
        tmp_path,
        [_http_entry()],
        reject,
    )
    assert rejected.is_unavailable("tools")
    disp.materialize_tool_service(
        rejected,
        identity=_http_identity(),
        raw_tools=_catalog_pages(),
        workspace_root=tmp_path,
        service_factory=_recording_service_factory,
    )
    listed, call = rejected.tool_service.list_tools("tools")
    assert listed.text == "unavailable:unknown_server"
    assert call.authorization_outcome == "BLOCK"
    assert probe.open_calls == 0

    leased_disp, leased_probe = _seed_side_effect_durable(tmp_path)
    leased = await leased_disp.disposition_for_new_session(
        "session-1",
        tmp_path,
        [_http_entry()],
        _allow,
    )
    assert leased.is_leased("tools")
    leased_disp.materialize_tool_service(
        leased,
        identity=_http_identity(),
        raw_tools=_catalog_pages(),
        workspace_root=tmp_path,
        elapsed_seconds=30.1,
        service_factory=_recording_service_factory,
    )
    listed, call = leased.tool_service.list_tools("tools")
    assert listed.text == "unavailable:CATALOG_BUDGET_EXCEEDED"
    assert call.authorization_outcome == "BLOCK"
    assert leased_probe.open_calls == 0


@pytest.mark.asyncio
async def test_two_sessions_and_two_servers_do_not_cross_consume(tmp_path: Path) -> None:
    disp, probe = _seed_side_effect_durable(tmp_path)
    state_a = await disp.disposition_for_new_session(
        "session-a",
        tmp_path,
        [_http_entry(name="tools"), _http_entry(name="docs")],
        _allow,
    )
    state_b = await disp.disposition_for_new_session(
        "session-b",
        tmp_path,
        [_http_entry(name="tools")],
        _allow,
    )
    assert state_a is not state_b
    assert state_a.tool_service is not state_b.tool_service
    assert probe.open_calls == 0

    disp.materialize_tool_service(
        state_a,
        identity=_http_identity(name="tools"),
        raw_tools=_catalog_pages(write=True),
        workspace_root=tmp_path,
        service_factory=_recording_service_factory,
    )
    disp.materialize_tool_service(
        state_a,
        identity=_http_identity(name="docs"),
        raw_tools=_catalog_pages(),
        workspace_root=tmp_path,
        service_factory=_recording_service_factory,
    )
    disp.materialize_tool_service(
        state_b,
        identity=_http_identity(name="tools"),
        raw_tools=_catalog_pages(write=True),
        workspace_root=tmp_path,
        service_factory=_recording_service_factory,
    )
    assert probe.open_calls == 0

    tools_out, tools_call = state_a.tool_service.list_tools("tools")
    docs_out, docs_call = state_a.tool_service.list_tools("docs")
    assert tools_call.authorization_outcome == "ALLOW"
    assert docs_call.authorization_outcome == "ALLOW"
    assert {tool["name"] for tool in json.loads(tools_out.text)["tools"]} == {
        "list_providers",
        "delete_resource",
    }
    assert {tool["name"] for tool in json.loads(docs_out.text)["tools"]} == {"list_providers"}
    b_docs, b_docs_call = state_b.tool_service.list_tools("docs")
    assert b_docs.text == "unavailable:unknown_server"
    assert b_docs_call.authorization_outcome == "BLOCK"

    args = {"id": "abc"}
    approval_a = state_a.tool_service.issue_one_call_approval(
        _write_request(session_id="session-a", arguments=args)
    )
    assert approval_a is not None
    approval_b_wrong_session = state_b.tool_service.issue_one_call_approval(
        _write_request(session_id="session-a", arguments=args)
    )
    assert approval_b_wrong_session is None
    stolen, stolen_call = state_b.tool_service.call_tool(
        "tools",
        "delete_resource",
        args,
        one_call_approval=approval_a.token,
    )
    assert stolen_call.authorization_outcome != "ALLOW"
    assert "dispatched:" not in stolen.text

    output, call = state_a.tool_service.call_tool(
        "tools",
        "delete_resource",
        args,
        one_call_approval=approval_a.token,
    )
    assert call.authorization_outcome == "ALLOW"
    assert output.text == "dispatched:delete_resource"

    replay_out, replay = state_a.tool_service.call_tool(
        "tools",
        "delete_resource",
        args,
        one_call_approval=approval_a.token,
    )
    assert replay.authorization_outcome != "ALLOW"
    assert "dispatched:" not in replay_out.text

    hold_out, hold = state_a.tool_service.call_tool("tools", "delete_resource", args)
    assert hold.authorization_outcome != "ALLOW"
    assert "dispatched:" not in hold_out.text


# --- Seam 5: ClientMcpRuntime.close aggregate outcome (frozen matrix v3, R1) ---


class _RecordingAdapter:
    def __init__(self, calls: list[str], *, raise_on_close: bool = False) -> None:
        self._calls = calls
        self._raise_on_close = raise_on_close

    def close_all(self) -> None:
        self._calls.append("sdk")
        if self._raise_on_close:
            raise RuntimeError("sdk close failed")


class _RecordingEndpoint:
    def __init__(self, calls: list[str], *, raise_on_close: bool = False) -> None:
        self._calls = calls
        self._raise_on_close = raise_on_close

    def close(self) -> None:
        self._calls.append("endpoint")
        if self._raise_on_close:
            raise RuntimeError("endpoint close failed")


class _RecordingSupervisor:
    def __init__(
        self,
        calls: list[str],
        *,
        state: MCPSupervisorState = MCPSupervisorState.DEAD,
        raise_on_close: bool = False,
        state_after: MCPSupervisorState | None = None,
    ) -> None:
        self._calls = calls
        self._state = state
        self._raise_on_close = raise_on_close
        self._state_after = state_after

    @property
    def state(self) -> MCPSupervisorState:
        return self._state

    def close(self) -> None:
        self._calls.append("supervisor")
        if self._state_after is not None:
            self._state = self._state_after
        if self._raise_on_close:
            raise RuntimeError("supervisor close failed")


def _runtime(calls: list[str], *, adapter, supervisor, endpoint) -> ClientMcpRuntime:
    return ClientMcpRuntime(
        disposition=object(),
        supervisor=supervisor,
        sdk_adapter=adapter,
        candidate_endpoint=endpoint,
    )


def test_runtime_close_attempts_all_stages_in_order() -> None:
    # Row 4d: ordered attempts SDK -> endpoint -> supervisor despite injected failures.
    for sdk_fail, ep_fail in [(True, False), (False, True), (True, True)]:
        calls: list[str] = []
        outcome = _runtime(
            calls,
            adapter=_RecordingAdapter(calls, raise_on_close=sdk_fail),
            supervisor=_RecordingSupervisor(calls, state=MCPSupervisorState.DEAD),
            endpoint=_RecordingEndpoint(calls, raise_on_close=ep_fail),
        ).close()
        assert calls == ["sdk", "endpoint", "supervisor"]
        assert isinstance(outcome, ClientMcpShutdownOutcome)
        assert outcome.complete is False


def test_runtime_close_without_endpoint_skips_endpoint_stage() -> None:
    calls: list[str] = []
    runtime = ClientMcpRuntime(
        disposition=object(),
        supervisor=_RecordingSupervisor(calls, state=MCPSupervisorState.DEAD),
        sdk_adapter=_RecordingAdapter(calls),
        candidate_endpoint=None,
    )
    outcome = runtime.close()
    assert calls == ["sdk", "supervisor"]
    assert outcome.endpoint_closed is True
    assert outcome.complete is True


def test_supervisor_close_raise_after_dead_is_non_clean() -> None:
    # Row 4a: supervisor reaches DEAD then close() raises -> aggregate non-clean.
    calls: list[str] = []
    runtime = _runtime(
        calls,
        adapter=_RecordingAdapter(calls),
        supervisor=_RecordingSupervisor(
            calls, state=MCPSupervisorState.DEAD, raise_on_close=True
        ),
        endpoint=_RecordingEndpoint(calls),
    )
    outcome = runtime.close()
    assert outcome.sdk_closed is True
    assert outcome.endpoint_closed is True
    assert outcome.supervisor_closed is False
    assert outcome.supervisor_state is MCPSupervisorState.DEAD
    assert outcome.complete is False


def test_stage_failure_persists_across_repeated_close() -> None:
    # Row 4b: a recorded stage failure is sticky across repeated runtime.close().
    calls: list[str] = []
    adapter = _RecordingAdapter(calls, raise_on_close=True)
    supervisor = _RecordingSupervisor(calls, state=MCPSupervisorState.DEAD)
    runtime = _runtime(calls, adapter=adapter, supervisor=supervisor, endpoint=_RecordingEndpoint(calls))

    first = runtime.close()
    assert first.sdk_closed is False
    assert first.complete is False

    # Second call: every stage now returns normally, supervisor DEAD.
    adapter._raise_on_close = False
    second = runtime.close()
    assert second.sdk_closed is True
    assert second.supervisor_state is MCPSupervisorState.DEAD
    assert second.complete is False  # prior failure retained -> no invented success


def test_pending_supervisor_then_dead_completes() -> None:
    """Row 4c with a REAL supervisor: a still-STOPPING supervisor (no stage exception)
    is pending, not a failure, and completes on a later close once its real cleanup
    has actually finished -- no double's state is mutated to manufacture the result."""
    import threading

    from optimus.mcp.client_supervisor import MCPSupervisorError

    started = threading.Event()
    cleanup_entered = threading.Event()
    release = threading.Event()
    sup = MCPAsyncSupervisor(close_join_timeout_seconds=0.05)
    sup.start()
    owner = sup._thread  # noqa: SLF001
    assert owner is not None

    async def op() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cleanup_entered.set()
            release.wait(timeout=30)
            raise

    def worker() -> None:
        try:
            sup.submit(op(), timeout_seconds=0.05)  # timeout initiates cancellation
        except MCPSupervisorError:
            pass

    w = threading.Thread(target=worker, name="row4c-submit")
    w.start()
    calls: list[str] = []
    runtime = ClientMcpRuntime(
        disposition=object(), supervisor=sup, sdk_adapter=_RecordingAdapter(calls)
    )
    try:
        assert started.wait(2)
        assert cleanup_entered.wait(2)  # cleanup held -> real pending shutdown
        first = runtime.close()
        assert first.supervisor_state is MCPSupervisorState.STOPPING
        assert first.supervisor_closed is True  # no exception: pending, not a failure
        assert first.complete is False
    finally:
        release.set()
        w.join(5)
        owner.join(5)

    assert_threads_stopped([owner], 'owner is still alive')
    second = runtime.close()
    assert second.supervisor_state is MCPSupervisorState.DEAD
    assert second.complete is True


@pytest.mark.parametrize("page_count", [1, 2])
def test_real_client_session_resolves_all_pages(
    tmp_path: Path, sdk_supervisor: MCPAsyncSupervisor, page_count: int,
) -> None:
    """A real ListToolsResult must reach a usable, complete identity-bound catalog."""
    from mcp import Client, ClientSession
    from mcp.server import Server
    from mcp.types import ListToolsResult, Tool

    cursors: list[str | None] = []

    async def list_tools(_ctx: Any, params: Any) -> ListToolsResult:
        cursor = params.cursor if params else None
        cursors.append(cursor)
        assert cursor in (None, "next-page")
        index = 1 if cursor is None else 2
        return ListToolsResult(
            tools=[Tool(name=f"lookup_{index}", description="Safe lookup.", inputSchema={"type": "object"})],
            nextCursor="next-page" if page_count == 2 and index == 1 else None,
        )

    async def scenario() -> None:
        server = Server("real-test", on_list_tools=list_tools)
        async with Client(server, mode="legacy") as client:
            assert isinstance(client.session, ClientSession)
            adapter = ClientMcpSdkAdapter(
                supervisor=sdk_supervisor,
                session_factory=lambda _cap: client.session,
                http_client_factory=lambda: SimpleNamespace(follow_redirects=False, trust_env=False),
                stdio_transport_factory=lambda _cap: None,
                process_control=_ControlledProcessControl(),
            )
            disp = _disposition(tmp_path)
            state = await disp.disposition_for_new_session("real-session", tmp_path, [_http_entry()], _allow)
            disp.attach_runtime_resolver(state, sdk_adapter=adapter)
            try:
                listed, audit = await asyncio.to_thread(state.tool_service.list_tools, "tools")
                assert audit.authorization_outcome == "ALLOW", listed.text
                assert {t["name"] for t in json.loads(listed.text)["tools"]} == (
                    {"lookup_1"} if page_count == 1 else {"lookup_1", "lookup_2"}
                )
                service = state.tool_service._lookup("tools")
                catalog = object.__getattribute__(service, "_catalog")
                assert catalog.tools[0].input_schema == {"type": "object"}
                assert cursors == ([None] if page_count == 1 else [None, "next-page"])
                repeated, _ = await asyncio.to_thread(state.tool_service.list_tools, "tools")
                assert repeated.text == listed.text
                assert len(cursors) == page_count
            finally:
                await asyncio.to_thread(state.close)

    sdk_supervisor.submit(scenario(), timeout_seconds=20)


@pytest.mark.asyncio
async def test_discovery_elapsed_reaches_catalog_and_is_visible(
    tmp_path: Path, sdk_supervisor: MCPAsyncSupervisor, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dropping measured elapsed would admit a completed over-budget discovery."""
    import optimus.mcp.client_disposition as module

    ticks = iter([100.0, 131.0])
    monkeypatch.setattr(module, "monotonic", lambda: next(ticks), raising=False)
    adapter = _actual_sdk_adapter(sdk_supervisor, operations=[])
    adapter._operation_timeout_seconds = 60.0
    disp = _disposition(tmp_path)
    state = await disp.disposition_for_new_session("elapsed", tmp_path, [_http_entry()], _allow)
    disp.attach_runtime_resolver(state, sdk_adapter=adapter)
    listed, audit = state.tool_service.list_tools("tools")
    assert listed.text == "unavailable:CATALOG_BUDGET_EXCEEDED"
    assert audit.authorization_outcome == "BLOCK"
    assert adapter._connections == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("error_kind", ["sdk-code", "catalog-code", "unknown-code", "untyped-code"])
async def test_discovery_failure_exposes_only_allowlisted_typed_codes(
    tmp_path: Path, sdk_supervisor: MCPAsyncSupervisor, monkeypatch: pytest.MonkeyPatch, error_kind: str,
) -> None:
    """Raw remote messages and forged error codes must not reach list output."""
    from optimus.mcp.client_catalog import ClientMcpCatalogError
    from optimus.mcp.client_sdk import ClientMcpSdkError

    remote_marker = "remote-sensitive-marker"
    errors = {
        "sdk-code": ClientMcpSdkError("OPERATION_TIMEOUT"),
        "catalog-code": ClientMcpCatalogError("CATALOG_CURSOR_LOOP"),
        "unknown-code": ClientMcpSdkError(remote_marker),
        "untyped-code": RuntimeError(remote_marker),
    }
    errors["untyped-code"].code = "OPERATION_TIMEOUT"
    adapter = _actual_sdk_adapter(sdk_supervisor, operations=[])
    def fail(_connection: object) -> Any:
        raise errors[error_kind]
    monkeypatch.setattr(adapter, "discover", fail)
    disp = _disposition(tmp_path)
    state = await disp.disposition_for_new_session("failure", tmp_path, [_http_entry()], _allow)
    disp.attach_runtime_resolver(state, sdk_adapter=adapter)
    listed, audit = state.tool_service.list_tools("tools")
    expected = {"sdk-code": "OPERATION_TIMEOUT", "catalog-code": "CATALOG_CURSOR_LOOP"}.get(error_kind, "DISCOVERY_FAILED")
    assert listed.text == f"unavailable:{expected}"
    assert remote_marker not in repr((listed, audit))
    assert audit.authorization_outcome == "BLOCK"
    assert adapter._connections == {}
    unknown, _ = state.tool_service.list_tools("unknown")
    assert unknown.text == "unavailable:unknown_server"
    # v2 intentionally changes list discovery diagnostics only; call delivery is out of scope.
    called, _ = state.tool_service.call_tool("tools", "lookup", {})
    assert called.text == "unavailable:unknown_server"
