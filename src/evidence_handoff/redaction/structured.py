"""Bounded JSON/NDJSON sanitization and ACP truncated-tail handling."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from optimus_security.sanitization import (
    EVIDENCE_REDACTION_POLICY,
    PathAliasRule,
    sanitize_for_persistence,
)

from .bounds import (
    MAX_ARTIFACT_BYTES,
    MAX_COLLECTION_MEMBERS,
    MAX_DECODED_STRING_BYTES,
    MAX_JSON_DEPTH,
    MAX_NDJSON_TAIL_BYTES,
)
from .models import Disposition
from .private_files import (
    PrivateFileError,
    cleanup_private_path,
    create_private_staging_file,
)

# Re-export for monkeypatchable bounds in unit tests.
__all__ = [
    "MAX_ARTIFACT_BYTES",
    "MAX_COLLECTION_MEMBERS",
    "MAX_DECODED_STRING_BYTES",
    "MAX_JSON_DEPTH",
    "MAX_NDJSON_TAIL_BYTES",
    "StructuredSanitizeResult",
    "is_valid_json_object_prefix",
    "sanitize_json_artifact",
    "sanitize_ndjson_artifact",
]


@dataclass(frozen=True)
class StructuredSanitizeResult:
    disposition: Disposition
    staging_path: Path | None
    rule_counts: Mapping[str, int]
    reason_code: str | None
    truncated_tail_dropped: bool
    dropped_tail_bytes: int | None
    byte_size: int | None


def _quarantine(
    reason: str,
    *,
    rule_counts: Mapping[str, int] | None = None,
) -> StructuredSanitizeResult:
    return StructuredSanitizeResult(
        disposition=Disposition.QUARANTINED,
        staging_path=None,
        rule_counts=dict(rule_counts or {}),
        reason_code=reason,
        truncated_tail_dropped=False,
        dropped_tail_bytes=None,
        byte_size=None,
    )


def _merge_counts(*maps: Mapping[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for mapping in maps:
        for key, value in mapping.items():
            out[key] = out.get(key, 0) + value
    return out


def _reject_json_constant(name: str) -> object:
    raise json.JSONDecodeError(f"constant {name} rejected", name, 0)


def _dump_deterministic(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _check_bounds(value: object) -> str | None:
    """Return a reason code if bounds are violated."""
    members = 0

    def walk(node: object, depth: int) -> str | None:
        nonlocal members
        if depth > MAX_JSON_DEPTH:
            return "json_nesting_too_deep"
        if isinstance(node, str):
            if len(node.encode("utf-8")) > MAX_DECODED_STRING_BYTES:
                return "json_string_too_large"
            return None
        if isinstance(node, dict):
            members += len(node)
            if members > MAX_COLLECTION_MEMBERS:
                return "json_collection_too_large"
            for child in node.values():
                reason = walk(child, depth + 1)
                if reason:
                    return reason
            return None
        if isinstance(node, list):
            members += len(node)
            if members > MAX_COLLECTION_MEMBERS:
                return "json_collection_too_large"
            for child in node:
                reason = walk(child, depth + 1)
                if reason:
                    return reason
            return None
        return None

    return walk(value, 1 if not isinstance(value, (dict, list)) else 0)


def _collect_string_paths(value: object, path: tuple[str, ...] = ()) -> dict[tuple[str, ...], list[str]]:
    found: dict[tuple[str, ...], list[str]] = {}
    if isinstance(value, str):
        found.setdefault(path, []).append(value)
        return found
    if isinstance(value, dict):
        for key, child in value.items():
            for child_path, strings in _collect_string_paths(child, (*path, str(key))).items():
                found.setdefault(child_path, []).extend(strings)
        return found
    if isinstance(value, list):
        for index, child in enumerate(value):
            for child_path, strings in _collect_string_paths(child, (*path, str(index))).items():
                found.setdefault(child_path, []).extend(strings)
    return found


def _joined_scan_hit(
    records: Sequence[object],
    *,
    known_secrets: Sequence[str],
    known_pii: Sequence[str],
    path_aliases: Sequence[PathAliasRule],
) -> tuple[bool, dict[str, int]]:
    by_path: dict[tuple[str, ...], list[str]] = {}
    counts: dict[str, int] = {}
    for record in records:
        for path, strings in _collect_string_paths(record).items():
            by_path.setdefault(path, []).extend(strings)
    for strings in by_path.values():
        joined = "".join(strings)
        for secret in known_secrets:
            if secret and secret in joined:
                return True, counts
        result = sanitize_for_persistence(
            joined,
            known_secrets=known_secrets,
            known_pii=known_pii,
            path_aliases=path_aliases,
            policy=EVIDENCE_REDACTION_POLICY,
        )
        counts = _merge_counts(counts, result.rule_counts)
        for secret in known_secrets:
            if secret and secret in str(result.value):
                return True, counts
    return False, counts


def _serialized_scan_hit(
    text: str,
    *,
    known_secrets: Sequence[str],
    known_pii: Sequence[str],
    path_aliases: Sequence[PathAliasRule],
) -> tuple[bool, dict[str, int]]:
    for secret in known_secrets:
        if secret and secret in text:
            return True, {}
    result = sanitize_for_persistence(
        text,
        known_secrets=known_secrets,
        known_pii=known_pii,
        path_aliases=path_aliases,
        policy=EVIDENCE_REDACTION_POLICY,
    )
    for secret in known_secrets:
        if secret and secret in str(result.value):
            return True, dict(result.rule_counts)
    return False, dict(result.rule_counts)


def _abort(handle: object | None, staging_path: Path | None) -> None:
    if handle is not None:
        close = getattr(handle, "close", None)
        if close is not None:
            try:
                close()
            except Exception:
                pass
    if staging_path is not None:
        try:
            cleanup_private_path(staging_path)
        except Exception:
            pass


def _write_staging(staging_root: Path, artifact_role: str, payload: bytes) -> tuple[Path, int]:
    handle = create_private_staging_file(staging_root=staging_root, artifact_role=artifact_role)
    try:
        os.write(handle.fileno(), payload)
        handle.flush()
        path = handle.path
        handle.close()
        return path, len(payload)
    except Exception:
        _abort(handle, handle.path)
        raise


def sanitize_json_artifact(
    *,
    source_path: Path,
    staging_root: Path,
    artifact_role: str,
    known_secrets: Sequence[str],
    known_pii: Sequence[str],
    path_aliases: Sequence[PathAliasRule],
) -> StructuredSanitizeResult:
    try:
        raw = source_path.read_bytes()
    except OSError:
        return _quarantine("json_source_unreadable")
    if len(raw) > MAX_ARTIFACT_BYTES:
        return _quarantine("input_too_large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return _quarantine("invalid_utf8")
    try:
        parsed = json.loads(text, parse_constant=_reject_json_constant)
    except json.JSONDecodeError:
        return _quarantine("json_parse_failed")
    bound = _check_bounds(parsed)
    if bound:
        return _quarantine(bound)
    sanitized = sanitize_for_persistence(
        parsed,
        known_secrets=known_secrets,
        known_pii=known_pii,
        path_aliases=path_aliases,
        policy=EVIDENCE_REDACTION_POLICY,
    )
    try:
        serialized = _dump_deterministic(sanitized.value)
    except (TypeError, ValueError):
        return _quarantine("json_serialize_failed", rule_counts=sanitized.rule_counts)
    hit, scan_counts = _serialized_scan_hit(
        serialized,
        known_secrets=known_secrets,
        known_pii=known_pii,
        path_aliases=path_aliases,
    )
    counts = _merge_counts(sanitized.rule_counts, scan_counts)
    if hit:
        return _quarantine("final_scan_hit", rule_counts=counts)
    path_hit, path_counts = _joined_scan_hit(
        [sanitized.value],
        known_secrets=known_secrets,
        known_pii=known_pii,
        path_aliases=path_aliases,
    )
    counts = _merge_counts(counts, path_counts)
    if path_hit:
        return _quarantine("final_scan_hit", rule_counts=counts)
    try:
        staging_path, byte_size = _write_staging(
            staging_root, artifact_role, serialized.encode("utf-8")
        )
    except PrivateFileError:
        return _quarantine("private_staging_failed", rule_counts=counts)
    return StructuredSanitizeResult(
        disposition=Disposition.PROMOTED,
        staging_path=staging_path,
        rule_counts=counts,
        reason_code=None,
        truncated_tail_dropped=False,
        dropped_tail_bytes=None,
        byte_size=byte_size,
    )


def sanitize_ndjson_artifact(
    *,
    source_path: Path,
    staging_root: Path,
    artifact_role: str,
    known_secrets: Sequence[str],
    known_pii: Sequence[str],
    path_aliases: Sequence[PathAliasRule],
    allow_acp_truncated_tail: bool = False,
) -> StructuredSanitizeResult:
    try:
        raw = source_path.read_bytes()
    except OSError:
        return _quarantine("ndjson_source_unreadable")
    if len(raw) > MAX_ARTIFACT_BYTES:
        return _quarantine("input_too_large")

    ends_with_newline = raw.endswith(b"\n")
    # Split physical lines without decoding yet so a UTF-8-broken tail can be isolated.
    if raw == b"":
        return _quarantine("ndjson_empty")
    parts = raw.split(b"\n")
    # If file ends with newline, final split piece is empty and not a record.
    if ends_with_newline:
        line_bytes = parts[:-1]
        tail_bytes = b""
    else:
        if len(parts) == 1:
            # Single incomplete line, no preceding records.
            line_bytes = []
            tail_bytes = parts[0]
        else:
            line_bytes = parts[:-1]
            tail_bytes = parts[-1]

    records: list[Any] = []
    counts: dict[str, int] = {}
    for line in line_bytes:
        if line == b"":
            continue  # ignore empty physical lines between records
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError:
            return _quarantine("invalid_utf8")
        try:
            parsed = json.loads(text, parse_constant=_reject_json_constant)
        except json.JSONDecodeError:
            return _quarantine("ndjson_record_malformed")
        bound = _check_bounds(parsed)
        if bound:
            return _quarantine(bound)
        sanitized = sanitize_for_persistence(
            parsed,
            known_secrets=known_secrets,
            known_pii=known_pii,
            path_aliases=path_aliases,
            policy=EVIDENCE_REDACTION_POLICY,
        )
        counts = _merge_counts(counts, sanitized.rule_counts)
        records.append(sanitized.value)

    truncated_tail_dropped = False
    dropped_tail_bytes: int | None = None

    if tail_bytes:
        if not allow_acp_truncated_tail:
            return _quarantine("ndjson_record_malformed", rule_counts=counts)
        if not records:
            return _quarantine("ndjson_record_malformed", rule_counts=counts)
        if ends_with_newline:
            return _quarantine("ndjson_record_malformed", rule_counts=counts)
        if len(tail_bytes) > MAX_NDJSON_TAIL_BYTES:
            return _quarantine("ndjson_tail_too_large", rule_counts=counts)
        try:
            tail_text = tail_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return _quarantine("invalid_utf8", rule_counts=counts)
        if not is_valid_json_object_prefix(tail_text):
            return _quarantine("json_prefix_invalid", rule_counts=counts)
        # In-memory scan for aggregate rule counts; never persist tail bytes/fields.
        tail_scan = sanitize_for_persistence(
            tail_text,
            known_secrets=known_secrets,
            known_pii=known_pii,
            path_aliases=path_aliases,
            policy=EVIDENCE_REDACTION_POLICY,
        )
        counts = _merge_counts(counts, tail_scan.rule_counts)
        truncated_tail_dropped = True
        dropped_tail_bytes = len(tail_bytes)
    elif not records:
        return _quarantine("ndjson_empty", rule_counts=counts)

    hit, path_counts = _joined_scan_hit(
        records,
        known_secrets=known_secrets,
        known_pii=known_pii,
        path_aliases=path_aliases,
    )
    counts = _merge_counts(counts, path_counts)
    if hit:
        return _quarantine("final_scan_hit", rule_counts=counts)

    lines = [_dump_deterministic(record) for record in records]
    serialized = "\n".join(lines) + ("\n" if lines else "")
    ser_hit, ser_counts = _serialized_scan_hit(
        serialized,
        known_secrets=known_secrets,
        known_pii=known_pii,
        path_aliases=path_aliases,
    )
    counts = _merge_counts(counts, ser_counts)
    if ser_hit:
        return _quarantine("final_scan_hit", rule_counts=counts)

    try:
        staging_path, byte_size = _write_staging(staging_root, artifact_role, serialized.encode("utf-8"))
    except PrivateFileError:
        return _quarantine("private_staging_failed", rule_counts=counts)

    return StructuredSanitizeResult(
        disposition=Disposition.PROMOTED,
        staging_path=staging_path,
        rule_counts=counts,
        reason_code=None,
        truncated_tail_dropped=truncated_tail_dropped,
        dropped_tail_bytes=dropped_tail_bytes,
        byte_size=byte_size,
    )


# --- Incremental non-executing JSON object-prefix validator ---


def is_valid_json_object_prefix(text: str) -> bool:
    """Return True iff text is a valid JSON object or a valid incomplete object prefix.

    Accepts only missing suffix token(s)/closing delimiter(s). Illegal tokens,
    invalid ordering, or trailing data after a complete value fail.
    """
    if not text or text[0] != "{":
        return False
    i = 0
    n = len(text)
    stack: list[str] = []
    expect = "value"  # value | comma_or_end | colon | key

    def skip_ws(pos: int) -> int:
        while pos < n and text[pos] in " \t\r\n":
            pos += 1
        return pos

    def parse_string(pos: int) -> int | None:
        if pos >= n or text[pos] != '"':
            return None
        pos += 1
        while pos < n:
            ch = text[pos]
            if ch == "\\":
                if pos + 1 >= n:
                    return n  # incomplete escape — valid prefix
                esc = text[pos + 1]
                if esc in '"\\/bfnrt':
                    pos += 2
                    continue
                if esc == "u":
                    if pos + 5 >= n:
                        return n
                    hexpart = text[pos + 2 : pos + 6]
                    if len(hexpart) < 4 or any(c not in "0123456789abcdefABCDEF" for c in hexpart):
                        return None
                    pos += 6
                    continue
                return None
            if ch == '"':
                return pos + 1
            if ord(ch) < 0x20:
                return None
            pos += 1
        return n  # incomplete string — valid prefix

    def parse_number(pos: int) -> int | None:
        """Consume a JSON number or a valid incomplete number prefix.

        Always scan character-by-character. A full-match regex with optional
        fraction/exponent groups would accept ``1`` from ``1.`` / ``1e`` and
        leave the dangling ``.``/``e`` for the next token, wrongly rejecting
        mid-number crash tails.
        """
        j = pos
        if j >= n:
            return None
        if text[j] == "-":
            j += 1
            if j >= n:
                return n  # incomplete: lone "-"
        if j >= n:
            return None
        if text[j] == "0":
            j += 1
            if j < n and text[j] in "0123456789":
                return None  # leading zero
        elif text[j] in "123456789":
            j += 1
            while j < n and text[j] in "0123456789":
                j += 1
        else:
            return None
        if j < n and text[j] == ".":
            j += 1
            if j >= n:
                return n  # incomplete: trailing "."
            if text[j] not in "0123456789":
                return None
            while j < n and text[j] in "0123456789":
                j += 1
        if j < n and text[j] in "eE":
            j += 1
            if j >= n:
                return n  # incomplete: trailing "e"/"E"
            if text[j] in "+-":
                j += 1
                if j >= n:
                    return n  # incomplete: trailing "e+" / "e-"
            if j >= n or text[j] not in "0123456789":
                return None
            while j < n and text[j] in "0123456789":
                j += 1
        return j if j > pos else None

    while True:
        i = skip_ws(i)
        if i >= n:
            # EOF: complete object is valid; incomplete containers/tokens are valid prefixes.
            if expect == "done" and not stack:
                return True
            return bool(stack) or expect in {"comma_or_end", "key", "colon", "value"}

        ch = text[i]

        if expect == "key":
            if ch == "}":
                if not stack or stack[-1] != "{":
                    return False
                stack.pop()
                i += 1
                expect = "comma_or_end" if stack else "done"
                continue
            str_end = parse_string(i)
            if str_end is None:
                return False
            if str_end >= n and text[i] == '"' and str_end == n:
                return True  # incomplete key string
            i = str_end
            if i >= n:
                return True
            expect = "colon"
            continue

        if expect == "colon":
            if ch != ":":
                return False
            i += 1
            expect = "value"
            continue

        if expect == "comma_or_end":
            if ch == ",":
                i += 1
                expect = "key" if stack and stack[-1] == "{" else "value"
                continue
            if ch == "}":
                if not stack or stack[-1] != "{":
                    return False
                stack.pop()
                i += 1
                expect = "comma_or_end" if stack else "done"
                continue
            if ch == "]":
                if not stack or stack[-1] != "[":
                    return False
                stack.pop()
                i += 1
                expect = "comma_or_end" if stack else "done"
                continue
            return False

        if expect == "done":
            return False  # trailing data

        # expect == "value"
        if ch == "{":
            stack.append("{")
            i += 1
            expect = "key"
            continue
        if ch == "[":
            stack.append("[")
            i += 1
            # empty array or value
            i2 = skip_ws(i)
            if i2 < n and text[i2] == "]":
                i = i2 + 1
                stack.pop()
                expect = "comma_or_end" if stack else "done"
                continue
            expect = "value"
            continue
        if ch == '"':
            str_end = parse_string(i)
            if str_end is None:
                return False
            i = str_end
            if i >= n:
                return True
            expect = "comma_or_end"
            continue
        if ch in "-0123456789":
            num_end = parse_number(i)
            if num_end is None:
                return False
            i = num_end
            if i >= n:
                return True
            expect = "comma_or_end"
            continue
        if text.startswith("true", i):
            i += 4
            expect = "comma_or_end"
            continue
        if text.startswith("false", i):
            i += 5
            expect = "comma_or_end"
            continue
        if text.startswith("null", i):
            i += 4
            expect = "comma_or_end"
            continue
        # Incomplete literals
        for lit in ("true", "false", "null"):
            if lit.startswith(text[i:]) and text[i:]:
                return True
        return False
