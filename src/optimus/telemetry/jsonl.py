from __future__ import annotations

from pathlib import Path

from optimus.telemetry.events import TelemetryEvent

DEFAULT_TELEMETRY_DIRNAME = ".optimus"
DEFAULT_TELEMETRY_FILENAME = "telemetry.jsonl"


class JsonlTelemetryWriter:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    @classmethod
    def for_workspace(cls, workspace_root: str | Path) -> JsonlTelemetryWriter:
        """Build the writer at the project-standard, already-gitignored local telemetry path."""
        return cls(Path(workspace_root) / DEFAULT_TELEMETRY_DIRNAME / DEFAULT_TELEMETRY_FILENAME)

    def append(self, event: TelemetryEvent) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(event.to_json_line())
            file.write("\n")
