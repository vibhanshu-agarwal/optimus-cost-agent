"""Plan 12.10: the measurement tool's own arithmetic and corpus count, on real files. The pilot itself needs released resources."""

from __future__ import annotations

import hashlib
import json
import subprocess
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


def test_the_k2_admin_user_leaves_the_index_user_alone_and_the_launch_path_still_accepts_the_file(tmp_path: Path) -> None:
    from optimus_security.memory_index_config import ACL_NAME, CONFIG_NAME, acl_text
    from tools.plan12_memory.m1_qualify import k2_admin_acl

    original = acl_text("optimus-index", "a" * 64)
    (tmp_path / ACL_NAME).write_bytes(original.encode("utf-8"))
    (tmp_path / CONFIG_NAME).write_text(json.dumps({"acl_sha256": "0" * 64, "port": 6393}), encoding="utf-8")
    k2_admin_acl(tmp_path, "local")
    data = (tmp_path / ACL_NAME).read_bytes()
    assert data.decode("utf-8").startswith(original) and b"user k2-admin on #" in data and b"local" not in data
    document = json.loads((tmp_path / CONFIG_NAME).read_text(encoding="utf-8"))
    assert document == {"acl_sha256": hashlib.sha256(data).hexdigest(), "port": 6393}


def test_a_bound_with_no_measurement_is_neither_met_nor_failed() -> None:
    from tools.plan12_memory.m1_qualify import within

    assert within(None, 1) is None
    assert within(2, 2) is True and within(3, 2) is False
    assert within(3, 2, at_least=True) is True


def test_the_large_corpus_must_be_at_the_approved_commit(tmp_path: Path) -> None:
    from tools.plan12_memory.m1_qualify import clone_large_corpus

    source = tmp_path / "source"
    source.mkdir()
    (source / "a.java").write_text("class A {}\n", encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "c"]):
        subprocess.run(["git", "-C", str(source), *args], capture_output=True, check=True)
    head = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    with pytest.raises(SystemExit, match="not the approved"):
        clone_large_corpus(source, tmp_path / "wrong", expected_commit="0" * 40)
    clone = clone_large_corpus(source, tmp_path / "right", expected_commit=head)
    assert "**/*Test.java" in (clone / ".optimusignore").read_text(encoding="utf-8")
