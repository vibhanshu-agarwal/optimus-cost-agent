"""Gateway-owned tool policy: context resolution and server-side revalidation.

Plan 11.2 (``P11-FEAT-GATEWAY-TOOLS``), Task 3. This module independently
resolves the authenticated request context and revalidates tool class,
policy signal, and domain/HTTPS constraints for every Gateway tool call. It
never trusts caller-supplied ``approved_urls``/allowlists as authoritative;
the effective allowlist is always the intersection of the requested domains
with the Gateway's own configured policy.

The HTTPS-hostname and domain-matching helpers below intentionally mirror
``optimus.net.https`` and ``optimus.evidence.domain_policy`` byte-for-byte in
behavior. They are reimplemented here (not imported) so that
``optimus_gateway`` keeps its zero-``optimus.*``-import, independently
deployable boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

from optimus_gateway.models import GatewayToolContext, ToolClass, ToolPolicySignal

_SUPPORTED_EXECUTION_MODES = frozenset({"plan", "chat", "agent"})

_WEB_SEARCH_SIGNALS = frozenset(
    {
        ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        ToolPolicySignal.CURRENT_OR_LATEST_FACT,
        ToolPolicySignal.API_OR_FRAMEWORK_FACT_NOT_IN_REPO,
    }
)

_PACKAGE_ADVISORY_SIGNALS = frozenset(
    {
        ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
        ToolPolicySignal.SECURITY_OR_CVE_CHECK,
    }
)


class GatewayToolPolicyError(ValueError):
    """Raised when a tool request's context cannot be resolved. Carries a stable rule_id."""

    def __init__(self, rule_id: str, message: str) -> None:
        super().__init__(message)
        self.rule_id = rule_id


@dataclass(frozen=True)
class GatewayToolDecision:
    """A structured, audit-stable authorization decision."""

    allowed: bool
    rule_id: str
    reason: str
    effective_domains: tuple[str, ...] = ()
    resolved_urls: tuple[str, ...] = ()


class GatewayToolPolicy:
    """Resolves authenticated tool-call context and revalidates policy independently.

    :ivar _allowed_domains: The Gateway's own configured domain allowlist. Requested
        domains are only ever narrowed against this set; they can never widen it.
    """

    def __init__(self, *, allowed_domains: tuple[str, ...]) -> None:
        normalized = tuple(
            sorted({domain for domain in (_normalize_domain(value) for value in allowed_domains) if domain})
        )
        if not normalized:
            raise ValueError("allowed_domains must not be empty")
        self._allowed_domains = normalized

    def resolve_context(
        self,
        *,
        request_body: Mapping[str, Any],
        authenticated_subject: str,
    ) -> GatewayToolContext:
        if not isinstance(authenticated_subject, str) or not authenticated_subject.strip():
            raise GatewayToolPolicyError("MISSING_IDENTITY", "authenticated_subject is required")

        if not isinstance(request_body, Mapping):
            raise GatewayToolPolicyError("MALFORMED_METADATA", "request body must be a JSON object")

        metadata = request_body.get("context")
        if not isinstance(metadata, Mapping):
            raise GatewayToolPolicyError("MALFORMED_METADATA", "context metadata is required")

        run_id = metadata.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise GatewayToolPolicyError("MISSING_RUN_ID", "run_id is required")

        execution_mode = metadata.get("execution_mode")
        if not isinstance(execution_mode, str) or execution_mode.strip().lower() not in _SUPPORTED_EXECUTION_MODES:
            raise GatewayToolPolicyError(
                "UNSUPPORTED_EXECUTION_MODE", f"unsupported execution_mode: {execution_mode!r}"
            )

        session_id = _optional_string(metadata, "session_id")
        org_id = _optional_string(metadata, "org_id")
        project_id = _optional_string(metadata, "project_id")
        model = _optional_string(metadata, "model")

        return GatewayToolContext(
            run_id=run_id.strip(),
            authenticated_subject=authenticated_subject.strip(),
            session_id=session_id,
            execution_mode=execution_mode.strip().lower(),
            org_id=org_id,
            project_id=project_id,
            model=model,
        )

    def authorize(
        self,
        *,
        context: GatewayToolContext,
        tool_class: ToolClass,
        policy_signal: ToolPolicySignal,
        requested_domains: tuple[str, ...],
        resolved_urls: tuple[str, ...],
    ) -> GatewayToolDecision:
        del context  # Reserved for org/project-scoped policy; not yet differentiated.

        signal_error = self._check_policy_signal(tool_class=tool_class, policy_signal=policy_signal)
        if signal_error is not None:
            return signal_error

        effective_domains = tuple(
            domain
            for domain in (_normalize_domain(value) for value in requested_domains)
            if domain and any(_domain_matches_configured(domain, configured) for configured in self._allowed_domains)
        )
        if requested_domains and not effective_domains:
            return GatewayToolDecision(
                allowed=False,
                rule_id="EMPTY_DOMAIN_INTERSECTION",
                reason="allowed_domains not in configured Gateway policy allowlist",
            )

        for url in resolved_urls:
            host = _https_hostname(url)
            if host is None:
                return GatewayToolDecision(
                    allowed=False,
                    rule_id="NON_HTTPS_URL",
                    reason=f"URL is not HTTPS: {url}",
                    effective_domains=effective_domains,
                )
            allowlist = effective_domains or self._allowed_domains
            if not any(_host_matches_domain(host, domain) for domain in allowlist):
                return GatewayToolDecision(
                    allowed=False,
                    rule_id="URL_DOMAIN_NOT_ALLOWED",
                    reason=f"URL host not in effective allowed domains: {url}",
                    effective_domains=effective_domains,
                )

        return GatewayToolDecision(
            allowed=True,
            rule_id="ALLOWED",
            reason="policy checks passed",
            effective_domains=effective_domains,
            resolved_urls=resolved_urls,
        )

    def _check_policy_signal(
        self,
        *,
        tool_class: ToolClass,
        policy_signal: ToolPolicySignal,
    ) -> GatewayToolDecision | None:
        if tool_class is ToolClass.WEB_SEARCH:
            if policy_signal not in _WEB_SEARCH_SIGNALS:
                return GatewayToolDecision(
                    allowed=False,
                    rule_id="POLICY_SIGNAL_MISMATCH",
                    reason=f"policy_signal {policy_signal!r} does not authorize web search",
                )
            return None
        if tool_class is ToolClass.WEB_EXTRACT:
            if policy_signal is not ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE:
                return GatewayToolDecision(
                    allowed=False,
                    rule_id="POLICY_SIGNAL_MISMATCH",
                    reason="web extract requires approved search-result provenance",
                )
            return None
        if tool_class is ToolClass.PACKAGE_AND_ADVISORY_METADATA:
            if policy_signal not in _PACKAGE_ADVISORY_SIGNALS:
                return GatewayToolDecision(
                    allowed=False,
                    rule_id="POLICY_SIGNAL_MISMATCH",
                    reason=f"policy_signal {policy_signal!r} does not authorize package/advisory metadata",
                )
            return None
        return GatewayToolDecision(
            allowed=False,
            rule_id="UNSUPPORTED_TOOL_CLASS",
            reason=f"unsupported tool class: {tool_class!r}",
        )


def _optional_string(metadata: Mapping[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise GatewayToolPolicyError("MALFORMED_METADATA", f"{key} must be a string")
    return value


def _https_hostname(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname is None:
        return None
    return parsed.hostname.lower().rstrip(".")


def _normalize_domain(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        if parsed.hostname is None:
            return ""
        return parsed.hostname.lower().rstrip(".")
    bare = value.split("/", 1)[0].strip()
    if bare.startswith("["):
        end = bare.find("]")
        if end == -1:
            return ""
        return bare[1:end].lower()
    host = bare.rsplit(":", 1)[0] if ":" in bare else bare
    return host.lower().strip().rstrip(".")


def _domain_matches_configured(domain: str, configured: str) -> bool:
    return domain == configured or domain.endswith(f".{configured}")


def _host_matches_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")
