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
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from keyring.errors import PasswordSetError

from optimus.acp import __main__ as acp_main
from optimus.acp import bootstrap
from optimus.acp import launch_approval_cli as trust_cli
from optimus.acp import server as acp_server
from optimus.acp import stage_c as host_stage_c
from optimus.acp.launch_approvals import KeyringApprovalStore
from optimus.acp.launch_gate import LaunchGateError, authorize_launch, resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.operator_paths import resolve_authorized_operator_paths
from optimus.acp.outbound_writer import DedicatedOutboundWriter as _REAL_DEDICATED_WRITER  # before the launch fixture stubs it
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
    assert (row.display_value, row.decision) == (envelope.literal, "requires exact approval")
    assert row.source_class == "stage-c-release:plan12-2-stage-c-r9:$8/138 attempts/60 min"  # the operator sees what is approved


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


@pytest.mark.parametrize(
    ("release_id", "limit_usd", "max_attempts"),
    [
        ("plan12-2-stage-c-r8", Decimal("8"), 138),
        ("plan12-2-stage-c-r7", Decimal("8"), 138),
        ("plan12-2-stage-c-r6", Decimal("8"), 138),
        ("plan12-2-stage-c-r5", Decimal("8"), 138),
        ("plan12-2-stage-c-r4", Decimal("8"), 138),
        ("plan12-2-stage-c-r3", Decimal("8"), 138),
        ("plan12-2-stage-c-r2", Decimal("8"), 138),
        ("plan12-2-stage-c-r1", Decimal("0.50"), 24),
    ],
    ids=["r8-same-limits", "r7-same-limits", "r6-same-limits", "r5-same-limits", "r4-same-limits", "r3-same-limits", "r2-same-limits", "r1"],
)
def test_an_approval_of_an_earlier_release_never_authorizes_an_r9_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, release_id: str, limit_usd: Decimal, max_attempts: int
) -> None:
    """Release r9 needs its own fresh bound approval: an approval of r8, r7, r6, r5, r4, r3 or r2 (the same $8 / 138
    attempts, their own ledgers and expired windows) or of the reviewed r1 ($0.50, 24 attempts) is refused for the
    r9 launch."""
    keyring = FakeKeyring()
    with monkeypatch.context() as earlier:
        earlier.setattr(stage_c, "STAGE_C_RELEASE_ID", release_id)
        earlier.setattr(stage_c, "STAGE_C_LIMIT_USD", limit_usd)
        earlier.setattr(stage_c, "STAGE_C_MAX_ATTEMPTS", max_attempts)
        authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring, test_profile="attached", stage_c=True)
    r8, store = _candidate(tmp_path, keyring, test_profile="attached", stage_c_flag=True)
    assert stage_c.STAGE_C_RELEASE_ID == "plan12-2-stage-c-r9"
    with pytest.raises(LaunchGateError) as caught:
        authorize_launch(candidate=r8, store=store, launch_session_id="s1")
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


# --- The L2 wiring proof (Codex's review f381e730, item 4) -------------------------------------------------------


class _FakeRedisRuntime:
    def ping(self):
        return None

    def sync_state_store(self):
        return self

    def telemetry_adapter(self):
        return object()

    def run_sync(self, operation, *, timeout=None):
        import asyncio

        return asyncio.run(operation())

    def close(self, *, timeout=None):
        return None


def test_the_generated_l2_host_arguments_wire_the_attached_stage_c_launch_and_answer_initialize(launch, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The schedule's generated attached (L2) host arguments run the real entrypoint in process, with a synthetic
    test-only approval and keyring, fake Redis and Gateway, in-memory stdio and an isolated ledger whose window is
    already open. The real attached Stage C composition is built, the debug trace lands in the workspace, ACP
    initialize is answered and the ledger and window are left as they were. Any real process, Gateway child,
    provider request or real keyring use fails it. Wiring only: not the human L2 ceremony, Zed attachment, the
    Redis lifecycle or real summary behaviour."""
    import io
    import subprocess
    import time

    import keyring as real_keyring

    from optimus.acp.debug_trace import reset_debug_trace_context
    from tools import plan12_stage_c_schedule as schedule_tool

    keyring, _started = launch
    # The launch gate reads provider credentials through the real keyring module unless given a backend; route that
    # module to the synthetic keyring before the approval is made, so neither the approval nor the launch can read
    # or write the operator's real credential store.
    store_calls: list[tuple[str, ...]] = []

    def synthetic(name: str):
        def call(service, key, *rest):
            store_calls.append((name, service, key))  # names only, never a value
            return getattr(keyring, name)(service, key, *rest)

        return call

    for name in ("get_password", "set_password", "delete_password"):
        monkeypatch.setattr(real_keyring, name, synthetic(name))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runbook = schedule_tool._runbook(schedule_tool.RunbookPaths(agent_exe=tmp_path / "optimus-agent.exe", workspace=workspace, evidence=tmp_path / "ev"))
    [l2] = [step for step in runbook["steps"] if step["title"] == "L2 Zed launch (attached)"]
    argv = json.loads(l2["commands"][0].removeprefix("Zed settings agent_servers Optimus: "))["args"]
    candidate = authorize_workspace_for_test(env=_ENV, workspace_root=workspace, fake_keyring=keyring, test_profile="attached", stage_c=True)
    ledger = _ledger(workspace)
    envelope = stage_c.compose_stage_c_envelope(ledger=ledger)
    stage_c.initialize_stage_c_ledger(ledger, envelope)
    stage_c.StageCGuard.open(ledger, envelope).close()  # the window opened at an earlier launch of this release
    before = ledger.read_bytes()
    assert ledger.is_relative_to(tmp_path) and b'"kind": "window"' in before.replace(b'"kind":"window"', b'"kind": "window"')

    def forbidden(*_args, **_kwargs):
        raise AssertionError("the L2 wiring proof reached a real process or provider")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr("optimus.gateway.client.urlopen", forbidden)
    monkeypatch.setattr("optimus.acp.preflight.run_preflight", lambda environ, **_kwargs: "redis://127.0.0.1:6379/0")
    monkeypatch.setattr("optimus.acp.bootstrap.RedisRuntime.from_url", lambda url: _FakeRedisRuntime())
    gateways = _gateway_kwargs(monkeypatch, [])
    attachments: list[tuple[dict, tuple]] = []
    real_attachment = host_stage_c.stage_c_attachment

    def attachment(**kwargs):
        result = real_attachment(**kwargs)
        attachments.append((kwargs, result))
        return result

    monkeypatch.setattr(host_stage_c, "stage_c_attachment", attachment)
    servers: list[tuple[dict, Any]] = []
    monkeypatch.setattr(acp_main, "build_configured_server", lambda **k: servers.append((k, bootstrap.build_configured_server(**k))) or servers[-1][1])
    request = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": 1, "clientCapabilities": {}}}
    stdout = io.BytesIO()

    class _Stdin:
        """The initialize line, then end of input only once a reply was written (or after 10 s), so the server
        never sees end of input before it answers."""

        def __init__(self) -> None:
            self.lines = [(json.dumps(request) + "\n").encode("utf-8")]

        def readline(self) -> bytes:
            if self.lines:
                return self.lines.pop(0)
            deadline = time.monotonic() + 10
            while not stdout.getvalue() and time.monotonic() < deadline:
                time.sleep(0.01)
            return b""

    stdin = _Stdin()
    monkeypatch.setattr(acp_main, "StdioNdjsonLineReader", lambda _stream: acp_server.StdioNdjsonLineReader(stdin))
    monkeypatch.setattr(acp_main, "StdioNdjsonLineWriter", lambda _stream: acp_server.StdioNdjsonLineWriter(stdout))
    monkeypatch.setattr("optimus.acp.outbound_writer.DedicatedOutboundWriter", _REAL_DEDICATED_WRITER)

    try:
        assert acp_main.main(argv) == 0
    finally:
        reset_debug_trace_context()

    [gateway] = gateways
    assert (gateway["test_profile"], gateway["stage_c_ledger"], gateway["stage_c_envelope"]) == ("attached", ledger, candidate.security_literals[STAGE_C_LITERAL_NAME])
    [(kwargs, server)] = servers
    assert kwargs["test_composition"].profile.name == "attached" and kwargs["stage_c"].ledger == ledger
    [(built, (context_attachment, seeder))] = attachments
    assert built["composition"] is kwargs["test_composition"] and context_attachment is not None and seeder is not None
    assert server._context_attachment is context_attachment
    [reply] = [json.loads(line) for line in stdout.getvalue().decode("utf-8").splitlines()]
    assert reply["id"] == 0 and reply["result"]["protocolVersion"] == 1 and "loadSession" not in reply["result"]["agentCapabilities"]
    trace = workspace.resolve() / ".optimus" / "debug-acp.ndjson"
    assert trace.is_file() and all(json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines())
    assert ledger.read_bytes() == before  # the ledger and its open window are untouched
    assert store_calls and all(call[0] == "get_password" for call in store_calls)  # served by the synthetic keyring, read-only


# --- The Gateway child ------------------------------------------------------------------------------------------


def test_the_gateway_child_gets_the_ledger_path_and_a_version_three_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from tests.unit.acp.test_local_infra_model_registry import _spawned_args  # the existing child-argv harness

    ledger = _ledger(tmp_path)
    envelope = stage_c.compose_stage_c_envelope(ledger=ledger).literal
    argv = _spawned_args(tmp_path, monkeypatch, model_registry="optimus-model-registry-v1:" + "c" * 64, test_profile="attached", stage_c_envelope=envelope, stage_c_ledger=ledger)

    assert argv[argv.index("--plan12-stage-c-ledger") + 1] == str(ledger)
    manifest = json.loads(argv[argv.index("--manifest") + 1])
    assert (manifest["schema_version"], manifest["stage_c_envelope"]) == (3, envelope)


# --- Plan 12.2 F1: the ceremony prepares the ledger before any approval is persisted ------------------------------


class _PersistFailingKeyring(FakeKeyring):
    """Fails approval persistence (`durable:`/`oneshot:` keys) only, before storing or after storing the record."""

    def __init__(self, *, store_first: bool) -> None:
        super().__init__()
        self.store_first = store_first

    def set_password(self, service: str, key: str, value: str) -> None:
        if key.startswith(("durable:", "oneshot:")):
            if self.store_first:
                super().set_password(service, key, value)
            raise PasswordSetError("simulated keyring backend failure")
        super().set_password(service, key, value)


def _ceremony(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    keyring: FakeKeyring,
    *,
    stage_c_flag: bool = True,
    mode: str = "durable",
    target_argv: tuple[str, ...] = (),
    answer: str = "y",
) -> tuple[object, Path, list[list[str]]]:
    """The release ceremony through the CLI's own `main` (so a typed refusal is its exit code and `optimus-trust:`
    message), set up as `_approve` does, with an injectable keyring, mode and target. A raw exception escaping `main`
    is returned as the outcome, so a test can assert on it like an exit code; spawns are recorded, never run."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    (tmp_path / "config").mkdir(exist_ok=True)
    for name, value in {**_ENV, "OPTIMUS_CONFIG_ROOT": str(tmp_path / "config")}.items():
        monkeypatch.setenv(name, value)
    store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=tmp_path / "approval-runtime")
    spawned: list[list[str]] = []
    monkeypatch.setattr(trust_cli, "_require_tty", lambda: None)
    monkeypatch.setattr(trust_cli, "_resolve_store", lambda _workspace: (store, tmp_path / "approval-runtime"))
    monkeypatch.setattr(trust_cli, "subprocess", SimpleNamespace(run=lambda argv, **_: spawned.append(argv) or SimpleNamespace(returncode=0)))
    monkeypatch.setattr("builtins.input", lambda _prompt: answer)
    try:
        argv = ["--workspace-root", str(workspace), "approve", "--mode", mode, "--plan12-test-profile", "attached"]
        argv += ["--plan12-stage-c"] if stage_c_flag else []
        outcome: object = trust_cli.main([*argv, *(["--", *target_argv] if target_argv else [])])
    except Exception as exc:  # noqa: BLE001 - the baseline's raw failure is the observed outcome
        outcome = exc
    return outcome, workspace, spawned


def _approval_keys(keyring: FakeKeyring) -> dict[str, str]:
    return {key: value for (_service, key), value in keyring._store.items() if key.startswith(("durable:", "oneshot:"))}


def _write_ledger(workspace: Path, *records: dict[str, Any], envelope_literal: str | None = None) -> Path:
    ledger = _ledger(workspace)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    envelope = stage_c.compose_stage_c_envelope(ledger=ledger)
    init = {"kind": "init", "envelope": envelope_literal or envelope.literal, "release_id": envelope.release_id, "limit_usd": str(envelope.limit_usd),
            "max_attempts": envelope.max_attempts, "window_seconds": envelope.window_seconds, "at": "2026-10-12T08:00:00+00:00"}  # fmt: skip
    ledger.write_bytes(b"".join(json.dumps(record).encode("utf-8") + b"\n" for record in (init, *records)))
    return ledger


@pytest.mark.parametrize("mode, target", [("durable", ()), ("one-shot", ()), ("one-shot", (sys.executable, "-c", "pass"))])
def test_a_ledger_that_cannot_be_created_refuses_before_any_approval_is_persisted(monkeypatch, tmp_path, capsys, mode, target) -> None:
    keyring = FakeKeyring()
    _ceremony(monkeypatch, tmp_path, keyring, stage_c_flag=False)  # an earlier, ordinary durable approval
    before = _approval_keys(keyring)
    capsys.readouterr()

    def unwritable(_path: Path, _envelope: object) -> None:
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(trust_cli, "initialize_stage_c_ledger", unwritable)
    outcome, _, spawned = _ceremony(monkeypatch, tmp_path, keyring, mode=mode, target_argv=target)

    assert outcome == 2
    assert "STAGE_C_LEDGER_WRITE_FAILED" in capsys.readouterr().err
    assert _approval_keys(keyring) == before  # the earlier durable approval is untouched, and nothing new exists
    assert spawned == []


def test_a_partly_written_ledger_is_refused_then_and_on_every_retry_and_never_reported_as_kept(monkeypatch, tmp_path, capsys) -> None:
    keyring = FakeKeyring()

    def failing_write(_handle: object, _record: object, _fsync: object) -> None:
        raise OSError(28, "No space left on device")

    with monkeypatch.context() as patch:
        patch.setattr(stage_c, "_write_record", failing_write)
        outcome, workspace, _ = _ceremony(monkeypatch, tmp_path, keyring)
    first = capsys.readouterr()
    ledger = _ledger(workspace)
    left = ledger.read_bytes()

    assert outcome == 2 and "STAGE_C_LEDGER_WRITE_FAILED" in first.err
    assert _approval_keys(keyring) == {}

    outcome, _, _ = _ceremony(monkeypatch, tmp_path, keyring)
    retry = capsys.readouterr()

    assert outcome == 2 and "STAGE_C_LEDGER_CORRUPT" in retry.err
    assert "kept as it is" not in retry.out
    assert ledger.read_bytes() == left and _approval_keys(keyring) == {}


@pytest.mark.parametrize(
    "records, code",
    [
        ([], "STAGE_C_LEDGER_ENVELOPE_MISMATCH"),
        ([{"kind": "halt", "reason": "operator halt"}], "STAGE_C_HALTED"),
        ([{"kind": "reserve", "n": 1, "attempt_id": "a-1", "reserve_usd": "0.10"}], "STAGE_C_HALTED"),
    ],
    ids=["another-envelope", "halted", "in-doubt"],
)
def test_an_existing_ledger_that_cannot_be_bound_is_refused_without_persisting_an_approval(monkeypatch, tmp_path, capsys, records, code) -> None:
    keyring = FakeKeyring()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    foreign = "plan12-stage-c-foreign-envelope" if code.endswith("MISMATCH") else None
    ledger = _write_ledger(workspace, *records, envelope_literal=foreign)
    before = ledger.read_bytes()

    outcome, _, _ = _ceremony(monkeypatch, tmp_path, keyring)

    assert outcome == 2 and code in capsys.readouterr().err
    assert ledger.read_bytes() == before and _approval_keys(keyring) == {}


def test_a_ledger_held_by_a_running_gateway_is_refused(monkeypatch, tmp_path, capsys) -> None:
    keyring = FakeKeyring()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = _write_ledger(workspace)
    held = stage_c._Lock(ledger.with_name(ledger.name + ".lock"))  # the lock a Gateway holds for its life
    try:
        outcome, _, _ = _ceremony(monkeypatch, tmp_path, keyring)
    finally:
        held.release()

    assert outcome == 2 and "STAGE_C_LEDGER_LOCKED" in capsys.readouterr().err
    assert _approval_keys(keyring) == {}


def test_an_unreadable_ledger_is_refused(monkeypatch, tmp_path, capsys) -> None:
    keyring = FakeKeyring()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = _write_ledger(workspace)
    ledger.with_name(ledger.name + ".lock").mkdir()  # the lock probe cannot open a directory: a real filesystem error

    outcome, _, _ = _ceremony(monkeypatch, tmp_path, keyring)

    assert outcome == 2 and "STAGE_C_LEDGER_UNREADABLE" in capsys.readouterr().err
    assert _approval_keys(keyring) == {}


def test_a_symlink_at_the_ledger_path_is_refused(monkeypatch, tmp_path, capsys) -> None:
    keyring = FakeKeyring()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = _ledger(workspace)
    ledger.parent.mkdir(parents=True)
    real = tmp_path / "elsewhere.jsonl"
    real.write_bytes(b"")
    try:
        ledger.symlink_to(real)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    outcome, _, _ = _ceremony(monkeypatch, tmp_path, keyring)

    assert outcome == 2 and "STAGE_C_LEDGER_MISSING" in capsys.readouterr().err
    assert _approval_keys(keyring) == {}


def test_the_ledger_is_prepared_before_a_failing_approval_write(monkeypatch, tmp_path, capsys) -> None:
    keyring = _PersistFailingKeyring(store_first=False)

    outcome, workspace, _ = _ceremony(monkeypatch, tmp_path, keyring)

    assert isinstance(outcome, PasswordSetError)
    ledger = _ledger(workspace)
    assert ledger.is_file(), "the ledger is prepared before any approval persistence call"
    assert stage_c.stage_c_ledger_status(ledger, stage_c.compose_stage_c_envelope(ledger=ledger)).state.attempts == 0
    assert "approval written" not in capsys.readouterr().out


def test_a_kept_ledger_reports_its_replayed_state(monkeypatch, tmp_path, capsys) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_ledger(workspace, {"kind": "window", "start": "2026-10-12T09:00:00+00:00", "deadline": "2026-10-12T10:00:00+00:00"})

    outcome, _, _ = _ceremony(monkeypatch, tmp_path, FakeKeyring())
    out = capsys.readouterr().out

    [kept] = [line for line in out.splitlines() if "kept as it is (never reset)" in line]
    assert outcome == 0
    envelope = stage_c.compose_stage_c_envelope(ledger=_ledger(tmp_path / "workspace"))
    assert f"0/{envelope.max_attempts} attempts" in kept and "charged" in kept and "2026-10-12T10:00:00" in kept


def test_a_one_shot_ceremony_creates_the_ledger_and_writes_its_approval(monkeypatch, tmp_path) -> None:
    keyring = FakeKeyring()

    outcome, workspace, spawned = _ceremony(monkeypatch, tmp_path, keyring, mode="one-shot")

    assert outcome == 0 and _ledger(workspace).is_file() and spawned == []
    assert [key.split(":")[0] for key in _approval_keys(keyring)] == ["oneshot"]


def test_a_declined_stage_c_ceremony_creates_nothing(monkeypatch, tmp_path) -> None:
    keyring = FakeKeyring()

    outcome, workspace, _ = _ceremony(monkeypatch, tmp_path, keyring, answer="n")

    assert outcome == 1 and not _ledger(workspace).exists() and _approval_keys(keyring) == {}


def test_a_keyring_that_stores_then_fails_leaves_a_valid_ledger_unchanged_and_claims_no_success(monkeypatch, tmp_path, capsys) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = _write_ledger(workspace)
    before = ledger.read_bytes()

    outcome, _, _ = _ceremony(monkeypatch, tmp_path, _PersistFailingKeyring(store_first=True))

    assert isinstance(outcome, PasswordSetError)
    assert ledger.read_bytes() == before
    assert "approval written" not in capsys.readouterr().out  # the stored entry is an unknown outcome, not asserted


def test_a_failed_one_shot_approval_write_never_spawns(monkeypatch, tmp_path) -> None:
    outcome, _, spawned = _ceremony(monkeypatch, tmp_path, _PersistFailingKeyring(store_first=False), mode="one-shot", target_argv=(sys.executable, "-c", "pass"))

    assert isinstance(outcome, PasswordSetError) and spawned == []


def test_an_expired_or_exhausted_but_bound_ledger_is_kept_and_the_approval_written(monkeypatch, tmp_path, capsys) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = _write_ledger(
        workspace,
        {"kind": "window", "start": "2026-10-12T09:00:00+00:00", "deadline": "2026-10-12T10:00:00+00:00"},
        {"kind": "reserve", "n": 1, "attempt_id": "a-1", "reserve_usd": "8"},
        {"kind": "settle", "n": 1, "result": "charged", "cost_usd": "8"},
    )
    before = ledger.read_bytes()
    keyring = FakeKeyring()

    outcome, _, _ = _ceremony(monkeypatch, tmp_path, keyring)

    assert outcome == 0 and ledger.read_bytes() == before
    assert "kept as it is (never reset)" in capsys.readouterr().out
    assert [key.split(":")[0] for key in _approval_keys(keyring)] == ["durable"]
