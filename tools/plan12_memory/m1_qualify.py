"""Plan 12.10 M1 qualification and the second K2: `python -m tools.plan12_memory.m1_scale --phase qualify --config reports/plan12-memory-m1/run-config-qualify.json`.

This repository and the approved large corpus, through the real route on the released Redis, then K2 on those same real records. Measures and
reports against targets.json and never tunes; a failed bound stays in the report. The report is rewritten after each stage, so a stopped run still
shows what it measured. Assembly on the large corpus is labelled calibration here, because its limits are approved from it and qualified on a later
run. No generative or provider call is possible: the Gateway's upstream is an unroutable local address. Records carry counts, timings and hashes.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import secrets
import shutil
import struct
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import psutil
import redis

from context_engine.index_worker import SCHEMA_VERSION, StorageRefusedError
from optimus.acp import local_infra
from optimus.context.memory_session import MemorySession
from optimus.context.memory_workspace import FastembedEmbedder, GatewayIndexStorage, index_scope
from optimus.context.project_registry import ProjectRegistration
from optimus.guardrails.file_policy import FilePolicy
from optimus_gateway import memory_index
from optimus_security import memory_index_contract as mic
from optimus_security.memory_index_config import ACL_NAME, memory_index_root
from tools.plan12_memory import m1_scale as scale
from tools.plan12_memory.m1_evaluate import CachedEmbedder
from tools.plan12_memory.redis_probe import is_oom_refusal

_K2_USER = "k2-admin"
_EVENTS = "oidx:k2:events"
_LEASE_MS = 60000
_RENEW_SECONDS = 20.0
_PROJECTION_WAIT_SECONDS = 10.0
_ANY_REVISION = "0" * 64
# The approved scope leaves test Java out, by the sample's rule, with an ignore file in the corpus (scale.json approved_corpus).
_TEST_RULE = "**/test/\n**/tests/\n**/Test*\n**/*Test.java\n**/*Tests.java\n"
_LARGE_TASKS = (
    "how does the namenode decide where to place a new block",
    "where does the resource manager schedule a container and what happens when a node is lost",
    "explain how a failed block write is recovered in the client pipeline",
    "where are delegation tokens renewed and cancelled",
)
_ONE_FILE = {"complete": True, "files_indexed": 1, "files_total": 1}


def k2_admin_acl(root: Path, password: str) -> None:
    """A second user for this run only: durable-append canaries and forcing rewrites need commands the index's own user never gets. The index
    still runs as its least-privilege user. The configuration's digest follows the changed file, or the real launch path would refuse it."""
    path = root / ACL_NAME
    data = path.read_bytes().rstrip(b"\n") + f"\nuser {_K2_USER} on #{hashlib.sha256(password.encode()).hexdigest()} ~* resetchannels +@all\n".encode()
    path.write_bytes(data)
    config = next(item for item in root.iterdir() if item.is_file() and item.name != ACL_NAME and item.suffix == ".json")
    document = json.loads(config.read_text(encoding="utf-8"))
    document["acl_sha256"] = hashlib.sha256(data).hexdigest()
    config.write_text(json.dumps(document), encoding="utf-8")


def clone_large_corpus(source: Path, target: Path, *, expected_commit: str) -> Path:
    """A real checkout at the approved commit, plus the approved ignore file, so a measurement's edits never touch the source clone."""
    if target.exists():
        shutil.rmtree(scale.long_path(target), onexc=scale._clear_read_only)
    subprocess.run(["git", "-c", "core.longpaths=true", "clone", "-q", "--local", "--no-hardlinks", str(source), str(target)], capture_output=True, check=True)
    head = subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    if not head.startswith(expected_commit):
        raise SystemExit(f"the large corpus is at {head}, not the approved {expected_commit}")
    subprocess.run(["git", "-C", str(target), "config", "core.longpaths", "true"], check=True)
    (target / ".optimusignore").write_text(_TEST_RULE, encoding="utf-8")
    return target


def within(value: float | None, limit: float, *, at_least: bool = False) -> bool | None:
    if value is None:
        return None
    return value >= limit if at_least else value <= limit


def _p95(values: list[float]) -> float | None:
    return scale._percentile(values, 0.95)


def owner_id(name: str) -> str:
    """The route's owner format: lowercase hex."""
    return hashlib.sha256(name.encode()).hexdigest()[:32]


def compare_acknowledged(acknowledged: Mapping[str, str], stored: Mapping[str, str]) -> dict[str, int]:
    """Exactly what was acknowledged, by run-unique ID and payload. Stream length could not show a lost item beside an extra one."""
    missing = sum(key not in stored for key in acknowledged)
    conflicting = sum(key in stored and stored[key] != value for key, value in acknowledged.items())
    return {"acknowledged": len(acknowledged), "missing": missing, "conflicting": conflicting}


def _record(name: str, dimensions: int) -> dict[str, Any]:
    vector = mic.encode_vector(struct.pack(f"<{dimensions}f", *([0.1] * dimensions)))
    return {"id": hashlib.sha256(name.encode()).hexdigest(), "kind": "symbol", "path": f"k2/{name}.py", "path_id": hashlib.sha256(name.encode()).hexdigest(), "file_hash": "0" * 64, "language": "python",
            "symbol": name, "signature": f"def {name}()", "description": "function in a canary file", "terms": name, "vector": vector}


class _Canaries:
    """Four clients, each with its own index line through the real route and its own pinned connection. One canary: a durable append acknowledged by
    WAITAOF, as a memory Gate would, then the record through the route until a query finds it. A prototype append is not the production Gate (M3),
    and its projection, which publishes a generation, is heavier than a Gate's would be."""

    def __init__(self, settings: Any, embedding: str, dimensions: int, connect: Callable[[], redis.Redis]) -> None:
        self._settings, self._embedding, self._dimensions, self._connect = settings, embedding, dimensions, connect
        self._sequence = itertools.count(1)
        self._run = secrets.token_hex(4)
        self._lock = threading.Lock()
        self.acknowledged: dict[str, str] = {}

    def _storage(self, client_number: int, tag: str) -> GatewayIndexStorage:
        registration = ProjectRegistration(f"{tag}-{client_number}", 1, f"git:{tag}-{client_number}", f"{tag}/{client_number}", created=False)
        return GatewayIndexStorage(self._settings, scope=index_scope(registration, branch="k2", embedding=self._embedding, parser_version="k2"))

    def _note_error(self, out: dict[str, Any], stage: str, error: BaseException) -> None:
        name = f"{stage}:{getattr(error, 'code', type(error).__name__)}"
        with self._lock:
            out["errors"][name] = out["errors"].get(name, 0) + 1

    def _project(self, storage: Any, token: int, name: str, acked: float, out: dict[str, Any]) -> None:
        try:
            epoch = storage.call("generation", action="begin", token=token)["epoch"]
            storage.call("batch", token=token, epoch=epoch, records=[_record(name, self._dimensions)])
            storage.call("generation", action="publish", token=token, epoch=epoch, revision=_ANY_REVISION, dirty=False, coverage=_ONE_FILE)
            seen = False
            while time.perf_counter() - acked < _PROJECTION_WAIT_SECONDS and not seen:
                seen = bool(storage.call("query", mode="lexical", terms=[name], k=1)["records"])
            with self._lock:
                if seen:
                    out["projections"].append((time.perf_counter() - acked) * 1000)
                else:
                    out["unprojected"] += 1
        except Exception as error:  # noqa: BLE001 - counted by kind and kept in the report; this is the measure
            with self._lock:
                out["unprojected"] += 1
            self._note_error(out, "project", error)

    def _client(self, client_number: int, rounds: int, pause: float, out: dict[str, Any], tag: str, ready: threading.Barrier | None, go: threading.Barrier | None) -> None:
        owner = owner_id(f"{tag}owner{client_number}")
        token = None
        storage = self._storage(client_number, tag)
        connection = self._connect().client()  # WAITAOF speaks for its own connection, so append and wait must share one
        try:
            storage.call("generation", action="open", embedding=self._embedding, dimensions=self._dimensions, schema_version=SCHEMA_VERSION)
            token = storage.call("lease", action="acquire", owner=owner, ttl_ms=_LEASE_MS, kind="scope")["token"]
            if ready is not None and go is not None:  # ready before any pressure, so the writes under it are what is tested
                ready.wait(120)
                go.wait(120)
            renewed = time.monotonic()
            for _ in range(rounds):
                name = f"canary{self._run}x{next(self._sequence)}"
                payload = hashlib.sha256(name.encode()).hexdigest()
                try:
                    started = time.perf_counter()
                    connection.xadd(_EVENTS, {"id": name, "payload": payload})
                    local, _replicas = connection.execute_command("WAITAOF", 1, 0, 5000)
                    acked = time.perf_counter()
                except redis.RedisError as error:
                    if is_oom_refusal(error):
                        with self._lock:
                            out["refused_oom"] += 1
                        if ready is not None:  # under pressure the route's own write path is the point, whatever the append did
                            self._project(storage, token, name, time.perf_counter(), out)
                    else:
                        self._note_error(out, "append", error)
                    continue
                with self._lock:
                    out["acks"].append((acked - started) * 1000)
                    out["unconfirmed"] += int(local) < 1
                    if int(local) >= 1:
                        self.acknowledged[name] = payload
                if time.monotonic() - renewed > _RENEW_SECONDS:
                    storage.call("lease", action="renew", owner=owner, ttl_ms=_LEASE_MS, kind="scope", token=token)
                    renewed = time.monotonic()
                self._project(storage, token, name, acked, out)
                if pause:
                    time.sleep(pause)
        except Exception as error:  # noqa: BLE001 - a client that never started must show, or four dead clients would read as no errors
            self._note_error(out, "setup", error)
            for barrier in (ready, go):
                if barrier is not None:
                    barrier.abort()
        finally:
            try:
                if token is not None:
                    storage.call("lease", action="release", owner=owner, kind="scope", token=token)
            except Exception as error:  # noqa: BLE001
                self._note_error(out, "release", error)
            connection.close()

    def run(self, *, rounds: int, pause: float, during: Callable[[], Any] | None = None, pressure: Callable[[], None] | None = None, tag: str = "k2") -> dict[str, Any]:
        """`pressure` runs once every client has its line and lease, and before any of them writes."""
        out: dict[str, Any] = {"acks": [], "projections": [], "unconfirmed": 0, "unprojected": 0, "refused_oom": 0, "errors": {}}
        ready = threading.Barrier(5) if pressure is not None else None
        go = threading.Barrier(5) if pressure is not None else None
        threads = [threading.Thread(target=self._client, args=(number, rounds, pause, out, tag, ready, go), daemon=True) for number in range(4)]
        for thread in threads:
            thread.start()
        if ready is not None and go is not None and pressure is not None:
            try:
                ready.wait(120)
                pressure()
                go.wait(120)
            except threading.BrokenBarrierError:
                out["errors"]["setup:not every client got ready"] = 1
                pressure()
        if during is not None:
            during()
        for thread in threads:
            thread.join(1800)
        expected = 4 * rounds
        return {"expected": expected, "acknowledged": len(out["acks"]), "complete": len(out["acks"]) == expected and len(out["projections"]) == expected, "ack_p50_ms": scale._percentile(out["acks"], 0.5), "ack_p95_ms": _p95(out["acks"]),
                "projected": len(out["projections"]), "projection_p50_ms": scale._percentile(out["projections"], 0.5), "projection_p95_ms": _p95(out["projections"]),
                "unconfirmed": out["unconfirmed"], "unprojected": out["unprojected"], "refused_oom": out["refused_oom"], "errors": out["errors"], "unfinished_clients": sum(thread.is_alive() for thread in threads)}

    def survived(self) -> dict[str, int]:
        stored = {fields[b"id"].decode(): fields[b"payload"].decode() for _entry, fields in self._connect().xrange(_EVENTS)}
        return compare_acknowledged(self.acknowledged, stored)


def rewrite_under_writes(admin: Any, canaries: Any, *, rounds: int, poll_seconds: float = 0.05, limit_seconds: float = 900) -> dict[str, Any]:
    """BGREWRITEAOF once every client holds its line and lease, then writes under it. Overlap is counted conservatively (Codex reviews 30 and 31):
    a scheduled rewrite is not a running one; the baseline is taken just after the rewrite is first seen running; and an acknowledgement counts
    only if a later poll, made after the count was read, still saw it running. A rewrite that ends before any write proves nothing and says so."""
    marks: dict[str, Any] = {"seen_running": False, "acknowledged_while_running": 0}

    def start() -> None:
        admin.bgrewriteaof()
        marks["started"] = time.monotonic()

    def watch() -> None:
        baseline: int | None = None
        while time.monotonic() - marks["started"] < limit_seconds:
            count = len(canaries.acknowledged)  # read before the status, so a running answer vouches for every acknowledgement in it
            info = admin.info("persistence")
            if int(info["aof_rewrite_in_progress"]):
                marks["seen_running"] = True
                if baseline is None:
                    baseline = len(canaries.acknowledged)
                else:
                    marks["acknowledged_while_running"] = max(marks["acknowledged_while_running"], count - baseline)
            elif not int(info.get("aof_rewrite_scheduled", 0)):
                marks["ended"], marks["last_status"] = time.monotonic(), info.get("aof_last_bgrewrite_status")
                return
            time.sleep(poll_seconds)

    result = canaries.run(rounds=rounds, pause=0, pressure=start, during=watch)
    ended = marks.get("ended")
    result["rewrite"] = {"seconds": None if ended is None else round(ended - marks["started"], 3), "seen_running": marks["seen_running"], "last_status": marks.get("last_status"),
                         "acknowledged_while_running": marks["acknowledged_while_running"],
                         "overlap_proven": ended is not None and marks["seen_running"] and marks.get("last_status") == "ok" and marks["acknowledged_while_running"] > 0}
    return result


def _wait_flag(admin: redis.Redis, flag: str, seconds: float = 900) -> float | None:
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        if int(admin.info("persistence")[flag]) == 0:
            return round(time.monotonic() - started, 3)
        time.sleep(0.25)
    return None


def _marker_state(container: str, marker: str) -> str:
    result = subprocess.run(["docker", "exec", container, "grep", "-rlF", marker, "/data"], capture_output=True, text=True, check=False)
    if result.returncode == 0 and result.stdout.strip():
        return "present"
    return "absent" if result.returncode == 1 and not result.stderr.strip() else "error"


class _Peaks:
    """Maxima kept across restarts by sampling, per phase, so a restart cannot erase a peak. A sample that failed outside a planned outage makes that phase's bound unknown;
    it never reads as zero, and the surviving samples cannot vouch for what was missed."""

    def __init__(self, container: str, connect: Callable[[], redis.Redis], *, interval: float = 30.0) -> None:
        self._container, self._connect, self._interval = container, connect, interval
        self._stop = threading.Event()
        self.phase = "index"
        self.in_outage = False  # the instance is down on purpose, so a failed sample is no finding
        self.peaks: dict[str, dict[str, Any]] = {}
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _bump(self, name: str, value: float | None) -> None:
        phase = self.peaks.setdefault(self.phase, {"used_memory_mb": None, "disk_mb": None, "container_memory_mb": None, "failed_samples": 0})
        if value is None:
            phase["failed_samples"] += not self.in_outage
        elif phase[name] is None or value > phase[name]:
            phase[name] = round(value, 1)

    def sample(self) -> None:
        try:
            used = int(self._connect().info("memory")["used_memory_peak"]) / 1048576
        except redis.RedisError:
            used = None
        self._bump("used_memory_mb", used)
        disk = subprocess.run(["docker", "exec", self._container, "sh", "-c", "du -sk /data | cut -f1"], capture_output=True, text=True, check=False).stdout.strip()
        self._bump("disk_mb", int(disk) / 1024 if disk.isdigit() else None)
        peak = subprocess.run(["docker", "exec", self._container, "cat", "/sys/fs/cgroup/memory.peak"], capture_output=True, text=True, check=False).stdout.strip()
        self._bump("container_memory_mb", int(peak) / 1048576 if peak.isdigit() else None)

    def bound(self, phase: str, name: str, limit: float) -> bool | None:
        seen = self.peaks.get(phase, {})
        return None if seen.get("failed_samples") else within(seen.get(name), limit)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self.sample()

    def __enter__(self) -> _Peaks:
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        self._thread.join(60)


def _reachable(call: Callable[[], Any], started: float, seconds: float) -> float | None:
    """Seconds from `started`, taken before the lifecycle operation, so the whole outage counts."""
    while time.monotonic() - started < seconds:
        try:
            if call():
                return round(time.monotonic() - started, 3)
        except Exception:  # noqa: BLE001, S110 - measuring when it comes back
            pass
        time.sleep(0.2)
    return None


def _noeviction(admin: redis.Redis, canaries: _Canaries, query: Callable[[], Any], memory: Any) -> dict[str, Any]:
    """Held over the ceiling, so every write meets it: real OOM refusals on appends and on the route's writes from clients that were ready before it,
    nothing evicted, and existing evidence still readable while full. Then room again, on those same lines' neighbours."""
    before_keys = int(admin.dbsize())
    result: dict[str, Any] = {}

    def press() -> None:
        admin.config_set("maxmemory", max(int(admin.info("memory")["used_memory"]) - 1024 * 1024, 1024 * 1024))

    try:
        result["route_while_full"] = canaries.run(rounds=3, pause=0, pressure=press, tag="full")
        appends_refused = 0
        for number in range(12):
            try:
                admin.xadd("oidx:k2:refused", {"id": number})
            except redis.RedisError as error:
                appends_refused += is_oom_refusal(error)
        result["appends_refused_while_full"] = {"tried": 12, "refused_by_the_ceiling": appends_refused}
        try:
            result["readable_while_full"] = bool(query())
        except Exception as error:  # noqa: BLE001 - the measure
            result["readable_while_full"] = False
            result["read_error"] = getattr(error, "code", type(error).__name__)
        result["no_keys_evicted"] = int(admin.dbsize()) >= before_keys
    finally:
        admin.config_set("maxmemory", memory.maxmemory_mb * 1024 * 1024)
    result["oom_refusal_seen"] = result["appends_refused_while_full"]["refused_by_the_ceiling"] == 12
    result["canaries_after_room"] = canaries.run(rounds=3, pause=0)
    return result


def _purge(admin: redis.Redis, settings: Any, embedding: str, dimensions: int, container: str, fixed: Mapping[str, Any]) -> dict[str, Any]:
    """Logical purge, then physical erasure of one distinctive record across AOF and RDB. Erasure counts only after the marker was seen on disk."""
    marker = f"k2erase{secrets.token_hex(12)}"
    registration = ProjectRegistration("k2-purge", 1, "git:k2-purge", "k2/purge", created=False)
    storage = GatewayIndexStorage(settings, scope=index_scope(registration, branch="k2", embedding=embedding, parser_version="k2"))
    owner = owner_id("k2purge")
    storage.call("generation", action="open", embedding=embedding, dimensions=dimensions, schema_version=SCHEMA_VERSION)
    token = storage.call("lease", action="acquire", owner=owner, ttl_ms=_LEASE_MS, kind="scope")["token"]
    epoch = storage.call("generation", action="begin", token=token)["epoch"]
    storage.call("batch", token=token, epoch=epoch, records=[_record(marker, dimensions)])
    storage.call("generation", action="publish", token=token, epoch=epoch, revision=_ANY_REVISION, dirty=False, coverage=_ONE_FILE)
    assert storage.call("query", mode="lexical", terms=[marker], k=1)["records"], "the marker must be found before it is purged"
    admin.execute_command("WAITAOF", 1, 0, 5000)
    reached = None
    wait_started = time.monotonic()
    while time.monotonic() - wait_started < 15:
        if _marker_state(container, marker) == "present":
            reached = round(time.monotonic() - wait_started, 3)
            break
        time.sleep(0.5)
    if reached is None:
        return {"marker_seen_on_disk": False, "note": "the positive control failed, so erasure was not measured", "logical_within": None, "physical_within": None}
    purge_started = time.monotonic()
    dropped = drop_and_time(storage, token, marker)
    denied, logical = dropped["route_denies_after_drop"], dropped["logical_purge_seconds"]
    admin.bgrewriteaof()
    _wait_flag(admin, "aof_rewrite_in_progress")
    admin.bgsave()
    _wait_flag(admin, "rdb_bgsave_in_progress")
    erased = None
    while time.monotonic() - purge_started < fixed["physical_erasure_seconds"] * 2:
        if _marker_state(container, marker) == "absent":
            erased = round(time.monotonic() - purge_started, 3)
            break
        time.sleep(0.5)
    return {"marker_sha256": f"hex:{hashlib.sha256(marker.encode()).hexdigest()}", "marker_seen_on_disk": True, "seconds_until_seen": reached, **dropped, "physical_erasure_seconds": erased,
            "logical_within": None if denied is None else denied and within(logical, fixed["logical_purge_seconds"]), "physical_within": within(erased, fixed["physical_erasure_seconds"])}


def _denied(storage: Any, marker: str) -> tuple[bool | None, str]:
    try:
        return not storage.call("query", mode="lexical", terms=[marker], k=1)["records"], "no records"
    except StorageRefusedError as error:  # the expected answer: this line no longer exists
        return error.code in {"SCOPE_UNKNOWN", "NOT_PUBLISHED"}, error.code
    except Exception as error:  # noqa: BLE001 - a transport failure says nothing either way
        return None, type(error).__name__


def drop_and_time(storage: Any, token: int, marker: str) -> dict[str, Any]:
    """Logical purge is how soon a reader is refused. The drop's first step takes the line out of service; the remaining steps only sweep the
    keyspace, so the whole drop is reported apart from the bound."""
    started = time.monotonic()
    cursor, first = None, None
    while True:
        cursor = storage.call("cleanup", action="drop", token=token, **({} if cursor is None else {"cursor": cursor})).get("cursor")
        if first is None:
            first = (*_denied(storage, marker), round(time.monotonic() - started, 3))
        if cursor is None:
            break
    swept = round(time.monotonic() - started, 3)
    denied, answer = _denied(storage, marker)
    return {"denied_after_first_step": first[0], "answer_after_first_step": first[1], "logical_purge_seconds": first[2], "whole_drop_seconds": swept,
            "route_denies_after_drop": None if denied is None or first[0] is None else denied and first[0], "route_answer": answer}


def run_k2(*, targets: Mapping[str, Any], config: Mapping[str, Any], memory: Any, connect: Callable[[], redis.Redis], settings: Any, large: Any, real_records: int, peaks: _Peaks, write: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    container = config["container"]
    peaks.phase = "k2"
    canaries = _Canaries(settings, large.embedder.identity, memory.embedding.dimensions, connect)
    bounds = targets["k2_second_run"]
    fixed = bounds["unchanged_from_the_first_probe"]
    term = config.get("k2_probe_term", "block")
    query = lambda: large.storage.call("query", mode="lexical", terms=[term], k=5)["records"]  # noqa: E731
    report: dict[str, Any] = {"schema": "plan12-memory-m1.k2.v2", "real_records_indexed": real_records, "items_target": bounds["items"], "bounds": bounds,
                              "limits": ["A prototype append is not the production Gate, notice or erasure workflow, which are M3's.", "One instance: the topology stays provisional if a bound fails.",
                                         f"The user {_K2_USER} exists for this run only, for WAITAOF, rewrites and memory changes; the index itself ran as its least-privilege user.",
                                         "Slow persistence is appendfsync always; the disk itself was not throttled."]}
    admin = connect()
    rounds = config["k2_rounds"]
    report["nominal"] = canaries.run(rounds=rounds, pause=0.05)
    write(report)
    report["burst"] = canaries.run(rounds=rounds, pause=0)
    write(report)
    report["during_aof_rewrite"] = rewrite_under_writes(admin, canaries, rounds=rounds)
    admin.bgsave()
    report["rdb_save_seconds"] = _wait_flag(admin, "rdb_bgsave_in_progress")
    write(report)
    admin.config_set("appendfsync", "always")
    try:
        report["slow_persistence_appendfsync_always"] = canaries.run(rounds=rounds, pause=0)
    finally:
        admin.config_set("appendfsync", "everysec")
    write(report)
    report["noeviction"] = _noeviction(admin, canaries, query, memory)
    write(report)

    # Restart: same container and volume. Timed from before the command, and the publication is read before anything can repair it.
    published = large.storage.call("coverage")["current"]
    peaks.sample()  # the container's own peak counter resets with it
    peaks.in_outage = True
    started = time.monotonic()
    restarted = subprocess.run(["docker", "restart", container], capture_output=True, check=False).returncode == 0
    usable = _reachable(query, started, 300)
    peaks.in_outage = False
    report["restart"] = {"command_succeeded": restarted, "seconds_until_usable": usable, "within": within(usable, fixed["restart_to_usable_seconds"])}
    write(report)
    if usable is None:
        report["stopped"] = "the instance did not come back after a restart; the later stages need it, so they did not run"
        write(report)
        return report
    report["restart"].update(same_publication=large.storage.call("coverage")["current"] == published, acknowledged_after=canaries.survived())
    write(report)

    # Crash: killed, started by the real lifecycle, timed from the kill. Survival and publication are read before the worker repairs anything.
    report["before_crash"] = canaries.run(rounds=5, pause=0)
    published = large.storage.call("coverage")["current"]
    peaks.sample()
    peaks.in_outage = True
    started = time.monotonic()
    subprocess.run(["docker", "kill", container], capture_output=True, check=False)
    status = local_infra.ensure_memory_redis(memory_index_root(Path(config["_config_root"])))
    usable = _reachable(query, started, 300)
    peaks.in_outage = False
    report["crash"] = {"ensure_state": status.state, "seconds_until_usable": usable, "within": within(usable, fixed["restart_to_usable_seconds"])}
    write(report)
    if usable is None:
        report["stopped"] = "the instance did not come back after a crash; the later stages need it, so they did not run"
        write(report)
        return report
    report["crash"].update(same_publication=large.storage.call("coverage")["current"] == published, acknowledged_after=canaries.survived())
    repair_started = time.perf_counter()
    repaired = large.worker().run(threading.Event())
    report["crash"]["repair"] = {"state": repaired.state, "seconds": round(time.perf_counter() - repair_started, 1), "records_written": repaired.records_written, "coverage": repaired.coverage}
    write(report)

    report["purge"] = _purge(connect(), settings, large.embedder.identity, memory.embedding.dimensions, container, fixed)
    peaks.sample()
    report["resources"] = {"peaks_by_phase": peaks.peaks, "used_within_limit": peaks.bound("k2", "used_memory_mb", bounds["maxmemory_mb"] - bounds["reserve"]["mb"]),
                           "physical_within": peaks.bound("k2", "container_memory_mb", bounds["physical_ram_mb"]["limit"]), "k2_disk_within": peaks.bound("k2", "disk_mb", bounds["disk_mb"])}
    nominal = report["nominal"]
    report["checks"] = {"items_at_least_target": real_records >= bounds["items"], "nominal_complete": nominal["complete"], "no_busy_at_nominal": not any("INDEX_BUSY" in name for name in nominal["errors"]), "no_errors_at_nominal": not nominal["errors"], "no_unprojected_at_nominal": nominal["unprojected"] == 0, "no_unconfirmed_at_nominal": nominal["unconfirmed"] == 0,
                        "ack_p95_within": within(nominal["ack_p95_ms"], fixed["ack_latency_p95_ms"]), "projection_p95_within": within(nominal["projection_p95_ms"], fixed["projection_latency_p95_ms"]),
                        "nothing_acknowledged_lost_or_conflicting_after_crash": report["crash"]["acknowledged_after"]["missing"] == 0 and report["crash"]["acknowledged_after"]["conflicting"] == 0,
                        "rewrite_overlap_proven": report["during_aof_rewrite"]["rewrite"]["overlap_proven"]}
    write(report)
    return report


def _session(root: Path, embedder: Any, work: Path, *, project: str, parser_version: str, storage_for: Callable[[str], Any]) -> MemorySession:
    return MemorySession(policy=FilePolicy(root), registration=ProjectRegistration(project, 1, f"git:{project}", str(root), created=False), storage_for=storage_for, embedder_for=lambda: embedder,
                         embedding_identity=embedder.identity, parser_version=parser_version, manifest_root=work / "manifests")


def _counted(settings: Any) -> tuple[list[scale._CountingStorage], Callable[[str], scale._CountingStorage]]:
    me = threading.get_ident()
    counters: list[scale._CountingStorage] = []

    def storage_for(scope: str) -> scale._CountingStorage:
        counters.append(scale._CountingStorage(GatewayIndexStorage(settings, scope=scope), me))
        return counters[-1]

    return counters, storage_for


def _calibrate_assembly(root: Path, settings: Any, embedder: Any, work: Path, *, project: str, parser_version: str, during_build: list[dict[str, Any]], qualifying: bool = False) -> dict[str, Any]:
    """Calibration unless the run is configured to qualify: limits are approved from a calibration and qualified on a later run, never the same one."""
    counters, storage_for = _counted(settings)
    session = _session(root, embedder, work, project=project, parser_version=parser_version, storage_for=storage_for)
    session.start()
    try:
        deadline = time.monotonic() + 3600
        while session._last_outcome is None or session._last_outcome.state != "complete":
            if time.monotonic() > deadline:
                return {"state": "CALIBRATION", "outcome": f"no complete pass in an hour: {session.status()}"}
            time.sleep(1)
        scope = session._current_scope()
        for counter in counters:
            counter.calls.clear()
        session._map = None
        started = time.perf_counter()
        map_text = session.repo_map(scope)
        refresh = {"wall_ms": round((time.perf_counter() - started) * 1000, 1), "route_calls": sum(sum(counter.calls.values()) for counter in counters), "chars": len(map_text)}
        idle = [_turn_or_error(session, counters, task, f"cal-{round_}-{number}") for round_ in range(5) for number, task in enumerate(_LARGE_TASKS)]
        session_edit = session_edit_visibility(session, root, scope.storage)
        state = "QUALIFICATION: judged against targets.json assembly_corpus_b" if qualifying else "CALIBRATION: never a qualification result"
        return {"state": state, "repo_map_on_a_miss": refresh, "session_edit": session_edit, "idle": _assembly_condition(idle, spread=False),
                "during_build": _assembly_condition(during_build, spread=True), "coverage": session.status()}
    finally:
        close_and_confirm_stopped(session)


def close_and_confirm_stopped(session: Any, *, seconds: float = 120) -> None:
    """The session's own close waits 10 s. A pass stalled in a listing or an embedding can outlive that, and K2 must not run under it."""
    session.close()
    thread = getattr(session, "_thread", None)
    if thread is not None:
        thread.join(seconds)
        if thread.is_alive():
            raise SystemExit("the calibration session's index pass did not stop; K2 would run under its load")


def session_edit_visibility(session: MemorySession, root: Path, storage: Any, *, limit_seconds: float = 900, poll_seconds: float = 0.1) -> dict[str, Any]:
    """An edit through the product's own path: the session's thread, its revision check and Git's changed paths, woken as a turn wakes it.
    This is the measure against the 6 s edit limit; the direct worker measure leaves out the session's revision scan."""
    target = scale.edit_target(root, ".java")
    expected = target.relative_to(scale.long_path(root)).as_posix()
    target.write_text(target.read_text(encoding="utf-8") + "\n\nclass M1SessionAddedClass { void m1SessionAddedMethod() {} }\n", encoding="utf-8")
    before = session._last_outcome
    started = time.perf_counter()
    session.request_pass()
    visible = None
    while visible is None and time.perf_counter() - started < limit_seconds:
        if any(record.get("path") == expected for record in storage.call("query", mode="lexical", terms=["m1sessionaddedmethod"], k=5)["records"]):
            visible = round(time.perf_counter() - started, 2)
        else:
            time.sleep(poll_seconds)
    while session._last_outcome is before and time.perf_counter() - started < limit_seconds:
        time.sleep(poll_seconds)
    ended = session._last_outcome
    return {"seconds_until_queryable": visible, "new_symbol_found": visible is not None, "pass_state": getattr(ended, "state", None) if ended is not before else "unfinished",
            "whole_pass_seconds": round(time.perf_counter() - started, 2) if ended is not before else None}


def _assembly_during_build(root: Path, settings: Any, embedder: Any, work: Path, *, project: str, parser_version: str, progress: Callable[[], float | None]) -> list[dict[str, Any]]:
    """The turn a person would get while the large line builds, on that line's published part, with how far the build had got when that turn
    began and when it ended. This session runs no worker: the build already holds the line."""
    counters, storage_for = _counted(settings)
    session = _session(root, embedder, work, project=project, parser_version=parser_version, storage_for=storage_for)
    session._embedder = embedder  # start() would load it, and also start a second worker on the line the build holds
    try:
        turns = []
        for number, task in enumerate(_LARGE_TASKS):
            at = progress()
            turn = _turn_or_error(session, counters, task, f"build-{at}-{number}")
            turns.append({**turn, "build_progress": at, "ended_at": time.perf_counter()})
        return turns
    finally:
        session.close()


_ASSEMBLY_MINIMUM_TURNS = 20  # per condition before an assembly limit can be qualified (Codex review 30)


def _turn_or_error(session: MemorySession, counters: list[scale._CountingStorage], task: str, run_id: str) -> dict[str, Any]:
    """Every turn is kept: one that raised is a finding, never dropped, and it cannot count toward the minimum."""
    try:
        return scale._measure_turn(session, counters, task, run_id)
    except Exception as error:  # noqa: BLE001 - kept in the report; this is the measure
        return {"task": task, "error": f"{type(error).__name__}: {str(error)[:200]}"}


def _build_third(progress: float | None) -> str | None:
    if progress is None:
        return None
    return "early" if progress < 1 / 3 else "middle" if progress < 2 / 3 else "late"


def _assembly_condition(turns: list[dict[str, Any]], *, spread: bool) -> dict[str, Any] | None:
    """One condition's turns, summarised over those that completed, and whether they are enough to qualify a limit: the minimum count, the dense
    channel in every turn, no turn that raised and, during a build, samples in its early, middle and late thirds."""
    if not turns:
        return None
    counted = [turn for turn in turns if turn.get("during_build") is True] if spread else turns  # turns after the build ended are kept, not counted
    valid = [turn for turn in counted if "error" not in turn]
    errors = [turn["error"] for turn in counted if "error" in turn]
    out: dict[str, Any] = {**scale._assembly_summary(valid), **_dense_in_every_turn(counted), "errors": errors, "per_turn": turns}
    if spread:
        out["turns_after_the_build_ended"] = len(turns) - len(counted)
    short: list[str] = []
    if len(valid) < _ASSEMBLY_MINIMUM_TURNS:
        short.append(f"{len(valid)} completed turns, fewer than {_ASSEMBLY_MINIMUM_TURNS}")
    if not out["dense_in_every_turn"]:
        short.append("a turn without the dense channel's answer")
    if errors:
        short.append(f"{len(errors)} turns raised")
    if spread:
        sampled = {_build_third(turn.get("build_progress")) for turn in valid}
        out["build_thirds_sampled"] = [third for third in ("early", "middle", "late") if third in sampled]
        missing = [third for third in ("early", "middle", "late") if third not in sampled]
        if missing:
            short.append(f"no sample in the {', '.join(missing)} third of the build")
    out["enough_to_qualify"] = not short
    if short:
        out["not_enough_because"] = short
    return out


def mark_during_build(turns: list[dict[str, Any]], build_ended: float | None) -> None:
    """A turn counts as during the build only if it ended before the worker's own finish; a batch can cross it. A build with no recorded finish
    vouches for no turn. Each turn keeps how long before the finish it ended, negative once the build was over."""
    for turn in turns:
        ended = turn.pop("ended_at", None)
        turn["during_build"] = build_ended is not None and ended is not None and ended <= build_ended
        turn["seconds_before_build_end"] = None if build_ended is None or ended is None else round(build_ended - ended, 1)


def _build_progress(call: Callable[..., dict[str, Any]]) -> float | None:
    """How far a cold build has got, from its own latest publication: files indexed over the honest total. None if it cannot be read."""
    try:
        coverage = (call("coverage").get("current") or {}).get("coverage") or {}
    except Exception:  # noqa: BLE001 - an unread progress leaves the sample unplaced, so it cannot fill a third
        return None
    total = coverage.get("files_total")
    return round(coverage.get("files_indexed", 0) / total, 3) if total else None


def _dense_in_every_turn(turns: list[dict[str, Any]]) -> dict[str, Any]:
    """Hybrid assembly needs the dense channel's answer each turn. A call that was refused or unavailable still leaves retrieval "ok", so the
    channel's own outcome decides, and any channel that did not answer is named."""
    missing = [turn["task"] for turn in turns if not str(turn.get("channels", {}).get("dense", "")).endswith(" results")]
    failed = sorted({f"{name}: {outcome}" for turn in turns for name, outcome in turn.get("channels", {}).items()
                     if outcome.startswith(("refused", "unavailable", "not asked", "no embedding"))})
    return {"dense_in_every_turn": not missing, **({"turns_without_dense": missing} if missing else {}), **({"channels_that_did_not_answer": failed} if failed else {})}


def _built_with_samples(index: scale._Index, foreground: scale._Index, store: memory_index.IndexStore, *, config: Mapping[str, Any], pids: dict[str, int], turns: Any, during_build: list[dict[str, Any]], assembly: Callable[[Callable[[], float | None]], list[dict[str, Any]]]) -> dict[str, Any]:
    """The cold build under its limit, with foreground work on the finished line while it runs: what a person's turn meets. A timer of its own holds the limit, and the
    worker stamps its own finish, so a foreground sample cannot postpone the cancel or lengthen the measured build."""
    cancel = threading.Event()
    real_call = index.storage.call
    first_publish: list[float] = []
    finished: list[float] = []
    done: list[Any] = []
    failure: list[str] = []

    def watching(op: str, **fields: Any) -> dict[str, Any]:
        reply = real_call(op, **fields)
        if op == "generation" and fields.get("action") == "publish" and not first_publish:
            first_publish.append(time.perf_counter())
        return reply

    def build_it() -> None:
        try:
            done.append(index.worker().run(cancel))
        except Exception as error:  # noqa: BLE001 - kept in the report; the run stops at its own check
            failure.append(type(error).__name__)
        finally:
            finished.append(time.perf_counter())

    limit = config["hours_limit"] * 3600
    index.storage.call = watching  # type: ignore[method-assign]
    started = time.perf_counter()
    build = threading.Thread(target=build_it, daemon=True)
    timer = threading.Timer(limit, cancel.set)
    timer.daemon = True
    samples: list[dict[str, Any]] = []
    turn_samples: list[dict[str, Any]] = []
    foreground_errors: list[str] = []
    vector = mic.encode_vector(foreground.embedder.embed(["measure a query vector for this repository"])[0])
    terms = ["gateway", "redis", "context", "policy", "server", "approval", "token", "manifest"]
    try:
        with scale._Sampler(pids) as sampler:
            build.start()
            timer.start()
            next_sample = time.monotonic() + config.get("first_sample_seconds", 60)
            next_assembly: float | None = None
            while build.is_alive():
                # Assembly on its own cadence from the first publish, so its turns spread across the build's early, middle and late thirds.
                if first_publish and (next_assembly is None or time.monotonic() >= next_assembly):
                    try:
                        during_build.extend(assembly(lambda: _build_progress(real_call)))
                    except Exception as error:  # noqa: BLE001 - a finding; it never stops the build
                        foreground_errors.append(f"assembly {type(error).__name__}: {str(error)[:200]}")
                    next_assembly = time.monotonic() + config.get("assembly_sample_seconds", 1800)
                if time.monotonic() >= next_sample:
                    try:
                        samples.append({"at_seconds": round(time.perf_counter() - started), **scale._query_load(foreground, store, samples=config["query_samples"], terms=terms, vector=vector)})
                        if turns is not None and not turn_samples:
                            turn_samples.append({"at_seconds": round(time.perf_counter() - started), "turns": turns.turns(config["acpx_turns"]), "cancel": turns.cancel_during_a_turn(), "measures": "machine load on a person's turn; this agent's own Gateway and kit, not the indexed line"})
                    except Exception as error:  # noqa: BLE001 - foreground failures are findings and never stop the build
                        foreground_errors.append(f"{type(error).__name__}: {str(error)[:200]}")
                    next_sample = time.monotonic() + config["foreground_sample_seconds"]
                time.sleep(1)
            build.join()
    finally:
        timer.cancel()
        if build.is_alive():
            cancel.set()
            build.join(300)
        index.storage.call = real_call  # type: ignore[method-assign]
    mark_during_build(during_build, finished[0] if finished else None)
    seconds = (finished[0] if finished else time.perf_counter()) - started
    outcome = done[0] if done else None
    return {"state": getattr(outcome, "state", "no-result"), "detail": getattr(outcome, "detail", None), "failure": failure, "hours": round(seconds / 3600, 3), "within_the_hours_limit": seconds <= limit, "seconds": round(seconds, 1), "files_written": getattr(outcome, "files_written", None), "records_written": getattr(outcome, "records_written", None),
            "coverage": getattr(outcome, "coverage", None), "first_file_visible_seconds": round(first_publish[0] - started, 2) if first_publish else None, "processes": sampler.report(), "foreground_during_build": samples, "foreground_errors": foreground_errors, "acpx_during_build": turn_samples}


def run_qualify(config: dict[str, Any], repository: Path) -> dict[str, Any]:
    work = repository / config["work_dir"]
    admin_password = secrets.token_hex(24)
    config = {**config, "_config_root": str(work / "config")}
    report_path = repository / config["out"]
    k2_path = repository / config["k2_out"]
    targets = json.loads((repository / "reports/plan12-memory-m1/targets.json").read_text(encoding="utf-8"))
    head = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    report: dict[str, Any] = {"schema": "plan12-memory-m1.qualify.v2", "phase": "qualify", "head": f"hex:{head}", "config": {k: v for k, v in config.items() if k not in {"artifact_cache", "_config_root"}},
                              "host": {"cpus": psutil.cpu_count(), "memory_gb": round(psutil.virtual_memory().total / 2**30, 1)}}

    def save() -> None:
        report_path.write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")

    save()
    root, memory, _password, client, gateway, settings, settings_file = scale._provision(config, repository, work, prepare=lambda path: k2_admin_acl(path, admin_password))

    def connect() -> redis.Redis:
        return redis.Redis(host="127.0.0.1", port=memory.port, username=_K2_USER, password=admin_password, socket_timeout=30, socket_connect_timeout=10)

    kit = os.environ.get("P1210_ACPX_KIT")
    turns = None
    peaks = _Peaks(config["container"], connect, interval=config.get("peak_sample_seconds", 30))
    try:
        with peaks:
            inner = FastembedEmbedder(root, memory.embedding, directory=settings_file["embedding"]["artifact_directory"], threads=config["embedding_threads"])
            launcher = psutil.Process(gateway.pid)
            pids = {"gateway": (launcher.children() or [launcher])[0].pid, "worker": psutil.Process().pid}
            store = memory_index.IndexStore(client, cursor_key=b"m" * 32)

            scale._note("this repository (reusing the evaluation's embeddings where its text matches)")
            repo_copy = scale._corpus_copy(repository, work / "corpus-repo", config["repo_paths"])
            report["repository"] = {"count": scale.count_corpus(repo_copy)}
            cached = CachedEmbedder(inner, repository / config["embedding_cache"])
            repo_index = scale._Index(repo_copy, settings, cached, project="qualify-repo", parser_version="qualify")  # type: ignore[arg-type]
            started = time.perf_counter()
            repo_outcome = repo_index.worker().run(threading.Event())
            report["repository"].update(state=repo_outcome.state, seconds=round(time.perf_counter() - started, 1), records_written=repo_outcome.records_written, embedded_now=cached.embedded, coverage=repo_outcome.coverage, note="Embeddings reused, so this time is not a build forecast.")
            save()

            large = clone_large_corpus(repository / config["large_corpus"], work / "corpus-large", expected_commit=config["large_commit"].removeprefix("hex:"))
            count = scale.count_corpus(large)
            report["large"] = {"count": count, "parsed_java_at_least_1m": count["parsed_lines"]["java"] >= 1_000_000, "commit": config["large_commit"]}
            save()
            embedder = scale._TimedEmbedder(inner)
            index = scale._Index(large, settings, embedder, project="qualify-large", parser_version="qualify")
            if kit:
                turns = scale._AcpxTurns(Path(kit).resolve(), work / "acpx-stub", stub_seconds=int(config["hours_limit"] * 3600) + 3600)
                opened = turns.open()
                first_turn = turns.turns(1)
                if opened != "0" or first_turn["failures"]:  # before the build, or a broken launch costs hours and leaves no foreground evidence
                    report["acpx"] = {"session_new_exit": opened, "first_turn": first_turn, "failure_output": turns.failure}
                    report["stopped"] = "the acpx agent did not start, so the build was not begun"
                    save()
                    return report
                report["acpx"] = {"first_turn": first_turn, "queue_owners_recorded": turns.record_owner(), "idle": turns.turns(config["acpx_turns"]), "idle_cancel": turns.cancel_during_a_turn(), "measures": "machine load on a person's turn; this agent's own Gateway and kit, not the indexed line"}
            else:
                report["acpx"] = {"state": "UNRUN", "reason": "P1210_ACPX_KIT names no approved stub agent"}
            save()
            scale._note(f"large corpus: {count['embedded_chunks']} chunks")
            during_build: list[dict[str, Any]] = []
            report["large"]["cold"] = _built_with_samples(index, repo_index, store, config=config, pids=pids, turns=turns, during_build=during_build,
                                                          assembly=lambda progress: _assembly_during_build(large, settings, embedder, work, project="qualify-large", parser_version="qualify", progress=progress))
            report["large"]["cold"]["embedded_items_per_second"] = round(embedder.items / embedder.seconds, 1) if embedder.seconds else None
            report["large"]["cold"]["redis"] = scale._redis_facts(client, config["container"])
            peaks.sample()
            report["large"]["cold"]["peaks"] = dict(peaks.peaks.get("index", {}))
            report["large"]["cold"]["index_disk_within_2048"] = peaks.bound("index", "disk_mb", 2048)
            save()

            if report["large"]["cold"]["state"] != "complete":
                report["stopped"] = "the large build did not complete; K2 and the later stages need its records, so they did not run"
                save()
                return report
            scale._note("reconcile, edit, queries")
            started = time.perf_counter()
            unchanged = index.worker().run(threading.Event())
            elapsed = time.perf_counter() - started
            files = sum(count["files"].values())
            report["large"]["reconcile_unchanged"] = {"state": unchanged.state, "seconds": round(elapsed, 1), "seconds_per_1000_files": round(elapsed / max(files, 1) * 1000, 1), "records_written": unchanged.records_written}
            target = scale.edit_target(large, ".java")
            target.write_text(target.read_text(encoding="utf-8") + "\n\nclass M1QualifyAddedClass { void m1QualifyAddedMethod() {} }\n", encoding="utf-8")
            report["large"]["incremental_one_file"] = scale.edit_visibility(lambda cancel: index.worker().run(cancel), lambda: scale._symbol_at(index, "m1QualifyAddedMethod", large, target))
            vector = mic.encode_vector(embedder.embed(["how does the namenode place a block"])[0])
            report["large"]["query_idle"] = scale._query_load(index, store, samples=config["query_samples"], terms=["block", "namenode", "container", "token", "replica", "lease", "scheduler", "rpc"], vector=vector)
            report["large"]["bulk"] = scale._bulk(index, store, batches=config["bulk_batches"], dimensions=memory.embedding.dimensions)
            save()

            second = scale._Index(large, settings, embedder, project="qualify-cancel", parser_version="qualify-cancel")
            cancel = threading.Event()
            built: list[Any] = []
            worker = threading.Thread(target=lambda: built.append(second.worker().run(cancel)), daemon=True)
            worker.start()
            time.sleep(30)
            started = time.perf_counter()
            cancel.set()
            worker.join(120)
            report["large"]["cancel"] = {"seconds_to_stop": round(time.perf_counter() - started, 3), "state": built[0].state if built else "no-result"}
            save()

            scale._note("assembly calibration")
            report["large"]["assembly_calibration"] = _calibrate_assembly(large, settings, embedder, work, project="qualify-large", parser_version="qualify", during_build=during_build,
                                                                         qualifying=bool(config.get("assembly_qualifies")))
            report["redis_before_k2"] = scale._redis_facts(client, config["container"])
            save()

            scale._note("K2")

            def write_k2(k2: dict[str, Any]) -> None:
                k2_path.write_text(json.dumps({**k2, "head": f"hex:{head}"}, indent=1, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")

            real = (repo_outcome.records_written or 0) + (report["large"]["cold"]["records_written"] or 0)
            run_k2(targets=targets, config=config, memory=memory, connect=connect, settings=settings, large=index, real_records=real, peaks=peaks, write=write_k2)
            client.close()
    finally:
        save()
        if turns is not None:
            turns.close()
        gateway.kill()
        gateway.wait(10)
    return report
