"""Plan 12.11 Task 5 qualification driver: the parts that run without the released store (the translation from what a run
observed to the grader's trace, and what a zero-paid run may decide)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.plan12_memory import m3_evaluate as m3
from tools.plan12_memory.evaluate import grade_trace

FIXTURES = (Path("tests/fixtures/plan12_memory/lifecycle.json"), Path("tests/fixtures/plan12_memory/lifecycle-d10.json"))
CONFIG = Path("reports/plan12-memory-m3/run-config.json")
ITEM = "m-" + "a" * 16


def _cases() -> dict[str, m3.GoldenCase]:
    found: dict[str, m3.GoldenCase] = {}
    for fixture in FIXTURES:
        found.update(m3.load_cases(fixture))
    return found


def _row(version: int, action: str, status: str, trust: str = "user-authored", kind: str = "preference") -> SimpleNamespace:
    return SimpleNamespace(version=version, action=action, status=status, trust=trust, kind=kind)


def _entry(version: int, action: str, status: str, trust: str = "user-authored", kind: str = "preference") -> dict[str, object]:
    return {"version": version, "action": action, "status": status, "trust": trust, "kind": kind}


def test_without_the_release_nothing_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("P1211_MEMORY_DOCKER_RELEASED", raising=False)
    monkeypatch.setattr(m3, "Store", lambda *_a: pytest.fail("the store was provisioned without the release"))
    with pytest.raises(SystemExit, match="^UNRUN"):
        m3.main(["--config", str(CONFIG), "--output", "unused"])


@pytest.mark.parametrize(("versions", "expected"), [
    ([_entry(1, "admit", "active"), _entry(2, "update", "active")], ["superseded", "active"]),
    ([_entry(1, "admit", "active"), _entry(2, "withdraw", "withdrawn")], ["withdrawn", "withdrawn"]),
    ([_entry(1, "admit", "active"), _entry(2, "update", "active"), _entry(3, "withdraw", "withdrawn")],
     ["superseded", "withdrawn", "withdrawn"]),
    ([_entry(1, "admit", "active"), _entry(2, "withdraw", "withdrawn"), _entry(3, "tombstone", "purged")], ["purged"] * 3),
    ([_entry(1, "off", "active", "off"), _entry(2, "off", "superseded", "off")], ["superseded", "superseded"]),  # overflow archive
    ([_entry(1, "tombstone", "purged")], ["purged"]),  # a restore that applied a recorded purge
])
def test_a_status_change_reaches_the_content_versions_before_it(versions: list[dict[str, object]], expected: list[str]) -> None:
    assert m3.version_statuses(versions) == expected


def test_the_trace_names_only_what_the_run_observed_under_the_declared_keys() -> None:
    case = _cases()["M03-b-D10"]  # remember, then forget: v1 withdrawn
    run = m3.Run()
    for kind, item, version in [("store.admit", ITEM, 1), ("commit.admit", ITEM, 1), ("card.Remembered", ITEM, 1),
                                ("store.withdraw", ITEM, 2), ("store.admit", "m-" + "b" * 16, 1), ("store.mystery", ITEM, 3),
                                ("checkpoint", None, None)]:
        run.add(kind, item, version)
    history = {ITEM: [_entry(1, "admit", "active"), _entry(2, "withdraw", "withdrawn")]}
    trace = m3.to_trace(case, run, {"pref-indent": ITEM}, {ITEM: _row(2, "withdraw", "withdrawn")}, source_id="git:x",
                        config_id="c", history=history)
    assert [(e.type, e.memory_key, e.version) for e in trace.events] == [
        ("memory.committed", "pref-indent", 1), ("memory.notice.remembered", "pref-indent", 1), ("memory.withdrawn", "pref-indent", 2),
        ("checkpoint.written", None, None)]  # a store append is no commit; an undeclared item has no key; an unknown kind is dropped
    assert [(s.version, s.status) for s in trace.memory_state] == [(1, "withdrawn"), (2, "withdrawn")]
    assert trace.coverage_complete and grade_trace(case, trace).layers["authority"].status == "PASS"
    # the same run without the Gateway's confirmed commit result: the notice has no durable commit before it
    run.observations = [o for o in run.observations if o.kind != "commit.admit"]
    unconfirmed = m3.to_trace(case, run, {"pref-indent": ITEM}, {ITEM: _row(2, "withdraw", "withdrawn")}, source_id="git:x",
                              config_id="c", history=history)
    assert grade_trace(case, unconfirmed).layers["authority"].status == "FAIL"


def test_a_needed_event_the_harness_cannot_observe_is_missing_coverage() -> None:
    case = _cases()["M20-a"]  # decay: strength_faded is the product's (#235 M6) to show
    trace = m3.to_trace(case, m3.Run(), {}, {}, source_id="git:x", config_id="c")
    assert not trace.coverage_complete and trace.missing_coverage == ("memory.strength_faded:pref-indent",)


def test_every_event_an_in_scope_case_needs_is_observable_or_owned_elsewhere() -> None:
    cases, config = _cases(), json.loads(CONFIG.read_text(encoding="utf-8"))["cases"]
    needed = {name.split(":")[0] for case_id in config for name in (*cases[case_id].required_events, *cases[case_id].prohibited_events)}
    assert needed - m3.OBSERVABLE - set(m3.UNRUN_EVENTS) == set()


def test_a_zero_paid_run_never_passes_a_case_and_names_who_decides_the_rest() -> None:
    cases = _cases()
    passing = grade_trace(cases["M03-b-D10"], m3.to_trace(cases["M03-b-D10"], m3.Run(), {}, {}, source_id="git:x", config_id="c"))
    view = m3.qualification_view(cases["M03-b-D10"], passing, [])
    assert view["layers"]["answer"] == "UNRUN" and view["status"] in ("INCONCLUSIVE", "FAIL") and "retrieval" not in view["owners"]
    evidence = cases["M06-b"]  # requires a retrieved README: the stand-in runs no tools
    view = m3.qualification_view(evidence, grade_trace(evidence, m3.to_trace(evidence, m3.Run(), {}, {}, source_id="g", config_id="c")), [])
    assert view["layers"]["retrieval"] == "UNRUN" and view["owners"]["retrieval"] == m3.PAID and view["status"] == "INCONCLUSIVE"
    decay = cases["M20-a"]
    view = m3.qualification_view(decay, grade_trace(decay, m3.to_trace(decay, m3.Run(), {}, {}, source_id="g", config_id="c")),
                                 ["#235 M6 (decay)"])
    assert view["status"] == "UNRUN" and view["owners"]["case"] == "#235 M6 (decay)"


def test_a_failed_decided_layer_stays_failed() -> None:
    case = _cases()["M03-b-D10"]
    run = m3.Run()
    run.add("card.Remembered", ITEM, 1)  # a notice with no commit before it
    verdict = grade_trace(case, m3.to_trace(case, run, {"pref-indent": ITEM}, {}, source_id="g", config_id="c"))
    assert m3.qualification_view(case, verdict, [])["status"] == "FAIL"


def test_a_command_names_the_item_and_version_the_user_would_read() -> None:
    store = SimpleNamespace(read=lambda item: SimpleNamespace(event=SimpleNamespace(version=3)) if item == ITEM else None)
    rig = SimpleNamespace(items={"pref-indent": ITEM}, host=SimpleNamespace(extractor=SimpleNamespace(store=store)))
    assert m3._resolve("/forget {pref-indent@v} --purge", rig) == f"/forget {ITEM}@3 --purge"
    assert m3._resolve("/memory view {pref-indent}", rig) == f"/memory view {ITEM}"


@pytest.mark.parametrize(("action", "status"), [("tombstone", "purged"), ("withdraw", "withdrawn")])
def test_a_restored_deletion_reaches_every_version_below_its_one_entry(action: str, status: str) -> None:
    case = _cases()["M21-a-D10"]
    trace = m3.to_trace(case, m3.Run(), {"pref-old": ITEM}, {ITEM: _row(3, action, status)}, source_id="g", config_id="c",
                        history={ITEM: [_entry(3, action, status)]})
    assert [(s.version, s.status) for s in trace.memory_state] == [(1, status), (2, status), (3, status)]


def test_only_a_commit_result_the_gateway_gave_as_durable_counts_as_a_commit(tmp_path: Path) -> None:
    replies = iter([(200, {"item": ITEM, "version": 1, "durable_state": "confirmed"}),
                    (200, {"item": "m-" + "b" * 16, "version": 1, "durable_state": "unconfirmed"})])
    rig = SimpleNamespace(store=SimpleNamespace(service=SimpleNamespace(handle=lambda _body, deadline: next(replies))), confirmed=set())
    send = m3.Rig.post(rig, None, timeout=1.0, path="/memory")
    send(b"{}"), send(b"{}")
    assert rig.confirmed == {(ITEM, 1)}
    workspace = m3._new_repo(tmp_path / "ws")
    app = (workspace / "src" / "app.py").read_text(encoding="utf-8").strip()
    statements = {ITEM: "Use tabs.", "m-" + "b" * 16: "Use tabs.", "m-" + "c" * 16: f"src/app.py holds {app}"}
    events = [(f"1-{n}", {b"e": json.dumps({"event": {"item": item, "version": 1, "action": action, "status": "active", "title": ""}})})
              for n, (item, action) in enumerate([(ITEM, "admit"), ("m-" + "b" * 16, "admit"), ("m-" + "c" * 16, "admit"),
                                                  ("m-" + "d" * 16, "off")])]
    store = SimpleNamespace(read=lambda item: SimpleNamespace(event=SimpleNamespace(statement=statements[item], lineage=())))
    rig = SimpleNamespace(store=SimpleNamespace(observer=SimpleNamespace(xrange=lambda _key, min: events)), seen_stream={},
                          confirmed={(ITEM, 1)}, host=SimpleNamespace(workspace=workspace, extractor=SimpleNamespace(store=store)))
    rig._points_at_a_file = lambda stored: m3.Rig._points_at_a_file(rig, stored)
    rig._holds_a_file = lambda stored: m3.Rig._holds_a_file(rig, stored)
    run = m3.Run()
    m3.Rig._stream(rig, run, 0, "proj")
    assert [(o.kind, o.item[2]) for o in run.observations] == [
        ("store.admit", "a"), ("commit.admit", "a"), ("store.admit", "b"), ("store.admit", "c"), ("store.body", "c"), ("store.off", "d")]
