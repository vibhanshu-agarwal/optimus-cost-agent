"""Plan 12.14 Task 1 (CP1, after Codex round 122 attempt 2): the paid Q runner and scorer with zero paid calls.

The runner tests drive the real AgentRunner, the real route binder and the real in-process Gateway handler (tests.unit.agent.test_route_binding);
only the provider is scripted. The scorer tests use the frozen cases, their pinned snapshot blobs, and answers written independently of the
encoded checks: one correct answer per answered case and a contradicting variant of each relationship the oracle states."""

from __future__ import annotations

import hashlib
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
CASES_SHA = "hex:" + hashlib.sha256((ROOT / "reports/plan12-memory-m2b/cases.json").read_bytes()).hexdigest()
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
    return [{"route_request_id": "r1", "receipt_base": "m2b-q-QX-N:answer:1:1",
             "gateway_attempts": [{"attempt": n, "gateway_request_id": g, "outcome": o, "physical": o in paid.PHYSICAL} for n, g, o in attempts]}]


def _receipt(ordinal: int, gateway_id: str | None, outcome: str, cost: str | None) -> dict[str, Any]:
    return {"attempt_id": f"m2b-q-QX-N:answer:1:1:{ordinal}", "gateway_request_id": gateway_id, "outcome": outcome, "cost_usd": cost}


def test_reconciliation_keys_each_attempt_by_gateway_id_ordinal_and_disposition():
    """A rejected and a completed attempt that repeat one Gateway id each keep their own receipt's charge."""
    out = paid.reconcile(_sent((1, "g1", "rejected"), (2, "g1", "completed")), [_receipt(2, "g1", "completed", "0.01"), _receipt(1, "g1", "rejected", "0")])
    assert out["problems"] == [] and [a["cost_usd"] for a in out["attempts"]] == ["0", "0.01"]


@pytest.mark.parametrize("receipts, problem, unclaimed", [
    ([], "no matching host receipt", 0),  # missing
    ([_receipt(1, "g1", "rejected", "0")], "no matching host receipt", 0),  # partial: the completed attempt's receipt is missing
    ([_receipt(1, "g1", "rejected", "0"), _receipt(2, "g1", "completed", "0.01"), _receipt(2, "g1", "completed", "0.01")], "2 host receipts match (charge unknown)", 0),  # duplicates kept, flagged
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


def test_a_row_whose_run_raised_is_incomplete_even_when_its_receipts_reconcile():
    row = {"guard_refusal": None, "error": "AttemptIntegrityError", "reconciliation": {"problems": []}, "logical_requests": 1, "expected_logical_requests": 1,
           "attempts": [{"cost_usd": "0.01"}], "stop_reason": None, "emitted_answer": False}
    assert paid.terminal(row) == ("incomplete", "the run raised AttemptIntegrityError")


def test_duplicate_receipts_are_kept_and_flagged_and_leave_the_charge_unknown():
    """Fable 5.2's CP1 simplification: only a clean one-to-one match carries an amount. Two receipts for one attempt, identical or not, are
    kept, flagged and priced at the worst case; the row is incomplete and the Gateway ledger is the authority."""
    for second in ("0.01", "0.02"):
        out = paid.reconcile(_sent((1, "g1", "completed")), [_receipt(1, "g1", "completed", "0.01"), _receipt(1, "g1", "completed", second)])
        assert out["problems"] == ["r1 attempt 1: 2 host receipts match (charge unknown)"] and out["attempts"][0]["cost_usd"] is None
        assert len(out["attempts"][0]["receipt_attempt_ids"]) == 2 and set(out) == {"attempts", "unclaimed_receipts", "problems"}
        ceiling = _ceiling()
        ceiling.settle(out["attempts"])
        assert (ceiling.attempts_used, ceiling.unknown_attempts, ceiling.usd_settled) == (1, 1, Decimal(0))
        assert paid.settlement(out["attempts"], out["problems"])["usd_actual"] == "UNKNOWN"


def test_an_unclaimed_receipt_is_kept_and_flagged_and_never_charged():
    """Fable 5.2's CP1 simplification: there is no money-only path. A receipt on no attempt is a problem; only the matched attempt settles."""
    foreign = {**_receipt(1, "g9", "completed", "0.02"), "attempt_id": "m2b-q-QX-N:answer:1:2:1"}
    out = paid.reconcile(_sent((1, "g1", "completed")), [_receipt(1, "g1", "completed", "0.01"), foreign, dict(foreign)])
    assert len(out["unclaimed_receipts"]) == 2 and len(out["problems"]) == 2 and out["attempts"][0]["cost_usd"] == "0.01"
    ceiling = _ceiling()
    ceiling.settle(out["attempts"])
    assert (ceiling.attempts_used, ceiling.unknown_attempts, ceiling.usd_settled) == (1, 0, Decimal("0.01"))
    assert paid.settlement(out["attempts"], out["problems"])["usd_actual"] == "UNKNOWN", "a flagged row's actual cost is the ledger's to say"


def test_a_conflicting_copy_of_a_matched_receipt_is_flagged_and_the_row_unknown():
    """A matched receipt and a copy naming another route request: the copy is kept and flagged, so the row's actual cost is UNKNOWN."""
    match = _receipt(1, "g1", "completed", "0.01")
    out = paid.reconcile(_sent((1, "g1", "completed")), [match, {**match, "cost_usd": "0.05", "usage": {"route_request_id": "r-other"}}])
    assert out["attempts"][0]["cost_usd"] == "0.01" and len(out["unclaimed_receipts"]) == 1 and out["problems"]
    assert paid.settlement(out["attempts"], out["problems"]) == {"attempts": 1, "attempts_unknown_cost": 0, "usd_actual": "UNKNOWN"}


def test_a_send_without_its_host_request_identity_matches_nothing():
    unbound = [{"route_request_id": "r1", "gateway_attempts": [{"attempt": 1, "gateway_request_id": "g1", "outcome": "completed", "physical": True}]}]
    out = paid.reconcile(unbound, [_receipt(1, "g1", "completed", "0.01")])
    assert out["attempts"][0]["cost_usd"] is None and out["problems"][0] == "r1: no host request identity recorded at dispatch"


def test_a_send_with_no_gateway_attempt_reserves_its_unknown_attempts_once():
    """Codex CP1 attempt 4 finding 4: the host's own uncertain record of a transport loss is no third attempt."""
    lost = [{"route_request_id": "r1", "receipt_base": "m2b-q-QX-N:answer:1:1", "gateway_attempts": []}]
    out = paid.reconcile(lost, [{"attempt_id": "m2b-q-QX-N:answer:1:1", "gateway_request_id": None, "outcome": "uncertain", "cost_usd": None}])
    assert len(out["attempts"]) == 2 and out["unclaimed_receipts"] == [] and out["attempts"][0]["receipt_attempt_ids"] == ["m2b-q-QX-N:answer:1:1"]
    ceiling = _ceiling()
    ceiling.settle(out["attempts"])
    assert (ceiling.attempts_used, ceiling.unknown_attempts, ceiling.usd_settled) == (2, 2, Decimal(0))
    reported = paid.reconcile(lost, [{"attempt_id": "m2b-q-QX-N:answer:1:1", "gateway_request_id": "g1", "outcome": "completed", "cost_usd": "0.01"}])
    assert len(reported["attempts"]) == 2 and reported["unclaimed_receipts"] == [] and reported["problems"]
    ceiling = _ceiling()
    ceiling.settle(reported["attempts"])  # the reported amount is kept on the row, never settled: two worst-case attempts bound it
    assert (ceiling.attempts_used, ceiling.unknown_attempts, ceiling.usd_settled) == (2, 2, Decimal(0))


def test_a_receipt_must_belong_to_this_host_request():
    """Codex CP1 attempts 3-4 finding 4: the same Gateway id, ordinal and disposition under any other host request never match."""
    for other in ("m2b-q-QY-N:answer:1:1:1", "m2b-q-QX-N:answer:2:1:1", "m2b-q-QX-N:answer:1:2:1"):  # another run, turn, or wire attempt
        stray = {**_receipt(1, "g1", "completed", "0.01"), "attempt_id": other}
        assert paid.reconcile(_sent((1, "g1", "completed")), [stray])["attempts"][0]["cost_usd"] is None, other
    wrong_attempt = {**_receipt(1, "g1", "completed", "0.01"), "usage": {"attempt": 2}}
    assert paid.reconcile(_sent((1, "g1", "completed")), [wrong_attempt])["attempts"][0]["cost_usd"] is None
    conflicting = {**_receipt(1, "g1", "completed", "0.01"), "usage": {"route_request_id": "r-other"}}
    assert paid.reconcile(_sent((1, "g1", "completed")), [conflicting])["attempts"][0]["cost_usd"] is None
    agreeing = {**_receipt(1, "g1", "completed", "0.01"), "usage": {"route_request_id": "r1"}}
    assert paid.reconcile(_sent((1, "g1", "completed")), [agreeing])["problems"] == []
    two_sends = [*_sent((1, "g1", "completed")), {"route_request_id": "r2", "receipt_base": "m2b-q-QX-N:answer:1:2",
                                                     "gateway_attempts": [{"attempt": 1, "gateway_request_id": "g2", "outcome": "completed", "physical": True}]}]
    shared = [_receipt(1, "g1", "completed", "0.01"), _receipt(1, "g2", "completed", "0.01")]  # both under one request part
    out = paid.reconcile(two_sends, shared)
    assert out["attempts"][1]["cost_usd"] is None and out["problems"] == ["r2 attempt 1: no matching host receipt", "host receipt m2b-q-QX-N:answer:1:1:1 (completed) matches no Gateway attempt"]
    own = [_receipt(1, "g1", "completed", "0.01"), {**_receipt(1, "g2", "completed", "0.01"), "attempt_id": "m2b-q-QX-N:answer:1:2:1"}]
    assert paid.reconcile(two_sends, own)["problems"] == []


def test_a_completed_attempt_the_host_records_as_uncertain_keeps_both_dispositions_and_an_unknown_charge():
    out = paid.reconcile(_sent((1, "g1", "completed")), [_receipt(1, "g1", "uncertain", None)])
    [attempt] = out["attempts"]
    assert out["problems"] == [] and attempt["outcome"] == "completed" and attempt["receipt_outcomes"] == ["uncertain"] and attempt["cost_usd"] is None


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
                           reported_cost_usd=Decimal("0.01"), recorded_at=datetime.now(UTC), gateway_usage=usage, role="easy", quantizations=("fp8",),
                           strategy="s", revision_digest="d")
    row = paid.receipt_row(receipt)
    assert row["repriced_uncached_usd"] == "0.00075" and row["cache_write_tokens"] == "UNKNOWN" and row["post_teardown"] is False
    usage_row = row.get("usage") or {}
    assert usage_row.get("model_version") == "v" and usage_row.get("native_unit") == "tokens" and usage_row.get("total_tokens") == 1100 and row.get("recorded_at")
    assert row.get("role") == "easy" and row.get("quantizations") == ["fp8"] and row.get("strategy") == "s" and row.get("revision_digest") == "d"
    assert set(row) >= {f for f in StageReceipt.__slots__ if f not in {"gateway_usage", "reported_cost_usd"}} and set(row["usage"]) == set(GatewayUsage.model_fields)


# --- the real runner, the real binder and the in-process Gateway ---------------------------------------------------------


def test_a_bound_request_is_settled_from_the_gateways_own_attempts(tmp_path, snapshot):
    row, gateway = _row(tmp_path, snapshot)
    assert paid.terminal(row)[0] == "settled" and row["logical_requests"] == 1 == len(gateway.payloads) and row["reconciliation"]["problems"] == []
    [sent] = row["sent"]
    assert sent["route_request_id"] == gateway.payloads[0]["route_binding"]["request_id"] and sent["gateway_attempts"][0]["physical"]
    [attempt] = row["attempts"]
    assert attempt["gateway_request_id"] == row["host_receipts"][0]["gateway_request_id"] and attempt["cost_usd"] is not None
    assert row["settlement"] == {"attempts": 1, "attempts_unknown_cost": 0, "usd_actual": attempt["cost_usd"]}


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
    change = dict(change)
    ceiling = change.pop("ceiling", None) or _ceiling()
    row, gateway = _row(tmp_path, snapshot, ceiling=ceiling, **change)
    assert gateway.payloads == [] and row["logical_requests"] == 0 and reason in (row["guard_refusal"] or "")
    assert paid.terminal(row)[0] == "incomplete"
    # the host's own record of the refused request is kept, never charged (Codex CP1 attempt 3 finding 3)
    assert row["attempts"] == [] and (ceiling.attempts_used, ceiling.unknown_attempts, ceiling.usd_settled) == (0, 0, Decimal(0))
    assert len(row["reconciliation"]["unforwarded_receipt_ids"]) == len(row["host_receipts"])


def test_a_row_sends_at_most_once(tmp_path, snapshot):
    with pytest.raises(ValueError, match="at most one send per row"):
        _row(tmp_path, snapshot, allowance=2)


class _Recording:
    """The real Gateway client, each request's arguments kept so a later send can be attempted with them."""

    def __init__(self, inner: Any) -> None:
        self.inner, self.calls = inner, []

    def create_response(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.inner.create_response(**kwargs)


def test_a_guard_allows_at_most_one_send():
    """Fable 5.2's CP1 simplification: the intra-row multi-send path is deleted, so no Guard exists that could send twice."""
    for allowance in (2, -1):
        with pytest.raises(ValueError, match="at most one send per row"):
            paid.Guard(object(), None, _ceiling(), allowance=allowance)


@pytest.mark.parametrize("lose", ["all", "the completed attempt's"])
def test_a_missing_or_partial_receipt_set_makes_the_row_incomplete_and_stops_the_run(tmp_path, snapshot, lose):
    """The row after a send whose receipts do not reconcile never runs: the row is incomplete and the run stops there."""
    from optimus_gateway.upstream_client import UpstreamAttemptFailure

    workspace = tmp_path / "ws"
    workspace.mkdir()
    gateway = InProcessGateway(snapshot, ScriptedUpstream(replies=["ok", "again"], attempts=[UpstreamAttemptFailure("rejected", http_status=429), None, None]))
    rows: list[dict[str, Any]] = []
    real_run_one = paid.run_one

    def losing_run_one(*args: Any, **kwargs: Any) -> dict[str, Any]:
        row = real_run_one(*args, **kwargs)
        if not rows:  # the first row's receipt set is lost after the fact, as a dropped sink would
            keep = 0 if lose == "all" else 1
            row["host_receipts"] = row["host_receipts"][:keep]
            reconciled = paid.reconcile(row["sent"], row["host_receipts"])
            row["reconciliation"]["problems"] = reconciled["problems"]
        rows.append(row)
        return row

    import unittest.mock as um

    with um.patch.object(paid, "run_one", losing_run_one):
        report = paid.run(CASES, u_equals_b=True, outline_available=True, gateway=_client(gateway), approved=_approved(snapshot), model=STANDARD,
                          packer_for=lambda _c, _a: None, binder_for=lambda _c, _a: _binder(snapshot), workspace_for=lambda _c: workspace, ceiling=_ceiling(),
                          write=lambda _r: None, write_answers=lambda _a: None)
    assert len(rows) == 1 and report["rows"][0]["terminal"] == "incomplete" and report["stopped"]["at"] == ["QR1", "N"]
    assert len(gateway.payloads) == 1, "nothing after the unreconciled row is sent"


class _Unattributed(_Recording):
    """The real client, its settled usage renamed so it names no completed route attempt: the host's accounting integrity error."""

    def create_response(self, **kwargs: Any) -> Any:
        response = super().create_response(**kwargs)
        return response.model_copy(update={"gateway_usage": response.gateway_usage.model_copy(update={"gateway_request_id": "settled-elsewhere"})})


def test_an_accounting_integrity_error_keeps_its_row_and_its_receipts(tmp_path, snapshot):
    """Codex CP1 attempt 3 finding 4: the host raises after recording an unattributed receipt; the row and every receipt survive."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    gateway = InProcessGateway(snapshot, ScriptedUpstream(replies=["The answer."]))
    ceiling = _ceiling()
    try:
        row = paid.run_one({"case_id": "QX", "task": "What is x?"}, "N", position=1, gateway=_Unattributed(_client(gateway)), approved=_approved(snapshot), model=STANDARD,
                           packer=None, binder=_binder(snapshot), workspace=workspace, ceiling=ceiling, allowance=1)
    except Exception as error:  # noqa: BLE001 - the row must survive any failure of the run
        pytest.fail(f"run_one raised {error!r}")
    row["expected_logical_requests"], row["emitted_answer"] = 1, bool(row["answer"])
    assert len(gateway.payloads) == 1 and row["error"] == "AttemptIntegrityError" and paid.terminal(row)[0] == "incomplete"
    unattributed = [r for r in row["host_receipts"] if r["outcome"] == "unattributed"]
    # one physical attempt from the Gateway's evidence, its charge unknown; the unattributed receipt is kept on the row, never settled
    assert len(unattributed) == 1 and Decimal(unattributed[0]["cost_usd"]) > 0 and ceiling.attempts_used == len(row["attempts"]) == 1
    assert (ceiling.unknown_attempts, ceiling.usd_settled) == (1, Decimal(0)) and row["settlement"]["usd_actual"] == "UNKNOWN"
    assert any("settled-elsewhere" in p or "matches no Gateway attempt" in p for p in row["reconciliation"]["problems"])


class _TransportLoss:
    """A client whose connection drops after dispatch: no Gateway report, so the host records one uncertain attempt."""

    def __init__(self) -> None:
        self.calls = 0

    def create_response(self, **kwargs: Any) -> Any:
        self.calls += 1
        raise ConnectionResetError("connection lost after dispatch")


class _MalformedAttempts(_Recording):
    """The real client, its reply re-raised as the client raises for malformed route_attempts: the valid usage survives, the attempts don't."""

    def create_response(self, **kwargs: Any) -> Any:
        from optimus.gateway.errors import GatewayResponseError

        response = super().create_response(**kwargs)
        raise GatewayResponseError("route_attempts is malformed", gateway_usage=response.gateway_usage, audit_code="ROUTE_ATTEMPTS_MALFORMED")


def test_valid_usage_with_malformed_attempt_evidence_is_two_unknown_attempts_and_its_receipt_kept(tmp_path, snapshot):
    """Codex CP1 attempt 5 finding 4, under Fable's simplification: two worst-case attempt slots bound it; the reported amount stays on the
    row for the ledger, never settled, and the row's actual cost is UNKNOWN."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    gateway = InProcessGateway(snapshot, ScriptedUpstream(replies=["The answer."]))
    ceiling = _ceiling()
    row = paid.run_one({"case_id": "QX", "task": "What is x?"}, "N", position=1, gateway=_MalformedAttempts(_client(gateway)), approved=_approved(snapshot), model=STANDARD,
                       packer=None, binder=_binder(snapshot), workspace=workspace, ceiling=ceiling, allowance=1)
    row["expected_logical_requests"], row["emitted_answer"] = 1, bool(row["answer"])
    charged = [r for r in row["host_receipts"] if r["cost_usd"] not in (None, "0")]
    assert len(gateway.payloads) == 1 and len(row["attempts"]) == 2 and paid.terminal(row)[0] == "incomplete" and len(charged) == 1
    assert (ceiling.attempts_used, ceiling.unknown_attempts, ceiling.usd_settled) == (2, 2, Decimal(0))
    assert row["settlement"] == {"attempts": 2, "attempts_unknown_cost": 2, "usd_actual": "UNKNOWN"}


def test_a_transport_loss_reserves_two_unknown_attempts_and_no_third(tmp_path, snapshot):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    ceiling, lossy = _ceiling(), _TransportLoss()
    row = paid.run_one({"case_id": "QX", "task": "What is x?"}, "N", position=1, gateway=lossy, approved=_approved(snapshot), model=STANDARD, packer=None,
                       binder=_binder(snapshot), workspace=workspace, ceiling=ceiling, allowance=1)
    row["expected_logical_requests"], row["emitted_answer"] = 1, bool(row["answer"])
    assert lossy.calls == 1 and row["logical_requests"] == 1 and len(row["attempts"]) == 2 and paid.terminal(row)[0] == "incomplete"
    assert [r["outcome"] for r in row["host_receipts"]] == ["uncertain"] and row["reconciliation"]["unclaimed_receipt_ids"] == []
    assert (ceiling.attempts_used, ceiling.unknown_attempts, ceiling.usd_settled) == (2, 2, Decimal(0))


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


def test_qo4_runs_no_quote_control():
    """Codex CP1 attempt 5 finding 5: the oracle makes QO4's standalone quote control conditional, and every arm is a zero-call boundary."""
    case = BY_ID["QO4"]
    assert case["checks"]["quote"] is None and case["quote_control"]["run"] is False and case["quote_control"]["target_lines"] == [1123, 1131]
    assert all(c["checks"]["quote"] is None for c in CASES) and not hasattr(sc, "check_quote")
    assert "quote" not in sc.score_answer(case, "Any text.", _reader(case["snapshot"]))


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
    result = sc.score(case, ANSWERS[case_id], read)
    assert result["screen"] == sc.PASS and result["verdict"] == sc.PENDING_AUDIT and result["audit"] == "missing", result["checks"]
    assert sc.score(case, ANSWERS[case_id], read, audit=_audit(case, ANSWERS[case_id]))["verdict"] == sc.PASS  # only a bound audit makes PASS
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


# What a paid row's model received (the sink outside the repository keeps it), and the evidence a supported ruling quotes from it.
DELIVERED = "--- required files ---\n--- src/example.py ---\nRRF_K = 60  # the fusion constant, as the model received it\n"
DELIVERED_SHA = "hex:" + hashlib.sha256(DELIVERED.encode()).hexdigest()
QUOTE = "RRF_K = 60"


def _audit(case: dict, answer: str, *, arm: str = "X", release: str | None = None, rulings: tuple[bool, ...] = (True, True),
           cases_sha: str | None = None, input_sha: str | None = None) -> dict[str, Any]:
    """A support-audit record bound to exactly this answer (and on a paid row its request), with both designated CP3 reviewers'
    rulings, each quoting the delivered evidence it relied on."""
    return {"identity": sc.audit_identity(case, arm, release=release, answer=answer, cases_sha256=cases_sha, input_sha256=input_sha),
            "rulings": [{"reviewer": name, "supported": ruling, "reason": "checked against the oracle and the pinned snapshot", "quotes": [QUOTE]}
                        for name, ruling in zip(("fable-5.2", "codex-gpt-6.2-sol"), rulings, strict=False)]}


# Codex CP1 attempts 3-4 finding 5: the screen catches the literal reversals it encodes; a semantic one waits for the audit.
SCREENED_REVERSALS = {
    "QB2": "`RRF_K` is the reciprocal-rank fusion constant: 60.\n\n`QUOTA` starts with lexical. Some descriptions say dense first.",
    "QB3": "`MAX_ENTRIES` caps one page at 40 entries.\n\n`MAX_PAGE_BYTES` is 12,288 bytes excluding framing.",
}
SEMANTIC_REVERSAL = ("QB4", "`MAX_CONTEXT_CEILING_TOKENS` is 262,144 tokens, the total context ceiling.\n\n"
                            "`IMPLEMENTER_ROLES` is easy, medium, complex, escalation and administrator.")


@pytest.mark.parametrize("case_id", sorted(SCREENED_REVERSALS))
def test_a_reversal_the_screen_encodes_fails_at_the_screen(case_id):
    case = BY_ID[case_id]
    result = sc.score(case, SCREENED_REVERSALS[case_id], _reader(case["snapshot"]), audit=_audit(case, SCREENED_REVERSALS[case_id]))
    assert result["screen"] == sc.FAIL and result["verdict"] == sc.FAIL  # a supported ruling never lifts a screen failure


def test_a_semantic_reversal_waits_for_the_audit_and_a_ruling_binds_only_its_own_answer():
    case_id, answer = SEMANTIC_REVERSAL
    case = BY_ID[case_id]
    read = _reader(case["snapshot"])
    pending = sc.score(case, answer, read)
    assert pending["screen"] == sc.PASS and pending["verdict"] == sc.PENDING_AUDIT
    assert sc.score(case, answer, read, audit=_audit(case, answer, rulings=(False, False)))["verdict"] == sc.FAIL
    replayed = sc.score(case, answer, read, audit=_audit(case, ANSWERS[case_id]))  # a supported ruling for the correct answer's bytes
    assert replayed["verdict"] == sc.PENDING_AUDIT and replayed["audit"] == "mismatched"
    assert sc.score(case, answer + " ", read, audit=_audit(case, answer))["audit"] == "mismatched"  # one byte changed


def _verdict(screen: str, audit: Any, identity: dict) -> tuple[str, str]:
    """answer_verdict, any exception reported as a failed check: a malformed ruling must never raise (Codex CP1 attempt 5)."""
    try:
        return sc.answer_verdict(screen, audit, identity)
    except Exception as error:  # noqa: BLE001
        pytest.fail(f"answer_verdict raised {error!r}")


def test_an_audit_ruling_needs_both_reviewers_a_reason_and_agreement():
    case, answer = BY_ID["QB1"], ANSWERS["QB1"]
    identity = sc.audit_identity(case, "X", release=None, answer=answer, cases_sha256=None)
    assert _verdict(sc.FAIL, _audit(case, answer), identity) == (sc.FAIL, "not needed")  # the audit never lifts a screen failure
    assert _verdict(sc.INCOMPLETE, None, identity)[0] == sc.INCOMPLETE and _verdict(sc.PASS, None, identity) == (sc.PENDING_AUDIT, "missing")
    assert _verdict(sc.PASS, _audit(case, answer), identity) == (sc.PASS, "supported")
    assert _verdict(sc.PASS, _audit(case, answer, rulings=(True, False)), identity) == (sc.PENDING_AUDIT, "disputed: held for the operator")
    assert _verdict(sc.PASS, _audit(case, answer, rulings=(True,)), identity) == (sc.PENDING_AUDIT, "incomplete ruling")
    for broken in ({"supported": "yes"}, {"reason": " "}, {"reason": 7}, {"reviewer": "fable-5.2"}, {"reviewer": "someone-else"}):
        record = _audit(case, answer)
        record["rulings"][1] = {**record["rulings"][1], **broken}
        assert _verdict(sc.PASS, record, identity) == (sc.PENDING_AUDIT, "incomplete ruling"), broken
    extra = _audit(case, answer)
    extra["rulings"] = [*extra["rulings"], dict(extra["rulings"][0])]  # a third ruling, the designated set still complete
    assert _verdict(sc.PASS, extra, identity) == (sc.PENDING_AUDIT, "incomplete ruling")
    labels = _audit(case, answer)
    labels["rulings"] = [{**r, "reviewer": name} for r, name in zip(labels["rulings"], ("a", "b"), strict=True)]  # two arbitrary distinct labels
    assert _verdict(sc.PASS, labels, identity) == (sc.PENDING_AUDIT, "incomplete ruling")
    for malformed in ({**_audit(case, answer), "rulings": ["supported", "supported"]}, {**_audit(case, answer), "rulings": "both"}, "supported"):
        assert _verdict(sc.PASS, malformed, identity)[0] == sc.PENDING_AUDIT  # never a raise (Codex attempt 5)
    other_release = {**_audit(case, answer), "identity": {**identity, "release": "R"}}
    assert _verdict(sc.PASS, other_release, identity) == (sc.PENDING_AUDIT, "mismatched")


def test_framing_named_with_an_unrelated_exclusion_still_passes_the_screen():
    case = BY_ID["QB3"]
    answer = "`MAX_ENTRIES` caps one page at 40 entries.\n\n`MAX_PAGE_BYTES` caps it at 12,288 UTF-8 bytes, including framing, excluding unrelated files."
    assert sc.score(case, answer, _reader(case["snapshot"]))["screen"] == sc.PASS


def _answer_row(terminal: str, answer: str | None, finish: str = "stop", *, case_id: str = "QB1", arm: str = "F") -> dict[str, Any]:
    """A producer row as m2b_paid writes it: its case, arm, answer digest and terminal."""
    return {"release": "Q", "case_id": case_id, "arm": arm, "answer_sha256": None if answer is None else "hex:" + hashlib.sha256(answer.encode()).hexdigest(),
            "expected_logical_requests": 1, "terminal": terminal, "sent": [{"finish_reason": finish, "input_sha256": DELIVERED_SHA}]}


def test_rows_score_their_status_before_their_text():
    case = BY_ID["QB1"]
    read = _reader(case["snapshot"])
    good = ANSWERS["QB1"]
    audit = _audit(case, good, arm="F", release="Q", cases_sha=CASES_SHA, input_sha=DELIVERED_SHA)
    score = lambda arm, row, answer=good, audit=audit: sc.score_row(case, arm, row, answer, read, audit, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)  # noqa: E731
    assert score("F", _answer_row("settled", good))["verdict"] == sc.PASS
    assert score("B", _answer_row("settled", good, arm="B"))["audit"] == "mismatched"  # bound to its arm
    assert score("F", _answer_row("settled", good), audit=None)["verdict"] == sc.PENDING_AUDIT
    assert score("F", _answer_row("settled", good, "length"))["verdict"] == sc.INCOMPLETE  # cut at the cap
    assert score("F", {**_answer_row("failed", good), "stop_reason": "CHAT_SEARCH_LIMIT_REACHED", "sent": []})["verdict"] == sc.INCOMPLETE
    assert score("F", _answer_row("incomplete", good))["verdict"] == sc.INCOMPLETE
    over = BY_ID["QB3"]
    refused = {"release": "Q", "case_id": "QB3", "arm": "B", "expected_logical_requests": 0, "terminal": "expected_zero_call", "stop_reason": TOO_LARGE,
               "logical_requests": 0, "emitted_answer": False}
    boundary = lambda row: sc.score_row(over, "B", row, None, read, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)  # noqa: E731
    assert boundary(refused)["verdict"] == sc.PASS
    assert boundary({**refused, "logical_requests": 1})["verdict"] == sc.FAIL
    assert boundary({**refused, "stop_reason": "AGENT_SETUP_FAILED"})["verdict"] == sc.FAIL
    assert boundary({**refused, "terminal": "incomplete"})["verdict"] == sc.FAIL  # a clean terminal only
    outline = BY_ID["QO1"]  # F before Task 3's outline: the runner allows no send, so the row is a boundary, never an answer
    row = sc.score_row(outline, "F", {**refused, "case_id": "QO1", "arm": "F"}, None, read, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)
    assert row["kind"] == "boundary" and row["verdict"] == sc.PASS


def test_a_paid_row_scores_only_the_answer_the_producer_recorded_under_the_verified_cases():
    """Codex CP1 attempt 5 finding 5: a substituted answer with its own valid audit never scores; the cases digest is required."""
    case = BY_ID["QB4"]
    read = _reader(case["snapshot"])
    _case_id, substituted = SEMANTIC_REVERSAL
    recorded = _answer_row("settled", ANSWERS["QB4"], case_id="QB4")
    own_audit = _audit(case, substituted, arm="F", release="Q", cases_sha=CASES_SHA, input_sha=DELIVERED_SHA)  # otherwise valid, for the substituted bytes
    result = sc.score_row(case, "F", recorded, substituted, read, own_audit, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)
    assert result["verdict"] == sc.INCOMPLETE and result["reason"] == "not the producer's answer"
    assert sc.score_row(case, "F", {**recorded, "case_id": "QB1"}, ANSWERS["QB4"], read, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)["verdict"] == sc.INCOMPLETE
    for missing in (None, "", "0a16d5b8"):
        with pytest.raises(ValueError, match="verified cases digest"):
            sc.score_row(case, "F", recorded, ANSWERS["QB4"], read, cases_sha256=missing, release="Q", delivered_input=DELIVERED)
    unverified = _audit(case, ANSWERS["QB4"], arm="F", release="Q", cases_sha=None)  # a ruling recorded without the cases digest
    assert sc.score_row(case, "F", recorded, ANSWERS["QB4"], read, unverified, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)["audit"] == "mismatched"


def test_qo4_is_a_boundary_in_every_arm_and_a_quote_on_its_zero_call_row_fails():
    case = BY_ID["QO4"]
    read = _reader(case["snapshot"])
    refused = {"release": "Q", "case_id": "QO4", "expected_logical_requests": 0, "terminal": "expected_zero_call", "stop_reason": TOO_LARGE,
               "logical_requests": 0, "emitted_answer": False}
    assert all(sc.score_row(case, arm, {**refused, "arm": arm}, None, read, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)["verdict"] == sc.PASS for arm in ("N", "B", "U", "F"))
    quoted = sc.score_row(case, "F", {**refused, "arm": "F", "emitted_answer": True}, "```python\ndef _project_child_env():\n```", read, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)
    assert quoted["verdict"] == sc.FAIL


# --- the Q-release gate's scorer items (Codex CP1 attempt 7 B items; gate item 6) ---------------------------------------------


@pytest.mark.parametrize("reviewer", [[], {}, ["fable-5.2"], None, 7])
def test_a_malformed_reviewer_field_holds_the_answer_pending_and_never_raises(reviewer):
    case = BY_ID["QB1"]
    good = ANSWERS["QB1"]
    audit = _audit(case, good, arm="F", release="Q", cases_sha=CASES_SHA, input_sha=DELIVERED_SHA)
    audit["rulings"][0] = {**audit["rulings"][0], "reviewer": reviewer}
    try:
        result = sc.score_row(case, "F", _answer_row("settled", good), good, _reader(case["snapshot"]), audit, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)
    except TypeError as error:
        pytest.fail(f"a malformed reviewer must not raise: {error!r}")
    assert (result["verdict"], result["audit"]) == (sc.PENDING_AUDIT, "incomplete ruling")


def test_paid_scoring_runs_only_against_the_sealed_cases_bytes():
    assert sc.SEALED_CASES_SHA256 == CASES_SHA, "the scorer's pin is the sealed cases file"
    case = BY_ID["QB1"]
    for other in ("hex:", "hex:" + "0" * 64, CASES_SHA.upper()):
        with pytest.raises(ValueError, match="verified cases digest"):
            sc.score_row(case, "F", _answer_row("settled", ANSWERS["QB1"]), ANSWERS["QB1"], _reader(case["snapshot"]), cases_sha256=other, release="Q", delivered_input=DELIVERED)


def test_a_row_from_another_release_or_none_never_scores():
    case = BY_ID["QB1"]
    good = ANSWERS["QB1"]
    read = _reader(case["snapshot"])
    audit = _audit(case, good, arm="F", release="Q", cases_sha=CASES_SHA, input_sha=DELIVERED_SHA)
    for release in (None, "R", ""):
        result = sc.score_row(case, "F", {**_answer_row("settled", good), "release": release}, good, read, audit, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)
        assert (result["verdict"], result.get("reason")) == (sc.INCOMPLETE, "another release"), release
    with pytest.raises(ValueError, match="expected release"):
        sc.score_row(case, "F", _answer_row("settled", good), good, read, audit, cases_sha256=CASES_SHA, release=None, delivered_input=DELIVERED)


def test_a_boundary_row_must_be_the_producers_own_with_an_explicit_no_answer():
    case = BY_ID["QB3"]
    read = _reader(case["snapshot"])
    refused = {"release": "Q", "case_id": "QB3", "arm": "B", "expected_logical_requests": 0, "terminal": "expected_zero_call", "stop_reason": TOO_LARGE,
               "logical_requests": 0, "emitted_answer": False}
    assert sc.score_row(case, "B", refused, None, read, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)["verdict"] == sc.PASS
    without_flag = {k: v for k, v in refused.items() if k != "emitted_answer"}
    for row, answer, why in (({**refused, "case_id": "QB4"}, None, "another case"), ({**refused, "arm": "N"}, None, "another arm"),
                             (without_flag, None, "no explicit no-answer flag"), (refused, "Some supplied text.", "conflicting supplied text")):
        assert sc.score_row(case, "B", row, answer, read, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)["verdict"] == sc.FAIL, why


def test_an_operator_hold_removes_a_suspected_false_screen_failure_from_every_gate_without_rescoring():
    case = BY_ID["QB1"]
    read = _reader(case["snapshot"])
    wrong = CONTRADICTIONS["QB1"]
    held = {**_audit(case, wrong, arm="F", release="Q", cases_sha=CASES_SHA, input_sha=DELIVERED_SHA), "operator_hold": {"reason": "the oracle phrase may be too narrow"}}
    row = _answer_row("settled", wrong)
    result = sc.score_row(case, "F", row, wrong, read, held, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)
    assert result["screen"] == sc.FAIL and (result["verdict"], result["audit"]) == (sc.HELD, "operator hold: suspected false screen failure, not rescored")
    for hold in ({"reason": " "}, {}, "yes"):
        assert sc.score_row(case, "F", row, wrong, read, {**held, "operator_hold": hold}, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)["verdict"] == sc.FAIL
    unbound = {**held, "identity": {**held["identity"], "arm": "B"}}
    assert sc.score_row(case, "F", row, wrong, read, unbound, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)["verdict"] == sc.FAIL
    good = ANSWERS["QB1"]
    on_pass = {**_audit(case, good, arm="F", release="Q", cases_sha=CASES_SHA, input_sha=DELIVERED_SHA), "operator_hold": {"reason": "x"}}
    assert sc.score_row(case, "F", _answer_row("settled", good), good, read, on_pass, cases_sha256=CASES_SHA, release="Q", delivered_input=DELIVERED)["verdict"] == sc.PASS


def test_the_guard_forwards_only_the_input_the_dry_preparation_pass_prepared(tmp_path, snapshot):
    """Q-release gate item 14 (Fable gate consult recommendation 1): the paid launcher's dry pass fixes each row's exact input digest, and
    the Guard refuses any other input before anything is sent."""
    workspace = tmp_path / "ws"
    workspace.mkdir()

    def row(expected: str | None) -> tuple[dict[str, Any], InProcessGateway]:
        gateway = InProcessGateway(snapshot, ScriptedUpstream(replies=["The answer."]))
        out = paid.run_one({"case_id": "QX", "task": "What is x?"}, "N", position=1, gateway=_client(gateway), approved=_approved(snapshot), model=STANDARD,
                           packer=None, binder=_binder(snapshot), workspace=workspace, ceiling=_ceiling(), allowance=1, expected_input_sha256=expected)
        return out, gateway

    prepared, _ = row(None)
    digest = prepared["sent"][0]["input_sha256"]
    same, gateway = row(digest)
    assert same["guard_refusal"] is None and len(gateway.payloads) == 1 and same["sent"][0]["input_sha256"] == digest
    other, gateway = row("hex:" + "0" * 64)
    assert gateway.payloads == [] and other["logical_requests"] == 0 and other["guard_refusal"] == "the input is not the one the dry preparation pass prepared"


def test_a_q_rows_summarizer_client_refuses_every_call():
    client = paid.NoSummaries()
    for _ in range(2):
        with pytest.raises(paid.GuardRefused, match="never summarizes"):
            client.create_response(model="anthropic/claude-haiku-5.5", input_text="history")
    assert client.calls == 2


def test_an_answer_is_scored_only_with_the_request_its_model_received_and_rulings_quote_from_it():
    """Q-release gate item 15: the support audit is bound to the delivered request, and a supported ruling must quote, verbatim, evidence
    the model received; a fact true of the repository but absent from the request supports nothing."""
    case, good = BY_ID["QB1"], ANSWERS["QB1"]
    read = _reader(case["snapshot"])
    audit = _audit(case, good, arm="F", release="Q", cases_sha=CASES_SHA, input_sha=DELIVERED_SHA)
    score = lambda delivered, audit=audit: sc.score_row(case, "F", _answer_row("settled", good), good, read, audit, cases_sha256=CASES_SHA,  # noqa: E731
                                                        release="Q", delivered_input=delivered)
    assert score(DELIVERED)["verdict"] == sc.PASS
    for other in (None, DELIVERED + " ", "another request"):
        assert (score(other)["verdict"], score(other).get("reason")) == (sc.INCOMPLETE, "the delivered input is not the row's"), other
    for quotes in (["RRF_K = 61"], [], [" "], "RRF_K = 60", None):
        unquoted = {**audit, "rulings": [{**r, "quotes": quotes} for r in audit["rulings"]]}
        assert (score(DELIVERED, unquoted)["verdict"], score(DELIVERED, unquoted)["audit"]) == (sc.PENDING_AUDIT, "a supported ruling quotes nothing the model received"), quotes
    other_request = _audit(case, good, arm="F", release="Q", cases_sha=CASES_SHA, input_sha="hex:" + "1" * 64)
    assert score(DELIVERED, other_request)["audit"] == "mismatched", "a ruling bound to another request"


def test_the_guard_keeps_each_sent_request_in_the_sink_before_forwarding_and_never_a_refused_one(tmp_path, snapshot):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    kept: list[tuple[str, str]] = []

    class Watching:
        def __init__(self, inner: Any) -> None:
            self.inner = inner

        def create_response(self, **kwargs: Any) -> Any:
            assert kept and kept[-1][1] == kwargs["input_text"], "the request is kept before it is forwarded"
            return self.inner.create_response(**kwargs)

    for allowance in (1, 0):
        gateway = InProcessGateway(snapshot, ScriptedUpstream(replies=["The answer."]))
        row = paid.run_one({"case_id": "QX", "task": "What is x?"}, "N", position=1, gateway=Watching(_client(gateway)), approved=_approved(snapshot), model=STANDARD,
                           packer=None, binder=_binder(snapshot), workspace=workspace, ceiling=_ceiling(), allowance=allowance, write_input=lambda sha, text: kept.append((sha, text)))
        assert len(kept) == 1, "the refused row (allowance 0) keeps nothing"
    sha, text = kept[0]
    assert sha == "hex:" + hashlib.sha256(text.encode()).hexdigest() and all(text not in json.dumps(entry) for entry in row["sent"])
