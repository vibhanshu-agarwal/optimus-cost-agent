"""Plan 11.29: move open work from the consolidated backlog to GitHub Issues without losing any of it.

The migration is driven by a reviewed inventory (``reports/github-work-tracking-migration.json``). This module reads the
authority documents the inventory was built from and checks the inventory against them:

* every record-like *unit* in a source — a ``###`` entry, an identity-bearing table row, a section that carries its own
  ``**Status:**`` line, a frozen-artifact live-owner bullet — is claimed by exactly one inventory record, unless its whole
  section is classified as history/excluded/not-work and the unit itself is not unresolved work;
* every ``##`` section of every source has exactly one classification;
* a record that merges several identities, merges conflicting source statuses, or is marked a duplicate states why;
* a plan and an item are never merged into one record, because their acceptance surfaces differ;
* unresolved work is never retired without an explicit terminal disposition, and an accepted risk with outstanding
  mitigation is never excluded.

Unit keys are ``<source>:<line>`` against the exact source bytes, whose git blob ids the inventory pins.
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
from typing import Any

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

_IDENTITY = re.compile(
    r"(?P<id>P\d+(?:\.\d+)*-(?:FU|FEAT|REMEDIATION|UNRUN|CAND)-[A-Z0-9][A-Z0-9-]*"
    r"|P11\.26-[A-Z0-9-]+|MAIN-\d+|EVIDENCE-HANDOFF-[A-Z0-9-]+|HARDENING-[A-Z0-9-]+|T13-CAND-[A-Z0-9-]+"
    r"|Plan \d+(?:\.\d+)*)"
)
# A2A audit obligations are numbered `C1`…`M17`; such a code names a row only as its first cell, since other tables
# cite findings like "C15 precision" in passing.
_SHORT_OBLIGATION = re.compile(r"[CHM]\d+[a-z]?")
_STATUS_LINE = re.compile(r"^\*\*Status:\*\*\s*(?P<value>.+)$")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_DELIMITER_CELL = re.compile(r":?-{3,}:?")
_STATUS_TOKEN = re.compile(
    r"(accepted_open|unrun_binding|unrun|open|partially implemented|promoted|blocked|active|not drafted|in review|ready|closed|retired"
    r"|reviewed disposition)",
    re.IGNORECASE,
)


def git_blob_id(data: bytes) -> str:
    """Git's object id for ``data`` as a blob, so a pin can be checked with ``git rev-parse <rev>:<path>``."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def normalized_status(text: str | None) -> str | None:
    """The leading status token of a status cell or line (``Promoted -> [Plan 12.1](…)`` -> ``promoted``)."""
    if not text:
        return None
    match = _STATUS_TOKEN.search(re.sub(r"[`~*]", "", text))
    return match.group(1).lower() if match else None


@dataclass(frozen=True)
class SourceUnit:
    source: str
    section: str
    kind: str  # "entry" | "row" | "section-record" | "frozen-mapping"
    line: int
    identity: str | None
    stated_status: str | None
    struck: bool = False

    @property
    def key(self) -> str:
        return f"{self.source}:{self.line}"

    @property
    def unresolved(self) -> bool:
        if self.kind == "frozen-mapping":  # its text names a live owner, not a status
            return False
        return not self.struck and normalized_status(self.stated_status) in UNRESOLVED_STATUSES


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def source_sections(text: str) -> list[str]:
    """The ``##`` section titles of a Markdown source, outside fenced blocks."""
    titles, fenced = [], False
    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            titles.append(line[3:].strip())
    return titles


def source_units(source: str, text: str) -> list[SourceUnit]:
    """Every record-like unit of one source, in line order."""
    lines = text.splitlines()
    units: list[SourceUnit] = []
    section = ""
    section_line = 0
    section_has_entries = False
    section_status: str | None = None
    entry: dict[str, Any] | None = None
    header: list[str] | None = None
    fenced = False

    def close_entry() -> None:
        nonlocal entry
        if entry is not None:
            units.append(SourceUnit(source, section, "entry", entry["line"], entry["identity"], entry["status"]))
        entry = None

    def close_section() -> None:
        if section and not section_has_entries and section_status is not None:
            units.append(SourceUnit(source, section, "section-record", section_line, None, section_status))

    for number, line in enumerate(lines, 1):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.startswith("## "):
            close_entry()
            close_section()
            section, section_line, section_has_entries, section_status, header = line[3:].strip(), number, False, None, None
            continue
        if line.startswith("### "):
            close_entry()
            section_has_entries, header = True, None
            title = line[4:].strip()
            match = _IDENTITY.search(title)
            entry = {"line": number, "identity": match.group("id") if match else title, "status": None}
            continue
        status = _STATUS_LINE.match(line)
        if status:
            if entry is not None:
                entry["status"] = entry["status"] or status.group("value").strip()
            elif section_status is None:
                section_status = status.group("value").strip()
            continue
        if line.startswith("|"):
            cells = _cells(line)
            if header is None:
                header = cells
                continue
            if all(_DELIMITER_CELL.fullmatch(cell) for cell in cells if cell):
                continue
            first = cells[0].strip("`~* ")
            if _SHORT_OBLIGATION.fullmatch(first):
                identity = first
            else:
                identity = next((m.group("id") for cell in cells if (m := _IDENTITY.search(cell))), None)
            row = dict(zip(header, cells, strict=False))
            columns = {name.strip().lower(): value for name, value in row.items()}
            stated = columns.get("status") or columns.get("state") or columns.get("disposition")
            struck = cells[0].startswith("~~")
            units.append(SourceUnit(source, section, "row", number, identity or re.sub(r"[`~*\[\]]", "", cells[0])[:80], stated, struck))
            continue
        if not line.strip():
            header = None
            continue
        if line.startswith("- `docs/superpowers/") and "SHA-256" in line:
            owner = line.split("Live owner:", 1)[1].strip() if "Live owner:" in line else None
            units.append(SourceUnit(source, section, "frozen-mapping", number, line.split("`")[1], owner))
    close_entry()
    close_section()
    return units


@dataclass(frozen=True)
class SectionDisposition:
    source: str
    title: str
    classification: str
    rationale: str


@dataclass(frozen=True)
class InventoryRecord:
    id: str
    kind: str
    status: str | None
    disposition: str
    units: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    parent: str | None = None
    duplicate_of: str | None = None
    duplicate_rationale: str | None = None
    status_conflict_disposition: str | None = None
    terminal_disposition: str | None = None
    mitigation_outstanding: bool = False
    target_issue: int | None = None
    priority: str | None = None
    product: str = "optimus"
    rationale: str = ""


@dataclass(frozen=True)
class Inventory:
    schema: str
    baseline_commit: str
    source_blobs: Mapping[str, str]
    source_paths: Mapping[str, str]
    sections: tuple[SectionDisposition, ...]
    records: tuple[InventoryRecord, ...]


@dataclass(frozen=True)
class CoverageReport:
    problems: tuple[str, ...] = ()
    counts: Mapping[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


_RECORD_FIELDS = {name for name in InventoryRecord.__dataclass_fields__}


def load_inventory(path: Path) -> Inventory:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise ValueError(f"inventory schema is {data.get('schema')!r}, expected {SCHEMA!r}")
    records = []
    for raw in data["records"]:
        unknown = set(raw) - _RECORD_FIELDS
        if unknown:
            raise ValueError(f"record {raw.get('id')!r} has unknown fields {sorted(unknown)}")
        records.append(InventoryRecord(**{**raw, "units": tuple(raw["units"]), "aliases": tuple(raw.get("aliases", ()))}))
    sources = data["baseline"]["sources"]
    return Inventory(
        schema=data["schema"],
        baseline_commit=data["baseline"]["commit"],
        source_blobs={name: spec["blob"] for name, spec in sources.items()},
        source_paths={name: spec["path"] for name, spec in sources.items()},
        sections=tuple(SectionDisposition(**section) for section in data["sections"]),
        records=tuple(records),
    )


def validate_inventory(inventory: Inventory, sources: Mapping[str, bytes]) -> CoverageReport:
    problems: list[str] = []

    if set(sources) != set(inventory.source_blobs):
        problems.append(f"sources {sorted(sources)} differ from the baseline sources {sorted(inventory.source_blobs)}")
    for name, data in sources.items():
        if inventory.source_blobs.get(name) != git_blob_id(data):
            problems.append(f"source {name!r} is not the baseline blob {inventory.source_blobs.get(name)}; re-derive the inventory")

    texts = {name: data.decode("utf-8") for name, data in sources.items()}
    units = {unit.key: unit for name, text in texts.items() for unit in source_units(name, text)}

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
    actual_sections = {(name, title) for name, text in texts.items() for title in source_sections(text)}
    for source, title in sorted(actual_sections - set(classified)):
        problems.append(f"unclassified section {source}:{title!r}")
    for source, title in sorted(set(classified) - actual_sections):
        problems.append(f"classified section {source}:{title!r} does not exist in the source")

    records = {}
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
        section_retires = section is not None and section.classification in RETIRING_DISPOSITIONS
        if unit.unresolved or not section_retires:
            problems.append(f"unclaimed unit {key} ({unit.kind} {unit.identity!r} in {unit.section!r}, status {unit.stated_status!r})")

    for record in inventory.records:
        problems.extend(_record_problems(record, records, units))
    problems.extend(_parent_cycles(records))

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
    for reference in (record.parent, record.duplicate_of):
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


def git_blob_bytes(commit: str, path: str) -> bytes:
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=REPO_ROOT, check=True, capture_output=True).stdout


def read_sources_at(commit: str, paths: Mapping[str, str]) -> dict[str, bytes]:
    """Source bytes exactly as committed at ``commit``, never the working tree."""
    return {name: git_blob_bytes(commit, path) for name, path in paths.items()}


def main(argv: Sequence[str] | None = None, reader: SourceReader = read_sources_at) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="check an inventory against the sources at its baseline commit")
    validate.add_argument("inventory", type=Path)
    args = parser.parse_args(argv)

    inventory = load_inventory(args.inventory)
    report = validate_inventory(inventory, reader(inventory.baseline_commit, inventory.source_paths))
    for problem in report.problems:
        print(f"PROBLEM: {problem}")
    print(json.dumps({"ok": report.ok, "problems": len(report.problems), **report.counts}, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
