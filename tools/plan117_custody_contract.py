"""Plan 11.7 server-side custody feasibility contract: schemas, hashing, reducer."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_ARTIFACT_MANIFEST = "plan117-custody-artifact-manifest-v1"
SCHEMA_VERIFIER_SUMMARY = "plan117-custody-verifier-summary-v1"
SCHEMA_CUSTODY_STATE = "plan117-custody-state-v1"
SCHEMA_SETTINGS_TRANSACTION = "plan117-custody-settings-transaction-v1"
SCHEMA_APPROVAL_EQUIVALENCE = "plan117-custody-approval-equivalence-v1"
SCHEMA_PROCESS_RECORD = "plan117-custody-process-record-v1"
SCHEMA_TRANSCRIPT_PROJECTION = "plan117-custody-transcript-projection-v1"
SCHEMA_ATTEMPT_MANIFEST = "plan117-custody-attempt-manifest-v1"
SCHEMA_STAGE_ATTEMPT_RECORD = "plan117-custody-stage-attempt-record-v1"
SCHEMA_SUPPLEMENTAL_FACT_RECORD = "plan117-custody-supplemental-fact-record-v1"
SCHEMA_STAGE_LEDGER = "plan117-custody-stage-ledger-v1"
SCHEMA_RUN_RESERVATION = "plan117-custody-run-reservation-v1"
ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256 = (
    "5BB327D88761AE329869B90866839D03F61EFF6AF0E5AE47F8D3D7551F849A4D"
)
MAX_ATTEMPTS_PER_KIND = 3
MAX_CORRELATION_ORDINAL_UNDER_AMENDMENT = 3
MAX_PROMPT_ORDINAL_UNDER_AMENDMENT = 3
HASH_CHUNK_SIZE = 1 << 20  # 1 MiB
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PRESUMPTIVE_INELIGIBLE_TOKENS = frozenset(
    {"workspace", "cwd", "recency", "pid", "title", "prompt"}
)
_PARTIAL_CHECKPOINTS = frozenset({"task4", "task5"})
_JSON_HASH_METHODS = frozenset({"raw_file_sha256"})
_SUPPORTED_SUPERSESSION_REASON_CODES = frozenset(
    {
        "invalid_probe_relay_capture_tooling_failure",
        "invalid_probe_origin_attempt_original_mismatch",
        "invalid_probe_attempt_supersession_chain",
        "invalid_probe_stage_accounting",
        "invalid_probe_retry_budget_exhausted",
        "invalid_probe_fixture_identity_mismatch",
        "invalid_probe_execution_identity_mismatch",
        "invalid_probe_jsonc_settings_safety",
        "blocked_probe_same_session_prompt_retry_unavailable",
        "blocked_probe_gateway_usage_cost_unavailable",
        "invalid_probe_retry_ledger_unavailable",
        "invalid_probe_retry_proof_unavailable",
        "invalid_probe_retry_process_identity_mismatch",
        "invalid_probe_retry_connection_identity_mismatch",
        "invalid_probe_retry_acp_session_identity_mismatch",
        "invalid_probe_retry_control_channel_failure",
        "invalid_probe_retry_second_prompt_failure",
        "AMBIGUOUS_WORKSPACE_REFERENCE",
        "REQUIRED_WORKSPACE_FILE_TOO_LARGE",
        "stop_probe_zed_client_crashed",
        "gateway_timeout",
        "transient_capture",
    }
)


class CustodyContractError(ValueError):
    """Fail-closed contract/verification error with a safe reason code."""

    def __init__(self, reason_code: str, field_path: str = "") -> None:
        self.reason_code = reason_code
        self.field_path = field_path
        super().__init__(reason_code)


class ProbeDisposition(StrEnum):
    INVALID_TRIGGER_CHAIN = "invalid_probe_trigger_chain_mismatch"
    INVALID_TARGET_IDENTITY = "invalid_probe_target_identity_mismatch"
    INVALID_RELAY_ENVIRONMENT = "invalid_probe_relay_environment_mismatch"
    INVALID_SETTINGS_RESTORE = "invalid_probe_settings_not_restored"
    INVALID_NON_ZED_TRAFFIC = "invalid_probe_non_zed_client_or_injected_traffic"
    INVALID_PROCESS_CUSTODY = "invalid_probe_process_custody_ambiguous"
    INVALID_TRANSCRIPT_DEBUG = "invalid_probe_transcript_debug_divergence"
    INVALID_CORRELATION_INVENTORY = "invalid_probe_correlation_inventory_incomplete"
    INVALID_REDACTION_SEAL = "invalid_probe_redaction_or_seal_failure"
    ZED_CLIENT_CRASHED = "stop_probe_zed_client_crashed"
    POST_NEW_PROMPT_UNAVAILABLE = "blocked_probe_post_new_prompt_unavailable"
    DEPENDENCY_UNAVAILABLE = "blocked_probe_dependency_unavailable"
    INFEASIBLE = "infeasible_for_production_target"
    FEASIBLE_CANDIDATE = "feasible_server_side_custody_candidate"


class AttemptKind(StrEnum):
    CORRELATION_CAPTURE = "correlation_capture"
    POST_NEW_PROMPT = "post_new_prompt"


class FailureClass(StrEnum):
    NONE = "none"
    TRANSIENT = "transient"
    PERMANENT = "permanent"


class StageKind(StrEnum):
    CORRELATION_CAPTURE = "correlation_capture"
    POST_NEW_PROMPT = "post_new_prompt"


class StageStatus(StrEnum):
    NOT_STARTED = "not_started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class EvidenceReference:
    relative_path: str
    sha256: str
    hash_method: str


@dataclass(frozen=True)
class StageAttemptRecord:
    record_id: str
    run_attempt_id: str
    stage: StageKind
    ordinal: int
    status: StageStatus
    failure_class: FailureClass
    reason_code: str | None
    evidence: tuple[EvidenceReference, ...]
    supersedes_record_id: str | None
    supersedes_sha256: str | None
    amendment_sha256: str
    created_by: str
    created_utc: str


@dataclass(frozen=True)
class SupplementalFactRecord:
    record_id: str
    run_attempt_id: str
    fact_kind: str
    reason_code: str
    evidence: tuple[EvidenceReference, ...]
    supersedes_record_id: str | None
    supersedes_sha256: str | None
    amendment_sha256: str
    created_by: str
    created_utc: str


@dataclass(frozen=True)
class StageLedger:
    terminal_records: tuple[StageAttemptRecord, ...]
    next_correlation_ordinal: int
    next_prompt_ordinal: int


@dataclass(frozen=True)
class LaunchSessionIdentity:
    run_attempt_id: str
    zed_pid: int
    zed_process_start_time_utc: str
    connection_id: str
    acp_session_id: str


@dataclass(frozen=True)
class LiveSessionProof:
    run_attempt_id: str
    zed_pid: int
    zed_process_start_time_utc: str
    connection_id: str
    acp_session_id: str
    zed_alive: bool
    relay_alive: bool
    acp_session_observed: bool
    captured_utc: str
    evidence: tuple[EvidenceReference, ...]
    proof_sha256: str


@dataclass(frozen=True)
class RetryPreflightResult:
    run_attempt_id: str
    prompt_ordinal: int
    prompt_fixture_sha256: str
    target_sha256: str
    live_session_proof_sha256: str
    settings_mutated: bool
    zed_launched: bool


@dataclass(frozen=True)
class AttemptRecord:
    attempt_id: str
    phase: str
    kind: AttemptKind
    ordinal: int
    failure_class: FailureClass
    reason_code: str | None
    manifest_sha256: str


@dataclass(frozen=True)
class CorrelationSignal:
    field_path: str
    origin: str
    available_before_new_decision: bool
    a_sha256: str | None
    b_sha256: str | None
    c_sha256: str | None
    restart_stable: bool
    fresh_thread_distinct: bool
    thread_specific: bool
    trust_compatible: bool
    protocol_honest: bool
    safely_persistable: bool
    independently_falsifiable: bool
    ancestry_derived: bool
    eligible: bool
    reason_code: str


@dataclass(frozen=True)
class VerificationResult:
    disposition: ProbeDisposition
    reason_codes: Sequence[str]
    verified_artifact_count: int


def _require_lowercase_sha256(value: object, *, field_path: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise CustodyContractError("sha256_not_lowercase", field_path)
    return value


def sha256_hex_equal(left: str, right: str) -> bool:
    """Case-insensitive equality for pinned SHA-256 digests."""
    return left.lower() == right.lower()


def derive_restart_stable(a_sha256: str | None, b_sha256: str | None) -> bool:
    return a_sha256 is not None and a_sha256 == b_sha256


def derive_fresh_thread_distinct(b_sha256: str | None, c_sha256: str | None) -> bool:
    return c_sha256 is None or c_sha256 != b_sha256


def field_path_presumptively_ineligible(field_path: str) -> bool:
    tokens = {part.lower() for part in re.split(r"[./_\-]", field_path) if part}
    return bool(tokens.intersection(_PRESUMPTIVE_INELIGIBLE_TOKENS))


def compute_eligible(
    *,
    available_before_new_decision: bool,
    thread_specific: bool,
    restart_stable: bool,
    fresh_thread_distinct: bool,
    protocol_honest: bool,
    trust_compatible: bool,
    safely_persistable: bool,
    independently_falsifiable: bool,
    ancestry_derived: bool,
    ancestry_revalidated: bool = False,
) -> bool:
    rules = (
        available_before_new_decision
        and thread_specific
        and restart_stable
        and fresh_thread_distinct
        and protocol_honest
        and trust_compatible
        and safely_persistable
        and independently_falsifiable
    )
    if not rules:
        return False
    if ancestry_derived and not ancestry_revalidated:
        return False
    return True


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AttemptRecordModel(_StrictModel):
    attempt_id: str
    phase: str
    kind: AttemptKind
    ordinal: int = Field(ge=1)
    failure_class: FailureClass
    reason_code: str | None = None
    manifest_sha256: str

    @field_validator("manifest_sha256")
    @classmethod
    def _lowercase_sha(cls, value: str) -> str:
        return _require_lowercase_sha256(value, field_path="attempts.manifest_sha256")

    def to_record(self) -> AttemptRecord:
        return AttemptRecord(
            attempt_id=self.attempt_id,
            phase=self.phase,
            kind=self.kind,
            ordinal=self.ordinal,
            failure_class=self.failure_class,
            reason_code=self.reason_code,
            manifest_sha256=self.manifest_sha256,
        )


class CorrelationSignalModel(_StrictModel):
    field_path: str
    origin: str
    available_before_new_decision: bool
    a_sha256: str | None = None
    b_sha256: str | None = None
    c_sha256: str | None = None
    restart_stable: bool
    fresh_thread_distinct: bool
    thread_specific: bool
    trust_compatible: bool
    protocol_honest: bool
    safely_persistable: bool
    independently_falsifiable: bool
    ancestry_derived: bool
    eligible: bool
    reason_code: str

    @field_validator("a_sha256", "b_sha256", "c_sha256")
    @classmethod
    def _optional_lowercase_sha(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_lowercase_sha256(value, field_path="correlation_signals.sha256")

    def to_verified_signal(
        self, *, revalidated_field_paths: frozenset[str]
    ) -> CorrelationSignal:
        restart_stable = derive_restart_stable(self.a_sha256, self.b_sha256)
        fresh_thread_distinct = derive_fresh_thread_distinct(self.b_sha256, self.c_sha256)
        if self.restart_stable != restart_stable:
            raise CustodyContractError(
                "restart_stable_mismatch",
                f"correlation_signals.{self.field_path}.restart_stable",
            )
        if self.fresh_thread_distinct != fresh_thread_distinct:
            raise CustodyContractError(
                "fresh_thread_distinct_mismatch",
                f"correlation_signals.{self.field_path}.fresh_thread_distinct",
            )
        ancestry_revalidated = self.field_path in revalidated_field_paths
        eligible = compute_eligible(
            available_before_new_decision=self.available_before_new_decision,
            thread_specific=self.thread_specific,
            restart_stable=restart_stable,
            fresh_thread_distinct=fresh_thread_distinct,
            protocol_honest=self.protocol_honest,
            trust_compatible=self.trust_compatible,
            safely_persistable=self.safely_persistable,
            independently_falsifiable=self.independently_falsifiable,
            ancestry_derived=self.ancestry_derived,
            ancestry_revalidated=ancestry_revalidated,
        )
        if field_path_presumptively_ineligible(self.field_path):
            eligible = False
        if self.eligible != eligible:
            raise CustodyContractError(
                "eligible_mismatch",
                f"correlation_signals.{self.field_path}.eligible",
            )
        return CorrelationSignal(
            field_path=self.field_path,
            origin=self.origin,
            available_before_new_decision=self.available_before_new_decision,
            a_sha256=self.a_sha256,
            b_sha256=self.b_sha256,
            c_sha256=self.c_sha256,
            restart_stable=restart_stable,
            fresh_thread_distinct=fresh_thread_distinct,
            thread_specific=self.thread_specific,
            trust_compatible=self.trust_compatible,
            protocol_honest=self.protocol_honest,
            safely_persistable=self.safely_persistable,
            independently_falsifiable=self.independently_falsifiable,
            ancestry_derived=self.ancestry_derived,
            eligible=eligible,
            reason_code=self.reason_code,
        )


class ReducerInput(_StrictModel):
    trigger_chain_mismatch: bool
    target_identity_mismatch: bool
    relay_environment_mismatch: bool
    settings_not_restored: bool
    non_zed_or_injected_traffic: bool
    process_custody_ambiguous: bool
    transcript_debug_divergence: bool
    correlation_inventory_incomplete: bool
    redaction_or_seal_failure: bool
    zed_client_crashed: bool
    post_new_prompt_unavailable: bool
    dependency_unavailable: bool
    inventory_complete: bool
    has_eligible_signal: bool
    valid_b_continuation: bool
    valid_completed_c_control: bool
    message_binding_ok: bool
    ancestry_revalidation_ok: bool


class ArtifactEntryModel(_StrictModel):
    locator: str
    sha256: str | None = None
    role: str
    hash_method: str

    @field_validator("sha256")
    @classmethod
    def _optional_lowercase_sha(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_lowercase_sha256(value, field_path="artifacts.sha256")


class ArtifactManifestModel(_StrictModel):
    schema_name: Literal["plan117-custody-artifact-manifest-v1"] = Field(alias="schema")
    checkpoint: Literal["task0", "task4", "task5", "final"]
    complete: bool
    report_root: str
    custody_root: str
    artifacts: list[ArtifactEntryModel]
    attempts: list[AttemptRecordModel] = Field(default_factory=list)
    correlation_signals: list[CorrelationSignalModel] = Field(default_factory=list)
    direct_revalidation_field_paths: list[str] = Field(default_factory=list)
    reducer: ReducerInput | None = None
    declared_disposition: ProbeDisposition | None = None
    settings_restored: bool | None = None
    redaction_sealed: bool | None = None
    document_audit_present: bool | None = None
    valid_session_new_captured: bool | None = None
    reason_codes: list[str] = Field(default_factory=list)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write raw bytes via temp sibling + os.replace + fsync."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.partial-{uuid.uuid4().hex}")
    try:
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        raise ValueError("atomic_write_failed") from None


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write canonical UTF-8 LF JSON via temp sibling + os.replace + fsync."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.partial-{uuid.uuid4().hex}")
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        raise ValueError("atomic_write_failed") from None


def write_canonical_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Public alias for :func:`atomic_write_json`."""
    atomic_write_json(path, payload)


def atomic_create_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Create-only canonical UTF-8 LF JSON; fails closed if the path already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    data = encoded.encode("utf-8")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        fd = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise CustodyContractError("reservation_already_exists", str(path)) from exc
    except OSError as exc:
        if getattr(exc, "errno", None) in {17, 183}:  # EEXIST (posix / win)
            raise CustodyContractError("reservation_already_exists", str(path)) from exc
        raise ValueError("atomic_create_failed") from None
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        if path.exists():
            path.unlink(missing_ok=True)
        raise ValueError("atomic_create_failed") from None
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _evidence_to_canonical(evidence: Sequence[EvidenceReference]) -> list[dict[str, str]]:
    return [
        {
            "hash_method": item.hash_method,
            "relative_path": item.relative_path,
            "sha256": item.sha256.lower(),
        }
        for item in evidence
    ]


def stage_attempt_record_payload(record: StageAttemptRecord) -> dict[str, Any]:
    """Canonical JSON-object form of a stage attempt record (sorted keys via dumps)."""
    return {
        "amendment_sha256": record.amendment_sha256.lower(),
        "created_by": record.created_by,
        "created_utc": record.created_utc,
        "evidence": _evidence_to_canonical(record.evidence),
        "failure_class": record.failure_class.value,
        "ordinal": record.ordinal,
        "reason_code": record.reason_code,
        "record_id": record.record_id,
        "run_attempt_id": record.run_attempt_id,
        "stage": record.stage.value,
        "status": record.status.value,
        "supersedes_record_id": record.supersedes_record_id,
        "supersedes_sha256": (
            None if record.supersedes_sha256 is None else record.supersedes_sha256.lower()
        ),
    }


def stage_attempt_record_sha256(record: StageAttemptRecord) -> str:
    """Raw-byte SHA-256 of the canonical LF JSON serialization of a stage record."""
    payload = stage_attempt_record_payload(record)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def verify_supersession_chain(records: Sequence[StageAttemptRecord]) -> None:
    """Fail closed on cycles, forks, missing/mismatched parents, bad digests, or reasons."""
    by_id: dict[str, StageAttemptRecord] = {}
    for record in records:
        if record.record_id in by_id:
            raise CustodyContractError(
                "invalid_probe_attempt_supersession_chain",
                f"duplicate_record_id:{record.record_id}",
            )
        by_id[record.record_id] = record

    children_by_parent: dict[str, list[str]] = {}
    for record in records:
        if not sha256_hex_equal(record.amendment_sha256, ORIGIN_A_FIXTURE_V2_AMENDMENT_SHA256):
            raise CustodyContractError(
                "invalid_probe_attempt_supersession_chain",
                f"{record.record_id}.amendment_sha256",
            )
        if record.supersedes_record_id is None:
            if record.supersedes_sha256 is not None:
                raise CustodyContractError(
                    "invalid_probe_attempt_supersession_chain",
                    f"{record.record_id}.supersedes_sha256",
                )
            continue
        if record.supersedes_sha256 is None or not _SHA256_RE.fullmatch(
            record.supersedes_sha256.lower()
        ):
            raise CustodyContractError(
                "invalid_probe_attempt_supersession_chain",
                f"{record.record_id}.supersedes_sha256",
            )
        if (
            record.reason_code is not None
            and record.reason_code not in _SUPPORTED_SUPERSESSION_REASON_CODES
        ):
            raise CustodyContractError(
                "invalid_probe_attempt_supersession_chain",
                f"{record.record_id}.reason_code",
            )
        parent_id = record.supersedes_record_id
        children_by_parent.setdefault(parent_id, []).append(record.record_id)
        parent = by_id.get(parent_id)
        if parent is not None:
            expected = stage_attempt_record_sha256(parent)
            if not sha256_hex_equal(expected, record.supersedes_sha256):
                raise CustodyContractError(
                    "invalid_probe_attempt_supersession_chain",
                    f"{record.record_id}.supersedes_sha256",
                )

    for parent_id, child_ids in children_by_parent.items():
        if len(child_ids) > 1:
            raise CustodyContractError(
                "invalid_probe_attempt_supersession_chain",
                f"fork:{parent_id}",
            )

    # Cycle detection among in-set supersession edges only.
    for start in by_id:
        seen: set[str] = set()
        current: str | None = start
        while current is not None:
            if current in seen:
                raise CustodyContractError(
                    "invalid_probe_attempt_supersession_chain",
                    f"cycle:{current}",
                )
            seen.add(current)
            node = by_id.get(current)
            if node is None or node.supersedes_record_id is None:
                break
            nxt = node.supersedes_record_id
            if nxt not in by_id:
                break
            current = nxt


def normalize_stage_ledger(records: Sequence[StageAttemptRecord]) -> StageLedger:
    """Derive terminal stage outcomes and next ordinals; fail closed on accounting defects."""
    verify_supersession_chain(records)
    superseded_ids = {
        record.supersedes_record_id
        for record in records
        if record.supersedes_record_id is not None
        and any(item.record_id == record.supersedes_record_id for item in records)
    }
    terminals: list[StageAttemptRecord] = []
    for record in records:
        if record.record_id in superseded_ids:
            continue
        if record.status is StageStatus.SUPERSEDED:
            continue
        if record.status is StageStatus.NOT_STARTED:
            continue
        terminals.append(record)

    by_stage_ordinal: dict[tuple[StageKind, int], StageAttemptRecord] = {}
    for record in terminals:
        if record.ordinal < 1:
            raise CustodyContractError("invalid_probe_stage_accounting", "ordinal")
        key = (record.stage, record.ordinal)
        if key in by_stage_ordinal:
            raise CustodyContractError(
                "invalid_probe_stage_accounting",
                f"duplicate_terminal:{record.stage.value}:{record.ordinal}",
            )
        by_stage_ordinal[key] = record

    for stage in (StageKind.CORRELATION_CAPTURE, StageKind.POST_NEW_PROMPT):
        ordinals = sorted(ord for (stg, ord) in by_stage_ordinal if stg is stage)
        if not ordinals:
            continue
        expected = list(range(1, max(ordinals) + 1))
        if ordinals != expected:
            raise CustodyContractError(
                "invalid_probe_stage_accounting",
                f"ordinal_gap:{stage.value}",
            )
        max_allowed = (
            MAX_CORRELATION_ORDINAL_UNDER_AMENDMENT
            if stage is StageKind.CORRELATION_CAPTURE
            else MAX_PROMPT_ORDINAL_UNDER_AMENDMENT
        )
        if max(ordinals) > max_allowed:
            raise CustodyContractError(
                "invalid_probe_retry_budget_exhausted",
                stage.value,
            )

    for record in terminals:
        if (
            record.run_attempt_id == "origin-a-3"
            and record.stage is StageKind.CORRELATION_CAPTURE
            and record.ordinal != 3
        ):
            raise CustodyContractError(
                "invalid_probe_stage_accounting",
                "origin-a-3.correlation_ordinal",
            )

    corr_ordinals = [
        record.ordinal
        for record in terminals
        if record.stage is StageKind.CORRELATION_CAPTURE
    ]
    prompt_ordinals = [
        record.ordinal for record in terminals if record.stage is StageKind.POST_NEW_PROMPT
    ]
    next_corr = (max(corr_ordinals) + 1) if corr_ordinals else 1
    next_prompt = (max(prompt_ordinals) + 1) if prompt_ordinals else 1
    ordered = tuple(
        sorted(
            terminals,
            key=lambda item: (item.stage.value, item.ordinal, item.record_id),
        )
    )
    return StageLedger(
        terminal_records=ordered,
        next_correlation_ordinal=next_corr,
        next_prompt_ordinal=next_prompt,
    )


def next_stage_ordinal(ledger: StageLedger, stage: StageKind) -> int:
    """Return the next free ordinal for ``stage`` from a normalized ledger."""
    if stage is StageKind.CORRELATION_CAPTURE:
        return ledger.next_correlation_ordinal
    if stage is StageKind.POST_NEW_PROMPT:
        return ledger.next_prompt_ordinal
    raise CustodyContractError("invalid_probe_stage_accounting", "stage")


def _require_nonempty_str(value: object, *, field_path: str, reason_code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CustodyContractError(reason_code, field_path)
    return value


def live_session_proof_payload(proof: LiveSessionProof) -> dict[str, Any]:
    """Canonical safe-field payload for digest binding (excludes proof_sha256)."""
    return {
        "acp_session_id": proof.acp_session_id,
        "acp_session_observed": proof.acp_session_observed,
        "captured_utc": proof.captured_utc,
        "connection_id": proof.connection_id,
        "evidence": _evidence_to_canonical(proof.evidence),
        "relay_alive": proof.relay_alive,
        "run_attempt_id": proof.run_attempt_id,
        "zed_alive": proof.zed_alive,
        "zed_pid": proof.zed_pid,
        "zed_process_start_time_utc": proof.zed_process_start_time_utc,
    }


def live_session_proof_sha256(proof: LiveSessionProof) -> str:
    """SHA-256 over canonical live-session proof bytes."""
    payload = live_session_proof_payload(proof)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_live_session_proof(
    *,
    run_attempt_id: str,
    zed_pid: int,
    zed_process_start_time_utc: str,
    connection_id: str,
    acp_session_id: str,
    zed_alive: bool,
    relay_alive: bool,
    acp_session_observed: bool,
    captured_utc: str,
    evidence: Sequence[EvidenceReference],
) -> LiveSessionProof:
    """Build an immutable proof with digest bound to safe normalized fields."""
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)) or len(evidence) < 1:
        raise CustodyContractError("invalid_probe_retry_proof_unavailable", "evidence")
    if not isinstance(zed_pid, int) or isinstance(zed_pid, bool) or zed_pid <= 0:
        raise CustodyContractError("invalid_probe_retry_proof_unavailable", "zed_pid")
    run_id = _require_nonempty_str(
        run_attempt_id,
        field_path="run_attempt_id",
        reason_code="invalid_probe_retry_proof_unavailable",
    )
    start_utc = _require_nonempty_str(
        zed_process_start_time_utc,
        field_path="zed_process_start_time_utc",
        reason_code="invalid_probe_retry_proof_unavailable",
    )
    conn_id = _require_nonempty_str(
        connection_id,
        field_path="connection_id",
        reason_code="invalid_probe_retry_proof_unavailable",
    )
    session_id = _require_nonempty_str(
        acp_session_id,
        field_path="acp_session_id",
        reason_code="invalid_probe_retry_proof_unavailable",
    )
    captured = _require_nonempty_str(
        captured_utc,
        field_path="captured_utc",
        reason_code="invalid_probe_retry_proof_unavailable",
    )
    for index, item in enumerate(evidence):
        if not isinstance(item, EvidenceReference):
            raise CustodyContractError("invalid_probe_retry_proof_unavailable", f"evidence[{index}]")
        _require_lowercase_sha256(item.sha256.lower(), field_path=f"evidence[{index}].sha256")
        if item.hash_method not in _JSON_HASH_METHODS:
            raise CustodyContractError(
                "invalid_probe_retry_proof_unavailable",
                f"evidence[{index}].hash_method",
            )
        _require_nonempty_str(
            item.relative_path,
            field_path=f"evidence[{index}].relative_path",
            reason_code="invalid_probe_retry_proof_unavailable",
        )
    normalized_evidence = tuple(
        EvidenceReference(
            relative_path=item.relative_path,
            sha256=item.sha256.lower(),
            hash_method=item.hash_method,
        )
        for item in evidence
    )
    provisional = LiveSessionProof(
        run_attempt_id=run_id,
        zed_pid=zed_pid,
        zed_process_start_time_utc=start_utc,
        connection_id=conn_id,
        acp_session_id=session_id,
        zed_alive=bool(zed_alive),
        relay_alive=bool(relay_alive),
        acp_session_observed=bool(acp_session_observed),
        captured_utc=captured,
        evidence=normalized_evidence,
        proof_sha256="0" * 64,
    )
    digest = live_session_proof_sha256(provisional)
    return LiveSessionProof(
        run_attempt_id=provisional.run_attempt_id,
        zed_pid=provisional.zed_pid,
        zed_process_start_time_utc=provisional.zed_process_start_time_utc,
        connection_id=provisional.connection_id,
        acp_session_id=provisional.acp_session_id,
        zed_alive=provisional.zed_alive,
        relay_alive=provisional.relay_alive,
        acp_session_observed=provisional.acp_session_observed,
        captured_utc=provisional.captured_utc,
        evidence=provisional.evidence,
        proof_sha256=digest,
    )


def validate_live_session_proof(
    proof: LiveSessionProof,
    *,
    expected: LaunchSessionIdentity,
) -> None:
    """Fail closed when proof identity/liveness disagrees with launch records."""
    if not isinstance(proof, LiveSessionProof):
        raise CustodyContractError("invalid_probe_retry_proof_unavailable", "live_session_proof")
    if not proof.evidence:
        raise CustodyContractError("invalid_probe_retry_proof_unavailable", "evidence")
    recomputed = live_session_proof_sha256(proof)
    if not sha256_hex_equal(recomputed, proof.proof_sha256):
        raise CustodyContractError("invalid_probe_retry_proof_unavailable", "proof_sha256")
    if proof.run_attempt_id != expected.run_attempt_id:
        raise CustodyContractError(
            "invalid_probe_retry_process_identity_mismatch",
            "run_attempt_id",
        )
    if proof.zed_pid != expected.zed_pid or not proof.zed_alive:
        raise CustodyContractError(
            "invalid_probe_retry_process_identity_mismatch",
            "zed_process_identity",
        )
    if proof.zed_process_start_time_utc != expected.zed_process_start_time_utc:
        raise CustodyContractError(
            "invalid_probe_retry_process_identity_mismatch",
            "zed_process_start_time_utc",
        )
    if not proof.relay_alive or proof.connection_id != expected.connection_id:
        raise CustodyContractError(
            "invalid_probe_retry_connection_identity_mismatch",
            "connection_id",
        )
    if not proof.acp_session_observed or proof.acp_session_id != expected.acp_session_id:
        raise CustodyContractError(
            "invalid_probe_retry_acp_session_identity_mismatch",
            "acp_session_id",
        )


def evaluate_prompt_retry_preflight(
    *,
    run_attempt_id: str,
    ledger: StageLedger,
    prompt_fixture_sha256: str,
    expected_prompt_fixture_sha256: str,
    target_sha256: str,
    expected_target_sha256: str,
    live_session_proof: LiveSessionProof | None,
    launch_identity: LaunchSessionIdentity,
) -> RetryPreflightResult:
    """Pure fail-closed eligibility check for the one same-session prompt retry."""
    if run_attempt_id != "origin-a-3":
        raise CustodyContractError("invalid_probe_stage_accounting", "run_attempt_id")
    if launch_identity.run_attempt_id != "origin-a-3":
        raise CustodyContractError("invalid_probe_stage_accounting", "launch_identity.run_attempt_id")
    if not isinstance(ledger, StageLedger):
        raise CustodyContractError("invalid_probe_retry_ledger_unavailable", "ledger")
    if ledger.next_correlation_ordinal > MAX_CORRELATION_ORDINAL_UNDER_AMENDMENT + 1:
        raise CustodyContractError("invalid_probe_retry_budget_exhausted", "correlation_ordinal")
    if ledger.next_correlation_ordinal != MAX_CORRELATION_ORDINAL_UNDER_AMENDMENT + 1:
        # Retry must not allocate a new correlation launch (ordinal 4).
        raise CustodyContractError("invalid_probe_stage_accounting", "correlation_missing")

    corr = [
        record
        for record in ledger.terminal_records
        if record.run_attempt_id == "origin-a-3"
        and record.stage is StageKind.CORRELATION_CAPTURE
        and record.status is StageStatus.SUCCEEDED
        and record.ordinal == 3
    ]
    if not corr:
        raise CustodyContractError("invalid_probe_stage_accounting", "correlation_missing")

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
        raise CustodyContractError("invalid_probe_stage_accounting", "prompt_ordinal_2")

    if ledger.next_prompt_ordinal != 3:
        raise CustodyContractError("invalid_probe_retry_budget_exhausted", "prompt_ordinal")

    if not sha256_hex_equal(prompt_fixture_sha256, expected_prompt_fixture_sha256):
        raise CustodyContractError("invalid_probe_fixture_identity_mismatch", "prompt_fixture")
    if not sha256_hex_equal(target_sha256, expected_target_sha256):
        raise CustodyContractError("invalid_probe_fixture_identity_mismatch", "target")

    if live_session_proof is None:
        raise CustodyContractError(
            "blocked_probe_same_session_prompt_retry_unavailable",
            "live_session_proof",
        )
    if live_session_proof.run_attempt_id != "origin-a-3":
        raise CustodyContractError("invalid_probe_stage_accounting", "live_session_proof.run_attempt_id")
    validate_live_session_proof(live_session_proof, expected=launch_identity)

    return RetryPreflightResult(
        run_attempt_id="origin-a-3",
        prompt_ordinal=3,
        prompt_fixture_sha256=prompt_fixture_sha256.lower(),
        target_sha256=target_sha256.lower(),
        live_session_proof_sha256=live_session_proof.proof_sha256.lower(),
        settings_mutated=False,
        zed_launched=False,
    )


def sha256_file(path: Path) -> str:
    """Stream a regular file in 1 MiB chunks; reject symlinks."""
    if path.is_symlink():
        raise ValueError("symlink_forbidden")
    if not path.is_file():
        raise ValueError("regular_file_required")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def validate_attempt_budgets(attempts: Sequence[AttemptRecord]) -> None:
    """Enforce independent 3-attempt budgets and permanent-failure stop."""
    by_kind: dict[AttemptKind, list[AttemptRecord]] = {
        AttemptKind.CORRELATION_CAPTURE: [],
        AttemptKind.POST_NEW_PROMPT: [],
    }
    for attempt in attempts:
        by_kind[attempt.kind].append(attempt)

    for _kind, records in by_kind.items():
        ordered = sorted(records, key=lambda item: item.ordinal)
        if len(ordered) > MAX_ATTEMPTS_PER_KIND:
            raise ValueError("attempt_budget_exceeded")
        seen_permanent = False
        for record in ordered:
            if seen_permanent:
                raise ValueError("permanent_failure_must_stop")
            if record.failure_class is FailureClass.PERMANENT:
                seen_permanent = True


def reduce_disposition(flags: ReducerInput) -> ProbeDisposition:
    """Select the first true disposition predicate in ProbeDisposition order."""
    predicates: list[tuple[ProbeDisposition, bool]] = [
        (ProbeDisposition.INVALID_TRIGGER_CHAIN, flags.trigger_chain_mismatch),
        (ProbeDisposition.INVALID_TARGET_IDENTITY, flags.target_identity_mismatch),
        (ProbeDisposition.INVALID_RELAY_ENVIRONMENT, flags.relay_environment_mismatch),
        (ProbeDisposition.INVALID_SETTINGS_RESTORE, flags.settings_not_restored),
        (ProbeDisposition.INVALID_NON_ZED_TRAFFIC, flags.non_zed_or_injected_traffic),
        (ProbeDisposition.INVALID_PROCESS_CUSTODY, flags.process_custody_ambiguous),
        (ProbeDisposition.INVALID_TRANSCRIPT_DEBUG, flags.transcript_debug_divergence),
        (ProbeDisposition.INVALID_CORRELATION_INVENTORY, flags.correlation_inventory_incomplete),
        (ProbeDisposition.INVALID_REDACTION_SEAL, flags.redaction_or_seal_failure),
        (ProbeDisposition.ZED_CLIENT_CRASHED, flags.zed_client_crashed),
        (ProbeDisposition.POST_NEW_PROMPT_UNAVAILABLE, flags.post_new_prompt_unavailable),
        (ProbeDisposition.DEPENDENCY_UNAVAILABLE, flags.dependency_unavailable),
        (
            ProbeDisposition.INFEASIBLE,
            flags.inventory_complete and not flags.has_eligible_signal,
        ),
        (
            ProbeDisposition.FEASIBLE_CANDIDATE,
            flags.has_eligible_signal
            and flags.valid_b_continuation
            and flags.valid_completed_c_control
            and flags.message_binding_ok
            and flags.ancestry_revalidation_ok,
        ),
    ]
    for disposition, predicate in predicates:
        if predicate:
            return disposition
    raise ValueError("reducer_undetermined")


def resolve_contained_path(
    *,
    manifest_dir: Path,
    locator: str,
    report_root: Path,
    custody_root: Path,
) -> Path:
    candidate = (manifest_dir / locator).resolve()
    allowed = (report_root.resolve(), custody_root.resolve())
    for root in allowed:
        try:
            candidate.relative_to(root)
            return candidate
        except ValueError:
            continue
    raise CustodyContractError("path_outside_allowed_roots", "artifacts.locator")


def _reject_crlf(path: Path, *, field_path: str) -> None:
    data = path.read_bytes()
    if b"\r\n" in data:
        raise CustodyContractError("crlf_line_endings_forbidden", field_path)


def _load_manifest_payload(path: Path) -> dict[str, Any]:
    _reject_crlf(path, field_path="manifest")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CustodyContractError("invalid_manifest_json", "manifest") from exc
    if not isinstance(payload, dict):
        raise CustodyContractError("invalid_manifest_json", "manifest")
    return payload


def _parse_manifest(payload: dict[str, Any]) -> ArtifactManifestModel:
    try:
        return ArtifactManifestModel.model_validate(payload)
    except CustodyContractError:
        raise
    except Exception as exc:
        reason = "invalid_manifest_schema"
        message = str(exc)
        if "sha256_not_lowercase" in message or "sha256_not_lowercase" in repr(exc):
            reason = "sha256_not_lowercase"
        raise CustodyContractError(reason, "manifest") from exc


def verify_manifest(path: Path, *, checkpoint: str | None = None) -> VerificationResult:
    """Offline-only verification of a custody artifact manifest.

    Performs local file and hash checks only. No network, Redis, Gateway, keyring,
    settings mutation, process launch, or ambient credential access.
    """
    manifest_path = path.resolve()
    payload = _load_manifest_payload(manifest_path)
    manifest = _parse_manifest(payload)

    if checkpoint is None:
        if manifest.checkpoint != "final" or not manifest.complete:
            raise CustodyContractError("partial_manifest_requires_checkpoint", "checkpoint")
    else:
        if checkpoint not in _PARTIAL_CHECKPOINTS:
            raise CustodyContractError("unsupported_checkpoint", "checkpoint")
        if manifest.checkpoint != checkpoint:
            raise CustodyContractError("checkpoint_mismatch", "checkpoint")

    manifest_dir = manifest_path.parent
    report_root = (manifest_dir / manifest.report_root).resolve()
    custody_root = (manifest_dir / manifest.custody_root).resolve()

    verified = 0
    for index, artifact in enumerate(manifest.artifacts):
        field = f"artifacts[{index}]"
        if artifact.hash_method == "reviewer_owned_gitignored_not_hashed":
            if artifact.sha256 is not None:
                raise CustodyContractError("unexpected_digest", f"{field}.sha256")
            continue
        if (
            artifact.hash_method not in _JSON_HASH_METHODS
            and artifact.hash_method != "git_blob_sha256"
        ):
            raise CustodyContractError("unsupported_hash_method", f"{field}.hash_method")
        if artifact.sha256 is None:
            raise CustodyContractError("missing_digest", f"{field}.sha256")
        target = resolve_contained_path(
            manifest_dir=manifest_dir,
            locator=artifact.locator,
            report_root=report_root,
            custody_root=custody_root,
        )
        if not target.is_file() or target.is_symlink():
            raise CustodyContractError("artifact_missing_or_symlink", f"{field}.locator")
        if artifact.hash_method in _JSON_HASH_METHODS or target.suffix.lower() in {
            ".json",
            ".md",
            ".txt",
            ".ndjson",
        }:
            _reject_crlf(target, field_path=f"{field}.locator")
        # Task 1 unit fixtures use raw_file_sha256. git_blob_sha256 pins are compared
        # against on-disk bytes here; later live tasks may strengthen to `git show` blobs.
        actual = sha256_file(target)
        if not sha256_hex_equal(actual, artifact.sha256):
            raise CustodyContractError("artifact_digest_mismatch", f"{field}.sha256")
        verified += 1

    attempt_records = [item.to_record() for item in manifest.attempts]
    try:
        validate_attempt_budgets(attempt_records)
    except ValueError as exc:
        raise CustodyContractError(str(exc), "attempts") from exc

    revalidated = frozenset(manifest.direct_revalidation_field_paths)
    verified_signals: list[CorrelationSignal] = []
    for index, signal_model in enumerate(manifest.correlation_signals):
        try:
            verified_signals.append(
                signal_model.to_verified_signal(revalidated_field_paths=revalidated)
            )
        except CustodyContractError:
            raise
        except Exception as exc:
            raise CustodyContractError(
                "signal_recompute_mismatch", f"correlation_signals[{index}]"
            ) from exc

    if checkpoint == "task4":
        disposition = ProbeDisposition.INVALID_CORRELATION_INVENTORY
        if manifest.settings_restored is False:
            disposition = ProbeDisposition.INVALID_SETTINGS_RESTORE
        return VerificationResult(
            disposition=disposition,
            reason_codes=tuple(manifest.reason_codes)
            or ("task4_partial_before_correlation",),
            verified_artifact_count=verified,
        )

    if manifest.reducer is None:
        raise CustodyContractError("reducer_required", "reducer")
    if manifest.declared_disposition is None:
        raise CustodyContractError("declared_disposition_required", "declared_disposition")

    computed_eligible = any(signal.eligible for signal in verified_signals)
    flags = manifest.reducer
    if flags.has_eligible_signal != computed_eligible:
        raise CustodyContractError("eligible_signal_flag_mismatch", "reducer.has_eligible_signal")

    if checkpoint is None:
        if not manifest.settings_restored:
            raise CustodyContractError("settings_not_restored", "settings_restored")
        if not manifest.redaction_sealed:
            raise CustodyContractError("redaction_seal_missing", "redaction_sealed")
        if not manifest.document_audit_present:
            raise CustodyContractError("document_audit_missing", "document_audit_present")

    disposition = reduce_disposition(flags)
    if disposition is not manifest.declared_disposition:
        raise CustodyContractError("declared_disposition_mismatch", "declared_disposition")

    return VerificationResult(
        disposition=disposition,
        reason_codes=tuple(manifest.reason_codes),
        verified_artifact_count=verified,
    )
