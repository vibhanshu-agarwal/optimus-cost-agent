"""Thin, offline-first command line for Plan 11.26 audit artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.plan1126_runtime_audit.corpus import literal_seeds  # noqa: E402
from tools.plan1126_runtime_audit.inventory import discover_sites  # noqa: E402
from tools.plan1126_runtime_audit.model import AuditArtifact, PrerequisiteStatus  # noqa: E402
from tools.plan1126_runtime_audit.provenance import ExpectedArtifactIdentity, verify_running_artifact  # noqa: E402
from tools.plan1126_runtime_audit.render import render_markdown  # noqa: E402
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
    return parser


def _verify_artifact(path: str) -> AuditArtifact:
    payload = _read_json(path)
    schema = _read_json(_SCHEMA_PATH)
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        raise ValueError("; ".join(error.message for error in errors))
    return AuditArtifact.from_dict(payload)


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


def _run_offline(args: argparse.Namespace) -> int:
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
