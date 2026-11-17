"""Plan 12.11 K2 capacity measurement: `python -m tools.plan12_memory.m3_k2 --output reports/plan12-memory-m3/capacity-k2.json`.

Runs only against the released resources (operator release, 2026-11-17): the test memory store `p1211-memory-test-redis` and,
for the separate index load, `p1211-k2-index-redis` on 127.0.0.1:6397. Both are recreated here and left for CP2 close.
Measures, never tunes, and preserves misses: every acknowledged save is checked against this tool's own record of what it was
told (item, version, a digest of the statement), never against the store's view. Records carry counts, timings and digests.

Phases:
- main: four Gateways (four in-process stores with their own connections, one project each) write 100,000 events over 10,000
  live items against the production launch flags, while a synthetic index rebuild loads the second Redis. An observer Gateway
  times how long after an acknowledgement a read shows it. Then a purge per project (logical and disk step), then a kill and
  restart, timed to the first successful read, and the identity check again.
- slow: the same store recreated with its writes throttled (`--device-write-bps` on the volume's device), a shorter load.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import redis

from optimus.acp import local_infra
from optimus_gateway import memory_store
from tests.integration.memory.conftest import CONTAINER, Provisioned, docker, remove_released_resources, setup_config, wait_for_auth

INDEX_CONTAINER = "p1211-k2-index-redis"
INDEX_VOLUME = "p1211-k2-index-data"
INDEX_PORT = 6397
IMAGE = "redis@sha256:298e5b3bc566bade82f46ad5511777a4a07a294097ce16ada2f6a42be5239df5"
TARGETS = Path("reports/plan12-memory-m3/targets.json")
CLIENTS = 4


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(quantile * len(ordered)))]


def _summary(values: Sequence[float], scale: float = 1.0) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    return {"count": len(values), "p50": round(statistics.median(values) * scale, 2), "p95": round(_percentile(values, 0.95) * scale, 2),  # type: ignore[operator]
            "max": round(max(values) * scale, 2)}


def _digest(text: str) -> str:
    return "hex:" + hashlib.sha256(text.encode()).hexdigest()


class _Keyring:
    def __init__(self, password: str) -> None:
        self.password = password

    def get_password(self, _service: str, _name: str) -> str:
        return self.password


def _service(provisioned: Provisioned, journal: Path) -> memory_store.MemoryStoreService:
    return memory_store.build_memory_store_service(provisioned.config, keyring_backend=_Keyring(provisioned.password), hmac_key=b"k" * 32,
                                                   journal_root=journal)


def _call(service: memory_store.MemoryStoreService, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    return service.handle(json.dumps(body).encode(), deadline=time.monotonic() + 5)


def _event(item: str, version: int, statement: str) -> dict[str, Any]:
    return {"event_id": f"e-{item[-8:]}-{version}", "item": item, "version": version, "action": "admit" if version == 1 else "update",
            "trust": "user-authored", "status": "active", "kind": "preference", "scope": "s-k2", "title": f"k2 {item[-6:]}",
            "statement": statement, "anchors": [], "lineage": [], "valid_from_ms": 0, "valid_until_ms": 0}


@contextmanager
def _throttled(device_flags: Sequence[str]) -> Iterator[None]:
    """Add docker-run flags to the released store's own launch, so the launch's settings check still applies to it."""
    if not device_flags:
        yield
        return
    plain = subprocess.run

    def run(argv: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(argv, list) and argv[1:3] == ["run", "-d"] and CONTAINER in argv:
            argv = [argv[0], "run", "-d", *device_flags, *argv[3:]]
        return plain(argv, *args, **kwargs)

    local_infra.subprocess.run = run  # type: ignore[assignment]
    try:
        yield
    finally:
        local_infra.subprocess.run = plain  # type: ignore[assignment]


def _provision(work: Path) -> Provisioned:
    remove_released_resources()
    root, config, password = setup_config(work / "store")
    status = local_infra.ensure_memory_store_redis(root)
    assert status.state == "ready", status
    provisioned = Provisioned(root, config, password)
    wait_for_auth(provisioned)
    return provisioned


def _index_redis() -> redis.Redis:
    docker("rm", "-f", INDEX_CONTAINER)
    docker("volume", "rm", "-f", INDEX_VOLUME)
    docker("run", "-d", "--name", INDEX_CONTAINER, "--restart", "no", "-p", f"127.0.0.1:{INDEX_PORT}:6379", "--memory", "1024m",
           "-v", f"{INDEX_VOLUME}:/data", IMAGE, "redis-server", "--appendonly", "yes", "--appendfsync", "everysec",
           "--maxmemory", "768mb", "--maxmemory-policy", "noeviction", check=True)
    client = redis.Redis(host="127.0.0.1", port=INDEX_PORT, socket_timeout=10)
    deadline = time.monotonic() + 30
    while True:
        try:
            client.ping()
            return client
        except redis.RedisError:
            assert time.monotonic() < deadline
            time.sleep(0.5)


def _index_load(client: redis.Redis, stop: threading.Event, out: dict[str, Any]) -> None:
    """A rebuild's shape: batches of 128 records with a 384-float vector each, the whole set replaced generation after generation,
    with a snapshot after each. Synthetic: it stands for an index rebuild's CPU, memory and disk on a separate Redis."""
    rng = random.Random(1211)
    vector = bytes(rng.getrandbits(8) for _ in range(384 * 4))
    generation = records = 0
    while not stop.is_set():
        pipe = client.pipeline(transaction=False)
        for number in range(128):
            pipe.hset(f"k2idx:{generation % 2}:{records % 40000}", mapping={"terms": f"word{number} scale", "vector": vector})
            records += 1
        pipe.execute()
        if records % 40000 < 128:
            client.delete(*[f"k2idx:{(generation + 1) % 2}:{n}" for n in range(1000)])  # the old generation's first page
            generation += 1
            try:
                client.bgsave()
            except redis.ResponseError:
                pass
    out.update(records=records, generations=generation)


def _container_ram_mib(container: str) -> float | None:
    text = docker("stats", "--no-stream", "--format", "{{.MemUsage}}", container).stdout.strip().split("/")[0].strip()
    for unit, scale in (("GiB", 1024.0), ("MiB", 1.0), ("KiB", 1 / 1024)):
        if text.endswith(unit):
            return round(float(text[: -len(unit)]) * scale, 1)
    return None


def _disk_kib(container: str) -> int | None:
    text = docker("exec", container, "sh", "-c", "du -sk /data | cut -f1").stdout.strip()
    return int(text) if text.isdigit() else None


def _sampler(provisioned: Provisioned, stop: threading.Event, out: dict[str, Any]) -> None:
    client = provisioned.connect()
    peaks = {"container_ram_mib": 0.0, "used_memory_rss_mib": 0.0, "disk_kib": 0, "aof_last_cow_mib": 0.0, "rdb_last_cow_mib": 0.0}
    samples = 0
    while not stop.wait(2.0):
        try:
            memory, persistence = client.info("memory"), client.info("persistence")
        except redis.RedisError:
            continue  # the store is down for the restart phase
        samples += 1
        peaks["used_memory_rss_mib"] = max(peaks["used_memory_rss_mib"], memory["used_memory_rss"] / 1048576)
        peaks["aof_last_cow_mib"] = max(peaks["aof_last_cow_mib"], persistence.get("aof_last_cow_size", 0) / 1048576)
        peaks["rdb_last_cow_mib"] = max(peaks["rdb_last_cow_mib"], persistence.get("rdb_last_cow_size", 0) / 1048576)
        peaks["container_ram_mib"] = max(peaks["container_ram_mib"], _container_ram_mib(CONTAINER) or 0.0)
        peaks["disk_kib"] = max(peaks["disk_kib"], _disk_kib(CONTAINER) or 0)
    out.update({name: round(value, 1) for name, value in peaks.items()}, samples=samples)


def _write_load(provisioned: Provisioned, work: Path, *, events: int, items: int, observe_every: int) -> dict[str, Any]:
    """CLIENTS Gateways, one project each, each writing events/CLIENTS events round-robin over items/CLIENTS items."""
    services = [_service(provisioned, work / f"journal-{n}") for n in range(CLIENTS)]
    observer = _service(provisioned, work / "journal-observer")
    projects = [f"p-k2-{n}" for n in range(CLIENTS)]
    expected: list[dict[str, tuple[int, str]]] = [{} for _ in range(CLIENTS)]
    acks: list[float] = []
    projection: list[float] = []
    refusals: dict[str, int] = {}
    unconfirmed: list[tuple[int, str, dict[str, Any], int]] = []
    lock = threading.Lock()

    def client(n: int) -> None:
        service, project = services[n], projects[n]
        code, reply = _call(service, {"op": "lease", "project": project, "owner": f"k2-{n}", "action": "acquire", "ttl_ms": 300_000})
        if code != 200:  # the first request of a fresh Gateway verifies the store; four at once may find it busy
            code, reply = _call(service, {"op": "lease", "project": project, "owner": f"k2-{n}", "action": "acquire", "ttl_ms": 300_000})
        assert code == 200, (n, reply)
        token = reply["token"]
        per_items = items // CLIENTS
        for number in range(events // CLIENTS):
            if number and number % 2000 == 0:
                _call(service, {"op": "lease", "project": project, "owner": f"k2-{n}", "action": "renew", "ttl_ms": 300_000, "token": token})
            item = f"m-{n:04x}{number % per_items:012x}"
            version = expected[n].get(item, (0, ""))[0] + 1
            statement = f"k2 client {n} item {number % per_items} version {version}"
            key = hashlib.sha256(f"{project}:{item}:{version}".encode()).hexdigest()
            body = {"op": "append", "project": project, "token": token, "expected_version": version - 1, "idempotency_key": key,
                    "event": _event(item, version, statement)}
            started = time.perf_counter()
            code, reply = _call(service, body)
            elapsed = time.perf_counter() - started
            if code == 200 and reply.get("durable_state") == "confirmed":
                expected[n][item] = (version, _digest(statement))
                with lock:
                    acks.append(elapsed)
                if number % observe_every == 0:
                    seen_at = time.perf_counter()
                    while True:
                        current = _call(observer, {"op": "read", "project": project, "item": item})[1].get("item")
                        if current and current["version"] >= version:
                            break
                        if time.perf_counter() - seen_at > 10:
                            break
                        time.sleep(0.005)
                    with lock:
                        projection.append(time.perf_counter() - seen_at)
            else:
                reason = reply.get("error") or f"durable_state={reply.get('durable_state')}"
                with lock:
                    refusals[reason] = refusals.get(reason, 0) + 1
                    unconfirmed.append((n, key, body, version))
                if code == 200:  # written but not proven: the retry below reconciles it, as a host would
                    expected[n][item] = (version, _digest(statement))

    started = time.perf_counter()
    threads = [threading.Thread(target=client, args=(n,)) for n in range(CLIENTS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    seconds = time.perf_counter() - started
    retried = sum(1 for n, _key, body, _v in unconfirmed if _call(services[n], body)[1].get("durable_state") == "confirmed")
    return {"services": services, "projects": projects, "expected": expected, "seconds": round(seconds, 1),
            "ack_ms": _summary(acks, 1000), "projection_after_ack_ms": _summary(projection, 1000), "refusals": refusals,
            "unconfirmed": len(unconfirmed), "unconfirmed_retried_confirmed": retried,
            "events_acknowledged": len(acks) + retried}


def _identity_check(provisioned: Provisioned, work: Path, projects: Sequence[str], expected: Sequence[dict[str, tuple[int, str]]],
                    label: str) -> dict[str, Any]:
    """A fresh Gateway lists every item and compares it with what this tool was told; every difference is reported."""
    fresh = _service(provisioned, work / f"journal-check-{label}")
    misses = wrong = 0
    for project, wanted in zip(projects, expected, strict=True):
        seen: dict[str, tuple[int, str]] = {}
        cursor = None
        while True:
            body = {"op": "list", "project": project, "scope": "s-k2", "limit": 100, **({"cursor": cursor} if cursor else {})}
            code, reply = _call(fresh, body)
            if code != 200:
                code, reply = _call(fresh, body)  # the first request after a restart is refused while the store re-verifies
            assert code == 200, reply
            for record in reply["items"]:
                seen[record["item"]] = (record["version"], _digest(record["statement"]) if record["status"] != "purged" else "purged")
            cursor = reply["cursor"]
            if cursor is None:
                break
        for item, (version, digest) in wanted.items():
            got = seen.get(item)
            if got is None:
                misses += 1
            elif got != (version, digest) and got[1] != "purged":
                wrong += 1
    return {"items_expected": sum(len(w) for w in expected), "missing": misses, "wrong": wrong}


def _purges(services: Sequence[memory_store.MemoryStoreService], projects: Sequence[str],
            expected: Sequence[dict[str, tuple[int, str]]]) -> dict[str, Any]:
    logical: list[float] = []
    physical: list[float] = []
    for n, (service, project) in enumerate(zip(services, projects, strict=True)):
        token = _call(service, {"op": "lease", "project": project, "owner": f"k2-{n}", "action": "acquire", "ttl_ms": 300_000})[1]["token"]
        item = next(iter(expected[n]))
        started = time.perf_counter()
        code, reply = _call(service, {"op": "purge", "project": project, "token": token, "item": item, "idempotency_key": "f" * 63 + str(n)})
        assert code == 200 and reply["durable_state"] == "confirmed", reply
        logical.append(time.perf_counter() - started)
        while _call(service, {"op": "purge_status", "project": project, "item": item})[1].get("purge_state") != memory_store.PURGE_COMPLETED:
            if time.perf_counter() - started > 600:
                break
            time.sleep(0.25)
        physical.append(time.perf_counter() - started)
        expected[n].pop(item)
    return {"logical_s": _summary(logical), "rewrite_and_snapshot_s": _summary(physical)}


def _restart(provisioned: Provisioned, work: Path, project: str, item: str) -> float:
    docker("kill", CONTAINER, check=True)
    started = time.perf_counter()
    status = local_infra.ensure_memory_store_redis(provisioned.root)
    assert status.state == "ready", status
    fresh = _service(provisioned, work / "journal-restart")
    while True:
        code, reply = _call(fresh, {"op": "read", "project": project, "item": item})
        if code == 200 and reply.get("item"):
            return time.perf_counter() - started
        if time.perf_counter() - started > 300:
            return float("inf")
        time.sleep(0.2)


def run(output: Path, *, events: int, items: int, slow_events: int, slow_bps: str) -> dict[str, Any]:
    targets = json.loads(TARGETS.read_text(encoding="utf-8"))["k2"]
    work = Path(tempfile.mkdtemp(prefix="p1211-k2-", dir=Path.cwd() / "tmp"))
    report: dict[str, Any] = {"schema": "plan12-memory-m3.capacity-k2.v1", "targets": targets, "clients": CLIENTS,
                              "release": "operator 2026-11-17 'Release both' on #490", "loss_scope": targets["loss_scope"],
                              "source": {"head": "git:" + _git("rev-parse", "HEAD"), "dirty": bool(_git("status", "--porcelain"))}}

    provisioned = _provision(work / "main")
    index = _index_redis()
    stop = threading.Event()
    index_out: dict[str, Any] = {}
    sample_out: dict[str, Any] = {}
    background = [threading.Thread(target=_index_load, args=(index, stop, index_out)), threading.Thread(target=_sampler, args=(provisioned, stop, sample_out))]
    for thread in background:
        thread.start()
    try:
        load = _write_load(provisioned, work, events=events, items=items, observe_every=50)
        after_load = _identity_check(provisioned, work, load["projects"], load["expected"], "load")
        purges = _purges(load["services"], load["projects"], load["expected"])
        restart_s = _restart(provisioned, work, load["projects"][0], next(iter(load["expected"][0])))
        after_restart = _identity_check(provisioned, work, load["projects"], load["expected"], "restart")
    finally:
        stop.set()
        for thread in background:
            thread.join()
    report["main"] = {key: value for key, value in load.items() if key not in ("services", "projects", "expected")}
    report["main"].update(identity_after_load=after_load, identity_after_restart=after_restart, purge=purges,
                          restart_to_usable_s=round(restart_s, 1), resources=sample_out, index_load=index_out)

    device = docker("exec", CONTAINER, "sh", "-c", "grep ' /data ' /proc/mounts | cut -d' ' -f1").stdout.strip()
    with _throttled(["--device-write-bps", f"{device}:{slow_bps}"]):
        slow = _provision(work / "slow")
        slow_load = _write_load(slow, work / "slow-journals", events=slow_events, items=min(items, slow_events // 2), observe_every=25)
        slow_identity = _identity_check(slow, work, slow_load["projects"], slow_load["expected"], "slow")
    report["slow_persistence"] = {"device_write_bps": f"{device}:{slow_bps}", "events": slow_events,
                                  **{key: value for key, value in slow_load.items() if key not in ("services", "projects", "expected")},
                                  "identity": slow_identity}

    main = report["main"]
    report["verdicts"] = {
        "events": main["events_acknowledged"] >= targets["events"],
        "ack_p95": (main["ack_ms"].get("p95") or 1e9) <= targets["ack_p95_s"] * 1000,
        "projection_after_ack_p95": (main["projection_after_ack_ms"].get("p95") or 1e9) <= targets["projection_after_ack_p95_ms"],
        "restart_to_usable": main["restart_to_usable_s"] <= targets["restart_to_usable_s"],
        "logical_purge": (purges["logical_s"].get("max") or 1e9) <= targets["logical_purge_after_confirmed_tombstone_s"],
        "rewrite_and_snapshot": (purges["rewrite_and_snapshot_s"].get("max") or 1e9) <= targets["rewrite_and_snapshot_s"],
        "physical_ram": max(sample_out.get("container_ram_mib", 1e9), sample_out.get("used_memory_rss_mib", 1e9)) <= targets["physical_ram_gib"] * 1024,
        "peak_disk": sample_out.get("disk_kib", 1e12) <= targets["peak_persistence_disk_gib"] * 1024 * 1024,
        "acknowledged_write_loss": after_load["missing"] + after_load["wrong"] + after_restart["missing"] + after_restart["wrong"] == targets["acknowledged_write_loss"],
        "slow_persistence_loss": slow_identity["missing"] + slow_identity["wrong"] == 0,
    }
    report["passed"] = all(report["verdicts"].values())
    output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="m3_k2")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--events", type=int, default=100_000)
    parser.add_argument("--items", type=int, default=10_000)
    parser.add_argument("--slow-events", type=int, default=4_000)
    parser.add_argument("--slow-bps", default="256kb")  # below what a few hundred small fsyncs a second need
    args = parser.parse_args(argv)
    if not os.environ.get("P1211_MEMORY_DOCKER_RELEASED"):
        print("UNRUN: P1211_MEMORY_DOCKER_RELEASED is not set; no Docker command ran")
        return 2
    report = run(args.output, events=args.events, items=args.items, slow_events=args.slow_events, slow_bps=args.slow_bps)
    print(json.dumps({"passed": report["passed"], "verdicts": report["verdicts"]}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
