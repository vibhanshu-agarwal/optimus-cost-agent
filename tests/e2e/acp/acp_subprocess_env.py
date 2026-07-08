from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from optimus.acp.subprocess_env import build_acp_subprocess_env
from tests.integration.optimus_gateway.gateway_env import project_root


def build_acp_subprocess_env_for_tests(
    *,
    operator_environ: Mapping[str, str] | None = None,
    root: Path | None = None,
) -> dict[str, str]:
    return build_acp_subprocess_env(operator_environ=operator_environ, project_root=root or project_root())
