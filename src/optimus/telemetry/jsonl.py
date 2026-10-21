from __future__ import annotations

import os
import threading
from pathlib import Path

from optimus.telemetry.events import TelemetryEvent

DEFAULT_TELEMETRY_DIRNAME = ".optimus"
DEFAULT_TELEMETRY_FILENAME = "telemetry.jsonl"

# One lock per destination file, shared by every writer instance in the process (correction plan v4, C4): the fan-out's
# writer and a diagnostic writer for the same workspace never interleave a line.
_DESTINATION_LOCKS: dict[str, threading.Lock] = {}
_DESTINATION_LOCKS_GUARD = threading.Lock()


def _destination_lock(path: Path) -> threading.Lock:
    key = os.path.normcase(os.path.abspath(path))
    with _DESTINATION_LOCKS_GUARD:
        return _DESTINATION_LOCKS.setdefault(key, threading.Lock())


class JsonlTelemetryWriter:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = _destination_lock(self._path)

    @property
    def path(self) -> Path:
        return self._path

    @classmethod
    def for_workspace(cls, workspace_root: str | Path) -> JsonlTelemetryWriter:
        """Build the writer at the project-standard, already-gitignored local telemetry path."""
        return cls(Path(workspace_root) / DEFAULT_TELEMETRY_DIRNAME / DEFAULT_TELEMETRY_FILENAME)

    def append(self, event: TelemetryEvent) -> None:
        line = event.to_json_line() + "\n"
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8", newline="\n") as file:
                file.write(line)
