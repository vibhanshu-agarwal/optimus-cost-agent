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
