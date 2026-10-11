from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFIER = REPO_ROOT / "tools/verify_masterplan_impact.py"
MASTERPLAN = REPO_ROOT / "docs/superpowers/plans/hardening-runtime-quality-masterplan.md"


BACKLOG = "docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md"


def _backlog_diff(*changed_lines: str) -> str:
    header = (
        f"diff --git a/{BACKLOG} b/{BACKLOG}\n"
        "index 1111111..2222222 100644\n"
        f"--- a/{BACKLOG}\n"
        f"+++ b/{BACKLOG}\n"
        "@@ -10,1 +10,1 @@ | `HARDENING-FEAT-RUNTIME-QUALITY` | Open | HIGH |\n"
    )
    return header + "".join(f"{line}\n" for line in changed_lines)


def _run_verifier(
    tmp_path: Path,
    *,
    body: str,
    changed_files: tuple[str, ...],
    backlog_diff: str | None = None,
) -> subprocess.CompletedProcess[str]:
    body_file = tmp_path / "body.md"
    changed_file = tmp_path / "changed-files.txt"
    body_file.write_text(body, encoding="utf-8")
    changed_file.write_text("\n".join(changed_files) + "\n", encoding="utf-8")
    diff_args: list[str] = []
    if backlog_diff is not None:
        diff_file = tmp_path / "backlog.diff"
        diff_file.write_text(backlog_diff, encoding="utf-8")
        diff_args = ["--backlog-diff-file", str(diff_file)]
    return subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--body-file",
            str(body_file),
            "--changed-files-file",
            str(changed_file),
            "--masterplan",
            str(MASTERPLAN),
            *diff_args,
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_updated_declaration_accepts_known_track_with_masterplan_change(tmp_path: Path) -> None:
    result = _run_verifier(
        tmp_path,
        body="Master-plan impact: updated — HARDENING-TRACK-STATIC-TYPING\n",
        changed_files=(
            "docs/superpowers/plans/hardening-runtime-quality-masterplan.md",
            "src/optimus/example.py",
        ),
    )

    assert result.returncode == 0, result.stderr


def test_none_declaration_accepts_unrelated_change_with_concrete_rationale(tmp_path: Path) -> None:
    result = _run_verifier(
        tmp_path,
        body="Master-plan impact: none: changes only an unrelated operator guide\n",
        changed_files=("docs/runbooks/unrelated.md",),
    )

    assert result.returncode == 0, result.stderr


def test_event_body_is_read_as_data_without_shell_interpolation(tmp_path: Path) -> None:
    event_file = tmp_path / "event.json"
    changed_file = tmp_path / "changed-files.txt"
    event_file.write_text(
        json.dumps(
            {
                "pull_request": {
                    "body": (
                        "Untrusted prose: `$(echo must-not-run)`\n"
                        "Master-plan impact: none: changes only an unrelated operator guide\n"
                    )
                }
            }
        ),
        encoding="utf-8",
    )
    changed_file.write_text("docs/runbooks/unrelated.md\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--event-file",
            str(event_file),
            "--changed-files-file",
            str(changed_file),
            "--masterplan",
            str(MASTERPLAN),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "body,changed_files,error_token",
    [
        ("ordinary PR body\n", ("README.md",), "exactly one"),
        (
            "Master-plan impact: none: first\nMaster-plan impact: none: second\n",
            ("README.md",),
            "exactly one",
        ),
        ("Master-plan impact: none:   \n", ("README.md",), "malformed"),
        (
            "Master-plan impact: updated — HARDENING-TRACK-NOT-REGISTERED\n",
            ("docs/superpowers/plans/hardening-runtime-quality-masterplan.md",),
            "unknown track",
        ),
        (
            "Master-plan impact: updated — HARDENING-TRACK-STATIC-TYPING\n",
            ("src/optimus/example.py",),
            "must update the masterplan",
        ),
        (
            "Master-plan impact: none: child status did not change\n",
            ("docs/superpowers/plans/hardening-static-type-checking-implementation.md",),
            "child plan changed",
        ),
        (
            "Master-plan impact: none: status text did not change\n",
            ("docs/superpowers/plans/hardening-runtime-quality-masterplan.md",),
            "none conflicts",
        ),
        (
            "Master-plan impact: none: feature state did not change\n",
            (
                "docs/superpowers/plans/"
                "2026-07-23-consolidated-deferred-followups-backlog.md",
            ),
            "backlog diff is required",
        ),
    ],
)
def test_invalid_declarations_fail_closed(
    tmp_path: Path,
    body: str,
    changed_files: tuple[str, ...],
    error_token: str,
) -> None:
    result = _run_verifier(tmp_path, body=body, changed_files=changed_files)

    assert result.returncode != 0
    assert error_token in result.stderr.lower()


def test_none_accepts_backlog_change_that_touches_no_hardening_content(tmp_path: Path) -> None:
    result = _run_verifier(
        tmp_path,
        body="Master-plan impact: none: evidence-handoff registry rows only\n",
        changed_files=(BACKLOG, "docs/superpowers/specs/example-design_v2.md"),
        backlog_diff=_backlog_diff(
            "-| `EVIDENCE-HANDOFF-FEAT-EXAMPLE` | Open | MEDIUM | Old scope. |",
            "+| `EVIDENCE-HANDOFF-FEAT-EXAMPLE` | Closed | MEDIUM | New scope. |",
        ),
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "changed_line",
    [
        "+| `HARDENING-FEAT-RUNTIME-QUALITY` | Closed | HIGH | Claimed closure. |",
        "-| `HARDENING-FEAT-RUNTIME-QUALITY` | Open | HIGH | Projection. |",
        "+See [the child plan](hardening-static-type-checking-implementation.md).",
        "+Pointer to hardening-runtime-quality-masterplan.md status.",
    ],
)
def test_none_rejects_backlog_change_that_touches_hardening_content(
    tmp_path: Path, changed_line: str
) -> None:
    result = _run_verifier(
        tmp_path,
        body="Master-plan impact: none: registry rows only\n",
        changed_files=(BACKLOG,),
        backlog_diff=_backlog_diff("+| `EVIDENCE-HANDOFF-FEAT-EXAMPLE` | Open |", changed_line),
    )

    assert result.returncode != 0
    assert "none conflicts" in result.stderr.lower()


def test_none_ignores_hardening_text_in_diff_headers_and_context(tmp_path: Path) -> None:
    diff = _backlog_diff(
        " | `HARDENING-FEAT-RUNTIME-QUALITY` | Open | HIGH | unchanged context |",
        "+| `EVIDENCE-HANDOFF-FEAT-EXAMPLE` | Open | MEDIUM | Added. |",
    )
    result = _run_verifier(
        tmp_path,
        body="Master-plan impact: none: registry rows only\n",
        changed_files=(BACKLOG,),
        backlog_diff=diff,
    )

    assert result.returncode == 0, result.stderr


def test_none_fails_closed_when_backlog_is_listed_but_diff_is_empty(tmp_path: Path) -> None:
    result = _run_verifier(
        tmp_path,
        body="Master-plan impact: none: registry rows only\n",
        changed_files=(BACKLOG,),
        backlog_diff="",
    )

    assert result.returncode != 0
    assert "no changed lines" in result.stderr.lower()


def test_none_still_rejects_masterplan_change_even_with_clean_backlog_diff(tmp_path: Path) -> None:
    result = _run_verifier(
        tmp_path,
        body="Master-plan impact: none: registry rows only\n",
        changed_files=(BACKLOG, "docs/superpowers/plans/hardening-runtime-quality-masterplan.md"),
        backlog_diff=_backlog_diff("+| `EVIDENCE-HANDOFF-FEAT-EXAMPLE` | Open |"),
    )

    assert result.returncode != 0
    assert "none conflicts" in result.stderr.lower()


def test_workflow_supplies_the_backlog_diff_to_the_verifier() -> None:
    workflow = (REPO_ROOT / ".github/workflows/masterplan-impact.yml").read_text(encoding="utf-8")

    assert f'-- {BACKLOG} > "$RUNNER_TEMP/masterplan-backlog.diff"' in workflow
    assert '--backlog-diff-file "$RUNNER_TEMP/masterplan-backlog.diff"' in workflow
