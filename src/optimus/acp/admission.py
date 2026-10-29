"""Finite serialized-payload custody; these limits do not bound process RSS."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, fields
from enum import Enum

_LOGGER = logging.getLogger(__name__)

class AdmissionClass(Enum):
    ORDINARY = "ordinary"
    REQUIRED = "required"


@dataclass(frozen=True, slots=True)
class AdmissionLimits:
    pending_items: int = 64
    active_prompts: int = 8
    active_requests: int = 8
    inbound_bytes: int = 16 * 1024 * 1024
    frame_bytes: int = 8 * 1024 * 1024
    outbound_items: int = 64
    control_items: int = 8
    outbound_bytes: int = 16 * 1024 * 1024
    control_bytes: int = 1024 * 1024
    subprocess_items: int = 64
    stderr_bytes: int = 256 * 1024
    stderr_line_bytes: int = 16 * 1024

    def __post_init__(self) -> None:
        if any(type(getattr(self, item.name)) is not int or getattr(self, item.name) <= 0 for item in fields(self)):
            raise ValueError("admission limits must be positive finite integers")
        if self.control_bytes >= self.outbound_bytes:
            raise ValueError("control reserve must be smaller than outbound capacity")


DEFAULT_LIMITS = AdmissionLimits()


class Reservation:
    def __init__(self, account: AdmissionAccount, count: int, size: int) -> None:
        self._account = account
        self._count = count
        self._size = size
        self._released = False

    def release(self) -> None:
        account = self._account
        with account._lock:
            if self._released:
                return
            self._released = True
            account.count -= self._count
            account.bytes -= self._size


class AdmissionAccount:
    def __init__(self, *, count: int, bytes: int, reserved_count: int = 0, reserved_bytes: int = 0, queue_id: str = "inbound") -> None:
        if count <= 0 or bytes <= 0 or reserved_count < 0 or not 0 <= reserved_bytes < bytes:
            raise ValueError("invalid finite admission capacity")
        if queue_id not in {"inbound", "outbound", "subprocess"}:
            raise ValueError("unknown admission queue")
        self._queue_id = queue_id
        self._count_limit = count
        self._byte_limit = bytes
        self._reserved_count = reserved_count
        self._reserved_bytes = reserved_bytes
        self._lock = threading.Lock()
        self.count = self.bytes = 0
        self.rejected = 0
        self._full = False
        self._closed = False

    def _report(self, transition: str, count: int, size: int, rejected: int, elapsed: float) -> None:
        try:
            _LOGGER.info(
                "ACP queue %s %s count=%d bytes=%d rejected=%d wait_seconds=%.6f",
                self._queue_id, transition, count, size, rejected, elapsed,
            )
        except Exception:
            return  # Diagnostics cannot change admission or settlement.

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            snapshot = (self.count, self.bytes, self.rejected)
        self._report("closing", *snapshot, 0.0)

    def try_reserve(self, count: int, bytes: int, kind: AdmissionClass) -> Reservation | None:
        if count < 0 or bytes < 0:
            raise ValueError("negative reservation")
        started = time.monotonic()
        transition = ""
        reservation = None
        with self._lock:
            full = self.count + count > self._count_limit + self._reserved_count or self.bytes + bytes > self._byte_limit
            full |= kind is AdmissionClass.ORDINARY and (
                self.count + count > self._count_limit
                or self.bytes + bytes > self._byte_limit - self._reserved_bytes
            )
            if full or self._closed:
                self.rejected = min(2**63 - 1, self.rejected + 1)
                if not self._full and not self._closed:
                    self._full = True
                    transition = "full"
            else:
                if self._full:
                    self._full = False
                    transition = "recovered"
                self.count += count
                self.bytes += bytes
                reservation = Reservation(self, count, bytes)
            snapshot = (self.count, self.bytes, self.rejected)
        if transition:
            self._report(transition, *snapshot, time.monotonic() - started)
        return reservation
