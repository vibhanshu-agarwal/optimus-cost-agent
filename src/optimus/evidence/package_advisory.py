from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock

from optimus.evidence.ledger import EvidenceLedger, EvidenceLedgerEntry
from optimus.gateway.client import GatewayClient
from optimus.gateway.errors import GatewayResponseError
from optimus.gateway.tool_models import (
    PackageLookupRequest,
    PackageLookupResult,
    SecurityAdvisoryRequest,
    SecurityAdvisoryResult,
    parse_gateway_tool_envelope,
)
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


class PackageAdvisoryService:
    """Orchestration layer for gateway-backed package/security metadata (``P11-FU-2``).

    Mirrors :class:`~optimus.evidence.acquisition.EvidenceAcquisitionService`'s
    policy/pre-tool/ledger orchestration, but routes exclusively through the
    dedicated ``ToolClass.PACKAGE_AND_ADVISORY_METADATA`` class: the reason and
    policy signal for each operation are fixed by the endpoint, not caller
    input, so a caller cannot select generic web search for these signals.
    Provider hosts are resolved server-side, so no local domain policy applies
    here. Package/version text, advisory summaries, and citation URLs are
    always untrusted data.
    """

    def __init__(
        self,
        *,
        gateway_client: GatewayClient,
        registry: ToolRegistry | None = None,
        ledger: EvidenceLedger | None = None,
        pre_tool_guard: PreToolGuard | None = None,
    ) -> None:
        self.gateway_client = gateway_client
        self.registry = registry or ToolRegistry()
        self.ledger = ledger or EvidenceLedger()
        self._ledger_lock = Lock()
        self._pre_tool_guard = pre_tool_guard

    def package_lookup(
        self,
        request: PackageLookupRequest,
        *,
        execution_mode: ExecutionMode,
    ) -> tuple[PackageLookupResult, EvidenceLedger]:
        """Authorize, look up via gateway, and record usage for a package lookup."""
        context = request.context
        self.registry.authorize_and_record_call(
            ToolInvocationRequest(
                run_id=context.run_id,
                tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
                execution_mode=execution_mode,
                policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
                reason=EvidenceReasonCode.PACKAGE_VERSION,
            )
        )
        self._assert_pre_tool_allowed(
            run_id=context.run_id,
            execution_mode=execution_mode,
            action=f"package_lookup:{request.package}",
        )
        body = self.gateway_client.post_tool_json(
            path="/v1/tools/package/lookup",
            payload=request.model_dump(mode="json"),
        )
        try:
            envelope = parse_gateway_tool_envelope(body, PackageLookupResult)
        except GatewayResponseError as exc:
            self._record_parse_failure_usage(
                run_id=context.run_id,
                session_id=context.session_id,
                reason=EvidenceReasonCode.PACKAGE_VERSION,
                policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
                tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
                sources=(),
                exc=exc,
            )
            raise
        ledger = self._record_ledger_entry(
            EvidenceLedgerEntry.from_gateway_usage(
                run_id=context.run_id,
                session_id=context.session_id,
                reason=EvidenceReasonCode.PACKAGE_VERSION,
                policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK.value,
                tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
                sources=tuple(str(citation) for citation in envelope.result.citations),
                gateway_usage=envelope.gateway_usage,
                queried_at=_utc_now(),
            )
        )
        return envelope.result, ledger

    def security_advisory(
        self,
        request: SecurityAdvisoryRequest,
        *,
        execution_mode: ExecutionMode,
    ) -> tuple[SecurityAdvisoryResult, EvidenceLedger]:
        """Authorize, look up via gateway, and record usage for a security advisory."""
        context = request.context
        self.registry.authorize_and_record_call(
            ToolInvocationRequest(
                run_id=context.run_id,
                tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
                execution_mode=execution_mode,
                policy_signal=ToolPolicySignal.SECURITY_OR_CVE_CHECK,
                reason=EvidenceReasonCode.SECURITY_ADVISORY,
            )
        )
        self._assert_pre_tool_allowed(
            run_id=context.run_id,
            execution_mode=execution_mode,
            action=f"security_advisory:{request.identifier}",
        )
        body = self.gateway_client.post_tool_json(
            path="/v1/tools/security/advisory",
            payload=request.model_dump(mode="json"),
        )
        try:
            envelope = parse_gateway_tool_envelope(body, SecurityAdvisoryResult)
        except GatewayResponseError as exc:
            self._record_parse_failure_usage(
                run_id=context.run_id,
                session_id=context.session_id,
                reason=EvidenceReasonCode.SECURITY_ADVISORY,
                policy_signal=ToolPolicySignal.SECURITY_OR_CVE_CHECK,
                tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
                sources=(),
                exc=exc,
            )
            raise
        sources = tuple(
            str(citation) for advisory in envelope.result.advisories for citation in advisory.citations
        )
        ledger = self._record_ledger_entry(
            EvidenceLedgerEntry.from_gateway_usage(
                run_id=context.run_id,
                session_id=context.session_id,
                reason=EvidenceReasonCode.SECURITY_ADVISORY,
                policy_signal=ToolPolicySignal.SECURITY_OR_CVE_CHECK.value,
                tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
                sources=sources,
                gateway_usage=envelope.gateway_usage,
                queried_at=_utc_now(),
            )
        )
        return envelope.result, ledger

    def _assert_pre_tool_allowed(
        self,
        *,
        run_id: str,
        execution_mode: ExecutionMode,
        action: str,
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
                approval_granted=execution_mode is ExecutionMode.AGENT,
            )
        )
        if result.verdict is PreToolVerdict.BLOCK:
            raise ToolCallRejected(_rejected_package_advisory_decision(reason=result.reason))
        if result.verdict is PreToolVerdict.HOLD:
            raise ToolCallRejected(
                _rejected_package_advisory_decision(reason=f"human approval required: {result.reason}")
            )

    def _record_ledger_entry(self, entry: EvidenceLedgerEntry) -> EvidenceLedger:
        with self._ledger_lock:
            self.ledger = self.ledger.record(entry)
            return self.ledger

    def _record_parse_failure_usage(
        self,
        *,
        run_id: str,
        session_id: str | None,
        reason: EvidenceReasonCode,
        policy_signal: ToolPolicySignal,
        tool_class: ToolClass,
        sources: tuple[str, ...],
        exc: GatewayResponseError,
    ) -> None:
        if exc.gateway_usage is None:
            return
        self._record_ledger_entry(
            EvidenceLedgerEntry.from_gateway_usage(
                run_id=run_id,
                session_id=session_id,
                reason=reason,
                policy_signal=policy_signal.value,
                tool_class=tool_class,
                sources=sources,
                gateway_usage=exc.gateway_usage,
                queried_at=_utc_now(),
            )
        )


def _rejected_package_advisory_decision(*, reason: str) -> ToolInvocationDecision:
    return ToolInvocationDecision(
        decision=PolicyDecision.REJECT,
        reason=reason,
        tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
        policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
        reason_code=EvidenceReasonCode.PACKAGE_VERSION,
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)
