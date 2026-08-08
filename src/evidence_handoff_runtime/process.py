"""Process spawn seam for lifecycle-managed external commands."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from typing import Protocol


class ProcessResult(Protocol):
    returncode: int
    stdout: str
    stderr: str


class ProcessRunner(Protocol):
    def run(
        self,
        argv: list[str],
        *,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> ProcessResult: ...


class SubprocessRunner:
    """Default shell=False subprocess runner."""

    def run(
        self,
        argv: list[str],
        *,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            shell=False,
            env=dict(env) if env is not None else None,
            timeout=timeout,
        )


def require_argv(argv: Sequence[str]) -> list[str]:
    if not argv:
        raise ValueError("empty_argv")
    if not argv[0]:
        raise ValueError("empty_executable")
    return [str(part) for part in argv]


__all__ = [
    "ProcessResult",
    "ProcessRunner",
    "SubprocessRunner",
    "require_argv",
]
