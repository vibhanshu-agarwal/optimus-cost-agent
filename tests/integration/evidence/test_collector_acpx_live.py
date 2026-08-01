"""Live acpx-driven evidence collection for the evidence_gather collect stage.

Requires independently authored ``acpx`` on PATH and a real agent process.
Follow ``docs/runbooks/local-live-dependencies.md`` §6: keep persistent
``optimus-trust run-gateway`` alive, then run this module with client fixture
vars from the checkout ``.env`` (never print secret values).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "evidence" / "scenarios" / "zed-session.toml"
KNOWN_SECRET_CANARIES = (
    "sk-ant-api03-CANARY_DO_NOT_USE",
    "OPTIMUS_API_KEY_VALUE_CANARY",
)

pytestmark = [pytest.mark.requires_acpx]


def _gather():
    import tools.evidence_gather as gather

    return gather


def _load_dotenv_values(path: Path) -> dict[str, str]:
    """Parse untrusted KEY=VALUE lines; never log values."""
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
        pytest.fail(
            "live_client_credentials_missing: set OPTIMUS_GATEWAY_URL/OPTIMUS_API_KEY "
            "or provide checkout .env while persistent run-gateway is up"
        )
    return gateway, api_key


def _require_acpx() -> tuple[str, str]:
    path = shutil.which("acpx")
    if path is None:
        pytest.fail("acpx_not_on_path")
    completed = subprocess.run(
        [path, "--version"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=30,
    )
    if completed.returncode != 0:
        pytest.fail("acpx_version_failed")
    version = (completed.stdout or completed.stderr or "").strip()
    if not version:
        pytest.fail("acpx_version_empty")
    return path, version


def _require_agent() -> Path:
    which = shutil.which("optimus-agent")
    if which:
        return Path(which).resolve()
    candidate = REPO_ROOT / ".venv" / "Scripts" / "optimus-agent.exe"
    if candidate.is_file():
        return candidate.resolve()
    pytest.fail("optimus_agent_not_on_path")


def _require_gateway_reachable(gateway_url: str) -> None:
    import urllib.error
    import urllib.request

    # Local gateway answers HTTP on the bind port; /health may be 501.
    probe = gateway_url.rstrip("/") + "/"
    try:
        with urllib.request.urlopen(probe, timeout=3) as response:  # noqa: S310 - loopback live probe
            _ = getattr(response, "status", 200)
    except urllib.error.HTTPError:
        # Any HTTP response proves the listener is up (including 4xx/5xx stubs).
        return
    except (urllib.error.URLError, TimeoutError, OSError):
        pytest.fail(
            "gateway_unreachable: start persistent gateway per "
            "docs/runbooks/local-live-dependencies.md §6 "
            "(optimus-trust --workspace-root . run-gateway --with-local-phoenix)"
        )


@pytest.mark.requires_acpx
def test_collector_acpx_live_completion_without_render_claim(tmp_path: Path) -> None:
    acpx_path, acpx_version = _require_acpx()
    agent = _require_agent()
    gateway, api_key = _require_client_gateway_credentials()
    _require_gateway_reachable(gateway)

    gather = _gather()
    capture = (tmp_path / "capture").resolve()
    # Durable approval is authored against the repo workspace root.
    workspace = REPO_ROOT.resolve()
    ndjson_path = (workspace / ".optimus" / "debug-acp.ndjson").resolve()
    ndjson_path.parent.mkdir(parents=True, exist_ok=True)
    if not ndjson_path.exists():
        ndjson_path.write_text("", encoding="utf-8")

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

    from tools.evidence_gather_support import acp as acp_mod
    from tools.evidence_gather_support import ndjson as ndjson_mod
    from tools.evidence_gather_support.common import HostError

    snapshot = ndjson_mod.snapshot_source(ndjson_path)
    launch_session_id = f"live-{hashlib.sha256(os.urandom(8)).hexdigest()[:12]}"
    command = acp_mod.build_acpx_command(
        acpx_path=acpx_path,
        workspace_root=workspace,
        agent_executable=agent,
        prompt="Reply with exactly: pong",
        launch_session_id=launch_session_id,
        no_auto_start=True,
        launch_approval_id="appr_8339fa774a4c047ea22f246d",
    )
    assert command[0] == acpx_path
    assert "--no-auto-start" in command[command.index("--agent") + 1]
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "PATHEXT",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "HOME",
            "SYSTEMDRIVE",
            "COMSPEC",
        }
    }
    # Do not inject OPTIMUS_* into the acpx/agent snapshot. Persistent
    # run-gateway + durable approval project credentials via the launch gate.
    _ = (gateway, api_key)  # prove client credentials exist for canary scan only

    stdout_capture = (capture / "acpx-stdout.ndjson").resolve()
    stderr_capture = (capture / "acpx-stderr.txt").resolve()
    try:
        rc = acp_mod.spawn_acpx(
            command=command,
            cwd=workspace,
            env=env,
            timeout_seconds=180,
            stdout_path=stdout_capture,
            stderr_path=stderr_capture,
        )
    except HostError as exc:
        pytest.fail(f"acpx_spawn_failed:{exc.code}")
    if rc != 0:
        stderr_bytes = stderr_capture.read_bytes() if stderr_capture.is_file() else b""
        stdout_bytes = stdout_capture.read_bytes() if stdout_capture.is_file() else b""
        pytest.fail(
            "acpx_nonzero_exit:"
            f"rc={rc}:"
            f"stderr_sha256={hashlib.sha256(stderr_bytes).hexdigest()}:"
            f"stderr_bytes={len(stderr_bytes)}:"
            f"stdout_bytes={len(stdout_bytes)}"
        )

    records = ndjson_mod.read_ordered_suffix(ndjson_path, snapshot)
    exits = [item for item in records if item.get("location") == "server.py:process_request:exit"]
    prompts = [
        item for item in records if item.get("location") == "spec.py:_handle_session_prompt:entry"
    ]
    if not exits or not prompts:
        locations = [str(item.get("location")) for item in records[:20]]
        pytest.fail(
            "acpx_missing_completion_events:"
            f"records={len(records)}:"
            f"locations={locations}:"
            f"stdout_bytes={stdout_capture.stat().st_size if stdout_capture.is_file() else 0}:"
            f"stderr_bytes={stderr_capture.stat().st_size if stderr_capture.is_file() else 0}"
        )
    prompt = prompts[-1]
    pdata = prompt.get("data") if isinstance(prompt.get("data"), dict) else {}
    session_id = str(pdata.get("session_id") or "")
    request_id = str(pdata.get("request_id") or "")
    run_id = str(pdata.get("run_id") or "")
    debug_session = str(prompt.get("sessionId") or "")
    assert session_id and request_id and run_id and debug_session

    foreign = dict(exits[-1])
    foreign["sessionId"] = "debug_foreign"
    with pytest.raises(HostError) as foreign_exc:
        ndjson_mod.normalize_completion(
            (*prompts, foreign),
            correlate_session_id=session_id,
            correlate_request_id=request_id,
            correlate_run_id=run_id,
            expected_debug_session_id=debug_session,
            scenario_id="zed-session",
            run_id="live-run",
            evidence_sha256=("b" * 64,),
        )
    assert foreign_exc.value.code == "foreign_ndjson_suffix"

    errored = dict(exits[-1])
    data = dict(errored.get("data") or {})
    data["has_error"] = True
    errored["data"] = data
    with pytest.raises(HostError) as error_exc:
        ndjson_mod.normalize_completion(
            (*prompts, errored),
            correlate_session_id=session_id,
            correlate_request_id=request_id,
            correlate_run_id=run_id,
            expected_debug_session_id=debug_session,
            scenario_id="zed-session",
            run_id="live-run",
            evidence_sha256=("b" * 64,),
        )
    assert error_exc.value.code == "completion_has_error"

    claim = ndjson_mod.normalize_completion(
        records,
        correlate_session_id=session_id,
        correlate_request_id=request_id,
        correlate_run_id=run_id,
        expected_debug_session_id=debug_session,
        scenario_id="zed-session",
        run_id="live-run",
        evidence_sha256=("c" * 64,),
    )
    assert claim.claim_kind.value == "completion_observed"
    assert claim.claim_kind.value != "render_observed"

    suffix_digest = ndjson_mod.suffix_sha256(ndjson_path, snapshot)
    assert len(suffix_digest) == 64
    assert acpx_version
    assert hashlib.sha256(acpx_path.encode("utf-8")).hexdigest()
    blob = ndjson_path.read_bytes()
    for canary in KNOWN_SECRET_CANARIES:
        assert canary.encode("utf-8") not in blob
    assert api_key.encode("utf-8") not in blob

    # Content-free live identities for the review relay (no secret values).
    print(f"acpx_version={acpx_version}")
    print(f"acpx_path_digest={hashlib.sha256(acpx_path.encode('utf-8')).hexdigest()}")
    print(f"suffix_sha256={suffix_digest}")
    print(f"completion_claim={claim.claim_kind.value}")
    print(f"exit_count={len(exits)}")
    print(f"prompt_count={len(prompts)}")
