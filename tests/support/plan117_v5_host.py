"""Deterministic host actions for the Plan 11.7 v5 collector (test support only).

The fake never starts a process or touches Zed. It writes real relay captures with the relay's own
recorder, real SQLite profile databases with Zed's ``sidebar_threads`` shape and real launcher /
closure files, so the collector's derivation and custody checks run against genuine bytes.
Behaviour switches (``FakeHostOptions``) inject one failure class at a time.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from optimus.acp.shapes import AGENT_MESSAGE_BLOCK_SEPARATOR
from tools import plan117_custody_relay as relay
from tools.evidence_gather_support import plan117_current_client_collector as collector
from tools.evidence_gather_support import plan117_current_client_contract as contract

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_COMMIT = "6e5478a0225671ae9ed566b494f66a300562a6b5"  # pragma: allowlist secret - public Git commit pin (base commit object)
SOURCE_TREE = "1" * 40
PROMPTED_SESSION = "session-" + "a" * 32


def session_for(arm_id: str, launch_id: str) -> str:
    return "session-" + hashlib.sha256(f"{arm_id}/{launch_id}".encode()).hexdigest()[:32]


@dataclass
class FakeHostOptions:
    reopen_load_arm: str | None = None
    pre_reopen_binding_arm: str | None = None
    first_launch_load_arm: str | None = None
    forced_kill: tuple[str, str] | None = None
    omit_module: str | None = None
    extra_notice_arm: str | None = None
    advertise_resume: tuple[str, str] | None = None
    deny_load_session: tuple[str, str] | None = None
    cleanup_fails: bool = False
    normal_source_changes: bool = False
    abort_at: tuple[str, str] | None = None
    tamper_spec_kind: str | None = None
    report_before_launch: tuple[str, str] | None = None
    prompted_binding_retained: bool = False
    second_thread_arm: str | None = None
    second_thread_bound_arm: str | None = None
    empty_prompt_arm: str | None = None
    empty_prompt_shape: object = ()
    approval_failure: str | None = None
    unconfirmed_drain: bool = False


@dataclass
class FakeHost:
    tmp: Path
    options: FakeHostOptions = field(default_factory=FakeHostOptions)
    clock: int = 1_000_000_000_000
    wall_tick: int = 0
    launches: list[tuple[str, str]] = field(default_factory=list)

    approval_events: list[tuple[str, str]] = field(default_factory=list)
    approval_arms: tuple[str, ...] = ()

    # ------------------------------------------------------------------ HostActions surface

    def actions(self) -> collector.HostActions:
        return collector.HostActions(
            source_facts=self.source_facts,
            normal_source_digest=self.normal_source_digest,
            base_module_bytes=self.base_module_bytes,
            zed_identity=self.zed_identity,
            prepare_source=self.prepare_source,
            launch=self.launch,
            approvals=self.approvals,
            interpreter=Path(sys.executable),
            locate_database=self.locate_database,
            remove_tree=self.remove_tree,
            monotonic_ns=self.monotonic_ns,
            wall_now=self.wall_now,
        )

    def approvals(self, control_dir: Path | None, workspaces: Any) -> FakeHost:
        self.approval_arms = tuple(workspace.arm for workspace in workspaces)
        return self

    def approve_all(self) -> None:
        for arm in self.approval_arms:
            self.approval_events.append(("approve", arm))
            if arm == self.options.approval_failure:
                raise collector.HostError("scoped_approval_declined_or_failed")

    def verify(self, arm: str) -> collector.LaunchApproval:
        self.approval_events.append(("verify", arm))
        digest = hashlib.sha256(arm.encode()).hexdigest()
        return collector.LaunchApproval(digest, f"appr_{digest[:24]}", digest)

    def recover(self, *, processes_stopped: bool) -> bool:
        self.approval_events.append(("recover" if processes_stopped else "hold", ""))
        return processes_stopped

    def monotonic_ns(self) -> int:
        self.clock += 1_000_000
        return self.clock

    def wall_now(self) -> str:
        self.wall_tick += 1
        minute, second = divmod(self.wall_tick, 60)
        return f"2026-11-20T10:{minute:02d}:{second:02d}Z"

    def source_facts(self, root: Path) -> collector.SourceObservation:
        return collector.SourceObservation(
            actual_source_commit=SOURCE_COMMIT,
            actual_source_tree=SOURCE_TREE,
            tracked_diff_sha256=contract.EMPTY_BYTES_SHA256,
            untracked_digest_sha256=contract.EMPTY_BYTES_SHA256,
        )

    def normal_source_digest(self, root: Path) -> str:
        calls = getattr(self, "_digest_calls", 0)
        self._digest_calls = calls + 1
        if self.options.normal_source_changes and calls > 0:
            return hashlib.sha256(b"changed").hexdigest()
        return hashlib.sha256(b"normal").hexdigest()

    def base_module_bytes(self, root: Path, commit: str, path: str) -> bytes:
        return (REPO_ROOT / path).read_bytes()

    def zed_identity(self) -> collector.ZedIdentity:
        executable = self.tmp / "zed-install" / "zed.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"fake-zed-binary")
        return collector.ZedIdentity(
            executable=executable,
            executable_sha256=hashlib.sha256(b"fake-zed-binary").hexdigest(),
            cli_version="Zed 1.27.0",
            app_version="1.27.0",
            source_revision="c84af5b99cbc366d675064e52b23664a015b6e35",  # pragma: allowlist secret - fake Zed source-revision fixture, not authentication material
        )

    def prepare_source(self, request: collector.SourcePreparation) -> None:
        spec = collector.render_isolated_spec(self.base_module_bytes(request.normal_source_root, SOURCE_COMMIT, contract.REQUIRED_MODULE_PATHS["optimus.acp.spec"]), request.source_kind, request.fixture)
        if self.options.tamper_spec_kind == request.source_kind:
            spec += b"# tampered\n"
        for module, relative in contract.REQUIRED_MODULE_PATHS.items():
            target = request.source_root.joinpath(*relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(spec if module == "optimus.acp.spec" else f"# {module}\n".encode())
        request.launcher_path.parent.mkdir(parents=True, exist_ok=True)
        request.launcher_path.write_bytes(collector.render_launcher_bytes(request.source_root, request.closure_report_path))

    def locate_database(self, profile_root: Path) -> collector.DatabaseLocation:
        return collector.DatabaseLocation(main=profile_root / "db" / "0-stable" / "db.sqlite", wal=None, shm=None)

    def remove_tree(self, path: Path) -> None:
        if self.options.cleanup_fails:
            raise OSError("simulated cleanup failure")
        shutil.rmtree(path)

    # ------------------------------------------------------------------ launch emulation

    def launch(self, request: collector.LaunchRequest) -> collector.LaunchResult:
        key = (request.arm_id, request.launch_id)
        self.launches.append(key)
        if self.options.abort_at == key:
            raise collector.HostError("simulated_launch_failure")
        started = self.monotonic_ns()
        messages = self._script(request)
        self._write_relay(request.relay_dir, messages, request.child_argv)
        self._write_closure(request, started)
        self._update_database(request)
        ended = self.monotonic_ns()
        forced = self.options.forced_kill == key
        audit = {
            "event_type": "authorization", "final_reason_code": "AUTHORIZED", "approval_mode": "durable",
            "approval_migration_disposition": "none", "approval_id": request.approval.approval_id,
            "workspace_digest": request.approval.workspace_digest, "launch_session_id": request.launch_session_id,
        }
        return collector.LaunchResult(started, ended, 1 if forced else 0, forced, not self.options.unconfirmed_drain, audit)

    def _initialize_result(self, key: tuple[str, str]) -> dict[str, Any]:
        capabilities: dict[str, Any] = {"loadSession": True, "sessionCapabilities": {}}
        if self.options.advertise_resume == key:
            capabilities["sessionCapabilities"] = {"resume": {}}
        if self.options.deny_load_session == key:
            capabilities["loadSession"] = False
        return {"protocolVersion": 1, "agentCapabilities": capabilities, "authMethods": []}

    def _script(self, request: collector.LaunchRequest) -> list[tuple[str, dict[str, Any]]]:
        arm_id, launch_id = request.arm_id, request.launch_id
        key = (arm_id, launch_id)
        out: list[tuple[str, dict[str, Any]]] = [
            ("zed_to_agent", {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": 1}}),
            ("agent_to_zed", {"jsonrpc": "2.0", "id": 0, "result": self._initialize_result(key)}),
        ]

        def new_session(session_id: str) -> None:
            out.append(("zed_to_agent", {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": "C:\\w", "mcpServers": []}}))
            out.append(("agent_to_zed", {"jsonrpc": "2.0", "id": 1, "result": {"sessionId": session_id, "modes": {}}}))
            out.append(("agent_to_zed", {"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": session_id, "update": {"sessionUpdate": "available_commands_update", "availableCommands": []}}}))

        def update(session_id: str, kind: str, text: str | None = None) -> None:
            body: dict[str, Any] = {"sessionUpdate": kind}
            if text is not None:
                body["content"] = {"type": "text", "text": text}
            out.append(("agent_to_zed", {"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": session_id, "update": body}}))

        if arm_id == contract.ARM_PROMPTED:
            if launch_id == "lifecycle_a":
                new_session(PROMPTED_SESSION)
                out.append(("zed_to_agent", {"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": {"sessionId": PROMPTED_SESSION, "prompt": [{"type": "text", "text": "hi"}]}}))
                update(PROMPTED_SESSION, "agent_message_chunk", "hello")
                out.append(("agent_to_zed", {"jsonrpc": "2.0", "id": 2, "result": {"stopReason": "end_turn"}}))
            else:
                out.append(("zed_to_agent", {"jsonrpc": "2.0", "id": 1, "method": "session/load", "params": {"sessionId": PROMPTED_SESSION, "cwd": "C:\\w", "mcpServers": []}}))
                out.append(("agent_to_zed", {"jsonrpc": "2.0", "id": 1, "result": {}}))
            return out
        session_id = session_for(arm_id, launch_id)
        new_session(session_id)
        if launch_id == "first" and self.options.first_launch_load_arm == arm_id:
            out.append(("zed_to_agent", {"jsonrpc": "2.0", "id": 5, "method": "session/load", "params": {"sessionId": session_id}}))
            out.append(("agent_to_zed", {"jsonrpc": "2.0", "id": 5, "result": {}}))
        if launch_id == "first" and arm_id in contract.R_DESCRIPTOR_IDS:
            descriptor = {d.descriptor_id: d for d in request.fixture.descriptors}[arm_id]
            prompt = list(self.options.empty_prompt_shape) if self.options.empty_prompt_arm == arm_id else [{"type": "text", "text": "hi"}]
            out.append(("zed_to_agent", {"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": {"sessionId": session_id, "prompt": prompt}}))
            if descriptor.notice_text is not None:
                update(session_id, "agent_message_chunk", descriptor.notice_text + AGENT_MESSAGE_BLOCK_SEPARATOR)
            if self.options.extra_notice_arm == arm_id:
                update(session_id, "plan")
            if descriptor.wire_class == "result_stop_reason":
                out.append(("agent_to_zed", {"jsonrpc": "2.0", "id": 2, "result": {"stopReason": descriptor.stop_reason}}))
            else:
                out.append(("agent_to_zed", {"jsonrpc": "2.0", "id": 2, "error": contract.descriptor_response_body(descriptor)}))
        if launch_id == "reopen" and self.options.reopen_load_arm == arm_id:
            out.append(("zed_to_agent", {"jsonrpc": "2.0", "id": 9, "method": "session/load", "params": {"sessionId": session_for(arm_id, "first")}}))
            out.append(("agent_to_zed", {"jsonrpc": "2.0", "id": 9, "result": {}}))
        return out

    def _write_relay(self, relay_dir: Path, messages: list[tuple[str, dict[str, Any]]], child_argv: list[str]) -> None:
        recorder = relay._LockedRecorder(relay_dir, "relay", 0.0)
        try:
            for direction, message in messages:
                recorder.record_chunk(direction, json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n")
            recorder.record_eof(relay.DIR_ZED_TO_AGENT)
            recorder.record_eof(relay.DIR_AGENT_TO_ZED)
            totals = recorder.totals()
        finally:
            recorder.close()
        relay._write_summary(
            relay_dir,
            run_id="relay",
            child_argv=child_argv,
            child_exit_code=0,
            totals=totals,
            zed_eof=True,
            agent_eof=True,
            terminal_disposition="completed",
            reason_code=None,
        )

    def _write_closure(self, request: collector.LaunchRequest, started: int) -> None:
        entries = []
        for module, relative in sorted(contract.REQUIRED_MODULE_PATHS.items()):
            if module == self.options.omit_module:
                continue
            path = request.source_root.joinpath(*relative.split("/"))
            payload = path.read_bytes()
            entries.append({"module_name": module, "resolved_path": collector._canonical_text(str(path.resolve())), "source_relative_path": relative, "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
        report_ns = started - 5 if self.options.report_before_launch == (request.arm_id, request.launch_id) else started + 1
        report = {
            "schema": collector.MODULE_CLOSURE_SCHEMA,
            "pid": 4242,
            "monotonic_ns": report_ns,
            "entrypoint_module": contract.ENTRYPOINT_MODULE,
            "source_root": collector._canonical_text(str(request.source_root.resolve())),
            "entries": entries,
            "inspection_failures": [],
        }
        request.closure_report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")

    def _update_database(self, request: collector.LaunchRequest) -> None:
        location = self.locate_database(request.profile_root)
        location.main.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(location.main)
        try:
            connection.execute("CREATE TABLE IF NOT EXISTS sidebar_threads (thread_id BLOB PRIMARY KEY, session_id TEXT)")
            arm_id, launch_id = request.arm_id, request.launch_id
            thread = hashlib.sha256(arm_id.encode()).digest()[:16]
            binding: str | None = None
            if arm_id == contract.ARM_PROMPTED and launch_id == "lifecycle_a":
                binding = PROMPTED_SESSION
            if arm_id == contract.ARM_PROMPTED and launch_id == "lifecycle_b" and self.options.prompted_binding_retained:
                binding = PROMPTED_SESSION
            if launch_id == "first" and self.options.pre_reopen_binding_arm == arm_id:
                binding = session_for(arm_id, "first")
            connection.execute("INSERT OR REPLACE INTO sidebar_threads (thread_id, session_id) VALUES (?, ?)", (thread, binding))
            if launch_id in ("first", "lifecycle_a") and self.options.second_thread_bound_arm == arm_id:
                connection.execute("INSERT OR REPLACE INTO sidebar_threads (thread_id, session_id) VALUES (?, ?)", (b"\x02" * 16, session_for(arm_id, launch_id)))
            if self.options.second_thread_arm == arm_id:
                connection.execute("INSERT OR REPLACE INTO sidebar_threads (thread_id, session_id) VALUES (?, ?)", (b"\x01" * 16, None))
            connection.commit()
        finally:
            connection.close()
