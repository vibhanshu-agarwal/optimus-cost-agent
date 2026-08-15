#!/usr/bin/env python3
"""P11-FU-10: real-acpx duplicate error-code observation helper.

Invokes the independently authored ``acpx`` binary only. Never imports the
project ACP protocol stack or any project-authored ACP client. A throwaway
probe agent in a temporary directory returns ``-32001`` then ``-32911`` so
an external client can observe those envelopes. The observation cannot
justify retaining a JSON-RPC reserved-band code.
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
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "reports" / "plan-11-18-p11-fu-10-acpx-error-code-evidence.md"
PROBED_CODES: tuple[int, int] = (-32001, -32911)
ACP_TIMEOUT_SECONDS = 25.0
UNCONDITIONAL_ALLOCATION_REASON = (
    "The application duplicate-ID code changed unconditionally because -32001 is inside "
    "JSON-RPC's reserved band (-32768..-32000). This observation is evidence about one "
    "real client; it is not permission to retain a protocol-invalid number. "
    "DUPLICATE_REQUEST_ID remains -32911."
)

PROBE_AGENT_SOURCE = '''\
import json
import os
import sys
import threading

CODE = int(os.environ["P11_FU_10_PROBE_CODE"])
FRAMING = {"mode": None}
threading.Timer(20, lambda: os._exit(1)).start()


def read_message():
    first = sys.stdin.buffer.read(1)
    if not first:
        return None
    if first == b"{":
        FRAMING["mode"] = "ndjson"
        line = first + sys.stdin.buffer.readline()
        return json.loads(line.decode("utf-8"))
    header = first
    while b"\\r\\n\\r\\n" not in header:
        chunk = sys.stdin.buffer.read(1)
        if not chunk:
            return None
        header += chunk
    FRAMING["mode"] = "content-length"
    length = 0
    for raw_line in header.split(b"\\r\\n"):
        name, separator, value = raw_line.partition(b":")
        if separator and name.strip().lower() == b"content-length":
            length = int(value.strip())
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))


def write_message(payload):
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if FRAMING["mode"] == "ndjson":
        sys.stdout.buffer.write(raw + b"\\n")
    else:
        sys.stdout.buffer.write(
            b"Content-Length: " + str(len(raw)).encode("ascii") + b"\\r\\n\\r\\n" + raw
        )
    sys.stdout.buffer.flush()


while True:
    request = read_message()
    if request is None:
        break
    write_message(
        {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {"code": CODE, "message": "p11-fu-10 probe"},
        }
    )
'''


class AcpxNotFoundError(RuntimeError):
    """Raised when the independent ``acpx`` binary is missing."""


class AcpxEvidenceError(ValueError):
    """Raised when the evidence runner fails closed."""


def resolve_acpx() -> str:
    acpx = shutil.which("acpx")
    if acpx is None:
        raise AcpxNotFoundError(
            "acpx not found on PATH. Install the independent acpx ACP client "
            "(https://github.com/openclaw/acpx); never substitute a project client."
        )
    return acpx


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


def assert_report_destination(path: Path, *, reports_root: Path) -> None:
    resolved = path.resolve()
    root = reports_root.resolve()
    if not resolved.is_relative_to(root):
        raise AcpxEvidenceError(
            f"report destination {resolved} is outside {root}; refuse to write evidence"
        )


def assert_report_has_no_secrets(report_text: str, *, known_secrets: Sequence[str] = ()) -> None:
    markers = ("OPTIMUS_API_KEY=", *tuple(secret for secret in known_secrets if secret))
    for marker in markers:
        if marker in report_text:
            raise AcpxEvidenceError("secret value leaked into evidence report")


def classify_probe_output(*, stdout: str, stderr: str) -> str:
    combined = f"{stdout}\n{stderr}"
    if any(str(code) in combined for code in PROBED_CODES) and "error" in combined.casefold():
        return "error_envelope_observed"
    return "client_output_unclassified"


def build_report(
    *,
    acpx_path: str,
    acpx_version: str,
    probes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "acpx_client": "external (independent acpx binary; no project ACP client used)",
        "acpx_version": acpx_version,
        "acpx_path_digest": hashlib.sha256(acpx_path.encode("utf-8")).hexdigest(),
        "probed_codes": [int(probe["code"]) for probe in probes],
        "probes": [
            {
                "code": int(probe["code"]),
                "exit_code": int(probe["exit_code"]),
                "classification": str(probe["classification"]),
            }
            for probe in probes
        ],
        "unconditional_allocation_reason": UNCONDITIONAL_ALLOCATION_REASON,
    }


def build_acpx_command(*, acpx: str, cwd: Path, agent_invocation: str, task: str) -> list[str]:
    return [
        acpx,
        "--format",
        "json",
        "--approve-all",
        "--timeout",
        "15",
        "--ttl",
        "5",
        "--cwd",
        str(cwd),
        "--agent",
        agent_invocation,
        "exec",
        task,
    ]


def _agent_invocation(python: str, probe_path: Path) -> str:
    return f"{python.replace(chr(92), '/')} {probe_path.as_posix()}"


def _write_probe_agent(scratch_dir: Path) -> Path:
    probe_path = scratch_dir / "probe_agent.py"
    probe_path.write_text(PROBE_AGENT_SOURCE, encoding="utf-8")
    return probe_path


def _kill_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(  # noqa: S603
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            check=False,
            shell=False,
            timeout=30,
        )
        return
    try:
        os.kill(pid, 9)
    except OSError:
        pass


def _run_acpx(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: float,
) -> tuple[int, str, str]:
    process = subprocess.Popen(  # noqa: S603
        list(command),
        cwd=str(cwd),
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process.pid)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except Exception:
            stdout, stderr = "", ""
        raise AcpxEvidenceError("acpx probe timed out") from None
    return int(process.returncode or 0), stdout or "", stderr or ""


def _run_one_probe(
    *,
    acpx: str,
    python: str,
    probe_path: Path,
    scratch_dir: Path,
    code: int,
    timeout: float,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["P11_FU_10_PROBE_CODE"] = str(code)
    command = build_acpx_command(
        acpx=acpx,
        cwd=scratch_dir,
        agent_invocation=_agent_invocation(python, probe_path),
        task="p11-fu-10 error-code probe",
    )
    exit_code, stdout, stderr = _run_acpx(command, cwd=scratch_dir, env=env, timeout=timeout)
    classification = classify_probe_output(stdout=stdout, stderr=stderr)
    if classification != "error_envelope_observed":
        raise AcpxEvidenceError(
            f"acpx probe for {code} could not be driven; classification={classification}"
        )
    return {
        "code": code,
        "exit_code": exit_code,
        "classification": classification,
    }


def write_markdown_report(path: Path, report: Mapping[str, Any]) -> None:
    body = (
        "# Plan 11.18 P11-FU-10 acpx error-code evidence\n\n"
        "Sanitized observation of an independently authored `acpx` client against a "
        "throwaway probe agent. No raw transcript, task prompt, environment, or "
        "credentials are recorded.\n\n"
        f"{UNCONDITIONAL_ALLOCATION_REASON}\n\n"
        "```json\n"
        + json.dumps(dict(report), indent=2, sort_keys=True)
        + "\n```\n"
    )
    assert_report_has_no_secrets(body)
    path.write_text(body, encoding="utf-8")


def run_capture(
    *,
    report_path: Path,
    reports_root: Path = ROOT / "reports",
    timeout: float = ACP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    assert_report_destination(report_path, reports_root=reports_root)
    acpx = resolve_acpx()
    version = acpx_version(acpx)
    with tempfile.TemporaryDirectory(prefix="p11-fu-10-acpx-") as scratch:
        scratch_dir = Path(scratch)
        probe_path = _write_probe_agent(scratch_dir)
        probes = [
            _run_one_probe(
                acpx=acpx,
                python=sys.executable,
                probe_path=probe_path,
                scratch_dir=scratch_dir,
                code=code,
                timeout=timeout,
            )
            for code in PROBED_CODES
        ]
    report = build_report(acpx_path=acpx, acpx_version=version, probes=probes)
    rendered = json.dumps(report, sort_keys=True)
    assert_report_has_no_secrets(rendered)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_markdown_report(report_path, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        run_capture(report_path=args.report)
    except AcpxNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except AcpxEvidenceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
