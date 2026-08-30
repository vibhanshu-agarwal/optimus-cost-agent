"""Thin, offline-first command line for Plan 11.26 audit artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.plan1126_runtime_audit.checkpoints import CheckpointStore  # noqa: E402
from tools.plan1126_runtime_audit.corpus import literal_seeds  # noqa: E402
from tools.plan1126_runtime_audit.inventory import discover_sites  # noqa: E402
from tools.plan1126_runtime_audit.model import AuditArtifact, PrerequisiteStatus  # noqa: E402
from tools.plan1126_runtime_audit.provenance import ExpectedArtifactIdentity, verify_running_artifact  # noqa: E402
from tools.plan1126_runtime_audit.render import render_markdown  # noqa: E402
from tools.plan1126_runtime_audit.repeatability import RepeatabilityStatus, classify_repeatability  # noqa: E402
from tools.plan1126_runtime_audit.source import GitCommitSource, SourceTree  # noqa: E402

_SCHEMA_PATH = ROOT / "tests" / "fixtures" / "plan1126_runtime_audit" / "audit-artifact.schema.json"
_AUTHORITY_KEYS = {
    "live-redis": "redis_mutation",
    "acpx": "acpx_live",
    "sdk": "sdk_or_conformance_harness_live",
    "zed": "zed_live",
}
_ZED_OUTCOMES = frozenset({"OBSERVED", "NOT_OBSERVED", "NOT_APPLICABLE", "INVALID"})
_ACCEPTED_MERGED_COMMIT = "5ea8f8f71548eb05a8562a10e98667e3d2061c4d"
_ACCEPTED_OVERLAY_COMMIT = "fac32284888850bacde93815265cbabe3afd4663"
_TASK_0_INTAKE_COMMIT = "55fcd1fe4fd2d10c17776946d8f19d8d5f420a67"
_TASK_1_REPORT = "reports/plan-11-26-prerequisite-intake.json"
_FROZEN_LITERAL_SEEDS = (0, 1, 42, 18446744073709551615)
# Trust roots are code-owned: accepting a successor requires separately reviewing
# its committed report, hashing its canonical JSON, and reviewing a code change
# that adds that digest here. No report, CLI flag, or environment value may extend it.
_ACCEPTED_AUTHORITY_DIGESTS = frozenset({"48bd260e636013291f0216cd7a30b6c6323a306a78226ed6e678e0062d30c08a"})


def _emit(status: str, reasons: Sequence[str] = ()) -> None:
    print(json.dumps({"reasons": list(reasons), "status": status}, sort_keys=True, separators=(",", ":")))


def _read_json(path: str | Path) -> Mapping[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON document must be an object")
    return payload


def _is_lower_hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(character in "0123456789abcdef" for character in value)


def _read_accepted_authority(
    path: str | Path, accepted_digests: frozenset[str],
) -> tuple[Mapping[str, Any] | None, str | None]:
    try:
        authority = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None, "authority_report_invalid"
    canonical = json.dumps(authority, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() not in accepted_digests:
        return None, "authority_report_unaccepted"
    review = authority.get("review_acceptance")
    if (
        authority.get("schema_version") != "plan-11-26-prerequisite-intake-v1"
        or authority.get("plan_id") != "11.26"
        or authority.get("source_task_0_commit") != _TASK_0_INTAKE_COMMIT
        or not isinstance(review, Mapping)
        or review.get("status") != "ACCEPTED"
        or not isinstance(authority.get("authority_decisions"), Mapping)
    ):
        return None, "authority_report_shape_invalid"
    return authority, None


def _authority_anchor(
    authority: Mapping[str, Any], command: str, *, artifact_required: bool = False,
) -> Mapping[str, Any] | None:
    anchors = authority.get("expected_execution_anchors")
    anchor = anchors.get(command) if isinstance(anchors, Mapping) else None
    expected_fields = {
        "expected_binding_commit", "expected_command", "expected_client_identity",
        *({"expected_artifact_sha256"} if artifact_required else set()),
    }
    if not isinstance(anchor, Mapping) or set(anchor) != expected_fields:
        return None
    client = anchor.get("expected_client_identity")
    if (
        anchor.get("expected_command") != command
        or not _is_lower_hex(anchor.get("expected_binding_commit"), 40)
        or not isinstance(client, Mapping)
        or set(client) != {"name", "version"}
        or any(not isinstance(client.get(field), str) or not client[field] for field in ("name", "version"))
        or (artifact_required and not _is_lower_hex(anchor.get("expected_artifact_sha256"), 64))
    ):
        return None
    return anchor


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _live_gate(
    args: argparse.Namespace,
    command: str,
    *,
    accepted_authority_digests: frozenset[str] = _ACCEPTED_AUTHORITY_DIGESTS,
) -> tuple[str, tuple[str, ...], Mapping[str, Any] | None]:
    if not args.authority_report:
        return "UNRUN", ("authority_report_required",), None
    authority, authority_error = _read_accepted_authority(args.authority_report, accepted_authority_digests)
    if authority_error is not None:
        return "INVALID", (authority_error,), None
    assert authority is not None
    decisions = authority.get("authority_decisions")
    if not isinstance(decisions, Mapping) or decisions.get(_AUTHORITY_KEYS[command]) != "AUTHORIZED":
        return "UNRUN", ("authority_not_granted",), None
    anchor = _authority_anchor(authority, command)
    if anchor is None:
        return "INVALID", ("authority_anchors_incomplete",), None
    if args.binding_commit is not None and args.binding_commit != anchor["expected_binding_commit"]:
        return "INVALID", ("binding_commit_authority_mismatch",), None
    if not args.provenance_manifest:
        return "UNRUN", ("provenance_manifest_required",), None
    try:
        manifest = _read_json(args.provenance_manifest)
    except (OSError, ValueError, json.JSONDecodeError):
        return "INVALID", ("provenance_manifest_invalid",), None
    expected_client = anchor["expected_client_identity"]
    result = verify_running_artifact(
        manifest,
        binding_commit=anchor["expected_binding_commit"],
        expected_identity=ExpectedArtifactIdentity(
            package_name="optimus-cost-agent",
            package_version="0.1.0",
            client_name=expected_client["name"],
            client_version=expected_client["version"],
        ),
    )
    if not result.valid:
        return "INVALID", result.reasons, None
    return "UNRUN", ("execution_owned_by_task_11",), result.provenance


def _add_live_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--authority-report")
    parser.add_argument("--provenance-manifest")
    parser.add_argument("--binding-commit")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inventory = subparsers.add_parser("inventory")
    inventory.add_argument("--repository", default=str(ROOT))
    inventory.add_argument("--commit")
    inventory.add_argument("--path-prefix", action="append", default=["src/"])
    inventory.add_argument("--output")
    offline = subparsers.add_parser("offline")
    offline.add_argument("--baseline-report")
    offline.add_argument("--prerequisite-report")
    offline.add_argument("--artifact")
    offline.add_argument("--checkpoint")
    offline.add_argument("--task5-group-repeats", type=int, default=0)
    offline.add_argument("--output")
    for command in ("live-redis", "acpx", "sdk"):
        _add_live_options(subparsers.add_parser(command))
    zed = subparsers.add_parser("zed")
    zed_subparsers = zed.add_subparsers(dest="zed_command", required=True)
    zed_record = zed_subparsers.add_parser("record")
    zed_record.add_argument("--authority-report", required=True)
    zed_record.add_argument("--scenario", required=True)
    zed_record.add_argument("--artifact", required=True)
    zed_record.add_argument("--observations", required=True)
    render = subparsers.add_parser("render")
    render.add_argument("--artifact", required=True)
    render.add_argument("--report", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--artifact", required=True)
    semantic = subparsers.add_parser("semantic")
    semantic.add_argument("--artifact", required=True)
    semantic.add_argument("--report", required=True)
    telemetry = subparsers.add_parser("telemetry")
    telemetry.add_argument("--artifact", required=True)
    telemetry.add_argument("--report", required=True)
    return parser


def _verify_artifact(path: str) -> AuditArtifact:
    payload = _read_json(path)
    schema = _read_json(_SCHEMA_PATH)
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        raise ValueError("; ".join(error.message for error in errors))
    artifact = AuditArtifact.from_dict(payload)
    h4_records = tuple(record for record in artifact.evidence_records if record.hypothesis_id == "H4")
    if h4_records:
        from tools.plan1126_runtime_audit.delivery_characterization import (
            H4_SOURCE_PATHS,
            build_h4_audit_artifact,
        )

        merged_source = GitCommitSource(artifact.merged_commit, repository=ROOT)
        overlay_source = GitCommitSource(artifact.overlay_commit, repository=ROOT)
        merged = SourceTree({path: merged_source.read_text(path) for path in H4_SOURCE_PATHS})
        overlay = SourceTree({path: overlay_source.read_text(path) for path in H4_SOURCE_PATHS})
        rebuilt = build_h4_audit_artifact(
            merged=merged,
            overlay=overlay,
            merged_commit=artifact.merged_commit,
            overlay_commit=artifact.overlay_commit,
        )
        mechanical_record_fields = {
            "record_id", "hypothesis_id", "subject", "baseline_scope", "baseline_anchor_commit",
            "overlay_commit", "binding_commit", "vocabulary_names", "symbol_citations",
            "discovered_sites", "contradiction_search", "schedule_observations",
            "commands", "content_free_evidence",
        }
        actual_record = h4_records[0].to_dict()
        expected_record = rebuilt.evidence_records[0].to_dict()
        if {
            field: actual_record[field] for field in mechanical_record_fields
        } != {
            field: expected_record[field] for field in mechanical_record_fields
        }:
            raise ValueError("H4 evidence record does not match immutable-source rebuild")
        mechanical_finding_fields = {
            "finding_id", "subject", "classification", "baseline_scope", "symbols", "evidence",
            "owner",
        }
        actual_findings = tuple({
            field: finding.to_dict()[field] for field in mechanical_finding_fields
        } for finding in artifact.findings if finding.finding_id.startswith("H4-"))
        expected_findings = tuple({
            field: finding.to_dict()[field] for field in mechanical_finding_fields
        } for finding in rebuilt.findings)
        if actual_findings != expected_findings:
            raise ValueError("H4 findings do not match immutable-source rebuild")
    h3_records = tuple(record for record in artifact.evidence_records if record.hypothesis_id == "H3")
    if h3_records:
        from tools.plan1126_runtime_audit.cancellation import (
            H3_SOURCE_PATHS,
            build_h3_audit_artifact,
        )
        from tools.plan1126_runtime_audit.delivery_characterization import H4_SOURCE_PATHS

        merged_source = GitCommitSource(artifact.merged_commit, repository=ROOT)
        overlay_source = GitCommitSource(artifact.overlay_commit, repository=ROOT)
        paths = tuple(sorted(set(H3_SOURCE_PATHS) | set(H4_SOURCE_PATHS)))
        merged = SourceTree({path: merged_source.read_text(path) for path in paths})
        overlay = SourceTree({path: overlay_source.read_text(path) for path in paths})
        rebuilt = build_h3_audit_artifact(
            merged=merged,
            overlay=overlay,
            merged_commit=artifact.merged_commit,
            overlay_commit=artifact.overlay_commit,
        )
        expected_h3 = next(record for record in rebuilt.evidence_records if record.hypothesis_id == "H3")
        actual_record = h3_records[0].to_dict()
        expected_record = expected_h3.to_dict()
        mechanical_record_fields = set(expected_record) - {"ruling", "reviewer_status"}
        if {
            field: actual_record[field] for field in mechanical_record_fields
        } != {
            field: expected_record[field] for field in mechanical_record_fields
        }:
            raise ValueError("H3 evidence record does not match immutable-source rebuild")
        actual_h3_findings = tuple(
            finding.to_dict()
            for finding in sorted(
                (item for item in artifact.findings if item.finding_id.startswith("H3-")),
                key=lambda item: item.finding_id,
            )
        )
        expected_h3_findings = tuple(
            finding.to_dict()
            for finding in sorted(
                (item for item in rebuilt.findings if item.finding_id.startswith("H3-")),
                key=lambda item: item.finding_id,
            )
        )
        if actual_h3_findings != expected_h3_findings:
            raise ValueError("H3 findings do not match immutable-source rebuild")
    h5_records = tuple(record for record in artifact.evidence_records if record.hypothesis_id == "H5")
    if h5_records:
        from tools.plan1126_runtime_audit.cancellation import H3_SOURCE_PATHS
        from tools.plan1126_runtime_audit.delivery_characterization import H4_SOURCE_PATHS
        from tools.plan1126_runtime_audit.shutdown import (
            H5_SOURCE_PATHS,
            _canonical_digest,
            _derived_shutdown_order,
            characterize_shutdown_inventory,
            discover_shutdown_inventory,
        )

        merged_source = GitCommitSource(artifact.merged_commit, repository=ROOT)
        overlay_source = GitCommitSource(artifact.overlay_commit, repository=ROOT)
        paths = tuple(sorted(set(H3_SOURCE_PATHS) | set(H4_SOURCE_PATHS) | set(H5_SOURCE_PATHS)))
        merged = SourceTree({path: merged_source.read_text(path) for path in paths})
        overlay = SourceTree({path: overlay_source.read_text(path) for path in paths})
        actual_record = h5_records[0].to_dict()
        shutdown_merged = SourceTree({path: merged.read_text(path) for path in H5_SOURCE_PATHS})
        shutdown_overlay = SourceTree({path: overlay.read_text(path) for path in H5_SOURCE_PATHS})
        inventory = discover_shutdown_inventory(shutdown_merged, overlay=shutdown_overlay)
        inventory = characterize_shutdown_inventory(
            inventory,
            h5_records[0].schedule_observations.observations,
        )
        expected_inventory = [item.to_dict() for item in inventory.close_sites]
        expected_resources = [item.to_dict() for item in inventory.resources]
        expected_order = {
            "merged": list(_derived_shutdown_order(shutdown_merged)),
            "overlay": list(_derived_shutdown_order(shutdown_overlay)),
        }
        if (
            actual_record["discovered_sites"] != expected_inventory
            or actual_record["resource_ownership"] != expected_resources
            or actual_record["close_path_count"] != inventory.close_path_count
            or actual_record["shutdown_order"] != expected_order
        ):
            raise ValueError("H5 evidence record does not match immutable-source rebuild")
        s1_digest = _canonical_digest({
            "ruling": actual_record["s1_redis_runtime_ruling"],
            "shutdown_order": actual_record["shutdown_order"],
        })
        h5_findings = {
            finding.finding_id: finding for finding in artifact.findings if finding.finding_id.startswith("H5-")
        }
        required_h5 = {"H5-S1-REDIS-RUNTIME-merged", "H5-S1-REDIS-RUNTIME-overlay"}
        observations = actual_record["schedule_observations"]["observations"]
        expected_dynamic: dict[str, tuple[str, str]] = {}
        double_close = [item for item in observations if item["close_outcome"] == "DOUBLE_CLOSE_OBSERVED"]
        if double_close:
            expected_dynamic["H5-REPEATED-CLOSE-UNDERLYING-merged"] = (
                "H5-DOUBLE-CLOSE-OBSERVATIONS", _canonical_digest(double_close),
            )
        slow_close = [item for item in observations if item["repeat_latency_class"] == "ABOVE_100MS"]
        if slow_close:
            expected_dynamic["H5-REPEAT-LATENCY-ABOVE-100MS-merged"] = (
                "H5-SLOW-CLOSE-OBSERVATIONS", _canonical_digest(slow_close),
            )
        error_close = [item for item in observations if item["close_outcome"] == "ERROR"]
        if error_close:
            expected_dynamic["H5-CLOSE-ERROR-merged"] = (
                "H5-CLOSE-ERROR-OBSERVATIONS", _canonical_digest(error_close),
            )
        if set(h5_findings) != required_h5 | set(expected_dynamic):
            raise ValueError("H5 S1 findings are incomplete")
        if any(h5_findings[finding_id].evidence[0].digest != s1_digest for finding_id in required_h5):
            raise ValueError("H5 S1 finding evidence does not match the source-derived ruling")
        for finding_id, (evidence_id, digest) in expected_dynamic.items():
            evidence = h5_findings[finding_id].evidence[0]
            if evidence.evidence_id != evidence_id or evidence.digest != digest:
                raise ValueError("H5 runtime finding evidence does not match stored observations")
    h7_records = tuple(record for record in artifact.evidence_records if record.hypothesis_id == "H7")
    h6_records = tuple(record for record in artifact.evidence_records if record.hypothesis_id == "H6")
    if h6_records or h7_records:
        from tools.plan1126_runtime_audit.semantic_errors import (
            H7_SOURCE_PATHS,
            _authority_record,
            _h7_findings,
            _semantic_record,
        )

        if len(h6_records) != 1 or len(h7_records) != 1:
            raise ValueError("H6 and H7 must be present exactly once")
        merged_source = GitCommitSource(artifact.merged_commit, repository=ROOT)
        semantic_source = SourceTree({path: merged_source.read_text(path) for path in H7_SOURCE_PATHS})
        expected_h6 = _authority_record(semantic_source, artifact.merged_commit, artifact.overlay_commit)
        expected_h7 = _semantic_record(semantic_source, artifact.merged_commit, artifact.overlay_commit)
        for actual, expected, label in (
            (h6_records[0].to_dict(), expected_h6.to_dict(), "H6"),
            (h7_records[0].to_dict(), expected_h7.to_dict(), "H7"),
        ):
            fields = set(expected) - {"ruling", "reviewer_status"}
            if {field: actual[field] for field in fields} != {field: expected[field] for field in fields}:
                raise ValueError(f"{label} evidence record does not match immutable-source rebuild")
        actual_findings = tuple(
            finding.to_dict()
            for finding in sorted(
                (item for item in artifact.findings if item.finding_id.startswith("H7-")),
                key=lambda item: item.finding_id,
            )
        )
        expected_findings = tuple(item.to_dict() for item in _h7_findings(expected_h7))
        if actual_findings != expected_findings:
            raise ValueError("H7 findings do not match immutable-source rebuild")
    h8_records = tuple(record for record in artifact.evidence_records if record.hypothesis_id == "H8")
    if h8_records:
        from tools.plan1126_runtime_audit.telemetry import (
            H8_SOURCE_PATHS,
            _h8_findings,
            _telemetry_record,
        )

        if len(h8_records) != 1:
            raise ValueError("H8 must be present exactly once")
        merged_source = GitCommitSource(artifact.merged_commit, repository=ROOT)
        telemetry_source = SourceTree({path: merged_source.read_text(path) for path in H8_SOURCE_PATHS})
        with tempfile.TemporaryDirectory(prefix="plan1126-h8-verify-") as workspace:
            expected_h8 = _telemetry_record(
                telemetry_source, artifact.merged_commit, artifact.overlay_commit, workspace,
            )
        actual = h8_records[0].to_dict()
        expected = expected_h8.to_dict()
        fields = set(expected) - {"ruling", "reviewer_status"}
        if {field: actual[field] for field in fields} != {field: expected[field] for field in fields}:
            raise ValueError("H8 evidence record does not match immutable-source rebuild")
        actual_findings = tuple(
            finding.to_dict()
            for finding in sorted(
                (item for item in artifact.findings if item.finding_id.startswith("H8-")),
                key=lambda item: item.finding_id,
            )
        )
        expected_findings = tuple(
            item.to_dict() for item in sorted(_h8_findings(expected_h8), key=lambda item: item.finding_id)
        )
        if actual_findings != expected_findings:
            raise ValueError("H8 findings do not match immutable-source rebuild")
    return artifact


def _run_semantic(args: argparse.Namespace) -> int:
    from tools.plan1126_runtime_audit.cancellation import H3_SOURCE_PATHS
    from tools.plan1126_runtime_audit.delivery_characterization import H4_SOURCE_PATHS
    from tools.plan1126_runtime_audit.semantic_errors import H7_SOURCE_PATHS, build_h7_audit_artifact
    from tools.plan1126_runtime_audit.shutdown import H5_SOURCE_PATHS

    merged_source = GitCommitSource(_ACCEPTED_MERGED_COMMIT, repository=ROOT)
    overlay_source = GitCommitSource(_ACCEPTED_OVERLAY_COMMIT, repository=ROOT)
    paths = tuple(sorted(set(H3_SOURCE_PATHS) | set(H4_SOURCE_PATHS) | set(H5_SOURCE_PATHS) | set(H7_SOURCE_PATHS)))
    merged = SourceTree({path: merged_source.read_text(path) for path in paths})
    overlay = SourceTree({path: overlay_source.read_text(path) for path in paths})
    artifact = build_h7_audit_artifact(
        merged=merged, overlay=overlay,
        merged_commit=merged_source.commit, overlay_commit=overlay_source.commit,
    )
    payload = artifact.to_dict()
    schema = _read_json(_SCHEMA_PATH)
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    if errors:
        raise ValueError("generated Task 7 artifact does not satisfy the canonical schema")
    _atomic_json(Path(args.artifact), payload)
    _write_text(Path(args.report), render_markdown(payload))
    _emit("COMPLETE")
    return 0


def _run_telemetry(args: argparse.Namespace) -> int:
    from tools.plan1126_runtime_audit.cancellation import H3_SOURCE_PATHS
    from tools.plan1126_runtime_audit.delivery_characterization import H4_SOURCE_PATHS
    from tools.plan1126_runtime_audit.semantic_errors import H7_SOURCE_PATHS
    from tools.plan1126_runtime_audit.shutdown import H5_SOURCE_PATHS
    from tools.plan1126_runtime_audit.telemetry import H8_SOURCE_PATHS, build_h8_audit_artifact

    merged_source = GitCommitSource(_ACCEPTED_MERGED_COMMIT, repository=ROOT)
    overlay_source = GitCommitSource(_ACCEPTED_OVERLAY_COMMIT, repository=ROOT)
    paths = tuple(sorted(
        set(H3_SOURCE_PATHS) | set(H4_SOURCE_PATHS) | set(H5_SOURCE_PATHS)
        | set(H7_SOURCE_PATHS) | set(H8_SOURCE_PATHS)
    ))
    merged = SourceTree({path: merged_source.read_text(path) for path in paths})
    overlay = SourceTree({path: overlay_source.read_text(path) for path in paths})
    with tempfile.TemporaryDirectory(prefix="plan1126-h8-build-") as workspace:
        artifact = build_h8_audit_artifact(
            merged=merged, overlay=overlay,
            merged_commit=merged_source.commit, overlay_commit=overlay_source.commit,
            workspace=workspace,
        )
    payload = artifact.to_dict()
    schema = _read_json(_SCHEMA_PATH)
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    if errors:
        raise ValueError("generated Task 8 artifact does not satisfy the canonical schema")
    _atomic_json(Path(args.artifact), payload)
    _write_text(Path(args.report), render_markdown(payload))
    _emit("COMPLETE")
    return 0


def _record_zed(
    args: argparse.Namespace, *, accepted_authority_digests: frozenset[str] = _ACCEPTED_AUTHORITY_DIGESTS,
) -> int:
    authority, authority_error = _read_accepted_authority(args.authority_report, accepted_authority_digests)
    if authority_error is not None:
        _emit("INVALID", (authority_error,))
        return 1
    assert authority is not None
    decisions = authority.get("authority_decisions")
    if not isinstance(decisions, Mapping) or decisions.get("zed_live") != "AUTHORIZED":
        _emit("UNRUN", ("authority_not_granted",))
        return 0
    anchor = _authority_anchor(authority, "zed record", artifact_required=True)
    if anchor is None:
        _emit("INVALID", ("authority_anchors_incomplete",))
        return 1
    try:
        artifact_bytes = Path(args.artifact).read_bytes()
    except OSError:
        _emit("INVALID", ("artifact_invalid",))
        return 1
    if hashlib.sha256(artifact_bytes).hexdigest() != anchor["expected_artifact_sha256"]:
        _emit("INVALID", ("artifact_digest_mismatch",))
        return 1
    try:
        artifact = _verify_artifact(args.artifact)
    except (OSError, ValueError, json.JSONDecodeError):
        _emit("INVALID", ("artifact_invalid",))
        return 1
    provenance = artifact.running_artifact_provenance
    if artifact.binding_commit != anchor["expected_binding_commit"]:
        _emit("INVALID", ("artifact_binding_authority_mismatch",))
        return 1
    if provenance is None or provenance.get("binding_commit") != anchor["expected_binding_commit"]:
        _emit("INVALID", ("artifact_provenance_unavailable",))
        return 1
    if (provenance.get("package_name"), provenance.get("package_version")) != ("optimus-cost-agent", "0.1.0"):
        _emit("INVALID", ("package_identity_mismatch",))
        return 1
    client = provenance.get("client_provenance")
    expected_client = anchor["expected_client_identity"]
    if not isinstance(client, Mapping) or (client.get("name"), client.get("version")) != (
        expected_client["name"], expected_client["version"],
    ):
        _emit("INVALID", ("client_identity_mismatch",))
        return 1
    outcome = input("Scenario outcome [OBSERVED/NOT_OBSERVED/NOT_APPLICABLE/INVALID]: ").strip().upper()
    attestation = input("Type ATTESTED to confirm this operator observation: ").strip().upper()
    if outcome not in _ZED_OUTCOMES or attestation != "ATTESTED":
        _emit("INVALID", ("operator_observation_invalid",))
        return 1
    path = Path(args.observations)
    existing: Mapping[str, Any] = {"schema_version": "plan-11-26-zed-observations-v1", "records": []}
    if path.exists():
        existing = _read_json(path)
    records = list(existing.get("records", []))
    if any(record.get("scenario") == args.scenario for record in records if isinstance(record, Mapping)):
        _emit("INVALID", ("duplicate_scenario",))
        return 1
    records.append({
        "scenario": args.scenario,
        "outcome": outcome,
        "attestation": "ATTESTED",
        "provenance_fingerprint": provenance["environment_fingerprint"],
    })
    _atomic_json(path, {"schema_version": "plan-11-26-zed-observations-v1", "records": records})
    _emit("COMPLETE")
    return 0


def _run_inventory(args: argparse.Namespace) -> int:
    if not args.commit:
        _emit("UNRUN", ("commit_required",))
        return 0
    try:
        git_source = GitCommitSource(args.commit, repository=args.repository)
        prefixes = tuple(args.path_prefix)
        source = SourceTree({
            path: git_source.read_text(path)
            for path in git_source.paths()
            if path.endswith(".py") and path.startswith(prefixes)
        })
        sites = discover_sites(source)
    except (OSError, ValueError, KeyError):
        _emit("INVALID", ("inventory_source_invalid",))
        return 1
    payload = {
        "schema_version": "plan-11-26-inventory-v1",
        "commit": git_source.commit,
        "site_count": len(sites),
        "unclassified_site_count": sum(site.classification.value == "UNCLASSIFIED" for site in sites),
        "sites": [site.to_dict() for site in sites],
    }
    if args.output:
        _atomic_json(Path(args.output), payload)
    _emit("PARTIAL" if payload["unclassified_site_count"] else "COMPLETE")
    return 0


def _validate_offline_intakes(
    baseline: Mapping[str, Any], prerequisites: Mapping[str, Any],
) -> tuple[list[Mapping[str, Any]], list[PrerequisiteStatus], tuple[int, ...]]:
    if (
        baseline.get("schema_version") != "plan-11-26-baseline-intake-v1"
        or prerequisites.get("schema_version") != "plan-11-26-prerequisite-intake-v1"
        or baseline.get("plan_id") != "11.26"
        or prerequisites.get("plan_id") != "11.26"
    ):
        raise ValueError("intake schema or plan mismatch")
    merged = baseline.get("merged_baseline")
    overlay = baseline.get("runtime_overlay")
    pointer = baseline.get("task_1_prerequisite_intake")
    acceptance = prerequisites.get("review_acceptance")
    if (
        not isinstance(merged, Mapping)
        or merged.get("ref") != "main"
        or merged.get("commit") != _ACCEPTED_MERGED_COMMIT
        or not isinstance(overlay, Mapping)
        or overlay.get("accepted_runtime_commit") != _ACCEPTED_OVERLAY_COMMIT
        or baseline.get("binding_commit") is not None
        or baseline.get("baseline_reconciliation_status") != "UNRESOLVED"
        or not isinstance(pointer, Mapping)
        or pointer.get("status") != "ACCEPTED"
        or pointer.get("report") != _TASK_1_REPORT
        or pointer.get("source_task_0_commit") != _TASK_0_INTAKE_COMMIT
        or prerequisites.get("source_task_0_commit") != pointer.get("source_task_0_commit")
        or not isinstance(acceptance, Mapping)
        or acceptance.get("status") != "ACCEPTED"
    ):
        raise ValueError("accepted intake identity or linkage mismatch")
    rows = prerequisites.get("prerequisites")
    if not isinstance(rows, list) or len(rows) != 18:
        raise ValueError("exactly 18 prerequisite rows are required")
    expected_prefixes = [f"P{number:02d}_" for number in range(1, 19)]
    ids = [row.get("id") if isinstance(row, Mapping) else None for row in rows]
    if (
        len(set(ids)) != 18
        or any(
            not isinstance(identifier, str) or not identifier.startswith(prefix)
            for identifier, prefix in zip(ids, expected_prefixes, strict=True)
        )
    ):
        raise ValueError("prerequisite IDs must be unique P01-P18 records")
    required_fields = {
        "id", "prerequisite", "observed_status", "method", "owner", "authorized", "dependent_rows", "scope_out",
    }
    statuses: list[PrerequisiteStatus] = []
    typed_rows: list[Mapping[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping) or not required_fields.issubset(row):
            raise ValueError("prerequisite row is incomplete")
        for field in ("id", "prerequisite", "method", "owner"):
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError(f"prerequisite {field} must be a non-empty string")
        if not isinstance(row["authorized"], bool):
            raise ValueError("prerequisite authorized must be boolean")
        dependents = row["dependent_rows"]
        if not isinstance(dependents, list) or any(not isinstance(item, str) or not item.strip() for item in dependents):
            raise ValueError("prerequisite dependent_rows must contain non-empty strings")
        scope_out = row["scope_out"]
        if scope_out is not None and (
            not isinstance(scope_out, Mapping)
            or set(scope_out) != {"status", "owner", "reason"}
            or any(not isinstance(scope_out[field], str) or not scope_out[field].strip() for field in scope_out)
        ):
            raise ValueError("prerequisite scope_out is invalid")
        statuses.append(PrerequisiteStatus(row["observed_status"]))
        typed_rows.append(row)
    seeds = literal_seeds()
    if seeds != _FROZEN_LITERAL_SEEDS:
        raise ValueError("literal seed fixture drifted")
    return typed_rows, statuses, seeds


_TASK5_GROUP_COMMAND = (
    "uv", "run", "--frozen", "pytest",
    "tests/unit/acp/test_plan1126_cancellation.py",
    "tests/unit/acp/test_lifecycle.py",
    "tests/unit/acp/test_stdio_ndjson.py",
    "-q",
)
_TASK5_HARNESS_PATHS = (
    "tests/unit/acp/test_plan1126_cancellation.py",
    "tests/unit/acp/test_lifecycle.py",
    "tests/unit/acp/test_stdio_ndjson.py",
    "tools/plan1126_runtime_audit/cancellation.py",
    "tools/plan1126_runtime_audit/model.py",
    "tests/fixtures/plan1126_runtime_audit/audit-artifact.schema.json",
    "tools/run_plan1126_runtime_audit.py",
    "uv.lock",
)


def _task5_harness_fingerprint() -> str:
    digest = hashlib.sha256()
    for relative in _TASK5_HARNESS_PATHS:
        path = ROOT / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _task5_provenance_fingerprint() -> str:
    payload = {
        "executable": sys.executable,
        "platform": platform.platform(),
        "python": platform.python_version(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _run_task5_group_repeats(args: argparse.Namespace) -> int:
    if args.task5_group_repeats != 25:
        _emit("INVALID", ("task5_group_repeats_must_equal_25",))
        return 1
    if not args.artifact or not args.checkpoint:
        _emit("UNRUN", ("artifact_and_checkpoint_required",))
        return 0
    try:
        artifact = _verify_artifact(args.artifact)
    except (OSError, ValueError, json.JSONDecodeError):
        _emit("INVALID", ("artifact_invalid",))
        return 1
    if not any(record.hypothesis_id == "H3" for record in artifact.evidence_records):
        _emit("INVALID", ("h3_evidence_required",))
        return 1

    store = CheckpointStore(args.checkpoint)
    checkpoint = store.read()
    artifact_digest = hashlib.sha256(
        json.dumps(artifact.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    harness_fingerprint = _task5_harness_fingerprint()
    provenance_fingerprint = _task5_provenance_fingerprint()
    command_text = " ".join(_TASK5_GROUP_COMMAND)
    completed_entries = {
        key: value
        for key, value in checkpoint.entries.items()
        if key.startswith("task5-group-repeat-")
        and isinstance(value, Mapping)
        and value.get("artifact_digest") == artifact_digest
        and value.get("command") == command_text
        and value.get("harness_fingerprint") == harness_fingerprint
        and value.get("provenance_fingerprint") == provenance_fingerprint
        and value.get("status") == "PASS"
    }
    for repeat_index in range(25):
        record_id = f"task5-group-repeat-{repeat_index + 1:02d}"
        if record_id in completed_entries:
            continue
        started = time.perf_counter()
        completed = subprocess.run(
            list(_TASK5_GROUP_COMMAND),
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
        result = {
            "artifact_digest": artifact_digest,
            "command": command_text,
            "duration_ms": duration_ms,
            "harness_fingerprint": harness_fingerprint,
            "platform": platform.platform(),
            "provenance_fingerprint": provenance_fingerprint,
            "python": platform.python_version(),
            "returncode": completed.returncode,
            "status": "PASS" if completed.returncode == 0 else "FAIL",
        }
        checkpoint = store.append(record_id, result, expected_revision=checkpoint.revision)
        if completed.returncode != 0:
            _emit("INVALID", (f"{record_id}_failed",))
            return 1

    final_checkpoint = store.read()
    entries = [
        value
        for key, value in sorted(final_checkpoint.entries.items())
        if key.startswith("task5-group-repeat-")
        and isinstance(value, Mapping)
        and value.get("artifact_digest") == artifact_digest
        and value.get("command") == command_text
        and value.get("harness_fingerprint") == harness_fingerprint
        and value.get("provenance_fingerprint") == provenance_fingerprint
        and value.get("status") == "PASS"
    ]
    if len(entries) != 25:
        _emit("INVALID", ("task5_group_checkpoint_incomplete",))
        return 1
    durations = sorted(float(item["duration_ms"]) for item in entries)
    repeatability = classify_repeatability(
        outcomes=[{"returncode": item["returncode"], "status": item["status"]} for item in entries],
        harness_fingerprints=[str(item["harness_fingerprint"]) for item in entries],
        provenance_fingerprints=[str(item["provenance_fingerprint"]) for item in entries],
    )
    if repeatability.status is not RepeatabilityStatus.STABLE:
        _emit("INVALID", (f"task5_repeatability={repeatability.status.value}",))
        return 1
    p95_index = max(0, __import__("math").ceil(len(durations) * 0.95) - 1)
    _emit(
        "COMPLETE",
        (
            f"repeat_count={len(entries)}",
            f"p50_ms={statistics.median(durations):.3f}",
            f"p95_ms={durations[p95_index]:.3f}",
            f"repeatability={repeatability.status.value}",
            f"harness_fingerprint={harness_fingerprint}",
            f"provenance_fingerprint={provenance_fingerprint}",
        ),
    )
    return 0


def _run_offline(args: argparse.Namespace) -> int:
    if args.task5_group_repeats:
        return _run_task5_group_repeats(args)
    if not args.baseline_report or not args.prerequisite_report:
        _emit("UNRUN", ("intake_reports_required",))
        return 0
    try:
        baseline = _read_json(args.baseline_report)
        prerequisites = _read_json(args.prerequisite_report)
        rows, statuses, seeds = _validate_offline_intakes(baseline, prerequisites)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        _emit("INVALID", ("intake_reports_invalid",))
        return 1
    payload = {
        "schema_version": "plan-11-26-offline-foundation-v1",
        "merged_commit": baseline["merged_baseline"]["commit"],
        "overlay_commit": baseline["runtime_overlay"]["accepted_runtime_commit"],
        "binding_commit": baseline["binding_commit"],
        "prerequisite_count": len(rows),
        "prerequisite_status_counts": {
            status.value: sum(item is status for item in statuses) for status in PrerequisiteStatus
        },
        "literal_seeds": list(seeds),
    }
    if args.output:
        _atomic_json(Path(args.output), payload)
    _emit("COMPLETE")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "inventory":
        return _run_inventory(args)
    if args.command == "semantic":
        return _run_semantic(args)
    if args.command == "telemetry":
        return _run_telemetry(args)
    if args.command == "offline":
        return _run_offline(args)
    if args.command in {"live-redis", "acpx", "sdk"}:
        status, reasons, _ = _live_gate(args, args.command)
        _emit(status, reasons)
        return 1 if status == "INVALID" else 0
    if args.command == "zed":
        return _record_zed(args)
    try:
        artifact = _verify_artifact(args.artifact)
        if args.command == "render":
            _write_text(Path(args.report), render_markdown(artifact.to_dict()))
        _emit("PASS")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _emit("INVALID", (str(exc),))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
