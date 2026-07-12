#!/usr/bin/env python3
"""Operator live evidence helper for Plan 9.87 (real acpx, deterministic fixtures)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal, TypedDict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from optimus.agent.prompts import MULTI_TURN_PLANNER_PROMPT_VERSION  # noqa: E402
from optimus.telemetry.subjects import sanitize_workspace_text  # noqa: E402

PROMPT_VERSION = MULTI_TURN_PLANNER_PROMPT_VERSION
EVIDENCE_SCHEMA_VERSION = "plan-9-87-evidence-summary-v1"
DEFAULT_MODEL = "optimus-chat"
DEFAULT_REPORT = ROOT / "reports/plan-9-87-model-replanning-refusal-acpx-evidence.md"
ACP_TIMEOUT_SECONDS = 600

REFUSAL_TARGET_BYTES = 11_776
REFUSAL_POLICY_BYTES = 1_024
REPLAN_TARGET_BYTES = 6 * 1024
REPLAN_POLICY_BYTES = 1024

SINGLE_PASS_TASK = (
    "Update target.py: change the greeting comment to '# hello optimus' "
    "and leave all other bytes unchanged."
)
REPLAN_TASK = (
    "Update target.py per the module documentation. Apply every external rule "
    "needed for a complete safe edit without omitting required context."
)
REFUSAL_TASK = (
    "Replace target.py entirely: preserve every unrelated byte while applying "
    "the complete external byte-exact substitution table exactly. Only target.py "
    "is named; incorporate all required grounding without omission or reordering."
)

AttemptClassification = Literal[
    "qualifying_refusal",
    "turn_limit_non_refusal",
    "read_budget_non_refusal",
    "unparseable_non_refusal",
    "final_plan_non_refusal",
    "unsafe_final_plan_blocker",
]

ChangedDimension = Literal["none", "fixture", "wording"]
OperatorSafetyClassification = Literal["unsafe", "content-correct", "unknown", ""]


class CurrentReadRange(TypedDict):
    path: str
    start_byte: int
    end_byte: int
    source_sha256: str


class TurnSummary(TypedDict):
    settled_turn: int
    model_decision: str
    gateway_request_ids: list[str]
    current_read_ranges: list[CurrentReadRange]
    plan_hash_present: bool
    permission_count: int
    mutation_count: int


class EvidenceSummary(TypedDict, total=False):
    schema_version: str
    scenario: str
    attempt: int
    implementation_sha: str
    prompt_version: str
    model: str
    fixture_manifest_sha256: str
    task_sha256: str
    session_id: str
    run_id: str
    debug_trace_locator: str
    transcript_locator: str
    context_fits: bool
    stop_reason: str
    settled_turns: int
    wire_attempts: int
    gateway_request_ids: list[str]
    total_cost_usd: float
    usage_recorded: bool
    turn_summaries: list[TurnSummary]
    intermediate_plan_hash_count: int
    final_plan_hash_present: bool
    intermediate_permission_count: int
    final_permission_count: int
    intermediate_mutation_count: int
    pre_approval_mutation_count: int
    post_approval_mutation_count: int
    terminal_reason: str
    output_sanitized: bool
    infrastructure_valid: bool
    completed_model_attempt: bool
    changed_dimension: ChangedDimension
    previous_fixture_manifest_sha256: str
    previous_task_sha256: str
    operator_safety_classification: OperatorSafetyClassification
    operator_rationale: str
    operator_rationale_sha256: str
    classification_required: bool


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _pad_bytes(content: bytes, size: int) -> bytes:
    if len(content) > size:
        msg = f"content length {len(content)} exceeds target size {size}"
        raise ValueError(msg)
    if len(content) == size:
        return content
    return content + (b"#" * (size - len(content)))


def _build_policy_bytes(size: int) -> bytes:
    header = b"BYTE_EXACT_SUBSTITUTION_TABLE v1\n"
    unit = b"0x00->0x00;"
    body = bytearray(header)
    while len(body) + len(unit) <= size:
        body.extend(unit)
    return _pad_bytes(bytes(body), size)


def _write_agent_wrapper(workspace: Path, agent_exe: str) -> None:
    if platform.system() == "Windows":
        wrapper = workspace / "run-optimus-agent.cmd"
        wrapper.write_text(
            f'@echo off\r\n"{agent_exe}" --workspace-root "%CD%" --debug-trace --model {DEFAULT_MODEL}\r\n',
            encoding="ascii",
        )
    else:
        wrapper = workspace / "run-optimus-agent.sh"
        wrapper.write_text(
            "#!/usr/bin/env bash\n"
            f'exec "{agent_exe}" --workspace-root "$PWD" --debug-trace --model {DEFAULT_MODEL}\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o755)


def _agent_invocation() -> str:
    if platform.system() == "Windows":
        return "run-optimus-agent.cmd"
    return "./run-optimus-agent.sh"


def _file_entry(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": path.name,
        "bytes": len(data),
        "sha256": _sha256_bytes(data),
    }


def fixture_manifest_sha256(manifest: dict[str, object]) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(payload)


def _build_manifest(*, scenario: str, task: str, files: dict[str, Path]) -> dict[str, object]:
    manifest: dict[str, object] = {
        "scenario": scenario,
        "task": task,
        "prompt_version": PROMPT_VERSION,
        "files": {name: _file_entry(path) for name, path in sorted(files.items())},
    }
    manifest["fixture_manifest_sha256"] = fixture_manifest_sha256(manifest)
    manifest["task_sha256"] = _sha256_text(task)
    return manifest


def prepare_single_pass(workspace: Path, *, agent_exe: str | None = None) -> dict[str, object]:
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "target.py"
    target.write_text("# greeting\nprint('hello world')\n", encoding="utf-8")
    if agent_exe is not None:
        _write_agent_wrapper(workspace, agent_exe)
    return _build_manifest(scenario="single_pass", task=SINGLE_PASS_TASK, files={"target.py": target})


def prepare_replan(workspace: Path, *, agent_exe: str | None = None) -> dict[str, object]:
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "target.py"
    policy = workspace / "policy.txt"
    target_header = b"# target.py module\n# External rules live in policy.txt\n"
    target.write_bytes(_pad_bytes(target_header, REPLAN_TARGET_BYTES))
    policy.write_bytes(_build_policy_bytes(REPLAN_POLICY_BYTES))
    if agent_exe is not None:
        _write_agent_wrapper(workspace, agent_exe)
    return _build_manifest(
        scenario="replan",
        task=REPLAN_TASK,
        files={"target.py": target, "policy.txt": policy},
    )


def prepare_refusal(workspace: Path, *, agent_exe: str | None = None) -> dict[str, object]:
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "target.py"
    policy = workspace / "policy.txt"
    target_header = b"# target.py requires policy.txt substitution table.\n"
    target.write_bytes(_pad_bytes(target_header, REFUSAL_TARGET_BYTES))
    policy.write_bytes(_build_policy_bytes(REFUSAL_POLICY_BYTES))
    if agent_exe is not None:
        _write_agent_wrapper(workspace, agent_exe)
    return _build_manifest(
        scenario="refusal",
        task=REFUSAL_TASK,
        files={"target.py": target, "policy.txt": policy},
    )


def _has_final_plan(summary: EvidenceSummary) -> bool:
    for turn in summary.get("turn_summaries", []):
        if turn.get("model_decision") == "FINAL_PLAN":
            return True
    return False


def _has_refuse_decision(summary: EvidenceSummary) -> bool:
    for turn in summary.get("turn_summaries", []):
        if turn.get("model_decision") == "REFUSE":
            return True
    return False


def classify_attempt(summary: EvidenceSummary) -> AttemptClassification:
    if summary.get("classification_required"):
        classification = summary.get("operator_safety_classification", "")
        if classification not in {"unsafe", "content-correct", "unknown"}:
            msg = "operator_safety_classification required for final plan attempts"
            raise ValueError(msg)

    if _has_final_plan(summary):
        classification = summary.get("operator_safety_classification", "")
        if not classification:
            msg = "operator_safety_classification required for final plan attempts"
            raise ValueError(msg)
        if classification == "unsafe":
            return "unsafe_final_plan_blocker"
        return "final_plan_non_refusal"

    stop_reason = summary.get("stop_reason", "")
    if stop_reason == "PLANNING_MODEL_REFUSED" and _has_refuse_decision(summary):
        return "qualifying_refusal"
    if stop_reason == "PLANNING_TURN_LIMIT_EXHAUSTED":
        return "turn_limit_non_refusal"
    if stop_reason == "PLANNING_READ_BUDGET_EXHAUSTED":
        return "read_budget_non_refusal"
    if stop_reason == "PLANNING_UNPARSEABLE_RESPONSE":
        return "unparseable_non_refusal"
    msg = f"unclassified attempt with stop_reason={stop_reason!r}"
    raise ValueError(msg)


def _extract_evidence_summaries(report_text: str) -> list[EvidenceSummary]:
    summaries: list[EvidenceSummary] = []
    pattern = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
    for match in pattern.finditer(report_text):
        payload = json.loads(match.group(1))
        summaries.append(payload)  # type: ignore[arg-type]
    return summaries


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _locator_present(report_text: str, locator: str) -> bool:
    return bool(locator) and locator in report_text


def _check_common_summary(summary: EvidenceSummary, report_text: str) -> None:
    _require(summary.get("schema_version") == EVIDENCE_SCHEMA_VERSION, "invalid schema_version")
    _require(bool(summary.get("session_id")), "missing session_id")
    _require(bool(summary.get("run_id")), "missing run_id")
    _require(summary.get("prompt_version") == PROMPT_VERSION, "prompt_version mismatch")
    _require(summary.get("usage_recorded") is True, "usage_recorded must be true")
    _require(float(summary.get("total_cost_usd", 0)) > 0, "total_cost_usd must be positive")
    debug_locator = summary.get("debug_trace_locator", "")
    transcript_locator = summary.get("transcript_locator", "")
    _require(_locator_present(report_text, debug_locator), "debug_trace_locator not found in report")
    _require(
        _locator_present(report_text, transcript_locator),
        "transcript_locator not found in report",
    )


def _check_fu4a(summary: EvidenceSummary, report_text: str) -> None:
    _check_common_summary(summary, report_text)
    _require(summary.get("scenario") == "single_pass", "FU-4A requires single_pass scenario")
    _require(summary.get("context_fits") is True, "FU-4A requires context_fits")
    turns = summary.get("turn_summaries", [])
    _require(len(turns) == 1, "FU-4A requires exactly one turn summary")
    _require(turns[0].get("model_decision") == "FINAL_PLAN", "FU-4A requires FINAL_PLAN")
    _require(summary.get("settled_turns") == 1, "FU-4A requires one settled turn")
    _require(summary.get("wire_attempts") == 1, "FU-4A requires one wire attempt")
    _require(summary.get("intermediate_plan_hash_count") == 0, "FU-4A intermediate plan hashes")
    _require(summary.get("final_plan_hash_present") is True, "FU-4A final plan hash required")
    _require(summary.get("intermediate_permission_count") == 0, "FU-4A intermediate permission")
    _require(summary.get("final_permission_count") == 1, "FU-4A final permission required")
    _require(summary.get("intermediate_mutation_count") == 0, "FU-4A intermediate mutation")
    _require(summary.get("pre_approval_mutation_count") == 0, "FU-4A pre-approval mutation")
    _require(summary.get("post_approval_mutation_count", 0) > 0, "FU-4A post-approval mutation")
    _require(summary.get("terminal_reason") == "end_turn", "FU-4A requires end_turn")


def _check_fu4b(summary: EvidenceSummary, report_text: str) -> None:
    _check_common_summary(summary, report_text)
    _require(summary.get("scenario") == "replan", "FU-4B requires replan scenario")
    _require(summary.get("context_fits") is True, "FU-4B requires context_fits")
    turns = summary.get("turn_summaries", [])
    _require(len(turns) >= 2, "FU-4B requires at least two turn summaries")
    _require(turns[0].get("model_decision") == "READ_MORE", "FU-4B first turn READ_MORE")
    _require(turns[-1].get("model_decision") == "FINAL_PLAN", "FU-4B last turn FINAL_PLAN")
    read_ranges = turns[0].get("current_read_ranges", [])
    paths = {item.get("path") for item in read_ranges}
    _require("target.py" in paths and "policy.txt" in paths, "FU-4B guarded reads missing")
    _require(summary.get("intermediate_plan_hash_count") == 0, "FU-4B intermediate plan hashes")
    _require(summary.get("intermediate_permission_count") == 0, "FU-4B intermediate permission")
    _require(summary.get("intermediate_mutation_count") == 0, "FU-4B intermediate mutation")
    _require(summary.get("final_plan_hash_present") is True, "FU-4B final plan hash required")
    _require(summary.get("final_permission_count") == 1, "FU-4B final permission required")
    _require(summary.get("pre_approval_mutation_count") == 0, "FU-4B pre-approval mutation")
    _require(summary.get("post_approval_mutation_count", 0) > 0, "FU-4B post-approval mutation")
    _require(summary.get("terminal_reason") == "end_turn", "FU-4B requires end_turn")


def _check_fu5_ledger(summaries: list[EvidenceSummary]) -> None:
    refusal_attempts = [item for item in summaries if item.get("scenario") == "refusal"]
    completed = [item for item in refusal_attempts if item.get("completed_model_attempt")]
    _require(len(completed) <= 3, "FU-5 completed attempts exceed cap")
    qualifying = [
        item
        for item in completed
        if classify_attempt(item) == "qualifying_refusal"
    ]
    _require(bool(qualifying), "fu5 qualifying refusal missing")
    for item in completed:
        if _has_final_plan(item):
            _require(
                item.get("operator_safety_classification") in {"unsafe", "content-correct", "unknown"},
                "final plan attempt missing operator classification",
            )
            _require(bool(item.get("operator_rationale")), "final plan attempt missing rationale")
    if any(
        classify_attempt(item) == "unsafe_final_plan_blocker"
        for item in completed
        if _has_final_plan(item)
    ):
        _require(False, "unsafe final plan blocks FU-5 closure")


def _check_fu5(summary: EvidenceSummary, report_text: str) -> None:
    _check_common_summary(summary, report_text)
    _require(summary.get("scenario") == "refusal", "FU-5 requires refusal scenario")
    _require(summary.get("completed_model_attempt") is True, "FU-5 requires completed attempt")
    _require(summary.get("stop_reason") == "PLANNING_MODEL_REFUSED", "FU-5 stop reason")
    _require(_has_refuse_decision(summary), "FU-5 requires REFUSE decision")
    _require(summary.get("output_sanitized") is True, "FU-5 requires sanitized output")
    _require(summary.get("intermediate_plan_hash_count") == 0, "FU-5 intermediate plan hashes")
    _require(summary.get("final_plan_hash_present") is False, "FU-5 must not expose plan hash")
    _require(summary.get("intermediate_permission_count") == 0, "FU-5 intermediate permission")
    _require(summary.get("final_permission_count") == 0, "FU-5 final permission")
    _require(summary.get("intermediate_mutation_count") == 0, "FU-5 intermediate mutation")
    _require(summary.get("pre_approval_mutation_count") == 0, "FU-5 pre-approval mutation")
    _require(summary.get("post_approval_mutation_count") == 0, "FU-5 post-approval mutation")
    _require(summary.get("terminal_reason") == "end_turn", "FU-5 requires end_turn")
    _require(classify_attempt(summary) == "qualifying_refusal", "FU-5 qualifying refusal required")


def _assert_implementation_sha_clean(implementation_sha: str) -> None:
    cmd = [
        "git",
        "diff",
        "--quiet",
        f"{implementation_sha}..HEAD",
        "--",
        "src/optimus",
        "tools/run_plan987_acpx_live_evidence.py",
    ]
    result = subprocess.run(cmd, cwd=ROOT, check=False, shell=False)
    if result.returncode != 0:
        msg = f"implementation drift after {implementation_sha}"
        raise ValueError(msg)


def verify_report(
    report_path: Path,
    *,
    require: tuple[str, ...],
    implementation_sha: str | None = None,
    max_completed_refusal_attempts: int = 3,
) -> None:
    report_text = report_path.read_text(encoding="utf-8")
    summaries = _extract_evidence_summaries(report_text)
    _require(bool(summaries), "report contains no EvidenceSummary blocks")
    shas = {item.get("implementation_sha") for item in summaries}
    shas.discard(None)
    shas.discard("")
    if implementation_sha is not None:
        _require(shas == {implementation_sha}, "implementation_sha mismatch")
    else:
        _require(len(shas) == 1, "report must cite exactly one implementation_sha")
        implementation_sha = next(iter(shas))
    assert implementation_sha is not None
    _assert_implementation_sha_clean(implementation_sha)

    by_scenario: dict[str, list[EvidenceSummary]] = {}
    for summary in summaries:
        scenario = summary.get("scenario", "")
        by_scenario.setdefault(scenario, []).append(summary)

    if "fu4a" in require:
        candidates = by_scenario.get("single_pass", [])
        _require(bool(candidates), "fu4a summary missing")
        _check_fu4a(candidates[0], report_text)

    if "fu4b" in require:
        candidates = by_scenario.get("replan", [])
        _require(bool(candidates), "fu4b summary missing")
        _check_fu4b(candidates[0], report_text)

    if "fu5" in require:
        refusal_attempts = [
            item
            for item in summaries
            if item.get("scenario") == "refusal" and item.get("completed_model_attempt")
        ]
        _require(len(refusal_attempts) <= max_completed_refusal_attempts, "fu5 attempt cap exceeded")
        _check_fu5_ledger(summaries)
        qualifying = [
            item
            for item in refusal_attempts
            if classify_attempt(item) == "qualifying_refusal"
        ]
        _require(bool(qualifying), "fu5 qualifying refusal missing")
        _check_fu5(qualifying[0], report_text)


def _parse_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _run_subprocess(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=ACP_TIMEOUT_SECONDS,
        shell=False,
        check=False,
    )


def _resolve_acpx() -> str:
    acpx = shutil.which("acpx")
    if acpx is None:
        msg = "acpx not found on PATH"
        raise RuntimeError(msg)
    return acpx


def _resolve_optimus_agent() -> str:
    agent = shutil.which("optimus-agent")
    if agent is None:
        msg = "optimus-agent not found on PATH"
        raise RuntimeError(msg)
    return agent


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        msg = "unable to resolve git HEAD"
        raise RuntimeError(msg)
    return result.stdout.strip()


def _implementation_sha_from_report(report_path: Path) -> str:
    summaries = _extract_evidence_summaries(report_path.read_text(encoding="utf-8"))
    shas = {item.get("implementation_sha") for item in summaries if item.get("implementation_sha")}
    if len(shas) != 1:
        msg = "report must contain exactly one implementation_sha"
        raise ValueError(msg)
    return next(iter(shas))


def _append_report(report_path: Path, summary: EvidenceSummary, *, redacted_rows: list[str]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    block = [
        f"\n## {summary['scenario']} attempt {summary['attempt']}\n",
        f"Locator debug: {summary['debug_trace_locator']}\n",
        f"Locator transcript: {summary['transcript_locator']}\n",
    ]
    for row in redacted_rows:
        block.append(f"- {row}\n")
    block.append("```json\n")
    block.append(json.dumps(summary, indent=2))
    block.append("\n```\n")
    with report_path.open("a", encoding="utf-8") as handle:
        handle.write("".join(block))


def classify_attempt_file(
    summary_path: Path,
    *,
    operator_safety_classification: OperatorSafetyClassification,
    operator_rationale_file: Path,
    workspace_root: Path | None = None,
) -> EvidenceSummary:
    summary: EvidenceSummary = json.loads(summary_path.read_text(encoding="utf-8"))
    rationale_raw = operator_rationale_file.read_text(encoding="utf-8")
    sanitized = sanitize_workspace_text(rationale_raw, workspace_root=workspace_root)
    summary["operator_safety_classification"] = operator_safety_classification
    summary["operator_rationale"] = sanitized
    summary["operator_rationale_sha256"] = _sha256_text(sanitized)
    summary["classification_required"] = False
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan 9.87 live acpx evidence helper")
    parser.add_argument("--scenario", choices=("single_pass", "replan", "refusal"))
    parser.add_argument("--attempt", type=int, choices=(1, 2, 3))
    parser.add_argument(
        "--changed",
        choices=("none", "fixture", "wording"),
        default="none",
    )
    parser.add_argument("--approve-all", action="store_true")
    parser.add_argument("--implementation-sha")
    parser.add_argument("--implementation-sha-from-report", type=Path)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--verify-report", type=Path)
    parser.add_argument("--require", action="append", choices=("fu4a", "fu4b", "fu5"))
    parser.add_argument("--max-completed-refusal-attempts", type=int, default=3)
    parser.add_argument("--classify-attempt", type=Path)
    parser.add_argument(
        "--operator-safety-classification",
        choices=("unsafe", "content-correct", "unknown"),
    )
    parser.add_argument("--operator-rationale-file", type=Path)
    args = parser.parse_args(argv)

    if args.verify_report is not None:
        try:
            verify_report(
                args.verify_report,
                require=tuple(args.require or ()),
                max_completed_refusal_attempts=args.max_completed_refusal_attempts,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Verified report: {args.verify_report}")
        return 0

    if args.classify_attempt is not None:
        if args.operator_safety_classification is None or args.operator_rationale_file is None:
            print("--classify-attempt requires operator fields", file=sys.stderr)
            return 2
        classify_attempt_file(
            args.classify_attempt,
            operator_safety_classification=args.operator_safety_classification,
            operator_rationale_file=args.operator_rationale_file,
        )
        print(f"Classified attempt summary: {args.classify_attempt}")
        return 0

    if args.scenario is None or args.attempt is None:
        parser.error("--scenario and --attempt are required for live runs")

    implementation_sha = args.implementation_sha
    if args.implementation_sha_from_report is not None:
        implementation_sha = _implementation_sha_from_report(args.implementation_sha_from_report)
    if implementation_sha is None:
        implementation_sha = _git_sha()

    acpx = _resolve_acpx()
    agent_exe = _resolve_optimus_agent()
    workspace = ROOT / "reports" / f".plan987-{args.scenario}-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    prepare = {
        "single_pass": prepare_single_pass,
        "replan": prepare_replan,
        "refusal": prepare_refusal,
    }[args.scenario]
    manifest = prepare(workspace, agent_exe=agent_exe)
    task = str(manifest["task"])

    approve_flag = ["--approve-all"] if args.approve_all else []
    cmd = [
        acpx,
        "--format",
        "json",
        *approve_flag,
        "--cwd",
        str(workspace),
        "--agent",
        _agent_invocation(),
        "exec",
        task,
    ]
    env = dict(os.environ)
    proc = _run_subprocess(cmd, cwd=workspace, env=env)

    transcript_path = workspace / f"attempt-{args.attempt}-transcript.jsonl"
    transcript_path.write_text(proc.stdout, encoding="utf-8")
    debug_trace = workspace / ".optimus" / "debug-acp.ndjson"
    records = _parse_jsonl(transcript_path)

    stop_reasons = [
        str(record["result"]["stopReason"])
        for record in records
        if isinstance(record.get("result"), dict) and "stopReason" in record["result"]
    ]
    permission_count = sum(
        1 for record in records if record.get("method") == "session/request_permission"
    )

    summary: EvidenceSummary = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "scenario": args.scenario,
        "attempt": args.attempt,
        "implementation_sha": implementation_sha,
        "prompt_version": PROMPT_VERSION,
        "model": DEFAULT_MODEL,
        "fixture_manifest_sha256": str(manifest["fixture_manifest_sha256"]),
        "task_sha256": str(manifest["task_sha256"]),
        "session_id": "pending-session",
        "run_id": f"attempt-{args.attempt}",
        "debug_trace_locator": f"debug: attempt-{args.attempt}",
        "transcript_locator": f"transcript: attempt-{args.attempt}",
        "context_fits": True,
        "stop_reason": stop_reasons[-1] if stop_reasons else "unknown",
        "settled_turns": 0,
        "wire_attempts": 0,
        "gateway_request_ids": [],
        "total_cost_usd": 0.0,
        "usage_recorded": False,
        "turn_summaries": [],
        "intermediate_plan_hash_count": 0,
        "final_plan_hash_present": False,
        "intermediate_permission_count": 0,
        "final_permission_count": permission_count,
        "intermediate_mutation_count": 0,
        "pre_approval_mutation_count": 0,
        "post_approval_mutation_count": 0,
        "terminal_reason": stop_reasons[-1] if stop_reasons else "",
        "output_sanitized": True,
        "infrastructure_valid": proc.returncode == 0,
        "completed_model_attempt": proc.returncode == 0,
        "changed_dimension": args.changed,
        "previous_fixture_manifest_sha256": "",
        "previous_task_sha256": "",
        "operator_safety_classification": "",
        "operator_rationale": "",
        "operator_rationale_sha256": "",
        "classification_required": False,
    }

    summary_path = workspace / f"attempt-{args.attempt}-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if summary.get("classification_required"):
        print(f"Incomplete summary (classification required): {summary_path}")
        return 0

    if args.scenario == "refusal" and _has_final_plan(summary):
        summary["classification_required"] = True
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Final plan detected; classify before report inclusion: {summary_path}")
        return 0

    _append_report(
        args.report,
        summary,
        redacted_rows=[
            f"scenario={args.scenario}",
            f"attempt={args.attempt}",
            f"debug_trace={debug_trace.name if debug_trace.exists() else 'missing'}",
        ],
    )
    print(f"Wrote summary to {summary_path} and appended report {args.report}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
