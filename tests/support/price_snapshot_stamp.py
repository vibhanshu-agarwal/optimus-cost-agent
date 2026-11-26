"""Test helpers: stamp a usage envelope once its price snapshot is durable, without assuming a fast disk (#632)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from optimus_gateway import usage_price_snapshots as snapshots


def until_stamped(produce: Callable[[], dict[str, Any]], *, deadline_seconds: float = 30.0) -> dict[str, Any]:
    """``produce()`` retried until its usage carries ``price_snapshot_id``, to a deadline. Each real-writer call already
    waits ``ACK_WAIT_SECONDS`` on the ticket; the short pause only keeps a call that returns at once (a failed or absent
    write) from spinning. Unstamped at the deadline, the last usage is returned and fails the caller's assertion."""
    end = time.monotonic() + deadline_seconds
    while True:
        usage = produce()
        if "price_snapshot_id" in usage or time.monotonic() >= end:
            return usage
        threading.Event().wait(0.01)


def stamp_when_durable(policy: Any, *, deadline_seconds: float = 30.0) -> dict[str, Any]:
    return until_stamped(lambda: snapshots.stamp({}, policy), deadline_seconds=deadline_seconds)
