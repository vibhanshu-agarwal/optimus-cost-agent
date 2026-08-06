"""Gateway-side MCP call admission, result validation, and release gating."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from optimus_gateway.mcp_connections import MCPConnectionManager
from optimus_gateway.mcp_models import (
    MCPBindingSummary,
    MCPCallRequest,
    MCPCallResponse,
    parse_namespaced_tool_name,
)
from optimus_gateway.mcp_profiles import MCPProfileRegistry
from optimus_gateway.mcp_usage import MCPUsageRecord, MCPUsageWriter


class MCPResultPolicyError(ValueError):
    def __init__(self, message: str, *, disposition: str = "mcp.result_invalid") -> None:
        super().__init__(message)
        self.disposition = disposition


class MCPInvocationError(RuntimeError):
    def __init__(self, disposition: str, *, status: int = 403) -> None:
        super().__init__(disposition)
        self.disposition = disposition
        self.status = status


def validate_mcp_result(
    raw_result: Mapping[str, Any], *, expected_binding: MCPBindingSummary
) -> MCPCallResponse:
    """Strictly validate a Gateway-shaped result before any release decision."""

    if not isinstance(raw_result, Mapping):
        raise MCPResultPolicyError("MCP result must be an object")
    try:
        response = MCPCallResponse.model_validate(dict(raw_result))
    except ValidationError as exc:
        raise MCPResultPolicyError("MCP result failed strict validation") from exc
    if response.result_type != "complete":
        raise MCPResultPolicyError(
            "MCP result is input_required and is not releasable",
            disposition="mcp.call.input_required",
        )
    if response.binding != expected_binding:
        raise MCPResultPolicyError("MCP result binding does not match the request")
    return response


class MCPInvocationBroker:
    """Perform one admitted MCP call with no automatic upstream retry."""

    def call(
        self,
        *,
        request: MCPCallRequest,
        registry: MCPProfileRegistry,
        connection_manager: MCPConnectionManager,
        usage_writer: MCPUsageWriter,
    ) -> MCPCallResponse:
        admission = registry.for_call(request)
        if not admission.accepted or admission.profile is None:
            raise MCPInvocationError(admission.disposition)
        profile = admission.profile

        # Recheck immediately before opening/dispatching.  This is intentionally
        # separate from the initial admission so lifecycle changes cannot race
        # into an already-authorized transport call.
        latest = registry.for_call(request)
        if not latest.accepted or latest.profile is None:
            raise MCPInvocationError(latest.disposition)
        profile = latest.profile

        try:
            _, upstream_tool_name = parse_namespaced_tool_name(
                request.tool_name, expected_profile_id=profile.profile_id
            )
        except ValueError as exc:
            raise MCPInvocationError("mcp.tool_namespace_invalid") from exc

        admit = getattr(usage_writer, "admit", None)
        if callable(admit):
            try:
                admit(request=request, profile=profile)
            except MCPInvocationError:
                raise
            except Exception as exc:  # noqa: BLE001 - budget details stay Gateway-internal
                raise MCPInvocationError("mcp.call_budget_denied", status=429) from exc

        started = time.monotonic()
        try:
            transport = connection_manager.open_for(profile)
            raw_result = transport.tools_call(
                upstream_tool_name=upstream_tool_name,
                arguments=dict(request.arguments),
                protocol_version="2026-07-28",
            )
        except MCPInvocationError:
            raise
        except Exception as exc:  # noqa: BLE001 - upstream detail is not a client error
            raise MCPInvocationError("mcp.call_indeterminate", status=502) from exc

        expected_binding = MCPBindingSummary(
            profile_id=request.profile_id,
            profile_revision=request.profile_revision,
            manifest_hash=request.manifest_hash,
        )
        try:
            response = _validate_and_wrap_upstream_result(
                raw_result,
                expected_binding=expected_binding,
                transport=profile.transport,
            )
        except MCPResultPolicyError as exc:
            raise MCPInvocationError(exc.disposition, status=422) from exc

        if response.transport != profile.transport or response.protocol_version != "2026-07-28":
            raise MCPInvocationError("mcp.result_transport_mismatch", status=422)
        try:
            response_bytes = len(
                json.dumps(response.model_dump(mode="json"), separators=(",", ":"), ensure_ascii=False).encode(
                    "utf-8"
                )
            )
        except (TypeError, ValueError) as exc:
            raise MCPInvocationError("mcp.result_invalid", status=422) from exc
        if response_bytes > profile.limits.max_result_bytes:
            raise MCPInvocationError("mcp.result_budget_exceeded", status=429)

        if response.attribution == "unavailable" and not profile.attribution_policy.allow_unattributed_spend:
            raise MCPInvocationError("mcp.budget.unattributed_spend_denied", status=402)
        if response.attribution == "explicit_zero" and not profile.attribution_policy.declared_free:
            raise MCPInvocationError("mcp.budget.explicit_zero_not_declared_free", status=403)

        request_bytes = len(
            json.dumps(
                {"name": upstream_tool_name, "arguments": request.arguments},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        usage_record = MCPUsageRecord(
            gateway_request_id=response.usage.gateway_request_id,
            run_id=request.run_id,
            session_id=request.session_id,
            request_id=request.request_id,
            profile_id=request.profile_id,
            profile_revision=request.profile_revision,
            namespaced_tool_name=request.tool_name,
            upstream_tool_name=upstream_tool_name,
            transport=response.transport,
            disposition=response.disposition,
            attribution=response.attribution,
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            request_bytes=request_bytes,
            response_bytes=response_bytes,
            provider_request_id=None,
            billing_units=response.usage.billing_units,
            cost_usd=response.usage.cost_usd,
        )

        try:
            usage_writer.persist(usage_record)
        except Exception as exc:  # noqa: BLE001 - persistence detail is not client-visible
            raise MCPInvocationError("mcp.usage_persistence_failed", status=503) from exc
        return response


def _validate_and_wrap_upstream_result(
    raw_result: Mapping[str, Any], *, expected_binding: MCPBindingSummary, transport: str
) -> MCPCallResponse:
    """Turn a standard MCP tools/call result into the typed Gateway envelope."""

    if not isinstance(raw_result, Mapping):
        raise MCPResultPolicyError("MCP result must be an object")
    if "result_type" in raw_result:
        return validate_mcp_result(raw_result, expected_binding=expected_binding)
    if set(raw_result) - {"content", "isError"}:
        raise MCPResultPolicyError("MCP result contains unsupported fields")
    is_error = raw_result.get("isError", False)
    if not isinstance(is_error, bool):
        raise MCPResultPolicyError("MCP result isError must be boolean")
    if is_error:
        raise MCPResultPolicyError(
            "MCP upstream result is an error",
            disposition="mcp.call.upstream_error",
        )
    content = raw_result.get("content")
    if not isinstance(content, list):
        raise MCPResultPolicyError("MCP result content must be an array")
    wrapped = {
        "result_type": "complete",
        "content": content,
        "disposition": "mcp.call.complete",
        "binding": expected_binding.model_dump(mode="json"),
        "transport": transport,
        "protocol_version": "2026-07-28",
        "attribution": "unavailable",
        "usage": {
            "gateway_request_id": f"gw-mcp-{uuid.uuid4().hex}",
            "attribution": "unavailable",
        },
    }
    return validate_mcp_result(wrapped, expected_binding=expected_binding)


__all__ = [
    "MCPInvocationBroker",
    "MCPInvocationError",
    "MCPResultPolicyError",
    "MCPUsageWriter",
    "validate_mcp_result",
]
