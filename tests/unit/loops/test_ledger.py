import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from optimus.loops.ledger import InMemoryProgressLedger, JsonlProgressLedger, ProgressLedgerEntry
from optimus.loops.models import LoopStopReason


def entry(iteration: int = 1) -> ProgressLedgerEntry:
    return ProgressLedgerEntry(
        run_id="run-1",
        session_id="session-1",
        iteration=iteration,
        goal="Migrate auth call sites",
        summary="updated one file",
        cost_credits=Decimal("0.125"),
        stop_reason=None,
        failure_signature=None,
        occurred_at=datetime(2026, 7, 6, tzinfo=UTC),
    )


def test_in_memory_progress_ledger_is_append_only():
    ledger = InMemoryProgressLedger()

    ledger.append(entry(1))
    ledger.append(entry(2))

    assert tuple(item.iteration for item in ledger.entries(run_id="run-1")) == (1, 2)
    assert ledger.entries(run_id="other") == ()


def test_jsonl_progress_ledger_writes_redacted_json_lines(tmp_path):
    path = tmp_path / "reports" / "loop-progress.jsonl"
    ledger = JsonlProgressLedger(path, workspace_root=tmp_path)

    ledger.append(entry(1))
    ledger.append(
        ProgressLedgerEntry(
            run_id="run-1",
            session_id=None,
            iteration=2,
            goal="Migrate auth call sites",
            summary=f"stopped after token=secret-token in {tmp_path / 'src' / 'optimus' / 'x.py'}",
            cost_credits=Decimal("0"),
            stop_reason=LoopStopReason.MAX_ITERATIONS,
            failure_signature="Authorization: Bearer secret-token",
            occurred_at=datetime(2026, 7, 6, tzinfo=UTC),
        )
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    decoded = [json.loads(line) for line in lines]
    assert decoded[0]["cost_credits"] == "0.125"
    assert decoded[1]["stop_reason"] == "MAX_ITERATIONS"
    assert "secret-token" not in lines[1]
    assert "<workspace>/src/optimus/x.py" in lines[1]


def test_jsonl_progress_ledger_rejects_path_outside_workspace(tmp_path):
    outside = tmp_path.parent / "outside.jsonl"

    with pytest.raises(ValueError, match="progress ledger path must stay under workspace_root"):
        JsonlProgressLedger(outside, workspace_root=tmp_path)
