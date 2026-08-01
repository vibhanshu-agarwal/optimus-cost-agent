"""Investigation-only probe: real ``zed://`` OS scheme against Zed 1.13.1.

Creates no collector adapter, registry ID, support module, entry point, feature
flag, or scenario capability. A negative result completes the investigation.

Operator authorization (Task 11): URI *shape* is determined in-probe from the
verified Windows registry handler template (``Zed.exe "%1"``) plus a small set of
bounded candidate forms; the probe file path is generated under ``tmp_path``.
Optional override: ``OPTIMUS_EVIDENCE_ZED_SCHEME_URI`` supplies one exact URI.

Markers: evidence_investigation, requires_zed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pytest

from tools.evidence_gather_support import zed_logs as zed_mod
from tools.evidence_gather_support.common import HostError

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = REPO_ROOT / "reports" / "task11-evidence-collector"
ProbeOutcome = Literal["supported", "unsupported", "indeterminate"]

pytestmark = [
    pytest.mark.evidence_investigation,
    pytest.mark.requires_zed,
]

_SW_SHOWNORMAL = 1
_SCHEME_KEY_PATHS = (
    r"HKCR\zed\shell\open\command",
    r"HKCU\Software\Classes\zed\shell\open\command",
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _zed_executable() -> Path:
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        pytest.fail("LOCALAPPDATA_missing")
    for relative in (
        Path("Programs") / "Zed" / "bin" / "Zed.exe",
        Path("Programs") / "Zed" / "Zed.exe",
    ):
        candidate = Path(local) / relative
        if candidate.is_file():
            return candidate.resolve()
    pytest.fail("zed_executable_missing")


def _require_zed_version(exe: Path) -> str:
    completed = subprocess.run(
        [str(exe), "--version"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=30,
    )
    version = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0 or not version:
        pytest.fail("zed_version_failed")
    try:
        zed_mod.require_supported_client_identity("zed-1.13.1", reported_version=version)
    except HostError as exc:
        pytest.fail(f"zed_version_unsupported:{exc.code}:{version}")
    return version


def _reg_query(key_path: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["reg", "query", key_path],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=30,
    )
    stdout = completed.stdout or ""
    match = re.search(r"REG_SZ\s+(.+)$", stdout, flags=re.MULTILINE)
    command = match.group(1).strip() if match else None
    return {
        "key": key_path,
        "returncode": completed.returncode,
        "command": command,
        "command_sha256": _sha256_text(command) if command else None,
        "stdout_sha256": _sha256_text(stdout),
        "stderr_sha256": _sha256_text(completed.stderr or ""),
    }


def _read_scheme_registration() -> dict[str, Any]:
    entries = [_reg_query(path) for path in _SCHEME_KEY_PATHS]
    commands = [item["command"] for item in entries if item.get("command")]
    registered = bool(commands)
    # Handler must pass the URI through as %1 (raw scheme string to Zed).
    percent_one = all("%1" in str(command) for command in commands) if commands else False
    return {
        "registered": registered,
        "percent_one_passthrough": percent_one,
        "entries": entries,
    }


def _candidate_uris(probe_file: Path) -> list[dict[str, str]]:
    """Bounded URI shapes derived from registry ``"%1"`` passthrough semantics."""
    override = os.environ.get("OPTIMUS_EVIDENCE_ZED_SCHEME_URI", "").strip()
    if override:
        if not override.lower().startswith("zed:"):
            pytest.fail("scheme_uri_override_not_zed_scheme")
        return [{"shape": "operator_override", "uri": override}]

    absolute = probe_file.resolve()
    as_posix = absolute.as_posix()
    # Drive form without the leading slash confusion: C:/Users/...
    drive_slash = as_posix if re.match(r"^[A-Za-z]:/", as_posix) else as_posix
    quoted = urllib.parse.quote(as_posix, safe="/:")
    return [
        {"shape": "file_triple_slash_drive", "uri": f"zed:///{drive_slash}"},
        {"shape": "file_host_path", "uri": f"zed://file/{drive_slash}"},
        {"shape": "file_query_path", "uri": f"zed://file?path={quoted}"},
    ]


def _process_command_lines(*, uri: str | None = None) -> list[dict[str, str]]:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-CimInstance Win32_Process -Filter \"Name='Zed.exe'\" "
                "| ForEach-Object { \"{0}`t{1}\" -f $_.ProcessId, $_.CommandLine }"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=30,
    )
    rows: list[dict[str, str]] = []
    for line in (completed.stdout or "").splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2 or not parts[0].strip().isdigit():
            continue
        cmdline = parts[1]
        rows.append(
            {
                "pid": parts[0].strip(),
                "command_line_sha256": _sha256_text(cmdline),
                "command_line_len": str(len(cmdline)),
                "contains_zed_scheme": str(
                    "zed://" in cmdline.lower() or cmdline.lower().startswith("zed:")
                ).lower(),
                "contains_exact_uri": str(uri is not None and uri in cmdline).lower(),
            }
        )
    return rows


def _enum_window_titles_for_pids(pids: set[int]) -> list[dict[str, Any]]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[dict[str, Any]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        proc = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc))
        if int(proc.value) not in pids:
            return True
        length = int(user32.GetWindowTextLengthW(hwnd))
        title = ""
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
        found.append(
            {
                "hwnd": int(hwnd),
                "pid": int(proc.value),
                "title_len": len(title),
                "title_sha256": _sha256_text(title),
                "title_has_probe_name": False,  # filled by caller with probe name
                "title": title,
            }
        )
        return True

    user32.EnumWindows(_callback, 0)
    return found


def _invoke_os_scheme(uri: str) -> dict[str, Any]:
    """Invoke the registered scheme via ShellExecuteW (real OS handler path)."""
    # Do not call Zed.exe directly — that would bypass scheme registration.
    # Import windll only here so Linux CI can collect this module under marker
    # deselection without a Windows-only ctypes attribute.
    from ctypes import windll

    windll.ole32.CoInitializeEx(None, 0x0)
    rc = int(windll.shell32.ShellExecuteW(None, "open", uri, None, None, _SW_SHOWNORMAL))
    # Per MSDN, values > 32 indicate success.
    return {
        "mechanism": "ShellExecuteW",
        "uri_sha256": _sha256_text(uri),
        "uri_len": len(uri),
        "shell_execute_rc": rc,
        "ok": rc > 32,
    }


def _log_root_snapshot() -> tuple[Path, set[str], int]:
    root = zed_mod.require_zed_log_root(
        zed_mod.default_live_zed_log_root(),
        expected_live_root=zed_mod.default_live_zed_log_root(),
    )
    names = {path.name for path in root.iterdir() if path.is_file()}
    return root, names, time.monotonic_ns()


def _observe_after_invoke(
    *,
    probe_name: str,
    uri: str,
    pre_pids: tuple[int, ...],
    pre_cmd_sha256: set[str],
    pre_log_names: set[str],
    log_root: Path,
    wait_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + wait_seconds
    last: dict[str, Any] = {
        "timed_out": True,
        "pids": list(pre_pids),
        "command_lines": [],
        "windows": [],
        "new_log_names": [],
        "title_matched_probe": False,
        "cmdline_matched_uri": False,
        "new_process_seen": False,
        "new_cmdline_seen": False,
    }
    while time.monotonic() < deadline:
        try:
            pids = zed_mod.discover_zed_editor_pids()
        except HostError:
            pids = ()
        cmd_rows = _process_command_lines(uri=uri)
        windows = _enum_window_titles_for_pids(set(pids) | set(pre_pids))
        for window in windows:
            title = str(window.pop("title", ""))
            window["title_has_probe_name"] = probe_name in title
        new_logs = sorted(
            name for name in ({path.name for path in log_root.iterdir() if path.is_file()} - pre_log_names)
        )
        title_hit = any(window.get("title_has_probe_name") for window in windows)
        uri_hit = any(row.get("contains_exact_uri") == "true" for row in cmd_rows)
        new_process = any(int(pid) not in set(pre_pids) for pid in pids)
        new_cmdline = any(row.get("command_line_sha256") not in pre_cmd_sha256 for row in cmd_rows)
        last = {
            "timed_out": False,
            "elapsed_s": round(wait_seconds - (deadline - time.monotonic()), 3),
            "pids": list(pids),
            "command_lines": cmd_rows,
            "windows": windows,
            "new_log_names": new_logs,
            "title_matched_probe": title_hit,
            "cmdline_matched_uri": uri_hit,
            "new_process_seen": new_process,
            "new_cmdline_seen": new_cmdline,
        }
        if title_hit or (uri_hit and (new_process or new_cmdline)):
            return last
        time.sleep(0.5)
    last["timed_out"] = True
    last["elapsed_s"] = wait_seconds
    return last


def _classify_attempt(observation: dict[str, Any], invoke: dict[str, Any]) -> tuple[ProbeOutcome, str]:
    if not invoke.get("ok"):
        return "indeterminate", "shell_execute_failed"
    if observation.get("title_matched_probe"):
        return "supported", "window_title_shows_probe_file"
    if observation.get("cmdline_matched_uri") and (
        observation.get("new_process_seen") or observation.get("new_cmdline_seen")
    ):
        return "indeterminate", "uri_reached_process_without_title_confirmation"
    return "unsupported", "scheme_invoked_without_observable_editor_effect"


def test_zed_scheme_live_investigation(tmp_path: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("zed_scheme_requires_windows_registry")

    started = datetime.now(tz=UTC).isoformat()
    exe = _zed_executable()
    version = _require_zed_version(exe)
    registration = _read_scheme_registration()
    if not registration["registered"]:
        evidence = {
            "schema": "evidence-investigation-zed-scheme-v1",
            "complete": True,
            "result": "unsupported",
            "reason_code": "scheme_not_registered",
            "started_at": started,
            "ended_at": datetime.now(tz=UTC).isoformat(),
            "zed_version": version,
            "registration": registration,
        }
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        body = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
        digest = _sha256_text(body)
        evidence["evidence_sha256"] = digest
        (EVIDENCE_DIR / "zed-scheme-result.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"result": "unsupported", "reason_code": "scheme_not_registered", "digest": digest}, sort_keys=True))
        assert evidence["result"] == "unsupported"
        return

    if not registration["percent_one_passthrough"]:
        evidence = {
            "schema": "evidence-investigation-zed-scheme-v1",
            "complete": True,
            "result": "indeterminate",
            "reason_code": "scheme_handler_missing_percent_one",
            "started_at": started,
            "ended_at": datetime.now(tz=UTC).isoformat(),
            "zed_version": version,
            "registration": registration,
        }
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        body = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
        digest = _sha256_text(body)
        evidence["evidence_sha256"] = digest
        (EVIDENCE_DIR / "zed-scheme-result.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"result": "indeterminate", "reason_code": "scheme_handler_missing_percent_one", "digest": digest}, sort_keys=True))
        assert evidence["result"] == "indeterminate"
        return

    probe = (tmp_path / "zed-scheme-probe.txt").resolve()
    probe.write_text("optimus-zed-scheme-probe\n", encoding="utf-8")
    candidates = _candidate_uris(probe)
    try:
        pre_pids = zed_mod.discover_zed_editor_pids()
    except HostError:
        pre_pids = ()
    pre_cmd = _process_command_lines()
    pre_cmd_sha256 = {row["command_line_sha256"] for row in pre_cmd}
    log_root, pre_log_names, _ = _log_root_snapshot()

    attempts: list[dict[str, Any]] = []
    overall: ProbeOutcome = "unsupported"
    overall_reason = "all_candidates_unsupported"
    wait_seconds = float(os.environ.get("OPTIMUS_EVIDENCE_ZED_SCHEME_WAIT_SECONDS", "12"))

    for candidate in candidates:
        invoke = _invoke_os_scheme(candidate["uri"])
        invoked_at = datetime.now(tz=UTC).isoformat()
        observation = _observe_after_invoke(
            probe_name=probe.name,
            uri=candidate["uri"],
            pre_pids=pre_pids,
            pre_cmd_sha256=pre_cmd_sha256,
            pre_log_names=pre_log_names,
            log_root=log_root,
            wait_seconds=wait_seconds,
        )
        result, reason = _classify_attempt(observation, invoke)
        attempts.append(
            {
                "shape": candidate["shape"],
                "uri_sha256": _sha256_text(candidate["uri"]),
                "uri_len": len(candidate["uri"]),
                "invoked_at": invoked_at,
                "invoke": invoke,
                "observation": observation,
                "result": result,
                "reason_code": reason,
            }
        )
        if result == "supported":
            overall = "supported"
            overall_reason = reason
            break
        if result == "indeterminate" and overall != "supported":
            overall = "indeterminate"
            overall_reason = reason

    ended = datetime.now(tz=UTC).isoformat()
    evidence = {
        "schema": "evidence-investigation-zed-scheme-v1",
        "complete": True,
        "result": overall,
        "reason_code": overall_reason,
        "started_at": started,
        "ended_at": ended,
        "zed_version": version,
        "zed_exe_sha256": _sha256_text(str(exe)),
        "registration": registration,
        "probe_file_sha256": _sha256_text(probe.read_text(encoding="utf-8")),
        "probe_name": probe.name,
        "wait_seconds": wait_seconds,
        "pre_pids": list(pre_pids),
        "attempts": attempts,
        "cleanup": {"note": "left Zed running; probe file may remain open"},
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    digest = _sha256_text(body)
    evidence["evidence_sha256"] = digest
    (EVIDENCE_DIR / "zed-scheme-result.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "result": overall,
                "reason_code": overall_reason,
                "attempts": len(attempts),
                "evidence_sha256": digest,
                "shapes": [item["shape"] for item in attempts],
            },
            sort_keys=True,
        )
    )
    assert overall in {"supported", "unsupported", "indeterminate"}
    assert overall_reason
