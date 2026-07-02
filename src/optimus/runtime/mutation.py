from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from optimus.runtime.modes import ExecutionMode

if TYPE_CHECKING:
    from optimus.runtime.state import RuntimeContext

MUTATION_FORBIDDEN_CODE = -32002


class MutationKind(StrEnum):
    WRITE_FILE = "write_file"
    SHELL_EXEC = "shell_exec"
    # Shadow application of a candidate patch or diff without committing it
    # to the working tree; still treated as a mutation for guard purposes.
    SHADOW_APPLY = "shadow_apply"


@dataclass(frozen=True)
class MutationForbidden(Exception):
    message: str
    code: int = MUTATION_FORBIDDEN_CODE

    def __str__(self) -> str:
        return self.message


class MutationGuard:
    def assert_allowed(self, context: RuntimeContext, kind: MutationKind) -> None:
        from optimus.runtime.state import AgentState

        if context.execution_mode in {ExecutionMode.PLAN, ExecutionMode.CHAT}:
            raise MutationForbidden("mutation forbidden in Plan/Chat mode")
        if context.execution_mode is not ExecutionMode.AGENT:
            raise MutationForbidden(f"unknown execution mode: {context.execution_mode}")
        if not context.approval_granted or context.user_approval_id is None:
            raise MutationForbidden("approval required before mutation")
        if context.state not in {AgentState.EXECUTING, AgentState.TOOL_CALLING, AgentState.VALIDATING}:
            raise MutationForbidden(f"mutation not allowed from state {context.state.value}")


def assert_mutation_allowed(context: RuntimeContext, kind: MutationKind) -> None:
    MutationGuard().assert_allowed(context, kind)
