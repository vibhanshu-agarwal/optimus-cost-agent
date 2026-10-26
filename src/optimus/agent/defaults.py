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


def auto_requested(environ: Mapping[str, str], *, cli_model: str | None = None) -> bool:
    """Whether this launch is Auto (Plan 12.4 Design 4). Only ``OPTIMUS_AGENT_MODEL=auto`` selects it, since the launch
    gate composes and approves the registry from the environment alone and never sees ``--model``. Refused:
    ``--model auto``, and the environment's ``auto`` with a different explicit ``--model``."""
    cli = (cli_model or "").strip()
    env = environ.get("OPTIMUS_AGENT_MODEL", "").strip()
    if cli == AUTO_MODEL:
        raise AgentModelError("Auto is selected only by OPTIMUS_AGENT_MODEL=auto, never by --model")
    if env == AUTO_MODEL and cli:
        raise AgentModelError(f"OPTIMUS_AGENT_MODEL=auto conflicts with --model {cli!r}; use one or the other")
    return env == AUTO_MODEL


def _eligible_implementers(registry: RegistrySnapshot) -> set[str]:
    return {model_id for role in IMPLEMENTER_ROLES for model_id in select_eligible_models(registry, role)}


def resolve_model_for_registry(
    environ: Mapping[str, str], *, cli_model: str | None = None, registry: RegistrySnapshot | None
) -> str:
    """Resolve the agent model against ``registry`` (None: enforcement inactive, today's rules).

    Under an enforced registry a configured model must be an exact ID eligible for an implementer
    role, and ``auto`` is refused here: it is never a model ID and never sent upstream. An Auto launch takes the
    Auto composition's own path (``auto_requested``) instead of this resolution.
    """
    chosen = (cli_model or "").strip() or environ.get("OPTIMUS_AGENT_MODEL", "").strip()
    if registry is None:
        return chosen or DEFAULT_AGENT_MODEL
    if not chosen:
        return default_agent_model(registry)
    if chosen == AUTO_MODEL:
        raise AgentModelError("'auto' is not a model ID; an Auto launch resolves each turn's model through the Auto composition")
    eligible = _eligible_implementers(registry)
    if chosen not in eligible:
        raise AgentModelError(
            f"model {chosen!r} is not eligible in the trusted model registry (eligible: {', '.join(sorted(eligible)) or 'none'}). "
            "Unset OPTIMUS_AGENT_MODEL (and --model) to use the default, or set it to an eligible model ID"
        )
    return chosen


def resolve_agent_model(environ: Mapping[str, str], *, cli_model: str | None = None) -> str:
    return resolve_model_for_registry(environ, cli_model=cli_model, registry=trusted_snapshot())
