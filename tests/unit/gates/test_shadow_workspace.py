"""#645: a failed promotion restores every file it can and keeps the original failure."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from optimus.gates import shadow_workspace as sw


class _PromotionBroke(RuntimeError):
    pass


def _plan(tmp_path: Path) -> sw.ShadowPromotionPlan:
    workspace = tmp_path / "workspace"
    shadow = tmp_path / "shadow"
    workspace.mkdir()
    shadow.mkdir()
    for name, body in (("a.txt", b"A0"), ("b.txt", b"B0"), ("c.txt", b"C0")):
        (workspace / name).write_bytes(body)
    for name, body in (("a.txt", b"A1"), ("b.txt", b"B1"), ("c.txt", b"C1")):
        (shadow / name).write_bytes(body)
    changes = tuple(
        sw.ShadowChange(relative_path=Path(name), kind=sw.ShadowChangeKind.WRITE)
        for name in ("a.txt", "b.txt", "c.txt")
    )
    return sw.ShadowPromotionPlan(workspace_root=workspace, shadow_root=shadow, changes=changes)


@pytest.mark.skipif(getattr(os, "geteuid", lambda: 1)() == 0, reason="root ignores the read-only bit")
def test_one_failed_restoration_does_not_stop_the_rest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _plan(tmp_path)
    real_apply = sw._apply_shadow_change
    locked = plan.workspace_root / "b.txt"

    def _apply(change: sw.ShadowChange, source: Path | None, target: Path) -> None:
        if change.relative_path == Path("c.txt"):
            raise _PromotionBroke("promotion broke")
        real_apply(change, source, target)
        if change.relative_path == Path("b.txt"):
            os.chmod(target, stat.S_IREAD)  # its restoration will now fail

    monkeypatch.setattr(sw, "_apply_shadow_change", _apply)
    try:
        with pytest.raises(_PromotionBroke) as raised:
            sw.promote_shadow_changes(plan)
    finally:
        os.chmod(locked, stat.S_IREAD | stat.S_IWRITE)

    assert str(raised.value) == "promotion broke"
    assert getattr(raised.value, "__notes__", []) == ["shadow_restore_incomplete: b.txt"]
    # Restoration runs in reverse: b.txt fails, and a.txt after it is still restored.
    assert locked.read_bytes() == b"B1"
    assert (plan.workspace_root / "a.txt").read_bytes() == b"A0"
    assert (plan.workspace_root / "c.txt").read_bytes() == b"C0"


def test_complete_restoration_adds_no_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _plan(tmp_path)
    real_apply = sw._apply_shadow_change

    def _apply(change: sw.ShadowChange, source: Path | None, target: Path) -> None:
        if change.relative_path == Path("c.txt"):
            raise _PromotionBroke("promotion broke")
        real_apply(change, source, target)

    monkeypatch.setattr(sw, "_apply_shadow_change", _apply)
    with pytest.raises(_PromotionBroke) as raised:
        sw.promote_shadow_changes(plan)
    assert getattr(raised.value, "__notes__", None) is None
    assert (plan.workspace_root / "a.txt").read_bytes() == b"A0"
    assert (plan.workspace_root / "b.txt").read_bytes() == b"B0"
