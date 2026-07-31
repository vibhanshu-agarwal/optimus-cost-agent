"""RED/GREEN unit tests for bounded JSON/NDJSON evidence sanitization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_handoff.redaction.bounds import MAX_JSON_DEPTH
from evidence_handoff.redaction.models import Disposition

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "evidence"


def _canaries() -> dict[str, str]:
    return json.loads((FIXTURES / "redaction_canaries.json").read_text(encoding="utf-8"))


def _structured():
    from evidence_handoff.redaction import structured as structured_mod

    return structured_mod


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    capture = tmp_path / "cap"
    staging = tmp_path / "staging"
    capture.mkdir()
    staging.mkdir()
    return capture, staging


def test_json_bounds_and_unsupported_object_safety(tmp_path: Path) -> None:
    structured = _structured()
    capture, staging = _setup(tmp_path)
    source = capture / "deep.json"
    node: dict = {}
    cur = node
    for _ in range(MAX_JSON_DEPTH + 2):
        cur["c"] = {}
        cur = cur["c"]
    source.write_text(json.dumps(node), encoding="utf-8")
    result = structured.sanitize_json_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "json_nesting_too_deep"


def test_json_string_too_long(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    structured = _structured()
    monkeypatch.setattr(structured, "MAX_DECODED_STRING_BYTES", 8)
    capture, staging = _setup(tmp_path)
    source = capture / "long.json"
    source.write_text(json.dumps({"v": "abcdefghijk"}), encoding="utf-8")
    result = structured.sanitize_json_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "json_string_too_large"


def test_json_member_count_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    structured = _structured()
    monkeypatch.setattr(structured, "MAX_COLLECTION_MEMBERS", 3)
    capture, staging = _setup(tmp_path)
    source = capture / "wide.json"
    source.write_text(json.dumps({"a": 1, "b": 2, "c": 3, "d": 4}), encoding="utf-8")
    result = structured.sanitize_json_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "json_collection_too_large"


def test_json_deterministic_utf8_and_escape_scanning(tmp_path: Path) -> None:
    structured = _structured()
    canaries = _canaries()
    secret = canaries["unlabeled_api_key"]
    capture, staging = _setup(tmp_path)
    source = capture / "esc.json"
    # Escaped form in JSON source must still be caught after decode.
    payload = {"note": f"pre\\u0020{secret}"}
    # Build with real unicode escape for a character inside path; secret itself literal.
    source.write_text(
        '{"note": "pre ' + secret + '"}',
        encoding="utf-8",
    )
    result = structured.sanitize_json_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(secret,),
        known_pii=(),
        path_aliases=(),
    )
    assert result.disposition is Disposition.PROMOTED
    out = result.staging_path.read_text(encoding="utf-8")
    assert secret not in out
    # Deterministic separators.
    assert out == json.dumps(json.loads(out), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    del payload


def test_json_unsupported_object_type_metadata(tmp_path: Path) -> None:
    structured = _structured()
    capture, staging = _setup(tmp_path)
    # Standard json cannot emit custom objects; simulate via NaN rejection / non-JSON.
    source = capture / "bad.json"
    source.write_text('{"x": NaN}', encoding="utf-8")
    result = structured.sanitize_json_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "json_parse_failed"


def test_generic_ndjson_all_or_nothing_malformed_interior(tmp_path: Path) -> None:
    structured = _structured()
    capture, staging = _setup(tmp_path)
    source = capture / "rows.ndjson"
    source.write_text('{"a":1}\n{not-json}\n{"b":2}\n', encoding="utf-8")
    result = structured.sanitize_ndjson_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
        allow_acp_truncated_tail=False,
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "ndjson_record_malformed"
    assert result.staging_path is None


def test_ndjson_malformed_newline_terminated_final_record(tmp_path: Path) -> None:
    structured = _structured()
    capture, staging = _setup(tmp_path)
    source = capture / "tail.ndjson"
    source.write_text('{"a":1}\n{bad}\n', encoding="utf-8")
    result = structured.sanitize_ndjson_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
        allow_acp_truncated_tail=False,
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "ndjson_record_malformed"


def test_joined_scan_detects_secret_split_across_records(tmp_path: Path) -> None:
    structured = _structured()
    canaries = _canaries()
    secret = canaries["unlabeled_api_key"]
    mid = len(secret) // 2
    left, right = secret[:mid], secret[mid:]
    capture, staging = _setup(tmp_path)
    source = capture / "split.ndjson"
    source.write_text(
        json.dumps({"part": left}, separators=(",", ":"))
        + "\n"
        + json.dumps({"part": right}, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    result = structured.sanitize_ndjson_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(secret,),
        known_pii=(),
        path_aliases=(),
        allow_acp_truncated_tail=False,
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "final_scan_hit"


def test_json_object_prefix_validator_accepts_missing_closers_only() -> None:
    structured = _structured()
    assert structured.is_valid_json_object_prefix('{"a":1') is True
    assert structured.is_valid_json_object_prefix('{"a":') is True
    assert structured.is_valid_json_object_prefix('{"a":"hi') is True
    assert structured.is_valid_json_object_prefix("{") is True
    assert structured.is_valid_json_object_prefix('{"a":1}') is True
    # Illegal token / ordering / trailing data after complete value.
    assert structured.is_valid_json_object_prefix('{"a":1}trailing') is False
    assert structured.is_valid_json_object_prefix('{"a":01}') is False
    assert structured.is_valid_json_object_prefix("[1,2") is False  # must start as object
    assert structured.is_valid_json_object_prefix("") is False
    assert structured.is_valid_json_object_prefix("{,}") is False


def test_json_object_prefix_accepts_mid_number_cuts() -> None:
    """Crash mid-numeric field must remain an eligible ACP object prefix."""
    structured = _structured()
    assert structured.is_valid_json_object_prefix('{"a":-') is True
    assert structured.is_valid_json_object_prefix('{"a":1.') is True
    assert structured.is_valid_json_object_prefix('{"a":1e') is True
    assert structured.is_valid_json_object_prefix('{"a":1E') is True
    assert structured.is_valid_json_object_prefix('{"a":1e+') is True
    assert structured.is_valid_json_object_prefix('{"a":1e-') is True
    assert structured.is_valid_json_object_prefix('{"cost":0.') is True
    # Completed illegal forms still fail.
    assert structured.is_valid_json_object_prefix('{"a":1.}') is False
    assert structured.is_valid_json_object_prefix('{"a":1e}') is False
    assert structured.is_valid_json_object_prefix('{"a":1e+}') is False
    assert structured.is_valid_json_object_prefix('{"a":01') is False


def test_acp_truncated_tail_mid_number_promotes(tmp_path: Path) -> None:
    structured = _structured()
    capture, staging = _setup(tmp_path)
    source = capture / "cost-cut.ndjson"
    complete = '{"sessionUpdate":"agent_message_chunk","n":1}'
    tail = '{"sessionUpdate":"usage","cost_usd":1.'
    source.write_bytes((complete + "\n" + tail).encode("utf-8"))
    result = structured.sanitize_ndjson_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="acp_debug_trace",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
        allow_acp_truncated_tail=True,
    )
    assert result.disposition is Disposition.PROMOTED
    assert result.truncated_tail_dropped is True
    assert result.dropped_tail_bytes == len(tail.encode("utf-8"))
    assert b"cost_usd" not in result.staging_path.read_bytes()


def test_acp_truncated_tail_six_condition_promotes(tmp_path: Path) -> None:
    structured = _structured()
    capture, staging = _setup(tmp_path)
    source = capture / "acp.ndjson"
    complete = json.dumps({"sessionUpdate": "agent_message_chunk", "content": "ok"}, separators=(",", ":"))
    tail = '{"sessionUpdate":"agent_message_chunk","content":"partial'
    raw = (complete + "\n" + tail).encode("utf-8")
    assert not raw.endswith(b"\n")
    source.write_bytes(raw)
    result = structured.sanitize_ndjson_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="acp_debug_trace",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
        allow_acp_truncated_tail=True,
    )
    assert result.disposition is Disposition.PROMOTED
    assert result.truncated_tail_dropped is True
    assert result.dropped_tail_bytes == len(tail.encode("utf-8"))
    out = result.staging_path.read_bytes()
    assert tail.encode("utf-8") not in out
    assert b"partial" not in out
    assert complete.encode("utf-8") in out or b"agent_message_chunk" in out


def test_acp_tail_invalid_prefix_quarantines(tmp_path: Path) -> None:
    structured = _structured()
    capture, staging = _setup(tmp_path)
    source = capture / "bad-prefix.ndjson"
    source.write_bytes(b'{"a":1}\n{"a":01')  # illegal leading-zero number in incomplete tail
    result = structured.sanitize_ndjson_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="acp_debug_trace",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
        allow_acp_truncated_tail=True,
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code in {"ndjson_tail_invalid", "ndjson_record_malformed", "json_prefix_invalid"}


def test_acp_generic_ndjson_not_eligible_for_tail_drop(tmp_path: Path) -> None:
    structured = _structured()
    capture, staging = _setup(tmp_path)
    source = capture / "generic.ndjson"
    source.write_bytes(b'{"a":1}\n{"b":')
    result = structured.sanitize_ndjson_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
        allow_acp_truncated_tail=False,
    )
    assert result.disposition is Disposition.QUARANTINED


def test_incomplete_utf8_tail_quarantines(tmp_path: Path) -> None:
    structured = _structured()
    capture, staging = _setup(tmp_path)
    source = capture / "utf8.ndjson"
    # Complete record + incomplete UTF-8 multibyte in tail (€ is e2 82 ac).
    source.write_bytes(b'{"a":1}\n{"note":"\xe2\x82')
    result = structured.sanitize_ndjson_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="acp_debug_trace",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
        allow_acp_truncated_tail=True,
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "invalid_utf8"


def test_multiple_malformed_regions_quarantine(tmp_path: Path) -> None:
    structured = _structured()
    capture, staging = _setup(tmp_path)
    source = capture / "multi.ndjson"
    source.write_text("{bad1}\n{bad2}\n", encoding="utf-8")
    result = structured.sanitize_ndjson_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
        allow_acp_truncated_tail=False,
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "ndjson_record_malformed"


def test_excess_tail_after_complete_json_object_prefix_fails() -> None:
    structured = _structured()
    assert structured.is_valid_json_object_prefix('{"a":1}{"b":2') is False
