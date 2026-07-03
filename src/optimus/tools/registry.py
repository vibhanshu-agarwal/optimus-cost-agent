from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from optimus.tools.policy import (
    PolicyDecision,
    ToolClass,
    ToolInvocationDecision,
    ToolInvocationPolicy,
    ToolInvocationRequest,
)


@dataclass(frozen=True)
class ToolCallRecord:
    run_id: str
    sequence_number: int
    tool_class: ToolClass
    decision: ToolInvocationDecision


class ToolCallRejected(RuntimeError):
    def __init__(self, decision: ToolInvocationDecision) -> None:
        self.decision = decision
        super().__init__(decision.reason)


class ToolRegistry:
    def __init__(
        self,
        *,
        policy: ToolInvocationPolicy | None = None,
        max_calls_per_run: int = 10,
    ) -> None:
        if max_calls_per_run < 1:
            raise ValueError("max_calls_per_run must be >= 1")
        self._policy = policy or ToolInvocationPolicy()
        self._max_calls_per_run = max_calls_per_run
        self._lock = Lock()
        self._records_by_run: dict[str, list[ToolCallRecord]] = {}
        self._search_urls_by_run: dict[str, set[str]] = {}

    def authorize_and_record_call(self, request: ToolInvocationRequest) -> ToolCallRecord:
        decision = self._policy.authorize(request)
        with self._lock:
            if decision.decision is PolicyDecision.REJECT:
                raise ToolCallRejected(decision)

            records = self._records_by_run.setdefault(request.run_id, [])
            if len(records) >= self._max_calls_per_run:
                raise ToolCallRejected(
                    ToolInvocationDecision(
                        decision=PolicyDecision.REJECT,
                        reason="max_calls_per_run exceeded",
                        tool_class=request.tool_class,
                        policy_signal=request.policy_signal,
                        reason_code=request.reason,
                    )
                )

            record = ToolCallRecord(
                run_id=request.run_id,
                sequence_number=len(records) + 1,
                tool_class=request.tool_class,
                decision=decision,
            )
            records.append(record)
            return record

    def record_search_results(self, *, run_id: str, urls: tuple[str, ...]) -> None:
        with self._lock:
            self._search_urls_by_run.setdefault(run_id, set()).update(urls)

    def search_result_urls(self, run_id: str) -> frozenset[str]:
        with self._lock:
            return frozenset(self._search_urls_by_run.get(run_id, set()))

    def call_count(self, run_id: str) -> int:
        with self._lock:
            return len(self._records_by_run.get(run_id, []))

    def records(self, run_id: str) -> tuple[ToolCallRecord, ...]:
        with self._lock:
            return tuple(self._records_by_run.get(run_id, ()))
