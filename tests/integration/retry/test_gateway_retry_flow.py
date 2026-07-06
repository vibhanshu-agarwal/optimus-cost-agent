from __future__ import annotations

from pathlib import Path

from optimus.gateway.errors import GatewayHttpError
from optimus.retry.policy import RetryController, RetryPolicy


def test_gateway_503_twice_then_success_does_not_write_until_success(tmp_path):
    target = tmp_path / "result.txt"
    calls: list[int] = []

    def gateway_then_write() -> str:
        calls.append(len(calls) + 1)
        if len(calls) < 3:
            assert not target.exists()
            raise GatewayHttpError(503, "temporary outage")
        target.write_text("success", encoding="utf-8")
        return "success"

    result = RetryController(
        policy=RetryPolicy(max_retries=3, base_delay_ms=1, jitter_ms=(0,)),
        sleep_ms=lambda delay_ms: None,
    ).run(gateway_then_write)

    assert result.value == "success"
    assert result.retry_count == 2
    assert Path(target).read_text(encoding="utf-8") == "success"
