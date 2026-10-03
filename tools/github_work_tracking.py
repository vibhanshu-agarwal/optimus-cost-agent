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
  mitigation is never excluded; parents form no cycle and never hang an open item under a retired record.

Unit keys are ``<source>:<line>`` against the exact source bytes, whose git blob ids the inventory pins. The reviewed
drafting rules that produce the inventory live in ``tools.github_work_tracking_rules``; ``draft`` reproduces the
committed inventory from its baseline commit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

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
    terminal_disposition: str | None = None
    mitigation_outstanding: bool = False
    target_issue: int | None = None
    priority: str | None = None
    product: str = "optimus"
    reviewed: bool = False
    review_note: str | None = None
    rationale: str = ""


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


@dataclass(frozen=True)
class CoverageReport:
    problems: tuple[str, ...] = ()
    counts: Mapping[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


_RECORD_FIELDS = set(InventoryRecord.__dataclass_fields__)
_TUPLE_FIELDS = ("units", "aliases", "anchors", "related")


def inventory_from_data(data: Mapping) -> Inventory:
    if data.get("schema") != SCHEMA:
        raise ValueError(f"inventory schema is {data.get('schema')!r}, expected {SCHEMA!r}")
    records = []
    for raw in data["records"]:
        unknown = set(raw) - _RECORD_FIELDS
        if unknown:
            raise ValueError(f"record {raw.get('id')!r} has unknown fields {sorted(unknown)}")
        records.append(InventoryRecord(**{**raw, **{name: tuple(raw.get(name, ())) for name in _TUPLE_FIELDS}}))
    sources = data["baseline"]["sources"]
    return Inventory(
        schema=data["schema"],
        baseline_commit=data["baseline"]["commit"],
        source_blobs={name: spec["blob"] for name, spec in sources.items()},
        source_paths={name: spec["path"] for name, spec in sources.items()},
        sections=tuple(SectionDisposition(**section) for section in data["sections"]),
        records=tuple(records),
        compat_anchors=dict(data.get("compat_anchors", {})),
        reviewed_anomalies=dict(data.get("reviewed_anomalies", {})),
    )


def load_inventory(path: Path) -> Inventory:
    return inventory_from_data(json.loads(path.read_text(encoding="utf-8")))


def validate_inventory(inventory: Inventory, sources: Mapping[str, bytes]) -> CoverageReport:
    problems: list[str] = []

    if set(sources) != set(inventory.source_blobs):
        problems.append(f"sources {sorted(sources)} differ from the baseline sources {sorted(inventory.source_blobs)}")
    for name, data in sources.items():
        if inventory.source_blobs.get(name) != git_blob_id(data):
            problems.append(f"source {name!r} is not the baseline blob {inventory.source_blobs.get(name)}; re-derive the inventory")

    scans = {name: scan_source(name, data.decode("utf-8")) for name, data in sources.items()}
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

    aliases: dict[str, str] = {}
    for record in inventory.records:
        problems.extend(_record_problems(record, records, units))
        if record.disposition == "migrate":
            for alias in record.aliases:
                if alias in aliases and aliases[alias] != record.id:
                    problems.append(f"alias {alias!r} names both {aliases[alias]!r} and {record.id!r}")
                aliases[alias] = record.id
    problems.extend(_parent_cycles(records))
    for anchor, target in inventory.compat_anchors.items():
        if target not in records and not target.startswith("section:"):
            problems.append(f"compatibility anchor {anchor!r} points to unknown record {target!r}")

    counts = Counter(record.disposition for record in inventory.records)
    counts.update({"units": len(units), "records": len(records)})
    return CoverageReport(tuple(problems), dict(counts))


def _record_problems(record: InventoryRecord, records: Mapping[str, InventoryRecord], units: Mapping[str, SourceUnit]) -> list[str]:
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


def render_manifest(data: Mapping) -> str:
    """The manifest text: stable key order, LF, and each pinned id on one line with its inline secret-scan marker."""
    text = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    text = re.sub(r'\{\n\s+"path": (".*?"),\n\s+"blob": (".*?"),\n\s+"pin": (".*?")\n\s+\}', r'{"path": \1, "blob": \2, "pin": \3}', text)
    return re.sub(r'\n(\s+)"commit": (".*?"),\n\s+"commit_pin": (".*?"),', r'\n\1"commit": \2, "commit_pin": \3,', text)


def main(argv: Sequence[str] | None = None, reader: SourceReader = read_sources_at) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="check an inventory against the sources at its baseline commit")
    validate.add_argument("inventory", type=Path)
    draft = commands.add_parser("draft", help="derive the inventory from the sources at a commit (written to stdout)")
    draft.add_argument("commit")
    args = parser.parse_args(argv)

    if args.command == "draft":
        from tools import github_work_tracking_rules as rules

        sources = reader(args.commit, rules.SOURCES)
        sys.stdout.buffer.write(render_manifest(rules.draft_inventory(args.commit, sources)).encode("utf-8"))
        return 0

    inventory = load_inventory(args.inventory)
    report = validate_inventory(inventory, reader(inventory.baseline_commit, inventory.source_paths))
    for problem in report.problems:
        print(f"PROBLEM: {problem}")
    print(json.dumps({"ok": report.ok, "problems": len(report.problems), **report.counts}, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
