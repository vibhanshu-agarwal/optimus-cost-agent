"""Plan 12.2 closure (release supplement V2): the trusted, process-scoped test composition.

Offline acceptance before any paid/live use. A named, source-owned profile is bound into the HMAC
launch approval; the host refuses a composition its launch did not approve; the Gateway composes the
same profile itself and refuses a manifest naming another hash; the server hands the trusted route
policy to every session adapter. Production composition is unchanged.

The real ``qualification`` profile admits no model today (its tokenizer, finish and reasoning facts are
unverified), so the positive mechanism is shown with a SYNTHETIC, test-only profile whose facts are
marked verified here and nowhere else. It is not a real profile, approval or admissible live route.
"""

from __future__ import annotations

import asyncio
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

from optimus.acp import __main__ as acp_main
from optimus.acp.launch_approvals import KeyringApprovalStore
from optimus.acp.launch_gate import LaunchGateError, authorize_launch, resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.operator_paths import resolve_authorized_operator_paths
from optimus.acp.test_composition import compose_test_composition
from optimus.acp.trusted_paths import resolve_workspace_security_state
from optimus.agent.defaults import AgentModelError
from optimus.gateway.route_binding import RouteIdentityError
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.binding import APPROVAL_LITERAL_NAME, BindingError, approval_literal, packaged_defaults
from optimus_model_policy.registry import load_registry
from tests.unit.acp.conftest import FakeKeyring, authorize_workspace_for_test

_ENV = {
    "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
    "OPTIMUS_API_KEY": "test-key",  # pragma: allowlist secret - synthetic test fixture
    "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
}
LUNA = "openai/gpt-6-luna"

# SYNTHETIC test-only facts: the estimator and endpoint are marked verified so the mechanism can be
# exercised end to end. Never a real profile, never shipped, never a qualification claim.
SYNTHETIC_OVERRIDE = textwrap.dedent(
    """\
    output_reserve_tokens: {implementer: 32768, summarizer: 8192}
    estimators:
      synthetic-r1: {method: utf8-bytes-ratio, tokens_per_byte: "1", per_message_tokens: 8, fixed_tokens: 64, verified: true}
    models:
      openai/gpt-6-luna:
        prices: {input_usd_per_million: "0.20", output_usd_per_million: "1.00"}
        capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [none]}
        default_reasoning: none
        route:
          estimator: synthetic-r1
          endpoints:
            - {provider: openai/fast, quantization: unknown, context_window_tokens: 1050000, max_output_tokens: 128000, verified: true, observed_on: "2026-10-04"}
    """
)


@pytest.fixture
def synthetic_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
    """Replace the qualification profile, for this test only, with the synthetic eligible one."""
    override = tmp_path / "synthetic-override.yaml"
    override.write_text(SYNTHETIC_OVERRIDE, encoding="utf-8")
    pinned = load_registry(packaged_defaults(), override).effective_hash
    real = profiles.TEST_PROFILES["qualification"]
    monkeypatch.setitem(profiles.TEST_PROFILES, "qualification", profiles.TestProfile(**{**real.__dict__, "effective_hash": pinned}))
    monkeypatch.setattr(profiles, "_override_path", lambda _profile: override)
    return pinned


def _candidate(workspace: Path, keyring: FakeKeyring, *, test_profile: str | None):
    snapshot = LaunchEnvironmentSnapshot.capture(_ENV)
    paths = resolve_authorized_operator_paths(workspace_root=workspace, snapshot_values=snapshot.values, platform_name=sys.platform)
    store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=workspace / ".optimus-runtime")
    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_state=resolve_workspace_security_state(workspace),
        operator_paths=paths,
        hmac_key=store.hmac_key,
        test_profile=test_profile,
    )
    return candidate, store


# --- Launch approval ------------------------------------------------------------------------------------


def test_a_profile_launch_binds_the_profiles_exact_hash_for_approval(tmp_path: Path) -> None:
    keyring = FakeKeyring()
    plain, _ = _candidate(tmp_path, keyring, test_profile=None)
    profiled, _ = _candidate(tmp_path, keyring, test_profile="qualification")

    literal = approval_literal(profiles.compose_test_profile_snapshot("qualification"))
    assert APPROVAL_LITERAL_NAME not in plain.security_literals
    assert profiled.security_literals[APPROVAL_LITERAL_NAME] == literal
    [row] = [row for row in profiled.display_rows if row.name == APPROVAL_LITERAL_NAME]
    assert (row.display_value, row.source_class, row.decision) == (literal, "test-profile:qualification", "requires exact approval")
    assert profiled.security_snapshot_digest != plain.security_snapshot_digest


def test_an_approval_without_the_profile_never_authorizes_a_profile_launch(tmp_path: Path) -> None:
    keyring = FakeKeyring()
    authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring)
    profiled, store = _candidate(tmp_path, keyring, test_profile="qualification")
    with pytest.raises(LaunchGateError) as caught:
        authorize_launch(candidate=profiled, store=store, launch_session_id="s1")
    assert caught.value.code == "SNAPSHOT_MISMATCH"

    authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring, test_profile="qualification")
    profiled, store = _candidate(tmp_path, keyring, test_profile="qualification")
    assert authorize_launch(candidate=profiled, store=store, launch_session_id="s2").approval_mode == "durable"
    plain, store = _candidate(tmp_path, keyring, test_profile=None)
    with pytest.raises(LaunchGateError) as caught:  # and the profile approval never authorizes a plain launch
        authorize_launch(candidate=plain, store=store, launch_session_id="s3")
    assert caught.value.code == "SNAPSHOT_MISMATCH"


def test_an_unavailable_profile_refuses_the_candidate(tmp_path: Path) -> None:
    with pytest.raises(LaunchGateError) as caught:
        _candidate(tmp_path, FakeKeyring(), test_profile="attached")
    assert (caught.value.code, caught.value.detail) == ("MODEL_REGISTRY_INVALID", "TEST_PROFILE_UNAVAILABLE")


# --- Host composition --------------------------------------------------------------------------------------


@pytest.mark.parametrize("approved", [None, "optimus-model-registry-v1:" + "0" * 64])
def test_a_composition_the_launch_did_not_approve_is_refused(approved: str | None) -> None:
    with pytest.raises(BindingError) as caught:
        compose_test_composition("qualification", approved_literal=approved)
    assert caught.value.code == "TEST_PROFILE_NOT_APPROVED"


def test_the_real_qualification_profile_has_no_eligible_model_yet() -> None:
    snapshot = profiles.compose_test_profile_snapshot("qualification")
    composition = compose_test_composition("qualification", approved_literal=approval_literal(snapshot))
    with pytest.raises(AgentModelError):
        composition.agent_model(_ENV, cli_model=None)


def test_a_synthetic_eligible_profile_composes_its_exact_model_and_route(synthetic_profile: str) -> None:
    composition = compose_test_composition("qualification", approved_literal="optimus-model-registry-v1:" + synthetic_profile)

    model = composition.agent_model({"OPTIMUS_AGENT_MODEL": "claude-haiku"}, cli_model=None)  # the alias never wins
    policy = composition.route_policy(model_id=model, shared_secret="test-key")  # pragma: allowlist secret - synthetic
    assert model == LUNA
    assert (policy.identity.model_id, policy.identity.role, policy.identity.route, policy.identity.quantizations, policy.output_cap) == (
        LUNA, "easy", ("openai/fast",), ("unknown",), 32_768
    )  # fmt: skip
    assert policy.identity.registry_hash == synthetic_profile
    with pytest.raises(RouteIdentityError):
        composition.route_policy(model_id="openai/other", shared_secret="test-key")  # pragma: allowlist secret - synthetic


def test_the_enforced_gateway_request_carries_the_profiles_exact_route_filter(synthetic_profile: str, tmp_path: Path) -> None:
    """The composed route reaches the real in-process enforced Gateway as the documented filters: the
    exact endpoint only, quantization "unknown", no fallbacks, required parameters, reasoning "none"."""
    from optimus.agent.models import AgentRunRequest
    from optimus.agent.runner import AgentRunner
    from optimus.runtime.modes import ExecutionMode
    from tests.unit.agent.test_route_binding import InProcessGateway, ScriptedUpstream, _client
    from tests.unit.optimus_gateway.model_policy_support import SHARED_SECRET

    calls: list[dict[str, Any]] = []

    class Recording(ScriptedUpstream):
        def create_message_once(self, *, model, input_text, max_tokens, provider_controls, reasoning):
            calls.append({"provider_controls": dict(provider_controls), "reasoning": reasoning, "max_tokens": max_tokens})
            return super().create_message_once(model=model, input_text=input_text, max_tokens=max_tokens, provider_controls=provider_controls, reasoning=reasoning)

    snapshot = profiles.compose_test_profile_snapshot("qualification")
    composition = compose_test_composition("qualification", approved_literal=approval_literal(snapshot))
    binder = composition.route_policy(model_id=LUNA, shared_secret=SHARED_SECRET).capture(session_id="s", turn_seq=1, deliver_notice=lambda text: True)
    gateway = InProcessGateway(snapshot, Recording(replies=["An answer."]))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    request = AgentRunRequest(run_id="s:1", session_id="s", task="A question?", workspace_root=workspace, execution_mode=ExecutionMode.CHAT)

    result = AgentRunner(gateway_client=_client(gateway), model=LUNA).run(request, route_binder=binder)

    assert result.output_text == "An answer." and [status for status, _ in gateway.replies] == [200]
    [call] = calls
    assert call["provider_controls"] == {"only": ["openai/fast"], "quantizations": ["unknown"], "allow_fallbacks": False, "require_parameters": True}
    assert (call["reasoning"], call["max_tokens"]) == ("none", 32_768)


# --- Server and entrypoint ----------------------------------------------------------------------------------


def test_the_server_hands_its_route_policy_to_every_session_adapter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from optimus.acp import server as server_module
    from optimus.acp.dispatcher import JsonRpcDispatcher

    class _Stop(Exception):
        pass

    seen: list[Any] = []

    def adapter(**kwargs):
        seen.append(kwargs.get("route_policy"))
        raise _Stop

    monkeypatch.setattr(server_module, "AcpDuplexAdapter", adapter)
    marker = object()
    server = server_module.AcpStreamServer(JsonRpcDispatcher(agent_runner=object(), workspace_root=tmp_path), route_policy=marker)

    class _Writer:
        async def write_line(self, payload):
            return None

    with pytest.raises(_Stop):
        asyncio.run(server._serve_ndjson(object(), _Writer(), dedicated_writer=None, notice_control=None, join_dedicated_writer=True))
    assert seen == [marker] and server.route_policy is marker


@pytest.fixture
def launch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    keyring = FakeKeyring()
    monkeypatch.setattr(acp_main, "keyring", keyring)
    for name, value in _ENV.items():
        monkeypatch.setenv(name, value)
    started: list[Any] = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: started.append(("redis",)))
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: started.append(("gateway", k.get("test_profile"), k.get("model_registry"))))

    class _Server:
        async def serve_ndjson(self, *args, **kwargs):
            return None

    def build(**kwargs):
        started.append(("server", kwargs.get("test_composition")))
        return _Server()

    monkeypatch.setattr(acp_main, "build_configured_server", build)
    monkeypatch.setattr(acp_main, "StdioNdjsonLineReader", lambda stream: None)
    monkeypatch.setattr(acp_main, "StdioNdjsonLineWriter", lambda stream: None)

    class _Dedicated:
        def __init__(self, writer):
            pass

        def start(self):
            return None

        def close_and_join(self):
            return None

    monkeypatch.setattr("optimus.acp.outbound_writer.DedicatedOutboundWriter", _Dedicated)
    return keyring, started


pytestmark = pytest.mark.usefixtures("isolated_windows_known_folders")


def test_an_unknown_profile_name_is_rejected_by_the_parser(capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        acp_main.parse_args(["--plan12-test-profile", "bogus"])
    assert caught.value.code == 2 and "invalid choice" in capsys.readouterr().err


def test_an_unavailable_profile_stops_startup_before_any_side_effect(launch, tmp_path: Path, capsys) -> None:
    keyring, started = launch
    authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring)

    assert acp_main.main(["--workspace-root", str(tmp_path), "--plan12-test-profile", "attached"]) == 2
    assert "MODEL_REGISTRY_INVALID: TEST_PROFILE_UNAVAILABLE" in capsys.readouterr().err
    assert started == []


def test_a_profile_launch_without_its_approval_stops_before_any_side_effect(launch, tmp_path: Path, capsys) -> None:
    keyring, started = launch
    authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring)  # a plain approval only

    assert acp_main.main(["--workspace-root", str(tmp_path), "--plan12-test-profile", "qualification"]) == 2
    assert started == []


def test_the_approved_real_qualification_profile_stops_on_its_missing_facts(launch, tmp_path: Path, capsys) -> None:
    keyring, started = launch
    authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring, test_profile="qualification")

    assert acp_main.main(["--workspace-root", str(tmp_path), "--plan12-test-profile", "qualification"]) == 2
    assert "AGENT_MODEL_INVALID" in capsys.readouterr().err
    assert started == []  # no Redis, Gateway or server: zero upstream calls


def test_an_approved_synthetic_profile_composes_the_gateway_and_server(launch, synthetic_profile: str, tmp_path: Path) -> None:
    keyring, started = launch
    authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring, test_profile="qualification")

    assert acp_main.main(["--workspace-root", str(tmp_path), "--plan12-test-profile", "qualification"]) == 0
    gateway = [entry for entry in started if entry[0] == "gateway"]
    server = [entry for entry in started if entry[0] == "server"]
    assert gateway == [("gateway", "qualification", "optimus-model-registry-v1:" + synthetic_profile)]
    [(_, composition)] = server
    assert composition.snapshot.effective_hash == synthetic_profile and composition.profile.model_id == LUNA


def test_without_a_profile_the_launch_composition_is_unchanged(launch, tmp_path: Path) -> None:
    keyring, started = launch
    authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring)

    assert acp_main.main(["--workspace-root", str(tmp_path)]) == 0
    assert ("gateway", None, None) in started and ("server", None) in started


# The Gateway child's argv is checked in test_local_infra_model_registry.py.


def test_the_gateway_composes_the_named_profile_itself(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from optimus_gateway import __main__ as gateway_main
    from tests.unit.optimus_gateway.test_main_model_registry import _API_KEY, _SECRET, _Keyring, _manifest, _Server

    for name in ("OPTIMUS_LOCAL_GATEWAY_BIND_HOST", "OPTIMUS_LOCAL_GATEWAY_PORT", "OPTIMUS_LOCAL_GATEWAY_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", _SECRET)
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", _API_KEY)
    monkeypatch.setattr(gateway_main, "_keyring_module", _Keyring())
    configs: list[Any] = []
    monkeypatch.setattr(gateway_main, "serve_gateway", lambda *, config: configs.append(config) or _Server())
    literal = approval_literal(profiles.compose_test_profile_snapshot("qualification"))

    def run(manifest_literal, profile):
        argv = ["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", _manifest(manifest_literal)]
        return gateway_main.main(argv + (["--plan12-test-profile", profile] if profile else []))

    assert run(literal, "qualification") == 0
    assert configs[-1].model_policy.snapshot.effective_hash == configs[-1].model_policy.approved_hash == literal.split(":")[-1]
    configs.clear()
    assert run(None, "qualification") == 2 and configs == []  # a manifest naming no registry
    assert run("optimus-model-registry-v1:" + "d" * 64, "qualification") == 2 and configs == []  # another hash
    assert run(literal, None) == 2 and configs == []  # an unprofiled Gateway never enforces a profile's manifest
    assert run(None, "attached") == 2 and "TEST_PROFILE_UNAVAILABLE" in capsys.readouterr().err
    assert configs == []
