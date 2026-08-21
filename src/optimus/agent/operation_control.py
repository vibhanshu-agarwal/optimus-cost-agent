"""Narrow runner-facing turn operation control (Plan 11.25 Task 6)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TurnOperationControl(Protocol):
    """ACP TurnControl-compatible surface consumed by AgentRunner / PlanningLoopRunner.

    Holds no copied cancellation booleans and no ACP transport methods.
    """

    def register_operations(self, operations: Sequence[tuple[Any, str]]) -> None: ...

    def try_start(self, kind: Any, operation_id: str) -> Any: ...

    def complete_directive(self, kind: Any, operation_id: str, terminal_state: str) -> None: ...

    def halt_requested(self) -> bool: ...
