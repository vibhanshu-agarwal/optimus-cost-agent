"""Plan 12.14 Task 1: the paid Q runner and scorer, with zero paid calls. A scripted Gateway client is the only client the runner holds."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from optimus.agent.index_turn import LIMIT_NOTICE
from optimus.gateway.models import GatewayResponse, GatewayUsage
from tools.plan12_memory import m2b_paid as paid
from tools.plan12_memory import m2b_score as sc

ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads((ROOT / "reports/plan12-memory-m2b/cases.json").read_text(encoding="utf-8"))["paid_q"]["cases"]


class Scripted:
    def __init__(self, replies: list[str], cost: str | None = "0.001") -> None:
        self.replies, self.cost, self.inputs = list(replies), cost, []

    def create_response(self, *, model: str, input_text: str, metadata: Any = None, route_binding: Any = None) -> GatewayResponse:
        self.inputs.append(input_text)
        number = len(self.inputs)
        usage = GatewayUsage(gateway_request_id=f"q-{number}", provider="local-script", billing_units=0, cost_usd=None if self.cost is None else Decimal(self.cost))
        return GatewayResponse(response_id=f"q-{number}", output_text=self.replies.pop(0) if self.replies else "done", gateway_usage=usage, raw={})


# --- schedule and expectations -------------------------------------------------------------------------------------------


def test_the_schedule_is_each_categorys_four_orders_and_drops_u_when_it_equals_b():
    full = paid.schedule(CASES, u_equals_b=False)
    assert len(full) == 48 and [p for _c, _a, p in full] == list(range(1, 49))
    assert [(c, a) for c, a, _p in full[:4]] == [("QR1", "N"), ("QR1", "B"), ("QR1", "U"), ("QR1", "F")]
    assert [(c, a) for c, a, _p in full[4:8]] == [("QR2", "B"), ("QR2", "U"), ("QR2", "F"), ("QR2", "N")]
    aliased = paid.schedule(CASES, u_equals_b=True)
    assert len(aliased) == 36 and all(arm != "U" for _c, arm, _p in aliased)


def test_expected_calls_follow_the_predeclared_refusals():
    with_outline = paid.expected_calls(CASES, u_equals_b=True, outline_available=True)
    assert sum(with_outline.values()) == 30  # 12 N + 7 B + 11 F
    refused = sorted(key for key, calls in with_outline.items() if calls == 0)
    assert refused == [("QB3", "B"), ("QB4", "B"), ("QO1", "B"), ("QO2", "B"), ("QO4", "B"), ("QO4", "F")]
    assert sum(paid.expected_calls(CASES, u_equals_b=True, outline_available=False).values()) == 28


# --- the ceiling ---------------------------------------------------------------------------------------------------------


def test_the_ceiling_reserves_the_route_attempts_before_each_request():
    ceiling = paid.Ceiling(attempts_max=4, usd_max=Decimal("1"), per_attempt_usd=Decimal("0.1"))
    ceiling.reserve()
    ceiling.settle([{"cost_usd": "0.05"}, {"cost_usd": "0.05"}])  # a resend counts as two physical attempts
    ceiling.reserve()
    ceiling.settle([{"cost_usd": "0.05"}])
    with pytest.raises(paid.CapRefused):
        ceiling.reserve()  # 3 used + 2 > 4


def test_unknown_costs_are_reserved_at_the_worst_case():
    ceiling = paid.Ceiling(attempts_max=96, usd_max=Decimal("0.25"), per_attempt_usd=Decimal("0.1"))
    ceiling.reserve()  # 0.1 x 2 = 0.20 is within
    ceiling.settle([{"cost_usd": None}])
    with pytest.raises(paid.CapRefused):
        ceiling.reserve()  # an unknown attempt is priced at the worst case: 0.1 x (1 + 2) = 0.30 is not
    assert ceiling.unknown_attempts == 1


# --- the real runner, engine absent (arm N), zero tools -------------------------------------------------------------------


def test_an_n_request_goes_through_the_real_runner_once_and_is_recorded(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    gateway = Scripted(["The answer cites src/x.py."])
    ceiling = paid.Ceiling(attempts_max=96, usd_max=Decimal("6.00"), per_attempt_usd=Decimal("0.04608"))
    case = {"case_id": "QB9", "task": "What is x?", "kind": "ordinary-fit"}
    row = paid.run_one(case, "N", position=1, gateway=gateway, model="anthropic/claude-haiku-5.5", packer=None, binder=None, workspace=tmp_path, ceiling=ceiling)
    assert row["logical_requests"] == 1 == len(gateway.inputs) and row["answer"].startswith("The answer")
    assert row["sent"][0]["input_bytes"] == len(gateway.inputs[0].encode("utf-8"))


def test_the_run_stops_at_an_unknown_cost_and_never_replaces_a_request(tmp_path):
    gateway = Scripted(["first"], cost=None)
    ceiling = paid.Ceiling(attempts_max=96, usd_max=Decimal("6.00"), per_attempt_usd=Decimal("0.04608"))
    written: list[Any] = []
    report = paid.run(CASES, u_equals_b=True, outline_available=True, gateway=gateway, model="anthropic/claude-haiku-5.5",
                      packer_for=lambda _c, _a: None, binder_for=lambda _c, _a: None, workspace_for=lambda _c: tmp_path, ceiling=ceiling, write=written.append, write_answers=lambda _a: None)
    assert len(gateway.inputs) == 1 and report["stopped"]["reason"] == "an attempt's cost is unknown"
    assert "answer" not in report["rows"][0] and report["rows"][0]["answer_sha256"].startswith("hex:")


def test_the_run_stops_when_the_ceiling_cannot_reserve(tmp_path):
    gateway = Scripted([])
    ceiling = paid.Ceiling(attempts_max=3, usd_max=Decimal("6.00"), per_attempt_usd=Decimal("0.04608"))
    report = paid.run(CASES, u_equals_b=True, outline_available=True, gateway=gateway, model="anthropic/claude-haiku-5.5",
                      packer_for=lambda _c, _a: None, binder_for=lambda _c, _a: None, workspace_for=lambda _c: tmp_path, ceiling=ceiling, write=lambda _r: None, write_answers=lambda _a: None)
    # QR1 N and B each send one request (one attempt each); F would need 2 more than the 1 left of 3
    assert len(gateway.inputs) == 2 and report["stopped"]["at"] == ["QR1", "F"] and "cannot reserve" in report["stopped"]["reason"]
    assert report["ceiling"]["attempts_used"] == 2 and [r["arm"] for r in report["rows"]] == ["N", "B"]


# --- the scorer and selector --------------------------------------------------------------------------------------------


SOURCE = b"def outer():\n    pass\n\n\nclass Thing:\n    def method(self):\n        return 1\n"


def _read(path: str) -> bytes | None:
    return SOURCE if path == "src/a.py" else None


def test_the_selector_removes_only_the_hosts_search_limit_notice():
    assert sc.select(f"Answer.\n\n{LIMIT_NOTICE}") == "Answer."
    assert sc.select("Answer.") == "Answer." and sc.select(None) is None


def test_a_citation_passes_by_path_and_symbol_or_an_overlapping_range():
    requirement = {"requirement_id": "R1", "any_of": ["symbol:src/a.py::Thing.method"]}
    assert sc.check_citation(requirement, "See src/a.py, method.", _read) == sc.PASS
    assert sc.check_citation(requirement, "See src/a.py:6-7.", _read) == sc.PASS
    assert sc.check_citation(requirement, "See src/a.py:1-2.", _read) == sc.FAIL
    assert sc.check_citation(requirement, "See method.", _read) == sc.FAIL


def test_facts_and_prohibited_citations():
    assert sc.check_fact({"fact_id": "F1", "any_of": ["0.25", "quarter"]}, "A Quarter of it") == sc.PASS
    assert sc.check_fact({"fact_id": "F2", "all_of": ["dense", "lexical"]}, "dense only") == sc.FAIL
    assert sc.check_fact({"fact_id": "F3", "at_least": 2, "of": ["Thing", "outer", "rank"]}, "Thing and outer") == sc.PASS
    assert sc.check_fact({"fact_id": "F3", "at_least": 2, "of": ["rank", "Thing"]}, "ranking Thing") == sc.FAIL  # whole words
    assert sc.check_prohibited("src/a.py:7", _read) == sc.PASS
    assert sc.check_prohibited("src/a.py:99", _read) == sc.FAIL and sc.check_prohibited("src/missing.py", _read) == sc.FAIL


def test_a_quote_must_be_verbatim_and_either_complete_or_disclosed():
    quote = {"target_lines": [6, 7], "refusal_phrases": ["not included"]}
    complete = "```python\n    def method(self):\n        return 1\n```"
    assert sc.check_quote(quote, complete, "src/a.py", _read) == sc.PASS
    assert sc.check_quote(quote, "The file was not included.", "src/a.py", _read) == sc.PASS
    assert sc.check_quote(quote, "```\ndef invented():\n```", "src/a.py", _read) == sc.FAIL
    assert sc.check_quote(quote, "Here it is.", "src/a.py", _read) == sc.FAIL


def test_the_verdict_is_pass_only_when_every_check_passes_and_incomplete_on_unknown():
    case = {"case_id": "X", "checks": {"citations": [{"requirement_id": "R1", "any_of": ["path:src/a.py"]}], "facts": [{"fact_id": "F1", "any_of": ["thing"]}], "quote": None},
            "required_files": [{"path": "src/a.py"}]}
    assert sc.score(case, "src/a.py has Thing", _read)["verdict"] == sc.PASS
    assert sc.score(case, "src/a.py only", _read)["verdict"] == sc.FAIL
    assert sc.score(case, None, _read)["verdict"] == "INCOMPLETE"


def test_every_frozen_case_scores_its_own_correct_answer_and_rejects_an_empty_one():
    """Each paid case's checks are satisfiable from the snapshot: a reply naming every requirement and fact passes; a blank one fails."""
    import subprocess

    def reader(snapshot: str):
        def read(path: str) -> bytes | None:
            done = subprocess.run(["git", "-C", str(ROOT), "cat-file", "blob", f"{snapshot.removeprefix('git:')}:{path}"], capture_output=True)
            return done.stdout if done.returncode == 0 else None

        return read

    for case in CASES:
        parts = []
        for requirement in case["checks"]["citations"]:
            kind, _, rest = requirement["any_of"][0].partition(":")
            path, _, symbol = rest.partition("::")
            parts.append(f"{path} {symbol.rsplit('.', 1)[-1]}")
        for fact in case["checks"]["facts"]:
            parts.append(" ".join(fact.get("all_of") or fact.get("any_of", [])[:1] or fact["of"][: fact["at_least"]]))
        if case["checks"]["quote"] is not None:
            parts.append("The requested lines were not given to me.")
        read = reader(case["snapshot"])
        assert sc.score(case, " ".join(parts), read)["verdict"] == sc.PASS, case["case_id"]
        assert sc.score(case, "", read)["verdict"] == sc.FAIL, case["case_id"]
