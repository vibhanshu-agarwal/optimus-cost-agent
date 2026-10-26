"""Contract-bound scenario doubles and their narrowly scoped unexpected-call logs."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial
from inspect import isfunction
from typing import NoReturn
from unittest.mock import NonCallableMock, create_autospec

from optimus.agent.runner import AgentRunner


@dataclass
class ContractCallLog:
    label: str
    calls: list[str] = field(default_factory=list)
    expected: tuple[str, ...] = ()

    def expect(self, *operations: str) -> None:
        if self.calls:
            raise ValueError("declare expected contract calls before exercising the boundary")
        self.expected = operations

    def reject(self, operation: str, *_args, **_kwargs) -> NoReturn:
        self.calls.append(operation)
        raise AssertionError(f"unscripted {self.label}.{operation}")


_active_logs: list[ContractCallLog] | None = None


@contextmanager
def contract_call_scope():
    global _active_logs
    if _active_logs is not None:
        raise RuntimeError("contract call scopes must not overlap in one test process")
    logs: list[ContractCallLog] = []
    _active_logs = logs
    try:
        yield logs
    finally:
        _active_logs = None
        assert_contract_calls(logs)


def new_contract_call_log(label: str) -> ContractCallLog:
    if _active_logs is None:
        raise RuntimeError("contract boundary constructed outside its owning pytest fixture")
    log = ContractCallLog(label)
    _active_logs.append(log)
    return log


def checked_agent_runner(script: object) -> AgentRunner:
    if isinstance(script, (NonCallableMock, AgentRunner)):
        raise TypeError("expected a scripted observer, not a real or already checked AgentRunner")
    if not callable(getattr(script, "run", None)):
        raise TypeError("scripted observer must supply a callable run")
    checked = create_autospec(AgentRunner, instance=True, spec_set=True)
    calls = new_contract_call_log("AgentRunner")
    for name, member in vars(AgentRunner).items():
        if name != "run" and not name.startswith("__") and isfunction(member):
            getattr(checked, name).side_effect = partial(calls.reject, name)
    checked.event_sink = None
    checked.run.side_effect = lambda *args, **kwargs: script.run(*args, **kwargs)
    return checked


def assert_contract_calls(logs: list[ContractCallLog]) -> None:
    mismatches = [(log.label, log.calls, log.expected) for log in logs if tuple(log.calls) != log.expected]
    assert not mismatches, f"unexpected contract calls (actual, expected): {mismatches!r}"
