"""Shared fixtures for tests/unit/acp.

Plan 9.96, Task 5: __main__.py now gates every launch through
resolve_launch_candidate/authorize_launch before any Redis/Gateway/agent/
debug-file/preflight side effect. Tests that exercise main() need a way to
pre-author a durable approval matching a given environment WITHOUT touching
the real OS keyring — FakeKeyring and authorize_workspace_for_test() below
do exactly that, using the same construction sequence __main__.py itself
uses so the resulting approval's digest genuinely matches what main() will
compute (rather than a hand-rolled shortcut that could silently diverge).
"""

from __future__ import annotations

import sys
from pathlib import Path

from optimus.acp.launch_approvals import KeyringApprovalStore, build_approval_record
from optimus.acp.launch_gate import LaunchCandidate, resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.operator_paths import resolve_authorized_operator_paths
from optimus.acp.trusted_paths import resolve_workspace_identity


class FakeKeyring:
    """In-memory keyring backend. Never touches the real OS keychain."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        return self._store.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self._store[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        self._store.pop((service, key), None)


def authorize_workspace_for_test(
    *,
    env: dict[str, str],
    workspace_root: Path,
    fake_keyring: FakeKeyring,
    runtime_root: Path | None = None,
) -> LaunchCandidate:
    """Author a durable approval for `env`/`workspace_root` using the exact
    same resolve_launch_candidate/build_approval_record sequence __main__.py
    uses internally, so main()'s own authorization check succeeds against
    the identical digest. Returns the resolved candidate for convenience.
    """
    snapshot = LaunchEnvironmentSnapshot.capture(env)
    workspace_identity = resolve_workspace_identity(workspace_root)
    paths = resolve_authorized_operator_paths(
        workspace_root=workspace_root,
        snapshot_values=snapshot.values,
        platform_name=sys.platform,
    )
    store = KeyringApprovalStore(
        keyring_backend=fake_keyring,
        runtime_root=runtime_root or (workspace_root / ".optimus-runtime"),
    )
    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_identity=workspace_identity,
        operator_paths=paths,
        hmac_key=store.hmac_key,
    )
    record = build_approval_record(
        mode="durable",
        workspace_identity=workspace_identity,
        security_literals=candidate.security_literals,
        secret_fingerprints=candidate.secret_fingerprints,
        monotonic_grants=candidate.monotonic_grants,
        model_observation=candidate.model_observation,
        hmac_key=store.hmac_key,
    )
    store.write_durable(record)
    return candidate
