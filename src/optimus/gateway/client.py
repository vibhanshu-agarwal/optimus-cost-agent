from __future__ import annotations

import contextlib
import json
import math
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.errors import GatewayHttpError, GatewayResponseError
from optimus.gateway.models import (
    GatewayDecision,
    GatewayResponse,
    GatewayRouteAttempt,
    GatewayUsage,
    build_responses_payload,
    parse_decision_response,
    parse_gateway_response,
    parse_gateway_usage,
    parse_route_attempts,
)
from optimus_model_policy.binding import HOST_GATEWAY_TIMEOUT_SECONDS
from optimus_security.failure_facts import exception_fact
from optimus_security.usage_capture_contract import CAPTURE_REQUEST_HEADER, CAPTURE_REQUEST_ID

if TYPE_CHECKING:
    from optimus_model_policy.binding import RouteBinding

# Shared upstream-dispatch budget plus processing slack; delivery depends on responsive Gateway processing and storage.
DEFAULT_GATEWAY_TIMEOUT_SECONDS = HOST_GATEWAY_TIMEOUT_SECONDS


@dataclass(frozen=True)
class CaptureIntent:
    """The durable-capture identity of one host request (Plan 12.8): the turn it serves, the host request ID its receipts
    are numbered from (their `attempt_id` is this ID or this ID plus `:<attempt>`), its stage and optional purpose."""

    turn_id: str
    host_request_id: str
    stage: str
    purpose: str | None = None
    requested_model: str | None = None


CaptureHook = Callable[[CaptureIntent], bool]
_CURRENT_INTENT: ContextVar[CaptureIntent | None] = ContextVar("optimus_capture_intent", default=None)


@contextmanager
def capturing(intent: CaptureIntent) -> Iterator[None]:
    """Model requests sent in this block carry ``intent``: the Gateway client records it before it sends."""
    token = _CURRENT_INTENT.set(intent)
    try:
        yield
    finally:
        _CURRENT_INTENT.reset(token)


def validate_gateway_timeout_seconds(value: object) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError("gateway timeout must be a positive finite number of seconds") from None
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError("gateway timeout must be a positive finite number of seconds")
    return parsed


@dataclass(frozen=True)
class GatewayRequest:
    method: str
    url: str
    headers: dict[str, str]
    payload: dict[str, Any]
    timeout_seconds: float = DEFAULT_GATEWAY_TIMEOUT_SECONDS

    def __repr__(self) -> str:
        safe_headers = dict(self.headers)
        for key in tuple(safe_headers):
            if key.lower() == "authorization":
                safe_headers[key] = "Bearer **********"
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
            raw = exc.read()
            detail = raw.decode("utf-8", errors="replace")
            gateway_usage = _try_parse_error_usage(detail)
            gateway_code, retryable, route_attempts = _try_parse_error_correlation(detail)
            raise GatewayHttpError(
                exc.code,
                detail or exc.reason,
                gateway_usage=gateway_usage,
                gateway_code=gateway_code,
                retryable=retryable,
                route_attempts=route_attempts,
                route_attempts_malformed=_route_attempts_dropped(detail, route_attempts),
                error_envelope=_error_envelope(raw, detail),
            ) from exc
        except URLError as exc:
            raise GatewayHttpError(0, str(exc.reason), failure={"kind": "transport", **exception_fact(exc)}) from exc

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
        timeout_seconds: float = DEFAULT_GATEWAY_TIMEOUT_SECONDS,
        capture: CaptureHook | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport or UrllibGatewayTransport()
        self._timeout_seconds = validate_gateway_timeout_seconds(timeout_seconds)
        self._capture = capture

    def create_response(
        self,
        *,
        model: str,
        input_text: str,
        metadata: dict[str, Any] | None = None,
        route_binding: RouteBinding | None = None,
    ) -> GatewayResponse:
        """``route_binding`` binds the trusted model registry, request identity, output cap and any
        Contributor disclosure (Plan 12.2 Task 5); it is sent only once registry enforcement is active.
        Inside :func:`capturing`, the request's durable pre-dispatch intent is recorded first (Plan 12.8)."""
        self._settings.validate_trusted_gateway()
        body = self._transport.post_json(
            GatewayRequest(
                method="POST",
                url=self._url("/v1/responses"),
                headers=self._dispatch_headers(),
                payload=build_responses_payload(
                    model=model, input_text=input_text, metadata=metadata, route_binding=route_binding
                ),
                timeout_seconds=self._timeout_seconds,
            )
        )
        return parse_gateway_response(body)

    def create_decision(
        self, *, model: str, state: dict[str, Any], questions: dict[str, Any], route_binding: RouteBinding
    ) -> GatewayDecision:
        """One classifier decision (Plan 12.4 Task 5): ``POST /v1/decisions`` with the request's binding. Errors arrive
        as for any Gateway request; a 200 reply is parsed by :func:`parse_decision_response`."""
        self._settings.validate_trusted_gateway()
        body = self._transport.post_json(
            GatewayRequest(
                method="POST",
                url=self._url("/v1/decisions"),
                headers=self._dispatch_headers(),
                payload={"model": model, "state": state, "questions": questions, "route_binding": route_binding.to_wire()},
                timeout_seconds=self._timeout_seconds,
            )
        )
        return parse_decision_response(body)

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

    def _dispatch_headers(self) -> dict[str, str]:
        """The model request's headers, after its pre-dispatch intent is recorded. Capture never refuses or fails a
        send: a missing hook, a malformed identity or a hook failure leaves the intent unrecorded and the request
        unchanged except for the header it would have carried."""
        headers = self._json_headers()
        intent = _CURRENT_INTENT.get()
        if intent is None or not CAPTURE_REQUEST_ID.fullmatch(intent.host_request_id):
            return headers
        if self._capture is not None:
            with contextlib.suppress(Exception):  # capture is best effort here; its own records show the gap
                self._capture(intent)
        headers[CAPTURE_REQUEST_HEADER] = intent.host_request_id
        return headers

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


def _try_parse_error_correlation(detail: str) -> tuple[str | None, bool | None, tuple[GatewayRouteAttempt, ...]]:
    """The enforced-routing fields of an HTTP error body: its stable code, whether the host may
    re-send, and the provider attempts made. A body without them (today's routing) yields
    ``(None, None, ())``; malformed attempts are dropped without discarding ``retryable``."""
    try:
        decoded = json.loads(detail, parse_float=Decimal)
    except (json.JSONDecodeError, ValueError):
        return None, None, ()
    if not isinstance(decoded, dict):
        return None, None, ()
    code = decoded.get("code") if isinstance(decoded.get("code"), str) else None
    retryable = decoded.get("retryable") if isinstance(decoded.get("retryable"), bool) else None
    attempts: tuple[GatewayRouteAttempt, ...] = ()
    if "route_attempts" in decoded:
        try:
            attempts = parse_route_attempts(decoded["route_attempts"])
        except Exception:  # noqa: BLE001 — a malformed record list is dropped, never fatal here
            attempts = ()
    return code, retryable, attempts


def _error_envelope(raw: bytes, detail: str) -> dict[str, str | None]:
    """Why an HTTP error body could not be used, in fixed values (correction plan v4, C3): whether its bytes were valid
    UTF-8 (checked before the replacement decode loses it), whether the decoded text was a JSON object, and the audit
    code of a ``gateway_usage`` it carried that failed validation (absent usage is no fault). The parsing and
    accounting are unchanged; the body itself is never kept."""
    try:
        raw.decode("utf-8")
        encoding = "ok"
    except UnicodeDecodeError:
        encoding = "invalid_utf8"
    try:
        decoded = json.loads(detail, parse_float=Decimal)
    except ValueError:
        return {"error_body_encoding": encoding, "error_body": "invalid_json", "usage_audit_code": None}
    if not isinstance(decoded, dict):
        return {"error_body_encoding": encoding, "error_body": "non_object", "usage_audit_code": None}
    audit_code = None
    if "gateway_usage" in decoded:
        try:
            parse_gateway_usage(decoded["gateway_usage"])
        except GatewayResponseError as exc:
            audit_code = exc.audit_code or "GATEWAY_USAGE_INVALID"
        except Exception:  # noqa: BLE001 - any other validation failure is still invalid usage
            audit_code = "GATEWAY_USAGE_INVALID"
    return {"error_body_encoding": encoding, "error_body": "ok", "usage_audit_code": audit_code}


def _route_attempts_dropped(detail: str, parsed: tuple[GatewayRouteAttempt, ...]) -> bool:
    """Whether an error body carried a non-empty ``route_attempts`` value that parsing had to drop."""
    if parsed:
        return False
    try:
        decoded = json.loads(detail, parse_float=Decimal)
    except (json.JSONDecodeError, ValueError):
        return False
    if not isinstance(decoded, dict) or "route_attempts" not in decoded:
        return False
    return decoded["route_attempts"] != []


def _decode_gateway_json(body: str) -> dict[str, Any]:
    try:
        decoded = json.loads(body, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise GatewayHttpError(0, "gateway returned invalid JSON", failure={"kind": "gateway_invalid_json"}) from exc
    if not isinstance(decoded, dict):
        raise GatewayHttpError(0, "gateway returned non-object JSON", failure={"kind": "gateway_non_object_json"})
    return decoded
