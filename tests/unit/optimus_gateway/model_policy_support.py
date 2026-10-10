"""Shared fixtures for the Plan 12.2 Task 5 Gateway model-policy tests (not a test module).

``VERIFIED_POLICY`` is a non-fixture registry whose routes, estimator and reserve are marked verified,
so the enforcer's admit path can be exercised offline. It is test data, never a shipped policy.
"""

from __future__ import annotations

import io
import json
import socket
import ssl
import textwrap
import urllib.request
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from optimus_gateway.model_policy import GatewayModelPolicy
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.upstream_client import ProviderMessageResult, UpstreamAttemptFailure
from optimus_model_policy import Message, RegistrySnapshot, load_registry
from optimus_model_policy.binding import RouteBinding, disclosure_key, issue_disclosure, payload_digest, route_digest

SHARED_SECRET = "policy-test-shared-secret"  # pragma: allowlist secret - synthetic test fixture
PROVIDER_KEY = "sk-or-policy-test"  # pragma: allowlist secret - synthetic test fixture
CAP = 16384
# effective_total = min(262144, 300000) = 262144; usable = 262144 - 16384 = 245760.
# tokens = ceil(0.5 * bytes) + 8 per message + 64 fixed; one message -> 72 framing tokens, so the
# largest admitted single-message input is 2 * (245760 - 72) = 491376 UTF-8 bytes.
LIMIT_BYTES = 491_376

VERIFIED_POLICY = textwrap.dedent(
    """\
    schema_version: 1
    policy_version: "task5-verified-test"
    fixture: false
    context_ceiling_tokens: 262144
    output_reserve_tokens: {implementer: 16384, summarizer: 8192}
    estimators:
      half:
        method: utf8-bytes-ratio
        tokens_per_byte: "0.5"
        per_message_tokens: 8
        fixed_tokens: 64
        verified: true
    role_price_blends: {}
    alerts: {thresholds_usd: []}
    models:
      cn/alpha:
        origin: china
        tier: cheap
        prices: {input_usd_per_million: "0.10", output_usd_per_million: "0.40"}
        data_use: {provider_may_train_on_inputs: "no", disclosure: none}
        capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [high]}
        default_reasoning: high
        route:
          estimator: half
          endpoints:
            - {provider: alpha-cloud/fp8, quantization: fp8, context_window_tokens: 300000, max_output_tokens: 32768, verified: true}
            - {provider: alpha-backup/bf16, quantization: bf16, context_window_tokens: 400000, max_output_tokens: 20000, verified: true}
      us/contrib:
        origin: non-china
        tier: cheap
        prices: {input_usd_per_million: "0.20", output_usd_per_million: "0.80"}
        data_use: {provider_may_train_on_inputs: "yes", disclosure: contributor}
        capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [high]}
        default_reasoning: high
        route:
          estimator: half
          endpoints:
            - {provider: contrib-ai/bf16, quantization: bf16, context_window_tokens: 300000, max_output_tokens: 32768, verified: true}
      cn/nullquant:
        origin: china
        tier: cheap
        prices: {input_usd_per_million: "0.30", output_usd_per_million: "1.20"}
        data_use: {provider_may_train_on_inputs: "no", disclosure: none}
        capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [high]}
        default_reasoning: high
        route:
          estimator: half
          endpoints:
            - {provider: null-quant, quantization: null, context_window_tokens: 300000, max_output_tokens: 32768, verified: true}
      us/idle:
        origin: non-china
        tier: cheap
        prices: {input_usd_per_million: "0.05", output_usd_per_million: "0.10"}
        data_use: {provider_may_train_on_inputs: "no", disclosure: none}
        capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [high]}
        default_reasoning: high
        route:
          estimator: half
          endpoints:
            - {provider: idle-ai/fp8, quantization: fp8, context_window_tokens: 300000, max_output_tokens: 32768, verified: true}
    roles:
      medium: [cn/alpha, us/contrib, cn/nullquant]
    """
)


def verified_snapshot(tmp_path: Path, text: str = VERIFIED_POLICY) -> RegistrySnapshot:
    path = tmp_path / "verified-registry.yaml"
    path.write_text(text, encoding="utf-8")
    return load_registry(path, None)


def model_policy(snapshot: RegistrySnapshot, *, approved_hash: str | None = None) -> GatewayModelPolicy:
    return GatewayModelPolicy.for_launch(
        snapshot=snapshot,
        approved_hash=snapshot.effective_hash if approved_hash is None else approved_hash,
        shared_secret=SHARED_SECRET,
    )


def gateway_config(policy: GatewayModelPolicy | None = None) -> GatewayServiceConfig:
    return GatewayServiceConfig(
        bind_host="127.0.0.1",
        bind_port=8765,
        shared_secret=SHARED_SECRET,
        provider="openrouter",
        provider_api_key=PROVIDER_KEY,
        base_url="https://openrouter.ai/api/v1",
        model_policy=policy,
    )


AUTH = f"Bearer {SHARED_SECRET}"


def binding(
    snapshot: RegistrySnapshot,
    *,
    model: str = "cn/alpha",
    input_text: str = "plan the change",
    output_cap: int = CAP,
    request_id: str = "req-1",
    disclose: bool = False,
    secret: str = SHARED_SECRET,
) -> dict[str, Any]:
    disclosure = None
    if disclose:
        disclosure = issue_disclosure(
            disclosure_key(secret),
            request_id=request_id,
            model_id=model,
            route=route_digest(model, snapshot.policy.models[model]),
            payload=payload_digest(
                model, (Message("user", input_text),), output_cap, reasoning=snapshot.policy.models[model].default_reasoning
            ),
        )
    return RouteBinding(
        registry_hash=snapshot.effective_hash, request_id=request_id, output_cap=output_cap, disclosure=disclosure
    ).to_wire()


class RecordingUpstream:
    """Records every upstream call with exactly the keywords the real client's methods accept.

    ``create_message`` is today's routing; ``create_message_once`` is one enforced attempt, whose
    results can be scripted: each ``attempts`` item is an ``UpstreamAttemptFailure`` to raise, or
    None for a completed reply. With no script every attempt completes.
    """

    def __init__(self, finish_reason: str | None = "stop", attempts: list[UpstreamAttemptFailure | None] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._finish_reason = finish_reason
        self._attempts = list(attempts or [])

    def create_message(self, *, model: str, input_text: str) -> ProviderMessageResult:
        self.calls.append({"legacy": True, "model": model, "input_text": input_text})
        return self._result(model)

    def create_message_once(
        self, *, model: str, input_text: str, max_tokens: int, provider_controls: Any, reasoning: str | None
    ) -> ProviderMessageResult:
        self.calls.append(
            {
                "model": model,
                "input_text": input_text,
                "max_tokens": max_tokens,
                "provider_controls": provider_controls,
                "reasoning": reasoning,
            }
        )
        planned = self._attempts.pop(0) if self._attempts else None
        if planned is not None:
            raise planned
        return self._result(model)

    def _result(self, model: str) -> ProviderMessageResult:
        return ProviderMessageResult(
            message_id=f"gen-{len(self.calls)}",
            output_text="WRITE a.py\nx\nTEST pytest -q",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            billing_units=15,
            cost_usd=Decimal("0.0002"),
            provider="openrouter",
            resolved_provider="Alpha",
            requested_model=model,
            resolved_model=model,
            model_version=None,
            cache_hit=False,
            finish_reason=self._finish_reason,
        )


# --- The network under the real upstream client ------------------------------------------------------
#
# Only the operating-system layer is replaced: `socket.create_connection` and `SSLContext.wrap_socket`.
# Everything above it runs for real: urllib's opener and its URLError wrapping, and http.client's
# connect, send and response parsing (Codex CP1 corrections review: test the wrapped error).


class Wire:
    """Each stage fails with the given exception or succeeds: connecting (every time, or only the first
    ``connect_failures`` times), the TLS handshake, sending
    (after ``send_ok_calls`` successful sends, such as a proxy's CONNECT), and the reply (raw HTTP
    bytes, or an exception raised while reading it). ``replies``
    gives one reply per response read, in order (a proxy's CONNECT reply, then the request's). Every
    established connection records the bytes sent on it. ``proxies`` replaces the process's proxy
    configuration (none by default), so a proxied runner sees the same network."""

    def __init__(
        self,
        *,
        connect: BaseException | None = None,
        connect_failures: int | None = None,
        handshake: BaseException | None = None,
        send: BaseException | None = None,
        send_ok_calls: int = 0,
        reply: bytes | BaseException = b"",
        replies: list[bytes | BaseException] | None = None,
        proxies: dict[str, str] | None = None,
    ) -> None:
        self.connect_error = connect
        self.connect_failures = connect_failures
        self.handshake_error = handshake
        self.send_error = send
        self.send_ok_calls = send_ok_calls
        self.send_calls = 0
        self.reply = reply
        self.replies = replies
        self.proxies = proxies or {}
        self.connects = 0
        self.sent: list[bytearray] = []

    def next_reply(self) -> bytes | BaseException:
        return self.replies.pop(0) if self.replies is not None else self.reply

    def install(self, monkeypatch: pytest.MonkeyPatch) -> Wire:
        wire = self
        # Proxies are read when an opener is built: the enforced client builds its own, and the legacy
        # path's urlopen rebuilds the shared one once it is reset here.
        monkeypatch.setattr(urllib.request, "getproxies", lambda: dict(wire.proxies))
        monkeypatch.setattr(urllib.request, "_opener", None)

        def create_connection(address: object, timeout: object = None, source_address: object = None, **_: object) -> _WireSocket:
            wire.connects += 1
            if wire.connect_error is not None and (wire.connect_failures is None or wire.connects <= wire.connect_failures):
                raise wire.connect_error
            buffer = bytearray()
            wire.sent.append(buffer)
            return _WireSocket(wire, buffer)

        def wrap_socket(context: object, sock: _WireSocket, *args: object, **kwargs: object) -> _WireSocket:
            if wire.handshake_error is not None:
                raise wire.handshake_error
            return sock

        monkeypatch.setattr(socket, "create_connection", create_connection)
        monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap_socket)
        return self

    def bytes_sent(self) -> int:
        return sum(len(buffer) for buffer in self.sent)

    def request_body(self, index: int = -1) -> dict[str, Any]:
        head, _, body = bytes(self.sent[index]).partition(b"\r\n\r\n")
        assert head.startswith(b"POST /api/v1/chat/completions HTTP/1.1\r\n")
        return json.loads(body)

    def requests_sent(self) -> list[bytes]:
        """The request lines sent, in order (a proxy's CONNECT, then the request's POST)."""
        return [line for buffer in self.sent for line in bytes(buffer).split(b"\r\n") if line.startswith((b"CONNECT ", b"POST "))]


class _WireSocket:
    def __init__(self, wire: Wire, buffer: bytearray) -> None:
        self._wire = wire
        self._buffer = buffer

    def setsockopt(self, *args: object) -> None:
        return None

    def sendall(self, data: bytes) -> None:
        self._wire.send_calls += 1
        if self._wire.send_error is not None and self._wire.send_calls > self._wire.send_ok_calls:
            raise self._wire.send_error
        self._buffer += data

    def makefile(self, mode: str) -> io.BufferedReader:
        # A real socket's makefile("rb") is a BufferedReader over a raw stream; so is this one.
        reply = self._wire.next_reply()
        raw = _FailingRaw(reply) if isinstance(reply, BaseException) else io.BytesIO(reply)
        return io.BufferedReader(raw)  # type: ignore[arg-type]

    def close(self) -> None:
        return None


class _FailingRaw(io.RawIOBase):
    def __init__(self, error: BaseException) -> None:
        self._error = error

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        raise self._error


def http_reply(status: int, body: bytes = b"{}", *, extra_headers: str = "") -> bytes:
    head = f"HTTP/1.1 {status} Status\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n{extra_headers}\r\n"
    return head.encode("ascii") + body


def ok_completion_body() -> bytes:
    return json.dumps(
        {
            "id": "gen-1",
            "model": "cn/alpha",
            "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": "0.00001"},
        }
    ).encode()
