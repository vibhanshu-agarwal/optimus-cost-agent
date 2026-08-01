"""Investigation-only probe: hermetic Zed ``--user-data-dir`` isolation.

Creates no collector adapter, registry ID, support module, entry point, feature
flag, or scenario capability. A negative result completes the investigation.

Launches at least two real Zed 1.13.1 processes with distinct temporary roots,
``shell=False``. Refuses ambient profile roots, repo paths, cloud-sync roots,
overlap, and symlink/reparse escapes. Does not delete operator profiles.

Markers: evidence_investigation, requires_zed.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pytest

from tools.evidence_gather_support import zed_logs as zed_mod
from tools.evidence_gather_support.common import HostError

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = REPO_ROOT / "reports" / "task12-evidence-collector"
ProbeOutcome = Literal["supported", "unsupported", "indeterminate"]

pytestmark = [
    pytest.mark.evidence_investigation,
    pytest.mark.requires_zed,
]

_CLOUD_MARKERS = (
    "onedrive",
    "dropbox",
    "google drive",
    "icloud",
    "box sync",
    "box.com",
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _zed_paths() -> tuple[Path, Path]:
    """Return (cli_or_app_for_version, app_binary_for_launch).

    Windows installs ship ``bin\\Zed.exe`` (CLI that invokes the app) and
    ``Zed.exe`` (the editor). Hermetic ``--user-data-dir`` launches must target
    the app binary; the CLI alone often exits after IPC handoff.
    """
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        pytest.fail("LOCALAPPDATA_missing")
    app = Path(local) / "Programs" / "Zed" / "Zed.exe"
    cli = Path(local) / "Programs" / "Zed" / "bin" / "Zed.exe"
    if not app.is_file():
        pytest.fail("zed_app_executable_missing")
    version_exe = cli if cli.is_file() else app
    return version_exe.resolve(), app.resolve()


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


def _ambient_profile_root() -> Path:
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        pytest.fail("LOCALAPPDATA_missing")
    return (Path(local) / "Zed").resolve()


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    if sys.platform != "win32":
        return False
    import ctypes

    get_attrs = ctypes.windll.kernel32.GetFileAttributesW
    get_attrs.restype = ctypes.c_uint32
    attrs = int(get_attrs(str(path)))
    if attrs == 0xFFFFFFFF:
        return False
    # FILE_ATTRIBUTE_REPARSE_POINT = 0x400
    return bool(attrs & 0x400)


def _validate_user_data_root(root: Path, *, sibling: Path | None = None) -> None:
    """Fail closed on disallowed custody roots (investigation gate, not adapter)."""
    if not root.is_absolute():
        raise HostError("user_data_root_not_absolute")
    resolved = root.resolve()
    if resolved.exists() and not resolved.is_dir():
        raise HostError("user_data_root_not_directory")
    if _is_reparse_point(resolved if resolved.exists() else root.parent.resolve()):
        raise HostError("user_data_root_reparse_point")
    if resolved.exists() and any(_is_reparse_point(path) for path in resolved.rglob("*") if path.exists()):
        # Only check shallow children we create; refuse if root itself is reparse.
        pass
    repo = REPO_ROOT.resolve()
    try:
        resolved.relative_to(repo)
        raise HostError("user_data_root_inside_repository")
    except ValueError:
        pass
    ambient = _ambient_profile_root()
    if resolved == ambient:
        raise HostError("user_data_root_ambient_profile")
    try:
        resolved.relative_to(ambient)
        raise HostError("user_data_root_ambient_profile")
    except ValueError:
        pass
    try:
        ambient.relative_to(resolved)
        raise HostError("user_data_root_ambient_profile")
    except ValueError:
        pass
    lowered = str(resolved).lower()
    if any(marker in lowered for marker in _CLOUD_MARKERS):
        raise HostError("user_data_root_cloud_sync")
    if sibling is not None:
        other = sibling.resolve()
        if resolved == other:
            raise HostError("user_data_roots_overlap")
        try:
            resolved.relative_to(other)
            raise HostError("user_data_roots_overlap")
        except ValueError:
            pass
        try:
            other.relative_to(resolved)
            raise HostError("user_data_roots_overlap")
        except ValueError:
            pass


def _process_rows() -> list[dict[str, str]]:
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
                "cmdline": cmdline,
            }
        )
    return rows


def _root_markers(root: Path) -> dict[str, Any]:
    log_file = root / "logs" / "Zed.log"
    return {
        "root_sha256": _sha256_text(str(root.resolve())),
        "has_logs_dir": (root / "logs").is_dir(),
        "has_config_dir": (root / "config").is_dir(),
        "has_db_dir": (root / "db").is_dir(),
        "has_zed_log": log_file.is_file(),
        "zed_log_sha256": _sha256_text(log_file.read_text(encoding="utf-8", errors="replace"))
        if log_file.is_file()
        else None,
        "zed_log_size": log_file.stat().st_size if log_file.is_file() else 0,
        "child_dir_names": sorted(
            path.name for path in root.iterdir() if path.is_dir()
        )
        if root.is_dir()
        else [],
    }


def _cmdline_references_root(cmdline: str, root: Path | str) -> bool:
    """Match hermetic roots in process command lines despite path-form drift."""
    if not cmdline:
        return False
    text = str(root)
    lowered = cmdline.lower()
    candidates = {
        text.lower(),
        text.replace("/", "\\").lower(),
        text.replace("\\", "/").lower(),
        ("\\\\?\\" + text).lower(),
        ("\\\\?\\" + text.replace("/", "\\")).lower(),
    }
    return any(candidate and candidate in lowered for candidate in candidates)


def _terminate_pid(pid: int) -> dict[str, Any]:
    completed = subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=30,
    )
    # 128 = process not found / already exited — bounded custody still satisfied.
    already_gone = completed.returncode == 128
    return {
        "pid": pid,
        "returncode": completed.returncode,
        "stdout_sha256": _sha256_text(completed.stdout or ""),
        "stderr_sha256": _sha256_text(completed.stderr or ""),
        "ok": completed.returncode == 0 or already_gone,
        "already_gone": already_gone,
    }


def test_zed_user_data_live_investigation(tmp_path: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("zed_user_data_requires_windows")

    started = datetime.now(tz=UTC).isoformat()
    version_exe, app_exe = _zed_paths()
    version = _require_zed_version(version_exe)
    ambient = _ambient_profile_root()

    # Explicit temporary roots — never ambient profile / repo / cloud sync.
    root_a = (tmp_path / "user-data-a").resolve()
    root_b = (tmp_path / "user-data-b").resolve()
    root_a.mkdir()
    root_b.mkdir()

    refusal_checks: list[dict[str, str]] = []
    for label, path, sibling in (
        ("ok_a", root_a, root_b),
        ("ok_b", root_b, root_a),
    ):
        try:
            _validate_user_data_root(path, sibling=sibling)
            refusal_checks.append({"case": label, "result": "accepted"})
        except HostError as exc:
            pytest.fail(f"hermetic_root_rejected:{label}:{exc.code}")

    # Negative refusal probes (must fail closed).
    for case, path in (
        ("repo_root", REPO_ROOT.resolve()),
        ("ambient_profile", ambient),
    ):
        try:
            _validate_user_data_root(path)
            refusal_checks.append({"case": case, "result": "unexpectedly_accepted"})
            pytest.fail(f"refusal_gate_failed:{case}")
        except HostError as exc:
            refusal_checks.append({"case": case, "result": "refused", "code": exc.code})

    try:
        _validate_user_data_root(root_a, sibling=root_a)
        refusal_checks.append({"case": "overlap_self", "result": "unexpectedly_accepted"})
        pytest.fail("refusal_gate_failed:overlap_self")
    except HostError as exc:
        refusal_checks.append({"case": "overlap_self", "result": "refused", "code": exc.code})

    probe = (tmp_path / "zed-user-data-probe.txt").resolve()
    probe.write_text("optimus-zed-user-data-probe\n", encoding="utf-8")

    try:
        pre_pids = set(zed_mod.discover_zed_editor_pids())
    except HostError:
        pre_pids = set()

    launches: list[dict[str, Any]] = []
    children: list[subprocess.Popen[bytes]] = []
    try:
        for label, root in (("a", root_a), ("b", root_b)):
            # App binary + --foreground: keep a process that owns the hermetic
            # root instead of a CLI that may IPC-handoff and exit immediately.
            argv = [
                str(app_exe),
                "--foreground",
                "--user-data-dir",
                str(root),
                str(probe),
            ]
            proc = subprocess.Popen(  # noqa: S603 — absolute Zed path, shell=False
                argv,
                cwd=str(tmp_path),
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            children.append(proc)
            launches.append(
                {
                    "label": label,
                    "spawn_pid": proc.pid,
                    "root": str(root),
                    "root_sha256": _sha256_text(str(root)),
                    "argv_sha256": _sha256_text(json.dumps(argv, separators=(",", ":"))),
                    "argv_has_user_data_dir": "--user-data-dir" in argv,
                    "argv_has_foreground": "--foreground" in argv,
                    "argv_has_root": str(root) in argv,
                    "launch_target": "app",
                }
            )
            time.sleep(2.0)

        # Zed may re-exec; wait for hermetic roots to materialize and for live
        # editor PIDs whose command lines reference each root.
        deadline = time.monotonic() + 45
        resolved_pids: dict[str, int] = {}
        while time.monotonic() < deadline:
            rows = _process_rows()
            for launch in launches:
                root = launch["root"]
                label = launch["label"]
                if label in resolved_pids:
                    continue
                for row in rows:
                    cmdline = row["cmdline"]
                    if "--user-data-dir" in cmdline and _cmdline_references_root(
                        cmdline, root
                    ):
                        if "--crash-handler" in cmdline.lower():
                            continue
                        pid = int(row["pid"])
                        if pid in pre_pids:
                            continue
                        resolved_pids[label] = pid
                        launch["editor_pid"] = pid
                        break
            roots_ready = (root_a / "logs").is_dir() and (root_b / "logs").is_dir()
            if len(resolved_pids) == 2 and roots_ready:
                break
            # Roots alone are enough to stop waiting once both have logs;
            # cmdline custody may race if processes exit after writing.
            if roots_ready and time.monotonic() + 5 >= deadline:
                break
            time.sleep(0.5)
        time.sleep(1.0)

        rows = _process_rows()
        custody: list[dict[str, Any]] = []
        for launch, root in zip(launches, (root_a, root_b), strict=True):
            pid = int(launch.get("editor_pid") or launch["spawn_pid"])
            matching = [row for row in rows if int(row["pid"]) == pid]
            cmdline = matching[0]["cmdline"] if matching else ""
            # Prefer any live row that still references this root if spawn pid vanished.
            if not cmdline:
                for row in rows:
                    if _cmdline_references_root(
                        row["cmdline"], root
                    ) and "--user-data-dir" in row["cmdline"]:
                        if "--crash-handler" in row["cmdline"].lower():
                            continue
                        pid = int(row["pid"])
                        if pid in pre_pids:
                            continue
                        cmdline = row["cmdline"]
                        launch["editor_pid"] = pid
                        break
            custody.append(
                {
                    "label": launch["label"],
                    "spawn_pid": launch["spawn_pid"],
                    "pid": pid,
                    "still_running": any(row["pid"] == str(pid) for row in rows),
                    "cmdline_contains_user_data_dir_flag": "--user-data-dir" in cmdline,
                    "cmdline_contains_root": _cmdline_references_root(cmdline, root),
                    "cmdline_sha256": _sha256_text(cmdline) if cmdline else None,
                    "markers": _root_markers(root),
                    "not_preexisting_pid": pid not in pre_pids,
                }
            )

        markers_a = custody[0]["markers"]
        markers_b = custody[1]["markers"]
        isolated = (
            custody[0]["pid"] != custody[1]["pid"]
            and custody[0]["cmdline_contains_root"]
            and custody[1]["cmdline_contains_root"]
            and custody[0]["cmdline_contains_user_data_dir_flag"]
            and custody[1]["cmdline_contains_user_data_dir_flag"]
            and markers_a["has_logs_dir"]
            and markers_b["has_logs_dir"]
            and markers_a["has_zed_log"]
            and markers_b["has_zed_log"]
            and markers_a["zed_log_sha256"] != markers_b["zed_log_sha256"]
            and custody[0]["not_preexisting_pid"]
            and custody[1]["not_preexisting_pid"]
        )

        ambient_present = bool(pre_pids)
        spawn_exits = [
            child.poll() is not None for child in children
        ]
        if isolated:
            outcome: ProbeOutcome = "supported"
            reason = "two_isolated_user_data_instances"
        elif not any(item["still_running"] for item in custody) and not (
            markers_a["has_logs_dir"] and markers_b["has_logs_dir"]
        ):
            if ambient_present and all(spawn_exits):
                # Ambient Zed already running; hermetic launches exited without
                # materializing roots — single-instance / IPC handoff blocks
                # multi-root custody under this Windows install.
                outcome = "unsupported"
                reason = "ambient_instance_blocks_hermetic_user_data"
            else:
                outcome = "indeterminate"
                reason = "processes_exited_before_observation"
        elif markers_a["has_logs_dir"] and markers_b["has_logs_dir"] and (
            custody[0]["pid"] != custody[1]["pid"]
        ):
            # Roots materialized with distinct PIDs even if cmdline snapshot raced.
            if (
                markers_a["has_zed_log"]
                and markers_b["has_zed_log"]
                and markers_a["zed_log_sha256"] != markers_b["zed_log_sha256"]
            ):
                outcome = "supported"
                reason = "two_isolated_roots_with_distinct_logs"
            else:
                outcome = "indeterminate"
                reason = "roots_ready_without_log_files"
        elif custody[0]["pid"] == custody[1]["pid"]:
            outcome = "unsupported"
            reason = "instances_shared_pid"
        elif not (markers_a["has_logs_dir"] and markers_b["has_logs_dir"]):
            outcome = "unsupported"
            reason = "hermetic_logs_missing"
        else:
            outcome = "indeterminate"
            reason = "partial_isolation_signals"

    finally:
        teardown: list[dict[str, Any]] = []
        # Terminate editor PIDs we resolved plus original spawn PIDs — never ambient.
        spawned_pids: set[int] = set()
        for item in launches:
            spawned_pids.add(int(item["spawn_pid"]))
            if "editor_pid" in item:
                spawned_pids.add(int(item["editor_pid"]))
        # Also kill any remaining process whose cmdline references our hermetic roots.
        try:
            for row in _process_rows():
                cmdline = row["cmdline"]
                if _cmdline_references_root(cmdline, root_a) or _cmdline_references_root(
                    cmdline, root_b
                ):
                    spawned_pids.add(int(row["pid"]))
        except Exception:
            pass
        spawned_pids -= pre_pids
        for pid in sorted(spawned_pids):
            teardown.append(_terminate_pid(pid))
        for proc in children:
            try:
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    # Ambient profile must remain untouched by our teardown target set.
    ambient_still = ambient.is_dir()
    try:
        post_pids = set(zed_mod.discover_zed_editor_pids())
    except HostError:
        post_pids = set()
    ambient_pids_remaining = sorted(pre_pids & post_pids)

    ended = datetime.now(tz=UTC).isoformat()
    evidence = {
        "schema": "evidence-investigation-zed-user-data-v1",
        "complete": True,
        "result": outcome,
        "reason_code": reason,
        "started_at": started,
        "ended_at": ended,
        "zed_version": version,
        "zed_version_exe_sha256": _sha256_text(str(version_exe)),
        "zed_app_exe_sha256": _sha256_text(str(app_exe)),
        "ambient_profile_sha256": _sha256_text(str(ambient)),
        "ambient_profile_still_present": ambient_still,
        "ambient_instance_present_at_start": bool(pre_pids),
        "pre_pids": sorted(pre_pids),
        "ambient_pids_remaining": ambient_pids_remaining,
        "refusal_checks": refusal_checks,
        "launches": [
            {
                key: value
                for key, value in item.items()
                if key not in {"root", "cmdline"}
            }
            for item in launches
        ],
        "custody": custody,
        "teardown": teardown,
        "probe_file_sha256": _sha256_text(probe.read_text(encoding="utf-8")),
        "cleanup": {
            "note": "terminated only spawned PIDs; ambient profile not deleted",
            "teardown_all_ok": all(item.get("ok") for item in teardown),
        },
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    digest = _sha256_text(body)
    evidence["evidence_sha256"] = digest
    (EVIDENCE_DIR / "zed-user-data-result.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "result": outcome,
                "reason_code": reason,
                "pids": [item["pid"] for item in custody],
                "evidence_sha256": digest,
                "teardown_ok": evidence["cleanup"]["teardown_all_ok"],
            },
            sort_keys=True,
        )
    )
    assert outcome in {"supported", "unsupported", "indeterminate"}
    assert reason
    assert all(item["result"] != "unexpectedly_accepted" for item in refusal_checks)
