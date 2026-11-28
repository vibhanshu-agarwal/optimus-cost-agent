"""#689: an approved WRITE whose folder does not exist creates the missing folders inside the workspace, after the guard
accepted the target, then writes the file. A folder or write that fails ends the turn with a stated stop reason, never an
exception out of the adapter, and the folders this write created are removed again."""

from __future__ import annotations

import os
import sys

import pytest

from optimus.acp.settlement import EffectState
from tests.unit.agent.test_directive_path_characters import _drive, _SamePlan

NOT_APPLIED = "The file change in the approved plan was not applied."


def _final_text(outbound) -> str:
    updates = [n["params"]["update"] for n in outbound.notifications if n["method"] == "session/update"]
    return [u["content"]["text"] for u in updates if u["sessionUpdate"] == "agent_message_chunk"][-1]


async def test_a_write_into_a_new_folder_creates_it_and_writes_the_approved_bytes(tmp_path):
    result, _outbound, _runner, _records = await _drive(tmp_path, _SamePlan("WRITE src/new_pkg/module.py\nVALUE = 1\n"))

    assert result["_meta"]["runStopReason"] is None and result["stopReason"] == "end_turn"
    assert (tmp_path / "src" / "new_pkg" / "module.py").read_bytes() == b"VALUE = 1\n"


async def test_nested_new_folders_are_all_created(tmp_path):
    (tmp_path / "src").mkdir()
    result, _outbound, _runner, _records = await _drive(tmp_path, _SamePlan("WRITE src/a/b/c/d.py\nX = 2\n"))

    assert result["stopReason"] == "end_turn"
    assert (tmp_path / "src" / "a" / "b" / "c" / "d.py").read_bytes() == b"X = 2\n"


async def test_a_file_where_a_folder_is_needed_stops_with_a_reason_and_leaves_no_folder(tmp_path):
    (tmp_path / "src").write_text("a file, not a folder\n")
    result, outbound, runner, records = await _drive(tmp_path, _SamePlan("WRITE src/new_pkg/module.py\nVALUE = 1\nTEST pytest -q\n"))

    assert result["_meta"]["runStopReason"] == "WRITE_DIRECTIVE_NOT_EXECUTED" and result["stopReason"] == "end_turn"
    assert (tmp_path / "src").read_text() == "a file, not a folder\n"
    assert runner.commands == []  # the plan's TESTs check a change that was not made
    assert _final_text(outbound).startswith(NOT_APPLIED)
    [record] = records.values()
    assert record.completion_text.startswith(NOT_APPLIED)


async def test_a_failed_write_after_new_folders_removes_only_the_folders_it_created(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "kept.py").write_text("kept\n")

    def refuse(self, *args, **kwargs):
        raise PermissionError(13, "denied")

    monkeypatch.setattr("pathlib.Path.write_text", refuse)
    result, outbound, _runner, _records = await _drive(tmp_path, _SamePlan("WRITE src/x/y/z.py\nZ = 3\n"))

    assert result["_meta"]["runStopReason"] == "WRITE_DIRECTIVE_NOT_EXECUTED"
    assert sorted(p.name for p in (tmp_path / "src").iterdir()) == ["kept.py"]
    assert _final_text(outbound).startswith(NOT_APPLIED)


async def test_a_write_that_fails_part_way_stops_with_a_reason_and_deletes_no_file(tmp_path, monkeypatch):
    real = __import__("pathlib").Path.write_text

    def disk_full(self, data, *args, **kwargs):
        real(self, data[:2], *args, **kwargs)
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("pathlib.Path.write_text", disk_full)
    result, _outbound, _runner, _records = await _drive(tmp_path, _SamePlan("WRITE new/deeper/z.py\nZ = 3\n"))

    assert result["_meta"]["runStopReason"] == "WRITE_DIRECTIVE_NOT_EXECUTED"
    # by then the file may be another writer's, so it is never deleted; its folder, no longer empty, stays with it
    assert (tmp_path / "new" / "deeper" / "z.py").read_text() == "Z "


async def test_a_created_folder_that_does_not_resolve_to_itself_is_an_effect_not_a_guard_refusal(tmp_path, monkeypatch):
    from optimus.tools import mutation_tools

    real = mutation_tools.resolve_target
    monkeypatch.setattr(mutation_tools, "resolve_target", lambda p: None if p.name == "raced" else real(p))
    result, _outbound, _runner, records = await _drive(tmp_path, _SamePlan("WRITE raced/z.py\nZ = 3\n"))

    # a folder was made before the check failed, so the WRITE did not end failed_no_effect as a guard refusal would
    assert result["_meta"]["runStopReason"] == "WRITE_DIRECTIVE_NOT_EXECUTED"
    assert not (tmp_path / "raced" / "z.py").exists()
    assert (tmp_path / "raced").is_dir()  # a folder that does not resolve to itself is not this write's to remove
    [record] = records.values()
    assert record.effect_state is EffectState.INDETERMINATE  # #700: the committed record, not only the stop code


async def test_a_second_folder_that_cannot_be_created_removes_the_first_one(tmp_path, monkeypatch):
    real = __import__("pathlib").Path.mkdir
    made: list[str] = []

    def second_fails(self, *args, **kwargs):
        made.append(self.name)
        if len(made) == 2:
            raise OSError(36, "File name too long")
        return real(self, *args, **kwargs)

    monkeypatch.setattr("pathlib.Path.mkdir", second_fails)
    result, outbound, runner, records = await _drive(tmp_path, _SamePlan("WRITE outer/inner/z.py\nZ = 3\nTEST pytest -q\n"))

    assert made == ["outer", "inner"]  # the first folder was made before the second failed
    assert result["_meta"]["runStopReason"] == "WRITE_DIRECTIVE_NOT_EXECUTED"
    assert not (tmp_path / "outer").exists()  # the rollback removed the folder this write made
    assert runner.commands == []
    assert _final_text(outbound).startswith(NOT_APPLIED)
    [record] = records.values()
    assert record.effect_state is EffectState.INDETERMINATE


async def test_a_folder_that_cannot_be_created_stops_with_a_reason(tmp_path, monkeypatch):
    def refuse(self, *args, **kwargs):
        raise OSError(36, "File name too long")

    monkeypatch.setattr("pathlib.Path.mkdir", refuse)
    result, outbound, _runner, _records = await _drive(tmp_path, _SamePlan("WRITE deep/module.py\nVALUE = 1\n"))

    assert result["_meta"]["runStopReason"] == "WRITE_DIRECTIVE_NOT_EXECUTED"
    assert not (tmp_path / "deep").exists()
    assert _final_text(outbound).startswith(NOT_APPLIED)


@pytest.mark.parametrize("folder", [".venv", "node_modules"])
async def test_a_new_folder_the_file_policy_refuses_is_never_created(folder, tmp_path):
    result, _outbound, runner, _records = await _drive(
        tmp_path, _SamePlan(f"WRITE {folder}/new_pkg/module.py\nVALUE = 1\nTEST pytest -q\n")
    )

    assert result["_meta"]["runStopReason"] == "WRITE_GUARD_REFUSED"
    assert list(tmp_path.iterdir()) == []
    assert runner.commands == []


async def test_a_parent_that_links_out_of_the_workspace_is_refused_and_nothing_is_created_outside(tmp_path):
    workspace, outside = tmp_path / "ws", tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    try:
        os.symlink(outside, workspace / "link", target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        if sys.platform != "win32":
            raise
        try:  # without the symlink privilege, a junction is the Windows link a workspace can hold
            import _winapi

            _winapi.CreateJunction(str(outside), str(workspace / "link"))
        except OSError:
            pytest.skip(f"this host can create neither a directory symlink nor a junction: {type(exc).__name__}")

    result, _outbound, runner, _records = await _drive(workspace, _SamePlan("WRITE link/new_pkg/module.py\nVALUE = 1\n"))

    assert result["_meta"]["runStopReason"] == "WRITE_GUARD_REFUSED"
    assert list(outside.iterdir()) == []
    assert runner.commands == []


async def test_a_write_over_a_file_that_is_not_utf8_stops_with_a_reason_and_leaves_its_bytes(tmp_path):
    original = bytes([0x63, 0x61, 0x66, 0xE9, 0x0A, 0xFF, 0x00, 0x0D, 0x0A])  # Latin-1 text and stray bytes: not UTF-8
    (tmp_path / "legacy.txt").write_bytes(original)
    result, outbound, runner, records = await _drive(tmp_path, _SamePlan("WRITE legacy.txt\nnew\nTEST pytest -q\n"))

    assert result["_meta"]["runStopReason"] == "WRITE_DIRECTIVE_NOT_EXECUTED" and result["stopReason"] == "end_turn"
    assert (tmp_path / "legacy.txt").read_bytes() == original  # no encoding guessed, nothing rewritten
    assert runner.commands == []
    assert _final_text(outbound).startswith(NOT_APPLIED)
    [record] = records.values()
    assert record.completion_text.startswith(NOT_APPLIED)


async def test_a_write_target_removed_before_its_read_stops_with_a_reason(tmp_path, monkeypatch):
    from optimus.agent.tools import AgentToolbox

    (tmp_path / "gone.py").write_text("old\n")
    real = AgentToolbox.read_file

    def removed_first(self, path, **kwargs):
        os.remove(path)  # another process removes it between the existence check and the read
        return real(self, path, **kwargs)

    monkeypatch.setattr(AgentToolbox, "read_file", removed_first)
    result, outbound, runner, _records = await _drive(tmp_path, _SamePlan("WRITE gone.py\nnew\nTEST pytest -q\n"))

    assert result["_meta"]["runStopReason"] == "WRITE_DIRECTIVE_NOT_EXECUTED"
    assert not (tmp_path / "gone.py").exists()  # the WRITE never ran after its read failed
    assert runner.commands == []
    assert _final_text(outbound).startswith(NOT_APPLIED)
