from __future__ import annotations

import re
from pathlib import Path

from optimus.telemetry.redaction import redact_for_telemetry

_SUBJECT_SECRET_VALUE_PATTERN = re.compile(r"(?i)\b(token|password|secret|credential|api[_-]?key)(\s+)\S+")


def sanitize_workspace_text(text: str, *, workspace_root: str | Path | None) -> str:
    subject = text.replace("\\", "/")
    if workspace_root is not None:
        workspace_text = Path(workspace_root).resolve().as_posix().rstrip("/")
        subject = subject.replace(workspace_text, "<workspace>")
    subject = str(redact_for_telemetry(subject))
    return _SUBJECT_SECRET_VALUE_PATTERN.sub(r"\1\2**********", subject)
