#!/usr/bin/env python3
"""Offline verifier for Plan 11.19 current-version Zed session/load reprobe evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from optimus_security.sanitization import EVIDENCE_REDACTION_POLICY, sanitize_for_persistence  # noqa: E402

SCHEMA = "plan-11-19-zed-session-load-reprobe-v1"
RELAY_EXTRACT_SOURCE = "opaque-relay-post-run"
ALLOWED_FINDINGS = frozenset({"REACHABLE", "UNREACHABLE", "INDETERMINATE"})
ALLOWED_INDETERMINATE_REASONS = frozenset(
    {
        "PRECONDITION_UNMET",
        "INTERNAL_CAPABILITY_UNAVAILABLE",
        "OBSERVATION_INCOMPLETE",
        "CLEANUP_UNVERIFIED",
        "HERMETIC_INVOCATION_UNAVAILABLE",
        "ALREADY_RUNNING_ZED",
        "RELAY_FAILURE",
        "ISOLATION_PREDICATE_FAILED",
        "LIVE_LAUNCH_UNAUTHORIZED",
    }
)
REQUIRED_FIELDS = (
    "schema",
    "recorded_at_utc",
    "commit",
    "finding",
    "indeterminate_reason",
    "zed",
    "acpx",
    "normal_source",
    "isolated_source",
    "isolated_build",
    "invocation",
    "isolation",
    "capability_payload",
    "relay",
    "captured_exchange",
    "origin_a_launches",
    "zed_launches",
    "files",
)
RELAY_CHILD_STDERR_EXCERPT_LIMIT = 4000
_SHA256_KEY = re.compile(r"sha256|commit|hash", re.I)
_ZED_OVERCLAIM = re.compile(r"zed does not support", re.I)


class VerifyError(RuntimeError):
    """Field-level verifier failure that must not echo secret values."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def require(condition: object, field: str, message: str) -> None:
    if not condition:
        raise VerifyError(field, message)


def _sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerifyError("manifest", "manifest is not readable JSON") from exc
    require(isinstance(payload, dict), "manifest", "manifest must be a JSON object")
    return payload


def _scan_credential_like(value: Any, *, field: str) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _scan_credential_like(nested, field=f"{field}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            _scan_credential_like(nested, field=f"{field}[{index}]")
        return
    if not isinstance(value, str) or _SHA256_KEY.search(field):
        return
    sanitized = sanitize_for_persistence(value, policy=EVIDENCE_REDACTION_POLICY)
    require(sanitized.value == value, field, "raw credential-like value")


def _require_report_relative(report_dir: Path, relative: str) -> Path:
    require(isinstance(relative, str) and relative.strip(), "files", "path is outside the report directory")
    require(not Path(relative).is_absolute(), "files", "path is outside the report directory")
    require(".." not in Path(relative).parts, "files", "path is outside the report directory")
    candidate = (report_dir / relative).resolve()
    require(candidate.is_relative_to(report_dir.resolve()), "files", "path is outside the report directory")
    return candidate


def _verify_files(report_dir: Path, files: Mapping[str, Any], relay: Mapping[str, Any]) -> None:
    require(isinstance(files, Mapping), "files", "files must be an object of relative paths")
    for relative, claimed in files.items():
        path = _require_report_relative(report_dir, str(relative))
        require(path.is_file(), "files", "declared report file is missing")
        require(isinstance(claimed, str) and claimed == _sha256_file(path), str(relative), "SHA-256 mismatch")
    zed_path = report_dir / "relay" / "zed-to-agent.bin"
    agent_path = report_dir / "relay" / "agent-to-zed.bin"
    require(zed_path.is_file() and agent_path.is_file(), "relay", "relay digest files are missing")
    require(
        relay.get("zed_to_agent_sha256") == _sha256_file(zed_path),
        "relay.zed_to_agent_sha256",
        "relay digest mismatch",
    )
    require(
        relay.get("agent_to_zed_sha256") == _sha256_file(agent_path),
        "relay.agent_to_zed_sha256",
        "relay digest mismatch",
    )


def _verify_finding_rule(manifest: Mapping[str, Any]) -> None:
    finding = manifest["finding"]
    require(finding in ALLOWED_FINDINGS, "finding", "finding must be REACHABLE, UNREACHABLE, or INDETERMINATE")
    exchange = manifest.get("captured_exchange")
    if finding == "REACHABLE":
        require(exchange and exchange["request"]["method"] == "session/load", "captured_exchange", "REACHABLE requires session/load")
        require(exchange["response"].get("result") == {}, "captured_exchange", "REACHABLE requires empty result")
    elif finding == "UNREACHABLE":
        require(exchange and isinstance(exchange["response"].get("error"), dict), "captured_exchange", "UNREACHABLE requires an error object")
    else:
        require(manifest["indeterminate_reason"] in ALLOWED_INDETERMINATE_REASONS, "indeterminate_reason", "INDETERMINATE without a named reason")


def _verify_isolation(manifest: Mapping[str, Any]) -> None:
    isolation = manifest["isolation"]
    require(isinstance(isolation, Mapping), "isolation", "isolation record is missing")
    finding = manifest["finding"]
    require(
        isolation.get("normal_agent_load_session_advertised") is False,
        "isolation.normal_agent_load_session_advertised",
        "normal capability payload contains loadSession",
    )
    require(
        isolation.get("isolated_probe_load_session_advertised") is True,
        "isolation.isolated_probe_load_session_advertised",
        "isolated probe must advertise loadSession",
    )
    normal = manifest["normal_source"]
    require(isinstance(normal, Mapping), "normal_source", "normal source identities are missing")
    require(
        normal.get("sha256_before") and normal.get("sha256_before") == normal.get("sha256_after"),
        "normal_source",
        "source digest drifted",
    )
    if finding in {"REACHABLE", "UNREACHABLE"}:
        require(isolation.get("cleanup_verified") is True, "isolation.cleanup_verified", "cleanup was not verified")
        require(isolation.get("cleanup_dry_run_verified") is True, "isolation.cleanup_dry_run_verified", "cleanup dry-run not verified")


def _verify_report(report_dir: Path, manifest: Mapping[str, Any]) -> None:
    report_path = report_dir / "report.md"
    require(report_path.is_file(), "report.md", "report is missing")
    text = report_path.read_text(encoding="utf-8")
    finding = str(manifest["finding"])
    require(finding in text, "report.md", "report must state the manifest finding")
    reason = manifest.get("indeterminate_reason")
    if finding == "INDETERMINATE":
        require(isinstance(reason, str) and reason in text, "report.md", "report must name the INDETERMINATE limitation")
        if reason == "INTERNAL_CAPABILITY_UNAVAILABLE":
            require(
                "not a finding about Zed" in text,
                "report.md",
                "normal-agent non-advertisement must not be described as a Zed finding",
            )
            require(
                _ZED_OVERCLAIM.search(text) is None,
                "report.md",
                "normal-agent non-advertisement must not be described as a Zed finding",
            )


def verify_manifest(manifest_path: Path) -> None:
    manifest_path = manifest_path.resolve()
    require(manifest_path.is_file(), "manifest", "manifest path does not exist")
    report_dir = manifest_path.parent
    manifest = _load_manifest(manifest_path)
    for field in REQUIRED_FIELDS:
        require(field in manifest, field, "required field is missing")
    require(manifest.get("schema") == SCHEMA, "schema", "unexpected evidence schema")
    require(manifest.get("origin_a_launches") == 0, "origin_a_launches", "origin-A launches are forbidden")
    require(isinstance(manifest.get("zed"), Mapping) and isinstance(manifest.get("acpx"), Mapping), "zed", "identities are missing")
    require(isinstance(manifest.get("invocation"), Mapping) and manifest["invocation"].get("discovered_from"), "invocation", "current-version invocation provenance is missing")
    require(isinstance(manifest.get("relay"), Mapping), "relay", "relay digests are missing")
    require(manifest["relay"].get("source") == RELAY_EXTRACT_SOURCE, "relay.source", "classification requires a sanitized post-run relay extract")

    excerpt = manifest.get("relay_child_stderr_excerpt")
    if "relay_child_stderr_excerpt" in manifest:
        require(isinstance(excerpt, str), "relay_child_stderr_excerpt", "optional field must be a string")
        require(len(excerpt) <= RELAY_CHILD_STDERR_EXCERPT_LIMIT, "relay_child_stderr_excerpt", "optional field exceeds 4000 characters")

    _scan_credential_like(manifest, field="manifest")
    _verify_files(report_dir, manifest["files"], manifest["relay"])
    _verify_isolation(manifest)
    _verify_finding_rule(manifest)
    _verify_report(report_dir, manifest)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        verify_manifest(args.manifest)
    except VerifyError as exc:
        print(f"{exc.field}: {exc.message}", file=sys.stderr)
        return 1
    except (TypeError, KeyError):
        print("captured_exchange: missing request or response", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
