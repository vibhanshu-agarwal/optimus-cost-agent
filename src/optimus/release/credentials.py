from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES

ALLOWED_LOCAL_CREDENTIAL_NAMES = frozenset({"OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY"})
PROVIDER_CREDENTIAL_NAMES = frozenset(
    {
        *LOCAL_PROVIDER_KEY_NAMES,
        "ANTHROPIC_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "LANGSMITH_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "TAVILY_API_KEY",
        "GLM_API_KEY",
    }
)


@dataclass(frozen=True)
class CredentialScanResult:
    allowed_present: tuple[str, ...]
    provider_keys_resolvable: tuple[str, ...]
    config_hits: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.provider_keys_resolvable

    @property
    def summary(self) -> str:
        if self.passed:
            return f"allowed Optimus credentials present: {', '.join(self.allowed_present)}"
        return f"provider credentials resolvable: {', '.join(self.provider_keys_resolvable)}"


def scan_local_credentials(
    *,
    environ: dict[str, str] | None = None,
    config_paths: tuple[str | Path, ...] = (),
) -> CredentialScanResult:
    active_environ = dict(os.environ) if environ is None else environ
    allowed_present = tuple(sorted(key for key in ALLOWED_LOCAL_CREDENTIAL_NAMES if active_environ.get(key)))
    provider_hits = set(key for key in PROVIDER_CREDENTIAL_NAMES if active_environ.get(key))
    config_hits = _scan_config_files(config_paths)
    provider_hits.update(config_hits)
    return CredentialScanResult(
        allowed_present=allowed_present,
        provider_keys_resolvable=tuple(sorted(provider_hits)),
        config_hits=tuple(sorted(config_hits)),
    )


def _scan_config_files(config_paths: tuple[str | Path, ...]) -> set[str]:
    hits: set[str] = set()
    names_pattern = "|".join(re.escape(name) for name in sorted(PROVIDER_CREDENTIAL_NAMES, key=len, reverse=True))
    pattern = re.compile(rf'["\']?\b({names_pattern})\b["\']?\s*[:=]', re.IGNORECASE)
    for config_path in config_paths:
        path = Path(config_path)
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(text):
            canonical = _canonical_name(match.group(1))
            hits.add(canonical)
    return hits


def _canonical_name(name: str) -> str:
    upper = name.upper()
    for candidate in PROVIDER_CREDENTIAL_NAMES:
        if candidate.upper() == upper:
            return candidate
    return upper
