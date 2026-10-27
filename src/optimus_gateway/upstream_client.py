from __future__ import annotations

import functools
import http.client
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from http.client import HTTPException
from typing import Any, Final, Literal, NamedTuple, Protocol, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPDefaultErrorHandler,
    HTTPErrorProcessor,
    HTTPHandler,
    HTTPSHandler,
    OpenerDirector,
    ProxyHandler,
    Request,
    UnknownHandler,
    urlopen,
)

from optimus_model_policy.binding import ATTEMPT_NOT_SENT, ATTEMPT_REJECTED, ATTEMPT_UNCERTAIN
from optimus_security.failure_facts import bounded, exception_fact, guardrail_stage_facts, slug

# OpenRouter's documented router pipeline stage types (router-metadata guide, 2026-10-20). Any other type is
# recorded as ``unrecognized``: it still counts as a stage, but its text is never persisted.
KNOWN_ROUTER_STAGES = frozenset({"guardrail", "plugin", "server_tools", "response_healing", "context_compression"})

T = TypeVar("T")

_MAX_UPSTREAM_ATTEMPTS = 4
_MODEL_MAX_UPSTREAM_ATTEMPTS = 3
_TRANSIENT_HTTP_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_DEFAULT_BACKOFF_SECONDS = (0.05, 0.1, 0.2)


@dataclass(frozen=True)
class RetryEvent:
    attempt: int
    classification: str
    latency_seconds: float
    disposition: Literal["retry", "terminal"]
    failure: dict[str, Any] | None = None
    """The failed attempt's bounded cause, taken where it arose (correction plan v4, C9)."""


@dataclass(frozen=True)
class ProviderMessageResult:
    message_id: str
    output_text: str
    input_tokens: int
    output_tokens: int
    total_tokens: int | None
    billing_units: int
    cost_usd: Decimal
    provider: str
    resolved_provider: str | None
    requested_model: str
    resolved_model: str | None
    model_version: str | None
    cache_hit: bool
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    cache_age_seconds: int | None = None
    finish_reason: str | None = None
    """The provider's own finish status, lower-cased (``stop``, ``length``, ...); ``None`` when the
    provider reported none. Never synthesized (Plan 12.2 Task 5)."""
    router_attempt: int | None = None
    """OpenRouter's 1-indexed successful routing attempt (above 1: earlier attempts fell back); ``None``
    without router metadata."""
    router_pipeline: tuple[str, ...] | None = None
    """The ``type`` of every router pipeline stage that materially changed the request or response
    (compression, guardrails, ...); empty when none ran, ``None`` without router metadata."""
    router_guardrails: tuple[dict[str, Any], ...] | None = None
    """Each ``guardrail`` stage's closed facts, in pipeline order (``failure_facts.guardrail_stage_facts``, #400);
    empty when none ran, ``None`` without router metadata. Only the experimental route's pipeline check reads them,
    to accept the one unflagged stage of #400 option b1 (``model_policy.unflagged_guardrail_only``)."""
    router_metadata_error: str | None = None
    """Why the router metadata could not be read (malformed, or more than one selected endpoint). Its
    routing fields are then all ``None``; the reply's usage and cost do not depend on it."""


class UpstreamClient(Protocol):
    def create_message(self, *, model: str, input_text: str) -> ProviderMessageResult:
        """Call an upstream LLM API and return normalized text + usage (today's routing)."""

    def create_message_once(
        self,
        *,
        model: str,
        input_text: str,
        max_tokens: int,
        provider_controls: Mapping[str, Any],
        reasoning: str | None,
    ) -> ProviderMessageResult:
        """One provider attempt under an enforced model policy; raises UpstreamAttemptFailure."""

    def create_decision_once(
        self,
        *,
        model: str,
        state: Mapping[str, Any],
        questions: Mapping[str, Any],
        provider_controls: Mapping[str, Any],
    ) -> DecisionResult:
        """One System One decision attempt under an enforced model policy; raises UpstreamAttemptFailure."""


class RetryableUpstreamError(Exception):
    """Transient gateway→provider fault eligible for local retry before RuntimeError."""


def is_retryable_upstream_fault(exc: BaseException) -> bool:
    """Classify gateway→provider faults while HTTP/network shape is still visible."""
    if isinstance(exc, RetryableUpstreamError):
        return True
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, HTTPError):
        return exc.code in _TRANSIENT_HTTP_STATUS_CODES
    if isinstance(exc, URLError):
        return True
    return False


def call_with_upstream_retry(
    operation: Callable[[], T],
    *,
    max_attempts: int = _MAX_UPSTREAM_ATTEMPTS,
    sleep: Callable[[float], None] | None = None,
    on_retry: Callable[[int], None] | None = None,
    on_attempt_failure: Callable[[int, str, float, Literal["retry", "terminal"], dict[str, Any] | None], None] | None = None,
    backoff_seconds: tuple[float, ...] = _DEFAULT_BACKOFF_SECONDS,
) -> T:
    """Retry only transient upstream faults; reraise the final failure as RuntimeError. ``on_attempt_failure`` also
    gets each failed attempt's bounded cause (correction plan v4, C9)."""
    sleeper = sleep or time.sleep
    attempt = 1
    while True:
        started_at = time.monotonic()
        try:
            return operation()
        except Exception as exc:
            retryable = is_retryable_upstream_fault(exc)
            disposition: Literal["retry", "terminal"] = (
                "retry" if retryable and attempt < max_attempts else "terminal"
            )
            if on_attempt_failure is not None:
                on_attempt_failure(
                    attempt,
                    "transient" if retryable else "permanent",
                    time.monotonic() - started_at,
                    disposition,
                    _attempt_failure(exc),
                )
            if disposition == "terminal":
                if retryable:
                    raise RuntimeError(str(exc)) from exc
                raise
            if on_retry is not None:
                on_retry(attempt)
            delay = backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)]
            sleeper(delay)
            attempt += 1


class UrllibOpenAICompatibleClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 60.0,
        max_attempts: int = _MODEL_MAX_UPSTREAM_ATTEMPTS,
        sleep: Callable[[float], None] | None = None,
        on_retry: Callable[[RetryEvent], None] | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._on_retry = on_retry
        self._attempt_opener: OpenerDirector | None = None

    def _request(self, payload: Mapping[str, Any], request_class: type[Request] = Request, *, path: str = "/chat/completions") -> Request:
        return request_class(
            f"{self._base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "content-type": "application/json",
                "X-OpenRouter-Metadata": "enabled",
            },
            method="POST",
        )

    def create_message(self, *, model: str, input_text: str) -> ProviderMessageResult:
        """Today's routing: one request with the legacy transient-fault retry loop."""
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": input_text}],
        }
        request = self._request(payload)

        def call() -> ProviderMessageResult:
            body, headers = _urlopen_json(
                request,
                timeout_seconds=self._timeout_seconds,
                label="upstream",
            )
            return parse_openai_chat_completion(body, headers, requested_model=model)

        def report_failure(
            attempt: int,
            classification: str,
            latency_seconds: float,
            disposition: Literal["retry", "terminal"],
            failure: dict[str, Any] | None = None,
        ) -> None:
            if self._on_retry is not None:
                self._on_retry(
                    RetryEvent(
                        attempt=attempt,
                        classification=classification,
                        latency_seconds=latency_seconds,
                        disposition=disposition,
                        failure=failure,
                    )
                )

        return call_with_upstream_retry(
            call,
            max_attempts=self._max_attempts,
            sleep=self._sleep,
            on_attempt_failure=report_failure,
        )

    def create_message_once(
        self,
        *,
        model: str,
        input_text: str,
        max_tokens: int,
        provider_controls: Mapping[str, Any],
        reasoning: str | None,
    ) -> ProviderMessageResult:
        """Exactly one provider attempt under an enforced model policy (Plan 12.2 Task 5).

        No retry happens here: the Gateway decides, per the attempt contract, whether a failed attempt
        may be followed by one recovery attempt. A failure raises :class:`UpstreamAttemptFailure` saying
        whether the request certainly never reached a model or may have run and been billed.

        Wire mapping v1: the output cap is OpenRouter's ``max_tokens``, the approved endpoints are its
        ``provider`` routing object, and the approved reasoning level is ``reasoning.effort``.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": input_text}],
            "max_tokens": max_tokens,
            "provider": json.loads(json.dumps(dict(provider_controls))),
        }
        if reasoning is not None:
            payload["reasoning"] = {"effort": reasoning}
        request = _attempt_of(self._request(payload, request_class=_AttemptRequest))
        if self._attempt_opener is None:
            self._attempt_opener = _build_attempt_opener()
        try:
            with self._attempt_opener.open(request, timeout=self._timeout_seconds) as response:
                raw = response.read()
                headers = {str(name).casefold(): str(value) for name, value in getattr(response, "headers", {}).items()}
        except HTTPError as exc:
            # A 4xx (other than a request timeout) is the provider refusing the request before any
            # model ran; a 408, a 5xx or an unfollowed redirect may follow a model run that was billed.
            refused = 400 <= exc.code < 500 and exc.code != 408
            # The upstream error body is never read: a moderation error can echo the prompt.
            raise UpstreamAttemptFailure(
                ATTEMPT_REJECTED if refused else ATTEMPT_UNCERTAIN, http_status=exc.code, failure={"kind": "http"}
            ) from exc
        except (OSError, HTTPException) as exc:
            # urllib wraps an OSError raised while connecting *or* while sending in the same URLError,
            # so the exception's type cannot say whether the request left (an SSLError, a refusal or an
            # unreachable host can each arise in either phase; Codex CP1 corrections review). The phase
            # can: a failure before the connection was established delivered nothing, and any later
            # failure may have reached a model that ran and was billed.
            raise UpstreamAttemptFailure(
                ATTEMPT_UNCERTAIN if request.connected else ATTEMPT_NOT_SENT, failure={"kind": "transport", **exception_fact(exc)}
            ) from exc
        try:
            decoded = json.loads(raw.decode("utf-8"))
            if not isinstance(decoded, dict):
                raise RuntimeError("upstream response was not an object")
            return parse_openai_chat_completion(decoded, headers, requested_model=model)
        except (UnicodeError, ValueError, RuntimeError) as exc:
            # A reply arrived but its usage cannot be verified: it may have been billed.
            raise UpstreamAttemptFailure(ATTEMPT_UNCERTAIN, failure=_unreadable_reply(exc)) from exc

    def create_decision_once(
        self,
        *,
        model: str,
        state: Mapping[str, Any],
        questions: Mapping[str, Any],
        provider_controls: Mapping[str, Any],
    ) -> DecisionResult:
        """Exactly one System One decision attempt (Plan 12.4 v7: the Jev adapter), with the same attempt contract
        as :meth:`create_message_once`: a failure says whether the request certainly reached no model or may have
        been billed, and nothing is retried here. The approved endpoints are the request's ``provider`` object."""
        payload = {
            "model": model,
            "state": json.loads(json.dumps(dict(state))),
            "questions": json.loads(json.dumps(dict(questions))),
            "provider": json.loads(json.dumps(dict(provider_controls))),
        }
        request = _attempt_of(self._request(payload, request_class=_AttemptRequest, path="/systemone"))
        if self._attempt_opener is None:
            self._attempt_opener = _build_attempt_opener()
        try:
            with self._attempt_opener.open(request, timeout=self._timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            refused = 400 <= exc.code < 500 and exc.code != 408
            # The upstream error body is never read: it can echo the request's state.
            raise UpstreamAttemptFailure(
                ATTEMPT_REJECTED if refused else ATTEMPT_UNCERTAIN, http_status=exc.code, failure={"kind": "http"}
            ) from exc
        except (OSError, HTTPException) as exc:
            raise UpstreamAttemptFailure(
                ATTEMPT_UNCERTAIN if request.connected else ATTEMPT_NOT_SENT, failure={"kind": "transport", **exception_fact(exc)}
            ) from exc
        try:
            decoded = json.loads(raw.decode("utf-8"))
            if not isinstance(decoded, dict):
                raise RuntimeError("decision response was not an object")
            return parse_decision_response(decoded, questions=questions)
        except (UnicodeError, ValueError, RuntimeError) as exc:
            raise UpstreamAttemptFailure(ATTEMPT_UNCERTAIN, failure=_unreadable_reply(exc)) from exc


@dataclass(frozen=True)
class DecisionResult:
    """One System One decision reply: its typed answers and the usage it reported (output is free, so ``cost_usd``
    is the input charge)."""

    decision_id: str
    resolved_model: str
    resolved_provider: str | None
    answers: Mapping[str, Any]
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


_DECISION_TYPES: Final = frozenset({"choice", "noul", "score"})


def parse_decision_response(body: Mapping[str, Any], *, questions: Mapping[str, Any]) -> DecisionResult:
    """Parse a System One reply, failing closed: every asked question has exactly one answer of its own type with a
    value in range, and the usage is complete. A reply that cannot be verified raises ``RuntimeError``."""
    decision_id, resolved_model = body.get("id"), body.get("model")
    if not isinstance(decision_id, str) or not decision_id or not isinstance(resolved_model, str) or not resolved_model:
        raise RuntimeError("decision response has no id or model")
    provider = body.get("provider")
    answers = body.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise RuntimeError("decision answers do not match the questions")
    for name, answer in answers.items():
        asked = questions[name]
        kind = asked.get("type") if isinstance(asked, dict) else None
        if not isinstance(answer, dict) or answer.get("type") != kind or kind not in _DECISION_TYPES:
            raise RuntimeError("a decision answer has the wrong type")
        value = answer.get(kind)
        if kind == "choice" and not (isinstance(value, str) and value in asked.get("criteria", {})):
            raise RuntimeError("a choice answer is not one of the options")
        if kind == "noul" and not (isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1):
            raise RuntimeError("a noul answer is not a probability")
        if kind == "score" and not (isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= max(len(asked.get("criteria", [])) - 1, 0)):
            raise RuntimeError("a score answer is outside its scale")
    usage = body.get("usage")
    if not isinstance(usage, dict):
        raise RuntimeError("decision response has no usage")
    cost = usage.get("cost")
    if isinstance(cost, bool) or not isinstance(cost, (int, float, str)):
        raise RuntimeError("decision usage has no cost")
    try:
        cost_usd = Decimal(str(cost))
    except ArithmeticError as exc:
        raise RuntimeError("decision usage cost is not a number") from exc
    if not cost_usd.is_finite() or cost_usd < 0:
        raise RuntimeError("decision usage cost is not a non-negative number")
    return DecisionResult(
        decision_id=decision_id,
        resolved_model=resolved_model,
        resolved_provider=provider if isinstance(provider, str) and provider else None,
        answers=answers,
        input_tokens=_required_nonnegative_int(usage.get("input_tokens"), "input_tokens"),
        output_tokens=_required_nonnegative_int(usage.get("output_tokens"), "output_tokens"),
        cost_usd=cost_usd,
    )


class _AttemptRequest(Request):
    """One enforced attempt's request. ``connected`` turns true once its connection is established (the
    TCP connect, any proxy tunnel and the TLS handshake have all completed): the earliest point at which
    request bytes may leave. Until then a failure certainly delivered nothing."""

    connected = False


class _MarksAttemptConnected:
    """Mixed into an http.client connection: marks the attempt connected when ``connect()`` returns.
    http.client connects lazily from its first ``send()``, before writing any request byte."""

    def __init__(self, *args: Any, attempt: _AttemptRequest, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._attempt = attempt

    def connect(self) -> None:
        super().connect()  # type: ignore[misc]
        self._attempt.connected = True


class _AttemptHTTPConnection(_MarksAttemptConnected, http.client.HTTPConnection):
    pass


class _AttemptHTTPSConnection(_MarksAttemptConnected, http.client.HTTPSConnection):
    pass


def _attempt_of(req: Request) -> _AttemptRequest:
    if not isinstance(req, _AttemptRequest):
        # Fail closed: an untracked request could only ever be classified "not sent".
        raise TypeError("an enforced attempt must be an _AttemptRequest")
    return req


class _AttemptHTTPHandler(HTTPHandler):
    def http_open(self, req: Request) -> http.client.HTTPResponse:
        return self.do_open(functools.partial(_AttemptHTTPConnection, attempt=_attempt_of(req)), req)


class _AttemptHTTPSHandler(HTTPSHandler):
    def https_open(self, req: Request) -> http.client.HTTPResponse:
        # As the standard handler does, with the TLS context it built.
        return self.do_open(functools.partial(_AttemptHTTPSConnection, attempt=_attempt_of(req)), req, context=self._context)  # type: ignore[attr-defined]


def _build_attempt_opener() -> OpenerDirector:
    """``urlopen``'s default handlers (proxies, HTTP error handling) with three differences:
    - HTTP and HTTPS connections record their attempt's phase;
    - there is no redirect handler, because an attempt is one exchange; following a redirect would send
      again, to another URL, so a 3xx surfaces as an HTTP error and is classified by its status;
    - there are no FTP, file or data handlers, so no other scheme can open an untracked connection; it
      fails as an unknown URL type before anything is sent."""
    opener = OpenerDirector()
    for handler in (
        ProxyHandler(),
        UnknownHandler(),
        _AttemptHTTPHandler(),
        _AttemptHTTPSHandler(),
        HTTPDefaultErrorHandler(),
        HTTPErrorProcessor(),
    ):
        opener.add_handler(handler)
    return opener


def _unreadable_reply(exc: BaseException) -> dict[str, Any]:
    """Why an arrived reply could not be read: invalid UTF-8, invalid JSON, or this module's own schema reason as a
    slug. Never the reply's text."""
    if isinstance(exc, UnicodeError):
        return {"kind": "invalid_utf8"}
    if isinstance(exc, json.JSONDecodeError):
        return {"kind": "invalid_json"}
    return {"kind": "schema", "reason": slug(str(exc))}


class UpstreamAttemptFailure(Exception):
    """One enforced provider attempt that did not complete, and what is known about it. ``failure`` is its bounded,
    content-free cause (Plan 12.2 diagnosability): ``http``, ``transport`` with the exception class and errno,
    ``invalid_utf8``, ``invalid_json`` or ``schema`` with a module-authored reason."""

    def __init__(self, outcome: str, *, http_status: int | None = None, failure: dict[str, Any] | None = None) -> None:
        self.outcome = outcome
        self.http_status = http_status
        self.failure = failure
        super().__init__(f"upstream attempt {outcome}" + (f" ({http_status})" if http_status is not None else ""))

    @property
    def recoverable(self) -> bool:
        """True only when the attempt certainly reached no model: never sent, or rate-limited (429)."""
        return self.outcome == ATTEMPT_NOT_SENT or (self.outcome == ATTEMPT_REJECTED and self.http_status == 429)


def _urlopen_json(
    request: Request, *, timeout_seconds: float, label: str
) -> tuple[dict[str, Any], dict[str, str]]:
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            decoded = json.loads(response.read().decode("utf-8"))
            if not isinstance(decoded, dict):
                raise RuntimeError(f"{label} response was not an object")
            headers = {
                str(name).casefold(): str(value)
                for name, value in getattr(response, "headers", {}).items()
            }
            return decoded, headers
    # Each raise carries its bounded cause, taken here while the original exception is in hand (correction plan v4, C9).
    # The exceptions' types, texts and retry classification are unchanged.
    except HTTPError as exc:
        message = f"{label} request failed ({exc.code})"
        error = RetryableUpstreamError(message) if is_retryable_upstream_fault(exc) else RuntimeError(message)
        raise _with_failure(error, {"kind": "http", "status": exc.code}) from exc
    except URLError as exc:
        fact = exception_fact(exc)
        raise _with_failure(RetryableUpstreamError(f"{label} request failed ({fact.get('cause', fact['class'])})"), {"kind": "transport", **fact}) from exc
    except TimeoutError as exc:
        raise _with_failure(RetryableUpstreamError(f"{label} request timed out"), {"kind": "transport", **exception_fact(exc)}) from exc
    except (UnicodeError, json.JSONDecodeError) as exc:
        kind = "invalid_utf8" if isinstance(exc, UnicodeError) else "invalid_json"
        raise _with_failure(RuntimeError(f"{label} response was invalid JSON"), {"kind": kind}) from exc


def _with_failure(error: Exception, failure: dict[str, Any]) -> Exception:
    error.failure = failure  # type: ignore[attr-defined]
    return error


def _attempt_failure(exc: BaseException) -> dict[str, Any]:
    """A failed legacy attempt's bounded cause: the one ``_urlopen_json`` attached, else a parser ``RuntimeError``'s
    module-authored reason as a slug, else the exception's class and errno."""
    failure = getattr(exc, "failure", None)
    if isinstance(failure, dict):
        return failure
    if type(exc) is RuntimeError:
        return {"kind": "schema", "reason": slug(str(exc))}
    return exception_fact(exc)


def parse_openai_chat_completion(
    body: dict[str, Any],
    headers: dict[str, str],
    *,
    requested_model: str,
) -> ProviderMessageResult:
    normalized_headers = {name.casefold(): value for name, value in headers.items()}
    message_id = body.get("id")
    if not isinstance(message_id, str) or not message_id:
        raise RuntimeError("upstream response missing id")

    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("upstream response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError("upstream response missing choices[0]")
    message = first.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("upstream response missing message")
    output_text = message.get("content")
    if not isinstance(output_text, str):
        raise RuntimeError("upstream response missing message content")
    # A missing or malformed finish status reads as None ("not reported"): it is never trusted as
    # complete, and the billed call keeps its usage either way (Plan 12.2 Task 5).
    raw_finish = first.get("finish_reason")
    finish_reason = raw_finish.strip().casefold() if isinstance(raw_finish, str) and raw_finish.strip() else None

    usage = body.get("usage")
    if not isinstance(usage, dict):
        raise RuntimeError("upstream response missing usage")
    input_tokens = _required_nonnegative_int(usage.get("prompt_tokens"), "input token count")
    output_tokens = _required_nonnegative_int(usage.get("completion_tokens"), "output token count")
    total_tokens_value = usage.get("total_tokens")
    total_tokens = (
        _required_nonnegative_int(total_tokens_value, "total token count")
        if total_tokens_value is not None
        else None
    )
    billing_units_value = total_tokens if total_tokens is not None else usage.get("billing_units")
    billing_units = _required_nonnegative_int(billing_units_value, "provider billing units")
    cost_usd = _provider_cost(usage.get("cost"))

    router = _router_evidence(body.get("openrouter_metadata"))
    resolved_model = _optional_string(body, "model", "model") or router.model
    model_version = _optional_string(body, "model_version", "model version")

    prompt_details = usage.get("prompt_tokens_details")
    if prompt_details is not None and not isinstance(prompt_details, dict):
        raise RuntimeError("upstream response has invalid prompt token details")
    completion_details = usage.get("completion_tokens_details")
    if completion_details is not None and not isinstance(completion_details, dict):
        raise RuntimeError("upstream response has invalid completion token details")
    cached_tokens = _optional_nonnegative_int(prompt_details, "cached_tokens", "cached token count")
    reasoning_tokens = _optional_nonnegative_int(
        completion_details, "reasoning_tokens", "reasoning token count"
    )
    cache_status = normalized_headers.get("x-openrouter-cache-status", "").casefold()
    cache_age_seconds = _optional_header_nonnegative_int(
        normalized_headers, "x-openrouter-cache-age"
    )

    return ProviderMessageResult(
        message_id=message_id,
        output_text=output_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        billing_units=billing_units,
        cost_usd=cost_usd,
        provider="openrouter",
        resolved_provider=router.provider,
        requested_model=requested_model,
        resolved_model=resolved_model,
        model_version=model_version,
        cache_hit=cache_status == "hit",
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
        cache_age_seconds=cache_age_seconds,
        finish_reason=finish_reason,
        router_attempt=router.attempt,
        router_pipeline=router.pipeline,
        router_guardrails=router.guardrails,
        router_metadata_error=router.error,
    )


class _RouterEvidence(NamedTuple):
    provider: str | None = None
    model: str | None = None
    attempt: int | None = None
    pipeline: tuple[str, ...] | None = None
    guardrails: tuple[dict[str, Any], ...] | None = None
    error: str | None = None


def _router_evidence(metadata: object) -> _RouterEvidence:
    """What the router metadata says about routing, kept apart from billing (Codex Haiku Stage A
    review M1): metadata that cannot be read leaves every routing field unknown and says why, so a
    route that relies on it can refuse the reply, and the reply's valid usage is never discarded."""
    if metadata is None:
        return _RouterEvidence()
    try:
        if not isinstance(metadata, dict):
            raise RuntimeError("upstream response has malformed router metadata")
        selected = _selected_endpoint(metadata)
        pipeline = _router_pipeline(metadata)
        return _RouterEvidence(
            provider=_optional_string(selected, "provider", "router metadata"),
            model=_optional_string(selected, "model", "router metadata"),
            attempt=_optional_nonnegative_int(metadata, "attempt", "router metadata attempt"),
            pipeline=pipeline,
            # _router_pipeline has already checked that every stage is an object with a string type.
            guardrails=tuple(guardrail_stage_facts(stage) for stage in metadata.get("pipeline", []) if stage["type"] == "guardrail"),
        )
    except RuntimeError as exc:
        return _RouterEvidence(error=str(exc))


def _selected_endpoint(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """The router metadata's selected endpoint (documented shape: ``endpoints.available[]`` entries with
    ``provider``, ``model`` and ``selected``), or None when no entry is selected. More than one selected
    entry, or a malformed shape, is refused rather than guessed."""
    if metadata is None or "endpoints" not in metadata:
        return None
    endpoints = metadata["endpoints"]
    available = endpoints.get("available") if isinstance(endpoints, dict) else None
    if not isinstance(available, list) or not all(isinstance(entry, dict) for entry in available):
        raise RuntimeError("upstream response has malformed router metadata endpoints")
    if any(not isinstance(entry.get("selected", False), bool) for entry in available):
        raise RuntimeError("upstream response has malformed router metadata selection")
    chosen = [entry for entry in available if entry.get("selected") is True]
    if len(chosen) > 1:
        raise RuntimeError("upstream response has ambiguous router metadata selection")
    return chosen[0] if chosen else None


def _router_pipeline(metadata: dict[str, Any] | None) -> tuple[str, ...] | None:
    if metadata is None:
        return None
    stages = metadata.get("pipeline", [])
    if not isinstance(stages, list) or not all(isinstance(stage, dict) and isinstance(stage.get("type"), str) for stage in stages):
        raise RuntimeError("upstream response has malformed router metadata pipeline")
    return tuple(bounded(stage["type"], KNOWN_ROUTER_STAGES) or "unrecognized" for stage in stages)


def _required_nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeError(f"upstream response has invalid {field}")
    return value


def _optional_nonnegative_int(
    container: dict[str, Any] | None, field: str, description: str
) -> int | None:
    if container is None or field not in container:
        return None
    return _required_nonnegative_int(container[field], description)


def _provider_cost(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise RuntimeError("upstream response has invalid provider cost")
    try:
        cost = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RuntimeError("upstream response has invalid provider cost") from exc
    if not cost.is_finite() or cost < 0:
        raise RuntimeError("upstream response has invalid provider cost")
    return cost


def _optional_string(
    container: dict[str, Any] | None, field: str, description: str
) -> str | None:
    if container is None or field not in container:
        return None
    value = container[field]
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"upstream response has malformed {description}")
    return value


def _optional_header_nonnegative_int(headers: dict[str, str], name: str) -> int | None:
    value = headers.get(name)
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"upstream response has invalid {name}") from exc
    if parsed < 0:
        raise RuntimeError(f"upstream response has invalid {name}")
    return parsed
