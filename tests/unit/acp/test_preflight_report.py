from __future__ import annotations

from optimus.acp.preflight import (
    PreflightCheckResult,
    collect_preflight_checks,
    first_preflight_failure,
    format_preflight_table,
)


def test_format_preflight_table_renders_pass_and_fail_rows():
    checks = [
        PreflightCheckResult(name="gateway credentials", passed=True, detail="present"),
        PreflightCheckResult(name="redis connectivity", passed=False, detail="down"),
    ]

    table = format_preflight_table(checks)

    assert "gateway credentials  PASS" in table
    assert "redis connectivity" in table
    assert "FAIL" in table
    assert "down" in table


def test_first_preflight_failure_returns_first_failed_check():
    checks = [
        PreflightCheckResult(name="gateway credentials", passed=True, detail="present"),
        PreflightCheckResult(name="redis url", passed=False, detail="missing"),
    ]

    failed = first_preflight_failure(checks)

    assert failed is not None
    assert failed.name == "redis url"


def test_collect_preflight_checks_reports_missing_gateway_credentials(monkeypatch):
    monkeypatch.delenv("OPTIMUS_GATEWAY_URL", raising=False)
    monkeypatch.delenv("OPTIMUS_API_KEY", raising=False)
    monkeypatch.delenv("OPTIMUS_REDIS_URL", raising=False)

    checks = collect_preflight_checks({}, workspace_root=None, strict=False, require_timeseries=False)

    failed = first_preflight_failure(checks)
    assert failed is not None
    assert failed.name == "gateway credentials"
