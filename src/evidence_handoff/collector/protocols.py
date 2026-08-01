"""Portable collector capability protocols.

Host implementations may satisfy these protocols. Concrete host types must never
appear in portable signatures, annotations, or serialized contracts.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from .models import CapturedArtifact, CollectionBatch, EvidenceClaim, Observation, RunContext


class Collector(Protocol):
    collector_id: str
    contract_version: str

    def collect(self, context: RunContext) -> CollectionBatch: ...


class Detector(Protocol):
    detector_id: str
    contract_version: str

    def detect(
        self,
        *,
        context: RunContext,
        observations: Sequence[Observation],
        artifacts: Sequence[CapturedArtifact],
    ) -> tuple[EvidenceClaim, ...]: ...


class Clock(Protocol):
    def monotonic_ns(self) -> int: ...

    def wall_now_iso(self) -> str: ...


class ArtifactStore(Protocol):
    def store(
        self,
        *,
        role: str,
        media_type: str,
        payload: bytes,
        relative_locator: str,
    ) -> CapturedArtifact: ...
