from __future__ import annotations

from pathlib import Path

from optimus.guardrails.validation import ValidationResult, ValidationVerdict


class PathSafetyValidator:
    def __init__(self, *, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()

    def validate_read(self, path: str | Path) -> ValidationResult:
        candidate = Path(path)
        if _is_secret_path(candidate):
            return ValidationResult(ValidationVerdict.BLOCK, "path.secret.read", "secret path reads are denied")
        if not self._inside_workspace(candidate):
            return ValidationResult(ValidationVerdict.HOLD, "path.read.outside_workspace", "read outside workspace requires approval")
        return ValidationResult(ValidationVerdict.ALLOW, "path.read.allowed", "path read allowed")

    def validate_write(self, path: str | Path) -> ValidationResult:
        candidate = Path(path)
        if _is_secret_path(candidate):
            return ValidationResult(ValidationVerdict.BLOCK, "path.secret.write", "secret path writes are denied")
        if not self._inside_workspace(candidate):
            return ValidationResult(ValidationVerdict.BLOCK, "path.workspace_escape", "writes must stay inside workspace")
        return ValidationResult(ValidationVerdict.ALLOW, "path.write.allowed", "path write allowed")

    def validate_delete_pattern(self, pattern: str) -> ValidationResult:
        normalized = pattern.replace("\\", "/")
        if "**" in normalized or normalized.endswith("/*") or normalized.endswith("/"):
            return ValidationResult(ValidationVerdict.HOLD, "path.recursive_glob_delete", "recursive or broad delete requires approval")
        return ValidationResult(ValidationVerdict.ALLOW, "path.delete_pattern.allowed", "delete pattern allowed")

    def _inside_workspace(self, path: Path) -> bool:
        resolved = path.resolve(strict=False)
        try:
            resolved.relative_to(self._workspace_root)
        except ValueError:
            return False
        return True


def _is_secret_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    secret_names = {".env", ".pypirc", ".netrc", "id_rsa", "id_ed25519", "credentials", "token", "secrets"}
    if parts & secret_names:
        return True
    return any(part.endswith(".pem") or part.endswith(".key") for part in parts)
