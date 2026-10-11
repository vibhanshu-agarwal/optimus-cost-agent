"""Plan 11.30 Task 0: the shared positive-end predicate and operator-invoked registry maintenance.

Every maintenance proof runs against a synthetic registry under `tmp_path`; nothing here reads or
changes the host registry. The predicate proofs use the real kernel for the cases the kernel can
produce deterministically (this live process, a reused PID, an exited child whose handle is still
held) and inject the native answers that cannot be produced on demand (no such process, denied).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.testing import registry_maintenance as maintenance
from tools.testing import run_context, run_context_records, run_context_windows

_windows = pytest.mark.skipif(sys.platform != "win32", reason="native process identity is Windows-only")


# --- The shared predicate: positive end, live, or unknown; never a guess.


@_windows
def test_this_live_process_is_live() -> None:
    me = run_context_windows.current_identity()
    assert run_context.process_end_status(me.pid, me.creation_time) == (run_context.LIVE, "running")


@_windows
def test_a_reused_pid_proves_only_that_the_recorded_process_ended() -> None:
    me = run_context_windows.current_identity()
    assert me.creation_time is not None
    assert run_context.process_end_status(me.pid, me.creation_time - 1) == (run_context.ENDED, "replaced")


@_windows
def test_an_exited_process_whose_handle_is_still_held_has_terminated() -> None:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    try:
        identity = run_context_windows.process_identity(child.pid)
        assert child.wait(timeout=60) == 0
        # The Popen object still holds a handle, so the PID cannot have been reused yet.
        assert run_context.process_end_status(child.pid, identity.creation_time) == (run_context.ENDED, "terminated")
    finally:
        child.wait(timeout=60)


@_windows
@pytest.mark.parametrize(
    ("identity", "expected"),
    [
        (run_context_windows.ProcessIdentity(pid=7, creation_time=None, error=run_context_windows.ERROR_INVALID_PARAMETER),
         (run_context.ENDED, "not_found")),
        (run_context_windows.ProcessIdentity(pid=7, creation_time=None, error=5), (run_context.UNKNOWN, "query_failed")),
        (run_context_windows.ProcessIdentity(pid=7, creation_time=11, live=None, error=5, opened=True),
         (run_context.UNKNOWN, "query_failed")),
        (run_context_windows.ProcessIdentity(pid=7, creation_time=None, live=True, error=6, opened=True),
         (run_context.UNKNOWN, "query_failed")),
        (run_context_windows.ProcessIdentity(pid=7, creation_time=11, live=True, opened=True), (run_context.LIVE, "running")),
    ],
    ids=["no-such-process", "open-denied", "wait-denied", "creation-time-unreadable", "running"],
)
def test_only_a_positive_native_answer_ends_a_process(
    monkeypatch: pytest.MonkeyPatch, identity: run_context_windows.ProcessIdentity, expected: tuple[str, str],
) -> None:
    monkeypatch.setattr(run_context_windows, "process_identity", lambda _pid: identity)
    assert run_context.process_end_status(7, 11) == expected


@_windows
def test_an_entry_without_a_creation_time_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_context_windows, "process_identity", lambda _pid: pytest.fail("no query without an identity"))
    assert run_context.process_end_status(7, None) == (run_context.UNKNOWN, "incomplete_identity")


@pytest.mark.skipif(sys.platform == "win32", reason="the weaker POSIX capability")
def test_posix_presence_is_never_identity_proof() -> None:
    assert run_context.process_end_status(os.getpid(), None) == (run_context.UNKNOWN, "proc_present")


# --- Inventory, archive and verify against a synthetic registry.


def _record(run_id: str, worktree: Path) -> dict[str, object]:
    pid = int(run_id.split("-")[1])
    return {"checkpoint": "start", "run_id": run_id, "mode": "active", "reason": "default_selection",
            "worktree": str(worktree), "root": {"pid": pid, "creation_time": 1000 + pid}}


def _plant(registry: Path, run_id: str, worktree: Path) -> Path:
    run_context_records.write_record(registry / f"{run_id}.json", _record(run_id, worktree))
    return registry / f"{run_id}.json"


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A synthetic registry with one entry of every disposition. Root PIDs name their end status."""
    folder = tmp_path / "registry"
    folder.mkdir()
    gone, here = tmp_path / "removed-worktree", tmp_path / "present-worktree"
    here.mkdir()
    statuses = {11: (run_context.ENDED, "not_found"), 12: (run_context.ENDED, "replaced"), 13: (run_context.LIVE, "running"),
                14: (run_context.UNKNOWN, "query_failed"), 15: (run_context.ENDED, "terminated")}
    monkeypatch.setattr(run_context, "process_end_status", lambda pid, _created: statuses[pid])
    _plant(folder, "20260101T000000-11-aaaaaa", gone)
    _plant(folder, "20260101T000000-12-bbbbbb", gone)
    _plant(folder, "20260101T000000-13-cccccc", gone)
    _plant(folder, "20260101T000000-14-dddddd", gone)
    _plant(folder, "20260101T000000-15-eeeeee", here)
    (folder / "20260101T000000-16-ffffff.json").write_text("{not json", encoding="utf-8")
    misfiled = _record("20260101T000000-11-aaaaab", gone)
    run_context_records.write_record(folder / "20260101T000000-17-a0a0a0.json", misfiled)
    return folder


def _snapshot(folder: Path) -> dict[str, bytes]:
    """Every file of a synthetic registry and its archive folder, the only two levels maintenance touches."""
    found: dict[str, bytes] = {}
    for prefix, level in (("", folder), ("ended/", folder / "ended")):
        if level.is_dir():
            found.update({prefix + path.name: path.read_bytes() for path in level.iterdir() if path.is_file()})
    return found


def test_the_inventory_names_every_entry_and_changes_nothing(registry: Path) -> None:
    before = _snapshot(registry)
    manifest = maintenance.inventory(registry)
    assert _snapshot(registry) == before
    found = {entry["name"]: (entry["disposition"], entry["reason"]) for entry in manifest["entries"]}
    assert found == {
        "20260101T000000-11-aaaaaa.json": ("eligible", "worktree_absent_and_root_ended"),
        "20260101T000000-12-bbbbbb.json": ("eligible", "worktree_absent_and_root_ended"),
        "20260101T000000-13-cccccc.json": ("keep", "root_live"),
        "20260101T000000-14-dddddd.json": ("keep", "root_unknown"),
        "20260101T000000-15-eeeeee.json": ("keep", "worktree_present"),
        "20260101T000000-16-ffffff.json": ("keep", "malformed"),
        "20260101T000000-17-a0a0a0.json": ("keep", "misfiled"),
    }
    assert (manifest["total"], manifest["eligible"]) == (7, 2)
    eligible = [entry for entry in manifest["entries"] if entry["disposition"] == "eligible"]
    assert manifest["class_digest"] == maintenance.class_digest(eligible)


def test_a_missing_worktree_alone_is_never_enough(registry: Path) -> None:
    reasons = {entry["reason"] for entry in maintenance.inventory(registry)["entries"] if entry["disposition"] == "keep"}
    assert {"root_live", "root_unknown"} <= reasons


def test_a_dry_run_moves_nothing_and_a_wrong_grant_is_refused(registry: Path) -> None:
    manifest = maintenance.inventory(registry)
    before = _snapshot(registry)
    code, outcomes = maintenance.archive(manifest, str(manifest["class_digest"]), execute=False)
    assert code == 0 and {outcome["outcome"] for outcome in outcomes} == {"would_archive"}
    assert _snapshot(registry) == before
    with pytest.raises(SystemExit, match="granted class digest"):
        maintenance.archive(manifest, "0" * 64, execute=True)
    assert _snapshot(registry) == before


def test_the_granted_class_is_archived_with_one_receipt_each_and_the_rest_stays(registry: Path) -> None:
    manifest = maintenance.inventory(registry)
    kept = {name: data for name, data in _snapshot(registry).items() if not name.startswith("20260101T000000-1") or
            name.split("-")[1] not in {"11", "12"}}
    code, outcomes = maintenance.archive(manifest, str(manifest["class_digest"]), execute=True)
    assert code == 0 and sorted(outcome["outcome"] for outcome in outcomes) == ["archived", "archived"]
    after = _snapshot(registry)
    for name, data in kept.items():
        assert after[name] == data, name
    receipts = [json.loads(line) for line in (registry / "ended" / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sorted(receipt["name"] for receipt in receipts) == ["20260101T000000-11-aaaaaa.json", "20260101T000000-12-bbbbbb.json"]
    assert all(receipt["disposition"] == "archived" and receipt["end_status"] == run_context.ENDED for receipt in receipts)
    assert maintenance.verify(manifest) == (0, [])
    # Archived entries are no longer read as registered runs; the archive folder is not an entry.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(run_context_records, "registry_root", lambda: registry)
        listed = {entry["run_id"] for entry in run_context_records.registry_entries("none")[0]}
    assert "20260101T000000-11-aaaaaa" not in listed and "20260101T000000-13-cccccc" in listed
    # Running the same grant again changes nothing and adds no receipt.
    code, outcomes = maintenance.archive(manifest, str(manifest["class_digest"]), execute=True)
    assert code == 0 and {outcome["outcome"] for outcome in outcomes} == {"already_archived"}
    assert len((registry / "ended" / "receipts.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_an_entry_that_changed_after_the_inventory_is_refused_and_kept(registry: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = maintenance.inventory(registry)
    replaced = registry / "20260101T000000-11-aaaaaa.json"
    run_context_records.write_record(replaced, {**_record("20260101T000000-11-aaaaaa", registry.parent / "elsewhere"), "branch": "x"})
    code, outcomes = maintenance.archive(manifest, str(manifest["class_digest"]), execute=True)
    by_name = {outcome["name"]: outcome for outcome in outcomes}
    assert code == maintenance.EXIT_REFUSED
    assert by_name[replaced.name]["outcome"] == "refused" and replaced.exists()
    assert by_name["20260101T000000-12-bbbbbb.json"]["outcome"] == "archived"


def test_a_root_that_is_no_longer_ended_is_refused(registry: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = maintenance.inventory(registry)
    monkeypatch.setattr(run_context, "process_end_status", lambda _pid, _created: (run_context.UNKNOWN, "query_failed"))
    code, outcomes = maintenance.archive(manifest, str(manifest["class_digest"]), execute=True)
    assert code == maintenance.EXIT_REFUSED and {outcome["outcome"] for outcome in outcomes} == {"refused"}
    assert not (registry / "ended").exists()


def test_an_existing_different_destination_is_never_overwritten(registry: Path) -> None:
    manifest = maintenance.inventory(registry)
    (registry / "ended").mkdir()
    conflict = registry / "ended" / "20260101T000000-11-aaaaaa.json"
    conflict.write_bytes(b"someone else's bytes")
    code, outcomes = maintenance.archive(manifest, str(manifest["class_digest"]), execute=True)
    assert code == maintenance.EXIT_REFUSED and conflict.read_bytes() == b"someone else's bytes"
    assert (registry / "20260101T000000-11-aaaaaa.json").exists()


def test_an_interrupted_move_is_reconciled_from_what_is_on_disk(registry: Path) -> None:
    manifest = maintenance.inventory(registry)
    ended = registry / "ended"
    ended.mkdir()
    # Interrupted after the link, before the old name was removed.
    os.link(registry / "20260101T000000-11-aaaaaa.json", ended / "20260101T000000-11-aaaaaa.json")
    # Interrupted after the move, before the receipt.
    os.link(registry / "20260101T000000-12-bbbbbb.json", ended / "20260101T000000-12-bbbbbb.json")
    (registry / "20260101T000000-12-bbbbbb.json").unlink()
    code, outcomes = maintenance.archive(manifest, str(manifest["class_digest"]), execute=True)
    assert code == 0
    assert {outcome["name"]: outcome["outcome"] for outcome in outcomes} == {
        "20260101T000000-11-aaaaaa.json": "archived", "20260101T000000-12-bbbbbb.json": "reconciled"}
    assert maintenance.verify(manifest) == (0, [])


def test_verify_fails_on_a_missing_receipt_or_a_different_archived_copy(registry: Path) -> None:
    manifest = maintenance.inventory(registry)
    maintenance.archive(manifest, str(manifest["class_digest"]), execute=True)
    receipts = registry / "ended" / "receipts.jsonl"
    receipts.write_text(receipts.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    (registry / "ended" / "20260101T000000-11-aaaaaa.json").write_bytes(b"tampered")
    code, problems = maintenance.verify(manifest)
    assert code == maintenance.EXIT_MISMATCH and len(problems) == 2


def test_the_cli_inventory_never_overwrites_a_manifest(registry: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "manifest.json"
    assert maintenance.main(["inventory", "--registry", str(registry), "--out", str(out)]) == 0
    assert "eligible=2" in capsys.readouterr().out
    with pytest.raises(FileExistsError):
        maintenance.main(["inventory", "--registry", str(registry), "--out", str(out)])


def test_the_cli_refuses_a_manifest_the_shared_sanitizer_would_change(registry: Path, tmp_path: Path) -> None:
    """A registry file name is filesystem text anyone can plant; it never reaches a manifest or the terminal unchecked."""
    shaped_like_an_assignment = "token" + "=" + "hunter2" * 2
    (registry / f"zzz-{shaped_like_an_assignment}.json").write_text("{}", encoding="utf-8")
    out = tmp_path / "manifest.json"
    assert maintenance.main(["inventory", "--registry", str(registry), "--out", str(out)]) == maintenance.EXIT_REFUSED
    assert not out.exists()


def test_a_damaged_receipt_file_is_a_named_mismatch_never_a_crash(registry: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """A run interrupted while appending a receipt leaves a partial last line; archive and verify say so and move nothing."""
    manifest = maintenance.inventory(registry)
    maintenance.archive(manifest, str(manifest["class_digest"]), execute=True)
    receipts = registry / "ended" / "receipts.jsonl"
    receipts.write_text(receipts.read_text(encoding="utf-8") + '{"schema": "test-run-regi', encoding="utf-8")
    before = _snapshot(registry)
    assert maintenance.verify(manifest)[0] == maintenance.EXIT_MISMATCH
    out = tmp_path / "m.json"
    out.write_text(json.dumps(manifest), encoding="utf-8")
    assert maintenance.main(["archive", "--manifest", str(out), "--class-digest", str(manifest["class_digest"]), "--execute"]) == maintenance.EXIT_MISMATCH
    assert "receipts unreadable" in capsys.readouterr().out
    assert _snapshot(registry) == before


# --- Codex Checkpoint A C-M1: a receipt proves an archival only when it matches the manifest and the grant.


def _honest(registry: Path, manifest: dict[str, object], planned: dict[str, object], **changes: object) -> dict[str, object]:
    """The receipt the tool would write for `planned` under this manifest, with the given fields changed."""
    receipt: dict[str, object] = {
        "schema": maintenance.RECEIPT_SCHEMA, "name": planned["name"], "sha256": planned["sha256"], "run_id": planned["run_id"],
        "source": str(registry / str(planned["name"])), "target": str(registry / "ended" / str(planned["name"])),
        "end_status": run_context.ENDED, "end_basis": planned["end_basis"], "disposition": "archived",
        "class_digest": manifest["class_digest"], "utc": "2026-10-04T00:00:00+00:00",
    }
    receipt.update(changes)
    return receipt


def _place(registry: Path, manifest: dict[str, object], receipts: list[dict[str, object]]) -> None:
    """Archived copies of every eligible entry, moved by hand, plus exactly the given receipt lines."""
    ended = registry / "ended"
    ended.mkdir(exist_ok=True)
    for entry in _eligible_entries(manifest):
        os.replace(registry / str(entry["name"]), ended / str(entry["name"]))
    (ended / "receipts.jsonl").write_text("".join(json.dumps(receipt) + "\n" for receipt in receipts), encoding="utf-8")


def _eligible_entries(manifest: dict[str, object]) -> list[dict[str, object]]:
    return [entry for entry in manifest["entries"] if entry["disposition"] == "eligible"]  # type: ignore[union-attr]


def test_codex_forged_receipt_never_passes_verify_or_counts_as_archived(registry: Path) -> None:
    """Correct archived bytes, one schema-valid receipt with the wrong digest, class, paths and a LIVE root."""
    manifest = maintenance.inventory(registry)
    first, second = _eligible_entries(manifest)
    forged = _honest(registry, manifest, first, sha256="0" * 64, class_digest="f" * 64, source="C:/elsewhere/x.json",
                     target="C:/elsewhere/ended/x.json", end_status=run_context.LIVE)
    _place(registry, manifest, [forged, _honest(registry, manifest, second)])
    code, problems = maintenance.verify(manifest)
    assert code == maintenance.EXIT_MISMATCH and any(str(first["name"]) in problem for problem in problems), problems
    assert all(str(second["name"]) not in problem for problem in problems), problems
    code, outcomes = maintenance.archive(manifest, str(manifest["class_digest"]), execute=True)
    by_name = {outcome["name"]: outcome["outcome"] for outcome in outcomes}
    assert code == maintenance.EXIT_REFUSED and (by_name[first["name"]], by_name[second["name"]]) == ("refused", "already_archived")


@pytest.mark.parametrize(
    "change",
    [
        {"sha256": "0" * 64}, {"run_id": "20260101T000000-11-bbbbbb"}, {"source": "C:/elsewhere/x.json"},
        {"target": "C:/elsewhere/ended/x.json"}, {"end_status": "UNKNOWN"}, {"end_basis": "running"},
        {"disposition": "moved"}, {"class_digest": "f" * 64}, {"utc": "yesterday"},
    ],
    ids=["digest", "run-id", "source", "target", "status", "basis", "disposition", "class", "utc"],
)
def test_a_receipt_that_does_not_match_the_manifest_is_a_named_mismatch(registry: Path, change: object) -> None:
    manifest = maintenance.inventory(registry)
    first, second = _eligible_entries(manifest)
    broken = _honest(registry, manifest, first)
    broken.update(change)  # type: ignore[arg-type]
    _place(registry, manifest, [broken, _honest(registry, manifest, second)])
    code, problems = maintenance.verify(manifest)
    assert code == maintenance.EXIT_MISMATCH and any(str(first["name"]) in problem for problem in problems), problems
    assert all(str(second["name"]) not in problem for problem in problems), "a matching receipt stays valid"


def test_duplicate_and_foreign_receipts_in_the_class_are_named(registry: Path) -> None:
    manifest = maintenance.inventory(registry)
    first, second = _eligible_entries(manifest)
    foreign_name = "20260101T000000-99-999999.json"
    foreign = _honest(registry, manifest, {**first, "name": foreign_name, "run_id": foreign_name[:-5]})
    _place(registry, manifest, [_honest(registry, manifest, first), _honest(registry, manifest, second),
                                _honest(registry, manifest, first), foreign])
    code, problems = maintenance.verify(manifest)
    assert code == maintenance.EXIT_MISMATCH
    assert any(str(first["name"]) in problem and "2 receipts" in problem for problem in problems), problems
    assert any(foreign_name in problem for problem in problems), problems
    code, outcomes = maintenance.archive(manifest, str(manifest["class_digest"]), execute=True)
    assert code == maintenance.EXIT_REFUSED and {o["name"]: o["outcome"] for o in outcomes}[first["name"]] == "refused"


def test_a_valid_receipt_without_its_archived_copy_is_refused_not_archived_again(registry: Path) -> None:
    manifest = maintenance.inventory(registry)
    maintenance.archive(manifest, str(manifest["class_digest"]), execute=True)
    first = _eligible_entries(manifest)[0]
    (registry / "ended" / str(first["name"])).unlink()
    code, outcomes = maintenance.archive(manifest, str(manifest["class_digest"]), execute=True)
    assert code == maintenance.EXIT_REFUSED and {o["name"]: o["outcome"] for o in outcomes}[first["name"]] == "refused"
    assert maintenance.verify(manifest)[0] == maintenance.EXIT_MISMATCH


def test_receipts_from_another_grant_do_not_disturb_this_one(registry: Path) -> None:
    """The receipt file is append-only across grants: another class's receipts for other names are history."""
    manifest = maintenance.inventory(registry)
    first = _eligible_entries(manifest)[0]
    other_name = "20250101T000000-98-989898.json"
    other = _honest(registry, manifest, {**first, "name": other_name, "run_id": other_name[:-5]}, class_digest="e" * 64)
    (registry / "ended").mkdir()
    (registry / "ended" / "receipts.jsonl").write_text(json.dumps(other) + "\n", encoding="utf-8")
    code, outcomes = maintenance.archive(manifest, str(manifest["class_digest"]), execute=True)
    assert code == 0 and sorted(outcome["outcome"] for outcome in outcomes) == ["archived", "archived"]
    assert maintenance.verify(manifest) == (0, [])


# --- Codex Checkpoint A follow-up: a malformed receipt value is a named mismatch, never a crash or a pass.

_RECEIPT_VALUE_FIELDS = ("name", "sha256", "run_id", "source", "target", "end_status", "end_basis", "disposition", "class_digest", "utc")


_STRUCTURAL_DAMAGE = [
    *[pytest.param(field, value, id=f"{field}-{kind}") for field in _RECEIPT_VALUE_FIELDS
      for kind, value in (("list", ["archived"]), ("dict", {"x": 1}), ("int", 7), ("null", None))],
    pytest.param("disposition", [], id="codex-disposition-empty-list"),
    pytest.param("extra", "field", id="extra-field"),
    pytest.param("sha256", "<missing>", id="missing-field"),
]


@pytest.mark.parametrize(("field", "value"), _STRUCTURAL_DAMAGE)
def test_a_structurally_damaged_receipt_file_is_a_named_mismatch_and_moves_nothing(
    registry: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], field: str, value: object,
) -> None:
    """A receipt line that is not exactly the receipt schema with text values cannot be attributed to any
    entry, so the whole file is untrusted: verify names the line, archive refuses and nothing moves."""
    manifest = maintenance.inventory(registry)
    first, second = _eligible_entries(manifest)
    broken = _honest(registry, manifest, first)
    if value == "<missing>":
        del broken[field]
    else:
        broken[field] = value
    _place(registry, manifest, [_honest(registry, manifest, second), broken])
    before = _snapshot(registry)
    assert maintenance.verify(manifest) == (maintenance.EXIT_MISMATCH, ["receipts unreadable at line 2"])
    out = tmp_path / "m.json"
    out.write_text(json.dumps(manifest), encoding="utf-8")
    assert maintenance.main(["archive", "--manifest", str(out), "--class-digest", str(manifest["class_digest"]), "--execute"]) \
        == maintenance.EXIT_MISMATCH
    assert "receipts unreadable at line 2" in capsys.readouterr().out
    assert _snapshot(registry) == before


@pytest.mark.parametrize(
    "utc",
    ["2026-99-99T99:99:99+00:00", "2026-13-45T25:61:61+00:00", "2026-02-30T00:00:00+00:00", "２０２６-10-04T00:00:00+00:00",
     "2026-10-04T00:00:00+05:30", "2026-10-04 00:00:00+00:00", "2026-10-04T00:00:00Z", "2026-10-04T00:00:00.1234567+00:00"],
    ids=["codex-impossible-everything", "impossible-fields", "impossible-day", "non-ascii-digits", "not-utc", "space-separator", "z-suffix", "seven-fraction-digits"],
)
def test_a_receipt_time_must_be_a_real_utc_time_in_the_tool_s_form(registry: Path, utc: str) -> None:
    manifest = maintenance.inventory(registry)
    first, second = _eligible_entries(manifest)
    _place(registry, manifest, [_honest(registry, manifest, first, utc=utc), _honest(registry, manifest, second)])
    code, problems = maintenance.verify(manifest)
    assert code == maintenance.EXIT_MISMATCH and any(str(first["name"]) in problem and "utc" in problem for problem in problems), problems


def test_the_tool_s_own_receipt_times_are_accepted(registry: Path) -> None:
    """Control: receipts written by the tool itself (microsecond UTC times) verify."""
    manifest = maintenance.inventory(registry)
    assert maintenance.archive(manifest, str(manifest["class_digest"]), execute=True)[0] == 0
    assert maintenance.verify(manifest) == (0, [])
