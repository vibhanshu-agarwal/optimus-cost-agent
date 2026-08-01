"""Host detectors: reduce normalized observations into portable claims."""

from __future__ import annotations

from collections.abc import Sequence

from evidence_handoff.collector.models import (
    ClaimKind,
    CollectionBatch,
    EvidenceClaim,
    Observation,
    RunContext,
)

from .common import HostError

_FAILURE_CODES = frozenset({"collector_failure", "timeout", "ambiguous_multi_instance"})
_CRASH_ROLES = frozenset({"zed_process_dump", "zed_panic_json"})


def detect_claims(
    *,
    context: RunContext,
    batches: Sequence[CollectionBatch],
    render_claim: EvidenceClaim | None = None,
) -> tuple[EvidenceClaim, ...]:
    """Emit integrity, completion, crash, and optional render claims only."""
    claims: list[EvidenceClaim] = []
    for batch in batches:
        claims.extend(_integrity_claims(context=context, batch=batch))
        claims.extend(_completion_claims(context=context, batch=batch))
        claims.extend(_crash_claims(context=context, batch=batch))
        # Screenshot transport never becomes a render claim here.
        for observation in batch.observations:
            if observation.observation_kind == "render_observed":
                raise HostError("render_claim_forbidden")
    if render_claim is not None:
        if render_claim.claim_kind is not ClaimKind.RENDER_OBSERVED:
            raise HostError("render_claim_forbidden")
        if render_claim.scenario_id != context.scenario_id or render_claim.run_id != context.run_id:
            raise HostError("foreign_run_id")
        claims.append(render_claim)
    return tuple(claims)


def _integrity_claims(*, context: RunContext, batch: CollectionBatch) -> tuple[EvidenceClaim, ...]:
    failure = next(
        (
            observation.reason_code
            for observation in batch.observations
            if observation.reason_code in _FAILURE_CODES
        ),
        None,
    )
    if failure is not None:
        return (
            EvidenceClaim(
                claim_kind=ClaimKind.INTEGRITY_VALID,
                scenario_id=context.scenario_id,
                run_id=context.run_id,
                detector_id=f"integrity-{batch.collector_id}",
                contract_version="v1",
                evidence_sha256=_digests(batch),
                starts_at_ns=_min_offset(batch.observations),
                ends_at_ns=_max_offset(batch.observations),
                reason_code=failure,
            ),
        )
    return (
        EvidenceClaim(
            claim_kind=ClaimKind.INTEGRITY_VALID,
            scenario_id=context.scenario_id,
            run_id=context.run_id,
            detector_id=f"integrity-{batch.collector_id}",
            contract_version="v1",
            evidence_sha256=_digests(batch),
            starts_at_ns=_min_offset(batch.observations),
            ends_at_ns=_max_offset(batch.observations),
            reason_code="ok",
        ),
    )


def _completion_claims(*, context: RunContext, batch: CollectionBatch) -> tuple[EvidenceClaim, ...]:
    if batch.collector_id != "acp_stream_collector":
        return ()
    events = [
        observation
        for observation in batch.observations
        if observation.observation_kind == "completion_event" and observation.reason_code is None
    ]
    if not events:
        return ()
    if len(events) != 1:
        raise HostError("completion_ambiguous")
    event = events[0]
    digest = event.artifact_sha256
    if digest is None:
        raise HostError("bad_digest")
    return (
        EvidenceClaim(
            claim_kind=ClaimKind.COMPLETION_OBSERVED,
            scenario_id=context.scenario_id,
            run_id=context.run_id,
            detector_id="completion_detector",
            contract_version="v1",
            evidence_sha256=(digest,),
            starts_at_ns=event.monotonic_offset_ns,
            ends_at_ns=event.monotonic_offset_ns,
            reason_code="ok",
        ),
    )


def _crash_claims(*, context: RunContext, batch: CollectionBatch) -> tuple[EvidenceClaim, ...]:
    if batch.collector_id != "zed_crash_collector":
        return ()
    crash_obs = [
        observation
        for observation in batch.observations
        if observation.artifact_role in _CRASH_ROLES and observation.reason_code is None
    ]
    if not crash_obs:
        return ()
    # Ambiguous multi-instance is fail-closed at collect; classify still refuses
    # multiple independent crash candidates in one batch.
    digests = tuple(
        observation.artifact_sha256
        for observation in crash_obs
        if observation.artifact_sha256 is not None
    )
    if len(digests) != len(crash_obs):
        raise HostError("bad_digest")
    if len(set(digests)) != len(digests):
        raise HostError("duplicate_claim")
    starts = min(item.monotonic_offset_ns for item in crash_obs)
    ends = max(item.monotonic_offset_ns for item in crash_obs)
    return (
        EvidenceClaim(
            claim_kind=ClaimKind.CLIENT_CRASH_OBSERVED,
            scenario_id=context.scenario_id,
            run_id=context.run_id,
            detector_id="crash_detector",
            contract_version="v1",
            evidence_sha256=digests,
            starts_at_ns=starts,
            ends_at_ns=ends,
            reason_code="ok",
        ),
    )


def _digests(batch: CollectionBatch) -> tuple[str, ...]:
    return tuple(artifact.sha256 for artifact in batch.artifacts)


def _min_offset(observations: Sequence[Observation]) -> int:
    if not observations:
        return 0
    return min(item.monotonic_offset_ns for item in observations)


def _max_offset(observations: Sequence[Observation]) -> int:
    if not observations:
        return 0
    return max(item.monotonic_offset_ns for item in observations)
