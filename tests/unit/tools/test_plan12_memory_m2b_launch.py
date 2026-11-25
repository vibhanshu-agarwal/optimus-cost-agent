"""Plan 12.14 Q launcher (gate G1b), zero paid: production's shipped D3 composition (the trusted registry) driven through the paid runner, the
production HTTP Gateway server and client, whose real upstream client posts to a loopback stub provider, and memory turns on a real
MemorySession over fake index storage. The drivers' sequencing and failure paths run on test doubles."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from optimus.context.context_budget import BudgetPolicy
from optimus.context.shipped_policy import attachment_limits
from optimus_model_policy.binding import trusted_snapshot
from tests.unit.context.test_memory_tools_and_turns import _session, _Storage, workspace  # noqa: F401 - fixture
from tests.unit.tools.test_plan12_memory_m2b_paid import no_sleep  # noqa: F401 - fixture
from tests.unit.tools.test_plan12_memory_m2b_production_bytes import LOADER, TASK, _records
from tools.plan12_memory import m2b_evaluate as ev
from tools.plan12_memory import m2b_launch as launch
from tools.plan12_memory import m2b_paid as paid

ROOT = Path(__file__).resolve().parents[3]
LEGACY = BudgetPolicy("legacy", 420, None)  # under the D3 estimator, the required file (414) and nothing else, so B packs less than F
SNAP = "git:x"


class _Epoch(_Storage):
    """The fake index at a given generation: a fresh build publishes a new one, so the scope line differs between runs."""

    def __init__(self, records: list[dict], epoch: int, **kwargs: Any) -> None:
        super().__init__(records, **kwargs)
        self.epoch = epoch

    def call(self, op: str, **kwargs: Any) -> dict:
        out = super().call(op, **kwargs)
        if op == "coverage" and out.get("current"):
            out["current"] = {**out["current"], "epoch": self.epoch}
        return out


class _Vectors:
    def embed(self, texts: list[str]) -> list[bytes]:
        return [struct.pack("<4f", 1.0, 0.0, 0.0, 0.0) for _ in texts]


def _cases() -> list[dict[str, Any]]:
    return [{"case_id": f"{prefix}{n}", "category": category, "kind": None, "snapshot": SNAP, "task": TASK, "required_files": [{"path": "pkg/a.py"}],
             "forced_refusal": dict.fromkeys("NBUF", False)}
            for category, prefix in (("ranking", "QR"), ("budget", "QB"), ("outline", "QO")) for n in range(1, 5)]


def _commit(tree: Path) -> None:
    for args in (("add", "-A"), ("-c", "user.email=t@t", "-c", "user.name=t", "-c", "core.autocrlf=false", "commit", "-q", "-m", "c")):
        subprocess.run(["git", "-C", str(tree), *args], check=True, capture_output=True)


@pytest.fixture
def tree(workspace: Path) -> Path:  # noqa: F811
    """A materialized checkout: its own repository, committed, as m1_evaluate.materialize leaves one."""
    (workspace / "pkg" / "b.py").write_text(LOADER, encoding="utf-8", newline="\n")
    subprocess.run(["git", "-C", str(workspace), "init", "-q", "-b", "q"], check=True, capture_output=True)
    _commit(workspace)
    return workspace


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    """The synthetic schedule sends every row: 36 rows, 36 sends, no forced refusal."""
    monkeypatch.setattr(launch, "FROZEN_COUNTS", (36, 36, 0))


def _ready_session(tree: Path, epoch: int, **storage: Any) -> Any:
    """An indexed session as the launcher leaves one: its embedder loaded and its catalogue read (wait_indexed)."""
    session = _session(tree, _Epoch(_records(), epoch, **storage))
    session._embedder = _Vectors()  # noqa: SLF001
    session.turn()._retriever.retrieve("prime")  # noqa: SLF001
    assert session.wait_for_catalogue(5)
    return session


def _composition(tree: Path, *, epoch: int = 3, checked: bool = False, **storage: Any) -> launch.Composition:
    """`checked` runs the real git checkout check before each request; elsewhere it is doubled (a git process per row is slow on Windows),
    and the tests about the checkout run it for real."""
    return launch.Composition(trusted_snapshot(), "s" * 64, LEGACY, {SNAP: _ready_session(tree, epoch, **storage)}, {SNAP: tree}, epochs={SNAP: epoch},
                              trees={SNAP: launch.checkout_tree(tree)}, heads={SNAP: launch.checkout_head(tree)},
                              verify_checkout=launch.checkout_drift if checked else lambda _ws, _head: None)


def _rehearse(composition: launch.Composition, *, budget_report: dict | None = None, cases: list[dict] | None = None) -> dict[str, Any]:
    with launch.loopback_gateway(composition.snapshot, composition.shared_secret) as (client, provider):
        return launch.rehearse(cases or _cases(), composition, gateway=client, provider=provider, u_equals_b=True, outline_available=True, budget_report=budget_report)


def _budget(record: dict[str, Any], *, complete: bool = True) -> dict[str, Any]:
    """A budget report whose packs are the rows' own (as a G2 budget pass on the rows' session measures them)."""
    packs = {(r["case_id"], r["arm"]): r["pack_sha256"] for r in record["rows"]}
    return {"outline_available": True, "rows": [{"case_id": c, "arms": {"BU": {"complete": complete, "pack_sha256": packs[(c, "B")]}, "F": {"complete": True, "pack_sha256": packs[(c, "F")]}}}
                                                for c in ev.BUDGET_CASES]}


def _gate() -> dict[str, Any]:
    return {"rows": 36, "sends": 36, "forced_refusals": 0, "attempts_max": 96, "usd_max": "6.00", "per_attempt_usd": "0.04608",
            "digests": {rel: "hex:" + hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in launch.PINNED_FILES},
            "registry_hash": trusted_snapshot().effective_hash, "tariff": launch.tariff_record()}


@pytest.fixture
def gates_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """The budget report's own gates are m2b_evaluate's, proved there; here a report passes unless a row says otherwise."""
    monkeypatch.setattr(launch.ev, "budget_gates", lambda rows, outline_available: {"passes": bool(rows) and all(r.get("passes", True) for r in rows)})


# --- the composition -----------------------------------------------------------------------------------------------------------

def test_each_arm_is_productions_d3_composition_with_only_bs_pack_budget_replaced(tree, monkeypatch):
    """The shipped registry's attachment for the D3 model, as ordinary_attachment builds it; B differs only in its pack budget; the binder is
    production's RoutePolicy for the model's implementer role with Q's output cap; N has no memory turn and B/F join one."""
    composition = _composition(tree)
    shipped = attachment_limits(composition.snapshot, launch.D3_MODEL)
    case = _cases()[0]
    assert composition.packer(case, "N").memory is None and composition.packer(case, "F").memory is not None and composition.packer(case, "B").memory is not None
    built = launch.ordinary_attachment(snapshot=composition.snapshot, model_id=launch.D3_MODEL, gateway_client=composition.summaries, shared_secret=composition.shared_secret)
    assert (built.pack_budget, built.model_id, built.registry_hash) == (shipped.pack_budget, launch.D3_MODEL, composition.snapshot.effective_hash)
    assert built.pack_budget.name == "model-aware" and built.pack_budget.ceiling == 32_768
    asked: list[dict] = []
    monkeypatch.setattr(launch, "ordinary_attachment", lambda **kwargs: asked.append(kwargs) or built)
    f, b = composition.attachment("F"), composition.attachment("B")
    assert f is built and b.pack_budget == LEGACY
    assert [x.name for x in fields(f) if getattr(f, x.name) is not getattr(b, x.name)] == ["pack_budget"], "B replaces only the pack budget"
    assert all(kw["gateway_client"] is composition.summaries and kw["model_id"] == launch.D3_MODEL for kw in asked), "summaries go to the refusing client"
    with pytest.raises(launch.LaunchRefused):
        composition.attachment("U")
    binder = composition.binder(case, "F")
    assert (binder.output_cap, binder.identity.model_id) == (paid.OUTPUT_CAP, launch.D3_MODEL)


# --- the rehearsal ---------------------------------------------------------------------------------------------------------------

def test_the_rehearsal_sends_every_row_once_through_the_http_gateway_and_seals_what_the_paid_run_must_reproduce(tree):
    record = _rehearse(_composition(tree, checked=True))  # the real checkout check on every row of a clean checkout
    assert record["passes"], record["problems"]
    assert (record["sends"], record["provider_calls"], record["summary_calls"]) == (36, 36, 0)
    for row in record["rows"]:
        memory = row["arm"] != "N"
        assert row["sent"] and row["limit_line"] is memory and (row["pack_sha256"] is not None) is memory, row
        assert row["binding"] == {"registry_hash": trusted_snapshot().effective_hash, "model": launch.D3_MODEL, "output_cap": paid.OUTPUT_CAP}
        assert (row["cache_prefix_chars"] is not None) is memory, "the indexed prefix is cached, and the provider received exactly that split"
        assert (row["epoch"], row["tree"], row["retrieval_evidence"]) == ((3, launch.checkout_tree(tree), "manifest") if memory else (None, launch.checkout_tree(tree), "no memory turn"))
        assert row["input_masked_sha256"] != row["input_sha256"] or not memory, "a memory row's scope line names its generation"
    by_arm = {row["arm"]: row["pack_sha256"] for row in record["rows"] if row["case_id"] == "QB1"}
    assert by_arm["B"] != by_arm["F"], "B packs under the legacy budget, F under the route's own"


def test_a_provider_request_split_elsewhere_than_the_binding_fails_the_rehearsal(tree, monkeypatch):
    answer = launch.StubProvider.answer

    def shifted(self: launch.StubProvider, body: dict) -> dict:
        out = answer(self, body)
        self.calls[-1]["cache_prefix_chars"] = (self.calls[-1]["cache_prefix_chars"] or 0) + 1
        return out

    monkeypatch.setattr(launch.StubProvider, "answer", shifted)
    problems = _rehearse(_composition(tree))["problems"]
    assert len(problems) == 36 and all("the provider's cached block ends at" in p for p in problems)


def test_a_rebuilt_index_at_a_new_generation_still_matches_the_sealed_rehearsal_and_gives_its_own_exact_inputs(tree):
    """The epoch is a global counter (Fable gate consult): only the masked input is sealed, and the dry pass's exact inputs are the paid ones."""
    sealed, dry = _rehearse(_composition(tree, epoch=3)), _rehearse(_composition(tree, epoch=4))
    expected = launch.compare(sealed, dry)
    assert len(expected) == 36 and expected == {(r["case_id"], r["arm"]): {"input_sha256": r["input_sha256"], "cache_prefix_chars": r["cache_prefix_chars"]} for r in dry["rows"]}
    assert any(r["input_sha256"] != s["input_sha256"] for r, s in zip(dry["rows"], sealed["rows"], strict=True)), "the exact inputs moved with the generation"


@pytest.mark.parametrize("field", ["pack_sha256", "input_masked_sha256", "prefix_sha256", "cache_prefix_chars", "limit_line", "terminal", "retrieval_evidence"])
def test_any_sealed_difference_refuses_the_launch(tree, field):
    sealed, dry = _rehearse(_composition(tree)), _rehearse(_composition(tree))
    sealed["rows"][4] = {**sealed["rows"][4], field: "something else"}
    with pytest.raises(launch.LaunchRefused, match=field):
        launch.compare(sealed, dry)


def test_a_retrieval_on_another_generation_than_the_session_published_fails_the_rehearsal(tree):
    composition = _composition(tree)
    composition.epochs[SNAP] = 99
    problems = _rehearse(composition)["problems"]
    assert len(problems) == 24 and all(p.endswith("retrieval read generation 3, the session published 99") for p in problems)


def test_degraded_retrieval_fails_the_rehearsal(tree):
    record = _rehearse(_composition(tree, complete=False))
    assert not record["passes"] and any("index coverage incomplete" in p for p in record["problems"])
    full = {"state": "ok", "coverage": {"complete": True}, "channels": {"memory": "no authorized source", "lexical": "3 results", "dense": "0 results", "structure": "2 results",
                                                                          "recency": "1 results"}}
    assert launch.degraded({"retrieval": full}) == []
    assert launch.degraded({"retrieval": {**full, "channels": {**full["channels"], "catalogue": "not ready", "dense": "unavailable"}}}) == [
        "catalogue not ready", "channel dense: unavailable"]
    assert launch.degraded({"retrieval": {**full, "channels": {}}}) == [f"channel {name} missing" for name in sorted(launch.EXPECTED_CHANNELS)]
    assert launch.degraded({"retrieval": full, "stale_paths": ["pkg/a.py"]}) == ["1 stale files held back"]
    assert launch.degraded({"retrieval": {"state": "unpublished"}})[:2] == ["retrieval state 'unpublished'", "index coverage incomplete"]


def test_a_row_that_stopped_before_retrieval_says_so_explicitly(tree):
    composition = _composition(tree)
    evidence = launch.Evidence(composition, _cases())
    composition.packers[("QB3", "B")] = SimpleNamespace(memory=SimpleNamespace(manifest={}))
    composition.packers[("QB3", "N")] = SimpleNamespace(memory=None)
    row = {"logical_request_id": "m2b-q-QB3-B", "sent": []}
    assert evidence({"case_id": "QB3", "snapshot": SNAP}, "B", row)["retrieval_evidence"] == "none: the turn stopped before retrieval"
    assert evidence({"case_id": "QB3", "snapshot": SNAP}, "N", row)["retrieval_evidence"] == "no memory turn"


BIG = "".join(f"def handler_{i}(event):\n    return 'big file body {i}'\n\n\n" for i in range(60))


def _with_refusal(tree: Path) -> list[dict[str, Any]]:
    """QB3 names a required file B's legacy budget cannot hold: production retrieves, packs, then refuses before its manifest."""
    (tree / "pkg" / "big.py").write_text(BIG, encoding="utf-8", newline="\n")
    _commit(tree)
    cases = _cases()
    qb3 = next(c for c in cases if c["case_id"] == "QB3")
    qb3.update({"task": "Explain what pkg/big.py does.", "required_files": [{"path": "pkg/big.py"}], "forced_refusal": {**qb3["forced_refusal"], "B": True},
                "boundary": {"stop_reason": "REQUIRED_WORKSPACE_FILE_TOO_LARGE", "gateway_requests": 0}})
    return cases


def test_a_refusal_after_retrieval_keeps_its_retrieval_evidence_and_fails_when_degraded(tree, monkeypatch):
    """Codex round 124 attempt 2, A2: QB3/B's expected refusal comes after retrieval, so its epoch and degradation are still checked."""
    monkeypatch.setattr(launch, "FROZEN_COUNTS", (36, 35, 1))
    cases = _with_refusal(tree)
    clean = _rehearse(_composition(tree), cases=cases)
    assert clean["passes"], clean["problems"]
    row = next(r for r in clean["rows"] if (r["case_id"], r["arm"]) == ("QB3", "B"))
    assert (row["terminal"], row["sent"], row["retrieval_evidence"], row["epoch"], row["degraded"]) == (
        "expected_zero_call", False, "retrieval, then a refusal before the manifest", 3, [])
    degraded = _rehearse(_composition(tree, complete=False), cases=cases)
    assert "QB3/B: index coverage incomplete" in degraded["problems"]


def test_the_rehearsal_accounts_for_every_budget_case_and_arm_against_the_budget_report(tree):
    honest = _rehearse(_composition(tree))
    assert _rehearse(_composition(tree), budget_report=_budget(honest))["passes"]
    missing = _budget(honest)
    missing["rows"] = missing["rows"][:-1]
    assert _rehearse(_composition(tree), budget_report=missing)["problems"] == ["QO4: not in the budget report"]
    wrong = _budget(honest)
    wrong["rows"][0]["arms"]["F"]["pack_sha256"] = wrong["rows"][0]["arms"]["BU"]["pack_sha256"]
    assert _rehearse(_composition(tree), budget_report=wrong)["problems"] == ["QB1/F: the pack is not the budget report's"]
    refused = _rehearse(_composition(tree), budget_report=_budget(honest, complete=False))["problems"]
    assert refused == [f"{c}/B: the budget report measured no complete pack, but the row is settled" for c in ev.BUDGET_CASES]


def test_a_row_whose_limit_line_is_not_its_arms_fails_the_rehearsal(tree):
    """B and F send the runner's limit observation (the indexed Chat builder, tools withdrawn); N, with no memory turn, does not."""

    class NWithMemory(launch.Composition):
        def packer(self, case: dict, arm: str) -> Any:
            attached = super().packer(case, arm)
            if arm == "N":
                attached.memory = self.sessions[case["snapshot"]].turn()
            return attached

    plain = _composition(tree)
    record = _rehearse(NWithMemory(plain.snapshot, plain.shared_secret, LEGACY, plain.sessions, plain.workspaces, epochs=plain.epochs, trees=plain.trees,
                               heads=plain.heads, verify_checkout=plain.verify_checkout))
    assert {p for p in record["problems"] if p.endswith("limit line is present")} == {f"{c['case_id']}/N: the limit line is present" for c in _cases()}


def test_a_provider_call_the_schedule_did_not_send_fails_the_rehearsal(tree, monkeypatch):
    answer = launch.StubProvider.answer

    def twice(self: launch.StubProvider, body: dict) -> dict:
        if len(self.calls) == 5:
            self.calls.append({"input_sha256": "hex:extra", "cache_prefix_chars": None, "marked_blocks": [], "model": body["model"]})
        return answer(self, body)

    monkeypatch.setattr(launch.StubProvider, "answer", twice)
    assert _rehearse(_composition(tree))["problems"] == ["37 provider calls for 36 sends"]


def test_a_request_that_does_not_carry_its_context_exactly_once_fails_the_rehearsal(tree, monkeypatch):
    monkeypatch.setattr(launch, "masked_sha", lambda text, context: None)
    problems = _rehearse(_composition(tree))["problems"]
    assert len(problems) == 36 and all(p.endswith("the row's workspace context is not in its request exactly once") for p in problems)


def test_a_summary_call_fails_the_rehearsal(tree):
    composition = _composition(tree)
    composition.summaries.calls = 1
    assert "1 summary calls; a Q row never summarizes" in _rehearse(composition)["problems"]


def test_masking_hides_only_the_emitted_scope_lines_index_generation():
    line = "--- scope: index generation {}, complete, 2 of 2 files; ---"

    def request(pack: str, epoch: int) -> tuple[str, str]:
        context = f"{pack}\n{line.format(epoch)}"
        return f"prefix\n{context}\nthe task", context

    assert launch.masked_sha(*request("pack", 3)) == launch.masked_sha(*request("pack", 41))
    assert launch.masked_sha(*request("pack", 3)) != launch.masked_sha(*request("other", 3))
    literal = line.format(5)  # a source file's own line, inside the pack, is never masked
    assert launch.masked_sha(*request(f"code\n{literal}", 3)) != launch.masked_sha(*request(f"code\n{line.format(6)}", 3))
    assert launch.masked_sha("no context here", "missing") is None, "a context not in the request exactly once has no masked digest"


# --- the paid launch ---------------------------------------------------------------------------------------------------------------

def _launch(tree: Path, sealed: dict, budget: dict, provider_calls: list[int], *, gate: dict | None = None) -> dict:
    composition = _composition(tree, epoch=9, checked=True)
    kept: list[tuple[str, str]] = []
    with launch.loopback_gateway(composition.snapshot, composition.shared_secret) as (client, provider):  # the operator Gateway's stand-in
        try:
            return launch.paid_launch(_cases(), composition, gateway=client, sealed=sealed, budget_report=budget, gate=gate or _gate(), u_equals_b=True, outline_available=True,
                                      repository=ROOT, write=lambda _r: None, write_answers=lambda _a: None, write_input=lambda sha, text: kept.append((sha, text)))
        finally:
            provider_calls.append(len(provider.calls))
            assert len(kept) == len(provider.calls), "every forwarded request is in the sink, and nothing else"


def test_the_paid_launch_forwards_each_rows_dry_pass_input_only_after_every_row_matches(tree, frozen, gates_pass):
    sealed = _rehearse(_composition(tree))
    calls: list[int] = []
    report = _launch(tree, sealed, _budget(sealed), calls)
    assert report["stopped"] is None and calls == [36]
    assert all(row["guard_refusal"] is None and row["terminal"] == "settled" for row in report["rows"])
    assert all(row["epoch"] == (9 if row["arm"] != "N" else None) and row["tree"] == launch.checkout_tree(tree) for row in report["rows"]), "each paid row keeps its own evidence"
    assert all(row["pack_sha256"] == s["pack_sha256"] for row, s in zip(report["rows"], sealed["rows"], strict=True))


@pytest.mark.parametrize(("move", "reason"), [
    (lambda tree: (tree / "notes.md").write_text("# Edited after the dry pass\n", encoding="utf-8"), "the checkout has changed since it was opened"),
    (lambda tree: ((tree / "notes.md").write_text("# Committed after the dry pass\n", encoding="utf-8"), _commit(tree)), "the checkout is not the commit it was opened at"),
    (lambda tree: (tree / "untracked.txt").write_text("new\n", encoding="utf-8"), "the checkout has changed since it was opened"),
])
def test_a_paid_row_whose_checkout_moved_after_the_dry_pass_is_refused_before_its_request(tree, frozen, gates_pass, monkeypatch, move, reason):
    """Codex round 124 attempt 3, B2: a change to a file outside every row's selected context leaves the request bytes the same, so the
    checkout itself is verified before each request."""
    sealed = _rehearse(_composition(tree))
    real_run = paid.run

    def moved(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("expected_inputs") is not None:  # the paid rows, after the dry pass compared clean
            move(tree)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(launch.paid, "run", moved)
    calls: list[int] = []
    report = _launch(tree, sealed, _budget(sealed), calls)
    assert calls == [0] and report["stopped"] is not None and report["rows"][0]["evidence_refusal"] == reason


def test_a_paid_row_on_a_newer_index_generation_than_the_dry_pass_is_refused_before_its_request(tree, frozen, gates_pass, monkeypatch):
    """A background pass that publishes between the dry pass and the paid rows leaves the checkout clean but moves the scope line: the
    paid row is held to its dry row and refused before anything is sent."""
    sealed = _rehearse(_composition(tree))
    real_run = paid.run

    def republished(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("expected_inputs") is not None:
            kwargs["packer_for"].__self__.sessions[SNAP]._storage_for("scope").epoch = 10  # noqa: SLF001 - the fake index publishes again
        return real_run(*args, **kwargs)

    monkeypatch.setattr(launch.paid, "run", republished)
    calls: list[int] = []
    report = _launch(tree, sealed, _budget(sealed), calls)
    first_memory = next(row for row in report["rows"] if row["arm"] != "N")
    assert calls == [first_memory["position"] - 1] and report["stopped"] is not None
    assert first_memory["evidence_refusal"] == "the scope line's generation is not the dry pass's"


def test_the_paid_launch_refuses_before_any_send_on_a_sealed_difference(tree, frozen, gates_pass):
    sealed = _rehearse(_composition(tree))
    budget = _budget(sealed)
    sealed["rows"][7] = {**sealed["rows"][7], "pack_sha256": "hex:" + "0" * 64}
    calls: list[int] = []
    with pytest.raises(launch.LaunchRefused, match="differs from the sealed rehearsal"):
        _launch(tree, sealed, budget, calls)
    assert calls == [0]


def test_a_row_the_dry_pass_did_not_prepare_or_split_elsewhere_is_refused_by_its_guard(tree):
    sealed = _rehearse(_composition(tree))
    first = next(r for r in sealed["rows"] if r["cache_prefix_chars"] is not None)  # a memory row, whose prefix is cached
    shifted = launch.compare(sealed, sealed)  # every row's exact input (same generation), then one boundary moved
    shifted[(first["case_id"], first["arm"])] = {**shifted[(first["case_id"], first["arm"])], "cache_prefix_chars": first["cache_prefix_chars"] + 1}
    for expected, reason, position in (({}, "the input is not the one the dry preparation pass prepared", 1),
                                       (shifted, "the cached prefix is not the one the dry preparation pass bound", first["position"])):
        composition = _composition(tree)
        with launch.loopback_gateway(composition.snapshot, composition.shared_secret) as (client, provider):
            report = paid.run(_cases(), u_equals_b=True, outline_available=True, gateway=client, approved=composition.approved(), model=composition.model_id,
                              packer_for=composition.packer, binder_for=composition.binder, workspace_for=composition.workspace_for,
                              ceiling=paid.Ceiling(96, launch.USD_MAX, launch.PER_ATTEMPT_USD), write=lambda _r: None, write_answers=lambda _a: None, expected_inputs=expected)
            refused = report["rows"][-1]
            assert (refused["guard_refusal"], refused["position"], len(provider.calls)) == (reason, position, position - 1), "refused before forwarding"


@pytest.mark.parametrize(("change", "reason"), [
    ({"gate": {"sends": 25}}, "the gate's schedule counts are not the cases'"),
    ({"budget": {"outline_available": True, "rows": [{"passes": False}]}}, "the budget report does not pass its gates"),
    ({"budget": {"outline_available": False, "rows": [{}]}}, "the outline's availability is not the budget report's"),
    ({"gate": {"digests": {}}}, "the gate does not pin tools/plan12_memory/m2b_launch.py"),
    ({"gate": {"digests": {**_gate()["digests"], "tools/plan12_memory/m2b_paid.py": "hex:" + "0" * 64}}}, "tools/plan12_memory/m2b_paid.py is not the gate's"),
    ({"gate": {"registry_hash": "0" * 64}}, "the registry is not the gate's"),
    ({"gate": {"tariff": {**launch.tariff_record(), "output_usd_per_million": "2.00"}}}, "the tariff is not the gate's"),
    ({"gate": {"usd_max": "7.00"}}, "the gate's release bounds are not the frozen"),
    ({"gate": {"per_attempt_usd": "0.01"}}, "the gate's release bounds are not the frozen"),
    ({"frozen": (36, 25, 11)}, "not the frozen (36, 25, 11)"),
])
def test_the_preflight_refuses_unless_the_release_and_the_gate_hold(change, reason, frozen, gates_pass, monkeypatch):
    budget = {"outline_available": True, "rows": [{}]}
    ceiling = launch.preflight(_cases(), u_equals_b=True, outline_available=True, budget_report=budget, gate=_gate(), snapshot=trusted_snapshot(), repository=ROOT)
    assert (ceiling.attempts_max, ceiling.usd_max, ceiling.per_attempt_usd) == (96, launch.USD_MAX, launch.PER_ATTEMPT_USD), "the frozen bounds, never the caller's"
    if "frozen" in change:
        monkeypatch.setattr(launch, "FROZEN_COUNTS", change["frozen"])
    with pytest.raises(launch.LaunchRefused) as refused:
        launch.preflight(_cases(), u_equals_b=True, outline_available=True, budget_report=change.get("budget", budget), gate={**_gate(), **change.get("gate", {})},
                         snapshot=trusted_snapshot(), repository=ROOT)
    assert reason in str(refused.value)


COMMENT = "https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/548#issuecomment-"


def _repository(tmp_path: Path, gate: dict | None) -> tuple[Path, dict[str, Any]]:
    repo = tmp_path / "repo"
    (repo / Path(launch.CONTRACT).parent).mkdir(parents=True)
    data = json.dumps({"q_launch": gate} if gate is not None else {}).encode()
    (repo / launch.CONTRACT).write_bytes(data)
    for args in (("init", "-q"), ("add", "-A"), ("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "c")):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    return repo, {"head": head, "contract_sha256": "hex:" + hashlib.sha256(data).hexdigest(), "reviews": {"fable": COMMENT + "1", "codex": COMMENT + "2"}}


def test_the_release_must_name_the_clean_head_the_contracts_bytes_and_both_reviews(tmp_path):
    repo, release = _repository(tmp_path, {"sends": 25})
    assert launch.verify_release(repo, release)[1] == {"sends": 25}
    for changed, reason in (({"head": "0" * 40}, "not the released head"), ({"contract_sha256": "hex:" + "0" * 64}, "not the released bytes"),
                            ({"reviews": {"fable": COMMENT + "1"}}, "both review comments"), ({"reviews": {"fable": COMMENT + "1", "codex": COMMENT + "1"}}, "distinct"),
                            ({"reviews": {"fable": COMMENT + "1", "codex": "#548 comment 2"}}, "both review comments")):
        with pytest.raises(launch.LaunchRefused, match=reason):
            launch.verify_release(repo, {**release, **changed})
    (repo / launch.CONTRACT).write_text("{}", encoding="utf-8")
    with pytest.raises(launch.LaunchRefused, match="uncommitted changes"):
        launch.verify_release(repo, release)
    bare, bare_release = _repository(tmp_path / "bare", None)
    with pytest.raises(launch.LaunchRefused, match="no q_launch gate"):
        launch.verify_release(bare, bare_release)


def _g2() -> dict[str, Any]:
    gate = _gate()
    return {"passes": True, "pinned": dict(gate["digests"]), "registry_hash": gate["registry_hash"], "tariff_id": paid.D3_TARIFF.id,
            "cases_sha256": launch.sc.SEALED_CASES_SHA256}


def test_the_paid_run_needs_a_passing_g2_report_that_ran_the_gates_files_and_composition():
    gate = _gate()
    for accepted in (_g2(), {**_g2(), "pinned": {**_g2()["pinned"], launch.SCORER: "hex:" + "1" * 64}}):  # the scorer may have its G3 successor pin
        try:
            launch.verify_g2(accepted, gate)
        except launch.LaunchRefused as refused:
            pytest.fail(f"a G2 report the gate accepts was refused: {refused}")
    for changed, reason in (({"passes": False}, "did not pass"), ({"pinned": {**_g2()["pinned"], "tools/plan12_memory/m2b_launch.py": "hex:0"}}, "ran another tools/plan12_memory/m2b_launch.py"),
                            ({"registry_hash": "0" * 64}, "another composition"), ({"cases_sha256": "hex:0"}, "another composition or cases")):
        with pytest.raises(launch.LaunchRefused, match=reason):
            launch.verify_g2({**_g2(), **changed}, gate)


def test_at_paid_time_a_row_whose_pack_generation_or_tree_is_not_the_dry_passs_is_refused_before_its_request(tree):
    composition = _composition(tree)
    context = "the pack\n--- scope: index generation 3, complete; ---"
    dry = {"case_id": "QR1", "arm": "B", "sent": True, "tree": composition.trees[SNAP], "epoch": 3, "pack_sha256": "hex:" + hashlib.sha256(b"the pack").hexdigest()}
    launch.Evidence(composition, _cases(), expected=[dry]).observe(SimpleNamespace(run_id="m2b-q-QR1-B"), SimpleNamespace(text=context))
    for changed, reason in (({"pack_sha256": "hex:0"}, "the pack is not the dry pass's"), ({"epoch": 4}, "the scope line's generation is not the dry pass's"),
                            ({"tree": "git:other"}, "the source tree is not the dry pass's")):
        evidence = launch.Evidence(composition, _cases(), expected=[{**dry, **changed}])
        with pytest.raises(paid.GuardRefused, match=reason):
            evidence.observe(SimpleNamespace(run_id="m2b-q-QR1-B"), SimpleNamespace(text=context))
        assert evidence.refusals == {"m2b-q-QR1-B": reason}


def test_a_gate_artifact_is_read_only_from_its_verified_bytes(tmp_path):
    (tmp_path / "a.json").write_text('{"x": 1}', encoding="utf-8")
    spec = {"path": "a.json", "sha256": "hex:" + hashlib.sha256(b'{"x": 1}').hexdigest()}
    assert launch.load_artifact(tmp_path, spec) == {"x": 1}
    with pytest.raises(launch.LaunchRefused, match="not the gate's bytes"):
        launch.load_artifact(tmp_path, {**spec, "sha256": "hex:" + "0" * 64})


def test_text_sinks_must_be_outside_the_repository_and_keep_each_request_by_its_digest(tmp_path):
    with pytest.raises(launch.LaunchRefused, match="outside the repository"):
        launch._sink(ROOT / "tmp" / "sink", ROOT)  # noqa: SLF001
    sink = launch._sink(tmp_path / "sink", ROOT)  # noqa: SLF001
    write = launch.input_sink(sink)
    write("hex:1", "first request")
    write("hex:2", "second\nrequest")
    assert [json.loads(line) for line in (sink / "inputs.jsonl").read_text(encoding="utf-8").splitlines()] == [
        {"input_sha256": "hex:1", "text": "first request"}, {"input_sha256": "hex:2", "text": "second\nrequest"}]


# --- waiting for an index --------------------------------------------------------------------------------------------------------

class _Waiting:
    """A session double: a worker outcome, a live generation and a catalogue that is read after `reads` asks."""

    def __init__(self, state: str = "complete", detail: str = "", reads: int = 1) -> None:
        self._last_outcome = SimpleNamespace(state=state, detail=detail)
        self._unusable = None
        self.asks: list[int] = []
        self.reads = reads
        self.storage = SimpleNamespace(call=lambda op: {"current": {"epoch": 7}})

    def _current_scope(self) -> Any:
        return SimpleNamespace(storage=self.storage)

    def _catalogue_for(self, scope: Any, epoch: int, complete: bool) -> list | None:
        self.asks.append(epoch)
        return [] if len(self.asks) > self.reads else None

    def wait_for_catalogue(self, timeout: float) -> bool:
        return True

    def status(self) -> str:
        return "Context index: status"


def test_waiting_for_an_index_holds_the_catalogue_for_the_published_generation():
    session = _Waiting(reads=2)
    assert launch.wait_indexed(session, 5) == 7 and session.asks == [7, 7, 7]


def test_a_refused_index_worker_stops_the_wait_with_its_reason():
    with pytest.raises(launch.LaunchRefused, match=r"refused \(STORE_FULL\)"):
        launch.wait_indexed(_Waiting(state="refused", detail="STORE_FULL"), 5)


# --- the G2 driver ---------------------------------------------------------------------------------------------------------------

@pytest.fixture
def driver(tmp_path, tree, monkeypatch):
    """run_gate with its infrastructure doubled: provisioning, the embedder and the index sessions; everything else is the real path."""
    calls: dict[str, list] = {"open": [], "removed": [], "rehearse": []}
    monkeypatch.setattr(launch.m1_scale, "_provision", lambda config, repository, work, **_kw: (tmp_path, SimpleNamespace(), None, SimpleNamespace(close=lambda: None),
                                                                                         SimpleNamespace(kill=lambda: None, wait=lambda s: None), None, {}))
    monkeypatch.setattr(launch, "_embedder", lambda *a: SimpleNamespace(embedded=0, reused=0))
    monkeypatch.setattr(launch, "_remove_container", lambda config: calls["removed"].append(config["container"]))

    def open_sessions(revisions, *, composition, **_kw):
        calls["open"].append(list(revisions))
        for snapshot in revisions:
            composition.sessions[snapshot], composition.workspaces[snapshot] = _ready_session(tree, 3), tree

    monkeypatch.setattr(launch, "open_sessions", open_sessions)
    monkeypatch.setattr(launch, "rehearse", lambda *a, **k: calls["rehearse"].append(1) or {"passes": True})
    config = {"cases": "reports/plan12-memory-m2b/cases.json", "work_dir": str(tmp_path / "work"), "label": "test", "container": "p1214-x", "volume": "p1214-v",
              "release_prefix": "p1214-"}
    return config, calls, tmp_path / "gate.json"


def test_the_driver_stops_after_a_failed_smoke_before_indexing_the_rest_and_keeps_its_report(driver, monkeypatch):
    config, calls, out = driver
    monkeypatch.setattr(launch, "smoke", lambda *a, **k: {"passes": False, "problems": ["guard refusal: x"]})
    report = launch.run_gate(config, ROOT, out)
    assert report["passes"] is False and len(calls["open"]) == 1 and len(calls["open"][0]) == 1 and calls["rehearse"] == [] and calls["removed"] == ["p1214-x"]
    assert json.loads(out.read_text(encoding="utf-8"))["smoke"]["problems"] == ["guard refusal: x"]


def test_the_driver_stops_after_failed_budget_gates_before_the_rehearsal(driver, monkeypatch):
    config, calls, out = driver
    monkeypatch.setattr(launch, "smoke", lambda *a, **k: {"passes": True})
    monkeypatch.setattr(launch.ev, "_budget_cases", lambda *a, **k: [])
    report = launch.run_gate(config, ROOT, out)
    assert report["passes"] is False and [len(r) for r in calls["open"]] == [1, 4] and calls["rehearse"] == [] and calls["removed"] == ["p1214-x"]
    assert json.loads(out.read_text(encoding="utf-8"))["budget"]["budget_gates"]["passes"] is False


def test_a_failed_start_still_removes_the_container_and_keeps_why(driver, monkeypatch):
    config, calls, out = driver

    def fails(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("the container never answered")

    monkeypatch.setattr(launch.m1_scale, "_provision", fails)
    try:
        launch.run_gate(config, ROOT, out)
    except RuntimeError:
        pass
    else:
        pytest.fail("the failed start was swallowed")
    assert calls["removed"] == ["p1214-x"] and json.loads(out.read_text(encoding="utf-8"))["failed"] == "RuntimeError"


@pytest.mark.parametrize(("listing", "reason"), [((0, "abc123\n"), "teardown left the released container behind"),
                                                 ((1, ""), "teardown could not confirm the released container is gone")])
def test_teardown_confirms_the_released_container_and_volume_are_gone(monkeypatch, listing, reason):
    commands: list[list[str]] = []
    left = [(0, "")]  # the first teardown finds nothing left

    def docker(command: list[str], **_kw: Any) -> Any:
        commands.append(command)
        if command[1] == "ps":
            return SimpleNamespace(returncode=left[-1][0], stdout=left[-1][1])
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(launch.subprocess, "run", docker)
    launch._remove_container({"container": "p1214-x", "volume": "p1214-v"})  # noqa: SLF001 - nothing listed: both gone
    assert commands[:2] == [["docker", "rm", "-f", "p1214-x"], ["docker", "volume", "rm", "-f", "p1214-v"]]
    left.append(listing)
    with pytest.raises(launch.LaunchRefused, match=reason):
        launch._remove_container({"container": "p1214-x", "volume": "p1214-v"})  # noqa: SLF001


def test_every_session_closes_even_if_others_fail_to_and_each_failure_is_named(tree):
    closed: list[str] = []

    def failing(name: str, error: type[Exception]) -> Any:
        def close() -> None:
            closed.append(name)
            raise error("would not close")
        return close

    sessions = {"git:" + "a" * 40: SimpleNamespace(close=failing("a", RuntimeError)), "git:" + "b" * 40: SimpleNamespace(close=lambda: closed.append("b")),
                "git:" + "c" * 40: SimpleNamespace(close=failing("c", OSError))}
    try:
        launch._close_sessions(launch.Composition(trusted_snapshot(), "s" * 64, LEGACY, sessions, {}))  # noqa: SLF001
    except launch.LaunchRefused as refused:
        assert str(refused) == f"sessions did not close: {'a' * 12} (RuntimeError), {'c' * 12} (OSError)"
    except Exception as other:  # noqa: BLE001 - a session's own error escaping means the rest were never closed
        pytest.fail(f"a session's {type(other).__name__} escaped before every session was closed")
    else:
        pytest.fail("sessions that would not close were not reported")
    assert closed == ["a", "b", "c"]


def test_a_snapshot_is_bound_to_its_frozen_source_tree_and_its_checkout_to_the_commit_made_when_materialized(tmp_path, monkeypatch):
    """Codex round 124 attempt 4: an export-ignored file (7abbaa2's PDFs) makes the archive-made checkout's tree differ from the revision's;
    the row seals the revision's own tree, and the drift check holds the checkout to the commit materialize made."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "kept.py").write_text("x = 1\n", encoding="utf-8")
    (source / "paper.pdf").write_bytes(b"%PDF")
    (source / ".gitattributes").write_text("*.pdf export-ignore\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "init", "-q"], check=True, capture_output=True)
    _commit(source)
    revision = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    session = _Waiting()
    session.start = lambda: None
    session.storage = SimpleNamespace(call=lambda op: {"current": {"epoch": 7, "coverage": {"complete": True}}})
    monkeypatch.setattr("optimus.context.memory_session.session_factory", lambda **kwargs: lambda _ws: session)
    composition = launch.Composition(trusted_snapshot(), "s" * 64, LEGACY, {}, {})
    recorded: list[dict] = []
    launch.open_sessions([f"git:{revision}"], repository=source, work=tmp_path / "work", root=tmp_path, memory=None, settings=None,
                         settings_file={"embedding": {"artifact_directory": "a"}}, embedder=None, composition=composition, trees=recorded)
    checkout = composition.workspaces[f"git:{revision}"]
    source_tree = "git:" + subprocess.run(["git", "-C", str(source), "rev-parse", f"{revision}^{{tree}}"], check=True, capture_output=True, text=True).stdout.strip()
    assert composition.trees[f"git:{revision}"] == source_tree != launch.checkout_tree(checkout), "the row seals the revision's own tree"
    assert composition.heads[f"git:{revision}"] == launch.checkout_head(checkout) and launch.checkout_drift(checkout, composition.heads[f"git:{revision}"]) is None
    [entry] = recorded
    assert (entry["tree"], entry["checkout_head"], entry["checkout_tree"]) == (source_tree, launch.checkout_head(checkout), launch.checkout_tree(checkout))


def test_an_index_gateway_that_dies_after_it_starts_is_still_stopped_with_its_client_and_container(tmp_path, monkeypatch):
    """Codex round 124 attempt 3, A3: through the real m1_scale._provision, a failure after the Gateway process starts but before it
    reports its port still stops it, closes the Redis client and removes the container, in that order."""
    events: list[str] = []
    (tmp_path / "artifacts" / "snapshot").mkdir(parents=True)
    memory = SimpleNamespace(port=1, user="u", resource="r", credential_name="c")
    scale = launch.m1_scale
    monkeypatch.setattr(scale.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=""))
    monkeypatch.setattr("optimus.acp.memory_setup.shipped_defaults", lambda: {})
    monkeypatch.setattr(scale, "run_setup", lambda config_root, *, keyring_backend, **_k: keyring_backend.set_password(scale.KEYRING_SERVICE, "c", "pw"))
    monkeypatch.setattr(scale, "memory_index_root", lambda root: tmp_path)
    monkeypatch.setattr(scale, "read", lambda root: (None, memory, None))
    monkeypatch.setattr(scale.local_infra, "ensure_memory_redis", lambda root: SimpleNamespace(state="ready"))
    monkeypatch.setattr(scale.memory_index, "connect", lambda endpoint: SimpleNamespace(ping=lambda: True, close=lambda: events.append("client closed")))

    class Dies:  # starts, then exits before saying its port
        stdin = SimpleNamespace(write=lambda text: None, flush=lambda: None)
        stdout = SimpleNamespace(readline=lambda: "")

        def kill(self) -> None:
            events.append("gateway stopped")

        def wait(self, seconds: float) -> int:
            return 1

    monkeypatch.setattr(scale.subprocess, "Popen", lambda *a, **k: Dies())
    monkeypatch.setattr(launch, "_remove_container", lambda config: events.append("container removed"))
    config = {"container": "p1214-x", "volume": "p1214-v", "release_prefix": "p1214-", "artifact_cache": str(tmp_path / "artifacts"), "port": 1, "maxmemory_mb": 1}
    try:
        with launch.provisioned(config, tmp_path, tmp_path / "work", launch.Composition(trusted_snapshot(), "s" * 64, LEGACY, {}, {})):
            pytest.fail("provisioned with a dead index Gateway")
    except ValueError:
        pass
    assert events == ["gateway stopped", "client closed", "container removed"]


def test_a_failed_run_whose_teardown_also_fails_keeps_both_failures(driver, monkeypatch):
    config, calls, out = driver

    def broken(*_a: Any, **_k: Any) -> Any:
        raise launch.LaunchRefused("the smoke row could not be prepared")

    def left_behind(config: dict) -> None:
        raise launch.LaunchRefused("teardown left the released container behind")

    monkeypatch.setattr(launch, "smoke", broken)
    monkeypatch.setattr(launch, "_remove_container", left_behind)
    try:
        launch.run_gate(config, ROOT, out)
    except launch.LaunchRefused:
        pass
    else:
        pytest.fail("a failed run returned")
    kept = json.loads(out.read_text(encoding="utf-8"))
    assert (kept["passes"], kept["failures"]) == (False, ["teardown left the released container behind", "the smoke row could not be prepared"])


def test_the_paid_entry_refuses_a_failing_preflight_before_provisioning_anything(tmp_path, monkeypatch):
    """Codex round 124 attempt 3, B1: the release, the gate, the G2 report and the whole preflight are checked before any container or index."""
    gate = {**_gate(), "tariff": {**launch.tariff_record(), "output_usd_per_million": "9.99"}, "g2_report": {"path": "g2.json", "sha256": ""}}
    gate["digests"][launch.CASES] = launch.sc.SEALED_CASES_SHA256
    g2 = json.dumps({"passes": True, "pinned": gate["digests"], "registry_hash": gate["registry_hash"], "tariff_id": paid.D3_TARIFF.id, "cases_sha256": launch.sc.SEALED_CASES_SHA256,
                     "budget": {"outline_available": True, "rows": []}}).encode()
    gate["g2_report"]["sha256"] = "hex:" + hashlib.sha256(g2).hexdigest()
    repo = tmp_path / "repo"
    (repo / Path(launch.CASES).parent).mkdir(parents=True)
    (repo / launch.CASES).write_bytes((ROOT / launch.CASES).read_bytes())
    (repo / "g2.json").write_bytes(g2)
    contract = json.dumps({"q_launch": gate, "task1_freezes": {"selected_candidate": {"u_equals_b": True}}}).encode()
    (repo / launch.CONTRACT).write_bytes(contract)
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True, capture_output=True)
    _commit(repo)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    release = {"head": head, "contract_sha256": "hex:" + hashlib.sha256(contract).hexdigest(), "reviews": {"fable": COMMENT + "1", "codex": COMMENT + "2"}}
    monkeypatch.setenv("OPTIMUS_API_KEY", "k" * 32)
    monkeypatch.setattr(launch.m1_scale, "_provision", lambda *a, **k: pytest.fail("provisioned before the preflight held"))
    monkeypatch.setattr(launch, "_remove_container", lambda config: pytest.fail("touched Docker before the preflight held"))
    try:
        launch.run_paid({"sink_dir": str(tmp_path / "sink"), "work_dir": str(tmp_path / "work")}, repo, release, tmp_path / "paid.json")
    except launch.LaunchRefused as refused:
        assert str(refused).startswith("preflight: ") and "the tariff is not the gate's" in str(refused)
    except Exception as other:  # noqa: BLE001 - anything else means the preflight did not come first
        pytest.fail(f"the paid entry went on past a failing preflight and raised {type(other).__name__}")
    else:
        pytest.fail("the paid entry went on past a failing preflight")


def test_a_teardown_failure_after_a_passing_rehearsal_is_no_pass(driver, monkeypatch):
    """Codex round 124 attempt 2, A3: the gate passes only once every resource is torn down and confirmed gone."""
    config, calls, out = driver
    monkeypatch.setattr(launch, "smoke", lambda *a, **k: {"passes": True})
    monkeypatch.setattr(launch.ev, "_budget_cases", lambda *a, **k: [])
    monkeypatch.setattr(launch.ev, "budget_gates", lambda rows, outline_available: {"passes": True})

    def left_behind(config: dict) -> None:
        calls["removed"].append(config["container"])
        raise launch.LaunchRefused("teardown left the released container behind")

    monkeypatch.setattr(launch, "_remove_container", left_behind)
    try:
        launch.run_gate(config, ROOT, out)
    except launch.LaunchRefused as refused:
        assert str(refused) == "teardown left the released container behind"
    else:
        pytest.fail("a run that left its container behind returned")
    kept = json.loads(out.read_text(encoding="utf-8"))
    assert calls["rehearse"] == [1] and calls["removed"] == ["p1214-x"] and (kept["passes"], kept["failed"]) == (False, "teardown left the released container behind")


def test_unreleased_names_are_refused_before_anything_is_created_or_removed(driver, monkeypatch):
    config, calls, out = driver
    monkeypatch.setattr(launch.m1_scale, "_provision", lambda *a, **k: pytest.fail("provisioned under an unreleased name"))
    try:
        launch.run_gate({**config, "container": "someone-elses"}, ROOT, out)
    except launch.LaunchRefused as refused:
        assert str(refused) == "only the released container and volume"
    else:
        pytest.fail("ran under an unreleased name")
    assert calls["removed"] == [], "nothing removed under a name the release does not cover"


def test_the_driver_refuses_unsealed_cases_before_provisioning(driver, monkeypatch, tmp_path):
    config, _calls, out = driver
    (tmp_path / "cases.json").write_bytes((ROOT / config["cases"]).read_bytes() + b" ")
    monkeypatch.setattr(launch.m1_scale, "_provision", lambda *a, **k: pytest.fail("provisioned with unsealed cases"))
    try:
        launch.run_gate({**config, "cases": str(tmp_path / "cases.json")}, ROOT, out)
    except launch.LaunchRefused as refused:
        assert str(refused) == "the cases are not the sealed bytes"
    else:
        pytest.fail("the driver ran on unsealed cases")


@pytest.mark.parametrize("name", launch.PROVIDER_KEY_NAMES)
def test_the_gate_driver_refuses_with_a_provider_key_in_the_environment_before_provisioning_anything(monkeypatch, tmp_path, name):
    """G2 runs with no provider key in the environment (Fable gate consult), checked before any container, index or file is touched."""
    monkeypatch.setenv(name, "a-key")
    monkeypatch.setattr(launch.m1_scale, "_provision", lambda *a, **k: pytest.fail("provisioned with a provider key present"))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "run-config.json").write_text("{}", encoding="utf-8")
    try:
        launch.main(["--phase", "gate", "--config", "run-config.json", "--output", "gate.json"])
    except launch.LaunchRefused as refused:
        assert str(refused) == f"a provider key is in the environment: {name}"
    except Exception as other:  # noqa: BLE001 - anything else means the check did not come first
        pytest.fail(f"the driver went on with a provider key present and raised {type(other).__name__}")
    else:
        pytest.fail("the driver ran with a provider key present")
