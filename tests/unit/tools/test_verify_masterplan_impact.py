"""Plan 11.29: the offline ``Work tracking impact:`` pull-request declaration (the required ``verify`` job).

The file keeps its historical name because the required check's workflow step and the approved plan's commands name it.
Dispositions of the replaced masterplan-board tests: the declaration, event-body and fail-closed tests are CHANGED to the
new declaration; the five backlog-diff tests are RETIRED, because after cutover the pool carries no hardening status and
a changed tracked plan must link its own issue instead; the workflow test is CHANGED to the new steps.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tools import github_work_tracking as gwt
from tools import verify_masterplan_impact as verifier

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFIER = REPO_ROOT / "tools/verify_masterplan_impact.py"
ISSUES = f"https://github.com/{gwt.REPO}/issues"
PLANS = "docs/superpowers/plans/"
TRACKED = PLANS + "2026-11-01-plan-11-30-example.md"  # a new plan carrying its own tracking header (#301)
FROZEN = PLANS + "2026-08-18-plan-11-23-example.md"  # an approved plan resolved through the sealed manifest (#222)
EXEMPT = PLANS + "2026-07-01-phase-1-roadmap.md"
UNTRACKED = PLANS + "2026-11-02-plan-11-31-untracked.md"


def _root(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    """A checkout with one header-tracked plan, one manifest-mapped frozen plan, an exempt document and a manifest."""
    root = tmp_path / "checkout"
    (root / PLANS).mkdir(parents=True)
    (root / TRACKED).write_text(f"# Plan 11.30\n\n**Tracking issue:** {ISSUES}/301\n\nBody.\n", encoding="utf-8")
    (root / FROZEN).write_text("# Plan 11.23\n\nFrozen approved bytes.\n", encoding="utf-8")
    (root / EXEMPT).write_text("# Roadmap\n", encoding="utf-8")
    for path, text in (files or {}).items():
        (root / path).write_text(text, encoding="utf-8")
    manifest = {
        "plan_files": {FROZEN: {"record": "plan:11.23", "blob": "0" * 40, "pin": "x"}},
        "plan_exemptions": {EXEMPT: "navigation history"},
        "records": [{"id": "plan:11.23", "disposition": "migrate", "target_issue": 222}],
    }
    (root / "reports").mkdir()
    (root / "reports/github-work-tracking-migration.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _run(
    tmp_path: Path, body: str, changed: tuple[str, ...], *, event: bool = False, files: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    root = _root(tmp_path, files)
    changed_file = tmp_path / "changed-files.txt"
    changed_file.write_text("".join(f"{path}\n" for path in changed), encoding="utf-8")
    if event:
        source = tmp_path / "event.json"
        source.write_text(json.dumps({"pull_request": {"body": body}}), encoding="utf-8")
        body_args = ["--event-file", str(source)]
    else:
        source = tmp_path / "body.md"
        source.write_text(body, encoding="utf-8")
        body_args = ["--body-file", str(source)]
    return subprocess.run(
        [sys.executable, str(VERIFIER), *body_args, "--changed-files-file", str(changed_file), "--root", str(root)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    ("declaration", "changed"),
    [
        (f"Work tracking impact: {ISSUES}/301", (TRACKED, "src/optimus/example.py")),
        (f"Work tracking impact: {gwt.REPO}#301, {ISSUES}/222", (TRACKED, FROZEN)),
        (f"Work tracking impact: {ISSUES}/222", (FROZEN,)),  # a deleted or moved frozen plan still resolves by manifest
        (f"Work tracking impact: {ISSUES}/450", ("src/optimus/example.py",)),  # code-only work links its issue
    ],
)
def test_issue_links_accept_their_tracked_changes(tmp_path: Path, declaration: str, changed: tuple[str, ...]) -> None:
    result = _run(tmp_path, declaration + "\n", changed)
    assert result.returncode == 0, result.stderr


def test_none_accepts_an_untracked_change_with_a_concrete_rationale(tmp_path: Path) -> None:
    result = _run(tmp_path, "Work tracking impact: none: changes only an unrelated operator guide\n", ("docs/runbooks/x.md", EXEMPT))
    assert result.returncode == 0, result.stderr


def test_event_body_is_read_as_data_without_shell_interpolation(tmp_path: Path) -> None:
    body = "Untrusted prose: `$(echo must-not-run)`\nWork tracking impact: none: changes only an unrelated operator guide\n"
    result = _run(tmp_path, body, ("docs/runbooks/x.md",), event=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("body", "changed", "error"),
    [
        ("ordinary PR body\n", ("README.md",), "exactly one"),
        ("Work tracking impact: none: a\nWork tracking impact: none: b\n", ("README.md",), "exactly one"),
        ("Master-plan impact: none: the retired declaration\n", ("README.md",), "exactly one"),
        ("Work tracking impact: none:   \n", ("README.md",), "concrete rationale"),
        ("Work tracking impact: updated — HARDENING-TRACK-STATIC-TYPING\n", ("README.md",), "malformed"),
        ("Work tracking impact: #301\n", ("README.md",), "malformed"),
        ("Work tracking impact: https://github.com/someone/else/issues/301\n", ("README.md",), "malformed"),
        (f"Work tracking impact: {ISSUES}/0\n", ("README.md",), "malformed"),
        (f"Work tracking impact: {ISSUES}/301, {ISSUES}/301\n", (TRACKED,), "more than once"),
        ("Work tracking impact: none: the tracked plan changed only in prose\n", (TRACKED,), "#301"),
        (f"Work tracking impact: {ISSUES}/999\n", (TRACKED,), "#301"),
        ("Work tracking impact: none: the frozen plan was only moved\n", (FROZEN,), "#222"),
        ("Work tracking impact: none: a new plan\n", (UNTRACKED,), "tracking header"),
    ],
)
def test_invalid_declarations_fail_closed(tmp_path: Path, body: str, changed: tuple[str, ...], error: str) -> None:
    result = _run(tmp_path, body, changed, files={UNTRACKED: "# A new plan without its header\n"})
    assert result.returncode != 0
    assert error in result.stderr, result.stderr


@pytest.mark.parametrize(
    "body",
    [
        f"<!-- Work tracking impact: {ISSUES}/301 -->\n",
        f"<!--\nWork tracking impact: {ISSUES}/301\n-->\n",
        f"<!-- an example, never closed\nWork tracking impact: {ISSUES}/301\n",
        f"```text\nWork tracking impact: {ISSUES}/301\n```\n",
        f"~~~\nWork tracking impact: {ISSUES}/301\n~~~\n",
    ],
    ids=["inline comment", "comment block", "unclosed comment", "backtick fence", "tilde fence"],
)
def test_a_declaration_a_reviewer_cannot_see_does_not_count(tmp_path: Path, body: str) -> None:
    result = _run(tmp_path, body, (TRACKED,))
    assert result.returncode != 0
    assert "exactly one" in result.stderr, result.stderr


def test_a_visible_declaration_beside_hidden_examples_counts(tmp_path: Path) -> None:
    body = (
        "<!--\nWork tracking impact: none: a commented example\n-->\n"
        f"Work tracking impact: {ISSUES}/301\n"
        f"```text\nWork tracking impact: {ISSUES}/1\n```\n"
    )
    result = _run(tmp_path, body, (TRACKED,))
    assert result.returncode == 0, result.stderr


def test_a_sealed_plan_cannot_trade_its_identity_for_a_header(tmp_path: Path) -> None:
    rebound = {FROZEN: f"# Plan 11.23\n\n**Tracking issue:** {ISSUES}/999\n\nEdited.\n"}
    result = _run(tmp_path / "rebound", f"Work tracking impact: {ISSUES}/999\n", (FROZEN,), files=rebound)
    assert result.returncode != 0
    assert "#999" in result.stderr and "#222" in result.stderr, result.stderr
    kept = {FROZEN: f"# Plan 11.23\n\n**Tracking issue:** {ISSUES}/222\n\nEdited.\n"}
    result = _run(tmp_path / "kept", f"Work tracking impact: {ISSUES}/222\n", (FROZEN,), files=kept)
    assert result.returncode == 0, result.stderr


def test_a_plan_with_two_tracking_headers_fails_closed(tmp_path: Path) -> None:
    root = _root(tmp_path, {TRACKED: f"**Tracking issue:** {ISSUES}/301\n**Tracking issue:** {ISSUES}/302\n"})
    with pytest.raises(ValueError, match="2 tracking headers"):
        verifier.verify(body=f"Work tracking impact: {ISSUES}/301\n", changed_files={TRACKED}, root=root)


def test_the_declaration_is_checked_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("the verifier opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    verifier.verify(body=f"Work tracking impact: {ISSUES}/301\n", changed_files={TRACKED, "src/x.py"}, root=_root(tmp_path))
    source = VERIFIER.read_text(encoding="utf-8")
    assert not any(name in source for name in ("urllib", "http.client", "requests", "import socket", "subprocess"))


def test_workflow_runs_the_offline_verifier_under_the_required_job_identity() -> None:
    workflow = (REPO_ROOT / ".github/workflows/masterplan-impact.yml").read_text(encoding="utf-8")
    assert "\n  verify:\n" in workflow  # the required status-check context
    assert "git diff --name-only --no-renames --diff-filter=ACMRD" in workflow  # a moved file lists its old path too
    assert "tools/verify_masterplan_impact.py" in workflow and '--event-file "$GITHUB_EVENT_PATH"' in workflow
    assert "--masterplan" not in workflow and "--backlog-diff-file" not in workflow
    assert "uv run --frozen pytest tests/unit/tools/test_verify_masterplan_impact.py -q" in workflow


def test_pull_request_template_asks_for_the_work_tracking_declaration() -> None:
    template = (REPO_ROOT / ".github/pull_request_template.md").read_text(encoding="utf-8")
    assert "Work tracking impact:" in template and "Master-plan impact" not in template
    active = [line for line in template.splitlines() if line.strip().startswith("Work tracking impact:")]
    assert active == []  # the examples stay inside the comment, so an untouched template fails closed
