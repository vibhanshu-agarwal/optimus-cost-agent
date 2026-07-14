from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoopStopReason(StrEnum):
    COMPLETED = "COMPLETED"
    MAX_ITERATIONS = "MAX_ITERATIONS"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    WALL_CLOCK = "WALL_CLOCK"
    REPEATED_FAILURE = "REPEATED_FAILURE"
    HUMAN_HALT = "HUMAN_HALT"


class LoopBudgetPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_iterations: int = Field(ge=1)
    max_budget_credits: Decimal = Field(gt=Decimal("0"))
    max_wall_clock_minutes: int = Field(ge=1)
    repeated_failure_limit: int = Field(default=3, ge=2)


class CompletionEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    completed: bool
    reason: str = Field(min_length=1)
    confidence: Decimal = Field(default=Decimal("1"), ge=Decimal("0"), le=Decimal("1"))
    cost_credits: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    gateway_request_id: str | None = None


class IterationOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary: str = Field(min_length=1)
    cost_credits: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    failure_signature: str | None = None
    deterministic_completion: bool = False
    evidence: dict[str, str] = Field(default_factory=dict)


class CompletionEvaluatorProtocol(Protocol):
    def evaluate(self, state: "IterationState", ledger: Any) -> CompletionEvaluation:
        raise NotImplementedError


class LoopToolExecutorProtocol(Protocol):
    """Marker protocol for guarded loop tool bundles passed through the controller."""


class IterationState(BaseModel):
    """
    Represents the state of an iteration in a process, managing data such as runtime, budget, and
    progress. Ensures validity of time-aware datetime and provides methods for updating the state
    based on outcomes and evaluations.

    This class is designed to encapsulate iteration information, calculate elapsed time, track
    progress, and provide mechanisms for handling runtime limits, failures, and halt requests.

    :ivar run_id: Unique identifier for the run.
    :type run_id: str
    :ivar session_id: Identifier for the session, if applicable.
    :type session_id: str | None
    :ivar goal: Description of the goal for the iteration.
    :type goal: str
    :ivar completion_condition: Criteria defining what constitutes completion for this iteration.
    :type completion_condition: str
    :ivar started_at: Datetime when the iteration started, must be timezone-aware.
    :type started_at: datetime
    :ivar deadline_at: Optional deadline for completing the iteration.
    :type deadline_at: datetime | None
    :ivar remaining_budget_credits: Remaining budget credits for the iteration, if applicable.
    :type remaining_budget_credits: Decimal | None
    :ivar iteration: Counter tracking the current iteration cycle.
    :type iteration: int
    :ivar credits_spent: Total credits spent up to the current iteration.
    :type credits_spent: Decimal
    :ivar last_failure_signature: Identifier for the last failure signature, if any.
    :type last_failure_signature: str | None
    :ivar repeated_failure_count: Count of consecutive failures with the same signature.
    :type repeated_failure_count: int
    :ivar human_halt_requested: Indicates whether a halt has been requested by a human.
    :type human_halt_requested: bool
    """
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None
    goal: str = Field(min_length=1)
    completion_condition: str = Field(min_length=1)
    started_at: datetime
    deadline_at: datetime | None = None
    remaining_budget_credits: Decimal | None = None
    iteration: int = Field(default=0, ge=0)
    credits_spent: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    last_failure_signature: str | None = None
    repeated_failure_count: int = Field(default=0, ge=0)
    human_halt_requested: bool = False

    @field_validator("started_at")
    @classmethod
    def require_timezone_aware_started_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        return value

    def record_outcome(self, outcome: IterationOutcome) -> "IterationState":
        repeated = 0
        if outcome.failure_signature is not None:
            repeated = self.repeated_failure_count + 1 if outcome.failure_signature == self.last_failure_signature else 1
        return self.model_copy(
            update={
                "iteration": self.iteration + 1,
                "credits_spent": self.credits_spent + outcome.cost_credits,
                "last_failure_signature": outcome.failure_signature,
                "repeated_failure_count": repeated,
            }
        )

    def record_completion_evaluation(self, evaluation: CompletionEvaluation) -> "IterationState":
        return self.model_copy(update={"credits_spent": self.credits_spent + evaluation.cost_credits})

    def request_halt(self) -> "IterationState":
        return self.model_copy(update={"human_halt_requested": True})

    def with_runtime_limits(self, *, policy: LoopBudgetPolicy) -> "IterationState":
        deadline_at = self.started_at + timedelta(minutes=policy.max_wall_clock_minutes)
        remaining = max(Decimal("0"), policy.max_budget_credits - self.credits_spent)
        return self.model_copy(update={"deadline_at": deadline_at, "remaining_budget_credits": remaining})

    def elapsed_minutes(self, *, now: datetime) -> int:
        elapsed = now - self.started_at
        return max(0, int(elapsed.total_seconds() // 60))
