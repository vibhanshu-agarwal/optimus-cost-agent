"""P11-FU-33: the H5 schedule records detection-time context, so a failure names its cause.

The schedule used to record only thread names, and hard-coded ``unexpected_persistent_tasks``
to ``()``. These tests pin what a detection now carries: the thread's daemon flag, target and
current stack, and real pending-task state -- in single-line, content-free text the frozen
audit schemas accept.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import weakref
from collections import Counter
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

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


def test_a_thread_that_exits_during_the_task_scan_keeps_its_target_and_stack(monkeypatch):
    """Codex re-review RR2: a detected thread is captured (target, identity, frames) together with its
    detection, before the task scan. Here it exits exactly at the task-scan boundary; its row must still
    carry its target and the frame it was in, not "<exited before it could be described>"."""
    from types import SimpleNamespace

    release = threading.Event()
    started = threading.Event()
    threads: list[threading.Thread] = []

    def _short_lived_teardown() -> None:
        started.set()
        release.wait(10)

    calls = {"count": 0}

    def _probe(record, cause, *, source):  # noqa: ARG001 - signature of the real probe
        calls["count"] += 1
        if calls["count"] == 2:
            thread = threading.Thread(target=_short_lived_teardown, name="fu33-short-lived-teardown", daemon=True)
            thread.start()
            threads.append(thread)
            assert started.wait(10)
        return 1, f"{cause}:prepared"

    real_scan = shutdown._leftover_tasks

    def _scan_during_which_the_thread_exits(baseline):
        if threads and threads[0].is_alive():
            release.set()
            threads[0].join(5)
            assert not threads[0].is_alive()
        return real_scan(baseline)

    monkeypatch.setattr(shutdown, "_probe_resource", _probe)
    monkeypatch.setattr(shutdown, "_leftover_tasks", _scan_during_which_the_thread_exits)
    observations: list[shutdown.ShutdownScheduleObservation] = []
    shutdown._run_schedule(
        observations,
        [SimpleNamespace(close_path_id="h5-0000000000000001")],
        3,
        None,
        ("MainThread",),
        Counter(thread.name for thread in threading.enumerate()),
    )

    entries = observations[1].unexpected_persistent_threads
    assert len(entries) == 1, entries
    entry = entries[0]
    assert entry.startswith("fu33-short-lived-teardown | daemon=True | target="), entry
    assert "_short_lived_teardown" in entry.split(" | ")[2], entry
    assert "in _short_lived_teardown" in entry, entry  # the frame it was in at detection
    assert "exited before it could be described" not in entry, entry
    assert "still_alive_after_join=no" in entry, entry
    assert _CONTENT_FREE.match(entry), entry


# #287: error attribution must survive without changing H5's ERROR verdict.
def _diagnostic_schedule(monkeypatch, error=None, *, probe=None):
    from types import SimpleNamespace

    def _raise_probe(record, cause, *, source):
        raise error

    monkeypatch.setattr(shutdown, "_probe_resource", probe or _raise_probe)
    rows = []
    shutdown._run_schedule(
        rows, [SimpleNamespace(close_path_id="h5-0000000000000001")], 1, None,
        ("MainThread",), Counter(thread.name for thread in threading.enumerate()),
    )
    assert len(rows) == len(shutdown._TERMINAL_CAUSES)
    return rows


def _error_fields(row):
    parts = row.cause_effect.split(" | ")
    assert len(parts) == 7, row.cause_effect
    assert [p.split("=", 1)[0] for p in parts[1:]] == ["errno", "winerror", "origin", "probe", "chain", "group"]
    assert row.close_outcome == "ERROR"
    assert row.complete is True and row.close_invocation_count == 3 and row.underlying_close_count == 0
    # This is the unchanged acceptance predicate, not an interpretation of synthetic counts.
    assert not ("probe_error" not in row.cause_effect)
    return dict(p.split("=", 1) for p in parts[1:])


def test_schedule_probe_errors_retain_origin_and_error_numbers(monkeypatch):
    def _setup_failed(record, cause, *, source):
        error = OSError(24, "PRIVATE_MESSAGE", "PRIVATE_FILENAME")
        error.winerror = 10055
        raise error

    def _close_failed(record, cause, *, source):
        raise RuntimeError("PRIVATE_MESSAGE")

    setup = _error_fields(_diagnostic_schedule(monkeypatch, probe=_setup_failed)[0])
    close = _error_fields(_diagnostic_schedule(monkeypatch, probe=_close_failed)[0])
    assert setup["errno"] == "24" and setup["winerror"] == "10055"
    assert close["errno"] == close["winerror"] == "unknown"
    assert setup["origin"].endswith(" in _setup_failed")
    assert close["origin"].endswith(" in _close_failed")
    assert setup["origin"] != close["origin"]
    assert "tools/plan1126_runtime_audit/shutdown.py:" in setup["probe"]
    assert setup["probe"].endswith(" in _run_schedule")
    assert "PRIVATE" not in str(setup)


class _Unprintable:
    def __str__(self):
        raise AssertionError("REJECTED_VALUE_STRINGIFIED")

    __repr__ = __str__


class _IntegerSubclass(int):
    def __str__(self):
        raise AssertionError("REJECTED_VALUE_STRINGIFIED")


@pytest.mark.parametrize("value,expected", [
    (None, "unknown"), ("PRIVATE_ATTRIBUTE", "unknown"), (_Unprintable(), "unknown"),
    (True, "unknown"), (_IntegerSubclass(3), "unknown"), (2**63, "unknown"),
    (-(2**63)-1, "unknown"), (-(2**63), str(-(2**63))), (2**63-1, str(2**63-1)), (0, "0"),
], ids=["missing", "string", "object", "bool", "int-subclass", "too-big", "too-small", "minimum", "maximum", "zero"])
def test_schedule_error_numbers_are_exact_bounded_ints(monkeypatch, value, expected):
    error = RuntimeError("PRIVATE_MESSAGE")
    error.errno = value
    error.winerror = value
    fields = _error_fields(_diagnostic_schedule(monkeypatch, error)[0])
    assert fields["errno"] == fields["winerror"] == expected
    assert fields["chain"] == fields["group"] == "none"


@pytest.mark.parametrize("chain", ["none", "cause", "context", "both"])
def test_schedule_retains_only_direct_chain_presence(monkeypatch, chain):
    error = RuntimeError("PRIVATE_MESSAGE")
    if chain in {"cause", "both"}:
        error.__cause__ = ValueError("PRIVATE_CHAIN")
    if chain in {"context", "both"}:
        error.__context__ = ValueError("PRIVATE_CHAIN")
    error.__suppress_context__ = True
    row = _diagnostic_schedule(monkeypatch, error)[0]
    assert _error_fields(row)["chain"] == chain
    assert "PRIVATE" not in row.cause_effect


class _MetadataFailure(RuntimeError):
    broken = ""
    failure = RuntimeError

    def __getattribute__(self, name):
        if name == object.__getattribute__(self, "broken"):
            raise object.__getattribute__(self, "failure")("PRIVATE_METADATA_FAILURE")
        return super().__getattribute__(name)


@pytest.mark.parametrize("broken,unknown_fields", [
    ("errno", ["errno"]), ("winerror", ["winerror"]),
    ("__traceback__", ["origin", "probe"]), ("__cause__", ["chain"]), ("__context__", ["chain"]),
])
def test_schedule_contains_ordinary_metadata_failures(monkeypatch, broken, unknown_fields):
    error = _MetadataFailure("PRIVATE_MESSAGE")
    error.broken = broken
    error.errno = 7
    row = _diagnostic_schedule(monkeypatch, error)[0]
    fields = _error_fields(row)
    assert row.cause_effect.startswith(f"{row.terminal_cause}:probe_error:_MetadataFailure | ")
    assert all(fields[key] == "unknown" for key in unknown_fields)
    if broken != "errno":
        assert fields["errno"] == "7"
    assert "PRIVATE" not in row.cause_effect


def test_schedule_contains_location_formatter_failure(monkeypatch):
    def _broken_locations(*args, **kwargs):
        raise RuntimeError("PRIVATE_FORMATTER_FAILURE")

    monkeypatch.setattr(shutdown, "_locations", _broken_locations)
    error = OSError(5, "PRIVATE_MESSAGE")
    row = _diagnostic_schedule(monkeypatch, error)[0]
    fields = _error_fields(row)
    assert fields["origin"] == fields["probe"] == "unknown"
    assert fields["errno"] == "5"
    assert "PRIVATE" not in row.cause_effect


@pytest.mark.parametrize("failure", [KeyboardInterrupt, asyncio.CancelledError, shutdown.ExecutingSourceMismatch])
@pytest.mark.parametrize("where", ["probe", "metadata", "locations"])
def test_schedule_never_contains_control_flow_or_source_refusal(monkeypatch, failure, where):
    error = _MetadataFailure("PRIVATE_MESSAGE")
    if where == "probe":
        error = failure("PRIVATE_MESSAGE")
    elif where == "metadata":
        error.broken, error.failure = "errno", failure
    else:
        def _refuse(*args, **kwargs):
            raise failure("PRIVATE_MESSAGE")
        monkeypatch.setattr(shutdown, "_locations", _refuse)
    with pytest.raises(failure):
        _diagnostic_schedule(monkeypatch, error)


class _GroupMetadataFailure(ExceptionGroup):
    value = None

    def __getattribute__(self, name):
        if name == "exceptions":
            value = object.__getattribute__(self, "value")
            if value == "raise":
                raise RuntimeError("PRIVATE_GROUP")
            return value
        return super().__getattribute__(name)


@pytest.mark.parametrize("value,expected", [((), "unknown"), ([], "unknown"), ("raise", "unknown")])
def test_schedule_rejects_invalid_root_group_metadata(monkeypatch, value, expected):
    error = _GroupMetadataFailure("PRIVATE_GROUP", [ValueError("PRIVATE_MEMBER")])
    error.value = value
    assert _error_fields(_diagnostic_schedule(monkeypatch, error)[0])["group"] == expected


def test_schedule_records_only_root_group_count(monkeypatch):
    row = _diagnostic_schedule(monkeypatch, ExceptionGroup("PRIVATE_GROUP", [
        ValueError("PRIVATE_MEMBER"), ExceptionGroup("PRIVATE_NESTED", [RuntimeError("PRIVATE_MEMBER")]),
    ]))[0]
    assert _error_fields(row)["group"] == "2"
    assert "PRIVATE" not in row.cause_effect
    with pytest.raises(BaseExceptionGroup):
        _diagnostic_schedule(monkeypatch, BaseExceptionGroup("PRIVATE_GROUP", [KeyboardInterrupt()]))


@pytest.mark.parametrize("filename", [
    "C:/HOST_PATH_MARKER/probe.py", "//HOST_PATH_MARKER/share/probe.py",
    "/tmp/HOST_PATH_MARKER/probe.py", "/home/HOST_PATH_MARKER/probe.py",
    "<string>", "<frozen fixture>", "C:/HOST_PATH_MARKER/é.py", "C:/HOST_PATH_MARKER/a|b\x85c\u2028d.py",
])
@pytest.mark.parametrize("kind", ["module", "lambda", "genexpr"])
def test_schedule_uses_content_free_location_metadata(monkeypatch, filename, kind):
    original = Path.resolve
    if kind == "module":
        code = "raise error"
    elif kind == "lambda":
        code = "(lambda: 1 / 0)()"
    else:
        code = "next(1 / 0 for _ in [None])"

    def _resolve(path, *args, **kwargs):
        if str(path) == str(Path(filename)):
            return Path(filename)
        return original(path, *args, **kwargs)

    def _probe(record, cause, *, source):
        exec(compile(code, filename, "exec"), {"error": RuntimeError("PRIVATE_MESSAGE")})

    with monkeypatch.context() as context:
        context.setattr(Path, "resolve", _resolve)
        row = _diagnostic_schedule(context, probe=_probe)[0]
    assert Path.resolve is original
    with pytest.raises(RuntimeError, match="FIXTURE_BODY"):
        with monkeypatch.context() as context:
            context.setattr(Path, "resolve", _resolve)
            raise RuntimeError("FIXTURE_BODY")
    assert Path.resolve is original
    fields = _error_fields(row)
    assert "HOST_PATH_MARKER" not in fields["origin"]
    assert fields["origin"].endswith(" in <module>" if kind == "module" else f" in <{kind}>")
    assert fields["probe"].endswith(" in _run_schedule")
    assert not re.search(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]", row.cause_effect)
    assert row.cause_effect.count(" | ") == 6


def test_extended_error_row_round_trips_through_both_unchanged_schemas(monkeypatch):
    row = _diagnostic_schedule(monkeypatch, OSError(5, "PRIVATE_MESSAGE"))[0]
    _error_fields(row)
    assert shutdown.ShutdownScheduleObservation.from_dict(row.to_dict()).to_dict() == row.to_dict()
    root = Path(__file__).resolve().parents[4]
    for name in ("audit-artifact.schema.json", "audit-artifact-v2.schema.json"):
        schema = json.loads((root / "tests/fixtures/plan1126_runtime_audit" / name).read_text())
        Draft202012Validator({"$ref": "#/$defs/shutdownObservation", "$defs": schema["$defs"]}).validate(row.to_dict())


@pytest.mark.parametrize("count,outcome", [(0, "IDEMPOTENT_NOOP"), (1, "CLOSED_ONCE"), (2, "DOUBLE_CLOSE_OBSERVED")])
def test_successful_schedule_rows_keep_existing_fields(monkeypatch, count, outcome):
    def _probe(record, cause, *, source):
        return count, f"{cause}:prepared"

    for row in _diagnostic_schedule(monkeypatch, probe=_probe):
        assert row.to_dict() == {
            "close_path_id": "h5-0000000000000001", "terminal_cause": row.terminal_cause,
            "complete": True, "close_invocation_count": 3, "control_thread_names": ["MainThread"],
            "unexpected_persistent_threads": [], "unexpected_persistent_tasks": [],
            "repeat_latency_class": row.repeat_latency_class, "underlying_close_count": count,
            "close_outcome": outcome, "cause_effect": f"{row.terminal_cause}:prepared",
        }


def test_schedule_class_name_read_failure_has_explicit_ambiguous_exception_bucket(monkeypatch):
    class _UnreadableName(type):
        def __getattribute__(cls, name):
            if name == "__name__":
                raise RuntimeError("PRIVATE_CLASS_METADATA")
            return super().__getattribute__(name)

    class _UnavailableType(Exception, metaclass=_UnreadableName):
        pass

    row = _diagnostic_schedule(monkeypatch, _UnavailableType("PRIVATE_MESSAGE"))[0]
    _error_fields(row)
    assert row.cause_effect.startswith(f"{row.terminal_cause}:probe_error:Exception | ")
    assert "PRIVATE" not in row.cause_effect


def test_root_group_member_attribute_is_read_once_without_traversal(monkeypatch):
    class _CountingGroup(ExceptionGroup):
        reads = 0

        def __getattribute__(self, name):
            if name == "exceptions":
                self.reads += 1
            return super().__getattribute__(name)

    error = _CountingGroup("PRIVATE_GROUP", [ValueError("PRIVATE_MEMBER")])
    rows = _diagnostic_schedule(monkeypatch, error)
    assert all(_error_fields(row)["group"] == "1" for row in rows)
    assert error.reads == len(rows)


def test_unraised_exception_and_empty_filename_have_unknown_origin(monkeypatch):
    value = shutdown._probe_error_effect("cancel", ValueError("PRIVATE_MESSAGE"))
    assert "origin=unknown | probe=unknown | chain=none | group=none" in value

    def _probe(record, cause, *, source):
        exec(compile("raise RuntimeError('PRIVATE_MESSAGE')", "", "exec"))

    row = _diagnostic_schedule(monkeypatch, probe=_probe)[0]
    fields = _error_fields(row)
    assert fields["origin"] == "unknown" and fields["probe"].endswith(" in _run_schedule")


def test_schedule_does_not_claim_earlier_probe_after_deeper_path_resolution_failure(monkeypatch):
    package = shutdown._REPOSITORY_ROOT / "tools/plan1126_runtime_audit"
    inner, outer = package / "diagnostic_fixture_inner.py", package / "diagnostic_fixture_outer.py"
    namespace = {}
    exec(compile("def inner(error):\n    raise error\n", str(inner), "exec"), namespace)
    exec(compile("def outer(error):\n    inner(error)\n", str(outer), "exec"), namespace)
    original = Path.resolve
    failing = False

    def _resolve(path, *args, **kwargs):
        if path == inner:
            if failing:
                raise OSError("PRIVATE_PATH_RESOLUTION_FAILURE")
            return inner
        if path == outer:
            return outer
        return original(path, *args, **kwargs)

    def _probe(record, cause, *, source):
        namespace["outer"](OSError(5, "PRIVATE_MESSAGE"))

    with monkeypatch.context() as context:
        context.setattr(Path, "resolve", _resolve)
        normal = _error_fields(_diagnostic_schedule(context, probe=_probe)[0])
        assert normal["probe"].endswith("diagnostic_fixture_inner.py:2 in inner")
        failing = True
        row = _diagnostic_schedule(context, probe=_probe)[0]
    assert Path.resolve is original
    fields = _error_fields(row)
    assert fields["errno"] == "5" and fields["origin"].endswith("diagnostic_fixture_inner.py:2 in inner")
    assert fields["probe"] == "unknown"  # An earlier known frame cannot establish the deepest frame.
    assert "PRIVATE" not in row.cause_effect


def test_review_control_normalization_cannot_create_schema_rejected_label(monkeypatch):
    filename = "C:/HOST_PATH_MARKER/secret\x81=value.py"
    original = Path.resolve

    def _resolve(path, *args, **kwargs):
        return Path(filename) if path == Path(filename) else original(path, *args, **kwargs)

    def _probe(record, cause, *, source):
        exec(compile("raise OSError(5, 'PRIVATE_MESSAGE')", filename, "exec"))

    with monkeypatch.context() as context:
        context.setattr(Path, "resolve", _resolve)
        row = _diagnostic_schedule(context, probe=_probe)[0]
    assert Path.resolve is original
    assert "secret =" not in row.cause_effect
    assert "<label> =" in _error_fields(row)["origin"]
    root = Path(__file__).resolve().parents[4]
    for name in ("audit-artifact.schema.json", "audit-artifact-v2.schema.json"):
        schema = json.loads((root / "tests/fixtures/plan1126_runtime_audit" / name).read_text())
        Draft202012Validator({"$ref": "#/$defs/shutdownObservation", "$defs": schema["$defs"]}).validate(row.to_dict())


@pytest.mark.parametrize("filename", ["", "<string>", "<frozen fixture>"])
def test_review_pseudo_and_empty_filename_do_not_become_package_frames(monkeypatch, filename):
    def _probe(record, cause, *, source):
        exec(compile("raise RuntimeError('PRIVATE_MESSAGE')", filename, "exec"))

    original_cwd = Path.cwd()
    with monkeypatch.context() as context:
        context.chdir(shutdown._REPOSITORY_ROOT / "tools/plan1126_runtime_audit")
        fields = _error_fields(_diagnostic_schedule(context, probe=_probe)[0])
    assert Path.cwd() == original_cwd
    assert fields["origin"] == (f"{filename}:1 in <module>" if filename else "unknown")
    assert "tools/plan1126_runtime_audit/shutdown.py:" in fields["probe"]
    assert fields["probe"].endswith(" in _run_schedule")


def test_review_empty_basename_is_unknown_instead_of_invalid_location(monkeypatch):
    def _probe(record, cause, *, source):
        exec(compile("raise RuntimeError('PRIVATE_MESSAGE')", "C:/", "exec"))

    fields = _error_fields(_diagnostic_schedule(monkeypatch, probe=_probe)[0])
    assert fields["origin"] == "unknown"
    assert fields["probe"].endswith(" in _run_schedule")


def test_review_final_fallback_keeps_error_and_class_without_metadata(monkeypatch):
    def _decimal_failure(value):
        monkeypatch.delattr(shutdown, "str")  # Restore before the next cause's class-name check.
        assert value == 5
        raise RuntimeError("PRIVATE_DECIMAL_FORMATTING_FAILURE")

    class _FormattingError(OSError):
        def __getattribute__(self, name):
            if name == "errno":
                monkeypatch.setattr(shutdown, "str", _decimal_failure, raising=False)
            return super().__getattribute__(name)

    # Fail serialization of a validated numeric field, without changing process-wide builtins.
    for row in _diagnostic_schedule(monkeypatch, _FormattingError(5, "PRIVATE_MESSAGE")):
        assert row.cause_effect.startswith(f"{row.terminal_cause}:probe_error:_FormattingError | ")
        assert set(_error_fields(row).values()) == {"unknown"}
        assert "PRIVATE" not in row.cause_effect
    assert "str" not in vars(shutdown)


def test_review_probe_local_values_are_not_diagnostic_content(monkeypatch):
    from dataclasses import replace

    def _probe(record, cause, *, source):
        _private_local = "LOCAL_VALUE_CANARY"
        raise RuntimeError("PRIVATE_MESSAGE")

    def _assert_private_values_absent(row):
        assert "LOCAL_VALUE_CANARY" not in row.cause_effect
        assert "PRIVATE_MESSAGE" not in row.cause_effect

    rows = _diagnostic_schedule(monkeypatch, probe=_probe)
    for row in rows:
        _assert_private_values_absent(row)
        assert _error_fields(row)["origin"].endswith(" in _probe")
    # Characterization with a positive oracle control; this is not evidence of a former leak.
    for leaked_value in ("LOCAL_VALUE_CANARY", "PRIVATE_MESSAGE"):
        with pytest.raises(AssertionError):
            _assert_private_values_absent(replace(rows[0], cause_effect=rows[0].cause_effect + leaked_value))


@pytest.mark.parametrize("filename", ["<HOST_PATH_MARKER/dir/probe.py>", r"<HOST_PATH_MARKER\dir\probe.py>"])
def test_review_path_bearing_pseudo_filename_is_unknown(monkeypatch, filename):
    def _probe(record, cause, *, source):
        exec(compile("raise RuntimeError('PRIVATE_MESSAGE')", filename, "exec"))

    row = _diagnostic_schedule(monkeypatch, probe=_probe)[0]
    fields = _error_fields(row)
    assert fields["origin"] == "unknown"
    assert "HOST_PATH_MARKER" not in row.cause_effect
    assert fields["probe"].endswith(" in _run_schedule")


@pytest.mark.parametrize("filename", ["relative.py", "nested/relative.py", r"nested\relative.py"])
def test_review_relative_filename_metadata_does_not_depend_on_cwd(monkeypatch, filename):
    def _probe(record, cause, *, source):
        exec(compile("raise RuntimeError('PRIVATE_MESSAGE')", filename, "exec"))

    results = []
    for cwd in (shutdown._REPOSITORY_ROOT, shutdown._REPOSITORY_ROOT / "tools/plan1126_runtime_audit"):
        with monkeypatch.context() as context:
            context.chdir(cwd)
            results.append(_error_fields(_diagnostic_schedule(context, probe=_probe)[0]))
    assert results[0] == results[1]
    assert results[0]["origin"] == results[0]["probe"] == "unknown"


def test_review_exception_base_group_hybrid_retains_root_count(monkeypatch):
    class _HybridGroup(BaseExceptionGroup, Exception):
        pass

    error = _HybridGroup("PRIVATE_GROUP", [ValueError("PRIVATE_MEMBER")])
    assert isinstance(error, Exception) and not isinstance(error, ExceptionGroup)
    for row in _diagnostic_schedule(monkeypatch, error):
        assert _error_fields(row)["group"] == "1"
        assert "PRIVATE" not in row.cause_effect
