"""Scoped E3 approval operations tested with the Windows-size fake keyring."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from optimus.acp.launch_approvals import ApprovalError, DurableWriteIntent, KeyringApprovalStore
from optimus.acp.launch_gate import LaunchGateError, verify_exact_durable
from tests.unit.acp.test_launch_approvals_multipart import WindowsLimitKeyring, _record, _store


def test_exact_store_open_does_not_create_integrity_key(tmp_path: Path) -> None:
    keyring = WindowsLimitKeyring()
    with pytest.raises(ApprovalError, match="HMAC_KEY_MISSING"):
        KeyringApprovalStore.open_existing(keyring_backend=keyring, runtime_root=tmp_path)
    assert not keyring.keys()


def test_scoped_publish_records_multipart_intent_before_mutating_and_revokes_exactly(tmp_path: Path) -> None:
    keyring = WindowsLimitKeyring()
    store = _store(tmp_path, keyring)
    record = _record(1500)
    intents = []

    def persist(intent):
        assert not keyring.keys()
        assert intent.approval_id == record.approval_id
        assert intent.generation is not None
        intents.append(intent)

    store.publish_durable_if_absent(record, "b" * 64, persist)
    intent, = intents
    assert store.read_exact_durable(record.workspace_digest, "b" * 64, record.approval_id) == record
    store.revoke_exact_durable(intent)
    assert not keyring.keys()


def test_exact_publish_checks_legacy_and_current_under_lock(tmp_path: Path) -> None:
    keyring = WindowsLimitKeyring()
    store = _store(tmp_path, keyring)
    legacy = _record(digest="b" * 64)
    store.write_durable(legacy)
    with pytest.raises(ApprovalError, match="APPROVAL_ALREADY_EXISTS"):
        store.publish_durable_if_absent(_record(), legacy.workspace_digest, lambda _: pytest.fail("intent written"))
    assert store.read_durable(legacy.workspace_digest) == legacy


def test_revoke_an_owned_manifest_when_a_part_is_missing(tmp_path: Path) -> None:
    keyring = WindowsLimitKeyring()
    store = _store(tmp_path, keyring)
    record = _record(1500)
    intent = store.publish_durable_if_absent(record, "b" * 64, lambda _: None)
    store._delete(next(key for key in keyring.keys() if "#" in key))
    assert store.revoke_exact_durable(intent)
    assert not store.revoke_exact_durable(intent)
    assert not keyring.keys()


def test_publish_refuses_existing_record_and_reconciles_lost_acknowledgement(tmp_path: Path) -> None:
    keyring = WindowsLimitKeyring()
    store = _store(tmp_path, keyring)
    record = _record()
    key = f"durable:{record.workspace_digest}"
    store.write_durable(record)
    with pytest.raises(ApprovalError, match="APPROVAL_ALREADY_EXISTS"):
        store.publish_durable_if_absent(_record(), "b" * 64, lambda _: pytest.fail("intent written"))
    store._delete(key)
    intents = []
    real_set = keyring.set_password

    def lose_ack(service, name, value):
        real_set(service, name, value)
        if name == key:
            raise OSError("injected acknowledgement loss")

    keyring.set_password = lose_ack
    with pytest.raises(ApprovalError, match="APPROVAL_STORE_WRITE_FAILED"):
        store.publish_durable_if_absent(record, "b" * 64, intents.append)
    assert not store.revoke_exact_durable(intents[0])
    assert not keyring.keys()


def test_recovery_scrubs_only_verified_orphan_parts(tmp_path: Path) -> None:
    class Interrupted(BaseException):
        pass

    keyring = WindowsLimitKeyring()
    store = _store(tmp_path, keyring)
    record = _record(1500)
    intents = []

    def interrupt(op: str, key: str) -> None:
        if op == "set" and key == f"durable:{record.workspace_digest}":
            raise Interrupted()

    keyring.hook = interrupt
    with pytest.raises(Interrupted):
        store.publish_durable_if_absent(record, "b" * 64, intents.append)
    keyring.hook = None
    assert len(keyring.keys()) == 2
    store.revoke_exact_durable(intents[0])
    assert not keyring.keys()


def test_revoke_does_not_delete_replacement(tmp_path: Path) -> None:
    keyring = WindowsLimitKeyring()
    store = _store(tmp_path, keyring)
    intents = []
    original = _record()
    store.publish_durable_if_absent(original, "b" * 64, intents.append)
    replacement = _record()
    store.write_durable(replacement)
    with pytest.raises(ApprovalError, match="APPROVAL_ID_MISMATCH"):
        store.revoke_exact_durable(intents[0])
    assert store.read_durable(original.workspace_digest) == replacement



def test_exact_gate_refuses_snapshot_and_monotonic_changes(tmp_path: Path) -> None:
    store = _store(tmp_path, WindowsLimitKeyring())
    record = _record()
    legacy = "b" * 64
    receipt = tmp_path / "intent.json"
    store.publish_durable_if_absent(record, legacy, lambda intent: intent.persist(receipt))
    intent = DurableWriteIntent.read(receipt)
    candidate = SimpleNamespace(
        workspace_identity=SimpleNamespace(digest=record.workspace_digest),
        workspace_state=SimpleNamespace(legacy_v2_digest=legacy),
        security_snapshot_digest=record.security_snapshot_digest,
        monotonic_grants={},
    )
    kwargs = {"approval_id": intent.approval_id, "record_digest": intent.record_digest, "launch_session_id": "scoped-check"}
    assert verify_exact_durable(candidate, store, **kwargs).approval_id == intent.approval_id
    candidate.security_snapshot_digest = "c" * 64
    with pytest.raises(LaunchGateError, match="SNAPSHOT_MISMATCH"):
        verify_exact_durable(candidate, store, **kwargs)
    candidate.security_snapshot_digest = record.security_snapshot_digest
    candidate.monotonic_grants = {"OPTIMUS_MAX_PLANNING_TURNS": "100"}
    with pytest.raises(LaunchGateError, match="MONOTONIC_LOOSENING_UNAPPROVED"):
        verify_exact_durable(candidate, store, **kwargs)


def test_exact_agent_flag_requires_pinned_workspace_and_excludes_other_paths(tmp_path: Path) -> None:
    from optimus.acp.__main__ import parse_args

    expected = "appr_" + "a" * 24 + ":" + "b" * 64
    args = parse_args(["--workspace-root", str(tmp_path), "--expected-durable-approval", expected, "--no-auto-start"])
    assert args.expected_durable_approval == ("appr_" + "a" * 24, "b" * 64)
    with pytest.raises(SystemExit):
        parse_args(["--workspace-root", str(tmp_path), "--expected-durable-approval", expected, "--setup"])


def test_scoped_cli_preflight_verify_and_revoke_with_a_fake_store(tmp_path, monkeypatch, capsys):
    from optimus.acp import launch_approval_cli as cli
    from optimus.acp.trusted_paths import resolve_workspace_security_state

    state = resolve_workspace_security_state(tmp_path)
    legacy = state.legacy_v2_digest
    digest = state.identity.digest
    store = _store(tmp_path, WindowsLimitKeyring())
    record = _record(digest=digest)
    candidate = SimpleNamespace(
        workspace_identity=state.identity, workspace_state=state,
        security_snapshot_digest=record.security_snapshot_digest, monotonic_grants={},
    )
    monkeypatch.setattr(cli, "_resolve_store", lambda workspace, *, existing_only: (store, tmp_path))
    monkeypatch.setattr(cli, "_require_tty", lambda: None)
    monkeypatch.setattr(cli, "_prepare_candidate_context", lambda workspace: (None, None))
    monkeypatch.setattr(cli, "_resolve_candidate", lambda *args, **kwargs: candidate)
    workspace = ["--workspace-root", str(tmp_path)]

    assert cli.main([*workspace, "scoped-preflight"]) == 0
    assert json.loads(capsys.readouterr().out)["workspace_digest"] == digest
    receipt = tmp_path / "intent.json"
    intent = store.publish_durable_if_absent(record, legacy, lambda item: item.persist(receipt))
    assert cli.main([*workspace, "scoped-preflight"]) == 2
    assert cli.main([*workspace, "scoped-verify", str(receipt), digest]) == 0
    assert json.loads(capsys.readouterr().out)["record_digest"] == intent.record_digest
    assert cli.main(["scoped-revoke", str(receipt)]) == 0
    assert cli.main(["scoped-revoke", str(receipt)]) == 3


def test_scoped_ceremony_and_revoke_are_tty_gated(tmp_path: Path, monkeypatch) -> None:
    from optimus.acp import launch_approval_cli as cli

    class NonTty:
        def isatty(self):
            return False

    monkeypatch.setattr("sys.stdin", NonTty())
    receipt = str(tmp_path / "receipt.json")
    assert cli.main(["--workspace-root", str(tmp_path), "scoped-approve", receipt, "a" * 64]) == 2
    assert cli.main(["scoped-revoke", receipt]) == 2
    assert not (tmp_path / "receipt.json").exists()
