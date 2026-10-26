"""Plan 12.2 Task 5: an unusable model or registry stops ACP startup with a typed message.

Under an enforced registry, a configured model the registry does not make eligible (or a registry that
cannot be trusted) fails before any local dependency starts, with an ``optimus-agent:`` message rather
than a traceback from inside the runtime composition (Fable CP1 review, m5).
"""

from __future__ import annotations

import pytest

from optimus.acp import __main__ as acp_main
from optimus.acp.auto_composition import AutoComposition
from optimus.acp.bootstrap import StartupConfigurationError
from optimus.agent.defaults import AgentModelError
from optimus_model_policy.binding import BindingError, auto_snapshot
from tests.unit.acp.conftest import FakeKeyring, authorize_workspace_for_test

pytestmark = pytest.mark.usefixtures("isolated_windows_known_folders")

_ENV = {
    "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
    "OPTIMUS_API_KEY": "test-key",  # pragma: allowlist secret - synthetic test fixture
    "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
}


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (AgentModelError("model 'claude-haiku' is not eligible in the trusted model registry"), "optimus-agent: AGENT_MODEL_INVALID: model 'claude-haiku'"),
        (BindingError("FIXTURE_POLICY", "a fixture registry cannot be trusted at launch"), "optimus-agent: MODEL_REGISTRY_INVALID: FIXTURE_POLICY"),
    ],
)
def test_an_unusable_model_stops_startup_before_any_side_effect(monkeypatch, tmp_path, capsys, error, expected) -> None:
    keyring = FakeKeyring()
    authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring)
    monkeypatch.setattr(acp_main, "keyring", keyring)
    for name, value in _ENV.items():
        monkeypatch.setenv(name, value)

    def refuse(*args: object, **kwargs: object) -> str:
        raise error

    started: list[object] = []
    monkeypatch.setattr(acp_main, "resolve_agent_model", refuse)
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: started.append("redis"))
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: started.append("gateway"))
    monkeypatch.setattr(acp_main, "build_configured_server", lambda **k: started.append("server"))

    assert acp_main.main(["--workspace-root", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert expected in err
    assert "Traceback" not in err
    assert started == []
    if isinstance(error, BindingError):
        assert "a fixture registry" not in err, "only the stable code is exported"


def test_an_approved_auto_launch_hands_its_composition_to_the_gateway_and_the_server(monkeypatch, tmp_path, capsys) -> None:
    """Plan 12.4 Task 4: the Auto composition is recomposed and checked against the approval, then the Gateway is spawned
    for it and the server is built with it; ``--model`` with the environment's ``auto`` is refused before anything."""
    env = {**_ENV, "OPTIMUS_AGENT_MODEL": "auto"}
    keyring = FakeKeyring()
    authorize_workspace_for_test(env=env, workspace_root=tmp_path, fake_keyring=keyring)
    monkeypatch.setattr(acp_main, "keyring", keyring)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    started: list[object] = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: started.append("redis"))
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: started.append(("gateway", k["auto_composition"])))

    def build(**kwargs: object) -> None:
        started.append(("server", kwargs.get("auto_composition")))
        raise StartupConfigurationError(exit_code=3, user_message="stopped by the test")

    monkeypatch.setattr(acp_main, "build_configured_server", build)

    assert acp_main.main(["--workspace-root", str(tmp_path)]) == 3
    approved = auto_snapshot()
    assert approved is not None
    redis, gateway, (server, composition) = started
    assert (redis, gateway, server) == ("redis", ("gateway", True), "server")
    assert isinstance(composition, AutoComposition) and composition.snapshot.effective_hash == approved.effective_hash
    capsys.readouterr()
    started.clear()

    assert acp_main.main(["--workspace-root", str(tmp_path), "--model", "anthropic/claude-haiku-5.5"]) == 2
    assert "AGENT_MODEL_INVALID: OPTIMUS_AGENT_MODEL=auto conflicts with --model" in capsys.readouterr().err
    assert started == []
