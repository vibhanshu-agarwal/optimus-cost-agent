from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock

from optimus.evidence.domain_policy import EvidenceDomainPolicy
from optimus.evidence.gateway_io import (
    build_web_extract_payload,
    build_web_search_payload,
    parse_web_extract_response,
    parse_web_search_response,
)
from optimus.evidence.ledger import EvidenceLedger, EvidenceLedgerEntry
from optimus.evidence.models import (
    EvidenceExtractRequest,
    EvidenceExtractResponse,
    EvidenceRequest,
    EvidenceSearchResponse,
)
from optimus.gateway.client import GatewayClient
from optimus.gateway.errors import GatewayResponseError
from optimus.runtime.modes import ExecutionMode
from optimus.tools.policy import ToolClass, ToolInvocationRequest
from optimus.tools.registry import ToolRegistry


class EvidenceAcquisitionService:
    """Orchestration layer for gateway-backed web evidence in Phase 1.

    Wires together policy checks, domain allowlisting, gateway I/O, provenance
    tracking, and cost/usage auditing into two operations: ``search`` and
    ``extract``. Authorization consumes per-run caps before transport; transport
    failures and malformed response bodies without usage keep the cap record but
    do not append a ledger entry. When the gateway returns usage but the
    evidence payload is malformed, usage is still recorded before the error
    propagates.
    """

    def __init__(
        self,
        *,
        gateway_client: GatewayClient,
        domain_policy: EvidenceDomainPolicy,
        registry: ToolRegistry | None = None,
        ledger: EvidenceLedger | None = None,
    ) -> None:
        self.gateway_client = gateway_client
        self.domain_policy = domain_policy
        self.registry = registry or ToolRegistry()
        self.ledger = ledger or EvidenceLedger()
        self._ledger_lock = Lock()

    def search(
        self,
        request: EvidenceRequest,
        *,
        execution_mode: ExecutionMode,
    ) -> tuple[EvidenceSearchResponse, EvidenceLedger]:
        """Authorize, search via gateway, validate result URLs, and record provenance."""
        effective_allowed_domains = self.domain_policy.effective_allowed_domains(request.allowed_domains)
        self.registry.authorize_and_record_call(
            ToolInvocationRequest(
                run_id=request.run_id,
                tool_class=ToolClass.WEB_SEARCH,
                execution_mode=execution_mode,
                policy_signal=request.policy_signal,
                reason=request.reason,
                allowed_domains=effective_allowed_domains,
            )
        )
        body = self.gateway_client.post_tool_json(
            path="/v1/tools/web/search",
            payload=build_web_search_payload(
                query=request.query,
                reason=request.reason,
                allowed_domains=effective_allowed_domains,
                result_cap=request.result_cap,
                search_depth=request.search_depth,
                metadata={
                    "run_id": request.run_id,
                    "session_id": request.session_id,
                    "policy_signal": request.policy_signal.value,
                },
            ),
        )
        try:
            response = parse_web_search_response(body)
        except GatewayResponseError as exc:
            self._record_parse_failure_usage(
                request=request,
                tool_class=ToolClass.WEB_SEARCH,
                sources=(),
                exc=exc,
            )
            raise
        urls = tuple(result.url_text for result in response.results)
        for url in urls:
            self.domain_policy.assert_url_allowed(url, effective_allowed_domains)
        self.registry.record_search_results(run_id=request.run_id, urls=urls)
        ledger = self._record_ledger_entry(
            EvidenceLedgerEntry.from_gateway_usage(
                run_id=request.run_id,
                session_id=request.session_id,
                reason=request.reason,
                policy_signal=request.policy_signal.value,
                tool_class=ToolClass.WEB_SEARCH,
                sources=urls,
                gateway_usage=response.gateway_usage,
                credits_used=response.credits_used,
                queried_at=_utc_now(),
            )
        )
        return response, ledger

    def extract(
        self,
        request: EvidenceExtractRequest,
        *,
        execution_mode: ExecutionMode,
    ) -> tuple[EvidenceExtractResponse, EvidenceLedger]:
        """Authorize extract for provenance-approved URL, call gateway, and record usage."""
        target_url = request.url_text
        effective_allowed_domains = self.domain_policy.effective_allowed_domains(request.allowed_domains)
        self.domain_policy.assert_url_allowed(target_url, effective_allowed_domains)
        self.registry.authorize_and_record_call(
            ToolInvocationRequest(
                run_id=request.run_id,
                tool_class=ToolClass.WEB_EXTRACT,
                execution_mode=execution_mode,
                policy_signal=request.policy_signal,
                reason=request.reason,
                target_url=target_url,
                prior_search_result_urls=self.registry.search_result_urls(request.run_id),
            )
        )
        body = self.gateway_client.post_tool_json(
            path="/v1/tools/web/extract",
            payload=build_web_extract_payload(
                url=target_url,
                reason=request.reason,
                max_chars_per_source=request.max_chars_per_source,
                metadata={
                    "run_id": request.run_id,
                    "session_id": request.session_id,
                    "policy_signal": request.policy_signal.value,
                },
            ),
        )
        try:
            response = parse_web_extract_response(body)
        except GatewayResponseError as exc:
            self._record_parse_failure_usage(
                request=request,
                tool_class=ToolClass.WEB_EXTRACT,
                sources=(target_url,),
                exc=exc,
            )
            raise
        ledger = self._record_ledger_entry(
            EvidenceLedgerEntry.from_gateway_usage(
                run_id=request.run_id,
                session_id=request.session_id,
                reason=request.reason,
                policy_signal=request.policy_signal.value,
                tool_class=ToolClass.WEB_EXTRACT,
                sources=(target_url,),
                gateway_usage=response.gateway_usage,
                credits_used=response.credits_used,
                queried_at=_utc_now(),
            )
        )
        return response, ledger

    def _record_ledger_entry(self, entry: EvidenceLedgerEntry) -> EvidenceLedger:
        with self._ledger_lock:
            self.ledger = self.ledger.record(entry)
            return self.ledger

    def _record_parse_failure_usage(
        self,
        *,
        request: EvidenceRequest | EvidenceExtractRequest,
        tool_class: ToolClass,
        sources: tuple[str, ...],
        exc: GatewayResponseError,
    ) -> None:
        if exc.gateway_usage is None:
            return
        self._record_ledger_entry(
            EvidenceLedgerEntry.from_gateway_usage(
                run_id=request.run_id,
                session_id=request.session_id,
                reason=request.reason,
                policy_signal=request.policy_signal.value,
                tool_class=tool_class,
                sources=sources,
                gateway_usage=exc.gateway_usage,
                credits_used=exc.credits_used or 0,
                queried_at=_utc_now(),
            )
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)
