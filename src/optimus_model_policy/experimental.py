"""Per-model admission exceptions, read from each model's own registry entry (Plan 12.4 v7 Design 1; ADR-025).

An entry's ``admission`` block relaxes up to two registry rules for that model only, and nothing else:

- ``empirical_estimate``: an unverified ``utf8-bytes-ratio-empirical`` estimator is admitted (``verified`` stays
  false and keeps its meaning everywhere else). Passing calls show that the tested requests fitted, not that every
  input would; every reply's reported prompt tokens are checked against the estimate.
- ``provider_family``: the route's provider base slug is accepted although OpenRouter documents that a base slug
  can reach every variant or region of that provider. The Gateway checks each reply's router metadata for the
  recorded provider name, which identifies the provider, not a variant.

The block is data, not code: it is part of the canonical policy, so it changes the effective hash and is admitted
only once the operator approves that hash in the launch approval (ADR-025 supersedes the code-pinned table that
Plan 12.2 bound to one snapshot hash and one model). Every exception route keeps the usage, finish, one-attempt and
no-pipeline reply checks, disabled provider fallback, receipt-first accounting and a permanent per-model stop for the
rest of the Gateway's life after a failed check.

The hashes below are review pins, never admission keys: the two Haiku test profiles' reviewed snapshots
(``test_profiles.py`` refuses a profile that composes to anything else) and the packaged defaults' reviewed
snapshot, which the shipped defaults compose to exactly (they are "old defaults + the attached override").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from optimus_model_policy.registry import RegistrySnapshot

__all__ = [
    "EMPIRICAL_ESTIMATOR_METHOD",
    "HAIKU_ATTACHED_HASH",
    "HAIKU_QUALIFICATION_HASH",
    "SHIPPED_DEFAULTS_HASH",
    "ExperimentalRoute",
    "experimental_route",
]

EMPIRICAL_ESTIMATOR_METHOD: Final = "utf8-bytes-ratio-empirical"

HAIKU_QUALIFICATION_HASH: Final = "d180f7b1cbfa1f2e6d7655d91b6cc04ed2f045ac66e9a41ccf5d99140cba9ba1"  # pragma: allowlist secret - registry identity, not a credential
HAIKU_ATTACHED_HASH: Final = "fdcf00f0ffff25030e0d97ea3c3bc5be44155f432d1a2e0d07fe5142a9df88c1"  # pragma: allowlist secret - registry identity, not a credential
SHIPPED_DEFAULTS_HASH: Final = HAIKU_ATTACHED_HASH
"""The packaged defaults' reviewed effective hash: the attached profile's (closure plan v3)."""


@dataclass(frozen=True, slots=True)
class ExperimentalRoute:
    """One model's admission exceptions in a snapshot: whether its estimate is empirical, and the provider base
    slug and router-metadata name a provider-family route must report (both None when it has no such part)."""

    model_id: str
    empirical_estimate: bool
    provider_family: str | None
    provider_name: str | None


def experimental_route(snapshot: RegistrySnapshot, model_id: str) -> ExperimentalRoute | None:
    """This model's admission exceptions in ``snapshot``, from its own entry, or None when it has none."""
    entry = snapshot.policy.models.get(model_id)
    admission = None if entry is None else entry.admission
    if admission is None or (admission.empirical_estimate is None and admission.provider_family is None):
        return None
    family = admission.provider_family
    return ExperimentalRoute(
        model_id=model_id,
        empirical_estimate=admission.empirical_estimate is not None,
        provider_family=None if family is None else family.provider,
        provider_name=None if family is None else family.provider_name,
    )
