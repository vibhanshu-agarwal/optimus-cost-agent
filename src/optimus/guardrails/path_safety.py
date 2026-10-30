from __future__ import annotations

from pathlib import Path

from optimus.guardrails.runtime_tree import has_runtime_component, resolve_target, target_reserved
from optimus.guardrails.secret_paths import is_secret_path
from optimus.guardrails.validation import ValidationResult, ValidationVerdict


class PathSafetyValidator:
    def __init__(self, *, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()

    def validate_read(
        self, path: str | Path, *, requested_relative_path: str | None = None, target_unresolved: bool = False
    ) -> ValidationResult:
        """The secret rule comes first, on the requested path and its resolved target alike (#385); then an
        unresolvable target and the reserved runtime tree are hard denials (Plan 12.2 READ), inside or outside the
        workspace; then the unchanged outside-workspace HOLD."""
        candidate = Path(path)
        if _secret(candidate, requested_relative_path):
            return ValidationResult(ValidationVerdict.BLOCK, "path.secret.read", "secret path reads are denied")
        if target_unresolved:
            return ValidationResult(ValidationVerdict.BLOCK, "path.unresolved.read", "an unresolvable read target is denied")
        if self._runtime_reserved(candidate, requested_relative_path):
            return ValidationResult(ValidationVerdict.BLOCK, "path.runtime.read", "runtime tree reads are denied")
        if not self._inside_workspace(candidate):
            return ValidationResult(ValidationVerdict.HOLD, "path.read.outside_workspace", "read outside workspace requires approval")
        return ValidationResult(ValidationVerdict.ALLOW, "path.read.allowed", "path read allowed")

    def validate_write(
        self, path: str | Path, *, requested_relative_path: str | None = None, target_unresolved: bool = False
    ) -> ValidationResult:
        """In the same order as a read (Plan 12.2 W), ahead of the unchanged workspace-escape denial."""
        candidate = Path(path)
        if _secret(candidate, requested_relative_path):
            return ValidationResult(ValidationVerdict.BLOCK, "path.secret.write", "secret path writes are denied")
        if target_unresolved:
            return ValidationResult(ValidationVerdict.BLOCK, "path.unresolved.write", "an unresolvable write target is denied")
        if self._runtime_reserved(candidate, requested_relative_path):
            return ValidationResult(ValidationVerdict.BLOCK, "path.runtime.write", "runtime tree writes are denied")
        if not self._inside_workspace(candidate):
            return ValidationResult(ValidationVerdict.BLOCK, "path.workspace_escape", "writes must stay inside workspace")
        return ValidationResult(ValidationVerdict.ALLOW, "path.write.allowed", "path write allowed")

    def validate_delete_pattern(self, pattern: str) -> ValidationResult:
        normalized = pattern.replace("\\", "/")
        if "**" in normalized or normalized.endswith("/*") or normalized.endswith("/"):
            return ValidationResult(ValidationVerdict.HOLD, "path.recursive_glob_delete", "recursive or broad delete requires approval")
        return ValidationResult(ValidationVerdict.ALLOW, "path.delete_pattern.allowed", "delete pattern allowed")

    def _runtime_reserved(self, candidate: Path, requested_relative_path: str | None) -> bool:
        """Whether the lexical or the resolved identity lies in the reserved runtime tree. With request metadata (a
        guard call), the lexical identity is the model's requested workspace-relative path and ``candidate`` is the
        caller's resolved target. Without it (a direct call, such as a command token), a relative path is anchored at
        the workspace root, never at the process cwd, and an unresolvable path is judged lexically only."""
        root = self._workspace_root
        if requested_relative_path is not None:
            lexical = Path(requested_relative_path).parts
            target = candidate if candidate.is_absolute() else resolve_target(root / candidate)
        elif candidate.is_absolute():
            lexical = _relative_parts(candidate, root)
            target = resolve_target(candidate)
        else:
            lexical = candidate.parts
            target = resolve_target(root / candidate)
        if has_runtime_component(lexical):
            return True
        return target is not None and target_reserved(target, root)

    def _inside_workspace(self, path: Path) -> bool:
        resolved = path.resolve(strict=False)
        try:
            resolved.relative_to(self._workspace_root)
        except ValueError:
            return False
        return True


def _secret(candidate: Path, requested_relative_path: str | None) -> bool:
    return is_secret_path(str(candidate)) or (requested_relative_path is not None and is_secret_path(requested_relative_path))


def _relative_parts(path: Path, root: Path) -> tuple[str, ...]:
    try:
        return path.relative_to(root).parts
    except ValueError:
        return ()

