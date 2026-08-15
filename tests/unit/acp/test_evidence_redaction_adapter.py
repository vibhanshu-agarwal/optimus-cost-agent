"""Unit tests for the Optimus evidence redaction host adapter."""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path
from typing import get_type_hints

import pytest

from optimus.acp.evidence_redaction_adapter import (
    EvidenceRedactionHostContext,
    assert_portable_runtime_inputs,
    build_redaction_runtime_inputs,
)
from optimus.acp.launch_approvals import KeyringApprovalStore
from optimus.acp.launch_gate import AuthorizedLaunch, LaunchCandidate, authorize_launch, resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.operator_paths import resolve_authorized_operator_paths
from optimus.acp.trusted_paths import resolve_workspace_identity
from tests.unit.acp.conftest import FakeKeyring

ADAPTER_PATH = Path(__file__).resolve().parents[3] / "src/optimus/acp/evidence_redaction_adapter.py"


class _FakeCredentialKeyring:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        return self._store.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self._store[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        self._store.pop((service, key), None)


def _authorized_launch(
    tmp_path: Path,
    *,
    env: dict[str, str],
    credential_keyring: _FakeCredentialKeyring | None = None,
) -> AuthorizedLaunch:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    snapshot = LaunchEnvironmentSnapshot.capture(env)
    paths = resolve_authorized_operator_paths(
        workspace_root=workspace,
        snapshot_values=snapshot.values,
        platform_name=sys.platform,
    )
    (paths.runtime_root).mkdir(parents=True, exist_ok=True)
    fake_approvals = FakeKeyring()
    store = KeyringApprovalStore(keyring_backend=fake_approvals, runtime_root=paths.runtime_root)
    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_identity=resolve_workspace_identity(workspace),
        operator_paths=paths,
        hmac_key=store.hmac_key,
        credential_keyring_backend=credential_keyring,
    )
    # Seed a matching durable approval via the same digest inputs.
    from optimus.acp.launch_approvals import build_approval_record

    record = build_approval_record(
        mode="durable",
        workspace_identity=candidate.workspace_identity,
        security_literals=candidate.security_literals,
        secret_fingerprints=candidate.secret_fingerprints,
        monotonic_grants=candidate.monotonic_grants,
        model_observation=candidate.model_observation,
        hmac_key=store.hmac_key,
    )
    store.write_durable(record)
    return authorize_launch(
        candidate=candidate,
        store=store,
        approval_id=None,
        launch_session_id="session-redaction-adapter-test",
    )


def _host_context(tmp_path: Path, launch: AuthorizedLaunch) -> EvidenceRedactionHostContext:
    profile = tmp_path / "profile"
    user_data = tmp_path / "user-data"
    capture = tmp_path / "capture"
    staging = tmp_path / "staging"
    quarantine = tmp_path / "quarantine"
    forbidden = tmp_path / "forbidden-cloud"
    for path in (profile, user_data, capture, staging, quarantine, forbidden):
        path.mkdir()
    return EvidenceRedactionHostContext(
        authorized_launch=launch,
        operator_profile_root=profile.resolve(),
        user_data_roots=(user_data.resolve(),),
        temporary_capture_root=capture.resolve(),
        staging_root=staging.resolve(),
        quarantine_root=quarantine.resolve(),
        operator_identity_values=("operator-canary", "host-canary"),
        forbidden_persistence_roots=(
            launch.candidate.operator_paths.workspace_root.resolve(),
            forbidden.resolve(),
        ),
    )


def test_host_context_has_exact_eight_fields() -> None:
    names = {field.name for field in EvidenceRedactionHostContext.__dataclass_fields__.values()}
    assert names == {
        "authorized_launch",
        "operator_profile_root",
        "user_data_roots",
        "temporary_capture_root",
        "staging_root",
        "quarantine_root",
        "operator_identity_values",
        "forbidden_persistence_roots",
    }
    signature = inspect.signature(build_redaction_runtime_inputs)
    assert list(signature.parameters) == ["context"]
    hints = get_type_hints(build_redaction_runtime_inputs)
    assert hints["context"] is EvidenceRedactionHostContext
    assert hints["return"].__name__ == "RedactionRuntimeInputs"


def test_adapter_includes_projected_secret_inventory_values(tmp_path: Path) -> None:
    launch = _authorized_launch(
        tmp_path,
        env={
            "OPTIMUS_API_KEY": "agent-env-secret-canary",
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "gateway-env-shared-canary",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "openrouter",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-env-provider-canary",
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:9",
        },
    )
    result = build_redaction_runtime_inputs(_host_context(tmp_path, launch))
    secrets = result.sensitive_values.secret_values_for_sanitizer()
    assert "agent-env-secret-canary" in secrets
    assert "gateway-env-shared-canary" in secrets
    assert "sk-env-provider-canary" in secrets


def test_adapter_includes_keyring_resolved_provider_and_shared_secret(tmp_path: Path) -> None:
    creds = _FakeCredentialKeyring()
    creds.set_password("optimus-cost-agent", "model_provider", "openrouter")
    creds.set_password("optimus-cost-agent", "model_provider_api_key", "sk-keyring-provider-canary")
    creds.set_password("optimus-cost-agent", "local_gateway_shared_secret", "keyring-shared-canary")
    launch = _authorized_launch(
        tmp_path,
        env={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:9"},
        credential_keyring=creds,
    )
    result = build_redaction_runtime_inputs(_host_context(tmp_path, launch))
    secrets = set(result.sensitive_values.secret_values_for_sanitizer())
    assert "sk-keyring-provider-canary" in secrets
    assert "keyring-shared-canary" in secrets
    assert result.sensitive_values.source_class_counts.get("keyring", 0) >= 1


def test_adapter_injects_identity_pii_and_longest_root_aliases(tmp_path: Path) -> None:
    launch = _authorized_launch(
        tmp_path,
        env={
            "OPTIMUS_API_KEY": "alias-env-secret",
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "alias-shared",
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:9",
        },
    )
    context = _host_context(tmp_path, launch)
    result = build_redaction_runtime_inputs(context)
    pii = result.sensitive_values.pii_values_for_sanitizer()
    assert "operator-canary" in pii
    assert "host-canary" in pii
    aliases = [(rule.alias, rule.source_root) for rule in result.path_aliases]
    alias_names = {alias for alias, _ in aliases}
    assert {"<workspace>", "<user-data>", "<temp>", "<staging>", "<quarantine>"} <= alias_names
    roots = [Path(root).as_posix() for _, root in aliases]
    assert roots == sorted(roots, key=len, reverse=True)


def test_portable_result_contains_no_optimus_host_objects(tmp_path: Path) -> None:
    launch = _authorized_launch(
        tmp_path,
        env={
            "OPTIMUS_API_KEY": "boundary-secret",
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "boundary-shared",
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:9",
        },
    )
    result = build_redaction_runtime_inputs(_host_context(tmp_path, launch))
    assert_portable_runtime_inputs(result)
    assert not isinstance(result.sensitive_values, AuthorizedLaunch)
    assert not isinstance(result.sensitive_values, LaunchCandidate)
    assert isinstance(result.temporary_capture_root, Path)


def test_adapter_source_does_not_call_ambient_resolvers() -> None:
    tree = ast.parse(ADAPTER_PATH.read_text(encoding="utf-8"))
    banned_names = {"environ", "getenv", "keyring", "dotenv", "resolve_trusted_operator_roots"}
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in banned_names:
            hits.append(node.attr)
        if isinstance(node, ast.Name) and node.id in {"keyring", "dotenv"}:
            hits.append(node.id)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {"keyring", "dotenv"} or alias.name.startswith("dotenv"):
                    hits.append(alias.name)
        if isinstance(node, ast.ImportFrom):
            if node.module in {"keyring", "dotenv"} or (node.module or "").startswith("dotenv"):
                hits.append(node.module or "")
            if node.module == "os" and any(alias.name in {"environ", "getenv"} for alias in node.names):
                hits.append("os.environ")
    assert hits == []


def test_client_mcp_audit_fields_redact_raw_values_and_forbid_gateway_label() -> None:
    """P11-FU-9 Task 7: evidence/audit paths expose only safe client-MCP metadata."""
    from optimus.acp.evidence_redaction_adapter import build_client_mcp_audit_fields
    from optimus.mcp.client_config import ClientMcpSafeView

    raw_secret = "sk-live-must-never-cross-evidence"
    view = ClientMcpSafeView(
        provenance="client_supplied_acp",
        transport="http",
        server_name="tools",
        canonical_target="https://mcp.example.com/audit",
        arguments=(),
        credential_names=("Authorization", "api_key"),
        credential_name_fingerprints=("fp-auth", "fp-query"),
        scanner_rule_ids=(),
        disposition="normalized",
    )
    fields = build_client_mcp_audit_fields(safe_view=view, outcome="allow_once")
    blob = repr(fields)
    assert fields["provenance"] == "client_supplied_acp"
    assert fields["transport"] == "http"
    assert fields["disposition"] == "normalized"
    assert fields["outcome"] == "allow_once"
    assert fields["credential_present"] is True
    assert fields["credential_names"] == ("Authorization", "api_key")
    assert fields["credential_name_fingerprints"] == ("fp-auth", "fp-query")
    assert raw_secret not in blob
    assert "gateway_brokered_mcp" not in blob
    assert "gateway_brokered_mcp" not in fields.values()
    assert all(v != raw_secret for v in fields.values())


def test_client_mcp_audit_fields_from_runtime_capability_safe_view_only() -> None:
    """Structured safe-view path must not serialize runtime header/env values."""
    from optimus.acp.evidence_redaction_adapter import build_client_mcp_audit_fields
    from optimus.mcp.client_config import (
        ClientMcpRuntimeCapability,
        ClientMcpSafeIdentity,
        ClientMcpSafeView,
    )

    secret = "runtime-header-secret-value"
    identity = ClientMcpSafeIdentity(
        transport="http",
        server_name="tools",
        canonical_target="https://mcp.example.com/cap",
        arguments=(),
        credential_name_fingerprints=("fp1",),
    )
    view = ClientMcpSafeView(
        provenance="client_supplied_acp",
        transport="http",
        server_name="tools",
        canonical_target="https://mcp.example.com/cap",
        arguments=(),
        credential_names=("Authorization",),
        credential_name_fingerprints=("fp1",),
        scanner_rule_ids=(),
        disposition="normalized",
    )
    capability = ClientMcpRuntimeCapability(
        safe_identity=identity,
        safe_view=view,
        header_values={"Authorization": secret},
        env_values={},
    )
    fields = build_client_mcp_audit_fields(runtime_capability=capability, outcome="leased")
    assert secret not in repr(fields)
    assert secret not in repr(capability)
    assert fields["provenance"] == "client_supplied_acp"
    assert "gateway_brokered_mcp" not in repr(fields)


def test_client_mcp_audit_error_path_does_not_leak_raw_values() -> None:
    from optimus.acp.evidence_redaction_adapter import (
        EvidenceRedactionAdapterError,
        build_client_mcp_audit_fields,
    )

    with pytest.raises(EvidenceRedactionAdapterError) as exc_info:
        build_client_mcp_audit_fields(safe_view=None, outcome="denied")  # type: ignore[arg-type]
    assert "sk-" not in repr(exc_info.value)
    assert "gateway_brokered_mcp" not in repr(exc_info.value)
    assert str(exc_info.value) == exc_info.value.code
