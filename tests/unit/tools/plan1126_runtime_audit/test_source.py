"""Immutable source-view tests for the Plan 11.26 audit."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tools.plan1126_runtime_audit.source import GitCommitSource, SourceTree


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout.strip()


def test_git_commit_source_reads_immutable_blob_not_dirty_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Plan 11.26 Test")
    _git(repo, "config", "user.email", "plan1126@example.invalid")
    tracked = repo / "sample.py"
    tracked.write_text("VALUE = 'committed'\n", encoding="utf-8")
    _git(repo, "add", "sample.py")
    _git(repo, "commit", "-m", "fixture")
    commit = _git(repo, "rev-parse", "HEAD")
    tracked.write_text("VALUE = 'dirty substitution'\n", encoding="utf-8")

    source = GitCommitSource(commit=commit, repository=repo)

    assert source.read_text("sample.py") == "VALUE = 'committed'\n"
    assert source.paths() == ("sample.py",)


def test_source_tree_is_sorted_and_rejects_path_traversal() -> None:
    source = SourceTree({"z.py": "z = 1\n", "a.py": "a = 1\n"})
    assert source.paths() == ("a.py", "z.py")
    assert source.read_text("a.py") == "a = 1\n"
    try:
        source.read_text("../outside.py")
    except ValueError as exc:
        assert "repository-relative" in str(exc)
    else:
        raise AssertionError("path traversal must be rejected")
