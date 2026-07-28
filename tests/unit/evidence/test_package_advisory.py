from decimal import Decimal

import pytest

from optimus.evidence.ledger import EvidenceLedger
from optimus.evidence.package_advisory import PackageAdvisoryService
from optimus.gateway.errors import GatewayHttpError, GatewayResponseError
from optimus.gateway.tool_models import GatewayToolContext, PackageLookupRequest, SecurityAdvisoryRequest
from optimus.guardrails.pre_tool import PreToolResult, PreToolVerdict
from optimus.runtime.modes import ExecutionMode
from optimus.tools.policy import ToolClass
from optimus.tools.registry import ToolCallRejected, ToolRegistry
from optimus.usage.accounting import UsageAccountingService


def _context(**overrides) -> GatewayToolContext:
    fields = {"run_id": "run-1", "session_id": "session-1", "execution_mode": "PLAN"}
    fields.update(overrides)
    return GatewayToolContext(**fields)


class FakeGatewayClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def post_tool_json(self, *, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append({"path": path, "payload": payload})
        if path == "/v1/tools/package/lookup":
            return {
                "tool_class": "package_and_advisory_metadata",
                "policy_signal": "DEPENDENCY_VERSION_CHECK",
                "run_id": "run-1",
                "result": {
                    "package": "pytest-asyncio",
                    "ecosystem": "pypi",
                    "requested_version": None,
                    "latest_version": "0.24.0",
                    "versions": [],
                    "citations": ["https://pypi.org/project/pytest-asyncio/"],
                },
                "provenance": {"search_id": None, "source_urls": [], "trust": "untrusted"},
                "gateway_usage": {
                    "gateway_request_id": "gw-pkg-1",
                    "provider": "package-registry",
                    "cache_hit": False,
                    "billing_units": 1,
                    "cost_usd": "0.0005",
                },
            }
        if path == "/v1/tools/security/advisory":
            return {
                "tool_class": "package_and_advisory_metadata",
                "policy_signal": "SECURITY_OR_CVE_CHECK",
                "run_id": "run-1",
                "result": {
                    "identifier": "CVE-2026-12345",
                    "ecosystem": "npm",
                    "version": "1.2.3",
                    "advisories": [
                        {
                            "advisory_id": "GHSA-xxxx-yyyy-zzzz",
                            "summary": "Untrusted summary text",
                            "severity": "high",
                            "affected_ranges": ["<1.2.4"],
                            "fixed_versions": ["1.2.4"],
                            "citations": ["https://github.com/advisories/GHSA-xxxx-yyyy-zzzz"],
                        }
                    ],
                },
                "provenance": {"search_id": None, "source_urls": [], "trust": "untrusted"},
                "gateway_usage": {
                    "gateway_request_id": "gw-adv-1",
                    "provider": "osv",
                    "cache_hit": False,
                    "billing_units": 1,
                    "cost_usd": "0.0007",
                },
            }
        raise AssertionError(f"unexpected path: {path}")


class FailingGatewayClient(FakeGatewayClient):
    def post_tool_json(self, *, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append({"path": path, "payload": payload})
        raise GatewayHttpError(502, "gateway unavailable")


class FailingWithUsageGatewayClient(FakeGatewayClient):
    """A gateway HTTP error that still carries billed usage in the error body."""

    def post_tool_json(self, *, path: str, payload: dict[str, object]) -> dict[str, object]:
        from optimus.gateway.models import GatewayUsage

        self.calls.append({"path": path, "payload": payload})
        if path == "/v1/tools/package/lookup":
            usage = GatewayUsage(
                gateway_request_id="gw-pkg-http-error",
                provider="package-registry",
                cache_hit=False,
                billing_units=1,
                cost_usd=Decimal("0.0005"),
            )
        elif path == "/v1/tools/security/advisory":
            usage = GatewayUsage(
                gateway_request_id="gw-adv-http-error",
                provider="osv",
                cache_hit=False,
                billing_units=1,
                cost_usd=Decimal("0.0007"),
            )
        else:
            raise AssertionError(f"unexpected path: {path}")
        raise GatewayHttpError(502, "gateway unavailable", gateway_usage=usage)


class MalformedBodyGatewayClient(FakeGatewayClient):
    def post_tool_json(self, *, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append({"path": path, "payload": payload})
        if path == "/v1/tools/package/lookup":
            return {
                "tool_class": "package_and_advisory_metadata",
                "policy_signal": "DEPENDENCY_VERSION_CHECK",
                "run_id": "run-1",
                "result": {
                    "package": "pytest-asyncio",
                    "ecosystem": "pypi",
                    "requested_version": None,
                    "latest_version": "0.24.0",
                    "versions": [],
                    "citations": ["not-a-url"],
                },
                "provenance": {"search_id": None, "source_urls": [], "trust": "untrusted"},
                "gateway_usage": {
                    "gateway_request_id": "gw-pkg-bad",
                    "provider": "package-registry",
                    "cache_hit": False,
                    "billing_units": 1,
                    "cost_usd": "0.0005",
                },
            }
        if path == "/v1/tools/security/advisory":
            return {
                "tool_class": "package_and_advisory_metadata",
                "policy_signal": "SECURITY_OR_CVE_CHECK",
                "run_id": "run-1",
                "result": {
                    "identifier": "CVE-2026-12345",
                    "ecosystem": "npm",
                    "version": "1.2.3",
                    "advisories": [
                        {
                            "advisory_id": "GHSA-xxxx-yyyy-zzzz",
                            "summary": "Untrusted summary text",
                            "severity": "high",
                            "affected_ranges": ["<1.2.4"],
                            "fixed_versions": ["1.2.4"],
                            "citations": ["not-a-url"],
                        }
                    ],
                },
                "provenance": {"search_id": None, "source_urls": [], "trust": "untrusted"},
                "gateway_usage": {
                    "gateway_request_id": "gw-adv-bad",
                    "provider": "osv",
                    "cache_hit": False,
                    "billing_units": 1,
                    "cost_usd": "0.0007",
                },
            }
        raise AssertionError(f"unexpected path: {path}")


def test_package_lookup_authorizes_dedicated_class_and_signal_and_returns_typed_result():
    gateway = FakeGatewayClient()
    service = PackageAdvisoryService(
        gateway_client=gateway,
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = PackageLookupRequest(
        context=_context(),
        package="pytest-asyncio",
        ecosystem="pypi",
    )

    result, ledger = service.package_lookup(request, execution_mode=ExecutionMode.PLAN)

    assert result.latest_version == "0.24.0"
    assert gateway.calls[0]["path"] == "/v1/tools/package/lookup"
    assert gateway.calls[0]["payload"]["package"] == "pytest-asyncio"
    assert service.registry.records("run-1")[0].tool_class is ToolClass.PACKAGE_AND_ADVISORY_METADATA
    assert ledger.entries[0].tool_class is ToolClass.PACKAGE_AND_ADVISORY_METADATA
    assert ledger.entries[0].gateway_request_id == "gw-pkg-1"
    assert ledger.total_cost_usd() == Decimal("0.0005")


def test_security_advisory_authorizes_dedicated_class_and_signal_and_returns_typed_result():
    gateway = FakeGatewayClient()
    service = PackageAdvisoryService(
        gateway_client=gateway,
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = SecurityAdvisoryRequest(
        context=_context(),
        identifier="CVE-2026-12345",
        ecosystem="npm",
        version="1.2.3",
    )

    result, ledger = service.security_advisory(request, execution_mode=ExecutionMode.PLAN)

    assert result.advisories[0].advisory_id == "GHSA-xxxx-yyyy-zzzz"
    assert gateway.calls[0]["path"] == "/v1/tools/security/advisory"
    assert gateway.calls[0]["payload"]["identifier"] == "CVE-2026-12345"
    assert service.registry.records("run-1")[0].tool_class is ToolClass.PACKAGE_AND_ADVISORY_METADATA
    assert ledger.entries[0].tool_class is ToolClass.PACKAGE_AND_ADVISORY_METADATA
    assert ledger.entries[0].gateway_request_id == "gw-adv-1"


def test_package_lookup_gateway_failure_consumes_authorized_attempt_without_ledger_entry():
    gateway = FailingGatewayClient()
    service = PackageAdvisoryService(
        gateway_client=gateway,
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = PackageLookupRequest(context=_context(), package="pytest-asyncio", ecosystem="pypi")

    with pytest.raises(GatewayHttpError):
        service.package_lookup(request, execution_mode=ExecutionMode.PLAN)

    assert service.registry.call_count("run-1") == 1
    assert service.ledger.entries == ()


def test_package_lookup_malformed_body_records_usage_before_error():
    gateway = MalformedBodyGatewayClient()
    service = PackageAdvisoryService(
        gateway_client=gateway,
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = PackageLookupRequest(context=_context(), package="pytest-asyncio", ecosystem="pypi")

    with pytest.raises(GatewayResponseError):
        service.package_lookup(request, execution_mode=ExecutionMode.PLAN)

    assert service.registry.call_count("run-1") == 1
    assert len(service.ledger.entries) == 1
    assert service.ledger.entries[0].gateway_request_id == "gw-pkg-bad"
    assert service.ledger.entries[0].cost_usd == Decimal("0.0005")


def test_security_advisory_malformed_body_records_usage_before_error():
    gateway = MalformedBodyGatewayClient()
    service = PackageAdvisoryService(
        gateway_client=gateway,
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = SecurityAdvisoryRequest(context=_context(), identifier="CVE-2026-12345")

    with pytest.raises(GatewayResponseError):
        service.security_advisory(request, execution_mode=ExecutionMode.PLAN)

    assert service.registry.call_count("run-1") == 1
    assert len(service.ledger.entries) == 1
    assert service.ledger.entries[0].gateway_request_id == "gw-adv-bad"
    assert service.ledger.entries[0].cost_usd == Decimal("0.0007")


class FreePackageLookupGatewayClient(FakeGatewayClient):
    def post_tool_json(self, *, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append({"path": path, "payload": payload})
        if path == "/v1/tools/package/lookup":
            return {
                "tool_class": "package_and_advisory_metadata",
                "policy_signal": "DEPENDENCY_VERSION_CHECK",
                "run_id": "run-1",
                "result": {
                    "package": "pytest-asyncio",
                    "ecosystem": "pypi",
                    "requested_version": None,
                    "latest_version": "0.24.0",
                    "versions": [],
                    "citations": [],
                },
                "provenance": {"search_id": None, "source_urls": [], "trust": "untrusted"},
                "gateway_usage": {
                    "gateway_request_id": "gw-pkg-free",
                    "provider": "package-registry",
                    "cache_hit": False,
                    "billing_units": 0,
                    "cost_usd": "0",
                },
            }
        raise AssertionError(f"unexpected path: {path}")


def test_package_lookup_records_provider_usage_with_fixed_service_and_requests_unit():
    gateway = FreePackageLookupGatewayClient()
    accounting = UsageAccountingService()
    service = PackageAdvisoryService(
        gateway_client=gateway,
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
        usage_accounting=accounting,
    )
    request = PackageLookupRequest(context=_context(), package="pytest-asyncio", ecosystem="pypi")

    service.package_lookup(request, execution_mode=ExecutionMode.PLAN)

    assert len(accounting.provider_ledger.entries) == 1
    entry = accounting.provider_ledger.entries[0]
    assert entry.gateway_request_id == "gw-pkg-free"
    assert entry.service == "package.lookup"
    assert entry.native_unit == "requests"
    assert entry.cost_usd == Decimal("0")
    assert entry.billing_units == 0


def test_security_advisory_records_provider_usage_with_fixed_service_and_requests_unit():
    gateway = FakeGatewayClient()
    accounting = UsageAccountingService()
    service = PackageAdvisoryService(
        gateway_client=gateway,
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
        usage_accounting=accounting,
    )
    request = SecurityAdvisoryRequest(context=_context(), identifier="CVE-2026-12345")

    service.security_advisory(request, execution_mode=ExecutionMode.PLAN)

    assert len(accounting.provider_ledger.entries) == 1
    entry = accounting.provider_ledger.entries[0]
    assert entry.gateway_request_id == "gw-adv-1"
    assert entry.service == "security.advisory"
    assert entry.native_unit == "requests"


def test_package_lookup_malformed_body_records_provider_usage_before_error():
    gateway = MalformedBodyGatewayClient()
    accounting = UsageAccountingService()
    service = PackageAdvisoryService(
        gateway_client=gateway,
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
        usage_accounting=accounting,
    )
    request = PackageLookupRequest(context=_context(), package="pytest-asyncio", ecosystem="pypi")

    with pytest.raises(GatewayResponseError):
        service.package_lookup(request, execution_mode=ExecutionMode.PLAN)

    assert len(accounting.provider_ledger.entries) == 1
    assert accounting.provider_ledger.entries[0].gateway_request_id == "gw-pkg-bad"


def test_package_lookup_gateway_failure_without_usage_records_no_provider_usage():
    gateway = FailingGatewayClient()
    accounting = UsageAccountingService()
    service = PackageAdvisoryService(
        gateway_client=gateway,
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
        usage_accounting=accounting,
    )
    request = PackageLookupRequest(context=_context(), package="pytest-asyncio", ecosystem="pypi")

    with pytest.raises(GatewayHttpError):
        service.package_lookup(request, execution_mode=ExecutionMode.PLAN)

    assert accounting.provider_ledger.entries == ()


def test_package_lookup_http_error_with_usage_records_provider_usage_before_error():
    gateway = FailingWithUsageGatewayClient()
    accounting = UsageAccountingService()
    service = PackageAdvisoryService(
        gateway_client=gateway,
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
        usage_accounting=accounting,
    )
    request = PackageLookupRequest(context=_context(), package="pytest-asyncio", ecosystem="pypi")

    with pytest.raises(GatewayHttpError):
        service.package_lookup(request, execution_mode=ExecutionMode.PLAN)

    assert len(accounting.provider_ledger.entries) == 1
    entry = accounting.provider_ledger.entries[0]
    assert entry.gateway_request_id == "gw-pkg-http-error"
    assert entry.service == "package.lookup"
    assert entry.native_unit == "requests"
    assert entry.cost_usd == Decimal("0.0005")
    assert len(service.ledger.entries) == 1
    assert service.ledger.entries[0].gateway_request_id == "gw-pkg-http-error"


def test_security_advisory_http_error_with_usage_records_provider_usage_before_error():
    gateway = FailingWithUsageGatewayClient()
    accounting = UsageAccountingService()
    service = PackageAdvisoryService(
        gateway_client=gateway,
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
        usage_accounting=accounting,
    )
    request = SecurityAdvisoryRequest(context=_context(), identifier="CVE-2026-12345")

    with pytest.raises(GatewayHttpError):
        service.security_advisory(request, execution_mode=ExecutionMode.PLAN)

    assert len(accounting.provider_ledger.entries) == 1
    entry = accounting.provider_ledger.entries[0]
    assert entry.gateway_request_id == "gw-adv-http-error"
    assert entry.service == "security.advisory"
    assert entry.native_unit == "requests"
    assert entry.cost_usd == Decimal("0.0007")
    assert len(service.ledger.entries) == 1
    assert service.ledger.entries[0].gateway_request_id == "gw-adv-http-error"


class BlockingPreToolGuard:
    def check(self, request):
        return PreToolResult(PreToolVerdict.BLOCK, "network.unexpected_egress", "blocked network egress")


def test_package_lookup_pre_tool_guard_blocks_before_gateway_transport():
    gateway = FakeGatewayClient()
    service = PackageAdvisoryService(
        gateway_client=gateway,
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
        pre_tool_guard=BlockingPreToolGuard(),
    )
    request = PackageLookupRequest(context=_context(), package="pytest-asyncio", ecosystem="pypi")

    with pytest.raises(ToolCallRejected, match="blocked network egress"):
        service.package_lookup(request, execution_mode=ExecutionMode.AGENT)

    assert gateway.calls == []


def test_security_advisory_pre_tool_guard_blocks_before_gateway_transport():
    gateway = FakeGatewayClient()
    service = PackageAdvisoryService(
        gateway_client=gateway,
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
        pre_tool_guard=BlockingPreToolGuard(),
    )
    request = SecurityAdvisoryRequest(context=_context(), identifier="CVE-2026-12345")

    with pytest.raises(ToolCallRejected, match="blocked network egress"):
        service.security_advisory(request, execution_mode=ExecutionMode.AGENT)

    assert gateway.calls == []
