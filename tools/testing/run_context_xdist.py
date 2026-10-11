"""pytest-xdist workers inside one controller-owned run (Plan 11.30 Task 5; v4 design contract 5).

Test tooling only, used from `tests/conftest.py`. The controller is the ordinary run context: it alone owns the run
ID, the Windows job and guard, the registry announcement, the run's streams and its terminal verdict. A worker owns
none of them. It receives the run's metadata, with a per-run secret, from its controller through xdist's own
channel (never the environment); installs the guard in its own interpreter before collection; checks that its
controller is among its running ancestors; and writes one signed record of who it is. It announces nothing, enrols
in no job and never writes the run's streams: the controller records every phase it is sent, with the worker that
ran it.

At the end the controller judges the workers: each one expected, never crashed, its signed record present and its
own, its process unique, its ancestry, guard and sources the controller's, every phase it sent received exactly
once, every selected test complete, and every worker (and on Windows every other member of the run's job) ended.
Anything else makes the run INVALID, whatever pytest's own exit status says. Without Windows' creation-time
ancestry and job the capability is labelled weaker.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

from tools.testing import run_context
from tools.testing import run_context_guard as guard
from tools.testing import run_context_records as records
from tools.testing import run_context_windows as native

WORKER_INPUT = "p1130_run"
WORKER_OUTPUT = "p1130_worker"
# How long the controller waits, at its end, for workers and stray job members to end before calling them survivors.
END_WAIT_SECONDS = 15.0
_FACTS = ("python", "pytest", "lock_sha256", "config_sha256")


def is_worker(config: object) -> bool:
    """Whether this pytest session is an xdist worker."""
    return hasattr(config, "workerinput")


def node_key(nodeid: str) -> str:
    """The exact identity of a test, as the run's streams record it."""
    return run_context._node(nodeid)  # noqa: SLF001 - one definition of a node's identity


def sign(token: str, record: dict[str, object]) -> str:
    """The record's signature under the run's secret: an HMAC of its canonical text, without the signature and the
    schema tag the sink adds. Digest only: the canonical text is never persisted or sent anywhere."""
    body = json.dumps({name: value for name, value in record.items() if name not in ("signature", "schema")},
                      sort_keys=True, separators=(",", ":"))
    return hmac.new(token.encode("ascii"), body.encode("utf-8"), sha256).hexdigest()


def write_worker_record(target: Path, record: dict[str, object], *, token: str) -> None:
    """Sign a worker record with the run's secret and persist it through the run context's single sink."""
    records.write_worker_record(target, {**record, "signature": sign(token, record)})


# --- worker side ---------------------------------------------------------------------------------------------


@dataclass
class Worker:
    worker: str
    run_id: str
    controller_root: dict[str, object]
    guard_mode: str
    pid: int
    creation_time: int | None
    phases: int = 0


_worker: Worker | None = None


def current_worker() -> Worker | None:
    """This interpreter's worker state, when it is an xdist worker of a controller-owned run."""
    return _worker


def _metadata(payload: object) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    root = payload.get("root")
    wanted = (isinstance(payload.get("run_id"), str) and isinstance(payload.get("token"), str)
              and isinstance(payload.get("records"), str) and payload.get("mode") in (run_context.ACTIVE, run_context.PASSIVE)
              and isinstance(root, dict) and isinstance(root.get("pid"), int))
    return payload if wanted else None


def _identity() -> tuple[int, int | None]:
    if native.supported():
        own = native.current_identity()
        return own.pid, own.creation_time
    return os.getpid(), None


def _proc_parent(pid: int) -> int | None:
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        return int(text.rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return None


def _ancestry(root: dict[str, Any]) -> dict[str, object]:
    """Whether the controller's root process is among this worker's running ancestors.

    On Windows by validated creation-time ancestry; elsewhere by the /proc parent chain, which names a PID only."""
    if native.supported():
        chain, stopped = native.ancestors()
        if any(found.pid == root.get("pid") and found.creation_time == root.get("creation_time") for found in chain):
            return {"status": "controller", "method": "validated_process_ancestry"}
        return {"status": "not_found", "method": "validated_process_ancestry", "reason": stopped}
    current = os.getpid()
    for _ in range(64):
        parent = _proc_parent(current)
        if parent is None or parent <= 1:
            break
        if parent == root.get("pid"):
            return {"status": "pid_ancestry", "method": "proc_parent_chain"}
        current = parent
    return {"status": "not_found", "method": "proc_parent_chain", "reason": "chain_ended"}


def _source_facts(worktree: Path) -> dict[str, object]:
    facts = run_context._session_facts(worktree)  # noqa: SLF001 - the same facts the controller records
    _branch, head = run_context._git_identity(worktree)  # noqa: SLF001
    return {**{name: facts.get(name) for name in _FACTS}, "head": head}


def start_worker(config: object) -> Worker:
    """Attach this worker to its controller's run: metadata, guard, ancestry and one signed record.

    A worker started without valid run metadata from its controller refuses to collect anything."""
    import pytest

    global _worker
    workerinput = config.workerinput  # type: ignore[attr-defined]
    worker = str(workerinput.get("workerid"))
    # Taken out of the worker's configuration once read: no test in the worker can read the run's secret.
    payload = _metadata(workerinput.pop(WORKER_INPUT, None))
    if payload is None:
        raise pytest.UsageError(
            f"TEST_RUN_CONTEXT_XDIST_WORKER_METADATA: worker {worker} has no valid run metadata from its controller"
        )
    guard_mode = guard.install() if payload["mode"] == run_context.ACTIVE else "not_installed"
    pid, created = _identity()
    record: dict[str, object] = {
        "run_id": payload["run_id"], "worker": worker, "pid": pid, "creation_time": created,
        "ancestry": _ancestry(payload["root"]), "guard_mode": guard_mode,
        "facts": _source_facts(Path(str(config.rootpath))),  # type: ignore[attr-defined]
    }
    write_worker_record(Path(payload["records"]) / f"{worker}.json", record, token=payload["token"])
    _worker = Worker(worker, payload["run_id"], dict(payload["root"]), guard_mode, pid, created)
    return _worker


def count_phase() -> None:
    if _worker is not None:
        _worker.phases += 1


def worker_output(config: object, *, deselected: list[str], unrun: int, summary: str | None) -> None:
    """What this worker tells its controller at its end, through xdist's own channel."""
    if _worker is None:
        return
    config.workeroutput[WORKER_OUTPUT] = {  # type: ignore[attr-defined]
        "pid": _worker.pid, "creation_time": _worker.creation_time, "phases": _worker.phases,
        "deselected": list(deselected), "unrun": int(unrun), "summary": summary,
    }


# --- controller side -----------------------------------------------------------------------------------------


@dataclass
class WorkerFacts:
    """What the controller learned about one worker."""

    collected: tuple[str, ...] | None = None
    output: dict[str, Any] = field(default_factory=dict)
    error: object = None
    down: bool = False
    received: int = 0
    # Whether the controller itself found the worker's recorded identity in the run's job while it ran (native only).
    member: bool | None = None


class Controller:
    """The controller's view of its workers, and the terminal verdict on them."""

    def __init__(self, *, run_id: str, root: dict[str, object], guard_mode: str, facts: dict[str, object],
                 records: Path, native: bool, mode: str = run_context.ACTIVE, token: str | None = None) -> None:
        self.run_id, self.root, self.guard_mode, self.facts = run_id, dict(root), guard_mode, dict(facts)
        self.records, self.native, self.mode = records, native, mode
        self.token = token or secrets.token_hex(32)
        self.expected: list[str] = []
        self.workers: dict[str, WorkerFacts] = {}
        # (test, phase) -> (the worker whose channel delivered it, its outcome): what the verdict proves execution from.
        self.phases: dict[tuple[str, str], tuple[str, str]] = {}
        self.misattributed: list[str] = []
        self.selected: tuple[str, ...] | None = None
        self.disagreement = False
        self.duplicates = 0
        self.unknown = 0

    def node_input(self, worker: str) -> dict[str, object]:
        """The run metadata handed to one worker before it starts."""
        self.expected.append(worker)
        self.workers[worker] = WorkerFacts()
        return {"run_id": self.run_id, "token": self.token, "root": dict(self.root), "mode": self.mode,
                "records": str(self.records)}

    def collection(self, worker: str, ids: list[str] | tuple[str, ...]) -> bool:
        """One worker's collected tests. True the first time, when the caller records the selection."""
        facts = self.workers.get(worker)
        if facts is None:
            self.unknown += 1
            return False
        facts.collected = tuple(ids)
        if self.selected is None:
            self.selected = facts.collected
            return True
        if facts.collected != self.selected:
            self.disagreement = True
        return False

    def confirm_member(self, worker: str) -> None:
        """Confirm, independently of anything the worker says, that the identity its record names is a running
        member of the run's job. Called while the worker runs (after its collection); native platforms only."""
        facts = self.workers.get(worker)
        record = records.read_worker_record(self.records / f"{worker}.json")
        if facts is None or record is None or not self.native:
            return
        identity = native.ProcessIdentity(int(record["pid"]), record["creation_time"])  # type: ignore[arg-type]
        facts.member = native.is_member(identity)

    def phase(self, report: object) -> None:
        """One phase report forwarded by a worker, attributed to the channel xdist received it on (`report.node`);
        the `worker_id` inside it is only the worker's own claim, and a disagreement is kept for the verdict."""
        claimed = getattr(report, "worker_id", None)
        gateway = getattr(getattr(report, "node", None), "gateway", None)
        worker = str(claimed if gateway is None else gateway.id)
        facts = self.workers.get(worker)
        if facts is None:
            self.unknown += 1
            return
        if claimed is not None and str(claimed) != worker:
            self.misattributed.append(worker)
        facts.received += 1
        key = (node_key(str(report.nodeid)), str(report.when))  # type: ignore[attr-defined]
        if key in self.phases:
            self.duplicates += 1
        else:
            self.phases[key] = (worker, str(getattr(report, "outcome", "")))

    def down(self, worker: str, output: dict[str, Any] | None, error: object) -> None:
        facts = self.workers.get(worker)
        if facts is None:
            self.unknown += 1
            return
        facts.output, facts.error, facts.down = dict(output or {}), error, True

    def _execution_problems(self) -> list[str]:
        """What the phases prove about execution, beyond their totals (Codex D-M1). Every phase belongs to a test of
        the agreed selection; each selected test has its setup and teardown, all from one worker; a passing setup is
        followed by its call, and a setup that skipped or failed by none (pytest never calls after it)."""
        problems: list[str] = []
        selected = {node_key(node) for node in self.selected or ()}
        if any(node not in selected for node, _ in self.phases):
            problems.append("unselected_phase")
        for node in selected:
            setup, call, teardown = (self.phases.get((node, when)) for when in ("setup", "call", "teardown"))
            if setup is None or teardown is None:
                problems.append("node_incomplete")
                continue
            if setup[1] == "passed" and call is None:
                problems.append("call_missing")
            if setup[1] != "passed" and call is not None:
                problems.append("call_unexpected")
            if len({phase[0] for phase in (setup, call, teardown) if phase is not None}) != 1:
                problems.append("mixed_owner")
        return problems

    def verdict(self, *, ended: dict[str, str], survivors: list[dict[str, object]] | None) -> dict[str, object]:
        """Every worker judged; any problem makes the run INVALID. `survivors` None: the job's members are unknown."""
        problems: list[str] = []
        identities: list[dict[str, object]] = []
        claimed: list[tuple[object, object]] = []
        for worker in self.expected:
            facts = self.workers.get(worker)
            if facts is None or not facts.down:
                problems.append(f"worker_missing:{worker}")
                continue
            if facts.error is not None:
                problems.append(f"crashed:{worker}")
            if facts.collected is None:
                problems.append(f"collection_missing:{worker}")
            sent = facts.output.get(WORKER_OUTPUT)
            record = records.read_worker_record(self.records / f"{worker}.json")
            if record is None:
                problems.append(f"record_missing:{worker}")
                continue
            if not hmac.compare_digest(str(record["signature"]), sign(self.token, record)):
                problems.append(f"signature:{worker}")
            if record["run_id"] != self.run_id:
                problems.append(f"run_mismatch:{worker}")
            if record["worker"] != worker:
                problems.append(f"worker_mismatch:{worker}")
            if not isinstance(sent, dict) or (sent.get("pid"), sent.get("creation_time")) != (record["pid"], record["creation_time"]):
                problems.append(f"identity_mismatch:{worker}")
            accepted = ("controller",) if self.native else ("controller", "pid_ancestry")
            if record["ancestry"].get("status") not in accepted:  # type: ignore[union-attr]
                problems.append(f"ancestry:{worker}")
            if record["guard_mode"] != self.guard_mode:
                problems.append(f"guard:{worker}")
            if record["facts"] != self.facts:
                problems.append(f"source:{worker}")
            if isinstance(sent, dict) and sent.get("phases") != facts.received:
                problems.append(f"phases_lost:{worker}")
            if self.native and facts.member is not True:
                problems.append(f"membership:{worker}")
            if ended.get(worker) != run_context.ENDED:
                problems.append(f"survivor:{worker}")
            claimed.append((record["pid"], record["creation_time"]))
            identities.append({"worker": worker, "pid": record["pid"], "creation_time": record["creation_time"]})
        if len(set(claimed)) != len(claimed):
            problems.append("identity_reused")
        if self.disagreement:
            problems.append("collection_disagreement")
        if self.duplicates:
            problems.append("duplicate_phase")
        if self.unknown:
            problems.append("unknown_worker")
        problems.extend(f"attribution:{worker}" for worker in self.misattributed)
        problems.extend(self._execution_problems())
        if survivors is None:
            problems.append("members_unknown")
        elif survivors:
            problems.append("escaped_descendants")
        unique = list(dict.fromkeys(problems))
        verdict: dict[str, object] = {
            "workers": len(self.expected), "verdict": "INVALID" if unique else "valid",
            "capability": "native" if self.native else "weaker", "problems": unique, "identities": identities,
        }
        if survivors:
            verdict["escaped"] = list(survivors)  # each with its parent, so it is attributable to a worker
        return verdict


_controller: Controller | None = None


def controller_for(context: run_context.RunContext) -> Controller:
    """This run's controller state, created when its first worker is configured."""
    global _controller
    if _controller is None or _controller.run_id != context.run_id:
        facts = {name: context.facts.get(name) for name in _FACTS}
        _controller = Controller(
            run_id=context.run_id, root={"pid": context.root.get("pid"), "creation_time": context.root.get("creation_time")},
            guard_mode=context.guard_mode, facts={**facts, "head": context.head}, records=context.record_dir / "workers",
            native=native.supported(), mode=context.mode,
        )
    return _controller


def current_controller() -> Controller | None:
    return _controller


def _wait_ended(identities: list[dict[str, object]]) -> dict[str, str]:
    """Each worker's end status, waiting up to END_WAIT_SECONDS for all of them to end."""
    deadline = time.monotonic() + END_WAIT_SECONDS
    while True:
        status = {str(item["worker"]): run_context.process_end_status(int(item["pid"]), item["creation_time"])[0]  # type: ignore[arg-type]
                  for item in identities}
        if all(value == run_context.ENDED for value in status.values()) or time.monotonic() >= deadline:
            return status
        time.sleep(0.2)


def _survivors() -> list[dict[str, object]] | None:
    """Members of the run's job, other than the controller itself, still running after the wait (Windows only);
    None when the members could not be listed."""
    if not native.supported():
        return []
    if native.owner() is None:
        return None  # a native platform without the run's job: its members are unknown, never "none escaped"
    own = os.getpid()
    deadline = time.monotonic() + END_WAIT_SECONDS
    while True:
        found, _error = native.members()
        others = [item for item in (found or []) if item.pid != own and item.live is not False]
        if found is not None and not others:
            return []
        if time.monotonic() >= deadline:
            if found is None:
                return None
            parents, _failure = native._parent_map(native._kernel32())  # noqa: SLF001 - one snapshot for attribution
            return [{"pid": item.pid, "creation_time": item.creation_time, "parent_pid": (parents or {}).get(item.pid)}
                    for item in others]
        time.sleep(0.2)


def finish_controller(controller: Controller) -> dict[str, object]:
    """The controller's terminal verdict on its workers, after waiting for them to end. Never raises: a failure in
    this terminal work is an INVALID verdict, so the run's terminal record is still written."""
    try:
        return _finish_controller(controller)
    except Exception:  # noqa: BLE001 - a terminal query that failed proves nothing about the workers
        return {"workers": len(controller.expected), "verdict": "INVALID",
                "capability": "native" if controller.native else "weaker", "problems": ["controller_failure"],
                "identities": []}


def _finish_controller(controller: Controller) -> dict[str, object]:
    readable = [
        {"worker": worker, "pid": record["pid"], "creation_time": record["creation_time"]}
        for worker in controller.expected
        if (record := records.read_worker_record(controller.records / f"{worker}.json")) is not None
    ]
    ended = _wait_ended(readable)
    return controller.verdict(ended=ended, survivors=_survivors() if controller.native else [])
