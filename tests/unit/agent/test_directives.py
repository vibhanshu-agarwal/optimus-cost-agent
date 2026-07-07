import pytest

from optimus.agent.directives import AgentDirectiveParseError, parse_agent_plan


def test_parse_agent_plan_accepts_read_write_and_test_directives():
    directives = parse_agent_plan("READ src/example.py\nWRITE src/example.py\ncontent\nTEST pytest tests/unit -q")

    assert directives.read_paths == ("src/example.py",)
    assert directives.write.path == "src/example.py"
    assert directives.tests == (("pytest", "tests/unit", "-q"),)


def test_parse_agent_plan_rejects_unparseable_text():
    with pytest.raises(AgentDirectiveParseError, match="no valid agent directives"):
        parse_agent_plan("Here is what I would do in prose.")


def test_parse_agent_plan_rejects_unsafe_test_directive():
    with pytest.raises(AgentDirectiveParseError, match="unsafe TEST directive"):
        parse_agent_plan("TEST python -c print(1)")


@pytest.mark.parametrize(
    "plan_text",
    (
        "TEST python -m pytest tests/unit",
        "TEST pytest ../outside -q",
        "TEST pytest tests/unit; rm -rf .",
        "TEST pytest C:/repo/tests",
        "TEST pytest tests/unit && pytest tests/integration",
    ),
)
def test_test_directive_rejects_non_pytest_or_unsafe_tokens(plan_text):
    with pytest.raises(AgentDirectiveParseError, match="unsafe TEST directive"):
        parse_agent_plan(plan_text)
