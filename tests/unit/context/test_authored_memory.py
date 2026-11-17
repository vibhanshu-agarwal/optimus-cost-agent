"""Plan 12.11: the host adapter for the memory store route, against the Gateway's real handler on the in-memory stand-in."""

from __future__ import annotations

import time
from typing import Any

import pytest

from context_engine import memory_gate
from context_engine.memory_contracts import HostVerdict, MemoryCandidate, Span
from optimus.context import authored_memory as am
from optimus.usage.savings_report import ReportTransportError
from tests.unit.optimus_gateway.test_memory_store_commit import store

_TRUSTED = HostVerdict(workspace_trusted=True, scope_valid=True, spans_verified=True, lineage_complete=True, scans_passed=True)


def _adapter(service: Any, owner: str = "host-1") -> am.GatewayMemoryStore:
    def post(_settings: Any, *, timeout: float, path: str) -> Any:
        assert path == "/v1/context/memory" and timeout > 5
        return lambda body: service.handle(body, deadline=time.monotonic() + 5)

    return am.GatewayMemoryStore(object(), project="p-1", owner=owner, post=post)  # type: ignore[arg-type]


def _candidate(statement: str = "New tests use plain pytest asserts.", **changes: Any) -> MemoryCandidate:
    fields = {"project": "p-1", "scope": "s-1", "trust": "user-authored", "kind": "preference", "speech_act": "preference",
              "statement": statement, "title": "test style", "spans": (Span("b-1", 0, 40),), "idempotency_key": "a" * 64}
    return MemoryCandidate(**{**fields, **changes})


def test_a_gate_draft_is_appended_once_and_read_back_as_the_engine_s_event() -> None:
    service, server, _ = store()
    adapter = _adapter(service)
    candidate = _candidate()
    draft = memory_gate.admit(candidate, _TRUSTED).draft
    assert draft is not None
    with adapter.lease() as token:
        first = adapter.append(token, candidate, draft)
        again = adapter.append(token, candidate, draft)  # the same decision retried: the first result, nothing appended twice
    assert first.durable_state == "confirmed" and (again.event_id, again.version) == (first.event_id, first.version)
    stored = adapter.read(draft.item)
    assert stored is not None and (stored.event.statement, stored.event.trust, stored.event.anchors) == (
        "New tests use plain pytest asserts.", "user-authored", ("b-1:0-40",))
    assert sum(len(entries) for entries in server.streams.values()) == 1
    assert [item.item for item in adapter.user_items("s-1", limit=20)] == [draft.item]


def test_the_lease_is_released_after_the_job_and_another_holder_is_a_refusal() -> None:
    service, _server, _ = store()
    first, second = _adapter(service, "host-1"), _adapter(service, "host-2")
    with first.lease():
        with pytest.raises(am.MemoryStoreRefused) as refused, second.lease():
            pass
        assert refused.value.code == "LEASE_HELD"
    with second.lease() as token:
        assert token > 0


def test_an_unreachable_store_is_unavailable_never_a_refusal() -> None:
    def post(_settings: Any, **_kwargs: Any) -> Any:
        def send(_body: bytes) -> Any:
            raise ReportTransportError("down")
        return send

    adapter = am.GatewayMemoryStore(object(), project="p-1", owner="h", post=post)  # type: ignore[arg-type]
    with pytest.raises(am.MemoryStoreUnavailable):
        adapter.read("m-0123456789abcdef")
