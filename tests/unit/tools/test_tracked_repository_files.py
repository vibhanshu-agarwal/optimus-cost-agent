from __future__ import annotations

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
    ignored.write_text("type ZodCreditCard = string;\n", encoding="utf-8")

    actual = tracked_repository_files(root, pathspecs=("src", "tests"))

    assert _relative(root, actual) == ("src/tracked.py", "tests/tracked.py")


def test_force_adding_an_ignored_file_makes_it_visible(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    ignored = root / "tests" / "fixtures" / "node_modules" / "zod" / "index.d.ts"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("type ZodCreditCard = string;\n", encoding="utf-8")
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
