"""Plan 12.4 Task 4, slice 1: choosing Auto and composing it at launch (Design 1; implementation note r3, section 1).

``OPTIMUS_AGENT_MODEL=auto`` is the only way to choose Auto. The launch gate composes the Auto registry (the shipped
defaults, the shipped Auto overlay and the operator override) and binds its literal and its composition name, so an
ordinary approval never authorizes an Auto launch, or the reverse. The host recomposes it and refuses anything else; the
Gateway composes it independently (``--auto-composition``) and refuses a manifest that names another hash;
``optimus-trust run-gateway --auto`` signs only under an approval that binds both. The strict auth probe never sends
``auto``: it uses ADR-023's default planner computed in the Auto registry.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from optimus.acp import preflight
from optimus.acp.auto_composition import compose_auto_composition
from optimus.acp.launch_approvals import KeyringApprovalStore
from optimus.acp.launch_gate import LaunchGateError, authorize_launch, resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.operator_paths import resolve_authorized_operator_paths
from optimus.acp.trusted_paths import resolve_workspace_security_state
from optimus.agent.defaults import AgentModelError, auto_requested, resolve_model_for_registry
from optimus_gateway import __main__ as gateway_main
from optimus_model_policy import Role, select_eligible_models
from optimus_model_policy.binding import (
    APPROVAL_LITERAL_NAME,
    AUTO_COMPOSITION,
    COMPOSITION_LITERAL_NAME,
    BindingError,
    approval_literal,
    auto_snapshot,
    packaged_defaults,
    trusted_approval_literal,
    use_operator_override,
)
from optimus_model_policy.registry import load_registry
from tests.unit.acp.conftest import FakeKeyring, authorize_workspace_for_test
from tests.unit.acp.test_local_infra_model_registry import _spawned_args
from tests.unit.acp.test_operator_registry_override import LUNA_OVERRIDE, _run_gateway, _write_override
from tests.unit.optimus_gateway.test_main_model_registry import _manifest, started  # noqa: F401 - fixture

AUTO_HASH = "f11dc3ab9f7ac2355f00efe4490653194ce7e7c0b4b12704fd0b21b9571a416a"  # pragma: allowlist secret - registry identity (CA2), not a credential
_BASE = {
    "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
    "OPTIMUS_API_KEY": "test-key",  # pragma: allowlist secret - synthetic test fixture
    "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
}
_AUTO_ENV = {**_BASE, "OPTIMUS_AGENT_MODEL": "auto"}


def _auto_overlay() -> Path:
    return packaged_defaults().with_name("auto_overlay.yaml")


def _candidate(workspace: Path, keyring: FakeKeyring, env: dict[str, str], **kwargs: object):
    snapshot = LaunchEnvironmentSnapshot.capture(env)
    paths = resolve_authorized_operator_paths(workspace_root=workspace, snapshot_values=snapshot.values, platform_name=sys.platform)
    store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=workspace / ".optimus-runtime")
    candidate = resolve_launch_candidate(
        snapshot=snapshot, workspace_state=resolve_workspace_security_state(workspace), operator_paths=paths, hmac_key=store.hmac_key, **kwargs
    )
    return candidate, store


# --- Choosing Auto ---------------------------------------------------------------------------------


def test_only_the_environment_chooses_auto() -> None:
    assert auto_requested({"OPTIMUS_AGENT_MODEL": "auto"}) is True
    assert auto_requested({"OPTIMUS_AGENT_MODEL": " auto "}) is True
    assert auto_requested({}) is False
    assert auto_requested({"OPTIMUS_AGENT_MODEL": "anthropic/claude-haiku-5.5"}) is False
    assert auto_requested({}, cli_model="anthropic/claude-haiku-5.5") is False
    with pytest.raises(AgentModelError, match="never by --model"):
        auto_requested({}, cli_model="auto")
    with pytest.raises(AgentModelError, match="conflicts with --model"):
        auto_requested({"OPTIMUS_AGENT_MODEL": "auto"}, cli_model="anthropic/claude-haiku-5.5")


def test_auto_is_never_a_model_id() -> None:
    with pytest.raises(AgentModelError, match="not a model ID"):
        resolve_model_for_registry({"OPTIMUS_AGENT_MODEL": "auto"}, registry=load_registry(packaged_defaults()))


# --- The composition -------------------------------------------------------------------------------


def test_the_auto_composition_is_defaults_then_overlay_then_override(tmp_path: Path) -> None:
    use_operator_override(None)
    snapshot = auto_snapshot()
    assert snapshot is not None and snapshot.effective_hash == AUTO_HASH  # the hash the operator approved (CA2)
    assert select_eligible_models(snapshot, Role.CLASSIFIER) == ("typesafe/jev-1.14",)
    path = _write_override(tmp_path / "config")
    use_operator_override(path)
    try:
        assert auto_snapshot().effective_hash == load_registry(packaged_defaults(), _auto_overlay(), path).effective_hash
        assert auto_snapshot().effective_hash != AUTO_HASH  # an override changes the hash, which needs its own approval
    finally:
        use_operator_override(None)
    assert trusted_approval_literal() == approval_literal(load_registry(packaged_defaults()))  # ordinary unchanged


def test_the_host_recomposes_only_the_approved_auto_composition() -> None:
    use_operator_override(None)
    literal = approval_literal(auto_snapshot())
    composition = compose_auto_composition(approved_literal=literal, composition=AUTO_COMPOSITION)
    assert composition.snapshot.effective_hash == AUTO_HASH
    assert composition.default_model() == "google/gemini-3.8-flash"  # ADR-023's default planner, computed here
    for approved, name in ((literal, None), (trusted_approval_literal(), AUTO_COMPOSITION), (None, AUTO_COMPOSITION)):
        with pytest.raises(BindingError) as caught:
            compose_auto_composition(approved_literal=approved, composition=name)
        assert caught.value.code == "AUTO_NOT_APPROVED"


# --- The launch gate -------------------------------------------------------------------------------


def test_the_gate_binds_the_auto_literal_and_its_name(tmp_path: Path) -> None:
    keyring = FakeKeyring()
    ordinary, _ = _candidate(tmp_path, keyring, _BASE)
    auto, _ = _candidate(tmp_path, keyring, _AUTO_ENV)
    assert auto.security_literals[APPROVAL_LITERAL_NAME] == approval_literal(load_registry(packaged_defaults(), _auto_overlay()))
    assert auto.security_literals[COMPOSITION_LITERAL_NAME] == AUTO_COMPOSITION
    assert COMPOSITION_LITERAL_NAME not in ordinary.security_literals
    [row] = [row for row in auto.display_rows if row.name == APPROVAL_LITERAL_NAME]
    assert row.source_class == "auto-composition"
    assert auto.security_snapshot_digest != ordinary.security_snapshot_digest


def test_an_ordinary_approval_never_authorizes_an_auto_launch(tmp_path: Path) -> None:
    keyring = FakeKeyring()
    authorize_workspace_for_test(env=_BASE, workspace_root=tmp_path, fake_keyring=keyring)
    auto, store = _candidate(tmp_path, keyring, _AUTO_ENV)
    with pytest.raises(LaunchGateError) as caught:
        authorize_launch(candidate=auto, store=store, launch_session_id="s1")
    assert caught.value.code == "SNAPSHOT_MISMATCH"


def test_auto_with_a_test_profile_is_refused(tmp_path: Path) -> None:
    with pytest.raises(LaunchGateError) as caught:
        _candidate(tmp_path, FakeKeyring(), _AUTO_ENV, test_profile="attached")
    assert caught.value.code == "AUTO_WITH_TEST_PROFILE"


# --- The Gateway -----------------------------------------------------------------------------------


def test_the_gateway_composes_auto_and_refuses_another_hash(started: list) -> None:  # noqa: F811
    use_operator_override(None)
    argv = ["--bind-host", "127.0.0.1", "--port", "8765", "--auto-composition"]
    assert gateway_main.main([*argv, "--manifest", _manifest(approval_literal(auto_snapshot()))]) == 0
    assert started[0].model_policy.snapshot.effective_hash == AUTO_HASH
    started.clear()
    # A swapped composition on either side refuses before serving: an Auto Gateway under an ordinary manifest, and an
    # ordinary Gateway under an Auto manifest.
    assert gateway_main.main([*argv, "--manifest", _manifest(trusted_approval_literal())]) == 2
    assert gateway_main.main(["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", _manifest(approval_literal(auto_snapshot()))]) == 2
    assert started == []
    with pytest.raises(SystemExit):
        gateway_main.main([*argv, "--plan12-test-profile", "attached", "--manifest", _manifest(None)])


def test_the_gateway_child_gets_the_auto_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert "--auto-composition" in _spawned_args(tmp_path, monkeypatch, model_registry="x", auto_composition=True)
    assert "--auto-composition" not in _spawned_args(tmp_path, monkeypatch, model_registry="x")


def test_run_gateway_auto_signs_only_under_an_approval_binding_auto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_operator_override(None)
    auto_literal = approval_literal(auto_snapshot())
    bound = SimpleNamespace(security_literals={APPROVAL_LITERAL_NAME: auto_literal, COMPOSITION_LITERAL_NAME: AUTO_COMPOSITION})
    code, spawned, _ = _run_gateway(tmp_path, monkeypatch, approval=bound, auto=True)
    assert code == 0 and "--auto-composition" in spawned[0]

    refusals = (
        None,  # no durable approval
        SimpleNamespace(security_literals={APPROVAL_LITERAL_NAME: auto_literal}),  # the literal without the name
        SimpleNamespace(security_literals={APPROVAL_LITERAL_NAME: trusted_approval_literal()}),  # an ordinary approval
    )
    for approval in refusals:
        code, spawned, err = _run_gateway(tmp_path, monkeypatch, approval=approval, auto=True)
        assert (code, spawned) == (2, []) and "MODEL_REGISTRY_NOT_APPROVED" in err
    # An ordinary run never signs under an Auto approval.
    code, spawned, err = _run_gateway(tmp_path, monkeypatch, approval=bound)
    assert (code, spawned) == (2, []) and "MODEL_REGISTRY_NOT_APPROVED" in err


def test_run_gateway_auto_refuses_a_changed_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_operator_override(None)
    bound = SimpleNamespace(security_literals={APPROVAL_LITERAL_NAME: approval_literal(auto_snapshot()), COMPOSITION_LITERAL_NAME: AUTO_COMPOSITION})
    _write_override(tmp_path / "config", LUNA_OVERRIDE)  # the composed Auto hash now differs from the approved one
    code, spawned, err = _run_gateway(tmp_path, monkeypatch, approval=bound, auto=True)
    assert (code, spawned) == (2, []) and "MODEL_REGISTRY_NOT_APPROVED" in err


# --- The strict auth probe -------------------------------------------------------------------------


def test_the_auto_probe_uses_the_default_planner_bound_against_the_auto_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    use_operator_override(None)
    sent: list = []

    class _Client:
        def __init__(self, *, settings) -> None:
            pass

        def create_response(self, *, model, input_text, metadata, route_binding) -> None:
            sent.append((model, route_binding))

    monkeypatch.setattr("optimus.gateway.client.GatewayClient", _Client)
    preflight._require_gateway_auth(_AUTO_ENV)
    [(model, binding)] = sent
    assert model == "google/gemini-3.8-flash" != "auto"
    assert binding is not None and binding.registry_hash == AUTO_HASH


def test_the_auto_probe_follows_a_changed_configured_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An override that removes Gemini from medium makes the default planner the first eligible easy model."""
    path = _write_override(tmp_path / "config", LUNA_OVERRIDE + "  medium: []\n")
    use_operator_override(path)
    sent: list = []

    class _Client:
        def __init__(self, *, settings) -> None:
            pass

        def create_response(self, *, model, input_text, metadata, route_binding) -> None:
            sent.append(model)

    monkeypatch.setattr("optimus.gateway.client.GatewayClient", _Client)
    try:
        preflight._require_gateway_auth(_AUTO_ENV)
    finally:
        use_operator_override(None)
    assert sent == ["openai/gpt-6-luna"]


def test_the_probe_refuses_auto_by_cli_flag() -> None:
    with pytest.raises(preflight.PreflightFailure, match="never by --model"):
        preflight._require_gateway_auth(_BASE, cli_model="auto")
