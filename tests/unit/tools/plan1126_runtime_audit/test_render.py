"""Deterministic content-free rendering and fail-closed CLI tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.run_plan1126_runtime_audit as cli
from tools.plan1126_runtime_audit.model import AuditArtifact, GateStatus, LiveStatus
from tools.plan1126_runtime_audit.render import render_markdown
from tools.run_plan1126_runtime_audit import _live_gate, _record_zed, main

_COMMIT = "5ea8f8f71548eb05a8562a10e98667e3d2061c4d"
_OVERLAY = "fac32284888850bacde93815265cbabe3afd4663"
_TASK_0_COMMIT = "55fcd1fe4fd2d10c17776946d8f19d8d5f420a67"


def _artifact(**overrides: object) -> AuditArtifact:
    values: dict[str, object] = dict(
        schema_version="plan-11-26-runtime-audit-v1",
        merged_commit=_COMMIT,
        overlay_commit=_OVERLAY,
        binding_commit=None,
        baseline_reconciliation_status="UNRESOLVED",
        running_artifact_provenance=None,
        static_audit_status=LiveStatus.UNRUN,
        runtime_characterization_status=LiveStatus.UNRUN,
        live_redis_status=LiveStatus.UNRUN,
        acpx_status=LiveStatus.UNRUN,
        additional_client_status=LiveStatus.UNRUN,
        zed_status=LiveStatus.UNRUN,
        live_interoperability_status=LiveStatus.UNRUN,
        findings=(),
        discovered_multipliers={"cancellation_points": 0, "queues": 0, "sinks": 0, "close_paths": 0},
        computed_run_cost={
            "cancellation_concurrency_levels": [2, 4, 8],
            "cancellation_schedules": 0,
            "cancellation_control_schedules": 0,
            "queue_admissions": 0,
            "sink_failure_runs": 0,
            "idempotent_close_invocations": 0,
            "scenario_p50_ms": {},
            "scenario_p95_ms": {},
        },
        gate_status=GateStatus.PASS,
    )
    values.update(overrides)
    return AuditArtifact(**values)


def _provenance(client_name: str, client_version: str = "0.12.0") -> dict[str, object]:
    return {
        "binding_commit": _COMMIT, "executable_path": "C:/installed/agent.exe", "executable_sha256": "1" * 64,
        "package_name": "optimus-cost-agent", "package_version": "0.1.0", "package_metadata_sha256": "2" * 64,
        "build_manifest_sha256": "3" * 64, "embedded_commit": _COMMIT, "embedded_commit_sha256": "4" * 64,
        "launcher_sha256": "5" * 64,
        "client_provenance": {
            "name": client_name, "version": client_version, "path": "C:/installed/client.exe",
            "sha256": "6" * 64, "metadata_sha256": "7" * 64,
        },
        "environment_fingerprint": "8" * 64,
    }


def _canonical_digest(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _authority_document(*, plan_id: str = "11.26") -> dict[str, object]:
    return {
        "schema_version": "plan-11-26-prerequisite-intake-v1",
        "plan_id": plan_id,
        "source_task_0_commit": _TASK_0_COMMIT,
        "review_acceptance": {"status": "ACCEPTED"},
        "authority_decisions": {"redis_mutation": "AUTHORIZED", "zed_live": "AUTHORIZED"},
        "expected_execution_anchors": {
            "live-redis": {
                "expected_binding_commit": _COMMIT,
                "expected_command": "live-redis",
                "expected_client_identity": {"name": "redis-timeseries", "version": "8.0"},
            },
            "zed record": {
                "expected_binding_commit": _COMMIT,
                "expected_artifact_sha256": "9" * 64,
                "expected_command": "zed record",
                "expected_client_identity": {"name": "zed", "version": "1.17.2"},
            },
        },
    }


def test_render_is_deterministic_regeneration_from_canonical_json_and_content_free() -> None:
    payload = _artifact().to_dict()
    reversed_payload = dict(reversed(list(payload.items())))
    first = render_markdown(payload)
    second = render_markdown(reversed_payload)
    assert first == second
    assert first.startswith("# Plan 11.26 ACP runtime audit\n")
    assert "prompt" not in first.lower()
    assert "response body" not in first.lower()
    assert "UNRUN" in first


def test_cli_verify_and_render_use_json_as_authority(tmp_path: Path, capsys) -> None:
    artifact_path = tmp_path / "artifact.json"
    report_path = tmp_path / "artifact.md"
    artifact_path.write_text(json.dumps(_artifact().to_dict()), encoding="utf-8")
    assert main(["verify", "--artifact", str(artifact_path)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"
    assert main(["render", "--artifact", str(artifact_path), "--report", str(report_path)]) == 0
    assert report_path.read_text(encoding="utf-8") == render_markdown(_artifact().to_dict())


def test_live_cli_commands_fail_closed_before_any_dependency_execution(tmp_path: Path, capsys, monkeypatch) -> None:
    for command in ("live-redis", "acpx", "sdk"):
        assert main([command]) == 0
        result = json.loads(capsys.readouterr().out)
        assert result == {"reasons": ["authority_report_required"], "status": "UNRUN"}

    artifact = tmp_path / "artifact.json"
    authority = tmp_path / "authority.json"
    observations = tmp_path / "zed-observations.json"
    artifact.write_text(json.dumps(_artifact().to_dict()), encoding="utf-8")
    authority.write_text(json.dumps({"authority_decisions": {"zed_live": "UNAUTHORIZED"}}), encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(AssertionError("must not prompt")))
    assert main([
        "zed", "record", "--scenario", "normal-close", "--artifact", str(artifact),
        "--authority-report", str(authority), "--observations", str(observations),
    ]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result == {"reasons": ["authority_report_unaccepted"], "status": "INVALID"}
    assert not observations.exists()


def test_production_cli_rejects_unreviewed_authority_before_other_inputs(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    authority = tmp_path / "fabricated-authority.json"
    authority.write_text(json.dumps(_authority_document()), encoding="utf-8")
    missing = tmp_path / "does-not-exist.json"
    observations = tmp_path / "observations.json"
    assert main([
        "live-redis", "--authority-report", str(authority), "--provenance-manifest", str(missing),
    ]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "reasons": ["authority_report_unaccepted"], "status": "INVALID",
    }
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(AssertionError("must not prompt")))
    assert main([
        "zed", "record", "--scenario", "normal-close", "--artifact", str(missing),
        "--authority-report", str(authority), "--observations", str(observations),
    ]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "reasons": ["authority_report_unaccepted"], "status": "INVALID",
    }
    assert not observations.exists()


def test_committed_task_1_authority_is_accepted_identity_but_remains_unrun(tmp_path: Path, capsys) -> None:
    root = Path(__file__).parents[4]
    accepted = json.loads((root / "reports" / "plan-11-26-prerequisite-intake.json").read_text(encoding="utf-8"))
    copied_report = tmp_path / "copied-task-1-authority.json"
    copied_report.write_text(json.dumps(dict(reversed(list(accepted.items()))), indent=1), encoding="utf-8")
    assert main([
        "live-redis",
        "--authority-report", str(copied_report),
        "--provenance-manifest", str(tmp_path / "missing-provenance.json"),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "reasons": ["authority_not_granted"], "status": "UNRUN",
    }


def test_injected_accepted_digest_still_requires_authority_invariants(tmp_path: Path) -> None:
    authority = tmp_path / "wrong-plan-authority.json"
    payload = _authority_document(plan_id="11.25")
    authority.write_text(json.dumps(payload), encoding="utf-8")
    status, reasons, provenance = _live_gate(
        SimpleNamespace(
            authority_report=str(authority),
            provenance_manifest=str(tmp_path / "missing-provenance.json"),
            binding_commit=None,
        ),
        "live-redis",
        accepted_authority_digests=frozenset({_canonical_digest(payload)}),
    )
    assert (status, reasons, provenance) == ("INVALID", ("authority_report_shape_invalid",), None)


def test_live_cli_returns_invalid_for_bad_external_provenance(tmp_path: Path, capsys) -> None:
    authority = tmp_path / "authority.json"
    provenance = tmp_path / "provenance.json"
    authority_payload = _authority_document()
    authority.write_text(json.dumps(authority_payload), encoding="utf-8")
    provenance.write_text(json.dumps({"git_sha": _COMMIT}), encoding="utf-8")
    status, reasons, _ = _live_gate(
        SimpleNamespace(
            authority_report=str(authority), provenance_manifest=str(provenance), binding_commit=_COMMIT,
        ),
        "live-redis",
        accepted_authority_digests=frozenset({_canonical_digest(authority_payload)}),
    )
    assert status == "INVALID"
    assert "manifest_fields_incomplete" in reasons


def test_zed_record_rejects_non_zed_artifact_identity_without_prompt(tmp_path: Path, capsys, monkeypatch) -> None:
    artifact_path = tmp_path / "artifact.json"
    authority = tmp_path / "authority.json"
    observations = tmp_path / "observations.json"
    artifact_path.write_text(json.dumps(_artifact(
        binding_commit=_COMMIT,
        running_artifact_provenance=_provenance("acpx"),
    ).to_dict()), encoding="utf-8")
    artifact_digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    authority_payload = _authority_document()
    authority_payload["expected_execution_anchors"]["zed record"]["expected_artifact_sha256"] = artifact_digest
    authority.write_text(json.dumps(authority_payload), encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(AssertionError("must not prompt")))
    assert _record_zed(
        SimpleNamespace(
            scenario="normal-close", artifact=str(artifact_path),
            authority_report=str(authority), observations=str(observations),
        ),
        accepted_authority_digests=frozenset({_canonical_digest(authority_payload)}),
    ) == 1
    assert json.loads(capsys.readouterr().out) == {"reasons": ["client_identity_mismatch"], "status": "INVALID"}


def test_granted_live_authority_requires_independent_complete_anchor(tmp_path: Path, capsys) -> None:
    authority = tmp_path / "authority.json"
    provenance = tmp_path / "provenance.json"
    provenance.write_text(json.dumps({"binding_commit": _COMMIT}), encoding="utf-8")
    authority_payload = _authority_document()
    authority_payload["expected_execution_anchors"].pop("live-redis")
    authority.write_text(json.dumps(authority_payload), encoding="utf-8")
    status, reasons, provenance_result = _live_gate(
        SimpleNamespace(
            authority_report=str(authority), provenance_manifest=str(provenance), binding_commit=None,
        ),
        "live-redis",
        accepted_authority_digests=frozenset({_canonical_digest(authority_payload)}),
    )
    assert (status, reasons, provenance_result) == ("INVALID", ("authority_anchors_incomplete",), None)


def test_manifest_and_optional_binding_cannot_replace_authority_anchor(tmp_path: Path, capsys) -> None:
    authority = tmp_path / "authority.json"
    provenance = tmp_path / "provenance.json"
    authority_payload = _authority_document()
    authority_payload["expected_execution_anchors"]["live-redis"]["expected_binding_commit"] = _OVERLAY
    authority.write_text(json.dumps(authority_payload), encoding="utf-8")
    provenance.write_text(json.dumps({"binding_commit": _COMMIT}), encoding="utf-8")
    status, reasons, provenance_result = _live_gate(
        SimpleNamespace(
            authority_report=str(authority), provenance_manifest=str(provenance), binding_commit=_COMMIT,
        ),
        "live-redis",
        accepted_authority_digests=frozenset({_canonical_digest(authority_payload)}),
    )
    assert (status, reasons, provenance_result) == ("INVALID", ("binding_commit_authority_mismatch",), None)


def test_zed_uses_authority_before_artifact_and_rejects_self_anchoring(tmp_path: Path, capsys, monkeypatch) -> None:
    root = Path(__file__).parents[4]
    missing_artifact = tmp_path / "missing.json"
    observations = tmp_path / "observations.json"
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(AssertionError("must not prompt")))
    assert main([
        "zed", "record", "--scenario", "normal-close", "--artifact", str(missing_artifact),
        "--authority-report", str(root / "reports" / "plan-11-26-prerequisite-intake.json"),
        "--observations", str(observations),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "reasons": ["authority_not_granted"], "status": "UNRUN",
    }

    artifact = tmp_path / "fabricated-artifact.json"
    artifact.write_text(json.dumps(_artifact(
        binding_commit=_COMMIT,
        running_artifact_provenance=_provenance("zed", "1.17.2"),
    ).to_dict()), encoding="utf-8")
    authority = tmp_path / "authority.json"
    authority_payload = _authority_document()
    authority_payload["expected_execution_anchors"]["zed record"].update({
        "expected_binding_commit": _OVERLAY,
        "expected_artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
    })
    authority.write_text(json.dumps(authority_payload), encoding="utf-8")
    assert _record_zed(
        SimpleNamespace(
            scenario="normal-close", artifact=str(artifact),
            authority_report=str(authority), observations=str(observations),
        ),
        accepted_authority_digests=frozenset({_canonical_digest(authority_payload)}),
    ) == 1
    assert json.loads(capsys.readouterr().out) == {
        "reasons": ["artifact_binding_authority_mismatch"], "status": "INVALID",
    }
    assert not observations.exists()


def test_inventory_and_offline_subcommands_are_non_live(tmp_path: Path, capsys) -> None:
    assert main(["inventory"]) == 0
    assert json.loads(capsys.readouterr().out) == {"reasons": ["commit_required"], "status": "UNRUN"}
    assert main(["offline"]) == 0
    assert json.loads(capsys.readouterr().out) == {"reasons": ["intake_reports_required"], "status": "UNRUN"}


def test_inventory_and_offline_subcommands_perform_offline_work(tmp_path: Path, capsys) -> None:
    root = Path(__file__).parents[4]
    inventory_output = tmp_path / "inventory.json"
    assert main([
        "inventory", "--repository", str(root), "--commit", _COMMIT, "--output", str(inventory_output),
    ]) == 0
    inventory_status = json.loads(capsys.readouterr().out)
    inventory = json.loads(inventory_output.read_text(encoding="utf-8"))
    assert inventory_status["status"] == "PARTIAL"
    assert inventory["site_count"] > 0
    assert inventory["unclassified_site_count"] == inventory["site_count"]

    offline_output = tmp_path / "offline.json"
    assert main([
        "offline",
        "--baseline-report", str(root / "reports" / "plan-11-26-baseline-intake.json"),
        "--prerequisite-report", str(root / "reports" / "plan-11-26-prerequisite-intake.json"),
        "--output", str(offline_output),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "COMPLETE"
    offline = json.loads(offline_output.read_text(encoding="utf-8"))
    assert offline["prerequisite_count"] == 18
    assert offline["binding_commit"] is None


def _offline_spec(
    scenario_id: str, code: str, *, harness_paths: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "command": (sys.executable, "-c", code),
        "harness_paths": harness_paths,
    }


def _write_offline_artifact(path: Path) -> None:
    path.write_text(json.dumps(_artifact(
        static_audit_status=LiveStatus.UNRUN,
        runtime_characterization_status=LiveStatus.UNRUN,
        discovered_multipliers={"cancellation_points": 8, "queues": 3, "sinks": 5, "close_paths": 15},
        computed_run_cost={
            "cancellation_concurrency_levels": [2, 4, 8],
            "cancellation_schedules": 6_144,
            "cancellation_control_schedules": 2_048,
            "queue_admissions": 30_000,
            "sink_failure_runs": 500,
            "idempotent_close_invocations": 225,
            "scenario_p50_ms": {},
            "scenario_p95_ms": {},
        },
        gate_status=GateStatus.INCOMPLETE,
    ).to_dict()), encoding="utf-8")


def test_offline_tier_runner_checkpoints_real_repeats_and_resumes(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    artifact = tmp_path / "artifact.json"
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "narrow.json"
    _write_offline_artifact(artifact)
    monkeypatch.setattr(cli, "_OFFLINE_TIER_COMMANDS", {
        "narrow": (_offline_spec("sample", "print('1 passed in 0.01s')"),),
        "group": (),
    })
    monkeypatch.setattr(cli, "_OFFLINE_REPEAT_COUNTS", {"narrow": 2, "group": 2, "terminal": 1})

    command = [
        "offline", "--artifact", str(artifact), "--checkpoint", str(checkpoint),
        "--tier", "narrow", "--repeats", "2", "--output", str(output),
    ]
    assert main(command) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "COMPLETE"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["tier"] == "narrow"
    assert len(payload["scenarios"]) == 1
    scenario = payload["scenarios"][0]
    assert scenario["scenario_id"] == "sample"
    assert scenario["command"] == f"{sys.executable} -c print('1 passed in 0.01s')"
    assert scenario["repeat_count"] == 2
    assert scenario["repeatability"] == "STABLE"
    assert scenario["status"] == "PASS"
    assert len(scenario["outcome_fingerprints"]) == 1
    assert len(scenario["outcome_fingerprints"][0]) == 64
    assert scenario["p50_ms"] >= 0
    assert scenario["p95_ms"] >= scenario["p50_ms"]
    assert json.loads(checkpoint.read_text(encoding="utf-8"))["revision"] == 2

    assert main(command) == 0
    capsys.readouterr()
    assert json.loads(checkpoint.read_text(encoding="utf-8"))["revision"] == 2


def test_offline_tier_distinguishes_flaky_from_harness_invalid(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    artifact = tmp_path / "artifact.json"
    _write_offline_artifact(artifact)
    monkeypatch.setattr(cli, "_OFFLINE_REPEAT_COUNTS", {"narrow": 2, "group": 2, "terminal": 1})
    counter = tmp_path / "counter.txt"
    flaky_code = (
        "from pathlib import Path; "
        f"p=Path({str(counter)!r}); n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n)); "
        "print('1 passed in 0.01s' if n == 1 else '1 failed in 0.01s'); raise SystemExit(0 if n == 1 else 1)"
    )
    monkeypatch.setattr(cli, "_OFFLINE_TIER_COMMANDS", {
        "narrow": (_offline_spec("flaky", flaky_code),), "group": (),
    })
    flaky_output = tmp_path / "flaky.json"
    assert main([
        "offline", "--artifact", str(artifact), "--checkpoint", str(tmp_path / "flaky-checkpoint.json"),
        "--tier", "narrow", "--repeats", "2", "--output", str(flaky_output),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "reasons": ["flaky_scenarios=flaky"], "status": "COMPLETE",
    }
    assert json.loads(flaky_output.read_text(encoding="utf-8"))["scenarios"][0]["repeatability"] == "FLAKY"

    harness = tmp_path / "harness.txt"
    harness.write_text("stable", encoding="utf-8")
    invalid_code = f"from pathlib import Path; p=Path({str(harness)!r}); p.write_text(p.read_text()+'x'); print('1 passed')"
    monkeypatch.setattr(cli, "_OFFLINE_TIER_COMMANDS", {
        "narrow": (_offline_spec("invalid", invalid_code, harness_paths=(str(harness),)),), "group": (),
    })
    invalid_output = tmp_path / "invalid.json"
    assert main([
        "offline", "--artifact", str(artifact), "--checkpoint", str(tmp_path / "invalid-checkpoint.json"),
        "--tier", "narrow", "--repeats", "2", "--output", str(invalid_output),
    ]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "reasons": ["harness_invalid_scenarios=invalid"], "status": "INVALID",
    }
    assert json.loads(invalid_output.read_text(encoding="utf-8"))["scenarios"][0]["repeatability"] == "HARNESS_INVALID"


def test_offline_tier_captures_timeout_diagnostics_and_attributes_harness_instability(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    artifact = tmp_path / "artifact.json"
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "timeout.json"
    _write_offline_artifact(artifact)
    nodeid = "tests/unit/tools/plan1126_runtime_audit/test_probe.py::test_blocks"
    spec = _offline_spec("bounded", f"import time; print({nodeid!r}, flush=True); time.sleep(1)")
    spec["timeout_seconds"] = 0.5
    spec["harness_nodeids"] = (nodeid,)
    monkeypatch.setattr(cli, "_OFFLINE_TIER_COMMANDS", {"narrow": (spec,), "group": ()})

    assert main([
        "offline", "--artifact", str(artifact), "--checkpoint", str(checkpoint),
        "--tier", "narrow", "--repeats", "1", "--output", str(output),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "reasons": ["harness_unstable_scenarios=bounded"], "status": "COMPLETE",
    }
    scenario = json.loads(output.read_text(encoding="utf-8"))["scenarios"][0]
    assert scenario["status"] == "TIMEOUT"
    assert scenario["repeatability"] == "HARNESS_UNSTABLE"
    entry = json.loads(checkpoint.read_text(encoding="utf-8"))["entries"]
    outcome = entry["task11-narrow-bounded-repeat-01"]["outcome"]
    assert outcome["status"] == "TIMEOUT"
    assert outcome["last_test_nodeid"] == nodeid
    assert outcome["timeout_subject"] == "HARNESS"
    assert nodeid in outcome["stdout_tail"]
    assert len(outcome["stdout_sha256"]) == 64
    assert outcome["stderr_tail"] == ""


def test_offline_timeout_terminates_descendants_that_inherit_capture_pipes(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    artifact = tmp_path / "artifact.json"
    checkpoint = tmp_path / "checkpoint.json"
    _write_offline_artifact(artifact)
    nodeid = "tests/unit/tools/plan1126_runtime_audit/test_probe.py::test_descendant"
    child_code = "import time; time.sleep(2)"
    code = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        f"print({nodeid!r}, flush=True); time.sleep(2)"
    )
    spec = _offline_spec("descendant", code)
    spec["timeout_seconds"] = 0.1
    spec["harness_nodeids"] = (nodeid,)
    monkeypatch.setattr(cli, "_OFFLINE_TIER_COMMANDS", {"narrow": (spec,), "group": ()})

    started = time.perf_counter()
    assert main([
        "offline", "--artifact", str(artifact), "--checkpoint", str(checkpoint),
        "--tier", "narrow", "--repeats", "1",
    ]) == 0
    elapsed = time.perf_counter() - started
    capsys.readouterr()

    assert elapsed < 1.0


def test_offline_scenario_rerun_uses_new_generation_without_overwriting_history(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    artifact = tmp_path / "artifact.json"
    checkpoint = tmp_path / "checkpoint.json"
    _write_offline_artifact(artifact)
    spec = _offline_spec("sample", "print('1 passed in 0.01s')")
    monkeypatch.setattr(cli, "_OFFLINE_TIER_COMMANDS", {"narrow": (spec,), "group": ()})

    base = [
        "offline", "--artifact", str(artifact), "--checkpoint", str(checkpoint),
        "--tier", "narrow", "--repeats", "1", "--scenario", "sample",
    ]
    assert main(base) == 0
    capsys.readouterr()
    assert main([*base, "--measurement-generation", "c18-bounded-git-v1"]) == 0
    capsys.readouterr()

    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert payload["revision"] == 2
    assert "task11-narrow-sample-repeat-01" in payload["entries"]
    assert "task11-narrow-sample-c18-bounded-git-v1-repeat-01" in payload["entries"]
    assert payload["entries"]["task11-narrow-sample-c18-bounded-git-v1-repeat-01"][
        "measurement_generation"
    ] == "c18-bounded-git-v1"


def test_cost_proposal_selects_latest_complete_measurement_generation(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    root = Path(__file__).parents[4]
    artifact = tmp_path / "artifact.json"
    checkpoint = tmp_path / "checkpoint.json"
    terminal_report = tmp_path / "terminal.md"
    _write_offline_artifact(artifact)
    spec = _offline_spec("measured_group", "print('1 passed in 0.01s')")
    monkeypatch.setattr(cli, "_OFFLINE_TIER_COMMANDS", {"narrow": (), "group": (spec,)})
    monkeypatch.setattr(cli, "_OFFLINE_REPEAT_COUNTS", {"narrow": 2, "group": 2, "terminal": 1})

    base = [
        "offline", "--artifact", str(artifact), "--checkpoint", str(checkpoint),
        "--tier", "group", "--repeats", "2", "--scenario", "measured_group",
    ]
    assert main(base) == 0
    capsys.readouterr()
    assert main([*base, "--measurement-generation", "c18-bounded-git-v1"]) == 0
    capsys.readouterr()
    document = json.loads(checkpoint.read_text(encoding="utf-8"))
    for repeat in (1, 2):
        document["entries"][f"task11-group-measured_group-repeat-{repeat:02d}"][
            "duration_ms"
        ] = 999.0
        complete_key = (
            f"task11-group-measured_group-c18-bounded-git-v1-repeat-{repeat:02d}"
        )
        document["entries"][complete_key]["duration_ms"] = 5.0
    partial = dict(
        document["entries"][
            "task11-group-measured_group-c18-bounded-git-v1-repeat-01"
        ]
    )
    partial["duration_ms"] = 1.0
    partial["measurement_generation"] = "newer-incomplete-v1"
    partial["checkpoint_revision"] = int(document["revision"]) + 1
    document["revision"] = int(document["revision"]) + 1
    document["entries"][
        "task11-group-measured_group-newer-incomplete-v1-repeat-01"
    ] = partial
    checkpoint.write_text(json.dumps(document), encoding="utf-8")

    assert main([
        "offline", "--artifact", str(artifact), "--checkpoint", str(checkpoint),
        "--baseline-report", str(root / "reports" / "plan-11-26-baseline-intake.json"),
        "--prerequisite-report", str(root / "reports" / "plan-11-26-prerequisite-intake.json"),
        "--cost-proposal", "--terminal-report", str(terminal_report),
    ]) == 0
    capsys.readouterr()

    cost = json.loads(artifact.read_text(encoding="utf-8"))["computed_run_cost"]
    assert cost["scenario_p50_ms"]["measured_group"] == 5.0
    assert "c18-bounded-git-v1" in terminal_report.read_text(encoding="utf-8")


def test_offline_cost_proposal_updates_measurements_and_keeps_live_rows_unrun(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    root = Path(__file__).parents[4]
    artifact = tmp_path / "artifact.json"
    checkpoint = tmp_path / "checkpoint.json"
    terminal_report = tmp_path / "terminal.md"
    _write_offline_artifact(artifact)
    spec = _offline_spec("measured_group", "print('1 passed in 0.01s')")
    monkeypatch.setattr(cli, "_OFFLINE_TIER_COMMANDS", {"narrow": (spec,), "group": (spec,)})
    monkeypatch.setattr(cli, "_OFFLINE_REPEAT_COUNTS", {"narrow": 2, "group": 2, "terminal": 1})
    for tier in ("narrow", "group"):
        assert main([
            "offline", "--artifact", str(artifact), "--checkpoint", str(checkpoint),
            "--tier", tier, "--repeats", "2",
        ]) == 0
        capsys.readouterr()

    assert main([
        "offline", "--artifact", str(artifact), "--checkpoint", str(checkpoint),
        "--baseline-report", str(root / "reports" / "plan-11-26-baseline-intake.json"),
        "--prerequisite-report", str(root / "reports" / "plan-11-26-prerequisite-intake.json"),
        "--cost-proposal", "--terminal-report", str(terminal_report),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "reasons": ["operator_cost_approval_required"], "status": "UNRUN",
    }
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert set(payload["computed_run_cost"]["scenario_p50_ms"]) == {"measured_group"}
    assert set(payload["computed_run_cost"]["scenario_p95_ms"]) == {"measured_group"}
    assert payload["live_redis_status"] == "UNRUN"
    assert payload["acpx_status"] == "UNRUN"
    assert payload["additional_client_status"] == "UNRUN"
    assert payload["zed_status"] == "UNRUN"
    report = terminal_report.read_text(encoding="utf-8")
    for token in ("6,144", "2,048", "30,000", "500", "225", "UNRUN_WSL2", "operator / Plan 11.26"):
        assert token in report
    assert "Live run count | 0" in report
    assert "p95 excluding timeouts" in report
    assert "Harness-timeout p95 contribution" in report
    assert "## Repeatability disposition" in report
    assert "| narrow | measured_group | legacy | 2 | 0 | 0 | STABLE |" in report


def test_offline_terminal_command_runs_once_only_after_tier_evidence_exists(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    artifact = tmp_path / "artifact.json"
    checkpoint = tmp_path / "checkpoint.json"
    _write_offline_artifact(artifact)
    spec = _offline_spec("terminal_group", "print('1 passed in 0.01s')")
    monkeypatch.setattr(cli, "_OFFLINE_TIER_COMMANDS", {"narrow": (spec,), "group": (spec,)})
    monkeypatch.setattr(cli, "_OFFLINE_REPEAT_COUNTS", {"narrow": 1, "group": 1, "terminal": 1})
    for tier in ("narrow", "group"):
        assert main([
            "offline", "--artifact", str(artifact), "--checkpoint", str(checkpoint),
            "--tier", tier, "--repeats", "1",
        ]) == 0
        capsys.readouterr()
    assert main(["offline", "--artifact", str(artifact), "--checkpoint", str(checkpoint)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "COMPLETE"
    entries = json.loads(checkpoint.read_text(encoding="utf-8"))["entries"]
    assert "task11-terminal-terminal_group-repeat-01" in entries


@pytest.mark.parametrize(
    "mutation",
    [
        "merged_commit",
        "overlay_commit",
        "binding_commit",
        "reconciliation_status",
        "pointer_report",
        "source_link",
        "duplicate_id",
        "missing_id",
        "missing_owner",
        "invalid_method",
        "invalid_authorized",
        "invalid_dependents",
        "incomplete_scope_out",
    ],
)
def test_offline_rejects_semantically_invalid_task_0_and_task_1_intakes(
    mutation: str, tmp_path: Path, capsys,
) -> None:
    root = Path(__file__).parents[4]
    baseline = json.loads((root / "reports" / "plan-11-26-baseline-intake.json").read_text(encoding="utf-8"))
    prerequisites = json.loads((root / "reports" / "plan-11-26-prerequisite-intake.json").read_text(encoding="utf-8"))
    if mutation == "merged_commit":
        baseline["merged_baseline"]["commit"] = "0" * 40
    elif mutation == "overlay_commit":
        baseline["runtime_overlay"]["accepted_runtime_commit"] = "1" * 40
    elif mutation == "binding_commit":
        baseline["binding_commit"] = _COMMIT
    elif mutation == "reconciliation_status":
        baseline["baseline_reconciliation_status"] = "RESOLVED"
    elif mutation == "pointer_report":
        baseline["task_1_prerequisite_intake"]["report"] = "reports/other.json"
    elif mutation == "source_link":
        prerequisites["source_task_0_commit"] = "2" * 40
    elif mutation == "duplicate_id":
        prerequisites["prerequisites"][-1]["id"] = prerequisites["prerequisites"][0]["id"]
    elif mutation == "missing_id":
        prerequisites["prerequisites"].pop()
    elif mutation == "missing_owner":
        prerequisites["prerequisites"][0]["owner"] = ""
    elif mutation == "invalid_method":
        prerequisites["prerequisites"][0]["method"] = 1
    elif mutation == "invalid_authorized":
        prerequisites["prerequisites"][0]["authorized"] = "true"
    elif mutation == "invalid_dependents":
        prerequisites["prerequisites"][0]["dependent_rows"] = [1]
    elif mutation == "incomplete_scope_out":
        prerequisites["prerequisites"][1]["scope_out"].pop("reason")
    baseline_path = tmp_path / f"baseline-{mutation}.json"
    prerequisite_path = tmp_path / f"prerequisite-{mutation}.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    prerequisite_path.write_text(json.dumps(prerequisites), encoding="utf-8")
    assert main([
        "offline", "--baseline-report", str(baseline_path),
        "--prerequisite-report", str(prerequisite_path),
    ]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "reasons": ["intake_reports_invalid"], "status": "INVALID",
    }


def test_offline_requires_the_frozen_literal_seed_fixture(tmp_path: Path, capsys, monkeypatch) -> None:
    root = Path(__file__).parents[4]
    monkeypatch.setattr("tools.run_plan1126_runtime_audit.literal_seeds", lambda: (99,))
    assert main([
        "offline",
        "--baseline-report", str(root / "reports" / "plan-11-26-baseline-intake.json"),
        "--prerequisite-report", str(root / "reports" / "plan-11-26-prerequisite-intake.json"),
    ]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "reasons": ["intake_reports_invalid"], "status": "INVALID",
    }


def test_cli_script_runs_directly_from_outside_repository(tmp_path: Path) -> None:
    script = Path(__file__).parents[4] / "tools" / "run_plan1126_runtime_audit.py"
    completed = subprocess.run(
        [sys.executable, str(script), "inventory"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"reasons": ["commit_required"], "status": "UNRUN"}
