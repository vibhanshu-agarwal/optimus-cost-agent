from optimus.agent.prompts import AGENT_PLANNER_PROMPT_VERSION, build_agent_planner_input


def test_planner_prompt_mandates_directive_grammar():
    prompt = build_agent_planner_input("Add a docstring")

    assert AGENT_PLANNER_PROMPT_VERSION in prompt
    assert "READ <relative-path>" in prompt
    assert "WRITE <relative-path>" in prompt
    assert "TEST pytest <relative-test-path-or-args>" in prompt
    assert "Do not emit prose before the directives" in prompt
