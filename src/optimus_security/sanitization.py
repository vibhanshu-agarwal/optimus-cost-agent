"""Shared structured/free-text sanitizer for diagnostic persistence.

Implements structured/free-text redaction, exact current-secret replacement,
URI-userinfo masking, rule counts, and safe unsupported-object type metadata.
Never reads ambient environment.

The sanitizer accepts known secrets explicitly. All agent, Gateway, telemetry,
stderr, state, and transcript boundaries use this single implementation.
Evidence callers opt into EVIDENCE_REDACTION_POLICY explicitly; the default
COMPATIBILITY_SANITIZATION_POLICY preserves pre-existing caller behavior.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Maximum length of a secret that the sanitizer guarantees to catch in streaming
# mode. Secrets longer than this are rejected at launch time.
MAX_SECRET_TEXT_CHARS = 65_536

_REDACTED = "**********"
_CORRELATION_TAG_DOMAIN = b"p996-correlation-tag-v1"

# Entropy / prefix candidates (evidence-redaction-v1 provisional until Task 1 freeze).
_ENTROPY_MIN_LEN = 24
_ENTROPY_MAX_LEN = 256
_ENTROPY_MIN_CLASSES = 2
_ENTROPY_MIN_BITS = 4.0
_PREFIX_SUFFIX_MIN = 16
_PREFIX_SUFFIX_MAX = 240

# Longest-first recognized prefixes.
_RECOGNIZED_PREFIXES: tuple[str, ...] = (
    "sk-or-v1-",
    "sk-ant-",
    "sk-proj-",
    "github_pat_",
    "sk-",
    "tvly-",
    "AIza",
    "ghp_",
)

# Patterns for free-text redaction (independent of known secrets).
_BEARER_TOKEN_RE = re.compile(r"(?i)(authorization:\s*bearer\s+|bearer\s+)\S+")
_ENV_ASSIGNMENT_RE = re.compile(r"(?i)\b([A-Z_][A-Z0-9_]*(?:_KEY|_SECRET|_TOKEN|_PASSWORD))\s*=\s*\S+")
_GENERIC_SECRET_ASSIGNMENT_RE = re.compile(r"(?i)\b(token|password|secret|credential|api[_-]?key)((?:=|:)\s*)\S+")
_WHITESPACE_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(token|password|secret|credential|api[_-]?key)(\s+)\S+"
)
_API_KEY_HEADER_RE = re.compile(r"(?i)(api[_-]?key)\s*:\s*\S+")
_X_API_KEY_HEADER_RE = re.compile(r"(?i)x-api-key:\s*\S+")
_URL_USERINFO_RE = re.compile(r"(?i)(\w+://)[^/\s:@]*:[^@\s/]+@")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_TOKEN_CANDIDATE_RE = re.compile(r"[A-Za-z0-9._+:/-]{24,256}")

_ID_VALUE = r"[A-Za-z0-9._:-]{1,128}"
_MODEL_VALUE = r"[A-Za-z0-9._:+/-]{1,128}"
_GIT_SHA_VALUE = r"[0-9a-fA-F]{7,64}"
_ARTIFACT_SHA_VALUE = r"[0-9a-fA-F]{64}"

_PRESERVE_LABELS: tuple[tuple[str, str], ...] = (
    ("session_id|sessionId", _ID_VALUE),
    ("run_id|runId", _ID_VALUE),
    ("gateway_request_id|gatewayRequestId", _ID_VALUE),
    ("model", _MODEL_VALUE),
    ("provider", _MODEL_VALUE),
    ("git_sha|gitSha", _GIT_SHA_VALUE),
    ("artifact_sha256|sha256", _ARTIFACT_SHA_VALUE),
)

_STRUCTURED_PRESERVE_KEYS = frozenset(
    {
        "session_id",
        "sessionid",
        "run_id",
        "runid",
        "gateway_request_id",
        "gatewayrequestid",
        "model",
        "provider",
        "git_sha",
        "gitsha",
        "artifact_sha256",
        "sha256",
    }
)

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
class PathAliasRule:
    """Trusted resolved root mapped to a content-free persisted alias."""

    source_root: str
    alias: str


@dataclass(frozen=True)
class SanitizationPolicy:
    """Immutable per-call sanitization rule activation contract."""

    version: str
    enable_exact_secrets: bool = True
    enable_uri_userinfo: bool = True
    enable_bearer_header_assignment: bool = True
    enable_secret_dict_keys: bool = True
    enable_whitespace_secret_assignment: bool = False
    enable_prefix_detection: bool = False
    enable_entropy_detection: bool = False
    enable_email_masking: bool = False
    enable_known_pii: bool = False
    enable_path_aliases: bool = False
    enable_contextual_preservation: bool = False


COMPATIBILITY_SANITIZATION_POLICY = SanitizationPolicy(version="compatibility-v1")

EVIDENCE_REDACTION_POLICY = SanitizationPolicy(
    version="evidence-redaction-v1",
    enable_whitespace_secret_assignment=True,
    enable_prefix_detection=True,
    enable_entropy_detection=True,
    enable_email_masking=True,
    enable_known_pii=True,
    enable_path_aliases=True,
    enable_contextual_preservation=True,
)

# Workspace subjects enable the shared whitespace assignment rule without
# changing the default compatibility contract used by redact_for_telemetry.
WORKSPACE_SUBJECT_SANITIZATION_POLICY = replace(
    COMPATIBILITY_SANITIZATION_POLICY,
    enable_whitespace_secret_assignment=True,
)


@dataclass(frozen=True)
class SanitizationResult:
    """Result of sanitizing a value for persistence.

    value: the sanitized output (same structural type as input where possible).
    rule_counts: how many times each rule fired (content-free metadata).
    """

    value: object
    rule_counts: Mapping[str, int]


def shannon_entropy(token: str) -> float:
    """Shannon entropy in bits per character over the token's observed alphabet."""
    if not token:
        return 0.0
    length = len(token)
    counts = Counter(token)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def character_class_count(token: str) -> int:
    """Count how many of lowercase/uppercase/digit/symbol classes appear."""
    return sum(
        [
            any(ch.islower() for ch in token),
            any(ch.isupper() for ch in token),
            any(ch.isdigit() for ch in token),
            any(not ch.isalnum() for ch in token),
        ]
    )


def is_git_sha_shape(value: str) -> bool:
    return bool(re.fullmatch(_GIT_SHA_VALUE, value))


def is_artifact_sha256_shape(value: str) -> bool:
    return bool(re.fullmatch(_ARTIFACT_SHA_VALUE, value))


def is_correlation_id_shape(value: str) -> bool:
    return bool(re.fullmatch(_ID_VALUE, value))


def is_model_or_provider_shape(value: str) -> bool:
    return bool(re.fullmatch(_MODEL_VALUE, value))


def sanitize_for_persistence(
    value: object,
    *,
    known_secrets: Sequence[str] = (),
    known_pii: Sequence[str] = (),
    path_aliases: Sequence[PathAliasRule] = (),
    policy: SanitizationPolicy = COMPATIBILITY_SANITIZATION_POLICY,
) -> SanitizationResult:
    """Sanitize a value for safe persistence/export.

    Applies the active policy's rule set. Default policy is compatibility-only.

    Never reads ambient environment. Known secrets/PII are passed explicitly.
    """
    counter = _RuleCounter()
    sorted_secrets = sorted((s for s in known_secrets if s), key=len, reverse=True)
    sorted_pii = sorted((s for s in known_pii if s), key=len, reverse=True)
    normalized_aliases = _normalize_path_aliases(path_aliases)
    sanitized = _sanitize_recursive(
        value,
        sorted_secrets=sorted_secrets,
        sorted_pii=sorted_pii,
        path_aliases=normalized_aliases,
        policy=policy,
        counter=counter,
    )
    return SanitizationResult(value=sanitized, rule_counts=dict(counter.counts))


# --- Internal implementation ---


@dataclass
class _RuleCounter:
    """Mutable counter for tracking which sanitization rules fired."""

    counts: dict[str, int] = field(default_factory=dict)

    def inc(self, rule: str) -> None:
        self.counts[rule] = self.counts.get(rule, 0) + 1


def _normalize_path_aliases(path_aliases: Sequence[PathAliasRule]) -> list[PathAliasRule]:
    normalized: list[PathAliasRule] = []
    for rule in path_aliases:
        root = Path(rule.source_root).expanduser().resolve().as_posix().rstrip("/")
        if not root:
            continue
        normalized.append(PathAliasRule(source_root=root, alias=rule.alias))
    normalized.sort(key=lambda item: len(item.source_root), reverse=True)
    return normalized


def _sanitize_recursive(
    value: object,
    *,
    sorted_secrets: list[str],
    sorted_pii: list[str],
    path_aliases: list[PathAliasRule],
    policy: SanitizationPolicy,
    counter: _RuleCounter,
) -> object:
    """Recursively sanitize a value."""
    if isinstance(value, str):
        return _sanitize_text(
            value,
            sorted_secrets=sorted_secrets,
            sorted_pii=sorted_pii,
            path_aliases=path_aliases,
            policy=policy,
            counter=counter,
        )

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            key_str = str(key)
            if (
                policy.enable_secret_dict_keys
                and _is_secret_dict_key(key_str)
                and not _is_structured_preserve_key(key_str, child, policy)
            ):
                result[key_str] = _REDACTED
                counter.inc("dict_key_redaction")
            elif _is_structured_preserve_key(key_str, child, policy):
                result[key_str] = child
            else:
                result[key_str] = _sanitize_recursive(
                    child,
                    sorted_secrets=sorted_secrets,
                    sorted_pii=sorted_pii,
                    path_aliases=path_aliases,
                    policy=policy,
                    counter=counter,
                )
        return result

    if isinstance(value, (list, tuple)):
        return [
            _sanitize_recursive(
                item,
                sorted_secrets=sorted_secrets,
                sorted_pii=sorted_pii,
                path_aliases=path_aliases,
                policy=policy,
                counter=counter,
            )
            for item in value
        ]

    if isinstance(value, (int, float, bool, type(None))):
        return value

    import decimal

    if isinstance(value, decimal.Decimal):
        return value

    counter.inc("unsupported_object_type_metadata")
    return f"<{type(value).__module__}.{type(value).__qualname__}>"


def _is_structured_preserve_key(key: str, value: object, policy: SanitizationPolicy) -> bool:
    if not policy.enable_contextual_preservation:
        return False
    if not isinstance(value, str):
        return False
    normalized = key.lower().replace("-", "")
    if normalized not in _STRUCTURED_PRESERVE_KEYS:
        return False
    if normalized in {"git_sha", "gitsha"}:
        return is_git_sha_shape(value)
    if normalized in {"artifact_sha256", "sha256"}:
        return is_artifact_sha256_shape(value)
    if normalized in {"model", "provider"}:
        return is_model_or_provider_shape(value)
    return is_correlation_id_shape(value)


def _sanitize_text(
    text: str,
    *,
    sorted_secrets: list[str],
    sorted_pii: list[str],
    path_aliases: list[PathAliasRule],
    policy: SanitizationPolicy,
    counter: _RuleCounter,
) -> str:
    """Sanitize a free-text string under the active policy."""
    result = text

    if policy.enable_exact_secrets:
        for secret in sorted_secrets:
            if secret in result:
                result = result.replace(secret, _REDACTED)
                counter.inc("exact_secret_replacement")

    if policy.enable_known_pii:
        for pii in sorted_pii:
            if pii in result:
                result = result.replace(pii, _REDACTED)
                counter.inc("known_pii_replacement")

    if policy.enable_path_aliases:
        result = _apply_path_aliases(result, path_aliases, counter)

    if policy.enable_uri_userinfo and _URL_USERINFO_RE.search(result):
        result = _URL_USERINFO_RE.sub(r"\1" + _REDACTED + "@", result)
        counter.inc("uri_userinfo_masking")

    if policy.enable_bearer_header_assignment:
        if _BEARER_TOKEN_RE.search(result):
            result = _BEARER_TOKEN_RE.sub(r"\1" + _REDACTED, result)
            counter.inc("bearer_token_redaction")

        if _ENV_ASSIGNMENT_RE.search(result):
            result = _ENV_ASSIGNMENT_RE.sub(r"\1=" + _REDACTED, result)
            counter.inc("env_assignment_redaction")

        if _GENERIC_SECRET_ASSIGNMENT_RE.search(result):
            result = _GENERIC_SECRET_ASSIGNMENT_RE.sub(r"\1\2" + _REDACTED, result)
            counter.inc("generic_secret_redaction")

        if _API_KEY_HEADER_RE.search(result):
            result = _API_KEY_HEADER_RE.sub(r"\1: " + _REDACTED, result)
            counter.inc("api_key_header_redaction")

        if _X_API_KEY_HEADER_RE.search(result):
            result = _X_API_KEY_HEADER_RE.sub("x-api-key: " + _REDACTED, result)
            counter.inc("x_api_key_header_redaction")

    if policy.enable_whitespace_secret_assignment and _WHITESPACE_SECRET_ASSIGNMENT_RE.search(result):
        result = _WHITESPACE_SECRET_ASSIGNMENT_RE.sub(r"\1\2" + _REDACTED, result)
        counter.inc("whitespace_secret_assignment")

    if policy.enable_email_masking and _EMAIL_RE.search(result):
        result = _EMAIL_RE.sub(_REDACTED, result)
        counter.inc("email_masking")

    protected = _protected_spans(result) if policy.enable_contextual_preservation else ()

    if policy.enable_prefix_detection:
        result = _apply_prefix_redaction(result, protected=protected, counter=counter)

    if policy.enable_entropy_detection:
        # Recompute protected spans after prefix edits so indices stay aligned.
        protected = _protected_spans(result) if policy.enable_contextual_preservation else ()
        result = _apply_entropy_redaction(result, protected=protected, counter=counter)

    return result


def _apply_path_aliases(text: str, path_aliases: list[PathAliasRule], counter: _RuleCounter) -> str:
    if not path_aliases:
        return text
    # Work on a slash-normalized copy for matching, then rewrite matches.
    normalized = text.replace("\\", "/")
    result = normalized
    for rule in path_aliases:
        root = rule.source_root
        # Match root at a path-segment boundary.
        pattern = re.compile(
            re.escape(root) + r'(?=/|$|\s|["\'])',
            re.IGNORECASE,
        )
        if pattern.search(result):
            result = pattern.sub(rule.alias, result)
            counter.inc("path_alias_replacement")
    return result


def _protected_spans(text: str) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    for labels, value_pat in _PRESERVE_LABELS:
        patterns = (
            re.compile(rf'(?i)"(?:{labels})"\s*:\s*"({value_pat})"'),
            re.compile(rf"(?i)\b(?:{labels})=({value_pat})\b"),
            re.compile(rf"(?i)\b(?:{labels}):\s*({value_pat})\b"),
            re.compile(rf'(?i)(?:{labels})":\s*String\("({value_pat})"\)'),
        )
        for pattern in patterns:
            for match in pattern.finditer(text):
                spans.append((match.start(1), match.end(1)))
    spans.sort()
    return tuple(spans)


def _span_protected(start: int, end: int, protected: Sequence[tuple[int, int]]) -> bool:
    return any(start >= p_start and end <= p_end for p_start, p_end in protected)


def _apply_prefix_redaction(
    text: str,
    *,
    protected: Sequence[tuple[int, int]],
    counter: _RuleCounter,
) -> str:
    matches: list[tuple[int, int]] = []
    for prefix in _RECOGNIZED_PREFIXES:
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_-]){re.escape(prefix)}[A-Za-z0-9_-]{{{_PREFIX_SUFFIX_MIN},{_PREFIX_SUFFIX_MAX}}}(?![A-Za-z0-9_-])"
        )
        for match in pattern.finditer(text):
            if _span_protected(match.start(), match.end(), protected):
                continue
            matches.append((match.start(), match.end()))
    return _replace_spans(text, matches, counter, rule="prefix_redaction")


def _is_entropy_candidate(token: str) -> bool:
    if not (_ENTROPY_MIN_LEN <= len(token) <= _ENTROPY_MAX_LEN):
        return False
    if character_class_count(token) < _ENTROPY_MIN_CLASSES:
        return False
    return shannon_entropy(token) >= _ENTROPY_MIN_BITS


def _apply_entropy_redaction(
    text: str,
    *,
    protected: Sequence[tuple[int, int]],
    counter: _RuleCounter,
) -> str:
    matches: list[tuple[int, int]] = []
    for match in _TOKEN_CANDIDATE_RE.finditer(text):
        token = match.group(0)
        if not _is_entropy_candidate(token):
            continue
        if _span_protected(match.start(), match.end(), protected):
            continue
        matches.append((match.start(), match.end()))
    return _replace_spans(text, matches, counter, rule="entropy_redaction")


def _replace_spans(
    text: str,
    spans: Sequence[tuple[int, int]],
    counter: _RuleCounter,
    *,
    rule: str,
) -> str:
    if not spans:
        return text
    # Drop overlaps, keep earliest longest-ish by sorting start then -length.
    ordered = sorted(spans, key=lambda item: (item[0], -(item[1] - item[0])))
    selected: list[tuple[int, int]] = []
    last_end = -1
    for start, end in ordered:
        if start < last_end:
            continue
        selected.append((start, end))
        last_end = end
    parts: list[str] = []
    cursor = 0
    for start, end in selected:
        parts.append(text[cursor:start])
        parts.append(_REDACTED)
        counter.inc(rule)
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def _is_secret_dict_key(key: str) -> bool:
    """Check if a dictionary key name indicates a secret value."""
    lower = key.lower()
    if lower in _EXACT_SECRET_KEYS:
        return True
    normalized = lower.replace("-", "_")
    if normalized in _SECRET_KEY_PARTS:
        return True
    segments = normalized.split("_")
    for segment in segments:
        if segment in _SECRET_KEY_PARTS:
            return True
    for i in range(len(segments) - 1):
        pair = f"{segments[i]}_{segments[i + 1]}"
        if pair in _SECRET_KEY_PARTS:
            return True
    return False


def validate_secret_length(secret: str, *, max_chars: int = MAX_SECRET_TEXT_CHARS) -> None:
    """Reject a secret longer than the streaming overlap guarantee supports."""
    if len(secret) > max_chars:
        raise ValueError(f"secret length {len(secret)} exceeds the maximum of {max_chars} characters")


class StreamingTextSanitizer:
    """Bounded-overlap streaming sanitizer for incrementally-arriving text."""

    def __init__(
        self,
        *,
        known_secrets: Sequence[str] = (),
        known_pii: Sequence[str] = (),
        path_aliases: Sequence[PathAliasRule] = (),
        policy: SanitizationPolicy = COMPATIBILITY_SANITIZATION_POLICY,
        max_secret_chars: int = MAX_SECRET_TEXT_CHARS,
    ) -> None:
        self._sorted_secrets = sorted((s for s in known_secrets if s), key=len, reverse=True)
        self._sorted_pii = sorted((s for s in known_pii if s), key=len, reverse=True)
        self._path_aliases = _normalize_path_aliases(path_aliases)
        self._policy = policy
        self.overlap_chars = max(0, max_secret_chars - 1)
        self._pending = ""
        self._counter = _RuleCounter()

    @property
    def rule_counts(self) -> Mapping[str, int]:
        return dict(self._counter.counts)

    def feed(self, chunk: str) -> str:
        self._pending += chunk
        if len(self._pending) <= self.overlap_chars:
            return ""
        tentative_boundary = len(self._pending) - self.overlap_chars
        boundary = self._safe_release_boundary(tentative_boundary)
        if boundary <= 0:
            return ""
        to_release, self._pending = self._pending[:boundary], self._pending[boundary:]
        return _sanitize_text(
            to_release,
            sorted_secrets=self._sorted_secrets,
            sorted_pii=self._sorted_pii,
            path_aliases=self._path_aliases,
            policy=self._policy,
            counter=self._counter,
        )

    def _safe_release_boundary(self, tentative_boundary: int) -> int:
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
        remaining, self._pending = self._pending, ""
        if not remaining:
            return ""
        return _sanitize_text(
            remaining,
            sorted_secrets=self._sorted_secrets,
            sorted_pii=self._sorted_pii,
            path_aliases=self._path_aliases,
            policy=self._policy,
            counter=self._counter,
        )


def session_correlation_tag(secret: str, *, field_name: str, session_key: bytes) -> str:
    """Compute a non-derivable, session-scoped correlation tag for a secret."""
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


@dataclass(frozen=True)
class CredentialUriCanonicalization:
    """Original-text credential URI canonicalization for security snapshots."""

    normalized_uri: str
    display_uri: str
    userinfo_present: bool


def canonicalize_credential_uri(uri: str) -> CredentialUriCanonicalization:
    """Canonicalize a credential-bearing URI using original-text slicing."""
    stripped = uri.strip()
    parsed = urlparse(stripped)
    userinfo_present = parsed.username is not None or parsed.password is not None

    if not userinfo_present:
        return CredentialUriCanonicalization(
            normalized_uri=stripped,
            display_uri=stripped,
            userinfo_present=False,
        )

    _, _, hostport = parsed.netloc.rpartition("@")
    normalized_netloc = hostport
    display_netloc = f"{_REDACTED}@{hostport}"

    netloc_index = stripped.find(parsed.netloc)
    prefix = stripped[:netloc_index]
    suffix = stripped[netloc_index + len(parsed.netloc) :]

    return CredentialUriCanonicalization(
        normalized_uri=prefix + normalized_netloc + suffix,
        display_uri=prefix + display_netloc + suffix,
        userinfo_present=True,
    )


def mask_uri_userinfo(uri: str) -> str:
    """Mask user information in a URI, preserving structure."""
    return canonicalize_credential_uri(uri).display_uri
