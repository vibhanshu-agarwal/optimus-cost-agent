"""Unit tests for the P11-FU-10 external-acpx error-code evidence runner."""

from __future__ import annotations

import ast
import hashlib
import shutil
from pathlib import Path

import pytest

from tools.run_p11_fu_10_acpx_error_code_evidence import (
    AcpxEvidenceError,
    AcpxNotFoundError,
    assert_report_destination,
    assert_report_has_no_secrets,
    build_report,
    classify_probe_output,
    resolve_acpx,
)

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "tools" / "run_p11_fu_10_acpx_error_code_evidence.py"
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _imported_module_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_resolve_acpx_matches_shutil_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tools.run_p11_fu_10_acpx_error_code_evidence.shutil.which",
        lambda name: r"C:\tools\acpx.exe" if name == "acpx" else None,
    )
    monkeypatch.setattr(shutil, "which", lambda name: r"C:\tools\acpx.exe" if name == "acpx" else None)
    assert resolve_acpx() == shutil.which("acpx")


def test_script_never_imports_project_acp_protocol_client() -> None:
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    imported = _imported_module_names(ast.parse(source))
    runner_source_for_protocol_client_imports = "\n".join(sorted(imported))
    assert "optimus.acp" not in runner_source_for_protocol_client_imports
    assert all(not name.startswith("optimus.acp") for name in imported)


def test_rejects_missing_acpx_with_controlled_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tools.run_p11_fu_10_acpx_error_code_evidence.shutil.which", lambda _name: None)
    with pytest.raises(AcpxNotFoundError, match="acpx not found"):
        resolve_acpx()


def test_report_records_both_probed_codes_without_transcript_or_secret() -> None:
    report = build_report(
        acpx_path=r"C:\tools\acpx.exe",
        acpx_version="0.12.0",
        probes=(
            {"code": -32001, "exit_code": 1, "classification": "error_envelope_observed"},
            {"code": -32911, "exit_code": 1, "classification": "error_envelope_observed"},
        ),
    )
    report_text = str(report)
    assert report["probed_codes"] == [-32001, -32911]
    assert "OPTIMUS_API_KEY" not in report_text
    assert "full_transcript" not in report
    assert report["acpx_path_digest"] == hashlib.sha256(r"C:\tools\acpx.exe".encode("utf-8")).hexdigest()
    assert "reserved band" in report["unconditional_allocation_reason"]
    assert "-32911" in report["unconditional_allocation_reason"]


def test_assert_report_has_no_secrets_rejects_api_key_material() -> None:
    with pytest.raises(AcpxEvidenceError, match="secret"):
        assert_report_has_no_secrets("probe failed OPTIMUS_API_KEY=top-secret-canary")


def test_assert_report_destination_fails_closed_outside_reports(tmp_path: Path) -> None:
    with pytest.raises(AcpxEvidenceError, match="reports"):
        assert_report_destination(tmp_path / "outside.md", reports_root=_REPO_ROOT / "reports")


def test_assert_report_destination_accepts_reports_path() -> None:
    destination = _REPO_ROOT / "reports" / "plan-11-18-p11-fu-10-acpx-error-code-evidence.md"
    assert_report_destination(destination, reports_root=_REPO_ROOT / "reports")


def test_classify_probe_output_is_bounded() -> None:
    assert classify_probe_output(stdout='{"error":{"code":-32001}}', stderr="") == "error_envelope_observed"
    assert classify_probe_output(stdout="timeout waiting", stderr="") == "client_output_unclassified"
    assert classify_probe_output(stdout="", stderr="acpx: connection refused") == "client_output_unclassified"
