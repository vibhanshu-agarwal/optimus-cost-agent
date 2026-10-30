"""Plan 12.7 P5: version-bound ACP/Zed capability observations, with a synthetic stub agent.

Two parts, both stdlib-only at import so the stub runs as a plain script under Zed:

* `stub-agent`: a minimal ACP agent Zed launches over stdio. It answers initialize/session/new/prompt,
  sends a pre-prompt message and a host-style tool-call card (P5-b, P5-c reference peer), reads the
  synthetic buffer through `fs/read_text_file` only when the client advertises it (P5-a), and logs
  what it saw as JSON Lines. It holds no model and makes no network call. Its evidence is client-only:
  it says what Zed does, never what Optimus can emit.
* `run_zed` (the `--kind zed` body): records versions, merges the stub log and the operator-visible GUI
  observations, and scans the inspectable Zed sinks for the synthetic canaries (P5-d).

    <python> tools/plan12_memory/client_probe.py stub-agent --log FILE --canary-seed SEED --buffer FILE
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = 1
_MAX_SCAN_BYTES = 512 * 1024 * 1024
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


def canaries(seed: str) -> dict[str, str]:
    digest = hashlib.sha256(f"plan12.7-p5:{seed}".encode()).hexdigest()
    return {sink: f"P127C-{digest[:12]}-{sink}" for sink in ("message", "card")}


class StubAgent:
    """Pure request handling: each incoming message yields the messages to send and log rows to append."""

    def __init__(self, seed: str, buffer_path: str) -> None:
        self.canary = canaries(seed)
        self.buffer_path = buffer_path
        self.client_capabilities: dict[str, Any] = {}
        self.pending: dict[int, str] = {}
        self.next_id = 1000
        self.prompts = 0

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.next_id += 1
        self.pending[self.next_id] = method
        return {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params}

    @staticmethod
    def _update(session: str, update: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": session, "update": update}}

    def _text(self, session: str, text: str) -> dict[str, Any]:
        return self._update(session, {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}})

    def _card(self, session: str, number: int) -> dict[str, Any]:
        return self._update(session, {"sessionUpdate": "tool_call", "toolCallId": f"memory/p127-{number}",
                                      "title": f"Remembered (synthetic) {self.canary['card']}", "kind": "other",
                                      "status": "completed"})

    def handle(self, message: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        method, ident, params = message.get("method"), message.get("id"), message.get("params") or {}
        if method is None and ident in self.pending:
            asked = self.pending.pop(ident)
            content = (message.get("result") or {}).get("content")
            if asked == "fs/read_text_file" and isinstance(content, str):
                disk = Path(self.buffer_path).read_bytes() if Path(self.buffer_path).exists() else b""
                row = {"event": "fs_read_result", "client_sha256": hashlib.sha256(content.encode()).hexdigest(),
                       "disk_sha256": hashlib.sha256(disk).hexdigest()}
                row["matches_disk"] = row["client_sha256"] == row["disk_sha256"]
                return [], [row]
            return [], [{"event": "client_response", "method": asked, "error": message.get("error")}]
        if method == "initialize":
            self.client_capabilities = dict(params.get("clientCapabilities") or {})
            reply = {"jsonrpc": "2.0", "id": ident, "result": {"protocolVersion": PROTOCOL_VERSION,
                                                                 "agentCapabilities": {"loadSession": False},
                                                                 "authMethods": []}}
            return [reply], [{"event": "initialize", "protocolVersion": params.get("protocolVersion"),
                              "clientCapabilities": self.client_capabilities,
                              "clientInfo": params.get("clientInfo")}]
        if method == "session/new":
            session = f"p127-{int(time.time() * 1000)}"
            out = [{"jsonrpc": "2.0", "id": ident, "result": {"sessionId": session}},
                   self._text(session, f"Welcome back (synthetic pre-prompt brief) {self.canary['message']}"),
                   self._card(session, 0)]
            return out, [{"event": "session_new", "pre_prompt_updates_sent": 2}]
        if method == "session/prompt":
            session = str(params.get("sessionId", ""))
            self.prompts += 1
            out: list[dict[str, Any]] = []
            advertised = bool((self.client_capabilities.get("fs") or {}).get("readTextFile"))
            if advertised:
                out.append(self._request("fs/read_text_file", {"sessionId": session, "path": self.buffer_path}))
            out += [self._text(session, f"Synthetic reply {self.prompts}; fs.readTextFile advertised: {advertised}."),
                    self._card(session, self.prompts),
                    {"jsonrpc": "2.0", "id": ident, "result": {"stopReason": "end_turn"}}]
            return out, [{"event": "prompt", "fs_read_requested": advertised}]
        if method == "session/cancel" or ident is None:
            return [], [{"event": "notification", "method": method}]
        return ([{"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "method not found"}}],
                [{"event": "unsupported", "method": method}])


def serve(agent: StubAgent, log: Path, stdin: Any = None, stdout: Any = None) -> None:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as journal:
        for line in stdin:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                journal.write(json.dumps({"event": "malformed_input"}, ensure_ascii=True) + "\n")
                continue
            outgoing, rows = agent.handle(message)
            for row in rows:
                journal.write(json.dumps({"t": time.time(), **row}, ensure_ascii=True) + "\n")
            journal.flush()
            for item in outgoing:
                stdout.write(json.dumps(item, ensure_ascii=True) + "\n")
            stdout.flush()


def _text_hits(data: bytes, needles: Mapping[str, str]) -> set[str]:
    return {name for name, value in needles.items()
            if value.encode("utf-8") in data or value.encode("utf-16-le") in data}


def _sqlite_hits(path: Path, needles: Mapping[str, str]) -> tuple[set[str], list[str]]:
    """Read every text/blob cell; decompress zstd cells with the 3.14 stdlib. Undecodable cells are reported, not ignored."""
    from compression import zstd

    hits, opaque = set(), []
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as db:
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            for row in db.execute(f'SELECT * FROM "{table}"'):  # noqa: S608 - names come from sqlite_master
                for cell in row:
                    data = cell.encode("utf-8") if isinstance(cell, str) else cell if isinstance(cell, bytes) else b""
                    if data.startswith(_ZSTD_MAGIC):
                        try:
                            data = zstd.decompress(data)
                        except zstd.ZstdError:
                            opaque.append(f"{path.name}:{table}")
                            continue
                    hits |= _text_hits(data, needles)
    return hits, sorted(set(opaque))


def scan_sinks(roots: list[Path], needles: Mapping[str, str]) -> dict[str, Any]:
    """Which canaries persist where. A sink that cannot be read makes the confidentiality verdict INCONCLUSIVE."""
    found: dict[str, list[str]] = {name: [] for name in needles}
    unreadable, opaque, scanned, budget = [], [], 0, _MAX_SCAN_BYTES
    for root in roots:
        if not root.exists():
            unreadable.append(f"{root.as_posix()} (absent)")
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            try:
                size = path.stat().st_size
                if size > budget:
                    unreadable.append(f"{path.as_posix()} (scan budget exhausted)")
                    continue
                budget -= size
                data = path.read_bytes()
                hits = _text_hits(data, needles)
                if data.startswith(b"SQLite format 3"):
                    sql_hits, sql_opaque = _sqlite_hits(path, needles)
                    hits |= sql_hits
                    opaque += sql_opaque
                elif data.startswith(_ZSTD_MAGIC):
                    opaque.append(path.as_posix())
                scanned += 1
                for name in hits:
                    found[name].append(path.as_posix())
            except (OSError, sqlite3.Error) as error:
                unreadable.append(f"{path.as_posix()} ({type(error).__name__})")
    return {"files_scanned": scanned, "found": found, "unreadable": unreadable, "opaque": opaque}


_PHASES = ("visible_history", "close_reopen", "restart")


def _shot(entry: Any) -> bool:
    return isinstance(entry, dict) and isinstance(entry.get("screenshot_sha256"), str) and bool(
        re.fullmatch(r"[0-9a-f]{64}", entry["screenshot_sha256"]))


def _observed(entry: Any, key: str) -> bool | None:
    """A GUI observation counts only with its boolean and the hash of the screenshot it was read from."""
    return entry[key] if _shot(entry) and isinstance(entry.get(key), bool) else None


def run_zed(context: Any, result: Any, runner: Callable[..., Any] | None = None) -> None:
    """P5. The stub log and the canary sink scan are machine evidence; GUI observations need a screenshot hash.

    `gui_observations` JSON: {"P5-a": {"buffer_dirty": bool}, "P5-b": {"pre_prompt_text_visible": bool,
    "screenshot_sha256": hex}, "P5-c": {"reference_card_rendered": bool, "screenshot_sha256": hex},
    "P5-d": {"phases": {phase: {"canary_visible": bool, "screenshot_sha256": hex}} for visible_history,
    close_reopen and restart}. Anything missing or malformed leaves its row UNRUN or INCONCLUSIVE.
    """
    from tools.plan12_memory.probes import run_command

    runner = runner or run_command
    section = context.config.sections.get("zed") or {}
    if not section.get("canary_seed"):
        result.outcome, result.disposition = "UNRUN", "open"
        result.limitations.append("no released zed section with a canary seed")
        return
    needles = canaries(section["canary_seed"])
    context.ram_only.update(needles.values())
    versions = {}
    for name, argv in (("zed", [section.get("zed_cli", "zed"), "--version"]), ("acpx", [section.get("acpx", "acpx"), "--version"])):
        try:
            completed = runner(argv, context.timeout(60), None)
            versions[name] = " ".join(completed.stdout.split()[:3]) if completed.returncode == 0 else "UNKNOWN"
        except OSError as error:
            versions[name] = f"unavailable: {type(error).__name__}"
    stub_log = Path(section.get("stub_log", "tmp/plan12-probe-zed/stub-observations.jsonl"))
    rows = [json.loads(line) for line in stub_log.read_text(encoding="utf-8").splitlines() if line.strip()] if stub_log.exists() else []
    gui_path = Path(section.get("gui_observations", ""))
    gui = json.loads(gui_path.read_text(encoding="utf-8")) if gui_path.is_file() else {}
    init = next((row for row in rows if row.get("event") == "initialize"), None)
    reads = [row for row in rows if row.get("event") == "fs_read_result"]
    advertised = bool(((init or {}).get("clientCapabilities") or {}).get("fs", {}).get("readTextFile")) if init else None
    pre_prompt_sent = any(row.get("event") == "session_new" for row in rows)
    p5: dict[str, Any] = {}
    p5["P5-a"] = {"status": ("UNRUN" if init is None else "UNSUPPORTED" if not advertised else
                             "PASS" if any(not row["matches_disk"] for row in reads) else
                             "FAIL" if reads and (gui.get("P5-a") or {}).get("buffer_dirty") is True else "INCONCLUSIVE"),
                  "fs_readTextFile_advertised": advertised, "reads": reads,
                  "scope": "client-only: real Zed serving a synthetic unsaved buffer to the stub agent"}
    visible = _observed(gui.get("P5-b"), "pre_prompt_text_visible")
    p5["P5-b"] = {"status": "UNRUN" if not pre_prompt_sent or visible is None else "PASS" if visible else "UNSUPPORTED",
                  "pre_prompt_updates_sent": pre_prompt_sent, "gui": gui.get("P5-b"),
                  "fallback": "first-response brief when unsolicited display is unsupported",
                  "scope": "client-only: whether Zed renders an update sent before the first prompt"}
    card = _observed(gui.get("P5-c"), "reference_card_rendered")
    p5["P5-c"] = {"status": "UNRUN",
                  "optimus_path": {"status": "UNRUN", "owner": "M3", "reason": "Optimus has no host-generated card path "
                                   "without a model turn; no ad-hoc save mechanism is added here"},
                  "provider_calls": "not established: no Optimus or Gateway process ran for P5-c",
                  "reference_peer": {"status": "UNRUN" if not pre_prompt_sent or card is None else "PASS" if card else "FAIL",
                                     "gui": gui.get("P5-c"), "scope": "client-only control: Zed rendering a stub card"}}
    sinks = scan_sinks([Path(root) for root in section.get("sink_roots", [])], needles)
    persisted = {name: paths for name, paths in sinks["found"].items() if paths}
    phases = (gui.get("P5-d") or {}).get("phases") or {}
    seen = {phase: _observed(phases.get(phase), "canary_visible") for phase in _PHASES}
    complete = bool(section.get("sink_roots")) and sinks["files_scanned"] > 0 and not sinks["unreadable"] and not sinks["opaque"]
    p5["P5-d"] = {"status": ("UNRUN" if not rows else
                             "FAIL" if persisted or seen["close_reopen"] or seen["restart"] else
                             "UNSUPPORTED" if seen["visible_history"] is False else  # never displayed: nothing to qualify
                             "INCONCLUSIVE" if not complete or None in seen.values() else "PASS"),
                  "canaries_persisted_in": persisted, "phases": seen,
                  "sink_scan": {key: value for key, value in sinks.items() if key != "found"},
                  "canary_sha256": {name: hashlib.sha256(value.encode()).hexdigest() for name, value in needles.items()},
                  "scope": "only the inspected sinks; a PASS is a candidate for M3 qualification, never a confidentiality proof",
                  "consequence": "without an accepted M3 qualification, M3 uses the restricted-file fallback (spec 6.1.1) "
                                 "or keeps encryption/rotation unavailable"}
    result.observations.update({"versions": versions, "stub_events": len(rows), "P5": p5})
    statuses = [row["status"] for row in p5.values()]
    result.outcome = ("UNRUN" if all(s == "UNRUN" for s in statuses) else "FAIL" if "FAIL" in statuses else
                      "INCONCLUSIVE" if any(s in {"UNRUN", "INCONCLUSIVE"} for s in statuses) else "PASS")
    result.disposition = "handoff" if any(s in {"UNRUN", "INCONCLUSIVE"} for s in statuses) else "concluded"
    result.limitations.append("stub-agent evidence is client-only; it proves nothing about Optimus integration (M1/M3)")
    result.follow_up = "M1 owns buffer integration; M3 owns brief/notice binding, the Optimus card path and the phrase channel"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Plan 12.7 synthetic ACP stub agent")
    sub = parser.add_subparsers(dest="mode", required=True)
    stub = sub.add_parser("stub-agent")
    stub.add_argument("--log", required=True, type=Path)
    stub.add_argument("--canary-seed", required=True)
    stub.add_argument("--buffer", required=True)
    args = parser.parse_args(argv)
    serve(StubAgent(args.canary_seed, args.buffer), args.log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
