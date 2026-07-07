from __future__ import annotations

AGENT_PLANNER_PROMPT_VERSION = "AGENT_PLANNER_PROMPT_VERSION:2026-07-07"

_DIRECTIVE_GRAMMAR = """\
Respond using only the directive grammar below. Do not emit prose before the directives.

Directives:
- READ <relative-path>
- WRITE <relative-path>
  <file content immediately after the WRITE line>
- TEST pytest <relative-test-path-or-args>
"""


def build_agent_planner_input(task: str) -> str:
    return (
        f"{AGENT_PLANNER_PROMPT_VERSION}\n\n"
        f"Task: {task}\n\n"
        f"{_DIRECTIVE_GRAMMAR}"
    )
