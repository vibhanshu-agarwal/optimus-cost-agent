"""Fail-closed validation for the hardening masterplan PR declaration."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DECLARATION_PREFIX = "Master-plan impact:"
UPDATED_PREFIX = "updated — "
NONE_PREFIX = "none: "
TRACK_NAME = re.compile(r"HARDENING-TRACK-[A-Z0-9-]+")
BOARD_ROW = re.compile(
    r"^\| `(?P<track>HARDENING-TRACK-[A-Z0-9-]+)` "
    r"\| (?P<plan>`|\[[^]]+\]\()(?:archive/)?"
    r"(?P<filename>hardening-[a-z0-9-]+(?:_v[0-9]+)?\.md)"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    body_source = parser.add_mutually_exclusive_group(required=True)
    body_source.add_argument("--body-file", type=Path)
    body_source.add_argument("--event-file", type=Path)
    parser.add_argument("--changed-files-file", required=True, type=Path)
    parser.add_argument("--masterplan", required=True, type=Path)
    return parser.parse_args()


def _read_body(args: argparse.Namespace) -> str:
    if args.body_file is not None:
        return args.body_file.read_text(encoding="utf-8")
    event = json.loads(args.event_file.read_text(encoding="utf-8"))
    body = event.get("pull_request", {}).get("body")
    return body if isinstance(body, str) else ""


def _board(masterplan: Path) -> tuple[set[str], set[str]]:
    rows: list[tuple[str, str]] = []
    for line in masterplan.read_text(encoding="utf-8").splitlines():
        match = BOARD_ROW.match(line)
        if match is None:
            continue
        rows.append((match.group("track"), match.group("filename")))
    tracks = {track for track, _filename in rows}
    child_plans = {filename for _track, filename in rows}
    if len(rows) != 15 or len(tracks) != 15 or len(child_plans) != 15:
        raise ValueError("masterplan must contain 15 unique track-to-child rows")
    return tracks, child_plans


def _declaration(body: str) -> str:
    declarations = [
        line.strip()
        for line in body.splitlines()
        if line.strip().startswith(DECLARATION_PREFIX)
    ]
    if len(declarations) != 1:
        raise ValueError("PR body must contain exactly one Master-plan impact declaration")
    return declarations[0].removeprefix(DECLARATION_PREFIX).strip()


def verify(*, body: str, changed_files: set[str], masterplan: Path) -> None:
    known_tracks, child_plans = _board(masterplan)
    declaration = _declaration(body)
    masterplan_path = "docs/superpowers/plans/hardening-runtime-quality-masterplan.md"
    owning_backlog_path = (
        "docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md"
    )

    if declaration.startswith(UPDATED_PREFIX):
        raw_tracks = declaration.removeprefix(UPDATED_PREFIX)
        tracks = [value.strip() for value in raw_tracks.split(",")]
        if not tracks or any(TRACK_NAME.fullmatch(track) is None for track in tracks):
            raise ValueError("malformed updated Master-plan impact declaration")
        unknown = set(tracks) - known_tracks
        if unknown:
            raise ValueError(f"unknown track(s): {', '.join(sorted(unknown))}")
        if masterplan_path not in changed_files:
            raise ValueError("updated declaration must update the masterplan")
        return

    if declaration.startswith(NONE_PREFIX):
        rationale = declaration.removeprefix(NONE_PREFIX).strip()
        if not rationale:
            raise ValueError("malformed none declaration: concrete rationale is required")
        owning_changes = changed_files & {masterplan_path, owning_backlog_path}
        if owning_changes:
            raise ValueError(
                "none conflicts with changes to status authority: "
                f"{', '.join(sorted(owning_changes))}"
            )
        for changed_file in changed_files:
            normalized = changed_file.replace("\\", "/")
            if not normalized.startswith("docs/superpowers/plans/"):
                continue
            if Path(normalized).name in child_plans:
                raise ValueError(f"child plan changed without masterplan update: {normalized}")
        return

    raise ValueError("malformed Master-plan impact declaration")


def main() -> int:
    args = _parse_args()
    try:
        body = _read_body(args)
        changed_files = {
            line.strip().replace("\\", "/")
            for line in args.changed_files_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        verify(body=body, changed_files=changed_files, masterplan=args.masterplan)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"masterplan-impact: {exc}", file=sys.stderr)
        return 1
    print("masterplan-impact: declaration is consistent with changed files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
