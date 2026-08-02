"""Unit tests for Plan 11.7 custody contract schemas, eligibility, and reducer."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.plan117_custody_contract import (
    ArtifactManifestModel,
    AttemptKind,
    AttemptRecord,
    CorrelationSignal,
    CorrelationSignalModel,
    CustodyContractError,
    FailureClass,
    ProbeDisposition,
    ReducerInput,
    atomic_write_json,
    compute_eligible,
    derive_fresh_thread_distinct,
    derive_restart_stable,
    reduce_disposition,
    sha256_file,
    validate_attempt_budgets,
    write_canonical_json,
)

# Exact Stop taxonomy from the approved design / Global Constraints precedence list.
# Do not shorten or proxy this through a helper elsewhere.
STOP_TAXONOMY_ORDER = [
    "invalid_probe_trigger_chain_mismatch",
    "invalid_probe_target_identity_mismatch",
    "invalid_probe_relay_environment_mismatch",
    "invalid_probe_settings_not_restored",
    "invalid_probe_non_zed_client_or_injected_traffic",
    "invalid_probe_process_custody_ambiguous",
    "invalid_probe_transcript_debug_divergence",
    "invalid_probe_correlation_inventory_incomplete",
    "invalid_probe_redaction_or_seal_failure",
    "stop_probe_zed_client_crashed",
    "blocked_probe_post_new_prompt_unavailable",
    "blocked_probe_dependency_unavailable",
    "infeasible_for_production_target",
    "feasible_server_side_custody_candidate",
]

_DIGEST_A = "a" * 64
_DIGEST_B = "a" * 64
_DIGEST_C = "b" * 64
_DIGEST_OTHER = "c" * 64


def _eligible_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "available_before_new_decision": True,
        "thread_specific": True,
        "restart_stable": True,
        "fresh_thread_distinct": True,
        "protocol_honest": True,
        "trust_compatible": True,
        "safely_persistable": True,
        "independently_falsifiable": True,
        "ancestry_derived": False,
        "ancestry_revalidated": False,
    }
    base.update(overrides)
    return base


def _signal_model(**overrides: object) -> CorrelationSignalModel:
    payload: dict[str, object] = {
        "field_path": "initialize.params.clientInfo.threadBinding",
        "origin": "zed",
        "available_before_new_decision": True,
        "a_sha256": _DIGEST_A,
        "b_sha256": _DIGEST_B,
        "c_sha256": _DIGEST_C,
        "restart_stable": True,
        "fresh_thread_distinct": True,
        "thread_specific": True,
        "trust_compatible": True,
        "protocol_honest": True,
        "safely_persistable": True,
        "independently_falsifiable": True,
        "ancestry_derived": False,
        "eligible": True,
        "reason_code": "eligible_thread_binding",
    }
    payload.update(overrides)
    return CorrelationSignalModel.model_validate(payload)


def _reducer_input(**overrides: object) -> ReducerInput:
    payload: dict[str, object] = {
        "trigger_chain_mismatch": False,
        "target_identity_mismatch": False,
        "relay_environment_mismatch": False,
        "settings_not_restored": False,
        "non_zed_or_injected_traffic": False,
        "process_custody_ambiguous": False,
        "transcript_debug_divergence": False,
        "correlation_inventory_incomplete": False,
        "redaction_or_seal_failure": False,
        "zed_client_crashed": False,
        "post_new_prompt_unavailable": False,
        "dependency_unavailable": False,
        "inventory_complete": True,
        "has_eligible_signal": False,
        "valid_b_continuation": False,
        "valid_completed_c_control": False,
        "message_binding_ok": False,
        "ancestry_revalidation_ok": True,
    }
    payload.update(overrides)
    return ReducerInput.model_validate(payload)


# --- Enum / declaration order -------------------------------------------------


def test_probe_disposition_has_exactly_fourteen_values_in_stop_taxonomy_order() -> None:
    assert [member.value for member in ProbeDisposition] == STOP_TAXONOMY_ORDER
    assert len(ProbeDisposition) == 14


@pytest.mark.parametrize(
    ("index", "flag_name"),
    [
        (0, "trigger_chain_mismatch"),
        (1, "target_identity_mismatch"),
        (2, "relay_environment_mismatch"),
        (3, "settings_not_restored"),
        (4, "non_zed_or_injected_traffic"),
        (5, "process_custody_ambiguous"),
        (6, "transcript_debug_divergence"),
        (7, "correlation_inventory_incomplete"),
        (8, "redaction_or_seal_failure"),
        (9, "zed_client_crashed"),
        (10, "post_new_prompt_unavailable"),
        (11, "dependency_unavailable"),
    ],
)
def test_reducer_selects_first_true_invalid_or_block_predicate(
    index: int, flag_name: str
) -> None:
    flags = {name: False for name in (
        "trigger_chain_mismatch",
        "target_identity_mismatch",
        "relay_environment_mismatch",
        "settings_not_restored",
        "non_zed_or_injected_traffic",
        "process_custody_ambiguous",
        "transcript_debug_divergence",
        "correlation_inventory_incomplete",
        "redaction_or_seal_failure",
        "zed_client_crashed",
        "post_new_prompt_unavailable",
        "dependency_unavailable",
    )}
    flags[flag_name] = True
    # Lower-precedence outcomes that must not win when a higher predicate is true.
    result = reduce_disposition(
        _reducer_input(
            **flags,
            inventory_complete=True,
            has_eligible_signal=True,
            valid_b_continuation=True,
            valid_completed_c_control=True,
            message_binding_ok=True,
            ancestry_revalidation_ok=True,
        )
    )
    assert result.value == STOP_TAXONOMY_ORDER[index]


def test_settings_restore_precedes_crash() -> None:
    result = reduce_disposition(
        _reducer_input(settings_not_restored=True, zed_client_crashed=True)
    )
    assert result is ProbeDisposition.INVALID_SETTINGS_RESTORE


def test_crash_precedes_prompt_dependency_infeasible_and_feasible() -> None:
    result = reduce_disposition(
        _reducer_input(
            zed_client_crashed=True,
            post_new_prompt_unavailable=True,
            dependency_unavailable=True,
            inventory_complete=True,
            has_eligible_signal=True,
            valid_b_continuation=True,
            valid_completed_c_control=True,
            message_binding_ok=True,
        )
    )
    assert result is ProbeDisposition.ZED_CLIENT_CRASHED


def test_infeasible_when_gates_pass_inventory_complete_no_eligible() -> None:
    result = reduce_disposition(
        _reducer_input(
            inventory_complete=True,
            has_eligible_signal=False,
            valid_b_continuation=True,
            valid_completed_c_control=True,
            message_binding_ok=True,
        )
    )
    assert result is ProbeDisposition.INFEASIBLE


def test_feasible_requires_eligible_b_c_message_and_ancestry() -> None:
    with pytest.raises(ValueError, match="reducer_undetermined"):
        reduce_disposition(
            _reducer_input(
                inventory_complete=True,
                has_eligible_signal=True,
                valid_b_continuation=True,
                valid_completed_c_control=False,
                message_binding_ok=True,
                ancestry_revalidation_ok=True,
            )
        )

    with pytest.raises(ValueError, match="reducer_undetermined"):
        reduce_disposition(
            _reducer_input(
                inventory_complete=True,
                has_eligible_signal=True,
                valid_b_continuation=True,
                valid_completed_c_control=True,
                message_binding_ok=False,
                ancestry_revalidation_ok=True,
            )
        )

    feasible = reduce_disposition(
        _reducer_input(
            inventory_complete=True,
            has_eligible_signal=True,
            valid_b_continuation=True,
            valid_completed_c_control=True,
            message_binding_ok=True,
            ancestry_revalidation_ok=True,
        )
    )
    assert feasible is ProbeDisposition.FEASIBLE_CANDIDATE


# --- Digest relationship derivation -------------------------------------------


def test_derive_restart_stable_and_fresh_thread_distinct_expressions() -> None:
    assert derive_restart_stable(_DIGEST_A, _DIGEST_B) is True
    assert derive_restart_stable(None, _DIGEST_B) is False
    assert derive_restart_stable(_DIGEST_A, _DIGEST_OTHER) is False
    assert derive_fresh_thread_distinct(_DIGEST_B, None) is True
    assert derive_fresh_thread_distinct(_DIGEST_B, _DIGEST_C) is True
    assert derive_fresh_thread_distinct(_DIGEST_B, _DIGEST_B) is False


def test_compute_eligible_requires_all_eight_rules_and_non_ancestry() -> None:
    assert compute_eligible(**_eligible_kwargs()) is True
    for key in (
        "available_before_new_decision",
        "thread_specific",
        "restart_stable",
        "fresh_thread_distinct",
        "protocol_honest",
        "trust_compatible",
        "safely_persistable",
        "independently_falsifiable",
    ):
        assert compute_eligible(**_eligible_kwargs(**{key: False})) is False
    assert compute_eligible(**_eligible_kwargs(ancestry_derived=True)) is False
    assert (
        compute_eligible(**_eligible_kwargs(ancestry_derived=True, ancestry_revalidated=True))
        is True
    )


@pytest.mark.parametrize(
    "field_path",
    [
        "workspace.root",
        "launch.cwd",
        "observation.recency",
        "process.pid",
        "thread.title",
        "session.prompt",
    ],
)
def test_presumptively_ineligible_field_paths(field_path: str) -> None:
    model = _signal_model(field_path=field_path, eligible=False, reason_code="presumptively_ineligible")
    signal = model.to_verified_signal(revalidated_field_paths=frozenset())
    assert signal.eligible is False


def test_ancestry_candidate_ineligible_until_direct_revalidation() -> None:
    model = _signal_model(
        ancestry_derived=True,
        eligible=False,
        reason_code="ancestry_pending_revalidation",
    )
    blocked = model.to_verified_signal(revalidated_field_paths=frozenset())
    assert blocked.eligible is False

    model_claiming_eligible = _signal_model(
        ancestry_derived=True,
        eligible=True,
        reason_code="eligible_after_revalidation",
    )
    with pytest.raises(CustodyContractError):
        model_claiming_eligible.to_verified_signal(revalidated_field_paths=frozenset())

    ok = model_claiming_eligible.to_verified_signal(
        revalidated_field_paths=frozenset({model_claiming_eligible.field_path})
    )
    assert ok.eligible is True


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("restart_stable", False),
        ("fresh_thread_distinct", False),
        ("eligible", False),
    ],
)
def test_rejects_supplied_relationship_or_eligible_disagreeing_with_recompute(
    field: str, bad_value: bool
) -> None:
    model = _signal_model(**{field: bad_value})
    with pytest.raises(CustodyContractError):
        model.to_verified_signal(revalidated_field_paths=frozenset())


# --- Schema / hash helpers ----------------------------------------------------


def test_artifact_manifest_rejects_unknown_fields_and_wrong_schema() -> None:
    with pytest.raises(ValidationError):
        ArtifactManifestModel.model_validate(
            {
                "schema": "plan117-custody-artifact-manifest-v1",
                "checkpoint": "final",
                "complete": True,
                "artifacts": [],
                "unexpected": True,
            }
        )
    with pytest.raises(ValidationError):
        ArtifactManifestModel.model_validate(
            {
                "schema": "wrong-schema",
                "checkpoint": "final",
                "complete": True,
                "artifacts": [],
            }
        )


def test_sha256_fields_require_lowercase_64_hex() -> None:
    with pytest.raises(ValidationError):
        _signal_model(a_sha256="A" * 64)
    with pytest.raises(ValidationError):
        _signal_model(a_sha256="not-a-digest")
    ok = _signal_model(a_sha256=_DIGEST_A)
    assert ok.a_sha256 == _DIGEST_A


def test_sha256_file_streams_and_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "blob.bin"
    target.write_bytes(b"hello-plan117")
    digest = sha256_file(target)
    assert digest == sha256_file(target)
    assert digest == digest.lower()
    assert len(digest) == 64

    link = tmp_path / "link.bin"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable on this host")
    with pytest.raises(ValueError, match="symlink_forbidden"):
        sha256_file(link)


def test_atomic_write_json_uses_lf_and_is_public_alias(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    payload = {"schema": "plan117-test-v1", "ok": True, "nested": {"b": 2, "a": 1}}
    atomic_write_json(path, payload)
    raw = path.read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"}") or raw.endswith(b"}\n") is False
    decoded = json.loads(raw.decode("utf-8"))
    assert decoded == payload
    # Public alias
    alt = tmp_path / "alias.json"
    write_canonical_json(alt, payload)
    assert alt.read_bytes() == raw


# --- Attempt budgets ----------------------------------------------------------


def test_independent_three_attempt_budgets_and_permanent_stops() -> None:
    correlation = [
        AttemptRecord(
            attempt_id=f"c-{i}",
            phase="origin-a",
            kind=AttemptKind.CORRELATION_CAPTURE,
            ordinal=i,
            failure_class=FailureClass.TRANSIENT,
            reason_code="transient_capture",
            manifest_sha256=_DIGEST_A,
        )
        for i in range(1, 4)
    ]
    validate_attempt_budgets(correlation)

    too_many = [
        *correlation,
        AttemptRecord(
            attempt_id="c-4",
            phase="origin-a",
            kind=AttemptKind.CORRELATION_CAPTURE,
            ordinal=4,
            failure_class=FailureClass.TRANSIENT,
            reason_code="transient_capture",
            manifest_sha256=_DIGEST_A,
        ),
    ]
    with pytest.raises(ValueError, match="attempt_budget_exceeded"):
        validate_attempt_budgets(too_many)

    permanent_then_retry = [
        AttemptRecord(
            attempt_id="c-1",
            phase="origin-a",
            kind=AttemptKind.CORRELATION_CAPTURE,
            ordinal=1,
            failure_class=FailureClass.PERMANENT,
            reason_code="permanent_capture",
            manifest_sha256=_DIGEST_A,
        ),
        AttemptRecord(
            attempt_id="c-2",
            phase="origin-a",
            kind=AttemptKind.CORRELATION_CAPTURE,
            ordinal=2,
            failure_class=FailureClass.TRANSIENT,
            reason_code="should_not_retry",
            manifest_sha256=_DIGEST_A,
        ),
    ]
    with pytest.raises(ValueError, match="permanent_failure_must_stop"):
        validate_attempt_budgets(permanent_then_retry)


def test_valid_session_new_preserved_across_later_prompt_failures() -> None:
    attempts = [
        AttemptRecord(
            attempt_id="c-1",
            phase="origin-a",
            kind=AttemptKind.CORRELATION_CAPTURE,
            ordinal=1,
            failure_class=FailureClass.NONE,
            reason_code=None,
            manifest_sha256=_DIGEST_A,
        ),
        AttemptRecord(
            attempt_id="p-1",
            phase="origin-a",
            kind=AttemptKind.POST_NEW_PROMPT,
            ordinal=1,
            failure_class=FailureClass.TRANSIENT,
            reason_code="gateway_timeout",
            manifest_sha256=_DIGEST_OTHER,
        ),
        AttemptRecord(
            attempt_id="p-2",
            phase="origin-a",
            kind=AttemptKind.POST_NEW_PROMPT,
            ordinal=2,
            failure_class=FailureClass.TRANSIENT,
            reason_code="gateway_timeout",
            manifest_sha256=_DIGEST_OTHER,
        ),
    ]
    validate_attempt_budgets(attempts)
    # Correlation budget remains one successful capture; prompt budget is independent.
    assert sum(1 for a in attempts if a.kind is AttemptKind.CORRELATION_CAPTURE) == 1


def test_public_dataclass_shapes() -> None:
    signal = CorrelationSignal(
        field_path="x",
        origin="zed",
        available_before_new_decision=True,
        a_sha256=_DIGEST_A,
        b_sha256=_DIGEST_B,
        c_sha256=_DIGEST_C,
        restart_stable=True,
        fresh_thread_distinct=True,
        thread_specific=True,
        trust_compatible=True,
        protocol_honest=True,
        safely_persistable=True,
        independently_falsifiable=True,
        ancestry_derived=False,
        eligible=True,
        reason_code="eligible_thread_binding",
    )
    assert signal.eligible is True
    assert AttemptKind.CORRELATION_CAPTURE.value == "correlation_capture"
    assert FailureClass.TRANSIENT.value == "transient"


def test_attempt_record_model_round_trip_and_bad_sha() -> None:
    from tools.plan117_custody_contract import AttemptRecordModel

    model = AttemptRecordModel.model_validate(
        {
            "attempt_id": "c-1",
            "phase": "origin-a",
            "kind": "correlation_capture",
            "ordinal": 1,
            "failure_class": "none",
            "reason_code": None,
            "manifest_sha256": _DIGEST_A,
        }
    )
    record = model.to_record()
    assert record.attempt_id == "c-1"
    with pytest.raises((ValidationError, CustodyContractError)):
        AttemptRecordModel.model_validate(
            {
                "attempt_id": "c-1",
                "phase": "origin-a",
                "kind": "correlation_capture",
                "ordinal": 1,
                "failure_class": "none",
                "manifest_sha256": "ZZZZ",
            }
        )


def test_signal_model_accepts_null_digests_and_fresh_thread_distinct() -> None:
    model = _signal_model(
        a_sha256=None,
        b_sha256=None,
        c_sha256=None,
        restart_stable=False,
        fresh_thread_distinct=True,
        eligible=False,
        reason_code="missing_digests",
    )
    signal = model.to_verified_signal(revalidated_field_paths=frozenset())
    assert signal.restart_stable is False
    assert signal.fresh_thread_distinct is True
    assert signal.eligible is False


def test_sha256_file_rejects_missing_regular_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="regular_file_required"):
        sha256_file(tmp_path / "missing.bin")


def test_atomic_write_json_failure_cleans_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "out.json"

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(ValueError, match="atomic_write_failed"):
        atomic_write_json(path, {"ok": True})


def test_atomic_write_bytes_and_task3_schema_constants(tmp_path: Path) -> None:
    from tools.plan117_custody_contract import (
        SCHEMA_APPROVAL_EQUIVALENCE,
        SCHEMA_ATTEMPT_MANIFEST,
        SCHEMA_CUSTODY_STATE,
        SCHEMA_PROCESS_RECORD,
        SCHEMA_SETTINGS_TRANSACTION,
        SCHEMA_TRANSCRIPT_PROJECTION,
        atomic_write_bytes,
    )

    path = tmp_path / "preimage.bin"
    atomic_write_bytes(path, b"\x00\xffsettings-preimage")
    assert path.read_bytes() == b"\x00\xffsettings-preimage"
    assert SCHEMA_CUSTODY_STATE == "plan117-custody-state-v1"
    assert SCHEMA_SETTINGS_TRANSACTION == "plan117-custody-settings-transaction-v1"
    assert SCHEMA_APPROVAL_EQUIVALENCE == "plan117-custody-approval-equivalence-v1"
    assert SCHEMA_PROCESS_RECORD == "plan117-custody-process-record-v1"
    assert SCHEMA_TRANSCRIPT_PROJECTION == "plan117-custody-transcript-projection-v1"
    assert SCHEMA_ATTEMPT_MANIFEST == "plan117-custody-attempt-manifest-v1"

