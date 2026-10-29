"""What a planning step did, what came back and whether it was new (Plan 12.3, Design 1).

A step is an action fingerprint (its kind plus a normalised target) and a result digest (the
outcome's identity). Novelty is new evidence or a changed result: returned bytes not yet seen with that
file content, a file whose hash changed since its last read, an MCP result not seen before in this
turn, or one that changed since the same call's last result. A parse failure is never novel.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum


class ActionKind(StrEnum):
    READ = "READ"
    MCP = "MCP"
    PARSE_FAILURE = "PARSE_FAILURE"


@dataclass(frozen=True)
class LoopStep:
    """One planning step as the detector sees it. `subject` and `error_message` are for the model's
    nudge and the user's text only, never telemetry: they may name paths or tools."""

    kind: ActionKind
    fingerprint: str
    result_digest: str
    novel: bool
    subject: str
    error_class: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ReadResult:
    path: str
    start_byte: int
    end_byte: int
    source_sha256: str
    returned_end_byte: int  # where the returned bytes end; a range past the end of the file returns fewer (#432)


class ReadCoverage:
    """The byte ranges already read in this turn, per path and file content."""

    def __init__(self) -> None:
        self._spans: dict[tuple[str, str], list[tuple[int, int]]] = {}
        self._last_sha: dict[str, str] = {}

    def add(self, read: ReadResult) -> bool:
        """Record `read`; True if the file's hash changed since its last read, or if any byte it
        returned was not covered by an earlier read of the same content. A read that returned nothing
        (past the end of the file) is new only as the path's first read or after a change."""
        first_seen = read.path not in self._last_sha
        changed = self._last_sha.setdefault(read.path, read.source_sha256) != read.source_sha256
        self._last_sha[read.path] = read.source_sha256
        spans = self._spans.setdefault((read.path, read.source_sha256), [])
        start, end = read.start_byte, read.returned_end_byte
        if end <= start:
            return first_seen or changed
        novel = changed or not _covers(spans, start, end)
        spans.append((start, end))
        spans.sort()
        merged: list[tuple[int, int]] = []
        for start, end in spans:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        spans[:] = merged
        return novel


def _covers(merged: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(span_start <= start and end <= span_end for span_start, span_end in merged)


def read_step(reads: Iterable[ReadResult], coverage: ReadCoverage) -> LoopStep:
    ordered = sorted(reads, key=lambda read: (read.path, read.start_byte, read.end_byte))
    identities = [f"{read.path}#bytes={read.start_byte}:{read.end_byte}" for read in ordered]
    novel = False
    for read in ordered:
        novel = coverage.add(read) or novel
    return LoopStep(
        kind=ActionKind.READ,
        fingerprint="READ:" + "|".join(identities),
        result_digest="|".join(read.source_sha256 for read in ordered),
        novel=novel,
        subject="the read of " + ", ".join(identities),
    )


class McpResults:
    """The MCP results seen in this turn, and each call's last one."""

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._last: dict[str, str] = {}

    def add(self, fingerprint: str, digest: str) -> bool:
        """Record a result; True if it is new evidence or changed since the same call's last result."""
        changed = self._last.setdefault(fingerprint, digest) != digest
        novel = changed or digest not in self._seen
        self._seen.add(digest)
        self._last[fingerprint] = digest
        return novel


def mcp_step(
    *,
    operation: str,
    server: str,
    tool: str,
    arguments: Mapping[str, object],
    evidence_envelope: str,
    results: McpResults,
) -> LoopStep:
    """`evidence_envelope` is exactly what the planner receives; main returns no separate result digest."""
    canonical = json.dumps(dict(arguments), sort_keys=True, separators=(",", ":"), default=str)
    argument_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    digest = hashlib.sha256(evidence_envelope.encode("utf-8")).hexdigest()
    fingerprint = f"MCP:{operation}:{server}:{tool}:{argument_hash}"
    return LoopStep(
        kind=ActionKind.MCP,
        fingerprint=fingerprint,
        result_digest=digest,
        novel=results.add(fingerprint, digest),
        subject=f"the MCP call {server}.{tool}" if operation == "call" else f"the MCP tool list of {server}",
    )


def parse_failure_step(*, code: str, message: str) -> LoopStep:
    return LoopStep(
        kind=ActionKind.PARSE_FAILURE,
        fingerprint=f"PARSE:{code}",
        result_digest=code,
        novel=False,
        subject="a reply that did not match the directive grammar",
        error_class=code,
        error_message=message,
    )
