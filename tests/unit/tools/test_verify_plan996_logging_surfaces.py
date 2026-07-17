from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.verify_plan996_logging_surfaces import SurfaceAuditError, discover_surfaces, load_manifest, main, validate_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = PROJECT_ROOT / "docs" / "superpowers" / "reviews" / "2026-07-15-plan-9-96-logging-surface-audit.json"
KNOWN_TEST_NODE = (
    "tests/unit/tools/test_verify_plan996_logging_surfaces.py::"
    "test_discovers_representative_live_persistence_and_protocol_sinks"
)


def _manifest_entry(key: str) -> dict[str, str]:
    return {
        "key": key,
        "policy": "shared-sanitize",
        "rationale": "Test fixture classification.",
        "sanitizer": "optimus_security.sanitization.sanitize_for_persistence",
        "test_node": KNOWN_TEST_NODE,
        "evidence_tier": "unit",
    }


def test_checked_in_manifest_covers_current_surface_inventory() -> None:
    assert main(["--project-root", str(PROJECT_ROOT), "--manifest", str(MANIFEST_PATH)]) == 0


def test_main_validates_a_complete_manifest(tmp_path) -> None:
    project_root = tmp_path
    source_path = project_root / "src" / "example" / "sink.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("def emit():\n    print('safe')\n", encoding="utf-8")
    test_path = project_root / "tests" / "test_sink.py"
    test_path.parent.mkdir()
    test_path.write_text("def test_emit():\n    assert True\n", encoding="utf-8")
    manifest_path = project_root / "audit.json"
    manifest_path.write_text(
        json.dumps(
            {
                "surfaces": [
                    {
                        **_manifest_entry("example.sink:emit:stdout_export"),
                        "test_node": "tests/test_sink.py::test_emit",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert main(["--project-root", str(project_root), "--manifest", str(manifest_path)]) == 0


def test_load_manifest_requires_a_surface_entry_list(tmp_path) -> None:
    manifest_path = tmp_path / "audit.json"
    manifest_path.write_text(json.dumps({"surfaces": [_manifest_entry("example.module:emit:stderr_export")]}), encoding="utf-8")

    assert load_manifest(manifest_path) == [_manifest_entry("example.module:emit:stderr_export")]


def test_discovers_representative_live_persistence_and_protocol_sinks() -> None:
    """Discovery itself is a guard: known sink patterns must not disappear."""
    discovered = discover_surfaces(PROJECT_ROOT)

    assert {
        "optimus.telemetry.jsonl:JsonlTelemetryWriter.append:jsonl_append",
        "optimus.agent.state_store:RedisAgentStateStore.save_plan:redis_hash_write",
        "optimus.acp.dispatcher:JsonRpcDispatcher.dispatch:jsonrpc_error_response",
        "optimus.acp.spec:AcpDuplexAdapter._handle_session_prompt:structured_exception_export",
        "optimus_gateway.responses:handle_responses_request:http_error_response",
    }.issubset(discovered)


def test_discovers_unexpected_python_and_shell_sink_kinds(tmp_path) -> None:
    source_path = tmp_path / "src" / "example" / "unexpected.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "def emit(exc, redis, logger, writer):\n"
        "    logger.error(str(exc))\n"
        "    redis.hset('state', mapping={})\n"
        "    writer.write(str(exc))\n"
        "\n"
        "def render(count, writer):\n"
        "    writer.write(str(count))\n"
        "\n"
        "def structured(exc):\n"
        "    return JsonRpcError(code=1, message=exc.message, data=exc.data)\n",
        encoding="utf-8",
    )
    script_path = tmp_path / "tools" / "capture.sh"
    script_path.parent.mkdir()
    script_path.write_text("acpx run > transcript.jsonl\n", encoding="utf-8")

    discovered = discover_surfaces(tmp_path)

    assert {
        "example.unexpected:emit:logger_export",
        "example.unexpected:emit:redis_hash_write",
        "example.unexpected:emit:exception_export",
        "example.unexpected:structured:structured_exception_export",
        "tools.capture:script:raw_capture_write",
    }.issubset(discovered)
    assert "example.unexpected:render:exception_export" not in discovered


def test_rejects_discovered_sink_without_manifest_entry() -> None:
    discovered = {"example.module:emit:stderr_export"}

    with pytest.raises(SurfaceAuditError, match="UNCLASSIFIED_SINK"):
        validate_manifest(discovered, [], project_root=PROJECT_ROOT)


def test_rejects_stale_manifest_entry() -> None:
    entries = [_manifest_entry("example.module:missing:jsonl_append")]

    with pytest.raises(SurfaceAuditError, match="STALE_MANIFEST_ENTRY"):
        validate_manifest(set(), entries, project_root=PROJECT_ROOT)


def test_rejects_duplicate_manifest_key() -> None:
    key = "example.module:emit:stderr_export"
    entries = [_manifest_entry(key), _manifest_entry(key)]

    with pytest.raises(SurfaceAuditError, match="DUPLICATE_MANIFEST_KEY"):
        validate_manifest({key}, entries, project_root=PROJECT_ROOT)


def test_rejects_invalid_manifest_policy() -> None:
    key = "example.module:emit:stderr_export"
    entry = _manifest_entry(key)
    entry["policy"] = "trust-me"

    with pytest.raises(SurfaceAuditError, match="INVALID_MANIFEST_POLICY"):
        validate_manifest({key}, [entry], project_root=PROJECT_ROOT)


def test_rejects_manifest_entry_without_required_metadata() -> None:
    key = "example.module:emit:stderr_export"
    entry = _manifest_entry(key)
    del entry["test_node"]

    with pytest.raises(SurfaceAuditError, match="INVALID_MANIFEST_ENTRY"):
        validate_manifest({key}, [entry], project_root=PROJECT_ROOT)


def test_rejects_manifest_entry_with_uncollectible_test_node() -> None:
    key = "example.module:emit:stderr_export"
    entry = _manifest_entry(key)
    entry["test_node"] = "tests/unit/tools/test_verify_plan996_logging_surfaces.py::test_does_not_exist"

    with pytest.raises(SurfaceAuditError, match="UNRESOLVED_TEST_NODE"):
        validate_manifest({key}, [entry], project_root=PROJECT_ROOT)


def test_rejects_synthetic_discovered_sink_until_manifested() -> None:
    """Mutation proof: a newly discovered persistence pattern fails closed."""
    key = "example.module:emit:stderr_export"

    with pytest.raises(SurfaceAuditError, match="UNCLASSIFIED_SINK"):
        validate_manifest({key}, [], project_root=PROJECT_ROOT)

    validate_manifest({key}, [_manifest_entry(key)], project_root=PROJECT_ROOT)
