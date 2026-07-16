"""Integration test for the real assembled Plan 9.96 launch-trust flow.

Plan 9.96, Task 5 Batch 3 (capstone): unlike the unit tests elsewhere in this
plan, which deliberately isolate one seam at a time (resolve_launch_candidate
alone, authorize_launch alone, revalidate_workspace_identity alone), THIS
test's entire job is to prove those seams actually connect when driven
together, end to end, the same way __main__.py's main() drives them:

    capture -> resolve_launch_candidate -> authorize_launch
    -> revalidate_workspace_identity -> audit append -> child construction

Nothing in the chain below is mocked except the keyring BACKEND (a real OS
keychain touch is explicitly out of scope for this test tier — see
Global Constraint 21's "unit fakes prove deterministic policy only" carve-out
for the credential-store layer specifically). Every other seam —
LaunchEnvironmentSnapshot, resolve_workspace_identity/revalidate_workspace_identity,
resolve_authorized_operator_paths, KeyringApprovalStore's real HMAC/serialize/
verify logic, resolve_launch_candidate's real digest computation,
build_approval_record's real digest computation, authorize_launch's real
comparison, append_launch_audit_event's real file write, and
_project_child_env's real registry projection — runs for real. If this test
stubbed resolve_launch_candidate or authorize_launch, it would be testing the
stub, not the integration; it deliberately does not.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from optimus.acp.launch_approvals import (
    LAUNCH_POLICY_COMPATIBILITY,
    KeyringApprovalStore,
    build_approval_record,
)
from optimus.acp.launch_audit import LaunchAuditEvent, append_launch_audit_event
from optimus.acp.launch_gate import (
    LaunchCandidate,
    LaunchGateError,
    authorize_launch,
    resolve_launch_candidate,
)
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot, PropagationTarget
from optimus.acp.local_infra import apply_local_defaults
from optimus.acp.operator_paths import resolve_authorized_operator_paths
from optimus.acp.trusted_paths import (
    TrustedPathError,
    resolve_workspace_identity,
    revalidate_workspace_identity,
)


class FakeKeyring:
    """In-memory keyring backend — the one deliberately-not-real seam.

    Everything ELSE in this test drives the real production code: real
    digest computation, real HMAC signing/verification, real file I/O for
    the audit log, real registry-driven child-env projection. Only the OS
    credential-store touch itself is faked, consistent with how the rest of
    this plan's unit-adjacent tests treat the keyring layer (Global
    Constraint 21 reserves real-keyring evidence for the Task 9 live
    ceremony, not every test that merely needs an approval store).
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        return self._store.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self._store[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        self._store.pop((service, key), None)


def _base_env(*, workspace_root: Path) -> dict[str, str]:
    return {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "test-shared-key",
        "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        # Exercises OPTIMUS_CONFIG_ROOT's own real containment validation
        # inside resolve_authorized_operator_paths -- an absolute path
        # outside the workspace, as a real operator override would be.
        "OPTIMUS_CONFIG_ROOT": str((workspace_root.parent / "operator-config").resolve()),
    }


def _real_launch_pipeline(
    *, env: dict[str, str], workspace_root: Path, keyring: FakeKeyring, runtime_root: Path
) -> tuple[LaunchCandidate, KeyringApprovalStore]:
    """Run the real capture -> resolve steps shared by both authoring and
    re-authorizing a launch (mirrors what main() does before it ever touches
    the approval store)."""
    snapshot = LaunchEnvironmentSnapshot.capture(env)
    workspace_identity = resolve_workspace_identity(workspace_root)
    operator_paths = resolve_authorized_operator_paths(
        workspace_root=workspace_root,
        snapshot_values=snapshot.values,
        platform_name=sys.platform,
    )
    store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=runtime_root)
    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_identity=workspace_identity,
        operator_paths=operator_paths,
        hmac_key=store.hmac_key,
    )
    return candidate, store


def test_full_launch_trust_flow_connects_every_real_seam(tmp_path: Path) -> None:
    """Drive the entire chain for real and prove every seam agrees:

    1. An operator authors a durable approval for a workspace (real
       resolve_launch_candidate + real build_approval_record digest).
    2. A LATER, independently re-resolved candidate for the SAME environment
       (simulating a second, separate launch — exactly what a headless
       agent process does) authorizes successfully against that stored
       approval (real authorize_launch digest comparison).
    3. Workspace-identity revalidation passes (real
       revalidate_workspace_identity against the real, unchanged directory).
    4. The audit event is appended for real and reads back byte-for-byte
       correct from disk (real append_launch_audit_event + real file read).
    5. The projected Gateway/agent child environments contain EXACTLY the
       registry-authorized names for this environment — no more, no less
       (real _project_child_env via resolve_launch_candidate).
    """
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root.parent / "operator-config").mkdir()
    runtime_root = workspace_root / ".optimus-runtime"
    keyring = FakeKeyring()
    env = _base_env(workspace_root=workspace_root)

    # --- Step 1: author the durable approval (the "optimus-trust approve" side) ---
    authoring_candidate, store = _real_launch_pipeline(
        env=env, workspace_root=workspace_root, keyring=keyring, runtime_root=runtime_root
    )
    record = build_approval_record(
        mode="durable",
        workspace_identity=authoring_candidate.workspace_identity,
        security_literals=authoring_candidate.security_literals,
        secret_fingerprints=authoring_candidate.secret_fingerprints,
        monotonic_grants=authoring_candidate.monotonic_grants,
        model_observation=authoring_candidate.model_observation,
        hmac_key=store.hmac_key,
    )
    store.write_durable(record)

    # --- Step 2: a SEPARATE, later launch re-resolves the candidate from
    # scratch (its own independent LaunchEnvironmentSnapshot.capture call,
    # its own independent resolve_launch_candidate call) and authorizes
    # against the stored record. This is the real cross-process seam this
    # test exists to prove: two independently computed digests must agree
    # byte-for-byte, or authorization is permanently broken. ---
    launch_candidate, launch_store = _real_launch_pipeline(
        env=env, workspace_root=workspace_root, keyring=keyring, runtime_root=runtime_root
    )
    assert launch_candidate.security_snapshot_digest == authoring_candidate.security_snapshot_digest, (
        "two independent resolve_launch_candidate() calls over the same environment "
        "must produce byte-identical digests, or no launch could ever authorize"
    )

    authorized = authorize_launch(
        candidate=launch_candidate,
        store=launch_store,
        launch_session_id="sess_integration_test",
    )
    assert authorized.approval_mode == "durable"
    assert authorized.approval_id == record.approval_id

    # --- Step 3: real workspace-identity revalidation, the TOCTOU guard
    # wired into __main__.py between authorization and the first side
    # effect (Task 5 Step 7). Proven here against the REAL directory, not a
    # hand-built WorkspaceIdentity. ---
    revalidate_workspace_identity(authorized.candidate.workspace_identity)  # must not raise

    # --- Step 4: real audit append + real read-back from disk. ---
    candidate = authorized.candidate
    setting_decisions = tuple(
        {
            "name": row.name,
            "tier": row.tier.value,
            "source_class": row.source_class,
            "decision": row.decision,
        }
        for row in candidate.display_rows
    )
    event = LaunchAuditEvent(
        timestamp=datetime.now(timezone.utc),
        workspace_digest=candidate.workspace_identity.digest,
        launch_session_id=authorized.launch_session_id,
        approval_id=authorized.approval_id,
        approval_mode=authorized.approval_mode,
        registry_version=LAUNCH_POLICY_COMPATIBILITY,
        policy_version=LAUNCH_POLICY_COMPATIBILITY,
        setting_decisions=setting_decisions,
        monotonic_dispositions=(),
        rejected_names=(),
        child_propagation_decisions={
            "agent_child": tuple(sorted(candidate.agent_environ)),
            "gateway_child": tuple(sorted(candidate.gateway_environ)),
        },
        diagnostic_grant_state="none",
        sanitizer_rule_counts={},
        final_reason_code="AUTHORIZED",
    )
    append_launch_audit_event(event, runtime_root=runtime_root)

    audit_path = runtime_root / "launch-audit.ndjson"
    assert audit_path.is_file()
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    persisted = json.loads(lines[0])
    assert persisted["workspace_digest"] == candidate.workspace_identity.digest
    assert persisted["approval_id"] == record.approval_id
    assert persisted["launch_session_id"] == "sess_integration_test"
    assert persisted["final_reason_code"] == "AUTHORIZED"

    # --- Step 5: exact child-key-set assertions against the real registry
    # projection (_project_child_env inside resolve_launch_candidate), not
    # a hand-maintained expected list that could drift from the registry. ---
    from optimus.acp.launch_policy import LAUNCH_VARIABLE_POLICIES

    expected_agent_keys = {
        name
        for name, policy in LAUNCH_VARIABLE_POLICIES.items()
        if PropagationTarget.AGENT_CHILD in policy.propagation and env.get(name, "").strip()
    }
    expected_gateway_keys = {
        name
        for name, policy in LAUNCH_VARIABLE_POLICIES.items()
        if PropagationTarget.GATEWAY_CHILD in policy.propagation and env.get(name, "").strip()
    }
    assert set(candidate.agent_environ) == expected_agent_keys
    assert set(candidate.gateway_environ) == expected_gateway_keys
    # OPTIMUS_CONFIG_ROOT is PARENT_ONLY -- must reach neither child, even
    # though it is present (and non-empty) in this test's environment.
    assert "OPTIMUS_CONFIG_ROOT" not in candidate.agent_environ
    assert "OPTIMUS_CONFIG_ROOT" not in candidate.gateway_environ

    # apply_local_defaults operates on the real projected agent_environ, not
    # a hand-built dict -- proving the real seam between launch_gate.py and
    # local_infra.py, one step further down the same chain __main__.py runs.
    agent_environ = apply_local_defaults(
        candidate.agent_environ,
        config_root=candidate.operator_paths.config_root,
        resolved_shared_secret=candidate.shared_secret,
    )
    assert agent_environ["OPTIMUS_GATEWAY_URL"] == env["OPTIMUS_GATEWAY_URL"]
    assert agent_environ["OPTIMUS_API_KEY"] == env["OPTIMUS_API_KEY"]


def test_full_launch_trust_flow_relocated_workspace_fails_revalidation(tmp_path: Path) -> None:
    """Same real chain as above, up through authorization, but proves the
    TOCTOU guard genuinely rejects a real post-authorization relocation —
    the integration-level counterpart to the unit-level mutation test in
    test_main_wiring.py, driven through the real (not __main__.py-mocked)
    resolve_launch_candidate/authorize_launch/revalidate_workspace_identity
    chain end to end."""
    import shutil

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root.parent / "operator-config").mkdir()
    runtime_root = workspace_root / ".optimus-runtime"
    keyring = FakeKeyring()
    env = _base_env(workspace_root=workspace_root)

    authoring_candidate, store = _real_launch_pipeline(
        env=env, workspace_root=workspace_root, keyring=keyring, runtime_root=runtime_root
    )
    record = build_approval_record(
        mode="durable",
        workspace_identity=authoring_candidate.workspace_identity,
        security_literals=authoring_candidate.security_literals,
        secret_fingerprints=authoring_candidate.secret_fingerprints,
        monotonic_grants=authoring_candidate.monotonic_grants,
        model_observation=authoring_candidate.model_observation,
        hmac_key=store.hmac_key,
    )
    store.write_durable(record)

    launch_candidate, launch_store = _real_launch_pipeline(
        env=env, workspace_root=workspace_root, keyring=keyring, runtime_root=runtime_root
    )
    authorized = authorize_launch(
        candidate=launch_candidate,
        store=launch_store,
        launch_session_id="sess_integration_toctou",
    )

    # Relocate the real directory strictly AFTER authorization succeeded.
    shutil.rmtree(workspace_root)
    workspace_root.mkdir()

    with pytest.raises(TrustedPathError) as exc_info:
        revalidate_workspace_identity(authorized.candidate.workspace_identity)
    assert exc_info.value.code == "WORKSPACE_IDENTITY_CHANGED"


def test_full_launch_trust_flow_snapshot_mismatch_fails_closed(tmp_path: Path) -> None:
    """Real chain proving a genuine cross-process divergence — a second
    launch whose effective SECURITY-tier configuration changed since the
    approval was authored — is rejected by the real authorize_launch()
    digest comparison, not a hand-constructed digest mismatch."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root.parent / "operator-config").mkdir()
    runtime_root = workspace_root / ".optimus-runtime"
    keyring = FakeKeyring()
    env = _base_env(workspace_root=workspace_root)

    authoring_candidate, store = _real_launch_pipeline(
        env=env, workspace_root=workspace_root, keyring=keyring, runtime_root=runtime_root
    )
    record = build_approval_record(
        mode="durable",
        workspace_identity=authoring_candidate.workspace_identity,
        security_literals=authoring_candidate.security_literals,
        secret_fingerprints=authoring_candidate.secret_fingerprints,
        monotonic_grants=authoring_candidate.monotonic_grants,
        model_observation=authoring_candidate.model_observation,
        hmac_key=store.hmac_key,
    )
    store.write_durable(record)

    # A genuinely different environment: OPTIMUS_PRODUCTION_MODE is
    # SECURITY-tier, so it changes the real security_snapshot_digest.
    changed_env = dict(env)
    changed_env["OPTIMUS_PRODUCTION_MODE"] = "true"
    changed_candidate, changed_store = _real_launch_pipeline(
        env=changed_env, workspace_root=workspace_root, keyring=keyring, runtime_root=runtime_root
    )
    assert changed_candidate.security_snapshot_digest != authoring_candidate.security_snapshot_digest

    with pytest.raises(LaunchGateError) as exc_info:
        authorize_launch(
            candidate=changed_candidate,
            store=changed_store,
            launch_session_id="sess_integration_mismatch",
        )
    assert exc_info.value.code == "SNAPSHOT_MISMATCH"
