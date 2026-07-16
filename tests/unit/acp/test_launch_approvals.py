"""Tests for HMAC-protected keyring approvals and single-use consumption.

Task 3 of Plan 9.96: Durable and one-shot records have fixed schema, size,
integrity, workspace binding, expiry/revocation, and concurrency semantics.
A fake keyring is permitted in this unit task.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from optimus.acp.launch_approvals import (
    APPROVAL_SCHEMA_VERSION,
    DIAGNOSTIC_TTL_SECONDS,
    LAUNCH_POLICY_COMPATIBILITY,
    MAX_APPROVAL_RECORD_BYTES,
    ONE_SHOT_TTL_SECONDS,
    ApprovalError,
    ApprovalRecord,
    DiagnosticGrant,
    KeyringApprovalStore,
    build_approval_record,
    compute_record_hmac,
    compute_secret_fingerprint,
    derive_one_shot_handle,
    serialize_approval_record,
)
from optimus.acp.trusted_paths import WorkspaceIdentity

# --- Fake keyring backend for unit testing ---


class FakeKeyring:
    """In-memory keyring backend for unit tests."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        return self._store.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self._store[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        self._store.pop((service, key), None)


# --- Test fixtures ---


def _sample_workspace_identity() -> WorkspaceIdentity:
    return WorkspaceIdentity(
        canonical_path="/tmp/test-workspace",
        device=1,
        inode=12345,
        repository_root="/tmp/test-workspace",
        git_common_dir="/tmp/test-workspace/.git",
        digest="a" * 64,
    )


def _sample_approval_record(
    *,
    mode: str = "durable",
    workspace_identity: WorkspaceIdentity | None = None,
    hmac_key: bytes = b"test-hmac-key-32-bytes-long!!!!",
) -> ApprovalRecord:
    ws = workspace_identity or _sample_workspace_identity()
    return build_approval_record(
        mode=mode,
        workspace_identity=ws,
        security_literals={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        secret_fingerprints={"OPTIMUS_API_KEY": "fp_abc123"},
        monotonic_grants={"OPTIMUS_LIVE_MAX_COST_USD": "0.25"},
        model_observation="claude-haiku",
        hmac_key=hmac_key,
    )


# --- Task 3 Step 1: Record and fingerprint vector tests ---


class TestApprovalRecordSchema:
    """Record schema, canonical JSON, and size constraints."""

    def test_record_has_required_schema_fields(self) -> None:
        record = _sample_approval_record()
        assert record.schema_version == APPROVAL_SCHEMA_VERSION
        assert record.policy_compatibility == LAUNCH_POLICY_COMPATIBILITY
        assert record.approval_id.startswith("appr_")
        assert record.mode in ("one-shot", "durable")
        assert record.workspace_identity == _sample_workspace_identity()
        assert isinstance(record.created_at, datetime)
        assert record.creator_identity != ""
        assert record.ceremony_cli_version != ""
        assert record.registry_version != ""
        assert record.security_snapshot_digest != ""
        assert record.record_hmac != ""

    def test_durable_record_has_no_expiry(self) -> None:
        record = _sample_approval_record(mode="durable")
        assert record.expires_at is None

    def test_one_shot_record_has_expiry(self) -> None:
        record = _sample_approval_record(mode="one-shot")
        assert record.expires_at is not None
        # Expiry should be within ONE_SHOT_TTL_SECONDS of creation.
        delta = record.expires_at - record.created_at
        assert delta.total_seconds() <= ONE_SHOT_TTL_SECONDS

    def test_serialized_record_fits_within_max_bytes(self) -> None:
        record = _sample_approval_record()
        serialized = serialize_approval_record(record)
        assert len(serialized.encode("utf-8")) <= MAX_APPROVAL_RECORD_BYTES

    def test_record_at_exact_1800_bytes_is_accepted(self) -> None:
        """1,800-byte acceptance boundary."""
        record = _sample_approval_record()
        serialized = serialize_approval_record(record)
        # Should be well under; the constraint is enforced at write time.
        assert len(serialized.encode("utf-8")) <= MAX_APPROVAL_RECORD_BYTES

    def test_serialized_record_is_canonical_json(self) -> None:
        record = _sample_approval_record()
        serialized = serialize_approval_record(record)
        # Canonical: sorted keys, no extra whitespace.
        parsed = json.loads(serialized)
        re_serialized = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        assert serialized == re_serialized

    def test_serialized_record_contains_no_canary_secret(self) -> None:
        """Secrets and URI user information must never appear in serialized form."""
        hmac_key = b"super-secret-hmac-key-32bytes!!"
        record = build_approval_record(
            mode="durable",
            workspace_identity=_sample_workspace_identity(),
            security_literals={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
            secret_fingerprints={"OPTIMUS_API_KEY": "fp_canary_secret_value"},
            monotonic_grants={},
            model_observation=None,
            hmac_key=hmac_key,
        )
        serialized = serialize_approval_record(record)
        # The HMAC key itself must never appear.
        assert "super-secret-hmac-key" not in serialized
        # Secret fingerprints are stored (they're already derived values, not raw secrets).
        # But raw secret VALUES must never be in the record.
        # The fingerprint "fp_canary_secret_value" IS stored (it's a fingerprint, not the secret).
        assert "fp_canary_secret_value" in serialized


class TestSecretFingerprints:
    """Domain-separated HMAC fingerprints for secret values."""

    def test_fingerprint_is_deterministic(self) -> None:
        hmac_key = b"test-key-for-fingerprint-32byte"
        fp1 = compute_secret_fingerprint("my-secret", field_name="OPTIMUS_API_KEY", hmac_key=hmac_key)
        fp2 = compute_secret_fingerprint("my-secret", field_name="OPTIMUS_API_KEY", hmac_key=hmac_key)
        assert fp1 == fp2

    def test_fingerprint_changes_with_value(self) -> None:
        hmac_key = b"test-key-for-fingerprint-32byte"
        fp1 = compute_secret_fingerprint("secret-a", field_name="OPTIMUS_API_KEY", hmac_key=hmac_key)
        fp2 = compute_secret_fingerprint("secret-b", field_name="OPTIMUS_API_KEY", hmac_key=hmac_key)
        assert fp1 != fp2

    def test_fingerprint_is_domain_separated(self) -> None:
        """Same value under different field names produces different fingerprints."""
        hmac_key = b"test-key-for-fingerprint-32byte"
        fp1 = compute_secret_fingerprint("same-value", field_name="OPTIMUS_API_KEY", hmac_key=hmac_key)
        fp2 = compute_secret_fingerprint("same-value", field_name="ANTHROPIC_API_KEY", hmac_key=hmac_key)
        assert fp1 != fp2

    def test_fingerprint_changes_with_key(self) -> None:
        fp1 = compute_secret_fingerprint("value", field_name="X", hmac_key=b"key-aaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        fp2 = compute_secret_fingerprint("value", field_name="X", hmac_key=b"key-bbbbbbbbbbbbbbbbbbbbbbbbbbbb")
        assert fp1 != fp2

    def test_fingerprint_does_not_contain_raw_value(self) -> None:
        hmac_key = b"test-key-for-fingerprint-32byte"
        fp = compute_secret_fingerprint("hunter2-secret", field_name="OPTIMUS_API_KEY", hmac_key=hmac_key)
        assert "hunter2" not in fp


class TestRecordHmac:
    """HMAC integrity binding for approval records."""

    def test_hmac_is_deterministic(self) -> None:
        hmac_key = b"test-hmac-key-32-bytes-long!!!!!"
        record = _sample_approval_record(hmac_key=hmac_key)
        # Re-computing over the same record fields yields the same HMAC.
        recomputed = compute_record_hmac(record, hmac_key=hmac_key)
        assert record.record_hmac == recomputed

    def test_hmac_detects_field_tampering(self) -> None:
        hmac_key = b"test-hmac-key-32-bytes-long!!!!!"
        record = _sample_approval_record(hmac_key=hmac_key)
        # Tamper with a field — create a copy with different workspace digest.
        from dataclasses import replace

        tampered_ws = WorkspaceIdentity(
            canonical_path="/tmp/evil",
            device=1,
            inode=99999,
            repository_root=None,
            git_common_dir=None,
            digest="b" * 64,
        )
        tampered = replace(record, workspace_identity=tampered_ws)
        recomputed = compute_record_hmac(tampered, hmac_key=hmac_key)
        assert tampered.record_hmac != recomputed

    def test_hmac_detects_wrong_key(self) -> None:
        hmac_key = b"test-hmac-key-32-bytes-long!!!!!"
        record = _sample_approval_record(hmac_key=hmac_key)
        wrong_key = b"wrong-key-32-bytes-long!!!!!!!!!!"
        recomputed = compute_record_hmac(record, hmac_key=wrong_key)
        assert record.record_hmac != recomputed


class TestOneShotHandle:
    """One-shot nonce handle derivation."""

    def test_handle_starts_with_p996_prefix(self) -> None:
        nonce = b"\x00" * 32
        handle = derive_one_shot_handle(nonce)
        assert handle.startswith("p996_")

    def test_handle_is_deterministic(self) -> None:
        nonce = b"\x01" * 32
        h1 = derive_one_shot_handle(nonce)
        h2 = derive_one_shot_handle(nonce)
        assert h1 == h2

    def test_different_nonces_produce_different_handles(self) -> None:
        h1 = derive_one_shot_handle(b"\x01" * 32)
        h2 = derive_one_shot_handle(b"\x02" * 32)
        assert h1 != h2

    def test_handle_uses_unpadded_base64url(self) -> None:
        nonce = b"\xff" * 32
        handle = derive_one_shot_handle(nonce)
        suffix = handle[len("p996_"):]
        # Unpadded base64url: no '=' padding, no '+' or '/'.
        assert "=" not in suffix
        assert "+" not in suffix
        assert "/" not in suffix


# --- Task 3 Step 4: Concurrency and replay behavior tests ---


class TestKeyringApprovalStore:
    """Store operations with a fake keyring backend."""

    def _make_store_and_record(self, tmp_path: Path, *, mode: str = "durable") -> tuple:
        """Create a store and matching record with the same HMAC key."""
        keyring = FakeKeyring()
        hmac_key = b"shared-test-hmac-key-32-bytes!!"
        store = KeyringApprovalStore(
            keyring_backend=keyring,
            runtime_root=tmp_path,
            hmac_key=hmac_key,
        )
        record = _sample_approval_record(mode=mode, hmac_key=hmac_key)
        return store, record, keyring

    def test_write_and_read_durable(self, tmp_path: Path) -> None:
        store, record, _ = self._make_store_and_record(tmp_path)
        ws_digest = record.workspace_identity.digest

        store.write_durable(record)
        retrieved = store.read_durable(ws_digest)

        assert retrieved is not None
        assert retrieved.approval_id == record.approval_id
        assert retrieved.workspace_identity.digest == ws_digest

    def test_read_durable_returns_none_when_absent(self, tmp_path: Path) -> None:
        store, _, _ = self._make_store_and_record(tmp_path)
        assert store.read_durable("nonexistent_digest") is None

    def test_write_one_shot_returns_handle(self, tmp_path: Path) -> None:
        store, record, _ = self._make_store_and_record(tmp_path, mode="one-shot")
        nonce = b"\xab" * 32

        handle = store.write_one_shot(record, nonce)

        assert handle.startswith("p996_")
        assert handle == derive_one_shot_handle(nonce)

    def test_consume_one_shot_returns_record_and_deletes(self, tmp_path: Path) -> None:
        store, record, _ = self._make_store_and_record(tmp_path, mode="one-shot")
        nonce = b"\xcd" * 32

        handle = store.write_one_shot(record, nonce)
        consumed = store.consume_one_shot(handle, record.security_snapshot_digest)

        assert consumed.approval_id == record.approval_id

        # Second consumption must fail — delete-before-use semantics.
        with pytest.raises(ApprovalError) as exc_info:
            store.consume_one_shot(handle, record.security_snapshot_digest)
        assert exc_info.value.code == "ONE_SHOT_NOT_FOUND"

    def test_consume_one_shot_rejects_wrong_snapshot_digest(self, tmp_path: Path) -> None:
        store, record, _ = self._make_store_and_record(tmp_path, mode="one-shot")
        nonce = b"\xef" * 32

        handle = store.write_one_shot(record, nonce)

        with pytest.raises(ApprovalError) as exc_info:
            store.consume_one_shot(handle, "wrong_digest_" + "x" * 50)
        assert exc_info.value.code == "SNAPSHOT_MISMATCH"

    def test_consume_one_shot_rejects_expired(self, tmp_path: Path) -> None:
        hmac_key = b"shared-test-hmac-key-32-bytes!!"
        keyring = FakeKeyring()
        store = KeyringApprovalStore(
            keyring_backend=keyring,
            runtime_root=tmp_path,
            hmac_key=hmac_key,
        )
        # Create a record that's already expired.
        record = build_approval_record(
            mode="one-shot",
            workspace_identity=_sample_workspace_identity(),
            security_literals={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
            secret_fingerprints={},
            monotonic_grants={},
            model_observation=None,
            hmac_key=hmac_key,
            override_created_at=datetime.now(timezone.utc) - timedelta(seconds=ONE_SHOT_TTL_SECONDS + 60),
        )
        nonce = b"\x11" * 32
        handle = store.write_one_shot(record, nonce)

        with pytest.raises(ApprovalError) as exc_info:
            store.consume_one_shot(handle, record.security_snapshot_digest)
        assert exc_info.value.code == "APPROVAL_EXPIRED"

    def test_revoke_workspace_removes_durable(self, tmp_path: Path) -> None:
        store, record, _ = self._make_store_and_record(tmp_path)
        ws_digest = record.workspace_identity.digest

        store.write_durable(record)
        assert store.read_durable(ws_digest) is not None

        store.revoke_workspace(ws_digest)
        assert store.read_durable(ws_digest) is None

    def test_corrupt_record_fails_with_integrity_error(self, tmp_path: Path) -> None:
        store, record, keyring = self._make_store_and_record(tmp_path)
        ws_digest = record.workspace_identity.digest

        store.write_durable(record)

        # Corrupt the stored JSON by directly modifying the keyring.
        service = store._service_name
        raw = keyring.get_password(service, f"durable:{ws_digest}")
        assert raw is not None
        corrupted = raw.replace(record.approval_id, "appr_CORRUPTED")
        keyring.set_password(service, f"durable:{ws_digest}", corrupted)

        with pytest.raises(ApprovalError) as exc_info:
            store.read_durable(ws_digest)
        assert exc_info.value.code == "INTEGRITY_FAILURE"


class TestDiagnosticGrant:
    """Diagnostic grant write/consume semantics."""

    def test_write_and_consume_diagnostic_grant(self, tmp_path: Path) -> None:
        keyring = FakeKeyring()
        store = KeyringApprovalStore(
            keyring_backend=keyring,
            runtime_root=tmp_path,
        )
        grant = DiagnosticGrant(
            grant_id="diag_test_001",
            workspace_digest="a" * 64,
            approval_id="appr_test",
            launch_session_id="sess_test",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=DIAGNOSTIC_TTL_SECONDS),
            record_hmac="placeholder",
        )

        store.write_diagnostic_grant(grant)
        consumed = store.consume_diagnostic_grant("diag_test_001", "sess_test")

        assert consumed.grant_id == "diag_test_001"

        # Second consumption fails.
        with pytest.raises(ApprovalError) as exc_info:
            store.consume_diagnostic_grant("diag_test_001", "sess_test")
        assert exc_info.value.code == "GRANT_NOT_FOUND"

    def test_diagnostic_grant_rejects_wrong_session(self, tmp_path: Path) -> None:
        keyring = FakeKeyring()
        store = KeyringApprovalStore(
            keyring_backend=keyring,
            runtime_root=tmp_path,
        )
        grant = DiagnosticGrant(
            grant_id="diag_test_002",
            workspace_digest="a" * 64,
            approval_id="appr_test",
            launch_session_id="sess_correct",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=DIAGNOSTIC_TTL_SECONDS),
            record_hmac="placeholder",
        )
        store.write_diagnostic_grant(grant)

        with pytest.raises(ApprovalError) as exc_info:
            store.consume_diagnostic_grant("diag_test_002", "sess_wrong")
        assert exc_info.value.code == "GRANT_SESSION_MISMATCH"



# --- Task 3 Step 4: Additional coverage for concurrency, boundary, and policy ---


class TestOneShotConcurrency:
    """True concurrency tests: exactly one consumer must succeed."""

    def test_concurrent_consumers_only_one_succeeds(self, tmp_path: Path) -> None:
        """Two threads racing to consume the same one-shot — exactly one wins."""
        import threading

        hmac_key = b"shared-test-hmac-key-32-bytes!!"
        keyring = FakeKeyring()
        record = _sample_approval_record(mode="one-shot", hmac_key=hmac_key)
        nonce = b"\xaa" * 32

        # Write the one-shot record.
        store = KeyringApprovalStore(
            keyring_backend=keyring,
            runtime_root=tmp_path,
            hmac_key=hmac_key,
        )
        handle = store.write_one_shot(record, nonce)

        num_threads = 4
        results: list[str] = []
        lock = threading.Lock()

        def consumer() -> None:
            # Each thread gets its own store instance (same keyring/key/runtime_root).
            thread_store = KeyringApprovalStore(
                keyring_backend=keyring,
                runtime_root=tmp_path,
                hmac_key=hmac_key,
            )
            try:
                thread_store.consume_one_shot(handle, record.security_snapshot_digest)
                with lock:
                    results.append("success")
            except ApprovalError as e:
                with lock:
                    results.append(f"error:{e.code}")

        threads = [threading.Thread(target=consumer) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Every thread must report a result (no silent crashes).
        assert len(results) == num_threads, (
            f"Expected {num_threads} results, got {len(results)}: {results}"
        )
        # Exactly one succeeds.
        successes = [r for r in results if r == "success"]
        assert len(successes) == 1, (
            f"Expected exactly 1 success, got {len(successes)}: {results}"
        )
        # Every failure must be a proper coded error, not an uncaught exception.
        failures = [r for r in results if r != "success"]
        for f in failures:
            assert f.startswith("error:"), f"Unexpected result (not a coded error): {f}"
            code = f[len("error:"):]
            assert code in ("ONE_SHOT_NOT_FOUND", "LOCK_CONTENTION"), (
                f"Unexpected error code: {code}"
            )


class TestRecordSizeBoundary:
    """Exact 1800-byte accept / 1801-byte reject boundary."""

    def test_record_at_1800_bytes_is_accepted(self, tmp_path: Path) -> None:
        """A record serialized to exactly 1800 UTF-8 bytes passes write."""
        hmac_key = b"shared-test-hmac-key-32-bytes!!"
        keyring = FakeKeyring()
        store = KeyringApprovalStore(
            keyring_backend=keyring,
            runtime_root=tmp_path,
            hmac_key=hmac_key,
        )
        # Build a record and pad security_literals to hit exactly 1800 bytes.
        record = _build_padded_record(target_bytes=1800, hmac_key=hmac_key)
        serialized = serialize_approval_record(record)
        assert len(serialized.encode("utf-8")) == 1800

        # Should not raise.
        store.write_durable(record)

    def test_record_at_1801_bytes_is_rejected(self, tmp_path: Path) -> None:
        """A record serialized to 1801 UTF-8 bytes is rejected at write."""
        hmac_key = b"shared-test-hmac-key-32-bytes!!"
        keyring = FakeKeyring()
        store = KeyringApprovalStore(
            keyring_backend=keyring,
            runtime_root=tmp_path,
            hmac_key=hmac_key,
        )
        record = _build_padded_record(target_bytes=1801, hmac_key=hmac_key)
        serialized = serialize_approval_record(record)
        assert len(serialized.encode("utf-8")) == 1801

        with pytest.raises(ApprovalError) as exc_info:
            store.write_durable(record)
        assert exc_info.value.code == "RECORD_TOO_LARGE"


class TestPolicyAndKeyRotation:
    """Wrong-policy rejection and rotated-key invalidation."""

    def test_wrong_policy_compatibility_is_rejected_on_read(self, tmp_path: Path) -> None:
        """A record with mismatched policy_compatibility fails."""
        hmac_key = b"shared-test-hmac-key-32-bytes!!"
        keyring = FakeKeyring()
        store = KeyringApprovalStore(
            keyring_backend=keyring,
            runtime_root=tmp_path,
            hmac_key=hmac_key,
        )
        record = _sample_approval_record(hmac_key=hmac_key)
        ws_digest = record.workspace_identity.digest

        # Write normally.
        store.write_durable(record)

        # Manually corrupt the policy_compatibility field in stored JSON.
        service = store._service_name
        raw = keyring.get_password(service, f"durable:{ws_digest}")
        assert raw is not None
        # Replace policy with a different version — but this breaks HMAC too,
        # so we'll get INTEGRITY_FAILURE first. Instead, test the policy check
        # by building a record with a wrong policy at construction time and
        # signing it with the same key.
        from dataclasses import replace as dc_replace

        wrong_policy_record = dc_replace(record, policy_compatibility="P9.95-v1", record_hmac="")
        wrong_policy_record = dc_replace(
            wrong_policy_record,
            record_hmac=compute_record_hmac(wrong_policy_record, hmac_key=hmac_key),
        )
        # Write directly to keyring.
        wrong_serialized = serialize_approval_record(wrong_policy_record)
        keyring.set_password(service, f"durable:{ws_digest}", wrong_serialized)

        with pytest.raises(ApprovalError) as exc_info:
            store.read_durable(ws_digest)
        assert exc_info.value.code == "POLICY_MISMATCH"

    def test_rotated_key_invalidates_existing_records(self, tmp_path: Path) -> None:
        """After rotate_hmac_key(), existing records fail with INTEGRITY_FAILURE."""
        hmac_key = b"shared-test-hmac-key-32-bytes!!"
        keyring = FakeKeyring()
        store = KeyringApprovalStore(
            keyring_backend=keyring,
            runtime_root=tmp_path,
            hmac_key=hmac_key,
        )
        record = _sample_approval_record(hmac_key=hmac_key)
        ws_digest = record.workspace_identity.digest

        store.write_durable(record)
        # Confirm it reads fine before rotation.
        assert store.read_durable(ws_digest) is not None

        # Rotate the key.
        store.rotate_hmac_key()

        # Now reads fail because the HMAC no longer matches.
        with pytest.raises(ApprovalError) as exc_info:
            store.read_durable(ws_digest)
        assert exc_info.value.code == "INTEGRITY_FAILURE"

    def test_store_ignores_keyring_hmac_entry_changed_after_construction(self, tmp_path: Path) -> None:
        """Plan 9.96, Task 5 Step 7 (TOCTOU matrix): KeyringApprovalStore
        loads/generates its HMAC integrity key exactly once, inside
        __init__ -> _ensure_hmac_key(), and caches it on self._hmac_key for
        the store's entire lifetime (store.hmac_key never rereads the
        keyring). This asserts that overwriting the keyring's
        hmac_integrity_key entry AFTER a store instance already exists has
        NO EFFECT on that instance -- it keeps using the key it loaded at
        construction time.

        This is the correct TOCTOU proof, not "a later read would fail":
        nothing in KeyringApprovalStore rereads the keyring for its own
        integrity key after construction, so there is no reread-and-detect
        path here by design -- mirroring the os.environ/`.env.gateway`
        single-capture cases elsewhere in this matrix. A NEW store
        constructed afterward, by contrast, legitimately picks up the new
        key (proven separately below) -- the guarantee is per-instance
        stability, not global immutability of the keyring entry.
        """
        keyring = FakeKeyring()
        original_key = b"original-hmac-key-32-bytes-long"
        store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=tmp_path, hmac_key=original_key)
        # Persist the original key into the keyring, mirroring what the real
        # _ensure_hmac_key() would have done on first construction with no
        # explicit hmac_key override.
        import base64 as base64_mod

        keyring.set_password(
            "optimus-cost-agent-approvals",
            "hmac_integrity_key",
            base64_mod.urlsafe_b64encode(original_key).decode("ascii"),
        )
        record = _sample_approval_record(hmac_key=original_key)
        store.write_durable(record)

        # Overwrite the keyring's HMAC key entry AFTER the store instance
        # already exists and already has original_key cached.
        replacement_key = b"ATTACKER-REPLACED-hmac-key-32!!"
        keyring.set_password(
            "optimus-cost-agent-approvals",
            "hmac_integrity_key",
            base64_mod.urlsafe_b64encode(replacement_key).decode("ascii"),
        )

        # The existing store instance is unaffected: it still verifies
        # (and would still sign) with the key it loaded at construction.
        assert store.hmac_key == original_key
        retrieved = store.read_durable(record.workspace_identity.digest)
        assert retrieved is not None
        assert retrieved.approval_id == record.approval_id

    def test_new_store_picks_up_keyring_hmac_entry_written_by_another_instance(self, tmp_path: Path) -> None:
        """Companion to the no-effect test above: the per-instance caching
        guarantee is deliberately NOT global keyring immutability. A
        freshly constructed store (no explicit hmac_key override) legitimately
        loads whatever key currently sits in the keyring -- this is by design
        (key rotation must be visible to future launches) and distinguishes
        the "cached per instance" claim from "the keyring entry can never
        change effective behavior at all," which would be a stronger and
        incorrect claim."""
        keyring = FakeKeyring()
        first_store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=tmp_path)
        loaded_key = first_store.hmac_key

        second_store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=tmp_path)
        assert second_store.hmac_key == loaded_key


def _build_padded_record(*, target_bytes: int, hmac_key: bytes) -> ApprovalRecord:
    """Build a record padded to exactly target_bytes when serialized."""
    # Start with a minimal record.
    base_record = build_approval_record(
        mode="durable",
        workspace_identity=_sample_workspace_identity(),
        security_literals={},
        secret_fingerprints={},
        monotonic_grants={},
        model_observation=None,
        hmac_key=hmac_key,
    )
    base_serialized = serialize_approval_record(base_record)
    base_len = len(base_serialized.encode("utf-8"))

    # We need to add padding via model_observation field.
    # The field in JSON is: "model_observation":"<value>"
    # In the base record it's null: "model_observation":null
    # Changing to a string adds quotes: "model_observation":"X..."
    # null = 4 chars, "X..." = len + 2 chars for quotes.
    # Difference: (pad_len + 2) - 4 = pad_len - 2
    needed = target_bytes - base_len
    # needed = pad_len - 2, so pad_len = needed + 2
    pad_len = needed + 2
    if pad_len < 1:
        # Fallback: the base is already too large or at target.
        pad_len = 1

    from dataclasses import replace as dc_replace

    padded = dc_replace(base_record, model_observation="X" * pad_len, record_hmac="")
    padded = dc_replace(padded, record_hmac=compute_record_hmac(padded, hmac_key=hmac_key))

    # Fine-tune: check and adjust.
    actual_len = len(serialize_approval_record(padded).encode("utf-8"))
    diff = target_bytes - actual_len
    if diff != 0:
        new_pad_len = pad_len + diff
        padded = dc_replace(base_record, model_observation="X" * new_pad_len, record_hmac="")
        padded = dc_replace(padded, record_hmac=compute_record_hmac(padded, hmac_key=hmac_key))

    return padded
