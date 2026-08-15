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
    write_markdown_report,
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


def test_main_prints_controlled_stderr_when_acpx_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools.run_p11_fu_10_acpx_error_code_evidence import AcpxNotFoundError, main

    monkeypatch.setattr(
        "tools.run_p11_fu_10_acpx_error_code_evidence.run_capture",
        lambda **_kwargs: (_ for _ in ()).throw(AcpxNotFoundError("acpx not found on PATH")),
    )
    code = main(["--report", str(tmp_path / "reports" / "out.md")])
    assert code == 2
    err = capsys.readouterr().err
    assert "acpx not found" in err
    assert "sk-" not in err


def test_write_markdown_report_omits_transcript_and_secrets(tmp_path: Path) -> None:
    report = build_report(
        acpx_path=r"C:\tools\acpx.exe",
        acpx_version="0.12.0",
        probes=(
            {"code": -32001, "exit_code": 1, "classification": "error_envelope_observed"},
            {"code": -32911, "exit_code": 1, "classification": "error_envelope_observed"},
        ),
    )
    path = tmp_path / "evidence.md"
    write_markdown_report(path, report)
    body = path.read_text(encoding="utf-8")
    assert "full_transcript" not in body
    assert "OPTIMUS_API_KEY" not in body
    assert "-32911" in body


def test_write_probe_agent_is_temporary_fixture_without_optimus_imports(tmp_path: Path) -> None:
    from tools.run_p11_fu_10_acpx_error_code_evidence import _write_probe_agent

    probe_path = _write_probe_agent(tmp_path)
    source = probe_path.read_text(encoding="utf-8")
    assert "optimus.acp" not in source
    assert "P11_FU_10_PROBE_CODE" in source


def test_run_capture_writes_schema_limited_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tools.run_p11_fu_10_acpx_error_code_evidence import run_capture

    reports = tmp_path / "reports"
    reports.mkdir()
    destination = reports / "out.md"
    monkeypatch.setattr(
        "tools.run_p11_fu_10_acpx_error_code_evidence.resolve_acpx",
        lambda: r"C:\tools\acpx.exe",
    )
    monkeypatch.setattr(
        "tools.run_p11_fu_10_acpx_error_code_evidence.acpx_version",
        lambda _acpx: "0.12.0",
    )

    def fake_run(command, *, cwd, env, timeout):  # type: ignore[no-untyped-def]
        code = env["P11_FU_10_PROBE_CODE"]
        return 1, f'{{"error":{{"code":{code}}}}}', ""

    monkeypatch.setattr("tools.run_p11_fu_10_acpx_error_code_evidence._run_acpx", fake_run)
    report = run_capture(report_path=destination, reports_root=reports)
    body = destination.read_text(encoding="utf-8")
    assert report["probed_codes"] == [-32001, -32911]
    assert "full_transcript" not in body
    assert "OPTIMUS_API_KEY" not in body
