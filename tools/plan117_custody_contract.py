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
MAX_ATTEMPTS_PER_KIND = 3
HASH_CHUNK_SIZE = 1 << 20  # 1 MiB
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PRESUMPTIVE_INELIGIBLE_TOKENS = frozenset(
    {"workspace", "cwd", "recency", "pid", "title", "prompt"}
)
_PARTIAL_CHECKPOINTS = frozenset({"task4", "task5"})
_JSON_HASH_METHODS = frozenset({"raw_file_sha256"})


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
