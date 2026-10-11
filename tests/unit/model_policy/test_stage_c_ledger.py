"""Plan 12.2 Task 13 (Stage C): the durable dispatch guard for the shared test envelope (scope agreement,
2026-10-11, section 4).

The ledger is initialized once, by the later release ceremony; every Gateway start only reopens it. Before
each physical upstream attempt the guard checks the window, the attempt count and `known charges +
outstanding reserves + the next full reserve <= $0.50`, and persists the reservation before dispatch.
Each attempt is settled once: a known charge, a proven unbilled outcome (its attempt still counts) or an
unknown one, which stops every later dispatch. A restart replays the same totals and deadline; anything
unresolved or unreadable stays in doubt and stops dispatch. One writer, one attempt in flight.
Fake clocks and temporary files only: no Gateway, provider or service.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from optimus_model_policy import stage_c
from optimus_model_policy.stage_c import StageCGuard, StageCLedgerError, StageCRefusal

T0 = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
TIMEOUT = stage_c.ATTEMPT_TIMEOUT_SECONDS
RESERVE = Decimal("0.10")


class Clock:
    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _initialized(tmp_path: Path, clock: Clock | None = None) -> tuple[Path, stage_c.StageCEnvelope]:
    path = stage_c.stage_c_ledger_path(tmp_path)
    envelope = stage_c.compose_stage_c_envelope(ledger=path)
    stage_c.initialize_stage_c_ledger(path, envelope, clock=clock or Clock())
    return path, envelope


@pytest.fixture
def opened(tmp_path: Path):
    """An initialized ledger and a guard open on it; every guard opened through `reopen` is closed."""
    clock = Clock()
    path, envelope = _initialized(tmp_path, clock)
    guards: list[StageCGuard] = []

    def reopen(**kwargs) -> StageCGuard:
        for guard in guards:
            guard.close()
        guards.clear()
        guards.append(StageCGuard.open(path, envelope, clock=kwargs.pop("clock", clock), **kwargs))
        return guards[-1]

    yield reopen, clock, path, envelope
    for guard in guards:
        guard.close()


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _admit(guard: StageCGuard, n: int, reserve: Decimal = RESERVE) -> stage_c.Admission:
    return guard.admit(attempt_id=f"gw-{n:032x}", request_id=f"host-req-{n}", reserve_usd=reserve)


def _refused(guard: StageCGuard, code: str, reserve: Decimal = RESERVE) -> None:
    with pytest.raises(StageCRefusal) as caught:
        _admit(guard, 99, reserve)
    assert caught.value.code == code


# --- Initialization and reopening -----------------------------------------------------------------------------


def test_the_ledger_is_initialized_once_and_never_reset(tmp_path: Path) -> None:
    path, envelope = _initialized(tmp_path)
    [init] = _records(path)
    assert (init["kind"], init["envelope"], init["release_id"], init["limit_usd"], init["max_attempts"], init["window_seconds"]) == (
        "init", envelope.literal, stage_c.STAGE_C_RELEASE_ID, "0.50", 24, 3600
    )  # fmt: skip

    with pytest.raises(StageCLedgerError) as caught:
        stage_c.initialize_stage_c_ledger(path, envelope, clock=Clock())
    assert caught.value.code == "STAGE_C_LEDGER_EXISTS"
    assert len(_records(path)) == 1


def test_a_start_only_reopens_a_ledger_it_did_not_create(tmp_path: Path) -> None:
    path = stage_c.stage_c_ledger_path(tmp_path)
    envelope = stage_c.compose_stage_c_envelope(ledger=path)
    with pytest.raises(StageCLedgerError) as caught:
        StageCGuard.open(path, envelope, clock=Clock())
    assert caught.value.code == "STAGE_C_LEDGER_MISSING"
    assert not path.exists()


def test_a_ledger_for_another_envelope_is_refused(tmp_path: Path) -> None:
    path, envelope = _initialized(tmp_path)
    other = stage_c.StageCEnvelope(**{**envelope.__dict__, "max_attempts": 25})
    with pytest.raises(StageCLedgerError) as caught:
        StageCGuard.open(path, other, clock=Clock())
    assert caught.value.code == "STAGE_C_LEDGER_ENVELOPE_MISMATCH"


def test_the_ledger_must_be_the_envelopes_own_file(tmp_path: Path) -> None:
    path, envelope = _initialized(tmp_path)
    copy = tmp_path / "copy.jsonl"
    copy.write_bytes(path.read_bytes())
    with pytest.raises(StageCLedgerError) as caught:
        StageCGuard.open(copy, envelope, clock=Clock())
    assert caught.value.code == "STAGE_C_LEDGER_NOT_BOUND"


def test_one_writer_holds_the_ledger(opened) -> None:
    reopen, clock, path, envelope = opened
    reopen()
    with pytest.raises(StageCLedgerError) as caught:
        StageCGuard.open(path, envelope, clock=clock)
    assert caught.value.code == "STAGE_C_LEDGER_LOCKED"


def test_the_window_starts_at_the_first_open_and_restarts_never_extend_it(opened) -> None:
    reopen, clock, path, _ = opened
    guard = reopen()
    assert guard.state.deadline == T0 + timedelta(seconds=3600)
    clock.now = T0 + timedelta(minutes=50)
    assert reopen().state.deadline == T0 + timedelta(seconds=3600)
    assert [r["kind"] for r in _records(path)] == ["init", "window"]


# --- Admission boundaries -------------------------------------------------------------------------------------


def test_dollars_admit_at_equality_and_refuse_one_unit_over(opened) -> None:
    reopen, *_ = opened
    guard = reopen()
    guard.settle_charged(_admit(guard, 1, Decimal("0.30")), Decimal("0.30"))
    _refused(guard, "STAGE_C_BUDGET_EXHAUSTED", Decimal("0.2000001"))
    admission = _admit(guard, 2, Decimal("0.20"))
    assert admission.number == 2
    assert guard.state.outstanding_usd == Decimal("0.20") and guard.state.charged_usd == Decimal("0.30")


def test_attempts_admit_the_24th_and_refuse_the_25th_unbilled_ones_included(opened) -> None:
    reopen, *_ = opened
    guard = reopen()
    for n in range(1, 25):
        admission = _admit(guard, n, Decimal("0.001"))
        guard.settle_unbilled(admission, "not_sent") if n % 2 else guard.settle_charged(admission, Decimal("0"))
    assert guard.state.attempts == 24 and guard.state.charged_usd == Decimal("0")
    _refused(guard, "STAGE_C_ATTEMPTS_EXHAUSTED", Decimal("0.001"))


def test_an_attempt_starts_only_if_it_can_time_out_inside_the_window(opened) -> None:
    reopen, clock, *_ = opened
    guard = reopen()
    clock.now = T0 + timedelta(seconds=3600 - TIMEOUT)
    guard.settle_charged(_admit(guard, 1), Decimal("0.01"))  # equality: it times out exactly at the deadline
    clock.now += timedelta(microseconds=1)
    _refused(guard, "STAGE_C_WINDOW_EXHAUSTED")
    assert guard.remaining_seconds() == pytest.approx(TIMEOUT - 1e-6)


def test_only_one_attempt_is_in_flight(opened) -> None:
    reopen, *_ = opened
    guard = reopen()
    first = _admit(guard, 1)
    _refused(guard, "STAGE_C_ATTEMPT_IN_FLIGHT")
    guard.settle_charged(first, Decimal("0.01"))
    assert _admit(guard, 2).number == 2


def test_concurrent_admissions_dispatch_one(opened) -> None:
    reopen, *_ = opened
    guard = reopen()
    barrier, results = threading.Barrier(8), []

    def race(n: int) -> None:
        barrier.wait()
        try:
            results.append(("admitted", _admit(guard, n).number))
        except StageCRefusal as exc:
            results.append(("refused", exc.code))

    threads = [threading.Thread(target=race, args=(n,)) for n in range(1, 9)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert [r for r in results if r[0] == "admitted"] == [("admitted", 1)]
    assert {r[1] for r in results if r[0] == "refused"} == {"STAGE_C_ATTEMPT_IN_FLIGHT"}


def test_an_invalid_reservation_is_refused(opened) -> None:
    reopen, *_ = opened
    guard = reopen()
    for bad in (Decimal("0"), Decimal("-0.01"), Decimal("NaN")):
        _refused(guard, "STAGE_C_RESERVE_INVALID", bad)


# --- Settlement ------------------------------------------------------------------------------------------------


def test_the_reservation_is_durable_before_dispatch(opened) -> None:
    reopen, _, path, _ = opened
    guard = reopen()
    admission = _admit(guard, 1)
    reserve = _records(path)[-1]
    assert (reserve["kind"], reserve["n"], reserve["reserve_usd"], reserve["attempt_id"]) == ("reserve", 1, "0.10", admission.attempt_id)
    assert set(reserve) == {"kind", "n", "attempt_id", "request_id", "reserve_usd", "at"}


def test_a_safe_unbilled_resend_releases_its_dollars_but_counts_its_attempt(opened) -> None:
    reopen, *_ = opened
    guard = reopen()
    guard.settle_unbilled(_admit(guard, 1), "not_sent")
    guard.settle_unbilled(_admit(guard, 2), "rejected")
    guard.settle_charged(_admit(guard, 3), Decimal("0.0021"))
    state = guard.state
    assert (state.attempts, state.charged_usd, state.outstanding_usd, state.halted) == (3, Decimal("0.0021"), Decimal("0"), None)


def test_a_completed_reply_keeps_its_charge_whatever_happens_to_it_later(opened) -> None:
    reopen, _, path, _ = opened
    guard = reopen()
    guard.settle_charged(_admit(guard, 1), Decimal("0.0042"))
    settle = _records(path)[-1]
    assert (settle["kind"], settle["result"], settle["cost_usd"]) == ("settle", "charged", "0.0042")
    assert reopen().state.charged_usd == Decimal("0.0042")


@pytest.mark.parametrize("how", ["unknown-cost", "uncertain", "unbilled-claim-for-an-unproven-outcome"])
def test_an_unknown_charge_stops_every_later_dispatch(opened, how: str) -> None:
    reopen, *_ = opened
    guard = reopen()
    admission = _admit(guard, 1)
    if how == "unknown-cost":
        guard.settle_charged(admission, None)
    elif how == "uncertain":
        guard.settle_unknown(admission, "uncertain")
    else:
        guard.settle_unbilled(admission, "uncertain")
    assert guard.state.halted is not None
    _refused(guard, "STAGE_C_HALTED")
    _refused(reopen(), "STAGE_C_HALTED")  # the stop survives a restart


@pytest.mark.parametrize("settlement", ["unknown", "overrun"])
def test_a_settlement_that_stops_dispatch_still_stops_it_if_its_halt_record_was_lost(opened, settlement: str) -> None:
    """The settlement itself stops dispatch on replay; the halt record that follows it is a second record."""
    reopen, _, path, _ = opened
    guard = reopen()
    admission = _admit(guard, 1, Decimal("0.01"))
    guard.settle_unknown(admission, "uncertain") if settlement == "unknown" else guard.settle_charged(admission, Decimal("0.02"))
    guard.close()
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    assert json.loads(lines[-1])["kind"] == "halt"
    path.write_text("".join(lines[:-1]), encoding="utf-8", newline="")  # the halt record never reached the disk
    restarted = reopen()
    assert restarted.state.halted is not None
    _refused(restarted, "STAGE_C_HALTED", Decimal("0.001"))


def test_a_charge_above_its_reserve_is_kept_as_an_overrun_and_stops_dispatch(opened) -> None:
    reopen, *_ = opened
    guard = reopen()
    guard.settle_charged(_admit(guard, 1, Decimal("0.01")), Decimal("0.0100001"))
    state = guard.state
    assert state.charged_usd == Decimal("0.0100001") and state.overrun and state.halted is not None
    _refused(guard, "STAGE_C_HALTED", Decimal("0.001"))
    assert reopen().state.overrun


def test_a_repeated_identical_settlement_is_harmless_and_a_divergent_one_stops(opened) -> None:
    reopen, *_ = opened
    guard = reopen()
    admission = _admit(guard, 1)
    guard.settle_charged(admission, Decimal("0.01"))
    guard.settle_charged(admission, Decimal("0.01"))
    assert guard.state.charged_usd == Decimal("0.01") and guard.state.halted is None
    guard.settle_charged(admission, Decimal("0.02"))
    assert guard.state.charged_usd == Decimal("0.01") and guard.state.halted is not None


# --- Durability, restarts and damage ---------------------------------------------------------------------------


def test_a_reservation_that_cannot_be_made_durable_is_not_dispatched(opened) -> None:
    reopen, _, path, _ = opened

    def failing_fsync(_fd: int) -> None:
        raise OSError("disk full")

    reopen()  # the window is already recorded
    guard = reopen(fsync=failing_fsync)
    _refused(guard, "STAGE_C_LEDGER_WRITE_FAILED")
    assert guard.state.halted is not None and guard.state.outstanding_usd == Decimal("0")


def test_a_settlement_that_cannot_be_made_durable_stops_dispatch_and_is_never_free(opened) -> None:
    reopen, *_ = opened
    calls = []

    def flaky_fsync(fd: int) -> None:
        calls.append(fd)
        if len(calls) >= 2:  # the reservation is durable; the settlement's durability is unknown
            raise OSError("disk full")

    reopen()  # the window is already recorded
    guard = reopen(fsync=flaky_fsync)
    guard.settle_charged(_admit(guard, 1), Decimal("0.01"))
    assert guard.state.halted is not None
    _refused(guard, "STAGE_C_HALTED")
    # After a restart the attempt is either settled with its charge or still in doubt: never free.
    state = reopen().state
    assert state.attempts == 1
    assert (state.halted is None and state.charged_usd == Decimal("0.01")) or (state.halted is not None and "in doubt" in state.halted)


def test_a_clean_restart_reopens_the_same_totals_and_deadline(opened) -> None:
    reopen, clock, *_ = opened
    guard = reopen()
    guard.settle_charged(_admit(guard, 1), Decimal("0.03"))
    guard.settle_unbilled(_admit(guard, 2), "not_sent")
    clock.now = T0 + timedelta(minutes=20)
    state = reopen().state
    assert (state.attempts, state.charged_usd, state.outstanding_usd, state.halted, state.deadline) == (
        2, Decimal("0.03"), Decimal("0"), None, T0 + timedelta(hours=1)
    )  # fmt: skip


@pytest.mark.parametrize("when", ["after-reservation", "after-the-reply-before-settlement"])
def test_a_crash_leaves_the_attempt_in_doubt_never_free(opened, when: str) -> None:
    """Both crash points leave the same durable state: a reservation with no settlement. Its cost is
    never inferred as zero and the attempt is never retried."""
    reopen, *_ = opened
    guard = reopen()
    _admit(guard, 1)
    restarted = reopen()  # the process died holding the reservation
    state = restarted.state
    assert state.halted is not None and "in doubt" in state.halted
    assert (state.attempts, state.charged_usd) == (1, Decimal("0"))
    _refused(restarted, "STAGE_C_HALTED")


def test_a_truncated_or_malformed_record_stops_dispatch(opened) -> None:
    reopen, _, path, _ = opened
    guard = reopen()
    guard.settle_charged(_admit(guard, 1), Decimal("0.01"))
    guard.close()
    with path.open("ab") as handle:
        handle.write(b'{"kind": "reserve", "n": 2, "attem')  # a torn write
    state = reopen().state
    assert state.halted is not None and "malformed" in state.halted and state.charged_usd == Decimal("0.01")


def test_a_corrupt_initial_record_refuses_to_open(opened) -> None:
    reopen, clock, path, envelope = opened
    path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(StageCLedgerError) as caught:
        StageCGuard.open(path, envelope, clock=clock)
    assert caught.value.code == "STAGE_C_LEDGER_CORRUPT"


def test_the_ledger_records_no_prompt_credential_or_provider_text(opened) -> None:
    reopen, _, path, _ = opened
    guard = reopen()
    guard.settle_charged(_admit(guard, 1), Decimal("0.01"))
    guard.settle_unknown(_admit(guard, 2), "uncertain")
    allowed = {"kind", "n", "attempt_id", "request_id", "reserve_usd", "result", "outcome", "cost_usd", "reason", "at", "start", "deadline",
               "envelope", "release_id", "limit_usd", "max_attempts", "window_seconds", "overrun"}  # fmt: skip
    assert all(set(record) <= allowed for record in _records(path))
