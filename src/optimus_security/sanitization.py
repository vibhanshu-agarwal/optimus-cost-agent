"""Shared structured/free-text sanitizer for diagnostic persistence.

Plan 9.96, Task 4: Implements structured/free-text redaction, exact
current-secret replacement, URI-userinfo masking, rule counts, and safe
unsupported-object type metadata. Never reads ambient environment.

The sanitizer accepts known secrets explicitly. All agent, Gateway, telemetry,
stderr, state, and transcript boundaries use this single implementation
(Global Constraint 17).
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse, urlunparse

# Maximum length of a secret that the sanitizer guarantees to catch in streaming
# mode. Secrets longer than this are rejected at launch time (Task 6).
MAX_SECRET_TEXT_CHARS = 65_536

_REDACTED = "**********"
_CORRELATION_TAG_DOMAIN = b"p996-correlation-tag-v1"

# Patterns for free-text redaction (independent of known secrets).
_BEARER_TOKEN_RE = re.compile(r"(?i)(authorization:\s*bearer\s+|bearer\s+)\S+")
_ENV_ASSIGNMENT_RE = re.compile(r"(?i)\b([A-Z_][A-Z0-9_]*(?:_KEY|_SECRET|_TOKEN|_PASSWORD))\s*=\s*\S+")
_GENERIC_SECRET_ASSIGNMENT_RE = re.compile(r"(?i)\b(token|password|secret|credential|api[_-]?key)((?:=|:)\s*)\S+")
_API_KEY_HEADER_RE = re.compile(r"(?i)(api[_-]?key)\s*:\s*\S+")
_X_API_KEY_HEADER_RE = re.compile(r"(?i)x-api-key:\s*\S+")
_URL_USERINFO_RE = re.compile(r"(?i)(\w+://)[^/\s:@]*:[^@\s/]+@")

# Dictionary keys that are always considered secret.
_EXACT_SECRET_KEYS = frozenset({
    "authorization",
    "auth_header",
    "x-api-key",
})

_SECRET_KEY_PARTS = frozenset({
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
})


@dataclass(frozen=True)
class SanitizationResult:
    """Result of sanitizing a value for persistence.

    value: the sanitized output (same structural type as input where possible).
    rule_counts: how many times each rule fired (content-free metadata).
    """

    value: object
    rule_counts: Mapping[str, int]


def sanitize_for_persistence(
    value: object,
    *,
    known_secrets: Sequence[str] = (),
) -> SanitizationResult:
    """Sanitize a value for safe persistence/export.

    Applies:
    1. Exact known-secret replacement (longest-first match).
    2. URI-userinfo masking.
    3. Bearer/header/assignment pattern redaction.
    4. Dictionary key-based redaction for secret-named fields.
    5. Safe type metadata for unsupported objects (no repr/str/user code).

    Never reads ambient environment. Known secrets are passed explicitly.

    Args:
        value: The value to sanitize. May be str, dict, list, tuple, or any object.
        known_secrets: Exact secret values to redact. Order doesn't matter;
            replacement uses longest-first matching internally.

    Returns:
        SanitizationResult with the sanitized value and rule counts.
    """
    counter = _RuleCounter()
    # Sort secrets longest-first for greedy replacement.
    sorted_secrets = sorted(
        (s for s in known_secrets if s),
        key=len,
        reverse=True,
    )
    sanitized = _sanitize_recursive(value, sorted_secrets=sorted_secrets, counter=counter)
    return SanitizationResult(value=sanitized, rule_counts=dict(counter.counts))


# --- Internal implementation ---


@dataclass
class _RuleCounter:
    """Mutable counter for tracking which sanitization rules fired."""

    counts: dict[str, int] = field(default_factory=dict)

    def inc(self, rule: str) -> None:
        self.counts[rule] = self.counts.get(rule, 0) + 1


def _sanitize_recursive(
    value: object,
    *,
    sorted_secrets: list[str],
    counter: _RuleCounter,
) -> object:
    """Recursively sanitize a value."""
    if isinstance(value, str):
        return _sanitize_text(value, sorted_secrets=sorted_secrets, counter=counter)

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            key_str = str(key)
            if _is_secret_dict_key(key_str):
                result[key_str] = _REDACTED
                counter.inc("dict_key_redaction")
            else:
                result[key_str] = _sanitize_recursive(child, sorted_secrets=sorted_secrets, counter=counter)
        return result

    if isinstance(value, (list, tuple)):
        return [_sanitize_recursive(item, sorted_secrets=sorted_secrets, counter=counter) for item in value]

    if isinstance(value, (int, float, bool, type(None))):
        return value

    # Decimal is a safe numeric type used for cost/budget values.
    import decimal

    if isinstance(value, decimal.Decimal):
        return value

    # Unsupported object: return safe type metadata without calling repr/str/
    # arbitrary serializers or user code (Global Constraint 18).
    counter.inc("unsupported_object_type_metadata")
    return f"<{type(value).__module__}.{type(value).__qualname__}>"


def _sanitize_text(
    text: str,
    *,
    sorted_secrets: list[str],
    counter: _RuleCounter,
) -> str:
    """Sanitize a free-text string."""
    result = text

    # 1. Exact known-secret replacement (longest-first).
    for secret in sorted_secrets:
        if secret in result:
            result = result.replace(secret, _REDACTED)
            counter.inc("exact_secret_replacement")

    # 2. URI-userinfo masking.
    if _URL_USERINFO_RE.search(result):
        result = _URL_USERINFO_RE.sub(r"\1" + _REDACTED + "@", result)
        counter.inc("uri_userinfo_masking")

    # 3. Bearer token.
    if _BEARER_TOKEN_RE.search(result):
        result = _BEARER_TOKEN_RE.sub(r"\1" + _REDACTED, result)
        counter.inc("bearer_token_redaction")

    # 4. Environment assignment patterns.
    if _ENV_ASSIGNMENT_RE.search(result):
        result = _ENV_ASSIGNMENT_RE.sub(r"\1=" + _REDACTED, result)
        counter.inc("env_assignment_redaction")

    # 5. Generic secret assignment.
    if _GENERIC_SECRET_ASSIGNMENT_RE.search(result):
        result = _GENERIC_SECRET_ASSIGNMENT_RE.sub(r"\1\2" + _REDACTED, result)
        counter.inc("generic_secret_redaction")

    # 6. API key headers.
    if _API_KEY_HEADER_RE.search(result):
        result = _API_KEY_HEADER_RE.sub(r"\1: " + _REDACTED, result)
        counter.inc("api_key_header_redaction")

    if _X_API_KEY_HEADER_RE.search(result):
        result = _X_API_KEY_HEADER_RE.sub("x-api-key: " + _REDACTED, result)
        counter.inc("x_api_key_header_redaction")

    return result


def _is_secret_dict_key(key: str) -> bool:
    """Check if a dictionary key name indicates a secret value."""
    lower = key.lower()
    if lower in _EXACT_SECRET_KEYS:
        return True
    normalized = lower.replace("-", "_")
    if normalized in _SECRET_KEY_PARTS:
        return True
    # Check if any segment or consecutive segment pair matches.
    segments = normalized.split("_")
    for segment in segments:
        if segment in _SECRET_KEY_PARTS:
            return True
    # Check consecutive pairs (e.g., "api_key" in "optimus_api_key").
    for i in range(len(segments) - 1):
        pair = f"{segments[i]}_{segments[i + 1]}"
        if pair in _SECRET_KEY_PARTS:
            return True
    return False


def validate_secret_length(secret: str, *, max_chars: int = MAX_SECRET_TEXT_CHARS) -> None:
    """Reject a secret longer than the streaming overlap guarantee supports.

    Plan 9.96, Task 6: MAX_SECRET_TEXT_CHARS is the correctness bound
    StreamingTextSanitizer's cross-chunk overlap buffer is sized against
    (Global Constraint 19: "overlap equal to the supported maximum secret
    length"). An uncapped secret would need an unbounded overlap buffer, so
    every secret that will ever be passed to the streaming sanitizer must be
    validated against this same cap before use. This function only checks
    the length; the launch-time site that calls it (rejecting an
    over-length configured secret before authorization) is a separate,
    later change.
    """
    if len(secret) > max_chars:
        raise ValueError(f"secret length {len(secret)} exceeds the maximum of {max_chars} characters")


class StreamingTextSanitizer:
    """Bounded-overlap streaming sanitizer for incrementally-arriving text.

    Plan 9.96, Task 6, Global Constraint 19: sanitizes text arriving in
    chunks (e.g. subprocess stdout/stderr) while guaranteeing that a known
    secret split across ANY chunk boundary -- including the worst case of a
    single character in one chunk and the remainder in the next -- is still
    caught before the sanitized text is released to the caller.

    Design: every incoming chunk is appended to an internal pending buffer,
    and only the portion of that buffer that is more than `overlap_chars`
    characters from the end is sanitized and released on each feed() call.
    The trailing `overlap_chars` characters are always held back, because a
    secret could still be completed by text that has not arrived yet.
    finalize() flushes the entire remaining buffer once no more input is
    coming.

    `overlap_chars` defaults to `MAX_SECRET_TEXT_CHARS - 1`: with one fewer
    than the longest possible secret held back at all times, no secret of
    length <= MAX_SECRET_TEXT_CHARS can ever be split such that ALL of it
    has already been released before feed() had a chance to see it whole
    (the earliest a full copy of a k-length secret can be forced past the
    held-back window is exactly when the window is k-1 characters, one
    short of the secret itself).
    """

    def __init__(
        self,
        *,
        known_secrets: Sequence[str] = (),
        max_secret_chars: int = MAX_SECRET_TEXT_CHARS,
    ) -> None:
        self._sorted_secrets = sorted((s for s in known_secrets if s), key=len, reverse=True)
        self.overlap_chars = max(0, max_secret_chars - 1)
        self._pending = ""
        self._counter = _RuleCounter()

    @property
    def rule_counts(self) -> Mapping[str, int]:
        return dict(self._counter.counts)

    def feed(self, chunk: str) -> str:
        """Feed the next chunk of arriving text. Returns the portion that is
        now safe to release (sanitized), holding back the trailing overlap
        window for the next feed() or finalize() call."""
        self._pending += chunk
        if len(self._pending) <= self.overlap_chars:
            return ""
        tentative_boundary = len(self._pending) - self.overlap_chars
        boundary = self._safe_release_boundary(tentative_boundary)
        if boundary <= 0:
            return ""
        to_release, self._pending = self._pending[:boundary], self._pending[boundary:]
        return _sanitize_text(to_release, sorted_secrets=self._sorted_secrets, counter=self._counter)

    def _safe_release_boundary(self, tentative_boundary: int) -> int:
        """Never cut a release boundary through the middle of a known-secret
        occurrence. A blind character-count boundary (the naive approach)
        can release a secret's prefix in one feed() call and its suffix in
        the next -- since each feed() call sanitizes only the text it
        releases, a split secret would never be seen whole by any single
        _sanitize_text call and would leak in plain text either side of the
        cut. Pull the boundary back to the start of the EARLIEST occurrence
        that straddles it, then repeat (an occurrence starting even earlier
        could itself straddle the new, pulled-back boundary) until no
        occurrence straddles the final boundary.
        """
        boundary = tentative_boundary
        changed = True
        while changed:
            changed = False
            for secret in self._sorted_secrets:
                start = 0
                while True:
                    idx = self._pending.find(secret, start)
                    if idx == -1:
                        break
                    end = idx + len(secret)
                    if idx < boundary < end:
                        boundary = idx
                        changed = True
                    start = idx + 1
        return boundary

    def finalize(self) -> str:
        """Flush and sanitize the entire remaining buffer. Call once, after
        the last feed() call, when no more input is coming."""
        remaining, self._pending = self._pending, ""
        if not remaining:
            return ""
        return _sanitize_text(remaining, sorted_secrets=self._sorted_secrets, counter=self._counter)


def session_correlation_tag(secret: str, *, field_name: str, session_key: bytes) -> str:
    """Compute a non-derivable, session-scoped correlation tag for a secret.

    Plan 9.96, Task 6: used at predeclared elevated-diagnostic comparison
    points so an operator can confirm "this is the same configured value I
    approved" without the secret itself ever being displayed or logged. The
    contract accepts this as a bounded "one-bit match oracle" only because
    it fires at REVIEWED comparison points, not on attacker-chosen input --
    this function itself has no opinion on call sites; it is a pure
    primitive.

    HMAC-SHA256 keyed by the per-process session_key, domain-separated by
    field_name so the same secret value used for two different settings
    never produces a linkable tag, truncated to 128 bits (32 hex chars).
    Without knowledge of session_key, two tags cannot be linked to the same
    underlying secret across sessions -- session_key is generated fresh in
    memory per launch (never persisted, never derived from the secret) so a
    new session's tags are cryptographically unlinkable to a prior
    session's tags for the same secret.
    """
    secret_bytes = secret.encode("utf-8")
    message = (
        _CORRELATION_TAG_DOMAIN
        + b"\x00"
        + field_name.encode("utf-8")
        + b"\x00"
        + len(secret_bytes).to_bytes(8, "big")
        + secret_bytes
    )
    digest = hmac.new(session_key, message, hashlib.sha256).digest()
    return digest[:16].hex()


def mask_uri_userinfo(uri: str) -> str:
    """Mask user information in a URI, preserving structure.

    Returns the URI with username:password replaced by **********.
    If no userinfo is present, returns the URI unchanged.
    """
    parsed = urlparse(uri)
    if not parsed.username and not parsed.password:
        return uri
    # Rebuild netloc without userinfo.
    host = parsed.hostname or ""
    port_suffix = f":{parsed.port}" if parsed.port else ""
    clean_netloc = f"{host}{port_suffix}"
    return urlunparse(parsed._replace(netloc=clean_netloc))
