"""Plan 11.7 v5 E2: offline verifier of promoted sanitized current-client evidence.

Bundles are produced by the real pipeline over the deterministic fake host, then copied to a public bundle root;
all private roots are deleted before verification. Nothing here is live or accepted evidence.
"""

from __future__ import annotations

import json
import os
import shutil
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.support import plan117_v5_host as host_mod
from tests.unit.tools.test_evidence_gather_plan117_v5 import RUN_ID, Pipeline
from tools import verify_plan117_v5_current_client_evidence as verifier
from tools.evidence_gather_support import plan117_current_client_collector as col
from tools.evidence_gather_support import plan117_current_client_contract as c

D = c.GateDisposition


@pytest.fixture
def windows_shaped_paths(monkeypatch):
    import sys
    from pathlib import PurePosixPath

    from tools.evidence_gather_support import plan117_current_client_collector as col

    if sys.platform != "win32":
        monkeypatch.setattr(col, "_canonical_text", lambda text: c.canonicalize_windows_path("Z:\\" + "\\".join(PurePosixPath(text).parts[1:])))


class Bundle:
    def __init__(self, tmp_path, monkeypatch, options=None):
        pipeline = Pipeline(tmp_path, monkeypatch, options)
        pipeline.through_classify()
        assert pipeline.redact() == 0
        assert pipeline.redact(pipeline.receipt()) == 0
        self.checkout = pipeline.checkout
        self.root = tmp_path / "public-checkout" / "reports" / "plan-11-7-v5-current-client-gate"
        shutil.copytree(pipeline.sanitized / RUN_ID, self.root)
        shutil.rmtree(tmp_path / "private")
        shutil.rmtree(tmp_path / "host")
        self.manifest = self.root / "manifest.json"
        self.attestation = self.root / "redaction-attestation.json"
        self.report = self.root / "redaction-report.json"

    def run(self, capsys, *, manifest=None, attestation=None, root=None):
        capsys.readouterr()
        code = verifier.main(["--manifest", str(manifest or self.manifest), "--attestation", str(attestation or self.attestation), "--bundle-root", str(root or self.root)], checkout_root=self.checkout)
        out, err = capsys.readouterr()
        return code, json.loads(out) if out.strip() else None, err

    def load(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, path, document):
        path.write_bytes(c.canonical_json_bytes(document))

    def reforge(self, mutate_manifest):
        """A same-privilege forger: edit the manifest and recompute every unauthenticated hash downstream."""
        manifest = self.load(self.manifest)
        mutate_manifest(manifest)
        self.write(self.manifest, manifest)
        manifest_bytes = self.manifest.read_bytes()
        report = self.load(self.report)
        report["derivatives"][0].update(sha256=c.sha256_hex(manifest_bytes), size_bytes=len(manifest_bytes))
        self.write(self.report, report)
        report_bytes = self.report.read_bytes()
        attestation = self.load(self.attestation)
        attestation["sanitized_manifest_sha256"] = c.sha256_hex(manifest_bytes)
        attestation["redaction_report_sha256"] = c.sha256_hex(report_bytes)
        attestation["derivatives"] = [
            {"locator": "manifest.json", "sha256": c.sha256_hex(manifest_bytes), "size_bytes": len(manifest_bytes)},
            {"locator": "redaction-report.json", "sha256": c.sha256_hex(report_bytes), "size_bytes": len(report_bytes)},
        ]
        attestation["receipt"].update(sanitized_manifest_sha256=c.sha256_hex(manifest_bytes), redaction_report_sha256=c.sha256_hex(report_bytes),
                                      derivatives=[{"locator": "manifest.json", "sha256": c.sha256_hex(manifest_bytes)}])
        attestation["receipt_sha256"] = c.sha256_hex(c.canonical_json_bytes(attestation["receipt"]))
        self.write(self.attestation, attestation)


def test_promoted_accepted_bundle_verifies_with_private_roots_absent(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch)
    assert not (tmp_path / "private").exists()
    code, out, _ = bundle.run(capsys)
    assert code == 0
    assert out == {"integrity": "verified", "failures": [], "disposition": D.ACCEPTED_CURRENT_CLIENT_GATE.value, "reasons": [], "derived_reachability": "ZERO_ENTRY_UNREACHABLE"}


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows sharing semantics")
@pytest.mark.parametrize("release", [True, False], ids=["released", "persistent"])
def test_windows_promotion_with_a_held_attestation(tmp_path, monkeypatch, capsys, windows_shaped_paths, release):
    pipeline = Pipeline(tmp_path, monkeypatch)
    pipeline.through_classify()
    assert pipeline.redact() == 0
    receipt = pipeline.receipt()
    final = pipeline.sanitized / RUN_ID
    names = (col.SANITIZED_NAME, col.REPORT_NAME, col.ATTESTATION_NAME)
    sources = []
    waits = []
    files = {}

    with ExitStack() as handle:
        def observe(operation):
            def move(source, destination):
                source = Path(source)
                assert Path(destination) == final
                assert not final.exists()
                contents = {name: (source / name).read_bytes() for name in names}
                if not sources:
                    files.update(contents)
                    handle.enter_context((source / col.ATTESTATION_NAME).open("rb"))
                assert contents == files
                sources.append(source)
                operation(source, destination)
            return move

        def wait(seconds):
            waits.append(seconds)
            if release:
                handle.close()

        monkeypatch.setattr(col, "os", SimpleNamespace(**(vars(os) | {"rename": observe(os.rename), "replace": observe(os.replace)})))
        monkeypatch.setattr(col, "time", SimpleNamespace(sleep=wait))
        capsys.readouterr()
        exit_code = pipeline.redact(receipt)
        err = capsys.readouterr().err
        assert len(set(sources)) == 1
        if release:
            assert exit_code == 0
            assert waits == [0.05] and len(sources) == 2
            assert not sources[0].exists()
            assert {name: (final / name).read_bytes() for name in names} == files
        else:
            assert exit_code == 2 and err == "promotion_failed\n"
            assert waits == [0.05, 0.2] and len(sources) == 3
            assert not final.exists()
            assert (sources[0] / col.ATTESTATION_NAME).read_bytes() == files[col.ATTESTATION_NAME]

    if release:
        assert verifier.main(["--manifest", str(final / col.SANITIZED_NAME),
                              "--attestation", str(final / col.ATTESTATION_NAME),
                              "--bundle-root", str(final)], checkout_root=pipeline.checkout) == 0


@pytest.mark.parametrize(
    "platform, winerror, collision, expected_waits, expected_code",
    [
        ("nt", 32, False, [0.05, 0.2], "promotion_failed"),
        ("nt", 3, False, [], "promotion_failed"),
        ("nt", 32, True, [0.05], "promoted_run_exists"),
        ("posix", 5, False, [], "promotion_failed"),
    ],
    ids=["sharing-violation", "unrelated-denial", "destination-appears", "posix-single-attempt"],
)
def test_promotion_rename_refusal(tmp_path, monkeypatch, capsys, windows_shaped_paths,
                                  platform, winerror, collision, expected_waits, expected_code):
    pipeline = Pipeline(tmp_path, monkeypatch)
    pipeline.through_classify()
    assert pipeline.redact() == 0
    receipt = pipeline.receipt()
    final = pipeline.sanitized / RUN_ID
    attempts = []
    waits = []
    destination_id = None

    def observe(operation, source, destination):
        assert Path(destination) == final
        attempts.append((operation, Path(source)))
        if collision and final.exists():
            if os.name == "nt":
                return getattr(os, operation)(source, destination)
            if operation == "rename":
                raise FileExistsError("synthetic no-clobber refusal")
        error = OSError("synthetic private path")
        error.winerror = winerror
        raise error

    def wait(seconds):
        nonlocal destination_id
        waits.append(seconds)
        if collision:
            final.mkdir()
            destination_id = final.stat().st_ino

    monkeypatch.setattr(col, "os", SimpleNamespace(**(vars(os) | {
        "name": platform,
        "rename": lambda source, destination: observe("rename", source, destination),
        "replace": lambda source, destination: observe("replace", source, destination),
    })))
    monkeypatch.setattr(col, "time", SimpleNamespace(sleep=wait))
    capsys.readouterr()
    assert pipeline.redact(receipt) == 2
    expected_operation = "rename" if platform == "nt" else "replace"
    assert capsys.readouterr().err == expected_code + "\n"
    assert waits == expected_waits
    assert len(attempts) == len(waits) + 1 and len(set(attempts)) == 1
    assert attempts[0][0] == expected_operation and not attempts[0][1].exists()
    if collision:
        assert destination_id == final.stat().st_ino and not list(final.iterdir())
    else:
        assert not final.exists()


def test_stop_bundle_verifies_integrity_and_reports_stop_without_acceptance(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch, host_mod.FakeHostOptions(reopen_load_arm="r_refusal"))
    code, out, _ = bundle.run(capsys)
    assert code == 1
    assert (out["integrity"], out["disposition"]) == ("verified", D.ZERO_ENTRY_REACHABLE_STOP.value)
    assert out["derived_reachability"] is None


def test_integrity_failure_never_masks_a_stop_signal(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch, host_mod.FakeHostOptions(reopen_load_arm="a_prime"))
    bundle.report.write_bytes(bundle.report.read_bytes() + b" ")
    code, out, _ = bundle.run(capsys)
    assert code == 2
    assert out["integrity"] == "failed" and "derivative_digest_mismatch" in out["failures"]
    assert out["disposition"] == D.ZERO_ENTRY_REACHABLE_STOP.value


@pytest.mark.parametrize("captured_reopen", [False, True])
def test_attestation_decoder_refusal_preserves_manifest_disposition(
    tmp_path, monkeypatch, capsys, windows_shaped_paths, captured_reopen,
):
    bundle = Bundle(tmp_path, monkeypatch, host_mod.FakeHostOptions(reopen_load_arm="a_prime" if captured_reopen else None))
    attestation = bundle.attestation.read_text(encoding="utf-8")

    def reject_attestation(payload, *args, **kwargs):
        if payload == attestation:
            raise ValueError("simulated attestation decoder refusal")
        return json.loads(payload, *args, **kwargs)

    monkeypatch.setattr(c, "json", SimpleNamespace(**{**vars(json), "loads": reject_attestation}))
    code, out, _ = bundle.run(capsys)
    assert code == 2 and out["integrity"] == "failed" and "attestation_invalid" in out["failures"]
    expected = D.ZERO_ENTRY_REACHABLE_STOP if captured_reopen else D.INVALID_CURRENT_CLIENT_GATE
    assert out["disposition"] == expected.value


@pytest.mark.parametrize("target", ["manifest", "report"])
def test_altered_promoted_bytes_fail(tmp_path, monkeypatch, capsys, windows_shaped_paths, target):
    bundle = Bundle(tmp_path, monkeypatch)
    path = getattr(bundle, target)
    path.write_bytes(path.read_bytes().replace(b'"session_load":0', b'"session_load":1', 1) if target == "manifest" else path.read_bytes() + b"\n")
    code, out, _ = bundle.run(capsys)
    assert code == 2 and out["integrity"] == "failed"


@pytest.mark.parametrize(
    "mutation,failure",
    [
        (lambda a: a["receipt"].update(verdict="conditional"), "receipt_digest_mismatch"),
        (lambda a: (a["receipt"].update(verdict="rejecting"), a.update(receipt_sha256=c.sha256_hex(c.canonical_json_bytes(a["receipt"])))), "receipt_not_accepting"),
        (lambda a: (a["receipt"].update(run_id="p117v5-run-0009"), a.update(receipt_sha256=c.sha256_hex(c.canonical_json_bytes(a["receipt"])))), "receipt_binding_mismatch"),
        (lambda a: a.update(mapping_sha256="0" * 64), "receipt_binding_mismatch"),
        (lambda a: a["gate"].update(disposition=D.ACCEPTED_CURRENT_CLIENT_GATE.value, reasons=[]), None),
        (lambda a: a.update(evidence_kind="acpx-restart"), "unsupported_evidence_kind"),
        (lambda a: a.update(extra=1), "attestation_invalid"),
    ],
)
def test_attestation_and_receipt_tamper_fails(tmp_path, monkeypatch, capsys, windows_shaped_paths, mutation, failure):
    bundle = Bundle(tmp_path, monkeypatch, host_mod.FakeHostOptions(cleanup_fails=True))
    attestation = bundle.load(bundle.attestation)
    mutation(attestation)
    bundle.write(bundle.attestation, attestation)
    code, out, _ = bundle.run(capsys)
    assert code == 2 and out["integrity"] == "failed"
    assert (failure or "gate_mismatch") in out["failures"]


def test_reforged_capture_root_commitment_is_caught_by_the_trusted_run_spec(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch)

    def swap(manifest):
        roles = {item["role"]: item for item in manifest["path_identities"]}
        roles["capture_root"]["commitment"] = roles["run_root"]["commitment"]

    bundle.reforge(swap)
    code, out, _ = bundle.run(capsys)
    assert code == 2 and "run_spec_mismatch:private_root_commitments" in out["failures"]


def test_reforged_counts_with_recomputed_hashes_disagree_with_the_attested_gate(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch)

    def drop_prompt_count(manifest):
        arm = next(a for a in manifest["arms"] if a["arm_id"] == "r_refusal")
        arm["launches"][0]["counts"]["session_prompt"] = 0

    bundle.reforge(drop_prompt_count)
    code, out, _ = bundle.run(capsys)
    assert code == 2 and "gate_mismatch" in out["failures"]
    assert out["disposition"] == D.INVALID_CURRENT_CLIENT_GATE.value


def test_reforged_module_hash_is_caught_by_the_reducer(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch)

    def swap_spec_hash(manifest):
        launch = next(a for a in manifest["arms"] if a["arm_id"] == "a_prime")["launches"][0]
        next(e for e in launch["module_closure"]["entries"] if e["module_name"] == "optimus.acp.spec")["sha256"] = "0" * 64

    bundle.reforge(swap_spec_hash)
    code, out, _ = bundle.run(capsys)
    assert code == 2 and out["disposition"] == D.INVALID_CURRENT_CLIENT_GATE.value


def test_injected_raw_path_is_a_privacy_failure(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch)
    bundle.reforge(lambda manifest: manifest["client"].update(cli_version="Zed C:/Users/op"))
    code, out, err = bundle.run(capsys)
    assert code == 2 and "privacy_violation" in out["failures"]
    assert "Users" not in json.dumps(out) and "Users" not in err


def test_missing_attestation_or_derivative_fails(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch)
    bundle.report.unlink()
    code, out, _ = bundle.run(capsys)
    assert code == 2 and "derivative_missing" in out["failures"]
    bundle.attestation.unlink()
    code, out, _ = bundle.run(capsys)
    assert code == 2 and "attestation_missing" in out["failures"]


def test_manifest_or_attestation_outside_the_bundle_root_is_refused(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch)
    outside = tmp_path / "outside.json"
    shutil.copyfile(bundle.manifest, outside)
    code, out, err = bundle.run(capsys, manifest=outside)
    assert code == 2 and out is None and err.strip() == "path_escape"
    code, out, _ = bundle.run(capsys, attestation=outside)
    assert code == 2 and "path_escape" in out["failures"]


def test_bundle_cannot_register_itself(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch)
    registry_path = bundle.checkout / "reports" / "plan-11-7-v5-approved-runs.json"
    shutil.copyfile(registry_path, bundle.root / "plan-11-7-v5-approved-runs.json")
    registry_path.write_bytes(c.canonical_json_bytes({"schema": c.RUN_REGISTRY_SCHEMA, "runs": []}))
    code, out, _ = bundle.run(capsys)
    assert code == 2 and "run_not_registered" in out["failures"]


def test_trust_inputs_inside_the_bundle_root_are_refused(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch)
    code, out, _ = bundle.run(capsys, root=bundle.checkout.parent)
    assert code == 2 and "trust_input_inside_bundle" in out["failures"]


def test_scenario_blob_drift_in_the_checkout_fails(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch)
    scenario = bundle.checkout / "tests" / "fixtures" / "evidence" / "scenarios" / "plan117-current-client-gate-v5.toml"
    scenario.write_bytes(scenario.read_bytes() + b"\n")
    code, out, _ = bundle.run(capsys)
    assert code == 2 and "run_spec_mismatch:scenario_source_sha256" in out["failures"]


def test_cli_keeps_exactly_three_arguments():
    parser = verifier.build_parser()
    assert sorted(action.dest for action in parser._actions if action.dest != "help") == ["attestation", "bundle_root", "manifest"]
    assert all(action.required for action in parser._actions if action.dest != "help")


def test_committed_checkout_has_no_approved_run_so_nothing_can_verify_today(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch)
    capsys.readouterr()
    code = verifier.main(["--manifest", str(bundle.manifest), "--attestation", str(bundle.attestation), "--bundle-root", str(bundle.root)])
    out = json.loads(capsys.readouterr().out)
    assert code == 2 and "run_not_registered" in out["failures"]


@pytest.mark.parametrize("derivatives", [[], "x", [1]])
def test_malformed_report_derivatives_are_a_reported_failure_not_a_crash(tmp_path, monkeypatch, capsys, windows_shaped_paths, derivatives):
    bundle = Bundle(tmp_path, monkeypatch)
    report = bundle.load(bundle.report)
    report["derivatives"] = derivatives
    bundle.write(bundle.report, report)
    code, out, _ = bundle.run(capsys)
    assert code == 2 and out["integrity"] == "failed" and "report_inconsistent" in out["failures"]


# --------------------------------------------------------------------------- CP1 Fable finding S4


def test_a_missing_attestation_cannot_hide_a_stop_manifest(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch, host_mod.FakeHostOptions(reopen_load_arm="r_end_turn"))
    bundle.attestation.unlink()
    code, out, _ = bundle.run(capsys)
    assert code == 2
    assert out["integrity"] == "failed" and out["failures"] == ["attestation_missing"]
    assert out["disposition"] == D.ZERO_ENTRY_REACHABLE_STOP.value


def test_an_attestation_outside_the_root_cannot_hide_a_stop_manifest(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch, host_mod.FakeHostOptions(reopen_load_arm="a_prime"))
    outside = tmp_path / "elsewhere-attestation.json"
    shutil.copyfile(bundle.attestation, outside)
    code, out, _ = bundle.run(capsys, attestation=outside)
    assert code == 2 and "path_escape" in out["failures"]
    assert out["disposition"] == D.ZERO_ENTRY_REACHABLE_STOP.value


def test_a_manifest_outside_the_root_is_never_read(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch)
    outside = tmp_path / "elsewhere-manifest.json"
    shutil.copyfile(bundle.manifest, outside)
    code, out, err = bundle.run(capsys, manifest=outside)
    assert code == 2 and out is None and err.strip() == "path_escape"


# --------------------------------------------------------------------------- CP1 coordinator controls: verifier I/O containment


def _deny_reads(monkeypatch, predicate):
    """Synthetic denied read for chosen paths; records every read attempt. No ACL or real private file is touched."""
    from pathlib import Path

    original = Path.read_bytes
    attempts = []

    def read_bytes(self):
        attempts.append(Path(self))
        if predicate(Path(self)):
            raise PermissionError("synthetic denied read")
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    return attempts


def test_an_unreadable_attestation_cannot_hide_a_stop_manifest(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch, host_mod.FakeHostOptions(reopen_load_arm="r_refusal"))
    _deny_reads(monkeypatch, lambda p: p.name == "redaction-attestation.json")
    code, out, _ = bundle.run(capsys)
    assert code == 2 and "attestation_unreadable" in out["failures"]
    assert out["disposition"] == D.ZERO_ENTRY_REACHABLE_STOP.value


def test_an_unreadable_derivative_cannot_hide_a_stop_manifest(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch, host_mod.FakeHostOptions(reopen_load_arm="a_prime"))
    _deny_reads(monkeypatch, lambda p: p.name == "redaction-report.json")
    code, out, _ = bundle.run(capsys)
    assert code == 2 and "derivative_unreadable" in out["failures"]
    assert out["disposition"] == D.ZERO_ENTRY_REACHABLE_STOP.value


@pytest.mark.parametrize("name", ["plan-11-7-v5-approved-runs.json", "plan117-current-client-gate-v5.toml", "plan117-v5-first-refusal-descriptors.json"])
def test_unreadable_trust_inputs_cannot_hide_a_stop_manifest(tmp_path, monkeypatch, capsys, windows_shaped_paths, name):
    bundle = Bundle(tmp_path, monkeypatch, host_mod.FakeHostOptions(reopen_load_arm="r_cancelled"))
    _deny_reads(monkeypatch, lambda p: p.name == name)
    code, out, _ = bundle.run(capsys)
    assert code == 2 and "trust_input_unreadable" in out["failures"]
    assert out["disposition"] == D.ZERO_ENTRY_REACHABLE_STOP.value


def test_a_report_resolving_outside_the_root_is_never_read_by_any_path(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    from pathlib import Path

    bundle = Bundle(tmp_path, monkeypatch, host_mod.FakeHostOptions(reopen_load_arm="a_prime"))
    outside = tmp_path / "outside-report.json"
    shutil.copyfile(bundle.report, outside)
    original_resolve = Path.resolve

    def resolve(self, strict=False):
        if Path(self).name == "redaction-report.json":
            return original_resolve(outside, strict=strict)
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve)
    attempts = _deny_reads(monkeypatch, lambda p: p.name in {"redaction-report.json", "outside-report.json"})
    code, out, _ = bundle.run(capsys)
    assert code == 2 and "derivative_missing" in out["failures"]
    assert out["disposition"] == D.ZERO_ENTRY_REACHABLE_STOP.value
    assert not [p for p in attempts if p.name in {"redaction-report.json", "outside-report.json"}]


def test_an_unreadable_manifest_aborts_without_a_disposition(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch)
    _deny_reads(monkeypatch, lambda p: p.name == "manifest.json")
    code, out, err = bundle.run(capsys)
    assert code == 2 and out is None and err.strip() == "manifest_unreadable"


# --------------------------------------------------------------------------- consolidated Codex CP1 review (Serious 1, Serious 3)


def _rebind_report(bundle, payload):
    """Replace the report and recompute every unkeyed hash bound to it (a consistent same-privilege edit)."""
    bundle.report.write_bytes(payload)
    digest = c.sha256_hex(payload)
    attestation = bundle.load(bundle.attestation)
    for entry in attestation["derivatives"]:
        if entry["locator"] == "redaction-report.json":
            entry.update(sha256=digest, size_bytes=len(payload))
    attestation["redaction_report_sha256"] = digest
    attestation["receipt"]["redaction_report_sha256"] = digest
    attestation["receipt_sha256"] = c.sha256_hex(c.canonical_json_bytes(attestation["receipt"]))
    bundle.write(bundle.attestation, attestation)


def _report_variant(bundle, mutate):
    report = bundle.load(bundle.report)
    mutate(report)
    return c.canonical_json_bytes(report)


@pytest.mark.parametrize(
    "variant",
    [
        pytest.param(lambda b: b"{not json", id="malformed"),
        pytest.param(lambda b: b"null", id="null"),
        pytest.param(lambda b: b"[]", id="list"),
        pytest.param(lambda b: _report_variant(b, lambda r: r.update(extra=1)), id="unknown-field"),
        pytest.param(lambda b: _report_variant(b, lambda r: r.update(schema="other")), id="schema"),
        pytest.param(lambda b: _report_variant(b, lambda r: r.update(run_id="p117v5-run-0009")), id="run-id"),
        pytest.param(lambda b: _report_variant(b, lambda r: r.update(scenario_id="other")), id="scenario-id"),
        pytest.param(lambda b: _report_variant(b, lambda r: r.update(scenario_sha256="0" * 64)), id="scenario-sha"),
        pytest.param(lambda b: _report_variant(b, lambda r: r.update(raw_manifest_sha256="0" * 64)), id="raw-manifest-sha"),
        pytest.param(lambda b: _report_variant(b, lambda r: r["derivatives"][0].update(size_bytes=1)), id="derivative-size"),
        pytest.param(lambda b: _report_variant(b, lambda r: r["derivatives"][0].update(extra=1)), id="derivative-unknown"),
        pytest.param(lambda b: _report_variant(b, lambda r: r["privacy"].update(extra=1)), id="privacy-unknown"),
    ],
)
def test_a_rebound_invalid_report_fails_integrity_on_an_accepted_baseline(tmp_path, monkeypatch, capsys, windows_shaped_paths, variant):
    bundle = Bundle(tmp_path, monkeypatch)
    code, out, _ = bundle.run(capsys)
    assert code == 0 and out["disposition"] == D.ACCEPTED_CURRENT_CLIENT_GATE.value  # genuine accepted baseline
    _rebind_report(bundle, variant(bundle))
    code, out, _ = bundle.run(capsys)
    assert code == 2 and out["integrity"] == "failed" and "report_inconsistent" in out["failures"]


def test_a_rebound_but_unchanged_report_still_verifies(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch)
    _rebind_report(bundle, bundle.report.read_bytes())
    code, out, _ = bundle.run(capsys)
    assert code == 0 and out["integrity"] == "verified"


def test_a_malformed_trusted_scenario_is_reported_beside_a_kept_stop(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch, host_mod.FakeHostOptions(reopen_load_arm="r_refusal"))
    scenario = bundle.checkout / "tests" / "fixtures" / "evidence" / "scenarios" / "plan117-current-client-gate-v5.toml"
    scenario.write_bytes(b"this is = = not toml [\n")
    code, out, _ = bundle.run(capsys)
    assert code == 2 and "trust_input_invalid" in out["failures"]
    assert out["disposition"] == D.ZERO_ENTRY_REACHABLE_STOP.value


@pytest.mark.parametrize("literal", [b"1e400", b"-1e400"])
def test_an_overflowing_number_in_a_readable_stop_manifest_keeps_stop(tmp_path, monkeypatch, capsys, windows_shaped_paths, literal):
    bundle = Bundle(tmp_path, monkeypatch, host_mod.FakeHostOptions(reopen_load_arm="a_prime"))
    payload = bundle.manifest.read_bytes()
    assert b'"pid":4242' in payload
    bundle.manifest.write_bytes(payload.replace(b'"pid":4242', b'"pid":' + literal, 1))
    code, out, _ = bundle.run(capsys)
    assert code == 2 and out["integrity"] == "failed" and "manifest_not_strict_json" in out["failures"]
    assert out["disposition"] == D.ZERO_ENTRY_REACHABLE_STOP.value


def test_an_unparseable_manifest_without_a_signal_is_invalid_not_an_exception(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch)
    bundle.manifest.write_bytes(b"{not json")
    code, out, _ = bundle.run(capsys)
    assert code == 2 and out["disposition"] == D.INVALID_CURRENT_CLIENT_GATE.value


def test_unrelated_deep_material_cannot_hide_a_readable_stop(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    bundle = Bundle(tmp_path, monkeypatch, host_mod.FakeHostOptions(reopen_load_arm="a_prime"))
    payload = bundle.manifest.read_bytes()
    assert b'"pid":4242' in payload
    bundle.manifest.write_bytes(payload.replace(b'"pid":4242', b'"pid":' + b"[" * 2_000 + b"]" * 2_000, 1))
    code, out, err = bundle.run(capsys)
    assert code == 2 and err == ""
    assert out["integrity"] == "failed" and "manifest_invalid" in out["failures"]
    assert out["disposition"] == D.ZERO_ENTRY_REACHABLE_STOP.value


def test_permissive_json_maps_parser_recursion_to_none(monkeypatch):
    def too_deep(*_args, **_kwargs):
        raise RecursionError

    monkeypatch.setattr(verifier, "json", SimpleNamespace(loads=too_deep))
    assert verifier._permissive(b"[]") is None


# F1: deep arrays are invalid manifests whether the parser accepts or rejects their depth.
@pytest.mark.parametrize("depth", [2_000, 100_000])
def test_a_deeply_nested_manifest_is_a_reported_integrity_failure_not_a_crash(tmp_path, monkeypatch, capsys, windows_shaped_paths, depth):
    bundle = Bundle(tmp_path, monkeypatch)
    bundle.manifest.write_bytes(b"[" * depth + b"]" * depth)
    code, out, err = bundle.run(capsys)
    assert code == 2 and err == ""
    assert out["integrity"] == "failed" and "manifest_invalid" in out["failures"]
    assert out["disposition"] == D.INVALID_CURRENT_CLIENT_GATE.value
