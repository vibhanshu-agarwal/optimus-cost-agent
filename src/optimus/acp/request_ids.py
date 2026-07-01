from __future__ import annotations

from dataclasses import dataclass

from optimus.acp.errors import DUPLICATE_REQUEST_ID


@dataclass(frozen=True)
class DuplicateRequestId(Exception):
    request_id: str | int
    code: int = DUPLICATE_REQUEST_ID

    def __str__(self) -> str:
        return f"duplicate request id: {self.request_id}"


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
