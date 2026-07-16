"""Operator live-agent sign-off session driver.

Plan 9.96, Task 5 Batch 3 (`operator_verify.py` threading): the spawned
`python -m optimus.acp` child now runs through the gated __main__.py launch
gate. Before running this tool for the first time, author a durable
approval for the scratch verify workspace (`reports/.verify-live-agent-workspace`
under the repository root, by default) in a TTY so you can review the
effective configuration before it launches:

    optimus-trust --workspace-root reports/.verify-live-agent-workspace approve --mode durable

Deliberately NOT auto-approved: creating the approval from inside this tool
(from the same environment it is about to launch) would make the approval
tautological — it would always match, so the gate's actual purpose (a human
reviewing the effective configuration before launch) would be defeated. This
tool is therefore "just another gated launch," per Task 5's design.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from optimus.acp.e2e_transcript import PLAN_9_6_LIVE_AGENT_TRANSCRIPT_PATH, E2eAcpTranscriptWriter
from optimus.acp.ndjson_subprocess_session import LiveSessionError, NdjsonSubprocessSession
from optimus.acp.preflight import (
    PreflightCheckResult,
    collect_preflight_checks,
    first_preflight_failure,
    format_preflight_table,
)
from optimus.acp.subprocess_env import SubprocessEnvConfigurationError, build_acp_subprocess_env
from optimus.agent.defaults import resolve_agent_model
from optimus.agent.directives import AgentDirectiveParseError, parse_agent_plan
from optimus.agent.prompts import AGENT_PLANNER_PROMPT_VERSION
from optimus.agent.state_store import RedisAgentStateStore
from optimus.redis.async_bridge import sync_await

DEFAULT_VERIFY_TASK = (
    "Add a module docstring to `example.py` describing its function. "
    "Modify only `example.py`; do not create any other files or tests."
)
_DEFAULT_EXAMPLE_SOURCE = "def greet():\n    return 'hello'\n"
_WALL_CLOCK_TIMEOUT_SECONDS = 120
_VERIFY_WORKSPACE_DIRNAME = ".verify-live-agent-workspace"


def default_verify_workspace_root(repository_root: Path) -> Path:
    return (repository_root / "reports" / _VERIFY_WORKSPACE_DIRNAME).resolve()


def default_live_agent_transcript_path(repository_root: Path) -> Path:
    return (repository_root / PLAN_9_6_LIVE_AGENT_TRANSCRIPT_PATH).resolve()


@dataclass(frozen=True)
class OperatorLiveSessionConfig:
    workspace_root: Path
    repository_root: Path
    model: str
    task: str
    transcript_path: Path
    plan_only: bool = False
    require_manual_approval: bool = False
    wall_clock_timeout_seconds: int = _WALL_CLOCK_TIMEOUT_SECONDS


@dataclass
class OperatorLiveSessionResult:
    success: bool
    failure_message: str = ""
    model: str = ""
    prompt_version: str = AGENT_PLANNER_PROMPT_VERSION
    plan_hash: str = ""
    approval_id: str | None = None
    tool_trajectory: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    total_cost_usd: Decimal = Decimal("0")
    stop_reason: str = ""
    run_id: str = ""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the Optimus live agent end to end. Requires a one-time durable approval "
            "for the verify workspace first: optimus-trust --workspace-root "
            "reports/.verify-live-agent-workspace approve --mode durable"
        )
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help=(
            "Scratch workspace for the live session (default: "
            "reports/.verify-live-agent-workspace under the project root). "
            "The default task creates or mutates example.py inside this directory."
        ),
    )
    parser.add_argument("--model", default=None, help="Gateway model override (defaults to OPTIMUS_AGENT_MODEL).")
    parser.add_argument("--task", default=None, help="Task prompt for the live session.")
    parser.add_argument("--plan-only", action="store_true", help="Plan and stop before approval or mutation.")
    parser.add_argument(
        "--require-manual-approval",
        action="store_true",
        help="Print the plan and wait for operator y/n approval on stdin.",
    )
    parser.add_argument(
        "--transcript-path",
        type=Path,
        default=None,
        help="Write the live-session transcript to this path (default: reports/plan-9-6-live-agent-transcript.json).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, repository_root: Path) -> int:
    """
    Main entry point for the application. This function orchestrates the live verification
    process and ensures all preliminary checks and configurations are in place before invoking
    the live session. It processes input arguments, validates the workspace and environment,
    executes the live verification session, and handles errors or failures if they occur.

    :param argv: List of command-line arguments to be parsed for initializing the session.
                  Pass None to default to `sys.argv`.
    :type argv: list[str] or None
    :return: Exit status of the verification process. Zero indicates success, whereas non-zero
             values indicate specific errors or failures.
    :rtype: int
    """
    args = parse_args(argv)
    repository_root = repository_root.resolve()
    workspace = (args.workspace_root or default_verify_workspace_root(repository_root)).resolve()
    model = resolve_agent_model(os.environ, cli_model=args.model)
    task = (args.task or DEFAULT_VERIFY_TASK).strip()

    ensure_verify_workspace(workspace)
    checks = collect_preflight_checks(
        os.environ,
        workspace_root=workspace,
        strict=True,
        require_timeseries=True,
    )
    print(format_preflight_table(checks))
    failed = first_preflight_failure(checks)
    if failed is not None:
        print(f"\nPre-flight failed: {failed.detail}", file=sys.stderr)
        print(_operator_action_message(failed), file=sys.stderr)
        return 2

    before_snapshot = snapshot_workspace_text_files(workspace)
    transcript_path = (args.transcript_path or default_live_agent_transcript_path(repository_root)).resolve()
    config = OperatorLiveSessionConfig(
        workspace_root=workspace,
        repository_root=repository_root,
        model=model,
        task=task,
        transcript_path=transcript_path,
        plan_only=args.plan_only,
        require_manual_approval=args.require_manual_approval,
    )
    transcript = E2eAcpTranscriptWriter()
    try:
        result = run_operator_live_session(config, environ=os.environ, transcript=transcript)
    except (LiveSessionError, SubprocessEnvConfigurationError) as exc:
        transcript.write(config.transcript_path)
        print(str(exc), file=sys.stderr)
        return 3

    result.files_changed = changed_workspace_files(before_snapshot, snapshot_workspace_text_files(workspace))
    result.tool_trajectory = tool_trajectory_from_transcript(transcript)
    transcript.write(config.transcript_path)
    print()
    print(format_session_summary(result))
    if not result.success:
        print(result.failure_message, file=sys.stderr)
        return 3
    print("PASS: Optimus live agent verification completed.")
    return 0


def ensure_verify_workspace(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    example = workspace / "example.py"
    if not example.exists():
        example.write_text(_DEFAULT_EXAMPLE_SOURCE, encoding="utf-8")
    if not (workspace / ".git").exists():
        git_executable = shutil.which("git")
        if git_executable is None:
            raise LiveSessionError("git not found on PATH; required to initialize verify workspace")
        completed = subprocess.run(
            [git_executable, "init"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise LiveSessionError(f"git init failed in workspace: {completed.stderr}")


def run_operator_live_session(
    config: OperatorLiveSessionConfig,
    *,
    environ: Mapping[str, str],
    transcript: E2eAcpTranscriptWriter,
    approval_callback: Callable[[str], bool] | None = None,
) -> OperatorLiveSessionResult:
    """
    Executes a live operator session for a specified task, handling interaction
    with a subprocess-driven model and ensuring proper session lifecycle
    management.

    This function initializes a communication session with the model, sends
    prompts for task execution, handles retries for specific conditions, and
    tracks the resulting plan's execution cost. If specified, the function
    can limit execution to plan generation only or require manual approval
    through a callback mechanism.

    :param config: Configuration object for the operator live session,
        encapsulating session details such as task, model, workspace, and timeout.
    :type config: OperatorLiveSessionConfig
    :param environ: Environment variables used to set up the session
        and subprocess execution.
    :type environ: Mapping[str, str]
    :param transcript: Transcript writer used to log communication and outputs
        between the client and the subprocess.
    :type transcript: E2eAcpTranscriptWriter
    :param approval_callback: Optional callback function for manual approval
        of plans. It takes a string as input and returns a boolean indicating
        approval or rejection.
    :type approval_callback: Callable[[str], bool] | None
    :return: Result of the operator live session, including the model used,
        plan details, execution costs, and session stop reasons.
    :rtype: OperatorLiveSessionResult
    """
    redis_url = environ["OPTIMUS_REDIS_URL"].strip()
    redis_store = RedisAgentStateStore.from_url(redis_url)
    subprocess_env = build_acp_subprocess_env(operator_environ=environ)
    deadline = time.monotonic() + config.wall_clock_timeout_seconds
    run_ids: set[str] = set()
    process: subprocess.Popen[str] | None = None
    session: NdjsonSubprocessSession | None = None

    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "optimus.acp",
                "--workspace-root",
                str(config.workspace_root),
                "--model",
                config.model,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=subprocess_env,
            text=True,
            bufsize=1,
        )
        session = NdjsonSubprocessSession(process=process, transcript=transcript)

        session.send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": 1,
                    "clientCapabilities": {
                        "fs": {"readTextFile": True, "writeTextFile": True},
                        "terminal": True,
                    },
                    "clientInfo": {"name": "verify-live-agent", "version": "1.0.0"},
                },
            }
        )
        initialize_response = session.wait_for_response(1, deadline=deadline)
        if initialize_response.get("result", {}).get("protocolVersion") != 1:
            return _failure("initialize response missing protocolVersion=1")

        session.send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/new",
                "params": {"cwd": str(config.workspace_root), "mcpServers": []},
            }
        )
        session_response = session.wait_for_response(2, deadline=deadline)
        session_id = session_response.get("result", {}).get("sessionId")
        if not session_id:
            return _failure("session/new response missing sessionId")

        prompt_response, run_id, outcome = _run_prompt_turn(
            session=session,
            session_id=str(session_id),
            prompt_request_id=3,
            task=config.task,
            deadline=deadline,
            redis_store=redis_store,
            transcript=transcript,
            plan_only=config.plan_only,
            require_manual_approval=config.require_manual_approval,
            approval_callback=approval_callback,
        )
        run_ids.add(run_id)

        if outcome == "UNPARSEABLE_PLAN":
            first_output = latest_plan_text_from_transcript(transcript)
            retry_response, retry_run_id, retry_outcome = _run_prompt_turn(
                session=session,
                session_id=str(session_id),
                prompt_request_id=4,
                task=config.task,
                deadline=deadline,
                redis_store=redis_store,
                transcript=transcript,
                plan_only=config.plan_only,
                require_manual_approval=config.require_manual_approval,
                approval_callback=approval_callback,
            )
            run_ids.add(retry_run_id)
            if retry_outcome == "UNPARSEABLE_PLAN":
                retry_output = latest_plan_text_from_transcript(transcript)
                return _failure(
                    "Model returned UNPARSEABLE_PLAN after one retry.\n\n"
                    f"First output:\n{first_output}\n\nRetry output:\n{retry_output}"
                )
            prompt_response = retry_response
            run_id = retry_run_id

        if config.plan_only:
            loaded = redis_store.latest_plan_for_run(run_id=run_id)
            cost = loaded.cost_usd if loaded is not None else Decimal("0")
            plan_hash = _plan_hash_from_transcript(transcript) or (loaded.plan_hash if loaded else "")
            return OperatorLiveSessionResult(
                success=True,
                model=config.model,
                plan_hash=plan_hash,
                total_cost_usd=cost,
                stop_reason="plan_only",
                run_id=run_id,
            )

        stop_reason = prompt_response.get("result", {}).get("stopReason", "")
        if stop_reason != "end_turn":
            return _failure(f"expected stopReason=end_turn, got {stop_reason!r}")

        loaded = redis_store.latest_plan_for_run(run_id=run_id)
        cost = loaded.cost_usd if loaded is not None else Decimal("0")
        plan_hash = _plan_hash_from_transcript(transcript) or (loaded.plan_hash if loaded else "")
        approval_id = _approval_id_from_transcript(transcript)
        return OperatorLiveSessionResult(
            success=True,
            model=config.model,
            plan_hash=plan_hash,
            approval_id=approval_id,
            total_cost_usd=cost,
            stop_reason=stop_reason,
            run_id=run_id,
        )
    finally:
        if session is not None:
            session.close_stdin()
            session.terminate()
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for tracked_run_id in run_ids:
            _delete_plan_keys(redis_store.redis_client, tracked_run_id)


def format_session_summary(result: OperatorLiveSessionResult) -> str:
    return "\n".join(
        [
            "Optimus live agent verification summary",
            f"model: {result.model}",
            f"prompt_version: {result.prompt_version}",
            f"plan_hash: {result.plan_hash}",
            f"approval_id: {result.approval_id or '(none)'}",
            f"tool_trajectory: {', '.join(result.tool_trajectory) or '(none)'}",
            f"files_changed: {', '.join(result.files_changed) or '(none)'}",
            f"total_cost_usd: {result.total_cost_usd}",
            f"stop_reason: {result.stop_reason}",
        ]
    )


def snapshot_workspace_text_files(workspace: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(workspace.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        try:
            files[path.relative_to(workspace).as_posix()] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return files


def changed_workspace_files(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    changed: list[str] = []
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changed.append(key)
    return changed


def tool_trajectory_from_transcript(transcript: E2eAcpTranscriptWriter) -> list[str]:
    trajectory: list[str] = []
    for line in transcript.lines:
        if line["direction"] != "inbound":
            continue
        message = line["message"]
        if message.get("method") != "session/update":
            continue
        update = message.get("params", {}).get("update", {})
        if update.get("sessionUpdate") not in {"tool_call", "tool_call_update"}:
            continue
        title = update.get("title") or update.get("toolCall", {}).get("title")
        if title:
            trajectory.append(str(title))
    return trajectory


def latest_plan_text_from_transcript(transcript: E2eAcpTranscriptWriter) -> str:
    for line in reversed(transcript.lines):
        if line["direction"] != "inbound":
            continue
        message = line["message"]
        if message.get("method") != "session/update":
            continue
        update = message.get("params", {}).get("update", {})
        if update.get("sessionUpdate") != "plan":
            continue
        entries = update.get("entries")
        if isinstance(entries, list) and entries:
            lines = [
                str(entry.get("content", "")).strip()
                for entry in entries
                if isinstance(entry, dict) and str(entry.get("content", "")).strip()
            ]
            if lines:
                return "\n".join(lines)
        blocks = update.get("content", [])
        texts = [block["text"] for block in blocks if isinstance(block, dict) and block.get("type") == "text"]
        if texts:
            return "\n".join(texts)
    return ""


def _run_prompt_turn(
    *,
    session: NdjsonSubprocessSession,
    session_id: str,
    prompt_request_id: int,
    task: str,
    deadline: float,
    redis_store: RedisAgentStateStore,
    transcript: E2eAcpTranscriptWriter,
    plan_only: bool,
    require_manual_approval: bool,
    approval_callback: Callable[[str], bool] | None,
) -> tuple[dict, str, str]:
    """
    Executes a single turn of a prompt workflow by interacting with a session, handling
    permission requests, and processing prompt responses. It ensures appropriate approvals
    and handles unparseable plans or errors that may arise during the session while
    communicating with Redis for state management.

    :param session: The NdjsonSubprocessSession instance managing the prompt workflow.
    :param session_id: Unique identifier for the current session.
    :param prompt_request_id: Identifier for the prompt request being processed.
    :param task: The textual task or prompt that will be sent to the session.
    :param deadline: The time threshold (in seconds) for completing this operation.
    :param redis_store: Instance for managing Redis-based agent state storage.
    :param transcript: The transcript writer used for recording end-to-end operations.
    :param plan_only: Boolean flag indicating whether only the planning stage is required.
    :param require_manual_approval: Boolean indicating if manual approval is mandatory.
    :param approval_callback: Optional callback to handle manual approval for the plan.

    :return: A tuple consisting of:
        - The response dictionary corresponding to the prompt execution.
        - A string representing the unique run identifier for this workflow.
        - A string describing the parsing status or result.
    """
    session.send(
        {
            "jsonrpc": "2.0",
            "id": prompt_request_id,
            "method": "session/prompt",
            "params": {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": task}],
            },
        }
    )

    permission_request: dict | None = None
    prompt_response: dict | None = None
    while time.monotonic() < deadline:
        message = session.read_next(deadline=deadline)
        if message is None:
            continue
        if message.get("method") == "session/request_permission":
            permission_request = message
            break
        if message.get("id") == prompt_request_id and ("result" in message or "error" in message):
            prompt_response = message
            break

    run_id = f"{session_id}:{prompt_request_id}"
    if permission_request is None:
        if prompt_response is None:
            prompt_response = session.wait_for_response(prompt_request_id, deadline=deadline)
        plan_text = latest_plan_text_from_transcript(transcript)
        if _directive_parse_outcome(plan_text) == "UNPARSEABLE_PLAN":
            return prompt_response, run_id, "UNPARSEABLE_PLAN"
        raise LiveSessionError(
            "session/prompt completed without permission and without an UNPARSEABLE_PLAN marker.\n"
            f"response={prompt_response!r}\nplan_text={plan_text!r}"
        )

    plan_hash = permission_request["params"]["options"][0]["metadata"]["planHash"]
    params_meta = permission_request["params"].get("_meta", {})
    run_id = str(params_meta.get("runId", run_id))
    plan_text = latest_plan_text_from_transcript(transcript)

    plan_keys = _plan_keys_for_run(redis_store.redis_client, run_id)
    if not plan_keys:
        raise LiveSessionError(f"expected Redis plan keys for run_id={run_id!r}, found none")

    loaded = redis_store.load_plan(run_id=run_id, plan_hash=plan_hash)
    if loaded.cost_usd <= Decimal("0"):
        raise LiveSessionError(f"expected positive gateway-reported plan cost for run_id={run_id!r}")

    if plan_only:
        return {"result": {"stopReason": "plan_only"}}, run_id, "PARSED"

    approved = _resolve_approval(
        plan_text=plan_text,
        require_manual_approval=require_manual_approval,
        approval_callback=approval_callback,
    )
    if not approved:
        raise LiveSessionError("operator declined plan approval")

    session.send(
        {
            "jsonrpc": "2.0",
            "id": permission_request["id"],
            "result": {
                "outcome": {"outcome": "selected", "optionId": "approve"},
            },
        }
    )
    prompt_response = session.wait_for_response(prompt_request_id, deadline=deadline)
    return prompt_response, run_id, "PARSED"


def _resolve_approval(
    *,
    plan_text: str,
    require_manual_approval: bool,
    approval_callback: Callable[[str], bool] | None,
) -> bool:
    """
    Resolves the approval for a given plan by either using an optional callback,
    bypassing manual approval, or prompting the user for input if required. This
    function is designed to handle flexible approval workflows.

    :param plan_text: The textual representation of the plan to be approved.
    :param require_manual_approval: Indicates whether manual approval is required.
    :param approval_callback: A callable function that, if provided, determines
        approval based on the plan text. It takes a single string parameter and
        returns a boolean indicating the approval decision.
    :return: A boolean indicating whether the plan was approved (True) or not
        (False).
    """
    if approval_callback is not None:
        return approval_callback(plan_text)
    if not require_manual_approval:
        return True
    print("--- Agent plan (awaiting approval) ---")
    print(plan_text)
    print("---")
    while True:
        answer = input("Approve this plan? [y/N]: ").strip().lower()
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no", ""}:
            return False
        print("Please answer y or n.")


def _directive_parse_outcome(plan_text: str) -> str:
    try:
        parse_agent_plan(plan_text)
    except AgentDirectiveParseError:
        return "UNPARSEABLE_PLAN"
    return "PARSED"


def _plan_hash_from_transcript(transcript: E2eAcpTranscriptWriter) -> str:
    for line in reversed(transcript.lines):
        if line["direction"] != "inbound":
            continue
        message = line["message"]
        if message.get("method") != "session/request_permission":
            continue
        options = message.get("params", {}).get("options", [])
        if options and isinstance(options[0], dict):
            return str(options[0].get("metadata", {}).get("planHash", ""))
    return ""


def _approval_id_from_transcript(transcript: E2eAcpTranscriptWriter) -> str | None:
    for line in reversed(transcript.lines):
        if line["direction"] != "outbound":
            continue
        message = line["message"]
        if "result" not in message:
            continue
        approval_id = message.get("result", {}).get("metadata", {}).get("approvalId")
        if approval_id:
            return str(approval_id)
    return None


def _plan_keys_for_run(client: object, run_id: str) -> set[str]:
    async def _collect() -> set[str]:
        keys: set[str] = set()
        async for key in client.scan_iter(match=f"agent:plan:{run_id}*"):
            keys.add(key)
        return keys

    return sync_await(_collect())


def _delete_plan_keys(client: object, run_id: str) -> None:
    async def _delete() -> None:
        async for key in client.scan_iter(match=f"agent:plan:{run_id}*"):
            await client.delete(key)

    sync_await(_delete())


def _operator_action_message(check: PreflightCheckResult) -> str:
    if check.name == "gateway credentials":
        return "Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY before launching the Optimus ACP agent."
    if check.name == "redis url":
        return f"Start Redis and set OPTIMUS_REDIS_URL (for example {check.detail})."
    if check.name == "redis connectivity":
        return "Start Redis or fix OPTIMUS_REDIS_URL, then rerun verify_live_agent."
    if check.name == "redis timeseries":
        return "Use redis:8 or redis/redis-stack-server so TS.* commands are available."
    if check.name == "gateway auth":
        return "Fix OPTIMUS_API_KEY or gateway reachability, then rerun verify_live_agent."
    if check.name == "workspace writable":
        return "Choose a writable workspace directory for --workspace-root."
    return check.detail


def _failure(message: str) -> OperatorLiveSessionResult:
    return OperatorLiveSessionResult(success=False, failure_message=message)
