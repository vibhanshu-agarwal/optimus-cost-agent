from __future__ import annotations

from typing import Protocol


class CompositeGateResultLike(Protocol):
    @property
    def failed_gate_names(self) -> tuple[str, ...]:
        raise NotImplementedError


class CompositeGateError(Exception):
    def __init__(self, result: CompositeGateResultLike) -> None:
        self.result = result
        names = ", ".join(result.failed_gate_names)
        super().__init__(f"required fitness gates failed: {names}")
