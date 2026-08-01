"""Digest-bound run manifests and raw bundles with atomic filesystem publication."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import (
    AdapterParameter,
    CapturedArtifact,
    ClaimKind,
    ClassificationResult,
    CollectionBatch,
    EvidenceClaim,
    Observation,
    Outcome,
    RunContext,
    Scenario,
    _canonicalize,
    adapter_parameter_to_canonical_dict,
    scenario_to_canonical_dict,
)
from .scenarios import _is_portable_absolute_path, scenario_sha256

RUN_SCHEMA = "evidence-run-v1"
RAW_BUNDLE_SCHEMA = "evidence-raw-bundle-v1"
RENDER_OBSERVATION_SCHEMA = "evidence-render-observation-v1"
PROVISIONAL_RESULT_SCHEMA = "evidence-classification-v1"
_RUN_MANIFEST_NAME = "run-manifest.json"
_RAW_BUNDLE_NAME = "raw-bundle.json"
_PROVISIONAL_NAME = "provisional-result.json"
_RELATIVE_LOCATOR_RE = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9._/-]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RENDER_KEYS = frozenset(
    {
        "schema",
        "complete",
        "scenario_id",
        "run_id",
        "detector_id",
        "artifact_sha256",
        "starts_at_ns",
        "ends_at_ns",
        "assertion_provenance",
    }
)
_FORBIDDEN_RENDER_KEYS = frozenset(
    {
        "screenshot_approval",
        "approval",
        "authorization",
        "gate_approval",
        "authority",
    }
)


def write_run_manifest(
    *,
    capture_root: Path,
    scenario: Scenario,
    bindings: Sequence[AdapterParameter],
    run_id: str | None = None,
    monotonic_origin_ns: int | None = None,
) -> RunContext:
    root = _require_absolute_dir(capture_root, create=True)
    digest = scenario_sha256(scenario, bindings)
    resolved_run_id = run_id or uuid.uuid4().hex
    origin = monotonic_origin_ns if monotonic_origin_ns is not None else time.monotonic_ns()
    run_dir = root / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / _RUN_MANIFEST_NAME
    payload = {
        "schema": RUN_SCHEMA,
        "complete": True,
        "scenario_id": scenario.scenario_id,
        "run_id": resolved_run_id,
        "scenario_sha256": digest,
        "monotonic_origin_ns": origin,
        "bindings": [adapter_parameter_to_canonical_dict(item) for item in bindings],
        "scenario": scenario_to_canonical_dict(scenario),
        "client_adapter_id": scenario.client.adapter_id,
        "fixture_adapter_id": scenario.fixture.adapter_id,
        "collection_adapter_ids": [item.adapter_id for item in scenario.collection],
        "detection_adapter_ids": [item.adapter_id for item in scenario.detection],
        "required_evidence": list(scenario.required_evidence),
    }
    context = RunContext(
        schema=RUN_SCHEMA,
        scenario_id=scenario.scenario_id,
        run_id=resolved_run_id,
        scenario_sha256=digest,
        capture_root=root,
        monotonic_origin_ns=origin,
    )
    if manifest_path.exists():
        existing = _read_complete_json(manifest_path)
        if existing != payload:
            raise ValueError("immutable_mismatch")
        return context
    _atomic_write_json(manifest_path, payload)
    return context


def write_raw_bundle(
    *,
    context: RunContext,
    batches: Sequence[CollectionBatch],
) -> Path:
    root = _require_absolute_dir(context.capture_root, create=False)
    run_dir = root / context.run_id
    if not run_dir.is_dir():
        raise ValueError("run_dir_missing")
    for batch in batches:
        for artifact in batch.artifacts:
            _validate_relative_locator(artifact.relative_locator)
    payload = {
        "schema": RAW_BUNDLE_SCHEMA,
        "complete": True,
        "scenario_id": context.scenario_id,
        "run_id": context.run_id,
        "scenario_sha256": context.scenario_sha256,
        "batches": [_batch_to_dict(batch) for batch in batches],
    }
    payload["bundle_sha256"] = _payload_sha256({key: value for key, value in payload.items() if key != "bundle_sha256"})
    path = run_dir / _RAW_BUNDLE_NAME
    if path.exists():
        existing = _read_complete_json(path)
        if existing != payload:
            raise ValueError("immutable_mismatch")
        return path
    _atomic_write_json(path, payload)
    return path


def load_verified_raw_bundle(
    *,
    context: RunContext,
    bundle_path: Path,
) -> tuple[CollectionBatch, ...]:
    path = bundle_path
    if not path.is_absolute():
        raise ValueError("relative_path_rejected")
    if "partial" in path.name.lower():
        raise ValueError("partial_stage")
    if not path.is_file():
        raise ValueError("bundle_missing")
    payload = _read_complete_json(path)
    if payload.get("schema") != RAW_BUNDLE_SCHEMA:
        raise ValueError("unknown_schema")
    if payload.get("complete") is not True:
        raise ValueError("partial_stage")
    if payload.get("run_id") != context.run_id:
        raise ValueError("foreign_run_id")
    if payload.get("scenario_id") != context.scenario_id:
        raise ValueError("foreign_scenario_id")
    if payload.get("scenario_sha256") != context.scenario_sha256:
        raise ValueError("digest_mismatch")
    expected = dict(payload)
    digest = expected.pop("bundle_sha256", None)
    if digest != _payload_sha256(expected):
        raise ValueError("digest_mismatch")
    batches = tuple(_batch_from_dict(item) for item in payload["batches"])
    return batches


def validate_custody_roots(
    *,
    capture_root: Path,
    other_roots: Sequence[Path],
    forbidden_roots: Sequence[Path],
) -> None:
    capture = _require_absolute_path(capture_root)
    others = tuple(_require_absolute_path(path) for path in other_roots)
    forbidden = tuple(_require_absolute_path(path) for path in forbidden_roots)
    for root in (capture, *others):
        for banned in forbidden:
            if _is_under(root, banned):
                raise ValueError("path_under_forbidden_root")
    all_roots = (capture, *others)
    for index, left in enumerate(all_roots):
        for right in all_roots[index + 1 :]:
            if _is_under(left, right) or _is_under(right, left):
                raise ValueError("path_overlap")


def load_render_observation(
    *,
    context: RunContext,
    path: Path,
    allowed_detector_ids: Sequence[str],
) -> EvidenceClaim:
    if not path.is_absolute():
        raise ValueError("relative_path_rejected")
    payload = _read_complete_json(path)
    for key in payload:
        if key in _FORBIDDEN_RENDER_KEYS:
            raise ValueError("non_executable_input")
    unknown = sorted(set(payload) - _RENDER_KEYS)
    if unknown:
        raise ValueError("unknown_field")
    if payload.get("schema") != RENDER_OBSERVATION_SCHEMA:
        raise ValueError("unknown_schema")
    if payload.get("scenario_id") != context.scenario_id:
        raise ValueError("foreign_scenario_id")
    if payload.get("run_id") != context.run_id:
        raise ValueError("foreign_run_id")
    detector_id = payload.get("detector_id")
    if not isinstance(detector_id, str) or detector_id not in allowed_detector_ids:
        raise ValueError("unknown_detector")
    artifact_sha256 = payload.get("artifact_sha256")
    if not isinstance(artifact_sha256, str) or not _SHA256_RE.fullmatch(artifact_sha256):
        raise ValueError("bad_digest")
    starts_at_ns = payload.get("starts_at_ns")
    ends_at_ns = payload.get("ends_at_ns")
    if not isinstance(starts_at_ns, int) or not isinstance(ends_at_ns, int):
        raise ValueError("ambiguous_type")
    if ends_at_ns < starts_at_ns:
        raise ValueError("clock_regression")
    provenance = payload.get("assertion_provenance")
    if provenance == "screenshot-success":
        raise ValueError("screenshot_without_render_observation")
    if provenance != "scenario-detector":
        raise ValueError("unknown_field")
    return EvidenceClaim(
        claim_kind=ClaimKind.RENDER_OBSERVED,
        scenario_id=context.scenario_id,
        run_id=context.run_id,
        detector_id=detector_id,
        contract_version="v1",
        evidence_sha256=(artifact_sha256,),
        starts_at_ns=starts_at_ns,
        ends_at_ns=ends_at_ns,
        reason_code="ok",
    )


def write_provisional_result(
    *,
    context: RunContext,
    result: ClassificationResult,
) -> Path:
    root = _require_absolute_dir(context.capture_root, create=False)
    run_dir = root / context.run_id
    if not run_dir.is_dir():
        raise ValueError("run_dir_missing")
    if result.scenario_id != context.scenario_id or result.run_id != context.run_id:
        raise ValueError("foreign_run_id")
    payload = {
        "schema": PROVISIONAL_RESULT_SCHEMA,
        "complete": True,
        "scenario_id": result.scenario_id,
        "run_id": result.run_id,
        "outcome": result.outcome.value,
        "reason_codes": list(result.reason_codes),
        "raw_bundle_sha256": result.raw_bundle_sha256,
        "claims": [_canonicalize(asdict(claim)) for claim in result.claims],
    }
    path = run_dir / _PROVISIONAL_NAME
    if path.exists():
        existing = _read_complete_json(path)
        if existing != payload:
            raise ValueError("immutable_mismatch")
        return path
    _atomic_write_json(path, payload)
    return path


def load_provisional_result(
    *,
    context: RunContext,
    path: Path,
) -> ClassificationResult:
    if not path.is_absolute():
        raise ValueError("relative_path_rejected")
    payload = _read_complete_json(path)
    if payload.get("schema") != PROVISIONAL_RESULT_SCHEMA:
        raise ValueError("unknown_schema")
    if payload.get("run_id") != context.run_id:
        raise ValueError("foreign_run_id")
    if payload.get("scenario_id") != context.scenario_id:
        raise ValueError("foreign_scenario_id")
    claims = tuple(_claim_from_dict(item) for item in payload["claims"])
    return ClassificationResult(
        schema=PROVISIONAL_RESULT_SCHEMA,
        scenario_id=str(payload["scenario_id"]),
        run_id=str(payload["run_id"]),
        outcome=Outcome(str(payload["outcome"])),
        claims=claims,
        reason_codes=tuple(str(item) for item in payload["reason_codes"]),
        raw_bundle_sha256=str(payload["raw_bundle_sha256"]),
    )


def _claim_from_dict(raw: Mapping[str, Any]) -> EvidenceClaim:
    return EvidenceClaim(
        claim_kind=ClaimKind(str(raw["claim_kind"])),
        scenario_id=str(raw["scenario_id"]),
        run_id=str(raw["run_id"]),
        detector_id=str(raw["detector_id"]),
        contract_version=str(raw["contract_version"]),
        evidence_sha256=tuple(str(item) for item in raw["evidence_sha256"]),
        starts_at_ns=int(raw["starts_at_ns"]),
        ends_at_ns=int(raw["ends_at_ns"]),
        reason_code=str(raw["reason_code"]),
    )


def _batch_to_dict(batch: CollectionBatch) -> dict[str, Any]:
    return _canonicalize(asdict(batch))


def _batch_from_dict(raw: Mapping[str, Any]) -> CollectionBatch:
    observations = tuple(
        Observation(
            schema=str(item["schema"]),
            scenario_id=str(item["scenario_id"]),
            run_id=str(item["run_id"]),
            collector_id=str(item["collector_id"]),
            sequence=int(item["sequence"]),
            monotonic_offset_ns=int(item["monotonic_offset_ns"]),
            observed_at=str(item["observed_at"]),
            observation_kind=str(item["observation_kind"]),
            correlation=tuple((str(key), str(value)) for key, value in item["correlation"]),
            artifact_role=None if item["artifact_role"] is None else str(item["artifact_role"]),
            artifact_sha256=None if item["artifact_sha256"] is None else str(item["artifact_sha256"]),
            reason_code=None if item["reason_code"] is None else str(item["reason_code"]),
        )
        for item in raw["observations"]
    )
    artifacts = tuple(
        CapturedArtifact(
            role=str(item["role"]),
            media_type=str(item["media_type"]),
            relative_locator=str(item["relative_locator"]),
            sha256=str(item["sha256"]),
            size_bytes=int(item["size_bytes"]),
        )
        for item in raw["artifacts"]
    )
    return CollectionBatch(
        collector_id=str(raw["collector_id"]),
        contract_version=str(raw["contract_version"]),
        observations=observations,
        artifacts=artifacts,
    )


def _validate_relative_locator(locator: str) -> None:
    if not locator or not _RELATIVE_LOCATOR_RE.fullmatch(locator):
        raise ValueError("unsafe_relative_locator")
    if "\\" in locator:
        raise ValueError("unsafe_relative_locator")


def _require_absolute_path(path: Path) -> Path:
    text = str(path)
    if not _is_portable_absolute_path(text):
        # Also accept OS-resolved absolute paths from real tmp dirs.
        if not path.is_absolute():
            raise ValueError("relative_path_rejected")
    return path


def _require_absolute_dir(path: Path, *, create: bool) -> Path:
    root = _require_absolute_path(path)
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if not root.exists() or not root.is_dir():
        raise ValueError("capture_root_missing")
    return root.resolve()


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.partial-{uuid.uuid4().hex}")
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        raise ValueError("atomic_write_failed") from None


def _read_complete_json(path: Path) -> dict[str, Any]:
    if "partial" in path.name.lower():
        raise ValueError("partial_stage")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise ValueError("invalid_json") from None
    if not isinstance(payload, dict):
        raise ValueError("invalid_json")
    if payload.get("complete") is not True:
        raise ValueError("partial_stage")
    return payload
