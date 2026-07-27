"""Server-side tool provider protocols for the Gateway tool routes.

Plan 11.2 (``P11-FEAT-GATEWAY-TOOLS``), Task 4. These protocols are the
adapter boundary between the typed Gateway tool handlers and the real
upstream providers (Tavily, a package registry, an advisory database, and so
on). Concrete network-calling adapters are out of scope for this task; only
the injectable boundary is defined here, plus the sanitized failure type
handlers use to map any provider fault to a 502 without leaking provider
credentials, raw response bodies, or unbounded URLs.
"""
from __future__ import annotations

from typing import Protocol

from optimus_gateway.tool_models import (
    AdvisoryProviderResult,
    PackageLookupGatewayRequest,
    PackageProviderResult,
    SecurityAdvisoryGatewayRequest,
    WebExtractGatewayRequest,
    WebExtractProviderResult,
    WebSearchGatewayRequest,
    WebSearchProviderResult,
)


class ToolProviderError(RuntimeError):
    """Sanitized failure a provider adapter raises for any upstream/provider fault.

    Provider implementations should translate raw upstream exceptions into
    this type (or let ``tool_handlers`` catch a broader exception as a
    fallback) so credentials, raw response bodies, and internal upstream
    detail never reach the Gateway's HTTP error response.
    """


class WebToolProvider(Protocol):
    def search(self, request: WebSearchGatewayRequest) -> WebSearchProviderResult: ...

    def extract(self, request: WebExtractGatewayRequest) -> WebExtractProviderResult: ...


class PackageToolProvider(Protocol):
    def lookup(self, request: PackageLookupGatewayRequest) -> PackageProviderResult: ...


class AdvisoryToolProvider(Protocol):
    def lookup(self, request: SecurityAdvisoryGatewayRequest) -> AdvisoryProviderResult: ...


class TavilyWebToolProvider:
    """Gateway-owned Tavily adapter shell.

    HTTP behavior is intentionally deferred to Plan 11.3 Task 2; construction
    is available in Task 1 so complete Gateway configuration can be wired.
    """

    def __init__(self, *, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url

    def search(self, request: WebSearchGatewayRequest) -> WebSearchProviderResult:
        del request
        raise ToolProviderError("not implemented")

    def extract(self, request: WebExtractGatewayRequest) -> WebExtractProviderResult:
        del request
        raise ToolProviderError("not implemented")


class PackageRegistryToolProvider:
    """Gateway-owned package registry adapter shell for PyPI, npm, and Maven."""

    def __init__(self, *, pypi_base_url: str, npm_base_url: str, maven_base_url: str) -> None:
        self.pypi_base_url = pypi_base_url
        self.npm_base_url = npm_base_url
        self.maven_base_url = maven_base_url

    def lookup(self, request: PackageLookupGatewayRequest) -> PackageProviderResult:
        del request
        raise ToolProviderError("not implemented")


class OsvAdvisoryToolProvider:
    """Gateway-owned OSV advisory adapter shell."""

    def __init__(self, *, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url
        self.api_key = api_key

    def lookup(self, request: SecurityAdvisoryGatewayRequest) -> AdvisoryProviderResult:
        del request
        raise ToolProviderError("not implemented")
