"""Live DWM physical-bounds capture against a real Zed window.

Requires an interactive Windows desktop (``requires_windows_desktop``) and a
real visible Zed 1.13.1 top-level window. Capture proves physical-region
transport only — never a semantic ``render_observed`` claim.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path

import pytest

from tools.evidence_gather_support import windows_capture as dwm_mod
from tools.evidence_gather_support import zed_logs as zed_mod
from tools.evidence_gather_support.common import HostError

REPO_ROOT = Path(__file__).resolve().parents[3]

pytestmark = [pytest.mark.requires_windows_desktop]


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


def _ensure_zed_editor(exe: Path, open_path: Path) -> int:
    override = os.environ.get("OPTIMUS_EVIDENCE_DWM_PID", "").strip()
    try:
        observed = zed_mod.discover_zed_editor_pids()
        if override:
            pid = int(override)
            zed_mod.correlate_zed_processes(expected_pids=(pid,), observed_pids=observed)
            return pid
        if len(observed) == 1:
            return observed[0]
        if len(observed) > 1:
            raise HostError("zed_multi_instance_ambiguous")
    except HostError as exc:
        if exc.code == "zed_multi_instance_ambiguous":
            pytest.fail(exc.code)
        if override:
            pytest.fail(exc.code)

    subprocess.Popen(  # noqa: S603 — absolute Zed path, shell=False
        [str(exe), str(open_path)],
        cwd=str(REPO_ROOT),
        shell=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        observed = zed_mod.discover_zed_editor_pids()
        if override:
            pid = int(override)
            try:
                zed_mod.correlate_zed_processes(expected_pids=(pid,), observed_pids=observed)
                return pid
            except HostError:
                time.sleep(0.5)
                continue
        if len(observed) == 1:
            return observed[0]
        time.sleep(0.5)
    pytest.fail("zed_process_not_started")


def test_live_dwm_physical_bounds_capture_of_zed_window(tmp_path: Path) -> None:
    exe = _zed_executable()
    version = _require_zed_version(exe)
    probe = (tmp_path / "dwm-live-probe.txt").resolve()
    probe.write_text("optimus-evidence-dwm-live-probe\n", encoding="utf-8")
    pid = _ensure_zed_editor(exe, probe)
    # Give the first frame a moment to become visible.
    time.sleep(2.0)

    try:
        window = dwm_mod.resolve_unique_visible_window(expected_pid=pid)
    except HostError as exc:
        pytest.fail(exc.code)

    # Independent PID revalidation before capture (not an echoed constant).
    assert dwm_mod.window_pid(window.hwnd) == pid

    capture = dwm_mod.capture_window(hwnd=window.hwnd, expected_pid=pid)
    batch = dwm_mod.build_collection_batch(
        scenario_id="zed-session",
        run_id="live-dwm-capture",
        monotonic_origin_ns=capture.monotonic_ns,
        capture=capture,
    )

    assert capture.width > 0 and capture.height > 0
    assert capture.sha256 == hashlib.sha256(capture.png_bytes).hexdigest()
    assert capture.png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert batch.collector_id == "dwm_capture_collector"
    assert batch.artifacts[0].role == "screenshot"
    assert all(obs.observation_kind == "screenshot_capture" for obs in batch.observations)
    assert all(obs.observation_kind != "render_observed" for obs in batch.observations)

    evidence = {
        "zed_version": version,
        "pid": pid,
        "hwnd": hex(capture.hwnd),
        "title": window.title,
        "bounds": {
            "left": capture.bounds.left,
            "top": capture.bounds.top,
            "right": capture.bounds.right,
            "bottom": capture.bounds.bottom,
        },
        "dpi": {
            "dpi_x": capture.dpi.dpi_x,
            "dpi_y": capture.dpi.dpi_y,
            "awareness": capture.dpi.awareness,
        },
        "width": capture.width,
        "height": capture.height,
        "sha256": capture.sha256,
        "captured_at": capture.captured_at,
        "observation_kind": batch.observations[0].observation_kind,
        "render_claim_emitted": False,
    }
    print(evidence)

    out = REPO_ROOT / "reports" / "task7-evidence-collector"
    out.mkdir(parents=True, exist_ok=True)
    (out / "screenshot.png").write_bytes(capture.png_bytes)
    (out / "live-dwm-evidence.txt").write_text(repr(evidence) + "\n", encoding="utf-8")
