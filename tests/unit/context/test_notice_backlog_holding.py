"""#643: what the notice backlog holds when its file cannot be written, on a temp config folder, with the refusal injected where
it writes its file (`memory_recovery._durable_json`). The adapter-level sequences are in tests/unit/acp/test_memory_notice_recovery.py."""

from __future__ import annotations

import errno
import threading
from pathlib import Path
from typing import Any

import pytest

from optimus.context import memory_extraction as mx
from optimus.context import memory_recovery as mr
from optimus.usage.turn_settlement import TurnSettlement


def _refusing(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    state = {"full": True}
    real = mr._durable_json

    def write(path: Path, value: Any) -> None:
        if state["full"] and path.parent.name == "memory-notices":
            raise OSError(errno.ENOSPC, "No space left on device", str(path))
        real(path, value)

    monkeypatch.setattr(mr, "_durable_json", write)
    return state


def _record(number: int) -> dict[str, Any]:
    return {"event_id": f"e-{number}", "item": f"m-{number}", "version": 1, "action": "admit", "durable_state": "confirmed",
            "projection_state": "current"}


def _on_disk(tmp_path: Path) -> list[str]:
    return [record["event_id"] for record in mr.NoticeBacklog(tmp_path, "p-1").pending()]


def test_refused_writes_are_held_capped_and_logged_once_each_way(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                  caplog: pytest.LogCaptureFixture) -> None:
    disk = _refusing(monkeypatch)
    backlog = mr.NoticeBacklog(tmp_path, "p-1")
    limit = mr.NoticeBacklog.HELD_LIMIT
    for number in range(limit + 3):
        with pytest.raises(OSError):
            backlog.add([_record(number)])  # raised as before (an import stops on it), and held
    with pytest.raises(OSError):
        backlog.remove(["e-5"])
    held = [record["event_id"] for record in backlog.pending()]
    assert held == [f"e-{number}" for number in range(3, limit + 3) if number != 5]  # the oldest three dropped, one tombstoned
    assert _on_disk(tmp_path) == []
    disk["full"] = False
    backlog.flush()
    assert _on_disk(tmp_path) == held and backlog.pending() == mr.NoticeBacklog(tmp_path, "p-1").pending()
    assert caplog.messages == [
        "Memory notice backlog write failed (ENOSPC); holding 1 notice(s) and 0 removal(s) in this process",
        "Memory notice backlog written again; 3 held notice(s) or removal(s) were dropped at the cap meanwhile",
    ]


def test_a_tombstone_hides_a_record_already_on_disk_until_its_removal_is_written(tmp_path: Path,
                                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    disk = _refusing(monkeypatch)
    disk["full"] = False
    backlog = mr.NoticeBacklog(tmp_path, "p-1")
    backlog.add([_record(1), _record(2)])
    disk["full"] = True
    with pytest.raises(OSError):
        backlog.remove(["e-1"])
    assert [record["event_id"] for record in backlog.pending()] == ["e-2"] and _on_disk(tmp_path) == ["e-1", "e-2"]
    disk["full"] = False
    assert [record["event_id"] for record in backlog.pending()] == ["e-2"] and _on_disk(tmp_path) == ["e-2"]


def test_a_retry_never_overwrites_a_file_it_cannot_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    disk = _refusing(monkeypatch)
    disk["full"] = False
    other = mr.NoticeBacklog(tmp_path, "p-1")
    other.add([_record(1)])  # another process's record
    backlog = mr.NoticeBacklog(tmp_path, "p-1")
    disk["full"] = True
    with pytest.raises(OSError):
        backlog.add([_record(2)])
    disk["full"] = False
    real_read = Path.read_text

    def read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        if path == backlog.path:
            raise PermissionError(errno.EACCES, "sharing violation", str(path))
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    assert [record["event_id"] for record in backlog.pending()] == ["e-2"]  # the retry is refused; e-2 stays held
    monkeypatch.setattr(Path, "read_text", real_read)
    backlog.flush()
    assert _on_disk(tmp_path) == ["e-1", "e-2"]


def test_concurrent_adds_and_reads_of_a_failing_backlog_lose_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Extraction reports run on worker threads beside the command path's to_thread calls: every held record is kept."""
    disk = _refusing(monkeypatch)
    backlog = mr.NoticeBacklog(tmp_path, "p-1")
    errors: list[BaseException] = []

    def adder(start: int) -> None:
        for number in range(start, start + 40):
            try:
                backlog.add([_record(number)])
            except OSError:
                pass
            except BaseException as failure:  # noqa: BLE001 - anything else is a race
                errors.append(failure)
            if number == start + 20:
                disk["full"] = not disk["full"]  # writes start and stop working while the others run

    def reader() -> None:
        for _ in range(80):
            try:
                backlog.pending()
            except BaseException as failure:  # noqa: BLE001
                errors.append(failure)

    threads = [threading.Thread(target=adder, args=(start,)) for start in (0, 100, 200)] + [threading.Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    expected = {f"e-{number}" for start in (0, 100, 200) for number in range(start, start + 40)}
    assert errors == [] and {record["event_id"] for record in backlog.pending()} == expected
    disk["full"] = False
    backlog.flush()
    assert set(_on_disk(tmp_path)) == expected and len(_on_disk(tmp_path)) == len(expected)


def test_closing_the_extractor_writes_what_its_backlog_held(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    disk = _refusing(monkeypatch)
    extractor = mx.MemoryExtractor(store=None, settlement=TurnSettlement(), sanitize=lambda text: text,
                                   report=lambda _outcome: None, workers=0)
    extractor.notices = mr.NoticeBacklog(tmp_path, "p-1")
    with pytest.raises(OSError):
        extractor.notices.add([_record(1)])
    disk["full"] = False
    extractor.close()
    assert _on_disk(tmp_path) == ["e-1"]


def test_tombstones_are_capped_too_and_a_dropped_one_is_counted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                caplog: pytest.LogCaptureFixture) -> None:
    disk = _refusing(monkeypatch)
    disk["full"] = False
    backlog = mr.NoticeBacklog(tmp_path, "p-1")
    limit = mr.NoticeBacklog.HELD_LIMIT
    backlog.add([_record(number) for number in range(limit + 1)])
    disk["full"] = True
    with pytest.raises(OSError):
        backlog.remove([f"e-{number}" for number in range(limit + 1)])
    assert backlog.pending() == [_record(0)]  # its tombstone was the oldest, dropped at the cap
    disk["full"] = False
    backlog.add([_record(1000)])  # a real write
    assert _on_disk(tmp_path) == ["e-0", "e-1000"]  # the stated limit: a delivered card a restart could show again
    assert caplog.messages[-1] == ("Memory notice backlog written again; 1 held notice(s) or removal(s) were dropped at the cap "
                                   "meanwhile")


def test_a_malformed_event_id_never_hides_a_valid_notice(tmp_path: Path) -> None:
    """#643 review 1, finding 6: an id that is not a string is kept on disk but never matched, so `pending` still answers."""
    import json

    backlog = mr.NoticeBacklog(tmp_path, "p-1")
    backlog.add([_record(1)])
    data = json.loads(backlog.path.read_text(encoding="utf-8"))
    backlog.path.write_text(json.dumps([{"event_id": []}, *data]), encoding="utf-8")
    backlog.remove(["e-9"])
    backlog.add([_record(2)])
    assert [record["event_id"] for record in backlog.pending()] == [[], "e-1", "e-2"]


def test_a_lock_release_error_after_the_write_never_re_applies_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#643 review 1, finding 4: the file already holds the record when releasing the lock fails. Another process delivers and
    removes it; this process's next call must not write it back."""
    import contextlib

    backlog = mr.NoticeBacklog(tmp_path, "p-1")
    real_lock = mr._file_lock

    @contextlib.contextmanager
    def failing_release(path: Path, **kwargs: Any) -> Any:
        with real_lock(path, **kwargs):
            yield
        raise OSError(errno.EIO, "close failed")

    monkeypatch.setattr(mr, "_file_lock", failing_release)
    with pytest.raises(OSError):
        backlog.add([_record(1)])
    monkeypatch.setattr(mr, "_file_lock", real_lock)
    mr.NoticeBacklog(tmp_path, "p-1").remove(["e-1"])  # the other process
    assert backlog.pending() == [] and _on_disk(tmp_path) == []


def test_a_call_that_writes_nothing_is_not_reported_as_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                caplog: pytest.LogCaptureFixture) -> None:
    """#643 review 1, finding 7: a held add removed before any write leaves nothing to write; that proves nothing about the disk,
    so the outage is logged once, not once per command."""
    _refusing(monkeypatch)
    backlog = mr.NoticeBacklog(tmp_path, "p-1")
    for number in range(3):
        with pytest.raises(OSError):
            backlog.add([_record(number)])
        backlog.remove([f"e-{number}"])  # the card was delivered anyway; nothing on disk to remove
    assert caplog.messages == ["Memory notice backlog write failed (ENOSPC); holding 1 notice(s) and 0 removal(s) in this process"]
