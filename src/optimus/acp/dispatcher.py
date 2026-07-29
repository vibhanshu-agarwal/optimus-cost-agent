from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from optimus.acp.errors import (
    DUPLICATE_REQUEST_ID,
    INTERNAL_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    MUTATION_FORBIDDEN,
    JsonRpcError,
    error_response,
    success_response,
)
from optimus.acp.request_ids import DuplicateRequestId, RequestIdTracker
from optimus.agent.models import AgentRunRequest, AgentRunResult
from optimus.agent.runner import AgentRunner
from optimus.evidence.acquisition import EvidenceAcquisitionService
from optimus.evidence.domain_policy import EvidenceDomainRejected
from optimus.evidence.ledger import EvidenceLedger
from optimus.evidence.models import (
    EvidenceExtractRequest,
    EvidenceExtractResponse,
    EvidencePackageLookupRequest,
    EvidenceRequest,
    EvidenceSearchResponse,
    EvidenceSecurityAdvisoryRequest,
)
from optimus.evidence.package_advisory import PackageAdvisoryService
from optimus.gateway.client import GatewayClient
from optimus.gateway.errors import GatewayError
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.gateway.tool_models import (
    GatewayToolContext,
    PackageLookupRequest,
    PackageLookupResult,
    SecurityAdvisoryRequest,
    SecurityAdvisoryResult,
)
from optimus.guardrails.audit import ToolInvocationAuditEvent
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import AgentState, RuntimeContext
from optimus.tools.mutation_tools import write_file
from optimus.tools.policy import EvidenceReasonCode, ToolPolicySignal
from optimus.tools.registry import ToolCallRejected


class JsonRpcDispatcher:
    def __init__(
        self,
        request_ids: RequestIdTracker | None = None,
        runtime_context: RuntimeContext | None = None,
        gateway_client: GatewayClient | None = None,
        evidence_service: EvidenceAcquisitionService | None = None,
        package_advisory_service: PackageAdvisoryService | None = None,
        agent_runner: AgentRunner | None = None,
        pre_tool_guard: PreToolGuard | None = None,
        workspace_root: str | Path | None = None,
        allowed_network_hosts: tuple[str, ...] = (),
    ) -> None:
        self._request_ids = request_ids or RequestIdTracker()
        self._runtime_context = runtime_context or RuntimeContext(
            execution_mode=ExecutionMode.PLAN,
            state=AgentState.CHAT_ONLY,
        )
        self._gateway_client = gateway_client
        self._evidence_service = evidence_service
        self._package_advisory_service = package_advisory_service
        self._agent_runner = agent_runner
        self._workspace_root = Path(workspace_root).resolve() if workspace_root is not None else None
        # One guard (and one audit sink) is built here, at the dispatcher's own
        # lifetime, and threaded into every guarded tool call below. This is
        # deliberate: if each handler built its own default guard instead (as
        # optimus.tools.mutation_tools does when no guard is supplied), every
        # call would get a throwaway PreToolGuard/InMemoryAuditSink pair that
        # is discarded on return, and ToolInvocationAuditEvent records would
        # never actually accumulate anywhere reachable. workspace_root is an
        # explicit constructor argument rather than an implicit Path.cwd() so
        # the workspace-containment boundary is a real, caller-supplied
        # configuration value instead of "wherever this process happened to
        # be launched from."
        self._pre_tool_guard = pre_tool_guard or PreToolGuard.for_workspace(
            workspace_root=workspace_root or Path.cwd(),
            allowed_network_hosts=allowed_network_hosts,
        )

    @property
    def agent_runner(self) -> AgentRunner | None:
        return self._agent_runner

    @property
    def workspace_root(self) -> Path | None:
        return self._workspace_root

    def audit_events(self) -> tuple[ToolInvocationAuditEvent, ...]:
        """Return every guard decision recorded across this dispatcher's lifetime."""
        return self._pre_tool_guard.audit_events()

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        try:
            self._request_ids.remember(request_id)
        except DuplicateRequestId:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(
                    code=DUPLICATE_REQUEST_ID,
                    message="duplicate request id",
                    data={"id": request_id},
                ),
            )

        if request.get("jsonrpc") != "2.0" or "method" not in request:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
            )

        method = request["method"]
        try:
            if method == "optimus.ping":
                return success_response(request_id=request_id, result={"message": "pong"})
            if method == "optimus.gateway.responses":
                if self._gateway_client is None:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=METHOD_NOT_FOUND, message="gateway client not configured"),
                    )
                params = request.get("params")
                if (
                    not isinstance(params, dict)
                    or not isinstance(params.get("model"), str)
                    or not isinstance(params.get("input"), str)
                    or "messages" in params
                ):
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                metadata = params.get("metadata")
                if metadata is not None and not isinstance(metadata, dict):
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                gateway_response = self._gateway_client.create_response(
                    model=params["model"],
                    input_text=params["input"],
                    metadata=metadata,
                )
                return success_response(
                    request_id=request_id,
                    result=_gateway_response_payload(gateway_response),
                )
            if method == "optimus.evidence.search":
                if self._evidence_service is None:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=METHOD_NOT_FOUND, message="evidence service not configured"),
                    )
                try:
                    evidence_request = EvidenceRequest.model_validate(request.get("params"))
                except ValidationError:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                response, ledger = self._evidence_service.search(
                    evidence_request,
                    execution_mode=self._runtime_context.execution_mode,
                )
                return success_response(
                    request_id=request_id,
                    result=_evidence_search_payload(response, ledger, evidence_request.run_id),
                )
            if method == "optimus.evidence.extract":
                if self._evidence_service is None:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=METHOD_NOT_FOUND, message="evidence service not configured"),
                    )
                try:
                    extract_request = EvidenceExtractRequest.model_validate(request.get("params"))
                except ValidationError:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                response, ledger = self._evidence_service.extract(
                    extract_request,
                    execution_mode=self._runtime_context.execution_mode,
                )
                return success_response(
                    request_id=request_id,
                    result=_evidence_extract_payload(response, ledger, extract_request.run_id),
                )
            if method == "optimus.evidence.package_lookup":
                if self._package_advisory_service is None:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(
                            code=METHOD_NOT_FOUND, message="package advisory service not configured"
                        ),
                    )
                try:
                    acp_request = EvidencePackageLookupRequest.model_validate(request.get("params"))
                except ValidationError:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                if (
                    acp_request.policy_signal is not ToolPolicySignal.DEPENDENCY_VERSION_CHECK
                    or acp_request.reason is not EvidenceReasonCode.PACKAGE_VERSION
                ):
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                tool_request = PackageLookupRequest(
                    context=GatewayToolContext(
                        run_id=acp_request.run_id,
                        session_id=acp_request.session_id,
                        execution_mode=self._runtime_context.execution_mode.value,
                    ),
                    package=acp_request.package,
                    ecosystem=acp_request.ecosystem,
                    version=acp_request.version,
                )
                result, ledger = self._package_advisory_service.package_lookup(
                    tool_request,
                    execution_mode=self._runtime_context.execution_mode,
                )
                return success_response(
                    request_id=request_id,
                    result=_evidence_package_lookup_payload(result, ledger, acp_request.run_id),
                )
            if method == "optimus.evidence.security_advisory":
                if self._package_advisory_service is None:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(
                            code=METHOD_NOT_FOUND, message="package advisory service not configured"
                        ),
                    )
                try:
                    acp_request = EvidenceSecurityAdvisoryRequest.model_validate(request.get("params"))
                except ValidationError:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                if (
                    acp_request.policy_signal is not ToolPolicySignal.SECURITY_OR_CVE_CHECK
                    or acp_request.reason is not EvidenceReasonCode.SECURITY_ADVISORY
                ):
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                tool_request = SecurityAdvisoryRequest(
                    context=GatewayToolContext(
                        run_id=acp_request.run_id,
                        session_id=acp_request.session_id,
                        execution_mode=self._runtime_context.execution_mode.value,
                    ),
                    identifier=acp_request.identifier,
                    ecosystem=acp_request.ecosystem,
                    version=acp_request.version,
                )
                result, ledger = self._package_advisory_service.security_advisory(
                    tool_request,
                    execution_mode=self._runtime_context.execution_mode,
                )
                return success_response(
                    request_id=request_id,
                    result=_evidence_security_advisory_payload(result, ledger, acp_request.run_id),
                )
            if method == "optimus.agent.run":
                if self._agent_runner is None:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=METHOD_NOT_FOUND, message="agent runner not configured"),
                    )
                try:
                    agent_request = AgentRunRequest.model_validate(request.get("params"))
                except ValidationError:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                if self._workspace_root is not None and not agent_request.workspace_root.is_relative_to(
                    self._workspace_root
                ):
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="workspace_root outside configured workspace"),
                    )
                result = self._agent_runner.run(agent_request)
                return success_response(request_id=request_id, result=_agent_run_result_payload(result))
            if method == "optimus.mutation.writeFile":
                params = request.get("params")
                if not isinstance(params, dict) or not isinstance(params.get("path"), str):
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                write_file(
                    Path(params["path"]),
                    str(params.get("content", "")),
                    context=self._runtime_context,
                    guard=self._pre_tool_guard,
                )
                return success_response(request_id=request_id, result={"written": params["path"]})
        except MutationForbidden as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=MUTATION_FORBIDDEN, message=str(exc)),
            )
        except ToolCallRejected as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INVALID_REQUEST, message=str(exc)),
            )
        except EvidenceDomainRejected as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INVALID_REQUEST, message=str(exc)),
            )
        except ValueError as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INTERNAL_ERROR, message=str(exc)),
            )
        except GatewayError as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INTERNAL_ERROR, message=str(exc)),
            )

        return error_response(
            request_id=request_id,
            error=JsonRpcError(code=METHOD_NOT_FOUND, message=f"method not found: {method}"),
        )


def _agent_run_result_payload(result: AgentRunResult) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    payload["total_cost_usd"] = str(result.total_cost_usd)
    payload["tool_calls"] = [
        {**tool_call, "cost_usd": str(tool_call["cost_usd"])} for tool_call in payload.get("tool_calls", [])
    ]
    return payload


def _gateway_usage_payload(usage: GatewayUsage) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "gateway_request_id": usage.gateway_request_id,
        "provider": usage.provider,
        "provider_request_id": usage.provider_request_id,
        "cache_hit": usage.cache_hit,
        "billing_units": usage.billing_units,
        "cost_usd": str(usage.cost_usd),
    }
    for field in (
        "service",
        "native_unit",
        "model",
        "model_version",
        "price_snapshot_id",
        "resolved_provider",
        "resolved_model",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "reasoning_tokens",
        "cached_tokens",
        "cache_age_seconds",
    ):
        value = getattr(usage, field)
        if value is not None:
            payload[field] = str(value) if isinstance(value, Decimal) else value
    return payload


def _gateway_response_payload(response: GatewayResponse) -> dict[str, Any]:
    return {
        "response_id": response.response_id,
        "output_text": response.output_text,
        "gateway_usage": _gateway_usage_payload(response.gateway_usage),
    }


def _evidence_search_payload(
    response: EvidenceSearchResponse,
    ledger: EvidenceLedger,
    run_id: str,
) -> dict[str, Any]:
    return {
        "results": [
            {"title": result.title, "url": result.url_text, "snippet": result.snippet}
            for result in response.results
        ],
        "gateway_usage": _gateway_usage_payload(response.gateway_usage),
        "ledger_run_total_cost_usd": str(ledger.total_cost_usd(run_id=run_id)),
        "ledger_run_total_billing_units": ledger.total_billing_units(run_id=run_id),
    }


def _evidence_extract_payload(
    response: EvidenceExtractResponse,
    ledger: EvidenceLedger,
    run_id: str,
) -> dict[str, Any]:
    return {
        "url": response.url_text,
        "title": response.title,
        "content": response.content,
        "trust": response.trust,
        "gateway_usage": _gateway_usage_payload(response.gateway_usage),
        "ledger_run_total_cost_usd": str(ledger.total_cost_usd(run_id=run_id)),
        "ledger_run_total_billing_units": ledger.total_billing_units(run_id=run_id),
    }


def _ledger_usage_payload(ledger: EvidenceLedger, run_id: str) -> dict[str, Any]:
    """Reconstruct the last-recorded gateway usage fields for one run from the ledger.

    Package/advisory results carry no ``gateway_usage`` field of their own
    (unlike ``EvidenceSearchResponse``/``EvidenceExtractResponse``), so the ACP
    payload copies the usage fields the service just recorded to the ledger.
    """
    entries = ledger.entries_for_run(run_id)
    entry = entries[-1]
    return {
        "gateway_request_id": entry.gateway_request_id,
        "provider": entry.provider,
        "provider_request_id": entry.provider_request_id,
        "cache_hit": entry.cache_hit,
        "billing_units": entry.billing_units,
        "cost_usd": str(entry.cost_usd),
    }


def _evidence_package_lookup_payload(
    result: PackageLookupResult,
    ledger: EvidenceLedger,
    run_id: str,
) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    payload["gateway_usage"] = _ledger_usage_payload(ledger, run_id)
    payload["ledger_run_total_cost_usd"] = str(ledger.total_cost_usd(run_id=run_id))
    payload["ledger_run_total_billing_units"] = ledger.total_billing_units(run_id=run_id)
    return payload


def _evidence_security_advisory_payload(
    result: SecurityAdvisoryResult,
    ledger: EvidenceLedger,
    run_id: str,
) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    payload["gateway_usage"] = _ledger_usage_payload(ledger, run_id)
    payload["ledger_run_total_cost_usd"] = str(ledger.total_cost_usd(run_id=run_id))
    payload["ledger_run_total_billing_units"] = ledger.total_billing_units(run_id=run_id)
    return payload
