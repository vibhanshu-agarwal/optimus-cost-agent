from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class AnthropicMessageResult:
    message_id: str
    output_text: str
    input_tokens: int
    output_tokens: int


class AnthropicClient(Protocol):
    def create_message(self, *, model: str, input_text: str) -> AnthropicMessageResult:
        """Call Anthropic Messages API and return normalized text + usage."""


class UrllibAnthropicClient:
    def __init__(self, *, api_key: str, timeout_seconds: float = 60.0) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def create_message(self, *, model: str, input_text: str) -> AnthropicMessageResult:
        payload = {
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": input_text}],
        }
        request = Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"anthropic request failed ({exc.code}): {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"anthropic request failed: {exc.reason}") from exc

        return _parse_anthropic_message(body)


def _parse_anthropic_message(body: dict[str, Any]) -> AnthropicMessageResult:
    message_id = body.get("id")
    if not isinstance(message_id, str) or not message_id:
        raise RuntimeError("anthropic response missing id")

    usage = body.get("usage")
    if not isinstance(usage, dict):
        raise RuntimeError("anthropic response missing usage")
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        raise RuntimeError("anthropic response usage missing token counts")

    output_text = _extract_output_text(body.get("content"))
    return AnthropicMessageResult(
        message_id=message_id,
        output_text=output_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _extract_output_text(content: object) -> str:
    if not isinstance(content, list):
        raise RuntimeError("anthropic response missing content")
    chunks: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str):
                chunks.append(text)
    if not chunks:
        raise RuntimeError("anthropic response missing text content")
    return "".join(chunks)
