from __future__ import annotations

from collections.abc import Mapping

from optimus_model_policy import IMPLEMENTER_ROLES, RegistrySnapshot, Role, select_eligible_models
from optimus_model_policy.binding import trusted_snapshot

DEFAULT_AGENT_MODEL = "claude-haiku"
"""Today's default, used only while registry enforcement is inactive (Plan 12.2 Task 5). Once a
verified registry is enforced the default is the registry's cheapest eligible medium model."""

AUTO_MODEL = "auto"


class AgentModelError(ValueError):
    """The configured model cannot be used under the enforced model registry."""


def default_agent_model(registry: RegistrySnapshot | None) -> str:
    """The fixed default: today's alias while inactive, else the first eligible medium model."""
    if registry is None:
        return DEFAULT_AGENT_MODEL
    medium = select_eligible_models(registry, Role.MEDIUM)
    if not medium:
        raise AgentModelError("the trusted model registry has no eligible medium model")
    return medium[0]


def resolve_model_for_registry(
    environ: Mapping[str, str], *, cli_model: str | None = None, registry: RegistrySnapshot | None
) -> str:
    """Resolve the agent model against ``registry`` (None: enforcement inactive, today's rules).

    Under an enforced registry a configured model must be an exact ID eligible for an implementer
    role, and ``auto`` is refused: no accepted resolver is installed, so it is never sent upstream
    or treated as a medium classification.
    """
    chosen = (cli_model or "").strip() or environ.get("OPTIMUS_AGENT_MODEL", "").strip()
    if registry is None:
        return chosen or DEFAULT_AGENT_MODEL
    if not chosen:
        return default_agent_model(registry)
    if chosen == AUTO_MODEL:
        raise AgentModelError("'auto' model selection needs an accepted resolver, and none is installed")
    eligible = {model_id for role in IMPLEMENTER_ROLES for model_id in select_eligible_models(registry, role)}
    if chosen not in eligible:
        raise AgentModelError(f"model {chosen!r} is not eligible in the trusted model registry")
    return chosen


def resolve_agent_model(environ: Mapping[str, str], *, cli_model: str | None = None) -> str:
    return resolve_model_for_registry(environ, cli_model=cli_model, registry=trusted_snapshot())
