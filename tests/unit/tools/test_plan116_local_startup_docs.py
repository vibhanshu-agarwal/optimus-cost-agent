"""Plan 11.6 Task 5: single operator runbook presence and retirement assertions.

These documentation-surface tests enforce one living operator sequence for local
Redis/Gateway/Phoenix startup and reject competing active launcher instructions.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNBOOK_PATH = (
    REPO_ROOT / "docs/superpowers/plans/2026-07-29-plan-11-6-local-live-dependencies-operator-runbook.md"
)
README_PATH = REPO_ROOT / "README.md"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
ENV_GATEWAY_EXAMPLE_PATH = REPO_ROOT / ".env.gateway.example"
PREFLIGHT_PATH = REPO_ROOT / "src/optimus/acp/preflight.py"
PHOENIX_LIVE_TEST_PATH = REPO_ROOT / "tests/integration/telemetry/test_phoenix_live.py"

_DOCKER_RUN_REDIS = re.compile(r"docker\s+run\b[\s\S]{0,120}\bredis\b", re.IGNORECASE)
_DOCKER_RUN_PHOENIX = re.compile(r"docker\s+run\b[\s\S]{0,120}\barizephoenix\b", re.IGNORECASE)


def test_operator_runbook_documents_single_local_startup_sequence() -> None:
    assert RUNBOOK_PATH.is_file(), f"missing operator runbook at {RUNBOOK_PATH}"
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")

    assert "optimus-trust setup-credentials" in runbook
    assert "optimus-trust --workspace-root" in runbook
    assert "optimus-agent --workspace-root" in runbook
    assert "run-gateway --with-local-phoenix" in runbook
    assert "--check-config --strict" in runbook
    assert "--with-local-phoenix" in runbook
    assert "REDIS_PORT_CONFLICT" in runbook
    assert "docker ps --filter publish=6379" in runbook
    assert "Optimus never stops or deletes the conflicting container" in runbook
    assert "--no-auto-start" in runbook
    assert "acpx" in runbook


def test_retired_wrapper_scripts_are_absent() -> None:
    assert not Path("tools/run_local_gateway.sh").exists()
    assert not Path("tools/run_local_gateway.ps1").exists()


def test_active_guidance_has_no_competing_launcher_instructions() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    preflight = PREFLIGHT_PATH.read_text(encoding="utf-8")
    phoenix_live = PHOENIX_LIVE_TEST_PATH.read_text(encoding="utf-8")
    gateway_example = ENV_GATEWAY_EXAMPLE_PATH.read_text(encoding="utf-8")
    agent_env = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

    for name, text in (
        ("README.md", readme),
        ("preflight.py", preflight),
        ("test_phoenix_live.py", phoenix_live),
        (".env.gateway.example", gateway_example),
    ):
        assert "run_local_gateway" not in text, f"{name} still mentions run_local_gateway"
        assert _DOCKER_RUN_REDIS.search(text) is None, f"{name} still embeds docker run … redis"
        assert _DOCKER_RUN_PHOENIX.search(text) is None, f"{name} still embeds docker run … arizephoenix"

    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in agent_env
    assert "Phoenix" not in agent_env
    assert "6006" not in agent_env

    assert "plan-11-6-local-live-dependencies-operator-runbook.md" in readme
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in gateway_example
    assert "Gateway child" in gateway_example or "Gateway-child" in gateway_example
    assert "never exported into the agent shell" in gateway_example.lower() or (
        "never" in gateway_example.lower() and "agent shell" in gateway_example.lower()
    )
