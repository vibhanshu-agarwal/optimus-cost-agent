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


def test_survival_is_by_identity_and_payload_not_by_count() -> None:
    from tools.plan12_memory.m1_qualify import compare_acknowledged

    assert compare_acknowledged({"a": "1", "b": "2"}, {"a": "1", "b": "2", "c": "3"}) == {"acknowledged": 2, "missing": 0, "conflicting": 0}
    assert compare_acknowledged({"a": "1", "b": "2"}, {"a": "9", "c": "3"}) == {"acknowledged": 2, "missing": 1, "conflicting": 1}  # same count as stored would hide this


def test_every_canary_request_passes_the_routes_own_contract() -> None:
    from optimus_security import memory_index_contract as mic
    from tools.plan12_memory.m1_qualify import _ANY_REVISION, _ONE_FILE, _record, owner_id

    scope = "0" * 64
    owner = owner_id("k2owner0")
    name = "canaryabcdx1"
    for body in (
        {"op": "generation", "action": "open", "embedding": "e", "dimensions": 4, "schema_version": 1},
        {"op": "lease", "action": "acquire", "owner": owner, "ttl_ms": 60000, "kind": "scope"},
        {"op": "lease", "action": "renew", "owner": owner, "ttl_ms": 60000, "kind": "scope", "token": 1},
        {"op": "generation", "action": "begin", "token": 1},
        {"op": "batch", "token": 1, "epoch": 1, "records": [_record(name, 4)]},
        {"op": "generation", "action": "publish", "token": 1, "epoch": 1, "revision": _ANY_REVISION, "dirty": False, "coverage": _ONE_FILE},
        {"op": "query", "mode": "lexical", "terms": [name], "k": 1},
        {"op": "cleanup", "action": "drop", "token": 1},
        {"op": "lease", "action": "release", "owner": owner, "kind": "scope", "token": 1},
    ):
        mic.parse_request(json.dumps({"scope": scope, **body}).encode("utf-8"))


def test_a_failed_resource_sample_makes_the_bound_unknown_unless_the_outage_was_planned() -> None:
    from tools.plan12_memory.m1_qualify import _Peaks

    peaks = _Peaks("none", lambda: None)  # type: ignore[arg-type, return-value]
    peaks._bump("disk_mb", 10.0)
    assert peaks.bound("index", "disk_mb", 20) is True
    peaks.in_outage = True
    peaks._bump("disk_mb", None)
    assert peaks.bound("index", "disk_mb", 20) is True
    peaks.in_outage = False
    peaks._bump("disk_mb", None)
    assert peaks.bound("index", "disk_mb", 20) is None
    assert peaks.bound("k2", "disk_mb", 20) is None  # nothing seen is not a pass


def test_the_edit_lands_on_a_file_the_index_admits(tmp_path: Path) -> None:
    body = "class A {\n" + "    int field;\n" * 200 + "}\n"
    for name in ("a/src/test/java/ATest.java", "b/src/main/java/B.java"):
        path = tmp_path / name
        path.parent.mkdir(parents=True)
        path.write_bytes(body.encode())
    (tmp_path / ".optimusignore").write_bytes(b"**/test/\n")
    assert m1_scale.edit_target(tmp_path, ".java").name == "B.java"  # the sorted-first file is ignored, which measured nothing on 2026-11-06
    (tmp_path / ".optimusignore").write_bytes(b"**/test/\n**/main/\n")
    with pytest.raises(SystemExit, match="no indexed"):
        m1_scale.edit_target(tmp_path, ".java")


def test_an_edit_counts_as_visible_when_it_can_be_queried_not_when_its_pass_ends() -> None:
    published, release = threading.Event(), threading.Event()

    def run(_cancel: threading.Event) -> object:
        published.set()  # the early publication; the pass then keeps reconciling until the query has answered
        release.wait(5)
        return type("Outcome", (), {"state": "complete", "records_written": 3})()

    def found() -> bool:
        if published.is_set():
            release.set()
            return True
        return False

    result = m1_scale.edit_visibility(run, found, poll_seconds=0.01)
    assert result["new_symbol_found"] and result["state"] == "complete" and result["records_written"] == 3
    assert result["queryable_before_the_pass_ended"] is True  # run-then-query would answer only after the pass, and say False
    assert result["seconds_until_queryable"] <= result["whole_pass_seconds"]
    never = m1_scale.edit_visibility(lambda _cancel: type("Outcome", (), {"state": "complete", "records_written": 0})(), lambda: False, poll_seconds=0.01)
    assert never["new_symbol_found"] is False and never["seconds_until_queryable"] is None


def test_an_edit_measurement_past_its_deadline_or_a_failed_query_stops_its_worker() -> None:
    stopped: list[bool] = []

    def endless(cancel: threading.Event) -> object:
        while not cancel.wait(0.01):
            pass
        stopped.append(True)
        return type("Outcome", (), {"state": "cancelled", "records_written": 0})()

    late = m1_scale.edit_visibility(endless, lambda: False, limit_seconds=0.2, poll_seconds=0.01)
    assert stopped == [True] and late["state"] == "cancelled" and late["new_symbol_found"] is False

    def broken() -> bool:
        raise ConnectionError("route gone")

    failed = m1_scale.edit_visibility(endless, broken, poll_seconds=0.01)
    assert stopped == [True, True] and failed["query_error"] == "ConnectionError"
    crashed = m1_scale.edit_visibility(lambda _cancel: 1 / 0, lambda: False, poll_seconds=0.01)
    assert crashed["worker_failure"] == "ZeroDivisionError"


def test_a_session_edit_is_timed_from_the_wake_to_the_symbol_in_that_file(tmp_path: Path) -> None:
    from tools.plan12_memory.m1_qualify import session_edit_visibility

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "A.java").write_bytes(("class A {\n" + "    int field;\n" * 200 + "}\n").encode())

    class Session:
        _last_outcome: object = None

        def request_pass(self) -> None:
            threading.Timer(0.05, lambda: setattr(self, "_last_outcome", type("Outcome", (), {"state": "complete"})())).start()

    class Storage:
        def __init__(self, session: Session) -> None:
            self.session = session

        def call(self, op: str, **fields: object) -> dict:
            text = (tmp_path / "src" / "A.java").read_text(encoding="utf-8")
            hit = self.session._last_outcome is not None and "m1SessionAddedMethod" in text
            return {"records": [{"path": "elsewhere/B.java"}] + ([{"path": "src/A.java"}] if hit else [])}

    session = Session()
    result = session_edit_visibility(session, tmp_path, Storage(session), poll_seconds=0.01)  # type: ignore[arg-type]
    assert result["new_symbol_found"] and result["pass_state"] == "complete" and result["seconds_until_queryable"] <= result["whole_pass_seconds"]


def test_assembly_without_the_dense_channel_is_flagged_as_not_what_a_person_gets() -> None:
    from tools.plan12_memory.m1_qualify import _dense_in_every_turn

    assert _dense_in_every_turn([{"task": "a", "channels": {"dense": "40 results", "lexical": "40 results"}}]) == {"dense_in_every_turn": True}
    assert _dense_in_every_turn([{"task": "a", "channels": {"dense": "no embedding artifact", "lexical": "40 results"}}]) == {
        "dense_in_every_turn": False, "turns_without_dense": ["a"], "channels_that_did_not_answer": ["dense: no embedding artifact"]}
    refused = _dense_in_every_turn([{"task": "b", "channels": {"dense": "refused:INDEX_BUSY", "lexical": "unavailable"}}])
    assert refused["dense_in_every_turn"] is False  # it was asked, and retrieval still said ok
    assert refused["channels_that_did_not_answer"] == ["dense: refused:INDEX_BUSY", "lexical: unavailable"]


def test_logical_purge_is_timed_at_the_first_refusal_not_the_whole_sweep() -> None:
    from context_engine.index_worker import StorageRefusedError
    from tools.plan12_memory.m1_qualify import drop_and_time

    class Storage:
        steps = 0

        def call(self, op: str, **body: object) -> dict:
            if op == "cleanup":
                self.steps += 1
                return {"cursor": "next" if self.steps < 3 else None}
            if self.steps:
                raise StorageRefusedError("SCOPE_UNKNOWN")
            return {"records": [{"id": "marker"}]}

    times = iter([0.0, 0.2, 5.0])
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("tools.plan12_memory.m1_qualify.time.monotonic", lambda: next(times))
        result = drop_and_time(Storage(), 1, "marker")
    assert result["logical_purge_seconds"] == 0.2
    assert result["whole_drop_seconds"] == 5.0
    assert result["route_denies_after_drop"] is True
    assert result["answer_after_first_step"] == "SCOPE_UNKNOWN"

