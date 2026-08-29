"""Read-only source views for working with files or immutable Git blobs."""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath
from typing import Mapping


def _validate_relative_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise ValueError("path must be repository-relative")
    return pure.as_posix()


class SourceTree:
    """A deterministic in-memory source tree, primarily for offline fixtures."""

    def __init__(self, files: Mapping[str, str]) -> None:
        self._files = {_validate_relative_path(path): text for path, text in files.items()}

    def paths(self) -> tuple[str, ...]:
        return tuple(sorted(self._files))

    def read_text(self, path: str) -> str:
        return self._files[_validate_relative_path(path)]


class GitCommitSource:
    """A source tree whose only read primitive is ``git show <commit>:<path>``."""

    def __init__(self, commit: str, repository: Path | str = ".") -> None:
        self.repository = Path(repository).resolve()
        resolved = self._run("rev-parse", "--verify", f"{commit}^{{commit}} ".strip()).strip()
        if len(resolved) != 40 or any(ch not in "0123456789abcdef" for ch in resolved):
            raise ValueError("commit must resolve to an immutable commit object")
        self.commit = resolved

    def _run(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.repository,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return completed.stdout

    def paths(self) -> tuple[str, ...]:
        output = self._run("ls-tree", "-r", "--name-only", self.commit)
        return tuple(sorted(line for line in output.splitlines() if line))

    def read_text(self, path: str) -> str:
        relative = _validate_relative_path(path)
        return self._run("show", f"{self.commit}:{relative}")
