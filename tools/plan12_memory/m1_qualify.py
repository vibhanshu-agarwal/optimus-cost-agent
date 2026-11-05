"""Plan 12.10 M1 qualification and the second K2: `python -m tools.plan12_memory.m1_scale --phase qualify --config reports/plan12-memory-m1/run-config-qualify.json`.

This repository and the approved large corpus, through the real route on the released Redis, then K2 on those same real records. Measures and
reports against targets.json and never tunes; a failed bound stays in the report. The report is rewritten after each stage, so a stopped run still
shows what it measured. Assembly on the large corpus is labelled calibration here, because its limits are approved from it and qualified on a later
run. No generative or provider call is possible: the Gateway's upstream is an unroutable local address. Records carry counts, timings and hashes.
"""

from __future__ import annotations

import hashlib
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

_K2_USER = "k2-admin"
# The approved scope leaves test Java out, by the sample's rule, with an ignore file in the corpus (scale.json approved_corpus).
_TEST_RULE = "**/test/\n**/tests/\n**/Test*\n**/*Test.java\n**/*Tests.java\n"
_LARGE_TASKS = (
    "how does the namenode decide where to place a new block",
    "where does the resource manager schedule a container and what happens when a node is lost",
    "explain how a failed block write is recovered in the client pipeline",
    "where are delegation tokens renewed and cancelled",
)


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
        shutil.rmtree(target, onexc=scale._clear_read_only)
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


class _Canaries:
    """Four clients, each with its own index line through the real route. One canary: a durable append acknowledged by WAITAOF, as a memory Gate
    would, then the record through the route until a query finds it. A prototype append is not the production Gate (M3)."""

    def __init__(self, settings: Any, embedding: str, admin: redis.Redis, dimensions: int) -> None:
        self._settings, self._embedding, self._admin, self._dimensions = settings, embedding, admin, dimensions
        self._events = "oidx:k2:events"
        self._sequence = 0
        self._lock = threading.Lock()

    def _number(self) -> int:
        with self._lock:
            self._sequence += 1
            return self._sequence

    def _record(self, number: int) -> dict[str, Any]:
        digest = hashlib.sha256(f"canary{number}".encode()).hexdigest()
        vector = mic.encode_vector(struct.pack(f"<{self._dimensions}f", *([0.1] * self._dimensions)))
        return {"id": digest, "kind": "symbol", "path": f"k2/c{number}.py", "path_id": hashlib.sha256(f"c{number}".encode()).hexdigest(), "file_hash": "0" * 64, "language": "python",
                "symbol": f"canary_{number}", "signature": f"def canary_{number}()", "description": "function in a canary file", "terms": f"canary{number} k2canary", "vector": vector}

    def _client(self, client_number: int, rounds: int, pause: float, out: dict[str, Any]) -> None:
        registration = ProjectRegistration(f"k2-{client_number}", 1, f"git:k2-{client_number}", f"k2/{client_number}", created=False)
        storage = GatewayIndexStorage(self._settings, scope=index_scope(registration, branch="k2", embedding=self._embedding, parser_version="k2"))
        owner = f"k2owner{client_number}"
        admin = self._admin
        token = storage.call("lease", action="acquire", owner=owner, ttl_ms=60000, kind="scope")["token"]
        coverage = {"complete": True, "files_indexed": 1, "files_total": 1}
        for _ in range(rounds):
            number = self._number()
            try:
                started = time.perf_counter()
                admin.xadd(self._events, {"id": number})
                local, _replicas = admin.execute_command("WAITAOF", 1, 0, 5000)
                acked = time.perf_counter()
                epoch = storage.call("generation", action="begin", token=token)["epoch"]
                storage.call("batch", token=token, epoch=epoch, records=[self._record(number)])
                storage.call("generation", action="publish", token=token, epoch=epoch, revision=f"r{number}", dirty=False, coverage=coverage)
                seen = False
                while time.perf_counter() - acked < 10 and not seen:
                    seen = bool(storage.call("query", mode="lexical", terms=[f"canary{number}"], k=1)["records"])
                with self._lock:
                    out["acks"].append((acked - started) * 1000)
                    out["projections"].append((time.perf_counter() - acked) * 1000)
                    out["unconfirmed"] += int(local) < 1
                    out["lost"] += not seen
            except Exception as error:  # noqa: BLE001 - counted by kind and kept in the report; this is the measure
                name = getattr(error, "code", type(error).__name__)
                with self._lock:
                    out["errors"][name] = out["errors"].get(name, 0) + 1
            if pause:
                time.sleep(pause)
        storage.call("lease", action="release", owner=owner, kind="scope", token=token)

    def run(self, *, rounds: int, pause: float, during: Callable[[], None] | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {"acks": [], "projections": [], "unconfirmed": 0, "lost": 0, "errors": {}}
        threads = [threading.Thread(target=self._client, args=(number, rounds, pause, out), daemon=True) for number in range(4)]
        for thread in threads:
            thread.start()
        if during is not None:
            during()
        for thread in threads:
            thread.join(900)
        return {"count": len(out["acks"]), "ack_p50_ms": scale._percentile(out["acks"], 0.5), "ack_p95_ms": _p95(out["acks"]), "projection_p50_ms": scale._percentile(out["projections"], 0.5), "projection_p95_ms": _p95(out["projections"]),
                "unconfirmed": out["unconfirmed"], "lost": out["lost"], "errors": out["errors"], "unfinished_clients": sum(thread.is_alive() for thread in threads)}

    def events(self) -> int:
        return int(self._admin.xlen(self._events))


def _wait_flag(admin: redis.Redis, flag: str, seconds: float = 900) -> float | None:
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        if int(admin.info("persistence")[flag]) == 0:
            return round(time.monotonic() - started, 3)
        time.sleep(0.25)
    return None


def _peak_memory_mb(container: str) -> float | None:
    """The container's own peak, which sampling would miss. cgroup v2 keeps it in memory.peak."""
    result = subprocess.run(["docker", "exec", container, "cat", "/sys/fs/cgroup/memory.peak"], capture_output=True, text=True, check=False)
    return round(int(result.stdout) / 1048576, 1) if result.stdout.strip().isdigit() else None


def _marker_state(container: str, marker: str) -> str:
    result = subprocess.run(["docker", "exec", container, "grep", "-rlF", marker, "/data"], capture_output=True, text=True, check=False)
    if result.returncode == 0 and result.stdout.strip():
        return "present"
    return "absent" if result.returncode == 1 and not result.stderr.strip() else "error"


def _admin_client(memory: Any, password: str) -> redis.Redis:
    return redis.Redis(host="127.0.0.1", port=memory.port, username=_K2_USER, password=password, socket_timeout=30, socket_connect_timeout=10)


def _reachable(call: Callable[[], Any], seconds: float) -> float | None:
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        try:
            call()
            return round(time.monotonic() - started, 3)
        except Exception:  # noqa: BLE001 - measuring when it comes back
            time.sleep(0.2)
    return None


def run_k2(*, targets: Mapping[str, Any], config: Mapping[str, Any], memory: Any, admin_password: str, settings: Any, indexes: Mapping[str, Any], real_records: int, write: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    container = config["container"]
    admin = _admin_client(memory, admin_password)
    canaries = _Canaries(settings, indexes["large"].embedder.identity, admin, memory.embedding.dimensions)
    bounds = targets["k2_second_run"]
    fixed = bounds["unchanged_from_the_first_probe"]
    report: dict[str, Any] = {"schema": "plan12-memory-m1.k2.v1", "real_records_indexed": real_records, "items_target": bounds["items"], "bounds": bounds,
                              "limits": ["A prototype append is not the production Gate, notice or erasure workflow, which are M3's.", "One instance: the topology stays provisional if a bound fails.",
                                         f"The user {_K2_USER} exists for this run only, for WAITAOF, rewrites and memory changes; the index itself ran as its least-privilege user."]}
    rounds = config["k2_rounds"]
    report["nominal"] = canaries.run(rounds=rounds, pause=0.05)
    write(report)
    report["burst"] = canaries.run(rounds=rounds, pause=0)
    write(report)

    def rewrite() -> None:
        admin.bgrewriteaof()
    report["during_aof_rewrite"] = canaries.run(rounds=rounds, pause=0, during=rewrite)
    report["during_aof_rewrite"]["rewrite_seconds"] = _wait_flag(admin, "aof_rewrite_in_progress")
    admin.bgsave()
    report["rdb_save_seconds"] = _wait_flag(admin, "rdb_bgsave_in_progress")
    write(report)

    # Slower persistence than production's: every write is synced. The disk itself cannot be throttled from here.
    admin.config_set("appendfsync", "always")
    try:
        report["slow_persistence_appendfsync_always"] = canaries.run(rounds=rounds, pause=0)
    finally:
        admin.config_set("appendfsync", "everysec")
    write(report)

    # Noeviction: at the ceiling writes are refused, nothing is evicted, and everything still answers once there is room.
    before_keys = admin.dbsize()
    used = int(admin.info("memory")["used_memory"])
    admin.config_set("maxmemory", used + 1024 * 1024)
    refused: list[str] = []
    try:
        filler = "x" * 1_000_000
        for number in range(32):
            try:
                admin.set(f"oidx:k2:fill{number}", filler)
            except redis.ResponseError as error:
                refused.append(str(error).split(" ", 1)[0])
                break
    finally:
        admin.config_set("maxmemory", memory.maxmemory_mb * 1024 * 1024)
        for number in range(32):
            admin.delete(f"oidx:k2:fill{number}")
    query = lambda: indexes["large"].storage.call("query", mode="lexical", terms=["block"], k=5)  # noqa: E731
    report["noeviction"] = {"write_refused": bool(refused), "reason": refused[:1], "no_keys_evicted": admin.dbsize() >= before_keys, "answers_after": bool(query()["records"])}
    write(report)

    # Restart: same container and volume, the same publication, and acknowledged appends all there.
    published = indexes["large"].storage.call("coverage")["current"]
    acknowledged = canaries.events()
    subprocess.run(["docker", "restart", container], capture_output=True, check=True)
    usable = _reachable(lambda: query()["records"] or 1 / 0, 300)
    admin = _admin_client(memory, admin_password)
    report["restart"] = {"seconds_until_usable": usable, "same_publication": indexes["large"].storage.call("coverage")["current"] == published, "acknowledged_appends_survived": canaries_after(admin) >= acknowledged, "within": within(usable, fixed["restart_to_usable_seconds"])}
    write(report)

    # Crash: killed, started by the real lifecycle. Everything WAITAOF acknowledged must survive; the worker repairs the index, and coverage stays honest.
    canaries = _Canaries(settings, indexes["large"].embedder.identity, admin, memory.embedding.dimensions)
    canaries.run(rounds=5, pause=0)
    acknowledged = canaries_after(admin)
    subprocess.run(["docker", "kill", container], capture_output=True, check=True)
    status = local_infra.ensure_memory_redis(memory_index_root(Path(config["_config_root"])))
    usable = _reachable(lambda: query()["records"] or 1 / 0, 300)
    admin = _admin_client(memory, admin_password)
    started = time.perf_counter()
    repaired = indexes["large"].worker().run(threading.Event())
    report["crash"] = {"ensure_state": status.state, "seconds_until_usable": usable, "same_publication": indexes["large"].storage.call("coverage")["current"]["epoch"] == published["epoch"], "acknowledged_appends_survived": canaries_after(admin) >= acknowledged,
                       "worker_after": repaired.state, "worker_seconds": round(time.perf_counter() - started, 1), "within": within(usable, fixed["restart_to_usable_seconds"])}
    write(report)

    # Logical purge, then physical erasure of one distinctive record across AOF and RDB.
    marker = f"k2erase{secrets.token_hex(12)}"
    registration = ProjectRegistration("k2-purge", 1, "git:k2-purge", "k2/purge", created=False)
    storage = GatewayIndexStorage(settings, scope=index_scope(registration, branch="k2", embedding=indexes["large"].embedder.identity, parser_version="k2"))
    token = storage.call("lease", action="acquire", owner="k2purge", ttl_ms=60000, kind="scope")["token"]
    epoch = storage.call("generation", action="begin", token=token)["epoch"]
    vector = mic.encode_vector(struct.pack(f"<{memory.embedding.dimensions}f", *([0.1] * memory.embedding.dimensions)))
    storage.call("batch", token=token, epoch=epoch, records=[{"id": hashlib.sha256(marker.encode()).hexdigest(), "kind": "symbol", "path": "k2/p.py", "path_id": hashlib.sha256(b"p").hexdigest(), "file_hash": "0" * 64, "language": "python",
                                                              "symbol": marker, "signature": f"def {marker}()", "description": "function in a canary file", "terms": marker, "vector": vector}])
    storage.call("generation", action="publish", token=token, epoch=epoch, revision="r", dirty=False, coverage={"complete": True, "files_indexed": 1, "files_total": 1})
    admin.execute_command("WAITAOF", 1, 0, 5000)
    reached = _marker_state(container, marker)
    purge_started = time.monotonic()
    cursor = None
    while True:
        reply = storage.call("cleanup", action="drop", token=token, **({} if cursor is None else {"cursor": cursor}))
        cursor = reply.get("cursor")
        if cursor is None:
            break
    logical = round(time.monotonic() - purge_started, 3)
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
    report["purge"] = {"marker_sha256": f"hex:{hashlib.sha256(marker.encode()).hexdigest()}", "reached_disk_before_purge": reached, "logical_purge_seconds": logical, "physical_erasure_seconds": erased,
                       "logical_within": within(logical, fixed["logical_purge_seconds"]), "physical_within": within(erased, fixed["physical_erasure_seconds"])}
    facts = scale._redis_facts(redis.Redis(host="127.0.0.1", port=memory.port, username=_K2_USER, password=admin_password), container)
    peak = _peak_memory_mb(container)
    report["resources"] = {**facts, "container_peak_mb": peak, "used_within_limit": within(facts["used_memory_peak_mb"], bounds["maxmemory_mb"] - bounds["reserve"]["mb"]), "physical_within": within(peak, bounds["physical_ram_mb"]["limit"]), "disk_within": within((facts["disk_kb"] or 0) / 1024, bounds["disk_mb"])}
    nominal = report["nominal"]
    report["checks"] = {"items_at_least_target": real_records >= bounds["items"], "no_busy_at_nominal": "INDEX_BUSY" not in nominal["errors"], "no_errors_at_nominal": not nominal["errors"], "no_lost_at_nominal": nominal["lost"] == 0, "no_unconfirmed_at_nominal": nominal["unconfirmed"] == 0,
                        "ack_p95_within": within(nominal["ack_p95_ms"], fixed["ack_latency_p95_ms"]), "projection_p95_within": within(nominal["projection_p95_ms"], fixed["projection_latency_p95_ms"])}
    write(report)
    return report


def canaries_after(admin: redis.Redis) -> int:
    return int(admin.xlen("oidx:k2:events"))


def _calibrate_assembly(root: Path, settings: Any, embedder: Any, work: Path, *, project: str, parser_version: str) -> dict[str, Any]:
    """Labelled calibration: the operator approves large-corpus limits from this and they are qualified on a later run, never this one."""
    me = threading.get_ident()
    counters: list[scale._CountingStorage] = []

    def storage_for(scope: str) -> scale._CountingStorage:
        counters.append(scale._CountingStorage(GatewayIndexStorage(settings, scope=scope), me))
        return counters[-1]

    session = MemorySession(policy=FilePolicy(root), registration=ProjectRegistration(project, 1, f"git:{project}", str(root), created=False), storage_for=storage_for, embedder_for=lambda: embedder,
                            embedding_identity=embedder.identity, parser_version=parser_version, manifest_root=work / "manifests")
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
        idle = [scale._measure_turn(session, counters, task, f"cal-{round_}-{number}") for round_ in range(5) for number, task in enumerate(_LARGE_TASKS)]
        return {"state": "CALIBRATION: never a qualification result", "repo_map_on_a_miss": refresh, "idle": {**scale._assembly_summary(idle), "per_task": idle[-len(_LARGE_TASKS):]}, "coverage": session.status()}
    finally:
        session.close()


def _built_with_samples(index: scale._Index, foreground: scale._Index, store: memory_index.IndexStore, *, config: Mapping[str, Any], pids: dict[str, int], turns: Any) -> dict[str, Any]:
    """The cold build under its limit, with foreground work on the finished line while it runs: what a person's turn meets."""
    cancel = threading.Event()
    real_call = index.storage.call
    first_publish: list[float] = []

    def watching(op: str, **fields: Any) -> dict[str, Any]:
        reply = real_call(op, **fields)
        if op == "generation" and fields.get("action") == "publish" and not first_publish:
            first_publish.append(time.perf_counter())
        return reply

    index.storage.call = watching  # type: ignore[method-assign]
    done: list[Any] = []
    started = time.perf_counter()
    build = threading.Thread(target=lambda: done.append(index.worker().run(cancel)), daemon=True)
    limit = config["hours_limit"] * 3600
    vector = mic.encode_vector(foreground.embedder.embed(["measure a query vector for this repository"])[0])
    terms = ["gateway", "redis", "context", "policy", "server", "approval", "token", "manifest"]
    samples: list[dict[str, Any]] = []
    turn_samples: list[dict[str, Any]] = []
    with scale._Sampler(pids) as sampler:
        build.start()
        next_sample = time.monotonic() + 60
        while build.is_alive():
            if time.perf_counter() - started > limit:
                cancel.set()
                break
            if time.monotonic() >= next_sample:
                samples.append({"at_seconds": round(time.perf_counter() - started), **scale._query_load(foreground, store, samples=config["query_samples"], terms=terms, vector=vector)})
                if turns is not None and len(turn_samples) < 1:
                    turn_samples.append({"at_seconds": round(time.perf_counter() - started), "turns": turns.turns(config["acpx_turns"]), "cancel": turns.cancel_during_a_turn()})
                next_sample = time.monotonic() + config["foreground_sample_seconds"]
            time.sleep(1)
        build.join(120)
    index.storage.call = real_call  # type: ignore[method-assign]
    seconds = time.perf_counter() - started
    outcome = done[0] if done else None
    return {"state": getattr(outcome, "state", "no-result"), "detail": getattr(outcome, "detail", None), "hours": round(seconds / 3600, 3), "within_the_hours_limit": seconds <= limit, "seconds": round(seconds, 1), "files_written": getattr(outcome, "files_written", None), "records_written": getattr(outcome, "records_written", None),
            "coverage": getattr(outcome, "coverage", None), "first_file_visible_seconds": round(first_publish[0] - started, 2) if first_publish else None, "processes": sampler.report(), "foreground_during_build": samples, "acpx_during_build": turn_samples}


def run_qualify(config: dict[str, Any], repository: Path) -> dict[str, Any]:
    work = repository / config["work_dir"]
    admin_password = secrets.token_hex(24)
    config = {**config, "_config_root": str(work / "config")}
    report_path = repository / config["out"]
    k2_path = repository / config["k2_out"]
    targets = json.loads((repository / "reports/plan12-memory-m1/targets.json").read_text(encoding="utf-8"))
    head = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    report: dict[str, Any] = {"schema": "plan12-memory-m1.qualify.v1", "phase": "qualify", "head": f"hex:{head}", "config": {k: v for k, v in config.items() if k not in {"artifact_cache", "_config_root"}},
                              "host": {"cpus": psutil.cpu_count(), "memory_gb": round(psutil.virtual_memory().total / 2**30, 1)}}

    def save() -> None:
        report_path.write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")

    save()
    prepare = lambda root: k2_admin_acl(root, admin_password)  # noqa: E731
    root, memory, _password, client, gateway, settings, settings_file = scale._provision(config, repository, work, prepare=prepare)
    try:
        inner = FastembedEmbedder(root, memory.embedding, directory=settings_file["embedding"]["artifact_directory"], threads=config["embedding_threads"])
        launcher = psutil.Process(gateway.pid)
        pids = {"gateway": (launcher.children() or [launcher])[0].pid, "worker": psutil.Process().pid}
        store = memory_index.IndexStore(client, cursor_key=b"m" * 32)

        scale._note("this repository (reusing the evaluation's embeddings where its text matches)")
        repo_copy = scale._corpus_copy(repository, work / "corpus-repo", ["."])
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
        kit = os.environ.get("P1210_ACPX_KIT")
        turns = None if not kit else scale._AcpxTurns(Path(kit), work / "acpx-stub")
        if turns is None:
            report["acpx"] = {"state": "UNRUN", "reason": "P1210_ACPX_KIT names no approved stub agent"}
        else:
            turns.open()
            first_turn = turns.turns(1)
            report["acpx"] = {"first_turn": first_turn, "queue_owners_recorded": turns.record_owner(), "idle": turns.turns(config["acpx_turns"]), "idle_cancel": turns.cancel_during_a_turn()}
        save()
        scale._note(f"large corpus: {count['embedded_chunks']} chunks")
        report["large"]["cold"] = _built_with_samples(index, repo_index, store, config=config, pids=pids, turns=turns)
        report["large"]["cold"]["embedded_items_per_second"] = round(embedder.items / embedder.seconds, 1) if embedder.seconds else None
        report["large"]["cold"]["redis"] = scale._redis_facts(client, config["container"])
        if turns is not None:
            turns.close()
        save()

        if report["large"]["cold"]["state"] != "complete":
            report["stopped"] = "the large build did not complete; K2 and the later stages need its records, so they did not run"
            save()
            return report
        scale._note("reconcile, edit, queries")
        started = time.perf_counter()
        unchanged = index.worker().run(threading.Event())
        files = sum(count["files"].values())
        report["large"]["reconcile_unchanged"] = {"state": unchanged.state, "seconds": round(time.perf_counter() - started, 1), "seconds_per_1000_files": round((time.perf_counter() - started) / files * 1000, 1), "records_written": unchanged.records_written}
        target = next(path for path in sorted(large.rglob("*.java")) if path.stat().st_size > 2000 and "test" not in path.parts)
        target.write_text(target.read_text(encoding="utf-8") + "\n\nclass M1QualifyAddedClass { void m1QualifyAddedMethod() {} }\n", encoding="utf-8")
        started = time.perf_counter()
        edited = index.worker().run(threading.Event())
        found = index.storage.call("query", mode="lexical", terms=["m1qualifyaddedmethod"], k=5)["records"]
        report["large"]["incremental_one_file"] = {"state": edited.state, "seconds": round(time.perf_counter() - started, 2), "records_written": edited.records_written, "new_symbol_found": bool(found)}
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
        report["large"]["assembly_calibration"] = _calibrate_assembly(large, settings, embedder, work, project="qualify-large", parser_version="qualify")
        report["redis_before_k2"] = scale._redis_facts(client, config["container"])
        save()

        scale._note("K2")

        def write_k2(k2: dict[str, Any]) -> None:
            k2_path.write_text(json.dumps({**k2, "head": f"hex:{head}"}, indent=1, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")

        real = (repo_outcome.records_written or 0) + (report["large"]["cold"]["records_written"] or 0)
        run_k2(targets=targets, config=config, memory=memory, admin_password=admin_password, settings=settings, indexes={"repo": repo_index, "large": index}, real_records=real, write=write_k2)
        client.close()
    finally:
        save()
        gateway.kill()
        gateway.wait(10)
    return report

