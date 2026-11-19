"""Idempotent fixture preparation and precondition checks."""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path

from evidence_handoff.collector.bundles import _atomic_write_json, _is_under, _read_complete_json
from evidence_handoff.collector.models import AdapterParameter, Scenario
from evidence_handoff.collector.scenarios import scenario_sha256
from evidence_handoff.ledger.canonical import canonical_json

from .common import HostError


def prepare_fixtures(
    *,
    capture_root: Path,
    scenario: Scenario,
    bindings: tuple[AdapterParameter, ...],
    run_id: str,
) -> Path:
    """Materialize digest-bound fixture markers; refuse mismatched overwrites."""
    run_dir = capture_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    marker = run_dir / "fixture-marker.json"
    digest = scenario_sha256(scenario, bindings)
    payload = {
        "schema": "evidence-fixture-marker-v1",
        "complete": True,
        "scenario_id": scenario.scenario_id,
        "run_id": run_id,
        "scenario_sha256": digest,
        "fixture_adapter_id": scenario.fixture.adapter_id,
        "fixture_digest": hashlib.sha256(
            f"{scenario.fixture.adapter_id}:{digest}".encode()
        ).hexdigest(),
    }
    if marker.exists():
        try:
            existing = _read_complete_json(marker)
        except ValueError as exc:
            raise HostError(str(exc)) from None
        if existing != payload:
            raise HostError("immutable_mismatch")
        return marker
    _atomic_write_json(marker, payload)
    return marker


def _matches_precondition_record(path: Path, expected: bytes) -> bool:
    try:
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or getattr(metadata, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or metadata.st_size != len(expected)
        ):
            return False
        with path.open("rb") as existing:
            return existing.read(len(expected) + 1) == expected
    except OSError:
        return False


def run_preconditions(
    *,
    capture_root: Path,
    scenario: Scenario,
    run_id: str,
) -> tuple[str, ...]:
    """Record stable precondition codes; never launch a client or invent an outcome."""
    codes: list[str] = []
    run_dir = capture_root / run_id
    marker = run_dir / "fixture-marker.json"
    if not marker.is_file():
        codes.append("fixture_missing")
    else:
        try:
            _read_complete_json(marker)
        except ValueError:
            codes.append("fixture_incomplete")
        else:
            for item in scenario.preconditions:
                if item.adapter_id == "capture_root_ready":
                    if not capture_root.is_dir():
                        codes.append("capture_root_missing")
                    else:
                        codes.append("capture_root_ready")
                else:
                    codes.append("unknown_precondition")
    result_path = run_dir / "precondition-result.json"
    payload = {
        "schema": "evidence-precondition-result-v1",
        "complete": True,
        "run_id": run_id,
        "codes": codes,
    }
    try:
        if not _is_under(run_dir, capture_root):
            raise HostError("atomic_write_failed")
        if not _matches_precondition_record(result_path, canonical_json(payload)):
            _atomic_write_json(result_path, payload)
    except (OSError, ValueError):
        raise HostError("atomic_write_failed") from None
    if any(
        code.endswith("_missing")
        or code.endswith("_incomplete")
        or code == "unknown_precondition"
        for code in codes
    ):
        raise HostError(codes[-1] if codes else "precondition_failed")
    return tuple(codes)
