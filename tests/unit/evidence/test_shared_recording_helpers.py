"""#344: both evidence services record usage, ledger entries and request ids through one implementation."""

from __future__ import annotations

import re
from datetime import UTC

import pytest

from optimus.evidence.acquisition import EvidenceAcquisitionService
from optimus.evidence.domain_policy import EvidenceDomainPolicy
from optimus.evidence.ledger import EvidenceLedger
from optimus.evidence.models import EvidenceRequest
from optimus.evidence.package_advisory import PackageAdvisoryService
from optimus.gateway.tool_models import GatewayToolContext, PackageLookupRequest
from optimus.runtime.modes import ExecutionMode
from optimus.tools.policy import EvidenceReasonCode, ToolPolicySignal
from optimus.tools.registry import ToolRegistry
from optimus.usage.accounting import UsageAccountingService

_USAGE = {
    "gateway_request_id": "gw-1",
    "provider": "prov",
    "provider_request_id": "prov-1",
    "cache_hit": False,
    "billing_units": 2,
    "cost_usd": "0.002",
}


class _Gateway:
    def post_tool_json(self, *, path: str, payload: dict[str, object]) -> dict[str, object]:
        provenance = {"search_id": "s-1", "source_urls": [], "trust": "untrusted"}
        if path == "/v1/tools/web/search":
            return {
                "tool_class": "web_search",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "run_id": "run-1",
                "result": {"results": [{"title": "T", "url": "https://docs.example.com/a", "snippet": "S"}]},
                "provenance": {**provenance, "source_urls": ["https://docs.example.com/a"]},
                "gateway_usage": _USAGE,
            }
        return {
            "tool_class": "package_and_advisory_metadata",
            "policy_signal": "DEPENDENCY_VERSION_CHECK",
            "run_id": "run-1",
            "result": {
                "package": "pkg",
                "ecosystem": "pypi",
                "requested_version": None,
                "latest_version": "1.0",
                "versions": [],
                "citations": [],
            },
            "provenance": {**provenance, "search_id": None},
            "gateway_usage": _USAGE,
        }


def _search(accounting: UsageAccountingService | None):
    service = EvidenceAcquisitionService(
        gateway_client=_Gateway(),  # type: ignore[arg-type]
        domain_policy=EvidenceDomainPolicy(configured_allowed_domains=("docs.example.com",)),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
        usage_accounting=accounting,
    )
    request = EvidenceRequest(
        run_id="run-1",
        session_id="sess-1",
        query="q",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        allowed_domains=("docs.example.com",),
    )
    service.search(request, execution_mode=ExecutionMode.PLAN)
    return service, "web.search"


def _lookup(accounting: UsageAccountingService | None):
    service = PackageAdvisoryService(
        gateway_client=_Gateway(),  # type: ignore[arg-type]
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
        usage_accounting=accounting,
    )
    context = GatewayToolContext(run_id="run-1", session_id="sess-1", execution_mode="PLAN")
    request = PackageLookupRequest(context=context, package="pkg", ecosystem="pypi")
    service.package_lookup(request, execution_mode=ExecutionMode.PLAN)
    return service, "package.lookup"


@pytest.mark.parametrize("call", [_search, _lookup])
def test_both_services_record_usage_ledger_and_request_id_the_same_way(call) -> None:
    accounting = UsageAccountingService()
    service, name = call(accounting)

    (usage,) = accounting.provider_ledger.entries
    assert (usage.run_id, usage.session_id, usage.service) == ("run-1", "sess-1", name)
    assert (usage.gateway_request_id, usage.billing_units, str(usage.cost_usd)) == ("gw-1", 2, "0.002")
    assert re.fullmatch(rf"run-1:{re.escape(name)}:[0-9a-f]{{32}}", usage.request_id)
    assert usage.occurred_at.tzinfo is UTC

    (entry,) = service.ledger.entries
    assert entry.gateway_request_id == "gw-1"


@pytest.mark.parametrize("call", [_search, _lookup])
def test_both_services_record_ledger_without_usage_accounting(call) -> None:
    service, _ = call(None)

    assert [e.gateway_request_id for e in service.ledger.entries] == ["gw-1"]
