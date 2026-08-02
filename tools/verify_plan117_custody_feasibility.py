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
    FailureClass,
    StageAttemptRecord,
    StageKind,
    StageStatus,
    VerificationResult,
    normalize_stage_ledger,
    sha256_file,
    sha256_hex_equal,
    verify_manifest,
)
from tools.plan117_custody_relay import verify_relay_capture  # noqa: E402

PROMPT_FIXTURE_V2_SHA256 = (
    "9195EFEEE3A2180CFB85EDE409FF7785F159F64E36426DCDB369251560E28A50"
)
PYPROJECT_TARGET_SHA256 = (
    "AE28C0C3776F6B78DF23E86FC0E88B0088FEBB7241A04650C604D713E23EF697"
)
ORIGIN_A_FIXTURE_V2_CLASSIFICATIONS_CHECKPOINT = "origin-a-fixture-v2-classifications"
ORIGIN_A_FIXTURE_V2_PREFLIGHT_CHECKPOINT = "origin-a-fixture-v2-preflight"
_ORIGIN_A_FIXTURE_V2_CHECKPOINTS = frozenset(
    {
        ORIGIN_A_FIXTURE_V2_CLASSIFICATIONS_CHECKPOINT,
        ORIGIN_A_FIXTURE_V2_PREFLIGHT_CHECKPOINT,
    }
)
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
    "ORIGIN_A_FIXTURE_V2_PREFLIGHT_CHECKPOINT",
    "SCHEMA_EXECUTION_PREFLIGHT",
    "main",
    "verify_approval_equivalence",
    "verify_execution_preflight_payload",
    "verify_fixture_v2_identity",
    "verify_manifest",
    "verify_origin_a_fixture_v2_classifications",
    "verify_origin_a_fixture_v2_classifications_bundle",
    "verify_origin_a_fixture_v2_preflight",
    "verify_origin_a_original_hashes",
    "verify_relay_capture",
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
    if head.lower() != actual_head.lower():
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

    verify_execution_preflight_payload(
        preflight,
        actual_head=head_fn(),
        actual_files=actual_files,
        production_clean=clean_fn(),
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
        ),
        default=None,
        help=(
            "Allow a partial Task 4/5 manifest, or an origin-A fixture-v2 "
            "classifications/preflight checkpoint; omit for the complete final seal"
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
