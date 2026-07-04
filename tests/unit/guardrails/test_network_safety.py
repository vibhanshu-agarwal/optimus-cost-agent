from optimus.guardrails.network_safety import NetworkSafetyValidator, ValidationVerdict


def test_plain_http_is_blocked():
    validator = NetworkSafetyValidator(allowed_hosts=("gateway.optimus.ai",))

    result = validator.validate_url("http://gateway.optimus.ai/v1/responses")

    assert result.verdict is ValidationVerdict.BLOCK
    assert result.rule_id == "network.insecure_transport"


def test_gateway_host_allows_https():
    validator = NetworkSafetyValidator(allowed_hosts=("gateway.optimus.ai",))

    result = validator.validate_url("https://gateway.optimus.ai/v1/responses")

    assert result.verdict is ValidationVerdict.ALLOW


def test_unexpected_host_is_held():
    validator = NetworkSafetyValidator(allowed_hosts=("gateway.optimus.ai",))

    result = validator.validate_url("https://example.com/download.sh")

    assert result.verdict is ValidationVerdict.HOLD
    assert result.rule_id == "network.unexpected_egress"
