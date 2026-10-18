"""The shipped default agent model (Plan 12.2 closure plan v3): the enforced registry's first eligible medium model,
else its first eligible easy model. No medium model is eligible yet, so the shipped default is Claude Haiku 5.5;
the old `claude-haiku` alias (Haiku 4.5, removed by ADR-003) is refused with migration guidance."""

import pytest

from optimus.agent.defaults import AgentModelError, resolve_agent_model

HAIKU = "anthropic/claude-haiku-5.5"


def test_resolve_agent_model_prefers_an_eligible_cli_override():
    assert resolve_agent_model({"OPTIMUS_AGENT_MODEL": "x"}, cli_model=HAIKU) == HAIKU


def test_resolve_agent_model_uses_an_eligible_env_model_when_cli_missing():
    assert resolve_agent_model({"OPTIMUS_AGENT_MODEL": HAIKU}) == HAIKU


def test_resolve_agent_model_falls_back_to_the_shipped_default():
    assert resolve_agent_model({}) == HAIKU


@pytest.mark.parametrize("configured", ["claude-haiku", "anthropic/claude-haiku-4.5", "vendor/any"])
def test_an_unregistered_model_is_refused_with_migration_guidance(configured):
    with pytest.raises(AgentModelError) as caught:
        resolve_agent_model({"OPTIMUS_AGENT_MODEL": configured})
    message = str(caught.value)
    assert "not eligible" in message and HAIKU in message and "OPTIMUS_AGENT_MODEL" in message
