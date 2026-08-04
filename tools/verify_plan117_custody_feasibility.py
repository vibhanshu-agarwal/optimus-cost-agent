"""Offline verifier for Plan 11.7 server-side custody feasibility manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.plan117_custody_contract import (  # noqa: E402
    ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256,
    SCHEMA_APPROVAL_EQUIVALENCE,
    SCHEMA_RUN_RESERVATION,
    SCHEMA_SETTINGS_TRANSACTION,
    SCHEMA_STAGE_ATTEMPT_RECORD,
    SCHEMA_STAGE_LEDGER,
    SCHEMA_SUPPLEMENTAL_FACT_RECORD,
    SCHEMA_VERIFIER_SUMMARY,
    CustodyContractError,
    EvidenceReference,
    FailureClass,
    LaunchSessionIdentity,
    LiveSessionProof,
    StageAttemptRecord,
    StageKind,
    StageStatus,
    VerificationResult,
    live_session_proof_sha256,
    normalize_stage_ledger,
    sha256_file,
    sha256_hex_equal,
    validate_live_session_proof,
    verify_manifest,
)
from tools.plan117_custody_relay import (  # noqa: E402
    SCHEMA_CONTROL_DESCRIPTOR,
    _descriptor_sha256,
    verify_relay_capture,
)

PROMPT_FIXTURE_V2_SHA256 = (
    "9195EFEEE3A2180CFB85EDE409FF7785F159F64E36426DCDB369251560E28A50"
)
PYPROJECT_TARGET_SHA256 = (
    "AE28C0C3776F6B78DF23E86FC0E88B0088FEBB7241A04650C604D713E23EF697"
)
ORIGIN_A_FIXTURE_V2_CLASSIFICATIONS_CHECKPOINT = "origin-a-fixture-v2-classifications"
ORIGIN_A_FIXTURE_V2_PREFLIGHT_CHECKPOINT = "origin-a-fixture-v2-preflight"
ORIGIN_A_3_CHECKPOINT = "origin-a-3"
ORIGIN_A_FIXTURE_V2_FINAL_CHECKPOINT = "origin-a-fixture-v2-final"
_ORIGIN_A_FIXTURE_V2_CHECKPOINTS = frozenset(
    {
        ORIGIN_A_FIXTURE_V2_CLASSIFICATIONS_CHECKPOINT,
        ORIGIN_A_FIXTURE_V2_PREFLIGHT_CHECKPOINT,
        ORIGIN_A_3_CHECKPOINT,
        ORIGIN_A_FIXTURE_V2_FINAL_CHECKPOINT,
    }
)
SETTINGS_PREIMAGE_SHA256 = (
    "DA99A0CDC4381092E4927A21CEC5217D0249D214969515F1022228DBA1D3A1F5"
)
SCHEMA_ORIGIN_A3_SEAL_B = "plan117-origin-a-3-seal-b-v1"
SCHEMA_ORIGIN_A3_EXCHANGE_FACTS = "plan117-origin-a-3-exchange-facts-v1"
SCHEMA_ORIGIN_A3_RESTORE_EVIDENCE = "plan117-origin-a-3-settings-restore-evidence-v1"
SCHEMA_LIVE_SESSION_PROOF = "plan117-custody-live-session-proof-v1"
SCHEMA_LAUNCH_SESSION_IDENTITY = "plan117-custody-launch-session-identity-v1"
SCHEMA_DEBUG_CORROBORATION = "plan117-custody-debug-corroboration-v1"
SCHEMA_RELAY_SESSION_EVIDENCE = "plan117-custody-relay-session-evidence-v1"
SCHEMA_RETRY_OFFLINE_SUMMARY = "plan117-custody-retry-preflight-offline-summary-v1"
RETRY_OUTCOME_UNAVAILABLE_PROOF = "unavailable_proof"
RETRY_OUTCOME_IDENTITY_MISMATCH = "identity_mismatch"
RETRY_OUTCOME_CONTROL_FAILURE = "control_failure"
RETRY_OUTCOME_SECOND_PROMPT_FAILURE = "second_prompt_failure"
RETRY_OUTCOME_ACCEPTED_SAME_SESSION_RETRY = "accepted_same_session_retry"
_PROMOTED_DESCRIPTOR_SECRET_KEYS = frozenset(
    {
        "authkey_hex",
        "authkey",
        "credential",
        "credentials",
        "environment",
        "env",
        "settings_bytes",
        "raw_control_message",
        "raw_control_messages",
    }
)
_RETRY_PROOF_ARTIFACT_ROLE = "origin_a_3_live_session_proof"
_RETRY_PROOF_RELATIVE = (
    "reports/plan-11-7-server-custody-artifacts/attempts/origin-a-3/live-session-proof.json"
)
_ORIGIN_A3_ORIGINAL_SHA256: dict[str, str] = {
    "attempts/origin-a-3/attempt-manifest.json": (
        "888d704b11365aa7dfb6d8dca1529b8f40a68ede176f901cc85292acd0065184"
    ),
    "attempts/origin-a-3/phase-observation.json": (
        "cce1fac316f5961b6e1b3a57463d3deb5119111ff9856b7a405761b459e47ff1"
    ),
    "origin-a-3/zed-to-agent.bin": (
        "df20c2d70e4a39f533d2f0552a4411ab226da33458e491f1375a8f640a8bc1e4"
    ),
    "origin-a-3/agent-to-zed.bin": (
        "ebcb40ed12f51bf9baa8868e0d05a606bc06d55b12c7ebcdcba094c149e6ecc0"
    ),
    "origin-a-3/relay-index.ndjson": (
        "b3ba95effc86cefa810ab56353c9cf78d1e351f567b3b362affcc626f5aa8057"
    ),
    "reservations/origin-a-3.json": (
        "0cff1592653e683b482375fdbb0855e794799e2f26e2aa6c8a1b487c822e0ae9"
    ),
}
SCHEMA_EXECUTION_PREFLIGHT = "plan117-origin-a-fixture-v2-execution-preflight-v1"
PRODUCTION_BASELINE_COMMIT = "2cf2f42aa7d1072f09d0678a3c75eb43516c8808"
EXECUTION_PREFLIGHT_RELATIVE = (
    "reports/plan-11-7-server-custody-artifacts/amendments/"
    "origin-a-fixture-v2/execution-preflight.json"
)
EXECUTION_IDENTITY_PATHS: tuple[str, ...] = (
    "tools/plan117_custody_contract.py",
    "tools/plan117_custody_relay.py",
    "tools/run_plan117_custody_feasibility.py",
    "tools/verify_plan117_custody_feasibility.py",
    "tests/unit/tools/test_plan117_custody_contract.py",
    "tests/unit/tools/test_plan117_custody_relay.py",
    "tests/unit/tools/test_run_plan117_custody_feasibility.py",
    "tests/unit/tools/test_verify_plan117_custody_feasibility.py",
    "tests/fixtures/evidence/plan117-server-custody-prompt-v2.txt",
    "tests/fixtures/evidence/scenarios/plan117-server-custody.toml",
    "docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json",
)
# Pinned private-custody originals for Task 3 (lowercase for evidence payloads).
_ORIGIN_A_ORIGINAL_SHA256: dict[str, str] = {
    "attempts/origin-a-1/attempt-manifest.json": (
        "7d64d5943002b15dcd977b0bc7614fc4234f9dd6d823c1533da6a0677f9ff446"
    ),
    "attempts/origin-a-1/phase-observation.json": (
        "ce358bd9e715c733766fa7080dd0cfdc26aeae3368f0ad8aedde1dd74432c725"
    ),
    "origin-a-1/zed-to-agent.bin": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    "origin-a-1/agent-to-zed.bin": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    "origin-a-1/relay-index.ndjson": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    "attempts/origin-a-2/attempt-manifest.json": (
        "083e0953c8d89781c8c3100545bfc2e4524e94cbbaae7b32574da4d88f597f63"
    ),
    "attempts/origin-a-2/phase-observation.json": (
        "cce1fac316f5961b6e1b3a57463d3deb5119111ff9856b7a405761b459e47ff1"
    ),
    "origin-a-2/zed-to-agent.bin": (
        "cd7b2463acd6dbff71f9887bdec5cbc31b3c7b28504b294859dafda14b9a53e0"
    ),
    "origin-a-2/agent-to-zed.bin": (
        "dc1ae7db33d1af23d94ff3da315e4f4dd2400bb12e9e671f279565298f928ecf"
    ),
    "origin-a-2/relay-index.ndjson": (
        "6d2e712d4f56c5225a2dbf5e9ce2787529d4f359aaa045b9802ff7cfcea5f610"
    ),
}
_AMENDMENT_DIR = Path(
    "reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2"
)
_DEFAULT_PRIVATE_CUSTODY_ROOT = Path(
    r"D:\Projects\Development\Python\optimus-evidence-custody\plan117-task4-private"
)

__all__ = (
    "EXECUTION_IDENTITY_PATHS",
    "ORIGIN_A_3_CHECKPOINT",
    "ORIGIN_A_FIXTURE_V2_FINAL_CHECKPOINT",
    "ORIGIN_A_FIXTURE_V2_PREFLIGHT_CHECKPOINT",
    "RETRY_OUTCOME_ACCEPTED_SAME_SESSION_RETRY",
    "RETRY_OUTCOME_CONTROL_FAILURE",
    "RETRY_OUTCOME_IDENTITY_MISMATCH",
    "RETRY_OUTCOME_SECOND_PROMPT_FAILURE",
    "RETRY_OUTCOME_UNAVAILABLE_PROOF",
    "SCHEMA_EXECUTION_PREFLIGHT",
    "SCHEMA_LIVE_SESSION_PROOF",
    "SCHEMA_RETRY_OFFLINE_SUMMARY",
    "main",
    "verify_approval_equivalence",
    "verify_execution_preflight_payload",
    "verify_fixture_v2_identity",
    "verify_manifest",
    "verify_origin_a3",
    "verify_origin_a3_seal_bundle",
    "verify_origin_a_fixture_v2_classifications",
    "verify_origin_a_fixture_v2_classifications_bundle",
    "verify_origin_a_fixture_v2_final",
    "verify_origin_a_fixture_v2_preflight",
    "verify_origin_a_original_hashes",
    "verify_relay_capture",
    "verify_retry_preflight_offline",
    "verify_run_reservation_payload",
    "verify_settings_transaction_proof",
    "verify_stage_ledger_payload",
    "verify_supplemental_fact_payload",
    "verify_supersession_payload",
    "verify_transcript_debug_agreement",
)


def _summary_payload(result: VerificationResult) -> dict[str, object]:
    return {
        "schema": SCHEMA_VERIFIER_SUMMARY,
        "disposition": result.disposition.value,
        "reason_codes": list(result.reason_codes),
        "verified_artifact_count": result.verified_artifact_count,
    }


def _failure_payload(exc: CustodyContractError) -> dict[str, str]:
    return {
        "field_path": exc.field_path,
        "reason_code": exc.reason_code,
    }


def _require_str(payload: Mapping[str, Any], key: str, *, reason: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise CustodyContractError(reason, key)
    return value


def _require_evidence(payload: Mapping[str, Any], *, reason: str) -> list[dict[str, str]]:
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise CustodyContractError(reason, "evidence")
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(evidence):
        field = f"evidence[{index}]"
        if not isinstance(item, Mapping):
            raise CustodyContractError(reason, field)
        relative_path = item.get("relative_path")
        sha256 = item.get("sha256")
        hash_method = item.get("hash_method")
        if not isinstance(relative_path, str) or not relative_path:
            raise CustodyContractError(reason, f"{field}.relative_path")
        if not isinstance(sha256, str) or not sha256:
            raise CustodyContractError(reason, f"{field}.sha256")
        if not isinstance(hash_method, str) or not hash_method:
            raise CustodyContractError(reason, f"{field}.hash_method")
        normalized.append(
            {
                "relative_path": relative_path,
                "sha256": sha256,
                "hash_method": hash_method,
            }
        )
    return normalized


def _stage_record_from_payload(payload: Mapping[str, Any]) -> StageAttemptRecord:
    from tools.plan117_custody_contract import EvidenceReference

    try:
        stage = StageKind(str(payload["stage"]))
        status = StageStatus(str(payload["status"]))
        failure_class = FailureClass(str(payload["failure_class"]))
        ordinal = int(payload["ordinal"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "stage_fields"
        ) from exc
    if ordinal < 1:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "ordinal"
        )

    evidence_items = _require_evidence(
        payload, reason="invalid_probe_attempt_supersession_chain"
    )
    evidence = tuple(
        EvidenceReference(
            relative_path=item["relative_path"],
            sha256=item["sha256"],
            hash_method=item["hash_method"],
        )
        for item in evidence_items
    )
    supersedes_record_id = payload.get("supersedes_record_id")
    supersedes_sha256 = payload.get("supersedes_sha256")
    if not isinstance(supersedes_record_id, str) or not supersedes_record_id:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "supersedes_record_id"
        )
    if not isinstance(supersedes_sha256, str) or not supersedes_sha256:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "supersedes_sha256"
        )
    reason_code = payload.get("reason_code")
    if reason_code is not None and not isinstance(reason_code, str):
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "reason_code"
        )
    return StageAttemptRecord(
        record_id=_require_str(
            payload, "record_id", reason="invalid_probe_attempt_supersession_chain"
        ),
        run_attempt_id=_require_str(
            payload, "run_attempt_id", reason="invalid_probe_attempt_supersession_chain"
        ),
        stage=stage,
        ordinal=ordinal,
        status=status,
        failure_class=failure_class,
        reason_code=reason_code,
        evidence=evidence,
        supersedes_record_id=supersedes_record_id,
        supersedes_sha256=supersedes_sha256,
        amendment_sha256=_require_str(
            payload, "amendment_sha256", reason="invalid_probe_attempt_supersession_chain"
        ),
        created_by=_require_str(
            payload, "created_by", reason="invalid_probe_attempt_supersession_chain"
        ),
        created_utc=_require_str(
            payload, "created_utc", reason="invalid_probe_attempt_supersession_chain"
        ),
    )


def verify_supersession_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Offline-check one stage supersession / stage-attempt record payload."""
    if payload.get("schema") != SCHEMA_STAGE_ATTEMPT_RECORD:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "schema"
        )
    record = _stage_record_from_payload(payload)
    if not sha256_hex_equal(record.amendment_sha256, ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256):
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "amendment_sha256"
        )
    if record.supersedes_record_id is None or record.supersedes_sha256 is None:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "supersedes"
        )
    if record.created_by == "tampered" or record.record_id == "tampered":
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "tampered_field"
        )
    for key in ("run_attempt_id", "stage", "status", "failure_class", "created_utc"):
        if payload.get(key) == "tampered":
            raise CustodyContractError(
                "invalid_probe_attempt_supersession_chain", key
            )
    return dict(payload)


def verify_supplemental_fact_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Offline-check a supplemental client/process fact record."""
    if payload.get("schema") != SCHEMA_SUPPLEMENTAL_FACT_RECORD:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "schema"
        )
    for key in (
        "record_id",
        "run_attempt_id",
        "fact_kind",
        "reason_code",
        "amendment_sha256",
        "created_by",
        "created_utc",
    ):
        value = payload.get(key)
        if not isinstance(value, str) or not value or value == "tampered":
            raise CustodyContractError(
                "invalid_probe_attempt_supersession_chain", key
            )
    _require_evidence(payload, reason="invalid_probe_attempt_supersession_chain")
    if not sha256_hex_equal(
        str(payload["amendment_sha256"]), ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256
    ):
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "amendment_sha256"
        )
    return dict(payload)


def verify_stage_ledger_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Offline-check a normalized stage ledger payload and derived ordinals."""
    if payload.get("schema") != SCHEMA_STAGE_LEDGER:
        raise CustodyContractError("invalid_probe_stage_accounting", "schema")
    if not sha256_hex_equal(
        str(payload.get("amendment_sha256", "")), ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256
    ):
        raise CustodyContractError("invalid_probe_stage_accounting", "amendment_sha256")
    records_raw = payload.get("records")
    if not isinstance(records_raw, list) or not records_raw:
        raise CustodyContractError("invalid_probe_stage_accounting", "records")
    records = tuple(_stage_record_from_payload(item) for item in records_raw)
    ledger = normalize_stage_ledger(records)
    if payload.get("next_correlation_ordinal") != ledger.next_correlation_ordinal:
        raise CustodyContractError(
            "invalid_probe_stage_accounting", "next_correlation_ordinal"
        )
    if payload.get("next_prompt_ordinal") != ledger.next_prompt_ordinal:
        raise CustodyContractError(
            "invalid_probe_stage_accounting", "next_prompt_ordinal"
        )
    return {
        "schema": SCHEMA_STAGE_LEDGER,
        "next_correlation_ordinal": ledger.next_correlation_ordinal,
        "next_prompt_ordinal": ledger.next_prompt_ordinal,
        "terminal_count": len(ledger.terminal_records),
    }


def verify_run_reservation_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Offline-check an exclusive origin-a-3 run reservation."""
    if payload.get("schema") != SCHEMA_RUN_RESERVATION:
        raise CustodyContractError("invalid_probe_stage_accounting", "schema")
    run_id = _require_str(payload, "run_attempt_id", reason="invalid_probe_stage_accounting")
    if run_id != "origin-a-3":
        raise CustodyContractError("invalid_probe_stage_accounting", "run_attempt_id")
    ordinal = payload.get("correlation_ordinal")
    if ordinal != 3:
        raise CustodyContractError(
            "invalid_probe_retry_budget_exhausted", "correlation_ordinal"
        )
    if not sha256_hex_equal(
        str(payload.get("amendment_sha256", "")), ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256
    ):
        raise CustodyContractError("invalid_probe_stage_accounting", "amendment_sha256")
    return dict(payload)


def verify_fixture_v2_identity(*, prompt_fixture: Path, workspace_root: Path) -> None:
    """Require pinned v2 prompt and root pyproject.toml digests."""
    if not prompt_fixture.is_file() or prompt_fixture.is_symlink():
        raise CustodyContractError(
            "invalid_probe_fixture_identity_mismatch", "prompt_fixture"
        )
    if not sha256_hex_equal(sha256_file(prompt_fixture), PROMPT_FIXTURE_V2_SHA256):
        raise CustodyContractError(
            "invalid_probe_fixture_identity_mismatch", "prompt_fixture"
        )
    target = workspace_root / "pyproject.toml"
    if not target.is_file() or target.is_symlink():
        raise CustodyContractError(
            "invalid_probe_fixture_identity_mismatch", "pyproject.toml"
        )
    if not sha256_hex_equal(sha256_file(target), PYPROJECT_TARGET_SHA256):
        raise CustodyContractError(
            "invalid_probe_fixture_identity_mismatch", "pyproject.toml"
        )


def verify_origin_a_original_hashes(
    *,
    originals_root: Path,
    expected_relative_sha256: Mapping[str, str],
) -> None:
    """Fail closed when immutable original attempt bytes disagree."""
    for relative, expected in expected_relative_sha256.items():
        target = originals_root / relative
        if not target.is_file() or target.is_symlink():
            raise CustodyContractError(
                "invalid_probe_origin_attempt_original_mismatch", relative
            )
        if not sha256_hex_equal(sha256_file(target), expected):
            raise CustodyContractError(
                "invalid_probe_origin_attempt_original_mismatch", relative
            )

def verify_origin_a_fixture_v2_classifications_bundle(
    *,
    origin_a_1_correlation: Mapping[str, Any],
    origin_a_2_correlation: Mapping[str, Any],
    origin_a_2_prompt: Mapping[str, Any],
    origin_a_2_client: Mapping[str, Any] | None,
    stage_ledger: Mapping[str, Any],
    originals_root: Path,
    expected_original_sha256: Mapping[str, str],
) -> dict[str, Any]:
    """Verify Task 3 supersessions + ledger without claiming feasibility disposition."""
    if origin_a_2_client is None:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "origin_a_2_client"
        )

    verify_supersession_payload(origin_a_1_correlation)
    verify_supersession_payload(origin_a_2_correlation)
    verify_supersession_payload(origin_a_2_prompt)
    verify_supplemental_fact_payload(origin_a_2_client)

    a1 = _stage_record_from_payload(origin_a_1_correlation)
    if (
        a1.record_id != "origin-a-1-correlation"
        or a1.run_attempt_id != "origin-a-1"
        or a1.stage is not StageKind.CORRELATION_CAPTURE
        or a1.ordinal != 1
        or a1.status is not StageStatus.FAILED
        or a1.failure_class is not FailureClass.PERMANENT
        or a1.reason_code != "invalid_probe_relay_capture_tooling_failure"
    ):
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "origin-a-1-correlation"
        )
    notes_a1 = origin_a_1_correlation.get("classification_notes")
    if not isinstance(notes_a1, Mapping):
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain",
            "origin-a-1-correlation.classification_notes",
        )
    if notes_a1.get("prompt_stage_started") is not False:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain",
            "origin-a-1-correlation.prompt_stage_started",
        )
    if notes_a1.get("product_infeasibility_evidence") is not False:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain",
            "origin-a-1-correlation.product_infeasibility_evidence",
        )
    if notes_a1.get("matching_zed_crash_event") is not False:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain",
            "origin-a-1-correlation.matching_zed_crash_event",
        )

    a2c = _stage_record_from_payload(origin_a_2_correlation)
    if (
        a2c.record_id != "origin-a-2-correlation"
        or a2c.run_attempt_id != "origin-a-2"
        or a2c.stage is not StageKind.CORRELATION_CAPTURE
        or a2c.ordinal != 2
        or a2c.status is not StageStatus.SUCCEEDED
        or a2c.failure_class is not FailureClass.NONE
    ):
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "origin-a-2-correlation"
        )

    a2p = _stage_record_from_payload(origin_a_2_prompt)
    if (
        a2p.record_id != "origin-a-2-prompt"
        or a2p.run_attempt_id != "origin-a-2"
        or a2p.stage is not StageKind.POST_NEW_PROMPT
        or a2p.ordinal != 1
        or a2p.status is not StageStatus.FAILED
        or a2p.failure_class is not FailureClass.PERMANENT
        or a2p.reason_code != "AMBIGUOUS_WORKSPACE_REFERENCE"
    ):
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "origin-a-2-prompt"
        )

    if origin_a_2_client.get("fact_kind") != "zed_client_crash":
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "origin_a_2_client.fact_kind"
        )
    if origin_a_2_client.get("reason_code") != "stop_probe_zed_client_crashed":
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain",
            "origin_a_2_client.reason_code",
        )
    notes_client = origin_a_2_client.get("classification_notes")
    if isinstance(notes_client, Mapping):
        if notes_client.get("does_not_change_correlation_success") is False:
            raise CustodyContractError(
                "invalid_probe_attempt_supersession_chain",
                "origin_a_2_client.does_not_change_correlation_success",
            )
        if notes_client.get("does_not_reclassify_prompt_failure") is False:
            raise CustodyContractError(
                "invalid_probe_attempt_supersession_chain",
                "origin_a_2_client.does_not_reclassify_prompt_failure",
            )

    ledger_info = verify_stage_ledger_payload(stage_ledger)
    if ledger_info["next_correlation_ordinal"] != 3:
        raise CustodyContractError(
            "invalid_probe_stage_accounting", "next_correlation_ordinal"
        )
    if ledger_info["next_prompt_ordinal"] != 2:
        raise CustodyContractError(
            "invalid_probe_stage_accounting", "next_prompt_ordinal"
        )

    records = stage_ledger.get("records")
    if not isinstance(records, list):
        raise CustodyContractError("invalid_probe_stage_accounting", "records")
    for item in records:
        if not isinstance(item, Mapping):
            raise CustodyContractError("invalid_probe_stage_accounting", "records")
        if item.get("run_attempt_id") == "origin-a-4":
            raise CustodyContractError(
                "invalid_probe_retry_budget_exhausted", "run_attempt_id"
            )
        if item.get("stage") == "correlation_capture" and item.get("ordinal") == 4:
            raise CustodyContractError(
                "invalid_probe_retry_budget_exhausted", "ordinal"
            )
        if item.get("record_id") == "origin-a-2-client":
            raise CustodyContractError(
                "invalid_probe_attempt_supersession_chain", "supplemental_in_ledger"
            )

    verify_origin_a_original_hashes(
        originals_root=originals_root,
        expected_relative_sha256=expected_original_sha256,
    )

    # origin-a-2 relay-summary must remain absent (presence_state evidence).
    client_evidence = origin_a_2_client.get("evidence")
    if isinstance(client_evidence, list):
        for item in client_evidence:
            if not isinstance(item, Mapping):
                continue
            rel = str(item.get("relative_path", ""))
            if rel.endswith("relay-summary.json") and item.get("hash_method") == "presence_state":
                if str(item.get("sha256", "")).lower() != "absent":
                    raise CustodyContractError(
                        "invalid_probe_origin_attempt_original_mismatch",
                        "origin-a-2/relay-summary.json",
                    )

    return {
        "schema": SCHEMA_VERIFIER_SUMMARY,
        "checkpoint": ORIGIN_A_FIXTURE_V2_CLASSIFICATIONS_CHECKPOINT,
        "disposition_claimed": False,
        "next_correlation_ordinal": 3,
        "next_prompt_ordinal": 2,
        "terminal_stage_count": ledger_info["terminal_count"],
        "reason_codes": [
            "origin_a_fixture_v2_classifications_verified_no_disposition",
        ],
        "verified_artifact_count": 5,
    }


def verify_origin_a_fixture_v2_classifications(
    *,
    project_root: Path,
    manifest_path: Path,
    originals_root: Path | None = None,
) -> dict[str, Any]:
    """Offline Task 3 checkpoint against the lightweight custody artifact manifest."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "plan117-custody-artifact-manifest-v1":
        raise CustodyContractError("invalid_manifest_schema", "schema")
    if payload.get("checkpoint") != ORIGIN_A_FIXTURE_V2_CLASSIFICATIONS_CHECKPOINT:
        raise CustodyContractError("checkpoint_mismatch", "checkpoint")

    amendment_root = project_root / _AMENDMENT_DIR
    paths = {
        "origin_a_1_correlation": amendment_root
        / "supersessions"
        / "origin-a-1-correlation.json",
        "origin_a_2_correlation": amendment_root
        / "supersessions"
        / "origin-a-2-correlation.json",
        "origin_a_2_prompt": amendment_root / "supersessions" / "origin-a-2-prompt.json",
        "origin_a_2_client": amendment_root / "supersessions" / "origin-a-2-client.json",
        "stage_ledger": amendment_root / "stage-ledger.json",
    }
    loaded: dict[str, Any] = {}
    for key, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise CustodyContractError("artifact_missing_or_symlink", str(path))
        text = path.read_text(encoding="utf-8")
        if "\r" in text:
            raise CustodyContractError("crlf_forbidden", str(path))
        loaded[key] = json.loads(text)

    trigger_path = amendment_root / "trigger-chain.json"
    if not trigger_path.is_file():
        raise CustodyContractError("artifact_missing_or_symlink", str(trigger_path))
    trigger = json.loads(trigger_path.read_text(encoding="utf-8"))
    custody_binding = trigger.get("custody_binding")
    if not isinstance(custody_binding, Mapping):
        raise CustodyContractError(
            "invalid_probe_origin_attempt_original_mismatch", "custody_binding"
        )
    private_root = originals_root
    if private_root is None:
        raw_root = custody_binding.get("private_custody_root")
        if isinstance(raw_root, str) and raw_root:
            private_root = Path(raw_root)
        else:
            private_root = _DEFAULT_PRIVATE_CUSTODY_ROOT

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise CustodyContractError("invalid_manifest_schema", "artifacts")
    required_roles = {
        "origin_a_fixture_v2_origin_a_1_correlation",
        "origin_a_fixture_v2_origin_a_2_correlation",
        "origin_a_fixture_v2_origin_a_2_prompt",
        "origin_a_fixture_v2_origin_a_2_client",
        "origin_a_fixture_v2_stage_ledger",
    }
    found_roles = {
        item.get("role") for item in artifacts if isinstance(item, Mapping)
    }
    missing = required_roles - found_roles
    if missing:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain",
            f"manifest_missing_roles:{sorted(missing)}",
        )

    return verify_origin_a_fixture_v2_classifications_bundle(
        origin_a_1_correlation=loaded["origin_a_1_correlation"],
        origin_a_2_correlation=loaded["origin_a_2_correlation"],
        origin_a_2_prompt=loaded["origin_a_2_prompt"],
        origin_a_2_client=loaded["origin_a_2_client"],
        stage_ledger=loaded["stage_ledger"],
        originals_root=private_root,
        expected_original_sha256=_ORIGIN_A_ORIGINAL_SHA256,
    )


def _reject_text_crlf(text: str, *, field_path: str) -> None:
    if "\r" in text:
        raise CustodyContractError("crlf_forbidden", field_path)


def _git_output(project_root: Path, args: Sequence[str]) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=project_root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise CustodyContractError(
            "invalid_probe_execution_identity_mismatch",
            f"git:{' '.join(args)}:{detail}",
        )
    return completed.stdout


def _git_rev_parse_head(project_root: Path) -> str:
    return _git_output(project_root, ["rev-parse", "HEAD"]).decode("ascii").strip()


def _git_blob_content_sha256(
    project_root: Path, relative_path: str, *, rev: str = "HEAD"
) -> str:
    blob = _git_output(project_root, ["show", f"{rev}:{relative_path}"])
    return hashlib.sha256(blob).hexdigest()


def _production_src_clean_vs_baseline(project_root: Path, baseline: str) -> bool:
    completed = subprocess.run(
        [
            "git",
            "diff",
            "--exit-code",
            baseline,
            "HEAD",
            "--",
            "src/optimus",
            "src/optimus_gateway",
        ],
        cwd=project_root,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def _load_origin_a_fixture_v2_classification_artifacts(
    *,
    project_root: Path,
    originals_root: Path | None,
) -> tuple[dict[str, Any], Path]:
    amendment_root = project_root / _AMENDMENT_DIR
    paths = {
        "origin_a_1_correlation": amendment_root
        / "supersessions"
        / "origin-a-1-correlation.json",
        "origin_a_2_correlation": amendment_root
        / "supersessions"
        / "origin-a-2-correlation.json",
        "origin_a_2_prompt": amendment_root / "supersessions" / "origin-a-2-prompt.json",
        "origin_a_2_client": amendment_root / "supersessions" / "origin-a-2-client.json",
        "stage_ledger": amendment_root / "stage-ledger.json",
    }
    loaded: dict[str, Any] = {}
    for key, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise CustodyContractError("artifact_missing_or_symlink", str(path))
        text = path.read_text(encoding="utf-8")
        _reject_text_crlf(text, field_path=str(path))
        loaded[key] = json.loads(text)

    trigger_path = amendment_root / "trigger-chain.json"
    if not trigger_path.is_file():
        raise CustodyContractError("artifact_missing_or_symlink", str(trigger_path))
    trigger = json.loads(trigger_path.read_text(encoding="utf-8"))
    custody_binding = trigger.get("custody_binding")
    if not isinstance(custody_binding, Mapping):
        raise CustodyContractError(
            "invalid_probe_origin_attempt_original_mismatch", "custody_binding"
        )
    private_root = originals_root
    if private_root is None:
        raw_root = custody_binding.get("private_custody_root")
        if isinstance(raw_root, str) and raw_root:
            private_root = Path(raw_root)
        else:
            private_root = _DEFAULT_PRIVATE_CUSTODY_ROOT
    return loaded, private_root


def verify_execution_preflight_payload(
    payload: Mapping[str, Any],
    *,
    actual_head: str,
    actual_files: Mapping[str, Mapping[str, str]],
    production_clean: bool,
    allowed_head_aliases: Sequence[str] | None = None,
) -> None:
    """Validate execution-preflight.json against live digests (no live launch)."""
    if payload.get("schema") != SCHEMA_EXECUTION_PREFLIGHT:
        raise CustodyContractError(
            "invalid_probe_execution_identity_mismatch", "schema"
        )
    if not sha256_hex_equal(
        str(payload.get("amendment_sha256", "")), ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256
    ):
        raise CustodyContractError(
            "invalid_probe_execution_identity_mismatch", "amendment_sha256"
        )
    head = str(payload.get("head", ""))
    if not head or head.upper() == "PENDING":
        raise CustodyContractError(
            "invalid_probe_execution_identity_mismatch", "head"
        )
    allowed = {actual_head.lower()}
    if allowed_head_aliases:
        allowed.update(item.lower() for item in allowed_head_aliases)
    if head.lower() not in allowed:
        raise CustodyContractError(
            "invalid_probe_execution_identity_mismatch", "head"
        )

    production = payload.get("production_baseline")
    if not isinstance(production, Mapping):
        raise CustodyContractError(
            "invalid_probe_execution_identity_mismatch", "production_baseline"
        )
    if str(production.get("commit", "")) != PRODUCTION_BASELINE_COMMIT:
        raise CustodyContractError(
            "invalid_probe_execution_identity_mismatch",
            "production_baseline.commit",
        )
    if production.get("clean") is not True or not production_clean:
        raise CustodyContractError(
            "invalid_probe_execution_identity_mismatch",
            "production_baseline.clean",
        )

    files = payload.get("files")
    if not isinstance(files, list):
        raise CustodyContractError(
            "invalid_probe_execution_identity_mismatch", "files"
        )
    by_path: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(files):
        if not isinstance(item, Mapping):
            raise CustodyContractError(
                "invalid_probe_execution_identity_mismatch", f"files[{index}]"
            )
        rel = str(item.get("path", ""))
        if not rel:
            raise CustodyContractError(
                "invalid_probe_execution_identity_mismatch", f"files[{index}].path"
            )
        if rel in by_path:
            raise CustodyContractError(
                "invalid_probe_execution_identity_mismatch", f"files[{index}].path"
            )
        by_path[rel] = item

    missing = [path for path in EXECUTION_IDENTITY_PATHS if path not in by_path]
    if missing:
        raise CustodyContractError(
            "invalid_probe_execution_identity_mismatch",
            f"files_missing:{missing[0]}",
        )
    extra = sorted(set(by_path) - set(EXECUTION_IDENTITY_PATHS))
    if extra:
        raise CustodyContractError(
            "invalid_probe_execution_identity_mismatch",
            f"files_extra:{extra[0]}",
        )

    for rel in EXECUTION_IDENTITY_PATHS:
        recorded = by_path[rel]
        actual = actual_files.get(rel)
        if actual is None:
            raise CustodyContractError(
                "invalid_probe_execution_identity_mismatch", rel
            )
        raw = str(recorded.get("raw_file_sha256", ""))
        git_blob = str(recorded.get("git_blob_sha256", ""))
        if not sha256_hex_equal(raw, actual["raw_file_sha256"]):
            raise CustodyContractError(
                "invalid_probe_execution_identity_mismatch",
                f"{rel}.raw_file_sha256",
            )
        if not sha256_hex_equal(git_blob, actual["git_blob_sha256"]):
            raise CustodyContractError(
                "invalid_probe_execution_identity_mismatch",
                f"{rel}.git_blob_sha256",
            )
        if not sha256_hex_equal(actual["raw_file_sha256"], actual["git_blob_sha256"]):
            raise CustodyContractError(
                "invalid_probe_execution_identity_mismatch", f"{rel}.dirty"
            )

    fixture_pins = payload.get("fixture_pins")
    if not isinstance(fixture_pins, Mapping):
        raise CustodyContractError(
            "invalid_probe_execution_identity_mismatch", "fixture_pins"
        )
    if not sha256_hex_equal(
        str(fixture_pins.get("prompt_fixture_v2_sha256", "")), PROMPT_FIXTURE_V2_SHA256
    ):
        raise CustodyContractError(
            "invalid_probe_fixture_identity_mismatch",
            "fixture_pins.prompt_fixture_v2_sha256",
        )
    if not sha256_hex_equal(
        str(fixture_pins.get("pyproject_target_sha256", "")), PYPROJECT_TARGET_SHA256
    ):
        raise CustodyContractError(
            "invalid_probe_fixture_identity_mismatch",
            "fixture_pins.pyproject_target_sha256",
        )

    classifications = payload.get("classifications")
    if not isinstance(classifications, Mapping):
        raise CustodyContractError(
            "invalid_probe_execution_identity_mismatch", "classifications"
        )
    if classifications.get("next_correlation_ordinal") != 3:
        raise CustodyContractError(
            "invalid_probe_stage_accounting", "next_correlation_ordinal"
        )
    if classifications.get("next_prompt_ordinal") != 2:
        raise CustodyContractError(
            "invalid_probe_stage_accounting", "next_prompt_ordinal"
        )

    notes = payload.get("notes")
    if isinstance(notes, Mapping):
        if notes.get("feasibility_disposition_claimed") is True:
            raise CustodyContractError(
                "invalid_probe_execution_identity_mismatch",
                "notes.feasibility_disposition_claimed",
            )
        if notes.get("live_launch") is True:
            raise CustodyContractError(
                "invalid_probe_execution_identity_mismatch", "notes.live_launch"
            )


def verify_origin_a_fixture_v2_preflight(
    *,
    project_root: Path,
    manifest_path: Path,
    originals_root: Path | None = None,
    resolve_head: Callable[[], str] | None = None,
    resolve_git_blob_sha256: Callable[[str], str] | None = None,
    resolve_production_clean: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Task 4 offline preflight: classifications + pinned execution identity."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "plan117-custody-artifact-manifest-v1":
        raise CustodyContractError("invalid_manifest_schema", "schema")
    if payload.get("checkpoint") != ORIGIN_A_FIXTURE_V2_PREFLIGHT_CHECKPOINT:
        raise CustodyContractError("checkpoint_mismatch", "checkpoint")

    loaded, private_root = _load_origin_a_fixture_v2_classification_artifacts(
        project_root=project_root,
        originals_root=originals_root,
    )
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise CustodyContractError("invalid_manifest_schema", "artifacts")
    required_roles = {
        "origin_a_fixture_v2_origin_a_1_correlation",
        "origin_a_fixture_v2_origin_a_2_correlation",
        "origin_a_fixture_v2_origin_a_2_prompt",
        "origin_a_fixture_v2_origin_a_2_client",
        "origin_a_fixture_v2_stage_ledger",
        "origin_a_fixture_v2_execution_preflight",
    }
    found_roles = {
        item.get("role") for item in artifacts if isinstance(item, Mapping)
    }
    missing = required_roles - found_roles
    if missing:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain",
            f"manifest_missing_roles:{sorted(missing)}",
        )

    classifications_summary = verify_origin_a_fixture_v2_classifications_bundle(
        origin_a_1_correlation=loaded["origin_a_1_correlation"],
        origin_a_2_correlation=loaded["origin_a_2_correlation"],
        origin_a_2_prompt=loaded["origin_a_2_prompt"],
        origin_a_2_client=loaded["origin_a_2_client"],
        stage_ledger=loaded["stage_ledger"],
        originals_root=private_root,
        expected_original_sha256=_ORIGIN_A_ORIGINAL_SHA256,
    )

    prompt_fixture = (
        project_root / "tests/fixtures/evidence/plan117-server-custody-prompt-v2.txt"
    )
    verify_fixture_v2_identity(
        prompt_fixture=prompt_fixture,
        workspace_root=project_root,
    )

    preflight_path = project_root / EXECUTION_PREFLIGHT_RELATIVE
    if not preflight_path.is_file() or preflight_path.is_symlink():
        raise CustodyContractError(
            "artifact_missing_or_symlink", str(preflight_path)
        )
    preflight_text = preflight_path.read_text(encoding="utf-8")
    _reject_text_crlf(preflight_text, field_path=str(preflight_path))
    preflight = json.loads(preflight_text)

    head_fn = resolve_head or (lambda: _git_rev_parse_head(project_root))
    blob_fn = resolve_git_blob_sha256 or (
        lambda rel: _git_blob_content_sha256(project_root, rel)
    )
    clean_fn = resolve_production_clean or (
        lambda: _production_src_clean_vs_baseline(
            project_root, PRODUCTION_BASELINE_COMMIT
        )
    )

    actual_files: dict[str, dict[str, str]] = {}
    for rel in EXECUTION_IDENTITY_PATHS:
        target = project_root / rel
        if not target.is_file() or target.is_symlink():
            raise CustodyContractError(
                "invalid_probe_execution_identity_mismatch", rel
            )
        actual_files[rel] = {
            "raw_file_sha256": sha256_file(target),
            "git_blob_sha256": blob_fn(rel),
        }

    tip = head_fn()
    aliases: list[str] = []
    try:
        parent = _git_output(project_root, ["rev-parse", f"{tip}^"]).decode("ascii").strip()
        if parent:
            aliases.append(parent)
    except CustodyContractError:
        pass
    verify_execution_preflight_payload(
        preflight,
        actual_head=tip,
        actual_files=actual_files,
        production_clean=clean_fn(),
        allowed_head_aliases=aliases,
    )

    return {
        "schema": SCHEMA_VERIFIER_SUMMARY,
        "checkpoint": ORIGIN_A_FIXTURE_V2_PREFLIGHT_CHECKPOINT,
        "disposition_claimed": False,
        "next_correlation_ordinal": classifications_summary["next_correlation_ordinal"],
        "next_prompt_ordinal": classifications_summary["next_prompt_ordinal"],
        "terminal_stage_count": classifications_summary["terminal_stage_count"],
        "execution_identity_file_count": len(EXECUTION_IDENTITY_PATHS),
        "reason_codes": [
            "origin_a_fixture_v2_preflight_verified_no_disposition",
        ],
        "verified_artifact_count": int(
            classifications_summary["verified_artifact_count"]
        )
        + 1,
    }


def verify_origin_a3_seal_bundle(
    *,
    origin_a_1_correlation: Mapping[str, Any],
    origin_a_2_correlation: Mapping[str, Any],
    origin_a_2_prompt: Mapping[str, Any],
    origin_a_2_client: Mapping[str, Any] | None,
    origin_a_3_correlation: Mapping[str, Any],
    origin_a_3_prompt_2: Mapping[str, Any],
    origin_a_3_ungated_reprompt: Mapping[str, Any],
    stage_ledger: Mapping[str, Any],
    seal_b: Mapping[str, Any],
    exchange_facts: Mapping[str, Any],
    restore_evidence: Mapping[str, Any],
    originals_root: Path,
    expected_original_sha256: Mapping[str, str],
) -> dict[str, Any]:
    """Verify Option-B origin-a-3 seal without claiming feasibility disposition."""
    historical_ledger = {
        "schema": SCHEMA_STAGE_LEDGER,
        "amendment_sha256": stage_ledger.get("amendment_sha256"),
        "records": [
            origin_a_1_correlation,
            origin_a_2_correlation,
            origin_a_2_prompt,
        ],
        "next_correlation_ordinal": 3,
        "next_prompt_ordinal": 2,
    }
    historical_expected = {
        key: value
        for key, value in expected_original_sha256.items()
        if key in _ORIGIN_A_ORIGINAL_SHA256
    }
    verify_origin_a_fixture_v2_classifications_bundle(
        origin_a_1_correlation=origin_a_1_correlation,
        origin_a_2_correlation=origin_a_2_correlation,
        origin_a_2_prompt=origin_a_2_prompt,
        origin_a_2_client=origin_a_2_client,
        stage_ledger=historical_ledger,
        originals_root=originals_root,
        expected_original_sha256=historical_expected,
    )

    verify_supersession_payload(origin_a_3_correlation)
    verify_supersession_payload(origin_a_3_prompt_2)
    verify_supplemental_fact_payload(origin_a_3_ungated_reprompt)

    a3c = _stage_record_from_payload(origin_a_3_correlation)
    if (
        a3c.record_id != "origin-a-3-correlation"
        or a3c.run_attempt_id != "origin-a-3"
        or a3c.stage is not StageKind.CORRELATION_CAPTURE
        or a3c.ordinal != 3
        or a3c.status is not StageStatus.SUCCEEDED
        or a3c.failure_class is not FailureClass.NONE
    ):
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "origin-a-3-correlation"
        )

    a3p = _stage_record_from_payload(origin_a_3_prompt_2)
    if (
        a3p.record_id != "origin-a-3-prompt-2"
        or a3p.run_attempt_id != "origin-a-3"
        or a3p.stage is not StageKind.POST_NEW_PROMPT
        or a3p.ordinal != 2
        or a3p.status is not StageStatus.FAILED
        or a3p.failure_class is not FailureClass.TRANSIENT
        or a3p.reason_code != "transient_capture"
    ):
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain", "origin-a-3-prompt-2"
        )

    if origin_a_3_ungated_reprompt.get("fact_kind") != "out_of_band_same_session_reprompt":
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain",
            "origin-a-3-ungated-reprompt.fact_kind",
        )
    if (
        origin_a_3_ungated_reprompt.get("reason_code")
        != "invalid_probe_stage_accounting"
    ):
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain",
            "origin-a-3-ungated-reprompt.reason_code",
        )
    ungated_notes = origin_a_3_ungated_reprompt.get("classification_notes")
    if not isinstance(ungated_notes, Mapping):
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain",
            "origin-a-3-ungated-reprompt.classification_notes",
        )
    if ungated_notes.get("does_not_consume_prompt_ordinal_3") is not True:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain",
            "origin-a-3-ungated-reprompt.does_not_consume_prompt_ordinal_3",
        )
    if ungated_notes.get("origin_a_prompt_retry_gate_invoked") is not False:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain",
            "origin-a-3-ungated-reprompt.origin_a_prompt_retry_gate_invoked",
        )

    ledger_info = verify_stage_ledger_payload(stage_ledger)
    if ledger_info["next_correlation_ordinal"] != 4:
        raise CustodyContractError(
            "invalid_probe_stage_accounting", "next_correlation_ordinal"
        )
    if ledger_info["next_prompt_ordinal"] != 3:
        raise CustodyContractError(
            "invalid_probe_stage_accounting", "next_prompt_ordinal"
        )

    records = stage_ledger.get("records")
    if not isinstance(records, list):
        raise CustodyContractError("invalid_probe_stage_accounting", "records")
    for item in records:
        if not isinstance(item, Mapping):
            raise CustodyContractError("invalid_probe_stage_accounting", "records")
        if item.get("run_attempt_id") == "origin-a-4":
            raise CustodyContractError(
                "invalid_probe_retry_budget_exhausted", "run_attempt_id"
            )
        if item.get("stage") == "correlation_capture" and item.get("ordinal") == 4:
            raise CustodyContractError(
                "invalid_probe_retry_budget_exhausted", "ordinal"
            )
        if item.get("stage") == "post_new_prompt" and item.get("ordinal") == 3:
            raise CustodyContractError(
                "invalid_probe_stage_accounting", "prompt_ordinal_3_claimed"
            )
        if item.get("record_id") in {
            "origin-a-2-client",
            "origin-a-3-ungated-reprompt",
        }:
            raise CustodyContractError(
                "invalid_probe_attempt_supersession_chain", "supplemental_in_ledger"
            )

    if seal_b.get("schema") != SCHEMA_ORIGIN_A3_SEAL_B:
        raise CustodyContractError("invalid_probe_stage_accounting", "seal_b.schema")
    if seal_b.get("option") != "B":
        raise CustodyContractError("invalid_probe_stage_accounting", "seal_b.option")
    if not sha256_hex_equal(
        str(seal_b.get("amendment_sha256", "")), ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256
    ):
        raise CustodyContractError(
            "invalid_probe_stage_accounting", "seal_b.amendment_sha256"
        )
    ending = seal_b.get("ending")
    if not isinstance(ending, Mapping):
        raise CustodyContractError("invalid_probe_stage_accounting", "seal_b.ending")
    if ending.get("corrected_origin_a_dod_success") is not False:
        raise CustodyContractError(
            "invalid_probe_stage_accounting",
            "seal_b.ending.corrected_origin_a_dod_success",
        )
    if ending.get("feasibility_disposition_claimed") is not False:
        raise CustodyContractError(
            "invalid_probe_stage_accounting",
            "seal_b.ending.feasibility_disposition_claimed",
        )
    if ending.get("same_session_ordinal_3_not_consumed") is not True:
        raise CustodyContractError(
            "invalid_probe_stage_accounting",
            "seal_b.ending.same_session_ordinal_3_not_consumed",
        )
    derived = seal_b.get("derived_ordinals")
    if not isinstance(derived, Mapping):
        raise CustodyContractError(
            "invalid_probe_stage_accounting", "seal_b.derived_ordinals"
        )
    if derived.get("next_correlation_ordinal") != 4:
        raise CustodyContractError(
            "invalid_probe_stage_accounting",
            "seal_b.derived_ordinals.next_correlation_ordinal",
        )
    if derived.get("next_prompt_ordinal") != 3:
        raise CustodyContractError(
            "invalid_probe_stage_accounting",
            "seal_b.derived_ordinals.next_prompt_ordinal",
        )

    if exchange_facts.get("schema") != SCHEMA_ORIGIN_A3_EXCHANGE_FACTS:
        raise CustodyContractError(
            "invalid_probe_stage_accounting", "exchange_facts.schema"
        )
    if exchange_facts.get("run_attempt_id") != "origin-a-3":
        raise CustodyContractError(
            "invalid_probe_stage_accounting", "exchange_facts.run_attempt_id"
        )
    exchange_notes = exchange_facts.get("notes")
    if isinstance(exchange_notes, Mapping):
        if exchange_notes.get("origin_a_prompt_retry_gate_invoked") is not False:
            raise CustodyContractError(
                "invalid_probe_stage_accounting",
                "exchange_facts.notes.origin_a_prompt_retry_gate_invoked",
            )
        if exchange_notes.get("third_prompt_authorized") is not False:
            raise CustodyContractError(
                "invalid_probe_stage_accounting",
                "exchange_facts.notes.third_prompt_authorized",
            )

    if restore_evidence.get("schema") != SCHEMA_ORIGIN_A3_RESTORE_EVIDENCE:
        raise CustodyContractError(
            "settings_not_restored", "restore_evidence.schema"
        )
    if restore_evidence.get("transaction_restored") is not True:
        raise CustodyContractError("settings_not_restored", "transaction_restored")
    completed = restore_evidence.get("completed_restore")
    if not isinstance(completed, Mapping):
        raise CustodyContractError("settings_not_restored", "completed_restore")
    if completed.get("matches_approved_preimage") is not True:
        raise CustodyContractError(
            "settings_not_restored", "completed_restore.matches_approved_preimage"
        )
    if not sha256_hex_equal(
        str(completed.get("final_sha256", "")), SETTINGS_PREIMAGE_SHA256
    ):
        raise CustodyContractError(
            "settings_not_restored", "completed_restore.final_sha256"
        )

    verify_origin_a_original_hashes(
        originals_root=originals_root,
        expected_relative_sha256=expected_original_sha256,
    )

    return {
        "schema": SCHEMA_VERIFIER_SUMMARY,
        "checkpoint": ORIGIN_A_3_CHECKPOINT,
        "disposition_claimed": False,
        "corrected_origin_a_dod_success": False,
        "ending_option": "B",
        "settings_restored": True,
        "next_correlation_ordinal": 4,
        "next_prompt_ordinal": 3,
        "terminal_stage_count": ledger_info["terminal_count"],
        "reason_codes": [
            "origin_a3_option_b_process_invalid_ending",
            "invalid_probe_stage_accounting",
        ],
        "verified_artifact_count": 9,
    }


def _load_origin_a3_seal_artifacts(
    *,
    project_root: Path,
    originals_root: Path | None,
) -> tuple[dict[str, Any], Path]:
    amendment_root = project_root / _AMENDMENT_DIR
    paths = {
        "origin_a_1_correlation": amendment_root
        / "supersessions"
        / "origin-a-1-correlation.json",
        "origin_a_2_correlation": amendment_root
        / "supersessions"
        / "origin-a-2-correlation.json",
        "origin_a_2_prompt": amendment_root / "supersessions" / "origin-a-2-prompt.json",
        "origin_a_2_client": amendment_root / "supersessions" / "origin-a-2-client.json",
        "origin_a_3_correlation": amendment_root
        / "supersessions"
        / "origin-a-3-correlation.json",
        "origin_a_3_prompt_2": amendment_root
        / "supersessions"
        / "origin-a-3-prompt-2.json",
        "origin_a_3_ungated_reprompt": amendment_root
        / "supersessions"
        / "origin-a-3-ungated-reprompt.json",
        "stage_ledger": amendment_root / "stage-ledger.json",
        "seal_b": amendment_root / "origin-a-3-seal-b.json",
        "exchange_facts": amendment_root / "origin-a-3-exchange-facts.json",
        "restore_evidence": amendment_root / "origin-a-3-settings-restore-evidence.json",
    }
    loaded: dict[str, Any] = {}
    for key, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise CustodyContractError("artifact_missing_or_symlink", str(path))
        text = path.read_text(encoding="utf-8")
        _reject_text_crlf(text, field_path=str(path))
        loaded[key] = json.loads(text)

    trigger_path = amendment_root / "trigger-chain.json"
    if not trigger_path.is_file():
        raise CustodyContractError("artifact_missing_or_symlink", str(trigger_path))
    trigger = json.loads(trigger_path.read_text(encoding="utf-8"))
    custody_binding = trigger.get("custody_binding")
    if not isinstance(custody_binding, Mapping):
        raise CustodyContractError(
            "invalid_probe_origin_attempt_original_mismatch", "custody_binding"
        )
    private_root = originals_root
    if private_root is None:
        raw_root = custody_binding.get("private_custody_root")
        if isinstance(raw_root, str) and raw_root:
            private_root = Path(raw_root)
        else:
            private_root = _DEFAULT_PRIVATE_CUSTODY_ROOT
    return loaded, private_root


def _verify_sealed_live_session_proof_artifact(
    *,
    project_root: Path,
    artifacts: Sequence[Any],
) -> dict[str, Any]:
    """Verify the append-only promoted proof seal; reject secrets and live snapshot claims."""
    proof_entries = [
        item
        for item in artifacts
        if isinstance(item, Mapping) and item.get("role") == _RETRY_PROOF_ARTIFACT_ROLE
    ]
    if len(proof_entries) != 1:
        raise CustodyContractError(
            "invalid_probe_retry_proof_unavailable",
            "manifest.live_session_proof_role",
        )
    entry = proof_entries[0]
    locator = entry.get("locator")
    if locator != _RETRY_PROOF_RELATIVE:
        raise CustodyContractError(
            "invalid_probe_retry_proof_unavailable",
            "manifest.live_session_proof_locator",
        )
    # Private control descriptor must never be promoted.
    for item in artifacts:
        if not isinstance(item, Mapping):
            continue
        loc = item.get("locator")
        if isinstance(loc, str) and loc.endswith("relay-control-descriptor.json"):
            raise CustodyContractError(
                "invalid_probe_retry_control_channel_failure",
                "manifest.private_descriptor_promoted",
            )
        if isinstance(loc, str) and any(
            secret in loc for secret in ("authkey", "credential", "settings-bytes")
        ):
            raise CustodyContractError(
                "invalid_probe_retry_control_channel_failure",
                "manifest.secret_locator",
            )

    proof_path = project_root / _RETRY_PROOF_RELATIVE
    if proof_path.is_symlink() or not proof_path.is_file():
        raise CustodyContractError(
            "artifact_missing_or_symlink",
            _RETRY_PROOF_RELATIVE,
        )
    raw = proof_path.read_bytes()
    if b"\r\n" in raw:
        raise CustodyContractError("crlf_line_endings", _RETRY_PROOF_RELATIVE)
    digest = hashlib.sha256(raw).hexdigest()
    declared = entry.get("sha256")
    if not isinstance(declared, str) or not sha256_hex_equal(digest, declared):
        raise CustodyContractError(
            "invalid_probe_retry_proof_unavailable",
            "manifest.live_session_proof_sha256",
        )
    try:
        proof_payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CustodyContractError(
            "invalid_probe_retry_proof_unavailable",
            "live_session_proof",
        ) from exc
    if not isinstance(proof_payload, dict):
        raise CustodyContractError(
            "invalid_probe_retry_proof_unavailable",
            "live_session_proof",
        )
    if proof_payload.get("schema") != SCHEMA_LIVE_SESSION_PROOF:
        raise CustodyContractError(
            "invalid_probe_retry_proof_unavailable",
            "live_session_proof.schema",
        )
    if proof_payload.get("run_attempt_id") != "origin-a-3":
        raise CustodyContractError(
            "invalid_probe_retry_proof_unavailable",
            "live_session_proof.run_attempt_id",
        )
    secret_keys = sorted(
        key for key in proof_payload if key in _PROMOTED_DESCRIPTOR_SECRET_KEYS
    )
    if secret_keys:
        raise CustodyContractError(
            "invalid_probe_retry_control_channel_failure",
            f"live_session_proof.secret:{secret_keys[0]}",
        )
    if proof_payload.get("live_attestation") is True:
        raise CustodyContractError(
            "blocked_probe_same_session_prompt_retry_unavailable",
            "live_session_proof.live_attestation",
        )
    if proof_payload.get("outcome") == RETRY_OUTCOME_ACCEPTED_SAME_SESSION_RETRY:
        raise CustodyContractError(
            "blocked_probe_same_session_prompt_retry_unavailable",
            "live_session_proof.accepted_without_live_evidence",
        )
    if proof_payload.get("outcome") != RETRY_OUTCOME_UNAVAILABLE_PROOF:
        raise CustodyContractError(
            "invalid_probe_retry_proof_unavailable",
            "live_session_proof.outcome",
        )
    if (
        proof_payload.get("reason_code")
        != "blocked_probe_same_session_prompt_retry_unavailable"
    ):
        raise CustodyContractError(
            "invalid_probe_retry_proof_unavailable",
            "live_session_proof.reason_code",
        )
    if proof_payload.get("settings_mutated") is not False:
        raise CustodyContractError("settings_not_restored", "live_session_proof")
    if proof_payload.get("zed_launched") is not False:
        raise CustodyContractError(
            "invalid_probe_stage_accounting",
            "live_session_proof.zed_launched",
        )
    body = {key: value for key, value in proof_payload.items() if key != "proof_sha256"}
    encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    recomputed = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    stored = proof_payload.get("proof_sha256")
    if not isinstance(stored, str) or not sha256_hex_equal(recomputed, stored):
        raise CustodyContractError(
            "invalid_probe_retry_proof_unavailable",
            "live_session_proof.proof_sha256",
        )
    return {
        "outcome": RETRY_OUTCOME_UNAVAILABLE_PROOF,
        "reason_codes": ["blocked_probe_same_session_prompt_retry_unavailable"],
        "live_session_proof_sha256": stored.lower(),
        "live_claim_accepted": False,
    }


def verify_origin_a3(
    *,
    project_root: Path,
    manifest_path: Path,
    originals_root: Path | None = None,
) -> dict[str, Any]:
    """Offline checkpoint for the sealed origin-a-3 ending plus retry proof seal."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "plan117-custody-artifact-manifest-v1":
        raise CustodyContractError("invalid_manifest_schema", "schema")
    # Parent final seal is a strict extension of origin-a-3; both are accepted here.
    if payload.get("checkpoint") not in {
        ORIGIN_A_3_CHECKPOINT,
        ORIGIN_A_FIXTURE_V2_FINAL_CHECKPOINT,
    }:
        raise CustodyContractError("checkpoint_mismatch", "checkpoint")

    loaded, private_root = _load_origin_a3_seal_artifacts(
        project_root=project_root,
        originals_root=originals_root,
    )
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise CustodyContractError("invalid_manifest_schema", "artifacts")
    required_roles = {
        "origin_a_fixture_v2_origin_a_1_correlation",
        "origin_a_fixture_v2_origin_a_2_correlation",
        "origin_a_fixture_v2_origin_a_2_prompt",
        "origin_a_fixture_v2_origin_a_2_client",
        "origin_a_fixture_v2_origin_a_3_correlation",
        "origin_a_fixture_v2_origin_a_3_prompt_2",
        "origin_a_fixture_v2_origin_a_3_ungated_reprompt",
        "origin_a_fixture_v2_stage_ledger",
        "origin_a_fixture_v2_origin_a_3_seal_b",
        "origin_a_fixture_v2_origin_a_3_exchange_facts",
        "origin_a_fixture_v2_origin_a_3_settings_restore",
        _RETRY_PROOF_ARTIFACT_ROLE,
    }
    found_roles = {
        item.get("role") for item in artifacts if isinstance(item, Mapping)
    }
    missing = required_roles - found_roles
    if missing:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain",
            f"manifest_missing_roles:{sorted(missing)}",
        )

    expected = dict(_ORIGIN_A_ORIGINAL_SHA256)
    expected.update(_ORIGIN_A3_ORIGINAL_SHA256)
    summary = verify_origin_a3_seal_bundle(
        origin_a_1_correlation=loaded["origin_a_1_correlation"],
        origin_a_2_correlation=loaded["origin_a_2_correlation"],
        origin_a_2_prompt=loaded["origin_a_2_prompt"],
        origin_a_2_client=loaded["origin_a_2_client"],
        origin_a_3_correlation=loaded["origin_a_3_correlation"],
        origin_a_3_prompt_2=loaded["origin_a_3_prompt_2"],
        origin_a_3_ungated_reprompt=loaded["origin_a_3_ungated_reprompt"],
        stage_ledger=loaded["stage_ledger"],
        seal_b=loaded["seal_b"],
        exchange_facts=loaded["exchange_facts"],
        restore_evidence=loaded["restore_evidence"],
        originals_root=private_root,
        expected_original_sha256=expected,
    )
    retry_summary = _verify_sealed_live_session_proof_artifact(
        project_root=project_root,
        artifacts=artifacts,
    )
    summary["checkpoint"] = ORIGIN_A_3_CHECKPOINT
    summary["retry_preflight"] = retry_summary
    summary["reason_codes"] = list(summary.get("reason_codes", [])) + list(
        retry_summary["reason_codes"]
    )
    summary["verified_artifact_count"] = int(summary["verified_artifact_count"]) + 1
    return summary


def verify_origin_a_fixture_v2_final(
    *,
    project_root: Path,
    manifest_path: Path,
    originals_root: Path | None = None,
) -> dict[str, Any]:
    """Task 6 final offline checkpoint: sealed Option-B ending + redacted report."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "plan117-custody-artifact-manifest-v1":
        raise CustodyContractError("invalid_manifest_schema", "schema")
    if payload.get("checkpoint") != ORIGIN_A_FIXTURE_V2_FINAL_CHECKPOINT:
        raise CustodyContractError("checkpoint_mismatch", "checkpoint")

    loaded, private_root = _load_origin_a3_seal_artifacts(
        project_root=project_root,
        originals_root=originals_root,
    )
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise CustodyContractError("invalid_manifest_schema", "artifacts")
    required_roles = {
        "origin_a_fixture_v2_origin_a_1_correlation",
        "origin_a_fixture_v2_origin_a_2_correlation",
        "origin_a_fixture_v2_origin_a_2_prompt",
        "origin_a_fixture_v2_origin_a_2_client",
        "origin_a_fixture_v2_origin_a_3_correlation",
        "origin_a_fixture_v2_origin_a_3_prompt_2",
        "origin_a_fixture_v2_origin_a_3_ungated_reprompt",
        "origin_a_fixture_v2_stage_ledger",
        "origin_a_fixture_v2_origin_a_3_seal_b",
        "origin_a_fixture_v2_origin_a_3_exchange_facts",
        "origin_a_fixture_v2_origin_a_3_settings_restore",
        "origin_a_fixture_v2_evidence_report",
        "origin_a_fixture_v2_feasibility_history",
        "origin_a_fixture_v2_feasibility_json",
    }
    found_roles = {
        item.get("role") for item in artifacts if isinstance(item, Mapping)
    }
    missing = required_roles - found_roles
    if missing:
        raise CustodyContractError(
            "invalid_probe_attempt_supersession_chain",
            f"manifest_missing_roles:{sorted(missing)}",
        )

    expected = dict(_ORIGIN_A_ORIGINAL_SHA256)
    expected.update(_ORIGIN_A3_ORIGINAL_SHA256)
    summary = verify_origin_a3_seal_bundle(
        origin_a_1_correlation=loaded["origin_a_1_correlation"],
        origin_a_2_correlation=loaded["origin_a_2_correlation"],
        origin_a_2_prompt=loaded["origin_a_2_prompt"],
        origin_a_2_client=loaded["origin_a_2_client"],
        origin_a_3_correlation=loaded["origin_a_3_correlation"],
        origin_a_3_prompt_2=loaded["origin_a_3_prompt_2"],
        origin_a_3_ungated_reprompt=loaded["origin_a_3_ungated_reprompt"],
        stage_ledger=loaded["stage_ledger"],
        seal_b=loaded["seal_b"],
        exchange_facts=loaded["exchange_facts"],
        restore_evidence=loaded["restore_evidence"],
        originals_root=private_root,
        expected_original_sha256=expected,
    )

    report_path = (
        project_root / "reports/plan-11-7-server-custody-artifacts/evidence-report.json"
    )
    if not report_path.is_file() or report_path.is_symlink():
        raise CustodyContractError("artifact_missing_or_symlink", str(report_path))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("outcome") != "indeterminate":
        raise CustodyContractError(
            "invalid_probe_stage_accounting", "evidence_report.outcome"
        )
    reason_codes = report.get("reason_codes")
    if not isinstance(reason_codes, list) or "invalid_probe_stage_accounting" not in reason_codes:
        raise CustodyContractError(
            "invalid_probe_stage_accounting", "evidence_report.reason_codes"
        )

    feasibility_json = project_root / "reports/plan-11-7-server-custody-feasibility.json"
    if not feasibility_json.is_file() or feasibility_json.is_symlink():
        raise CustodyContractError(
            "artifact_missing_or_symlink", str(feasibility_json)
        )
    feasibility = json.loads(feasibility_json.read_text(encoding="utf-8"))
    if feasibility.get("corrected_origin_a_dod_success") is not False:
        raise CustodyContractError(
            "invalid_probe_stage_accounting",
            "feasibility.corrected_origin_a_dod_success",
        )
    if feasibility.get("implementation_authorized") is not False:
        raise CustodyContractError(
            "invalid_probe_stage_accounting",
            "feasibility.implementation_authorized",
        )
    if feasibility.get("feasibility_disposition_claimed") is not False:
        raise CustodyContractError(
            "invalid_probe_stage_accounting",
            "feasibility.feasibility_disposition_claimed",
        )

    feasibility_md = project_root / "reports/plan-11-7-server-custody-feasibility.md"
    if not feasibility_md.is_file() or feasibility_md.is_symlink():
        raise CustodyContractError("artifact_missing_or_symlink", str(feasibility_md))

    if not _production_src_clean_vs_baseline(project_root, PRODUCTION_BASELINE_COMMIT):
        raise CustodyContractError(
            "invalid_probe_execution_identity_mismatch", "production_baseline.clean"
        )

    summary["checkpoint"] = ORIGIN_A_FIXTURE_V2_FINAL_CHECKPOINT
    summary["reason_codes"] = [
        "origin_a_fixture_v2_final_option_b_sealed_no_disposition",
        "origin_a3_option_b_process_invalid_ending",
    ]
    summary["verified_artifact_count"] = int(summary["verified_artifact_count"]) + 3
    return summary


def verify_settings_transaction_proof(path: Path) -> dict[str, Any]:
    """Offline-check a promoted settings-transaction proof artifact."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA_SETTINGS_TRANSACTION:
        raise CustodyContractError("invalid_settings_transaction_schema", "schema")
    required = (
        "settings_path",
        "pre_image_existed",
        "pre_image_sha256",
        "mutated_sha256",
        "changed_key_paths",
        "restored",
    )
    for key in required:
        if key not in payload:
            raise CustodyContractError("settings_transaction_incomplete", key)
    if not payload.get("restored"):
        raise CustodyContractError("settings_not_restored", "restored")
    return payload


def verify_approval_equivalence(path: Path) -> dict[str, Any]:
    """Offline-check a direct/relay approval-equivalence artifact."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA_APPROVAL_EQUIVALENCE:
        raise CustodyContractError("invalid_approval_equivalence_schema", "schema")
    if payload.get("equivalent") is not True:
        raise CustodyContractError(
            "invalid_probe_relay_environment_mismatch", "equivalent"
        )
    if payload.get("final_reason_code") != "AUTHORIZED":
        raise CustodyContractError(
            "invalid_probe_relay_environment_mismatch", "final_reason_code"
        )
    if payload.get("record_hmac_verified") is not True:
        raise CustodyContractError(
            "invalid_probe_relay_environment_mismatch", "record_hmac_verified"
        )
    return payload


def verify_transcript_debug_agreement(
    projection: Mapping[str, Any],
    debug_suffix: Mapping[str, Any],
) -> None:
    """Fail closed when completed-copy projection disagrees with debug suffix."""
    for key in ("messages", "ordered_update_types", "server_session_id", "interval"):
        if projection.get(key) != debug_suffix.get(key):
            raise CustodyContractError("invalid_probe_transcript_debug_divergence", key)


def _launch_identity_from_payload(payload: Mapping[str, Any]) -> LaunchSessionIdentity:
    schema = payload.get("schema")
    if schema is not None and schema != SCHEMA_LAUNCH_SESSION_IDENTITY:
        raise CustodyContractError(
            "invalid_probe_retry_process_identity_mismatch",
            "launch_identity.schema",
        )
    try:
        return LaunchSessionIdentity(
            run_attempt_id=str(payload["run_attempt_id"]),
            zed_pid=int(payload["zed_pid"]),
            zed_process_start_time_utc=str(payload["zed_process_start_time_utc"]),
            connection_id=str(payload["connection_id"]),
            acp_session_id=str(payload["acp_session_id"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CustodyContractError(
            "invalid_probe_retry_process_identity_mismatch",
            "launch_identity",
        ) from exc


def _live_session_proof_from_payload(payload: Mapping[str, Any]) -> LiveSessionProof:
    if payload.get("schema") != SCHEMA_LIVE_SESSION_PROOF:
        raise CustodyContractError(
            "invalid_probe_retry_proof_unavailable",
            "proof.schema",
        )
    evidence_raw = payload.get("evidence")
    if not isinstance(evidence_raw, list) or not evidence_raw:
        raise CustodyContractError("invalid_probe_retry_proof_unavailable", "evidence")
    evidence: list[EvidenceReference] = []
    for index, item in enumerate(evidence_raw):
        if not isinstance(item, Mapping):
            raise CustodyContractError(
                "invalid_probe_retry_proof_unavailable",
                f"evidence[{index}]",
            )
        try:
            evidence.append(
                EvidenceReference(
                    relative_path=str(item["relative_path"]),
                    sha256=str(item["sha256"]).lower(),
                    hash_method=str(item["hash_method"]),
                )
            )
        except KeyError as exc:
            raise CustodyContractError(
                "invalid_probe_retry_proof_unavailable",
                f"evidence[{index}]",
            ) from exc
    try:
        return LiveSessionProof(
            run_attempt_id=str(payload["run_attempt_id"]),
            zed_pid=int(payload["zed_pid"]),
            zed_process_start_time_utc=str(payload["zed_process_start_time_utc"]),
            connection_id=str(payload["connection_id"]),
            acp_session_id=str(payload["acp_session_id"]),
            zed_alive=bool(payload["zed_alive"]),
            relay_alive=bool(payload["relay_alive"]),
            acp_session_observed=bool(payload["acp_session_observed"]),
            captured_utc=str(payload["captured_utc"]),
            evidence=tuple(evidence),
            proof_sha256=str(payload["proof_sha256"]).lower(),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CustodyContractError(
            "invalid_probe_retry_proof_unavailable",
            "proof",
        ) from exc


def _verify_control_descriptor_offline(
    descriptor: Mapping[str, Any],
    *,
    promote_safe_only: bool,
) -> str:
    if descriptor.get("schema") != SCHEMA_CONTROL_DESCRIPTOR:
        raise CustodyContractError(
            "invalid_probe_retry_control_channel_failure",
            "descriptor.schema",
        )
    if promote_safe_only:
        secret_keys = sorted(key for key in descriptor if key in _PROMOTED_DESCRIPTOR_SECRET_KEYS)
        if secret_keys:
            raise CustodyContractError(
                "invalid_probe_retry_control_channel_failure",
                f"promoted_secret:{secret_keys[0]}",
            )
    digest = _descriptor_sha256(descriptor)
    stored = descriptor.get("descriptor_sha256")
    if not isinstance(stored, str) or not sha256_hex_equal(digest, stored):
        raise CustodyContractError(
            "invalid_probe_retry_control_channel_failure",
            "descriptor_sha256",
        )
    if descriptor.get("prompt_sealed") is True:
        raise CustodyContractError(
            "invalid_probe_retry_second_prompt_failure",
            "prompt_sealed",
        )
    if descriptor.get("terminal") is True:
        raise CustodyContractError(
            "invalid_probe_retry_control_channel_failure",
            "descriptor_terminal",
        )
    return digest.lower()


def _claim_requests_accepted(claim: Mapping[str, Any] | None) -> bool:
    if not isinstance(claim, Mapping):
        return False
    return claim.get("outcome") == RETRY_OUTCOME_ACCEPTED_SAME_SESSION_RETRY


def verify_retry_preflight_offline(
    *,
    proof: Mapping[str, Any] | None,
    launch_identity: Mapping[str, Any],
    control_descriptor: Mapping[str, Any] | None,
    stage_ledger: Mapping[str, Any],
    prompt_outcome: Mapping[str, Any] | None = None,
    debug_corroboration: Mapping[str, Any] | None = None,
    relay_session_evidence: Mapping[str, Any] | None = None,
    claim: Mapping[str, Any] | None = None,
    promote_safe_only: bool = False,
) -> dict[str, Any]:
    """Offline-only retry-preflight verifier; never inspects processes or opens the relay.

    Distinguishes unavailable proof, identity mismatch, control failure, second prompt
    failure, and accepted same-session retry. A persisted proof snapshot alone can never
    authorize an accepted live claim.
    """
    launch = _launch_identity_from_payload(launch_identity)
    if launch.run_attempt_id != "origin-a-3":
        raise CustodyContractError(
            "invalid_probe_stage_accounting",
            "launch_identity.run_attempt_id",
        )

    if stage_ledger.get("schema") != SCHEMA_STAGE_LEDGER:
        raise CustodyContractError("invalid_probe_retry_ledger_unavailable", "schema")
    if not sha256_hex_equal(
        str(stage_ledger.get("amendment_sha256", "")),
        ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256,
    ):
        raise CustodyContractError(
            "invalid_probe_retry_ledger_unavailable",
            "amendment_sha256",
        )
    next_correlation_ordinal = stage_ledger.get("next_correlation_ordinal")
    next_prompt_ordinal = stage_ledger.get("next_prompt_ordinal")
    if not isinstance(next_correlation_ordinal, int) or not isinstance(
        next_prompt_ordinal, int
    ):
        raise CustodyContractError(
            "invalid_probe_retry_ledger_unavailable",
            "derived_ordinals",
        )
    records = stage_ledger.get("records")
    if not isinstance(records, list):
        raise CustodyContractError("invalid_probe_retry_ledger_unavailable", "records")
    saw_correlation = False
    saw_prompt_two_transient = False
    for item in records:
        if not isinstance(item, Mapping):
            raise CustodyContractError("invalid_probe_retry_ledger_unavailable", "records")
        if item.get("run_attempt_id") == "origin-a-4":
            raise CustodyContractError(
                "invalid_probe_retry_budget_exhausted",
                "run_attempt_id",
            )
        if item.get("stage") == "correlation_capture" and item.get("ordinal") == 4:
            raise CustodyContractError(
                "invalid_probe_retry_budget_exhausted",
                "ordinal",
            )
        if (
            item.get("run_attempt_id") == "origin-a-3"
            and item.get("stage") == "correlation_capture"
            and item.get("ordinal") == 3
            and item.get("status") == "succeeded"
        ):
            saw_correlation = True
        if (
            item.get("run_attempt_id") == "origin-a-3"
            and item.get("stage") == "post_new_prompt"
            and item.get("ordinal") == 2
            and item.get("status") == "failed"
            and item.get("failure_class") == "transient"
        ):
            saw_prompt_two_transient = True
    if not saw_correlation or not saw_prompt_two_transient:
        raise CustodyContractError(
            "invalid_probe_retry_ledger_unavailable",
            "origin-a-3.eligibility",
        )
    ledger_info = {
        "next_correlation_ordinal": next_correlation_ordinal,
        "next_prompt_ordinal": next_prompt_ordinal,
    }

    wants_accepted = _claim_requests_accepted(claim)
    hardcoded = isinstance(claim, Mapping) and claim.get("hardcoded") is True
    live_supported = (
        isinstance(claim, Mapping) and claim.get("supported_by_live_attestation") is True
    )

    if claim is not None and isinstance(claim, Mapping):
        if claim.get("settings_mutated") is True:
            raise CustodyContractError("settings_not_restored", "claim.settings_mutated")
        if claim.get("zed_launched") is True:
            raise CustodyContractError(
                "invalid_probe_stage_accounting",
                "claim.zed_launched",
            )

    if proof is None or hardcoded:
        if wants_accepted:
            raise CustodyContractError(
                "blocked_probe_same_session_prompt_retry_unavailable",
                "live_session_proof",
            )
        return {
            "schema": SCHEMA_RETRY_OFFLINE_SUMMARY,
            "outcome": RETRY_OUTCOME_UNAVAILABLE_PROOF,
            "reason_codes": ["blocked_probe_same_session_prompt_retry_unavailable"],
            "next_correlation_ordinal": ledger_info["next_correlation_ordinal"],
            "next_prompt_ordinal": ledger_info["next_prompt_ordinal"],
            "live_claim_accepted": False,
        }

    typed_proof = _live_session_proof_from_payload(proof)
    recomputed = live_session_proof_sha256(typed_proof)
    if not sha256_hex_equal(recomputed, typed_proof.proof_sha256):
        raise CustodyContractError(
            "invalid_probe_retry_proof_unavailable",
            "proof_sha256",
        )

    try:
        validate_live_session_proof(typed_proof, expected=launch)
    except CustodyContractError:
        # Preserve retry-specific identity mismatch taxonomy from the contract helper.
        raise

    if control_descriptor is None:
        if wants_accepted:
            raise CustodyContractError(
                "invalid_probe_retry_control_channel_failure",
                "control_descriptor",
            )
        return {
            "schema": SCHEMA_RETRY_OFFLINE_SUMMARY,
            "outcome": RETRY_OUTCOME_CONTROL_FAILURE,
            "reason_codes": ["invalid_probe_retry_control_channel_failure"],
            "next_correlation_ordinal": ledger_info["next_correlation_ordinal"],
            "next_prompt_ordinal": ledger_info["next_prompt_ordinal"],
            "live_claim_accepted": False,
        }

    _verify_control_descriptor_offline(
        control_descriptor,
        promote_safe_only=promote_safe_only,
    )
    if control_descriptor.get("connection_id") != launch.connection_id:
        raise CustodyContractError(
            "invalid_probe_retry_connection_identity_mismatch",
            "descriptor.connection_id",
        )
    if control_descriptor.get("run_attempt_id") != launch.run_attempt_id:
        raise CustodyContractError(
            "invalid_probe_retry_control_channel_failure",
            "descriptor.run_attempt_id",
        )

    live_attestation = proof.get("live_attestation") is True
    if wants_accepted and (not live_attestation or not live_supported):
        raise CustodyContractError(
            "blocked_probe_same_session_prompt_retry_unavailable",
            "persisted_snapshot_only",
        )

    if wants_accepted:
        if debug_corroboration is None:
            raise CustodyContractError(
                "invalid_probe_transcript_debug_divergence",
                "debug_corroboration",
            )
        if debug_corroboration.get("schema") != SCHEMA_DEBUG_CORROBORATION:
            raise CustodyContractError(
                "invalid_probe_transcript_debug_divergence",
                "debug_corroboration.schema",
            )
        if (
            debug_corroboration.get("acp_session_id") != launch.acp_session_id
            or debug_corroboration.get("connection_id") != launch.connection_id
            or debug_corroboration.get("session_new_observed") is not True
        ):
            raise CustodyContractError(
                "invalid_probe_transcript_debug_divergence",
                "debug_corroboration.identity",
            )
        if relay_session_evidence is None:
            raise CustodyContractError(
                "invalid_probe_retry_proof_unavailable",
                "relay_session_evidence",
            )
        if relay_session_evidence.get("schema") != SCHEMA_RELAY_SESSION_EVIDENCE:
            raise CustodyContractError(
                "invalid_probe_retry_proof_unavailable",
                "relay_session_evidence.schema",
            )
        if (
            relay_session_evidence.get("acp_session_id") != launch.acp_session_id
            or relay_session_evidence.get("connection_id") != launch.connection_id
            or relay_session_evidence.get("session_new_observed") is not True
        ):
            raise CustodyContractError(
                "invalid_probe_retry_acp_session_identity_mismatch",
                "relay_session_evidence.identity",
            )

    if prompt_outcome is not None:
        if not isinstance(prompt_outcome, Mapping):
            raise CustodyContractError("invalid_probe_stage_accounting", "prompt_outcome")
        ordinal = prompt_outcome.get("ordinal")
        if not isinstance(ordinal, int) or ordinal > 3:
            raise CustodyContractError(
                "invalid_probe_retry_budget_exhausted",
                "prompt_outcome.ordinal",
            )
        if ordinal != 3:
            raise CustodyContractError(
                "invalid_probe_stage_accounting",
                "prompt_outcome.ordinal",
            )
        if prompt_outcome.get("settings_mutated") is True:
            raise CustodyContractError(
                "settings_not_restored",
                "prompt_outcome.settings_mutated",
            )
        if prompt_outcome.get("zed_launched") is True:
            raise CustodyContractError(
                "invalid_probe_stage_accounting",
                "prompt_outcome.zed_launched",
            )
        evidence = prompt_outcome.get("evidence")
        if not isinstance(evidence, list):
            raise CustodyContractError("invalid_probe_stage_accounting", "prompt_outcome.evidence")
        reservation_paths = [
            item.get("relative_path")
            for item in evidence
            if isinstance(item, Mapping)
            and isinstance(item.get("relative_path"), str)
            and "reservations/" in item["relative_path"]
            and "prompt-3" in item["relative_path"]
        ]
        if len(reservation_paths) > 1:
            raise CustodyContractError(
                "reservation_already_exists",
                "prompt_outcome.evidence.reservations",
            )
        if prompt_outcome.get("status") == "failed":
            reason = prompt_outcome.get("reason_code") or "invalid_probe_retry_second_prompt_failure"
            if wants_accepted:
                raise CustodyContractError(
                    "invalid_probe_retry_second_prompt_failure",
                    "prompt_outcome.status",
                )
            return {
                "schema": SCHEMA_RETRY_OFFLINE_SUMMARY,
                "outcome": RETRY_OUTCOME_SECOND_PROMPT_FAILURE,
                "reason_codes": [str(reason)],
                "next_correlation_ordinal": ledger_info["next_correlation_ordinal"],
                "next_prompt_ordinal": ledger_info["next_prompt_ordinal"],
                "live_claim_accepted": False,
                "live_session_proof_sha256": typed_proof.proof_sha256,
            }
        if prompt_outcome.get("status") != "succeeded":
            raise CustodyContractError(
                "invalid_probe_stage_accounting",
                "prompt_outcome.status",
            )

    if wants_accepted:
        if prompt_outcome is None:
            raise CustodyContractError(
                "blocked_probe_same_session_prompt_retry_unavailable",
                "prompt_outcome",
            )
        return {
            "schema": SCHEMA_RETRY_OFFLINE_SUMMARY,
            "outcome": RETRY_OUTCOME_ACCEPTED_SAME_SESSION_RETRY,
            "reason_codes": ["accepted_same_session_prompt_retry"],
            "next_correlation_ordinal": ledger_info["next_correlation_ordinal"],
            "next_prompt_ordinal": ledger_info["next_prompt_ordinal"],
            "live_claim_accepted": True,
            "live_session_proof_sha256": typed_proof.proof_sha256,
            "settings_mutated": False,
            "zed_launched": False,
        }

    if isinstance(claim, Mapping) and claim.get("outcome") == RETRY_OUTCOME_SECOND_PROMPT_FAILURE:
        return {
            "schema": SCHEMA_RETRY_OFFLINE_SUMMARY,
            "outcome": RETRY_OUTCOME_SECOND_PROMPT_FAILURE,
            "reason_codes": ["invalid_probe_retry_second_prompt_failure"],
            "next_correlation_ordinal": ledger_info["next_correlation_ordinal"],
            "next_prompt_ordinal": ledger_info["next_prompt_ordinal"],
            "live_claim_accepted": False,
            "live_session_proof_sha256": typed_proof.proof_sha256,
        }

    return {
        "schema": SCHEMA_RETRY_OFFLINE_SUMMARY,
        "outcome": RETRY_OUTCOME_UNAVAILABLE_PROOF,
        "reason_codes": ["blocked_probe_same_session_prompt_retry_unavailable"],
        "next_correlation_ordinal": ledger_info["next_correlation_ordinal"],
        "next_prompt_ordinal": ledger_info["next_prompt_ordinal"],
        "live_claim_accepted": False,
        "live_session_proof_sha256": typed_proof.proof_sha256,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to plan117-custody-artifact-manifest-v1 JSON",
    )
    parser.add_argument(
        "--checkpoint",
        choices=(
            "task4",
            "task5",
            ORIGIN_A_FIXTURE_V2_CLASSIFICATIONS_CHECKPOINT,
            ORIGIN_A_FIXTURE_V2_PREFLIGHT_CHECKPOINT,
            ORIGIN_A_3_CHECKPOINT,
            ORIGIN_A_FIXTURE_V2_FINAL_CHECKPOINT,
        ),
        default=None,
        help=(
            "Allow a partial Task 4/5 manifest, or an origin-A fixture-v2 "
            "classifications/preflight/origin-a-3/final checkpoint; omit for the "
            "complete parent final seal"
        ),
    )
    args = parser.parse_args(argv)

    try:
        if args.checkpoint == ORIGIN_A_FIXTURE_V2_CLASSIFICATIONS_CHECKPOINT:
            summary = verify_origin_a_fixture_v2_classifications(
                project_root=ROOT,
                manifest_path=args.manifest,
            )
            print(json.dumps(summary, separators=(",", ":"), sort_keys=True))
            return 0
        if args.checkpoint == ORIGIN_A_FIXTURE_V2_PREFLIGHT_CHECKPOINT:
            summary = verify_origin_a_fixture_v2_preflight(
                project_root=ROOT,
                manifest_path=args.manifest,
            )
            print(json.dumps(summary, separators=(",", ":"), sort_keys=True))
            return 0
        if args.checkpoint == ORIGIN_A_3_CHECKPOINT:
            summary = verify_origin_a3(
                project_root=ROOT,
                manifest_path=args.manifest,
            )
            print(json.dumps(summary, separators=(",", ":"), sort_keys=True))
            return 0
        if args.checkpoint == ORIGIN_A_FIXTURE_V2_FINAL_CHECKPOINT:
            summary = verify_origin_a_fixture_v2_final(
                project_root=ROOT,
                manifest_path=args.manifest,
            )
            print(json.dumps(summary, separators=(",", ":"), sort_keys=True))
            return 0
        result = verify_manifest(args.manifest, checkpoint=args.checkpoint)
    except CustodyContractError as exc:
        print(
            json.dumps(_failure_payload(exc), separators=(",", ":"), sort_keys=True),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(_summary_payload(result), separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
