"""Plan 12.11 Task 5 qualification driver: the parts that run without the released store (how a run's observations are recorded
at their boundaries and turned into the grader's trace, and what a zero-paid run may decide)."""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tools.plan12_memory import m3_evaluate as m3
from tools.plan12_memory.evaluate import grade_trace

FIXTURES = (Path("tests/fixtures/plan12_memory/lifecycle.json"), Path("tests/fixtures/plan12_memory/lifecycle-d10.json"))
CONFIG = Path("reports/plan12-memory-m3/run-config.json")
ITEM = "m-" + "a" * 16
OTHER = "m-" + "b" * 16


def _cases() -> dict[str, m3.GoldenCase]:
    found: dict[str, m3.GoldenCase] = {}
    for fixture in FIXTURES:
        found.update(m3.load_cases(fixture))
    return found


def _row(version: int, action: str, status: str, trust: str = "user-authored", kind: str = "preference") -> SimpleNamespace:
    return SimpleNamespace(version=version, action=action, status=status, trust=trust, kind=kind)


def _entry(version: int, action: str, status: str, trust: str = "user-authored", kind: str = "preference") -> dict[str, Any]:
    return {"version": version, "action": action, "status": status, "trust": trust, "kind": kind}


class _Redis:
    """The store's stream and payload hash, as the harness's own read connection sees them."""

    def __init__(self) -> None:
        self.streams: dict[str, list[tuple[str, dict[bytes, bytes]]]] = {}
        self.hashes: dict[str, dict[str, bytes]] = {}

    def write(self, project: str, event: dict[str, Any], statement: str = "", lineage: tuple[str, ...] = ()) -> None:
        key = m3.memory_store.MemoryStore._key(project, "events")
        entries = self.streams.setdefault(key, [])
        entries.append((f"1-{len(entries)}", {b"e": json.dumps({"event": event}).encode()}))
        self.hashes.setdefault(m3.memory_store.MemoryStore._key(project, "payloads"), {})[event["event_id"]] = json.dumps(
            {"statement": statement, "title": event.get("title", ""), "lineage": list(lineage)}).encode()

    def xrange(self, key: str, min: str) -> list[tuple[str, dict[bytes, bytes]]]:
        entries = self.streams.get(key, [])
        after = min.lstrip("(")
        ids = [stream_id for stream_id, _fields in entries]
        return entries[ids.index(after) + 1:] if after in ids else entries

    def hget(self, key: str, field: str) -> bytes | None:
        return self.hashes.get(key, {}).get(field)


def _rig(tmp_path: Path) -> m3.Rig:
    """A rig with the real recording code over a stand-in store connection and a real workspace repository."""
    rig = object.__new__(m3.Rig)
    rig.run = m3.Run()
    rig.store = SimpleNamespace(observer=_Redis())
    rig.seen_stream, rig.exporter, rig.pending, rig.asking, rig.items = {}, {}, {}, False, {}
    rig.host = SimpleNamespace(workspace=m3._new_repo(tmp_path / "ws"), project="proj")
    return rig


def _event(item: str, version: int, action: str = "admit", status: str = "active", trust: str = "user-authored", **extra: Any) -> dict[str, Any]:
    return {"item": item, "version": version, "action": action, "status": status, "trust": trust, "kind": "preference",
            "event_id": f"e-{item[-1]}-{version}", "lineage": [], "title": "", **extra}


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
])
def test_a_status_change_reaches_the_content_versions_before_it(versions: list[dict[str, Any]], expected: list[str]) -> None:
    assert m3.version_statuses(versions) == expected


def test_a_commit_counts_only_for_its_own_project_s_confirmed_event_in_order(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    redis = rig.store.observer
    redis.write("source", _event(ITEM, 1))
    rig.exchanged({"op": "append", "project": "source"}, 200, {"event_id": "e-a-1", "durable_state": "confirmed"})
    redis.write("target", _event(ITEM, 1))  # the same item, published by an unconfirmed restore into another project
    rig.exchanged({"op": "restore", "project": "target", "final": True, "generation": "g"}, 200, {"state": "published", "durable_state": "unconfirmed"})
    redis.write("target", _event(OTHER, 1))
    rig.exchanged({"op": "append", "project": "target"}, 200, {"event_id": "e-b-1", "durable_state": "unconfirmed"})
    assert [(o.kind, o.item, o.project) for o in rig.run.observations] == [
        ("store.admit", ITEM, "source"), ("commit.admit", ITEM, "source"), ("store.admit", ITEM, "target"), ("store.admit", OTHER, "target")]
    case = _cases()["M01-a-D10"]
    trace = m3.to_trace(case, rig.run, {"pref-indent": ITEM}, {}, source_id="g", config_id="c", project="target")
    assert "memory.committed" not in [e.type for e in trace.events]  # the source's confirmation is not the target's


def test_a_card_sent_before_its_commit_is_not_a_notice_of_a_durable_commit() -> None:
    case = _cases()["M03-b-D10"]
    ordered, early = m3.Run(), m3.Run()
    for kinds, run in ((("store.admit", "commit.admit", "card.Remembered"), ordered), (("store.admit", "card.Remembered", "commit.admit"), early)):
        for kind in kinds:
            run.add(kind, ITEM, 1)
        run.add("store.withdraw", ITEM, 2)
    history = {ITEM: [_entry(1, "admit", "active"), _entry(2, "withdraw", "withdrawn")]}
    grade = {name: grade_trace(case, m3.to_trace(case, run, {"pref-indent": ITEM}, {ITEM: _row(2, "withdraw", "withdrawn")},
                                                  source_id="g", config_id="c", history=history)).layers["authority"].status
             for name, run in (("ordered", ordered), ("early", early))}
    assert grade == {"ordered": "PASS", "early": "FAIL"}


def test_cards_and_requests_are_recorded_as_the_host_sends_them(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    channel = m3._Channel(rig)
    held: list[dict[str, Any]] = []
    channel.host = SimpleNamespace(project="proj", state=SimpleNamespace(memory_backlog=SimpleNamespace(pending=lambda: held)))

    def card(event: str) -> dict[str, Any]:
        return {"sessionUpdate": "tool_call", "toolCallId": f"memory/{event}", "title": "Remembered: x",
                "content": [{"content": {"text": f"[memory:{ITEM}@1] · confirmed, current"}}]}

    async def scenario() -> None:
        channel.fail_cards = True
        held.append({"event_id": "e-1"})
        with pytest.raises(ConnectionError):
            await channel.notify("session/update", {"update": card("e-1")})  # the backlog holds it: backlogged
        with pytest.raises(ConnectionError):
            await channel.notify("session/update", {"update": card("e-2")})  # nothing kept it: no notice of any kind
        channel.fail_cards = False
        await channel.notify("session/update", {"update": card("e-1")})
        asking = asyncio.create_task(channel.request("session/request_permission", {}))
        await asyncio.sleep(0)
        rig.asking = True
        asked = asyncio.create_task(channel.request("session/request_permission", {}))
        await asyncio.sleep(0)
        asking.cancel(), asked.cancel()

    asyncio.run(scenario())
    assert [o.kind for o in rig.run.observations] == ["card.backlogged", "card.Remembered", "host.prompt"]


def test_each_detector_reports_what_it_was_built_to_see(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    redis = rig.store.observer
    redis.write("proj", _event(ITEM, 1, trust="agent-derived"))
    redis.write("proj", _event(ITEM, 2, action="update"))  # the same item now the user's: a trust change and a promotion
    redis.write("proj", _event(OTHER, 1, action="off", status="conflicted", trust="off"))
    app = (rig.host.workspace / "src" / "app.py").read_text(encoding="utf-8")
    redis.write("proj", _event("m-" + "c" * 16, 1), statement=f"src/app.py holds {app}")
    redis.write("proj", _event("m-" + "d" * 16, 1), statement="Read src/app.py for the entry point.", lineage=("file:src/app.py@0123",))
    redis.write("proj", _event("m-" + "e" * 16, 1, action="off", trust="off", title="(blocked)"))
    rig.exchanged({"op": "append", "project": "proj"}, 200, {"event_id": "none", "durable_state": "confirmed"})
    rig.exporter["seal-1"] = "earlier"
    rig.exchanged({"op": "restore", "project": "proj", "final": True, "generation": "seal-1"}, 200, {"state": "published"})
    rig.exchanged({"op": "restore", "project": "other", "final": True, "generation": "seal-1", "source": "earlier"}, 200,
                  {"state": "published"})
    served = SimpleNamespace(items=(), reverify=((OTHER, 1, "config.py"),), elsewhere=(), omitted_optional=0, omitted_protected=0,
                             complete=True)
    rows = [SimpleNamespace(event=SimpleNamespace(item=ITEM, version=2, status="active", trust="user-authored", statement="x"))]
    rig.served_decision(SimpleNamespace(store=SimpleNamespace(project="proj", items=lambda *_a, **_k: (rows, None))), served)
    kinds = [o.kind for o in rig.run.observations]
    for expected in ("store.trust_changed", "store.trust_promoted", "store.off.conflict", "store.body", "store.pointer",
                     "store.off.blocked", "restore.unmapped", "served.reverify", "served.expired"):
        assert expected in kinds, expected
    assert "commit.admit" not in kinds  # the reply confirmed none of the events read with it
    assert kinds.count("restore.unmapped") == 1 and rig.run.mapped == {"other": "earlier"}


def test_every_event_an_in_scope_case_needs_is_observable_or_owned_elsewhere() -> None:
    cases, config = _cases(), json.loads(CONFIG.read_text(encoding="utf-8"))["cases"]
    needed = {name.split(":")[0] for case_id in config for name in (*cases[case_id].required_events, *cases[case_id].prohibited_events)}
    assert needed - m3.OBSERVABLE - set(m3.UNRUN_EVENTS) == set()
    source = Path(m3.__file__).read_text(encoding="utf-8")
    emitted = source[source.index("class Observation"):]  # every kind is added somewhere, never only declared
    for kind in m3.EVENT_OF:
        family = kind.split(".")[0] + "."
        assert f'"{kind}"' in emitted or f'f"{family}{{' in emitted or kind.startswith("card."), kind


def test_a_restored_version_is_reported_only_from_what_the_run_saw() -> None:
    case = _cases()["M21-d-D10"]
    seen = m3.Run()
    seen.history[("proj", ITEM)] = {1: _entry(1, "admit", "active"), 2: _entry(2, "update", "active"), 3: _entry(3, "withdraw", "withdrawn")}
    restored = {ITEM: [_entry(3, "withdraw", "withdrawn")]}  # a restore re-applying the withdrawal publishes only that entry
    trace = m3.to_trace(case, seen, {"pref-indent": ITEM}, {ITEM: _row(3, "withdraw", "withdrawn")}, source_id="g", config_id="c",
                        history=restored, project="proj")
    assert [(s.version, s.status) for s in trace.memory_state] == [(1, "superseded"), (2, "withdrawn"), (3, "withdrawn")]
    assert trace.coverage_complete
    unseen = m3.to_trace(case, m3.Run(), {"pref-indent": ITEM}, {ITEM: _row(3, "withdraw", "withdrawn")}, source_id="g",
                         config_id="c", history=restored, project="proj")
    assert [(s.version, s.status) for s in unseen.memory_state] == [(3, "withdrawn")]  # never reconstructed
    assert not unseen.coverage_complete and "history: pref-indent v1 was never observed" in unseen.missing_coverage
    mapped = m3.Run()  # versions seen in the project a published restore mapped into this one count too
    mapped.mapped["proj"] = "earlier"
    mapped.history[("earlier", ITEM)] = {1: _entry(1, "admit", "active"), 2: _entry(2, "update", "active")}
    trace = m3.to_trace(case, mapped, {"pref-indent": ITEM}, {ITEM: _row(3, "withdraw", "withdrawn")}, source_id="g", config_id="c",
                        history=restored, project="proj")
    assert trace.coverage_complete and [s.status for s in trace.memory_state] == ["superseded", "withdrawn", "withdrawn"]


def test_another_project_s_observations_are_not_this_project_s_events() -> None:
    case = _cases()["M03-b-D10"]
    run = m3.Run()
    run.add("commit.admit", ITEM, 1, "earlier")
    run.add("checkpoint", project="earlier")
    run.add("checkpoint", project="proj")
    trace = m3.to_trace(case, run, {"pref-indent": ITEM}, {}, source_id="g", config_id="c", project="proj")
    assert [e.type for e in trace.events] == ["checkpoint.written"]


def test_a_hostile_lesson_from_tool_text_is_offered_with_fresh_verification(tmp_path: Path) -> None:
    submitted: list[Any] = []
    run = m3.Run()
    extraction = m3._Extraction(run)
    rig = SimpleNamespace(extraction=extraction, finish_input=lambda: None,
                          host=SimpleNamespace(session="s", extractor=SimpleNamespace(submit=submitted.append)))
    asyncio.run(m3._op_tool_output(rig, run, 4, "README.md: build with make all.", kind="document"))
    (turn,) = submitted
    assert [(e.ref, e.kind) for e in turn.work.evidence] == [("ev-4", "document"), ("ev-4-check", "verification")]
    prompt = "You extract at most a few optional lessons\n- ev-4-check (verification)\n- ev-4 (document)\n"
    (lesson,) = json.loads(extraction(prompt=prompt, max_output_tokens=100).text)["candidates"]
    assert lesson["evidence"] == ["ev-4"] and "make all" in lesson["statement"] and run.calls == ["agent"]


def test_a_crash_the_run_cannot_exercise_is_missing_coverage() -> None:
    run = m3.Run()
    asyncio.run(m3._op_crash(SimpleNamespace(), run, 1, "the host dies"))
    trace = m3.to_trace(_cases()["M19-a"], run, {}, {}, source_id="g", config_id="c")
    assert not trace.coverage_complete and any(name.startswith("crash:") for name in trace.missing_coverage)
    assert trace.reported_cost.complete is False  # nor does it claim its cost is complete
    assert grade_trace(_cases()["M19-a"], trace).layers["cost"].status != "FAIL"


def test_a_needed_event_the_harness_cannot_observe_is_missing_coverage() -> None:
    case = _cases()["M20-a"]  # decay: strength_faded is the product's (#235 M6) to show
    trace = m3.to_trace(case, m3.Run(), {}, {}, source_id="git:x", config_id="c")
    assert not trace.coverage_complete and trace.missing_coverage == ("memory.strength_faded:pref-indent",)


def _verdict(case: m3.GoldenCase, run: m3.Run | None = None, named: dict[str, str] | None = None,
             items: dict[str, Any] | None = None) -> tuple[Any, Any]:
    trace = m3.to_trace(case, run or m3.Run(), named or {}, items or {}, source_id="g", config_id="c")
    return grade_trace(case, trace), trace


def test_a_zero_paid_run_never_passes_a_case_and_names_who_decides_the_rest() -> None:
    cases = _cases()
    view = m3.qualification_view(cases["M03-b-D10"], _verdict(cases["M03-b-D10"])[0], [])
    assert view["layers"]["answer"] == "UNRUN" and view["status"] in ("INCONCLUSIVE", "FAIL") and "retrieval" not in view["owners"]
    evidence = cases["M06-b"]  # requires a retrieved README: the stand-in runs no tools
    view = m3.qualification_view(evidence, _verdict(evidence)[0], [])
    assert view["layers"]["retrieval"] == "UNRUN" and view["owners"]["retrieval"] == m3.PAID and view["status"] == "INCONCLUSIVE"
    ranked = SimpleNamespace(layers={**_verdict(evidence)[0].layers,
                                     "retrieval": SimpleNamespace(status="FAIL", reasons=("served order ['b', 'a'] breaks the required rank",))})
    assert m3.qualification_view(evidence, ranked, [])["layers"]["retrieval"] == "FAIL"  # a rank failure is still decided here


def test_a_decay_case_keeps_its_own_safety_checks() -> None:
    decay = _cases()["M20-a-D10"]  # pref-indent and pref-ruff stay active however long the break
    named = {"pref-indent": ITEM, "pref-ruff": OTHER}
    items = {ITEM: _row(1, "admit", "active"), OTHER: _row(1, "admit", "active")}
    verdict, trace = _verdict(decay, m3.Run(), named, items)
    view = m3.qualification_view(decay, verdict, ["#235 M6 (decay)"], trace)
    assert view["status"] == "UNRUN" and view["owners"]["case"] == "#235 M6 (decay)" and view["safety"]["status"] == "PASS"
    verdict, trace = _verdict(decay, m3.Run(), named, {ITEM: _row(1, "withdraw", "withdrawn"), OTHER: items[OTHER]})
    assert m3.qualification_view(decay, verdict, ["#235 M6 (decay)"], trace)["status"] == "FAIL"  # an expected item gone
    expired = m3.Run()
    expired.add("served.expired", ITEM, 1)
    verdict, trace = _verdict(decay, expired, named, items)
    view = m3.qualification_view(decay, verdict, ["#235 M6 (decay)"], trace)
    assert view["status"] == "FAIL" and any("memory.expired" in reason for reason in view["safety"]["reasons"])


def test_a_failed_decided_layer_stays_failed() -> None:
    case = _cases()["M03-b-D10"]
    run = m3.Run()
    run.add("card.Remembered", ITEM, 1)  # a notice with no commit before it
    verdict = grade_trace(case, m3.to_trace(case, run, {"pref-indent": ITEM}, {}, source_id="g", config_id="c"))
    assert m3.qualification_view(case, verdict, [])["status"] == "FAIL"


def test_the_variant_fixture_is_bound_to_its_decision_and_keeps_every_gold(tmp_path: Path) -> None:
    document = json.loads(FIXTURES[1].read_text(encoding="utf-8"))
    m3.check_variants(document)
    tampered = copy.deepcopy(document)
    tampered["decision"]["sha256"] = "hex:" + "0" * 64
    with pytest.raises(ValueError, match="digest"):
        m3.check_variants(tampered)
    changed = copy.deepcopy(document)
    changed["cases"][0]["expected_memory"] = []
    with pytest.raises(ValueError, match="gold"):
        m3.check_variants(changed)
    stray = copy.deepcopy(document)
    stray["cases"][0]["case_id"] = "M99-z-D10"
    with pytest.raises(ValueError, match="variant"):
        m3.check_variants(stray)
    reworded = copy.deepcopy(document)
    user = next(item for item in reworded["cases"][0]["inputs"] if item["actor"] == "user")
    user["text"] = "/remember something else"
    m3.check_variants(reworded)  # only the user's words may change


def test_the_effective_oracles_decide_from_what_the_run_recorded() -> None:
    skip = m3.Run()
    skip.outcomes.append({"purpose": m3.AGENT_PURPOSE, "skipped": "user_items_in_scope"})
    items = {ITEM: SimpleNamespace(version=1, status="active", trust="user-authored")}
    rig = SimpleNamespace(run=skip, items={"pref-indent": ITEM})
    assert m3._m09_skip(rig, items)["status"] == "PASS"
    skip.calls.append("agent")
    assert m3._m09_skip(rig, items)["status"] == "FAIL"
    overflow = m3.Run()
    overflow.seq = 2
    overflow.created_by[("p", OTHER)] = 2
    overflow.add("store.off.archived", ITEM, 2)
    rig = SimpleNamespace(run=overflow, items={})
    live = {OTHER: SimpleNamespace(trust="off", status="active")}
    assert m3._m15_overflow(rig, live)["status"] == "PASS"
    overflow.add("store.tombstone", ITEM, 3)
    assert m3._m15_overflow(rig, live)["status"] == "FAIL"


def test_a_command_names_the_item_and_version_the_user_would_read() -> None:
    store = SimpleNamespace(read=lambda item: SimpleNamespace(event=SimpleNamespace(version=3)) if item == ITEM else None)
    rig = SimpleNamespace(items={"pref-indent": ITEM}, host=SimpleNamespace(extractor=SimpleNamespace(store=store)))
    assert m3._resolve("/forget {pref-indent@v} --purge", rig) == f"/forget {ITEM}@3 --purge"
    assert m3._resolve("/memory view {pref-indent}", rig) == f"/memory view {ITEM}"
