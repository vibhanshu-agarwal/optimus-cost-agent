"""RED/GREEN contract for pending client-MCP candidate local IPC (P11-FU-9 Task 2)."""

from __future__ import annotations

import os
import tempfile
import threading
import time
from multiprocessing.connection import Client
from pathlib import Path

import pytest

from optimus.mcp.client_config import ClientMcpSafeIdentity
from optimus.mcp.client_trust import derive_ipc_auth_key
from optimus.mcp.local_ipc import (
    LocalIpcError,
    PendingClientMcpCandidate,
    PendingClientMcpCandidateEndpoint,
    SafeCandidateSnapshot,
    default_local_candidate_address,
    reject_network_endpoint_address,
)


def _identity(*, target: str = "https://mcp.example.com/a") -> ClientMcpSafeIdentity:
    return ClientMcpSafeIdentity(
        transport="http",
        server_name="tools",
        canonical_target=target,
        arguments=(),
        credential_name_fingerprints=("fp-1",),
    )


def _candidate(
    *,
    workspace_digest: str = "a" * 64,
    session_id: str = "session-1",
    target: str = "https://mcp.example.com/a",
    rendered_fingerprint: str = "render-fp-1",
) -> PendingClientMcpCandidate:
    return PendingClientMcpCandidate(
        workspace_digest=workspace_digest,
        session_id=session_id,
        identity=_identity(target=target),
        rendered_fingerprint=rendered_fingerprint,
        provenance="client_supplied_acp",
        scanner_rule_ids=(),
    )


def test_default_address_is_local_af_pipe_or_af_unix() -> None:
    kind, address = default_local_candidate_address(token="abc123")
    if os.name == "nt":
        assert kind == "af_pipe"
        assert address.startswith("\\\\.\\pipe\\")
    else:
        assert kind == "af_unix"
        assert Path(address).parent == Path(tempfile.gettempdir())
        assert address.endswith(".sock")


def test_network_endpoint_addresses_are_rejected() -> None:
    with pytest.raises(ValueError) as tcp:
        reject_network_endpoint_address(("127.0.0.1", 8765))
    assert "network" in str(tcp.value).lower() or "endpoint" in str(tcp.value).lower()

    with pytest.raises(ValueError):
        reject_network_endpoint_address("tcp://127.0.0.1:8765")
    with pytest.raises(ValueError):
        reject_network_endpoint_address("127.0.0.1:8765")


def test_successors_are_bounded_and_retirement_is_session_owned():
    endpoint = PendingClientMcpCandidateEndpoint(authkey=b"bounded-local-candidates")
    try:
        first = endpoint.publish(_candidate(session_id="one"))
        second = endpoint.publish(_candidate(session_id="one"))
        other = endpoint.publish(_candidate(session_id="two"))
        assert endpoint.pending_count == 2
        assert not endpoint.retire(second, session_id="two")
        with pytest.raises(LookupError):
            endpoint.consume_snapshot(first)
        assert endpoint.retire_session("one") == 1
        assert endpoint.retire_session("one") == 0
        assert endpoint.consume_snapshot(other).session_id == "two"
    finally:
        endpoint.close()


def test_real_listener_restart_uses_fresh_address_and_joins_captured_generation():
    endpoint = PendingClientMcpCandidateEndpoint(authkey=b"owned-generation-test")
    addresses = []
    try:
        for _ in range(3):
            candidate = endpoint.publish(_candidate())
            addresses.append(endpoint.endpoint_address)
            thread = endpoint._thread
            assert thread is not None and thread.is_alive()
            assert endpoint.retire(candidate, session_id="session-1")
            assert not thread.is_alive()
        assert len(set(addresses)) == 3
    finally:
        endpoint.close()


def test_incomplete_listener_stop_retains_ownership_and_refuses_replacement():
    endpoint = PendingClientMcpCandidateEndpoint(authkey=b"held-owned-authentication")
    peer = None
    thread = None
    try:
        candidate = endpoint.publish(_candidate())
        _, address = endpoint.endpoint_address
        thread = endpoint._thread
        listener = endpoint._listener
        # Hold the server after its challenge: a connected local peer has not answered.
        peer = Client(address)
        assert peer.poll(1)
        assert peer.recv_bytes()
        with pytest.raises(LocalIpcError, match="ipc_stop_incomplete"):
            endpoint.retire(candidate, session_id="session-1")
        assert endpoint._thread is thread and thread.is_alive()
        assert endpoint._listener is listener
        with pytest.raises(LocalIpcError, match="ipc_stop_incomplete"):
            endpoint.publish(_candidate())
    finally:
        if peer is not None:
            peer.close()
        if thread is not None:
            thread.join(2)
            assert not thread.is_alive()
        endpoint.close()


def test_concurrent_successor_is_not_erased_by_retiring_the_previous_candidate(monkeypatch):
    endpoint = PendingClientMcpCandidateEndpoint(authkey=b"concurrent-candidate-owner")
    retired, publish_done = threading.Event(), threading.Event()
    real_stop = endpoint._stop_listener
    def held_stop():
        retired.set()
        assert publish_done.wait(1)
        real_stop()
    monkeypatch.setattr(endpoint, "_stop_listener", held_stop)
    prior = endpoint.publish(_candidate())
    errors = []
    def retire():
        try:
            assert endpoint.retire(prior, session_id="session-1")
        except BaseException as exc:
            errors.append(exc)
    worker = threading.Thread(target=retire)
    worker.start()
    try:
        assert retired.wait(1)
        successor = endpoint.publish(_candidate())
        publish_done.set()
        worker.join(2)
        assert not worker.is_alive() and not errors
        assert endpoint.pending_count == 1
        assert endpoint.consume_snapshot(successor).session_id == "session-1"
    finally:
        publish_done.set()
        worker.join(2)
        monkeypatch.setattr(endpoint, "_stop_listener", real_stop)
        endpoint.close()


def test_ipc_auth_key_is_derived_from_hmac_root() -> None:
    root = b"0" * 32
    derived = derive_ipc_auth_key(root)
    assert derived != root
    assert derive_ipc_auth_key(root) == derived
    assert len(derived) >= 16


def test_publish_and_one_time_consume_snapshot() -> None:
    authkey = derive_ipc_auth_key(b"0" * 32)
    endpoint = PendingClientMcpCandidateEndpoint(authkey=authkey)
    try:
        candidate_id = endpoint.publish(_candidate())
        snapshot = endpoint.consume_snapshot(candidate_id)
        assert isinstance(snapshot, SafeCandidateSnapshot)
        assert snapshot.candidate_id == candidate_id
        assert snapshot.rendered_fingerprint == "render-fp-1"
        assert snapshot.provenance == "client_supplied_acp"
        assert "https://mcp.example.com/a" in snapshot.safe_identity_summary
        with pytest.raises(LookupError):
            endpoint.consume_snapshot(candidate_id)
    finally:
        endpoint.close()


def test_concurrent_matching_candidates_share_identity_but_consume_independently() -> None:
    authkey = derive_ipc_auth_key(b"0" * 32)
    endpoint = PendingClientMcpCandidateEndpoint(authkey=authkey)
    try:
        first = endpoint.publish(_candidate(session_id="s1", rendered_fingerprint="same-fp"))
        second = endpoint.publish(_candidate(session_id="s2", rendered_fingerprint="same-fp"))
        snap1 = endpoint.consume_snapshot(first)
        snap2 = endpoint.consume_snapshot(second)
        assert snap1.rendered_fingerprint == snap2.rendered_fingerprint == "same-fp"
        assert snap1.workspace_digest == snap2.workspace_digest
        assert snap1.server_name == snap2.server_name
        with pytest.raises(LookupError):
            endpoint.consume_snapshot(first)
    finally:
        endpoint.close()


def test_listener_is_pending_only_and_exposes_no_approve_operation() -> None:
    authkey = derive_ipc_auth_key(b"0" * 32)
    endpoint = PendingClientMcpCandidateEndpoint(authkey=authkey)
    try:
        assert endpoint.is_listening is False
        candidate_id = endpoint.publish(_candidate())
        assert endpoint.is_listening is True
        assert not hasattr(endpoint, "approve")
        endpoint.consume_snapshot(candidate_id)
        assert endpoint.pending_count == 0
        assert endpoint.is_listening is False
    finally:
        endpoint.close()


def test_remote_client_can_consume_via_local_ipc_only() -> None:
    authkey = derive_ipc_auth_key(b"1" * 32)
    endpoint = PendingClientMcpCandidateEndpoint(authkey=authkey)
    try:
        candidate_id = endpoint.publish(_candidate(rendered_fingerprint="via-ipc"))
        kind, address = endpoint.endpoint_address
        assert kind in {"af_pipe", "af_unix"}

        result: list[SafeCandidateSnapshot] = []
        error: list[BaseException] = []

        def _client() -> None:
            try:
                result.append(
                    PendingClientMcpCandidateEndpoint.consume_remote_snapshot(
                        address=address,
                        authkey=authkey,
                        candidate_id=candidate_id,
                    )
                )
            except BaseException as exc:  # noqa: BLE001 - capture for parent thread
                error.append(exc)

        thread = threading.Thread(target=_client)
        thread.start()
        thread.join(timeout=5)
        assert not error
        assert result and result[0].rendered_fingerprint == "via-ipc"
        with pytest.raises(LookupError):
            endpoint.consume_snapshot(candidate_id)
    finally:
        endpoint.close()


def test_remote_consume_after_listener_stop_fails_quickly() -> None:
    """Windows named-pipe Client() blocks forever if the Listener is already gone.

    Ceremony CLI must fail-closed with a bounded wait, not hang the process.
    """
    authkey = derive_ipc_auth_key(b"2" * 32)
    endpoint = PendingClientMcpCandidateEndpoint(authkey=authkey)
    try:
        candidate_id = endpoint.publish(_candidate())
        _kind, address = endpoint.endpoint_address
        endpoint.consume_snapshot(candidate_id)
        assert endpoint.is_listening is False
        started = time.monotonic()
        with pytest.raises((LookupError, LocalIpcError)):
            PendingClientMcpCandidateEndpoint.consume_remote_snapshot(
                address=address,
                authkey=authkey,
                candidate_id=candidate_id,
                timeout_seconds=1.0,
            )
        assert time.monotonic() - started < 3.0
    finally:
        endpoint.close()
