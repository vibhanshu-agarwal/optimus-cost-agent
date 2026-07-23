from optimus.agent.defaults import DEFAULT_AGENT_MODEL, resolve_agent_model


def test_resolve_agent_model_prefers_cli_override():
    assert resolve_agent_model({}, cli_model="claude-haiku") == "claude-haiku"


def test_resolve_agent_model_uses_env_when_cli_missing():
    assert resolve_agent_model({"OPTIMUS_AGENT_MODEL": "claude-haiku"}) == "claude-haiku"


def test_resolve_agent_model_falls_back_to_routable_shared_default():
    assert DEFAULT_AGENT_MODEL == "claude-haiku"
    assert resolve_agent_model({}) == "claude-haiku"
