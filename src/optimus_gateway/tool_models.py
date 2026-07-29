"""Gateway-local request/result/provider-usage contracts for typed tool routes.

Plan 11.2 (``P11-FEAT-GATEWAY-TOOLS``), Task 4. These are Gateway-local
equivalents of the shared wire contracts in ``optimus.gateway.tool_models``;
the field names, enum string values, and JSON envelope shape are kept
identical so requests/responses stay wire-compatible with the agent-side
client. ``optimus_gateway`` must remain independently deployable with zero
``optimus.*`` imports, so this module is a self-contained duplicate rather
than a shared import.

Every field validator here only performs structural/typed validation (shape,
bounds, HTTPS). Authoritative domain, tool-class, and policy-signal decisions
are made by :mod:`optimus_gateway.tool_policy`, not here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

from optimus_gateway.models import GatewayToolContext, ToolPolicySignal

_PACKAGE_ECOSYSTEMS = frozenset({"pypi", "npm", "maven"})
_SEARCH_DEPTHS = frozenset({"basic", "advanced"})
_ADVANCED_SEARCH_RESULT_CAP = 5
_MAX_EXTRACT_URLS = 10

# The wire "reason" field on /v1/tools/web/search carries the agent-side
# EvidenceReasonCode value (see optimus.tools.policy.WEB_SEARCH_TRIGGERS).
# policy_signal itself is never sent on the wire for web search, so the
# Gateway independently re-derives it from reason using the same fixed
# (signal, reason) pairing the local policy already enforced; a reason that
# does not appear here is a policy-signal mismatch, not a malformed shape.
_WEB_SEARCH_REASON_TO_SIGNAL: dict[str, ToolPolicySignal] = {
    "USER_REQUESTED": ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
    "CURRENT_FACT": ToolPolicySignal.CURRENT_OR_LATEST_FACT,
    "API_DOCS_OUTDATED": ToolPolicySignal.API_OR_FRAMEWORK_FACT_NOT_IN_REPO,
}


class GatewayToolValidationError(ValueError):
    """Raised when a tool request body fails structural/typed validation.

    Always maps to HTTP 400 at the handler boundary.
    """

    def __init__(self, rule_id: str, message: str) -> None:
        super().__init__(message)
        self.rule_id = rule_id


def resolve_web_search_policy_signal(reason: str) -> ToolPolicySignal | None:
    """Map a wire ``reason`` value to the web-search policy signal it authorizes.

    Returns ``None`` when ``reason`` does not authorize web search at all
    (including package/advisory or unrecognized reasons); callers must treat
    that as a policy-signal mismatch (403), not a malformed request (400).
    """
    return _WEB_SEARCH_REASON_TO_SIGNAL.get(reason)


# --- Provider usage (shared by all four provider result types) -------------


@dataclass(frozen=True)
class ProviderUsage:
    """Real provider-reported usage/cost; the Gateway assigns gateway_request_id.

    Provider adapters own this because only they observe the real upstream
    billing response; the Gateway never estimates tokens, billing units, or cost.
    """

    provider: str
    billing_units: int
    cost_usd: str
    cache_hit: bool = False
    provider_request_id: str | None = None


# --- Request contracts -------------------------------------------------


@dataclass(frozen=True)
class WebSearchGatewayRequest:
    context: GatewayToolContext
    query: str
    allowed_domains: tuple[str, ...]
    result_cap: int
    search_depth: str


@dataclass(frozen=True)
class WebExtractGatewayRequest:
    context: GatewayToolContext
    urls: tuple[str, ...]
    max_chars_per_source: int


@dataclass(frozen=True)
class PackageLookupGatewayRequest:
    context: GatewayToolContext
    package: str
    ecosystem: str
    version: str | None = None


@dataclass(frozen=True)
class SecurityAdvisoryGatewayRequest:
    context: GatewayToolContext
    identifier: str
    ecosystem: str | None = None
    version: str | None = None


# --- Result contracts -----------------------------------------------------


@dataclass(frozen=True)
class WebSearchResult:
    url: str
    title: str = ""
    snippet: str = ""


@dataclass(frozen=True)
class WebSearchProviderResult:
    results: tuple[WebSearchResult, ...]
    usage: ProviderUsage


@dataclass(frozen=True)
class WebExtractItem:
    url: str
    title: str = ""
    content: str = ""


@dataclass(frozen=True)
class WebExtractProviderResult:
    items: tuple[WebExtractItem, ...]
    usage: ProviderUsage


@dataclass(frozen=True)
class PackageVersionRecord:
    version: str
    source_url: str
    released_at: str | None = None


@dataclass(frozen=True)
class PackageProviderResult:
    package: str
    ecosystem: str
    usage: ProviderUsage
    requested_version: str | None = None
    latest_version: str | None = None
    versions: tuple[PackageVersionRecord, ...] = ()
    citations: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdvisoryRecord:
    advisory_id: str
    summary: str
    severity: str | None = None
    affected_ranges: tuple[str, ...] = ()
    fixed_versions: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdvisoryProviderResult:
    identifier: str
    usage: ProviderUsage
    ecosystem: str | None = None
    version: str | None = None
    advisories: tuple[AdvisoryRecord, ...] = ()


# --- Field-level (pre-context) request validation ---------------------------


@dataclass(frozen=True)
class WebSearchFields:
    query: str
    allowed_domains: tuple[str, ...]
    result_cap: int
    search_depth: str
    reason: str


@dataclass(frozen=True)
class WebExtractFields:
    urls: tuple[str, ...]
    max_chars_per_source: int


@dataclass(frozen=True)
class PackageLookupFields:
    package: str
    ecosystem: str
    version: str | None


@dataclass(frozen=True)
class SecurityAdvisoryFields:
    identifier: str
    ecosystem: str | None
    version: str | None


def validate_web_search_body(body: Mapping[str, Any]) -> WebSearchFields:
    if not isinstance(body, Mapping):
        raise GatewayToolValidationError("MALFORMED_BODY", "request body must be a JSON object")

    query = body.get("query")
    if not isinstance(query, str) or not query.strip():
        raise GatewayToolValidationError("INVALID_QUERY", "query is required and must be a non-empty string")

    allowed_domains = _validate_non_empty_string_list(body.get("allowed_domains"), field_name="allowed_domains")

    result_cap = body.get("result_cap", 5)
    if not _is_plain_int(result_cap) or not (1 <= result_cap <= 10):
        raise GatewayToolValidationError("INVALID_RESULT_CAP", "result_cap must be an integer from 1 through 10")

    search_depth = body.get("search_depth", "basic")
    if search_depth not in _SEARCH_DEPTHS:
        raise GatewayToolValidationError("INVALID_SEARCH_DEPTH", "search_depth must be 'basic' or 'advanced'")
    if search_depth == "advanced" and result_cap > _ADVANCED_SEARCH_RESULT_CAP:
        result_cap = _ADVANCED_SEARCH_RESULT_CAP

    reason = body.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise GatewayToolValidationError("MISSING_REASON", "reason is required")

    return WebSearchFields(
        query=query.strip(),
        allowed_domains=allowed_domains,
        result_cap=result_cap,
        search_depth=search_depth,
        reason=reason.strip(),
    )


def validate_web_extract_body(body: Mapping[str, Any]) -> WebExtractFields:
    if not isinstance(body, Mapping):
        raise GatewayToolValidationError("MALFORMED_BODY", "request body must be a JSON object")

    has_url = body.get("url") is not None
    has_urls = body.get("urls") is not None
    if has_url and has_urls:
        raise GatewayToolValidationError("MIXED_URL_FORMS", "cannot supply both url and urls")
    if has_url:
        urls_raw: Any = [body["url"]]
    elif has_urls:
        urls_raw = body["urls"]
    else:
        raise GatewayToolValidationError("MISSING_URLS", "either url or urls is required")

    if not isinstance(urls_raw, list) or not urls_raw:
        raise GatewayToolValidationError("INVALID_URLS", "urls must be a non-empty list")
    if len(urls_raw) > _MAX_EXTRACT_URLS:
        raise GatewayToolValidationError("INVALID_URLS", f"urls must contain at most {_MAX_EXTRACT_URLS} entries")
    if not all(isinstance(url, str) and url for url in urls_raw):
        raise GatewayToolValidationError("INVALID_URLS", "urls must contain only non-empty strings")
    for url in urls_raw:
        if not _is_https_url(url):
            raise GatewayToolValidationError("NON_HTTPS_URL", f"URL is not HTTPS: {url}")
    if len(set(urls_raw)) != len(urls_raw):
        raise GatewayToolValidationError("DUPLICATE_URL", "urls must not contain duplicates")

    max_chars_per_source = body.get("max_chars_per_source", 4000)
    if not _is_plain_int(max_chars_per_source) or not (1 <= max_chars_per_source <= 20000):
        raise GatewayToolValidationError(
            "INVALID_MAX_CHARS", "max_chars_per_source must be an integer from 1 through 20000"
        )

    return WebExtractFields(urls=tuple(urls_raw), max_chars_per_source=max_chars_per_source)


def validate_package_lookup_body(body: Mapping[str, Any]) -> PackageLookupFields:
    if not isinstance(body, Mapping):
        raise GatewayToolValidationError("MALFORMED_BODY", "request body must be a JSON object")

    package = body.get("package")
    if not isinstance(package, str) or not package.strip():
        raise GatewayToolValidationError("INVALID_PACKAGE", "package is required and must be a non-empty string")

    ecosystem = body.get("ecosystem")
    if ecosystem not in _PACKAGE_ECOSYSTEMS:
        raise GatewayToolValidationError("INVALID_ECOSYSTEM", "ecosystem must be one of pypi, npm, maven")

    version = body.get("version")
    if version is not None and not isinstance(version, str):
        raise GatewayToolValidationError("INVALID_VERSION", "version must be a string when present")

    return PackageLookupFields(package=package.strip(), ecosystem=ecosystem, version=version)


def validate_security_advisory_body(body: Mapping[str, Any]) -> SecurityAdvisoryFields:
    if not isinstance(body, Mapping):
        raise GatewayToolValidationError("MALFORMED_BODY", "request body must be a JSON object")

    identifier = body.get("identifier")
    if not isinstance(identifier, str) or not identifier.strip():
        raise GatewayToolValidationError(
            "INVALID_IDENTIFIER", "identifier is required and must be a non-empty string"
        )

    ecosystem = body.get("ecosystem")
    if ecosystem is not None and ecosystem not in _PACKAGE_ECOSYSTEMS:
        raise GatewayToolValidationError("INVALID_ECOSYSTEM", "ecosystem must be one of pypi, npm, maven when present")

    version = body.get("version")
    if version is not None and not isinstance(version, str):
        raise GatewayToolValidationError("INVALID_VERSION", "version must be a string when present")

    return SecurityAdvisoryFields(identifier=identifier.strip(), ecosystem=ecosystem, version=version)


# --- Envelope "result" payload builders (usage is a separate envelope field) -


def web_search_result_payload(result: WebSearchProviderResult) -> dict[str, Any]:
    return {
        "results": [{"title": item.title, "url": item.url, "snippet": item.snippet} for item in result.results]
    }


def web_extract_result_payload(result: WebExtractProviderResult) -> dict[str, Any]:
    return {"items": [{"url": item.url, "title": item.title, "content": item.content} for item in result.items]}


def package_lookup_result_payload(result: PackageProviderResult) -> dict[str, Any]:
    return {
        "package": result.package,
        "ecosystem": result.ecosystem,
        "requested_version": result.requested_version,
        "latest_version": result.latest_version,
        "versions": [
            {"version": record.version, "released_at": record.released_at, "source_url": record.source_url}
            for record in result.versions
        ],
        "citations": list(result.citations),
    }


def security_advisory_result_payload(result: AdvisoryProviderResult) -> dict[str, Any]:
    return {
        "identifier": result.identifier,
        "ecosystem": result.ecosystem,
        "version": result.version,
        "advisories": [
            {
                "advisory_id": advisory.advisory_id,
                "summary": advisory.summary,
                "severity": advisory.severity,
                "affected_ranges": list(advisory.affected_ranges),
                "fixed_versions": list(advisory.fixed_versions),
                "citations": list(advisory.citations),
            }
            for advisory in result.advisories
        ],
    }


def _validate_non_empty_string_list(value: Any, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise GatewayToolValidationError(
            f"INVALID_{field_name.upper()}", f"{field_name} is required and must be a non-empty list"
        )
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise GatewayToolValidationError(
            f"INVALID_{field_name.upper()}", f"{field_name} must contain only non-empty strings"
        )
    return tuple(value)


def _is_plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.hostname)
