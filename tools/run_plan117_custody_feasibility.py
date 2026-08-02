"""Plan 11.7 custody feasibility phase orchestration runner.

Observes files and processes; prints operator instructions. Never sends ACP
bytes, UI input, clipboard content, URI launches, or client requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.plan117_custody_contract import (  # noqa: E402
    SCHEMA_APPROVAL_EQUIVALENCE,
    SCHEMA_ATTEMPT_MANIFEST,
    SCHEMA_CUSTODY_STATE,
    SCHEMA_PROCESS_RECORD,
    SCHEMA_SETTINGS_TRANSACTION,
    SCHEMA_TRANSCRIPT_PROJECTION,
    AttemptKind,
    CustodyContractError,
    FailureClass,
    atomic_write_bytes,
    atomic_write_json,
    sha256_file,
    write_canonical_json,
)

PHASES = (
    "direct-control",
    "relay-control",
    "origin-a",
    "restart-b",
    "fresh-control-c",
    "direct-ancestry-control",
    "restore-settings",
    "finalize",
)

PHASE_PREREQUISITES: dict[str, tuple[str, ...]] = {
    "direct-control": (),
    "relay-control": ("direct-control",),
    "origin-a": ("direct-control", "relay-control"),
    "restart-b": ("direct-control", "relay-control", "origin-a"),
    "fresh-control-c": ("direct-control", "relay-control", "origin-a", "restart-b"),
    "direct-ancestry-control": (
        "direct-control",
        "relay-control",
        "origin-a",
        "restart-b",
        "fresh-control-c",
    ),
    "restore-settings": (),
    "finalize": (),
}

PROMPT_FIXTURE_TEXT = (
    "Read README.md and answer with one sentence naming this project. Do not modify files.\n"
)
PROMPT_FIXTURE_SHA256 = (
    "8EEA4738E72159A863FEA22A542F92D6A99E3681803BA21863F734C577480D82"
)
PROMPT_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "evidence" / "plan117-server-custody-prompt.txt"

SETTINGS_TX_META = "settings-transaction.json"
SETTINGS_PREIMAGE = "settings-preimage.bin"
STATE_FILENAME = "plan117-custody-state.json"
CHANGED_KEY_ALLOWLIST = frozenset(
    {
        "agent_servers.optimus.command",
        "agent_servers.optimus.args",
    }
)

ProcessQuery = Callable[..., list[dict[str, Any]]]
SubprocessRun = Callable[..., subprocess.CompletedProcess[str]]


class CustodyRunnerError(CustodyContractError):
    """Fail-closed runner error with a stable reason code."""


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_regular_non_symlink(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise CustodyRunnerError("symlink_forbidden", label)
    return path


def resolve_probe_paths(
    *,
    workspace_root: Path,
    capture_root: Path,
    zed_executable: Path,
    zed_source: Path,
    settings_path: Path,
    debug_log: Path,
    custody_root: Path,
    allowed_settings_roots: Sequence[Path],
) -> dict[str, Path]:
    paths = {
        "workspace_root": workspace_root,
        "capture_root": capture_root,
        "zed_executable": zed_executable,
        "zed_source": zed_source,
        "settings_path": settings_path,
        "debug_log": debug_log,
        "custody_root": custody_root,
    }
    for label, value in paths.items():
        if not value.is_absolute():
            raise CustodyRunnerError("path_not_absolute", label)
        resolved = value.resolve()
        if resolved.is_symlink():
            raise CustodyRunnerError("symlink_forbidden", label)
        paths[label] = resolved

    settings = paths["settings_path"]
    approved = False
    for root in allowed_settings_roots:
        root_resolved = root.resolve()
        try:
            settings.relative_to(root_resolved)
            approved = True
            break
        except ValueError:
            try:
                settings.parent.relative_to(root_resolved)
                approved = True
                break
            except ValueError:
                continue
    if not approved:
        raise CustodyRunnerError("settings_path_unapproved", "settings_path")
    if settings.exists():
        require_regular_non_symlink(settings, label="settings_path")
    return paths


def require_readme_precondition(workspace_root: Path) -> Path:
    readme = (workspace_root / "README.md").resolve()
    try:
        readme.relative_to(workspace_root.resolve())
    except ValueError as exc:
        raise CustodyRunnerError("readme_outside_workspace", "readme") from exc
    if readme.is_symlink() or not readme.is_file():
        raise CustodyRunnerError("readme_precondition_failed", "readme")
    return readme


def _validate_settings_approval(
    approval: Mapping[str, Any] | None,
    *,
    settings_path: Path,
    pre_image_sha256: str | None,
) -> Mapping[str, Any]:
    if approval is None:
        raise CustodyRunnerError("settings_mutation_approval_required", "approval")
    required = ("settings_path", "pre_image_sha256", "operator_identity", "approved_at_utc")
    for key in required:
        if key not in approval:
            raise CustodyRunnerError("settings_mutation_approval_incomplete", key)
    if Path(str(approval["settings_path"])).resolve() != settings_path.resolve():
        raise CustodyRunnerError("settings_mutation_approval_path_mismatch", "settings_path")
    approved_digest = approval["pre_image_sha256"]
    if approved_digest != pre_image_sha256:
        raise CustodyRunnerError("settings_mutation_approval_digest_mismatch", "pre_image_sha256")
    if not str(approval["operator_identity"]).strip():
        raise CustodyRunnerError("settings_mutation_approval_incomplete", "operator_identity")
    if not str(approval["approved_at_utc"]).strip():
        raise CustodyRunnerError("settings_mutation_approval_incomplete", "approved_at_utc")
    return approval


def _settings_tx_paths(custody_root: Path) -> tuple[Path, Path]:
    return custody_root / SETTINGS_TX_META, custody_root / SETTINGS_PREIMAGE


def _load_settings_json(settings_path: Path) -> dict[str, Any]:
    if not settings_path.exists():
        return {}
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CustodyRunnerError("settings_json_invalid", "settings_path") from exc
    if not isinstance(payload, dict):
        raise CustodyRunnerError("settings_json_invalid", "settings_path")
    return payload


def _atomic_replace_settings(settings_path: Path, data: bytes) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = settings_path.with_name(f"{settings_path.name}.partial-{uuid.uuid4().hex}")
    try:
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, settings_path)
    except OSError as exc:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        raise CustodyRunnerError("settings_atomic_replace_failed", "settings_path") from exc


def mutate_settings_insert_relay(
    *,
    settings_path: Path,
    custody_root: Path,
    relay_command: str,
    relay_args: Sequence[str],
    approval: Mapping[str, Any] | None,
    agent_server_name: str = "optimus",
    create_if_absent: bool = False,
) -> dict[str, Any]:
    settings_path = settings_path.resolve()
    custody_root = custody_root.resolve()
    if settings_path.is_symlink():
        raise CustodyRunnerError("symlink_forbidden", "settings_path")

    existed = settings_path.is_file()
    if not existed and not create_if_absent:
        raise CustodyRunnerError("settings_absent", "settings_path")
    pre_bytes = settings_path.read_bytes() if existed else None
    pre_digest = _digest_bytes(pre_bytes) if pre_bytes is not None else None
    _validate_settings_approval(
        approval, settings_path=settings_path, pre_image_sha256=pre_digest
    )

    payload = _load_settings_json(settings_path) if existed else {}
    servers = payload.setdefault("agent_servers", {})
    if not isinstance(servers, dict):
        raise CustodyRunnerError("settings_agent_servers_invalid", "agent_servers")
    entry = servers.get(agent_server_name)
    if not isinstance(entry, dict):
        entry = {}
        servers[agent_server_name] = entry
    if agent_server_name != "optimus":
        raise CustodyRunnerError("settings_agent_server_not_allowlisted", agent_server_name)
    entry["command"] = relay_command
    entry["args"] = list(relay_args)
    changed = [
        f"agent_servers.{agent_server_name}.command",
        f"agent_servers.{agent_server_name}.args",
    ]
    for key in changed:
        if key not in CHANGED_KEY_ALLOWLIST:
            raise CustodyRunnerError("settings_changed_key_not_allowlisted", key)

    mutated_text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    mutated_bytes = mutated_text.encode("utf-8")
    mutated_digest = _digest_bytes(mutated_bytes)

    meta_path, preimage_path = _settings_tx_paths(custody_root)
    if pre_bytes is not None:
        atomic_write_bytes(preimage_path, pre_bytes)
    elif preimage_path.exists():
        preimage_path.unlink()

    proof = {
        "schema": SCHEMA_SETTINGS_TRANSACTION,
        "settings_path": str(settings_path),
        "pre_image_existed": existed,
        "pre_image_sha256": pre_digest,
        "mutated_sha256": mutated_digest,
        "final_sha256": None,
        "final_existed": None,
        "changed_key_paths": changed,
        "restored": False,
        "approval": {
            "operator_identity": approval["operator_identity"],  # type: ignore[index]
            "approved_at_utc": approval["approved_at_utc"],  # type: ignore[index]
        },
    }
    atomic_write_json(meta_path, proof)
    _atomic_replace_settings(settings_path, mutated_bytes)
    return proof


def restore_settings(
    *,
    settings_path: Path,
    custody_root: Path,
    expected_mutated_sha256: str,
) -> dict[str, Any]:
    settings_path = settings_path.resolve()
    custody_root = custody_root.resolve()
    meta_path, preimage_path = _settings_tx_paths(custody_root)
    if not meta_path.is_file():
        raise CustodyRunnerError("settings_transaction_missing", "settings_transaction")
    proof = json.loads(meta_path.read_text(encoding="utf-8"))
    if proof.get("restored") is True:
        return {
            "restored": True,
            "already_restored": True,
            "final_existed": proof.get("final_existed"),
            "final_sha256": proof.get("final_sha256"),
        }

    current_exists = settings_path.is_file()
    current_digest = sha256_file(settings_path) if current_exists else None
    pre_existed = bool(proof.get("pre_image_existed"))
    pre_digest = proof.get("pre_image_sha256")

    if pre_existed and current_exists and current_digest == pre_digest:
        proof["restored"] = True
        proof["final_existed"] = True
        proof["final_sha256"] = current_digest
        atomic_write_json(meta_path, proof)
        return {
            "restored": True,
            "already_restored": True,
            "final_existed": True,
            "final_sha256": current_digest,
        }
    if not pre_existed and not current_exists:
        proof["restored"] = True
        proof["final_existed"] = False
        proof["final_sha256"] = None
        atomic_write_json(meta_path, proof)
        return {
            "restored": True,
            "already_restored": True,
            "final_existed": False,
            "final_sha256": None,
        }

    if Path(str(proof.get("settings_path", ""))).resolve() != settings_path:
        raise CustodyRunnerError("settings_path_mismatch", "settings_path")
    if current_digest != expected_mutated_sha256:
        raise CustodyRunnerError("settings_mutated_digest_mismatch", "settings_path")

    if pre_existed:
        if not preimage_path.is_file():
            raise CustodyRunnerError("settings_preimage_missing", "preimage")
        pre_bytes = preimage_path.read_bytes()
        if _digest_bytes(pre_bytes) != pre_digest:
            raise CustodyRunnerError("settings_preimage_digest_mismatch", "preimage")
        _atomic_replace_settings(settings_path, pre_bytes)
        final_existed = True
        final_digest = _digest_bytes(pre_bytes)
    else:
        settings_path.unlink()
        final_existed = False
        final_digest = None

    proof["restored"] = True
    proof["final_existed"] = final_existed
    proof["final_sha256"] = final_digest
    atomic_write_json(meta_path, proof)
    return {
        "restored": True,
        "already_restored": False,
        "final_existed": final_existed,
        "final_sha256": final_digest,
    }


def run_with_settings_transaction(
    *,
    settings_path: Path,
    custody_root: Path,
    relay_command: str,
    relay_args: Sequence[str],
    approval: Mapping[str, Any] | None,
    agent_server_name: str = "optimus",
    create_if_absent: bool = False,
    body: Callable[[], Any],
) -> Any:
    proof = mutate_settings_insert_relay(
        settings_path=settings_path,
        custody_root=custody_root,
        relay_command=relay_command,
        relay_args=relay_args,
        approval=approval,
        agent_server_name=agent_server_name,
        create_if_absent=create_if_absent,
    )
    try:
        return body()
    finally:
        restore_settings(
            settings_path=settings_path,
            custody_root=custody_root,
            expected_mutated_sha256=proof["mutated_sha256"],
        )


def _default_state() -> dict[str, Any]:
    return {
        "schema": SCHEMA_CUSTODY_STATE,
        "completed_phases": [],
        "active_settings_transaction": None,
        "run_ids": {"a": None, "b": None, "c": None},
        "next_ordinal": {
            AttemptKind.CORRELATION_CAPTURE.value: 1,
            AttemptKind.POST_NEW_PROMPT.value: 1,
        },
        "attempt_locators": {},
        "safe_stop_code": None,
    }


def init_phase_state(state_path: Path) -> dict[str, Any]:
    state = _default_state()
    atomic_write_json(state_path, state)
    return state


def load_phase_state(state_path: Path) -> dict[str, Any]:
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA_CUSTODY_STATE:
        raise CustodyRunnerError("invalid_phase_state_schema", "schema")
    return payload


def save_phase_state(state_path: Path, state: Mapping[str, Any]) -> None:
    atomic_write_json(state_path, dict(state))


def assert_phase_allowed(state: Mapping[str, Any], phase: str) -> None:
    if phase not in PHASES:
        raise CustodyRunnerError("unknown_phase", "phase")
    completed = set(state.get("completed_phases") or [])
    for required in PHASE_PREREQUISITES[phase]:
        if required not in completed:
            raise CustodyRunnerError("phase_order_violation", phase)


def mark_phase_complete(state_path: Path, phase: str) -> dict[str, Any]:
    state = load_phase_state(state_path)
    assert_phase_allowed(state, phase)
    completed = list(state.get("completed_phases") or [])
    if phase not in completed and phase not in {"restore-settings", "finalize"}:
        completed.append(phase)
    state["completed_phases"] = completed
    save_phase_state(state_path, state)
    return state


def allocate_attempt_directory(
    *,
    capture_root: Path,
    state_path: Path,
    phase: str,
    kind: str,
    force_ordinal: int | None = None,
) -> Path:
    state = load_phase_state(state_path)
    assert_phase_allowed(state, phase)
    if kind not in {AttemptKind.CORRELATION_CAPTURE.value, AttemptKind.POST_NEW_PROMPT.value}:
        raise CustodyRunnerError("unknown_attempt_kind", "kind")
    ordinal = force_ordinal if force_ordinal is not None else int(state["next_ordinal"][kind])
    if ordinal > 3:
        raise CustodyRunnerError("attempt_budget_exceeded", "ordinal")
    if kind == AttemptKind.CORRELATION_CAPTURE.value:
        name = f"{phase}-{ordinal}"
    else:
        name = f"{phase}-prompt-{ordinal}"
    attempt_dir = capture_root / "attempts" / name
    if attempt_dir.exists():
        raise CustodyRunnerError("attempt_directory_exists", str(attempt_dir))
    attempt_dir.mkdir(parents=True, exist_ok=False)
    if force_ordinal is None:
        state["next_ordinal"][kind] = ordinal + 1
    locators = dict(state.get("attempt_locators") or {})
    locators[name] = str(attempt_dir)
    state["attempt_locators"] = locators
    save_phase_state(state_path, state)
    return attempt_dir


def write_attempt_manifest(
    *,
    attempt_dir: Path,
    phase: str,
    kind: str,
    ordinal: int,
    failure_class: str,
    reason_code: str | None,
    classification_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    FailureClass(failure_class)  # validate
    AttemptKind(kind)
    payload = {
        "schema": SCHEMA_ATTEMPT_MANIFEST,
        "attempt_id": f"{phase}:{kind}:{ordinal}",
        "phase": phase,
        "kind": kind,
        "ordinal": ordinal,
        "failure_class": failure_class,
        "reason_code": reason_code,
        "classification_evidence": dict(classification_evidence),
    }
    atomic_write_json(attempt_dir / "attempt-manifest.json", payload)
    return payload


def capture_process_records(
    *,
    pids: Sequence[int],
    output_path: Path,
    subprocess_run: SubprocessRun | None = None,
) -> list[dict[str, Any]]:
    wanted = {int(pid) for pid in pids}
    if not wanted:
        atomic_write_json(
            output_path,
            {"schema": SCHEMA_PROCESS_RECORD, "processes": []},
        )
        return []
    run = subprocess_run or subprocess.run
    pid_list = ",".join(str(pid) for pid in sorted(wanted))
    script = (
        f"$pids=@({pid_list});"
        "Get-CimInstance Win32_Process |"
        "Where-Object { $pids -contains $_.ProcessId } |"
        "Select-Object ProcessId,ParentProcessId,CreationDate,ExecutablePath,CommandLine |"
        "ConvertTo-Json -Compress -Depth 3"
    )
    completed = run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise CustodyRunnerError("process_query_failed", "powershell")
    raw = (completed.stdout or "").strip()
    rows: list[Any]
    if not raw:
        rows = []
    else:
        parsed = json.loads(raw)
        rows = parsed if isinstance(parsed, list) else [parsed]
    records: list[dict[str, Any]] = []
    for row in rows:
        pid = int(row["ProcessId"])
        if pid not in wanted:
            continue
        command = str(row.get("CommandLine") or "")
        records.append(
            {
                "pid": pid,
                "parent_process_id": int(row.get("ParentProcessId") or 0),
                "creation_date": str(row.get("CreationDate") or ""),
                "executable_path": str(row.get("ExecutablePath") or ""),
                "command_line_sha256": _digest_bytes(command.encode("utf-8", errors="replace")),
            }
        )
    atomic_write_json(
        output_path,
        {"schema": SCHEMA_PROCESS_RECORD, "processes": records},
    )
    return records


def require_process_tree_exited(
    *,
    pids: Sequence[int],
    query: ProcessQuery | None = None,
) -> None:
    query_fn = query or (
        lambda pids, **_kwargs: capture_process_records(
            pids=pids,
            output_path=Path(os.environ.get("TEMP", ".")) / f"plan117-proc-{uuid.uuid4().hex}.json",
        )
    )
    remaining = query_fn(tuple(int(pid) for pid in pids))
    if remaining:
        raise CustodyRunnerError("process_tree_still_alive", "pids")


def _default_keyring_backend() -> Any:
    import keyring as keyring_backend

    return keyring_backend


def read_durable_approval_projection(
    *,
    workspace_root: Path,
    keyring_backend: Any | None = None,
    store_runtime_root: Path | None = None,
    hmac_key: bytes | None = None,
) -> dict[str, Any]:
    """Read a durable approval via KeyringApprovalStore (HMAC-verified, read-only).

    Computes workspace identity with ``resolve_workspace_identity``, then calls
    ``KeyringApprovalStore.read_durable``. Deserialization already verifies the
    record HMAC; this projection never reimplements digest/HMAC algorithms and
    never writes or revokes approvals.
    """
    from optimus.acp.launch_approvals import ApprovalError, KeyringApprovalStore
    from optimus.acp.trusted_paths import TrustedPathError, resolve_workspace_identity

    workspace_root = workspace_root.resolve()
    try:
        identity = resolve_workspace_identity(workspace_root)
    except TrustedPathError as exc:
        raise CustodyRunnerError("workspace_identity_unavailable", "workspace_root") from exc

    runtime_root = (store_runtime_root or (workspace_root / ".optimus")).resolve()
    runtime_root.mkdir(parents=True, exist_ok=True)
    store = KeyringApprovalStore(
        keyring_backend=keyring_backend or _default_keyring_backend(),
        runtime_root=runtime_root,
        hmac_key=hmac_key,
    )
    try:
        record = store.read_durable(identity.digest)
    except ApprovalError as exc:
        raise CustodyRunnerError("durable_approval_integrity_failure", "approval") from exc
    if record is None:
        raise CustodyRunnerError("durable_approval_missing", "approval")

    return {
        "approval_id": record.approval_id,
        "mode": record.mode,
        "security_snapshot_digest": record.security_snapshot_digest,
        "workspace_digest": record.workspace_identity.digest,
        "policy_compatibility": record.policy_compatibility,
        "registry_version": record.registry_version,
        "record_hmac_verified": True,
    }


def read_launch_audit_suffix(
    *,
    runtime_root: Path,
    launch_session_id: str | None = None,
    final_reason_code: str = "AUTHORIZED",
) -> dict[str, Any]:
    """Parse the append-only launch-audit NDJSON suffix (read-only).

    Returns the last matching event for ``launch_session_id`` (or the last
    AUTHORIZED event when session id is omitted). Does not append or mutate
    the audit file.
    """
    from optimus.acp.operator_paths import WorkspaceRuntimeRootError, require_workspace_runtime_root

    runtime_root = runtime_root.resolve()
    try:
        require_workspace_runtime_root(runtime_root)
    except WorkspaceRuntimeRootError as exc:
        raise CustodyRunnerError("launch_audit_runtime_unavailable", "runtime_root") from exc

    path = runtime_root / "launch-audit.ndjson"
    if not path.is_file():
        raise CustodyRunnerError("launch_audit_missing", "launch-audit.ndjson")

    matches: list[dict[str, Any]] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CustodyRunnerError("launch_audit_unreadable", "launch-audit.ndjson") from exc

    for line_no, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CustodyRunnerError("launch_audit_invalid_json", f"line:{line_no}") from exc
        if not isinstance(event, dict):
            raise CustodyRunnerError("launch_audit_invalid_json", f"line:{line_no}")
        if launch_session_id is not None and str(event.get("launch_session_id")) != launch_session_id:
            continue
        if final_reason_code and str(event.get("final_reason_code")) != final_reason_code:
            continue
        matches.append(event)

    if not matches:
        raise CustodyRunnerError("launch_audit_event_missing", "launch_session_id")

    event = matches[-1]
    return {
        "launch_session_id": event.get("launch_session_id"),
        "approval_id": event.get("approval_id"),
        "approval_mode": event.get("approval_mode"),
        "mode": event.get("approval_mode"),
        "workspace_digest": event.get("workspace_digest"),
        "final_reason_code": event.get("final_reason_code"),
        "policy_version": event.get("policy_version"),
        "policy_compatibility": event.get("policy_version"),
        "registry_version": event.get("registry_version"),
        "setting_decisions": event.get("setting_decisions"),
        "child_propagation_decisions": event.get("child_propagation_decisions"),
    }


def _project_audit_against_durable(
    audit: Mapping[str, Any],
    durable: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    """Bind an audit suffix to the HMAC-verified durable snapshot digest.

    Launch-audit events do not store ``security_snapshot_digest``; after the
    approval_id matches the durable record, the digest is taken from that
    verified record so direct/relay equality remains bound to one store read.
    """
    if str(audit.get("approval_id")) != str(durable.get("approval_id")):
        raise CustodyRunnerError(
            "invalid_probe_relay_environment_mismatch",
            f"{label}.approval_id",
        )
    return {
        "approval_id": audit.get("approval_id"),
        "approval_mode": audit.get("approval_mode") or audit.get("mode"),
        "mode": audit.get("approval_mode") or audit.get("mode"),
        "workspace_digest": audit.get("workspace_digest"),
        "final_reason_code": audit.get("final_reason_code"),
        "policy_compatibility": audit.get("policy_compatibility") or audit.get("policy_version"),
        "security_snapshot_digest": durable.get("security_snapshot_digest"),
        "setting_decisions": audit.get("setting_decisions"),
        "child_propagation_decisions": audit.get("child_propagation_decisions"),
    }


def prove_direct_relay_approval_equivalence(
    *,
    workspace_root: Path,
    runtime_root: Path,
    direct_launch_session_id: str,
    relay_launch_session_id: str,
    output_path: Path,
    keyring_backend: Any | None = None,
    store_runtime_root: Path | None = None,
    hmac_key: bytes | None = None,
) -> dict[str, Any]:
    """Prove environment equivalence from real store + launch-audit reads."""
    durable = read_durable_approval_projection(
        workspace_root=workspace_root,
        keyring_backend=keyring_backend,
        store_runtime_root=store_runtime_root or runtime_root,
        hmac_key=hmac_key,
    )
    direct_raw = read_launch_audit_suffix(
        runtime_root=runtime_root,
        launch_session_id=direct_launch_session_id,
    )
    relay_raw = read_launch_audit_suffix(
        runtime_root=runtime_root,
        launch_session_id=relay_launch_session_id,
    )
    direct = _project_audit_against_durable(direct_raw, durable, label="direct")
    relay = _project_audit_against_durable(relay_raw, durable, label="relay")
    return compare_approval_equality(
        durable_approval=durable,
        direct_audit=direct,
        relay_audit=relay,
        output_path=output_path,
    )


def compare_approval_equality(
    *,
    durable_approval: Mapping[str, Any],
    direct_audit: Mapping[str, Any],
    relay_audit: Mapping[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    fields = [
        "approval_id",
        "mode",
        "security_snapshot_digest",
        "workspace_digest",
        "policy_compatibility",
        "record_hmac_verified",
        "final_reason_code",
    ]

    def _mode(audit: Mapping[str, Any]) -> str:
        return str(audit.get("approval_mode") or audit.get("mode") or "")

    for audit, label in ((direct_audit, "direct"), (relay_audit, "relay")):
        if str(audit.get("approval_id")) != str(durable_approval.get("approval_id")):
            raise CustodyRunnerError("invalid_probe_relay_environment_mismatch", f"{label}.approval_id")
        if _mode(audit) != str(durable_approval.get("mode")):
            raise CustodyRunnerError("invalid_probe_relay_environment_mismatch", f"{label}.mode")
        if str(audit.get("security_snapshot_digest")) != str(
            durable_approval.get("security_snapshot_digest")
        ):
            raise CustodyRunnerError(
                "invalid_probe_relay_environment_mismatch",
                f"{label}.security_snapshot_digest",
            )
        if str(audit.get("workspace_digest")) != str(durable_approval.get("workspace_digest")):
            raise CustodyRunnerError(
                "invalid_probe_relay_environment_mismatch",
                f"{label}.workspace_digest",
            )
        policy = audit.get("policy_compatibility", durable_approval.get("policy_compatibility"))
        if str(policy) != str(durable_approval.get("policy_compatibility")):
            raise CustodyRunnerError(
                "invalid_probe_relay_environment_mismatch",
                f"{label}.policy_compatibility",
            )
        if str(audit.get("final_reason_code")) != "AUTHORIZED":
            raise CustodyRunnerError(
                "invalid_probe_relay_environment_mismatch",
                f"{label}.final_reason_code",
            )
    if not durable_approval.get("record_hmac_verified"):
        raise CustodyRunnerError("invalid_probe_relay_environment_mismatch", "record_hmac_verified")
    if str(direct_audit.get("security_snapshot_digest")) != str(
        relay_audit.get("security_snapshot_digest")
    ):
        raise CustodyRunnerError(
            "invalid_probe_relay_environment_mismatch",
            "direct_vs_relay.security_snapshot_digest",
        )

    payload = {
        "schema": SCHEMA_APPROVAL_EQUIVALENCE,
        "equivalent": True,
        "compared_fields": fields,
        "approval_id": durable_approval.get("approval_id"),
        "mode": durable_approval.get("mode"),
        "security_snapshot_digest": durable_approval.get("security_snapshot_digest"),
        "workspace_digest": durable_approval.get("workspace_digest"),
        "policy_compatibility": durable_approval.get("policy_compatibility"),
        "record_hmac_verified": True,
        "final_reason_code": "AUTHORIZED",
    }
    atomic_write_json(output_path, payload)
    return payload


def parse_completed_transcript(
    bin_path: Path,
    *,
    relay_terminated: bool,
    output_path: Path,
) -> dict[str, Any]:
    if not relay_terminated:
        raise CustodyRunnerError("relay_not_terminated", "relay")
    raw = bin_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CustodyRunnerError("invalid_probe_transcript_utf8", "transcript") from exc
    messages: list[dict[str, Any]] = []
    ordered_updates: list[str] = []
    session_id: str | None = None
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CustodyRunnerError("invalid_probe_transcript_framing", f"line:{line_no}") from exc
        if not isinstance(obj, dict):
            raise CustodyRunnerError("invalid_probe_transcript_framing", f"line:{line_no}")
        method = obj.get("method")
        msg: dict[str, Any] = {
            "method": method,
            "id": obj.get("id"),
            "has_result": "result" in obj,
            "has_error": "error" in obj,
        }
        if isinstance(obj.get("result"), dict):
            stop = obj["result"].get("stopReason") or obj["result"].get("stop_reason")
            if stop is not None:
                msg["stop_reason"] = stop
            if method == "session/new" and "sessionId" in obj["result"]:
                session_id = str(obj["result"]["sessionId"])
        if method == "session/update":
            params = obj.get("params") if isinstance(obj.get("params"), dict) else {}
            update = params.get("update") if isinstance(params.get("update"), dict) else {}
            update_type = update.get("sessionUpdate") or update.get("type")
            if update_type:
                ordered_updates.append(str(update_type))
        messages.append(msg)
    content_sha = _digest_bytes(raw)
    projection = {
        "schema": SCHEMA_TRANSCRIPT_PROJECTION,
        "messages": messages,
        "ordered_update_types": ordered_updates,
        "server_session_id": session_id,
        "content_sha256": content_sha,
        "byte_record_ref": str(bin_path),
        "interval": {"start_ns": None, "end_ns": None},
    }
    atomic_write_json(output_path, projection)
    return projection


def compare_transcript_debug(
    *,
    projection: Mapping[str, Any],
    debug_suffix: Mapping[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    keys = ("messages", "ordered_update_types", "server_session_id", "interval")
    for key in keys:
        if projection.get(key) != debug_suffix.get(key):
            raise CustodyRunnerError("invalid_probe_transcript_debug_divergence", key)
    payload = {
        "schema": "plan117-custody-transcript-debug-agreement-v1",
        "agree": True,
        "compared_keys": list(keys),
    }
    atomic_write_json(output_path, payload)
    return payload


def print_origin_a_instructions() -> None:
    print("Operator action (origin-a): submit the exact fixture prompt below.")
    print(PROMPT_FIXTURE_TEXT.rstrip("\n"))
    print(f"Prompt fixture SHA-256: {PROMPT_FIXTURE_SHA256}")


def print_restart_b_instructions() -> None:
    print(
        "Operator action (restart-b): use the prior-thread affordance Zed actually exposes "
        "for the Optimus thread from origin-a. Do not invent a continuation path."
    )
    print(
        "Label the UI outcome: 'prior_thread' if a prior-thread affordance was offered, "
        "or 'new_thread_only' if only \"New Optimus Thread\" was available."
    )


def print_fresh_control_c_instructions() -> None:
    print(
        "Operator action (fresh-control-c): explicitly start a new Optimus thread "
        "(New Optimus Thread) in the same workspace as a fresh-thread control."
    )


def record_operator_assertion(
    *,
    output_path: Path,
    phase: str,
    label: str,
    detail: str,
) -> dict[str, Any]:
    payload = {
        "schema": "plan117-custody-operator-assertion-v1",
        "phase": phase,
        "label": label,
        "detail": detail,
        "asserted": True,
        "machine_proof": False,
    }
    atomic_write_json(output_path, payload)
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--zed-executable", type=Path, required=True)
    parser.add_argument("--zed-source", type=Path, required=True)
    parser.add_argument("--settings-path", type=Path, required=True)
    parser.add_argument("--debug-log", type=Path, required=True)
    parser.add_argument("--custody-root", type=Path, default=None)
    parser.add_argument("--evidence-capture-root", type=Path, default=None)
    parser.add_argument("--result", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.phase == "finalize" and (
        args.evidence_capture_root is None or args.result is None
    ):
        print(
            "finalize requires --evidence-capture-root and --result",
            file=sys.stderr,
        )
        raise SystemExit(2)
    custody_root = (args.custody_root or (args.capture_root / "custody")).resolve()
    resolve_probe_paths(
        workspace_root=args.workspace_root,
        capture_root=args.capture_root,
        zed_executable=args.zed_executable,
        zed_source=args.zed_source,
        settings_path=args.settings_path,
        debug_log=args.debug_log,
        custody_root=custody_root,
        allowed_settings_roots=(args.settings_path.parent.resolve(), custody_root),
    )
    state_path = args.capture_root.resolve() / STATE_FILENAME
    if not state_path.exists():
        init_phase_state(state_path)
    state = load_phase_state(state_path)
    assert_phase_allowed(state, args.phase)

    if args.phase == "origin-a":
        require_readme_precondition(args.workspace_root.resolve())
        if PROMPT_FIXTURE_PATH.is_file():
            digest = sha256_file(PROMPT_FIXTURE_PATH).upper()
            if digest != PROMPT_FIXTURE_SHA256:
                raise CustodyRunnerError("prompt_fixture_digest_mismatch", "prompt")
        print_origin_a_instructions()
    elif args.phase == "restart-b":
        print_restart_b_instructions()
    elif args.phase == "fresh-control-c":
        print_fresh_control_c_instructions()
    elif args.phase == "restore-settings":
        meta_path, _ = _settings_tx_paths(custody_root)
        if meta_path.is_file():
            proof = json.loads(meta_path.read_text(encoding="utf-8"))
            if not proof.get("restored"):
                restore_settings(
                    settings_path=args.settings_path.resolve(),
                    custody_root=custody_root,
                    expected_mutated_sha256=str(proof["mutated_sha256"]),
                )
    elif args.phase == "finalize":
        mark_phase_complete(state_path, "finalize")
        print(
            json.dumps({"phase": "finalize", "ok": True}, separators=(",", ":"), sort_keys=True)
        )
        return 0

    if args.phase not in {"restore-settings", "finalize"}:
        mark_phase_complete(state_path, args.phase)
    return 0


__all__ = (
    "PHASES",
    "PROMPT_FIXTURE_SHA256",
    "PROMPT_FIXTURE_TEXT",
    "CustodyRunnerError",
    "allocate_attempt_directory",
    "assert_phase_allowed",
    "atomic_write_json",
    "capture_process_records",
    "compare_approval_equality",
    "compare_transcript_debug",
    "init_phase_state",
    "load_phase_state",
    "main",
    "mark_phase_complete",
    "mutate_settings_insert_relay",
    "parse_completed_transcript",
    "print_fresh_control_c_instructions",
    "print_origin_a_instructions",
    "print_restart_b_instructions",
    "prove_direct_relay_approval_equivalence",
    "read_durable_approval_projection",
    "read_launch_audit_suffix",
    "record_operator_assertion",
    "require_process_tree_exited",
    "require_readme_precondition",
    "require_regular_non_symlink",
    "resolve_probe_paths",
    "restore_settings",
    "run_with_settings_transaction",
    "save_phase_state",
    "write_attempt_manifest",
    "write_canonical_json",
)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
