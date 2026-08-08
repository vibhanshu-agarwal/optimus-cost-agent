"""Runtime redaction-input supply and in-memory structured ingress contracts."""

from __future__ import annotations

from pathlib import Path

import pytest


def _abs(tmp_path: Path, name: str) -> Path:
    path = (tmp_path / name).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _bootstrap(
    tmp_path: Path,
    *,
    secrets: tuple[str, ...] = ("svc-secret-alpha",),
    identities: tuple[str, ...] = ("operator@example.test",),
):
    from evidence_handoff_runtime.config import LifecycleBootstrapContext
    from optimus_security.sanitization import PathAliasRule

    capture = _abs(tmp_path, "capture")
    staging = _abs(tmp_path, "staging")
    quarantine = _abs(tmp_path, "quarantine")
    forbidden = _abs(tmp_path, "forbidden")
    return LifecycleBootstrapContext(
        service_secrets=secrets,
        identity_values=identities,
        path_aliases=(PathAliasRule(source_root=str(capture), alias="<temp>"),),
        temporary_capture_root=capture,
        staging_root=staging,
        quarantine_root=quarantine,
        forbidden_persistence_roots=(forbidden,),
        allowed_origins=("http://127.0.0.1:8765",),
        enrollment_principal_ids=("reviewer-1",),
        capabilities=("review-ruling",),
    )


def test_enabled_empty_inventory_fails_readiness(tmp_path: Path) -> None:
    from evidence_handoff_runtime.config import FeatureConfig, LifecycleBootstrapError
    from evidence_handoff_runtime.inputs import RuntimeInputSupplier

    config = FeatureConfig.from_mapping({"enabled": "true"})
    bootstrap = _bootstrap(tmp_path, secrets=(), identities=())
    supplier = RuntimeInputSupplier(config=config, startup=bootstrap)

    with pytest.raises(LifecycleBootstrapError) as raised:
        supplier.startup_inputs()
    assert raised.value.code == "empty_runtime_inventory"
    assert "secret" not in str(raised.value).lower() or str(raised.value) == "empty_runtime_inventory"


def test_disabled_empty_inventory_does_not_require_startup_inputs(tmp_path: Path) -> None:
    from evidence_handoff_runtime.config import FeatureConfig
    from evidence_handoff_runtime.control_state import build_control_state
    from evidence_handoff_runtime.inputs import RuntimeInputSupplier

    config = FeatureConfig.from_mapping({})
    bootstrap = _bootstrap(tmp_path, secrets=(), identities=())
    supplier = RuntimeInputSupplier(config=config, startup=bootstrap)
    state = build_control_state(config)

    assert state.availability.value == "disabled"
    assert state.may_start_infrastructure is False
    # Disabled path must not force inventory readiness; supplier stays inert.
    assert supplier.startup_inputs_required is False


def test_startup_inputs_populate_real_redaction_runtime_inputs(tmp_path: Path) -> None:
    from evidence_handoff.redaction.models import RedactionRuntimeInputs
    from evidence_handoff_runtime.config import FeatureConfig
    from evidence_handoff_runtime.inputs import RuntimeInputSupplier

    secret = "svc-secret-alpha"
    identity = "operator@example.test"
    config = FeatureConfig.from_mapping({"enabled": "true"})
    bootstrap = _bootstrap(tmp_path, secrets=(secret,), identities=(identity,))
    supplier = RuntimeInputSupplier(config=config, startup=bootstrap)

    runtime = supplier.startup_inputs()
    assert isinstance(runtime, RedactionRuntimeInputs)
    assert runtime.temporary_capture_root == bootstrap.temporary_capture_root
    assert runtime.staging_root == bootstrap.staging_root
    assert runtime.quarantine_root == bootstrap.quarantine_root
    assert runtime.forbidden_persistence_roots == bootstrap.forbidden_persistence_roots
    assert runtime.path_aliases == bootstrap.path_aliases
    assert secret in runtime.sensitive_values.secret_values_for_sanitizer()
    assert identity in runtime.sensitive_values.pii_values_for_sanitizer()


def test_request_inputs_adds_ephemeral_credential_and_retains_none(tmp_path: Path) -> None:
    from evidence_handoff_runtime.config import FeatureConfig
    from evidence_handoff_runtime.inputs import RuntimeInputSupplier

    secret = "svc-secret-alpha"
    request_credential = "request-credential-canary-value"
    config = FeatureConfig.from_mapping({"enabled": "true"})
    bootstrap = _bootstrap(tmp_path, secrets=(secret,), identities=("operator@example.test",))
    supplier = RuntimeInputSupplier(config=config, startup=bootstrap)

    request_inputs = supplier.request_inputs(request_credential)
    sanitizer_secrets = request_inputs.runtime.sensitive_values.secret_values_for_sanitizer()
    assert request_credential in sanitizer_secrets
    assert secret in sanitizer_secrets

    # Supplier must not retain the request credential after returning the snapshot.
    retained = repr(supplier)
    assert request_credential not in retained
    assert getattr(supplier, "_request_credential", None) in (None, "")


def test_request_and_startup_inputs_omit_values_from_repr(tmp_path: Path) -> None:
    from evidence_handoff_runtime.config import FeatureConfig
    from evidence_handoff_runtime.inputs import RuntimeInputSupplier

    secret = "svc-secret-alpha"
    identity = "operator@example.test"
    request_credential = "request-credential-canary-value"
    config = FeatureConfig.from_mapping({"enabled": "true"})
    bootstrap = _bootstrap(tmp_path, secrets=(secret,), identities=(identity,))
    supplier = RuntimeInputSupplier(config=config, startup=bootstrap)
    runtime = supplier.startup_inputs()
    request_inputs = supplier.request_inputs(request_credential)

    for rendered in (repr(runtime), repr(request_inputs), repr(supplier), repr(bootstrap)):
        assert secret not in rendered
        assert identity not in rendered
        assert request_credential not in rendered


def test_structured_ingress_sanitizes_draft_with_request_inputs(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import IngressTextDraft, StructuredIngress
    from evidence_handoff_runtime.config import FeatureConfig
    from evidence_handoff_runtime.inputs import RuntimeInputSupplier

    secret = "svc-secret-alpha"
    request_credential = "request-credential-canary-value"
    config = FeatureConfig.from_mapping({"enabled": "true"})
    bootstrap = _bootstrap(tmp_path, secrets=(secret,), identities=("operator@example.test",))
    supplier = RuntimeInputSupplier(config=config, startup=bootstrap)
    inputs = supplier.request_inputs(request_credential)

    draft = IngressTextDraft(
        kind="review-ruling",
        message_text=f"ruling body contains {secret} and {request_credential}",
    )
    result = StructuredIngress().sanitize(draft, inputs)

    assert result.ok is True
    assert secret not in result.message_text
    assert request_credential not in result.message_text
    assert result.rule_counts
    assert result.content_sha256
    assert len(result.content_sha256) == 64
    assert secret not in repr(result)
    assert request_credential not in repr(result)


def test_structured_ingress_rejects_empty_inventory_without_leaking_values(
    tmp_path: Path,
) -> None:
    from evidence_handoff.redaction.ingress import (
        IngressRejection,
        IngressTextDraft,
        RequestRedactionInputs,
        StructuredIngress,
    )
    from evidence_handoff.redaction.models import RedactionRuntimeInputs
    from optimus_security.sensitive_values import SensitiveValueInventory

    capture = _abs(tmp_path, "capture")
    staging = _abs(tmp_path, "staging")
    quarantine = _abs(tmp_path, "quarantine")
    forbidden = _abs(tmp_path, "forbidden")
    empty = RequestRedactionInputs(
        runtime=RedactionRuntimeInputs(
            sensitive_values=SensitiveValueInventory(),
            path_aliases=(),
            temporary_capture_root=capture,
            staging_root=staging,
            quarantine_root=quarantine,
            forbidden_persistence_roots=(forbidden,),
        )
    )
    draft = IngressTextDraft(kind="review-ruling", message_text="harmless text")
    result = StructuredIngress().sanitize(draft, empty)
    assert result.ok is False
    assert result.reason_code == "empty_runtime_inventory"
    assert isinstance(result, IngressRejection) or result.reason_code == "empty_runtime_inventory"
