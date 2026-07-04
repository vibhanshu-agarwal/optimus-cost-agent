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


def test_literal_private_ip_target_is_blocked():
    validator = NetworkSafetyValidator(allowed_hosts=("gateway.optimus.ai",))

    result = validator.validate_url("https://169.254.169.254/latest/meta-data/")

    assert result.verdict is ValidationVerdict.BLOCK
    assert result.rule_id == "network.private_ip_target"


def test_literal_loopback_target_is_blocked():
    validator = NetworkSafetyValidator(allowed_hosts=("gateway.optimus.ai",))

    result = validator.validate_url("https://127.0.0.1/admin")

    assert result.verdict is ValidationVerdict.BLOCK
    assert result.rule_id == "network.loopback_target"
