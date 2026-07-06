from __future__ import annotations

import json
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

DEFAULT_RELEASE_CREDENTIAL_SCAN_PATHS = (
    Path(".env"),
    Path(".env.local"),
    Path("pyproject.toml"),
    Path("reports/phase1-release-gate.json"),
    Path("reports/phase1-golden-results.json"),
    Path("reports/process-state.json"),
)

JSON_NAMES_AS_DATA_KEYS = frozenset({"provider_keys_resolvable"})


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


def default_release_credential_scan_paths(*, root: str | Path = ".") -> tuple[Path, ...]:
    base = Path(root).resolve()
    return tuple((base / path).resolve() for path in DEFAULT_RELEASE_CREDENTIAL_SCAN_PATHS)


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
    for config_path in config_paths:
        path = Path(config_path)
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".json":
            try:
                hits.update(_scan_json_value(json.loads(text)))
                continue
            except json.JSONDecodeError:
                pass
        hits.update(_scan_text_for_provider_assignments(text))
    return hits


def _scan_json_value(value: object, *, parent_key: str | None = None) -> set[str]:
    hits: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            canonical = _canonical_name(key)
            if canonical in PROVIDER_CREDENTIAL_NAMES and child not in (None, "", [], {}):
                hits.add(canonical)
            hits.update(_scan_json_value(child, parent_key=key))
    elif isinstance(value, list) and parent_key not in JSON_NAMES_AS_DATA_KEYS:
        for child in value:
            hits.update(_scan_json_value(child, parent_key=parent_key))
    elif isinstance(value, str) and parent_key not in JSON_NAMES_AS_DATA_KEYS:
        hits.update(_scan_text_for_provider_assignments(value))
    return hits


def _scan_text_for_provider_assignments(text: str) -> set[str]:
    hits: set[str] = set()
    names_pattern = "|".join(re.escape(name) for name in sorted(PROVIDER_CREDENTIAL_NAMES, key=len, reverse=True))
    pattern = re.compile(rf'["\']?\b({names_pattern})\b["\']?\s*[:=]', re.IGNORECASE)
    for match in pattern.finditer(text):
        hits.add(_canonical_name(match.group(1)))
    return hits


def _canonical_name(name: str) -> str:
    upper = name.upper()
    for candidate in PROVIDER_CREDENTIAL_NAMES:
        if candidate.upper() == upper:
            return candidate
    return upper
