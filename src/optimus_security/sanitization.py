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

import bisect
import hashlib
import hmac
import math
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult, urlsplit

# Maximum length of a secret that the sanitizer guarantees to catch in streaming
# mode. Secrets longer than this are rejected at launch time.
MAX_SECRET_TEXT_CHARS = 65_536
# Longest single rule match a stream release may hold back past its tentative cut before the stream is refused.
MAX_STREAM_HOLD_CHARS = 4 * MAX_SECRET_TEXT_CHARS
# Characters on each side of a candidate release cut that must sanitize the same together as apart.
_CUT_CHECK_CHARS = 8192
# Candidate cuts tried per release, each further back, before nothing is released this time.
_CUT_ATTEMPTS = 12

_REDACTED = "**********"
REDACTION_MASK = _REDACTED  # what every redaction leaves in place of what it removed
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
# The fewest closed-class English words prose puts after a keyword (#584): each one exempted is a one-word value that
# could leave in clear, so the list holds only articles, common prepositions and conjunctions, plain copulas and
# auxiliaries, and negation (no names, pronouns, determiners, modals or forms such as "being" or "been").
_PROSE_FUNCTION_WORDS = (
    "a an the of in on at to for from with by into via as than under over and or nor but if when while "
    "is are was were has have had does did not never only also"
).split()
# Group 2 keeps an optional copula and/or separator ("token is X", "token = X", "token is: X") so the mask lands on the
# value (#505). Groups 3 and 4 record a "=" or ":" separator. Only with none ("token X", "token is X") may the value be
# exempt, and only as a lowercase function word followed directly by whitespace, so "token was not made" keeps "not"
# while "password = not", "password Per" and a word cut at a stream boundary stay masked.
_WHITESPACE_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(token|password|secret|credential|api[_-]?key)(\s+(?:(?:is|was)(?:\s*([=:]))?\s+|([=:])\s+)?)"
    r"(?(3)|(?(4)|(?!(?-i:" + "|".join(_PROSE_FUNCTION_WORDS) + r")\s)))\S+"
)
_API_KEY_HEADER_RE = re.compile(r"(?i)(api[_-]?key)\s*:\s*\S+")
_X_API_KEY_HEADER_RE = re.compile(r"(?i)x-api-key:\s*\S+")
# The leading \b keeps a long word run linear: without it every position in the run retries the scheme (#622).
_URL_USERINFO_RE = re.compile(r"(?i)\b(\w+://)[^/\s:@]*:[^@\s/]+@")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# Each local-part run that ends at an "@", found from its start only: searching _EMAIL_RE directly retries every word
# boundary of a dotted run with no "@", which is quadratic in the run (#622, one-shot artifacts).
_EMAIL_LOCAL_RUN_RE = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]++(?=@)")
_WORD_BOUNDARY_RE = re.compile(r"\b")
_TOKEN_CANDIDATE_RE = re.compile(r"[A-Za-z0-9._+:/-]{24,256}")
_PREFIX_RES = tuple(
    re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(prefix)}[A-Za-z0-9_-]{{{_PREFIX_SUFFIX_MIN},{_PREFIX_SUFFIX_MAX}}}(?![A-Za-z0-9_-])")
    for prefix in _RECOGNIZED_PREFIXES
)

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

# v2 (#505): the whitespace assignment rule masks the value after a copula. v3 (#584): it no longer masks a function
# word after the keyword ("the token was not made"). v4 (#622): a stream release never cuts a label from its value,
# and a stream with one match past the hold-back limit is refused. Manifests recorded as v1 to v3 stay valid.
EVIDENCE_REDACTION_POLICY = SanitizationPolicy(
    version="evidence-redaction-v4",
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
# Its own identity since #505 changed that rule's output; before it, this policy reported compatibility-v1. v3: #584.
WORKSPACE_SUBJECT_SANITIZATION_POLICY = replace(
    COMPATIBILITY_SANITIZATION_POLICY,
    version="workspace-subject-v3",
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
    entropy_exempt: frozenset[str] = frozenset(),
) -> SanitizationResult:
    """Sanitize a value for safe persistence/export.

    Applies the active policy's rule set. Default policy is compatibility-only.

    Never reads ambient environment. Known secrets/PII are passed explicitly.

    `entropy_exempt`: whole tokens the caller has shown are not secrets (memory: a workspace file's name, #525). Only the
    entropy rule skips them, and only while every earlier rule has left them as they were; all other rules apply as usual.
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
        entropy_exempt=entropy_exempt,
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
    entropy_exempt: frozenset[str] = frozenset(),
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
            entropy_exempt=entropy_exempt,
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
                    entropy_exempt=entropy_exempt,
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
                entropy_exempt=entropy_exempt,
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
    entropy_exempt: frozenset[str] = frozenset(),
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

    if policy.enable_email_masking:
        masked = _mask_emails(result)
        if masked is not None:
            result = masked
            counter.inc("email_masking")

    protected = _protected_spans(result) if policy.enable_contextual_preservation else _NO_PROTECTED

    if policy.enable_prefix_detection:
        result = _apply_prefix_redaction(result, protected=protected, counter=counter)

    if policy.enable_entropy_detection:
        # Recompute protected spans after prefix edits so indices stay aligned.
        protected = _protected_spans(result) if policy.enable_contextual_preservation else _NO_PROTECTED
        result = _apply_entropy_redaction(result, protected=protected, counter=counter, exempt=entropy_exempt)

    return result


def _mask_emails(text: str) -> str | None:
    """``_EMAIL_RE.sub(_REDACTED, text)`` in linear time, or None when nothing matches.

    A match's local part is the run of local-part characters before its "@" (the class has no "@"), taken from the
    run's first word boundary, and the rest of the match does not depend on where in the run it starts. So each "@"
    needs one anchored match from that boundary, and no other start in the run can match.
    """
    pieces: list[str] = []
    pos = 0
    for run in _EMAIL_LOCAL_RUN_RE.finditer(text):
        start, at = max(run.start(), pos), run.end()
        if start >= at:
            continue
        boundary = _WORD_BOUNDARY_RE.search(text, start, at)
        if boundary is None or boundary.start() >= at:
            continue
        match = _EMAIL_RE.match(text, boundary.start())
        if match is None:
            continue
        pieces += (text[pos : match.start()], _REDACTED)
        pos = match.end()
    if not pieces:
        return None
    pieces.append(text[pos:])
    return "".join(pieces)


def _apply_path_aliases(text: str, path_aliases: list[PathAliasRule], counter: _RuleCounter) -> str:
    if not path_aliases:
        return text
    # Slash-normalize for matching; Windows may case-fold, POSIX must not.
    normalized = text.replace("\\", "/")
    result = normalized
    for rule in path_aliases:
        pattern = _path_alias_pattern(rule)
        if pattern is None:
            continue
        replaced, count = pattern.subn(rule.alias, result)
        if count:
            result = replaced
            counter.inc("path_alias_replacement")
    return result


def _path_alias_pattern(rule: PathAliasRule) -> re.Pattern[str] | None:
    """Match a path alias root in slash-normalized text; ``None`` for an empty root."""
    root = rule.source_root.replace("\\", "/").rstrip("/")
    if not root:
        return None
    # Segment boundaries: reject mid-token suffix matches such as
    # ``backup<rooted-path>/file``, while allowing whitespace/start prefixes.
    return re.compile(
        rf'(?<![A-Za-z0-9_]){re.escape(root)}(?=[/\\"\']|\s|$)',
        re.IGNORECASE if sys.platform == "win32" else 0,
    )


# Protected value spans as (sorted starts, running maximum of their ends): a token lies inside some span exactly when
# the largest end among spans starting at or before it reaches its end. One bisect per token, so one pass over a whole
# artifact stays linear in the number of tokens and spans (#622 round 3).
_Protected = tuple[tuple[int, ...], tuple[int, ...]]
_NO_PROTECTED: _Protected = ((), ())


def _protected_spans(text: str) -> _Protected:
    spans: list[tuple[int, int]] = []
    for labels, value_pat in _PRESERVE_LABELS:
        patterns = (
            re.compile(rf'(?i)"(?:{labels})"\s*:\s*"({value_pat})"'),
            re.compile(rf"(?i)\b(?:{labels})=({value_pat})\b"),
            re.compile(rf"(?i)\b(?:{labels}):\s*({value_pat})\b"),
            re.compile(rf'(?i)(?:{labels})":\s*String\("({value_pat})"\)'),
        )
        for pattern in patterns:
            spans.extend((match.start(1), match.end(1)) for match in pattern.finditer(text))
    spans.sort()
    max_ends: list[int] = []
    for _, p_end in spans:
        max_ends.append(max(p_end, max_ends[-1]) if max_ends else p_end)
    return tuple(p_start for p_start, _ in spans), tuple(max_ends)


def _span_protected(start: int, end: int, protected: _Protected) -> bool:
    starts, max_ends = protected
    i = bisect.bisect_right(starts, start)
    return i > 0 and max_ends[i - 1] >= end


def _apply_prefix_redaction(
    text: str,
    *,
    protected: _Protected,
    counter: _RuleCounter,
) -> str:
    matches: list[tuple[int, int]] = []
    for pattern in _PREFIX_RES:
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
    protected: _Protected,
    counter: _RuleCounter,
    exempt: frozenset[str] = frozenset(),
) -> str:
    matches: list[tuple[int, int]] = []
    for match in _TOKEN_CANDIDATE_RE.finditer(text):
        token = match.group(0)
        if token in exempt or not _is_entropy_candidate(token):
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


class StreamHoldBackExceededError(ValueError):
    """A release would cut through a rule match held back over ``max_hold_chars``; the stream must be refused."""


class StreamingTextSanitizer:
    """Bounded-overlap streaming sanitizer for incrementally-arriving text.

    A release cut changes no output: the streamed text equals one-shot sanitization, so a label leaves with its
    value (#622). A match held back past ``max_hold_chars`` refuses the stream instead of splitting it.
    """

    def __init__(
        self,
        *,
        known_secrets: Sequence[str] = (),
        known_pii: Sequence[str] = (),
        path_aliases: Sequence[PathAliasRule] = (),
        policy: SanitizationPolicy = COMPATIBILITY_SANITIZATION_POLICY,
        max_secret_chars: int = MAX_SECRET_TEXT_CHARS,
        max_hold_chars: int = MAX_STREAM_HOLD_CHARS,
    ) -> None:
        self._sorted_secrets = sorted((s for s in known_secrets if s), key=len, reverse=True)
        self._sorted_pii = sorted((s for s in known_pii if s), key=len, reverse=True)
        self._path_aliases = _normalize_path_aliases(path_aliases)
        self._policy = policy
        self.overlap_chars = max(0, max_secret_chars - 1)
        self.max_hold_chars = max_hold_chars
        self._pending = ""
        self._counter = _RuleCounter()
        self._exact_needles = tuple((needle, _smallest_period(needle)) for needle in self._sorted_secrets + self._sorted_pii)
        self._normalizes_slashes = policy.enable_path_aliases and bool(self._path_aliases)
        # Long matches the local cut check cannot see whole: each rule with a stand-in for the text still to come.
        # A label (or a URI's user part) running to the end of the buffer then matches through it and waits.
        probes: list[tuple[re.Pattern[str], str]] = []
        if policy.enable_uri_userinfo:
            probes.append((_URL_USERINFO_RE, ":x@"))
        if policy.enable_bearer_header_assignment:
            probes += [
                (_BEARER_TOKEN_RE, "x"),
                (_ENV_ASSIGNMENT_RE, "x"),
                (_GENERIC_SECRET_ASSIGNMENT_RE, "x"),
                (_API_KEY_HEADER_RE, "x"),
                (_X_API_KEY_HEADER_RE, "x"),
            ]
        if policy.enable_whitespace_secret_assignment:
            probes.append((_WHITESPACE_SECRET_ASSIGNMENT_RE, "x"))
        # Email is left to the local cut check: no real address outlasts it, a probe would hold every long
        # alphanumeric run (a hex dump), and the rule is slow on dotted runs.
        if policy.enable_prefix_detection:
            probes += [(pattern, "") for pattern in _PREFIX_RES]
        if policy.enable_entropy_detection:
            probes.append((_TOKEN_CANDIDATE_RE, ""))
        self._probes = tuple(probes)
        self._alias_patterns = (
            tuple(p for p in map(_path_alias_pattern, self._path_aliases) if p is not None) if policy.enable_path_aliases else ()
        )

    @property
    def rule_counts(self) -> Mapping[str, int]:
        return dict(self._counter.counts)

    def feed(self, chunk: str) -> str:
        self._pending += chunk
        if len(self._pending) <= self.overlap_chars:
            return ""
        tentative_boundary = len(self._pending) - self.overlap_chars
        boundary = self._safe_release_boundary(tentative_boundary)
        if tentative_boundary - boundary > self.max_hold_chars:
            # A match (or chain of overlapping matches) past the cap: releasing part of it could expose its value,
            # and holding it is unbounded, so the stream is refused.
            raise StreamHoldBackExceededError("a rule match exceeds the streaming hold-back limit")
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
        """The latest cut at or before the tentative one that changes no output, or 0 (#622).

        A cut must lie outside every long match, and the text on either side of it must sanitize the same
        together as apart. The local check covers what one-shot rule order does: a replaced secret creating a
        word boundary, an alias normalizing backslashes into a URI, an earlier mask exposing a later label, and
        the left context a rule's word boundary needs.
        """
        spans = sorted(self._long_match_spans(), reverse=True)
        candidate = tentative_boundary
        step = 64
        for _ in range(_CUT_ATTEMPTS):
            boundary = _cut_outside(spans, self._after_whitespace(candidate))
            if boundary <= 0:
                return 0
            if self._cut_is_inert(boundary):
                return boundary
            candidate = boundary - step
            step *= 2
        return 0

    def _after_whitespace(self, boundary: int) -> int:
        """The nearest cut at or before ``boundary`` that follows whitespace, within a short scan; else ``boundary``."""
        pending = self._pending
        for cut in range(boundary, max(0, boundary - _CUT_CHECK_CHARS // 8), -1):
            if pending[cut - 1].isspace():
                return cut
        return boundary

    def _long_match_spans(self) -> list[tuple[int, int]]:
        pending = self._pending
        spans: list[tuple[int, int]] = []
        for needle, period in self._exact_needles:
            spans.extend(run for run in _occurrence_runs(pending, needle, period) if run[1] - run[0] > 1)
        # The alias rule slash-normalizes the whole text before the pattern rules run (same length).
        text = pending.replace("\\", "/") if self._normalizes_slashes else pending
        for pattern, probe in self._probes:
            spans.extend(match.span() for match in pattern.finditer(text + probe))
        for pattern in self._alias_patterns:
            spans.extend(match.span() for match in pattern.finditer(text))
        return spans

    def _cut_is_inert(self, boundary: int) -> bool:
        left = self._pending[max(0, boundary - _CUT_CHECK_CHARS) : boundary]
        right = self._pending[boundary : boundary + _CUT_CHECK_CHARS]
        return self._trial_sanitize(left + right) == self._trial_sanitize(left) + self._trial_sanitize(right)

    def _trial_sanitize(self, text: str) -> str:
        """Sanitize without counting: a trial for the cut check, not output."""
        return _sanitize_text(
            text,
            sorted_secrets=self._sorted_secrets,
            sorted_pii=self._sorted_pii,
            path_aliases=self._path_aliases,
            policy=self._policy,
            counter=_RuleCounter(),
        )

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


def _smallest_period(needle: str) -> int:
    """The least p > 0 with needle[i] == needle[i + p] wherever both exist (KMP failure function)."""
    fail = [0] * len(needle)
    k = 0
    for i in range(1, len(needle)):
        while k and needle[i] != needle[k]:
            k = fail[k - 1]
        if needle[i] == needle[k]:
            k += 1
        fail[i] = k
    return len(needle) - (fail[-1] if needle else 0)


def _occurrence_runs(text: str, needle: str, period: int) -> list[tuple[int, int]]:
    """The union of ``needle``'s occurrences in ``text`` as maximal runs of overlapping ones, in linear time.

    Searching again from each occurrence plus one compares the whole needle at every overlap, quadratic for a
    self-overlapping needle (#622 review). Within a run, the next occurrence that overlaps the last one is one period on
    while the text keeps repeating, an O(period) check. Once that stops, an overlapping occurrence can only start in the
    last period of the run (Fine and Wilf), so the next search starts there.
    """
    size = len(needle)
    tail = needle[size - period :]
    runs: list[tuple[int, int]] = []
    idx = text.find(needle)
    while idx != -1:
        start, end = idx, idx + size
        while True:
            while period < size and text.startswith(tail, end):
                end += period
            idx = text.find(needle, end - period + 1)
            if idx == -1 or idx >= end:
                break
            end = idx + size
        runs.append((start, end))
    return runs


def _cut_outside(spans: Sequence[tuple[int, int]], boundary: int) -> int:
    """Move ``boundary`` back to the start of any span that strictly contains it; ``spans`` latest start first."""
    # Once the cut moves to a span's start, no span already visited can contain it.
    for start, end in spans:
        if start < boundary < end:
            boundary = start
    return max(0, boundary)


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


class CredentialUriError(ValueError):
    """A credential-bearing URI that cannot be shown or hashed safely. Its message never contains the value (#671)."""


_CREDENTIAL_URI_SCHEMES = frozenset({"http", "https", "redis", "rediss"})


def _split_credential_uri(stripped: str) -> SplitResult | None:
    """The parts of an absolute URI whose netloc sits verbatim right after ``scheme://``, else None.

    It returns None rather than raising inside the parser's except block, so no urllib.parse exception (whose text
    carries the netloc, password included) is kept in any exception chain.
    """
    # A control, format or separator character: urllib.parse drops some (a tab) before parsing, so a slice of the
    # original text would no longer match the parsed netloc and its password would survive the redaction.
    if any(unicodedata.category(char)[0] in "CZ" for char in stripped):
        return None
    try:
        parts = urlsplit(stripped)
        host, _port = parts.hostname, parts.port
    except ValueError:  # an NFKC-delimiter netloc, a bad port or a bad IPv6 literal
        return None
    start = len(parts.scheme) + 3
    if (
        parts.scheme not in _CREDENTIAL_URI_SCHEMES
        or not host
        or stripped[len(parts.scheme) : start] != "://"
        or stripped[start : start + len(parts.netloc)] != parts.netloc
    ):
        return None
    return parts


def canonicalize_credential_uri(uri: str) -> CredentialUriCanonicalization:
    """Canonicalize a credential-bearing URI using original-text slicing.

    The normalized URI (a digest input) is the original text with only the userinfo cut out, as before #671, so an
    approval of a valid value keeps its digest. The display is built from the validated parts with the userinfo, the
    query and the fragment redacted. A value that is not an absolute http, https, redis or rediss URI with a host
    raises CredentialUriError, whose message never contains the value. An empty value stays empty.
    """
    stripped = uri.strip()
    if not stripped:
        return CredentialUriCanonicalization(normalized_uri="", display_uri="", userinfo_present=False)
    parts = _split_credential_uri(stripped)
    if parts is None:
        raise CredentialUriError(
            "not an absolute http, https, redis or rediss URL with a host and without spaces or control characters"
        )
    userinfo_present = parts.username is not None or parts.password is not None
    start = len(parts.scheme) + 3
    hostport = parts.netloc.rpartition("@")[2]
    display = (
        stripped[:start]
        + (f"{_REDACTED}@" if userinfo_present else "")
        + hostport
        + parts.path
        + (f"?{_REDACTED}" if parts.query else "")
        + (f"#{_REDACTED}" if parts.fragment else "")
    )
    return CredentialUriCanonicalization(
        normalized_uri=stripped[:start] + hostport + stripped[start + len(parts.netloc) :],
        display_uri=display,
        userinfo_present=userinfo_present,
    )


def mask_uri_userinfo(uri: str) -> str:
    """Mask user information in a URI, preserving structure."""
    return canonicalize_credential_uri(uri).display_uri
