#!/usr/bin/env python3
"""Smoke-check that Redis-backed plan replay works with the real agent runner."""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from optimus.acp.bootstrap import StartupConfigurationError, build_configured_server
from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import RedisAgentStateStore
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.runtime.modes import ExecutionMode


class _SmokeGateway:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text
        self.calls = 0

    def create_response(self, *, model: str, input_text: str, metadata=None):
        self.calls += 1
        from decimal import Decimal

        from optimus.gateway.models import GatewayResponse, GatewayUsage

        return GatewayResponse(
            response_id="resp-smoke",
            output_text=self.output_text,
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-smoke",
                provider="glm",
                billing_units=1,
                cost_usd=Decimal("0.001"),
            ),
            raw={"id": "resp-smoke"},
        )


def _cleanup(store: RedisAgentStateStore, run_id: str) -> None:
    client = store._client
    for key in client.scan_iter(match=f"agent:plan:{run_id}*"):
        client.delete(key)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Redis-backed Optimus agent replay.")
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--redis-url", default=None, help="Defaults to OPTIMUS_REDIS_URL or redis://127.0.0.1:6379/0")
    parser.add_argument("--skip-bootstrap-check", action="store_true")
    args = parser.parse_args()

    workspace = args.workspace_root.resolve()
    redis_url = args.redis_url
    if redis_url is None:
        import os

        redis_url = os.environ.get("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")

    print(f"workspace: {workspace}")
    print(f"redis: {redis_url}")

    try:
        store = RedisAgentStateStore.from_url(redis_url)
        store.ping()
    except Exception as exc:
        print(f"FAIL: Redis is not reachable: {exc}")
        return 2

    if not args.skip_bootstrap_check:
        import os

        environ = dict(os.environ)
        environ.setdefault("OPTIMUS_GATEWAY_URL", "https://gateway.optimus.ai")
        environ.setdefault("OPTIMUS_API_KEY", "opt-smoke")
        environ["OPTIMUS_REDIS_URL"] = redis_url
        try:
            build_configured_server(environ=environ, workspace_root=workspace)
        except StartupConfigurationError as exc:
            print(f"FAIL: bootstrap startup check failed: {exc.user_message}")
            return exc.exit_code

    run_id = f"smoke-{uuid.uuid4().hex}"
    target = workspace / "example-smoke.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    plan_text = f'WRITE {target.name}\ndef f():\n    """Smoke test."""\n    return 1\n'
    guard = PreToolGuard.for_workspace(workspace_root=workspace, allowed_network_hosts=())

    try:
        planner_gateway = _SmokeGateway(plan_text)
        planner = AgentRunner(gateway_client=planner_gateway, model="glm-5.2", guard=guard, state_store=store)
        plan_result = planner.run(
            AgentRunRequest(
                run_id=run_id,
                task="Smoke test docstring",
                execution_mode=ExecutionMode.AGENT,
                workspace_root=workspace,
            )
        )
        if plan_result.status is not AgentRunStatus.AWAITING_APPROVAL:
            print(f"FAIL: expected awaiting_approval, got {plan_result.status}")
            return 1

        replay_gateway = _SmokeGateway("WRITE example-smoke.py\nBROKEN\n")
        replay_runner = AgentRunner(
            gateway_client=replay_gateway,
            model="glm-5.2",
            guard=guard,
            state_store=RedisAgentStateStore.from_url(redis_url),
        )
        approved = replay_runner.run(
            AgentRunRequest(
                run_id=run_id,
                task="Smoke test docstring",
                execution_mode=ExecutionMode.AGENT,
                workspace_root=workspace,
                approval=AgentApproval(
                    approved=True,
                    approval_id="smoke-approval",
                    plan_hash=plan_result.plan_hash,
                ),
            )
        )
        if approved.status is not AgentRunStatus.COMPLETED:
            print(f"FAIL: expected completed, got {approved.status} ({approved.stop_reason})")
            return 1
        if replay_gateway.calls != 0:
            print(f"FAIL: replay called gateway {replay_gateway.calls} times")
            return 1
        if "Smoke test" not in target.read_text(encoding="utf-8"):
            print("FAIL: target file was not mutated")
            return 1
    finally:
        _cleanup(store, run_id)
        if target.exists():
            target.unlink()

    print("PASS: Redis-backed plan store, approval replay, and file mutation verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
