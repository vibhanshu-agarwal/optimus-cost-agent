from __future__ import annotations

from collections.abc import Mapping

from optimus_model_policy import IMPLEMENTER_ROLES, RegistrySnapshot, Role, select_eligible_models
from optimus_model_policy.binding import trusted_snapshot

DEFAULT_AGENT_MODEL = "claude-haiku"
"""The inactive-enforcement alias, used only when no registry is passed (Plan 12.2 Task 5). With the enforced
registry (closure plan v3) the default is its cheapest eligible medium model, else its first eligible easy model."""

AUTO_MODEL = "auto"


class AgentModelError(ValueError):
    """The configured model cannot be used under the enforced model registry."""


def default_agent_model(registry: RegistrySnapshot | None) -> str:
    """The fixed default: the alias without a registry, else the first eligible medium model, else (the explicit
    default-planner exception of closure plan v3, until a medium model qualifies) the first eligible easy model.
    The model keeps its own tier; nothing is reassigned."""
    if registry is None:
        return DEFAULT_AGENT_MODEL
    for role in (Role.MEDIUM, Role.EASY):
        eligible = select_eligible_models(registry, role)
        if eligible:
            return eligible[0]
    raise AgentModelError("the trusted model registry has no eligible medium or easy model")


def _eligible_implementers(registry: RegistrySnapshot) -> set[str]:
    return {model_id for role in IMPLEMENTER_ROLES for model_id in select_eligible_models(registry, role)}


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
    eligible = _eligible_implementers(registry)
    if chosen not in eligible:
        raise AgentModelError(
            f"model {chosen!r} is not eligible in the trusted model registry (eligible: {', '.join(sorted(eligible)) or 'none'}). "
            "Unset OPTIMUS_AGENT_MODEL (and --model) to use the default, or set it to an eligible model ID"
        )
    return chosen


def resolve_agent_model(environ: Mapping[str, str], *, cli_model: str | None = None) -> str:
    return resolve_model_for_registry(environ, cli_model=cli_model, registry=trusted_snapshot())
