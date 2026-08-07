"""RED/GREEN contract for client MCP durable trust and session leases (P11-FU-9 Task 2)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from optimus.acp.launch_approvals import (
    LAUNCH_POLICY_COMPATIBILITY,
    KeyringApprovalStore,
)
from optimus.mcp.client_config import ClientMcpSafeIdentity
from optimus.mcp.client_trust import (
    MCP_POLICY_COMPATIBILITY,
    ClientMcpDurableRecord,
    ClientMcpDurableStore,
    ClientMcpLeaseAuthority,
    ClientMcpTrustError,
    compute_identity_fingerprint,
    compute_record_hmac,
    derive_credential_fingerprint_key,
    derive_ipc_auth_key,
    derive_record_hmac_key,
    write_client_mcp_durable_from_fingerprint,
)


class FakeKeyring:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        return self._store.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self._store[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        self._store.pop((service, key), None)


def _identity(*, target: str = "https://mcp.example.com/a", name: str = "tools") -> ClientMcpSafeIdentity:
    return ClientMcpSafeIdentity(
        transport="http",
        server_name=name,
        canonical_target=target,
        arguments=(),
        credential_name_fingerprints=("fp-header-1",),
    )


def _store(tmp_path: Path, *, hmac_key: bytes = b"0" * 32) -> tuple[KeyringApprovalStore, ClientMcpDurableStore, FakeKeyring]:
    keyring = FakeKeyring()
    launch = KeyringApprovalStore(keyring_backend=keyring, runtime_root=tmp_path, hmac_key=hmac_key)
    client = ClientMcpDurableStore(keyring_backend=keyring, hmac_key=launch.hmac_key)
    return launch, client, keyring


def test_policy_and_hmac_domains_are_separated_from_launch_approvals(tmp_path: Path) -> None:
    assert MCP_POLICY_COMPATIBILITY != LAUNCH_POLICY_COMPATIBILITY
    hmac_root = b"root-hmac-key-for-domain-separation!!"
    record_key = derive_record_hmac_key(hmac_root)
    cred_key = derive_credential_fingerprint_key(hmac_root)
    ipc_key = derive_ipc_auth_key(hmac_root)
    assert record_key != hmac_root
    assert cred_key != hmac_root
    assert ipc_key != hmac_root
    assert len({record_key, cred_key, ipc_key}) == 3

    launch, client, keyring = _store(tmp_path, hmac_key=hmac_root)
    identity = _identity()
    fingerprint = compute_identity_fingerprint(identity, hmac_key=hmac_root)
    record = ClientMcpDurableRecord.build(
        workspace_digest="a" * 64,
        identity=identity,
        identity_fingerprint=fingerprint,
        effect_ceiling="non_mutating",
        hmac_key=hmac_root,
    )
    client.write(record)
    assert launch.read_durable("a" * 64) is None
    raw_keys = [key for (_service, key) in keyring._store]
    assert any(key.startswith("client-mcp:") for key in raw_keys)
    assert not any(key == f"durable:{'a' * 64}" for key in raw_keys)


def test_hmac_tamper_rejects_durable_record(tmp_path: Path) -> None:
    _, client, keyring = _store(tmp_path)
    identity = _identity()
    fingerprint = compute_identity_fingerprint(identity, hmac_key=b"0" * 32)
    record = ClientMcpDurableRecord.build(
        workspace_digest="b" * 64,
        identity=identity,
        identity_fingerprint=fingerprint,
        effect_ceiling="non_mutating",
        hmac_key=b"0" * 32,
    )
    client.write(record)
    entry_key = client.entry_key("b" * 64, identity.server_name, fingerprint)
    raw = keyring.get_password(client.service_name, entry_key)
    assert raw is not None
    import json

    payload = json.loads(raw)
    flipped = "0" if payload["record_hmac"][-1] != "0" else "1"
    payload["record_hmac"] = payload["record_hmac"][:-1] + flipped
    keyring.set_password(client.service_name, entry_key, json.dumps(payload, separators=(",", ":"), sort_keys=True))
    with pytest.raises(ClientMcpTrustError) as exc_info:
        client.read("b" * 64, identity.server_name, fingerprint)
    assert exc_info.value.code == "INTEGRITY_FAILURE"


def test_records_are_keyed_by_workspace_name_and_identity(tmp_path: Path) -> None:
    _, client, _keyring = _store(tmp_path)
    hmac_key = b"0" * 32
    first = _identity(target="https://mcp.example.com/a")
    second = _identity(target="https://mcp.example.com/b")
    fp1 = compute_identity_fingerprint(first, hmac_key=hmac_key)
    fp2 = compute_identity_fingerprint(second, hmac_key=hmac_key)
    assert fp1 != fp2

    client.write(
        ClientMcpDurableRecord.build(
            workspace_digest="c" * 64,
            identity=first,
            identity_fingerprint=fp1,
            effect_ceiling="non_mutating",
            hmac_key=hmac_key,
        )
    )
    assert client.read("c" * 64, "tools", fp1) is not None
    assert client.read("c" * 64, "tools", fp2) is None
    assert client.read("d" * 64, "tools", fp1) is None
    assert client.read("c" * 64, "other", fp1) is None


def test_changed_identity_requires_new_ceremony(tmp_path: Path) -> None:
    _, client, _keyring = _store(tmp_path)
    hmac_key = b"0" * 32
    original = _identity(target="https://mcp.example.com/a")
    changed = _identity(target="https://mcp.example.com/changed")
    fp_original = compute_identity_fingerprint(original, hmac_key=hmac_key)
    fp_changed = compute_identity_fingerprint(changed, hmac_key=hmac_key)
    client.write(
        ClientMcpDurableRecord.build(
            workspace_digest="e" * 64,
            identity=original,
            identity_fingerprint=fp_original,
            effect_ceiling="non_mutating",
            hmac_key=hmac_key,
        )
    )
    authority = ClientMcpLeaseAuthority(store=client)
    assert authority.lookup_durable("e" * 64, "tools", fp_original) is not None
    assert authority.lookup_durable("e" * 64, "tools", fp_changed) is None


def test_default_ceiling_is_non_mutating_and_side_effect_eligible_persists(tmp_path: Path) -> None:
    _, client, _keyring = _store(tmp_path)
    hmac_key = b"0" * 32
    identity = _identity()
    fingerprint = compute_identity_fingerprint(identity, hmac_key=hmac_key)
    default_record = ClientMcpDurableRecord.build(
        workspace_digest="f" * 64,
        identity=identity,
        identity_fingerprint=fingerprint,
        hmac_key=hmac_key,
    )
    assert default_record.effect_ceiling == "non_mutating"
    client.write(default_record)
    assert client.read("f" * 64, "tools", fingerprint).effect_ceiling == "non_mutating"

    eligible = ClientMcpDurableRecord.build(
        workspace_digest="g" * 64,
        identity=identity,
        identity_fingerprint=fingerprint,
        effect_ceiling="side_effect_eligible",
        hmac_key=hmac_key,
    )
    client.write(eligible)
    assert client.read("g" * 64, "tools", fingerprint).effect_ceiling == "side_effect_eligible"


def test_allow_once_lease_is_session_only_and_does_not_write_durable(tmp_path: Path) -> None:
    _, client, _keyring = _store(tmp_path)
    hmac_key = b"0" * 32
    identity = _identity()
    fingerprint = compute_identity_fingerprint(identity, hmac_key=hmac_key)
    authority = ClientMcpLeaseAuthority(store=client)
    lease = authority.acquire_allow_once(
        session_id="session-1",
        workspace_digest="h" * 64,
        identity=identity,
        identity_fingerprint=fingerprint,
    )
    assert lease.session_id == "session-1"
    assert lease.effect_ceiling == "non_mutating"
    assert lease.identity_fingerprint == fingerprint
    assert client.read("h" * 64, "tools", fingerprint) is None
    assert authority.lookup_durable("h" * 64, "tools", fingerprint) is None


def test_record_hmac_uses_derived_domain_key(tmp_path: Path) -> None:
    hmac_key = b"0" * 32
    identity = _identity()
    fingerprint = compute_identity_fingerprint(identity, hmac_key=hmac_key)
    record = ClientMcpDurableRecord.build(
        workspace_digest="i" * 64,
        identity=identity,
        identity_fingerprint=fingerprint,
        effect_ceiling="non_mutating",
        hmac_key=hmac_key,
    )
    assert record.record_hmac == compute_record_hmac(record, hmac_key=hmac_key)
    tampered = replace(record, effect_ceiling="side_effect_eligible")
    assert compute_record_hmac(tampered, hmac_key=hmac_key) != record.record_hmac


def test_durable_record_never_contains_raw_configuration(tmp_path: Path) -> None:
    _, client, _keyring = _store(tmp_path)
    hmac_key = b"0" * 32
    identity = _identity()
    fingerprint = compute_identity_fingerprint(identity, hmac_key=hmac_key)
    record = ClientMcpDurableRecord.build(
        workspace_digest="j" * 64,
        identity=identity,
        identity_fingerprint=fingerprint,
        effect_ceiling="non_mutating",
        hmac_key=hmac_key,
    )
    client.write(record)
    stored = client.read("j" * 64, "tools", fingerprint)
    assert stored is not None
    payload = stored.to_safe_dict()
    assert "headers" not in payload
    assert "env" not in payload
    assert "Authorization" not in repr(payload)
    assert payload["policy_compatibility"] == MCP_POLICY_COMPATIBILITY


def test_write_rejects_fingerprint_that_does_not_match_identity(tmp_path: Path) -> None:
    _, client, _keyring = _store(tmp_path)
    hmac_key = b"0" * 32
    identity = _identity(target="https://mcp.example.com/real")
    real_fp = compute_identity_fingerprint(identity, hmac_key=hmac_key)
    with pytest.raises(ClientMcpTrustError) as exc_info:
        write_client_mcp_durable_from_fingerprint(
            store=client,
            workspace_digest="k" * 64,
            identity=identity,
            rendered_fingerprint="totally-made-up-not-derived-from-anything",
        )
    assert exc_info.value.code == "IDENTITY_MISMATCH"
    assert client.read("k" * 64, "tools", real_fp) is None
    assert client.read("k" * 64, "tools", "totally-made-up-not-derived-from-anything") is None


def test_write_accepts_only_derived_identity_fingerprint(tmp_path: Path) -> None:
    _, client, _keyring = _store(tmp_path)
    hmac_key = b"0" * 32
    identity = _identity(target="https://mcp.example.com/bound")
    fingerprint = compute_identity_fingerprint(identity, hmac_key=hmac_key)
    record = write_client_mcp_durable_from_fingerprint(
        store=client,
        workspace_digest="l" * 64,
        identity=identity,
        rendered_fingerprint=fingerprint,
    )
    assert record.identity_fingerprint == fingerprint
    stored = client.read("l" * 64, "tools", fingerprint)
    assert stored is not None
    assert stored.canonical_target == identity.canonical_target
