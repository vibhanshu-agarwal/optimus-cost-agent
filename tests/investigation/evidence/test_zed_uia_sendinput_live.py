"""Investigation-only probe: real UIA + SendInput against Zed 1.13.1.

Creates no collector adapter, registry ID, support module, entry point, feature
flag, or scenario capability. A negative result completes the investigation.

Markers: evidence_investigation, requires_zed, requires_windows_desktop.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pytest

from tools.evidence_gather_support import zed_logs as zed_mod
from tools.evidence_gather_support.common import HostError

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = REPO_ROOT / "reports" / "task10-evidence-collector"
ProbeOutcome = Literal["supported", "unsupported", "indeterminate"]

pytestmark = [
    pytest.mark.evidence_investigation,
    pytest.mark.requires_zed,
    pytest.mark.requires_windows_desktop,
]

# Win32 SendInput constants
_INPUT_KEYBOARD = 1
_KEYEVENTF_UNICODE = 0x0004
_KEYEVENTF_KEYUP = 0x0002
_SW_RESTORE = 9


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUT_UNION)]


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _zed_executable() -> Path:
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        pytest.fail("LOCALAPPDATA_missing")
    candidate = Path(local) / "Programs" / "Zed" / "bin" / "Zed.exe"
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


def _resolve_expected_pid(observed: tuple[int, ...]) -> int:
    override = os.environ.get("OPTIMUS_EVIDENCE_ZED_PID", "").strip()
    if override:
        pid = int(override)
        zed_mod.correlate_zed_processes(expected_pids=(pid,), observed_pids=observed)
        return pid
    if not observed:
        raise HostError("zed_process_lookup_failed")
    if len(observed) != 1:
        raise HostError("zed_multi_instance_ambiguous")
    return observed[0]


def _ensure_zed_running(exe: Path, open_path: Path) -> tuple[int, tuple[int, ...]]:
    try:
        observed = zed_mod.discover_zed_editor_pids()
        return _resolve_expected_pid(observed), observed
    except HostError as exc:
        if exc.code == "zed_multi_instance_ambiguous":
            raise
        if exc.code not in {"zed_process_lookup_failed", "zed_unrelated_process"}:
            raise
    subprocess.Popen(  # noqa: S603 — absolute Zed path, shell=False
        [str(exe), str(open_path)],
        cwd=str(REPO_ROOT),
        shell=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            observed = zed_mod.discover_zed_editor_pids()
            return _resolve_expected_pid(observed), observed
        except HostError as exc:
            if exc.code == "zed_multi_instance_ambiguous":
                raise
        time.sleep(0.5)
    pytest.fail("zed_process_not_started")


def _enum_top_level_hwnds_for_pid(pid: int) -> list[int]:
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        proc = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc))
        if int(proc.value) == int(pid):
            found.append(int(hwnd))
        return True

    user32.EnumWindows(_callback, 0)
    return found


def _window_title(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    length = int(user32.GetWindowTextLengthW(hwnd))
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _focus_hwnd(hwnd: int) -> dict[str, Any]:
    user32 = ctypes.windll.user32
    foreground_before = int(user32.GetForegroundWindow() or 0)
    user32.ShowWindow(hwnd, _SW_RESTORE)
    ok = bool(user32.SetForegroundWindow(hwnd))
    time.sleep(0.35)
    foreground_after = int(user32.GetForegroundWindow() or 0)
    return {
        "hwnd": hwnd,
        "set_foreground_ok": ok,
        "foreground_before": foreground_before,
        "foreground_after": foreground_after,
        "focused": foreground_after == hwnd,
    }


def _sendinput_unicode(text: str) -> dict[str, Any]:
    """Inject Unicode key events via real Win32 SendInput (not SendKeys)."""
    user32 = ctypes.windll.user32
    extra = ctypes.pointer(ctypes.c_ulong(0))
    events: list[_INPUT] = []
    for ch in text:
        down = _INPUT(
            type=_INPUT_KEYBOARD,
            union=_INPUT_UNION(
                ki=_KEYBDINPUT(
                    wVk=0,
                    wScan=ord(ch),
                    dwFlags=_KEYEVENTF_UNICODE,
                    time=0,
                    dwExtraInfo=extra,
                )
            ),
        )
        up = _INPUT(
            type=_INPUT_KEYBOARD,
            union=_INPUT_UNION(
                ki=_KEYBDINPUT(
                    wVk=0,
                    wScan=ord(ch),
                    dwFlags=_KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP,
                    time=0,
                    dwExtraInfo=extra,
                )
            ),
        )
        events.extend((down, up))
    array = (_INPUT * len(events))(*events)
    sent = int(user32.SendInput(len(events), ctypes.byref(array), ctypes.sizeof(_INPUT)))
    return {
        "mechanism": "SendInput",
        "chars": len(text),
        "events": len(events),
        "sent": sent,
        "ok": sent == len(events),
        "canary_sha256": _sha256_text(text),
    }


def _uia_probe_powershell(hwnd: int, canary: str) -> dict[str, Any]:
    """Real UI Automation via .NET UIAutomationClient (built-in on Windows)."""
    # Keep the script self-contained; return JSON only; never echo canary plaintext.
    canary_digest = _sha256_text(canary)
    script = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$hwnd = [IntPtr]{int(hwnd)}
$canaryDigest = '{canary_digest}'
$result = [ordered]@{{
  ok = $false
  reason_code = 'uia_failed'
  root_name = $null
  root_control_type = $null
  editable_count = 0
  document_count = 0
  value_pattern_count = 0
  text_pattern_count = 0
  focused_name = $null
  focused_control_type = $null
  focused_has_value_pattern = $false
  focused_has_text_pattern = $false
  value_before_sha256 = $null
  value_after_sha256 = $null
  value_contains_canary = $false
  canary_sha256 = $canaryDigest
}}
try {{
  $auto = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
  if ($null -eq $auto) {{
    $result.reason_code = 'uia_element_from_handle_null'
    $result | ConvertTo-Json -Compress
    exit 0
  }}
  $result.root_name = $auto.Current.Name
  $result.root_control_type = [string]$auto.Current.ControlType.ProgrammaticName
  $editCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Edit
  )
  $docCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Document
  )
  $edits = $auto.FindAll([System.Windows.Automation.TreeScope]::Descendants, $editCond)
  $docs = $auto.FindAll([System.Windows.Automation.TreeScope]::Descendants, $docCond)
  $result.editable_count = $edits.Count
  $result.document_count = $docs.Count
  $valueId = [System.Windows.Automation.ValuePattern]::Pattern
  $textId = [System.Windows.Automation.TextPattern]::Pattern
  $valueHits = 0
  $textHits = 0
  foreach ($el in @($edits + $docs)) {{
    $vp = $null; $tp = $null
    try {{ $vp = $el.GetCurrentPattern($valueId) }} catch {{}}
    try {{ $tp = $el.GetCurrentPattern($textId) }} catch {{}}
    if ($null -ne $vp) {{ $valueHits++ }}
    if ($null -ne $tp) {{ $textHits++ }}
  }}
  $result.value_pattern_count = $valueHits
  $result.text_pattern_count = $textHits
  $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
  if ($null -ne $focused) {{
    $result.focused_name = $focused.Current.Name
    $result.focused_control_type = [string]$focused.Current.ControlType.ProgrammaticName
    $fvp = $null; $ftp = $null
    try {{ $fvp = $focused.GetCurrentPattern($valueId) }} catch {{}}
    try {{ $ftp = $focused.GetCurrentPattern($textId) }} catch {{}}
    $result.focused_has_value_pattern = ($null -ne $fvp)
    $result.focused_has_text_pattern = ($null -ne $ftp)
    if ($null -ne $fvp) {{
      $before = [string]$fvp.Current.Value
      $sha = [System.Security.Cryptography.SHA256]::Create()
      $bytes = [System.Text.Encoding]::UTF8.GetBytes($before)
      $result.value_before_sha256 = ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()
    }}
  }}
  $result.ok = $true
  $result.reason_code = 'uia_ok'
}} catch {{
  $result.reason_code = 'uia_exception'
}}
$result | ConvertTo-Json -Compress
"""
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=60,
    )
    payload: dict[str, Any] = {
        "ok": False,
        "reason_code": "uia_powershell_failed",
        "returncode": completed.returncode,
        "stdout_sha256": _sha256_text(completed.stdout or ""),
        "stderr_sha256": _sha256_text(completed.stderr or ""),
    }
    if completed.returncode != 0:
        return payload
    try:
        parsed = json.loads((completed.stdout or "").strip() or "{}")
    except json.JSONDecodeError:
        payload["reason_code"] = "uia_json_invalid"
        return payload
    if not isinstance(parsed, dict):
        payload["reason_code"] = "uia_json_invalid"
        return payload
    parsed["powershell_returncode"] = completed.returncode
    return parsed


def _uia_read_focused_value() -> dict[str, Any]:
    script = """
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$result = [ordered]@{ ok = $false; value_sha256 = $null; contains_marker = $false; reason_code = 'no_value' }
try {
  $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
  if ($null -eq $focused) { $result.reason_code = 'no_focused'; $result | ConvertTo-Json -Compress; exit 0 }
  $vp = $null
  try { $vp = $focused.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern) } catch {}
  if ($null -eq $vp) { $result.reason_code = 'no_value_pattern'; $result | ConvertTo-Json -Compress; exit 0 }
  $value = [string]$vp.Current.Value
  $sha = [System.Security.Cryptography.SHA256]::Create()
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($value)
  $result.value_sha256 = ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()
  $result.contains_marker = $value.Contains('OPTIMUSUIA')
  $result.ok = $true
  $result.reason_code = 'value_read'
} catch {
  $result.reason_code = 'uia_read_exception'
}
$result | ConvertTo-Json -Compress
"""
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=45,
    )
    if completed.returncode != 0:
        return {"ok": False, "reason_code": "uia_read_powershell_failed"}
    try:
        parsed = json.loads((completed.stdout or "").strip() or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "reason_code": "uia_read_json_invalid"}
    return parsed if isinstance(parsed, dict) else {"ok": False, "reason_code": "uia_read_json_invalid"}


def _classify_probe(
    *,
    focus: dict[str, Any],
    uia_before: dict[str, Any],
    send: dict[str, Any],
    uia_after: dict[str, Any],
) -> tuple[ProbeOutcome, str]:
    # Structural UIA surface is decisive when inspection of the Zed HWND succeeded.
    if uia_before.get("ok"):
        editable = int(uia_before.get("editable_count") or 0) + int(
            uia_before.get("document_count") or 0
        )
        value_patterns = int(uia_before.get("value_pattern_count") or 0)
        text_patterns = int(uia_before.get("text_pattern_count") or 0)
        if editable == 0 and value_patterns == 0 and text_patterns == 0:
            return "unsupported", "uia_no_editable_control"
    if not focus.get("focused"):
        return "indeterminate", "focus_not_acquired"
    if not uia_before.get("ok"):
        return "indeterminate", str(uia_before.get("reason_code") or "uia_unavailable")
    if not send.get("ok"):
        return "unsupported", "sendinput_failed"
    if uia_after.get("ok") and uia_after.get("contains_marker") is True:
        return "supported", "sendinput_observed_via_uia_value"
    if uia_before.get("focused_has_value_pattern") or uia_before.get("focused_has_text_pattern"):
        return "unsupported", "sendinput_no_observable_uia_effect"
    return "unsupported", "uia_patterns_absent_for_verification"


def _write_evidence(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(encoded, encoding="utf-8")
    return _sha256_text(encoded)


def test_zed_uia_sendinput_investigation(tmp_path: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("requires_windows_desktop")

    started = datetime.now(tz=UTC).isoformat()
    exe = _zed_executable()
    version = _require_zed_version(exe)
    probe_file = (tmp_path / "zed-uia-probe.txt").resolve()
    probe_file.write_text("optimus-uia-sendinput-probe\n", encoding="utf-8")

    try:
        pid, observed = _ensure_zed_running(exe, probe_file)
    except HostError as exc:
        evidence = {
            "schema": "evidence-investigation-uia-sendinput-v1",
            "complete": True,
            "result": "indeterminate",
            "reason_code": exc.code,
            "started_at": started,
            "ended_at": datetime.now(tz=UTC).isoformat(),
            "zed_version": version,
        }
        digest = _write_evidence(EVIDENCE_DIR / "uia-sendinput-result.json", evidence)
        print(json.dumps({"result": "indeterminate", "reason_code": exc.code, "digest": digest}, sort_keys=True))
        assert evidence["result"] == "indeterminate"
        return

    hwnds = _enum_top_level_hwnds_for_pid(pid)
    if not hwnds:
        evidence = {
            "schema": "evidence-investigation-uia-sendinput-v1",
            "complete": True,
            "result": "indeterminate",
            "reason_code": "zed_window_not_found",
            "started_at": started,
            "ended_at": datetime.now(tz=UTC).isoformat(),
            "zed_version": version,
            "pid": pid,
            "observed_pids": list(observed),
        }
        digest = _write_evidence(EVIDENCE_DIR / "uia-sendinput-result.json", evidence)
        print(json.dumps({"result": "indeterminate", "reason_code": "zed_window_not_found", "digest": digest}, sort_keys=True))
        assert evidence["result"] == "indeterminate"
        return

    # Prefer the largest-titled visible window for the editor surface.
    hwnd = max(hwnds, key=lambda handle: (len(_window_title(handle)), handle))
    title = _window_title(hwnd)
    canary = f"OPTIMUSUIA{uuid.uuid4().hex[:8]}"
    focus = _focus_hwnd(hwnd)
    uia_before = _uia_probe_powershell(hwnd, canary)
    send = _sendinput_unicode(canary)
    time.sleep(0.5)
    uia_after = _uia_read_focused_value()
    outcome, reason = _classify_probe(
        focus=focus,
        uia_before=uia_before,
        send=send,
        uia_after=uia_after,
    )
    ended = datetime.now(tz=UTC).isoformat()
    evidence = {
        "schema": "evidence-investigation-uia-sendinput-v1",
        "complete": True,
        "result": outcome,
        "reason_code": reason,
        "started_at": started,
        "ended_at": ended,
        "zed_version": version,
        "pid": pid,
        "observed_pids": list(observed),
        "hwnd": hwnd,
        "window_title_sha256": _sha256_text(title),
        "window_title_len": len(title),
        "focus": focus,
        "uia_before": uia_before,
        "sendinput": send,
        "uia_after": uia_after,
        "cleanup": {
            "note": "left Zed running; probe file may remain open in editor",
            "probe_file_sha256": _sha256_text(probe_file.read_text(encoding="utf-8")),
        },
    }
    body = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    digest = _sha256_text(body)
    evidence["evidence_sha256"] = digest
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "uia-sendinput-result.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "result": outcome,
                "reason_code": reason,
                "pid": pid,
                "hwnd": hwnd,
                "evidence_sha256": digest,
                "editable_count": uia_before.get("editable_count"),
                "document_count": uia_before.get("document_count"),
                "sendinput_ok": send.get("ok"),
            },
            sort_keys=True,
        )
    )
    assert outcome in {"supported", "unsupported", "indeterminate"}
    assert reason
