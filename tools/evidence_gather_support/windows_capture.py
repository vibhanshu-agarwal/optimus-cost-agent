"""Windows DWM physical-bounds capture for evidence collection.

Resolves a unique top-level visible window for an expected PID, reads
``DWMWA_EXTENDED_FRAME_BOUNDS``, captures only that physical rectangle, and
revalidates process identity. A successful capture is evidence transport only —
never a semantic render claim.
"""

from __future__ import annotations

import ctypes
import hashlib
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from io import BytesIO

from evidence_handoff.collector.models import CapturedArtifact, CollectionBatch, Observation

from .common import HostError

COLLECTOR_ID = "dwm_capture_collector"
_DWMWA_EXTENDED_FRAME_BOUNDS = 9


@dataclass(frozen=True, slots=True)
class PhysicalBounds:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True, slots=True)
class DpiContext:
    dpi_x: int
    dpi_y: int
    awareness: str


@dataclass(frozen=True, slots=True)
class WindowCandidate:
    hwnd: int
    pid: int
    title: str
    visible: bool


@dataclass(frozen=True, slots=True)
class CaptureResult:
    hwnd: int
    pid: int
    bounds: PhysicalBounds
    dpi: DpiContext
    png_bytes: bytes
    sha256: str
    width: int
    height: int
    captured_at: str
    monotonic_ns: int


def _require_windows() -> None:
    if sys.platform != "win32":
        raise HostError("dwm_api_failure")


def validate_physical_bounds(bounds: PhysicalBounds) -> None:
    if bounds.width <= 0 or bounds.height <= 0:
        raise HostError("dwm_invalid_bounds")


def window_pid(hwnd: int) -> int:
    _require_windows()
    pid = wintypes.DWORD(0)
    ctypes.windll.user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    value = int(pid.value)
    if value <= 0:
        raise HostError("dwm_api_failure")
    return value


def enumerate_top_level_windows() -> tuple[WindowCandidate, ...]:
    _require_windows()
    user32 = ctypes.windll.user32
    found: list[WindowCandidate] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindow(hwnd):
            return True
        visible = bool(user32.IsWindowVisible(hwnd))
        if user32.GetWindow(hwnd, 4):  # GW_OWNER
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        try:
            pid = window_pid(int(hwnd))
        except HostError:
            return True
        found.append(
            WindowCandidate(
                hwnd=int(hwnd),
                pid=pid,
                title=buf.value,
                visible=visible,
            )
        )
        return True

    if not user32.EnumWindows(_enum, 0):
        raise HostError("dwm_api_failure")
    return tuple(found)


def resolve_unique_visible_window(*, expected_pid: int) -> WindowCandidate:
    expected = int(expected_pid)
    candidates = [
        item
        for item in enumerate_top_level_windows()
        if item.visible and item.pid == expected
    ]
    if not candidates:
        # Distinguish "no windows at all for PID" from "windows exist for other PIDs".
        others = [item for item in enumerate_top_level_windows() if item.visible]
        if others:
            raise HostError("dwm_pid_mismatch")
        raise HostError("dwm_window_not_found")
    if len(candidates) > 1:
        raise HostError("dwm_window_ambiguous")
    chosen = candidates[0]
    # Independent revalidation — never trust the enumerate filter alone.
    if window_pid(chosen.hwnd) != expected:
        raise HostError("dwm_pid_mismatch")
    return chosen


def query_dwm_extended_frame_bounds(hwnd: int) -> PhysicalBounds:
    _require_windows()
    rect = wintypes.RECT()
    status = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        _DWMWA_EXTENDED_FRAME_BOUNDS,
        ctypes.byref(rect),
        ctypes.sizeof(rect),
    )
    if status != 0:
        raise HostError("dwm_api_failure")
    bounds = PhysicalBounds(
        left=int(rect.left),
        top=int(rect.top),
        right=int(rect.right),
        bottom=int(rect.bottom),
    )
    validate_physical_bounds(bounds)
    return bounds


def get_physical_bounds(hwnd: int) -> PhysicalBounds:
    return query_dwm_extended_frame_bounds(hwnd)


def query_dpi_context(hwnd: int) -> DpiContext:
    _require_windows()
    dpi = ctypes.windll.user32.GetDpiForWindow(wintypes.HWND(hwnd))
    if dpi <= 0:
        raise HostError("dwm_api_failure")
    awareness = "unknown"
    try:
        value = ctypes.windll.user32.GetWindowDpiAwarenessContext(wintypes.HWND(hwnd))
        # DPI_AWARENESS_CONTEXT handles are opaque; record a stable label only.
        awareness = f"context_{int(value)}"
    except Exception:
        awareness = "unavailable"
    return DpiContext(dpi_x=int(dpi), dpi_y=int(dpi), awareness=awareness)


def get_dpi_context(hwnd: int) -> DpiContext:
    return query_dpi_context(hwnd)


def bitblt_region_png(region: PhysicalBounds) -> bytes:
    """Capture the physical screen rectangle as a PNG."""
    _require_windows()
    validate_physical_bounds(region)
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    width = region.width
    height = region.height
    hdc_screen = user32.GetDC(0)
    if not hdc_screen:
        raise HostError("dwm_api_failure")
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
    if not hdc_mem or not hbmp:
        if hdc_mem:
            gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)
        raise HostError("dwm_api_failure")
    old = gdi32.SelectObject(hdc_mem, hbmp)
    ok = gdi32.BitBlt(
        hdc_mem,
        0,
        0,
        width,
        height,
        hdc_screen,
        region.left,
        region.top,
        0x00CC0020,  # SRCCOPY
    )
    gdi32.SelectObject(hdc_mem, old)
    if not ok:
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)
        raise HostError("dwm_api_failure")

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height  # top-down
    header.biPlanes = 1
    header.biBitCount = 32
    header.biCompression = 0
    buffer = (ctypes.c_ubyte * (width * height * 4))()
    got = gdi32.GetDIBits(hdc_mem, hbmp, 0, height, buffer, ctypes.byref(header), 0)
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)
    if got != height:
        raise HostError("dwm_api_failure")

    from PIL import Image

    image = Image.frombuffer("RGBA", (width, height), bytes(buffer), "raw", "BGRA", 0, 1)
    rgb = image.convert("RGB")
    out = BytesIO()
    rgb.save(out, format="PNG", optimize=True)
    return out.getvalue()


def capture_window(
    *,
    hwnd: int,
    expected_pid: int,
    captured_at: str | None = None,
    monotonic_ns: int | None = None,
) -> CaptureResult:
    observed_pid = window_pid(hwnd)
    if observed_pid != int(expected_pid):
        raise HostError("dwm_pid_mismatch")
    before = query_dwm_extended_frame_bounds(hwnd)
    dpi = query_dpi_context(hwnd)
    png = bitblt_region_png(before)
    after = query_dwm_extended_frame_bounds(hwnd)
    if after != before:
        raise HostError("dwm_bounds_changed")
    # Re-check PID after capture — refuse echoed/spoofed identity.
    if window_pid(hwnd) != int(expected_pid):
        raise HostError("dwm_pid_mismatch")
    digest = hashlib.sha256(png).hexdigest()
    return CaptureResult(
        hwnd=int(hwnd),
        pid=int(expected_pid),
        bounds=before,
        dpi=dpi,
        png_bytes=png,
        sha256=digest,
        width=before.width,
        height=before.height,
        captured_at=captured_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        monotonic_ns=time.monotonic_ns() if monotonic_ns is None else monotonic_ns,
    )


def build_collection_batch(
    *,
    scenario_id: str,
    run_id: str,
    monotonic_origin_ns: int,
    capture: CaptureResult,
    artifact_relative: str = "artifacts/dwm/screenshot.png",
) -> CollectionBatch:
    observation = Observation(
        schema="evidence-observation-v1",
        scenario_id=scenario_id,
        run_id=run_id,
        collector_id=COLLECTOR_ID,
        sequence=0,
        monotonic_offset_ns=max(capture.monotonic_ns - monotonic_origin_ns, 0),
        observed_at=capture.captured_at,
        observation_kind="screenshot_capture",
        correlation=(
            ("hwnd", hex(capture.hwnd)),
            ("pid", str(capture.pid)),
            ("left", str(capture.bounds.left)),
            ("top", str(capture.bounds.top)),
            ("right", str(capture.bounds.right)),
            ("bottom", str(capture.bounds.bottom)),
            ("dpi_x", str(capture.dpi.dpi_x)),
            ("dpi_y", str(capture.dpi.dpi_y)),
            ("dpi_awareness", capture.dpi.awareness),
            ("width", str(capture.width)),
            ("height", str(capture.height)),
        ),
        artifact_role="screenshot",
        artifact_sha256=capture.sha256,
        reason_code=None,
    )
    artifact = CapturedArtifact(
        role="screenshot",
        media_type="image/png",
        relative_locator=artifact_relative,
        sha256=capture.sha256,
        size_bytes=len(capture.png_bytes),
    )
    return CollectionBatch(
        collector_id=COLLECTOR_ID,
        contract_version="v1",
        observations=(observation,),
        artifacts=(artifact,),
    )
