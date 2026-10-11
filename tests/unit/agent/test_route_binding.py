"""Codex CP3 ruling R4: planning and answer requests are bound to the trusted route (Task 1 contracts 4).

Offline proof through the production planner and Chat call sites and the actual in-process Gateway:
`handle_responses_request` with an enforced model policy runs its admission, capacity guard, disclosure
verification and attempt contract for real behind a `GatewayClient` transport. Only the provider is
fake. No network, service or paid call is made.

- A turn's binder is captured before any await and binds each complete final payload; a new payload
  is a new request with its own identity and, on a Contributor route, its own notice first.
- An undelivered notice sends nothing: a `not_sent` receipt at exactly 0 and a stated stop.
- Every provider attempt the Gateway reports is its own receipt, with the identity it was bound to.
- The Gateway's final input and output-cap guard still refuses; that refusal costs nothing.
- Applying a stored plan sends nothing and needs no new notice.
- Without a route policy nothing is bound, exactly as before.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

import optimus_gateway.responses as gateway_responses
from optimus.acp.lifecycle import TurnControl
from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import (
    GatewayClient,
    GatewayRequest,
    _route_attempts_dropped,
    _try_parse_error_correlation,
    _try_parse_error_usage,
)
from optimus.gateway.disclosure import CONTRIBUTOR_NOTICE
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.models import GatewayResponse, GatewayRouteAttempt, GatewayUsage
from optimus.gateway.route_binding import RouteIdentityError, RoutePolicy
from optimus.runtime.modes import ExecutionMode
from optimus.usage.turn_settlement import StageReceipt
from optimus_gateway.responses import handle_responses_request
from optimus_gateway.upstream_client import ProviderMessageResult, UpstreamAttemptFailure
from optimus_model_policy.binding import disclosure_key
from tests.unit.optimus_gateway.model_policy_support import (
    CAP,
    LIMIT_BYTES,
    SHARED_SECRET,
    gateway_config,
    model_policy,
    verified_snapshot,
)

STANDARD, CONTRIBUTOR = "cn/alpha", "us/contrib"
PLAN = "WRITE a.py\nx\nTEST pytest -q"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway_responses, "_sleep", lambda seconds: None)


@pytest.fixture
def snapshot(tmp_path: Path):
    (tmp_path / "registry").mkdir()
    return verified_snapshot(tmp_path / "registry")


class ScriptedUpstream:
    """The provider behind the real Gateway: each enforced attempt raises its scripted failure or
    returns the next scripted reply (the last one repeats)."""

    def __init__(self, replies: list[str] | None = None, attempts: list[UpstreamAttemptFailure | None] | None = None) -> None:
        self.replies = list(replies or [PLAN])
        self.attempts = list(attempts or [])
        self.calls: list[dict[str, Any]] = []

    def create_message_once(self, *, model, input_text, max_tokens, provider_controls, reasoning):
        self.calls.append({"model": model, "input_text": input_text, "max_tokens": max_tokens, "reasoning": reasoning})
        planned = self.attempts.pop(0) if self.attempts else None
        if planned is not None:
            raise planned
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return ProviderMessageResult(
            message_id=f"gen-{len(self.calls)}", output_text=text, input_tokens=10, output_tokens=5, total_tokens=15,
            billing_units=15, cost_usd=Decimal("0.0002"), provider="openrouter", resolved_provider="Alpha",
            requested_model=model, resolved_model=model, model_version=None, cache_hit=False, finish_reason="stop",
        )  # fmt: skip


class InProcessGateway:
    """A `GatewayTransport` that hands each request to the real Gateway handler and turns its error
    replies into the same `GatewayHttpError` the urllib transport raises."""

    def __init__(self, snapshot, upstream: ScriptedUpstream) -> None:
        self.config = gateway_config(model_policy(snapshot))
        self.upstream = upstream
        self.payloads: list[dict[str, Any]] = []
        self.replies: list[tuple[int, dict[str, Any]]] = []

    def post_json(self, request: GatewayRequest) -> dict[str, Any]:
        self.payloads.append(request.payload)
        status, body = handle_responses_request(
            authorization_header=request.headers.get("Authorization"), request_body=request.payload, config=self.config, upstream_client=self.upstream
        )
        self.replies.append((status, body))
        detail = json.dumps(body, default=str)
        if status != 200:
            code, retryable, attempts = _try_parse_error_correlation(detail)
            raise GatewayHttpError(
                status, detail, gateway_usage=_try_parse_error_usage(detail), gateway_code=code, retryable=retryable,
                route_attempts=attempts, route_attempts_malformed=_route_attempts_dropped(detail, attempts),
            )  # fmt: skip
        return json.loads(detail, parse_float=Decimal)


def _client(transport) -> GatewayClient:
    return GatewayClient(settings=OptimusGatewaySettings(optimus_api_key=SHARED_SECRET), transport=transport)


def _policy(snapshot, model: str = STANDARD, *, output_cap: int = CAP) -> RoutePolicy:
    return RoutePolicy(snapshot=snapshot, disclosure_key=disclosure_key(SHARED_SECRET), model_id=model, role="medium", output_cap=output_cap)


class Notices:
    def __init__(self, delivered: bool = True, events: list[str] | None = None) -> None:
        self.delivered = delivered
        self.events = events if events is not None else []

    def __call__(self, text: str) -> bool:
        self.events.append(f"notice:{text == CONTRIBUTOR_NOTICE}")
        return self.delivered


def _request(tmp_path: Path, mode: ExecutionMode, task: str = "Change the greeting.", **extra) -> AgentRunRequest:
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    return AgentRunRequest(run_id="s:1", session_id="s", task=task, workspace_root=workspace, execution_mode=mode, **extra)


def _run(tmp_path, snapshot, model, mode, *, upstream=None, notices=None, output_cap=CAP, task="Change the greeting.", runner=None, control=None):
    upstream = upstream or ScriptedUpstream()
    gateway = InProcessGateway(snapshot, upstream)
    runner = runner or AgentRunner(gateway_client=_client(gateway), model=model)
    notices = notices or Notices()
    binder = _policy(snapshot, model, output_cap=output_cap).capture(session_id="s", turn_seq=1, deliver_notice=notices)
    receipts: list[StageReceipt] = []
    result = runner.run(_request(tmp_path, mode, task), stage_receipts=receipts.append, route_binder=binder, operation_control=control)
    return result, receipts, gateway, notices, binder


# --- Standard and Contributor routes -----------------------------------------------------------------


@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.AGENT], ids=["chat", "planning"])
def test_a_standard_route_is_bound_without_a_notice_and_admitted_by_the_gateway(tmp_path, snapshot, mode) -> None:
    result, receipts, gateway, notices, binder = _run(tmp_path, snapshot, STANDARD, mode)

    assert notices.events == []
    [payload] = gateway.payloads
    binding = payload["route_binding"]
    assert binding["registry_hash"] == snapshot.effective_hash and binding.get("disclosure") is None
    assert payload["metadata"]["request_id"] == binding["request_id"]
    assert [call["max_tokens"] for call in gateway.upstream.calls] == [CAP]  # the bound output cap, counted once
    [receipt] = receipts
    identity = binder.identity
    assert (receipt.requested_model, receipt.role, receipt.route, receipt.reasoning, receipt.quantizations, receipt.registry_hash) == (
        STANDARD, "medium", ("alpha-cloud/fp8", "alpha-backup/bf16"), "high", ("fp8", "bf16"), snapshot.effective_hash
    )
    assert identity.route == receipt.route
    assert (receipt.outcome, receipt.reported_cost_usd, receipt.gateway_usage.billing_units) == ("completed", Decimal("0.0002"), 15)
    assert result.cost_complete is True


@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.AGENT], ids=["chat", "planning"])
def test_a_contributor_request_is_noticed_first_and_its_disclosure_verifies_at_the_gateway(tmp_path, snapshot, mode) -> None:
    events: list[str] = []

    class Upstream(ScriptedUpstream):
        def create_message_once(self, **kwargs):
            events.append("sent")
            return super().create_message_once(**kwargs)

    result, receipts, gateway, _, _ = _run(tmp_path, snapshot, CONTRIBUTOR, mode, upstream=Upstream(), notices=Notices(events=events))

    assert events == ["notice:True", "sent"]
    assert gateway.payloads[0]["route_binding"]["disclosure"] is not None
    assert [status for status, _ in gateway.replies] == [200]
    assert [(r.requested_model, r.outcome) for r in receipts] == [(CONTRIBUTOR, "completed")]


def test_each_new_planning_payload_is_a_new_request_with_its_own_notice(tmp_path, snapshot) -> None:
    (tmp_path / "ws").mkdir()
    (tmp_path / "ws" / "a.py").write_text("print('hi')\n", encoding="utf-8")
    upstream = ScriptedUpstream(replies=["OBSERVE: need the greeting\nREAD: a.py#bytes=0:5\n", PLAN])
    notices = Notices()

    result, receipts, gateway, _, _ = _run(tmp_path, snapshot, CONTRIBUTOR, ExecutionMode.AGENT, upstream=upstream, notices=notices)

    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    request_ids = [payload["route_binding"]["request_id"] for payload in gateway.payloads]
    assert len(request_ids) == 2 and len(set(request_ids)) == 2
    assert notices.events == ["notice:True", "notice:True"]  # one per new payload
    assert [status for status, _ in gateway.replies] == [200, 200]  # each disclosure verified
    assert [r.attempt_id for r in receipts] == ["s:1:planning:1:1:1", "s:1:planning:2:1:1"]


@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.AGENT], ids=["chat", "planning"])
def test_an_undelivered_notice_sends_nothing(tmp_path, snapshot, mode) -> None:
    control = TurnControl(session_id="s", turn_seq=1)

    result, receipts, gateway, notices, _ = _run(tmp_path, snapshot, CONTRIBUTOR, mode, notices=Notices(delivered=False), control=control)

    assert notices.events == ["notice:True"] and gateway.payloads == []
    assert [(r.outcome, r.reported_cost_usd, r.gateway_request_id) for r in receipts] == [("not_sent", Decimal("0"), None)]
    expected = "CHAT_NOTICE_UNDELIVERED" if mode is ExecutionMode.CHAT else "PLANNING_NOTICE_UNDELIVERED"
    assert (result.stop_reason, result.cost_complete, result.total_cost_usd) == (expected, True, Decimal("0"))
    assert control.provider_attempt_started() is False


# --- Provider attempts ---------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.AGENT], ids=["chat", "planning"])
def test_a_recovered_attempt_and_the_settled_one_are_each_receipted(tmp_path, snapshot, mode) -> None:
    upstream = ScriptedUpstream(attempts=[UpstreamAttemptFailure("rejected", http_status=429), None])

    result, receipts, _, _, _ = _run(tmp_path, snapshot, STANDARD, mode, upstream=upstream)

    assert [(r.outcome, r.reported_cost_usd, r.http_status) for r in receipts] == [
        ("rejected", Decimal("0"), 429),
        ("completed", Decimal("0.0002"), None),
    ]
    assert receipts[1].gateway_usage is not None and receipts[0].gateway_usage is None
    assert result.cost_complete is True


@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.AGENT], ids=["chat", "planning"])
def test_a_routed_failure_keeps_every_attempt_and_stays_unknown(tmp_path, snapshot, mode) -> None:
    upstream = ScriptedUpstream(attempts=[UpstreamAttemptFailure("not_sent"), UpstreamAttemptFailure("uncertain")])

    result, receipts, gateway, _, _ = _run(tmp_path, snapshot, STANDARD, mode, upstream=upstream)

    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("not_sent", Decimal("0")), ("uncertain", None)]
    assert len(gateway.payloads) == 1  # never re-sent by the host
    assert result.cost_complete is False
    assert result.stop_reason in {"CHAT_GATEWAY_COST_UNKNOWN", "PLANNING_GATEWAY_COST_UNKNOWN"}


@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.AGENT], ids=["chat", "planning"])
def test_an_uncertain_attempt_before_settled_usage_keeps_both_and_stays_incomplete(tmp_path, mode) -> None:
    """The Gateway contract never re-sends after an uncertain attempt; if a response ever reported one
    before its settled usage, the host keeps the unknown rather than folding it into the success."""
    usage = GatewayUsage(gateway_request_id="gw-2", provider="p", billing_units=1, cost_usd=Decimal("0.0004"))
    attempts = (
        GatewayRouteAttempt(attempt=1, gateway_request_id="gw-1", outcome="uncertain"),
        GatewayRouteAttempt(attempt=2, gateway_request_id="gw-2", outcome="completed"),
    )

    class Client:
        def create_response(self, **kwargs):
            return GatewayResponse(output_text=PLAN, gateway_usage=usage, raw={}, finish_reason="stop", route_attempts=attempts)

    receipts: list[StageReceipt] = []
    result = AgentRunner(gateway_client=Client(), model=STANDARD).run(_request(tmp_path, mode), stage_receipts=receipts.append)

    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("uncertain", None), ("completed", Decimal("0.0004"))]
    assert (result.cost_complete, result.unknown_cost_attempt_count, result.total_cost_usd) == (False, 1, Decimal("0.0004"))


# --- The final Gateway guard -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (ExecutionMode.CHAT, "CHAT_INPUT_CAPACITY_EXCEEDED"),
        (ExecutionMode.AGENT, "PLANNING_INPUT_CAPACITY_EXCEEDED"),
        (ExecutionMode.PLAN, "PLANNING_INPUT_CAPACITY_EXCEEDED"),
    ],
    ids=["chat", "planning", "single-shot-plan"],
)
def test_an_input_over_the_routes_capacity_gets_the_capacity_refusal_at_no_cost(tmp_path, snapshot, mode, expected) -> None:
    """Release supplement V1: the Gateway's INPUT_EXCEEDS_CAPACITY is shown as the capacity refusal (no
    smaller view claimed), never the generic gateway refusal; the refused request costs nothing and
    gives no meter reading."""
    from optimus.agent.planning_loop import planning_corrective_text
    from optimus.agent.runner import CHAT_FAILURE_MESSAGES

    result, receipts, gateway, _, binder = _run(tmp_path, snapshot, STANDARD, mode, task="x" * (LIMIT_BYTES + 1))

    [(status, body)] = gateway.replies
    assert status == 400 and body["code"] == "INPUT_EXCEEDS_CAPACITY"
    assert gateway.upstream.calls == []
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("rejected", Decimal("0"))]
    assert (result.stop_reason, result.cost_complete, result.total_cost_usd) == (expected, True, Decimal("0"))
    text = CHAT_FAILURE_MESSAGES[expected] if mode is ExecutionMode.CHAT else planning_corrective_text(expected)
    assert result.output_text == text and text.endswith("This thread stays open.") and "not sent to a model" in text
    assert binder.largest_dispatch() is None


@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.AGENT], ids=["chat", "planning"])
def test_a_reasonless_capacity_refusal_keeps_the_generic_refusal(tmp_path, snapshot, mode) -> None:
    """CAPACITY_REFUSED is only the Gateway's defensive fallback for a refusal without a reason; it does
    not establish overflow, so it keeps the generic refusal and its zero cost (Codex concurrence
    disposition, 2026-10-04). No production path reaches it today: this refusal is synthetic."""

    class Refusing:
        def create_response(self, **kwargs):
            raise GatewayHttpError(
                400, json.dumps({"code": "CAPACITY_REFUSED"}), gateway_usage=None, gateway_code="CAPACITY_REFUSED",
                retryable=False, route_attempts=(), route_attempts_malformed=False,
            )  # fmt: skip

    binder = _policy(snapshot).capture(session_id="s", turn_seq=1, deliver_notice=Notices())
    receipts: list[StageReceipt] = []
    result = AgentRunner(gateway_client=Refusing(), model=STANDARD).run(_request(tmp_path, mode), stage_receipts=receipts.append, route_binder=binder)

    expected = "CHAT_GATEWAY_REFUSED" if mode is ExecutionMode.CHAT else "PLANNING_GATEWAY_REFUSED"
    assert (result.stop_reason, result.cost_complete, result.total_cost_usd) == (expected, True, Decimal("0"))
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("rejected", Decimal("0"))]


@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.AGENT, ExecutionMode.PLAN], ids=["chat", "planning", "single-shot-plan"])
def test_the_request_reading_is_the_gateways_own_complete_input_and_capacity(tmp_path, snapshot, mode) -> None:
    """Release supplement V1: without an engine, the meter reads the request actually sent with the
    same packed input, verified estimator and usable capacity as the Gateway's final guard."""
    from optimus_model_policy import Message, PackedModelRequest, guard_request

    _, _, gateway, _, binder = _run(tmp_path, snapshot, STANDARD, mode)

    decisions = [
        guard_request(
            PackedModelRequest(model_id=STANDARD, messages=(Message(role="user", content=payload["input"]),), tools_json="", output_cap=CAP),
            snapshot,
            snapshot.effective_hash,
        )
        for payload in gateway.payloads
    ]
    assert decisions and all(decision.allowed for decision in decisions)
    largest = max(decisions, key=lambda decision: decision.input_tokens)
    reading = binder.largest_dispatch()
    assert reading is not None and (reading.tokens, reading.capacity) == (largest.input_tokens, largest.usable_input) == (largest.input_tokens, 262144 - CAP)


def test_an_output_cap_over_the_route_is_refused_by_the_gateway_at_no_cost(tmp_path, snapshot) -> None:
    result, receipts, gateway, _, _ = _run(tmp_path, snapshot, STANDARD, ExecutionMode.AGENT, output_cap=30_000)

    [(status, body)] = gateway.replies
    assert status == 400 and body["code"].startswith("OUTPUT_RESERVE_EXCEEDS")
    assert gateway.upstream.calls == []
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("rejected", Decimal("0"))]
    assert (result.stop_reason, result.cost_complete) == ("PLANNING_GATEWAY_REFUSED", True)


# --- Stored plans, legacy and configuration ----------------------------------------------------------------


def test_applying_a_stored_plan_sends_nothing_and_needs_no_new_notice(tmp_path, snapshot) -> None:
    upstream = ScriptedUpstream()
    gateway = InProcessGateway(snapshot, upstream)
    # The plan's TEST runs through an injected runner, never as a real process: an uninjected
    # `pytest -q` would run in the test process's working directory, the repository, and recurse
    # into this suite (Plan 12.2 CP4 run t12-full-1).
    shell: list[list[str]] = []
    runner = AgentRunner(
        gateway_client=_client(gateway), model=CONTRIBUTOR, shell_runner=lambda command: shell.append(command) or CompletedProcess(command, 0, "1 passed", "")
    )
    planned, _, _, notices, _ = _run(tmp_path, snapshot, CONTRIBUTOR, ExecutionMode.AGENT, runner=runner)
    assert planned.status is AgentRunStatus.AWAITING_APPROVAL and len(notices.events) == 1

    applying = Notices()
    binder = _policy(snapshot, CONTRIBUTOR).capture(session_id="s", turn_seq=1, deliver_notice=applying)
    receipts: list[StageReceipt] = []
    request = _request(tmp_path, ExecutionMode.AGENT).model_copy(
        update={"approval": AgentApproval(approved=True, approval_id="approval-1", plan_hash=planned.plan_hash)}
    )
    applied = runner.run(request, stage_receipts=receipts.append, route_binder=binder)

    assert applied.status is AgentRunStatus.COMPLETED
    assert (tmp_path / "ws" / "a.py").read_text(encoding="utf-8").strip() == "x"
    assert shell == [["pytest", "-q"]]
    assert gateway.payloads[1:] == [] and applying.events == [] and receipts == []


@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.AGENT], ids=["chat", "planning"])
def test_without_a_route_policy_requests_are_unbound_as_before(tmp_path, mode) -> None:
    seen: list[dict[str, Any]] = []

    class Client:
        def create_response(self, *, model, input_text, metadata=None):  # today's signature: no binding
            seen.append(dict(metadata or {}))
            usage = GatewayUsage(gateway_request_id="gw", provider="p", billing_units=1, cost_usd=Decimal("0.0001"))
            return GatewayResponse(output_text=PLAN, gateway_usage=usage, raw={}, finish_reason="stop")

    receipts: list[StageReceipt] = []
    AgentRunner(gateway_client=Client(), model="any/model").run(_request(tmp_path, mode), stage_receipts=receipts.append)

    assert seen and all("request_id" not in metadata for metadata in seen)
    assert [(r.requested_model, r.role, r.route, r.registry_hash) for r in receipts] == [("any/model", None, (), None)]


def test_a_binder_for_another_model_is_refused_before_anything_is_sent(tmp_path, snapshot) -> None:
    gateway = InProcessGateway(snapshot, ScriptedUpstream())
    binder = _policy(snapshot, STANDARD).capture(session_id="s", turn_seq=1, deliver_notice=Notices())

    with pytest.raises(RouteIdentityError):
        AgentRunner(gateway_client=_client(gateway), model=CONTRIBUTOR).run(_request(tmp_path, ExecutionMode.CHAT), route_binder=binder)
    assert gateway.payloads == []


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [({"output_cap": 0}, "output cap"), ({"model_id": "vendor/unknown"}, "not in the trusted registry"), ({"role": ""}, "role")],
)
def test_a_route_policy_needs_its_explicit_trusted_settings(snapshot, kwargs, message) -> None:
    settings = {"snapshot": snapshot, "disclosure_key": disclosure_key(SHARED_SECRET), "model_id": STANDARD, "role": "medium", "output_cap": CAP}

    with pytest.raises(RouteIdentityError, match=message):
        RoutePolicy(**{**settings, **kwargs})


# --- Through the ACP host ---------------------------------------------------------------------------------


async def test_the_acp_host_notices_through_the_session_before_the_bound_answer_is_sent(tmp_path, snapshot) -> None:
    from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
    from tests.unit.acp.test_context_engine_admission import new_session, prompt, session_of, texts

    outbound = RecordingOutboundChannel()
    notices_at_send: list[int] = []

    class Upstream(ScriptedUpstream):
        def create_message_once(self, **kwargs):
            notices_at_send.append(texts(outbound).count(CONTRIBUTOR_NOTICE))
            return super().create_message_once(**kwargs)

    gateway = InProcessGateway(snapshot, Upstream(replies=["An answer."]))
    adapter = AcpDuplexAdapter(
        runner=AgentRunner(gateway_client=_client(gateway), model=CONTRIBUTOR), workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(), outbound=outbound, route_policy=_policy(snapshot, CONTRIBUTOR),
    )  # fmt: skip
    session_id = await new_session(adapter, tmp_path, mode="chat")

    await prompt(adapter, outbound, session_id, "A question?", "p1")
    await prompt(adapter, outbound, session_id, "Another question?", "p2")

    assert notices_at_send == [1, 2]  # each turn's new request was noticed first, through the session
    assert [status for status, _ in gateway.replies] == [200, 200]
    receipts = session_of(adapter, session_id).cost_settlement.receipts(f"{session_id}:2")
    assert [(r.requested_model, r.role, r.registry_hash) for r in receipts] == [(CONTRIBUTOR, "medium", snapshot.effective_hash)]
    assert "An answer." in texts(outbound)


async def test_the_acp_host_sends_nothing_when_the_session_cannot_confirm_the_notice(tmp_path, snapshot) -> None:
    from optimus.acp.errors import AcpOutboundError
    from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
    from optimus.agent.runner import CHAT_FAILURE_MESSAGES
    from tests.unit.acp.test_context_engine_admission import new_session, prompt, session_of, texts

    outbound = RecordingOutboundChannel()
    original = outbound.notify

    async def notify(method, params, *, require_flushed=False):
        if CONTRIBUTOR_NOTICE in str(params.get("update", {}).get("content", {}).get("text", "")):
            raise AcpOutboundError(code=-32603, message="write failed")
        await original(method, params, require_flushed=require_flushed)

    outbound.notify = notify  # type: ignore[method-assign]
    gateway = InProcessGateway(snapshot, ScriptedUpstream(replies=["An answer."]))
    adapter = AcpDuplexAdapter(
        runner=AgentRunner(gateway_client=_client(gateway), model=CONTRIBUTOR), workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(), outbound=outbound, route_policy=_policy(snapshot, CONTRIBUTOR),
    )  # fmt: skip
    session_id = await new_session(adapter, tmp_path, mode="chat")

    await prompt(adapter, outbound, session_id, "A question?", "p1")

    assert gateway.payloads == []
    assert CHAT_FAILURE_MESSAGES["CHAT_NOTICE_UNDELIVERED"] in texts(outbound)
    [receipt] = session_of(adapter, session_id).cost_settlement.receipts(f"{session_id}:1")
    assert (receipt.outcome, receipt.reported_cost_usd) == ("not_sent", Decimal("0"))


async def test_the_acp_host_meters_and_warns_on_request_capacity_without_an_engine(tmp_path) -> None:
    """Release supplement V1 (D7 exception): under a trusted route policy and no engine, the meter reads
    the request's usable capacity; one 80% request warning arrives long before storage is near its
    floor; a request over capacity gets the capacity refusal, no reading, and the thread stays open.
    A heavier test estimator (4 tokens per byte) makes a 50 KB request cross 80% while storage is ~10%."""
    from optimus.acp.conversation import ConversationDisposition
    from optimus.acp.spec import (
        ABSENT_STORAGE_WARNING_TEXT,
        CAPACITY_WARNING_TEXT,
        REQUEST_CAPACITY_WARNING_TEXT,
        AcpDuplexAdapter,
        InMemoryAcpSpecSessionStore,
        RecordingOutboundChannel,
    )
    from optimus.agent.runner import CHAT_FAILURE_MESSAGES
    from tests.unit.acp.test_context_engine_admission import new_session, prompt, session_of, texts
    from tests.unit.acp.test_context_notices import usage_updates
    from tests.unit.optimus_gateway.model_policy_support import VERIFIED_POLICY

    (tmp_path / "registry").mkdir()
    heavy = verified_snapshot(tmp_path / "registry", VERIFIED_POLICY.replace('tokens_per_byte: "0.5"', 'tokens_per_byte: "4"'))
    usable = 262144 - CAP
    outbound = RecordingOutboundChannel()
    gateway = InProcessGateway(heavy, ScriptedUpstream(replies=["An answer."]))
    adapter = AcpDuplexAdapter(
        runner=AgentRunner(gateway_client=_client(gateway), model=STANDARD), workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(), outbound=outbound, route_policy=_policy(heavy, STANDARD),
    )  # fmt: skip
    session_id = await new_session(adapter, tmp_path, mode="chat")

    await prompt(adapter, outbound, session_id, "A question?", "p1")
    first = usage_updates(outbound)[-1]
    assert first["size"] == usable and 0 < first["used"] < 0.8 * usable
    assert REQUEST_CAPACITY_WARNING_TEXT not in texts(outbound)

    # Ordinary words: one 50 KB run without separators is slow to sanitize (owned separately).
    await prompt(adapter, outbound, session_id, "calculator note " * 3_125, "p2")
    second = usage_updates(outbound)[-1]
    assert second["size"] == usable and 0.8 * usable <= second["used"] <= usable
    assert texts(outbound).count(REQUEST_CAPACITY_WARNING_TEXT) == 1
    # Storage is nowhere near its 80% notice: the request limit comes first (D7).
    assert ABSENT_STORAGE_WARNING_TEXT not in texts(outbound) and CAPACITY_WARNING_TEXT not in texts(outbound)

    meters_before = len(usage_updates(outbound))
    response = await prompt(adapter, outbound, session_id, "rounding rule " * 1_500, "p3")  # history + prompt now exceed capacity
    assert response["result"]["stopReason"] == "end_turn"
    assert CHAT_FAILURE_MESSAGES["CHAT_INPUT_CAPACITY_EXCEEDED"] in texts(outbound)
    assert texts(outbound).count(REQUEST_CAPACITY_WARNING_TEXT) == 1  # never repeated
    assert len(usage_updates(outbound)) == meters_before  # a refused request gets no fabricated reading
    assert session_of(adapter, session_id).conversation.disposition is ConversationDisposition.OPEN
    assert len(gateway.upstream.calls) == 2  # the refused request reached no model


async def test_storage_notices_say_storage_under_a_route_policy(tmp_path, snapshot) -> None:
    """Release supplement V1: with a trusted route policy, the absent-engine 80% notice is labelled as
    storage and says a model request can be refused sooner."""
    from optimus.acp.spec import (
        ABSENT_STORAGE_WARNING_TEXT,
        CAPACITY_WARNING_TEXT,
        AcpDuplexAdapter,
        InMemoryAcpSpecSessionStore,
        RecordingOutboundChannel,
    )

    def adapter(policy):
        return AcpDuplexAdapter(
            runner=AgentRunner(gateway_client=_client(InProcessGateway(snapshot, ScriptedUpstream())), model=STANDARD), workspace_root=tmp_path,
            sessions=InMemoryAcpSpecSessionStore(), outbound=RecordingOutboundChannel(), route_policy=policy,
        )  # fmt: skip

    assert adapter(_policy(snapshot, STANDARD))._warning_text() == ABSENT_STORAGE_WARNING_TEXT  # noqa: SLF001
    assert adapter(None)._warning_text() == CAPACITY_WARNING_TEXT  # noqa: SLF001 - inactive enforcement unchanged
    assert "storage limit" in ABSENT_STORAGE_WARNING_TEXT and "refused sooner" in ABSENT_STORAGE_WARNING_TEXT


# --- The single-shot PLAN path ---------------------------------------------------------------------------


def test_the_single_shot_plan_path_is_bound_and_receipts_every_attempt(tmp_path, snapshot) -> None:
    upstream = ScriptedUpstream(attempts=[UpstreamAttemptFailure("rejected", http_status=429), None])

    result, receipts, gateway, _, _ = _run(tmp_path, snapshot, STANDARD, ExecutionMode.PLAN, upstream=upstream)

    assert gateway.payloads[0]["route_binding"]["request_id"] == gateway.payloads[0]["metadata"]["request_id"]
    assert [(r.stage, r.outcome, r.reported_cost_usd) for r in receipts] == [
        ("planning", "rejected", Decimal("0")),
        ("planning", "completed", Decimal("0.0002")),
    ]
    assert result.cost_complete is True


def test_the_single_shot_plan_path_sends_nothing_without_its_notice(tmp_path, snapshot) -> None:
    result, receipts, gateway, _, _ = _run(tmp_path, snapshot, CONTRIBUTOR, ExecutionMode.PLAN, notices=Notices(delivered=False))

    assert gateway.payloads == []
    assert (result.stop_reason, result.status) == ("PLANNING_NOTICE_UNDELIVERED", AgentRunStatus.FAILED)
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("not_sent", Decimal("0"))]


def test_the_single_shot_plan_failure_keeps_its_receipts_and_still_raises(tmp_path, snapshot) -> None:
    upstream = ScriptedUpstream(attempts=[UpstreamAttemptFailure("not_sent"), UpstreamAttemptFailure("uncertain")])
    gateway = InProcessGateway(snapshot, upstream)
    binder = _policy(snapshot).capture(session_id="s", turn_seq=1, deliver_notice=Notices())
    receipts: list[StageReceipt] = []

    with pytest.raises(GatewayHttpError):
        AgentRunner(gateway_client=_client(gateway), model=STANDARD).run(
            _request(tmp_path, ExecutionMode.PLAN), stage_receipts=receipts.append, route_binder=binder
        )

    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("not_sent", Decimal("0")), ("uncertain", None)]
