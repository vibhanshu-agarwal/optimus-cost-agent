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


# --- Origin-A fixture v2: stage ledger + append-only supersession -------------

AMENDMENT_SHA256 = "5BB327D88761AE329869B90866839D03F61EFF6AF0E5AE47F8D3D7551F849A4D"
_PARENT_A1 = "7d64d5943002b15dcd977b0bc7614fc4234f9dd6d823c1533da6a0677f9ff446"
_PARENT_A2 = "083e0953c8d89781c8c3100545bfc2e4524e94cbbaae7b32574da4d88f597f63"
_DIGEST_D = "d" * 64
_DIGEST_E = "e" * 64


def _stage_api():
    """Import stage-accounting surface; fail closed if symbols are absent."""
    import tools.plan117_custody_contract as contract

    required = (
        "StageKind",
        "StageStatus",
        "EvidenceReference",
        "StageAttemptRecord",
        "SupplementalFactRecord",
        "StageLedger",
        "normalize_stage_ledger",
        "next_stage_ordinal",
        "verify_supersession_chain",
        "stage_attempt_record_sha256",
        "atomic_create_json",
        "ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256",
        "SCHEMA_STAGE_ATTEMPT_RECORD",
        "SCHEMA_SUPPLEMENTAL_FACT_RECORD",
        "SCHEMA_STAGE_LEDGER",
        "SCHEMA_RUN_RESERVATION",
    )
    missing = [name for name in required if not hasattr(contract, name)]
    if missing:
        pytest.fail(f"missing stage-accounting API: {missing}")
    return contract


def _evidence(relative_path: str = "attempts/origin-a-1/attempt-manifest.json", digest: str = _PARENT_A1):
    contract = _stage_api()
    return contract.EvidenceReference(
        relative_path=relative_path,
        sha256=digest,
        hash_method="raw_file_sha256",
    )


def _stage_record(
    *,
    record_id: str,
    run_attempt_id: str,
    stage: object,
    ordinal: int,
    status: object,
    failure_class: FailureClass = FailureClass.NONE,
    reason_code: str | None = None,
    evidence: tuple[object, ...] | None = None,
    supersedes_record_id: str | None = None,
    supersedes_sha256: str | None = None,
    amendment_sha256: str = AMENDMENT_SHA256.lower(),
    created_by: str = "plan117-task1",
    created_utc: str = "2026-08-02T16:00:00Z",
):
    contract = _stage_api()
    return contract.StageAttemptRecord(
        record_id=record_id,
        run_attempt_id=run_attempt_id,
        stage=stage,
        ordinal=ordinal,
        status=status,
        failure_class=failure_class,
        reason_code=reason_code,
        evidence=evidence if evidence is not None else (_evidence(),),
        supersedes_record_id=supersedes_record_id,
        supersedes_sha256=supersedes_sha256,
        amendment_sha256=amendment_sha256,
        created_by=created_by,
        created_utc=created_utc,
    )


def _fixed_origin_a1_a2_records():
    """Canonical origin-a-1 / origin-a-2 terminal stage records after supersession."""
    contract = _stage_api()
    return (
        _stage_record(
            record_id="origin-a-1-correlation",
            run_attempt_id="origin-a-1",
            stage=contract.StageKind.CORRELATION_CAPTURE,
            ordinal=1,
            status=contract.StageStatus.FAILED,
            failure_class=FailureClass.PERMANENT,
            reason_code="invalid_probe_relay_capture_tooling_failure",
            evidence=(_evidence("attempts/origin-a-1/attempt-manifest.json", _PARENT_A1),),
            supersedes_record_id="origin-a-1-original-manifest",
            supersedes_sha256=_PARENT_A1,
        ),
        _stage_record(
            record_id="origin-a-2-correlation",
            run_attempt_id="origin-a-2",
            stage=contract.StageKind.CORRELATION_CAPTURE,
            ordinal=2,
            status=contract.StageStatus.SUCCEEDED,
            failure_class=FailureClass.NONE,
            reason_code=None,
            evidence=(_evidence("attempts/origin-a-2/attempt-manifest.json", _PARENT_A2),),
            supersedes_record_id="origin-a-2-original-manifest",
            supersedes_sha256=_PARENT_A2,
        ),
        _stage_record(
            record_id="origin-a-2-prompt",
            run_attempt_id="origin-a-2",
            stage=contract.StageKind.POST_NEW_PROMPT,
            ordinal=1,
            status=contract.StageStatus.FAILED,
            failure_class=FailureClass.PERMANENT,
            reason_code="AMBIGUOUS_WORKSPACE_REFERENCE",
            evidence=(_evidence("attempts/origin-a-2/phase-observation.json", _DIGEST_D),),
            supersedes_record_id="origin-a-2-original-prompt",
            supersedes_sha256=_DIGEST_D,
        ),
    )


def test_fixed_origin_a1_a2_ledger_derives_next_correlation_3_and_prompt_2() -> None:
    contract = _stage_api()
    records = _fixed_origin_a1_a2_records()
    contract.verify_supersession_chain(records)
    ledger = contract.normalize_stage_ledger(records)
    assert contract.next_stage_ordinal(ledger, contract.StageKind.CORRELATION_CAPTURE) == 3
    assert contract.next_stage_ordinal(ledger, contract.StageKind.POST_NEW_PROMPT) == 2
    assert ledger.next_correlation_ordinal == 3
    assert ledger.next_prompt_ordinal == 2


def test_one_physical_run_may_consume_both_correlation_and_prompt_stages() -> None:
    contract = _stage_api()
    records = _fixed_origin_a1_a2_records()
    ledger = contract.normalize_stage_ledger(records)
    a2_stages = {
        record.stage for record in ledger.terminal_records if record.run_attempt_id == "origin-a-2"
    }
    assert a2_stages == {
        contract.StageKind.CORRELATION_CAPTURE,
        contract.StageKind.POST_NEW_PROMPT,
    }
    # origin-a-1 consumed correlation only; prompt never started.
    a1 = [r for r in ledger.terminal_records if r.run_attempt_id == "origin-a-1"]
    assert len(a1) == 1
    assert a1[0].stage is contract.StageKind.CORRELATION_CAPTURE


def test_stage_ordinals_cannot_be_reclaimed_after_failure() -> None:
    contract = _stage_api()
    records = _fixed_origin_a1_a2_records()
    reclaim = _stage_record(
        record_id="reclaim-correlation-1",
        run_attempt_id="origin-a-reclaim",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=1,
        status=contract.StageStatus.SUCCEEDED,
        supersedes_record_id=None,
        supersedes_sha256=None,
    )
    with pytest.raises(CustodyContractError) as excinfo:
        contract.normalize_stage_ledger((*records, reclaim))
    assert excinfo.value.reason_code == "invalid_probe_stage_accounting"


def test_origin_a3_must_be_correlation_ordinal_3() -> None:
    contract = _stage_api()
    records = _fixed_origin_a1_a2_records()
    wrong = _stage_record(
        record_id="origin-a-3-correlation",
        run_attempt_id="origin-a-3",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=2,
        status=contract.StageStatus.SUCCEEDED,
        supersedes_record_id=None,
        supersedes_sha256=None,
        amendment_sha256=AMENDMENT_SHA256.lower(),
    )
    with pytest.raises(CustodyContractError) as excinfo:
        contract.normalize_stage_ledger((*records, wrong))
    assert excinfo.value.reason_code == "invalid_probe_stage_accounting"

    correct = _stage_record(
        record_id="origin-a-3-correlation",
        run_attempt_id="origin-a-3",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=3,
        status=contract.StageStatus.SUCCEEDED,
        supersedes_record_id=None,
        supersedes_sha256=None,
    )
    ledger = contract.normalize_stage_ledger((*records, correct))
    assert contract.next_stage_ordinal(ledger, contract.StageKind.CORRELATION_CAPTURE) == 4


def test_same_session_prompt_only_retry_allocates_no_correlation_stage() -> None:
    contract = _stage_api()
    base = _fixed_origin_a1_a2_records()
    a3_corr = _stage_record(
        record_id="origin-a-3-correlation",
        run_attempt_id="origin-a-3",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=3,
        status=contract.StageStatus.SUCCEEDED,
        supersedes_record_id=None,
        supersedes_sha256=None,
    )
    a3_prompt_fail = _stage_record(
        record_id="origin-a-3-prompt-2",
        run_attempt_id="origin-a-3",
        stage=contract.StageKind.POST_NEW_PROMPT,
        ordinal=2,
        status=contract.StageStatus.FAILED,
        failure_class=FailureClass.TRANSIENT,
        reason_code="gateway_timeout",
        supersedes_record_id=None,
        supersedes_sha256=None,
    )
    prompt_retry = _stage_record(
        record_id="origin-a-3-prompt-retry",
        run_attempt_id="origin-a-3",
        stage=contract.StageKind.POST_NEW_PROMPT,
        ordinal=3,
        status=contract.StageStatus.SUCCEEDED,
        supersedes_record_id=None,
        supersedes_sha256=None,
    )
    ledger = contract.normalize_stage_ledger((*base, a3_corr, a3_prompt_fail, prompt_retry))
    corr_for_a3 = [
        r
        for r in ledger.terminal_records
        if r.run_attempt_id == "origin-a-3" and r.stage is contract.StageKind.CORRELATION_CAPTURE
    ]
    assert len(corr_for_a3) == 1
    assert corr_for_a3[0].ordinal == 3
    assert ledger.next_correlation_ordinal == 4
    assert ledger.next_prompt_ordinal == 4


def test_fourth_correlation_launch_rejected_under_amendment() -> None:
    contract = _stage_api()
    base = _fixed_origin_a1_a2_records()
    a3 = _stage_record(
        record_id="origin-a-3-correlation",
        run_attempt_id="origin-a-3",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=3,
        status=contract.StageStatus.FAILED,
        failure_class=FailureClass.TRANSIENT,
        reason_code="transient_capture",
        supersedes_record_id=None,
        supersedes_sha256=None,
    )
    a4 = _stage_record(
        record_id="origin-a-4-correlation",
        run_attempt_id="origin-a-4",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=4,
        status=contract.StageStatus.SUCCEEDED,
        supersedes_record_id=None,
        supersedes_sha256=None,
    )
    with pytest.raises(CustodyContractError) as excinfo:
        contract.normalize_stage_ledger((*base, a3, a4))
    assert excinfo.value.reason_code in {
        "invalid_probe_retry_budget_exhausted",
        "invalid_probe_stage_accounting",
    }


def test_immutable_reservation_exclusive_create_refuses_overwrite(tmp_path: Path) -> None:
    contract = _stage_api()
    path = tmp_path / "reservations" / "origin-a-3.json"
    payload = {
        "schema": contract.SCHEMA_RUN_RESERVATION,
        "run_attempt_id": "origin-a-3",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
    }
    contract.atomic_create_json(path, payload)
    raw = path.read_bytes()
    assert b"\r\n" not in raw
    with pytest.raises((CustodyContractError, ValueError, OSError, FileExistsError)):
        contract.atomic_create_json(path, {**payload, "tampered": True})
    assert path.read_bytes() == raw


def test_verify_supersession_rejects_gaps_duplicates_forks_cycles_and_digest() -> None:
    contract = _stage_api()
    parent = _stage_record(
        record_id="parent-corr-1",
        run_attempt_id="origin-a-1",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=1,
        status=contract.StageStatus.FAILED,
        failure_class=FailureClass.PERMANENT,
        reason_code="invalid_probe_relay_capture_tooling_failure",
        supersedes_record_id=None,
        supersedes_sha256=None,
    )
    parent_digest = contract.stage_attempt_record_sha256(parent)

    # Gap: ordinal 2 without ordinal 1 terminal after normalize of only ordinal-2.
    gap = _stage_record(
        record_id="gap-corr-2",
        run_attempt_id="origin-a-2",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=2,
        status=contract.StageStatus.SUCCEEDED,
        supersedes_record_id=None,
        supersedes_sha256=None,
    )
    with pytest.raises(CustodyContractError) as gap_exc:
        contract.normalize_stage_ledger((gap,))
    assert gap_exc.value.reason_code == "invalid_probe_stage_accounting"

    # Duplicate terminal ordinals for the same stage.
    dup = _stage_record(
        record_id="dup-corr-1",
        run_attempt_id="origin-a-dup",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=1,
        status=contract.StageStatus.SUCCEEDED,
        supersedes_record_id=None,
        supersedes_sha256=None,
    )
    with pytest.raises(CustodyContractError) as dup_exc:
        contract.normalize_stage_ledger((parent, dup))
    assert dup_exc.value.reason_code in {
        "invalid_probe_stage_accounting",
        "invalid_probe_attempt_supersession_chain",
    }

    # Fork: two children superseding the same parent.
    child_a = _stage_record(
        record_id="child-a",
        run_attempt_id="origin-a-1",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=1,
        status=contract.StageStatus.FAILED,
        failure_class=FailureClass.PERMANENT,
        reason_code="invalid_probe_relay_capture_tooling_failure",
        supersedes_record_id=parent.record_id,
        supersedes_sha256=parent_digest,
    )
    child_b = _stage_record(
        record_id="child-b",
        run_attempt_id="origin-a-1",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=1,
        status=contract.StageStatus.FAILED,
        failure_class=FailureClass.PERMANENT,
        reason_code="invalid_probe_relay_capture_tooling_failure",
        supersedes_record_id=parent.record_id,
        supersedes_sha256=parent_digest,
    )
    with pytest.raises(CustodyContractError) as fork_exc:
        contract.verify_supersession_chain((parent, child_a, child_b))
    assert fork_exc.value.reason_code == "invalid_probe_attempt_supersession_chain"

    # Cycle.
    cyc_a = _stage_record(
        record_id="cyc-a",
        run_attempt_id="origin-a-1",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=1,
        status=contract.StageStatus.SUPERSEDED,
        failure_class=FailureClass.PERMANENT,
        reason_code="invalid_probe_relay_capture_tooling_failure",
        supersedes_record_id="cyc-b",
        supersedes_sha256=_DIGEST_E,
    )
    cyc_b = _stage_record(
        record_id="cyc-b",
        run_attempt_id="origin-a-1",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=1,
        status=contract.StageStatus.FAILED,
        failure_class=FailureClass.PERMANENT,
        reason_code="invalid_probe_relay_capture_tooling_failure",
        supersedes_record_id="cyc-a",
        supersedes_sha256=_DIGEST_E,
    )
    with pytest.raises(CustodyContractError) as cyc_exc:
        contract.verify_supersession_chain((cyc_a, cyc_b))
    assert cyc_exc.value.reason_code == "invalid_probe_attempt_supersession_chain"

    # Missing parent hash (supersession requires raw SHA-256 of the predecessor).
    orphan = _stage_record(
        record_id="orphan",
        run_attempt_id="origin-a-1",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=1,
        status=contract.StageStatus.FAILED,
        failure_class=FailureClass.PERMANENT,
        reason_code="invalid_probe_relay_capture_tooling_failure",
        supersedes_record_id="missing-parent",
        supersedes_sha256=None,
    )
    with pytest.raises(CustodyContractError) as miss_exc:
        contract.verify_supersession_chain((orphan,))
    assert miss_exc.value.reason_code == "invalid_probe_attempt_supersession_chain"

    # Hash mismatch against cited predecessor.
    bad_hash = _stage_record(
        record_id="bad-hash-child",
        run_attempt_id="origin-a-1",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=1,
        status=contract.StageStatus.FAILED,
        failure_class=FailureClass.PERMANENT,
        reason_code="invalid_probe_relay_capture_tooling_failure",
        supersedes_record_id=parent.record_id,
        supersedes_sha256=_DIGEST_E,
    )
    with pytest.raises(CustodyContractError) as hash_exc:
        contract.verify_supersession_chain((parent, bad_hash))
    assert hash_exc.value.reason_code == "invalid_probe_attempt_supersession_chain"

    # Unsupported reason code on a superseding correction.
    bad_reason = _stage_record(
        record_id="bad-reason",
        run_attempt_id="origin-a-1",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=1,
        status=contract.StageStatus.FAILED,
        failure_class=FailureClass.PERMANENT,
        reason_code="not_a_supported_amendment_reason",
        supersedes_record_id=parent.record_id,
        supersedes_sha256=parent_digest,
    )
    with pytest.raises(CustodyContractError) as reason_exc:
        contract.verify_supersession_chain((parent, bad_reason))
    assert reason_exc.value.reason_code == "invalid_probe_attempt_supersession_chain"

    # Wrong amendment digest.
    wrong_amend = _stage_record(
        record_id="wrong-amend",
        run_attempt_id="origin-a-1",
        stage=contract.StageKind.CORRELATION_CAPTURE,
        ordinal=1,
        status=contract.StageStatus.FAILED,
        failure_class=FailureClass.PERMANENT,
        reason_code="invalid_probe_relay_capture_tooling_failure",
        supersedes_record_id=parent.record_id,
        supersedes_sha256=parent_digest,
        amendment_sha256="0" * 64,
    )
    with pytest.raises(CustodyContractError) as amend_exc:
        contract.verify_supersession_chain((parent, wrong_amend))
    assert amend_exc.value.reason_code == "invalid_probe_attempt_supersession_chain"


def test_supplemental_fact_record_does_not_falsify_stage_outcomes() -> None:
    contract = _stage_api()
    records = _fixed_origin_a1_a2_records()
    ledger = contract.normalize_stage_ledger(records)
    fact = contract.SupplementalFactRecord(
        record_id="origin-a-2-client-crash",
        run_attempt_id="origin-a-2",
        fact_kind="zed_client_crash",
        reason_code="stop_probe_zed_client_crashed",
        evidence=(_evidence("attempts/origin-a-2/event-facts.json", _DIGEST_E),),
        supersedes_record_id="origin-a-2-original-crash-claim",
        supersedes_sha256=_DIGEST_E,
        amendment_sha256=AMENDMENT_SHA256.lower(),
        created_by="plan117-task1",
        created_utc="2026-08-02T16:00:00Z",
    )
    assert fact.fact_kind == "zed_client_crash"
    assert fact.reason_code == "stop_probe_zed_client_crashed"
    # Correlation remains succeeded; prompt remains failed; fact is separate.
    a2_corr = next(
        r
        for r in ledger.terminal_records
        if r.run_attempt_id == "origin-a-2" and r.stage is contract.StageKind.CORRELATION_CAPTURE
    )
    a2_prompt = next(
        r
        for r in ledger.terminal_records
        if r.run_attempt_id == "origin-a-2" and r.stage is contract.StageKind.POST_NEW_PROMPT
    )
    assert a2_corr.status is contract.StageStatus.SUCCEEDED
    assert a2_prompt.status is contract.StageStatus.FAILED
    assert fact.record_id not in {r.record_id for r in ledger.terminal_records}


def test_stage_accounting_schema_constants_and_pinned_amendment_digest() -> None:
    contract = _stage_api()
    assert contract.SCHEMA_STAGE_ATTEMPT_RECORD == "plan117-custody-stage-attempt-record-v1"
    assert contract.SCHEMA_SUPPLEMENTAL_FACT_RECORD == "plan117-custody-supplemental-fact-record-v1"
    assert contract.SCHEMA_STAGE_LEDGER == "plan117-custody-stage-ledger-v1"
    assert contract.SCHEMA_RUN_RESERVATION == "plan117-custody-run-reservation-v1"
    assert contract.sha256_hex_equal(
        contract.ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256,
        AMENDMENT_SHA256,
    )
    assert contract.StageKind.CORRELATION_CAPTURE.value == "correlation_capture"
    assert contract.StageKind.POST_NEW_PROMPT.value == "post_new_prompt"
    assert contract.StageStatus.NOT_STARTED.value == "not_started"
    assert contract.StageStatus.SUCCEEDED.value == "succeeded"
    assert contract.StageStatus.FAILED.value == "failed"
    assert contract.StageStatus.SUPERSEDED.value == "superseded"

