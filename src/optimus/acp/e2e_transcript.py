from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES

PLAN_9_6_E2E_TRANSCRIPT_PATH = Path("reports/plan-9-6-e2e-acp-transcript.json")

_FORBIDDEN_TRANSCRIPT_ROOT_KEYS = frozenset({"environ", "environment", "env", "process_env"})
_SENSITIVE_ENV_KEY_NAMES = frozenset(LOCAL_PROVIDER_KEY_NAMES) | {
    "OPTIMUS_API_KEY",
    "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY",
    "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET",
    "ANTHROPIC_API_KEY",
}


class E2eTranscriptSerializationError(ValueError):
    pass


@dataclass
class E2eAcpTranscriptWriter:
    lines: list[dict[str, Any]] = field(default_factory=list)

    def record_inbound(self, message: Mapping[str, Any]) -> None:
        self._append("inbound", message)

    def record_outbound(self, message: Mapping[str, Any]) -> None:
        self._append("outbound", message)

    def write(self, path: Path = PLAN_9_6_E2E_TRANSCRIPT_PATH) -> Path:
        payload = {"stdio_lines": list(self.lines)}
        assert_transcript_payload_safe(payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _append(self, direction: str, message: Mapping[str, Any]) -> None:
        serializable = json.loads(json.dumps(dict(message)))
        assert_transcript_payload_safe(serializable)
        self.lines.append({"direction": direction, "message": serializable})


def assert_transcript_payload_safe(value: object) -> None:
    if isinstance(value, Mapping):
        if _looks_like_process_env(value):
            raise E2eTranscriptSerializationError("refusing to serialize process environment in transcript")
        for key, nested in value.items():
            if str(key) in _FORBIDDEN_TRANSCRIPT_ROOT_KEYS and isinstance(nested, Mapping):
                raise E2eTranscriptSerializationError(
                    f"refusing to serialize process environment under transcript key {key!r}"
                )
            assert_transcript_payload_safe(nested)
        return
    if isinstance(value, list):
        for item in value:
            assert_transcript_payload_safe(item)


def _looks_like_process_env(mapping: Mapping[object, object]) -> bool:
    keys = {str(key) for key in mapping}
    if keys & _SENSITIVE_ENV_KEY_NAMES:
        return True
    if "PATH" in keys and ("HOME" in keys or "USERPROFILE" in keys or "SystemRoot" in keys):
        return True
    return False
