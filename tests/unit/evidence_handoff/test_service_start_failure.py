"""#649: a failed ledger start reports a bounded, value-free cause that survives teardown."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

CANARY = "CANARY-CHILD-STDERR-MUST-NOT-SURFACE-4b7e"


def _start_failing_child(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.ExceptionInfo[RuntimeError]:
    from evidence_handoff_runtime import service

    real_popen = subprocess.Popen

    def _popen(argv: list[str], **kwargs: Any) -> subprocess.Popen[bytes]:
        # A real child that writes a value to stderr and exits before it binds.
        script = f"import sys; sys.stderr.write({CANARY!r} * 400); sys.exit(3)"
        return real_popen([sys.executable, "-c", script], **kwargs)

    monkeypatch.setattr(service.subprocess, "Popen", _popen)
    config = service.ServiceConfig(
        bind_host="127.0.0.1",
        bind_port=1,
        allowed_origins=("http://127.0.0.1:1",),
        request_limits={"max_body_bytes": 65536},
        protocol_versions=("2025-11-25",),
    )

    class _Bootstrap:
        control_root = tmp_path / "control"

    with pytest.raises(RuntimeError) as raised:
        service.LedgerService.start(config, object(), _Bootstrap(), allow_unauthenticated_stub=True)
    return raised


def test_start_failure_is_bounded_and_value_free(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    raised = _start_failing_child(monkeypatch, tmp_path)
    assert str(raised.value) == "service_start_failed:service_process_exited teardown=complete"
    assert CANARY not in repr(raised.value.__cause__) + repr(raised.value.__context__)
    # Resource cleanup: the runtime file and the stderr log are gone.
    assert sorted(p.name for p in (tmp_path / "control").iterdir()) == []


def test_teardown_failure_keeps_the_readiness_cause(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from evidence_handoff_runtime import service

    real_stop = service.RunningService.stop

    def _stop(self: Any) -> None:
        real_stop(self)
        raise OSError("teardown broke")

    monkeypatch.setattr(service.RunningService, "stop", _stop)
    raised = _start_failing_child(monkeypatch, tmp_path)
    assert str(raised.value) == "service_start_failed:service_process_exited teardown=incomplete"


def test_a_file_left_behind_reports_incomplete_teardown(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    real_unlink = Path.unlink

    def _unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name == "service.stderr.log":
            raise PermissionError("sharing violation")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _unlink)
    raised = _start_failing_child(monkeypatch, tmp_path)
    assert str(raised.value) == "service_start_failed:service_process_exited teardown=incomplete"
    # The other deletions were still attempted.
    assert sorted(p.name for p in (tmp_path / "control").iterdir()) == ["service.stderr.log"]
