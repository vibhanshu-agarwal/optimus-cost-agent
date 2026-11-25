"""Plan 12.14 Q launcher (gate G1b), zero paid: production's shipped D3 composition (the trusted registry) driven through the paid runner, the
real Gateway handler in process over a scripted provider, and memory turns on a real MemorySession over fake index storage."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import fields
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from optimus.context.context_budget import BudgetPolicy
from optimus.context.shipped_policy import attachment_limits
from optimus_model_policy.binding import trusted_snapshot
from tests.unit.context.test_memory_tools_and_turns import _session, _Storage, workspace  # noqa: F401 - fixture
from tests.unit.tools.test_plan12_memory_m2b_paid import no_sleep  # noqa: F401 - fixture
from tests.unit.tools.test_plan12_memory_m2b_production_bytes import LOADER, TASK, _records
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


def _cases() -> list[dict[str, Any]]:
    return [{"case_id": f"{prefix}{n}", "category": category, "kind": None, "snapshot": SNAP, "task": TASK, "required_files": [{"path": "pkg/a.py"}],
             "forced_refusal": dict.fromkeys("NBUF", False)}
            for category, prefix in (("ranking", "QR"), ("budget", "QB"), ("outline", "QO")) for n in range(1, 5)]


@pytest.fixture
def tree(workspace: Path) -> Path:  # noqa: F811
    (workspace / "pkg" / "b.py").write_text(LOADER, encoding="utf-8", newline="\n")
    return workspace


class _Vectors:
    def embed(self, texts: list[str]) -> list[bytes]:
        return [struct.pack("<4f", 1.0, 0.0, 0.0, 0.0) for _ in texts]


def _composition(tree: Path, *, epoch: int = 3, **storage: Any) -> launch.Composition:
    """An indexed session as the launcher leaves one: its embedder loaded and its catalogue read (wait_indexed)."""
    session = _session(tree, _Epoch(_records(), epoch, **storage))
    session._embedder = _Vectors()  # noqa: SLF001
    session.turn()._retriever.retrieve("prime")  # noqa: SLF001
    assert session.wait_for_catalogue(5)
    return launch.Composition(trusted_snapshot(), "s" * 64, LEGACY, {SNAP: session}, {SNAP: tree})


def _rehearse(composition: launch.Composition, *, budget_report: dict | None = None) -> dict[str, Any]:
    provider = launch.ScriptedProvider(trusted_snapshot())
    return launch.rehearse(_cases(), composition, gateway=launch.local_client(composition.snapshot, composition.shared_secret, provider), provider=provider,
                           u_equals_b=True, outline_available=True, budget_report=budget_report)


def _gate() -> dict[str, Any]:
    rel = "tools/plan12_memory/m2b_paid.py"
    return {"sends": 36, "digests": {rel: "hex:" + hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()}, "registry_hash": trusted_snapshot().effective_hash,
            "tariff_id": paid.D3_TARIFF.id}


BUDGET_OK: dict[str, Any] = {"budget_gates": {"passes": True}, "outline_available": True, "rows": []}


def test_each_arm_is_productions_d3_composition_with_only_bs_pack_budget_replaced(tree, monkeypatch):
    """The shipped registry's attachment for the D3 model, as ordinary_attachment builds it; B differs only in its pack budget; the binder is
    production's RoutePolicy for the model's implementer role with Q's output cap; N has no memory turn and B/F join one."""
    composition = _composition(tree)
    shipped = attachment_limits(composition.snapshot, launch.D3_MODEL)
    built = launch.ordinary_attachment(snapshot=composition.snapshot, model_id=launch.D3_MODEL, gateway_client=composition.summaries, shared_secret=composition.shared_secret)
    assert (built.pack_budget, built.model_id, built.registry_hash) == (shipped.pack_budget, launch.D3_MODEL, composition.snapshot.effective_hash)
    assert built.pack_budget.name == "model-aware" and built.pack_budget.ceiling == 32_768
    asked: list[dict] = []
    monkeypatch.setattr(launch, "ordinary_attachment", lambda **kwargs: asked.append(kwargs) or built)
    f, b = composition.attachment("F"), composition.attachment("B")
    assert f is built and b.pack_budget == LEGACY
    assert [x.name for x in fields(f) if getattr(f, x.name) is not getattr(b, x.name)] == ["pack_budget"], "B replaces only the pack budget"
    assert all(kw["gateway_client"] is composition.summaries and kw["model_id"] == launch.D3_MODEL for kw in asked), "summaries go to the refusing client"
    monkeypatch.undo()
    with pytest.raises(launch.LaunchRefused):
        composition.attachment("U")
    binder = composition.binder(_cases()[0], "F")
    assert (binder.output_cap, binder.identity.model_id) == (paid.OUTPUT_CAP, launch.D3_MODEL)
    case = _cases()[0]
    assert composition.packer(case, "N").memory is None and composition.packer(case, "F").memory is not None and composition.packer(case, "B").memory is not None


def test_the_rehearsal_sends_every_row_once_and_seals_what_the_paid_run_must_reproduce(tree):
    record = _rehearse(_composition(tree))
    assert record["passes"], record["problems"]
    assert (record["sends"], record["provider_calls"], record["summary_calls"]) == (36, 36, 0)
    for row in record["rows"]:
        memory = row["arm"] != "N"
        assert row["sent"] and row["limit_line"] is memory and (row["pack_sha256"] is not None) is memory, row
        assert row["binding"] == {"registry_hash": trusted_snapshot().effective_hash, "model": launch.D3_MODEL, "output_cap": paid.OUTPUT_CAP}
        assert row["input_masked_sha256"] != row["input_sha256"] or not memory, "a memory row's scope line names its generation"
    by_arm = {row["arm"]: row["pack_sha256"] for row in record["rows"] if row["case_id"] == "QB1"}
    assert by_arm["B"] != by_arm["F"], "B packs under the legacy budget, F under the route's own"


def test_a_rebuilt_index_at_a_new_generation_still_matches_the_sealed_rehearsal_and_gives_its_own_exact_inputs(tree):
    """The epoch is a global counter (Fable gate consult): only the masked input is sealed, and the dry pass's exact inputs are the paid ones."""
    sealed, dry = _rehearse(_composition(tree, epoch=3)), _rehearse(_composition(tree, epoch=4))
    expected = launch.compare(sealed, dry)
    assert len(expected) == 36 and expected == {(r["case_id"], r["arm"]): r["input_sha256"] for r in dry["rows"]}
    assert any(r["input_sha256"] != s["input_sha256"] for r, s in zip(dry["rows"], sealed["rows"], strict=True)), "the exact inputs moved with the generation"


@pytest.mark.parametrize("field", ["pack_sha256", "input_masked_sha256", "prefix_sha256", "limit_line", "terminal"])
def test_any_sealed_difference_refuses_the_launch(tree, field):
    sealed, dry = _rehearse(_composition(tree)), _rehearse(_composition(tree))
    sealed["rows"][4] = {**sealed["rows"][4], field: "something else"}
    with pytest.raises(launch.LaunchRefused, match=field):
        launch.compare(sealed, dry)


def test_degraded_retrieval_fails_the_rehearsal(tree):
    record = _rehearse(_composition(tree, complete=False))
    assert not record["passes"] and any("index coverage incomplete" in p for p in record["problems"])
    assert launch.degraded({"retrieval": {"state": "ok", "coverage": {"complete": True}, "channels": {"memory": "no authorized source", "lexical": "3 results"}}}) == []
    assert launch.degraded({"retrieval": {"state": "ok", "coverage": {"complete": True}, "channels": {"catalogue": "not ready", "vector": "unavailable"}}}) == [
        "catalogue not ready", "channel vector: unavailable"]
    assert launch.degraded({"retrieval": {"state": "unpublished"}}) == ["retrieval state 'unpublished'", "index coverage incomplete"]


def test_the_rehearsal_checks_each_budget_cases_packs_against_the_budget_report(tree):
    composition = _composition(tree)
    honest = _rehearse(composition)
    packs = {(r["case_id"], r["arm"]): r["pack_sha256"] for r in honest["rows"]}
    report = {"rows": [{"case_id": "QB1", "arms": {"BU": {"pack_sha256": packs[("QB1", "B")]}, "F": {"pack_sha256": packs[("QB1", "F")]}}}]}
    assert _rehearse(_composition(tree), budget_report=report)["passes"]
    report["rows"][0]["arms"]["F"]["pack_sha256"] = packs[("QB1", "B")]
    assert _rehearse(_composition(tree), budget_report=report)["problems"] == ["QB1/F: the pack is not the budget report's"]


class _NWithMemory(launch.Composition):
    def packer(self, case: dict, arm: str) -> Any:
        attached = super().packer(case, arm)
        if arm == "N":
            attached.memory = self.sessions[case["snapshot"]].turn()
        return attached


def test_a_row_whose_limit_line_is_not_its_arms_fails_the_rehearsal(tree):
    """B and F send the runner's limit observation (the indexed Chat builder, tools withdrawn); N, with no memory turn, does not."""
    plain = _composition(tree)
    record = _rehearse(_NWithMemory(plain.snapshot, plain.shared_secret, LEGACY, plain.sessions, plain.workspaces))
    assert {p for p in record["problems"] if p.endswith("limit line is present")} == {f"{c['case_id']}/N: the limit line is present" for c in _cases()}


def test_a_provider_call_the_schedule_did_not_send_fails_the_rehearsal(tree):
    composition = _composition(tree)
    provider = launch.ScriptedProvider(trusted_snapshot())
    provider.calls = 1
    record = launch.rehearse(_cases(), composition, gateway=launch.local_client(composition.snapshot, composition.shared_secret, provider), provider=provider,
                             u_equals_b=True, outline_available=True, budget_report=None)
    assert record["problems"] == ["37 provider calls for 36 sends"]


def test_a_summary_call_fails_the_rehearsal(tree):
    composition = _composition(tree)
    composition.summaries.calls = 1
    assert "1 summary calls; a Q row never summarizes" in _rehearse(composition)["problems"]


def _launch(tree: Path, sealed: dict, *, gate: dict | None = None, budget: dict | None = None) -> tuple[launch.ScriptedProvider, dict | None]:
    provider = launch.ScriptedProvider(trusted_snapshot())  # the paid Gateway's stand-in
    composition = _composition(tree, epoch=9)
    kept: list[tuple[str, str]] = []
    report = launch.paid_launch(_cases(), composition, gateway=launch.local_client(composition.snapshot, composition.shared_secret, provider), sealed=sealed,
                                budget_report=budget or BUDGET_OK, gate=gate or _gate(), ceiling=paid.Ceiling(96, Decimal("6.00"), launch.PER_ATTEMPT_USD),
                                u_equals_b=True, outline_available=True, repository=ROOT, write=lambda _r: None, write_answers=lambda _a: None,
                                write_input=lambda sha, text: kept.append((sha, text)))
    assert len(kept) == provider.calls
    return provider, report


def test_the_paid_launch_forwards_each_rows_dry_pass_input_only_after_every_row_matches(tree):
    provider, report = _launch(tree, _rehearse(_composition(tree)))
    assert report is not None and report["stopped"] is None and provider.calls == 36
    assert all(row["guard_refusal"] is None and row["terminal"] == "settled" for row in report["rows"])


def test_the_paid_launch_refuses_before_any_send_on_a_sealed_difference(tree):
    sealed = _rehearse(_composition(tree))
    sealed["rows"][7] = {**sealed["rows"][7], "pack_sha256": "hex:" + "0" * 64}
    provider = launch.ScriptedProvider(trusted_snapshot())
    with pytest.raises(launch.LaunchRefused, match="differs from the sealed rehearsal"):
        composition = _composition(tree)
        launch.paid_launch(_cases(), composition, gateway=launch.local_client(composition.snapshot, composition.shared_secret, provider), sealed=sealed,
                           budget_report=BUDGET_OK, gate=_gate(), ceiling=paid.Ceiling(96, Decimal("6.00"), launch.PER_ATTEMPT_USD), u_equals_b=True,
                           outline_available=True, repository=ROOT, write=lambda _r: None, write_answers=lambda _a: None, write_input=lambda _s, _t: None)
    assert provider.calls == 0


def test_a_row_the_dry_pass_did_not_prepare_is_refused_by_its_guard(tree):
    composition = _composition(tree)
    provider = launch.ScriptedProvider(trusted_snapshot())
    report = paid.run(_cases(), u_equals_b=True, outline_available=True, gateway=launch.local_client(composition.snapshot, composition.shared_secret, provider),
                      approved=composition.approved(), model=composition.model_id, packer_for=composition.packer, binder_for=composition.binder,
                      workspace_for=composition.workspace_for, ceiling=paid.Ceiling(96, Decimal("6.00"), launch.PER_ATTEMPT_USD), write=lambda _r: None,
                      write_answers=lambda _a: None, expected_inputs={})
    assert provider.calls == 0 and report["rows"][0]["guard_refusal"] == "the input is not the one the dry preparation pass prepared"


@pytest.mark.parametrize(("change", "reason"), [
    ({"gate": {"sends": 25}}, "36 sends, the gate has 25"),
    ({"budget": {**BUDGET_OK, "budget_gates": {"passes": False}}}, "the budget report does not pass"),
    ({"budget": {**BUDGET_OK, "outline_available": False}}, "the outline's availability is not the budget report's"),
    ({"gate": {"digests": {"tools/plan12_memory/m2b_paid.py": "hex:" + "0" * 64}}}, "tools/plan12_memory/m2b_paid.py is not the gate's"),
    ({"gate": {"registry_hash": "0" * 64}}, "the registry is not the gate's"),
    ({"gate": {"tariff_id": "another"}}, "the tariff is not the gate's"),
    ({"ceiling": paid.Ceiling(70, Decimal("6.00"), launch.PER_ATTEMPT_USD)}, "do not fit 70 attempts"),
    ({"ceiling": paid.Ceiling(96, Decimal("3.00"), launch.PER_ATTEMPT_USD)}, "do not fit 96 attempts and USD 3.00"),
])
def test_the_preflight_refuses_unless_the_release_and_the_gate_hold(change, reason):
    kwargs = {"budget_report": change.get("budget", BUDGET_OK), "gate": {**_gate(), **change.get("gate", {})},
              "ceiling": change.get("ceiling", paid.Ceiling(96, Decimal("6.00"), launch.PER_ATTEMPT_USD))}
    assert launch.preflight(_cases(), u_equals_b=True, outline_available=True, snapshot=trusted_snapshot(), repository=ROOT, budget_report=BUDGET_OK, gate=_gate(),
                            ceiling=paid.Ceiling(96, Decimal("6.00"), launch.PER_ATTEMPT_USD)) == 36
    with pytest.raises(launch.LaunchRefused) as refused:
        launch.preflight(_cases(), u_equals_b=True, outline_available=True, snapshot=trusted_snapshot(), repository=ROOT, **kwargs)
    assert reason in str(refused.value)


def test_masking_hides_only_the_index_generation():
    assert launch.masked_sha("a; index generation 3, complete") == launch.masked_sha("a; index generation 41, complete")
    assert launch.masked_sha("a; index generation 3, complete") != launch.masked_sha("b; index generation 3, complete")


@pytest.mark.parametrize("name", launch.PROVIDER_KEY_NAMES)
def test_the_gate_driver_refuses_with_a_provider_key_in_the_environment_before_provisioning_anything(monkeypatch, tmp_path, name):
    """G2 runs with no provider key in the environment (Fable gate consult), checked before any container, index or file is touched."""
    monkeypatch.setenv(name, "a-key")
    monkeypatch.setattr(launch.m1_scale, "_provision", lambda *a, **k: pytest.fail("provisioned with a provider key present"))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "run-config.json").write_text("{}", encoding="utf-8")
    try:
        launch.main(["--config", "run-config.json", "--output", "gate.json"])
    except launch.LaunchRefused as refused:
        assert str(refused) == f"a provider key is in the environment: {name}"
    except Exception as other:  # noqa: BLE001 - anything else means the check did not come first
        pytest.fail(f"the driver went on with a provider key present and raised {type(other).__name__}")
    else:
        pytest.fail("the driver ran with a provider key present")
