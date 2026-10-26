"""Process-scoped Auto composition for the ACP host (Plan 12.4 Designs 1 and 4; ADR-027).

``OPTIMUS_AGENT_MODEL=auto`` is the only way to choose Auto (``optimus.agent.defaults.auto_requested``). The launch
gate composes the Auto registry (the shipped defaults, the shipped Auto overlay and the operator override) and binds
its literal and its composition name in the operator's approval. After the launch is authorized, the host recomposes it
here and refuses anything other than what that authorized candidate digested. The Gateway composes the same registry
independently (``--auto-composition``) and refuses to start unless the signed manifest binds its hash. Nothing here
reads the environment, changes ``trusted_snapshot()`` or edits shipped data.
"""

from __future__ import annotations

from dataclasses import dataclass

from optimus.agent.defaults import default_agent_model
from optimus_model_policy import RegistrySnapshot
from optimus_model_policy.binding import AUTO_COMPOSITION, BindingError, approval_literal, auto_snapshot

__all__ = ["AutoComposition", "compose_auto_composition"]


@dataclass(frozen=True)
class AutoComposition:
    """The approved Auto registry for this launch."""

    snapshot: RegistrySnapshot

    def default_model(self) -> str:
        """ADR-023's default planner computed in the Auto registry: the strict auth probe's model, and the last fallback
        when no tier at or above a turn's is routable. Computed from configuration, never pinned."""
        return default_agent_model(self.snapshot)


def compose_auto_composition(*, approved_literal: str | None, composition: str | None) -> AutoComposition:
    """The Auto composition. ``approved_literal`` and ``composition`` are what the authorized candidate digested; a
    launch whose approval did not bind the Auto composition, or whose recomposed literal differs, is refused."""
    if composition != AUTO_COMPOSITION:
        raise BindingError("AUTO_NOT_APPROVED", "the authorized launch did not bind the Auto composition")
    snapshot = auto_snapshot()
    if snapshot is None or approved_literal != approval_literal(snapshot):
        raise BindingError("AUTO_NOT_APPROVED", "the composed Auto registry is not the one the authorized launch digested")
    return AutoComposition(snapshot=snapshot)
