"""Plan 12.11 Task 1: the closed shapes of `POST /v1/context/memory`. The store behind them is proven on the real dedicated Redis
in tests/integration/memory/test_store.py."""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from context_engine import memory_contracts as engine
from optimus_gateway import memory_store
from optimus_security import memory_store_contract as msc

_KEY = "a" * 64


def event(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"event_id": "e-1", "item": "m-0123456789abcdef", "version": 1, "action": "admit", "trust": "user-authored",
                            "status": "active", "kind": "preference", "scope": "s-1", "title": "pytest asserts",
                            "statement": "Use plain pytest asserts.", "anchors": ["b-1"], "lineage": [], "valid_from_ms": 0,
                            "valid_until_ms": 0}
    return {**base, **changes}


def append(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"op": "append", "project": "p-1", "token": 1, "expected_version": 0, "idempotency_key": _KEY, "event": event()}
    return {**body, **changes}


_POINT = {"session": "sess-1", "sequence": 1, "branch": "main", "worktree": "wt-1", "baseline": "b" * 40, "settled_at_ms": 5,
          "outcome": "settled", "objective": "obj-1", "provenance": "turn-1", "plan_hash": "", "pending": [], "amendments": [],
          "completion": [], "verification": [], "remaining": []}

VALID = [
    {"op": "capabilities"},
    {"op": "lease", "project": "p-1", "owner": "host-1", "action": "acquire", "ttl_ms": 30_000},
    {"op": "lease", "project": "p-1", "owner": "host-1", "action": "renew", "ttl_ms": 30_000, "token": 3},
    {"op": "lease", "project": "p-1", "owner": "host-1", "action": "release", "token": 3},
    append(),
    append(expected_version=1, event=event(version=2, action="update", statement="Use plain asserts everywhere.")),
    append(expected_version=2, event=event(version=3, action="withdraw", status="withdrawn", title="", statement="")),
    append(event=event(action="off", trust="off", statement="", title="withheld")),
    {"op": "read", "project": "p-1", "item": "m-0123456789abcdef"},
    {"op": "list", "project": "p-1", "scope": "s-1", "limit": 100},
    {"op": "list", "project": "p-1", "scope": "s-1", "limit": 1, "cursor": "bS0x." + "0" * 64},
    {"op": "checkpoint", "project": "p-1", "token": 1, "checkpoint": _POINT},
    {"op": "checkpoint", "project": "p-1", "token": 1, "checkpoint": {**_POINT, "baseline": ""}},
    {"op": "checkpoints", "project": "p-1", "limit": 20},
    {"op": "purge", "project": "p-1", "token": 1, "item": "m-0123456789abcdef", "idempotency_key": _KEY},
    {"op": "purge_status", "project": "p-1", "item": "m-0123456789abcdef"},
    {"op": "export", "project": "p-1", "limit": 100},
    {"op": "export", "project": "p-1", "limit": 1, "cursor": "bS0x." + "0" * 64},
    {"op": "restore", "project": "p-1", "token": 1, "generation": _KEY, "batch": 0, "final": True, "events": [event()]},
    {"op": "restore_status", "project": "p-1", "generation": _KEY},
]


@pytest.mark.parametrize("body", VALID, ids=lambda body: f"{body['op']}-{body.get('action') or body.get('event', {}).get('action', '')}")
def test_every_operation_has_one_valid_shape(body: dict[str, Any]) -> None:
    assert msc.parse_request(json.dumps(body).encode()) == body


def test_the_operation_set_is_closed_and_complete() -> None:
    assert {body["op"] for body in VALID} == msc.OPERATIONS


INVALID = {
    "unknown-op": {"op": "eval"},
    "extra-field": {"op": "capabilities", "key": "omem:x"},
    "missing-field": {"op": "read", "project": "p-1"},
    "project-with-space": {"op": "read", "project": "p 1", "item": "m-0123456789abcdef"},
    "item-shape": {"op": "read", "project": "p-1", "item": "omem:p:x"},
    "bool-is-not-int": {"op": "checkpoints", "project": "p-1", "limit": True},
    "list-limit-0": {"op": "list", "project": "p-1", "scope": "s-1", "limit": 0},
    "list-limit-101": {"op": "list", "project": "p-1", "scope": "s-1", "limit": 101},
    "cursor-shape": {"op": "list", "project": "p-1", "scope": "s-1", "limit": 1, "cursor": "no-tag"},
    "lease-unknown-action": {"op": "lease", "project": "p-1", "owner": "h", "action": "steal", "ttl_ms": 30_000},
    "lease-acquire-with-token": {"op": "lease", "project": "p-1", "owner": "h", "action": "acquire", "ttl_ms": 30_000, "token": 1},
    "lease-release-without-token": {"op": "lease", "project": "p-1", "owner": "h", "action": "release"},
    "lease-ttl-too-long": {"op": "lease", "project": "p-1", "owner": "h", "action": "acquire", "ttl_ms": 300_001},
    "event-extra-field": append(event={**event(), "key": "omem:x"}),
    "admit-not-first": append(expected_version=1, event=event(version=2)),
    "update-first": append(event=event(action="update")),
    "version-skips": append(expected_version=0, event=event(version=2, action="update")),
    "tombstone-by-append": append(event=event(action="tombstone", status="purged", title="", statement="")),
    "purged-by-append": append(event=event(status="purged")),
    "off-with-payload": append(event=event(action="off", trust="off")),
    "off-action-wrong-trust": append(event=event(action="off", statement="")),
    "withdraw-with-payload": append(expected_version=1, event=event(version=2, action="withdraw", status="withdrawn")),
    "withdrawn-without-withdraw": append(expected_version=1, event=event(version=2, action="update", status="withdrawn")),
    "statement-too-long": append(event=event(statement="x" * (msc.MAX_STATEMENT_CHARS + 1))),
    "statement-two-lines": append(event=event(statement="one\ntwo")),
    "validity-backwards": append(event=event(valid_from_ms=10, valid_until_ms=10)),
    "too-many-anchors": append(event=event(anchors=[f"b-{n}" for n in range(msc.MAX_REFERENCES + 1)])),
    "idempotency-not-digest": append(idempotency_key="retry-1"),
    "checkpoint-with-text": {"op": "checkpoint", "project": "p-1", "token": 1, "checkpoint": {**_POINT, "objective": "fix the bug"}},
    "checkpoint-bad-baseline": {"op": "checkpoint", "project": "p-1", "token": 1, "checkpoint": {**_POINT, "baseline": "main"}},
    "restore-empty-batch": {"op": "restore", "project": "p-1", "token": 1, "generation": _KEY, "batch": 0, "final": True, "events": []},
    "restore-too-many": {"op": "restore", "project": "p-1", "token": 1, "generation": _KEY, "batch": 0, "final": False,
                         "events": [event()] * (msc.MAX_RESTORE_BATCH + 1)},
    "restore-bad-event": {"op": "restore", "project": "p-1", "token": 1, "generation": _KEY, "batch": 0, "final": True,
                          "events": [event(status="purged")]},
    "restore-final-not-bool": {"op": "restore", "project": "p-1", "token": 1, "generation": _KEY, "batch": 0, "final": 1, "events": [event()]},
    "export-path": {"op": "export", "project": "p-1", "limit": 1, "path": "C:/x"},
    "withdraw-first": append(event=event(action="withdraw", status="withdrawn", title="", statement="")),
    "statement-c1-control": append(event=event(statement="a" + chr(0x85) + "b")),
    "statement-delete": append(event=event(statement="a" + chr(0x7F))),
    "title-bidi-override": append(event=event(title=chr(0x202E) + "evil")),
    "title-bidi-isolate": append(event=event(title=chr(0x2066) + "x" + chr(0x2069))),
}


def test_an_event_crosses_from_the_route_to_the_engine_and_back_unchanged() -> None:
    wire = event(anchors=["b-1:0-25"], lineage=["ev-1", "ev-2"], valid_from_ms=7, valid_until_ms=9)
    assert msc.event(wire) == wire
    assert engine.MemoryEvent.from_record("p-1", wire).to_record() == wire
    assert set(engine.MemoryEvent.RECORD_FIELDS) == set(wire)


def test_a_checkpoint_crosses_from_the_route_to_the_engine_and_back_unchanged() -> None:
    wire = {**_POINT, "plan_hash": "c" * 64, "amendments": ["am-1"], "completion": ["done-1"], "verification": ["ver-1"], "remaining": ["todo-1"]}
    assert msc.checkpoint(wire) == wire
    assert engine.ContinuationCheckpoint.from_record("p-1", wire).to_record() == wire


def test_a_record_with_a_missing_or_extra_field_is_not_an_engine_contract() -> None:
    with pytest.raises(engine.ContractError):
        engine.MemoryEvent.from_record("p-1", {**event(), "extra": 1})
    with pytest.raises(engine.ContractError):
        engine.ContinuationCheckpoint.from_record("p-1", {k: v for k, v in _POINT.items() if k != "provenance"})


def test_emoji_joined_by_zero_width_joiners_are_text() -> None:
    family = chr(0x1F468) + chr(0x200D) + chr(0x1F469) + chr(0x200D) + chr(0x1F467)
    body = append(event=event(statement=f"Our team emoji is {family}"))
    assert msc.parse_request(json.dumps(body).encode()) == body


@pytest.mark.parametrize("body", INVALID.values(), ids=INVALID.keys())
def test_anything_else_is_refused_before_the_store(body: dict[str, Any]) -> None:
    with pytest.raises(msc.MemoryRequestError) as refused:
        msc.parse_request(json.dumps(body).encode())
    assert (refused.value.code, refused.value.status) == ("REQUEST_INVALID", 400)


@pytest.mark.parametrize("raw", [b"", b"[]", b"\xff", b"[" * 100_000], ids=["empty", "array", "not-utf8", "deep-nesting"])
def test_malformed_bytes_are_refused(raw: bytes) -> None:
    with pytest.raises(msc.MemoryRequestError):
        msc.parse_request(raw)


def test_the_route_speaks_the_engines_vocabulary() -> None:
    assert msc.TRUST == engine.TRUST and msc.STATUS == engine.STATUS and msc.KINDS == engine.KINDS
    assert set(msc.APPEND_ACTIONS) == set(engine.ACTIONS) - {"tombstone"}
    assert (msc.MAX_STATEMENT_CHARS, msc.MAX_TITLE_CHARS) == (engine.MAX_STATEMENT_CHARS, engine.MAX_TITLE_CHARS)


class _Untouchable:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the store must not be reached: {name}")


@pytest.mark.parametrize("op", sorted(msc.UNAVAILABLE))
def test_operations_their_task_has_not_built_answer_unavailable_without_touching_redis(op: str) -> None:
    body = next(body for body in VALID if body["op"] == op)
    store = memory_store.MemoryStore(_Untouchable(), _Untouchable(), admission_ceiling_mb=384, cursor_key=b"k")  # type: ignore[arg-type]
    service = memory_store.MemoryStoreService(store)
    assert service.handle(json.dumps(body).encode(), deadline=time.monotonic() + 1) == (501, msc.error_body("MEMORY_OPERATION_UNAVAILABLE"))
