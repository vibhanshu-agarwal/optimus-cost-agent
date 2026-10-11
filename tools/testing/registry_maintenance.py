"""Operator-invoked maintenance of the pytest run-context registry. Test tooling only (Plan 11.30 Task 0).

Nothing here runs from a pytest session, a hook or CI. Every command is explicit:

- `inventory` (read-only) lists every registry entry with its digest, its recorded worktree, whether
  that worktree still exists and whether its root process has positively ended. It writes one new
  manifest naming the eligible class and that class's digest. It never moves anything.
- `archive` moves exactly the manifest's eligible entries to `registry/ended/`, and only when the
  operator passes the class digest the manifest states (the grant). Without `--execute` it is a dry
  run. Each entry is re-read and re-checked first; an entry whose bytes, worktree or end status
  changed is refused and stays in place.
- `verify` checks that every eligible entry of a manifest has exactly one receipt and an archived
  copy with the inventoried digest, and is gone from the registry.

An entry is eligible only when it is a conforming record filed under its own run ID, its recorded
worktree is absent, and its root process has positively ENDED (`run_context.process_end_status`).
A missing worktree alone, age or reported provenance is never enough. UNKNOWN, LIVE, malformed,
unreadable or misfiled entries stay in place. Nothing is deleted: a move is a hard link to the new
name followed by removal of the old one, so an existing destination is never overwritten, and an
interrupted move is reconciled from what is on disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.testing import run_context
from tools.testing import run_context_records as records

MANIFEST_SCHEMA = "test-run-registry-inventory-v1"
RECEIPT_SCHEMA = "test-run-registry-receipt-v1"
ENDED_FOLDER = "ended"
RECEIPTS = "receipts.jsonl"
EXIT_REFUSED = 3
EXIT_MISMATCH = 4
# A receipt is proof only when it is exactly the receipt this tool writes for that entry under that grant.
_RECEIPT_FIELDS = frozenset({
    "schema", "name", "sha256", "run_id", "source", "target", "end_status", "end_basis", "disposition", "class_digest", "utc",
})
_POSITIVE_ENDS = frozenset({"not_found", "replaced", "terminated", "proc_absent"})
_DISPOSITIONS = frozenset({"archived", "reconciled"})
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?\+00:00")


def _is_utc_time(text: str) -> bool:
    """The tool's own time form (`datetime.now(timezone.utc).isoformat()`), and a real UTC time."""
    if not text.isascii() or _UTC.fullmatch(text) is None:
        return False
    try:
        return datetime.fromisoformat(text).utcoffset() == timedelta(0)
    except ValueError:
        return False


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _entry(path: Path) -> dict[str, object]:
    """One registry entry as found now: digest, identity, worktree, end status and disposition."""
    try:
        data = path.read_bytes()
    except OSError:
        return {"name": path.name, "sha256": None, "disposition": "keep", "reason": "unreadable"}
    found: dict[str, object] = {"name": path.name, "sha256": _digest(data)}
    record, how = records._load_record(path)  # noqa: SLF001 - the one validating reader of the field table
    if record is None:
        return {**found, "disposition": "keep", "reason": "malformed" if how == "refused" else how}
    run_id, root, worktree = record["run_id"], record["root"], record.get("worktree")
    found["run_id"] = run_id
    if path.name != f"{run_id}.json":
        return {**found, "disposition": "keep", "reason": "misfiled"}
    status, basis = run_context.process_end_status(root["pid"], root["creation_time"])  # type: ignore[index]
    found.update({
        "worktree": worktree, "root_pid": root["pid"], "root_creation_time": root["creation_time"],  # type: ignore[index]
        "end_status": status, "end_basis": basis,
    })
    if not isinstance(worktree, str):
        return {**found, "worktree_exists": None, "disposition": "keep", "reason": "worktree_unrecorded"}
    found["worktree_exists"] = Path(worktree).exists()
    if found["worktree_exists"]:
        return {**found, "disposition": "keep", "reason": "worktree_present"}
    if status != run_context.ENDED:
        return {**found, "disposition": "keep", "reason": f"root_{status.lower()}"}
    return {**found, "disposition": "eligible", "reason": "worktree_absent_and_root_ended"}


def class_digest(eligible: list[dict[str, object]]) -> str:
    """The digest an operator grant names: every eligible entry's name and content digest, sorted."""
    return _digest("\n".join(sorted(f"{entry['name']}\t{entry['sha256']}" for entry in eligible)).encode("utf-8"))


def inventory(registry: Path) -> dict[str, object]:
    """Every top-level `*.json` entry of the registry, read-only."""
    try:
        names = sorted(path.name for path in registry.iterdir() if path.name.endswith(".json") and path.is_file())
    except FileNotFoundError:
        names = []
    entries = [_entry(registry / name) for name in names]
    eligible = [entry for entry in entries if entry["disposition"] == "eligible"]
    reasons: dict[str, int] = {}
    for entry in entries:
        reasons[str(entry["reason"])] = reasons.get(str(entry["reason"]), 0) + 1
    return {
        "schema": MANIFEST_SCHEMA, "registry": str(registry), "taken_utc": datetime.now(timezone.utc).isoformat(),
        "platform": sys.platform, "total": len(entries), "eligible": len(eligible), "reasons": reasons,
        "class_digest": class_digest(eligible), "entries": entries,
    }


class ReceiptsUnreadable(Exception):
    """The receipt file has a line that is not a whole receipt of this schema: not JSON (for example a
    run interrupted while appending), not exactly the receipt fields, or a value that is not text. Such
    a line cannot be attributed to any entry, so the file is untrusted: nothing is moved and nothing is
    verified until a person looks."""

    def __init__(self, line_number: int) -> None:
        super().__init__(f"receipts unreadable at line {line_number}")
        self.line_number = line_number


def _receipts(ended: Path) -> list[dict[str, object]]:
    path = ended / RECEIPTS
    if not path.exists():
        return []
    found: list[dict[str, object]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            receipt = json.loads(line)
        except ValueError:
            raise ReceiptsUnreadable(number) from None
        if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA or set(receipt) != _RECEIPT_FIELDS \
                or not all(isinstance(value, str) for value in receipt.values()):
            raise ReceiptsUnreadable(number)
        found.append(receipt)
    return found


def _append_receipt(ended: Path, receipt: dict[str, object]) -> None:
    line = json.dumps({"schema": RECEIPT_SCHEMA, **receipt}, sort_keys=True)
    if not records.unchanged_by_shared_sanitizer(line):
        raise ValueError("receipt refused by the shared sanitizer")
    with open(ended / RECEIPTS, "a", encoding="utf-8") as stream:
        stream.write(line + "\n")


def _receipt(planned: dict[str, object], manifest: dict[str, object], disposition: str) -> dict[str, object]:
    registry = Path(str(manifest["registry"]))
    return {
        "name": planned["name"], "sha256": planned["sha256"], "run_id": planned["run_id"],
        "source": str(registry / str(planned["name"])), "target": str(registry / ENDED_FOLDER / str(planned["name"])),
        "end_status": planned["end_status"], "end_basis": planned["end_basis"], "disposition": disposition,
        "class_digest": manifest["class_digest"], "utc": datetime.now(timezone.utc).isoformat(),
    }


def _eligible(manifest: dict[str, object]) -> list[dict[str, object]]:
    return [entry for entry in manifest["entries"] if entry["disposition"] == "eligible"]  # type: ignore[union-attr]


def _receipt_mismatch(receipt: dict[str, object], planned: dict[str, object], manifest: dict[str, object]) -> str | None:
    """The first field in which a receipt differs from the one this tool writes for `planned` under this grant."""
    if set(receipt) != _RECEIPT_FIELDS:
        return "fields"
    expected = _receipt(planned, manifest, str(receipt["disposition"]))
    for field in ("name", "sha256", "run_id", "source", "target", "end_basis", "class_digest"):
        if receipt[field] != expected[field]:
            return field
    if receipt["end_status"] != run_context.ENDED or receipt["end_basis"] not in _POSITIVE_ENDS:
        return "end_status"
    if receipt["disposition"] not in _DISPOSITIONS:
        return "disposition"
    if not _is_utc_time(str(receipt["utc"])):
        return "utc"
    return None


def _receipt_findings(manifest: dict[str, object], receipts: list[dict[str, object]]) -> tuple[dict[str, str | None], list[str]]:
    """For each eligible entry: None when exactly one receipt matches it, else why not. Plus receipts of this
    grant's class that name no eligible entry. Another grant's receipts for other entries are history."""
    planned_by_name = {str(entry["name"]): entry for entry in _eligible(manifest)}
    claims: dict[str, list[dict[str, object]]] = {}
    foreign: list[str] = []
    for receipt in receipts:
        name = str(receipt.get("name"))
        if name in planned_by_name:
            claims.setdefault(name, []).append(receipt)
        elif receipt.get("class_digest") == manifest["class_digest"]:
            foreign.append(f"{name}: receipt of this class names no eligible entry")
    findings: dict[str, str | None] = {}
    for name, planned in planned_by_name.items():
        found = claims.get(name, [])
        if len(found) != 1:
            findings[name] = f"{len(found)} receipts"
            continue
        field = _receipt_mismatch(found[0], planned, manifest)
        findings[name] = None if field is None else f"receipt {field} does not match"
    return findings, foreign


def archive(manifest: dict[str, object], granted_digest: str, *, execute: bool) -> tuple[int, list[dict[str, object]]]:
    """Move the manifest's eligible class under the operator's grant. Returns an exit code and each outcome."""
    planned_entries = _eligible(manifest)
    if manifest.get("schema") != MANIFEST_SCHEMA or class_digest(planned_entries) != manifest.get("class_digest"):
        raise SystemExit("manifest is not a conforming inventory")
    if granted_digest != manifest["class_digest"]:
        raise SystemExit("the granted class digest does not match this manifest")
    registry = Path(str(manifest["registry"]))
    ended = registry / ENDED_FOLDER
    findings, foreign = _receipt_findings(manifest, _receipts(ended))
    outcomes: list[dict[str, object]] = [
        {"name": problem.split(": ", 1)[0], "outcome": "refused", "reason": "foreign_receipt_in_class"} for problem in foreign]
    for planned in planned_entries:
        name, digest = str(planned["name"]), str(planned["sha256"])
        source, target = registry / name, ended / name
        outcome: dict[str, object] = {"name": name, "sha256": digest}
        finding = findings[name]
        if finding is None:
            archived = target.exists() and _digest(target.read_bytes()) == digest and not source.exists()
            outcomes.append({**outcome, "outcome": "already_archived"} if archived
                            else {**outcome, "outcome": "refused", "reason": "receipt_without_archive"})
            continue
        if finding != "0 receipts":
            outcomes.append({**outcome, "outcome": "refused", "reason": f"receipt_mismatch:{finding}"})
            continue
        if not source.exists() and target.exists():
            # Interrupted after the move, before the receipt: reconcile from what is on disk.
            if _digest(target.read_bytes()) != digest:
                outcomes.append({**outcome, "outcome": "refused", "reason": "archived_copy_differs"})
                continue
            if execute:
                _append_receipt(ended, _receipt(planned, manifest, "reconciled"))
            outcomes.append({**outcome, "outcome": "reconciled" if execute else "would_reconcile"})
            continue
        now = _entry(source)
        if now.get("sha256") != digest or now["disposition"] != "eligible":
            outcomes.append({**outcome, "outcome": "refused", "reason": f"changed_since_inventory:{now['reason']}"})
            continue
        if target.exists() and _digest(target.read_bytes()) != digest:
            outcomes.append({**outcome, "outcome": "refused", "reason": "destination_exists"})
            continue
        if not execute:
            outcomes.append({**outcome, "outcome": "would_archive"})
            continue
        ended.mkdir(exist_ok=True)
        if not target.exists():
            os.link(source, target)  # fails rather than overwrite an existing name
        source.unlink()
        _append_receipt(ended, _receipt(planned, manifest, "archived"))
        outcomes.append({**outcome, "outcome": "archived"})
    refused = any(outcome["outcome"] == "refused" for outcome in outcomes)
    return (EXIT_REFUSED if refused else 0), outcomes


def verify(manifest: dict[str, object]) -> tuple[int, list[str]]:
    """Every eligible entry: exactly one receipt, an archived copy with its digest, and no entry left in the registry."""
    registry = Path(str(manifest["registry"]))
    ended = registry / ENDED_FOLDER
    try:
        receipts = _receipts(ended)
    except ReceiptsUnreadable as error:
        return EXIT_MISMATCH, [f"receipts unreadable at line {error.line_number}"]
    findings, problems = _receipt_findings(manifest, receipts)
    for planned in _eligible(manifest):
        name = str(planned["name"])
        if findings[name] is not None:
            problems.append(f"{name}: {findings[name]}")
        target = ended / name
        if not target.exists() or _digest(target.read_bytes()) != planned["sha256"]:
            problems.append(f"{name}: archived copy missing or different")
        if (registry / name).exists():
            problems.append(f"{name}: still in the registry")
    return (EXIT_MISMATCH if problems else 0), problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.testing.registry_maintenance",
                                     description="Inventory, archive or verify run-context registry entries.")
    commands = parser.add_subparsers(dest="command", required=True)
    taken = commands.add_parser("inventory", help="read-only: write a manifest of every entry and the eligible class")
    taken.add_argument("--registry", type=Path, default=None, help="registry folder (default: this host's)")
    taken.add_argument("--out", type=Path, required=True, help="manifest file to create; never overwritten")
    moved = commands.add_parser("archive", help="move the manifest's eligible class under a grant (dry run unless --execute)")
    moved.add_argument("--manifest", type=Path, required=True)
    moved.add_argument("--class-digest", required=True, help="the class digest the operator granted")
    moved.add_argument("--execute", action="store_true", help="actually move; without it nothing changes")
    checked = commands.add_parser("verify", help="check receipts and archived copies against a manifest")
    checked.add_argument("--manifest", type=Path, required=True)
    arguments = parser.parse_args(argv)
    if arguments.command == "inventory":
        manifest = inventory(arguments.registry or records.registry_root())
        if not records.unchanged_by_shared_sanitizer(manifest):
            # Entry names are filesystem text; a manifest the shared sanitizer would change is never written or shown.
            print("inventory: REFUSED the manifest would be changed by the shared sanitizer; nothing written")
            return EXIT_REFUSED
        with open(arguments.out, "x", encoding="utf-8") as stream:
            stream.write(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
        print(f"inventory: total={manifest['total']} eligible={manifest['eligible']} class_digest={manifest['class_digest']}")
        print("reasons: " + ", ".join(f"{name}={count}" for name, count in sorted(manifest["reasons"].items())))  # type: ignore[union-attr]
        return 0
    manifest = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    if arguments.command == "archive":
        try:
            code, outcomes = archive(manifest, arguments.class_digest, execute=arguments.execute)
        except ReceiptsUnreadable as error:
            print(f"archive: REFUSED receipts unreadable at line {error.line_number}; nothing moved")
            return EXIT_MISMATCH
        counts: dict[str, int] = {}
        for outcome in outcomes:
            counts[str(outcome["outcome"])] = counts.get(str(outcome["outcome"]), 0) + 1
        mode = "EXECUTED" if arguments.execute else "DRY RUN"
        print(f"archive: {mode} " + ", ".join(f"{name}={count}" for name, count in sorted(counts.items())))
        for outcome in outcomes:
            if outcome["outcome"] == "refused":
                print(f"refused: {outcome['name']} {outcome['reason']}")
        return code
    code, problems = verify(manifest)
    print(f"verify: {'OK' if code == 0 else 'MISMATCH'} problems={len(problems)}")
    for problem in problems:
        print(problem)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
