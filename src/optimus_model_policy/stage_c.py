"""Plan 12.2 Task 13 (Stage C): the source-owned test envelope and its durable dispatch guard (Codex scope
agreement, 2026-10-11).

One reviewed release shares one envelope across both test-profile launches (``qualification`` and
``attached``), the acpx and Zed sessions and any authorized restart: at most $8 of known charges plus
outstanding reservations, 138 physical upstream attempts (unbilled ones included) and one 60-minute window
that starts at the first Stage C Gateway open (release r9, the operator's approval of proposal 235d7b7e on 2026-10-17
after r8 stopped at B7.6 on a charged reply refusal; it rounds up the accepted $7.518097 / 138-attempt complete-case
reservation bound). Release r9 supersedes r8, r7, r6, r5, r4, r3 and r2 ($8, 138 attempts each; stopped and expired) and the
reviewed r1 ($0.50, 24 attempts): each release has its own ledger file and literal, so an earlier ledger is
never opened, reset or overwritten, and an earlier approval never authorizes an r9 launch. Its literal binds the release, the limits, both profiles' pinned
hashes, the fixed scenario catalogue and the resolved ledger file, and is carried by the HMAC launch
approval and the Gateway child's signed manifest; the Gateway composes the same envelope itself.

The ledger is an append-only JSON-lines file under the operator's trusted runtime root, initialized once
by the release ceremony; every Gateway start only reopens it, holding an exclusive lock for its life.
:class:`StageCGuard` admits one physical attempt at a time only when the window, the attempt count and
``known charges + outstanding reserves + the next full reserve <= limit`` allow it (equality admissible),
persisting the reservation before dispatch. It settles each attempt once: a provider-reported charge, a
proven unbilled outcome (the dollars are released, the attempt still counts) or an unknown result, which
stops every later dispatch. A restart replays the same totals and deadline; an unresolved, malformed or
divergent record stays in doubt and stops dispatch, never inferring a zero cost.

Test-only and scoped to this envelope: no product cost stop, production activation or shipped default
changes. The limits are empirical dispatch admission bounds under the registry's conservative prices and
the route's estimator; they do not guarantee that provider bills never exceed a reservation, that every
case finishes, or protection against deliberate edits to trusted runtime files.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import IO, Any, Final

from optimus_model_policy.binding import ATTEMPT_NOT_SENT, ATTEMPT_REJECTED, UPSTREAM_ATTEMPT_TIMEOUT_SECONDS, BindingError

__all__ = [
    "ATTEMPT_TIMEOUT_SECONDS",
    "ENVELOPE_LITERAL_PREFIX",
    "STAGE_C_LIMIT_USD",
    "STAGE_C_LITERAL_NAME",
    "STAGE_C_MAX_ATTEMPTS",
    "STAGE_C_PROFILES",
    "STAGE_C_PROFILE_HASHES",
    "STAGE_C_ATTACHED_SCENARIO",
    "STAGE_C_RELEASE_ID",
    "STAGE_C_SCENARIOS",
    "STAGE_C_WINDOW_SECONDS",
    "Admission",
    "GuardState",
    "LedgerStatus",
    "StageCEnvelope",
    "StageCGuard",
    "StageCLedgerError",
    "StageCRefusal",
    "compose_stage_c_envelope",
    "initialize_stage_c_ledger",
    "ledger_deadline",
    "require_stage_c_profile",
    "reservation_usd",
    "scenario_catalogue_digest",
    "stage_c_ledger_path",
    "stage_c_ledger_status",
]

STAGE_C_RELEASE_ID: Final = "plan12-2-stage-c-r9"
STAGE_C_LIMIT_USD: Final = Decimal("8")
STAGE_C_MAX_ATTEMPTS: Final = 138
STAGE_C_WINDOW_SECONDS: Final = 60 * 60
STAGE_C_PROFILES: Final = ("qualification", "attached")
STAGE_C_PROFILE_HASHES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "qualification": "048c1a2b3e7d3436d371e8964200064bb30f0a1a865c945f92a2fc09d3ba5cba",  # pragma: allowlist secret - registry identity, not a credential
        "attached": "06e637845f5f7cea2b4a22d23407c59efc9741d7848b06ee5f4c3d2284f3f07d",  # pragma: allowlist secret - registry identity, not a credential
    }
)
"""Release r9's own profile pins, fixed when Plan 12.4 v7 moved admission into the registry entries, so the historical
envelope's identity is unchanged. The migrated profiles compose other hashes (``require_stage_c_profile``)."""
ENVELOPE_LITERAL_PREFIX: Final = "optimus-stage-c-envelope-v1:"
STAGE_C_LITERAL_NAME: Final = "_stage_c_envelope"
"""The security-literal name under which a Stage C launch approval binds the envelope literal."""
ATTEMPT_TIMEOUT_SECONDS: Final = UPSTREAM_ATTEMPT_TIMEOUT_SECONDS
"""The Gateway's upstream attempt timeout, from the shared contract: an attempt is admitted only if it can time out
inside the window."""
_LEDGER_DIRECTORY: Final = "plan12-stage-c"

STAGE_C_ATTACHED_SCENARIO: Final = "attached-maintenance-v1"
# The fixed attached scenarios by name; their canonical content is part of the envelope's identity, so the
# launch approval and the Gateway manifest bind the whole scenario. The seed is generated by the host
# (`optimus.acp.stage_c.seed_history`) and must reproduce the pinned digest and byte count. Live turns
# count the designated session's attached turns from 1.
STAGE_C_SCENARIOS: Final[Mapping[str, Mapping[str, Any]]] = MappingProxyType(
    {
        STAGE_C_ATTACHED_SCENARIO: {
            "version": 1,
            "profile": "attached",
            "designated_session": "the first session/new of an attached Stage C launch; later sessions are not seeded",
            "seed": {
                "generator": "stage-c-seed-v1",
                "turns": 64,
                "completion_bytes": 9000,
                "synthetic_approvals": [16, 48],
                "records_sha256": "4b86709d353e59eef0db8a5a994df20c410dcab23481917e2f1939c120ff5f8d",  # pragma: allowlist secret - public seed digest
                "records_bytes": 590151,
            },
            "schedule": {
                "engine_unavailable_turns": [4, 5],
                "cancel_pause_turn": 7,
                "cancel_pause_before_call": 2,
                "cancel_wait_seconds": 30,
            },
        }
    }
)


def _digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def scenario_catalogue_digest(scenarios: Mapping[str, Mapping[str, Any]] = STAGE_C_SCENARIOS) -> str:
    """The SHA-256 of the scenario catalogue's canonical JSON (names and whole content)."""
    return _digest({name: dict(scenarios[name]) for name in sorted(scenarios)})


def reservation_usd(*, input_tokens: int, output_tokens: int, input_usd_per_million: Decimal, output_usd_per_million: Decimal) -> Decimal:
    """One attempt's full reservation: its input estimate and output cap at the given prices."""
    return (Decimal(input_tokens) * input_usd_per_million + Decimal(output_tokens) * output_usd_per_million) / Decimal(1_000_000)


@dataclass(frozen=True)
class StageCEnvelope:
    """One release's shared test envelope. ``profiles`` pairs each allowed profile with its pinned hash;
    ``scenarios`` is the scenario catalogue's digest; ``ledger`` is the resolved ledger file path."""

    release_id: str
    limit_usd: Decimal
    max_attempts: int
    window_seconds: int
    profiles: tuple[tuple[str, str], ...]
    scenarios: str
    ledger: str

    def canonical(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "limit_usd": str(self.limit_usd),
            "max_attempts": self.max_attempts,
            "window_seconds": self.window_seconds,
            "profiles": dict(self.profiles),
            "scenarios": self.scenarios,
            "ledger": self.ledger,
        }

    @property
    def literal(self) -> str:
        """The envelope's launch-security literal, bound by approval and the child manifest."""
        return ENVELOPE_LITERAL_PREFIX + _digest(self.canonical())


def stage_c_ledger_path(runtime_root: Path) -> Path:
    """The release's ledger file under the operator's trusted runtime root."""
    return runtime_root / _LEDGER_DIRECTORY / f"{STAGE_C_RELEASE_ID}.jsonl"


def compose_stage_c_envelope(*, ledger: Path) -> StageCEnvelope:
    """The reviewed release's envelope for the resolved ``ledger`` path."""
    if not ledger.is_absolute():
        raise BindingError("STAGE_C_LEDGER_NOT_ABSOLUTE", "the ledger path must be the resolved runtime path")
    profiles = [(name, STAGE_C_PROFILE_HASHES[name]) for name in STAGE_C_PROFILES]
    return StageCEnvelope(
        release_id=STAGE_C_RELEASE_ID,
        limit_usd=STAGE_C_LIMIT_USD,
        max_attempts=STAGE_C_MAX_ATTEMPTS,
        window_seconds=STAGE_C_WINDOW_SECONDS,
        profiles=tuple(profiles),
        scenarios=scenario_catalogue_digest(),
        ledger=str(ledger),
    )


def require_stage_c_profile(envelope: StageCEnvelope, profile: str, effective_hash: str) -> None:
    """Refuse a launch that pairs this release with a profile whose snapshot is not the release's own pin: after
    Plan 12.4 v7 moved admission into the registry entries, the migrated profiles compose other hashes, so the
    historical release keeps its identity and gains no new authority."""
    if dict(envelope.profiles).get(profile) != effective_hash:
        raise BindingError("STAGE_C_PROFILE_MIGRATED", "the release pins another snapshot for this profile")


# --- The ledger --------------------------------------------------------------------------------------------


def ledger_deadline(path: Path) -> datetime | None:
    """The shared window's deadline as the ledger records it (read-only, no lock), or None before the
    first Gateway open or when it cannot be read."""
    try:
        for raw in path.read_bytes().splitlines()[1:]:
            record = json.loads(raw) if raw else None
            if isinstance(record, dict) and record.get("kind") == "window":
                return datetime.fromisoformat(record["deadline"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return None


class StageCLedgerError(Exception):
    """The ledger cannot be created or opened. ``code`` is stable."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


class StageCRefusal(Exception):
    """An attempt the envelope does not admit; nothing was dispatched. ``code`` is stable."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _write_failure_fact(exc: BaseException) -> dict[str, Any]:
    """A failed ledger write's class and errno, never its text (Codex round 13 finding 6). Local, not
    ``optimus_security.failure_facts``: this package may not import the security package."""
    name = type(exc).__name__
    number = getattr(exc, "errno", None)
    return {
        "class": name if name.isidentifier() and name.isascii() and len(name) <= 80 else "unrecognized",
        "errno": number if isinstance(number, int) and not isinstance(number, bool) else None,
    }


def _write_failure_text(fact: Mapping[str, Any]) -> str:
    return f"{fact['class']} errno {fact['errno']}" if fact["errno"] is not None else str(fact["class"])


def _write_record(handle: IO[bytes], record: Mapping[str, Any], fsync: Callable[[int], None]) -> None:
    handle.write((json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    handle.flush()
    fsync(handle.fileno())


def initialize_stage_c_ledger(
    path: Path, envelope: StageCEnvelope, *, clock: Callable[[], datetime] = _utc_now, fsync: Callable[[int], None] = os.fsync
) -> None:
    """Create the release's ledger once, for the release ceremony. An existing ledger is never replaced or
    reset; the window starts later, at the first Gateway open."""
    if str(path) != envelope.ledger:
        raise StageCLedgerError("STAGE_C_LEDGER_NOT_BOUND", "the ledger path is not the envelope's")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = path.open("xb")
    except FileExistsError as exc:
        raise StageCLedgerError("STAGE_C_LEDGER_EXISTS", "a ledger is never reset; the release keeps its totals") from exc
    with handle:
        _write_record(
            handle,
            {
                "kind": "init",
                "envelope": envelope.literal,
                "release_id": envelope.release_id,
                "limit_usd": str(envelope.limit_usd),
                "max_attempts": envelope.max_attempts,
                "window_seconds": envelope.window_seconds,
                "at": clock().isoformat(),
            },
            fsync,
        )


@dataclass(frozen=True)
class Admission:
    """One admitted physical attempt and its durable reservation."""

    number: int
    attempt_id: str
    reserve_usd: Decimal


@dataclass(frozen=True)
class GuardState:
    attempts: int
    charged_usd: Decimal
    outstanding_usd: Decimal
    halted: str | None
    overrun: bool
    window_start: datetime | None
    deadline: datetime | None


@dataclass
class _Replay:
    attempts: int = 0
    charged: Decimal = Decimal(0)
    outstanding: Admission | None = None
    settlements: dict[int, tuple[str, str | None]] = field(default_factory=dict)
    halted: str | None = None
    overrun: bool = False
    window_start: datetime | None = None
    deadline: datetime | None = None


def _decimal(text: Any) -> Decimal:
    if not isinstance(text, str):
        raise ValueError("a decimal is recorded as text")
    value = Decimal(text)
    if not value.is_finite() or value < 0:
        raise ValueError("a recorded amount is finite and non-negative")
    return value


class _Lock:
    """An exclusive, non-blocking lock on ``<ledger>.lock``, held for the guard's life."""

    def __init__(self, path: Path) -> None:
        self._handle = path.open("a+b")
        try:
            if sys.platform == "win32":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._handle.close()
            raise StageCLedgerError("STAGE_C_LEDGER_LOCKED", "another Gateway holds this ledger") from exc

    def release(self) -> None:
        try:
            if sys.platform == "win32":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self._handle.close()


class StageCGuard:
    """The durable dispatch guard of one envelope, for one Gateway process."""

    def __init__(self, path: Path, envelope: StageCEnvelope, lock: _Lock, handle: IO[bytes], replay: _Replay, *, clock, fsync) -> None:
        self.path = path
        self.envelope = envelope
        self._lock_file = lock
        self._handle = handle
        self._replay = replay
        self._clock = clock
        self._fsync = fsync
        self._write_failure = "unknown"
        # The last failed ledger write's class and errno, kept apart from the halt reason (which a write failure after
        # an earlier halt does not change) so the Gateway can log it (correction plan v4, C2). None until one fails.
        self.last_write_failure: dict[str, Any] | None = None
        self._mutex = threading.Lock()
        self.closed = False

    @classmethod
    def open(
        cls,
        path: Path,
        envelope: StageCEnvelope,
        *,
        clock: Callable[[], datetime] = _utc_now,
        fsync: Callable[[int], None] = os.fsync,
    ) -> StageCGuard:
        """Reopen the initialized ledger (never create it), replay its totals and start the window at the
        first open. Refuses a path that is not the envelope's, a missing, foreign or unreadable ledger and
        a ledger another Gateway holds."""
        if not path.is_absolute():
            raise StageCLedgerError("STAGE_C_LEDGER_NOT_ABSOLUTE")
        if str(path) != envelope.ledger:
            raise StageCLedgerError("STAGE_C_LEDGER_NOT_BOUND", "the ledger path is not the envelope's")
        if path.is_symlink() or not path.is_file():
            raise StageCLedgerError("STAGE_C_LEDGER_MISSING", "initialize the release's ledger first; a start never creates one")
        lock = _Lock(path.with_name(path.name + ".lock"))
        try:
            replay = cls._replay_ledger(path, envelope)
            handle = path.open("ab")
            guard = cls(path, envelope, lock, handle, replay, clock=clock, fsync=fsync)
            if replay.halted is None and replay.deadline is None:
                guard._start_window()
            return guard
        except BaseException:
            lock.release()
            raise

    @staticmethod
    def _replay_ledger(path: Path, envelope: StageCEnvelope) -> _Replay:
        lines = path.read_bytes().split(b"\n")
        try:
            init = json.loads(lines[0])
            if not isinstance(init, dict) or init.get("kind") != "init":
                raise ValueError("the first record is not the initialization")
        except ValueError as exc:
            raise StageCLedgerError("STAGE_C_LEDGER_CORRUPT", "the initialization record is unreadable") from exc
        if init.get("envelope") != envelope.literal:
            raise StageCLedgerError("STAGE_C_LEDGER_ENVELOPE_MISMATCH", "the ledger was initialized for another envelope")
        state = _Replay()
        for number, raw in enumerate(lines[1:], start=2):
            if raw == b"" and number == len(lines):
                break  # the newline after the last complete record
            try:
                StageCGuard._apply(state, json.loads(raw))
            except (ValueError, KeyError, TypeError, InvalidOperation):
                state.halted = state.halted or f"malformed record at line {number}"
                break
        if state.halted is None and state.outstanding is not None:
            state.halted = f"attempt {state.outstanding.number} unresolved at restart (in doubt)"
        return state

    @staticmethod
    def _apply(state: _Replay, record: Any) -> None:
        if not isinstance(record, dict):
            raise ValueError("a record is an object")
        kind = record["kind"]
        if kind == "window":
            if state.deadline is not None:
                raise ValueError("the window is recorded once")
            state.window_start, state.deadline = datetime.fromisoformat(record["start"]), datetime.fromisoformat(record["deadline"])
        elif kind == "reserve":
            if state.outstanding is not None or record["n"] != state.attempts + 1:
                raise ValueError("a reservation follows a settled attempt in order")
            state.outstanding = Admission(record["n"], record["attempt_id"], _decimal(record["reserve_usd"]))
            state.attempts += 1
        elif kind == "settle":
            n, result, cost = record["n"], record["result"], record["cost_usd"]
            if n in state.settlements:
                if state.settlements[n] != (result, cost):
                    state.halted = state.halted or f"divergent settlement of attempt {n}"
                return
            if state.outstanding is None or state.outstanding.number != n or result not in ("charged", "unbilled", "unknown"):
                raise ValueError("a settlement names the outstanding attempt")
            if result == "charged":
                charge = _decimal(cost)
                state.charged += charge
                if charge > state.outstanding.reserve_usd:
                    state.overrun = True
                    state.halted = state.halted or f"attempt {n} charged over its reservation"
            elif cost is not None:
                raise ValueError("only a charged result records a cost")
            elif result == "unknown":
                state.halted = state.halted or f"attempt {n} has an unknown charge"
            state.settlements[n] = (result, cost)
            state.outstanding = None
        elif kind == "halt":
            state.halted = state.halted or str(record["reason"])
            state.overrun = state.overrun or bool(record.get("overrun", False))
        else:
            raise ValueError(f"unknown record kind {kind!r}")

    # --- Durable writes ------------------------------------------------------------------------------------

    def _append(self, record: Mapping[str, Any]) -> bool:
        try:
            _write_record(self._handle, record, self._fsync)
            return True
        except (OSError, ValueError) as exc:
            self.last_write_failure = _write_failure_fact(exc)
            self._write_failure = _write_failure_text(self.last_write_failure)
            self._replay.halted = self._replay.halted or f"ledger write failed ({self._write_failure})"
            return False

    def _start_window(self) -> None:
        start = self._clock()
        deadline = start + timedelta(seconds=self.envelope.window_seconds)
        if self._append({"kind": "window", "start": start.isoformat(), "deadline": deadline.isoformat()}):
            self._replay.window_start, self._replay.deadline = start, deadline

    def _halt(self, reason: str, *, overrun: bool = False) -> None:
        self._replay.halted = self._replay.halted or reason
        self._replay.overrun = self._replay.overrun or overrun
        self._append({"kind": "halt", "reason": reason, "at": self._clock().isoformat(), **({"overrun": True} if overrun else {})})

    # --- Admission and settlement ---------------------------------------------------------------------------

    @property
    def state(self) -> GuardState:
        with self._mutex:
            r = self._replay
            outstanding = r.outstanding.reserve_usd if r.outstanding is not None else Decimal(0)
            return GuardState(r.attempts, r.charged, outstanding, r.halted, r.overrun, r.window_start, r.deadline)

    def remaining_seconds(self) -> float:
        """Seconds left in the shared window (zero or less once it has passed)."""
        deadline = self._replay.deadline
        return 0.0 if deadline is None else (deadline - self._clock()).total_seconds()

    def admit(self, *, attempt_id: str, request_id: str, reserve_usd: Decimal) -> Admission:
        """Admit one physical attempt and persist its reservation before dispatch, or refuse it."""
        with self._mutex:
            r = self._replay
            if r.halted is not None:
                raise StageCRefusal("STAGE_C_HALTED", r.halted)
            if r.outstanding is not None:
                raise StageCRefusal("STAGE_C_ATTEMPT_IN_FLIGHT", "one attempt is in flight per envelope")
            if not reserve_usd.is_finite() or reserve_usd <= 0:
                raise StageCRefusal("STAGE_C_RESERVE_INVALID", "a reservation is a positive amount")
            now = self._clock()
            if r.deadline is None or now + timedelta(seconds=ATTEMPT_TIMEOUT_SECONDS) > r.deadline:
                raise StageCRefusal("STAGE_C_WINDOW_EXHAUSTED", "the attempt could not time out inside the window")
            if r.attempts + 1 > self.envelope.max_attempts:
                raise StageCRefusal("STAGE_C_ATTEMPTS_EXHAUSTED", f"{r.attempts} of {self.envelope.max_attempts} attempts used")
            if r.charged + reserve_usd > self.envelope.limit_usd:
                raise StageCRefusal("STAGE_C_BUDGET_EXHAUSTED", f"known charges {r.charged} USD plus this reservation exceed {self.envelope.limit_usd} USD")
            admission = Admission(r.attempts + 1, attempt_id, reserve_usd)
            record = {"kind": "reserve", "n": admission.number, "attempt_id": attempt_id, "request_id": request_id, "reserve_usd": str(reserve_usd), "at": now.isoformat()}
            if not self._append(record):
                raise StageCRefusal(
                    "STAGE_C_LEDGER_WRITE_FAILED", f"the reservation is not durable, so nothing is dispatched ({self._write_failure})"
                )
            r.outstanding, r.attempts = admission, admission.number
            return admission

    def settle_charged(self, admission: Admission, cost_usd: Decimal | None) -> None:
        """Settle a completed attempt with its provider-reported charge, before any later check can fail
        the call. No known charge is an unknown result."""
        if cost_usd is None or not cost_usd.is_finite() or cost_usd < 0:
            self.settle_unknown(admission, "no known charge")
            return
        self._settle(admission, "charged", str(cost_usd), cost_usd)

    def settle_unbilled(self, admission: Admission, outcome: str) -> None:
        """Release a proven unbilled attempt's dollars (never sent, or refused before any model ran); the
        attempt stays counted. Any other outcome is unknown."""
        if outcome not in (ATTEMPT_NOT_SENT, ATTEMPT_REJECTED):
            self.settle_unknown(admission, f"attempt {outcome}")
            return
        self._settle(admission, "unbilled", None, Decimal(0), outcome=outcome)

    def settle_unknown(self, admission: Admission, reason: str) -> None:
        """Record an attempt whose charge is unknown and stop every later dispatch."""
        self._settle(admission, "unknown", None, None, reason=reason)

    def _settle(self, admission: Admission, result: str, cost_text: str | None, charge: Decimal | None, *, outcome: str | None = None, reason: str | None = None) -> None:
        with self._mutex:
            r = self._replay
            if admission.number in r.settlements:
                if r.settlements[admission.number] != (result, cost_text):
                    self._halt(f"divergent settlement of attempt {admission.number}")
                return
            if r.outstanding is None or r.outstanding.number != admission.number:
                self._halt(f"settlement of attempt {admission.number}, which is not outstanding")
                return
            record: dict[str, Any] = {"kind": "settle", "n": admission.number, "result": result, "cost_usd": cost_text, "at": self._clock().isoformat()}
            if outcome is not None:
                record["outcome"] = outcome
            if reason is not None:
                record["reason"] = reason
            if not self._append(record):
                return  # stays outstanding on disk: in doubt at the next start
            r.settlements[admission.number] = (result, cost_text)
            r.outstanding = None
            if result == "unknown":
                self._halt(f"attempt {admission.number} has an unknown charge")
            elif charge is not None:
                r.charged += charge
                if charge > admission.reserve_usd or r.charged > self.envelope.limit_usd:
                    self._halt(f"attempt {admission.number} charged {charge} USD over its reservation or the limit", overrun=True)

    def close(self) -> None:
        """Release the ledger for the next Gateway start. Safe to call twice."""
        if self.closed:
            return
        self.closed = True
        try:
            self._handle.close()
        finally:
            self._lock_file.release()


# --- Read-only status between launches ------------------------------------------------------------------------


@dataclass(frozen=True)
class LedgerStatus:
    """The release ledger as a custody check sees it between client launches."""

    lock_free: bool
    state: GuardState


def stage_c_ledger_status(path: Path, envelope: StageCEnvelope) -> LedgerStatus:
    """Whether any Gateway holds the release ledger, and the totals and window the next start would replay
    (Codex completion review R4). Read-only: it never writes the ledger, starts the window or repairs
    anything; the lock is only probed, taken and released at once."""
    if path.is_symlink() or not path.is_file():
        raise StageCLedgerError("STAGE_C_LEDGER_MISSING", "initialize the release's ledger first; a check never creates one")
    try:
        _Lock(path.with_name(path.name + ".lock")).release()
        lock_free = True
    except StageCLedgerError:
        lock_free = False
    r = StageCGuard._replay_ledger(path, envelope)
    outstanding = r.outstanding.reserve_usd if r.outstanding is not None else Decimal(0)
    return LedgerStatus(lock_free, GuardState(r.attempts, r.charged, outstanding, r.halted, r.overrun, r.window_start, r.deadline))
