"""Plan 12.14 Task 1 (CP1, after Codex round 122 attempt 2): the paid Q runner and scorer with zero paid calls.

The runner tests drive the real AgentRunner, the real route binder and the real in-process Gateway handler (tests.unit.agent.test_route_binding);
only the provider is scripted. The scorer tests use the frozen cases, their pinned snapshot blobs, and answers written independently of the
encoded checks: one correct answer per answered case and a contradicting variant of each relationship the oracle states."""

from __future__ import annotations

import json
import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import optimus_gateway.responses as gateway_responses
from optimus.agent.index_turn import LIMIT_NOTICE
from optimus.agent.models import AgentRunRequest
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.runtime.modes import ExecutionMode
from tests.unit.agent.test_route_binding import STANDARD, InProcessGateway, Notices, ScriptedUpstream, _client, _policy
from tests.unit.optimus_gateway.model_policy_support import CAP, verified_snapshot
from tools.plan12_memory import m2b_paid as paid
from tools.plan12_memory import m2b_score as sc

ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads((ROOT / "reports/plan12-memory-m2b/cases.json").read_text(encoding="utf-8"))["paid_q"]["cases"]
BY_ID = {c["case_id"]: c for c in CASES}
TOO_LARGE = "REQUIRED_WORKSPACE_FILE_TOO_LARGE"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway_responses, "_sleep", lambda seconds: None)


@pytest.fixture
def snapshot(tmp_path: Path):
    (tmp_path / "registry").mkdir()
    return verified_snapshot(tmp_path / "registry")


def _ceiling(attempts: int = 96, usd: str = "6.00") -> paid.Ceiling:
    return paid.Ceiling(attempts_max=attempts, usd_max=Decimal(usd), per_attempt_usd=Decimal("0.04608"))


def _approved(snapshot, *, registry_hash: str | None = None, model_id: str = STANDARD) -> paid.Approved:
    return paid.Approved(registry_hash or snapshot.effective_hash, estimate_request=len, model_id=model_id, output_cap=CAP)


def _binder(snapshot, cap: int = CAP):
    return _policy(snapshot, STANDARD, output_cap=cap).capture(session_id="s", turn_seq=1, deliver_notice=Notices())


def _row(tmp_path: Path, snapshot, *, upstream: ScriptedUpstream | None = None, allowance: int = 1, task: str = "What is x?", cap: int = CAP,
         approved_hash: str | None = None, approved_model: str = STANDARD, ceiling: paid.Ceiling | None = None, bind: bool = True,
         required: tuple[str, ...] = ()) -> tuple[dict[str, Any], InProcessGateway]:
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    gateway = InProcessGateway(snapshot, upstream or ScriptedUpstream(replies=["The answer."]))
    row = paid.run_one({"case_id": "QX", "task": task}, "N", position=1, gateway=_client(gateway), approved=_approved(snapshot, registry_hash=approved_hash, model_id=approved_model),
                       model=STANDARD, packer=None, binder=_binder(snapshot, cap) if bind else None, workspace=workspace, ceiling=ceiling or _ceiling(), allowance=allowance)
    row["expected_logical_requests"] = allowance
    row["emitted_answer"] = paid.emitted_answer(row["stop_reason"], row["answer"], required)
    return row, gateway


# --- schedule and expectations -------------------------------------------------------------------------------------------


def test_the_schedule_is_each_categorys_four_orders_and_drops_u_when_it_equals_b():
    full = paid.schedule(CASES, u_equals_b=False)
    assert len(full) == 48 and [p for _c, _a, p in full] == list(range(1, 49))
    assert [(c, a) for c, a, _p in full[:8]] == [("QR1", "N"), ("QR1", "B"), ("QR1", "U"), ("QR1", "F"), ("QR2", "B"), ("QR2", "U"), ("QR2", "F"), ("QR2", "N")]
    assert len(paid.schedule(CASES, u_equals_b=True)) == 36


def test_expected_calls_follow_the_predeclared_refusals():
    calls = paid.expected_calls(CASES, u_equals_b=True, outline_available=True)
    assert sum(calls.values()) == 25  # Codex round 122: 7 N, 7 B, 11 F
    assert sum(v for (_c, a), v in calls.items() if a == "N") == 7 and sum(v for (_c, a), v in calls.items() if a == "F") == 11
    assert all(calls[(c, a)] == 0 for c in ("QB3", "QB4", "QO1", "QO2") for a in ("N", "B")) and all(calls[("QO4", a)] == 0 for a in ("N", "B", "F"))
    assert sum(paid.expected_calls(CASES, u_equals_b=True, outline_available=False).values()) == 23


def test_the_ceiling_reserves_the_route_attempts_and_prices_unknowns_at_the_worst_case():
    ceiling = paid.Ceiling(attempts_max=4, usd_max=Decimal("1"), per_attempt_usd=Decimal("0.1"))
    ceiling.reserve()
    ceiling.settle([{"cost_usd": "0.05"}, {"cost_usd": "0.05"}])
    ceiling.reserve()
    ceiling.settle([{"cost_usd": "0.05"}])
    with pytest.raises(paid.CapRefused):
        ceiling.reserve()
    tight = paid.Ceiling(attempts_max=96, usd_max=Decimal("0.25"), per_attempt_usd=Decimal("0.1"))
    tight.reserve()
    tight.settle([{"cost_usd": None}])
    with pytest.raises(paid.CapRefused):
        tight.reserve()


# --- reconciliation (the #463 producer contract, Codex attempt 2 finding 4) ------------------------------------------------


def _sent(*attempts: tuple[int, str, str]) -> list[dict[str, Any]]:
    return [{"route_request_id": "r1", "gateway_attempts": [{"attempt": n, "gateway_request_id": g, "outcome": o, "physical": o in paid.PHYSICAL} for n, g, o in attempts]}]


def _receipt(ordinal: int, gateway_id: str | None, outcome: str, cost: str | None) -> dict[str, Any]:
    return {"attempt_id": f"m2b-q-QX-N:answer:1:1:{ordinal}", "gateway_request_id": gateway_id, "outcome": outcome, "cost_usd": cost}


def test_reconciliation_keys_each_attempt_by_gateway_id_ordinal_and_disposition():
    """A rejected and a completed attempt that repeat one Gateway id each keep their own receipt's charge."""
    out = paid.reconcile(_sent((1, "g1", "rejected"), (2, "g1", "completed")), [_receipt(2, "g1", "completed", "0.01"), _receipt(1, "g1", "rejected", "0")])
    assert out["problems"] == [] and [a["cost_usd"] for a in out["attempts"]] == ["0", "0.01"]


@pytest.mark.parametrize("receipts, problem, unclaimed", [
    ([], "no matching host receipt", 0),  # missing
    ([_receipt(1, "g1", "rejected", "0")], "no matching host receipt", 0),  # partial: the completed attempt's receipt is missing
    ([_receipt(1, "g1", "rejected", "0"), _receipt(2, "g1", "completed", "0.01"), _receipt(2, "g1", "completed", "0.01")], "2 host receipts match", 2),  # duplicates: ambiguous, both kept
    ([_receipt(1, "g1", "rejected", "0"), _receipt(2, "g1", "completed", "0.01"), _receipt(3, "g9", "completed", "0.02")], "matches no Gateway attempt", 1),  # unattributed, kept
])
def test_reconciliation_keeps_and_flags_missing_duplicate_and_unclaimed_records(receipts, problem, unclaimed):
    out = paid.reconcile(_sent((1, "g1", "rejected"), (2, "g1", "completed")), receipts)
    assert any(problem in p for p in out["problems"]) and len(out["attempts"]) == 2 and len(out["unclaimed_receipts"]) == unclaimed


@pytest.mark.parametrize("receipt", [_receipt(2, "g1", "completed", "0.01"), _receipt(1, "g1", "rejected", "0"), _receipt(1, "g2", "completed", "0.01")],
                         ids=["another ordinal", "another disposition", "another Gateway id"])
def test_a_receipt_matches_only_on_every_key(receipt):
    out = paid.reconcile(_sent((1, "g1", "completed")), [receipt])
    assert out["attempts"][0]["cost_usd"] is None and out["problems"][0] == "r1 attempt 1: no matching host receipt" and out["unclaimed_receipts"] == [receipt]


def test_a_row_with_any_reconciliation_problem_is_incomplete():
    row = {"guard_refusal": None, "reconciliation": {"problems": ["host receipt x (completed) matches no Gateway attempt"]}, "logical_requests": 1,
           "expected_logical_requests": 1, "attempts": [{"cost_usd": "0.01"}], "stop_reason": None, "emitted_answer": True}
    assert paid.terminal(row) == ("incomplete", "host receipt x (completed) matches no Gateway attempt")
    assert paid.terminal({**row, "reconciliation": {"problems": []}})[0] == "settled"


def test_two_receipts_for_one_key_are_ambiguous():
    out = paid.reconcile(_sent((1, "g1", "completed")), [_receipt(1, "g1", "completed", "0.01"), _receipt(1, "g1", "completed", "0.01")])
    assert out["problems"][0] == "r1 attempt 1: 2 host receipts match" and out["attempts"][0]["cost_usd"] is None and len(out["unclaimed_receipts"]) == 2


def test_a_send_with_no_gateway_attempt_is_unknown():
    out = paid.reconcile([{"route_request_id": "r1", "gateway_attempts": []}], [])
    assert len(out["attempts"]) == 2 and all(a["cost_usd"] is None for a in out["attempts"]) and out["problems"]


def test_a_receipt_row_keeps_every_reported_field():
    from datetime import UTC, datetime

    from optimus.gateway.models import GatewayUsage
    from optimus.usage.turn_settlement import StageReceipt

    usage = GatewayUsage(gateway_request_id="g1", provider="anthropic", billing_units=0, cost_usd=Decimal("0.01"), input_tokens=1000, output_tokens=100, total_tokens=1100,
                         cached_tokens=600, model_version="v", native_unit="tokens")
    receipt = StageReceipt(session_id=None, turn_id="t", stage="answer", attempt_id="a1", gateway_request_id="g1", outcome="completed",
                           reported_cost_usd=Decimal("0.01"), recorded_at=datetime.now(UTC), gateway_usage=usage)
    row = paid.receipt_row(receipt)
    assert row["repriced_uncached_usd"] == "0.00075" and row["cache_write_tokens"] == "UNKNOWN" and row["post_teardown"] is False
    assert row["usage"]["model_version"] == "v" and row["usage"]["native_unit"] == "tokens" and row["usage"]["total_tokens"] == 1100 and row["recorded_at"]
    assert set(paid.USAGE_FIELDS) <= set(GatewayUsage.model_fields)


# --- the real runner, the real binder and the in-process Gateway ---------------------------------------------------------


def test_a_bound_request_is_settled_from_the_gateways_own_attempts(tmp_path, snapshot):
    row, gateway = _row(tmp_path, snapshot)
    assert paid.terminal(row)[0] == "settled" and row["logical_requests"] == 1 == len(gateway.payloads) and row["reconciliation"]["problems"] == []
    [sent] = row["sent"]
    assert sent["route_request_id"] == gateway.payloads[0]["route_binding"]["request_id"] and sent["gateway_attempts"][0]["physical"]
    [attempt] = row["attempts"]
    assert attempt["gateway_request_id"] == row["host_receipts"][0]["gateway_request_id"] and attempt["cost_usd"] is not None


def test_a_bound_resend_counts_two_physical_attempts_against_the_ceiling(tmp_path, snapshot):
    from optimus_gateway.upstream_client import UpstreamAttemptFailure

    ceiling = _ceiling()
    row, _ = _row(tmp_path, snapshot, upstream=ScriptedUpstream(replies=["ok"], attempts=[UpstreamAttemptFailure("rejected", http_status=429), None]), ceiling=ceiling)
    assert row["logical_requests"] == 1 and len(row["attempts"]) == 2 and ceiling.attempts_used == 2 and row["reconciliation"]["problems"] == []
    assert [a["outcome"] for a in row["attempts"]] == ["rejected", "completed"] and paid.terminal(row)[0] == "settled"


def test_a_terminal_failure_after_a_send_keeps_its_attempts_and_is_not_settled(tmp_path, snapshot):
    from optimus_gateway.upstream_client import UpstreamAttemptFailure

    row, _ = _row(tmp_path, snapshot, upstream=ScriptedUpstream(attempts=[UpstreamAttemptFailure("not_sent"), UpstreamAttemptFailure("uncertain")]))
    assert row["logical_requests"] == 1 and row["stop_reason"] is not None
    assert [a["outcome"] for a in row["attempts"]] == ["uncertain"]  # not_sent never left: not a physical attempt
    assert paid.terminal(row)[0] in {"incomplete", "failed"}


@pytest.mark.parametrize("change, reason", [
    ({"bind": False}, "unbound"),
    ({"approved_model": "other/model-under-the-same-hash"}, "not the released one"),
    ({"approved_hash": "0" * 64}, "approved composition"),
    ({"cap": CAP + 1}, "approved composition"),
    ({"task": "x" * 70_000}, "over the cap"),
    ({"allowance": 0}, "allowance"),
    ({"ceiling": paid.Ceiling(attempts_max=1, usd_max=Decimal("6"), per_attempt_usd=Decimal("0.04608"))}, "reservation refused"),
])
def test_the_guard_refuses_before_anything_is_sent(tmp_path, snapshot, change, reason):
    row, gateway = _row(tmp_path, snapshot, **change)
    assert gateway.payloads == [] and row["logical_requests"] == 0 and reason in (row["guard_refusal"] or "")
    assert paid.terminal(row)[0] == "incomplete"


class _Recording:
    """The real Gateway client, each request's arguments kept so a later send can be attempted with them."""

    def __init__(self, inner: Any) -> None:
        self.inner, self.calls = inner, []

    def create_response(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.inner.create_response(**kwargs)


@pytest.mark.parametrize("lose", ["all", "the completed attempt's"])
def test_a_missing_or_partial_receipt_set_stops_the_next_send(tmp_path, snapshot, lose):
    from optimus_gateway.upstream_client import UpstreamAttemptFailure

    workspace = tmp_path / "ws"
    workspace.mkdir()
    gateway = InProcessGateway(snapshot, ScriptedUpstream(replies=["ok", "again"], attempts=[UpstreamAttemptFailure("rejected", http_status=429), None, None]))
    inner, receipts = _Recording(_client(gateway)), []
    guard = paid.Guard(inner, _approved(snapshot), _ceiling(), allowance=2, receipts=receipts)
    runner = AgentRunner(gateway_client=guard, model=STANDARD, state_store=InMemoryAgentStateStore())
    request = AgentRunRequest(run_id="m2b-q-QX-N", task="What is x?", execution_mode=ExecutionMode.CHAT, workspace_root=workspace, max_planning_turns=1, max_cost_usd=Decimal("6"))
    with paid.zero_tools():
        runner.run(request, context_packer=None, route_binder=_binder(snapshot), stage_receipts=receipts.append)
    assert len(guard.sent) == 1 and len(receipts) == 2 and paid.reconcile(guard.sent, [paid.receipt_row(r) for r in receipts])["problems"] == []
    del receipts[0 if lose == "all" else 1 :]
    with pytest.raises(paid.GuardRefused):
        guard.create_response(**inner.calls[0])
    assert len(gateway.payloads) == 1 and "not reconciled" in guard.refusal


def test_a_refused_row_sends_nothing_through_the_real_runner(tmp_path, snapshot):
    """N on an oversized named file: today's context refuses before dispatch and delivers only the host's own notice."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "big.py").write_text("#" * 20_000 + "\n", encoding="utf-8")
    row, gateway = _row(tmp_path, snapshot, allowance=0, task='Summarize "big.py"', required=("big.py",))
    assert gateway.payloads == [] and row["logical_requests"] == 0 and row["guard_refusal"] is None and row["emitted_answer"] is False
    assert row["stop_reason"] == TOO_LARGE and paid.terminal(row, expected_stop=TOO_LARGE)[0] == "expected_zero_call"
    assert paid.terminal(row, expected_stop=None)[0] == "incomplete"  # an undeclared stop never passes as expected


def test_a_zero_call_row_needs_its_declared_stop_and_no_emitted_answer():
    row = {"guard_refusal": None, "reconciliation": {"problems": []}, "logical_requests": 0, "expected_logical_requests": 0, "stop_reason": TOO_LARGE, "emitted_answer": False}
    assert paid.terminal(row, expected_stop=TOO_LARGE)[0] == "expected_zero_call"
    assert paid.terminal({**row, "stop_reason": "AGENT_SETUP_FAILED"}, expected_stop=TOO_LARGE)[0] == "incomplete"
    assert paid.terminal({**row, "emitted_answer": True}, expected_stop=TOO_LARGE)[0] == "incomplete"
    notice = "Workspace reference 'src/optimus/acp/launch_gate.py' exceeds the available context budget. Retry with a smaller scope."
    assert paid.emitted_answer(TOO_LARGE, notice, ["src/optimus/acp/launch_gate.py"]) is False
    assert paid.emitted_answer(TOO_LARGE, notice, ["src/other.py"]) is True and paid.emitted_answer(None, notice, ["src/optimus/acp/launch_gate.py"]) is True
    assert paid.emitted_answer(TOO_LARGE, notice + "\n```python\ndef _project_child_env():\n```", ["src/optimus/acp/launch_gate.py"]) is True
    assert paid.emitted_answer(TOO_LARGE, None, []) is False


def test_the_run_stops_at_the_first_row_that_is_not_settled(tmp_path, snapshot):
    from optimus_gateway.upstream_client import UpstreamAttemptFailure

    workspace = tmp_path / "ws"
    workspace.mkdir()
    gateway = InProcessGateway(snapshot, ScriptedUpstream(attempts=[UpstreamAttemptFailure("uncertain"), UpstreamAttemptFailure("uncertain")]))
    written: list[Any] = []
    answers: list[Any] = []
    report = paid.run(CASES, u_equals_b=True, outline_available=True, gateway=_client(gateway), approved=_approved(snapshot), model=STANDARD, packer_for=lambda _c, _a: None,
                      binder_for=lambda _c, _a: _binder(snapshot), workspace_for=lambda _c: workspace, ceiling=_ceiling(), write=written.append, write_answers=answers.append)
    assert len(report["rows"]) == 1 and report["stopped"]["at"] == ["QR1", "N"] and len(gateway.payloads) == 1
    assert "answer" not in report["rows"][0] and report["rows"][0]["terminal"] in {"incomplete", "failed"} and report["schema"].endswith("paid-attempts.v2")


# --- the scorer -----------------------------------------------------------------------------------------------------------


def _reader(snapshot: str):
    def read(path: str) -> bytes | None:
        done = subprocess.run(["git", "-C", str(ROOT), "cat-file", "blob", f"{snapshot.removeprefix('git:')}:{path}"], capture_output=True)
        return done.stdout if done.returncode == 0 else None

    return read


SOURCE = b"def outer():\n    pass\n\n\nclass Thing:\n    def method(self):\n        return 1\n" + b"\n" * 100
LOCI = {"L1": {"locus_id": "L1", "path": "src/a.py", "names": ["Thing"], "line": 5}}


def _read(path: str) -> bytes | None:
    return SOURCE if path == "src/a.py" else None


def _fact(*groups: list[str], locus: str | None = None, negated: bool = False, forbid: list[str] | None = None) -> dict[str, Any]:
    return {"fact_id": "F", "groups": [list(g) for g in groups], "locus": locus, "negated": negated, **({"forbid": forbid} if forbid else {})}


def test_the_selector_removes_only_the_hosts_search_limit_notice():
    assert sc.select(f"Answer.\n\n{LIMIT_NOTICE}") == "Answer." and sc.select("Answer.") == "Answer." and sc.select(None) is None


def test_a_citation_binds_its_path_and_symbol_in_one_clause_or_a_narrow_range():
    requirement = {"requirement_id": "R1", "any_of": ["symbol:src/a.py::Thing.method"]}
    assert sc.check_citation(requirement, "In src/a.py, `method` returns one.", _read) == sc.PASS
    assert sc.check_citation(requirement, "See src/a.py:6-7.", _read) == sc.PASS
    assert sc.check_citation(requirement, "See src/a.py.\nElsewhere, `method` returns one.", _read) == sc.FAIL  # symbol placed elsewhere
    assert sc.check_citation(requirement, "See src/a.py:1-100.", _read) == sc.FAIL  # a file-wide range is not a locus
    assert sc.check_citation(requirement, "See src/a.py:7-6.", _read) == sc.FAIL  # a reversed range
    assert sc.check_citation(requirement, "See src/a.py:1-2.", _read) == sc.FAIL  # an unrelated range
    assert sc.check_citation(requirement, "In src/a.py the method returns one.", _read) == sc.FAIL  # an ordinary word needs code form


def test_a_fact_is_a_relationship_inside_one_paragraph():
    assert sc.check_fact(_fact(["dense"], ["lexical"]), "It interleaves dense, then lexical.") == sc.PASS
    assert sc.check_fact(_fact(["dense"], ["lexical"]), "It starts with dense.\n\nLexical is a channel.") == sc.FAIL  # split across paragraphs
    assert sc.check_fact(_fact(["dense"], ["lexical"]), "dense only") == sc.FAIL
    assert sc.check_fact(_fact(["60"]), "line 160") == sc.FAIL and sc.check_fact(_fact(["40"]), "src/a.py:140") == sc.FAIL  # whole numbers only
    assert sc.check_fact({"fact_id": "F", "at_least": 2, "of": ["rank", "Thing"]}, "ranking Thing") == sc.FAIL


def test_a_negated_carrying_sentence_fails_unless_the_fact_is_a_negation():
    assert sc.check_fact(_fact(["dense"], ["first"]), "It does not put dense first.") == sc.FAIL
    assert sc.check_fact(_fact(["dense"], ["first"]), "Dense isn't first; lexical is.") == sc.FAIL
    assert sc.check_fact(_fact(["retriev"], negated=True), "It never retrieves the exception.") == sc.PASS
    assert sc.check_fact(_fact(["dense"], ["first"]), "Notably, dense comes first.") == sc.PASS  # `not` inside a word is no negation


def test_a_fact_is_tied_to_its_locus_and_rejects_forbidden_extras():
    assert sc.check_fact(_fact(["dense"], ["lexical"], locus="L1"), "`Thing` interleaves dense and lexical.", LOCI) == sc.PASS
    assert sc.check_fact(_fact(["dense"], ["lexical"], locus="L1"), "`Thing` is a class.\n\nIt interleaves dense and lexical.", LOCI) == sc.FAIL
    assert sc.check_fact(_fact(["dense"], ["lexical"], locus="L1"), "See src/a.py:4-6: dense and lexical.", LOCI) == sc.PASS  # a narrow range covers line 5
    assert sc.check_fact(_fact(["easy"], ["medium"], forbid=["summarizer"]), "Roles: easy, medium and summarizer.") == sc.FAIL


def test_a_cited_line_outside_its_file_or_a_reversed_range_is_prohibited():
    assert sc.check_prohibited("See src/a.py:6-7.", _read) == sc.PASS
    assert sc.check_prohibited("See src/a.py:7-6.", _read) == sc.FAIL
    assert sc.check_prohibited("See src/a.py:500.", _read) == sc.FAIL and sc.check_prohibited("See src/b.py.", _read) == sc.FAIL


def test_the_quote_control_needs_one_exact_block_or_an_explicit_refusal_with_no_code():
    case = BY_ID["QO4"]
    read = _reader(case["snapshot"])
    lines = read("src/optimus/acp/launch_gate.py").decode("utf-8").splitlines()[1122:1131]
    exact = "```python\n" + "\n".join(lines) + "\n```"
    quote, path = case["checks"]["quote"], "src/optimus/acp/launch_gate.py"
    assert sc.check_quote(quote, exact, path, read) == sc.PASS
    assert sc.check_quote(quote, exact.replace("\n", "\r\n"), path, read) == sc.PASS  # line endings only
    assert sc.check_quote(quote, "```python\n" + "\n".join(reversed(lines)) + "\n```", path, read) == sc.FAIL  # reordered lines
    assert sc.check_quote(quote, "```python\n" + "\n".join(lines[:-1]) + "\n```", path, read) == sc.FAIL  # incomplete
    assert sc.check_quote(quote, exact + "\n\n```python\ndef extra():\n```", path, read) == sc.FAIL  # a second block
    assert sc.check_quote(quote, exact + "\n\ndef invented():\n    return 1", path, read) == sc.FAIL  # unfenced code beside it
    assert sc.check_quote(quote, "The requested lines are unavailable to me.", path, read) == sc.PASS
    assert sc.check_quote(quote, "Unavailable, but roughly:\n```\ndef invented():\n```", path, read) == sc.FAIL
    assert sc.check_quote(quote, "The requested lines are unavailable; roughly:\ndef _project_child_env(environ):\n    return {}", path, read) == sc.FAIL  # unfenced code
    assert sc.check_quote(quote, "That is unavailable.", path, read) == sc.FAIL  # says nothing about the requested lines


# Written from the oracles and the source, not from the encoded checks (Codex attempt 2 finding 5). QO4 is a boundary in every arm.
ANSWERS = {
    "QR1": (
        "Finished request tasks are handled in src/optimus/acp/server.py, inside `AcpStreamServer.serve_ndjson`.\n\n"
        "Each request runs as a task created for `process_request`, and `add_done_callback(request_tasks.discard)` registers a done callback that only "
        "removes the finished task from the tracking set; it never retrieves the task's exception, so an error that escaped is lost silently."
    ),
    "QR2": (
        "Shutdown completes across three places.\n\n"
        "In src/optimus/mcp/client_disposition.py, `ClientMcpRuntime.close` runs its cleanup stages in turn and stops on the first stage that raises.\n\n"
        "In src/optimus/mcp/client_supervisor.py, `MCPAsyncSupervisor.close` does a bounded join, `join(timeout=5.0)`, and then marks itself dead even though "
        "its owner thread can remain alive.\n\n"
        "In src/optimus/acp/server.py, `serve_ndjson` calls the shutdown and never checks its result."
    ),
    "QR3": (
        "The launch entry point is src/optimus/acp/__main__.py `main`.\n\n"
        "In src/optimus/acp/bootstrap.py, `build_client_mcp_runtime` forwards just the agent's environment, so the captured system values stop being passed there; "
        "src/optimus/acp/subprocess_env.py `build_acp_subprocess_env` built that environment.\n\n"
        "Downstream, src/optimus/mcp/client_config.py `constructed_child_environ` reads os.environ for SystemRoot again when constructing the child, and "
        "`_resolve_stdio_command` reads PATHEXT from the ambient environment when resolving the command."
    ),
    "QR4": (
        "Trace records are written by src/optimus/acp/debug_trace.py `acp_debug_log`.\n\n"
        "In `acp_debug_log`, `redact_for_telemetry` runs outside the guarded write block, so a redaction failure can escape before the lock is taken.\n\n"
        "The callers in src/optimus/acp/server.py `serve_ndjson`, src/optimus/acp/spec.py `_handle_session_prompt` and "
        "src/optimus/agent/planning_loop.py `run_iteration` build the payload data eagerly, before `acp_debug_log` reaches its debug_trace_enabled check."
    ),
    "QB1": (
        "`SIGNATURE_SHARE` is 0.25, so signatures get a quarter of the optional room and bodies the rest.\n\n"
        "When the serialized required text exceeds the budget, the branch `if used > budget_tokens:` returns an empty pack and lists every required path in "
        "`missing_required`, so the pack is incomplete rather than smaller."
    ),
    "QB2": "`RRF_K` is the reciprocal-rank fusion constant: 60.\n\n`QUOTA` interleaves the two channels for the first places, starting with dense: dense 1, lexical 1, dense 2, lexical 2.",
    "QB3": "`MAX_ENTRIES` caps one page at 40 entries.\n\n`MAX_PAGE_BYTES` caps it at 12 * 1024 = 12,288 UTF-8 bytes, with the header, navigation and markers included.",
    "QB4": "`MAX_CONTEXT_CEILING_TOKENS` is 262,144 tokens, the total context ceiling with the output reserve counted once.\n\n`IMPLEMENTER_ROLES` is exactly easy, medium, complex and escalation.",
    "QO1": (
        "The module gates a launch on approval.\n\n"
        "`resolve_launch_candidate` gathers the configuration and the security identity of the launch into a `LaunchCandidate` that will be checked.\n\n"
        "`authorize_launch` validates that candidate against a durable approval or a one-shot (monotonic) grant and returns an `AuthorizedLaunch`."
    ),
    "QO2": "The importer works in two steps.\n\n`Importer.preview` reads the selected source and builds a preview before anything is written.\n\n`Importer.apply` applies only a confirmed preview, after it checks the source digest again.",
    "QO3": "The repository map ranks and renders files.\n\n`rank` scores files over the observed import edges between them.\n\n`build_repo_map` emits whole file entries, each with its symbols, within the character budget.",
}
CONTRADICTIONS = {
    "QR1": ANSWERS["QR1"].replace("it never retrieves the task's exception, so an error that escaped is lost silently", "it retrieves and logs the task's exception"),
    "QR2": ANSWERS["QR2"].replace("never checks its result", "checks its result and reports a failure"),
    "QR4": ANSWERS["QR4"].replace("runs outside the guarded write block, so a redaction failure can escape before the lock is taken", "runs inside the guarded write block"),
    "QB1": ANSWERS["QB1"].replace("returns an empty pack and lists every required path in `missing_required`", "trims the required files until they fit"),
    "QB2": ANSWERS["QB2"].replace("starting with dense: dense 1, lexical 1, dense 2, lexical 2", "starting with lexical: lexical 1, dense 1, lexical 2, dense 2"),
    "QB2-negated": "`RRF_K` is 60.\n\n`QUOTA` does not start with dense first. It starts with lexical.",  # Codex attempt 2's own example
    "QB3": ANSWERS["QB3"].replace("40 entries", "400 entries"),
    "QB4": ANSWERS["QB4"].replace("exactly easy, medium, complex and escalation", "easy, medium, complex, escalation and summarizer"),
    "QO2": ANSWERS["QO2"].replace("after it checks the source digest again", "without checking the source again").replace("before anything is written", "and writes it as it goes"),
}


@pytest.mark.parametrize("case_id", sorted(ANSWERS))
def test_every_answered_case_passes_an_independent_correct_answer_and_fails_non_answers(case_id):
    case = BY_ID[case_id]
    read = _reader(case["snapshot"])
    assert sc.score(case, ANSWERS[case_id], read)["verdict"] == sc.PASS, sc.score(case, ANSWERS[case_id], read)["checks"]
    paths = sorted({e.partition(":")[2].partition("::")[0] for r in case["checks"]["citations"] for e in r["any_of"]} | {f["path"] for f in case["required_files"]})
    hedge = f"{' '.join(paths)}: I could not inspect these files, so details are missing and this answer is incomplete."
    assert sc.score(case, hedge, read)["verdict"] == sc.FAIL
    keywords = " ".join(p for f in case["checks"]["facts"] for g in f.get("groups", []) for p in g)  # a bare list of every phrase, no locus
    assert sc.score(case, keywords, read)["verdict"] == sc.FAIL
    assert sc.score(case, case["task"], read)["verdict"] == sc.FAIL  # the question restated


@pytest.mark.parametrize("name", sorted(CONTRADICTIONS))
def test_an_answer_that_reverses_the_oracle_fails(name):
    case = BY_ID[name.partition("-")[0]]
    assert CONTRADICTIONS[name] != ANSWERS[case["case_id"]]
    assert sc.score(case, CONTRADICTIONS[name], _reader(case["snapshot"]))["verdict"] == sc.FAIL


def test_rows_score_their_status_before_their_text():
    case = BY_ID["QB1"]
    read = _reader(case["snapshot"])
    good = ANSWERS["QB1"]
    assert sc.score_row(case, "F", {"terminal": "settled", "sent": [{"finish_reason": "stop"}]}, good, read)["verdict"] == sc.PASS
    assert sc.score_row(case, "F", {"terminal": "settled", "sent": [{"finish_reason": "length"}]}, good, read)["verdict"] == sc.INCOMPLETE  # cut at the cap
    assert sc.score_row(case, "F", {"terminal": "failed", "stop_reason": "CHAT_SEARCH_LIMIT_REACHED", "sent": []}, good, read)["verdict"] == sc.INCOMPLETE
    assert sc.score_row(case, "F", {"terminal": "incomplete", "sent": [{"finish_reason": "stop"}]}, good, read)["verdict"] == sc.INCOMPLETE
    over = BY_ID["QB3"]
    refused = {"stop_reason": TOO_LARGE, "logical_requests": 0, "emitted_answer": False}
    assert sc.score_row(over, "B", refused, None, read)["verdict"] == sc.PASS
    assert sc.score_row(over, "B", {**refused, "logical_requests": 1}, None, read)["verdict"] == sc.FAIL
    assert sc.score_row(over, "B", {**refused, "stop_reason": "AGENT_SETUP_FAILED"}, None, read)["verdict"] == sc.FAIL


def test_qo4_is_a_boundary_in_every_arm_and_a_quote_on_its_zero_call_row_fails():
    case = BY_ID["QO4"]
    read = _reader(case["snapshot"])
    refused = {"stop_reason": TOO_LARGE, "logical_requests": 0, "emitted_answer": False}
    assert all(sc.score_row(case, arm, refused, None, read)["verdict"] == sc.PASS for arm in ("N", "B", "U", "F"))
    assert sc.score_row(case, "F", {**refused, "emitted_answer": True}, "```python\ndef _project_child_env():\n```", read)["verdict"] == sc.FAIL
