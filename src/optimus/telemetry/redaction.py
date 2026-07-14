from __future__ import annotations

import re
from typing import Any

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES

_EXACT_SECRET_KEYS = {
    "authorization",
    "auth_header",
    "x-api-key",
}

_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "optimus_api_key",
)

_REDACT_ENV_KEY_NAMES = frozenset({*LOCAL_PROVIDER_KEY_NAMES, "OPTIMUS_API_KEY"})
_REDACT_ENV_KEY_NAMES_LOWER = frozenset(name.lower().replace("-", "_") for name in _REDACT_ENV_KEY_NAMES)
_ENV_ASSIGNMENT_PATTERN = re.compile(
    rf"\b({'|'.join(sorted(_REDACT_ENV_KEY_NAMES, key=len, reverse=True))})\s*=\s*\S+",
    re.IGNORECASE,
)
_API_KEY_HEADER_PATTERN = re.compile(r"(?i)(api[_-]?key)\s*:\s*\S+")
_X_API_KEY_HEADER_PATTERN = re.compile(r"(?i)x-api-key:\s*\S+")
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)(authorization:\s*bearer\s+|bearer\s+)[^\s]+")
_URL_USERINFO_PATTERN = re.compile(r"(?i)(https?://)[^/\s:@]+:[^@\s/]+@")
_GENERIC_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(token|password|secret|credential|api[_-]?key)((?:=|:)\s*)\S+"
)


def redact_for_telemetry(value: Any) -> Any:
    """
    Recursively redacts sensitive information from the input value to ensure it is safe for use in telemetry.

    Supports redaction of sensitive information in dictionaries, lists, tuples, and strings. The function identifies
    sensitive keys in dictionaries and masks them with a placeholder string. Strings are processed to redact sensitive
    content as free text. The input type and structure are preserved in the output.

    :param value: Input data which may contain sensitive information. Accepted input types include dictionaries, lists,
        tuples, strings, or any other data types.
    :returns: The input data with sensitive information redacted. The redacted output preserves the same structure and
        type as the input.
    """
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key).lower()
            if _is_secret_dict_key(key_text):
                redacted[key] = "**********"
            else:
                redacted[key] = redact_for_telemetry(child)
        return redacted
    if isinstance(value, (list, tuple)):
        return [redact_for_telemetry(child) for child in value]
    if isinstance(value, str):
        return _redact_free_text(value)
    return value


def _redact_free_text(text: str) -> str:
    redacted = _URL_USERINFO_PATTERN.sub(r"\1**********@", text)
    redacted = _BEARER_TOKEN_PATTERN.sub(r"\1**********", redacted)
    redacted = _ENV_ASSIGNMENT_PATTERN.sub(r"\1=**********", redacted)
    redacted = _GENERIC_SECRET_ASSIGNMENT_PATTERN.sub(r"\1\2**********", redacted)
    redacted = _API_KEY_HEADER_PATTERN.sub(r"\1: **********", redacted)
    redacted = _X_API_KEY_HEADER_PATTERN.sub("x-api-key: **********", redacted)
    return redacted


def _is_secret_dict_key(key_text: str) -> bool:
    if key_text in _EXACT_SECRET_KEYS:
        return True
    normalized = key_text.replace("-", "_")
    if normalized in _REDACT_ENV_KEY_NAMES_LOWER:
        return True
    if normalized in _SECRET_KEY_PARTS:
        return True
    segments = normalized.split("_")
    return any(segment in _SECRET_KEY_PARTS for segment in segments)
