"""Plan 12.2 Task 13 (Stage C), Codex completion review R4: the custody check between client launches.

Between the Zed launches and each acpx launch the previous host and its Gateway must be gone before the
next one starts its own: nothing listens on the Gateway's URL, no Gateway holds the release ledger's lock and
no Optimus host or Gateway process is left. The check also reads (never writes) the ledger's totals and
window, and against the previous check's receipt proves the same release window and non-decreasing totals.
Temporary ledgers and a fake process list only; the receipt names processes by id and image, never by
command line.
"""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from optimus_model_policy import stage_c
from tools import plan12_stage_c_transition_check as tool

T0 = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A workspace whose release ledger is initialized and whose window opened at T0, with no Gateway left."""
    root = tmp_path / "workspace"
    ledger = tool.ledger_for(root)
    envelope = stage_c.compose_stage_c_envelope(ledger=ledger)
    stage_c.initialize_stage_c_ledger(ledger, envelope, clock=lambda: T0)
    guard = stage_c.StageCGuard.open(ledger, envelope, clock=lambda: T0)
    guard.settle_charged(guard.admit(attempt_id="gw-" + "0" * 32, request_id="r", reserve_usd=Decimal("0.05")), Decimal("0.004"))
    guard.close()
    return root


def _free_url() -> str:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def _check(workspace: Path, **kwargs):
    kwargs.setdefault("gateway_url", _free_url())
    kwargs.setdefault("processes", lambda: [])
    return tool.check(workspace_root=workspace, clock=lambda: T0 + timedelta(minutes=10), **kwargs)


def test_the_ledger_is_the_workspaces_release_ledger(tmp_path: Path) -> None:
    assert tool.ledger_for(tmp_path) == stage_c.stage_c_ledger_path(tmp_path.resolve() / ".optimus")


def test_a_clear_transition_reports_the_ledgers_totals_and_window(workspace: Path) -> None:
    receipt = _check(workspace)

    assert receipt["clear"] is True and receipt["problems"] == []
    assert (receipt["gateway_listening"], receipt["ledger_lock_free"], receipt["processes"]) == (False, True, [])
    state = receipt["ledger_state"]
    assert (state["attempts"], state["charged_usd"], state["outstanding_usd"], state["halted"]) == (1, "0.004", "0", None)
    assert (state["deadline"], state["remaining_seconds"]) == ((T0 + timedelta(hours=1)).isoformat(), 3000.0)


def test_a_held_ledger_is_not_a_clear_transition(workspace: Path) -> None:
    ledger = tool.ledger_for(workspace)
    guard = stage_c.StageCGuard.open(ledger, stage_c.compose_stage_c_envelope(ledger=ledger), clock=lambda: T0)
    try:
        receipt = _check(workspace)
    finally:
        guard.close()
    assert receipt["clear"] is False and receipt["ledger_lock_free"] is False
    assert "a Gateway still holds the release ledger" in receipt["problems"]


def test_a_listening_gateway_url_is_not_a_clear_transition(workspace: Path) -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        receipt = _check(workspace, gateway_url=f"http://127.0.0.1:{server.getsockname()[1]}")
    assert receipt["clear"] is False and receipt["gateway_listening"] is True
    assert any(problem.startswith("something still listens on") for problem in receipt["problems"])


def test_a_remaining_host_or_gateway_process_is_not_a_clear_transition(workspace: Path) -> None:
    receipt = _check(workspace, processes=lambda: [(4242, "python.exe")])
    assert receipt["clear"] is False and receipt["processes"] == [{"pid": 4242, "name": "python.exe"}]


def test_the_process_query_reports_ids_and_images_only() -> None:
    projection = tool.PROCESS_QUERY.split("ForEach-Object", 1)[1]
    assert "ProcessId" in projection and "Name" in projection and "CommandLine" not in projection
    assert tool.parse_processes("4242 python.exe\r\n77 node.exe\r\n\r\n") == [(4242, "python.exe"), (77, "node.exe")]


def test_the_previous_receipt_proves_the_same_window_and_non_decreasing_totals(workspace: Path) -> None:
    first = _check(workspace)
    assert _check(workspace, previous=first)["clear"] is True

    moved = {**first, "ledger_state": {**first["ledger_state"], "deadline": (T0 + timedelta(hours=2)).isoformat()}}
    assert "the release window differs from the previous check" in _check(workspace, previous=moved)["problems"]
    ahead = {**first, "ledger_state": {**first["ledger_state"], "attempts": 5}}
    assert "the ledger's totals went backwards since the previous check" in _check(workspace, previous=ahead)["problems"]


def test_main_writes_a_new_receipt_and_exits_by_the_result(workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool, "host_processes", lambda: [])
    out = tmp_path / "evidence" / "check-1.json"
    url = _free_url()

    assert tool.main(["--workspace-root", str(workspace), "--gateway-url", url, "--out", str(out)]) == 0
    first = json.loads(out.read_text(encoding="utf-8"))
    assert first["clear"] is True
    with pytest.raises(SystemExit):
        tool.main(["--workspace-root", str(workspace), "--gateway-url", url, "--out", str(out)])  # never overwritten
    second = tmp_path / "evidence" / "check-2.json"
    monkeypatch.setattr(tool, "host_processes", lambda: [(1, "optimus-agent.exe")])
    assert tool.main(["--workspace-root", str(workspace), "--gateway-url", url, "--out", str(second), "--previous", str(out)]) == 1
