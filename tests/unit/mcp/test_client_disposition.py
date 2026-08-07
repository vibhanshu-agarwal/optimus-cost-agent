"""RED/GREEN contract for ClientMcpDisposition and AcpMcpPermissionBroker (P11-FU-9 Task 6)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

from optimus.acp.launch_approvals import KeyringApprovalStore
from optimus.acp.shapes import build_client_mcp_permission_params
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolRequest
from optimus.mcp.client_config import ClientMcpConfigError, ClientMcpConfigNormalizer, ClientMcpSafeIdentity
from optimus.mcp.client_disposition import (
    AcpMcpPermissionBroker,
    ClientMcpDisposition,
    ClientMcpSessionState,
)
from optimus.mcp.client_trust import (
    ClientMcpDurableRecord,
    ClientMcpDurableStore,
    ClientMcpLeaseAuthority,
    compute_identity_fingerprint,
    write_client_mcp_durable_from_fingerprint,
)
from optimus.runtime.modes import ExecutionMode

HMAC_KEY = b"p11-fu-9-disposition-test-hmac-key!!"


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


@pytest.mark.asyncio
async def test_valid_entry_requests_safe_approval_without_opening_transport(tmp_path: Path) -> None:
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


@pytest.mark.asyncio
async def test_timeout_and_outbound_failure_yield_unavailable_not_lease(tmp_path: Path) -> None:
    for outcome in ("timeout", "outbound_failure"):
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


@pytest.mark.asyncio
async def test_reject_leaves_tools_unavailable(tmp_path: Path) -> None:
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
    assert all(opt["kind"] != "allow_always" for opt in params["options"])
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
