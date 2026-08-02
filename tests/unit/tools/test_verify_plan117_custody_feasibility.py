"""Unit tests for the offline Plan 11.7 custody feasibility verifier."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tools import verify_plan117_custody_feasibility as verifier_mod
from tools.plan117_custody_contract import (
    CustodyContractError,
    ProbeDisposition,
    VerificationResult,
    atomic_write_json,
    sha256_file,
    verify_manifest,
)
from tools.plan117_custody_relay import (
    DIR_ZED_TO_AGENT,
    EOF_AGENT_TO_ZED,
    EOF_ZED_TO_AGENT,
    run_relay,
)

ROOT = Path(__file__).resolve().parents[3]
VERIFIER = ROOT / "tools" / "verify_plan117_custody_feasibility.py"

_DIGEST_A = "a" * 64
_DIGEST_B = "a" * 64
_DIGEST_C = "b" * 64


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    atomic_write_json(path, payload)
    return sha256_file(path)


def _artifact(locator: str, sha256: str, role: str, method: str = "raw_file_sha256") -> dict[str, Any]:
    return {
        "locator": locator,
        "sha256": sha256,
        "role": role,
        "hash_method": method,
    }


def _base_final_payload(
    *,
    artifacts: list[dict[str, Any]],
    signals: list[dict[str, Any]] | None = None,
    attempts: list[dict[str, Any]] | None = None,
    reducer_flags: dict[str, Any] | None = None,
    disposition: str = "infeasible_for_production_target",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "plan117-custody-artifact-manifest-v1",
        "checkpoint": "final",
        "complete": True,
        "report_root": "reports",
        "custody_root": "custody",
        "artifacts": artifacts,
        "attempts": attempts or [],
        "correlation_signals": signals if signals is not None else [],
        "direct_revalidation_field_paths": [],
        "reducer": reducer_flags
        or {
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
            "valid_b_continuation": True,
            "valid_completed_c_control": True,
            "message_binding_ok": True,
            "ancestry_revalidation_ok": True,
        },
        "declared_disposition": disposition,
        "settings_restored": True,
        "redaction_sealed": True,
        "document_audit_present": True,
        "valid_session_new_captured": True,
        "reason_codes": ["workspace_only_or_no_restart_discriminator"],
    }
    if extra:
        payload.update(extra)
    return payload


def _eligible_signal(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
    return payload


def test_verify_manifest_accepts_final_infeasible_fixture(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    custody_root = tmp_path / "custody"
    report_root.mkdir()
    custody_root.mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("reports/trigger.json", digest, "trigger_chain")],
        ),
    )
    result = verify_manifest(manifest_path)
    assert isinstance(result, VerificationResult)
    assert result.disposition is ProbeDisposition.INFEASIBLE
    assert result.verified_artifact_count == 1
    assert "workspace_only_or_no_restart_discriminator" in result.reason_codes


def test_verify_manifest_rejects_task0_partial_without_checkpoint(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema": "plan117-custody-artifact-manifest-v1",
            "checkpoint": "task0",
            "complete": True,
            "report_root": "reports",
            "custody_root": "custody",
            "artifacts": [_artifact("reports/trigger.json", digest, "trigger_chain")],
        },
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path)
    assert exc_info.value.reason_code == "partial_manifest_requires_checkpoint"
    assert "checkpoint" in exc_info.value.field_path


def test_verify_manifest_accepts_task4_checkpoint(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    custody_root = tmp_path / "custody"
    report_root.mkdir()
    custody_root.mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema": "plan117-custody-artifact-manifest-v1",
            "checkpoint": "task4",
            "complete": False,
            "report_root": "reports",
            "custody_root": "custody",
            "artifacts": [_artifact("reports/trigger.json", digest, "trigger_chain")],
            "attempts": [],
            "settings_restored": True,
        },
    )
    result = verify_manifest(manifest_path, checkpoint="task4")
    assert result.disposition is ProbeDisposition.INVALID_CORRELATION_INVENTORY
    assert result.verified_artifact_count == 1


def test_verify_manifest_rejects_path_escape(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    outside = tmp_path / "outside.json"
    digest = _write_json(outside, {"schema": "x", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("../outside.json", digest, "trigger_chain")],
        ),
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path)
    assert exc_info.value.reason_code == "path_outside_allowed_roots"


def test_verify_manifest_rejects_digest_mismatch(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    trigger = report_root / "trigger.json"
    _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("reports/trigger.json", "0" * 64, "trigger_chain")],
        ),
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path)
    assert exc_info.value.reason_code == "artifact_digest_mismatch"
    assert "sha256" in exc_info.value.field_path


def test_verify_manifest_rejects_crlf_line_endings(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    trigger = report_root / "trigger.json"
    trigger.write_bytes(b'{"schema":"plan117-custody-trigger-v1","complete":true}\r\n')
    digest = sha256_file(trigger)
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("reports/trigger.json", digest, "trigger_chain")],
        ),
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path)
    assert exc_info.value.reason_code == "crlf_line_endings_forbidden"


def test_verify_manifest_rejects_signal_boolean_tamper(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("reports/trigger.json", digest, "trigger_chain")],
            signals=[_eligible_signal(restart_stable=False)],
            disposition="feasible_server_side_custody_candidate",
            reducer_flags={
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
                "has_eligible_signal": True,
                "valid_b_continuation": True,
                "valid_completed_c_control": True,
                "message_binding_ok": True,
                "ancestry_revalidation_ok": True,
            },
        ),
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path)
    assert exc_info.value.reason_code in {
        "restart_stable_mismatch",
        "eligible_mismatch",
        "signal_recompute_mismatch",
    }


def test_verify_manifest_feasible_candidate_positive(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("reports/trigger.json", digest, "trigger_chain")],
            signals=[_eligible_signal()],
            disposition="feasible_server_side_custody_candidate",
            reducer_flags={
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
                "has_eligible_signal": True,
                "valid_b_continuation": True,
                "valid_completed_c_control": True,
                "message_binding_ok": True,
                "ancestry_revalidation_ok": True,
            },
            extra={"reason_codes": ["eligible_thread_binding"]},
        ),
    )
    result = verify_manifest(manifest_path)
    assert result.disposition is ProbeDisposition.FEASIBLE_CANDIDATE


def test_verify_manifest_case_insensitive_pin_compare(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("reports/trigger.json", digest.upper(), "trigger_chain")],
        ),
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path)
    assert exc_info.value.reason_code in {
        "sha256_not_lowercase",
        "invalid_manifest_schema",
        "artifact_digest_mismatch",
    }


def test_cli_prints_canonical_summary_and_nonzero_on_failure(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("reports/trigger.json", digest, "trigger_chain")],
        ),
    )
    ok = subprocess.run(
        [sys.executable, str(VERIFIER), "--manifest", str(manifest_path)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert ok.returncode == 0
    summary = json.loads(ok.stdout)
    assert summary["schema"] == "plan117-custody-verifier-summary-v1"
    assert summary["disposition"] == "infeasible_for_production_target"
    assert "reason_codes" in summary
    assert summary["verified_artifact_count"] == 1
    assert set(summary.keys()) == {
        "schema",
        "disposition",
        "reason_codes",
        "verified_artifact_count",
    }

    bad_manifest = tmp_path / "bad.json"
    atomic_write_json(
        bad_manifest,
        {
            "schema": "plan117-custody-artifact-manifest-v1",
            "checkpoint": "task0",
            "complete": True,
            "report_root": "reports",
            "custody_root": "custody",
            "artifacts": [_artifact("reports/trigger.json", digest, "trigger_chain")],
        },
    )
    bad = subprocess.run(
        [sys.executable, str(VERIFIER), "--manifest", str(bad_manifest)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert bad.returncode != 0
    err = json.loads(bad.stderr)
    assert err["reason_code"] == "partial_manifest_requires_checkpoint"
    assert "field_path" in err
    assert "OPTIMUS_API_KEY" not in bad.stderr


def test_cli_task5_checkpoint_option(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema": "plan117-custody-artifact-manifest-v1",
            "checkpoint": "task5",
            "complete": False,
            "report_root": "reports",
            "custody_root": "custody",
            "artifacts": [_artifact("reports/trigger.json", digest, "trigger_chain")],
            "attempts": [],
            "correlation_signals": [],
            "direct_revalidation_field_paths": [],
            "reducer": {
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
                "valid_b_continuation": True,
                "valid_completed_c_control": False,
                "message_binding_ok": False,
                "ancestry_revalidation_ok": True,
            },
            "declared_disposition": "infeasible_for_production_target",
            "settings_restored": True,
            "reason_codes": ["workspace_only_or_no_restart_discriminator"],
        },
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--manifest",
            str(manifest_path),
            "--checkpoint",
            "task5",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0
    summary = json.loads(proc.stdout)
    assert summary["disposition"] == "infeasible_for_production_target"


def test_main_module_entry_covers_success_and_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Exercise the CLI path bootstrap branch used when invoked as a script.
    root = str(verifier_mod.ROOT)
    if root in sys.path:
        sys.path.remove(root)
    import importlib

    importlib.reload(verifier_mod)
    assert root in sys.path

    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("reports/trigger.json", digest, "trigger_chain")],
            attempts=[
                {
                    "attempt_id": "c-1",
                    "phase": "origin-a",
                    "kind": "correlation_capture",
                    "ordinal": 1,
                    "failure_class": "none",
                    "reason_code": None,
                    "manifest_sha256": _DIGEST_A,
                }
            ],
        ),
    )
    assert verifier_mod.main(["--manifest", str(manifest_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema"] == "plan117-custody-verifier-summary-v1"

    bad = tmp_path / "bad.json"
    atomic_write_json(
        bad,
        {
            "schema": "plan117-custody-artifact-manifest-v1",
            "checkpoint": "task0",
            "complete": True,
            "report_root": "reports",
            "custody_root": "custody",
            "artifacts": [],
        },
    )
    assert verifier_mod.main(["--manifest", str(bad)]) == 1
    err = json.loads(capsys.readouterr().err)
    assert err["reason_code"] == "partial_manifest_requires_checkpoint"


def test_verify_manifest_rejects_invalid_json_and_non_object(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8", newline="\n")
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(bad)
    assert exc_info.value.reason_code == "invalid_manifest_json"

    arr = tmp_path / "arr.json"
    arr.write_text("[]", encoding="utf-8", newline="\n")
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(arr)
    assert exc_info.value.reason_code == "invalid_manifest_json"


def test_verify_manifest_checkpoint_mismatch_and_unsupported(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema": "plan117-custody-artifact-manifest-v1",
            "checkpoint": "task4",
            "complete": False,
            "report_root": "reports",
            "custody_root": "custody",
            "artifacts": [_artifact("reports/trigger.json", digest, "trigger_chain")],
            "settings_restored": True,
        },
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path, checkpoint="task5")
    assert exc_info.value.reason_code == "checkpoint_mismatch"


def test_verify_manifest_reviewer_owned_and_unsupported_method(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[
                _artifact("reports/trigger.json", digest, "trigger_chain"),
                {
                    "locator": "docs/superpowers/reviews/plan-11-7-review-checkpoints.md",
                    "sha256": None,
                    "role": "checkpoint_log",
                    "hash_method": "reviewer_owned_gitignored_not_hashed",
                },
            ],
        ),
    )
    # Path escapes report/custody roots for docs/... — place a stub under custody instead.
    custody_doc = tmp_path / "custody" / "checkpoint.md"
    custody_doc.write_text("x\n", encoding="utf-8", newline="\n")
    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[
                _artifact("reports/trigger.json", digest, "trigger_chain"),
                {
                    "locator": "custody/checkpoint.md",
                    "sha256": None,
                    "role": "checkpoint_log",
                    "hash_method": "reviewer_owned_gitignored_not_hashed",
                },
            ],
        ),
    )
    result = verify_manifest(manifest_path)
    assert result.verified_artifact_count == 1

    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[
                {
                    "locator": "reports/trigger.json",
                    "sha256": digest,
                    "role": "trigger_chain",
                    "hash_method": "md5",
                }
            ],
        ),
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path)
    assert exc_info.value.reason_code == "unsupported_hash_method"


def test_verify_manifest_missing_artifact_and_budget_and_seal_gates(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"

    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("reports/missing.json", digest, "trigger_chain")],
        ),
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path)
    assert exc_info.value.reason_code == "artifact_missing_or_symlink"

    attempts = [
        {
            "attempt_id": f"c-{i}",
            "phase": "origin-a",
            "kind": "correlation_capture",
            "ordinal": i,
            "failure_class": "transient",
            "reason_code": "x",
            "manifest_sha256": _DIGEST_A,
        }
        for i in range(1, 5)
    ]
    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("reports/trigger.json", digest, "trigger_chain")],
            attempts=attempts,
        ),
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path)
    assert exc_info.value.reason_code == "attempt_budget_exceeded"

    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("reports/trigger.json", digest, "trigger_chain")],
            extra={"settings_restored": False},
        ),
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path)
    assert exc_info.value.reason_code == "settings_not_restored"

    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("reports/trigger.json", digest, "trigger_chain")],
            extra={"redaction_sealed": False},
        ),
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path)
    assert exc_info.value.reason_code == "redaction_seal_missing"

    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("reports/trigger.json", digest, "trigger_chain")],
            extra={"document_audit_present": False},
        ),
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path)
    assert exc_info.value.reason_code == "document_audit_missing"


def test_verify_manifest_task4_settings_not_restored(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema": "plan117-custody-artifact-manifest-v1",
            "checkpoint": "task4",
            "complete": False,
            "report_root": "reports",
            "custody_root": "custody",
            "artifacts": [_artifact("reports/trigger.json", digest, "trigger_chain")],
            "settings_restored": False,
        },
    )
    result = verify_manifest(manifest_path, checkpoint="task4")
    assert result.disposition is ProbeDisposition.INVALID_SETTINGS_RESTORE


def test_verify_manifest_reducer_and_disposition_required(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema": "plan117-custody-artifact-manifest-v1",
            "checkpoint": "task5",
            "complete": False,
            "report_root": "reports",
            "custody_root": "custody",
            "artifacts": [_artifact("reports/trigger.json", digest, "trigger_chain")],
            "settings_restored": True,
        },
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path, checkpoint="task5")
    assert exc_info.value.reason_code == "reducer_required"

    atomic_write_json(
        manifest_path,
        {
            "schema": "plan117-custody-artifact-manifest-v1",
            "checkpoint": "final",
            "complete": True,
            "report_root": "reports",
            "custody_root": "custody",
            "artifacts": [_artifact("reports/trigger.json", digest, "trigger_chain")],
            "reducer": {
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
                "valid_b_continuation": True,
                "valid_completed_c_control": True,
                "message_binding_ok": True,
                "ancestry_revalidation_ok": True,
            },
            "settings_restored": True,
            "redaction_sealed": True,
            "document_audit_present": True,
            "reason_codes": ["x"],
        },
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path)
    assert exc_info.value.reason_code == "declared_disposition_required"


def test_verify_manifest_declared_disposition_mismatch(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("reports/trigger.json", digest, "trigger_chain")],
            disposition="feasible_server_side_custody_candidate",
        ),
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path)
    assert exc_info.value.reason_code == "declared_disposition_mismatch"


def test_verify_manifest_eligible_flag_mismatch(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    (tmp_path / "custody").mkdir()
    trigger = report_root / "trigger.json"
    digest = _write_json(trigger, {"schema": "plan117-custody-trigger-v1", "complete": True})
    manifest_path = tmp_path / "manifest.json"
    atomic_write_json(
        manifest_path,
        _base_final_payload(
            artifacts=[_artifact("reports/trigger.json", digest, "trigger_chain")],
            signals=[_eligible_signal()],
            disposition="feasible_server_side_custody_candidate",
            reducer_flags={
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
                "valid_b_continuation": True,
                "valid_completed_c_control": True,
                "message_binding_ok": True,
                "ancestry_revalidation_ok": True,
            },
        ),
    )
    with pytest.raises(CustodyContractError) as exc_info:
        verify_manifest(manifest_path)
    assert exc_info.value.reason_code == "eligible_signal_flag_mismatch"


def _make_valid_relay_capture(tmp_path: Path, *, run_id: str = "v1") -> Path:
    parent_in = __import__("io").BytesIO(b"abc\x00\xff")
    parent_out = __import__("io").BytesIO()
    code = (
        "import sys;"
        "data=sys.stdin.buffer.read();"
        "sys.stdout.buffer.write(data);"
        "sys.stdout.buffer.flush()"
    )
    exit_code = run_relay(
        capture_root=tmp_path,
        run_id=run_id,
        child_executable=sys.executable,
        child_args=["-c", code],
        stdin=parent_in,
        stdout=parent_out,
    )
    assert exit_code == 0
    return tmp_path / run_id


def test_verify_relay_capture_accepts_valid(tmp_path: Path) -> None:
    run_dir = _make_valid_relay_capture(tmp_path)
    verifier_mod.verify_relay_capture(run_dir)


@pytest.mark.parametrize(
    ("mutator", "reason_substr"),
    [
        (
            lambda d: (d / "zed-to-agent.bin").write_bytes(
                (d / "zed-to-agent.bin").read_bytes() + b"Z"
            ),
            "relay_",
        ),
        (
            lambda d: _mutate_index_field(d, "size", 999),
            "relay_",
        ),
        (
            lambda d: _mutate_index_field(d, "directional_offset", 999),
            "relay_offset",
        ),
        (
            lambda d: _mutate_index_field(d, "sequence", 99),
            "relay_sequence",
        ),
        (
            lambda d: _mutate_index_field(d, "direction", "mutated_direction"),
            "relay_direction",
        ),
        (
            lambda d: _mutate_index_field(d, "sha256", "0" * 64),
            "relay_chunk_digest",
        ),
        (
            lambda d: _mutate_index_field(d, "run_id", "other-run"),
            "relay_run_id",
        ),
        (
            lambda d: _mutate_summary_field(d, "child_argv_sha256", "1" * 64),
            "relay_child_argv_digest_mismatch",
        ),
        (
            lambda d: _mutate_summary_field(d, "relay_sha256", "2" * 64),
            "relay_digest_mismatch",
        ),
        (
            lambda d: _drop_summary_key(d, "child_exit_code"),
            "relay_terminal_exit",
        ),
        (
            lambda d: _drop_summary_key(d, "terminal_disposition"),
            "relay_terminal_disposition",
        ),
        (
            lambda d: _strip_eof_records(d),
            "relay_missing_directional_eof",
        ),
    ],
)
def test_verify_relay_capture_rejects_independent_mutations(
    tmp_path: Path,
    mutator: Any,
    reason_substr: str,
) -> None:
    run_dir = _make_valid_relay_capture(tmp_path, run_id=f"m-{abs(hash(reason_substr)) % 10_000_000}")
    verifier_mod.verify_relay_capture(run_dir)
    mutator(run_dir)
    with pytest.raises(CustodyContractError) as exc_info:
        verifier_mod.verify_relay_capture(run_dir)
    assert reason_substr in exc_info.value.reason_code


def test_verify_relay_capture_rejects_child_argv_digest_missing(tmp_path: Path) -> None:
    run_dir = _make_valid_relay_capture(tmp_path, run_id="argv-missing")
    _drop_summary_key(run_dir, "child_argv_sha256")
    with pytest.raises(CustodyContractError) as exc_info:
        verifier_mod.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code == "relay_child_argv_digest_missing"


def test_verify_relay_capture_rejects_reordered_index(tmp_path: Path) -> None:
    run_dir = _make_valid_relay_capture(tmp_path, run_id="reorder")
    index_path = run_dir / "relay-index.ndjson"
    lines = [line for line in index_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) >= 2
    lines[0], lines[1] = lines[1], lines[0]
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(CustodyContractError) as exc_info:
        verifier_mod.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code == "relay_sequence_gap"


def test_verify_relay_capture_rejects_inserted_bytes_in_index_chunk(tmp_path: Path) -> None:
    run_dir = _make_valid_relay_capture(tmp_path, run_id="insert")
    index_path = run_dir / "relay-index.ndjson"
    records = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines() if line]
    data_records = [r for r in records if r["direction"] == DIR_ZED_TO_AGENT]
    assert data_records
    data_records[0]["size"] = int(data_records[0]["size"]) + 1
    rebuilt = []
    for record in records:
        rebuilt.append(json.dumps(record, separators=(",", ":"), sort_keys=True))
    index_path.write_text("\n".join(rebuilt) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(CustodyContractError) as exc_info:
        verifier_mod.verify_relay_capture(run_dir)
    assert exc_info.value.reason_code in {
        "relay_raw_bytes_mismatch",
        "relay_chunk_digest_mismatch",
        "relay_chunk_size_invalid",
    }


def _mutate_index_field(run_dir: Path, field: str, value: Any) -> None:
    index_path = run_dir / "relay-index.ndjson"
    records = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines() if line]
    target = next(r for r in records if r["direction"] == DIR_ZED_TO_AGENT)
    target[field] = value
    index_path.write_text(
        "\n".join(json.dumps(r, separators=(",", ":"), sort_keys=True) for r in records) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _mutate_summary_field(run_dir: Path, field: str, value: Any) -> None:
    summary_path = run_dir / "relay-summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if value is None and field in payload:
        return
    payload[field] = value
    atomic_write_json(summary_path, payload)


def _drop_summary_key(run_dir: Path, field: str) -> None:
    summary_path = run_dir / "relay-summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload.pop(field, None)
    atomic_write_json(summary_path, payload)


def _strip_eof_records(run_dir: Path) -> None:
    index_path = run_dir / "relay-index.ndjson"
    records = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines() if line]
    kept = [r for r in records if r["direction"] not in {EOF_ZED_TO_AGENT, EOF_AGENT_TO_ZED}]
    # Resequence to keep sequence gap-free so the missing-EOF reason wins.
    for index, record in enumerate(kept):
        record["sequence"] = index
    index_path.write_text(
        "\n".join(json.dumps(r, separators=(",", ":"), sort_keys=True) for r in kept) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    summary_path = run_dir / "relay-summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload["zed_to_agent_eof"] = False
    payload["agent_to_zed_eof"] = False
    atomic_write_json(summary_path, payload)
