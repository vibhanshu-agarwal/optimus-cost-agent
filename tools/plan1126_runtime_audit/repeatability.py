"""Normalized repeatability fingerprints and disposition."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Sequence


class RepeatabilityStatus(StrEnum):
    STABLE = "STABLE"
    FLAKY = "FLAKY"
    HARNESS_INVALID = "HARNESS_INVALID"
    HARNESS_UNSTABLE = "HARNESS_UNSTABLE"


@dataclass(frozen=True, slots=True)
class RepeatabilityResult:
    status: RepeatabilityStatus
    outcome_fingerprints: tuple[str, ...]


def _fingerprint(outcome: Any) -> str:
    canonical = json.dumps(outcome, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def classify_repeatability(
    *, outcomes: Sequence[Any], harness_fingerprints: Sequence[str], provenance_fingerprints: Sequence[str],
    harness_behavior_unstable: Sequence[bool] = (),
) -> RepeatabilityResult:
    if not outcomes or len(outcomes) != len(harness_fingerprints) or len(outcomes) != len(provenance_fingerprints):
        return RepeatabilityResult(RepeatabilityStatus.HARNESS_INVALID, ())
    fingerprints = tuple(sorted({_fingerprint(outcome) for outcome in outcomes}))
    if len(set(harness_fingerprints)) != 1 or len(set(provenance_fingerprints)) != 1:
        return RepeatabilityResult(RepeatabilityStatus.HARNESS_INVALID, fingerprints)
    if harness_behavior_unstable:
        if len(harness_behavior_unstable) != len(outcomes):
            return RepeatabilityResult(RepeatabilityStatus.HARNESS_INVALID, fingerprints)
        if any(harness_behavior_unstable):
            return RepeatabilityResult(RepeatabilityStatus.HARNESS_UNSTABLE, fingerprints)
    status = RepeatabilityStatus.STABLE if len(fingerprints) == 1 else RepeatabilityStatus.FLAKY
    return RepeatabilityResult(status, fingerprints)
