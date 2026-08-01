"""Deterministic safe report rendering and body-free inspection."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from evidence_handoff.collector.bundles import _atomic_write_json
from evidence_handoff.collector.models import ClassificationResult, Outcome
from evidence_handoff.redaction.models import Disposition, RedactionGateResult

from .common import HostError, require_absolute_path

REPORT_SCHEMA = "evidence-report-v1"

_FORBIDDEN_REPORT_TOKENS = (
    "EVIDENCE_REDACTION_POLICY",
    "AuthorizedLaunch",
    "EvidenceRedactionHostContext",
    "OPTIMUS_API_KEY",
    "Traceback",
)


def _assert_report_payload_safe(payload: Mapping[str, Any]) -> None:
    """Refuse host/policy/credential tokens without a separate serialization sink."""
    stack: list[object] = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, Mapping):
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
        elif isinstance(item, str):
            for token in _FORBIDDEN_REPORT_TOKENS:
                if token in item:
                    raise HostError("report_unsafe_content")


def write_evidence_report(
    *,
    report_path: Path,
    scenario_id: str,
    run_id: str,
    provisional: ClassificationResult,
    gate_results: Sequence[RedactionGateResult],
) -> Path:
    absolute = require_absolute_path(report_path)
    if absolute.exists():
        raise HostError("report_already_exists")
    for result in gate_results:
        if result.disposition is not Disposition.PROMOTED:
            raise HostError("report_requires_promoted_artifacts")
        if result.artifact_locator is None:
            raise HostError("report_requires_promoted_artifacts")
        locator = result.artifact_locator
        if Path(locator).is_absolute() or "\\" in locator or ".." in Path(locator).parts:
            raise HostError("report_raw_path_rejected")
    if provisional.outcome not in {
        Outcome.RENDERED_STABLE,
        Outcome.RENDERED_THEN_CRASHED,
        Outcome.CLIENT_CRASHED,
        Outcome.INDETERMINATE,
    }:
        raise HostError("report_unknown_outcome")

    payload = {
        "schema": REPORT_SCHEMA,
        "complete": True,
        "scenario_id": scenario_id,
        "run_id": run_id,
        "outcome": provisional.outcome.value,
        "reason_codes": list(provisional.reason_codes),
        "raw_bundle_sha256": provisional.raw_bundle_sha256,
        "promoted_artifacts": [
            {
                "artifact_locator": result.artifact_locator,
                "manifest_locator": result.manifest_locator,
                "disposition": result.disposition.value,
                "reason_code": result.reason_code,
            }
            for result in gate_results
        ],
    }
    _assert_report_payload_safe(payload)
    try:
        _atomic_write_json(absolute, payload)
    except ValueError:
        raise HostError("atomic_write_failed") from None
    return absolute


def inspect_report(*, report_path: Path) -> dict[str, object]:
    absolute = require_absolute_path(report_path)
    if not absolute.is_file():
        raise HostError("report_missing")
    raw = absolute.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if payload.get("schema") != REPORT_SCHEMA:
        raise HostError("report_unknown_schema")
    digest = hashlib.sha256(raw).hexdigest()
    return {
        "schema": payload["schema"],
        "scenario_id": payload["scenario_id"],
        "run_id": payload["run_id"],
        "outcome": payload["outcome"],
        "report_sha256": digest,
        "promoted_count": len(payload.get("promoted_artifacts", [])),
        "artifact_locators": [
            item.get("artifact_locator") for item in payload.get("promoted_artifacts", [])
        ],
    }
