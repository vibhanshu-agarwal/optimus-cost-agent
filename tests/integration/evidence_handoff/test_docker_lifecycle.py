"""Live Windows evidence: PostgreSQL started via real Docker Desktop on loopback only.

Task 1 RED: adapter/factory must be absent — these assertions fail until Task 2 GREEN.
Task 3 expands this module with real Docker start/health/restart/cleanup proof.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.requires_evidence_handoff_postgres


def test_docker_postgres_adapter_and_factory_are_registered() -> None:
    """Fails while DockerPostgresBackend / build_store_backend are missing (Task 1 RED)."""
    from evidence_handoff_runtime.backends import DockerPostgresBackend, build_store_backend

    assert DockerPostgresBackend is not None
    assert callable(build_store_backend)
