"""Source-owned test-only route exceptions (Plan 12.2 Haiku 5.5 release and Codex disposition, 2026-10-09).

An entry here relaxes two registry rules for one reviewed test profile, identified by its exact pinned
snapshot hash, and nothing else. Two profiles are listed: qualification (profile A) and attached (profile B,
the same policy plus the accepted summary-quality receipt; offline preparation batch, 2026-10-11):

- an EMPIRICAL size estimate: a ``utf8-bytes-ratio-empirical`` estimator is admitted although it is not
  publisher-verified (``verified`` stays false and keeps its meaning everywhere else). Passing calls show
  that the tested requests fitted, not that every input would;
- provider-family routing: the route's generic provider slug is accepted although OpenRouter documents
  that a base slug can reach every variant or region of that provider. The Gateway checks each
  response's router metadata for the expected provider, which identifies the provider, not a variant.

It is never a YAML flag: an override with any changed policy value composes a different hash and gets the ordinary
refusals. No production snapshot is ever listed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from optimus_model_policy.registry import RegistrySnapshot

__all__ = [
    "EMPIRICAL_ESTIMATOR_METHOD",
    "EXPERIMENTAL_ROUTES",
    "HAIKU_ATTACHED_HASH",
    "HAIKU_QUALIFICATION_HASH",
    "ExperimentalRoute",
    "experimental_route",
]

EMPIRICAL_ESTIMATOR_METHOD: Final = "utf8-bytes-ratio-empirical"

HAIKU_QUALIFICATION_HASH: Final = "048c1a2b3e7d3436d371e8964200064bb30f0a1a865c945f92a2fc09d3ba5cba"  # pragma: allowlist secret - registry identity, not a credential
HAIKU_ATTACHED_HASH: Final = "06e637845f5f7cea2b4a22d23407c59efc9741d7848b06ee5f4c3d2284f3f07d"  # pragma: allowlist secret - registry identity, not a credential


@dataclass(frozen=True, slots=True)
class ExperimentalRoute:
    """One reviewed test route: its profile, exact model, accepted provider-family slug and the provider
    name OpenRouter's router metadata must report for every response."""

    profile: str
    model_id: str
    provider_family: str
    provider_name: str


EXPERIMENTAL_ROUTES: Final[Mapping[str, ExperimentalRoute]] = MappingProxyType(
    {
        HAIKU_QUALIFICATION_HASH: ExperimentalRoute(
            profile="qualification",
            model_id="anthropic/claude-haiku-5.5",
            provider_family="anthropic",
            provider_name="Anthropic",
        ),
        HAIKU_ATTACHED_HASH: ExperimentalRoute(
            profile="attached",
            model_id="anthropic/claude-haiku-5.5",
            provider_family="anthropic",
            provider_name="Anthropic",
        ),
    }
)


def experimental_route(snapshot: RegistrySnapshot, model_id: str) -> ExperimentalRoute | None:
    """The reviewed experimental route for this exact snapshot and model, or None."""
    route = EXPERIMENTAL_ROUTES.get(snapshot.effective_hash)
    return route if route is not None and route.model_id == model_id else None
