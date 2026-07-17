#!/usr/bin/env python3
"""Controlled ACP capture entry point for Plan 9.96 evidence.

The capture path is deliberately independent of ``optimus.acp.__main__`` so
it can exercise the launch trust gates before starting the independently
provided ``acpx`` child.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

import keyring

from optimus.acp.launch_approvals import (
    LAUNCH_POLICY_COMPATIBILITY,
    ApprovalError,
    KeyringApprovalStore,
)
from optimus.acp.launch_audit import LaunchAuditError, LaunchAuditEvent, append_launch_audit_event
from optimus.acp.launch_gate import (
    AuthorizedLaunch,
    LaunchGateError,
    authorize_launch,
    resolve_launch_candidate,
)
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.local_infra import _SYSTEM_ENV_KEYS, apply_local_defaults
from optimus.acp.operator_paths import resolve_authorized_operator_paths
from optimus.acp.trusted_paths import (
    TrustedPathError,
    resolve_trusted_operator_roots,
    resolve_workspace_identity,
    revalidate_workspace_identity,
)
from optimus_security.launch_manifest import LaunchManifestError, read_manifest_hmac_key
from optimus_security.sanitization import StreamingTextSanitizer


@dataclass(frozen=True)
class CaptureLaunch:
    """An authorized capture launch that has not yet started a child process."""

    authorized: AuthorizedLaunch
    agent_environ: Mapping[str, str]


@dataclass(frozen=True)
class AuditedLaunch:
    """A capture launch whose required audit event was recorded."""

    capture: CaptureLaunch


_STREAM_READ_SIZE = 8192
_CAPTURE_WAIT_TIMEOUT_SECONDS = 30.0
_SANITIZER_VERSION = "p996-streaming-sanitizer-v1"
_EVIDENCE_MANIFEST_HMAC_DOMAIN = b"p996-evidence-manifest-hmac-v1"
_EVIDENCE_MANIFEST_FILENAME = "sanitizer-manifest.json"
_TRANSCRIPT_ARTIFACTS = ("transcript.stdout", "transcript.stderr")



def authorize_capture(
    *,
    workspace: Path,
    environment: Mapping[str, str],
    keyring_backend: Any | None = None,
    approval_runtime_root: Path | None = None,
    launch_approval_id: str | None = None,
    launch_session_id: str,
    diagnostic_grant_id: str | None = None,
) -> CaptureLaunch:
    """Capture once, resolve, and authorize a controlled ACP capture launch.

    For elevated mode (diagnostic_grant_id is not None), consume the
    diagnostic grant via the committed single-use path, bound to the launch
    session ID. Fail CLOSED on any grant error — unlike the serving process
    (which silently downgrades to ordinary), an evidence harness that claims
    elevated but captured ordinary produces wrong-mode evidence.
    """
    snapshot = LaunchEnvironmentSnapshot.capture(environment)
    workspace_identity = resolve_workspace_identity(workspace)
    operator_paths = resolve_authorized_operator_paths(
        workspace_root=workspace,
        snapshot_values=snapshot.values,
    )
    if keyring_backend is None:
        import keyring as keyring_backend

    if approval_runtime_root is None:
        approval_runtime_root = resolve_trusted_operator_roots(platform_name=sys.platform).approval_runtime_root
    store = KeyringApprovalStore(keyring_backend=keyring_backend, runtime_root=approval_runtime_root)
    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_identity=workspace_identity,
        operator_paths=operator_paths,
        hmac_key=store.hmac_key,
        credential_keyring_backend=keyring_backend,
    )
    authorized = authorize_launch(
        candidate=candidate,
        store=store,
        approval_id=launch_approval_id,
        launch_session_id=launch_session_id,
    )
    if diagnostic_grant_id is not None:
        # Fail CLOSED: an invalid/expired/wrong-session grant must not silently
        # downgrade to ordinary. The serving process (__main__.py) downgrades
        # because ordinary is the safe serving mode; an evidence harness that
        # claims elevated but captured ordinary is wrong-mode evidence.
        try:
            grant = store.consume_diagnostic_grant(diagnostic_grant_id, launch_session_id)
        except ApprovalError as exc:
            raise LaunchGateError(
                code=exc.code,
                detail=exc.detail,
            ) from exc
        from dataclasses import replace
        authorized = replace(authorized, diagnostic_grant=grant)
    agent_environ = apply_local_defaults(
        authorized.candidate.agent_environ,
        config_root=authorized.candidate.operator_paths.config_root,
        resolved_shared_secret=authorized.candidate.shared_secret,
    )
    return CaptureLaunch(authorized=authorized, agent_environ=agent_environ)


def append_authorized_audit(capture: CaptureLaunch) -> AuditedLaunch:
    """Append the value-safe launch audit event before child startup."""
    authorized = capture.authorized
    candidate = authorized.candidate
    setting_decisions = tuple(
        {
            "name": row.name,
            "tier": row.tier.value,
            "source_class": row.source_class,
            "decision": row.decision,
        }
        for row in candidate.display_rows
    )
    event = LaunchAuditEvent(
        timestamp=datetime.now(timezone.utc),
        workspace_digest=candidate.workspace_identity.digest,
        launch_session_id=authorized.launch_session_id,
        approval_id=authorized.approval_id,
        approval_mode=authorized.approval_mode,
        registry_version=LAUNCH_POLICY_COMPATIBILITY,
        policy_version=LAUNCH_POLICY_COMPATIBILITY,
        setting_decisions=setting_decisions,
        monotonic_dispositions=tuple(
            {"name": name, "disposition": "recorded"} for name in sorted(candidate.monotonic_grants)
        ),
        rejected_names=(),
        child_propagation_decisions={
            "agent_child": tuple(sorted(capture.agent_environ)),
            "gateway_child": tuple(sorted(candidate.gateway_environ)),
        },
        diagnostic_grant_state="none" if authorized.diagnostic_grant is None else "granted",
        sanitizer_rule_counts={},
        final_reason_code="AUTHORIZED",
    )
    append_launch_audit_event(event, runtime_root=candidate.operator_paths.runtime_root)
    return AuditedLaunch(capture=capture)


def spawn_authorized_capture(audited: AuditedLaunch, *, command: Sequence[str]) -> subprocess.Popen[str]:
    """Revalidate the workspace and start the authorized capture child."""
    if not command:
        raise ValueError("capture command must not be empty")
    capture = audited.capture
    candidate = capture.authorized.candidate
    revalidate_workspace_identity(candidate.workspace_identity)
    # Merge the same system-env allowlist the committed Task 5 launcher uses
    # (local_infra._SYSTEM_ENV_KEYS), sourced from the gate's sanctioned
    # one-time snapshot (candidate.inherited.values) — never an ambient
    # os.environ read. Without PATH/SYSTEMROOT/COMSPEC a real Windows child
    # cannot start; the registry-authorized OPTIMUS_* set plus this allowlist
    # is what "children contain exactly registry-authorized names" means in
    # practice (Task 5 precedent, already reviewer-approved).
    child_env = dict(capture.agent_environ)
    for key in _SYSTEM_ENV_KEYS:
        value = candidate.inherited.values.get(key, "")
        if value:
            child_env[key] = value
    return subprocess.Popen(
        list(command),
        cwd=candidate.workspace_identity.canonical_path,
        env=child_env,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def capture_acpx(
    *,
    workspace: Path,
    environment: Mapping[str, str],
    keyring_backend: Any | None = None,
    approval_runtime_root: Path | None = None,
    launch_approval_id: str | None = None,
    launch_session_id: str,
    command: Sequence[str],
    diagnostic_grant_id: str | None = None,
) -> subprocess.Popen[str]:
    """Run the complete authorization, audit, revalidation, and spawn walk."""
    capture = authorize_capture(
        workspace=workspace,
        environment=environment,
        keyring_backend=keyring_backend,
        approval_runtime_root=approval_runtime_root,
        launch_approval_id=launch_approval_id,
        launch_session_id=launch_session_id,
        diagnostic_grant_id=diagnostic_grant_id,
    )
    audited = append_authorized_audit(capture)
    return spawn_authorized_capture(audited, command=command)


def _known_secrets(capture: CaptureLaunch) -> tuple[str, ...]:
    candidate = capture.authorized.candidate
    secrets: list[str] = []
    # Env-sourced SECRET-tier values from the projected child environments —
    # the child sees these and could echo them. Uses the projected env (not
    # inherited.values) because the projection is what the child actually
    # receives, and it is the gate's sanctioned one-time snapshot.
    for name in candidate.secret_inventory:
        if name in candidate.agent_environ:
            secrets.append(candidate.agent_environ[name])
        if name in candidate.gateway_environ:
            secrets.append(candidate.gateway_environ[name])
    # Resolved provider API key and shared secret may come from .env.gateway or
    # keyring, NOT the inherited env scan, so they are absent from
    # secret_inventory when sourced from keyring (Task 9's real configuration:
    # credentials in Windows Credential Manager, no .env). apply_local_defaults
    # projects the shared secret into the child's OPTIMUS_API_KEY; the provider
    # key is projected into the gateway child env. Both must be folded in or an
    # acpx echo of OPTIMUS_API_KEY goes raw to disk — Task 8's purpose defeated
    # in precisely the configuration Task 9 runs.
    if (
        candidate.provider_credentials is not None
        and candidate.provider_credentials.secrets is not None
    ):
        secrets.append(candidate.provider_credentials.secrets.model_provider_api_key)
    if candidate.shared_secret:
        secrets.append(candidate.shared_secret)
    return tuple(secrets)


def _stream_sanitized(
    source: TextIO, destination: Path, *, known_secrets: tuple[str, ...]
) -> Mapping[str, int]:
    """Stream-sanitize source to destination. Returns the sanitizer's rule
    counts (content-free metadata for the evidence manifest)."""
    sanitizer = StreamingTextSanitizer(known_secrets=known_secrets)
    with destination.open("w", encoding="utf-8") as stream:
        while chunk := source.read(_STREAM_READ_SIZE):
            stream.write(sanitizer.feed(chunk))
        stream.write(sanitizer.finalize())
    return dict(sanitizer.rule_counts)


@dataclass(frozen=True)
class CaptureResult:
    """Result of a capture: child exit code and aggregated sanitizer rule counts."""

    exit_code: int
    rule_counts: Mapping[str, int]


def _capture_to_disk(
    audited: AuditedLaunch, *, command: Sequence[str], output_dir: Path
) -> CaptureResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    process = spawn_authorized_capture(audited, command=command)
    assert process.stdout is not None
    assert process.stderr is not None
    secrets = _known_secrets(audited.capture)
    rule_counts: dict[str, int] = {}
    counts_lock = threading.Lock()

    def _merge_counts(counts: Mapping[str, int]) -> None:
        with counts_lock:
            for name, count in counts.items():
                rule_counts[name] = rule_counts.get(name, 0) + count

    workers = [
        threading.Thread(
            target=lambda: _merge_counts(
                _stream_sanitized(process.stdout, output_dir / "transcript.stdout", known_secrets=secrets)
            ),
        ),
        threading.Thread(
            target=lambda: _merge_counts(
                _stream_sanitized(process.stderr, output_dir / "transcript.stderr", known_secrets=secrets)
            ),
        ),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    try:
        exit_code = process.wait(timeout=_CAPTURE_WAIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        exit_code = process.returncode or 1
    return CaptureResult(exit_code=exit_code, rule_counts=dict(rule_counts))


def _compute_artifact_sha256(path: Path) -> str:
    """SHA-256 hex digest of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _extract_decoded_strings(content: str) -> list[str]:
    """Extract every string value from JSON lines in the transcript.

    Plan 9.96 Task 8 Step 3 requires scanning **decoded** transcript records,
    not just raw text. A secret inside a JSON string can be unicode-escaped
    (e.g. ``\u0068unter2``) and evade a raw-text scan entirely. This function
    parses each line as JSON and recursively extracts every string value,
    so the joined scan can catch what the raw-text layer misses.
    """
    decoded: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            continue
        _collect_strings(obj, decoded)
    return decoded


def _extract_decoded_strings_by_path(content: str) -> dict[str, list[str]]:
    """Extract decoded string values grouped by their JSON key path.

    Plan 9.96 Task 8 Step 3 requires "**join** decoded transcript records."
    The join is per-path: streamed deltas always recur at the same key path
    (e.g. ``update.content.text``), so concatenating values at each path in
    document order reconstructs the stream exactly. Structural fields like
    ``method`` or ``sessionUpdate`` join only with themselves (harmless).
    This is fully general — no protocol-specific path assumptions, no
    fallback branch.

    Returns a dict mapping dotted key paths to lists of string values at
    that path, in document order.
    """
    by_path: dict[str, list[str]] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            continue
        _collect_strings_by_path(obj, (), by_path)
    return by_path


def _collect_strings_by_path(
    obj: object, path: tuple[str, ...], out: dict[str, list[str]]
) -> None:
    """Recursively collect string values with their key path (dict keys only,
    array indices ignored)."""
    if isinstance(obj, str):
        key = ".".join(path) if path else "<root>"
        out.setdefault(key, []).append(obj)
    elif isinstance(obj, dict):
        for key, value in obj.items():
            _collect_strings_by_path(value, path + (key,), out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _collect_strings_by_path(item, path, out)


def _collect_strings(obj: object, out: list[str]) -> None:
    """Recursively collect every string value from a parsed JSON object."""
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            _collect_strings(value, out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _collect_strings(item, out)


def _scan_content_for_secrets(
    content: str,
    known_secrets: tuple[str, ...],
    *,
    artifact_name: str,
    secret_start_index: int = 0,
) -> list[str]:
    """Scan raw text AND decoded JSON strings for known secrets and patterns.

    Two layers:
    1. Raw-text scan: exact secret match + bearer/assignment patterns.
    2. Decoded-JSON scan: parse each JSON line, extract string values, and
       scan the decoded values. Catches unicode-escaped secrets that evade
       the raw-text layer.
    """
    rules_fired: list[str] = []

    # Layer 1: raw-text scan.
    for i, secret in enumerate(known_secrets):
        if secret and secret in content:
            rules_fired.append(f"exact_secret_leak:artifact={artifact_name}:index={secret_start_index + i}")
    if _BEARER_PATTERN.search(content):
        rules_fired.append(f"bearer_token_pattern:artifact={artifact_name}")
    if _SECRET_ASSIGNMENT_PATTERN.search(content):
        rules_fired.append(f"secret_assignment_pattern:artifact={artifact_name}")

    # Layer 2: decoded-JSON scan (per-string).
    decoded_strings = _extract_decoded_strings(content)
    for i, secret in enumerate(known_secrets):
        if secret:
            for decoded in decoded_strings:
                if secret in decoded:
                    rules_fired.append(f"decoded_secret_leak:artifact={artifact_name}:index={secret_start_index + i}")
                    break
    for decoded in decoded_strings:
        if _BEARER_PATTERN.search(decoded):
            rules_fired.append(f"decoded_bearer_token_pattern:artifact={artifact_name}")
            break
    for decoded in decoded_strings:
        if _SECRET_ASSIGNMENT_PATTERN.search(decoded):
            rules_fired.append(f"decoded_secret_assignment_pattern:artifact={artifact_name}")
            break

    # Layer 3: joined-decoded-strings scan (per JSON path). For each key path,
    # concatenate all string values at that path in document order with NO
    # separator (delta-faithful — ACP sessions stream agent text as chunked
    # deltas across records at the same path, e.g. ``update.content.text``;
    # deltas concatenate directly; a newline join would re-split the secret at
    # the boundary). This catches secrets split across record boundaries that
    # neither the raw-text scan (layer 1) nor the per-string decoded scan
    # (layer 2) can catch. The frozen plan says "**join** decoded transcript
    # records" — the join is the entire point.
    #
    # Per-path grouping (not all-strings join) so structural fields like
    # ``method`` don't interleave between content halves. Fully general — no
    # protocol-specific path assumptions.
    #
    # False-positive risk of coincidental concatenations is accepted — this is
    # a fail-closed evidence gate, and quarantine-and-investigate is the
    # correct outcome.
    strings_by_path = _extract_decoded_strings_by_path(content)
    for _path, values in strings_by_path.items():
        joined_decoded = "".join(values)
        for i, secret in enumerate(known_secrets):
            if secret and secret in joined_decoded:
                rules_fired.append(f"joined_decoded_secret_leak:artifact={artifact_name}:index={secret_start_index + i}")
        if _BEARER_PATTERN.search(joined_decoded):
            rules_fired.append(f"joined_decoded_bearer_token_pattern:artifact={artifact_name}")
        if _SECRET_ASSIGNMENT_PATTERN.search(joined_decoded):
            rules_fired.append(f"joined_decoded_secret_assignment_pattern:artifact={artifact_name}")

    return rules_fired


def _joined_scan(artifact_dir: Path, known_secrets: tuple[str, ...]) -> dict[str, object]:
    """Join decoded transcript records and scan for exact known secret values
    plus canaries/patterns. Runs while current secrets are still in memory.

    Scans both raw text and decoded JSON string values (a secret inside a JSON
    string can be unicode-escaped and evade a raw-text scan).

    Returns a result dict with:
    - hit: bool (True if any secret/canary found in sanitized output)
    - rules_fired: list of rule identifiers that triggered (content-free)
    - scanned_artifacts: list of artifact filenames scanned
    """
    rules_fired: list[str] = []
    scanned: list[str] = []

    for name in _TRANSCRIPT_ARTIFACTS:
        path = artifact_dir / name
        if not path.is_file():
            continue
        scanned.append(name)
        content = path.read_text(encoding="utf-8")
        rules_fired.extend(
            _scan_content_for_secrets(content, known_secrets, artifact_name=name)
        )

    return {
        "hit": len(rules_fired) > 0,
        "rules_fired": rules_fired,
        "scanned_artifacts": scanned,
    }


_BEARER_PATTERN = re.compile(r"(?i)(authorization:\s*bearer\s+|bearer\s+)\S+")
_SECRET_ASSIGNMENT_PATTERN = re.compile(r"(?i)\b(token|password|secret|credential|api[_-]?key)((?:=|:)\s*)\S+")


def _compute_evidence_manifest_hmac(fields: dict[str, object], hmac_key: bytes) -> str:
    """Domain-separated HMAC-SHA-256 over the manifest fields (excluding the
    hmac field itself). Uses a distinct domain prefix from approval-record,
    grant, and gateway-child-manifest HMACs so cross-type collisions are
    impossible."""
    signed_fields = {k: v for k, v in fields.items() if k != "hmac"}
    canonical = json.dumps(signed_fields, sort_keys=True, separators=(",", ":"))
    msg = _EVIDENCE_MANIFEST_HMAC_DOMAIN + b"\x00" + canonical.encode("utf-8")
    return hmac.new(hmac_key, msg, hashlib.sha256).hexdigest()


def _write_evidence_manifest(
    output_dir: Path,
    *,
    rule_counts: Mapping[str, int],
    joined_scan_result: dict[str, object],
    hmac_key: bytes,
) -> Path:
    """Write the compact evidence manifest with HMAC. Never includes secret
    material — only SHA-256 digests, rule counts, scan result, and HMAC."""
    artifact_sha256s: dict[str, str] = {}
    for name in _TRANSCRIPT_ARTIFACTS:
        path = output_dir / name
        if path.is_file():
            artifact_sha256s[name] = _compute_artifact_sha256(path)

    manifest_fields: dict[str, object] = {
        "sanitizer_version": _SANITIZER_VERSION,
        "rule_counts": dict(rule_counts),
        "artifact_sha256": artifact_sha256s,
        "joined_scan": joined_scan_result,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_fields["hmac"] = _compute_evidence_manifest_hmac(manifest_fields, hmac_key)

    manifest_path = output_dir / _EVIDENCE_MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest_fields, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest_path


def _verify_evidence_manifest(
    manifest_path: Path,
    *,
    artifact_dir: Path,
    keyring_backend: Any | None = None,
) -> int:
    """Verify an evidence manifest: load HMAC key via read_manifest_hmac_key,
    verify the manifest HMAC, then re-check artifact/manifest digests, JSON
    strings, canaries, patterns, and the recorded promotion decision.

    A hit quarantines the artifact and exits nonzero.
    """
    if keyring_backend is None:
        import keyring as keyring_backend

    try:
        hmac_key = read_manifest_hmac_key(keyring_backend)
    except LaunchManifestError as exc:
        print(f"optimus-agent: {exc.code}: cannot read manifest HMAC key", file=sys.stderr)
        return 2

    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)

    # 1. Verify HMAC before trusting anything in the manifest.
    expected_hmac = _compute_evidence_manifest_hmac(manifest, hmac_key)
    actual_hmac = manifest.get("hmac", "")
    if not hmac.compare_digest(expected_hmac, actual_hmac):
        print("optimus-agent: EVIDENCE_HMAC_MISMATCH: manifest HMAC verification failed", file=sys.stderr)
        _quarantine_artifacts(artifact_dir)
        return 1

    # 2. Re-check artifact SHA-256 digests.
    artifact_sha256s = manifest.get("artifact_sha256", {})
    for name, expected_digest in artifact_sha256s.items():
        path = artifact_dir / name
        if not path.is_file():
            print(f"optimus-agent: EVIDENCE_ARTIFACT_MISSING: {name}", file=sys.stderr)
            _quarantine_artifacts(artifact_dir)
            return 1
        actual_digest = _compute_artifact_sha256(path)
        if actual_digest != expected_digest:
            print(f"optimus-agent: EVIDENCE_DIGEST_MISMATCH: {name}", file=sys.stderr)
            _quarantine_artifacts(artifact_dir)
            return 1

    # 3. Re-run joined scan for patterns (without known secrets — verify mode
    # does not have them; it checks that no bearer/secret-assignment patterns
    # survived sanitization). Scans both raw text AND decoded JSON strings.
    for name in _TRANSCRIPT_ARTIFACTS:
        path = artifact_dir / name
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        pattern_hits = _scan_content_for_secrets(content, (), artifact_name=name)
        if pattern_hits:
            print(f"optimus-agent: EVIDENCE_PATTERN_HIT: {name}", file=sys.stderr)
            _quarantine_artifacts(artifact_dir)
            return 1

    # 4. Check the recorded joined-scan result.
    recorded_scan = manifest.get("joined_scan", {})
    if recorded_scan.get("hit"):
        print("optimus-agent: EVIDENCE_SCAN_HIT: recorded joined-scan reported a hit", file=sys.stderr)
        _quarantine_artifacts(artifact_dir)
        return 1

    print("optimus-agent: evidence manifest verified", file=sys.stderr)
    return 0


def _quarantine_artifacts(artifact_dir: Path) -> None:
    """Move artifacts outside the promotable set on a verification hit."""
    quarantine = artifact_dir / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    for name in _TRANSCRIPT_ARTIFACTS + (_EVIDENCE_MANIFEST_FILENAME,):
        path = artifact_dir / name
        if path.is_file():
            path.rename(quarantine / name)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    capture_parser = subcommands.add_parser("capture")
    capture_parser.add_argument("--workspace", type=Path, required=True)
    capture_parser.add_argument("--output-dir", type=Path, required=True)
    capture_parser.add_argument("--mode", choices=("ordinary", "elevated"), required=True)
    capture_parser.add_argument("--agent-approval-id")
    capture_parser.add_argument("--launch-session-id")
    capture_parser.add_argument("--diagnostic-grant-id")
    verify_parser = subcommands.add_parser("verify")
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args(argv)


_LEGACY_LOCATOR_PATTERNS = (
    "run_plan987",
    "run_plan988",
    "plan-9-87",
    "plan-9-88",
)

# The frozen helpers (run_plan987:1231, run_plan988:971) write their raw
# transcript to ``<workspace>/attempt-{N}-transcript.jsonl``. This filename
# contains none of the substring patterns above, so it needs its own regex.
# Precise enough to never match the 9.96 tool's own artifacts
# (transcript.stdout, transcript.stderr, sanitizer-manifest.json).
_LEGACY_RAW_TRANSCRIPT_RE = re.compile(r"attempt-\d+-transcript\.jsonl")


def _is_legacy_locator(path: Path) -> str | None:
    """Check if a path contains a Plan 9.87/9.88 legacy locator pattern.
    Returns the matched pattern if found, None otherwise."""
    path_str = str(path).lower().replace("\\", "/")
    for pattern in _LEGACY_LOCATOR_PATTERNS:
        if pattern in path_str:
            return pattern
    if _LEGACY_RAW_TRANSCRIPT_RE.search(path_str):
        return "attempt-transcript-jsonl"
    return None


def _reject_legacy_locator(path: Path, *, kind: str) -> int:
    """Reject a Plan 9.87/9.88 legacy locator as Plan 9.96 evidence."""
    matched = _is_legacy_locator(path)
    if matched is not None:
        print(
            f"optimus-agent: rejecting Plan 9.87/9.88 legacy locator ({matched}) "
            f"as Plan 9.96 evidence ({kind}). Use the controlled capture command: "
            "tools/run_plan996_acpx_security_evidence.py capture",
            file=sys.stderr,
        )
        return 2
    return -1


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "verify":
        # Step 4: reject Plan 9.87/9.88 legacy locators before verification.
        for path in (args.manifest, args.artifact_dir):
            result = _reject_legacy_locator(path, kind="verify")
            if result != -1:
                return result
        return _verify_evidence_manifest(args.manifest, artifact_dir=args.artifact_dir)

    # Step 4: reject Plan 9.87/9.88 legacy locators in capture output-dir.
    result = _reject_legacy_locator(args.output_dir, kind="capture")
    if result != -1:
        return result

    acpx = shutil.which("acpx")
    if acpx is None:
        print("acpx is required for controlled Plan 9.96 capture", file=sys.stderr)
        return 2
    # Enforce mode⇔grant coupling BEFORE authorization: an evidence artifact
    # that claims elevated but captured ordinary (or vice versa) is wrong-mode
    # evidence. --mode elevated requires --diagnostic-grant-id; --mode ordinary
    # rejects it (must not burn a single-use grant on an ordinary capture).
    if args.mode == "elevated" and args.diagnostic_grant_id is None:
        print(
            "optimus-agent: --mode elevated requires --diagnostic-grant-id "
            "(author one with optimus-trust run --elevated-debug)",
            file=sys.stderr,
        )
        return 2
    if args.mode == "ordinary" and args.diagnostic_grant_id is not None:
        print(
            "optimus-agent: --mode ordinary must not be combined with --diagnostic-grant-id",
            file=sys.stderr,
        )
        return 2
    launch_session_id = args.launch_session_id or f"sess_{secrets.token_hex(12)}"
    try:
        capture = authorize_capture(
            workspace=args.workspace,
            environment=os.environ,
            launch_approval_id=args.agent_approval_id,
            launch_session_id=launch_session_id,
            diagnostic_grant_id=args.diagnostic_grant_id,
        )
        audited = append_authorized_audit(capture)
        # The gated smoke command is ``acpx --version``: it exits cleanly, ignores
        # stdin, and produces capturable output. Bare ``acpx`` reads a prompt from
        # stdin and would hang (reviewer-proven empirically). The provenance
        # version string is recorded from the gated child's sanitized transcript.
        # _capture_to_disk is INSIDE the try because spawn_authorized_capture
        # calls revalidate_workspace_identity at spawn time — the one TOCTOU
        # vector (workspace relocated between authorize and spawn). Without this,
        # a workspace relocation would propagate as an uncaught traceback with
        # exit 1, same defect class as the NO_APPROVAL gap fixed in FIX 5.
        result = _capture_to_disk(audited, command=[acpx, "--version"], output_dir=args.output_dir)
        # Joined promotion scan: while current secrets are still in memory,
        # join decoded transcript records and scan for exact known values plus
        # canaries/patterns. A hit quarantines the artifact.
        known = _known_secrets(capture)
        scan_result = _joined_scan(args.output_dir, known)
        if scan_result["hit"]:
            print(
                "optimus-agent: EVIDENCE_SCAN_HIT: joined scan found secret material in sanitized output",
                file=sys.stderr,
            )
            _quarantine_artifacts(args.output_dir)
            return 1
        # Write the HMAC-signed evidence manifest. The HMAC key comes from the
        # same approval-store keyring namespace (read_manifest_hmac_key), domain-
        # separated so it can never be reused as an approval-record or grant HMAC.
        approval_runtime_root = resolve_trusted_operator_roots(platform_name=sys.platform).approval_runtime_root
        manifest_store = KeyringApprovalStore(
            keyring_backend=keyring,
            runtime_root=approval_runtime_root,
        )
        _write_evidence_manifest(
            args.output_dir,
            rule_counts=result.rule_counts,
            joined_scan_result=scan_result,
            hmac_key=manifest_store.hmac_key,
        )
    except LaunchGateError as exc:
        if exc.code == "NO_APPROVAL":
            print(
                "optimus-agent: no launch approval found for this workspace. Review the effective "
                "configuration and author one with:\n"
                f"  optimus-trust --workspace-root {args.workspace} approve --mode durable",
                file=sys.stderr,
            )
        elif exc.code == "SNAPSHOT_MISMATCH":
            print(
                "optimus-agent: effective configuration changed since the last approval. Review the new "
                "configuration and re-approve with:\n"
                f"  optimus-trust --workspace-root {args.workspace} approve --mode durable",
                file=sys.stderr,
            )
        else:
            print(f"optimus-agent: {exc.code}" + (f": {exc.detail}" if exc.detail else ""), file=sys.stderr)
        return 2
    except LaunchAuditError as exc:
        print(f"optimus-agent: {exc.code}: audit could not be recorded; capture stopped.", file=sys.stderr)
        return 2
    except TrustedPathError as exc:
        print(f"optimus-agent: {exc}", file=sys.stderr)
        return 2
    transcript = args.output_dir / "transcript.stdout"
    if transcript.is_file():
        version = transcript.read_text(encoding="utf-8").strip()
        if version:
            print(f"acpx provenance: {version}", file=sys.stderr)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
