"""Staged end-to-end evidence_gather proof against real Zed / acpx / DWM / keyring.

Invokes only ``tools/evidence_gather.py`` stages separately. Determinate crash/render
outcomes require operator-approved real exercises; missing claims are recorded and
left open rather than synthesized (plan Task 9 Step 2).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
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

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "evidence" / "scenarios" / "zed-session.toml"
MISSING_CLAIMS_PATH = REPO_ROOT / "reports" / "task9-evidence-collector" / "missing-claims.json"

pytestmark = [
    pytest.mark.requires_acpx,
    pytest.mark.requires_zed,
    pytest.mark.requires_windows_desktop,
    pytest.mark.requires_os_keyring,
]


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
            "client_crashed",
            "requires operator-approved real correlated Zed crash without preceding render",
        ),
        (
            "rendered_stable",
            "requires real render, liveness, complete observation window, and no crash",
        ),
    ):
        _record_missing(MISSING_CLAIMS_PATH, claim, reason)
    assert MISSING_CLAIMS_PATH.is_file()
    recorded = json.loads(MISSING_CLAIMS_PATH.read_text(encoding="utf-8"))
    assert {"rendered_then_crashed", "client_crashed", "rendered_stable"} <= {
        item["claim"] for item in recorded
    }


def test_staged_determinate_paths_require_operator_exercises(tmp_path: Path) -> None:
    """Document that determinate live claims stay open without real exercises."""
    if os.environ.get("OPTIMUS_EVIDENCE_STAGED_DETERMINATE") == "1":
        pytest.fail(
            "OPTIMUS_EVIDENCE_STAGED_DETERMINATE=1 is set but this test does not "
            "automate render/crash injection; implement operator-driven steps before enabling"
        )
    missing = tmp_path / "determinate-unavailable.json"
    _record_missing(
        missing,
        "determinate_matrix",
        "operator exercises not enabled; feature remains open per Task 9 Step 2",
    )
    assert missing.is_file()
