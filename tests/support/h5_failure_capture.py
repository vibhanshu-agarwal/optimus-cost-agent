"""Opt-in, private H5 evidence capture. This module never performs a measurement."""
from __future__ import annotations

import json
import os
import re
import stat
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tools.plan1126_runtime_audit import evidence_store
from tools.plan1126_runtime_audit.measurement import EnvironmentBinding
from tools.plan1126_runtime_audit.shutdown import CloseSite, ResourceOwnershipRecord, ShutdownScheduleObservation
from tools.plan1126_runtime_audit.source import ExecutingSourceMismatch
from tools.testing.run_context import RunContext
from tools.testing.run_context_records import COMMIT, RUN_ID

TARGET = "tests/unit/acp/test_plan1126_shutdown.py::test_shutdown_causes_repeat_100_with_control_allowlist"
ENTRY = "h5.shutdown_schedule"
RECORD_ID = "CM-h5-shutdown_schedule"
CAUSES = ("orderly_eof", "request_cancellation", "transport_failure", "server_cancellation", "partial_startup_failure")
INVALID = "ISSUE287_H5_CAPTURE_INVALID"
_platform = sys.platform
_ROOT = Path(__file__).resolve().parents[2]
_ROW_FIELDS = {field.name for field in fields(ShutdownScheduleObservation)} | {"observation_id"}
_RECEIPT_FIELDS = {
    "schema", "run_id", "pid", "creation_time", "session_index", "context_started_utc", "capture_utc", "worktree", "head",
    "mode", "native", "guard_mode", "requester_nodeid", "phase", "entry", "depth", "options", "request_window",
    "producer_nodeid", "reuse_state", "producer_window", "binding", "record_id", "evidence",
}


@dataclass(frozen=True)
class CaptureStatus:
    state: str
    run_id: str
    requester: str
    reason: str
    elapsed_ns: int | None = None
    published_files: int | None = None
    logical_bytes: int | None = None


def _require(condition: object) -> None:
    if not condition:
        raise ValueError(INVALID)


def _integer(value: object, *, positive: bool = False) -> bool:
    return type(value) is int and (value > 0 if positive else value >= 0)


def _directory_identity(path: Path) -> tuple[int, int]:
    """Non-following, usable Windows file identity; no file-ID width assumption."""
    one, two = os.lstat(path), os.lstat(path)
    for info in (one, two):
        _require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode))
        _require(not (getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT))
        _require(_integer(info.st_ino, positive=True) and _integer(info.st_dev))
    _require((one.st_dev, one.st_ino) == (two.st_dev, two.st_ino))
    return one.st_dev, one.st_ino


def validate_capture_directory(directory: Path) -> tuple[int, int]:
    """Validate existing ancestors before resolving; never follow a supplied junction."""
    _require(directory.is_absolute() and ".." not in directory.parts)
    for path in (*reversed(directory.parents), directory):
        _directory_identity(path)
    _require(directory.resolve(strict=True) == directory)
    return _directory_identity(directory)


def _safe_file(path: Path) -> None:
    validate_capture_directory(path.parent)
    info = os.lstat(path)
    _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode))
    _require(not (getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT))


def _plain(value: Any) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is list:
        for item in value:
            _plain(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _plain(item)
        return
    raise ValueError(INVALID)


def _has_reference(value: Any) -> bool:
    if isinstance(value, dict):
        return "$ref" in value or any(_has_reference(item) for item in value.values())
    return isinstance(value, list) and any(_has_reference(item) for item in value)


def _schema_definitions() -> list[dict[str, Any]]:
    directory = _ROOT / "tests/fixtures/plan1126_runtime_audit"
    return [json.loads((directory / name).read_text(encoding="utf-8"))["$defs"]["contentFreeText"]
            for name in ("audit-artifact.schema.json", "audit-artifact-v2.schema.json")]


def _validators() -> list[Draft202012Validator]:
    definitions = _schema_definitions()
    _require(len(definitions) == 2 and not any(_has_reference(item) for item in definitions))
    for definition in definitions:
        Draft202012Validator.check_schema(definition)
    return [Draft202012Validator(item) for item in definitions]


def _content_free(value: Any, validators: list[Draft202012Validator]) -> None:
    if type(value) is str:
        for validator in validators:
            validator.validate(value)
    elif isinstance(value, (list, dict)):
        for item in value.values() if isinstance(value, dict) else value:
            _content_free(item, validators)


def _error_grammar(row: dict[str, Any]) -> None:
    effect = row["cause_effect"]
    marker = f"{row['terminal_cause']}:probe_error:"
    if row["close_outcome"] != "ERROR" and ":probe_error:" not in effect:
        return
    _require(row["close_outcome"] == "ERROR" and effect.startswith(marker))
    parts = effect[len(marker):].split(" | ")
    _require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", parts[0]) is not None)
    if len(parts) == 1:  # Legacy tokens contain no inferred flags or locations.
        return
    names = ("errno", "winerror", "origin", "probe", "chain", "group")
    _require(len(parts) == 7)
    values = {}
    for name, part in zip(names, parts[1:], strict=True):
        _require(part.startswith(name + "="))
        values[name] = part[len(name) + 1:]
    for name in ("errno", "winerror"):
        value = values[name]
        if value != "unknown":
            _require(re.fullmatch(r"0|-?[1-9][0-9]*", value) is not None)
            _require(-(2**63) <= int(value) < 2**63)
    for name in ("origin", "probe"):
        value = values[name]
        _require(value == "unknown" or re.fullmatch(r"[^|\x00-\x1f\x7f-\x9f\u2028\u2029]+:[1-9][0-9]* in [^|\x00-\x1f\x7f-\x9f\u2028\u2029]+", value) is not None)
    _require(values["chain"] in {"none", "cause", "context", "both", "unknown"})
    group = values["group"]
    _require(group in {"none", "unknown"} or (re.fullmatch(r"[1-9][0-9]*", group) is not None and int(group) < 2**63))


def _validate_result(result: Mapping[str, Any], binding: Mapping[str, Any]) -> None:
    _plain(result)
    _require(set(result) == {"inventory", "inventory_identifiers", "observations"})
    validators = _validators()
    inventory = result["inventory"]
    _require(type(inventory) is dict and set(inventory) == {"kind", "source_fingerprint", "close_path_count", "close_sites", "resources"})
    _require(inventory["kind"] == "shutdown-close-paths" and inventory["source_fingerprint"] == binding["source_fingerprint"])
    _require(_integer(inventory["close_path_count"]))
    for name, model in (("resources", ResourceOwnershipRecord), ("close_sites", CloseSite)):
        _require(type(inventory[name]) is list)
        for item in inventory[name]:
            model.from_dict(item)
            if name == "resources":
                _require(type(item["schedule_applicable"]) is bool and _integer(item["dependency_rank"]))
    _content_free(inventory, validators)
    paths = evidence_store.derive_inventory_identifiers(inventory, binding)
    _require(type(result["inventory_identifiers"]) is list and sorted(result["inventory_identifiers"]) == list(paths))
    rows = result["observations"]
    _require(type(rows) is list)
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        _require(type(row) is dict and set(row) == _ROW_FIELDS)
        _require(type(row["complete"]) is bool)
        for name in ("close_invocation_count", "underlying_close_count"):
            _require(_integer(row[name]) and row[name] < 2**63)
        for name in ("control_thread_names", "unexpected_persistent_threads", "unexpected_persistent_tasks"):
            _require(type(row[name]) is list and all(type(item) is str for item in row[name]))
        _require(row["observation_id"] == row["close_path_id"] and row["close_path_id"] in paths)
        _require(type(row["terminal_cause"]) is str and row["terminal_cause"] in CAUSES)
        ShutdownScheduleObservation.from_dict({key: value for key, value in row.items() if key != "observation_id"})
        _content_free(row, validators)
        _error_grammar(row)
        counts[(row["close_path_id"], row["terminal_cause"])] += 1
    _require(counts == Counter({(path, cause): 100 for path in paths for cause in CAUSES}))


def _timestamp(value: Any) -> None:
    _require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?\+00:00", value))
    parsed = datetime.fromisoformat(value)
    _require(parsed.utcoffset() == UTC.utcoffset(parsed))


def _validate_receipt(receipt: dict[str, Any]) -> None:
    _plain(receipt)
    _require(set(receipt) == _RECEIPT_FIELDS and receipt["schema"] == "issue287-h5-capture-v1")
    matched = RUN_ID.fullmatch(receipt["run_id"])
    _require(matched is not None and _integer(receipt["pid"], positive=True))
    _require(matched is not None and int(matched["pid"]) == receipt["pid"])
    _require(receipt["creation_time"] is None or _integer(receipt["creation_time"], positive=True))
    _require(_integer(receipt["session_index"], positive=True) and COMMIT.fullmatch(receipt["head"]))
    _require(receipt["requester_nodeid"] == TARGET and receipt["phase"] == "call" and receipt["entry"] == ENTRY)
    _require(receipt["depth"] == "full" and receipt["options"] == {"repeats": 100} and type(receipt["options"]["repeats"]) is int)
    _require(receipt["record_id"] == RECORD_ID and receipt["mode"] in {"active", "passive"})
    _require(type(receipt["guard_mode"]) is str and re.fullmatch(r"[A-Za-z0-9_]{1,64}", receipt["guard_mode"]))
    _require(type(receipt["worktree"]) is str and Path(receipt["worktree"]).is_absolute())
    _require(set(receipt["native"]) == {"supported", "attempted", "valid"})
    _require(all(value is None or type(value) is bool for value in receipt["native"].values()))
    for name in ("context_started_utc", "capture_utc"):
        _timestamp(receipt[name])
    window = receipt["request_window"]
    _require(type(window) is dict and set(window) == {"start", "end"})
    _timestamp(window["start"])
    _timestamp(window["end"])
    _require(datetime.fromisoformat(window["start"]) <= datetime.fromisoformat(window["end"]))
    if receipt["reuse_state"] == "FRESH":
        _require(receipt["producer_nodeid"] == TARGET and receipt["producer_window"] == window)
    else:
        _require(receipt["reuse_state"] == "REUSED" and receipt["producer_window"] == "unknown")
        _require(type(receipt["producer_nodeid"]) is str and "::" in receipt["producer_nodeid"])
    _content_free(receipt["producer_nodeid"], _validators())
    EnvironmentBinding.from_dict(receipt["binding"])
    reference = evidence_store.RetainedEvidenceReference.from_dict(receipt["evidence"])
    _require(type(reference.observation_count) is int)
    _require(reference.location == f"{RECORD_ID}.{reference.file_digest[:32]}.evidence.json")


def _read_json(path: Path) -> dict[str, Any]:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result)
            result[key] = value
        return result
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    _require(type(value) is dict)
    return value


def _verify_bundle(directory: Path, *, expected_run_id: str, expected_head: str, expected_pid: int,
                   expected_creation_time: int | None, expected_repository_root: Path) -> dict[str, Any]:
    validate_capture_directory(directory)
    _safe_file(directory / "capture.json")
    receipt = _read_json(directory / "capture.json")
    _validate_receipt(receipt)
    _require(RUN_ID.fullmatch(expected_run_id) and COMMIT.fullmatch(expected_head) and _integer(expected_pid, positive=True))
    _require(expected_creation_time is None or _integer(expected_creation_time, positive=True))
    _require((receipt["run_id"], receipt["head"], receipt["pid"]) == (expected_run_id, expected_head, expected_pid))
    if expected_creation_time is not None:
        _require(receipt["creation_time"] == expected_creation_time)
    _require(Path(receipt["worktree"]).resolve(strict=True) == expected_repository_root.resolve(strict=True))
    reference = evidence_store.RetainedEvidenceReference.from_dict(receipt["evidence"])
    _safe_file(directory / "evidence" / reference.location)
    payload = evidence_store.verify_retained_evidence(record_id=RECORD_ID, measurement_binding=receipt["binding"],
        observation_digest=reference.observation_digest, reference=reference, base_directory=directory / "evidence")
    _require(payload["entry"] == ENTRY)
    _validate_result({key: payload[key] for key in ("inventory", "inventory_identifiers", "observations")}, receipt["binding"])
    return {"receipt": receipt, "inventory": payload["inventory"], "observations": payload["observations"]}


def verify_h5_capture_bundle(directory: Path, *, expected_run_id: str, expected_head: str, expected_pid: int,
                             expected_creation_time: int | None, expected_repository_root: Path) -> dict[str, Any]:
    """Read-only integrity/identity verification; native acceptance is a separate external decision."""
    try:
        _require(directory.name == "h5" and directory.parent.name == expected_run_id)
        return _verify_bundle(directory, expected_run_id=expected_run_id, expected_head=expected_head, expected_pid=expected_pid,
                              expected_creation_time=expected_creation_time, expected_repository_root=expected_repository_root)
    except ExecutingSourceMismatch:
        raise
    except Exception:
        raise ValueError(INVALID) from None


def _published_metrics(directory: Path, reference: evidence_store.RetainedEvidenceReference) -> tuple[int, int]:
    paths = (directory / "capture.json", directory / "evidence" / reference.location)
    return len(paths), sum(path.stat().st_size for path in paths)


def capture_h5_measurement(*, directory: Path, repository_root: Path, context: RunContext, binding: EnvironmentBinding,
                           result: Mapping[str, Any], requester: str, earlier: str | None, depth: str,
                           options: Mapping[str, Any], request_started_utc: str, request_finished_utc: str) -> CaptureStatus:
    """Publish a complete no-clobber bundle from already returned data; ordinary refusal is content-free."""
    if _platform != "win32":
        return CaptureStatus("UNSUPPORTED", context.run_id, requester, "UNSUPPORTED_PLATFORM")
    started = time.perf_counter_ns()
    try:
        _require(requester == TARGET and depth == "full" and dict(options) == {"repeats": 100} and type(options["repeats"]) is int)
        _require(context.root.get("pid") == os.getpid() and type(context.root.get("pid")) is int)
        _require(Path(context.worktree).resolve(strict=True) == repository_root.resolve(strict=True))
        bound = binding.to_dict()
        _plain(bound)
        EnvironmentBinding.from_dict(bound)
        _validate_result(result, bound)
        receipt = {
            "schema": "issue287-h5-capture-v1", "run_id": context.run_id, "pid": context.root.get("pid"),
            "creation_time": context.root.get("creation_time"), "session_index": context.session_index,
            "context_started_utc": context.started_utc, "capture_utc": datetime.now(UTC).isoformat(),
            "worktree": str(repository_root.resolve(strict=True)), "head": context.head, "mode": context.mode,
            "native": {key: context.native.get(key) for key in ("supported", "attempted", "valid")}, "guard_mode": context.guard_mode,
            "requester_nodeid": requester, "phase": "call", "entry": ENTRY, "depth": depth, "options": dict(options),
            "request_window": {"start": request_started_utc, "end": request_finished_utc}, "producer_nodeid": earlier or requester,
            "reuse_state": "REUSED" if earlier is not None else "FRESH",
            "producer_window": "unknown" if earlier is not None else {"start": request_started_utc, "end": request_finished_utc},
            "binding": bound, "record_id": RECORD_ID,
        }
        # Validate all bytes before creating any staging path.
        _, _, provisional = evidence_store.build_evidence_payload(record_id=RECORD_ID, entry=ENTRY, binding=bound, result=result)
        receipt["evidence"] = provisional.to_dict()
        _validate_receipt(receipt)
        base_id = validate_capture_directory(directory)
        parent = directory / context.run_id
        parent.mkdir(exist_ok=True)
        parent_id = validate_capture_directory(parent)
        final = parent / "h5"
        _require(not os.path.lexists(final))
        stage = Path(tempfile.mkdtemp(prefix=".h5-", dir=parent))
        stage_id = validate_capture_directory(stage)
        reference = evidence_store.write_evidence_sidecar(directory=stage / "evidence", record_id=RECORD_ID,
                                                          entry=ENTRY, binding=bound, result=result)
        _require(reference == provisional)
        with (stage / "capture.json").open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(receipt, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            handle.write("\n")
        head, creation_time = context.head, context.root.get("creation_time")
        assert isinstance(head, str) and (creation_time is None or type(creation_time) is int)
        _verify_bundle(stage, expected_run_id=context.run_id, expected_head=head, expected_pid=os.getpid(),
                       expected_creation_time=creation_time, expected_repository_root=repository_root)
        _require(validate_capture_directory(directory) == base_id and validate_capture_directory(parent) == parent_id)
        _require(validate_capture_directory(stage) == stage_id and stage.parent == final.parent == parent)
        _require(not os.path.lexists(final))
        os.rename(stage, final)  # Windows rename refuses an existing destination, including an empty directory.
        _verify_bundle(final, expected_run_id=context.run_id, expected_head=head, expected_pid=os.getpid(),
                       expected_creation_time=creation_time, expected_repository_root=repository_root)
        published_files = logical_bytes = None
        try:
            published_files, logical_bytes = _published_metrics(final, reference)
        except Exception:
            pass  # Metrics failure cannot invalidate the independently verified bundle.
        return CaptureStatus("CAPTURED", context.run_id, requester, "VERIFIED", time.perf_counter_ns() - started,
                             published_files, logical_bytes)
    except ExecutingSourceMismatch:
        raise
    except Exception:
        return CaptureStatus("INVALID", context.run_id, requester, "VALIDATION_OR_IO", time.perf_counter_ns() - started)
