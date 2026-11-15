"""Plan 11.7 v5 E2: pipeline-native current-client collector support.

I/O side of the v5 gate; the pure contract lives in ``plan117_current_client_contract``. Built slice by
slice under test: R-census tracing over production source first.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evidence_handoff.collector.bundles import RAW_BUNDLE_SCHEMA, _payload_sha256, load_verified_raw_bundle
from evidence_handoff.collector.models import CapturedArtifact, CollectionBatch, Observation, RunContext
from evidence_handoff.collector.pipeline import _OBSERVATION_SCHEMA as OBSERVATION_SCHEMA
from tools.evidence_gather_support import plan117_current_client_contract as contract
from tools.evidence_gather_support.common import HostError

COLLECTOR_ID = "plan117_v5_current_client_collector"
CONTRACT_VERSION = "v1"
FIXTURE_ADAPTER_ID = "plan117_v5_isolated_source_fixture"
MODULE_CLOSURE_SCHEMA = "plan-11-7-v5-module-closure-report-v1"


# --------------------------------------------------------------------------- R census tracing

_CENSUS_CLASS = "AcpDuplexAdapter"
_CENSUS_FUNCTIONS = ("handle_client_request", "_handle_client_request", "_handle_session_prompt", "_refuse_prompt", "_mcp_refusal", "_handle_savings")
_ADMISSION_ANCHOR = "allocate_turn_seq"


def _stop_reasons(value: ast.expr) -> list[object]:
    if isinstance(value, ast.Constant):
        return [value.value]
    if isinstance(value, ast.IfExp) and isinstance(value.body, ast.Constant) and isinstance(value.orelse, ast.Constant):
        return [value.body.value, value.orelse.value]
    return ["*"]


def _sites(node: ast.AST, prior_idle: bool) -> list[tuple[str, bool]]:
    found: list[tuple[str, bool]] = []
    for child in ast.iter_child_nodes(node):
        idle = prior_idle or (isinstance(child, ast.If) and "state.suspended" in ast.unparse(child.test))
        if isinstance(child, ast.Call):
            name = ast.unparse(child.func)
            if name == "JsonRpcError":
                keywords = {item.arg: item.value for item in child.keywords}
                code = ast.unparse(keywords["code"]) if "code" in keywords else "*"
                message = keywords.get("message")
                text = message.value if isinstance(message, ast.Constant) and isinstance(message.value, str) else "*"
                found.append((f"error:{code}:{text}", idle))
            elif name.endswith("._mcp_refusal"):
                reason = child.args[2].value if len(child.args) > 2 and isinstance(child.args[2], ast.Constant) else "*"
                found.append((f"mcp_refusal:{reason}", idle))
            elif name.endswith("._refuse_prompt"):
                found.append(("refuse_prompt", idle))
            elif name.endswith("._handle_savings"):
                found.append(("savings", idle))
        elif isinstance(child, ast.Dict):
            for key, value in zip(child.keys, child.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "stopReason":
                    found.extend((f"stop_reason:{item}", idle) for item in _stop_reasons(value))
        found.extend(_sites(child, idle))
    return found


def trace_first_prompt_census(spec_text: str) -> tuple[tuple[str, str, bool, int], ...]:
    """``(function, site, prior_idle, count)`` for every first-prompt response-class site.

    ``_handle_session_prompt`` is read only up to its admission (``allocate_turn_seq``) statement;
    sites inside the ``state.suspended`` re-disposition block are marked ``prior_idle``.
    """
    counts: dict[tuple[str, str, bool], int] = {}
    for node in ast.parse(spec_text).body:
        if not isinstance(node, ast.ClassDef) or node.name != _CENSUS_CLASS:
            continue
        for function in node.body:
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)) or function.name not in _CENSUS_FUNCTIONS:
                continue
            body = function.body
            if function.name == "_handle_session_prompt":
                cut = next((i for i, statement in enumerate(body) if _ADMISSION_ANCHOR in ast.unparse(statement)), None)
                if cut is None:
                    raise HostError("r_census_anchor_missing")
                body = body[:cut]
            for statement in body:
                for site, idle in _sites(ast.Module(body=[statement], type_ignores=[]), False):
                    counts[(function.name, site, idle)] = counts.get((function.name, site, idle), 0) + 1
    return tuple(sorted((f, s, idle, n) for (f, s, idle), n in counts.items()))


def verify_census(fixture: contract.DescriptorFixture, spec_text: str) -> None:
    """Fail closed when production gains, loses or moves a first-prompt response branch."""
    expected = tuple(sorted((e.function, e.site, e.prior_idle, e.count) for e in fixture.census))
    if trace_first_prompt_census(spec_text) != expected:
        raise HostError("r_census_mismatch")


# --------------------------------------------------------------------------- frozen isolated patches
#
# Throwaway Task 0 source only. The load-only operations are the probe's existing allowlisted anchors
# (tools/probe_p11_zed_session_load.py ``_INITIALIZE_*``/``_SESSION_*_BRANCH``); each refusal stub adds
# one first-prompt answer taken verbatim from its registered descriptor.

_LOAD_ONLY_OPERATIONS: tuple[tuple[str, str], ...] = (
    (
        "            # session/load remains P11-FEAT-ZED-RESUME; do not advertise loadSession.\n"
        '            "sessionCapabilities": {},\n',
        '            "loadSession": True,\n            "sessionCapabilities": {},\n',
    ),
    (
        '        if method == "session/prompt":\n'
        "            return await self._handle_session_prompt(request, ownership_slot=ownership_slot)\n",
        '        if method == "session/prompt":\n'
        "            return await self._handle_session_prompt(request, ownership_slot=ownership_slot)\n"
        '        if method == "session/load":\n'
        '            return self._non_turn(success_response(request_id=request.get("id"), result={}), ownership_slot)\n',
    ),
)
_REFUSAL_ANCHOR = "        if session_id in self._active_turns or session_id in self._report_cancels:\n"


def _refusal_operation(descriptor: contract.Descriptor) -> tuple[str, str]:
    if descriptor.wire_class == "result_stop_reason":
        response = f'success_response(request.get("id"), {{"stopReason": {descriptor.stop_reason!r}}})'
    else:
        response = f'error_response(request.get("id"), JsonRpcError(code={descriptor.error_code_name}, message={descriptor.error_message!r}))'
    notice = ""
    if descriptor.notice_text is not None:
        notice = (
            "        with contextlib.suppress(Exception):\n"
            "            await self._outbound.notify(\n"
            f'                "session/update", build_agent_message_chunk_notification(session_id=session_id, text={descriptor.notice_text!r})\n'
            "            )\n"
        )
    stub = (
        f"        # plan117-v5 throwaway refusal stub: {descriptor.descriptor_id}\n"
        '        if getattr(self, "_plan117_v5_prompted", False):\n'
        "            return self._non_turn(error_response(request.get(\"id\"), JsonRpcError(code=INVALID_REQUEST, "
        'message="plan117-v5 stub allows one prompt")), ownership_slot)\n'
        "        self._plan117_v5_prompted = True\n"
        f"{notice}"
        f"        return self._non_turn({response}, ownership_slot)\n"
    )
    return (_REFUSAL_ANCHOR, stub + _REFUSAL_ANCHOR)


def patch_operations(source_kind: str, fixture: contract.DescriptorFixture) -> tuple[tuple[str, str], ...]:
    if source_kind == contract.LOAD_ONLY_STUB:
        return _LOAD_ONLY_OPERATIONS
    descriptors = {item.descriptor_id: item for item in fixture.descriptors}
    descriptor = descriptors.get(source_kind.removeprefix("refusal_stub:"))
    if source_kind not in contract.SOURCE_KINDS or descriptor is None:
        raise HostError("unknown_source_kind")
    return (*_LOAD_ONLY_OPERATIONS, _refusal_operation(descriptor))


def patch_sha256(source_kind: str, fixture: contract.DescriptorFixture) -> str:
    """Identity of the patch itself (its anchor/replacement pairs), independent of base bytes."""
    operations = [list(pair) for pair in patch_operations(source_kind, fixture)]
    return contract.sha256_hex(contract.canonical_json_bytes({"source_kind": source_kind, "operations": operations}))


def render_isolated_spec(spec_bytes: bytes, source_kind: str, fixture: contract.DescriptorFixture) -> bytes:
    """Apply one frozen patch; every anchor must occur exactly once."""
    text = spec_bytes.decode("utf-8")
    for anchor, replacement in patch_operations(source_kind, fixture):
        if text.count(anchor) != 1:
            raise HostError("isolated_patch_anchor_mismatch")
        text = text.replace(anchor, replacement, 1)
    return text.encode("utf-8")


# --------------------------------------------------------------------------- launcher and module-closure report
#
# The hook mechanism (wrap AcpStreamServer.serve/serve_ndjson so the report is written after bootstrap
# imports and before the first byte is read) follows candidate 6208177's launcher.

_LAUNCHER_TEMPLATE = '''"""Plan 11.7 v5 throwaway isolated launcher (Task 0 source only; never production)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

_SOURCE = Path({source!r}).resolve()
_REPORT = Path({report!r})
sys.path.insert(0, str(_SOURCE / "src"))


def _write_module_closure_report() -> None:
    entries = []
    failures = []
    for name, module in sorted(sys.modules.items()):
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue
        try:
            Path(module_file).resolve().relative_to(_SOURCE)
        except ValueError:
            continue  # outside the isolated source root: not part of the closure
        try:
            resolved = Path(module_file).resolve(strict=True)
            relative = resolved.relative_to(_SOURCE)
            payload = resolved.read_bytes()
        except (OSError, ValueError):
            failures.append(name)  # in-root but not inspectable: the closure is incomplete
            continue
        entries.append({{"module_name": name, "resolved_path": str(resolved), "source_relative_path": relative.as_posix(),
                         "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}})
    report = {{"schema": {schema!r}, "pid": os.getpid(), "monotonic_ns": time.monotonic_ns(),
               "entrypoint_module": "optimus.acp.__main__", "source_root": str(_SOURCE), "entries": entries, "inspection_failures": failures}}
    partial = _REPORT.with_name(_REPORT.name + ".partial")
    partial.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    os.replace(partial, _REPORT)


def _install_module_closure_hook() -> None:
    from optimus.acp.server import AcpStreamServer

    reported = []

    def wrap(original):
        async def serve_with_report(self, *args, **kwargs):
            if not reported:
                reported.append(True)
                _write_module_closure_report()
            return await original(self, *args, **kwargs)

        return serve_with_report

    AcpStreamServer.serve = wrap(AcpStreamServer.serve)
    AcpStreamServer.serve_ndjson = wrap(AcpStreamServer.serve_ndjson)


_install_module_closure_hook()

from optimus.acp.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
'''


def render_launcher_bytes(source_root: Path, report_path: Path) -> bytes:
    """A launcher whose hook reports the in-root module closure before the server reads stdin."""
    return _LAUNCHER_TEMPLATE.format(source=str(source_root), report=str(report_path), schema=MODULE_CLOSURE_SCHEMA).encode("utf-8")


_CLOSURE_KEYS = ("schema", "pid", "monotonic_ns", "entrypoint_module", "source_root", "entries", "inspection_failures")
_CLOSURE_ENTRY_KEYS = ("module_name", "resolved_path", "source_relative_path", "size_bytes", "sha256")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MODULE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _closure_error(where: str = "") -> contract.ContractError:
    return contract.ContractError("module_closure_malformed", where)


def parse_closure_report(payload: bytes, *, source_root_canonical: str) -> dict[str, Any]:
    """Strict launcher report → contract closure facts; every entry must lie beneath the isolated root.

    Pure over the captured Windows path text, so it needs no live root after cleanup.
    """
    document = contract.strict_json_loads(payload)
    if type(document) is not dict or set(document) != set(_CLOSURE_KEYS) or document["schema"] != MODULE_CLOSURE_SCHEMA:
        raise _closure_error("$")
    if type(document["source_root"]) is not str or contract.canonicalize_windows_path(document["source_root"]) != source_root_canonical:
        raise _closure_error("$.source_root")
    pid, monotonic = document["pid"], document["monotonic_ns"]
    if type(pid) is not int or pid < 1 or type(monotonic) is not int or monotonic < 0:
        raise _closure_error("$.pid")
    if document["entrypoint_module"] != contract.ENTRYPOINT_MODULE or type(document["entries"]) is not list:
        raise _closure_error("$.entrypoint_module")
    if type(document["inspection_failures"]) is not list or document["inspection_failures"]:
        raise contract.ContractError("module_closure_incomplete", "$.inspection_failures")
    entries = []
    for position, entry in enumerate(document["entries"]):
        where = f"$.entries[{position}]"
        if type(entry) is not dict or set(entry) != set(_CLOSURE_ENTRY_KEYS):
            raise _closure_error(where)
        name, resolved, relative, size, digest = (entry[key] for key in _CLOSURE_ENTRY_KEYS)
        if type(name) is not str or not _MODULE.fullmatch(name) or type(size) is not int or size < 0:
            raise _closure_error(where)
        if type(digest) is not str or not _HEX64.fullmatch(digest) or type(resolved) is not str or type(relative) is not str:
            raise _closure_error(where)
        parts = relative.split("/")
        if any(part in {"", ".", ".."} or "\\" in part or ":" in part for part in parts):
            raise _closure_error(where)
        if contract.canonicalize_windows_path(resolved) != source_root_canonical + "\\" + "\\".join(parts):
            raise _closure_error(where)
        entries.append({"module_name": name, "source_relative_path": relative, "sha256": digest})
    if len({entry["module_name"] for entry in entries}) != len(entries):
        raise _closure_error("$.entries")
    return {"report_monotonic_ns": monotonic, "pid": pid, "entrypoint_module": document["entrypoint_module"],
            "entries": sorted(entries, key=lambda item: item["module_name"])}


# --------------------------------------------------------------------------- wire derivation from relay captures

_RELAY_FILES = ("zed-to-agent.bin", "agent-to-zed.bin", "relay-index.ndjson", "relay-summary.json")
_SESSION = re.compile(r"^session-[0-9a-f]{32}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}$")
_METHOD = re.compile(r"^[A-Za-z_][A-Za-z0-9_/.$-]{0,63}$")
_LOWER_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True, slots=True)
class RelayMessage:
    start: int
    end: int
    message: dict[str, Any]
    text: str


@dataclass(frozen=True, slots=True)
class DerivedWire:
    events: list[dict[str, Any]]
    undecodable: bool
    initialize: dict[str, Any] | None
    relay_valid: bool
    stdin_eof: bool
    child_exit_code: int | None


def parse_ndjson_messages(payload: bytes) -> tuple[list[RelayMessage], bool]:
    """One message per NDJSON line plus an undecodable flag (bad JSON, non-object, unterminated tail)."""
    messages: list[RelayMessage] = []
    undecodable = bool(payload) and not payload.endswith(b"\n")
    offset = 0
    for line in payload.splitlines(keepends=True):
        stripped = line.rstrip(b"\r\n")
        if stripped.strip():
            try:
                decoded = contract.strict_json_loads(stripped)
            except contract.ContractError:
                decoded = _lenient_object(stripped)
                undecodable = True  # strictly invalid (duplicate keys, overflow, ...) but still scanned for signals
            if type(decoded) is dict:
                messages.append(RelayMessage(offset, offset + len(stripped), decoded, stripped.decode("utf-8", "replace")))
            else:
                undecodable = True
        offset += len(line)
    return messages, undecodable


def _lenient_object(payload: bytes) -> dict[str, Any] | None:
    """Permissive decode used only so a strictly invalid line cannot hide a positive signal; never for acceptance."""
    try:
        decoded = json.loads(payload.decode("utf-8", "replace"))
    except ValueError:
        return None
    return decoded if type(decoded) is dict else None


def _prompt_valid(params: Any) -> bool:
    """Production's own first-prompt input validation (spec._handle_session_prompt shape checks + _text_from_content_blocks).

    Only this boolean leaves the collector: no prompt text is retained or promoted.
    """
    from optimus.acp.spec import _text_from_content_blocks

    if type(params) is not dict or type(params.get("sessionId")) is not str or type(params.get("prompt")) is not list:
        return False
    return bool(_text_from_content_blocks(params["prompt"]))


def _member_text(text: str, key: str) -> str | None:
    """Exact source text of one top-level member's value, so an empty-object result keeps its exact bytes."""
    decoder = json.JSONDecoder()
    index = text.index("{") + 1
    while True:
        while text[index] in " \t\r\n,":
            index += 1
        if text[index] == "}":
            return None
        name, index = json.decoder.scanstring(text, index + 1)
        index = text.index(":", index) + 1
        while text[index] in " \t\r\n":
            index += 1
        _value, end = decoder.raw_decode(text, index)
        if name == key:
            return text[index:end]
        index = end


def _session_id(value: Any) -> str | None:
    return value if type(value) is str and _SESSION.fullmatch(value) else None


def wire_event(index: int, direction: str, relay_message: RelayMessage) -> dict[str, Any] | None:
    """Contract wire event for one decoded message, or None for an unrecognized shape."""
    message = relay_message.message
    event: dict[str, Any] = dict.fromkeys(contract._WIRE_KEYS)
    event.update(index=index, direction=direction)
    has_id = "id" in message
    request_id = message.get("id")
    if has_id and not (type(request_id) is int or (type(request_id) is str and _TOKEN.fullmatch(request_id))):
        return None
    params = message["params"] if type(message.get("params")) is dict else {}
    if "method" in message:
        method = message["method"]
        if type(method) is not str or not _METHOD.fullmatch(method):
            return None
        event.update(kind="request" if has_id else "notification", method=method, request_id=request_id if has_id else None,
                     session_id=_session_id(params.get("sessionId")))
        if has_id and direction == "zed_to_agent" and method == "session/prompt":
            event["prompt_valid"] = _prompt_valid(message.get("params"))
        if method == "session/update":
            update = params["update"] if type(params.get("update")) is dict else {}
            kind = update.get("sessionUpdate")
            event["update_kind"] = kind if type(kind) is str and _LOWER_TOKEN.fullmatch(kind) else "unrecognized"
            content = update.get("content")
            if type(content) is dict and type(content.get("text")) is str:
                event["text_sha256"] = contract.sha256_hex(content["text"].encode("utf-8"))
        return event
    if not has_id or ("result" in message) == ("error" in message):
        return None
    body = message.get("result", message.get("error"))
    try:
        body_bytes = contract.canonical_json_bytes(body)
    except ValueError:
        return None  # a non-finite body cannot be hashed canonically: unrecognized, flagged undecodable by the caller
    event.update(kind="response", request_id=request_id, response_sha256=contract.sha256_hex(body_bytes))
    if "result" in message:
        try:
            exact = _member_text(relay_message.text, "result")
        except (ValueError, IndexError):
            exact = None
        event["result_bytes_sha256"] = contract.sha256_hex((exact or "").encode("utf-8"))
        if type(body) is dict:
            event["result_session_id"] = _session_id(body.get("sessionId"))
            stop = body.get("stopReason")
            event["stop_reason"] = stop if type(stop) is str and _LOWER_TOKEN.fullmatch(stop) else None
    else:
        code = body.get("code") if type(body) is dict else None
        if type(code) is not int:
            return None
        event["error_code"] = code
    return event


def _initialize_facts(event: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
    result = message["result"] if type(message.get("result")) is dict else {}
    capabilities = result["agentCapabilities"] if type(result.get("agentCapabilities")) is dict else {}
    session_caps = capabilities["sessionCapabilities"] if type(capabilities.get("sessionCapabilities")) is dict else {}
    load = capabilities.get("loadSession")
    return {"result_sha256": event["response_sha256"], "load_session": load if type(load) is bool else None,
            "has_resume": "resume" in capabilities or "resume" in session_caps}


def derive_wire(relay_dir: Path) -> DerivedWire:
    """Ordered wire events from one relay capture. An integrity failure is reported, never a reason to skip parsing."""
    from tools.plan117_custody_relay import CustodyContractError, verify_relay_capture

    try:
        verify_relay_capture(relay_dir)
        relay_valid = True
    except (CustodyContractError, OSError, ValueError, TypeError):
        relay_valid = False
    chunk_ends: dict[str, list[tuple[int, int]]] = {"zed_to_agent": [], "agent_to_zed": []}
    try:
        for line in (relay_dir / "relay-index.ndjson").read_text(encoding="utf-8").splitlines():
            record = json.loads(line) if line else {}
            if record.get("direction") in chunk_ends and int(record["size"]) > 0:
                chunk_ends[record["direction"]].append((int(record["directional_offset"]) + int(record["size"]), int(record["sequence"])))
    except (OSError, ValueError, KeyError, TypeError):
        relay_valid = False
    ordered: list[tuple[int, int, str, RelayMessage]] = []
    undecodable = False
    for direction, name in (("zed_to_agent", "zed-to-agent.bin"), ("agent_to_zed", "agent-to-zed.bin")):
        path = relay_dir / name
        messages, bad = parse_ndjson_messages(path.read_bytes() if path.is_file() else b"")
        undecodable = undecodable or bad
        for message in messages:
            # Ordered by the global relay sequence of the chunk that carried the message's final byte.
            sequence = next((seq for end, seq in chunk_ends[direction] if end >= message.end), None)
            if sequence is None:
                relay_valid, sequence = False, 1 << 62
            ordered.append((sequence, message.start, direction, message))
    ordered.sort(key=lambda item: (item[0], item[2], item[1]))
    events: list[dict[str, Any]] = []
    initialize = None
    initialize_ids: set[Any] = set()
    for _sequence, _start, direction, message in ordered:
        event = wire_event(len(events), direction, message)
        if event is None:
            undecodable = True
            continue
        events.append(event)
        if event["kind"] == "request" and event["method"] == "initialize" and direction == "zed_to_agent":
            initialize_ids.add(event["request_id"])
        elif event["kind"] == "response" and direction == "agent_to_zed" and event["request_id"] in initialize_ids:
            initialize = _initialize_facts(event, message.message)
    summary: dict[str, Any] = {}
    if relay_valid:
        summary = json.loads((relay_dir / "relay-summary.json").read_text(encoding="utf-8"))
    exit_code = summary.get("child_exit_code")
    return DerivedWire(events, undecodable, initialize, relay_valid, summary.get("zed_to_agent_eof") is True,
                       exit_code if type(exit_code) is int else None)


# --------------------------------------------------------------------------- closed database copies
#
# Zed's binding lives in sidebar_threads(thread_id BLOB PRIMARY KEY, session_id TEXT) (shape confirmed
# against preserved real evidence in candidate 6208177's probe). Copies are read in a private scratch
# copy so even a read-only SQLite open cannot add sidecar files to the retained artifact.

# A non-null binding that is not a session ID stays non-null: it is still a positive binding signal.
UNRECOGNIZED_BINDING = "session-" + "0" * 32


@dataclass(frozen=True, slots=True)
class DatabaseBinding:
    readable: bool
    thread_id: str | None
    session_binding: str | None


def read_database_binding(main_copy: Path, wal_copy: Path | None = None, shm_copy: Path | None = None) -> DatabaseBinding:
    """Thread identity and binding of the single sidebar_threads row in a closed database copy."""
    with tempfile.TemporaryDirectory(prefix="p117v5-db-") as scratch:
        target = Path(scratch) / "db.sqlite"
        shutil.copyfile(main_copy, target)
        for source, suffix in ((wal_copy, "-wal"), (shm_copy, "-shm")):
            if source is not None:
                shutil.copyfile(source, Path(scratch) / f"db.sqlite{suffix}")
        try:
            connection = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
            try:
                rows = connection.execute("SELECT thread_id, session_id FROM sidebar_threads").fetchall()
            finally:
                connection.close()
        except sqlite3.Error:
            return DatabaseBinding(False, None, None)
    bound = {binding for _thread, binding in rows if binding is not None}
    binding = None
    if bound:
        only = next(iter(bound)) if len(bound) == 1 else None
        binding = only if type(only) is str and _SESSION.fullmatch(only) else UNRECOGNIZED_BINDING
    if len(rows) != 1 or type(rows[0][0]) is not bytes or not rows[0][0]:
        return DatabaseBinding(True, None, binding)
    return DatabaseBinding(True, rows[0][0].hex().upper(), binding)


# --------------------------------------------------------------------------- capture-time path custody and run key

PATH_KEY_LOCATOR = "private/path-key.json"
PATH_KEY_SCHEMA = "plan-11-7-v5-path-key-v1"
_KEY_HEX = re.compile(r"^[0-9a-f]{64}$")


def _canonical_text(text: str) -> str:
    """windows-path-v1 is defined for Windows only; every other host fails closed."""
    if sys.platform != "win32":
        raise HostError("path_capture_requires_win32")
    return contract.canonicalize_windows_path(text)


def capture_path_identity(role: str, path: Path, kind: str) -> dict[str, Any]:
    """Strictly resolve an EXISTING absolute path while it exists, and hash it if it is a file."""
    if not Path(path).is_absolute():
        raise HostError("path_not_absolute")
    try:
        resolved = Path(path).resolve(strict=True)
    except OSError:
        raise HostError("path_missing") from None
    if not (resolved.is_file() if kind == "file" else resolved.is_dir()):
        raise HostError("path_kind_mismatch")
    canonical = _canonical_text(str(resolved))
    payload = resolved.read_bytes() if kind == "file" else None
    return {
        "role": role,
        "raw_path": canonical,
        "canonical_path": canonical,
        "kind": kind,
        "sha256": None if payload is None else contract.sha256_hex(payload),
        "size_bytes": None if payload is None else len(payload),
    }


def is_beneath(child: str, parent: str) -> bool:
    """Strict containment on canonical windows-path-v1 text, case-insensitively, at component boundaries."""
    return child.casefold().startswith(parent.casefold().rstrip("\\") + "\\")


def are_disjoint(left: str, right: str) -> bool:
    return left.casefold() != right.casefold() and not is_beneath(left, right) and not is_beneath(right, left)


def load_run_key(run_dir: Path) -> bytes:
    path = run_dir.joinpath(*PATH_KEY_LOCATOR.split("/"))
    if not path.is_file():
        raise HostError("run_key_missing")
    try:
        document = contract.strict_json_loads(path.read_bytes())
    except contract.ContractError:
        raise HostError("run_key_invalid") from None
    if type(document) is not dict or document.get("schema") != PATH_KEY_SCHEMA or set(document) != {"schema", "key_hex"}:
        raise HostError("run_key_invalid")
    if type(document["key_hex"]) is not str or not _KEY_HEX.fullmatch(document["key_hex"]):
        raise HostError("run_key_invalid")
    return bytes.fromhex(document["key_hex"])


def create_run_key(run_dir: Path) -> bytes:
    """Create the per-run private HMAC key once (at prepare). An existing key is reused, never replaced."""
    path = run_dir.joinpath(*PATH_KEY_LOCATOR.split("/"))
    if path.exists():
        return load_run_key(run_dir)
    key = secrets.token_bytes(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contract.canonical_json_bytes({"schema": PATH_KEY_SCHEMA, "key_hex": key.hex()}))
    return key


def private_root_commitments(capture_root: Path, run_key: bytes) -> dict[str, str]:
    """The opaque private-root commitments a reviewed RunSpec pins before the live run."""
    identity = capture_path_identity("capture_root", capture_root, "directory")
    return {"capture_root": contract.commit_path(identity["canonical_path"], run_key)}


# --------------------------------------------------------------------------- collection state machine
#
# One run drives A-prime, the six R cases and prompted A/B through substitutable HostActions and returns ONE
# CollectionBatch for the existing raw-bundle writer. Every source, patch, key and root problem refuses
# before the first launch; after it, a failure is preserved as an aborted run and path custody, the
# restoration check and cleanup still run, in that order.

SCENARIO_RELATIVE = "tests/fixtures/evidence/scenarios/plan117-current-client-gate-v5.toml"
ARTIFACT_SCHEMA = "plan-11-7-v5-collector-artifact-v1"
ZED_LAUNCH_TIMEOUT_SECONDS = 900.0
LAUNCH_CONFIG: dict[str, Any] = {
    "agent_server_name": "optimus",
    "relay": "tools/plan117_custody_relay.py",
    "module_closure_schema": MODULE_CLOSURE_SCHEMA,
    "zed_launch_timeout_seconds": ZED_LAUNCH_TIMEOUT_SECONDS,
    "hermetic_user_data_dir": True,
    "arm_ids": list(contract.ARM_IDS),
}
LAUNCH_CONFIG_SHA256 = contract.sha256_hex(contract.canonical_json_bytes(LAUNCH_CONFIG))
_EMPTY = contract.EMPTY_BYTES_SHA256


@dataclass(frozen=True, slots=True)
class SourceObservation:
    actual_source_commit: str
    actual_source_tree: str
    tracked_diff_sha256: str
    untracked_digest_sha256: str


@dataclass(frozen=True, slots=True)
class ZedIdentity:
    executable: Path
    executable_sha256: str
    cli_version: str
    app_version: str
    source_revision: str


@dataclass(frozen=True, slots=True)
class SourcePreparation:
    source_kind: str
    source_root: Path
    launcher_path: Path
    closure_report_path: Path
    normal_source_root: Path
    fixture: contract.DescriptorFixture
    source_commit: str


@dataclass(frozen=True, slots=True)
class LaunchRequest:
    arm_id: str
    launch_id: str
    source_kind: str
    source_root: Path
    launcher_path: Path
    closure_report_path: Path
    profile_root: Path
    workspace_root: Path
    relay_dir: Path
    fixture: contract.DescriptorFixture


@dataclass(frozen=True, slots=True)
class LaunchResult:
    started_ns: int
    ended_ns: int
    zed_exit_code: int | None
    timed_out: bool


@dataclass(frozen=True, slots=True)
class DatabaseLocation:
    main: Path
    wal: Path | None
    shm: Path | None


@dataclass(frozen=True, slots=True)
class HostActions:
    source_facts: Callable[[Path], SourceObservation]
    normal_source_digest: Callable[[Path], str]
    base_spec_bytes: Callable[[Path, str], bytes]
    zed_identity: Callable[[], ZedIdentity]
    prepare_source: Callable[[SourcePreparation], None]
    launch: Callable[[LaunchRequest], LaunchResult]
    locate_database: Callable[[Path], DatabaseLocation]
    remove_tree: Callable[[Path], None]
    monotonic_ns: Callable[[], int]
    wall_now: Callable[[], str]


@dataclass(frozen=True, slots=True)
class CollectInputs:
    context: RunContext
    run_spec: contract.RunSpec
    fixture: contract.DescriptorFixture
    descriptor_fixture_sha256: str
    normal_source_root: Path
    scratch_parent: Path


def launch_ids_for(arm_id: str) -> tuple[str, str]:
    return contract.PROMPTED_LAUNCH_IDS if arm_id == contract.ARM_PROMPTED else contract.REOPEN_LAUNCH_IDS


class _Emitter:
    """Writes artifacts beneath the run directory and records one observation per transition."""

    def __init__(self, context: RunContext, actions: HostActions) -> None:
        self.context = context
        self.actions = actions
        self.run_dir = context.capture_root / context.run_id
        self.observations: list[Observation] = []
        self.artifacts: list[CapturedArtifact] = []

    def artifact(self, role: str, locator: str, payload: bytes | None, media_type: str) -> CapturedArtifact:
        path = self.run_dir.joinpath(*locator.split("/"))
        if payload is None:
            payload = path.read_bytes()
        else:
            if path.exists():
                raise HostError("artifact_exists")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        item = CapturedArtifact(role=role, media_type=media_type, relative_locator=locator, sha256=contract.sha256_hex(payload), size_bytes=len(payload))
        self.artifacts.append(item)
        return item

    def observe(self, kind: str, item: CapturedArtifact, arm_id: str = "", launch_id: str = "") -> None:
        self.observations.append(Observation(
            schema=OBSERVATION_SCHEMA, scenario_id=self.context.scenario_id, run_id=self.context.run_id,
            collector_id=COLLECTOR_ID, sequence=len(self.observations),
            monotonic_offset_ns=max(self.actions.monotonic_ns() - self.context.monotonic_origin_ns, 0),
            observed_at=self.actions.wall_now(), observation_kind=f"plan117_v5_{kind}",
            correlation=(("arm_id", arm_id), ("launch_id", launch_id)), artifact_role=item.role,
            artifact_sha256=item.sha256, reason_code=None,
        ))

    def document(self, kind: str, role: str, locator: str, body: dict[str, Any], arm_id: str = "", launch_id: str = "") -> None:
        payload = contract.canonical_json_bytes({"schema": ARTIFACT_SCHEMA, "kind": kind, **body})
        self.observe(kind, self.artifact(role, locator, payload, "application/json"), arm_id, launch_id)


def _preflight(inputs: CollectInputs, actions: HostActions, run_key: bytes) -> tuple[bytes, SourceObservation]:
    spec = inputs.run_spec
    if spec.run_id != inputs.context.run_id or spec.evidence_kind != contract.EVIDENCE_KIND_GATE:
        raise HostError("run_spec_mismatch")
    if inputs.descriptor_fixture_sha256 != spec.descriptor_fixture_sha256 or LAUNCH_CONFIG_SHA256 != spec.launch_config_sha256:
        raise HostError("run_spec_mismatch")
    if tuple(sorted(contract.REQUIRED_MODULE_PATHS)) != spec.required_modules:
        raise HostError("run_spec_mismatch")
    if any(patch_sha256(kind, inputs.fixture) != spec.patch_sha256s[kind] for kind in contract.SOURCE_KINDS):
        raise HostError("patch_identity_mismatch")
    if private_root_commitments(inputs.context.capture_root, run_key) != dict(spec.private_root_commitments):
        raise HostError("private_root_commitment_mismatch")
    source = actions.source_facts(inputs.normal_source_root)
    if (source.actual_source_commit, source.actual_source_tree) != (spec.source_commit, spec.source_tree):
        raise HostError("source_commit_mismatch")
    if (source.tracked_diff_sha256, source.untracked_digest_sha256) != (_EMPTY, _EMPTY):
        raise HostError("source_dirty")
    base_spec = actions.base_spec_bytes(inputs.normal_source_root, spec.source_commit)
    verify_census(inputs.fixture, base_spec.decode("utf-8"))
    return base_spec, source


def collect_current_client_gate(inputs: CollectInputs, actions: HostActions) -> CollectionBatch:
    context, spec = inputs.context, inputs.run_spec
    emit = _Emitter(context, actions)
    run_key = load_run_key(emit.run_dir)
    base_spec, source = _preflight(inputs, actions, run_key)
    normal_root = Path(inputs.normal_source_root)
    run_root = Path(inputs.scratch_parent) / f"p117v5-{context.run_id}"
    if run_root.exists():
        raise HostError("run_root_exists")
    run_root.mkdir()
    try:

        emit.document("run_start", "plan117_v5_run_start", "artifacts/plan117/run-start.json", {
            "run_id": context.run_id, "approval_id": spec.approval_id,
            "wall_started_at": actions.wall_now(), "monotonic_started_ns": actions.monotonic_ns()})
        emit.observe("path_key", emit.artifact("plan117_v5_path_key", PATH_KEY_LOCATOR, None, "application/json"))
        emit.document("source", "plan117_v5_source", "artifacts/plan117/source.json", {
            "historical_pins": dict(contract.HISTORICAL_PINS), "approved_source_commit": spec.source_commit,
            "actual_source_commit": source.actual_source_commit, "actual_source_tree": source.actual_source_tree,
            "tracked_diff_sha256": source.tracked_diff_sha256, "untracked_digest_sha256": source.untracked_digest_sha256,
            "normal_source_sha256_before": actions.normal_source_digest(normal_root),
            "descriptor_fixture_sha256": inputs.descriptor_fixture_sha256, "launch_config_sha256": LAUNCH_CONFIG_SHA256,
            "budget_policy_sha256": spec.budget_policy_sha256})
        zed = actions.zed_identity()
        identities = [capture_path_identity("zed_executable", zed.executable, "file")]
        if identities[0]["sha256"] != zed.executable_sha256:
            raise HostError("zed_identity_mismatch")
        emit.document("client", "plan117_v5_client", "artifacts/plan117/client.json", {
            "executable_sha256": zed.executable_sha256, "cli_version": zed.cli_version,
            "app_version": zed.app_version, "source_revision": zed.source_revision})
        identities += [capture_path_identity("capture_root", context.capture_root, "directory"),
                       capture_path_identity("normal_source_root", normal_root, "directory"),
                       capture_path_identity("run_root", run_root, "directory")]
        run_root_text = identities[-1]["canonical_path"]
        if not all(are_disjoint(item["canonical_path"], run_root_text) for item in identities[1:3]):
            raise HostError("run_root_overlap")

        sources: dict[str, tuple[Path, Path, Path]] = {}
        records = []
        for kind in contract.SOURCE_KINDS:
            token = kind.replace(":", "-").replace("_", "-")
            source_root = run_root / "src" / token
            launcher = run_root / "build" / token / "launcher.py"
            report = run_root / "build" / token / "module-closure.json"
            source_root.mkdir(parents=True)
            actions.prepare_source(SourcePreparation(kind, source_root, launcher, report, normal_root, inputs.fixture, spec.source_commit))
            spec_bytes = source_root.joinpath("src", "optimus", "acp", "spec.py").read_bytes()
            if spec_bytes != render_isolated_spec(base_spec, kind, inputs.fixture):
                raise HostError("isolated_patch_mismatch")
            if launcher.read_bytes() != render_launcher_bytes(source_root, report):
                raise HostError("launcher_mismatch")
            sources[kind] = (source_root, launcher, report)
            identities += [capture_path_identity(f"isolated_source:{kind}", source_root, "directory"),
                           capture_path_identity(f"launcher:{kind}", launcher, "file")]
            records.append({"source_kind": kind, "root_role": f"isolated_source:{kind}", "launcher_role": f"launcher:{kind}",
                            "launcher_sha256": contract.sha256_hex(launcher.read_bytes()), "spec_sha256": contract.sha256_hex(spec_bytes),
                            "patch_sha256": patch_sha256(kind, inputs.fixture)})
        emit.document("isolated_sources", "plan117_v5_isolated_sources", "artifacts/plan117/isolated-sources.json", {"sources": records})
        for arm_id in contract.ARM_IDS:
            for leaf in ("profile", "workspace"):
                directory = run_root / "arms" / arm_id / leaf
                directory.mkdir(parents=True)
                identities.append(capture_path_identity(f"{leaf}:{arm_id}", directory, "directory"))
        if not all(is_beneath(item["canonical_path"], run_root_text) for item in identities if item["role"].split(":")[0] in {"isolated_source", "launcher", "profile", "workspace"}):
            raise HostError("root_escape")
    except (HostError, OSError, ValueError):
        # Refused before any launch: leave no scratch behind (the run directory keeps what was recorded).
        try:
            actions.remove_tree(run_root)
        except OSError:
            pass
        raise

    aborted = None
    try:
        for arm_id in contract.ARM_IDS:
            for launch_id in launch_ids_for(arm_id):
                _collect_launch(emit, actions, inputs.fixture, run_root, sources, arm_id, launch_id, identities)
    except (HostError, OSError, ValueError, sqlite3.Error) as exc:
        code = exc.code if isinstance(exc, HostError) and _LOWER_TOKEN.fullmatch(exc.code) else "host_action_failed"
        aborted = {"reason_code": code, "stage": "launch"}

    emit.document("path_custody", "plan117_v5_path_custody", "artifacts/plan117/path-custody.json", {
        "captured_monotonic_ns": actions.monotonic_ns(), "identities": sorted(identities, key=lambda item: item["role"])})
    emit.document("restoration", "plan117_v5_restoration", "artifacts/plan117/restoration.json", {
        "normal_source_sha256_after": actions.normal_source_digest(normal_root)})
    started = actions.monotonic_ns()
    try:
        actions.remove_tree(run_root)
        removed = True
    except OSError:
        removed = False
    emit.document("cleanup", "plan117_v5_cleanup", "artifacts/plan117/cleanup.json", {
        "started_monotonic_ns": started, "ended_monotonic_ns": actions.monotonic_ns(),
        "targets": [{"role": "run_root", "removed": removed, "absent_after": not run_root.exists()}]})
    emit.document("run_end", "plan117_v5_run_end", "artifacts/plan117/run-end.json", {
        "wall_ended_at": actions.wall_now(), "monotonic_ended_ns": actions.monotonic_ns(), "aborted": aborted})
    return CollectionBatch(collector_id=COLLECTOR_ID, contract_version=CONTRACT_VERSION,observations=tuple(emit.observations), artifacts=tuple(emit.artifacts))


def _collect_launch(emit: _Emitter, actions: HostActions, fixture: contract.DescriptorFixture, run_root: Path,
                    sources: dict[str, tuple[Path, Path, Path]], arm_id: str, launch_id: str, identities: list[dict[str, Any]]) -> None:
    kind = contract.source_kind_for_arm(arm_id)
    source_root, launcher, report = sources[kind]
    report.unlink(missing_ok=True)
    profile = run_root / "arms" / arm_id / "profile"
    relay_dir = run_root / "relay" / arm_id / launch_id
    result = actions.launch(LaunchRequest(arm_id, launch_id, kind, source_root, launcher, report, profile,
                                          run_root / "arms" / arm_id / "workspace", relay_dir, fixture))
    base = f"artifacts/plan117/arms/{arm_id}/{launch_id}"
    for name in _RELAY_FILES:
        path = relay_dir / name
        emit.artifact(f"plan117_v5_relay:{arm_id}:{launch_id}:{name}", f"{base}/relay/{name}", path.read_bytes() if path.is_file() else b"", "application/octet-stream")
    emit.artifact(f"plan117_v5_closure:{arm_id}:{launch_id}", f"{base}/module-closure.json", report.read_bytes() if report.is_file() else b"", "application/json")
    emit.document("launch", f"plan117_v5_launch:{arm_id}:{launch_id}", f"{base}/launch.json", {
        "arm_id": arm_id, "launch_id": launch_id, "source_kind": kind, "started_ns": result.started_ns,
        "ended_ns": result.ended_ns, "zed_exit_code": result.zed_exit_code, "timed_out": result.timed_out}, arm_id, launch_id)
    label = f"after_{launch_id}"
    location = actions.locate_database(profile)
    role = f"database:{arm_id}:{label}"
    main = capture_path_identity(role, location.main, "file")
    profile_text = next(item["canonical_path"] for item in identities if item["role"] == f"profile:{arm_id}")
    if not is_beneath(main["canonical_path"], profile_text):
        raise HostError("database_outside_profile")
    identities.append(main)
    db_base = f"artifacts/plan117/arms/{arm_id}/{label}/db"
    emit.artifact(f"plan117_v5_db:{arm_id}:{label}:main", f"{db_base}/db.sqlite", location.main.read_bytes(), "application/vnd.sqlite3")
    presence = {"main": True}
    for file_role, path in (("wal", location.wal), ("shm", location.shm)):
        presence[file_role] = path is not None and path.is_file()
        if path is not None and presence[file_role]:
            identities.append(capture_path_identity(f"{role}:{file_role}", path, "file"))
            emit.artifact(f"plan117_v5_db:{arm_id}:{label}:{file_role}", f"{db_base}/db.sqlite-{file_role}", path.read_bytes(), "application/octet-stream")
    emit.document("checkpoint", f"plan117_v5_checkpoint:{arm_id}:{label}", f"artifacts/plan117/arms/{arm_id}/{label}/checkpoint.json", {
        "arm_id": arm_id, "label": label, "copied_monotonic_ns": actions.monotonic_ns(), "presence": presence}, arm_id, launch_id)


# --------------------------------------------------------------------------- raw manifest derivation
#
# Rebuilt from the verified batch alone: every artifact is rehashed against its CapturedArtifact record and a
# mismatch is recorded as a custody failure (never silently trusted); wire facts are re-derived from relay
# bytes, closure from the launcher report, bindings from closed database copies, paths from capture-time custody.

_HEAD_KINDS = ("run_start", "path_key", "source", "client", "isolated_sources")
_TAIL_KINDS = ("path_custody", "restoration", "cleanup", "run_end")


def _expected_transitions() -> list[tuple[str, str, str]]:
    tokens = [(kind, "", "") for kind in _HEAD_KINDS]
    for arm_id in contract.ARM_IDS:
        for launch_id in launch_ids_for(arm_id):
            tokens += [("launch", arm_id, launch_id), ("checkpoint", arm_id, launch_id)]
    return tokens


def _transitions_valid(batch: CollectionBatch, aborted: bool) -> bool:
    tokens = []
    previous = -1
    for position, observation in enumerate(batch.observations):
        if observation.sequence != position or observation.monotonic_offset_ns < previous or observation.collector_id != COLLECTOR_ID:
            return False
        previous = observation.monotonic_offset_ns
        correlation = dict(observation.correlation)
        tokens.append((observation.observation_kind.removeprefix("plan117_v5_"), correlation.get("arm_id", ""), correlation.get("launch_id", "")))
    tail = [(kind, "", "") for kind in _TAIL_KINDS]
    body = tokens[: len(tokens) - len(tail)]
    if tokens[len(body):] != tail:
        return False
    expected = _expected_transitions()
    return body == expected[: len(body)] and len(body) >= len(_HEAD_KINDS) if aborted else body == expected


class _Artifacts:
    def __init__(self, run_dir: Path, batch: CollectionBatch, failures: list[str]) -> None:
        self.run_dir, self.failures = run_dir, failures
        self.by_role: dict[str, CapturedArtifact] = {}
        for item in batch.artifacts:
            if item.role in self.by_role:
                failures.append("artifact_role_duplicate")
            self.by_role[item.role] = item

    def bytes(self, role: str) -> bytes | None:
        item = self.by_role.get(role)
        if item is None:
            return None
        parts = item.relative_locator.split("/")
        path = self.run_dir.joinpath(*parts)
        if any(part in {"", ".", ".."} for part in parts) or not path.resolve().is_relative_to(self.run_dir.resolve()):
            self.failures.append("artifact_locator_invalid")
            return None
        if not path.is_file():
            self.failures.append("artifact_missing")
            return None
        try:
            payload = path.read_bytes()
        except OSError:
            self.failures.append("artifact_unreadable")
            return None
        if contract.sha256_hex(payload) != item.sha256 or len(payload) != item.size_bytes:
            self.failures.append("artifact_digest_mismatch")
        return payload

    def document(self, role: str, kind: str, keys: tuple[str, ...]) -> dict[str, Any]:
        """A collector JSON artifact, or all-null fields plus a recorded custody failure. Never raises, so a broken
        unrelated artifact cannot stop derivation before captured relay/database signals reach the STOP scan."""
        payload = self.bytes(role)
        try:
            document = contract.strict_json_loads(payload if payload is not None else b"")
        except contract.ContractError:
            document = None
        if type(document) is not dict or set(document) != {"schema", "kind", *keys} or (document.get("schema"), document.get("kind")) != (ARTIFACT_SCHEMA, kind):
            self.failures.append("artifact_malformed")
            return {"schema": None, "kind": None, **dict.fromkeys(keys)}
        return document


_SOURCE_DOC_KEYS = ("historical_pins", "approved_source_commit", "actual_source_commit", "actual_source_tree", "tracked_diff_sha256",
                    "untracked_digest_sha256", "normal_source_sha256_before", "descriptor_fixture_sha256", "launch_config_sha256", "budget_policy_sha256")


def derive_raw_document(context: RunContext, batches: Sequence[CollectionBatch], *, provisional_sha256: str,
                        ingress_failures: Sequence[str] = ()) -> dict[str, Any]:
    if len(batches) != 1 or batches[0].collector_id != COLLECTOR_ID:
        raise HostError("collector_batch_mismatch")
    batch = batches[0]
    run_dir = context.capture_root / context.run_id
    failures: list[str] = list(ingress_failures)
    art = _Artifacts(run_dir, batch, failures)
    start = art.document("plan117_v5_run_start", "run_start", ("run_id", "approval_id", "wall_started_at", "monotonic_started_ns"))
    end = art.document("plan117_v5_run_end", "run_end", ("wall_ended_at", "monotonic_ended_ns", "aborted"))
    if start["run_id"] != context.run_id:
        failures.append("run_start_mismatch")
    if not _transitions_valid(batch, end["aborted"] is not None):
        failures.append("transition_chronology_invalid")
    run_key: bytes | None = None
    if art.bytes("plan117_v5_path_key") is None:
        failures.append("run_key_missing")
    else:
        try:
            run_key = load_run_key(run_dir)
        except HostError:
            failures.append("run_key_invalid")
    source = art.document("plan117_v5_source", "source", _SOURCE_DOC_KEYS)
    restoration = art.document("plan117_v5_restoration", "restoration", ("normal_source_sha256_after",))
    client = art.document("plan117_v5_client", "client", ("executable_sha256", "cli_version", "app_version", "source_revision"))
    isolated = art.document("plan117_v5_isolated_sources", "isolated_sources", ("sources",))
    custody = art.document("plan117_v5_path_custody", "path_custody", ("captured_monotonic_ns", "identities"))
    cleanup = art.document("plan117_v5_cleanup", "cleanup", ("started_monotonic_ns", "ended_monotonic_ns", "targets"))
    identities = custody["identities"] if type(custody["identities"]) is list else []
    roots = {item["role"]: item["canonical_path"] for item in identities
             if type(item) is dict and type(item.get("role")) is str and type(item.get("canonical_path")) is str}
    if len(roots) != len(identities):
        failures.append("path_custody_malformed")
    arms = []
    for arm_id in contract.ARM_IDS:
        launches, checkpoints = [], []
        for launch_id in launch_ids_for(arm_id):
            if f"plan117_v5_launch:{arm_id}:{launch_id}" not in art.by_role:
                break
            launches.append(_derive_launch(art, arm_id, launch_id, roots))
            if f"plan117_v5_checkpoint:{arm_id}:after_{launch_id}" not in art.by_role:
                break
            checkpoints.append(_derive_checkpoint(art, arm_id, launch_id))
        if not launches:
            break
        arms.append({"arm_id": arm_id, "profile_role": f"profile:{arm_id}", "workspace_role": f"workspace:{arm_id}", "launches": launches, "checkpoints": checkpoints})
    bundle = json.loads((run_dir / "raw-bundle.json").read_text(encoding="utf-8"))
    return {
        "schema": contract.RAW_SCHEMA, "evidence_kind": contract.EVIDENCE_KIND_GATE, "scenario_id": context.scenario_id,
        "scenario_sha256": context.scenario_sha256, "run_id": context.run_id, "approval_id": start["approval_id"],
        "raw_bundle_sha256": bundle["bundle_sha256"], "provisional_classification_sha256": provisional_sha256,
        "aborted": end["aborted"], "custody_failures": sorted(set(failures)),
        "run_window": {"wall_started_at": start["wall_started_at"], "wall_ended_at": end["wall_ended_at"],
                       "monotonic_started_ns": start["monotonic_started_ns"], "monotonic_ended_ns": end["monotonic_ended_ns"]},
        "source": {**{key: source[key] for key in _SOURCE_DOC_KEYS}, "normal_source_sha256_after": restoration["normal_source_sha256_after"]},
        "client": {"executable_role": "zed_executable", **{key: client[key] for key in ("executable_sha256", "cli_version", "app_version", "source_revision")}},
        "isolated_sources": isolated["sources"], "path_identities": custody["identities"], "path_commitment_key_hex": None if run_key is None else run_key.hex(),
        "arms": arms,
        "custody": {"path_custody_monotonic_ns": custody["captured_monotonic_ns"],
                    "cleanup": {key: cleanup[key] for key in ("started_monotonic_ns", "ended_monotonic_ns", "targets")}},
    }


def _derive_launch(art: _Artifacts, arm_id: str, launch_id: str, roots: dict[Any, Any]) -> dict[str, Any]:
    record = art.document(f"plan117_v5_launch:{arm_id}:{launch_id}", "launch", ("arm_id", "launch_id", "source_kind", "started_ns", "ended_ns", "zed_exit_code", "timed_out"))
    if (record["arm_id"], record["launch_id"]) != (arm_id, launch_id):
        art.failures.append("launch_record_mismatch")
    with tempfile.TemporaryDirectory(prefix="p117v5-relay-") as scratch:
        for name in _RELAY_FILES:
            payload = art.bytes(f"plan117_v5_relay:{arm_id}:{launch_id}:{name}")
            if payload:
                (Path(scratch) / name).write_bytes(payload)
        wire = derive_wire(Path(scratch))
    if not wire.relay_valid:
        art.failures.append("relay_capture_invalid")
    closure = None
    closure_payload = art.bytes(f"plan117_v5_closure:{arm_id}:{launch_id}")
    root_text = roots.get(f"isolated_source:{record['source_kind']}")
    if closure_payload and type(root_text) is str:
        try:
            closure = parse_closure_report(closure_payload, source_root_canonical=root_text)
        except contract.ContractError:
            art.failures.append("module_closure_malformed")
    if record["timed_out"] is True:
        mechanism = "forced_kill"
    elif record["timed_out"] is False and wire.relay_valid and wire.stdin_eof:
        mechanism = "clean_eof"
    else:
        mechanism = "unknown"
    events = wire.events
    requests = [e for e in events if e["kind"] == "request" and e["direction"] == "zed_to_agent"]
    return {
        "launch_id": launch_id, "source_kind": record["source_kind"],
        "monotonic_started_ns": record["started_ns"], "monotonic_ended_ns": record["ended_ns"],
        "module_closure": closure, "initialize": wire.initialize, "wire": events,
        "counts": {
            "initialize": sum(e["method"] == "initialize" for e in requests),
            "session_new": sum(e["method"] == "session/new" for e in requests),
            "session_load": sum(e["method"] == "session/load" for e in requests),
            "session_prompt": sum(e["method"] == "session/prompt" for e in requests),
            "session_update": sum(e["kind"] == "notification" and e["direction"] == "agent_to_zed" and e["method"] == "session/update" for e in events),
        },
        "undecodable_bytes": wire.undecodable,
        "shutdown": {"mechanism": mechanism, "agent_stdin_eof": wire.stdin_eof, "child_exit_code": wire.child_exit_code, "zed_exit_code": record["zed_exit_code"]},
    }


def _derive_checkpoint(art: _Artifacts, arm_id: str, launch_id: str) -> dict[str, Any]:
    label = f"after_{launch_id}"
    record = art.document(f"plan117_v5_checkpoint:{arm_id}:{label}", "checkpoint", ("arm_id", "label", "copied_monotonic_ns", "presence"))
    presence_known = type(record["presence"]) is dict
    presence = record["presence"] if presence_known else {}
    files, copies = [], {}
    with tempfile.TemporaryDirectory(prefix="p117v5-dbcopy-") as scratch:
        for file_role in ("main", "shm", "wal"):
            role = f"plan117_v5_db:{arm_id}:{label}:{file_role}"
            # Presence is derived from what was captured; the record's metadata can be wrong but cannot hide a copy.
            captured = role in art.by_role
            if not presence_known or (presence.get(file_role) is True) != captured:
                art.failures.append("checkpoint_presence_mismatch")
            payload = art.bytes(role) if captured else None
            if payload is not None:
                copies[file_role] = Path(scratch) / f"db.sqlite-{file_role}"
                copies[file_role].write_bytes(payload)
            files.append({
                "file_role": file_role, "presence": "present" if payload is not None else "absent",
                "path_role": None if payload is None else (f"database:{arm_id}:{label}" if file_role == "main" else f"database:{arm_id}:{label}:{file_role}"),
                "copy_sha256": _EMPTY if payload is None else contract.sha256_hex(payload)})
        binding = read_database_binding(copies["main"], copies.get("wal"), copies.get("shm")) if "main" in copies else DatabaseBinding(False, None, None)
    return {"label": label, "copied_monotonic_ns": record["copied_monotonic_ns"], "files": files, "readable": binding.readable,
            "thread_id": binding.thread_id, "session_binding": binding.session_binding, "closed_copy": True}


# --------------------------------------------------------------------------- two-phase redaction
#
# This completes the redaction emission candidate 6208177 deferred. Phase 1 (no receipt) stages the sanitized
# manifest and redaction report for private review and writes the private raw manifest and path mapping
# beside the raw bundle. Phase 2 recomputes everything, requires byte-equal staged derivatives and an
# accepting receipt bound to every hash, then promotes manifest, report and attestation in one rename.
# Promotion is about privacy eligibility, not the verdict: STOP and INVALID evidence is promotable too.

RAW_MANIFEST_LOCATOR = "private/raw-manifest.json"
MAPPING_LOCATOR = "private/path-mapping.json"
SANITIZED_NAME = "manifest.json"
REPORT_NAME = "redaction-report.json"
ATTESTATION_NAME = "redaction-attestation.json"


@dataclass(frozen=True, slots=True)
class StagedRedaction:
    status: str
    gate: contract.GateVerificationResult
    raw: contract.Plan117RawManifest | None
    raw_manifest_sha256: str | None
    mapping_sha256: str | None
    sanitized_bytes: bytes | None
    report_bytes: bytes | None


def _write_once(path: Path, payload: bytes) -> None:
    """Write an immutable record; an existing one must already hold exactly these bytes."""
    if path.exists():
        if path.read_bytes() != payload:
            raise HostError("immutable_mismatch")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.partial-{secrets.token_hex(8)}")
    partial.write_bytes(payload)
    os.replace(partial, path)


_BUNDLE_KEYS = ("schema", "complete", "scenario_id", "run_id", "scenario_sha256", "batches", "bundle_sha256")
_BATCH_KEYS = ("collector_id", "contract_version", "observations", "artifacts")
_OBSERVATION_KEYS = ("schema", "scenario_id", "run_id", "collector_id", "sequence", "monotonic_offset_ns", "observed_at",
                     "observation_kind", "correlation", "artifact_role", "artifact_sha256", "reason_code")
_ARTIFACT_KEYS = ("role", "media_type", "relative_locator", "sha256", "size_bytes")
_LOCATOR = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9._/-]+$")


_LOADER_ENVELOPE_CODES = frozenset({"relative_path_rejected", "partial_stage", "bundle_missing", "invalid_json", "unknown_schema",
                                    "foreign_run_id", "foreign_scenario_id", "digest_mismatch"})


def strict_bundle_ingress(context: RunContext) -> tuple[tuple[str, ...], tuple[CollectionBatch, ...] | None]:
    """Closed-schema check of the raw bundle bytes BEFORE the shared loader's int()/str() normalization.

    Returns fixed codes (empty when clean) and, only when the outer envelope verifies on its own (schema, completeness,
    run, scenario, scenario digest, bundle digest), batches built from the exactly-typed KNOWN fields of items bound to
    this run. Unknown keys and malformed containers are recorded; an item with an invalid known field is dropped and
    recorded. Never raises, never reads an artifact: a violation stays a custody failure while
    derivation continues, so malformed or foreign metadata can neither be accepted nor hide an independently captured STOP.
    """
    run_dir = context.capture_root / context.run_id
    codes: set[str] = set()

    def bad() -> None:
        codes.add("raw_bundle_ingress_invalid")

    def text(value: Any) -> bool:
        return type(value) is str

    def count(value: Any) -> bool:
        return type(value) is int and value >= 0

    try:
        payload = (run_dir / "raw-bundle.json").read_bytes()
        document = json.loads(payload)
    except (OSError, ValueError):
        return ("raw_bundle_ingress_invalid",), None
    try:
        contract.strict_json_loads(payload)
    except contract.ContractError:
        bad()
    envelope = {key: value for key, value in document.items() if key != "bundle_sha256"} if type(document) is dict else {}
    if (not envelope or "bundle_sha256" not in document or document.get("complete") is not True or type(document.get("batches")) is not list
            or (document.get("schema"), document.get("run_id"), document.get("scenario_id"), document.get("scenario_sha256"))
            != (RAW_BUNDLE_SCHEMA, context.run_id, context.scenario_id, context.scenario_sha256)
            or document["bundle_sha256"] != _payload_sha256(envelope)):
        return ("raw_bundle_ingress_invalid",), None
    if set(document) != set(_BUNDLE_KEYS):
        bad()
    batches = []
    for batch in document["batches"]:
        # Attribution needs only the batch identity; each container and item is then judged on its own, so malformed
        # observation metadata or an unknown key is recorded without erasing an otherwise valid artifact binding.
        if type(batch) is not dict or not text(batch.get("collector_id")) or not text(batch.get("contract_version")):
            bad()
            continue
        if set(batch) != set(_BATCH_KEYS):
            bad()
        if batch["contract_version"] != CONTRACT_VERSION:
            codes.add("raw_bundle_identity_mismatch")
        containers: dict[str, Any] = {}
        for key in ("observations", "artifacts"):
            containers[key] = batch.get(key)
            if type(containers[key]) is not list:
                bad()
                containers[key] = []
        observations, artifacts = [], []
        for observation in containers["observations"]:
            if type(observation) is not dict or not set(_OBSERVATION_KEYS) <= set(observation):
                bad()
                continue
            if set(observation) != set(_OBSERVATION_KEYS):
                bad()
            correlation = observation["correlation"]
            if not (all(text(observation[key]) for key in ("schema", "scenario_id", "run_id", "collector_id", "observed_at", "observation_kind"))
                    and count(observation["sequence"]) and count(observation["monotonic_offset_ns"])
                    and all(observation[key] is None or text(observation[key]) for key in ("artifact_role", "artifact_sha256", "reason_code"))
                    and type(correlation) is list
                    and all(type(pair) is list and len(pair) == 2 and text(pair[0]) and text(pair[1]) for pair in correlation)):
                bad()
                continue
            if (observation["schema"], observation["run_id"], observation["scenario_id"]) != (OBSERVATION_SCHEMA, context.run_id, context.scenario_id):
                codes.add("raw_bundle_identity_mismatch")
                continue
            observations.append(Observation(**{key: observation[key] for key in _OBSERVATION_KEYS if key != "correlation"},
                                            correlation=tuple((key, value) for key, value in correlation)))
        for artifact in containers["artifacts"]:
            if type(artifact) is not dict or not set(_ARTIFACT_KEYS) <= set(artifact):
                bad()
                continue
            if set(artifact) != set(_ARTIFACT_KEYS):
                bad()
            locator = artifact["relative_locator"]
            if not (text(locator) and _LOCATOR.fullmatch(locator) and "\\" not in locator
                    and run_dir.joinpath(*locator.split("/")).resolve().is_relative_to(run_dir.resolve())):
                codes.add("artifact_locator_invalid")
                continue
            if not (text(artifact["role"]) and text(artifact["media_type"]) and text(artifact["sha256"])
                    and _HEX64.fullmatch(artifact["sha256"]) and count(artifact["size_bytes"])):
                bad()
                continue
            artifacts.append(CapturedArtifact(**{key: artifact[key] for key in _ARTIFACT_KEYS}))
        batches.append(CollectionBatch(collector_id=batch["collector_id"], contract_version=batch["contract_version"],
                                       observations=tuple(observations), artifacts=tuple(artifacts)))
    return tuple(sorted(codes)), tuple(batches)


def compute_redaction(context: RunContext, *, identity_tokens: Sequence[str]) -> StagedRedaction:
    """Deterministic raw -> sanitized -> report from the verified bundle; writes only the private records."""
    run_dir = context.capture_root / context.run_id
    ingress, batches = strict_bundle_ingress(context)
    try:
        load_verified_raw_bundle(context=context, bundle_path=run_dir / "raw-bundle.json")
    except (TypeError, KeyError, ValueError) as exc:
        # The shared loader's envelope verdict stands; past a verified envelope only its per-item conversion can fail,
        # which ingress already recorded. Fixed codes only: a conversion message would echo the malformed value.
        code = exc.args[0] if type(exc) is ValueError and exc.args and isinstance(exc.args[0], str) and exc.args[0] in _LOADER_ENVELOPE_CODES else None
        if code is not None or batches is None:
            raise HostError(code or "bundle_invalid") from None
    if batches is None:
        raise HostError("bundle_invalid")
    provisional = run_dir / "provisional-result.json"
    if not provisional.is_file():
        raise HostError("provisional_missing")
    raw_document = derive_raw_document(context, batches, provisional_sha256=contract.sha256_hex(provisional.read_bytes()), ingress_failures=ingress)
    gate = contract.reduce_document(raw_document, layer="raw")
    try:
        raw = contract.parse_raw_manifest(raw_document)
    except contract.ContractError:
        return StagedRedaction("underivable", gate, None, None, None, None, None)
    raw_bytes = contract.canonical_json_bytes(raw_document)
    sanitized, mapping = contract.derive_sanitized_manifest(raw)
    sanitized_bytes = contract.canonical_json_bytes(sanitized)
    mapping_bytes = contract.canonical_json_bytes(mapping)
    violations = list(contract.find_privacy_violations(sanitized, forbidden_strings=contract.private_forbidden_strings(raw), identity_tokens=identity_tokens))
    if contract.reduce_document(sanitized, layer="sanitized") != gate:
        violations.append("layer_disagreement")
    report = contract.build_redaction_report(raw=raw, raw_manifest_sha256=contract.sha256_hex(raw_bytes), sanitized_bytes=sanitized_bytes, gate=gate, privacy_violations=violations)
    _write_once(run_dir.joinpath(*RAW_MANIFEST_LOCATOR.split("/")), raw_bytes)
    _write_once(run_dir.joinpath(*MAPPING_LOCATOR.split("/")), mapping_bytes)
    return StagedRedaction("quarantined" if violations else "awaiting_review", gate, raw, contract.sha256_hex(raw_bytes),
                           contract.sha256_hex(mapping_bytes), sanitized_bytes, contract.canonical_json_bytes(report))


def stage_redaction(context: RunContext, *, staging_root: Path, quarantine_root: Path, identity_tokens: Sequence[str]) -> StagedRedaction:
    """Phase 1: stage eligible derivatives for private review (or quarantine them); promote nothing."""
    staged = compute_redaction(context, identity_tokens=identity_tokens)
    if staged.sanitized_bytes is not None and staged.report_bytes is not None:
        target = (quarantine_root if staged.status == "quarantined" else staging_root) / context.run_id
        _write_once(target / SANITIZED_NAME, staged.sanitized_bytes)
        _write_once(target / REPORT_NAME, staged.report_bytes)
    return staged


def promote_with_receipt(context: RunContext, *, staging_root: Path, sanitized_root: Path, receipt_path: Path,
                         identity_tokens: Sequence[str]) -> Path:
    """Phase 2: recompute, require the staged bytes and an accepting bound receipt, then promote atomically."""
    staged = compute_redaction(context, identity_tokens=identity_tokens)
    raw = staged.raw
    if staged.status != "awaiting_review" or raw is None or staged.sanitized_bytes is None or staged.report_bytes is None:
        raise HostError("redaction_not_eligible")
    for name, payload in ((SANITIZED_NAME, staged.sanitized_bytes), (REPORT_NAME, staged.report_bytes)):
        path = staging_root / context.run_id / name
        if not path.is_file() or path.read_bytes() != payload:
            raise HostError("staged_derivative_mismatch")
    final = sanitized_root / context.run_id
    if final.exists():
        raise HostError("promoted_run_exists")
    if not Path(receipt_path).is_file():
        raise HostError("receipt_missing")
    sanitized_sha = contract.sha256_hex(staged.sanitized_bytes)
    try:
        receipt = contract.parse_private_review_receipt(contract.strict_json_loads(Path(receipt_path).read_bytes()))
        contract.verify_receipt_binding(receipt, contract.ReceiptExpectation(
            run_id=raw.run_id, scenario_id=raw.scenario_id, scenario_sha256=raw.scenario_sha256,
            source_commit=raw.source.actual_source_commit, raw_manifest_sha256=str(staged.raw_manifest_sha256),
            raw_bundle_sha256=raw.raw_bundle_sha256, sanitized_manifest_sha256=sanitized_sha, mapping_sha256=str(staged.mapping_sha256),
            derivatives=[{"locator": SANITIZED_NAME, "sha256": sanitized_sha}], redaction_report_sha256=contract.sha256_hex(staged.report_bytes),
            not_before=raw.run_window.wall_ended_at.strftime("%Y-%m-%dT%H:%M:%SZ")))
    except contract.ContractError as exc:
        raise HostError(exc.code) from None
    attestation = contract.build_attestation(raw=raw, raw_manifest_sha256=str(staged.raw_manifest_sha256), sanitized_bytes=staged.sanitized_bytes,
                                             mapping_sha256=str(staged.mapping_sha256), report_bytes=staged.report_bytes, receipt=receipt, gate=staged.gate)
    # The receipt's reviewer identity is deliberately public, so only private values are scanned here.
    if contract.find_privacy_violations(attestation, forbidden_strings=contract.private_forbidden_strings(raw)):
        raise HostError("attestation_privacy_violation")
    partial = sanitized_root / f".{context.run_id}.partial-{secrets.token_hex(8)}"
    partial.mkdir(parents=True)
    try:
        (partial / SANITIZED_NAME).write_bytes(staged.sanitized_bytes)
        (partial / REPORT_NAME).write_bytes(staged.report_bytes)
        (partial / ATTESTATION_NAME).write_bytes(contract.canonical_json_bytes(attestation))
        os.replace(partial, final)
    except OSError:
        shutil.rmtree(partial, ignore_errors=True)
        raise HostError("promotion_failed") from None
    return final


# --------------------------------------------------------------------------- trusted checkout inputs (D11)
#
# The scenario, approved-run registry and descriptor fixture are read from the reviewed checkout only, never
# from a bundle or a caller-chosen location. The reviewed invocation record pins the checkout commit and the
# exact git blob hashes of those three files and must live outside the run roots.

APPROVED_RUNS_RELATIVE = "reports/plan-11-7-v5-approved-runs.json"
DESCRIPTOR_FIXTURE_RELATIVE = "tests/fixtures/evidence/plan117-v5-first-refusal-descriptors.json"
INVOCATION_RECORD_SCHEMA = "plan-11-7-v5-invocation-record-v1"
_INVOCATION_KEYS = ("schema", "run_id", "checkout_commit", "scenario_blob_sha1", "registry_blob_sha1", "descriptor_fixture_blob_sha1")


def require_registered_scenario(scenario_path: Path, checkout_root: Path) -> bytes:
    """The v5 scenario may only be the checkout's registered file (path identity; content cannot widen it)."""
    try:
        expected = checkout_root.joinpath(*SCENARIO_RELATIVE.split("/")).resolve(strict=True)
        supplied = Path(scenario_path).resolve(strict=True)
    except OSError:
        raise HostError("plan117_v5_scenario_unregistered") from None
    if supplied != expected:
        raise HostError("plan117_v5_scenario_unregistered")
    return expected.read_bytes()


def load_trusted_registry(checkout_root: Path) -> tuple[contract.ApprovedRunRegistry, bytes]:
    try:
        payload = checkout_root.joinpath(*APPROVED_RUNS_RELATIVE.split("/")).read_bytes()
    except OSError:
        raise HostError("approved_runs_missing") from None
    try:
        return contract.parse_approved_runs(contract.strict_json_loads(payload)), payload
    except contract.ContractError as exc:
        raise HostError(exc.code) from None


def load_descriptor_fixture(checkout_root: Path) -> tuple[contract.DescriptorFixture, str]:
    payload = checkout_root.joinpath(*DESCRIPTOR_FIXTURE_RELATIVE.split("/")).read_bytes()
    try:
        return contract.parse_descriptor_fixture(contract.strict_json_loads(payload)), contract.sha256_hex(payload)
    except contract.ContractError as exc:
        raise HostError(exc.code) from None


def git_blob_sha1(payload: bytes) -> str:
    """Git's object identity for file bytes (sha1 over the blob header), as the reviewed record pins it."""
    return hashlib.sha1(b"blob %d\x00" % len(payload) + payload, usedforsecurity=False).hexdigest()


def verify_invocation_record(record_path: Path, *, checkout_root: Path, checkout_commit: str, forbidden_roots: Sequence[Path], run_id: str) -> None:
    resolved = Path(record_path).resolve()
    if any(resolved == Path(root).resolve() or resolved.is_relative_to(Path(root).resolve()) for root in forbidden_roots):
        raise HostError("invocation_record_inside_run_roots")
    try:
        record = contract.strict_json_loads(resolved.read_bytes())
    except (OSError, contract.ContractError):
        raise HostError("invocation_record_invalid") from None
    if type(record) is not dict or set(record) != set(_INVOCATION_KEYS):
        raise HostError("invocation_record_invalid")

    def blob(relative: str) -> str:
        return git_blob_sha1(checkout_root.joinpath(*relative.split("/")).read_bytes())

    expected = {
        "schema": INVOCATION_RECORD_SCHEMA, "run_id": run_id, "checkout_commit": checkout_commit,
        "scenario_blob_sha1": blob(SCENARIO_RELATIVE), "registry_blob_sha1": blob(APPROVED_RUNS_RELATIVE),
        "descriptor_fixture_blob_sha1": blob(DESCRIPTOR_FIXTURE_RELATIVE),
    }
    if record != expected:
        raise HostError("invocation_record_mismatch")


# --------------------------------------------------------------------------- live seam (E3 only; never under pytest)

_VERSION = re.compile(r"(\d+\.\d+\.\d+)")
_REVISION = re.compile(r"\b([0-9a-f]{40})\b")


def real_host_actions(repo_root: Path) -> HostActions:
    """Live HostActions over the existing probe and custody-relay primitives. UNRUN until a released E3."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        raise HostError("plan117_v5_real_actions_forbidden_in_pytest")
    import subprocess
    import time

    import tools.probe_p11_zed_session_load as probe

    def git(root: Path, *args: str) -> bytes:
        completed = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False, timeout=60)  # noqa: S603, S607
        if completed.returncode != 0:
            raise HostError("git_failed")
        return completed.stdout

    def source_facts(root: Path) -> SourceObservation:
        untracked = sorted(item for item in git(root, "ls-files", "-z", "--others", "--exclude-standard").split(b"\0") if item)
        digest = hashlib.sha256()
        for relative in untracked:
            digest.update(relative + b"\0" + root.joinpath(*relative.decode("utf-8").split("/")).read_bytes() + b"\0")
        return SourceObservation(git(root, "rev-parse", "HEAD").decode().strip(), git(root, "rev-parse", "HEAD^{tree}").decode().strip(),
                                 contract.sha256_hex(git(root, "diff", "HEAD", "--binary")), digest.hexdigest() if untracked else _EMPTY)

    def zed_identity() -> ZedIdentity:
        executable = probe._resolve_zed_executable()
        output = probe._observe_zed_version()
        version, revision = _VERSION.search(output), _REVISION.search(output)
        if version is None or revision is None:
            raise HostError("zed_identity_unparsed")
        return ZedIdentity(executable, probe._file_sha256(executable), f"Zed {version.group(1)}", version.group(1), revision.group(1))

    def prepare_source(request: SourcePreparation) -> None:
        request.source_root.rmdir()
        probe._copy_normal_workspace_sources(request.normal_source_root, request.source_root, probe.normal_workspace_source_paths(request.normal_source_root))
        spec = request.source_root.joinpath("src", "optimus", "acp", "spec.py")
        spec.write_bytes(render_isolated_spec(probe.git_cat_file_blob(request.normal_source_root, request.source_commit, "src/optimus/acp/spec.py"), request.source_kind, request.fixture))
        request.launcher_path.parent.mkdir(parents=True, exist_ok=True)
        request.launcher_path.write_bytes(render_launcher_bytes(request.source_root, request.closure_report_path))

    def launch(request: LaunchRequest) -> LaunchResult:
        executable = probe._resolve_zed_executable()
        request.profile_root.mkdir(parents=True, exist_ok=True)
        invocation = probe.discover_hermetic_zed_invocation(
            executable=executable, version_output=probe._observe_zed_version(), help_output=probe._observe_zed_help(executable),
            executable_sha256=probe._file_sha256(executable), hermetic_root=request.profile_root)
        probe.validate_zed_invocation(invocation, hermetic_root=request.profile_root)
        argv = probe.build_real_zed_launch_argv(invocation, workspace=request.workspace_root, launch_help=probe._observe_zed_help(Path(invocation.argv[0])))
        relay_args = [str(repo_root / "tools" / "plan117_custody_relay.py"), "--capture-root", str(request.relay_dir.parent),
                      "--run-id", request.relay_dir.name, "--child-executable", sys.executable, "--", str(request.launcher_path)]
        probe.seed_hermetic_zed_settings(request.profile_root, relay_command=sys.executable, relay_args=relay_args)
        started = time.monotonic_ns()
        meta = probe._launch_zed_once(argv, env=probe._zed_env_for_invocation(invocation), cwd=request.workspace_root,
                                      log_path=request.relay_dir.parent / f"{request.relay_dir.name}-zed.log", timeout_s=ZED_LAUNCH_TIMEOUT_SECONDS)
        return LaunchResult(started, time.monotonic_ns(), meta.get("returncode"), meta.get("timed_out") is True)

    def locate_database(profile_root: Path) -> DatabaseLocation:
        candidates = sorted(path for path in profile_root.rglob("*.sqlite") if path.is_file())
        if len(candidates) != 1:
            raise HostError("ambiguous_database_location")
        main = candidates[0]
        return DatabaseLocation(main, main.with_name(main.name + "-wal"), main.with_name(main.name + "-shm"))

    return HostActions(
        source_facts=source_facts, normal_source_digest=probe.normal_workspace_source_digest,
        base_spec_bytes=lambda root, commit: probe.git_cat_file_blob(root, commit, "src/optimus/acp/spec.py"),
        zed_identity=zed_identity, prepare_source=prepare_source, launch=launch, locate_database=locate_database,
        remove_tree=shutil.rmtree, monotonic_ns=time.monotonic_ns, wall_now=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
