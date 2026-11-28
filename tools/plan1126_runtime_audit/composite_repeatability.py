"""Validate sealed observations and classify repeatability without masking other evidence.

This module reads no files. Callers provide the two byte documents and retain
their own provenance. Evidence references describe approved inputs; they are
never opened or interpreted as instructions.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeGuard

INPUT_SCHEMA = "optimus-repeatability-input-v1"
MANIFEST_SCHEMA = "optimus-repeatability-manifest-v1"
HASH_FIELDS = (
    "artifact_digest", "provenance_fingerprint", "harness_fingerprint_before",
    "harness_fingerprint_after", "original_command_sha256",
)
IDENTITY_FIELDS = (*HASH_FIELDS, "measurement_generation", "command", "platform", "python")
OUTCOMES = frozenset({"PASS", "FAIL", "TIMEOUT", "ERROR"})
SUBJECTS = frozenset({"NONE", "HARNESS", "PRODUCT", "UNRESOLVED"})
REFERENCE_KINDS = frozenset({"PROVENANCE", "DECLARED_HARNESS_NODE_MATCH", "ACCEPTED_LEGACY_UNRESOLVED", "PRODUCT_ASSERTION", "DECISION"})
DIGEST = re.compile(r"[0-9a-f]{64}")
Fingerprint = tuple[tuple[str, str, str], ...]


class InputParseError(ValueError):
    """A document does not provide a usable JSON envelope."""


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    cohort: str | None = None
    observation_id: str | None = None
    field: str | None = None


@dataclass(frozen=True, slots=True)
class Observation:
    raw: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class CohortSpec:
    cohort: str
    expected_count: int
    expected_observations: Mapping[str, tuple[int, int]]
    identity: Mapping[str, str]
    assertions: Mapping[str, str]
    harness_nodes: frozenset[str]
    evidence_refs: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class Disposition:
    raw: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ParsedInput:
    observations: tuple[Observation, ...]
    specs: tuple[CohortSpec, ...]
    residual_dispositions: tuple[Disposition, ...]
    input_sha256: str
    manifest_sha256: str
    manifest: Mapping[str, object]
    diagnostics: tuple[ValidationIssue, ...]


@dataclass(frozen=True, slots=True)
class RowResult:
    observation: Observation
    observed_outcome: str | None
    subject: str
    fingerprint: Fingerprint
    diagnostics: tuple[ValidationIssue, ...]


@dataclass(frozen=True, slots=True)
class CohortResult:
    cohort: str
    input_validity: str
    counts: Mapping[str, int]
    harness_instability_observed: bool
    product_variability_observed: bool
    product_repeatability: str


@dataclass(frozen=True, slots=True)
class CompositeResult:
    rows: tuple[RowResult, ...]
    cohorts: tuple[CohortResult, ...]
    diagnostics: tuple[ValidationIssue, ...]
    counts: Mapping[str, int]
    input_validity: str
    harness_instability_observed: bool
    product_variability_observed: bool
    product_repeatability: str


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType({key: _freeze(item) for key, item in value.items()})


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return _freeze_mapping(value)
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _unique_object(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in items:
        if key in result:
            raise InputParseError("JSON object contains a duplicate key")
        result[key] = item
    return result


def _parse_float(raw: str) -> float:
    result = float(raw)
    if not math.isfinite(result):
        raise InputParseError("JSON contains a non-finite number")
    return result


def _load_document(payload: bytes, name: str) -> object:
    try:
        result = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_unique_object, parse_float=_parse_float, parse_constant=_parse_float,
        )
    except (ValueError, RecursionError) as exc:
        raise InputParseError(f"{name} is not strict UTF-8 JSON") from exc
    return result


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _hash(value: object) -> bool:
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def _integer(value: object, minimum: int) -> TypeGuard[int]:
    return type(value) is int and value >= minimum


def _listed(value: object, choices: frozenset[str] | set[str]) -> TypeGuard[str]:
    return isinstance(value, str) and value in choices


def _strings(value: object) -> TypeGuard[list[str] | tuple[str, ...]]:
    return isinstance(value, (list, tuple)) and all(_text(item) is not None for item in value)


def _mapping(value: object) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def _source_reference(value: object) -> bool:
    # A name or a stable URI, never a workstation path. It is never opened.
    path = _text(value)
    if path is None or "\\" in path or path.startswith("/") or re.match(r"^[a-zA-Z]:", path):
        return False
    return all(part != ".." for part in path.split("/"))


def _reference_kind(refs: Mapping[str, str], reference: str | None) -> str | None:
    return refs.get(reference) if reference is not None else None


def _parse_refs(raw: object, issues: list[ValidationIssue]) -> dict[str, str]:
    refs = {}
    for name, value in _mapping(raw).items():
        ref = _mapping(value)
        if _text(name) and _listed(ref.get("kind"), REFERENCE_KINDS) and _hash(ref.get("sha256")) and _source_reference(ref.get("path")):
            refs[name] = ref["kind"]
        else:
            issues.append(ValidationIssue("invalid_evidence_reference", field=name))
    return refs


def _parse_specs(manifest: dict, issues: list[ValidationIssue], refs: Mapping[str, str]) -> tuple[CohortSpec, ...]:
    raw_nodes = manifest.get("harness_node_allowlist")
    if not _strings(raw_nodes) or len(set(raw_nodes)) != len(raw_nodes):
        issues.append(ValidationIssue("invalid_harness_allowlist"))
        raw_nodes = []
    result = []
    seen_names = set()
    seen_ids = set()
    for entry in manifest["cohorts"]:
        spec = _mapping(entry)
        name = _text(spec.get("cohort"))
        if not name or name in seen_names:
            issues.append(ValidationIssue("invalid_or_duplicate_cohort_spec", cohort=name))
            continue
        seen_names.add(name)
        items = _mapping(spec.get("expected_observations"))
        identity = _mapping(spec.get("identity"))
        assertions = _mapping(spec.get("assertions"))
        count = spec.get("expected_count")
        usable = (
            _integer(count, 1)
            and count == len(items)
            and all(key in identity and _text(identity[key]) for key in IDENTITY_FIELDS)
            and all(_hash(identity[key]) for key in HASH_FIELDS)
            and identity["harness_fingerprint_before"] == identity["harness_fingerprint_after"]
            and isinstance(spec.get("assertions"), dict)
            and all(_text(key) and _text(value) for key, value in assertions.items())
        )
        expected: dict[str, tuple[int, int]] = {}
        for row_id, value in items.items():
            row = _mapping(value)
            index, revision = row.get("repeat_index"), row.get("checkpoint_revision")
            if not _text(row_id) or row_id in seen_ids or not _integer(index, 1) or not _integer(revision, 1):
                usable = False
                continue
            seen_ids.add(row_id)
            expected[row_id] = (index, revision)
        if not usable or not _integer(count, 1) or sorted(index for index, _ in expected.values()) != list(range(1, len(items) + 1)):
            issues.append(ValidationIssue("invalid_cohort_declarations", cohort=name))
            continue
        result.append(CohortSpec(
            name, count, MappingProxyType(expected),
            MappingProxyType({key: identity[key] for key in IDENTITY_FIELDS}),
            MappingProxyType(dict(assertions)), frozenset(raw_nodes), MappingProxyType(dict(refs)),
        ))
    return tuple(result)


def _parse_dispositions(raw: Sequence, refs: Mapping[str, str], issues: list[ValidationIssue]) -> tuple[Disposition, ...]:
    result = []
    seen = set()
    for value in raw:
        item = _mapping(value)
        name = _text(item.get("id"))
        reference = _text(item.get("decision_source_ref"))
        if (
            name is None or name in seen or not _text(item.get("preserved_verdict"))
            or not _listed(item.get("state"), {"PROPOSED", "ACCEPTED"})
            or not _text(item.get("decision_text")) or not _integer(item.get("owning_issue"), 1)
            or _reference_kind(refs, reference) != "DECISION"
        ):
            issues.append(ValidationIssue("invalid_disposition", observation_id=name))
        seen.add(name)
        result.append(Disposition(_freeze_mapping(dict(item) if isinstance(value, dict) else {"unreadable_disposition": value})))
    return tuple(result)


def parse_input(payload: bytes, manifest: bytes) -> ParsedInput:
    """Decode two documents. Preserve readable rows and record semantic invalidity."""
    raw, declared = _load_document(payload, "input"), _load_document(manifest, "manifest")
    if (
        not isinstance(declared, dict)
        or declared.get("schema") != MANIFEST_SCHEMA
        or not isinstance(declared.get("cohorts"), list)
        or not isinstance(declared.get("evidence_refs"), dict)
        or not isinstance(declared.get("residual_dispositions"), list)
    ):
        raise InputParseError("manifest does not use the supported envelope")
    envelope = _mapping(raw)
    observations = envelope.get("observations")
    issues = []
    if not isinstance(observations, list):
        issues.append(ValidationIssue("missing_observations_array"))
        observations = []
    input_hash = hashlib.sha256(payload).hexdigest()
    if envelope.get("schema") != INPUT_SCHEMA:
        issues.append(ValidationIssue("invalid_input_schema"))
    if declared.get("input_sha256") != input_hash:
        issues.append(ValidationIssue("input_digest_mismatch"))
    if not _hash(declared.get("checkpoint_sha256")):
        issues.append(ValidationIssue("invalid_checkpoint_digest"))
    for field in ("selection", "transformation", "witness"):
        if not _text(declared.get(field)):
            issues.append(ValidationIssue("invalid_manifest_provenance", field=field))
    refs = _parse_refs(declared["evidence_refs"], issues)
    specs = _parse_specs(declared, issues, refs)
    dispositions = _parse_dispositions(declared["residual_dispositions"], refs, issues)
    return ParsedInput(
        tuple(Observation(_freeze_mapping(row if isinstance(row, dict) else {"unreadable_observation": row})) for row in observations),
        specs, dispositions, input_hash, hashlib.sha256(manifest).hexdigest(), _freeze_mapping(declared), tuple(issues),
    )


def _outcome_issues(outcome: Mapping) -> list[str]:
    invalid = []
    status = outcome.get("status")
    code = outcome.get("returncode")
    counts = outcome.get("counts")
    if not _listed(status, OUTCOMES):
        invalid.append("outcome.status")
    if "returncode" not in outcome or (
        code is not None if status == "TIMEOUT" else type(code) is not int or ((code == 0) != (status == "PASS"))
    ):
        invalid.append("outcome.returncode")
    if not isinstance(counts, Mapping) or any(not _integer(value, 0) for value in _mapping(counts).values()):
        invalid.append("outcome.counts")
    elif status == "PASS" and any(counts.get(key, 0) > 0 for key in ("failed", "error", "errors")):
        invalid.append("outcome.counts")
    elif status == "FAIL" and counts.get("failed") == 0:
        invalid.append("outcome.counts")
    for field in ("stdout_sha256", "stderr_sha256"):
        if outcome.get(field) is not None and not _hash(outcome[field]):
            invalid.append(f"outcome.{field}")
    if outcome.get("last_test_nodeid") is not None and not _text(outcome["last_test_nodeid"]):
        invalid.append("outcome.last_test_nodeid")
    if outcome.get("timeout_output_truncated") is not None and type(outcome["timeout_output_truncated"]) is not bool:
        invalid.append("outcome.timeout_output_truncated")
    timeout_subject = outcome.get("timeout_subject")
    if timeout_subject is not None and (status != "TIMEOUT" or not _listed(timeout_subject, SUBJECTS)):
        invalid.append("outcome.timeout_subject")
    return invalid


def _product_fingerprint(raw: object, spec: CohortSpec) -> Fingerprint | None:
    if not isinstance(raw, tuple):
        return None
    items: list[tuple[str, str, str]] = []
    seen = set()
    for entry in raw:
        assertion = _mapping(entry)
        name = _text(assertion.get("assertion_id"))
        key = _text(assertion.get("comparison_key"))
        ref = _text(assertion.get("evidence_ref"))
        result = assertion.get("result")
        if (
            name is None or name in seen or key is None or spec.assertions.get(name) != key
            or _reference_kind(spec.evidence_refs, ref) != "PRODUCT_ASSERTION" or not _listed(result, {"PASS", "FAIL"})
        ):
            return None
        seen.add(name)
        items.append((key, name, result))
    if seen and seen != set(spec.assertions):
        return None
    return tuple(sorted(items))


def _attribution(raw: Mapping, spec: CohortSpec, outcome: Mapping, fingerprint: Fingerprint) -> str | None:
    claim = _mapping(raw.get("attribution"))
    kind = claim.get("evidence_kind")
    reference = _text(claim.get("evidence_ref"))
    claimed = claim.get("subject")
    status = outcome.get("status")
    if not _text(claim.get("rationale")) or not _listed(claimed, SUBJECTS):
        return None
    if kind == "NONE" and reference is None and not fingerprint:
        expected = "NONE" if status == "PASS" else "UNRESOLVED"
    elif kind == "UNATTRIBUTED_OUTCOME" and reference is None and not fingerprint and status != "PASS":
        expected = "UNRESOLVED"
    elif kind == "ACCEPTED_LEGACY_UNRESOLVED" and (
        _reference_kind(spec.evidence_refs, reference) == kind and outcome.get("timeout_subject") == "UNRESOLVED" and not fingerprint
    ):
        expected = "UNRESOLVED"
    elif kind == "DECLARED_HARNESS_NODE_MATCH" and (
        _reference_kind(spec.evidence_refs, reference) == kind and outcome.get("timeout_subject") == "HARNESS"
        and _text(outcome.get("last_test_nodeid")) in spec.harness_nodes and not fingerprint
    ):
        expected = "HARNESS"
    elif kind == "PRODUCT_ASSERTION" and _reference_kind(spec.evidence_refs, reference) == kind and fingerprint:
        expected = "PRODUCT" if any(result == "FAIL" for _, _, result in fingerprint) else (
            "NONE" if status == "PASS" else "UNRESOLVED"
        )
    else:
        return None
    return expected if claimed == expected else None


def _classify_row(observation: Observation, spec: CohortSpec | None, duplicate: bool) -> RowResult:
    raw = observation.raw
    name = _text(raw.get("cohort"))
    row_id = _text(raw.get("observation_id"))
    outcome = _mapping(raw.get("outcome"))
    observed = _text(outcome.get("status"))
    diagnostics = [
        ValidationIssue("invalid_field", name, row_id, field) for field in _outcome_issues(outcome)
    ]
    if duplicate:
        diagnostics.append(ValidationIssue("duplicate_observation", name, row_id))
    subject: str | None = None
    fingerprint: Fingerprint = ()
    if spec is None:
        diagnostics.append(ValidationIssue("undeclared_cohort", name, row_id))
    else:
        expected = spec.expected_observations.get(row_id) if row_id is not None else None
        index, revision = raw.get("repeat_index"), raw.get("checkpoint_revision")
        if expected is None:
            diagnostics.append(ValidationIssue("unexpected_observation", name, row_id))
        if not _integer(index, 1) or not _integer(revision, 1) or expected != (index, revision):
            diagnostics.append(ValidationIssue("observation_identity_mismatch", name, row_id, "repeat_index/checkpoint_revision"))
        for field, wanted in spec.identity.items():
            if raw.get(field) != wanted:
                diagnostics.append(ValidationIssue("observation_identity_mismatch", name, row_id, field))
        duration = raw.get("duration_ms")
        if not isinstance(duration, (float, int)) or type(duration) is bool or duration < 0 or (
            isinstance(duration, float) and not math.isfinite(duration)
        ):
            diagnostics.append(ValidationIssue("invalid_field", name, row_id, "duration_ms"))
        for field in ("omitted_fields", "limitations", "provenance_refs"):
            if not _strings(raw.get(field)):
                diagnostics.append(ValidationIssue("invalid_field", name, row_id, field))
        prov = raw.get("provenance_refs")
        if _strings(prov) and (not prov or any(spec.evidence_refs.get(ref) != "PROVENANCE" for ref in prov)):
            diagnostics.append(ValidationIssue("unbound_provenance", name, row_id, "provenance_refs"))
        product = _product_fingerprint(raw.get("product_evidence", ()), spec)
        if product is None:
            diagnostics.append(ValidationIssue("invalid_product_evidence", name, row_id))
        else:
            fingerprint = product
        subject = _attribution(raw, spec, outcome, fingerprint)
        if subject is None:
            diagnostics.append(ValidationIssue("invalid_attribution", name, row_id))
    if diagnostics:
        return RowResult(observation, observed, "NONE" if observed == "PASS" else "UNRESOLVED", (), tuple(diagnostics))
    return RowResult(observation, observed, subject or "UNRESOLVED", fingerprint, ())


def _count_rows(rows: Sequence[RowResult]) -> Mapping[str, int]:
    counts = Counter(row.observed_outcome for row in rows)
    subjects = Counter(row.subject for row in rows)
    return MappingProxyType({
        **{name.lower(): counts[name] for name in sorted(OUTCOMES)},
        **{f"{name.lower()}_count": subjects[name] for name in sorted(SUBJECTS)},
        "observations": len(rows),
    })


def _cohort_result(name: str, rows: Sequence[RowResult], valid: bool) -> CohortResult:
    fingerprints = [row.fingerprint for row in rows if row.fingerprint and row.subject in {"PRODUCT", "NONE"}]
    variety = len(set(fingerprints)) > 1
    harness = any(row.subject == "HARNESS" for row in rows)
    stable = len(fingerprints) >= 2 and len(fingerprints) == len(rows)
    repeatability = "INDETERMINATE"
    if valid and variety:
        repeatability = "FLAKY"
    elif valid and stable:
        repeatability = "STABLE_OBSERVED"
    return CohortResult(name, "VALID" if valid else "INVALID", _count_rows(rows), harness, variety, repeatability)


def classify_composite(observations: Sequence[Observation], specs: Sequence[CohortSpec]) -> CompositeResult:
    """Keep outcomes, validation, harness facts and comparable product evidence separate."""
    by_name = {spec.cohort: spec for spec in specs}
    ids = Counter(_text(row.raw.get("observation_id")) for row in observations)
    indices = Counter(
        (_text(row.raw.get("cohort")), value)
        for row in observations if _integer(value := row.raw.get("repeat_index"), 1)
    )
    grouped = defaultdict(list)
    rows = []
    diagnostics: list[ValidationIssue] = []
    for observation in observations:
        name = _text(observation.raw.get("cohort"))
        index = observation.raw.get("repeat_index")
        repeat_collision = _integer(index, 1) and indices[(name, index)] > 1
        spec = by_name.get(name) if name is not None else None
        row = _classify_row(observation, spec, ids[_text(observation.raw.get("observation_id"))] > 1 or repeat_collision)
        rows.append(row)
        grouped[name].append(row)
        diagnostics.extend(row.diagnostics)

    cohorts = []
    for spec in specs:
        subset = grouped.pop(spec.cohort, [])
        actual = {_text(row.observation.raw.get("observation_id")) for row in subset}
        missing = spec.expected_observations.keys() - actual
        diagnostics.extend(ValidationIssue("missing_observation", spec.cohort, row_id) for row_id in sorted(missing))
        valid = not missing and len(subset) == spec.expected_count and not any(row.diagnostics for row in subset)
        cohorts.append(_cohort_result(spec.cohort, subset, valid))
    for name, subset in grouped.items():
        cohorts.append(_cohort_result(name or "(unidentified cohort)", subset, False))
    if not specs:
        diagnostics.append(ValidationIssue("no_declared_cohorts"))
    valid = bool(specs) and not diagnostics and all(cohort.input_validity == "VALID" for cohort in cohorts)
    variability = any(cohort.product_variability_observed for cohort in cohorts)
    repeatability = "INDETERMINATE"
    if valid and variability:
        repeatability = "FLAKY"
    elif valid and all(cohort.product_repeatability == "STABLE_OBSERVED" for cohort in cohorts):
        repeatability = "STABLE_OBSERVED"
    return CompositeResult(
        tuple(rows), tuple(cohorts), tuple(diagnostics), _count_rows(rows), "VALID" if valid else "INVALID",
        any(cohort.harness_instability_observed for cohort in cohorts), variability, repeatability,
    )
