"""Plan 12.14 Task 2: what the budget pass measures and what paid Q sends are production's own bytes, given matching inputs (Codex CP1
attempts 2-3, finding 2).

Production's side is the real MemorySession turn over the real file policy, its own retriever and its own required set, inside a real
attached turn; the storage port answers from a table, as in tests/unit/context/test_memory_tools_and_turns. The evaluator's side is
m2b_evaluate exactly as its budget pass calls it: its own Retriever, production_retrieve(), policy_reader() and budget_case(). The paid
side is m2b_paid.run_one: the real AgentRunner behind the Guard, the real route binder and the in-process Gateway.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from context_engine.engine import ContextEngine
from context_engine.retrieval import Retriever
from optimus.agent import runner as runner_module
from optimus.agent.models import AgentRunRequest
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.context import memory_session
from optimus.context.assembly import AttachedTurn, ContextAttachment, SummarizerRoute
from optimus.context.context_budget import BudgetPolicy, legacy_budget
from optimus.runtime.modes import ExecutionMode
from tests.unit.agent.test_context_selection import SANITIZER, _SummarizerCall, limits, parameters
from tests.unit.agent.test_route_binding import STANDARD, InProcessGateway, ScriptedUpstream, _client
from tests.unit.context.test_memory_tools_and_turns import SOURCE, _record, _session, _sha, _Storage, workspace  # noqa: F401 - fixture
from tests.unit.tools.test_plan12_memory_m2b_paid import _approved, _binder, _ceiling, no_sleep, snapshot  # noqa: F401 - fixtures
from tools.plan12_memory import m2b_evaluate as ev
from tools.plan12_memory import m2b_paid as paid

LOADER = "class Loader:\n    def load(self):\n        return 1\n"
TASK = "Explain how pkg/a.py relates to `Loader`."
USABLE = 600  # legacy 150 holds the required file and nothing else; the model-aware arm below has room for the named symbol
MODEL_AWARE = BudgetPolicy("model-aware", 1_500, 1_200)


class _SymbolsOnly(_Storage):
    """No lexical matches and no embedder: optional evidence reaches the pack only through the channels the task's names open."""

    def call(self, op: str, **fields: Any) -> dict:
        if fields.get("mode") == "lexical":
            self.calls.append((op, fields))
            return {"records": []}
        return super().call(op, **fields)


def _records() -> list[dict]:
    return [_record("x", "pkg/a.py", "helper", _sha(SOURCE), lines=(6, 7), signature="def helper():"),
            _record("y", "pkg/b.py", "Loader", _sha(LOADER), lines=(1, 3), signature="class Loader:")]


def _digest(text: str) -> str:
    return "hex:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def packs(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Every pack production's memory turn assembles, in order."""
    seen: list[Any] = []
    real = memory_session.assemble_pack

    def spy(**kwargs: Any) -> Any:
        seen.append(real(**kwargs))
        return seen[-1]

    monkeypatch.setattr(memory_session, "assemble_pack", spy)
    return seen


def _measured(root: Path, storage: _Storage | None = None) -> dict[str, Any]:
    (root / "pkg" / "b.py").write_text(LOADER, encoding="utf-8", newline="\n")
    case = {"case_id": "QX", "kind": "ordinary-fit", "task": TASK, "required_files": [{"path": "pkg/a.py"}]}
    retrieval = ev.production_retrieve(Retriever(storage or _SymbolsOnly(_records()), None), TASK, named=["pkg/a.py"])
    return ev.budget_case(case, retrieval, ev.policy_reader(root), policy="baseline", model_aware=MODEL_AWARE, legacy=legacy_budget(USABLE),
                          full_input=len, pack_estimate=len)


def _queries(storage: _Storage) -> list[dict]:
    return [fields for op, fields in storage.calls if op == "query"]


def test_each_arms_pack_in_the_budget_pass_is_the_pack_production_builds(workspace, packs):  # noqa: F811
    measured = _SymbolsOnly(_records())
    row = _measured(workspace, measured)
    turns = []
    for policy in (None, MODEL_AWARE):
        turns.append(_SymbolsOnly(_records()))
        _session(workspace, turns[-1]).turn().assemble(run_id="r", task=TASK, selection_text=TASK, model_id="m", estimate=len,
                                                       usable_input_tokens=USABLE, pack_budget=policy)
    assert _queries(measured) == _queries(turns[0]) == _queries(turns[1]), "the same index queries: query text, named files and symbols"
    assert [_digest(pack.text) for pack in packs] == [row["arms"]["BU"]["pack_sha256"], row["arms"]["F"]["pack_sha256"]]
    assert (row["arms"]["BU"]["optional_items"], row["arms"]["F"]["optional_items"]) == (0, 1) and row["arms"]["BU"]["complete"], "the arrangement"


def _attached(root: Path, pack_budget: BudgetPolicy, *, records: dict | None = None, prompt: str = TASK, mode: ExecutionMode = ExecutionMode.CHAT,
              memory: bool = True) -> AttachedTurn:
    """A Q row's packer as a launch prepares one: a real attached turn (no history unless `records` gives some), the memory turn joined to
    it, then the history view prepared, in the adapter's order (spec.py: _prepare_memory, then _prepare_attached_context; Codex CP2 A2)."""
    records = records or {}
    attachment = ContextAttachment(
        engine=ContextEngine(), parameters=parameters(), limits=limits(), source_max_bytes=1_000_000, record_reservation_bytes=0,
        usable_input_tokens=50_000, estimate_request=len, pack_budget=pack_budget, registry_hash="e" * 64, model_id=STANDARD,
        summarizer=lambda identity, deliver_notice: _SummarizerCall(),
        summarizer_route=SummarizerRoute(model_id="test/summarizer", role="summarizer", route=("p",), reasoning=None, quantizations=("fp8",)),
        record_receipt=[].append, max_repacks=2,
    )
    attached = AttachedTurn.capture(attachment=attachment, session_key="q", records=records, approvals={}, generation=len(records), sanitizer=SANITIZER,
                                    strategy="compaction", mode=mode, checkpoint=None, current_prompt=prompt, turn_seq=len(records) + 1, cancelled=lambda: False)
    if memory:
        attached.memory = _session(root, _SymbolsOnly(_records())).turn()
    assert attached.prepare().kind == "view"
    return attached


def test_n_must_run_on_the_attached_turn_because_a_bare_runner_is_not_productions_no_index_request(tmp_path, workspace, snapshot):  # noqa: F811
    """Fable gate consult, question 2: production attaches whenever the registry has a summarizer, so its no-index first turn is an attached
    turn with no memory, fitted through the packer. A bare runner (no packer) sends a different request: the attached turn carries its
    conversation envelope even with no history. So Q's N runs on the attached turn without a memory turn, not with packer None."""
    _measured(workspace)
    sent = []
    for packer in (None, _attached(workspace, BudgetPolicy("legacy", 500, None), memory=False)):
        gateway = InProcessGateway(snapshot, ScriptedUpstream(replies=["An answer."]))
        row = paid.run_one({"case_id": "QX", "task": TASK}, "N", position=1, gateway=_client(gateway), approved=_approved(snapshot), model=STANDARD,
                           packer=packer, binder=_binder(snapshot), workspace=workspace, ceiling=_ceiling(), allowance=1)
        assert row["logical_requests"] == 1 and row["reconciliation"]["problems"] == []
        [payload] = gateway.payloads
        sent.append(payload["input"])
    bare, attached = sent
    assert bare != attached and "pkg/a.py" in bare and "pkg/a.py" in attached
    assert "Prior conversation" in attached and "Prior conversation" not in bare, "the difference is production's own envelope"


def test_fs_paid_request_is_productions_final_round_request_carrying_the_measured_pack(tmp_path, workspace, snapshot, packs):  # noqa: F811
    """The Guard forwards the runner's own bytes: F's request equals production's Chat builder with tools withdrawn (the enumerated Q
    delta) fitted by an identically prepared packer, and carries exactly the pack whose digest the budget pass recorded."""
    row = _measured(workspace)
    gateway = InProcessGateway(snapshot, ScriptedUpstream(replies=["An answer."]))
    sent = paid.run_one({"case_id": "QX", "task": TASK}, "F", position=1, gateway=_client(gateway), approved=_approved(snapshot), model=STANDARD,
                        packer=_attached(workspace, MODEL_AWARE), binder=_binder(snapshot), workspace=workspace, ceiling=_ceiling(), allowance=1)
    assert sent["logical_requests"] == 1 and sent["reconciliation"]["problems"] == []
    [payload] = gateway.payloads
    [pack] = packs
    assert _digest(pack.text) == row["arms"]["F"]["pack_sha256"] and pack.text in payload["input"]

    packer = _attached(workspace, MODEL_AWARE)
    request = AgentRunRequest(run_id="m2b-q-QX-F", task=TASK, execution_mode=ExecutionMode.CHAT, workspace_root=workspace, max_planning_turns=1)
    context = AgentRunner(gateway_client=None, model=STANDARD, state_store=InMemoryAgentStateStore())._turn_context(request, TASK, packer)  # noqa: SLF001
    build = runner_module._chat_builder(request, context.text, memory=packer.memory, repo_map=packer.memory.repo_map(), index_results="", tools_open=False)  # noqa: SLF001
    assert payload["input"] == packer.fit(build)
    assert sent["sent"][0]["input_sha256"] == _digest(payload["input"])


# --- the outline row in both proofs (Q-release gate item 10: Fable CP2 finding 4) ------------------------------------------------

BIG = "".join(f"def handler_{i}(event, context):\n    return 'OUTLINE_BODY {i}'\n\n\n" for i in range(200))
SUMMARY = 'Summarize "pkg/big.py"'


def _measured_outline(root: Path, storage: _Storage) -> dict[str, Any]:
    (root / "pkg" / "big.py").write_text(BIG, encoding="utf-8", newline="\n")
    case = {"case_id": "QO-X", "kind": "outline", "task": SUMMARY, "required_files": [{"path": "pkg/big.py"}]}
    retrieval = ev.production_retrieve(Retriever(storage, None), SUMMARY, named=["pkg/big.py"])
    return ev.budget_case(case, retrieval, ev.policy_reader(root), policy="baseline", model_aware=MODEL_AWARE, legacy=legacy_budget(USABLE),
                          full_input=len, pack_estimate=len, outline=True)


def test_an_outline_rows_pack_in_the_budget_pass_is_the_pack_productions_chat_turn_builds(workspace, packs):  # noqa: F811
    """The evaluator's outline arm (the case's required file and summary target) and production's Chat turn (its resolver and the runner's
    Chat-only target) build the same F outline pack; B refuses in both. optional_room is the chosen budget less V (Fable CP2 finding 6)."""
    from context_engine.file_outline import DISCLOSURE, summary_target

    measured = _SymbolsOnly(_records())
    row = _measured_outline(workspace, measured)
    turns = []
    for policy in (None, MODEL_AWARE):
        turns.append(_SymbolsOnly(_records()))
        _session(workspace, turns[-1]).turn().assemble(run_id="r", task=SUMMARY, selection_text=SUMMARY, model_id="m", estimate=len,
                                                       usable_input_tokens=USABLE, pack_budget=policy, overview_path=summary_target(SUMMARY))
    assert _queries(measured) == _queries(turns[0]) == _queries(turns[1])
    assert [_digest(pack.text) for pack in packs] == [row["arms"]["BU"]["pack_sha256"], row["arms"]["F"]["pack_sha256"]]
    assert (row["arms"]["BU"]["complete"], row["arms"]["F"]["complete"], row["arms"]["F"]["outline"]) == (False, True, True)
    assert DISCLOSURE in packs[1].text and "OUTLINE_BODY" not in packs[1].text
    v = packs[1].outline["section_tokens"]
    assert 0 < v <= MODEL_AWARE.ceiling and row["arms"]["F"]["optional_room"] == row["arms"]["F"]["budget"] - v >= 0


def test_fs_paid_outline_request_carries_exactly_the_measured_outline_pack(tmp_path, workspace, snapshot, packs):  # noqa: F811
    """Through the real runner, Guard, binder and in-process Gateway: F's summary request carries the outline pack whose digest the budget
    pass recorded, with its disclosure and no body."""
    from context_engine.file_outline import DISCLOSURE

    row = _measured_outline(workspace, _SymbolsOnly(_records()))
    gateway = InProcessGateway(snapshot, ScriptedUpstream(replies=["An outline-based summary."]))
    sent = paid.run_one({"case_id": "QO-X", "task": SUMMARY}, "F", position=1, gateway=_client(gateway), approved=_approved(snapshot), model=STANDARD,
                        packer=_attached(workspace, MODEL_AWARE, prompt=SUMMARY), binder=_binder(snapshot), workspace=workspace, ceiling=_ceiling(), allowance=1)
    assert sent["logical_requests"] == 1 and sent["reconciliation"]["problems"] == []
    [payload] = gateway.payloads
    [pack] = packs
    assert pack.outline is not None and _digest(pack.text) == row["arms"]["F"]["pack_sha256"] and pack.text in payload["input"]
    assert DISCLOSURE in payload["input"] and "OUTLINE_BODY" not in payload["input"]


def test_a_bound_outline_request_keeps_the_whole_file_requests_cache_prefix(tmp_path, workspace, packs):  # noqa: F811
    """Q-release gate item 13 (Fable CP2 finding 8): on a route approved to cache a prefix, with the same map and tool state, a bound outline
    request and a bound whole-file request share the prefix digest and cache_prefix_chars; the outline and its disclosure sit after it."""
    from context_engine.file_outline import DISCLOSURE
    from tests.unit.optimus_gateway.model_policy_support import verified_snapshot
    from tests.unit.optimus_gateway.test_prompt_cache import _with_cache

    (tmp_path / "cached").mkdir()
    cached = verified_snapshot(tmp_path / "cached", _with_cache("prefix"))
    _measured_outline(workspace, _SymbolsOnly(_records()))
    sent = {}
    for name, task in (("outline", SUMMARY), ("whole", 'Summarize "pkg/a.py"')):
        gateway = InProcessGateway(cached, ScriptedUpstream(replies=["A summary."]))
        row = paid.run_one({"case_id": f"QO-{name}", "task": task}, "F", position=1, gateway=_client(gateway), approved=_approved(cached), model=STANDARD,
                           packer=_attached(workspace, MODEL_AWARE, prompt=task), binder=_binder(cached), workspace=workspace, ceiling=_ceiling(), allowance=1)
        [entry] = row["sent"]
        [payload] = gateway.payloads
        sent[name] = (entry, payload["input"])
    (outline, outline_input), (whole, whole_input) = sent["outline"], sent["whole"]
    assert packs[0].outline is not None and packs[1].outline is None, "the arrangement: one outline turn, one whole-file turn"
    assert outline["cache_prefix_chars"] is not None and outline["cache_prefix_chars"] == whole["cache_prefix_chars"]
    assert outline["prefix_sha256"] == whole["prefix_sha256"] and outline_input[: outline["cache_prefix_chars"]] == whole_input[: whole["cache_prefix_chars"]]
    assert DISCLOSURE in outline_input[outline["cache_prefix_chars"]:] and DISCLOSURE not in outline_input[: outline["cache_prefix_chars"]]
