from __future__ import annotations

from collections.abc import Mapping

DEFAULT_AGENT_MODEL = "glm-5.2"


def resolve_agent_model(environ: Mapping[str, str], *, cli_model: str | None = None) -> str:
    if cli_model and cli_model.strip():
        return cli_model.strip()
    configured = environ.get("OPTIMUS_AGENT_MODEL", "").strip()
    if configured:
        return configured
    return DEFAULT_AGENT_MODEL
