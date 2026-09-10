"""Every family's sealed observations, read once, replayed -- never re-measured.

Historical verification is replay: it re-states stored evidence and makes no new execution
claim. It was not. A reviewer replaced one probe -- H4's delivery schedule -- with a refusal,
ran the CLI's verifier over the committed artifact, and caught exactly one probe attempt:

    _verify_artifact -> build_h4_audit_artifact -> delivery_schedule_observations

H5 and H9 had already been converted one family at a time, each with its own reader and its
own builder keyword. Repeating that five more times would give the cumulative builders ten
keywords apiece and five more places for the next family to be forgotten. So there is one
carrier instead: :class:`SealedObservations` reads every family from the accepted artifact
and travels through the whole builder chain as a single argument.

What this module does NOT do is as important. It never runs a probe, and it never invents a
row: a family whose evidence is absent from the sealed artifact is REFUSED by name, because
the alternative -- quietly measuring today's code to fill the gap -- is exactly how a current
measurement becomes filed as historical evidence.

Static inventories, counts, canonical digests and derived summaries are still recomputed from
immutable source by the builders. Recomputing a summary from replayed rows is replay;
executing a probe to regenerate the rows is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class MissingSealedEvidence(ValueError):
    """A family's stored observations are absent, so its record cannot be replayed.

    Raised, never worked around. This is the prerequisite being reported rather than
    satisfied by measuring current code.
    """


#: family -> (hypothesis id, record field, row key inside that field, dotted row class).
#: The two row keys are a fact about the sealed bytes, not a choice: H3/H4/H5 store their
#: rows under "observations" and H7/H8/H9 under "rows". Reading them from one table is what
#: keeps the next family from inventing a third spelling.
_FAMILIES: dict[str, tuple[str, str, str, str, str]] = {
    "cancellation": ("H3", "schedule_observations", "observations", ".cancellation", "CancellationObservation"),
    "delivery": ("H4", "schedule_observations", "observations", ".model", "DeliveryObservation"),
    "shutdown": ("H5", "schedule_observations", "observations", ".shutdown", "ShutdownScheduleObservation"),
    "semantic": ("H7", "observations", "rows", ".semantic_errors", "SemanticObservation"),
    "schema": ("H8", "schema_observations", "rows", ".telemetry", "RuntimeEventSchemaObservation"),
    "redaction": ("H8", "redaction_observations", "rows", ".telemetry", "RuntimeRedactionObservation"),
    "correlation": ("H8", "correlation_observations", "rows", ".telemetry", "RuntimeCorrelationObservation"),
    "sink_failure": ("H8", "sink_failure_observations", "rows", ".telemetry", "RuntimeSinkFailureObservation"),
    "admission": ("H9", "admission_observations", "rows", ".queue_policy", "QueueAdmissionObservation"),
    "health": ("H9", "health_observations", "rows", ".queue_policy", "HealthObservation"),
}

FAMILY_NAMES: tuple[str, ...] = tuple(_FAMILIES)


def _row_class(module: str, name: str):
    """Resolved lazily so this module stays a leaf and cannot close an import cycle."""
    from importlib import import_module

    return getattr(import_module(module, __package__), name)


def replayed_family(sealed: Mapping[str, Any], family: str) -> tuple[Any, ...]:
    """Read one family's sealed rows and rebuild its typed observations. Runs NO probe."""
    try:
        hypothesis, field, key, module, class_name = _FAMILIES[family]
    except KeyError:
        raise MissingSealedEvidence(f"{family!r} is not a replayable observation family") from None

    records = [
        record
        for record in sealed.get("evidence_records", [])
        if record.get("hypothesis_id") == hypothesis
    ]
    if len(records) != 1:
        raise MissingSealedEvidence(
            f"sealed evidence must contain exactly one {hypothesis} record to replay {family!r}"
        )
    container = records[0].get(field)
    rows = container.get(key) if isinstance(container, Mapping) else None
    if not rows:
        raise MissingSealedEvidence(
            f"the sealed {hypothesis} record carries no {family!r} observations at "
            f"{field}.{key}; this prerequisite is missing and must not be satisfied by "
            "measuring current code"
        )
    row_class = _row_class(module, class_name)
    return tuple(row_class.from_dict(row) for row in rows)


@dataclass(frozen=True)
class SealedObservations:
    """Every family's stored rows, travelling together through the builder chain.

    One argument rather than ten keywords: the builders chain (H3 -> H4, H5 -> H3,
    H7 -> H5, H8 -> H7, H9 -> H8, H10 -> H9), so any cumulative artifact needs several
    families at once and every one of them is a place a probe could creep back in.
    """

    cancellation: tuple[Any, ...]
    delivery: tuple[Any, ...]
    shutdown: tuple[Any, ...]
    semantic: tuple[Any, ...]
    schema: tuple[Any, ...]
    redaction: tuple[Any, ...]
    correlation: tuple[Any, ...]
    sink_failure: tuple[Any, ...]
    admission: tuple[Any, ...]
    health: tuple[Any, ...]

    @classmethod
    def from_sealed(cls, sealed: Mapping[str, Any]) -> "SealedObservations":
        """Read every family from the accepted artifact, refusing any that is absent."""
        return cls(**{family: replayed_family(sealed, family) for family in _FAMILIES})

    def counts(self) -> dict[str, int]:
        """Row counts per family -- what a caller asserts on to show replay actually happened."""
        return {family: len(getattr(self, family)) for family in _FAMILIES}
