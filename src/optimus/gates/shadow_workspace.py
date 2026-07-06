from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ShadowChangeKind(StrEnum):
    WRITE = "write"
    DELETE = "delete"


@dataclass(frozen=True)
class ShadowChange:
    relative_path: Path
    kind: ShadowChangeKind


@dataclass(frozen=True)
class ShadowPromotionPlan:
    workspace_root: Path
    shadow_root: Path
    changes: tuple[ShadowChange, ...]

    @property
    def changed_paths(self) -> tuple[Path, ...]:
        return tuple(change.relative_path for change in self.changes)


class ShadowWorkspace:
    def __init__(self, *, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.shadow_root = Path(self._temporary_directory.name) / self.workspace_root.name
        shutil.copytree(self.workspace_root, self.shadow_root, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
        self._baseline_digests = _file_digests_by_relative_path(self.shadow_root)

    def changes(self) -> tuple[ShadowChange, ...]:
        changes: list[ShadowChange] = []
        shadow_digests = _file_digests_by_relative_path(self.shadow_root)

        for relative in sorted(set(self._baseline_digests) | set(shadow_digests)):
            if relative in self._baseline_digests and relative not in shadow_digests:
                changes.append(ShadowChange(relative_path=relative, kind=ShadowChangeKind.DELETE))
            elif relative not in self._baseline_digests or shadow_digests[relative] != self._baseline_digests[relative]:
                changes.append(ShadowChange(relative_path=relative, kind=ShadowChangeKind.WRITE))
        return tuple(changes)

    def changed_paths(self) -> tuple[Path, ...]:
        return tuple(change.relative_path for change in self.changes())

    def promotion_plan(self) -> ShadowPromotionPlan:
        return ShadowPromotionPlan(
            workspace_root=self.workspace_root,
            shadow_root=self.shadow_root,
            changes=self.changes(),
        )

    def cleanup(self) -> None:
        self._temporary_directory.cleanup()


def promote_shadow_changes(plan: ShadowPromotionPlan, *, fail_after_promoted_paths: int | None = None) -> None:
    backups: list[tuple[Path, bytes | None]] = []
    promoted_count = 0
    try:
        for change in plan.changes:
            source = plan.shadow_root / change.relative_path
            target = plan.workspace_root / change.relative_path
            backups.append((target, target.read_bytes() if target.exists() else None))
            if change.kind is ShadowChangeKind.DELETE:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            promoted_count += 1
            if fail_after_promoted_paths is not None and promoted_count >= fail_after_promoted_paths:
                raise RuntimeError("simulated promotion failure")
    except Exception:
        _restore_backups(backups)
        raise


def _file_digests_by_relative_path(root: Path) -> dict[Path, str]:
    return {
        path.relative_to(root): _sha256_file(path)
        for path in root.rglob("*")
        if path.is_file()
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _restore_backups(backups: Iterable[tuple[Path, bytes | None]]) -> None:
    for target, content in reversed(tuple(backups)):
        if content is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(content)
