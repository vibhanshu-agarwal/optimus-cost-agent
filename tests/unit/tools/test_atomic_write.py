"""#691: an approved WRITE or EDIT reaches disk through a staging file beside the resolved target and one atomic replace, so a
failure at any step leaves the target's original bytes and no staging file. Refusals today's in-place write made stay
refusals. Each platform-specific case has a stand-in that runs everywhere."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from optimus.guardrails.file_policy import FilePolicy, FilePurpose
from optimus.guardrails.pre_tool import PreToolResult, PreToolVerdict
from optimus.guardrails.runtime_tree import staging_name
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import AgentState, RuntimeContext
from optimus.tools import mutation_tools
from optimus.tools.mutation_tools import WriteFailed, write_file, write_file_keeping_line_endings

LEFTOVER = ".optimus-write-0123456789abcdef.tmp"


class _Allow:
    def check(self, request):
        return PreToolResult(verdict=PreToolVerdict.ALLOW, rule_id="test.allow", reason="allowed")


def _context() -> RuntimeContext:
    return RuntimeContext(
        execution_mode=ExecutionMode.AGENT, state=AgentState.EXECUTING, approval_granted=True, user_approval_id="approval-1"
    )


def _write(target: Path, body: str = "new\n", root: Path | None = None) -> None:
    write_file_keeping_line_endings(target, body, context=_context(), guard=_Allow(), workspace_root=root)


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_a_write_replaces_the_file_and_leaves_no_staging_file(tmp_path):
    (tmp_path / "a.py").write_bytes(b"old\r\n")
    _write(tmp_path / "a.py", "one\ntwo\n")

    assert (tmp_path / "a.py").read_bytes() == b"one\r\ntwo\r\n"  # the file's own line endings, as before
    assert _names(tmp_path) == ["a.py"]


def test_an_exact_write_translates_newlines_as_write_text_did(tmp_path):
    for newline, expected in (("", b"a\nb\n"), ("\n", b"a\nb\n"), ("\r\n", b"a\r\nb\r\n"), (None, os.linesep.join(["a", "b", ""]).encode())):
        write_file(tmp_path / "e.py", "a\nb\n", context=_context(), guard=_Allow(), newline=newline)
        assert (tmp_path / "e.py").read_bytes() == expected, newline


def _fail(monkeypatch, name: str):
    real = {"open": os.open, "fsync": os.fsync, "chmod": os.chmod, "replace": mutation_tools._swap_in}[name]

    def failing(*args, **kwargs):
        if name == "open" and not args[1] & os.O_CREAT:
            return real(*args, **kwargs)  # the write-open probe of the existing target; only the staging open fails
        raise OSError(28, "No space left on device")

    if name == "replace":  # the publish seam: os.replace, or ReplaceFileW for an existing target on Windows
        monkeypatch.setattr(mutation_tools, "_swap_in", failing)
    else:
        monkeypatch.setattr(os, name, failing)


@pytest.mark.parametrize(("patched", "step"), [("open", "stage"), ("fsync", "fsync"), ("chmod", "chmod"), ("replace", "replace")])
def test_each_step_that_fails_leaves_the_original_bytes_and_no_staging_file(patched, step, tmp_path, monkeypatch):
    (tmp_path / "a.py").write_bytes(b"old\n")
    _fail(monkeypatch, patched)

    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "a.py")

    assert failed.value.step == step and failed.value.no_effect is True
    assert (tmp_path / "a.py").read_bytes() == b"old\n"
    assert _names(tmp_path) == ["a.py"]


def test_a_staging_write_that_fails_part_way_leaves_the_original_bytes(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_bytes(b"old\n")
    real_fdopen = os.fdopen

    def half_written(descriptor, mode):
        handle = real_fdopen(descriptor, mode)
        real_write = handle.write

        def write(data):
            real_write(data[:1])
            raise OSError(28, "No space left on device")

        handle.write = write
        return handle

    monkeypatch.setattr(os, "fdopen", half_written)
    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "a.py", "a much longer body\n")

    assert failed.value.step == "stage" and failed.value.no_effect is True
    assert (tmp_path / "a.py").read_bytes() == b"old\n" and _names(tmp_path) == ["a.py"]


def test_a_staging_file_that_cannot_be_removed_is_an_effect(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_bytes(b"old\n")
    _fail(monkeypatch, "replace")

    def stuck(self, missing_ok=False):
        raise PermissionError(13, "in use")

    monkeypatch.setattr(Path, "unlink", stuck)
    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "a.py")

    assert failed.value.step == "replace, then cleanup" and failed.value.no_effect is False
    assert (tmp_path / "a.py").read_bytes() == b"old\n"  # the target is still untouched
    [leftover] = [name for name in _names(tmp_path) if name != "a.py"]
    assert FilePolicy(tmp_path).path_denial(leftover) == "deny.staging_file"


def test_a_failed_write_into_new_folders_is_no_effect_only_once_the_folders_are_gone(tmp_path, monkeypatch):
    _fail(monkeypatch, "fsync")
    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "x" / "y" / "z.py", root=tmp_path)
    assert failed.value.no_effect is True and _names(tmp_path) == []

    def kept(self):
        raise OSError(39, "Directory not empty")

    monkeypatch.setattr(Path, "rmdir", kept)
    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "x" / "y" / "z.py", root=tmp_path)
    assert failed.value.no_effect is False  # a folder this write made is still there


class _Sharing(PermissionError):
    winerror = 32  # what Windows reports while another process holds the target


def test_a_replace_held_briefly_by_another_process_is_retried(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_bytes(b"old\n")
    real, attempts = mutation_tools._swap_in, []

    def held_twice(source, target, **kwargs):
        attempts.append(1)
        if len(attempts) <= 2:
            raise _Sharing(13, "in use")
        real(source, target, **kwargs)

    waits: list[float] = []
    monkeypatch.setattr(mutation_tools, "_swap_in", held_twice)
    monkeypatch.setattr(mutation_tools.time, "sleep", waits.append)
    _write(tmp_path / "a.py")

    assert waits == [0.05, 0.05]  # about 50 ms between attempts
    assert len(attempts) == 3 and (tmp_path / "a.py").read_bytes() == b"new\n" and _names(tmp_path) == ["a.py"]


def test_a_target_held_open_for_good_fails_after_three_retries_and_keeps_its_bytes(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_bytes(b"old\n")
    attempts = []

    def held(source, target, **kwargs):
        attempts.append(1)
        raise _Sharing(13, "in use")

    monkeypatch.setattr(mutation_tools, "_swap_in", held)
    monkeypatch.setattr(mutation_tools.time, "sleep", lambda seconds: None)
    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "a.py")

    assert len(attempts) == 4 and failed.value.step == "replace" and failed.value.no_effect is True
    assert (tmp_path / "a.py").read_bytes() == b"old\n" and _names(tmp_path) == ["a.py"]


def test_another_permission_error_on_replace_is_not_retried(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_bytes(b"old\n")
    attempts = []

    def denied(source, target, **kwargs):
        attempts.append(1)
        raise PermissionError(13, "denied")

    monkeypatch.setattr(mutation_tools, "_swap_in", denied)
    with pytest.raises(WriteFailed):
        _write(tmp_path / "a.py")
    assert len(attempts) == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file open semantics")
def test_a_target_open_without_delete_sharing_fails_honestly_on_windows(tmp_path, monkeypatch):
    # the accepted regression: today's in-place write would have succeeded; now the write fails and the file keeps its bytes
    (tmp_path / "a.py").write_bytes(b"old\n")
    monkeypatch.setattr(mutation_tools.time, "sleep", lambda seconds: None)
    with open(tmp_path / "a.py", "rb"), pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "a.py")
    assert failed.value.step == "replace"
    assert (tmp_path / "a.py").read_bytes() == b"old\n" and _names(tmp_path) == ["a.py"]


def test_a_target_this_process_may_not_write_is_refused_before_staging(tmp_path, monkeypatch):
    # stand-in on every platform for a read-only file or an ACL that denies writing data: the write-open probe is refused
    target = tmp_path / "a.py"
    target.write_bytes(b"old\n")
    real_open, opened = os.open, []

    def denied_for_the_target(path, flags, *args, **kwargs):
        opened.append((Path(path).name, flags & os.O_CREAT))
        if Path(path) == target:
            raise PermissionError(13, "write access denied")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", denied_for_the_target)
    with pytest.raises(WriteFailed) as failed:
        _write(target)
    assert failed.value.step == "refused" and failed.value.no_effect is True
    assert opened == [("a.py", 0)]  # the probe never creates or truncates, and nothing was staged
    assert target.read_bytes() == b"old\n" and _names(tmp_path) == ["a.py"]


def test_a_read_only_file_is_refused_unchanged(tmp_path):
    if sys.platform != "win32" and os.geteuid() == 0:
        pytest.skip("root may write a read-only file; the stand-in above covers the refusal")
    target = tmp_path / "a.py"
    target.write_bytes(b"old\n")
    os.chmod(target, stat.S_IREAD)
    try:
        with pytest.raises(WriteFailed) as failed:
            _write(target)
        assert failed.value.step == "refused"
        assert target.read_bytes() == b"old\n" and _names(tmp_path) == ["a.py"]
    finally:
        os.chmod(target, stat.S_IREAD | stat.S_IWRITE)


def test_a_hidden_or_system_file_is_refused_unchanged(tmp_path, monkeypatch):
    # stand-in on every platform: the file reports the hidden attribute, as Windows does
    target = tmp_path / "a.py"
    target.write_bytes(b"old\n")
    real_stat = os.stat

    class _Hidden:
        def __init__(self, facts):
            self._facts = facts
            self.st_file_attributes = 0x2

        def __getattr__(self, name):
            return getattr(self._facts, name)

    monkeypatch.setattr(os, "stat", lambda path, *a, **k: _Hidden(real_stat(path, *a, **k)) if Path(path) == target else real_stat(path, *a, **k))
    with pytest.raises(WriteFailed) as failed:
        _write(target)
    assert failed.value.step == "refused" and target.read_bytes() == b"old\n"


@pytest.mark.skipif(sys.platform != "win32", reason="the hidden attribute is Windows'")
def test_a_hidden_file_is_refused_unchanged_on_windows(tmp_path):
    import ctypes

    target = tmp_path / "h.py"
    target.write_bytes(b"old\n")
    ctypes.windll.kernel32.SetFileAttributesW(str(target), 0x2)
    with pytest.raises(WriteFailed) as failed:
        _write(target)
    assert failed.value.step == "refused" and target.read_bytes() == b"old\n"
    assert os.stat(target).st_file_attributes & 0x2  # still hidden


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_the_target_mode_is_kept_and_the_staging_file_is_never_wider(tmp_path, monkeypatch):
    target = tmp_path / "run.sh"
    target.write_bytes(b"old\n")
    os.chmod(target, 0o750)
    seen, created_with = [], []
    real, real_open = mutation_tools._swap_in, os.open

    def look(source, destination, **kwargs):
        seen.append(stat.S_IMODE(os.stat(source).st_mode))
        real(source, destination, **kwargs)

    def note_mode(path, flags, mode=0o777, *args, **kwargs):
        if flags & os.O_CREAT:
            created_with.append(mode)
        return real_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(mutation_tools, "_swap_in", look)
    monkeypatch.setattr(os, "open", note_mode)
    _write(target)
    assert created_with == [0o750]  # never wider than the target, from the moment it exists
    assert seen == [0o750] and stat.S_IMODE(os.stat(target).st_mode) == 0o750


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_a_new_file_gets_the_mode_write_text_gave(tmp_path):
    umask = os.umask(0o022)
    os.umask(umask)
    _write(tmp_path / "new.py")
    assert stat.S_IMODE(os.stat(tmp_path / "new.py").st_mode) == 0o666 & ~umask


def test_a_write_through_a_file_link_changes_the_real_file_and_keeps_the_link(tmp_path):
    real, link = tmp_path / "real.py", tmp_path / "link.py"
    real.write_bytes(b"old\n")
    try:
        os.symlink(real, link)
    except OSError:
        pytest.skip("this host cannot create a file symlink (Windows without the privilege)")
    _write(link)
    assert link.is_symlink() and real.read_bytes() == b"new\n" and _names(tmp_path) == ["link.py", "real.py"]


def test_the_staging_name_rule_refuses_only_the_exact_shape(tmp_path):
    policy = FilePolicy(tmp_path)
    assert policy.path_denial(LEFTOVER) == "deny.staging_file"
    assert policy.path_denial(f"src/deep/{staging_name()}") == "deny.staging_file"
    for name in (".optimus-write-xyz.tmp", ".optimus-writer.txt", "optimus-write-0123456789abcdef.tmp", f"{LEFTOVER}.bak", ".optimus-write-0123456789abcde.tmp"):
        assert policy.path_denial(name) is None, name


def test_a_leftover_staging_file_is_never_indexed_listed_or_attached(tmp_path):
    from optimus.agent.workspace_context import WorkspaceReferenceStatus, resolve_task_references

    for folder in ("a", "b"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / LEFTOVER).write_text("half a write\n")
    (tmp_path / "a" / "kept.py").write_text("kept\n")
    policy = FilePolicy(tmp_path)

    listed, _unlisted = policy.names()
    assert listed == ("a/kept.py",)  # not listed, so never indexed or offered as a candidate
    decisions = {d.relative_path: d for d in policy.walk(purpose=FilePurpose.AUTOMATIC)}
    assert not decisions[f"a/{LEFTOVER}"].allowed and decisions[f"a/{LEFTOVER}"].reason == "deny.staging_file"
    [found] = resolve_task_references(f"Explain {LEFTOVER}", policy, listed)
    assert found.status is WorkspaceReferenceStatus.NOT_READABLE and found.status is not WorkspaceReferenceStatus.AMBIGUOUS


async def test_a_leftover_is_never_sent_to_the_model_in_an_agent_turn(tmp_path):
    from tests.unit.agent.test_directive_path_characters import _drive, _SamePlan

    (tmp_path / LEFTOVER).write_text("half a write" + chr(10))
    (tmp_path / "small.py").write_text("kept_marker = 1" + chr(10))
    gateway = _SamePlan("WRITE small.py" + chr(10) + "kept_marker = 2" + chr(10))

    result, _outbound, _runner, _records = await _drive(tmp_path, gateway)

    assert result["stopReason"] == "end_turn" and (tmp_path / LEFTOVER).read_text() == "half a write" + chr(10)
    assert gateway.calls and all("half a write" not in sent for sent in gateway.calls)
    assert any("kept_marker" in sent for sent in gateway.calls)


@pytest.mark.parametrize("mode", ["chat"])
async def test_a_leftover_is_never_sent_to_the_model_even_when_named(mode, tmp_path, monkeypatch):
    from tests.unit.acp import test_workspace_name_markdown as module
    from tests.unit.agent.test_directive_path_characters import _RealRunner

    gateways = []
    monkeypatch.setattr(module, "_RealRunner", lambda gateway: gateways.append(gateway) or _RealRunner(gateway))
    (tmp_path / LEFTOVER).write_text("half a write" + chr(10))
    (tmp_path / "kept.py").write_text("kept_marker = 1" + chr(10))

    await module._prompt(tmp_path, f"Explain {LEFTOVER} and kept.py", mode)

    [gateway] = gateways
    assert gateway.calls and all("half a write" not in sent for sent in gateway.calls)
    assert any("kept_marker" in sent for sent in gateway.calls)  # an ordinary file next to it is still attached


def test_a_replace_that_renamed_and_then_reported_an_error_is_an_effect(tmp_path, monkeypatch):
    # Codex r1 M6: an NFS rename can complete and still return an error; the staging file is gone, so nothing proves no effect
    (tmp_path / "a.py").write_bytes(b"old\n")
    real = mutation_tools._swap_in

    def renamed_then_failed(source, target, **kwargs):
        real(source, target, **kwargs)
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(mutation_tools, "_swap_in", renamed_then_failed)
    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "a.py")
    assert failed.value.no_effect is False and failed.value.step == "replace, then cleanup"


def test_a_target_that_resolves_elsewhere_before_the_replace_is_not_replaced(tmp_path, monkeypatch):
    # Codex r1 H1: a folder on the way swapped after the guard judged the target; the replace is not attempted
    (tmp_path / "a.py").write_bytes(b"old\n")
    real_resolve, calls = mutation_tools.resolve_target, []

    def moved_on_second_look(path):
        calls.append(path)
        resolved = real_resolve(path)
        return resolved if len(calls) == 1 or resolved is None else resolved.with_name("elsewhere.py")

    monkeypatch.setattr(mutation_tools, "resolve_target", moved_on_second_look)
    replaced = []
    monkeypatch.setattr(mutation_tools, "_swap_in", lambda *args, **kwargs: replaced.append(args))
    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "a.py")
    # Codex r3 #7 narrowing: the redirect is caught by the check before staging, so nothing was ever created
    assert replaced == [] and failed.value.step == "stage" and failed.value.no_effect is True
    assert (tmp_path / "a.py").read_bytes() == b"old\n" and _names(tmp_path) == ["a.py"]


def test_an_edit_whose_base_changes_while_it_is_staged_writes_nothing(tmp_path, monkeypatch):
    # Codex r1 M3: an editor saves during the fsync; the base is checked again just before the replace
    import hashlib

    from optimus.tools.mutation_tools import WriteSourceChanged

    target = tmp_path / "e.py"
    target.write_bytes(b"a = 1\n")
    base = hashlib.sha256(b"a = 1\n").hexdigest()
    real_fsync = os.fsync

    def saved_meanwhile(descriptor):
        real_fsync(descriptor)
        target.write_bytes(b"a = 1\nb = 2\n")  # the user's newer save

    monkeypatch.setattr(os, "fsync", saved_meanwhile)
    with pytest.raises(WriteSourceChanged):
        write_file(target, "a = 2\n", context=_context(), guard=_Allow(), expected_sha256=base)
    assert target.read_bytes() == b"a = 1\nb = 2\n" and _names(tmp_path) == ["e.py"]


@pytest.mark.parametrize("newline", ["|", "\n\n", "x"])
def test_an_illegal_newline_value_is_refused_as_write_text_did(newline, tmp_path):
    with pytest.raises(ValueError):
        write_file(tmp_path / "e.py", "a\n", context=_context(), guard=_Allow(), newline=newline)
    assert _names(tmp_path) == []


def test_a_carriage_return_newline_is_translated_as_write_text_did(tmp_path):
    write_file(tmp_path / "e.py", "a\nb\n", context=_context(), guard=_Allow(), newline="\r")
    assert (tmp_path / "e.py").read_bytes() == b"a\rb\r"


@pytest.mark.parametrize("requested", [LEFTOVER, f"src/{LEFTOVER}"])
def test_the_read_and_write_guard_refuses_a_leftover_by_name(requested, tmp_path):
    # Codex r1 H2: the direct guard, not only discovery, refuses the staging name, so a READ_MORE or WRITE cannot reach it
    from optimus.guardrails.path_safety import PathSafetyValidator
    from optimus.guardrails.validation import ValidationVerdict

    (tmp_path / "src").mkdir()
    (tmp_path / requested).write_text("half a write" + chr(10))
    validator = PathSafetyValidator(workspace_root=tmp_path)
    target = (tmp_path / requested).resolve()

    assert validator.validate_read(target, requested_relative_path=requested).verdict is ValidationVerdict.BLOCK
    assert validator.validate_write(target, requested_relative_path=requested).verdict is ValidationVerdict.BLOCK


def test_the_guard_refuses_a_link_whose_target_is_a_leftover(tmp_path):
    from optimus.guardrails.path_safety import PathSafetyValidator
    from optimus.guardrails.validation import ValidationVerdict

    (tmp_path / LEFTOVER).write_text("half a write" + chr(10))
    try:
        os.symlink(tmp_path / LEFTOVER, tmp_path / "innocent.py")
    except OSError:
        pytest.skip("this host cannot create a file symlink (Windows without the privilege)")
    validator = PathSafetyValidator(workspace_root=tmp_path)
    verdict = validator.validate_read((tmp_path / "innocent.py").resolve(), requested_relative_path="innocent.py").verdict
    assert verdict is ValidationVerdict.BLOCK


async def test_a_staging_file_left_behind_is_recorded_as_an_unknown_effect(tmp_path, monkeypatch):
    # through session/prompt: the replace fails and the staging file cannot be removed, so the record is INDETERMINATE
    from optimus.acp.settlement import EffectState
    from tests.unit.agent.test_directive_path_characters import _drive, _SamePlan

    (tmp_path / "a.py").write_bytes(b"old\n")

    def refused(*args, **kwargs):
        raise PermissionError(13, "denied")

    def stuck(self, missing_ok=False):
        raise PermissionError(13, "in use")

    monkeypatch.setattr(mutation_tools, "_swap_in", refused)
    monkeypatch.setattr(Path, "unlink", stuck)
    result, outbound, _runner, records = await _drive(tmp_path, _SamePlan("WRITE a.py" + chr(10) + "new" + chr(10)))

    assert result["_meta"]["runStopReason"] == "WRITE_DIRECTIVE_NOT_EXECUTED"
    assert (tmp_path / "a.py").read_bytes() == b"old\n"
    [record] = records.values()
    assert record.effect_state is EffectState.INDETERMINATE
    # the shown text and the history both follow that record: never "was not applied" for an unknown effect
    from tests.unit.agent.test_write_new_folders import _final_text

    for text in (_final_text(outbound), record.completion_text):
        assert text.startswith(UNCONFIRMED) and "was not applied" not in text


def test_the_target_is_resolved_once_after_the_guard_and_never_adopted_later(tmp_path, monkeypatch):
    # Codex r2 H1: a redirect after the guard's decision is never adopted; nothing is staged or written in the new place
    (tmp_path / "a.py").write_bytes(b"old\n")
    (tmp_path / "other").mkdir()
    real_resolve, calls = mutation_tools.resolve_target, []

    def redirected_after_the_first_look(path):
        calls.append(path)
        resolved = real_resolve(path)
        if len(calls) == 1 or resolved is None or resolved.name != "a.py":
            return resolved
        return tmp_path / "other" / "a.py"

    monkeypatch.setattr(mutation_tools, "resolve_target", redirected_after_the_first_look)
    with pytest.raises(WriteFailed):
        _write(tmp_path / "a.py")
    assert _names(tmp_path / "other") == [] and (tmp_path / "a.py").read_bytes() == b"old\n" and _names(tmp_path) == ["a.py", "other"]


def _held_once_then(monkeypatch, during_wait):
    real, attempts = mutation_tools._swap_in, []

    def held_once(source, target, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise _Sharing(13, "in use")
        real(source, target, **kwargs)

    monkeypatch.setattr(mutation_tools, "_swap_in", held_once)
    monkeypatch.setattr(mutation_tools.time, "sleep", lambda seconds: during_wait())
    return attempts


def test_an_edit_base_that_changes_during_a_retry_wait_writes_nothing(tmp_path, monkeypatch):
    import hashlib

    from optimus.tools.mutation_tools import WriteSourceChanged

    target = tmp_path / "e.py"
    target.write_bytes(b"a = 1\n")
    attempts = _held_once_then(monkeypatch, lambda: target.write_bytes(b"a = 1\nsaved meanwhile\n"))
    with pytest.raises(WriteSourceChanged):
        write_file(target, "a = 2\n", context=_context(), guard=_Allow(), expected_sha256=hashlib.sha256(b"a = 1\n").hexdigest())
    assert attempts == [1] and target.read_bytes() == b"a = 1\nsaved meanwhile\n" and _names(tmp_path) == ["e.py"]


def test_a_target_redirected_during_a_retry_wait_is_not_replaced(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_bytes(b"old\n")
    moved = []
    real_resolve = mutation_tools.resolve_target
    monkeypatch.setattr(mutation_tools, "resolve_target", lambda p: (tmp_path / "x.py") if moved else real_resolve(p))
    attempts = _held_once_then(monkeypatch, lambda: moved.append(1))
    with pytest.raises(WriteFailed):
        _write(tmp_path / "a.py")
    assert attempts == [1] and (tmp_path / "a.py").read_bytes() == b"old\n" and _names(tmp_path) == ["a.py"]


def test_the_write_probe_neither_creates_nor_truncates_and_keeps_the_real_cause(tmp_path, monkeypatch):
    target = tmp_path / "a.py"
    target.write_bytes(b"old\n")
    real_open, probes = os.open, []

    def note(path, flags, *args, **kwargs):
        if Path(path) == target:
            probes.append(flags)
            raise PermissionError(13, "write access denied")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", note)
    with pytest.raises(WriteFailed) as failed:
        _write(target)
    [flags] = probes
    assert flags & (os.O_CREAT | os.O_TRUNC | os.O_APPEND) == 0 and flags & os.O_WRONLY
    assert isinstance(failed.value.__cause__, PermissionError) and failed.value.errno == 13  # Codex r2 L7


def test_a_target_that_is_not_a_regular_file_is_refused_without_being_opened(tmp_path, monkeypatch):
    # Codex r2 M3, stand-in everywhere for a FIFO: opening one for writing could block or signal its reader
    target = tmp_path / "pipe"
    target.write_bytes(b"")
    real_stat, opened = os.stat, []

    class _Fifo:
        def __init__(self, facts):
            self._facts = facts
            self.st_mode = stat.S_IFIFO | 0o644

        def __getattr__(self, name):
            return getattr(self._facts, name)

    monkeypatch.setattr(os, "stat", lambda path, *a, **k: _Fifo(real_stat(path, *a, **k)) if Path(path) == target else real_stat(path, *a, **k))
    real_open = os.open
    monkeypatch.setattr(os, "open", lambda path, *a, **k: opened.append(path) or real_open(path, *a, **k))
    with pytest.raises(WriteFailed) as failed:
        _write(target)
    assert failed.value.step == "refused" and opened == []


def test_a_stale_edit_whose_staging_file_stays_is_settled_as_an_unknown_effect(tmp_path, monkeypatch):
    # Codex r2 M4: the WriteFailed's own account wins over its WriteSourceChanged cause
    import hashlib

    from optimus.agent.runner import _failure_terminal

    target = tmp_path / "e.py"
    target.write_bytes(b"a = 1\n")
    real_fsync = os.fsync

    def saved_meanwhile(descriptor):
        real_fsync(descriptor)
        target.write_bytes(b"a = 1\nb = 2\n")

    def stuck(self, missing_ok=False):
        raise PermissionError(13, "in use")

    monkeypatch.setattr(os, "fsync", saved_meanwhile)
    monkeypatch.setattr(Path, "unlink", stuck)
    with pytest.raises(WriteFailed) as failed:
        write_file(target, "a = 2\n", context=_context(), guard=_Allow(), expected_sha256=hashlib.sha256(b"a = 1\n").hexdigest())
    assert failed.value.no_effect is False and _failure_terminal(failed.value) == "failed_effect_unknown"


def test_a_case_variant_of_a_leftover_is_refused_too(tmp_path):
    # Codex r2 H2: APFS and NTFS open the same file for any casing, so the predicate casefolds on every platform
    from optimus.guardrails.path_safety import PathSafetyValidator
    from optimus.guardrails.runtime_tree import is_staging_name
    from optimus.guardrails.validation import ValidationVerdict

    variant = LEFTOVER.upper()
    assert is_staging_name(variant) and FilePolicy(tmp_path).path_denial(variant) == "deny.staging_file"
    verdict = PathSafetyValidator(workspace_root=tmp_path).validate_read(tmp_path / variant, requested_relative_path=variant).verdict
    assert verdict is ValidationVerdict.BLOCK


UNCONFIRMED = "Optimus could not confirm whether the file change in the approved plan was applied."


@pytest.mark.parametrize(("effect", "starts"), [("NONE", "The file change in the approved plan was not applied."), ("INDETERMINATE", UNCONFIRMED)])
def test_the_not_executed_text_follows_the_recorded_effect(effect, starts):
    # orchestrator ruling on Codex r2 M5: no effect never shows the uncertain text, unknown never shows "was not applied"
    from optimus.acp.settlement import EffectState
    from optimus.acp.spec import _completion_message
    from optimus.agent.models import AgentRunResult, AgentRunStatus, ExecutionMode

    result = AgentRunResult(run_id="r", session_id="s", execution_mode=ExecutionMode.AGENT, status=AgentRunStatus.FAILED,
                            final_state="FAILED", output_text="WRITE a.py\nx", stop_reason="WRITE_DIRECTIVE_NOT_EXECUTED")
    text = _completion_message(result, effect=EffectState[effect])
    assert text.startswith(starts) and (effect == "NONE") == ("was not applied" in text)


def test_a_failed_folder_is_no_effect_once_the_rollback_removed_it(tmp_path, monkeypatch):
    def refuse(self, *args, **kwargs):
        raise OSError(36, "File name too long")

    monkeypatch.setattr(Path, "mkdir", refuse)
    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "deep" / "a.py", root=tmp_path)
    assert failed.value.step == "folders" and failed.value.no_effect is True


def _with_streams(target: Path) -> None:
    target.write_bytes(b"old\r\n")
    Path(f"{target}:Zone.Identifier").write_bytes(b"[ZoneTransfer]\r\nZoneId=3\r\n")
    Path(f"{target}:custom").write_bytes(b"custom stream")


def _streams(target: Path) -> tuple[bytes, bytes]:
    return Path(f"{target}:Zone.Identifier").read_bytes(), Path(f"{target}:custom").read_bytes()


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS named streams")
def test_a_write_keeps_the_mark_of_the_web_and_other_named_streams_on_windows(tmp_path):
    target = tmp_path / "downloaded.py"
    _with_streams(target)
    _write(target, "new\n")
    assert target.read_bytes() == b"new\r\n" and _streams(target) == (b"[ZoneTransfer]\r\nZoneId=3\r\n", b"custom stream")
    assert _names(tmp_path) == ["downloaded.py"]


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS named streams")
def test_an_edit_keeps_the_mark_of_the_web_and_other_named_streams_on_windows(tmp_path):
    import hashlib

    target = tmp_path / "downloaded.py"
    _with_streams(target)
    write_file(target, "a = 2\r\n", context=_context(), guard=_Allow(), expected_sha256=hashlib.sha256(b"old\r\n").hexdigest())
    assert target.read_bytes() == b"a = 2\r\n" and _streams(target)[0].startswith(b"[ZoneTransfer]")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file ACLs")
def test_a_write_keeps_an_explicit_acl_entry_on_windows(tmp_path):
    import subprocess

    target = tmp_path / "acl.py"
    target.write_bytes(b"old\n")
    subprocess.run(["icacls", str(target), "/grant", "*S-1-5-32-545:(R)"], capture_output=True, check=True)
    _write(target, "new\n")
    listed = subprocess.run(["icacls", str(target)], capture_output=True, text=True, check=True).stdout
    assert "BUILTIN" + chr(92) + "Users:(R)" in listed or "S-1-5-32-545" in listed


def test_an_existing_target_is_published_through_the_platform_swap(tmp_path, monkeypatch):
    # stand-in everywhere: the publish step is told whether the target existed (ReplaceFileW on Windows, os.replace otherwise)
    seen = []
    real = mutation_tools._swap_in
    monkeypatch.setattr(mutation_tools, "_swap_in", lambda s, t, **kwargs: seen.append(kwargs["existed"]) or real(s, t, **kwargs))
    (tmp_path / "old.py").write_bytes(b"old\n")
    _write(tmp_path / "old.py")
    _write(tmp_path / "new.py")
    assert seen == [True, False]


def _displaced(code: int, *, then=None):
    def replace_file_w(target, staging):  # what ReplaceFileW leaves for 1176 or 1177 when it gives no backup file
        os.remove(target)
        if then is not None:
            then(target)
        return code

    return replace_file_w


@pytest.mark.skipif(sys.platform != "win32", reason="ReplaceFileW is Windows'")
def test_replacefile_1176_puts_the_new_bytes_in_place_but_never_claims_success(tmp_path, monkeypatch):
    # Codex r3 #2: the original is gone and whether its streams came along is unknown, so the outcome stays unconfirmed
    monkeypatch.setattr(mutation_tools, "_replace_file_w", _displaced(1176))
    (tmp_path / "a.py").write_bytes(b"old\n")
    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "a.py")
    assert failed.value.no_effect is False and failed.value.step == "replace, unconfirmed"
    assert (tmp_path / "a.py").read_bytes() == b"new\n" and _names(tmp_path) == ["a.py"]


@pytest.mark.skipif(sys.platform != "win32", reason="ReplaceFileW is Windows'")
def test_replacefile_1176_never_overwrites_a_file_that_arrived_meanwhile(tmp_path, monkeypatch):
    # Codex r3 #2: a sync client restores the name between ReplaceFileW and the recovery; the recovery does not overwrite it
    monkeypatch.setattr(mutation_tools, "_replace_file_w", _displaced(1176, then=lambda target: Path(target).write_bytes(b"synced\n")))
    (tmp_path / "a.py").write_bytes(b"old\n")
    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "a.py")
    assert failed.value.no_effect is False
    assert (tmp_path / "a.py").read_bytes() == b"synced\n"
    [kept] = [name for name in _names(tmp_path) if name != "a.py"]
    assert (tmp_path / kept).read_bytes() == b"new\n"  # the new bytes survive under the staging name, never deleted


@pytest.mark.skipif(sys.platform != "win32", reason="ReplaceFileW is Windows'")
def test_replacefile_1177_keeps_the_staging_file_and_is_unconfirmed(tmp_path, monkeypatch):
    # Codex r3 #1: the staging file kept its name while the original moved away; it is never deleted
    monkeypatch.setattr(mutation_tools, "_replace_file_w", _displaced(1177))
    (tmp_path / "a.py").write_bytes(b"old\n")
    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "a.py")
    assert failed.value.no_effect is False and failed.value.step == "replace, unconfirmed"
    [kept] = _names(tmp_path)
    assert (tmp_path / kept).read_bytes() == b"new\n"


@pytest.mark.skipif(sys.platform != "win32", reason="ReplaceFileW is Windows'")
async def test_replacefile_1177_shows_the_unconfirmed_text_and_records_an_unknown_effect(tmp_path, monkeypatch):
    from optimus.acp.settlement import EffectState
    from tests.unit.agent.test_directive_path_characters import _drive, _SamePlan
    from tests.unit.agent.test_write_new_folders import _final_text

    monkeypatch.setattr(mutation_tools, "_replace_file_w", _displaced(1177))
    (tmp_path / "a.py").write_bytes(b"old\n")
    result, outbound, _runner, records = await _drive(tmp_path, _SamePlan("WRITE a.py" + chr(10) + "new" + chr(10)))
    [record] = records.values()
    assert result["_meta"]["runStopReason"] == "WRITE_DIRECTIVE_NOT_EXECUTED" and record.effect_state is EffectState.INDETERMINATE
    assert _final_text(outbound).startswith(UNCONFIRMED) and record.completion_text.startswith(UNCONFIRMED)


def test_a_retry_restages_clean_bytes_before_trying_again(tmp_path, monkeypatch):
    # Codex r3 #4: a failed ReplaceFileW may have merged the target's metadata into the staging file; the retry gets a new one
    (tmp_path / "a.py").write_bytes(b"old\n")
    real, stagings = mutation_tools._swap_in, []

    def held_once_after_touching_the_stage(source, target, **kwargs):
        stagings.append((os.stat(source).st_ino, source.read_bytes()))
        if len(stagings) == 1:
            source.write_bytes(b"merged metadata")  # what a partial merge could leave
            raise _Sharing(13, "in use")
        real(source, target, **kwargs)

    monkeypatch.setattr(mutation_tools, "_swap_in", held_once_after_touching_the_stage)
    monkeypatch.setattr(mutation_tools.time, "sleep", lambda seconds: None)
    _write(tmp_path / "a.py")
    assert [data for _ino, data in stagings] == [b"new\n", b"new\n"]
    assert (tmp_path / "a.py").read_bytes() == b"new\n" and _names(tmp_path) == ["a.py"]


@pytest.mark.parametrize("writer", ["write", "edit"])
def test_a_read_that_fails_before_staging_is_no_effect(writer, tmp_path, monkeypatch):
    # Codex r3 #5: an editor's sharing lock on the first read; nothing was created, so the record is not "unknown"
    import hashlib

    target = tmp_path / "a.py"
    target.write_bytes(b"old\n")

    def locked(self):
        raise PermissionError(13, "locked")

    monkeypatch.setattr(Path, "read_bytes", locked)
    with pytest.raises(WriteFailed) as failed:
        if writer == "write":
            _write(target)
        else:
            write_file(target, "x\n", context=_context(), guard=_Allow(), expected_sha256=hashlib.sha256(b"old\n").hexdigest())
    assert failed.value.step == "read" and failed.value.no_effect is True


def test_a_folder_whose_removal_cannot_be_proven_is_an_effect(tmp_path, monkeypatch):
    # Codex r3 #6: rmdir fails on a dropped share; an inaccessible folder is never counted as gone
    real_mkdir = Path.mkdir

    def second_fails(self, *args, **kwargs):
        if self.name == "inner":
            raise OSError(64, "The specified network name is no longer available")
        return real_mkdir(self, *args, **kwargs)

    def unreachable(self):
        raise OSError(64, "The specified network name is no longer available")

    monkeypatch.setattr(Path, "mkdir", second_fails)
    monkeypatch.setattr(Path, "rmdir", unreachable)
    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "outer" / "inner" / "a.py", root=tmp_path)
    assert failed.value.step == "folders" and failed.value.no_effect is False


def test_a_mkdir_that_failed_but_left_a_folder_is_an_effect(tmp_path, monkeypatch):
    # Codex r3 #6: the mkdir completed on the server but its reply was lost; the folder exists although mkdir raised
    real_mkdir = Path.mkdir

    def made_then_failed(self, *args, **kwargs):
        real_mkdir(self, *args, **kwargs)
        raise OSError(121, "The semaphore timeout period has expired")

    monkeypatch.setattr(Path, "mkdir", made_then_failed)
    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "deep" / "a.py", root=tmp_path)
    assert failed.value.no_effect is False


@pytest.mark.skipif(sys.platform != "win32", reason="ReplaceFileW is Windows'")
@pytest.mark.parametrize("code", [1175, 87])
def test_other_replacefile_failures_leave_the_target_and_remove_the_staging_file(code, tmp_path, monkeypatch):
    monkeypatch.setattr(mutation_tools, "_replace_file_w", lambda target, staging: code)
    (tmp_path / "a.py").write_bytes(b"old\n")
    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "a.py")
    assert failed.value.no_effect is True and (tmp_path / "a.py").read_bytes() == b"old\n" and _names(tmp_path) == ["a.py"]
