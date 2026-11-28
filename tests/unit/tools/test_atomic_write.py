"""#691: an approved WRITE or EDIT reaches disk through a staging file beside the resolved target and one atomic replace, so a
failure at any step leaves the target's original bytes and no staging file. Refusals today's in-place write made stay
refusals. Each platform-specific case has a stand-in that runs everywhere."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from optimus.guardrails.file_policy import FilePolicy, FilePurpose, staging_name
from optimus.guardrails.pre_tool import PreToolResult, PreToolVerdict
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


def _fail(monkeypatch, name: str, *, after_real: bool = False):
    real = {"open": os.open, "fsync": os.fsync, "chmod": os.chmod, "replace": os.replace}[name]

    def failing(*args, **kwargs):
        if after_real:
            real(*args, **kwargs)
        raise OSError(28, "No space left on device")

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
    real, attempts = os.replace, []

    def held_twice(source, target):
        attempts.append(1)
        if len(attempts) <= 2:
            raise _Sharing(13, "in use")
        real(source, target)

    monkeypatch.setattr(os, "replace", held_twice)
    monkeypatch.setattr(mutation_tools.time, "sleep", lambda seconds: None)
    _write(tmp_path / "a.py")

    assert len(attempts) == 3 and (tmp_path / "a.py").read_bytes() == b"new\n" and _names(tmp_path) == ["a.py"]


def test_a_target_held_open_for_good_fails_after_three_retries_and_keeps_its_bytes(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_bytes(b"old\n")
    attempts = []

    def held(source, target):
        attempts.append(1)
        raise _Sharing(13, "in use")

    monkeypatch.setattr(os, "replace", held)
    monkeypatch.setattr(mutation_tools.time, "sleep", lambda seconds: None)
    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "a.py")

    assert len(attempts) == 4 and failed.value.step == "replace" and failed.value.no_effect is True
    assert (tmp_path / "a.py").read_bytes() == b"old\n" and _names(tmp_path) == ["a.py"]


def test_another_permission_error_on_replace_is_not_retried(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_bytes(b"old\n")
    attempts = []

    def denied(source, target):
        attempts.append(1)
        raise PermissionError(13, "denied")

    monkeypatch.setattr(os, "replace", denied)
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
    # stand-in for a read-only file on every platform: os.access is what the refusal consults
    (tmp_path / "a.py").write_bytes(b"old\n")
    monkeypatch.setattr(os, "access", lambda path, mode: False)
    opened = []
    monkeypatch.setattr(os, "open", lambda *args, **kwargs: opened.append(args) or 0)

    with pytest.raises(WriteFailed) as failed:
        _write(tmp_path / "a.py")
    assert failed.value.step == "refused" and failed.value.no_effect is True and opened == []
    assert (tmp_path / "a.py").read_bytes() == b"old\n"


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
    seen = []
    real = os.replace

    def look(source, destination):
        seen.append(stat.S_IMODE(os.stat(source).st_mode))
        real(source, destination)

    monkeypatch.setattr(os, "replace", look)
    _write(target)
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
