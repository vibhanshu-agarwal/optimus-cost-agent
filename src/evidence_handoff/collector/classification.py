"""Fail-closed four-value evidence classification."""

from __future__ import annotations

import re
from collections.abc import Sequence

from .models import (
    ClaimKind,
    ClassificationResult,
    EvidenceClaim,
    Outcome,
    RunContext,
)

CLASSIFICATION_SCHEMA = "evidence-classification-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_POSITIVE = "ok"
_FAILURE_CODES = frozenset({"collector_failure", "timeout", "ambiguous_multi_instance"})


def validate_claims(
    *,
    context: RunContext,
    claims: Sequence[EvidenceClaim],
    required_collectors: Sequence[str],
) -> tuple[str, ...]:
    """Return stable integrity/correlation reason codes; empty means structurally valid."""
    codes: list[str] = []
    seen: set[tuple[str, str, int, int]] = set()
    for claim in claims:
        if claim.scenario_id != context.scenario_id:
            codes.append("foreign_scenario_id")
        if claim.run_id != context.run_id:
            codes.append("foreign_run_id")
        if claim.ends_at_ns < claim.starts_at_ns:
            codes.append("clock_regression")
        if not claim.evidence_sha256 or any(
            not _SHA256_RE.fullmatch(item) for item in claim.evidence_sha256
        ):
            codes.append("bad_digest")
        key = (claim.claim_kind.value, claim.detector_id, claim.starts_at_ns, claim.ends_at_ns)
        if key in seen:
            codes.append("duplicate_claim")
        seen.add(key)
        if claim.reason_code in _FAILURE_CODES:
            codes.append(claim.reason_code)

    for collector_id in required_collectors:
        expected = f"integrity-{collector_id}"
        if not any(
            claim.claim_kind is ClaimKind.INTEGRITY_VALID
            and claim.detector_id == expected
            and claim.reason_code == _POSITIVE
            for claim in claims
        ):
            codes.append("missing_collector")

    # Preserve stable unique order.
    return tuple(dict.fromkeys(codes))


def classify(
    *,
    context: RunContext,
    raw_bundle_sha256: str,
    claims: Sequence[EvidenceClaim],
    required_collectors: Sequence[str],
    stability_interval_ns: int,
) -> ClassificationResult:
    """Reduce claims to exactly one outcome using the frozen precedence table."""
    if not _SHA256_RE.fullmatch(raw_bundle_sha256):
        return _result(
            context,
            raw_bundle_sha256=raw_bundle_sha256,
            claims=claims,
            outcome=Outcome.INDETERMINATE,
            reason_codes=("bad_digest",),
        )

    integrity_codes = validate_claims(
        context=context,
        claims=claims,
        required_collectors=required_collectors,
    )
    if integrity_codes:
        return _result(
            context,
            raw_bundle_sha256=raw_bundle_sha256,
            claims=claims,
            outcome=Outcome.INDETERMINATE,
            reason_codes=integrity_codes,
        )

    renders = _positive(claims, ClaimKind.RENDER_OBSERVED)
    crashes = _positive(claims, ClaimKind.CLIENT_CRASH_OBSERVED)
    completions = _positive(claims, ClaimKind.COMPLETION_OBSERVED)
    alives = _positive(claims, ClaimKind.CLIENT_ALIVE)
    windows = _positive(claims, ClaimKind.OBSERVATION_WINDOW_COMPLETE)

    reason_codes: list[str] = []

    # Anything that is not cleanly "crash strictly after render" is contradictory —
    # the exact complement of precedence-2's own ordering check.
    for render in renders:
        for crash in crashes:
            if not crash.starts_at_ns > render.ends_at_ns:
                reason_codes.append("contradictory_claims")

    if reason_codes:
        return _result(
            context,
            raw_bundle_sha256=raw_bundle_sha256,
            claims=claims,
            outcome=Outcome.INDETERMINATE,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
        )

    # Precedence 2: ordered render-then-crash (strictly later).
    for render in renders:
        for crash in crashes:
            if crash.starts_at_ns > render.ends_at_ns:
                return _result(
                    context,
                    raw_bundle_sha256=raw_bundle_sha256,
                    claims=claims,
                    outcome=Outcome.RENDERED_THEN_CRASHED,
                    reason_codes=(),
                )

    # Precedence 3: valid crash with no earlier render.
    for crash in crashes:
        if not any(render.ends_at_ns < crash.starts_at_ns for render in renders):
            return _result(
                context,
                raw_bundle_sha256=raw_bundle_sha256,
                claims=claims,
                outcome=Outcome.CLIENT_CRASHED,
                reason_codes=(),
            )

    # Precedence 4: rendered_stable only with full stability interval and no crash.
    if crashes:
        return _result(
            context,
            raw_bundle_sha256=raw_bundle_sha256,
            claims=claims,
            outcome=Outcome.INDETERMINATE,
            reason_codes=("contradictory_claims",),
        )

    if completions and renders and alives and windows:
        for window in windows:
            span = window.ends_at_ns - window.starts_at_ns
            if span < stability_interval_ns:
                reason_codes.append("incomplete_interval")
                continue
            if not any(
                render.starts_at_ns <= window.starts_at_ns
                and render.ends_at_ns <= window.ends_at_ns
                for render in renders
            ):
                continue
            if not any(alive.starts_at_ns >= window.ends_at_ns for alive in alives):
                continue
            if not any(completion.starts_at_ns <= window.ends_at_ns for completion in completions):
                continue
            return _result(
                context,
                raw_bundle_sha256=raw_bundle_sha256,
                claims=claims,
                outcome=Outcome.RENDERED_STABLE,
                reason_codes=(),
            )
        if "incomplete_interval" in reason_codes:
            return _result(
                context,
                raw_bundle_sha256=raw_bundle_sha256,
                claims=claims,
                outcome=Outcome.INDETERMINATE,
                reason_codes=tuple(dict.fromkeys(reason_codes)),
            )

    return _result(
        context,
        raw_bundle_sha256=raw_bundle_sha256,
        claims=claims,
        outcome=Outcome.INDETERMINATE,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
    )


def _positive(claims: Sequence[EvidenceClaim], kind: ClaimKind) -> tuple[EvidenceClaim, ...]:
    return tuple(
        claim
        for claim in claims
        if claim.claim_kind is kind and claim.reason_code == _POSITIVE
    )


def _result(
    context: RunContext,
    *,
    raw_bundle_sha256: str,
    claims: Sequence[EvidenceClaim],
    outcome: Outcome,
    reason_codes: tuple[str, ...],
) -> ClassificationResult:
    return ClassificationResult(
        schema=CLASSIFICATION_SCHEMA,
        scenario_id=context.scenario_id,
        run_id=context.run_id,
        outcome=outcome,
        claims=tuple(claims),
        reason_codes=reason_codes,
        raw_bundle_sha256=raw_bundle_sha256,
    )
