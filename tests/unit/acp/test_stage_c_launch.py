"""Plan 12.2 Task 13 (Stage C): the shared test envelope through approval, host resolution and the Gateway
start (Codex scope agreement, 2026-10-11, section 2).

A Stage C launch names one of the release's test profiles and binds the envelope literal into its HMAC
approval beside the profile's registry literal; the release ceremony (``optimus-trust approve
--plan12-stage-c``) creates the ledger once and never resets it; the host recomposes the envelope from
source and its trusted runtime root, refuses a launch the approval did not bind or whose ledger does not
exist before any service starts, and starts its own Gateway with the ledger path and the signed envelope.
The Gateway composes the same literal from the same path. No real service, keyring or provider.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from optimus.acp import __main__ as acp_main
from optimus.acp import launch_approval_cli as trust_cli
from optimus.acp.launch_approvals import KeyringApprovalStore
from optimus.acp.launch_gate import LaunchGateError, authorize_launch, resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.operator_paths import resolve_authorized_operator_paths
from optimus.acp.trusted_paths import resolve_workspace_security_state
from optimus_model_policy import stage_c
from optimus_model_policy.binding import APPROVAL_LITERAL_NAME
from optimus_model_policy.stage_c import STAGE_C_LITERAL_NAME
from tests.unit.acp import test_test_composition as composition_tests
from tests.unit.acp.conftest import FakeKeyring, authorize_workspace_for_test
from tests.unit.acp.test_test_composition import _ENV

pytestmark = pytest.mark.usefixtures("isolated_windows_known_folders")

launch = composition_tests.launch  # the shared host-launch fixture (Redis, Gateway and server faked)


def _candidate(workspace: Path, keyring: FakeKeyring, *, test_profile: str | None, stage_c_flag: bool):
    snapshot = LaunchEnvironmentSnapshot.capture(_ENV)
    paths = resolve_authorized_operator_paths(workspace_root=workspace, snapshot_values=snapshot.values, platform_name=sys.platform)
    store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=workspace / ".optimus-runtime")
    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_state=resolve_workspace_security_state(workspace),
        operator_paths=paths,
        hmac_key=store.hmac_key,
        test_profile=test_profile,
        stage_c=stage_c_flag,
    )
    return candidate, store


def _ledger(workspace: Path) -> Path:
    return stage_c.stage_c_ledger_path((workspace / ".optimus").resolve())


# --- Approval binding ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("profile", ["qualification", "attached"])
def test_a_stage_c_launch_binds_the_envelope_beside_the_profile(tmp_path: Path, profile: str) -> None:
    keyring = FakeKeyring()
    plain, _ = _candidate(tmp_path, keyring, test_profile=profile, stage_c_flag=False)
    staged, _ = _candidate(tmp_path, keyring, test_profile=profile, stage_c_flag=True)

    envelope = stage_c.compose_stage_c_envelope(ledger=_ledger(tmp_path))
    assert staged.security_literals[STAGE_C_LITERAL_NAME] == envelope.literal
    assert staged.security_literals[APPROVAL_LITERAL_NAME] == plain.security_literals[APPROVAL_LITERAL_NAME]
    assert STAGE_C_LITERAL_NAME not in plain.security_literals
    assert staged.security_snapshot_digest != plain.security_snapshot_digest
    [row] = [row for row in staged.display_rows if row.name == STAGE_C_LITERAL_NAME]
    assert (row.display_value, row.decision) == (envelope.literal, "requires exact approval") and "$0.50" in row.source_class


def test_both_profile_launches_bind_one_shared_envelope(tmp_path: Path) -> None:
    keyring = FakeKeyring()
    qualification, _ = _candidate(tmp_path, keyring, test_profile="qualification", stage_c_flag=True)
    attached, _ = _candidate(tmp_path, keyring, test_profile="attached", stage_c_flag=True)
    assert qualification.security_literals[STAGE_C_LITERAL_NAME] == attached.security_literals[STAGE_C_LITERAL_NAME]


def test_a_stage_c_launch_needs_a_stage_c_profile(tmp_path: Path) -> None:
    with pytest.raises(LaunchGateError) as caught:
        _candidate(tmp_path, FakeKeyring(), test_profile=None, stage_c_flag=True)
    assert caught.value.code == "STAGE_C_NEEDS_TEST_PROFILE"


@pytest.mark.parametrize(("approved", "launched"), [(False, True), (True, False)], ids=["profile-only-approval", "stage-c-approval"])
def test_an_approval_with_or_without_the_envelope_authorizes_only_its_own_launch(tmp_path: Path, approved: bool, launched: bool) -> None:
    keyring = FakeKeyring()
    authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring, test_profile="attached", stage_c=approved)
    other, store = _candidate(tmp_path, keyring, test_profile="attached", stage_c_flag=launched)
    with pytest.raises(LaunchGateError) as caught:
        authorize_launch(candidate=other, store=store, launch_session_id="s1")
    assert caught.value.code == "SNAPSHOT_MISMATCH"


def test_the_gateway_composes_the_same_envelope_from_the_ledger_it_is_given(tmp_path: Path) -> None:
    staged, _ = _candidate(tmp_path, FakeKeyring(), test_profile="attached", stage_c_flag=True)
    assert stage_c.compose_stage_c_envelope(ledger=Path(str(_ledger(tmp_path)))).literal == staged.security_literals[STAGE_C_LITERAL_NAME]


# --- The release ceremony creates the ledger once -------------------------------------------------------------


def _approve(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, stage_c_flag: bool, profile: str = "attached") -> tuple[int, Path]:
    """The release ceremony through the CLI's own `_cmd_approve`, as the existing approval tests drive it."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    (tmp_path / "config").mkdir(exist_ok=True)
    for name, value in {**_ENV, "OPTIMUS_CONFIG_ROOT": str(tmp_path / "config")}.items():
        monkeypatch.setenv(name, value)
    store = KeyringApprovalStore(keyring_backend=FakeKeyring(), runtime_root=tmp_path / "approval-runtime")
    monkeypatch.setattr(trust_cli, "_require_tty", lambda: None)
    monkeypatch.setattr(trust_cli, "_resolve_store", lambda _workspace: (store, tmp_path / "approval-runtime"))
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    return trust_cli._cmd_approve(workspace, mode="durable", target_argv=[], test_profile=profile, stage_c=stage_c_flag), workspace


def test_the_approval_ceremony_creates_the_ledger_once_and_never_resets_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    code, workspace = _approve(monkeypatch, tmp_path, stage_c_flag=True)
    assert code == 0
    ledger = _ledger(workspace)
    [init] = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert init["kind"] == "init" and init["envelope"] == stage_c.compose_stage_c_envelope(ledger=ledger).literal
    assert "Stage C ledger initialized" in capsys.readouterr().out

    window = {"kind": "window", "start": "2026-10-12T09:00:00+00:00", "deadline": "2026-10-12T10:00:00+00:00"}
    ledger.write_bytes(ledger.read_bytes() + json.dumps(window).encode("utf-8") + b"\n")
    before = ledger.read_bytes()
    code, _ = _approve(monkeypatch, tmp_path, stage_c_flag=True, profile="qualification")
    assert code == 0 and ledger.read_bytes() == before  # a fresh approval is not a new grant
    assert "kept as it is (never reset)" in capsys.readouterr().out


def test_an_approval_without_the_envelope_creates_no_ledger(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    code, workspace = _approve(monkeypatch, tmp_path, stage_c_flag=False)
    assert code == 0 and not _ledger(workspace).exists()


# --- Host launch ------------------------------------------------------------------------------------------------


def test_stage_c_needs_a_test_profile_at_the_parser(capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        acp_main.parse_args(["--plan12-stage-c"])
    assert caught.value.code == 2 and "--plan12-stage-c needs --plan12-test-profile" in capsys.readouterr().err


def _gateway_kwargs(monkeypatch: pytest.MonkeyPatch, started: list) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    class _Gateway:
        def stop(self):
            started.append(("gateway-stopped",))

    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: calls.append(k) or started.append(("gateway",)) or _Gateway())
    return calls


def test_a_stage_c_launch_without_its_ledger_stops_before_any_service(launch, tmp_path: Path, capsys) -> None:
    keyring, started = launch
    authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring, test_profile="attached", stage_c=True)

    assert acp_main.main(["--workspace-root", str(tmp_path), "--plan12-test-profile", "attached", "--plan12-stage-c"]) == 2
    assert "STAGE_C_LEDGER_MISSING" in capsys.readouterr().err and started == []


def test_a_stage_c_launch_with_a_profile_only_approval_stops_before_any_service(launch, tmp_path: Path) -> None:
    keyring, started = launch
    authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring, test_profile="attached")
    assert acp_main.main(["--workspace-root", str(tmp_path), "--plan12-test-profile", "attached", "--plan12-stage-c"]) == 2
    assert started == []


@pytest.mark.parametrize("profile", ["qualification", "attached"])
def test_an_approved_stage_c_launch_starts_its_gateway_on_the_envelope_and_hands_it_to_the_server(
    launch, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, profile: str
) -> None:
    keyring, started = launch
    candidate = authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring, test_profile=profile, stage_c=True)
    ledger = _ledger(tmp_path)
    stage_c.initialize_stage_c_ledger(ledger, stage_c.compose_stage_c_envelope(ledger=ledger))
    calls = _gateway_kwargs(monkeypatch, started)
    servers: list[dict[str, Any]] = []

    class _Server:
        async def serve_ndjson(self, *args, **kwargs):
            return None

    monkeypatch.setattr(acp_main, "build_configured_server", lambda **k: servers.append(k) or _Server())

    assert acp_main.main(["--workspace-root", str(tmp_path), "--plan12-test-profile", profile, "--plan12-stage-c"]) == 0
    [gateway] = calls
    assert (gateway["stage_c_envelope"], gateway["stage_c_ledger"]) == (candidate.security_literals[STAGE_C_LITERAL_NAME], ledger)
    assert gateway["test_profile"] == profile
    [server] = servers
    assert server["stage_c"].ledger == ledger and server["stage_c"].envelope.literal == gateway["stage_c_envelope"]


def test_without_stage_c_the_profile_launch_is_unchanged(launch, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    keyring, started = launch
    authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring, test_profile="attached")
    calls = _gateway_kwargs(monkeypatch, started)
    assert acp_main.main(["--workspace-root", str(tmp_path), "--plan12-test-profile", "attached"]) == 0
    [gateway] = calls
    assert (gateway["stage_c_envelope"], gateway["stage_c_ledger"]) == (None, None)


# --- The Gateway child ------------------------------------------------------------------------------------------


def test_the_gateway_child_gets_the_ledger_path_and_a_version_three_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from tests.unit.acp.test_local_infra_model_registry import _spawned_args  # the existing child-argv harness

    ledger = _ledger(tmp_path)
    envelope = stage_c.compose_stage_c_envelope(ledger=ledger).literal
    argv = _spawned_args(tmp_path, monkeypatch, model_registry="optimus-model-registry-v1:" + "c" * 64, test_profile="attached", stage_c_envelope=envelope, stage_c_ledger=ledger)

    assert argv[argv.index("--plan12-stage-c-ledger") + 1] == str(ledger)
    manifest = json.loads(argv[argv.index("--manifest") + 1])
    assert (manifest["schema_version"], manifest["stage_c_envelope"]) == (3, envelope)
