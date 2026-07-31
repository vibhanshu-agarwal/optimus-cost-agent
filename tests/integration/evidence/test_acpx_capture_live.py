"""Live acpx + redaction-gate evidence (real keyring, gateway, spawned process).

Operator supplies absolute non-overlapping roots via environment variables that
*this test* reads and passes as explicit function arguments. The runner itself
never reads those ambient names for roots.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = REPO_ROOT / "tools" / "run_redaction_gate_live_evidence.py"

pytestmark = [
    pytest.mark.requires_os_keyring,
    pytest.mark.requires_gateway,
    pytest.mark.e2e,
]


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_redaction_gate_live_evidence",
        RUNNER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _require_operator_roots() -> tuple[Path, Path, Path, Path]:
    names = (
        "evidence_capture_root",
        "evidence_staging_root",
        "evidence_quarantine_root",
        "evidence_output_root",
    )
    missing = [name for name in names if not os.environ.get(name, "").strip()]
    if missing:
        pytest.skip(
            "operator must set shell-local roots: " + ", ".join(missing)
        )
    return (
        Path(os.environ["evidence_capture_root"]).resolve(),
        Path(os.environ["evidence_staging_root"]).resolve(),
        Path(os.environ["evidence_quarantine_root"]).resolve(),
        Path(os.environ["evidence_output_root"]).resolve(),
    )


def test_acpx_capture_streams_into_redaction_gate_without_raw_transcript() -> None:
    runner = _load_runner()
    capture, staging, quarantine, output = _require_operator_roots()
    for root in (capture, staging, quarantine, output):
        root.mkdir(parents=True, exist_ok=True)

    gateway = os.environ.get("OPTIMUS_GATEWAY_URL", "").strip()
    api_key = os.environ.get("OPTIMUS_API_KEY", "").strip()
    if not gateway or not api_key:
        pytest.skip("OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY required for e2e acpx drive")

    summary = runner.run_verify(
        capture_root=capture,
        staging_root=staging,
        quarantine_root=quarantine,
        output_root=output,
        workspace_root=REPO_ROOT,
        drive_acp=True,
    )
    assert summary["raw_transcript_present"] is False
    assert summary["acpx_version"]
    assert summary["identities"]["secret_count"] >= 1
    assert summary["drive_acp"] is True

    by_role = {item["role"]: item for item in summary["artifacts"]}
    assert by_role["zed_debug_line"]["disposition"] == "promoted"
    assert by_role["redaction_canaries"]["disposition"] == "promoted"
    assert by_role["acp_truncated_tail"]["disposition"] == "promoted"
    assert isinstance(by_role["acp_truncated_tail"].get("dropped_tail_bytes"), int)
    assert by_role["acp_truncated_tail"]["dropped_tail_bytes"] > 0
    assert by_role["zed_render"]["disposition"] == "awaiting_human_approval"
    assert by_role["acpx_session_stream"]["disposition"] == "promoted"
    assert by_role["zed_debug_line"].get("artifact_sha256")
    assert by_role["redaction_canaries"].get("artifact_sha256")

    names = {path.name for path in output.rglob("*") if path.is_file()}
    assert "transcript.stdout" not in names
    assert "transcript.stderr" not in names

    report = runner.run_inspect(output_root=output)
    assert report["canary_hits"] == 0
    assert report["raw_transcript_present"] is False
    assert report["artifact_count"] >= 1
