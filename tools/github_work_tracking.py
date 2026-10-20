"""Plan 11.29: move open work from the consolidated backlog to GitHub Issues without losing any of it.

The migration is driven by a reviewed inventory (``reports/github-work-tracking-migration.json``). This module reads the
authority documents the inventory was built from and checks the inventory against them. The check fails closed:

* every record-like *unit* of a source is found: a ``###`` entry, an identity-bearing table row, a ``##`` section that
  carries its own ``**Status:**`` line, a frozen-artifact live-owner bullet; anything the parser cannot read with
  certainty (a loose status line, a second status line in one record, a partly struck row, an unbalanced code fence) is
  reported, never skipped;
* a unit is resolved only when its status starts with a known resolved token (``RESOLVED_STATUSES``); an unknown status is
  treated as unresolved work, and a row with no status column needs a record or a reviewed section declaration;
* every unit is claimed by exactly one record, except resolved and declared-statusless units in a section classified as
  history/excluded/not-work; a unit whose status is ``Reviewed disposition`` always needs a record;
* every ``##`` section of every source has exactly one classification;
* a record that merges several identities, merges conflicting source statuses, or is marked a duplicate states why;
* a plan and an item are never merged into one record, because their acceptance surfaces differ;
* unresolved work is never retired without an explicit terminal disposition, and an accepted risk with outstanding
  mitigation is never excluded; parents form no cycle and never hang an open item under a retired record;
* a record's status is the text one of its claimed units states; only a status no unit states may be synthesized, with a
  known token and a status disposition; a migrating record's priority is its source value, or ``MEDIUM`` unless a
  priority disposition explains another value; each migrating record targets its own positive issue number;
* a frozen artifact's mapping links every live owner it names that has a record.

Unit keys are ``<source>:<line>`` against the exact source bytes, whose git blob ids the inventory pins. The reviewed
drafting rules that produce the inventory live in ``tools.github_work_tracking_rules``; ``draft`` reproduces the
committed inventory from its baseline commit.

Status here is a migration expectation, not a registry. A ``--scope`` file narrows ``plan``, ``publish``, ``reconcile`` and
``finalize`` to the records whose authority moves, without relaxing any check on them. After final acceptance the GitHub
issues own current status: neither the baseline status, a record's ``status_current`` evidence nor a rerun of ``plan`` or
``publish`` authorizes resetting what a later, legitimate edit of an issue says.
"""

from __future__ import annotations

import argparse
import copy
import functools
import hashlib
import json
import math
import os
import posixpath
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

SCHEMA = "optimus-work-tracking-migration-v1"

SECTION_CLASSIFICATIONS = frozenset({"migrated", "mixed", "history", "excluded", "not-work"})
DISPOSITIONS = frozenset({"migrate", "duplicate", "history", "excluded", "not-work"})
RETIRING_DISPOSITIONS = frozenset({"history", "excluded", "not-work"})
RECORD_KINDS = frozenset(
    {"plan", "feature", "follow-up", "obligation", "candidate", "track", "item", "risk", "frozen-mapping", "external-issue", "structure"}
)
PRODUCTS = frozenset({"optimus", "evidence-a2a"})
PLAN_UNIT_SECTIONS = frozenset({"Live implementation plan registry", "Child-plan status board"})
# Open work is also recorded as an `ACCEPTED_OPEN` or `UNRUN` disposition in tables that carry no status column.
UNRESOLVED_STATUSES = frozenset(
    {
        "open",
        "partially implemented",
        "promoted",
        "blocked",
        "active",
        "not drafted",
        "in review",
        "ready",
        "accepted_open",
        "unrun_binding",
        "unrun",
    }
)
RESOLVED_STATUSES = frozenset({"closed", "retired", "reviewed disposition", "complete", "completed", "implemented", "resolved", "merged"})
REVIEWED_DISPOSITION = "reviewed disposition"
# The `priority:*` label vocabulary; a migrating record without a source priority takes the operator's default.
PRIORITIES = frozenset({"HIGH", "MEDIUM", "LOW"})
DEFAULT_PRIORITY = "MEDIUM"

# The status token must be the first text of the status (the pool's own rule); `\b` keeps "Openly" or "Unblocked" out.
_STATUS_TOKEN = re.compile(
    r"(?P<token>accepted_open|unrun_binding|unrun|partially implemented|reviewed disposition|not drafted|in review|promoted"
    r"|blocked|active|ready|open|closed|retired|completed|complete|implemented|resolved|merged)\b",
    re.IGNORECASE,
)
_ID_TAIL = r"[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?"
_IDENTITY = re.compile(
    rf"(?P<id>P\d+(?:\.\d+)*-(?:FU|FEAT|REMEDIATION|UNRUN|CAND)-{_ID_TAIL}|P11\.26-{_ID_TAIL}|MAIN-\d+"
    rf"|EVIDENCE-HANDOFF-{_ID_TAIL}|HARDENING-{_ID_TAIL}|T13-CAND-{_ID_TAIL}|Plan \d+(?:\.\d+)*)"
)
# A2A audit obligations are numbered `C1`…`M17`; such a code names a row only as its whole first cell, since other tables
# cite findings like "C15 precision" in passing.
_SHORT_OBLIGATION = re.compile(r"[CHM]\d+[a-z]?")
_STATUS_LINE = re.compile(r"^\*\*Status:\*\*\s*(?P<value>\S.*)$")
# "Status:", "**Status (2026-10-04)**:", "Current status:", "Status for pickup:"; not prose like "Status ownership follows ...:".
_LOOSE_STATUS_LINE = re.compile(
    r"(?i)^\s*(?:[-*+]\s+)?(?:\*\*|__)?\s*(?:current\s+)?status(?:\s+[\w-]+){0,2}\s*(?:\([^)]*\))?\s*(?:\*\*|__)?\s*:"
)
_FENCE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})")
_HEADING = re.compile(r"^(?P<marks>#{1,6}) (?P<title>.+?)\s*#*\s*$")
_DELIMITER_ROW = re.compile(r"^\s{0,3}\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$")
_FROZEN_BULLET = re.compile(r"^- `(?P<path>docs/superpowers/[^`]+)` — SHA-256 ")


def git_blob_id(data: bytes) -> str:
    """Git's object id for ``data`` as a blob, so a pin can be checked with ``git rev-parse <rev>:<path>``."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def normalized_status(text: str | None) -> str | None:
    """The leading status token (``Promoted -> [Plan 12.1](…)`` -> ``promoted``), or ``None`` when there is none."""
    if not text:
        return None
    match = _STATUS_TOKEN.match(re.sub(r"[`~*]", "", text).strip())
    return match.group("token").lower() if match else None


def status_token(text: str | None) -> str:
    """The leading status token as the source writes it (``Promoted -> [Plan 12.1](…)`` -> ``Promoted``)."""
    cleaned = re.sub(r"[`~*]", "", text or "").strip()
    match = _STATUS_TOKEN.match(cleaned)
    return match.group("token") if match else cleaned


def owner_identities(text: str | None) -> list[str]:
    """Every identity a frozen artifact's live-owner text names, in order and without repeats (anchors are lower case)."""
    found: list[str] = []
    for match in _IDENTITY.finditer(_clean(text)):
        if match.group("id") not in found:
            found.append(match.group("id"))
    return found


def heading_anchor(title: str) -> str:
    """GitHub's anchor for a Markdown heading (formatting and punctuation dropped, spaces to hyphens)."""
    text = re.sub(r"`|\*\*|\*|\[|\]\([^)]*\)", "", title).strip().lower()
    return "".join(ch for ch in text if ch.isalnum() or ch in " -_").replace(" ", "-")


@dataclass(frozen=True)
class SourceUnit:
    source: str
    section: str
    kind: str  # "entry" | "row" | "section-record" | "frozen-mapping"
    line: int
    end: int
    identity: str | None
    title: str
    stated_status: str | None
    has_status_field: bool = True
    struck: bool = False
    status_struck: bool = False
    severity: str | None = None
    priority: str | None = None
    cells: Mapping[str, str] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.line}"

    @property
    def status_class(self) -> str:
        """``unresolved``, ``resolved``, ``statusless``, ``unknown`` or ``mapping``; unknown counts as unresolved work."""
        if self.kind == "frozen-mapping":
            return "mapping"
        if self.struck:
            return "resolved" if self.status_struck or not (self.stated_status or "").strip() else "unknown"
        if not self.has_status_field:
            return "statusless"
        token = normalized_status(self.stated_status)
        if token in RESOLVED_STATUSES:
            return "resolved"
        if token in UNRESOLVED_STATUSES:
            return "unresolved"
        return "unknown"

    @property
    def unresolved(self) -> bool:
        return self.status_class in {"unresolved", "unknown"}


@dataclass(frozen=True)
class SourceScan:
    units: tuple[SourceUnit, ...]
    sections: tuple[str, ...]
    anomalies: tuple[str, ...]


def _cells(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _clean(text: str | None) -> str:
    return re.sub(r"[`~*]", "", text or "").strip()


def _row_identity(cells: list[str]) -> str | None:
    first = cells[0].strip("`~* ")
    if _SHORT_OBLIGATION.fullmatch(first):
        return first
    for cell in cells[:2]:
        match = _IDENTITY.search(cell)
        if match:
            return match.group("id")
    return None


def _row_title(cells: list[str], row: Mapping[str, str], identity: str | None) -> str:
    for column in ("item", "summary"):
        if row.get(column):
            return (
                f"{identity}: {_clean(row[column])}" if identity and not _clean(row[column]).startswith(identity) else _clean(row[column])
            )
    link = re.match(r"\[(?P<text>[^\]]+)\]", cells[0].strip("~ "))
    if link:
        return _clean(link.group("text"))
    return identity or _clean(cells[0])[:120]


def scan_source(source: str, text: str) -> SourceScan:
    """Every record-like unit of one source, its ``##`` sections, and every construct the parser cannot read safely."""
    lines = text.splitlines()
    units: list[SourceUnit] = []
    sections: list[str] = []
    anomalies: list[str] = []
    section = ""
    section_line = 0
    section_status: str | None = None
    entry: dict | None = None
    fence: tuple[str, int] | None = None

    def close_entry(end: int) -> None:
        nonlocal entry
        if entry is not None:
            units.append(SourceUnit(source, section, "entry", entry["line"], end, entry["identity"], entry["title"], entry["status"]))
        entry = None

    def close_section(end: int) -> None:
        if section and section_status is not None:
            units.append(SourceUnit(source, section, "section-record", section_line, end, None, section, section_status))

    number = 0
    while number < len(lines):
        line = lines[number]
        number += 1
        if fence is not None:
            closing = _FENCE.match(line)
            if closing and closing.group("marker")[0] == fence[0][0] and len(closing.group("marker")) >= len(fence[0]):
                if not line[closing.end() :].strip():
                    fence = None
            continue
        opening = _FENCE.match(line)
        if opening:
            fence = (opening.group("marker"), number)
            continue
        heading = _HEADING.match(line)
        if heading and len(heading.group("marks")) <= 3:
            level = len(heading.group("marks"))
            close_entry(number - 1)
            if level <= 2:
                close_section(number - 1)
                section, section_line, section_status = heading.group("title").strip(), number, None
                if level == 2:
                    sections.append(section)
            else:
                title = heading.group("title").strip()
                match = _IDENTITY.search(title)
                entry = {"line": number, "identity": match.group("id") if match else title, "title": title, "status": None}
            continue
        status = _STATUS_LINE.match(line)
        if status:
            value = status.group("value").strip()
            if entry is not None:
                if entry["status"] is not None:
                    anomalies.append(f"{source}:{number} second **Status:** line in the record at line {entry['line']}")
                entry["status"] = entry["status"] or value
            elif section_status is None:
                section_status = value
            else:
                anomalies.append(f"{source}:{number} second **Status:** line in section {section!r}")
            continue
        if _LOOSE_STATUS_LINE.match(line) and not line.lstrip().startswith("|"):
            anomalies.append(f"{source}:{number} status line in an unrecognized form: {line.strip()[:80]!r}")
            continue
        if "|" in line and number < len(lines) and _DELIMITER_ROW.match(lines[number]) and "|" in lines[number]:
            header = [cell.strip().lower() for cell in _cells(line)]
            number += 1  # the delimiter row
            while number < len(lines) and "|" in lines[number]:  # a blank line has no pipe, so it ends the table
                row_line = lines[number]
                number += 1
                cells = _cells(row_line)
                row = dict(zip(header, cells, strict=False))
                status_column = next((name for name in ("status", "state", "disposition") if name in header), None)
                stated = row.get(status_column) if status_column else None
                struck = cells[0].startswith("~~")
                status_struck = bool(stated) and stated.strip().startswith("~~")
                if struck and stated and stated.strip() and not status_struck:
                    anomalies.append(f"{source}:{number} partly struck row: identity struck but status {stated.strip()[:40]!r} is not")
                identity = _row_identity(cells)
                units.append(
                    SourceUnit(
                        source,
                        section,
                        "row",
                        number,
                        number,
                        identity or _clean(re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", cells[0]))[:80],
                        _row_title(cells, row, identity),
                        stated,
                        status_column is not None,
                        struck,
                        status_struck,
                        _clean(row.get("severity")) or None,
                        _clean(row.get("priority")) or None,
                        row,
                    )
                )
            continue
        frozen = _FROZEN_BULLET.match(line)
        if frozen:
            owner = line.split("Live owner:", 1)[1].strip() if "Live owner:" in line else None
            units.append(SourceUnit(source, section, "frozen-mapping", number, number, frozen.group("path"), frozen.group("path"), owner))
    close_entry(len(lines))
    close_section(len(lines))
    if fence is not None:
        anomalies.append(f"{source}:{fence[1]} code fence is never closed; everything after it is unreadable")
    units.sort(key=lambda unit: unit.line)
    return SourceScan(tuple(units), tuple(sections), tuple(anomalies))


def source_units(source: str, text: str) -> list[SourceUnit]:
    return list(scan_source(source, text).units)


def source_sections(text: str) -> list[str]:
    return list(scan_source("", text).sections)


@dataclass(frozen=True)
class SectionDisposition:
    source: str
    title: str
    classification: str
    rationale: str
    statusless_reviewed: bool = False


@dataclass(frozen=True)
class InventoryRecord:
    id: str
    kind: str
    status: str | None
    disposition: str
    units: tuple[str, ...]
    title: str = ""
    aliases: tuple[str, ...] = ()
    anchors: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    severity: str | None = None
    parent: str | None = None
    duplicate_of: str | None = None
    duplicate_rationale: str | None = None
    status_conflict_disposition: str | None = None
    status_disposition: str | None = None
    priority_disposition: str | None = None
    terminal_disposition: str | None = None
    mitigation_outstanding: bool = False
    target_issue: int | None = None
    priority: str | None = None
    product: str = "optimus"
    reviewed: bool = False
    review_note: str | None = None
    rationale: str = ""
    # Reviewed passages of other files quoted exactly in the issue body: (context source, "line" | "section", text).
    quotes: tuple[tuple[str, str, str], ...] = ()
    # Reviewed passages of an adopted pilot's own body, quoted exactly in the body that replaces it.
    retained: tuple[str, ...] = ()
    # One-time migration evidence, never a status registry. ``status_current`` ({"status", "evidence"}) is the reviewed status an
    # issue must carry when authority moves, where the source changed after the baseline; it sets only the expected ``status:``
    # label. ``source_updates`` are dated passages of a pinned source commit that changed after the baseline, quoted exactly.
    status_current: Mapping[str, Any] | None = None
    source_updates: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class Inventory:
    schema: str
    baseline_commit: str
    source_blobs: Mapping[str, str]
    source_paths: Mapping[str, str]
    sections: tuple[SectionDisposition, ...]
    records: tuple[InventoryRecord, ...]
    compat_anchors: Mapping[str, str] = field(default_factory=dict)
    reviewed_anomalies: Mapping[str, str] = field(default_factory=dict)
    # Files quoted for context only, pinned like the sources but outside unit coverage.
    context_blobs: Mapping[str, str] = field(default_factory=dict)
    context_paths: Mapping[str, str] = field(default_factory=dict)
    # Reviewed adoptions of live issues without a generated region: record id -> {"issue", "fingerprint"}.
    adoptions: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    # The sealed identities the offline gates check: each frozen approval artifact's SHA-256 (path -> digest), each
    # docs-root plan file's owning record at its baseline blob (path -> {"record", "blob"}), and the docs-root documents
    # that track no issue of their own (path -> why).
    frozen_artifacts: Mapping[str, str] = field(default_factory=dict)
    plan_files: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    plan_exemptions: Mapping[str, str] = field(default_factory=dict)

    @property
    def read_paths(self) -> dict[str, str]:
        """Every file the inventory pins at its baseline: the coverage sources, then the context files."""
        return {**self.source_paths, **self.context_paths}


@dataclass(frozen=True)
class CoverageReport:
    problems: tuple[str, ...] = ()
    counts: Mapping[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


_RECORD_FIELDS = set(InventoryRecord.__dataclass_fields__)
_TUPLE_FIELDS = ("units", "aliases", "anchors", "related", "retained", "source_updates")


def inventory_from_data(data: Mapping) -> Inventory:
    if data.get("schema") != SCHEMA:
        raise ValueError(f"inventory schema is {data.get('schema')!r}, expected {SCHEMA!r}")
    records = []
    for raw in data["records"]:
        unknown = set(raw) - _RECORD_FIELDS
        if unknown:
            raise ValueError(f"record {raw.get('id')!r} has unknown fields {sorted(unknown)}")
        quotes = tuple(tuple(quote) for quote in raw.get("quotes", ()))
        records.append(InventoryRecord(**{**raw, **{name: tuple(raw.get(name, ())) for name in _TUPLE_FIELDS}, "quotes": quotes}))
    sources = data["baseline"]["sources"]
    context = data["baseline"].get("context", {})
    return Inventory(
        schema=data["schema"],
        baseline_commit=data["baseline"]["commit"],
        source_blobs={name: spec["blob"] for name, spec in sources.items()},
        source_paths={name: spec["path"] for name, spec in sources.items()},
        sections=tuple(SectionDisposition(**section) for section in data["sections"]),
        records=tuple(records),
        compat_anchors=dict(data.get("compat_anchors", {})),
        reviewed_anomalies=dict(data.get("reviewed_anomalies", {})),
        context_blobs={name: spec["blob"] for name, spec in context.items()},
        context_paths={name: spec["path"] for name, spec in context.items()},
        adoptions={record_id: dict(adoption) for record_id, adoption in data.get("adoptions", {}).items()},
        frozen_artifacts={path: entry["sha256"] for path, entry in data.get("frozen_artifacts", {}).items()},
        plan_files={path: {"record": entry["record"], "blob": entry["blob"]} for path, entry in data.get("plan_files", {}).items()},
        plan_exemptions=dict(data.get("plan_exemptions", {})),
    )


def load_inventory(path: Path) -> Inventory:
    return inventory_from_data(json.loads(path.read_text(encoding="utf-8")))


def validate_inventory(inventory: Inventory, sources: Mapping[str, bytes]) -> CoverageReport:
    """``sources`` holds every file in ``inventory.read_paths``: the coverage sources and the pinned context files."""
    problems: list[str] = []

    if set(sources) != set(inventory.read_paths):
        problems.append(f"sources {sorted(sources)} differ from the baseline sources {sorted(inventory.read_paths)}")
    for name, data in sources.items():
        if name in inventory.context_blobs:
            if inventory.context_blobs[name] != git_blob_id(data):
                problems.append(f"context {name!r} is not its pinned blob {inventory.context_blobs[name]}; re-derive the inventory")
        elif inventory.source_blobs.get(name) != git_blob_id(data):
            problems.append(f"source {name!r} is not the baseline blob {inventory.source_blobs.get(name)}; re-derive the inventory")

    scans = {name: scan_source(name, data.decode("utf-8")) for name, data in sources.items() if name in inventory.source_paths}
    seen_anomalies = set()
    for scan in scans.values():
        for anomaly in scan.anomalies:
            key = anomaly.split(" ", 1)[0]
            seen_anomalies.add(key)
            if not (inventory.reviewed_anomalies.get(key) or "").strip():
                problems.append(f"unreadable source: {anomaly}")
    for key in sorted(set(inventory.reviewed_anomalies) - seen_anomalies):
        problems.append(f"reviewed anomaly {key} no longer occurs in the sources; drop or update the acknowledgement")
    units = {unit.key: unit for scan in scans.values() for unit in scan.units}

    classified: dict[tuple[str, str], SectionDisposition] = {}
    for section in inventory.sections:
        key = (section.source, section.title)
        if key in classified:
            problems.append(f"section {section.source}:{section.title!r} is classified twice")
        if section.classification not in SECTION_CLASSIFICATIONS:
            problems.append(f"section {section.source}:{section.title!r} has unknown classification {section.classification!r}")
        if not section.rationale.strip():
            problems.append(f"section {section.source}:{section.title!r} has no rationale")
        classified[key] = section
    actual_sections = {(name, title) for name, scan in scans.items() for title in scan.sections}
    for source, title in sorted(actual_sections - set(classified)):
        problems.append(f"unclassified section {source}:{title!r}")
    for source, title in sorted(set(classified) - actual_sections):
        problems.append(f"classified section {source}:{title!r} does not exist in the source")

    records: dict[str, InventoryRecord] = {}
    for record in inventory.records:
        if record.id in records:
            problems.append(f"record id {record.id!r} is used twice")
        records[record.id] = record

    claims: Counter[str] = Counter(key for record in inventory.records for key in record.units)
    for key, count in claims.items():
        if count > 1:
            problems.append(f"unit {key} is claimed by more than one record")
        if key not in units:
            problems.append(f"unit {key} claimed by a record is not a unit of the sources")

    for key, unit in units.items():
        if claims[key]:
            continue
        section = classified.get((unit.source, unit.section))
        retires = section is not None and section.classification in RETIRING_DISPOSITIONS
        label = f"unclaimed unit {key} ({unit.kind} {unit.identity!r} in {unit.section!r}, status {unit.stated_status!r})"
        state = unit.status_class
        if state in {"unresolved", "unknown"}:
            problems.append(f"{label}: {'unknown status vocabulary' if state == 'unknown' else 'unresolved work'}")
        elif not retires:
            problems.append(f"{label}: its section is not retired, so it needs a record")
        elif state == "statusless" and not section.statusless_reviewed:
            problems.append(f"{label}: no status; claim it or mark the section's statusless rows reviewed")
        elif normalized_status(unit.stated_status) == REVIEWED_DISPOSITION:
            problems.append(f"{label}: a reviewed disposition always needs its own record")

    index = identity_index((record.id, record.aliases) for record in inventory.records)
    aliases: dict[str, str] = {}
    source_paths = set(inventory.source_paths.values())
    for record in inventory.records:
        problems.extend(_record_problems(record, records, units, index))
        problems.extend(_current_status_problems(record))
        problems.extend(_source_update_shape_problems(record, source_paths))
        if record.disposition == "migrate":
            for alias in record.aliases:
                if alias in aliases and aliases[alias] != record.id:
                    problems.append(f"alias {alias!r} names both {aliases[alias]!r} and {record.id!r}")
                aliases[alias] = record.id
    problems.extend(_target_issue_problems(inventory.records))
    problems.extend(_quote_problems(inventory, sources))
    problems.extend(_adoption_problems(inventory, records))
    problems.extend(_parent_cycles(records))
    for anchor, target in inventory.compat_anchors.items():
        if target not in records and not target.startswith("section:"):
            problems.append(f"compatibility anchor {anchor!r} points to unknown record {target!r}")

    counts = Counter(record.disposition for record in inventory.records)
    counts.update({"units": len(units), "records": len(records)})
    return CoverageReport(tuple(problems), dict(counts))


def identity_index(records: Iterable[tuple[str, Sequence[str]]]) -> dict[str, str]:
    """Source identity -> record id: every record id, then each alias not already taken (the first record keeps it)."""
    pairs = list(records)
    index: dict[str, str] = {}
    for record_id, aliases in pairs:
        for alias in aliases:
            index.setdefault(alias, record_id)
    index.update({record_id: record_id for record_id, _aliases in pairs})
    return index


def _target_issue_problems(records: Sequence[InventoryRecord]) -> list[str]:
    """Each migrating record lands on its own issue; a record that maps to another's issue is a ``duplicate``."""
    problems = []
    targets: dict[int, str] = {}
    for record in records:
        target = record.target_issue
        if target is None:
            continue
        label = f"record {record.id!r}"
        if not isinstance(target, int) or isinstance(target, bool) or target < 1:
            problems.append(f"{label} target issue {target!r} is not a positive issue number")
        elif record.disposition != "migrate":
            problems.append(f"{label} targets issue #{target} but does not migrate; a duplicate names its original with duplicate_of")
        elif target in targets:
            problems.append(
                f"{label} targets issue #{target}, which {targets[target]!r} already targets; a true duplicate uses duplicate_of"
            )
        else:
            targets[target] = record.id
    return problems


QUOTE_SELECTORS = ("line", "section")
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def _headings(lines: Sequence[str]) -> list[tuple[int, int, str]]:
    """(line number, level, title) of every heading outside fenced code."""
    found, fence = [], None
    for number, line in enumerate(lines, 1):
        opener = _FENCE.match(line)
        if opener:
            marker = opener.group("marker")
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            continue
        heading = None if fence else _HEADING.match(line)
        if heading:
            found.append((number, len(heading.group("marks")), heading.group("title")))
    return found


def quote_span(lines: Sequence[str], selector: str, text: str) -> tuple[int, int]:
    """The 1-based ``(first, last)`` lines a reviewed context quote covers.

    ``line`` is the one line that starts with ``text``; ``section`` is the one heading titled ``text`` through the line
    before the next heading of the same or a higher level, without trailing blank lines. Anything else is an error.
    """
    if selector == "line":
        found = [number for number, line in enumerate(lines, 1) if line.startswith(text)]
    elif selector == "section":
        headings = _headings(lines)
        found = [number for number, _level, title in headings if title == text]
    else:
        raise ValueError(f"unknown selector {selector!r}; use one of {', '.join(QUOTE_SELECTORS)}")
    if len(found) != 1:
        raise ValueError(f"{selector} {text!r} matches {len(found) or 'no'} line(s); a quote must match exactly one")
    first = last = found[0]
    if selector == "section":
        level = next(level for number, level, _title in headings if number == first)
        last = next((number - 1 for number, other, _title in headings if number > first and other <= level), len(lines))
        while last > first and not lines[last - 1].strip():
            last -= 1
    return first, last


def _quote_problems(inventory: Inventory, sources: Mapping[str, bytes]) -> list[str]:
    """Each reviewed context quote names a pinned context file and resolves there exactly once."""
    problems = []
    for record in inventory.records:
        for source, selector, text in record.quotes:
            label = f"record {record.id!r} context quote ({selector} {text!r} in {source!r})"
            if record.disposition != "migrate":
                problems.append(f"{label}: only a migrating record's issue body quotes context")
            if source not in inventory.context_paths:
                problems.append(f"{label}: unknown context source; pin it under the baseline's context")
            elif source in sources:
                try:
                    quote_span(sources[source].decode("utf-8").splitlines(), selector, text)
                except ValueError as error:
                    problems.append(f"{label}: {error}")
    return problems


def _adoption_problems(inventory: Inventory, records: Mapping[str, InventoryRecord]) -> list[str]:
    """A reviewed adoption names a migrating record, that record's reviewed target issue and a SHA-256 fingerprint."""
    problems = []
    for record_id, adoption in inventory.adoptions.items():
        label = f"adoption of {record_id!r}"
        record = records.get(record_id)
        if record is None or record.disposition != "migrate":
            problems.append(f"{label}: no migrating record has that id")
        elif record.target_issue is None or adoption.get("issue") != record.target_issue:
            problems.append(f"{label} names #{adoption.get('issue')}, not the record's reviewed target issue {record.target_issue}")
        if not (isinstance(adoption.get("fingerprint"), str) and _SHA256_HEX.fullmatch(adoption["fingerprint"])):
            problems.append(f"{label}: its fingerprint {adoption.get('fingerprint')!r} is not a SHA-256 hex digest")
    for record in records.values():
        label = f"record {record.id!r}"
        if record.retained and record.id not in inventory.adoptions:
            problems.append(f"{label} retains pilot passages, but only a record with a reviewed adoption has a pilot body to retain")
        for index, passage in enumerate(record.retained, 1):
            if not passage.strip():
                problems.append(f"{label}: retained pilot passage {index} is empty")
            elif passage != passage.strip():
                problems.append(f"{label}: retained pilot passage {index} has surrounding whitespace; cut it exactly")
            if _MARKER.search(passage) or _END_MARKER.search(passage):
                problems.append(f"{label}: retained pilot passage {index} carries a source marker, which would split the region")
            if record.retained.index(passage) != index - 1:
                problems.append(f"{label}: retained pilot passage {index} appears more than once")
    return problems


_COMMIT_ID = re.compile(r"[0-9a-f]{40}")
_UPDATE_FIELDS = frozenset({"date", "path", "line", "commit", "commit_pin", "text"})  # commit_pin only carries the secret-scan pragma
_UPDATE_REQUIRED = frozenset({"date", "path", "line", "commit", "text"})


def _current_status_problems(record: InventoryRecord) -> list[str]:
    """A reviewed current status is a known status that has a reviewed label, with a permalink as its evidence."""
    value = record.status_current
    if value is None:
        return []
    label = f"record {record.id!r} status_current"
    if record.disposition != "migrate":
        return [f"{label}: only a migrating record carries one"]
    if not isinstance(value, Mapping):
        return [f"{label} must be an object with a status and its evidence"]
    problems = []
    if unknown := sorted(set(value) - {"status", "evidence"}):
        problems.append(f"{label} has unknown fields {unknown}")
    status, evidence = value.get("status"), value.get("evidence")
    if not isinstance(status, str) or normalized_status(status) is None:
        problems.append(f"{label}: {status!r} is not a known status")
    elif status_label(status) not in LABEL_SPECS:
        problems.append(f"{label}: {status!r} has no reviewed status label")
    if not isinstance(evidence, str) or not evidence.strip():
        problems.append(f"{label} needs its evidence")
    elif not _PERMALINK.match(evidence):
        problems.append(f"{label}: its evidence must be a permalink to a file of this repository at a commit")
    return problems


def _source_update_shape_problems(record: InventoryRecord, source_paths: set[str]) -> list[str]:
    """Each source update is a dated, committed, exactly quoted passage of a baseline source; its text is checked against the
    commit by ``source_update_problems``."""
    if not record.source_updates:
        return []
    label = f"record {record.id!r} source update"
    if record.disposition != "migrate":
        return [f"{label}: only a migrating record carries one"]
    problems = []
    seen: set[tuple[Any, Any, Any]] = set()
    for index, update in enumerate(record.source_updates, 1):
        where = f"{label} {index}"
        if not isinstance(update, Mapping):
            problems.append(f"{where} must be an object")
            continue
        if unknown := sorted(set(update) - _UPDATE_FIELDS):
            problems.append(f"{where} has unknown fields {unknown}")
        if missing := sorted(_UPDATE_REQUIRED - set(update)):
            problems.append(f"{where} lacks {missing}")
        date, commit, path = update.get("date"), update.get("commit"), update.get("path")
        line, text = update.get("line"), update.get("text")
        if "date" in update and not _calendar_date(date):
            problems.append(f"{where} date {date!r} is not a calendar date written YYYY-MM-DD")
        if "commit" in update and not (isinstance(commit, str) and _COMMIT_ID.fullmatch(commit)):
            problems.append(f"{where} commit {commit!r} is not a lowercase 40-hex commit id")
        if "path" in update and path not in source_paths:
            problems.append(f"{where} path {path!r} is not one of the baseline sources {sorted(source_paths)}")
        if "line" in update and not (isinstance(line, int) and not isinstance(line, bool) and line >= 1):
            problems.append(f"{where} line {line!r} is not a positive line number")
        if "text" in update:
            if not isinstance(text, str) or not text.strip():
                problems.append(f"{where} text is empty")
            else:
                if text != text.strip():
                    problems.append(f"{where} text has surrounding whitespace; quote it exactly")
                if _MARKER.search(text) or _END_MARKER.search(text):
                    problems.append(f"{where} text carries a source marker, which would split the generated region")
        key = (commit, path, line)
        if key in seen:
            problems.append(f"{where} appears more than once (same commit, path and line)")
        seen.add(key)
    return problems


def _calendar_date(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def source_update_problems(inventory: Inventory, read: SourceReader) -> list[str]:
    """Each source update's quoted text is on its cited line of its source file at its commit.

    ``read`` is a source reader (``read_sources_at``). A commit or file that cannot be read is a problem, never a skip. Updates
    with a malformed shape are left to ``validate_inventory``.
    """
    names = {path: name for name, path in inventory.source_paths.items()}
    problems: list[str] = []
    cache: dict[tuple[str, str], list[str] | str] = {}
    for record in inventory.records:
        for index, update in enumerate(record.source_updates, 1):
            if not isinstance(update, Mapping) or not _UPDATE_REQUIRED <= set(update) or update["path"] not in names:
                continue
            where = f"record {record.id!r} source update {index}"
            commit, path, line, text = update["commit"], update["path"], update["line"], update["text"]
            if (commit, path) not in cache:
                try:
                    cache[commit, path] = read(commit, {names[path]: path})[names[path]].decode("utf-8").splitlines()
                except (subprocess.CalledProcessError, KeyError, OSError, UnicodeDecodeError) as error:
                    cache[commit, path] = f"cannot be read at {commit} ({type(error).__name__})"
            lines = cache[commit, path]
            if isinstance(lines, str):
                problems.append(f"{where}: {path} {lines}")
            elif not isinstance(line, int) or not 1 <= line <= len(lines):
                problems.append(f"{where}: {path} at {commit[:12]} has no line {line}")
            elif text not in lines[line - 1]:
                problems.append(f"{where}: line {line} of {path} at {commit[:12]} does not contain the quoted text")
    return problems


def _status_problems(record: InventoryRecord, claimed: Sequence[SourceUnit]) -> list[str]:
    """The record's status is the text one of its claimed units states; only a status no unit states may be synthesized."""
    label = f"record {record.id!r}"
    stated = sorted({_clean(unit.stated_status) for unit in claimed if unit.kind != "frozen-mapping" and _clean(unit.stated_status)})
    disposition = (record.status_disposition or "").strip()
    problems = []
    if stated:
        if record.status not in stated:
            problems.append(f"{label} status {record.status!r} is not the source status of any claimed unit {stated}")
        if disposition:
            problems.append(f"{label} has a status disposition, but its source states the status, which cannot be overridden")
    elif record.status is not None:
        if not disposition:
            problems.append(
                f"{label} status {record.status!r} is stated by no claimed unit; a synthesized status needs a status disposition"
            )
        if normalized_status(record.status) is None:
            problems.append(f"{label} synthesized status {record.status!r} is not a known status")
    if record.disposition == "migrate" and not (record.status or "").strip():
        problems.append(f"{label} migrates without a status")
    return problems


def _priority_problems(record: InventoryRecord, claimed: Sequence[SourceUnit]) -> list[str]:
    """A migrating record's priority is its source value; without one it is the default unless a disposition says why."""
    if record.disposition != "migrate":
        return []
    label = f"record {record.id!r}"
    stated = sorted({unit.priority.upper() for unit in claimed if unit.priority})
    disposition = (record.priority_disposition or "").strip()
    if record.priority not in PRIORITIES:
        return [f"{label} priority {record.priority!r} is not one of {sorted(PRIORITIES)}"]
    if stated and record.priority not in stated:
        return [f"{label} priority {record.priority!r} is not its source priority {stated}"]
    if len(stated) == 1 and disposition:
        return [f"{label} has a priority disposition, but its source states the priority, which cannot be overridden"]
    if len(stated) > 1 and not disposition:
        return [f"{label} has conflicting source priorities {stated} without a priority disposition"]
    if not stated and record.priority != DEFAULT_PRIORITY and not disposition:
        return [
            f"{label} priority {record.priority!r} has no source and is not the default {DEFAULT_PRIORITY}; it needs a priority disposition"
        ]
    return []


def _record_problems(
    record: InventoryRecord, records: Mapping[str, InventoryRecord], units: Mapping[str, SourceUnit], index: Mapping[str, str]
) -> list[str]:
    problems = []
    label = f"record {record.id!r}"
    if record.kind not in RECORD_KINDS:
        problems.append(f"{label} has unknown kind {record.kind!r}")
    if record.disposition not in DISPOSITIONS:
        problems.append(f"{label} has unknown disposition {record.disposition!r}")
    if record.product not in PRODUCTS:
        problems.append(f"{label} has unknown product {record.product!r}")
    if not record.units and record.kind != "external-issue":
        problems.append(f"{label} claims no source unit")
    if record.disposition == "migrate" and not record.title.strip():
        problems.append(f"{label} migrates without a title")
    if record.reviewed and not (record.review_note or "").strip():
        problems.append(f"{label} is marked reviewed without a review note")
    for reference in (record.parent, record.duplicate_of, *record.related):
        if reference is not None and reference not in records:
            problems.append(f"{label} references unknown record {reference!r}")
    parent = records.get(record.parent) if record.parent else None
    if record.disposition == "migrate" and parent is not None and parent.disposition != "migrate":
        problems.append(f"{label} would hang under parent {parent.id!r}, which is not migrating ({parent.disposition})")

    if record.disposition == "duplicate":
        if not record.duplicate_of:
            problems.append(f"{label} is a duplicate without duplicate_of")
        elif records.get(record.duplicate_of) and records[record.duplicate_of].disposition == "duplicate":
            problems.append(f"{label} is a duplicate of another duplicate")
        if not (record.duplicate_rationale or "").strip():
            problems.append(f"{label} is a duplicate without a duplicate rationale")

    claimed = [units[key] for key in record.units if key in units]
    problems.extend(_status_problems(record, claimed))
    problems.extend(_priority_problems(record, claimed))
    for unit in claimed:
        if unit.kind == "frozen-mapping":  # every live owner with a record stays linked; one without stays a name
            for identity in owner_identities(unit.stated_status):
                target = index.get(identity)
                if target is not None and target not in record.related:
                    problems.append(f"{label} drops live owner {identity!r} (record {target!r}) named by {unit.key}")

    identities = {unit.identity for unit in claimed if unit.kind != "section-record"}
    if len(identities) > 1 and not (record.duplicate_rationale or "").strip():
        problems.append(f"{label} merges identities {sorted(map(str, identities))} without a duplicate rationale")

    statuses = {normalized_status(unit.stated_status) for unit in claimed} - {None}
    if len(statuses) > 1 and not (record.status_conflict_disposition or "").strip():
        problems.append(f"{label} has conflicting source statuses {sorted(statuses)} without a reviewed disposition")

    plan_units = [unit for unit in claimed if unit.section in PLAN_UNIT_SECTIONS]
    if plan_units and len(plan_units) != len(claimed):
        problems.append(f"{label} merges plan and item units; their acceptance surfaces must stay separate records")

    if record.disposition in RETIRING_DISPOSITIONS:
        if any(unit.unresolved for unit in claimed) and not (record.terminal_disposition or "").strip():
            problems.append(f"{label} retires unresolved work ({record.disposition}) without an explicit terminal disposition")
        if record.kind == "risk" and record.mitigation_outstanding:
            problems.append(f"{label} is an accepted risk with outstanding mitigation and cannot be {record.disposition}")
    return problems


def _parent_cycles(records: Mapping[str, InventoryRecord]) -> list[str]:
    """Native sub-issue parents form a forest; a cycle can never be bound on GitHub."""
    problems = []
    for start in records:
        seen, current = [start], records[start].parent
        while current is not None and current in records:
            if current in seen:
                if current == start:
                    problems.append(f"record {start!r} is in a parent cycle {' -> '.join([*seen, current])}")
                break
            seen.append(current)
            current = records[current].parent
    return problems


REPO_ROOT = Path(__file__).resolve().parents[1]
SourceReader = Callable[[str, Mapping[str, str]], Mapping[str, bytes]]


def git_blob_bytes(commit: str, path: str, repo: Path = REPO_ROOT) -> bytes:
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=repo, check=True, capture_output=True).stdout


def read_sources_at(commit: str, paths: Mapping[str, str], repo: Path = REPO_ROOT) -> dict[str, bytes]:
    """Source bytes exactly as committed at ``commit``, never the working tree."""
    return {name: git_blob_bytes(commit, path, repo) for name, path in paths.items()}


PLANS_DIR = "docs/superpowers/plans/"
POOL_FILE = "2026-07-23-consolidated-deferred-followups-backlog.md"
POOL_PATH = PLANS_DIR + POOL_FILE


def read_plans_at(commit: str, repo: Path = REPO_ROOT) -> dict[str, bytes]:
    """Every docs-root plan file (``docs/superpowers/plans/*.md``, not the archive) exactly as committed at ``commit``."""
    listing = subprocess.run(["git", "ls-tree", "-z", commit, "--", PLANS_DIR], cwd=repo, check=True, capture_output=True).stdout
    entries = [entry.decode("utf-8") for entry in listing.split(b"\0") if entry]
    paths = [entry.split("\t", 1)[1] for entry in entries if entry.split(" ", 2)[1] == "blob"]
    return {path: git_blob_bytes(commit, path, repo) for path in sorted(paths) if path.endswith(".md")}


def render_manifest(data: Mapping) -> str:
    """The manifest text: stable key order, LF, and each pinned id on one line with its inline secret-scan marker."""
    text = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    text = re.sub(r'\{\n\s+"path": (".*?"),\n\s+"blob": (".*?"),\n\s+"pin": (".*?")\n\s+\}', r'{"path": \1, "blob": \2, "pin": \3}', text)
    text = re.sub(
        r'\{\n\s+"issue": (\d+),\n\s+"fingerprint": (".*?"),\n\s+"pin": (".*?")\n\s+\}',
        r'{"issue": \1, "fingerprint": \2, "pin": \3}',
        text,
    )
    text = re.sub(r'\{\n\s+"sha256": (".*?"),\n\s+"pin": (".*?")\n\s+\}', r'{"sha256": \1, "pin": \2}', text)
    text = re.sub(
        r'\{\n\s+"record": (".*?"),\n\s+"blob": (".*?"),\n\s+"pin": (".*?")\n\s+\}', r'{"record": \1, "blob": \2, "pin": \3}', text
    )
    return re.sub(r'\n(\s+)"commit": (".*?"),\n\s+"commit_pin": (".*?"),', r'\n\1"commit": \2, "commit_pin": \3,', text)


# ==== Task 2: bounded, restart-safe publication and reconciliation ====
#
# Publication is planned completely before the first write: every issue and label page is read (pull requests
# excluded), every conflict is found, and the batch lists each exact body, label set and native binding. Applying a
# batch journals each write's intent durably before sending it, re-reads an issue against the fingerprint the plan saw
# before updating it, validates each result (a binding both ways) before the next write, and stops on any mismatch or
# unknown outcome. Nothing is ever retried; a stopped run is reconciled read-only and needs fresh authority to go on.

REPO = "vibhanshu-agarwal/optimus-cost-agent"
PAGE = REPO_ROOT / "docs" / "work-status.html"
TRIAL_LABEL = "shadow-pilot"
WRITE_PAUSE_S = 1.0  # GitHub asks clients to wait at least a second between mutating requests
TITLE_LIMIT, BODY_LIMIT = 256, 65_536
MAX_PAGES = 100
# Neutral on purpose: it stays true before and after the authority switch, because it names the one place that states who is
# authoritative (the backlog's own `Moved` pointer) instead of asserting an owner.
TRIAL_BANNER = (
    "> **Staged copy for the tracking migration.** Whether this issue or the consolidated backlog is authoritative for this record is stated only"
    " by the backlog's pointer for it: a row or entry marked `Moved` that links this issue. Until that pointer is on the default branch, the backlog"
    " remains authoritative. This issue grants no implementation or live-run authority. Do not reference it with a closing keyword."
)
_MARKER = re.compile(r"<!-- optimus-source: (\S+) -->")
_END_MARKER = re.compile(r"<!-- /optimus-source: (\S+) -->")
_PARENT_URL = re.compile(rf"https://api\.github\.com/repos/{re.escape(REPO)}/issues/(\d+)")
_LINK_TARGET = re.compile(r"(\]\()([^)\s]+)(\))")
_VOCABULARY = re.compile(r'<script type="application/json" id="work-status-vocabulary">(?P<json>.*?)</script>', re.DOTALL)
_SOURCE_DIMENSIONS = ("status", "product", "kind")  # always the source record's value
_DEFAULTED_DIMENSIONS = ("priority", "difficulty", "estimate", "handler")  # an explicit value on the issue survives a default
_MANAGED_PREFIXES = tuple(f"{dimension}:" for dimension in (*_SOURCE_DIMENSIONS, *_DEFAULTED_DIMENSIONS))


@dataclass(frozen=True)
class LabelSpec:
    name: str
    description: str
    color: str

    def payload(self) -> dict[str, str]:
        return {"color": self.color, "description": self.description}


# The pilot's 13 labels keep their published values; the rest are agent proposals reviewed before publication.
LABEL_SPECS = {
    name: LabelSpec(name, description, color)
    for name, description, color in (
        ("shadow-pilot", "Trial copy; repository pool remains authoritative", "d4c5f9"),
        ("status:open", "Source record is Open", "0e8a16"),
        ("status:partially-implemented", "Source record is Partially implemented", "fbca04"),
        ("status:promoted", "Source record is Promoted to a plan", "c5def5"),
        ("status:blocked", "Source record is Blocked", "d93f0b"),
        ("status:active", "Source record is Active", "0e8a16"),
        ("status:not-drafted", "Source record is Not drafted", "ededed"),
        ("status:in-review", "Source record is In review", "1d76db"),
        ("status:ready", "Source record is Ready", "0e8a16"),
        ("status:accepted-open", "Source record is Accepted open: reviewed and still open work", "fbca04"),
        ("status:unrun", "Source record is Unrun", "d93f0b"),
        ("status:unrun-binding", "Source record is Unrun and binding", "b60205"),
        ("priority:high", "High scheduling priority", "d93f0b"),
        ("priority:medium", "Medium scheduling priority", "fbca04"),
        ("priority:low", "Low scheduling priority", "c2e0c6"),
        ("difficulty:high", "High complexity/difficulty", "e99695"),
        ("difficulty:medium", "Medium complexity/difficulty; default unless assessed", "c2e0c6"),
        ("difficulty:low", "Low complexity/difficulty", "bfdadc"),
        ("estimate:na", "Planned Estimate is NA: not estimated", "ededed"),
        ("estimate:1d", "Working days remaining to DONE: 1; excludes approval waits", "c5def5"),
        ("estimate:2d", "Working days remaining to DONE: 2; excludes approval waits", "c5def5"),
        ("estimate:3d", "Working days remaining to DONE: 3; excludes approval waits", "c5def5"),
        ("estimate:5d", "Working days remaining to DONE: 5; excludes approval waits", "c5def5"),
        ("estimate:8d", "Working days remaining to DONE: 8; excludes approval waits", "c5def5"),
        ("estimate:13d", "Working days remaining to DONE: 13; excludes approval waits", "c5def5"),
        ("handler:claude", "Current work handler: Claude", "bfd4f2"),
        ("handler:codex", "Current work handler: Codex", "bfd4f2"),
        ("handler:operator", "Current work handler: the operator", "bfd4f2"),
        ("handler:unassigned", "No current work handler assigned", "ededed"),
        ("product:optimus", "Optimus product", "1d76db"),
        ("product:evidence-a2a", "Evidence/A2A product", "5319e7"),
        ("kind:feature", "Feature slice that owns plans and items", "0e8a16"),
        ("kind:plan", "Tracking issue for a repository implementation plan", "0052cc"),
        ("kind:track", "Hardening child-plan track", "5319e7"),
        ("kind:candidate", "Reviewed candidate awaiting its own plan", "c5def5"),
        ("kind:follow-up", "Deferred follow-up with its own acceptance criteria", "006b75"),
        ("kind:obligation", "Audit obligation retaining its owning feature custody", "7057ff"),
        ("kind:item", "Work item owned by a track or feature", "bfdadc"),
    )
}


@functools.cache
def page_vocabulary(page: Path = PAGE) -> dict[str, Any]:
    """The live page's label vocabulary, the one list of status, dimension, product and kind values."""
    match = _VOCABULARY.search(page.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"{page} has no work-status vocabulary block")
    return json.loads(match.group("json"))


def _label_values(dimension: str) -> set[str] | None:
    """The allowed values of a label dimension; ``None`` for a free-form dimension."""
    vocabulary = page_vocabulary()
    plain = {"status": "statuses", "product": "products", "kind": "kinds"}
    if dimension in plain:
        return set(vocabulary[plain[dimension]])
    for spec in vocabulary["dimensions"].values():
        if spec["label"] == dimension:
            return None if spec.get("free_form") else set(spec["values"])
    return set()


def _valid_label(label: str) -> bool:
    dimension, _, value = label.partition(":")
    values = _label_values(dimension)
    return bool(value) and (values is None or value in values)


def _managed(label: str) -> bool:
    """GitHub label names are unique case-insensitively, so ``Priority:High`` is a managed priority label too."""
    lowered = label.lower()
    return lowered == TRIAL_LABEL or lowered.startswith(_MANAGED_PREFIXES)


def _in_dimension(label: str, dimension: str) -> bool:
    return label.lower().startswith(dimension + ":")


def source_marker(record_id: str) -> str:
    """The identity marker an issue body carries; the plan and A2A forms are the ones the pilot published (#222, #225)."""
    if record_id.startswith("plan:"):
        return "PLAN-" + record_id.removeprefix("plan:")
    if record_id.startswith("A2A-"):
        return "EVIDENCE-HANDOFF-" + record_id
    return record_id


def marker_comment(marker: str) -> str:
    return f"<!-- optimus-source: {marker} -->"


def end_marker_comment(marker: str) -> str:
    """Closes the generated region; text outside the region belongs to the issue and survives every update."""
    return f"<!-- /optimus-source: {marker} -->"


def generated_region(body: str, marker: str) -> tuple[int, int] | str:
    """The ``[start, end)`` span of a body's generated region for ``marker``, or why there is no single well-formed one."""
    start, end = marker_comment(marker), end_marker_comment(marker)
    if body.count(start) != 1:
        return f"its body carries {body.count(start)} copies of the source marker"
    if body.count(end) == 0:
        return "its body has no generated region (the source marker without a region end, as in a pilot body); rewriting it would discard reviewed text, so it needs a reviewed body decision first"
    if body.count(end) != 1 or body.index(end) < body.index(start):
        return "its body has a malformed generated region"
    return body.index(start), body.index(end) + len(end)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _issue_list(numbers: Iterable[int]) -> str:
    return ", ".join(f"#{number}" for number in sorted(numbers))


# ---- transport and reads ----


class TransportError(RuntimeError):
    """A GitHub request did not complete cleanly; ``status`` is the HTTP status when gh reported one."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ReadFailed(RuntimeError):
    """A read returned nothing usable, so planning or verification cannot rest on it."""


class GitHubClient(Protocol):
    def get(self, path: str) -> str: ...

    def send(self, method: str, path: str, payload: Mapping[str, Any]) -> str: ...


class GhClient:
    """The executor's existing ``gh`` connection: transport only; parsing and classification are shared code."""

    def __init__(self, timeout_s: float = 120) -> None:
        self.timeout_s = timeout_s

    def get(self, path: str) -> str:
        return self._run(["gh", "api", path], None)

    def send(self, method: str, path: str, payload: Mapping[str, Any]) -> str:
        return self._run(["gh", "api", "-X", method, path, "--input", "-"], json.dumps(payload).encode("utf-8"))

    def _run(self, command: list[str], data: bytes | None) -> str:
        try:
            completed = subprocess.run(command, input=data, capture_output=True, timeout=self.timeout_s, check=False)
        except (subprocess.TimeoutExpired, OSError) as error:
            raise TransportError(f"{type(error).__name__}: {error}") from None
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", "replace").strip()
            status = re.search(r"HTTP (\d{3})", stderr)
            raise TransportError(f"gh exited {completed.returncode}: {stderr[:300]}", int(status.group(1)) if status else None)
        return completed.stdout.decode("utf-8")


def _json(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError as error:
        raise ReadFailed(f"the response is not JSON ({error})") from None


def read_pages(client: GitHubClient, path: str) -> list[Any]:
    """Every object of a REST list, 100 per page, until an empty page."""
    items: list[Any] = []
    separator = "&" if "?" in path else "?"
    for page in range(1, MAX_PAGES + 1):
        try:
            batch = _json(client.get(f"{path}{separator}per_page=100&page={page}"))
        except TransportError as error:
            raise ReadFailed(f"reading {path} page {page} failed: {error}") from None
        if not isinstance(batch, list):
            raise ReadFailed(f"{path} page {page} is not a list")
        if not batch:
            return items
        items.extend(batch)
    raise ReadFailed(f"{path} has more than {MAX_PAGES} pages")


@dataclass(frozen=True)
class IssueSnapshot:
    number: int
    id: int
    title: str
    body: str
    labels: tuple[str, ...]
    state: str
    state_reason: str | None
    parent: int | None

    @property
    def markers(self) -> tuple[str, ...]:
        return tuple(_MARKER.findall(self.body))

    @property
    def fingerprint(self) -> str:
        """What an update must still find before it writes: title, body, labels, state and native parent."""
        fields = (self.title, self.body, list(self.labels), self.state, self.state_reason, self.parent)
        return _sha256(_canonical(dict(zip(("title", "body", "labels", "state", "state_reason", "parent"), fields, strict=True))))


def issue_snapshot(raw: Any) -> IssueSnapshot:
    """An issue object as read from GitHub; a parent URL outside this repository is unusable, never followed."""
    try:
        url = raw.get("parent_issue_url")
        parent = None
        if url is not None:
            match = _PARENT_URL.fullmatch(url)
            if match is None:
                raise ReadFailed(f"issue #{raw.get('number')} has a parent URL outside {REPO}: {url!r}")
            parent = int(match.group(1))
        labels = tuple(sorted(label["name"] for label in raw["labels"]))
        return IssueSnapshot(
            int(raw["number"]), int(raw["id"]), raw["title"], raw.get("body") or "", labels, raw["state"], raw.get("state_reason"), parent
        )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ReadFailed(f"unusable issue object ({type(error).__name__}: {error})") from None


def read_issues(client: GitHubClient, repo: str = REPO) -> list[IssueSnapshot]:
    """Every issue in every state, once each (a page shift can list one twice); pull requests are dropped."""
    issues: dict[int, IssueSnapshot] = {}
    for raw in read_pages(client, f"repos/{repo}/issues?state=all"):
        if not (isinstance(raw, dict) and "pull_request" in raw):
            issue = issue_snapshot(raw)
            issues[issue.number] = issue  # the later observation wins
    return list(issues.values())


def read_labels(client: GitHubClient, repo: str = REPO) -> dict[str, LabelSpec]:
    """Repository labels keyed by lower-cased name, because GitHub label names are unique case-insensitively."""
    labels = {}
    for raw in read_pages(client, f"repos/{repo}/labels"):
        try:
            labels[raw["name"].lower()] = LabelSpec(raw["name"], raw.get("description") or "", str(raw["color"]).lower())
        except (AttributeError, KeyError, TypeError) as error:
            raise ReadFailed(f"unusable label object ({type(error).__name__}: {error})") from None
    return labels


# ---- issue drafts: the exact body and labels of each migrating record ----


def blob_url(path: str, commit: str, repo: str = REPO) -> str:
    return f"https://github.com/{repo}/blob/{commit}/{path}"


def normalize_links(text: str, source_path: str, commit: str, repo: str = REPO) -> str:
    """Relative and in-page link targets of quoted source become permalinks at ``commit``; nothing else changes."""

    def pinned(match: re.Match[str]) -> str:
        target = match.group(2)
        if re.match(r"(?i)(https?|mailto):", target):
            return match.group(0)
        path, hash_mark, anchor = target.partition("#")
        if path.startswith("/"):
            resolved = posixpath.normpath(path.lstrip("/"))
        else:
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source_path), path)) if path else source_path
        if resolved == ".." or resolved.startswith("../"):
            raise ValueError(f"link {target!r} in {source_path} resolves outside the repository")
        return f"{match.group(1)}{blob_url(resolved, commit, repo)}{hash_mark}{anchor}{match.group(3)}"

    return _LINK_TARGET.sub(pinned, text)


def _unit_span(unit: SourceUnit, lines: Sequence[str]) -> tuple[int, int, list[str]]:
    """(first, last, text) of a unit in its source; a row is quoted with its table's header and delimiter rows."""
    if unit.kind == "row":
        index = unit.line - 2
        while index >= 1 and not _DELIMITER_ROW.match(lines[index]):
            index -= 1
        if index < 1:
            raise ValueError(f"{unit.key}: no table header above the row")
        return unit.line, unit.line, [lines[index - 1], lines[index], lines[unit.line - 1]]
    if unit.kind == "frozen-mapping":
        return unit.line, unit.line, [lines[unit.line - 1]]
    last = unit.end
    if unit.kind == "section-record":  # the section's own text, not the entries beneath it
        for number in range(unit.line + 1, unit.end + 1):
            heading = _HEADING.match(lines[number - 1])
            if heading and len(heading.group("marks")) <= 3:
                last = number - 1
                break
    while last > unit.line and not lines[last - 1].strip():
        last -= 1
    return unit.line, last, list(lines[unit.line - 1 : last])


def unit_source_text(unit: SourceUnit, lines: Sequence[str]) -> str:
    return "\n".join(_unit_span(unit, lines)[2])


def priority_basis(record: InventoryRecord, claimed: Sequence[SourceUnit]) -> str:
    """``source`` when a claimed unit states a priority, ``reviewed`` for a disposed value, otherwise ``default``."""
    if any(unit.priority for unit in claimed):
        return "source"
    return "reviewed" if (record.priority_disposition or "").strip() else "default"


def status_label(status: str | None) -> str:
    token = normalized_status(status) or "unrecognized"
    return "status:" + token.replace(" ", "-").replace("_", "-")


def record_labels(record: InventoryRecord, trial: bool) -> tuple[str, ...]:
    """Source status (or the reviewed current status, where the source changed after the baseline), product and kind; source or
    default priority; the operator's Medium and NA defaults and the plan's unassigned handler."""
    current = record.status_current["status"] if isinstance(record.status_current, Mapping) else record.status
    labels = {
        status_label(current),
        f"priority:{(record.priority or DEFAULT_PRIORITY).lower()}",
        "difficulty:medium",
        "estimate:na",
        "handler:unassigned",
        f"product:{record.product}",
        f"kind:{record.kind}",
    }
    if trial:
        labels.add(TRIAL_LABEL)
    return tuple(sorted(labels))


@dataclass(frozen=True)
class IssueDraft:
    record_id: str
    marker: str
    title: str
    body: str
    labels: tuple[str, ...]
    parent: str | None
    priority_basis: str


def quote_block(text: str) -> str:
    """``text`` as a Markdown block quote: every line, blank ones included, keeps its exact content after ``> ``."""
    return "\n".join(f"> {line}" if line else ">" for line in text.split("\n"))


def render_body(
    record: InventoryRecord,
    claimed: Sequence[SourceUnit],
    lines: Mapping[str, Sequence[str]],
    inventory: Inventory,
    basis: str,
    trial: bool,
) -> str:
    """Marker, provenance, metadata basis, an adopted pilot's kept passages and every claimed unit quoted exactly from
    the pinned source."""
    commit = inventory.baseline_commit
    short = commit[:7]
    aliases = [alias for alias in record.aliases if alias != record.id]
    # The fact names the status; the source's whole statement, which may wrap over lines, is quoted below it.
    stated = any(_clean(unit.stated_status) == record.status for unit in claimed)
    status = (
        f"- **Source status at baseline `{short}`:** {status_token(record.status)} ("
        + ("the leading status of the source quoted below; " if stated else "")
        + "historical: this issue's state and labels carry the current status)"
    )
    if record.status_disposition:
        status += f". Synthesized: {record.status_disposition}"
    # Current priority, difficulty, estimate and handler live only in labels; the body records the migration's basis.
    priority = (record.priority or DEFAULT_PRIORITY).title()
    basis_text = {
        "source": f"priority {priority} from the source",
        "default": f"no source priority (the migration default is {DEFAULT_PRIORITY.title()})",
    }.get(basis) or f"priority {priority} by reviewed disposition: {record.priority_disposition}"
    facts = [
        f"- **Source record:** `{record.id}`" + (f" (also {', '.join(f'`{alias}`' for alias in aliases)})" if aliases else ""),
        status,
        f"- **Migration basis** (historical; this issue's state and labels carry the current values): {basis_text};"
        " the source states no difficulty, planned estimate or handler (the migration defaults are Medium, NA and unassigned).",
    ]
    if record.severity:
        facts.append(f"- **Source severity:** {record.severity} (historical; separate from scheduling priority).")
    if record.parent:
        owner = next((other for other in inventory.records if other.id == record.parent), None)
        if owner is not None and owner.kind == "candidate":
            # A candidate is a source sub-record that has no issue of its own, so no native parent is bound to it.
            facts.append(
                f"- **Source owner (historical):** `{record.parent}`. This source ownership does not by itself establish a GitHub parent link."
            )
        else:
            facts.append(
                f"- **Source owner:** `{record.parent}` (bound as the native parent at migration; the native link carries the current one)."
            )
    if record.related:
        facts.append(f"- **Related:** {', '.join(f'`{related}`' for related in record.related)}.")
    if record.duplicate_rationale:
        facts.append(f"- **Merged source records:** {record.duplicate_rationale}")
    if record.status_conflict_disposition:
        facts.append(f"- **Conflicting source statuses:** {record.status_conflict_disposition}")
    if record.reviewed:
        facts.append(f"- **Reviewed note:** {record.review_note}")
    out = [marker_comment(source_marker(record.id)), ""]
    if trial:
        out += [TRIAL_BANNER, ""]
    out += [
        "Generated from the reviewed migration inventory (`reports/github-work-tracking-migration.json`) by"
        " `tools/github_work_tracking.py`; published by Claude through the operator's GitHub account. Agent signatures"
        " identify authorship only and carry no operator authority.",
        "",
        *facts,
        "",
    ]
    if record.retained:
        out += [
            "## Reviewed pilot passages",
            "",
            "Kept from the reviewed pilot body that this generated body replaces, quoted exactly with their published link"
            " targets. Historical: this issue's state and labels carry the current status.",
            "",
        ]
        for passage in record.retained:
            out += [quote_block(passage), ""]
    out += [
        f"## Source at baseline `{short}`",
        "",
        "Quoted exactly from the pinned source; only relative and in-page link targets are rewritten as permalinks at that commit.",
        "",
    ]
    for unit in claimed:
        first, last, text = _unit_span(unit, lines[unit.source])
        path = inventory.source_paths[unit.source]
        span = f"L{first}" if first == last else f"L{first}-L{last}"
        out += [f"**`{path}` line {unit.line}** ([at baseline]({blob_url(path, commit)}?plain=1#{span}))", ""]
        out += [normalize_links("\n".join(text), path, commit), ""]
    if record.quotes:
        out += [
            f"## Reviewed context at baseline `{short}`",
            "",
            "Further passages reviewed for this record, quoted exactly from the pinned files; only relative and in-page link"
            " targets are rewritten as permalinks at that commit.",
            "",
        ]
        for source, selector, quoted in record.quotes:
            first, last = quote_span(lines[source], selector, quoted)
            path = inventory.context_paths[source]
            span = f"L{first}" if first == last else f"L{first}-L{last}"
            out += [f"**`{path}` line {first}** ([at baseline]({blob_url(path, commit)}?plain=1#{span}))", ""]
            out += [normalize_links("\n".join(lines[source][first - 1 : last]), path, commit), ""]
    for update in record.source_updates:
        later, where, line = update["commit"], update["path"], update["line"]
        out += [
            f"## Historical source update, {update['date']} (`{later[:7]}`)",
            "",
            "The pinned source above is the baseline. This passage is the same record's text at that later commit, quoted exactly; it is"
            " history, not a live status: this issue's state and labels carry the current status.",
            "",
            f"**`{where}` line {line}** ([at {later[:7]}]({blob_url(where, later)}?plain=1#L{line}))",
            "",
            quote_block(normalize_links(update["text"], where, later)),
            "",
        ]
    out.append(end_marker_comment(source_marker(record.id)))
    return "\n".join(out) + "\n"


def draft_issues(inventory: Inventory, sources: Mapping[str, bytes], trial: bool = True) -> list[IssueDraft]:
    """One draft per migrating record with source units; an existing external issue is reused, never redrafted.

    ``sources`` holds every file in ``inventory.read_paths``; only the coverage sources hold units.
    """
    texts = {name: data.decode("utf-8") for name, data in sources.items()}
    units = {unit.key: unit for name, text in texts.items() if name in inventory.source_paths for unit in scan_source(name, text).units}
    lines = {name: text.splitlines() for name, text in texts.items()}
    drafts = []
    for record in inventory.records:
        if record.disposition != "migrate" or record.kind == "external-issue":
            continue
        claimed = [units[key] for key in record.units]
        basis = priority_basis(record, claimed)
        body = render_body(record, claimed, lines, inventory, basis, trial)
        drafts.append(
            IssueDraft(record.id, source_marker(record.id), record.title, body, record_labels(record, trial), record.parent, basis)
        )
    return drafts


# ---- the plan: every operation, found conflicts first ----


@dataclass(frozen=True)
class IssueRef:
    number: int
    id: int


@dataclass(frozen=True)
class Operation:
    op: str  # "create-label" | "create-issue" | "update-issue" | "bind-sub-issue"
    target: str
    payload: Mapping[str, Any]
    issue: int | None = None
    expected_fingerprint: str | None = None

    @property
    def payload_sha256(self) -> str:
        return _sha256(_canonical(self.payload))


OPERATION_KINDS = ("create-label", "create-issue", "update-issue", "bind-sub-issue")


@dataclass(frozen=True)
class MigrationBatch:
    repo: str
    baseline_commit: str
    trial: bool
    operations: tuple[Operation, ...]
    conflicts: tuple[str, ...]
    reused: Mapping[str, IssueRef]
    scope: tuple[str, ...] | None = None  # the records a scoped plan is about; recorded in the batch only when one was given

    @property
    def ok(self) -> bool:
        return not self.conflicts

    @property
    def budget(self) -> dict[str, int]:
        counts = Counter(operation.op for operation in self.operations)
        reads = counts["update-issue"] + 2 * counts["bind-sub-issue"]
        return {**{kind: counts[kind] for kind in OPERATION_KINDS}, "writes": len(self.operations), "reads_around_writes": reads}

    def to_data(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "repo": self.repo,
            "baseline_commit": self.baseline_commit,
            "trial": self.trial,
            **({} if self.scope is None else {"scope": list(self.scope)}),
            "budget": self.budget,
            "conflicts": list(self.conflicts),
            "reused": {record_id: {"number": ref.number, "id": ref.id} for record_id, ref in self.reused.items()},
            "operations": [
                {
                    "op": operation.op,
                    "target": operation.target,
                    "issue": operation.issue,
                    "expected_fingerprint": operation.expected_fingerprint,
                    "payload_sha256": operation.payload_sha256,
                    "payload": dict(operation.payload),
                }
                for operation in self.operations
            ],
        }

    @property
    def sha256(self) -> str:
        return _sha256(render_batch(self))


def render_batch(batch: MigrationBatch) -> str:
    return json.dumps(batch.to_data(), indent=1, ensure_ascii=False) + "\n"


def _target_problem(label: str, number: int | None, issue: IssueSnapshot | None) -> str | None:
    if issue is None:
        return f"{label} targets #{number}, which does not exist (or is a pull request)"
    if issue.state != "open":
        return f"{label} targets #{number}, which is closed; the migration never reopens an issue"
    return None


def merged_labels(draft: IssueDraft, issue: IssueSnapshot) -> tuple[list[str], list[str]]:
    """The labels an update writes, and conflicts that stop it.

    Status, product, kind and the trial marker come from the draft. For priority, difficulty, estimate and handler an
    explicit value already on the issue survives a default; an explicit source priority must agree with it. Every
    label outside the managed namespaces survives untouched.
    """
    wanted = set(draft.labels)
    result = {label for label in issue.labels if not _managed(label)}
    result |= {label for label in wanted if label == TRIAL_LABEL or label.startswith(tuple(f"{d}:" for d in _SOURCE_DIMENSIONS))}
    conflicts = []
    where = f"record {draft.record_id!r} (#{issue.number})"
    for dimension in _DEFAULTED_DIMENSIONS:
        want = next(label for label in wanted if label.startswith(dimension + ":"))
        present = [label for label in issue.labels if _in_dimension(label, dimension)]
        if len(present) > 1:
            conflicts.append(f"{where} carries more than one {dimension} label {present}")
        elif present and not _valid_label(present[0]):
            conflicts.append(f"{where} carries {present[0]!r}, which is not a known {dimension} value")
        elif present and dimension == "priority" and draft.priority_basis != "default" and present[0] != want:
            conflicts.append(
                f"{where} carries {present[0]!r}, but its {draft.priority_basis} priority is {want!r}; resolve it before any write"
            )
        else:
            result.add(present[0] if present else want)
    return sorted(result), conflicts


def plan_migration(
    inventory: Inventory,
    drafts: Sequence[IssueDraft],
    issues: Sequence[IssueSnapshot],
    labels: Mapping[str, LabelSpec],
    selected: frozenset[str] | None = None,
    scope: frozenset[str] | None = None,
) -> MigrationBatch:
    """Every write a publication needs, in order (labels, issues, bindings), and every conflict that forbids it.

    With ``selected`` (``--only``), the writes are the selected records' own: the missing labels they carry, their
    creates and updates, and each binding with a selected end once both its issues exist. A record outside the
    selection whose source marker is on one issue is an earlier batch's identity. Conflicts are still found across the
    whole repository and inventory.

    With ``scope`` (``--scope``), the plan is about exactly those records: a record outside it is neither planned nor
    judged, and the batch records the scope. Source markers are still checked across the whole repository, and an issue of
    an outside record is never written; it is only read, to resolve the native parent of a scoped child.
    """
    conflicts: list[str] = []
    selection = selected if selected is not None else scope

    def chosen(record_id: str) -> bool:
        return selection is None or record_id in selection

    drafts_by_id = {draft.record_id: draft for draft in drafts}  # every draft: a scoped child's parent may lie outside the scope
    owners = {draft.marker: draft.record_id for draft in drafts}  # every marker: a foreign or repeated one is a defect anywhere
    by_number = {issue.number: issue for issue in issues}
    hits: dict[str, list[int]] = defaultdict(list)
    for issue in issues:
        for marker in issue.markers:
            hits[marker].append(issue.number)
    for marker, numbers in sorted(hits.items()):
        if marker not in owners:
            conflicts.append(f"issue(s) {_issue_list(numbers)} carry source marker {marker!r}, which no migrating record owns")
        elif len(numbers) > 1:
            conflicts.append(f"source marker {marker!r} of {owners[marker]!r} is on more than one issue: {_issue_list(numbers)}")
    known: dict[str, IssueRef] = {}  # an outside record's existing issue, read to resolve a scoped child's parent
    if scope is not None:
        for record in inventory.records:
            if record.disposition == "migrate" and record.id not in scope:
                draft = drafts_by_id.get(record.id)
                marked = hits.get(draft.marker, []) if draft else []
                number = marked[0] if len(marked) == 1 else record.target_issue
                if number in by_number:
                    known[record.id] = IssueRef(by_number[number].number, by_number[number].id)
        drafts = [draft for draft in drafts if draft.record_id in scope]
    for draft in drafts:
        if not 0 < len(draft.title) <= TITLE_LIMIT or len(draft.body) > BODY_LIMIT:
            conflicts.append(
                f"record {draft.record_id!r} title ({len(draft.title)}) or body ({len(draft.body)}) is outside GitHub's limits"
            )
        starts, ends = _MARKER.findall(draft.body), _END_MARKER.findall(draft.body)
        if starts != [draft.marker] or ends != [draft.marker]:  # a marker quoted from the source would corrupt identity
            conflicts.append(
                f"record {draft.record_id!r} body carries source markers {starts} and region ends {ends};"
                f" it must carry exactly its own markers {draft.marker!r}"
            )

    label_ops = []
    needed = {label for draft in drafts if chosen(draft.record_id) for label in draft.labels}
    for name in sorted({label for draft in drafts for label in draft.labels}):
        spec = LABEL_SPECS.get(name)
        existing = labels.get(name.lower())
        if spec is None:
            conflicts.append(f"label {name!r} has no reviewed specification")
        elif existing is None:
            if name in needed:  # created by the first batch whose records carry it
                label_ops.append(Operation("create-label", name, {"name": name, **spec.payload()}))
        elif existing != spec:
            conflicts.append(
                f"label {name!r} exists as {existing.name!r} with color {existing.color} and description"
                f" {existing.description!r}, not the reviewed {spec.color} and {spec.description!r}"
            )

    reused: dict[str, IssueRef] = {}
    issue_ops = []
    for record in inventory.records:
        if record.disposition != "migrate" or (scope is not None and record.id not in scope):
            continue
        label = f"record {record.id!r}"
        if record.kind == "external-issue":  # reusing an existing issue is its own reviewed operation, never a write here
            issue = by_number.get(record.target_issue) if record.target_issue is not None else None
            problem = _target_problem(label, record.target_issue, issue)
            if problem:
                conflicts.append(problem)
            elif issue is not None:
                reused[record.id] = IssueRef(issue.number, issue.id)
            continue
        draft = drafts_by_id.get(record.id)
        if draft is None:
            conflicts.append(f"{label} has no drafted issue")
            continue
        marked = hits.get(draft.marker, [])
        if record.target_issue is None:
            if len(marked) == 1 and not chosen(record.id):  # published by an earlier batch: an identity, never a write
                reused[record.id] = IssueRef(marked[0], by_number[marked[0]].id)
            elif marked:
                conflicts.append(
                    f"{label} has no reviewed target issue, but its source marker is on {_issue_list(marked)}; an earlier"
                    " write's outcome may be unknown: reconcile read-only and record the identity before any write"
                )
            elif chosen(record.id):
                payload = {"title": draft.title, "body": draft.body, "labels": list(draft.labels)}
                issue_ops.append(Operation("create-issue", record.id, payload))
            continue
        issue = by_number.get(record.target_issue)
        problem = _target_problem(label, record.target_issue, issue)
        if problem is None and issue is not None and draft.marker not in issue.markers:
            problem = f"{label} targets #{issue.number}, which does not carry its source marker {draft.marker!r}"
        if problem or issue is None:
            conflicts.append(str(problem))
            continue
        reused[record.id] = IssueRef(issue.number, issue.id)
        wanted, label_conflicts = merged_labels(draft, issue)
        conflicts.extend(label_conflicts)
        region = generated_region(issue.body, draft.marker)
        adoption = inventory.adoptions.get(record.id)
        legacy = issue.body.count(marker_comment(draft.marker)) == 1 and end_marker_comment(draft.marker) not in issue.body
        if isinstance(region, str) and not (legacy and adoption):
            conflicts.append(f"{label}: #{issue.number}: {region}")
            continue
        if isinstance(region, str):  # a pilot body with no region, adopted only in the exact state its review read
            if issue.fingerprint != adoption["fingerprint"]:
                conflicts.append(
                    f"{label}: #{issue.number} has no generated region and has changed since its reviewed adoption"
                    f" (fingerprint {issue.fingerprint[:12]}…, reviewed {str(adoption['fingerprint'])[:12]}…); review it again"
                )
                continue
            lacking = [str(index) for index, passage in enumerate(record.retained, 1) if passage not in issue.body]
            if lacking:
                conflicts.append(
                    f"{label}: #{issue.number}'s body lacks reviewed pilot passage {', '.join(lacking)}; a kept passage"
                    " quotes the adopted body exactly"
                )
                continue
            body = draft.body.rstrip("\n")  # the reviewed adoption replaces the whole body; its kept passages are quoted in it
        else:
            # An update rewrites only the generated region; the existing title and every line outside the region survive.
            body = issue.body[: region[0]] + draft.body.rstrip("\n") + issue.body[region[1] :]
        if chosen(record.id) and (issue.body, list(issue.labels)) != (body, wanted):
            payload = {"title": issue.title, "body": body, "labels": wanted}
            issue_ops.append(Operation("update-issue", record.id, payload, issue.number, issue.fingerprint))

    exists = set(reused) | {operation.target for operation in issue_ops if operation.op == "create-issue"}
    bind_ops = []
    for draft in drafts:
        ref = reused.get(draft.record_id)
        current = by_number[ref.number].parent if ref else None
        where = f"record {draft.record_id!r}"
        if draft.parent is None:
            if current is not None:
                conflicts.append(
                    f"{where} has no parent, but #{ref.number if ref else '?'} is a native sub-issue of #{current}; the migration never re-parents"
                )
            continue
        if draft.parent not in drafts_by_id:
            conflicts.append(f"{where} has parent {draft.parent!r}, which has no drafted issue")
            continue
        parent_ref = reused.get(draft.parent) or known.get(draft.parent)
        if current is not None:
            if parent_ref is None or current != parent_ref.number:
                conflicts.append(
                    f"{where}: #{ref.number if ref else '?'} is already a native sub-issue of #{current}; the migration never re-parents"
                )
            continue
        if draft.parent in known and chosen(draft.record_id):
            # The parent's issue exists outside the scope and the link is missing. A scope never writes to an outside issue, so
            # planning nothing here would report success for a state that reconcile rejects: refuse it instead.
            conflicts.append(
                f"{where}: its parent {draft.parent!r} (#{known[draft.parent].number}) lies outside the scope and the child has no native"
                " link to it; a scope binds only inside itself, so link it separately or widen the scope"
            )
            continue
        ends = {draft.record_id, draft.parent}
        if selection is not None and not (ends & selection and ends <= exists):
            continue  # it belongs to the batch that publishes the later of its two issues
        bind_ops.append(
            Operation("bind-sub-issue", f"{draft.record_id} <- {draft.parent}", {"child": draft.record_id, "parent": draft.parent})
        )

    trial = any(TRIAL_LABEL in draft.labels for draft in drafts)
    operations = tuple(label_ops + issue_ops + bind_ops)
    return MigrationBatch(
        REPO, inventory.baseline_commit, trial, operations, tuple(conflicts), reused, None if scope is None else tuple(sorted(scope))
    )


# ---- publication: journal, write, validate; stop without retry ----


class Journal:
    """Append-only JSON lines, flushed and fsynced per record before the next step, so a write's intent is on disk
    before the write is sent. It promises nothing after a process kill or a disk failure."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.records: list[dict[str, Any]] = []

    def write(self, step: str, **fields: Any) -> None:
        utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        record = {"schema": SCHEMA, "seq": len(self.records), "utc": utc, "step": step, **fields}
        self.records.append(record)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())


@dataclass(frozen=True)
class PublicationResult:
    outcome: str  # "pass" | "incomplete" (every write validated, required evidence missing) | "failed" | "unknown" | "refused"
    reason: str
    writes: int
    issues: Mapping[str, int]
    journal_ok: bool = True  # False when any journal record could not be written: the evidence is incomplete, never sealed


def _request(operation: Operation, refs: Mapping[str, IssueRef], repo: str) -> tuple[str, str, dict[str, Any]]:
    if operation.op == "create-label":
        return "POST", f"repos/{repo}/labels", dict(operation.payload)
    if operation.op == "create-issue":
        return "POST", f"repos/{repo}/issues", dict(operation.payload)
    if operation.op == "update-issue":
        return "PATCH", f"repos/{repo}/issues/{operation.issue}", dict(operation.payload)
    if operation.op == "bind-sub-issue":
        parent, child = refs[operation.payload["parent"]], refs[operation.payload["child"]]
        return "POST", f"repos/{repo}/issues/{parent.number}/sub_issues", {"sub_issue_id": child.id}
    raise ValueError(f"unknown operation {operation.op!r}")


def _result_problem(operation: Operation, payload: Mapping[str, Any], obj: Any, refs: Mapping[str, IssueRef]) -> str | None:
    """How a write's returned object differs from its request, or ``None``."""
    if not isinstance(obj, dict):
        return "the response is not an object"
    if operation.op == "create-label":
        got = (obj.get("name"), str(obj.get("color", "")).lower(), obj.get("description") or "")
        want = (payload["name"], payload["color"], payload["description"])
        return None if got == want else f"label {got} is not {want}"
    if operation.op == "bind-sub-issue":  # GitHub answers with the parent issue
        parent = refs[operation.payload["parent"]].number
        return None if obj.get("number") == parent else f"the binding answered for #{obj.get('number')}, not #{parent}"
    try:
        issue = issue_snapshot(obj)
    except ReadFailed as error:
        return str(error)
    checks = (
        ("number", operation.op != "update-issue" or issue.number == operation.issue),
        ("title", issue.title == payload["title"]),
        ("body", issue.body == payload["body"]),
        ("labels", list(issue.labels) == sorted(payload["labels"])),
        ("state", issue.state == "open"),
    )
    return ", ".join(name for name, ok in checks if not ok) or None


def _binding_problem(client: GitHubClient, repo: str, parent: int, child: int) -> str | None:
    """A binding counts only when the child names the parent and the parent lists the child."""
    try:
        found: int | None = issue_snapshot(_json(client.get(f"repos/{repo}/issues/{child}/parent"))).number
    except TransportError as error:
        if error.status != 404:
            raise
        found = None
    if found != parent:
        return f"#{child}'s native parent is {f'#{found}' if found else 'missing'}, not #{parent}"
    children = [issue_snapshot(raw).number for raw in read_pages(client, f"repos/{repo}/issues/{parent}/sub_issues")]
    if child not in children:
        return f"#{parent}'s sub-issues {_issue_list(children)} do not include #{child}"
    return None


def publish_batch(
    batch: MigrationBatch, client: GitHubClient, journal: Journal, pause: Callable[[], None] | None = None
) -> PublicationResult:
    """Apply a conflict-free batch in order; stop at the first failed, mismatched or unknown write, never retrying.

    Every way out attempts an outcome record. A failure of any kind before a write is sent means nothing was written
    for that operation (``failed``); a failure of any kind once it has been sent leaves its outcome ``unknown``. A
    journal that cannot be written stops the run, and the result says so (``journal_ok``). When the outcome record
    itself cannot be written, the reason says so; a run whose writes all validated is then ``incomplete``, never
    ``pass``, and any other outcome keeps its classification.
    """
    repo = batch.repo
    wait = pause or (lambda: time.sleep(WRITE_PAUSE_S))
    refs = dict(batch.reused)
    writes = 0
    journal_ok = True

    def record(step: str, **fields: Any) -> bool:
        """Journal one record; ``False`` when this record could not be written, which ``journal_ok`` then keeps."""
        nonlocal journal_ok
        try:
            journal.write(step, **fields)
        except Exception:  # noqa: BLE001 - the evidence store itself failed: stop, and never claim a seal
            journal_ok = False
            return False
        return True

    def finish(outcome: str, reason: str) -> PublicationResult:
        issues = {record_id: ref.number for record_id, ref in refs.items()}
        if not record("outcome", outcome=outcome, reason=reason, writes=writes, issues=issues):
            reason = f"{reason}; the final outcome could not be journaled, so the evidence is incomplete"
            if outcome == "pass":
                outcome = "incomplete"
        return PublicationResult(outcome, reason, writes, issues, journal_ok)

    if not record("start", batch_sha256=batch.sha256, operations=len(batch.operations), conflicts=len(batch.conflicts), trial=batch.trial):
        return finish("failed", "the journal could not be written; nothing was written")
    if batch.conflicts:
        return finish("refused", f"the batch has {len(batch.conflicts)} conflict(s); nothing is written")
    for index, operation in enumerate(batch.operations):
        label = f"{operation.op} {operation.target}"
        try:  # before the write: any failure here means nothing was sent for this operation
            method, path, payload = _request(operation, refs, repo)
            if operation.op == "update-issue":
                current = issue_snapshot(_json(client.get(f"repos/{repo}/issues/{operation.issue}")))
                if current.fingerprint != operation.expected_fingerprint:
                    return finish(
                        "failed",
                        f"#{operation.issue} changed after the plan read it (a concurrent body or label edit); its update is not sent",
                    )
            if writes:
                wait()
        except Exception as error:  # noqa: BLE001 - classified by stage, never retried
            return finish("failed", f"{label}: {type(error).__name__} before the write ({error}); nothing was written for it")
        intent = {"method": method, "endpoint": path, "payload_sha256": operation.payload_sha256}
        if not record("intent", index=index, op=operation.op, target=operation.target, **intent):
            return finish("failed", f"{label}: its intent could not be journaled, so the write was not sent")
        writes += 1
        try:  # once the write is sent, any failure leaves its outcome unknown
            obj = _json(client.send(method, path, payload))
            number, issue_id = (obj.get("number"), obj.get("id")) if isinstance(obj, dict) else (None, None)
            if operation.op == "create-issue" and isinstance(number, int) and isinstance(issue_id, int):
                refs[operation.target] = IssueRef(number, issue_id)  # kept even when the result then fails validation
            if not record("result", index=index, op=operation.op, target=operation.target, number=number, id=issue_id):
                return finish("unknown", f"{label}: its result could not be journaled; it is not retried")
            problem = _result_problem(operation, payload, obj, refs)
            if problem is None and operation.op == "bind-sub-issue":
                problem = _binding_problem(client, repo, refs[operation.payload["parent"]].number, refs[operation.payload["child"]].number)
        except Exception as error:  # noqa: BLE001 - classified by stage, never retried
            reason = f"{label}: {type(error).__name__} after the write was sent ({error}); its outcome is unknown and it is not retried"
            return finish("unknown", reason)
        if problem:
            return finish("failed", f"{label}: the result differs from the request ({problem}); no further write")
        if not record("validated", index=index, op=operation.op, target=operation.target):
            return finish("failed", f"{label}: validated, but the journal could not record it; no further write")
    return finish("pass", f"{writes} write(s) applied and validated")


# ---- reconciliation: read-only, exact coverage ----


@dataclass(frozen=True)
class ReconciliationReport:
    problems: tuple[str, ...]
    mapping: Mapping[str, int]
    # A scoped run only: each observed issue the scope does not map (never checked, never written), with the record that owns
    # it by reviewed target or source marker, or ``None``.
    untouched: Mapping[int, str | None] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


def _label_problems(draft: IssueDraft, issue: IssueSnapshot) -> list[str]:
    where = f"record {draft.record_id!r}: #{issue.number}"
    problems = []
    for dimension in _SOURCE_DIMENSIONS:
        got = sorted(label for label in issue.labels if _in_dimension(label, dimension))
        want = sorted(label for label in draft.labels if _in_dimension(label, dimension))
        if got != want:
            problems.append(f"{where} {dimension} labels {got} are not {want}")
    if (TRIAL_LABEL in issue.labels) != (TRIAL_LABEL in draft.labels):
        problems.append(f"{where} {'lacks' if TRIAL_LABEL in draft.labels else 'still carries'} the {TRIAL_LABEL} label")
    for dimension in _DEFAULTED_DIMENSIONS:
        got = [label for label in issue.labels if _in_dimension(label, dimension)]
        want = next(label for label in draft.labels if label.startswith(dimension + ":"))
        if len(got) != 1 or not _valid_label(got[0]):
            problems.append(f"{where} needs exactly one valid {dimension} label, not {got}")
        elif dimension == "priority" and draft.priority_basis != "default" and got[0] != want:
            problems.append(f"{where} carries {got[0]!r}, not its {draft.priority_basis} priority {want!r}")
    return problems


def reconcile(
    inventory: Inventory,
    drafts: Sequence[IssueDraft],
    observed: Sequence[IssueSnapshot],
    selected: frozenset[str] | None = None,
    scope: frozenset[str] | None = None,
) -> ReconciliationReport:
    """Each migrating record maps to exactly one open issue whose generated region, labels, native parent and (for a
    created issue) title match its draft.

    With ``selected`` (``--only``), a record outside the selection may have no issue yet. Every issue that exists is
    still checked in full, and source markers are checked across the whole repository.

    With ``scope`` (``--scope``), the verdict is about exactly those records, which are checked as usual. A record outside
    it is neither required nor judged, and its issues are reported as untouched. Source markers are scanned across the whole
    repository regardless: a marker no record owns, or one on several issues, fails even when its record is outside the scope.
    """
    problems: list[str] = []
    drafts_by_id = {draft.record_id: draft for draft in drafts}
    owners = {draft.marker: draft.record_id for draft in drafts}
    by_number = {issue.number: issue for issue in observed}
    hits: dict[str, list[IssueSnapshot]] = defaultdict(list)
    for issue in observed:
        for marker in issue.markers:
            hits[marker].append(issue)
    for marker, issues in sorted(hits.items()):
        if marker not in owners:
            problems.append(
                f"{_issue_list(issue.number for issue in issues)} carry source marker {marker!r}, which no migrating record owns"
            )
        elif scope is not None and len(issues) > 1 and owners[marker] not in scope:  # a scoped record's duplicate is found below
            problems.append(
                f"record {owners[marker]!r} source marker is on more than one issue: {_issue_list(issue.number for issue in issues)}"
            )
    known: dict[str, int] = {}  # an outside record's existing issue, to resolve a scoped child's native parent
    mapping: dict[str, int] = {}
    for record in inventory.records:
        if record.disposition != "migrate":
            continue
        if scope is not None and record.id not in scope:
            draft = drafts_by_id.get(record.id)
            marked = hits.get(draft.marker, []) if draft else []
            number = marked[0].number if len(marked) == 1 else record.target_issue
            if number in by_number:
                known[record.id] = number
            continue
        label = f"record {record.id!r}"
        if record.kind == "external-issue":
            issue = by_number.get(record.target_issue) if record.target_issue is not None else None
            problem = _target_problem(label, record.target_issue, issue)
            if problem:
                problems.append(problem)
            elif issue is not None:
                mapping[record.id] = issue.number
            continue
        draft = drafts_by_id.get(record.id)
        if draft is None:
            problems.append(f"{label} has no drafted issue")
            continue
        found = hits.get(draft.marker, [])
        if len(found) != 1:
            if found or selected is None or record.id in selected:
                problems.append(
                    f"{label} source marker is on more than one issue: {_issue_list(issue.number for issue in found)}"
                    if found
                    else f"{label} has no issue carrying its source marker {draft.marker!r}"
                )
            continue
        issue = found[0]
        mapping[record.id] = issue.number
        if record.target_issue is not None and issue.number != record.target_issue:
            problems.append(f"{label} maps to #{issue.number}, not its reviewed target #{record.target_issue}")
        if issue.state != "open":
            problems.append(f"{label}: #{issue.number} is closed during the migration")
        if record.target_issue is None and issue.title != draft.title:  # a reused issue keeps its own reviewed title
            problems.append(f"{label}: #{issue.number} title differs from the draft")
        region = generated_region(issue.body, draft.marker)
        if isinstance(region, str):
            problems.append(f"{label}: #{issue.number}: {region}")
        elif issue.body[region[0] : region[1]] != draft.body.rstrip("\n"):
            problems.append(f"{label}: #{issue.number} body's generated region differs from the draft")
        problems.extend(_label_problems(draft, issue))
    for draft in drafts:
        number = mapping.get(draft.record_id)
        if number is None:
            continue
        expected = (mapping.get(draft.parent) or known.get(draft.parent)) if draft.parent else None
        actual = by_number[number].parent
        if actual != expected:
            problems.append(
                f"record {draft.record_id!r}: #{number}'s native parent is {f'#{actual}' if actual else 'none'}, not {f'#{expected}' if expected else 'none'}"
            )
    shared = [number for number, count in Counter(mapping.values()).items() if count > 1]
    if shared:
        problems.append(f"{_issue_list(shared)} are mapped by more than one record")
    untouched: dict[int, str | None] = {}
    if scope is not None:
        owner_of: dict[int, str] = {}
        for record in inventory.records:
            if record.disposition == "migrate" and record.target_issue is not None:
                owner_of.setdefault(record.target_issue, record.id)
        for marker, issues in hits.items():
            for issue in issues:
                if marker in owners:
                    owner_of.setdefault(issue.number, owners[marker])
        mapped = set(mapping.values())
        untouched = {
            issue.number: owner_of.get(issue.number) for issue in sorted(observed, key=lambda i: i.number) if issue.number not in mapped
        }
    return ReconciliationReport(tuple(problems), mapping, untouched)


# ==== Task 4: offline governance gates ====
#
# After the cutover, issues own current status. These checks read only the repository and the sealed manifest, never
# GitHub: every docs-root plan has one issue identity, every source record is classified and mapped once, the pool's
# inbound anchors still resolve, frozen approval bytes are unchanged, and the pool is an authority stub, not a board.

TRACKING_HEADER = re.compile(r"^\*\*Tracking issue:\*\* (?P<url>\S+)\s*$")
_ISSUE_URL = re.compile(rf"https://github\.com/{re.escape(REPO)}/issues/(?P<number>[1-9]\d*)")
_ISSUE_SHORT = re.compile(rf"{re.escape(REPO)}#(?P<number>[1-9]\d*)")
_ISSUE_LINK = re.compile(rf"https://github\.com/{re.escape(REPO)}/issues/[1-9]\d*")
_PERMALINK = re.compile(rf"https://github\.com/{re.escape(REPO)}/blob/[0-9a-f]{{40}}/")
_HISTORY_PERMALINK = re.compile(rf"https://github\.com/{re.escape(REPO)}/blob/[0-9a-f]{{40}}/{re.escape(POOL_PATH)}")
_ISSUES_LIST_LINK = re.compile(rf"\]\(https://github\.com/{re.escape(REPO)}/issues(?:\?[^)]*)?\)")
_WORK_STATUS_LINK = re.compile(r"\]\([^)\s]*work-status\.html\)")
STUB_MAX_LINES = 150


def issue_reference(text: str) -> int:
    """The issue number of a repository-qualified reference: its full issue URL or ``owner/repo#number``."""
    match = _ISSUE_URL.fullmatch(text) or _ISSUE_SHORT.fullmatch(text)
    if match is None:
        raise ValueError(f"{text!r} is not an issue of {REPO}")
    return int(match.group("number"))


def visible_lines(text: str) -> list[str]:
    """The lines of Markdown ``text`` as a reader of the rendered page sees them: fenced code and HTML comments (an
    unclosed comment runs to the end) are blanked, so an example there never counts as a header or a declaration."""
    lines: list[str] = []
    fence: str | None = None
    comment = False
    for line in text.splitlines():
        if comment:
            end = line.find("-->")
            if end < 0:
                lines.append("")
                continue
            comment, line = False, line[end + 3 :]
        elif fence is not None:
            closing = _FENCE.match(line)
            if closing and closing.group("marker")[0] == fence[0] and len(closing.group("marker")) >= len(fence):
                fence = None if not line[closing.end() :].strip() else fence
            lines.append("")
            continue
        else:
            opening = _FENCE.match(line)
            if opening:
                fence = opening.group("marker")
                lines.append("")
                continue
        shown = []
        while (start := line.find("<!--")) >= 0:
            shown.append(line[:start])
            end = line.find("-->", start + 4)
            if end < 0:
                comment, line = True, ""
                break
            line = line[end + 3 :]
        lines.append("".join(shown) + line)
    return lines


def tracking_issue(text: str, path: str) -> int | None:
    """A plan's visible ``**Tracking issue:** <issue URL>`` header, or ``None`` when it has none; more than one is an
    error."""
    headers = [match.group("url") for match in map(TRACKING_HEADER.match, visible_lines(text)) if match]
    if len(headers) > 1:
        raise ValueError(f"{path} carries {len(headers)} tracking headers; a plan has exactly one")
    if not headers:
        return None
    match = _ISSUE_URL.fullmatch(headers[0])
    if match is None:
        raise ValueError(f"{path} tracking header {headers[0]!r} is not an issue of {REPO}")
    return int(match.group("number"))


def plan_identity_problems(plans: Mapping[str, bytes], inventory: Inventory) -> list[str]:
    """Each docs-root plan file has one issue identity: its own tracking header, the sealed baseline identity of its
    exact blob, or a reviewed exemption. A sealed plan keeps its sealed identity: a header there may repeat it, never
    replace it."""
    records = {record.id: record for record in inventory.records}
    problems = []
    for path, data in sorted(plans.items()):
        entry = inventory.plan_files.get(path)
        record = records.get(entry["record"]) if entry else None
        try:
            header = tracking_issue(data.decode("utf-8"), path)
        except ValueError as error:
            problems.append(str(error))
            continue
        if entry is not None and header is not None:
            sealed = record.target_issue if record else None
            if header != sealed:
                problems.append(
                    f"{path} carries a tracking header for #{header}, but its sealed baseline identity {entry['record']!r} is"
                    f" {f'#{sealed}' if sealed else 'not yet an issue'}; a sealed plan keeps its identity"
                )
            continue
        if header is not None or path in inventory.plan_exemptions:
            continue
        if entry is None:
            problems.append(f"{path} has no tracking header, no sealed baseline identity and no reviewed exemption")
        elif entry["blob"] != git_blob_id(data):
            problems.append(f"{path} changed since its sealed baseline identity; a changed plan carries its own tracking header")
        elif record is None or record.target_issue is None:
            problems.append(f"{path}'s baseline record {entry['record']!r} has no issue identity")
    return problems


def mapping_problems(inventory: Inventory) -> list[str]:
    """No source record is left unclassified: each migrates to an issue, is a duplicate of a migrating record, or retires
    with a reviewed rationale."""
    records = {record.id: record for record in inventory.records}
    problems = []
    for record in inventory.records:
        label = f"record {record.id!r}"
        if record.disposition == "migrate" and record.target_issue is None:
            problems.append(f"{label} migrates but has no issue identity")
        elif record.disposition in RETIRING_DISPOSITIONS and not (record.rationale.strip() or (record.terminal_disposition or "").strip()):
            problems.append(f"{label} retires ({record.disposition}) with no reviewed rationale")
        elif record.disposition == "duplicate":
            original = records.get(record.duplicate_of or "")
            if original is None or original.disposition != "migrate":
                problems.append(f"{label} is a duplicate of {record.duplicate_of!r}, which is not a migrating record")
    return problems


def coverage_problems(inventory: Inventory) -> list[str]:
    """Every source identity reaches one issue, and every compatibility anchor reaches a record or a pool section."""
    issues: dict[str, set[int]] = defaultdict(set)
    for record in inventory.records:
        if record.disposition == "migrate" and record.target_issue is not None:
            for identity in {record.id, *record.aliases}:
                issues[identity].add(record.target_issue)
    problems = [
        f"identity {identity!r} names more than one issue: {_issue_list(sorted(numbers))}"
        for identity, numbers in sorted(issues.items())
        if len(numbers) > 1
    ]
    ids = {record.id for record in inventory.records}
    for anchor, target in sorted(inventory.compat_anchors.items()):
        if target not in ids and not target.startswith("section:"):
            problems.append(f"compatibility anchor {anchor!r} points to unknown record {target!r}")
    return problems


def anchor_problems(stub: str, anchors: Iterable[str]) -> list[str]:
    """Each anchor resolves to exactly one heading of the pool, and its section links an issue or an exact historical
    permalink."""
    lines = stub.splitlines()
    headings = _headings(lines)
    slugs = [heading_anchor(title) for _number, _level, title in headings]
    problems = []
    for anchor in sorted(set(anchors)):
        if anchor != anchor.lower():
            problems.append(f"anchor {anchor!r} has uppercase letters, but GitHub heading anchors are lowercase; link {anchor.lower()!r}")
            continue
        count = slugs.count(anchor)
        if count == 0:
            problems.append(f"anchor {anchor!r} no longer resolves in the pool")
            continue
        if count > 1:
            problems.append(f"anchor {anchor!r} has more than one heading in the pool")
            continue
        index = slugs.index(anchor)
        first = headings[index][0]
        last = headings[index + 1][0] - 1 if index + 1 < len(headings) else len(lines)
        section = "\n".join(lines[first - 1 : last])
        if not (_ISSUE_LINK.search(section) or _PERMALINK.search(section)):
            problems.append(f"anchor {anchor!r} points nowhere: its section needs an issue link or an exact historical permalink")
    return problems


def inbound_pool_anchors(files: Mapping[str, str]) -> set[str]:
    """Every fragment any of ``files`` links on the live pool file.

    A permalink pinned to a commit (``/blob/<40 hex>/…``) resolves against the pool at that commit forever, so the stub
    need not keep its anchor; a branch or relative link follows the live file and must keep resolving."""
    pattern = re.compile(rf"(?P<pinned>/blob/[0-9a-f]{{40}}/[^\s)#]*?)?{re.escape(POOL_FILE)}#(?P<anchor>[A-Za-z0-9_-]+)")
    return {match["anchor"] for text in files.values() for match in pattern.finditer(text) if not match["pinned"]}


def frozen_problems(read: Callable[[str], bytes | None], inventory: Inventory) -> list[str]:
    """Each frozen approval artifact still has the exact bytes its sealed SHA-256 names (``read`` gives committed bytes).

    An artifact moved, byte for byte, into its directory's ``archive/`` (the repository's archive convention) is the
    same artifact.
    """
    problems = []
    for path, digest in sorted(inventory.frozen_artifacts.items()):
        archived = posixpath.join(posixpath.dirname(path), "archive", posixpath.basename(path))
        data = read(path)
        data = read(archived) if data is None else data
        if data is None:
            problems.append(f"frozen artifact {path} is missing")
        elif hashlib.sha256(data).hexdigest() != digest:
            problems.append(f"frozen artifact {path} changed: sha256 {hashlib.sha256(data).hexdigest()[:12]}…, sealed {digest[:12]}…")
    return problems


def stub_problems(text: str) -> list[str]:
    """The pool after the cutover: an authority statement, the live links and a history permalink; no board.

    Boards are found by their Markdown delimiter rows and status lines, which is what the generated stub could carry;
    an HTML ``<table>`` or a differently worded status line passes, so only a later hand edit could slip one in.
    """
    lines = text.splitlines()
    problems = []
    for number, line in enumerate(lines, 1):
        if _DELIMITER_ROW.match(line):
            problems.append(f"line {number}: the pool keeps a table; current status lives in issues")
        elif _STATUS_LINE.match(line) or _LOOSE_STATUS_LINE.match(line):
            problems.append(f"line {number}: the pool keeps a status line; current status lives in issues")
    if not _HISTORY_PERMALINK.search(text):
        problems.append("the pool has no commit-bound history permalink to its pre-cutover text")
    if not _WORK_STATUS_LINK.search(text):
        problems.append("the pool does not link the work status page")
    if not _ISSUES_LIST_LINK.search(text):
        problems.append("the pool does not link the GitHub issues list")
    if len(lines) > STUB_MAX_LINES:
        problems.append(f"the pool is {len(lines)} lines; the authority stub keeps at most {STUB_MAX_LINES}")
    return problems


def finalize_inventory(data: Mapping, mapping: Mapping[str, int], scope: frozenset[str] | None = None) -> dict:
    """The manifest with each migrating record's issue from a sealed reconcile ``mapping`` (record id -> issue number).

    Every migrating record needs exactly one positive issue, an already reviewed target must agree, and no issue serves
    two records. The input is never changed.

    With ``scope``, the mapping must name exactly the scoped records: only their ``target_issue`` fields are written, every
    other record keeps what it has, and no scoped record may take an issue another record already targets.
    """
    final = copy.deepcopy(dict(data))
    records = {record["id"]: record for record in final["records"]}
    migrating = {record_id for record_id, record in records.items() if record["disposition"] == "migrate"}
    unknown = sorted(set(mapping) - migrating)
    if unknown:
        raise ValueError(f"the mapping names records that do not migrate: {unknown}")
    if scope is not None:
        if outside := sorted(set(mapping) - scope):
            raise ValueError(f"the mapping names records outside the scope: {outside}")
        if not_migrating := sorted(scope - migrating):
            raise ValueError(f"the scope names records that do not migrate: {not_migrating}")
    missing = sorted((migrating if scope is None else scope) - set(mapping))
    if missing:
        raise ValueError(f"migrating records without an issue in the mapping: {missing}")
    for record_id, number in mapping.items():
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise ValueError(f"record {record_id!r} maps to {number!r}, not a positive issue number")
        reviewed = records[record_id].get("target_issue")
        if reviewed is not None and reviewed != number:
            raise ValueError(f"record {record_id!r} maps to #{number}, but its reviewed target issue is #{reviewed}")
    shared = sorted(number for number, count in Counter(mapping.values()).items() if count > 1)
    if shared:
        raise ValueError(f"{_issue_list(shared)} map to more than one record")
    if scope is not None:
        taken = {
            record["target_issue"]: record_id
            for record_id, record in records.items()
            if record_id not in scope and record.get("target_issue")
        }
        for record_id, number in mapping.items():
            if number in taken:
                raise ValueError(f"record {record_id!r} maps to #{number}, which record {taken[number]!r} already targets")
    for record_id, number in mapping.items():
        records[record_id]["target_issue"] = number
    return final


# ==== Task 4: the cutover change set, rendered from a finalized manifest ====

_PLACEHOLDER = re.compile(r"\{\{issue:(?P<record>[^{}\s]+)\}\}(?!\w)")  # never glued to a following word
PLACEHOLDER_START = "{{issue:"
_PLACEHOLDER_LIKE = re.compile(r"\{\{\s*issue\s*:", re.IGNORECASE)  # any spacing or case: filled exactly, or refused


def _issue_of(record_id: str, records: Mapping[str, InventoryRecord]) -> int:
    """The issue of a migrating record in a finalized manifest."""
    record = records.get(record_id)
    if record is None:
        raise ValueError(f"unknown record {record_id!r}")
    if record.disposition != "migrate":
        raise ValueError(f"record {record_id!r} does not migrate ({record.disposition}), so it has no issue")
    if record.target_issue is None:
        raise ValueError(f"record {record_id!r} has no issue yet; finalize the manifest from the reconcile mapping first")
    return record.target_issue


def fill_issue_placeholders(text: str, inventory: Inventory) -> str:
    """Each ``{{issue:RECORD}}`` becomes that record's issue URL from a finalized manifest; none is left behind."""
    records = {record.id: record for record in inventory.records}
    filled = _PLACEHOLDER.sub(lambda match: f"https://github.com/{REPO}/issues/{_issue_of(match.group('record'), records)}", text)
    leftover = _PLACEHOLDER_LIKE.search(filled)
    if leftover:
        raise ValueError(f"malformed issue placeholder {filled[leftover.start() : leftover.start() + 40]!r}")
    return filled


def render_pool_stub(inventory: Inventory, pool: str, history_commit: str, anchors: Iterable[str], headings: Mapping[str, str]) -> str:
    """The pool after the cutover: the authority statement, the live links, a permalink to ``pool`` at
    ``history_commit``, and one heading per compatibility anchor that links its issue and its entry at that commit.

    ``pool`` must be the pool the manifest inventoried. An anchor's heading is the pool's own heading for it, or a
    reviewed heading from ``headings`` that reproduces it. The result passes the stub and anchor gates, or it is refused.
    """
    if git_blob_id(pool.encode("utf-8")) != inventory.source_blobs["pool"]:
        raise ValueError("this is not the pool the manifest inventoried; re-baseline the manifest before the cutover")
    found = _headings(pool.splitlines())
    pool_headings = {heading_anchor(title): title for _number, _level, title in found}
    entries = {f"pool:{number}": heading_anchor(title) for number, _level, title in found}  # a heading unit's anchor
    records = {record.id: record for record in inventory.records}
    history = blob_url(POOL_PATH, history_commit)
    issues = f"https://github.com/{REPO}/issues"
    sections = []
    for anchor in sorted(set(anchors)):
        target = inventory.compat_anchors.get(anchor)
        if target is None:
            raise ValueError(f"inbound anchor {anchor!r} has no reviewed target in the manifest's compat_anchors")
        if anchor in pool_headings:
            title = pool_headings[anchor]
        elif anchor not in headings:
            raise ValueError(f"anchor {anchor!r} has no heading in the pool and no reviewed heading")
        elif heading_anchor(headings[anchor]) != anchor:
            raise ValueError(f"reviewed heading {headings[anchor]!r} does not reproduce anchor {anchor!r}")
        else:
            title = headings[anchor]
        if target.startswith("section:"):
            sections.append(f"### {title}\n\nThe [section at the cutover]({history}#{target.removeprefix('section:')}).\n")
            continue
        record = records.get(target)
        if record is None:
            raise ValueError(f"anchor {anchor!r} points to unknown record {target!r}")
        # A reviewed heading links the record's own heading at the cutover, when it has one.
        fragment = anchor if anchor in pool_headings else next((entries[unit] for unit in record.units if unit in entries), None)
        at_cutover = f"[its entry at the cutover]({history}#{fragment})" if fragment else f"[the pool at the cutover]({history})"
        if record.disposition == "migrate":
            line = f"Tracked in [{record.id}]({issues}/{_issue_of(record.id, records)}); history: {at_cutover}."
        elif record.disposition == "duplicate":
            original = record.duplicate_of or ""
            line = f"A duplicate of {original}, tracked in [{original}]({issues}/{_issue_of(original, records)}); history: {at_cutover}."
        else:
            line = f"Retired at the cutover as {record.disposition}, not open work; history: {at_cutover}."
        sections.append(f"### {title}\n\n{line}\n")
    stub = (
        f"# {found[0][2]}\n\n"
        "This file no longer tracks work. GitHub issues are the sole live registry for every feature, defect, follow-up\n"
        f"and plan: [all issues]({issues}), [the plans]({issues}?q=is%3Aissue+label%3Akind%3Aplan) and the\n"
        "[work status page](../../work-status.html), which shows every issue as one live table.\n\n"
        f"The pool as it stood before the cutover is preserved at [commit `{history_commit[:12]}`]({history}).\n\n"
        "## Compatibility anchors\n\n"
        "Older documents link the headings below; each points to its issue, or to its entry before the cutover.\n\n" + "\n".join(sections)
    )
    problems = stub_problems(stub) + anchor_problems(stub, anchors)
    if problems:
        raise ValueError(f"the rendered stub fails its gates: {'; '.join(problems)}")
    return stub


def _checkout_files(root: Path) -> Iterator[tuple[str, bytes]]:
    """Every tracked file of the checkout at ``root`` (any type can link the pool), by repository-relative path.

    Repository truth is the Git index (``tools/tracked_repository_files.py``): stage a new document before rendering;
    untracked and ignored files are neither scanned nor filled."""
    from tools.tracked_repository_files import tracked_repository_files

    resolved = root.resolve()
    for path in tracked_repository_files(root, pathspecs=["."]):
        yield path.relative_to(resolved).as_posix(), path.read_bytes()


def cutover_docs(
    inventory: Inventory, root: Path, history_pool: bytes, history_commit: str, headings: Mapping[str, str]
) -> dict[str, bytes]:
    """The changed files of the cutover under ``root``: every tracked Markdown document with its issue placeholders
    filled, and the pool stub keeping every reviewed and inbound anchor. Nothing is written; any refusal raises before a caller
    writes anything.

    The checkout's pool must be the pool at ``history_commit`` (line endings aside, since a Windows checkout may
    convert them), so the history permalink preserves exactly the text the stub replaces.
    """
    if (root / POOL_PATH).read_bytes().replace(b"\r\n", b"\n") != history_pool.replace(b"\r\n", b"\n"):
        raise ValueError(f"{POOL_PATH} under {root} is not the pool at {history_commit}; render the cutover from that pool")
    anchors, changed = set(inventory.compat_anchors), {}
    for path, data in _checkout_files(root):  # the pool links none of its own anchors by file name
        anchors |= inbound_pool_anchors({path: data.decode("utf-8", "replace")})
        if path.endswith(".md") and _PLACEHOLDER_LIKE.search(data.decode("utf-8", "replace")):
            changed[path] = fill_issue_placeholders(data.decode("utf-8"), inventory).encode("utf-8")
    changed[POOL_PATH] = render_pool_stub(inventory, history_pool.decode("utf-8"), history_commit, anchors, headings).encode("utf-8")
    return changed


# ---- command line ----


def read_selection(paths: Sequence[Path] | None, inventory: Inventory) -> frozenset[str] | None:
    """The migrating records named in the ``--only`` files, one id per line; ``None`` (every record) without any."""
    if not paths:
        return None
    ids = [line.strip() for path in paths for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not ids:
        raise ValueError("the selection names no record")
    unknown = sorted(set(ids) - {record.id for record in inventory.records if record.disposition == "migrate"})
    if unknown:
        raise ValueError(f"the selection names records the inventory does not migrate: {unknown}")
    twice = sorted(record_id for record_id, count in Counter(ids).items() if count > 1)
    if twice:
        raise ValueError(f"the selection names {twice} more than once")
    return frozenset(ids)


def read_scope(path: Path | None, inventory: Inventory) -> frozenset[str] | None:
    """The records a scoped run is about, from one file of ids (one per line); ``None`` (every record) without a file.

    The scope is strict: an empty or blank-only file, a repeated id and an id the inventory does not migrate are refused, and
    a refusal never falls back to an unscoped run.
    """
    if path is None:
        return None
    ids = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not ids:
        raise ValueError("the scope names no record")
    unknown = sorted(set(ids) - {record.id for record in inventory.records if record.disposition == "migrate"})
    if unknown:
        raise ValueError(f"the scope names records the inventory does not migrate: {unknown}")
    twice = sorted(record_id for record_id, count in Counter(ids).items() if count > 1)
    if twice:
        raise ValueError(f"the scope names {twice} more than once")
    return frozenset(ids)


def _github_command(args: argparse.Namespace, reader: SourceReader, client: GitHubClient) -> int:
    """``plan`` and ``reconcile`` only read GitHub; ``publish`` writes only a reviewed batch that a fresh plan equals.
    ``--only`` selects records within the full inventory; ``--scope`` narrows the whole run to the records whose authority moves
    (``--only`` must then lie inside it), and a refused scope never falls back to an unscoped run."""
    if args.command == "publish" and not args.execute:
        print(json.dumps({"step": "STOP", "reason": "publish writes to GitHub only with --execute"}))
        return 2
    inventory = load_inventory(args.inventory)
    try:
        selected = read_selection(args.only, inventory)
        scope = read_scope(args.scope, inventory)
        if selected is not None and scope is not None and not selected <= scope:
            raise ValueError(f"the selection names records outside the scope: {sorted(selected - scope)}")
    except (OSError, ValueError) as error:  # an unreadable or unreviewable selection or scope is refused before any read
        print(json.dumps({"step": "STOP", "reason": str(error)}))
        return 2
    if selected is not None and getattr(args, "mapping_out", None) is not None:
        print(json.dumps({"step": "STOP", "reason": "a mapping is written only by a full reconcile, without --only"}))
        return 2
    sources = reader(inventory.baseline_commit, inventory.read_paths)
    report = validate_inventory(inventory, sources)
    update_problems = source_update_problems(inventory, reader)
    if not report.ok or update_problems:
        print(
            json.dumps(
                {"step": "STOP", "reason": f"the inventory has {len(report.problems) + len(update_problems)} problem(s); run validate"}
            )
        )
        return 2
    drafts = draft_issues(inventory, sources, trial=not args.final)
    try:
        issues, labels = read_issues(client), read_labels(client)
    except ReadFailed as error:
        print(json.dumps({"step": "STOP", "reason": str(error)}))
        return 2
    if args.command == "reconcile":
        result = reconcile(inventory, drafts, issues, selected, scope)
        for problem in result.problems:
            print(f"PROBLEM: {problem}")
        summary: dict[str, Any] = {"ok": result.ok, "problems": len(result.problems), "mapped": len(result.mapping)}
        if scope is not None:  # what the scope left alone is named, so the report never reads as "all issues checked"
            for number, owner in result.untouched.items():
                print(f"UNTOUCHED: #{number} ({owner or 'no migration record'})")
            summary |= {"scope": len(scope), "untouched": list(result.untouched)}
        print(json.dumps(summary))
        if result.ok and args.mapping_out is not None:  # a mapping is evidence only when every record reconciles
            args.mapping_out.write_bytes((json.dumps(dict(result.mapping), indent=2, sort_keys=True) + "\n").encode("utf-8"))
        return 0 if result.ok else 1
    batch = plan_migration(inventory, drafts, issues, labels, selected, scope)
    text = render_batch(batch).encode("utf-8")
    if args.command == "plan":
        args.out.write_bytes(text)
        for conflict in batch.conflicts:
            print(f"CONFLICT: {conflict}")
        print(json.dumps({"ok": batch.ok, "conflicts": len(batch.conflicts), "batch_sha256": batch.sha256, **batch.budget}))
        return 0 if batch.ok else 1
    reviewed = args.batch.read_bytes()
    if text != reviewed:
        print(json.dumps({"step": "STOP", "reason": "a fresh plan differs from the reviewed batch; plan and review again"}))
        return 2
    args.evidence_dir.mkdir(parents=True, exist_ok=False)
    (args.evidence_dir / "batch.json").write_bytes(reviewed)
    seconds = args.pause_seconds
    result = publish_batch(batch, client, Journal(args.evidence_dir / "journal.jsonl"), pause=lambda: time.sleep(seconds))
    sealed = result.journal_ok and _seal_evidence(args.evidence_dir)  # sealed last, after the outcome record
    outcome = "incomplete" if result.outcome == "pass" and not sealed else result.outcome  # a pass needs its seal
    summary = {"outcome": outcome, "reason": result.reason, "writes": result.writes, "issues": dict(result.issues), "sealed": sealed}
    if not sealed:
        summary["evidence"] = (
            "incomplete: the journal could not be written in full, so the evidence could not be sealed"
            if not result.journal_ok
            else "incomplete: the journal was written, but its evidence seal could not be written"
        )
    print(json.dumps(summary))
    return {"pass": 0, "failed": 1, "refused": 2, "unknown": 3, "incomplete": 4}[outcome]


def _seal_evidence(directory: Path) -> bool:
    """Write the digests of the reviewed batch and the journal; ``False`` (and no seal) when the storage fails."""
    try:
        names = ("batch.json", "journal.jsonl")
        seal = "".join(f"{hashlib.sha256((directory / name).read_bytes()).hexdigest()}  {name}\n" for name in names)
        (directory / "evidence.sha256").write_bytes(seal.encode("utf-8"))
    except OSError:
        return False
    return True


def _pause_seconds(text: str) -> float:
    """A pause between writes: a finite number of seconds from 0 to 60, checked before any request is made."""
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not (math.isfinite(value) and 0 <= value <= 60):
        raise argparse.ArgumentTypeError(f"--pause-seconds must be a finite number of seconds from 0 to 60, not {text!r}")
    return value


def main(argv: Sequence[str] | None = None, reader: SourceReader = read_sources_at, client: GitHubClient | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="check an inventory against the sources at its baseline commit")
    validate.add_argument("inventory", type=Path)
    draft = commands.add_parser("draft", help="derive the inventory from the sources at a commit (written to stdout)")
    draft.add_argument("commit")
    plan = commands.add_parser("plan", help="read GitHub and write every operation a publication would perform (no writes)")
    plan.add_argument("inventory", type=Path)
    plan.add_argument("--out", type=Path, required=True)
    publish = commands.add_parser("publish", help="apply a reviewed batch; a fresh plan must equal it byte for byte")
    publish.add_argument("inventory", type=Path)
    publish.add_argument("--batch", type=Path, required=True)
    publish.add_argument("--evidence-dir", type=Path, required=True)
    publish.add_argument("--execute", action="store_true", help="without it, nothing is written")
    publish.add_argument("--pause-seconds", type=_pause_seconds, default=WRITE_PAUSE_S)
    check = commands.add_parser("reconcile", help="read GitHub and check every migrating record's issue (no writes)")
    check.add_argument("inventory", type=Path)
    check.add_argument("--mapping-out", type=Path, help="when every record reconciles, write its record -> issue mapping")
    for command in (plan, publish, check):
        command.add_argument("--final", action="store_true", help="final copies: no trial label or banner")
        command.add_argument("--only", type=Path, action="append", help="a file of record ids, one per line, to act on (repeatable)")
        command.add_argument(
            "--scope",
            type=Path,
            help="a file of record ids, one per line: the run is about exactly these records and leaves every other issue untouched",
        )
    finalize = commands.add_parser("finalize", help="record each migrating record's issue from a reconcile mapping (offline)")
    finalize.add_argument("inventory", type=Path)
    finalize.add_argument("--mapping", type=Path, required=True)
    finalize.add_argument(
        "--scope", type=Path, help="a file of record ids: the mapping must name exactly these, and only their issues are recorded"
    )
    finalize.add_argument("--out", type=Path, required=True)
    cutover = commands.add_parser("cutover-docs", help="write the pool stub and fill issue placeholders from a finalized manifest")
    cutover.add_argument("inventory", type=Path)
    cutover.add_argument("--history-commit", required=True, help="the commit whose pool the stub's history permalink keeps")
    cutover.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)

    if args.command in ("plan", "publish", "reconcile"):
        return _github_command(args, reader, client or GhClient())

    if args.command == "finalize":
        try:
            mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
            if not isinstance(mapping, dict):
                raise ValueError("the mapping is not a JSON object of record ids to issue numbers")
            data = json.loads(args.inventory.read_text(encoding="utf-8"))
            scope = None  # only a scoped finalize loads the inventory, so an unscoped one judges nothing it did not before
            if args.scope is not None:
                try:
                    scope = read_scope(args.scope, inventory_from_data(data))
                except OSError as error:  # an unreadable scope is refused like any other bad scope
                    raise ValueError(f"the scope cannot be read: {type(error).__name__}") from None
            final = finalize_inventory(data, mapping, scope)
        except ValueError as error:
            print(json.dumps({"step": "STOP", "reason": str(error)}))
            return 2
        args.out.write_bytes(render_manifest(final).encode("utf-8"))
        return 0

    if args.command == "cutover-docs":
        from tools import github_work_tracking_rules as rules
        from tools.tracked_repository_files import TrackedFileInventoryError

        inventory = load_inventory(args.inventory)
        try:
            pool = reader(args.history_commit, {"pool": POOL_PATH})["pool"]
            changed = cutover_docs(inventory, args.root, pool, args.history_commit, rules.COMPAT_HEADINGS)
        except (ValueError, TrackedFileInventoryError) as error:  # no index to read is a refusal, not a crash
            print(json.dumps({"step": "STOP", "reason": str(error)}))
            return 2
        # Every check has passed; the files are then written one by one into the Git checkout. If a write fails part way,
        # `git status` lists the files already written and `git restore` undoes them.
        for path, data in changed.items():
            (args.root / path).write_bytes(data)
        print(json.dumps({"ok": True, "changed": sorted(changed)}))
        return 0

    if args.command == "draft":
        from tools import github_work_tracking_rules as rules

        sources = reader(args.commit, rules.READS)
        manifest = rules.draft_inventory(args.commit, sources, read_plans_at(args.commit))
        sys.stdout.buffer.write(render_manifest(manifest).encode("utf-8"))
        return 0

    inventory = load_inventory(args.inventory)
    report = validate_inventory(inventory, reader(inventory.baseline_commit, inventory.read_paths))
    problems = [*report.problems, *source_update_problems(inventory, reader)]
    for problem in problems:
        print(f"PROBLEM: {problem}")
    print(json.dumps({"ok": not problems, "problems": len(problems), **report.counts}, sort_keys=True))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
