"""The successor envelope: sealed historical records plus separately bound fresh ones.

Historical replay and fresh measurement are different claims, so they are different
records inside an explicitly versioned envelope. The historical records are carried
through **unchanged** -- same bytes, same v1 record schema, same immutable source
identities -- and each fresh measurement arrives as its own
:class:`~.model.CurrentMeasurementRecord` carrying the environment it actually ran in and
a resolvable reference to the inventory and observations it produced.

Nothing here re-derives a historical record, and nothing calls a current probe to satisfy
a historical constructor. Replay reads sealed observations; measurement runs in a fresh
child interpreter under a verified execution context and seals what it measured.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from .evidence_store import (
    RetainedEvidenceError,
    RetainedEvidenceReference,
    verify_retained_evidence,
    write_evidence_sidecar,
)
from .measurement import MeasurementSpecification, run_fresh_measurement
from .model import (
    AUDIT_ARTIFACT_SCHEMA_V2,
    CURRENT_MEASUREMENT_SCHEMA_VERSION,
    AuditArtifact,
    CurrentMeasurementRecord,
)
from .registry import entry_requirements, entry_source_paths
from .source import SourceTree, source_fingerprint

#: Fresh measurement entries and the subject each one records.
FRESH_ENTRIES: dict[str, str] = {
    "h5.shutdown_schedule": "Shutdown close-path schedule, measured on current source",
    "h9.connection_health": "Redis connection health normalization, measured on current source",
    "identity.echo_bound_modules": "Execution identity of the modules a verified child loaded",
    "s1.serving_custody": "S1 serving RedisRuntime custody, derived from current source and demonstrated wiring",
}

_HYPOTHESIS_IDS: dict[str, str] = {
    "h5.shutdown_schedule": "H5",
    "h9.connection_health": "H9",
    "identity.echo_bound_modules": "IDENTITY",
    "s1.serving_custody": "S1",
}


def entry_ruling(entry: str, inventory: Mapping[str, Any], observations: list[Mapping[str, Any]]) -> str:
    """The ruling a record carries, DERIVED from its retained evidence.

    Seam 2, checkpoint B: the S1 record's ruling states a classification, so it is a
    generated field with a contract -- built from the rows here and rebuilt from the
    retained sidecar at verification, where a mismatch is refused. (The H4 verifier
    lesson: a generated ruling that is never compared is a ruling anyone can edit.)
    Other entries keep the fixed measurement ruling.
    """
    if entry == "s1.serving_custody":
        from .serving_custody import derive_s1_ruling

        return derive_s1_ruling(tuple(observations), inventory)
    return _RULING

_RULING = (
    "Measured on current source in a fresh child interpreter under a verified execution "
    "context, with the inventory and observations retained beside this artifact. This is "
    "evidence about the measured revision only; it makes no claim about any historical "
    "baseline and does not assert that serving integration is complete."
)


def replay_sealed_artifact(path: str | Path) -> AuditArtifact:
    """Historical replay: read and validate sealed evidence, running NO current probe.

    Replay makes no new execution claim, so it needs neither the historical runtime nor a
    matching environment -- only the sealed bytes and their original validator.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return AuditArtifact.from_dict(payload)


@dataclass(frozen=True)
class MeasurementPlan:
    """One entry, the tree it measures, and the identity it is held to.

    Per entry, not per run: H5 and H9 discover their inventories from different path sets,
    so a single shared tree would have one of them measuring a contract discovered
    somewhere else.
    """

    entry: str
    source: SourceTree
    spec: MeasurementSpecification
    options: Mapping[str, Any]


def default_measurement_plan(
    *,
    repository_root: str | Path,
    entries: tuple[str, ...],
    options: Mapping[str, Any] | None = None,
) -> tuple[MeasurementPlan, ...]:
    """Build each entry's measured tree and specification from the working tree.

    The specification starts at the entry's own requirements -- runtime, bridge, probe
    implementation and installed dependency closure -- so the default path binds
    everything the entry executes rather than whatever the caller happened to name.
    """
    root = Path(repository_root).resolve()
    plans: list[MeasurementPlan] = []
    for entry in entries:
        paths = entry_source_paths(entry)
        source = SourceTree({path: (root / path).read_text(encoding="utf-8") for path in paths})
        requirements = entry_requirements(entry)
        plans.append(
            MeasurementPlan(
                entry=entry,
                source=source,
                spec=MeasurementSpecification(
                    paths=requirements.paths,
                    import_roots=(str(root / "src"), str(root)),
                    dependencies=requirements.dependencies,
                    source_fingerprint=source_fingerprint(source, source.paths()),
                ),
                options=dict(options or {}),
            )
        )
    return tuple(plans)


def measure_current(
    *,
    plans: tuple[MeasurementPlan, ...],
    repository_root: str | Path,
    evidence_directory: str | Path,
) -> tuple[CurrentMeasurementRecord, ...]:
    """Run each plan in a fresh child, seal what it measured, then prove the seal resolves.

    The verification below runs **after** the measuring process has exited, from the
    written bytes only. That ordering is the point: a check performed inside the process
    that produced the evidence proves only that the process agreed with itself.
    """
    evidence_directory = Path(evidence_directory)
    # PREFLIGHT, before anything is measured or written. Two plans for the same entry would
    # produce the same record id, and an artifact cannot carry two records with one id --
    # so the run is refused here rather than half-completed, leaving a directory whose
    # contents nobody can attribute.
    duplicates = sorted({plan.entry for plan in plans if [p.entry for p in plans].count(plan.entry) > 1})
    if duplicates:
        raise RetainedEvidenceError(
            f"these entries appear more than once in a single measurement run: {duplicates}; "
            "each entry yields one record id, so a run measures each at most once"
        )
    records: list[CurrentMeasurementRecord] = []
    for plan in plans:
        entry = plan.entry
        binding, result = run_fresh_measurement(
            source=plan.source,
            spec=plan.spec,
            entry=entry,
            options=plan.options,
            repository_root=repository_root,
        )
        record_id = f"CM-{entry.replace('.', '-')}"
        reference = write_evidence_sidecar(
            directory=evidence_directory,
            record_id=record_id,
            entry=entry,
            binding=binding.to_dict(),
            result=result,
        )
        verify_retained_evidence(
            record_id=record_id,
            measurement_binding=binding.to_dict(),
            observation_digest=reference.observation_digest,
            reference=reference,
            base_directory=evidence_directory,
        )
        records.append(
            CurrentMeasurementRecord(
                record_id=record_id,
                hypothesis_id=_HYPOTHESIS_IDS[entry],
                subject=FRESH_ENTRIES[entry],
                schema_version=CURRENT_MEASUREMENT_SCHEMA_VERSION,
                measurement_binding=binding.to_dict(),
                observation_digest=reference.observation_digest,
                retained_evidence=reference.to_dict(),
                ruling=entry_ruling(entry, result["inventory"], list(result["observations"])),
            )
        )
    return tuple(records)


def verify_current_records(
    artifact: AuditArtifact, evidence_directory: str | Path
) -> tuple[dict[str, Any], ...]:
    """Reconstruct every current record's evidence from disk and check its claims."""
    resolved: list[dict[str, Any]] = []
    for record in artifact.current_measurement_records:
        reference = RetainedEvidenceReference.from_dict(record.retained_evidence)
        payload = verify_retained_evidence(
            record_id=record.record_id,
            measurement_binding=record.measurement_binding,
            observation_digest=record.observation_digest,
            reference=reference,
            base_directory=evidence_directory,
        )
        # A generated ruling is re-derived from the retained rows and compared. The rows
        # are digest-bound; the ruling is not, so this is the only thing that stops an
        # edited verdict from standing over evidence that says otherwise.
        expected = entry_ruling(str(payload["entry"]), payload["inventory"], list(payload["observations"]))
        if record.ruling != expected:
            raise RetainedEvidenceError(
                f"{record.record_id}: the record's ruling does not match the ruling its retained "
                "evidence derives; a generated ruling must be rebuilt from the rows, not edited"
            )
        resolved.append(payload)
    return tuple(resolved)


def build_successor_artifact(
    sealed: AuditArtifact,
    current_records: tuple[CurrentMeasurementRecord, ...],
) -> AuditArtifact:
    """Carry sealed historical records unchanged and attach the fresh ones beside them."""
    if not current_records:
        raise ValueError("the successor envelope requires at least one current measurement record")
    return replace(
        sealed,
        schema_version=AUDIT_ARTIFACT_SCHEMA_V2,
        current_measurement_records=current_records,
    )
