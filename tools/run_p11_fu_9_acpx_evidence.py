#!/usr/bin/env python3
"""P11-FU-9 Task 8: real-acpx client-MCP evidence helper.

Invokes the independently authored ``acpx`` binary only. Never imports the
project ACP protocol stack, framing helpers, or any project-authored ACP client.
Scratch ``.acpxrc.json`` / ``mcpServers.json`` / ``tmp/`` must be gitignored
before write. Reports contain only content-free digests, versions, and safe names.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SCHEMA_VERSION = "p11-fu-9-acpx-client-mcp-evidence-v1"
DEFAULT_MD_REPORT = ROOT / "reports" / "p11-fu-9-client-mcp-live-evidence.md"
DEFAULT_JSON_REPORT = ROOT / "reports" / "p11-fu-9-client-mcp-live-evidence.json"
ACP_TIMEOUT_SECONDS = 600.0
AGENT_NAME = "optimus-fu9"

SCRATCH_IGNORE_CANDIDATES: tuple[str, ...] = (".acpxrc.json", "mcpServers.json", "tmp/")

DISALLOWED_PROJECT_ACP_MODULES: tuple[str, ...] = (
    "optimus.acp.dispatcher",
    "optimus.acp.server",
    "optimus.acp.bootstrap",
    "optimus.acp.__main__",
    "optimus.acp.ndjson_subprocess_session",
    "optimus.acp.e2e_transcript",
    "optimus.acp.spec",
    "optimus.acp.framing",
)


class AcpxNotFoundError(RuntimeError):
    """Raised when the independent ``acpx`` binary is missing."""


class AcpxEvidenceError(ValueError):
    """Raised when scratch/report safety checks fail closed."""


@dataclass(frozen=True)
class ScratchConfigPaths:
    acpxrc: Path
    mcp_servers: Path


def resolve_acpx() -> str:
    acpx = shutil.which("acpx")
    if acpx is None:
        raise AcpxNotFoundError(
            "acpx not found on PATH. Install the independent acpx ACP client "
            "(https://github.com/openclaw/acpx); never substitute a project client."
        )
    return acpx


def resolve_optimus_agent() -> str:
    agent = shutil.which("optimus-agent")
    if agent is None:
        candidate = ROOT / ".venv" / "Scripts" / "optimus-agent.exe"
        if candidate.is_file():
            return str(candidate.resolve())
        wsl_candidate = ROOT / ".venv-wsl" / "bin" / "optimus-agent"
        if wsl_candidate.is_file():
            return str(wsl_candidate.resolve())
        raise AcpxNotFoundError("optimus-agent not found on PATH")
    return agent


def acpx_version(acpx: str) -> str:
    completed = subprocess.run(  # noqa: S603
        [acpx, "--version"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise AcpxEvidenceError("acpx --version failed")
    version = (completed.stdout or completed.stderr or "").strip()
    if not version:
        raise AcpxEvidenceError("acpx --version returned empty output")
    return version


def assert_scratch_paths_ignored(*, repo_root: Path) -> None:
    """Fail closed unless scratch candidates are ignored.

    Prefers ``git check-ignore -q``. When git cannot open the worktree (exit 128 —
    common for Windows-authored worktrees mounted under WSL), fall back to an
    exact ``.gitignore`` pattern membership check so the harness still refuses
    unignored scratch without fabricating a green live claim.
    """
    git_ok = True
    for candidate in SCRATCH_IGNORE_CANDIDATES:
        completed = subprocess.run(  # noqa: S603
            ["git", "check-ignore", "-q", "--", candidate],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=30,
        )
        if completed.returncode == 0:
            continue
        if completed.returncode == 128:
            git_ok = False
            break
        raise AcpxEvidenceError(
            f"git check-ignore failed for {candidate!r} (exit {completed.returncode}); "
            "refuse to write unignored ACP/MCP scratch"
        )
    if git_ok:
        return

    gitignore = repo_root / ".gitignore"
    if not gitignore.is_file():
        raise AcpxEvidenceError("git unavailable and .gitignore missing; refuse scratch write")
    lines = {
        line.strip()
        for line in gitignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    missing = [candidate for candidate in SCRATCH_IGNORE_CANDIDATES if candidate not in lines]
    if missing:
        raise AcpxEvidenceError(
            f"git worktree unusable and .gitignore missing scratch rules: {missing}"
        )


def build_acpxrc_document(*, agent_argv: Sequence[str]) -> dict[str, Any]:
    """Windows-safe structured argv for the custom ``optimus-fu9`` agent name."""
    return {"agents": {AGENT_NAME: {"argv": list(agent_argv)}}}


def build_mcp_servers_document(servers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"mcpServers": [dict(server) for server in servers]}


def build_acpx_command(
    *,
    acpx: str,
    cwd: Path,
    mcp_config: Path,
    task: str,
) -> list[str]:
    return [
        acpx,
        "--mcp-config",
        str(mcp_config),
        "--format",
        "json",
        "--approve-all",
        "--cwd",
        str(cwd),
        AGENT_NAME,
        "exec",
        task,
    ]


def write_scratch_configs(
    *,
    scratch_dir: Path,
    repo_root: Path,
    agent_argv: Sequence[str],
    mcp_servers: Sequence[Mapping[str, Any]],
) -> ScratchConfigPaths:
    assert_scratch_paths_ignored(repo_root=repo_root)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    acpxrc = scratch_dir / ".acpxrc.json"
    mcp_servers_path = scratch_dir / "mcpServers.json"
    acpxrc.write_text(
        json.dumps(build_acpxrc_document(agent_argv=agent_argv), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    mcp_servers_path.write_text(
        json.dumps(build_mcp_servers_document(mcp_servers), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return ScratchConfigPaths(acpxrc=acpxrc, mcp_servers=mcp_servers_path)


def parse_jsonl_records(text: str) -> list[dict[str, Any]]:
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


def _path_digest(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def extract_safe_evidence(
    records: Sequence[Mapping[str, Any]],
    *,
    acpx_path: str,
    acpx_version: str,
    exit_code: int,
) -> dict[str, Any]:
    """Reduce acpx JSONL to content-free evidence fields only."""
    protocol_version: int | None = None
    session_id: str | None = None
    stop_reason: str | None = None
    mcp_capabilities: dict[str, bool] | None = None
    tool_titles: list[str] = []
    permission_option_ids: list[str] = []

    for record in records:
        result = record.get("result")
        if isinstance(result, dict):
            if isinstance(result.get("protocolVersion"), int) and protocol_version is None:
                protocol_version = result["protocolVersion"]
            caps = result.get("agentCapabilities")
            if isinstance(caps, dict):
                mcp_caps = caps.get("mcpCapabilities")
                if isinstance(mcp_caps, dict) and mcp_capabilities is None:
                    mcp_capabilities = {
                        "http": bool(mcp_caps.get("http")),
                        "sse": bool(mcp_caps.get("sse")),
                    }
            if isinstance(result.get("sessionId"), str) and session_id is None:
                session_id = result["sessionId"]
            if isinstance(result.get("stopReason"), str):
                stop_reason = result["stopReason"]

        params = record.get("params")
        if isinstance(params, dict):
            update = params.get("update")
            if isinstance(update, dict) and update.get("sessionUpdate") == "tool_call":
                title = update.get("title")
                if isinstance(title, str):
                    tool_titles.append(title)
            options = params.get("options")
            if isinstance(options, list):
                for option in options:
                    if isinstance(option, dict) and isinstance(option.get("optionId"), str):
                        permission_option_ids.append(option["optionId"])

    return {
        "acpx_version": acpx_version,
        "acpx_path_digest": _path_digest(acpx_path),
        "acp_protocol_version": protocol_version,
        "session_id": session_id,
        "stop_reason": stop_reason,
        "mcp_capabilities": mcp_capabilities or {"http": False, "sse": False},
        "tool_call_titles": tool_titles,
        "permission_option_ids": sorted(set(permission_option_ids)),
        "exit_code": exit_code,
    }


def assert_report_has_no_secrets(payload: Mapping[str, Any], *, known_secrets: Sequence[str]) -> None:
    rendered = json.dumps(payload, sort_keys=True)
    for secret in known_secrets:
        if secret and secret in rendered:
            raise AcpxEvidenceError("secret value leaked into evidence report")


def build_evidence_summary(
    *,
    evidence: Mapping[str, Any],
    mcp_servers_count: int,
    capture_complete: bool,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "acpx_client": "external (independent acpx binary; no project ACP client used)",
        "capture_complete": capture_complete,
        "empty_mcp_servers_noop": mcp_servers_count == 0,
        "mcp_servers_count": mcp_servers_count,
        **dict(evidence),
    }


def write_reports(
    *,
    md_path: Path,
    json_path: Path,
    summary: Mapping[str, Any],
) -> None:
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(dict(summary), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(
        "# P11-FU-9 client MCP live acpx evidence\n\n"
        "Content-free summary only. Raw transcripts stay in ignored scratch.\n\n"
        "```json\n"
        + json.dumps(dict(summary), indent=2, sort_keys=True)
        + "\n```\n",
        encoding="utf-8",
    )


def run_capture(
    *,
    scratch_dir: Path,
    repo_root: Path,
    task: str,
    mcp_servers: Sequence[Mapping[str, Any]],
    md_report: Path,
    json_report: Path,
    agent_argv: Sequence[str] | None = None,
    timeout: float = ACP_TIMEOUT_SECONDS,
    known_secrets: Sequence[str] = (),
) -> int:
    acpx = resolve_acpx()
    version = acpx_version(acpx)
    argv = list(agent_argv) if agent_argv is not None else [resolve_optimus_agent(), "--workspace-root", str(scratch_dir)]
    paths = write_scratch_configs(
        scratch_dir=scratch_dir,
        repo_root=repo_root,
        agent_argv=argv,
        mcp_servers=mcp_servers,
    )
    command = build_acpx_command(
        acpx=acpx,
        cwd=scratch_dir,
        mcp_config=paths.mcp_servers,
        task=task,
    )
    proc = subprocess.run(  # noqa: S603
        command,
        cwd=scratch_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
        check=False,
    )
    # Persist raw transcript only under ignored scratch.
    (scratch_dir / "tmp").mkdir(parents=True, exist_ok=True)
    (scratch_dir / "tmp" / "acpx.stdout.jsonl").write_text(proc.stdout or "", encoding="utf-8")
    (scratch_dir / "tmp" / "acpx.stderr.txt").write_text(proc.stderr or "", encoding="utf-8")

    records = parse_jsonl_records(proc.stdout or "")
    evidence = extract_safe_evidence(
        records,
        acpx_path=acpx,
        acpx_version=version,
        exit_code=proc.returncode,
    )
    capture_complete = evidence.get("session_id") is not None and evidence.get("stop_reason") is not None
    summary = build_evidence_summary(
        evidence=evidence,
        mcp_servers_count=len(mcp_servers),
        capture_complete=bool(capture_complete),
    )
    assert_report_has_no_secrets(summary, known_secrets=known_secrets)
    write_reports(md_path=md_report, json_path=json_report, summary=summary)
    return proc.returncode


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--task", required=True)
    parser.add_argument("--mcp-servers-json", type=Path, default=None)
    parser.add_argument("--md-report", type=Path, default=DEFAULT_MD_REPORT)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--timeout", type=float, default=ACP_TIMEOUT_SECONDS)
    return parser.parse_args(sys.argv[1:] if argv is None else argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    servers: list[dict[str, Any]] = []
    if args.mcp_servers_json is not None:
        loaded = json.loads(args.mcp_servers_json.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("mcpServers"), list):
            servers = list(loaded["mcpServers"])
        elif isinstance(loaded, list):
            servers = list(loaded)
        else:
            raise AcpxEvidenceError("mcp-servers-json must be a list or {mcpServers: [...]}")
    try:
        return run_capture(
            scratch_dir=args.scratch_dir,
            repo_root=args.repo_root,
            task=args.task,
            mcp_servers=servers,
            md_report=args.md_report,
            json_report=args.json_report,
            timeout=args.timeout,
        )
    except (AcpxNotFoundError, AcpxEvidenceError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired as exc:
        print(f"acpx did not complete within {exc.timeout}s", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
