"""Plan 11.7 v5 E2: the v5 gate through the EXISTING evidence_gather pipeline stages.

validate -> prepare -> check -> collect -> classify -> redact (stage) -> redact (receipt), driven through
``evidence_gather.main``. The trusted checkout, host actions and identity tokens are substituted through module
seams; nothing launches a process, Zed or service, and nothing here is live or accepted evidence.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path, PurePosixPath

import pytest

from tests.support import plan117_v5_host as host_mod
from tools import evidence_gather as gather
from tools.evidence_gather_support import plan117_current_client_collector as col
from tools.evidence_gather_support import plan117_current_client_contract as c

REPO = Path(__file__).resolve().parents[3]
RUN_ID = "p117v5-run-0001"
COMMIT = host_mod.SOURCE_COMMIT
D = c.GateDisposition


@pytest.fixture
def windows_shaped_paths(monkeypatch):
    if sys.platform != "win32":
        monkeypatch.setattr(col, "_canonical_text", lambda text: c.canonicalize_windows_path("Z:\\" + "\\".join(PurePosixPath(text).parts[1:])))


class Pipeline:
    def __init__(self, tmp_path: Path, monkeypatch, options=None) -> None:
        self.tmp = tmp_path
        self.checkout = tmp_path / "checkout"
        for relative in (col.SCENARIO_RELATIVE, col.DESCRIPTOR_FIXTURE_RELATIVE, col.APPROVED_RUNS_RELATIVE):
            target = self.checkout.joinpath(*relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO.joinpath(*relative.split("/")), target)
        self.scenario = self.checkout.joinpath(*col.SCENARIO_RELATIVE.split("/"))
        self.capture = tmp_path / "private" / "capture"
        self.scratch = tmp_path / "private" / "scratch"
        self.normal = tmp_path / "normal"
        self.staging = tmp_path / "private" / "staging"
        self.quarantine = tmp_path / "private" / "quarantine"
        self.sanitized = tmp_path / "public" / "sanitized"
        for root in (self.capture, self.scratch, self.normal):
            root.mkdir(parents=True)
        self.host = host_mod.FakeHost(tmp_path / "host", options or host_mod.FakeHostOptions())
        monkeypatch.setattr(gather, "PLAN117_V5_CHECKOUT_ROOT", self.checkout)
        monkeypatch.setattr(gather, "_plan117_v5_checkout_head", lambda root: COMMIT)
        monkeypatch.setattr(gather, "PLAN117_V5_HOST_ACTIONS_FACTORY", lambda checkout: self.host.actions())
        monkeypatch.setattr(gather, "PLAN117_V5_IDENTITY_TOKENS_FACTORY", lambda: ())

    def main(self, *argv: str, capsys=None) -> int:
        return gather.main([str(item) for item in argv])

    def bind(self):
        return ("--bind", f"run_id={RUN_ID}")

    def register_run(self, **overrides) -> None:
        from evidence_handoff.collector.scenarios import load_scenario, resolve_bindings, scenario_sha256

        scenario = load_scenario(self.scenario)
        key = col.load_run_key(self.capture / RUN_ID)
        spec = {
            "run_id": RUN_ID, "evidence_kind": c.EVIDENCE_KIND_GATE, "scenario_id": c.SCENARIO_ID,
            "scenario_source_sha256": hashlib.sha256(self.scenario.read_bytes()).hexdigest(),
            "scenario_sha256": scenario_sha256(scenario, resolve_bindings(scenario, (f"run_id={RUN_ID}",))),
            "descriptor_fixture_sha256": col.load_descriptor_fixture(self.checkout)[1],
            "patch_sha256s": {kind: col.patch_sha256(kind, c.default_descriptor_fixture()) for kind in c.SOURCE_KINDS},
            "source_commit": COMMIT, "source_tree": host_mod.SOURCE_TREE, "required_modules": sorted(c.REQUIRED_MODULE_PATHS),
            "client": {"executable_sha256": hashlib.sha256(b"fake-zed-binary").hexdigest(), "app_version": "1.27.0", "source_revision": "c84af5b99cbc366d675064e52b23664a015b6e35"},
            "launch_config_sha256": col.LAUNCH_CONFIG_SHA256, "arm_ids": list(c.ARM_IDS), "approval_id": "approval-p117v5-0001",
            "approval_not_before": "2026-11-20T09:00:00Z", "approval_not_after": "2026-11-20T18:00:00Z",
            "budget_policy_sha256": hashlib.sha256(b"budget").hexdigest(),
            "private_root_commitments": col.private_root_commitments(self.capture, key),
        }
        spec.update(overrides)
        registry = {"schema": c.RUN_REGISTRY_SCHEMA, "runs": [{"run_spec": spec, "run_spec_sha256": c.sha256_hex(c.canonical_json_bytes(spec))}]}
        self.checkout.joinpath(*col.APPROVED_RUNS_RELATIVE.split("/")).write_bytes(c.canonical_json_bytes(registry))
        self.write_invocation()

    def write_invocation(self, **overrides) -> Path:
        record = {
            "schema": col.INVOCATION_RECORD_SCHEMA, "run_id": RUN_ID, "checkout_commit": COMMIT,
            "scenario_blob_sha1": col.git_blob_sha1(self.scenario.read_bytes()),
            "registry_blob_sha1": col.git_blob_sha1(self.checkout.joinpath(*col.APPROVED_RUNS_RELATIVE.split("/")).read_bytes()),
            "descriptor_fixture_blob_sha1": col.git_blob_sha1(self.checkout.joinpath(*col.DESCRIPTOR_FIXTURE_RELATIVE.split("/")).read_bytes()),
        }
        record.update(overrides)
        self.invocation = self.tmp / "reviewed" / "invocation.json"
        self.invocation.parent.mkdir(exist_ok=True)
        self.invocation.write_bytes(c.canonical_json_bytes(record))
        return self.invocation

    def prepare(self) -> int:
        return self.main("prepare", "--scenario", self.scenario, "--capture-root", self.capture, *self.bind())

    def collect(self) -> int:
        return self.main("collect", "--scenario", self.scenario, "--capture-root", self.capture, *self.bind(),
                         "--invocation-record", self.invocation, "--normal-source-root", self.normal, "--scratch-parent", self.scratch)

    def classify(self) -> int:
        return self.main("classify", "--scenario", self.scenario, "--capture-root", self.capture, *self.bind(), "--result", self.tmp / "private" / "classify.json")

    def redact(self, receipt: Path | None = None) -> int:
        extra = () if receipt is None else ("--review-receipt", receipt)
        return self.main("redact", "--scenario", self.scenario, "--capture-root", self.capture, *self.bind(),
                         "--staging-root", self.staging, "--quarantine-root", self.quarantine, "--sanitized-root", self.sanitized,
                         "--result", self.tmp / "private" / "redact.json", *extra)

    def through_classify(self) -> None:
        assert self.prepare() == 0
        self.register_run()
        assert self.main("check", "--scenario", self.scenario, "--capture-root", self.capture, *self.bind()) == 0
        assert self.collect() == 0
        assert self.classify() == 0

    def receipt(self, **overrides) -> Path:
        staged = col.compute_redaction(self.context(), identity_tokens=())
        raw = staged.raw
        document = {
            "schema": c.RECEIPT_SCHEMA, "verdict": "accepting", "reviewer_identity": "private-reviewer",
            "reviewer_session": "review-session-1", "reviewer_model": "operator-private-review", "reviewed_at": "2026-11-21T09:00:00Z",
            "run_id": raw.run_id, "scenario_id": raw.scenario_id, "scenario_sha256": raw.scenario_sha256,
            "source_commit": raw.source.actual_source_commit, "raw_manifest_sha256": staged.raw_manifest_sha256,
            "raw_bundle_sha256": raw.raw_bundle_sha256, "sanitized_manifest_sha256": c.sha256_hex(staged.sanitized_bytes),
            "mapping_sha256": staged.mapping_sha256,
            "derivatives": [{"locator": "manifest.json", "sha256": c.sha256_hex(staged.sanitized_bytes)}],
            "redaction_report_sha256": c.sha256_hex(staged.report_bytes),
        }
        document.update(overrides)
        path = self.tmp / "reviewed" / "receipt.json"
        path.write_bytes(c.canonical_json_bytes(document))
        return path

    def context(self):
        from evidence_handoff.collector.models import RunContext

        manifest = json.loads((self.capture / RUN_ID / "run-manifest.json").read_text(encoding="utf-8"))
        return RunContext(schema="evidence-run-v1", scenario_id=manifest["scenario_id"], run_id=RUN_ID,
                          scenario_sha256=manifest["scenario_sha256"], capture_root=self.capture.resolve(), monotonic_origin_ns=manifest["monotonic_origin_ns"])


def _out(capsys):
    captured = capsys.readouterr()
    return captured.out, captured.err


# --------------------------------------------------------------------------- scenario authority


def test_validate_accepts_only_the_registered_checkout_scenario(tmp_path, monkeypatch, capsys):
    pipeline = Pipeline(tmp_path, monkeypatch)
    assert pipeline.main("validate", "--scenario", pipeline.scenario, *pipeline.bind()) == 0
    summary = json.loads(_out(capsys)[0])
    assert summary["scenario_id"] == c.SCENARIO_ID and summary["collection_adapter_ids"] == [col.COLLECTOR_ID]
    copy = tmp_path / "elsewhere.toml"
    shutil.copyfile(pipeline.scenario, copy)
    assert pipeline.main("validate", "--scenario", copy, *pipeline.bind()) == 2
    assert _out(capsys)[1].strip() == "plan117_v5_scenario_unregistered"


def test_committed_repository_scenario_is_the_registered_one(capsys):
    assert gather.main(["validate", "--scenario", str(REPO / col.SCENARIO_RELATIVE), "--bind", f"run_id={RUN_ID}"]) == 0


def test_repeated_scenario_flag_is_refused_for_routing(tmp_path, monkeypatch, capsys):
    pipeline = Pipeline(tmp_path, monkeypatch)
    legacy = REPO / "tests" / "fixtures" / "evidence" / "scenarios" / "zed-session.toml"
    assert pipeline.main("collect", "--scenario", legacy, "--scenario", pipeline.scenario, "--capture-root", pipeline.capture) == 2
    assert _out(capsys)[1].strip() == "repeated_scenario_flag"


# --------------------------------------------------------------------------- prepare / check / collect


def test_prepare_uses_the_bound_run_id_and_creates_the_private_key_once(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    pipeline = Pipeline(tmp_path, monkeypatch)
    assert pipeline.prepare() == 0
    summary = json.loads(_out(capsys)[0])
    run_dir = pipeline.capture / RUN_ID
    assert (run_dir / "run-manifest.json").is_file() and (run_dir / "fixture-marker.json").is_file()
    key = col.load_run_key(run_dir)
    assert summary == {"run_id": RUN_ID, "private_root_commitments": col.private_root_commitments(pipeline.capture, key)}
    assert key.hex() not in json.dumps(summary)
    assert pipeline.prepare() == 0
    assert col.load_run_key(run_dir) == key


def test_prepare_rejects_a_malformed_run_id(tmp_path, monkeypatch, capsys):
    pipeline = Pipeline(tmp_path, monkeypatch)
    assert pipeline.main("prepare", "--scenario", pipeline.scenario, "--capture-root", pipeline.capture, "--bind", "run_id=../escape-xx") == 2
    assert _out(capsys)[1].strip() == "plan117_v5_run_id_invalid"


def test_full_pipeline_collects_once_and_never_appends(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    pipeline = Pipeline(tmp_path, monkeypatch)
    pipeline.through_classify()
    run_dir = pipeline.capture / RUN_ID
    bundle = json.loads((run_dir / "raw-bundle.json").read_text(encoding="utf-8"))
    assert [batch["collector_id"] for batch in bundle["batches"]] == [col.COLLECTOR_ID]
    assert (run_dir / "provisional-result.json").is_file()
    before = (run_dir / "raw-bundle.json").read_bytes()
    launches = list(pipeline.host.launches)
    capsys.readouterr()
    assert pipeline.collect() == 2
    assert _out(capsys)[1].strip() == "run_already_collected"
    assert (run_dir / "raw-bundle.json").read_bytes() == before and pipeline.host.launches == launches


def test_collect_requires_a_registered_run(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    pipeline = Pipeline(tmp_path, monkeypatch)
    assert pipeline.prepare() == 0
    pipeline.write_invocation()
    capsys.readouterr()
    assert pipeline.collect() == 2
    assert _out(capsys)[1].strip() == "run_not_registered"
    assert pipeline.host.launches == []


@pytest.mark.parametrize("overrides,code", [({"registry_blob_sha1": "0" * 40}, "invocation_record_mismatch"), ({"checkout_commit": "f" * 40}, "invocation_record_mismatch")])
def test_collect_requires_the_reviewed_invocation_record(tmp_path, monkeypatch, capsys, windows_shaped_paths, overrides, code):
    pipeline = Pipeline(tmp_path, monkeypatch)
    assert pipeline.prepare() == 0
    pipeline.register_run()
    pipeline.write_invocation(**overrides)
    capsys.readouterr()
    assert pipeline.collect() == 2
    assert _out(capsys)[1].strip() == code
    assert pipeline.host.launches == []


def test_bundle_cannot_register_itself(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    pipeline = Pipeline(tmp_path, monkeypatch)
    assert pipeline.prepare() == 0
    pipeline.register_run()
    planted = pipeline.capture / RUN_ID / "plan-11-7-v5-approved-runs.json"
    planted.write_bytes(pipeline.checkout.joinpath(*col.APPROVED_RUNS_RELATIVE.split("/")).read_bytes())
    pipeline.checkout.joinpath(*col.APPROVED_RUNS_RELATIVE.split("/")).write_bytes(c.canonical_json_bytes({"schema": c.RUN_REGISTRY_SCHEMA, "runs": []}))
    pipeline.write_invocation()
    capsys.readouterr()
    assert pipeline.collect() == 2
    assert _out(capsys)[1].strip() == "run_not_registered"


def test_classify_writes_only_a_generic_custody_result(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    pipeline = Pipeline(tmp_path, monkeypatch, host_mod.FakeHostOptions(reopen_load_arm="a_prime"))
    pipeline.through_classify()
    result = json.loads((tmp_path / "private" / "classify.json").read_text(encoding="utf-8"))
    assert result["outcome"] not in {d.value for d in D}


# --------------------------------------------------------------------------- redact


def test_redact_stages_then_promotes_only_with_an_accepting_receipt(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    pipeline = Pipeline(tmp_path, monkeypatch)
    pipeline.through_classify()
    capsys.readouterr()
    assert pipeline.redact() == 0
    staged = json.loads((tmp_path / "private" / "redact.json").read_text(encoding="utf-8"))
    assert staged["status"] == "awaiting_review" and staged["gate"]["disposition"] == D.ACCEPTED_CURRENT_CLIENT_GATE.value
    assert not pipeline.sanitized.exists() or list(pipeline.sanitized.iterdir()) == []
    rejecting = pipeline.receipt(verdict="rejecting")
    assert pipeline.redact(rejecting) == 2
    assert _out(capsys)[1].strip() == "receipt_not_accepting"
    (tmp_path / "private" / "redact.json").unlink()
    assert pipeline.redact(pipeline.receipt()) == 0
    assert sorted(p.name for p in (pipeline.sanitized / RUN_ID).iterdir()) == ["manifest.json", "redaction-attestation.json", "redaction-report.json"]


@pytest.mark.parametrize("which", ["staging", "quarantine"])
def test_redact_refuses_overlapping_custody_roots(tmp_path, monkeypatch, capsys, windows_shaped_paths, which):
    pipeline = Pipeline(tmp_path, monkeypatch)
    pipeline.through_classify()
    setattr(pipeline, which, pipeline.sanitized)
    capsys.readouterr()
    assert pipeline.redact() == 2
    assert _out(capsys)[1].strip() == "path_overlap"


def test_redact_refuses_private_roots_inside_the_reviewed_checkout(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    pipeline = Pipeline(tmp_path, monkeypatch)
    pipeline.through_classify()
    pipeline.staging = pipeline.checkout / "tmp-staging"
    capsys.readouterr()
    assert pipeline.redact() == 2
    assert _out(capsys)[1].strip() == "private_root_inside_checkout"


def test_receipt_inside_the_sanitized_root_is_refused(tmp_path, monkeypatch, capsys, windows_shaped_paths):
    pipeline = Pipeline(tmp_path, monkeypatch)
    pipeline.through_classify()
    assert pipeline.redact() == 0
    receipt = pipeline.receipt()
    pipeline.sanitized.mkdir(parents=True, exist_ok=True)
    planted = pipeline.sanitized / "receipt.json"
    shutil.copyfile(receipt, planted)
    (tmp_path / "private" / "redact.json").unlink()
    capsys.readouterr()
    assert pipeline.redact(planted) == 2
    assert _out(capsys)[1].strip() == "receipt_inside_promoted_root"


# --------------------------------------------------------------------------- legacy behaviour


def test_legacy_parser_and_registry_are_unchanged_for_other_scenarios():
    parser = gather.build_parser()
    choices = next(action for action in parser._actions if action.dest == "command").choices
    assert sorted(choices) == ["check", "classify", "collect", "inspect", "prepare", "redact", "validate"]
    collect = choices["collect"]
    assert {action.dest for action in collect._actions} >= {"workspace_root", "agent_executable", "prompt", "correlate_session_id"}
    assert "invocation_record" not in {action.dest for action in collect._actions}


def test_legacy_prepare_still_allocates_a_fresh_run_id(tmp_path, capsys):
    scenario = REPO / "tests" / "fixtures" / "evidence" / "scenarios" / "plan117-server-custody.toml"
    capture = tmp_path / "capture"
    assert gather.main(["prepare", "--scenario", str(scenario), "--capture-root", str(capture), "--bind", "model=test-model"]) == 0
    runs = [p.name for p in capture.iterdir()]
    assert len(runs) == 1 and len(runs[0]) == 32 and not (capture / runs[0] / col.PATH_KEY_LOCATOR).exists()
