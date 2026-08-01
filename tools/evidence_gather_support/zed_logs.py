"""Pre-run Zed-log snapshot, bounded watch, and process/file correlation."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from evidence_handoff.collector.models import CapturedArtifact, CollectionBatch, Observation

from .common import HostError

SUPPORTED_CLIENT_IDENTITY = "zed-1.13.1"
SUPPORTED_VERSION_TOKEN = "1.13.1"
COLLECTOR_ID = "zed_crash_collector"
_MINIDUMP_MAGIC = b"MDMP"
_VERSION_TOKEN_RE = re.compile(r"\b(\d+\.\d+\.\d+)\b")


@dataclass(frozen=True, slots=True)
class ZedFileRecord:
    name: str
    size_bytes: int
    mtime_ns: int
    file_id: tuple[int, int]


@dataclass(frozen=True, slots=True)
class ZedLogSnapshot:
    root: Path
    records: tuple[ZedFileRecord, ...]
    monotonic_ns: int
    wall_clock: str


def require_supported_client_identity(identity: str, *, reported_version: str) -> None:
    if identity != SUPPORTED_CLIENT_IDENTITY:
        raise HostError("zed_version_mismatch")
    match = _VERSION_TOKEN_RE.search(reported_version)
    if match is None or match.group(1) != SUPPORTED_VERSION_TOKEN:
        raise HostError("zed_version_mismatch")


def require_zed_log_root(path: Path, *, expected_live_root: Path | None = None) -> Path:
    absolute = path if path.is_absolute() else path.resolve()
    if not absolute.is_absolute():
        raise HostError("relative_path_rejected")
    resolved = absolute.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise HostError("zed_log_root_missing")
    if expected_live_root is not None:
        expected = expected_live_root.resolve()
        if resolved != expected:
            raise HostError("zed_log_root_mismatch")
    return resolved


def default_live_zed_log_root() -> Path:
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        raise HostError("zed_log_root_missing")
    return (Path(local) / "Zed" / "logs").resolve()


def file_record_for(path: Path) -> ZedFileRecord:
    absolute = path.resolve()
    if not absolute.is_file():
        raise HostError("zed_log_root_missing")
    stat = absolute.stat()
    return ZedFileRecord(
        name=absolute.name,
        size_bytes=stat.st_size,
        mtime_ns=getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
        file_id=(stat.st_dev, getattr(stat, "st_ino", 0)),
    )


def snapshot_log_root(
    root: Path,
    *,
    monotonic_ns: int | None = None,
    wall_clock: str | None = None,
) -> ZedLogSnapshot:
    resolved = require_zed_log_root(root)
    records: list[ZedFileRecord] = []
    for child in sorted(resolved.iterdir(), key=lambda item: item.name):
        if child.is_file():
            records.append(file_record_for(child))
    return ZedLogSnapshot(
        root=resolved,
        records=tuple(records),
        monotonic_ns=time.monotonic_ns() if monotonic_ns is None else monotonic_ns,
        wall_clock=wall_clock or "1970-01-01T00:00:00Z",
    )


def list_new_or_changed(snapshot: ZedLogSnapshot, root: Path) -> tuple[ZedFileRecord, ...]:
    resolved = require_zed_log_root(root)
    if resolved != snapshot.root:
        raise HostError("zed_log_root_mismatch")
    prior = {record.name: record for record in snapshot.records}
    found: list[ZedFileRecord] = []
    for child in sorted(resolved.iterdir(), key=lambda item: item.name):
        if not child.is_file():
            continue
        current = file_record_for(child)
        previous = prior.get(current.name)
        if previous is None or previous != current:
            found.append(current)
    return tuple(found)


def classify_artifact_role(name: str, header: bytes) -> str:
    lower = name.lower()
    if lower.endswith(".dmp") or header.startswith(_MINIDUMP_MAGIC):
        return "zed_process_dump"
    if lower.endswith(".json"):
        return "zed_panic_json"
    if lower.endswith(".log") or lower.endswith(".log.old"):
        return "zed_log"
    return "zed_unknown"


def digest_stable(path: Path, *, expected: ZedFileRecord) -> str:
    absolute = path.resolve()
    before = file_record_for(absolute)
    if before != expected:
        raise HostError("zed_hash_raced")
    digest = hashlib.sha256(absolute.read_bytes()).hexdigest()
    after = file_record_for(absolute)
    if after != expected:
        raise HostError("zed_hash_raced")
    return digest


def discover_zed_editor_pids() -> tuple[int, ...]:
    """Independently enumerate running Zed editor PIDs (excludes crash-handler helpers)."""
    if sys.platform != "win32":
        raise HostError("zed_process_lookup_failed")
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
    if completed.returncode != 0:
        raise HostError("zed_process_lookup_failed")
    editors: list[int] = []
    for line in (completed.stdout or "").splitlines():
        parts = line.split("\t", 1)
        if not parts or not parts[0].strip().isdigit():
            continue
        command = parts[1] if len(parts) > 1 else ""
        if "--crash-handler" in command.lower():
            continue
        editors.append(int(parts[0].strip()))
    return tuple(sorted(set(editors)))


def correlate_zed_processes(
    *,
    expected_pids: Sequence[int],
    observed_pids: Sequence[int],
) -> None:
    expected = tuple(int(pid) for pid in expected_pids)
    observed = tuple(int(pid) for pid in observed_pids)
    if not observed:
        raise HostError("zed_process_lookup_failed")
    if not expected:
        if len(set(observed)) > 1:
            raise HostError("zed_multi_instance_ambiguous")
        return
    expected_set = set(expected)
    observed_set = set(observed)
    if expected_set.isdisjoint(observed_set):
        raise HostError("zed_unrelated_process")
    # Expected present but any additional unrelated editor process is ambiguous.
    if observed_set - expected_set:
        raise HostError("zed_multi_instance_ambiguous")
    # Observed must cover every expected PID (no silent partial match).
    if expected_set - observed_set:
        raise HostError("zed_unrelated_process")


def process_correlation_fields(
    *,
    expected_pids: Sequence[int],
    observed_pids: Sequence[int],
) -> tuple[tuple[str, str], ...]:
    correlate_zed_processes(expected_pids=expected_pids, observed_pids=observed_pids)
    fields: list[tuple[str, str]] = []
    for pid in expected_pids:
        fields.append(("pid", str(int(pid))))
    for pid in observed_pids:
        fields.append(("observed_pid", str(int(pid))))
    return tuple(fields)


def require_ordered_watch_window(
    *,
    watch_started_ns: int,
    watch_ended_ns: int,
    wall_started: str,
    wall_ended: str,
) -> None:
    if watch_ended_ns < watch_started_ns:
        raise HostError("zed_clock_ambiguous")
    if wall_ended < wall_started:
        raise HostError("zed_clock_ambiguous")


def watch_log_root(
    snapshot: ZedLogSnapshot,
    *,
    watch_seconds: float,
    poll_interval_seconds: float = 0.05,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> tuple[ZedFileRecord, ...]:
    if watch_seconds < 0:
        raise HostError("zed_watch_timeout")
    started = monotonic()
    deadline = started + watch_seconds
    while True:
        candidates = list_new_or_changed(snapshot, snapshot.root)
        if candidates:
            return candidates
        now = monotonic()
        if now >= deadline:
            raise HostError("zed_watch_timeout")
        remaining = deadline - now
        sleep(min(poll_interval_seconds, max(remaining, 0.0)))


def build_collection_batch(
    *,
    scenario_id: str,
    run_id: str,
    monotonic_origin_ns: int,
    snapshot: ZedLogSnapshot,
    candidates: Sequence[ZedFileRecord],
    digests: Mapping[str, str],
    process_pids: Sequence[int],
    watch_started_ns: int,
    watch_ended_ns: int,
    wall_started: str,
    wall_ended: str,
    artifact_relative_prefix: str = "artifacts/zed",
) -> CollectionBatch:
    require_ordered_watch_window(
        watch_started_ns=watch_started_ns,
        watch_ended_ns=watch_ended_ns,
        wall_started=wall_started,
        wall_ended=wall_ended,
    )
    observations: list[Observation] = []
    artifacts: list[CapturedArtifact] = []
    base_corr = (
        ("log_root", str(snapshot.root)),
        ("watch_started_ns", str(watch_started_ns)),
        ("watch_ended_ns", str(watch_ended_ns)),
        ("wall_started", wall_started),
        ("wall_ended", wall_ended),
        ("pre_run_count", str(len(snapshot.records))),
    )
    pid_corr = tuple(("pid", str(int(pid))) for pid in process_pids)
    for index, candidate in enumerate(candidates):
        path = snapshot.root / candidate.name
        header = path.read_bytes()[:4] if path.is_file() else b""
        role = classify_artifact_role(candidate.name, header)
        digest = digests[candidate.name]
        relative = f"{artifact_relative_prefix}/{candidate.name}"
        artifacts.append(
            CapturedArtifact(
                role=role,
                media_type=_media_type_for(role),
                relative_locator=relative,
                sha256=digest,
                size_bytes=candidate.size_bytes,
            )
        )
        observations.append(
            Observation(
                schema="evidence-observation-v1",
                scenario_id=scenario_id,
                run_id=run_id,
                collector_id=COLLECTOR_ID,
                sequence=index,
                monotonic_offset_ns=max(watch_ended_ns - monotonic_origin_ns, 0),
                observed_at=wall_ended,
                observation_kind="zed_log_candidate",
                correlation=base_corr
                + pid_corr
                + (
                    ("file_name", candidate.name),
                    ("file_size_bytes", str(candidate.size_bytes)),
                    ("file_mtime_ns", str(candidate.mtime_ns)),
                    ("file_id", f"{candidate.file_id[0]}:{candidate.file_id[1]}"),
                ),
                artifact_role=role,
                artifact_sha256=digest,
                reason_code=None,
            )
        )
    return CollectionBatch(
        collector_id=COLLECTOR_ID,
        contract_version="v1",
        observations=tuple(observations),
        artifacts=tuple(artifacts),
    )


def _media_type_for(role: str) -> str:
    if role == "zed_process_dump":
        return "application/octet-stream"
    if role == "zed_panic_json":
        return "application/json"
    if role == "zed_log":
        return "text/plain"
    return "application/octet-stream"
