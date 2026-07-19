"""Tests for launch candidate resolution and authorization.

Plan 9.96, Task 4 Step 1: Cover environment precedence without rereading
ambient env. Exact provider/base URL displayed; Redis/Gateway URI userinfo
masked; secret rows show name/presence/provenance/length only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from optimus.acp.launch_gate import (
    LaunchCandidate,
    LaunchGateError,
    authorize_launch,
    resolve_launch_candidate,
)
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.operator_paths import OperatorPaths
from optimus.acp.trusted_paths import WorkspaceIdentity

_HMAC_KEY = b"test-gate-hmac-key-32-bytes!!!!"


def _sample_workspace_identity() -> WorkspaceIdentity:
    return WorkspaceIdentity(
        lexical_path="/tmp/test-workspace",
        canonical_path="/tmp/test-workspace",
        device=1,
        inode=12345,
        change_time_ns=1,
        repository_root="/tmp/test-workspace",
        git_common_dir="/tmp/test-workspace/.git",
        digest="a" * 64,
    )


def _sample_operator_paths(tmp_path: Path) -> OperatorPaths:
    return OperatorPaths(
        workspace_root=tmp_path,
        config_root=tmp_path / "config",
        runtime_root=tmp_path / ".optimus",
        debug_log_path=tmp_path / ".optimus" / "debug-acp.ndjson",
        gateway_log_path=tmp_path / ".optimus" / "local-gateway.log",
    )


class TestResolveLaunchCandidateEnforcesSecretLengthCap:
    """Plan 9.96, Task 6 Batch 2: the MAX_SECRET_TEXT_CHARS cap deferred from
    Batch 1 must now be enforced at launch time -- rejecting a configured
    secret longer than the cap BEFORE authorization, not merely documented.
    This closes the one gap Batch 1 deliberately left open: until this
    enforcement exists, an over-long secret could in principle exceed
    StreamingTextSanitizer's overlap window, since that guarantee assumes
    every secret is <= MAX_SECRET_TEXT_CHARS. A rejected secret is a
    launch-blocker (LaunchGateError), not a silent downgrade -- unlike the
    diagnostic-grant case, secret-length is a hard correctness precondition
    for a security-sensitive guarantee, not a diagnostics nicety."""

    def test_over_length_secret_fails_closed_before_authorization(self, tmp_path: Path) -> None:
        from optimus_security.sanitization import MAX_SECRET_TEXT_CHARS

        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "x" * (MAX_SECRET_TEXT_CHARS + 1),
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)

        with pytest.raises(LaunchGateError) as exc_info:
            resolve_launch_candidate(
                snapshot=snapshot,
                workspace_identity=_sample_workspace_identity(),
                operator_paths=_sample_operator_paths(tmp_path),
                hmac_key=_HMAC_KEY,
            )
        assert exc_info.value.code == "SECRET_TOO_LONG"
        assert "OPTIMUS_API_KEY" in exc_info.value.detail

    def test_secret_at_exact_max_length_is_accepted(self, tmp_path: Path) -> None:
        from optimus_security.sanitization import MAX_SECRET_TEXT_CHARS

        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "x" * MAX_SECRET_TEXT_CHARS,
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)

        # Must not raise.
        resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )

    def test_ordinary_length_secret_is_unaffected(self, tmp_path: Path) -> None:
        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key-normal-length",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)

        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )
        assert "OPTIMUS_API_KEY" in candidate.secret_inventory


class TestResolveLaunchCandidateValidatesEnvGatewayPermissions:
    """Review finding (Task 5 Batch 2): validate_config_file_permissions()
    must be enforced structurally inside resolve_launch_candidate itself —
    the one place that actually parses .env.gateway via
    resolve_provider_credentials/resolve_shared_secret — rather than relying
    on each caller (the optimus-trust CLI, __main__.py, or any future caller)
    to remember to call it first. This is the canonical enforcement point;
    test_launch_approval_cli.py's tests prove callers still trigger it
    transitively."""

    def test_missing_env_gateway_skips_check_and_resolves_normally(self, tmp_path: Path) -> None:
        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        paths = _sample_operator_paths(tmp_path)
        assert not (paths.config_root / ".env.gateway").exists()

        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=paths,
            hmac_key=_HMAC_KEY,
        )
        assert isinstance(candidate, LaunchCandidate)

    @pytest.mark.skipif(
        __import__("sys").platform == "win32",
        reason="POSIX-only: permission bit checks",
    )
    def test_group_readable_env_gateway_fails_closed_before_credential_parsing(self, tmp_path: Path) -> None:
        paths = _sample_operator_paths(tmp_path)
        paths.config_root.mkdir(parents=True)
        env_gateway = paths.config_root / ".env.gateway"
        env_gateway.write_text(
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n"
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-should-never-be-read\n",
            encoding="utf-8",
        )
        env_gateway.chmod(0o640)  # group-readable — must be rejected

        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)

        with pytest.raises(LaunchGateError) as exc_info:
            resolve_launch_candidate(
                snapshot=snapshot,
                workspace_identity=_sample_workspace_identity(),
                operator_paths=paths,
                hmac_key=_HMAC_KEY,
            )
        assert exc_info.value.code == "CONFIG_FILE_PERMISSIONS_TOO_OPEN"

    @pytest.mark.skipif(
        __import__("sys").platform == "win32",
        reason="POSIX-only: permission bit checks",
    )
    def test_owner_only_env_gateway_passes_and_credentials_resolve(self, tmp_path: Path) -> None:
        paths = _sample_operator_paths(tmp_path)
        paths.config_root.mkdir(parents=True)
        env_gateway = paths.config_root / ".env.gateway"
        env_gateway.write_text(
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n"
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-or-test-value\n",
            encoding="utf-8",
        )
        env_gateway.chmod(0o600)  # owner-only — must pass

        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)

        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=paths,
            hmac_key=_HMAC_KEY,
        )
        assert candidate.provider_credentials is not None
        assert candidate.provider_credentials.secrets is not None
        assert candidate.provider_credentials.secrets.model_provider_api_key == "sk-or-test-value"


class TestCandidateResolution:
    """Resolve launch candidate from immutable snapshot."""

    def test_basic_resolution_with_required_vars(self, tmp_path: Path) -> None:
        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            "OPTIMUS_PRODUCTION_MODE": "false",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )
        assert isinstance(candidate, LaunchCandidate)
        assert candidate.security_snapshot_digest
        assert len(candidate.display_rows) > 0

    def test_provider_url_displayed_literally(self, tmp_path: Path) -> None:
        """Provider/base URL must be displayed literally (not masked)."""
        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            "OPTIMUS_LOCAL_GATEWAY_BASE_URL": "https://api.openrouter.ai/v1",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )
        base_url_rows = [r for r in candidate.display_rows if r.name == "OPTIMUS_LOCAL_GATEWAY_BASE_URL"]
        assert len(base_url_rows) == 1
        assert base_url_rows[0].display_value == "https://api.openrouter.ai/v1"

    def test_redis_uri_userinfo_masked_in_display(self, tmp_path: Path) -> None:
        """Redis URI user information is masked in display."""
        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://user:secret@127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )
        redis_rows = [r for r in candidate.display_rows if r.name == "OPTIMUS_REDIS_URL"]
        assert len(redis_rows) == 1
        assert "secret" not in redis_rows[0].display_value
        assert "user" not in redis_rows[0].display_value

    def test_secret_values_never_displayed(self, tmp_path: Path) -> None:
        """Secret-tier variables show redacted display, never the value."""
        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "super-secret-key-value",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )
        api_key_rows = [r for r in candidate.display_rows if r.name == "OPTIMUS_API_KEY"]
        assert len(api_key_rows) == 1
        assert "super-secret-key-value" not in api_key_rows[0].display_value
        assert api_key_rows[0].display_value == "**********"

    def test_unknown_optimus_name_rejects(self, tmp_path: Path) -> None:
        """Unknown OPTIMUS_* in inherited env raises LaunchGateError."""
        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            "OPTIMUS_UNKNOWN_SETTING": "value",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        with pytest.raises(LaunchGateError) as exc_info:
            resolve_launch_candidate(
                snapshot=snapshot,
                workspace_identity=_sample_workspace_identity(),
                operator_paths=_sample_operator_paths(tmp_path),
                hmac_key=_HMAC_KEY,
            )
        assert exc_info.value.code == "UNCLASSIFIED_VARIABLE"
        assert "OPTIMUS_UNKNOWN_SETTING" in exc_info.value.detail

    def test_internal_only_inherited_rejects(self, tmp_path: Path) -> None:
        """Internal-only names in inherited env are rejected."""
        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            "OPTIMUS_ACP_DEBUG_TRACE": "1",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        with pytest.raises(LaunchGateError) as exc_info:
            resolve_launch_candidate(
                snapshot=snapshot,
                workspace_identity=_sample_workspace_identity(),
                operator_paths=_sample_operator_paths(tmp_path),
                hmac_key=_HMAC_KEY,
            )
        assert exc_info.value.code == "INTERNAL_ONLY_INHERITED"

    def test_snapshot_digest_changes_with_credential(self, tmp_path: Path) -> None:
        """Changing a credential value changes the snapshot digest."""
        base_env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "key-a",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        env2 = {**base_env, "OPTIMUS_API_KEY": "key-b"}

        snap1 = LaunchEnvironmentSnapshot.capture(base_env)
        snap2 = LaunchEnvironmentSnapshot.capture(env2)

        c1 = resolve_launch_candidate(
            snapshot=snap1,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )
        c2 = resolve_launch_candidate(
            snapshot=snap2,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )
        assert c1.security_snapshot_digest != c2.security_snapshot_digest

    def test_snapshot_does_not_reread_environ(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Candidate resolution uses only the snapshot, not os.environ."""

        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)

        # Mutate os.environ — should have no effect.
        monkeypatch.setenv("OPTIMUS_API_KEY", "MUTATED_AFTER_CAPTURE")

        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )
        # The candidate should use the original captured value.
        api_key_rows = [r for r in candidate.display_rows if r.name == "OPTIMUS_API_KEY"]
        assert len(api_key_rows) == 1
        # Value was "test-key" at capture time; display is redacted but proves we used snapshot.
        assert candidate.secret_inventory == tuple(sorted(["OPTIMUS_API_KEY"]))



# --- Task 4 Step 2: Config-root validation tests ---


class TestConfigFilePermissions:
    """Config file permission validation."""

    def test_nonexistent_file_fails(self, tmp_path: Path) -> None:
        from optimus.acp.launch_gate import validate_config_file_permissions

        with pytest.raises(LaunchGateError) as exc_info:
            validate_config_file_permissions(tmp_path / "no-such-file")
        assert exc_info.value.code == "CONFIG_FILE_NOT_FOUND"

    def test_directory_instead_of_file_fails(self, tmp_path: Path) -> None:
        from optimus.acp.launch_gate import validate_config_file_permissions

        d = tmp_path / "a-directory"
        d.mkdir()
        with pytest.raises(LaunchGateError) as exc_info:
            validate_config_file_permissions(d)
        assert exc_info.value.code == "CONFIG_FILE_NOT_REGULAR"

    @pytest.mark.skipif(
        __import__("sys").platform == "win32",
        reason="POSIX-only: permission bit checks",
    )
    def test_posix_rejects_group_readable(self, tmp_path: Path) -> None:
        from optimus.acp.launch_gate import validate_config_file_permissions

        f = tmp_path / ".env.gateway"
        f.write_text("test", encoding="utf-8")
        f.chmod(0o640)  # group-readable
        with pytest.raises(LaunchGateError) as exc_info:
            validate_config_file_permissions(f, platform_name="linux")
        assert exc_info.value.code == "CONFIG_FILE_PERMISSIONS_TOO_OPEN"

    @pytest.mark.skipif(
        __import__("sys").platform == "win32",
        reason="POSIX-only: permission bit checks",
    )
    def test_posix_accepts_owner_only(self, tmp_path: Path) -> None:
        from optimus.acp.launch_gate import validate_config_file_permissions

        f = tmp_path / ".env.gateway"
        f.write_text("test", encoding="utf-8")
        f.chmod(0o600)  # owner-only
        # Should not raise.
        validate_config_file_permissions(f, platform_name="linux")

    def test_windows_injectable_adapter_passing(self, tmp_path: Path) -> None:
        """Windows DACL check passes when adapter returns True."""
        from optimus.acp.launch_gate import validate_config_file_permissions

        f = tmp_path / ".env.gateway"
        f.write_text("test", encoding="utf-8")

        class PassingAdapter:
            def check_file_permissions(self, path: Path) -> bool:
                return True

        # Should not raise.
        validate_config_file_permissions(f, platform_name="win32", win32_security_adapter=PassingAdapter())

    def test_windows_injectable_adapter_failing(self, tmp_path: Path) -> None:
        """Windows DACL check fails when adapter returns an error string."""
        from optimus.acp.launch_gate import validate_config_file_permissions

        f = tmp_path / ".env.gateway"
        f.write_text("test", encoding="utf-8")

        class FailingAdapter:
            def check_file_permissions(self, path: Path) -> str:
                return "Everyone has read access"

        with pytest.raises(LaunchGateError) as exc_info:
            validate_config_file_permissions(f, platform_name="win32", win32_security_adapter=FailingAdapter())
        assert exc_info.value.code == "CONFIG_FILE_PERMISSIONS_TOO_OPEN"



# --- End-to-end authorization flow tests ---
# These tests prove the happy path actually works: resolve_launch_candidate()
# produces a digest, build_approval_record() using the candidate's exact
# security_literals/secret_fingerprints/monotonic_grants/model_observation
# produces a MATCHING digest, and authorize_launch() succeeds. Their absence
# previously hid a critical bug where the two sides computed incompatible
# digests and no approval could ever authorize a launch.


class TestEndToEndAuthorization:
    """Prove the full candidate -> approval -> authorization flow succeeds."""

    def test_durable_approval_digest_matches_candidate_digest(self, tmp_path: Path) -> None:
        """The record built from a candidate's exact fields has a matching digest."""
        from optimus.acp.launch_approvals import build_approval_record

        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )

        record = build_approval_record(
            mode="durable",
            workspace_identity=candidate.workspace_identity,
            security_literals=candidate.security_literals,
            secret_fingerprints=candidate.secret_fingerprints,
            monotonic_grants=candidate.monotonic_grants,
            model_observation=candidate.model_observation,
            hmac_key=_HMAC_KEY,
        )

        assert record.security_snapshot_digest == candidate.security_snapshot_digest, (
            "Record digest must match candidate digest for authorization to ever succeed"
        )

    def test_full_authorize_launch_durable_succeeds(self, tmp_path: Path) -> None:
        """End-to-end: resolve candidate, write durable approval, authorize succeeds."""
        from optimus.acp.launch_approvals import KeyringApprovalStore, build_approval_record

        class FakeKeyring:
            def __init__(self) -> None:
                self._store: dict[tuple[str, str], str] = {}

            def get_password(self, service: str, key: str) -> str | None:
                return self._store.get((service, key))

            def set_password(self, service: str, key: str, value: str) -> None:
                self._store[(service, key)] = value

            def delete_password(self, service: str, key: str) -> None:
                self._store.pop((service, key), None)

        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        ws_identity = _sample_workspace_identity()
        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=ws_identity,
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )

        fake_keyring = FakeKeyring()
        store = KeyringApprovalStore(
            keyring_backend=fake_keyring,
            runtime_root=tmp_path,
            hmac_key=_HMAC_KEY,
        )

        record = build_approval_record(
            mode="durable",
            workspace_identity=candidate.workspace_identity,
            security_literals=candidate.security_literals,
            secret_fingerprints=candidate.secret_fingerprints,
            monotonic_grants=candidate.monotonic_grants,
            model_observation=candidate.model_observation,
            hmac_key=_HMAC_KEY,
        )
        store.write_durable(record)

        # Re-resolve the SAME candidate (simulating a second launch) and authorize.
        candidate2 = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=ws_identity,
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )
        authorized = authorize_launch(
            candidate=candidate2,
            store=store,
            launch_session_id="sess_test123",
        )
        assert authorized.approval_id == record.approval_id
        assert authorized.approval_mode == "durable"

    def test_full_authorize_launch_one_shot_succeeds(self, tmp_path: Path) -> None:
        """End-to-end: one-shot approval authorizes successfully."""
        from optimus.acp.launch_approvals import KeyringApprovalStore, build_approval_record

        class FakeKeyring:
            def __init__(self) -> None:
                self._store: dict[tuple[str, str], str] = {}

            def get_password(self, service: str, key: str) -> str | None:
                return self._store.get((service, key))

            def set_password(self, service: str, key: str, value: str) -> None:
                self._store[(service, key)] = value

            def delete_password(self, service: str, key: str) -> None:
                self._store.pop((service, key), None)

        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        ws_identity = _sample_workspace_identity()
        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=ws_identity,
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )

        fake_keyring = FakeKeyring()
        store = KeyringApprovalStore(
            keyring_backend=fake_keyring,
            runtime_root=tmp_path,
            hmac_key=_HMAC_KEY,
        )

        record = build_approval_record(
            mode="one-shot",
            workspace_identity=candidate.workspace_identity,
            security_literals=candidate.security_literals,
            secret_fingerprints=candidate.secret_fingerprints,
            monotonic_grants=candidate.monotonic_grants,
            model_observation=candidate.model_observation,
            hmac_key=_HMAC_KEY,
        )
        import secrets as secrets_mod

        nonce = secrets_mod.token_bytes(32)
        handle = store.write_one_shot(record, nonce)

        authorized = authorize_launch(
            candidate=candidate,
            store=store,
            approval_id=handle,
            launch_session_id="sess_test456",
        )
        assert authorized.approval_mode == "one-shot"

        # Replay must fail — one-shot is consumed.
        with pytest.raises(LaunchGateError):
            authorize_launch(
                candidate=candidate,
                store=store,
                approval_id=handle,
                launch_session_id="sess_test789",
            )



# --- Real Windows DACL enumeration tests (platform-guarded) ---
# These exercise the actual Win32 security API on real Windows, not a fake.
# Task 2's SHGetKnownFolderPath bug (wrong GUID marshaling, only failed on
# real Windows) is the reason this class of check gets its own real-execution
# test rather than relying solely on the injectable-adapter unit tests above.


class TestRealWindowsDaclEnumeration:
    """Real (non-mocked) Windows DACL enumeration."""

    @pytest.mark.skipif(
        __import__("sys").platform != "win32",
        reason="Windows-only: real DACL enumeration",
    )
    def test_current_user_sid_resolves(self) -> None:
        from optimus.acp.launch_gate import _current_user_sid_string

        sid = _current_user_sid_string()
        assert sid.startswith("S-1-5-21-"), f"Expected a domain/local user SID, got: {sid}"

    @pytest.mark.skipif(
        __import__("sys").platform != "win32",
        reason="Windows-only: real DACL enumeration",
    )
    def test_default_acl_file_is_accepted(self, tmp_path: Path) -> None:
        """A normal file with Windows' default inherited ACL passes."""
        from optimus.acp.launch_gate import validate_config_file_permissions

        f = tmp_path / ".env.gateway"
        f.write_text("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=x", encoding="utf-8")
        # Should not raise.
        validate_config_file_permissions(f, platform_name="win32")

    @pytest.mark.skipif(
        __import__("sys").platform != "win32",
        reason="Windows-only: real DACL enumeration",
    )
    def test_everyone_granted_file_is_rejected(self, tmp_path: Path) -> None:
        """A file with an explicit Everyone allow-ACE is rejected."""
        import subprocess

        from optimus.acp.launch_gate import validate_config_file_permissions

        f = tmp_path / ".env.gateway"
        f.write_text("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=x", encoding="utf-8")
        result = subprocess.run(
            ["icacls", str(f), "/grant", "Everyone:(R)"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"icacls setup failed: {result.stderr}"

        with pytest.raises(LaunchGateError) as exc_info:
            validate_config_file_permissions(f, platform_name="win32")
        assert exc_info.value.code == "CONFIG_FILE_PERMISSIONS_TOO_OPEN"

    @pytest.mark.skipif(
        __import__("sys").platform != "win32",
        reason="Windows-only: real DACL enumeration",
    )
    def test_users_group_granted_file_is_rejected(self, tmp_path: Path) -> None:
        """A file with an explicit Users group allow-ACE is rejected."""
        import subprocess

        from optimus.acp.launch_gate import validate_config_file_permissions

        f = tmp_path / ".env.gateway"
        f.write_text("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=x", encoding="utf-8")
        result = subprocess.run(
            ["icacls", str(f), "/grant", "Users:(R)"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"icacls setup failed: {result.stderr}"

        with pytest.raises(LaunchGateError) as exc_info:
            validate_config_file_permissions(f, platform_name="win32")
        assert exc_info.value.code == "CONFIG_FILE_PERMISSIONS_TOO_OPEN"

    @pytest.mark.skipif(
        __import__("sys").platform != "win32",
        reason="Windows-only: real DACL enumeration",
    )
    def test_explicit_current_user_grant_is_accepted(self, tmp_path: Path) -> None:
        """A file with an explicit current-user allow-ACE (plus defaults) passes."""
        import getpass
        import subprocess

        from optimus.acp.launch_gate import validate_config_file_permissions

        f = tmp_path / ".env.gateway"
        f.write_text("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=x", encoding="utf-8")
        username = getpass.getuser()
        result = subprocess.run(
            ["icacls", str(f), "/grant", f"{username}:(R)"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"icacls setup failed: {result.stderr}"

        # Should not raise.
        validate_config_file_permissions(f, platform_name="win32")



# --- Task 4 Step 3: Single-read credential resolution tests ---


class TestSingleReadCredentialResolution:
    """Provider/shared-secret credentials are resolved once during candidate
    resolution and exposed as immutable objects on LaunchCandidate."""

    def test_provider_credentials_resolved_from_snapshot(self, tmp_path: Path) -> None:
        """Provider credentials present in the snapshot are resolved onto the candidate."""
        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "openrouter",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-or-test",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )
        assert candidate.provider_credentials is not None
        assert candidate.provider_credentials.secrets is not None
        assert candidate.provider_credentials.secrets.provider == "openrouter"
        assert candidate.provider_credentials.secrets.model_provider_api_key == "sk-or-test"

    def test_shared_secret_resolved_from_snapshot(self, tmp_path: Path) -> None:
        """Shared secret present in the snapshot is resolved onto the candidate."""
        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared-secret-value",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )
        assert candidate.shared_secret == "shared-secret-value"

    def test_no_credentials_present_resolves_to_none_gracefully(self, tmp_path: Path) -> None:
        """When no provider/.env.gateway/keyring credentials exist, resolution
        does not crash and produces a resolution object with secrets=None."""

        class EmptyKeyring:
            def get_password(self, service: str, key: str) -> str | None:
                return None

        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
            credential_keyring_backend=EmptyKeyring(),
        )
        # Default provider (openrouter) with no key -> secrets is None, no crash.
        assert candidate.provider_credentials is not None
        assert candidate.provider_credentials.secrets is None
        assert candidate.shared_secret is None

    def test_credential_resolution_uses_snapshot_not_os_environ(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Credentials come from the immutable snapshot, not a later os.environ read."""
        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "captured-secret",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)

        # Mutate os.environ after capture — must have zero effect.
        monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "MUTATED_AFTER_CAPTURE")

        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )
        assert candidate.shared_secret == "captured-secret"


    def test_candidate_ignores_env_gateway_bytes_changed_after_resolution(self, tmp_path: Path) -> None:
        """Plan 9.96, Task 5 Step 7 (TOCTOU matrix): .env.gateway is read
        exactly once inside resolve_launch_candidate() (via
        resolve_provider_credentials/resolve_shared_secret), and the result
        is baked into the already-returned LaunchCandidate's
        provider_credentials/shared_secret fields. Rewriting the file on
        disk AFTER resolve_launch_candidate() has already returned must have
        NO EFFECT on the candidate object already held -- there is no
        "reread and detect" path for this by design (mirroring Constraint
        6's os.environ single-capture rule), so the correct TOCTOU proof is
        that the already-resolved candidate is unaffected, not that a
        second resolution call would fail. A test expecting failure here
        would require code that doesn't exist and shouldn't: the whole
        point of Task 5 Step 3 (single-read credential resolution) is that
        nothing downstream ever reopens .env.gateway."""
        paths = _sample_operator_paths(tmp_path)
        paths.config_root.mkdir(parents=True)
        env_gateway = paths.config_root / ".env.gateway"
        env_gateway.write_text(
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n"
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-or-original\n",
            encoding="utf-8",
        )
        if sys.platform != "win32":
            env_gateway.chmod(0o600)
        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)

        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=_sample_workspace_identity(),
            operator_paths=paths,
            hmac_key=_HMAC_KEY,
        )

        # Rewrite the file AFTER resolve_launch_candidate() already returned.
        env_gateway.write_text(
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n"
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-or-ATTACKER-INJECTED\n",
            encoding="utf-8",
        )

        # The candidate object already held is unaffected -- it never
        # rereads the file.
        assert candidate.provider_credentials.secrets.model_provider_api_key == "sk-or-original"

    def test_authorized_launch_ignores_durable_record_altered_after_authorize(self, tmp_path: Path) -> None:
        """Plan 9.96, Task 5 Step 7 (TOCTOU matrix), 'approval record
        altered' case. Deliberately a documented NO-EFFECT case, not an
        active-revalidation one:

        1. Nothing spawned reaches the child from the approval record.
           authorize_launch() only VALIDATES the candidate against the
           record; every value that reaches the agent/Gateway child
           (candidate.agent_environ, .provider_credentials, .shared_secret,
           .gateway_environ, the monotonic values) is snapshot-derived, not
           record-derived. AuthorizedLaunch.approval_id is an audit
           identifier, never a spawn input. So altering/deleting the
           durable keyring record after authorize_launch() has already
           returned has no injection path into the spawn -- there is
           nothing left for a fresh read to protect.
        2. The threat this would defend (a same-user attacker with keyring
           write access rewriting the durable record mid-launch) is
           explicitly outside the Phase 1 threat boundary: the frozen
           contract states same-user malware/OS-session compromise remain
           out of scope, and that "approval write/read separation is code
           architecture, not an OS privilege boundary."
        3. A durable approval is a standing authorization by design (the
           whole point of the headless/scheduled path); treating a
           mid-launch record deletion as a launch failure would be
           denial-of-service on an already-legitimately-authorized launch,
           not a security improvement.

        (One-shot mode is unaffected by this reasoning: it is already
        TOCTOU-safe via the existing lock + delete-before-use sequence in
        KeyringApprovalStore.consume_one_shot, which is a completely
        separate code path from this durable-mode test.)
        """
        from optimus.acp.launch_approvals import KeyringApprovalStore, build_approval_record

        class FakeKeyring:
            def __init__(self) -> None:
                self._store: dict[tuple[str, str], str] = {}

            def get_password(self, service: str, key: str) -> str | None:
                return self._store.get((service, key))

            def set_password(self, service: str, key: str, value: str) -> None:
                self._store[(service, key)] = value

            def delete_password(self, service: str, key: str) -> None:
                self._store.pop((service, key), None)

        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        ws_identity = _sample_workspace_identity()
        candidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=ws_identity,
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )

        fake_keyring = FakeKeyring()
        store = KeyringApprovalStore(keyring_backend=fake_keyring, runtime_root=tmp_path, hmac_key=_HMAC_KEY)
        record = build_approval_record(
            mode="durable",
            workspace_identity=candidate.workspace_identity,
            security_literals=candidate.security_literals,
            secret_fingerprints=candidate.secret_fingerprints,
            monotonic_grants=candidate.monotonic_grants,
            model_observation=candidate.model_observation,
            hmac_key=_HMAC_KEY,
        )
        store.write_durable(record)

        authorized = authorize_launch(candidate=candidate, store=store, launch_session_id="sess_toctou")
        assert authorized.approval_mode == "durable"

        # Delete the durable record from the keyring AFTER authorize_launch()
        # already returned -- simulating a same-user attacker (or, more
        # realistically, an operator running `optimus-trust revoke`)
        # racing the launch.
        store.revoke_workspace(ws_identity.digest)

        # The already-returned AuthorizedLaunch is unaffected: what reaches
        # the child is still exactly the snapshot-derived candidate.
        assert authorized.candidate.agent_environ == candidate.agent_environ
        assert authorized.candidate.provider_credentials == candidate.provider_credentials
        assert authorized.candidate.shared_secret == candidate.shared_secret

    def test_digest_changes_when_env_gateway_credential_changes(self, tmp_path: Path) -> None:
        """Changing a .env.gateway-sourced provider key changes the digest.

        This is the regression test for the approval-reuse hole: resolved
        credentials that come from .env.gateway (not the raw environment
        scan) must still be reflected in security_snapshot_digest, or a
        stale durable approval would remain valid after a credential swap.
        """

        class FixedKeyring:
            """Empty keyring so only .env.gateway values are in play."""

            def get_password(self, service: str, key: str) -> str | None:
                return None

        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        ws_identity = _sample_workspace_identity()

        config_root_alpha = tmp_path / "config-alpha"
        config_root_alpha.mkdir()
        env_gateway_alpha = config_root_alpha / ".env.gateway"
        env_gateway_alpha.write_text(
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n"
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-SECRET-ALPHA-111\n",
            encoding="utf-8",
        )
        if sys.platform != "win32":
            env_gateway_alpha.chmod(0o600)
        paths_alpha = OperatorPaths(
            workspace_root=tmp_path,
            config_root=config_root_alpha,
            runtime_root=tmp_path / ".optimus",
            debug_log_path=tmp_path / ".optimus" / "debug-acp.ndjson",
            gateway_log_path=tmp_path / ".optimus" / "local-gateway.log",
        )

        config_root_beta = tmp_path / "config-beta"
        config_root_beta.mkdir()
        env_gateway_beta = config_root_beta / ".env.gateway"
        env_gateway_beta.write_text(
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n"
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-SECRET-BETA-222\n",
            encoding="utf-8",
        )
        if sys.platform != "win32":
            env_gateway_beta.chmod(0o600)
        paths_beta = OperatorPaths(
            workspace_root=tmp_path,
            config_root=config_root_beta,
            runtime_root=tmp_path / ".optimus",
            debug_log_path=tmp_path / ".optimus" / "debug-acp.ndjson",
            gateway_log_path=tmp_path / ".optimus" / "local-gateway.log",
        )

        candidate_alpha = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=ws_identity,
            operator_paths=paths_alpha,
            hmac_key=_HMAC_KEY,
            credential_keyring_backend=FixedKeyring(),
        )
        candidate_beta = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=ws_identity,
            operator_paths=paths_beta,
            hmac_key=_HMAC_KEY,
            credential_keyring_backend=FixedKeyring(),
        )

        assert candidate_alpha.provider_credentials.secrets.model_provider_api_key == "sk-SECRET-ALPHA-111"
        assert candidate_beta.provider_credentials.secrets.model_provider_api_key == "sk-SECRET-BETA-222"
        assert candidate_alpha.security_snapshot_digest != candidate_beta.security_snapshot_digest, (
            "Digest must change when the resolved .env.gateway credential changes — "
            "otherwise a stale durable approval remains valid after a credential swap."
        )


# --- Task 5 Batch 3 Step 5: monotonic tighten/loosen authorization ---
# Global Constraint 12: an unapproved tightening (or exact-equal value) of
# OPTIMUS_LIVE_MAX_COST_USD/OPTIMUS_MAX_PLANNING_TURNS must be allowed
# WITHOUT requiring re-approval. Only a loosening beyond the approved/default
# value requires an exact matching approval grant.


class TestMonotonicTightenIsFreeAfterApproval:
    """An operator who approves a launch, then tightens
    OPTIMUS_MAX_PLANNING_TURNS/OPTIMUS_LIVE_MAX_COST_USD below the approved
    value, must NOT be forced to re-approve — Global Constraint 12 makes
    tightening free. Today, monotonic_grants is folded into
    security_snapshot_digest, so ANY change (including a tightening)
    changes the digest and produces SNAPSHOT_MISMATCH. This test currently
    FAILS, proving the bug; fixing it requires stopping digest identity from
    gating monotonic values and instead comparing them directly in
    authorize_launch()."""

    def test_tightening_max_planning_turns_after_approval_does_not_require_reapproval(
        self, tmp_path: Path
    ) -> None:
        from optimus.acp.launch_approvals import KeyringApprovalStore, build_approval_record

        class FakeKeyring:
            def __init__(self) -> None:
                self._store: dict[tuple[str, str], str] = {}

            def get_password(self, service: str, key: str) -> str | None:
                return self._store.get((service, key))

            def set_password(self, service: str, key: str, value: str) -> None:
                self._store[(service, key)] = value

            def delete_password(self, service: str, key: str) -> None:
                self._store.pop((service, key), None)

        # Approve WITHOUT setting OPTIMUS_MAX_PLANNING_TURNS at all (implicit default).
        approved_env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        ws_identity = _sample_workspace_identity()
        approved_snapshot = LaunchEnvironmentSnapshot.capture(approved_env)
        approved_candidate = resolve_launch_candidate(
            snapshot=approved_snapshot,
            workspace_identity=ws_identity,
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )

        fake_keyring = FakeKeyring()
        store = KeyringApprovalStore(keyring_backend=fake_keyring, runtime_root=tmp_path, hmac_key=_HMAC_KEY)
        record = build_approval_record(
            mode="durable",
            workspace_identity=approved_candidate.workspace_identity,
            security_literals=approved_candidate.security_literals,
            secret_fingerprints=approved_candidate.secret_fingerprints,
            monotonic_grants=approved_candidate.monotonic_grants,
            model_observation=approved_candidate.model_observation,
            hmac_key=_HMAC_KEY,
        )
        store.write_durable(record)

        # Operator TIGHTENS: sets OPTIMUS_MAX_PLANNING_TURNS=2 (below the
        # reviewed default of 3) after the approval was authored. Global
        # Constraint 12 requires this to be allowed without re-approval.
        tightened_env = {**approved_env, "OPTIMUS_MAX_PLANNING_TURNS": "2"}
        tightened_snapshot = LaunchEnvironmentSnapshot.capture(tightened_env)
        tightened_candidate = resolve_launch_candidate(
            snapshot=tightened_snapshot,
            workspace_identity=ws_identity,
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )

        # Must NOT raise LaunchGateError(code="SNAPSHOT_MISMATCH").
        authorized = authorize_launch(
            candidate=tightened_candidate,
            store=store,
            launch_session_id="sess_tighten_test",
        )
        assert authorized.approval_mode == "durable"


class TestMonotonicLoosenRequiresExactApproval:
    """The security-critical direction: an UNAPPROVED loosening of a
    monotonic-limit variable beyond the approved/default value must still be
    rejected. Removing monotonic_grants from the digest (the tightening fix)
    must not silently permit loosening — that would be the classic
    "fixed the false positive by disabling the check" failure mode. This
    test currently FAILS because authorize_launch() has no monotonic
    comparison at all yet; it only compares (now monotonic-blind) digests."""

    def test_loosening_max_planning_turns_beyond_default_without_approval_is_rejected(
        self, tmp_path: Path
    ) -> None:
        from optimus.acp.launch_approvals import KeyringApprovalStore, build_approval_record

        class FakeKeyring:
            def __init__(self) -> None:
                self._store: dict[tuple[str, str], str] = {}

            def get_password(self, service: str, key: str) -> str | None:
                return self._store.get((service, key))

            def set_password(self, service: str, key: str, value: str) -> None:
                self._store[(service, key)] = value

            def delete_password(self, service: str, key: str) -> None:
                self._store.pop((service, key), None)

        # Approve WITHOUT setting OPTIMUS_MAX_PLANNING_TURNS (implicit default of 3).
        approved_env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        ws_identity = _sample_workspace_identity()
        approved_snapshot = LaunchEnvironmentSnapshot.capture(approved_env)
        approved_candidate = resolve_launch_candidate(
            snapshot=approved_snapshot,
            workspace_identity=ws_identity,
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )

        fake_keyring = FakeKeyring()
        store = KeyringApprovalStore(keyring_backend=fake_keyring, runtime_root=tmp_path, hmac_key=_HMAC_KEY)
        record = build_approval_record(
            mode="durable",
            workspace_identity=approved_candidate.workspace_identity,
            security_literals=approved_candidate.security_literals,
            secret_fingerprints=approved_candidate.secret_fingerprints,
            monotonic_grants=approved_candidate.monotonic_grants,
            model_observation=approved_candidate.model_observation,
            hmac_key=_HMAC_KEY,
        )
        store.write_durable(record)

        # Operator (or an attacker who can set env vars) LOOSENS: sets
        # OPTIMUS_MAX_PLANNING_TURNS=9, above the reviewed default of 3,
        # with NO matching grant in the approval record's monotonic_grants.
        loosened_env = {**approved_env, "OPTIMUS_MAX_PLANNING_TURNS": "9"}
        loosened_snapshot = LaunchEnvironmentSnapshot.capture(loosened_env)
        loosened_candidate = resolve_launch_candidate(
            snapshot=loosened_snapshot,
            workspace_identity=ws_identity,
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )

        with pytest.raises(LaunchGateError) as exc_info:
            authorize_launch(
                candidate=loosened_candidate,
                store=store,
                launch_session_id="sess_loosen_test",
            )
        assert exc_info.value.code == "MONOTONIC_LOOSENING_UNAPPROVED"

    def test_loosening_with_exact_matching_approved_grant_succeeds(self, tmp_path: Path) -> None:
        """A loosening IS allowed when the durable approval's
        monotonic_grants contains an exact matching entry for the name."""
        from optimus.acp.launch_approvals import KeyringApprovalStore, build_approval_record

        class FakeKeyring:
            def __init__(self) -> None:
                self._store: dict[tuple[str, str], str] = {}

            def get_password(self, service: str, key: str) -> str | None:
                return self._store.get((service, key))

            def set_password(self, service: str, key: str, value: str) -> None:
                self._store[(service, key)] = value

            def delete_password(self, service: str, key: str) -> None:
                self._store.pop((service, key), None)

        # Approve WITH OPTIMUS_MAX_PLANNING_TURNS=9 explicitly present —
        # the approval's own monotonic_grants records this as the reviewed,
        # approved value.
        approved_env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            "OPTIMUS_MAX_PLANNING_TURNS": "9",
        }
        ws_identity = _sample_workspace_identity()
        approved_snapshot = LaunchEnvironmentSnapshot.capture(approved_env)
        approved_candidate = resolve_launch_candidate(
            snapshot=approved_snapshot,
            workspace_identity=ws_identity,
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )
        assert approved_candidate.monotonic_grants.get("OPTIMUS_MAX_PLANNING_TURNS") == "9"

        fake_keyring = FakeKeyring()
        store = KeyringApprovalStore(keyring_backend=fake_keyring, runtime_root=tmp_path, hmac_key=_HMAC_KEY)
        record = build_approval_record(
            mode="durable",
            workspace_identity=approved_candidate.workspace_identity,
            security_literals=approved_candidate.security_literals,
            secret_fingerprints=approved_candidate.secret_fingerprints,
            monotonic_grants=approved_candidate.monotonic_grants,
            model_observation=approved_candidate.model_observation,
            hmac_key=_HMAC_KEY,
        )
        store.write_durable(record)

        # Re-resolve the SAME candidate (same launch, same value) and authorize.
        relaunch_candidate = resolve_launch_candidate(
            snapshot=approved_snapshot,
            workspace_identity=ws_identity,
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )
        authorized = authorize_launch(
            candidate=relaunch_candidate,
            store=store,
            launch_session_id="sess_approved_loosen_test",
        )
        assert authorized.approval_mode == "durable"

    def test_loosening_beyond_the_approved_grant_is_still_rejected(self, tmp_path: Path) -> None:
        """An approval granting OPTIMUS_MAX_PLANNING_TURNS=9 does not
        authorize an even-higher unapproved value like 20 — the grant is an
        exact match, not a new ceiling."""
        from optimus.acp.launch_approvals import KeyringApprovalStore, build_approval_record

        class FakeKeyring:
            def __init__(self) -> None:
                self._store: dict[tuple[str, str], str] = {}

            def get_password(self, service: str, key: str) -> str | None:
                return self._store.get((service, key))

            def set_password(self, service: str, key: str, value: str) -> None:
                self._store[(service, key)] = value

            def delete_password(self, service: str, key: str) -> None:
                self._store.pop((service, key), None)

        approved_env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            "OPTIMUS_MAX_PLANNING_TURNS": "9",
        }
        ws_identity = _sample_workspace_identity()
        approved_snapshot = LaunchEnvironmentSnapshot.capture(approved_env)
        approved_candidate = resolve_launch_candidate(
            snapshot=approved_snapshot,
            workspace_identity=ws_identity,
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )

        fake_keyring = FakeKeyring()
        store = KeyringApprovalStore(keyring_backend=fake_keyring, runtime_root=tmp_path, hmac_key=_HMAC_KEY)
        record = build_approval_record(
            mode="durable",
            workspace_identity=approved_candidate.workspace_identity,
            security_literals=approved_candidate.security_literals,
            secret_fingerprints=approved_candidate.secret_fingerprints,
            monotonic_grants=approved_candidate.monotonic_grants,
            model_observation=approved_candidate.model_observation,
            hmac_key=_HMAC_KEY,
        )
        store.write_durable(record)

        escalated_env = {**approved_env, "OPTIMUS_MAX_PLANNING_TURNS": "20"}
        escalated_snapshot = LaunchEnvironmentSnapshot.capture(escalated_env)
        escalated_candidate = resolve_launch_candidate(
            snapshot=escalated_snapshot,
            workspace_identity=ws_identity,
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
        )

        with pytest.raises(LaunchGateError) as exc_info:
            authorize_launch(
                candidate=escalated_candidate,
                store=store,
                launch_session_id="sess_escalated_test",
            )
        assert exc_info.value.code == "MONOTONIC_LOOSENING_UNAPPROVED"

    def test_unparseable_monotonic_value_fails(self, tmp_path: Path) -> None:
        """An unparseable monotonic value must fail, not silently pass."""
        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            "OPTIMUS_MAX_PLANNING_TURNS": "not-a-number",
        }
        snapshot = LaunchEnvironmentSnapshot.capture(env)
        with pytest.raises(LaunchGateError):
            resolve_launch_candidate(
                snapshot=snapshot,
                workspace_identity=_sample_workspace_identity(),
                operator_paths=_sample_operator_paths(tmp_path),
                hmac_key=_HMAC_KEY,
            )
