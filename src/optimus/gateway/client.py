from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.models import (
    GatewayResponse,
    GatewayUsage,
    build_responses_payload,
    parse_gateway_response,
    parse_gateway_usage,
)


@dataclass(frozen=True)
class GatewayRequest:
    method: str
    url: str
    headers: dict[str, str]
    payload: dict[str, Any]
    timeout_seconds: float = 30.0

    def __repr__(self) -> str:
        safe_headers = dict(self.headers)
        if "Authorization" in safe_headers:
            safe_headers["Authorization"] = "Bearer **********"
        return (
            "GatewayRequest("
            f"method={self.method!r}, url={self.url!r}, headers={safe_headers!r}, "
            f"payload={self.payload!r}, timeout_seconds={self.timeout_seconds!r})"
        )

    def body_bytes(self) -> bytes:
        return json.dumps(self.payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


class GatewayTransport(Protocol):
    def post_json(self, request: GatewayRequest) -> dict[str, Any]:
        """Send JSON to the gateway and return a decoded JSON object."""


# Production transport seam: stdlib urllib keeps Phase 1 free of HTTP client deps.
# Tests inject a fake transport instead; release-gate E2E can add outbound intercept later.
class UrllibGatewayTransport:
    def post_json(self, request: GatewayRequest) -> dict[str, Any]:
        urllib_request = Request(
            request.url,
            data=request.body_bytes(),
            headers=request.headers,
            method=request.method,
        )
        try:
            with urlopen(urllib_request, timeout=request.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            gateway_usage = _try_parse_error_usage(detail)
            raise GatewayHttpError(
                exc.code, detail or exc.reason, gateway_usage=gateway_usage
            ) from exc
        except URLError as exc:
            raise GatewayHttpError(0, str(exc.reason)) from exc

        return _decode_gateway_json(body)


class GatewayClient:
    """
    This class provides a client interface for interacting with the Gateway service.

    The class enables interacting with the Gateway service through HTTP requests. Supported
    operations include creating responses, posting tool-specific data, and sending
    observability information. It also abstracts the underlying transport mechanism and
    provides configuration options for timeouts and authentication.

    :ivar settings: Configuration object for the Gateway API, including gateway URL
        and authentication details.
    :type settings: OptimusGatewaySettings
    :ivar transport: Transport mechanism for sending HTTP requests. Defaults to
        `UrllibGatewayTransport` if not provided.
    :type transport: GatewayTransport | None
    :ivar timeout_seconds: Default timeout for network requests, in seconds.
    :type timeout_seconds: float
    """
    def __init__(
        self,
        *,
        settings: OptimusGatewaySettings,
        transport: GatewayTransport | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._settings = settings
        self._transport = transport or UrllibGatewayTransport()
        self._timeout_seconds = timeout_seconds

    def create_response(
        self,
        *,
        model: str,
        input_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        self._settings.validate_trusted_gateway()
        body = self._transport.post_json(
            GatewayRequest(
                method="POST",
                url=self._url("/v1/responses"),
                headers=self._json_headers(),
                payload=build_responses_payload(model=model, input_text=input_text, metadata=metadata),
                timeout_seconds=self._timeout_seconds,
            )
        )
        return parse_gateway_response(body)

    def post_tool_json(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not path.startswith("/v1/tools/"):
            raise ValueError("tool path must start with /v1/tools/")
        self._settings.validate_trusted_gateway()
        return self._transport.post_json(
            GatewayRequest(
                method="POST",
                url=self._url(path),
                headers=self._json_headers(),
                payload=payload,
                timeout_seconds=self._timeout_seconds,
            )
        )

    def post_observability_json(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not path.startswith("/v1/observability/"):
            raise ValueError("observability path must start with /v1/observability/")
        self._settings.validate_trusted_gateway()
        return self._transport.post_json(
            GatewayRequest(
                method="POST",
                url=self._url(path),
                headers=self._json_headers(),
                payload=payload,
                timeout_seconds=self._timeout_seconds,
            )
        )

    def _url(self, path: str) -> str:
        return f"{self._settings.gateway_url.rstrip('/')}{path}"

    def _json_headers(self) -> dict[str, str]:
        headers = self._settings.auth_headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        return headers


def _try_parse_error_usage(detail: str) -> GatewayUsage | None:
    """Attempt to extract valid gateway_usage from an HTTP error body.

    Returns a validated GatewayUsage if the body is a JSON object containing a
    valid gateway_usage envelope. Returns None for non-JSON bodies, non-object
    JSON, missing gateway_usage, or invalid gateway_usage — without raising.
    """
    try:
        decoded = json.loads(detail, parse_float=Decimal)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(decoded, dict):
        return None
    usage_body = decoded.get("gateway_usage")
    if not isinstance(usage_body, dict):
        return None
    try:
        return parse_gateway_usage(usage_body)
    except Exception:  # noqa: BLE001 — intentionally broad; invalid usage is not an error here
        return None


def _decode_gateway_json(body: str) -> dict[str, Any]:
    try:
        decoded = json.loads(body, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise GatewayHttpError(0, "gateway returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise GatewayHttpError(0, "gateway returned non-object JSON")
    return decoded
