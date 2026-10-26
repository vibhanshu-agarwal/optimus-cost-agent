"""Shared idle-MCP boundary fixtures; no test-module imports."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from context_engine import StrategyParameters, ViewLimits
from context_engine.engine import ContextEngine
from context_engine.summary import PROMPT_VERSION, SUMMARY_FORMAT
from optimus.context.assembly import ContextAttachment
from optimus.mcp.client_config import ClientMcpRuntimeCapability, ClientMcpSafeIdentity, ClientMcpSafeView


def context_attachment() -> ContextAttachment:
    def estimate(text: str) -> int:
        return (len(text.encode("utf-8")) + 3) // 4
    return ContextAttachment(
        engine=ContextEngine(),
        parameters=StrategyParameters(anchor_input_tokens=200, compaction_tail_input_tokens=30, hybrid_tail_input_tokens=30,
            summary_output_tokens=300, max_maintenance_calls=4, prompt_version=PROMPT_VERSION, format_version=SUMMARY_FORMAT),
        limits=ViewLimits(history_input_tokens=4000, source_max_bytes=2_000_000, transient_max_bytes=2_000_000,
            maintenance_input_tokens=400_000, maintenance_output_tokens=300, summary_max_bytes=1200,
            estimate_history=estimate, estimator_id="utf8-bytes-div-4-test"),
        source_max_bytes=2_000_000, record_reservation_bytes=0, usable_input_tokens=500_000,
        estimate_request=estimate, registry_hash="e" * 64, model_id="test/planner", summarizer=None,
        summarizer_route=None, record_receipt=lambda _: None, max_repacks=2,
    )


def capability(*, command: str, arguments: tuple[str, ...] = (), name: str = "owned-peer") -> ClientMcpRuntimeCapability:
    identity = ClientMcpSafeIdentity(
        transport="stdio", server_name=name, canonical_target=command,
        arguments=arguments, credential_name_fingerprints=(),
    )
    return ClientMcpRuntimeCapability(
        safe_identity=identity,
        safe_view=ClientMcpSafeView(
            provenance="client_supplied_acp", transport="stdio", server_name=name,
            canonical_target=command, arguments=arguments, credential_names=(),
            credential_name_fingerprints=(), scanner_rule_ids=(), disposition="normalized",
        ),
        header_values={}, env_values={},
    )


@dataclass
class ContextWitness:
    tasks: list[tuple[str, asyncio.Task[Any] | None]] = field(default_factory=list)

    def wrap(self, factory, label: str):
        @asynccontextmanager
        async def context(*args):
            self.tasks.append((label + ":enter", asyncio.current_task()))
            try:
                async with factory(*args) as value:
                    yield value
            finally:
                self.tasks.append((label + ":exit", asyncio.current_task()))
        return context


def peer_script() -> Path:
    return Path(__file__).resolve().parents[1] / "integration" / "mcp" / "sdk_stdio_peer.py"
