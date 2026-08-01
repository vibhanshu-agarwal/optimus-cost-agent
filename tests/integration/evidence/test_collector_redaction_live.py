"""Live OS-keyring + public-gate proof for collector redact stage.

Uses the real OS credential-store backend for credential resolution. Durable
approval records use an in-memory FakeKeyring so the test does not mutate OS
approval state. Never prints or persists credential values.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import keyring
import pytest
from PIL import Image, PngImagePlugin

from evidence_handoff.collector.bundles import write_provisional_result, write_raw_bundle
from evidence_handoff.collector.models import (
    CapturedArtifact,
    ClassificationResult,
    CollectionBatch,
    Observation,
    Outcome,
    RunContext,
)
from evidence_handoff.redaction.gate import promote_approved_screenshot
from evidence_handoff.redaction.models import Disposition, RedactionGateResult
from optimus.acp.launch_approvals import KeyringApprovalStore, build_approval_record
from optimus.acp.launch_gate import resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.operator_paths import bootstrap_workspace_runtime_root, resolve_authorized_operator_paths
from optimus.acp.trusted_paths import resolve_workspace_identity
from tests.unit.acp.conftest import FakeKeyring
from tools.evidence_gather_support import redaction as redaction_mod
from tools.evidence_gather_support.common import HostError

pytestmark = pytest.mark.requires_os_keyring

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "evidence" / "scenarios" / "zed-session.toml"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _prepare_run(tmp_path: Path) -> tuple[Path, Path, Path, RunContext]:
    import tools.evidence_gather as gather

    capture = (tmp_path / "capture").resolve()
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    (workspace / ".git").mkdir()
    assert (
        gather.main(
            [
                "prepare",
                "--scenario",
                str(FIXTURE.resolve()),
                "--capture-root",
                str(capture),
                "--bind",
                "model=operator-supplied",
            ]
        )
        == 0
    )
    run_dir = next(path for path in capture.iterdir() if path.is_dir())
    manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
    context = RunContext(
        schema="evidence-run-v1",
        scenario_id=str(manifest["scenario_id"]),
        run_id=str(manifest["run_id"]),
        scenario_sha256=str(manifest["scenario_sha256"]),
        capture_root=capture,
        monotonic_origin_ns=int(manifest["monotonic_origin_ns"]),
    )
    return capture, workspace, run_dir, context


def _seed_artifacts(context: RunContext, run_dir: Path, *, secret: str) -> None:
    artifacts: list[CapturedArtifact] = []
    observations: list[Observation] = []

    text_rel = "artifacts/note.txt"
    text_path = run_dir / text_rel
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_body = f"safe live note containing {secret}\n".encode()
    text_path.write_bytes(text_body)
    artifacts.append(
        CapturedArtifact(
            role="zed_log",
            media_type="text/plain",
            relative_locator=text_rel,
            sha256=_sha256(text_body),
            size_bytes=len(text_body),
        )
    )

    json_rel = "artifacts/panic.json"
    json_path = run_dir / json_rel
    json_body = json.dumps({"ok": True, "note": "live"}).encode()
    json_path.write_bytes(json_body)
    artifacts.append(
        CapturedArtifact(
            role="zed_panic_json",
            media_type="application/json",
            relative_locator=json_rel,
            sha256=_sha256(json_body),
            size_bytes=len(json_body),
        )
    )

    png_rel = "artifacts/shot.png"
    png_path = run_dir / png_rel
    img = Image.new("RGB", (12, 12), color=(11, 22, 33))
    info = PngImagePlugin.PngInfo()
    info.add_text("Author", "LIVE_PNG_TEXT_CANARY")
    img.save(png_path, pnginfo=info)
    png_bytes = png_path.read_bytes()
    artifacts.append(
        CapturedArtifact(
            role="screenshot",
            media_type="image/png",
            relative_locator=png_rel,
            sha256=_sha256(png_bytes),
            size_bytes=len(png_bytes),
        )
    )

    dump_rel = "artifacts/crash.dmp"
    dump_path = run_dir / dump_rel
    dump_body = b"MDMP" + b"\x00" * 64 + secret.encode()
    dump_path.write_bytes(dump_body)
    artifacts.append(
        CapturedArtifact(
            role="zed_process_dump",
            media_type="application/octet-stream",
            relative_locator=dump_rel,
            sha256=_sha256(dump_body),
            size_bytes=len(dump_body),
        )
    )

    for index, artifact in enumerate(artifacts):
        observations.append(
            Observation(
                schema="evidence-observation-v1",
                scenario_id=context.scenario_id,
                run_id=context.run_id,
                collector_id="live_redact_seed",
                sequence=index,
                monotonic_offset_ns=index + 1,
                observed_at="1970-01-01T00:00:00+00:00",
                observation_kind="live_seed",
                correlation=(),
                artifact_role=artifact.role,
                artifact_sha256=artifact.sha256,
                reason_code=None,
            )
        )

    batch = CollectionBatch(
        collector_id="live_redact_seed",
        contract_version="v1",
        observations=tuple(observations),
        artifacts=tuple(artifacts),
    )
    bundle_path = write_raw_bundle(context=context, batches=(batch,))
    bundle_digest = json.loads(bundle_path.read_text(encoding="utf-8"))["bundle_sha256"]
    write_provisional_result(
        context=context,
        result=ClassificationResult(
            schema="evidence-provisional-result-v1",
            scenario_id=context.scenario_id,
            run_id=context.run_id,
            outcome=Outcome.INDETERMINATE,
            claims=(),
            reason_codes=("live",),
            raw_bundle_sha256=str(bundle_digest),
        ),
    )


def _seed_durable(*, workspace: Path, env: dict[str, str], fake: FakeKeyring) -> None:
    snapshot = LaunchEnvironmentSnapshot.capture(env)
    paths = resolve_authorized_operator_paths(
        workspace_root=workspace,
        snapshot_values=snapshot.values,
        platform_name=__import__("sys").platform,
    )
    bootstrap_workspace_runtime_root(paths)
    store = KeyringApprovalStore(keyring_backend=fake, runtime_root=paths.runtime_root)
    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_identity=resolve_workspace_identity(workspace),
        operator_paths=paths,
        hmac_key=store.hmac_key,
        credential_keyring_backend=keyring,
    )
    record = build_approval_record(
        mode="durable",
        workspace_identity=candidate.workspace_identity,
        security_literals=candidate.security_literals,
        secret_fingerprints=candidate.secret_fingerprints,
        monotonic_grants=candidate.monotonic_grants,
        model_observation=candidate.model_observation,
        hmac_key=store.hmac_key,
    )
    store.write_durable(record)


def test_collector_redaction_live_os_keyring_and_public_gate(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tools.evidence_gather as gather

    capture, workspace, run_dir, _context = _prepare_run(tmp_path)
    secret = f"live-env-api-{uuid.uuid4().hex}"
    env = {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:9",
        "OPTIMUS_API_KEY": secret,
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": f"live-env-shared-{uuid.uuid4().hex}",
    }
    _seed_artifacts(_context, run_dir, secret=secret)
    raw_before = (run_dir / "raw-bundle.json").read_bytes()
    provisional_before = (run_dir / "provisional-result.json").read_bytes()

    user_data = (tmp_path / "user-data").resolve()
    staging = (tmp_path / "staging").resolve()
    quarantine = (tmp_path / "quarantine").resolve()
    sanitized = (tmp_path / "sanitized").resolve()
    forbidden = (tmp_path / "forbidden-extra").resolve()
    for path in (user_data, staging, quarantine, sanitized, forbidden):
        path.mkdir()
    report = (tmp_path / "report.json").resolve()
    result = (tmp_path / "result.json").resolve()

    assert keyring.get_keyring() is not None
    os_backend = keyring.get_keyring()
    os_backend_id = f"{type(os_backend).__module__}.{type(os_backend).__name__}"
    assert "keyring" in type(os_backend).__module__ or os_backend_id.startswith("keyring")

    fake_approvals = FakeKeyring()
    _seed_durable(workspace=workspace, env=env, fake=fake_approvals)

    empty = FakeKeyring()
    with pytest.raises(HostError) as missing:
        redaction_mod.authorize_redaction_launch(
            workspace_root=workspace,
            environ=env,
            keyring_backend=empty,
            credential_keyring_backend=keyring,
        )
    assert missing.value.code == "REDACTION_AUTHORIZATION_NO_DURABLE_APPROVAL"
    assert (run_dir / "raw-bundle.json").read_bytes() == raw_before
    assert (run_dir / "provisional-result.json").read_bytes() == provisional_before

    drifted = dict(env)
    drifted["OPTIMUS_API_KEY"] = f"drifted-{uuid.uuid4().hex}"
    with pytest.raises(HostError) as drift:
        redaction_mod.authorize_redaction_launch(
            workspace_root=workspace,
            environ=drifted,
            keyring_backend=fake_approvals,
            credential_keyring_backend=keyring,
        )
    assert drift.value.code == "REDACTION_AUTHORIZATION_SNAPSHOT_MISMATCH"
    assert (run_dir / "raw-bundle.json").read_bytes() == raw_before

    profile = redaction_mod.resolve_operator_profile_root()
    identities = redaction_mod.resolve_operator_identity_values()
    assert profile.is_absolute() and profile.exists()
    assert len(identities) >= 2

    real_authorize = redaction_mod.authorize_redaction_launch

    def authorize_live(**kwargs):
        return real_authorize(
            workspace_root=kwargs["workspace_root"],
            environ=env,
            keyring_backend=fake_approvals,
            credential_keyring_backend=keyring,
        )

    monkeypatch.setattr(redaction_mod, "authorize_redaction_launch", authorize_live)

    with caplog.at_level(logging.DEBUG):
        first = gather.main(
            [
                "redact",
                "--scenario",
                str(FIXTURE.resolve()),
                "--workspace-root",
                str(workspace),
                "--user-data-root",
                str(user_data),
                "--forbidden-root",
                str(forbidden),
                "--capture-root",
                str(capture),
                "--staging-root",
                str(staging),
                "--quarantine-root",
                str(quarantine),
                "--sanitized-root",
                str(sanitized),
                "--result",
                str(result),
                "--report",
                str(report),
                "--bind",
                "model=operator-supplied",
            ]
        )
    out1 = capsys.readouterr().out
    assert first == 0
    assert not report.exists()
    summary1 = json.loads(result.read_text(encoding="utf-8"))
    assert summary1["outcome"] == "indeterminate"
    assert Disposition.AWAITING_HUMAN_APPROVAL.value in summary1["dispositions"]
    assert Disposition.QUARANTINED.value in summary1["dispositions"]
    assert Disposition.PROMOTED.value in summary1["dispositions"]
    assert (run_dir / "provisional-result.json").read_bytes() == provisional_before
    assert (run_dir / "raw-bundle.json").read_bytes() == raw_before

    joined = "\n".join([out1, caplog.text, result.read_text(encoding="utf-8")])
    assert secret not in joined
    assert env["OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"] not in joined
    assert "AuthorizedLaunch" not in joined
    for identity in identities:
        assert identity not in joined

    staged_png = None
    for candidate in staging.rglob("*"):
        if not candidate.is_file():
            continue
        if candidate.read_bytes()[:8].startswith(b"\x89PNG\r\n\x1a\n"):
            staged_png = candidate
            break
    assert staged_png is not None, f"no staged PNG under {staging}"
    approval_path = (tmp_path / "screenshot-approval.json").resolve()
    approval_path.write_text(
        json.dumps(
            {
                "staged_sha256": _sha256(staged_png.read_bytes()),
                "approver_id": "live-approver",
                "collector_id": "live-collector",
                "approved_at": datetime.now(tz=UTC).isoformat(),
                "rationale": "independent live approval",
            }
        ),
        encoding="utf-8",
    )
    screenshot_approval = redaction_mod.load_screenshot_approval(approval_path)

    authorized = real_authorize(
        workspace_root=workspace,
        environ=env,
        keyring_backend=fake_approvals,
        credential_keyring_backend=keyring,
    )
    host = redaction_mod.build_redaction_host_context(
        authorized_launch=authorized,
        workspace_root=workspace,
        user_data_roots=(user_data,),
        temporary_capture_root=capture,
        staging_root=staging,
        quarantine_root=quarantine,
        operator_forbidden_roots=(forbidden,),
    )
    assert workspace in host.forbidden_persistence_roots
    assert forbidden in host.forbidden_persistence_roots
    assert host.operator_profile_root.is_dir()
    assert len(host.operator_identity_values) >= 2
    identity_count = len(host.operator_identity_values)
    profile_exists = host.operator_profile_root.exists()
    runtime = redaction_mod.convert_host_context(host)
    del authorized, host

    promoted_shot = promote_approved_screenshot(
        staging_path=staged_png,
        destination_root=sanitized,
        artifact_role="screenshot",
        runtime=runtime,
        approval=screenshot_approval,
    )
    assert promoted_shot.disposition is Disposition.PROMOTED
    assert promoted_shot.artifact_locator is not None
    assert not Path(promoted_shot.artifact_locator).is_absolute()

    assert not (run_dir / "artifacts" / "crash.dmp").exists()
    assert list(quarantine.rglob("process_dump-*.bin")), f"expected dump under {quarantine}"
    for artifact in sanitized.rglob("artifact"):
        assert secret.encode() not in artifact.read_bytes()

    assert (run_dir / "provisional-result.json").read_bytes() == provisional_before
    assert (run_dir / "raw-bundle.json").read_bytes() == raw_before

    gate_like = (
        RedactionGateResult(
            disposition=Disposition.PROMOTED,
            artifact_locator="<destination>/zed_log/artifact",
            manifest_locator="<destination>/zed_log/manifest.json",
            reason_code=None,
        ),
        RedactionGateResult(
            disposition=Disposition.PROMOTED,
            artifact_locator=promoted_shot.artifact_locator,
            manifest_locator=promoted_shot.manifest_locator,
            reason_code=None,
        ),
        RedactionGateResult(
            disposition=Disposition.QUARANTINED,
            artifact_locator=None,
            manifest_locator=None,
            reason_code="process_dump_quarantined",
        ),
    )
    assert redaction_mod.report_eligible(gate_like) is False

    cloudy = (tmp_path / "Dropbox" / "capture2").resolve()
    cloudy.mkdir(parents=True)
    with pytest.raises(HostError) as cloudy_err:
        redaction_mod.validate_redaction_custody_roots(
            workspace_root=workspace,
            capture_root=cloudy,
            staging_root=staging,
            quarantine_root=quarantine,
            sanitized_root=sanitized,
            user_data_roots=(user_data,),
            forbidden_roots=(forbidden,),
        )
    assert cloudy_err.value.code == "cloud_sync_path_segment"

    again = real_authorize(
        workspace_root=workspace,
        environ=env,
        keyring_backend=fake_approvals,
        credential_keyring_backend=keyring,
    )
    assert again.approval_mode == "durable"
    del again

    evidence = {
        "os_keyring_backend": os_backend_id,
        "approval_backend": f"{type(fake_approvals).__module__}.{type(fake_approvals).__name__}",
        "profile_source_class": "FOLDERID_Profile" if __import__("sys").platform == "win32" else "pwd.pw_dir",
        "identity_value_count": identity_count,
        "profile_exists": profile_exists,
        "forbidden_contains_workspace": True,
        "first_pass_dispositions": sorted(summary1["dispositions"]),
        "screenshot_promoted_after_independent_approval": True,
        "dump_hash_only_quarantined": True,
        "provisional_unchanged": True,
        "report_eligible_with_dump": False,
        "secret_canary_clean": True,
    }
    (tmp_path / "live-redaction-evidence.json").write_text(
        json.dumps(evidence, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert evidence["secret_canary_clean"] is True
    assert profile.is_absolute()
