"""Server-side tool provider protocols and Gateway-owned provider adapters."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Protocol
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from optimus_gateway.tool_models import (
    AdvisoryProviderResult,
    AdvisoryRecord,
    PackageLookupGatewayRequest,
    PackageProviderResult,
    PackageVersionRecord,
    ProviderUsage,
    SecurityAdvisoryGatewayRequest,
    WebExtractGatewayRequest,
    WebExtractItem,
    WebExtractProviderResult,
    WebSearchGatewayRequest,
    WebSearchProviderResult,
    WebSearchResult,
)
from optimus_gateway.tool_provider_http import ToolProviderError, request_bytes, request_json


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

        return request_json(
            request,
            label=f"Tavily {operation}",
            urlopen_fn=self._urlopen,
            timeout_seconds=self._timeout_seconds,
            sleep=self._sleep,
            on_retry=self._on_retry,
        )


def _usage() -> ProviderUsage:
    return ProviderUsage(provider="tavily", billing_units=0, cost_usd="0")


def _is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.hostname)


class PackageRegistryToolProvider:
    """Gateway-owned package registry adapter shell for PyPI, npm, and Maven."""

    def __init__(
        self,
        *,
        pypi_base_url: str,
        npm_base_url: str,
        maven_base_url: str,
        urlopen: Callable[..., object] = urlopen,
        timeout_seconds: float = 60.0,
        sleep: Callable[[float], None] | None = None,
        on_retry: Callable[[int], None] | None = None,
    ) -> None:
        self.pypi_base_url = pypi_base_url.rstrip("/")
        self.npm_base_url = npm_base_url.rstrip("/")
        self.maven_base_url = maven_base_url.rstrip("/")
        self._urlopen = urlopen
        self._timeout_seconds = timeout_seconds
        self._sleep = sleep
        self._on_retry = on_retry

    def lookup(self, request: PackageLookupGatewayRequest) -> PackageProviderResult:
        if request.ecosystem == "pypi":
            return self._lookup_pypi(request)
        if request.ecosystem == "npm":
            return self._lookup_npm(request)
        if request.ecosystem == "maven":
            return self._lookup_maven(request)
        raise ToolProviderError("package registry lookup failed")

    def _lookup_pypi(self, request: PackageLookupGatewayRequest) -> PackageProviderResult:
        url = f"{self.pypi_base_url}/pypi/{quote(request.package, safe='')}/json"
        body = self._get_json(url, label="PyPI lookup")
        info = body.get("info")
        releases = body.get("releases")
        if not isinstance(info, dict) or not isinstance(releases, dict):
            raise ToolProviderError("PyPI lookup returned invalid metadata")
        latest = info.get("version")
        if not isinstance(latest, str):
            latest = None
        versions = tuple(
            PackageVersionRecord(
                version=version,
                source_url=f"https://pypi.org/project/{quote(request.package, safe='')}/{quote(version, safe='')}/",
                released_at=_release_time(files),
            )
            for version, files in releases.items()
            if isinstance(version, str) and isinstance(files, list)
        )
        return PackageProviderResult(
            package=request.package,
            ecosystem=request.ecosystem,
            requested_version=request.version,
            latest_version=latest,
            versions=versions,
            citations=(f"https://pypi.org/project/{quote(request.package, safe='')}/",),
            usage=_usage_for("pypi"),
        )

    def _lookup_npm(self, request: PackageLookupGatewayRequest) -> PackageProviderResult:
        url = f"{self.npm_base_url}/{quote(request.package, safe='')}"
        body = self._get_json(url, label="npm lookup")
        tags = body.get("dist-tags")
        raw_versions = body.get("versions")
        times = body.get("time")
        if not isinstance(tags, dict) or not isinstance(raw_versions, dict):
            raise ToolProviderError("npm lookup returned invalid metadata")
        latest = tags.get("latest")
        if not isinstance(latest, str):
            latest = None
        versions = tuple(
            PackageVersionRecord(
                version=version,
                source_url=f"https://www.npmjs.com/package/{quote(request.package, safe='')}/v/{quote(version, safe='')}",
                released_at=times.get(version) if isinstance(times, dict) and isinstance(times.get(version), str) else None,
            )
            for version in raw_versions
            if isinstance(version, str)
        )
        return PackageProviderResult(
            package=request.package,
            ecosystem=request.ecosystem,
            requested_version=request.version,
            latest_version=latest,
            versions=versions,
            citations=(f"https://www.npmjs.com/package/{quote(request.package, safe='')}",),
            usage=_usage_for("npm"),
        )

    def _lookup_maven(self, request: PackageLookupGatewayRequest) -> PackageProviderResult:
        if request.package.count(":") != 1:
            raise ToolProviderError("Maven package must use group:artifact format")
        group, artifact = request.package.split(":")
        if not group or not artifact:
            raise ToolProviderError("Maven package must use group:artifact format")
        url = f"{self.maven_base_url}/{quote(group.replace('.', '/'), safe='/')}/{quote(artifact, safe='')}/maven-metadata.xml"
        body = request_bytes(
            Request(url, headers={"accept": "application/xml"}, method="GET"),
            label="Maven lookup",
            urlopen_fn=self._urlopen,
            timeout_seconds=self._timeout_seconds,
            sleep=self._sleep,
            on_retry=self._on_retry,
        )
        try:
            root = ElementTree.fromstring(body)
            versioning = root.find("versioning")
            latest_node = versioning.find("latest") if versioning is not None else None
            versions_node = versioning.find("versions") if versioning is not None else None
            raw_versions = versions_node.findall("version") if versions_node is not None else []
            versions = tuple(
                PackageVersionRecord(
                    version=node.text,
                    source_url=(
                        "https://central.sonatype.com/artifact/"
                        f"{quote(group, safe='')}/{quote(artifact, safe='')}/{quote(node.text, safe='')}"
                    ),
                )
                for node in raw_versions
                if node.text
            )
            latest = latest_node.text if latest_node is not None else (versions[-1].version if versions else None)
        except (ElementTree.ParseError, DefusedXmlException, AttributeError):
            raise ToolProviderError("Maven lookup returned invalid metadata") from None
        return PackageProviderResult(
            package=request.package,
            ecosystem=request.ecosystem,
            requested_version=request.version,
            latest_version=latest,
            versions=versions,
            citations=(
                f"https://central.sonatype.com/artifact/{quote(group, safe='')}/{quote(artifact, safe='')}",
            ),
            usage=_usage_for("maven"),
        )

    def _get_json(self, url: str, *, label: str) -> dict[str, object]:
        return request_json(
            Request(url, headers={"accept": "application/json"}, method="GET"),
            label=label,
            urlopen_fn=self._urlopen,
            timeout_seconds=self._timeout_seconds,
            sleep=self._sleep,
            on_retry=self._on_retry,
        )

class OsvAdvisoryToolProvider:
    """Gateway-owned OSV advisory adapter shell."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        urlopen: Callable[..., object] = urlopen,
        timeout_seconds: float = 60.0,
        sleep: Callable[[float], None] | None = None,
        on_retry: Callable[[int], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._urlopen = urlopen
        self._timeout_seconds = timeout_seconds
        self._sleep = sleep
        self._on_retry = on_retry

    def lookup(self, request: SecurityAdvisoryGatewayRequest) -> AdvisoryProviderResult:
        headers = {"accept": "application/json", "content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        if _looks_like_osv_id(request.identifier):
            body = request_json(
                Request(f"{self.base_url}/vulns/{quote(request.identifier, safe='')}", headers=headers, method="GET"),
                label="OSV lookup",
                urlopen_fn=self._urlopen,
                timeout_seconds=self._timeout_seconds,
                sleep=self._sleep,
                on_retry=self._on_retry,
            )
            raw_vulns = [body]
        else:
            payload = {
                "package": {"name": request.identifier, "ecosystem": request.ecosystem},
                "version": request.version,
            }
            body = request_json(
                Request(
                    f"{self.base_url}/v1/query",
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                ),
                label="OSV lookup",
                urlopen_fn=self._urlopen,
                timeout_seconds=self._timeout_seconds,
                sleep=self._sleep,
                on_retry=self._on_retry,
            )
            raw_vulns = body.get("vulns", [])
        if not isinstance(raw_vulns, list):
            raise ToolProviderError("OSV lookup returned invalid advisories")
        if any(not isinstance(item, dict) for item in raw_vulns):
            raise ToolProviderError("OSV lookup returned invalid advisories")
        advisories = tuple(_advisory_record(item) for item in raw_vulns)
        return AdvisoryProviderResult(
            identifier=request.identifier,
            ecosystem=request.ecosystem,
            version=request.version,
            advisories=advisories,
            usage=_usage_for("osv"),
        )


def _release_time(files: object) -> str | None:
    if not isinstance(files, list):
        return None
    for item in files:
        if isinstance(item, dict):
            value = item.get("upload_time_iso_8601", item.get("upload_time"))
            if isinstance(value, str):
                return value
    return None


def _advisory_record(raw: dict[str, object]) -> AdvisoryRecord:
    affected = raw.get("affected", [])
    if not isinstance(affected, list):
        raise ToolProviderError("OSV lookup returned invalid advisories")
    references = raw.get("references", [])
    if not isinstance(references, list):
        raise ToolProviderError("OSV lookup returned invalid advisories")

    affected_ranges: list[str] = []
    fixed_versions: list[str] = []
    for item in affected:
        if not isinstance(item, dict):
            raise ToolProviderError("OSV lookup returned invalid advisories")
        ranges = item.get("ranges", [])
        if not isinstance(ranges, list):
            raise ToolProviderError("OSV lookup returned invalid advisories")
        for range_item in ranges:
            if not isinstance(range_item, dict):
                raise ToolProviderError("OSV lookup returned invalid advisories")
            events = range_item.get("events", [])
            if not isinstance(events, list):
                raise ToolProviderError("OSV lookup returned invalid advisories")
            for event in events:
                if not isinstance(event, dict):
                    raise ToolProviderError("OSV lookup returned invalid advisories")
                if isinstance(event.get("introduced"), str):
                    affected_ranges.append(event["introduced"])
                if isinstance(event.get("fixed"), str):
                    fixed_versions.append(event["fixed"])
    if any(not isinstance(reference, dict) for reference in references):
        raise ToolProviderError("OSV lookup returned invalid advisories")
    citations = tuple(
        reference["url"]
        for reference in references
        if isinstance(reference.get("url"), str) and _is_https_url(reference["url"])
    )
    severity = raw.get("severity")
    if isinstance(severity, list) and severity and isinstance(severity[0], dict):
        severity = severity[0].get("score")
    return AdvisoryRecord(
        advisory_id=raw.get("id") if isinstance(raw.get("id"), str) else "unknown",
        summary=raw.get("summary") if isinstance(raw.get("summary"), str) else "",
        severity=severity if isinstance(severity, str) else None,
        affected_ranges=tuple(affected_ranges),
        fixed_versions=tuple(fixed_versions),
        citations=citations,
    )


def _usage_for(provider: str) -> ProviderUsage:
    return ProviderUsage(provider=provider, billing_units=0, cost_usd="0")


def _looks_like_osv_id(identifier: str) -> bool:
    upper = identifier.upper()
    return upper.startswith(("CVE-", "GHSA-", "OSV-"))
