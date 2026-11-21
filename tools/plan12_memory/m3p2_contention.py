"""Plan 12.12 K2 contention: `python -m tools.plan12_memory.m3p2_contention --output <file>`, with the CP2 release set
(`P1211_MEMORY_DOCKER_RELEASED`, `P1212_BACKUP_TEST_ROOT`).

Runs the workload frozen in `reports/plan12-memory-m3-part2/targets.json` (`k2_contention`) once, unchanged: the Plan 12.11 K2
writers (`m3_k2.schedule`, four projects, 5,000 events each) on the released test store, with a fifth project `p-bi-0` holding
10,000 items written first; when every writer has 2,000 acknowledgements, backup generation 1 and a 1,000-entry import into
`p-bi-0` start together; generation 2 starts when the import settles. Backups go to the released folder through the production
`Backups`, the import through the production `/memory import` commands. Measures, never tunes: a miss is retained, and if any
writer had stopped writing before generation 2 was verified the evidence is INCOMPLETE, never a pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import secrets
import string
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from optimus.acp import memory_commands as mc
from optimus.context import memory_backups as mb
from optimus.context import memory_import as mi
from optimus.context import memory_recovery as mr
from optimus.context.authored_memory import GatewayMemoryStore
from tests.integration.memory.conftest import RELEASE_FLAG
from tools.plan12_memory import m3_k2 as k2

TARGETS = Path("reports/plan12-memory-m3-part2/targets.json")
BI = "p-bi-0"
BI_CLIENT = 4  # the initial population's client index in m3_k2's generators
BARRIER_ACKS = 2000


def _workload() -> dict[str, Any]:
    return dict(json.loads(TARGETS.read_text(encoding="utf-8"))["k2_contention"])


def _host(service: Any, project: str, owner: str) -> GatewayMemoryStore:
    def post(_settings: Any, *, timeout: float, path: str) -> Any:
        return lambda body: service.handle(body, deadline=time.monotonic() + 5)

    return GatewayMemoryStore(object(), project=project, owner=owner, post=post)  # type: ignore[arg-type]


def import_source(root: Path, project: str) -> list[str]:
    """The frozen import leg: `random.Random(1212)`; entry i is 'p1212 import entry <i>: ' and seeded lowercase words to a
    length drawn from 200 to 2,000 characters; one MEMORY.md linking ten topic notes of 100 entries each."""
    rng = random.Random(1212)
    statements = []
    for i in range(1000):
        length = rng.randint(200, 2000)
        text = f"p1212 import entry {i}: "
        while len(text) < length:
            text += "".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(2, 9))) + " "
        statements.append(text[:length].rstrip())
    root.mkdir(parents=True)
    (root / "MEMORY.md").write_text("# Notes\n\n" + "".join(f"- [[topic-{t}]]\n" for t in range(10)), encoding="utf-8")
    for t in range(10):
        body = "".join(f"- {s} [project: {project}]\n" for s in statements[t * 100:(t + 1) * 100])
        (root / f"topic-{t}.md").write_text(body, encoding="utf-8")
    return statements


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q"], cwd=path, env=env, check=True, stdin=subprocess.DEVNULL)
    return path


def _populate(service: Any, items: int) -> float:
    """The initial population of p-bi-0 (m3_k2's item and statement generators, unchanged), under its lease, released after.
    Written in the host's own scope, `project`: in the K2 scope `s-k2` the host's recovery check would read p-bi-0 as an emptied
    store once a copy exists, and refuse every write (the CP2 smoke run)."""
    started = time.perf_counter()
    _code, reply = k2._call(service, {"op": "lease", "project": BI, "owner": "bi-populate", "action": "acquire", "ttl_ms": 300_000})
    token = reply["token"]
    for slot in range(items):
        if slot and slot % 2000 == 0:
            k2._call(service, {"op": "lease", "project": BI, "owner": "bi-populate", "action": "renew", "ttl_ms": 300_000, "token": token})
        item, statement = k2._item(BI_CLIENT, slot), k2._statement(BI_CLIENT, slot, 1)
        body = {"op": "append", "project": BI, "token": token, "expected_version": 0,
                "idempotency_key": hashlib.sha256(f"{BI}:{item}:1".encode()).hexdigest(),
                "event": {**k2._event(item, 1, statement), "scope": "project"}}  # a host's scope: its emptiness check reads it
        for _attempt in range(4):
            code, reply = k2._call(service, body)
            if code == 200 and reply.get("durable_state") == "confirmed":
                break
        else:
            raise RuntimeError(f"initial population {item} not confirmed: {reply}")
    k2._call(service, {"op": "lease", "project": BI, "owner": "bi-populate", "action": "release", "token": token})
    return round(time.perf_counter() - started, 1)


class Writers:
    """The four K2 writers, as `m3_k2._write_load` writes, with each acknowledgement's time kept and a barrier at 2,000 each."""

    def __init__(self, provisioned: Any, work: Path, *, events: int, items: int, observe_every: int = 50) -> None:
        self.services = [k2._service(provisioned, work / f"journal-{n}") for n in range(k2.CLIENTS)]
        self.observer = k2._service(provisioned, work / "journal-observer")
        self.projects = [f"p-k2-{n}" for n in range(k2.CLIENTS)]
        self.events, self.items, self.observe_every = events, items, observe_every
        self.acks: list[tuple[float, float]] = []  # (when acknowledged, latency)
        self.projection: list[tuple[float, float]] = []
        self.counts = [0] * k2.CLIENTS
        self.finished: list[float | None] = [None] * k2.CLIENTS
        self.failed: list[tuple[int, str, int]] = []
        self.refusals: dict[str, int] = {}
        self.barrier = threading.Event()
        self._lock = threading.Lock()

    def client(self, n: int) -> None:
        service, project = self.services[n], self.projects[n]
        code, reply = k2._call(service, {"op": "lease", "project": project, "owner": f"k2-{n}", "action": "acquire", "ttl_ms": 300_000})
        if code != 200:
            code, reply = k2._call(service, {"op": "lease", "project": project, "owner": f"k2-{n}", "action": "acquire", "ttl_ms": 300_000})
        assert code == 200, (n, reply)
        token = reply["token"]
        per_items = self.items // k2.CLIENTS
        written: dict[str, int] = {}
        for number in range(self.events // k2.CLIENTS):
            if number and number % 2000 == 0:
                k2._call(service, {"op": "lease", "project": project, "owner": f"k2-{n}", "action": "renew", "ttl_ms": 300_000, "token": token})
            slot = number % per_items
            item = k2._item(n, slot)
            version = written.get(item, 0) + 1
            written[item] = version
            statement = k2._statement(n, slot, version)
            key = hashlib.sha256(f"{project}:{item}:{version}".encode()).hexdigest()
            body = {"op": "append", "project": project, "token": token, "expected_version": version - 1, "idempotency_key": key,
                    "event": k2._event(item, version, statement)}
            started = time.perf_counter()
            code, reply = k2._call(service, body)
            retries = 0
            while not (code == 200 and reply.get("durable_state") == "confirmed") and retries < 3:
                reason = reply.get("error") or f"durable_state={reply.get('durable_state')}"
                with self._lock:
                    self.refusals[reason] = self.refusals.get(reason, 0) + 1
                retries += 1
                code, reply = k2._call(service, body)
            now = time.perf_counter()
            if code == 200 and reply.get("durable_state") == "confirmed":
                with self._lock:
                    self.acks.append((now, now - started))
                    self.counts[n] += 1
                    if min(self.counts) >= BARRIER_ACKS:
                        self.barrier.set()
                if number % self.observe_every == 0:
                    seen_at = time.perf_counter()
                    while time.perf_counter() - seen_at <= 10:
                        current = k2._call(self.observer, {"op": "read", "project": project, "item": item})[1].get("item")
                        if current and current["version"] >= version:
                            break
                        time.sleep(0.005)
                    with self._lock:
                        self.projection.append((time.perf_counter(), time.perf_counter() - seen_at))
            else:
                with self._lock:
                    self.failed.append((n, item, version))
        self.finished[n] = time.perf_counter()


def _verify_generation(place: Path, name: str, initial: dict[str, str], imported_at: list[tuple[str, str]]) -> dict[str, Any]:
    """A backup generation's inventory against its own observed head: the initial items with their statements, and exactly the
    import items whose commits are at or before that head."""
    manifest, entries = mr.read_generation(place / name, BI)
    head = manifest["head"]

    def order(stream_id: str) -> tuple[int, int]:
        major, minor = stream_id.split("-")
        return int(major), int(minor)

    expected_imports = {item for item, stream_id in imported_at if order(stream_id) <= order(head)}
    held = {shaped["entry"]["item"]: shaped["entry"] for shaped in entries}
    missing_initial = [item for item, digest in initial.items()
                       if item not in held or k2._digest(held[item].get("statement", "")) != digest]
    imports = {item for item, entry in held.items() if entry.get("trust") == "legacy-import"}
    return {"generation": name, "head": head, "entries": len(entries), "expected": len(initial) + len(expected_imports),
            "initial_missing_or_changed": len(missing_initial), "imports_expected_at_head": len(expected_imports),
            "imports_held": len(imports), "imports_missing": len(expected_imports - imports), "imports_unexpected": len(imports - expected_imports),
            "verified": not missing_initial and imports == expected_imports and len(entries) == len(initial) + len(expected_imports)}


def run(output: Path) -> dict[str, Any]:
    workload = _workload()
    backup_root = os.environ.get("P1212_BACKUP_TEST_ROOT")
    if not os.environ.get(RELEASE_FLAG) or not backup_root or not Path(backup_root).is_dir():
        raise SystemExit(f"UNRUN: {RELEASE_FLAG} and P1212_BACKUP_TEST_ROOT (the released backup folder) are required")
    work = Path(tempfile.mkdtemp(prefix="p1212-k2c-"))
    target = Path(backup_root) / f"contention-{secrets.token_hex(6)}"
    provisioned = k2._provision(work)
    events = workload["writers"]["events_total"]
    items = workload["writers"]["items_per_writer"] * k2.CLIENTS
    expected = k2.schedule(events=events, items=items)

    host_service = k2._service(provisioned, work / "journal-bi")
    populate_seconds = _populate(host_service, workload["initial_population"]["items"])
    initial = {k2._item(BI_CLIENT, slot): k2._digest(k2._statement(BI_CLIENT, slot, 1))
               for slot in range(workload["initial_population"]["items"])}
    repo = _git_repo(work / "ws")
    config = work / "config"
    store = _host(host_service, BI, "session:contention")
    recovery = mr.Recovery(store, mr.StateFile(config, BI))
    backups = mb.Backups(recovery, mb.BackupStateFile(config, BI), workspace=repo, config_root=config)

    def written(action: str, item: str) -> None:
        recovery.written(action, item)
        if action in ("withdraw", "tombstone"):
            backups.withdrawn(item)
    store.guard, store.written = recovery.recovery_required, written
    commands = mc.MemoryCommands(store, trusted=True, sanitize=lambda v: v, scope="project", recovery=recovery, workspace=repo,
                                 backups=backups, imports=mi.ImportLog(config, BI))
    recovery.confirm(mr.location(repo), sync_consent=False)
    target.mkdir()
    backups.configure(backups.assess(target), consent=False)
    source = work / "import-src"
    import_source(source, BI)
    preview = commands.run(mc.MemoryCommand("import", target=str(source)), block="command:1")
    preview_id = preview.text.split("`", 2)[1]
    asked = commands.run(mc.MemoryCommand("import_apply", preview=preview_id), block="command:2")
    assert asked.confirm is not None, asked.text

    sample: dict[str, Any] = {}
    stop = threading.Event()
    sampler = threading.Thread(target=k2._sampler, args=(provisioned, stop, sample))
    writers = Writers(provisioned, work, events=events, items=items)
    threads = [threading.Thread(target=writers.client, args=(n,)) for n in range(k2.CLIENTS)]
    legs: dict[str, Any] = {}

    def backup_leg(name: str) -> None:
        started = time.perf_counter()
        attempts, errors = 0, []
        while True:
            attempts += 1
            try:
                generation = backups.backup(explicit=True)
                break
            except mb.BackupError as failure:  # memory moving on (the import, here) is retried, as the scheduler would
                errors.append(failure.code)
                if attempts >= 30:
                    legs[name] = {"error": errors}
                    return
                time.sleep(1.0)
        legs[name] = {"generation": generation.name, "attempts": attempts, "errors": errors, "started": started,
                      "published": time.perf_counter(), "seconds": round(time.perf_counter() - started, 1)}

    def import_leg() -> None:
        started = time.perf_counter()
        answer = commands.confirmed(asked.confirm)  # type: ignore[arg-type]
        legs["import"] = {"answer": answer.text, "started": started, "settled": time.perf_counter(),
                          "seconds": round(time.perf_counter() - started, 1), "status": commands.run(mc.MemoryCommand("import_status"),
                                                                                                        block="command:3").text,
                          "notices": [(n.item, n.event_id, n.durable_state) for n, _label in answer.notices]}

    sampler.start()
    window = time.perf_counter()
    for thread in threads:
        thread.start()
    if not writers.barrier.wait(timeout=900):
        raise RuntimeError("the writers never reached the barrier")
    barrier = time.perf_counter()
    g1 = threading.Thread(target=backup_leg, args=("generation_1",))
    imp = threading.Thread(target=import_leg)
    g1.start(), imp.start()
    imp.join()
    backup_leg("generation_2")
    g1.join()
    imported_at = _import_positions(provisioned, legs["import"]["notices"])
    place = target
    verified = {}
    for name in ("generation_1", "generation_2"):
        leg = legs.get(name, {})
        if "generation" in leg:
            verified[name] = _verify_generation(place, leg["generation"], initial, imported_at)
            leg["verified_at"] = time.perf_counter()
    for thread in threads:
        thread.join()
    stop.set()
    sampler.join()
    end = max([t for t in writers.finished if t is not None] + [legs["import"]["settled"]]
              + [legs.get("generation_2", {}).get("verified_at", barrier)])
    g2_verified = legs.get("generation_2", {}).get("verified_at")
    overlap = g2_verified is not None and all(t is not None and t > g2_verified for t in writers.finished)
    inside = [latency for at, latency in writers.acks if barrier <= at <= end]
    projected = [latency for at, latency in writers.projection if barrier <= at <= end]
    identity = k2._identity_check(provisioned, work, writers.projects, expected, "contention")
    bi_check = _bi_check(provisioned, work, initial, imported_at)
    targets = json.loads(Path("reports/plan12-memory-m3/targets.json").read_text(encoding="utf-8"))["k2"]
    measured = {"ack_p95_ms": k2._summary(inside, 1000).get("p95"), "projection_p95_ms": k2._summary(projected, 1000).get("p95"),
                "rss_mib": sample.get("used_memory_rss_mib"), "container_ram_mib": sample.get("container_ram_mib"),
                "disk_kib": sample.get("disk_kib"),
                "acknowledged_write_loss": identity["missing"] + identity["wrong"] + bi_check["missing"] + len(writers.failed)}
    verdicts = {"ack_p95": measured["ack_p95_ms"] is not None and measured["ack_p95_ms"] <= targets["ack_p95_s"] * 1000,
                "projection_p95": measured["projection_p95_ms"] is not None
                and measured["projection_p95_ms"] <= targets["projection_after_ack_p95_ms"],
                "rss": (measured["rss_mib"] or 0) <= targets["physical_ram_gib"] * 1024,
                "disk": (measured["disk_kib"] or 0) <= targets["peak_persistence_disk_gib"] * 1024 * 1024,
                "loss": measured["acknowledged_write_loss"] == targets["acknowledged_write_loss"]}
    for leg in legs.values():
        for key in ("started", "published", "settled", "verified_at"):
            if key in leg:
                leg[key] = round(leg[key] - barrier, 2)  # seconds after the barrier
    result = {
        "schema": "plan12-memory-m3p2.k2-contention.v1",
        "source": "git:" + subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip(),
        "dirty_src": bool(subprocess.run(["git", "status", "--porcelain", "--", "src", "tools"], capture_output=True, text=True).stdout.strip()),
        "workload": "reports/plan12-memory-m3-part2/targets.json k2_contention, unchanged",
        "populate_seconds": populate_seconds,
        "barrier_after_s": round(barrier - window, 1),
        "writer_finished_after_barrier_s": [None if t is None else round(t - barrier, 1) for t in writers.finished],
        "interval_s": round(end - barrier, 1),
        "overlap": "ESTABLISHED" if overlap else "INCOMPLETE",
        "measured": measured, "targets": {k: targets[k] for k in ("ack_p95_s", "projection_after_ack_p95_ms", "physical_ram_gib",
                                                                   "peak_persistence_disk_gib", "acknowledged_write_loss")},
        "verdicts": verdicts,
        "ack_ms_whole_run": k2._summary([latency for _at, latency in writers.acks], 1000),
        "ack_ms_interval": k2._summary(inside, 1000), "projection_ms_interval": k2._summary(projected, 1000),
        "refusals": writers.refusals, "writers_unconfirmed": len(writers.failed), "writer_identity": identity, "bi_identity": bi_check,
        "legs": legs, "generations": verified, "sample": sample,
        "observations_only": "backup and import durations: no threshold exists",
    }
    confirmed = sum(1 for _item, _event, state in legs["import"]["notices"] if state == "confirmed")
    result["import_confirmed"] = confirmed
    verdicts["import_all_confirmed"] = confirmed == workload["import_leg"]["entries"]
    result["status"] = ("INCOMPLETE" if not overlap else "PASS" if all(verdicts.values()) and all(
        v["verified"] for v in verified.values()) and len(verified) == 2 else "FAIL")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    return result


def _import_positions(provisioned: Any, notices: list[tuple[str, str, str]]) -> list[tuple[str, str]]:
    """Each confirmed import commit's stream position, read from p-bi-0's stream."""
    from optimus_gateway import memory_store

    wanted = {event_id: item for item, event_id, state in notices if state == "confirmed"}
    found = []
    for stream_id, fields in provisioned.connect().xrange(memory_store.MemoryStore._key(BI, "events")):
        event = json.loads(fields[b"e"]).get("event") or {}
        if event.get("event_id") in wanted:
            found.append((wanted[event["event_id"]], stream_id.decode() if isinstance(stream_id, bytes) else stream_id))
    return found


def _bi_check(provisioned: Any, work: Path, initial: dict[str, str], imported_at: list[tuple[str, str]]) -> dict[str, Any]:
    """p-bi-0 after the window, read by a fresh Gateway: every initial item unchanged, every confirmed import present."""
    fresh = k2._service(provisioned, work / "journal-check-bi")
    seen: dict[str, dict[str, Any]] = {}
    for scope in ("project",):
        cursor = None
        while True:
            code, reply = k2._call(fresh, {"op": "list", "project": BI, "scope": scope, "limit": 100, **({"cursor": cursor} if cursor else {})})
            if code != 200:
                code, reply = k2._call(fresh, {"op": "list", "project": BI, "scope": scope, "limit": 100, **({"cursor": cursor} if cursor else {})})
            assert code == 200, reply
            seen.update({record["item"]: record for record in reply["items"]})
            cursor = reply["cursor"]
            if cursor is None:
                break
    missing = sum(1 for item, digest in initial.items() if item not in seen or k2._digest(seen[item]["statement"]) != digest)
    missing += sum(1 for item, _at in imported_at if item not in seen or seen[item]["trust"] != "legacy-import")
    return {"initial": len(initial), "imports_confirmed": len(imported_at), "missing": missing, "listed": len(seen)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run(args.output)
    print(result["status"], result["overlap"], json.dumps(result["measured"]), json.dumps(result["verdicts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
