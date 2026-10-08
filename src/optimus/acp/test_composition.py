"""Process-scoped Plan 12.2 test composition for the ACP host (closure release supplement V2, 2026-10-04).

After a launch is authorized, a named test profile becomes one explicit composition value passed into
the server: its reviewed snapshot, the exact model the test process uses, and the trusted route policy
every session adapter binds requests with. The operator's approval binds the profile through the
launch's security-snapshot digest (``authorize_launch``); the host re-composes the profile and refuses
any snapshot other than the one that authorized candidate digested. Nothing here reads the environment, flips ``ENFORCEMENT_ACTIVE``, changes ``trusted_snapshot()``
or edits shipped defaults; without a composition the host keeps today's unbound composition.

The Gateway composes the same named profile independently and refuses to start unless the signed
child manifest binds its hash, so the two sides agree on one approved effective hash.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from optimus.agent.defaults import AgentModelError, resolve_model_for_registry
from optimus.gateway.route_binding import RouteIdentityError, RoutePolicy
from optimus_model_policy import RegistrySnapshot
from optimus_model_policy.binding import BindingError, approval_literal, disclosure_key
from optimus_model_policy.test_profiles import TEST_PROFILES, TestProfile, compose_test_profile_snapshot

__all__ = ["TestComposition", "compose_test_composition"]


@dataclass(frozen=True)
class TestComposition:
    """One reviewed test profile, composed for this process after its launch was approved."""

    __test__ = False  # not a pytest test class

    profile: TestProfile
    snapshot: RegistrySnapshot

    def agent_model(self, environ: Mapping[str, str], *, cli_model: str | None) -> str:
        """The exact model this test process uses: the profile's own model, which the profile's snapshot
        must make eligible for an implementer role. Another explicit model is refused here, before any
        side effect, since the route policy binds only the profile's model (Fable CP4 release review m3)."""
        chosen = (cli_model or "").strip()
        if chosen and chosen != self.profile.model_id:
            raise AgentModelError(f"test profile {self.profile.name!r} runs only its own reviewed model")
        return resolve_model_for_registry(environ, cli_model=self.profile.model_id, registry=self.snapshot)

    def route_policy(self, *, model_id: str, shared_secret: str) -> RoutePolicy:
        """The trusted planning/answer route policy for the profile's exact model and role."""
        profile = self.profile
        if model_id != profile.model_id or profile.role is None or profile.output_cap is None:
            raise RouteIdentityError(f"test profile {profile.name!r} binds only its own reviewed model")
        return RoutePolicy(
            snapshot=self.snapshot,
            disclosure_key=disclosure_key(shared_secret),
            model_id=model_id,
            role=profile.role,
            output_cap=profile.output_cap,
        )


def compose_test_composition(name: str, *, approved_literal: str | None) -> TestComposition:
    """The named profile's composition. ``approved_literal`` is the registry literal the authorized
    candidate digested (the approval itself is enforced by ``authorize_launch``); a composition whose
    literal differs is refused."""
    snapshot = compose_test_profile_snapshot(name)
    if approved_literal != approval_literal(snapshot):
        raise BindingError("TEST_PROFILE_NOT_APPROVED", "the composed profile is not the one the authorized launch digested")
    return TestComposition(profile=TEST_PROFILES[name], snapshot=snapshot)
