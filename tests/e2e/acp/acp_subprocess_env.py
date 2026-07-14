from __future__ import annotations

from collections.abc import Mapping

from optimus.acp.subprocess_env import build_acp_subprocess_env


def build_acp_subprocess_env_for_tests(
    *,
    operator_environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    return build_acp_subprocess_env(operator_environ=operator_environ)
