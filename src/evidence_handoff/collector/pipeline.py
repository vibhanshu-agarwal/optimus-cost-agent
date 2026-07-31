"""Deterministic collector composition and observation validation."""

from __future__ import annotations

from collections.abc import Sequence

from .models import CollectionBatch, Observation, RunContext
from .protocols import Collector

_OBSERVATION_SCHEMA = "evidence-observation-v1"


def compose_collection(
    context: RunContext,
    collectors: Sequence[Collector],
) -> tuple[CollectionBatch, ...]:
    """Run collectors in order and validate normalized batches.

    Independent observations within a batch are sorted by sequence. Failures raise
    ValueError with a stable snake_case reason code and no body/path payload.
    """
    seen_ids: set[str] = set()
    batches: list[CollectionBatch] = []
    for collector in collectors:
        collector_id = collector.collector_id
        if collector_id in seen_ids:
            raise ValueError("collector_collision")
        seen_ids.add(collector_id)
        batch = collector.collect(context)
        if batch.collector_id != collector_id:
            raise ValueError("collector_id_mismatch")
        if batch.contract_version != collector.contract_version:
            raise ValueError("contract_version_mismatch")
        batches.append(_validate_batch(context, batch))
    return tuple(batches)


def _validate_batch(context: RunContext, batch: CollectionBatch) -> CollectionBatch:
    sequences: set[int] = set()
    artifacts_by_role = {artifact.role: artifact for artifact in batch.artifacts}
    if len(artifacts_by_role) != len(batch.artifacts):
        raise ValueError("artifact_role_collision")

    ordered = tuple(
        sorted(batch.observations, key=lambda item: (item.sequence, item.monotonic_offset_ns))
    )
    previous_offset: int | None = None
    normalized: list[Observation] = []
    for observation in ordered:
        if observation.schema != _OBSERVATION_SCHEMA:
            raise ValueError("unknown_schema")
        if observation.scenario_id != context.scenario_id:
            raise ValueError("foreign_scenario_id")
        if observation.run_id != context.run_id:
            raise ValueError("foreign_run_id")
        if observation.collector_id != batch.collector_id:
            raise ValueError("collector_id_mismatch")
        if observation.sequence in sequences:
            raise ValueError("duplicate_sequence")
        sequences.add(observation.sequence)
        if previous_offset is not None and observation.monotonic_offset_ns < previous_offset:
            raise ValueError("clock_regression")
        previous_offset = observation.monotonic_offset_ns
        if observation.artifact_role is not None:
            artifact = artifacts_by_role.get(observation.artifact_role)
            if artifact is None:
                raise ValueError("digest_mismatch")
            if observation.artifact_sha256 != artifact.sha256:
                raise ValueError("digest_mismatch")
        if observation.reason_code is not None and (
            not observation.reason_code
            or "/" in observation.reason_code
            or "\\" in observation.reason_code
            or " " in observation.reason_code
        ):
            raise ValueError("unsafe_reason_code")
        normalized.append(observation)

    return CollectionBatch(
        collector_id=batch.collector_id,
        contract_version=batch.contract_version,
        observations=tuple(normalized),
        artifacts=batch.artifacts,
    )
