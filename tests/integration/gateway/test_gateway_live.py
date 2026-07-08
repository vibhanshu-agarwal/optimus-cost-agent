from __future__ import annotations

import os
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from optimus.acp.preflight import PreflightFailure, run_preflight
from optimus.agent.directives import AgentDirectiveParseError, parse_agent_plan
from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunResult, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.redis.async_bridge import sync_await
from optimus.redis.runtime import RedisRuntime
from optimus.runtime.modes import ExecutionMode
from optimus.telemetry.redis_sink import RedisTelemetryEventSink

pytestmark = pytest.mark.requires_gateway

_LIVE_HAIKU_MODEL = "claude-haiku"
_DEFAULT_LIVE_MAX_COST_USD = Decimal("0.25")
_CALCULATOR_TASK = (
    "Create a file `calculator.py` with exactly these functions: "
    "`add(a, b)`, `subtract(a, b)`, `multiply(a, b)`, `divide(a, b)`. "
    "Each returns the numeric result of that operation on its two arguments. "
    "No classes, no CLI wrapper, no extra functions. "
    "Write only `calculator.py`; do not create any other files or tests."
)
_CALCULATOR_CHECKS: tuple[tuple[str, str], ...] = (
    ("add(2, 3)", "5"),
    ("subtract(10, 4)", "6"),
    ("multiply(3, 4)", "12"),
    ("divide(10, 2)", "5"),
)


def _live_max_cost_usd() -> Decimal:
    raw = os.environ.get("OPTIMUS_LIVE_MAX_COST_USD", "").strip()
    if not raw:
        return _DEFAULT_LIVE_MAX_COST_USD
    return Decimal(raw)


def _assert_cost_within_cap(cost_usd: Decimal) -> None:
    cap = _live_max_cost_usd()
    assert cost_usd <= cap, f"live gateway cost {cost_usd} exceeded OPTIMUS_LIVE_MAX_COST_USD cap {cap}"


def _delete_plan_keys(runtime: RedisRuntime, run_id: str) -> None:
    client = runtime.sync_state_store().redis_client

    async def _delete() -> None:
        async for key in client.scan_iter(match=f"agent:plan:{run_id}*"):
            await client.delete(key)

    sync_await(_delete())


def _require_gateway_client() -> GatewayClient:
    try:
        run_preflight(os.environ)
    except PreflightFailure as exc:
        pytest.fail(exc.user_message)
    return GatewayClient(settings=OptimusGatewaySettings.from_env())


def _build_live_agent_runner(
    workspace_root: Path,
    *,
    model: str = _LIVE_HAIKU_MODEL,
) -> tuple[AgentRunner, RedisRuntime]:
    redis_url = run_preflight(os.environ, workspace_root=workspace_root, require_timeseries=True)
    runtime = RedisRuntime.from_url(redis_url)
    settings = OptimusGatewaySettings.from_env()
    resolved_workspace = workspace_root.resolve()
    guard = PreToolGuard.for_workspace(workspace_root=resolved_workspace, allowed_network_hosts=())
    runner = AgentRunner(
        gateway_client=GatewayClient(settings=settings),
        model=model,
        guard=guard,
        state_store=runtime.sync_state_store(),
        event_sink=RedisTelemetryEventSink(runtime.telemetry_adapter()),
    )
    return runner, runtime


def _directive_parse_outcome(output_text: str) -> str:
    try:
        parse_agent_plan(output_text)
    except AgentDirectiveParseError:
        return "UNPARSEABLE_PLAN"
    return "PARSED"


def _run_plan_mode_once(
    runner: AgentRunner,
    *,
    workspace_root: Path,
    task: str,
    run_id: str,
) -> tuple[AgentRunResult, str]:
    result = runner.run(
        AgentRunRequest(
            run_id=run_id,
            session_id=None,
            task=task,
            execution_mode=ExecutionMode.PLAN,
            workspace_root=workspace_root,
            max_cost_usd=_live_max_cost_usd(),
        )
    )
    return result, _directive_parse_outcome(result.output_text)


def _assert_calculator_subprocess(workspace: Path, expression: str, expected: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-c", f"import calculator; print(calculator.{expression})"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, (
        f"calculator.{expression} subprocess failed "
        f"(exit={completed.returncode}, stderr={completed.stderr!r}, stdout={completed.stdout!r})"
    )
    actual = completed.stdout.strip()
    try:
        assert float(actual) == float(expected)
    except ValueError as exc:
        raise AssertionError(
            f"calculator.{expression} expected numeric {expected!r}, got non-numeric {actual!r}"
        ) from exc


def _fail_with_calculator_source(workspace: Path, message: str) -> None:
    calculator_path = workspace / "calculator.py"
    if calculator_path.is_file():
        source = calculator_path.read_text(encoding="utf-8")
        pytest.fail(f"{message}\n\ncalculator.py:\n{source}")
    pytest.fail(f"{message}\n\ncalculator.py was not created under {workspace}")


def test_live_gateway_minimal_response_reports_usage_fields() -> None:
    client = _require_gateway_client()

    response = client.create_response(
        model=_LIVE_HAIKU_MODEL,
        input_text="Reply with one short word.",
        metadata={"purpose": "live_gateway_minimal_probe"},
    )

    assert response.response_id
    assert response.gateway_usage.cost_usd >= Decimal("0")
    assert response.gateway_usage.gateway_request_id
    assert response.gateway_usage.provider
    assert response.output_text.strip()
    _assert_cost_within_cap(response.gateway_usage.cost_usd)


def test_live_planning_pass_records_directive_or_unparseable_with_one_retry(tmp_path: Path) -> None:
    workspace = tmp_path.resolve()
    example = workspace / "example.py"
    example.write_text("def f():\n    return 1\n", encoding="utf-8")
    client = _require_gateway_client()
    runner = AgentRunner(gateway_client=client, model=_LIVE_HAIKU_MODEL)
    task = "Explain the function in example.py"
    run_id = f"live-plan-{uuid.uuid4().hex}"

    result, outcome = _run_plan_mode_once(
        runner,
        workspace_root=workspace,
        task=task,
        run_id=run_id,
    )
    total_cost = result.total_cost_usd

    if outcome == "UNPARSEABLE_PLAN":
        retry_result, retry_outcome = _run_plan_mode_once(
            runner,
            workspace_root=workspace,
            task=task,
            run_id=f"{run_id}:retry",
        )
        total_cost += retry_result.total_cost_usd
        if retry_outcome == "UNPARSEABLE_PLAN":
            pytest.fail(
                "Model returned UNPARSEABLE_PLAN after one retry.\n\n"
                f"First output:\n{result.output_text}\n\n"
                f"Retry output:\n{retry_result.output_text}"
            )
        result = retry_result
        outcome = retry_outcome

    _assert_cost_within_cap(total_cost)
    assert outcome == "PARSED", result.output_text
    assert result.status is AgentRunStatus.COMPLETED
    assert result.final_state == "CHAT_ONLY"


def test_live_agent_writes_working_calculator(tmp_path: Path) -> None:
    workspace = tmp_path.resolve()
    runner, runtime = _build_live_agent_runner(workspace)
    run_id = f"live-calc-{uuid.uuid4().hex}"
    total_cost = Decimal("0")
    try:
        plan_result = runner.run(
            AgentRunRequest(
                run_id=run_id,
                session_id=None,
                task=_CALCULATOR_TASK,
                execution_mode=ExecutionMode.AGENT,
                workspace_root=workspace,
                max_cost_usd=_live_max_cost_usd(),
            )
        )
        total_cost += plan_result.total_cost_usd
        _assert_cost_within_cap(total_cost)

        if plan_result.stop_reason == "UNPARSEABLE_PLAN":
            pytest.fail(f"Model returned UNPARSEABLE_PLAN:\n{plan_result.output_text}")
        assert plan_result.status is AgentRunStatus.AWAITING_APPROVAL, plan_result.output_text
        assert plan_result.plan_hash is not None

        approved_result = runner.run(
            AgentRunRequest(
                run_id=run_id,
                session_id=None,
                task=_CALCULATOR_TASK,
                execution_mode=ExecutionMode.AGENT,
                workspace_root=workspace,
                approval=AgentApproval(
                    approved=True,
                    approval_id=f"{run_id}:approval",
                    plan_hash=plan_result.plan_hash,
                ),
                max_cost_usd=_live_max_cost_usd(),
            )
        )
        total_cost += approved_result.total_cost_usd
        _assert_cost_within_cap(total_cost)

        if approved_result.status is not AgentRunStatus.COMPLETED:
            _fail_with_calculator_source(
                workspace,
                f"Agent run did not complete (status={approved_result.status}, "
                f"stop_reason={approved_result.stop_reason!r}, final_state={approved_result.final_state!r})",
            )

        calculator_path = workspace / "calculator.py"
        if not calculator_path.is_file():
            _fail_with_calculator_source(workspace, "calculator.py was not written after approval")

        for expression, expected in _CALCULATOR_CHECKS:
            try:
                _assert_calculator_subprocess(workspace, expression, expected)
            except AssertionError as exc:
                _fail_with_calculator_source(workspace, str(exc))
    finally:
        _delete_plan_keys(runtime, run_id)
        runtime.close()
