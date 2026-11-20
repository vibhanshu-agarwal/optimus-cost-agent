"""CP4 review 10, design R (operator-accepted 2026-11-19): memory calls are sent with no reasoning.

Haiku 5.5 thinks adaptively by default and its thinking shares the 512-token memory cap, so an extraction could end at the
cap before any text (CP4 ON P7). The registry approves one purpose-scoped setting per memory purpose; the host binds it with
its purpose; the Gateway admits only that exact pair, sends it upstream and covers it in the Contributor disclosure; and each
call's receipt records the reasoning it was sent with. Planning and context summaries keep the entry's default.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from optimus.context import memory_extraction as mx
from optimus.context.assembly import AttachedTurn
from optimus.context.maintenance import HostMaintenance, MaintenanceIdentity, SummarizerRoute, gateway_summarizer_factory
from optimus.gateway.disclosure import ContributorDisclosure
from optimus.usage.capture_events import receipt_payload
from optimus.usage.turn_settlement import receipt_from_maintenance
from optimus_gateway.responses import handle_responses_request
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.binding import disclosure_key, packaged_defaults, trusted_snapshot
from optimus_model_policy.registry import MEMORY_PURPOSES, RegistryError, Role, load_registry, reasoning_for
from optimus_model_policy.validation import select_eligible_models
from tests.unit.agent.test_context_maintenance import SANITIZER, _request
from tests.unit.agent.test_gateway_refusal_diagnosis import Replying
from tests.unit.agent.test_route_binding import InProcessGateway, ScriptedUpstream, _client
from tests.unit.optimus_gateway.model_policy_support import (
    AUTH,
    SHARED_SECRET,
    VERIFIED_POLICY,
    binding,
    gateway_config,
    model_policy,
    verified_snapshot,
)

HAIKU = "anthropic/claude-haiku-5.5"
MEMORY = sorted(MEMORY_PURPOSES)


def _attached():
    return profiles.compose_test_profile_snapshot("attached")


# --- The registry -------------------------------------------------------------------------------------------------


def test_the_registry_memory_purposes_are_the_extractors_own() -> None:
    assert set(MEMORY_PURPOSES) == {mx.USER_PURPOSE, mx.AGENT_PURPOSE, mx.COMPACTION_PURPOSE}
    assert mx.MAX_OUTPUT_TOKENS == 512  # the frozen cap is unchanged


@pytest.mark.parametrize("composition", ["shipped", "attached", "qualification"])
def test_every_haiku_composition_sends_memory_calls_without_reasoning_and_everything_else_at_low(composition: str) -> None:
    snapshot = trusted_snapshot() if composition == "shipped" else profiles.compose_test_profile_snapshot(composition)
    entry = snapshot.policy.models[HAIKU]
    assert dict(entry.purpose_reasoning) == dict.fromkeys(MEMORY_PURPOSES, "none")
    assert [reasoning_for(entry, purpose) for purpose in MEMORY] == ["none"] * 3
    assert reasoning_for(entry, None) == reasoning_for(entry, "context.summary") == reasoning_for(entry, "agent.plan") == "low"
    # The accepted summary-quality receipt is for `low` context summaries only, never evidence for `none`.
    assert [receipt.reasoning for receipt in entry.summary_receipts] in ([], ["low"])


def test_an_entry_without_purpose_reasoning_keeps_its_canonical_form() -> None:
    entry = trusted_snapshot().policy.models["qwen/qwen3.7-flash"]
    assert entry.purpose_reasoning == {} and "purpose_reasoning" not in entry.model_dump(mode="json")
    assert "purpose_reasoning" in trusted_snapshot().policy.models[HAIKU].model_dump(mode="json")


def _override(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "override.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_only_memory_purposes_may_carry_their_own_reasoning(tmp_path: Path) -> None:
    override = _override(tmp_path, "models:\n  anthropic/claude-haiku-5.5:\n    purpose_reasoning: {context_summary: none}\n")
    with pytest.raises(RegistryError) as caught:
        load_registry(packaged_defaults(), override)
    assert caught.value.code == "SCHEMA_INVALID"


def test_a_purpose_setting_the_route_does_not_support_makes_the_model_ineligible(tmp_path: Path) -> None:
    override = _override(tmp_path, "models:\n  anthropic/claude-haiku-5.5:\n    capabilities: {reasoning_levels: [low, medium, high, xhigh, max]}\n")
    snapshot = load_registry(packaged_defaults(), override)
    assert HAIKU not in select_eligible_models(snapshot, Role.SUMMARIZER)
    assert HAIKU in select_eligible_models(trusted_snapshot(), Role.SUMMARIZER)


# --- The Gateway admits only the exact pair -----------------------------------------------------------------------


def _post(snapshot, upstream, **scoped: Any) -> tuple[int, dict[str, Any]]:
    wire = {**binding(snapshot, model=HAIKU, input_text="hi", output_cap=512), **scoped}
    return handle_responses_request(
        authorization_header=AUTH, request_body={"model": HAIKU, "input": "hi", "route_binding": wire},
        config=gateway_config(model_policy(snapshot)), upstream_client=upstream,
    )  # fmt: skip


@pytest.mark.parametrize("purpose", MEMORY)
def test_a_memory_purpose_bound_with_none_is_sent_without_reasoning(purpose: str) -> None:
    upstream = Replying()
    status, _body = _post(_attached(), upstream, purpose=purpose, reasoning="none")
    assert status == 200 and [call["reasoning"] for call in upstream.calls] == ["none"]


def test_an_unscoped_request_keeps_the_default_reasoning() -> None:
    upstream = Replying()
    assert _post(_attached(), upstream)[0] == 200 and [call["reasoning"] for call in upstream.calls] == ["low"]


@pytest.mark.parametrize(
    ("purpose", "reasoning"),
    [("context.summary", "none"), ("agent.plan", "none"), ("memory.extract_user", "low"), ("memory.extract_user", "high")],
)
def test_any_other_pair_is_refused_before_dispatch(purpose: str, reasoning: str) -> None:
    upstream = Replying()
    status, body = _post(_attached(), upstream, purpose=purpose, reasoning=reasoning)
    assert (status, body["code"]) == (400, "REASONING_NOT_APPROVED") and upstream.calls == []


@pytest.mark.parametrize(
    "scoped",
    [
        {"purpose": "memory.extract_user"},
        {"reasoning": "none"},
        {"purpose": "Memory", "reasoning": "none"},
        {"purpose": "memory.extract_user", "reasoning": "off"},
        {"purpose": "memory.extract_user", "reasoning": []},  # Codex review 11: never a TypeError past the structured refusal
        {"purpose": "memory.extract_user", "reasoning": {}},
        {"purpose": ["memory.extract_user"], "reasoning": "none"},
        {"purpose": {}, "reasoning": "none"},
    ],
)
def test_a_malformed_scoped_binding_is_refused(scoped: dict[str, str]) -> None:
    upstream = Replying()
    status, body = _post(_attached(), upstream, **scoped)
    assert (status, body["code"]) == (400, "BINDING_MALFORMED") and upstream.calls == []


def test_a_model_without_purpose_settings_refuses_a_scoped_binding(tmp_path: Path) -> None:
    snapshot = verified_snapshot(tmp_path)
    wire = {**binding(snapshot, input_text="hi"), "purpose": "memory.extract_user", "reasoning": "high"}
    upstream = ScriptedUpstream()
    status, body = handle_responses_request(
        authorization_header=AUTH, request_body={"model": "cn/alpha", "input": "hi", "route_binding": wire},
        config=gateway_config(model_policy(snapshot)), upstream_client=upstream,
    )  # fmt: skip
    assert (status, body["code"]) == (400, "REASONING_NOT_APPROVED") and upstream.calls == []


# --- The Contributor disclosure covers the bound reasoning --------------------------------------------------------

_CONTRIBUTOR = VERIFIED_POLICY.replace(
    "    data_use: {provider_may_train_on_inputs: \"yes\", disclosure: contributor}\n"
    "    capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [high]}\n"
    "    default_reasoning: high\n",
    "    data_use: {provider_may_train_on_inputs: \"yes\", disclosure: contributor}\n"
    "    capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [none, high]}\n"
    "    default_reasoning: high\n"
    "    purpose_reasoning: {memory.extract_user: none}\n",
)


def _contributor_post(snapshot, wire: dict[str, Any], upstream) -> tuple[int, dict[str, Any]]:
    return handle_responses_request(
        authorization_header=AUTH, request_body={"model": "us/contrib", "input": "hi", "route_binding": wire},
        config=gateway_config(model_policy(snapshot)), upstream_client=upstream,
    )  # fmt: skip


def test_the_disclosure_digest_binds_the_purpose_reasoning(tmp_path: Path) -> None:
    assert _CONTRIBUTOR != VERIFIED_POLICY
    snapshot = verified_snapshot(tmp_path, _CONTRIBUTOR)
    disclosure = ContributorDisclosure(snapshot=snapshot, key=disclosure_key(SHARED_SECRET), deliver_notice=lambda _text: True)

    def bound(purpose: str | None) -> dict[str, Any]:
        made = disclosure.binding(model_id="us/contrib", request_id="r-1", input_text="hi", output_cap=16384, purpose=purpose)
        assert made is not None
        return made.to_wire()

    scoped, plain = bound("memory.extract_user"), bound("context.summary")
    assert (scoped["purpose"], scoped["reasoning"]) == ("memory.extract_user", "none") and "reasoning" not in plain
    upstream = ScriptedUpstream()
    assert _contributor_post(snapshot, scoped, upstream)[0] == 200 and upstream.calls[-1]["reasoning"] == "none"
    assert _contributor_post(snapshot, plain, upstream)[0] == 200 and upstream.calls[-1]["reasoning"] == "high"
    # Swapping the reasoning without a disclosure issued for it fails the digest check: nothing more is sent.
    sent = len(upstream.calls)
    lowered = {key: value for key, value in scoped.items() if key not in {"purpose", "reasoning"}}
    raised = {**plain, "purpose": "memory.extract_user", "reasoning": "none"}
    for wire in (lowered, raised):
        status, body = _contributor_post(snapshot, wire, upstream)
        assert (status, body["code"]) == (400, "DISCLOSURE_INVALID")
    assert len(upstream.calls) == sent


# --- Each call's receipt records the reasoning it was sent with ---------------------------------------------------


def _summarizer():
    snapshot = _attached()
    entry = snapshot.policy.models[HAIKU]
    route = SummarizerRoute(model_id=HAIKU, role="summarizer", route=entry.route.providers, reasoning="low", quantizations=entry.route.quantizations)
    identity = MaintenanceIdentity(
        session_id="s", turn_seq=1, model_id=HAIKU, role="summarizer", route=route.route, reasoning="low",
        quantizations=route.quantizations, strategy="test", revision_digest="rev", registry_hash=snapshot.effective_hash,
    )  # fmt: skip
    upstream = Replying()
    factory = gateway_summarizer_factory(
        gateway_client=_client(InProcessGateway(snapshot, upstream)), route=route, snapshot=snapshot, disclosure_key=disclosure_key(SHARED_SECRET)
    )
    return factory(identity, lambda _text: True), identity, upstream


def test_each_memory_call_records_none_through_the_production_receipt_path() -> None:
    call, identity, upstream = _summarizer()
    turn = object.__new__(AttachedTurn)  # only the memory hooks' own fields: the bound call, identity and receipt sink
    receipts: list[Any] = []
    turn._memory_call, turn._memory_identity, turn._receipt_sink = call, identity, receipts.append  # type: ignore[method-assign]
    hooks = turn.memory_hooks()
    assert hooks is not None
    bound, record = hooks

    for purpose in MEMORY:
        response = bound(prompt="Extract.", max_output_tokens=512, purpose=purpose)
        for attempt in response.attempts:
            record("s:1", purpose, attempt, response.finish_status)

    assert [sent["reasoning"] for sent in upstream.calls] == ["none"] * 3
    stage = [receipt_from_maintenance(receipt) for receipt in receipts]
    assert [(receipt.purpose, receipt.reasoning, receipt.outcome) for receipt in stage] == [(purpose, "none", "completed") for purpose in MEMORY]
    assert identity.reasoning == "low"  # the shared turn identity is never changed
    [user] = [receipt for receipt in stage if receipt.purpose == "memory.extract_user"]
    payload = receipt_payload(user, epoch_id="e-1", late=False, purpose=user.purpose)
    assert (payload["purpose"], payload["reasoning"]) == ("memory.extract_user", "none")  # what capture persists


def test_a_context_summary_keeps_the_route_default_in_its_receipt() -> None:
    call, identity, upstream = _summarizer()
    receipts: list[Any] = []
    host = HostMaintenance(call=call, sanitizer=SANITIZER, identity=identity, record_receipt=receipts.append, cancelled=lambda: False)
    host(_request(input_text="earlier turns", max_output_tokens=8192))
    assert [sent["reasoning"] for sent in upstream.calls] == ["low"]
    assert [receipt_from_maintenance(receipt).reasoning for receipt in receipts] == ["low"]
    assert all(receipt.reasoning is None for receipt in receipts)  # no call-level setting: the turn identity's applies
    assert Decimal("0") <= receipts[0].cost_usd
    assert dataclasses.replace(identity) == identity
