from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

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


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None = None
    task: str = Field(min_length=1)
    execution_mode: ExecutionMode
    workspace_root: Path
    approval: AgentApproval = Field(default_factory=AgentApproval)
    max_cost_usd: Decimal = Field(default=Decimal("0.05"), ge=Decimal("0"))
    skill_paths: tuple[Path, ...] = ()
    completion_condition: str | None = None

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
    mutation_count: int = Field(default=0, ge=0)
    provider_keys_resolvable: tuple[str, ...] = ()
    plan_hash: str | None = None
    stop_reason: str | None = None
