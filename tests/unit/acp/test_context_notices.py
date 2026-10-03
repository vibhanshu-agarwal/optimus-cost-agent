"""Plan 12.2 Task 10: truthful live notices and meters for attached sessions (design spec 8.4, 10).

- The sliding notice is sent once, on the first admitted turn after a committed switch to sliding,
  live-only and confirmed by an actual flush; switching away before a prompt cancels it. A fallback
  is disclosed separately. No notice enters the canonical history.
- An attached session's storage notices name storage, not the model's context.
- The attached meter reports the largest complete planning/answer input actually dispatched in the
  turn against that request's usable capacity. Summarizer calls are excluded, and a turn that sent
  nothing produces no reading. The engine-absent floor meter is unchanged.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from optimus.acp.errors import AcpOutboundError
from optimus.acp.session_config import SLIDING_ACTIVE_TEXT, STRATEGY_CONFIG_ID
from optimus.acp.spec import (
    ATTACHED_STORAGE_WARNING_TEXT,
    CAPACITY_WARNING_TEXT,
    CONTEXT_FALLBACK_TEXT,
)
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.runtime.modes import ExecutionMode
from tests.unit.acp.test_context_engine_admission import (
    FlakyEngine,
    SummarizerCall,
    estimate,
    make_adapter,
    make_attachment,
    new_session,
    prompt,
    rpc,
    session_of,
    texts,
)


def set_strategy(session_id: str, value: str, request_id: str = "s") -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "session/set_config_option",
        "params": {"sessionId": session_id, "configId": STRATEGY_CONFIG_ID, "value": value},
    }


def usage_updates(outbound) -> list[dict[str, Any]]:
    updates = [n["params"]["update"] for n in outbound.notifications if n["method"] == "session/update"]
    return [u for u in updates if u["sessionUpdate"] == "usage_update"]


class DispatchingRunner:
    """Answers Chat like the real runner does at its boundary: fits the request, records the
    dispatch, then answers. `sizes` sets one complete input per dispatch (several = retries)."""

    def __init__(self, *, sizes: tuple[int, ...] = (400,), dispatch: bool = True) -> None:
        self.sizes = sizes
        self.dispatch = dispatch
        self.requests: list[Any] = []
        self.sent: list[str] = []

    def run(self, request, **kwargs):
        self.requests.append(request)
        packer = kwargs.get("context_packer")
        if packer is not None and self.dispatch:
            for size in self.sizes:
                text = packer.fit(lambda envelope, size=size: f"Q{'x' * size}\n{envelope}")
                assert text is not None
                packer.record_dispatch(text)
                self.sent.append(text)
        return AgentRunResult(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=ExecutionMode.CHAT,
            status=AgentRunStatus.COMPLETED,
            final_state="CHAT_ONLY",
            output_text="An answer.",
            tool_calls=(),
            total_cost_usd=Decimal("0.001"),
            mutation_count=0,
            provider_keys_resolvable=(),
        )


# --- Sliding notice ---------------------------------------------------------------------------------


async def test_the_sliding_notice_goes_once_on_the_first_admitted_turn_after_the_switch(tmp_path):
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment(), DispatchingRunner())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    await rpc(adapter, set_strategy(session_id, "sliding_window"))
    outbound.notifications.clear()

    await prompt(adapter, outbound, session_id, "First", "p1")
    first = texts(outbound)
    outbound.notifications.clear()
    await prompt(adapter, outbound, session_id, "Second", "p2")

    assert first[0] == SLIDING_ACTIVE_TEXT and first.count(SLIDING_ACTIVE_TEXT) == 1
    assert SLIDING_ACTIVE_TEXT not in texts(outbound)
    records = session_of(adapter, session_id).conversation.records.values()
    assert all(SLIDING_ACTIVE_TEXT not in record.completion_text for record in records)  # live-only


async def test_switching_away_before_a_prompt_cancels_the_sliding_notice(tmp_path):
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment(), DispatchingRunner())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    await rpc(adapter, set_strategy(session_id, "sliding_window", "a"))
    await rpc(adapter, set_strategy(session_id, "compaction", "b"))
    outbound.notifications.clear()

    await prompt(adapter, outbound, session_id, "First", "p1")

    assert SLIDING_ACTIVE_TEXT not in texts(outbound)


async def test_an_unconfirmed_sliding_notice_is_tried_again_on_the_next_turn(tmp_path):
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment(), DispatchingRunner())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    await rpc(adapter, set_strategy(session_id, "sliding_window"))
    original = outbound.notify
    failures = {"left": 1}

    async def notify(method, params, *, require_flushed=False):
        content = params.get("update", {}).get("content", {})
        if failures["left"] and SLIDING_ACTIVE_TEXT in str(content.get("text", "")):
            failures["left"] -= 1
            raise AcpOutboundError(code=-32603, message="write failed")
        await original(method, params, require_flushed=require_flushed)

    outbound.notify = notify  # type: ignore[method-assign]
    outbound.notifications.clear()
    response = await prompt(adapter, outbound, session_id, "First", "p1")
    assert response["result"]["stopReason"] == "end_turn"  # a failed notice never fails the turn
    assert SLIDING_ACTIVE_TEXT not in texts(outbound)

    await prompt(adapter, outbound, session_id, "Second", "p2")
    assert texts(outbound).count(SLIDING_ACTIVE_TEXT) == 1


async def test_a_sliding_turn_that_falls_back_discloses_both_separately(tmp_path):
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment(engine=FlakyEngine(failures=1)), DispatchingRunner())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    await rpc(adapter, set_strategy(session_id, "sliding_window"))
    outbound.notifications.clear()

    await prompt(adapter, outbound, session_id, "First", "p1")

    shown = texts(outbound)
    assert shown[:2] == [SLIDING_ACTIVE_TEXT, CONTEXT_FALLBACK_TEXT.format(strategy="sliding window")]


# --- Storage wording ----------------------------------------------------------------------------


async def test_an_attached_storage_warning_names_storage(tmp_path):
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment(source_max=10_000), DispatchingRunner())
    session_id = await new_session(adapter, tmp_path, mode="chat")

    await prompt(adapter, outbound, session_id, "y" * 8100, "p1")

    shown = texts(outbound)
    assert ATTACHED_STORAGE_WARNING_TEXT in shown and CAPACITY_WARNING_TEXT not in shown
    assert "storage" in ATTACHED_STORAGE_WARNING_TEXT


# --- Meter --------------------------------------------------------------------------------------


async def test_the_attached_meter_reports_the_largest_dispatched_input_against_its_capacity(tmp_path):
    runner = DispatchingRunner(sizes=(400, 4000, 1000))
    attachment = make_attachment(summarizer=SummarizerCall())
    adapter, outbound, _ = make_adapter(tmp_path, attachment, runner)
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in range(3):
        await prompt(adapter, outbound, session_id, f"Earlier {n}", f"e{n}")
    outbound.notifications.clear()

    await prompt(adapter, outbound, session_id, "Now", "now")

    [reading] = usage_updates(outbound)
    assert reading["used"] == max(estimate(text) for text in runner.sent[-3:])
    assert reading["size"] == attachment.usable_input_tokens
    # Summarizer calls are costs, never readings: the reading is a planning/answer input.
    assert reading["used"] == estimate(runner.sent[-2])


async def test_a_turn_that_sent_nothing_produces_no_reading(tmp_path):
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment(), DispatchingRunner(dispatch=False))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    outbound.notifications.clear()

    await prompt(adapter, outbound, session_id, "hello", "p1")

    assert usage_updates(outbound) == []


async def test_a_full_history_fallback_dispatch_is_measured_too(tmp_path):
    runner = DispatchingRunner(sizes=(800,))
    attachment = make_attachment(engine=FlakyEngine(failures=1))
    adapter, outbound, _ = make_adapter(tmp_path, attachment, runner)
    session_id = await new_session(adapter, tmp_path, mode="chat")
    outbound.notifications.clear()

    await prompt(adapter, outbound, session_id, "hello", "p1")

    [reading] = usage_updates(outbound)
    assert reading["used"] == estimate(runner.sent[-1]) and reading["size"] == attachment.usable_input_tokens


async def test_the_absent_floor_meter_is_unchanged(tmp_path):
    adapter, outbound, _ = make_adapter(tmp_path, None, DispatchingRunner())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    outbound.notifications.clear()

    await prompt(adapter, outbound, session_id, "hello", "p1")

    [reading] = usage_updates(outbound)
    gauge = session_of(adapter, session_id).conversation.usage_gauge()
    assert (reading["used"], reading["size"]) == (gauge.used, gauge.size) == (gauge.used, 524_288 // 4)


@pytest.mark.parametrize("ties", [(1000, 1000)])
def test_equal_inputs_report_the_smaller_capacity(ties):
    from optimus.context.assembly import DispatchReading

    reading = DispatchReading.largest((DispatchReading(tokens=ties[0], capacity=9000), DispatchReading(tokens=ties[1], capacity=7000)))
    assert (reading.tokens, reading.capacity) == (1000, 7000)
    assert DispatchReading.largest(()) is None


def test_the_runner_records_a_dispatch_only_when_it_actually_sends(tmp_path):
    from optimus.acp.lifecycle import TurnControl
    from optimus.agent.models import AgentRunRequest
    from optimus.agent.runner import AgentRunner
    from optimus.gateway.models import GatewayResponse, GatewayUsage

    class Gateway:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def create_response(self, *, model, input_text, metadata=None):
            self.calls.append(input_text)
            usage = GatewayUsage(gateway_request_id="gw", provider="p", billing_units=1, cost_usd=Decimal("0.001"))
            return GatewayResponse(output_text="An answer.", gateway_usage=usage, raw={})

    class Packer:
        def __init__(self) -> None:
            self.dispatched: list[str] = []

        def fit(self, build):
            return build("HISTORY")

        def record_dispatch(self, text: str) -> None:
            self.dispatched.append(text)

    request = AgentRunRequest(
        run_id="s:1", session_id="s", task="Q?", execution_mode=ExecutionMode.CHAT, workspace_root=tmp_path,
        conversation_envelope="HISTORY", selection_text="Q?", context_digest="d" * 64,
    )  # fmt: skip
    gateway, packer = Gateway(), Packer()
    AgentRunner(gateway_client=gateway, model="m").run(request, context_packer=packer)
    assert packer.dispatched == gateway.calls

    halted_gateway, halted_packer = Gateway(), Packer()
    control = TurnControl(session_id="s", turn_seq=1)
    control.request_session_cancel()
    AgentRunner(gateway_client=halted_gateway, model="m").run(request, context_packer=halted_packer, operation_control=control)
    assert halted_packer.dispatched == [] and halted_gateway.calls == []


# --- Contributor disclosure -------------------------------------------------------------------------

CONTRIBUTOR = "meta/muse-spark-1.3-contributor"
STANDARD = "deepseek/deepseek-v4.1-flash"


def _disclosure(*, delivered: bool = True):
    from optimus.gateway.disclosure import ContributorDisclosure
    from optimus_model_policy import load_registry
    from optimus_model_policy.binding import disclosure_key, packaged_defaults

    snapshot = load_registry(packaged_defaults(), None)
    notices: list[str] = []

    def deliver(text: str) -> bool:
        notices.append(text)
        return delivered

    return ContributorDisclosure(snapshot=snapshot, key=disclosure_key("launch-secret"), deliver_notice=deliver), snapshot, notices


def test_the_contributor_notice_is_the_filed_text():
    from optimus.gateway.disclosure import CONTRIBUTOR_NOTICE

    assert CONTRIBUTOR_NOTICE == "Muse Spark Contributor may use supplied prompts, code, tool content and completions for model training."


def test_a_contributor_request_is_noticed_first_and_its_authorization_verifies_at_the_gateway():
    from optimus.gateway.disclosure import CONTRIBUTOR_NOTICE
    from optimus_model_policy.binding import disclosure_key, payload_digest, route_digest, verify_disclosure
    from optimus_model_policy.capacity import Message

    disclosure, snapshot, notices = _disclosure()

    binding = disclosure.binding(model_id=CONTRIBUTOR, request_id="req-1", input_text="P", output_cap=300)

    assert notices == [CONTRIBUTOR_NOTICE]
    assert (binding.registry_hash, binding.request_id, binding.output_cap) == (snapshot.effective_hash, "req-1", 300)
    entry = snapshot.policy.models[CONTRIBUTOR]
    payload = payload_digest(CONTRIBUTOR, (Message(role="user", content="P"),), 300, reasoning=entry.default_reasoning)
    assert verify_disclosure(
        disclosure_key("launch-secret"), binding.disclosure, request_id="req-1", model_id=CONTRIBUTOR,
        route=route_digest(CONTRIBUTOR, entry), payload=payload,
    )  # fmt: skip


def test_a_standard_route_needs_no_notice_or_authorization():
    disclosure, _, notices = _disclosure()

    binding = disclosure.binding(model_id=STANDARD, request_id="req-1", input_text="P", output_cap=300)

    assert binding.disclosure is None and notices == []


def test_an_identical_retry_shares_the_notice_and_a_new_payload_needs_its_own():
    disclosure, _, notices = _disclosure()

    first = disclosure.binding(model_id=CONTRIBUTOR, request_id="req-1", input_text="P", output_cap=300)
    again = disclosure.binding(model_id=CONTRIBUTOR, request_id="req-1", input_text="P", output_cap=300)
    assert len(notices) == 1 and again.disclosure == first.disclosure

    disclosure.binding(model_id=CONTRIBUTOR, request_id="req-2", input_text="Q", output_cap=300)
    assert len(notices) == 2


def test_an_undelivered_notice_authorizes_nothing():
    disclosure, _, notices = _disclosure(delivered=False)

    assert disclosure.binding(model_id=CONTRIBUTOR, request_id="req-1", input_text="P", output_cap=300) is None
    assert len(notices) == 1


def test_an_unknown_model_is_never_bound():
    disclosure, _, _ = _disclosure()

    with pytest.raises(ValueError):
        disclosure.binding(model_id="vendor/unknown", request_id="req-1", input_text="P", output_cap=300)


class _RoutedClient:
    def __init__(self, response) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create_response(self, *, model, input_text, metadata=None, route_binding=None):
        self.calls.append({"model": model, "route_binding": route_binding})
        return self.response


def _contributor_call(client, disclosure):
    from optimus.context.maintenance import GatewaySummarizerCall

    return GatewaySummarizerCall(
        gateway_client=client,
        model_id=CONTRIBUTOR,
        session_id="s",
        request_ids=lambda: "req-1",
        bind=lambda request_id, input_text, output_cap: disclosure.binding(
            model_id=CONTRIBUTOR, request_id=request_id, input_text=input_text, output_cap=output_cap
        ),
    )


def test_routed_provider_attempts_share_one_notice_and_keep_their_own_receipts():
    from optimus.gateway.models import GatewayResponse, GatewayRouteAttempt, GatewayUsage

    disclosure, _, notices = _disclosure()
    usage = GatewayUsage(gateway_request_id="gw-2", provider="p", billing_units=1, cost_usd=Decimal("0.0004"))
    attempts = (
        GatewayRouteAttempt(attempt=1, gateway_request_id="gw-1", outcome="uncertain"),
        GatewayRouteAttempt(attempt=2, gateway_request_id="gw-2", outcome="completed"),
    )
    client = _RoutedClient(GatewayResponse(output_text="x", gateway_usage=usage, raw={}, finish_reason="stop", route_attempts=attempts))

    response = _contributor_call(client, disclosure)(prompt="P", max_output_tokens=300)

    assert len(notices) == 1 and client.calls[0]["route_binding"].disclosure is not None
    assert [(a.outcome, a.cost_usd) for a in response.attempts] == [("uncertain", None), ("completed", Decimal("0.0004"))]


def test_a_contributor_summary_whose_notice_failed_is_never_sent():
    disclosure, _, _ = _disclosure(delivered=False)
    client = _RoutedClient(None)

    response = _contributor_call(client, disclosure)(prompt="P", max_output_tokens=300)

    assert client.calls == []
    [attempt] = response.attempts
    assert (attempt.outcome, attempt.cost_usd, response.text) == ("not_sent", Decimal("0"), None)


def test_the_production_summarizer_notices_a_contributor_route_before_it_sends():
    from optimus.context.maintenance import MaintenanceIdentity, SummarizerRoute, gateway_summarizer_factory
    from optimus.gateway.disclosure import CONTRIBUTOR_NOTICE
    from optimus.gateway.models import GatewayResponse, GatewayUsage
    from optimus_model_policy import load_registry
    from optimus_model_policy.binding import disclosure_key, packaged_defaults

    events: list[str] = []

    class Client:
        def create_response(self, *, model, input_text, metadata=None, route_binding=None):
            events.append(f"sent:{model}:{route_binding.disclosure is not None}")
            usage = GatewayUsage(gateway_request_id="gw", provider="p", billing_units=1, cost_usd=Decimal("0.0001"))
            return GatewayResponse(output_text="x", gateway_usage=usage, raw={}, finish_reason="stop")

    route = SummarizerRoute(model_id=CONTRIBUTOR, role="summarizer", route=("p",), reasoning=None, quantizations=(None,))
    factory = gateway_summarizer_factory(
        gateway_client=Client(), route=route, snapshot=load_registry(packaged_defaults(), None),
        disclosure_key=disclosure_key("launch-secret"),
    )  # fmt: skip
    identity = MaintenanceIdentity(
        session_id="s", turn_seq=1, model_id=CONTRIBUTOR, role="summarizer", route=("p",), reasoning=None,
        quantizations=(None,), strategy="compaction", revision_digest="d" * 64,
    )  # fmt: skip

    def deliver(text: str) -> bool:
        events.append(f"notice:{text == CONTRIBUTOR_NOTICE}")
        return True

    factory(identity, deliver)(prompt="P", max_output_tokens=300)

    assert events == ["notice:True", f"sent:{CONTRIBUTOR}:True"]


# --- Fable CP3 review fixes -------------------------------------------------------------------------


def _contributor_attachment(client):
    import dataclasses

    from optimus.context.maintenance import SummarizerRoute, gateway_summarizer_factory
    from optimus_model_policy import load_registry
    from optimus_model_policy.binding import disclosure_key, packaged_defaults

    route = SummarizerRoute(model_id=CONTRIBUTOR, role="summarizer", route=("meta",), reasoning=None, quantizations=(None,))
    factory = gateway_summarizer_factory(
        gateway_client=client, route=route, snapshot=load_registry(packaged_defaults(), None), disclosure_key=disclosure_key("launch-secret")
    )
    return dataclasses.replace(make_attachment(), summarizer=factory, summarizer_route=route)


class _ObservingClient:
    """A Gateway client double that records how many Contributor notices had reached the session when
    each summary request was sent."""

    def __init__(self, outbound) -> None:
        self.outbound = outbound
        self.notices_seen: list[int] = []

    def create_response(self, *, model, input_text, metadata=None, route_binding=None):
        from context_engine.summary import SECTIONS
        from optimus.gateway.disclosure import CONTRIBUTOR_NOTICE
        from optimus.gateway.models import GatewayResponse, GatewayUsage

        assert route_binding is not None and route_binding.disclosure is not None
        self.notices_seen.append(sum(CONTRIBUTOR_NOTICE in text for text in texts(self.outbound)))
        usage = GatewayUsage(gateway_request_id=f"gw-{len(self.notices_seen)}", provider="meta", billing_units=1, cost_usd=Decimal("0.0001"))
        summary = "\n".join(f"## {name}\nNone." for name in SECTIONS)
        return GatewayResponse(output_text=summary, gateway_usage=usage, raw={}, finish_reason="stop")


async def test_the_session_notice_channel_delivers_the_contributor_notice_before_the_summary_is_sent(tmp_path):
    from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel

    outbound = RecordingOutboundChannel()
    client = _ObservingClient(outbound)
    adapter = AcpDuplexAdapter(
        runner=DispatchingRunner(), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound,
        context_attachment=_contributor_attachment(client),
    )  # fmt: skip
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in range(4):
        await prompt(adapter, outbound, session_id, f"Prompt {n}", f"p{n}")

    # Turns 3 and 4 each summarized once, each request noticed first through the real channel.
    assert client.notices_seen == [1, 2]
    receipts = [r for r in session_of(adapter, session_id).cost_settlement.receipts(f"{session_id}:4") if r.stage == "summarization"]
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("completed", Decimal("0.0001"))]


async def test_an_undelivered_contributor_notice_sends_no_summary(tmp_path):
    from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
    from optimus.gateway.disclosure import CONTRIBUTOR_NOTICE

    outbound = RecordingOutboundChannel()
    original = outbound.notify

    async def notify(method, params, *, require_flushed=False):
        if CONTRIBUTOR_NOTICE in str(params.get("update", {}).get("content", {}).get("text", "")):
            raise AcpOutboundError(code=-32603, message="write failed")
        await original(method, params, require_flushed=require_flushed)

    outbound.notify = notify  # type: ignore[method-assign]
    client = _ObservingClient(outbound)
    adapter = AcpDuplexAdapter(
        runner=DispatchingRunner(), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound,
        context_attachment=_contributor_attachment(client),
    )  # fmt: skip
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in range(3):
        await prompt(adapter, outbound, session_id, f"Prompt {n}", f"p{n}")

    assert client.notices_seen == []  # nothing that needed the notice was sent
    receipts = [r for r in session_of(adapter, session_id).cost_settlement.receipts(f"{session_id}:3") if r.stage == "summarization"]
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("not_sent", Decimal("0"))]


async def test_a_session_that_starts_on_sliding_gets_its_notice(tmp_path):
    import dataclasses

    adapter, outbound, _ = make_adapter(tmp_path, dataclasses.replace(make_attachment(), initial_strategy="sliding_window"), DispatchingRunner())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    outbound.notifications.clear()

    await prompt(adapter, outbound, session_id, "First", "p1")

    assert texts(outbound).count(SLIDING_ACTIVE_TEXT) == 1
