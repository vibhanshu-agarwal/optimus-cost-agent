"""Plan 11.30 Task 2: the profile runner — Git change views, the selection record and supervised subruns."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools.testing import run_profile
from tools.testing import test_profiles as profiles


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-c", "user.name=Profile Test", "-c", "user.email=profile@example.invalid", "-c", "core.autocrlf=false", *arguments],
        cwd=repo, check=True, capture_output=True, text=True,
    )
    return completed.stdout.strip()


def _write(repo: Path, name: str, text: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    for name in ("a.py", "b.py", "c.py", "d.py", "f.py", "h.py"):
        _write(root, name, f"{name} = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _sha(repo: Path, name: str) -> str:
    return hashlib.sha256((repo / name).read_bytes()).hexdigest()


def test_inside_a_real_partial_commit_hook_the_commit_view_is_git_s_temporary_index(repo: Path, tmp_path: Path) -> None:
    """`git commit -- <path>` runs its hooks on a temporary index named by GIT_INDEX_FILE. The hook's commit view is
    exactly that partial commit, not the separately staged index; the hook's refusal leaves no commit behind."""
    head = _git(repo, "rev-parse", "HEAD")
    _write(repo, "b.py", "b = 'staged in the real index'\n")
    _git(repo, "add", "b.py")
    _write(repo, "a.py", "a = 'only this file is committed'\n")
    seen = tmp_path / "seen.json"
    script = tmp_path / "hook.py"
    script.write_text(
        "import json, os, sys\nfrom pathlib import Path\n"
        f"sys.path.insert(0, {str(run_profile.ROOT)!r})\n"
        "from tools.testing import run_profile\n"
        "found = run_profile.change_set(Path.cwd(), 'commit', None)\n"
        f"Path({str(seen)!r}).write_text(json.dumps({{'index': os.environ.get('GIT_INDEX_FILE'),"
        " 'changes': [[c.status, c.path] for c in found.changes], 'provisional': [path for path, _ in found.provisional]}))\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "{script.as_posix()}"\n', encoding="utf-8")
    hook.chmod(0o755)
    with pytest.raises(subprocess.CalledProcessError):
        _git(repo, "commit", "-q", "-m", "partial", "--", "a.py")
    found = json.loads(seen.read_text(encoding="utf-8"))
    assert found["index"] and Path(found["index"]).name != "index"  # git's temporary index for the partial commit
    # a.py is what this commit stages; b.py, staged only in the real index, is working-tree divergence from the
    # temporary index: selected and hashed as provisional. Read from the real index, the two would swap.
    assert sorted(found["changes"]) == [["M", "a.py"], ["M", "b.py"]] and found["provisional"] == ["b.py"]
    assert _git(repo, "rev-parse", "HEAD") == head and _git(repo, "diff", "--cached", "--name-only") == "b.py"


def test_the_commit_view_is_the_index_against_head_and_never_an_earlier_commit(repo: Path) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    _write(repo, "b.py", "b = 2\n")
    _git(repo, "commit", "-q", "-am", "earlier commit")
    _write(repo, "c.py", "c = 2\n")
    _git(repo, "add", "c.py")
    commit = run_profile.change_set(repo, "commit", None)
    assert commit.view == "commit" and commit.changes == (profiles.Change("M", "c.py"),) and commit.provisional == ()
    checkpoint = run_profile.change_set(repo, "checkpoint", base)
    assert {change.path for change in checkpoint.changes} == {"b.py", "c.py"}
    assert checkpoint.provisional == (("c.py", _sha(repo, "c.py")),)  # staged but not yet committed


def test_unstaged_divergence_is_selected_and_hashed_as_provisional_or_refused_for_exact_source(repo: Path) -> None:
    _write(repo, "c.py", "c = 2\n")
    _git(repo, "add", "c.py")
    _write(repo, "d.py", "d = 2\n")
    found = run_profile.change_set(repo, "commit", None)
    assert {change.path for change in found.changes} == {"c.py", "d.py"}
    assert found.provisional == (("d.py", _sha(repo, "d.py")),)
    with pytest.raises(profiles.SelectionError, match="d.py"):
        run_profile.change_set(repo, "commit", None, exact=True)


def test_a_checkpoint_includes_untracked_files_and_renames_deletes_and_unusual_names_survive(repo: Path) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "mv", "f.py", "g.py")
    _git(repo, "rm", "-q", "h.py")
    _write(repo, "spa ce é.py", "x = 1\n")
    _git(repo, "add", "spa ce é.py")
    _write(repo, "new_untracked.py", "n = 1\n")
    commit = run_profile.change_set(repo, "commit", None)
    assert set(commit.changes) == {
        profiles.Change("R", "g.py", "f.py"), profiles.Change("D", "h.py"), profiles.Change("A", "spa ce é.py"),
    }
    checkpoint = run_profile.change_set(repo, "checkpoint", base)
    assert profiles.Change("A", "new_untracked.py") in checkpoint.changes
    assert ("new_untracked.py", _sha(repo, "new_untracked.py")) in checkpoint.provisional
    assert ("h.py", None) in checkpoint.provisional


def test_an_unavailable_checkpoint_base_is_an_unavailable_old_view(repo: Path) -> None:
    found = run_profile.change_set(repo, "checkpoint", "0" * 40)
    assert found.old_graph is False


def test_a_checkpoint_needs_a_base_and_a_commit_needs_none(repo: Path) -> None:
    with pytest.raises(profiles.SelectionError, match="--base"):
        run_profile.change_set(repo, "checkpoint", None)
    with pytest.raises(profiles.SelectionError, match="--base"):
        run_profile.change_set(repo, "commit", "HEAD")


def test_an_empty_index_is_an_empty_commit_view(repo: Path) -> None:
    assert run_profile.change_set(repo, "commit", None).changes == ()


# --- Supervised subruns: real nested pytest sessions of this checkout, each an ACTIVE run with records. ---

_THIS = "tests/unit/tools/test_run_profile.py"
_LOAD = f"{_THIS}::test_profile_probe_load"
_REPEAT = f"{_THIS}::test_profile_probe_repeat"


def test_profile_probe_load() -> None:
    """Synthetic load target for the overlap controls; a no-op in an ordinary run."""
    time.sleep(float(os.environ.get("OPTIMUS_TEST_PROFILE_PROBE_LOAD_SECONDS", "0")))


def test_profile_probe_repeat() -> None:
    """Synthetic repeated target for the overlap controls; a no-op in an ordinary run."""
    if os.environ.get("OPTIMUS_TEST_PROFILE_PROBE_FAIL"):
        pytest.fail("planted failure in a load-overlap repeat")
    time.sleep(float(os.environ.get("OPTIMUS_TEST_PROFILE_PROBE_REPEAT_SECONDS", "0")))


def _env(tmp_path: Path, **values: str) -> dict[str, str]:
    scratch = tmp_path / "child-temp"
    scratch.mkdir(exist_ok=True)
    return {**os.environ, "TMPDIR": str(scratch), "TEMP": str(scratch), "TMP": str(scratch), **values}


def test_a_subrun_is_an_active_recorded_run_of_exactly_its_nodes(tmp_path: Path) -> None:
    result = run_profile.run_subrun(run_profile.ROOT, tmp_path / "out", "selected", (_REPEAT,), env=_env(tmp_path))
    assert result.exit_code == 0
    assert (result.mode, result.reason) == ("active", "default_selection")
    assert result.started_utc and result.finished_utc and result.started_utc <= result.finished_utc
    assert result.argfile.read_text(encoding="utf-8").splitlines() == [_REPEAT]
    assert "-k" not in result.command and "--count" not in result.command  # original internal depth
    assert "--audit-depth=full" in result.command and result.audit_depth == "full"  # asked for, and recorded by the run
    # Its own terminal record supports a pass: real supported Windows needs no qualification; POSIX keeps its weaker labels.
    assert result.problem is None
    assert result.executing_utc and result.executing_until_utc and result.executing_until_utc <= result.finished_utc
    if sys.platform == "win32":
        assert not [label for label in result.qualifications if label.startswith(("native=", "guard="))]
    else:
        assert {"native=unsupported", "guard=unsupported_platform"} <= set(result.qualifications)


@pytest.mark.skipif(sys.platform != "win32", reason="load-overlap repeats are Windows-only")
def test_every_counted_repeat_is_completely_overlapped_by_one_load_run(tmp_path: Path) -> None:
    env = _env(tmp_path, OPTIMUS_TEST_PROFILE_PROBE_LOAD_SECONDS="25", OPTIMUS_TEST_PROFILE_PROBE_REPEAT_SECONDS="0.2")
    outcome = run_profile.overlap(run_profile.ROOT, tmp_path / "out", (_LOAD,), (_REPEAT,), repeats=3, env=env)
    assert outcome.verdict == "complete", outcome
    assert outcome.required.exit_code == 0 and len(outcome.counted) == 3
    for repeat in outcome.counted:
        load = next(run for run in outcome.loads if run.run_id == repeat.load_run_id)
        assert load.started_utc <= repeat.started_utc and repeat.finished_utc <= load.finished_utc, (load, repeat)
    assert len({run.run_id for run in (*outcome.loads, *outcome.attempts)}) == len(outcome.loads) + len(outcome.attempts)


@pytest.mark.skipif(sys.platform != "win32", reason="load-overlap repeats are Windows-only")
def test_a_failed_repeat_stops_the_lane_and_is_kept(tmp_path: Path) -> None:
    env = _env(tmp_path, OPTIMUS_TEST_PROFILE_PROBE_LOAD_SECONDS="25", OPTIMUS_TEST_PROFILE_PROBE_FAIL="1")
    outcome = run_profile.overlap(run_profile.ROOT, tmp_path / "out", (_LOAD,), (_REPEAT,), repeats=3, env=env)
    assert outcome.verdict == "failed"
    assert [attempt.exit_code for attempt in outcome.attempts] == [1]
    assert all(run.process_alive is False for run in outcome.loads)


@pytest.mark.skipif(sys.platform != "win32", reason="load-overlap repeats are Windows-only")
def test_overlap_that_cannot_be_held_is_unrun_never_a_pass(tmp_path: Path) -> None:
    env = _env(tmp_path, OPTIMUS_TEST_PROFILE_PROBE_LOAD_SECONDS="3", OPTIMUS_TEST_PROFILE_PROBE_REPEAT_SECONDS="8")
    outcome = run_profile.overlap(run_profile.ROOT, tmp_path / "out", (_LOAD,), (_REPEAT,), repeats=1, max_attempts=2, env=env)
    assert outcome.verdict == "unrun"
    assert outcome.counted == () and len(outcome.attempts) == 2
    assert all(attempt.exit_code == 0 for attempt in outcome.attempts)  # passed, but not under load: not counted
    assert len(outcome.loads) >= 2  # the load workload was repeated to try to sustain overlap


def test_an_interrupted_lane_stops_only_its_own_processes(tmp_path: Path) -> None:
    foreign = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])  # noqa: S603
    try:
        env = _env(tmp_path, OPTIMUS_TEST_PROFILE_PROBE_LOAD_SECONDS="120", OPTIMUS_TEST_PROFILE_PROBE_REPEAT_SECONDS="0")

        def interrupt(event: str) -> None:
            if event.startswith("repeat-1 finished"):
                raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            run_profile.overlap(run_profile.ROOT, tmp_path / "out", (_LOAD,), (_REPEAT,), repeats=3, env=env, progress=interrupt)
        assert run_profile.owned_processes_alive() == 0
        assert foreign.poll() is None
    finally:
        foreign.kill()
        foreign.wait(timeout=30)


def test_a_dry_run_commit_writes_a_conforming_selection_record_and_runs_nothing(tmp_path: Path) -> None:
    out = tmp_path / "evidence"
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "tools.testing.run_profile", "--profile", "commit", "--dry-run", f"--output={out}"],
        cwd=run_profile.ROOT, env=_env(tmp_path), capture_output=True, text=True, timeout=600, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    written = Path(re.search(r"record=(\S+selection\.json)", completed.stdout)[1])  # type: ignore[index]
    assert written.parent.parent == out
    record = json.loads(written.read_text(encoding="utf-8"))
    assert record["schema"] == run_profile.SELECTION_SCHEMA and record["profile"] == "commit"
    assert record["label"] in {"selected", "no-commit-input"}
    assert {"manifest_sha256", "classification_sha256", "head", "index_sha256", "nodes", "reasons", "fallback", "domains"} <= set(record)
    assert all(set(entry) == {"node", "label"} and len(entry["node"]) == 64 for entry in record["nodes"])  # digests, never raw IDs
    assert not (written.parent / "subruns").exists()
    assert "test-profile: profile=commit" in completed.stdout


def test_an_input_failure_line_passes_the_shared_sanitizer() -> None:
    line = run_profile.failure_line("commit", profiles.SelectionError("unreadable docs/notes-http://user:hunter2@example.invalid.md"))  # pragma: allowlist secret - synthetic credential-shaped text the sanitizer must mask
    assert line.startswith("test-profile: profile=commit verdict=input-failure detail=")
    assert "hunter2" not in line


def test_a_selection_record_the_shared_sanitizer_would_change_is_refused() -> None:
    manifest = profiles.load_manifest('schema = "test-profiles-v1"\n[selection]\nprose_gates = ["tests/unit/docs/**"]\n')
    nodes = ("tests/unit/docs/test_docs_index.py::test_a",)
    classification = profiles.classify_nodes(nodes, manifest)
    path = "docs/notes-http://user:hunter2@example.invalid.md"  # pragma: allowlist secret - synthetic credential-shaped text the sanitizer must mask
    dependencies = profiles.build_dependency_map({}, (path,), manifest)
    changes = profiles.ChangeSet("commit", (profiles.Change("A", path),))
    selection = profiles.select_tests(changes, classification, dependencies, profiles.ProfileRequest("commit"))
    with pytest.raises(profiles.SelectionError, match="shared sanitizer"):
        run_profile.selection_record(run_profile.ROOT, changes, selection, classification, manifest, None)


def test_a_subrun_writes_to_the_runner_s_own_redirected_output(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    """Inside a hook the runner's stdout is a pipe or file; a subrun's failures must reach it, not vanish."""
    result = run_profile.run_subrun(run_profile.ROOT, tmp_path / "out", "selected", (_REPEAT,), env=_env(tmp_path))
    assert result.exit_code == 0
    assert "1 passed" in capfd.readouterr().out


_GONE = object()


def _terminal(platform: str = "win32", **changes: object) -> dict[str, object]:
    """The validity-bearing fields of a terminal run record, as a supported Windows or a qualified POSIX session writes them."""
    windows = platform == "win32"
    record: dict[str, object] = {
        "checkpoint": "terminal", "run_id": "20261004T180537-3948-0248dd", "mode": "active", "platform": platform,
        "started_utc": "2026-10-04T18:05:37.000000+00:00", "finished_utc": "2026-10-04T18:05:39.000000+00:00",
        "completeness": "COMPLETE", "exit_status": 0,
        "native": {"supported": True, "attempted": True, "enrolled": True, "valid": True} if windows
        else {"supported": False, "attempted": False, "enrolled": False},
        "guard_mode": "pytest_process_guard" if windows else "unsupported_platform",
        "protection": "full" if windows else "none",
        "parent_run": {"status": "none"} if windows else {"status": "unsupported"},
        "audit_depth": "full",
    }
    if windows:
        record.update({"accounting": {"ok": True, "total_processes": 9}, "members": {"ok": True, "complete": True, "identities": []}})
    record.update(changes)
    return {name: value for name, value in record.items() if value is not _GONE}


@pytest.mark.parametrize(("changes", "problem"), [
    ({"checkpoint": "start"}, "no_terminal_record"),
    ({"finished_utc": _GONE}, "no_terminal_record"),
    ({"completeness": "INVALID"}, "records_INVALID"),
    ({"completeness": "TRUNCATED"}, "records_TRUNCATED"),
    ({"terminal_failure": "record.streams"}, "terminal_failure"),
    ({"exit_status": 1}, "exit_status_differs"),
    ({"mode": "passive"}, "mode_passive"),
    ({"native": {"supported": True, "attempted": True, "enrolled": True, "valid": False}}, "native_invalid"),
    ({"native": {"supported": True, "attempted": True, "enrolled": False}}, "native_invalid"),
    ({"native": {"supported": True, "attempted": False, "enrolled": False}}, "native_not_enrolled"),
    ({"native": {"supported": False, "attempted": False, "enrolled": False}}, "native_unsupported"),
    ({"guard_mode": "not_installed"}, "guard_not_installed"),
    ({"guard_mode": "unsupported_platform"}, "guard_unsupported_platform"),
    # Reduced-depth audits are never evidence the runner can count (Plan 11.30 Task 4), nor is a record that does not say.
    ({"audit_depth": "quick"}, "audit_depth_quick"),
    ({"audit_depth": _GONE}, "audit_depth_missing"),
])
def test_an_exit_zero_active_record_without_terminal_or_capability_evidence_cannot_support_a_pass(
    changes: dict[str, object], problem: str,
) -> None:
    assert run_profile.record_validity(_terminal(**changes), 0) == (problem, ())


def test_a_missing_record_or_a_posix_guard_failure_cannot_support_a_pass() -> None:
    assert run_profile.record_validity(None, 0) == ("no_run_record", ())
    assert run_profile.record_validity(_terminal("linux", guard_mode="not_installed"), 0) == ("guard_not_installed", ())
    assert run_profile.record_validity(_terminal("linux", completeness="INVALID"), 0) == ("records_INVALID", ())


@pytest.mark.parametrize(("record", "qualifications"), [
    (_terminal(), ()),
    (_terminal(parent_run={"status": "UNKNOWN", "reason": "registry_partial"}), ("parent=UNKNOWN:registry_partial",)),
    (_terminal(guard_mode="main5_guard_present", protection="none"), ("guard=main5_guard_present",)),
    (_terminal(protection="reduced"), ("protection=reduced",)),
    (_terminal(parent_run={"status": "not_found", "reason": "ancestor_exited"}), ("parent=not_found:ancestor_exited",)),
    (_terminal(accounting={"ok": False}), ("processes=QUERY_FAILED",)),
    (_terminal(members={"ok": True, "complete": False, "identities": []}), ("members=incomplete",)),
    (_terminal("linux"), ("native=unsupported", "guard=unsupported_platform", "parent=unsupported")),
])
def test_legitimate_qualifications_are_kept_and_never_turned_into_failure(
    record: dict[str, object], qualifications: tuple[str, ...],
) -> None:
    assert run_profile.record_validity(record, 0) == (None, qualifications)


def _selection(*nodes: str, concurrency: tuple[str, ...] = ()) -> profiles.Selection:
    return profiles.Selection("checkpoint", "selected", nodes, {node: "test" for node in nodes}, (), (), {}, (), (), concurrency, "full")


def _classification(**tiers: str) -> profiles.Classification:
    return profiles.Classification({f"t::{name}": tier for name, tier in tiers.items()}, {}, {}, ())


def _subrun(tmp_path: Path, name: str, *, exit_code: int = 0, problem: str | None = None) -> run_profile.SubrunResult:
    argfile = tmp_path / f"{name}.txt"
    argfile.write_text("t::a\n", encoding="utf-8")
    return run_profile.SubrunResult(name, ("t::a",), (), argfile, exit_code=exit_code, run_id="20261004T180537-3948-0248dd",
                                    mode="active", reason="default_selection", problem=problem)


@pytest.mark.parametrize("problem", ["records_INVALID", "native_invalid", "no_terminal_record"])
def test_an_exit_zero_active_subrun_whose_record_cannot_support_a_pass_is_invalid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, problem: str,
) -> None:
    monkeypatch.setattr(run_profile, "run_subrun", lambda *args, **kwargs: _subrun(tmp_path, "selected", problem=problem))
    verdict, code, _subruns, _outcome, detail = run_profile.execute(run_profile.ROOT, tmp_path, _selection("t::a"), _classification(a="core"))
    assert (verdict, code, detail) == ("invalid", run_profile.EXIT_INVALID, f"selected: {problem}")


def test_a_subrun_never_validated_against_its_record_is_invalid_not_a_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The reviewer's boundary probe: ACTIVE, exit 0 and no terminal time must not pass."""
    unvalidated = run_profile.SubrunResult("selected", ("t::a",), (), tmp_path / "nodes.txt", exit_code=0, mode="active")
    monkeypatch.setattr(run_profile, "run_subrun", lambda *args, **kwargs: unvalidated)
    verdict, code, *_ = run_profile.execute(run_profile.ROOT, tmp_path, _selection("t::a"), _classification(a="core"))
    assert (verdict, code) == ("invalid", run_profile.EXIT_INVALID)


def test_a_valid_subrun_passes_and_a_failed_one_stays_failed_whatever_its_record(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run_profile, "run_subrun", lambda *args, **kwargs: _subrun(tmp_path, "selected"))
    assert run_profile.execute(run_profile.ROOT, tmp_path, _selection("t::a"), _classification(a="core"))[:2] == ("pass", 0)
    monkeypatch.setattr(run_profile, "run_subrun", lambda *args, **kwargs: _subrun(tmp_path, "selected", exit_code=1, problem="records_INVALID"))
    assert run_profile.execute(run_profile.ROOT, tmp_path, _selection("t::a"), _classification(a="core"))[:2] == ("failed", run_profile.EXIT_TESTS_FAILED)


def test_a_subrun_that_never_begins_its_tests_makes_the_run_invalid_with_its_reason(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A start timeout is a failure of the run itself: reported in the manifest, never a traceback or the tests-failed code."""
    def stalled(*args: object, **kwargs: object) -> object:
        raise profiles.SelectionError("subrun load-1 did not begin a test phase within 300 s")

    selected = _subrun(tmp_path, "selected")
    monkeypatch.setattr(run_profile, "run_subrun", lambda root, out, name, *args, **kwargs: selected if name == "selected" else stalled())
    monkeypatch.setattr(run_profile, "overlap", stalled)
    selection = _selection("t::a", "t::audit", concurrency=("t::a",))
    verdict, code, subruns, outcome, detail = run_profile.execute(run_profile.ROOT, tmp_path, selection, _classification(a="core", audit="audit-current"))
    assert (verdict, code, subruns, outcome) == ("invalid", run_profile.EXIT_INVALID, [selected], None)
    assert detail == "subrun load-1 did not begin a test phase within 300 s"


def test_a_start_failure_detail_passes_the_shared_sanitizer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def stalled(*args: object, **kwargs: object) -> object:
        raise profiles.SelectionError("subrun selected did not begin under http://user:hunter2@example.invalid")  # pragma: allowlist secret - synthetic credential-shaped text the sanitizer must mask

    monkeypatch.setattr(run_profile, "run_subrun", stalled)
    verdict, _code, _subruns, _outcome, detail = run_profile.execute(run_profile.ROOT, tmp_path, _selection("t::a"), _classification(a="core"))
    assert verdict == "invalid" and detail.startswith("subrun selected did not begin") and "hunter2" not in detail


@pytest.mark.skipif(sys.platform != "win32", reason="load-overlap repeats are Windows-only")
def test_a_load_that_stops_beginning_its_tests_keeps_what_already_ran_and_is_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A stall after a repeat ran: the lane stops its own load, keeps that load and the repeat, and says why."""
    real, calls = run_profile.wait_until_executing, []

    def stalls_the_second_time(root: Path, result: run_profile.SubrunResult, process: object) -> bool:
        calls.append(result.name)
        if len(calls) == 2:
            raise profiles.SelectionError(f"subrun {result.name} did not begin a test phase within 300 s")
        return real(root, result, process)  # type: ignore[arg-type]

    monkeypatch.setattr(run_profile, "wait_until_executing", stalls_the_second_time)
    env = _env(tmp_path, OPTIMUS_TEST_PROFILE_PROBE_LOAD_SECONDS="25", OPTIMUS_TEST_PROFILE_PROBE_REPEAT_SECONDS="0")
    outcome = run_profile.overlap(run_profile.ROOT, tmp_path / "out", (_LOAD,), (_REPEAT,), repeats=3, env=env)
    assert (outcome.verdict, outcome.detail) == ("invalid", "subrun load-1 did not begin a test phase within 300 s")
    assert [load.name for load in outcome.loads] == ["load-1"] and outcome.loads[0].terminated
    assert [(attempt.name, attempt.exit_code) for attempt in outcome.attempts] == [("repeat-1", 0)] and outcome.counted == ()
    assert run_profile.owned_processes_alive() == 0


def test_a_stalled_load_detail_passes_the_shared_sanitizer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def stalled(root: Path, result: run_profile.SubrunResult, process: object) -> bool:
        raise profiles.SelectionError(f"subrun {result.name} stalled under http://user:hunter2@example.invalid")  # pragma: allowlist secret - synthetic credential-shaped text the sanitizer must mask

    monkeypatch.setattr(run_profile, "wait_until_executing", stalled)
    env = _env(tmp_path, OPTIMUS_TEST_PROFILE_PROBE_LOAD_SECONDS="25")
    outcome = run_profile.overlap(run_profile.ROOT, tmp_path / "out", (_LOAD,), (_REPEAT,), repeats=3, env=env)
    assert outcome.verdict == "invalid" and outcome.detail.startswith("subrun load-1 stalled") and "hunter2" not in outcome.detail
    assert outcome.loads[0].terminated and run_profile.owned_processes_alive() == 0


@pytest.mark.skipif(sys.platform != "win32", reason="the load-overlap lane is Windows-only")
@pytest.mark.parametrize(("verdict", "problem", "expected"), [
    ("unrun", "records_INVALID", ("invalid", "load-1: records_INVALID")),
    ("invalid", None, ("invalid", "subrun load-2 did not begin a test phase within 300 s")),
    ("anything-else", None, ("invalid", "unknown stability verdict anything-else")),
])
def test_an_overlap_lane_that_cannot_count_names_why(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, verdict: str, problem: str | None, expected: tuple[str, str],
) -> None:
    load = _subrun(tmp_path, "load-1", problem=problem)
    detail = "subrun load-2 did not begin a test phase within 300 s" if verdict == "invalid" else "only 0 of 3 repeats were completely overlapped in 3 attempts"
    outcome = run_profile.OverlapOutcome(verdict, load, (load,), (), (), detail)
    monkeypatch.setattr(run_profile, "run_subrun", lambda *args, **kwargs: _subrun(tmp_path, "selected"))
    monkeypatch.setattr(run_profile, "overlap", lambda *args, **kwargs: outcome)
    selection = _selection("t::a", "t::audit", concurrency=("t::a",))
    found = run_profile.execute(run_profile.ROOT, tmp_path, selection, _classification(a="core", audit="audit-current"))
    assert (found[0], found[1], found[4]) == (expected[0], run_profile.EXIT_INVALID, expected[1]) and load in found[2]


def _timed(name: str, started: int, finished: int, *, executing: int | None = None, until: int | None = None,
           problem: str | None = None, terminated: bool = False) -> run_profile.SubrunResult:
    def at(second: int | None) -> str | None:
        return None if second is None else f"2026-10-04T18:00:{second:02d}.000000+00:00"

    return run_profile.SubrunResult(name, ("t::a",), (), Path("nodes.txt"), exit_code=0, run_id=f"run-{name}", mode="active",
                                    started_utc=at(started), finished_utc=at(finished), executing_utc=at(executing),
                                    executing_until_utc=at(until), problem=problem, terminated=terminated)


def test_a_repeat_counts_only_inside_its_load_s_recorded_test_phases() -> None:
    load = _timed("load-1", 0, 50, executing=5, until=40)
    assert run_profile.covers(load, _timed("repeat-1", 10, 30))
    assert not run_profile.covers(load, _timed("repeat-2", 10, 45))  # ends in the load's teardown tail
    assert not run_profile.covers(load, _timed("repeat-3", 3, 30))  # starts before the load executes
    assert not run_profile.covers(load, _timed("repeat-4", 10, 30, problem="records_INVALID"))
    assert not run_profile.covers(_timed("load-2", 0, 50, executing=5, until=40, problem="records_INVALID"), _timed("repeat-5", 10, 30))
    # A load this runner stopped has no terminal record; its recorded phases still prove it was executing.
    stopped = _timed("load-3", 0, 50, executing=5, until=40, problem="no_terminal_record", terminated=True)
    assert run_profile.covers(stopped, _timed("repeat-6", 10, 30))
    assert not run_profile.covers(stopped, _timed("repeat-7", 10, 45))
