"""The shared failure-facts helper (Plan 12.2, operator directive 2026-10-20): every failure path persists a bounded,
content-free cause. These controls plant content and credential canaries where a cause could leak them."""

from __future__ import annotations

import errno
import json
import uuid
from urllib.error import URLError

import pytest

from optimus_security.failure_facts import (
    bounded,
    bounded_failure,
    bounded_guardrail_facts,
    exception_fact,
    final_sanitize,
    gateway_request_id,
    guardrail_stage_facts,
    host_route_id,
    host_session_id,
    provider_request_id,
    rpc_request_id,
    slug,
)

CANARY = "Bearer " + "failure-facts-canary-token"  # synthetic; must never survive into a fact


# --- #400: a guardrail router stage's closed facts (agreed handling D, Codex round 39) ----------------------------

# OpenRouter's documented blocked-guardrail stage (router-metadata guide, "Guardrail Blocked (403)"), with a canary in
# every free-text or identifying field.
BLOCKED_STAGE = {
    "type": "guardrail",
    "name": CANARY,
    "guardrail_id": CANARY,
    "guardrail_scope": "api-key",
    "summary": CANARY,
    "data": {"action": "blocked", "detected": True, "engines": [CANARY], "patterns": [CANARY]},
}


def test_a_guardrail_stage_keeps_only_its_documented_closed_facts() -> None:
    facts = guardrail_stage_facts(BLOCKED_STAGE)
    assert facts == {
        "flagged": "missing", "detected": True, "decision": "missing", "action": "blocked",
        "verdict_conflict": False, "guardrail_scope": "api-key",
    }  # fmt: skip
    assert CANARY not in json.dumps(facts)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, True), (False, False), ("false", "invalid"), (0, "invalid"), (None, "invalid")],
)
def test_a_guardrail_boolean_is_never_coerced(value, expected) -> None:
    assert guardrail_stage_facts({"type": "guardrail", "data": {"flagged": value}})["flagged"] == expected


def test_undocumented_verdicts_and_scopes_are_unrecognized_and_wrong_types_invalid() -> None:
    stage = {"type": "guardrail", "guardrail_scope": "workspace", "data": {"action": "redacted", "decision": "allow"}}
    facts = guardrail_stage_facts(stage)
    assert (facts["action"], facts["decision"], facts["guardrail_scope"]) == ("unrecognized", "unrecognized", "unrecognized")
    facts = guardrail_stage_facts({"type": "guardrail", "guardrail_scope": 7, "data": {"action": 5}})
    assert (facts["action"], facts["guardrail_scope"]) == ("invalid", "invalid")


def test_a_stage_without_readable_data_records_why() -> None:
    assert guardrail_stage_facts({"type": "guardrail"}) == {
        "flagged": "missing", "detected": "missing", "decision": "missing", "action": "missing",
        "verdict_conflict": False, "guardrail_scope": "missing",
    }  # fmt: skip
    facts = guardrail_stage_facts({"type": "guardrail", "data": [CANARY]})
    assert {facts[key] for key in ("flagged", "detected", "decision", "action")} == {"invalid"}
    assert CANARY not in json.dumps(facts)


def test_disagreeing_decision_and_action_set_the_conflict_indicator_and_neither_is_preferred() -> None:
    def conflict(data: dict) -> bool:
        return guardrail_stage_facts({"type": "guardrail", "data": data})["verdict_conflict"]

    assert conflict({"decision": "block", "action": "blocked"}) is True
    assert conflict({"decision": "blocked", "action": "blocked"}) is False
    assert conflict({"action": "blocked"}) is False
    facts = guardrail_stage_facts({"type": "guardrail", "data": {"decision": "block", "action": "blocked"}})
    assert (facts["decision"], facts["action"]) == ("unrecognized", "blocked")  # recorded apart, no alias wins


def test_an_explicit_null_verdict_is_present_and_can_conflict_but_a_missing_one_cannot() -> None:
    """Codex round 40, finding 4: presence is the key, never its value."""

    def facts(data: dict) -> dict:
        return guardrail_stage_facts({"type": "guardrail", "data": data})

    assert facts({"decision": None, "action": "blocked"})["verdict_conflict"] is True
    assert facts({"decision": None, "action": None})["verdict_conflict"] is False  # present and equal
    assert facts({"action": "blocked"})["verdict_conflict"] is False
    assert facts({"decision": None})["verdict_conflict"] is False
    assert facts({"decision": None})["decision"] == "invalid"


def test_received_guardrail_facts_are_re_bounded_before_they_are_persisted() -> None:
    received = {"flagged": "yes", "detected": True, "decision": CANARY, "action": "blocked", "verdict_conflict": CANARY,
                "guardrail_scope": CANARY, "name": CANARY}  # fmt: skip
    assert bounded_guardrail_facts(received) == {
        "flagged": "invalid", "detected": True, "decision": "unrecognized", "action": "blocked",
        "verdict_conflict": "invalid", "guardrail_scope": "unrecognized",
    }  # fmt: skip
    assert bounded_guardrail_facts(CANARY) is None


def test_an_exception_fact_names_its_class_and_errno_and_never_its_text() -> None:
    fact = exception_fact(OSError(errno.ENOSPC, f"No space left: {CANARY}"))
    assert fact == {"class": "OSError", "errno": errno.ENOSPC}
    assert CANARY not in json.dumps(fact)


def test_a_wrapped_transport_failure_names_the_underlying_class() -> None:
    fact = exception_fact(URLError(ConnectionRefusedError(errno.ECONNREFUSED, CANARY)))
    assert fact == {"class": "URLError", "cause": "ConnectionRefusedError", "errno": errno.ECONNREFUSED}


def test_an_exception_cause_is_followed_one_level() -> None:
    try:
        try:
            raise TimeoutError(CANARY)
        except TimeoutError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        fact = exception_fact(outer)
    assert fact == {"class": "RuntimeError", "cause": "TimeoutError", "errno": None}


def test_a_class_name_outside_the_safe_shape_is_never_recorded() -> None:
    hostile = type("Bearer secret value", (Exception,), {})
    assert exception_fact(hostile("x"))["class"] == "unrecognized"


def test_bounded_keeps_only_allowlisted_values() -> None:
    assert bounded("guardrail", frozenset({"guardrail"})) == "guardrail"
    assert bounded(CANARY, frozenset({"guardrail"})) == "unrecognized"
    assert bounded(None, frozenset({"guardrail"})) is None


def test_slug_keeps_a_module_authored_reason_and_rejects_anything_else() -> None:
    assert slug("upstream response has invalid provider cost") == "upstream_response_has_invalid_provider_cost"
    assert slug(f"upstream response has invalid {CANARY}") == "unrecognized"
    assert slug("x" * 200) == "unrecognized"


def test_a_received_failure_cause_is_re_bounded_before_it_is_persisted() -> None:
    hostile = {"kind": CANARY, "class": CANARY, "cause": "ConnectionResetError", "errno": "111", "reason": CANARY, "message": CANARY}
    assert bounded_failure(hostile) == {"kind": "unrecognized", "class": "unrecognized", "cause": "ConnectionResetError", "errno": None, "reason": "unrecognized"}
    assert bounded_failure({"kind": "schema", "reason": "upstream_response_has_invalid_usage"}) == {"kind": "schema", "reason": "upstream_response_has_invalid_usage"}
    assert bounded_failure(CANARY) is None


# --- Field-specific id projections (correction plan v4, C1) -------------------------------------------------------

BARE_KEY = "sk-or-v1-" + "0123456789abcdef" * 4  # pragma: allowlist secret - synthetic credential-shaped canary
PROSE = "private note CANARY"
GW = f"gw-{uuid.uuid4().hex}"
SESSION = f"session-{uuid.uuid4().hex}"


def _host_route_ids() -> list[str]:
    """Every host-generated id shape, from the real generators' formats (`spec.py:327`, `route_binding.py:175`,
    `maintenance.py:404`)."""
    return [f"{SESSION}:3", f"{SESSION}:3:answer:1:{uuid.uuid4().hex}", f"{SESSION}:12:summary:2:{uuid.uuid4().hex}"]


def test_a_gateway_request_id_keeps_only_the_gateway_shape() -> None:
    assert (gateway_request_id(GW), gateway_request_id(None)) == (GW, None)
    for hostile in (BARE_KEY, PROSE, "gw-1", f"{GW}x", 7):
        assert gateway_request_id(hostile) == "unrecognized"


def test_a_provider_request_id_keeps_only_the_openrouter_generation_shape() -> None:
    assert provider_request_id("gen-1760001234-AbC_d-9") == "gen-1760001234-AbC_d-9"
    for hostile in (BARE_KEY, PROSE, "chatcmpl-1", "gen-" + "x" * 97):
        assert provider_request_id(hostile) == "unrecognized"


def test_host_run_and_route_ids_keep_the_generated_shapes() -> None:
    for real in _host_route_ids():
        assert host_route_id(real) == real
    for hostile in (BARE_KEY, PROSE, SESSION, f"{SESSION}:3:Answer:1:{uuid.uuid4().hex}", f"{SESSION}:3:answer:1:short"):
        assert host_route_id(hostile) == "unrecognized"
    assert host_route_id(None) is None


def test_a_host_session_id_keeps_the_generated_shape() -> None:
    assert host_session_id(SESSION) == SESSION
    assert (host_session_id(PROSE), host_session_id(BARE_KEY), host_session_id(None)) == ("unrecognized", "unrecognized", None)


def test_a_client_rpc_id_is_an_int_or_a_short_plain_token_never_a_credential() -> None:
    assert (rpc_request_id(0), rpc_request_id(1), rpc_request_id("abc-1_x"), rpc_request_id(None)) == (0, 1, "abc-1_x", None)
    for hostile in (True, BARE_KEY, "sk-" + "a" * 20, "tvly-abc", PROSE, "x" * 65):
        assert rpc_request_id(hostile) == "unrecognized"


def test_slug_accepts_brackets_and_colons_in_module_reasons() -> None:
    assert slug("upstream response missing choices[0]") == "upstream_response_missing_choices_0"
    assert slug("gateway_usage missing required field: cost_usd") == "gateway_usage_missing_required_field_cost_usd"


def test_a_received_http_failure_keeps_its_integer_status() -> None:
    assert bounded_failure({"kind": "http", "status": 503}) == {"kind": "http", "status": 503}
    assert bounded_failure({"kind": "http", "status": "503"}) == {"kind": "http", "status": None}
    assert bounded_failure({"kind": "http", "status": 99}) == {"kind": "http", "status": None}


def test_final_sanitize_redacts_a_planted_credential_and_keeps_the_shape() -> None:
    record = {"event": "model_request", "error": f"failed: {CANARY}", "status": 502}
    cleaned = final_sanitize(record)
    assert CANARY not in json.dumps(cleaned)
    assert (cleaned["event"], cleaned["status"]) == ("model_request", 502)


def test_final_sanitize_redacts_a_bare_credential_by_its_prefix_and_keeps_real_ids() -> None:
    real = {"gateway_request_id": GW, "provider_request_id": "gen-1760001234-AbCdEf0123456789", "route_request_id": _host_route_ids()[1]}
    cleaned = final_sanitize({"error": f"refused {BARE_KEY}", **real})
    assert BARE_KEY not in json.dumps(cleaned)
    assert {key: cleaned[key] for key in real} == real


@pytest.mark.parametrize("kind", ["attempt_deadline", "attempt_capacity", "request_budget"])
def test_the_request_budget_failure_kinds_survive_re_bounding(kind: str) -> None:
    """Codex round 2 on #397 Z2: an unlisted kind is persisted as unrecognized, losing why the attempt ended."""
    assert bounded_failure({"kind": kind}) == {"kind": kind}
