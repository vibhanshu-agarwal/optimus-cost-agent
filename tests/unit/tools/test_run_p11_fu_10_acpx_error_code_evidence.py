"""Unit tests for the P11-FU-10 external-acpx error-code evidence runner."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.support.concurrency import DescendantRecorder, assert_descendants_killed
from tests.support.fault_injection import descendant_tree
from tools import run_p11_fu_9_acpx_evidence as fu9
from tools import run_p11_fu_10_acpx_error_code_evidence as fu10
from tools.run_p11_fu_10_acpx_error_code_evidence import (
    AcpxEvidenceError,
    AcpxNotFoundError,
    _run_acpx,
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
    monkeypatch.setattr(shutil, "which", lambda name: r"C:\tools\acpx.exe" if name == "acpx" else None)
    assert resolve_acpx() == r"C:\tools\acpx.exe"


def test_script_never_imports_project_acp_protocol_client() -> None:
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    imported = _imported_module_names(ast.parse(source))
    runner_source_for_protocol_client_imports = "\n".join(sorted(imported))
    assert "optimus.acp" not in runner_source_for_protocol_client_imports
    assert all(not name.startswith("optimus.acp") for name in imported)


def test_rejects_missing_acpx_with_controlled_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(AcpxNotFoundError, match="acpx not found"):
        resolve_acpx()


@pytest.mark.parametrize("runner", [fu9, fu10], ids=["fu9", "fu10"])
def test_lookup_preserves_runner_error_and_install_guidance(
    runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(runner.AcpxNotFoundError) as error:
        runner.resolve_acpx()
    assert type(error.value) is runner.AcpxNotFoundError
    assert str(error.value) == (
        "acpx not found on PATH. Install the independent acpx ACP client "
        "(https://github.com/openclaw/acpx); never substitute a project client."
    )


@pytest.mark.parametrize("runner", [fu9, fu10], ids=["fu9", "fu10"])
@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr", "expected", "error_message"),
    [
        (0, " 0.12.0\n", "ignored", "0.12.0", None),
        (0, "", " 0.12.0\n", "0.12.0", None),
        (0, " \n", "0.12.0", None, "acpx --version returned empty output"),
        (0, "", "", None, "acpx --version returned empty output"),
        (1, "0.12.0", "", None, "acpx --version failed"),
    ],
)
def test_version_preserves_subprocess_contract(
    runner,
    returncode: int,
    stdout: str,
    stderr: str,
    expected: str | None,
    error_message: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(argv, **kwargs):
        assert argv == ["synthetic-acpx", "--version"]
        assert kwargs == dict(capture_output=True, text=True, check=False, shell=False, timeout=30)
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)
    if error_message is None:
        assert runner.acpx_version("synthetic-acpx") == expected
    else:
        with pytest.raises(runner.AcpxEvidenceError) as error:
            runner.acpx_version("synthetic-acpx")
        assert type(error.value) is runner.AcpxEvidenceError
        assert str(error.value) == error_message


@pytest.mark.parametrize("runner", [fu9, fu10], ids=["fu9", "fu10"])
def test_version_propagates_timeout(runner, monkeypatch: pytest.MonkeyPatch) -> None:
    timeout = subprocess.TimeoutExpired(["synthetic-acpx", "--version"], timeout=30)

    def fake_run(*args, **kwargs):
        raise timeout

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(subprocess.TimeoutExpired) as error:
        runner.acpx_version("synthetic-acpx")
    assert error.value is timeout


def test_both_runners_use_shared_lookup_and_version(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = "tools.acpx_runner_cli"
    assert importlib.util.find_spec(module_name) is not None, "shared acpx runner CLI helper is missing"
    shared = importlib.import_module(module_name)

    def lookup(error_type):
        return error_type.__module__

    def version(acpx, error_type):
        return f"{acpx}:{error_type.__module__}"

    monkeypatch.setattr(shared, "resolve_acpx", lookup)
    monkeypatch.setattr(shared, "acpx_version", version)
    for runner in (fu9, fu10):
        assert runner.resolve_acpx() == runner.__name__
        assert runner.acpx_version("synthetic-acpx") == f"synthetic-acpx:{runner.__name__}"


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


@pytest.mark.parametrize("shape", ["parent-alive", "middle-exited"])
def test_acpx_timeout_kills_every_descendant(tmp_path: Path, shape: str) -> None:
    """In "middle-exited" no walk of parent pids from the acpx stand-in reaches the grandchild."""
    pids = tmp_path / "pids"
    pids.mkdir()
    code, roles = descendant_tree(pids, shape)
    timeout = 5.0
    with DescendantRecorder(pids, roles) as recorder:
        started = time.monotonic()
        with pytest.raises(AcpxEvidenceError, match="timed out"):
            _run_acpx([sys.executable, "-c", code], cwd=tmp_path, env=dict(os.environ), timeout=timeout)
        assert_descendants_killed(recorder, roles, deadline=started + timeout + 10.0, what=f"acpx timeout ({shape})")
