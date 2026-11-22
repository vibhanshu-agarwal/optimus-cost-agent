"""Plan 11.7 v5 E1: pure current-client gate contracts and two-layer derivation.

No filesystem, process, SQLite or network access. Everything here is a closed-world parser or a pure
function over already-captured facts. The collector (``plan117_current_client_collector``) owns I/O.

Two layers, never mixed:

- private raw manifest ``plan-11-7-v5-current-client-raw-v1``: exact paths and the per-run HMAC key;
- public sanitized manifest ``plan-11-7-v5-current-client-sanitized-v1`` plus its redaction attestation:
  role, opaque alias, keyed commitment, hashes and derived observations only.

The reducer's first step is a shape-tolerant scan for a positive empty-reopen signal, so no parse,
count, custody, source or redaction failure can mask ``ZERO_ENTRY_REACHABLE_STOP``.

Provenance: the reducer-as-ordered-predicates design, the windows-path-v1 canonicalization and the
positive-signal definition follow candidate 6208177 (``plan117_current_client_contract.py``); the v5
schemas, R cases, receipt and run registry are new. Candidate bytes are not imported.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum, StrEnum
from typing import Any

from evidence_handoff.collector.bundles import PROVISIONAL_RESULT_SCHEMA
from evidence_handoff.collector.models import ClaimKind, Outcome
from tools.evidence_gather_support.plan117_launcher import PUBLIC_LAUNCHER_IDENTITY

SCENARIO_ID = "plan117-current-client-gate-v5"
EVIDENCE_KIND_GATE = "current-client-gate"
EVIDENCE_KINDS = (EVIDENCE_KIND_GATE, "acpx-restart", "zed-resume")

RAW_SCHEMA = "plan-11-7-v5-current-client-raw-v1"
SANITIZED_SCHEMA = "plan-11-7-v5-current-client-sanitized-v1"
ATTESTATION_SCHEMA = "plan-11-7-v5-current-client-redaction-attestation-v1"
REDACTION_REPORT_SCHEMA = "plan-11-7-v5-current-client-redaction-report-v1"
RECEIPT_SCHEMA = "plan-11-7-v5-private-review-receipt-v1"
PRIVATE_MAPPING_SCHEMA = "plan-11-7-v5-private-path-mapping-v1"
RUN_REGISTRY_SCHEMA = "plan-11-7-v5-approved-runs-v1"
DESCRIPTOR_FIXTURE_SCHEMA = "plan-11-7-v5-first-refusal-descriptors-v1"

PATH_IDENTITY_SCHEME = "windows-path-v1"
PATH_COMMITMENT_DOMAIN = b"plan-11-7-v5:path:v1\x00"

ARM_A_PRIME = "a_prime"
ARM_PROMPTED = "prompted"
R_DESCRIPTOR_IDS = (
    "r_end_turn",
    "r_refusal",
    "r_cancelled",
    "r_invalid_request",
    "r_request_cancelled",
    "r_internal_error",
)
REOPEN_ARM_IDS = (ARM_A_PRIME, *R_DESCRIPTOR_IDS)
ARM_IDS = (*REOPEN_ARM_IDS, ARM_PROMPTED)
REOPEN_LAUNCH_IDS = ("first", "reopen")
PROMPTED_LAUNCH_IDS = ("lifecycle_a", "lifecycle_b")

LOAD_ONLY_STUB = "load_only_stub"
SOURCE_KINDS = (LOAD_ONLY_STUB, *(f"refusal_stub:{descriptor_id}" for descriptor_id in R_DESCRIPTOR_IDS))

REQUIRED_MODULE_PATHS: Mapping[str, str] = {
    "optimus.acp.__main__": "src/optimus/acp/__main__.py",
    "optimus.acp.errors": "src/optimus/acp/errors.py",
    "optimus.acp.server": "src/optimus/acp/server.py",
    "optimus.acp.spec": "src/optimus/acp/spec.py",
}
ENTRYPOINT_MODULE = "optimus.acp.__main__"

HISTORICAL_PINS: Mapping[str, str] = {
    "v2_planned": "cd7014d894576483fe4d2f9d59d2ecbb2c67ee03",  # pragma: allowlist secret - public historical Git commit pin
    "v3_ratified": "3e9b8fa26e00d3c90d0b9ea4182bc67f13a3de47",  # pragma: allowlist secret - public historical Git commit pin
    "candidate_repairs": "fc80403060f578986c287686c27d935a8043dc5a",  # pragma: allowlist secret - public historical Git commit pin
    "candidate_v3": "6208177b55237132c4087652de87c78f21159fb2",  # pragma: allowlist secret - public historical Git commit pin
    "unfinished_v3": "60488daa3df31a0d12d22db61ebc3797a9ffd0b1",  # pragma: allowlist secret - public historical Git commit pin
}

EMPTY_BYTES_SHA256 = hashlib.sha256(b"").hexdigest()
EMPTY_OBJECT_SHA256 = hashlib.sha256(b"{}").hexdigest()

# Out-of-turn current-state publications main sends live and never stores (D6 closed inventory).
LIVE_ONLY_UPDATE_KINDS = frozenset({"available_commands_update", "current_mode_update", "config_option_update"})

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_THREAD_ID = re.compile(r"^[0-9A-F]{2,128}$")
_SESSION_ID = re.compile(r"^session-[0-9a-f]{32}$")
_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{6,62}[a-z0-9]$")
_SCENARIO_ID = re.compile(r"^[a-z][a-z0-9-]*$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}$")
_REASON_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ROLE = re.compile(r"^[a-z][a-z0-9_]*(?::[a-z0-9_]+){0,3}$")
_ALIAS = re.compile(r"^path-[0-9]{3}$")
_MODULE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_METHOD = re.compile(r"^[A-Za-z_][A-Za-z0-9_/.$-]{0,63}$")
_UPDATE_KIND = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_STOP_REASON = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._+-]{0,63}$")
_LOCATOR_COMPONENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")
_TIMESTAMP = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_SIGNED64 = 2**63 - 1


class ContractError(ValueError):
    """A value-free contract failure: ``code`` is a fixed token, ``where`` a structural locator."""

    def __init__(self, code: str, where: str = "") -> None:
        self.code = code
        self.where = where
        super().__init__(f"{code}:{where}" if where else code)


# --------------------------------------------------------------------------- strict JSON


def _no_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate_key")
        result[key] = value
    return result


def _reject_constant(_name: str) -> Any:
    raise ContractError("non_finite_number")


def _finite_float(text: str) -> float:
    value = float(text)
    if value in (float("inf"), float("-inf")) or value != value:
        raise ContractError("non_finite_number")
    return value


def strict_json_loads(payload: bytes) -> Any:
    """UTF-8 JSON with duplicate keys and NaN/Infinity rejected."""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise ContractError("invalid_utf8") from None
    try:
        return json.loads(text, object_pairs_hook=_no_duplicate_pairs, parse_constant=_reject_constant, parse_float=_finite_float)
    except ContractError:
        raise
    except (ValueError, RecursionError):
        raise ContractError("invalid_json") from None


def canonical_json_bytes(value: Any) -> bytes:
    """Sorted keys, compact separators, UTF-8, no NaN/Infinity."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------- strict field readers


def _obj(value: Any, keys: Iterable[str], where: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(keys):
        raise ContractError("schema_invalid", where)
    return value


def _list(value: Any, where: str) -> list[Any]:
    if type(value) is not list:
        raise ContractError("schema_invalid", where)
    return value


def _str(value: Any, where: str, pattern: re.Pattern[str] | None = None) -> str:
    if type(value) is not str or (pattern is not None and not pattern.fullmatch(value)):
        raise ContractError("schema_invalid", where)
    return value


def _opt_str(value: Any, where: str, pattern: re.Pattern[str] | None = None) -> str | None:
    return None if value is None else _str(value, where, pattern)


def _int(value: Any, where: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum or value > _SIGNED64:
        raise ContractError("schema_invalid", where)
    return value


def _opt_int(value: Any, where: str, *, minimum: int = 0) -> int | None:
    return None if value is None else _int(value, where, minimum=minimum)


def _signed_int(value: Any, where: str) -> int:
    if type(value) is not int or not -_SIGNED64 <= value <= _SIGNED64:
        raise ContractError("schema_invalid", where)
    return value


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise ContractError("schema_invalid", where)
    return value


def _enum(value: Any, allowed: Iterable[str], where: str) -> str:
    if type(value) is not str or value not in set(allowed):
        raise ContractError("schema_invalid", where)
    return value


_PROVISIONAL_KEYS = ("schema", "complete", "scenario_id", "run_id", "outcome", "reason_codes", "raw_bundle_sha256", "claims")
_PROVISIONAL_CLAIM_KEYS = (
    "claim_kind", "scenario_id", "run_id", "detector_id", "contract_version", "evidence_sha256", "starts_at_ns", "ends_at_ns", "reason_code",
)


def validate_provisional_custody(payload: bytes, *, scenario_id: str, run_id: str, raw_bundle_sha256: str) -> None:
    """Validate the classifier's custody record without deriving the gate verdict from its outcome."""
    document = _obj(strict_json_loads(payload), _PROVISIONAL_KEYS, "$")
    if document["schema"] != PROVISIONAL_RESULT_SCHEMA or document["complete"] is not True:
        raise ContractError("schema_invalid", "$.provisional")
    binding = (
        _str(document["scenario_id"], "$.scenario_id"),
        _str(document["run_id"], "$.run_id"),
        _str(document["raw_bundle_sha256"], "$.raw_bundle_sha256", _HEX64),
    )
    if binding != (scenario_id, run_id, raw_bundle_sha256):
        raise ContractError("provisional_binding_mismatch")
    _enum(document["outcome"], Outcome, "$.outcome")
    for reason in _list(document["reason_codes"], "$.reason_codes"):
        _str(reason, "$.reason_codes[]")
    for item in _list(document["claims"], "$.claims"):
        claim = _obj(item, _PROVISIONAL_CLAIM_KEYS, "$.claims[]")
        claim_scenario = _str(claim["scenario_id"], "$.claims[].scenario_id")
        claim_run = _str(claim["run_id"], "$.claims[].run_id")
        if (claim_scenario, claim_run) != (scenario_id, run_id):
            raise ContractError("provisional_binding_mismatch")
        _enum(claim["claim_kind"], ClaimKind, "$.claims[].claim_kind")
        for field_name in ("detector_id", "contract_version", "reason_code"):
            _str(claim[field_name], f"$.claims[].{field_name}")
        _int(claim["starts_at_ns"], "$.claims[].starts_at_ns")
        _int(claim["ends_at_ns"], "$.claims[].ends_at_ns")
        for digest in _list(claim["evidence_sha256"], "$.claims[].evidence_sha256"):
            _str(digest, "$.claims[].evidence_sha256[]", _HEX64)


def _timestamp(value: Any, where: str) -> datetime:
    text = _str(value, where, _TIMESTAMP)
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ContractError("schema_invalid", where) from None


def _locator(value: Any, where: str) -> str:
    """A safe source-relative POSIX locator: no drive, root, backslash, dot or dot-dot component."""
    text = _str(value, where)
    parts = text.split("/")
    if not text or any(part in {"", ".", ".."} or not _LOCATOR_COMPONENT.fullmatch(part) for part in parts):
        raise ContractError("schema_invalid", where)
    return text


def _unique(items: Iterable[str], where: str) -> None:
    seen: set[str] = set()
    for item in items:
        if item in seen:
            raise ContractError("schema_invalid", where)
        seen.add(item)


# --------------------------------------------------------------------------- windows-path-v1


def canonicalize_windows_path(path: str) -> str:
    """Canonical windows-path-v1 text for an ALREADY strictly-resolved drive-letter path.

    NFC; ``\\`` separators; redundant ``.`` components removed; drive letter uppercased; every other
    character, including case, preserved. Relative, drive-relative, UNC and dot-dot paths are refused:
    strict resolution happens at capture time, so a canonical input never contains them.
    """
    if type(path) is not str or not path or "\x00" in path:
        raise ContractError("path_not_canonicalizable")
    text = unicodedata.normalize("NFC", path).replace("/", "\\")
    if len(text) < 3 or not text[0].isascii() or not text[0].isalpha() or text[1:3] != ":\\":
        raise ContractError("path_not_canonicalizable")
    parts = [part for part in text[3:].split("\\") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ContractError("path_not_canonicalizable")
    return text[0].upper() + ":\\" + "\\".join(parts)


def path_identity_bytes(canonical_path: str) -> bytes:
    return f"{PATH_IDENTITY_SCHEME}\x00".encode() + canonical_path.encode("utf-8")


def commit_path(canonical_path: str, run_key: bytes) -> str:
    """``HMAC-SHA-256(run_key, b"plan-11-7-v5:path:v1\\0" + windows-path-v1 bytes)``, lowercase hex."""
    if type(run_key) is not bytes or len(run_key) != 32:
        raise ContractError("run_key_invalid")
    if canonicalize_windows_path(canonical_path) != canonical_path:
        raise ContractError("path_not_canonical")
    return hmac.new(run_key, PATH_COMMITMENT_DOMAIN + path_identity_bytes(canonical_path), hashlib.sha256).hexdigest()


def commit_private_mapping(mapping_bytes: bytes, run_key: bytes) -> str:
    """Bind canonical private mapping bytes for the receipt's mapping_sha256 field."""
    if type(run_key) is not bytes or len(run_key) != 32:
        raise ContractError("run_key_invalid")
    return hmac.digest(run_key, b"plan-11-7-v5:mapping:v1\x00" + mapping_bytes, "sha256").hex()


# --------------------------------------------------------------------------- gate dispositions and reasons


class GateDisposition(StrEnum):
    ZERO_ENTRY_REACHABLE_STOP = "ZERO_ENTRY_REACHABLE_STOP"
    INVALID_CURRENT_CLIENT_GATE = "INVALID_CURRENT_CLIENT_GATE"
    INDETERMINATE_CURRENT_CLIENT_GATE = "INDETERMINATE_CURRENT_CLIENT_GATE"
    ACCEPTED_CURRENT_CLIENT_GATE = "ACCEPTED_CURRENT_CLIENT_GATE"

    # short aliases for readers of the tests
    ACCEPTED = "ACCEPTED_CURRENT_CLIENT_GATE"


class Tier(IntEnum):
    STOP = 0
    SCHEMA_CUSTODY = 1
    REOPEN_CHOREOGRAPHY = 2
    PROMPTED = 3
    SOURCE_PROFILE_CLEANUP = 4
    INDETERMINATE = 5


class GateReason(StrEnum):
    """Declaration order is the plan's precedence; ``reason_tier`` is non-decreasing over it."""

    # tier 0: positive empty-reopen signal (non-waivable)
    REOPEN_PRE_BINDING_NON_NULL = "reopen_pre_binding_non_null"
    REOPEN_LOAD_OBSERVED = "reopen_load_observed"
    REOPEN_LOAD_ID_OBSERVED = "reopen_load_id_observed"
    # tier 1: schema / custody invalidity
    SCHEMA_INVALID = "schema_invalid"
    CUSTODY_ARTIFACT_FAILURE = "custody_artifact_failure"
    INTEGRITY_INVALID = "integrity_invalid"
    RUN_SPEC_MISMATCH = "run_spec_mismatch"
    PRIVACY_VIOLATION = "privacy_violation"
    ARM_SET_INVALID = "arm_set_invalid"
    WIRE_INCONSISTENT = "wire_inconsistent"
    COUNTS_INCONSISTENT = "counts_inconsistent"
    CHRONOLOGY_INVALID = "chronology_invalid"
    MODULE_CLOSURE_INCOMPLETE = "module_closure_incomplete"
    MODULE_CLOSURE_CHRONOLOGY = "module_closure_chronology"
    PATCH_IDENTITY_MISMATCH = "patch_identity_mismatch"
    CROSS_ARM_IDENTITY_REUSE = "cross_arm_identity_reuse"
    DATABASE_IDENTITY_DISAGREEMENT = "database_identity_disagreement"
    DATABASE_UNREADABLE = "database_unreadable"
    LIVE_DATABASE_INSPECTED = "live_database_inspected"
    # tier 2: A-prime / first-refusal choreography
    FIRST_LAUNCH_SEQUENCE_INVALID = "first_launch_sequence_invalid"
    FIRST_LAUNCH_LOAD_OBSERVED = "first_launch_load_observed"
    REOPEN_SEQUENCE_INVALID = "reopen_sequence_invalid"
    INITIALIZE_MISSING = "initialize_missing"
    CAPABILITY_LOAD_SESSION_MISSING = "capability_load_session_missing"
    CAPABILITY_RESUME_ADVERTISED = "capability_resume_advertised"
    BINDING_AFTER_REOPEN_NOT_NULL = "binding_after_reopen_not_null"
    R_PROMPT_RESPONSE_MISMATCH = "r_prompt_response_mismatch"
    R_NOTICE_MISMATCH = "r_notice_mismatch"
    R_PROMPT_INVALID = "r_prompt_invalid"
    STORED_CLASS_UPDATE_OBSERVED = "stored_class_update_observed"
    SHUTDOWN_FORCED_KILL = "shutdown_forced_kill"
    SHUTDOWN_INCONSISTENT = "shutdown_inconsistent"
    # tier 3: prompted arm
    PROMPTED_LIFECYCLE_A_INVALID = "prompted_lifecycle_a_invalid"
    PROMPTED_BINDING_BEFORE_B_MISMATCH = "prompted_binding_before_b_mismatch"
    PROMPTED_LOAD_INVALID = "prompted_load_invalid"
    PROMPTED_LOAD_RESPONSE_NOT_EMPTY = "prompted_load_response_not_empty"
    PROMPTED_SPURIOUS_ACTIVITY = "prompted_spurious_activity"
    PROMPTED_BINDING_RETAINED = "prompted_binding_retained"
    # tier 4: source / profile / cleanup / redaction
    HISTORICAL_PINS_MISMATCH = "historical_pins_mismatch"
    SOURCE_COMMIT_MISMATCH = "source_commit_mismatch"
    SOURCE_DIRTY = "source_dirty"
    NORMAL_SOURCE_NOT_RESTORED = "normal_source_not_restored"
    CLEANUP_UNVERIFIED = "cleanup_unverified"
    CLEANUP_BEFORE_CUSTODY = "cleanup_before_custody"
    # tier 5: incomplete evidence
    RUN_ABORTED = "run_aborted"
    ARM_UNOBSERVED = "arm_unobserved"
    SHUTDOWN_UNKNOWN = "shutdown_unknown"


_TIER_START: tuple[tuple[GateReason, Tier], ...] = (
    (GateReason.REOPEN_PRE_BINDING_NON_NULL, Tier.STOP),
    (GateReason.SCHEMA_INVALID, Tier.SCHEMA_CUSTODY),
    (GateReason.FIRST_LAUNCH_SEQUENCE_INVALID, Tier.REOPEN_CHOREOGRAPHY),
    (GateReason.PROMPTED_LIFECYCLE_A_INVALID, Tier.PROMPTED),
    (GateReason.HISTORICAL_PINS_MISMATCH, Tier.SOURCE_PROFILE_CLEANUP),
    (GateReason.RUN_ABORTED, Tier.INDETERMINATE),
)
_REASON_ORDER = {reason: position for position, reason in enumerate(GateReason)}


def reason_tier(reason: GateReason) -> Tier:
    tier = Tier.STOP
    for start, start_tier in _TIER_START:
        if _REASON_ORDER[reason] >= _REASON_ORDER[start]:
            tier = start_tier
    return tier


@dataclass(frozen=True, slots=True)
class GateHit:
    reason: GateReason
    subject: str | None = None

    def code(self) -> str:
        return self.reason.value if self.subject is None else f"{self.reason.value}:{self.subject}"


@dataclass(frozen=True, slots=True)
class GateVerificationResult:
    disposition: GateDisposition
    primary: GateHit | None
    secondary: tuple[GateHit, ...]
    derived_reachability: str | None

    def reason_codes(self) -> tuple[str, ...]:
        return tuple(hit.code() for hit in (self.primary, *self.secondary) if hit is not None)

    def to_json(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition.value,
            "reasons": list(self.reason_codes()),
            "derived_reachability": self.derived_reachability,
        }


_SUBJECT_ORDER = {name: position for position, name in enumerate(ARM_IDS)}


def _hit_sort_key(hit: GateHit) -> tuple[int, int, int, str]:
    subject = hit.subject or ""
    arm = subject.split("/", 1)[0]
    return (int(reason_tier(hit.reason)), _REASON_ORDER[hit.reason], _SUBJECT_ORDER.get(arm, len(ARM_IDS)), subject)


def compose_result(hits: Iterable[GateHit]) -> GateVerificationResult:
    """One primary disposition from the highest-precedence hit; every other hit stays visible."""
    ordered = sorted(set(hits), key=_hit_sort_key)
    if not ordered:
        return GateVerificationResult(GateDisposition.ACCEPTED_CURRENT_CLIENT_GATE, None, (), "ZERO_ENTRY_UNREACHABLE")
    tier = reason_tier(ordered[0].reason)
    if tier is Tier.STOP:
        disposition = GateDisposition.ZERO_ENTRY_REACHABLE_STOP
    elif tier is Tier.INDETERMINATE:
        disposition = GateDisposition.INDETERMINATE_CURRENT_CLIENT_GATE
    else:
        disposition = GateDisposition.INVALID_CURRENT_CLIENT_GATE
    return GateVerificationResult(disposition, ordered[0], tuple(ordered[1:]), None)


# --------------------------------------------------------------------------- positive-signal scan (shape tolerant)


@dataclass(slots=True)
class _RepeatedMembers:
    values: list[Any]


def _preserve_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    members: dict[str, Any] = {}
    for key, value in pairs:
        if key not in members:
            members[key] = value
        elif isinstance(members[key], _RepeatedMembers):
            members[key].values.append(value)
        else:
            members[key] = _RepeatedMembers([members[key], value])
    return members


def scan_json_positive_signals(payload: bytes) -> tuple[GateHit, ...]:
    """Read positive signals from a non-strict manifest without discarding repeated members."""
    try:
        document = json.loads(payload.decode("utf-8", "replace"), object_pairs_hook=_preserve_members)
    except (ValueError, RecursionError):
        return ()
    return scan_positive_signals(document)


def _member_values(document: Any, key: str) -> Sequence[Any]:
    value = document.get(key) if type(document) is dict else None
    return value.values if isinstance(value, _RepeatedMembers) else (value,)


def _exact_strings(items: Any, key: str) -> list[str | None]:
    values = []
    for item in items if type(items) is list else ():
        value = item.get(key) if type(item) is dict else None
        values.append(value if type(value) is str else None)
    return values


def _prompted_launches(launches: Any) -> bool:
    ids = _exact_strings(launches, "launch_id")
    return bool(ids) and all(value in PROMPTED_LAUNCH_IDS for value in ids) and len(set(ids)) == len(ids)


def _scan_reopen_arm(arm: dict[str, Any], subject: str, hits: set[GateHit]) -> None:
    for checkpoints in _member_values(arm, "checkpoints"):
        after_reopen_exempt = _exact_strings(checkpoints, "label").count("after_reopen") == 1
        for checkpoint in checkpoints if type(checkpoints) is list else ():
            if not any(value is not None for value in _member_values(checkpoint, "session_binding")):
                continue
            if not (after_reopen_exempt and checkpoint.get("label") == "after_reopen"):
                hits.add(GateHit(GateReason.REOPEN_PRE_BINDING_NON_NULL, subject))
    for launches in _member_values(arm, "launches"):
        first_exempt = _exact_strings(launches, "launch_id").count("first") == 1
        for launch in launches if type(launches) is list else ():
            if type(launch) is not dict or (first_exempt and launch.get("launch_id") == "first"):
                continue
            for counts in _member_values(launch, "counts"):
                if any(value is not None and value != 0 for value in _member_values(counts, "session_load")):
                    hits.add(GateHit(GateReason.REOPEN_LOAD_OBSERVED, subject))
            for wire in _member_values(launch, "wire"):
                for event in wire if type(wire) is list else ():
                    if "session/load" not in _member_values(event, "method"):
                        continue
                    has_id = any(value is not None for value in _member_values(event, "request_id"))
                    if not has_id or "request" in _member_values(event, "kind"):
                        hits.add(GateHit(GateReason.REOPEN_LOAD_OBSERVED, subject))
                    if has_id:
                        hits.add(GateHit(GateReason.REOPEN_LOAD_ID_OBSERVED, subject))


def scan_positive_signals(document: Any) -> tuple[GateHit, ...]:
    """Scan readable empty-reopen observations before schema validation.

    Repeated observations are scanned within their original arm lists. Only exact,
    unique IDs grant exemptions for first launches, after-reopen bindings and the
    prompted arm. Ambiguous IDs can conservatively over-report STOP. An exact
    replacement of the prompted arm remains indistinguishable by shape.
    """
    hits: set[GateHit] = set()
    for arms in _member_values(document, "arms"):
        ids = _exact_strings(arms, "arm_id")
        prompted_count = ids.count(ARM_PROMPTED)
        for arm, arm_id in zip(arms if type(arms) is list else (), ids, strict=True):
            if type(arm) is not dict:
                continue
            if arm_id == ARM_PROMPTED and prompted_count == 1 and all(
                _prompted_launches(launches) for launches in _member_values(arm, "launches")
            ):
                continue
            _scan_reopen_arm(arm, arm_id if arm_id is not None and arm_id in ARM_IDS else "unidentified", hits)
    return tuple(sorted(hits, key=_hit_sort_key))


# --------------------------------------------------------------------------- typed manifest


@dataclass(frozen=True, slots=True)
class WireEvent:
    index: int
    direction: str
    kind: str
    method: str | None
    request_id: str | int | None
    session_id: str | None
    response_sha256: str | None
    result_bytes_sha256: str | None
    result_session_id: str | None
    stop_reason: str | None
    error_code: int | None
    update_kind: str | None
    text_sha256: str | None
    prompt_valid: bool | None


@dataclass(frozen=True, slots=True)
class Counts:
    initialize: int
    session_new: int
    session_load: int
    session_prompt: int
    session_update: int


@dataclass(frozen=True, slots=True)
class ModuleEntry:
    module_name: str
    source_relative_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ModuleClosure:
    report_monotonic_ns: int
    pid: int
    entrypoint_module: str
    entries: tuple[ModuleEntry, ...]


@dataclass(frozen=True, slots=True)
class InitializeFacts:
    result_sha256: str
    load_session: bool | None
    has_resume: bool


@dataclass(frozen=True, slots=True)
class Shutdown:
    mechanism: str
    agent_stdin_eof: bool
    child_exit_code: int | None
    zed_exit_code: int | None


@dataclass(frozen=True, slots=True)
class Launch:
    launch_id: str
    source_kind: str
    monotonic_started_ns: int
    monotonic_ended_ns: int
    module_closure: ModuleClosure | None
    initialize: InitializeFacts | None
    wire: tuple[WireEvent, ...]
    counts: Counts
    undecodable_bytes: bool
    shutdown: Shutdown


@dataclass(frozen=True, slots=True)
class DatabaseFile:
    file_role: str
    presence: str
    path_role: str | None
    copy_sha256: str


@dataclass(frozen=True, slots=True)
class Checkpoint:
    label: str
    copied_monotonic_ns: int
    files: tuple[DatabaseFile, ...]
    readable: bool
    thread_id: str | None
    session_binding: str | None
    closed_copy: bool


@dataclass(frozen=True, slots=True)
class Arm:
    arm_id: str
    profile_role: str
    workspace_role: str
    launches: tuple[Launch, ...]
    checkpoints: tuple[Checkpoint, ...]


@dataclass(frozen=True, slots=True)
class IsolatedSource:
    source_kind: str
    root_role: str
    launcher_role: str
    launcher_sha256: str
    spec_sha256: str
    patch_sha256: str


@dataclass(frozen=True, slots=True)
class PathIdentity:
    role: str
    kind: str
    sha256: str | None
    size_bytes: int | None
    raw_path: str | None = None
    canonical_path: str | None = None
    alias: str | None = None
    commitment: str | None = None

    @property
    def location_key(self) -> str:
        return self.canonical_path if self.canonical_path is not None else str(self.commitment)


@dataclass(frozen=True, slots=True)
class RunWindow:
    wall_started_at: datetime
    wall_ended_at: datetime
    monotonic_started_ns: int
    monotonic_ended_ns: int


@dataclass(frozen=True, slots=True)
class SourceFacts:
    historical_pins: Mapping[str, str]
    approved_source_commit: str
    actual_source_commit: str
    actual_source_tree: str
    tracked_diff_sha256: str
    untracked_digest_sha256: str
    normal_source_sha256_before: str
    normal_source_sha256_after: str
    descriptor_fixture_sha256: str
    launch_config_sha256: str
    budget_policy_sha256: str


@dataclass(frozen=True, slots=True)
class ClientFacts:
    executable_role: str
    executable_sha256: str
    cli_version: str
    app_version: str
    source_revision: str


@dataclass(frozen=True, slots=True)
class CleanupTarget:
    role: str
    removed: bool
    absent_after: bool


@dataclass(frozen=True, slots=True)
class CustodyFacts:
    path_custody_monotonic_ns: int
    cleanup_started_monotonic_ns: int
    cleanup_ended_monotonic_ns: int
    cleanup_targets: tuple[CleanupTarget, ...]


@dataclass(frozen=True, slots=True)
class Aborted:
    reason_code: str
    stage: str


@dataclass(frozen=True, slots=True)
class _Manifest:
    schema: str
    evidence_kind: str
    scenario_id: str
    scenario_sha256: str
    run_id: str
    approval_id: str
    raw_bundle_sha256: str
    provisional_classification_sha256: str | None
    aborted: Aborted | None
    custody_failures: tuple[str, ...]
    run_window: RunWindow
    source: SourceFacts
    client: ClientFacts
    isolated_sources: tuple[IsolatedSource, ...]
    path_identities: tuple[PathIdentity, ...]
    arms: tuple[Arm, ...]
    custody: CustodyFacts

    def identity(self, role: str) -> PathIdentity:
        for item in self.path_identities:
            if item.role == role:
                return item
        raise ContractError("schema_invalid", f"role:{role}")


@dataclass(frozen=True, slots=True)
class Plan117RawManifest(_Manifest):
    provisional_classification_sha256: str
    path_commitment_key_hex: str = ""

    @property
    def run_key(self) -> bytes:
        return bytes.fromhex(self.path_commitment_key_hex)


@dataclass(frozen=True, slots=True)
class Plan117SanitizedManifest(_Manifest):
    provisional_classification_sha256: str


_TOP_KEYS = (
    "schema", "evidence_kind", "scenario_id", "scenario_sha256", "run_id", "approval_id", "raw_bundle_sha256",
    "provisional_classification_sha256", "aborted", "custody_failures", "run_window", "source", "client",
    "isolated_sources", "path_identities", "arms", "custody",
)
_WIRE_KEYS = (
    "index", "direction", "kind", "method", "request_id", "session_id", "response_sha256", "result_bytes_sha256",
    "result_session_id", "stop_reason", "error_code", "update_kind", "text_sha256", "prompt_valid",
)
_SOURCE_KEYS = (
    "historical_pins", "approved_source_commit", "actual_source_commit", "actual_source_tree", "tracked_diff_sha256",
    "untracked_digest_sha256", "normal_source_sha256_before", "normal_source_sha256_after", "descriptor_fixture_sha256",
    "launch_config_sha256", "budget_policy_sha256",
)


def _parse_wire_event(value: Any, where: str, position: int) -> WireEvent:
    item = _obj(value, _WIRE_KEYS, where)
    if _int(item["index"], f"{where}.index") != position:
        raise ContractError("schema_invalid", f"{where}.index")
    request_id = item["request_id"]
    if request_id is not None and not (
        (type(request_id) is int and abs(request_id) <= _SIGNED64) or (type(request_id) is str and _TOKEN.fullmatch(request_id))
    ):
        raise ContractError("schema_invalid", f"{where}.request_id")
    error_code = item["error_code"]
    is_prompt = item["kind"] == "request" and item["direction"] == "zed_to_agent" and item["method"] == "session/prompt"
    prompt_valid = item["prompt_valid"]
    if (type(prompt_valid) is not bool) if is_prompt else (prompt_valid is not None):
        raise ContractError("schema_invalid", f"{where}.prompt_valid")
    return WireEvent(
        index=position,
        direction=_enum(item["direction"], ("zed_to_agent", "agent_to_zed"), f"{where}.direction"),
        kind=_enum(item["kind"], ("request", "response", "notification"), f"{where}.kind"),
        method=_opt_str(item["method"], f"{where}.method", _METHOD),
        request_id=request_id,
        session_id=_opt_str(item["session_id"], f"{where}.session_id", _SESSION_ID),
        response_sha256=_opt_str(item["response_sha256"], f"{where}.response_sha256", _HEX64),
        result_bytes_sha256=_opt_str(item["result_bytes_sha256"], f"{where}.result_bytes_sha256", _HEX64),
        result_session_id=_opt_str(item["result_session_id"], f"{where}.result_session_id", _SESSION_ID),
        stop_reason=_opt_str(item["stop_reason"], f"{where}.stop_reason", _STOP_REASON),
        error_code=None if error_code is None else _signed_int(error_code, f"{where}.error_code"),
        update_kind=_opt_str(item["update_kind"], f"{where}.update_kind", _UPDATE_KIND),
        text_sha256=_opt_str(item["text_sha256"], f"{where}.text_sha256", _HEX64),
        prompt_valid=prompt_valid,
    )


def _parse_closure(value: Any, where: str) -> ModuleClosure | None:
    if value is None:
        return None
    item = _obj(value, ("report_monotonic_ns", "pid", "entrypoint_module", "entries"), where)
    entries = []
    for position, raw in enumerate(_list(item["entries"], f"{where}.entries")):
        entry_where = f"{where}.entries[{position}]"
        entry = _obj(raw, ("module_name", "source_relative_path", "sha256"), entry_where)
        entries.append(
            ModuleEntry(
                _str(entry["module_name"], f"{entry_where}.module_name", _MODULE),
                _locator(entry["source_relative_path"], f"{entry_where}.source_relative_path"),
                _str(entry["sha256"], f"{entry_where}.sha256", _HEX64),
            )
        )
    _unique((entry.module_name for entry in entries), f"{where}.entries")
    return ModuleClosure(
        _int(item["report_monotonic_ns"], f"{where}.report_monotonic_ns"),
        _int(item["pid"], f"{where}.pid", minimum=1),
        _str(item["entrypoint_module"], f"{where}.entrypoint_module", _MODULE),
        tuple(entries),
    )


def _parse_launch(value: Any, where: str) -> Launch:
    item = _obj(
        value,
        ("launch_id", "source_kind", "monotonic_started_ns", "monotonic_ended_ns", "module_closure", "initialize", "wire", "counts", "undecodable_bytes", "shutdown"),
        where,
    )
    initialize_raw = item["initialize"]
    initialize = None
    if initialize_raw is not None:
        init = _obj(initialize_raw, ("result_sha256", "load_session", "has_resume"), f"{where}.initialize")
        load_session = init["load_session"]
        initialize = InitializeFacts(
            _str(init["result_sha256"], f"{where}.initialize.result_sha256", _HEX64),
            None if load_session is None else _bool(load_session, f"{where}.initialize.load_session"),
            _bool(init["has_resume"], f"{where}.initialize.has_resume"),
        )
    counts_raw = _obj(item["counts"], ("initialize", "session_new", "session_load", "session_prompt", "session_update"), f"{where}.counts")
    shutdown_raw = _obj(item["shutdown"], ("mechanism", "agent_stdin_eof", "child_exit_code", "zed_exit_code"), f"{where}.shutdown")
    wire_raw = _list(item["wire"], f"{where}.wire")
    return Launch(
        launch_id=_str(item["launch_id"], f"{where}.launch_id", _REASON_TOKEN),
        source_kind=_enum(item["source_kind"], SOURCE_KINDS, f"{where}.source_kind"),
        monotonic_started_ns=_int(item["monotonic_started_ns"], f"{where}.monotonic_started_ns"),
        monotonic_ended_ns=_int(item["monotonic_ended_ns"], f"{where}.monotonic_ended_ns"),
        module_closure=_parse_closure(item["module_closure"], f"{where}.module_closure"),
        initialize=initialize,
        wire=tuple(_parse_wire_event(event, f"{where}.wire[{position}]", position) for position, event in enumerate(wire_raw)),
        counts=Counts(*(_int(counts_raw[key], f"{where}.counts.{key}") for key in ("initialize", "session_new", "session_load", "session_prompt", "session_update"))),
        undecodable_bytes=_bool(item["undecodable_bytes"], f"{where}.undecodable_bytes"),
        shutdown=Shutdown(
            _enum(shutdown_raw["mechanism"], ("clean_eof", "forced_kill", "unknown"), f"{where}.shutdown.mechanism"),
            _bool(shutdown_raw["agent_stdin_eof"], f"{where}.shutdown.agent_stdin_eof"),
            None if shutdown_raw["child_exit_code"] is None else _signed_int(shutdown_raw["child_exit_code"], f"{where}.shutdown.child_exit_code"),
            None if shutdown_raw["zed_exit_code"] is None else _signed_int(shutdown_raw["zed_exit_code"], f"{where}.shutdown.zed_exit_code"),
        ),
    )


def _parse_checkpoint(value: Any, where: str) -> Checkpoint:
    item = _obj(value, ("label", "copied_monotonic_ns", "files", "readable", "thread_id", "session_binding", "closed_copy"), where)
    files = []
    for position, raw in enumerate(_list(item["files"], f"{where}.files")):
        file_where = f"{where}.files[{position}]"
        entry = _obj(raw, ("file_role", "presence", "path_role", "copy_sha256"), file_where)
        presence = _enum(entry["presence"], ("present", "absent"), f"{file_where}.presence")
        path_role = _opt_str(entry["path_role"], f"{file_where}.path_role", _ROLE)
        copy_sha256 = _str(entry["copy_sha256"], f"{file_where}.copy_sha256", _HEX64)
        if (presence == "present") != (path_role is not None) or (presence == "absent" and copy_sha256 != EMPTY_BYTES_SHA256):
            raise ContractError("schema_invalid", file_where)
        files.append(DatabaseFile(_enum(entry["file_role"], ("main", "wal", "shm"), f"{file_where}.file_role"), presence, path_role, copy_sha256))
    if sorted(item.file_role for item in files) != ["main", "shm", "wal"]:
        raise ContractError("schema_invalid", f"{where}.files")
    return Checkpoint(
        label=_str(item["label"], f"{where}.label", _REASON_TOKEN),
        copied_monotonic_ns=_int(item["copied_monotonic_ns"], f"{where}.copied_monotonic_ns"),
        files=tuple(sorted(files, key=lambda f: f.file_role)),
        readable=_bool(item["readable"], f"{where}.readable"),
        thread_id=_opt_str(item["thread_id"], f"{where}.thread_id", _THREAD_ID),
        session_binding=_opt_str(item["session_binding"], f"{where}.session_binding", _SESSION_ID),
        closed_copy=_bool(item["closed_copy"], f"{where}.closed_copy"),
    )


def _parse_arm(value: Any, where: str) -> Arm:
    item = _obj(value, ("arm_id", "profile_role", "workspace_role", "launches", "checkpoints"), where)
    launches = tuple(_parse_launch(raw, f"{where}.launches[{i}]") for i, raw in enumerate(_list(item["launches"], f"{where}.launches")))
    checkpoints = tuple(_parse_checkpoint(raw, f"{where}.checkpoints[{i}]") for i, raw in enumerate(_list(item["checkpoints"], f"{where}.checkpoints")))
    _unique((launch.launch_id for launch in launches), f"{where}.launches")
    _unique((checkpoint.label for checkpoint in checkpoints), f"{where}.checkpoints")
    return Arm(
        arm_id=_enum(item["arm_id"], ARM_IDS, f"{where}.arm_id"),
        profile_role=_str(item["profile_role"], f"{where}.profile_role", _ROLE),
        workspace_role=_str(item["workspace_role"], f"{where}.workspace_role", _ROLE),
        launches=launches,
        checkpoints=checkpoints,
    )


def _parse_path_identity(value: Any, where: str, layer: str) -> PathIdentity:
    if layer == "raw":
        item = _obj(value, ("role", "raw_path", "canonical_path", "kind", "sha256", "size_bytes"), where)
        canonical = _str(item["canonical_path"], f"{where}.canonical_path")
        raw_path = _str(item["raw_path"], f"{where}.raw_path")
        try:
            if canonicalize_windows_path(canonical) != canonical or canonicalize_windows_path(raw_path) != canonical:
                raise ContractError("schema_invalid", f"{where}.canonical_path")
        except ContractError:
            raise ContractError("schema_invalid", f"{where}.canonical_path") from None
        extra: dict[str, Any] = {"raw_path": raw_path, "canonical_path": canonical}
    else:
        item = _obj(value, ("role", "alias", "commitment", "kind", "sha256", "size_bytes"), where)
        extra = {"alias": _str(item["alias"], f"{where}.alias", _ALIAS), "commitment": _str(item["commitment"], f"{where}.commitment", _HEX64)}
    kind = _enum(item["kind"], ("file", "directory"), f"{where}.kind")
    sha256 = _opt_str(item["sha256"], f"{where}.sha256", _HEX64)
    size_bytes = _opt_int(item["size_bytes"], f"{where}.size_bytes")
    if (kind == "file") != (sha256 is not None) or (sha256 is None) != (size_bytes is None):
        raise ContractError("schema_invalid", where)
    return PathIdentity(role=_str(item["role"], f"{where}.role", _ROLE), kind=kind, sha256=sha256, size_bytes=size_bytes, **extra)


def _parse_manifest(document: Any, layer: str, *, diagnose_unbound: bool = False) -> _Manifest:
    keys = (*_TOP_KEYS, "path_commitment_key_hex") if layer == "raw" else _TOP_KEYS
    top = _obj(document, keys, "$")
    expected_schema = RAW_SCHEMA if layer == "raw" else SANITIZED_SCHEMA
    if top["schema"] != expected_schema:
        raise ContractError("schema_invalid", "$.schema")
    window = _obj(top["run_window"], ("wall_started_at", "wall_ended_at", "monotonic_started_ns", "monotonic_ended_ns"), "$.run_window")
    source = _obj(top["source"], _SOURCE_KEYS, "$.source")
    pins = _obj(source["historical_pins"], HISTORICAL_PINS.keys(), "$.source.historical_pins")
    client = _obj(top["client"], ("executable_role", "executable_sha256", "cli_version", "app_version", "source_revision"), "$.client")
    custody = _obj(top["custody"], ("path_custody_monotonic_ns", "cleanup"), "$.custody")
    cleanup = _obj(custody["cleanup"], ("started_monotonic_ns", "ended_monotonic_ns", "targets"), "$.custody.cleanup")
    targets = []
    for position, raw in enumerate(_list(cleanup["targets"], "$.custody.cleanup.targets")):
        target_where = f"$.custody.cleanup.targets[{position}]"
        target = _obj(raw, ("role", "removed", "absent_after"), target_where)
        targets.append(CleanupTarget(_str(target["role"], f"{target_where}.role", _ROLE), _bool(target["removed"], f"{target_where}.removed"), _bool(target["absent_after"], f"{target_where}.absent_after")))
    aborted = None
    if top["aborted"] is not None:
        aborted_raw = _obj(top["aborted"], ("reason_code", "stage"), "$.aborted")
        aborted = Aborted(_str(aborted_raw["reason_code"], "$.aborted.reason_code", _REASON_TOKEN), _str(aborted_raw["stage"], "$.aborted.stage", _REASON_TOKEN))
    sources = []
    for position, raw in enumerate(_list(top["isolated_sources"], "$.isolated_sources")):
        source_where = f"$.isolated_sources[{position}]"
        entry = _obj(raw, ("source_kind", "root_role", "launcher_role", "launcher_sha256", "spec_sha256", "patch_sha256"), source_where)
        sources.append(
            IsolatedSource(
                _enum(entry["source_kind"], SOURCE_KINDS, f"{source_where}.source_kind"),
                _str(entry["root_role"], f"{source_where}.root_role", _ROLE),
                _str(entry["launcher_role"], f"{source_where}.launcher_role", _ROLE),
                _str(entry["launcher_sha256"], f"{source_where}.launcher_sha256", _HEX64),
                _str(entry["spec_sha256"], f"{source_where}.spec_sha256", _HEX64),
                _str(entry["patch_sha256"], f"{source_where}.patch_sha256", _HEX64),
            )
        )
    identities = tuple(_parse_path_identity(raw, f"$.path_identities[{i}]", layer) for i, raw in enumerate(_list(top["path_identities"], "$.path_identities")))
    arms = tuple(_parse_arm(raw, f"$.arms[{i}]") for i, raw in enumerate(_list(top["arms"], "$.arms")))
    custody_failures = tuple(_str(code, f"$.custody_failures[{i}]", _REASON_TOKEN) for i, code in enumerate(_list(top["custody_failures"], "$.custody_failures")))
    _unique((item.role for item in identities), "$.path_identities")
    _unique((item.source_kind for item in sources), "$.isolated_sources")
    _unique((item.arm_id for item in arms), "$.arms")
    _unique((item.role for item in targets), "$.custody.cleanup.targets")
    if aborted is None and {item.source_kind for item in sources} != set(SOURCE_KINDS):
        raise ContractError("schema_invalid", "$.isolated_sources")
    if layer == "sanitized":
        _unique((item.alias for item in identities if item.alias is not None), "$.path_identities.alias")
    provisional = top["provisional_classification_sha256"]
    unbound = diagnose_unbound and layer == "raw" and provisional is None
    common: dict[str, Any] = {
        "schema": top["schema"],
        "evidence_kind": _enum(top["evidence_kind"], EVIDENCE_KINDS, "$.evidence_kind"),
        "scenario_id": _str(top["scenario_id"], "$.scenario_id", _SCENARIO_ID),
        "scenario_sha256": _str(top["scenario_sha256"], "$.scenario_sha256", _HEX64),
        "run_id": _str(top["run_id"], "$.run_id", _RUN_ID),
        "approval_id": _str(top["approval_id"], "$.approval_id", _TOKEN),
        "raw_bundle_sha256": _str(top["raw_bundle_sha256"], "$.raw_bundle_sha256", _HEX64),
        "provisional_classification_sha256": None if unbound else _str(provisional, "$.provisional_classification_sha256", _HEX64),
        "aborted": aborted,
        "custody_failures": custody_failures,
        "run_window": RunWindow(
            _timestamp(window["wall_started_at"], "$.run_window.wall_started_at"),
            _timestamp(window["wall_ended_at"], "$.run_window.wall_ended_at"),
            _int(window["monotonic_started_ns"], "$.run_window.monotonic_started_ns"),
            _int(window["monotonic_ended_ns"], "$.run_window.monotonic_ended_ns"),
        ),
        "source": SourceFacts(
            historical_pins={key: _str(pins[key], f"$.source.historical_pins.{key}", _HEX40) for key in HISTORICAL_PINS},
            approved_source_commit=_str(source["approved_source_commit"], "$.source.approved_source_commit", _HEX40),
            actual_source_commit=_str(source["actual_source_commit"], "$.source.actual_source_commit", _HEX40),
            actual_source_tree=_str(source["actual_source_tree"], "$.source.actual_source_tree", _HEX40),
            **{key: _str(source[key], f"$.source.{key}", _HEX64) for key in _SOURCE_KEYS[4:]},
        ),
        "client": ClientFacts(
            _str(client["executable_role"], "$.client.executable_role", _ROLE),
            _str(client["executable_sha256"], "$.client.executable_sha256", _HEX64),
            _str(client["cli_version"], "$.client.cli_version", _VERSION),
            _str(client["app_version"], "$.client.app_version", _VERSION),
            _str(client["source_revision"], "$.client.source_revision", _HEX40),
        ),
        "isolated_sources": tuple(sources),
        "path_identities": identities,
        "arms": arms,
        "custody": CustodyFacts(
            _int(custody["path_custody_monotonic_ns"], "$.custody.path_custody_monotonic_ns"),
            _int(cleanup["started_monotonic_ns"], "$.custody.cleanup.started_monotonic_ns"),
            _int(cleanup["ended_monotonic_ns"], "$.custody.cleanup.ended_monotonic_ns"),
            tuple(targets),
        ),
    }
    if layer == "raw":
        key = _str(top["path_commitment_key_hex"], "$.path_commitment_key_hex", _HEX64)
        # An unbound diagnostic can be reduced but cannot become a publishable manifest.
        manifest: _Manifest = _Manifest(**common) if unbound else Plan117RawManifest(**common, path_commitment_key_hex=key)
    else:
        manifest = Plan117SanitizedManifest(**common)
    _check_role_references(manifest)
    return manifest


def _check_role_references(manifest: _Manifest) -> None:
    roles = {item.role for item in manifest.path_identities}
    referenced = [manifest.client.executable_role]
    for source in manifest.isolated_sources:
        referenced.extend((source.root_role, source.launcher_role))
    for arm in manifest.arms:
        referenced.extend((arm.profile_role, arm.workspace_role))
        for checkpoint in arm.checkpoints:
            referenced.extend(item.path_role for item in checkpoint.files if item.path_role is not None)
    referenced.extend(target.role for target in manifest.custody.cleanup_targets)
    missing = [role for role in referenced if role not in roles]
    if missing:
        raise ContractError("schema_invalid", "role_reference")


def parse_raw_manifest(document: Any) -> Plan117RawManifest:
    manifest = _parse_manifest(document, "raw")
    assert isinstance(manifest, Plan117RawManifest)
    return manifest


def parse_sanitized_manifest(document: Any) -> Plan117SanitizedManifest:
    manifest = _parse_manifest(document, "sanitized")
    assert isinstance(manifest, Plan117SanitizedManifest)
    return manifest


# --------------------------------------------------------------------------- reducer


def source_kind_for_arm(arm_id: str) -> str:
    return f"refusal_stub:{arm_id}" if arm_id in R_DESCRIPTOR_IDS else LOAD_ONLY_STUB


def _requests(launch: Launch, method: str) -> list[WireEvent]:
    return [e for e in launch.wire if e.kind == "request" and e.direction == "zed_to_agent" and e.method == method]


def _response_to(launch: Launch, request: WireEvent) -> WireEvent | None:
    opposite = "agent_to_zed" if request.direction == "zed_to_agent" else "zed_to_agent"
    for event in launch.wire[request.index + 1 :]:
        if event.kind == "response" and event.direction == opposite and event.request_id == request.request_id:
            return event
    return None


def _derived_counts(launch: Launch) -> Counts:
    return Counts(
        initialize=len(_requests(launch, "initialize")),
        session_new=len(_requests(launch, "session/new")),
        session_load=len(_requests(launch, "session/load")),
        session_prompt=len(_requests(launch, "session/prompt")),
        session_update=sum(1 for e in launch.wire if e.kind == "notification" and e.direction == "agent_to_zed" and e.method == "session/update"),
    )


def _wire_consistent(launch: Launch) -> bool:
    if launch.undecodable_bytes:
        return False
    seen: dict[tuple[str, Any], bool] = {}
    for event in launch.wire:
        if event.kind == "request":
            key = (event.direction, event.request_id)
            if event.method is None or event.request_id is None or key in seen or event.response_sha256 is not None:
                return False
            seen[key] = False
        elif event.kind == "response":
            request_direction = "zed_to_agent" if event.direction == "agent_to_zed" else "agent_to_zed"
            key = (request_direction, event.request_id)
            if event.method is not None or event.response_sha256 is None or key not in seen or seen[key]:
                return False
            if (event.error_code is None) == (event.result_bytes_sha256 is None):
                return False
            seen[key] = True
        elif event.method is None or event.request_id is not None or event.response_sha256 is not None:
            return False
    answered = all(done for (direction, _), done in seen.items() if direction == "zed_to_agent")
    if not answered:
        return False
    if launch.initialize is not None:
        initialize = _requests(launch, "initialize")
        response = _response_to(launch, initialize[0]) if len(initialize) == 1 else None
        if response is None or response.response_sha256 != launch.initialize.result_sha256:
            return False
    return True


@dataclass(slots=True)
class _Collector:
    hits: list[GateHit] = field(default_factory=list)

    def add(self, condition: bool, reason: GateReason, subject: str | None = None) -> None:
        if condition:
            self.hits.append(GateHit(reason, subject))


def _launch_order(manifest: _Manifest) -> list[tuple[Arm, Launch]]:
    return [(arm, launch) for arm in manifest.arms for launch in arm.launches]


def _expected_launch_ids(arm_id: str) -> tuple[str, str]:
    return PROMPTED_LAUNCH_IDS if arm_id == ARM_PROMPTED else REOPEN_LAUNCH_IDS


def _check_structure(manifest: _Manifest, out: _Collector) -> bool:
    """Arm/launch/checkpoint set. Returns False when per-arm checks cannot run meaningfully."""
    arm_ids = tuple(arm.arm_id for arm in manifest.arms)
    if manifest.aborted is None:
        out.add(arm_ids != ARM_IDS, GateReason.ARM_SET_INVALID)
    elif arm_ids != ARM_IDS[: len(arm_ids)]:
        out.add(True, GateReason.ARM_SET_INVALID)
    complete = True
    for arm in manifest.arms:
        expected = _expected_launch_ids(arm.arm_id)
        launch_ids = tuple(launch.launch_id for launch in arm.launches)
        labels = tuple(checkpoint.label for checkpoint in arm.checkpoints)
        if launch_ids != expected or labels != tuple(f"after_{launch_id}" for launch_id in expected):
            if manifest.aborted is None or launch_ids != expected[: len(launch_ids)]:
                out.add(True, GateReason.ARM_SET_INVALID, arm.arm_id)
            complete = False
    return complete and arm_ids == ARM_IDS


def _check_chronology(manifest: _Manifest, out: _Collector) -> None:
    window = manifest.run_window
    bad = window.wall_ended_at <= window.wall_started_at or window.monotonic_ended_ns <= window.monotonic_started_ns
    cursor = window.monotonic_started_ns
    last = cursor
    for arm in manifest.arms:
        checkpoints = {checkpoint.label: checkpoint for checkpoint in arm.checkpoints}
        for launch in arm.launches:
            if launch.monotonic_started_ns < cursor or launch.monotonic_ended_ns <= launch.monotonic_started_ns:
                bad = True
            cursor = launch.monotonic_ended_ns
            checkpoint = checkpoints.get(f"after_{launch.launch_id}")
            if checkpoint is not None:
                if checkpoint.copied_monotonic_ns < launch.monotonic_ended_ns:
                    bad = True
                cursor = max(cursor, checkpoint.copied_monotonic_ns)
            last = cursor
    custody = manifest.custody
    if custody.path_custody_monotonic_ns < last or custody.cleanup_ended_monotonic_ns < custody.cleanup_started_monotonic_ns:
        bad = True
    if max(custody.cleanup_ended_monotonic_ns, custody.path_custody_monotonic_ns) > window.monotonic_ended_ns:
        bad = True
    out.add(bad, GateReason.CHRONOLOGY_INVALID)


def _check_launch_custody(manifest: _Manifest, arm: Arm, launch: Launch, out: _Collector) -> None:
    subject = f"{arm.arm_id}/{launch.launch_id}"
    out.add(not _wire_consistent(launch), GateReason.WIRE_INCONSISTENT, subject)
    out.add(_derived_counts(launch) != launch.counts, GateReason.COUNTS_INCONSISTENT, subject)
    sources = {source.source_kind: source for source in manifest.isolated_sources}
    out.add(launch.source_kind != source_kind_for_arm(arm.arm_id), GateReason.PATCH_IDENTITY_MISMATCH, subject)
    closure = launch.module_closure
    if closure is None:
        out.add(True, GateReason.MODULE_CLOSURE_INCOMPLETE, subject)
        return
    entries = {entry.module_name: entry for entry in closure.entries}
    incomplete = closure.entrypoint_module != ENTRYPOINT_MODULE or any(
        name not in entries or entries[name].source_relative_path != path for name, path in REQUIRED_MODULE_PATHS.items()
    )
    out.add(incomplete, GateReason.MODULE_CLOSURE_INCOMPLETE, subject)
    out.add(
        not launch.monotonic_started_ns <= closure.report_monotonic_ns <= launch.monotonic_ended_ns,
        GateReason.MODULE_CLOSURE_CHRONOLOGY,
        subject,
    )
    source = sources.get(launch.source_kind)
    spec_entry = entries.get("optimus.acp.spec")
    out.add(source is None or spec_entry is None or spec_entry.sha256 != source.spec_sha256, GateReason.PATCH_IDENTITY_MISMATCH, subject)


def _check_identities(manifest: _Manifest, out: _Collector) -> None:
    keys: list[str] = []
    database_keys: dict[str, str] = {}
    for arm in manifest.arms:
        keys.extend((manifest.identity(arm.profile_role).location_key, manifest.identity(arm.workspace_role).location_key))
        mains = []
        threads = []
        for checkpoint in arm.checkpoints:
            out.add(not checkpoint.closed_copy, GateReason.LIVE_DATABASE_INSPECTED, f"{arm.arm_id}/{checkpoint.label}")
            out.add(not checkpoint.readable or checkpoint.thread_id is None, GateReason.DATABASE_UNREADABLE, f"{arm.arm_id}/{checkpoint.label}")
            main = next(item for item in checkpoint.files if item.file_role == "main")
            mains.append(None if main.path_role is None else manifest.identity(main.path_role).location_key)
            threads.append(checkpoint.thread_id)
        if mains:
            disagreement = None in mains or len(set(mains)) != 1 or None in threads or len(set(threads)) != 1
            out.add(disagreement, GateReason.DATABASE_IDENTITY_DISAGREEMENT, arm.arm_id)
            if mains[0] is not None:
                database_keys[arm.arm_id] = mains[0]
    out.add(len(set(keys)) != len(keys), GateReason.CROSS_ARM_IDENTITY_REUSE)
    out.add(len(set(database_keys.values())) != len(database_keys), GateReason.CROSS_ARM_IDENTITY_REUSE)


def _check_capability_and_shutdown(arm: Arm, launch: Launch, out: _Collector) -> None:
    subject = f"{arm.arm_id}/{launch.launch_id}"
    if launch.initialize is None:
        out.add(True, GateReason.INITIALIZE_MISSING, subject)
    else:
        out.add(launch.initialize.load_session is not True, GateReason.CAPABILITY_LOAD_SESSION_MISSING, subject)
        out.add(launch.initialize.has_resume, GateReason.CAPABILITY_RESUME_ADVERTISED, subject)
    shutdown = launch.shutdown
    out.add(shutdown.mechanism == "forced_kill", GateReason.SHUTDOWN_FORCED_KILL, subject)
    out.add(shutdown.mechanism == "unknown", GateReason.SHUTDOWN_UNKNOWN, subject)
    out.add(
        shutdown.mechanism == "clean_eof" and (not shutdown.agent_stdin_eof or shutdown.child_exit_code != 0),
        GateReason.SHUTDOWN_INCONSISTENT,
        subject,
    )


def _prompt_window(launch: Launch) -> tuple[int, int] | None:
    prompts = _requests(launch, "session/prompt")
    if len(prompts) != 1:
        return None
    response = _response_to(launch, prompts[0])
    return None if response is None else (prompts[0].index, response.index)


def _updates(launch: Launch) -> list[WireEvent]:
    return [e for e in launch.wire if e.kind == "notification" and e.method == "session/update" and e.direction == "agent_to_zed"]


def _check_reopen_arm(arm: Arm, descriptors: Mapping[str, Descriptor], out: _Collector) -> None:
    launches = {launch.launch_id: launch for launch in arm.launches}
    checkpoints = {checkpoint.label: checkpoint for checkpoint in arm.checkpoints}
    first = launches.get("first")
    reopen = launches.get("reopen")
    expected_prompts = 0 if arm.arm_id == ARM_A_PRIME else 1
    if first is not None:
        counts = _derived_counts(first)
        out.add(counts.session_load > 0, GateReason.FIRST_LAUNCH_LOAD_OBSERVED, arm.arm_id)
        out.add(
            (counts.initialize, counts.session_new, counts.session_prompt) != (1, 1, expected_prompts),
            GateReason.FIRST_LAUNCH_SEQUENCE_INVALID,
            arm.arm_id,
        )
        window = _prompt_window(first)
        for update in _updates(first):
            inside = window is not None and window[0] < update.index < window[1]
            if not inside and update.update_kind not in LIVE_ONLY_UPDATE_KINDS:
                out.add(True, GateReason.STORED_CLASS_UPDATE_OBSERVED, arm.arm_id)
        if arm.arm_id in R_DESCRIPTOR_IDS and window is not None:
            descriptor = descriptors[arm.arm_id]
            prompt = first.wire[window[0]]
            response = first.wire[window[1]]
            new_requests = _requests(first, "session/new")
            new_response = _response_to(first, new_requests[0]) if len(new_requests) == 1 else None
            matches = (
                response.response_sha256 == expected_response_sha256(descriptor)
                and (response.stop_reason == descriptor.stop_reason)
                and (response.error_code == descriptor.error_code)
                and new_response is not None
                and prompt.session_id == new_response.result_session_id
            )
            out.add(not matches, GateReason.R_PROMPT_RESPONSE_MISMATCH, arm.arm_id)
            # An empty or malformed request can elicit a registered reply; only a valid first prompt counts.
            out.add(prompt.prompt_valid is not True, GateReason.R_PROMPT_INVALID, arm.arm_id)
            inside_updates = tuple((u.update_kind, u.text_sha256) for u in _updates(first) if window[0] < u.index < window[1])
            out.add(inside_updates != expected_notices(descriptor), GateReason.R_NOTICE_MISMATCH, arm.arm_id)
    if reopen is not None:
        counts = _derived_counts(reopen)
        out.add(
            (counts.initialize, counts.session_new, counts.session_load, counts.session_prompt) != (1, 1, 0, 0),
            GateReason.REOPEN_SEQUENCE_INVALID,
            arm.arm_id,
        )
        for update in _updates(reopen):
            out.add(update.update_kind not in LIVE_ONLY_UPDATE_KINDS, GateReason.STORED_CLASS_UPDATE_OBSERVED, arm.arm_id)
    for launch in arm.launches:
        _check_capability_and_shutdown(arm, launch, out)
    pre = checkpoints.get("after_first")
    post = checkpoints.get("after_reopen")
    out.add(pre is not None and pre.session_binding is not None, GateReason.REOPEN_PRE_BINDING_NON_NULL, arm.arm_id)
    out.add(post is not None and post.session_binding is not None, GateReason.BINDING_AFTER_REOPEN_NOT_NULL, arm.arm_id)


def _check_prompted_arm(arm: Arm, out: _Collector) -> None:
    launches = {launch.launch_id: launch for launch in arm.launches}
    checkpoints = {checkpoint.label: checkpoint for checkpoint in arm.checkpoints}
    a = launches.get("lifecycle_a")
    b = launches.get("lifecycle_b")
    session_id = None
    if a is not None:
        counts = _derived_counts(a)
        new_requests = _requests(a, "session/new")
        new_response = _response_to(a, new_requests[0]) if len(new_requests) == 1 else None
        session_id = None if new_response is None else new_response.result_session_id
        prompts = _requests(a, "session/prompt")
        invalid = (
            (counts.initialize, counts.session_new, counts.session_load, counts.session_prompt) != (1, 1, 0, 1)
            or session_id is None
            or any(prompt.session_id != session_id or prompt.prompt_valid is not True for prompt in prompts)
        )
        out.add(invalid, GateReason.PROMPTED_LIFECYCLE_A_INVALID, arm.arm_id)
    pre_b = checkpoints.get("after_lifecycle_a")
    out.add(pre_b is not None and (session_id is None or pre_b.session_binding != session_id), GateReason.PROMPTED_BINDING_BEFORE_B_MISMATCH, arm.arm_id)
    if b is not None:
        counts = _derived_counts(b)
        loads = _requests(b, "session/load")
        out.add(
            counts.initialize != 1 or len(loads) != 1 or loads[0].session_id is None or loads[0].session_id != session_id,
            GateReason.PROMPTED_LOAD_INVALID,
            arm.arm_id,
        )
        response = _response_to(b, loads[0]) if len(loads) == 1 else None
        out.add(
            response is None or response.error_code is not None or response.result_bytes_sha256 != EMPTY_OBJECT_SHA256,
            GateReason.PROMPTED_LOAD_RESPONSE_NOT_EMPTY,
            arm.arm_id,
        )
        out.add(counts.session_new != 0 or counts.session_prompt != 0 or counts.session_update != 0, GateReason.PROMPTED_SPURIOUS_ACTIVITY, arm.arm_id)
    post_b = checkpoints.get("after_lifecycle_b")
    out.add(post_b is not None and post_b.session_binding is not None, GateReason.PROMPTED_BINDING_RETAINED, arm.arm_id)
    for launch in arm.launches:
        _check_capability_and_shutdown(arm, launch, out)


def _check_source_and_cleanup(manifest: _Manifest, out: _Collector) -> None:
    source = manifest.source
    out.add(dict(source.historical_pins) != dict(HISTORICAL_PINS), GateReason.HISTORICAL_PINS_MISMATCH)
    out.add(source.actual_source_commit != source.approved_source_commit, GateReason.SOURCE_COMMIT_MISMATCH)
    out.add(
        source.tracked_diff_sha256 != EMPTY_BYTES_SHA256 or source.untracked_digest_sha256 != EMPTY_BYTES_SHA256,
        GateReason.SOURCE_DIRTY,
    )
    out.add(source.normal_source_sha256_before != source.normal_source_sha256_after, GateReason.NORMAL_SOURCE_NOT_RESTORED)
    targets = manifest.custody.cleanup_targets
    out.add(
        not targets or "run_root" not in {t.role for t in targets} or not all(t.removed and t.absent_after for t in targets),
        GateReason.CLEANUP_UNVERIFIED,
    )
    out.add(manifest.custody.cleanup_started_monotonic_ns < manifest.custody.path_custody_monotonic_ns, GateReason.CLEANUP_BEFORE_CUSTODY)


def reduce_gate(manifest: _Manifest, *, descriptors: DescriptorFixture | None = None) -> GateVerificationResult:
    """Pure reducer over a strictly parsed manifest (either layer)."""
    fixture = descriptors or default_descriptor_fixture()
    by_id = {descriptor.descriptor_id: descriptor for descriptor in fixture.descriptors}
    out = _Collector()
    out.hits.extend(scan_positive_signals(_shadow_document(manifest)))
    out.add(bool(manifest.custody_failures), GateReason.CUSTODY_ARTIFACT_FAILURE)
    out.add(manifest.evidence_kind != EVIDENCE_KIND_GATE or manifest.scenario_id != SCENARIO_ID, GateReason.SCHEMA_INVALID)
    if manifest.aborted is not None:
        out.add(True, GateReason.RUN_ABORTED)
        _check_structure(manifest, out)
        for missing in ARM_IDS[len(manifest.arms) :]:
            out.add(True, GateReason.ARM_UNOBSERVED, missing)
        return compose_result(out.hits)
    complete = _check_structure(manifest, out)
    _check_chronology(manifest, out)
    for arm, launch in _launch_order(manifest):
        _check_launch_custody(manifest, arm, launch, out)
    for source in manifest.isolated_sources:
        out.add(manifest.identity(source.launcher_role).sha256 != source.launcher_sha256, GateReason.PATCH_IDENTITY_MISMATCH, source.source_kind)
    _check_identities(manifest, out)
    for arm in manifest.arms:
        if arm.arm_id == ARM_PROMPTED:
            _check_prompted_arm(arm, out)
        else:
            _check_reopen_arm(arm, by_id, out)
    _check_source_and_cleanup(manifest, out)
    if not complete:
        out.add(True, GateReason.ARM_SET_INVALID)
    return compose_result(out.hits)


def _shadow_document(manifest: _Manifest) -> dict[str, Any]:
    """The minimal shape ``scan_positive_signals`` reads, rebuilt from a typed manifest."""
    return {
        "arms": [
            {
                "arm_id": arm.arm_id,
                "checkpoints": [{"label": cp.label, "session_binding": cp.session_binding} for cp in arm.checkpoints],
                "launches": [
                    {
                        "launch_id": launch.launch_id,
                        "counts": {"session_load": launch.counts.session_load},
                        "wire": [{"method": e.method, "kind": e.kind, "request_id": e.request_id} for e in launch.wire],
                    }
                    for launch in arm.launches
                ],
            }
            for arm in manifest.arms
        ]
    }


def reduce_document(
    document: Any,
    *,
    layer: str,
    descriptors: DescriptorFixture | None = None,
    extra_hits: Iterable[GateHit] = (),
) -> GateVerificationResult:
    """Scan for STOP first, then reduce all evidence with a valid shape.

    An absent raw classification digest still permits diagnosis and always adds schema invalidity.
    """
    if layer not in ("raw", "sanitized"):
        raise ValueError("layer")
    signals = scan_positive_signals(document)
    try:
        manifest = _parse_manifest(document, layer, diagnose_unbound=True)
    except (ContractError, TypeError, ValueError, KeyError, AttributeError, IndexError):
        # Untrusted input: any parse failure is schema invalidity, and the already-scanned STOP still wins.
        return compose_result((*signals, GateHit(GateReason.SCHEMA_INVALID), *extra_hits))
    reduced = reduce_gate(manifest, descriptors=descriptors)
    hits = [hit for hit in (reduced.primary, *reduced.secondary) if hit is not None]
    if manifest.provisional_classification_sha256 is None:
        hits.append(GateHit(GateReason.SCHEMA_INVALID))
    return compose_result((*hits, *signals, *extra_hits))


# --------------------------------------------------------------------------- sanitized derivation and privacy


def _alias(position: int) -> str:
    return f"path-{position:03d}"


def _launcher_roles(raw: Plan117RawManifest) -> set[str]:
    # An incomplete source list can still have capture-time launcher identities.
    return ({source.launcher_role for source in raw.isolated_sources}
            | {identity.role for identity in raw.path_identities if identity.role.startswith("launcher:")})


def derive_sanitized_manifest(raw: Plan117RawManifest) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(sanitized_document, private_mapping_document)``; neither touches the filesystem.

    Path identities become role + opaque alias + keyed commitment. The private mapping keeps the
    canonical paths, and launcher metadata describes the public template instead of private rendered bytes.
    """
    key = raw.run_key
    ordered = sorted(raw.path_identities, key=lambda item: item.role)
    public = []
    private = []
    launchers = _launcher_roles(raw)
    for position, identity in enumerate(ordered):
        assert identity.canonical_path is not None
        commitment = commit_path(identity.canonical_path, key)
        digest, size = (PUBLIC_LAUNCHER_IDENTITY if identity.role in launchers
                        else (identity.sha256, identity.size_bytes))
        public.append(
            {"role": identity.role, "alias": _alias(position), "commitment": commitment, "kind": identity.kind, "sha256": digest, "size_bytes": size}
        )
        private.append({"role": identity.role, "alias": _alias(position), "commitment": commitment, "canonical_path": identity.canonical_path})
    document = manifest_to_document(raw)
    document.pop("path_commitment_key_hex")
    document["schema"] = SANITIZED_SCHEMA
    document["path_identities"] = public
    if any(raw.identity(source.launcher_role).sha256 != source.launcher_sha256 for source in raw.isolated_sources):
        # A canonical rendering cannot attest to a mismatched private launcher.
        document["custody_failures"] = sorted(set(raw.custody_failures) | {"launcher_identity_mismatch"})
    for source in document["isolated_sources"]:
        source["launcher_sha256"] = PUBLIC_LAUNCHER_IDENTITY[0]
    mapping = {"schema": PRIVATE_MAPPING_SCHEMA, "run_id": raw.run_id, "scheme": PATH_IDENTITY_SCHEME, "entries": private}
    return document, mapping


def manifest_to_document(manifest: _Manifest) -> dict[str, Any]:
    """Serialize a typed manifest back to its closed JSON document."""

    def ts(value: datetime) -> str:
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")

    def identity(item: PathIdentity) -> dict[str, Any]:
        if item.canonical_path is not None:
            return {"role": item.role, "raw_path": item.raw_path, "canonical_path": item.canonical_path, "kind": item.kind, "sha256": item.sha256, "size_bytes": item.size_bytes}
        return {"role": item.role, "alias": item.alias, "commitment": item.commitment, "kind": item.kind, "sha256": item.sha256, "size_bytes": item.size_bytes}

    def launch(item: Launch) -> dict[str, Any]:
        closure = item.module_closure
        return {
            "launch_id": item.launch_id,
            "source_kind": item.source_kind,
            "monotonic_started_ns": item.monotonic_started_ns,
            "monotonic_ended_ns": item.monotonic_ended_ns,
            "module_closure": None
            if closure is None
            else {
                "report_monotonic_ns": closure.report_monotonic_ns,
                "pid": closure.pid,
                "entrypoint_module": closure.entrypoint_module,
                "entries": [{"module_name": e.module_name, "source_relative_path": e.source_relative_path, "sha256": e.sha256} for e in closure.entries],
            },
            "initialize": None
            if item.initialize is None
            else {"result_sha256": item.initialize.result_sha256, "load_session": item.initialize.load_session, "has_resume": item.initialize.has_resume},
            "wire": [{key: getattr(event, key) for key in _WIRE_KEYS} for event in item.wire],
            "counts": {key: getattr(item.counts, key) for key in ("initialize", "session_new", "session_load", "session_prompt", "session_update")},
            "undecodable_bytes": item.undecodable_bytes,
            "shutdown": {
                "mechanism": item.shutdown.mechanism,
                "agent_stdin_eof": item.shutdown.agent_stdin_eof,
                "child_exit_code": item.shutdown.child_exit_code,
                "zed_exit_code": item.shutdown.zed_exit_code,
            },
        }

    def checkpoint(item: Checkpoint) -> dict[str, Any]:
        return {
            "label": item.label,
            "copied_monotonic_ns": item.copied_monotonic_ns,
            "files": [{"file_role": f.file_role, "presence": f.presence, "path_role": f.path_role, "copy_sha256": f.copy_sha256} for f in item.files],
            "readable": item.readable,
            "thread_id": item.thread_id,
            "session_binding": item.session_binding,
            "closed_copy": item.closed_copy,
        }

    document: dict[str, Any] = {
        "schema": manifest.schema,
        "evidence_kind": manifest.evidence_kind,
        "scenario_id": manifest.scenario_id,
        "scenario_sha256": manifest.scenario_sha256,
        "run_id": manifest.run_id,
        "approval_id": manifest.approval_id,
        "raw_bundle_sha256": manifest.raw_bundle_sha256,
        "provisional_classification_sha256": manifest.provisional_classification_sha256,
        "aborted": None if manifest.aborted is None else {"reason_code": manifest.aborted.reason_code, "stage": manifest.aborted.stage},
        "custody_failures": list(manifest.custody_failures),
        "run_window": {
            "wall_started_at": ts(manifest.run_window.wall_started_at),
            "wall_ended_at": ts(manifest.run_window.wall_ended_at),
            "monotonic_started_ns": manifest.run_window.monotonic_started_ns,
            "monotonic_ended_ns": manifest.run_window.monotonic_ended_ns,
        },
        "source": {key: (dict(getattr(manifest.source, key)) if key == "historical_pins" else getattr(manifest.source, key)) for key in _SOURCE_KEYS},
        "client": {key: getattr(manifest.client, key) for key in ("executable_role", "executable_sha256", "cli_version", "app_version", "source_revision")},
        "isolated_sources": [
            {key: getattr(item, key) for key in ("source_kind", "root_role", "launcher_role", "launcher_sha256", "spec_sha256", "patch_sha256")}
            for item in manifest.isolated_sources
        ],
        "path_identities": [identity(item) for item in manifest.path_identities],
        "arms": [
            {
                "arm_id": arm.arm_id,
                "profile_role": arm.profile_role,
                "workspace_role": arm.workspace_role,
                "launches": [launch(item) for item in arm.launches],
                "checkpoints": [checkpoint(item) for item in arm.checkpoints],
            }
            for arm in manifest.arms
        ],
        "custody": {
            "path_custody_monotonic_ns": manifest.custody.path_custody_monotonic_ns,
            "cleanup": {
                "started_monotonic_ns": manifest.custody.cleanup_started_monotonic_ns,
                "ended_monotonic_ns": manifest.custody.cleanup_ended_monotonic_ns,
                "targets": [{"role": t.role, "removed": t.removed, "absent_after": t.absent_after} for t in manifest.custody.cleanup_targets],
            },
        },
    }
    if isinstance(manifest, Plan117RawManifest):
        document["path_commitment_key_hex"] = manifest.path_commitment_key_hex
    return document


_WINDOWS_PATH_MATERIAL = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
_POSIX_HOME = re.compile(r"(?:^|[^A-Za-z0-9])/(?:home|Users|mnt|root|var/folders)/", re.IGNORECASE)
_TOKEN_SPLIT = re.compile(r"[^0-9a-z]+")


def _strings(value: Any) -> Iterable[str]:
    # Iterative depth-first walk, same order as recursion, so a deeply nested document cannot exhaust the stack (F1).
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            yield item
        elif isinstance(item, Mapping):
            for key, child in reversed(list(item.items())):
                stack.append(child)
                stack.append(str(key))
        elif isinstance(item, (list, tuple)):
            stack.extend(reversed(item))


def find_privacy_violations(
    value: Any,
    *,
    forbidden_strings: Sequence[str],
    identity_tokens: Sequence[str] = (),
) -> tuple[str, ...]:
    """Fixed violation codes for any string (keys included) in a promotable document."""
    violations: set[str] = set()
    forbidden = tuple(item.casefold() for item in forbidden_strings if item)
    tokens = {item.casefold() for item in identity_tokens if item}
    for text in _strings(value):
        folded = text.casefold()
        if _WINDOWS_PATH_MATERIAL.search(text):
            violations.add("windows_path_material")
        if "\\" in text:
            violations.add("backslash")
        if _POSIX_HOME.search(text):
            violations.add("posix_home_path")
        if any(item in folded for item in forbidden):
            violations.add("forbidden_value")
        if tokens and tokens.intersection(part for part in _TOKEN_SPLIT.split(folded) if part):
            violations.add("operator_identity")
    return tuple(sorted(violations))


def private_forbidden_strings(raw: Plan117RawManifest) -> tuple[str, ...]:
    """Every private value that must never reach a promotable byte."""
    _, mapping = derive_sanitized_manifest(raw)
    # The legacy unkeyed mapping digest can confirm guesses about the private paths.
    values = [raw.path_commitment_key_hex, sha256_hex(canonical_json_bytes(mapping))]
    public_launcher_sha256 = PUBLIC_LAUNCHER_IDENTITY[0]
    values.extend(source.launcher_sha256 for source in raw.isolated_sources if source.launcher_sha256 != public_launcher_sha256)
    launchers = _launcher_roles(raw)
    for identity in raw.path_identities:
        if identity.role in launchers and identity.sha256 is not None and identity.sha256 != public_launcher_sha256:
            values.append(identity.sha256)
        values.extend(item for item in (identity.raw_path, identity.canonical_path) if item)
        if identity.canonical_path:
            # Unkeyed path digests are dictionary-guessable, so they are as private as the path itself.
            values.extend(
                sha256_hex(payload)
                for payload in (
                    path_identity_bytes(identity.canonical_path),
                    identity.canonical_path.encode("utf-8"),
                    identity.canonical_path.casefold().encode("utf-8"),
                )
            )
    return tuple(values)


# --------------------------------------------------------------------------- R descriptors


@dataclass(frozen=True, slots=True)
class Descriptor:
    descriptor_id: str
    wire_class: str
    stop_reason: str | None
    error_code_name: str | None
    error_code: int | None
    error_message: str | None
    notice_source: str | None
    notice_text: str | None


@dataclass(frozen=True, slots=True)
class CensusEntry:
    function: str
    site: str
    prior_idle: bool
    count: int
    disposition: str
    descriptor_id: str | None


@dataclass(frozen=True, slots=True)
class DescriptorFixture:
    source_path: str
    descriptors: tuple[Descriptor, ...]
    census: tuple[CensusEntry, ...]
    excluded_classes: tuple[Mapping[str, Any], ...]


_CENSUS_DISPOSITIONS = ("descriptor", "negative_control", "requires_prior_idle", "dispatch")


def parse_descriptor_fixture(document: Any) -> DescriptorFixture:
    top = _obj(document, ("schema", "source_path", "descriptors", "census", "excluded_classes"), "$")
    if top["schema"] != DESCRIPTOR_FIXTURE_SCHEMA:
        raise ContractError("schema_invalid", "$.schema")
    descriptors = []
    for position, raw in enumerate(_list(top["descriptors"], "$.descriptors")):
        where = f"$.descriptors[{position}]"
        item = _obj(raw, ("descriptor_id", "wire_class", "stop_reason", "error_code_name", "error_code", "error_message", "notice_source", "notice_text"), where)
        descriptor = Descriptor(
            _enum(item["descriptor_id"], R_DESCRIPTOR_IDS, f"{where}.descriptor_id"),
            _enum(item["wire_class"], ("result_stop_reason", "error"), f"{where}.wire_class"),
            _opt_str(item["stop_reason"], f"{where}.stop_reason", _STOP_REASON),
            _opt_str(item["error_code_name"], f"{where}.error_code_name", re.compile(r"^[A-Z][A-Z_]*$")),
            None if item["error_code"] is None else _signed_int(item["error_code"], f"{where}.error_code"),
            _opt_str(item["error_message"], f"{where}.error_message"),
            _opt_str(item["notice_source"], f"{where}.notice_source"),
            _opt_str(item["notice_text"], f"{where}.notice_text"),
        )
        is_stop = descriptor.wire_class == "result_stop_reason"
        if is_stop != (descriptor.stop_reason is not None) or is_stop == (descriptor.error_code is not None):
            raise ContractError("schema_invalid", where)
        if (descriptor.error_code is None) != (descriptor.error_message is None) or (descriptor.error_code is None) != (descriptor.error_code_name is None):
            raise ContractError("schema_invalid", where)
        if (descriptor.notice_source is None) != (descriptor.notice_text is None):
            raise ContractError("schema_invalid", where)
        expected_stop = descriptor.descriptor_id.removeprefix("r_") if is_stop else None
        if is_stop and descriptor.stop_reason != expected_stop:
            raise ContractError("schema_invalid", where)
        descriptors.append(descriptor)
    if tuple(d.descriptor_id for d in descriptors) != R_DESCRIPTOR_IDS:
        raise ContractError("schema_invalid", "$.descriptors")
    census = []
    for position, raw in enumerate(_list(top["census"], "$.census")):
        where = f"$.census[{position}]"
        item = _obj(raw, ("function", "site", "prior_idle", "count", "disposition", "descriptor_id"), where)
        entry = CensusEntry(
            _str(item["function"], f"{where}.function", re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")),
            _str(item["site"], f"{where}.site"),
            _bool(item["prior_idle"], f"{where}.prior_idle"),
            _int(item["count"], f"{where}.count", minimum=1),
            _enum(item["disposition"], _CENSUS_DISPOSITIONS, f"{where}.disposition"),
            None if item["descriptor_id"] is None else _enum(item["descriptor_id"], R_DESCRIPTOR_IDS, f"{where}.descriptor_id"),
        )
        if (entry.disposition == "descriptor") != (entry.descriptor_id is not None):
            raise ContractError("schema_invalid", where)
        if entry.prior_idle and entry.disposition != "requires_prior_idle":
            raise ContractError("schema_invalid", where)
        census.append(entry)
    _unique((f"{e.function}|{e.site}|{e.prior_idle}" for e in census), "$.census")
    if {e.descriptor_id for e in census if e.descriptor_id is not None} != set(R_DESCRIPTOR_IDS):
        raise ContractError("schema_invalid", "$.census")
    excluded = []
    for position, raw in enumerate(_list(top["excluded_classes"], "$.excluded_classes")):
        where = f"$.excluded_classes[{position}]"
        item = _obj(raw, ("error_code_name", "error_code", "requires", "owner"), where)
        _str(item["error_code_name"], f"{where}.error_code_name", re.compile(r"^[A-Z][A-Z_]*$"))
        _signed_int(item["error_code"], f"{where}.error_code")
        _str(item["requires"], f"{where}.requires", _REASON_TOKEN)
        _str(item["owner"], f"{where}.owner", re.compile(r"^\S.{0,255}$"))
        excluded.append(item)
    return DescriptorFixture(_locator(top["source_path"], "$.source_path"), tuple(descriptors), tuple(census), tuple(excluded))


_DEFAULT_FIXTURE: list[DescriptorFixture] = []


def default_descriptor_fixture() -> DescriptorFixture:
    """The committed fixture, read once. Lazy so this module stays import-time I/O free."""
    if not _DEFAULT_FIXTURE:
        from pathlib import Path

        path = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "evidence" / "plan117-v5-first-refusal-descriptors.json"
        _DEFAULT_FIXTURE.append(parse_descriptor_fixture(strict_json_loads(path.read_bytes())))
    return _DEFAULT_FIXTURE[0]


def expected_response_sha256(descriptor: Descriptor) -> str:
    if descriptor.wire_class == "result_stop_reason":
        return sha256_hex(canonical_json_bytes({"stopReason": descriptor.stop_reason}))
    return sha256_hex(canonical_json_bytes({"code": descriptor.error_code, "message": descriptor.error_message}))


def expected_notices(descriptor: Descriptor) -> tuple[tuple[str, str], ...]:
    """The exact agent-chunk text main sends: the notice plus its fixed block separator."""
    if descriptor.notice_text is None:
        return ()
    from optimus.acp.shapes import AGENT_MESSAGE_BLOCK_SEPARATOR

    return (("agent_message_chunk", sha256_hex((descriptor.notice_text + AGENT_MESSAGE_BLOCK_SEPARATOR).encode("utf-8"))),)


# --------------------------------------------------------------------------- private review receipt


_RECEIPT_KEYS = (
    "schema", "verdict", "reviewer_identity", "reviewer_session", "reviewer_model", "reviewed_at", "run_id", "scenario_id",
    "scenario_sha256", "source_commit", "raw_manifest_sha256", "raw_bundle_sha256", "sanitized_manifest_sha256",
    "mapping_sha256", "derivatives", "redaction_report_sha256",
)


@dataclass(frozen=True, slots=True)
class PrivateReviewReceipt:
    verdict: str
    reviewer_identity: str
    reviewer_session: str
    reviewer_model: str
    reviewed_at: datetime
    run_id: str
    scenario_id: str
    scenario_sha256: str
    source_commit: str
    raw_manifest_sha256: str
    raw_bundle_sha256: str
    sanitized_manifest_sha256: str
    mapping_sha256: str
    derivatives: tuple[tuple[str, str], ...]
    redaction_report_sha256: str
    document: Mapping[str, Any]


def parse_private_review_receipt(document: Any) -> PrivateReviewReceipt:
    """Closed receipt schema: it carries a verdict and hashes, never observations or counts."""
    item = _obj(document, _RECEIPT_KEYS, "$")
    if item["schema"] != RECEIPT_SCHEMA:
        raise ContractError("schema_invalid", "$.schema")
    derivatives = []
    for position, raw in enumerate(_list(item["derivatives"], "$.derivatives")):
        entry = _obj(raw, ("locator", "sha256"), f"$.derivatives[{position}]")
        derivatives.append((_locator(entry["locator"], f"$.derivatives[{position}].locator"), _str(entry["sha256"], f"$.derivatives[{position}].sha256", _HEX64)))
    return PrivateReviewReceipt(
        verdict=_str(item["verdict"], "$.verdict"),
        reviewer_identity=_str(item["reviewer_identity"], "$.reviewer_identity", _TOKEN),
        reviewer_session=_str(item["reviewer_session"], "$.reviewer_session", _TOKEN),
        reviewer_model=_str(item["reviewer_model"], "$.reviewer_model", _TOKEN),
        reviewed_at=_timestamp(item["reviewed_at"], "$.reviewed_at"),
        run_id=_str(item["run_id"], "$.run_id", _RUN_ID),
        scenario_id=_str(item["scenario_id"], "$.scenario_id"),
        scenario_sha256=_str(item["scenario_sha256"], "$.scenario_sha256", _HEX64),
        source_commit=_str(item["source_commit"], "$.source_commit", _HEX40),
        raw_manifest_sha256=_str(item["raw_manifest_sha256"], "$.raw_manifest_sha256", _HEX64),
        raw_bundle_sha256=_str(item["raw_bundle_sha256"], "$.raw_bundle_sha256", _HEX64),
        sanitized_manifest_sha256=_str(item["sanitized_manifest_sha256"], "$.sanitized_manifest_sha256", _HEX64),
        mapping_sha256=_str(item["mapping_sha256"], "$.mapping_sha256", _HEX64),
        derivatives=tuple(derivatives),
        redaction_report_sha256=_str(item["redaction_report_sha256"], "$.redaction_report_sha256", _HEX64),
        document=dict(item),
    )


@dataclass(frozen=True, slots=True)
class ReceiptExpectation:
    run_id: str
    scenario_id: str
    scenario_sha256: str
    source_commit: str
    raw_manifest_sha256: str
    raw_bundle_sha256: str
    sanitized_manifest_sha256: str
    mapping_sha256: str
    derivatives: Sequence[Mapping[str, str]]
    redaction_report_sha256: str
    not_before: str


def verify_receipt_binding(receipt: PrivateReviewReceipt, expected: ReceiptExpectation) -> None:
    """Only an accepting verdict whose every hash matches the recomputed private facts may promote."""
    if receipt.verdict != "accepting":
        raise ContractError("receipt_not_accepting")
    expected_derivatives = tuple((item["locator"], item["sha256"]) for item in expected.derivatives)
    pairs = (
        (receipt.run_id, expected.run_id),
        (receipt.scenario_id, expected.scenario_id),
        (receipt.scenario_sha256, expected.scenario_sha256),
        (receipt.source_commit, expected.source_commit),
        (receipt.raw_manifest_sha256, expected.raw_manifest_sha256),
        (receipt.raw_bundle_sha256, expected.raw_bundle_sha256),
        (receipt.sanitized_manifest_sha256, expected.sanitized_manifest_sha256),
        (receipt.mapping_sha256, expected.mapping_sha256),
        (receipt.derivatives, expected_derivatives),
        (receipt.redaction_report_sha256, expected.redaction_report_sha256),
    )
    if not expected_derivatives or any(actual != wanted for actual, wanted in pairs):
        raise ContractError("receipt_binding_mismatch")
    if receipt.reviewed_at < _timestamp(expected.not_before, "not_before"):
        raise ContractError("receipt_chronology_invalid")


# --------------------------------------------------------------------------- redaction report and attestation


def build_redaction_report(
    *,
    raw: Plan117RawManifest,
    raw_manifest_sha256: str,
    sanitized_bytes: bytes,
    gate: GateVerificationResult,
    privacy_violations: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema": REDACTION_REPORT_SCHEMA,
        "run_id": raw.run_id,
        "scenario_id": raw.scenario_id,
        "scenario_sha256": raw.scenario_sha256,
        "raw_manifest_sha256": raw_manifest_sha256,
        "derivatives": [{"locator": "manifest.json", "sha256": sha256_hex(sanitized_bytes), "size_bytes": len(sanitized_bytes)}],
        "privacy": {"status": "passed" if not privacy_violations else "failed", "violations": list(privacy_violations)},
        "gate": gate.to_json(),
    }


_ATTESTATION_KEYS = (
    "schema", "evidence_kind", "scenario_id", "scenario_sha256", "run_id", "approval_id", "source_commit", "raw_manifest_sha256",
    "raw_bundle_sha256", "provisional_classification_sha256", "sanitized_manifest_sha256", "mapping_sha256",
    "redaction_report_sha256", "derivatives", "receipt", "receipt_sha256", "gate",
)


@dataclass(frozen=True, slots=True)
class Plan117RedactionAttestation:
    evidence_kind: str
    scenario_id: str
    scenario_sha256: str
    run_id: str
    approval_id: str
    source_commit: str
    raw_manifest_sha256: str
    raw_bundle_sha256: str
    provisional_classification_sha256: str
    sanitized_manifest_sha256: str
    mapping_sha256: str
    redaction_report_sha256: str
    derivatives: tuple[tuple[str, str, int], ...]
    receipt: PrivateReviewReceipt
    receipt_sha256: str
    gate: Mapping[str, Any]


def build_attestation(
    *,
    raw: Plan117RawManifest,
    raw_manifest_sha256: str,
    sanitized_bytes: bytes,
    mapping_sha256: str,
    report_bytes: bytes,
    receipt: PrivateReviewReceipt,
    gate: GateVerificationResult,
) -> dict[str, Any]:
    return {
        "schema": ATTESTATION_SCHEMA,
        "evidence_kind": raw.evidence_kind,
        "scenario_id": raw.scenario_id,
        "scenario_sha256": raw.scenario_sha256,
        "run_id": raw.run_id,
        "approval_id": raw.approval_id,
        "source_commit": raw.source.actual_source_commit,
        "raw_manifest_sha256": raw_manifest_sha256,
        "raw_bundle_sha256": raw.raw_bundle_sha256,
        "provisional_classification_sha256": raw.provisional_classification_sha256,
        "sanitized_manifest_sha256": sha256_hex(sanitized_bytes),
        "mapping_sha256": mapping_sha256,
        "redaction_report_sha256": sha256_hex(report_bytes),
        "derivatives": [
            {"locator": "manifest.json", "sha256": sha256_hex(sanitized_bytes), "size_bytes": len(sanitized_bytes)},
            {"locator": "redaction-report.json", "sha256": sha256_hex(report_bytes), "size_bytes": len(report_bytes)},
        ],
        "receipt": dict(receipt.document),
        "receipt_sha256": sha256_hex(canonical_json_bytes(dict(receipt.document))),
        "gate": gate.to_json(),
    }


def parse_attestation(document: Any) -> Plan117RedactionAttestation:
    item = _obj(document, _ATTESTATION_KEYS, "$")
    if item["schema"] != ATTESTATION_SCHEMA:
        raise ContractError("schema_invalid", "$.schema")
    derivatives = []
    for position, raw in enumerate(_list(item["derivatives"], "$.derivatives")):
        entry = _obj(raw, ("locator", "sha256", "size_bytes"), f"$.derivatives[{position}]")
        derivatives.append(
            (
                _locator(entry["locator"], f"$.derivatives[{position}].locator"),
                _str(entry["sha256"], f"$.derivatives[{position}].sha256", _HEX64),
                _int(entry["size_bytes"], f"$.derivatives[{position}].size_bytes"),
            )
        )
    _unique((locator for locator, _, _ in derivatives), "$.derivatives")
    if [locator for locator, _, _ in derivatives] != ["manifest.json", "redaction-report.json"]:
        raise ContractError("schema_invalid", "$.derivatives")
    gate = _obj(item["gate"], ("disposition", "reasons", "derived_reachability"), "$.gate")
    _enum(gate["disposition"], [d.value for d in GateDisposition], "$.gate.disposition")
    for position, code in enumerate(_list(gate["reasons"], "$.gate.reasons")):
        _str(code, f"$.gate.reasons[{position}]")
    if gate["derived_reachability"] not in (None, "ZERO_ENTRY_UNREACHABLE"):
        raise ContractError("schema_invalid", "$.gate.derived_reachability")
    receipt = parse_private_review_receipt(item["receipt"])
    return Plan117RedactionAttestation(
        evidence_kind=_enum(item["evidence_kind"], EVIDENCE_KINDS, "$.evidence_kind"),
        scenario_id=_str(item["scenario_id"], "$.scenario_id"),
        scenario_sha256=_str(item["scenario_sha256"], "$.scenario_sha256", _HEX64),
        run_id=_str(item["run_id"], "$.run_id", _RUN_ID),
        approval_id=_str(item["approval_id"], "$.approval_id", _TOKEN),
        source_commit=_str(item["source_commit"], "$.source_commit", _HEX40),
        raw_manifest_sha256=_str(item["raw_manifest_sha256"], "$.raw_manifest_sha256", _HEX64),
        raw_bundle_sha256=_str(item["raw_bundle_sha256"], "$.raw_bundle_sha256", _HEX64),
        provisional_classification_sha256=_str(item["provisional_classification_sha256"], "$.provisional_classification_sha256", _HEX64),
        sanitized_manifest_sha256=_str(item["sanitized_manifest_sha256"], "$.sanitized_manifest_sha256", _HEX64),
        mapping_sha256=_str(item["mapping_sha256"], "$.mapping_sha256", _HEX64),
        redaction_report_sha256=_str(item["redaction_report_sha256"], "$.redaction_report_sha256", _HEX64),
        derivatives=tuple(derivatives),
        receipt=receipt,
        receipt_sha256=_str(item["receipt_sha256"], "$.receipt_sha256", _HEX64),
        gate=dict(gate),
    )


# --------------------------------------------------------------------------- trusted approved-run registry


_RUN_SPEC_KEYS = (
    "run_id", "evidence_kind", "scenario_id", "scenario_source_sha256", "scenario_sha256", "descriptor_fixture_sha256",
    "patch_sha256s", "source_commit", "source_tree", "required_modules", "client", "launch_config_sha256", "arm_ids",
    "approval_id", "approval_not_before", "approval_not_after", "budget_policy_sha256", "private_root_commitments",
)


@dataclass(frozen=True, slots=True)
class RunSpec:
    run_id: str
    evidence_kind: str
    scenario_id: str
    scenario_source_sha256: str
    scenario_sha256: str
    descriptor_fixture_sha256: str
    patch_sha256s: Mapping[str, str]
    source_commit: str
    source_tree: str
    required_modules: tuple[str, ...]
    client: Mapping[str, str]
    launch_config_sha256: str
    arm_ids: tuple[str, ...]
    approval_id: str
    approval_not_before: datetime
    approval_not_after: datetime
    budget_policy_sha256: str
    private_root_commitments: Mapping[str, str]
    run_spec_sha256: str


@dataclass(frozen=True, slots=True)
class ApprovedRunRegistry:
    runs: tuple[RunSpec, ...]

    def lookup(self, run_id: str) -> RunSpec:
        for spec in self.runs:
            if spec.run_id == run_id:
                return spec
        raise ContractError("run_not_registered")


def _parse_run_spec(value: Any, where: str) -> RunSpec:
    item = _obj(value, _RUN_SPEC_KEYS, where)
    patches = _obj(item["patch_sha256s"], SOURCE_KINDS, f"{where}.patch_sha256s")
    client = _obj(item["client"], ("executable_sha256", "app_version", "source_revision"), f"{where}.client")
    commitments = _obj(item["private_root_commitments"], ("capture_root",), f"{where}.private_root_commitments")
    arm_ids = tuple(_str(arm, f"{where}.arm_ids") for arm in _list(item["arm_ids"], f"{where}.arm_ids"))
    if arm_ids != ARM_IDS:
        raise ContractError("schema_invalid", f"{where}.arm_ids")
    modules = tuple(_str(m, f"{where}.required_modules", _MODULE) for m in _list(item["required_modules"], f"{where}.required_modules"))
    if list(modules) != sorted(set(modules)):
        raise ContractError("schema_invalid", f"{where}.required_modules")
    not_before = _timestamp(item["approval_not_before"], f"{where}.approval_not_before")
    not_after = _timestamp(item["approval_not_after"], f"{where}.approval_not_after")
    if not_after <= not_before:
        raise ContractError("schema_invalid", f"{where}.approval_window")
    return RunSpec(
        run_id=_str(item["run_id"], f"{where}.run_id", _RUN_ID),
        evidence_kind=_enum(item["evidence_kind"], EVIDENCE_KINDS, f"{where}.evidence_kind"),
        scenario_id=_str(item["scenario_id"], f"{where}.scenario_id"),
        scenario_source_sha256=_str(item["scenario_source_sha256"], f"{where}.scenario_source_sha256", _HEX64),
        scenario_sha256=_str(item["scenario_sha256"], f"{where}.scenario_sha256", _HEX64),
        descriptor_fixture_sha256=_str(item["descriptor_fixture_sha256"], f"{where}.descriptor_fixture_sha256", _HEX64),
        patch_sha256s={kind: _str(patches[kind], f"{where}.patch_sha256s", _HEX64) for kind in SOURCE_KINDS},
        source_commit=_str(item["source_commit"], f"{where}.source_commit", _HEX40),
        source_tree=_str(item["source_tree"], f"{where}.source_tree", _HEX40),
        required_modules=modules,
        client={
            "executable_sha256": _str(client["executable_sha256"], f"{where}.client.executable_sha256", _HEX64),
            "app_version": _str(client["app_version"], f"{where}.client.app_version", _VERSION),
            "source_revision": _str(client["source_revision"], f"{where}.client.source_revision", _HEX40),
        },
        launch_config_sha256=_str(item["launch_config_sha256"], f"{where}.launch_config_sha256", _HEX64),
        arm_ids=arm_ids,
        approval_id=_str(item["approval_id"], f"{where}.approval_id", _TOKEN),
        approval_not_before=not_before,
        approval_not_after=not_after,
        budget_policy_sha256=_str(item["budget_policy_sha256"], f"{where}.budget_policy_sha256", _HEX64),
        private_root_commitments={"capture_root": _str(commitments["capture_root"], f"{where}.private_root_commitments.capture_root", _HEX64)},
        run_spec_sha256=sha256_hex(canonical_json_bytes(item)),
    )


def parse_approved_runs(document: Any) -> ApprovedRunRegistry:
    """The reviewed checkout's approved-run registry: an evidence trust input, not a status register."""
    top = _obj(document, ("schema", "runs"), "$")
    if top["schema"] != RUN_REGISTRY_SCHEMA:
        raise ContractError("schema_invalid", "$.schema")
    runs = []
    for position, raw in enumerate(_list(top["runs"], "$.runs")):
        row = _obj(raw, ("run_spec", "run_spec_sha256"), f"$.runs[{position}]")
        spec = _parse_run_spec(row["run_spec"], f"$.runs[{position}].run_spec")
        if _str(row["run_spec_sha256"], f"$.runs[{position}].run_spec_sha256", _HEX64) != spec.run_spec_sha256:
            raise ContractError("run_spec_digest_mismatch")
        runs.append(spec)
    run_ids = [spec.run_id for spec in runs]
    if len(set(run_ids)) != len(run_ids):
        raise ContractError("duplicate_run_id")
    return ApprovedRunRegistry(tuple(runs))


def run_spec_mismatches(manifest: _Manifest, spec: RunSpec) -> tuple[str, ...]:
    """Fields where a manifest disagrees with its reviewed RunSpec (value-free field names)."""
    mismatches: list[str] = []

    def check(condition: bool, name: str) -> None:
        if condition:
            mismatches.append(name)

    check(manifest.run_id != spec.run_id, "run_id")
    check(manifest.evidence_kind != spec.evidence_kind, "evidence_kind")
    check(manifest.scenario_id != spec.scenario_id, "scenario_id")
    check(manifest.scenario_sha256 != spec.scenario_sha256, "scenario_sha256")
    check(manifest.source.descriptor_fixture_sha256 != spec.descriptor_fixture_sha256, "descriptor_fixture_sha256")
    check({s.source_kind: s.patch_sha256 for s in manifest.isolated_sources} != dict(spec.patch_sha256s), "patch_sha256s")
    check(manifest.source.approved_source_commit != spec.source_commit, "source_commit")
    check(manifest.source.actual_source_tree != spec.source_tree, "source_tree")
    check(tuple(sorted(REQUIRED_MODULE_PATHS)) != spec.required_modules, "required_modules")
    check(
        (manifest.client.executable_sha256, manifest.client.app_version, manifest.client.source_revision)
        != (spec.client["executable_sha256"], spec.client["app_version"], spec.client["source_revision"]),
        "client",
    )
    check(manifest.source.launch_config_sha256 != spec.launch_config_sha256, "launch_config_sha256")
    check(tuple(arm.arm_id for arm in manifest.arms) != spec.arm_ids, "arm_ids")
    check(manifest.approval_id != spec.approval_id, "approval_id")
    check(
        manifest.run_window.wall_started_at < spec.approval_not_before or manifest.run_window.wall_ended_at > spec.approval_not_after,
        "approval_window",
    )
    check(manifest.source.budget_policy_sha256 != spec.budget_policy_sha256, "budget_policy_sha256")
    try:
        identity = manifest.identity("capture_root")
        if isinstance(manifest, Plan117RawManifest):
            assert identity.canonical_path is not None
            commitment = commit_path(identity.canonical_path, manifest.run_key)
        else:
            commitment = identity.commitment
        check(commitment != spec.private_root_commitments["capture_root"], "private_root_commitments")
    except ContractError:
        mismatches.append("private_root_commitments")
    return tuple(mismatches)
