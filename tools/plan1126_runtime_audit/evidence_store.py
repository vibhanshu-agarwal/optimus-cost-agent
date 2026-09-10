"""Retained evidence for fresh measurements: the observations, not just their digest.

An earlier version of the current-measurement record hashed the child's result and threw
the result away. What survived was a record naming a digest of something that no longer
existed anywhere -- unfalsifiable by construction, because nothing could be recomputed
from it and nothing could contradict it. The historical artifact's sealed observations
cannot stand in either: they are evidence about a different revision.

So a fresh measurement writes a **sealed sidecar** holding the complete inventory it
discovered and the complete observation rows it produced, and the record carries a
resolvable reference to that file: its location, the digest of its bytes, the canonical
digest of the inventory and the canonical digest of the observations. Verification is a
reconstruction, run after the measuring process has exited:

* the sidecar must be present -- a dangling reference fails rather than being tolerated;
* its bytes must hash to the recorded file digest;
* its observations must hash to the digest the record binds, and the record's own
  environment binding must be the one the sidecar was written under;
* every observation identifier must resolve to an identifier DERIVED from the retained
  inventory, so rows discovered from one tree cannot be filed against another.

Two things this module learned from counterexamples:

1. **A deterministic filename is an overwrite waiting to happen.** The location used to come
   from the record id alone and the writer called ``write_bytes`` unconditionally, so a
   second measurement into the same evidence directory replaced the first run's sidecar and
   the first record stopped verifying -- an ordinary output collision, no tampering needed.
   Sidecars are content-addressed and written atomically now: distinct results land at
   distinct paths, an identical result is an idempotent no-op, and a path that already holds
   different bytes is refused rather than replaced. Nothing here ever deletes or truncates.
2. **A declared identifier list is not an authority.** Verification used to accept the
   payload's own ``inventory_identifiers``, so an inventory listing ``a.py`` could declare
   ``b.py`` admissible and an observation for ``b.py`` verified against an inventory that
   never mentioned it. Identifiers are DERIVED from the retained inventory contents by
   kind; the retained list is kept only as a redundant copy that must agree exactly.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

CURRENT_EVIDENCE_SCHEMA_VERSION = "plan-11-26-current-evidence-v1"


class RetainedEvidenceError(RuntimeError):
    """Retained evidence is missing, altered, or does not match the record binding it."""


class EvidenceCollisionError(RetainedEvidenceError):
    """A write would have replaced sealed evidence that is already on disk.

    Refused rather than resolved: the earlier bytes are somebody's verified record, and the
    only safe way to disagree with them is to write somewhere else.
    """


def canonical_digest(value: Any) -> str:
    """A stable digest over JSON-canonical bytes, used for every retained-evidence claim."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


@dataclass(frozen=True)
class RetainedEvidenceReference:
    """A resolvable pointer from a record to the evidence it was derived from."""

    kind: str
    location: str
    file_digest: str
    inventory_digest: str
    observation_digest: str
    observation_count: int

    def __post_init__(self) -> None:
        if self.kind != "sidecar":
            raise ValueError("retained evidence kind must be 'sidecar'")
        if not self.location or Path(self.location).is_absolute() or ".." in Path(self.location).parts:
            raise ValueError("retained evidence location must be a relative path inside the evidence directory")
        for name in ("file_digest", "inventory_digest", "observation_digest"):
            if not _is_hex64(getattr(self, name)):
                raise ValueError(f"retained evidence {name} is invalid")
        if not isinstance(self.observation_count, int) or self.observation_count < 1:
            raise ValueError("retained evidence must record at least one observation")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "location": self.location,
            "file_digest": self.file_digest,
            "inventory_digest": self.inventory_digest,
            "observation_digest": self.observation_digest,
            "observation_count": self.observation_count,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RetainedEvidenceReference":
        expected = {
            "kind", "location", "file_digest", "inventory_digest",
            "observation_digest", "observation_count",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            raise ValueError("retained evidence reference fields do not match the canonical schema")
        return cls(
            kind=payload["kind"],
            location=payload["location"],
            file_digest=payload["file_digest"],
            inventory_digest=payload["inventory_digest"],
            observation_digest=payload["observation_digest"],
            observation_count=payload["observation_count"],
        )


def _inventory_block(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "inventory": result["inventory"],
        "inventory_identifiers": list(result["inventory_identifiers"]),
    }


#: The path whose discovered health probe the H9 measurement actually drives.
_H9_RUNTIME_PATH = "src/optimus/redis/runtime.py"


def _rows(inventory: Mapping[str, Any], field: str) -> list[Mapping[str, Any]]:
    rows = inventory.get(field)
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise RetainedEvidenceError(
            f"retained inventory field {field!r} is missing or malformed, so its admissible "
            "identifiers cannot be derived"
        )
    return rows


def derive_inventory_identifiers(
    inventory: Mapping[str, Any], binding: Mapping[str, Any] | None = None
) -> tuple[str, ...]:
    """Derive the admissible observation identifiers from the retained inventory itself.

    The point of derivation is that the answer comes from the inventory's PRIMITIVE
    contents -- its resource rows, its discovered sites -- rather than from a summary the
    same payload also carries. A summary can disagree with the thing it summarises; a
    derivation cannot.

    For H9 the scenario universe comes from the ``HealthScenario`` enum in code, never from
    the observed rows: letting observations define which observations are admissible is the
    same circularity in a different place.
    """
    if not isinstance(inventory, Mapping):
        raise RetainedEvidenceError("retained inventory is not an object")
    kind = inventory.get("kind")

    if kind == "bound-modules":
        paths = inventory.get("paths")
        if not isinstance(paths, list) or not all(isinstance(item, str) and item for item in paths):
            raise RetainedEvidenceError("retained bound-modules inventory has no usable path list")
        if binding is None:
            raise RetainedEvidenceError(
                "a bound-modules inventory cannot be derived without the binding it describes"
            )
        # Derived from the BINDING, not from the inventory. For this kind the inventory is
        # itself a list of the observation ids, so deriving from it would compare a list
        # with itself and admit whatever it happened to contain. The binding is verified
        # separately, which is what makes it an independent authority.
        bound = {row[0] for row in binding.get("module_origins") or () if row}
        if not bound:
            raise RetainedEvidenceError("the record binding names no executing module to derive from")
        if set(paths) != bound:
            raise RetainedEvidenceError(
                "the retained bound-modules inventory does not match the modules the binding names"
            )
        return tuple(sorted(bound))

    if kind == "shutdown-close-paths":
        identifiers = {
            row.get("close_path_id")
            for row in _rows(inventory, "resources")
            if row.get("schedule_applicable")
        }
        if not identifiers or not all(isinstance(item, str) and item for item in identifiers):
            raise RetainedEvidenceError(
                "retained shutdown inventory declares no applicable close path to measure"
            )
        return tuple(sorted(identifiers))

    if kind == "queue-and-health-sites":
        from .queue_policy import HealthScenario

        surface = "+".join(sorted(
            f"{row.get('path')}:{row.get('line')}:{row.get('symbol')}"
            for row in _rows(inventory, "sites")
            if row.get("site_kind") == "HEALTH_PROBE" and row.get("path") == _H9_RUNTIME_PATH
        ))
        if not surface:
            raise RetainedEvidenceError(
                "the retained queue inventory discovers no health probe in "
                f"{_H9_RUNTIME_PATH}, so no health observation can be attributed to it"
            )
        return tuple(sorted(f"{surface}|{scenario.value}" for scenario in HealthScenario))

    if kind == "serving-custody":
        from .serving_custody import CustodyScenario

        # Seam 2, checkpoint B. The universe is the enum in code: a row set can never
        # decide which rows are admissible, and a partial demonstration cannot verify as a
        # complete one -- every scenario must be present, demonstrated or not.
        if not isinstance(inventory.get("sites"), list) or "serving_shutdown_order" not in inventory:
            raise RetainedEvidenceError("retained serving-custody inventory is missing its sites or stage order")
        return tuple(sorted(scenario.value for scenario in CustodyScenario))

    raise RetainedEvidenceError(
        f"retained inventory kind {kind!r} has no derivation, so its observations cannot be "
        "checked against it"
    )


def build_evidence_payload(
    *, record_id: str, entry: str, binding: Mapping[str, Any], result: Mapping[str, Any]
) -> tuple[dict[str, Any], bytes, RetainedEvidenceReference]:
    """Build the sidecar payload, its canonical bytes and its reference -- WITHOUT writing.

    Separated from the write so a caller can preflight a whole output set before any of it
    reaches disk.
    """
    observations = list(result["observations"])
    if not observations:
        raise RetainedEvidenceError(
            f"{entry}: the measurement returned no observations, so there is no evidence to retain"
        )
    declared = list(result["inventory_identifiers"])
    derived = derive_inventory_identifiers(result["inventory"], binding)
    if tuple(sorted(set(declared))) != derived:
        raise RetainedEvidenceError(
            f"{entry}: the identifiers this measurement declares do not match the ones its own "
            "inventory yields, so the two describe different work"
        )
    payload = {
        "schema_version": CURRENT_EVIDENCE_SCHEMA_VERSION,
        "record_id": record_id,
        "entry": entry,
        "measurement_binding": dict(binding),
        **_inventory_block(result),
        "observations": observations,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    file_digest = hashlib.sha256(encoded).hexdigest()
    return payload, encoded, RetainedEvidenceReference(
        kind="sidecar",
        # CONTENT-ADDRESSED. A location derived from the record id alone is the same path on
        # every run, so a second measurement replaced the first one's sealed bytes and the
        # first record stopped verifying. Including the content digest means a different
        # result is a different file and an identical result is the same file.
        location=f"{record_id}.{file_digest[:32]}.evidence.json",
        file_digest=file_digest,
        inventory_digest=canonical_digest(_inventory_block(result)),
        observation_digest=canonical_digest(observations),
        observation_count=len(observations),
    )


def write_evidence_sidecar(
    *,
    directory: str | Path,
    record_id: str,
    entry: str,
    binding: Mapping[str, Any],
    result: Mapping[str, Any],
) -> RetainedEvidenceReference:
    """Seal the complete inventory and observations beside the artifact, and reference them.

    Immutable: an existing path holding the same bytes is reused, an existing path holding
    different bytes is refused, and the write is atomic so a crash cannot leave a truncated
    sidecar where a verified one used to be.
    """
    _payload, encoded, reference = build_evidence_payload(
        record_id=record_id, entry=entry, binding=binding, result=result
    )
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    destination = target / reference.location
    if destination.exists():
        if destination.read_bytes() == encoded:
            return reference  # idempotent: the same measurement sealed to the same bytes
        raise EvidenceCollisionError(
            f"{destination} already holds different sealed evidence; refusing to replace it"
        )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{reference.location}.", suffix=".tmp", dir=str(target)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return reference


def load_retained_evidence(
    reference: RetainedEvidenceReference, base_directory: str | Path
) -> dict[str, Any]:
    """Resolve a reference to its sidecar and prove the bytes are the ones referenced."""
    path = Path(base_directory) / reference.location
    if not path.is_file():
        raise RetainedEvidenceError(
            f"retained evidence {reference.location!r} is missing from {base_directory}; the record "
            "claims a digest over observations that cannot be produced"
        )
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference.file_digest:
        raise RetainedEvidenceError(
            f"retained evidence {reference.location!r} does not match its recorded file digest; "
            "the sealed observations have been altered since the measurement"
        )
    return json.loads(raw)


def verify_retained_evidence(
    *,
    record_id: str,
    measurement_binding: Mapping[str, Any],
    observation_digest: str,
    reference: RetainedEvidenceReference,
    base_directory: str | Path,
) -> dict[str, Any]:
    """Reconstruct a record's evidence and check every claim it makes about it."""
    payload = load_retained_evidence(reference, base_directory)
    if payload.get("schema_version") != CURRENT_EVIDENCE_SCHEMA_VERSION:
        raise RetainedEvidenceError("retained evidence declares an unknown schema version")
    if payload.get("record_id") != record_id:
        raise RetainedEvidenceError(
            "retained evidence belongs to a different measurement record than the one referencing it"
        )
    if payload.get("measurement_binding") != dict(measurement_binding):
        raise RetainedEvidenceError(
            "retained evidence was written under a different environment binding than the record claims"
        )
    observations = payload.get("observations")
    if not isinstance(observations, list) or not observations:
        raise RetainedEvidenceError("retained evidence contains no observations")
    if len(observations) != reference.observation_count:
        raise RetainedEvidenceError("retained evidence observation count does not match the reference")
    actual = canonical_digest(observations)
    if actual != reference.observation_digest or actual != observation_digest:
        raise RetainedEvidenceError(
            "retained observations do not hash to the digest the record binds; the record's claim "
            "cannot be reproduced from the evidence it points at"
        )
    if canonical_digest(_inventory_block(payload)) != reference.inventory_digest:
        raise RetainedEvidenceError("the retained inventory does not match the digest the record binds")
    # DERIVED from the retained inventory, not read off the payload's own summary of it. The
    # declared list is kept as a redundant copy and must agree exactly; when the two
    # disagree, the inventory wins and the evidence is refused.
    derived = derive_inventory_identifiers(payload.get("inventory"), measurement_binding)
    declared = payload.get("inventory_identifiers")
    if not isinstance(declared, list) or tuple(sorted(set(declared))) != derived:
        raise RetainedEvidenceError(
            "the identifier list retained beside this inventory does not match the identifiers "
            "the inventory itself yields; a declared list is not an authority over its own inventory"
        )
    identifiers = set(derived)
    _verify_inventory_identity(payload, measurement_binding)
    _verify_entry_identity(payload, record_id)
    for index, observation in enumerate(observations):
        identifier = observation.get("observation_id") if isinstance(observation, Mapping) else None
        if identifier is None:
            raise RetainedEvidenceError(f"retained observation {index} carries no observation_id")
        if identifier not in identifiers:
            raise RetainedEvidenceError(
                f"retained observation {identifier!r} is absent from the inventory this record binds; "
                "observations discovered from one tree cannot be filed against another"
            )
    # COVERAGE, not just membership. A subset check calls a sidecar holding one row of a
    # full schedule complete, which is the more useful lie: every identifier the inventory
    # yields has to appear, or the evidence is partial and says so.
    observed = {observation.get("observation_id") for observation in observations}
    unmeasured = sorted(identifiers - observed)
    if unmeasured:
        raise RetainedEvidenceError(
            f"the retained observations do not cover every identifier this inventory yields; "
            f"missing: {unmeasured[:5]}"
        )
    return payload


def _verify_entry_identity(payload: Mapping[str, Any], record_id: str) -> None:
    """The sidecar names the entry it came from; that name has to mean something.

    It was written and never read back, so a sidecar could claim any entry -- or an entry
    that does not exist -- and nothing noticed. The record id is derived from the entry, so
    the two must agree.
    """
    from .registry import measurement_entry_names

    entry = payload.get("entry")
    if entry not in measurement_entry_names():
        raise RetainedEvidenceError(
            f"retained evidence names {entry!r}, which is not an allowlisted measurement entry"
        )
    expected = f"CM-{entry.replace('.', '-')}"
    if record_id != expected:
        raise RetainedEvidenceError(
            f"retained evidence for {entry!r} is filed under {record_id!r} rather than {expected!r}"
        )


def _verify_inventory_identity(
    payload: Mapping[str, Any], measurement_binding: Mapping[str, Any]
) -> None:
    """Tie the retained inventory to the source the record was measured against.

    Where the inventory carries the fingerprint of the tree it was discovered from, that
    fingerprint must be the one the binding names. An inventory discovered from another
    revision describes another contract, however well-formed it is.
    """
    inventory = payload.get("inventory")
    if not isinstance(inventory, Mapping):
        raise RetainedEvidenceError("retained inventory is not an object")
    fingerprint = inventory.get("source_fingerprint")
    if fingerprint is None:
        return
    expected = measurement_binding.get("source_fingerprint")
    if fingerprint != expected:
        raise RetainedEvidenceError(
            "the retained inventory was discovered from a different tree than this record was "
            "measured against, so its identifiers describe a contract the record never covered"
        )
