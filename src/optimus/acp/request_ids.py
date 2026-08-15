from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DuplicateRequestId(Exception):
    request_id: str | int


class RequestIdTracker:
    def __init__(self) -> None:
        self._seen: set[str | int] = set()

    def remember(self, request_id: str | int | None) -> None:
        if request_id is None:
            return
        if request_id in self._seen:
            raise DuplicateRequestId(request_id=request_id)
        self._seen.add(request_id)

    def seen(self, request_id: str | int) -> bool:
        return request_id in self._seen
