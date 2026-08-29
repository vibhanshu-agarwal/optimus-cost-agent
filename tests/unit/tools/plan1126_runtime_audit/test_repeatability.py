"""Repeatability classification tests."""

from __future__ import annotations

from tools.plan1126_runtime_audit.repeatability import RepeatabilityStatus, classify_repeatability


def test_repeatability_distinguishes_runtime_flake_from_harness_invalidity() -> None:
    flaky = classify_repeatability(
        outcomes=({"state": "sent", "count": 1}, {"count": 1, "state": "failed"}),
        harness_fingerprints=("h1", "h1"),
        provenance_fingerprints=("p1", "p1"),
    )
    assert flaky.status is RepeatabilityStatus.FLAKY

    invalid = classify_repeatability(
        outcomes=({"state": "sent"}, {"state": "sent"}),
        harness_fingerprints=("h1", "h2"),
        provenance_fingerprints=("p1", "p1"),
    )
    assert invalid.status is RepeatabilityStatus.HARNESS_INVALID


def test_repeatability_normalizes_mapping_order_for_stable_outcomes() -> None:
    result = classify_repeatability(
        outcomes=({"state": "sent", "nested": {"a": 1, "b": 2}}, {"nested": {"b": 2, "a": 1}, "state": "sent"}),
        harness_fingerprints=("h1", "h1"),
        provenance_fingerprints=("p1", "p1"),
    )
    assert result.status is RepeatabilityStatus.STABLE
    assert len(result.outcome_fingerprints) == 1
