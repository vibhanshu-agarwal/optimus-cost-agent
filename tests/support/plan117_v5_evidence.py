"""Synthetic Plan 11.7 v5 current-client gate documents for unit tests.

Test support only. Every value is synthetic: no document built here is, or may be presented as, live
or accepted evidence. ``valid_raw_document`` describes one complete accepted run (A-prime, the six
registered first-refusal cases and the prompted A/B arm); tests mutate a deep copy of it.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from tools.evidence_gather_support import plan117_current_client_contract as contract

RUN_ID = "p117v5-run-0001"
APPROVAL_ID = "approval-p117v5-0001"
RUN_KEY = bytes(range(32))
SOURCE_COMMIT = "6e5478a0225671ae9ed566b494f66a300562a6b5"  # pragma: allowlist secret - public Git commit pin (base commit object)
SOURCE_TREE = "1" * 40
PROMPTED_SESSION = "session-" + "a" * 32
THREAD_PREFIX = "EC3CEBDAAD744C75934D2FB5B5E72F"  # pragma: allowlist secret - synthetic test thread prefix for fake thread IDs
RUN_ROOT = "C:\\p117v5\\run"
_BASE_NS = 1_000_000_000_000
_LAUNCH_NS = 10_000_000_000


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_sha(value: Any) -> str:
    return sha(contract.canonical_json_bytes(value))


def descriptor_fixture() -> dict[str, Any]:
    """Parsed copy of the committed first-refusal descriptor fixture."""
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "fixtures" / "evidence" / "plan117-v5-first-refusal-descriptors.json"
    return json.loads(path.read_text(encoding="utf-8"))


def descriptor_fixture_sha256() -> str:
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "fixtures" / "evidence" / "plan117-v5-first-refusal-descriptors.json"
    return sha(path.read_bytes())


def _event(index: int, direction: str, kind: str, **fields: Any) -> dict[str, Any]:
    event = {
        "index": index,
        "direction": direction,
        "kind": kind,
        "method": None,
        "request_id": None,
        "session_id": None,
        "response_sha256": None,
        "result_bytes_sha256": None,
        "result_session_id": None,
        "stop_reason": None,
        "error_code": None,
        "update_kind": None,
        "text_sha256": None,
        "prompt_valid": None,
    }
    event.update(fields)
    return event


class _Wire:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def add(self, direction: str, kind: str, **fields: Any) -> None:
        self.events.append(_event(len(self.events), direction, kind, **fields))

    def request(self, method: str, request_id: int, session_id: str | None = None) -> None:
        # session/prompt requests carry the bounded validity fact derived from the captured prompt parameters
        prompt_valid = True if method == "session/prompt" else None
        self.add("zed_to_agent", "request", method=method, request_id=request_id, session_id=session_id, prompt_valid=prompt_valid)

    def response(self, request_id: int, result: Any = None, *, error: Any = None, **fields: Any) -> None:
        body = error if error is not None else result
        self.add(
            "agent_to_zed",
            "response",
            request_id=request_id,
            response_sha256=_canonical_sha(body),
            result_bytes_sha256=None if error is not None else sha(contract.canonical_json_bytes(result)),
            error_code=None if error is None else error["code"],
            **fields,
        )

    def update(self, session_id: str, update_kind: str, text_sha256: str | None = None) -> None:
        self.add(
            "agent_to_zed",
            "notification",
            method="session/update",
            session_id=session_id,
            update_kind=update_kind,
            text_sha256=text_sha256,
        )


def _initialize(wire: _Wire) -> None:
    wire.request("initialize", 0)
    wire.response(0, {"agentCapabilities": {"loadSession": True}})


def _new_session(wire: _Wire, request_id: int, session_id: str) -> None:
    wire.request("session/new", request_id)
    wire.response(request_id, {"sessionId": session_id}, result_session_id=session_id)
    wire.update(session_id, "available_commands_update")


def _counts(events: list[dict[str, Any]]) -> dict[str, int]:
    requests = [e for e in events if e["kind"] == "request"]
    return {
        "initialize": sum(1 for e in requests if e["method"] == "initialize"),
        "session_new": sum(1 for e in requests if e["method"] == "session/new"),
        "session_load": sum(1 for e in requests if e["method"] == "session/load"),
        "session_prompt": sum(1 for e in requests if e["method"] == "session/prompt"),
        "session_update": sum(1 for e in events if e["kind"] == "notification" and e["method"] == "session/update"),
    }


def _session(arm_id: str, launch_id: str) -> str:
    digest = hashlib.sha256(f"{arm_id}/{launch_id}".encode()).hexdigest()[:32]
    return f"session-{digest}"


def _descriptor(descriptor_id: str) -> dict[str, Any]:
    for item in descriptor_fixture()["descriptors"]:
        if item["descriptor_id"] == descriptor_id:
            return item
    raise KeyError(descriptor_id)


def _first_prompt(wire: _Wire, session_id: str, descriptor_id: str) -> None:
    descriptor = _descriptor(descriptor_id)
    wire.request("session/prompt", 2, session_id)
    if descriptor["notice_text"] is not None:
        wire.update(session_id, "agent_message_chunk", sha((descriptor["notice_text"] + "\n\n").encode("utf-8")))
    if descriptor["wire_class"] == "result_stop_reason":
        wire.response(2, {"stopReason": descriptor["stop_reason"]}, stop_reason=descriptor["stop_reason"])
    else:
        wire.response(2, error={"code": descriptor["error_code"], "message": descriptor["error_message"]})


def _closure(source_kind: str, report_ns: int) -> dict[str, Any]:
    return {
        "report_monotonic_ns": report_ns,
        "pid": 4242,
        "entrypoint_module": "optimus.acp.__main__",
        "entries": [
            {"module_name": name, "source_relative_path": path, "sha256": spec_sha(source_kind) if name == "optimus.acp.spec" else sha(name.encode())}
            for name, path in sorted(contract.REQUIRED_MODULE_PATHS.items())
        ],
    }


def spec_sha(source_kind: str) -> str:
    return sha(f"patched-spec/{source_kind}".encode())


def patch_sha(source_kind: str) -> str:
    return sha(f"patch/{source_kind}".encode())


def launcher_sha(source_kind: str) -> str:
    return sha(f"launcher/{source_kind}".encode())


def _launch(arm_id: str, launch_id: str, ordinal: int, events: list[dict[str, Any]]) -> dict[str, Any]:
    source_kind = contract.source_kind_for_arm(arm_id)
    start = _BASE_NS + ordinal * _LAUNCH_NS
    return {
        "launch_id": launch_id,
        "source_kind": source_kind,
        "monotonic_started_ns": start,
        "monotonic_ended_ns": start + _LAUNCH_NS // 2,
        "module_closure": _closure(source_kind, start + 1_000),
        "initialize": {
            "result_sha256": _canonical_sha({"agentCapabilities": {"loadSession": True}}),
            "load_session": True,
            "has_resume": False,
        },
        "wire": events,
        "counts": _counts(events),
        "undecodable_bytes": False,
        "shutdown": {"mechanism": "clean_eof", "agent_stdin_eof": True, "child_exit_code": 0, "zed_exit_code": 0},
    }


def _checkpoint(arm_id: str, launch_id: str, ordinal: int, binding: str | None) -> dict[str, Any]:
    copied = _BASE_NS + ordinal * _LAUNCH_NS + (_LAUNCH_NS * 3) // 4
    return {
        "label": f"after_{launch_id}",
        "copied_monotonic_ns": copied,
        "files": [
            {"file_role": "main", "presence": "present", "path_role": f"database:{arm_id}:after_{launch_id}", "copy_sha256": sha(f"db/{arm_id}/{launch_id}".encode())},
            {"file_role": "shm", "presence": "absent", "path_role": None, "copy_sha256": contract.EMPTY_BYTES_SHA256},
            {"file_role": "wal", "presence": "absent", "path_role": None, "copy_sha256": contract.EMPTY_BYTES_SHA256},
        ],
        "readable": True,
        "thread_id": THREAD_PREFIX + f"{contract.ARM_IDS.index(arm_id):02X}",
        "session_binding": binding,
        "closed_copy": True,
    }


def _arm(arm_id: str, arm_ordinal: int) -> dict[str, Any]:
    first_ordinal = arm_ordinal * 2
    if arm_id == contract.ARM_PROMPTED:
        a = _Wire()
        _initialize(a)
        _new_session(a, 1, PROMPTED_SESSION)
        a.request("session/prompt", 2, PROMPTED_SESSION)
        a.update(PROMPTED_SESSION, "agent_message_chunk", sha(b"hello"))
        a.response(2, {"stopReason": "end_turn"}, stop_reason="end_turn")
        b = _Wire()
        _initialize(b)
        b.request("session/load", 1, PROMPTED_SESSION)
        b.response(1, {})
        launches = [
            _launch(arm_id, "lifecycle_a", first_ordinal, a.events),
            _launch(arm_id, "lifecycle_b", first_ordinal + 1, b.events),
        ]
        checkpoints = [
            _checkpoint(arm_id, "lifecycle_a", first_ordinal, PROMPTED_SESSION),
            _checkpoint(arm_id, "lifecycle_b", first_ordinal + 1, None),
        ]
    else:
        first = _Wire()
        _initialize(first)
        _new_session(first, 1, _session(arm_id, "first"))
        if arm_id != contract.ARM_A_PRIME:
            _first_prompt(first, _session(arm_id, "first"), arm_id)
        reopen = _Wire()
        _initialize(reopen)
        _new_session(reopen, 1, _session(arm_id, "reopen"))
        launches = [
            _launch(arm_id, "first", first_ordinal, first.events),
            _launch(arm_id, "reopen", first_ordinal + 1, reopen.events),
        ]
        checkpoints = [
            _checkpoint(arm_id, "first", first_ordinal, None),
            _checkpoint(arm_id, "reopen", first_ordinal + 1, None),
        ]
    return {
        "arm_id": arm_id,
        "profile_role": f"profile:{arm_id}",
        "workspace_role": f"workspace:{arm_id}",
        "launches": launches,
        "checkpoints": checkpoints,
    }


def _path_identity(role: str, raw_path: str, kind: str, data: bytes | None = None) -> dict[str, Any]:
    return {
        "role": role,
        "raw_path": raw_path,
        "canonical_path": contract.canonicalize_windows_path(raw_path),
        "kind": kind,
        "sha256": None if data is None else sha(data),
        "size_bytes": None if data is None else len(data),
    }


def path_identities() -> list[dict[str, Any]]:
    items = [
        _path_identity("capture_root", "C:\\p117v5\\capture", "directory"),
        _path_identity("run_root", RUN_ROOT, "directory"),
        _path_identity("normal_source_root", "C:\\work\\optimus", "directory"),
        _path_identity("zed_executable", "C:\\Program Files\\Zed\\zed.exe", "file", b"zed-binary"),
    ]
    for kind in contract.SOURCE_KINDS:
        token = kind.replace(":", "-")
        items.append(_path_identity(f"isolated_source:{kind}", f"{RUN_ROOT}\\src-{token}", "directory"))
        items.append(_path_identity(f"launcher:{kind}", f"{RUN_ROOT}\\build-{token}\\launcher.py", "file", f"launcher/{kind}".encode()))
    for arm_id in contract.ARM_IDS:
        items.append(_path_identity(f"profile:{arm_id}", f"{RUN_ROOT}\\{arm_id}\\profile", "directory"))
        items.append(_path_identity(f"workspace:{arm_id}", f"{RUN_ROOT}\\{arm_id}\\workspace", "directory"))
        launch_ids = contract.PROMPTED_LAUNCH_IDS if arm_id == contract.ARM_PROMPTED else contract.REOPEN_LAUNCH_IDS
        for launch_id in launch_ids:
            db_path = f"{RUN_ROOT}\\{arm_id}\\profile\\db\\0-stable\\db.sqlite"
            items.append(_path_identity(f"database:{arm_id}:after_{launch_id}", db_path, "file", f"db/{arm_id}".encode()))
    return sorted(items, key=lambda item: item["role"])


def valid_raw_document() -> dict[str, Any]:
    arms = [_arm(arm_id, ordinal) for ordinal, arm_id in enumerate(contract.ARM_IDS)]
    last_end = _BASE_NS + (2 * len(contract.ARM_IDS)) * _LAUNCH_NS
    cleanup_targets = [{"role": "run_root", "removed": True, "absent_after": True}]
    return {
        "schema": contract.RAW_SCHEMA,
        "evidence_kind": contract.EVIDENCE_KIND_GATE,
        "scenario_id": contract.SCENARIO_ID,
        "scenario_sha256": sha(b"scenario"),
        "run_id": RUN_ID,
        "approval_id": APPROVAL_ID,
        "raw_bundle_sha256": sha(b"bundle"),
        "provisional_classification_sha256": sha(b"provisional"),
        "aborted": None,
        "custody_failures": [],
        "run_window": {
            "wall_started_at": "2026-11-20T10:00:00Z",
            "wall_ended_at": "2026-11-20T11:00:00Z",
            "monotonic_started_ns": _BASE_NS - 1_000,
            "monotonic_ended_ns": last_end + 5 * _LAUNCH_NS,
        },
        "source": {
            "historical_pins": dict(contract.HISTORICAL_PINS),
            "approved_source_commit": SOURCE_COMMIT,
            "actual_source_commit": SOURCE_COMMIT,
            "actual_source_tree": SOURCE_TREE,
            "tracked_diff_sha256": contract.EMPTY_BYTES_SHA256,
            "untracked_digest_sha256": contract.EMPTY_BYTES_SHA256,
            "normal_source_sha256_before": sha(b"normal"),
            "normal_source_sha256_after": sha(b"normal"),
            "descriptor_fixture_sha256": descriptor_fixture_sha256(),
            "launch_config_sha256": sha(b"launch-config"),
            "budget_policy_sha256": sha(b"budget-policy"),
        },
        "client": {
            "executable_role": "zed_executable",
            "executable_sha256": sha(b"zed-binary"),
            "cli_version": "Zed 1.27.0",
            "app_version": "1.27.0",
            "source_revision": "c84af5b99cbc366d675064e52b23664a015b6e35",  # pragma: allowlist secret - fake Zed source-revision fixture, not authentication material
        },
        "isolated_sources": [
            {
                "source_kind": kind,
                "root_role": f"isolated_source:{kind}",
                "launcher_role": f"launcher:{kind}",
                "launcher_sha256": launcher_sha(kind),
                "spec_sha256": spec_sha(kind),
                "patch_sha256": patch_sha(kind),
            }
            for kind in contract.SOURCE_KINDS
        ],
        "path_identities": path_identities(),
        "path_commitment_key_hex": RUN_KEY.hex(),
        "arms": arms,
        "custody": {
            "path_custody_monotonic_ns": last_end + _LAUNCH_NS,
            "cleanup": {
                "started_monotonic_ns": last_end + 2 * _LAUNCH_NS,
                "ended_monotonic_ns": last_end + 3 * _LAUNCH_NS,
                "targets": cleanup_targets,
            },
        },
    }


def mutated(mutation) -> dict[str, Any]:
    """A deep copy of the valid raw document after ``mutation(document)``."""
    document = copy.deepcopy(valid_raw_document())
    mutation(document)
    return document


def arm(document: dict[str, Any], arm_id: str) -> dict[str, Any]:
    return next(item for item in document["arms"] if item["arm_id"] == arm_id)


def launch(document: dict[str, Any], arm_id: str, launch_id: str) -> dict[str, Any]:
    return next(item for item in arm(document, arm_id)["launches"] if item["launch_id"] == launch_id)


def checkpoint(document: dict[str, Any], arm_id: str, label: str) -> dict[str, Any]:
    return next(item for item in arm(document, arm_id)["checkpoints"] if item["label"] == label)


def recount(launch_record: dict[str, Any]) -> None:
    launch_record["counts"] = _counts(launch_record["wire"])


def add_reopen_load(document: dict[str, Any], arm_id: str, *, recount_after: bool = True) -> None:
    """Append a session/load request (and its empty response) to an arm's reopen launch."""
    record = launch(document, arm_id, "reopen")
    wire = record["wire"]
    index = len(wire)
    wire.append(_event(index, "zed_to_agent", "request", method="session/load", request_id=9, session_id=_session(arm_id, "first")))
    wire.append(_event(index + 1, "agent_to_zed", "response", request_id=9, response_sha256=_canonical_sha({}), result_bytes_sha256=sha(b"{}")))
    if recount_after:
        recount(record)


def reindex(launch_record: dict[str, Any]) -> None:
    for position, event in enumerate(launch_record["wire"]):
        event["index"] = position
