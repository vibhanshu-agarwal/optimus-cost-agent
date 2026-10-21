"""Plan 12.2 Task 13 (Stage C): the custody check between client launches (Codex completion review R4).

A profiled launch starts its own Gateway, and the release ledger has one writer, so before every Zed or acpx
launch the previous host and its Gateway must be gone: nothing listens on the Gateway's URL, no Gateway holds
the ledger's lock and no Optimus host or Gateway process is left. The check also reads (never writes) the
ledger's totals and window and, against the previous check's receipt, proves the same release window and
totals that never went backwards. It starts nothing, stops nothing and calls no model.

Processes are matched by command line but reported by id and image name only: a host's command line carries
its signed launch material, so it is never printed or written.

Usage: python tools/plan12_stage_c_transition_check.py --workspace-root <ws> --out <new receipt.json>
           [--gateway-url http://127.0.0.1:8765] [--previous <earlier receipt.json>]
Exit 0 only when the transition is clear.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from optimus.acp.operator_paths import resolve_operator_paths
from optimus_model_policy import stage_c

DEFAULT_GATEWAY_URL = "http://127.0.0.1:8765"  # the local infrastructure's default Gateway URL
# Every Optimus host or Gateway process (the host module, its console script and wrapper, the Gateway
# module), except this query's own shell. The projection after ForEach-Object names id and image only.
PROCESS_QUERY = (
    "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and "
    "$_.CommandLine -match 'optimus[._-](acp|agent)|optimus_gateway' } | "
    'ForEach-Object { "$($_.ProcessId) $($_.Name)" }'
)


def ledger_for(workspace_root: Path) -> Path:
    """The workspace's release ledger, under the runtime root every launch resolves."""
    return stage_c.stage_c_ledger_path(resolve_operator_paths(workspace_root=workspace_root, environ=os.environ).runtime_root)


def parse_processes(text: str) -> list[tuple[int, str]]:
    found = []
    for line in text.splitlines():
        pid, _, name = line.strip().partition(" ")
        if pid.isdigit():
            found.append((int(pid), name))
    return found


def host_processes() -> list[tuple[int, str]] | None:
    """The Optimus host and Gateway processes left on this machine, or None where the query is unavailable."""
    if sys.platform != "win32":
        return None
    result = subprocess.run(  # noqa: S603 - a fixed query, no caller input
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", PROCESS_QUERY], capture_output=True, text=True, timeout=120, check=False
    )
    return parse_processes(result.stdout) if result.returncode == 0 else None


def gateway_listening(url: str) -> bool:
    parts = urlsplit(url)
    try:
        with socket.create_connection((parts.hostname or "127.0.0.1", parts.port or 80), timeout=2):
            return True
    except OSError:
        return False


def _state(status: stage_c.LedgerStatus, now: datetime) -> dict[str, Any]:
    s = status.state
    return {
        "attempts": s.attempts,
        "charged_usd": str(s.charged_usd),
        "outstanding_usd": str(s.outstanding_usd),
        "halted": s.halted,
        "overrun": s.overrun,
        "window_start": None if s.window_start is None else s.window_start.isoformat(),
        "deadline": None if s.deadline is None else s.deadline.isoformat(),
        "remaining_seconds": None if s.deadline is None else (s.deadline - now).total_seconds(),
    }


def check(
    *,
    workspace_root: Path,
    gateway_url: str = DEFAULT_GATEWAY_URL,
    previous: Mapping[str, Any] | None = None,
    processes: Callable[[], list[tuple[int, str]] | None] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    ledger = ledger_for(workspace_root)
    status = stage_c.stage_c_ledger_status(ledger, stage_c.compose_stage_c_envelope(ledger=ledger))
    now = clock()
    listening = gateway_listening(gateway_url)
    left = (processes or host_processes)()
    state = _state(status, now)
    problems = []
    if listening:
        problems.append(f"something still listens on {gateway_url}")
    if not status.lock_free:
        problems.append("a Gateway still holds the release ledger")
    if left is None:
        problems.append("the host and Gateway processes could not be listed")
    elif left:
        problems.append("Optimus host or Gateway processes are still running")
    if previous is not None:
        before = previous["ledger_state"]
        if before["deadline"] is not None and (state["window_start"], state["deadline"]) != (before["window_start"], before["deadline"]):
            problems.append("the release window differs from the previous check")
        if state["attempts"] < before["attempts"] or Decimal(state["charged_usd"]) < Decimal(before["charged_usd"]):
            problems.append("the ledger's totals went backwards since the previous check")
    return {
        "checked_at": now.isoformat(),
        "release_id": stage_c.STAGE_C_RELEASE_ID,
        "ledger": str(ledger),
        "gateway_url": gateway_url,
        "gateway_listening": listening,
        "ledger_lock_free": status.lock_free,
        "processes": None if left is None else [{"pid": pid, "name": name} for pid, name in left],
        "ledger_state": state,
        "previous_checked_at": None if previous is None else previous.get("checked_at"),
        "problems": problems,
        "clear": not problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    parser.add_argument("--out", type=Path, required=True, help="a new receipt file; an existing one is never overwritten")
    parser.add_argument("--previous", type=Path, default=None, help="the previous check's receipt")
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error(f"{args.out} exists; every check gets a new receipt")
    previous = json.loads(args.previous.read_text(encoding="utf-8")) if args.previous is not None else None
    receipt = check(workspace_root=args.workspace_root, gateway_url=args.gateway_url, previous=previous, processes=host_processes)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("custody clear" if receipt["clear"] else "NOT CLEAR: " + "; ".join(receipt["problems"]))
    state = receipt["ledger_state"]
    print(f"ledger: {state['attempts']} attempts, ${state['charged_usd']} charged, halted: {state['halted']}, deadline: {state['deadline']}")
    return 0 if receipt["clear"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
