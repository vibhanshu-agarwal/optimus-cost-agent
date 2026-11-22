"""Plan 11.7 v5 E2: collector, derivation, frozen stubs and two-phase redaction.

Written slice by slice, each slice's tests before its code. No process, Zed, service or network is
touched; every artifact is synthetic and none is live or accepted evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.evidence_gather_support import plan117_current_client_collector as col
from tools.evidence_gather_support import plan117_current_client_contract as c
from tools.evidence_gather_support.common import HostError

REPO = Path(__file__).resolve().parents[3]
SPEC_TEXT = (REPO / "src" / "optimus" / "acp" / "spec.py").read_text(encoding="utf-8")
FIXTURE = c.default_descriptor_fixture()
D = c.GateDisposition
R = c.GateReason
RUN_ID = "p117v5-run-0001"


# --------------------------------------------------------------------------- slice 1: R census tracing


def test_current_source_census_matches_the_frozen_fixture():
    col.verify_census(FIXTURE, SPEC_TEXT)


def test_only_malformed_or_unknown_session_requests_are_negative_controls():
    """Plan 11.7 v5: every well-formed pre-admission branch maps to its wire class's descriptor (one per class, whatever its
    message); malformed or unknown-session requests are the only negative controls."""
    controls = {e.site for e in FIXTURE.census if e.disposition == "negative_control"}
    assert controls == {"error:INVALID_REQUEST:invalid request", "error:INVALID_REQUEST:unknown session", "error:METHOD_NOT_FOUND:*"}


def test_census_is_traced_from_source_not_copied_from_the_fixture():
    traced = col.trace_first_prompt_census(SPEC_TEXT)
    assert ("_handle_session_prompt", "error:INVALID_REQUEST:empty prompt", False, 1) in traced
    assert ("_refuse_prompt", "stop_reason:refusal", False, 1) in traced
    assert ("_handle_savings", "stop_reason:cancelled", False, 3) in traced
    # the host's shared local answer is counted at each caller with that caller's own message (Plan 12.11 CP3)
    assert ("_handle_savings", "error:INTERNAL_ERROR:the usage report could not be delivered", False, 1) in traced
    assert ("_handle_memory_command", "error:INTERNAL_ERROR:the memory answer could not be delivered", False, 1) in traced
    assert ("_handle_session_prompt", "memory_command", False, 1) in traced
    # post-admission branches (after allocate_turn_seq) are not part of the first-refusal census
    assert not any(site == "stop_reason:*" for _, site, _, _ in traced)


def test_new_first_prompt_response_branch_fails_structural_coverage():
    mutated = SPEC_TEXT.replace(
        "        task = _text_from_content_blocks(prompt)\n",
        '        if params.get("x"):\n            return error_response(request.get("id"), JsonRpcError(code=INTERNAL_ERROR, message="new class"))\n'
        "        task = _text_from_content_blocks(prompt)\n",
        1,
    )
    assert mutated != SPEC_TEXT
    with pytest.raises(HostError) as excinfo:
        col.verify_census(FIXTURE, mutated)
    assert excinfo.value.code == "r_census_mismatch"


def test_removed_branch_fails_structural_coverage():
    mutated = SPEC_TEXT.replace('JsonRpcError(code=INVALID_REQUEST, message="empty prompt")', 'JsonRpcError(code=INVALID_REQUEST, message="invalid request")', 1)
    assert mutated != SPEC_TEXT
    with pytest.raises(HostError):
        col.verify_census(FIXTURE, mutated)


def test_reopen_refusal_moved_out_of_the_prior_idle_block_fails_coverage():
    mutated = SPEC_TEXT.replace(
        '        if session_id in self._reopen_reservations:\n            return self._mcp_refusal(request, session_id, "mcp_reopen_in_progress", ownership_slot)\n',
        '        if session_id in self._reopen_reservations:\n            return self._mcp_refusal(request, session_id, "mcp_reopen_refused", ownership_slot)\n',
        1,
    )
    assert mutated != SPEC_TEXT
    with pytest.raises(HostError):
        col.verify_census(FIXTURE, mutated)


def test_mcp_reopen_refused_is_only_reachable_after_prior_idle_suspension():
    reopen_refused = [entry for entry in col.trace_first_prompt_census(SPEC_TEXT) if entry[1] == "mcp_refusal:mcp_reopen_refused"]
    assert reopen_refused and all(entry[2] for entry in reopen_refused)


def test_every_descriptor_class_is_reached_by_a_source_branch():
    traced = {(f, s, idle) for f, s, idle, _ in col.trace_first_prompt_census(SPEC_TEXT)}
    reached = {entry.descriptor_id for entry in FIXTURE.census if entry.disposition == "descriptor" and (entry.function, entry.site, entry.prior_idle) in traced}
    assert reached == set(c.R_DESCRIPTOR_IDS)


def test_census_without_its_admission_anchor_fails_closed():
    with pytest.raises(HostError) as excinfo:
        col.trace_first_prompt_census(SPEC_TEXT.replace("allocate_turn_seq", "allocate_seq"))
    assert excinfo.value.code == "r_census_anchor_missing"


# --------------------------------------------------------------------------- slice 2: frozen isolated patches


def _initialize_block(text):
    return text.split("def _handle_initialize", 1)[1].split("\n    def ", 1)[0]


@pytest.mark.parametrize("kind", c.SOURCE_KINDS)
def test_isolated_patch_applies_once_compiles_and_advertises_load_without_resume(kind):
    patched = col.render_isolated_spec(SPEC_TEXT.encode("utf-8"), kind, FIXTURE).decode("utf-8")
    compile(patched, "spec.py", "exec")
    block = _initialize_block(patched)
    assert block.count('"loadSession": True') == 1 and "resume" not in block
    assert patched.count('if method == "session/load":') == 1
    assert patched.count("plan117-v5 throwaway refusal stub") == (0 if kind == c.LOAD_ONLY_STUB else 1)


def test_unpatched_source_does_not_advertise_load_session():
    assert '"loadSession": True' not in _initialize_block(SPEC_TEXT)


def test_patch_identities_are_distinct_stable_and_independent_of_base_bytes():
    shas = {kind: col.patch_sha256(kind, FIXTURE) for kind in c.SOURCE_KINDS}
    assert len(set(shas.values())) == len(c.SOURCE_KINDS)
    assert all(len(value) == 64 for value in shas.values())
    assert shas == {kind: col.patch_sha256(kind, FIXTURE) for kind in c.SOURCE_KINDS}


@pytest.mark.parametrize("anchor", ["if session_id in self._active_turns or session_id in self._report_cancels:", '"sessionCapabilities": {},'])
def test_patch_refuses_a_drifted_patch_surface(anchor):
    drifted = SPEC_TEXT.replace(anchor, "pass", 1).encode()
    with pytest.raises(HostError) as excinfo:
        col.render_isolated_spec(drifted, "refusal_stub:r_refusal", FIXTURE)
    assert excinfo.value.code == "isolated_patch_anchor_mismatch"


def test_unknown_source_kind_is_refused():
    with pytest.raises(HostError):
        col.patch_sha256("refusal_stub:r_unknown", FIXTURE)


def _load_patched_module(kind):
    import sys
    import types

    patched = col.render_isolated_spec(SPEC_TEXT.encode("utf-8"), kind, FIXTURE).decode("utf-8")
    name = f"optimus.acp._p117v5_patched_{kind.replace(':', '_')}"
    module = types.ModuleType(name)
    module.__file__ = str(REPO / "src" / "optimus" / "acp" / "spec.py")
    sys.modules[name] = module
    try:
        exec(compile(patched, module.__file__, "exec"), module.__dict__)  # noqa: S102 - the frozen throwaway patch under test
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return name, module


class _NeverRunner:
    def run(self, *_args, **_kwargs):  # pragma: no cover - the stubs answer before admission
        raise AssertionError("runner must not be reached")


async def _drive(module, tmp_path, *, prompts=1, load=False):
    outbound = module.RecordingOutboundChannel()
    adapter = module.AcpDuplexAdapter(runner=_NeverRunner(), workspace_root=tmp_path, sessions=module.InMemoryAcpSpecSessionStore(), outbound=outbound)
    responses = []

    async def rpc(request):
        envelope = await adapter.handle_client_request(request)
        responses.append(envelope.response)

    await rpc({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": module.ACP_PROTOCOL_VERSION}})
    await rpc({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}})
    session_id = responses[1]["result"]["sessionId"]
    before = len(outbound.notifications)
    for number in range(prompts):
        await rpc({"jsonrpc": "2.0", "id": 2 + number, "method": "session/prompt", "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "hello"}]}})
    if load:
        await rpc({"jsonrpc": "2.0", "id": 9, "method": "session/load", "params": {"sessionId": session_id, "cwd": str(tmp_path), "mcpServers": []}})
    return responses, outbound.notifications[before:]


@pytest.mark.parametrize("descriptor_id", c.R_DESCRIPTOR_IDS)
def test_refusal_stub_emits_exactly_its_descriptor_with_no_stored_class_entry(descriptor_id, tmp_path):
    import asyncio
    import sys

    name, module = _load_patched_module(f"refusal_stub:{descriptor_id}")
    try:
        responses, notifications = asyncio.run(_drive(module, tmp_path, prompts=2))
    finally:
        sys.modules.pop(name, None)
    descriptor = {d.descriptor_id: d for d in FIXTURE.descriptors}[descriptor_id]
    capabilities = responses[0]["result"]["agentCapabilities"]
    assert capabilities["loadSession"] is True
    assert "resume" not in capabilities and "resume" not in capabilities["sessionCapabilities"]
    first = responses[2]
    body = first["result"] if "result" in first else first["error"]
    assert c.sha256_hex(c.canonical_json_bytes(body)) == c.expected_response_sha256(descriptor)
    assert responses[3]["error"]["message"] == "plan117-v5 stub allows one prompt"
    updates = tuple(
        (n["params"]["update"]["sessionUpdate"], c.sha256_hex(n["params"]["update"]["content"]["text"].encode()))
        for n in notifications
        if n["method"] == "session/update"
    )
    assert updates == c.expected_notices(descriptor)


def test_load_only_stub_answers_load_with_exact_empty_result(tmp_path):
    import asyncio
    import sys

    name, module = _load_patched_module(c.LOAD_ONLY_STUB)
    try:
        responses, notifications = asyncio.run(_drive(module, tmp_path, prompts=0, load=True))
    finally:
        sys.modules.pop(name, None)
    assert responses[-1] == {"jsonrpc": "2.0", "id": 9, "result": {}}
    assert notifications == []


# --------------------------------------------------------------------------- slice 3: launcher and module-closure report


def test_launcher_reports_in_root_closure_before_the_server_reads(tmp_path, monkeypatch):
    import asyncio
    import hashlib
    import json

    from optimus.acp import server

    report = tmp_path / "closure.json"
    seen = []

    async def fake_serve(self, *args, **kwargs):
        seen.append(report.is_file())

    monkeypatch.setattr(server.AcpStreamServer, "serve", fake_serve)
    monkeypatch.setattr(server.AcpStreamServer, "serve_ndjson", fake_serve)
    launcher = col.render_launcher_bytes(REPO, report)
    exec(compile(launcher, "launcher.py", "exec"), {"__name__": "p117v5_launcher_under_test"})  # noqa: S102 - rendered launcher under test
    asyncio.run(server.AcpStreamServer.serve(None))
    asyncio.run(server.AcpStreamServer.serve_ndjson(None))
    assert seen == [True, True]
    document = json.loads(report.read_text(encoding="utf-8"))
    assert document["schema"] == col.MODULE_CLOSURE_SCHEMA
    assert document["entrypoint_module"] == c.ENTRYPOINT_MODULE
    entries = {entry["module_name"]: entry for entry in document["entries"]}
    spec_bytes = (REPO / "src" / "optimus" / "acp" / "spec.py").read_bytes()
    assert entries["optimus.acp.spec"] == {
        "module_name": "optimus.acp.spec",
        "resolved_path": str((REPO / "src" / "optimus" / "acp" / "spec.py").resolve()),
        "source_relative_path": "src/optimus/acp/spec.py",
        "size_bytes": len(spec_bytes),
        "sha256": hashlib.sha256(spec_bytes).hexdigest(),
    }
    assert all(not entry["source_relative_path"].startswith("/") for entry in entries.values())


def test_launcher_bytes_are_deterministic_and_do_not_launch_on_import():
    first = col.render_launcher_bytes(Path("C:/x/src-root"), Path("C:/x/report.json"))
    assert first == col.render_launcher_bytes(Path("C:/x/src-root"), Path("C:/x/report.json"))
    compile(first, "launcher.py", "exec")
    assert b"if __name__ == \"__main__\":\n    raise SystemExit(main())" in first


ROOT = r"C:\p117v5\run\src\load-only-stub"


def _closure(**overrides):
    entries = [
        {"module_name": name, "resolved_path": ROOT + "\\" + path.replace("/", "\\"), "source_relative_path": path, "size_bytes": 3, "sha256": "a" * 64}
        for name, path in sorted(c.REQUIRED_MODULE_PATHS.items())
    ]
    document = {"schema": col.MODULE_CLOSURE_SCHEMA, "pid": 4242, "monotonic_ns": 77, "entrypoint_module": c.ENTRYPOINT_MODULE, "source_root": ROOT, "entries": entries, "inspection_failures": []}
    document.update(overrides)
    return c.canonical_json_bytes(document)


def test_closure_report_yields_contract_closure_facts():
    facts = col.parse_closure_report(_closure(), source_root_canonical=ROOT)
    assert facts == {
        "report_monotonic_ns": 77,
        "pid": 4242,
        "entrypoint_module": c.ENTRYPOINT_MODULE,
        "entries": [{"module_name": n, "source_relative_path": p, "sha256": "a" * 64} for n, p in sorted(c.REQUIRED_MODULE_PATHS.items())],
    }


@pytest.mark.parametrize(
    "payload",
    [
        _closure(extra=1),
        _closure(schema="other"),
        _closure(pid=0),
        _closure(pid=True),
        _closure(source_root=r"C:\other\root"),
        _closure(entries=[{"module_name": "m", "resolved_path": r"C:\elsewhere\m.py", "source_relative_path": "m.py", "size_bytes": 1, "sha256": "a" * 64}]),
        _closure(entries=[{"module_name": "m", "resolved_path": ROOT + r"\m.py", "source_relative_path": "../m.py", "size_bytes": 1, "sha256": "a" * 64}]),
        _closure(entries=[{"module_name": "m", "resolved_path": ROOT + r"\m.py", "source_relative_path": "m.py", "size_bytes": 1, "sha256": "A" * 64}]),
        b'{"schema":"x","schema":"y"}',
        b"not json",
    ],
)
def test_malformed_or_out_of_root_closure_report_is_refused(payload):
    with pytest.raises(c.ContractError):
        col.parse_closure_report(payload, source_root_canonical=ROOT)


# --------------------------------------------------------------------------- slice 4: wire derivation from relay captures


def write_relay_capture(relay_dir, messages, *, chunks=None):
    """A genuine relay capture written by the relay's own recorder and summary writer."""
    import json

    from tools import plan117_custody_relay as relay

    recorder = relay._LockedRecorder(relay_dir, "relay", 0.0)
    try:
        for direction, message in messages:
            payload = message if isinstance(message, bytes) else json.dumps(message, separators=(",", ":")).encode() + b"\n"
            recorder.record_chunk(direction, payload)
        recorder.record_eof(relay.DIR_ZED_TO_AGENT)
        recorder.record_eof(relay.DIR_AGENT_TO_ZED)
        totals = recorder.totals()
    finally:
        recorder.close()
    relay._write_summary(relay_dir, run_id="relay", child_argv=["python", "launcher.py"], child_exit_code=0, totals=totals,
                         zed_eof=True, agent_eof=True, terminal_disposition="completed", reason_code=None)


S1 = "session-" + "b" * 32
HANDSHAKE = [
    ("zed_to_agent", {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": 1}}),
    ("agent_to_zed", {"jsonrpc": "2.0", "id": 0, "result": {"agentCapabilities": {"loadSession": True, "sessionCapabilities": {}}}}),
    ("zed_to_agent", {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": r"C:\w"}}),
    ("agent_to_zed", {"jsonrpc": "2.0", "id": 1, "result": {"sessionId": S1}}),
    ("agent_to_zed", {"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": S1, "update": {"sessionUpdate": "available_commands_update"}}}),
]


def test_ndjson_parsing_keeps_exact_result_value_bytes():
    payload = b'{"jsonrpc":"2.0","id":1,"result":{ }}\n{"jsonrpc":"2.0","id":2,"result":{}}\n'
    messages, undecodable = col.parse_ndjson_messages(payload)
    assert not undecodable and len(messages) == 2
    first, second = (col.wire_event(i, "agent_to_zed", m) for i, m in enumerate(messages))
    assert first["response_sha256"] == second["response_sha256"]
    assert first["result_bytes_sha256"] == c.sha256_hex(b"{ }")
    assert second["result_bytes_sha256"] == c.EMPTY_OBJECT_SHA256


@pytest.mark.parametrize("payload", [b"not json\n", b'{"a":1,"a":2}\n', b"[1]\n", b'{"a":1}', b'{"a":NaN}\n'])
def test_undecodable_relay_bytes_are_flagged(payload):
    assert col.parse_ndjson_messages(payload)[1] is True


def test_wire_events_are_ordered_across_directions_by_relay_sequence(tmp_path):
    write_relay_capture(tmp_path, HANDSHAKE)
    derived = col.derive_wire(tmp_path)
    assert derived.relay_valid and not derived.undecodable
    assert [(e["direction"], e["kind"], e["method"], e["request_id"]) for e in derived.events] == [
        ("zed_to_agent", "request", "initialize", 0),
        ("agent_to_zed", "response", None, 0),
        ("zed_to_agent", "request", "session/new", 1),
        ("agent_to_zed", "response", None, 1),
        ("agent_to_zed", "notification", "session/update", None),
    ]
    assert [e["index"] for e in derived.events] == [0, 1, 2, 3, 4]
    assert derived.events[3]["result_session_id"] == S1
    assert derived.events[4]["update_kind"] == "available_commands_update"
    assert derived.initialize == {"result_sha256": derived.events[1]["response_sha256"], "load_session": True, "has_resume": False}
    assert derived.stdin_eof is True and derived.child_exit_code == 0


def test_derived_events_satisfy_the_contract_wire_schema(tmp_path):
    write_relay_capture(tmp_path, HANDSHAKE)
    for position, event in enumerate(col.derive_wire(tmp_path).events):
        c._parse_wire_event(event, "wire", position)


@pytest.mark.parametrize(
    "capabilities,expected",
    [
        ({"loadSession": True, "sessionCapabilities": {"resume": {}}}, (True, True)),
        ({"loadSession": True, "resume": True}, (True, True)),
        ({"loadSession": False}, (False, False)),
        ({"loadSession": "yes"}, (None, False)),
        ({}, (None, False)),
    ],
)
def test_initialize_capability_facts_come_from_the_exact_result(tmp_path, capabilities, expected):
    write_relay_capture(tmp_path, [HANDSHAKE[0], ("agent_to_zed", {"jsonrpc": "2.0", "id": 0, "result": {"agentCapabilities": capabilities}})])
    initialize = col.derive_wire(tmp_path).initialize
    assert (initialize["load_session"], initialize["has_resume"]) == expected


def test_prompt_and_error_responses_carry_their_classes(tmp_path):
    write_relay_capture(tmp_path, [
        *HANDSHAKE,
        ("zed_to_agent", {"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": {"sessionId": S1}}),
        ("agent_to_zed", {"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": S1, "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "hi\n\n"}}}}),
        ("agent_to_zed", {"jsonrpc": "2.0", "id": 2, "error": {"code": -32600, "message": "empty prompt"}}),
        ("zed_to_agent", {"jsonrpc": "2.0", "id": 3, "method": "session/prompt", "params": {"sessionId": S1}}),
        ("agent_to_zed", {"jsonrpc": "2.0", "id": 3, "result": {"stopReason": "refusal"}}),
    ])
    events = col.derive_wire(tmp_path).events
    assert events[5]["session_id"] == S1 and events[6]["text_sha256"] == c.sha256_hex(b"hi\n\n")
    assert (events[7]["error_code"], events[7]["result_bytes_sha256"]) == (-32600, None)
    assert events[7]["response_sha256"] == c.sha256_hex(b'{"code":-32600,"message":"empty prompt"}')
    assert events[9]["stop_reason"] == "refusal"


def test_message_split_across_chunks_orders_by_its_completing_chunk(tmp_path):
    first = b'{"jsonrpc":"2.0","id":0,"method":"initialize"}\n'
    write_relay_capture(tmp_path, [
        ("zed_to_agent", first[:10]),
        ("agent_to_zed", {"jsonrpc": "2.0", "method": "session/update", "params": {}}),
        ("zed_to_agent", first[10:]),
    ])
    kinds = [e["kind"] for e in col.derive_wire(tmp_path).events]
    assert kinds == ["notification", "request"]


@pytest.mark.parametrize("name", ["zed-to-agent.bin", "relay-index.ndjson", "relay-summary.json"])
def test_tampered_or_missing_relay_capture_is_invalid_but_still_parsed(tmp_path, name):
    write_relay_capture(tmp_path, HANDSHAKE)
    path = tmp_path / name
    if name == "relay-summary.json":
        path.unlink()
    elif name == "relay-index.ndjson":
        tampered = path.read_bytes().replace(b'"sequence":1,', b'"sequence":7,')
        assert tampered != path.read_bytes()
        path.write_bytes(tampered)
    else:
        path.write_bytes(path.read_bytes().replace(b"initialize", b"initializX"))
    derived = col.derive_wire(tmp_path)
    assert derived.relay_valid is False
    if name == "zed-to-agent.bin":
        assert any(e["method"] == "initializX" for e in derived.events)


def test_unreadable_relay_summary_does_not_drop_wire(tmp_path, monkeypatch):
    write_relay_capture(tmp_path, HANDSHAKE)
    original = Path.read_bytes

    def read_bytes(path):
        if path == tmp_path / "relay-summary.json":
            raise PermissionError("synthetic relay summary read failure")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    wire = col.derive_wire(tmp_path)
    assert not wire.relay_valid
    assert any(event["method"] == "initialize" for event in wire.events)


def test_unrecognized_message_shapes_are_undecodable_not_dropped_silently(tmp_path):
    write_relay_capture(tmp_path, [("zed_to_agent", {"jsonrpc": "2.0", "id": True, "method": "initialize"}), ("agent_to_zed", {"jsonrpc": "2.0", "id": 0, "result": 1, "error": {}})])
    derived = col.derive_wire(tmp_path)
    assert derived.undecodable is True and derived.events == []


# --------------------------------------------------------------------------- slice 5: closed database copies


def make_zed_database(path, rows, *, journal="delete"):
    """A synthetic profile database with Zed's sidebar_threads(thread_id BLOB PRIMARY KEY, session_id TEXT) shape."""
    import sqlite3

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"PRAGMA journal_mode={journal}")
        connection.execute("CREATE TABLE IF NOT EXISTS sidebar_threads (thread_id BLOB PRIMARY KEY, session_id TEXT)")
        connection.execute("DELETE FROM sidebar_threads")
        connection.executemany("INSERT INTO sidebar_threads VALUES (?, ?)", rows)
        connection.commit()
    finally:
        connection.close()
    return path


def test_native_locator_selects_the_binding_database_in_a_two_file_zed_profile(tmp_path, monkeypatch):
    import sqlite3

    global_db = tmp_path / "db" / "0-global" / "db.sqlite"
    global_db.parent.mkdir(parents=True)
    connection = sqlite3.connect(global_db)
    try:
        connection.execute("CREATE TABLE kv (key TEXT PRIMARY KEY, value BLOB)")
    finally:
        connection.close()
    stable_db = make_zed_database(tmp_path / "db" / "0-stable" / "db.sqlite", [(b"\x01" * 16, None)])
    before = {path: path.read_bytes() for path in (global_db, stable_db)}
    actions, _, _ = _real_actions_with_recorded_git(monkeypatch, {})

    location = actions.locate_database(tmp_path)

    assert location == col.DatabaseLocation(
        stable_db, stable_db.with_name("db.sqlite-wal"), stable_db.with_name("db.sqlite-shm")
    )
    assert col.read_database_binding(location.main) == col.DatabaseBinding(True, "01" * 16, None)
    assert {path: path.read_bytes() for path in before} == before
    assert sorted(path.name for path in stable_db.parent.iterdir()) == ["db.sqlite"]
    assert sorted(path.name for path in global_db.parent.iterdir()) == ["db.sqlite"]


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("no_database", "binding_database_missing"),
        ("wrong_columns", "binding_database_schema_invalid"),
        ("view", "binding_database_schema_invalid"),
        ("corrupt", "binding_database_unreadable"),
        ("two_binding_databases", "ambiguous_database_location"),
        ("mixed_case_binding_database", "ambiguous_database_location"),
        ("directory_sidecar", "binding_database_unreadable"),
    ],
)
def test_native_locator_rejects_profiles_without_an_unambiguous_binding_database(tmp_path, monkeypatch, case, code):
    import sqlite3

    db = tmp_path / "db.sqlite"
    if case == "corrupt":
        db.write_bytes(b"not SQLite")
    elif case == "two_binding_databases":
        make_zed_database(db, [])
        make_zed_database(tmp_path / "other.sqlite", [])
    elif case == "directory_sidecar":
        make_zed_database(db, [])
        db.with_name("db.sqlite-wal").mkdir()
    elif case == "mixed_case_binding_database":
        make_zed_database(db, [])
        connection = sqlite3.connect(tmp_path / "other.sqlite")
        try:
            connection.execute("CREATE TABLE SIDEBAR_THREADS (THREAD_ID BLOB PRIMARY KEY, SESSION_ID TEXT)")
        finally:
            connection.close()
    elif case in {"wrong_columns", "view"}:
        connection = sqlite3.connect(db)
        try:
            if case == "wrong_columns":
                connection.execute("CREATE TABLE sidebar_threads (thread_id BLOB PRIMARY KEY)")
            else:
                connection.execute("CREATE VIEW sidebar_threads AS SELECT NULL AS thread_id, NULL AS session_id")
        finally:
            connection.close()
    actions, _, _ = _real_actions_with_recorded_git(monkeypatch, {})

    with pytest.raises(HostError) as excinfo:
        actions.locate_database(tmp_path)
    assert excinfo.value.code == code


def test_native_locator_finds_a_binding_table_written_only_to_the_wal(tmp_path, monkeypatch):
    import shutil
    import sqlite3

    source = tmp_path / "source" / "db.sqlite"
    source.parent.mkdir()
    profile = tmp_path / "profile"
    profile.mkdir()
    main = profile / "db.sqlite"
    wal = profile / "db.sqlite-wal"
    shm = profile / "db.sqlite-shm"
    connection = sqlite3.connect(source)
    try:
        connection.execute("CREATE TABLE baseline (label TEXT)")
        connection.commit()
        connection.execute("PRAGMA journal_mode=wal")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE SIDEBAR_THREADS (THREAD_ID BLOB PRIMARY KEY, SESSION_ID TEXT)")
        connection.execute("INSERT INTO SIDEBAR_THREADS VALUES (?, ?)", (b"\xa1" * 16, None))
        connection.commit()
        for path in (main, wal, shm):
            shutil.copyfile(source.with_name(path.name), path)
    finally:
        connection.close()

    lone_main = tmp_path / "main-without-sidecars.sqlite"
    shutil.copyfile(main, lone_main)
    assert not col.read_database_binding(lone_main).readable
    before = {path: path.read_bytes() for path in (main, wal, shm)}
    actions, _, _ = _real_actions_with_recorded_git(monkeypatch, {})

    location = actions.locate_database(profile)

    assert location == col.DatabaseLocation(main, wal, shm)
    assert col.read_database_binding(location.main, location.wal, location.shm) == col.DatabaseBinding(True, "A1" * 16, None)
    assert {path: path.read_bytes() for path in before} == before


def test_binding_is_read_from_a_closed_copy_without_touching_it(tmp_path):
    path = make_zed_database(tmp_path / "copy" / "db.sqlite", [(b"\xab" * 16, "session-" + "c" * 32)])
    before = path.read_bytes()
    assert col.read_database_binding(path) == col.DatabaseBinding(readable=True, thread_id="AB" * 16, session_binding="session-" + "c" * 32)
    assert path.read_bytes() == before
    assert sorted(p.name for p in path.parent.iterdir()) == ["db.sqlite"]


def test_null_binding_is_reported_as_null(tmp_path):
    path = make_zed_database(tmp_path / "db.sqlite", [(b"\x01" * 16, None)])
    assert col.read_database_binding(path) == col.DatabaseBinding(True, "01" * 16, None)


def test_more_or_fewer_than_one_thread_has_no_thread_identity(tmp_path):
    two = make_zed_database(tmp_path / "two.sqlite", [(b"\x01" * 16, None), (b"\x02" * 16, None)])
    none = make_zed_database(tmp_path / "none.sqlite", [])
    assert col.read_database_binding(two) == col.DatabaseBinding(True, None, None)
    assert col.read_database_binding(none) == col.DatabaseBinding(True, None, None)


def test_unreadable_or_foreign_copy_is_reported_unreadable(tmp_path):
    garbage = tmp_path / "garbage.sqlite"
    garbage.write_bytes(b"not a database")
    import sqlite3

    foreign = tmp_path / "foreign.sqlite"
    connection = sqlite3.connect(foreign)
    connection.execute("CREATE TABLE other (x)")
    connection.commit()
    connection.close()
    assert col.read_database_binding(garbage).readable is False
    assert col.read_database_binding(foreign).readable is False


def test_malformed_binding_value_cannot_pass_as_null(tmp_path):
    path = make_zed_database(tmp_path / "db.sqlite", [(b"\x01" * 16, "not-a-session")])
    binding = col.read_database_binding(path)
    assert binding.session_binding is not None
    assert not c._SESSION_ID.fullmatch(binding.session_binding) or binding.session_binding == col.UNRECOGNIZED_BINDING


def test_wal_sidecar_copy_is_applied_when_present(tmp_path):
    import shutil
    import sqlite3

    live = tmp_path / "live" / "db.sqlite"
    make_zed_database(live, [(b"\x01" * 16, None)], journal="wal")
    connection = sqlite3.connect(live)
    connection.execute("PRAGMA wal_autocheckpoint=0")
    connection.execute("UPDATE sidebar_threads SET session_id=?", ("session-" + "d" * 32,))
    connection.commit()
    copy = tmp_path / "copy"
    copy.mkdir()
    for suffix in ("", "-wal", "-shm"):
        shutil.copyfile(live.with_name("db.sqlite" + suffix), copy / ("db.sqlite" + suffix))
    connection.close()
    binding = col.read_database_binding(copy / "db.sqlite", copy / "db.sqlite-wal", copy / "db.sqlite-shm")
    assert binding.session_binding == "session-" + "d" * 32


# --------------------------------------------------------------------------- slice 6: capture-time path custody and run key


@pytest.fixture
def windows_shaped_paths(monkeypatch):
    """windows-path-v1 is Windows-only. Off Windows, map tmp paths onto a synthetic drive so the pipeline can
    still be exercised; on Windows the real canonicalizer runs unchanged."""
    import sys
    from pathlib import PurePosixPath

    if sys.platform != "win32":
        monkeypatch.setattr(col, "_canonical_text", lambda text: c.canonicalize_windows_path("Z:\\" + "\\".join(PurePosixPath(text).parts[1:])))


def test_capture_strictly_resolves_an_existing_path_of_the_declared_kind(tmp_path, windows_shaped_paths):
    import hashlib

    (tmp_path / "file.txt").write_bytes(b"abc")
    (tmp_path / "sub").mkdir()  # strict resolution requires every intermediate directory to exist (POSIX does)
    identity = col.capture_path_identity("role_x", tmp_path / "sub" / ".." / "file.txt", "file")
    assert identity["sha256"] == hashlib.sha256(b"abc").hexdigest() and identity["size_bytes"] == 3
    assert identity["raw_path"] == identity["canonical_path"] == c.canonicalize_windows_path(identity["canonical_path"])
    assert ".." not in identity["canonical_path"]
    c._parse_path_identity(identity, "identity", "raw")
    directory = col.capture_path_identity("role_d", tmp_path, "directory")
    assert (directory["sha256"], directory["size_bytes"]) == (None, None)


@pytest.mark.parametrize("case", ["relative", "missing", "kind"])
def test_capture_refuses_relative_missing_or_wrong_kind_paths(tmp_path, windows_shaped_paths, case):
    (tmp_path / "file.txt").write_bytes(b"x")
    path, kind = {"relative": (Path("relative"), "directory"), "missing": (tmp_path / "nope", "directory"), "kind": (tmp_path / "file.txt", "directory")}[case]
    with pytest.raises(HostError) as excinfo:
        col.capture_path_identity("role_x", path, kind)
    assert excinfo.value.code == {"relative": "path_not_absolute", "missing": "path_missing", "kind": "path_kind_mismatch"}[case]


@pytest.mark.skipif(__import__("sys").platform == "win32", reason="exercises the non-Windows refusal")
def test_capture_fails_closed_off_windows(tmp_path):
    with pytest.raises(HostError) as excinfo:
        col.capture_path_identity("role_x", tmp_path, "directory")
    assert excinfo.value.code == "path_capture_requires_win32"


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="the real windows-path-v1 canonicalizer")
def test_real_windows_capture_uppercases_the_drive_and_keeps_other_case(tmp_path):
    identity = col.capture_path_identity("role_d", tmp_path, "directory")
    resolved = str(tmp_path.resolve())
    assert identity["canonical_path"] == resolved[0].upper() + resolved[1:]


def test_containment_is_decided_on_canonical_component_boundaries():
    assert col.is_beneath(r"C:\run\arms\a", r"C:\run")
    assert col.is_beneath(r"c:\RUN\x", r"C:\run")
    assert not col.is_beneath(r"C:\runner\x", r"C:\run")
    assert not col.is_beneath(r"C:\run", r"C:\run")
    assert col.are_disjoint(r"C:\a", r"C:\b")
    assert not col.are_disjoint(r"C:\a", r"C:\a\b")
    assert not col.are_disjoint(r"C:\a", r"c:\A")


def test_run_key_is_created_once_private_and_never_replaced(tmp_path):
    key = col.create_run_key(tmp_path)
    assert len(key) == 32
    assert col.create_run_key(tmp_path) == key == col.load_run_key(tmp_path)
    assert (tmp_path / col.PATH_KEY_LOCATOR).is_file()


@pytest.mark.parametrize("payload,code", [(None, "run_key_missing"), (b"{}", "run_key_invalid"), (b'{"schema":"plan-11-7-v5-path-key-v1","key_hex":"00"}', "run_key_invalid")])
def test_missing_or_malformed_run_key_fails_closed(tmp_path, payload, code):
    if payload is not None:
        (tmp_path / "private").mkdir()
        (tmp_path / col.PATH_KEY_LOCATOR).write_bytes(payload)
    with pytest.raises(HostError) as excinfo:
        col.load_run_key(tmp_path)
    assert excinfo.value.code == code


def test_private_root_commitment_is_the_keyed_commitment_of_the_captured_capture_root(tmp_path, windows_shaped_paths):
    key = col.create_run_key(tmp_path / "run")
    commitments = col.private_root_commitments(tmp_path, key)
    canonical = col.capture_path_identity("capture_root", tmp_path, "directory")["canonical_path"]
    assert commitments == {"capture_root": c.commit_path(canonical, key)}
    assert canonical not in str(commitments)


# --------------------------------------------------------------------------- slice 7: collection state machine and raw derivation

FIXTURE_SHA = c.sha256_hex((REPO / "tests" / "fixtures" / "evidence" / "plan117-v5-first-refusal-descriptors.json").read_bytes())


class Run:
    """One deterministic run through the real collector, raw-bundle writer and generic classifier."""

    def __init__(self, tmp_path, options=None):
        import hashlib

        from evidence_handoff.collector.bundles import write_run_manifest
        from evidence_handoff.collector.scenarios import load_scenario, resolve_bindings
        from tests.support import plan117_v5_host as host_mod

        self.host_mod = host_mod
        self.tmp = tmp_path
        self.capture_root = tmp_path / "capture"
        self.scratch = tmp_path / "scratch"
        self.normal = tmp_path / "normal"
        for root in (self.capture_root, self.scratch, self.normal):
            root.mkdir()
        self.host = host_mod.FakeHost(tmp_path / "host", options or host_mod.FakeHostOptions())
        scenario = load_scenario(REPO / col.SCENARIO_RELATIVE)
        bindings = resolve_bindings(scenario, (f"run_id={RUN_ID}",))
        self.context = write_run_manifest(capture_root=self.capture_root, scenario=scenario, bindings=bindings, run_id=RUN_ID, monotonic_origin_ns=self.host.clock)
        self.run_dir = self.capture_root / RUN_ID
        self.key = col.create_run_key(self.run_dir)
        self.row = {
            "run_id": RUN_ID,
            "evidence_kind": c.EVIDENCE_KIND_GATE,
            "scenario_id": c.SCENARIO_ID,
            "scenario_source_sha256": c.sha256_hex((REPO / col.SCENARIO_RELATIVE).read_bytes()),
            "scenario_sha256": self.context.scenario_sha256,
            "descriptor_fixture_sha256": FIXTURE_SHA,
            "patch_sha256s": {kind: col.patch_sha256(kind, FIXTURE) for kind in c.SOURCE_KINDS},
            "source_commit": host_mod.SOURCE_COMMIT,
            "source_tree": host_mod.SOURCE_TREE,
            "required_modules": sorted(c.REQUIRED_MODULE_PATHS),
            "client": {"executable_sha256": hashlib.sha256(b"fake-zed-binary").hexdigest(), "app_version": "1.27.0", "source_revision": "c84af5b99cbc366d675064e52b23664a015b6e35"},
            "launch_config_sha256": col.LAUNCH_CONFIG_SHA256,
            "arm_ids": list(c.ARM_IDS),
            "approval_id": "approval-p117v5-0001",
            "approval_not_before": "2026-11-20T09:00:00Z",
            "approval_not_after": "2026-11-20T18:00:00Z",
            "budget_policy_sha256": hashlib.sha256(b"budget").hexdigest(),
            "private_root_commitments": col.private_root_commitments(self.capture_root, self.key),
        }
        self.spec = self.registry_spec()

    def registry_spec(self, **overrides):
        row = dict(self.row, **overrides)
        registry = {"schema": c.RUN_REGISTRY_SCHEMA, "runs": [{"run_spec": row, "run_spec_sha256": c.sha256_hex(c.canonical_json_bytes(row))}]}
        return c.parse_approved_runs(registry).lookup(RUN_ID)

    def collect(self):
        import json

        from evidence_handoff.collector.bundles import write_provisional_result, write_raw_bundle
        from evidence_handoff.collector.classification import classify
        from tools.evidence_gather_support import detectors as detectors_mod

        inputs = col.CollectInputs(self.context, self.spec, FIXTURE, FIXTURE_SHA, self.normal, self.scratch)
        batch = col.collect_current_client_gate(inputs, self.host.actions())
        write_raw_bundle(context=self.context, batches=(batch,))
        digest = json.loads((self.run_dir / "raw-bundle.json").read_text(encoding="utf-8"))["bundle_sha256"]
        claims = detectors_mod.detect_claims(context=self.context, batches=(batch,))
        self.provisional = classify(context=self.context, raw_bundle_sha256=digest, claims=claims, required_collectors=(batch.collector_id,), stability_interval_ns=1)
        write_provisional_result(context=self.context, result=self.provisional)
        return batch

    def raw(self):
        from evidence_handoff.collector.bundles import load_verified_raw_bundle

        batches = load_verified_raw_bundle(context=self.context, bundle_path=self.run_dir / "raw-bundle.json")
        provisional = c.sha256_hex((self.run_dir / "provisional-result.json").read_bytes())
        return col.derive_raw_document(self.context, batches, provisional_sha256=provisional)

    def gate(self):
        return c.reduce_document(self.raw(), layer="raw")


def _codes(result):
    return [hit.reason for hit in (result.primary, *result.secondary) if hit is not None]


def _launch_order():
    return [(arm, launch) for arm in c.ARM_IDS for launch in (c.PROMPTED_LAUNCH_IDS if arm == c.ARM_PROMPTED else c.REOPEN_LAUNCH_IDS)]


def test_clean_run_derives_an_accepted_raw_manifest_after_live_roots_are_gone(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    batch = run.collect()
    assert list(run.scratch.iterdir()) == [], "cleanup removed the run root before derivation"
    raw = run.raw()
    result = c.reduce_document(raw, layer="raw")
    assert result.disposition is D.ACCEPTED_CURRENT_CLIENT_GATE, result.reason_codes()
    assert result.derived_reachability == "ZERO_ENTRY_UNREACHABLE"
    assert [arm["arm_id"] for arm in raw["arms"]] == list(c.ARM_IDS)
    assert run.host.launches == _launch_order()
    manifest = c.parse_raw_manifest(raw)
    assert c.run_spec_mismatches(manifest, run.spec) == ()
    assert raw["path_commitment_key_hex"] == run.key.hex()
    assert batch.collector_id == col.COLLECTOR_ID and len(batch.observations) == len(batch.artifacts) - sum(1 for a in batch.artifacts if a.role.startswith(("plan117_v5_relay:", "plan117_v5_closure:", "plan117_v5_db:")))


def test_counts_ids_and_bindings_are_derived_from_artifacts_not_supplied(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    run.collect()
    raw = run.raw()
    prompted = next(arm for arm in raw["arms"] if arm["arm_id"] == "prompted")
    a, b = prompted["launches"]
    assert a["counts"] == {"initialize": 1, "session_new": 1, "session_load": 0, "session_prompt": 1, "session_update": 2}
    assert b["counts"]["session_load"] == 1
    assert prompted["checkpoints"][0]["session_binding"] == run.host_mod.PROMPTED_SESSION
    assert prompted["checkpoints"][1]["session_binding"] is None
    assert a["shutdown"] == {"mechanism": "clean_eof", "agent_stdin_eof": True, "child_exit_code": 0, "zed_exit_code": 0}


def test_generic_custody_classification_is_not_the_gate_verdict(tmp_path, windows_shaped_paths):
    run = Run(tmp_path, run_options(reopen_load_arm="r_refusal"))
    run.collect()
    assert run.provisional.outcome.value not in {d.value for d in D}
    assert run.gate().disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert run.raw()["provisional_classification_sha256"] == c.sha256_hex((run.run_dir / "provisional-result.json").read_bytes())


def run_options(**values):
    from tests.support import plan117_v5_host as host_mod

    return host_mod.FakeHostOptions(**values)


@pytest.mark.parametrize("arm_id", c.REOPEN_ARM_IDS)
def test_reopen_load_in_any_reopen_arm_latches_stop_through_the_pipeline(tmp_path, windows_shaped_paths, arm_id):
    run = Run(tmp_path, run_options(reopen_load_arm=arm_id))
    run.collect()
    result = run.gate()
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert result.primary.subject == arm_id


def test_pre_reopen_database_binding_latches_stop(tmp_path, windows_shaped_paths):
    run = Run(tmp_path, run_options(pre_reopen_binding_arm="r_invalid_request"))
    run.collect()
    result = run.gate()
    assert (result.disposition, result.primary.reason) == (D.ZERO_ENTRY_REACHABLE_STOP, R.REOPEN_PRE_BINDING_NON_NULL)


@pytest.mark.parametrize(
    "options,reason",
    [
        ({"first_launch_load_arm": "a_prime"}, R.FIRST_LAUNCH_LOAD_OBSERVED),
        ({"omit_module": "optimus.acp.errors"}, R.MODULE_CLOSURE_INCOMPLETE),
        ({"extra_notice_arm": "r_end_turn"}, R.R_NOTICE_MISMATCH),
        ({"advertise_resume": ("prompted", "lifecycle_b")}, R.CAPABILITY_RESUME_ADVERTISED),
        ({"deny_load_session": ("a_prime", "first")}, R.CAPABILITY_LOAD_SESSION_MISSING),
        ({"cleanup_fails": True}, R.CLEANUP_UNVERIFIED),
        ({"normal_source_changes": True}, R.NORMAL_SOURCE_NOT_RESTORED),
        ({"report_before_launch": ("r_refusal", "first")}, R.MODULE_CLOSURE_CHRONOLOGY),
        ({"prompted_binding_retained": True}, R.PROMPTED_BINDING_RETAINED),
        ({"second_thread_arm": "a_prime"}, R.DATABASE_UNREADABLE),
    ],
)
def test_each_injected_failure_is_classified_invalid_through_the_pipeline(tmp_path, windows_shaped_paths, options, reason):
    run = Run(tmp_path, run_options(**options))
    run.collect()
    result = run.gate()
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE, result.reason_codes()
    assert reason in _codes(result)


def test_confirmed_forced_stop_ends_the_schedule_and_preserves_the_shutdown_reason(tmp_path, windows_shaped_paths):
    run = Run(tmp_path, run_options(forced_kill=("r_cancelled", "reopen")))
    run.collect()
    raw = run.raw()
    assert raw["aborted"] == {"reason_code": "zed_shutdown_forced", "stage": "launch"}
    assert raw["arms"][-1]["launches"][-1]["shutdown"]["mechanism"] == "forced_kill"
    assert run.host.launches[-1] == ("r_cancelled", "reopen")
    assert c.reduce_document(raw, layer="raw").disposition is D.INDETERMINATE_CURRENT_CLIENT_GATE


def test_failure_mid_run_preserves_an_aborted_bundle_and_still_cleans_up(tmp_path, windows_shaped_paths):
    run = Run(tmp_path, run_options(abort_at=("r_cancelled", "reopen")))
    run.collect()
    assert list(run.scratch.iterdir()) == []
    raw = run.raw()
    assert raw["aborted"] == {"reason_code": "simulated_launch_failure", "stage": "launch"}
    assert [arm["arm_id"] for arm in raw["arms"]] == ["a_prime", "r_end_turn", "r_refusal", "r_cancelled"]
    assert c.reduce_document(raw, layer="raw").disposition is D.INDETERMINATE_CURRENT_CLIENT_GATE


def test_abort_with_a_positive_signal_is_still_stop(tmp_path, windows_shaped_paths):
    run = Run(tmp_path, run_options(reopen_load_arm="a_prime", abort_at=("r_end_turn", "first")))
    run.collect()
    assert run.gate().disposition is D.ZERO_ENTRY_REACHABLE_STOP



@pytest.mark.parametrize("arm", ["a_prime", "r_refusal"])
@pytest.mark.parametrize("captured_stop", [True, False])
def test_cp1_review_relay_survives_capture_record_write_failure(tmp_path, windows_shaped_paths, monkeypatch, arm, captured_stop):
    run = Run(tmp_path, run_options(reopen_load_arm=arm if captured_stop else None))
    write_document = col._Emitter.document

    def write_with_fault(emitter, kind, role, locator, body, arm_id="", launch_id=""):
        if (kind, arm_id, launch_id) == ("launch", arm, "reopen"):
            raise OSError("synthetic custody record write failure")
        write_document(emitter, kind, role, locator, body, arm_id, launch_id)

    monkeypatch.setattr(col._Emitter, "document", write_with_fault)
    run.collect()
    result = run.gate()
    if captured_stop:
        assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP, result.reason_codes()
        assert result.primary.subject == arm
    else:
        assert result.disposition in (D.INVALID_CURRENT_CLIENT_GATE, D.INDETERMINATE_CURRENT_CLIENT_GATE)


@pytest.mark.parametrize("captured_stop", [True, False])
def test_cp1_review_database_survives_checkpoint_record_write_failure(tmp_path, windows_shaped_paths, monkeypatch, captured_stop):
    run = Run(tmp_path, run_options(pre_reopen_binding_arm="a_prime" if captured_stop else None))
    write_document = col._Emitter.document

    def write_with_fault(emitter, kind, role, locator, body, arm_id="", launch_id=""):
        if (kind, arm_id, launch_id) == ("checkpoint", "a_prime", "first"):
            raise OSError("synthetic custody record write failure")
        write_document(emitter, kind, role, locator, body, arm_id, launch_id)

    monkeypatch.setattr(col._Emitter, "document", write_with_fault)
    run.collect()
    result = run.gate()
    if captured_stop:
        assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP, result.reason_codes()
        assert R.REOPEN_PRE_BINDING_NON_NULL in _codes(result)
    else:
        assert result.disposition in (D.INVALID_CURRENT_CLIENT_GATE, D.INDETERMINATE_CURRENT_CLIENT_GATE)


@pytest.mark.parametrize("captured_stop", [True, False])
def test_cp1_review_later_arm_survives_missing_earlier_record(tmp_path, windows_shaped_paths, captured_stop):
    from dataclasses import replace

    arm = "r_refusal"
    run = Run(tmp_path, run_options(reopen_load_arm=arm if captured_stop else None))
    captured = run.collect()
    review_batch = replace(
        captured,
        artifacts=tuple(item for item in captured.artifacts if item.role != "plan117_v5_launch:a_prime:first"),
    )
    provisional = c.sha256_hex((run.run_dir / "provisional-result.json").read_bytes())
    raw = col.derive_raw_document(run.context, (review_batch,), provisional_sha256=provisional)
    result = c.reduce_document(raw, layer="raw")
    if captured_stop:
        assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP, result.reason_codes()
        assert result.primary.subject == arm
    else:
        assert result.disposition in (D.INVALID_CURRENT_CLIENT_GATE, D.INDETERMINATE_CURRENT_CLIENT_GATE)


@pytest.mark.parametrize("code", ["binding_database_unreadable", "ambiguous_database_location"])
def test_cp1_review_database_custody_failure_retains_private_scratch(tmp_path, windows_shaped_paths, monkeypatch, code):
    from dataclasses import replace

    run = Run(tmp_path)
    actions = run.host.actions()

    def refuse_database(_profile):
        raise HostError(code)

    monkeypatch.setattr(run.host, "actions", lambda: replace(actions, locate_database=refuse_database))
    run.collect()
    raw = run.raw()
    assert raw["aborted"] == {"reason_code": code, "stage": "launch"}
    assert raw["arms"][0]["launches"][0]["launch_id"] == "first"
    assert raw["custody"]["cleanup"]["targets"] == [{"role": "run_root", "removed": False, "absent_after": False}]
    assert list(run.scratch.iterdir())
    assert run.gate().disposition is not D.ACCEPTED_CURRENT_CLIENT_GATE


# The live seam's probe primitives raise ProbeError (a RuntimeError, not a HostError); its message can carry
# private paths, so it must never reach a record or the CLI.
_PRIVATE_TEXT = "operator-private-p117v5"


def _probe_error():
    from tools.probe_p11_zed_session_load import ProbeError

    return ProbeError("launch_zed", f"FileNotFoundError: C:\\Users\\{_PRIVATE_TEXT}\\zed.exe")


def _raise(exc):
    def action(*args):
        raise exc

    return action


def _fail_launch_at(run, monkeypatch, key, exc):
    original = run.host.launch

    def launch(request):
        if (request.arm_id, request.launch_id) == key:
            run.host.launches.append(key)
            raise exc
        return original(request)

    monkeypatch.setattr(run.host, "launch", launch)


def _record_bytes(run, batch):
    records = [run.run_dir.joinpath(*item.relative_locator.split("/")) for item in batch.artifacts]
    return b"".join(path.read_bytes() for path in (*records, run.run_dir / "raw-bundle.json", run.run_dir / "provisional-result.json"))


def test_an_unknown_launch_error_preserves_scratch_and_emits_a_fixed_code(tmp_path, windows_shaped_paths, monkeypatch):
    run = Run(tmp_path)
    _fail_launch_at(run, monkeypatch, ("r_cancelled", "reopen"), _probe_error())
    batch = run.collect()
    assert list(run.scratch.iterdir())
    raw = run.raw()
    assert raw["aborted"] == {"reason_code": "zed_tree_unconfirmed", "stage": "launch"}
    assert [arm["arm_id"] for arm in raw["arms"]] == ["a_prime", "r_end_turn", "r_refusal", "r_cancelled"]
    assert raw["custody"]["cleanup"]["targets"] == [{"role": "run_root", "removed": False, "absent_after": False}]
    assert c.reduce_document(raw, layer="raw").disposition is D.INDETERMINATE_CURRENT_CLIENT_GATE
    assert _PRIVATE_TEXT.encode() not in _record_bytes(run, batch)


@pytest.mark.parametrize("failure", ["unconfirmed-result", "runtime-error", "host-error"])
@pytest.mark.parametrize("has_load", [True, False], ids=["stop", "no-positive"])
def test_unconfirmed_reopen_preserves_captured_relay(tmp_path, windows_shaped_paths, monkeypatch, failure, has_load):
    from dataclasses import replace

    arm_id = "a_prime"
    run = Run(tmp_path, run_options(reopen_load_arm=arm_id if has_load else None))
    original = run.host.launch

    def launch(request):
        result = original(request)
        if (request.arm_id, request.launch_id) != (arm_id, "reopen"):
            return result
        if failure == "runtime-error":
            raise _probe_error()
        if failure == "host-error":
            raise HostError("zed_tree_unconfirmed")
        return replace(result, tree_stopped=False)

    monkeypatch.setattr(run.host, "launch", launch)
    batch = run.collect()
    raw = run.raw()
    result = c.reduce_document(raw, layer="raw")

    assert raw["aborted"] == {"reason_code": "zed_tree_unconfirmed", "stage": "launch"}
    assert run.host.approval_events[-1] == ("hold", "")
    assert list(run.scratch.iterdir())
    assert any(item.role == f"plan117_v5_relay:{arm_id}:reopen:zed-to-agent.bin" for item in batch.artifacts)
    assert all(item.role != f"plan117_v5_launch:{arm_id}:reopen" for item in batch.artifacts)
    assert _PRIVATE_TEXT.encode() not in _record_bytes(run, batch)
    if has_load:
        assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP, result.reason_codes()
        assert (result.primary.reason, result.primary.subject) == (R.REOPEN_LOAD_OBSERVED, arm_id)
    else:
        assert result.disposition in (D.INDETERMINATE_CURRENT_CLIENT_GATE, D.INVALID_CURRENT_CLIENT_GATE)
        assert R.REOPEN_LOAD_OBSERVED not in _codes(result)


@pytest.mark.parametrize("capture_error", [KeyboardInterrupt, RuntimeError], ids=["interrupt", "unexpected-error"])
@pytest.mark.parametrize("has_load", [True, False], ids=["stop", "no-positive"])
def test_unconfirmed_reopen_holds_approval_recovery_when_capture_fails(tmp_path, windows_shaped_paths, monkeypatch, capture_error, has_load):
    from dataclasses import replace

    arm_id = "a_prime"
    run = Run(tmp_path, run_options(reopen_load_arm=arm_id if has_load else None))
    original_launch = run.host.launch
    original_artifact = col._Emitter.artifact

    def launch(request):
        result = original_launch(request)
        if (request.arm_id, request.launch_id) == (arm_id, "reopen"):
            return replace(result, tree_stopped=False)
        return result

    def artifact(emit, role, *args):
        if role == f"plan117_v5_relay:{arm_id}:reopen:agent-to-zed.bin":
            raise capture_error("synthetic failure during relay capture")
        return original_artifact(emit, role, *args)

    monkeypatch.setattr(run.host, "launch", launch)
    monkeypatch.setattr(col._Emitter, "artifact", artifact)
    batch = run.collect()
    raw = run.raw()
    result = c.reduce_document(raw, layer="raw")

    assert run.host.approval_events[-1] == ("hold", "")
    assert raw["aborted"] == {"reason_code": "zed_tree_unconfirmed", "stage": "launch"}
    assert raw["custody"]["cleanup"]["targets"] == [{"role": "run_root", "removed": False, "absent_after": False}]
    roles = {item.role for item in batch.artifacts}
    assert f"plan117_v5_relay:{arm_id}:reopen:zed-to-agent.bin" in roles
    assert f"plan117_v5_relay:{arm_id}:reopen:agent-to-zed.bin" not in roles
    assert f"plan117_v5_checkpoint:{arm_id}:after_reopen" not in roles
    if has_load:
        assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP, result.reason_codes()
        assert (result.primary.reason, result.primary.subject) == (R.REOPEN_LOAD_OBSERVED, arm_id)
    else:
        assert result.disposition in (D.INDETERMINATE_CURRENT_CLIENT_GATE, D.INVALID_CURRENT_CLIENT_GATE)
        assert R.REOPEN_LOAD_OBSERVED not in _codes(result)



@pytest.mark.parametrize("fault", ["write", "cleanup"])
@pytest.mark.parametrize("has_load", [True, False], ids=["stop", "invalid"])
def test_relay_scratch_error_preserves_wire_disposition(tmp_path, windows_shaped_paths, monkeypatch, fault, has_load):
    run = Run(tmp_path, run_options(reopen_load_arm="a_prime" if has_load else None))
    run.collect()
    write_bytes = Path.write_bytes
    cleanup = col.tempfile.TemporaryDirectory.cleanup
    relay_writes = 0
    faulty_directory = None
    fault_count = 0

    def write(path, payload):
        nonlocal relay_writes, faulty_directory, fault_count
        if path.name == "zed-to-agent.bin" and path.parent.name.startswith("p117v5-relay-"):
            relay_writes += 1
            if relay_writes == 2:  # A-prime reopen, where the observed load must survive.
                faulty_directory = path.parent
                if fault == "write":
                    fault_count += 1
                    raise PermissionError("synthetic relay scratch write failure")
        return write_bytes(path, payload)

    def remove(directory):
        nonlocal fault_count
        cleanup(directory)
        if fault == "cleanup" and Path(directory.name) == faulty_directory:
            fault_count += 1
            raise PermissionError("synthetic relay scratch cleanup failure")

    monkeypatch.setattr(Path, "write_bytes", write)
    monkeypatch.setattr(col.tempfile.TemporaryDirectory, "cleanup", remove)
    redaction = col.compute_redaction(run.context, identity_tokens=())

    assert fault_count == 1
    assert redaction.gate.disposition is (D.ZERO_ENTRY_REACHABLE_STOP if has_load else D.INVALID_CURRENT_CLIENT_GATE)
    assert R.CUSTODY_ARTIFACT_FAILURE in _codes(redaction.gate)
    assert redaction.raw is not None
    assert "relay_scratch_io_failed" in redaction.raw.custody_failures
    if has_load:
        assert (redaction.gate.primary.reason, redaction.gate.primary.subject) == (R.REOPEN_LOAD_OBSERVED, "a_prime")



def test_a_runtime_error_abort_after_a_positive_signal_is_still_stop(tmp_path, windows_shaped_paths, monkeypatch):
    run = Run(tmp_path, run_options(reopen_load_arm="a_prime"))
    _fail_launch_at(run, monkeypatch, ("r_end_turn", "first"), _probe_error())
    run.collect()
    assert list(run.scratch.iterdir())
    result = run.gate()
    assert (result.disposition, result.primary.subject) == (D.ZERO_ENTRY_REACHABLE_STOP, "a_prime")


@pytest.mark.parametrize("hook", ["base_spec_bytes", "zed_identity", "prepare_source"])
def test_a_runtime_error_before_any_launch_leaves_no_scratch_and_a_fixed_code(tmp_path, windows_shaped_paths, monkeypatch, hook):
    run = Run(tmp_path)
    monkeypatch.setattr(run.host, hook, _raise(_probe_error()))
    with pytest.raises(HostError) as excinfo:
        run.collect()
    assert excinfo.value.code == "host_action_failed"
    assert _PRIVATE_TEXT not in str(excinfo.value)
    assert list(run.scratch.iterdir()) == [] and run.host.launches == []


@pytest.mark.parametrize("options,disposition", [({}, D.INVALID_CURRENT_CLIENT_GATE), ({"reopen_load_arm": "a_prime"}, D.ZERO_ENTRY_REACHABLE_STOP)])
def test_a_restoration_check_failure_still_cleans_up_and_never_claims_restoration(tmp_path, windows_shaped_paths, monkeypatch, options, disposition):
    run = Run(tmp_path, run_options(**options))
    original = run.host.normal_source_digest
    calls = []

    def digest(root):
        calls.append(root)
        if len(calls) > 1:
            raise _probe_error()
        return original(root)

    monkeypatch.setattr(run.host, "normal_source_digest", digest)
    batch = run.collect()
    assert list(run.scratch.iterdir()) == []
    raw = run.raw()
    assert raw["source"]["normal_source_sha256_after"] is None
    assert raw["aborted"] == {"reason_code": "host_action_failed", "stage": "restoration"}
    assert raw["custody"]["cleanup"]["targets"] == [{"role": "run_root", "removed": True, "absent_after": True}]
    assert c.reduce_document(raw, layer="raw").disposition is disposition
    assert _PRIVATE_TEXT.encode() not in _record_bytes(run, batch)


_TAIL_RECORDS = ("path-custody.json", "restoration.json", "cleanup.json", "run-end.json")


def _fail_tail_writes(monkeypatch, names):
    """A real storage fault inside the emitter's write after every launch completed; the message carries a private path."""
    original = Path.write_bytes

    def write_bytes(self, data):
        if self.parent.name == "plan117" and self.name in names:
            raise OSError(28, f"No space left on device: C:\\Users\\{_PRIVATE_TEXT}\\{self.name}")
        return original(self, data)

    monkeypatch.setattr(Path, "write_bytes", write_bytes)


@pytest.mark.parametrize(
    "options,names,disposition",
    [
        ({}, ("path-custody.json",), D.INVALID_CURRENT_CLIENT_GATE),
        ({"reopen_load_arm": "a_prime"}, ("path-custody.json",), D.ZERO_ENTRY_REACHABLE_STOP),
        ({}, ("cleanup.json",), D.INVALID_CURRENT_CLIENT_GATE),
        ({"reopen_load_arm": "r_refusal"}, _TAIL_RECORDS, D.ZERO_ENTRY_REACHABLE_STOP),
        ({}, _TAIL_RECORDS, D.INVALID_CURRENT_CLIENT_GATE),
    ],
)
def test_a_tail_record_storage_fault_still_cleans_up_and_keeps_the_captured_evidence(tmp_path, windows_shaped_paths, monkeypatch, options, names, disposition):
    run = Run(tmp_path, run_options(**options))
    _fail_tail_writes(monkeypatch, names)
    batch = run.collect()
    assert run.host.launches == _launch_order()
    assert list(run.scratch.iterdir()) == [], "cleanup must not depend on the tail records being writable"
    roles = {item.role for item in batch.artifacts}
    assert not {f"plan117_v5_{name.removesuffix('.json').replace('-', '_')}" for name in names} & roles
    assert all(not (run.run_dir / "artifacts" / "plan117" / name).exists() for name in names)
    assert c.reduce_document(run.raw(), layer="raw").disposition is disposition
    assert _PRIVATE_TEXT.encode() not in _record_bytes(run, batch)


@pytest.mark.parametrize("hook", ["prepare_source", "launch", "normal_source_digest"])
def test_an_interrupt_is_never_swallowed_as_a_host_failure(tmp_path, windows_shaped_paths, monkeypatch, hook):
    run = Run(tmp_path)
    if hook == "normal_source_digest":
        original = run.host.normal_source_digest
        calls = []

        def digest(root):
            calls.append(root)
            if len(calls) > 1:
                raise KeyboardInterrupt
            return original(root)

        monkeypatch.setattr(run.host, hook, digest)
    else:
        monkeypatch.setattr(run.host, hook, _raise(KeyboardInterrupt()))
    if hook == "launch":
        run.collect()
        assert run.raw()["aborted"] == {"stage": "launch", "reason_code": "zed_tree_unconfirmed"}
        assert list(run.scratch.iterdir())
    else:
        with pytest.raises(KeyboardInterrupt):
            run.collect()
        assert not (run.run_dir / "artifacts" / "plan117" / "run-end.json").exists()


def test_patched_source_substitution_is_refused_before_any_launch(tmp_path, windows_shaped_paths):
    run = Run(tmp_path, run_options(tamper_spec_kind="refusal_stub:r_refusal"))
    with pytest.raises(HostError) as excinfo:
        run.collect()
    assert excinfo.value.code == "isolated_patch_mismatch"
    assert run.host.launches == []


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("source_commit", "f" * 40, "source_commit_mismatch"),
        ("private_root_commitments", {"capture_root": "0" * 64}, "private_root_commitment_mismatch"),
        ("launch_config_sha256", "0" * 64, "run_spec_mismatch"),
        ("descriptor_fixture_sha256", "0" * 64, "run_spec_mismatch"),
        ("patch_sha256s", {kind: "0" * 64 for kind in c.SOURCE_KINDS}, "patch_identity_mismatch"),
    ],
)
def test_collect_refuses_a_run_spec_mismatch_before_launching(tmp_path, windows_shaped_paths, field, value, code):
    run = Run(tmp_path)
    run.spec = run.registry_spec(**{field: value})
    with pytest.raises(HostError) as excinfo:
        run.collect()
    assert excinfo.value.code == code
    assert run.host.launches == []


def test_collect_refuses_a_dirty_source_before_launching(tmp_path, windows_shaped_paths, monkeypatch):
    run = Run(tmp_path)
    monkeypatch.setattr(run.host, "source_facts", lambda root: col.SourceObservation(run.host_mod.SOURCE_COMMIT, run.host_mod.SOURCE_TREE, "0" * 64, c.EMPTY_BYTES_SHA256))
    with pytest.raises(HostError) as excinfo:
        run.collect()
    assert excinfo.value.code == "source_dirty"
    assert run.host.launches == []


def test_collect_refuses_a_source_whose_census_drifted(tmp_path, windows_shaped_paths, monkeypatch):
    run = Run(tmp_path)
    monkeypatch.setattr(run.host, "base_spec_bytes", lambda root, commit: SPEC_TEXT.replace('message="empty prompt"', 'message="blank prompt"').encode())
    with pytest.raises(HostError) as excinfo:
        run.collect()
    assert excinfo.value.code == "r_census_mismatch"


def test_collect_requires_the_prepared_run_key(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    (run.run_dir / col.PATH_KEY_LOCATOR).unlink()
    with pytest.raises(HostError) as excinfo:
        run.collect()
    assert excinfo.value.code == "run_key_missing"


def test_existing_run_root_is_never_reused(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    (run.scratch / f"p117v5-{RUN_ID}").mkdir()
    with pytest.raises(HostError) as excinfo:
        run.collect()
    assert excinfo.value.code == "run_root_exists"


def _fail_path_method(monkeypatch, name, target, exc):
    """A real filesystem fault on one path only; every other path keeps the real method."""
    original = getattr(Path, name)

    def method(self, *args, **kwargs):
        if self == target:
            raise exc
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, name, method)


def _early_faults():
    private = f"C:\\Users\\{_PRIVATE_TEXT}\\x"
    return [
        ("read_bytes", PermissionError(13, "Permission denied", private)),
        ("read_bytes", FileNotFoundError(2, "No such file or directory", private)),
        ("read_bytes", OSError(5, "Input/output error", private)),
        ("exists", OSError(5, "Input/output error", private)),
        ("mkdir", PermissionError(13, "Permission denied", private)),
        ("mkdir", OSError(28, "No space left on device", private)),
    ]


def _early_target(run, name):
    return run.run_dir / col.PATH_KEY_LOCATOR if name == "read_bytes" else run.scratch / f"p117v5-{RUN_ID}"


def _assert_nothing_started(run):
    assert run.host.launches == [] and list(run.scratch.iterdir()) == []
    assert not (run.run_dir / "artifacts").exists(), "no run record (start, custody or cleanup) for a run that never started"


@pytest.mark.parametrize("name,exc", _early_faults(), ids=lambda value: value if isinstance(value, str) else type(value).__name__)
def test_an_early_filesystem_fault_reports_only_a_fixed_code(tmp_path, windows_shaped_paths, monkeypatch, name, exc):
    run = Run(tmp_path)
    _fail_path_method(monkeypatch, name, _early_target(run, name), exc)
    with pytest.raises(HostError) as excinfo:
        run.collect()
    assert excinfo.value.code == "host_action_failed"
    assert _PRIVATE_TEXT not in str(excinfo.value) and _PRIVATE_TEXT not in repr(excinfo.value.args)
    _assert_nothing_started(run)


def test_a_missing_scratch_parent_reports_only_a_fixed_code(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    run.scratch.rmdir()
    run.scratch = tmp_path / _PRIVATE_TEXT / "scratch"
    with pytest.raises(HostError) as excinfo:
        run.collect()
    assert excinfo.value.code == "host_action_failed" and _PRIVATE_TEXT not in str(excinfo.value)
    assert run.host.launches == [] and not run.scratch.parent.exists()
    assert not (run.run_dir / "artifacts").exists()


@pytest.mark.parametrize("name", ["read_bytes", "mkdir"])
def test_an_interrupt_during_early_filesystem_access_still_propagates(tmp_path, windows_shaped_paths, monkeypatch, name):
    run = Run(tmp_path)
    _fail_path_method(monkeypatch, name, _early_target(run, name), KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        run.collect()
    _assert_nothing_started(run)


def test_a_malformed_run_key_keeps_its_own_code_through_collect(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    (run.run_dir / col.PATH_KEY_LOCATOR).write_bytes(b"{}")
    with pytest.raises(HostError) as excinfo:
        run.collect()
    assert excinfo.value.code == "run_key_invalid"
    _assert_nothing_started(run)


def test_tampered_artifact_after_collection_is_a_custody_failure(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    run.collect()
    path = run.run_dir / "artifacts" / "plan117" / "arms" / "a_prime" / "first" / "module-closure.json"
    path.write_bytes(path.read_bytes().replace(b"4242", b"4243"))
    result = run.gate()
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.CUSTODY_ARTIFACT_FAILURE in _codes(result)


def test_relay_tamper_that_injects_a_reopen_load_is_still_stop(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    run.collect()
    relay = run.run_dir / "artifacts" / "plan117" / "arms" / "r_internal_error" / "reopen" / "relay" / "zed-to-agent.bin"
    relay.write_bytes(relay.read_bytes() + b'{"jsonrpc":"2.0","id":9,"method":"session/load","params":{}}\n')
    result = run.gate()
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert R.CUSTODY_ARTIFACT_FAILURE in _codes(result)


def test_reordered_observations_fail_transition_chronology(tmp_path, windows_shaped_paths):
    from dataclasses import replace

    run = Run(tmp_path)
    batch = run.collect()
    observations = list(batch.observations)
    observations[6], observations[8] = observations[8], observations[6]
    reordered = replace(batch, observations=tuple(replace(o, sequence=i) for i, o in enumerate(observations)))
    raw = col.derive_raw_document(run.context, (reordered,), provisional_sha256="0" * 64)
    assert "transition_chronology_invalid" in raw["custody_failures"]
    assert c.reduce_document(raw, layer="raw").disposition is D.INVALID_CURRENT_CLIENT_GATE


def test_derivation_accepts_exactly_one_batch_from_this_collector(tmp_path, windows_shaped_paths):
    from dataclasses import replace

    run = Run(tmp_path)
    batch = run.collect()
    for batches in ((replace(batch, collector_id="acp_stream_collector"),), (batch, batch), ()):
        with pytest.raises(HostError) as excinfo:
            col.derive_raw_document(run.context, batches, provisional_sha256="0" * 64)
        assert excinfo.value.code == "collector_batch_mismatch"


def test_derivation_does_not_trust_a_substituted_path_key(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    run.collect()
    (run.run_dir / col.PATH_KEY_LOCATOR).write_bytes(c.canonical_json_bytes({"schema": col.PATH_KEY_SCHEMA, "key_hex": "1" * 64}))
    raw = run.raw()
    assert "artifact_digest_mismatch" in raw["custody_failures"]
    assert R.CUSTODY_ARTIFACT_FAILURE in _codes(c.reduce_document(raw, layer="raw"))


# --------------------------------------------------------------------------- slice 8: two-phase redaction


def _roots(tmp_path):
    roots = {name: tmp_path / name for name in ("staging", "quarantine", "sanitized")}
    for root in roots.values():
        root.mkdir()
    return roots


def _receipt(run, staged, **overrides):
    raw = staged.raw
    receipt = {
        "schema": c.RECEIPT_SCHEMA,
        "verdict": "accepting",
        "reviewer_identity": "private-reviewer",
        "reviewer_session": "review-session-1",
        "reviewer_model": "operator-private-review",
        "reviewed_at": "2026-11-21T09:00:00Z",
        "run_id": raw.run_id,
        "scenario_id": raw.scenario_id,
        "scenario_sha256": raw.scenario_sha256,
        "source_commit": raw.source.actual_source_commit,
        "raw_manifest_sha256": staged.raw_manifest_sha256,
        "raw_bundle_sha256": raw.raw_bundle_sha256,
        "sanitized_manifest_sha256": c.sha256_hex(staged.sanitized_bytes),
        "mapping_sha256": staged.mapping_sha256,
        "derivatives": [{"locator": "manifest.json", "sha256": c.sha256_hex(staged.sanitized_bytes)}],
        "redaction_report_sha256": c.sha256_hex(staged.report_bytes),
    }
    receipt.update(overrides)
    path = run.tmp / "receipt.json"
    path.write_bytes(c.canonical_json_bytes(receipt))
    return path


def _staged(tmp_path, options=None, tokens=()):
    run = Run(tmp_path, options)
    run.collect()
    roots = _roots(tmp_path)
    staged = col.stage_redaction(run.context, staging_root=roots["staging"], quarantine_root=roots["quarantine"], identity_tokens=tokens)
    return run, roots, staged


def _promote(run, roots, receipt, tokens=()):
    return col.promote_with_receipt(run.context, staging_root=roots["staging"], sanitized_root=roots["sanitized"], receipt_path=receipt, identity_tokens=tokens)


def test_stage_writes_only_private_records_and_staged_derivatives(tmp_path, windows_shaped_paths):
    import json

    run, roots, staged = _staged(tmp_path)
    assert staged.status == "awaiting_review"
    assert sorted(p.name for p in (roots["staging"] / RUN_ID).iterdir()) == ["manifest.json", "redaction-report.json"]
    assert list(roots["sanitized"].iterdir()) == [] and list(roots["quarantine"].iterdir()) == []
    raw = json.loads((run.run_dir / col.RAW_MANIFEST_LOCATOR).read_text(encoding="utf-8"))
    mapping = json.loads((run.run_dir / col.MAPPING_LOCATOR).read_text(encoding="utf-8"))
    staged_text = (roots["staging"] / RUN_ID / "manifest.json").read_text(encoding="utf-8")
    for identity in raw["path_identities"]:
        assert identity["canonical_path"] not in staged_text
    assert raw["path_commitment_key_hex"] not in staged_text
    arms_root = run.run_dir / "artifacts" / "plan117" / "arms"
    for arm_id, launch_id in _launch_order():
        authorization = json.loads((arms_root / arm_id / launch_id / "launch.json").read_bytes())
        for field in ("approval_id", "record_digest", "workspace_digest", "launch_session_id"):
            assert authorization[field] not in staged_text
    assert {entry["canonical_path"] for entry in mapping["entries"]} == {i["canonical_path"] for i in raw["path_identities"]}
    report = json.loads((roots["staging"] / RUN_ID / "redaction-report.json").read_text(encoding="utf-8"))
    assert report["privacy"] == {"status": "passed", "violations": []}
    assert report["derivatives"][0]["sha256"] == c.sha256_hex((roots["staging"] / RUN_ID / "manifest.json").read_bytes())


def test_restaging_is_idempotent_and_never_rewrites_private_records(tmp_path, windows_shaped_paths):
    run, roots, staged = _staged(tmp_path)
    before = (run.run_dir / col.RAW_MANIFEST_LOCATOR).read_bytes()
    again = col.stage_redaction(run.context, staging_root=roots["staging"], quarantine_root=roots["quarantine"], identity_tokens=())
    assert again.sanitized_bytes == staged.sanitized_bytes and (run.run_dir / col.RAW_MANIFEST_LOCATOR).read_bytes() == before


def test_accepting_receipt_promotes_manifest_report_and_attestation(tmp_path, windows_shaped_paths):
    import json

    run, roots, staged = _staged(tmp_path)
    final = _promote(run, roots, _receipt(run, staged))
    assert sorted(p.name for p in final.iterdir()) == ["manifest.json", "redaction-attestation.json", "redaction-report.json"]
    attestation = c.parse_attestation(json.loads((final / "redaction-attestation.json").read_text(encoding="utf-8")))
    assert attestation.sanitized_manifest_sha256 == c.sha256_hex((final / "manifest.json").read_bytes())
    assert attestation.redaction_report_sha256 == c.sha256_hex((final / "redaction-report.json").read_bytes())
    assert attestation.mapping_sha256 == c.sha256_hex((run.run_dir / col.MAPPING_LOCATOR).read_bytes())
    assert attestation.raw_manifest_sha256 == c.sha256_hex((run.run_dir / col.RAW_MANIFEST_LOCATOR).read_bytes())
    assert attestation.receipt_sha256 == c.sha256_hex(c.canonical_json_bytes(dict(attestation.receipt.document)))
    assert attestation.gate["disposition"] == D.ACCEPTED_CURRENT_CLIENT_GATE.value
    assert [p.name for p in roots["sanitized"].iterdir()] == [RUN_ID]


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"verdict": "rejecting"}, "receipt_not_accepting"),
        ({"verdict": "conditional"}, "receipt_not_accepting"),
        ({"raw_manifest_sha256": "0" * 64}, "receipt_binding_mismatch"),
        ({"mapping_sha256": "0" * 64}, "receipt_binding_mismatch"),
        ({"sanitized_manifest_sha256": "0" * 64}, "receipt_binding_mismatch"),
        ({"reviewed_at": "2026-11-20T10:00:30Z"}, "receipt_chronology_invalid"),
        ({"observation_counts": {}}, "schema_invalid"),
    ],
)
def test_non_accepting_or_mismatched_receipt_cannot_promote(tmp_path, windows_shaped_paths, overrides, code):
    run, roots, staged = _staged(tmp_path)
    with pytest.raises(HostError) as excinfo:
        _promote(run, roots, _receipt(run, staged, **overrides))
    assert excinfo.value.code == code
    assert list(roots["sanitized"].iterdir()) == []


def test_missing_receipt_cannot_promote(tmp_path, windows_shaped_paths):
    run, roots, _staged_result = _staged(tmp_path)
    with pytest.raises(HostError) as excinfo:
        _promote(run, roots, tmp_path / "absent.json")
    assert excinfo.value.code == "receipt_missing"


def test_altered_staged_derivative_cannot_promote(tmp_path, windows_shaped_paths):
    run, roots, staged = _staged(tmp_path)
    path = roots["staging"] / RUN_ID / "redaction-report.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(HostError) as excinfo:
        _promote(run, roots, _receipt(run, staged))
    assert excinfo.value.code == "staged_derivative_mismatch"


def test_artifact_tamper_after_review_breaks_the_receipt_binding(tmp_path, windows_shaped_paths):
    run, roots, staged = _staged(tmp_path)
    receipt = _receipt(run, staged)
    path = run.run_dir / "artifacts" / "plan117" / "arms" / "a_prime" / "first" / "launch.json"
    path.write_bytes(path.read_bytes().replace(b'"timed_out":false', b'"timed_out":true'))
    with pytest.raises(HostError):
        _promote(run, roots, receipt)
    assert list(roots["sanitized"].iterdir()) == []


def test_promoted_run_is_never_overwritten(tmp_path, windows_shaped_paths):
    run, roots, staged = _staged(tmp_path)
    receipt = _receipt(run, staged)
    _promote(run, roots, receipt)
    with pytest.raises(HostError) as excinfo:
        _promote(run, roots, receipt)
    assert excinfo.value.code == "promoted_run_exists"


def test_operator_identity_in_a_sanitized_field_is_quarantined(tmp_path, windows_shaped_paths):
    import json

    run, roots, staged = _staged(tmp_path, tokens=("zed",))
    assert staged.status == "quarantined"
    assert not (roots["staging"] / RUN_ID).exists()
    report = json.loads((roots["quarantine"] / RUN_ID / "redaction-report.json").read_text(encoding="utf-8"))
    assert report["privacy"] == {"status": "failed", "violations": ["operator_identity"]}
    with pytest.raises(HostError) as excinfo:
        _promote(run, roots, _receipt(run, staged), tokens=("zed",))
    assert excinfo.value.code == "redaction_not_eligible"


def test_stop_evidence_is_promotable_and_keeps_its_disposition(tmp_path, windows_shaped_paths):
    import json

    run, roots, staged = _staged(tmp_path, run_options(reopen_load_arm="a_prime"))
    final = _promote(run, roots, _receipt(run, staged))
    assert json.loads((final / "redaction-attestation.json").read_text(encoding="utf-8"))["gate"]["disposition"] == D.ZERO_ENTRY_REACHABLE_STOP.value



def test_cp1_review_launcher_public_identity_is_path_independent(tmp_path, windows_shaped_paths):
    from dataclasses import replace

    run = Run(tmp_path)
    run.collect()
    staged = col.compute_redaction(run.context, identity_tokens=())
    assert staged.status == "awaiting_review"
    raw = staged.raw
    sanitized = c.parse_sanitized_manifest(json.loads(staged.sanitized_bytes))
    canonical = col.render_launcher_bytes(Path("ISOLATED_SOURCE"), Path("MODULE_CLOSURE_REPORT"))
    expected_sha256, expected_bytes = c.sha256_hex(canonical), len(canonical)
    for private_source, public_source in zip(raw.isolated_sources, sanitized.isolated_sources, strict=True):
        private_launcher = raw.identity(private_source.launcher_role)
        public_launcher = sanitized.identity(public_source.launcher_role)
        assert private_launcher.sha256 == private_source.launcher_sha256
        assert private_launcher.sha256 != expected_sha256
        assert private_launcher.sha256.encode() not in staged.sanitized_bytes
        assert (public_launcher.sha256, public_launcher.size_bytes) == (expected_sha256, expected_bytes)
        assert public_source.launcher_sha256 == expected_sha256
    assert c.reduce_gate(sanitized) == staged.gate

    source, *other_sources = raw.isolated_sources
    mismatched = replace(raw, isolated_sources=(replace(source, launcher_sha256="0" * 64), *other_sources))
    public, _ = c.derive_sanitized_manifest(mismatched)
    assert c.reduce_document(public, layer="sanitized").disposition is D.INVALID_CURRENT_CLIENT_GATE

    incomplete = replace(raw, isolated_sources=tuple(other_sources))
    public, _ = c.derive_sanitized_manifest(incomplete)
    launcher = next(item for item in public["path_identities"] if item["role"] == source.launcher_role)
    assert (launcher["sha256"], launcher["size_bytes"]) == (expected_sha256, expected_bytes)
    assert raw.identity(source.launcher_role).sha256 in c.private_forbidden_strings(incomplete)
    assert c.reduce_document(public, layer="sanitized").disposition is D.INVALID_CURRENT_CLIENT_GATE


def test_redaction_requires_the_provisional_custody_result(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    run.collect()
    (run.run_dir / "provisional-result.json").unlink()
    roots = _roots(tmp_path)
    with pytest.raises(HostError) as excinfo:
        col.stage_redaction(run.context, staging_root=roots["staging"], quarantine_root=roots["quarantine"], identity_tokens=())
    assert excinfo.value.code == "provisional_missing"



@pytest.mark.parametrize("arm", ["a_prime", "r_refusal"])
def test_missing_classification_preserves_captured_stop(tmp_path, windows_shaped_paths, arm):
    run = Run(tmp_path, run_options(reopen_load_arm=arm, cleanup_fails=True))
    run.collect()
    (run.run_dir / "provisional-result.json").unlink()
    roots = _roots(tmp_path)

    staged = col.stage_redaction(run.context, staging_root=roots["staging"], quarantine_root=roots["quarantine"], identity_tokens=())

    assert staged.status == "underivable"
    assert staged.gate.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert "custody_artifact_failure:provisional_missing" in staged.gate.reason_codes()
    assert R.SCHEMA_INVALID in _codes(staged.gate)
    assert R.CLEANUP_UNVERIFIED in _codes(staged.gate)
    assert list(roots["staging"].iterdir()) == []
    assert list(roots["sanitized"].iterdir()) == []


def test_redaction_refuses_a_tampered_raw_bundle(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    run.collect()
    bundle = run.run_dir / "raw-bundle.json"
    bundle.write_bytes(bundle.read_bytes().replace(b"plan117_v5_run_start", b"plan117_v5_run_begin", 1))
    roots = _roots(tmp_path)
    with pytest.raises(HostError) as excinfo:
        col.stage_redaction(run.context, staging_root=roots["staging"], quarantine_root=roots["quarantine"], identity_tokens=())
    assert excinfo.value.code == "digest_mismatch"


# --------------------------------------------------------------------------- slice 9: trusted checkout inputs and live seam


def test_registered_scenario_is_the_checkout_file_by_path_not_by_content(tmp_path):
    import shutil

    registered = REPO / col.SCENARIO_RELATIVE
    assert col.require_registered_scenario(registered, REPO) == registered.read_bytes()
    copy = tmp_path / registered.name
    shutil.copyfile(registered, copy)
    for candidate in (copy, tmp_path / "missing.toml"):
        with pytest.raises(HostError) as excinfo:
            col.require_registered_scenario(candidate, REPO)
        assert excinfo.value.code == "plan117_v5_scenario_unregistered"


def test_committed_approved_run_registry_is_empty_with_no_invented_approval():
    import json

    registry, payload = col.load_trusted_registry(REPO)
    assert registry.runs == ()
    assert json.loads(payload) == {"schema": c.RUN_REGISTRY_SCHEMA, "runs": []}


def test_registry_is_read_only_from_the_given_checkout(tmp_path):
    with pytest.raises(HostError) as excinfo:
        col.load_trusted_registry(tmp_path)
    assert excinfo.value.code == "approved_runs_missing"
    (tmp_path / "reports").mkdir()
    (tmp_path / col.APPROVED_RUNS_RELATIVE).write_text('{"schema":"other","runs":[]}', encoding="utf-8")
    with pytest.raises(HostError) as excinfo:
        col.load_trusted_registry(tmp_path)
    assert excinfo.value.code == "schema_invalid"


def test_descriptor_fixture_loads_with_its_exact_file_hash():
    fixture, digest = col.load_descriptor_fixture(REPO)
    assert fixture == FIXTURE
    assert digest == FIXTURE_SHA


def test_git_blob_hash_matches_git_object_hashing():
    assert col.git_blob_sha1(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"  # pragma: allowlist secret - public Git blob hash of fixed test bytes
    assert col.git_blob_sha1(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"  # pragma: allowlist secret - public Git blob hash of fixed test bytes


COMMIT = "6e5478a0225671ae9ed566b494f66a300562a6b5"  # pragma: allowlist secret - public Git commit pin (base commit object)


def _invocation(**overrides):
    record = {
        "schema": col.INVOCATION_RECORD_SCHEMA,
        "run_id": RUN_ID,
        "checkout_commit": COMMIT,
        "scenario_blob_sha1": col.git_blob_sha1((REPO / col.SCENARIO_RELATIVE).read_bytes()),
        "registry_blob_sha1": col.git_blob_sha1((REPO / col.APPROVED_RUNS_RELATIVE).read_bytes()),
        "descriptor_fixture_blob_sha1": col.git_blob_sha1((REPO / col.DESCRIPTOR_FIXTURE_RELATIVE).read_bytes()),
    }
    record.update(overrides)
    return record


def test_invocation_record_pins_checkout_commit_and_trust_input_blobs(tmp_path):
    record = tmp_path / "invocation.json"
    record.write_bytes(c.canonical_json_bytes(_invocation()))
    col.verify_invocation_record(record, checkout_root=REPO, checkout_commit=COMMIT, forbidden_roots=(tmp_path / "capture",), run_id=RUN_ID)


@pytest.mark.parametrize(
    "overrides",
    [{"registry_blob_sha1": "0" * 40}, {"scenario_blob_sha1": "0" * 40}, {"descriptor_fixture_blob_sha1": "0" * 40},
     {"checkout_commit": "f" * 40}, {"run_id": "p117v5-run-0002"}, {"extra": 1}, {"schema": "other"}],
)
def test_invocation_record_mismatch_is_refused(tmp_path, overrides):
    record = tmp_path / "invocation.json"
    record.write_bytes(c.canonical_json_bytes(_invocation(**overrides)))
    with pytest.raises(HostError) as excinfo:
        col.verify_invocation_record(record, checkout_root=REPO, checkout_commit=COMMIT, forbidden_roots=(), run_id=RUN_ID)
    assert excinfo.value.code in {"invocation_record_mismatch", "invocation_record_invalid"}


def test_invocation_record_inside_the_run_roots_is_refused(tmp_path):
    capture = tmp_path / "capture"
    capture.mkdir()
    record = capture / "invocation.json"
    record.write_bytes(c.canonical_json_bytes(_invocation()))
    with pytest.raises(HostError) as excinfo:
        col.verify_invocation_record(record, checkout_root=REPO, checkout_commit=COMMIT, forbidden_roots=(capture,), run_id=RUN_ID)
    assert excinfo.value.code == "invocation_record_inside_run_roots"


def test_real_host_actions_refuse_to_run_under_pytest():
    with pytest.raises(HostError) as excinfo:
        col.real_host_actions(REPO)
    assert excinfo.value.code == "plan117_v5_real_actions_forbidden_in_pytest"


# --------------------------------------------------------------------------- CP1 Fable findings (S2, S3, S5, M8, M9, M10, M13)


def test_a_bound_row_among_several_threads_is_still_a_positive_binding(tmp_path):
    path = make_zed_database(tmp_path / "db.sqlite", [(b"\x01" * 16, None), (b"\x02" * 16, "session-" + "e" * 32)])
    binding = col.read_database_binding(path)
    assert binding.session_binding is not None and binding.thread_id is None


def test_a_bound_second_thread_before_reopen_latches_stop_through_the_pipeline(tmp_path, windows_shaped_paths):
    run = Run(tmp_path, run_options(second_thread_bound_arm="r_refusal"))
    run.collect()
    result = run.gate()
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert result.primary.reason is R.REOPEN_PRE_BINDING_NON_NULL


def test_an_unreadable_in_root_module_makes_the_closure_report_incomplete(tmp_path, monkeypatch):
    import asyncio
    import json
    import sys
    import types

    from optimus.acp import server

    report = tmp_path / "closure.json"

    async def fake_serve(self, *args, **kwargs):
        return None

    monkeypatch.setattr(server.AcpStreamServer, "serve", fake_serve)
    monkeypatch.setattr(server.AcpStreamServer, "serve_ndjson", fake_serve)
    ghost = types.ModuleType("optimus.p117v5_ghost_module")
    ghost.__file__ = str(REPO / "src" / "optimus" / "p117v5_ghost_module.py")
    monkeypatch.setitem(sys.modules, ghost.__name__, ghost)
    exec(compile(col.render_launcher_bytes(REPO, report), "launcher.py", "exec"), {"__name__": "p117v5_launcher_under_test"})  # noqa: S102
    asyncio.run(server.AcpStreamServer.serve(None))
    document = json.loads(report.read_text(encoding="utf-8"))
    # The repository stands in for the isolated root here, so pytest's own in-root entry shims are reported too.
    assert "optimus.p117v5_ghost_module" in document["inspection_failures"]
    assert all(entry["module_name"] != ghost.__name__ for entry in document["entries"])


def test_a_closure_report_with_inspection_failures_is_refused():
    with pytest.raises(c.ContractError):
        col.parse_closure_report(_closure(inspection_failures=["optimus.some_module"]), source_root_canonical=ROOT)


def test_a_closure_report_must_declare_its_inspection_failures():
    import json

    document = json.loads(_closure())
    document.pop("inspection_failures")
    with pytest.raises(c.ContractError):
        col.parse_closure_report(c.canonical_json_bytes(document), source_root_canonical=ROOT)


def _real_actions_with_recorded_git(monkeypatch, outputs):
    import subprocess

    import tools.probe_p11_zed_session_load as probe

    calls = []

    class Completed:
        def __init__(self, stdout):
            self.returncode, self.stdout = 0, stdout

    def fake_run(argv, cwd=None, **kwargs):
        calls.append((tuple(argv), Path(cwd)))
        return Completed(outputs.get(tuple(argv[1:]), b""))

    blobs = []
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(probe, "git_cat_file_blob", lambda root, commit, path: blobs.append((Path(root), commit, path)) or SPEC_TEXT.encode())
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    return col.real_host_actions(REPO), calls, blobs


def test_real_source_facts_inspect_the_requested_root_not_the_machinery_checkout(tmp_path, monkeypatch):
    outputs = {("rev-parse", "HEAD"): b"a" * 40 + b"\n", ("rev-parse", "HEAD^{tree}"): b"b" * 40 + b"\n", ("diff", "HEAD", "--binary"): b"", ("ls-files", "-z", "--others", "--exclude-standard"): b""}
    actions, calls, _ = _real_actions_with_recorded_git(monkeypatch, outputs)
    facts = actions.source_facts(tmp_path)
    assert calls and {cwd for _, cwd in calls} == {tmp_path}
    assert (facts.actual_source_commit, facts.actual_source_tree) == ("a" * 40, "b" * 40)


def test_real_base_spec_is_read_from_the_executing_root_at_the_pinned_commit(tmp_path, monkeypatch):
    actions, _, blobs = _real_actions_with_recorded_git(monkeypatch, {})
    assert actions.base_spec_bytes(tmp_path, "c" * 40) == SPEC_TEXT.encode()
    assert blobs == [(tmp_path, "c" * 40, "src/optimus/acp/spec.py")]


def test_collect_binds_the_executing_source_root_separately_from_the_registry_checkout(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    seen = []
    original = run.host.source_facts
    run.host.source_facts = lambda root: seen.append(Path(root)) or original(root)
    run.collect()
    assert seen == [run.normal] and run.normal != REPO


def test_census_covers_the_pre_dispatch_request_handler():
    traced = col.trace_first_prompt_census(SPEC_TEXT)
    assert any(function == "_handle_client_request" for function, *_ in traced)
    col.verify_census(FIXTURE, SPEC_TEXT)


def test_new_pre_dispatch_refusal_fails_structural_coverage():
    mutated = SPEC_TEXT.replace(
        '        method = request["method"]\n',
        '        method = request["method"]\n        if method == "x":\n            return self._non_turn(error_response(request_id, JsonRpcError(code=INTERNAL_ERROR, message="x")), ownership_slot)\n',
        1,
    )
    assert mutated != SPEC_TEXT
    with pytest.raises(HostError):
        col.verify_census(FIXTURE, mutated)


@pytest.mark.parametrize("code", ["-32600", True, None, 1.5])
def test_a_non_integer_error_code_is_undecodable_not_coerced(code):
    message = col.RelayMessage(0, 10, {"jsonrpc": "2.0", "id": 1, "error": {"code": code, "message": "m"}}, "")
    assert col.wire_event(0, "agent_to_zed", message) is None


def test_exact_result_bytes_survive_unusual_json_whitespace():
    text = '{"jsonrpc":"2.0",\r"id":1 ,\r"result" :\t{ }\r}'
    message = col.RelayMessage(0, len(text), {"jsonrpc": "2.0", "id": 1, "result": {}}, text)
    assert col.wire_event(0, "agent_to_zed", message)["result_bytes_sha256"] == c.sha256_hex(b"{ }")


def test_pre_launch_refusal_removes_the_scratch_run_root(tmp_path, windows_shaped_paths):
    run = Run(tmp_path, run_options(tamper_spec_kind="load_only_stub"))
    with pytest.raises(HostError):
        run.collect()
    assert list(run.scratch.iterdir()) == []


# --------------------------------------------------------------------------- CP1 M3: unrelated malformed artifacts never mask captured STOP

_UNRELATED_ARTIFACTS = (
    "artifacts/plan117/cleanup.json",
    "artifacts/plan117/source.json",
    "artifacts/plan117/path-custody.json",
    "artifacts/plan117/restoration.json",
    "artifacts/plan117/client.json",
    "artifacts/plan117/isolated-sources.json",
    "artifacts/plan117/run-start.json",
    "artifacts/plan117/run-end.json",
    "artifacts/plan117/arms/prompted/lifecycle_a/launch.json",
    "artifacts/plan117/arms/r_end_turn/after_first/checkpoint.json",
)


def _break(run, locator, how):
    path = run.run_dir.joinpath(*locator.split("/"))
    if how == "malformed":
        path.write_bytes(b"{not json")
    elif how == "wrong-shape":
        path.write_bytes(b'{"schema":"other"}')
    else:
        path.unlink()


@pytest.mark.parametrize("locator", _UNRELATED_ARTIFACTS)
@pytest.mark.parametrize("how", ["malformed", "wrong-shape", "deleted"])
def test_an_unrelated_broken_artifact_cannot_mask_a_captured_reopen_load(tmp_path, windows_shaped_paths, locator, how):
    run = Run(tmp_path, run_options(reopen_load_arm="a_prime"))
    run.collect()
    _break(run, locator, how)
    raw = run.raw()
    result = c.reduce_document(raw, layer="raw")
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP, (locator, how, result.reason_codes())
    assert raw["custody_failures"]


@pytest.mark.parametrize("filename", ["relay-summary.json", "relay-index.ndjson"])
@pytest.mark.parametrize("captured_reopen", [False, True])
def test_relay_metadata_decode_failure_preserves_reopen_evidence(
    tmp_path, windows_shaped_paths, monkeypatch, filename, captured_reopen,
):
    from types import SimpleNamespace

    from tools import plan117_custody_relay as relay

    arm = "r_cancelled"
    run = Run(tmp_path, run_options(reopen_load_arm=arm if captured_reopen else None))
    run.collect()
    marker = '{"fixture":"decoder depth failure"}'
    path = run.run_dir / "artifacts" / "plan117" / "arms" / arm / "reopen" / "relay" / filename
    path.write_text(marker + "\n", encoding="utf-8")

    def decode(payload, *args, **kwargs):
        if payload in (marker, marker + "\n", marker.encode(), (marker + "\n").encode()):
            raise RecursionError("simulated decoder depth limit")
        return json.loads(payload, *args, **kwargs)

    # Simulate the decoder limit only in the three readers and only for the fixture marker.
    decoder = SimpleNamespace(**{**vars(json), "loads": decode})
    for module in (c, col, relay):
        monkeypatch.setattr(module, "json", decoder)

    raw = run.raw()
    result = c.reduce_document(raw, layer="raw")
    assert "relay_capture_invalid" in raw["custody_failures"]
    if filename == "relay-summary.json":
        assert "launch_argv_mismatch" in raw["custody_failures"]
    if captured_reopen:
        assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP
        assert result.primary.reason is R.REOPEN_LOAD_OBSERVED
    else:
        assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE


@pytest.mark.parametrize("filename", ["relay-summary.json", "relay-index.ndjson"])
@pytest.mark.parametrize("captured_reopen", [False, True])
def test_relay_numeric_conversion_failure_preserves_reopen_evidence(
    tmp_path, windows_shaped_paths, monkeypatch, filename, captured_reopen,
):
    from tools import plan117_custody_relay as relay

    arm = "r_cancelled"
    run = Run(tmp_path, run_options(reopen_load_arm=arm if captured_reopen else None))
    run.collect()
    marker = "simulated conversion failure"
    path = run.run_dir / "artifacts" / "plan117" / "arms" / arm / "reopen" / "relay" / filename
    lines = path.read_text(encoding="utf-8").splitlines()
    metadata = json.loads(lines[0])
    field = "zed_to_agent_bytes" if filename == "relay-summary.json" else "sequence"
    metadata[field] = marker
    lines[0] = json.dumps(metadata)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def convert(value):
        if value == marker:
            raise OverflowError("simulated relay counter conversion failure")
        return int(value)

    monkeypatch.setattr(relay, "int", convert, raising=False)
    raw = run.raw()
    result = c.reduce_document(raw, layer="raw")
    assert "relay_capture_invalid" in raw["custody_failures"]
    if captured_reopen:
        assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP
        assert result.primary.reason is R.REOPEN_LOAD_OBSERVED
    else:
        assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE


def test_a_broken_artifact_cannot_mask_a_captured_pre_reopen_binding(tmp_path, windows_shaped_paths):
    run = Run(tmp_path, run_options(pre_reopen_binding_arm="r_cancelled"))
    run.collect()
    _break(run, "artifacts/plan117/cleanup.json", "malformed")
    _break(run, "artifacts/plan117/arms/r_cancelled/first/launch.json", "malformed")
    assert c.reduce_document(run.raw(), layer="raw").disposition is D.ZERO_ENTRY_REACHABLE_STOP


@pytest.mark.parametrize("locator", _UNRELATED_ARTIFACTS)
def test_an_unrelated_broken_artifact_without_a_positive_is_invalid_not_an_exception(tmp_path, windows_shaped_paths, locator):
    run = Run(tmp_path)
    run.collect()
    _break(run, locator, "malformed")
    result = c.reduce_document(run.raw(), layer="raw")
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.CUSTODY_ARTIFACT_FAILURE in _codes(result) or R.SCHEMA_INVALID in _codes(result)


def test_redaction_of_an_underivable_run_still_reports_the_captured_stop(tmp_path, windows_shaped_paths):
    run = Run(tmp_path, run_options(reopen_load_arm="r_internal_error"))
    run.collect()
    _break(run, "artifacts/plan117/path-custody.json", "malformed")
    roots = _roots(tmp_path)
    staged = col.stage_redaction(run.context, staging_root=roots["staging"], quarantine_root=roots["quarantine"], identity_tokens=())
    assert staged.status == "underivable"
    assert staged.gate.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert list(roots["staging"].iterdir()) == [] and list(roots["sanitized"].iterdir()) == []


# --------------------------------------------------------------------------- consolidated Codex CP1 review (Serious 2-5)


def _rewrite_json(path, mutate):
    import json

    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(json.dumps(document, separators=(",", ":"), sort_keys=True), encoding="utf-8")


# ---- Serious 4: a valid first prompt, not an empty/invalid request, is required


@pytest.mark.parametrize(
    "prompt,valid",
    [
        ([{"type": "text", "text": "hi"}], True),
        ([{"type": "text", "text": "hi"}, {"type": "image", "data": "x"}], True),
        ([], False),
        ([{"type": "text", "text": "   "}], False),
        ([{"type": "image", "data": "x"}], False),
        ([{"type": "text", "text": 5}], False),
        ("hi", False),
        (None, False),
    ],
)
def test_prompt_validity_is_derived_from_the_captured_request_with_production_semantics(prompt, valid):
    message = col.RelayMessage(0, 1, {"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": {"sessionId": "session-" + "a" * 32, "prompt": prompt}}, "")
    event = col.wire_event(0, "zed_to_agent", message)
    assert event["prompt_valid"] is valid
    assert "hi" not in json.dumps(event)


def test_prompt_validity_needs_well_formed_params():
    for params in ({"prompt": [{"type": "text", "text": "hi"}]}, None, {"sessionId": 5, "prompt": [{"type": "text", "text": "hi"}]}):
        message = col.RelayMessage(0, 1, {"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": params}, "")
        assert col.wire_event(0, "zed_to_agent", message)["prompt_valid"] is False


def test_non_prompt_events_carry_no_prompt_validity():
    message = col.RelayMessage(0, 1, {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}, "")
    assert col.wire_event(0, "zed_to_agent", message)["prompt_valid"] is None


@pytest.mark.parametrize("descriptor_id", c.R_DESCRIPTOR_IDS)
def test_refusal_stub_keeps_the_production_empty_prompt_rejection_boundary(descriptor_id, tmp_path):
    import asyncio
    import sys

    name, module = _load_patched_module(f"refusal_stub:{descriptor_id}")
    try:
        async def drive():
            outbound = module.RecordingOutboundChannel()
            adapter = module.AcpDuplexAdapter(runner=_NeverRunner(), workspace_root=tmp_path, sessions=module.InMemoryAcpSpecSessionStore(), outbound=outbound)
            await adapter.handle_client_request({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": module.ACP_PROTOCOL_VERSION}})
            new = (await adapter.handle_client_request({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}})).response
            session_id = new["result"]["sessionId"]
            replies = []
            for number, prompt in enumerate(([], [{"type": "text", "text": "hello"}], [{"type": "text", "text": "again"}])):
                envelope = await adapter.handle_client_request({"jsonrpc": "2.0", "id": 2 + number, "method": "session/prompt", "params": {"sessionId": session_id, "prompt": prompt}})
                replies.append(envelope.response)
            return replies

        empty, valid, second = asyncio.run(drive())
    finally:
        sys.modules.pop(name, None)
    descriptor = {d.descriptor_id: d for d in FIXTURE.descriptors}[descriptor_id]
    assert empty["error"] == {"code": -32600, "message": "empty prompt"}  # production rejection, before the stub
    body = valid["result"] if "result" in valid else valid["error"]
    assert c.sha256_hex(c.canonical_json_bytes(body)) == c.expected_response_sha256(descriptor)
    assert second["error"]["message"] == "plan117-v5 stub allows one prompt"


@pytest.mark.parametrize("arm_id", c.R_DESCRIPTOR_IDS)
@pytest.mark.parametrize("shape", [(), ({"type": "text", "text": "  "},), ({"type": "image", "data": "x"},)])
def test_an_invalid_first_prompt_cannot_satisfy_any_r_case_through_the_pipeline(tmp_path, windows_shaped_paths, arm_id, shape):
    run = Run(tmp_path, run_options(empty_prompt_arm=arm_id, empty_prompt_shape=shape))
    run.collect()
    raw = run.raw()
    result = c.reduce_document(raw, layer="raw")
    assert result.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.R_PROMPT_INVALID in _codes(result)


def test_a_valid_prompt_is_recorded_only_as_a_validity_fact(tmp_path, windows_shaped_paths):
    sentinel = "PROMPT-SENTINEL-7Q3"
    run = Run(tmp_path, run_options(empty_prompt_arm="r_refusal", empty_prompt_shape=({"type": "text", "text": sentinel},)))
    run.collect()
    raw = run.raw()
    assert c.reduce_document(raw, layer="raw").disposition is D.ACCEPTED_CURRENT_CLIENT_GATE
    assert sentinel not in json.dumps(raw)


# ---- Serious 2: nested malformation / read failure / presence metadata never hide captured signals


def test_an_unhashable_custody_role_cannot_mask_a_captured_reopen_load(tmp_path, windows_shaped_paths):
    run = Run(tmp_path, run_options(reopen_load_arm="r_end_turn"))
    run.collect()
    _rewrite_json(run.run_dir / "artifacts" / "plan117" / "path-custody.json", lambda d: d["identities"][0].update(role=[]))
    raw = run.raw()
    assert c.reduce_document(raw, layer="raw").disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert raw["custody_failures"]


def test_an_unreadable_unrelated_artifact_is_a_custody_failure_not_an_exception(tmp_path, windows_shaped_paths, monkeypatch):
    run = Run(tmp_path, run_options(reopen_load_arm="a_prime"))
    run.collect()
    original = Path.read_bytes

    def read_bytes(self):
        if self.name == "cleanup.json":
            raise PermissionError("synthetic denied read")
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    raw = run.raw()
    assert c.reduce_document(raw, layer="raw").disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert "artifact_unreadable" in raw["custody_failures"]


@pytest.mark.parametrize(
    ("reopen_arm", "expected"),
    [
        ("r_refusal", D.ZERO_ENTRY_REACHABLE_STOP),
        (None, D.INVALID_CURRENT_CLIENT_GATE),
    ],
    ids=("later-stop", "no-positive"),
)
def test_redaction_continues_after_unrelated_checkpoint_copy_error(tmp_path, windows_shaped_paths, monkeypatch, reopen_arm, expected):
    run = Run(tmp_path, run_options(reopen_load_arm=reopen_arm))
    run.collect()
    copyfile = col.shutil.copyfile
    copy_failed = False

    def fail_first_database_copy(source, target, *args, **kwargs):
        nonlocal copy_failed
        if not copy_failed and Path(source).name == "db.sqlite-main" and Path(target).name == "db.sqlite":
            copy_failed = True
            raise PermissionError("closed checkpoint copy denied")
        return copyfile(source, target, *args, **kwargs)

    monkeypatch.setattr(col.shutil, "copyfile", fail_first_database_copy)
    redaction = col.compute_redaction(run.context, identity_tokens=())

    assert redaction.gate.disposition is expected
    assert R.CUSTODY_ARTIFACT_FAILURE in _codes(redaction.gate)
    assert redaction.raw is not None
    assert "checkpoint_copy_unreadable" in redaction.raw.custody_failures
    first_checkpoint = redaction.raw.arms[0].checkpoints[0]
    assert first_checkpoint.readable is False
    assert first_checkpoint.files[0].presence == "present"
    if reopen_arm is not None:
        assert redaction.gate.primary.subject == reopen_arm


@pytest.mark.parametrize(
    ("has_binding", "expected"),
    [
        (True, D.ZERO_ENTRY_REACHABLE_STOP),
        (False, D.INVALID_CURRENT_CLIENT_GATE),
    ],
    ids=("stop", "invalid"),
)
def test_redaction_preserves_checkpoint_result_after_cleanup_error(tmp_path, windows_shaped_paths, monkeypatch, has_binding, expected):
    run = Run(tmp_path, run_options(pre_reopen_binding_arm="a_prime" if has_binding else None))
    run.collect()
    cleanup = col.tempfile.TemporaryDirectory.cleanup
    cleanup_failed = False

    def fail_first_database_cleanup(directory):
        nonlocal cleanup_failed
        cleanup(directory)
        if not cleanup_failed and Path(directory.name).name.startswith("p117v5-db-"):
            cleanup_failed = True
            raise PermissionError("closed checkpoint scratch cleanup denied")

    monkeypatch.setattr(col.tempfile.TemporaryDirectory, "cleanup", fail_first_database_cleanup)
    redaction = col.compute_redaction(run.context, identity_tokens=())

    assert cleanup_failed
    assert redaction.gate.disposition is expected
    assert R.CUSTODY_ARTIFACT_FAILURE in _codes(redaction.gate)
    assert redaction.raw is not None
    assert "checkpoint_copy_cleanup_failed" in redaction.raw.custody_failures
    first_checkpoint = redaction.raw.arms[0].checkpoints[0]
    assert first_checkpoint.readable
    assert (first_checkpoint.session_binding is not None) is has_binding
    if has_binding:
        assert redaction.gate.primary.subject == "a_prime"
        assert redaction.gate.primary.reason is R.REOPEN_PRE_BINDING_NON_NULL


@pytest.mark.parametrize("presence", [{"main": False, "wal": False, "shm": False}, {}, {"wal": False}])
def test_presence_metadata_cannot_hide_a_captured_database_binding(tmp_path, windows_shaped_paths, presence):
    run = Run(tmp_path, run_options(pre_reopen_binding_arm="r_refusal"))
    run.collect()
    _rewrite_json(run.run_dir / "artifacts" / "plan117" / "arms" / "r_refusal" / "after_first" / "checkpoint.json", lambda d: d.update(presence=presence))
    raw = run.raw()
    result = c.reduce_document(raw, layer="raw")
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert result.primary.reason is R.REOPEN_PRE_BINDING_NON_NULL
    assert raw["custody_failures"]


def test_staged_redaction_reports_stop_despite_nested_malformation(tmp_path, windows_shaped_paths):
    run = Run(tmp_path, run_options(reopen_load_arm="r_internal_error"))
    run.collect()
    _rewrite_json(run.run_dir / "artifacts" / "plan117" / "path-custody.json", lambda d: d["identities"][1].update(role={"x": 1}))
    roots = _roots(tmp_path)
    staged = col.stage_redaction(run.context, staging_root=roots["staging"], quarantine_root=roots["quarantine"], identity_tokens=())
    assert staged.gate.disposition is D.ZERO_ENTRY_REACHABLE_STOP


# ---- Serious 3 (collector side): a strictly invalid but readable relay message still exposes a reopen load


@pytest.mark.parametrize(
    "line",
    [
        b'{"jsonrpc":"2.0","id":9,"method":"session/load","params":{"x":1e400}}\n',
        b'{"jsonrpc":"2.0","id":9,"method":"session/load","method":"session/load","params":{}}\n',
    ],
)
def test_a_strictly_invalid_reopen_load_line_is_still_a_positive_signal(tmp_path, windows_shaped_paths, line):
    run = Run(tmp_path)
    run.collect()
    relay = run.run_dir / "artifacts" / "plan117" / "arms" / "r_cancelled" / "reopen" / "relay" / "zed-to-agent.bin"
    relay.write_bytes(relay.read_bytes() + line)
    result = c.reduce_document(run.raw(), layer="raw")
    assert result.disposition is D.ZERO_ENTRY_REACHABLE_STOP


@pytest.mark.parametrize("fallback_failure", [False, True], ids=["strict-refusal", "fallback-refusal"])
@pytest.mark.parametrize("captured_reopen", [False, True])
def test_wire_decoder_failure_preserves_independent_reopen_evidence(
    tmp_path, windows_shaped_paths, monkeypatch, fallback_failure, captured_reopen,
):
    from types import SimpleNamespace

    arm = "r_cancelled"
    run = Run(tmp_path, run_options(reopen_load_arm=arm if captured_reopen else None))
    run.collect()
    marker = '{"fixture":"wire decoder failure"}'
    wire = run.run_dir / "artifacts" / "plan117" / "arms" / arm / "reopen" / "relay" / "zed-to-agent.bin"
    wire.write_bytes(marker.encode("utf-8") + b"\n" + wire.read_bytes())

    def strict_decode(payload, *args, **kwargs):
        if payload == marker:
            if fallback_failure:
                raise json.JSONDecodeError("simulated strict refusal", payload, 0)
            raise ValueError("simulated numeric decoder refusal")
        return json.loads(payload, *args, **kwargs)

    monkeypatch.setattr(c, "json", SimpleNamespace(**{**vars(json), "loads": strict_decode}))
    if fallback_failure:
        def fallback_decode(payload, *args, **kwargs):
            if payload == marker:
                raise RecursionError("simulated fallback decoder limit")
            return json.loads(payload, *args, **kwargs)

        monkeypatch.setattr(col, "json", SimpleNamespace(**{**vars(json), "loads": fallback_decode}))

    raw = run.raw()
    gate = c.reduce_document(raw, layer="raw")
    assert "relay_capture_invalid" in raw["custody_failures"]
    if captured_reopen:
        assert gate.disposition is D.ZERO_ENTRY_REACHABLE_STOP
        assert gate.primary.reason is R.REOPEN_LOAD_OBSERVED
    else:
        assert gate.disposition is D.INVALID_CURRENT_CLIENT_GATE


@pytest.mark.parametrize("captured_reopen", [False, True], ids=["invalid", "stop"])
def test_relay_text_encoding_failure_preserves_independent_reopen_evidence(tmp_path, windows_shaped_paths, monkeypatch, captured_reopen):
    arm = "r_refusal"
    run = Run(tmp_path, run_options(reopen_load_arm=arm if captured_reopen else None))
    run.collect()
    first_session = run.host_mod.session_for(arm, "first")
    wire_event = col.wire_event

    def normalize(index, direction, message):
        params = message.message.get("params", {})
        update = params.get("update", {})
        if params.get("sessionId") == first_session and "content" in update:
            raise UnicodeEncodeError("utf-8", "synthetic text", 0, 1, "simulated relay text encoding failure")
        return wire_event(index, direction, message)

    monkeypatch.setattr(col, "wire_event", normalize)
    raw = run.raw()
    first = next(arm_record for arm_record in raw["arms"] if arm_record["arm_id"] == arm)["launches"][0]
    assert first["undecodable_bytes"] is True

    gate = c.reduce_document(raw, layer="raw")
    assert R.WIRE_INCONSISTENT in _codes(gate)
    if captured_reopen:
        assert gate.disposition is D.ZERO_ENTRY_REACHABLE_STOP
        assert gate.primary.reason is R.REOPEN_LOAD_OBSERVED
    else:
        assert gate.disposition is D.INVALID_CURRENT_CLIENT_GATE


def test_parse_ndjson_recovers_strictly_invalid_objects_but_flags_them():
    messages, undecodable = col.parse_ndjson_messages(b'{"a":1e400}\n{"a":1,"a":2}\n')
    assert undecodable is True and [m.message for m in messages] == [{"a": float("inf")}, {"a": 2}]


# ---- Serious 5: strict v5 ingress before the shared loader normalizes


def _rebind_bundle(run, mutate):
    from evidence_handoff.collector.bundles import _payload_sha256

    path = run.run_dir / "raw-bundle.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    document.pop("bundle_sha256")
    document["bundle_sha256"] = _payload_sha256(document)
    path.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["batches"][0]["observations"][0].update(sequence=False),
        lambda d: d["batches"][0]["observations"][3].update(sequence="3"),
        lambda d: d["batches"][0]["observations"][0].update(extra=1),
        lambda d: d["batches"][0].update(extra=1),
        lambda d: d.update(extra=1),
        lambda d: d["batches"][0]["artifacts"][0].update(size_bytes=True),
        lambda d: d["batches"][0]["artifacts"][0].update(extra="x"),
        lambda d: d["batches"][0]["observations"][0].update(correlation=[["arm_id", 1], ["launch_id", ""]]),
    ],
)
def test_strict_v5_ingress_flags_coercion_and_unknown_fields_without_masking_stop(tmp_path, windows_shaped_paths, mutation):
    run = Run(tmp_path, run_options(reopen_load_arm="a_prime"))
    run.collect()
    _rebind_bundle(run, mutation)
    staged = col.compute_redaction(run.context, identity_tokens=())
    assert staged.gate.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert col.strict_bundle_ingress(run.context)[0] != ()


def test_strict_v5_ingress_without_a_positive_is_invalid(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    run.collect()
    _rebind_bundle(run, lambda d: d["batches"][0]["observations"][0].update(sequence=False))
    staged = col.compute_redaction(run.context, identity_tokens=())
    assert staged.gate.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.CUSTODY_ARTIFACT_FAILURE in _codes(staged.gate)


def test_the_unmodified_bundle_passes_strict_ingress(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    run.collect()
    assert col.strict_bundle_ingress(run.context)[0] == ()


def test_an_escaping_artifact_locator_is_flagged_and_never_read(tmp_path, windows_shaped_paths, monkeypatch):
    run = Run(tmp_path, run_options(reopen_load_arm="r_refusal"))
    run.collect()
    outside = run.capture_root / "outside.json"
    outside.write_bytes(b"{}")

    def escape(d):
        artifact = next(a for a in d["batches"][0]["artifacts"] if a["role"] == "plan117_v5_cleanup")
        artifact.update(relative_locator="../outside.json", sha256=c.sha256_hex(b"{}"), size_bytes=2)

    _rebind_bundle(run, escape)
    original = Path.read_bytes
    reads = []

    def read_bytes(self):
        reads.append(Path(self).name)
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    assert "artifact_locator_invalid" in col.strict_bundle_ingress(run.context)[0]
    staged = col.compute_redaction(run.context, identity_tokens=())
    assert staged.gate.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert "outside.json" not in reads


# ---- C5 totality: non-coercible metadata and foreign identities under a verified envelope


def _unrelated_artifact(d):
    return next(a for a in d["batches"][0]["artifacts"] if a["role"] == "plan117_v5_cleanup")


# A dropped required collector artifact nulls its manifest section, so its invalidity surfaces as SCHEMA_INVALID.
_INGRESS_INVALIDITY = {R.CUSTODY_ARTIFACT_FAILURE, R.SCHEMA_INVALID}

_NON_COERCIBLE = [
    pytest.param(lambda d: d["batches"][0]["observations"][3].update(sequence=[]), id="sequence-list"),
    pytest.param(lambda d: d["batches"][0]["observations"][3].update(sequence="sentinel-raw-value"), id="sequence-text"),
    pytest.param(lambda d: d["batches"][0]["observations"][3].update(monotonic_offset_ns=None), id="offset-none"),
    pytest.param(lambda d: d["batches"][0]["observations"][0].update(correlation=[["arm_id"]]), id="correlation-short-pair"),
    pytest.param(lambda d: d["batches"][0]["observations"][0].update(correlation=[["arm_id", "", "x"]]), id="correlation-long-pair"),
    pytest.param(lambda d: d["batches"][0]["observations"][0].pop("observed_at"), id="observation-field-missing"),
    pytest.param(lambda d: _unrelated_artifact(d).update(size_bytes=None), id="artifact-size-none"),
    pytest.param(lambda d: d["batches"][0]["observations"][2].update(schema="evidence-observation-v0"), id="observation-schema"),
    pytest.param(lambda d: d["batches"][0]["observations"][2].update(run_id="p117v5-foreign-0002"), id="observation-run-id"),
    pytest.param(lambda d: d["batches"][0]["observations"][2].update(scenario_id="foreign-scenario"), id="observation-scenario-id"),
    pytest.param(lambda d: d["batches"][0].update(contract_version="v2"), id="batch-contract-version"),
]


def test_unmutated_baselines_are_clean_accepted_and_clean_stop(tmp_path, windows_shaped_paths):
    for name in ("accepted", "stop"):
        (tmp_path / name).mkdir()
    accepted = Run(tmp_path / "accepted")
    accepted.collect()
    stop = Run(tmp_path / "stop", run_options(reopen_load_arm="a_prime"))
    stop.collect()
    assert col.strict_bundle_ingress(accepted.context)[0] == () == col.strict_bundle_ingress(stop.context)[0]
    clean = col.compute_redaction(accepted.context, identity_tokens=())
    assert clean.gate.disposition is D.ACCEPTED_CURRENT_CLIENT_GATE and clean.raw.custody_failures == ()
    positive = col.compute_redaction(stop.context, identity_tokens=())
    assert positive.gate.disposition is D.ZERO_ENTRY_REACHABLE_STOP and positive.raw.custody_failures == ()
    assert R.CUSTODY_ARTIFACT_FAILURE not in _codes(positive.gate)


@pytest.mark.parametrize("mutation", _NON_COERCIBLE)
def test_non_coercible_or_foreign_metadata_keeps_the_independent_stop_and_stays_invalid(tmp_path, windows_shaped_paths, mutation):
    run = Run(tmp_path, run_options(reopen_load_arm="a_prime"))
    run.collect()
    _rebind_bundle(run, mutation)
    staged = col.compute_redaction(run.context, identity_tokens=())
    assert staged.gate.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert staged.gate.primary.subject == "a_prime"
    assert _INGRESS_INVALIDITY & set(_codes(staged.gate))
    assert col.strict_bundle_ingress(run.context)[0] != ()


@pytest.mark.parametrize("mutation", _NON_COERCIBLE)
def test_non_coercible_or_foreign_metadata_without_a_positive_is_invalid(tmp_path, windows_shaped_paths, mutation):
    run = Run(tmp_path)
    run.collect()
    _rebind_bundle(run, mutation)
    staged = col.compute_redaction(run.context, identity_tokens=())
    assert staged.gate.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert _INGRESS_INVALIDITY & set(_codes(staged.gate))


@pytest.mark.parametrize(
    "mutation,rebind,code",
    [
        (lambda d: d.update(run_id="p117v5-foreign-0002"), True, "foreign_run_id"),
        (lambda d: d.update(scenario_id="foreign-scenario"), True, "foreign_scenario_id"),
        (lambda d: d.update(schema="evidence-raw-bundle-v0"), True, "unknown_schema"),
        (lambda d: d["batches"][0]["observations"][3].update(sequence="sentinel-raw-value"), False, "digest_mismatch"),
        (lambda d: d.update(batches="sentinel-raw-value"), True, "bundle_invalid"),
    ],
)
def test_an_untrusted_envelope_is_refused_with_a_fixed_code(tmp_path, windows_shaped_paths, mutation, rebind, code):
    run = Run(tmp_path, run_options(reopen_load_arm="a_prime"))
    run.collect()
    if rebind:
        _rebind_bundle(run, mutation)
    else:
        path = run.run_dir / "raw-bundle.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        mutation(document)
        path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(HostError) as caught:
        col.compute_redaction(run.context, identity_tokens=())
    assert str(caught.value) == code and "sentinel" not in str(caught.value)
    assert col.strict_bundle_ingress(run.context)[1] is None


# ---- C5 shape: observation containers and unknown keys on the POSITIVE artifact itself


def _artifact(d, role):
    return next(a for a in d["batches"][0]["artifacts"] if a["role"] == role)


_RELAY_POSITIVE = "plan117_v5_relay:a_prime:reopen:zed-to-agent.bin"
_DB_POSITIVE = "plan117_v5_db:r_invalid_request:after_first:main"

_SHAPES = [
    pytest.param(lambda d: d["batches"][0].update(observations=None), id="observations-null"),
    pytest.param(lambda d: d["batches"][0].pop("observations"), id="observations-missing"),
    pytest.param(lambda d: d["batches"][0].update(observations={}), id="observations-object"),
    pytest.param(lambda d: d["batches"][0].update(observations="sentinel-raw-value"), id="observations-text"),
    pytest.param(lambda d: d["batches"][0].update(observations=0), id="observations-number"),
]


@pytest.mark.parametrize("mutation", _SHAPES)
def test_a_malformed_observation_container_keeps_the_captured_stop_and_stays_invalid(tmp_path, windows_shaped_paths, mutation):
    run = Run(tmp_path, run_options(reopen_load_arm="a_prime"))
    run.collect()
    _rebind_bundle(run, mutation)
    staged = col.compute_redaction(run.context, identity_tokens=())
    assert staged.gate.disposition is D.ZERO_ENTRY_REACHABLE_STOP
    assert staged.gate.primary.subject == "a_prime"
    assert _INGRESS_INVALIDITY & set(_codes(staged.gate))
    assert col.strict_bundle_ingress(run.context)[0] != ()


@pytest.mark.parametrize("mutation", _SHAPES)
def test_a_malformed_observation_container_without_a_positive_is_invalid(tmp_path, windows_shaped_paths, mutation):
    run = Run(tmp_path)
    run.collect()
    _rebind_bundle(run, mutation)
    staged = col.compute_redaction(run.context, identity_tokens=())
    assert staged.gate.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert _INGRESS_INVALIDITY & set(_codes(staged.gate))


@pytest.mark.parametrize(
    "options,role,subject,reason",
    [
        pytest.param({"reopen_load_arm": "a_prime"}, _RELAY_POSITIVE, "a_prime", R.REOPEN_LOAD_OBSERVED, id="relay"),
        pytest.param({"pre_reopen_binding_arm": "r_invalid_request"}, _DB_POSITIVE, "r_invalid_request", R.REOPEN_PRE_BINDING_NON_NULL, id="database"),
    ],
)
def test_an_unknown_key_on_the_positive_artifact_keeps_its_binding_and_stays_invalid(tmp_path, windows_shaped_paths, options, role, subject, reason):
    run = Run(tmp_path, run_options(**options))
    run.collect()
    _rebind_bundle(run, lambda d: _artifact(d, role).update(extra=1))
    staged = col.compute_redaction(run.context, identity_tokens=())
    assert (staged.gate.disposition, staged.gate.primary.subject, staged.gate.primary.reason) == (D.ZERO_ENTRY_REACHABLE_STOP, subject, reason)
    assert R.CUSTODY_ARTIFACT_FAILURE in _codes(staged.gate)
    assert "raw_bundle_ingress_invalid" in col.strict_bundle_ingress(run.context)[0]


def test_an_unknown_key_on_a_captured_relay_without_a_positive_is_invalid(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    run.collect()
    _rebind_bundle(run, lambda d: _artifact(d, _RELAY_POSITIVE).update(extra=1))
    staged = col.compute_redaction(run.context, identity_tokens=())
    assert staged.gate.disposition is D.INVALID_CURRENT_CLIENT_GATE
    assert R.CUSTODY_ARTIFACT_FAILURE in _codes(staged.gate)


@pytest.mark.parametrize(
    "change",
    [
        pytest.param({"size_bytes": None}, id="size-none"),
        pytest.param({"sha256": "0" * 63}, id="digest-malformed"),
        pytest.param({"relative_locator": "../outside.bin"}, id="locator-escaping"),
    ],
)
def test_an_unknown_key_never_rescues_an_invalid_known_field_on_the_positive_artifact(tmp_path, windows_shaped_paths, change):
    run = Run(tmp_path, run_options(reopen_load_arm="a_prime"))
    run.collect()
    _rebind_bundle(run, lambda d: _artifact(d, _RELAY_POSITIVE).update(extra=1, **change))
    staged = col.compute_redaction(run.context, identity_tokens=())
    assert staged.gate.disposition is D.INVALID_CURRENT_CLIENT_GATE



def test_collector_approves_all_arms_and_rechecks_before_every_spawn(tmp_path, windows_shaped_paths):
    run = Run(tmp_path)
    batch = run.collect()
    assert run.host.approval_events[:8] == [("approve", arm) for arm in c.ARM_IDS]
    assert run.host.approval_events[8:24] == [("verify", arm) for arm in c.ARM_IDS for _ in range(2)]
    assert run.host.approval_events[-1] == ("recover", "")
    assert len(run.host.launches) == 16
    assert batch.observations


def test_partial_approval_refusal_launches_nothing_and_recovers(tmp_path, windows_shaped_paths):
    run = Run(tmp_path, run_options(approval_failure="r_refusal"))
    run.collect()
    assert not run.host.launches
    assert run.host.approval_events[-1] == ("recover", "")
    assert not list(run.scratch.iterdir())


def test_unconfirmed_drain_retains_scratch_and_never_copies_database(tmp_path, windows_shaped_paths):
    run = Run(tmp_path, run_options(unconfirmed_drain=True))
    batch = run.collect()
    assert not any(item.role.startswith("plan117_v5_db:") for item in batch.artifacts)
    assert run.host.launches == [("a_prime", "first")]
    assert run.host.approval_events[-1] == ("hold", "")
    assert list(run.scratch.iterdir())
    assert run.gate().disposition is not D.ACCEPTED_CURRENT_CLIENT_GATE


def test_audit_observer_excludes_stale_and_ambiguous_authorizations(tmp_path):
    from types import SimpleNamespace

    approval = col.LaunchApproval("a" * 64, "appr_" + "b" * 24, "c" * 64)
    session_id = "sess_" + "d" * 24
    request = SimpleNamespace(approval=approval, launch_session_id=session_id)
    event = {
        "event_type": "authorization", "final_reason_code": "AUTHORIZED", "approval_mode": "durable",
        "approval_migration_disposition": "none", "approval_id": approval.approval_id,
        "workspace_digest": approval.workspace_digest, "launch_session_id": session_id,
    }
    row = json.dumps(event).encode() + b"\n"
    audit = tmp_path / "launch-audit.ndjson"
    audit.write_bytes(row)
    assert col._read_scoped_launch_audit(audit, len(row), request) is None
    audit.write_bytes(row * 2)
    assert col._read_scoped_launch_audit(audit, len(row), request) == event
    migration = {**event, "event_type": "approval_migration"}
    audit.write_bytes(row * 2 + json.dumps(migration).encode() + b"\n")
    assert col._read_scoped_launch_audit(audit, len(row), request) is None
    audit.write_bytes(row * 3)
    assert col._read_scoped_launch_audit(audit, len(row), request) is None
