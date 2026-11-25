"""Plan 12.14 Q launcher (Q-release gate G1b).

- G2, zero paid: `python -m tools.plan12_memory.m2b_launch --phase gate --config reports/plan12-memory-m2b/gate-config.json --output ...`
- Task 4, under its own release: `... --phase paid --config ... --release <release.json> --output ...`

Design: optimus-handoff/p1214-gate/gate-design.md, as revised after Fable 5.2's consult, with Codex round 124's changes (#548). One process
opens production memory sessions (session_factory, with only the embedder swapped for the shared content-keyed cache) over the paid cases'
five snapshots, each indexed to completion and its catalogue read for the published generation, in a fixed order. Every Q row goes through
production's own composition:

- the shipped registry's attachment for the D3 model (ordinary_attachment), its summarizer on a client that refuses every call (NoSummaries);
  B replaces only the pack budget with the legacy policy, F keeps the route's own; N is the attached turn with no memory turn (af44b9f);
- AttachedTurn.capture, the memory turn joined (B and F), then prepare(), in the adapter's order;
- production's RoutePolicy for the model's own implementer role, with Q's 2,048 output cap.

The rehearsal runs the whole schedule through the production client and the production HTTP Gateway server, whose real upstream client posts
to a loopback stub provider answering as the empirical route's first-attempt router. It records per row what the paid run must reproduce
(the pack digest through the runner's own workspace-context observer, the prefix digest and boundary, the input digest with the scope line's
index generation masked, the binding, the limit line) and the row's evidence (epoch, tree, retrieval). It fails on a row that is not settled
or an expected refusal, degraded or unrecorded retrieval, an epoch that is not the session's published one, a provider request whose cached
split is not the row's, a provider call the schedule did not send, any summary call, or a budget case whose rows are not the budget report's.

The paid launch verifies the release (head, clean tree, the contract's exact bytes and the gate it carries), loads the gate's artifacts from
their verified bytes, runs the preflight, repeats the preparation as a dry pass on the loopback Gateway, compares every row with the sealed
rehearsal and refuses before any send on a difference. Each row's Guard then holds that row's exact dry-pass input and prefix boundary.
Records hold digests and counts, never source or request text; request and answer texts go only to sinks outside the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field, replace
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Final

from optimus.acp.context_attachment import implementer_role, ordinary_attachment
from optimus.acp.conversation import ConversationSanitizer, build_conversation_sanitizer_inputs
from optimus.agent.index_turn import LIMIT_OBSERVATION
from optimus.config.gateway import OptimusGatewaySettings
from optimus.context.assembly import AttachedTurn, ContextAttachment
from optimus.context.context_budget import BudgetPolicy
from optimus.context.shipped_policy import attachment_limits
from optimus.gateway.client import GatewayClient
from optimus.gateway.route_binding import RoutePolicy
from optimus.runtime.modes import ExecutionMode
from optimus_gateway.model_policy import GatewayModelPolicy
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway
from optimus_model_policy import RegistrySnapshot
from optimus_model_policy.binding import MAX_ROUTE_ATTEMPTS, disclosure_key, trusted_snapshot
from optimus_model_policy.experimental import experimental_route
from tools.plan12_memory import m1_evaluate, m1_scale
from tools.plan12_memory import m2b_evaluate as ev
from tools.plan12_memory import m2b_paid as paid
from tools.plan12_memory import m2b_score as sc

D3_MODEL: Final = ev.D3_MODEL
PER_ATTEMPT_USD: Final = Decimal("0.04608")  # the D3 route's worst case per attempt at Q's caps (evaluation contract)
ATTEMPTS_MAX: Final = 96
USD_MAX: Final = Decimal("6.00")
FROZEN_COUNTS: Final = (36, 25, 11)  # rows, sends, forced refusals, with U = B and the outline (cases.json paid_q.expected_sends)
CONTRACT: Final = "reports/plan12-memory-m2b/evaluation-contract.json"
CASES: Final = "reports/plan12-memory-m2b/cases.json"
SCORER: Final = "tools/plan12_memory/m2b_score.py"  # G3 gives the scorer its own successor pin; every other file is the one G2 ran
# The files whose bytes the gate must pin; a gate that leaves one out is refused (Codex round 124 B1).
PINNED_FILES: Final = ("tools/plan12_memory/m2b_paid.py", "tools/plan12_memory/m2b_launch.py", "tools/plan12_memory/m2b_score.py",
                       "tools/plan12_memory/m2b_evaluate.py", CASES)
# The frozen schedule's worst case fits the frozen release: every send at MAX_ROUTE_ATTEMPTS attempts, each at the per-attempt bound.
assert FROZEN_COUNTS[1] * MAX_ROUTE_ATTEMPTS <= ATTEMPTS_MAX and FROZEN_COUNTS[1] * MAX_ROUTE_ATTEMPTS * PER_ATTEMPT_USD <= USD_MAX
SCOPE_LINE: Final = re.compile(r"^(--- scope: index generation )(\d+)")  # matched on the emitted scope line only, never the pack's text
EXPECTED_CHANNELS: Final = frozenset({"dense", "lexical", "memory", "recency", "structure"})
# What a row must keep from the rehearsal to the paid run. Never the exact input (its scope line names the generation), the epoch or the
# index revision: those are each run's own evidence.
SEALED: Final = ("sent", "terminal", "input_masked_sha256", "pack_sha256", "prefix_sha256", "cache_prefix_chars", "binding", "limit_line", "retrieval_evidence",
                  "tree")
EVIDENCE_FIELDS: Final = ("pack_sha256", "epoch", "tree", "retrieval_evidence", "degraded", "evidence_refusal")
RETRIEVED: Final = frozenset({"manifest", "retrieval, then a refusal before the manifest"})  # rows whose retrieval ran, so whose epoch must be the published one
REVIEW_COMMENT: Final = re.compile(r"https://github\.com/vibhanshu-agarwal/optimus-cost-agent/issues/548#issuecomment-\d+")
REHEARSAL_REPLY: Final = "Rehearsal answer from the stub provider; no provider was called."
INDEX_SECONDS: Final = 3_600
PROVIDER_KEY_NAMES: Final = ("OPENROUTER_API_KEY", "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY")
PLACEHOLDER_PROVIDER_KEY: Final = "rehearsal-no-provider"  # pragma: allowlist secret - the loopback stub needs no key


class LaunchRefused(Exception):
    """The launcher refused before anything was sent."""


def _sha(text: str) -> str:
    return "hex:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bytes_sha(data: bytes) -> str:
    return "hex:" + hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    return _bytes_sha(path.read_bytes())


def _masked_context(context: str) -> str:
    head, newline, line = context.rpartition("\n")
    return f"{head}{newline}{SCOPE_LINE.sub(r'\g<1><masked>', line)}"


def masked_sha(text: str, context: str | None) -> str | None:
    """The request's digest with only the emitted scope line's generation masked: the row's own workspace context is replaced by itself
    with its last line masked. None when that context is not in the request exactly once (Codex round 124 attempt 2, B2). An N row has no
    memory turn, so no scope line: its context is None and its digest is the request's own (its attached turn may also trim today's
    selection to fit, so that selection is not verbatim in the request)."""
    if context is None:
        return _sha(text)
    if text.count(context) != 1:
        return None
    return _sha(text.replace(context, _masked_context(context)))


def scope_generation(context: str) -> int | None:
    found = SCOPE_LINE.match(context.rpartition("\n")[2])
    return None if found is None else int(found.group(2))


def schedule_counts(cases: Sequence[Mapping[str, Any]], *, u_equals_b: bool, outline_available: bool) -> tuple[int, int, int]:
    rows = len(paid.schedule(cases, u_equals_b=u_equals_b))
    sends = sum(paid.expected_calls(cases, u_equals_b=u_equals_b, outline_available=outline_available).values())
    return rows, sends, rows - sends


def check_schedule(cases: Sequence[Mapping[str, Any]], *, u_equals_b: bool, outline_available: bool) -> None:
    counts = schedule_counts(cases, u_equals_b=u_equals_b, outline_available=outline_available)
    if counts != FROZEN_COUNTS:
        raise LaunchRefused(f"the schedule has {counts[0]} rows, {counts[1]} sends and {counts[2]} forced refusals, not the frozen {FROZEN_COUNTS}")


def checkout_tree(workspace: Path) -> str:
    return "git:" + _git(workspace, "rev-parse", "HEAD^{tree}")


def checkout_head(workspace: Path) -> str:
    return "git:" + _git(workspace, "rev-parse", "HEAD")


def checkout_drift(workspace: Path, head: str) -> str | None:
    """Why a row's checkout is not the one it was opened at: any tracked or untracked change, or another commit (Codex round 124 attempt 3,
    B2). A file outside the row's selected context counts too, since the request bytes alone would not show it. One git process: porcelain
    v2 gives the commit and every change."""
    lines = _git(workspace, "status", "--porcelain=v2", "--branch", "--untracked-files=all").splitlines()
    if any(not line.startswith("# ") for line in lines):
        return "the checkout has changed since it was opened"
    if f"# branch.oid {head.removeprefix('git:')}" not in lines:
        return "the checkout is not the commit it was opened at"
    return None


@dataclass
class Composition:
    """Production's Q composition for one process: each row's packer and binder are built fresh, as a launch builds them per turn."""

    snapshot: RegistrySnapshot
    shared_secret: str
    legacy: BudgetPolicy
    sessions: dict[str, Any]  # case snapshot -> its MemorySession
    workspaces: dict[str, Path]  # case snapshot -> its tree
    model_id: str = D3_MODEL
    epochs: dict[str, int] = field(default_factory=dict)  # case snapshot -> the generation its session published and its catalogue holds
    trees: dict[str, str] = field(default_factory=dict)  # case snapshot -> its frozen source tree (the revision's own), sealed per row
    heads: dict[str, str] = field(default_factory=dict)  # case snapshot -> its materialized checkout's commit, taken right after materializing
    verify_checkout: Callable[[Path, str], str | None] = checkout_drift
    summaries: paid.NoSummaries = field(default_factory=paid.NoSummaries)
    packers: dict[tuple[str, str], AttachedTurn] = field(default_factory=dict)  # each row's, read after it for its manifest

    def attachment(self, arm: str) -> ContextAttachment:
        attachment = ordinary_attachment(snapshot=self.snapshot, model_id=self.model_id, gateway_client=self.summaries, shared_secret=self.shared_secret)
        if attachment is None:
            raise LaunchRefused("the registry has no eligible summarizer, so a launch would attach nothing")
        if arm == "U":
            raise LaunchRefused("this release has U = B, so U is never run")
        return replace(attachment, pack_budget=self.legacy) if arm == "B" else attachment

    def packer(self, case: Mapping[str, Any], arm: str) -> AttachedTurn:
        attachment = self.attachment(arm)
        workspace = self.workspaces[case["snapshot"]]
        sanitizer = ConversationSanitizer(build_conversation_sanitizer_inputs({"OPTIMUS_API_KEY": self.shared_secret}, workspace_root=workspace), workspace=workspace)
        attached = AttachedTurn.capture(attachment=attachment, session_key=f"m2b-q-{case['case_id']}-{arm}", records={}, approvals={}, generation=0, sanitizer=sanitizer,
                                        strategy=attachment.initial_strategy, mode=ExecutionMode.CHAT, checkpoint=None, current_prompt=case["task"], turn_seq=1,
                                        cancelled=lambda: False)
        if arm != "N":
            attached.memory = self.memory_turn(case["snapshot"])
        outcome = attached.prepare()
        if outcome.kind != "view":
            raise LaunchRefused(f"{case['case_id']}/{arm}: the attached turn prepared {outcome.kind!r}, not its history view")
        self.packers[(case["case_id"], arm)] = attached
        return attached

    def checkout_drift(self, snapshot: str) -> str | None:
        return self.verify_checkout(self.workspaces[snapshot], self.heads[snapshot])

    def memory_turn(self, snapshot: str) -> Any:
        """The session's own turn, keeping the retrieval and pack production computed (`m2b_seen`), so a turn that refuses after retrieval and
        before its manifest still has its evidence (Codex round 124 attempt 2, A2)."""
        turn = self.sessions[snapshot].turn()
        retrieve = turn._retrieve  # noqa: SLF001

        def seen(*args: Any, **kwargs: Any) -> Any:
            turn.m2b_seen = retrieve(*args, **kwargs)
            return turn.m2b_seen

        turn._retrieve, turn.m2b_seen = seen, None  # noqa: SLF001
        return turn

    def binder(self, case: Mapping[str, Any], arm: str) -> Any:
        role = implementer_role(self.snapshot, self.model_id)
        policy = RoutePolicy(snapshot=self.snapshot, disclosure_key=disclosure_key(self.shared_secret), model_id=self.model_id, role=role.value, output_cap=paid.OUTPUT_CAP)
        return policy.capture(session_id=f"m2b-q-{case['case_id']}-{arm}", turn_seq=1, deliver_notice=lambda text: True)

    def approved(self) -> paid.Approved:
        return paid.Approved(self.snapshot.effective_hash, estimate_request=attachment_limits(self.snapshot, self.model_id).estimate_request, model_id=self.model_id)

    def workspace_for(self, case: Mapping[str, Any]) -> Path:
        return self.workspaces[case["snapshot"]]


# --- the loopback provider and the production HTTP Gateway in front of it (Codex round 124 A1) -------------------------------------

class StubProvider:
    """A loopback HTTP server in the provider's place: it answers OpenRouter's chat-completions shape as the empirical route's first-attempt
    router would. It keeps, per request, the digest of the text it received and where the cached block ended, never the text."""

    def __init__(self, snapshot: RegistrySnapshot) -> None:
        self.snapshot = snapshot
        self.calls: list[dict[str, Any]] = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server's name
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                reply = json.dumps(stub.answer(body)).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

            def log_message(self, *args: Any) -> None:  # the request line names no content, but nothing here is diagnostic either
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, name="m2b-stub-provider", daemon=True).start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/api/v1"

    def answer(self, body: Mapping[str, Any]) -> dict[str, Any]:
        content = body["messages"][0]["content"]
        blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
        text = "".join(block["text"] for block in blocks)
        marked = [index for index, block in enumerate(blocks) if "cache_control" in block]
        self.calls.append({"input_sha256": _sha(text), "cache_prefix_chars": len(blocks[0]["text"]) if marked == [0] and len(blocks) == 2 else None,
                           "marked_blocks": marked, "model": body["model"]})
        route = experimental_route(self.snapshot, body["model"])
        router = route.provider_name if route is not None and route.provider_name is not None else body["provider"]["only"][0]
        return {"id": f"gen-rehearsal-{len(self.calls)}", "model": body["model"], "choices": [{"message": {"content": REHEARSAL_REPLY}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0},
                "openrouter_metadata": {"attempt": 1, "pipeline": [], "endpoints": {"available": [{"provider": router, "model": body["model"], "selected": True}]}}}

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@contextmanager
def loopback_gateway(snapshot: RegistrySnapshot, shared_secret: str) -> Iterator[tuple[GatewayClient, StubProvider]]:
    """The production Gateway server (its HTTP handler, admission and real upstream client) with only its upstream URL on the stub, and the
    production client in front of it."""
    provider = StubProvider(snapshot)
    try:
        policy = GatewayModelPolicy.for_launch(snapshot=snapshot, approved_hash=snapshot.effective_hash, shared_secret=shared_secret)
        config = GatewayServiceConfig(bind_host="127.0.0.1", bind_port=0, shared_secret=shared_secret, provider="openrouter", provider_api_key=PLACEHOLDER_PROVIDER_KEY,
                                      base_url=provider.base_url, model_policy=policy)
        server = serve_gateway(config=config)
        threading.Thread(target=server.serve_forever, name="m2b-loopback-gateway", daemon=True).start()
        try:
            yield GatewayClient(settings=OptimusGatewaySettings(gateway_url=f"http://127.0.0.1:{server.server_address[1]}", optimus_api_key=shared_secret)), provider
        finally:
            server.shutdown()
            server.server_close()
    finally:
        provider.close()


# --- per-row evidence and the rehearsal ------------------------------------------------------------------------------------------

def degraded(manifest: Mapping[str, Any]) -> list[str]:
    """Why a row's retrieval is not the full one (Fable gate consult; Codex round 124 A2): a state other than ok, incomplete coverage, a
    channel missing or not giving a results list (memory's "no authorized source" is a Q turn's normal report), a catalogue not yet read,
    or stale evidence held back."""
    retrieval = manifest.get("retrieval") or {}
    found = [] if retrieval.get("state") == "ok" else [f"retrieval state {retrieval.get('state')!r}"]
    if not (retrieval.get("coverage") or {}).get("complete"):
        found.append("index coverage incomplete")
    channels = retrieval.get("channels") or {}
    found.extend(f"channel {name} missing" for name in sorted(EXPECTED_CHANNELS - set(channels)))
    for name, outcome in sorted(channels.items()):
        if name == "catalogue":
            found.append("catalogue not ready")
        elif not (re.fullmatch(r"\d+ results", str(outcome)) or (name == "memory" and outcome == "no authorized source")):
            found.append(f"channel {name}: {outcome}")
    if manifest.get("stale_paths"):
        found.append(f"{len(manifest['stale_paths'])} stale files held back")
    return found


class Evidence:
    """What the runner showed each row: the request text (this process's memory only), its workspace context, and what its memory turn
    retrieved (generation, retrieval and degradation, kept even when the turn refuses before its manifest), with the snapshot's tree id.
    Called by the paid runner before each row is written.

    With `expected` (the dry pass's rows, at paid time), the workspace-context observer, which runs before the request is built, refuses a
    row whose pack, scope-line generation or source tree is not the dry pass's (Codex round 124 attempt 2, B2)."""

    def __init__(self, composition: Composition, cases: Sequence[Mapping[str, Any]], expected: Sequence[Mapping[str, Any]] | None = None) -> None:
        self.composition = composition
        self.snapshot_of = {case["case_id"]: case["snapshot"] for case in cases}
        self.run_snapshot = {f"m2b-q-{case['case_id']}-{arm}": case["snapshot"] for case in cases for arm in "NBUF"}
        self.expected = None if expected is None else {f"m2b-q-{r['case_id']}-{r['arm']}": r for r in expected}
        self.inputs: dict[str, str] = {}
        self.contexts: dict[str, str] = {}
        self.refusals: dict[str, str] = {}

    def keep(self, sha: str, text: str) -> None:
        self.inputs[sha] = text

    def observe(self, request: Any, result: Any) -> None:
        """Runs before the row's request is built: the checkout must still be the tree it was opened at, and at paid time the row must be
        the dry row; otherwise the row is refused before anything is sent."""
        self.contexts[request.run_id] = result.text
        want = None if self.expected is None else self.expected.get(request.run_id)
        snapshot = self.run_snapshot.get(request.run_id)
        reason = None if snapshot is None else self.composition.checkout_drift(snapshot)
        if reason is None and want is not None and want["sent"]:
            reason = self._differs(want, result.text)
        if reason is not None:
            self.refusals[request.run_id] = reason
            raise paid.GuardRefused(reason)

    def _differs(self, want: Mapping[str, Any], context: str) -> str | None:
        if self.composition.trees.get(self.snapshot_of[want["case_id"]]) != want["tree"]:
            return "the source tree is not the dry pass's"
        if want["arm"] != "N" and _sha(context.rpartition("\n")[0]) != want["pack_sha256"]:
            return "the pack is not the dry pass's"
        if want["arm"] != "N" and scope_generation(context) != want["epoch"]:
            return "the scope line's generation is not the dry pass's"
        return None

    def __call__(self, case: Mapping[str, Any], arm: str, row: Mapping[str, Any]) -> dict[str, Any]:
        memory = self.composition.packers[(case["case_id"], arm)].memory
        manifest = None if memory is None else memory.manifest
        seen = None if memory is None else getattr(memory, "m2b_seen", None)
        context = self.contexts.get(row["logical_request_id"])
        epoch, found = None, []
        if memory is None:
            evidence = "no memory turn"
        elif seen is None:
            evidence = "none: the turn stopped before retrieval"
        else:
            retrieval, pack = seen
            view = {"retrieval": {"state": retrieval.state, "coverage": dict(retrieval.coverage), "channels": dict(retrieval.channels)},
                    "stale_paths": [] if pack is None else list(pack.stale_paths)}
            evidence = "manifest" if manifest else "retrieval, then a refusal before the manifest"
            epoch, found = retrieval.epoch, degraded(view)
        return {"pack_sha256": _sha(context.rpartition("\n")[0]) if row["sent"] and memory is not None and context is not None else None,  # minus its scope line
                "epoch": epoch, "tree": self.composition.trees.get(case["snapshot"]), "retrieval_evidence": evidence, "degraded": found,
                "evidence_refusal": self.refusals.get(row["logical_request_id"])}


def _budget_problems(rows: Mapping[tuple[str, str], Mapping[str, Any]], budget_report: Mapping[str, Any]) -> list[str]:
    """Item 8, every budget/outline case and both arms against the budget report (Codex round 124 A5): a complete pack is sent with exactly
    the measured bytes; an incomplete one is the row's expected refusal with nothing sent."""
    measured = {r["case_id"]: r for r in budget_report["rows"]}
    problems = [f"{case_id}: not in the budget report" for case_id in ev.BUDGET_CASES if case_id not in measured]
    for case_id in (c for c in ev.BUDGET_CASES if c in measured):
        for arm, key in (("B", "BU"), ("F", "F")):
            row, arm_report = rows.get((case_id, arm)), measured[case_id]["arms"][key]
            if row is None:
                problems.append(f"{case_id}/{arm}: no row")
            elif arm_report["complete"] and not (row["sent"] and row["pack_sha256"] == arm_report["pack_sha256"]):
                problems.append(f"{case_id}/{arm}: the pack is not the budget report's")
            elif not arm_report["complete"] and (row["sent"] or row["terminal"] != "expected_zero_call"):
                problems.append(f"{case_id}/{arm}: the budget report measured no complete pack, but the row is {row['terminal']}")
    return problems


def rehearse(cases: Sequence[Mapping[str, Any]], composition: Composition, *, gateway: Any, provider: StubProvider, u_equals_b: bool, outline_available: bool,
             budget_report: Mapping[str, Any] | None, release: str = "rehearsal") -> dict[str, Any]:
    """The whole schedule through the paid runner against the stub provider, and per row what the paid run must reproduce."""
    evidence = Evidence(composition, cases)
    approved = composition.approved()
    before = len(provider.calls)
    report = paid.run(cases, u_equals_b=u_equals_b, outline_available=outline_available, gateway=gateway, approved=approved, model=composition.model_id,
                      packer_for=composition.packer, binder_for=composition.binder, workspace_for=composition.workspace_for,
                      ceiling=paid.Ceiling(attempts_max=ATTEMPTS_MAX, usd_max=USD_MAX, per_attempt_usd=PER_ATTEMPT_USD), write=lambda _r: None,
                      write_answers=lambda _a: None, release=release, write_input=evidence.keep, observe_context=evidence.observe, row_evidence=evidence)
    received = {call["input_sha256"]: call for call in provider.calls[before:]}
    snapshot_of = {case["case_id"]: case["snapshot"] for case in cases}
    rows: list[dict[str, Any]] = []
    problems: list[str] = [] if report["stopped"] is None else [f"stopped at {report['stopped']['at']}: {report['stopped']['reason']}"]
    for row in report["rows"]:
        name = f"{row['case_id']}/{row['arm']}"
        missing = [key for key in EVIDENCE_FIELDS if key not in row]
        if missing:
            problems.append(f"{name}: the row carries no launcher evidence ({', '.join(missing)})")
            continue
        entry = row["sent"][0] if row["sent"] else None
        text = None if entry is None else evidence.inputs.get(entry["input_sha256"])
        record = {"case_id": row["case_id"], "arm": row["arm"], "position": row["position"], "terminal": row["terminal"], "sent": entry is not None,
                  "input_sha256": None if entry is None else entry["input_sha256"], "input_masked_sha256": None if text is None else masked_sha(text, None if row["arm"] == "N" else evidence.contexts.get(row["logical_request_id"])),
                  "pack_sha256": row["pack_sha256"], "prefix_sha256": None if entry is None else entry["prefix_sha256"],
                  "cache_prefix_chars": None if entry is None else entry["cache_prefix_chars"],
                  # what the Guard checked before forwarding: it refuses any other model, hash or cap
                  "binding": None if entry is None else {"registry_hash": approved.registry_hash, "model": approved.model_id, "output_cap": approved.output_cap},
                  "limit_line": None if text is None else LIMIT_OBSERVATION in text,
                  "epoch": row["epoch"], "tree": row["tree"], "retrieval_evidence": row["retrieval_evidence"], "degraded": row["degraded"]}
        rows.append(record)
        if text is not None and record["input_masked_sha256"] is None:
            problems.append(f"{name}: the row's workspace context is not in its request exactly once")
        if row["terminal"] not in {"settled", "expected_zero_call"}:
            problems.append(f"{name}: {row['terminal']} ({row['terminal_reason']})")
        if record["sent"] and record["limit_line"] is not (row["arm"] != "N"):
            problems.append(f"{name}: the limit line is {'present' if record['limit_line'] else 'absent'}")
        problems.extend(f"{name}: {reason}" for reason in record["degraded"])
        published = composition.epochs.get(snapshot_of[row["case_id"]])
        if record["retrieval_evidence"] in RETRIEVED and (published is None or record["epoch"] != published):
            problems.append(f"{name}: retrieval read generation {record['epoch']}, the session published {published}")
        if entry is not None:
            upstream = received.get(entry["input_sha256"])
            if upstream is None:
                problems.append(f"{name}: the provider never received this request")
            elif upstream["cache_prefix_chars"] != entry["cache_prefix_chars"]:
                problems.append(f"{name}: the provider's cached block ends at {upstream['cache_prefix_chars']}, the binding at {entry['cache_prefix_chars']}")
    sends = sum(1 for r in rows if r["sent"])  # a row sending other than its expected count is already incomplete above
    if len(provider.calls) - before != sends:
        problems.append(f"{len(provider.calls) - before} provider calls for {sends} sends")
    if composition.summaries.calls:
        problems.append(f"{composition.summaries.calls} summary calls; a Q row never summarizes")
    if budget_report is not None:
        problems.extend(_budget_problems({(r["case_id"], r["arm"]): r for r in rows}, budget_report))
    return {"schema": "plan12-memory-m2b.rehearsal.v2", "release": release, "u_equals_b": u_equals_b, "outline_available": outline_available, "rows": rows, "sends": sends,
            "provider_calls": len(provider.calls) - before, "summary_calls": composition.summaries.calls, "problems": problems, "passes": not problems}


def compare(sealed: Mapping[str, Any], dry: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """Each sent row's exact input and prefix boundary from the dry pass, only if every row matches the sealed rehearsal; otherwise nothing
    is sent."""
    if not sealed.get("passes"):
        raise LaunchRefused("the sealed rehearsal did not pass")
    if not dry["passes"]:
        raise LaunchRefused("the dry pass did not pass: " + "; ".join(dry["problems"]))
    want = {(r["case_id"], r["arm"]): r for r in sealed["rows"]}
    got = {(r["case_id"], r["arm"]): r for r in dry["rows"]}
    if list(want) != list(got):
        raise LaunchRefused("the dry pass ran another schedule than the sealed rehearsal")
    differences = [f"{key[0]}/{key[1]} {name}" for key, row in want.items() for name in SEALED if got[key].get(name) != row.get(name)]
    if differences:
        raise LaunchRefused("the dry pass differs from the sealed rehearsal: " + "; ".join(differences))
    return {key: {"input_sha256": row["input_sha256"], "cache_prefix_chars": row["cache_prefix_chars"]} for key, row in got.items() if row["sent"]}


# --- the release, the gate and the preflight (Codex round 124 B1) --------------------------------------------------------------

def _git(repository: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repository), *args], capture_output=True, text=True, check=True).stdout.strip()


def verify_release(repository: Path, release: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The operator's release names the head, the contract's exact bytes and both review comments; the checkout must be that head, clean,
    and the contract must carry the gate (`q_launch`). Returns the contract and its gate."""
    if _git(repository, "rev-parse", "HEAD") != release.get("head"):
        raise LaunchRefused("the checkout is not the released head")
    if _git(repository, "status", "--porcelain", "--untracked-files=no"):
        raise LaunchRefused("the checkout has uncommitted changes")
    data = (repository / CONTRACT).read_bytes()
    if _bytes_sha(data) != release.get("contract_sha256"):
        raise LaunchRefused("the contract is not the released bytes")
    reviews = release.get("reviews")
    named = [reviews.get(name) for name in ("fable", "codex")] if isinstance(reviews, Mapping) else []
    if len(named) != 2 or not all(isinstance(url, str) and REVIEW_COMMENT.fullmatch(url) for url in named) or named[0] == named[1]:
        raise LaunchRefused("the release does not name both review comments (two distinct #548 comment links)")
    contract = json.loads(data)
    gate = contract.get("q_launch")
    if not isinstance(gate, dict):
        raise LaunchRefused("the contract carries no q_launch gate")
    return contract, gate


def load_artifact(repository: Path, spec: Mapping[str, Any]) -> Any:
    """A gate artifact read from its verified bytes."""
    data = (repository / spec["path"]).read_bytes()
    if _bytes_sha(data) != spec["sha256"]:
        raise LaunchRefused(f"{spec['path']} is not the gate's bytes")
    return json.loads(data)


def tariff_record() -> dict[str, str]:
    tariff = paid.D3_TARIFF
    return {"id": tariff.id, "input_usd_per_million": str(tariff.input_usd_per_million), "output_usd_per_million": str(tariff.output_usd_per_million)}


def verify_g2(g2: Mapping[str, Any], gate: Mapping[str, Any]) -> None:
    """The sealed G2 report must have passed and have run exactly the gate's runner, launcher, evaluator, cases and composition; only the
    scorer may have its G3 successor pin (Codex round 124 attempt 2, B1)."""
    problems = [] if g2.get("passes") is True else ["the G2 report did not pass"]
    pinned, digests = g2.get("pinned") or {}, gate.get("digests") or {}
    problems.extend(f"the G2 report ran another {rel}" for rel in PINNED_FILES if rel != SCORER and pinned.get(rel) != digests.get(rel))
    if (g2.get("registry_hash"), g2.get("tariff_id"), g2.get("cases_sha256")) != (gate.get("registry_hash"), (gate.get("tariff") or {}).get("id"), sc.SEALED_CASES_SHA256):
        problems.append("the G2 report ran another composition or cases")
    if problems:
        raise LaunchRefused("G2: " + "; ".join(problems))


def preflight(cases: Sequence[Mapping[str, Any]], *, u_equals_b: bool, outline_available: bool, budget_report: Mapping[str, Any], gate: Mapping[str, Any],
              snapshot: RegistrySnapshot, repository: Path) -> paid.Ceiling:
    """Items 3 and 12: the frozen schedule, the frozen release bounds (never the caller's), every pinned file and the composition the
    gate's, and the outline available exactly when the budget report, re-gated here, says so. Returns the release's ceiling."""
    problems: list[str] = []
    try:
        check_schedule(cases, u_equals_b=u_equals_b, outline_available=outline_available)
    except LaunchRefused as refused:
        problems.append(str(refused))
    rows, sends, refusals = schedule_counts(cases, u_equals_b=u_equals_b, outline_available=outline_available)
    if (gate.get("rows"), gate.get("sends"), gate.get("forced_refusals")) != (rows, sends, refusals):
        problems.append("the gate's schedule counts are not the cases'")
    if (gate.get("attempts_max"), str(gate.get("usd_max")), str(gate.get("per_attempt_usd"))) != (ATTEMPTS_MAX, str(USD_MAX), str(PER_ATTEMPT_USD)):
        problems.append("the gate's release bounds are not the frozen 96 attempts, USD 6.00 and USD 0.04608 an attempt")
    digests = gate.get("digests") or {}
    problems.extend(f"the gate does not pin {rel}" for rel in PINNED_FILES if rel not in digests)
    problems.extend(f"{rel} is not the gate's" for rel, digest in sorted(digests.items()) if not (repository / rel).is_file() or _file_sha(repository / rel) != digest)
    if snapshot.effective_hash != gate.get("registry_hash"):
        problems.append("the registry is not the gate's")
    if gate.get("tariff") != tariff_record():
        problems.append("the tariff is not the gate's")
    if budget_report.get("outline_available") is not outline_available:
        problems.append("the outline's availability is not the budget report's")
    if not ev.budget_gates(budget_report.get("rows") or [], outline_available=outline_available)["passes"]:
        problems.append("the budget report does not pass its gates")
    if problems:
        raise LaunchRefused("preflight: " + "; ".join(problems))
    return paid.Ceiling(attempts_max=ATTEMPTS_MAX, usd_max=USD_MAX, per_attempt_usd=PER_ATTEMPT_USD)


def paid_launch(cases: Sequence[Mapping[str, Any]], composition: Composition, *, gateway: Any, sealed: Mapping[str, Any], budget_report: Mapping[str, Any],
                gate: Mapping[str, Any], u_equals_b: bool, outline_available: bool, repository: Path, write: Callable[[Mapping[str, Any]], None],
                write_answers: Callable[[Mapping[str, Any]], None], write_input: Callable[[str, str], None]) -> dict[str, Any]:
    """Task 4: the preflight, the dry pass on the loopback Gateway, the comparison, then the paid rows, each Guard holding its row's exact
    dry-pass input and prefix boundary, each row keeping its own evidence. Any refusal happens before the first paid send."""
    ceiling = preflight(cases, u_equals_b=u_equals_b, outline_available=outline_available, budget_report=budget_report, gate=gate, snapshot=composition.snapshot,
                        repository=repository)
    with loopback_gateway(composition.snapshot, composition.shared_secret) as (client, provider):
        dry = rehearse(cases, composition, gateway=client, provider=provider, u_equals_b=u_equals_b, outline_available=outline_available, budget_report=budget_report,
                       release="dry")
    expected = compare(sealed, dry)
    composition.packers.clear()
    evidence = Evidence(composition, cases, expected=[row for row in dry["rows"] if row["sent"]])
    return paid.run(cases, u_equals_b=u_equals_b, outline_available=outline_available, gateway=gateway, approved=composition.approved(), model=composition.model_id,
                    packer_for=composition.packer, binder_for=composition.binder, workspace_for=composition.workspace_for, ceiling=ceiling, write=write,
                    write_answers=write_answers, write_input=write_input, expected_inputs=expected, observe_context=evidence.observe, row_evidence=evidence)


# --- the drivers: G2 (zero paid) and Task 4 (paid, under its own release) ------------------------------------------------------

def wait_indexed(session: Any, seconds: float = INDEX_SECONDS) -> int:
    """A complete pass on the session's own worker, then its catalogue held for the generation the index publishes now, so no row sees
    `catalogue not ready` or another generation's suggestions (Codex round 124 A2). A worker that is refused or stops says why."""
    deadline = time.monotonic() + seconds
    while True:
        outcome = session._last_outcome  # noqa: SLF001 - as m1_scale and the session tests wait
        if outcome is not None and outcome.state == "complete":
            break
        if outcome is not None and outcome.state == "refused":
            raise LaunchRefused(f"the index worker was refused ({outcome.detail or 'no detail'}): {session.status()}")
        if session._unusable is not None or time.monotonic() > deadline:  # noqa: SLF001
            raise LaunchRefused(f"no complete index pass ({'none yet' if outcome is None else outcome.state}): {session.status()}")
        time.sleep(1)
    scope = session._current_scope()  # noqa: SLF001
    epoch = scope.storage.call("coverage")["current"]["epoch"]
    while session._catalogue_for(scope, epoch, True) is None:  # noqa: SLF001 - asks for it, then holds it for this generation
        if not session.wait_for_catalogue(max(0.1, deadline - time.monotonic())) or time.monotonic() > deadline:
            raise LaunchRefused(f"the catalogue for generation {epoch} was not read: {session.status()}")
        time.sleep(0.1)
    return int(epoch)


def open_sessions(revisions: Sequence[str], *, repository: Path, work: Path, root: Path, memory: Any, settings: Any, settings_file: Mapping[str, Any], embedder: Any,
                  composition: Composition, trees: list[dict[str, Any]]) -> None:
    """Production's session for each snapshot, in the given order, each indexed to completion before the next starts. Each is registered
    in the composition as soon as it opens, so a later failure still closes it."""
    from optimus.context.memory_session import session_factory

    factory = session_factory(memory_root=root, config_root=work / "config", settings=settings, config=memory, artifact_directory=settings_file["embedding"]["artifact_directory"])
    for snapshot in revisions:
        revision = snapshot.removeprefix("git:")
        tree = work / "trees" / revision[:12]
        m1_evaluate.materialize(repository, revision, tree, branch=f"q-{revision[:12]}")
        # The frozen source tree is the row's sealed identity (gate design); the archive-made checkout's own tree can differ (an export-ignored
        # file), so it is bound to by its commit, taken before anything else touches it (Codex round 124 attempt 4).
        composition.trees[snapshot], composition.heads[snapshot] = "git:" + _git(repository, "rev-parse", f"{revision}^{{tree}}"), checkout_head(tree)
        session = factory(tree)
        if session is None:
            raise LaunchRefused(f"{revision[:12]}: the workspace could not be registered")
        session._embedder_for = lambda: embedder  # noqa: SLF001 - the one swap: the shared content-keyed embedding cache (Fable gate consult)
        composition.sessions[snapshot], composition.workspaces[snapshot] = session, tree
        started = time.perf_counter()
        session.start()
        composition.epochs[snapshot] = wait_indexed(session)
        coverage = session._current_scope().storage.call("coverage")["current"]["coverage"]  # noqa: SLF001
        trees.append({"revision": snapshot, "tree": composition.trees[snapshot], "checkout_head": composition.heads[snapshot], "checkout_tree": checkout_tree(tree),
                      "epoch": composition.epochs[snapshot], "seconds": round(time.perf_counter() - started, 1), "coverage": coverage})


def smoke(cases: Sequence[Mapping[str, Any]], composition: Composition, snapshot: str, *, gateway: Any, provider: StubProvider) -> dict[str, Any]:
    """One F row on the first indexed snapshot, through the whole path, before the other snapshots are indexed (Codex round 124 A3)."""
    case = next(c for c in sorted(cases, key=lambda c: c["case_id"]) if c["snapshot"] == snapshot and not c["forced_refusal"]["F"])
    evidence = Evidence(composition, cases)
    before = len(provider.calls)
    row = paid.run_one(case, "F", position=0, gateway=gateway, approved=composition.approved(), model=composition.model_id, packer=composition.packer(case, "F"),
                       binder=composition.binder(case, "F"), workspace=composition.workspace_for(case),
                       ceiling=paid.Ceiling(attempts_max=ATTEMPTS_MAX, usd_max=USD_MAX, per_attempt_usd=PER_ATTEMPT_USD), allowance=1, release="smoke",
                       write_input=evidence.keep, observe_context=evidence.observe)
    seen = evidence(case, "F", row)
    problems = [f"{name}: {value}" for name, value in (("guard refusal", row["guard_refusal"]), ("error", row["error"]), ("stop", row["stop_reason"])) if value]
    problems += row["reconciliation"]["problems"] + seen["degraded"]
    if row["logical_requests"] != 1 or len(provider.calls) - before != 1:
        problems.append(f"{row['logical_requests']} sends and {len(provider.calls) - before} provider calls, not one each")
    composition.packers.clear()
    return {"case_id": case["case_id"], "arm": "F", "epoch": seen["epoch"], "problems": problems, "passes": not problems}


def _embedder(config: Mapping[str, Any], repository: Path, root: Path, memory: Any, settings_file: Mapping[str, Any]) -> Any:
    return m1_evaluate.CachedEmbedder(ev.FastembedEmbedder(root, memory.embedding, directory=settings_file["embedding"]["artifact_directory"], threads=config["embedding_threads"]),
                                      ev.embedding_cache(config, repository))


def _released_names(config: Mapping[str, Any]) -> None:
    """m1_scale._provision's own check, made before anything can be created or removed."""
    prefix = config.get("release_prefix", "p1210-")
    if not (config["container"].startswith(prefix) and config["volume"].startswith(prefix)):
        raise LaunchRefused("only the released container and volume")


def _remove_container(config: Mapping[str, Any]) -> None:
    """Remove the released container and volume, then confirm both are gone."""
    container, volume = config["container"], config["volume"]
    subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)
    subprocess.run(["docker", "volume", "rm", "-f", volume], capture_output=True, check=False)
    for kind, command in (("container", ["docker", "ps", "-a", "-q", "--filter", f"name=^{container}$"]), ("volume", ["docker", "volume", "ls", "-q", "--filter", f"name=^{volume}$"])):
        listed = subprocess.run(command, capture_output=True, text=True, check=False)
        if listed.returncode != 0:
            raise LaunchRefused(f"teardown could not confirm the released {kind} is gone")
        if listed.stdout.strip():
            raise LaunchRefused(f"teardown left the released {kind} behind")


def _close_sessions(composition: Composition) -> None:
    """Every session closes even if one fails to; once all have been tried, one refusal names each that failed, by snapshot, with its
    error's type (Codex round 124 attempt 4)."""
    failed: list[str] = []
    for snapshot, session in composition.sessions.items():
        try:
            session.close()
        except Exception as failure:  # noqa: BLE001 - kept, and reported once every session has been asked to close
            failed.append(f"{snapshot.removeprefix('git:')[:12]} ({type(failure).__name__})")
    if failed:
        raise LaunchRefused(f"sessions did not close: {', '.join(failed)}")


@contextmanager
def provisioned(config: Mapping[str, Any], repository: Path, work: Path, composition: Composition) -> Iterator[tuple[Path, Any, Any, Mapping[str, Any], Any]]:
    """The released Redis and index Gateway. Each resource's cleanup is registered where it is acquired and every one runs however this
    ends, a failed start or a failed cleanup included (Codex round 124 attempts 2 and 3, A3): the sessions close, then the index Gateway
    and its client stop (registered by _provision the moment each exists), then the container and volume are removed and confirmed gone."""
    _released_names(config)
    with ExitStack() as stack:
        stack.callback(_remove_container, config)  # first in, last out: _provision may create the container and then fail
        root, memory, _password, _client, _gateway, settings, settings_file = m1_scale._provision(dict(config), repository, work, cleanup=stack)  # noqa: SLF001
        stack.callback(_close_sessions, composition)
        yield root, memory, settings, settings_file, _embedder(config, repository, root, memory, settings_file)


def _sealed_cases(repository: Path, config: Mapping[str, Any]) -> list[dict[str, Any]]:
    data = (repository / config["cases"]).read_bytes()
    if _bytes_sha(data) != sc.SEALED_CASES_SHA256:
        raise LaunchRefused("the cases are not the sealed bytes")
    return json.loads(data)["paid_q"]["cases"]


def _no_provider_key() -> None:
    present = [name for name in PROVIDER_KEY_NAMES if os.environ.get(name)]
    if present:
        raise LaunchRefused(f"a provider key is in the environment: {', '.join(present)}")


def run_gate(config: Mapping[str, Any], repository: Path, out: Path) -> dict[str, Any]:
    """G2 in one container lifecycle, stopping at the first failed stage with its report kept: the schedule checked before anything starts;
    the first snapshot indexed and one F row smoked; the other four indexed; the budget pass with the outline on the main snapshot's own
    session and its gates; then the rehearsal of every row."""
    _no_provider_key()
    contract = json.loads((repository / CONTRACT).read_text(encoding="utf-8"))
    u_equals_b = contract["task1_freezes"]["selected_candidate"]["u_equals_b"]
    cases = _sealed_cases(repository, config)
    check_schedule(cases, u_equals_b=u_equals_b, outline_available=True)
    head = _git(repository, "rev-parse", "HEAD")
    work = repository / config["work_dir"] / "gate"
    legacy, model_aware, _estimate = ev.production_routes(work)
    report: dict[str, Any] = {"schema": "plan12-memory-m2b.gate-g2.v2", "head": f"git:{head}", "label": config["label"], "cases_sha256": sc.SEALED_CASES_SHA256,
                              "pinned": {rel: _file_sha(repository / rel) for rel in PINNED_FILES}, "registry_hash": trusted_snapshot().effective_hash,
                              "tariff_id": paid.D3_TARIFF.id, "counts": dict(zip(("rows", "sends", "forced_refusals"), FROZEN_COUNTS, strict=True)),
                              "rehearsal_gateway": "the production HTTP Gateway server and client; its real upstream client posts to a loopback stub provider",
                              "trees": [], "passes": False}
    composition = Composition(trusted_snapshot(), secrets.token_hex(32), legacy, {}, {})
    revisions = sorted({case["snapshot"] for case in cases})  # the fixed order; the paid run repeats it
    try:
        with provisioned(config, repository, work, composition) as (root, memory, settings, settings_file, embedder), \
                loopback_gateway(composition.snapshot, composition.shared_secret) as (client, provider):
            index = {"repository": repository, "work": work, "root": root, "memory": memory, "settings": settings, "settings_file": settings_file, "embedder": embedder,
                     "composition": composition, "trees": report["trees"]}
            open_sessions(revisions[:1], **index)
            report["smoke"] = smoke(cases, composition, revisions[0], gateway=client, provider=provider)
            if not report["smoke"]["passes"]:
                return report
            open_sessions(revisions[1:], **index)
            main = next(case["snapshot"] for case in cases if case["category"] == "budget")
            rows = ev._budget_cases(config, repository, work, settings, embedder, {"paid_q": {"cases": cases}}, report["trees"], legacy=legacy.ceiling,  # noqa: SLF001
                                    model_aware=model_aware, outline=True, turn=composition.sessions[main].turn())
            report["budget"] = {"outline_available": True, "budget": {"legacy": legacy.ceiling, "C": model_aware.ceiling, "T": model_aware.target}, "rows": rows,
                                "budget_gates": ev.budget_gates(rows, outline_available=True)}
            if not report["budget"]["budget_gates"]["passes"]:
                return report
            report["rehearsal"] = rehearse(cases, composition, gateway=client, provider=provider, u_equals_b=u_equals_b, outline_available=True,
                                           budget_report=report["budget"])
            report["embedding"] = {"embedded": embedder.embedded, "reused": embedder.reused}
            passed = report["rehearsal"]["passes"]
        report["passes"] = passed  # only once every resource is torn down and confirmed gone
        return report
    except Exception as failure:
        report["failures"] = failures(failure)  # a failed teardown and the failure it followed, both kept
        report["failed"] = report["failures"][0]
        raise
    finally:
        ev._write(report, out)  # noqa: SLF001


def failures(failure: BaseException) -> list[str]:
    """The failure and every one it followed, newest first: our refusals by their text, any other error by its type only (its text may hold
    a path)."""
    chain: list[str] = []
    current: BaseException | None = failure
    while current is not None and len(chain) < 8:
        chain.append(str(current) if isinstance(current, LaunchRefused) else type(current).__name__)
        current = current.__cause__ or current.__context__
    return chain


def _sink(path: Path, repository: Path) -> Path:
    """Request and answer texts go only outside the repository (item 15)."""
    resolved = path.resolve()
    if resolved == repository.resolve() or repository.resolve() in resolved.parents:
        raise LaunchRefused("the text sinks must be outside the repository")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def input_sink(directory: Path) -> Callable[[str, str], None]:
    """Each forwarded request's text, appended before the send to the sink outside the repository, keyed by its digest (item 15)."""

    def write_input(sha: str, text: str) -> None:
        with (directory / "inputs.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({"input_sha256": sha, "text": text}, ensure_ascii=True) + "\n")

    return write_input


def run_paid(config: Mapping[str, Any], repository: Path, release: Mapping[str, Any], out: Path) -> dict[str, Any]:
    """Task 4 under the operator's release: the release and gate verified, the gate's artifacts loaded from their verified bytes, the same
    sessions in the same order, then paid_launch against the operator-started Gateway."""
    contract, gate = verify_release(repository, release)
    _no_provider_key()
    settings = OptimusGatewaySettings.from_env(os.environ)  # the operator-started Gateway
    if (gate.get("digests") or {}).get(CASES) != sc.SEALED_CASES_SHA256:
        raise LaunchRefused("the gate does not pin the sealed cases")
    cases = load_artifact(repository, {"path": CASES, "sha256": sc.SEALED_CASES_SHA256})["paid_q"]["cases"]  # the one file the preflight checks
    g2 = load_artifact(repository, gate["g2_report"])
    verify_g2(g2, gate)
    u_equals_b = contract["task1_freezes"]["selected_candidate"]["u_equals_b"]
    budget_report = g2["budget"]
    preflight(cases, u_equals_b=u_equals_b, outline_available=budget_report["outline_available"], budget_report=budget_report, gate=gate, snapshot=trusted_snapshot(),
              repository=repository)  # before anything is provisioned or indexed (Codex round 124 attempt 3, B1); paid_launch repeats it
    sink = _sink(Path(config["sink_dir"]), repository)
    work = repository / config["work_dir"] / "paid"
    legacy, _model_aware, _estimate = ev.production_routes(work)
    composition = Composition(trusted_snapshot(), settings.optimus_api_key.get_secret_value(), legacy, {}, {})
    revisions = sorted({case["snapshot"] for case in cases})

    with provisioned(config, repository, work, composition) as (root, memory, index_settings, settings_file, embedder):
        open_sessions(revisions, repository=repository, work=work, root=root, memory=memory, settings=index_settings, settings_file=settings_file, embedder=embedder,
                      composition=composition, trees=[])
        return paid_launch(cases, composition, gateway=GatewayClient(settings=settings), sealed=g2["rehearsal"], budget_report=budget_report, gate=gate,
                           u_equals_b=u_equals_b, outline_available=budget_report["outline_available"], repository=repository, write=paid.write_json(out),
                           write_answers=paid.write_json(sink / "answers.json"), write_input=input_sink(sink))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phase", required=True, choices=("gate", "paid"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--release", type=Path, help="the operator's release (head, contract_sha256, reviews); required for --phase paid")
    args = parser.parse_args(argv)
    repository = Path.cwd()
    config = json.loads((repository / args.config).read_text(encoding="utf-8"))
    if args.phase == "paid":
        if args.release is None:
            raise LaunchRefused("the paid phase needs the operator's release")
        report = run_paid(config, repository, json.loads(args.release.read_text(encoding="utf-8")), repository / args.output)
        print(json.dumps({"stopped": report["stopped"], "rows": len(report["rows"])}))
        return 0 if report["stopped"] is None else 1
    report = run_gate(config, repository, repository / args.output)
    print(json.dumps({"passes": report["passes"], "smoke": (report.get("smoke") or {}).get("passes"), "budget": ((report.get("budget") or {}).get("budget_gates") or {}).get("passes"),
                      "rehearsal": (report.get("rehearsal") or {}).get("passes")}))
    return 0 if report["passes"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
