"""Offline check of a pull request's ``Work tracking impact:`` declaration (Plan 11.29).

The file keeps its historical name because the required ``verify`` job and the approved plan's commands run it. It
reads only the pull-request body, the changed-file list and the checkout (its plan files and the sealed migration
manifest); it makes no network request and does not judge whether the linked issues capture every finding.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import github_work_tracking as gwt  # noqa: E402 - the repository root is on the path only from here

DECLARATION_PREFIX = "Work tracking impact:"
NONE_PREFIX = "none:"
MANIFEST = "reports/github-work-tracking-migration.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    body_source = parser.add_mutually_exclusive_group(required=True)
    body_source.add_argument("--body-file", type=Path)
    body_source.add_argument("--event-file", type=Path)
    parser.add_argument("--changed-files-file", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path("."), help="the pull request's checkout")
    return parser.parse_args()


def _read_body(args: argparse.Namespace) -> str:
    if args.body_file is not None:
        return args.body_file.read_text(encoding="utf-8")
    event = json.loads(args.event_file.read_text(encoding="utf-8"))
    body = event.get("pull_request", {}).get("body")
    return body if isinstance(body, str) else ""


def _declaration(body: str) -> str:
    # Only what a reviewer sees counts: a declaration inside an HTML comment or fenced code is an example.
    declarations = [line.strip() for line in gwt.visible_lines(body) if line.strip().startswith(DECLARATION_PREFIX)]
    if len(declarations) != 1:
        raise ValueError(f"the pull request body must contain exactly one {DECLARATION_PREFIX} declaration")
    return declarations[0].removeprefix(DECLARATION_PREFIX).strip()


def _declared_issues(value: str) -> set[int] | None:
    """The linked issue numbers, or ``None`` for a ``none:`` declaration with its rationale."""
    if value.startswith(NONE_PREFIX):
        if not value.removeprefix(NONE_PREFIX).strip():
            raise ValueError("malformed none declaration: a concrete rationale is required")
        return None
    numbers = []
    for item in (part.strip() for part in value.split(",")):
        try:
            numbers.append(gwt.issue_reference(item))
        except ValueError:
            raise ValueError(f"malformed {DECLARATION_PREFIX} declaration: {item!r} is not an issue of {gwt.REPO}") from None
    repeated = sorted({number for number in numbers if numbers.count(number) > 1})
    if repeated:
        raise ValueError(f"the declaration links {', '.join(f'#{number}' for number in repeated)} more than once")
    return set(numbers)


def _plan_issue(root: Path, path: str, manifest: dict[str, Any]) -> int | None:
    """A changed plan's tracking issue: the sealed manifest's baseline identity for its path, which a header may repeat
    but never replace; else its own header."""
    file = root / path
    header = gwt.tracking_issue(file.read_text(encoding="utf-8"), path) if file.is_file() else None
    entry = manifest.get("plan_files", {}).get(path)
    if entry is None:
        return header
    record = next((record for record in manifest.get("records", []) if record.get("id") == entry.get("record")), None)
    sealed = record.get("target_issue") if record else None
    if header is not None and header != sealed:
        raise ValueError(
            f"{path} carries a tracking header for #{header}, but its sealed baseline identity is"
            f" {f'#{sealed}' if sealed else 'not yet an issue'}; a sealed plan keeps its identity"
        )
    return sealed


def verify(*, body: str, changed_files: set[str], root: Path) -> None:
    """Raise ``ValueError`` unless the declaration is well formed and links every changed tracked plan's issue."""
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    declared = _declared_issues(_declaration(body))
    for path in sorted(changed_files):
        if not (path.startswith(gwt.PLANS_DIR) and path.endswith(".md")):
            continue
        number = _plan_issue(root, path, manifest)
        if number is None:
            docs_root = "/" not in path.removeprefix(gwt.PLANS_DIR)
            if docs_root and (root / path).is_file() and path not in manifest.get("plan_exemptions", {}):
                raise ValueError(f"{path} is a new docs-root plan without a tracking header; add **Tracking issue:** <issue URL>")
            continue
        if declared is None:
            raise ValueError(f"none conflicts with {path}, which is tracked by #{number}; link that issue")
        if number not in declared:
            raise ValueError(f"{path} is tracked by #{number}; link it in the declaration")


def main() -> int:
    args = _parse_args()
    try:
        changed = {
            line.strip().replace("\\", "/") for line in args.changed_files_file.read_text(encoding="utf-8").splitlines() if line.strip()
        }
        verify(body=_read_body(args), changed_files=changed, root=args.root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"work-tracking-impact: {exc}", file=sys.stderr)
        return 1
    print("work-tracking-impact: the declaration is consistent with the changed files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
