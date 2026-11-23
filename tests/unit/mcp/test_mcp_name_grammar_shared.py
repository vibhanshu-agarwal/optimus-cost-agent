"""#345: the agent directive parser and the client MCP config normalizer share one name grammar."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from optimus.agent.directives import AgentDirectiveParseError, validate_mcp_name
from optimus.mcp import client_config
from optimus.mcp.client_config import ClientMcpConfigError, ClientMcpConfigNormalizer

CASES = [
    ("tools", True),
    ("Ctx7_tools.v1", True),
    ("a", True),
    ("x" * 64, True),
    ("x" * 65, False),
    ("", False),
    ("bad name", False),
    ("-lead", False),
    (".lead", False),
    ("trail\n", False),
    ("semi;colon", False),
]


def _directive_accepts(name: str) -> bool:
    try:
        validate_mcp_name(name, label="server")
    except AgentDirectiveParseError:
        return False
    return True


def _config_accepts(name: str, tmp_path: Path) -> bool:
    entry = {"name": name, "command": sys.executable, "args": [], "env": []}
    try:
        ClientMcpConfigNormalizer().normalize(
            [entry], workspace_root=tmp_path, controlled_path=str(Path(sys.executable).parent), hmac_key=b"k" * 32
        )
    except ClientMcpConfigError as exc:
        assert exc.rule_id == "client_mcp.invalid_server_name"
        return False
    return True


@pytest.mark.parametrize(("name", "valid"), CASES)
def test_both_modules_accept_and_reject_the_same_names(name: str, valid: bool, tmp_path: Path) -> None:
    assert _directive_accepts(name) is valid
    assert _config_accepts(name, tmp_path) is valid


def test_one_grammar_object_backs_both_modules() -> None:
    from optimus.agent import directives

    assert directives.MCP_NAME_RE is client_config.MCP_NAME_RE
