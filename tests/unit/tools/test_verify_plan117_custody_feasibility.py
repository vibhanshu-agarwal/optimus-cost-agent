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


def test_verify_settings_transaction_and_approval_equivalence(tmp_path: Path) -> None:
    settings_ok = {
        "schema": "plan117-custody-settings-transaction-v1",
        "settings_path": str(tmp_path / "settings.json"),
        "pre_image_existed": True,
        "pre_image_sha256": "a" * 64,
        "mutated_sha256": "b" * 64,
        "changed_key_paths": ["agent_servers.optimus.command"],
        "restored": True,
        "final_existed": True,
        "final_sha256": "a" * 64,
    }
    settings_path = tmp_path / "settings-transaction.json"
    atomic_write_json(settings_path, settings_ok)
    assert verifier_mod.verify_settings_transaction_proof(settings_path)["restored"] is True

    bad = dict(settings_ok, restored=False)
    bad_path = tmp_path / "settings-bad.json"
    atomic_write_json(bad_path, bad)
    with pytest.raises(CustodyContractError) as exc:
        verifier_mod.verify_settings_transaction_proof(bad_path)
    assert exc.value.reason_code == "settings_not_restored"

    eq = {
        "schema": "plan117-custody-approval-equivalence-v1",
        "equivalent": True,
        "compared_fields": ["approval_id"],
        "final_reason_code": "AUTHORIZED",
        "record_hmac_verified": True,
    }
    eq_path = tmp_path / "approval-equivalence.json"
    atomic_write_json(eq_path, eq)
    assert verifier_mod.verify_approval_equivalence(eq_path)["equivalent"] is True

    eq_bad = dict(eq, equivalent=False)
    eq_bad_path = tmp_path / "approval-bad.json"
    atomic_write_json(eq_bad_path, eq_bad)
    with pytest.raises(CustodyContractError) as exc2:
        verifier_mod.verify_approval_equivalence(eq_bad_path)
    assert exc2.value.reason_code == "invalid_probe_relay_environment_mismatch"


def test_verify_transcript_debug_agreement_helper() -> None:
    left = {
        "messages": [{"method": "initialize", "id": 1}],
        "ordered_update_types": [],
        "server_session_id": "s",
        "interval": {"start_ns": 1, "end_ns": 2},
    }
    verifier_mod.verify_transcript_debug_agreement(left, left)
    with pytest.raises(CustodyContractError) as exc:
        verifier_mod.verify_transcript_debug_agreement(left, dict(left, server_session_id="x"))
    assert exc.value.reason_code == "invalid_probe_transcript_debug_divergence"


# --- Origin-A fixture v2: offline supersession / stage / fixture verification -


AMENDMENT_SHA256 = "5BB327D88761AE329869B90866839D03F61EFF6AF0E5AE47F8D3D7551F849A4D"
PROMPT_V2_SHA256 = "9195EFEEE3A2180CFB85EDE409FF7785F159F64E36426DCDB369251560E28A50"
PYPROJECT_SHA256 = "AE28C0C3776F6B78DF23E86FC0E88B0088FEBB7241A04650C604D713E23EF697"


def _verifier_stage_api() -> Any:
    required = (
        "verify_stage_ledger_payload",
        "verify_supersession_payload",
        "verify_supplemental_fact_payload",
        "verify_fixture_v2_identity",
        "verify_origin_a_original_hashes",
        "verify_run_reservation_payload",
    )
    missing = [name for name in required if not hasattr(verifier_mod, name)]
    if missing:
        pytest.fail(f"missing origin-a fixture-v2 verifier API: {missing}")
    return verifier_mod


def test_verifier_accepts_valid_stage_ledger_and_rejects_tampered_fields() -> None:
    v = _verifier_stage_api()
    from tools.plan117_custody_contract import (
        EvidenceReference,
        FailureClass,
        StageAttemptRecord,
        StageKind,
        StageStatus,
        normalize_stage_ledger,
        stage_attempt_record_payload,
    )

    records = (
        StageAttemptRecord(
            record_id="origin-a-1-correlation",
            run_attempt_id="origin-a-1",
            stage=StageKind.CORRELATION_CAPTURE,
            ordinal=1,
            status=StageStatus.FAILED,
            failure_class=FailureClass.PERMANENT,
            reason_code="invalid_probe_relay_capture_tooling_failure",
            evidence=(EvidenceReference("a.json", "a" * 64, "raw_file_sha256"),),
            supersedes_record_id="orig-a1",
            supersedes_sha256="a" * 64,
            amendment_sha256=AMENDMENT_SHA256.lower(),
            created_by="plan117-task1",
            created_utc="2026-08-02T16:00:00Z",
        ),
        StageAttemptRecord(
            record_id="origin-a-2-correlation",
            run_attempt_id="origin-a-2",
            stage=StageKind.CORRELATION_CAPTURE,
            ordinal=2,
            status=StageStatus.SUCCEEDED,
            failure_class=FailureClass.NONE,
            reason_code=None,
            evidence=(EvidenceReference("b.json", "b" * 64, "raw_file_sha256"),),
            supersedes_record_id="orig-a2",
            supersedes_sha256="b" * 64,
            amendment_sha256=AMENDMENT_SHA256.lower(),
            created_by="plan117-task1",
            created_utc="2026-08-02T16:00:00Z",
        ),
        StageAttemptRecord(
            record_id="origin-a-2-prompt",
            run_attempt_id="origin-a-2",
            stage=StageKind.POST_NEW_PROMPT,
            ordinal=1,
            status=StageStatus.FAILED,
            failure_class=FailureClass.PERMANENT,
            reason_code="AMBIGUOUS_WORKSPACE_REFERENCE",
            evidence=(EvidenceReference("c.json", "c" * 64, "raw_file_sha256"),),
            supersedes_record_id="orig-a2-prompt",
            supersedes_sha256="c" * 64,
            amendment_sha256=AMENDMENT_SHA256.lower(),
            created_by="plan117-task1",
            created_utc="2026-08-02T16:00:00Z",
        ),
    )
    ledger = normalize_stage_ledger(records)
    payload = {
        "schema": "plan117-custody-stage-ledger-v1",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "records": [stage_attempt_record_payload(r) for r in records],
        "next_correlation_ordinal": ledger.next_correlation_ordinal,
        "next_prompt_ordinal": ledger.next_prompt_ordinal,
    }
    assert v.verify_stage_ledger_payload(payload)["next_correlation_ordinal"] == 3

    bad = dict(payload, next_correlation_ordinal=1)
    with pytest.raises(CustodyContractError) as exc:
        v.verify_stage_ledger_payload(bad)
    assert exc.value.reason_code == "invalid_probe_stage_accounting"

    bad_schema = dict(payload, schema="wrong")
    with pytest.raises(CustodyContractError) as schema_exc:
        v.verify_stage_ledger_payload(bad_schema)
    assert schema_exc.value.reason_code in {
        "invalid_probe_stage_accounting",
        "invalid_stage_ledger_schema",
    }


def test_verifier_fail_closed_on_supersession_fact_reservation_and_fixture_fields(
    tmp_path: Path,
) -> None:
    v = _verifier_stage_api()
    from tools.plan117_custody_contract import (
        EvidenceReference,
        FailureClass,
        StageAttemptRecord,
        StageKind,
        StageStatus,
        stage_attempt_record_payload,
    )

    record = StageAttemptRecord(
        record_id="origin-a-1-correlation",
        run_attempt_id="origin-a-1",
        stage=StageKind.CORRELATION_CAPTURE,
        ordinal=1,
        status=StageStatus.FAILED,
        failure_class=FailureClass.PERMANENT,
        reason_code="invalid_probe_relay_capture_tooling_failure",
        evidence=(EvidenceReference("a.json", "a" * 64, "raw_file_sha256"),),
        supersedes_record_id="orig-a1",
        supersedes_sha256="a" * 64,
        amendment_sha256=AMENDMENT_SHA256.lower(),
        created_by="plan117-task1",
        created_utc="2026-08-02T16:00:00Z",
    )
    good = stage_attempt_record_payload(record)
    good["schema"] = "plan117-custody-stage-attempt-record-v1"
    assert v.verify_supersession_payload(good)["record_id"] == "origin-a-1-correlation"

    for field in (
        "record_id",
        "run_attempt_id",
        "stage",
        "ordinal",
        "status",
        "failure_class",
        "evidence",
        "amendment_sha256",
        "created_by",
        "created_utc",
        "supersedes_record_id",
        "supersedes_sha256",
    ):
        tampered = dict(good)
        if field == "ordinal":
            tampered[field] = 0
        elif field == "evidence":
            tampered[field] = []
        elif field in {"supersedes_record_id", "supersedes_sha256"}:
            tampered[field] = None
        else:
            tampered[field] = "tampered"
        with pytest.raises(CustodyContractError):
            v.verify_supersession_payload(tampered)

    fact = {
        "schema": "plan117-custody-supplemental-fact-record-v1",
        "record_id": "origin-a-2-client",
        "run_attempt_id": "origin-a-2",
        "fact_kind": "zed_client_crash",
        "reason_code": "stop_probe_zed_client_crashed",
        "evidence": [
            {
                "relative_path": "events.json",
                "sha256": "e" * 64,
                "hash_method": "raw_file_sha256",
            }
        ],
        "supersedes_record_id": "orig-crash",
        "supersedes_sha256": "e" * 64,
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "created_by": "plan117-task1",
        "created_utc": "2026-08-02T16:00:00Z",
    }
    assert v.verify_supplemental_fact_payload(fact)["fact_kind"] == "zed_client_crash"
    for field in (
        "record_id",
        "run_attempt_id",
        "fact_kind",
        "reason_code",
        "evidence",
        "amendment_sha256",
        "created_by",
        "created_utc",
    ):
        bad_fact = dict(fact)
        bad_fact[field] = [] if field == "evidence" else "tampered"
        with pytest.raises(CustodyContractError):
            v.verify_supplemental_fact_payload(bad_fact)

    reservation = {
        "schema": "plan117-custody-run-reservation-v1",
        "run_attempt_id": "origin-a-3",
        "correlation_ordinal": 3,
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "created_utc": "2026-08-02T16:00:00Z",
    }
    assert v.verify_run_reservation_payload(reservation)["run_attempt_id"] == "origin-a-3"
    with pytest.raises(CustodyContractError):
        v.verify_run_reservation_payload(dict(reservation, correlation_ordinal=4))
    with pytest.raises(CustodyContractError):
        v.verify_run_reservation_payload(dict(reservation, amendment_sha256="0" * 64))

    fixture = ROOT / "tests" / "fixtures" / "evidence" / "plan117-server-custody-prompt-v2.txt"
    v.verify_fixture_v2_identity(prompt_fixture=fixture, workspace_root=ROOT)
    with pytest.raises(CustodyContractError) as fix_exc:
        v.verify_fixture_v2_identity(
            prompt_fixture=tmp_path / "missing.txt",
            workspace_root=ROOT,
        )
    assert fix_exc.value.reason_code == "invalid_probe_fixture_identity_mismatch"

    original = tmp_path / "origin-a-1" / "attempt-manifest.json"
    original.parent.mkdir(parents=True)
    original.write_bytes(b'{"ok":true}\n')
    digest = sha256_file(original)
    v.verify_origin_a_original_hashes(
        originals_root=tmp_path,
        expected_relative_sha256={"origin-a-1/attempt-manifest.json": digest},
    )
    with pytest.raises(CustodyContractError) as orig_exc:
        v.verify_origin_a_original_hashes(
            originals_root=tmp_path,
            expected_relative_sha256={"origin-a-1/attempt-manifest.json": "0" * 64},
        )
    assert orig_exc.value.reason_code == "invalid_probe_origin_attempt_original_mismatch"


# --- Origin-A fixture v2 Task 3: classifications checkpoint + tamper matrix ---


_A1_MANIFEST = "7d64d5943002b15dcd977b0bc7614fc4234f9dd6d823c1533da6a0677f9ff446"
_A1_PHASE = "ce358bd9e715c733766fa7080dd0cfdc26aeae3368f0ad8aedde1dd74432c725"
_EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_A2_MANIFEST = "083e0953c8d89781c8c3100545bfc2e4524e94cbbaae7b32574da4d88f597f63"
_A2_PHASE = "cce1fac316f5961b6e1b3a57463d3deb5119111ff9856b7a405761b459e47ff1"
_A2_Z2A = "cd7b2463acd6dbff71f9887bdec5cbc31b3c7b28504b294859dafda14b9a53e0"
_A2_A2Z = "dc1ae7db33d1af23d94ff3da315e4f4dd2400bb12e9e671f279565298f928ecf"
_A2_INDEX = "6d2e712d4f56c5225a2dbf5e9ce2787529d4f359aaa045b9802ff7cfcea5f610"
_EVENT_FACTS = "75b12ded46b3deb9c6b2a4ba8982857616d29dd8485535454f435b98a2a491da"


def _ev(relative_path: str, digest: str) -> dict[str, str]:
    return {
        "relative_path": relative_path,
        "sha256": digest,
        "hash_method": "raw_file_sha256",
    }


def _task3_stage_payload(
    *,
    record_id: str,
    run_attempt_id: str,
    stage: str,
    ordinal: int,
    status: str,
    failure_class: str,
    reason_code: str | None,
    evidence: list[dict[str, str]],
    supersedes_record_id: str,
    supersedes_sha256: str,
    notes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "plan117-custody-stage-attempt-record-v1",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "created_by": "plan117-task3",
        "created_utc": "2026-08-02T17:30:00Z",
        "evidence": evidence,
        "failure_class": failure_class,
        "ordinal": ordinal,
        "reason_code": reason_code,
        "record_id": record_id,
        "run_attempt_id": run_attempt_id,
        "stage": stage,
        "status": status,
        "supersedes_record_id": supersedes_record_id,
        "supersedes_sha256": supersedes_sha256,
    }
    if notes is not None:
        payload["classification_notes"] = notes
    return payload


def _task3_valid_bundle() -> dict[str, Any]:
    a1 = _task3_stage_payload(
        record_id="origin-a-1-correlation",
        run_attempt_id="origin-a-1",
        stage="correlation_capture",
        ordinal=1,
        status="failed",
        failure_class="permanent",
        reason_code="invalid_probe_relay_capture_tooling_failure",
        evidence=[
            _ev("attempts/origin-a-1/attempt-manifest.json", _A1_MANIFEST),
            _ev("attempts/origin-a-1/phase-observation.json", _A1_PHASE),
            _ev("origin-a-1/zed-to-agent.bin", _EMPTY),
            _ev("origin-a-1/agent-to-zed.bin", _EMPTY),
            _ev("origin-a-1/relay-index.ndjson", _EMPTY),
        ],
        supersedes_record_id="origin-a-1-original-manifest",
        supersedes_sha256=_A1_MANIFEST,
        notes={
            "full_duplex_deadlock": True,
            "forced_termination": True,
            "empty_capture": True,
            "matching_zed_crash_event": False,
            "event_facts_oa1_zed_fault_event_count": 0,
            "event_facts_oa1_exception_0xc0000409_count": 0,
            "prompt_stage_started": False,
            "product_infeasibility_evidence": False,
        },
    )
    a2_corr = _task3_stage_payload(
        record_id="origin-a-2-correlation",
        run_attempt_id="origin-a-2",
        stage="correlation_capture",
        ordinal=2,
        status="succeeded",
        failure_class="none",
        reason_code=None,
        evidence=[
            _ev("attempts/origin-a-2/attempt-manifest.json", _A2_MANIFEST),
            _ev("attempts/origin-a-2/phase-observation.json", _A2_PHASE),
            _ev("origin-a-2/zed-to-agent.bin", _A2_Z2A),
            _ev("origin-a-2/agent-to-zed.bin", _A2_A2Z),
            _ev("origin-a-2/relay-index.ndjson", _A2_INDEX),
        ],
        supersedes_record_id="origin-a-2-original-manifest",
        supersedes_sha256=_A2_MANIFEST,
        notes={
            "initialize_and_session_new": True,
            "index_and_byte_consistency": True,
            "relay_summary_present": False,
        },
    )
    a2_prompt = _task3_stage_payload(
        record_id="origin-a-2-prompt",
        run_attempt_id="origin-a-2",
        stage="post_new_prompt",
        ordinal=1,
        status="failed",
        failure_class="permanent",
        reason_code="AMBIGUOUS_WORKSPACE_REFERENCE",
        evidence=[_ev("attempts/origin-a-2/phase-observation.json", _A2_PHASE)],
        supersedes_record_id="origin-a-2-original-observation",
        supersedes_sha256=_A2_PHASE,
        notes={
            "pre_gateway_fixture_failure": True,
            "does_not_erase_correlation_success": True,
        },
    )
    client = {
        "schema": "plan117-custody-supplemental-fact-record-v1",
        "record_id": "origin-a-2-client",
        "run_attempt_id": "origin-a-2",
        "fact_kind": "zed_client_crash",
        "reason_code": "stop_probe_zed_client_crashed",
        "evidence": [
            _ev(
                "reports/plan-11-7-server-custody-artifacts/amendments/"
                "origin-a-fixture-v2/event-facts.json",
                _EVENT_FACTS,
            ),
            {
                "relative_path": "origin-a-2/relay-summary.json",
                "sha256": "absent",
                "hash_method": "presence_state",
            },
        ],
        "supersedes_record_id": "origin-a-2-original-crash-label",
        "supersedes_sha256": _A2_MANIFEST,
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "created_by": "plan117-task3",
        "created_utc": "2026-08-02T17:30:00Z",
        "classification_notes": {
            "exception_code": "0xc0000409",
            "application_error_event_id": 1000,
            "application_error_provider": "Application Error",
            "order_after_prompt_refusal": True,
            "relay_summary_absent": True,
            "does_not_change_correlation_success": True,
            "does_not_reclassify_prompt_failure": True,
        },
    }
    # Supplemental evidence with non-hex sha256 may fail _require_evidence only on type —
    # use a dedicated absent marker object instead for the crash fact in real files.
    client["evidence"] = [
        _ev(
            "reports/plan-11-7-server-custody-artifacts/amendments/"
            "origin-a-fixture-v2/event-facts.json",
            _EVENT_FACTS,
        ),
        _ev("event-facts/origin-a-2-exception-0xc0000409", _EVENT_FACTS),
    ]
    client["relay_summary_state"] = {"exists": False, "custody_relative": "origin-a-2/relay-summary.json"}
    stage_records = [a1, a2_corr, a2_prompt]
    ledger = {
        "schema": "plan117-custody-stage-ledger-v1",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "records": stage_records,
        "next_correlation_ordinal": 3,
        "next_prompt_ordinal": 2,
    }
    expected_originals = {
        "attempts/origin-a-1/attempt-manifest.json": _A1_MANIFEST,
        "attempts/origin-a-1/phase-observation.json": _A1_PHASE,
        "origin-a-1/zed-to-agent.bin": _EMPTY,
        "origin-a-1/agent-to-zed.bin": _EMPTY,
        "origin-a-1/relay-index.ndjson": _EMPTY,
        "attempts/origin-a-2/attempt-manifest.json": _A2_MANIFEST,
        "attempts/origin-a-2/phase-observation.json": _A2_PHASE,
        "origin-a-2/zed-to-agent.bin": _A2_Z2A,
        "origin-a-2/agent-to-zed.bin": _A2_A2Z,
        "origin-a-2/relay-index.ndjson": _A2_INDEX,
    }
    return {
        "origin_a_1_correlation": a1,
        "origin_a_2_correlation": a2_corr,
        "origin_a_2_prompt": a2_prompt,
        "origin_a_2_client": client,
        "stage_ledger": ledger,
        "expected_originals": expected_originals,
    }


def _seed_originals(root: Path, expected: dict[str, str]) -> None:
    """Create stand-in original files whose digests match ``expected`` via rewrite of bytes.

    For unit tampers we only need presence + controllable digests; use empty file for EMPTY
    and unique content otherwise by writing digest-tagged placeholder bytes then adjusting
    expected map to actual hashes when seeding unique content.
    """
    for relative, digest in expected.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if digest == _EMPTY:
            path.write_bytes(b"")
            continue
        # Write content that will not match pinned digest unless tests override expected.
        path.write_bytes(f"placeholder:{relative}\n".encode())


def test_verify_classifications_bundle_accepts_settled_accounting(tmp_path: Path) -> None:
    v = _verifier_stage_api()
    assert hasattr(v, "verify_origin_a_fixture_v2_classifications_bundle")
    bundle = _task3_valid_bundle()
    # Seed originals with bytes that match pinned digests only for empty; remap others
    # to actual placeholder hashes for this isolated unit fixture.
    originals_root = tmp_path / "private"
    remapped: dict[str, str] = {}
    for relative, digest in bundle["expected_originals"].items():
        path = originals_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if digest == _EMPTY:
            path.write_bytes(b"")
            remapped[relative] = _EMPTY
        else:
            path.write_bytes(f"unit-original:{relative}\n".encode())
            remapped[relative] = sha256_file(path)
    # Rewrite evidence + supersedes to remapped digests while preserving structure.
    a1 = dict(bundle["origin_a_1_correlation"])
    a1["evidence"] = [
        _ev(item["relative_path"], remapped[item["relative_path"]])
        for item in a1["evidence"]
    ]
    a1["supersedes_sha256"] = remapped["attempts/origin-a-1/attempt-manifest.json"]
    a2c = dict(bundle["origin_a_2_correlation"])
    a2c["evidence"] = [
        _ev(item["relative_path"], remapped[item["relative_path"]])
        for item in a2c["evidence"]
    ]
    a2c["supersedes_sha256"] = remapped["attempts/origin-a-2/attempt-manifest.json"]
    a2p = dict(bundle["origin_a_2_prompt"])
    a2p["evidence"] = [
        _ev("attempts/origin-a-2/phase-observation.json", remapped["attempts/origin-a-2/phase-observation.json"])
    ]
    a2p["supersedes_sha256"] = remapped["attempts/origin-a-2/phase-observation.json"]
    client = dict(bundle["origin_a_2_client"])
    client["supersedes_sha256"] = remapped["attempts/origin-a-2/attempt-manifest.json"]
    client["evidence"] = [
        _ev("event-facts/origin-a-2-exception-0xc0000409", remapped["attempts/origin-a-2/attempt-manifest.json"])
    ]
    ledger = {
        "schema": "plan117-custody-stage-ledger-v1",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "records": [a1, a2c, a2p],
        "next_correlation_ordinal": 3,
        "next_prompt_ordinal": 2,
    }
    summary = v.verify_origin_a_fixture_v2_classifications_bundle(
        origin_a_1_correlation=a1,
        origin_a_2_correlation=a2c,
        origin_a_2_prompt=a2p,
        origin_a_2_client=client,
        stage_ledger=ledger,
        originals_root=originals_root,
        expected_original_sha256=remapped,
    )
    assert summary["disposition_claimed"] is False
    assert summary["next_correlation_ordinal"] == 3
    assert summary["next_prompt_ordinal"] == 2
    assert "feasible" not in str(summary.get("disposition", "")).lower()
    assert "infeasible" not in str(summary.get("disposition", "")).lower()


def test_verify_classifications_rejects_falsely_restored_correlation_slot(
    tmp_path: Path,
) -> None:
    v = _verifier_stage_api()
    bundle = _task3_valid_bundle()
    originals_root = tmp_path / "private"
    remapped: dict[str, str] = {}
    for relative, digest in bundle["expected_originals"].items():
        path = originals_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if digest == _EMPTY:
            path.write_bytes(b"")
            remapped[relative] = _EMPTY
        else:
            path.write_bytes(f"unit-original:{relative}\n".encode())
            remapped[relative] = sha256_file(path)

    def _remap_stage(payload: dict[str, Any], supersede_key: str) -> dict[str, Any]:
        out = dict(payload)
        out["evidence"] = [
            _ev(item["relative_path"], remapped[item["relative_path"]])
            for item in payload["evidence"]
            if item["relative_path"] in remapped
        ]
        out["supersedes_sha256"] = remapped[supersede_key]
        return out

    a1 = _remap_stage(
        bundle["origin_a_1_correlation"], "attempts/origin-a-1/attempt-manifest.json"
    )
    a1["status"] = "succeeded"
    a1["failure_class"] = "none"
    a1["reason_code"] = None
    a2c = _remap_stage(
        bundle["origin_a_2_correlation"], "attempts/origin-a-2/attempt-manifest.json"
    )
    a2p = _remap_stage(
        bundle["origin_a_2_prompt"], "attempts/origin-a-2/phase-observation.json"
    )
    client = dict(bundle["origin_a_2_client"])
    client["supersedes_sha256"] = remapped["attempts/origin-a-2/attempt-manifest.json"]
    client["evidence"] = [
        _ev("event-facts/x", remapped["attempts/origin-a-2/attempt-manifest.json"])
    ]
    ledger = {
        "schema": "plan117-custody-stage-ledger-v1",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "records": [a1, a2c, a2p],
        "next_correlation_ordinal": 3,
        "next_prompt_ordinal": 2,
    }
    with pytest.raises(CustodyContractError) as exc:
        v.verify_origin_a_fixture_v2_classifications_bundle(
            origin_a_1_correlation=a1,
            origin_a_2_correlation=a2c,
            origin_a_2_prompt=a2p,
            origin_a_2_client=client,
            stage_ledger=ledger,
            originals_root=originals_root,
            expected_original_sha256=remapped,
        )
    assert exc.value.reason_code in {
        "invalid_probe_attempt_supersession_chain",
        "invalid_probe_stage_accounting",
        "invalid_probe_relay_capture_tooling_failure",
    }


def test_verify_classifications_rejects_missing_crash_fact(tmp_path: Path) -> None:
    v = _verifier_stage_api()
    bundle = _task3_valid_bundle()
    originals_root = tmp_path / "private"
    remapped: dict[str, str] = {}
    for relative, digest in bundle["expected_originals"].items():
        path = originals_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if digest == _EMPTY:
            path.write_bytes(b"")
            remapped[relative] = _EMPTY
        else:
            path.write_bytes(f"unit-original:{relative}\n".encode())
            remapped[relative] = sha256_file(path)

    def _remap_stage(payload: dict[str, Any], supersede_key: str) -> dict[str, Any]:
        out = dict(payload)
        out["evidence"] = [
            _ev(item["relative_path"], remapped[item["relative_path"]])
            for item in payload["evidence"]
            if item["relative_path"] in remapped
        ]
        out["supersedes_sha256"] = remapped[supersede_key]
        return out

    a1 = _remap_stage(
        bundle["origin_a_1_correlation"], "attempts/origin-a-1/attempt-manifest.json"
    )
    a2c = _remap_stage(
        bundle["origin_a_2_correlation"], "attempts/origin-a-2/attempt-manifest.json"
    )
    a2p = _remap_stage(
        bundle["origin_a_2_prompt"], "attempts/origin-a-2/phase-observation.json"
    )
    ledger = {
        "schema": "plan117-custody-stage-ledger-v1",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "records": [a1, a2c, a2p],
        "next_correlation_ordinal": 3,
        "next_prompt_ordinal": 2,
    }
    with pytest.raises(CustodyContractError) as exc:
        v.verify_origin_a_fixture_v2_classifications_bundle(
            origin_a_1_correlation=a1,
            origin_a_2_correlation=a2c,
            origin_a_2_prompt=a2p,
            origin_a_2_client=None,
            stage_ledger=ledger,
            originals_root=originals_root,
            expected_original_sha256=remapped,
        )
    assert exc.value.reason_code == "invalid_probe_attempt_supersession_chain"


def test_verify_classifications_rejects_changed_original_hash(tmp_path: Path) -> None:
    v = _verifier_stage_api()
    bundle = _task3_valid_bundle()
    originals_root = tmp_path / "private"
    remapped: dict[str, str] = {}
    for relative, digest in bundle["expected_originals"].items():
        path = originals_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if digest == _EMPTY:
            path.write_bytes(b"")
            remapped[relative] = _EMPTY
        else:
            path.write_bytes(f"unit-original:{relative}\n".encode())
            remapped[relative] = sha256_file(path)

    def _remap_stage(payload: dict[str, Any], supersede_key: str) -> dict[str, Any]:
        out = dict(payload)
        out["evidence"] = [
            _ev(item["relative_path"], remapped[item["relative_path"]])
            for item in payload["evidence"]
            if item["relative_path"] in remapped
        ]
        out["supersedes_sha256"] = remapped[supersede_key]
        return out

    a1 = _remap_stage(
        bundle["origin_a_1_correlation"], "attempts/origin-a-1/attempt-manifest.json"
    )
    a2c = _remap_stage(
        bundle["origin_a_2_correlation"], "attempts/origin-a-2/attempt-manifest.json"
    )
    a2p = _remap_stage(
        bundle["origin_a_2_prompt"], "attempts/origin-a-2/phase-observation.json"
    )
    client = dict(bundle["origin_a_2_client"])
    client["supersedes_sha256"] = remapped["attempts/origin-a-2/attempt-manifest.json"]
    client["evidence"] = [
        _ev("event-facts/x", remapped["attempts/origin-a-2/attempt-manifest.json"])
    ]
    ledger = {
        "schema": "plan117-custody-stage-ledger-v1",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "records": [a1, a2c, a2p],
        "next_correlation_ordinal": 3,
        "next_prompt_ordinal": 2,
    }
    bad_expected = dict(remapped)
    bad_expected["attempts/origin-a-1/attempt-manifest.json"] = "0" * 64
    with pytest.raises(CustodyContractError) as exc:
        v.verify_origin_a_fixture_v2_classifications_bundle(
            origin_a_1_correlation=a1,
            origin_a_2_correlation=a2c,
            origin_a_2_prompt=a2p,
            origin_a_2_client=client,
            stage_ledger=ledger,
            originals_root=originals_root,
            expected_original_sha256=bad_expected,
        )
    assert exc.value.reason_code == "invalid_probe_origin_attempt_original_mismatch"


def test_verify_classifications_rejects_replaced_original_file(tmp_path: Path) -> None:
    v = _verifier_stage_api()
    bundle = _task3_valid_bundle()
    originals_root = tmp_path / "private"
    remapped: dict[str, str] = {}
    for relative, digest in bundle["expected_originals"].items():
        path = originals_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if digest == _EMPTY:
            path.write_bytes(b"")
            remapped[relative] = _EMPTY
        else:
            path.write_bytes(f"unit-original:{relative}\n".encode())
            remapped[relative] = sha256_file(path)

    def _remap_stage(payload: dict[str, Any], supersede_key: str) -> dict[str, Any]:
        out = dict(payload)
        out["evidence"] = [
            _ev(item["relative_path"], remapped[item["relative_path"]])
            for item in payload["evidence"]
            if item["relative_path"] in remapped
        ]
        out["supersedes_sha256"] = remapped[supersede_key]
        return out

    a1 = _remap_stage(
        bundle["origin_a_1_correlation"], "attempts/origin-a-1/attempt-manifest.json"
    )
    a2c = _remap_stage(
        bundle["origin_a_2_correlation"], "attempts/origin-a-2/attempt-manifest.json"
    )
    a2p = _remap_stage(
        bundle["origin_a_2_prompt"], "attempts/origin-a-2/phase-observation.json"
    )
    client = dict(bundle["origin_a_2_client"])
    client["supersedes_sha256"] = remapped["attempts/origin-a-2/attempt-manifest.json"]
    client["evidence"] = [
        _ev("event-facts/x", remapped["attempts/origin-a-2/attempt-manifest.json"])
    ]
    ledger = {
        "schema": "plan117-custody-stage-ledger-v1",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "records": [a1, a2c, a2p],
        "next_correlation_ordinal": 3,
        "next_prompt_ordinal": 2,
    }
    # Replace an original after the expected digest was captured.
    replaced = originals_root / "attempts/origin-a-2/attempt-manifest.json"
    replaced.write_bytes(b'{"tampered":true}\n')
    with pytest.raises(CustodyContractError) as exc:
        v.verify_origin_a_fixture_v2_classifications_bundle(
            origin_a_1_correlation=a1,
            origin_a_2_correlation=a2c,
            origin_a_2_prompt=a2p,
            origin_a_2_client=client,
            stage_ledger=ledger,
            originals_root=originals_root,
            expected_original_sha256=remapped,
        )
    assert exc.value.reason_code == "invalid_probe_origin_attempt_original_mismatch"


def test_verify_classifications_rejects_prompt_only_origin_a1(tmp_path: Path) -> None:
    v = _verifier_stage_api()
    bundle = _task3_valid_bundle()
    originals_root = tmp_path / "private"
    remapped: dict[str, str] = {}
    for relative, digest in bundle["expected_originals"].items():
        path = originals_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if digest == _EMPTY:
            path.write_bytes(b"")
            remapped[relative] = _EMPTY
        else:
            path.write_bytes(f"unit-original:{relative}\n".encode())
            remapped[relative] = sha256_file(path)

    a1_prompt_only = _task3_stage_payload(
        record_id="origin-a-1-prompt",
        run_attempt_id="origin-a-1",
        stage="post_new_prompt",
        ordinal=1,
        status="failed",
        failure_class="permanent",
        reason_code="AMBIGUOUS_WORKSPACE_REFERENCE",
        evidence=[
            _ev(
                "attempts/origin-a-1/phase-observation.json",
                remapped["attempts/origin-a-1/phase-observation.json"],
            )
        ],
        supersedes_record_id="origin-a-1-original-observation",
        supersedes_sha256=remapped["attempts/origin-a-1/phase-observation.json"],
    )
    a2c = dict(bundle["origin_a_2_correlation"])
    a2c["evidence"] = [
        _ev(item["relative_path"], remapped[item["relative_path"]])
        for item in a2c["evidence"]
    ]
    a2c["supersedes_sha256"] = remapped["attempts/origin-a-2/attempt-manifest.json"]
    a2p = dict(bundle["origin_a_2_prompt"])
    a2p["evidence"] = [
        _ev(
            "attempts/origin-a-2/phase-observation.json",
            remapped["attempts/origin-a-2/phase-observation.json"],
        )
    ]
    a2p["supersedes_sha256"] = remapped["attempts/origin-a-2/phase-observation.json"]
    # Gap in correlation ordinals (missing 1) — ledger must fail.
    ledger = {
        "schema": "plan117-custody-stage-ledger-v1",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "records": [a1_prompt_only, a2c, a2p],
        "next_correlation_ordinal": 3,
        "next_prompt_ordinal": 3,
    }
    client = dict(bundle["origin_a_2_client"])
    client["supersedes_sha256"] = remapped["attempts/origin-a-2/attempt-manifest.json"]
    client["evidence"] = [
        _ev("event-facts/x", remapped["attempts/origin-a-2/attempt-manifest.json"])
    ]
    with pytest.raises(CustodyContractError) as exc:
        v.verify_origin_a_fixture_v2_classifications_bundle(
            origin_a_1_correlation=a1_prompt_only,
            origin_a_2_correlation=a2c,
            origin_a_2_prompt=a2p,
            origin_a_2_client=client,
            stage_ledger=ledger,
            originals_root=originals_root,
            expected_original_sha256=remapped,
        )
    assert exc.value.reason_code in {
        "invalid_probe_stage_accounting",
        "invalid_probe_attempt_supersession_chain",
    }


def test_verify_classifications_rejects_missing_origin_a2_correlation_success(
    tmp_path: Path,
) -> None:
    v = _verifier_stage_api()
    bundle = _task3_valid_bundle()
    originals_root = tmp_path / "private"
    remapped: dict[str, str] = {}
    for relative, digest in bundle["expected_originals"].items():
        path = originals_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if digest == _EMPTY:
            path.write_bytes(b"")
            remapped[relative] = _EMPTY
        else:
            path.write_bytes(f"unit-original:{relative}\n".encode())
            remapped[relative] = sha256_file(path)

    a1 = dict(bundle["origin_a_1_correlation"])
    a1["evidence"] = [
        _ev(item["relative_path"], remapped[item["relative_path"]])
        for item in a1["evidence"]
    ]
    a1["supersedes_sha256"] = remapped["attempts/origin-a-1/attempt-manifest.json"]
    a2_failed = dict(bundle["origin_a_2_correlation"])
    a2_failed["status"] = "failed"
    a2_failed["failure_class"] = "permanent"
    a2_failed["reason_code"] = "invalid_probe_relay_capture_tooling_failure"
    a2_failed["evidence"] = [
        _ev(item["relative_path"], remapped[item["relative_path"]])
        for item in a2_failed["evidence"]
    ]
    a2_failed["supersedes_sha256"] = remapped["attempts/origin-a-2/attempt-manifest.json"]
    a2p = dict(bundle["origin_a_2_prompt"])
    a2p["evidence"] = [
        _ev(
            "attempts/origin-a-2/phase-observation.json",
            remapped["attempts/origin-a-2/phase-observation.json"],
        )
    ]
    a2p["supersedes_sha256"] = remapped["attempts/origin-a-2/phase-observation.json"]
    client = dict(bundle["origin_a_2_client"])
    client["supersedes_sha256"] = remapped["attempts/origin-a-2/attempt-manifest.json"]
    client["evidence"] = [
        _ev("event-facts/x", remapped["attempts/origin-a-2/attempt-manifest.json"])
    ]
    ledger = {
        "schema": "plan117-custody-stage-ledger-v1",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "records": [a1, a2_failed, a2p],
        "next_correlation_ordinal": 3,
        "next_prompt_ordinal": 2,
    }
    with pytest.raises(CustodyContractError) as exc:
        v.verify_origin_a_fixture_v2_classifications_bundle(
            origin_a_1_correlation=a1,
            origin_a_2_correlation=a2_failed,
            origin_a_2_prompt=a2p,
            origin_a_2_client=client,
            stage_ledger=ledger,
            originals_root=originals_root,
            expected_original_sha256=remapped,
        )
    assert exc.value.reason_code in {
        "invalid_probe_attempt_supersession_chain",
        "invalid_probe_stage_accounting",
    }


def test_verify_classifications_rejects_ledger_allocating_origin_a4(tmp_path: Path) -> None:
    v = _verifier_stage_api()
    bundle = _task3_valid_bundle()
    originals_root = tmp_path / "private"
    remapped: dict[str, str] = {}
    for relative, digest in bundle["expected_originals"].items():
        path = originals_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if digest == _EMPTY:
            path.write_bytes(b"")
            remapped[relative] = _EMPTY
        else:
            path.write_bytes(f"unit-original:{relative}\n".encode())
            remapped[relative] = sha256_file(path)

    a1 = dict(bundle["origin_a_1_correlation"])
    a1["evidence"] = [
        _ev(item["relative_path"], remapped[item["relative_path"]])
        for item in a1["evidence"]
    ]
    a1["supersedes_sha256"] = remapped["attempts/origin-a-1/attempt-manifest.json"]
    a2c = dict(bundle["origin_a_2_correlation"])
    a2c["evidence"] = [
        _ev(item["relative_path"], remapped[item["relative_path"]])
        for item in a2c["evidence"]
    ]
    a2c["supersedes_sha256"] = remapped["attempts/origin-a-2/attempt-manifest.json"]
    a2p = dict(bundle["origin_a_2_prompt"])
    a2p["evidence"] = [
        _ev(
            "attempts/origin-a-2/phase-observation.json",
            remapped["attempts/origin-a-2/phase-observation.json"],
        )
    ]
    a2p["supersedes_sha256"] = remapped["attempts/origin-a-2/phase-observation.json"]
    a3 = _task3_stage_payload(
        record_id="origin-a-3-correlation",
        run_attempt_id="origin-a-3",
        stage="correlation_capture",
        ordinal=3,
        status="succeeded",
        failure_class="none",
        reason_code=None,
        evidence=[_ev("attempts/origin-a-3/attempt-manifest.json", remapped["attempts/origin-a-2/attempt-manifest.json"])],
        supersedes_record_id="origin-a-3-reservation",
        supersedes_sha256=remapped["attempts/origin-a-2/attempt-manifest.json"],
    )
    a4 = _task3_stage_payload(
        record_id="origin-a-4-correlation",
        run_attempt_id="origin-a-4",
        stage="correlation_capture",
        ordinal=4,
        status="succeeded",
        failure_class="none",
        reason_code=None,
        evidence=[_ev("attempts/origin-a-4/attempt-manifest.json", remapped["attempts/origin-a-2/attempt-manifest.json"])],
        supersedes_record_id="origin-a-4-reservation",
        supersedes_sha256=remapped["attempts/origin-a-2/attempt-manifest.json"],
    )
    client = dict(bundle["origin_a_2_client"])
    client["supersedes_sha256"] = remapped["attempts/origin-a-2/attempt-manifest.json"]
    client["evidence"] = [
        _ev("event-facts/x", remapped["attempts/origin-a-2/attempt-manifest.json"])
    ]
    ledger = {
        "schema": "plan117-custody-stage-ledger-v1",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "records": [a1, a2c, a2p, a3, a4],
        "next_correlation_ordinal": 5,
        "next_prompt_ordinal": 2,
    }
    with pytest.raises(CustodyContractError) as exc:
        v.verify_origin_a_fixture_v2_classifications_bundle(
            origin_a_1_correlation=a1,
            origin_a_2_correlation=a2c,
            origin_a_2_prompt=a2p,
            origin_a_2_client=client,
            stage_ledger=ledger,
            originals_root=originals_root,
            expected_original_sha256=remapped,
        )
    assert exc.value.reason_code == "invalid_probe_retry_budget_exhausted"


def test_cli_origin_a_fixture_v2_classifications_checkpoint_choice() -> None:
    """argparse must accept the Task 3 classifications checkpoint name."""
    parser_src = (ROOT / "tools" / "verify_plan117_custody_feasibility.py").read_text(
        encoding="utf-8"
    )
    assert "origin-a-fixture-v2-classifications" in parser_src
    assert "verify_origin_a_fixture_v2_classifications" in parser_src

# --- Origin-A fixture v2 Task 4: execution-preflight checkpoint ---


def _valid_execution_preflight_payload(
    *,
    head: str,
    files: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema": "plan117-origin-a-fixture-v2-execution-preflight-v1",
        "amendment_sha256": AMENDMENT_SHA256,
        "branch": "agent/cursor/p11-feat-zed-resume",
        "head": head,
        "intended_commit_subject": "test(acp): amend Plan 11.7 origin fixture accounting",
        "production_baseline": {
            "commit": "2cf2f42aa7d1072f09d0678a3c75eb43516c8808",
            "paths": ["src/optimus", "src/optimus_gateway"],
            "clean": True,
        },
        "fixture_pins": {
            "prompt_fixture_v2_sha256": PROMPT_V2_SHA256,
            "pyproject_target_sha256": PYPROJECT_SHA256,
        },
        "classifications": {
            "next_correlation_ordinal": 3,
            "next_prompt_ordinal": 2,
        },
        "files": files,
        "notes": {
            "live_launch": False,
            "settings_mutation": False,
            "feasibility_disposition_claimed": False,
        },
    }


def test_verify_execution_preflight_payload_accepts_matching_identity() -> None:
    v = _verifier_stage_api()
    assert hasattr(v, "verify_execution_preflight_payload")
    digest = "ab" * 32
    files = [
        {
            "path": path,
            "raw_file_sha256": digest,
            "git_blob_sha256": digest,
        }
        for path in v.EXECUTION_IDENTITY_PATHS
    ]
    actual = {
        path: {"raw_file_sha256": digest, "git_blob_sha256": digest}
        for path in v.EXECUTION_IDENTITY_PATHS
    }
    payload = _valid_execution_preflight_payload(head="abc123", files=files)
    v.verify_execution_preflight_payload(
        payload,
        actual_head="abc123",
        actual_files=actual,
        production_clean=True,
    )


def test_verify_execution_preflight_rejects_wrong_commit_digest() -> None:
    v = _verifier_stage_api()
    digest = "cd" * 32
    files = [
        {
            "path": path,
            "raw_file_sha256": digest,
            "git_blob_sha256": digest,
        }
        for path in v.EXECUTION_IDENTITY_PATHS
    ]
    actual = {
        path: {"raw_file_sha256": digest, "git_blob_sha256": digest}
        for path in v.EXECUTION_IDENTITY_PATHS
    }
    payload = _valid_execution_preflight_payload(head="deadbeef", files=files)
    with pytest.raises(CustodyContractError) as exc:
        v.verify_execution_preflight_payload(
            payload,
            actual_head="cafebabe",
            actual_files=actual,
            production_clean=True,
        )
    assert exc.value.reason_code == "invalid_probe_execution_identity_mismatch"
    assert exc.value.field_path == "head"


def test_verify_execution_preflight_rejects_dirty_execution_identity() -> None:
    v = _verifier_stage_api()
    clean = "11" * 32
    dirty = "22" * 32
    files = []
    actual: dict[str, dict[str, str]] = {}
    for index, path in enumerate(v.EXECUTION_IDENTITY_PATHS):
        if index == 0:
            files.append(
                {
                    "path": path,
                    "raw_file_sha256": dirty,
                    "git_blob_sha256": clean,
                }
            )
            actual[path] = {"raw_file_sha256": dirty, "git_blob_sha256": clean}
        else:
            files.append(
                {
                    "path": path,
                    "raw_file_sha256": clean,
                    "git_blob_sha256": clean,
                }
            )
            actual[path] = {"raw_file_sha256": clean, "git_blob_sha256": clean}
    payload = _valid_execution_preflight_payload(head="abc123", files=files)
    with pytest.raises(CustodyContractError) as exc:
        v.verify_execution_preflight_payload(
            payload,
            actual_head="abc123",
            actual_files=actual,
            production_clean=True,
        )
    assert exc.value.reason_code == "invalid_probe_execution_identity_mismatch"
    assert exc.value.field_path.endswith(".dirty")


def test_cli_origin_a_fixture_v2_preflight_checkpoint_choice() -> None:
    parser_src = (ROOT / "tools" / "verify_plan117_custody_feasibility.py").read_text(
        encoding="utf-8"
    )
    assert "origin-a-fixture-v2-preflight" in parser_src
    assert "verify_origin_a_fixture_v2_preflight" in parser_src
    assert "ORIGIN_A_FIXTURE_V2_PREFLIGHT_CHECKPOINT" in parser_src


def _a3_seal_valid_bundle(tmp_path: Path) -> dict[str, Any]:
    """Build a remapped Option-B seal bundle with seeded private originals."""
    v = _verifier_stage_api()
    assert hasattr(v, "verify_origin_a3_seal_bundle")
    base = _task3_valid_bundle()
    originals_root = tmp_path / "private"
    remapped: dict[str, str] = {}
    a3_paths = {
        "attempts/origin-a-3/attempt-manifest.json": b"a3-manifest\n",
        "attempts/origin-a-3/phase-observation.json": b"a3-phase\n",
        "origin-a-3/zed-to-agent.bin": b"a3-z2a",
        "origin-a-3/agent-to-zed.bin": b"a3-a2z",
        "origin-a-3/relay-index.ndjson": b"a3-index\n",
        "reservations/origin-a-3.json": b'{"run_attempt_id":"origin-a-3"}\n',
    }
    for relative, digest in base["expected_originals"].items():
        path = originals_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if digest == _EMPTY:
            path.write_bytes(b"")
            remapped[relative] = _EMPTY
        else:
            path.write_bytes(f"unit-original:{relative}\n".encode())
            remapped[relative] = sha256_file(path)
    for relative, payload in a3_paths.items():
        path = originals_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        remapped[relative] = sha256_file(path)

    def _remap_stage(payload: dict[str, Any], supersede_key: str) -> dict[str, Any]:
        out = dict(payload)
        out["evidence"] = [
            _ev(item["relative_path"], remapped[item["relative_path"]])
            for item in payload["evidence"]
            if item["relative_path"] in remapped
        ]
        out["supersedes_sha256"] = remapped[supersede_key]
        return out

    a1 = _remap_stage(
        base["origin_a_1_correlation"], "attempts/origin-a-1/attempt-manifest.json"
    )
    a2c = _remap_stage(
        base["origin_a_2_correlation"], "attempts/origin-a-2/attempt-manifest.json"
    )
    a2p = _remap_stage(
        base["origin_a_2_prompt"], "attempts/origin-a-2/phase-observation.json"
    )
    client = dict(base["origin_a_2_client"])
    client["supersedes_sha256"] = remapped["attempts/origin-a-2/attempt-manifest.json"]
    client["evidence"] = [
        _ev("event-facts/x", remapped["attempts/origin-a-2/attempt-manifest.json"])
    ]
    a3c = _task3_stage_payload(
        record_id="origin-a-3-correlation",
        run_attempt_id="origin-a-3",
        stage="correlation_capture",
        ordinal=3,
        status="succeeded",
        failure_class="none",
        reason_code=None,
        evidence=[
            _ev(
                "attempts/origin-a-3/attempt-manifest.json",
                remapped["attempts/origin-a-3/attempt-manifest.json"],
            ),
            _ev(
                "attempts/origin-a-3/phase-observation.json",
                remapped["attempts/origin-a-3/phase-observation.json"],
            ),
            _ev("origin-a-3/zed-to-agent.bin", remapped["origin-a-3/zed-to-agent.bin"]),
            _ev("origin-a-3/agent-to-zed.bin", remapped["origin-a-3/agent-to-zed.bin"]),
            _ev(
                "origin-a-3/relay-index.ndjson",
                remapped["origin-a-3/relay-index.ndjson"],
            ),
            _ev(
                "reservations/origin-a-3.json",
                remapped["reservations/origin-a-3.json"],
            ),
        ],
        supersedes_record_id="origin-a-3-original-manifest",
        supersedes_sha256=remapped["attempts/origin-a-3/attempt-manifest.json"],
        notes={"reservation_present": True},
    )
    a3c["created_by"] = "plan117-origin-a3-seal-b"
    exchange_digest = remapped["origin-a-3/zed-to-agent.bin"]
    a3p = _task3_stage_payload(
        record_id="origin-a-3-prompt-2",
        run_attempt_id="origin-a-3",
        stage="post_new_prompt",
        ordinal=2,
        status="failed",
        failure_class="transient",
        reason_code="transient_capture",
        evidence=[
            _ev("origin-a-3/zed-to-agent.bin", remapped["origin-a-3/zed-to-agent.bin"]),
            _ev("origin-a-3/agent-to-zed.bin", remapped["origin-a-3/agent-to-zed.bin"]),
            _ev(
                "origin-a-3/relay-index.ndjson",
                remapped["origin-a-3/relay-index.ndjson"],
            ),
            _ev(
                "reports/plan-11-7-server-custody-artifacts/amendments/"
                "origin-a-fixture-v2/origin-a-3-exchange-facts.json",
                exchange_digest,
            ),
        ],
        supersedes_record_id="origin-a-3-original-observation",
        supersedes_sha256=remapped["attempts/origin-a-3/phase-observation.json"],
        notes={"loop_stop": "PLANNING_UNPARSEABLE_RESPONSE"},
    )
    a3p["created_by"] = "plan117-origin-a3-seal-b"
    ungated = {
        "schema": "plan117-custody-supplemental-fact-record-v1",
        "record_id": "origin-a-3-ungated-reprompt",
        "run_attempt_id": "origin-a-3",
        "fact_kind": "out_of_band_same_session_reprompt",
        "reason_code": "invalid_probe_stage_accounting",
        "evidence": [
            _ev("origin-a-3/zed-to-agent.bin", remapped["origin-a-3/zed-to-agent.bin"]),
            _ev("origin-a-3/agent-to-zed.bin", remapped["origin-a-3/agent-to-zed.bin"]),
            _ev(
                "reports/plan-11-7-server-custody-artifacts/amendments/"
                "origin-a-fixture-v2/origin-a-3-exchange-facts.json",
                exchange_digest,
            ),
        ],
        "supersedes_record_id": "origin-a-3-ungated-reprompt-label",
        "supersedes_sha256": remapped["origin-a-3/zed-to-agent.bin"],
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "created_by": "plan117-origin-a3-seal-b",
        "created_utc": "2026-08-02T20:03:37Z",
        "classification_notes": {
            "does_not_consume_prompt_ordinal_3": True,
            "origin_a_prompt_retry_gate_invoked": False,
        },
    }
    ledger = {
        "schema": "plan117-custody-stage-ledger-v1",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "records": [a1, a2c, a2p, a3c, a3p],
        "next_correlation_ordinal": 4,
        "next_prompt_ordinal": 3,
        "derived_from": [
            "origin-a-1-correlation",
            "origin-a-2-correlation",
            "origin-a-2-prompt",
            "origin-a-3-correlation",
            "origin-a-3-prompt-2",
        ],
    }
    seal_b = {
        "schema": "plan117-origin-a-3-seal-b-v1",
        "option": "B",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "ending": {
            "corrected_origin_a_dod_success": False,
            "feasibility_disposition_claimed": False,
            "budget_expansion_required_for_clean_relaunch": True,
            "same_session_ordinal_3_not_consumed": True,
        },
        "derived_ordinals": {
            "next_correlation_ordinal": 4,
            "next_prompt_ordinal": 3,
        },
        "classifications": {
            "correlation_ordinal_3": "succeeded",
            "prompt_ordinal_2": "failed_transient",
            "prompt_ordinal_3": "unclaimed_not_authorized",
            "dcacf89a_exchange": "supplemental_out_of_band_same_session_reprompt",
        },
    }
    exchange_facts = {
        "schema": "plan117-origin-a-3-exchange-facts-v1",
        "run_attempt_id": "origin-a-3",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "notes": {
            "origin_a_prompt_retry_gate_invoked": False,
            "third_prompt_authorized": False,
        },
        "exchanges": [
            {
                "classification_role": "prompt_ordinal_2_candidate",
                "rpc_id": "ada61949-a060-4593-adf6-b56474b40d16",
            },
            {
                "classification_role": "out_of_band_same_session_reprompt_not_ordinal_3",
                "rpc_id": "dcacf89a-7c51-4f5b-a6b7-c8f67e7f4bc6",
            },
        ],
    }
    restore = {
        "schema": "plan117-origin-a-3-settings-restore-evidence-v1",
        "transaction_restored": True,
        "continue_flag_created": True,
        "completed_restore": {
            "matches_approved_preimage": True,
            "final_sha256": (
                "DA99A0CDC4381092E4927A21CEC5217D0249D214969515F1022228DBA1D3A1F5"
            ),
            "method": "rename_away_then_replace",
        },
    }
    return {
        "origin_a_1_correlation": a1,
        "origin_a_2_correlation": a2c,
        "origin_a_2_prompt": a2p,
        "origin_a_2_client": client,
        "origin_a_3_correlation": a3c,
        "origin_a_3_prompt_2": a3p,
        "origin_a_3_ungated_reprompt": ungated,
        "stage_ledger": ledger,
        "seal_b": seal_b,
        "exchange_facts": exchange_facts,
        "restore_evidence": restore,
        "originals_root": originals_root,
        "expected_originals": remapped,
    }


def test_verify_origin_a3_seal_bundle_accepts_option_b(tmp_path: Path) -> None:
    v = _verifier_stage_api()
    bundle = _a3_seal_valid_bundle(tmp_path)
    summary = v.verify_origin_a3_seal_bundle(
        origin_a_1_correlation=bundle["origin_a_1_correlation"],
        origin_a_2_correlation=bundle["origin_a_2_correlation"],
        origin_a_2_prompt=bundle["origin_a_2_prompt"],
        origin_a_2_client=bundle["origin_a_2_client"],
        origin_a_3_correlation=bundle["origin_a_3_correlation"],
        origin_a_3_prompt_2=bundle["origin_a_3_prompt_2"],
        origin_a_3_ungated_reprompt=bundle["origin_a_3_ungated_reprompt"],
        stage_ledger=bundle["stage_ledger"],
        seal_b=bundle["seal_b"],
        exchange_facts=bundle["exchange_facts"],
        restore_evidence=bundle["restore_evidence"],
        originals_root=bundle["originals_root"],
        expected_original_sha256=bundle["expected_originals"],
    )
    assert summary["next_correlation_ordinal"] == 4
    assert summary["next_prompt_ordinal"] == 3
    assert summary["disposition_claimed"] is False
    assert summary["corrected_origin_a_dod_success"] is False
    assert summary["ending_option"] == "B"
    assert summary["settings_restored"] is True


def test_verify_origin_a3_seal_bundle_rejects_dod_success_claim(tmp_path: Path) -> None:
    v = _verifier_stage_api()
    bundle = _a3_seal_valid_bundle(tmp_path)
    seal = dict(bundle["seal_b"])
    ending = dict(seal["ending"])
    ending["corrected_origin_a_dod_success"] = True
    seal["ending"] = ending
    with pytest.raises(CustodyContractError) as exc:
        v.verify_origin_a3_seal_bundle(
            origin_a_1_correlation=bundle["origin_a_1_correlation"],
            origin_a_2_correlation=bundle["origin_a_2_correlation"],
            origin_a_2_prompt=bundle["origin_a_2_prompt"],
            origin_a_2_client=bundle["origin_a_2_client"],
            origin_a_3_correlation=bundle["origin_a_3_correlation"],
            origin_a_3_prompt_2=bundle["origin_a_3_prompt_2"],
            origin_a_3_ungated_reprompt=bundle["origin_a_3_ungated_reprompt"],
            stage_ledger=bundle["stage_ledger"],
            seal_b=seal,
            exchange_facts=bundle["exchange_facts"],
            restore_evidence=bundle["restore_evidence"],
            originals_root=bundle["originals_root"],
            expected_original_sha256=bundle["expected_originals"],
        )
    assert exc.value.reason_code == "invalid_probe_stage_accounting"


def test_verify_origin_a3_seal_bundle_rejects_unrestored_settings(tmp_path: Path) -> None:
    v = _verifier_stage_api()
    bundle = _a3_seal_valid_bundle(tmp_path)
    restore = dict(bundle["restore_evidence"])
    restore["transaction_restored"] = False
    with pytest.raises(CustodyContractError) as exc:
        v.verify_origin_a3_seal_bundle(
            origin_a_1_correlation=bundle["origin_a_1_correlation"],
            origin_a_2_correlation=bundle["origin_a_2_correlation"],
            origin_a_2_prompt=bundle["origin_a_2_prompt"],
            origin_a_2_client=bundle["origin_a_2_client"],
            origin_a_3_correlation=bundle["origin_a_3_correlation"],
            origin_a_3_prompt_2=bundle["origin_a_3_prompt_2"],
            origin_a_3_ungated_reprompt=bundle["origin_a_3_ungated_reprompt"],
            stage_ledger=bundle["stage_ledger"],
            seal_b=bundle["seal_b"],
            exchange_facts=bundle["exchange_facts"],
            restore_evidence=restore,
            originals_root=bundle["originals_root"],
            expected_original_sha256=bundle["expected_originals"],
        )
    assert exc.value.reason_code == "settings_not_restored"


def test_cli_origin_a3_and_final_checkpoint_choices() -> None:
    parser_src = (ROOT / "tools" / "verify_plan117_custody_feasibility.py").read_text(
        encoding="utf-8"
    )
    assert "origin-a-3" in parser_src
    assert "origin-a-fixture-v2-final" in parser_src
    assert "verify_origin_a3" in parser_src
    assert "verify_origin_a_fixture_v2_final" in parser_src


# --- Plan 11.7 retry-preflight Task 4: offline proof verification + tampers ---


_RETRY_PROOF_EVIDENCE = "c" * 64
_RETRY_DEBUG_DIGEST = "d" * 64
_RETRY_RELAY_DIGEST = "e" * 64


def _retry_offline_api() -> Any:
    required = (
        "verify_retry_preflight_offline",
        "RETRY_OUTCOME_UNAVAILABLE_PROOF",
        "RETRY_OUTCOME_IDENTITY_MISMATCH",
        "RETRY_OUTCOME_CONTROL_FAILURE",
        "RETRY_OUTCOME_SECOND_PROMPT_FAILURE",
        "RETRY_OUTCOME_ACCEPTED_SAME_SESSION_RETRY",
    )
    missing = [name for name in required if not hasattr(verifier_mod, name)]
    if missing:
        pytest.fail(f"missing retry offline verifier API: {missing}")
    return verifier_mod


def _retry_launch_identity(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "plan117-custody-launch-session-identity-v1",
        "run_attempt_id": "origin-a-3",
        "zed_pid": 4242,
        "zed_process_start_time_utc": "2026-08-04T12:00:00Z",
        "connection_id": "conn-origin-a-3",
        "acp_session_id": "sess-origin-a-3",
    }
    payload.update(overrides)
    return payload


def _retry_control_descriptor(**overrides: Any) -> dict[str, Any]:
    from tools.plan117_custody_relay import _descriptor_sha256

    payload: dict[str, Any] = {
        "schema": "plan117-custody-relay-control-descriptor-v1",
        "run_attempt_id": "origin-a-3",
        "endpoint_kind": "af_pipe",
        "endpoint_path": r"\\.\pipe\plan117-origin-a-3-control",
        "connection_id": "conn-origin-a-3",
        "owner_id": "operator-test",
        "terminal": False,
        "prompt_sealed": False,
    }
    payload.update(overrides)
    payload.pop("descriptor_sha256", None)
    payload["descriptor_sha256"] = _descriptor_sha256(payload)
    return payload


def _retry_proof_payload(**overrides: Any) -> dict[str, Any]:
    from tools.plan117_custody_contract import (
        EvidenceReference,
        build_live_session_proof,
        live_session_proof_payload,
    )

    evidence = (
        EvidenceReference(
            relative_path="attempts/origin-a-3/relay-index.ndjson",
            sha256=_RETRY_PROOF_EVIDENCE,
            hash_method="raw_file_sha256",
        ),
    )
    proof = build_live_session_proof(
        run_attempt_id="origin-a-3",
        zed_pid=4242,
        zed_process_start_time_utc="2026-08-04T12:00:00Z",
        connection_id="conn-origin-a-3",
        acp_session_id="sess-origin-a-3",
        zed_alive=True,
        relay_alive=True,
        acp_session_observed=True,
        captured_utc="2026-08-04T12:05:00Z",
        evidence=evidence,
    )
    payload = live_session_proof_payload(proof)
    payload["schema"] = "plan117-custody-live-session-proof-v1"
    payload["proof_sha256"] = proof.proof_sha256
    payload["live_attestation"] = True
    payload.update(overrides)
    if "proof_sha256" not in overrides and set(overrides) - {"schema", "live_attestation"}:
        # Caller changed digest-bound fields without supplying a digest: leave stale digest
        # so the verifier can reject recomputation mismatch unless they override digest too.
        pass
    return payload


def _retry_ready_ledger_payload(*, next_prompt_ordinal: int = 3) -> dict[str, Any]:
    a3c = _task3_stage_payload(
        record_id="origin-a-3-correlation",
        run_attempt_id="origin-a-3",
        stage="correlation_capture",
        ordinal=3,
        status="succeeded",
        failure_class="none",
        reason_code=None,
        evidence=[_ev("attempts/origin-a-3/attempt-manifest.json", "a" * 64)],
        supersedes_record_id="origin-a-3-reservation",
        supersedes_sha256="b" * 64,
    )
    a3p = _task3_stage_payload(
        record_id="origin-a-3-prompt-2",
        run_attempt_id="origin-a-3",
        stage="post_new_prompt",
        ordinal=2,
        status="failed",
        failure_class="transient",
        reason_code="transient_capture",
        evidence=[_ev("origin-a-3/relay-index.ndjson", "a" * 64)],
        supersedes_record_id="origin-a-3-original-observation",
        supersedes_sha256="b" * 64,
    )
    return {
        "schema": "plan117-custody-stage-ledger-v1",
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "records": [a3c, a3p],
        "next_correlation_ordinal": 4,
        "next_prompt_ordinal": next_prompt_ordinal,
    }


def _retry_prompt_outcome(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "plan117-custody-stage-attempt-record-v1",
        "record_id": "origin-a-3-prompt-3",
        "run_attempt_id": "origin-a-3",
        "stage": "post_new_prompt",
        "ordinal": 3,
        "status": "succeeded",
        "failure_class": "none",
        "reason_code": None,
        "evidence": [
            _ev("attempts/origin-a-3/live-session-proof.json", "f" * 64),
            _ev("reservations/origin-a-3-prompt-3.json", "1" * 64),
        ],
        "supersedes_record_id": "origin-a-3-prompt-2",
        "supersedes_sha256": "2" * 64,
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "created_by": "plan117-origin-a-prompt-retry",
        "created_utc": "2026-08-04T12:06:00Z",
        "settings_mutated": False,
        "zed_launched": False,
    }
    payload.update(overrides)
    return payload


def _retry_debug_corroboration(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "plan117-custody-debug-corroboration-v1",
        "run_attempt_id": "origin-a-3",
        "connection_id": "conn-origin-a-3",
        "acp_session_id": "sess-origin-a-3",
        "debug_relative_path": "attempts/origin-a-3/debug-acp.ndjson",
        "debug_sha256": _RETRY_DEBUG_DIGEST,
        "session_new_observed": True,
    }
    payload.update(overrides)
    return payload


def _retry_relay_session_evidence(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "plan117-custody-relay-session-evidence-v1",
        "run_attempt_id": "origin-a-3",
        "connection_id": "conn-origin-a-3",
        "acp_session_id": "sess-origin-a-3",
        "relay_index_relative_path": "origin-a-3/relay-index.ndjson",
        "relay_index_sha256": _RETRY_RELAY_DIGEST,
        "session_new_observed": True,
    }
    payload.update(overrides)
    return payload


def _accepted_retry_bundle(**overrides: Any) -> dict[str, Any]:
    proof = _retry_proof_payload()
    bundle: dict[str, Any] = {
        "proof": proof,
        "launch_identity": _retry_launch_identity(),
        "control_descriptor": _retry_control_descriptor(),
        "stage_ledger": _retry_ready_ledger_payload(next_prompt_ordinal=3),
        "prompt_outcome": _retry_prompt_outcome(),
        "debug_corroboration": _retry_debug_corroboration(),
        "relay_session_evidence": _retry_relay_session_evidence(),
        "claim": {
            "outcome": "accepted_same_session_retry",
            "settings_mutated": False,
            "zed_launched": False,
            "supported_by_live_attestation": True,
        },
    }
    bundle.update(overrides)
    return bundle


def test_verify_retry_preflight_offline_accepts_same_session_retry() -> None:
    v = _retry_offline_api()
    summary = v.verify_retry_preflight_offline(**_accepted_retry_bundle())
    assert summary["outcome"] == v.RETRY_OUTCOME_ACCEPTED_SAME_SESSION_RETRY
    assert "invalid_probe_retry" not in " ".join(summary.get("reason_codes", []))


def test_verify_retry_preflight_offline_rejects_changed_proof_field() -> None:
    v = _retry_offline_api()
    bundle = _accepted_retry_bundle()
    proof = dict(bundle["proof"])
    proof["zed_pid"] = 9999
    bundle["proof"] = proof
    with pytest.raises(CustodyContractError) as exc:
        v.verify_retry_preflight_offline(**bundle)
    assert exc.value.reason_code in {
        "invalid_probe_retry_proof_unavailable",
        "invalid_probe_retry_process_identity_mismatch",
    }


def test_verify_retry_preflight_offline_rejects_changed_evidence_hash() -> None:
    v = _retry_offline_api()
    bundle = _accepted_retry_bundle()
    proof = dict(bundle["proof"])
    evidence = list(proof["evidence"])
    item = dict(evidence[0])
    item["sha256"] = "9" * 64
    evidence[0] = item
    proof["evidence"] = evidence
    bundle["proof"] = proof
    with pytest.raises(CustodyContractError) as exc:
        v.verify_retry_preflight_offline(**bundle)
    assert exc.value.reason_code == "invalid_probe_retry_proof_unavailable"


def test_verify_retry_preflight_offline_rejects_descriptor_mismatch() -> None:
    v = _retry_offline_api()
    bundle = _accepted_retry_bundle()
    descriptor = dict(bundle["control_descriptor"])
    descriptor["descriptor_sha256"] = "0" * 64
    bundle["control_descriptor"] = descriptor
    with pytest.raises(CustodyContractError) as exc:
        v.verify_retry_preflight_offline(**bundle)
    assert exc.value.reason_code == "invalid_probe_retry_control_channel_failure"


def test_verify_retry_preflight_offline_rejects_stale_endpoint() -> None:
    v = _retry_offline_api()
    bundle = _accepted_retry_bundle()
    bundle["control_descriptor"] = _retry_control_descriptor(terminal=True)
    with pytest.raises(CustodyContractError) as exc:
        v.verify_retry_preflight_offline(**bundle)
    assert exc.value.reason_code in {
        "invalid_probe_retry_proof_unavailable",
        "invalid_probe_retry_control_channel_failure",
    }


def test_verify_retry_preflight_offline_rejects_pid_reuse() -> None:
    v = _retry_offline_api()
    bundle = _accepted_retry_bundle()
    # Same PID, different process-start identity => PID reuse.
    from tools.plan117_custody_contract import (
        EvidenceReference,
        build_live_session_proof,
        live_session_proof_payload,
    )

    reused = build_live_session_proof(
        run_attempt_id="origin-a-3",
        zed_pid=4242,
        zed_process_start_time_utc="2026-08-04T18:00:00Z",
        connection_id="conn-origin-a-3",
        acp_session_id="sess-origin-a-3",
        zed_alive=True,
        relay_alive=True,
        acp_session_observed=True,
        captured_utc="2026-08-04T18:05:00Z",
        evidence=(
            EvidenceReference(
                relative_path="attempts/origin-a-3/relay-index.ndjson",
                sha256=_RETRY_PROOF_EVIDENCE,
                hash_method="raw_file_sha256",
            ),
        ),
    )
    payload = live_session_proof_payload(reused)
    payload["schema"] = "plan117-custody-live-session-proof-v1"
    payload["proof_sha256"] = reused.proof_sha256
    payload["live_attestation"] = True
    bundle["proof"] = payload
    with pytest.raises(CustodyContractError) as exc:
        v.verify_retry_preflight_offline(**bundle)
    assert exc.value.reason_code == "invalid_probe_retry_process_identity_mismatch"


def test_verify_retry_preflight_offline_rejects_wrong_session_id() -> None:
    v = _retry_offline_api()
    bundle = _accepted_retry_bundle()
    from tools.plan117_custody_contract import (
        EvidenceReference,
        build_live_session_proof,
        live_session_proof_payload,
    )

    wrong = build_live_session_proof(
        run_attempt_id="origin-a-3",
        zed_pid=4242,
        zed_process_start_time_utc="2026-08-04T12:00:00Z",
        connection_id="conn-origin-a-3",
        acp_session_id="sess-WRONG",
        zed_alive=True,
        relay_alive=True,
        acp_session_observed=True,
        captured_utc="2026-08-04T12:05:00Z",
        evidence=(
            EvidenceReference(
                relative_path="attempts/origin-a-3/relay-index.ndjson",
                sha256=_RETRY_PROOF_EVIDENCE,
                hash_method="raw_file_sha256",
            ),
        ),
    )
    payload = live_session_proof_payload(wrong)
    payload["schema"] = "plan117-custody-live-session-proof-v1"
    payload["proof_sha256"] = wrong.proof_sha256
    payload["live_attestation"] = True
    bundle["proof"] = payload
    with pytest.raises(CustodyContractError) as exc:
        v.verify_retry_preflight_offline(**bundle)
    assert exc.value.reason_code == "invalid_probe_retry_acp_session_identity_mismatch"


def test_verify_retry_preflight_offline_rejects_wrong_connection_id() -> None:
    v = _retry_offline_api()
    bundle = _accepted_retry_bundle()
    from tools.plan117_custody_contract import (
        EvidenceReference,
        build_live_session_proof,
        live_session_proof_payload,
    )

    wrong = build_live_session_proof(
        run_attempt_id="origin-a-3",
        zed_pid=4242,
        zed_process_start_time_utc="2026-08-04T12:00:00Z",
        connection_id="conn-WRONG",
        acp_session_id="sess-origin-a-3",
        zed_alive=True,
        relay_alive=True,
        acp_session_observed=True,
        captured_utc="2026-08-04T12:05:00Z",
        evidence=(
            EvidenceReference(
                relative_path="attempts/origin-a-3/relay-index.ndjson",
                sha256=_RETRY_PROOF_EVIDENCE,
                hash_method="raw_file_sha256",
            ),
        ),
    )
    payload = live_session_proof_payload(wrong)
    payload["schema"] = "plan117-custody-live-session-proof-v1"
    payload["proof_sha256"] = wrong.proof_sha256
    payload["live_attestation"] = True
    bundle["proof"] = payload
    with pytest.raises(CustodyContractError) as exc:
        v.verify_retry_preflight_offline(**bundle)
    assert exc.value.reason_code == "invalid_probe_retry_connection_identity_mismatch"


def test_verify_retry_preflight_offline_rejects_missing_debug_corroboration() -> None:
    v = _retry_offline_api()
    bundle = _accepted_retry_bundle(debug_corroboration=None)
    with pytest.raises(CustodyContractError) as exc:
        v.verify_retry_preflight_offline(**bundle)
    assert exc.value.reason_code in {
        "invalid_probe_transcript_debug_divergence",
        "invalid_probe_retry_proof_unavailable",
        "blocked_probe_same_session_prompt_retry_unavailable",
    }


def test_verify_retry_preflight_offline_rejects_prompt_ordinal_4() -> None:
    v = _retry_offline_api()
    bundle = _accepted_retry_bundle(
        prompt_outcome=_retry_prompt_outcome(
            record_id="origin-a-3-prompt-4",
            ordinal=4,
        )
    )
    with pytest.raises(CustodyContractError) as exc:
        v.verify_retry_preflight_offline(**bundle)
    assert exc.value.reason_code == "invalid_probe_retry_budget_exhausted"


def test_verify_retry_preflight_offline_rejects_second_reservation() -> None:
    v = _retry_offline_api()
    outcome = _retry_prompt_outcome(
        evidence=[
            _ev("attempts/origin-a-3/live-session-proof.json", "f" * 64),
            _ev("reservations/origin-a-3-prompt-3.json", "1" * 64),
            _ev("reservations/origin-a-3-prompt-3-duplicate.json", "2" * 64),
        ]
    )
    bundle = _accepted_retry_bundle(prompt_outcome=outcome)
    with pytest.raises(CustodyContractError) as exc:
        v.verify_retry_preflight_offline(**bundle)
    assert exc.value.reason_code in {
        "reservation_already_exists",
        "invalid_probe_retry_budget_exhausted",
        "invalid_probe_stage_accounting",
    }


def test_verify_retry_preflight_offline_rejects_relaunch() -> None:
    v = _retry_offline_api()
    bundle = _accepted_retry_bundle(
        claim={
            "outcome": "accepted_same_session_retry",
            "settings_mutated": False,
            "zed_launched": True,
            "supported_by_live_attestation": True,
        },
        prompt_outcome=_retry_prompt_outcome(zed_launched=True),
    )
    with pytest.raises(CustodyContractError) as exc:
        v.verify_retry_preflight_offline(**bundle)
    assert exc.value.reason_code in {
        "invalid_probe_stage_accounting",
        "invalid_probe_retry_budget_exhausted",
        "blocked_probe_same_session_prompt_retry_unavailable",
    }


def test_verify_retry_preflight_offline_rejects_settings_mutation() -> None:
    v = _retry_offline_api()
    bundle = _accepted_retry_bundle(
        claim={
            "outcome": "accepted_same_session_retry",
            "settings_mutated": True,
            "zed_launched": False,
            "supported_by_live_attestation": True,
        },
        prompt_outcome=_retry_prompt_outcome(settings_mutated=True),
    )
    with pytest.raises(CustodyContractError) as exc:
        v.verify_retry_preflight_offline(**bundle)
    assert exc.value.reason_code == "settings_not_restored"


def test_verify_retry_preflight_offline_rejects_hardcoded_success_result() -> None:
    v = _retry_offline_api()
    bundle = _accepted_retry_bundle(
        proof=None,
        control_descriptor=None,
        debug_corroboration=None,
        relay_session_evidence=None,
        prompt_outcome=None,
        claim={
            "outcome": "accepted_same_session_retry",
            "settings_mutated": False,
            "zed_launched": False,
            "hardcoded": True,
            "supported_by_live_attestation": False,
        },
    )
    with pytest.raises(CustodyContractError) as exc:
        v.verify_retry_preflight_offline(**bundle)
    assert exc.value.reason_code in {
        "blocked_probe_same_session_prompt_retry_unavailable",
        "invalid_probe_retry_proof_unavailable",
    }


def test_verify_retry_preflight_offline_rejects_persisted_snapshot_only_live_claim() -> None:
    v = _retry_offline_api()
    # Proof JSON present but no debug/relay corroboration and no live attestation flag.
    proof = _retry_proof_payload(live_attestation=False)
    bundle = _accepted_retry_bundle(
        proof=proof,
        debug_corroboration=None,
        relay_session_evidence=None,
        claim={
            "outcome": "accepted_same_session_retry",
            "settings_mutated": False,
            "zed_launched": False,
            "supported_by_live_attestation": False,
        },
    )
    with pytest.raises(CustodyContractError) as exc:
        v.verify_retry_preflight_offline(**bundle)
    assert exc.value.reason_code in {
        "blocked_probe_same_session_prompt_retry_unavailable",
        "invalid_probe_retry_proof_unavailable",
    }


def test_verify_retry_preflight_offline_classifies_unavailable_proof() -> None:
    v = _retry_offline_api()
    summary = v.verify_retry_preflight_offline(
        proof=None,
        launch_identity=_retry_launch_identity(),
        control_descriptor=_retry_control_descriptor(),
        stage_ledger=_retry_ready_ledger_payload(next_prompt_ordinal=3),
        prompt_outcome=None,
        debug_corroboration=None,
        relay_session_evidence=None,
        claim=None,
    )
    assert summary["outcome"] == v.RETRY_OUTCOME_UNAVAILABLE_PROOF
    assert "blocked_probe_same_session_prompt_retry_unavailable" in summary["reason_codes"]


def test_verify_retry_preflight_offline_classifies_second_prompt_failure() -> None:
    v = _retry_offline_api()
    bundle = _accepted_retry_bundle(
        prompt_outcome=_retry_prompt_outcome(
            status="failed",
            failure_class="transient",
            reason_code="invalid_probe_retry_second_prompt_failure",
        ),
        claim={
            "outcome": "second_prompt_failure",
            "settings_mutated": False,
            "zed_launched": False,
            "supported_by_live_attestation": True,
        },
        stage_ledger=_retry_ready_ledger_payload(next_prompt_ordinal=3),
    )
    summary = v.verify_retry_preflight_offline(**bundle)
    assert summary["outcome"] == v.RETRY_OUTCOME_SECOND_PROMPT_FAILURE
    assert "invalid_probe_retry_second_prompt_failure" in summary["reason_codes"]


def test_verify_retry_preflight_offline_rejects_promoted_descriptor_secrets() -> None:
    v = _retry_offline_api()
    bundle = _accepted_retry_bundle()
    descriptor = dict(bundle["control_descriptor"])
    descriptor["authkey_hex"] = "ab" * 32
    # Keep digest consistent with locator body that now includes authkey when present
    # in the private descriptor; promoted verification must still reject secrets.
    from tools.plan117_custody_relay import _descriptor_sha256

    descriptor["descriptor_sha256"] = _descriptor_sha256(descriptor)
    bundle["control_descriptor"] = descriptor
    with pytest.raises(CustodyContractError) as exc:
        v.verify_retry_preflight_offline(**bundle, promote_safe_only=True)
    assert exc.value.reason_code == "invalid_probe_retry_control_channel_failure"
