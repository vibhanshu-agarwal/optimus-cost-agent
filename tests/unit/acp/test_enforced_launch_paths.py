"""Closure plan v3: the launch paths that cannot carry the shipped registry's route binding.

- ``--framed`` has no route binding on the framed transport, so it is refused at startup with a readable message
  (before any service or provider call) rather than sending unbound requests the enforced Gateway would refuse.
- ``--check-config --strict`` keeps working: its auth probe is bound through the ordinary route policy. It is still
  a real (possibly billed) request against a real Gateway; these tests use a fake client only.
"""

from __future__ import annotations

import pytest

from optimus.acp import __main__ as acp_main
from optimus.acp.preflight import run_preflight
from optimus_model_policy.experimental import SHIPPED_DEFAULTS_HASH
from tests.unit.acp.test_preflight import FakeAsyncRedisClient, _patch_runtime

HAIKU = "anthropic/claude-haiku-5.5"


def test_framed_is_refused_at_startup_while_the_registry_is_enforced(capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        acp_main.parse_args(["--framed"])
    err = capsys.readouterr().err
    assert caught.value.code == 2
    assert "--framed is not supported" in err and "omit --framed" in err


def test_the_strict_auth_probe_is_bound_through_the_ordinary_route_policy(monkeypatch) -> None:
    _patch_runtime(monkeypatch, FakeAsyncRedisClient())
    captured: dict[str, object] = {}

    class FakeGatewayClient:
        def __init__(self, *, settings):
            self.settings = settings

        def create_response(self, *, model: str, input_text: str, metadata=None, route_binding=None):
            captured.update(model=model, route_binding=route_binding)
            return object()

    monkeypatch.setattr("optimus.gateway.client.GatewayClient", FakeGatewayClient)
    run_preflight(
        {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "opt-test",  # pragma: allowlist secret - synthetic test fixture, not a real credential
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            "OPTIMUS_PRODUCTION_MODE": "false",
        },
        strict=True,
    )
    binding = captured["route_binding"]
    assert captured["model"] == HAIKU
    assert binding is not None and binding.registry_hash == SHIPPED_DEFAULTS_HASH and binding.output_cap == 32_768


_ENV = {
    "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
    "OPTIMUS_API_KEY": "opt-test",  # pragma: allowlist secret - synthetic test fixture, not a real credential
    "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
    "OPTIMUS_PRODUCTION_MODE": "false",
}


def _capturing_client(monkeypatch) -> dict[str, object]:
    captured: dict[str, object] = {}

    class FakeGatewayClient:
        def __init__(self, *, settings):
            self.settings = settings

        def create_response(self, *, model: str, input_text: str, metadata=None, route_binding=None):
            captured.update(model=model, route_binding=route_binding)
            return object()

    monkeypatch.setattr("optimus.gateway.client.GatewayClient", FakeGatewayClient)
    return captured


def test_the_strict_probe_uses_the_launchs_own_model_over_a_stale_environment(monkeypatch) -> None:
    """Fable review 1, F1: an ineligible OPTIMUS_AGENT_MODEL with an eligible --model probes the --model."""
    _patch_runtime(monkeypatch, FakeAsyncRedisClient())
    captured = _capturing_client(monkeypatch)
    run_preflight({**_ENV, "OPTIMUS_AGENT_MODEL": "claude-haiku"}, strict=True, cli_model=HAIKU)
    binding = captured["route_binding"]
    assert captured["model"] == HAIKU and binding is not None and binding.registry_hash == SHIPPED_DEFAULTS_HASH


def test_a_refused_probe_model_is_a_typed_preflight_failure_before_any_request(monkeypatch) -> None:
    from optimus.acp.preflight import PreflightFailure

    _patch_runtime(monkeypatch, FakeAsyncRedisClient())
    captured = _capturing_client(monkeypatch)
    with pytest.raises(PreflightFailure) as caught:
        run_preflight({**_ENV, "OPTIMUS_AGENT_MODEL": "claude-haiku"}, strict=True)
    assert caught.value.exit_code == 2 and caught.value.user_message.startswith("AGENT_MODEL_INVALID: ")
    assert captured == {}, "no request was sent"


def test_without_enforcement_framed_is_accepted_and_the_probe_is_unbound(monkeypatch) -> None:
    """Codex 6249427656 item 9: the enforcement-off behaviour is kept where it is still supported."""
    from optimus_model_policy import binding

    monkeypatch.setattr(binding, "ENFORCEMENT_ACTIVE", False)
    assert acp_main.parse_args(["--framed"]).framed is True
    _patch_runtime(monkeypatch, FakeAsyncRedisClient())
    captured = _capturing_client(monkeypatch)
    run_preflight(_ENV, strict=True)
    assert captured["route_binding"] is None
