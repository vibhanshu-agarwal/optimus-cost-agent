from __future__ import annotations

import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from optimus_gateway.models import GatewayToolContext
from optimus_gateway.tool_models import (
    WebExtractGatewayRequest,
    WebExtractProviderResult,
    WebSearchGatewayRequest,
    WebSearchProviderResult,
)
from optimus_gateway.tool_providers import TavilyWebToolProvider, ToolProviderError


class _Response:
    def __init__(self, body: object) -> None:
        self._body = json.dumps(body).encode()

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _request(*, query: str = "python", depth: str = "basic", cap: int = 5) -> WebSearchGatewayRequest:
    return WebSearchGatewayRequest(
        context=GatewayToolContext(run_id="run-1", authenticated_subject="gateway-client"),
        query=query,
        allowed_domains=("python.org",),
        result_cap=cap,
        search_depth=depth,
    )


def _extract_request(*, max_chars: int = 10) -> WebExtractGatewayRequest:
    return WebExtractGatewayRequest(
        context=GatewayToolContext(run_id="run-1", authenticated_subject="gateway-client"),
        urls=("https://python.org/",),
        max_chars_per_source=max_chars,
    )


def test_search_normalizes_https_results_and_usage() -> None:
    captured: list[dict[str, object]] = []

    def fake_urlopen(request, *, timeout):
        captured.append(json.loads(request.data))
        return _Response(
            {
                "results": [
                    {"url": "https://python.org/docs", "title": "Docs", "content": "A snippet"},
                    {"url": "http://insecure.example", "title": "Drop", "content": "No"},
                ]
            }
        )

    provider = TavilyWebToolProvider(
        api_key="tavily-secret",
        base_url="https://api.tavily.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )

    result = provider.search(_request())

    assert isinstance(result, WebSearchProviderResult)
    assert [(item.url, item.title, item.snippet) for item in result.results] == [
        ("https://python.org/docs", "Docs", "A snippet")
    ]
    assert result.usage.provider == "tavily"
    assert result.usage.billing_units == 0
    assert result.usage.cost_usd == "0"
    assert captured[0]["query"] == "python"
    assert captured[0]["max_results"] == 5


def test_search_passes_advanced_depth_and_request_cap() -> None:
    captured: list[dict[str, object]] = []

    def fake_urlopen(request, *, timeout):
        captured.append(json.loads(request.data))
        return _Response({"results": []})

    provider = TavilyWebToolProvider(
        api_key="secret",
        base_url="https://api.tavily.example/",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )

    provider.search(_request(depth="advanced", cap=5))

    assert captured[0]["search_depth"] == "advanced"
    assert captured[0]["max_results"] == 5


def test_extract_normalizes_https_items_and_truncates_content() -> None:
    def fake_urlopen(request, *, timeout):
        return _Response(
            {
                "results": [
                    {
                        "url": "https://python.org/",
                        "title": "Python",
                        "raw_content": "0123456789-extra",
                    },
                    {"url": "http://insecure.example", "raw_content": "drop"},
                ]
            }
        )

    provider = TavilyWebToolProvider(
        api_key="secret",
        base_url="https://api.tavily.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )

    result = provider.extract(_extract_request(max_chars=10))

    assert isinstance(result, WebExtractProviderResult)
    assert [(item.url, item.title, item.content) for item in result.items] == [
        ("https://python.org/", "Python", "0123456789")
    ]


@pytest.mark.parametrize("failure", ["timeout", "http"])
def test_upstream_failures_raise_sanitized_provider_error(failure: str) -> None:
    api_key = "super-secret-tavily-key"

    def fake_urlopen(request, *, timeout):
        if failure == "timeout":
            raise TimeoutError(f"{api_key} timed out")
        raise HTTPError(request.full_url, 503, f"failure {api_key}", {}, BytesIO(b"raw secret body"))

    provider = TavilyWebToolProvider(
        api_key=api_key,
        base_url="https://api.tavily.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )

    with pytest.raises(ToolProviderError) as exc_info:
        provider.search(_request())

    assert api_key not in str(exc_info.value)
    assert "raw secret body" not in str(exc_info.value)


def test_malformed_body_raises_sanitized_provider_error() -> None:
    api_key = "super-secret-tavily-key"

    def fake_urlopen(request, *, timeout):
        return _Response({"unexpected": api_key})

    provider = TavilyWebToolProvider(
        api_key=api_key,
        base_url="https://api.tavily.example",
        urlopen=fake_urlopen,
        sleep=lambda _: None,
    )

    with pytest.raises(ToolProviderError) as exc_info:
        provider.search(_request())

    assert api_key not in str(exc_info.value)
