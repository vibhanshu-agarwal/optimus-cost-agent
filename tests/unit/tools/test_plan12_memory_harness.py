"""Plan 12.5 Task 3: arm D's narrow Gateway adapter and the harness-choice record.

The Gateway replies here are a DOUBLE: no model or network runs. Their shape comes from the
Gateway's own reply builders and the requests are parsed by its real validators, so these
tests prove adapter behaviour only, never native harness, transport or model compatibility.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from optimus_gateway.chat_completions import _build_chat_completions_success
from optimus_gateway.models import flatten_messages_to_input_text, validate_chat_completions_envelope
from optimus_gateway.responses import _attempt_record, _gateway_usage, format_cost_usd
from optimus_gateway.upstream_client import ProviderMessageResult
from optimus_model_policy.binding import ATTEMPT_OUTCOMES, RouteBinding
from tools.plan12_memory.contracts import GatewayRoute
from tools.plan12_memory.harness import _POSSIBLY_BILLED, _UNBILLED, build_request, encode_transcript, parse_reply

ROOT = Path(__file__).resolve().parents[3]
ROUTE = GatewayRoute(model_id="vendor/model-x", registry_hash="ab" * 32, output_cap=4096)
MESSAGES = [
    {"role": "system", "content": "You are a helpful assistant.", "extra": {}},
    {"role": "user", "content": "Find where the session options are built."},
    {"role": "assistant", "content": "THOUGHT: list files\n\n```mswea_bash_command\nls\n```", "extra": {"actions": []}},
    {"role": "user", "content": "<returncode>0</returncode>\n<output>\nsrc\n</output>"},
]


def _double_reply(*outcomes: str, status: int = 200, usage_for: int | None = None, code: str | None = None) -> dict[str, Any]:
    """DOUBLE: a Gateway reply built by the Gateway's own builders from made-up provider values."""
    ids = [f"gw-{n:032x}" for n in range(1, len(outcomes) + 1)]
    attempts = [_attempt_record(n, ids[n - 1], outcome) for n, outcome in enumerate(outcomes, 1)]
    result = ProviderMessageResult(
        message_id="gen-1", output_text="THOUGHT: done\n\n```mswea_bash_command\necho COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n```",
        input_tokens=1200, output_tokens=80, total_tokens=1280, billing_units=1280, cost_usd=Decimal("0.0123"),
        provider="openrouter", resolved_provider="vendor", requested_model=ROUTE.model_id, resolved_model=ROUTE.model_id,
        model_version=None, cache_hit=False, cached_tokens=0, reasoning_tokens=None, finish_reason="stop",
    )
    usage = None
    if usage_for is not None:
        usage = _gateway_usage(config=SimpleNamespace(provider="openrouter"), model=ROUTE.model_id,  # type: ignore[arg-type]
                               provider_result=result, gateway_request_id=ids[usage_for])
        usage.update(route_request_id="case-L01:1", attempt=usage_for + 1, cost_usd=format_cost_usd(result.cost_usd))
    if status == 200:
        return {**_build_chat_completions_success(provider_result=result, gateway_usage=usage or {}), "route_attempts": attempts}
    body: dict[str, Any] = {"error": "refused", "code": code, "route_request_id": "case-L01:1", "route_attempts": attempts, "retryable": False}
    return body if usage is None else body | {"gateway_usage": usage}


def test_request_passes_the_real_gateway_envelope_and_binding() -> None:
    body = build_request(ROUTE, MESSAGES, request_id="case-L01:1")

    model, messages, metadata = validate_chat_completions_envelope(body)
    binding = RouteBinding.from_wire(body["route_binding"])

    assert (model, metadata) == (ROUTE.model_id, None)
    assert flatten_messages_to_input_text(messages) == encode_transcript(MESSAGES)
    assert (binding.registry_hash, binding.request_id, binding.output_cap, binding.disclosure) == (
        ROUTE.registry_hash, "case-L01:1", 4096, None)
    assert set(body) == {"model", "messages", "route_binding"}  # no credential and no tools field


def test_roles_survive_the_gateway_flattening() -> None:
    plain = flatten_messages_to_input_text(MESSAGES)  # what the Gateway does to role-tagged messages
    sent = flatten_messages_to_input_text(build_request(ROUTE, MESSAGES, request_id="r")["messages"])

    assert "THOUGHT: list files" in plain and "<assistant>" not in plain
    starts = [sent.index(f"<{role}>\n") for role in ("system", "user", "assistant")]
    assert starts == sorted(starts)
    assert sent.count("<user>\n") == 2 and sent.endswith("</user>")


@pytest.mark.parametrize(
    "messages",
    [[], [{"role": "tool", "content": "x"}], [{"role": "exit", "content": "x"}], [{"role": "user", "content": [{"type": "text", "text": "x"}]}]],
    ids=["empty", "tool-role", "exit-role", "multimodal"],
)
def test_unsupported_messages_are_refused(messages: list[dict[str, Any]]) -> None:
    with pytest.raises(ValueError):
        encode_transcript(messages)


def test_attempt_outcomes_match_the_gateway() -> None:
    assert _UNBILLED | _POSSIBLY_BILLED == ATTEMPT_OUTCOMES
    assert not _UNBILLED & _POSSIBLY_BILLED


def test_success_settles_the_completed_attempt_and_skips_the_unbilled_one() -> None:
    reply = parse_reply(200, _double_reply("not_sent", "completed", usage_for=1), route=ROUTE)

    assert reply.content is not None and reply.content.endswith("```")
    assert (reply.finish_reason, reply.error_code) == ("stop", None)
    [receipt] = reply.attempts
    assert receipt.attempt_id == receipt.gateway_request_id == f"gw-{2:032x}"
    assert (receipt.state, receipt.input_tokens, receipt.output_tokens, receipt.cache_tokens) == ("settled", 1200, 80, 0)
    assert receipt.reasoning_tokens is None  # unreported stays unknown, never zero
    assert receipt.cost_usd == Decimal("0.0123")
    assert receipt.price_snapshot_id == f"registry:{ROUTE.registry_hash}"


def test_uncertain_or_unmatched_attempts_stay_unknown() -> None:
    failed = parse_reply(502, _double_reply("uncertain", status=502, code="UPSTREAM_ATTEMPT_UNCERTAIN"), route=ROUTE)
    body = _double_reply("completed", usage_for=0)
    body["gateway_usage"]["gateway_request_id"] = "gw-other"
    [unmatched] = parse_reply(200, body, route=ROUTE).attempts

    assert (failed.content, failed.error_code) == (None, "UPSTREAM_ATTEMPT_UNCERTAIN")
    [uncertain] = failed.attempts
    for receipt in (uncertain, unmatched):
        assert (receipt.state, receipt.cost_usd, receipt.input_tokens, receipt.price_snapshot_id) == ("intent_only", None, None, None)


def test_billed_refusal_keeps_its_receipt() -> None:
    reply = parse_reply(422, _double_reply("completed", status=422, usage_for=0, code="FINISH_STATUS_REFUSED"), route=ROUTE)

    assert (reply.content, reply.error_code) == (None, "FINISH_STATUS_REFUSED")
    assert [(r.state, r.cost_usd) for r in reply.attempts] == [("settled", Decimal("0.0123"))]


@pytest.mark.parametrize(
    ("status", "body", "code"),
    [
        (401, {"error": "unauthorized"}, "HTTP_401"),
        (400, {"error": "model is required"}, "HTTP_400"),
        (409, {"error": "x", "code": "REGISTRY_HASH_MISMATCH", "retryable": False, "route_attempts": []}, "REGISTRY_HASH_MISMATCH"),
    ],
    ids=["unauthorized", "envelope", "policy-refusal"],
)
def test_refusals_before_routing_carry_no_receipt(status: int, body: dict[str, Any], code: str) -> None:
    reply = parse_reply(status, body, route=ROUTE)

    assert (reply.error_code, reply.attempts, reply.content) == (code, (), None)


_BREAKS: dict[str, Callable[[dict[str, Any]], object]] = {
    "no-attempts": lambda b: b.pop("route_attempts"),
    "no-choices": lambda b: b.pop("choices"),
    "null-content": lambda b: b["choices"][0]["message"].update(content=None),
    "unknown-outcome": lambda b: b["route_attempts"][0].update(outcome="lost"),
    "no-attempt-id": lambda b: b["route_attempts"][0].pop("gateway_request_id"),
    "text-tokens": lambda b: b["gateway_usage"].update(input_tokens="1200"),
    "bool-tokens": lambda b: b["gateway_usage"].update(output_tokens=True),
    "negative-tokens": lambda b: b["gateway_usage"].update(input_tokens=-1),
    "bad-cost": lambda b: b["gateway_usage"].update(cost_usd="abc"),
    "nan-cost": lambda b: b["gateway_usage"].update(cost_usd="NaN"),
    "float-cost": lambda b: b["gateway_usage"].update(cost_usd=0.0123),
}


@pytest.mark.parametrize("break_it", _BREAKS.values(), ids=_BREAKS.keys())
def test_malformed_replies_raise(break_it: Callable[[dict[str, Any]], object]) -> None:
    body = _double_reply("completed", usage_for=0)
    break_it(body)

    with pytest.raises(ValueError):
        parse_reply(200, body, route=ROUTE)


def test_harness_choice_pins_one_candidate_and_claims_no_run() -> None:
    record = json.loads((ROOT / "reports/plan12-memory-evaluation/harness-choice.json").read_text(encoding="utf-8"))

    assert re.fullmatch(r"git:[0-9a-f]{40}", record["selected"]["commit"])
    assert record["status"]["native_compatibility"] == "UNRUN"
    obligations = record["runtime_obligations"]
    assert obligations and all(item["status"] == "UNRUN" and item["acceptance_check"] for item in obligations)
    assert (ROOT / record["adapter"]["module"]).is_file()
