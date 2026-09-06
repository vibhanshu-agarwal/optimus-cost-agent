"""Fail-closed Git-index inventory for repository-truth scanners."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:/")


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


def tracked_repository_files(
    project_root: Path, *, pathspecs: Sequence[str]
) -> tuple[Path, ...]:
    """Return existing tracked files beneath validated repository pathspecs."""
    try:
        root = project_root.resolve(strict=True)
    except OSError as exc:
        raise TrackedFileInventoryError("project_root_invalid", str(project_root)) from exc
    normalized_pathspecs = tuple(_normalize_pathspec(item) for item in pathspecs)
    try:
        completed = subprocess.run(  # noqa: S603
            ["git", "ls-files", "-z", "--", *normalized_pathspecs],
            cwd=root,
            check=False,
            capture_output=True,
            shell=False,
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
