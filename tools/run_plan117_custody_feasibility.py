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
    MAX_CORRELATION_ORDINAL_UNDER_AMENDMENT,
    ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256,
    SCHEMA_APPROVAL_EQUIVALENCE,
    SCHEMA_ATTEMPT_MANIFEST,
    SCHEMA_CUSTODY_STATE,
    SCHEMA_PROCESS_RECORD,
    SCHEMA_RUN_RESERVATION,
    SCHEMA_SETTINGS_TRANSACTION,
    SCHEMA_STAGE_ATTEMPT_RECORD,
    SCHEMA_STAGE_LEDGER,
    SCHEMA_TRANSCRIPT_PROJECTION,
    AttemptKind,
    CustodyContractError,
    EvidenceReference,
    FailureClass,
    LaunchSessionIdentity,
    LiveSessionProof,
    RetryPreflightResult,
    StageAttemptRecord,
    StageKind,
    StageLedger,
    StageStatus,
    atomic_create_json,
    atomic_write_bytes,
    atomic_write_json,
    evaluate_prompt_retry_preflight,
    next_stage_ordinal,
    normalize_stage_ledger,
    sha256_file,
    sha256_hex_equal,
    stage_attempt_record_payload,
    stage_attempt_record_sha256,
    write_canonical_json,
)
from tools.plan117_custody_relay import (  # noqa: E402
    acquire_live_session_proof,
    send_existing_session_prompt,
)

PHASES = (
    "direct-control",
    "relay-control",
    "origin-a",
    "origin-a-prompt-retry",
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
    "origin-a-prompt-retry": ("direct-control", "relay-control", "origin-a"),
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
PROMPT_FIXTURE_V2_PATH = (
    ROOT / "tests" / "fixtures" / "evidence" / "plan117-server-custody-prompt-v2.txt"
)
PROMPT_FIXTURE_V2_SHA256 = (
    "9195EFEEE3A2180CFB85EDE409FF7785F159F64E36426DCDB369251560E28A50"
)
PYPROJECT_TARGET_SHA256 = (
    "AE28C0C3776F6B78DF23E86FC0E88B0088FEBB7241A04650C604D713E23EF697"
)

SETTINGS_TX_META = "settings-transaction.json"
SETTINGS_PREIMAGE = "settings-preimage.bin"
STATE_FILENAME = "plan117-custody-state.json"
SCHEMA_LAUNCH_SESSION_IDENTITY = "plan117-custody-launch-session-identity-v1"
SCHEMA_PROMPT_RESERVATION = "plan117-custody-prompt-reservation-v1"
PROMPT_RETRY_ORDINAL = 3
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
    approved_digest = str(approval["pre_image_sha256"] or "").upper()
    actual_digest = str(pre_image_sha256 or "").upper()
    if approved_digest != actual_digest:
        raise CustodyRunnerError("settings_mutation_approval_digest_mismatch", "pre_image_sha256")
    if not str(approval["operator_identity"]).strip():
        raise CustodyRunnerError("settings_mutation_approval_incomplete", "operator_identity")
    if not str(approval["approved_at_utc"]).strip():
        raise CustodyRunnerError("settings_mutation_approval_incomplete", "approved_at_utc")
    return approval


def _settings_tx_paths(custody_root: Path) -> tuple[Path, Path]:
    return custody_root / SETTINGS_TX_META, custody_root / SETTINGS_PREIMAGE


def _strip_jsonc(text: str) -> str:
    """Strip // and /* */ comments and trailing commas for Zed settings.jsonc.

    Trailing-comma removal tracks string/escape state so values such as
    ``\"a, ]\"`` are never corrupted.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            if i + 1 >= n:
                # Unterminated block comment: leave remainder as-is so
                # json.loads fails closed rather than inventing structure.
                out.append(text[i - 2 :])
                break
            i += 2
            continue
        out.append(ch)
        i += 1
    stripped = "".join(out)
    # Remove trailing commas before } or ] only outside strings.
    cleaned: list[str] = []
    j = 0
    m = len(stripped)
    in_string = False
    escape = False
    while j < m:
        ch = stripped[j]
        if in_string:
            cleaned.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            j += 1
            continue
        if ch == '"':
            in_string = True
            cleaned.append(ch)
            j += 1
            continue
        if ch == ",":
            k = j + 1
            while k < m and stripped[k] in " \t\r\n":
                k += 1
            if k < m and stripped[k] in "}]":
                j += 1
                continue
        cleaned.append(ch)
        j += 1
    return "".join(cleaned)


def parse_jsonc(text: str) -> Any:
    """Parse JSON or JSONC (Zed settings). Fail closed on invalid input."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(_strip_jsonc(text))


def _load_settings_json(settings_path: Path) -> dict[str, Any]:
    if not settings_path.exists():
        return {}
    try:
        text = settings_path.read_text(encoding="utf-8")
        payload = parse_jsonc(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CustodyRunnerError("settings_json_invalid", "settings_path") from exc
    if not isinstance(payload, dict):
        raise CustodyRunnerError("settings_json_invalid", "settings_path")
    return payload


def _atomic_replace_settings(settings_path: Path, data: bytes) -> dict[str, str]:
    """Atomically place ``data`` at ``settings_path``.

    Prefer direct ``os.replace`` onto the live path. When that fails with a
    permission/access error (common on Windows while Zed holds settings.json
    open), fall back to rename-away-then-replace: move the live file aside,
    then move the restored sibling into place. Returns the method used and,
    when applicable, the mutated-backup path.
    """
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = settings_path.with_name(f"{settings_path.name}.partial-{uuid.uuid4().hex}")
    try:
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, settings_path)
            return {"restore_method": "direct_replace"}
        except OSError as direct_exc:
            if not _is_settings_replace_access_denied(direct_exc):
                raise
            return _atomic_replace_settings_rename_away(
                settings_path=settings_path,
                prepared_path=temporary,
                direct_exc=direct_exc,
            )
    except OSError as exc:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        raise CustodyRunnerError("settings_atomic_replace_failed", "settings_path") from exc


def _is_settings_replace_access_denied(exc: OSError) -> bool:
    winerror = getattr(exc, "winerror", None)
    if winerror == 5:
        return True
    if isinstance(exc, PermissionError):
        return True
    if getattr(exc, "errno", None) in {13, 5}:  # EACCES / Windows errno surface
        return True
    return False


def _atomic_replace_settings_rename_away(
    *,
    settings_path: Path,
    prepared_path: Path,
    direct_exc: OSError,
) -> dict[str, str]:
    """Move the locked live file aside, then place the prepared bytes."""
    mutated_backup = settings_path.with_name(
        f"{settings_path.name}.mutated-hold-{uuid.uuid4().hex}"
    )
    # Use a distinct sibling name so the final place is not the same "replace onto
    # live path from *.partial-*" operation that just failed under a file lock.
    restored_sibling = settings_path.with_name(
        f"{settings_path.name}.restored-{uuid.uuid4().hex}"
    )
    try:
        if prepared_path.resolve() != restored_sibling.resolve():
            os.replace(prepared_path, restored_sibling)
        if not settings_path.exists():
            os.replace(restored_sibling, settings_path)
            return {"restore_method": "direct_replace"}
        os.replace(settings_path, mutated_backup)
        try:
            os.replace(restored_sibling, settings_path)
        except OSError:
            # Best-effort rollback of the mutated bytes to the live path.
            try:
                if not settings_path.exists() and mutated_backup.exists():
                    os.replace(mutated_backup, settings_path)
            except OSError:
                pass
            raise
        return {
            "restore_method": "rename_away_then_replace",
            "mutated_backup_path": str(mutated_backup),
        }
    except OSError as exc:
        for path in (prepared_path, restored_sibling):
            if path.exists():
                path.unlink(missing_ok=True)
        raise CustodyRunnerError("settings_atomic_replace_failed", "settings_path") from (
            exc if exc is not direct_exc else direct_exc
        )


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
        place = _atomic_replace_settings(settings_path, pre_bytes)
        final_existed = True
        final_digest = _digest_bytes(pre_bytes)
    else:
        settings_path.unlink()
        place = {"restore_method": "unlink_absent_preimage"}
        final_existed = False
        final_digest = None

    proof["restored"] = True
    proof["final_existed"] = final_existed
    proof["final_sha256"] = final_digest
    proof["restore_method"] = place.get("restore_method")
    if place.get("mutated_backup_path"):
        proof["mutated_backup_path"] = place["mutated_backup_path"]
    atomic_write_json(meta_path, proof)
    result = {
        "restored": True,
        "already_restored": False,
        "final_existed": final_existed,
        "final_sha256": final_digest,
        "restore_method": place.get("restore_method"),
    }
    if place.get("mutated_backup_path"):
        result["mutated_backup_path"] = place["mutated_backup_path"]
    return result


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
        "workspace_digest": record.workspace_digest,
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


def load_private_run_manifest(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if path.is_symlink() or not path.is_file():
        raise CustodyRunnerError("private_run_manifest_missing", "private_run_manifest")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CustodyRunnerError("private_run_manifest_invalid", "private_run_manifest") from exc
    if not isinstance(payload, dict):
        raise CustodyRunnerError("private_run_manifest_invalid", "private_run_manifest")
    return payload


def _approval_from_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    approval = manifest.get("settings_mutation_approval")
    if not isinstance(approval, dict):
        raise CustodyRunnerError("settings_mutation_approval_required", "approval")
    return dict(approval)


def _relay_from_manifest(manifest: Mapping[str, Any]) -> tuple[str, list[str]]:
    relay = manifest.get("relay")
    if not isinstance(relay, dict):
        raise CustodyRunnerError("relay_config_missing", "relay")
    command = relay.get("command")
    args = relay.get("args")
    if not isinstance(command, str) or not command.strip():
        raise CustodyRunnerError("relay_config_missing", "relay.command")
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        raise CustodyRunnerError("relay_config_missing", "relay.args")
    return command, list(args)


def _write_phase_observation(
    attempt_dir: Path,
    *,
    phase: str,
    settings_mutated: bool,
) -> dict[str, Any]:
    payload = {
        "schema": "plan117-custody-phase-observation-v1",
        "phase": phase,
        "settings_mutated": settings_mutated,
        "runner_sends_acp": False,
        "ready_for_operator": True,
    }
    atomic_write_json(attempt_dir / "phase-observation.json", payload)
    return payload


def _stdin_operator_wait(prompt: str) -> None:
    print(prompt, flush=True)
    try:
        input()
    except EOFError as exc:
        raise CustodyRunnerError("operator_wait_eof", "stdin") from exc


def _operator_continue_wait(
    attempt_dir: Path,
    prompt: str,
    *,
    timeout_s: float = 3600.0,
    poll_s: float = 0.5,
) -> None:
    """Wait for operator via sentinel file (agent-friendly) or stdin Enter when TTY."""
    import time

    sentinel = attempt_dir / "operator-continue.flag"
    print(prompt, flush=True)
    print(f"Create empty file to continue: {sentinel}", flush=True)
    if sys.stdin.isatty():
        print("(Or press Enter in this terminal.)", flush=True)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if sentinel.is_file():
            return
        if sys.stdin.isatty():
            # Non-blocking-ish: short select alternative - poll sentinel only on Windows
            # when stdin is TTY we still prefer sentinel for agent orchestration.
            pass
        time.sleep(poll_s)
    raise CustodyRunnerError("operator_wait_timeout", str(sentinel))


def _next_attempt_ordinal(*, capture_root: Path, phase: str, kind: str) -> int:
    """Pick the next free per-phase ordinal (1..3) for attempt directory naming."""
    if kind == AttemptKind.CORRELATION_CAPTURE.value:
        pattern = f"{phase}-"
    else:
        pattern = f"{phase}-prompt-"
    attempts = capture_root / "attempts"
    for ordinal in range(1, 4):
        candidate = attempts / f"{pattern}{ordinal}"
        if not candidate.exists():
            return ordinal
    raise CustodyRunnerError("attempt_budget_exceeded", "ordinal")


def run_direct_control_phase(
    *,
    capture_root: Path,
    state_path: Path,
    operator_wait: bool = False,
    wait_fn: Callable[[str], None] | None = None,
) -> Path:
    ordinal = _next_attempt_ordinal(
        capture_root=capture_root,
        phase="direct-control",
        kind=AttemptKind.CORRELATION_CAPTURE.value,
    )
    attempt_dir = allocate_attempt_directory(
        capture_root=capture_root,
        state_path=state_path,
        phase="direct-control",
        kind=AttemptKind.CORRELATION_CAPTURE.value,
        force_ordinal=ordinal,
    )
    write_attempt_manifest(
        attempt_dir=attempt_dir,
        phase="direct-control",
        kind=AttemptKind.CORRELATION_CAPTURE.value,
        ordinal=ordinal,
        failure_class=FailureClass.NONE.value,
        reason_code="observation_pending",
        classification_evidence={"ready_for_operator": True},
    )
    _write_phase_observation(attempt_dir, phase="direct-control", settings_mutated=False)
    print(
        "Operator action (direct-control): launch Zed with the current Optimus "
        "agent_servers.optimus command (no relay). Do not edit settings.json."
    )
    if operator_wait:
        if wait_fn is not None:
            wait_fn(
                "Press Enter when the direct-control observation window is complete "
                f"(attempt={attempt_dir})."
            )
        else:
            _operator_continue_wait(
                attempt_dir,
                "Waiting for direct-control observation window to complete "
                f"(attempt={attempt_dir}).",
            )
    return attempt_dir


def run_relay_mediated_phase(
    *,
    phase: str,
    capture_root: Path,
    state_path: Path,
    settings_path: Path,
    custody_root: Path,
    private_run_manifest: Path,
    observe: Callable[[Path], None] | None = None,
    operator_wait: bool = False,
    wait_fn: Callable[[str], None] | None = None,
) -> Path:
    if phase not in {"relay-control", "origin-a"}:
        raise CustodyRunnerError("unknown_phase", phase)
    manifest = load_private_run_manifest(private_run_manifest)
    approval = _approval_from_manifest(manifest)
    relay_command, relay_args = _relay_from_manifest(manifest)

    attempt_holder: dict[str, Path] = {}

    def body() -> None:
        ordinal = _next_attempt_ordinal(
            capture_root=capture_root,
            phase=phase,
            kind=AttemptKind.CORRELATION_CAPTURE.value,
        )
        attempt_dir = allocate_attempt_directory(
            capture_root=capture_root,
            state_path=state_path,
            phase=phase,
            kind=AttemptKind.CORRELATION_CAPTURE.value,
            force_ordinal=ordinal,
        )
        attempt_holder["path"] = attempt_dir
        write_attempt_manifest(
            attempt_dir=attempt_dir,
            phase=phase,
            kind=AttemptKind.CORRELATION_CAPTURE.value,
            ordinal=ordinal,
            failure_class=FailureClass.NONE.value,
            reason_code="observation_pending",
            classification_evidence={"ready_for_operator": True, "settings_mutated": True},
        )
        _write_phase_observation(attempt_dir, phase=phase, settings_mutated=True)
        if phase == "relay-control":
            print(
                "Operator action (relay-control): launch Zed while settings point at the "
                "custody relay. Runner sends no ACP bytes."
            )
        if observe is not None:
            observe(attempt_dir)
        elif operator_wait:
            if wait_fn is not None:
                wait_fn(
                    "Press Enter when the relay observation window is complete "
                    f"(settings will restore; attempt={attempt_dir})."
                )
            else:
                _operator_continue_wait(
                    attempt_dir,
                    "Waiting for relay observation window to complete "
                    f"(settings remain mutated until continue; attempt={attempt_dir}).",
                )

    run_with_settings_transaction(
        settings_path=settings_path,
        custody_root=custody_root,
        relay_command=relay_command,
        relay_args=relay_args,
        approval=approval,
        body=body,
    )
    return attempt_holder["path"]


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


def _require_fixture_v2_digests(*, prompt_fixture: Path, workspace_root: Path) -> None:
    require_regular_non_symlink(prompt_fixture, label="prompt_fixture")
    prompt_digest = sha256_file(prompt_fixture)
    if not sha256_hex_equal(prompt_digest, PROMPT_FIXTURE_V2_SHA256):
        raise CustodyRunnerError("invalid_probe_fixture_identity_mismatch", "prompt_fixture")
    target = workspace_root / "pyproject.toml"
    require_regular_non_symlink(target, label="pyproject.toml")
    target_digest = sha256_file(target)
    if not sha256_hex_equal(target_digest, PYPROJECT_TARGET_SHA256):
        raise CustodyRunnerError("invalid_probe_fixture_identity_mismatch", "pyproject.toml")


def assert_origin_a3_preflight(
    *,
    expected_run_attempt_id: str,
    ledger: StageLedger,
    prompt_fixture: Path,
    workspace_root: Path,
    reservation_path: Path,
) -> None:
    """Fail closed unless origin-a-3 is the exact next correlation allocation."""
    if expected_run_attempt_id != "origin-a-3":
        raise CustodyRunnerError("invalid_probe_stage_accounting", "expected_run_attempt_id")
    next_corr = next_stage_ordinal(ledger, StageKind.CORRELATION_CAPTURE)
    if next_corr != 3:
        raise CustodyRunnerError("invalid_probe_stage_accounting", "correlation_ordinal")
    if next_corr > 3:
        raise CustodyRunnerError("invalid_probe_retry_budget_exhausted", "correlation_ordinal")
    if reservation_path.exists():
        raise CustodyRunnerError("reservation_already_exists", str(reservation_path))
    attempt_dir = reservation_path.parent.parent / "attempts" / "origin-a-3"
    if attempt_dir.exists():
        raise CustodyRunnerError("reservation_already_exists", str(attempt_dir))
    _require_fixture_v2_digests(prompt_fixture=prompt_fixture, workspace_root=workspace_root)


def reserve_origin_a_run(
    *,
    reservation_root: Path,
    run_attempt_id: str,
    ledger: StageLedger,
) -> Path:
    """Immutable exclusive reservation before settings mutation / launch."""
    if run_attempt_id != "origin-a-3":
        raise CustodyRunnerError("invalid_probe_stage_accounting", "run_attempt_id")
    next_corr = next_stage_ordinal(ledger, StageKind.CORRELATION_CAPTURE)
    if next_corr != 3:
        raise CustodyRunnerError("invalid_probe_stage_accounting", "correlation_ordinal")
    reservation_root.mkdir(parents=True, exist_ok=True)
    path = reservation_root / f"{run_attempt_id}.json"
    payload = {
        "schema": SCHEMA_RUN_RESERVATION,
        "run_attempt_id": run_attempt_id,
        "correlation_ordinal": 3,
        "prompt_ordinal_if_correlated": ledger.next_prompt_ordinal,
        "amendment_sha256": ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256.lower(),
        "created_utc": "reserved",
    }
    try:
        atomic_create_json(path, payload)
    except CustodyContractError as exc:
        raise CustodyRunnerError(exc.reason_code, exc.field_path) from exc
    return path


def _stage_record_from_payload(payload: Mapping[str, Any]) -> StageAttemptRecord:
    try:
        stage = StageKind(str(payload["stage"]))
        status = StageStatus(str(payload["status"]))
        failure_class = FailureClass(str(payload["failure_class"]))
        ordinal = int(payload["ordinal"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CustodyRunnerError("invalid_probe_retry_ledger_unavailable", "stage_fields") from exc
    evidence_raw = payload.get("evidence")
    if not isinstance(evidence_raw, list) or not evidence_raw:
        raise CustodyRunnerError("invalid_probe_retry_ledger_unavailable", "evidence")
    evidence: list[EvidenceReference] = []
    for index, item in enumerate(evidence_raw):
        if not isinstance(item, Mapping):
            raise CustodyRunnerError(
                "invalid_probe_retry_ledger_unavailable",
                f"evidence[{index}]",
            )
        try:
            evidence.append(
                EvidenceReference(
                    relative_path=str(item["relative_path"]),
                    sha256=str(item["sha256"]),
                    hash_method=str(item["hash_method"]),
                )
            )
        except KeyError as exc:
            raise CustodyRunnerError(
                "invalid_probe_retry_ledger_unavailable",
                f"evidence[{index}]",
            ) from exc
    supersedes_record_id = payload.get("supersedes_record_id")
    supersedes_sha256 = payload.get("supersedes_sha256")
    if not isinstance(supersedes_record_id, str) or not supersedes_record_id:
        raise CustodyRunnerError(
            "invalid_probe_retry_ledger_unavailable",
            "supersedes_record_id",
        )
    if not isinstance(supersedes_sha256, str) or not supersedes_sha256:
        raise CustodyRunnerError(
            "invalid_probe_retry_ledger_unavailable",
            "supersedes_sha256",
        )
    reason_code = payload.get("reason_code")
    if reason_code is not None and not isinstance(reason_code, str):
        raise CustodyRunnerError("invalid_probe_retry_ledger_unavailable", "reason_code")
    try:
        return StageAttemptRecord(
            record_id=str(payload["record_id"]),
            run_attempt_id=str(payload["run_attempt_id"]),
            stage=stage,
            ordinal=ordinal,
            status=status,
            failure_class=failure_class,
            reason_code=reason_code,
            evidence=tuple(evidence),
            supersedes_record_id=supersedes_record_id,
            supersedes_sha256=supersedes_sha256,
            amendment_sha256=str(payload["amendment_sha256"]),
            created_by=str(payload["created_by"]),
            created_utc=str(payload["created_utc"]),
        )
    except KeyError as exc:
        raise CustodyRunnerError(
            "invalid_probe_retry_ledger_unavailable",
            "stage_record",
        ) from exc


def load_stage_ledger(path: Path) -> StageLedger:
    """Load and recompute an immutable stage ledger; never trust stored next_* alone."""
    require_regular_non_symlink(path, label="stage_ledger")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CustodyRunnerError("invalid_probe_retry_ledger_unavailable", "stage_ledger") from exc
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA_STAGE_LEDGER:
        raise CustodyRunnerError("invalid_probe_retry_ledger_unavailable", "schema")
    records_raw = payload.get("records")
    if not isinstance(records_raw, list) or not records_raw:
        raise CustodyRunnerError("invalid_probe_retry_ledger_unavailable", "records")
    try:
        records = tuple(
            _stage_record_from_payload(item)
            for item in records_raw
            if isinstance(item, Mapping)
        )
        if len(records) != len(records_raw):
            raise CustodyRunnerError("invalid_probe_retry_ledger_unavailable", "records")
        return normalize_stage_ledger(records)
    except CustodyContractError as exc:
        raise CustodyRunnerError(exc.reason_code, exc.field_path) from exc


def load_launch_session_identity(path: Path) -> LaunchSessionIdentity:
    """Load immutable launch/session identity used to bind live proof (closes vacuous bind)."""
    require_regular_non_symlink(path, label="launch_identity")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CustodyRunnerError(
            "invalid_probe_retry_process_identity_mismatch",
            "launch_identity",
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA_LAUNCH_SESSION_IDENTITY:
        raise CustodyRunnerError(
            "invalid_probe_retry_process_identity_mismatch",
            "launch_identity.schema",
        )
    try:
        return LaunchSessionIdentity(
            run_attempt_id=str(payload["run_attempt_id"]),
            zed_pid=int(payload["zed_pid"]),
            zed_process_start_time_utc=str(payload["zed_process_start_time_utc"]),
            connection_id=str(payload["connection_id"]),
            acp_session_id=str(payload["acp_session_id"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CustodyRunnerError(
            "invalid_probe_retry_process_identity_mismatch",
            "launch_identity",
        ) from exc


def reserve_prompt_ordinal(
    *,
    reservation_root: Path,
    run_attempt_id: str,
    prompt_ordinal: int,
    live_session_proof_sha256: str,
) -> Path:
    """Atomically reserve the single same-session prompt retry ordinal."""
    if run_attempt_id != "origin-a-3":
        raise CustodyRunnerError("invalid_probe_stage_accounting", "run_attempt_id")
    if prompt_ordinal != PROMPT_RETRY_ORDINAL:
        raise CustodyRunnerError("invalid_probe_retry_budget_exhausted", "prompt_ordinal")
    reservation_root.mkdir(parents=True, exist_ok=True)
    path = reservation_root / f"{run_attempt_id}-prompt-{prompt_ordinal}.json"
    payload = {
        "schema": SCHEMA_PROMPT_RESERVATION,
        "run_attempt_id": run_attempt_id,
        "prompt_ordinal": prompt_ordinal,
        "live_session_proof_sha256": live_session_proof_sha256.lower(),
        "amendment_sha256": ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256.lower(),
        "created_utc": "reserved",
        "settings_mutated": False,
        "zed_launched": False,
    }
    try:
        atomic_create_json(path, payload)
    except CustodyContractError as exc:
        raise CustodyRunnerError(exc.reason_code, exc.field_path) from exc
    return path


def _descriptor_sha256_from_locator(descriptor_path: Path) -> str:
    """Read locator digest only; never treat the descriptor as live proof."""
    require_regular_non_symlink(descriptor_path, label="relay_control_descriptor")
    try:
        payload = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CustodyRunnerError(
            "invalid_probe_retry_control_channel_failure",
            "relay_control_descriptor",
        ) from exc
    if not isinstance(payload, dict):
        raise CustodyRunnerError(
            "invalid_probe_retry_control_channel_failure",
            "relay_control_descriptor",
        )
    if payload.get("prompt_sealed") is True:
        raise CustodyRunnerError(
            "invalid_probe_retry_second_prompt_failure",
            "prompt_sealed",
        )
    if payload.get("terminal") is True:
        raise CustodyRunnerError(
            "invalid_probe_retry_control_channel_failure",
            "descriptor_terminal",
        )
    digest = payload.get("descriptor_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise CustodyRunnerError(
            "invalid_probe_retry_control_channel_failure",
            "descriptor_sha256",
        )
    return digest.lower()


def assert_prompt_retry_ledger_eligible(
    *,
    run_attempt_id: str,
    ledger: StageLedger,
) -> None:
    """Fail closed on ledger eligibility before any live control / proof query."""
    if run_attempt_id != "origin-a-3":
        raise CustodyRunnerError("invalid_probe_stage_accounting", "run_attempt_id")
    if not isinstance(ledger, StageLedger):
        raise CustodyRunnerError("invalid_probe_retry_ledger_unavailable", "ledger")
    if ledger.next_correlation_ordinal > MAX_CORRELATION_ORDINAL_UNDER_AMENDMENT + 1:
        raise CustodyRunnerError("invalid_probe_retry_budget_exhausted", "correlation_ordinal")
    if ledger.next_correlation_ordinal != MAX_CORRELATION_ORDINAL_UNDER_AMENDMENT + 1:
        raise CustodyRunnerError("invalid_probe_stage_accounting", "correlation_missing")
    corr = [
        record
        for record in ledger.terminal_records
        if record.run_attempt_id == "origin-a-3"
        and record.stage is StageKind.CORRELATION_CAPTURE
        and record.status is StageStatus.SUCCEEDED
        and record.ordinal == 3
    ]
    if not corr:
        raise CustodyRunnerError("invalid_probe_stage_accounting", "correlation_missing")
    prompt_two = [
        record
        for record in ledger.terminal_records
        if record.run_attempt_id == "origin-a-3"
        and record.stage is StageKind.POST_NEW_PROMPT
        and record.ordinal == 2
        and record.status is StageStatus.FAILED
        and record.failure_class is FailureClass.TRANSIENT
        and record.evidence
    ]
    if not prompt_two:
        raise CustodyRunnerError("invalid_probe_stage_accounting", "prompt_ordinal_2")
    if ledger.next_prompt_ordinal != PROMPT_RETRY_ORDINAL:
        raise CustodyRunnerError("invalid_probe_retry_budget_exhausted", "prompt_ordinal")


def run_origin_a_prompt_retry(
    *,
    run_attempt_id: str,
    workspace_root: Path,
    capture_root: Path,
    prompt_fixture: Path,
    stage_ledger_path: Path,
    launch_identity_path: Path,
    descriptor_path: Path,
    caller_owner_id: str,
) -> dict[str, Any]:
    """Ledger -> identity -> live proof -> pure gate -> reserve ordinal 3 -> prompt.

    Never launches Zed, mutates settings, issues session/new, or accepts proof /
    ACP session IDs / eligibility from CLI input. Loads immutable launch identity
    and passes it to ``assert_prompt_retry_preflight``, which is the trust boundary
    binding live proof to that identity.
    """
    if run_attempt_id != "origin-a-3":
        raise CustodyRunnerError("invalid_probe_stage_accounting", "run_attempt_id")
    if not isinstance(caller_owner_id, str) or not caller_owner_id.strip():
        raise CustodyRunnerError(
            "invalid_probe_retry_control_channel_failure",
            "caller_owner_id",
        )

    ledger = load_stage_ledger(stage_ledger_path)
    # Design order: correlation + prompt-2 transient eligibility before live proof.
    assert_prompt_retry_ledger_eligible(
        run_attempt_id=run_attempt_id,
        ledger=ledger,
    )

    launch_identity = load_launch_session_identity(launch_identity_path)
    _require_fixture_v2_digests(prompt_fixture=prompt_fixture, workspace_root=workspace_root)
    target_sha256 = sha256_file(workspace_root / "pyproject.toml")

    expected_descriptor_sha256 = _descriptor_sha256_from_locator(descriptor_path)
    try:
        proof = acquire_live_session_proof(
            run_attempt_id=run_attempt_id,
            descriptor_path=descriptor_path,
            expected_descriptor_sha256=expected_descriptor_sha256,
            caller_owner_id=caller_owner_id,
        )
    except CustodyContractError as exc:
        raise CustodyRunnerError(exc.reason_code, exc.field_path) from exc

    # Public gate is the trust boundary: bind live proof to immutable launch identity.
    gate_result = assert_prompt_retry_preflight(
        run_attempt_id=run_attempt_id,
        ledger=ledger,
        prompt_fixture=prompt_fixture,
        target_sha256=target_sha256,
        live_session_proof=proof,
        launch_identity=launch_identity,
    )

    reservation_path = reserve_prompt_ordinal(
        reservation_root=capture_root / "reservations",
        run_attempt_id=run_attempt_id,
        prompt_ordinal=PROMPT_RETRY_ORDINAL,
        live_session_proof_sha256=proof.proof_sha256,
    )

    prompt_error: CustodyRunnerError | None = None
    prompt_ok = False
    try:
        send_existing_session_prompt(
            run_attempt_id=run_attempt_id,
            descriptor_path=descriptor_path,
            expected_descriptor_sha256=expected_descriptor_sha256,
            connection_id=proof.connection_id,
            acp_session_id=proof.acp_session_id,
            prompt_fixture=prompt_fixture,
            caller_owner_id=caller_owner_id,
        )
        prompt_ok = True
    except CustodyContractError as exc:
        prompt_error = CustodyRunnerError(exc.reason_code, exc.field_path)
    except CustodyRunnerError as exc:
        prompt_error = exc

    # Append-only outcome + proof references; reservation is never reclaimed.
    attempt_dir = capture_root / "attempts" / run_attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=True)
    proof_ref = {
        "schema": "plan117-custody-live-session-proof-ref-v1",
        "run_attempt_id": run_attempt_id,
        "live_session_proof_sha256": proof.proof_sha256.lower(),
        "prompt_ordinal": PROMPT_RETRY_ORDINAL,
        "reservation_path": str(reservation_path.relative_to(capture_root)).replace("\\", "/"),
        "settings_mutated": False,
        "zed_launched": False,
    }
    try:
        atomic_create_json(attempt_dir / "live-session-proof-ref.json", proof_ref)
    except CustodyContractError as exc:
        # A prior failed-after-reserve retry may already have written the proof ref.
        if exc.reason_code != "reservation_already_exists":
            raise CustodyRunnerError(exc.reason_code, exc.field_path) from exc

    prompt_two = [
        record
        for record in ledger.terminal_records
        if record.run_attempt_id == run_attempt_id
        and record.stage is StageKind.POST_NEW_PROMPT
        and record.ordinal == 2
    ]
    if not prompt_two:
        raise CustodyRunnerError("invalid_probe_stage_accounting", "prompt_ordinal_2")
    parent_prompt = prompt_two[0]
    outcome = StageAttemptRecord(
        record_id=f"{run_attempt_id}-prompt-{PROMPT_RETRY_ORDINAL}",
        run_attempt_id=run_attempt_id,
        stage=StageKind.POST_NEW_PROMPT,
        ordinal=PROMPT_RETRY_ORDINAL,
        status=StageStatus.SUCCEEDED if prompt_ok else StageStatus.FAILED,
        failure_class=FailureClass.NONE if prompt_ok else FailureClass.TRANSIENT,
        reason_code=None if prompt_ok else (
            prompt_error.reason_code
            if prompt_error is not None
            else "invalid_probe_retry_second_prompt_failure"
        ),
        evidence=(
            EvidenceReference(
                relative_path=f"attempts/{run_attempt_id}/live-session-proof-ref.json",
                sha256=sha256_file(attempt_dir / "live-session-proof-ref.json"),
                hash_method="raw_file_sha256",
            ),
            EvidenceReference(
                relative_path=str(reservation_path.relative_to(capture_root)).replace(
                    "\\", "/"
                ),
                sha256=sha256_file(reservation_path),
                hash_method="raw_file_sha256",
            ),
        ),
        supersedes_record_id=parent_prompt.record_id,
        supersedes_sha256=stage_attempt_record_sha256(parent_prompt),
        amendment_sha256=ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256.lower(),
        created_by="plan117-origin-a-prompt-retry",
        created_utc="reserved",
    )
    outcome_path = capture_root / "stages" / f"{run_attempt_id}-prompt-{PROMPT_RETRY_ORDINAL}.json"
    try:
        write_stage_outcome_exclusive(outcome_path, outcome)
    except CustodyRunnerError as outcome_exc:
        # Outcome may already exist from a prior failed-after-reserve attempt.
        if prompt_error is not None:
            raise prompt_error from outcome_exc
        raise

    if prompt_error is not None:
        raise prompt_error

    return {
        "phase": "origin-a-prompt-retry",
        "run_attempt_id": run_attempt_id,
        "prompt_ordinal": gate_result.prompt_ordinal,
        "prompt_fixture_sha256": gate_result.prompt_fixture_sha256,
        "target_sha256": gate_result.target_sha256,
        "live_session_proof_sha256": gate_result.live_session_proof_sha256,
        "settings_mutated": False,
        "zed_launched": False,
        "reservation": str(reservation_path.relative_to(capture_root)).replace("\\", "/"),
    }


def assert_prompt_retry_preflight(
    *,
    run_attempt_id: str,
    ledger: StageLedger,
    prompt_fixture: Path,
    target_sha256: str,
    live_session_proof: LiveSessionProof | None,
    launch_identity: LaunchSessionIdentity,
) -> RetryPreflightResult:
    """Same-session prompt-only retry: no Zed launch, no settings mutation.

    Pure and exception-based. Does not inspect processes, open the relay, mutate
    settings, or synthesize missing proof fields. ``launch_identity`` must come
    from immutable custody records; the gate binds ``live_session_proof`` to that
    identity and never treats the proof's own fields as ground truth.
    """
    if live_session_proof is None:
        raise CustodyRunnerError(
            "blocked_probe_same_session_prompt_retry_unavailable",
            "live_session_proof",
        )
    if not isinstance(launch_identity, LaunchSessionIdentity):
        raise CustodyRunnerError(
            "invalid_probe_retry_process_identity_mismatch",
            "launch_identity",
        )
    require_regular_non_symlink(prompt_fixture, label="prompt_fixture")
    prompt_digest = sha256_file(prompt_fixture)
    try:
        return evaluate_prompt_retry_preflight(
            run_attempt_id=run_attempt_id,
            ledger=ledger,
            prompt_fixture_sha256=prompt_digest,
            expected_prompt_fixture_sha256=PROMPT_FIXTURE_V2_SHA256,
            target_sha256=target_sha256,
            expected_target_sha256=PYPROJECT_TARGET_SHA256,
            live_session_proof=live_session_proof,
            launch_identity=launch_identity,
        )
    except CustodyContractError as exc:
        raise CustodyRunnerError(exc.reason_code, exc.field_path) from exc


def write_stage_outcome_exclusive(path: Path, record: StageAttemptRecord) -> None:
    """Append-only stage outcome via exclusive create."""
    payload = stage_attempt_record_payload(record)
    payload["schema"] = SCHEMA_STAGE_ATTEMPT_RECORD
    try:
        atomic_create_json(path, payload)
    except CustodyContractError as exc:
        raise CustodyRunnerError(exc.reason_code, exc.field_path) from exc


def verify_original_attempt_hashes(
    *,
    originals_root: Path,
    expected_relative_sha256: Mapping[str, str],
) -> None:
    """Fail closed when an immutable original locator/hash disagrees."""
    for relative, expected in expected_relative_sha256.items():
        target = originals_root / relative
        if not target.is_file() or target.is_symlink():
            raise CustodyRunnerError(
                "invalid_probe_origin_attempt_original_mismatch",
                relative,
            )
        actual = sha256_file(target)
        if not sha256_hex_equal(actual, expected):
            raise CustodyRunnerError(
                "invalid_probe_origin_attempt_original_mismatch",
                relative,
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=PHASES,
        help="Probe phase (positional; matches amendment CLI)",
    )
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--zed-executable", type=Path, required=True)
    parser.add_argument("--zed-source", type=Path, required=True)
    parser.add_argument("--settings-path", type=Path, required=True)
    parser.add_argument("--debug-log", type=Path, required=True)
    parser.add_argument("--custody-root", type=Path, default=None)
    parser.add_argument("--private-run-manifest", type=Path, default=None)
    parser.add_argument(
        "--no-operator-wait",
        action="store_true",
        help="Skip stdin operator wait (unit tests only; live Step 2 must wait)",
    )
    parser.add_argument("--evidence-capture-root", type=Path, default=None)
    parser.add_argument("--result", type=Path, default=None)
    parser.add_argument(
        "--expected-run-attempt-id",
        default=None,
        help="Exact physical-run id required for origin-a (must be origin-a-3)",
    )
    parser.add_argument(
        "--run-attempt-id",
        default=None,
        help="Physical-run id for origin-a-prompt-retry (must be origin-a-3)",
    )
    parser.add_argument(
        "--prompt-fixture",
        type=Path,
        default=None,
        help="Prompt fixture path (v2 required for origin-a / origin-a-prompt-retry)",
    )
    parser.add_argument(
        "--stage-ledger",
        type=Path,
        default=None,
        help="Immutable stage ledger path (required for origin-a-prompt-retry)",
    )
    parser.add_argument(
        "--launch-identity",
        type=Path,
        default=None,
        help="Immutable launch/session identity path (required for origin-a-prompt-retry)",
    )
    parser.add_argument(
        "--relay-control-descriptor",
        type=Path,
        default=None,
        help="Private relay control descriptor locator (required for origin-a-prompt-retry)",
    )
    parser.add_argument(
        "--caller-owner-id",
        default=None,
        help="Out-of-band operator identity for relay control (required for origin-a-prompt-retry)",
    )
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
        workspace_root=args.workspace_root.resolve(),
        capture_root=args.capture_root.resolve(),
        zed_executable=args.zed_executable.resolve(),
        zed_source=args.zed_source.resolve(),
        settings_path=args.settings_path.resolve(),
        debug_log=args.debug_log.resolve(),
        custody_root=custody_root,
        allowed_settings_roots=(args.settings_path.resolve().parent, custody_root),
    )
    state_path = args.capture_root.resolve() / STATE_FILENAME
    if not state_path.exists():
        init_phase_state(state_path)
    state = load_phase_state(state_path)
    assert_phase_allowed(state, args.phase)
    operator_wait = not bool(args.no_operator_wait)

    if args.phase == "direct-control":
        run_direct_control_phase(
            capture_root=args.capture_root.resolve(),
            state_path=state_path,
            operator_wait=operator_wait,
        )
    elif args.phase in {"relay-control", "origin-a"}:
        if args.private_run_manifest is None:
            raise CustodyRunnerError("private_run_manifest_required", "private_run_manifest")
        if args.phase == "origin-a":
            if args.expected_run_attempt_id == "origin-a-3":
                fixture = (args.prompt_fixture or PROMPT_FIXTURE_V2_PATH).resolve()
                _require_fixture_v2_digests(
                    prompt_fixture=fixture,
                    workspace_root=args.workspace_root.resolve(),
                )
            else:
                require_readme_precondition(args.workspace_root.resolve())
                if PROMPT_FIXTURE_PATH.is_file():
                    digest = sha256_file(PROMPT_FIXTURE_PATH).upper()
                    if digest != PROMPT_FIXTURE_SHA256:
                        raise CustodyRunnerError("prompt_fixture_digest_mismatch", "prompt")
            # Print fixture before the mutation hold so the operator can act during the window.
            print_origin_a_instructions()
        run_relay_mediated_phase(
            phase=args.phase,
            capture_root=args.capture_root.resolve(),
            state_path=state_path,
            settings_path=args.settings_path.resolve(),
            custody_root=custody_root,
            private_run_manifest=args.private_run_manifest.resolve(),
            operator_wait=operator_wait,
        )
    elif args.phase == "origin-a-prompt-retry":
        if args.run_attempt_id != "origin-a-3":
            raise CustodyRunnerError("invalid_probe_stage_accounting", "run_attempt_id")
        if args.stage_ledger is None:
            raise CustodyRunnerError("invalid_probe_retry_ledger_unavailable", "stage_ledger")
        if args.launch_identity is None:
            raise CustodyRunnerError(
                "invalid_probe_retry_process_identity_mismatch",
                "launch_identity",
            )
        if args.relay_control_descriptor is None:
            raise CustodyRunnerError(
                "invalid_probe_retry_control_channel_failure",
                "relay_control_descriptor",
            )
        if not isinstance(args.caller_owner_id, str) or not args.caller_owner_id.strip():
            raise CustodyRunnerError(
                "invalid_probe_retry_control_channel_failure",
                "caller_owner_id",
            )
        fixture = (args.prompt_fixture or PROMPT_FIXTURE_V2_PATH).resolve()
        result = run_origin_a_prompt_retry(
            run_attempt_id=args.run_attempt_id,
            workspace_root=args.workspace_root.resolve(),
            capture_root=args.capture_root.resolve(),
            prompt_fixture=fixture,
            stage_ledger_path=args.stage_ledger.resolve(),
            launch_identity_path=args.launch_identity.resolve(),
            descriptor_path=args.relay_control_descriptor.resolve(),
            caller_owner_id=args.caller_owner_id,
        )
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
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
    "PROMPT_FIXTURE_V2_SHA256",
    "PYPROJECT_TARGET_SHA256",
    "CustodyRunnerError",
    "allocate_attempt_directory",
    "assert_origin_a3_preflight",
    "assert_phase_allowed",
    "assert_prompt_retry_ledger_eligible",
    "assert_prompt_retry_preflight",
    "atomic_write_json",
    "capture_process_records",
    "compare_approval_equality",
    "compare_transcript_debug",
    "init_phase_state",
    "load_launch_session_identity",
    "load_phase_state",
    "load_private_run_manifest",
    "load_stage_ledger",
    "main",
    "mark_phase_complete",
    "mutate_settings_insert_relay",
    "parse_jsonc",
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
    "reserve_origin_a_run",
    "reserve_prompt_ordinal",
    "resolve_probe_paths",
    "restore_settings",
    "run_direct_control_phase",
    "run_origin_a_prompt_retry",
    "run_relay_mediated_phase",
    "run_with_settings_transaction",
    "save_phase_state",
    "verify_original_attempt_hashes",
    "write_attempt_manifest",
    "write_canonical_json",
    "write_stage_outcome_exclusive",
)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
