from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import TYPE_CHECKING
from uuid import uuid4

from optimus.evidence.domain_policy import EvidenceDomainPolicy
from optimus.evidence.gateway_io import (
    build_web_extract_payload,
    build_web_search_payload,
    parse_web_extract_envelope,
    parse_web_search_envelope,
)
from optimus.evidence.ledger import EvidenceLedger, EvidenceLedgerEntry
from optimus.evidence.models import (
    EvidenceExtractRequest,
    EvidenceExtractResponse,
    EvidenceRequest,
    EvidenceSearchResponse,
    EvidenceSearchResult,
)
from optimus.gateway.client import GatewayClient
from optimus.gateway.errors import GatewayHttpError, GatewayResponseError
from optimus.gateway.models import GatewayUsage
from optimus.gateway.tool_models import GatewayToolContext
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolVerdict
from optimus.runtime.modes import ExecutionMode
from optimus.tools.policy import (
    EvidenceReasonCode,
    PolicyDecision,
    ToolClass,
    ToolInvocationDecision,
    ToolInvocationRequest,
    ToolPolicySignal,
)
from optimus.tools.registry import ToolCallRejected, ToolRegistry

if TYPE_CHECKING:
    # Deferred: optimus.usage.accounting imports optimus.evidence.ledger, which (via
    # optimus.evidence's package __init__) imports this module back -- a real circular
    # import at module-load time. The annotation-only reference below (enabled by
    # `from __future__ import annotations`) never needs the class at runtime.
    from optimus.usage.accounting import UsageAccountingService

WEB_SEARCH_SERVICE = "web.search"
WEB_EXTRACT_SERVICE = "web.extract"
TAVILY_NATIVE_UNIT = "tavily_credits"


class EvidenceAcquisitionService:
    """Orchestration layer for gateway-backed web evidence in Phase 1.

    Wires together policy checks, domain allowlisting, gateway I/O, provenance
    tracking, and cost/usage auditing into two operations: ``search`` and
    ``extract``. Authorization consumes per-run caps before transport; transport
    failures and malformed response bodies without usage keep the cap record but
    do not append a ledger entry. When the gateway returns usage but the
    evidence payload is malformed, or the transport call itself fails with an
    HTTP error that still carries billed usage (``GatewayHttpError.gateway_usage``),
    usage is still recorded before the error propagates.
    """

    def __init__(
        self,
        *,
        gateway_client: GatewayClient,
        domain_policy: EvidenceDomainPolicy,
        registry: ToolRegistry | None = None,
        ledger: EvidenceLedger | None = None,
        pre_tool_guard: PreToolGuard | None = None,
        usage_accounting: UsageAccountingService | None = None,
    ) -> None:
        self.gateway_client = gateway_client
        self.domain_policy = domain_policy
        self.registry = registry or ToolRegistry()
        self.ledger = ledger or EvidenceLedger()
        self._ledger_lock = Lock()
        self._pre_tool_guard = pre_tool_guard
        self._usage_accounting = usage_accounting

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
        self._assert_pre_tool_web_allowed(
            run_id=request.run_id,
            execution_mode=execution_mode,
            action=f"web_search:{request.query}",
        )
        context = GatewayToolContext(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=execution_mode.value,
        )
        request_id = _stable_request_id(request.run_id, WEB_SEARCH_SERVICE)
        effective_request = request.model_copy(update={"allowed_domains": effective_allowed_domains})
        try:
            body = self.gateway_client.post_tool_json(
                path="/v1/tools/web/search",
                payload=build_web_search_payload(effective_request, context),
            )
        except GatewayHttpError as exc:
            self._record_parse_failure_usage(
                request=request,
                tool_class=ToolClass.WEB_SEARCH,
                sources=(),
                exc=exc,
                service=WEB_SEARCH_SERVICE,
                native_unit=TAVILY_NATIVE_UNIT,
                request_id=request_id,
            )
            raise
        try:
            envelope = parse_web_search_envelope(body)
        except GatewayResponseError as exc:
            self._record_parse_failure_usage(
                request=request,
                tool_class=ToolClass.WEB_SEARCH,
                sources=(),
                exc=exc,
                service=WEB_SEARCH_SERVICE,
                native_unit=TAVILY_NATIVE_UNIT,
                request_id=request_id,
            )
            raise
        urls = tuple(str(item.url) for item in envelope.result.results)
        for url in urls:
            self.domain_policy.assert_url_allowed(url, effective_allowed_domains)
        self.registry.record_search_results(run_id=request.run_id, urls=urls)
        response = EvidenceSearchResponse(
            results=tuple(
                EvidenceSearchResult(title=item.title, url=str(item.url), snippet=item.snippet)
                for item in envelope.result.results
            ),
            gateway_usage=envelope.gateway_usage,
        )
        self._record_provider_usage(
            run_id=request.run_id,
            session_id=request.session_id,
            request_id=request_id,
            gateway_usage=envelope.gateway_usage,
            service=WEB_SEARCH_SERVICE,
            native_unit=TAVILY_NATIVE_UNIT,
        )
        ledger = self._record_ledger_entry(
            EvidenceLedgerEntry.from_gateway_usage(
                run_id=request.run_id,
                session_id=request.session_id,
                reason=request.reason,
                policy_signal=request.policy_signal.value,
                tool_class=ToolClass.WEB_SEARCH,
                sources=urls,
                gateway_usage=envelope.gateway_usage,
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
        self._assert_pre_tool_web_allowed(
            run_id=request.run_id,
            execution_mode=execution_mode,
            action=f"web_extract:{request.url_text}",
            target_url=request.url_text,
        )
        context = GatewayToolContext(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=execution_mode.value,
        )
        request_id = _stable_request_id(request.run_id, WEB_EXTRACT_SERVICE)
        try:
            body = self.gateway_client.post_tool_json(
                path="/v1/tools/web/extract",
                payload=build_web_extract_payload(request, context),
            )
        except GatewayHttpError as exc:
            self._record_parse_failure_usage(
                request=request,
                tool_class=ToolClass.WEB_EXTRACT,
                sources=(target_url,),
                exc=exc,
                service=WEB_EXTRACT_SERVICE,
                native_unit=TAVILY_NATIVE_UNIT,
                request_id=request_id,
            )
            raise
        try:
            envelope = parse_web_extract_envelope(body)
        except GatewayResponseError as exc:
            self._record_parse_failure_usage(
                request=request,
                tool_class=ToolClass.WEB_EXTRACT,
                sources=(target_url,),
                exc=exc,
                service=WEB_EXTRACT_SERVICE,
                native_unit=TAVILY_NATIVE_UNIT,
                request_id=request_id,
            )
            raise
        if not envelope.result.items:
            failure = GatewayResponseError("extract result items missing", gateway_usage=envelope.gateway_usage)
            self._record_parse_failure_usage(
                request=request,
                tool_class=ToolClass.WEB_EXTRACT,
                sources=(target_url,),
                exc=failure,
                service=WEB_EXTRACT_SERVICE,
                native_unit=TAVILY_NATIVE_UNIT,
                request_id=request_id,
            )
            raise failure
        item = envelope.result.items[0]
        response = EvidenceExtractResponse(
            url=str(item.url),
            title=item.title,
            content=item.content,
            trust="untrusted",
            gateway_usage=envelope.gateway_usage,
        )
        self._record_provider_usage(
            run_id=request.run_id,
            session_id=request.session_id,
            request_id=request_id,
            gateway_usage=response.gateway_usage,
            service=WEB_EXTRACT_SERVICE,
            native_unit=TAVILY_NATIVE_UNIT,
        )
        ledger = self._record_ledger_entry(
            EvidenceLedgerEntry.from_gateway_usage(
                run_id=request.run_id,
                session_id=request.session_id,
                reason=request.reason,
                policy_signal=request.policy_signal.value,
                tool_class=ToolClass.WEB_EXTRACT,
                sources=(target_url,),
                gateway_usage=response.gateway_usage,
                queried_at=_utc_now(),
            )
        )
        return response, ledger

    def _assert_pre_tool_web_allowed(
        self,
        *,
        run_id: str,
        execution_mode: ExecutionMode,
        action: str,
        target_url: str | None = None,
    ) -> None:
        if self._pre_tool_guard is None:
            return
        result = self._pre_tool_guard.check(
            PreToolRequest(
                run_id=run_id,
                session_id=None,
                execution_mode=execution_mode,
                tool_surface=ToolSurface.WEB,
                action=action,
                target_path=target_url,
                approval_granted=execution_mode is ExecutionMode.AGENT,
            )
        )
        if result.verdict is PreToolVerdict.BLOCK:
            raise ToolCallRejected(
                _rejected_web_decision(
                    reason=result.reason,
                    tool_class=ToolClass.WEB_EXTRACT if target_url else ToolClass.WEB_SEARCH,
                )
            )
        if result.verdict is PreToolVerdict.HOLD:
            raise ToolCallRejected(
                _rejected_web_decision(
                    reason=f"human approval required: {result.reason}",
                    tool_class=ToolClass.WEB_EXTRACT if target_url else ToolClass.WEB_SEARCH,
                )
            )

    def _record_ledger_entry(self, entry: EvidenceLedgerEntry) -> EvidenceLedger:
        with self._ledger_lock:
            self.ledger = self.ledger.record(entry)
            return self.ledger

    def _record_provider_usage(
        self,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        gateway_usage: GatewayUsage,
        service: str,
        native_unit: str,
    ) -> None:
        if self._usage_accounting is None:
            return
        self._usage_accounting.record_gateway_usage(
            gateway_usage,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=_utc_now(),
            service=service,
            native_unit=native_unit,
        )

    def _record_parse_failure_usage(
        self,
        *,
        request: EvidenceRequest | EvidenceExtractRequest,
        tool_class: ToolClass,
        sources: tuple[str, ...],
        exc: GatewayResponseError | GatewayHttpError,
        service: str,
        native_unit: str,
        request_id: str,
    ) -> None:
        """Record usage carried by a transport-level or parse-level failure.

        Shared by the ``GatewayHttpError`` transport-failure path and the
        ``GatewayResponseError`` envelope-parsing-failure path: both exception
        types carry an optional ``gateway_usage`` for attempts the gateway
        still billed despite the failure.
        """
        if exc.gateway_usage is None:
            return
        self._record_provider_usage(
            run_id=request.run_id,
            session_id=request.session_id,
            request_id=request_id,
            gateway_usage=exc.gateway_usage,
            service=service,
            native_unit=native_unit,
        )
        self._record_ledger_entry(
            EvidenceLedgerEntry.from_gateway_usage(
                run_id=request.run_id,
                session_id=request.session_id,
                reason=request.reason,
                policy_signal=request.policy_signal.value,
                tool_class=tool_class,
                sources=sources,
                gateway_usage=exc.gateway_usage,
                queried_at=_utc_now(),
            )
        )


def _rejected_web_decision(*, reason: str, tool_class: ToolClass) -> ToolInvocationDecision:
    return ToolInvocationDecision(
        decision=PolicyDecision.REJECT,
        reason=reason,
        tool_class=tool_class,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        reason_code=EvidenceReasonCode.USER_REQUESTED,
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _stable_request_id(run_id: str, service: str) -> str:
    """One caller-generated ID per transport attempt, reused across the success
    and parse-failure recording paths for that same attempt."""
    return f"{run_id}:{service}:{uuid4().hex}"
