#!/usr/bin/env python3
"""Re-probe ACP ``session/load`` with independent acpx, without launching Zed.

The one required argument is a parent directory for a throwaway workspace. The
probe creates and removes only a unique child of that directory. It asks the
operator to approve that exact temporary workspace through ``optimus-trust``,
then revokes and verifies removal of that approval before deleting the child.
It queries ``Zed --version`` for point-in-time context but never starts Zed,
changes Zed settings, or touches an existing Zed profile.

acpx is the ACP client for all protocol traffic.  The probe makes a session in
one isolated acpx home, exports it, imports it into a second isolated home, and
uses a non-prompt configuration operation to force acpx's saved-session
reconnect.  acpx invokes ``session/resume`` when advertised and ``session/load``
only when its live capability payload advertises it; otherwise the probe records
the capability-gated unreachable result.  No prompt, Gateway request, origin-A
fixture, or correlation launch is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from optimus_security.sanitization import EVIDENCE_REDACTION_POLICY, sanitize_for_persistence


class Finding(StrEnum):
    """The only verdicts this reachability probe can emit."""

    REACHABLE = "REACHABLE"
    UNREACHABLE = "UNREACHABLE"
    INDETERMINATE = "INDETERMINATE"


class IndeterminateReason(StrEnum):
    """Why a non-verdict must not be misread as an observation about Zed."""

    PRECONDITION_UNMET = "PRECONDITION_UNMET"
    OBSERVATION_INCOMPLETE = "OBSERVATION_INCOMPLETE"


@dataclass(frozen=True)
class SessionLoadEvaluation:
    """Classified live exchange while retaining its exact safe protocol payloads."""

    finding: Finding
    capability_payload: dict[str, Any] | None
    load_exchange: dict[str, Any] | None


@dataclass(frozen=True)
class CommandResult:
    """Captured command details from an independent acpx invocation."""

    command: list[str]
    returncode: int
    stdout: str
    stderr: str


class ProbeError(RuntimeError):
    """A bounded precondition or execution failure that leaves the verdict indeterminate."""

    def __init__(self, stage: str, message: str, command_result: CommandResult | None = None) -> None:
        self.stage = stage
        self.command_result = command_result
        super().__init__(message)


def evaluate_session_load_exchange(
    capability_payload: Mapping[str, Any] | None,
    load_exchange: Mapping[str, Any] | None,
) -> SessionLoadEvaluation:
    """Classify only a complete, internally consistent live capability/load exchange."""
    capabilities = dict(capability_payload) if isinstance(capability_payload, Mapping) else None
    exchange = dict(load_exchange) if isinstance(load_exchange, Mapping) else None
    if capabilities is None:
        return SessionLoadEvaluation(Finding.INDETERMINATE, capabilities, exchange)

    advertised = capabilities.get("loadSession") is True
    if not advertised:
        return SessionLoadEvaluation(Finding.UNREACHABLE, capabilities, exchange)
    if exchange is None:
        return SessionLoadEvaluation(Finding.INDETERMINATE, capabilities, exchange)

    response = exchange.get("response")
    if not isinstance(response, Mapping):
        return SessionLoadEvaluation(Finding.INDETERMINATE, capabilities, exchange)

    has_result = "result" in response
    has_error = isinstance(response.get("error"), Mapping)
    if advertised and has_result:
        return SessionLoadEvaluation(Finding.REACHABLE, capabilities, exchange)
    if has_error:
        return SessionLoadEvaluation(Finding.UNREACHABLE, capabilities, exchange)
    return SessionLoadEvaluation(Finding.INDETERMINATE, capabilities, exchange)


def _run(command: Sequence[str], *, cwd: Path, env: Mapping[str, str]) -> CommandResult:
    completed = subprocess.run(  # noqa: S603
        list(command),
        cwd=cwd,
        env=dict(env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        shell=False,
        timeout=90,
    )
    return CommandResult(
        command=list(command),
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def _run_required(command: Sequence[str], *, cwd: Path, env: Mapping[str, str], stage: str) -> CommandResult:
    try:
        result = _run(command, cwd=cwd, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError(stage, f"{type(exc).__name__}: {exc}") from exc
    if result.returncode != 0:
        raise ProbeError(stage, f"exit={result.returncode}: captured command evidence", result)
    return result


def _resolve_acpx() -> Path:
    on_path = shutil.which("acpx")
    if on_path:
        return Path(on_path).resolve()
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        npm_shim = Path(appdata) / "npm" / "acpx.cmd"
        if npm_shim.is_file():
            return npm_shim.resolve()
    raise ProbeError("resolve_acpx", "independent acpx binary is not available on PATH or in APPDATA\\npm")


def _resolve_optimus_agent(repo_root: Path) -> Path:
    on_path = shutil.which("optimus-agent")
    if on_path:
        return Path(on_path).resolve()
    candidate = repo_root / ".venv" / "Scripts" / "optimus-agent.exe"
    if candidate.is_file():
        return candidate.resolve()
    raise ProbeError("resolve_optimus_agent", "optimus-agent is not available on PATH or in the repository virtualenv")


def _observe_zed_version() -> str:
    zed = shutil.which("zed")
    if zed is None:
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        candidate = Path(local_app_data) / "Programs" / "Zed" / "bin" / "Zed.exe"
        if candidate.is_file():
            zed = str(candidate)
    if zed is None:
        raise ProbeError("observe_zed_version", "Zed executable not found")
    try:
        completed = subprocess.run(  # noqa: S603
            [zed, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError("observe_zed_version", f"{type(exc).__name__}: {exc}") from exc
    version = (completed.stdout or completed.stderr).strip()
    if completed.returncode != 0 or not version:
        raise ProbeError("observe_zed_version", f"Zed --version exit={completed.returncode}")
    return version


def _acpx_version(acpx: Path, *, cwd: Path, env: Mapping[str, str]) -> str:
    result = _run_required([str(acpx), "--version"], cwd=cwd, env=env, stage="acpx_version")
    version = (result.stdout or result.stderr).strip()
    if not version:
        raise ProbeError("acpx_version", "acpx --version returned empty output")
    return version


def _file_sha256(path: Path) -> str:
    """Return the provenance digest for the exact acpx launcher invoked."""
    try:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as exc:
        raise ProbeError("acpx_provenance", f"{type(exc).__name__}: {exc}") from exc


def _isolated_environment(home: Path) -> dict[str, str]:
    passthrough = {
        "COMSPEC",
        "PATH",
        "PATHEXT",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "WINDIR",
    }
    environment = {key: value for key, value in os.environ.items() if key in passthrough}
    app_data = home / "AppData" / "Roaming"
    local_app_data = home / "AppData" / "Local"
    temp_root = home / "Temp"
    for directory in (app_data, local_app_data, temp_root):
        directory.mkdir(parents=True, exist_ok=True)
    environment.update(
        {
            "APPDATA": str(app_data),
            "HOME": str(home),
            "LOCALAPPDATA": str(local_app_data),
            "TEMP": str(temp_root),
            "TMP": str(temp_root),
            "USERPROFILE": str(home),
        }
    )
    return environment


def build_acpx_command(acpx: Path, *, workspace: Path, agent: Path) -> list[str]:
    """Build a raw acpx agent command with slash-normalized Windows paths."""
    return [
        str(acpx),
        "--format",
        "json",
        "--json-strict",
        "--no-terminal",
        "--auth-policy",
        "skip",
        "--deny-all",
        "--allowed-tools",
        "",
        "--timeout",
        "60",
        "--ttl",
        "1",
        "--cwd",
        str(workspace),
        "--agent",
        subprocess.list2cmdline(
            [agent.as_posix(), "--workspace-root", workspace.as_posix(), "--no-auto-start"]
        ),
    ]


def _resolve_trust_cli(repo_root: Path) -> Path:
    candidate = repo_root / ".venv" / "Scripts" / "optimus-trust.exe"
    if candidate.is_file():
        return candidate.resolve()
    on_path = shutil.which("optimus-trust")
    if on_path:
        return Path(on_path).resolve()
    raise ProbeError("resolve_optimus_trust", "optimus-trust is not available in the repository virtualenv or on PATH")


def build_trust_command(trust_cli: Path, workspace: Path, action: str) -> list[str]:
    """Build the exact trust-CLI command for temporary approval or cleanup."""
    prefix = [str(trust_cli), "--workspace-root", str(workspace)]
    if action == "approve":
        return [*prefix, "approve", "--mode", "durable"]
    if action == "revoke":
        return [*prefix, "revoke"]
    if action == "inspect":
        return [*prefix, "inspect"]
    raise ValueError(f"unsupported trust action: {action}")


def build_cleanup_remediation(trust_cli: Path, workspace: Path) -> list[str]:
    """Return the exact workspace-scoped command needed after a failed cleanup."""
    return [str(trust_cli), "--workspace-root", str(workspace), "revoke"]


def _run_interactive_required(command: Sequence[str], *, cwd: Path, stage: str) -> CommandResult:
    """Run a trust ceremony only from an interactive terminal; never synthesize consent."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ProbeError(stage, "interactive TTY required for Optimus launch-approval ceremony")
    try:
        completed = subprocess.run(list(command), cwd=cwd, check=False, shell=False)  # noqa: S603
    except OSError as exc:
        raise ProbeError(stage, f"{type(exc).__name__}: {exc}") from exc
    if completed.returncode != 0:
        raise ProbeError(stage, f"exit={completed.returncode}")
    return CommandResult(command=list(command), returncode=completed.returncode, stdout="", stderr="")


def _parse_ndjson(raw: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in raw.splitlines():
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            records.append(decoded)
    return records


def _extract_session_load_evidence(records: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    capabilities: dict[str, Any] | None = None
    requests: dict[Any, dict[str, Any]] = {}
    exchanges: list[dict[str, Any]] = []
    for record in records:
        result = record.get("result")
        if isinstance(result, Mapping):
            candidate = result.get("agentCapabilities")
            if capabilities is None and isinstance(candidate, Mapping):
                capabilities = dict(candidate)
        if record.get("method") == "session/load":
            requests[record.get("id")] = dict(record)
            continue
        request = requests.get(record.get("id"))
        if request is not None and ("result" in record or "error" in record):
            exchanges.append({"request": request, "response": dict(record)})
    return capabilities, exchanges[0] if exchanges else None


def _safe_payload(value: Any) -> Any:
    """Apply the repository's evidence sanitizer to every persisted stream or payload."""
    return sanitize_for_persistence(value, policy=EVIDENCE_REDACTION_POLICY).value


def capture_acpx_evidence(command_result: CommandResult) -> dict[str, Any]:
    """Retain safe structured ACP evidence from a successful *or failed* acpx stage."""
    records = _parse_ndjson(command_result.stdout)
    capability_payload, load_exchange = _extract_session_load_evidence(records)
    non_protocol_lines = sum(1 for line in command_result.stdout.splitlines() if line.strip()) - len(records)
    return {
        "command": _safe_payload(command_result.command),
        "exit_code": command_result.returncode,
        "stdout_records": _safe_payload(records),
        "stdout_unparsed_line_count": non_protocol_lines,
        "stderr": _safe_payload(command_result.stderr.strip()) or None,
        "capability_payload": _safe_payload(capability_payload),
        "session_load_exchange": _safe_payload(load_exchange),
    }


def extract_acpx_archive_capability_payload(archive: Path) -> dict[str, Any] | None:
    """Read the live initialize capabilities persisted by acpx's own session export."""
    try:
        archive_payload = json.loads(archive.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeError("acpx_export_archive", f"{type(exc).__name__}: {exc}") from exc
    if not isinstance(archive_payload, Mapping):
        return None
    session = archive_payload.get("session")
    if not isinstance(session, Mapping):
        return None
    state = session.get("state")
    if not isinstance(state, Mapping):
        return None
    capabilities = state.get("agent_capabilities")
    return dict(capabilities) if isinstance(capabilities, Mapping) else None


def classify_indeterminate_context(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Separate a missing documented dependency from an incomplete ACP observation."""
    evidence_text = json.dumps(evidence, sort_keys=True).casefold()
    redis_unreachable = "redis" in evidence_text and (
        "not reachable" in evidence_text or "timeout connecting" in evidence_text
    )
    if redis_unreachable:
        return {
            "indeterminate_reason": IndeterminateReason.PRECONDITION_UNMET.value,
            "precondition": {
                "name": "redis",
                "remediation": {
                    "runbook": "docs/runbooks/local-live-dependencies.md#5-bounded-session-bound-smoke-redis--gateway-optional-phoenix",
                    "command": "optimus-agent --workspace-root <throwaway-workspace> --check-config --strict",
                },
            },
        }
    return {
        "indeterminate_reason": IndeterminateReason.OBSERVATION_INCOMPLETE.value,
        "precondition": None,
    }


def _revoke_temporary_approval(trust_cli: Path, workspace: Path, *, cwd: Path) -> None:
    """Revoke and verify the temporary durable record, retrying bounded transient failures."""
    last_error: ProbeError | None = None
    for _attempt in range(1, 4):
        try:
            _run_interactive_required(
                build_trust_command(trust_cli, workspace, "revoke"),
                cwd=cwd,
                stage="temporary_approval_revoke",
            )
            try:
                inspected = _run(build_trust_command(trust_cli, workspace, "inspect"), cwd=cwd, env=os.environ)
            except (OSError, subprocess.TimeoutExpired) as exc:
                last_error = ProbeError("temporary_approval_verify", f"{type(exc).__name__}: {exc}")
                continue
            if inspected.returncode == 1:
                return
            last_error = ProbeError("temporary_approval_verify", f"inspect exit={inspected.returncode}")
        except ProbeError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _git_head(repo_root: Path) -> str | None:
    try:
        completed = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def _validate_parent_workspace(parent_workspace: Path, repo_root: Path) -> Path:
    resolved = parent_workspace.resolve()
    if not resolved.is_dir():
        raise ProbeError("workspace", "workspace path must be an existing directory")
    if resolved == repo_root or (resolved / ".git").exists():
        raise ProbeError("workspace", "workspace path must be a throwaway directory, never a repository")
    return resolved


def run_probe(parent_workspace: Path) -> dict[str, Any]:
    """Run the non-prompt acpx recovery sequence and return a self-contained finding."""
    repo_root = Path(__file__).resolve().parents[1]
    recorded_at = datetime.now(UTC).isoformat()
    result: dict[str, Any] = {
        "schema": "p11-feat-zed-resume-session-load-reprobe-v1",
        "recorded_at_utc": recorded_at,
        "commit": _git_head(repo_root),
        "finding": Finding.INDETERMINATE.value,
        "indeterminate_reason": IndeterminateReason.OBSERVATION_INCOMPLETE.value,
        "precondition": None,
        "zed_version": None,
        "acpx_version": None,
        "acpx_executable": None,
        "acpx_launcher_sha256": None,
        "capability_payload": None,
        "session_load_exchange": None,
        "command": "uv run --frozen python tools/probe_p11_zed_session_load.py <throwaway-workspace>",
        "origin_a_launches": 0,
        "zed_launches": 0,
        "temporary_launch_approval_revoked": None,
        "cleanup_remediation": None,
        "non_claims": [
            "Does not prove that Zed itself emits session/load after a restart.",
            "Does not establish origin-A correlation, server-side custody feasibility, or authorization for an amendment.",
        ],
    }
    run_root: Path | None = None
    trust_cli: Path | None = None
    temporary_approval_created = False
    cleanup_succeeded = True
    try:
        workspace_parent = _validate_parent_workspace(parent_workspace, repo_root)
        result["zed_version"] = _observe_zed_version()
        run_root = Path(tempfile.mkdtemp(prefix="p11-zed-session-load-", dir=workspace_parent))
        workspace = run_root / "workspace"
        first_home = run_root / "acpx-home-first"
        second_home = run_root / "acpx-home-second"
        workspace.mkdir()
        acpx = _resolve_acpx()
        result["acpx_executable"] = str(acpx)
        result["acpx_launcher_sha256"] = _file_sha256(acpx)
        agent = _resolve_optimus_agent(repo_root)
        trust_cli = _resolve_trust_cli(repo_root)
        first_environment = _isolated_environment(first_home)
        second_environment = _isolated_environment(second_home)
        result["acpx_version"] = _acpx_version(acpx, cwd=workspace, env=first_environment)
        command = build_acpx_command(acpx, workspace=workspace, agent=agent)
        try:
            trust_preflight = _run(build_trust_command(trust_cli, workspace, "inspect"), cwd=workspace, env=os.environ)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProbeError("temporary_approval_preflight", f"{type(exc).__name__}: {exc}") from exc
        if trust_preflight.returncode != 1:
            raise ProbeError("temporary_approval_preflight", f"inspect exit={trust_preflight.returncode}", trust_preflight)
        approval_command = build_trust_command(trust_cli, workspace, "approve")
        result["temporary_approval_command"] = approval_command
        _run_interactive_required(approval_command, cwd=workspace, stage="temporary_approval")
        temporary_approval_created = True
        _run_required([*command, "sessions", "new"], cwd=workspace, env=first_environment, stage="acpx_new_session")
        archive = run_root / "session.json"
        _run_required(
            [*command, "sessions", "export", "--output", str(archive)],
            cwd=workspace,
            env=first_environment,
            stage="acpx_export_session",
        )
        initial_capability_payload = extract_acpx_archive_capability_payload(archive)
        _run_required(
            [*command, "sessions", "import", str(archive)],
            cwd=workspace,
            env=second_environment,
            stage="acpx_import_session",
        )
        try:
            load_attempt = _run([*command, "set-mode", "p11-session-load-reprobe"], cwd=workspace, env=second_environment)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProbeError("acpx_recovery", f"{type(exc).__name__}: {exc}") from exc
        recovery_evidence = capture_acpx_evidence(load_attempt)
        capability_payload = initial_capability_payload
        load_exchange = recovery_evidence["session_load_exchange"]
        evaluated = evaluate_session_load_exchange(capability_payload, load_exchange)
        result.update(
            {
                "finding": evaluated.finding.value,
                "capability_payload": evaluated.capability_payload,
                "session_load_exchange": evaluated.load_exchange,
                "acpx_initialization": {
                    "evidence_source": "acpx session export",
                    "capability_payload": _safe_payload(initial_capability_payload),
                },
                "acpx_recovery": recovery_evidence,
            }
        )
        if evaluated.finding is Finding.INDETERMINATE:
            result.update(classify_indeterminate_context(recovery_evidence))
        else:
            result["indeterminate_reason"] = None
    except ProbeError as exc:
        result["failure"] = {"stage": exc.stage, "message": _safe_payload(str(exc))}
        if exc.command_result is not None:
            failure_evidence = capture_acpx_evidence(exc.command_result)
            result["acpx_failure"] = failure_evidence
            result["capability_payload"] = failure_evidence["capability_payload"]
            result["session_load_exchange"] = failure_evidence["session_load_exchange"]
            result.update(classify_indeterminate_context(failure_evidence))
    finally:
        if temporary_approval_created and run_root is not None and trust_cli is not None:
            workspace = run_root / "workspace"
            try:
                result["temporary_revoke_command"] = build_trust_command(trust_cli, workspace, "revoke")
                _revoke_temporary_approval(trust_cli, workspace, cwd=workspace)
                result["temporary_launch_approval_revoked"] = True
            except ProbeError as exc:
                cleanup_succeeded = False
                result["temporary_launch_approval_revoked"] = False
                result["cleanup_failure"] = {"stage": exc.stage, "message": _safe_payload(str(exc))}
                result["cleanup_remediation"] = build_cleanup_remediation(trust_cli, workspace)
                result["finding"] = Finding.INDETERMINATE.value
        if run_root is not None and run_root.exists() and cleanup_succeeded:
            try:
                shutil.rmtree(run_root)
            except OSError as exc:
                cleanup_succeeded = False
                result["cleanup_failure"] = {
                    "stage": "throwaway_workspace_remove",
                    "message": _safe_payload(f"{type(exc).__name__}: {exc}"),
                }
                result["cleanup_remediation"] = ["remove-throwaway-workspace", str(run_root)]
                result["finding"] = Finding.INDETERMINATE.value
        result["throwaway_workspace_removed"] = run_root is not None and not run_root.exists()
    return result


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path, help="existing throwaway parent directory; never a repository")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    print(json.dumps(run_probe(args.workspace), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
