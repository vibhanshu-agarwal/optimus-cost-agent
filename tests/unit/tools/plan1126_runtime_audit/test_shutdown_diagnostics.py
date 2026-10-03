"""P11-FU-33: the H5 schedule records detection-time context, so a failure names its cause.

The schedule used to record only thread names, and hard-coded ``unexpected_persistent_tasks``
to ``()``. These tests pin what a detection now carries: the thread's daemon flag, target and
current stack, and real pending-task state -- in single-line, content-free text the frozen
audit schemas accept.
"""

from __future__ import annotations

import asyncio
import re
import threading
import weakref
from collections import Counter

from tools.plan1126_runtime_audit import shutdown

# The frozen schema's contentFreeText rule (tests/fixtures/plan1126_runtime_audit/audit-artifact.schema.json).
_CONTENT_FREE = re.compile(
    r"^(?!.*(?:api[_-]?key|password|passwd|access[_-]?token|refresh[_-]?token|authorization|cookie|secret"
    r"|response body|prompt body|request body|payload body)\s*[:=])[^\u0000-\u001f\u007f]+$"
)


def test_a_persistent_thread_entry_names_the_thread_its_target_and_where_it_is():
    release = threading.Event()

    def _parked_in_close() -> None:
        release.wait(10)

    thread = threading.Thread(target=_parked_in_close, name="fu33-diagnostic-probe", daemon=True)
    thread.start()
    try:
        entries = shutdown._describe_persistent_threads(Counter({"fu33-diagnostic-probe": 1}))
    finally:
        release.set()
        thread.join(5)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.startswith("fu33-diagnostic-probe | daemon=True | target=")
    assert "_parked_in_close" in entry.split(" | ")[2]
    assert "in _parked_in_close" in entry, entry
    assert "still_alive_after_join=yes" in entry, entry
    assert _CONTENT_FREE.match(entry), entry


def test_a_thread_that_exits_during_the_diagnostic_join_is_still_reported():
    """The verdict is taken at detection: the join only annotates, it never clears the entry."""
    release = threading.Event()
    thread = threading.Thread(target=release.wait, args=(10,), name="fu33-exiting-probe", daemon=True)
    thread.start()
    threading.Timer(0.05, release.set).start()
    entries = shutdown._describe_persistent_threads(Counter({"fu33-exiting-probe": 1}))
    thread.join(5)

    assert len(entries) == 1
    assert entries[0].startswith("fu33-exiting-probe | ")
    assert "still_alive_after_join=no" in entries[0], entries[0]


def test_a_task_left_pending_on_a_closed_loop_is_reported_with_its_coroutine_and_frame():
    baseline = shutdown._pending_task_baseline()
    loop = asyncio.new_event_loop()
    never: asyncio.Future[None] = loop.create_future()

    async def _awaiting_forever() -> None:
        await never

    task = loop.create_task(_awaiting_forever(), name="fu33-leaked-task")
    loop.run_until_complete(asyncio.sleep(0))
    loop.close()
    try:
        entries = shutdown._leftover_task_descriptions(baseline)
    finally:
        task._log_destroy_pending = False  # noqa: SLF001 - the leak is this test's fixture

    assert len(entries) == 1, entries
    entry = entries[0]
    assert entry.startswith("fu33-leaked-task | coro=")
    assert "_awaiting_forever" in entry.split(" | ")[1], entry  # the coroutine, not just a frame
    assert "in _awaiting_forever" in entry, entry
    assert _CONTENT_FREE.match(entry), entry


def test_no_pending_task_outside_the_baseline_reports_nothing():
    baseline = shutdown._pending_task_baseline()
    assert shutdown._leftover_task_descriptions(baseline) == ()
    assert isinstance(baseline, weakref.WeakSet)


def test_a_leaked_task_is_attributed_to_the_exact_repeat_that_left_it(monkeypatch):
    """Codex review (P11-FU-33 batch): every row measures real task state. A group-level scan left
    99 of 100 rows claiming "no tasks" unmeasured and could not say which repeat leaked."""
    from types import SimpleNamespace

    leaked_loops: list[asyncio.AbstractEventLoop] = []
    leaked_tasks: list[asyncio.Task[None]] = []
    calls = {"count": 0}

    def _probe(record, cause, *, source):  # noqa: ARG001 - signature of the real probe
        calls["count"] += 1
        if calls["count"] == 2:
            loop = asyncio.new_event_loop()
            never: asyncio.Future[None] = loop.create_future()

            async def _left_by_repeat_two() -> None:
                await never

            task = loop.create_task(_left_by_repeat_two(), name="fu33-repeat-two")
            loop.run_until_complete(asyncio.sleep(0))
            loop.close()
            task._log_destroy_pending = False  # noqa: SLF001 - the leak is this test's fixture
            leaked_loops.append(loop)
            leaked_tasks.append(task)
        return 1, f"{cause}:prepared"

    monkeypatch.setattr(shutdown, "_probe_resource", _probe)
    observations: list[shutdown.ShutdownScheduleObservation] = []
    shutdown._run_schedule(
        observations,
        [SimpleNamespace(close_path_id="h5-0000000000000001")],
        3,
        None,
        ("MainThread",),
        Counter(thread.name for thread in threading.enumerate()),
    )

    rows_with_tasks = [index for index, row in enumerate(observations) if row.unexpected_persistent_tasks]
    assert rows_with_tasks == [1], rows_with_tasks
    assert observations[1].unexpected_persistent_tasks[0].startswith("fu33-repeat-two | coro=")
    assert len(observations) == 3 * len(shutdown._TERMINAL_CAUSES)


def test_a_task_that_finishes_during_the_thread_diagnostic_join_stays_in_its_row(monkeypatch):
    """Codex review R3: task state is captured at detection, before any diagnostic join. Here the
    owner thread finishes its task exactly while the schedule waits on that thread; the row must
    still name the task (and the thread), not report "no tasks"."""
    from types import SimpleNamespace

    started = threading.Event()
    release = threading.Event()
    owners: list[threading.Thread] = []

    def _owner() -> None:
        loop = asyncio.new_event_loop()
        gate = loop.create_future()

        async def _finishing_during_the_join() -> None:
            await gate

        task = loop.create_task(_finishing_during_the_join(), name="fu33-join-window-task")
        loop.run_until_complete(asyncio.sleep(0))
        started.set()
        release.wait(10)
        gate.set_result(None)
        loop.run_until_complete(task)
        loop.close()

    calls = {"count": 0}

    def _probe(record, cause, *, source):  # noqa: ARG001 - signature of the real probe
        calls["count"] += 1
        if calls["count"] == 2:
            owner = threading.Thread(target=_owner, name="fu33-join-window-owner", daemon=True)
            owner.start()
            owners.append(owner)
            assert started.wait(10)
        return 1, f"{cause}:prepared"

    real_join = shutdown.alive_after_bounded_join

    def _join_that_lets_the_owner_finish(thread, seconds):
        release.set()
        return real_join(thread, max(seconds, 5.0))

    monkeypatch.setattr(shutdown, "_probe_resource", _probe)
    monkeypatch.setattr(shutdown, "alive_after_bounded_join", _join_that_lets_the_owner_finish)
    observations: list[shutdown.ShutdownScheduleObservation] = []
    shutdown._run_schedule(
        observations,
        [SimpleNamespace(close_path_id="h5-0000000000000001")],
        3,
        None,
        ("MainThread",),
        Counter(thread.name for thread in threading.enumerate()),
    )
    for owner in owners:
        owner.join(5)

    row = observations[1]
    assert [entry.split(" | ")[0] for entry in row.unexpected_persistent_threads] == ["fu33-join-window-owner"]
    assert "still_alive_after_join=no" in row.unexpected_persistent_threads[0]  # it finished during the join
    assert len(row.unexpected_persistent_tasks) == 1, row.unexpected_persistent_tasks
    assert row.unexpected_persistent_tasks[0].startswith("fu33-join-window-task | coro=")
