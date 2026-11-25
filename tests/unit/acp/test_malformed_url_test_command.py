"""#597: a malformed URL in a TEST command is refused by the network rule as a verdict. urlparse raises ValueError for
"https://[" (Invalid IPv6 URL); that used to leave the prompt handler instead of ending the turn as TEST_GUARD_REFUSED.

Same harness as test_guard_refusal_ends_turn.py: the real AcpDuplexAdapter and AgentRunner, a recording shell."""

from __future__ import annotations

import pytest

from optimus.agent.directives import parse_agent_plan
from optimus.agent.models import TEST_GUARD_REFUSED
from tests.unit.acp.test_guard_refusal_ends_turn import _assert_ended_normally, _drive, _files

MALFORMED = ["https://[", "https://[::1"]


@pytest.mark.parametrize("url", MALFORMED)
async def test_a_malformed_url_in_a_test_command_ends_the_turn_with_fixed_text(url, tmp_path):
    (tmp_path / "small.py").write_text("old\n")
    before = _files(tmp_path)
    assert parse_agent_plan(f"TEST pytest -k {url}\n").tests  # the plan parses, so it is approvable

    response, outbound, runner, records = await _drive(tmp_path, f"TEST pytest -k {url}\nTEST pytest -q\n")

    _assert_ended_normally(response, outbound, runner, records, code=TEST_GUARD_REFUSED, token=url)
    assert _files(tmp_path) == before
