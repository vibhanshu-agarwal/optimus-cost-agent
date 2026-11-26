"""#650: ledger.delivery_status initializes a reader capability only when the store says it is absent."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from evidence_handoff.ledger.errors import LedgerStoreError


class _Store:
    def __init__(self, lookup_error: Exception) -> None:
        self.lookup_error = lookup_error
        self.upserts: list[Any] = []

    def get_reader_capability(self, principal_id: str) -> Any:
        raise self.lookup_error

    def upsert_reader_capability(self, capability: Any) -> None:
        raise AssertionError("delivery_status must not overwrite a capability")

    def insert_reader_capability_if_absent(self, capability: Any) -> None:
        self.upserts.append(capability)

    def global_integrity_fact(self) -> dict[str, Any]:
        return {"latched": False}

    def touch_authenticated_request(self, **_: Any) -> None:
        return None

    def retired_agent_ids(self) -> frozenset[str]:
        return frozenset()


def _delivery_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, store: _Store):
    import mcp.server.mcpserver as mcpserver

    import evidence_handoff_runtime.observability as observability
    from evidence_handoff_runtime import service

    servers: list[Any] = []

    class _RecordingServer(mcpserver.MCPServer):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            servers.append(self)

    enrollment = SimpleNamespace(principal_id="reader-p", agent_id="reader-a", scopes=frozenset({"ledger.read"}))
    validator = MagicMock()
    validator.enrollments = {("inst", "reader-p"): enrollment}
    auth_ctx = {
        "validator": validator,
        "sessions": MagicMock(),
        "store": store,
        "ledger_instance_id": "inst",
        "known_agent_ids": frozenset({"reader-a"}),
        "retired_agent_ids": frozenset(),
        "service_secrets": (),
        "identity_values": (),
        "path_aliases": (),
        "temporary_capture_root": tmp_path / "capture",
        "staging_root": tmp_path / "staging",
        "quarantine_root": tmp_path / "quarantine",
        "forbidden_persistence_roots": (),
        "_bound_request": {"authorization": "Bearer synthetic", "session_id": "sid-1"},
    }
    monkeypatch.setattr(mcpserver, "MCPServer", _RecordingServer)
    monkeypatch.setattr(service, "_load_auth_context", lambda runtime, bundle: auth_ctx)
    monkeypatch.setattr(observability, "build_delivery_views", lambda store: ())
    runtime = {
        "bind_host": "127.0.0.1",
        "bind_port": 8765,
        "allowed_origins": ["http://127.0.0.1:8765"],
        "request_limits": {"max_body_bytes": 65536},
        "protocol_versions": ["2025-11-25"],
    }
    service.build_asgi_app(runtime, auth_bundle={"synthetic": True})
    return servers[0]._tool_manager.get_tool("ledger.delivery_status").fn


def test_absent_capability_is_initialized(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = _Store(LedgerStoreError("capability_not_found"))
    _delivery_status(monkeypatch, tmp_path, store)()
    assert [(cap.principal_id, cap.supported_schemas) for cap in store.upserts] == [("reader-p", frozenset())]


@pytest.mark.parametrize(
    "error",
    [LedgerStoreError("capability_row_corrupt"), OSError("connection reset"), ValueError("bad row")],
)
def test_storage_uncertainty_leaves_capability_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error: Exception
) -> None:
    store = _Store(error)
    with pytest.raises(type(error)):
        _delivery_status(monkeypatch, tmp_path, store)()
    assert store.upserts == []
