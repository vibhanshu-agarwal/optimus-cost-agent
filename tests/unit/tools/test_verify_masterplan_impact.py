from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFIER = REPO_ROOT / "tools/verify_masterplan_impact.py"
MASTERPLAN = REPO_ROOT / "docs/superpowers/plans/hardening-runtime-quality-masterplan.md"


def _run_verifier(
    tmp_path: Path,
    *,
    body: str,
    changed_files: tuple[str, ...],
) -> subprocess.CompletedProcess[str]:
    body_file = tmp_path / "body.md"
    changed_file = tmp_path / "changed-files.txt"
    body_file.write_text(body, encoding="utf-8")
    changed_file.write_text("\n".join(changed_files) + "\n", encoding="utf-8")
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
