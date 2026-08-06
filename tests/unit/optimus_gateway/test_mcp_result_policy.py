from __future__ import annotations

import pytest

from optimus_gateway.mcp_invocation import MCPResultPolicyError, validate_mcp_result
from optimus_gateway.mcp_models import MCPBindingSummary

_BINDING = MCPBindingSummary(
    profile_id="context7",
    profile_revision="rev-1",
    manifest_hash="a" * 64,
)


def _result(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "result_type": "complete",
        "content": [{"type": "text", "text": "untrusted server text"}],
        "disposition": "mcp.call.complete",
        "binding": _BINDING.model_dump(mode="json"),
        "transport": "http",
        "protocol_version": "2026-07-28",
        "attribution": "explicit_zero",
        "usage": {
            "gateway_request_id": "gw-mcp-1",
            "attribution": "explicit_zero",
            "billing_units": 0,
            "cost_usd": "0",
        },
    }
    result.update(overrides)
    return result


def test_complete_result_is_strictly_typed_but_content_stays_untrusted():
    response = validate_mcp_result(_result(), expected_binding=_BINDING)

    assert response.result_type == "complete"
    assert response.content[0].type == "text"
    assert response.content[0].text == "untrusted server text"


def test_input_required_is_a_typed_call_scoped_denial():
    with pytest.raises(MCPResultPolicyError, match="input_required") as exc_info:
        validate_mcp_result(_result(result_type="input_required"), expected_binding=_BINDING)

    assert exc_info.value.disposition == "mcp.call.input_required"


@pytest.mark.parametrize(
    "content",
    (
        [{"type": "image", "data": "base64"}],
        [{"type": "audio", "data": "base64"}],
        [{"type": "text", "text": "ok", "uri": "https://attacker.example"}],
    ),
)
def test_non_releasable_or_malformed_content_is_rejected(content: list[dict[str, object]]):
    with pytest.raises(MCPResultPolicyError):
        validate_mcp_result(_result(content=content), expected_binding=_BINDING)


def test_binding_drift_is_rejected_before_result_release():
    wrong_binding = _BINDING.model_copy(update={"manifest_hash": "b" * 64})

    with pytest.raises(MCPResultPolicyError, match="binding"):
        validate_mcp_result(
            _result(binding=wrong_binding.model_dump(mode="json")),
            expected_binding=_BINDING,
        )
