"""Plan 12.10 M1 measurement: `python -m tools.plan12_memory.m1_scale --phase pilot --config reports/plan12-memory-m1/run-config.json`.

Runs against the released dedicated Redis and a real Gateway process, on a throwaway copy of the corpus. Measures, never tunes: it
reports what the pilot saw so the operator can freeze targets from numbers. No generative or provider call is possible here: the
Gateway's upstream is an unroutable local address and only the index route is used. Records carry counts, timings and hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import stat
import statistics
import struct
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import psutil
import redis

from context_engine.code_index import parse_file
from context_engine.index_worker import IndexWorker
from optimus.acp import local_infra
from optimus.acp.memory_setup import run_setup
from optimus.config.gateway import OptimusGatewaySettings
from optimus.context.memory_workspace import FastembedEmbedder, GatewayIndexStorage, WorkspaceIndexSource, current_branch, index_scope
from optimus.context.project_registry import ProjectRegistration
from optimus.guardrails.file_policy import FilePolicy, FilePurpose
from optimus_gateway import memory_index
from optimus_security import memory_index_contract as mic
from optimus_security.memory_index_config import KEYRING_SERVICE, memory_index_root, read

_SECRET = "m1-scale-local-secret"  # pragma: allowlist secret - a local measurement's own Gateway key
_GATEWAY_SCRIPT = """
import json, sys
from dataclasses import replace
from optimus_gateway import memory_index
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway

options = json.loads(sys.stdin.readline())
client = memory_index.connect(memory_index.IndexEndpoint("127.0.0.1", options["port"], options["user"], options["password"], options["resource"]))
store = memory_index.IndexStore(client, cursor_key=b"m" * 32)
config = GatewayServiceConfig(bind_host="127.0.0.1", bind_port=0, shared_secret=options["secret"], provider="openrouter",
                              provider_api_key=options["secret"], base_url="http://127.0.0.1:9/api/v1")
server = serve_gateway(config=replace(config, memory_index=memory_index.IndexService(store)), upstream_client=object())
print(server.server_address[1], flush=True)
server.serve_forever()
"""


class _Keyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, name: str, value: str) -> None:
        self.values[(service, name)] = value

    def get_password(self, service: str, name: str) -> str | None:
        return self.values.get((service, name))


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    return round(sorted(values)[max(0, int(len(values) * quantile + 0.5) - 1)], 3) if values else None


def _summary(values: Sequence[float]) -> dict[str, Any]:
    return {"samples": len(values), "p50_ms": _percentile(values, 0.5), "p95_ms": _percentile(values, 0.95), "max_ms": round(max(values), 3) if values else None,
            "mean_ms": round(statistics.fmean(values), 3) if values else None}


class _Sampler:
    """CPU, RSS and threads of named processes, sampled while a phase runs."""

    def __init__(self, pids: dict[str, int], interval: float = 0.5) -> None:
        self._processes = {name: psutil.Process(pid) for name, pid in pids.items()}
        self._interval = interval
        self._stop = threading.Event()
        self.samples: dict[str, list[tuple[float, int, int]]] = {name: [] for name in pids}
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread_cpu: dict[str, dict[int, float]] = {}
        self._threads_working: dict[str, int] = {}
        self._started = 0.0

    def _cpu_by_thread(self) -> dict[str, dict[int, float]]:
        out: dict[str, dict[int, float]] = {}
        for name, process in self._processes.items():
            try:
                out[name] = {thread.id: thread.user_time + thread.system_time for thread in process.threads()}
            except psutil.Error:
                out[name] = {}
        return out

    def _run(self) -> None:
        for process in self._processes.values():
            process.cpu_percent(None)
        while not self._stop.wait(self._interval):
            for name, process in self._processes.items():
                try:
                    with process.oneshot():
                        self.samples[name].append((process.cpu_percent(None), process.memory_info().rss, process.num_threads()))
                except psutil.Error:
                    pass

    def __enter__(self) -> _Sampler:
        self._thread_cpu = self._cpu_by_thread()
        self._started = time.perf_counter()
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        self._thread.join(5)
        elapsed = max(time.perf_counter() - self._started, 0.001)
        # Threads that did real work, as against pools that exist and sleep: the check on the configured two embedding threads.
        for name, seen in self._cpu_by_thread().items():
            self._threads_working[name] = sum((cpu - self._thread_cpu.get(name, {}).get(ident, 0.0)) / elapsed >= 0.05 for ident, cpu in seen.items())

    def report(self) -> dict[str, Any]:
        return {name: {"cpu_percent_mean": round(statistics.fmean(s[0] for s in rows), 1), "cpu_percent_max": round(max(s[0] for s in rows), 1),
                       "rss_mb_max": round(max(s[1] for s in rows) / 1048576, 1), "threads_max": max(s[2] for s in rows),
                       "threads_using_over_5_percent_of_a_cpu": self._threads_working.get(name)}
                for name, rows in self.samples.items() if rows}


class _TimedEmbedder:
    def __init__(self, inner: FastembedEmbedder) -> None:
        self._inner = inner
        self.identity = inner.identity
        self.dimensions = inner.dimensions
        self.seconds = 0.0
        self.items = 0
        self.chars = 0

    def embed(self, texts: Sequence[str]) -> list[bytes]:
        started = time.perf_counter()
        vectors = self._inner.embed(texts)
        self.seconds += time.perf_counter() - started
        self.items += len(texts)
        self.chars += sum(map(len, texts))
        return vectors


class _Index:
    def __init__(self, root: Path, settings: OptimusGatewaySettings, embedder: _TimedEmbedder, *, project: str, parser_version: str = "pilot") -> None:
        registration = ProjectRegistration(project, 1, f"git:{project}", str(root), created=False)
        self.root = root
        self.scope = index_scope(registration, branch=current_branch(root), embedding=embedder.identity, parser_version=parser_version)
        self.storage = GatewayIndexStorage(settings, scope=self.scope)
        self.embedder = embedder
        self.owner = hashlib.sha256(f"{project}{root}".encode()).hexdigest()[:32]

    def worker(self) -> IndexWorker:
        return IndexWorker(WorkspaceIndexSource(FilePolicy(self.root)), self.storage, self.embedder, owner=self.owner, cold_admission=False)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=m1", "-c", "user.email=m1@example.invalid", *args], capture_output=True, check=True)


def _clear_read_only(remove: Callable[[str], None], path: str, _error: BaseException) -> None:
    """Git marks its objects read-only, which stops a delete on Windows."""
    os.chmod(path, stat.S_IWRITE)
    remove(path)


def _corpus_copy(source: Path, target: Path, paths: Sequence[str]) -> Path:
    """A throwaway copy of the corpus's tracked files, so the measurement can edit it and no checkout changes."""
    if target.exists():
        shutil.rmtree(target, onexc=_clear_read_only)
    target.mkdir(parents=True)
    tracked = subprocess.run(["git", "-C", str(source), "ls-files", "-z", "--", *paths], capture_output=True, check=True).stdout.decode("utf-8").split("\0")
    for relative in filter(None, tracked):
        origin = source / relative
        if origin.is_file():
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, destination)
    _git(target, "init", "-q", "-b", "pilot")
    _git(target, "add", "-A")
    _git(target, "commit", "-q", "-m", "pilot corpus")
    return target


def count_corpus(root: Path) -> dict[str, Any]:
    """Eligible parsed lines per language, files, chunks and exclusions at this exact root, under the real file policy and parser."""
    policy = FilePolicy(root)
    exclusions: dict[str, int] = {}
    files = {"python": 0, "java": 0, "markdown": 0, "text": 0, "unsupported": 0}
    lines = dict.fromkeys(files, 0)
    records = dict.fromkeys(files, 0)
    chunk_chars: list[int] = []
    errors = 0
    started = time.perf_counter()
    for decision in policy.walk(purpose=FilePurpose.INDEX):
        if not decision.allowed:
            exclusions[decision.reason] = exclusions.get(decision.reason, 0) + 1
            continue
        _decision, data = policy.read(decision.relative_path, purpose=FilePurpose.INDEX)
        if data is None:
            exclusions["unreadable"] = exclusions.get("unreadable", 0) + 1
            continue
        parsed = parse_file(decision.relative_path, data)
        files[parsed.language] += 1
        lines[parsed.language] += parsed.parsed_lines
        records[parsed.language] += len(parsed.records)
        errors += parsed.parse_errors
        chunk_chars += [len(record.embed_text) for record in parsed.records if record.embed_text]
    return {"files": files, "parsed_lines": lines, "records": records, "excluded": exclusions, "parse_error_files": errors, "embedded_chunks": len(chunk_chars),
            "chunk_chars_mean": round(statistics.fmean(chunk_chars), 1) if chunk_chars else None, "chunk_chars_p95": _percentile(chunk_chars, 0.95),
            "parse_seconds": round(time.perf_counter() - started, 3)}


def _required(outcome: Any) -> Any:
    """A measurement of a worker that did not finish is not a measurement."""
    if outcome.state != "complete":
        raise SystemExit(f"the worker stopped: {outcome.state} {outcome.detail}, after {outcome.files_written} files and {outcome.records_written} records")
    return outcome


def _timed(call: Callable[[], Any]) -> float:
    started = time.perf_counter()
    call()
    return (time.perf_counter() - started) * 1000


def _note(message: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {message}", file=sys.stderr, flush=True)


def _load_scale_records(index: _Index, *, total: int, dimensions: int) -> dict[str, Any]:
    """Real-shaped records through the route, published into the line, so queries are measured at the forecast's chunk count without
    hours of embedding. Their vectors are random unit-free noise and their terms are distinct; they stand in for size, not meaning."""
    rng = random.Random(1210)
    token = index.storage.call("lease", action="acquire", owner=index.owner, ttl_ms=60000, kind="scope")["token"]
    epoch = index.storage.call("generation", action="begin", token=token)["epoch"]
    started = time.perf_counter()
    written = 0
    while written < total:
        count = min(128, total - written)
        records = []
        for number in range(written, written + count):
            digest = hashlib.sha256(str(number).encode()).hexdigest()
            records.append({"id": digest, "kind": "symbol", "path": f"scale/s{number % 4000}.py", "path_id": hashlib.sha256(str(number % 4000).encode()).hexdigest(), "file_hash": "0" * 64,
                            "language": "python", "symbol": f"scale_symbol_{number}", "signature": f"def scale_symbol_{number}(first, second)", "description": "function in a scale file",
                            "terms": f"scale symbol scale_symbol_{number} word{number % 500} first second",
                            "vector": mic.encode_vector(struct.pack(f"<{dimensions}f", *(rng.random() for _ in range(dimensions))))})
        index.storage.call("batch", token=token, epoch=epoch, records=records)
        written += count
        if written % 12800 == 0:
            index.storage.call("lease", action="renew", owner=index.owner, ttl_ms=60000, kind="scope", token=token)
    current = index.storage.call("coverage")["current"]
    index.storage.call("generation", action="publish", token=token, epoch=epoch, revision=current["revision"], dirty=current["dirty"], coverage=current["coverage"])
    index.storage.call("lease", action="release", owner=index.owner, kind="scope", token=token)
    seconds = time.perf_counter() - started
    return {"records": written, "seconds": round(seconds, 1), "records_per_second": round(written / seconds, 1)}


def runs_agent(arguments: Sequence[str], agent: str) -> bool:
    """One argument is exactly the agent, quoted or not. `run-a.cmd.backup.cmd` beside it is another program."""
    wanted = agent.casefold()
    return any(argument.strip("\"'").casefold() == wanted for argument in arguments)


class _AcpxTurns:
    """Real acpx turns against a real approved agent whose upstream is a local stub, so a person's turn is measured, idle and during a
    cold build. The folder comes only from P1210_ACPX_KIT, because its launch approvals belong to that folder; without it this reports UNRUN."""

    def __init__(self, kit: Path, evidence: Path) -> None:
        self._kit = kit
        self._acpx = shutil.which("acpx") or "acpx"
        self._common = ["--format", "json", "--deny-all", "--ttl", "900", "--timeout", "120", "--cwd", str(kit / "workspace-a"), "--agent", f"'{kit / 'run-a.cmd'}'"]
        evidence.mkdir(parents=True, exist_ok=True)
        self._stub = subprocess.Popen([sys.executable, "-I", str(kit / "stub_provider.py"), str(kit / "scenario.json"), str(evidence), "18791", "1800"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._before = set(psutil.pids())
        self._owners: list[tuple[int, float]] = []
        time.sleep(1.0)

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([self._acpx, *self._common, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=180)

    def open(self) -> str:
        return str(self._run("sessions", "new").returncode)

    def turns(self, count: int) -> dict[str, Any]:
        times, failures = [], 0
        for _ in range(count):
            started = time.perf_counter()
            result = self._run("prompt", "Explain in one line what the docstring in notes.py says. [p129:T1]")
            times.append((time.perf_counter() - started) * 1000)
            failures += '"stopReason":"end_turn"' not in result.stdout.replace(" ", "")
        return {**_summary(times), "failures": failures}

    def cancel_during_a_turn(self) -> dict[str, Any]:
        """A long scripted walk, cancelled a moment in: how long the person waits for it to stop."""
        turn = subprocess.Popen([self._acpx, *self._common, "prompt", "Walk the ledger. [p129:T4]"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
        time.sleep(1.5)
        started = time.perf_counter()
        self._run("cancel")
        output, _ = turn.communicate(timeout=120)
        return {"seconds_to_stop": round(time.perf_counter() - started, 3), "stop": "cancelled" if '"stopReason":"cancelled"' in output.replace(" ", "") else "other"}

    def record_owner(self) -> int:
        """Called once a turn has run, when this run's queue owner exists: a process that did not exist before this run, with a child whose
        argument is exactly this kit's agent. Only what is recorded here is ever stopped; anything else on the machine is another lane's."""
        agent = str(self._kit / "run-a.cmd")
        for process in psutil.process_iter(["pid", "cmdline", "create_time"]):
            if process.info["pid"] in self._before or not any("__queue-owner" in part for part in process.info["cmdline"] or []):
                continue
            try:
                if any(runs_agent(child.cmdline(), agent) for child in process.children()):
                    self._owners.append((process.info["pid"], process.info["create_time"]))
            except psutil.Error:
                pass
        return len(self._owners)

    def close(self) -> None:
        self._stub.kill()
        for pid, created in self._owners:
            try:
                process = psutil.Process(pid)
                if process.create_time() == created:  # a pid can be reused
                    for child in process.children(recursive=True):
                        child.kill()
                    process.kill()
            except psutil.Error:
                pass


def _redis_facts(client: redis.Redis, container: str) -> dict[str, Any]:
    memory = client.info("memory")
    usage = subprocess.run(["docker", "exec", container, "sh", "-c", "du -sk /data | cut -f1"], capture_output=True, text=True, check=False).stdout.strip()
    return {"used_memory_mb": round(memory["used_memory"] / 1048576, 1), "used_memory_peak_mb": round(memory["used_memory_peak"] / 1048576, 1),
            "disk_kb": int(usage) if usage.isdigit() else None, "maxmemory_mb": round(memory["maxmemory"] / 1048576, 1)}


def _direct(store: memory_index.IndexStore, scope: str, op: str, **fields: Any) -> dict[str, Any]:
    """The Gateway's own store code and validation in this process with an authenticated client: all the same work, without the route."""
    return store.dispatch(mic.parse_request(json.dumps({"op": op, "scope": scope, **fields}).encode("utf-8")))


def _query_load(index: _Index, store: memory_index.IndexStore, *, samples: int, terms: Sequence[str], vector: str) -> dict[str, Any]:
    """The same requests through the route and directly: what the route itself costs, on real data."""
    out: dict[str, list[float]] = {"proxy_lexical": [], "proxy_dense": [], "native_lexical": [], "native_dense": []}
    for number in range(samples):
        term = terms[number % len(terms)]
        out["proxy_lexical"].append(_timed(lambda term=term: index.storage.call("query", mode="lexical", terms=[term], k=20)))
        out["native_lexical"].append(_timed(lambda term=term: _direct(store, index.scope, "query", mode="lexical", terms=[term], k=20)))
        out["proxy_dense"].append(_timed(lambda: index.storage.call("query", mode="dense", vector=vector, k=20)))
        out["native_dense"].append(_timed(lambda: _direct(store, index.scope, "query", mode="dense", vector=vector, k=20)))
    return {name: _summary(values) for name, values in out.items()}


def _bulk(index: _Index, store: memory_index.IndexStore, *, batches: int, dimensions: int) -> dict[str, Any]:
    """Batches of real size, with their fencing and membership writes, through the route and directly."""
    token = index.storage.call("lease", action="acquire", owner=index.owner, ttl_ms=60000, kind="scope")["token"]
    epoch = index.storage.call("generation", action="begin", token=token)["epoch"]
    vector = mic.encode_vector(struct.pack(f"<{dimensions}f", *([0.1] * dimensions)))

    def records(batch: int, kind: str) -> list[dict[str, Any]]:
        return [{"id": hashlib.sha256(f"{kind}{batch}{n}".encode()).hexdigest(), "kind": "symbol", "path": f"bulk/{kind}{batch}.py", "path_id": hashlib.sha256(f"{kind}{batch}".encode()).hexdigest(),
                 "file_hash": "0" * 64, "language": "python", "symbol": f"symbol_{n}", "signature": "def symbol()", "terms": "bulk measurement terms", "vector": vector} for n in range(128)]

    started = time.perf_counter()
    for batch in range(batches):
        index.storage.call("batch", token=token, epoch=epoch, records=records(batch, "proxy"))
    proxy_seconds = time.perf_counter() - started
    started = time.perf_counter()
    for batch in range(batches):
        _direct(store, index.scope, "batch", token=token, epoch=epoch, records=records(batch, "native"))
    native_seconds = time.perf_counter() - started
    index.storage.call("lease", action="release", owner=index.owner, kind="scope", token=token)
    total = batches * 128
    return {"records": total, "proxy_records_per_second": round(total / proxy_seconds, 1), "native_records_per_second": round(total / native_seconds, 1),
            "proxy_seconds": round(proxy_seconds, 3), "native_seconds": round(native_seconds, 3)}


def run_pilot(config: dict[str, Any], repository: Path) -> dict[str, Any]:
    work = repository / config["work_dir"]
    work.mkdir(parents=True, exist_ok=True)
    container, volume = config["container"], config["volume"]
    assert container.startswith("p1210-") and volume.startswith("p1210-"), "only the released resources"
    subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)
    subprocess.run(["docker", "volume", "rm", "-f", volume], capture_output=True, check=False)

    artifact = next((repository / config["artifact_cache"]).iterdir())
    config_root = work / "config"
    if config_root.exists():
        shutil.rmtree(config_root)
    config_root.mkdir()

    def copy_artifact(*, repository: str, revision: str, target: Path) -> None:
        shutil.copytree(artifact, target, dirs_exist_ok=True)

    from optimus.acp.memory_setup import shipped_defaults

    settings_file = shipped_defaults()
    defaults = {**settings_file, "container": container, "volume": volume, "port": config["port"], "maxmemory_mb": config["maxmemory_mb"]}
    keyring = _Keyring()
    run_setup(config_root, keyring_backend=keyring, confirm=lambda _d: True, download=copy_artifact, defaults=defaults)
    root = memory_index_root(config_root)
    _literal, memory, _refusal = read(root)
    assert memory is not None
    password = keyring.get_password(KEYRING_SERVICE, memory.credential_name)
    assert password is not None
    status = local_infra.ensure_memory_redis(root)
    assert status.state == "ready", status
    client = memory_index.connect(memory_index.IndexEndpoint("127.0.0.1", memory.port, memory.user, password, memory.resource))
    deadline = time.monotonic() + 30
    while True:
        try:
            client.ping()
            break
        except redis.RedisError:
            assert time.monotonic() < deadline
            time.sleep(0.5)

    gateway = subprocess.Popen([sys.executable, "-c", _GATEWAY_SCRIPT], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    assert gateway.stdin is not None and gateway.stdout is not None
    gateway.stdin.write(json.dumps({"port": memory.port, "user": memory.user, "password": password, "resource": memory.resource, "secret": _SECRET}) + "\n")
    gateway.stdin.flush()
    port = int(gateway.stdout.readline())
    settings = OptimusGatewaySettings.from_env({"OPTIMUS_GATEWAY_URL": f"http://127.0.0.1:{port}", "OPTIMUS_API_KEY": _SECRET})

    report: dict[str, Any] = {"schema": "plan12-memory-m1.pilot.v1", "phase": "pilot", "config": {k: v for k, v in config.items() if k != "artifact_cache"}}
    report["host"] = {"cpus": psutil.cpu_count(), "memory_gb": round(psutil.virtual_memory().total / 2**30, 1), "python": sys.version.split()[0], "platform": sys.platform}
    try:
        corpus = _corpus_copy(repository, work / "corpus", config["corpus_paths"])
        report["corpus"] = count_corpus(corpus)
        embedder = _TimedEmbedder(FastembedEmbedder(root, memory.embedding, directory=settings_file["embedding"]["artifact_directory"], threads=config["embedding_threads"]))
        index = _Index(corpus, settings, embedder, project="pilot")
        launcher = psutil.Process(gateway.pid)  # a venv's python.exe is a launcher; the work happens in its child
        pids = {"gateway": (launcher.children() or [launcher])[0].pid, "worker": psutil.Process().pid}

        store = memory_index.IndexStore(client, cursor_key=b"m" * 32)
        _note(f"cold build: {report['corpus']['embedded_chunks']} chunks")
        real_call = index.storage.call
        first_publish: list[float] = []

        def watching(op: str, **fields: Any) -> dict[str, Any]:
            reply = real_call(op, **fields)
            if op == "generation" and fields.get("action") == "publish" and not first_publish:
                first_publish.append(time.perf_counter())
            return reply

        index.storage.call = watching  # type: ignore[method-assign]
        started = time.perf_counter()
        with _Sampler(pids) as sampler:
            outcome = _required(index.worker().run(threading.Event()))
        cold = time.perf_counter() - started
        index.storage.call = real_call  # type: ignore[method-assign]
        report["cold"] = {"state": outcome.state, "seconds": round(cold, 2), "files_written": outcome.files_written, "records_written": outcome.records_written, "coverage": outcome.coverage,
                          "first_file_visible_seconds": round(first_publish[0] - started, 2), "embedding_seconds": round(embedder.seconds, 2), "embedding_share": round(embedder.seconds / cold, 3), "embedded_items": embedder.items,
                          "embedded_items_per_second": round(embedder.items / embedder.seconds, 1) if embedder.seconds else None,
                          "end_to_end_records_per_second": round(outcome.records_written / cold, 1), "processes": sampler.report(), "redis": _redis_facts(client, container)}

        _note(f"cold build took {cold:.0f}s; reconcile")
        started = time.perf_counter()
        idle = _required(index.worker().run(threading.Event()))
        report["reconcile_unchanged"] = {"state": idle.state, "seconds": round(time.perf_counter() - started, 2), "records_written": idle.records_written}

        target = next(path for path in sorted(corpus.rglob("*.py")) if path.stat().st_size > 2000)
        target.write_text(target.read_text(encoding="utf-8") + "\n\ndef m1_pilot_added_function():\n    return 1\n", encoding="utf-8")
        started = time.perf_counter()
        edited = _required(index.worker().run(threading.Event()))
        report["incremental_one_file"] = {"state": edited.state, "seconds": round(time.perf_counter() - started, 2), "records_written": edited.records_written}
        found = index.storage.call("query", mode="lexical", terms=["m1_pilot_added_function"], k=5)["records"]
        report["incremental_one_file"]["new_symbol_found"] = bool(found)

        _note("loading scale records")
        report["scale_load"] = _load_scale_records(index, total=config["scale_records"], dimensions=memory.embedding.dimensions)
        report["redis_at_scale"] = _redis_facts(client, container)
        _note("queries")
        vector = mic.encode_vector(embedder.embed(["measure a query vector for this repository"])[0])
        terms = ["gateway", "redis", "context", "policy", "server", "approval", "token", "manifest"]
        report["query_idle"] = _query_load(index, store, samples=config["query_samples"], terms=terms, vector=vector)

        kit = os.environ.get("P1210_ACPX_KIT")
        turns = None if not kit else _AcpxTurns(Path(kit), work / "acpx-stub")
        if turns is None:
            report["acpx_turns"] = {"state": "UNRUN", "reason": "P1210_ACPX_KIT names no approved stub agent"}
        else:
            _note("acpx turns while idle")
            opened = turns.open()
            first_turn = turns.turns(1)  # a session's first turn does one-time work, so it is kept apart from the comparison
            report["acpx_turns"] = {"session_new_exit": opened, "first_turn": first_turn, "queue_owners_recorded": turns.record_owner(),
                                    "measures": "machine load on a person's turn; this agent's own Gateway, not the measured index route",
                                    "idle": turns.turns(config["acpx_turns"]), "idle_cancel": turns.cancel_during_a_turn()}

        # Foreground queries while a second scope cold-builds: the load a person's turn would meet. A wider copy, so it outlasts the measurements.
        load_corpus = _corpus_copy(repository, work / "corpus-load", config["load_paths"])
        report["load_corpus"] = count_corpus(load_corpus)
        second = _Index(load_corpus, settings, embedder, project="pilot-load", parser_version="pilot-load")
        cancel = threading.Event()
        built: list[Any] = []
        loader = threading.Thread(target=lambda: built.append(second.worker().run(cancel)), daemon=True)
        with _Sampler(pids) as sampler:
            loader.start()
            time.sleep(1.0)
            report["query_during_cold_build"] = _query_load(index, store, samples=config["query_samples"], terms=terms, vector=vector)
            report["query_during_cold_build"]["build_still_running"] = loader.is_alive()
            if turns is not None:
                _note("acpx turns during a cold build")
                report["acpx_turns"]["during_build"] = turns.turns(config["acpx_turns"])
                report["acpx_turns"]["during_build_cancel"] = turns.cancel_during_a_turn()
                report["acpx_turns"]["build_still_running"] = loader.is_alive()
                turns.close()
            cancel_started = time.perf_counter()
            cancel.set()
            loader.join(120)
            report["cancel"] = {"seconds_to_stop": round(time.perf_counter() - cancel_started, 3), "state": built[0].state if built else "no-result"}
        report["query_during_cold_build"]["processes"] = sampler.report()

        _note("bulk")
        report["bulk"] = _bulk(index, store, batches=config["bulk_batches"], dimensions=memory.embedding.dimensions)
        report["redis_end"] = _redis_facts(client, container)

        _note("recovery")
        # Recovery: kill the instance, and time until the published view answers again with its data.
        before = index.storage.call("coverage")["current"]
        subprocess.run(["docker", "kill", container], capture_output=True, check=True)
        started = time.perf_counter()
        status = local_infra.ensure_memory_redis(root)
        recovered = None
        while time.perf_counter() - started < 120:
            try:
                recovered = index.storage.call("coverage")["current"]
                break
            except Exception:  # noqa: BLE001 - measuring when it comes back
                time.sleep(0.2)
        answered = time.perf_counter() - started
        report["recovery"] = {"ensure_state": status.state, "seconds_until_answering": round(answered, 2), "same_publication": recovered == before,
                              "records_after": len(index.storage.call("query", mode="lexical", terms=["gateway"], k=20)["records"])}
    finally:
        gateway.kill()
        gateway.wait(10)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="m1_scale")
    parser.add_argument("--phase", choices=["pilot"], required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    repository = Path(__file__).resolve().parents[2]
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    report = run_pilot(config, repository)
    out = Path(args.config).with_name("pilot.json")
    out.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
