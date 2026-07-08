import pytest

from optimus.acp.preflight import PreflightFailure, run_preflight


def test_live_redis_fixture_fails_loud_when_redis_url_missing(monkeypatch):
    monkeypatch.delenv("OPTIMUS_REDIS_URL", raising=False)
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.optimus.ai")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt-test")

    with pytest.raises(pytest.fail.Exception, match="OPTIMUS_REDIS_URL"):
        try:
            run_preflight(require_timeseries=True)
        except PreflightFailure as exc:
            pytest.fail(exc.user_message)
