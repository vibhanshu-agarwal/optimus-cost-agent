"""The Optimus Context Engine: bounded conversation views over exact host authority (Plan 12.2).

An extractable, in-process package (ADR-001). It sees immutable sanitized data and an injected
maintenance callback; it has no credentials, workspace, ACP transport, store, approval or ledger. It
imports nothing from `optimus`, the Gateway, security, the registry or the evidence packages.
"""

from __future__ import annotations

from .checkpoints import ReuseResult, publish_checkpoint, reuse_checkpoint
from .contracts import (
    STRATEGIES,
    SUMMARIZING_STRATEGIES,
    ContractError,
    HistoryRevision,
    HistorySnapshot,
    MaintenanceCallback,
    MaintenanceRequest,
    MaintenanceResult,
    OrdinaryTurn,
    PreparedView,
    ProtectedTurnState,
    StrategyParameters,
    SummaryCheckpoint,
    ViewLimits,
    history_digest,
    turn_source_digest,
)

__all__ = [
    "STRATEGIES",
    "SUMMARIZING_STRATEGIES",
    "ContractError",
    "HistoryRevision",
    "HistorySnapshot",
    "MaintenanceCallback",
    "MaintenanceRequest",
    "MaintenanceResult",
    "OrdinaryTurn",
    "PreparedView",
    "ProtectedTurnState",
    "ReuseResult",
    "StrategyParameters",
    "SummaryCheckpoint",
    "ViewLimits",
    "history_digest",
    "publish_checkpoint",
    "reuse_checkpoint",
    "turn_source_digest",
]
