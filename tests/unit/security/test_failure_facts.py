"""The shared failure-facts helper (Plan 12.2, operator directive 2026-10-20): every failure path persists a bounded,
content-free cause. These controls plant content and credential canaries where a cause could leak them."""

from __future__ import annotations

import errno
import json
from urllib.error import URLError

from optimus_security.failure_facts import bounded, bounded_failure, bounded_id, exception_fact, final_sanitize, slug

CANARY = "Bearer " + "failure-facts-canary-token"  # synthetic; must never survive into a fact


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


def test_a_request_id_keeps_the_plain_id_shape_only() -> None:
    assert (bounded_id("gw-0123abcd"), bounded_id("gen-1760-abc"), bounded_id(None)) == ("gw-0123abcd", "gen-1760-abc", None)
    assert bounded_id(CANARY) == "unrecognized"


def test_final_sanitize_redacts_a_planted_credential_and_keeps_the_shape() -> None:
    record = {"event": "model_request", "error": f"failed: {CANARY}", "status": 502}
    cleaned = final_sanitize(record)
    assert CANARY not in json.dumps(cleaned)
    assert (cleaned["event"], cleaned["status"]) == ("model_request", 502)
