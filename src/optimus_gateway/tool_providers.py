"""Server-side tool provider protocols and Gateway-owned provider adapters."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from optimus_gateway.tool_models import (
    AdvisoryProviderResult,
    PackageLookupGatewayRequest,
    PackageProviderResult,
    ProviderUsage,
    SecurityAdvisoryGatewayRequest,
    WebExtractGatewayRequest,
    WebExtractItem,
    WebExtractProviderResult,
    WebSearchGatewayRequest,
    WebSearchProviderResult,
    WebSearchResult,
)
from optimus_gateway.upstream_client import (
    RetryableUpstreamError,
    call_with_upstream_retry,
    is_retryable_upstream_fault,
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
    """Gateway-owned Tavily search and extract adapter."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        urlopen: Callable[..., object] = urlopen,
        timeout_seconds: float = 60.0,
        sleep: Callable[[float], None] | None = None,
        on_retry: Callable[[int], None] | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._urlopen = urlopen
        self._timeout_seconds = timeout_seconds
        self._sleep = sleep
        self._on_retry = on_retry

    def search(self, request: WebSearchGatewayRequest) -> WebSearchProviderResult:
        payload = {
            "api_key": self.api_key,
            "query": request.query,
            "search_depth": request.search_depth,
            "max_results": request.result_cap,
            "include_domains": list(request.allowed_domains),
        }
        body = self._post_json("/search", payload, operation="search")
        raw_results = body.get("results")
        if not isinstance(raw_results, list):
            raise ToolProviderError("Tavily search returned an invalid results field")

        results: list[WebSearchResult] = []
        for raw_result in raw_results:
            if not isinstance(raw_result, dict):
                raise ToolProviderError("Tavily search returned an invalid result")
            url = raw_result.get("url")
            if not isinstance(url, str):
                raise ToolProviderError("Tavily search returned a result without a URL")
            if not _is_https_url(url):
                continue
            title = raw_result.get("title", "")
            snippet = raw_result.get("content", raw_result.get("snippet", ""))
            if not isinstance(title, str) or not isinstance(snippet, str):
                raise ToolProviderError("Tavily search returned an invalid result field")
            results.append(WebSearchResult(url=url, title=title, snippet=snippet))
            if len(results) >= request.result_cap:
                break
        return WebSearchProviderResult(results=tuple(results), usage=_usage())

    def extract(self, request: WebExtractGatewayRequest) -> WebExtractProviderResult:
        body = self._post_json(
            "/extract",
            {"api_key": self.api_key, "urls": list(request.urls)},
            operation="extract",
        )
        raw_results = body.get("results")
        if not isinstance(raw_results, list):
            raise ToolProviderError("Tavily extract returned an invalid results field")

        items: list[WebExtractItem] = []
        for raw_result in raw_results:
            if not isinstance(raw_result, dict):
                raise ToolProviderError("Tavily extract returned an invalid result")
            url = raw_result.get("url")
            if not isinstance(url, str):
                raise ToolProviderError("Tavily extract returned a result without a URL")
            if not _is_https_url(url):
                continue
            title = raw_result.get("title", "")
            content = raw_result.get("raw_content", raw_result.get("content", ""))
            if not isinstance(title, str) or not isinstance(content, str):
                raise ToolProviderError("Tavily extract returned an invalid result field")
            items.append(
                WebExtractItem(url=url, title=title, content=content[: request.max_chars_per_source])
            )
        return WebExtractProviderResult(items=tuple(items), usage=_usage())

    def _post_json(self, path: str, payload: dict[str, object], *, operation: str) -> dict[str, object]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )

        def call() -> dict[str, object]:
            try:
                with self._urlopen(request, timeout=self._timeout_seconds) as response:
                    body = json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                if is_retryable_upstream_fault(exc):
                    raise RetryableUpstreamError("Tavily transient HTTP failure") from exc
                raise RuntimeError("Tavily HTTP failure") from exc
            except (URLError, TimeoutError) as exc:
                if is_retryable_upstream_fault(exc):
                    raise RetryableUpstreamError("Tavily network failure") from None
                raise RuntimeError("Tavily network failure") from None
            except (OSError, UnicodeError, json.JSONDecodeError):
                raise RuntimeError("Tavily response failure") from None
            if not isinstance(body, dict):
                raise RuntimeError("Tavily response was not an object")
            return body

        try:
            return call_with_upstream_retry(
                call,
                sleep=self._sleep,
                on_retry=self._on_retry,
            )
        except Exception as exc:  # noqa: BLE001 - provider detail must not cross the adapter boundary
            del exc
            raise ToolProviderError(f"Tavily {operation} failed") from None


def _usage() -> ProviderUsage:
    return ProviderUsage(provider="tavily", billing_units=0, cost_usd="0")


def _is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.hostname)


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
