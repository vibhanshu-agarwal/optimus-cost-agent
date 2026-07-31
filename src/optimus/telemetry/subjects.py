from __future__ import annotations

from pathlib import Path

from optimus_security.sanitization import (
    WORKSPACE_SUBJECT_SANITIZATION_POLICY,
    sanitize_for_persistence,
)


def sanitize_workspace_text(text: str, *, workspace_root: str | Path | None) -> str:
    subject = text.replace("\\", "/")
    if workspace_root is not None:
        workspace_text = Path(workspace_root).resolve().as_posix().rstrip("/")
        subject = subject.replace(workspace_text, "<workspace>")
    return str(
        sanitize_for_persistence(
            subject,
            policy=WORKSPACE_SUBJECT_SANITIZATION_POLICY,
        ).value
    )
