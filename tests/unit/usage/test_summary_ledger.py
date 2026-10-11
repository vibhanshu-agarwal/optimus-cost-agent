"""Codex CP3 ruling R5: summary usage keeps its facts and reaches the existing usage ledger.

The summarizer path keeps the Gateway's original normalized usage and the identity it was bound to
through maintenance and settlement. `UsageLedgerAdapter` records each known attempt in the existing
`UsageAccountingService`/`ProviderUsageLedger` exactly once; an uncertain attempt never becomes a fake
`ProviderUsage` and stays a correlation fact in the settlement. The settlement and the ledger reconcile.
A captured identity that differs from the route actually bound is refused before any request exists,
so no attempt is relabelled.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from pathlib import Path

import pytest

from context_engine import MaintenanceRequest
from context_engine.summary import PROMPT_VERSION, SECTIONS, SUMMARY_FORMAT
from optimus.acp.conversation import ConversationSanitizer, ConversationSanitizerInputs
from optimus.context.maintenance import (
    GatewaySummarizerCall,
    HostMaintenance,
    MaintenanceIdentity,
    MaintenanceReceipt,
    SummarizerRoute,
    gateway_summarizer_factory,
)
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.models import GatewayResponse, GatewayRouteAttempt, GatewayUsage
from optimus.gateway.route_binding import RouteIdentityError
from optimus.usage.accounting import UsageAccountingService
from optimus.usage.errors import DuplicateGatewayRequestError
from optimus.usage.turn_settlement import TurnSettlement, UsageLedgerAdapter, receipt_from_maintenance

SANITIZER = ConversationSanitizer(ConversationSanitizerInputs((), ()))
SUMMARY = "\n".join(f"## {name}\nNone." for name in SECTIONS)
IDENTITY = MaintenanceIdentity(
    session_id="s", turn_seq=1, model_id="model-a", role="summarizer", route=("endpoint-a",), reasoning="low",
    quantizations=("fp8",), strategy="compaction", revision_digest="a" * 64, registry_hash="b" * 64,
)  # fmt: skip
REQUEST = MaintenanceRequest(
    input_text="synthetic ordinary history", covered_turn_ids=(1,), max_output_tokens=300, prompt_version=PROMPT_VERSION, format_version=SUMMARY_FORMAT
)


def _usage(gateway_id: str = "summary-gw", **changes) -> GatewayUsage:
    fields = dict(
        gateway_request_id=gateway_id, provider="fake", provider_request_id="pr-1", resolved_provider="Fake", resolved_model="model-a",
        model_version="v1", billing_units=34, cost_usd=Decimal("0.004"), input_tokens=23, output_tokens=11, cached_tokens=7,
        reasoning_tokens=2, total_tokens=34,
    )  # fmt: skip
    return GatewayUsage(**{**fields, **changes})


class Client:
    def __init__(self, *, response=None, error=None) -> None:
        self.response, self.error = response, error
        self.calls = 0

    def create_response(self, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response


def _summarize(client, *, cancelled_after: bool = False) -> list[MaintenanceReceipt]:
    receipts: list[MaintenanceReceipt] = []
    state = {"calls": 0}

    def cancelled() -> bool:
        state["calls"] += 1
        return cancelled_after and state["calls"] > 1

    call = GatewaySummarizerCall(gateway_client=client, model_id="model-a", session_id="s", request_ids=lambda: "summary-1")
    HostMaintenance(call=call, sanitizer=SANITIZER, identity=IDENTITY, record_receipt=receipts.append, cancelled=cancelled)(REQUEST)
    return receipts


def _ok(usage: GatewayUsage | None = None) -> Client:
    return Client(response=GatewayResponse(output_text=SUMMARY, gateway_usage=usage or _usage(), raw={}, finish_reason="stop"))


# --- Facts survive ------------------------------------------------------------------------------------


def test_the_summary_receipt_keeps_the_original_usage_and_the_bound_identity() -> None:
    [maintenance] = _summarize(_ok())
    stage = receipt_from_maintenance(maintenance)

    assert maintenance.gateway_usage == _usage()
    assert stage.gateway_usage == _usage() and stage.gateway_usage.billing_units == 34
    assert (stage.input_tokens, stage.output_tokens, stage.cached_tokens) == (23, 11, 7)
    assert (stage.provider, stage.resolved_provider, stage.resolved_model, stage.provider_request_id) == ("fake", "Fake", "model-a", "pr-1")
    assert (stage.requested_model, stage.role, stage.route, stage.reasoning, stage.quantizations) == (
        "model-a", "summarizer", ("endpoint-a",), "low", ("fp8",)
    )
    assert (stage.strategy, stage.revision_digest, stage.registry_hash) == ("compaction", "a" * 64, "b" * 64)


def test_missing_reported_tokens_stay_missing() -> None:
    [maintenance] = _summarize(_ok(_usage(input_tokens=None, output_tokens=None, cached_tokens=None)))

    stage = receipt_from_maintenance(maintenance)

    assert (stage.input_tokens, stage.output_tokens, stage.cached_tokens) == (None, None, None)


# --- The existing ledger --------------------------------------------------------------------------------


def _record(receipts: list[MaintenanceReceipt], service: UsageAccountingService, settlement: TurnSettlement) -> None:
    adapter = UsageLedgerAdapter(service)
    for receipt in receipts:
        adapter.record_maintenance(receipt)
        settlement.record_attempt(receipt_from_maintenance(receipt))


@pytest.mark.parametrize(
    "client",
    [
        pytest.param(lambda: _ok(), id="success"),
        pytest.param(
            lambda: Client(
                error=GatewayHttpError(
                    422, "x", gateway_code="FINISH_STATUS_UNVERIFIED", retryable=False, gateway_usage=_usage(),
                    route_attempts=(GatewayRouteAttempt(attempt=1, gateway_request_id="summary-gw", outcome="completed"),),
                )
            ),
            id="paid-failure",
        ),
        pytest.param(lambda: _ok(), id="cancelled-after-the-call"),
        pytest.param(
            lambda: Client(response=GatewayResponse(output_text="not a summary", gateway_usage=_usage(), raw={}, finish_reason="stop")),
            id="discarded-summary",
        ),
    ],
)  # fmt: skip
def test_a_known_summary_attempt_reaches_the_shared_ledger_exactly_once(request, client) -> None:
    service, settlement = UsageAccountingService(), TurnSettlement()
    receipts = _summarize(client(), cancelled_after="cancelled" in request.node.name)

    _record(receipts, service, settlement)
    _record(receipts, service, settlement)  # a replay adds nothing

    [entry] = service.provider_ledger.entries
    assert (entry.run_id, entry.service, entry.gateway_request_id, entry.billing_units, entry.cost_usd) == (
        "s:1", "context.summary", "summary-gw", 34, Decimal("0.004")
    )
    assert (entry.input_tokens, entry.output_tokens, entry.cached_tokens, entry.reasoning_tokens) == (23, 11, 7, 2)
    assert service.provider_ledger.total_cost_usd(run_id="s:1") == settlement.settle_turn("s:1").known_subtotal_usd


def test_an_uncertain_summary_attempt_never_becomes_ledger_usage() -> None:
    service, settlement = UsageAccountingService(), TurnSettlement()

    _record(_summarize(Client(error=ConnectionResetError("reset after send"))), service, settlement)

    assert service.provider_ledger.entries == ()
    summary = settlement.settle_turn("s:1")
    assert (summary.known_subtotal_usd, summary.complete, len(summary.unknown_attempt_ids)) == (Decimal("0"), False, 1)


def test_a_divergent_same_request_record_is_refused_by_the_ledgers_own_rule() -> None:
    service = UsageAccountingService()
    [first] = _summarize(_ok())
    [divergent] = _summarize(_ok(_usage(billing_units=35)))
    adapter = UsageLedgerAdapter(service)
    adapter.record_maintenance(first)

    with pytest.raises(DuplicateGatewayRequestError):
        adapter.record_maintenance(divergent)
    assert len(service.provider_ledger.entries) == 1


def test_the_ledger_records_concurrent_summaries_and_answers_without_losing_one() -> None:
    import threading

    service = UsageAccountingService()
    adapter = UsageLedgerAdapter(service)
    barrier = threading.Barrier(6)

    def record(n: int) -> None:
        barrier.wait(5)
        for k in range(20):
            [receipt] = _summarize(_ok(_usage(f"gw-{n}-{k}")))
            adapter.record_maintenance(receipt)

    threads = [threading.Thread(target=record, args=(n,), name=f"ledger-{n}") for n in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
        assert not thread.is_alive(), thread.name

    assert len(service.provider_ledger.entries) == 120


# --- Identity is the route actually bound ---------------------------------------------------------------


ROUTE = SummarizerRoute(model_id="model-a", role="summarizer", route=("endpoint-a",), reasoning="low", quantizations=("fp8",))


@pytest.mark.parametrize(
    ("field", "value"),
    [("model_id", "model-b"), ("role", "medium"), ("route", ("endpoint-b",)), ("reasoning", "high"), ("quantizations", ("bf16",))],
)
def test_a_captured_identity_that_is_not_the_bound_route_is_refused_before_any_request(field, value) -> None:
    client = _ok()
    factory = gateway_summarizer_factory(gateway_client=client, route=ROUTE, snapshot=None, disclosure_key=None)

    with pytest.raises(RouteIdentityError):
        factory(dataclasses.replace(IDENTITY, **{field: value}), lambda text: True)
    assert client.calls == 0


def _snapshot(tmp_path: Path):
    from tests.unit.optimus_gateway.model_policy_support import verified_snapshot

    return verified_snapshot(tmp_path)


def test_a_route_that_is_not_the_trusted_registrys_is_refused_at_configuration(tmp_path) -> None:
    snapshot = _snapshot(tmp_path)
    wrong = SummarizerRoute(model_id="cn/alpha", role="summarizer", route=("alpha-cloud/fp8",), reasoning="high", quantizations=("fp8",))

    with pytest.raises(RouteIdentityError):
        gateway_summarizer_factory(gateway_client=_ok(), route=wrong, snapshot=snapshot, disclosure_key=b"k")


def test_a_registry_identity_other_than_the_trusted_snapshot_is_refused(tmp_path) -> None:
    snapshot = _snapshot(tmp_path)
    route = SummarizerRoute(
        model_id="cn/alpha", role="summarizer", route=("alpha-cloud/fp8", "alpha-backup/bf16"), reasoning="high", quantizations=("fp8", "bf16")
    )
    factory = gateway_summarizer_factory(gateway_client=_ok(), route=route, snapshot=snapshot, disclosure_key=b"k")
    identity = dataclasses.replace(
        IDENTITY, model_id="cn/alpha", route=route.route, reasoning="high", quantizations=route.quantizations, registry_hash=snapshot.effective_hash
    )
    assert factory(identity, lambda text: True) is not None

    with pytest.raises(RouteIdentityError):
        factory(dataclasses.replace(identity, registry_hash="c" * 64), lambda text: True)


# --- Through an attached ACP turn ---------------------------------------------------------------------------


async def test_an_attached_turns_summaries_and_answers_reconcile_with_the_ledger(tmp_path) -> None:
    from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
    from optimus.agent.runner import AgentRunner
    from tests.unit.acp.test_context_engine_admission import make_attachment, new_session, prompt, session_of

    class Gateway:
        def __init__(self) -> None:
            self.n = 0

        def create_response(self, *, model, input_text, metadata=None, **kwargs):
            self.n += 1
            summary = metadata.get("purpose") == "context_summary"
            cost = "0.0004" if summary else "0.001"
            usage = _usage(f"gw-{self.n}", cost_usd=Decimal(cost), billing_units=self.n)
            return GatewayResponse(output_text=SUMMARY if summary else "An answer.", gateway_usage=usage, raw={}, finish_reason="stop")

    gateway, service = Gateway(), UsageAccountingService()
    route = SummarizerRoute(model_id="test/summarizer", role="summarizer", route=("provider-a",), reasoning=None, quantizations=("fp8",))
    attachment = dataclasses.replace(
        make_attachment(tail=10),
        summarizer=gateway_summarizer_factory(gateway_client=gateway, route=route, snapshot=None, disclosure_key=None),
        summarizer_route=route,
        record_receipt=UsageLedgerAdapter(service).record_maintenance,
    )
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=AgentRunner(gateway_client=gateway, model="test/planner", usage_accounting=service), workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(), outbound=outbound, context_attachment=attachment,
    )  # fmt: skip
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in range(4):
        await prompt(adapter, outbound, session_id, f"Question {n}: " + "words " * 30, f"p{n}")

    settlement = session_of(adapter, session_id).cost_settlement
    stages = {r.stage for r in settlement.receipts(f"{session_id}:4")}
    assert stages == {"summarization", "answer"}  # the last turn both summarized and answered
    for turn in range(1, 5):
        run_id = f"{session_id}:{turn}"
        assert service.provider_ledger.total_cost_usd(run_id=run_id) == settlement.settle_turn(run_id).known_subtotal_usd
    assert service.provider_ledger.total_cost_usd() == settlement.settle_all().known_subtotal_usd


def test_the_adapter_records_summaries_only() -> None:
    """Planning and answer usage reaches the ledger through the runner's own path; accepting it here
    too would emit its usage telemetry twice (Fable CP3 correction review MINOR-2)."""
    [maintenance] = _summarize(_ok())
    planning = dataclasses.replace(receipt_from_maintenance(maintenance), stage="planning")

    with pytest.raises(ValueError, match="runner's own ledger path"):
        UsageLedgerAdapter(UsageAccountingService()).record(planning)
