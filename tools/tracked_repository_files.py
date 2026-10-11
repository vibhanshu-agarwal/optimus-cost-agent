"""Fail-closed Git-index inventory for repository-truth scanners."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:/")
# Plan 11.30: inside a commit hook, git names the index being committed in GIT_INDEX_FILE, but a test run strips every
# GIT_* variable (tests/conftest.py). The profile runner hands that index to its test runs under these names, so a
# scanner lists the commit's own files -- for the repository being committed only. The names stay outside the
# product's OPTIMUS_* namespace: the agent's launch gate refuses any OPTIMUS_* name it does not know.
COMMIT_INDEX_FILE = "TEST_RUN_COMMIT_INDEX_FILE"
COMMIT_INDEX_ROOT = "TEST_RUN_COMMIT_INDEX_ROOT"


@dataclass(frozen=True, slots=True)
class TrackedFileInventoryError(RuntimeError):
    code: str
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}" if self.detail else self.code


def _normalize_pathspec(pathspec: str) -> str:
    normalized = pathspec.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or pure.is_absolute()
        or _WINDOWS_ABSOLUTE.match(normalized)
        or ".." in pure.parts
    ):
        raise TrackedFileInventoryError("invalid_pathspec", pathspec)
    return pure.as_posix()


def index_environment(root: Path) -> dict[str, str] | None:
    """The environment that lists `root`'s index: inside a commit hook's test run, the commit's own index (named by
    the profile runner) when `root` is the repository being committed; otherwise None, the default index. A named
    commit index that no longer exists is refused: listing it would read as an empty repository."""
    index, owner = os.environ.get(COMMIT_INDEX_FILE), os.environ.get(COMMIT_INDEX_ROOT)
    if not index or not owner:
        return None
    try:
        if Path(owner).resolve() != root.resolve():
            return None
    except OSError:
        return None
    if not Path(index).is_file():
        raise TrackedFileInventoryError("commit_index_missing", index)
    return {**os.environ, "GIT_INDEX_FILE": index}


def tracked_repository_files(
    project_root: Path, *, pathspecs: Sequence[str]
) -> tuple[Path, ...]:
    """Return existing tracked files beneath validated repository pathspecs."""
    try:
        root = project_root.resolve(strict=True)
    except OSError as exc:
        raise TrackedFileInventoryError("project_root_invalid", str(project_root)) from exc
    normalized_pathspecs = tuple(_normalize_pathspec(item) for item in pathspecs)
    environment = index_environment(root)
    try:
        completed = subprocess.run(  # noqa: S603
            ["git", "ls-files", "-z", "--", *normalized_pathspecs],
            cwd=root,
            check=False,
            capture_output=True,
            shell=False,
            env=environment,
        )
    except OSError as exc:
        raise TrackedFileInventoryError("git_ls_files_failed", type(exc).__name__) from exc
    if completed.returncode != 0:
        raise TrackedFileInventoryError(
            "git_ls_files_failed", f"exit={completed.returncode}"
        )
    try:
        relative_names = completed.stdout.decode("utf-8").split("\0")
    except UnicodeDecodeError as exc:
        raise TrackedFileInventoryError("git_ls_files_invalid_utf8") from exc

    files: list[tuple[str, Path]] = []
    for relative_name in relative_names:
        if not relative_name:
            continue
        normalized_name = relative_name.replace("\\", "/")
        pure = PurePosixPath(normalized_name)
        if pure.is_absolute() or ".." in pure.parts:
            raise TrackedFileInventoryError("tracked_path_escape", normalized_name)
        candidate = root.joinpath(*pure.parts)
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise TrackedFileInventoryError("tracked_file_missing", normalized_name) from exc
        if not resolved.is_relative_to(root):
            raise TrackedFileInventoryError("tracked_path_escape", normalized_name)
        if not resolved.is_file():
            raise TrackedFileInventoryError("tracked_file_not_regular", normalized_name)
        files.append((pure.as_posix(), resolved))
    return tuple(path for _name, path in sorted(files))
