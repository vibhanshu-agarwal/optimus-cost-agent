from datetime import UTC, datetime
from decimal import Decimal

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES, OptimusGatewaySettings
from optimus.evidence.acquisition import EvidenceAcquisitionService
from optimus.evidence.domain_policy import EvidenceDomainPolicy
from optimus.evidence.ledger import EvidenceLedger, EvidenceLedgerEntry
from optimus.gateway.client import GatewayClient, GatewayRequest
from optimus.gateway.models import GatewayUsage
from optimus.runtime.modes import ExecutionMode
from optimus.tools.policy import EvidenceReasonCode, ToolClass, ToolPolicySignal
from optimus.tools.registry import ToolRegistry
from optimus.usage.accounting import UsageAccountingService, reconcile_evidence_provider_usage
from tests.support.gateway_settings import TRUSTED_GATEWAY_ORIGIN


def usage() -> GatewayUsage:
    return GatewayUsage(
        gateway_request_id="gw-search-1",
        provider="tavily",
        cache_hit=False,
        billing_units=2,
        cost_usd=Decimal("0.002"),
        service="web.search",
        native_unit="tavily_credits",
        price_snapshot_id="prices-2026-07-04",
    )


def test_mocked_evidence_and_provider_ledgers_reconcile():
    gateway_usage = usage()
    evidence = EvidenceLedger().record(
        EvidenceLedgerEntry.from_gateway_usage(
            run_id="run-1",
            session_id="session-1",
            reason=EvidenceReasonCode.USER_REQUESTED,
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
            tool_class=ToolClass.WEB_SEARCH,
            sources=("https://docs.example.com",),
            gateway_usage=gateway_usage,
            queried_at=datetime(2026, 7, 4, tzinfo=UTC),
        )
    )
    provider = UsageAccountingService().record_gateway_usage(
        gateway_usage,
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        service="web.search",
        native_unit="tavily_credits",
    )

    report = reconcile_evidence_provider_usage(evidence, provider, run_id="run-1")

    assert report.reconciled is True


class NormalizedCapturingTransport:
    """Like the fake transport in ``test_mocked_evidence_flow.py``, but each
    ``gateway_usage`` also carries the normalized provider-accounting fields
    (``service``, ``native_unit``, ``optimus_credits_debited``,
    ``price_snapshot_id``) so the resulting usage can be replayed into
    :class:`~optimus.usage.accounting.UsageAccountingService`.
    """

    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict[str, object]:
        self.requests.append(request)
        if request.url.endswith("/v1/tools/web/search"):
            return {
                "tool_class": "web_search",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "run_id": "run-1",
                "result": {
                    "results": [
                        {
                            "title": "Docs",
                            "url": "https://docs.example.com/a",
                            "snippet": "Authoritative docs",
                        },
                    ]
                },
                "provenance": {
                    "search_id": "search-1",
                    "source_urls": ["https://docs.example.com/a"],
                    "trust": "untrusted",
                },
                "gateway_usage": {
                    "gateway_request_id": "gw-search-1",
                    "provider": "tavily",
                    "cache_hit": False,
                    "billing_units": 2,
                    "cost_usd": "0.002",
                    "service": "web.search",
                    "native_unit": "tavily_credits",
                    "price_snapshot_id": "prices-2026-07-04",
                },
            }
        if request.url.endswith("/v1/tools/web/extract"):
            return {
                "tool_class": "web_extract",
                "policy_signal": "APPROVED_SEARCH_RESULT_PROVENANCE",
                "run_id": "run-1",
                "result": {
                    "items": [
                        {
                            "url": "https://docs.example.com/a",
                            "title": "Docs",
                            "content": "Evidence text must be treated as untrusted text.",
                        },
                    ]
                },
                "provenance": {
                    "search_id": None,
                    "source_urls": ["https://docs.example.com/a"],
                    "trust": "untrusted",
                },
                "gateway_usage": {
                    "gateway_request_id": "gw-extract-1",
                    "provider": "tavily",
                    "cache_hit": True,
                    "billing_units": 1,
                    "cost_usd": "0.001",
                    "service": "web.extract",
                    "native_unit": "tavily_credits",
                    "price_snapshot_id": "prices-2026-07-04",
                },
            }
        raise AssertionError(f"unexpected URL: {request.url}")


def _settings_with_only_optimus_credentials(monkeypatch) -> OptimusGatewaySettings:
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", TRUSTED_GATEWAY_ORIGIN)
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt_live_test")
    for key in LOCAL_PROVIDER_KEY_NAMES:
        monkeypatch.delenv(key, raising=False)
    settings = OptimusGatewaySettings.from_env()
    assert settings.validate_no_local_provider_keys() == ()
    return settings


def _run_mocked_search_then_extract(monkeypatch):
    """Drive a full mocked search-then-extract flow through the real client
    stack and return ``(evidence_ledger, [gateway_usage, ...])`` so the test
    can independently replay the exact Gateway-issued usage into the provider
    ledger — proving the join key, not re-deriving it.
    """
    settings = _settings_with_only_optimus_credentials(monkeypatch)
    transport = NormalizedCapturingTransport()
    service = EvidenceAcquisitionService(
        gateway_client=GatewayClient(settings=settings, transport=transport),
        domain_policy=EvidenceDomainPolicy(configured_allowed_domains=("docs.example.com",)),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )

    search_response, _ = service.search(
        _search_request(), execution_mode=ExecutionMode.PLAN
    )
    extract_response, ledger = service.extract(
        _extract_request(), execution_mode=ExecutionMode.PLAN
    )
    return ledger, [search_response.gateway_usage, extract_response.gateway_usage]


def _search_request():
    from optimus.evidence.models import EvidenceRequest

    return EvidenceRequest(
        run_id="run-1",
        query="latest pytest release",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        allowed_domains=("docs.example.com",),
    )


def _extract_request():
    from optimus.evidence.models import EvidenceExtractRequest

    return EvidenceExtractRequest(
        run_id="run-1",
        url="https://docs.example.com/a",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
        allowed_domains=("docs.example.com",),
    )


def test_full_mocked_search_and_extract_flow_reconciles_against_provider_ledger(monkeypatch):
    """The evidence ledger produced by a real (transport-mocked) search-then-
    extract call reconciles cleanly against a provider ledger built from the
    exact same Gateway-issued usage envelopes, joined by
    ``gateway_request_id`` — never a locally invented identifier.
    """
    evidence_ledger, gateway_usages = _run_mocked_search_then_extract(monkeypatch)

    accounting = UsageAccountingService()
    for index, gateway_usage in enumerate(gateway_usages):
        accounting.record_gateway_usage(
            gateway_usage,
            run_id="run-1",
            session_id=None,
            request_id=f"req-{index}",
            occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
            service="web.search",
            native_unit="tavily_credits",
        )

    report = reconcile_evidence_provider_usage(evidence_ledger, accounting.provider_ledger, run_id="run-1")

    assert report.reconciled is True
    assert report.matched_gateway_request_ids == {"gw-search-1", "gw-extract-1"}
    assert report.missing_provider_usage_ids == frozenset()
    assert report.missing_evidence_ids == frozenset()
    assert report.cost_delta_usd == Decimal("0")


def test_reconciliation_detects_provider_usage_missing_for_one_gateway_call(monkeypatch):
    """If the provider-side usage pipeline drops one of the two Gateway calls
    (e.g. an export failure), reconciliation must surface exactly that gap by
    ``gateway_request_id`` rather than silently reporting success.
    """
    evidence_ledger, gateway_usages = _run_mocked_search_then_extract(monkeypatch)

    accounting = UsageAccountingService()
    # Only replay the search usage; the extract usage is "lost" downstream.
    accounting.record_gateway_usage(
        gateway_usages[0],
        run_id="run-1",
        session_id=None,
        request_id="req-0",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        service="web.search",
        native_unit="tavily_credits",
    )

    report = reconcile_evidence_provider_usage(evidence_ledger, accounting.provider_ledger, run_id="run-1")

    assert report.reconciled is False
    assert report.missing_provider_usage_ids == {"gw-extract-1"}
    assert report.cost_delta_usd == Decimal("0.001")


def test_injected_accounting_auto_records_provider_usage_reconciling_with_evidence_ledger(monkeypatch):
    """With ``UsageAccountingService`` injected directly into the evidence
    service (Task 3), ``search``/``extract`` must record provider usage
    themselves -- no manual replay by the caller required.
    """
    settings = _settings_with_only_optimus_credentials(monkeypatch)
    transport = NormalizedCapturingTransport()
    accounting = UsageAccountingService()
    service = EvidenceAcquisitionService(
        gateway_client=GatewayClient(settings=settings, transport=transport),
        domain_policy=EvidenceDomainPolicy(configured_allowed_domains=("docs.example.com",)),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
        usage_accounting=accounting,
    )

    service.search(_search_request(), execution_mode=ExecutionMode.PLAN)
    _, evidence_ledger = service.extract(_extract_request(), execution_mode=ExecutionMode.PLAN)

    report = reconcile_evidence_provider_usage(evidence_ledger, accounting.provider_ledger, run_id="run-1")

    assert report.reconciled is True
    assert report.matched_gateway_request_ids == {"gw-search-1", "gw-extract-1"}
    assert {entry.service for entry in accounting.provider_ledger.entries} == {"web.search", "web.extract"}
    assert {entry.native_unit for entry in accounting.provider_ledger.entries} == {"tavily_credits"}
