from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from optimus.runtime.modes import ExecutionMode


class AgentRunStatus(StrEnum):
    PLAN_READY = "plan_ready"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    FAILED = "failed"


class AgentApproval(BaseModel):
    model_config = ConfigDict(frozen=True)

    approved: bool = False
    approval_id: str | None = None
    plan_hash: str | None = None

    @model_validator(mode="after")
    def require_bound_approval(self) -> "AgentApproval":
        if self.approved and (not self.approval_id or not self.plan_hash):
            raise ValueError("approved requests require approval_id and plan_hash")
        return self


class AgentToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    cost_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    authorization_outcome: str = "ALLOW"


class AgentMcpToolOutput:
    """Bounded, safe, untrusted in-memory MCP observation for the next planning turn.

    Distinct from audit-only ``AgentToolCall``. Never a field on ``AgentRunRequest``,
    persisted plans, telemetry events, or ``AgentRunResult``.
    """

    __slots__ = ("server_name", "tool_name", "text", "untrusted")

    def __init__(
        self,
        *,
        server_name: str,
        tool_name: str,
        text: str,
        untrusted: bool = True,
    ) -> None:
        object.__setattr__(self, "server_name", server_name)
        object.__setattr__(self, "tool_name", tool_name)
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "untrusted", bool(untrusted))

    def __setattr__(self, name: str, value: object) -> None:
        raise TypeError("AgentMcpToolOutput is immutable")

    def __delattr__(self, name: str) -> None:
        raise TypeError("AgentMcpToolOutput is immutable")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AgentMcpToolOutput):
            return NotImplemented
        return (
            self.server_name == other.server_name
            and self.tool_name == other.tool_name
            and self.text == other.text
            and self.untrusted == other.untrusted
        )

    def __repr__(self) -> str:
        return (
            f"AgentMcpToolOutput(server_name={self.server_name!r}, "
            f"tool_name={self.tool_name!r}, untrusted={self.untrusted})"
        )


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None = None
    task: str = Field(min_length=1)
    execution_mode: ExecutionMode
    workspace_root: Path
    approval: AgentApproval = Field(default_factory=AgentApproval)
    max_cost_usd: Decimal = Field(default=Decimal("0.05"), ge=Decimal("0"))
    max_planning_turns: int = Field(default=3, ge=1)
    planning_wall_clock_minutes: int = Field(default=30, ge=1)
    skill_paths: tuple[Path, ...] = ()
    completion_condition: str | None = None
    # Plan 12.1 / P11.25-FU-1: prior conversation for the Chat path, rendered
    # separately from ``task`` (which then holds only the current prompt).
    conversation_envelope: str = ""
    # Plan 12.2 Task 9: an attached Context Engine turn. ``task`` holds only the current prompt,
    # ``conversation_envelope`` the rendered view (model history, both modes), ``selection_text``
    # the exact text that selects workspace files and skills (current prompt, exact turns, protected
    # facts; never a summary), and ``context_digest`` the admitted context a stored plan is bound to.
    # None for every engine-absent and non-ACP caller, which keep their existing behavior.
    selection_text: str | None = Field(default=None, min_length=1)
    context_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("execution_mode", mode="before")
    @classmethod
    def normalize_execution_mode(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.upper()
        return value

    @field_validator("workspace_root")
    @classmethod
    def require_absolute_workspace(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("workspace_root must be absolute")
        return value.resolve()


class AgentRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None
    execution_mode: ExecutionMode
    status: AgentRunStatus
    final_state: str = Field(min_length=1)
    output_text: str = Field(min_length=1)
    tool_calls: tuple[AgentToolCall, ...] = ()
    total_cost_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    cost_complete: bool = True
    unknown_cost_attempt_count: int = Field(default=0, ge=0)
    mutation_count: int = Field(default=0, ge=0)
    provider_keys_resolvable: tuple[str, ...] = ()
    plan_hash: str | None = None
    stop_reason: str | None = None
    candidate_plan_text: str | None = None


class ContextPacker(Protocol):
    """Fits one complete model request to its route's usable input (Plan 12.2 Task 9).

    ``build`` renders the complete request around a history envelope. The packer returns the text to
    send: with the admitted view when it fits, otherwise with a smaller view of the same captured
    history within a finite allowance; ``None`` when nothing fits, and then nothing is sent."""

    def fit(self, build: Callable[[str], str]) -> str | None: ...

    def record_dispatch(self, text: str) -> None:
        """Called as `text` is actually sent, once per attempt: the meter reads only real dispatches."""
        ...
