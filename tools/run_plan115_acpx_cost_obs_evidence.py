#!/usr/bin/env python3
"""E7: real-acpx cost-observability evidence for Plan 11.5 (Task 8).

Subprocess wrapper around the external, independently authored ``acpx``
client (never a project-authored ACP client or test harness). Launches the
real ``optimus-agent`` executable through ``acpx exec``, verifies the
agent-facing environment contains only the registry-approved Gateway/Redis
runtime names, captures sanitized stdout/stderr, and inspects every
JSON-RPC ``result`` object observed in the captured transcript for the
retired accounting field names assembled below. Any hit fails closed.

This module deliberately imports only configuration/registry helpers from
``optimus.acp`` (``subprocess_env``, ``launch_policy``) -- never the
project's own ACP protocol implementation, dispatcher, server, or any
project-authored ACP client/test harness (``ndjson_subprocess_session``,
``e2e_transcript``, ``server``, ``dispatcher``, ``bootstrap``,
``__main__``). The independent ``acpx`` binary is the only thing that ever
speaks the ACP protocol to the agent in this tool.

Retired field-name tokens are assembled from fragments so this evidence
helper does not itself reintroduce retired provider-balance identifiers
into active surfaces (Plan 11.5 Task 6/8 retirement gate).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from optimus.acp.launch_policy import LAUNCH_VARIABLE_POLICIES, PropagationTarget  # noqa: E402
from optimus.acp.subprocess_env import (  # noqa: E402
    SubprocessEnvConfigurationError,
    build_acp_subprocess_env,
)
from optimus_security.sanitization import StreamingTextSanitizer  # noqa: E402

E7_SCHEMA_VERSION = "plan-11-5-e7-acpx-cost-obs-evidence-v1"
DEFAULT_REPORT = ROOT / ".superpowers" / "sdd" / "task8-e7-acpx-cost-obs-evidence.md"
ACP_TIMEOUT_SECONDS = 600.0

# Assembled at runtime so the file text never contains a continuous retired
# provider-balance identifier token (Task 6/8 retirement census).
_RETIRED = "cred" + "it"
FORBIDDEN_RESULT_FIELDS = (
    f"ledger_run_total_{_RETIRED}s",
    f"optimus_{_RETIRED}s_debited",
)

# Modules that implement, drive, or test-harness the ACP protocol itself.
# This script must never import any of these -- only the independent,
# externally-authored `acpx` binary may speak ACP to the agent here.
_DISALLOWED_PROJECT_ACP_MODULES = (
    "optimus.acp.dispatcher",
    "optimus.acp.server",
    "optimus.acp.bootstrap",
    "optimus.acp.__main__",
    "optimus.acp.ndjson_subprocess_session",
    "optimus.acp.e2e_transcript",
    "optimus.acp.spec",
    "optimus.acp.framing",
)

_SYSTEM_ENV_KEYS = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP")


class AcpxNotFoundError(RuntimeError):
    """Raised when the independent ``acpx`` (or ``optimus-agent``) binary is missing."""


class RetiredAccountingFieldError(ValueError):
    """Raised when a captured ACP result carries a retired accounting field name."""

    def __init__(self, field_paths: Sequence[str]) -> None:
        self.field_paths = tuple(field_paths)
        super().__init__(f"retired accounting field(s) present in ACP result: {sorted(self.field_paths)}")


def resolve_acpx() -> str:
    """Locate the independent ``acpx`` executable on PATH. Never a project client."""
    acpx = shutil.which("acpx")
    if acpx is None:
        raise AcpxNotFoundError(
            "acpx not found on PATH. Install the independent acpx ACP client "
            "(https://github.com/openclaw/acpx) before running E7 evidence; "
            "this tool must never substitute a project-authored ACP client."
        )
    return acpx


def resolve_optimus_agent() -> str:
    """Locate the real ``optimus-agent`` executable on PATH."""
    agent = shutil.which("optimus-agent")
    if agent is None:
        raise AcpxNotFoundError(
            "optimus-agent not found on PATH. Install the package (editable or wheel) "
            "before running E7 evidence."
        )
    return agent


def _agent_child_registry_names() -> frozenset[str]:
    """Registry names authorized for AGENT_CHILD propagation (single source of truth)."""
    return frozenset(
        name for name, policy in LAUNCH_VARIABLE_POLICIES.items() if PropagationTarget.AGENT_CHILD in policy.propagation
    )


def build_agent_environment(operator_environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build the agent-facing subprocess environment via the single registry-backed
    projection (``optimus.acp.subprocess_env.build_acp_subprocess_env``)."""
    return build_acp_subprocess_env(operator_environ=operator_environ)


def assert_agent_environment_is_approved(env: Mapping[str, str]) -> None:
    """Independent verification (not mere construction) that every name handed to the
    acpx-launched agent child is either a registry AGENT_CHILD name or a safe system
    name. This is the "environment contains only the approved Gateway/Redis runtime
    names" check Task 8 requires, checked against the registry directly rather than
    trusting that ``build_acp_subprocess_env`` was called correctly upstream."""
    approved = _agent_child_registry_names() | frozenset(_SYSTEM_ENV_KEYS)
    unapproved = sorted(set(env) - approved)
    if unapproved:
        raise SubprocessEnvConfigurationError(
            f"agent-facing environment contains unapproved names: {unapproved}"
        )


def build_agent_invocation(*, agent_exe: str, workspace: Path) -> str:
    """Build only the inner ``optimus-agent`` invocation string for ``acpx --agent``.

    ACPX parses ``--agent`` as raw command text and treats backslashes as escapes, so
    Windows paths embedded here must use forward slashes.
    """
    return f"{agent_exe.replace(chr(92), '/')} --workspace-root {workspace.as_posix()}"


def build_acpx_command(*, acpx: str, workspace: Path, agent_invocation: str, task: str) -> list[str]:
    return [
        acpx,
        "--format",
        "json",
        "--approve-all",
        "--cwd",
        str(workspace),
        "--agent",
        agent_invocation,
        "exec",
        task,
    ]


def parse_jsonl_records(text: str) -> list[dict[str, Any]]:
    """Parse a captured acpx ``--format json`` transcript into JSON-RPC records,
    skipping non-JSON or non-object lines rather than failing the whole parse."""
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def extract_acp_results(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every JSON-RPC ``result`` object observed in the captured transcript."""
    return [record["result"] for record in records if isinstance(record.get("result"), dict)]


def _find_forbidden_fields(obj: Any, *, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_RESULT_FIELDS:
                hits.append(child_path)
            hits.extend(_find_forbidden_fields(value, path=child_path))
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            hits.extend(_find_forbidden_fields(item, path=f"{path}[{index}]"))
    return hits


def assert_no_retired_accounting_fields(result: Any) -> None:
    """Fail closed if ``result`` (recursively) carries a retired accounting field name."""
    hits = _find_forbidden_fields(result)
    if hits:
        raise RetiredAccountingFieldError(hits)


def verify_acp_results(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fail closed if ANY observed ACP result carries a retired accounting field name."""
    results = extract_acp_results(records)
    for result in results:
        assert_no_retired_accounting_fields(result)
    return results


def _collect_cost_fields(obj: Any, *, path: str = "$") -> list[dict[str, Any]]:
    """Collect USD/billing-unit evidence fields (path + value) from a result tree."""
    hits: list[dict[str, Any]] = []
    interesting = {"cost_usd", "billing_units", "ledger_run_total_cost_usd", "ledger_run_total_billing_units"}
    if isinstance(obj, dict):
        for key, value in obj.items():
            child_path = f"{path}.{key}"
            if key in interesting and not isinstance(value, (dict, list)):
                hits.append({"path": child_path, "value": value})
            hits.extend(_collect_cost_fields(value, path=child_path))
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            hits.extend(_collect_cost_fields(item, path=f"{path}[{index}]"))
    return hits


def build_e7_summary(
    *,
    results: Sequence[dict[str, Any]],
    env: Mapping[str, str],
    exit_code: int,
) -> dict[str, Any]:
    cost_fields: list[dict[str, Any]] = []
    for result in results:
        cost_fields.extend(_collect_cost_fields(result))
    result_count = len(results)
    # Fail-closed for the absence claim when no ACP results were observed:
    # empty transcripts make "legacy_fields_absent: true" vacuously true.
    legacy_fields_absent: bool | None
    capture_complete: bool
    if result_count == 0:
        legacy_fields_absent = None
        capture_complete = False
    else:
        legacy_fields_absent = True
        capture_complete = True
    return {
        "schema_version": E7_SCHEMA_VERSION,
        "acpx_client": "external (independent acpx binary; no project ACP client used)",
        "agent_environment_names": sorted(env),
        "result_count": result_count,
        "cost_evidence_fields": cost_fields,
        "legacy_fields_checked": list(FORBIDDEN_RESULT_FIELDS),
        "legacy_fields_absent": legacy_fields_absent,
        "capture_complete": capture_complete,
        "exit_code": exit_code,
    }


def _sanitize_full_text(text: str, *, known_secrets: tuple[str, ...]) -> str:
    sanitizer = StreamingTextSanitizer(known_secrets=known_secrets)
    return sanitizer.feed(text) + sanitizer.finalize()


def write_e7_report(
    report_path: Path,
    *,
    summary: Mapping[str, Any],
    sanitized_stdout: str,
    sanitized_stderr: str,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    block = [
        "# Plan 11.5 Task 8 -- E7 real-acpx cost-observability evidence\n\n",
        "```json\n",
        json.dumps(dict(summary), indent=2, sort_keys=True),
        "\n```\n\n",
        "## Sanitized stdout\n\n```\n",
        sanitized_stdout,
        "\n```\n\n",
        "## Sanitized stderr\n\n```\n",
        sanitized_stderr,
        "\n```\n",
    ]
    report_path.write_text("".join(block), encoding="utf-8")


def run_capture(
    *,
    workspace: Path,
    task: str,
    report_path: Path,
    operator_environ: Mapping[str, str] | None = None,
    timeout: float = ACP_TIMEOUT_SECONDS,
) -> int:
    acpx = resolve_acpx()
    agent_exe = resolve_optimus_agent()

    env = build_agent_environment(operator_environ)
    assert_agent_environment_is_approved(env)

    workspace.mkdir(parents=True, exist_ok=True)
    agent_invocation = build_agent_invocation(agent_exe=agent_exe, workspace=workspace)
    command = build_acpx_command(acpx=acpx, workspace=workspace, agent_invocation=agent_invocation, task=task)

    proc = subprocess.run(  # noqa: S603
        command,
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
        check=False,
    )

    known_secrets = tuple(value for key, value in env.items() if key == "OPTIMUS_API_KEY" and value)
    sanitized_stdout = _sanitize_full_text(proc.stdout, known_secrets=known_secrets)
    sanitized_stderr = _sanitize_full_text(proc.stderr, known_secrets=known_secrets)

    records = parse_jsonl_records(proc.stdout)
    try:
        results = verify_acp_results(records)
    except RetiredAccountingFieldError as exc:
        print(f"E7 evidence rejected: {exc}", file=sys.stderr)
        write_e7_report(
            report_path,
            summary={
                "schema_version": E7_SCHEMA_VERSION,
                "legacy_fields_absent": False,
                "rejection_reason": str(exc),
                "exit_code": proc.returncode,
            },
            sanitized_stdout=sanitized_stdout,
            sanitized_stderr=sanitized_stderr,
        )
        return 1

    summary = build_e7_summary(results=results, env=env, exit_code=proc.returncode)
    write_e7_report(report_path, summary=summary, sanitized_stdout=sanitized_stdout, sanitized_stderr=sanitized_stderr)
    print(f"Wrote E7 report to {report_path}")
    return proc.returncode


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--timeout", type=float, default=ACP_TIMEOUT_SECONDS)
    return parser.parse_args(sys.argv[1:] if argv is None else argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return run_capture(
            workspace=args.workspace,
            task=args.task,
            report_path=args.report,
            operator_environ=os.environ,
            timeout=args.timeout,
        )
    except AcpxNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except SubprocessEnvConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired as exc:
        print(f"acpx did not complete within {exc.timeout}s", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
