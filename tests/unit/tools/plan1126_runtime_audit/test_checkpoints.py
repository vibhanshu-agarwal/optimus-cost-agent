"""Atomic checkpoint and conflict tests."""

from __future__ import annotations

import multiprocessing
from pathlib import Path

import pytest

from tools.plan1126_runtime_audit.checkpoints import CheckpointConflict, CheckpointStore


def _concurrent_append(path: str, start, results) -> None:
    start.wait()
    try:
        revision = CheckpointStore(path).append(
            f"writer-{multiprocessing.current_process().pid}",
            {"padding": "x" * 8_000_000},
            expected_revision=0,
        ).revision
        results.put(("ok", revision))
    except CheckpointConflict:
        results.put(("conflict", None))


def test_checkpoint_store_resumes_and_rejects_stale_revision(tmp_path: Path) -> None:
    path = tmp_path / "audit.checkpoint.json"
    store = CheckpointStore(path)
    assert store.read().revision == 0
    first = store.append("inventory", {"completed": True}, expected_revision=0)
    assert first.revision == 1
    resumed = CheckpointStore(path).read()
    assert resumed.entries == {"inventory": {"completed": True}}
    with pytest.raises(CheckpointConflict, match="expected revision 0; found 1"):
        store.append("cost", {"runs": 10}, expected_revision=0)
    assert CheckpointStore(path).read() == resumed


def test_checkpoint_write_failure_preserves_prior_file_and_removes_temp(tmp_path: Path) -> None:
    path = tmp_path / "audit.checkpoint.json"
    store = CheckpointStore(path)
    store.append("inventory", {"completed": True}, expected_revision=0)
    before = path.read_bytes()
    with pytest.raises(TypeError):
        store.append("bad", {"not_json": object()}, expected_revision=1)
    assert path.read_bytes() == before
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_checkpoint_store_allows_only_one_concurrent_expected_revision_writer(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    path = tmp_path / "race.checkpoint.json"
    processes = [context.Process(target=_concurrent_append, args=(str(path), start, results)) for _ in range(2)]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0
    outcomes = sorted(results.get(timeout=2)[0] for _ in processes)
    assert outcomes == ["conflict", "ok"]
    assert CheckpointStore(path).read().revision == 1
