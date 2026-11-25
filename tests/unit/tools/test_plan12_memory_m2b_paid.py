"""Plan 12.14 Task 1 (CP1, after Codex round 122): the paid Q runner and scorer with zero paid calls.

The runner tests drive the real AgentRunner, the real route binder and the real in-process Gateway handler (tests.unit.agent.test_route_binding);
only the provider is scripted. The scorer tests use the frozen cases and their pinned snapshot blobs."""

from __future__ import annotations

import json
import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import optimus_gateway.responses as gateway_responses
from optimus.agent.index_turn import LIMIT_NOTICE
from tests.unit.agent.test_route_binding import STANDARD, InProcessGateway, Notices, ScriptedUpstream, _client, _policy
from tests.unit.optimus_gateway.model_policy_support import CAP, verified_snapshot
from tools.plan12_memory import m2b_paid as paid
from tools.plan12_memory import m2b_score as sc

ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads((ROOT / "reports/plan12-memory-m2b/cases.json").read_text(encoding="utf-8"))["paid_q"]["cases"]
BY_ID = {c["case_id"]: c for c in CASES}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway_responses, "_sleep", lambda seconds: None)


@pytest.fixture
def snapshot(tmp_path: Path):
    (tmp_path / "registry").mkdir()
    return verified_snapshot(tmp_path / "registry")


def _ceiling(attempts: int = 96, usd: str = "6.00") -> paid.Ceiling:
    return paid.Ceiling(attempts_max=attempts, usd_max=Decimal(usd), per_attempt_usd=Decimal("0.04608"))


def _row(tmp_path: Path, snapshot, *, upstream: ScriptedUpstream | None = None, allowance: int = 1, task: str = "What is x?", cap: int = CAP,
         approved_hash: str | None = None, ceiling: paid.Ceiling | None = None, bind: bool = True) -> tuple[dict[str, Any], InProcessGateway]:
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    gateway = InProcessGateway(snapshot, upstream or ScriptedUpstream(replies=["The answer."]))
    approved = paid.Approved(approved_hash or snapshot.effective_hash, estimate_request=len, output_cap=CAP)
    binder = _policy(snapshot, STANDARD, output_cap=cap).capture(session_id="s", turn_seq=1, deliver_notice=Notices()) if bind else None
    row = paid.run_one({"case_id": "QX", "task": task}, "N", position=1, gateway=_client(gateway), approved=approved, model=STANDARD, packer=None,
                       binder=binder, workspace=workspace, ceiling=ceiling or _ceiling(), allowance=allowance)
    row["expected_logical_requests"] = allowance
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


# --- the real runner, the real binder and the in-process Gateway ---------------------------------------------------------


def test_a_bound_request_is_settled_from_the_gateways_own_attempts(tmp_path, snapshot):
    row, gateway = _row(tmp_path, snapshot)
    assert paid.terminal(row)[0] == "settled" and row["logical_requests"] == 1 == len(gateway.payloads)
    [sent] = row["sent"]
    assert sent["route_request_id"] == gateway.payloads[0]["route_binding"]["request_id"] and sent["gateway_attempts"][0]["physical"]
    [attempt] = row["attempts"]
    assert attempt["gateway_request_id"] == row["host_receipts"][0]["gateway_request_id"] and attempt["cost_usd"] is not None


def test_a_bound_resend_counts_two_physical_attempts_against_the_ceiling(tmp_path, snapshot):
    from optimus_gateway.upstream_client import UpstreamAttemptFailure

    ceiling = _ceiling()
    row, _ = _row(tmp_path, snapshot, upstream=ScriptedUpstream(replies=["ok"], attempts=[UpstreamAttemptFailure("rejected", http_status=429), None]), ceiling=ceiling)
    assert row["logical_requests"] == 1 and len(row["attempts"]) == 2 and ceiling.attempts_used == 2
    assert [a["outcome"] for a in row["attempts"]] == ["rejected", "completed"] and paid.terminal(row)[0] == "settled"


def test_a_terminal_failure_after_a_send_keeps_its_attempts_and_is_not_settled(tmp_path, snapshot):
    from optimus_gateway.upstream_client import UpstreamAttemptFailure

    row, _ = _row(tmp_path, snapshot, upstream=ScriptedUpstream(attempts=[UpstreamAttemptFailure("not_sent"), UpstreamAttemptFailure("uncertain")]))
    assert row["logical_requests"] == 1 and row["stop_reason"] is not None
    assert [a["outcome"] for a in row["attempts"]] == ["uncertain"]  # not_sent never left: not a physical attempt
    assert paid.terminal(row)[0] in {"incomplete", "failed"}


@pytest.mark.parametrize("change, reason", [
    ({"bind": False}, "unbound"),
    ({"approved_hash": "0" * 64}, "approved composition"),
    ({"cap": CAP + 1}, "approved composition"),
    ({"task": "x" * 70_000}, "over the cap"),
    ({"allowance": 0}, "allowance"),
])
def test_the_guard_refuses_before_anything_is_sent(tmp_path, snapshot, change, reason):
    row, gateway = _row(tmp_path, snapshot, **change)
    assert gateway.payloads == [] and row["logical_requests"] == 0 and reason in (row["guard_refusal"] or "")
    assert paid.terminal(row)[0] == "incomplete"


def test_a_send_with_no_gateway_attempt_is_unknown(tmp_path, snapshot):
    row, _ = _row(tmp_path, snapshot)
    row["sent"][0]["gateway_attempts"] = []  # a reply that reported no attempt
    row["attempts"] = paid.physical_attempts(row["sent"], row["host_receipts"])
    assert len(row["attempts"]) == 2 and all(a["cost_usd"] is None for a in row["attempts"]) and paid.terminal(row)[0] == "incomplete"


def test_a_refused_row_sends_nothing_through_the_real_runner(tmp_path, snapshot):
    """N on an oversized named file: today's context refuses before dispatch."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "big.py").write_text("#" * 20_000 + "\n", encoding="utf-8")
    row, gateway = _row(tmp_path, snapshot, allowance=0, task='Summarize "big.py"')
    assert gateway.payloads == [] and row["logical_requests"] == 0 and row["guard_refusal"] is None
    assert row["stop_reason"] == "REQUIRED_WORKSPACE_FILE_TOO_LARGE" and paid.terminal(row)[0] == "expected_zero_call"


def test_the_run_stops_at_the_first_row_that_is_not_settled(tmp_path, snapshot):
    from optimus_gateway.upstream_client import UpstreamAttemptFailure

    workspace = tmp_path / "ws"
    workspace.mkdir()
    gateway = InProcessGateway(snapshot, ScriptedUpstream(attempts=[UpstreamAttemptFailure("uncertain"), UpstreamAttemptFailure("uncertain")]))
    written: list[Any] = []
    answers: list[Any] = []
    report = paid.run(CASES, u_equals_b=True, outline_available=True, gateway=_client(gateway), approved=paid.Approved(snapshot.effective_hash, estimate_request=len, output_cap=CAP),
                      model=STANDARD, packer_for=lambda _c, _a: None,
                      binder_for=lambda _c, _a: _policy(snapshot, STANDARD, output_cap=CAP).capture(session_id="s", turn_seq=1, deliver_notice=Notices()),
                      workspace_for=lambda _c: workspace, ceiling=_ceiling(), write=written.append, write_answers=answers.append)
    assert len(report["rows"]) == 1 and report["stopped"]["at"] == ["QR1", "N"] and len(gateway.payloads) == 1
    assert "answer" not in report["rows"][0] and report["rows"][0]["terminal"] in {"incomplete", "failed"}


def test_a_receipt_row_keeps_every_reported_field():
    from datetime import UTC, datetime

    from optimus.gateway.models import GatewayUsage
    from optimus.usage.turn_settlement import StageReceipt

    usage = GatewayUsage(gateway_request_id="g1", provider="anthropic", billing_units=0, cost_usd=Decimal("0.01"), input_tokens=1000, output_tokens=100, cached_tokens=600,
                         model_version="v", native_unit="tokens")
    receipt = StageReceipt(session_id=None, turn_id="t", stage="answer", attempt_id="a1", gateway_request_id="g1", outcome="completed",
                           reported_cost_usd=Decimal("0.01"), recorded_at=datetime.now(UTC), gateway_usage=usage)
    row = paid.receipt_row(receipt)
    assert row["repriced_uncached_usd"] == "0.00075" and row["cache_write_tokens"] == "UNKNOWN" and row["post_teardown"] is False
    assert row["usage"]["model_version"] == "v" and row["usage"]["native_unit"] == "tokens" and row["recorded_at"]


# --- the scorer -----------------------------------------------------------------------------------------------------------


def _reader(snapshot: str):
    def read(path: str) -> bytes | None:
        done = subprocess.run(["git", "-C", str(ROOT), "cat-file", "blob", f"{snapshot.removeprefix('git:')}:{path}"], capture_output=True)
        return done.stdout if done.returncode == 0 else None

    return read


SOURCE = b"def outer():\n    pass\n\n\nclass Thing:\n    def method(self):\n        return 1\n" + b"\n" * 100


def _read(path: str) -> bytes | None:
    return SOURCE if path == "src/a.py" else None


def test_the_selector_removes_only_the_hosts_search_limit_notice():
    assert sc.select(f"Answer.\n\n{LIMIT_NOTICE}") == "Answer." and sc.select("Answer.") == "Answer." and sc.select(None) is None


def test_a_citation_binds_its_path_and_symbol_in_one_clause_or_a_narrow_range():
    requirement = {"requirement_id": "R1", "any_of": ["symbol:src/a.py::Thing.method"]}
    assert sc.check_citation(requirement, "In src/a.py, `method` returns one.", _read) == sc.PASS
    assert sc.check_citation(requirement, "See src/a.py:6-7.", _read) == sc.PASS
    assert sc.check_citation(requirement, "See src/a.py.\nElsewhere, `method` returns one.", _read) == sc.FAIL  # symbol placed elsewhere
    assert sc.check_citation(requirement, "See src/a.py:1-100.", _read) == sc.FAIL  # a file-wide range is not a locus
    assert sc.check_citation(requirement, "See src/a.py:1-2.", _read) == sc.FAIL  # an unrelated range
    assert sc.check_citation(requirement, "In src/a.py the method returns one.", _read) == sc.FAIL  # an ordinary word needs code form


def test_facts_need_every_group_and_whole_numbers():
    assert sc.check_fact({"fact_id": "F", "groups": [["dense"], ["lexical"]]}, "dense, then lexical") == sc.PASS
    assert sc.check_fact({"fact_id": "F", "groups": [["dense"], ["lexical"]]}, "dense only") == sc.FAIL
    assert sc.check_fact({"fact_id": "F", "groups": [["60"]]}, "line 160") == sc.FAIL and sc.check_fact({"fact_id": "F", "groups": [["40"]]}, "src/a.py:140") == sc.FAIL
    assert sc.check_fact({"fact_id": "F", "at_least": 2, "of": ["rank", "Thing"]}, "ranking Thing") == sc.FAIL


def test_the_quote_control_needs_the_exact_contiguous_block_or_an_explicit_refusal():
    case = BY_ID["QO4"]
    read = _reader(case["snapshot"])
    lines = read("src/optimus/acp/launch_gate.py").decode("utf-8").splitlines()[1122:1131]
    exact = "```python\n" + "\n".join(lines) + "\n```"
    quote, path = case["checks"]["quote"], "src/optimus/acp/launch_gate.py"
    assert sc.check_quote(quote, exact, path, read) == sc.PASS
    assert sc.check_quote(quote, "```python\n" + "\n".join(reversed(lines)) + "\n```", path, read) == sc.FAIL  # reordered lines
    assert sc.check_quote(quote, "The requested lines are unavailable to me.", path, read) == sc.PASS
    assert sc.check_quote(quote, "Unavailable, but roughly:\n```\ndef invented():\n```", path, read) == sc.FAIL


def _correct_answer(case: dict) -> str:
    """A reply that meets every check: each citation as path plus code-form symbol in one clause, each locus by name, one phrase per group."""
    parts = []
    for requirement in case["checks"]["citations"]:
        path, _, symbol = requirement["any_of"][0].partition(":")[2].partition("::")
        parts.append(f"In {path}, `{symbol.rsplit('.', 1)[-1]}` does it." if symbol else f"See {path}.")
    for locus in case["checks"]["loci"]:
        parts.append(f"The locus is `{locus['names'][0]}`.")
    for fact in case["checks"]["facts"]:
        parts.append((" ".join(group[0] for group in fact["groups"]) if "groups" in fact else " ".join(fact["of"][: fact["at_least"]])) + ".")
    return " ".join(parts)


@pytest.mark.parametrize("case", [c for c in CASES if c["case_id"] != "QO4"], ids=lambda c: c["case_id"])
def test_every_answered_case_passes_its_correct_answer_and_fails_non_answers(case):
    read = _reader(case["snapshot"])
    assert sc.score(case, _correct_answer(case), read)["verdict"] == sc.PASS
    paths = sorted({e.partition(":")[2].partition("::")[0] for r in case["checks"]["citations"] for e in r["any_of"]} | {f["path"] for f in case["required_files"]})
    hedge = f"{' '.join(paths)}: I could not inspect these files, so details are missing and this answer is incomplete."
    assert sc.score(case, hedge, read)["verdict"] == sc.FAIL
    keywords = " ".join(p for f in case["checks"]["facts"] for g in f.get("groups", []) for p in g)  # a bare list of every phrase, no citation
    assert sc.score(case, keywords, read)["verdict"] == sc.FAIL
    assert sc.score(case, case["task"], read)["verdict"] == sc.FAIL  # the question restated


def test_a_contradicting_answer_fails_where_the_check_encodes_the_relationship():
    case = BY_ID["QR1"]
    read = _reader(case["snapshot"])
    contradicting = _correct_answer(case).replace("never retriev", "always retrieves")
    assert sc.score(case, contradicting, read)["verdict"] == sc.FAIL


def test_rows_score_their_status_before_their_text():
    case = BY_ID["QB1"]
    read = _reader(case["snapshot"])
    good = _correct_answer(case)
    assert sc.score_row(case, "F", {"stop_reason": None, "sent": [{"finish_reason": "stop"}]}, good, read)["verdict"] == sc.PASS
    assert sc.score_row(case, "F", {"stop_reason": None, "sent": [{"finish_reason": "length"}]}, good, read)["verdict"] == sc.INCOMPLETE  # cut at the cap
    assert sc.score_row(case, "F", {"stop_reason": "CHAT_SEARCH_LIMIT_REACHED", "sent": []}, good, read)["verdict"] == sc.INCOMPLETE
    over = BY_ID["QB3"]
    assert sc.score_row(over, "B", {"stop_reason": "REQUIRED_WORKSPACE_FILE_TOO_LARGE", "logical_requests": 0}, None, read)["verdict"] == sc.PASS
    assert sc.score_row(over, "B", {"stop_reason": "REQUIRED_WORKSPACE_FILE_TOO_LARGE", "logical_requests": 1}, None, read)["verdict"] == sc.FAIL
