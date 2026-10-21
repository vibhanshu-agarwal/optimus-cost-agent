"""Plan 12.2 diagnosability, host side (operator directive 2026-10-20; Codex round 13 findings 2 and 3; a recorded
revision of the 2026-10-13 ``log_provider_attempts`` contract): every host failure on a model call keeps a bounded,
content-free cause in the debug trace, with the Gateway's and the provider's request ids for correlation. The trace
still never holds a body, a header, error text, a prompt, a reply or a credential."""

from __future__ import annotations

import errno
import json
from decimal import Decimal
from pathlib import Path
from urllib.error import URLError

import pytest

from optimus.acp.debug_trace import configure_debug_trace, log_provider_attempts, reset_debug_trace_context
from optimus.gateway import client as client_module
from optimus.gateway.attempts import attempts_from_failure, gateway_failure_facts, host_failure_facts
from optimus.gateway.client import GatewayRequest, UrllibGatewayTransport, _decode_gateway_json
from optimus.gateway.errors import GatewayHttpError, GatewayResponseError
from optimus.gateway.models import GatewayRouteAttempt, GatewayUsage, parse_gateway_response

CANARY = "Bearer " + "host-diagnostics-canary"  # synthetic; must never reach the trace
LOCATION = "debug_trace.py:log_provider_attempts"
# Ids in their generated shapes: the trace keeps only those (correction plan v4, C1).
GW1, GW2 = f"gw-{1:032x}", f"gw-{2:032x}"
SESSION = "session-" + "5" * 32


@pytest.fixture(autouse=True)
def _isolated_trace():
    reset_debug_trace_context()
    yield
    reset_debug_trace_context()


def _trace(tmp_path: Path) -> Path:
    log = tmp_path / "trace" / "debug-acp.ndjson"
    configure_debug_trace(enabled=True, log_path=log)
    return log


def _record(log: Path) -> dict:
    [record] = [r for r in map(json.loads, log.read_text(encoding="utf-8").splitlines()) if r["location"] == LOCATION]
    assert CANARY not in json.dumps(record)
    return record["data"]


def _usage(gateway_request_id: str) -> GatewayUsage:
    return GatewayUsage(gateway_request_id=gateway_request_id, provider="p", provider_request_id="gen-7", billing_units=3, cost_usd=Decimal("0.0003"))


# --- Causes captured where the host's failure originates ----------------------------------------------------------


def test_a_host_transport_failure_carries_its_class_and_errno(monkeypatch) -> None:
    def refuse(*_args, **_kwargs):
        raise URLError(ConnectionRefusedError(errno.ECONNREFUSED, CANARY))

    monkeypatch.setattr(client_module, "urlopen", refuse)
    request = GatewayRequest(method="POST", url="http://127.0.0.1:9/v1/responses", headers={}, payload={})
    with pytest.raises(GatewayHttpError) as caught:
        UrllibGatewayTransport().post_json(request)
    assert caught.value.failure == {"kind": "transport", "class": "URLError", "cause": "ConnectionRefusedError", "errno": errno.ECONNREFUSED}


@pytest.mark.parametrize(("body", "kind"), [("{not json", "gateway_invalid_json"), ("[1]", "gateway_non_object_json")], ids=["invalid", "array"])
def test_an_unreadable_gateway_reply_names_why(body: str, kind: str) -> None:
    with pytest.raises(GatewayHttpError) as caught:
        _decode_gateway_json(body)
    assert caught.value.failure == {"kind": kind}


@pytest.mark.parametrize(
    ("body", "audit_code"),
    [
        ({}, "GATEWAY_USAGE_MISSING"),
        ({"gateway_usage": {"gateway_request_id": "", "provider": "p", "billing_units": 1, "cost_usd": "0.1"}}, "GATEWAY_USAGE_INVALID"),
        ({"gateway_usage": {"gateway_request_id": GW1, "provider": "p", "billing_units": 1}}, "GATEWAY_COST_MISSING"),
        ({"gateway_usage": {"gateway_request_id": GW1, "provider": "p", "billing_units": 1, "cost_usd": "0.1"}}, "OUTPUT_TEXT_MISSING"),
        ({"gateway_usage": {"gateway_request_id": GW1, "provider": "p", "billing_units": 1, "cost_usd": "0.1"}, "output_text": "x", "id": 5}, "RESPONSE_ID_INVALID"),
        (
            {"gateway_usage": {"gateway_request_id": GW1, "provider": "p", "billing_units": 1, "cost_usd": "0.1"}, "output_text": "x", "finish_reason": 3},
            "FINISH_REASON_INVALID",
        ),
        (
            {"gateway_usage": {"gateway_request_id": GW1, "provider": "p", "billing_units": 1, "cost_usd": "0.1"}, "output_text": "x", "route_attempts": [{"x": 1}]},
            "ROUTE_ATTEMPTS_MALFORMED",
        ),
    ],
    ids=["usage-missing", "usage-invalid", "cost-missing", "output-missing", "id-invalid", "finish-invalid", "attempts-malformed"],
)
def test_every_response_contract_failure_has_its_own_audit_code(body: dict, audit_code: str) -> None:
    with pytest.raises(GatewayResponseError) as caught:
        parse_gateway_response(body)
    assert caught.value.audit_code == audit_code


# --- The common diagnostic ----------------------------------------------------------------------------------------


def test_the_gateway_facts_carry_the_host_cause_and_the_dropped_attempts_flag() -> None:
    failure = {"kind": "transport", "class": "URLError", "cause": "ConnectionRefusedError", "errno": 111}
    assert gateway_failure_facts(GatewayHttpError(0, CANARY, failure=failure)) == {"code": None, "http_status": None, "failure": failure}
    malformed = GatewayHttpError(502, CANARY, gateway_code="UPSTREAM_ATTEMPT_UNCERTAIN", route_attempts_malformed=True)
    assert gateway_failure_facts(malformed) == {"code": "UPSTREAM_ATTEMPT_UNCERTAIN", "http_status": 502, "route_attempts_malformed": True}


def test_a_host_failure_outside_the_gateway_names_its_audit_code_or_class() -> None:
    assert host_failure_facts(GatewayResponseError(CANARY, audit_code="OUTPUT_TEXT_MISSING")) == {"audit_code": "OUTPUT_TEXT_MISSING"}
    assert host_failure_facts(GatewayResponseError(CANARY, audit_code=CANARY)) == {"audit_code": "unrecognized"}
    assert host_failure_facts(ConnectionResetError(errno.ECONNRESET, CANARY)) == {"exception": {"class": "ConnectionResetError", "errno": errno.ECONNRESET}}
    assert host_failure_facts(GatewayHttpError(502, CANARY)) is None  # the Gateway facts carry it


def test_the_trace_records_the_request_ids_the_router_stages_and_the_attempt_cause(tmp_path) -> None:
    """The revised contract: bounded Gateway and provider request ids, router stage categories and the attempt's
    content-free cause are written; anything outside the id shape is recorded as unrecognized."""
    log = _trace(tmp_path)
    cause = {"kind": "transport", "class": "URLError", "cause": "ConnectionResetError", "errno": 104}
    refused = GatewayHttpError(
        502, CANARY, gateway_code="UPSTREAM_ATTEMPT_UNCERTAIN", retryable=False,
        route_attempts=(
            GatewayRouteAttempt(attempt=1, gateway_request_id=GW1, outcome="uncertain", failure=cause),
            GatewayRouteAttempt(attempt=2, gateway_request_id=GW2, outcome="rejected", http_status=429, provider_request_id=CANARY),
        ),
    )  # fmt: skip
    log_provider_attempts(stage="answer", correlation=lambda: {}, attempts=attempts_from_failure(refused), failure=refused)
    data = _record(log)
    first, second = data["attempts"]
    assert (first["gateway_request_id"], first["provider_request_id"], first["failure"]) == (GW1, None, cause)
    assert (second["gateway_request_id"], second["provider_request_id"], second["failure"]) == (GW2, "unrecognized", None)


def test_a_failure_outside_the_gateway_reaches_the_trace(tmp_path) -> None:
    log = _trace(tmp_path)
    lost = ConnectionResetError(errno.ECONNRESET, CANARY)
    log_provider_attempts(stage="summary", correlation=lambda: {}, attempts=attempts_from_failure(lost), failure=lost)
    assert _record(log)["host_failure"] == {"exception": {"class": "ConnectionResetError", "errno": errno.ECONNRESET}}


def test_a_reason_without_an_exception_is_recorded_when_allowlisted(tmp_path) -> None:
    log = _trace(tmp_path)
    log_provider_attempts(stage="summary", correlation=lambda: {}, attempts=(), reason="summary_disclosure_undelivered")
    log_provider_attempts(stage="summary", correlation=lambda: {}, attempts=(), reason=CANARY)
    records = [r["data"] for r in map(json.loads, log.read_text(encoding="utf-8").splitlines()) if r["location"] == LOCATION]
    assert [r["reason"] for r in records] == ["summary_disclosure_undelivered", "unrecognized"]
    assert CANARY not in log.read_text(encoding="utf-8")


def test_a_gateway_usage_attempt_keeps_its_provider_request_id(tmp_path) -> None:
    log = _trace(tmp_path)
    refused = GatewayHttpError(
        422, CANARY, gateway_code="EMPIRICAL_ROUTER_PIPELINE", retryable=False, gateway_usage=_usage(GW1),
        route_attempts=(GatewayRouteAttempt(attempt=1, gateway_request_id=GW1, outcome="completed", provider_request_id="gen-7", router_pipeline=("guardrail",)),),
    )  # fmt: skip
    log_provider_attempts(stage="answer", correlation=lambda: {}, attempts=attempts_from_failure(refused), failure=refused)
    [attempt] = _record(log)["attempts"]
    assert (attempt["gateway_request_id"], attempt["provider_request_id"], attempt["router_pipeline"]) == (GW1, "gen-7", ["guardrail"])


def test_the_audit_code_allowlist_is_every_code_the_source_raises() -> None:
    """A new response-contract audit code must be added to the allowlist, or the trace records it as unrecognized."""
    import re

    from optimus.gateway.attempts import AUDIT_CODES
    from tools.tracked_repository_files import tracked_repository_files

    sources = tracked_repository_files(Path(__file__).resolve().parents[3], pathspecs=("src",))
    found = (re.findall(r'audit_code="([A-Z_]+)"', path.read_text(encoding="utf-8")) for path in sources if path.suffix == ".py")
    assert {code for codes in found for code in codes} == set(AUDIT_CODES)


def test_a_prompt_refusal_is_traced_with_an_allowlisted_reason(tmp_path) -> None:
    from optimus.acp.debug_trace import log_prompt_refusal

    log = _trace(tmp_path)
    log_prompt_refusal(session_id=SESSION, request_id="p1", reason="reservation")
    log_prompt_refusal(session_id=SESSION, request_id=CANARY, reason=CANARY)
    records = [r["data"] for r in map(json.loads, log.read_text(encoding="utf-8").splitlines()) if r["location"] == "debug_trace.py:log_prompt_refusal"]
    assert records == [
        {"session_id": SESSION, "request_id": "p1", "reason": "reservation"},
        {"session_id": SESSION, "request_id": "unrecognized", "reason": "unrecognized"},
    ]
    assert CANARY not in log.read_text(encoding="utf-8")
