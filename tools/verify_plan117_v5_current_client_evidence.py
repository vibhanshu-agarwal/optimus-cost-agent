"""Offline verifier for promoted Plan 11.7 v6 sanitized current-client evidence.

Three arguments only: ``--manifest``, ``--attestation``, ``--bundle-root``. The registered scenario, approved-run
registry and descriptor fixture are read from THIS reviewed checkout, never from the bundle. Verification needs no
private root and establishes sanitized integrity plus agreement with the reviewed RunSpec only: it cannot
reconstruct private paths, prove the private-to-public mapping, or authenticate a hostile same-privilege collector
who recomputes every unkeyed hash (that trust rests on the reviewed acquisition host and checkout custody).

Exit 0: integrity verified and ACCEPTED_CURRENT_CLIENT_GATE. Exit 1: integrity verified, any other disposition.
Exit 2: integrity or usage failure. Output is fixed codes only; no document value is echoed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
for _entry in (str(_ROOT), str(_ROOT / "src")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from evidence_handoff.collector.scenarios import load_scenario, resolve_bindings, scenario_sha256  # noqa: E402
from tools.evidence_gather_support import plan117_current_client_collector as collector  # noqa: E402
from tools.evidence_gather_support import plan117_current_client_contract as contract  # noqa: E402
from tools.evidence_gather_support.common import HostError  # noqa: E402


class VerificationAbort(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify_plan117_v5_current_client_evidence",
        description="Verify sanitized Plan 11.7 v6 current-client evidence.",
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    return parser


def _inside(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _parse(payload: bytes | None) -> Any:
    if payload is None:
        return None
    try:
        return contract.strict_json_loads(payload)
    except contract.ContractError:
        return None


def _permissive(payload: bytes) -> Any:
    try:
        return json.loads(payload.decode("utf-8", "replace"))
    except (ValueError, RecursionError):
        return None


def _read_contained(path: Path, root: Path) -> tuple[bytes | None, str | None]:
    """Resolve first, refuse anything outside the root, then read once: ``(bytes, None)`` or ``(None, code)``.

    The only read path for bundle files, so an escaped target is never opened by a later step.
    """
    try:
        resolved = Path(path).resolve(strict=True)
    except OSError:
        return None, "missing"
    if not _inside(resolved, root):
        return None, "escape"
    if not resolved.is_file():
        return None, "missing"
    try:
        return resolved.read_bytes(), None
    except OSError:
        return None, "unreadable"


def verify(manifest_path: Path, attestation_path: Path, bundle_root: Path, *, checkout_root: Path) -> dict[str, Any]:
    try:
        root = Path(bundle_root).resolve(strict=True)
    except OSError:
        raise VerificationAbort("bundle_root_missing") from None
    # Only the manifest itself can stop verification, and nothing outside the bundle root is ever read. Every
    # other custody or I/O problem is an integrity failure reported beside the manifest's own disposition, so an
    # unrelated attestation, derivative or trust-input failure can never hide a STOP.
    if not root.is_dir():
        raise VerificationAbort("path_escape")
    manifest_file = Path(manifest_path).resolve()
    manifest_bytes, manifest_error = _read_contained(manifest_path, root)
    if manifest_error is not None:
        raise VerificationAbort({"escape": "path_escape", "missing": "manifest_missing", "unreadable": "manifest_unreadable"}[manifest_error])
    assert manifest_bytes is not None
    failures: list[str] = []
    manifest_doc = _parse(manifest_bytes)
    recovered = ()
    if manifest_doc is None:
        # Strictly invalid (e.g. an overflowing number) but possibly readable: keep scanning it so a positive signal
        # is still reported. This permissive view never establishes integrity; it is recorded as a failure.
        manifest_doc = _permissive(manifest_bytes)
        if manifest_doc is not None:
            failures.append("manifest_not_strict_json")
            recovered = contract.scan_json_positive_signals(manifest_bytes)
    attestation_bytes, attestation_error = _read_contained(attestation_path, root)
    if attestation_error is not None:
        failures.append({"escape": "path_escape", "missing": "attestation_missing", "unreadable": "attestation_unreadable"}[attestation_error])
    checkout = Path(checkout_root).resolve()
    trust_files = [checkout.joinpath(*relative.split("/")) for relative in (collector.SCENARIO_RELATIVE, collector.APPROVED_RUNS_RELATIVE, collector.DESCRIPTOR_FIXTURE_RELATIVE)]
    try:
        trust_outside = not any(_inside(path.resolve(), root) for path in trust_files)
    except OSError:
        trust_outside = False
    if not trust_outside:
        failures.append("trust_input_inside_bundle")
    try:
        canonical = manifest_doc is not None and contract.canonical_json_bytes(manifest_doc) == manifest_bytes
    except ValueError:
        canonical = False
    if not canonical:
        failures.append("manifest_not_canonical")
    try:
        manifest = contract.parse_sanitized_manifest(manifest_doc)
    except contract.ContractError:
        manifest = None
        failures.append("manifest_invalid")
    attestation_doc, attestation = _parse(attestation_bytes), None
    if attestation_bytes is not None:
        try:
            attestation = contract.parse_attestation(attestation_doc)
        except contract.ContractError:
            failures.append("attestation_invalid")

    report_doc = None
    if attestation is not None:
        derivative_failures, payloads = _check_attestation(attestation, manifest, manifest_bytes, manifest_file, root)
        failures += derivative_failures
        report_bytes = payloads.get(collector.REPORT_NAME)  # only the already-contained read; never a second path
        report_doc = _parse(report_bytes)
        if report_bytes is not None and not _report_consistent(report_doc, attestation, manifest_bytes):
            failures.append("report_inconsistent")  # includes malformed JSON and JSON null
    if contract.find_privacy_violations([manifest_doc, report_doc, attestation_doc], forbidden_strings=()):
        failures.append("privacy_violation")
    if manifest is not None and trust_outside:
        try:
            failures += _check_run_spec(manifest, attestation, checkout)
        except (OSError, HostError):
            failures.append("trust_input_unreadable")
        except (ValueError, TypeError, KeyError):
            failures.append("trust_input_invalid")  # e.g. a malformed registered scenario; the manifest's STOP is kept

    plain = contract.reduce_document(manifest_doc, layer="sanitized", extra_hits=recovered)
    if attestation is not None and plain.to_json() != dict(attestation.gate):
        failures.append("gate_mismatch")
    failures = sorted(set(failures))
    extra = (contract.GateHit(contract.GateReason.INTEGRITY_INVALID),) if failures else ()
    gate = contract.reduce_document(manifest_doc, layer="sanitized", extra_hits=(*recovered, *extra))
    return {"integrity": "failed" if failures else "verified", "failures": failures, **gate.to_json()}


_REPORT_KEYS = frozenset({"schema", "run_id", "scenario_id", "scenario_sha256", "raw_manifest_sha256", "derivatives", "privacy", "gate"})


def _report_consistent(report: Any, attestation: contract.Plan117RedactionAttestation, manifest_bytes: bytes) -> bool:
    """The closed redaction-report schema with every binding the attestation states (input consistency only)."""
    if type(report) is not dict or set(report) != _REPORT_KEYS or report["schema"] != contract.REDACTION_REPORT_SCHEMA:
        return False
    bindings = (
        (report["run_id"], attestation.run_id), (report["scenario_id"], attestation.scenario_id),
        (report["scenario_sha256"], attestation.scenario_sha256), (report["raw_manifest_sha256"], attestation.raw_manifest_sha256),
        (report["gate"], dict(attestation.gate)),
        (report["privacy"], {"status": "passed", "violations": []}),
        (report["derivatives"], [{"locator": collector.SANITIZED_NAME, "sha256": contract.sha256_hex(manifest_bytes), "size_bytes": len(manifest_bytes)}]),
    )
    return all(type(left) is type(right) and left == right for left, right in bindings)


def _check_attestation(attestation: contract.Plan117RedactionAttestation, manifest: contract.Plan117SanitizedManifest | None,
                       manifest_bytes: bytes, manifest_file: Path, root: Path) -> tuple[list[str], dict[str, bytes]]:
    failures: list[str] = []
    if attestation.evidence_kind != contract.EVIDENCE_KIND_GATE:
        failures.append("unsupported_evidence_kind")
    digests: dict[str, str] = {}
    payloads: dict[str, bytes] = {}
    for locator, digest, size in attestation.derivatives:
        payload, error = _read_contained(root.joinpath(*locator.split("/")), root)
        if payload is None:
            failures.append("derivative_unreadable" if error == "unreadable" else "derivative_missing")
            continue
        payloads[locator] = payload
        digests[locator] = contract.sha256_hex(payload)
        if digests[locator] != digest or len(payload) != size:
            failures.append("derivative_digest_mismatch")
    if manifest_file != (root / collector.SANITIZED_NAME).resolve():
        failures.append("manifest_not_attested")
    if attestation.sanitized_manifest_sha256 != contract.sha256_hex(manifest_bytes):
        failures.append("manifest_digest_mismatch")
    if collector.REPORT_NAME in digests and attestation.redaction_report_sha256 != digests[collector.REPORT_NAME]:
        failures.append("derivative_digest_mismatch")
    receipt = attestation.receipt
    if attestation.receipt_sha256 != contract.sha256_hex(contract.canonical_json_bytes(dict(receipt.document))):
        failures.append("receipt_digest_mismatch")
    if receipt.verdict != "accepting":
        failures.append("receipt_not_accepting")
    bound = (
        (receipt.run_id, attestation.run_id), (receipt.scenario_id, attestation.scenario_id), (receipt.scenario_sha256, attestation.scenario_sha256),
        (receipt.source_commit, attestation.source_commit), (receipt.raw_manifest_sha256, attestation.raw_manifest_sha256),
        (receipt.raw_bundle_sha256, attestation.raw_bundle_sha256), (receipt.sanitized_manifest_sha256, attestation.sanitized_manifest_sha256),
        (receipt.mapping_sha256, attestation.mapping_sha256), (receipt.redaction_report_sha256, attestation.redaction_report_sha256),
        (receipt.derivatives, ((collector.SANITIZED_NAME, attestation.sanitized_manifest_sha256),)),
    )
    if any(left != right for left, right in bound):
        failures.append("receipt_binding_mismatch")
    if manifest is not None:
        facts = (manifest.run_id, manifest.scenario_id, manifest.scenario_sha256, manifest.approval_id, manifest.raw_bundle_sha256,
                 manifest.provisional_classification_sha256, manifest.source.actual_source_commit)
        claimed = (attestation.run_id, attestation.scenario_id, attestation.scenario_sha256, attestation.approval_id, attestation.raw_bundle_sha256,
                   attestation.provisional_classification_sha256, attestation.source_commit)
        if facts != claimed:
            failures.append("attestation_manifest_mismatch")
        if receipt.reviewed_at < manifest.run_window.wall_ended_at:
            failures.append("receipt_chronology_invalid")
    return failures, payloads


def _check_run_spec(manifest: contract.Plan117SanitizedManifest, attestation: contract.Plan117RedactionAttestation | None, checkout: Path) -> list[str]:
    for relative in (collector.APPROVED_RUNS_RELATIVE, collector.SCENARIO_RELATIVE, collector.DESCRIPTOR_FIXTURE_RELATIVE):
        path = checkout.joinpath(*relative.split("/"))
        if path.exists():
            path.read_bytes()  # an unreadable trust input is reported as such, never as a missing run
    try:
        registry, _payload = collector.load_trusted_registry(checkout)
        spec = registry.lookup(manifest.run_id)
    except HostError as exc:
        return [exc.code]
    except contract.ContractError as exc:
        return [exc.code]
    failures = [f"run_spec_mismatch:{field}" for field in contract.run_spec_mismatches(manifest, spec)]
    scenario_path = checkout.joinpath(*collector.SCENARIO_RELATIVE.split("/"))
    if contract.sha256_hex(scenario_path.read_bytes()) != spec.scenario_source_sha256:
        failures.append("run_spec_mismatch:scenario_source_sha256")
    scenario = load_scenario(scenario_path)
    if scenario_sha256(scenario, resolve_bindings(scenario, (f"run_id={manifest.run_id}",))) != manifest.scenario_sha256:
        failures.append("run_spec_mismatch:scenario_definition")
    if collector.load_descriptor_fixture(checkout)[1] != spec.descriptor_fixture_sha256:
        failures.append("run_spec_mismatch:checkout_descriptor_fixture")
    if attestation is not None and attestation.evidence_kind != spec.evidence_kind:
        failures.append("run_spec_mismatch:evidence_kind")
    return failures


def main(argv: Sequence[str] | None = None, *, checkout_root: Path | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = verify(args.manifest, args.attestation, args.bundle_root, checkout_root=checkout_root or _ROOT)
    except VerificationAbort as exc:
        print(exc.code, file=sys.stderr)
        return 2
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    if result["failures"]:
        return 2
    return 0 if result["disposition"] == contract.GateDisposition.ACCEPTED_CURRENT_CLIENT_GATE.value else 1


if __name__ == "__main__":
    raise SystemExit(main())
