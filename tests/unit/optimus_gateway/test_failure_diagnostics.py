"""Plan 12.2 diagnosability (operator directive 2026-10-20; Fable pr-3 F1/F4/F6, Codex round 13 findings 1 and 3-5):
every Gateway failure on the two model routes persists a bounded, content-free cause in the attempt record and the
Gateway log line, and no persisted diagnostic carries prompt, reply, upstream error text or a credential."""

from __future__ import annotations

import json
import sys
import urllib.request
from typing import Any

import pytest

import optimus_gateway.responses as gateway_responses
from optimus_gateway.responses import handle_responses_request, model_request_log_line
from optimus_gateway.upstream_client import (
    ProviderMessageResult,
    UpstreamAttemptFailure,
    UrllibOpenAICompatibleClient,
    parse_openai_chat_completion,
)
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.binding import BindingError, RouteBinding
from tests.unit.optimus_gateway.model_policy_support import (
    AUTH,
    PROVIDER_KEY,
    RecordingUpstream,
    Wire,
    binding,
    gateway_config,
    http_reply,
    model_policy,
)
from tests.unit.optimus_gateway.test_server import _post_json, _SmokeUpstreamClient, _start_server, _stop_server

CANARY = "Bearer " + "gateway-diagnostics-canary"  # synthetic; must never reach a persisted diagnostic
_URL = "https://openrouter.ai/api/v1"
HAIKU = "anthropic/claude-haiku-5.5"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway_responses, "_sleep", lambda _seconds: None)


def _once() -> Any:
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url=_URL, sleep=lambda _s: None)
    return client.create_message_once(model="cn/alpha", input_text="hi", max_tokens=8, provider_controls={"only": ["a/b"]}, reasoning=None)


def _failure(monkeypatch: pytest.MonkeyPatch, wire: Wire) -> UpstreamAttemptFailure:
    wire.install(monkeypatch)
    with pytest.raises(UpstreamAttemptFailure) as caught:
        _once()
    assert CANARY not in json.dumps(caught.value.failure)
    return caught.value


# --- The upstream attempt's own cause (Fable F1, Codex 1) ---------------------------------------------------------


def test_a_connect_failure_keeps_its_class_and_errno_never_its_text(monkeypatch) -> None:
    failure = _failure(monkeypatch, Wire(connect=ConnectionRefusedError(10061, CANARY)))
    assert (failure.outcome, failure.failure) == ("not_sent", {"kind": "transport", "class": "URLError", "cause": "ConnectionRefusedError", "errno": 10061})


def test_a_failure_while_sending_keeps_its_class_and_errno(monkeypatch) -> None:
    failure = _failure(monkeypatch, Wire(send=ConnectionResetError(10054, CANARY)))
    assert (failure.outcome, failure.failure) == ("uncertain", {"kind": "transport", "class": "URLError", "cause": "ConnectionResetError", "errno": 10054})


def test_a_lost_reply_names_its_class(monkeypatch) -> None:
    failure = _failure(monkeypatch, Wire(reply=b""))
    assert failure.outcome == "uncertain"
    assert (failure.failure["kind"], failure.failure["class"]) == ("transport", "RemoteDisconnected")


def test_an_upstream_http_error_keeps_its_status_and_never_reads_the_error_body(monkeypatch) -> None:
    body = json.dumps({"error": {"message": f"moderation flagged: {CANARY}", "metadata": {"flagged_input": CANARY}}}).encode()
    failure = _failure(monkeypatch, Wire(reply=http_reply(500, body)))
    assert (failure.outcome, failure.http_status, failure.failure) == ("uncertain", 500, {"kind": "http"})


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b"\xff\xfe\x00not utf-8", {"kind": "invalid_utf8"}),
        (b"{not json", {"kind": "invalid_json"}),
        (b"[1, 2]", {"kind": "schema", "reason": "upstream_response_was_not_an_object"}),
    ],
    ids=["invalid-utf8", "invalid-json", "not-an-object"],
)
def test_an_unreadable_reply_names_why(monkeypatch, body: bytes, expected: dict) -> None:
    failure = _failure(monkeypatch, Wire(reply=http_reply(200, body)))
    assert (failure.outcome, failure.failure) == ("uncertain", expected)


def test_a_schema_failure_names_the_module_reason_and_never_the_reply(monkeypatch) -> None:
    reply = {"id": "gen-1", "model": "cn/alpha", "choices": [{"message": {"content": CANARY}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1}}
    failure = _failure(monkeypatch, Wire(reply=http_reply(200, json.dumps(reply).encode())))
    assert failure.failure["kind"] == "schema"
    assert failure.failure["reason"].startswith("upstream_response_has_") and failure.failure["reason"] != "unrecognized"


def test_the_legacy_path_names_the_transport_class(monkeypatch) -> None:
    Wire(connect=ConnectionRefusedError(10061, CANARY)).install(monkeypatch)
    urllib.request.install_opener(None)
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url=_URL, sleep=lambda _s: None)
    with pytest.raises(Exception) as caught:
        client.create_message(model="cn/alpha", input_text="hi")
    assert "ConnectionRefusedError" in str(caught.value) and CANARY not in str(caught.value)


# --- The attempt record and the Gateway log line ------------------------------------------------------------------


def _haiku_post(upstream: RecordingUpstream) -> tuple[int, dict[str, Any]]:
    policy = model_policy(profiles.compose_test_profile_snapshot("qualification"))
    return handle_responses_request(
        authorization_header=AUTH,
        request_body={"model": HAIKU, "input": "hi", "route_binding": binding(policy.snapshot, model=HAIKU, input_text="hi", output_cap=32_768)},
        config=gateway_config(policy),
        upstream_client=upstream,
    )


def test_an_upstream_failure_cause_reaches_the_attempt_record_and_the_log_line() -> None:
    cause = {"kind": "transport", "class": "URLError", "cause": "ConnectionResetError", "errno": 10054}
    status, body = _haiku_post(RecordingUpstream(attempts=[UpstreamAttemptFailure("uncertain", failure=cause)]))

    assert (status, body["code"]) == (502, "UPSTREAM_ATTEMPT_UNCERTAIN")
    assert body["route_attempts"][0]["failure"] == cause
    line = json.loads(model_request_log_line("/v1/responses", status, body))
    assert line["route_attempts"][0]["failure"] == cause


class _UnknownCost(RecordingUpstream):
    def _result(self, model: str) -> ProviderMessageResult:
        base = super()._result(model)
        return ProviderMessageResult(**{**base.__dict__, "cost_usd": None, "resolved_provider": "Anthropic", "router_attempt": 1, "router_pipeline": ()})


def test_an_unverifiable_usage_keeps_its_reason_and_the_reply_ids() -> None:
    status, body = _haiku_post(_UnknownCost())

    assert (status, body["code"]) == (502, "UPSTREAM_ATTEMPT_UNCERTAIN")
    [attempt] = body["route_attempts"]
    assert attempt["failure"] == {"kind": "usage_contract", "reason": "cost_usd_must_be_non_null"}
    assert (attempt["provider_request_id"], attempt["router_pipeline"]) == ("gen-1", [])


# --- Content safety of everything persisted (Codex 3) -------------------------------------------------------------


def test_an_unknown_router_stage_type_is_recorded_as_unrecognized_and_still_refused() -> None:
    reply = {
        "id": "gen-1",
        "model": "cn/alpha",
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": "0.00001"},
        "openrouter_metadata": {
            "attempt": 1,
            "endpoints": {"total": 1, "available": [{"provider": "Anthropic", "model": HAIKU, "selected": True}]},
            "pipeline": [{"type": CANARY, "name": CANARY}, {"type": "guardrail", "name": "content-filter"}],
        },
    }
    result = parse_openai_chat_completion(reply, {}, requested_model="cn/alpha")
    assert result.router_pipeline == ("unrecognized", "guardrail")  # still non-empty, so the route still refuses it


def test_a_binding_with_unknown_fields_counts_them_and_never_echoes_their_names() -> None:
    raw = {"version": 1, "registry_hash": "x" * 64, "request_id": "r", "output_cap": 8, CANARY: 1, "private note": 2}
    with pytest.raises(BindingError) as caught:
        RouteBinding.from_wire(raw)
    assert (caught.value.code, str(caught.value.detail)) == ("BINDING_MALFORMED", "unknown fields (2)")


def test_the_log_line_is_redacted_as_a_whole_before_it_is_written() -> None:
    body = {"error": "x", "code": "X", "route_request_id": CANARY, "route_attempts": [{"attempt": 1, "gateway_request_id": CANARY}]}
    line = model_request_log_line("/v1/responses", 400, body)
    assert CANARY not in line and json.loads(line)["status"] == 400


# --- The server's log write (Codex 4 and 5, Fable F4 and F6) ------------------------------------------------------


@pytest.mark.parametrize(("raw", "error"), [(b"{not json", "invalid JSON"), (b"[1]", "request body must be a JSON object")], ids=["invalid", "array"])
def test_a_malformed_request_on_a_model_route_is_logged_too(capsys, raw: bytes, error: str) -> None:
    server, thread, host, port = _start_server(upstream_client=_SmokeUpstreamClient())
    try:
        status, _body = _post_json(host, port, "/v1/responses", body=raw)
    finally:
        _stop_server(server, thread)
    lines = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.startswith("{")]
    assert status == 400
    assert [(line["path"], line["status"], line["error"]) for line in lines] == [("/v1/responses", 400, error)]


class _BrokenStream:
    def write(self, _text: str) -> int:
        raise OSError(28, "No space left on device")

    def flush(self) -> None:
        raise OSError(28, "No space left on device")


def test_a_log_write_failure_never_breaks_the_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("optimus_gateway.server.handle_responses_request", lambda **_kwargs: (200, {"output_text": "ok"}))
    server, thread, host, port = _start_server(upstream_client=_SmokeUpstreamClient())
    try:
        monkeypatch.setattr(sys, "stderr", _BrokenStream())
        status, body = _post_json(host, port, "/v1/responses", body=json.dumps({"probe": True}))
    finally:
        monkeypatch.undo()
        _stop_server(server, thread)
    assert (status, body) == (200, {"output_text": "ok"})
