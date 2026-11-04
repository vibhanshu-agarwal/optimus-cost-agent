"""Plan 12.10: the measurement tool's own arithmetic and corpus count, on real files. The pilot itself needs released resources."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

pytest.importorskip("psutil")
pytest.importorskip("tree_sitter")

from tools.plan12_memory import m1_scale  # noqa: E402


def test_percentiles_are_nearest_rank() -> None:
    assert m1_scale._percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.0
    assert m1_scale._percentile([float(n) for n in range(1, 101)], 0.95) == 95.0
    assert m1_scale._percentile([], 0.5) is None


def test_the_corpus_count_is_per_language_with_exclusions(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("def hidden(): pass\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("def one():\n    return 1\n\n", encoding="utf-8")
    (tmp_path / "B.java").write_text("class B {\n  int two() { return 2; }\n}\n", encoding="utf-8")
    (tmp_path / "c.kt").write_text('fun main() { println("x") }\n', encoding="utf-8")
    counted = m1_scale.count_corpus(tmp_path)
    assert counted["parsed_lines"]["python"] == 2 and counted["parsed_lines"]["java"] == 3
    assert counted["files"]["unsupported"] == 2  # the Kotlin file and the ignore file: listed, no parsed lines
    assert counted["parsed_lines"]["unsupported"] == 0
    assert sum(counted["excluded"].values()) == 1
    assert counted["embedded_chunks"] == 3


def test_a_worker_that_did_not_finish_is_not_a_measurement() -> None:
    class Outcome:
        state, detail, files_written, records_written = "held", "LEASE_LOST", 1, 2

    with pytest.raises(SystemExit, match="LEASE_LOST"):
        m1_scale._required(Outcome())


def test_only_the_exact_agent_counts_as_this_runs_own(tmp_path: Path) -> None:
    agent = str(tmp_path / "run-a.cmd")
    assert m1_scale.runs_agent(["cmd.exe", "/d", "/s", "/c", agent], agent)
    assert m1_scale.runs_agent(["cmd.exe", "/c", f"'{agent}'"], agent)
    assert m1_scale.runs_agent(["cmd.exe", "/c", f'"{agent.upper()}"'], agent)
    assert not m1_scale.runs_agent(["cmd.exe", "/c", agent + ".backup.cmd"], agent)
    assert not m1_scale.runs_agent(["cmd.exe", "/c", str(tmp_path / "other" / "run-a.cmd")], agent)


def test_assembly_counts_only_the_turns_own_calls_and_summarises_them():
    class Inner:
        def call(self, op, **fields):
            return {"op": op}

    counting = m1_scale._CountingStorage(Inner(), threading.get_ident())
    counting.call("query", mode="dense")
    counting.call("coverage")
    worker = threading.Thread(target=counting.call, args=("batch",))
    worker.start()
    worker.join()
    assert counting.calls == {"query:dense": 1, "coverage": 1}
    turns = [{"wall_ms": 10.0, "route_ms": 4.0, "route_calls": 3, "pack_tokens": 50, "budget_tokens": 100, "state": "ok", "blocked": None},
             {"wall_ms": 20.0, "route_ms": 6.0, "route_calls": 9, "pack_tokens": None, "budget_tokens": None, "state": "unavailable", "blocked": "X"}]
    summary = m1_scale._assembly_summary(turns)
    assert summary["route_calls_max"] == 9 and summary["pack_share_of_token_budget_max"] == 0.5 and summary["states"] == ["ok", "unavailable"] and summary["blocked"] == ["X"]
