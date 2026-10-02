"""Shared fixtures for the Plan 12.2 Task 5 Gateway model-policy tests (not a test module).

``VERIFIED_POLICY`` is a non-fixture registry whose routes, estimator and reserve are marked verified,
so the enforcer's admit path can be exercised offline. It is test data, never a shipped policy.
"""

from __future__ import annotations

import textwrap
from decimal import Decimal
from pathlib import Path
from typing import Any

from optimus_gateway.model_policy import GatewayModelPolicy
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.upstream_client import ProviderMessageResult, UpstreamAttemptFailure
from optimus_model_policy import Message, RegistrySnapshot, load_registry
from optimus_model_policy.binding import RouteBinding, disclosure_key, issue_disclosure, payload_digest, route_digest

SHARED_SECRET = "policy-test-shared-secret"  # pragma: allowlist secret - synthetic test fixture
PROVIDER_KEY = "sk-or-policy-test"  # pragma: allowlist secret - synthetic test fixture
CAP = 16384
# effective_total = min(262144, 300000) = 262144; usable = 262144 - 16384 = 245760.
# tokens = ceil(0.5 * bytes) + 8 per message + 64 fixed; one message -> 72 framing tokens, so the
# largest admitted single-message input is 2 * (245760 - 72) = 491376 UTF-8 bytes.
LIMIT_BYTES = 491_376

VERIFIED_POLICY = textwrap.dedent(
    """\
    schema_version: 1
    policy_version: "task5-verified-test"
    fixture: false
    context_ceiling_tokens: 262144
    output_reserve_tokens: {implementer: 16384, summarizer: 8192}
    estimators:
      half:
        method: utf8-bytes-ratio
        tokens_per_byte: "0.5"
        per_message_tokens: 8
        fixed_tokens: 64
        verified: true
    role_price_blends: {}
    alerts: {thresholds_usd: []}
    models:
      cn/alpha:
        origin: china
        tier: cheap
        prices: {input_usd_per_million: "0.10", output_usd_per_million: "0.40"}
        data_use: {provider_may_train_on_inputs: "no", disclosure: none}
        capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [high]}
        default_reasoning: high
        route:
          estimator: half
          endpoints:
            - {provider: alpha-cloud/fp8, quantization: fp8, context_window_tokens: 300000, max_output_tokens: 32768, verified: true}
            - {provider: alpha-backup/bf16, quantization: bf16, context_window_tokens: 400000, max_output_tokens: 20000, verified: true}
      us/contrib:
        origin: non-china
        tier: cheap
        prices: {input_usd_per_million: "0.20", output_usd_per_million: "0.80"}
        data_use: {provider_may_train_on_inputs: "yes", disclosure: contributor}
        capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [high]}
        default_reasoning: high
        route:
          estimator: half
          endpoints:
            - {provider: contrib-ai/bf16, quantization: bf16, context_window_tokens: 300000, max_output_tokens: 32768, verified: true}
      cn/nullquant:
        origin: china
        tier: cheap
        prices: {input_usd_per_million: "0.30", output_usd_per_million: "1.20"}
        data_use: {provider_may_train_on_inputs: "no", disclosure: none}
        capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [high]}
        default_reasoning: high
        route:
          estimator: half
          endpoints:
            - {provider: null-quant, quantization: null, context_window_tokens: 300000, max_output_tokens: 32768, verified: true}
      us/idle:
        origin: non-china
        tier: cheap
        prices: {input_usd_per_million: "0.05", output_usd_per_million: "0.10"}
        data_use: {provider_may_train_on_inputs: "no", disclosure: none}
        capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [high]}
        default_reasoning: high
        route:
          estimator: half
          endpoints:
            - {provider: idle-ai/fp8, quantization: fp8, context_window_tokens: 300000, max_output_tokens: 32768, verified: true}
    roles:
      medium: [cn/alpha, us/contrib, cn/nullquant]
    """
)


def verified_snapshot(tmp_path: Path, text: str = VERIFIED_POLICY) -> RegistrySnapshot:
    path = tmp_path / "verified-registry.yaml"
    path.write_text(text, encoding="utf-8")
    return load_registry(path, None)


def model_policy(snapshot: RegistrySnapshot, *, approved_hash: str | None = None) -> GatewayModelPolicy:
    return GatewayModelPolicy.for_launch(
        snapshot=snapshot,
        approved_hash=snapshot.effective_hash if approved_hash is None else approved_hash,
        shared_secret=SHARED_SECRET,
    )


def gateway_config(policy: GatewayModelPolicy | None = None) -> GatewayServiceConfig:
    return GatewayServiceConfig(
        bind_host="127.0.0.1",
        bind_port=8765,
        shared_secret=SHARED_SECRET,
        provider="openrouter",
        provider_api_key=PROVIDER_KEY,
        base_url="https://openrouter.ai/api/v1",
        model_policy=policy,
    )


AUTH = f"Bearer {SHARED_SECRET}"


def binding(
    snapshot: RegistrySnapshot,
    *,
    model: str = "cn/alpha",
    input_text: str = "plan the change",
    output_cap: int = CAP,
    request_id: str = "req-1",
    disclose: bool = False,
    secret: str = SHARED_SECRET,
) -> dict[str, Any]:
    disclosure = None
    if disclose:
        disclosure = issue_disclosure(
            disclosure_key(secret),
            request_id=request_id,
            model_id=model,
            route=route_digest(model, snapshot.policy.models[model]),
            payload=payload_digest(
                model, (Message("user", input_text),), output_cap, reasoning=snapshot.policy.models[model].default_reasoning
            ),
        )
    return RouteBinding(
        registry_hash=snapshot.effective_hash, request_id=request_id, output_cap=output_cap, disclosure=disclosure
    ).to_wire()


class RecordingUpstream:
    """Records every upstream call with exactly the keywords the real client's methods accept.

    ``create_message`` is today's routing; ``create_message_once`` is one enforced attempt, whose
    results can be scripted: each ``attempts`` item is an ``UpstreamAttemptFailure`` to raise, or
    None for a completed reply. With no script every attempt completes.
    """

    def __init__(self, finish_reason: str | None = "stop", attempts: list[UpstreamAttemptFailure | None] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._finish_reason = finish_reason
        self._attempts = list(attempts or [])

    def create_message(self, *, model: str, input_text: str) -> ProviderMessageResult:
        self.calls.append({"legacy": True, "model": model, "input_text": input_text})
        return self._result(model)

    def create_message_once(
        self, *, model: str, input_text: str, max_tokens: int, provider_controls: Any, reasoning: str | None
    ) -> ProviderMessageResult:
        self.calls.append(
            {
                "model": model,
                "input_text": input_text,
                "max_tokens": max_tokens,
                "provider_controls": provider_controls,
                "reasoning": reasoning,
            }
        )
        planned = self._attempts.pop(0) if self._attempts else None
        if planned is not None:
            raise planned
        return self._result(model)

    def _result(self, model: str) -> ProviderMessageResult:
        return ProviderMessageResult(
            message_id=f"gen-{len(self.calls)}",
            output_text="WRITE a.py\nx\nTEST pytest -q",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            billing_units=15,
            cost_usd=Decimal("0.0002"),
            provider="openrouter",
            resolved_provider="Alpha",
            requested_model=model,
            resolved_model=model,
            model_version=None,
            cache_hit=False,
            finish_reason=self._finish_reason,
        )
