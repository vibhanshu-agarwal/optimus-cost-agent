"""Stable host errors and path/custody helpers for evidence_gather."""

from __future__ import annotations

from pathlib import Path


class HostError(Exception):
    """Fail-closed host failure with a stable snake_case code only."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def require_absolute_path(path: Path) -> Path:
    if not path.is_absolute():
        raise HostError("relative_path_rejected")
    return path


def require_existing_file(path: Path) -> Path:
    absolute = require_absolute_path(path)
    if not absolute.is_file():
        raise HostError("scenario_missing")
    return absolute


def require_directory(path: Path, *, create: bool = False) -> Path:
    absolute = require_absolute_path(path)
    if create:
        absolute.mkdir(parents=True, exist_ok=True)
    if not absolute.exists() or not absolute.is_dir():
        raise HostError("capture_root_missing")
    return absolute.resolve()
