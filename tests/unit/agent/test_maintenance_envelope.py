"""Plan 12.2 Task 12 (closure release supplement, item 7): the complete wrapped maintenance request.

`ViewLimits.maintenance_input_tokens` (131072) bounds only the engine-assembled text. The host then
wraps it in the summary prompt and the Gateway sends it as one framed message with one output reserve
(8192). This proves, through the real host wrapper, the real `GatewaySummarizerCall` and the real
in-process enforced Gateway, that the actual complete input at the accepted maximum engine-text
envelope plus its reserve fits the enabled guard; that exact equality is admitted; and that one token
over is refused with zero upstream attempts and a zero-cost receipt. A 131072 engine-text pass alone is
not this proof. The estimator here is a test-only r=1 profile, not a verified route.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from context_engine import OrdinaryTurn
from context_engine.engine import maintenance_input
from context_engine.summary import build_summary_prompt
from optimus.context.maintenance import GatewaySummarizerCall
from optimus.gateway.disclosure import ContributorDisclosure
from optimus_model_policy import Message, PackedModelRequest, estimate_complete_input
from optimus_model_policy.binding import disclosure_key
from tests.unit.agent.test_route_binding import InProcessGateway, ScriptedUpstream, _client
from tests.unit.optimus_gateway.model_policy_support import SHARED_SECRET, VERIFIED_POLICY, verified_snapshot

ACCEPTED_MAINTENANCE_INPUT_TOKENS = 131_072  # accepted closure numeric set: engine-assembled text only
ACCEPTED_SUMMARY_OUTPUT_TOKENS = 8_192  # accepted summary output cap and maintenance reserve
MODEL = "cn/alpha"
SUMMARY = "\n".join(f"## {name}\n-" for name in ("Task", "Decisions", "Constraints and changes", "Open work", "Files", "Facts"))


def _engine_text_at_the_envelope() -> str:
    """The largest engine-assembled maintenance text the accepted limit admits under an r=1 engine
    estimator (one token per UTF-8 byte): exactly 131072 bytes, built by the engine's own assembler."""
    empty = len(maintenance_input(None, [OrdinaryTurn(seq=1, user_prompt="", plan_text="", completion_text="")]).encode("utf-8"))
    turn = OrdinaryTurn(seq=1, user_prompt="u" * (ACCEPTED_MAINTENANCE_INPUT_TOKENS - empty), plan_text="", completion_text="")
    text = maintenance_input(None, [turn])
    assert len(text.encode("utf-8")) == ACCEPTED_MAINTENANCE_INPUT_TOKENS
    return text


def _snapshot(tmp_path: Path, *, ceiling: int):
    policy = VERIFIED_POLICY.replace('tokens_per_byte: "0.5"', 'tokens_per_byte: "1"').replace(
        "context_ceiling_tokens: 262144", f"context_ceiling_tokens: {ceiling}"
    )
    directory = tmp_path / f"registry-{ceiling}"
    directory.mkdir()
    return verified_snapshot(directory, policy)


def _wire_tokens(snapshot, prompt: str) -> int:
    """The Gateway's own complete-input estimate: one framed user message, no tools."""
    profile = snapshot.policy.estimators[snapshot.policy.models[MODEL].route.estimator]
    request = PackedModelRequest(model_id=MODEL, messages=(Message(role="user", content=prompt),), tools_json="", output_cap=ACCEPTED_SUMMARY_OUTPUT_TOKENS)
    return estimate_complete_input(request, profile).tokens


def _summarize(snapshot, prompt: str):
    upstream = ScriptedUpstream(replies=[SUMMARY])
    gateway = InProcessGateway(snapshot, upstream)
    disclosure = ContributorDisclosure(snapshot=snapshot, key=disclosure_key(SHARED_SECRET), deliver_notice=lambda text: True)
    call = GatewaySummarizerCall(
        gateway_client=_client(gateway),
        model_id=MODEL,
        session_id="s",
        request_ids=lambda: "s:1:summary:1",
        bind=lambda request_id, input_text, output_cap: disclosure.binding(
            model_id=MODEL, request_id=request_id, input_text=input_text, output_cap=output_cap
        ),
    )
    return call(prompt=prompt, max_output_tokens=ACCEPTED_SUMMARY_OUTPUT_TOKENS), gateway, upstream


def test_the_wrapped_maintenance_input_at_the_accepted_envelope_fits_the_enabled_guard(tmp_path: Path) -> None:
    prompt = build_summary_prompt(_engine_text_at_the_envelope())
    snapshot = _snapshot(tmp_path, ceiling=262_144)
    tokens = _wire_tokens(snapshot, prompt)

    # The wrapper and framing are extra to the engine text, and the whole request still fits.
    assert tokens > ACCEPTED_MAINTENANCE_INPUT_TOKENS
    assert tokens + ACCEPTED_SUMMARY_OUTPUT_TOKENS <= 262_144
    response, gateway, upstream = _summarize(snapshot, prompt)
    assert [status for status, _ in gateway.replies] == [200]
    [sent] = upstream.calls
    assert (sent["input_text"], sent["max_tokens"]) == (prompt, ACCEPTED_SUMMARY_OUTPUT_TOKENS)  # the complete wrapped input, one reserve
    assert response.finish_status == "stop" and [attempt.outcome for attempt in response.attempts] == ["completed"]


@pytest.mark.parametrize(("slack", "admitted"), [(0, True), (-1, False)], ids=["equality", "one-over"])
def test_equality_is_admitted_and_one_over_is_refused_with_zero_upstream_attempts(tmp_path: Path, slack: int, admitted: bool) -> None:
    prompt = build_summary_prompt(_engine_text_at_the_envelope())
    probe = _snapshot(tmp_path, ceiling=262_144)
    exact = _wire_tokens(probe, prompt) + ACCEPTED_SUMMARY_OUTPUT_TOKENS  # usable input == the wrapped input exactly
    snapshot = _snapshot(tmp_path, ceiling=exact + slack)

    response, gateway, upstream = _summarize(snapshot, prompt)

    [(status, body)] = gateway.replies
    if admitted:
        assert status == 200 and len(upstream.calls) == 1
        assert [attempt.outcome for attempt in response.attempts] == ["completed"]
    else:
        assert status == 400 and body["code"] == "INPUT_EXCEEDS_CAPACITY"
        assert upstream.calls == []  # zero upstream attempts
        assert [(attempt.outcome, attempt.cost_usd) for attempt in response.attempts] == [("rejected", Decimal("0"))]
        assert response.text is None
