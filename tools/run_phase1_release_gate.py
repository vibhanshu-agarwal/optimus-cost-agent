from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from optimus.acp.bootstrap import StartupConfigurationError, build_agent_runner_for_harness
from optimus.acp.preflight import PreflightFailure, run_preflight
from optimus.agent.golden import AgentGoldenTaskHarness
from optimus.golden.json_harness import JsonGoldenTaskHarness
from optimus.release.agent_smoke_transcript import PLAN_9_5_SMOKE_TRANSCRIPT_PATH, RecordingAgentRunner, SmokeTranscriptRecorder
from optimus.release.defaults import PLAN_9_5_REAL_AGENT_TASK_IDS, build_phase1_release_gates
from optimus.release.runner import ReleaseGateRunner

_AGENT_HARNESS_REDIS_ENV = "OPTIMUS_REDIS_URL"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 1 Optimus release gate.")
    harness_group = parser.add_mutually_exclusive_group()
    harness_group.add_argument(
        "--golden-results",
        type=Path,
        help="Path to actual GoldenTaskResult JSON captured from a real Optimus-only run.",
    )
    harness_group.add_argument(
        "--agent-harness",
        action="store_true",
        help="Run the Plan 9.5 golden subset through AgentGoldenTaskHarness.",
    )
    parser.add_argument(
        "--task-id",
        action="append",
        default=None,
        help="Golden task id to include; may be supplied more than once.",
    )
    parser.add_argument(
        "--agent-model",
        default="glm-5.2",
        help="Gateway model used by the real agent harness.",
    )
    parser.add_argument("--python-executable", default=sys.executable, help="Python executable used for command gates.")
    parser.add_argument("--credential-scan-root", type=Path, default=Path("."), help="Root used for default release credential artifact scans.")
    parser.add_argument("--command-timeout-seconds", type=float, default=600.0, help="Timeout for each subprocess-backed release gate.")
    parser.add_argument("--skip-command-gates-for-test", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


class _TranscriptGoldenHarness:
    def __init__(self, *, harness: AgentGoldenTaskHarness, recording_runner: RecordingAgentRunner) -> None:
        self._harness = harness
        self._recording_runner = recording_runner

    def run(self, task):
        self._recording_runner.set_task_id(task.task_id)
        return self._harness.run(task)


def main() -> int:
    args = parse_args()
    golden_harness = None
    golden_task_ids = None
    transcript_recorder: SmokeTranscriptRecorder | None = None
    if args.golden_results is not None:
        golden_harness = JsonGoldenTaskHarness.from_path(args.golden_results)
    elif args.agent_harness:
        workspace_root = Path(".").resolve()
        try:
            run_preflight(os.environ, workspace_root=workspace_root, require_timeseries=True)
            base_runner = build_agent_runner_for_harness(
                environ=os.environ,
                workspace_root=workspace_root,
                model=args.agent_model,
            )
        except PreflightFailure as exc:
            print(exc.user_message, file=sys.stderr)
            return exc.exit_code
        except StartupConfigurationError as exc:
            print(exc.user_message, file=sys.stderr)
            return exc.exit_code
        transcript_recorder = SmokeTranscriptRecorder(model=args.agent_model)
        recording_runner = RecordingAgentRunner(base_runner, recorder=transcript_recorder)
        harness = AgentGoldenTaskHarness(runner=recording_runner, workspace_root=workspace_root)
        golden_harness = _TranscriptGoldenHarness(harness=harness, recording_runner=recording_runner)
        golden_task_ids = tuple(args.task_id or PLAN_9_5_REAL_AGENT_TASK_IDS)
    gates = build_phase1_release_gates(
        python_executable=args.python_executable,
        golden_harness=golden_harness,
        golden_task_ids=golden_task_ids,
        include_command_gates=not args.skip_command_gates_for_test,
        credential_scan_root=args.credential_scan_root,
        command_timeout_seconds=args.command_timeout_seconds,
    )
    report = ReleaseGateRunner(gates=gates).run()
    if transcript_recorder is not None:
        # reports/plan-9-5-working-agent-smoke-transcript.json
        transcript_recorder.write(PLAN_9_5_SMOKE_TRANSCRIPT_PATH)
    print(report.to_json())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
