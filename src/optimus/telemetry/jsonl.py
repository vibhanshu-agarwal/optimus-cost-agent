from __future__ import annotations

from pathlib import Path

from optimus.telemetry.events import TelemetryEvent


class JsonlTelemetryWriter:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def append(self, event: TelemetryEvent) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(event.to_json_line())
            file.write("\n")
