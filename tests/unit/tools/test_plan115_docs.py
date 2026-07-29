"""Plan 11.5 Task 7: charter and living-doc correction assertions.

These are documentation-text tests: they read the committed working-tree text
of the charter, README, and env examples and assert that the stale
LangSmith/amortized-cost passages are gone, the approved replacement wording
is present, and the Gateway-only OTLP endpoint placement is honored.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHARTER_PATH = REPO_ROOT / "docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md"
README_PATH = REPO_ROOT / "README.md"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
ENV_GATEWAY_EXAMPLE_PATH = REPO_ROOT / ".env.gateway.example"


def test_charter_no_longer_names_langsmith_or_amortized_cost() -> None:
    charter = CHARTER_PATH.read_text(encoding="utf-8")
    assert "LangSmith trace export" not in charter
    assert "amortized observability cost" not in charter


def test_charter_states_approved_replacement_wording() -> None:
    charter = CHARTER_PATH.read_text(encoding="utf-8")
    assert "authenticated structured agent-to-Gateway trace ingress" in charter
    assert "OTel/OTLP export with Phoenix as the local default" in charter
    assert "no allocated or amortized per-request charge" in charter


def test_charter_keeps_authenticated_scoped_to_agent_to_gateway_ingress() -> None:
    charter = CHARTER_PATH.read_text(encoding="utf-8")
    # "authenticated" must modify the agent-to-Gateway ingress, not Phoenix export.
    assert "authenticated" not in charter.split("Phoenix as the local default")[-1][:80]


def test_readme_phase1_accounting_describes_current_fields_and_no_langsmith_charge() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    assert "cost_usd" in readme
    assert "billing_units" in readme
    assert "RedisTimeSeries" in readme
    assert "TraceDeliveryState" in readme
    assert "no allocated or amortized per-request charge" in readme
    assert "LangSmith is not a dependency" in readme


def test_otlp_endpoint_example_lives_only_on_gateway_side() -> None:
    agent_env = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    gateway_env = ENV_GATEWAY_EXAMPLE_PATH.read_text(encoding="utf-8")
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in agent_env
    assert "# OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:6006/v1/traces" in gateway_env
