"""Plan 12.14 Q launcher (Q-release gate G1b): `python -m tools.plan12_memory.m2b_launch --config reports/plan12-memory-m2b/run-config.json --output ...`.

Design: optimus-handoff/p1214-gate/gate-design.md, as revised after Fable 5.2's consult (#548). One process opens production memory sessions
(session_factory, with only the embedder swapped for the shared content-keyed cache) over the paid cases' five snapshots, indexed in a fixed
order, and drives every Q row through production's own composition:

- the shipped registry's attachment for the D3 model (ordinary_attachment), its summarizer on a client that refuses every call (NoSummaries);
  B replaces only the pack budget with the legacy policy, F keeps the route's own; N is the attached turn with no memory turn (af44b9f);
- AttachedTurn.capture, the memory turn joined (B and F), then prepare(), in the adapter's order;
- production's RoutePolicy for the model's own implementer role, with Q's 2,048 output cap.

The rehearsal (G2: zero paid; no provider key may be in the environment) runs the whole schedule against the real Gateway handler in process
over a scripted provider, and records per sent row the fields that must be the same at paid time: the pack digest (through the runner's own
workspace-context observer), the prefix digest and `cache_prefix_chars`, the input digest with its index generation masked (the epoch is a
global counter, so it differs on every fresh build), the binding and whether the limit line is present. It checks the send count, zero
summary calls, no degraded retrieval and, for B and F, that the eight budget/outline packs are the budget report's (item 8).

The paid launch (Task 4, under its own release) refuses unless the preflight holds, then repeats the same preparation as a dry pass against
the scripted provider, compares every row with the sealed rehearsal, refuses before any send on a difference, and gives each row's Guard that
row's exact dry-pass input: the Guard forwards nothing else (item 14). Records hold digests and counts, never source or request text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

from optimus.acp.context_attachment import implementer_role, ordinary_attachment
from optimus.acp.conversation import ConversationSanitizer, build_conversation_sanitizer_inputs
from optimus.agent.index_turn import LIMIT_OBSERVATION
from optimus.config.gateway import OptimusGatewaySettings
from optimus.context.assembly import AttachedTurn, ContextAttachment
from optimus.context.context_budget import BudgetPolicy
from optimus.context.shipped_policy import attachment_limits
from optimus.gateway.client import (
    GatewayClient,
    GatewayRequest,
    _route_attempts_dropped,
    _try_parse_error_correlation,
    _try_parse_error_usage,
)
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.route_binding import RoutePolicy
from optimus.runtime.modes import ExecutionMode
from optimus_gateway.model_policy import GatewayModelPolicy
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.responses import handle_responses_request
from optimus_gateway.upstream_client import ProviderMessageResult
from optimus_model_policy import RegistrySnapshot
from optimus_model_policy.binding import MAX_ROUTE_ATTEMPTS, disclosure_key, trusted_snapshot
from optimus_model_policy.experimental import experimental_route
from tools.plan12_memory import m1_evaluate, m1_scale
from tools.plan12_memory import m2b_evaluate as ev
from tools.plan12_memory import m2b_paid as paid

D3_MODEL: Final = ev.D3_MODEL
PER_ATTEMPT_USD: Final = Decimal("0.04608")  # the D3 route's worst case per attempt at Q's caps (evaluation contract)
GENERATION: Final = re.compile(r"index generation \d+")
# What a sent row must keep from the rehearsal to the paid run. Never the exact input: its scope line names the index generation.
SEALED: Final = ("sent", "terminal", "input_masked_sha256", "pack_sha256", "prefix_sha256", "cache_prefix_chars", "binding", "limit_line")
REHEARSAL_REPLY: Final = "Rehearsal answer from the scripted provider; no provider was called."
INDEX_SECONDS: Final = 3_600


class LaunchRefused(Exception):
    """The launcher refused before anything was sent."""


def _sha(text: str) -> str:
    return "hex:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def masked_sha(text: str) -> str:
    return _sha(GENERATION.sub("index generation <masked>", text))


@dataclass
class Composition:
    """Production's Q composition for one process: each row's packer and binder are built fresh, as a launch builds them per turn."""

    snapshot: RegistrySnapshot
    shared_secret: str
    legacy: BudgetPolicy
    sessions: Mapping[str, Any]  # case snapshot -> its MemorySession
    workspaces: Mapping[str, Path]  # case snapshot -> its tree
    model_id: str = D3_MODEL
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
            attached.memory = self.sessions[case["snapshot"]].turn()
        outcome = attached.prepare()
        if outcome.kind != "view":
            raise LaunchRefused(f"{case['case_id']}/{arm}: the attached turn prepared {outcome.kind!r}, not its history view")
        self.packers[(case["case_id"], arm)] = attached
        return attached

    def binder(self, case: Mapping[str, Any], arm: str) -> Any:
        role = implementer_role(self.snapshot, self.model_id)
        policy = RoutePolicy(snapshot=self.snapshot, disclosure_key=disclosure_key(self.shared_secret), model_id=self.model_id, role=role.value, output_cap=paid.OUTPUT_CAP)
        return policy.capture(session_id=f"m2b-q-{case['case_id']}-{arm}", turn_seq=1, deliver_notice=lambda text: True)

    def approved(self) -> paid.Approved:
        return paid.Approved(self.snapshot.effective_hash, estimate_request=attachment_limits(self.snapshot, self.model_id).estimate_request, model_id=self.model_id)

    def workspace_for(self, case: Mapping[str, Any]) -> Path:
        return self.workspaces[case["snapshot"]]


class ScriptedProvider:
    """The rehearsal's and dry pass's provider behind the real Gateway handler: one fixed reply, no network. It answers as the route's own
    first-attempt router would (the D3 route is empirical, so the Gateway checks the resolved provider, attempt and pipeline)."""

    def __init__(self, snapshot: RegistrySnapshot) -> None:
        self.snapshot = snapshot
        self.calls = 0

    def create_message_once(self, *, model: str, input_text: str, max_tokens: int, provider_controls: Any, reasoning: Any, **_cache: Any) -> ProviderMessageResult:
        self.calls += 1
        return ProviderMessageResult(message_id=f"rehearsal-{self.calls}", output_text=REHEARSAL_REPLY, input_tokens=1, output_tokens=1, total_tokens=2, billing_units=2,
                                     cost_usd=Decimal(0), provider="openrouter", resolved_provider=self._router_name(model, provider_controls), requested_model=model, resolved_model=model,
                                     model_version=None, cache_hit=False, finish_reason="stop", router_attempt=1, router_pipeline=())

    def _router_name(self, model: str, provider_controls: Mapping[str, Any]) -> str:
        route = experimental_route(self.snapshot, model)
        return route.provider_name if route is not None and route.provider_name is not None else provider_controls["only"][0]


class LocalGateway:
    """A GatewayTransport handing each request to the real Gateway handler, its errors turned into the urllib transport's GatewayHttpError."""

    def __init__(self, snapshot: RegistrySnapshot, shared_secret: str, provider: ScriptedProvider) -> None:
        policy = GatewayModelPolicy.for_launch(snapshot=snapshot, approved_hash=snapshot.effective_hash, shared_secret=shared_secret)
        self.config = GatewayServiceConfig(bind_host="127.0.0.1", bind_port=0, shared_secret=shared_secret, provider="openrouter", provider_api_key="rehearsal-no-provider",  # pragma: allowlist secret - a placeholder; the provider is scripted
                                           base_url="http://127.0.0.1:9/api/v1", model_policy=policy)
        self.provider = provider
        self.refusals: list[tuple[int, str]] = []  # each refused reply's status and body, kept so a failed rehearsal says why

    def post_json(self, request: GatewayRequest) -> dict[str, Any]:
        status, body = handle_responses_request(authorization_header=request.headers.get("Authorization"), request_body=request.payload, config=self.config,
                                                upstream_client=self.provider)
        detail = json.dumps(body, default=str)
        if status != 200:
            self.refusals.append((status, detail))
            code, retryable, attempts = _try_parse_error_correlation(detail)
            raise GatewayHttpError(status, detail, gateway_usage=_try_parse_error_usage(detail), gateway_code=code, retryable=retryable, route_attempts=attempts,
                                   route_attempts_malformed=_route_attempts_dropped(detail, attempts))
        return json.loads(detail, parse_float=Decimal)


def local_client(snapshot: RegistrySnapshot, shared_secret: str, provider: ScriptedProvider) -> GatewayClient:
    return GatewayClient(settings=OptimusGatewaySettings(optimus_api_key=shared_secret), transport=LocalGateway(snapshot, shared_secret, provider))


def degraded(manifest: Mapping[str, Any]) -> list[str]:
    """Why a sent row's retrieval is not the full one (Fable gate consult): an incomplete index, a catalogue not yet read, a channel that
    gave no results list, or a state other than ok. Memory has no authorized source in a Q turn, which is its normal report."""
    retrieval = manifest.get("retrieval") or {}
    found = [] if retrieval.get("state") == "ok" else [f"retrieval state {retrieval.get('state')!r}"]
    if not (retrieval.get("coverage") or {}).get("complete"):
        found.append("index coverage incomplete")
    for name, outcome in sorted((retrieval.get("channels") or {}).items()):
        if name == "catalogue":
            found.append("catalogue not ready")
        elif not (re.fullmatch(r"\d+ results", str(outcome)) or (name == "memory" and outcome == "no authorized source")):
            found.append(f"channel {name}: {outcome}")
    return found


def rehearse(cases: Sequence[Mapping[str, Any]], composition: Composition, *, gateway: Any, provider: ScriptedProvider, u_equals_b: bool, outline_available: bool,
             budget_report: Mapping[str, Any] | None, release: str = "rehearsal", ceiling: paid.Ceiling | None = None) -> dict[str, Any]:
    """The whole schedule through the paid runner against the scripted provider, and per row what the paid run must reproduce."""
    inputs: dict[str, str] = {}  # this process's memory only: the record keeps digests
    contexts: dict[str, str] = {}
    approved = composition.approved()
    ceiling = ceiling or paid.Ceiling(attempts_max=96, usd_max=Decimal("6.00"), per_attempt_usd=PER_ATTEMPT_USD)
    report = paid.run(cases, u_equals_b=u_equals_b, outline_available=outline_available, gateway=gateway, approved=approved, model=composition.model_id,
                      packer_for=composition.packer, binder_for=composition.binder, workspace_for=composition.workspace_for, ceiling=ceiling, write=lambda _r: None,
                      write_answers=lambda _a: None, release=release, write_input=inputs.__setitem__,
                      observe_context=lambda request, result: contexts.__setitem__(request.run_id, result.text))
    rows: list[dict[str, Any]] = []
    problems: list[str] = [] if report["stopped"] is None else [f"stopped at {report['stopped']['at']}: {report['stopped']['reason']}"]
    for row in report["rows"]:
        entry = row["sent"][0] if row["sent"] else None
        text = None if entry is None else inputs.get(entry["input_sha256"])
        context = contexts.get(row["logical_request_id"])
        memory = composition.packers[(row["case_id"], row["arm"])].memory
        record = {"case_id": row["case_id"], "arm": row["arm"], "position": row["position"], "terminal": row["terminal"], "sent": entry is not None,
                  "input_sha256": None if entry is None else entry["input_sha256"], "input_masked_sha256": None if text is None else masked_sha(text),
                  "pack_sha256": None if entry is None or memory is None or context is None else _sha(context.rpartition("\n")[0]),  # minus its coverage line
                  "prefix_sha256": None if entry is None else entry["prefix_sha256"], "cache_prefix_chars": None if entry is None else entry["cache_prefix_chars"],
                  # what the Guard checked before forwarding: it refuses any other model, hash or cap
                  "binding": None if entry is None else {"registry_hash": approved.registry_hash, "model": approved.model_id, "output_cap": approved.output_cap},
                  "limit_line": None if text is None else LIMIT_OBSERVATION in text,
                  "degraded": [] if entry is None or memory is None else degraded(memory.manifest)}
        rows.append(record)
        name = f"{row['case_id']}/{row['arm']}"
        if row["terminal"] not in {"settled", "expected_zero_call"}:
            problems.append(f"{name}: {row['terminal']} ({row['terminal_reason']})")
        if record["sent"] and record["limit_line"] is not (row["arm"] != "N"):
            problems.append(f"{name}: the limit line is {'present' if record['limit_line'] else 'absent'}")
        problems.extend(f"{name}: {reason}" for reason in record["degraded"])
    sends = sum(1 for r in rows if r["sent"])  # a row sending other than its expected count is already incomplete above
    if provider.calls != sends:
        problems.append(f"{provider.calls} provider calls for {sends} sends")
    if composition.summaries.calls:
        problems.append(f"{composition.summaries.calls} summary calls; a Q row never summarizes")
    if budget_report is not None:  # item 8: the rows send the packs the budget pass measured
        measured = {r["case_id"]: r for r in budget_report["rows"]}
        for r in rows:
            if r["sent"] and r["arm"] in {"B", "F"} and r["case_id"] in measured:
                want = measured[r["case_id"]]["arms"]["BU" if r["arm"] == "B" else "F"]["pack_sha256"]
                if r["pack_sha256"] != want:
                    problems.append(f"{r['case_id']}/{r['arm']}: the pack is not the budget report's")
    return {"schema": "plan12-memory-m2b.rehearsal.v1", "release": release, "u_equals_b": u_equals_b, "outline_available": outline_available, "rows": rows, "sends": sends,
            "provider_calls": provider.calls, "summary_calls": composition.summaries.calls, "problems": problems, "passes": not problems}


def compare(sealed: Mapping[str, Any], dry: Mapping[str, Any]) -> dict[tuple[str, str], str]:
    """Each sent row's exact input from the dry pass, only if every row matches the sealed rehearsal; otherwise nothing is sent."""
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
    return {key: row["input_sha256"] for key, row in got.items() if row["sent"]}


def _file_sha(path: Path) -> str:
    return "hex:" + hashlib.sha256(path.read_bytes()).hexdigest()


def preflight(cases: Sequence[Mapping[str, Any]], *, u_equals_b: bool, outline_available: bool, budget_report: Mapping[str, Any], ceiling: paid.Ceiling,
              gate: Mapping[str, Any], snapshot: RegistrySnapshot, repository: Path) -> int:
    """Items 3 and 12: the worst case of every send fits the release, the sealed files and composition are the gate's, and the outline is
    available exactly when the sealed, passing budget report says so. Returns the send count."""
    sends = sum(paid.expected_calls(cases, u_equals_b=u_equals_b, outline_available=outline_available).values())
    problems = []
    if sends != gate["sends"]:
        problems.append(f"{sends} sends, the gate has {gate['sends']}")
    if sends * MAX_ROUTE_ATTEMPTS > ceiling.attempts_max or sends * MAX_ROUTE_ATTEMPTS * ceiling.per_attempt_usd > ceiling.usd_max:
        problems.append(f"{sends} sends at {MAX_ROUTE_ATTEMPTS} attempts each do not fit {ceiling.attempts_max} attempts and USD {ceiling.usd_max}")
    if not (budget_report.get("budget_gates") or {}).get("passes"):
        problems.append("the budget report does not pass")
    if budget_report.get("outline_available") is not outline_available:
        problems.append("the outline's availability is not the budget report's")
    problems.extend(f"{rel} is not the gate's" for rel, digest in sorted(gate["digests"].items()) if _file_sha(repository / rel) != digest)
    if snapshot.effective_hash != gate["registry_hash"]:
        problems.append("the registry is not the gate's")
    if paid.D3_TARIFF.id != gate["tariff_id"]:
        problems.append("the tariff is not the gate's")
    if problems:
        raise LaunchRefused("preflight: " + "; ".join(problems))
    return sends


def paid_launch(cases: Sequence[Mapping[str, Any]], composition: Composition, *, gateway: Any, sealed: Mapping[str, Any], budget_report: Mapping[str, Any],
                gate: Mapping[str, Any], ceiling: paid.Ceiling, u_equals_b: bool, outline_available: bool, repository: Path,
                write: Callable[[Mapping[str, Any]], None], write_answers: Callable[[Mapping[str, Any]], None], write_input: Callable[[str, str], None]) -> dict[str, Any]:
    """Task 4, under its own release: preflight, the dry pass against the scripted provider, the comparison, then the paid rows, each
    Guard holding its row's exact dry-pass input. Any refusal happens before the first paid send."""
    preflight(cases, u_equals_b=u_equals_b, outline_available=outline_available, budget_report=budget_report, ceiling=ceiling, gate=gate, snapshot=composition.snapshot,
              repository=repository)
    provider = ScriptedProvider(composition.snapshot)
    dry = rehearse(cases, composition, gateway=local_client(composition.snapshot, composition.shared_secret, provider), provider=provider, u_equals_b=u_equals_b,
                   outline_available=outline_available, budget_report=budget_report, release="dry")
    expected = compare(sealed, dry)
    composition.packers.clear()
    return paid.run(cases, u_equals_b=u_equals_b, outline_available=outline_available, gateway=gateway, approved=composition.approved(), model=composition.model_id,
                    packer_for=composition.packer, binder_for=composition.binder, workspace_for=composition.workspace_for, ceiling=ceiling, write=write,
                    write_answers=write_answers, write_input=write_input, expected_inputs=expected)


# --- G2: the one driver that needs a release (Docker, the index Redis, the embedding artifact); no paid call is possible ------------------

PROVIDER_KEY_NAMES: Final = ("OPENROUTER_API_KEY", "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY")


def wait_indexed(session: Any, seconds: float = INDEX_SECONDS) -> None:
    """A complete pass on the session's own worker, then its catalogue read, so no row sees `catalogue not ready` (item 8)."""
    deadline = time.monotonic() + seconds
    while session._last_outcome is None or session._last_outcome.state != "complete":  # noqa: SLF001 - as m1_scale and the session tests wait
        if time.monotonic() > deadline:
            raise LaunchRefused(f"no complete index pass: {session.status()}")
        time.sleep(1)
    if not session.wait_for_catalogue(seconds):
        raise LaunchRefused("the catalogue was not read")


def open_sessions(revisions: Sequence[str], *, repository: Path, work: Path, root: Path, memory: Any, settings: Any, settings_file: Mapping[str, Any], embedder: Any,
                  trees: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Path]]:
    """Production's session for each snapshot, in the given order, each indexed to completion before the next starts."""
    from optimus.context.memory_session import session_factory

    factory = session_factory(memory_root=root, config_root=work / "config", settings=settings, config=memory, artifact_directory=settings_file["embedding"]["artifact_directory"])
    sessions: dict[str, Any] = {}
    workspaces: dict[str, Path] = {}
    for snapshot in revisions:
        revision = snapshot.removeprefix("git:")
        tree = work / "trees" / revision[:12]
        m1_evaluate.materialize(repository, revision, tree, branch=f"q-{revision[:12]}")
        session = factory(tree)
        if session is None:
            raise LaunchRefused(f"{revision[:12]}: the workspace could not be registered")
        session._embedder_for = lambda: embedder  # noqa: SLF001 - the one swap: the shared content-keyed embedding cache (Fable gate consult)
        sessions[snapshot], workspaces[snapshot] = session, tree
        started = time.perf_counter()
        session.start()
        wait_indexed(session)
        tree_id = subprocess.run(["git", "-C", str(repository), "rev-parse", f"{revision}^{{tree}}"], capture_output=True, text=True, check=True).stdout.strip()
        coverage = session._current_scope().storage.call("coverage")["current"]["coverage"]  # noqa: SLF001
        trees.append({"revision": snapshot, "tree": f"git:{tree_id}", "seconds": round(time.perf_counter() - started, 1), "coverage": coverage})
    return sessions, workspaces


def run_gate(config: Mapping[str, Any], repository: Path, out: Path) -> dict[str, Any]:
    """G2 in one container lifecycle: index the five snapshots in a fixed order, the budget pass with the outline on the main snapshot's own
    session, its gates, then the zero-paid rehearsal of every row."""
    present = [name for name in PROVIDER_KEY_NAMES if os.environ.get(name)]
    if present:
        raise LaunchRefused(f"a provider key is in the environment: {', '.join(present)}")
    contract = json.loads((repository / config.get("contract", "reports/plan12-memory-m2b/evaluation-contract.json")).read_text(encoding="utf-8"))
    u_equals_b = contract["task1_freezes"]["selected_candidate"]["u_equals_b"]
    cases_record = json.loads((repository / config["cases"]).read_text(encoding="utf-8"))
    cases = cases_record["paid_q"]["cases"]
    head = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    work = repository / config["work_dir"] / "gate"
    legacy, model_aware, _estimate = ev.production_routes(work)
    report: dict[str, Any] = {"schema": "plan12-memory-m2b.gate-g2.v1", "head": f"git:{head}", "label": config["label"], "cases_sha256": _file_sha(repository / config["cases"]),
                              "launcher_sha256": _file_sha(Path(__file__)), "runner_sha256": _file_sha(Path(paid.__file__)), "registry_hash": trusted_snapshot().effective_hash,
                              "tariff_id": paid.D3_TARIFF.id, "rehearsal_gateway": "the real Gateway handler in process over a scripted provider", "trees": []}
    root, memory, _password, client, gateway, settings, settings_file = m1_scale._provision(dict(config), repository, work)  # noqa: SLF001
    sessions: dict[str, Any] = {}
    try:
        embedder = m1_evaluate.CachedEmbedder(ev.FastembedEmbedder(root, memory.embedding, directory=settings_file["embedding"]["artifact_directory"], threads=config["embedding_threads"]),
                                              ev.embedding_cache(config, repository))
        revisions = sorted({case["snapshot"] for case in cases})  # the fixed order; the paid run repeats it
        sessions, workspaces = open_sessions(revisions, repository=repository, work=work, root=root, memory=memory, settings=settings, settings_file=settings_file,
                                             embedder=embedder, trees=report["trees"])
        main = next(case["snapshot"] for case in cases if case["category"] == "budget")
        rows = ev._budget_cases(config, repository, work, settings, embedder, cases_record, report["trees"], legacy=legacy.ceiling, model_aware=model_aware, outline=True,  # noqa: SLF001
                                turn=sessions[main].turn())
        report["budget"] = {"outline_available": True, "budget": {"legacy": legacy.ceiling, "C": model_aware.ceiling, "T": model_aware.target}, "rows": rows,
                            "budget_gates": ev.budget_gates(rows, outline_available=True)}
        ev._write(report, out)  # noqa: SLF001
        composition = Composition(trusted_snapshot(), secrets.token_hex(32), legacy, sessions, workspaces)
        provider = ScriptedProvider(composition.snapshot)
        report["rehearsal"] = rehearse(cases, composition, gateway=local_client(composition.snapshot, composition.shared_secret, provider), provider=provider,
                                       u_equals_b=u_equals_b, outline_available=True, budget_report=report["budget"])
        report["embedding"] = {"embedded": embedder.embedded, "reused": embedder.reused}
        report["passes"] = report["budget"]["budget_gates"]["passes"] and report["rehearsal"]["passes"]
        ev._write(report, out)  # noqa: SLF001
    finally:
        for session in sessions.values():
            session.close()
        client.close()
        gateway.kill()
        gateway.wait(10)
        subprocess.run(["docker", "rm", "-f", config["container"]], capture_output=True, check=False)
        subprocess.run(["docker", "volume", "rm", "-f", config["volume"]], capture_output=True, check=False)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    repository = Path.cwd()
    config = json.loads((repository / args.config).read_text(encoding="utf-8"))
    report = run_gate(config, repository, repository / args.output)
    print(json.dumps({"passes": report["passes"], "sends": report["rehearsal"]["sends"], "problems": report["rehearsal"]["problems"][:5]}))
    return 0 if report["passes"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
