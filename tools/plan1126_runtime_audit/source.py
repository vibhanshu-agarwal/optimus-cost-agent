"""Read-only source views for working with files or immutable Git blobs."""

from __future__ import annotations

import io
import os
import subprocess
import tarfile
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
    """A source tree read from immutable Git objects by bounded subprocesses."""

    _GIT_TIMEOUT_SECONDS = 10.0

    def __init__(self, commit: str, repository: Path | str = ".") -> None:
        self.repository = Path(repository).resolve()
        self._archive: dict[str, bytes] | None = None
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
            timeout=self._GIT_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
        return completed.stdout

    def _load_archive(self) -> Mapping[str, bytes]:
        if self._archive is None:
            completed = subprocess.run(
                ["git", "archive", "--format=tar", self.commit],
                cwd=self.repository,
                check=True,
                capture_output=True,
                timeout=self._GIT_TIMEOUT_SECONDS,
                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
            )
            archive: dict[str, bytes] = {}
            with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as bundle:
                for member in bundle.getmembers():
                    if not member.isfile():
                        continue
                    handle = bundle.extractfile(member)
                    if handle is not None:
                        archive[_validate_relative_path(member.name)] = handle.read()
            self._archive = archive
        return self._archive

    def paths(self) -> tuple[str, ...]:
        output = self._run("ls-tree", "-r", "--name-only", self.commit)
        return tuple(sorted(line for line in output.splitlines() if line))

    def read_text(self, path: str) -> str:
        relative = _validate_relative_path(path)
        text = self._load_archive()[relative].decode("utf-8")
        return text.replace("\r\n", "\n").replace("\r", "\n")
