"""Checkpoint A proofs for the pytest run context: selection, native ownership and root protection.

These tests exercise the real session they run in, and real nested pytest processes. Nothing here
writes to the real application folders: the denial probe targets a path whose parent does not
exist, so even a broken guard could not create it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.testing import run_context, run_context_guard, run_context_records, run_context_windows

_ROOT = Path(__file__).resolve().parents[3]
_THIS = "tests/unit/tools/test_run_context.py"
_SUMMARY = re.compile(r"test-run-context: (?P<body>[^=\n]+(?:=[^ \n=]*)(?: [^ \n=]+=[^ \n=]*)*)")
_windows = pytest.mark.skipif(sys.platform != "win32", reason="native job ownership is Windows-only")


def _context(request: pytest.FixtureRequest) -> run_context.RunContext:
    for value in request.config.stash._storage.values():  # noqa: SLF001 - the stash key is private to conftest
        if isinstance(value, run_context.RunContext):
            return value
    raise AssertionError("the root conftest did not start a run context")


def _nested(*arguments: str) -> tuple[int, dict[str, str], str]:
    """Run a real nested pytest and return its exit code, parsed summary line and output."""
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", *arguments],
        cwd=_ROOT, capture_output=True, text=True, timeout=300, check=False,
    )
    output = completed.stdout + completed.stderr
    found = _SUMMARY.search(output)
    fields = dict(part.split("=", 1) for part in found.group("body").split(" ")) if found else {}
    return completed.returncode, fields, output


def test_probe_noop() -> None:
    """A do-nothing target for the nested runs below."""


def test_probe_sentinel(request: pytest.FixtureRequest) -> None:
    """Synthetic target for the nested selection probes: reports what the session it ran in did.

    It does nothing in an ordinary run. A probe names a sentinel file through the environment, and
    may ask for a marker so that a non-default selection has something harmless to select.
    """
    sentinel = os.environ.get("OPTIMUS_TEST_RUN_CONTEXT_PROBE_SENTINEL")
    if not sentinel:
        return
    from optimus.acp import trusted_paths

    context = _context(request)
    owner = run_context_windows.owner()
    Path(sentinel).write_text(json.dumps({
        "mode": context.mode, "reason": context.reason, "guard": run_context_guard.mode(),
        "owns_job": owner is not None and owner.handle is not None,
        "real_adapter_replaced": trusted_paths._real_windows_known_folders is run_context_guard._refuse_real_adapter,  # noqa: SLF001
        "protected_roots": len(run_context_guard.protected_roots()),
    }), encoding="utf-8")


if os.environ.get("OPTIMUS_TEST_RUN_CONTEXT_PROBE_MARK"):
    test_probe_sentinel = getattr(pytest.mark, os.environ["OPTIMUS_TEST_RUN_CONTEXT_PROBE_MARK"])(test_probe_sentinel)


def test_this_default_session_is_active_and_recorded(request: pytest.FixtureRequest) -> None:
    context = _context(request)
    assert (context.mode, context.reason) == ("active", "default_selection")
    record = run_context_records.read_record(context.record_dir / "run.json")
    assert record is not None and record["run_id"] == context.run_id and record["mode"] == "active"
    registry = run_context_records.read_record(run_context_records.registry_root() / f"{context.run_id}.json")
    assert registry is not None and registry["root"] == context.root


def test_records_hold_identifiers_only_and_are_bounded(request: pytest.FixtureRequest, tmp_path: Path) -> None:
    context = _context(request)
    text = (context.record_dir / "run.json").read_text(encoding="utf-8")
    record = run_context_records.read_record(context.record_dir / "run.json")
    assert record is not None
    allowed = {
        "schema", "checkpoint", "run_id", "mode", "reason", "session_index", "started_utc", "worktree", "branch",
        "head", "declared_agent", "withheld", "platform", "root", "root_parent", "parent_run", "native",
        "guard_mode", "exit_status", "finished_utc", "accounting", "members",
    }
    assert sorted(set(record) - allowed) == []
    for identity in (record["root"], record["root_parent"]):
        assert sorted(set(identity) - {"pid", "creation_time", "image", "error", "live"}) == []
    # No command line, argument vector or environment value is ever a record field or value.
    leaked = [word for word in ("argv", "command_line", "environ", "--cov", "-m pytest", sys.argv[0]) if word and word in text]
    assert leaked == []
    assert len(text.encode("utf-8")) <= run_context_records.MAX_RECORD_BYTES

    assert record["withheld"] == []
    # A conforming record that is simply too big is refused as well, and nothing is left behind.
    oversized = {name: value for name, value in record.items() if name != "schema"}
    oversized["members"] = {"ok": True, "complete": True, "identities": [record["root"]] * run_context_records.MAX_MEMBERS}
    with pytest.raises(ValueError, match=run_context_records.TOO_LARGE):
        run_context_records.write_record(tmp_path / "big.json", oversized)
    assert not (tmp_path / "big.json").exists()
    (tmp_path / "foreign.json").write_text('{"schema": "something-else"}', encoding="utf-8")
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert run_context_records.read_record(tmp_path / "foreign.json") is None
    assert run_context_records.read_record(tmp_path / "broken.json") is None
    assert run_context_records.read_record(tmp_path / "missing.json") is None


@_windows
def test_the_pytest_process_owns_a_kill_on_close_job_without_breakaway(request: pytest.FixtureRequest) -> None:
    context = _context(request)
    native = context.native
    assert native["attempted"] is True and native["enrolled"] is True and native["valid"] is True, native
    assert native["created"] is True and native["name_already_existed"] is False
    assert native["handle_inheritable"] is False
    assert (native["kill_on_close"], native["breakaway_ok"], native["silent_breakaway_ok"]) == (True, False, False)
    assert run_context_windows.is_member(run_context_windows.current_identity()) is True
    # The process that started pytest is not part of this run's job: a run enrols only itself.
    assert run_context_windows.is_member(run_context_windows.parent_identity()) is False


def test_the_context_creates_no_thread() -> None:
    offending = [thread.name for thread in threading.enumerate() if "run_context" in thread.name.lower() or "run-context" in thread.name.lower()]
    assert offending == []
    for module in (run_context, run_context_guard, run_context_records, run_context_windows):
        source = Path(module.__file__).read_text(encoding="utf-8")
        used = [name for name in ("import threading", "from threading", "import multiprocessing", "subprocess.", "OpenJobObject") if name in source]
        assert used == [], f"{module.__name__} must not use {used}"


def test_a_nested_default_pytest_completes_and_names_this_run_as_its_parent(request: pytest.FixtureRequest) -> None:
    context = _context(request)
    code, fields, output = _nested(f"{_THIS}::test_probe_noop")
    assert code == 0, output
    assert fields.get("mode") == "active", output
    if sys.platform == "win32":
        assert fields.get("native") == "valid", output
        assert fields.get("parent") == context.run_id, output
        assert fields.get("job", "").startswith("optimus-test-run-") and fields["job"] != context.native["job_name"]
    else:
        assert fields.get("native") == "unsupported" and fields.get("parent") == "unsupported", output


@pytest.mark.parametrize(
    ("arguments", "reason", "exit_code"),
    [
        (("--collect-only",), "collection_only", 0),
        (("-m", "e2e"), "non_default_selection", 5),
        (("--test-run-context=passive",), "requested", 0),
    ],
)
def test_other_selections_stay_passive(arguments: tuple[str, ...], reason: str, exit_code: int) -> None:
    code, fields, output = _nested(f"{_THIS}::test_probe_noop", *arguments)
    assert code == exit_code, output
    assert (fields.get("mode"), fields.get("reason")) == ("passive", reason), output
    assert fields.get("native") in {"not_enrolled", "unsupported"}, output
    assert fields.get("guard") == "not_installed", output


@_windows
def test_a_test_that_omits_the_fixture_cannot_reach_or_write_the_real_folders(request: pytest.FixtureRequest) -> None:
    from optimus.acp import trusted_paths

    context = _context(request)
    if context.guard_mode == "main5_guard_present":
        # The MAIN-5 guard is in force and is stricter. Probing it here would itself be a recorded
        # MAIN-5 violation, and its own self-test lane already proves its refusals. This guard
        # must have stood aside: no adapter replaced, no synthetic default installed.
        assert run_context_guard.protected_roots() == ()
        assert trusted_paths._real_windows_known_folders is not run_context_guard._refuse_real_adapter  # noqa: SLF001
        return
    assert context.guard_mode == "pytest_process_guard"
    protected = run_context_guard.protected_roots()
    assert len(protected) >= 3 and all("optimus-cost-agent" in root or "python keyring" in root for root in protected)

    with pytest.raises(RuntimeError, match=run_context_guard.REAL_ADAPTER_REFUSAL):
        trusted_paths._real_windows_known_folders()  # noqa: SLF001

    roots = trusted_paths.resolve_trusted_operator_roots(platform_name="win32")
    for resolved in (roots.default_config_root, roots.approval_runtime_root):
        assert not run_context_guard._is_protected(resolved), resolved  # noqa: SLF001
        assert "known-folders" in str(resolved)
    (roots.approval_runtime_root / "locks").mkdir(parents=True)
    (roots.approval_runtime_root / "locks" / "probe.lock").write_text("synthetic", encoding="utf-8")

    # Parent folder does not exist: a broken guard would fail with FileNotFoundError, not create a file.
    target = Path(protected[1]) / "__test_run_context_denial_probe__" / "probe.txt"
    with pytest.raises(PermissionError, match=run_context_guard.WRITE_REFUSAL):
        open(target, "w", encoding="utf-8")  # noqa: SIM115
    assert not target.exists() and not target.parent.exists()


@_windows
def test_a_test_that_supplies_its_own_adapter_keeps_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from optimus.acp import trusted_paths

    fake = SimpleNamespace(roaming_appdata=tmp_path / "R", local_appdata=tmp_path / "L")
    monkeypatch.setattr(trusted_paths, "_real_windows_known_folders", lambda: fake)
    roots = trusted_paths.resolve_trusted_operator_roots(platform_name="win32")
    assert roots.approval_runtime_root == tmp_path / "L" / "optimus-cost-agent"


@_windows
def test_a_nested_pytest_is_guarded_too() -> None:
    node = f"{_THIS}::test_a_test_that_omits_the_fixture_cannot_reach_or_write_the_real_folders"
    code, fields, output = _nested(node)
    assert code == 0, output
    assert fields.get("guard") in {"pytest_process_guard", "main5_guard_present"}, output
