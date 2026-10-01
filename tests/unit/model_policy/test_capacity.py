"""Plan 12.2 Task 4: the complete-request capacity contract (spec 9.4, Task 1 contracts §4).

    effective_total = min(262144, verified_route_window)   # smallest window in the route allow-set
    usable_input    = effective_total - output_reserve       # the reserve is counted once
    complete_input_estimate <= usable_input                  # equality admitted
    0 < output_reserve <= verified_route_max_output

The estimate is taken from the final packed request (messages, framing, tool material), never from a
caller-declared token count. Decisions carry token fields only, never money.
"""

from __future__ import annotations

import json
import math
import textwrap
from dataclasses import fields
from pathlib import Path

import pytest

from optimus.agent.planning_loop import PLANNING_NEW_READ_MAX_BYTES, PLANNING_OBSERVATION_MAX_BYTES
from optimus.agent.prompts import _MCP_EVIDENCE_MAX_BYTES
from optimus.agent.workspace_context import DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES
from optimus_model_policy import (
    CapacityDecision,
    Message,
    PackedModelRequest,
    estimate_complete_input,
    guard_request,
    load_registry,
)

_POLICY = textwrap.dedent(
    """\
    schema_version: 1
    policy_version: "capacity-fixture"
    fixture: true
    context_ceiling_tokens: 262144
    output_reserve_tokens: {implementer: 16384}
    estimators:
      half-token-per-byte:
        method: utf8-bytes-ratio
        tokens_per_byte: "0.5"
        per_message_tokens: 8
        fixed_tokens: 64
        verified: true
      unverified-estimator:
        method: utf8-bytes-ratio
        tokens_per_byte: "0.25"
        per_message_tokens: 4
        fixed_tokens: 16
        verified: false
    role_price_blends: {}
    alerts: {thresholds_usd: []}
    models:
      cn/alpha:
        origin: china
        tier: cheap
        prices: {input_usd_per_million: "0.10", output_usd_per_million: "0.40"}
        data_use: {provider_may_train_on_inputs: "no", disclosure: none}
        capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [high]}
        default_reasoning: high
        route:
          estimator: half-token-per-byte
          endpoints:
            - {provider: alpha-cloud, quantization: fp8, context_window_tokens: 300000, max_output_tokens: 32768, verified: true}
      us/beta:
        origin: non-china
        tier: cheap
        prices: {input_usd_per_million: "0.20", output_usd_per_million: "0.80"}
        data_use: {provider_may_train_on_inputs: "no", disclosure: none}
        capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [high]}
        default_reasoning: high
        route:
          estimator: unverified-estimator
          endpoints:
            - {provider: beta-ai, quantization: null, context_window_tokens: 262144, max_output_tokens: 65536, verified: true}
    roles:
      medium: [cn/alpha, us/beta]
    """
)

_RESERVE = 16384
_FIXED = 64
_PER_MESSAGE = 8


@pytest.fixture
def snapshot(tmp_path: Path):
    path = tmp_path / "policy.yaml"
    path.write_text(_POLICY, encoding="utf-8")
    return load_registry(path, None)


def _request(text: str, *, model: str = "cn/alpha", output_cap: int = _RESERVE, tools_json: str = "") -> PackedModelRequest:
    return PackedModelRequest(
        model_id=model,
        messages=(Message(role="user", content=text),),
        tools_json=tools_json,
        output_cap=output_cap,
    )


def _ascii_for_tokens(tokens: int) -> str:
    """One user message whose estimate under the 0.5 tokens/byte fixture is exactly ``tokens``."""
    return "a" * ((tokens - _FIXED - _PER_MESSAGE) * 2)


def test_input_exactly_at_usable_capacity_is_admitted_and_one_more_token_is_refused(snapshot) -> None:
    usable = 262144 - _RESERVE  # the 300000-token window is capped at the 262144 ceiling

    at_limit = guard_request(_request(_ascii_for_tokens(usable)), snapshot, snapshot.effective_hash)
    over = guard_request(_request(_ascii_for_tokens(usable) + "aa"), snapshot, snapshot.effective_hash)

    assert at_limit == CapacityDecision(
        allowed=True,
        reason=None,
        input_tokens=usable,
        output_reserve=_RESERVE,
        usable_input=usable,
        effective_total=262144,
    )
    assert over.allowed is False
    assert over.reason == "INPUT_EXCEEDS_CAPACITY"
    assert over.input_tokens == usable + 1


def test_the_output_reserve_is_counted_exactly_once(snapshot) -> None:
    for reserve in (1, 4096, 32768):
        decision = guard_request(_request("x", output_cap=reserve), snapshot, snapshot.effective_hash)
        assert decision.usable_input == decision.effective_total - reserve
        assert decision.input_tokens == estimate_complete_input(_request("x"), snapshot.policy.estimators["half-token-per-byte"]).tokens


@pytest.mark.parametrize(("cap", "reason"), [(0, "OUTPUT_RESERVE_INVALID"), (32769, "OUTPUT_RESERVE_EXCEEDS_ROUTE")])
def test_an_output_reserve_the_route_cannot_honour_is_refused(snapshot, cap: int, reason: str) -> None:
    decision = guard_request(_request("x", output_cap=cap), snapshot, snapshot.effective_hash)
    assert (decision.allowed, decision.reason) == (False, reason)


def test_every_endpoint_in_the_allow_set_bounds_the_request(tmp_path: Path) -> None:
    anchor = "        - {provider: alpha-cloud, quantization: fp8, context_window_tokens: 300000, max_output_tokens: 32768, verified: true}\n"
    assert anchor in _POLICY, "fixture edit anchor not found"
    text = _POLICY.replace(
        anchor,
        anchor + "        - {provider: alpha-edge, quantization: fp8, context_window_tokens: 250000, max_output_tokens: 20000, verified: true}\n",
    )
    path = tmp_path / "two-endpoints.yaml"
    path.write_text(text, encoding="utf-8")
    snapshot = load_registry(path, None)

    decision = guard_request(_request("x"), snapshot, snapshot.effective_hash)
    assert decision.effective_total == 250000, "the smallest window in the allow-set governs"
    too_big = guard_request(_request("x", output_cap=20001), snapshot, snapshot.effective_hash)
    assert too_big.reason == "OUTPUT_RESERVE_EXCEEDS_ROUTE", "the smallest max output governs"


@pytest.mark.parametrize(
    ("model", "approved", "reason"),
    [
        ("claude-haiku", True, "UNKNOWN_MODEL"),
        ("vendor/anything", True, "UNKNOWN_MODEL"),
        ("us/beta", True, "ESTIMATOR_UNVERIFIED"),
        ("cn/alpha", False, "SNAPSHOT_NOT_APPROVED"),
    ],
)
def test_unknown_models_aliases_estimators_and_unapproved_snapshots_are_refused(snapshot, model, approved, reason) -> None:
    approved_hash = snapshot.effective_hash if approved else "0" * 64
    decision = guard_request(_request("x", model=model), snapshot, approved_hash)
    assert (decision.allowed, decision.reason) == (False, reason)


def test_an_unknown_estimator_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text(_POLICY.replace("estimator: half-token-per-byte", "estimator: missing-estimator"), encoding="utf-8")
    snapshot = load_registry(path, None)
    decision = guard_request(_request("x"), snapshot, snapshot.effective_hash)
    assert (decision.allowed, decision.reason) == (False, "ESTIMATOR_UNKNOWN")


def test_framing_unicode_escaped_json_and_tool_material_all_count(snapshot) -> None:
    profile = snapshot.policy.estimators["half-token-per-byte"]

    def tokens(request: PackedModelRequest) -> int:
        return estimate_complete_input(request, profile).tokens

    one = _request("hello")
    two = PackedModelRequest(
        model_id="cn/alpha",
        messages=(Message(role="system", content=""), Message(role="user", content="hello")),
        tools_json="",
        output_cap=_RESERVE,
    )
    assert tokens(two) == tokens(one) + _PER_MESSAGE, "each message's framing counts"

    assert tokens(_request("漢" * 10)) == tokens(_request("a" * 30)), "UTF-8 bytes, not characters"

    raw = 'say "hi" \\ there'
    escaped = json.dumps({"text": raw})
    assert tokens(_request("", tools_json=escaped)) == _FIXED + _PER_MESSAGE + math.ceil(len(escaped.encode()) * 0.5)
    assert len(escaped) > len(raw), "the final serialized (escaped) form is what is counted"

    future_tools = json.dumps([{"name": "read_file", "parameters": {"path": {"type": "string"}}}] * 20)
    assert tokens(_request("hello", tools_json=future_tools)) > tokens(one), "tool material counts"


def test_decisions_and_estimates_carry_no_money(snapshot) -> None:
    decision = guard_request(_request("x"), snapshot, snapshot.effective_hash)
    estimate = estimate_complete_input(_request("x"), snapshot.policy.estimators["half-token-per-byte"])
    names = {field.name for field in fields(decision)} | {field.name for field in fields(estimate)}
    assert not {name for name in names if "cost" in name or "usd" in name or "price" in name}


# --- D7 / ADR-014 full-floor harness (offline, fixture estimators) --------------------------------


def _full_floor_request(*, model: str) -> PackedModelRequest:
    """The largest absent-engine request: a full 524288-byte English/code history, the maximum
    workspace context, carried observations, a new read and MCP evidence, with system framing."""
    unit = "def add(a, b):\n    return a + b  # adds two numbers, then the result is checked.\n"
    history = (unit * (524288 // len(unit) + 1))[:524288]
    material = "w" * (
        DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES + PLANNING_OBSERVATION_MAX_BYTES + PLANNING_NEW_READ_MAX_BYTES + _MCP_EVIDENCE_MAX_BYTES
    )
    return PackedModelRequest(
        model_id=model,
        messages=(
            Message(role="system", content="You are the Optimus planner."),
            Message(role="user", content=history),
            Message(role="user", content=material),
        ),
        tools_json="",
        output_cap=_RESERVE,
    )


def test_the_full_floor_harness_reports_a_route_floor_conflict_instead_of_exempting(tmp_path: Path) -> None:
    """With a deliberately pessimistic fixture estimator (0.5 tokens/byte) the full floor cannot fit:
    the guard refuses and names the capacity reason. It never exempts the request to make it pass.
    Real per-route admission needs measured estimators and reserves (D1-D3), which is CP4 work;
    this harness is what that evidence will run through."""
    path = tmp_path / "policy.yaml"
    path.write_text(_POLICY, encoding="utf-8")
    snapshot = load_registry(path, None)

    decision = guard_request(_full_floor_request(model="cn/alpha"), snapshot, snapshot.effective_hash)

    assert (decision.allowed, decision.reason) == (False, "INPUT_EXCEEDS_CAPACITY")
    assert decision.input_tokens > 524288 // 2


def test_the_full_floor_fits_a_route_whose_estimator_allows_it(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text(_POLICY.replace('tokens_per_byte: "0.5"', 'tokens_per_byte: "0.3"'), encoding="utf-8")
    snapshot = load_registry(path, None)

    decision = guard_request(_full_floor_request(model="cn/alpha"), snapshot, snapshot.effective_hash)

    assert decision.allowed is True
    assert decision.input_tokens <= decision.usable_input
