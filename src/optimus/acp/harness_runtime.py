"""The agent runner TOGETHER with the Redis lifetime it runs on (Seam 2, checkpoint B).

A leaf module on purpose: the Plan 11.26 shutdown audit probes this bundle's single close
path, and importing it from ``optimus.acp.bootstrap`` would pull the whole serving
composition (dispatcher, server, MCP, guardrails) into a probe that only exercises one
`close`. Bootstrap re-exports it, so callers see one name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentHarnessRuntime:
    """Before this seam the harness builder returned only the runner; the ``RedisRuntime``
    it built was reachable through the runner's store and sink but nothing held a close
    handle for it, so the serving process could never shut it down. This bundle is that
    handle. A serving process hands it to ``AcpStreamServer``; a standalone harness closes
    it explicitly.
    """

    agent_runner: Any
    redis_runtime: Any

    def close(self, *, timeout: float | None = None):
        """Observe the runtime's single teardown; see ``RedisRuntime.close``."""
        return self.redis_runtime.close(timeout=timeout)
