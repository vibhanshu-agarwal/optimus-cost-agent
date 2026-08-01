"""Staged end-to-end evidence_gather proof against real Zed / acpx / DWM / keyring.

Invokes only ``tools/evidence_gather.py`` stages separately. Determinate crash/render
outcomes require operator-approved real exercises; missing claims are recorded and
left open rather than synthesized (plan Task 9 Step 2).
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

import keyring
import pytest

from evidence_handoff.collector.models import Outcome
from optimus.acp.launch_approvals import KeyringApprovalStore, build_approval_record
from optimus.acp.launch_gate import resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.operator_paths import bootstrap_workspace_runtime_root, resolve_authorized_operator_paths
from optimus.acp.trusted_paths import resolve_workspace_identity
from tests.unit.acp.conftest import FakeKeyring
from tools.evidence_gather_support import redaction as redaction_mod
from tools.evidence_gather_support import zed_logs as zed_mod
from tools.evidence_gather_support.common import HostError

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "evidence" / "scenarios" / "zed-session.toml"
MISSING_CLAIMS_PATH = REPO_ROOT / "reports" / "task9-evidence-collector" / "missing-claims.json"

pytestmark = [
    pytest.mark.requires_acpx,
    pytest.mark.requires_zed,
    pytest.mark.requires_windows_desktop,
    pytest.mark.requires_os_keyring,
]

_PROCESS_CREATE_THREAD = 0x0002
_PROCESS_QUERY_INFORMATION = 0x0400
_PROCESS_VM_OPERATION = 0x0008
_PROCESS_VM_WRITE = 0x0020
_PROCESS_VM_READ = 0x0010
_INDUCE_ACCESS = (
    _PROCESS_CREATE_THREAD
    | _PROCESS_QUERY_INFORMATION
    | _PROCESS_VM_OPERATION
    | _PROCESS_VM_WRITE
    | _PROCESS_VM_READ
)


def _resolve_agent() -> Path:
    which = shutil.which("optimus-agent")
    if which:
        return Path(which).resolve()
    candidate = REPO_ROOT / ".venv" / "Scripts" / "optimus-agent.exe"
    if candidate.is_file():
        return candidate.resolve()
    pytest.fail("optimus_agent_missing")


def _load_dotenv_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def _require_client_gateway_credentials() -> tuple[str, str]:
    gateway = os.environ.get("OPTIMUS_GATEWAY_URL", "").strip()
    api_key = os.environ.get("OPTIMUS_API_KEY", "").strip()
    if not gateway or not api_key:
        dotenv = _load_dotenv_values(REPO_ROOT / ".env")
        gateway = gateway or dotenv.get("OPTIMUS_GATEWAY_URL", "").strip()
        api_key = api_key or dotenv.get("OPTIMUS_API_KEY", "").strip()
    if not gateway or not api_key:
        pytest.fail("live_client_credentials_missing")
    return gateway, api_key


def _require_gateway_reachable(gateway_url: str) -> None:
    probe = gateway_url.rstrip("/") + "/"
    try:
        with urllib_request.urlopen(probe, timeout=3) as response:  # noqa: S310
            _ = getattr(response, "status", 200)
    except urllib_error.HTTPError:
        return
    except (urllib_error.URLError, TimeoutError, OSError):
        pytest.fail("gateway_unreachable")


def _require_acpx() -> None:
    if shutil.which("acpx") is None:
        pytest.fail("acpx_not_on_path")


def _zed_executable() -> Path:
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        pytest.fail("LOCALAPPDATA_missing")
    candidate = Path(local) / "Programs" / "Zed" / "bin" / "Zed.exe"
    if candidate.is_file():
        return candidate.resolve()
    pytest.fail("zed_executable_missing")


def _require_zed_version(exe: Path) -> str:
    completed = subprocess.run(
        [str(exe), "--version"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=30,
    )
    version = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0 or not version:
        pytest.fail("zed_version_failed")
    try:
        zed_mod.require_supported_client_identity("zed-1.13.1", reported_version=version)
    except HostError as exc:
        pytest.fail(f"zed_version_unsupported:{exc.code}:{version}")
    return version


def _resolve_expected_pid(observed: tuple[int, ...]) -> int:
    override = os.environ.get("OPTIMUS_EVIDENCE_ZED_PID", "").strip()
    if override:
        pid = int(override)
        zed_mod.correlate_zed_processes(expected_pids=(pid,), observed_pids=observed)
        return pid
    if not observed:
        raise HostError("zed_process_lookup_failed")
    if len(observed) != 1:
        raise HostError("zed_multi_instance_ambiguous")
    return observed[0]


def _ensure_zed_running(exe: Path, open_path: Path) -> tuple[int, tuple[int, ...]]:
    try:
        observed = zed_mod.discover_zed_editor_pids()
        return _resolve_expected_pid(observed), observed
    except HostError as exc:
        if exc.code == "zed_multi_instance_ambiguous":
            raise
        if exc.code not in {"zed_process_lookup_failed", "zed_unrelated_process"}:
            raise
    subprocess.Popen(  # noqa: S603 — absolute Zed path, shell=False
        [str(exe), str(open_path)],
        cwd=str(REPO_ROOT),
        shell=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            observed = zed_mod.discover_zed_editor_pids()
            return _resolve_expected_pid(observed), observed
        except HostError as exc:
            if exc.code == "zed_multi_instance_ambiguous":
                raise
        time.sleep(0.5)
    pytest.fail("zed_process_not_started")


def _induce_zed_crashpad_fault(pid: int) -> None:
    """Fault the editor so Zed's crash-handler can emit dump/panic under logs/."""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(_INDUCE_ACCESS, False, int(pid))
    if not handle:
        pytest.fail(f"zed_crash_open_process_failed:{ctypes.get_last_error()}")
    thread = None
    try:
        thread_id = ctypes.c_ulong(0)
        thread = kernel32.CreateRemoteThread(
            handle,
            None,
            0,
            ctypes.c_void_p(1),
            None,
            0,
            ctypes.byref(thread_id),
        )
        if not thread:
            pytest.fail(f"zed_crash_remote_thread_failed:{ctypes.get_last_error()}")
        kernel32.WaitForSingleObject(thread, 5_000)
    finally:
        if thread:
            kernel32.CloseHandle(thread)
        kernel32.CloseHandle(handle)


def _seed_durable(*, workspace: Path, env: dict[str, str], fake: FakeKeyring) -> None:
    snapshot = LaunchEnvironmentSnapshot.capture(env)
    paths = resolve_authorized_operator_paths(
        workspace_root=workspace,
        snapshot_values=snapshot.values,
        platform_name=sys.platform,
    )
    bootstrap_workspace_runtime_root(paths)
    store = KeyringApprovalStore(keyring_backend=fake, runtime_root=paths.runtime_root)
    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_identity=resolve_workspace_identity(workspace),
        operator_paths=paths,
        hmac_key=store.hmac_key,
        credential_keyring_backend=keyring,
    )
    record = build_approval_record(
        mode="durable",
        workspace_identity=candidate.workspace_identity,
        security_literals=candidate.security_literals,
        secret_fingerprints=candidate.secret_fingerprints,
        monotonic_grants=candidate.monotonic_grants,
        model_observation=candidate.model_observation,
        hmac_key=store.hmac_key,
    )
    store.write_durable(record)


def _record_missing(path: Path, claim: str, reason: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
    existing.append(
        {
            "claim": claim,
            "status": "missing",
            "reason": reason,
            "recorded_at": datetime.now(tz=UTC).isoformat(),
        }
    )
    path.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_staged_collector_missing_render_stays_indeterminate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real staged path: collect + classify without render → indeterminate; no report."""
    import tools.evidence_gather as gather

    if sys.platform != "win32":
        pytest.skip("requires_windows_desktop")

    _require_acpx()
    gateway, api_key = _require_client_gateway_credentials()
    _require_gateway_reachable(gateway)
    _ = api_key

    # Durable launch approval is authored against the repo workspace (Task 5 pattern).
    workspace = REPO_ROOT.resolve()
    capture = (tmp_path / "capture").resolve()
    user_data = (tmp_path / "user-data").resolve()
    staging = (tmp_path / "staging").resolve()
    quarantine = (tmp_path / "quarantine").resolve()
    sanitized = (tmp_path / "sanitized").resolve()
    forbidden = (tmp_path / "forbidden").resolve()
    for path in (user_data, staging, quarantine, sanitized, forbidden):
        path.mkdir()

    ndjson_path = (workspace / ".optimus" / "debug-acp.ndjson").resolve()
    ndjson_path.parent.mkdir(parents=True, exist_ok=True)
    if not ndjson_path.exists():
        ndjson_path.write_bytes(b"")

    env = {
        "OPTIMUS_GATEWAY_URL": gateway,
        "OPTIMUS_API_KEY": os.environ.get("OPTIMUS_API_KEY")
        or _load_dotenv_values(REPO_ROOT / ".env").get("OPTIMUS_API_KEY", ""),
        "OPTIMUS_REDIS_URL": os.environ.get(
            "OPTIMUS_REDIS_URL",
            _load_dotenv_values(REPO_ROOT / ".env").get("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0"),
        ),
    }
    for name, value in env.items():
        if value:
            monkeypatch.setenv(name, value)

    fake = FakeKeyring()
    _seed_durable(workspace=workspace, env=env, fake=fake)
    real_authorize = redaction_mod.authorize_redaction_launch

    def authorize_live(**kwargs):
        return real_authorize(
            workspace_root=kwargs["workspace_root"],
            environ=env,
            keyring_backend=fake,
            credential_keyring_backend=keyring,
        )

    monkeypatch.setattr(redaction_mod, "authorize_redaction_launch", authorize_live)

    assert gather.main(
        [
            "prepare",
            "--scenario",
            str(FIXTURE.resolve()),
            "--capture-root",
            str(capture),
            "--bind",
            "model=operator-supplied",
        ]
    ) == 0
    assert gather.main(
        [
            "check",
            "--scenario",
            str(FIXTURE.resolve()),
            "--capture-root",
            str(capture),
            "--bind",
            "model=operator-supplied",
        ]
    ) == 0

    # Collect through the entry point; correlation auto-discovered after real acpx.
    collect_code = gather.main(
        [
            "collect",
            "--scenario",
            str(FIXTURE.resolve()),
            "--capture-root",
            str(capture),
            "--bind",
            "model=operator-supplied",
            "--workspace-root",
            str(workspace),
            "--agent-executable",
            str(_resolve_agent()),
            "--prompt",
            "Reply with exactly: ok",
            "--timeout-seconds",
            "180",
            "--ndjson-path",
            str(ndjson_path),
            "--correlate-session-id",
            "auto",
            "--correlate-request-id",
            "auto",
            "--correlate-run-id",
            "auto",
            "--debug-session-id",
            "auto",
            "--no-auto-start",
        ]
    )
    if collect_code != 0:
        _record_missing(
            MISSING_CLAIMS_PATH,
            "indeterminate_via_live_collect",
            f"entry-point collect returned {collect_code}; live indeterminate path incomplete",
        )
        pytest.fail(f"collect_failed:{collect_code}")

    run_dir = next(path for path in capture.iterdir() if path.is_dir())
    classify_result = (tmp_path / "classify-result.json").resolve()
    assert (
        gather.main(
            [
                "classify",
                "--scenario",
                str(FIXTURE.resolve()),
                "--capture-root",
                str(capture),
                "--result",
                str(classify_result),
                "--bind",
                "model=operator-supplied",
            ]
        )
        == 0
    )
    classified = json.loads(classify_result.read_text(encoding="utf-8"))
    assert classified["outcome"] == Outcome.INDETERMINATE.value
    provisional = json.loads((run_dir / "provisional-result.json").read_text(encoding="utf-8"))
    assert provisional["outcome"] == Outcome.INDETERMINATE.value

    report = (tmp_path / "report.json").resolve()
    redact_result = (tmp_path / "redact-result.json").resolve()
    profile = redaction_mod.resolve_operator_profile_root()
    real_build = redaction_mod.build_redaction_host_context

    def build_injected(**kwargs):
        kwargs.setdefault("operator_profile_root", profile)
        kwargs.setdefault(
            "operator_identity_values",
            redaction_mod.resolve_operator_identity_values(),
        )
        return real_build(**kwargs)

    monkeypatch.setattr(redaction_mod, "build_redaction_host_context", build_injected)
    assert (
        gather.main(
            [
                "redact",
                "--scenario",
                str(FIXTURE.resolve()),
                "--workspace-root",
                str(workspace),
                "--user-data-root",
                str(user_data),
                "--forbidden-root",
                str(forbidden),
                "--capture-root",
                str(capture),
                "--staging-root",
                str(staging),
                "--quarantine-root",
                str(quarantine),
                "--sanitized-root",
                str(sanitized),
                "--result",
                str(redact_result),
                "--report",
                str(report),
                "--bind",
                "model=operator-supplied",
            ]
        )
        == 0
    )
    redact_summary = json.loads(redact_result.read_text(encoding="utf-8"))
    assert redact_summary["outcome"] == Outcome.INDETERMINATE.value
    if report.exists():
        inspect_code = gather.main(["inspect", "--report", str(report)])
        assert inspect_code == 0
    else:
        assert redact_summary["outcome"] == provisional["outcome"]

    for claim, reason in (
        (
            "rendered_then_crashed",
            "requires operator-approved real render observation plus later correlated Zed crash",
        ),
        (
            "rendered_stable",
            "requires real render, liveness, complete observation window, and no crash",
        ),
    ):
        _record_missing(MISSING_CLAIMS_PATH, claim, reason)
    assert MISSING_CLAIMS_PATH.is_file()
    recorded = json.loads(MISSING_CLAIMS_PATH.read_text(encoding="utf-8"))
    assert {"rendered_then_crashed", "rendered_stable"} <= {item["claim"] for item in recorded}


def test_staged_collector_client_crashed_without_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real crash, no render, through prepare→collect→classify→redact→inspect.

    Crashes the single Zed editor PID (closes every window/tab). Requires
    ``OPTIMUS_EVIDENCE_ZED_CRASH_EXERCISE=1`` after confirming no unsaved work.
    """
    import tools.evidence_gather as gather
    from tools.evidence_gather_support import acp as acp_mod

    if sys.platform != "win32":
        pytest.skip("requires_windows_desktop")
    if os.environ.get("OPTIMUS_EVIDENCE_ZED_CRASH_EXERCISE", "").strip() != "1":
        _record_missing(
            MISSING_CLAIMS_PATH,
            "client_crashed",
            "set OPTIMUS_EVIDENCE_ZED_CRASH_EXERCISE=1 after confirming no unsaved "
            "Zed work; one editor PID owns all windows",
        )
        pytest.fail(
            "client_crashed_exercise_incomplete: set OPTIMUS_EVIDENCE_ZED_CRASH_EXERCISE=1 "
            "after confirming no unsaved work in any Zed window"
        )

    _require_acpx()
    gateway, api_key = _require_client_gateway_credentials()
    _require_gateway_reachable(gateway)
    _ = api_key

    exe = _zed_executable()
    version = _require_zed_version(exe)
    log_root = zed_mod.require_zed_log_root(
        zed_mod.default_live_zed_log_root(),
        expected_live_root=zed_mod.default_live_zed_log_root(),
    )
    probe = (tmp_path / "zed-staged-crash-probe.txt").resolve()
    probe.write_text("optimus-staged-client-crashed-probe\n", encoding="utf-8")
    try:
        pid, observed = _ensure_zed_running(exe, probe)
    except HostError as exc:
        pytest.fail(exc.code)
    zed_mod.correlate_zed_processes(expected_pids=(pid,), observed_pids=observed)

    workspace = REPO_ROOT.resolve()
    capture = (tmp_path / "capture").resolve()
    user_data = (tmp_path / "user-data").resolve()
    staging = (tmp_path / "staging").resolve()
    quarantine = (tmp_path / "quarantine").resolve()
    sanitized = (tmp_path / "sanitized").resolve()
    forbidden = (tmp_path / "forbidden").resolve()
    for path in (user_data, staging, quarantine, sanitized, forbidden):
        path.mkdir()

    ndjson_path = (workspace / ".optimus" / "debug-acp.ndjson").resolve()
    ndjson_path.parent.mkdir(parents=True, exist_ok=True)
    if not ndjson_path.exists():
        ndjson_path.write_bytes(b"")

    env = {
        "OPTIMUS_GATEWAY_URL": gateway,
        "OPTIMUS_API_KEY": os.environ.get("OPTIMUS_API_KEY")
        or _load_dotenv_values(REPO_ROOT / ".env").get("OPTIMUS_API_KEY", ""),
        "OPTIMUS_REDIS_URL": os.environ.get(
            "OPTIMUS_REDIS_URL",
            _load_dotenv_values(REPO_ROOT / ".env").get("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0"),
        ),
    }
    for name, value in env.items():
        if value:
            monkeypatch.setenv(name, value)

    fake = FakeKeyring()
    _seed_durable(workspace=workspace, env=env, fake=fake)
    real_authorize = redaction_mod.authorize_redaction_launch

    def authorize_live(**kwargs):
        return real_authorize(
            workspace_root=kwargs["workspace_root"],
            environ=env,
            keyring_backend=fake,
            credential_keyring_backend=keyring,
        )

    monkeypatch.setattr(redaction_mod, "authorize_redaction_launch", authorize_live)

    real_spawn = acp_mod.spawn_acpx

    def spawn_then_induce_crash(**kwargs):
        code = real_spawn(**kwargs)
        if code != 0:
            return code
        # Snapshot already taken inside collect; fault after ACP so watch sees dump.
        _induce_zed_crashpad_fault(pid)
        time.sleep(2.0)
        return code

    monkeypatch.setattr(acp_mod, "spawn_acpx", spawn_then_induce_crash)

    assert gather.main(
        [
            "prepare",
            "--scenario",
            str(FIXTURE.resolve()),
            "--capture-root",
            str(capture),
            "--bind",
            "model=operator-supplied",
        ]
    ) == 0
    assert gather.main(
        [
            "check",
            "--scenario",
            str(FIXTURE.resolve()),
            "--capture-root",
            str(capture),
            "--bind",
            "model=operator-supplied",
        ]
    ) == 0

    collect_code = gather.main(
        [
            "collect",
            "--scenario",
            str(FIXTURE.resolve()),
            "--capture-root",
            str(capture),
            "--bind",
            "model=operator-supplied",
            "--workspace-root",
            str(workspace),
            "--agent-executable",
            str(_resolve_agent()),
            "--prompt",
            "Reply with exactly: ok",
            "--timeout-seconds",
            "180",
            "--ndjson-path",
            str(ndjson_path),
            "--correlate-session-id",
            "auto",
            "--correlate-request-id",
            "auto",
            "--correlate-run-id",
            "auto",
            "--debug-session-id",
            "auto",
            "--no-auto-start",
            "--zed-log-root",
            str(log_root),
            "--zed-client-identity",
            "zed-1.13.1",
            "--zed-version",
            version,
            "--zed-watch-seconds",
            "90",
            "--zed-pid",
            str(pid),
        ]
    )
    if collect_code != 0:
        _record_missing(
            MISSING_CLAIMS_PATH,
            "client_crashed",
            f"entry-point collect with zed watch returned {collect_code}",
        )
        pytest.fail(f"collect_failed:{collect_code}")

    run_dir = next(path for path in capture.iterdir() if path.is_dir())
    bundle = json.loads((run_dir / "raw-bundle.json").read_text(encoding="utf-8"))
    zed_batches = [
        batch for batch in bundle["batches"] if batch["collector_id"] == "zed_crash_collector"
    ]
    assert zed_batches, "expected zed_crash_collector batch in raw bundle"
    crash_roles = {
        obs["artifact_role"]
        for batch in zed_batches
        for obs in batch["observations"]
        if obs.get("artifact_role") in {"zed_process_dump", "zed_panic_json"}
    }
    assert crash_roles, "expected dump/panic roles in zed batch"

    classify_result = (tmp_path / "classify-result.json").resolve()
    assert (
        gather.main(
            [
                "classify",
                "--scenario",
                str(FIXTURE.resolve()),
                "--capture-root",
                str(capture),
                "--result",
                str(classify_result),
                "--bind",
                "model=operator-supplied",
            ]
        )
        == 0
    )
    classified = json.loads(classify_result.read_text(encoding="utf-8"))
    assert classified["outcome"] == Outcome.CLIENT_CRASHED.value
    provisional = json.loads((run_dir / "provisional-result.json").read_text(encoding="utf-8"))
    assert provisional["outcome"] == Outcome.CLIENT_CRASHED.value
    assert "render_observed" not in classified.get("claim_kinds", [])

    report = (tmp_path / "report.json").resolve()
    redact_result = (tmp_path / "redact-result.json").resolve()
    profile = redaction_mod.resolve_operator_profile_root()
    real_build = redaction_mod.build_redaction_host_context

    def build_injected(**kwargs):
        kwargs.setdefault("operator_profile_root", profile)
        kwargs.setdefault(
            "operator_identity_values",
            redaction_mod.resolve_operator_identity_values(),
        )
        return real_build(**kwargs)

    monkeypatch.setattr(redaction_mod, "build_redaction_host_context", build_injected)
    assert (
        gather.main(
            [
                "redact",
                "--scenario",
                str(FIXTURE.resolve()),
                "--workspace-root",
                str(workspace),
                "--user-data-root",
                str(user_data),
                "--forbidden-root",
                str(forbidden),
                "--capture-root",
                str(capture),
                "--staging-root",
                str(staging),
                "--quarantine-root",
                str(quarantine),
                "--sanitized-root",
                str(sanitized),
                "--result",
                str(redact_result),
                "--report",
                str(report),
                "--bind",
                "model=operator-supplied",
            ]
        )
        == 0
    )
    redact_summary = json.loads(redact_result.read_text(encoding="utf-8"))
    assert redact_summary["outcome"] == Outcome.CLIENT_CRASHED.value
    if report.exists():
        assert gather.main(["inspect", "--report", str(report)]) == 0

    evidence = {
        "schema": "evidence-staged-client-crashed-v1",
        "complete": True,
        "outcome": Outcome.CLIENT_CRASHED.value,
        "run_id": classified["run_id"],
        "zed_pid": pid,
        "zed_version": version,
        "crash_roles": sorted(crash_roles),
        "raw_bundle_sha256": classified["raw_bundle_sha256"],
        "claim_kinds": classified.get("claim_kinds"),
        "recorded_at": datetime.now(tz=UTC).isoformat(),
    }
    evidence_path = MISSING_CLAIMS_PATH.parent / "client-crashed-evidence.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, sort_keys=True))

    # Drop client_crashed from missing-claims if a prior incomplete run recorded it.
    if MISSING_CLAIMS_PATH.is_file():
        remaining = [
            item
            for item in json.loads(MISSING_CLAIMS_PATH.read_text(encoding="utf-8"))
            if item.get("claim") != "client_crashed"
        ]
        MISSING_CLAIMS_PATH.write_text(
            json.dumps(remaining, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def test_staged_determinate_paths_require_operator_exercises(tmp_path: Path) -> None:
    """Document that render-dependent live claims stay open without scoped render production."""
    if os.environ.get("OPTIMUS_EVIDENCE_STAGED_DETERMINATE") == "1":
        pytest.fail(
            "OPTIMUS_EVIDENCE_STAGED_DETERMINATE=1 is set but render-observation "
            "production is not yet scoped; do not enable until that gap is closed"
        )
    missing = tmp_path / "determinate-unavailable.json"
    _record_missing(
        missing,
        "render_dependent_matrix",
        "rendered_then_crashed/rendered_stable parked pending render-observation scoping",
    )
    assert missing.is_file()
