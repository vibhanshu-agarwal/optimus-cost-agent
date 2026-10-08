from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from tools.tracked_repository_files import (
    TrackedFileInventoryError,
    tracked_repository_files,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "-q")
    (root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "tracked.py").write_text("TRACKED = True\n", encoding="utf-8")
    (root / "tests" / "tracked.py").write_text("TRACKED = True\n", encoding="utf-8")
    _git(root, "add", ".gitignore", "src/tracked.py", "tests/tracked.py")
    return root


def _relative(root: Path, paths: tuple[Path, ...]) -> tuple[str, ...]:
    return tuple(path.relative_to(root).as_posix() for path in paths)


def test_inventory_returns_only_tracked_files_under_requested_pathspecs(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / "outside.txt").write_text("outside\n", encoding="utf-8")
    (root / "src" / "untracked.py").write_text("UNTRACKED = True\n", encoding="utf-8")
    ignored = root / "tests" / "fixtures" / "node_modules" / "zod" / "index.d.ts"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("type Zod" + "Cred" + "itCard = string;\n", encoding="utf-8")

    actual = tracked_repository_files(root, pathspecs=("src", "tests"))

    assert _relative(root, actual) == ("src/tracked.py", "tests/tracked.py")


def test_force_adding_an_ignored_file_makes_it_visible(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    ignored = root / "tests" / "fixtures" / "node_modules" / "zod" / "index.d.ts"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("type Zod" + "Cred" + "itCard = string;\n", encoding="utf-8")
    _git(root, "add", "-f", "tests/fixtures/node_modules/zod/index.d.ts")

    actual = tracked_repository_files(root, pathspecs=("tests",))

    assert _relative(root, actual) == (
        "tests/fixtures/node_modules/zod/index.d.ts",
        "tests/tracked.py",
    )


@pytest.mark.parametrize("pathspec", ("../outside", "/absolute", "C:/absolute"))
def test_inventory_rejects_escaping_or_absolute_pathspecs(
    tmp_path: Path, pathspec: str
) -> None:
    root = _repository(tmp_path)

    with pytest.raises(TrackedFileInventoryError, match="invalid_pathspec"):
        tracked_repository_files(root, pathspecs=(pathspec,))


def test_inventory_fails_when_root_is_not_a_git_repository(tmp_path: Path) -> None:
    with pytest.raises(TrackedFileInventoryError, match="git_ls_files_failed"):
        tracked_repository_files(tmp_path, pathspecs=("src",))


def test_inventory_fails_when_a_tracked_file_is_missing(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / "src" / "tracked.py").unlink()

    with pytest.raises(TrackedFileInventoryError, match="tracked_file_missing"):
        tracked_repository_files(root, pathspecs=("src",))


def _commit_index(root: Path) -> Path:
    """A partial commit's index (what git names GIT_INDEX_FILE for `git commit -- <path>`): HEAD, nothing removed."""
    index = root / ".git" / "next-index-test.lock"
    subprocess.run(["git", "read-tree", "HEAD"], cwd=root, check=True, capture_output=True,
                   env={**os.environ, "GIT_INDEX_FILE": str(index)})
    return index


def test_inside_a_commit_hook_run_the_scanner_lists_the_commit_s_own_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan 11.30 residual (Task 3, LOW): a test run inside a partial-commit hook has GIT_* stripped, so the scanner
    listed the default index. A deletion staged outside the commit then hid a file the commit keeps. The runner names
    the commit's index under non-GIT_ names; the scanner lists it, for that repository only."""
    root = _repository(tmp_path)
    _git(root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "base")
    index = _commit_index(root)
    _git(root, "rm", "-q", "--cached", "tests/tracked.py")  # staged outside the commit; the file stays on disk
    assert _relative(root, tracked_repository_files(root, pathspecs=["tests"])) == ()  # the default index
    monkeypatch.setenv("TEST_RUN_COMMIT_INDEX_FILE", str(index))
    monkeypatch.setenv("TEST_RUN_COMMIT_INDEX_ROOT", str(root))
    assert _relative(root, tracked_repository_files(root, pathspecs=["tests"])) == ("tests/tracked.py",)
    (tmp_path / "other").mkdir()
    other = _repository(tmp_path / "other")  # another repository is never listed through this commit's index
    (other / "tests" / "other_only.py").write_text("OTHER = True\n", encoding="utf-8")
    _git(other, "add", "tests/other_only.py")  # tracked only there: the commit's index would not list it
    assert _relative(other, tracked_repository_files(other, pathspecs=["tests"])) == ("tests/other_only.py", "tests/tracked.py")
    index.unlink()  # a named commit index that is gone: refused, never an empty listing
    with pytest.raises(TrackedFileInventoryError, match="commit_index_missing"):
        tracked_repository_files(root, pathspecs=["tests"])


_COMMIT_INDEX = "lists the repository through index_environment, so inside a commit hook's test run it reads the commit's index"
# Every tracked Python file that lists a Git index, and why that listing cannot read the default index where a commit's
# own index is meant (Plan 11.30 Task 3 residual, enumerated as a class).
_INDEX_LISTINGS = {
    "tools/tracked_repository_files.py": _COMMIT_INDEX,
    "tools/doc_paths.py": _COMMIT_INDEX,
    "tests/unit/docs/test_docs_index.py": _COMMIT_INDEX,
    "tests/unit/docs/test_plan_directory_hygiene.py": _COMMIT_INDEX,
    "tools/testing/run_profile.py": "the runner itself: it runs inside the commit hook, where git's own GIT_INDEX_FILE is in force",
    "tools/probe_p11_zed_session_load.py": "a manually run probe digests its own checkout; no test run executes that listing",
    "tests/unit/guardrails/test_ci_parity.py": "its listing programs run in per-test fixture repositories, never the repository being committed",
    "tests/unit/tools/test_probe_p11_zed_session_load.py": "a stand-in for git that the probe's isolated copies must never call",
    "tests/unit/tools/test_run_profile.py": "lists a per-test fixture repository's default index, which is the subject",
}


def test_every_index_listing_reads_the_commit_s_index_or_is_reviewed() -> None:
    root = Path(__file__).resolve().parents[3]
    needle = re.compile("[\"']ls-" + "files[\"']")
    found = {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in tracked_repository_files(root, pathspecs=["tools", "tests", "src"])
        if path.suffix == ".py" and needle.search(path.read_text(encoding="utf-8"))
    }
    assert sorted(set(found) - set(_INDEX_LISTINGS)) == [], "an unreviewed Git index listing"
    assert sorted(set(_INDEX_LISTINGS) - set(found)) == [], "a reviewed listing no longer exists"
    for name, why in _INDEX_LISTINGS.items():
        if why == _COMMIT_INDEX:
            assert "index_environment(" in found[name], name
