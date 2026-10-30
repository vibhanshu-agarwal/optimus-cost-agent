"""Plan 12.7 P3: synthetic K2 feasibility on one released, dedicated Redis (never the shared test server).

Admission runs before any client exists (`probes.admit_redis_resource`). The server's identity is then
confirmed read-only: the run ID seen through the endpoint must equal the one seen inside the released
container, the database must be empty, and AOF/noeviction/maxmemory must match the config. Only then
is synthetic load written. Every bound comes from the predeclared `targets.redis`; nothing is tuned
after the fact. Payload bodies stay in Redis and RAM; records carry counts, timings and hashes.
"""

from __future__ import annotations

import hashlib
import os
import random
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from tools.plan12_memory.probes import (
    AdmissionError,
    ProbeContext,
    ProbeResult,
    Runner,
    admit_redis_endpoint,
    admit_redis_resource,
    docker_inspect,
    run_command,
)

INDEX = "p127idx"
EVENTS = "p127:events"
ITEM = "p127:item:"
DERIVED = "p127:derived:"
ACK_SAMPLES_PER_WORKER = 100
BULK_BATCH = 500
WAITAOF_TIMEOUT_MS = 5000
MIN_VERSION = (8, 4)


def _pct(values: list[float], quantile: float) -> float | None:
    return round(sorted(values)[max(0, int(len(values) * quantile + 0.5) - 1)], 3) if values else None


def _p95(values: list[float]) -> float | None:
    return _pct(values, 0.95)


def _info(client: Any, section: str) -> dict[str, Any]:
    return client.info(section)


def _wait(predicate: Callable[[], bool], timeout: float, context: ProbeContext) -> float | None:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        context.check()
        try:
            if predicate():
                return round(time.monotonic() - started, 3)
        except Exception:  # a server still loading answers with errors; keep waiting until the deadline
            pass
        time.sleep(0.05)
    return None


def _container_run_id(runner: Runner, container: str, username: str | None, password: str) -> str:
    argv = ["docker", "exec", "-e", "REDISCLI_AUTH", container, "redis-cli", "--no-auth-warning"]
    argv += ["--user", username] if username else []
    completed = runner([*argv, "INFO", "server"], 60, {"REDISCLI_AUTH": password} if password else None)
    for line in completed.stdout.splitlines():
        if line.startswith("run_id:"):
            return line.split(":", 1)[1].strip()
    raise AdmissionError("could not read the run id inside the released container")


def _container_memory_bytes(runner: Runner, container: str) -> int | None:
    completed = runner(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", container], 60, None)
    text = completed.stdout.strip().split("/")[0].strip()
    units = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "kB": 1000, "MB": 1000**2, "GB": 1000**3}
    for unit in sorted(units, key=len, reverse=True):
        if text.endswith(unit):
            try:
                return int(float(text[: -len(unit)]) * units[unit])
            except ValueError:
                return None
    return None


def _disk_bytes(runner: Runner, container: str) -> int | None:
    completed = runner(["docker", "exec", container, "du", "-sb", "/data"], 60, None)
    try:
        return int(completed.stdout.split()[0])
    except (IndexError, ValueError):
        return None


def _marker_on_disk(runner: Runner, container: str, marker: str) -> bool:
    completed = runner(["docker", "exec", container, "grep", "-rlF", marker, "/data"], 60, None)
    return completed.returncode == 0 and bool(completed.stdout.strip())


class _Sampler:
    """Peak container RAM, sampled in the background while persistence forks run."""

    def __init__(self, runner: Runner, container: str) -> None:
        self.runner, self.container, self.peak = runner, container, 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        while not self._stop.is_set():
            if (value := _container_memory_bytes(self.runner, self.container)) is not None:
                self.peak = max(self.peak, value)
            self._stop.wait(0.5)

    def __enter__(self) -> _Sampler:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(10)


def run_redis(context: ProbeContext, result: ProbeResult, runner: Runner = run_command,
              client_factory: Callable[[], Any] | None = None) -> None:
    config = context.config
    resource = config.redis
    if resource is None:
        result.outcome, result.disposition = "UNRUN", "open"
        result.limitations.append("no released redis section; no client was constructed")
        return
    if not config.redis_targets_complete():
        result.outcome, result.disposition = "UNRUN", "open"
        result.limitations.append("predeclared numeric targets.redis are incomplete; a qualifying run needs all of them")
        return
    identity = admit_redis_resource(resource, lambda name: docker_inspect(name, runner))
    host, port, database = admit_redis_endpoint(resource)
    password = os.environ.get(resource.credential_env or "", "") if resource.credential_env else ""
    if resource.credential_env and not password:
        raise AdmissionError("the redis password environment variable is not set")
    if password:
        context.ram_only.add(password)
    targets = config.targets["redis"]
    if client_factory is None:
        import redis

        def client_factory() -> Any:
            return redis.Redis(host=host, port=port, db=database, username=resource.username, password=password or None,
                               socket_timeout=60, socket_connect_timeout=10, decode_responses=True)

    client = client_factory()
    context.on_cleanup("close redis client", client.close)
    obs: dict[str, Any] = {"identity": identity}
    server = _info(client, "server")
    version = tuple(int(part) for part in str(server.get("redis_version", "0.0")).split(".")[:2])
    if server.get("run_id") != _container_run_id(runner, resource.container, resource.username, password):
        raise AdmissionError("the endpoint does not reach the released container (run ids differ)")
    modules = sorted(str(row.get("name")) for row in client.module_list())
    settings = {key: client.config_get(key)[key] for key in ("appendonly", "appendfsync", "maxmemory", "maxmemory-policy")}
    obs["server"] = {"redis_version": server.get("redis_version"), "modules": modules, "config": settings,
                     "redis_py": __import__("redis").__version__}
    preflight = {"version_at_least_8_4": version >= MIN_VERSION,
                 "search_json_timeseries": {"search", "ReJSON", "timeseries"} <= set(modules),
                 "aof_on": settings["appendonly"] == "yes", "noeviction": settings["maxmemory-policy"] == "noeviction",
                 "maxmemory_matches_target": int(settings["maxmemory"]) == int(targets["maxmemory_bytes"]),
                 "database_empty": client.dbsize() == 0}
    obs["preflight"] = preflight
    if not all(preflight.values()):
        result.observations.update(obs)
        raise AdmissionError(f"released server does not match the probe config: {[k for k, v in preflight.items() if not v]}")

    items, dims, item_bytes = int(targets["items"]), int(targets["vector_dimensions"]), int(targets["item_bytes"])
    workers = int(targets["concurrency"])
    client.execute_command("FT.CREATE", INDEX, "ON", "JSON", "PREFIX", "1", ITEM, "SCHEMA", "$.id", "AS", "id", "TAG",
                           "$.kind", "AS", "kind", "TAG", "$.vector", "AS", "vector", "VECTOR", "FLAT", "6", "TYPE",
                           "FLOAT32", "DIM", str(dims), "DISTANCE_METRIC", "COSINE")
    rng = random.Random(1207)

    def document(index: int) -> dict[str, Any]:
        text = f"p127-{index}-" + "x" * max(0, item_bytes - 16)
        return {"id": str(index), "kind": "memory", "text": text, "vector": [round(rng.random(), 6) for _ in range(dims)]}

    def found(index: int) -> bool:
        return int(client.execute_command("FT.SEARCH", INDEX, f"@id:{{{index}}}", "NOCONTENT")[0]) == 1

    # Acknowledged single writes: append then WAITAOF on the same connection, as the Gate would.
    acks, projections, unconfirmed = [], [], 0
    lock = threading.Lock()
    ack_ids = list(range(workers * ACK_SAMPLES_PER_WORKER))
    docs = {index: document(index) for index in ack_ids}

    def ack_worker(ids: list[int]) -> None:
        nonlocal unconfirmed
        own = client_factory()
        try:
            for index in ids:
                context.check()
                started = time.perf_counter()
                own.xadd(EVENTS, {"id": index, "v": 1})
                local, _ = own.execute_command("WAITAOF", 1, 0, WAITAOF_TIMEOUT_MS)
                acked = time.perf_counter()
                own.json().set(f"{ITEM}{index}", "$", docs[index])
                while not int(own.execute_command("FT.SEARCH", INDEX, f"@id:{{{index}}}", "NOCONTENT")[0]):
                    time.sleep(0.001)
                with lock:
                    acks.append((acked - started) * 1000)
                    projections.append((time.perf_counter() - acked) * 1000)
                    unconfirmed += int(local) < 1
        finally:
            own.close()

    threads = [threading.Thread(target=ack_worker, args=(ack_ids[w::workers],), daemon=True) for w in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    docs.clear()
    obs["acknowledged_writes"] = {"count": len(acks), "unconfirmed": unconfirmed, "ack_p50_ms": _pct(acks, 0.5),
                                  "ack_p95_ms": _p95(acks), "projection_p95_ms": _p95(projections),
                                  "appendfsync": settings["appendfsync"]}

    # Bulk rebuild load: group commits, one WAITAOF per pipeline.
    bulk_started = time.perf_counter()
    for start in range(len(ack_ids), items, BULK_BATCH):
        context.check()
        pipe = client.pipeline(transaction=False)
        for index in range(start, min(items, start + BULK_BATCH)):
            pipe.xadd(EVENTS, {"id": index, "v": 1})
            pipe.json().set(f"{ITEM}{index}", "$", document(index))
        pipe.execute()
        local, _ = client.execute_command("WAITAOF", 1, 0, WAITAOF_TIMEOUT_MS)
        unconfirmed += int(local) < 1
    obs["bulk_load_seconds"] = round(time.perf_counter() - bulk_started, 3)
    indexed = _wait(lambda: str(_ft_info(client).get("percent_indexed")) in {"1", "1.0"}, 600, context)
    obs["index_ready_seconds"] = indexed

    memory = _info(client, "memory")
    logical = int(memory["used_memory"]) - int(memory.get("mem_not_counted_for_evict", 0))
    obs["memory_after_load"] = {"used_memory": memory["used_memory"], "mem_not_counted_for_evict": memory.get("mem_not_counted_for_evict"),
                                "logical_bytes": logical, "num_docs": _ft_info(client).get("num_docs")}

    # Rebuild burst: drop the index (documents stay), recreate, wait for full indexing.
    client.execute_command("FT.DROPINDEX", INDEX)
    rebuild_started = time.perf_counter()
    client.execute_command("FT.CREATE", INDEX, "ON", "JSON", "PREFIX", "1", ITEM, "SCHEMA", "$.id", "AS", "id", "TAG",
                           "$.kind", "AS", "kind", "TAG", "$.vector", "AS", "vector", "VECTOR", "FLAT", "6", "TYPE",
                           "FLOAT32", "DIM", str(dims), "DISTANCE_METRIC", "COSINE")
    obs["rebuild_ready_seconds"] = _wait(lambda: str(_ft_info(client).get("percent_indexed")) in {"1", "1.0"} and
                                         int(_ft_info(client).get("indexing", 1)) == 0, 600, context)
    obs["rebuild_wall_seconds"] = round(time.perf_counter() - rebuild_started, 3)

    # Derived growth until the admission reserve, then prove noeviction refuses instead of evicting.
    ceiling = int(targets["maxmemory_bytes"]) - int(targets["admission_reserve_bytes"])
    derived, before_growth = 0, logical
    while derived < items and logical < ceiling:
        context.check()
        pipe = client.pipeline(transaction=False)
        for index in range(derived, min(items, derived + BULK_BATCH)):
            pipe.set(f"{DERIVED}{index}", "d" * 512)
        pipe.execute()
        derived = min(items, derived + BULK_BATCH)
        memory = _info(client, "memory")
        logical = int(memory["used_memory"]) - int(memory.get("mem_not_counted_for_evict", 0))
    keys_before = client.dbsize()
    client.config_set("maxmemory", int(memory["used_memory"]) + 1024 * 1024)
    try:
        client.set("p127:oom-control", "o" * (4 * 1024 * 1024))
        oom_refused = False
    except Exception as error:
        oom_refused = "OOM" in str(error)
    finally:
        client.config_set("maxmemory", int(targets["maxmemory_bytes"]))
    obs["derived_growth"] = {"derived_keys": derived, "logical_before": before_growth, "logical_after": logical,
                             "bytes_per_derived_key": round((logical - before_growth) / derived, 1) if derived else None,
                             "reserve_ceiling": ceiling, "noeviction_refuses_write": oom_refused,
                             "no_keys_evicted": client.dbsize() == keys_before}

    # Persistence forks under load; physical RAM is sampled meanwhile, including copy-on-write peaks.
    slow_acks: list[float] = []
    with _Sampler(runner, resource.container) as sampler:
        client.execute_command("BGREWRITEAOF")
        for index in range(items, items + 50):
            started = time.perf_counter()
            client.xadd(EVENTS, {"id": index, "v": 1})
            local, _ = client.execute_command("WAITAOF", 1, 0, WAITAOF_TIMEOUT_MS)
            slow_acks.append((time.perf_counter() - started) * 1000)
            unconfirmed += int(local) < 1
        rewrite = _wait(lambda: int(_info(client, "persistence")["aof_rewrite_in_progress"]) == 0, 600, context)
        client.execute_command("BGSAVE")
        save = _wait(lambda: int(_info(client, "persistence")["rdb_bgsave_in_progress"]) == 0, 600, context)
    persistence = _info(client, "persistence")
    obs["persistence"] = {"aof_rewrite_seconds": rewrite, "rdb_save_seconds": save,
                          "aof_last_bgrewrite_status": persistence.get("aof_last_bgrewrite_status"),
                          "rdb_last_bgsave_status": persistence.get("rdb_last_bgsave_status"),
                          "ack_during_rewrite_p95_ms": _p95(slow_acks), "physical_peak_bytes": sampler.peak or None,
                          "disk_bytes": _disk_bytes(runner, resource.container)}
    acked_events = client.xlen(EVENTS)
    obs["unconfirmed_total"] = unconfirmed

    # Restart: same container and volume, reconciled through admission; acknowledged writes must survive.
    old_run_id = server.get("run_id")
    runner(["docker", "restart", "--time", "30", resource.container], 180, None)
    restart_started = time.monotonic()
    client.close()
    client = client_factory()
    context.on_cleanup("close restarted redis client", client.close)
    usable = _wait(lambda: client.ping() and int(_info(client, "persistence").get("loading", 1)) == 0 and found(items - 1),
                   float(targets["restart_to_usable_seconds"]) * 4, context)
    obs["restart"] = {"usable_seconds": usable, "wall_seconds": round(time.monotonic() - restart_started, 3),
                      "readmitted": admit_redis_resource(resource, lambda name: docker_inspect(name, runner)),
                      "run_id_changed": _info(client, "server").get("run_id") != old_run_id,
                      "acknowledged_events_survived": client.xlen(EVENTS) >= acked_events,
                      "documents_survived": int(_ft_info(client).get("num_docs", 0)) >= items}

    # Logical purge, then the physical-erasure horizon for that payload across AOF and RDB files.
    marker = f"p127-erase-{uuid.uuid4().hex}"
    context.ram_only.add(marker)
    victim = items + 1000
    client.json().set(f"{ITEM}{victim}", "$", {"id": str(victim), "kind": "memory", "text": marker,
                                               "vector": [0.5] * dims})
    client.execute_command("WAITAOF", 1, 0, WAITAOF_TIMEOUT_MS)
    on_disk_before = _wait(lambda: _marker_on_disk(runner, resource.container, marker), 10, context) is not None
    purge_started = time.monotonic()
    client.xadd(EVENTS, {"id": victim, "tombstone": 1})
    client.delete(f"{ITEM}{victim}")
    logical_purge = _wait(lambda: not found(victim), float(targets["logical_purge_seconds"]) * 10, context)
    client.execute_command("BGREWRITEAOF")
    _wait(lambda: int(_info(client, "persistence")["aof_rewrite_in_progress"]) == 0, 600, context)
    client.execute_command("BGSAVE")
    _wait(lambda: int(_info(client, "persistence")["rdb_bgsave_in_progress"]) == 0, 600, context)
    erased = _wait(lambda: not _marker_on_disk(runner, resource.container, marker),
                   float(targets["physical_erasure_seconds"]) * 2, context)
    obs["purge"] = {"marker_sha256": hashlib.sha256(marker.encode()).hexdigest(), "marker_on_disk_before": on_disk_before,
                    "logical_purge_seconds": logical_purge,
                    "physical_erasure_seconds": round(time.monotonic() - purge_started, 3) if erased is not None else None}

    checks = {
        "no_unconfirmed_acknowledgements": obs["unconfirmed_total"] == 0,
        "ack_p95_within": _le(obs["acknowledged_writes"]["ack_p95_ms"], targets["ack_latency_p95_ms"]),
        "projection_p95_within": _le(obs["acknowledged_writes"]["projection_p95_ms"], targets["projection_latency_p95_ms"]),
        "logical_memory_below_reserve": obs["memory_after_load"]["logical_bytes"] <= ceiling,
        "physical_ram_within": _le(obs["persistence"]["physical_peak_bytes"], targets["physical_ram_bytes"]),
        "disk_within": _le(obs["persistence"]["disk_bytes"], targets["disk_bytes"]),
        "noeviction_refuses_write": oom_refused and obs["derived_growth"]["no_keys_evicted"],
        "persistence_ok": persistence.get("aof_last_bgrewrite_status") == "ok" and persistence.get("rdb_last_bgsave_status") == "ok",
        "restart_within": _le(usable, targets["restart_to_usable_seconds"]),
        "acknowledged_writes_survive_restart": obs["restart"]["acknowledged_events_survived"] and obs["restart"]["documents_survived"],
        "marker_reached_disk": on_disk_before,
        "logical_purge_within": _le(logical_purge, targets["logical_purge_seconds"]),
        "physical_erasure_within": _le(obs["purge"]["physical_erasure_seconds"], targets["physical_erasure_seconds"]),
    }
    obs["checks"] = checks
    obs["targets"] = dict(targets)
    result.observations.update(obs)
    result.outcome = "PASS" if all(checks.values()) else "FAIL"
    result.disposition = "concluded"
    result.limitations += ["synthetic single-instance result; topology is provisional until M1 repeats K2 on the real corpus",
                           "a prototype append is not the production Gate, notice or erasure workflow (M3)"]
    result.follow_up = ("M1 repeats K2 on the real corpus with production adapters"
                        if result.outcome == "PASS" else
                        "single instance failed its bounds: the two-instance fallback needs its own released run in M1")


def _le(value: float | None, bound: float) -> bool:
    return value is not None and value <= bound


def _ft_info(client: Any) -> dict[str, Any]:
    raw = client.execute_command("FT.INFO", INDEX)
    return {str(key): value for key, value in zip(raw[::2], raw[1::2], strict=False)}

