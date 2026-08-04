"""RED/GREEN unit tests for Plan 11.7 custody feasibility phase orchestration."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = ROOT / "tools" / "run_plan117_custody_feasibility.py"
SCENARIO_PATH = ROOT / "tests" / "fixtures" / "evidence" / "scenarios" / "plan117-server-custody.toml"
PROMPT_FIXTURE = ROOT / "tests" / "fixtures" / "evidence" / "plan117-server-custody-prompt.txt"
PROMPT_SHA256_UPPER = "8EEA4738E72159A863FEA22A542F92D6A99E3681803BA21863F734C577480D82"

FORBIDDEN_TOKENS = (
    "SendInput",
    "pyautogui",
    "uiautomation",
    "acpx",
    "evidence_gather_support",
    "session/load",
)

PHASES = (
    "direct-control",
    "relay-control",
    "origin-a",
    "origin-a-prompt-retry",
    "restart-b",
    "fresh-control-c",
    "direct-ancestry-control",
    "restore-settings",
    "finalize",
)


def _import_runner():
    import tools.run_plan117_custody_feasibility as runner

    return runner


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_settings(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def _optimus_settings(*, command: str = "optimus-agent", args: list[str] | None = None) -> dict[str, Any]:
    return {
        "theme": "one-dark",
        "agent_servers": {
            "optimus": {
                "command": command,
                "args": args if args is not None else ["--workspace-root", "."],
                "env": {"KEEP": "me"},
            }
        },
        "unrelated": {"nested": True},
    }


def _approval(
    *,
    settings_path: Path,
    pre_image_sha256: str | None,
    operator_identity: str = "operator@host",
    approved_at_utc: str | None = None,
) -> dict[str, Any]:
    return {
        "settings_path": str(settings_path.resolve()),
        "pre_image_sha256": pre_image_sha256,
        "operator_identity": operator_identity,
        "approved_at_utc": approved_at_utc
        or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@pytest.fixture
def custody_roots(tmp_path: Path) -> dict[str, Path]:
    workspace = tmp_path / "workspace"
    capture = tmp_path / "capture"
    custody = tmp_path / "custody"
    settings = tmp_path / "zed" / "settings.json"
    zed_exe = tmp_path / "zed.exe"
    zed_src = tmp_path / "zed-src"
    debug_log = tmp_path / "debug-acp.ndjson"
    for path in (workspace, capture, custody, zed_src):
        path.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("Optimus Cost Agent\n", encoding="utf-8", newline="\n")
    zed_exe.write_bytes(b"MZ-fake-zed")
    debug_log.write_text("", encoding="utf-8", newline="\n")
    _write_settings(settings, _optimus_settings())
    return {
        "workspace_root": workspace.resolve(),
        "capture_root": capture.resolve(),
        "custody_root": custody.resolve(),
        "settings_path": settings.resolve(),
        "zed_executable": zed_exe.resolve(),
        "zed_source": zed_src.resolve(),
        "debug_log": debug_log.resolve(),
    }


# --- Scenario loader ----------------------------------------------------------


def test_plan117_scenario_loads_via_public_loader() -> None:
    from evidence_handoff.collector import load_scenario

    scenario = load_scenario(SCENARIO_PATH)
    assert scenario.scenario_id == "plan117-server-custody"
    assert "observation_window_complete" in scenario.required_evidence
    assert "completion_observed" not in scenario.required_evidence
    assert scenario.client.adapter_id == "zed_acp_client"
    assert scenario.fixture.adapter_id == "hermetic_user_data_fixture"
    assert any(item.adapter_id == "acp_stream_collector" for item in scenario.collection)
    assert {item.adapter_id for item in scenario.detection} == {
        "completion_detector",
        "crash_detector",
    }


def test_prompt_fixture_hash_and_readme_precondition(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    assert PROMPT_FIXTURE.read_bytes() == (
        b"Read README.md and answer with one sentence naming this project. "
        b"Do not modify files.\n"
    )
    assert _sha256_bytes(PROMPT_FIXTURE.read_bytes()).upper() == PROMPT_SHA256_UPPER
    assert runner.PROMPT_FIXTURE_SHA256.upper() == PROMPT_SHA256_UPPER
    readme = runner.require_readme_precondition(custody_roots["workspace_root"])
    assert readme.name == "README.md"
    assert readme.is_file()


# --- Path containment ---------------------------------------------------------


def test_path_containment_and_symlink_rejection(
    tmp_path: Path, custody_roots: dict[str, Path]
) -> None:
    runner = _import_runner()
    outside = (tmp_path / "outside" / "settings.json").resolve()
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.resolve_probe_paths(
            workspace_root=custody_roots["workspace_root"],
            capture_root=custody_roots["capture_root"],
            zed_executable=custody_roots["zed_executable"],
            zed_source=custody_roots["zed_source"],
            settings_path=outside,
            debug_log=custody_roots["debug_log"],
            custody_root=custody_roots["custody_root"],
            allowed_settings_roots=(custody_roots["custody_root"],),
        )
    assert exc.value.reason_code == "settings_path_unapproved"

    link = tmp_path / "link-settings.json"
    try:
        link.symlink_to(custody_roots["settings_path"])
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(runner.CustodyRunnerError) as exc2:
        runner.require_regular_non_symlink(link, label="settings_path")
    assert exc2.value.reason_code == "symlink_forbidden"


def test_relative_paths_rejected_before_side_effects(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.resolve_probe_paths(
            workspace_root=Path("relative-workspace"),
            capture_root=custody_roots["capture_root"],
            zed_executable=custody_roots["zed_executable"],
            zed_source=custody_roots["zed_source"],
            settings_path=custody_roots["settings_path"],
            debug_log=custody_roots["debug_log"],
            custody_root=custody_roots["custody_root"],
            allowed_settings_roots=(custody_roots["settings_path"].parent,),
        )
    assert exc.value.reason_code == "path_not_absolute"


# --- Settings transaction -----------------------------------------------------


def test_settings_mutation_refused_without_approval(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    settings = custody_roots["settings_path"]
    before = settings.read_bytes()
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.mutate_settings_insert_relay(
            settings_path=settings,
            custody_root=custody_roots["custody_root"],
            relay_command=str(ROOT / "tools" / "plan117_custody_relay.py"),
            relay_args=["--capture-root", str(custody_roots["capture_root"])],
            approval=None,
            agent_server_name="optimus",
        )
    assert exc.value.reason_code == "settings_mutation_approval_required"
    assert settings.read_bytes() == before


def test_settings_mutation_requires_path_digest_operator_utc(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    settings = custody_roots["settings_path"]
    pre = _sha256_bytes(settings.read_bytes())
    incomplete = {
        "settings_path": str(settings),
        "pre_image_sha256": pre,
        "operator_identity": "op",
        # missing approved_at_utc
    }
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.mutate_settings_insert_relay(
            settings_path=settings,
            custody_root=custody_roots["custody_root"],
            relay_command="relay.py",
            relay_args=[],
            approval=incomplete,
            agent_server_name="optimus",
        )
    assert exc.value.reason_code == "settings_mutation_approval_incomplete"


def test_settings_preimage_allowlist_atomic_replace_and_restore_success(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    settings = custody_roots["settings_path"]
    original = settings.read_bytes()
    pre = _sha256_bytes(original)
    approval = _approval(settings_path=settings, pre_image_sha256=pre)
    proof = runner.mutate_settings_insert_relay(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        relay_command="python",
        relay_args=["relay.py", "--x"],
        approval=approval,
        agent_server_name="optimus",
    )
    mutated = settings.read_bytes()
    assert mutated != original
    assert proof["pre_image_existed"] is True
    assert proof["pre_image_sha256"] == pre
    assert proof["mutated_sha256"] == _sha256_bytes(mutated)
    assert set(proof["changed_key_paths"]) <= {
        "agent_servers.optimus.command",
        "agent_servers.optimus.args",
    }
    payload = json.loads(mutated.decode("utf-8"))
    assert payload["theme"] == "one-dark"
    assert payload["unrelated"] == {"nested": True}
    assert payload["agent_servers"]["optimus"]["env"] == {"KEEP": "me"}
    assert payload["agent_servers"]["optimus"]["command"] == "python"
    assert payload["agent_servers"]["optimus"]["args"] == ["relay.py", "--x"]

    restored = runner.restore_settings(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        expected_mutated_sha256=proof["mutated_sha256"],
    )
    assert restored["restored"] is True
    assert settings.read_bytes() == original
    assert restored["final_sha256"] == pre
    assert restored["final_existed"] is True


@pytest.mark.parametrize("failure_mode", ["exception", "timeout", "crash"])
def test_settings_restore_on_every_exception_path(
    custody_roots: dict[str, Path], failure_mode: str
) -> None:
    runner = _import_runner()
    settings = custody_roots["settings_path"]
    original = settings.read_bytes()
    pre = _sha256_bytes(original)
    approval = _approval(settings_path=settings, pre_image_sha256=pre)

    def boom() -> None:
        if failure_mode == "timeout":
            raise TimeoutError("timed out")
        if failure_mode == "crash":
            raise SystemExit(1)
        raise RuntimeError("boom")

    with pytest.raises((RuntimeError, TimeoutError, SystemExit)):
        runner.run_with_settings_transaction(
            settings_path=settings,
            custody_root=custody_roots["custody_root"],
            relay_command="python",
            relay_args=["relay.py"],
            approval=approval,
            agent_server_name="optimus",
            body=boom,
        )
    assert settings.read_bytes() == original


def test_settings_absent_file_restoration(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    settings = custody_roots["settings_path"]
    settings.unlink()
    assert not settings.exists()
    approval = _approval(settings_path=settings, pre_image_sha256=None)
    proof = runner.mutate_settings_insert_relay(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        relay_command="python",
        relay_args=["relay.py"],
        approval=approval,
        agent_server_name="optimus",
        create_if_absent=True,
    )
    assert settings.is_file()
    assert proof["pre_image_existed"] is False
    restored = runner.restore_settings(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        expected_mutated_sha256=proof["mutated_sha256"],
    )
    assert restored["final_existed"] is False
    assert not settings.exists()


def test_restore_settings_idempotent_and_verifies_mutated_digest(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    settings = custody_roots["settings_path"]
    original = settings.read_bytes()
    pre = _sha256_bytes(original)
    approval = _approval(settings_path=settings, pre_image_sha256=pre)
    proof = runner.mutate_settings_insert_relay(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        relay_command="python",
        relay_args=["relay.py"],
        approval=approval,
        agent_server_name="optimus",
    )
    # Tamper mutated file before restore.
    settings.write_bytes(b'{"tampered":true}\n')
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.restore_settings(
            settings_path=settings,
            custody_root=custody_roots["custody_root"],
            expected_mutated_sha256=proof["mutated_sha256"],
        )
    assert exc.value.reason_code == "settings_mutated_digest_mismatch"

    # Put expected mutated bytes back and restore twice (idempotent).
    # Re-mutate cleanly.
    settings.write_bytes(original)
    proof2 = runner.mutate_settings_insert_relay(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        relay_command="python",
        relay_args=["relay.py"],
        approval=_approval(settings_path=settings, pre_image_sha256=pre),
        agent_server_name="optimus",
    )
    first = runner.restore_settings(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        expected_mutated_sha256=proof2["mutated_sha256"],
    )
    second = runner.restore_settings(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        expected_mutated_sha256=proof2["mutated_sha256"],
    )
    assert first["restored"] is True
    assert second["already_restored"] is True
    assert settings.read_bytes() == original


# --- Phase state machine ------------------------------------------------------


def test_phase_order_state_machine_and_immutable_attempts(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    assert tuple(runner.PHASES) == PHASES
    state_path = custody_roots["capture_root"] / "plan117-custody-state.json"
    state = runner.init_phase_state(state_path)
    assert state["schema"] == "plan117-custody-state-v1"
    assert state["completed_phases"] == []
    assert state["next_ordinal"]["correlation_capture"] == 1
    assert state["next_ordinal"]["post_new_prompt"] == 1

    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.assert_phase_allowed(state, "origin-a")
    assert exc.value.reason_code == "phase_order_violation"

    runner.mark_phase_complete(state_path, "direct-control")
    runner.mark_phase_complete(state_path, "relay-control")
    state = runner.load_phase_state(state_path)
    runner.assert_phase_allowed(state, "origin-a")

    attempt = runner.allocate_attempt_directory(
        capture_root=custody_roots["capture_root"],
        state_path=state_path,
        phase="origin-a",
        kind="correlation_capture",
    )
    assert attempt.name == "origin-a-1"
    assert attempt.is_dir()
    with pytest.raises(runner.CustodyRunnerError) as exc2:
        runner.allocate_attempt_directory(
            capture_root=custody_roots["capture_root"],
            state_path=state_path,
            phase="origin-a",
            kind="correlation_capture",
            force_ordinal=1,
        )
    assert exc2.value.reason_code == "attempt_directory_exists"


def test_separate_correlation_and_prompt_ordinals(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    state_path = custody_roots["capture_root"] / "plan117-custody-state.json"
    runner.init_phase_state(state_path)
    for phase in ("direct-control", "relay-control"):
        runner.mark_phase_complete(state_path, phase)
    corr = runner.allocate_attempt_directory(
        capture_root=custody_roots["capture_root"],
        state_path=state_path,
        phase="origin-a",
        kind="correlation_capture",
    )
    prompt = runner.allocate_attempt_directory(
        capture_root=custody_roots["capture_root"],
        state_path=state_path,
        phase="origin-a",
        kind="post_new_prompt",
    )
    assert corr.name == "origin-a-1"
    assert prompt.name.endswith("-1")
    state = runner.load_phase_state(state_path)
    assert state["next_ordinal"]["correlation_capture"] == 2
    assert state["next_ordinal"]["post_new_prompt"] == 2


def test_permanent_vs_transient_classification_fields(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    state_path = custody_roots["capture_root"] / "plan117-custody-state.json"
    runner.init_phase_state(state_path)
    for phase in ("direct-control", "relay-control"):
        runner.mark_phase_complete(state_path, phase)
    attempt = runner.allocate_attempt_directory(
        capture_root=custody_roots["capture_root"],
        state_path=state_path,
        phase="origin-a",
        kind="post_new_prompt",
    )
    manifest = runner.write_attempt_manifest(
        attempt_dir=attempt,
        phase="origin-a",
        kind="post_new_prompt",
        ordinal=1,
        failure_class="transient",
        reason_code="gateway_timeout",
        classification_evidence={"http_status": 504, "retryable": True},
    )
    assert manifest["failure_class"] == "transient"
    assert manifest["classification_evidence"]["retryable"] is True
    permanent = runner.write_attempt_manifest(
        attempt_dir=attempt / "nested-permanent",
        phase="origin-a",
        kind="post_new_prompt",
        ordinal=2,
        failure_class="permanent",
        reason_code="model_refusal",
        classification_evidence={"http_status": 400, "retryable": False},
    )
    assert permanent["failure_class"] == "permanent"
    assert (attempt / "attempt-manifest.json").is_file()


# --- Process observation ------------------------------------------------------


def test_powershell_cim_process_records_limited_to_requested_pids(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    fake_stdout = json.dumps(
        [
            {
                "ProcessId": 101,
                "ParentProcessId": 100,
                "CreationDate": "20260802120000.000000-000",
                "ExecutablePath": "C:\\\\Zed\\\\zed.exe",
                "CommandLine": "zed.exe --workspace secret-token",
            },
            {
                "ProcessId": 999,
                "ParentProcessId": 1,
                "CreationDate": "20260802120000.000000-000",
                "ExecutablePath": "C:\\\\Other\\\\other.exe",
                "CommandLine": "other",
            },
        ]
    )

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert argv[0].lower().endswith("powershell") or argv[0].lower() == "powershell.exe"
        assert "-NoProfile" in argv
        assert any("Get-CimInstance" in part for part in argv)
        return subprocess.CompletedProcess(argv, 0, stdout=fake_stdout, stderr="")

    records = runner.capture_process_records(
        pids=(101,),
        output_path=custody_roots["capture_root"] / "process-record.json",
        subprocess_run=fake_run,
    )
    assert len(records) == 1
    record = records[0]
    assert set(record) == {
        "pid",
        "parent_process_id",
        "creation_date",
        "executable_path",
        "command_line_sha256",
    }
    assert record["pid"] == 101
    assert record["command_line_sha256"] == _sha256_bytes(
        b"zed.exe --workspace secret-token"
    )
    assert "CommandLine" not in record
    assert "secret-token" not in json.dumps(record)


def test_complete_process_tree_exit_required_before_restart_b(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()

    def still_alive(pids: tuple[int, ...], **kwargs: Any) -> list[dict[str, Any]]:
        return [{"pid": pids[0], "parent_process_id": 1, "creation_date": "x", "executable_path": "z", "command_line_sha256": "a" * 64}]

    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.require_process_tree_exited(
            pids=(42, 43),
            query=still_alive,
        )
    assert exc.value.reason_code == "process_tree_still_alive"

    def gone(pids: tuple[int, ...], **kwargs: Any) -> list[dict[str, Any]]:
        return []

    runner.require_process_tree_exited(pids=(42, 43), query=gone)


# --- Approval equality --------------------------------------------------------


def test_read_durable_approval_uses_keyring_store_hmac_path(
    custody_roots: dict[str, Path],
) -> None:
    """Producer must call existing KeyringApprovalStore.read_durable (HMAC path)."""

    from optimus.acp.launch_approvals import (
        LAUNCH_POLICY_COMPATIBILITY,
        KeyringApprovalStore,
        build_approval_record,
    )
    from optimus.acp.trusted_paths import resolve_workspace_identity
    from tests.unit.acp.conftest import FakeKeyring

    runner = _import_runner()
    workspace = custody_roots["workspace_root"]
    runtime = workspace / ".optimus"
    runtime.mkdir(parents=True, exist_ok=True)
    fake = FakeKeyring()
    hmac_key = b"plan117-task3-store-hmac-key-32b!"
    store = KeyringApprovalStore(
        keyring_backend=fake,
        runtime_root=runtime,
        hmac_key=hmac_key,
    )
    identity = resolve_workspace_identity(workspace)
    record = build_approval_record(
        mode="durable",
        workspace_identity=identity,
        security_literals={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        secret_fingerprints={"OPTIMUS_API_KEY": "fp_test"},
        monotonic_grants={"OPTIMUS_LIVE_MAX_COST_USD": "0.25"},
        model_observation="claude-haiku",
        hmac_key=hmac_key,
    )
    store.write_durable(record)

    projected = runner.read_durable_approval_projection(
        workspace_root=workspace,
        keyring_backend=fake,
        store_runtime_root=runtime,
        hmac_key=hmac_key,
    )
    assert projected["approval_id"] == record.approval_id
    assert projected["mode"] == "durable"
    assert projected["workspace_digest"] == identity.digest
    assert projected["security_snapshot_digest"] == record.security_snapshot_digest
    assert projected["policy_compatibility"] == LAUNCH_POLICY_COMPATIBILITY
    assert projected["record_hmac_verified"] is True
    assert "record_hmac" not in projected  # never promote raw HMAC


def test_read_launch_audit_suffix_parses_real_ndjson(
    custody_roots: dict[str, Path],
) -> None:
    from datetime import UTC, datetime

    from optimus.acp.launch_approvals import LAUNCH_POLICY_COMPATIBILITY
    from optimus.acp.launch_audit import LaunchAuditEvent, append_launch_audit_event

    runner = _import_runner()
    workspace = custody_roots["workspace_root"]
    runtime = workspace / ".optimus"
    runtime.mkdir(parents=True, exist_ok=True)
    event = LaunchAuditEvent(
        timestamp=datetime.now(UTC),
        workspace_digest="b" * 64,
        launch_session_id="launch-direct-1",
        approval_id="apr-live-1",
        approval_mode="durable",
        registry_version=LAUNCH_POLICY_COMPATIBILITY,
        policy_version=LAUNCH_POLICY_COMPATIBILITY,
        setting_decisions=({"name": "x", "tier": "deny", "source_class": "s", "decision": "d"},),
        monotonic_dispositions=(),
        rejected_names=(),
        child_propagation_decisions={"agent_child": ("A",), "gateway_child": ("B",)},
        diagnostic_grant_state="none",
        sanitizer_rule_counts={},
        final_reason_code="AUTHORIZED",
    )
    append_launch_audit_event(event, runtime_root=runtime)

    projected = runner.read_launch_audit_suffix(
        runtime_root=runtime,
        launch_session_id="launch-direct-1",
    )
    assert projected["approval_id"] == "apr-live-1"
    assert projected["approval_mode"] == "durable"
    assert projected["workspace_digest"] == "b" * 64
    assert projected["final_reason_code"] == "AUTHORIZED"
    assert projected["policy_version"] == LAUNCH_POLICY_COMPATIBILITY
    assert projected["launch_session_id"] == "launch-direct-1"


def test_prove_direct_relay_approval_equivalence_from_real_store_and_audit(
    custody_roots: dict[str, Path],
) -> None:
    from datetime import UTC, datetime

    from optimus.acp.launch_approvals import LAUNCH_POLICY_COMPATIBILITY, KeyringApprovalStore, build_approval_record
    from optimus.acp.launch_audit import LaunchAuditEvent, append_launch_audit_event
    from optimus.acp.trusted_paths import resolve_workspace_identity
    from tests.unit.acp.conftest import FakeKeyring

    runner = _import_runner()
    workspace = custody_roots["workspace_root"]
    runtime = workspace / ".optimus"
    runtime.mkdir(parents=True, exist_ok=True)
    fake = FakeKeyring()
    hmac_key = b"plan117-task3-store-hmac-key-32b!"
    store = KeyringApprovalStore(
        keyring_backend=fake,
        runtime_root=runtime,
        hmac_key=hmac_key,
    )
    identity = resolve_workspace_identity(workspace)
    record = build_approval_record(
        mode="durable",
        workspace_identity=identity,
        security_literals={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        secret_fingerprints={"OPTIMUS_API_KEY": "fp_test"},
        monotonic_grants={"OPTIMUS_LIVE_MAX_COST_USD": "0.25"},
        model_observation="claude-haiku",
        hmac_key=hmac_key,
    )
    store.write_durable(record)

    for session_id in ("launch-direct-1", "launch-relay-1"):
        append_launch_audit_event(
            LaunchAuditEvent(
                timestamp=datetime.now(UTC),
                workspace_digest=identity.digest,
                launch_session_id=session_id,
                approval_id=record.approval_id,
                approval_mode="durable",
                registry_version=LAUNCH_POLICY_COMPATIBILITY,
                policy_version=LAUNCH_POLICY_COMPATIBILITY,
                setting_decisions=(),
                monotonic_dispositions=(),
                rejected_names=(),
                child_propagation_decisions={"agent_child": (), "gateway_child": ()},
                diagnostic_grant_state="none",
                final_reason_code="AUTHORIZED",
            ),
            runtime_root=runtime,
        )

    out = custody_roots["capture_root"] / "approval-equivalence-live.json"
    result = runner.prove_direct_relay_approval_equivalence(
        workspace_root=workspace,
        runtime_root=runtime,
        direct_launch_session_id="launch-direct-1",
        relay_launch_session_id="launch-relay-1",
        output_path=out,
        keyring_backend=fake,
        store_runtime_root=runtime,
        hmac_key=hmac_key,
    )
    assert result["equivalent"] is True
    assert result["approval_id"] == record.approval_id
    assert result["security_snapshot_digest"] == record.security_snapshot_digest
    assert result["record_hmac_verified"] is True
    assert out.is_file()
    assert b"\r" not in out.read_bytes()


def test_prove_direct_relay_approval_equivalence_rejects_mismatched_audit(
    custody_roots: dict[str, Path],
) -> None:
    from datetime import UTC, datetime

    from optimus.acp.launch_approvals import (
        LAUNCH_POLICY_COMPATIBILITY,
        KeyringApprovalStore,
        build_approval_record,
    )
    from optimus.acp.launch_audit import LaunchAuditEvent, append_launch_audit_event
    from optimus.acp.trusted_paths import resolve_workspace_identity
    from tests.unit.acp.conftest import FakeKeyring

    runner = _import_runner()
    workspace = custody_roots["workspace_root"]
    runtime = workspace / ".optimus"
    runtime.mkdir(parents=True, exist_ok=True)
    fake = FakeKeyring()
    hmac_key = b"plan117-task3-store-hmac-key-32b!"
    store = KeyringApprovalStore(
        keyring_backend=fake,
        runtime_root=runtime,
        hmac_key=hmac_key,
    )
    identity = resolve_workspace_identity(workspace)
    record = build_approval_record(
        mode="durable",
        workspace_identity=identity,
        security_literals={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        secret_fingerprints={"OPTIMUS_API_KEY": "fp_test"},
        monotonic_grants={"OPTIMUS_LIVE_MAX_COST_USD": "0.25"},
        model_observation="claude-haiku",
        hmac_key=hmac_key,
    )
    store.write_durable(record)
    append_launch_audit_event(
        LaunchAuditEvent(
            timestamp=datetime.now(UTC),
            workspace_digest=identity.digest,
            launch_session_id="launch-direct-1",
            approval_id=record.approval_id,
            approval_mode="durable",
            registry_version=LAUNCH_POLICY_COMPATIBILITY,
            policy_version=LAUNCH_POLICY_COMPATIBILITY,
            setting_decisions=(),
            monotonic_dispositions=(),
            rejected_names=(),
            child_propagation_decisions={"agent_child": (), "gateway_child": ()},
            diagnostic_grant_state="none",
            final_reason_code="AUTHORIZED",
        ),
        runtime_root=runtime,
    )
    append_launch_audit_event(
        LaunchAuditEvent(
            timestamp=datetime.now(UTC),
            workspace_digest=identity.digest,
            launch_session_id="launch-relay-bad",
            approval_id="apr-OTHER",
            approval_mode="durable",
            registry_version=LAUNCH_POLICY_COMPATIBILITY,
            policy_version=LAUNCH_POLICY_COMPATIBILITY,
            setting_decisions=(),
            monotonic_dispositions=(),
            rejected_names=(),
            child_propagation_decisions={"agent_child": (), "gateway_child": ()},
            diagnostic_grant_state="none",
            final_reason_code="AUTHORIZED",
        ),
        runtime_root=runtime,
    )
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.prove_direct_relay_approval_equivalence(
            workspace_root=workspace,
            runtime_root=runtime,
            direct_launch_session_id="launch-direct-1",
            relay_launch_session_id="launch-relay-bad",
            output_path=custody_roots["capture_root"] / "approval-equivalence-bad-live.json",
            keyring_backend=fake,
            store_runtime_root=runtime,
            hmac_key=hmac_key,
        )
    assert exc.value.reason_code == "invalid_probe_relay_environment_mismatch"


def test_read_durable_and_audit_error_paths(custody_roots: dict[str, Path], tmp_path: Path) -> None:
    from tests.unit.acp.conftest import FakeKeyring

    runner = _import_runner()
    missing_ws = tmp_path / "no-such-workspace"
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.read_durable_approval_projection(
            workspace_root=missing_ws,
            keyring_backend=FakeKeyring(),
            store_runtime_root=tmp_path / "rt",
            hmac_key=b"plan117-task3-store-hmac-key-32b!",
        )
    assert exc.value.reason_code == "workspace_identity_unavailable"

    workspace = custody_roots["workspace_root"]
    runtime = workspace / ".optimus"
    runtime.mkdir(parents=True, exist_ok=True)
    with pytest.raises(runner.CustodyRunnerError) as exc2:
        runner.read_durable_approval_projection(
            workspace_root=workspace,
            keyring_backend=FakeKeyring(),
            store_runtime_root=runtime,
            hmac_key=b"plan117-task3-store-hmac-key-32b!",
        )
    assert exc2.value.reason_code == "durable_approval_missing"

    with pytest.raises(runner.CustodyRunnerError) as exc3:
        runner.read_launch_audit_suffix(runtime_root=runtime, launch_session_id="missing")
    assert exc3.value.reason_code == "launch_audit_missing"

    (runtime / "launch-audit.ndjson").write_text("{not-json\n", encoding="utf-8")
    with pytest.raises(runner.CustodyRunnerError) as exc4:
        runner.read_launch_audit_suffix(runtime_root=runtime, launch_session_id="x")
    assert exc4.value.reason_code == "launch_audit_invalid_json"

    (runtime / "launch-audit.ndjson").write_text(
        json.dumps({"launch_session_id": "other", "final_reason_code": "DENIED"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(runner.CustodyRunnerError) as exc5:
        runner.read_launch_audit_suffix(runtime_root=runtime, launch_session_id="wanted")
    assert exc5.value.reason_code == "launch_audit_event_missing"

    bad_rt = tmp_path / "not-a-dir"
    bad_rt.write_text("x", encoding="utf-8")
    with pytest.raises(runner.CustodyRunnerError) as exc6:
        runner.read_launch_audit_suffix(runtime_root=bad_rt)
    assert exc6.value.reason_code == "launch_audit_runtime_unavailable"


def test_direct_relay_approval_equality_against_durable_fields(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    durable = {
        "approval_id": "apr-1",
        "mode": "durable",
        "security_snapshot_digest": "a" * 64,
        "workspace_digest": "b" * 64,
        "policy_compatibility": "launch-policy-v1",
        "record_hmac_verified": True,
    }
    audit_direct = {
        "approval_id": "apr-1",
        "approval_mode": "durable",
        "workspace_digest": "b" * 64,
        "final_reason_code": "AUTHORIZED",
        "security_snapshot_digest": "a" * 64,
        "policy_compatibility": "launch-policy-v1",
    }
    audit_relay = dict(audit_direct)
    result = runner.compare_approval_equality(
        durable_approval=durable,
        direct_audit=audit_direct,
        relay_audit=audit_relay,
        output_path=custody_roots["capture_root"] / "approval-equivalence.json",
    )
    assert result["equivalent"] is True
    assert result["compared_fields"] == [
        "approval_id",
        "mode",
        "security_snapshot_digest",
        "workspace_digest",
        "policy_compatibility",
        "record_hmac_verified",
        "final_reason_code",
    ]

    mismatched = dict(audit_relay)
    mismatched["security_snapshot_digest"] = "c" * 64
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.compare_approval_equality(
            durable_approval=durable,
            direct_audit=audit_direct,
            relay_audit=mismatched,
            output_path=custody_roots["capture_root"] / "approval-equivalence-bad.json",
        )
    assert exc.value.reason_code == "invalid_probe_relay_environment_mismatch"


# --- Transcript / debug -------------------------------------------------------


def test_completed_copy_transcript_parsing_only_after_relay_termination(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    raw = (
        b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
        b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":1}}\n'
    )
    bin_path = custody_roots["capture_root"] / "zed-to-agent.bin"
    bin_path.write_bytes(raw)
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.parse_completed_transcript(
            bin_path,
            relay_terminated=False,
            output_path=custody_roots["capture_root"] / "projection.json",
        )
    assert exc.value.reason_code == "relay_not_terminated"

    projection = runner.parse_completed_transcript(
        bin_path,
        relay_terminated=True,
        output_path=custody_roots["capture_root"] / "projection.json",
    )
    assert projection["messages"][0]["method"] == "initialize"
    assert projection["messages"][0]["id"] == 1


def test_exact_relay_debug_method_id_order_terminal_interval_agreement(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    projection = {
        "messages": [
            {"method": "initialize", "id": 1, "has_result": True, "has_error": False},
            {"method": "session/new", "id": 2, "has_result": True, "has_error": False},
            {
                "method": "session/prompt",
                "id": 3,
                "has_result": True,
                "has_error": False,
                "stop_reason": "end_turn",
            },
        ],
        "ordered_update_types": ["agent_message_chunk"],
        "server_session_id": "sess-1",
        "interval": {"start_ns": 10, "end_ns": 20},
    }
    debug_suffix = {
        "messages": [
            {"method": "initialize", "id": 1, "has_result": True, "has_error": False},
            {"method": "session/new", "id": 2, "has_result": True, "has_error": False},
            {
                "method": "session/prompt",
                "id": 3,
                "has_result": True,
                "has_error": False,
                "stop_reason": "end_turn",
            },
        ],
        "ordered_update_types": ["agent_message_chunk"],
        "server_session_id": "sess-1",
        "interval": {"start_ns": 10, "end_ns": 20},
    }
    runner.compare_transcript_debug(
        projection=projection,
        debug_suffix=debug_suffix,
        output_path=custody_roots["capture_root"] / "transcript-debug-agree.json",
    )
    bad = dict(debug_suffix)
    bad["messages"] = list(debug_suffix["messages"])
    bad["messages"][1] = dict(bad["messages"][1], id=99)
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.compare_transcript_debug(
            projection=projection,
            debug_suffix=bad,
            output_path=custody_roots["capture_root"] / "transcript-debug-bad.json",
        )
    assert exc.value.reason_code == "invalid_probe_transcript_debug_divergence"


# --- Forbidden APIs / operator instructions -----------------------------------


def test_no_forbidden_imports_or_apis() -> None:
    runner = _import_runner()
    source = RUNNER_PATH.read_text(encoding="utf-8")
    for token in FORBIDDEN_TOKENS:
        assert token not in source
    assert "SendInput" not in dir(runner)
    assert not hasattr(runner, "evidence_gather_support")
    # AST import graph: runner must not import forbidden modules.
    import ast

    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden_modules = {
        "acpx",
        "pyautogui",
        "uiautomation",
        "tools.evidence_gather_support",
    }
    assert imported.isdisjoint(forbidden_modules)


def test_operator_instructions_print_exact_prompt_and_labels(
    custody_roots: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _import_runner()
    runner.print_origin_a_instructions()
    out = capsys.readouterr().out
    assert "Read README.md and answer with one sentence naming this project." in out
    assert PROMPT_SHA256_UPPER in out.upper()

    runner.print_restart_b_instructions()
    out_b = capsys.readouterr().out
    assert "prior-thread" in out_b.lower() or "prior thread" in out_b.lower()
    assert "New Optimus Thread" in out_b

    runner.print_fresh_control_c_instructions()
    out_c = capsys.readouterr().out
    assert "new" in out_c.lower() and "thread" in out_c.lower()

    observation = runner.record_operator_assertion(
        output_path=custody_roots["capture_root"] / "operator-assertion.json",
        phase="restart-b",
        label="prior_thread_affordance_absent",
        detail="only New Optimus Thread was offered",
    )
    assert observation["asserted"] is True
    assert observation["machine_proof"] is False


def test_json_artifacts_use_atomic_write_json(
    custody_roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _import_runner()
    calls: list[Path] = []
    real = runner.atomic_write_json

    def tracking(path: Path, payload: dict[str, Any]) -> None:
        calls.append(path)
        real(path, payload)

    monkeypatch.setattr(runner, "atomic_write_json", tracking)
    state_path = custody_roots["capture_root"] / "plan117-custody-state.json"
    runner.init_phase_state(state_path)
    assert state_path in calls
    text = state_path.read_bytes()
    assert b"\r\n" not in text


def test_cli_phases_accepted() -> None:
    runner = _import_runner()
    assert set(runner.PHASES) == set(PHASES)
    # finalize requires evidence-capture-root and result
    with pytest.raises(SystemExit):
        runner.main(
            [
                "finalize",
                "--workspace-root",
                str(ROOT),
                "--capture-root",
                str(ROOT / "reports"),
                "--zed-executable",
                str(ROOT / "README.md"),
                "--zed-source",
                str(ROOT),
                "--settings-path",
                str(ROOT / "README.md"),
                "--debug-log",
                str(ROOT / "README.md"),
            ]
        )


def test_writer_discipline_no_ad_hoc_json_dump_in_runner() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    # Allow importing json for loads/parsing; forbid dump/write_text of JSON artifacts.
    assert "json.dump(" not in source
    assert ".write_text(" not in source or "atomic_write" in source


def test_main_phases_and_finalize_gate(custody_roots: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
    runner = _import_runner()
    settings = custody_roots["settings_path"]
    manifest = custody_roots["capture_root"] / "private-run-manifest.json"
    runner.atomic_write_json(
        manifest,
        {
            "schema": "plan117-custody-private-run-manifest-v1",
            "settings_mutation_approval": _approval(
                settings_path=settings,
                pre_image_sha256=_sha256_bytes(settings.read_bytes()),
            ),
            "relay": {"command": "python", "args": ["relay.py"]},
        },
    )
    common = [
        "--workspace-root",
        str(custody_roots["workspace_root"]),
        "--capture-root",
        str(custody_roots["capture_root"]),
        "--zed-executable",
        str(custody_roots["zed_executable"]),
        "--zed-source",
        str(custody_roots["zed_source"]),
        "--settings-path",
        str(settings),
        "--debug-log",
        str(custody_roots["debug_log"]),
        "--custody-root",
        str(custody_roots["custody_root"]),
        "--private-run-manifest",
        str(manifest),
        "--no-operator-wait",
    ]
    assert runner.main(["direct-control", *common]) == 0
    # refresh approval digest after any prior mutation/restore
    runner.atomic_write_json(
        manifest,
        {
            "schema": "plan117-custody-private-run-manifest-v1",
            "settings_mutation_approval": _approval(
                settings_path=settings,
                pre_image_sha256=_sha256_bytes(settings.read_bytes()),
            ),
            "relay": {"command": "python", "args": ["relay.py"]},
        },
    )
    assert runner.main(["relay-control", *common]) == 0
    runner.atomic_write_json(
        manifest,
        {
            "schema": "plan117-custody-private-run-manifest-v1",
            "settings_mutation_approval": _approval(
                settings_path=settings,
                pre_image_sha256=_sha256_bytes(settings.read_bytes()),
            ),
            "relay": {"command": "python", "args": ["relay.py"]},
        },
    )
    assert runner.main(["origin-a", *common]) == 0
    out = capsys.readouterr().out
    assert PROMPT_SHA256_UPPER in out.upper()
    assert runner.main(["restart-b", *common]) == 0
    assert runner.main(["fresh-control-c", *common]) == 0
    assert runner.main(["direct-ancestry-control", *common]) == 0
    assert runner.main(["restore-settings", *common]) == 0
    assert (
        runner.main(
            [
                "finalize",
                *common,
                "--evidence-capture-root",
                str(custody_roots["capture_root"]),
                "--result",
                str(custody_roots["capture_root"] / "result.json"),
            ]
        )
        == 0
    )


def test_main_restore_settings_phase_restores_active_tx(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    settings = custody_roots["settings_path"]
    original = settings.read_bytes()
    proof = runner.mutate_settings_insert_relay(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        relay_command="python",
        relay_args=["relay.py"],
        approval=_approval(settings_path=settings, pre_image_sha256=_sha256_bytes(original)),
        agent_server_name="optimus",
    )
    assert settings.read_bytes() != original
    code = runner.main(
        [
            "restore-settings",
            "--workspace-root",
            str(custody_roots["workspace_root"]),
            "--capture-root",
            str(custody_roots["capture_root"]),
            "--zed-executable",
            str(custody_roots["zed_executable"]),
            "--zed-source",
            str(custody_roots["zed_source"]),
            "--settings-path",
            str(settings),
            "--debug-log",
            str(custody_roots["debug_log"]),
            "--custody-root",
            str(custody_roots["custody_root"]),
        ]
    )
    assert code == 0
    assert settings.read_bytes() == original
    assert proof["mutated_sha256"]


def test_approval_path_and_digest_mismatch_gates(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    settings = custody_roots["settings_path"]
    pre = _sha256_bytes(settings.read_bytes())
    wrong_path = _approval(settings_path=settings.parent / "other.json", pre_image_sha256=pre)
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.mutate_settings_insert_relay(
            settings_path=settings,
            custody_root=custody_roots["custody_root"],
            relay_command="python",
            relay_args=[],
            approval=wrong_path,
            agent_server_name="optimus",
        )
    assert exc.value.reason_code == "settings_mutation_approval_path_mismatch"
    wrong_digest = _approval(settings_path=settings, pre_image_sha256="0" * 64)
    with pytest.raises(runner.CustodyRunnerError) as exc2:
        runner.mutate_settings_insert_relay(
            settings_path=settings,
            custody_root=custody_roots["custody_root"],
            relay_command="python",
            relay_args=[],
            approval=wrong_digest,
            agent_server_name="optimus",
        )
    assert exc2.value.reason_code == "settings_mutation_approval_digest_mismatch"


def test_empty_pid_query_and_invalid_transcript(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    assert (
        runner.capture_process_records(
            pids=(),
            output_path=custody_roots["capture_root"] / "empty-proc.json",
        )
        == []
    )
    bad = custody_roots["capture_root"] / "bad.bin"
    bad.write_bytes(b"\xff\xfe not utf8")
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.parse_completed_transcript(
            bad,
            relay_terminated=True,
            output_path=custody_roots["capture_root"] / "bad-proj.json",
        )
    assert exc.value.reason_code == "invalid_probe_transcript_utf8"
    framed = custody_roots["capture_root"] / "framed.bin"
    framed.write_bytes(b"{not-json\n")
    with pytest.raises(runner.CustodyRunnerError) as exc2:
        runner.parse_completed_transcript(
            framed,
            relay_terminated=True,
            output_path=custody_roots["capture_root"] / "framed-proj.json",
        )
    assert exc2.value.reason_code == "invalid_probe_transcript_framing"


def test_phase_state_schema_and_unknown_phase(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    state_path = custody_roots["capture_root"] / "bad-state.json"
    from tools.plan117_custody_contract import atomic_write_json

    atomic_write_json(state_path, {"schema": "wrong", "completed_phases": []})
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.load_phase_state(state_path)
    assert exc.value.reason_code == "invalid_phase_state_schema"
    state = runner.init_phase_state(custody_roots["capture_root"] / "ok-state.json")
    with pytest.raises(runner.CustodyRunnerError) as exc2:
        runner.assert_phase_allowed(state, "not-a-phase")
    assert exc2.value.reason_code == "unknown_phase"


def test_attempt_budget_and_unknown_kind(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    state_path = custody_roots["capture_root"] / "budget-state.json"
    runner.init_phase_state(state_path)
    for phase in ("direct-control", "relay-control"):
        runner.mark_phase_complete(state_path, phase)
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.allocate_attempt_directory(
            capture_root=custody_roots["capture_root"],
            state_path=state_path,
            phase="origin-a",
            kind="not-a-kind",
        )
    assert exc.value.reason_code == "unknown_attempt_kind"
    state = runner.load_phase_state(state_path)
    state["next_ordinal"]["correlation_capture"] = 4
    runner.save_phase_state(state_path, state)
    with pytest.raises(runner.CustodyRunnerError) as exc2:
        runner.allocate_attempt_directory(
            capture_root=custody_roots["capture_root"],
            state_path=state_path,
            phase="origin-a",
            kind="correlation_capture",
        )
    assert exc2.value.reason_code == "attempt_budget_exceeded"


def test_approval_equality_hmac_and_reason_gates(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    durable = {
        "approval_id": "apr-1",
        "mode": "durable",
        "security_snapshot_digest": "a" * 64,
        "workspace_digest": "b" * 64,
        "policy_compatibility": "launch-policy-v1",
        "record_hmac_verified": False,
    }
    audit = {
        "approval_id": "apr-1",
        "approval_mode": "durable",
        "workspace_digest": "b" * 64,
        "final_reason_code": "AUTHORIZED",
        "security_snapshot_digest": "a" * 64,
        "policy_compatibility": "launch-policy-v1",
    }
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.compare_approval_equality(
            durable_approval=durable,
            direct_audit=audit,
            relay_audit=audit,
            output_path=custody_roots["capture_root"] / "eq-hmac.json",
        )
    assert exc.value.reason_code == "invalid_probe_relay_environment_mismatch"
    durable["record_hmac_verified"] = True
    bad_reason = dict(audit, final_reason_code="DENIED")
    with pytest.raises(runner.CustodyRunnerError):
        runner.compare_approval_equality(
            durable_approval=durable,
            direct_audit=bad_reason,
            relay_audit=audit,
            output_path=custody_roots["capture_root"] / "eq-denied.json",
        )


def test_transcript_session_update_projection(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    raw = (
        b'{"jsonrpc":"2.0","id":1,"method":"session/new","result":{"sessionId":"s1"}}\n'
        b'{"jsonrpc":"2.0","method":"session/update","params":{"update":{"sessionUpdate":"agent_message_chunk"}}}\n'
        b'{"jsonrpc":"2.0","id":2,"method":"session/prompt","result":{"stopReason":"end_turn"}}\n'
    )
    path = custody_roots["capture_root"] / "updates.bin"
    path.write_bytes(raw)
    projection = runner.parse_completed_transcript(
        path,
        relay_terminated=True,
        output_path=custody_roots["capture_root"] / "updates-proj.json",
    )
    assert projection["server_session_id"] == "s1"
    assert projection["ordered_update_types"] == ["agent_message_chunk"]
    assert projection["messages"][2]["stop_reason"] == "end_turn"


def test_resolve_paths_accepts_approved_settings(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    paths = runner.resolve_probe_paths(
        workspace_root=custody_roots["workspace_root"],
        capture_root=custody_roots["capture_root"],
        zed_executable=custody_roots["zed_executable"],
        zed_source=custody_roots["zed_source"],
        settings_path=custody_roots["settings_path"],
        debug_log=custody_roots["debug_log"],
        custody_root=custody_roots["custody_root"],
        allowed_settings_roots=(custody_roots["settings_path"].parent,),
    )
    assert paths["settings_path"] == custody_roots["settings_path"]


def test_powershell_query_failure(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()

    def boom(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="fail")

    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.capture_process_records(
            pids=(1,),
            output_path=custody_roots["capture_root"] / "proc-fail.json",
            subprocess_run=boom,
        )
    assert exc.value.reason_code == "process_query_failed"


def test_readme_precondition_failures(tmp_path: Path) -> None:
    runner = _import_runner()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.require_readme_precondition(workspace)
    assert exc.value.reason_code == "readme_precondition_failed"


def test_settings_validation_error_paths(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    settings = custody_roots["settings_path"]
    pre = _sha256_bytes(settings.read_bytes())
    empty_op = _approval(settings_path=settings, pre_image_sha256=pre)
    empty_op["operator_identity"] = "  "
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.mutate_settings_insert_relay(
            settings_path=settings,
            custody_root=custody_roots["custody_root"],
            relay_command="python",
            relay_args=[],
            approval=empty_op,
            agent_server_name="optimus",
        )
    assert exc.value.reason_code == "settings_mutation_approval_incomplete"

    settings.write_bytes(b"not-json")
    with pytest.raises(runner.CustodyRunnerError) as exc2:
        runner.mutate_settings_insert_relay(
            settings_path=settings,
            custody_root=custody_roots["custody_root"],
            relay_command="python",
            relay_args=[],
            approval=_approval(settings_path=settings, pre_image_sha256=_sha256_bytes(b"not-json")),
            agent_server_name="optimus",
        )
    assert exc2.value.reason_code == "settings_json_invalid"

    _write_settings(settings, {"agent_servers": []})
    with pytest.raises(runner.CustodyRunnerError) as exc3:
        runner.mutate_settings_insert_relay(
            settings_path=settings,
            custody_root=custody_roots["custody_root"],
            relay_command="python",
            relay_args=[],
            approval=_approval(
                settings_path=settings,
                pre_image_sha256=_sha256_bytes(settings.read_bytes()),
            ),
            agent_server_name="optimus",
        )
    assert exc3.value.reason_code == "settings_agent_servers_invalid"

    _write_settings(settings, _optimus_settings())
    with pytest.raises(runner.CustodyRunnerError) as exc4:
        runner.mutate_settings_insert_relay(
            settings_path=settings,
            custody_root=custody_roots["custody_root"],
            relay_command="python",
            relay_args=[],
            approval=_approval(
                settings_path=settings,
                pre_image_sha256=_sha256_bytes(settings.read_bytes()),
            ),
            agent_server_name="other",
        )
    assert exc4.value.reason_code == "settings_agent_server_not_allowlisted"

    settings.unlink()
    with pytest.raises(runner.CustodyRunnerError) as exc5:
        runner.mutate_settings_insert_relay(
            settings_path=settings,
            custody_root=custody_roots["custody_root"],
            relay_command="python",
            relay_args=[],
            approval=_approval(settings_path=settings, pre_image_sha256=None),
            agent_server_name="optimus",
            create_if_absent=False,
        )
    assert exc5.value.reason_code == "settings_absent"


def test_restore_missing_transaction_and_path_mismatch(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.restore_settings(
            settings_path=custody_roots["settings_path"],
            custody_root=custody_roots["custody_root"],
            expected_mutated_sha256="a" * 64,
        )
    assert exc.value.reason_code == "settings_transaction_missing"

    settings = custody_roots["settings_path"]
    original = settings.read_bytes()
    proof = runner.mutate_settings_insert_relay(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        relay_command="python",
        relay_args=["relay.py"],
        approval=_approval(settings_path=settings, pre_image_sha256=_sha256_bytes(original)),
        agent_server_name="optimus",
    )
    other = custody_roots["custody_root"] / "other-settings.json"
    other.write_bytes(settings.read_bytes())
    with pytest.raises(runner.CustodyRunnerError) as exc2:
        runner.restore_settings(
            settings_path=other,
            custody_root=custody_roots["custody_root"],
            expected_mutated_sha256=proof["mutated_sha256"],
        )
    assert exc2.value.reason_code == "settings_path_mismatch"


def test_symlink_rejection_via_mock(custody_roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _import_runner()
    target = custody_roots["settings_path"]

    class _Sym(type(target)):
        def is_symlink(self) -> bool:  # type: ignore[override]
            return True

    linked = _Sym(target)
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.require_regular_non_symlink(linked, label="settings_path")
    assert exc.value.reason_code == "symlink_forbidden"

    with pytest.raises(runner.CustodyRunnerError) as exc2:
        runner.mutate_settings_insert_relay(
            settings_path=linked,
            custody_root=custody_roots["custody_root"],
            relay_command="python",
            relay_args=[],
            approval=_approval(settings_path=target, pre_image_sha256="a" * 64),
            agent_server_name="optimus",
        )
    assert exc2.value.reason_code == "symlink_forbidden"


def test_approval_field_mismatches(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    durable = {
        "approval_id": "apr-1",
        "mode": "durable",
        "security_snapshot_digest": "a" * 64,
        "workspace_digest": "b" * 64,
        "policy_compatibility": "launch-policy-v1",
        "record_hmac_verified": True,
    }
    good = {
        "approval_id": "apr-1",
        "approval_mode": "durable",
        "workspace_digest": "b" * 64,
        "final_reason_code": "AUTHORIZED",
        "security_snapshot_digest": "a" * 64,
        "policy_compatibility": "launch-policy-v1",
    }
    for field, value in (
        ("approval_id", "apr-x"),
        ("approval_mode", "one-shot"),
        ("workspace_digest", "c" * 64),
        ("policy_compatibility", "other"),
    ):
        bad = dict(good)
        bad[field] = value
        with pytest.raises(runner.CustodyRunnerError):
            runner.compare_approval_equality(
                durable_approval=durable,
                direct_audit=bad,
                relay_audit=good,
                output_path=custody_roots["capture_root"] / f"eq-{field}.json",
            )


def test_process_query_empty_stdout_and_single_object(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()

    def empty(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, stdout="   ", stderr="")

    assert (
        runner.capture_process_records(
            pids=(5,),
            output_path=custody_roots["capture_root"] / "proc-empty.json",
            subprocess_run=empty,
        )
        == []
    )

    def one(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {
                    "ProcessId": 5,
                    "ParentProcessId": 1,
                    "CreationDate": "t",
                    "ExecutablePath": "x",
                    "CommandLine": "y",
                }
            ),
            stderr="",
        )

    records = runner.capture_process_records(
        pids=(5,),
        output_path=custody_roots["capture_root"] / "proc-one.json",
        subprocess_run=one,
    )
    assert len(records) == 1


def test_parse_jsonc_preserves_urls_with_double_slash_inside_strings() -> None:
    runner = _import_runner()
    payload = runner.parse_jsonc(
        "// header\n"
        "{\n"
        '  "db": "postgresql://myuser:secret@localhost:5432/db",\n'
        '  "agent_servers": {"optimus": {"command": "x", "args": [],}},\n'
        "}\n"
    )
    assert payload["db"] == "postgresql://myuser:secret@localhost:5432/db"
    assert "// header" not in json.dumps(payload)


def test_relay_control_holds_mutation_until_operator_wait_returns(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    settings = custody_roots["settings_path"]
    original = settings.read_bytes()
    manifest = custody_roots["capture_root"] / "private-run-manifest.json"
    runner.atomic_write_json(
        manifest,
        {
            "schema": "plan117-custody-private-run-manifest-v1",
            "settings_mutation_approval": _approval(
                settings_path=settings,
                pre_image_sha256=_sha256_bytes(original),
            ),
            "relay": {"command": "python", "args": ["relay.py"]},
        },
    )
    state_path = custody_roots["capture_root"] / "plan117-custody-state.json"
    runner.init_phase_state(state_path)
    runner.mark_phase_complete(state_path, "direct-control")
    seen_mutated = {"value": False}

    def observe(attempt_dir: Path) -> None:
        current = json.loads(settings.read_text(encoding="utf-8"))
        seen_mutated["value"] = current["agent_servers"]["optimus"]["command"] == "python"
        assert attempt_dir.is_dir()

    runner.run_relay_mediated_phase(
        phase="relay-control",
        capture_root=custody_roots["capture_root"],
        state_path=state_path,
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        private_run_manifest=manifest,
        observe=observe,
    )
    assert seen_mutated["value"] is True
    assert settings.read_bytes() == original


def test_operator_continue_wait_accepts_sentinel_file(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    attempt = custody_roots["capture_root"] / "attempts" / "wait-1"
    attempt.mkdir(parents=True)
    sentinel = attempt / "operator-continue.flag"

    def create_soon() -> None:
        import threading
        import time

        def _write() -> None:
            time.sleep(0.2)
            sentinel.write_text("", encoding="utf-8")

        threading.Thread(target=_write, daemon=True).start()

    create_soon()
    runner._operator_continue_wait(attempt, "waiting", timeout_s=5.0, poll_s=0.05)


def test_operator_continue_wait_times_out(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    attempt = custody_roots["capture_root"] / "attempts" / "wait-timeout"
    attempt.mkdir(parents=True)
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner._operator_continue_wait(attempt, "waiting", timeout_s=0.15, poll_s=0.05)
    assert exc.value.reason_code == "operator_wait_timeout"


def test_direct_control_uses_custom_wait_fn(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    state_path = custody_roots["capture_root"] / "plan117-custody-state.json"
    runner.init_phase_state(state_path)
    called = {"n": 0}

    def wait_fn(prompt: str) -> None:
        called["n"] += 1
        assert "direct-control" in prompt

    runner.run_direct_control_phase(
        capture_root=custody_roots["capture_root"],
        state_path=state_path,
        operator_wait=True,
        wait_fn=wait_fn,
    )
    assert called["n"] == 1


def test_compare_transcript_debug_key_mismatch(custody_roots: dict[str, Path]) -> None:
    runner = _import_runner()
    left = {
        "messages": [],
        "ordered_update_types": [],
        "server_session_id": "s",
        "interval": {"start_ns": 1, "end_ns": 2},
    }
    right = dict(left, server_session_id="other")
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.compare_transcript_debug(
            projection=left,
            debug_suffix=right,
            output_path=custody_roots["capture_root"] / "td-bad.json",
        )
    assert exc.value.reason_code == "invalid_probe_transcript_debug_divergence"


def test_load_settings_json_accepts_jsonc_comments_and_trailing_commas(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    settings = custody_roots["settings_path"]
    settings.write_text(
        "// Zed settings\n"
        "{\n"
        '  "theme": "one-dark",\n'
        '  "agent_servers": {\n'
        '    "optimus": {\n'
        '      "type": "custom",\n'
        '      "command": "optimus-agent",\n'
        '      "args": ["--workspace-root", ".",],\n'
        "    },\n"
        "  },\n"
        "}\n",
        encoding="utf-8",
        newline="\n",
    )
    payload = runner._load_settings_json(settings)
    assert payload["theme"] == "one-dark"
    assert payload["agent_servers"]["optimus"]["command"] == "optimus-agent"
    assert payload["agent_servers"]["optimus"]["args"] == ["--workspace-root", "."]


def test_settings_mutation_accepts_uppercase_approval_digest_on_jsonc(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    settings = custody_roots["settings_path"]
    settings.write_text(
        "// header\n"
        '{\n  "agent_servers": {"optimus": {"command": "optimus-agent", "args": ["a"],}},\n'
        '  "keep": true,\n}\n',
        encoding="utf-8",
        newline="\n",
    )
    original = settings.read_bytes()
    pre_upper = hashlib.sha256(original).hexdigest().upper()
    proof = runner.mutate_settings_insert_relay(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        relay_command="python",
        relay_args=["relay.py"],
        approval=_approval(settings_path=settings, pre_image_sha256=pre_upper),
    )
    assert settings.read_bytes() != original
    restored = runner.restore_settings(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        expected_mutated_sha256=proof["mutated_sha256"],
    )
    assert restored["restored"] is True
    assert settings.read_bytes() == original


def test_restore_settings_falls_back_when_direct_replace_permission_denied(
    custody_roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zed often locks settings.json; direct os.replace onto it raises WinError 5.

    Restore must still succeed via rename-away then replace, without leaving the
    mutated bytes as the live settings path.
    """
    import os

    runner = _import_runner()
    settings = custody_roots["settings_path"]
    original = settings.read_bytes()
    pre = _sha256_bytes(original)
    approval = _approval(settings_path=settings, pre_image_sha256=pre)
    proof = runner.mutate_settings_insert_relay(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        relay_command="python",
        relay_args=["relay.py", "--x"],
        approval=approval,
        agent_server_name="optimus",
    )
    mutated = settings.read_bytes()
    assert mutated != original

    real_replace = os.replace
    settings_resolved = settings.resolve()

    def gated_replace(src: os.PathLike[str] | str, dst: os.PathLike[str] | str) -> None:
        src_path = Path(src)
        dst_path = Path(dst)
        # Simulate Zed holding the live path: replacing *onto* settings.json fails.
        if (
            dst_path.resolve() == settings_resolved
            and "partial-" in src_path.name
        ):
            raise PermissionError(5, "Access is denied", str(dst_path))
        real_replace(src, dst)

    monkeypatch.setattr(runner.os, "replace", gated_replace)

    restored = runner.restore_settings(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        expected_mutated_sha256=proof["mutated_sha256"],
    )
    assert restored["restored"] is True
    assert restored["already_restored"] is False
    assert settings.read_bytes() == original
    assert restored["final_sha256"] == pre
    assert restored.get("restore_method") == "rename_away_then_replace"
    meta = json.loads(
        (custody_roots["custody_root"] / "settings-transaction.json").read_text(
            encoding="utf-8"
        )
    )
    assert meta["restored"] is True
    assert meta["final_sha256"] == pre
    assert meta["restore_method"] == "rename_away_then_replace"
    assert meta.get("mutated_backup_path")
    backup = Path(str(meta["mutated_backup_path"]))
    assert backup.is_file()
    assert backup.read_bytes() == mutated


def test_restore_settings_still_fails_when_rename_away_also_blocked(
    custody_roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    runner = _import_runner()
    settings = custody_roots["settings_path"]
    original = settings.read_bytes()
    pre = _sha256_bytes(original)
    proof = runner.mutate_settings_insert_relay(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        relay_command="python",
        relay_args=["relay.py"],
        approval=_approval(settings_path=settings, pre_image_sha256=pre),
    )

    def always_denied(src: os.PathLike[str] | str, dst: os.PathLike[str] | str) -> None:
        raise PermissionError(5, "Access is denied", str(dst))

    monkeypatch.setattr(runner.os, "replace", always_denied)
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.restore_settings(
            settings_path=settings,
            custody_root=custody_roots["custody_root"],
            expected_mutated_sha256=proof["mutated_sha256"],
        )
    assert exc.value.reason_code == "settings_atomic_replace_failed"
    # Mutated bytes must remain; do not claim restored.
    assert settings.read_bytes() != original
    meta = json.loads(
        (custody_roots["custody_root"] / "settings-transaction.json").read_text(
            encoding="utf-8"
        )
    )
    assert meta.get("restored") is False


def test_restore_settings_rollback_when_final_place_fails_after_rename_away(
    custody_roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """If live settings are moved aside but the restored sibling cannot be placed,
    rollback must put the mutated bytes back — never leave settings.json missing.
    """
    import os

    runner = _import_runner()
    settings = custody_roots["settings_path"]
    settings_dir = settings.parent
    original = settings.read_bytes()
    pre = _sha256_bytes(original)
    proof = runner.mutate_settings_insert_relay(
        settings_path=settings,
        custody_root=custody_roots["custody_root"],
        relay_command="python",
        relay_args=["relay.py", "--x"],
        approval=_approval(settings_path=settings, pre_image_sha256=pre),
    )
    mutated = settings.read_bytes()
    assert mutated != original

    real_replace = os.replace
    settings_resolved = settings.resolve()

    def gated_replace(src: os.PathLike[str] | str, dst: os.PathLike[str] | str) -> None:
        src_path = Path(src)
        dst_path = Path(dst)
        dst_resolved = dst_path.resolve()
        # 1) Direct path: replacing onto live from *.partial-* fails (Zed lock).
        if dst_resolved == settings_resolved and "partial-" in src_path.name:
            raise PermissionError(5, "Access is denied", str(dst_path))
        # 2) Fallback final place: replacing onto live from *.restored-* also fails.
        if dst_resolved == settings_resolved and "restored-" in src_path.name:
            raise PermissionError(5, "Access is denied", str(dst_path))
        # Allow: partial->restored sibling, live->mutated-hold, and rollback hold->live.
        real_replace(src, dst)

    monkeypatch.setattr(runner.os, "replace", gated_replace)

    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.restore_settings(
            settings_path=settings,
            custody_root=custody_roots["custody_root"],
            expected_mutated_sha256=proof["mutated_sha256"],
        )
    assert exc.value.reason_code == "settings_atomic_replace_failed"
    assert settings.is_file()
    assert settings.read_bytes() == mutated
    meta = json.loads(
        (custody_roots["custody_root"] / "settings-transaction.json").read_text(
            encoding="utf-8"
        )
    )
    assert meta.get("restored") is False
    leftovers = [
        path
        for path in settings_dir.iterdir()
        if path.is_file()
        and (
            ".partial-" in path.name
            or ".restored-" in path.name
            or ".mutated-hold-" in path.name
        )
    ]
    assert leftovers == [], f"unexpected leftover settings siblings: {leftovers}"


def test_cli_accepts_positional_phase_matching_amendment(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    common = [
        "--workspace-root",
        str(custody_roots["workspace_root"]),
        "--capture-root",
        str(custody_roots["capture_root"]),
        "--zed-executable",
        str(custody_roots["zed_executable"]),
        "--zed-source",
        str(custody_roots["zed_source"]),
        "--settings-path",
        str(custody_roots["settings_path"]),
        "--debug-log",
        str(custody_roots["debug_log"]),
        "--custody-root",
        str(custody_roots["custody_root"]),
        "--no-operator-wait",
    ]
    assert runner.main(["direct-control", *common]) == 0
    attempt = custody_roots["capture_root"] / "attempts" / "direct-control-1"
    assert attempt.is_dir()
    assert (attempt / "attempt-manifest.json").is_file()
    assert (attempt / "phase-observation.json").is_file()


def test_direct_and_relay_control_are_not_noop(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    settings = custody_roots["settings_path"]
    original = settings.read_bytes()
    manifest = custody_roots["capture_root"] / "private-run-manifest.json"
    runner.atomic_write_json(
        manifest,
        {
            "schema": "plan117-custody-private-run-manifest-v1",
            "settings_mutation_approval": _approval(
                settings_path=settings,
                pre_image_sha256=_sha256_bytes(original),
                operator_identity="Vibhanshu Agarwal",
                approved_at_utc="2026-08-02T12:17:15Z",
            ),
            "relay": {"command": "python", "args": ["relay.py", "--x"]},
        },
    )
    common = [
        "--workspace-root",
        str(custody_roots["workspace_root"]),
        "--capture-root",
        str(custody_roots["capture_root"]),
        "--zed-executable",
        str(custody_roots["zed_executable"]),
        "--zed-source",
        str(custody_roots["zed_source"]),
        "--settings-path",
        str(settings),
        "--debug-log",
        str(custody_roots["debug_log"]),
        "--custody-root",
        str(custody_roots["custody_root"]),
        "--private-run-manifest",
        str(manifest),
        "--no-operator-wait",
    ]
    assert runner.main(["direct-control", *common]) == 0
    direct = custody_roots["capture_root"] / "attempts" / "direct-control-1"
    assert (direct / "phase-observation.json").is_file()
    direct_obs = json.loads((direct / "phase-observation.json").read_text(encoding="utf-8"))
    assert direct_obs["settings_mutated"] is False

    assert runner.main(["relay-control", *common]) == 0
    relay = custody_roots["capture_root"] / "attempts" / "relay-control-1"
    assert (relay / "phase-observation.json").is_file()
    relay_obs = json.loads((relay / "phase-observation.json").read_text(encoding="utf-8"))
    assert relay_obs["settings_mutated"] is True
    assert settings.read_bytes() == original
    tx = json.loads(
        (custody_roots["custody_root"] / "settings-transaction.json").read_text(encoding="utf-8")
    )
    assert tx["restored"] is True
    assert set(tx["changed_key_paths"]) == {
        "agent_servers.optimus.command",
        "agent_servers.optimus.args",
    }


def test_relay_control_requires_private_run_manifest(
    custody_roots: dict[str, Path],
) -> None:
    runner = _import_runner()
    # complete direct first
    common = [
        "--workspace-root",
        str(custody_roots["workspace_root"]),
        "--capture-root",
        str(custody_roots["capture_root"]),
        "--zed-executable",
        str(custody_roots["zed_executable"]),
        "--zed-source",
        str(custody_roots["zed_source"]),
        "--settings-path",
        str(custody_roots["settings_path"]),
        "--debug-log",
        str(custody_roots["debug_log"]),
        "--custody-root",
        str(custody_roots["custody_root"]),
        "--no-operator-wait",
    ]
    assert runner.main(["direct-control", *common]) == 0
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.main(["relay-control", *common])
    assert exc.value.reason_code == "private_run_manifest_required"


def test_private_run_manifest_and_relay_config_error_paths(
    custody_roots: dict[str, Path],
    tmp_path: Path,
) -> None:
    runner = _import_runner()
    missing = tmp_path / "nope.json"
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.load_private_run_manifest(missing)
    assert exc.value.reason_code == "private_run_manifest_missing"

    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.load_private_run_manifest(bad)
    assert exc.value.reason_code == "private_run_manifest_invalid"

    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner._approval_from_manifest({})
    assert exc.value.reason_code == "settings_mutation_approval_required"

    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner._relay_from_manifest({})
    assert exc.value.reason_code == "relay_config_missing"
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner._relay_from_manifest({"relay": {"command": "", "args": []}})
    assert exc.value.reason_code == "relay_config_missing"
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner._relay_from_manifest({"relay": {"command": "x", "args": [1]}})
    assert exc.value.reason_code == "relay_config_missing"


def test_parse_jsonc_rejects_still_invalid_payload() -> None:
    runner = _import_runner()
    with pytest.raises(json.JSONDecodeError):
        runner.parse_jsonc("// only comment\nnot-json")


# --- JSONC string-aware trailing-comma safety (Plan 11.7 Task 2) --------------


def test_parse_jsonc_commented_fallback_preserves_comma_bracket_inside_strings() -> None:
    """Realistic Zed settings regression: commented JSONC must not corrupt string values.

    Pre-fix trailing-comma pass silently turns ``\"a, ]\"`` into ``\"a ]\"``.
    """
    runner = _import_runner()
    text = (
        "// Zed settings\n"
        "{\n"
        '  "label": "a, ]",\n'
        '  "pair": "b,}",\n'
        '  "agent_servers": {"optimus": {"command": "x", "args": [],}},\n'
        "}\n"
    )
    stripped = runner._strip_jsonc(text)
    assert '"a, ]"' in stripped, (
        f"silent corruption: expected '\"a, ]\"' preserved, got {stripped!r}"
    )
    assert '"b,}"' in stripped, (
        f"silent corruption: expected '\"b,}}\"' preserved, got {stripped!r}"
    )
    payload = runner.parse_jsonc(text)
    assert payload["label"] == "a, ]"
    assert payload["pair"] == "b,}"
    assert payload["agent_servers"]["optimus"]["command"] == "x"
    assert payload["agent_servers"]["optimus"]["args"] == []


def test_parse_jsonc_preserves_escaped_quotes_and_backslashes() -> None:
    runner = _import_runner()
    text = (
        "// comment\n"
        "{\n"
        r'  "q": "say \"hi\", ]",' + "\n"
        r'  "bs": "path\\to\\file,}",' + "\n"
        '  "ok": true,' + "\n"
        "}\n"
    )
    payload = runner.parse_jsonc(text)
    assert payload["q"] == 'say "hi", ]'
    assert payload["bs"] == r"path\to\file,}"
    assert payload["ok"] is True


def test_parse_jsonc_preserves_line_and_block_comment_markers_inside_strings() -> None:
    runner = _import_runner()
    text = (
        "/* file header */\n"
        "{\n"
        '  "url": "https://example.com/path",\n'
        '  "hint": "use // for line comments",\n'
        '  "block": "not a /* real */ comment, ]",\n'
        '  "trail": 1,' + "\n"
        "}\n"
    )
    payload = runner.parse_jsonc(text)
    assert payload["url"] == "https://example.com/path"
    assert payload["hint"] == "use // for line comments"
    assert payload["block"] == "not a /* real */ comment, ]"
    assert payload["trail"] == 1


def test_parse_jsonc_strips_real_trailing_commas_outside_strings() -> None:
    runner = _import_runner()
    text = (
        "// keep comments\n"
        "{\n"
        '  "arr": [1, 2, 3,],\n'
        '  "obj": {"a": 1, "b": 2,},\n'
        '  "nested": [{"x": "y",},],\n'
        "}\n"
    )
    payload = runner.parse_jsonc(text)
    assert payload == {
        "arr": [1, 2, 3],
        "obj": {"a": 1, "b": 2},
        "nested": [{"x": "y"}],
    }


def test_parse_jsonc_comment_free_strict_json_bypasses_stripper() -> None:
    runner = _import_runner()
    # Valid strict JSON: must take the json.loads fast path (never need _strip_jsonc).
    text = '{\n  "label": "a, ]",\n  "pair": "b,}"\n}\n'
    payload = runner.parse_jsonc(text)
    assert payload["label"] == "a, ]"
    assert payload["pair"] == "b,}"
    # And the stripper must also preserve these when invoked directly.
    stripped = runner._strip_jsonc(text)
    assert '"a, ]"' in stripped
    assert '"b,}"' in stripped


def test_parse_jsonc_malformed_jsonc_fails_closed() -> None:
    runner = _import_runner()
    with pytest.raises(json.JSONDecodeError):
        runner.parse_jsonc("// header\n{not-json,}")
    with pytest.raises(json.JSONDecodeError):
        runner.parse_jsonc('{"unclosed": "string')
    with pytest.raises(json.JSONDecodeError):
        runner.parse_jsonc("/* only a block comment */")


def test_parse_jsonc_round_trip_semantic_values_exact() -> None:
    runner = _import_runner()
    text = (
        "// settings\n"
        "{\n"
        '  "theme": "one-dark",\n'
        '  "nums": [0, -1, 2.5,],\n'
        '  "flags": {"on": true, "off": false, "empty": null,},\n'
        '  "weird": "a, ] and b,} with // and /* markers",\n'
        "}\n"
    )
    payload = runner.parse_jsonc(text)
    assert payload["theme"] == "one-dark"
    assert payload["nums"] == [0, -1, 2.5]
    assert payload["flags"] == {"on": True, "off": False, "empty": None}
    assert payload["weird"] == "a, ] and b,} with // and /* markers"
    # Round-trip through json.dumps/json.loads must preserve semantics.
    assert json.loads(json.dumps(payload)) == payload


def test_settings_preimage_restored_after_mutation_window_failure_with_hostile_jsonc(
    custody_roots: dict[str, Path],
) -> None:
    """Hostile JSONC string values must not prevent exact pre-image restoration."""
    runner = _import_runner()
    settings = custody_roots["settings_path"]
    original_text = (
        "// Zed settings\n"
        "{\n"
        '  "theme": "one-dark",\n'
        '  "label": "a, ]",\n'
        '  "agent_servers": {\n'
        '    "optimus": {\n'
        '      "command": "optimus-agent",\n'
        '      "args": ["--workspace-root", ".",],\n'
        '      "env": {"KEEP": "me"},\n'
        "    },\n"
        "  },\n"
        '  "unrelated": {"nested": true},\n'
        "}\n"
    )
    settings.write_text(original_text, encoding="utf-8", newline="\n")
    original = settings.read_bytes()
    pre = _sha256_bytes(original)
    approval = _approval(settings_path=settings, pre_image_sha256=pre)

    # In-window parse must preserve the hostile string (not silently corrupt it).
    loaded = runner._load_settings_json(settings)
    assert loaded["label"] == "a, ]"

    def boom() -> None:
        raise RuntimeError("mutation-window failure")

    with pytest.raises(RuntimeError, match="mutation-window failure"):
        runner.run_with_settings_transaction(
            settings_path=settings,
            custody_root=custody_roots["custody_root"],
            relay_command="python",
            relay_args=["relay.py"],
            approval=approval,
            agent_server_name="optimus",
            body=boom,
        )
    assert settings.read_bytes() == original
    assert _sha256_bytes(settings.read_bytes()) == pre


# --- Origin-A fixture v2: exact origin-a-3 allocation + prompt-only retry ------

AMENDMENT_SHA256 = "5BB327D88761AE329869B90866839D03F61EFF6AF0E5AE47F8D3D7551F849A4D"
PROMPT_V2 = ROOT / "tests" / "fixtures" / "evidence" / "plan117-server-custody-prompt-v2.txt"
PROMPT_V2_SHA256 = "9195EFEEE3A2180CFB85EDE409FF7785F159F64E36426DCDB369251560E28A50"
PYPROJECT_SHA256 = "AE28C0C3776F6B78DF23E86FC0E88B0088FEBB7241A04650C604D713E23EF697"
_PARENT_A1 = "7d64d5943002b15dcd977b0bc7614fc4234f9dd6d823c1533da6a0677f9ff446"
_PARENT_A2 = "083e0953c8d89781c8c3100545bfc2e4524e94cbbaae7b32574da4d88f597f63"


def _runner_stage_api(runner: Any) -> Any:
    required = (
        "reserve_origin_a_run",
        "assert_origin_a3_preflight",
        "assert_prompt_retry_preflight",
        "write_stage_outcome_exclusive",
        "verify_original_attempt_hashes",
        "PROMPT_FIXTURE_V2_SHA256",
        "PYPROJECT_TARGET_SHA256",
    )
    missing = [name for name in required if not hasattr(runner, name)]
    if missing:
        pytest.fail(f"missing origin-a fixture-v2 runner API: {missing}")
    return runner


def _fixed_ledger_records():
    from tools.plan117_custody_contract import (
        EvidenceReference,
        FailureClass,
        StageAttemptRecord,
        StageKind,
        StageStatus,
    )

    def ev(path: str, digest: str) -> EvidenceReference:
        return EvidenceReference(path, digest, "raw_file_sha256")

    return (
        StageAttemptRecord(
            record_id="origin-a-1-correlation",
            run_attempt_id="origin-a-1",
            stage=StageKind.CORRELATION_CAPTURE,
            ordinal=1,
            status=StageStatus.FAILED,
            failure_class=FailureClass.PERMANENT,
            reason_code="invalid_probe_relay_capture_tooling_failure",
            evidence=(ev("attempts/origin-a-1/attempt-manifest.json", _PARENT_A1),),
            supersedes_record_id="origin-a-1-original-manifest",
            supersedes_sha256=_PARENT_A1,
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
            evidence=(ev("attempts/origin-a-2/attempt-manifest.json", _PARENT_A2),),
            supersedes_record_id="origin-a-2-original-manifest",
            supersedes_sha256=_PARENT_A2,
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
            evidence=(ev("attempts/origin-a-2/phase-observation.json", "d" * 64),),
            supersedes_record_id="origin-a-2-original-prompt",
            supersedes_sha256="d" * 64,
            amendment_sha256=AMENDMENT_SHA256.lower(),
            created_by="plan117-task1",
            created_utc="2026-08-02T16:00:00Z",
        ),
    )


def test_origin_a3_reservation_before_launch_is_exclusive(custody_roots: dict[str, Path]) -> None:
    runner = _runner_stage_api(_import_runner())
    from tools.plan117_custody_contract import normalize_stage_ledger

    ledger = normalize_stage_ledger(_fixed_ledger_records())
    reservation_root = custody_roots["capture_root"] / "reservations"
    path = runner.reserve_origin_a_run(
        reservation_root=reservation_root,
        run_attempt_id="origin-a-3",
        ledger=ledger,
    )
    assert path.is_file()
    assert b"\r\n" not in path.read_bytes()
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.reserve_origin_a_run(
            reservation_root=reservation_root,
            run_attempt_id="origin-a-3",
            ledger=ledger,
        )
    assert exc.value.reason_code in {
        "reservation_already_exists",
        "invalid_probe_stage_accounting",
        "invalid_probe_retry_budget_exhausted",
    }


def test_origin_a3_requires_exact_expected_run_attempt_id(custody_roots: dict[str, Path]) -> None:
    runner = _runner_stage_api(_import_runner())
    from tools.plan117_custody_contract import normalize_stage_ledger

    ledger = normalize_stage_ledger(_fixed_ledger_records())
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.assert_origin_a3_preflight(
            expected_run_attempt_id="origin-a-4",
            ledger=ledger,
            prompt_fixture=PROMPT_V2,
            workspace_root=ROOT,
            reservation_path=custody_roots["capture_root"] / "reservations" / "origin-a-3.json",
        )
    assert exc.value.reason_code in {
        "invalid_probe_stage_accounting",
        "invalid_probe_retry_budget_exhausted",
        "invalid_probe_fixture_identity_mismatch",
    }

    # Exact origin-a-3 + fixture/target digests accepted before reservation exists.
    runner.assert_origin_a3_preflight(
        expected_run_attempt_id="origin-a-3",
        ledger=ledger,
        prompt_fixture=PROMPT_V2,
        workspace_root=ROOT,
        reservation_path=custody_roots["capture_root"] / "reservations" / "origin-a-3.json",
    )


def test_origin_a3_refuses_reuse_when_reservation_or_attempt_exists(
    custody_roots: dict[str, Path],
) -> None:
    runner = _runner_stage_api(_import_runner())
    from tools.plan117_custody_contract import normalize_stage_ledger

    ledger = normalize_stage_ledger(_fixed_ledger_records())
    reservation_root = custody_roots["capture_root"] / "reservations"
    runner.reserve_origin_a_run(
        reservation_root=reservation_root,
        run_attempt_id="origin-a-3",
        ledger=ledger,
    )
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.assert_origin_a3_preflight(
            expected_run_attempt_id="origin-a-3",
            ledger=ledger,
            prompt_fixture=PROMPT_V2,
            workspace_root=ROOT,
            reservation_path=reservation_root / "origin-a-3.json",
        )
    assert exc.value.reason_code in {
        "reservation_already_exists",
        "invalid_probe_stage_accounting",
    }


def test_prompt_retry_requires_live_session_proof_and_skips_settings_launch(
    custody_roots: dict[str, Path],
) -> None:
    runner = _runner_stage_api(_import_runner())
    from tools.plan117_custody_contract import (
        EvidenceReference,
        FailureClass,
        StageAttemptRecord,
        StageKind,
        StageStatus,
        build_live_session_proof,
        normalize_stage_ledger,
    )

    records = list(_fixed_ledger_records())
    records.append(
        StageAttemptRecord(
            record_id="origin-a-3-correlation",
            run_attempt_id="origin-a-3",
            stage=StageKind.CORRELATION_CAPTURE,
            ordinal=3,
            status=StageStatus.SUCCEEDED,
            failure_class=FailureClass.NONE,
            reason_code=None,
            evidence=(EvidenceReference("attempts/origin-a-3/manifest.json", "a" * 64, "raw_file_sha256"),),
            supersedes_record_id=None,
            supersedes_sha256=None,
            amendment_sha256=AMENDMENT_SHA256.lower(),
            created_by="plan117-task1",
            created_utc="2026-08-02T16:00:00Z",
        )
    )
    records.append(
        StageAttemptRecord(
            record_id="origin-a-3-prompt-2",
            run_attempt_id="origin-a-3",
            stage=StageKind.POST_NEW_PROMPT,
            ordinal=2,
            status=StageStatus.FAILED,
            failure_class=FailureClass.TRANSIENT,
            reason_code="gateway_timeout",
            evidence=(EvidenceReference("attempts/origin-a-3/prompt.json", "b" * 64, "raw_file_sha256"),),
            supersedes_record_id=None,
            supersedes_sha256=None,
            amendment_sha256=AMENDMENT_SHA256.lower(),
            created_by="plan117-task1",
            created_utc="2026-08-02T16:00:00Z",
        )
    )
    ledger = normalize_stage_ledger(records)

    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.assert_prompt_retry_preflight(
            run_attempt_id="origin-a-3",
            ledger=ledger,
            prompt_fixture=PROMPT_V2,
            target_sha256=PYPROJECT_SHA256.lower(),
            live_session_proof=None,
        )
    assert exc.value.reason_code == "blocked_probe_same_session_prompt_retry_unavailable"

    proof = build_live_session_proof(
        run_attempt_id="origin-a-3",
        zed_pid=4242,
        zed_process_start_time_utc="2026-08-04T12:00:00Z",
        connection_id="conn-1",
        acp_session_id="sess-origin-a-3",
        zed_alive=True,
        relay_alive=True,
        acp_session_observed=True,
        captured_utc="2026-08-04T12:05:00Z",
        evidence=(
            EvidenceReference(
                "attempts/origin-a-3/relay-index.ndjson",
                "c" * 64,
                "raw_file_sha256",
            ),
        ),
    )
    result = runner.assert_prompt_retry_preflight(
        run_attempt_id="origin-a-3",
        ledger=ledger,
        prompt_fixture=PROMPT_V2,
        target_sha256=PYPROJECT_SHA256.lower(),
        live_session_proof=proof,
    )
    assert result.prompt_ordinal == 3
    assert result.settings_mutated is False
    assert result.zed_launched is False
    assert result.live_session_proof_sha256 == proof.proof_sha256
    # Prompt-only retry must not mutate settings or allocate a new attempt launch dir.
    assert not (custody_roots["settings_path"].parent / "mutated.marker").exists()
    assert not (custody_roots["capture_root"] / "attempts" / "origin-a-4").exists()


def test_stage_outcome_exclusive_write_and_originals_untouched(
    custody_roots: dict[str, Path], tmp_path: Path
) -> None:
    runner = _runner_stage_api(_import_runner())
    from tools.plan117_custody_contract import (
        EvidenceReference,
        FailureClass,
        StageAttemptRecord,
        StageKind,
        StageStatus,
    )

    original_dir = tmp_path / "attempts" / "origin-a-1"
    original_dir.mkdir(parents=True)
    original = original_dir / "attempt-manifest.json"
    original.write_bytes(b'{"immutable":true}\n')
    before = original.read_bytes()

    expected_hashes = {
        "attempts/origin-a-1/attempt-manifest.json": _sha256_bytes(before),
    }
    runner.verify_original_attempt_hashes(
        originals_root=tmp_path,
        expected_relative_sha256=expected_hashes,
    )

    # Tamper detection.
    original.write_bytes(b'{"immutable":false}\n')
    with pytest.raises(runner.CustodyRunnerError) as tamper:
        runner.verify_original_attempt_hashes(
            originals_root=tmp_path,
            expected_relative_sha256=expected_hashes,
        )
    assert tamper.value.reason_code == "invalid_probe_origin_attempt_original_mismatch"
    original.write_bytes(before)

    outcome_path = custody_roots["capture_root"] / "stages" / "origin-a-3-correlation.json"
    record = StageAttemptRecord(
        record_id="origin-a-3-correlation",
        run_attempt_id="origin-a-3",
        stage=StageKind.CORRELATION_CAPTURE,
        ordinal=3,
        status=StageStatus.SUCCEEDED,
        failure_class=FailureClass.NONE,
        reason_code=None,
        evidence=(EvidenceReference("attempts/origin-a-3/x.json", "c" * 64, "raw_file_sha256"),),
        supersedes_record_id=None,
        supersedes_sha256=None,
        amendment_sha256=AMENDMENT_SHA256.lower(),
        created_by="plan117-task1",
        created_utc="2026-08-02T16:00:00Z",
    )
    runner.write_stage_outcome_exclusive(outcome_path, record)
    with pytest.raises(runner.CustodyRunnerError):
        runner.write_stage_outcome_exclusive(outcome_path, record)
    assert original.read_bytes() == before


def test_cli_accepts_origin_a3_and_prompt_retry_boundaries() -> None:
    runner = _runner_stage_api(_import_runner())
    assert "origin-a-prompt-retry" in runner.PHASES
    parser = runner._build_parser()
    args = parser.parse_args(
        [
            "origin-a",
            "--expected-run-attempt-id",
            "origin-a-3",
            "--prompt-fixture",
            str(PROMPT_V2),
            "--workspace-root",
            str(ROOT),
            "--capture-root",
            str(ROOT / "reports"),
            "--zed-executable",
            str(ROOT / "README.md"),
            "--zed-source",
            str(ROOT),
            "--settings-path",
            str(ROOT / "README.md"),
            "--debug-log",
            str(ROOT / "README.md"),
        ]
    )
    assert args.expected_run_attempt_id == "origin-a-3"
    assert Path(args.prompt_fixture) == PROMPT_V2

    retry = parser.parse_args(
        [
            "origin-a-prompt-retry",
            "--run-attempt-id",
            "origin-a-3",
            "--prompt-fixture",
            str(PROMPT_V2),
            "--workspace-root",
            str(ROOT),
            "--capture-root",
            str(ROOT / "reports"),
            "--zed-executable",
            str(ROOT / "README.md"),
            "--zed-source",
            str(ROOT),
            "--settings-path",
            str(ROOT / "README.md"),
            "--debug-log",
            str(ROOT / "README.md"),
        ]
    )
    assert retry.phase == "origin-a-prompt-retry"
    assert retry.run_attempt_id == "origin-a-3"


def test_fixture_v2_and_pyproject_digest_constants() -> None:
    runner = _runner_stage_api(_import_runner())
    assert runner.PROMPT_FIXTURE_V2_SHA256.upper() == PROMPT_V2_SHA256
    assert runner.PYPROJECT_TARGET_SHA256.upper() == PYPROJECT_SHA256
    assert _sha256_bytes(PROMPT_V2.read_bytes()).upper() == PROMPT_V2_SHA256
    assert _sha256_bytes((ROOT / "pyproject.toml").read_bytes()).upper() == PYPROJECT_SHA256


# --- Task 3: origin-a-prompt-retry CLI wiring ---------------------------------


_RETRY_OWNER = "unit-retry-operator"
_RETRY_ZED_PID = 4242
_RETRY_START_UTC = "2026-08-04T12:00:00Z"
_RETRY_CONN = "conn-origin-a-3"
_RETRY_SESSION = "sess-origin-a-3"
_RETRY_EVIDENCE = "c" * 64


def _retry_api(runner: Any) -> Any:
    required = (
        "run_origin_a_prompt_retry",
        "load_stage_ledger",
        "load_launch_session_identity",
        "reserve_prompt_ordinal",
        "assert_prompt_retry_ledger_eligible",
        "assert_prompt_retry_preflight",
    )
    missing = [name for name in required if not hasattr(runner, name)]
    if missing:
        pytest.fail(f"missing origin-a-prompt-retry runner API: {missing}")
    return runner


def _retry_eligible_records():
    from tools.plan117_custody_contract import (
        EvidenceReference,
        FailureClass,
        StageAttemptRecord,
        StageKind,
        StageStatus,
    )

    records = list(_fixed_ledger_records())
    records.append(
        StageAttemptRecord(
            record_id="origin-a-3-correlation",
            run_attempt_id="origin-a-3",
            stage=StageKind.CORRELATION_CAPTURE,
            ordinal=3,
            status=StageStatus.SUCCEEDED,
            failure_class=FailureClass.NONE,
            reason_code=None,
            evidence=(
                EvidenceReference(
                    "attempts/origin-a-3/manifest.json",
                    "a" * 64,
                    "raw_file_sha256",
                ),
            ),
            supersedes_record_id="origin-a-3-original-manifest",
            supersedes_sha256="a" * 64,
            amendment_sha256=AMENDMENT_SHA256.lower(),
            created_by="plan117-task3",
            created_utc="2026-08-04T16:00:00Z",
        )
    )
    records.append(
        StageAttemptRecord(
            record_id="origin-a-3-prompt-2",
            run_attempt_id="origin-a-3",
            stage=StageKind.POST_NEW_PROMPT,
            ordinal=2,
            status=StageStatus.FAILED,
            failure_class=FailureClass.TRANSIENT,
            reason_code="gateway_timeout",
            evidence=(
                EvidenceReference(
                    "attempts/origin-a-3/prompt.json",
                    "b" * 64,
                    "raw_file_sha256",
                ),
            ),
            supersedes_record_id="origin-a-3-original-observation",
            supersedes_sha256="b" * 64,
            amendment_sha256=AMENDMENT_SHA256.lower(),
            created_by="plan117-task3",
            created_utc="2026-08-04T16:00:00Z",
        )
    )
    return tuple(records)


def _write_stage_ledger(path: Path, records: tuple[Any, ...]) -> None:
    from tools.plan117_custody_contract import (
        SCHEMA_STAGE_LEDGER,
        normalize_stage_ledger,
        stage_attempt_record_payload,
        write_canonical_json,
    )

    ledger = normalize_stage_ledger(records)
    payload = {
        "schema": SCHEMA_STAGE_LEDGER,
        "amendment_sha256": AMENDMENT_SHA256.lower(),
        "next_correlation_ordinal": ledger.next_correlation_ordinal,
        "next_prompt_ordinal": ledger.next_prompt_ordinal,
        "records": [stage_attempt_record_payload(record) for record in records],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(path, payload)


def _write_launch_identity(path: Path) -> None:
    from tools.plan117_custody_contract import write_canonical_json

    write_canonical_json(
        path,
        {
            "schema": "plan117-custody-launch-session-identity-v1",
            "run_attempt_id": "origin-a-3",
            "zed_pid": _RETRY_ZED_PID,
            "zed_process_start_time_utc": _RETRY_START_UTC,
            "connection_id": _RETRY_CONN,
            "acp_session_id": _RETRY_SESSION,
        },
    )


def _prime_retry_prereq_phases(runner: Any, capture_root: Path) -> None:
    state_path = capture_root / runner.STATE_FILENAME
    runner.init_phase_state(state_path)
    for phase in ("direct-control", "relay-control", "origin-a"):
        runner.mark_phase_complete(state_path, phase)


def _prepare_retry_workspace(custody_roots: dict[str, Path]) -> None:
    import shutil

    shutil.copyfile(
        ROOT / "pyproject.toml",
        custody_roots["workspace_root"] / "pyproject.toml",
    )


def _start_retry_control_endpoint(tmp_path: Path, **kwargs: Any) -> Any:
    import tools.plan117_custody_relay as relay
    from tools.plan117_custody_contract import EvidenceReference

    class _Proc:
        def __init__(self) -> None:
            self.pid = kwargs.get("zed_pid", _RETRY_ZED_PID)
            self._alive = kwargs.get("alive", True)
            self.returncode = None if self._alive else 0

        def poll(self) -> int | None:
            return None if self._alive else 0

        def mark_exited(self) -> None:
            self._alive = False
            self.returncode = 0

    proc = kwargs.get("zed_proc") or _Proc()
    start_utc = kwargs.get("start_utc", _RETRY_START_UTC)
    pid = kwargs.get("zed_pid", _RETRY_ZED_PID)

    def _observe(query_pid: int) -> Any:
        if query_pid != pid:
            return None
        return relay.ObservedProcessIdentity(
            pid=query_pid,
            process_start_time_utc=start_utc,
            alive=proc.poll() is None,
        )

    custody_root = tmp_path / "private" / "origin-a-3"
    custody_root.mkdir(parents=True, exist_ok=True)
    forwarded: list[bytes] = []

    def _forward(payload: bytes) -> None:
        forwarded.append(payload)

    endpoint = relay.RelayControlEndpoint.start(
        run_attempt_id="origin-a-3",
        custody_root=custody_root,
        zed_proc=proc,
        zed_process_start_time_utc=start_utc,
        connection_id=kwargs.get("connection_id", _RETRY_CONN),
        acp_session_id=kwargs.get("acp_session_id", _RETRY_SESSION),
        evidence=(
            EvidenceReference(
                relative_path="attempts/origin-a-3/relay-index.ndjson",
                sha256=_RETRY_EVIDENCE,
                hash_method="raw_file_sha256",
            ),
        ),
        process_observer=kwargs.get("process_observer") or _observe,
        owner_id=kwargs.get("owner_id", _RETRY_OWNER),
        prompt_forward=kwargs.get("prompt_forward") or _forward,
    )
    endpoint._test_proc = proc  # type: ignore[attr-defined]
    endpoint._test_forwarded = forwarded  # type: ignore[attr-defined]
    return endpoint


def _retry_cli_args(
    custody_roots: dict[str, Path],
    *,
    stage_ledger: Path,
    launch_identity: Path,
    descriptor: Path,
) -> list[str]:
    return [
        "origin-a-prompt-retry",
        "--run-attempt-id",
        "origin-a-3",
        "--prompt-fixture",
        str(PROMPT_V2),
        "--workspace-root",
        str(custody_roots["workspace_root"]),
        "--capture-root",
        str(custody_roots["capture_root"]),
        "--zed-executable",
        str(custody_roots["zed_executable"]),
        "--zed-source",
        str(custody_roots["zed_source"]),
        "--settings-path",
        str(custody_roots["settings_path"]),
        "--debug-log",
        str(custody_roots["debug_log"]),
        "--custody-root",
        str(custody_roots["custody_root"]),
        "--stage-ledger",
        str(stage_ledger),
        "--launch-identity",
        str(launch_identity),
        "--relay-control-descriptor",
        str(descriptor),
        "--caller-owner-id",
        _RETRY_OWNER,
        "--no-operator-wait",
    ]


def test_origin_a_prompt_retry_cli_order_ledger_proof_gate_reserve_prompt(
    custody_roots: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _retry_api(_import_runner())
    from tools.plan117_custody_contract import (
        LaunchSessionIdentity,
        LiveSessionProof,
        evaluate_prompt_retry_preflight,
        normalize_stage_ledger,
    )

    ledger_path = tmp_path / "stage-ledger.json"
    identity_path = tmp_path / "launch-identity.json"
    _write_stage_ledger(ledger_path, _retry_eligible_records())
    _write_launch_identity(identity_path)
    _prepare_retry_workspace(custody_roots)
    endpoint = _start_retry_control_endpoint(tmp_path)
    _prime_retry_prereq_phases(runner, custody_roots["capture_root"])

    call_order: list[str] = []
    real_load_ledger = runner.load_stage_ledger
    real_load_identity = runner.load_launch_session_identity
    real_ledger_eligible = runner.assert_prompt_retry_ledger_eligible
    real_assert = runner.assert_prompt_retry_preflight
    real_reserve = runner.reserve_prompt_ordinal
    real_evaluate = evaluate_prompt_retry_preflight

    import tools.plan117_custody_relay as relay

    real_acquire = relay.acquire_live_session_proof
    real_send = relay.send_existing_session_prompt

    def load_ledger(path: Path) -> Any:
        call_order.append("load_stage_ledger")
        return real_load_ledger(path)

    def ledger_eligible(**kwargs: Any) -> None:
        call_order.append("assert_prompt_retry_ledger_eligible")
        return real_ledger_eligible(**kwargs)

    def load_identity(path: Path) -> LaunchSessionIdentity:
        call_order.append("load_launch_session_identity")
        identity = real_load_identity(path)
        assert identity.acp_session_id == _RETRY_SESSION
        return identity

    def acquire(**kwargs: Any) -> LiveSessionProof:
        assert "assert_prompt_retry_ledger_eligible" in call_order
        call_order.append("acquire_live_session_proof")
        assert "acp_session_id" not in kwargs
        assert kwargs["caller_owner_id"] == _RETRY_OWNER
        return real_acquire(**kwargs)

    def evaluate(**kwargs: Any) -> Any:
        call_order.append("evaluate_prompt_retry_preflight")
        identity = kwargs["launch_identity"]
        assert isinstance(identity, LaunchSessionIdentity)
        assert identity.zed_pid == _RETRY_ZED_PID
        assert identity.connection_id == _RETRY_CONN
        assert identity.acp_session_id == _RETRY_SESSION
        # Must not be vacuous self-bind from proof alone without prior load.
        assert identity.run_attempt_id == "origin-a-3"
        return real_evaluate(**kwargs)

    def assert_gate(**kwargs: Any) -> Any:
        call_order.append("assert_prompt_retry_preflight")
        return real_assert(**kwargs)

    def reserve(**kwargs: Any) -> Path:
        assert "acquire_live_session_proof" in call_order
        assert "evaluate_prompt_retry_preflight" in call_order
        assert "assert_prompt_retry_preflight" in call_order
        call_order.append("reserve_prompt_ordinal")
        assert kwargs["prompt_ordinal"] == 3
        return real_reserve(**kwargs)

    def send(**kwargs: Any) -> dict[str, Any]:
        assert call_order[-1] == "reserve_prompt_ordinal"
        call_order.append("send_existing_session_prompt")
        assert kwargs["connection_id"] == _RETRY_CONN
        assert kwargs["acp_session_id"] == _RETRY_SESSION
        return real_send(**kwargs)

    monkeypatch.setattr(runner, "load_stage_ledger", load_ledger)
    monkeypatch.setattr(runner, "assert_prompt_retry_ledger_eligible", ledger_eligible)
    monkeypatch.setattr(runner, "load_launch_session_identity", load_identity)
    monkeypatch.setattr(runner, "assert_prompt_retry_preflight", assert_gate)
    monkeypatch.setattr(runner, "reserve_prompt_ordinal", reserve)
    monkeypatch.setattr(runner, "evaluate_prompt_retry_preflight", evaluate)
    monkeypatch.setattr(relay, "acquire_live_session_proof", acquire)
    monkeypatch.setattr(relay, "send_existing_session_prompt", send)
    # Ensure runner module sees patched relay symbols if already imported.
    if hasattr(runner, "acquire_live_session_proof"):
        monkeypatch.setattr(runner, "acquire_live_session_proof", acquire)
    if hasattr(runner, "send_existing_session_prompt"):
        monkeypatch.setattr(runner, "send_existing_session_prompt", send)

    settings_before = custody_roots["settings_path"].read_bytes()
    code = runner.main(
        _retry_cli_args(
            custody_roots,
            stage_ledger=ledger_path,
            launch_identity=identity_path,
            descriptor=endpoint.descriptor_path,
        )
    )
    assert code == 0
    out = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(out)
    assert payload["phase"] == "origin-a-prompt-retry"
    assert payload["run_attempt_id"] == "origin-a-3"
    assert payload["prompt_ordinal"] == 3
    assert payload["settings_mutated"] is False
    assert payload["zed_launched"] is False
    assert payload["live_session_proof_sha256"]
    assert "hardcoded" not in out.lower()
    # evaluate appears twice: once with immutable launch identity (Task-1 gap close),
    # then nested inside assert_prompt_retry_preflight's public-gate revalidation.
    assert call_order == [
        "load_stage_ledger",
        "assert_prompt_retry_ledger_eligible",
        "load_launch_session_identity",
        "acquire_live_session_proof",
        "evaluate_prompt_retry_preflight",
        "assert_prompt_retry_preflight",
        "evaluate_prompt_retry_preflight",
        "reserve_prompt_ordinal",
        "send_existing_session_prompt",
    ]
    assert custody_roots["settings_path"].read_bytes() == settings_before
    assert not (custody_roots["capture_root"] / "attempts" / "origin-a-4").exists()
    assert endpoint._test_forwarded  # type: ignore[attr-defined]
    # Ledger next prompt was 3 before; reservation consumed ordinal 3.
    reservation = (
        custody_roots["capture_root"] / "reservations" / "origin-a-3-prompt-3.json"
    )
    assert reservation.is_file()
    ledger = normalize_stage_ledger(_retry_eligible_records())
    assert ledger.next_prompt_ordinal == 3
    endpoint.close()


def test_origin_a_prompt_retry_failure_before_reserve_has_no_side_effects(
    custody_roots: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _retry_api(_import_runner())
    import tools.plan117_custody_relay as relay

    ledger_path = tmp_path / "stage-ledger.json"
    identity_path = tmp_path / "launch-identity.json"
    _write_stage_ledger(ledger_path, _retry_eligible_records())
    _write_launch_identity(identity_path)
    _prepare_retry_workspace(custody_roots)
    endpoint = _start_retry_control_endpoint(tmp_path)
    _prime_retry_prereq_phases(runner, custody_roots["capture_root"])

    side_effects: list[str] = []

    def boom_acquire(**_kwargs: Any) -> Any:
        side_effects.append("acquire")
        raise runner.CustodyRunnerError(
            "blocked_probe_same_session_prompt_retry_unavailable",
            "live_session_proof",
        )

    def forbid_send(**_kwargs: Any) -> Any:
        side_effects.append("send")
        raise AssertionError("send must not run before reservation")

    def forbid_reserve(**_kwargs: Any) -> Any:
        side_effects.append("reserve")
        raise AssertionError("reserve must not run after proof failure")

    monkeypatch.setattr(relay, "acquire_live_session_proof", boom_acquire)
    monkeypatch.setattr(relay, "send_existing_session_prompt", forbid_send)
    if hasattr(runner, "acquire_live_session_proof"):
        monkeypatch.setattr(runner, "acquire_live_session_proof", boom_acquire)
    if hasattr(runner, "send_existing_session_prompt"):
        monkeypatch.setattr(runner, "send_existing_session_prompt", forbid_send)
    monkeypatch.setattr(runner, "reserve_prompt_ordinal", forbid_reserve)

    settings_before = custody_roots["settings_path"].read_bytes()
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.main(
            _retry_cli_args(
                custody_roots,
                stage_ledger=ledger_path,
                launch_identity=identity_path,
                descriptor=endpoint.descriptor_path,
            )
        )
    assert exc.value.reason_code == "blocked_probe_same_session_prompt_retry_unavailable"
    assert side_effects == ["acquire"]
    assert custody_roots["settings_path"].read_bytes() == settings_before
    assert not (custody_roots["capture_root"] / "reservations" / "origin-a-3-prompt-3.json").exists()
    assert not (custody_roots["capture_root"] / "attempts" / "origin-a-4").exists()
    assert not endpoint._test_forwarded  # type: ignore[attr-defined]
    endpoint.close()


def test_origin_a_prompt_retry_rejects_cli_supplied_session_or_proof(
    custody_roots: dict[str, Path],
) -> None:
    runner = _retry_api(_import_runner())
    parser = runner._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "origin-a-prompt-retry",
                "--run-attempt-id",
                "origin-a-3",
                "--acp-session-id",
                "sess-forged",
                "--workspace-root",
                str(custody_roots["workspace_root"]),
                "--capture-root",
                str(custody_roots["capture_root"]),
                "--zed-executable",
                str(custody_roots["zed_executable"]),
                "--zed-source",
                str(custody_roots["zed_source"]),
                "--settings-path",
                str(custody_roots["settings_path"]),
                "--debug-log",
                str(custody_roots["debug_log"]),
            ]
        )
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "--acp-session-id" not in source
    assert "--live-session-proof" not in source
    assert "hardcoded JSON" not in source
    # Hardcoded success path must be gone from the retry branch.
    assert '"settings_mutated": False' not in source or "run_origin_a_prompt_retry" in source


def test_origin_a_prompt_retry_second_reservation_stops(
    custody_roots: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prove immutable reservation via a path that reaches reserve twice.

    First attempt reserves then fails at prompt (descriptor not sealed). Second
    attempt must hit ``reservation_already_exists`` — not a sealed-descriptor stop.
    """
    runner = _retry_api(_import_runner())
    import tools.plan117_custody_relay as relay

    ledger_path = tmp_path / "stage-ledger.json"
    identity_path = tmp_path / "launch-identity.json"
    _write_stage_ledger(ledger_path, _retry_eligible_records())
    _write_launch_identity(identity_path)
    _prepare_retry_workspace(custody_roots)

    def boom_forward(_payload: bytes) -> None:
        raise OSError("simulated prompt forward failure")

    endpoint = _start_retry_control_endpoint(tmp_path, prompt_forward=boom_forward)
    _prime_retry_prereq_phases(runner, custody_roots["capture_root"])
    args = _retry_cli_args(
        custody_roots,
        stage_ledger=ledger_path,
        launch_identity=identity_path,
        descriptor=endpoint.descriptor_path,
    )

    with pytest.raises(runner.CustodyRunnerError) as first:
        runner.main(args)
    assert first.value.reason_code == "invalid_probe_retry_control_channel_failure"
    reservation = (
        custody_roots["capture_root"] / "reservations" / "origin-a-3-prompt-3.json"
    )
    assert reservation.is_file()
    before = reservation.read_bytes()
    # Descriptor must remain usable so the second attempt can reach reserve.
    descriptor = json.loads(endpoint.descriptor_path.read_text(encoding="utf-8"))
    assert descriptor.get("prompt_sealed") is not True
    assert descriptor.get("terminal") is not True

    reserve_calls = {"n": 0}
    real_reserve = runner.reserve_prompt_ordinal

    def counting_reserve(**kwargs: Any) -> Path:
        reserve_calls["n"] += 1
        return real_reserve(**kwargs)

    monkeypatch.setattr(runner, "reserve_prompt_ordinal", counting_reserve)
    acquire_calls = {"n": 0}
    real_acquire = relay.acquire_live_session_proof

    def counting_acquire(**kwargs: Any) -> Any:
        acquire_calls["n"] += 1
        return real_acquire(**kwargs)

    monkeypatch.setattr(relay, "acquire_live_session_proof", counting_acquire)
    if hasattr(runner, "acquire_live_session_proof"):
        monkeypatch.setattr(runner, "acquire_live_session_proof", counting_acquire)

    with pytest.raises(runner.CustodyRunnerError) as second:
        runner.main(args)
    assert second.value.reason_code == "reservation_already_exists"
    assert acquire_calls["n"] >= 1, "second attempt must reach live proof before reserve"
    assert reserve_calls["n"] >= 1, "second attempt must consult reserve"
    assert reservation.read_bytes() == before
    endpoint.close()


def test_origin_a_prompt_retry_stale_proof_cannot_reserve(
    custody_roots: dict[str, Path],
    tmp_path: Path,
) -> None:
    runner = _retry_api(_import_runner())
    ledger_path = tmp_path / "stage-ledger.json"
    identity_path = tmp_path / "launch-identity.json"
    _write_stage_ledger(ledger_path, _retry_eligible_records())
    # Launch identity disagrees with live proof identity (stale / wrong bind).
    from tools.plan117_custody_contract import write_canonical_json

    write_canonical_json(
        identity_path,
        {
            "schema": "plan117-custody-launch-session-identity-v1",
            "run_attempt_id": "origin-a-3",
            "zed_pid": _RETRY_ZED_PID,
            "zed_process_start_time_utc": _RETRY_START_UTC,
            "connection_id": _RETRY_CONN,
            "acp_session_id": "sess-stale-other",
        },
    )
    _prepare_retry_workspace(custody_roots)
    endpoint = _start_retry_control_endpoint(tmp_path)
    _prime_retry_prereq_phases(runner, custody_roots["capture_root"])
    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.main(
            _retry_cli_args(
                custody_roots,
                stage_ledger=ledger_path,
                launch_identity=identity_path,
                descriptor=endpoint.descriptor_path,
            )
        )
    assert exc.value.reason_code == "invalid_probe_retry_acp_session_identity_mismatch"
    assert not (
        custody_roots["capture_root"] / "reservations" / "origin-a-3-prompt-3.json"
    ).exists()
    assert not endpoint._test_forwarded  # type: ignore[attr-defined]
    endpoint.close()


def test_origin_a_prompt_retry_exit_after_proof_before_prompt_no_relaunch(
    custody_roots: dict[str, Path],
    tmp_path: Path,
) -> None:
    runner = _retry_api(_import_runner())
    ledger_path = tmp_path / "stage-ledger.json"
    identity_path = tmp_path / "launch-identity.json"
    _write_stage_ledger(ledger_path, _retry_eligible_records())
    _write_launch_identity(identity_path)
    _prepare_retry_workspace(custody_roots)
    endpoint = _start_retry_control_endpoint(tmp_path)
    _prime_retry_prereq_phases(runner, custody_roots["capture_root"])
    settings_before = custody_roots["settings_path"].read_bytes()

    # After proof succeeds and reservation is taken, kill the process before prompt.
    real_reserve = runner.reserve_prompt_ordinal

    def reserve_then_exit(**kwargs: Any) -> Path:
        path = real_reserve(**kwargs)
        endpoint._test_proc.mark_exited()  # type: ignore[attr-defined]
        return path

    import tools.run_plan117_custody_feasibility as runner_mod

    # Patch on the module used by main.
    original = runner_mod.reserve_prompt_ordinal
    runner_mod.reserve_prompt_ordinal = reserve_then_exit  # type: ignore[assignment]
    try:
        with pytest.raises(runner.CustodyRunnerError) as exc:
            runner.main(
                _retry_cli_args(
                    custody_roots,
                    stage_ledger=ledger_path,
                    launch_identity=identity_path,
                    descriptor=endpoint.descriptor_path,
                )
            )
    finally:
        runner_mod.reserve_prompt_ordinal = original  # type: ignore[assignment]

    assert (
        exc.value.reason_code == "invalid_probe_retry_process_identity_mismatch"
    ), exc.value.reason_code
    reservation = (
        custody_roots["capture_root"] / "reservations" / "origin-a-3-prompt-3.json"
    )
    assert reservation.is_file()
    assert not (custody_roots["capture_root"] / "attempts" / "origin-a-4").exists()
    assert custody_roots["settings_path"].read_bytes() == settings_before
    assert not endpoint._test_forwarded  # type: ignore[attr-defined]
    endpoint.close()


def test_origin_a_prompt_retry_prompt_failure_cannot_reclaim_ordinal(
    custody_roots: dict[str, Path],
    tmp_path: Path,
) -> None:
    runner = _retry_api(_import_runner())
    ledger_path = tmp_path / "stage-ledger.json"
    identity_path = tmp_path / "launch-identity.json"
    _write_stage_ledger(ledger_path, _retry_eligible_records())
    _write_launch_identity(identity_path)
    _prepare_retry_workspace(custody_roots)

    def boom_forward(_payload: bytes) -> None:
        raise OSError("simulated prompt forward failure")

    endpoint = _start_retry_control_endpoint(tmp_path, prompt_forward=boom_forward)
    _prime_retry_prereq_phases(runner, custody_roots["capture_root"])
    args = _retry_cli_args(
        custody_roots,
        stage_ledger=ledger_path,
        launch_identity=identity_path,
        descriptor=endpoint.descriptor_path,
    )
    with pytest.raises(runner.CustodyRunnerError) as first:
        runner.main(args)
    assert first.value.reason_code == "invalid_probe_retry_control_channel_failure"
    reservation = (
        custody_roots["capture_root"] / "reservations" / "origin-a-3-prompt-3.json"
    )
    assert reservation.is_file()
    before = reservation.read_bytes()
    with pytest.raises(runner.CustodyRunnerError) as second:
        runner.main(args)
    assert second.value.reason_code == "reservation_already_exists"
    assert reservation.read_bytes() == before
    endpoint.close()


def test_origin_a_prompt_retry_ineligible_ledger_skips_live_proof(
    custody_roots: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ledger eligibility (prompt-2 transient) must run before acquire."""
    runner = _retry_api(_import_runner())
    import tools.plan117_custody_relay as relay
    from tools.plan117_custody_contract import (
        EvidenceReference,
        FailureClass,
        StageAttemptRecord,
        StageKind,
        StageStatus,
        normalize_stage_ledger,
    )

    records = list(_fixed_ledger_records())
    records.append(
        StageAttemptRecord(
            record_id="origin-a-3-correlation",
            run_attempt_id="origin-a-3",
            stage=StageKind.CORRELATION_CAPTURE,
            ordinal=3,
            status=StageStatus.SUCCEEDED,
            failure_class=FailureClass.NONE,
            reason_code=None,
            evidence=(
                EvidenceReference(
                    "attempts/origin-a-3/manifest.json",
                    "a" * 64,
                    "raw_file_sha256",
                ),
            ),
            supersedes_record_id="origin-a-3-original-manifest",
            supersedes_sha256="a" * 64,
            amendment_sha256=AMENDMENT_SHA256.lower(),
            created_by="plan117-task3",
            created_utc="2026-08-04T16:00:00Z",
        )
    )
    # next_prompt_ordinal == 3, but prompt-2 is permanent (not retry-eligible).
    records.append(
        StageAttemptRecord(
            record_id="origin-a-3-prompt-2",
            run_attempt_id="origin-a-3",
            stage=StageKind.POST_NEW_PROMPT,
            ordinal=2,
            status=StageStatus.FAILED,
            failure_class=FailureClass.PERMANENT,
            reason_code="AMBIGUOUS_WORKSPACE_REFERENCE",
            evidence=(
                EvidenceReference(
                    "attempts/origin-a-3/prompt.json",
                    "b" * 64,
                    "raw_file_sha256",
                ),
            ),
            supersedes_record_id="origin-a-3-original-observation",
            supersedes_sha256="b" * 64,
            amendment_sha256=AMENDMENT_SHA256.lower(),
            created_by="plan117-task3",
            created_utc="2026-08-04T16:00:00Z",
        )
    )
    ledger = normalize_stage_ledger(records)
    assert ledger.next_prompt_ordinal == 3

    ledger_path = tmp_path / "stage-ledger.json"
    identity_path = tmp_path / "launch-identity.json"
    _write_stage_ledger(ledger_path, tuple(records))
    _write_launch_identity(identity_path)
    _prepare_retry_workspace(custody_roots)
    endpoint = _start_retry_control_endpoint(tmp_path)
    _prime_retry_prereq_phases(runner, custody_roots["capture_root"])

    def forbid_acquire(**_kwargs: Any) -> Any:
        raise AssertionError("acquire_live_session_proof must not run for ineligible ledger")

    monkeypatch.setattr(relay, "acquire_live_session_proof", forbid_acquire)
    if hasattr(runner, "acquire_live_session_proof"):
        monkeypatch.setattr(runner, "acquire_live_session_proof", forbid_acquire)

    with pytest.raises(runner.CustodyRunnerError) as exc:
        runner.main(
            _retry_cli_args(
                custody_roots,
                stage_ledger=ledger_path,
                launch_identity=identity_path,
                descriptor=endpoint.descriptor_path,
            )
        )
    assert exc.value.reason_code == "invalid_probe_stage_accounting"
    assert exc.value.field_path == "prompt_ordinal_2"
    assert not (
        custody_roots["capture_root"] / "reservations" / "origin-a-3-prompt-3.json"
    ).exists()
    endpoint.close()