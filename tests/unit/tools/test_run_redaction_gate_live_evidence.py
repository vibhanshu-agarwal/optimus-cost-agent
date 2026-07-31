"""RED/GREEN unit tests for the redaction-gate live evidence runner."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = REPO_ROOT / "tools" / "run_redaction_gate_live_evidence.py"


def _load_runner():
    if not RUNNER_PATH.is_file():
        raise ImportError("run_redaction_gate_live_evidence missing")
    spec = importlib.util.spec_from_file_location("run_redaction_gate_live_evidence", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runner_module_exists() -> None:
    assert RUNNER_PATH.is_file()


def test_requires_explicit_absolute_roots(tmp_path: Path) -> None:
    runner = _load_runner()
    capture = (tmp_path / "cap").resolve()
    staging = (tmp_path / "stg").resolve()
    quarantine = (tmp_path / "q").resolve()
    output = (tmp_path / "out").resolve()
    for path in (capture, staging, quarantine, output):
        path.mkdir()
    roots = runner.validate_evidence_roots(
        capture_root=capture,
        staging_root=staging,
        quarantine_root=quarantine,
        output_root=output,
        forbidden_persistence_roots=(),
    )
    assert roots.capture_root == capture
    with pytest.raises(runner.LiveEvidenceError, match="relative_root_rejected"):
        runner.validate_evidence_roots(
            capture_root=Path("relative-cap"),
            staging_root=staging,
            quarantine_root=quarantine,
            output_root=output,
            forbidden_persistence_roots=(),
        )


def test_rejects_overlapping_roots(tmp_path: Path) -> None:
    runner = _load_runner()
    base = (tmp_path / "base").resolve()
    base.mkdir()
    nested = (base / "nested").resolve()
    nested.mkdir()
    other = (tmp_path / "other").resolve()
    other.mkdir()
    out = (tmp_path / "out").resolve()
    out.mkdir()
    with pytest.raises(runner.LiveEvidenceError, match="root_overlap"):
        runner.validate_evidence_roots(
            capture_root=base,
            staging_root=nested,
            quarantine_root=other,
            output_root=out,
            forbidden_persistence_roots=(),
        )


def test_rejects_cloud_sync_path_segment(tmp_path: Path) -> None:
    runner = _load_runner()
    capture = (tmp_path / "OneDrive" / "cap").resolve()
    staging = (tmp_path / "stg").resolve()
    quarantine = (tmp_path / "q").resolve()
    output = (tmp_path / "out").resolve()
    capture.mkdir(parents=True)
    for path in (staging, quarantine, output):
        path.mkdir()
    with pytest.raises(runner.LiveEvidenceError, match="cloud_sync_path_segment"):
        runner.validate_evidence_roots(
            capture_root=capture,
            staging_root=staging,
            quarantine_root=quarantine,
            output_root=output,
            forbidden_persistence_roots=(),
        )


def test_rejects_forbidden_persistence_containment(tmp_path: Path) -> None:
    runner = _load_runner()
    forbidden = (tmp_path / "cloud-sync").resolve()
    capture = (forbidden / "cap").resolve()
    staging = (tmp_path / "stg").resolve()
    quarantine = (tmp_path / "q").resolve()
    output = (tmp_path / "out").resolve()
    capture.mkdir(parents=True)
    for path in (staging, quarantine, output):
        path.mkdir()
    with pytest.raises(runner.LiveEvidenceError, match="path_under_forbidden_root"):
        runner.validate_evidence_roots(
            capture_root=capture,
            staging_root=staging,
            quarantine_root=quarantine,
            output_root=output,
            forbidden_persistence_roots=(forbidden,),
        )


def test_no_default_output_path_in_cli() -> None:
    runner = _load_runner()
    parser = runner.build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["verify"])
    # All four roots required for verify.
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "verify",
                "--capture-root",
                "C:/a",
                "--staging-root",
                "C:/b",
                "--quarantine-root",
                "C:/c",
            ]
        )


def test_acpx_resolution_records_version(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_runner()

    def _which(name: str) -> str | None:
        return r"C:\tools\acpx.exe" if name == "acpx" else None

    def _run(cmd: list[str], **kwargs: object):  # noqa: ANN001
        class _Completed:
            returncode = 0
            stdout = "acpx 0.1.0-test\n"
            stderr = ""

        assert cmd[0].endswith("acpx.exe")
        assert "--version" in cmd
        assert kwargs.get("shell") is False
        return _Completed()

    monkeypatch.setattr(runner.shutil, "which", _which)
    monkeypatch.setattr(runner.subprocess, "run", _run)
    path, version = runner.resolve_acpx()
    assert path.endswith("acpx.exe")
    assert "0.1.0-test" in version


def test_spawn_uses_shell_false(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = _load_runner()
    seen: dict[str, object] = {}

    class _Proc:
        def __init__(self) -> None:
            self.stdout = None
            self.stderr = None
            self.pid = 4242

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def _popen(cmd: list[str], **kwargs: object):  # noqa: ANN001
        seen["cmd"] = cmd
        seen["shell"] = kwargs.get("shell")
        seen["env"] = kwargs.get("env")
        return _Proc()

    monkeypatch.setattr(runner.subprocess, "Popen", _popen)
    proc = runner.spawn_agent_process(
        command=[sys.executable, "-c", "print('ok')"],
        cwd=tmp_path,
        env={"PATH": "x"},
    )
    assert seen["shell"] is False
    assert "evidence_capture_root" not in (seen["env"] or {})
    assert proc.pid == 4242


def test_screenshot_approval_file_required(tmp_path: Path) -> None:
    runner = _load_runner()
    with pytest.raises(runner.LiveEvidenceError, match="screenshot_approval_required"):
        runner.load_screenshot_approval(tmp_path / "missing-approval.json")
