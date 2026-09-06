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


def test_git_commit_source_bounds_every_git_subprocess(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def bounded_run(*args, **kwargs):
        calls.append(kwargs)
        assert kwargs["timeout"] == 10.0
        return subprocess.CompletedProcess(args[0], 0, stdout="a" * 40, stderr="")

    monkeypatch.setattr(subprocess, "run", bounded_run)

    source = GitCommitSource(commit="HEAD", repository=tmp_path)
    source.paths()

    assert len(calls) == 2


def test_git_commit_source_reads_multiple_blobs_from_one_bounded_archive(
    monkeypatch, tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Plan 11.26 Test")
    _git(repo, "config", "user.email", "plan1126@example.invalid")
    (repo / "a.py").write_text("A = 1\n", encoding="utf-8")
    (repo / "b.py").write_text("B = 2\n", encoding="utf-8")
    _git(repo, "add", "a.py", "b.py")
    _git(repo, "commit", "-m", "fixture")
    commit = _git(repo, "rev-parse", "HEAD")
    real_run = subprocess.run
    git_commands: list[tuple[str, ...]] = []

    def recording_run(command, **kwargs):
        git_commands.append(tuple(command))
        return real_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)
    source = GitCommitSource(commit=commit, repository=repo)

    assert source.read_text("a.py") == "A = 1\n"
    assert source.read_text("b.py") == "B = 2\n"
    assert sum(command[1:3] == ("archive", "--format=tar") for command in git_commands) == 1
    assert not any(command[1] == "show" for command in git_commands)


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
