"""Run the bounded OpenRouter deterministic-web-plugin architecture spike.

This is an experimental measurement harness, not production Gateway code. It emits
sanitized JSON only: credentials and assistant/source content are never printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MODEL = "google/gemini-2.5-flash-lite"
MAX_TOKENS = 16
MAX_RESULTS = 3
TIMEOUT_SECONDS = 60
MAX_EXTRACT_BYTES = 2_000_000


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._title_depth = 0
        self.text_parts: list[str] = []
        self.title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        if lowered == "title":
            self._title_depth += 1

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1
        if lowered == "title" and self._title_depth:
            self._title_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        normalized = " ".join(data.split())
        if not normalized:
            return
        self.text_parts.append(normalized)
        if self._title_depth:
            self.title_parts.append(normalized)


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, raw_value = line.split("=", 1)
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[name.strip()] = value
    return values


def _post_chat(*, api_key: str, query: str, plugin: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": query}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0,
        "plugins": [plugin],
    }
    request = Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "optimus-cost-agent-architecture-spike/1",
            "X-Title": "Optimus Cost Agent Architecture Spike",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read()
            status = response.status
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter HTTP {exc.code}: {error_body[:500]}") from exc
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    body = json.loads(raw)
    message = body.get("choices", [{}])[0].get("message", {})
    annotations = message.get("annotations") or []
    sanitized_annotations: list[dict[str, Any]] = []
    for annotation in annotations:
        citation = annotation.get("url_citation", {}) if isinstance(annotation, dict) else {}
        content = citation.get("content", "")
        sanitized_annotations.append(
            {
                "type": annotation.get("type") if isinstance(annotation, dict) else None,
                "url": citation.get("url"),
                "title": citation.get("title"),
                "content_chars": len(content) if isinstance(content, str) else 0,
                "content_sha256": (
                    hashlib.sha256(content.encode("utf-8")).hexdigest()
                    if isinstance(content, str) and content
                    else None
                ),
                "start_index": citation.get("start_index"),
                "end_index": citation.get("end_index"),
            }
        )
    assistant_content = message.get("content", "")
    return {
        "http_status": status,
        "latency_ms": elapsed_ms,
        "response_id": body.get("id"),
        "model_requested": MODEL,
        "model_returned": body.get("model"),
        "provider": body.get("provider"),
        "max_tokens": MAX_TOKENS,
        "assistant_content_chars": len(assistant_content) if isinstance(assistant_content, str) else 0,
        "finish_reason": body.get("choices", [{}])[0].get("finish_reason"),
        "annotation_count": len(sanitized_annotations),
        "annotations": sanitized_annotations,
        "usage": body.get("usage"),
    }


def _hostname(url: str | None) -> str:
    if not isinstance(url, str):
        return ""
    parsed = urlparse(url)
    return (parsed.hostname or "").lower().rstrip(".")


def _matches_domain(url: str | None, domain: str) -> bool:
    host = _hostname(url)
    return host == domain or host.endswith(f".{domain}")


def _extract(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not _matches_domain(url, "docs.python.org"):
        raise RuntimeError(f"refusing extract URL outside HTTPS docs.python.org spike allowlist: {url}")
    request = Request(
        url,
        headers={"User-Agent": "optimus-cost-agent-architecture-spike/1"},
        method="GET",
    )
    started = time.perf_counter()
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        raw = response.read(MAX_EXTRACT_BYTES + 1)
        status = response.status
        final_url = response.geturl()
        content_type = response.headers.get_content_type()
        charset = response.headers.get_content_charset() or "utf-8"
    fetch_ms = round((time.perf_counter() - started) * 1000, 1)
    if len(raw) > MAX_EXTRACT_BYTES:
        raise RuntimeError(f"extract exceeded {MAX_EXTRACT_BYTES} bytes")
    if urlparse(final_url).scheme != "https" or not _matches_domain(final_url, "docs.python.org"):
        raise RuntimeError(f"extract redirected outside HTTPS docs.python.org spike allowlist: {final_url}")
    if content_type != "text/html":
        raise RuntimeError(f"extract returned unsupported content type: {content_type}")

    parse_started = time.perf_counter()
    parser = _HtmlTextExtractor()
    parser.feed(raw.decode(charset, errors="replace"))
    text = " ".join(parser.text_parts)
    title = " ".join(parser.title_parts)
    parse_ms = round((time.perf_counter() - parse_started) * 1000, 1)
    return {
        "requested_url": url,
        "final_url": final_url,
        "http_status": status,
        "content_type": content_type,
        "bytes": len(raw),
        "fetch_ms": fetch_ms,
        "parse_ms": parse_ms,
        "title": title,
        "text_chars": len(text),
        "word_count": len(text.split()),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()

    env = _parse_env_file(args.env_file)
    provider = env.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "openrouter").strip().lower()
    if provider != "openrouter":
        raise RuntimeError(f"spike requires OpenRouter, configured provider is {provider!r}")
    api_key = env.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OpenRouter credential is absent")

    annotation_probe = _post_chat(
        api_key=api_key,
        query="What is the current stable Python release? Return a very short answer with sources.",
        plugin={"id": "web", "max_results": MAX_RESULTS},
    )
    filter_query = (
        "What does pathlib.Path.read_text do? Use the official Python documentation as the source."
    )
    include_probe = _post_chat(
        api_key=api_key,
        query=filter_query,
        plugin={"id": "web", "max_results": MAX_RESULTS, "include_domains": ["docs.python.org"]},
    )
    exclude_probe = _post_chat(
        api_key=api_key,
        query=filter_query,
        plugin={"id": "web", "max_results": MAX_RESULTS, "exclude_domains": ["docs.python.org"]},
    )

    include_urls = [
        annotation.get("url")
        for annotation in include_probe["annotations"]
        if isinstance(annotation.get("url"), str)
    ]
    if not include_urls:
        raise RuntimeError("include-domain probe returned no extractable citation")
    try:
        extract_probe: dict[str, Any] = {"success": True, **_extract(include_urls[0])}
    except Exception as exc:
        extract_probe = {
            "success": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    report = {
        "spike": "OpenRouter deterministic web plugin",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "configuration": {
            "endpoint": "https://openrouter.ai/api/v1/chat/completions",
            "model": MODEL,
            "engine": "default (omitted)",
            "max_tokens": MAX_TOKENS,
            "max_results": MAX_RESULTS,
            "request_count": 3,
        },
        "annotation_probe": annotation_probe,
        "include_domain_probe": include_probe,
        "exclude_domain_probe": exclude_probe,
        "extract_probe": extract_probe,
        "domain_measurements": {
            "include_annotation_count": include_probe["annotation_count"],
            "include_violations": sum(
                1
                for annotation in include_probe["annotations"]
                if not _matches_domain(annotation.get("url"), "docs.python.org")
            ),
            "exclude_annotation_count": exclude_probe["annotation_count"],
            "exclude_violations": sum(
                1
                for annotation in exclude_probe["annotations"]
                if _matches_domain(annotation.get("url"), "docs.python.org")
            ),
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
