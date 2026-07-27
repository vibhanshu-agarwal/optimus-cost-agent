"""Authenticated Gateway tool route handlers.

Plan 11.2 (``P11-FEAT-GATEWAY-TOOLS``), Task 4. Every handler follows the
same order: authenticate the bearer credential, validate the typed request
body, resolve the authenticated context, apply the Gateway-owned
policy/domain/provenance/call-cap checks, invoke the injected server-side
provider, and build the common typed envelope. Provider output and caller
metadata are always untrusted data; provider errors and state-store outages
are sanitized before they ever reach the HTTP response.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from optimus_gateway.models import GatewayServiceConfig, ToolClass, ToolPolicySignal, authorize_bearer
from optimus_gateway.responses import assert_gateway_usage_contract, sanitize_error_message
from optimus_gateway.tool_models import (
    GatewayToolValidationError,
    PackageLookupGatewayRequest,
    ProviderUsage,
    SecurityAdvisoryGatewayRequest,
    WebExtractGatewayRequest,
    WebSearchGatewayRequest,
    package_lookup_result_payload,
    resolve_web_search_policy_signal,
    security_advisory_result_payload,
    validate_package_lookup_body,
    validate_security_advisory_body,
    validate_web_extract_body,
    validate_web_search_body,
    web_extract_result_payload,
    web_search_result_payload,
)
from optimus_gateway.tool_policy import GatewayToolPolicy, GatewayToolPolicyError
from optimus_gateway.tool_providers import AdvisoryToolProvider, PackageToolProvider, WebToolProvider
from optimus_gateway.tool_state import GatewayToolCallCapExceeded, GatewayToolStateStore, GatewayToolStateUnavailable

# The Gateway authenticates exactly one shared-secret bearer credential (see
# GatewayServiceConfig); there is no separate multi-subject identity system
# yet, so every authenticated call resolves to this constant subject.
_AUTHENTICATED_SUBJECT = "gateway-client"
_DEFAULT_MAX_CALLS_PER_TOOL = 5

# Public so server.py's route dispatch and any external caller share one
# definition of exactly which paths this handler serves.
TOOL_ROUTE_PATHS = frozenset(
    {
        "/v1/tools/web/search",
        "/v1/tools/web/extract",
        "/v1/tools/package/lookup",
        "/v1/tools/security/advisory",
    }
)


@dataclass(frozen=True)
class GatewayToolDependencies:
    """Injectable Gateway-side tool boundary threaded through ``serve_gateway``.

    Groups the three server-side provider protocols (web covers both search
    and extract), the Gateway-owned policy, and the Gateway-owned state
    store. ``max_calls_per_tool`` is the configured per-``run_id`` +
    ``tool_class`` call cap; package lookup and security advisory share one
    counter because both use ``ToolClass.PACKAGE_AND_ADVISORY_METADATA``.
    """

    web_provider: WebToolProvider
    package_provider: PackageToolProvider
    advisory_provider: AdvisoryToolProvider
    policy: GatewayToolPolicy
    state_store: GatewayToolStateStore
    max_calls_per_tool: int = _DEFAULT_MAX_CALLS_PER_TOOL


def handle_tool_request(
    *,
    authorization_header: str | None,
    path: str,
    request_body: Mapping[str, Any],
    config: GatewayServiceConfig,
    dependencies: GatewayToolDependencies,
) -> tuple[int, dict[str, Any]]:
    if not authorize_bearer(authorization_header=authorization_header, shared_secret=config.shared_secret):
        return 401, {"error": "unauthorized"}

    if path == "/v1/tools/web/search":
        return _handle_web_search(request_body, dependencies)
    if path == "/v1/tools/web/extract":
        return _handle_web_extract(request_body, dependencies)
    if path == "/v1/tools/package/lookup":
        return _handle_package_lookup(request_body, dependencies)
    if path == "/v1/tools/security/advisory":
        return _handle_security_advisory(request_body, dependencies)
    return 404, {"error": "not found"}


def _handle_web_search(body: Mapping[str, Any], deps: GatewayToolDependencies) -> tuple[int, dict[str, Any]]:
    try:
        fields = validate_web_search_body(body)
    except GatewayToolValidationError as exc:
        return _validation_error_response(exc)

    try:
        context = deps.policy.resolve_context(request_body=body, authenticated_subject=_AUTHENTICATED_SUBJECT)
    except GatewayToolPolicyError as exc:
        return _context_error_response(exc)

    policy_signal = resolve_web_search_policy_signal(fields.reason)
    if policy_signal is None:
        return _policy_denied_response(
            rule_id="POLICY_SIGNAL_MISMATCH",
            reason=f"reason does not authorize web search: {fields.reason!r}",
        )

    decision = deps.policy.authorize(
        context=context,
        tool_class=ToolClass.WEB_SEARCH,
        policy_signal=policy_signal,
        requested_domains=fields.allowed_domains,
        resolved_urls=(),
    )
    if not decision.allowed:
        return _policy_denied_response(rule_id=decision.rule_id, reason=decision.reason)

    try:
        deps.state_store.increment_call(
            run_id=context.run_id, tool_class=ToolClass.WEB_SEARCH, max_calls=deps.max_calls_per_tool
        )
    except GatewayToolCallCapExceeded as exc:
        return _cap_exceeded_response(exc)
    except GatewayToolStateUnavailable as exc:
        return _state_unavailable_response(exc)

    provider_request = WebSearchGatewayRequest(
        context=context,
        query=fields.query,
        allowed_domains=decision.effective_domains,
        result_cap=fields.result_cap,
        search_depth=fields.search_depth,
    )
    try:
        provider_result = deps.web_provider.search(provider_request)
    except Exception as exc:  # noqa: BLE001 - provider faults are always sanitized before export
        return _provider_error_response(exc)

    result_urls = tuple(item.url for item in provider_result.results)
    revalidation = deps.policy.authorize(
        context=context,
        tool_class=ToolClass.WEB_SEARCH,
        policy_signal=policy_signal,
        requested_domains=decision.effective_domains,
        resolved_urls=result_urls,
    )
    if not revalidation.allowed:
        return _policy_denied_response(rule_id=revalidation.rule_id, reason=revalidation.reason)

    try:
        search_id = deps.state_store.record_search(run_id=context.run_id, source_urls=result_urls)
    except GatewayToolStateUnavailable as exc:
        return _state_unavailable_response(exc)

    gateway_usage = _build_gateway_usage(provider_result.usage)
    try:
        assert_gateway_usage_contract(gateway_usage)
    except ValueError as exc:
        return _malformed_provider_result_response(exc)

    return 200, {
        "tool_class": str(ToolClass.WEB_SEARCH),
        "policy_signal": str(policy_signal),
        "run_id": context.run_id,
        "result": web_search_result_payload(provider_result),
        "provenance": {"search_id": search_id, "source_urls": list(result_urls), "trust": "untrusted"},
        "gateway_usage": gateway_usage,
    }


def _handle_web_extract(body: Mapping[str, Any], deps: GatewayToolDependencies) -> tuple[int, dict[str, Any]]:
    try:
        fields = validate_web_extract_body(body)
    except GatewayToolValidationError as exc:
        return _validation_error_response(exc)

    try:
        context = deps.policy.resolve_context(request_body=body, authenticated_subject=_AUTHENTICATED_SUBJECT)
    except GatewayToolPolicyError as exc:
        return _context_error_response(exc)

    decision = deps.policy.authorize(
        context=context,
        tool_class=ToolClass.WEB_EXTRACT,
        policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
        requested_domains=(),
        resolved_urls=fields.urls,
    )
    if not decision.allowed:
        return _policy_denied_response(rule_id=decision.rule_id, reason=decision.reason)

    try:
        approved_urls = deps.state_store.search_result_urls(run_id=context.run_id)
    except GatewayToolStateUnavailable as exc:
        return _state_unavailable_response(exc)

    if any(url not in approved_urls for url in fields.urls):
        return _policy_denied_response(
            rule_id="URL_NOT_IN_SEARCH_PROVENANCE",
            reason="extract URL is not present in a prior Gateway-logged search result set for this run_id",
        )

    try:
        deps.state_store.increment_call(
            run_id=context.run_id, tool_class=ToolClass.WEB_EXTRACT, max_calls=deps.max_calls_per_tool
        )
    except GatewayToolCallCapExceeded as exc:
        return _cap_exceeded_response(exc)
    except GatewayToolStateUnavailable as exc:
        return _state_unavailable_response(exc)

    provider_request = WebExtractGatewayRequest(
        context=context, urls=fields.urls, max_chars_per_source=fields.max_chars_per_source
    )
    try:
        provider_result = deps.web_provider.extract(provider_request)
    except Exception as exc:  # noqa: BLE001 - provider faults are always sanitized before export
        return _provider_error_response(exc)

    if any(item.url not in fields.urls for item in provider_result.items):
        return _policy_denied_response(
            rule_id="RETURNED_URL_NOT_REQUESTED",
            reason="extract provider returned a URL that was not requested",
        )

    gateway_usage = _build_gateway_usage(provider_result.usage)
    try:
        assert_gateway_usage_contract(gateway_usage)
    except ValueError as exc:
        return _malformed_provider_result_response(exc)

    return 200, {
        "tool_class": str(ToolClass.WEB_EXTRACT),
        "policy_signal": str(ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE),
        "run_id": context.run_id,
        "result": web_extract_result_payload(provider_result),
        "provenance": {"search_id": None, "source_urls": list(fields.urls), "trust": "untrusted"},
        "gateway_usage": gateway_usage,
    }


def _handle_package_lookup(body: Mapping[str, Any], deps: GatewayToolDependencies) -> tuple[int, dict[str, Any]]:
    try:
        fields = validate_package_lookup_body(body)
    except GatewayToolValidationError as exc:
        return _validation_error_response(exc)

    try:
        context = deps.policy.resolve_context(request_body=body, authenticated_subject=_AUTHENTICATED_SUBJECT)
    except GatewayToolPolicyError as exc:
        return _context_error_response(exc)

    decision = deps.policy.authorize(
        context=context,
        tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
        policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
        requested_domains=(),
        resolved_urls=(),
    )
    if not decision.allowed:
        return _policy_denied_response(rule_id=decision.rule_id, reason=decision.reason)

    try:
        deps.state_store.increment_call(
            run_id=context.run_id,
            tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
            max_calls=deps.max_calls_per_tool,
        )
    except GatewayToolCallCapExceeded as exc:
        return _cap_exceeded_response(exc)
    except GatewayToolStateUnavailable as exc:
        return _state_unavailable_response(exc)

    provider_request = PackageLookupGatewayRequest(
        context=context, package=fields.package, ecosystem=fields.ecosystem, version=fields.version
    )
    try:
        provider_result = deps.package_provider.lookup(provider_request)
    except Exception as exc:  # noqa: BLE001 - provider faults are always sanitized before export
        return _provider_error_response(exc)

    citation_check = deps.policy.authorize(
        context=context,
        tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
        policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
        requested_domains=(),
        resolved_urls=provider_result.citations,
    )
    if not citation_check.allowed:
        return _policy_denied_response(rule_id=citation_check.rule_id, reason=citation_check.reason)

    gateway_usage = _build_gateway_usage(provider_result.usage)
    try:
        assert_gateway_usage_contract(gateway_usage)
    except ValueError as exc:
        return _malformed_provider_result_response(exc)

    return 200, {
        "tool_class": str(ToolClass.PACKAGE_AND_ADVISORY_METADATA),
        "policy_signal": str(ToolPolicySignal.DEPENDENCY_VERSION_CHECK),
        "run_id": context.run_id,
        "result": package_lookup_result_payload(provider_result),
        "provenance": {"search_id": None, "source_urls": list(provider_result.citations), "trust": "untrusted"},
        "gateway_usage": gateway_usage,
    }


def _handle_security_advisory(body: Mapping[str, Any], deps: GatewayToolDependencies) -> tuple[int, dict[str, Any]]:
    try:
        fields = validate_security_advisory_body(body)
    except GatewayToolValidationError as exc:
        return _validation_error_response(exc)

    try:
        context = deps.policy.resolve_context(request_body=body, authenticated_subject=_AUTHENTICATED_SUBJECT)
    except GatewayToolPolicyError as exc:
        return _context_error_response(exc)

    decision = deps.policy.authorize(
        context=context,
        tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
        policy_signal=ToolPolicySignal.SECURITY_OR_CVE_CHECK,
        requested_domains=(),
        resolved_urls=(),
    )
    if not decision.allowed:
        return _policy_denied_response(rule_id=decision.rule_id, reason=decision.reason)

    try:
        deps.state_store.increment_call(
            run_id=context.run_id,
            tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
            max_calls=deps.max_calls_per_tool,
        )
    except GatewayToolCallCapExceeded as exc:
        return _cap_exceeded_response(exc)
    except GatewayToolStateUnavailable as exc:
        return _state_unavailable_response(exc)

    provider_request = SecurityAdvisoryGatewayRequest(
        context=context, identifier=fields.identifier, ecosystem=fields.ecosystem, version=fields.version
    )
    try:
        provider_result = deps.advisory_provider.lookup(provider_request)
    except Exception as exc:  # noqa: BLE001 - provider faults are always sanitized before export
        return _provider_error_response(exc)

    all_citations = tuple(
        citation for advisory in provider_result.advisories for citation in advisory.citations
    )
    citation_check = deps.policy.authorize(
        context=context,
        tool_class=ToolClass.PACKAGE_AND_ADVISORY_METADATA,
        policy_signal=ToolPolicySignal.SECURITY_OR_CVE_CHECK,
        requested_domains=(),
        resolved_urls=all_citations,
    )
    if not citation_check.allowed:
        return _policy_denied_response(rule_id=citation_check.rule_id, reason=citation_check.reason)

    gateway_usage = _build_gateway_usage(provider_result.usage)
    try:
        assert_gateway_usage_contract(gateway_usage)
    except ValueError as exc:
        return _malformed_provider_result_response(exc)

    return 200, {
        "tool_class": str(ToolClass.PACKAGE_AND_ADVISORY_METADATA),
        "policy_signal": str(ToolPolicySignal.SECURITY_OR_CVE_CHECK),
        "run_id": context.run_id,
        "result": security_advisory_result_payload(provider_result),
        "provenance": {"search_id": None, "source_urls": list(all_citations), "trust": "untrusted"},
        "gateway_usage": gateway_usage,
    }


def _build_gateway_usage(usage: ProviderUsage) -> dict[str, Any]:
    return {
        "gateway_request_id": _new_gateway_request_id(),
        "provider": usage.provider,
        "provider_request_id": usage.provider_request_id,
        "cache_hit": usage.cache_hit,
        "billing_units": usage.billing_units,
        "cost_usd": usage.cost_usd,
    }


def _validation_error_response(exc: GatewayToolValidationError) -> tuple[int, dict[str, Any]]:
    return 400, {"error": sanitize_error_message(str(exc))}


def _context_error_response(exc: GatewayToolPolicyError) -> tuple[int, dict[str, Any]]:
    return 400, {"error": sanitize_error_message(str(exc))}


def _policy_denied_response(*, rule_id: str, reason: str) -> tuple[int, dict[str, Any]]:
    return 403, {
        "error": sanitize_error_message(reason),
        "rule_id": rule_id,
        "gateway_request_id": _new_gateway_request_id(),
    }


def _cap_exceeded_response(exc: GatewayToolCallCapExceeded) -> tuple[int, dict[str, Any]]:
    return 429, {
        "error": sanitize_error_message(str(exc)),
        "rule_id": "CALL_CAP_EXCEEDED",
        "gateway_request_id": _new_gateway_request_id(),
    }


def _state_unavailable_response(exc: GatewayToolStateUnavailable) -> tuple[int, dict[str, Any]]:
    del exc  # never surfaced: connection/backend detail must not leak into the response
    return 503, {
        "error": "gateway tool state is unavailable",
        "rule_id": "STATE_UNAVAILABLE",
        "gateway_request_id": _new_gateway_request_id(),
    }


def _provider_error_response(exc: Exception) -> tuple[int, dict[str, Any]]:
    return 502, {
        "error": sanitize_error_message(str(exc)),
        "rule_id": "PROVIDER_FAILURE",
        "gateway_request_id": _new_gateway_request_id(),
    }


def _malformed_provider_result_response(exc: ValueError) -> tuple[int, dict[str, Any]]:
    return 502, {
        "error": sanitize_error_message(str(exc)),
        "rule_id": "MALFORMED_PROVIDER_RESULT",
        "gateway_request_id": _new_gateway_request_id(),
    }


def _new_gateway_request_id() -> str:
    return f"gw-tool-{uuid.uuid4().hex}"
