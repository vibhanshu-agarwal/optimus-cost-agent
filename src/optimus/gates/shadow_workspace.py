from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ShadowPromotionPlan:
    workspace_root: Path
    shadow_root: Path
    changed_paths: tuple[Path, ...]


class ShadowWorkspace:
    def __init__(self, *, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.shadow_root = Path(self._temporary_directory.name) / self.workspace_root.name
        shutil.copytree(self.workspace_root, self.shadow_root, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))

    def changed_paths(self) -> tuple[Path, ...]:
        changed: list[Path] = []
        for shadow_path in self.shadow_root.rglob("*"):
            if not shadow_path.is_file():
                continue
            relative = shadow_path.relative_to(self.shadow_root)
            workspace_path = self.workspace_root / relative
            if not workspace_path.exists() or shadow_path.read_bytes() != workspace_path.read_bytes():
                changed.append(relative)
        return tuple(sorted(changed))

    def promotion_plan(self) -> ShadowPromotionPlan:
        return ShadowPromotionPlan(
            workspace_root=self.workspace_root,
            shadow_root=self.shadow_root,
            changed_paths=self.changed_paths(),
        )

    def cleanup(self) -> None:
        self._temporary_directory.cleanup()


def promote_shadow_changes(plan: ShadowPromotionPlan, *, fail_after_promoted_paths: int | None = None) -> None:
    backups: list[tuple[Path, bytes | None]] = []
    promoted_count = 0
    try:
        for relative in plan.changed_paths:
            source = plan.shadow_root / relative
            target = plan.workspace_root / relative
            backups.append((target, target.read_bytes() if target.exists() else None))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            promoted_count += 1
            if fail_after_promoted_paths is not None and promoted_count >= fail_after_promoted_paths:
                raise RuntimeError("simulated promotion failure")
    except Exception:
        _restore_backups(backups)
        raise


def _restore_backups(backups: Iterable[tuple[Path, bytes | None]]) -> None:
    for target, content in reversed(tuple(backups)):
        if content is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(content)
