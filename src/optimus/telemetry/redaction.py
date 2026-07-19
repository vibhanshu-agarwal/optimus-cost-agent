"""Telemetry redaction — compatibility wrapper over optimus_security.sanitization.

Plan 9.96, Task 4: redact_for_telemetry() is retained as a backward-compatible
wrapper that delegates to the shared sanitizer and returns .value directly.
The shared sanitizer is the single source of truth for sanitization rules
(Global Constraint 17).
"""

from __future__ import annotations

from typing import Any

from optimus_security.sanitization import sanitize_for_persistence


def redact_for_telemetry(value: Any) -> Any:
    """Recursively redacts sensitive information from the input value.

    This is the compatibility wrapper for existing callers. It delegates to
    optimus_security.sanitization.sanitize_for_persistence() and returns the
    sanitized .value directly (discarding rule_counts metadata).

    :param value: Input data which may contain sensitive information.
    :returns: The input data with sensitive information redacted.
    """
    result = sanitize_for_persistence(value, known_secrets=())
    return result.value
