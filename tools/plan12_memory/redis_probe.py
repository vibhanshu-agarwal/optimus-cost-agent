"""Plan 12.7 P3: synthetic K2 feasibility on one released, dedicated Redis (never the shared test server).

Admission runs before any client exists (`probes.admit_redis_resource`). The server's identity is then
confirmed read-only: the run ID seen through the endpoint must equal the one seen inside the released
container, the database must be empty, and AOF/noeviction/maxmemory must match the config. Only then
is synthetic load written. Every bound comes from the predeclared `targets.redis`; nothing is tuned
after the fact. Every wait is bounded by the probe deadline. A check that could not be observed is
recorded as unknown, which makes the result INCONCLUSIVE rather than a pass. Payload bodies stay in
Redis and RAM; records carry counts, timings and hashes.
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
    verdict,
)

INDEX = "p127idx"
EVENTS = "p127:events"
ITEM = "p127:item:"
DERIVED = "p127:derived:"
ACK_SAMPLES_PER_WORKER = 100
BULK_BATCH = 500
WAITAOF_TIMEOUT_MS = 5000
PROJECTION_WAIT_SECONDS = 10
MIN_VERSION = (8, 4)


def _pct(values: list[float], quantile: float) -> float | None:
    return round(sorted(values)[max(0, int(len(values) * quantile + 0.5) - 1)], 3) if values else None


def _p95(values: list[float]) -> float | None:
    return _pct(values, 0.95)


def _info(client: Any, section: str) -> dict[str, Any]:
    return client.info(section)


def _wait(predicate: Callable[[], bool], timeout: float, context: ProbeContext) -> float | None:
    """Seconds until the predicate held, or None if it did not hold within its bound. Only Redis connection,
    timeout and loading errors are waited out; any other error is a probe defect and propagates at once."""
    from redis.exceptions import BusyLoadingError, ConnectionError, ResponseError, TimeoutError

    started = time.monotonic()
    while time.monotonic() - started < timeout:
        context.check()
        try:
            if predicate():
                return round(time.monotonic() - started, 3)
        except (BusyLoadingError, ConnectionError, TimeoutError, OSError):
            pass  # a restarting or loading server
        except ResponseError as error:
            if "loading" not in str(error).lower():
                raise
        time.sleep(0.05)
    return None


def search_total(reply: Any) -> int:
    """FT.SEARCH's total under RESP3 (a map) or RESP2 (a list headed by the count)."""
    if isinstance(reply, dict):
        return int(reply["total_results"])
    return int(reply[0])


def _within(value: float | None, bound: float) -> bool | None:
    """Unknown when the measurement is missing; never a pass by default."""
    return None if value is None else value <= bound


def is_oom_refusal(error: BaseException) -> bool:
    """redis-py strips the OOM prefix and raises OutOfMemoryError; match that type, not message text."""
    from redis.exceptions import OutOfMemoryError

    return isinstance(error, OutOfMemoryError)


def _container_run_id(runner: Runner, context: ProbeContext, container: str, username: str | None, credential: str) -> str:
    argv = ["docker", "exec", "-e", "REDISCLI_AUTH", container, "redis-cli", "--no-auth-warning"]
    argv += ["--user", username] if username else []
    completed = runner([*argv, "INFO", "server"], context.timeout(60), {"REDISCLI_AUTH": credential} if credential else None)
    for line in completed.stdout.splitlines():
        if line.startswith("run_id:"):
            return line.split(":", 1)[1].strip()
    raise AdmissionError("could not read the run id inside the released container")


def _container_memory_bytes(runner: Runner, context: ProbeContext, container: str) -> int | None:
    completed = runner(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", container], context.timeout(30), None)
    text = completed.stdout.strip().split("/")[0].strip()
    units = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "kB": 1000, "MB": 1000**2, "GB": 1000**3}
    for unit in sorted(units, key=len, reverse=True):
        if completed.returncode == 0 and text.endswith(unit):
            try:
                return int(float(text[: -len(unit)]) * units[unit])
            except ValueError:
                return None
    return None


def _disk_bytes(runner: Runner, context: ProbeContext, container: str) -> int | None:
    completed = runner(["docker", "exec", container, "du", "-sb", "/data"], context.timeout(60), None)
    try:
        return int(completed.stdout.split()[0]) if completed.returncode == 0 else None
    except (IndexError, ValueError):
        return None


def marker_state(runner: Runner, context: ProbeContext, container: str, marker: str) -> str:
    """`present`, `absent` (grep inspected every file and found nothing) or `error` (inspection failed)."""
    completed = runner(["docker", "exec", container, "grep", "-rlF", marker, "/data"], context.timeout(60), None)
    if completed.returncode == 0 and completed.stdout.strip():
        return "present"
    if completed.returncode == 1 and not completed.stdout.strip() and not completed.stderr.strip():
        return "absent"
    return "error"


def wait_marker(runner: Runner, context: ProbeContext, container: str, marker: str, wanted: str,
                bound: float) -> tuple[float | None, bool]:
    """Seconds until the marker reached `wanted`, and whether any inspection failed on the way."""
    started, failed = time.monotonic(), False
    while time.monotonic() - started < bound:
        state = marker_state(runner, context, container, marker)
        failed |= state == "error"
        if state == wanted:
            return round(time.monotonic() - started, 3), failed
        time.sleep(0.5)
    return None, failed


def restart_and_reconcile(runner: Runner, context: ProbeContext, resource: Any, identity: dict[str, Any],
                          old_run_id: str | None, connect: Callable[[], Any], ready: Callable[[Any], bool],
                          bound: float) -> tuple[dict[str, Any], Any]:
    """Restart the same container, timed from before the command; it must succeed, come back under a new run
    ID and reconcile to the original container and volume. Returns observations and the new client."""
    started = time.monotonic()
    completed = runner(["docker", "restart", "--time", "30", resource.container], context.timeout(180), None)
    observations: dict[str, Any] = {"command_succeeded": completed.returncode == 0}
    client = connect() if completed.returncode == 0 else None
    usable = _wait(lambda: ready(client), bound * 4, context) if client is not None else None
    observations["usable_seconds"] = None if usable is None else round(time.monotonic() - started, 3)
    if client is not None and usable is not None:
        after = admit_redis_resource(resource, lambda name: docker_inspect(name, runner, context.timeout(60)))
        observations["same_container_and_volume"] = (after["container_id"], after["volume"]) == (
            identity["container_id"], identity["volume"])
        observations["run_id_changed"] = _info(client, "server").get("run_id") != old_run_id
    return observations, client


class _Sampler:
    """Peak container RAM, sampled in the background while persistence forks run."""

    def __init__(self, runner: Runner, context: ProbeContext, container: str) -> None:
        self.runner, self.context, self.container = runner, context, container
        self.peak, self.failures = 0, 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                value = _container_memory_bytes(self.runner, self.context, self.container)
            except Exception:  # a failed sample is counted, not hidden
                value = None
            if value is None:
                self.failures += 1
            else:
                self.peak = max(self.peak, value)
            self._stop.wait(0.5)

    def __enter__(self) -> _Sampler:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(35)


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
    identity = admit_redis_resource(resource, lambda name: docker_inspect(name, runner, context.timeout(60)))
    host, port, database = admit_redis_endpoint(resource)
    credential = os.environ.get(resource.credential_env or "", "") if resource.credential_env else ""
    if resource.credential_env and not credential:
        raise AdmissionError("the redis credential environment variable is not set")
    if credential:
        context.ram_only.add(credential)
    targets = config.targets["redis"]
    if client_factory is None:
        import redis

        def client_factory() -> Any:
            client = redis.Redis(host=host, port=port, db=database, username=resource.username, password=credential or None,
                                 socket_timeout=min(60.0, context.timeout(60)), socket_connect_timeout=10,
                                 decode_responses=True)
            context.on_cleanup("close a redis client", client.close)
            return client

    client = client_factory()
    obs: dict[str, Any] = result.observations  # filled as it goes, so an error keeps what was observed
    obs["identity"] = identity
    obs["protocol"] = getattr(client, "connection_pool", None) and client.connection_pool.connection_kwargs.get("protocol")
    server = _info(client, "server")
    version = tuple(int(part) for part in str(server.get("redis_version", "0.0")).split(".")[:2])
    if server.get("run_id") != _container_run_id(runner, context, resource.container, resource.username, credential):
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
        raise AdmissionError(f"released server does not match the probe config: {[k for k, v in preflight.items() if not v]}")

    items, dims, item_bytes = int(targets["items"]), int(targets["vector_dimensions"]), int(targets["item_bytes"])
    workers = int(targets["concurrency"])
    schema = ["SCHEMA", "$.id", "AS", "id", "TAG", "$.kind", "AS", "kind", "TAG", "$.vector", "AS", "vector", "VECTOR",
              "FLAT", "6", "TYPE", "FLOAT32", "DIM", str(dims), "DISTANCE_METRIC", "COSINE"]
    client.execute_command("FT.CREATE", INDEX, "ON", "JSON", "PREFIX", "1", ITEM, *schema)
    rng = random.Random(1207)

    def document(index: int) -> dict[str, Any]:
        text = f"p127-{index}-" + "x" * max(0, item_bytes - 16)
        return {"id": str(index), "kind": "memory", "text": text, "vector": [round(rng.random(), 6) for _ in range(dims)]}

    def found(conn: Any, index: int) -> bool:
        return search_total(conn.execute_command("FT.SEARCH", INDEX, f"@id:{{{index}}}", "NOCONTENT")) == 1

    def fully_indexed(conn: Any) -> bool:
        info = _ft_info(conn)
        return str(info.get("percent_indexed")) in {"1", "1.0"} and int(info.get("indexing", 1)) == 0

    # Acknowledged single writes: append then WAITAOF on the same connection, as the Gate would.
    acks, projections, errors, unprojected, unconfirmed = [], [], [], 0, 0
    lock = threading.Lock()
    ack_ids = list(range(workers * ACK_SAMPLES_PER_WORKER))
    docs = {index: document(index) for index in ack_ids}

    def ack_worker(ids: list[int]) -> None:
        nonlocal unconfirmed, unprojected
        try:
            own = client_factory()
            for index in ids:
                context.check()
                started = time.perf_counter()
                own.xadd(EVENTS, {"id": index, "v": 1})
                local, _ = own.execute_command("WAITAOF", 1, 0, WAITAOF_TIMEOUT_MS)
                acked = time.perf_counter()
                own.json().set(f"{ITEM}{index}", "$", docs[index])
                visible = _wait(lambda index=index: found(own, index), PROJECTION_WAIT_SECONDS, context)
                with lock:
                    acks.append((acked - started) * 1000)
                    unconfirmed += int(local) < 1
                    if visible is None:
                        unprojected += 1
                    else:
                        projections.append((time.perf_counter() - acked) * 1000)
        except Exception as error:  # surfaced after the join; a worker never fails silently
            with lock:
                errors.append(type(error).__name__)

    threads = [threading.Thread(target=ack_worker, args=(ack_ids[w::workers],), daemon=True) for w in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(context.timeout(context.config.timeout_seconds))
    if errors or any(thread.is_alive() for thread in threads):
        raise TimeoutError(f"acknowledgement workers did not finish cleanly: {sorted(set(errors)) or 'still running'}")
    docs.clear()
    obs["acknowledged_writes"] = {"count": len(acks), "unconfirmed": unconfirmed, "unprojected": unprojected,
                                  "ack_p50_ms": _pct(acks, 0.5), "ack_p95_ms": _p95(acks),
                                  "projection_p95_ms": _p95(projections), "appendfsync": settings["appendfsync"]}

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
    obs["index_ready_seconds"] = _wait(lambda: fully_indexed(client), 600, context)

    memory = _info(client, "memory")
    logical = int(memory["used_memory"]) - int(memory.get("mem_not_counted_for_evict", 0))
    obs["memory_after_load"] = {"used_memory": memory["used_memory"], "mem_not_counted_for_evict": memory.get("mem_not_counted_for_evict"),
                                "logical_bytes": logical, "num_docs": _ft_info(client).get("num_docs")}

    # Rebuild burst: drop the index (documents stay), recreate, wait for full indexing.
    client.execute_command("FT.DROPINDEX", INDEX)
    rebuild_started = time.perf_counter()
    client.execute_command("FT.CREATE", INDEX, "ON", "JSON", "PREFIX", "1", ITEM, *schema)
    obs["rebuild_ready_seconds"] = _wait(lambda: fully_indexed(client), 600, context)
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
    oom_refused: bool | None
    try:
        client.set("p127:oom-control", "o" * (4 * 1024 * 1024))
        oom_refused, oom_error = False, None
    except Exception as error:
        oom_refused, oom_error = (True if is_oom_refusal(error) else None), type(error).__name__
    finally:
        client.config_set("maxmemory", int(targets["maxmemory_bytes"]))
    obs["derived_growth"] = {"derived_keys": derived, "logical_before": before_growth, "logical_after": logical,
                             "bytes_per_derived_key": round((logical - before_growth) / derived, 1) if derived else None,
                             "reserve_ceiling": ceiling, "noeviction_refuses_write": oom_refused, "write_error": oom_error,
                             "no_keys_evicted": client.dbsize() == keys_before}

    # Persistence forks under load; physical RAM is sampled meanwhile, including copy-on-write peaks.
    slow_acks: list[float] = []
    with _Sampler(runner, context, resource.container) as sampler:
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
                          "ram_sample_failures": sampler.failures, "disk_bytes": _disk_bytes(runner, context, resource.container)}
    acked_events = client.xlen(EVENTS)
    obs["unconfirmed_total"] = unconfirmed

    # Restart: same container and volume; acknowledged writes must survive.
    def ready(conn: Any) -> bool:
        return bool(conn.ping()) and int(_info(conn, "persistence").get("loading", 1)) == 0 and found(conn, items - 1)

    restart, client = restart_and_reconcile(runner, context, resource, identity, server.get("run_id"), client_factory, ready,
                                            float(targets["restart_to_usable_seconds"]))
    if client is not None and restart.get("usable_seconds") is not None:
        restart["acknowledged_events_survived"] = client.xlen(EVENTS) >= acked_events
        restart["documents_survived"] = int(_ft_info(client).get("num_docs", 0)) >= items
    obs["restart"] = restart
    if client is None or restart.get("usable_seconds") is None:
        obs["checks"] = {"restart_within": False}
        result.outcome, result.disposition = "FAIL", "concluded"
        result.limitations.append("the server did not come back usable after restart; purge and erasure were not run")
        return

    # Logical purge, then the physical-erasure horizon for that payload across AOF and RDB files.
    marker = f"p127-erase-{uuid.uuid4().hex}"
    context.ram_only.add(marker)
    victim = items + 1000
    client.json().set(f"{ITEM}{victim}", "$", {"id": str(victim), "kind": "memory", "text": marker, "vector": [0.5] * dims})
    client.execute_command("WAITAOF", 1, 0, WAITAOF_TIMEOUT_MS)
    reached, reach_failed = wait_marker(runner, context, resource.container, marker, "present", 10)
    purge_started = time.monotonic()
    client.xadd(EVENTS, {"id": victim, "tombstone": 1})
    client.delete(f"{ITEM}{victim}")
    logical_purge = _wait(lambda: not found(client, victim), float(targets["logical_purge_seconds"]) * 10, context)
    client.execute_command("BGREWRITEAOF")
    _wait(lambda: int(_info(client, "persistence")["aof_rewrite_in_progress"]) == 0, 600, context)
    client.execute_command("BGSAVE")
    _wait(lambda: int(_info(client, "persistence")["rdb_bgsave_in_progress"]) == 0, 600, context)
    erased, erase_failed = wait_marker(runner, context, resource.container, marker, "absent",
                                       float(targets["physical_erasure_seconds"]) * 2)
    erasure_seconds = None if erased is None else round(time.monotonic() - purge_started, 3)
    obs["purge"] = {"marker_sha256": hashlib.sha256(marker.encode()).hexdigest(), "marker_reached_disk_seconds": reached,
                    "logical_purge_seconds": logical_purge, "physical_erasure_seconds": erasure_seconds,
                    "inspection_failed": reach_failed or erase_failed}

    checks: dict[str, bool | None] = {
        "no_unconfirmed_acknowledgements": obs["unconfirmed_total"] == 0,
        "all_acknowledged_writes_projected": unprojected == 0,
        "ack_p95_within": _within(obs["acknowledged_writes"]["ack_p95_ms"], targets["ack_latency_p95_ms"]),
        "projection_p95_within": _within(obs["acknowledged_writes"]["projection_p95_ms"], targets["projection_latency_p95_ms"]),
        "index_ready": obs["index_ready_seconds"] is not None and obs["rebuild_ready_seconds"] is not None,
        "logical_memory_below_reserve": logical <= ceiling,
        "physical_ram_within": _within(obs["persistence"]["physical_peak_bytes"], targets["physical_ram_bytes"]),
        "disk_within": _within(obs["persistence"]["disk_bytes"], targets["disk_bytes"]),
        "noeviction_refuses_write": None if oom_refused is None else oom_refused and obs["derived_growth"]["no_keys_evicted"],
        "persistence_ok": rewrite is not None and save is not None and persistence.get("aof_last_bgrewrite_status") == "ok"
        and persistence.get("rdb_last_bgsave_status") == "ok",
        "restart_command_succeeded": restart["command_succeeded"],
        "restart_within": restart["usable_seconds"] <= targets["restart_to_usable_seconds"],
        "restart_new_run_id": restart.get("run_id_changed"),
        "restart_same_container_and_volume": restart.get("same_container_and_volume"),
        "acknowledged_writes_survive_restart": restart.get("acknowledged_events_survived") and restart.get("documents_survived"),
        "marker_reached_disk": None if reached is None and reach_failed else reached is not None,
        "logical_purge_within": logical_purge is not None and logical_purge <= targets["logical_purge_seconds"],
        "physical_erasure_within": None if erase_failed else erasure_seconds is not None
        and erasure_seconds <= targets["physical_erasure_seconds"],
    }
    obs["checks"] = checks
    obs["targets"] = dict(targets)
    result.outcome, result.disposition = verdict(checks), "concluded"
    result.limitations += ["synthetic single-instance result; topology is provisional until M1 repeats K2 on the real corpus",
                           "a prototype append is not the production Gate, notice or erasure workflow (M3)"]
    result.follow_up = ("M1 repeats K2 on the real corpus with production adapters" if result.outcome == "PASS" else
                        "single instance did not meet its bounds: the two-instance fallback needs its own released run in M1")


def ft_info(reply: Any) -> dict[str, Any]:
    """FT.INFO under RESP3 (a map) or RESP2 (a flat key/value list)."""
    if isinstance(reply, dict):
        return {str(key): value for key, value in reply.items()}
    return {str(key): value for key, value in zip(reply[::2], reply[1::2], strict=False)}


def _ft_info(client: Any) -> dict[str, Any]:
    return ft_info(client.execute_command("FT.INFO", INDEX))
