"""Fail-closed four-value classification decision table."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_handoff.collector.models import (
    ClaimKind,
    EvidenceClaim,
    Outcome,
    RunContext,
)

_DIGEST = "a" * 64
_DIGEST_B = "b" * 64


def _classification():
    from evidence_handoff.collector import classification

    return classification


def _bundles():
    from evidence_handoff.collector import bundles

    return bundles


def _context(**overrides: object) -> RunContext:
    base = dict(
        schema="evidence-run-v1",
        scenario_id="zed-session",
        run_id="run-aaa",
        scenario_sha256=_DIGEST,
        capture_root=Path("/tmp/capture"),
        monotonic_origin_ns=1_000,
    )
    base.update(overrides)
    return RunContext(**base)  # type: ignore[arg-type]


def _claim(
    kind: ClaimKind,
    *,
    starts: int,
    ends: int | None = None,
    reason_code: str = "ok",
    detector_id: str = "detector",
    evidence: tuple[str, ...] = (_DIGEST,),
    run_id: str = "run-aaa",
    scenario_id: str = "zed-session",
) -> EvidenceClaim:
    return EvidenceClaim(
        claim_kind=kind,
        scenario_id=scenario_id,
        run_id=run_id,
        detector_id=detector_id,
        contract_version="v1",
        evidence_sha256=evidence,
        starts_at_ns=starts,
        ends_at_ns=ends if ends is not None else starts,
        reason_code=reason_code,
    )


def _integrity(collector_id: str) -> EvidenceClaim:
    return _claim(
        ClaimKind.INTEGRITY_VALID,
        starts=0,
        ends=0,
        detector_id=f"integrity-{collector_id}",
        reason_code="ok",
    )


def test_classify_module_exports_validate_and_classify() -> None:
    classification = _classification()
    assert callable(classification.validate_claims)
    assert callable(classification.classify)


@pytest.mark.parametrize(
    ("claims", "expected"),
    [
        (
            (
                _integrity("c1"),
                _claim(ClaimKind.COMPLETION_OBSERVED, starts=10),
                _claim(ClaimKind.RENDER_OBSERVED, starts=20),
                _claim(ClaimKind.CLIENT_ALIVE, starts=120),
                _claim(ClaimKind.OBSERVATION_WINDOW_COMPLETE, starts=20, ends=120),
            ),
            Outcome.RENDERED_STABLE,
        ),
        (
            (
                _integrity("c1"),
                _claim(ClaimKind.RENDER_OBSERVED, starts=10, ends=20),
                _claim(ClaimKind.CLIENT_CRASH_OBSERVED, starts=30),
            ),
            Outcome.RENDERED_THEN_CRASHED,
        ),
        (
            (
                _integrity("c1"),
                _claim(ClaimKind.CLIENT_CRASH_OBSERVED, starts=30),
            ),
            Outcome.CLIENT_CRASHED,
        ),
        (
            (
                _integrity("c1"),
                _claim(ClaimKind.COMPLETION_OBSERVED, starts=10),
            ),
            Outcome.INDETERMINATE,
        ),
    ],
)
def test_determinate_outcomes_and_indeterminate_fallback(
    claims: tuple[EvidenceClaim, ...], expected: Outcome
) -> None:
    classification = _classification()
    result = classification.classify(
        context=_context(),
        raw_bundle_sha256=_DIGEST,
        claims=claims,
        required_collectors=("c1",),
        stability_interval_ns=100,
    )
    assert result.outcome is expected
    assert result.schema == "evidence-classification-v1"
    assert result.raw_bundle_sha256 == _DIGEST


def test_render_then_crash_outranks_stable_ingredients() -> None:
    classification = _classification()
    claims = (
        _integrity("c1"),
        _claim(ClaimKind.COMPLETION_OBSERVED, starts=10),
        _claim(ClaimKind.RENDER_OBSERVED, starts=20, ends=30),
        _claim(ClaimKind.CLIENT_ALIVE, starts=200),
        _claim(ClaimKind.OBSERVATION_WINDOW_COMPLETE, starts=20, ends=200),
        _claim(ClaimKind.CLIENT_CRASH_OBSERVED, starts=40),
    )
    result = classification.classify(
        context=_context(),
        raw_bundle_sha256=_DIGEST,
        claims=claims,
        required_collectors=("c1",),
        stability_interval_ns=100,
    )
    assert result.outcome is Outcome.RENDERED_THEN_CRASHED


def test_crash_without_earlier_render_is_client_crashed() -> None:
    classification = _classification()
    # Crash alone — no render claim at all — is client_crashed, not a guess.
    claims = (
        _integrity("c1"),
        _claim(ClaimKind.CLIENT_CRASH_OBSERVED, starts=30),
    )
    result = classification.classify(
        context=_context(),
        raw_bundle_sha256=_DIGEST,
        claims=claims,
        required_collectors=("c1",),
        stability_interval_ns=100,
    )
    assert result.outcome is Outcome.CLIENT_CRASHED


def test_crash_entirely_before_render_is_contradictory_not_client_crashed() -> None:
    classification = _classification()
    # Crash@5 then render@[50,60] is physically impossible ordering — do not guess.
    claims = (
        _integrity("c1"),
        _claim(ClaimKind.CLIENT_CRASH_OBSERVED, starts=5),
        _claim(ClaimKind.RENDER_OBSERVED, starts=50, ends=60),
    )
    result = classification.classify(
        context=_context(),
        raw_bundle_sha256=_DIGEST,
        claims=claims,
        required_collectors=("c1",),
        stability_interval_ns=100,
    )
    assert result.outcome is Outcome.INDETERMINATE
    assert "contradictory_claims" in result.reason_codes


def test_early_impossible_crash_is_not_silently_dropped_when_later_crash_exists() -> None:
    classification = _classification()
    # Early crash@5 before render@[50,60], plus a later crash@200, must not
    # collapse to RENDERED_THEN_CRASHED by ignoring the impossible early crash.
    claims = (
        _integrity("c1"),
        _claim(ClaimKind.CLIENT_CRASH_OBSERVED, starts=5, detector_id="crash-early"),
        _claim(ClaimKind.RENDER_OBSERVED, starts=50, ends=60),
        _claim(ClaimKind.CLIENT_CRASH_OBSERVED, starts=200, detector_id="crash-late"),
    )
    result = classification.classify(
        context=_context(),
        raw_bundle_sha256=_DIGEST,
        claims=claims,
        required_collectors=("c1",),
        stability_interval_ns=100,
    )
    assert result.outcome is Outcome.INDETERMINATE
    assert "contradictory_claims" in result.reason_codes


def test_crash_overlapping_into_render_from_before_is_contradictory() -> None:
    classification = _classification()
    claims = (
        _integrity("c1"),
        _claim(ClaimKind.CLIENT_CRASH_OBSERVED, starts=40, ends=55),
        _claim(ClaimKind.RENDER_OBSERVED, starts=50, ends=60),
    )
    result = classification.classify(
        context=_context(),
        raw_bundle_sha256=_DIGEST,
        claims=claims,
        required_collectors=("c1",),
        stability_interval_ns=100,
    )
    assert result.outcome is Outcome.INDETERMINATE
    assert "contradictory_claims" in result.reason_codes


def test_crash_touching_render_start_is_contradictory() -> None:
    classification = _classification()
    claims = (
        _integrity("c1"),
        _claim(ClaimKind.CLIENT_CRASH_OBSERVED, starts=40, ends=50),
        _claim(ClaimKind.RENDER_OBSERVED, starts=50, ends=60),
    )
    result = classification.classify(
        context=_context(),
        raw_bundle_sha256=_DIGEST,
        claims=claims,
        required_collectors=("c1",),
        stability_interval_ns=100,
    )
    assert result.outcome is Outcome.INDETERMINATE
    assert "contradictory_claims" in result.reason_codes


def test_equal_timestamp_is_not_render_then_crash() -> None:
    classification = _classification()
    claims = (
        _integrity("c1"),
        _claim(ClaimKind.RENDER_OBSERVED, starts=10, ends=30),
        _claim(ClaimKind.CLIENT_CRASH_OBSERVED, starts=30),
    )
    result = classification.classify(
        context=_context(),
        raw_bundle_sha256=_DIGEST,
        claims=claims,
        required_collectors=("c1",),
        stability_interval_ns=100,
    )
    assert result.outcome is Outcome.INDETERMINATE


def test_boundary_stability_interval_must_be_complete() -> None:
    classification = _classification()
    # Window length 99 < required 100 → incomplete interval.
    claims = (
        _integrity("c1"),
        _claim(ClaimKind.COMPLETION_OBSERVED, starts=10),
        _claim(ClaimKind.RENDER_OBSERVED, starts=20),
        _claim(ClaimKind.CLIENT_ALIVE, starts=119),
        _claim(ClaimKind.OBSERVATION_WINDOW_COMPLETE, starts=20, ends=119),
    )
    result = classification.classify(
        context=_context(),
        raw_bundle_sha256=_DIGEST,
        claims=claims,
        required_collectors=("c1",),
        stability_interval_ns=100,
    )
    assert result.outcome is Outcome.INDETERMINATE
    assert "incomplete_interval" in result.reason_codes


def test_missing_completion_or_render_is_indeterminate() -> None:
    classification = _classification()
    no_completion = (
        _integrity("c1"),
        _claim(ClaimKind.RENDER_OBSERVED, starts=20),
        _claim(ClaimKind.CLIENT_ALIVE, starts=120),
        _claim(ClaimKind.OBSERVATION_WINDOW_COMPLETE, starts=20, ends=120),
    )
    no_render = (
        _integrity("c1"),
        _claim(ClaimKind.COMPLETION_OBSERVED, starts=10),
        _claim(ClaimKind.CLIENT_ALIVE, starts=120),
        _claim(ClaimKind.OBSERVATION_WINDOW_COMPLETE, starts=20, ends=120),
    )
    for claims in (no_completion, no_render):
        result = classification.classify(
            context=_context(),
            raw_bundle_sha256=_DIGEST,
            claims=claims,
            required_collectors=("c1",),
            stability_interval_ns=100,
        )
        assert result.outcome is Outcome.INDETERMINATE


def test_collector_failure_timeout_and_ambiguous_evidence_are_indeterminate() -> None:
    classification = _classification()
    for code in ("collector_failure", "timeout", "ambiguous_multi_instance"):
        claims = (
            _integrity("c1"),
            _claim(ClaimKind.RENDER_OBSERVED, starts=20, reason_code=code),
        )
        codes = classification.validate_claims(
            context=_context(),
            claims=claims,
            required_collectors=("c1",),
        )
        assert code in codes
        result = classification.classify(
            context=_context(),
            raw_bundle_sha256=_DIGEST,
            claims=claims,
            required_collectors=("c1",),
            stability_interval_ns=100,
        )
        assert result.outcome is Outcome.INDETERMINATE


def test_foreign_run_bad_digest_duplicate_and_clock_regression() -> None:
    classification = _classification()
    cases = [
        (_claim(ClaimKind.RENDER_OBSERVED, starts=1, run_id="other"), "foreign_run_id"),
        (_claim(ClaimKind.RENDER_OBSERVED, starts=1, evidence=("nope",)), "bad_digest"),
        (
            _claim(ClaimKind.RENDER_OBSERVED, starts=20, ends=10),
            "clock_regression",
        ),
    ]
    for claim, code in cases:
        codes = classification.validate_claims(
            context=_context(),
            claims=(_integrity("c1"), claim),
            required_collectors=("c1",),
        )
        assert code in codes

    dup = (
        _integrity("c1"),
        _claim(ClaimKind.RENDER_OBSERVED, starts=10, detector_id="r1"),
        _claim(ClaimKind.RENDER_OBSERVED, starts=10, detector_id="r1"),
    )
    codes = classification.validate_claims(
        context=_context(),
        claims=dup,
        required_collectors=("c1",),
    )
    assert "duplicate_claim" in codes


def test_contradictory_render_crash_ordering_is_indeterminate() -> None:
    classification = _classification()
    # Crash overlaps render interval — not strictly later, not crash-without-earlier-render.
    claims = (
        _integrity("c1"),
        _claim(ClaimKind.RENDER_OBSERVED, starts=10, ends=40),
        _claim(ClaimKind.CLIENT_CRASH_OBSERVED, starts=20, ends=30),
    )
    result = classification.classify(
        context=_context(),
        raw_bundle_sha256=_DIGEST,
        claims=claims,
        required_collectors=("c1",),
        stability_interval_ns=100,
    )
    assert result.outcome is Outcome.INDETERMINATE
    assert "contradictory_claims" in result.reason_codes


def test_missing_required_collector_integrity_is_indeterminate() -> None:
    classification = _classification()
    claims = (
        _claim(ClaimKind.COMPLETION_OBSERVED, starts=10),
        _claim(ClaimKind.RENDER_OBSERVED, starts=20),
        _claim(ClaimKind.CLIENT_ALIVE, starts=120),
        _claim(ClaimKind.OBSERVATION_WINDOW_COMPLETE, starts=20, ends=120),
    )
    result = classification.classify(
        context=_context(),
        raw_bundle_sha256=_DIGEST,
        claims=claims,
        required_collectors=("c1", "c2"),
        stability_interval_ns=100,
    )
    assert result.outcome is Outcome.INDETERMINATE
    assert "missing_collector" in result.reason_codes


def test_screenshot_success_alone_cannot_produce_positive_outcome() -> None:
    classification = _classification()
    # Capture/screenshot success is not a render claim.
    claims = (
        _integrity("c1"),
        _claim(
            ClaimKind.COMPLETION_OBSERVED,
            starts=10,
            reason_code="screenshot_captured",
        ),
    )
    result = classification.classify(
        context=_context(),
        raw_bundle_sha256=_DIGEST,
        claims=claims,
        required_collectors=("c1",),
        stability_interval_ns=100,
    )
    assert result.outcome is Outcome.INDETERMINATE


def test_absence_never_infers_crash_or_stable() -> None:
    classification = _classification()
    result = classification.classify(
        context=_context(),
        raw_bundle_sha256=_DIGEST,
        claims=(_integrity("c1"),),
        required_collectors=("c1",),
        stability_interval_ns=100,
    )
    assert result.outcome is Outcome.INDETERMINATE


def test_load_render_observation_builds_positive_render_claim(tmp_path: Path) -> None:
    bundles = _bundles()
    capture = (tmp_path / "capture").resolve()
    capture.mkdir()
    # Minimal run context via write_run_manifest helpers would need scenario; synthesize.
    context = _context(capture_root=capture)
    path = capture / "render-observation.json"
    path.write_text(
        json.dumps(
            {
                "schema": "evidence-render-observation-v1",
                "complete": True,
                "scenario_id": context.scenario_id,
                "run_id": context.run_id,
                "detector_id": "zed_render_detector",
                "artifact_sha256": _DIGEST_B,
                "starts_at_ns": 20,
                "ends_at_ns": 25,
                "assertion_provenance": "scenario-detector",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    claim = bundles.load_render_observation(
        context=context,
        path=path,
        allowed_detector_ids=("zed_render_detector",),
    )
    assert claim.claim_kind is ClaimKind.RENDER_OBSERVED
    assert claim.reason_code == "ok"
    assert claim.evidence_sha256 == (_DIGEST_B,)


def test_render_observation_rejects_approval_shaped_and_unknown_detector(
    tmp_path: Path,
) -> None:
    bundles = _bundles()
    capture = (tmp_path / "capture").resolve()
    capture.mkdir()
    context = _context(capture_root=capture)
    approval = capture / "approval.json"
    approval.write_text(
        json.dumps(
            {
                "schema": "evidence-render-observation-v1",
                "complete": True,
                "scenario_id": context.scenario_id,
                "run_id": context.run_id,
                "detector_id": "zed_render_detector",
                "artifact_sha256": _DIGEST_B,
                "starts_at_ns": 1,
                "ends_at_ns": 2,
                "assertion_provenance": "scenario-detector",
                "screenshot_approval": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non_executable_input|unknown_field"):
        bundles.load_render_observation(
            context=context,
            path=approval,
            allowed_detector_ids=("zed_render_detector",),
        )

    unknown = capture / "unknown.json"
    unknown.write_text(
        json.dumps(
            {
                "schema": "evidence-render-observation-v1",
                "complete": True,
                "scenario_id": context.scenario_id,
                "run_id": context.run_id,
                "detector_id": "not-allowlisted",
                "artifact_sha256": _DIGEST_B,
                "starts_at_ns": 1,
                "ends_at_ns": 2,
                "assertion_provenance": "scenario-detector",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown_detector"):
        bundles.load_render_observation(
            context=context,
            path=unknown,
            allowed_detector_ids=("zed_render_detector",),
        )


def test_screenshot_locator_without_render_observation_rejected(tmp_path: Path) -> None:
    bundles = _bundles()
    capture = (tmp_path / "capture").resolve()
    capture.mkdir()
    context = _context(capture_root=capture)
    path = capture / "screenshot-only.json"
    path.write_text(
        json.dumps(
            {
                "schema": "evidence-render-observation-v1",
                "complete": True,
                "scenario_id": context.scenario_id,
                "run_id": context.run_id,
                "detector_id": "zed_render_detector",
                "artifact_sha256": _DIGEST_B,
                "starts_at_ns": 1,
                "ends_at_ns": 2,
                "assertion_provenance": "screenshot-success",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="screenshot_without_render_observation"):
        bundles.load_render_observation(
            context=context,
            path=path,
            allowed_detector_ids=("zed_render_detector",),
        )


def test_provisional_result_round_trip(tmp_path: Path) -> None:
    bundles = _bundles()
    classification = _classification()
    capture = (tmp_path / "capture").resolve()
    capture.mkdir()
    context = _context(capture_root=capture)
    (capture / context.run_id).mkdir()
    claims = (
        _integrity("c1"),
        _claim(ClaimKind.CLIENT_CRASH_OBSERVED, starts=5),
    )
    result = classification.classify(
        context=context,
        raw_bundle_sha256=_DIGEST,
        claims=claims,
        required_collectors=("c1",),
        stability_interval_ns=100,
    )
    path = bundles.write_provisional_result(context=context, result=result)
    loaded = bundles.load_provisional_result(context=context, path=path)
    assert loaded == result
