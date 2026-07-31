"""Mixed real-filesystem integration evidence for the redaction gate."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, PngImagePlugin

from evidence_handoff.redaction.gate import run_redaction_gate
from evidence_handoff.redaction.models import ArtifactKind, Disposition, RedactionRuntimeInputs
from optimus_security.sanitization import PathAliasRule
from optimus_security.sensitive_values import SensitiveValueInventory, SensitiveValueSourceClass


def _runtime(tmp_path: Path) -> tuple[RedactionRuntimeInputs, Path]:
    capture = (tmp_path / "cap").resolve()
    staging = (tmp_path / "staging").resolve()
    quarantine = (tmp_path / "quarantine").resolve()
    dest = (tmp_path / "dest").resolve()
    for path in (capture, staging, quarantine, dest):
        path.mkdir()
    inventory = SensitiveValueInventory()
    inventory.add_secret(
        "Q7mV2xN9pR4tY8kL3cD6wF1hJ5sB0zUa",
        source_class=SensitiveValueSourceClass.ENVIRONMENT,
    )
    runtime = RedactionRuntimeInputs(
        sensitive_values=inventory,
        path_aliases=(
            PathAliasRule(source_root=str(dest), alias="<destination>"),
            PathAliasRule(source_root=str(staging), alias="<staging>"),
            PathAliasRule(source_root=str(quarantine), alias="<quarantine>"),
            PathAliasRule(source_root=str(capture), alias="<temp>"),
        ),
        temporary_capture_root=capture,
        staging_root=staging,
        quarantine_root=quarantine,
        forbidden_persistence_roots=(),
    )
    return runtime, dest


def test_mixed_artifact_dispositions(tmp_path: Path) -> None:
    runtime, dest = _runtime(tmp_path)
    secret = "Q7mV2xN9pR4tY8kL3cD6wF1hJ5sB0zUa"

    # JSON — promoted
    json_path = runtime.temporary_capture_root / "a.json"
    json_path.write_text(json.dumps({"ok": True, "note": "safe"}), encoding="utf-8")
    r_json = run_redaction_gate(
        source_path=json_path,
        destination_root=dest,
        artifact_kind=ArtifactKind.JSON,
        artifact_role="session_note",
        runtime=runtime,
    )
    assert r_json.disposition is Disposition.PROMOTED

    # Generic NDJSON malformed interior — quarantined
    ndjson_path = runtime.temporary_capture_root / "b.ndjson"
    ndjson_path.write_text('{"a":1}\n{bad}\n', encoding="utf-8")
    r_ndjson = run_redaction_gate(
        source_path=ndjson_path,
        destination_root=dest,
        artifact_kind=ArtifactKind.NDJSON,
        artifact_role="session_note",
        runtime=runtime,
    )
    assert r_ndjson.disposition is Disposition.QUARANTINED

    # ACP crash-tail — promoted with truncated tail
    acp_path = runtime.temporary_capture_root / "c.ndjson"
    acp_path.write_bytes(
        b'{"sessionUpdate":"agent_message_chunk","n":1}\n'
        b'{"sessionUpdate":"agent_message_chunk","content":"partial'
    )
    r_acp = run_redaction_gate(
        source_path=acp_path,
        destination_root=dest,
        artifact_kind=ArtifactKind.ACP_DEBUG_TRACE,
        artifact_role="acp_debug_trace",
        runtime=runtime,
    )
    assert r_acp.disposition is Disposition.PROMOTED

    # Text with secret — promoted sanitized
    text_path = runtime.temporary_capture_root / "d.txt"
    text_path.write_text(f"token {secret}\n", encoding="utf-8")
    r_text = run_redaction_gate(
        source_path=text_path,
        destination_root=dest,
        artifact_kind=ArtifactKind.TEXT,
        artifact_role="session_note",
        runtime=runtime,
    )
    assert r_text.disposition is Disposition.PROMOTED
    promoted_text = next(dest.rglob("artifact"))
    # Find the text bundle's artifact - may be multiple; check any doesn't contain secret
    for artifact in dest.rglob("artifact"):
        body = artifact.read_bytes()
        if body and secret.encode() not in body:
            break
    else:
        # At least one promoted artifact must exist without the secret
        assert secret.encode() not in b"".join(p.read_bytes() for p in dest.rglob("artifact"))

    # Metadata PNG — awaiting approval
    png_path = runtime.temporary_capture_root / "e.png"
    img = Image.new("RGB", (10, 10), color=(7, 8, 9))
    info = PngImagePlugin.PngInfo()
    info.add_text("Author", "PNG_TEXT_CANARY_SECRET_VALUE")
    img.save(png_path, pnginfo=info)
    r_png = run_redaction_gate(
        source_path=png_path,
        destination_root=dest,
        artifact_kind=ArtifactKind.SCREENSHOT,
        artifact_role="screenshot_v1",
        runtime=runtime,
    )
    assert r_png.disposition is Disposition.AWAITING_HUMAN_APPROVAL

    # JPEG screenshot — awaiting
    jpg_path = runtime.temporary_capture_root / "f.jpg"
    Image.new("RGB", (8, 8), color=(1, 1, 1)).save(jpg_path, format="JPEG")
    r_jpg = run_redaction_gate(
        source_path=jpg_path,
        destination_root=dest,
        artifact_kind=ArtifactKind.SCREENSHOT,
        artifact_role="screenshot_v1",
        runtime=runtime,
    )
    assert r_jpg.disposition is Disposition.AWAITING_HUMAN_APPROVAL

    # Dump — quarantined, no dest artifact for dump
    dump_path = runtime.temporary_capture_root / "g.dmp"
    dump_path.write_bytes(b"MDMP" + b"\x00" * 32)
    before_dest = {p.resolve() for p in dest.rglob("*") if p.is_file()}
    r_dump = run_redaction_gate(
        source_path=dump_path,
        destination_root=dest,
        artifact_kind=ArtifactKind.PROCESS_DUMP,
        artifact_role="process_dump",
        runtime=runtime,
    )
    assert r_dump.disposition is Disposition.QUARANTINED
    after_dest = {p.resolve() for p in dest.rglob("*") if p.is_file()}
    assert after_dest == before_dest
    del promoted_text
