"""Byte-offset NDJSON suffix extraction and ACP completion normalization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from evidence_handoff.collector.models import ClaimKind, EvidenceClaim

from .common import HostError

_COMPLETION_LOCATION = "server.py:process_request:exit"
_PROMPT_ENTRY_LOCATION = "spec.py:_handle_session_prompt:entry"


@dataclass(frozen=True, slots=True)
class FileIdentity:
    path: Path
    size_bytes: int
    mtime_ns: int
    file_id: tuple[int, int]


@dataclass(frozen=True, slots=True)
class NdjsonSnapshot:
    byte_offset: int
    identity: FileIdentity


def snapshot_source(path: Path) -> NdjsonSnapshot:
    absolute = path.resolve()
    if not absolute.exists():
        identity = FileIdentity(
            path=absolute,
            size_bytes=0,
            mtime_ns=0,
            file_id=(0, 0),
        )
        return NdjsonSnapshot(byte_offset=0, identity=identity)
    if not absolute.is_file():
        raise HostError("ndjson_not_file")
    stat = absolute.stat()
    identity = FileIdentity(
        path=absolute,
        size_bytes=stat.st_size,
        mtime_ns=getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
        file_id=(stat.st_dev, getattr(stat, "st_ino", 0)),
    )
    return NdjsonSnapshot(byte_offset=stat.st_size, identity=identity)


def read_ordered_suffix(path: Path, snapshot: NdjsonSnapshot) -> tuple[dict[str, Any], ...]:
    absolute = path.resolve()
    if absolute != snapshot.identity.path:
        raise HostError("ndjson_identity_changed")
    if not absolute.exists():
        if snapshot.byte_offset == 0:
            return ()
        raise HostError("ndjson_missing")
    stat = absolute.stat()
    current = FileIdentity(
        path=absolute,
        size_bytes=stat.st_size,
        mtime_ns=getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
        file_id=(stat.st_dev, getattr(stat, "st_ino", 0)),
    )
    if current.file_id != snapshot.identity.file_id and snapshot.identity.file_id != (0, 0):
        raise HostError("ndjson_identity_changed")
    if current.size_bytes < snapshot.byte_offset:
        raise HostError("ndjson_rotated")
    with absolute.open("rb") as handle:
        handle.seek(snapshot.byte_offset)
        encoded = handle.read()
    try:
        suffix = encoded.decode("utf-8")
    except UnicodeDecodeError:
        raise HostError("ndjson_not_utf8") from None
    if not suffix:
        return ()
    if not suffix.endswith("\n"):
        raise HostError("partial_ndjson_record")
    records: list[dict[str, Any]] = []
    for line in suffix.splitlines():
        if not line:
            raise HostError("malformed_ndjson_record")
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            raise HostError("malformed_ndjson_record") from None
        if not isinstance(payload, dict):
            raise HostError("malformed_ndjson_record")
        records.append(payload)
    return tuple(records)


def suffix_sha256(path: Path, snapshot: NdjsonSnapshot) -> str:
    absolute = path.resolve()
    if not absolute.is_file():
        if snapshot.byte_offset == 0:
            return hashlib.sha256(b"").hexdigest()
        raise HostError("ndjson_missing")
    with absolute.open("rb") as handle:
        handle.seek(snapshot.byte_offset)
        encoded = handle.read()
    return hashlib.sha256(encoded).hexdigest()


def discover_unique_completion(
    records: Sequence[Mapping[str, Any]],
) -> tuple[str, str, str, str]:
    """Return session_id, request_id, run_id, debug_session_id for a sole pair.

    Fail closed when the suffix contains more than one distinct
    (session_id, request_id, run_id) combination — never pick the latest
    foreign pair by timestamp (self-referential correlation).
    """
    prompt_entries = [
        record for record in records if record.get("location") == _PROMPT_ENTRY_LOCATION
    ]
    exits = [record for record in records if record.get("location") == _COMPLETION_LOCATION]
    if not prompt_entries or not exits:
        raise HostError("completion_missing")

    combinations: set[tuple[str, str, str]] = set()
    for prompt in prompt_entries:
        data = _data(prompt)
        session_id = data.get("session_id")
        request_id = data.get("request_id")
        run_id = data.get("run_id")
        if not isinstance(session_id, str) or not session_id:
            raise HostError("completion_correlation_missing")
        if request_id is None or run_id is None:
            raise HostError("completion_correlation_missing")
        combinations.add((session_id, str(request_id), str(run_id)))
    if len(combinations) != 1:
        raise HostError("completion_ambiguous")

    session_id, request_id, run_id = next(iter(combinations))
    matched_prompts = [
        record
        for record in prompt_entries
        if _data(record).get("session_id") == session_id
        and str(_data(record).get("request_id")) == request_id
        and str(_data(record).get("run_id")) == run_id
    ]
    if len(matched_prompts) != 1:
        raise HostError("completion_ambiguous")
    prompt = matched_prompts[0]
    debug_session_id = prompt.get("sessionId")
    if not isinstance(debug_session_id, str) or not debug_session_id:
        raise HostError("completion_correlation_missing")
    matched_exits = [
        record for record in exits if str(_data(record).get("request_id")) == request_id
    ]
    if not matched_exits:
        raise HostError("completion_missing")
    if len(matched_exits) != 1:
        raise HostError("completion_ambiguous")
    return session_id, request_id, run_id, debug_session_id


def normalize_completion(
    records: Sequence[Mapping[str, Any]],
    *,
    correlate_session_id: str,
    correlate_request_id: str,
    correlate_run_id: str,
    expected_debug_session_id: str,
    scenario_id: str = "zed-session",
    run_id: str = "run",
    evidence_sha256: tuple[str, ...] = (),
) -> EvidenceClaim:
    for record in records:
        session = record.get("sessionId")
        if session is not None and session != expected_debug_session_id:
            raise HostError("foreign_ndjson_suffix")

    prompt_entries = [
        record
        for record in records
        if record.get("location") == _PROMPT_ENTRY_LOCATION
    ]
    exits = [
        record
        for record in records
        if record.get("location") == _COMPLETION_LOCATION
    ]
    matched_prompts = [
        record
        for record in prompt_entries
        if _data(record).get("session_id") == correlate_session_id
        and str(_data(record).get("request_id")) == correlate_request_id
        and _data(record).get("run_id") == correlate_run_id
    ]
    matched_exits = [
        record
        for record in exits
        if str(_data(record).get("request_id")) == correlate_request_id
    ]
    if not matched_prompts:
        raise HostError("completion_correlation_missing")
    if len(matched_prompts) != 1:
        raise HostError("completion_ambiguous")
    if not matched_exits:
        raise HostError("completion_missing")
    if len(matched_exits) != 1:
        raise HostError("completion_ambiguous")
    exit_event = matched_exits[0]
    data = _data(exit_event)
    if data.get("has_error") is True:
        raise HostError("completion_has_error")
    prompt_ts = int(matched_prompts[0].get("timestamp") or 0)
    exit_ts = int(exit_event.get("timestamp") or 0)
    if exit_ts < prompt_ts:
        raise HostError("completion_ordering")
    starts = int(exit_event.get("timestamp") or 0) * 1_000_000
    return EvidenceClaim(
        claim_kind=ClaimKind.COMPLETION_OBSERVED,
        scenario_id=scenario_id,
        run_id=run_id,
        detector_id="completion_detector",
        contract_version="v1",
        evidence_sha256=evidence_sha256,
        starts_at_ns=starts,
        ends_at_ns=starts,
        reason_code="ok",
    )


def _data(record: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = record.get("data")
    return payload if isinstance(payload, Mapping) else {}
