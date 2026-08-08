"""Default-off feature toggle and operator-relay degradation."""

from __future__ import annotations

from pathlib import Path


def test_absent_toggle_disables_feature() -> None:
    from evidence_handoff_runtime.config import FeatureConfig

    config = FeatureConfig.from_mapping({})
    assert config.enabled is False


def test_explicit_false_and_empty_string_keep_feature_disabled() -> None:
    from evidence_handoff_runtime.config import FeatureConfig

    assert FeatureConfig.from_mapping({"enabled": "false"}).enabled is False
    assert FeatureConfig.from_mapping({"enabled": "0"}).enabled is False
    assert FeatureConfig.from_mapping({"enabled": ""}).enabled is False


def test_explicit_true_enables_feature() -> None:
    from evidence_handoff_runtime.config import FeatureConfig

    assert FeatureConfig.from_mapping({"enabled": "true"}).enabled is True
    assert FeatureConfig.from_mapping({"enabled": "1"}).enabled is True


def test_disabled_status_names_operator_relay_not_transport_failure() -> None:
    from evidence_handoff_runtime.config import Availability, FeatureConfig
    from evidence_handoff_runtime.control_state import build_control_state

    state = build_control_state(FeatureConfig.from_mapping({}))
    assert state.availability is Availability.DISABLED
    assert state.active_route == "operator_relay"
    assert "transport" not in state.active_route
    assert state.summary_code == "feature_disabled_operator_relay"


def test_disabled_control_state_does_not_start_process_or_project_credential() -> None:
    from evidence_handoff_runtime.config import FeatureConfig
    from evidence_handoff_runtime.control_state import build_control_state

    state = build_control_state(FeatureConfig.from_mapping({}))
    assert state.may_start_infrastructure is False
    assert state.projected_credential is None


def test_availability_enum_exposes_distinguished_non_ready_states() -> None:
    from evidence_handoff_runtime.config import Availability

    assert set(Availability) == {
        Availability.DISABLED,
        Availability.UNAVAILABLE,
        Availability.INTEGRITY_FAILED,
    }


def test_bootstrap_repr_and_exceptions_omit_secret_values(tmp_path: Path) -> None:
    from evidence_handoff_runtime.config import LifecycleBootstrapContext, LifecycleBootstrapError
    from optimus_security.sanitization import PathAliasRule

    secret = "super-secret-ledger-token-value"
    identity = "operator@example.test"
    capture = (tmp_path / "capture").resolve()
    staging = (tmp_path / "staging").resolve()
    quarantine = (tmp_path / "quarantine").resolve()
    forbidden = (tmp_path / "forbidden").resolve()
    for path in (capture, staging, quarantine, forbidden):
        path.mkdir(parents=True, exist_ok=True)

    bootstrap = LifecycleBootstrapContext(
        service_secrets=(secret,),
        identity_values=(identity,),
        path_aliases=(PathAliasRule(source_root=str(capture), alias="<temp>"),),
        temporary_capture_root=capture,
        staging_root=staging,
        quarantine_root=quarantine,
        forbidden_persistence_roots=(forbidden,),
        allowed_origins=("http://127.0.0.1:8765",),
        enrollment_principal_ids=("reviewer-1",),
        capabilities=("review-ruling",),
    )
    rendered = repr(bootstrap)
    assert secret not in rendered
    assert identity not in rendered
    assert "service_secret_count=1" in rendered
    assert "identity_value_count=1" in rendered

    err = LifecycleBootstrapError("empty_runtime_inventory")
    assert str(err) == "empty_runtime_inventory"
    assert secret not in repr(err)
    assert identity not in repr(err)
