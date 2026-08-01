"""Unit tests for portable collector composition and pipeline validation."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import get_type_hints

import pytest

from evidence_handoff.collector.models import (
    CapturedArtifact,
    CollectionBatch,
    Observation,
    RunContext,
)


def _pipeline():
    from evidence_handoff.collector import pipeline

    return pipeline


def _protocols():
    from evidence_handoff.collector import protocols

    return protocols


def _context(**overrides: object) -> RunContext:
    base = dict(
        schema="evidence-run-v1",
        scenario_id="zed-session",
        run_id="run-aaa",
        scenario_sha256="a" * 64,
        capture_root=Path("/tmp/capture"),
        monotonic_origin_ns=1_000,
    )
    base.update(overrides)
    return RunContext(**base)  # type: ignore[arg-type]


def _observation(**overrides: object) -> Observation:
    base = dict(
        schema="evidence-observation-v1",
        scenario_id="zed-session",
        run_id="run-aaa",
        collector_id="c1",
        sequence=1,
        monotonic_offset_ns=10,
        observed_at="2026-07-31T00:00:00+00:00",
        observation_kind="sample",
        correlation=(("k", "v"),),
        artifact_role=None,
        artifact_sha256=None,
        reason_code=None,
    )
    base.update(overrides)
    return Observation(**base)  # type: ignore[arg-type]


def _artifact(**overrides: object) -> CapturedArtifact:
    base = dict(
        role="trace",
        media_type="application/x-ndjson",
        relative_locator="artifacts/trace.ndjson",
        sha256="b" * 64,
        size_bytes=12,
    )
    base.update(overrides)
    return CapturedArtifact(**base)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class _FakeCollector:
    collector_id: str
    contract_version: str
    batch: CollectionBatch

    def collect(self, context: RunContext) -> CollectionBatch:
        del context
        return self.batch


def test_protocols_expose_collector_detector_clock_and_store() -> None:
    protocols = _protocols()
    assert hasattr(protocols, "Collector")
    assert hasattr(protocols, "Detector")
    assert hasattr(protocols, "Clock")
    assert hasattr(protocols, "ArtifactStore")


def test_compose_preserves_collector_order() -> None:
    pipeline = _pipeline()
    context = _context()
    first = CollectionBatch(
        collector_id="alpha",
        contract_version="v1",
        observations=(_observation(collector_id="alpha", sequence=1, monotonic_offset_ns=5),),
        artifacts=(),
    )
    second = CollectionBatch(
        collector_id="beta",
        contract_version="v1",
        observations=(_observation(collector_id="beta", sequence=1, monotonic_offset_ns=1),),
        artifacts=(),
    )
    batches = pipeline.compose_collection(
        context,
        (
            _FakeCollector("alpha", "v1", first),
            _FakeCollector("beta", "v1", second),
        ),
    )
    assert [batch.collector_id for batch in batches] == ["alpha", "beta"]


def test_compose_sorts_independent_observations_within_batch() -> None:
    pipeline = _pipeline()
    context = _context()
    unsorted = CollectionBatch(
        collector_id="c1",
        contract_version="v1",
        observations=(
            _observation(sequence=2, monotonic_offset_ns=20),
            _observation(sequence=1, monotonic_offset_ns=10),
        ),
        artifacts=(),
    )
    batches = pipeline.compose_collection(
        context,
        (_FakeCollector("c1", "v1", unsorted),),
    )
    assert [item.sequence for item in batches[0].observations] == [1, 2]


def test_compose_rejects_duplicate_sequence() -> None:
    pipeline = _pipeline()
    batch = CollectionBatch(
        collector_id="c1",
        contract_version="v1",
        observations=(
            _observation(sequence=1, monotonic_offset_ns=10),
            _observation(sequence=1, monotonic_offset_ns=20),
        ),
        artifacts=(),
    )
    with pytest.raises(ValueError, match="duplicate_sequence"):
        pipeline.compose_collection(_context(), (_FakeCollector("c1", "v1", batch),))


def test_compose_rejects_foreign_run_id() -> None:
    pipeline = _pipeline()
    batch = CollectionBatch(
        collector_id="c1",
        contract_version="v1",
        observations=(_observation(run_id="other-run"),),
        artifacts=(),
    )
    with pytest.raises(ValueError, match="foreign_run_id"):
        pipeline.compose_collection(_context(), (_FakeCollector("c1", "v1", batch),))


def test_compose_rejects_artifact_digest_mismatch() -> None:
    pipeline = _pipeline()
    batch = CollectionBatch(
        collector_id="c1",
        contract_version="v1",
        observations=(
            _observation(
                artifact_role="trace",
                artifact_sha256="c" * 64,
            ),
        ),
        artifacts=(_artifact(sha256="b" * 64),),
    )
    with pytest.raises(ValueError, match="digest_mismatch"):
        pipeline.compose_collection(_context(), (_FakeCollector("c1", "v1", batch),))


def test_compose_rejects_clock_regression() -> None:
    pipeline = _pipeline()
    batch = CollectionBatch(
        collector_id="c1",
        contract_version="v1",
        observations=(
            _observation(sequence=1, monotonic_offset_ns=30),
            _observation(sequence=2, monotonic_offset_ns=10),
        ),
        artifacts=(),
    )
    with pytest.raises(ValueError, match="clock_regression"):
        pipeline.compose_collection(_context(), (_FakeCollector("c1", "v1", batch),))


def test_compose_rejects_collector_id_collision() -> None:
    pipeline = _pipeline()
    batch = CollectionBatch(
        collector_id="c1",
        contract_version="v1",
        observations=(_observation(),),
        artifacts=(),
    )
    with pytest.raises(ValueError, match="collector_collision"):
        pipeline.compose_collection(
            _context(),
            (
                _FakeCollector("c1", "v1", batch),
                _FakeCollector("c1", "v1", batch),
            ),
        )


def test_compose_errors_are_body_free_reason_codes_only() -> None:
    pipeline = _pipeline()
    batch = CollectionBatch(
        collector_id="c1",
        contract_version="v1",
        observations=(_observation(run_id="foreign"),),
        artifacts=(),
    )
    with pytest.raises(ValueError) as exc_info:
        pipeline.compose_collection(_context(), (_FakeCollector("c1", "v1", batch),))
    message = str(exc_info.value)
    assert message == "foreign_run_id"
    assert "/" not in message
    assert "\\" not in message
    assert "traceback" not in message.lower()


def test_compose_signature_has_no_concrete_host_types() -> None:
    pipeline = _pipeline()
    hints = get_type_hints(pipeline.compose_collection)
    serialized = " ".join(str(value) for value in hints.values())
    for forbidden in ("Zed", "Windows", "Dwm", "Acpx", "Keyring", "optimus"):
        assert forbidden.lower() not in serialized.lower()
    source = inspect.getsource(pipeline.compose_collection)
    assert "Host" not in source
