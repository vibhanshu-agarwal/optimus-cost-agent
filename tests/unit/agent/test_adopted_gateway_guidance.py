"""Plan 12.2 closure (Codex 6249427656): an adopted Gateway that does not enforce this install's registry.

``--no-auto-start`` and ``optimus-trust run-gateway`` keep adopting a Gateway that is already listening. One
started before the upgrade enforces no registry and refuses every bound request with ``BINDING_UNSUPPORTED``;
one started for another registry refuses it with ``REGISTRY_HASH_MISMATCH``. Both refusals come before any
upstream attempt, so nothing is charged and nothing goes out unbound (there is no full-history escape). Chat
and Agent mode both show readable restart and re-approval guidance, and the summarizer's bound request is
refused the same way.

The real in-process Gateway handler runs behind the real ``GatewayClient``; only the provider is fake. No
network, service or paid call is made.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

import optimus_gateway.responses as gateway_responses
from optimus.acp.context_attachment import ordinary_attachment, ordinary_route_policy
from optimus.acp.spec import _PLANNING_TERMINAL_STOP_REASONS
from optimus.agent.runner import AgentRunner
from optimus.context.maintenance import MaintenanceIdentity
from optimus.gateway.attempts import gateway_registry_mismatch_text
from optimus.runtime.modes import ExecutionMode
from optimus.usage.turn_settlement import StageReceipt
from optimus_model_policy.binding import trusted_snapshot
from optimus_model_policy.test_profiles import compose_test_profile_snapshot
from tests.unit.agent.test_route_binding import InProcessGateway, ScriptedUpstream, _client, _request
from tests.unit.optimus_gateway.model_policy_support import SHARED_SECRET, gateway_config, model_policy

HAIKU = "anthropic/claude-haiku-5.5"
GUIDANCE = ("approve --mode durable", "run-gateway", "This refused request incurred no provider charge.")
EXPECTED_STOP = {ExecutionMode.CHAT: "CHAT_GATEWAY_REGISTRY_MISMATCH", ExecutionMode.AGENT: "PLANNING_GATEWAY_REGISTRY_MISMATCH"}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway_responses, "_sleep", lambda seconds: None)


def _shipped():
    snapshot = trusted_snapshot()
    assert snapshot is not None, "the closure release ships the enforced registry"
    return snapshot


def _adopted_gateway(kind: str) -> tuple[InProcessGateway, str]:
    """The Gateway an ordinary launch adopted: unenforced (pre-upgrade), or enforcing another registry."""
    gateway = InProcessGateway(_shipped(), ScriptedUpstream(replies=["An answer."]))
    if kind == "unenforced":
        gateway.config = gateway_config(None)
        return gateway, "BINDING_UNSUPPORTED"
    gateway.config = gateway_config(model_policy(compose_test_profile_snapshot("qualification")))
    return gateway, "REGISTRY_HASH_MISMATCH"


@pytest.mark.parametrize("kind", ["unenforced", "other-registry"])
@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.AGENT], ids=["chat", "planning"])
def test_an_adopted_mismatched_gateway_refuses_before_any_attempt_with_guidance(tmp_path: Path, mode: ExecutionMode, kind: str) -> None:
    gateway, code = _adopted_gateway(kind)
    binder = ordinary_route_policy(snapshot=_shipped(), model_id=HAIKU, shared_secret=SHARED_SECRET).capture(
        session_id="s", turn_seq=1, deliver_notice=lambda text: True
    )
    receipts: list[StageReceipt] = []

    request = _request(tmp_path, mode, task="A question?")
    result = AgentRunner(gateway_client=_client(gateway), model=HAIKU).run(request, stage_receipts=receipts.append, route_binder=binder)

    assert gateway.upstream.calls == [], "refused before any upstream attempt"
    assert [(status, body["code"]) for status, body in gateway.replies] == [(400, code)]
    assert all(payload["route_binding"]["registry_hash"] == _shipped().effective_hash for payload in gateway.payloads), "never unbound"
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("rejected", Decimal("0"))]
    assert (result.stop_reason, result.total_cost_usd, result.cost_complete) == (EXPECTED_STOP[mode], Decimal("0"), True)
    assert result.output_text == gateway_registry_mismatch_text(EXPECTED_STOP[mode], request.workspace_root)
    assert f"--workspace-root {request.workspace_root}" in result.output_text.replace('"', '')
    for phrase in GUIDANCE:
        assert phrase in result.output_text
    assert "whole turn" not in result.output_text and "Nothing was charged" not in result.output_text


def test_the_guidance_quotes_a_workspace_with_spaces_and_keeps_the_placeholder_when_unknown() -> None:
    spaced = Path("C:/work space/project")
    text = gateway_registry_mismatch_text("CHAT_GATEWAY_REGISTRY_MISMATCH", spaced)
    assert f'optimus-trust --workspace-root "{spaced}" approve --mode durable' in text
    assert f'optimus-trust --workspace-root "{spaced}" run-gateway' in text
    unknown = gateway_registry_mismatch_text("PLANNING_GATEWAY_REGISTRY_MISMATCH", None)
    assert unknown.startswith("Planning stopped because") and "--workspace-root <workspace> approve" in unknown


def test_the_agent_mode_guidance_reaches_the_client() -> None:
    assert "PLANNING_GATEWAY_REGISTRY_MISMATCH" in _PLANNING_TERMINAL_STOP_REASONS


@pytest.mark.parametrize("kind", ["unenforced", "other-registry"])
def test_the_summarizers_bound_request_is_refused_the_same_way(kind: str) -> None:
    gateway, code = _adopted_gateway(kind)
    attachment = ordinary_attachment(snapshot=_shipped(), model_id=HAIKU, gateway_client=_client(gateway), shared_secret=SHARED_SECRET)
    assert attachment is not None
    route = attachment.summarizer_route
    identity = MaintenanceIdentity(
        session_id="s", turn_seq=3, model_id=route.model_id, role=route.role, route=route.route, reasoning=route.reasoning,
        quantizations=route.quantizations, strategy="compaction", revision_digest="r", registry_hash=_shipped().effective_hash,
    )  # fmt: skip

    response = attachment.summarizer(identity, lambda text: True)(prompt="Summarize the notes.", max_output_tokens=8_192)

    assert response.text is None and gateway.upstream.calls == []
    assert [(status, body["code"]) for status, body in gateway.replies] == [(400, code)]
    assert gateway.payloads[0]["route_binding"]["registry_hash"] == _shipped().effective_hash
    assert [(attempt.outcome, attempt.cost_usd) for attempt in response.attempts] == [("rejected", Decimal("0"))]
