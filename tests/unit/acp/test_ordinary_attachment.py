"""Plan 12.2 closure plan v3: the ordinary launch attaches the Context Engine on the shipped registry.

The ordinary composition reuses the engine, Gateway maintenance and the one shared numeric policy, with no Stage C
scenario, seeder, fault seam or ledger. Every planner/answer request is bound through an ordinary route policy for
the resolved agent model, and the summarizer is the registry's first eligible summarizer (Haiku 5.5).
"""

from __future__ import annotations

import pytest

from context_engine.engine import ContextEngine
from optimus.acp import context_attachment as ordinary
from optimus.acp import stage_c as host
from optimus.context import shipped_policy
from optimus.gateway.route_binding import RouteIdentityError
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.binding import trusted_snapshot
from optimus_model_policy.experimental import SHIPPED_DEFAULTS_HASH

HAIKU = "anthropic/claude-haiku-5.5"
SECRET = "synthetic-shared-secret"  # pragma: allowlist secret - synthetic test value


def _shipped():
    snapshot = trusted_snapshot()
    assert snapshot is not None
    return snapshot


def test_the_shared_limits_are_the_stage_c_limits_on_the_same_snapshot() -> None:
    """One numeric policy object: Stage C's names are the shipped ones, and the attached profile's limits are the
    shipped snapshot's (usable 229,376; history 131,072; summary 8,192 tokens and bytes)."""
    assert host.stage_c_limits is shipped_policy.attachment_limits and host.StageCLimits is shipped_policy.AttachmentLimits
    shipped = shipped_policy.attachment_limits(_shipped(), HAIKU)
    attached = host.stage_c_limits(profiles.compose_test_profile_snapshot("attached"), HAIKU)
    for limits in (shipped, attached):
        assert limits.usable_input_tokens == 229_376
        assert (limits.limits.history_input_tokens, limits.limits.maintenance_output_tokens, limits.limits.summary_max_bytes) == (131_072, 8_192, 8_192)
        assert limits.parameters.max_maintenance_calls == 18
    assert shipped.parameters == attached.parameters
    assert (host.SOURCE_MAX_BYTES, host.RECORD_RESERVATION_BYTES, host.MAX_MAINTENANCE_CALLS) == (1_048_576, 131_072, 18)


def test_the_ordinary_attachment_has_no_stage_c_controls() -> None:
    attachment = ordinary.ordinary_attachment(snapshot=_shipped(), model_id=HAIKU, gateway_client=object(), shared_secret=SECRET)

    assert attachment is not None
    assert type(attachment.engine) is ContextEngine, "the plain engine: no scenario wrapper or fault seam"
    assert attachment.registry_hash == SHIPPED_DEFAULTS_HASH and attachment.model_id == HAIKU
    assert attachment.summarizer_route is not None and attachment.summarizer_route.model_id == HAIKU
    assert attachment.summarizer_route.role == "summarizer"
    assert attachment.record_receipt is shipped_policy.no_attachment_ledger
    assert (attachment.max_repacks, attachment.initial_strategy) == (1, "compaction")
    assert (attachment.source_max_bytes, attachment.record_reservation_bytes) == (1_048_576, 131_072)
    assert attachment.usable_input_tokens == 229_376


def test_without_an_eligible_summarizer_the_ordinary_launch_stays_absent_engine() -> None:
    qualification = profiles.compose_test_profile_snapshot("qualification")  # Haiku without its receipt
    assert ordinary.ordinary_attachment(snapshot=qualification, model_id=HAIKU, gateway_client=object(), shared_secret=SECRET) is None


def test_the_ordinary_route_policy_binds_the_agent_model_in_its_own_role() -> None:
    policy = ordinary.ordinary_route_policy(snapshot=_shipped(), model_id=HAIKU, shared_secret=SECRET)

    assert policy.identity.registry_hash == SHIPPED_DEFAULTS_HASH
    assert (policy.identity.model_id, policy.identity.role, policy.output_cap) == (HAIKU, "easy", 32_768)


def test_the_ordinary_route_policy_refuses_a_model_the_registry_does_not_make_eligible() -> None:
    with pytest.raises(RouteIdentityError):
        ordinary.ordinary_route_policy(snapshot=_shipped(), model_id="openai/gpt-6-luna", shared_secret=SECRET)
