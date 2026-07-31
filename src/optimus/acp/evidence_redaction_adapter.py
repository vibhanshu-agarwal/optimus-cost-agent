"""Optimus host adapter: AuthorizedLaunch → portable RedactionRuntimeInputs.

Consumes only already-resolved host objects and explicit context paths. Does not
read ``os.environ``, dotenv files, keyring APIs, configuration resolvers, or
trusted-root discovery.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

from evidence_handoff.redaction.models import RedactionRuntimeInputs
from optimus.acp.launch_gate import AuthorizedLaunch, LaunchCandidate
from optimus.acp.local_gateway_secrets import CredentialLayer
from optimus_security.sanitization import PathAliasRule
from optimus_security.sensitive_values import (
    SensitiveValueError,
    SensitiveValueInventory,
    SensitiveValueSourceClass,
)

_ALIAS_WORKSPACE = "<workspace>"
_ALIAS_USER_DATA = "<user-data>"
_ALIAS_TEMP = "<temp>"
_ALIAS_STAGING = "<staging>"
_ALIAS_QUARANTINE = "<quarantine>"


class EvidenceRedactionAdapterError(Exception):
    """Value-free host-adapter failure. Message is the stable code only."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"EvidenceRedactionAdapterError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True)
class EvidenceRedactionHostContext:
    """Host-only eight-field context pinned by the evidence-collector contract."""

    authorized_launch: AuthorizedLaunch
    operator_profile_root: Path
    user_data_roots: tuple[Path, ...]
    temporary_capture_root: Path
    staging_root: Path
    quarantine_root: Path
    operator_identity_values: tuple[str, ...]
    forbidden_persistence_roots: tuple[Path, ...]


def build_redaction_runtime_inputs(context: EvidenceRedactionHostContext) -> RedactionRuntimeInputs:
    """Convert host context into portable redaction runtime inputs."""
    try:
        return _build_redaction_runtime_inputs(context)
    except EvidenceRedactionAdapterError:
        raise
    except SensitiveValueError:
        raise
    except Exception:
        # Never chain input-bearing messages into the portable boundary.
        raise EvidenceRedactionAdapterError("host_context_conversion_failed") from None


def _build_redaction_runtime_inputs(context: EvidenceRedactionHostContext) -> RedactionRuntimeInputs:
    if type(context) is not EvidenceRedactionHostContext:
        raise EvidenceRedactionAdapterError("invalid_host_context")
    expected = {
        "authorized_launch",
        "operator_profile_root",
        "user_data_roots",
        "temporary_capture_root",
        "staging_root",
        "quarantine_root",
        "operator_identity_values",
        "forbidden_persistence_roots",
    }
    actual = {field.name for field in fields(context)}
    if actual != expected:
        raise EvidenceRedactionAdapterError("invalid_host_context_fields")

    launch = context.authorized_launch
    if not isinstance(launch, AuthorizedLaunch):
        raise EvidenceRedactionAdapterError("invalid_authorized_launch")
    candidate = launch.candidate
    if not isinstance(candidate, LaunchCandidate):
        raise EvidenceRedactionAdapterError("invalid_launch_candidate")

    inventory = SensitiveValueInventory()
    _ingest_projected_secrets(inventory, candidate)
    _ingest_resolved_credentials(inventory, candidate)
    for identity in context.operator_identity_values:
        if identity:
            inventory.add_pii(identity, source_class=SensitiveValueSourceClass.INJECTED_PII)

    aliases = _build_path_aliases(context, candidate)
    return RedactionRuntimeInputs(
        sensitive_values=inventory,
        path_aliases=aliases,
        temporary_capture_root=context.temporary_capture_root,
        staging_root=context.staging_root,
        quarantine_root=context.quarantine_root,
        forbidden_persistence_roots=context.forbidden_persistence_roots,
    )


def _layer_to_source(layer: CredentialLayer) -> SensitiveValueSourceClass:
    if layer is CredentialLayer.ENVIRONMENT:
        return SensitiveValueSourceClass.ENVIRONMENT
    if layer is CredentialLayer.CONFIG_FILE:
        return SensitiveValueSourceClass.CONFIG_FILE
    if layer is CredentialLayer.KEYRING:
        return SensitiveValueSourceClass.KEYRING
    return SensitiveValueSourceClass.ENVIRONMENT


def _ingest_projected_secrets(inventory: SensitiveValueInventory, candidate: LaunchCandidate) -> None:
    for name in candidate.secret_inventory:
        for mapping in (candidate.agent_environ, candidate.gateway_environ):
            value = mapping.get(name)
            if value:
                inventory.add_secret(value, source_class=SensitiveValueSourceClass.ENVIRONMENT)


def _ingest_resolved_credentials(
    inventory: SensitiveValueInventory,
    candidate: LaunchCandidate,
) -> None:
    provider = candidate.provider_credentials
    if provider is not None and provider.secrets is not None:
        key = provider.secrets.model_provider_api_key
        if key:
            inventory.add_secret(
                key,
                source_class=_layer_to_source(provider.api_key_provenance.layer),
            )
    if candidate.shared_secret:
        inventory.add_secret(
            candidate.shared_secret,
            source_class=_source_class_for_display_name(
                candidate,
                "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET",
                default=SensitiveValueSourceClass.KEYRING,
            ),
        )


def _source_class_for_display_name(
    candidate: LaunchCandidate,
    name: str,
    *,
    default: SensitiveValueSourceClass,
) -> SensitiveValueSourceClass:
    for row in candidate.display_rows:
        if row.name != name:
            continue
        if row.source_class == "inherited":
            return SensitiveValueSourceClass.ENVIRONMENT
        try:
            return SensitiveValueSourceClass(row.source_class)
        except ValueError:
            return default
    return default


def _build_path_aliases(
    context: EvidenceRedactionHostContext,
    candidate: LaunchCandidate,
) -> tuple[PathAliasRule, ...]:
    rules: list[PathAliasRule] = [
        PathAliasRule(
            source_root=str(candidate.operator_paths.workspace_root.resolve()),
            alias=_ALIAS_WORKSPACE,
        ),
        PathAliasRule(
            source_root=str(context.operator_profile_root.resolve()),
            alias=_ALIAS_USER_DATA,
        ),
        PathAliasRule(
            source_root=str(context.temporary_capture_root.resolve()),
            alias=_ALIAS_TEMP,
        ),
        PathAliasRule(
            source_root=str(context.staging_root.resolve()),
            alias=_ALIAS_STAGING,
        ),
        PathAliasRule(
            source_root=str(context.quarantine_root.resolve()),
            alias=_ALIAS_QUARANTINE,
        ),
    ]
    for root in context.user_data_roots:
        rules.append(
            PathAliasRule(
                source_root=str(root.resolve()),
                alias=_ALIAS_USER_DATA,
            )
        )
    # Longest-root-first for sanitizer matching.
    rules.sort(key=lambda rule: len(Path(rule.source_root).as_posix()), reverse=True)
    return tuple(rules)


def assert_portable_runtime_inputs(result: RedactionRuntimeInputs) -> None:
    """Raise if Optimus host types leaked into the portable result."""
    forbidden_types = (AuthorizedLaunch, LaunchCandidate)
    if isinstance(result.sensitive_values, forbidden_types):
        raise EvidenceRedactionAdapterError("optimus_type_crossed_portable_boundary")
    for alias in result.path_aliases:
        if isinstance(alias, forbidden_types):
            raise EvidenceRedactionAdapterError("optimus_type_crossed_portable_boundary")
        if not isinstance(alias, PathAliasRule):
            raise EvidenceRedactionAdapterError("non_portable_alias_type")
    for path in (
        result.temporary_capture_root,
        result.staging_root,
        result.quarantine_root,
        *result.forbidden_persistence_roots,
    ):
        if not isinstance(path, Path):
            raise EvidenceRedactionAdapterError("non_portable_path_type")
        if isinstance(path, forbidden_types):
            raise EvidenceRedactionAdapterError("optimus_type_crossed_portable_boundary")
