"""Test helper: stamp a usage envelope once its price snapshot is durable, without assuming a fast disk (#632)."""

from __future__ import annotations

import time
from typing import Any

from optimus_gateway import usage_price_snapshots as snapshots


def stamp_when_durable(policy: Any, *, deadline_seconds: float = 30.0) -> dict[str, Any]:
    """``snapshots.stamp({}, policy)`` retried to a deadline. Each call already waits ``ACK_WAIT_SECONDS`` on the ticket,
    so this neither sleeps nor spins; a write still unacknowledged at the deadline returns ``{}`` and fails the caller."""
    end = time.monotonic() + deadline_seconds
    while True:
        stamped = snapshots.stamp({}, policy)
        if "price_snapshot_id" in stamped or time.monotonic() >= end:
            return stamped
