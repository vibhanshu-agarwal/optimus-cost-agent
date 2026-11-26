"""Plan 12.14 Task 1: the preparation-time budget. C, T and the chosen budget, field omission and the shared cache-write multiplier."""

from __future__ import annotations

from decimal import Decimal

import pytest

from context_engine.context_pack import chosen_budget
from optimus.context.context_budget import HARD_MAX_TOKENS, LEGACY_MAX_TOKENS, BudgetPolicy, legacy_budget, plan_budget, target_tokens
from optimus_model_policy.registry import CACHE_WRITE_INPUT_MULTIPLIER

D3_USABLE = min(1_000_000, 262_144) - 32_768  # Haiku 5.5's window, the 262,144 ceiling and the implementer reserve


def test_the_multiplier_is_shared_and_the_gateway_reserves_with_it():
    from optimus_gateway import responses

    assert CACHE_WRITE_INPUT_MULTIPLIER == Decimal("1.25")
    assert responses.CACHE_WRITE_INPUT_MULTIPLIER is CACHE_WRITE_INPUT_MULTIPLIER
    assert not hasattr(responses, "_CACHE_WRITE_INPUT_MULTIPLIER")


def test_the_plans_forecast_for_d3s_entry():
    assert D3_USABLE == 229_376
    policy = plan_budget(D3_USABLE, input_target_usd=Decimal("0.008192"), input_usd_per_million=Decimal("0.50"), cache_write=True)
    assert (policy.name, policy.ceiling, policy.target) == ("model-aware", 32_768, 13_107)
    assert plan_budget(D3_USABLE, input_target_usd=Decimal("0.008192"), input_usd_per_million=Decimal("0.50"), cache_write=False).target == 16_384
    assert legacy_budget(D3_USABLE) == 16_384


def test_an_entry_without_the_field_keeps_the_legacy_budget():
    policy = plan_budget(D3_USABLE, input_target_usd=None, input_usd_per_million=Decimal("0.50"), cache_write=True)
    assert policy == BudgetPolicy("legacy", LEGACY_MAX_TOKENS, None)
    assert plan_budget(20_000, input_target_usd=None, input_usd_per_million=Decimal("1"), cache_write=False).ceiling == 5_000


@pytest.mark.parametrize("usable, ceiling", [(229_376, HARD_MAX_TOKENS), (100_000, 25_000), (4, 1)])
def test_the_ceiling_is_a_quarter_of_usable_input_up_to_32768(usable, ceiling):
    assert plan_budget(usable, input_target_usd=Decimal("1"), input_usd_per_million=Decimal("1"), cache_write=False).ceiling == ceiling


def test_a_zero_price_targets_the_ceiling():
    policy = plan_budget(D3_USABLE, input_target_usd=Decimal("0.008192"), input_usd_per_million=Decimal("0"), cache_write=True)
    assert policy.target == policy.ceiling == 32_768


def test_the_target_is_estimator_tokens_floored():
    assert target_tokens(Decimal("0.008192"), Decimal("0.50"), cache_write=True) == 13_107  # 13,107.2
    assert target_tokens(Decimal("0.000001"), Decimal("3"), cache_write=False) == 0


@pytest.mark.parametrize("bad", [Decimal("0"), Decimal("-1"), Decimal("NaN")])
def test_a_target_must_be_a_positive_decimal(bad):
    with pytest.raises(ValueError):
        plan_budget(D3_USABLE, input_target_usd=bad, input_usd_per_million=Decimal("0.50"), cache_write=True)


@pytest.mark.parametrize(
    "ceiling, target, required, expected",
    [
        (32_768, 13_107, 0, 13_107),           # nothing required: the soft target
        (32_768, 13_107, 2_000, 13_107),       # ordinary fit: the target, the floor not binding
        (32_768, 13_107, 12_500, 13_524),      # the floor gives 1,024 of room above the required text
        (32_768, 13_107, 20_000, 21_024),      # required over the target: required wins, floor only
        (32_768, 13_107, 32_000, 32_768),      # the floor uses only the room there is
        (32_768, 13_107, 32_768, 32_768),      # equality: whole, no optional room
        (32_768, 40_000, 0, 32_768),           # a target above the ceiling is clipped
    ],
)
def test_chosen_budget(ceiling, target, required, expected):
    assert chosen_budget(ceiling, target, required) == expected


# --- The route's budget, bound before preparation (Task 2 seam) ----------------------------------------------------------


def test_the_shipped_route_keeps_the_legacy_budget_and_the_d3_target_gives_the_forecast(tmp_path):
    from optimus.context.shipped_policy import attachment_limits
    from optimus_model_policy.binding import packaged_defaults, trusted_snapshot
    from optimus_model_policy.registry import load_registry

    haiku = "anthropic/claude-haiku-5.5"
    assert attachment_limits(trusted_snapshot(), haiku).pack_budget == BudgetPolicy("legacy", 16_384, None)
    override = tmp_path / "override.yaml"
    override.write_text(f'models:\n  {haiku}:\n    context_budget: {{input_target_usd: "0.008192"}}\n', encoding="utf-8")
    staged = attachment_limits(load_registry(packaged_defaults(), override), haiku).pack_budget
    assert staged == BudgetPolicy("model-aware", 32_768, 13_107)  # Haiku's route caches its prefix, so a write is priced


def test_escalation_keeps_the_budget_the_pack_was_prepared_with():
    from dataclasses import replace

    from tests.unit.agent.test_context_selection import _attached_turn

    attached, _ = _attached_turn(usable=1100)
    assert attached.pack_budget == BudgetPolicy("legacy", 275, None)  # no budget on the attachment: legacy on its usable input
    prepared = BudgetPolicy("model-aware", 275, 200)
    attached._attachment = replace(attached._attachment, pack_budget=prepared)  # noqa: SLF001 - as bound before preparation
    attached.escalate_attachment(replace(attached._attachment, model_id="test/strong", usable_input_tokens=5_000, pack_budget=BudgetPolicy("legacy", 1_250, None)))  # noqa: SLF001
    assert attached.model_id == "test/strong" and attached.pack_budget == prepared


def _pack(required_bytes: int, *, budget: int, target: int | None):
    from context_engine.context_pack import assemble_pack
    from context_engine.retrieval import Hit, Ranked

    body = "".join(f"def f{i}():\n    return {i}\n" for i in range(2000)).encode()
    files = {"req.py": b"#" * required_bytes + b"\n", "opt.py": body}
    import hashlib

    digest = hashlib.sha256(body).hexdigest()
    ranked = [Ranked(Hit(id=str(i), kind="symbol", path="opt.py", file_hash=digest, symbol=f"f{i}", signature=f"def f{i}()", start_line=2 * i + 1, end_line=2 * i + 2), 1 / (60 + i), {"lexical": i + 1}) for i in range(2000)]
    return assemble_pack(required=("req.py",), ranked=ranked, read=files.get, estimate=lambda t: len(t.encode()), budget_tokens=budget, target_tokens=target)


def test_without_a_target_the_pack_is_unchanged_and_with_one_it_uses_the_chosen_budget():
    legacy = _pack(1_000, budget=16_384, target=None)
    assert legacy.budget_tokens == 16_384 and legacy.complete
    aware = _pack(1_000, budget=32_768, target=13_107)
    assert aware.complete and aware.budget_tokens == 13_107 and aware.tokens <= 13_107 < legacy.tokens


def test_required_text_between_legacy_and_the_ceiling_is_whole_with_a_floor_and_over_the_ceiling_is_incomplete():
    assert not _pack(20_000, budget=16_384, target=None).complete
    whole = _pack(20_000, budget=32_768, target=13_107)
    required = 20_000 + len("--- required files ---\n--- req.py ---\n") + 1
    assert whole.complete and whole.budget_tokens == required + 1_024 and whole.tokens <= whole.budget_tokens
    over = _pack(40_000, budget=32_768, target=13_107)
    assert not over.complete and over.missing_required == ("req.py",)


# --- the seam's middle links (Fable CP1 finding 7): each would pass silently if reverted ----------------------------------


def test_the_memory_turn_takes_the_routes_ceiling_and_target_or_the_legacy_budget():
    from optimus.context.memory_session import pack_limits

    assert pack_limits(None, 229_376) == (16_384, None)
    assert pack_limits(BudgetPolicy("model-aware", 32_768, 13_107), 229_376) == (32_768, 13_107)


def test_the_memory_turn_hands_the_target_to_the_pack(monkeypatch):
    import contextlib

    from context_engine.retrieval import Retrieval
    from optimus.context import memory_session

    seen: dict = {}

    def fake_pack(**kwargs):
        seen.update(kwargs)
        return type("P", (), {"stale_paths": ()})()

    monkeypatch.setattr(memory_session, "assemble_pack", fake_pack)
    turn = object.__new__(memory_session.MemoryTurn)
    turn._session = type("S", (), {"foreground": staticmethod(contextlib.nullcontext)})()  # noqa: SLF001
    turn._retriever = type("R", (), {"retrieve": staticmethod(lambda *_a, **_k: Retrieval("ok"))})()  # noqa: SLF001
    turn._read = lambda _p: None  # noqa: SLF001
    turn._cancelled = lambda: False  # noqa: SLF001
    turn._retrieve("task", (), len, 32_768, "task", 13_107)  # noqa: SLF001
    assert (seen["budget_tokens"], seen["target_tokens"]) == (32_768, 13_107)


def test_the_runner_hands_the_packers_budget_to_the_memory_turn(tmp_path):
    from decimal import Decimal

    from optimus.agent.models import AgentRunRequest
    from optimus.agent.runner import AgentRunner
    from optimus.agent.workspace_context import WorkspaceContextResult
    from optimus.runtime.modes import ExecutionMode

    seen: dict = {}
    budget = BudgetPolicy("model-aware", 32_768, 13_107)

    class Memory:
        def assemble(self, **kwargs):
            seen.update(kwargs)
            return WorkspaceContextResult(text="", max_total_bytes=16_384, used_bytes=0, prioritized_paths=(), omitted_paths=(), diagnostics=())

    packer = type("Packer", (), {"memory": Memory(), "model_id": "m", "estimate_request": staticmethod(len), "usable_input_tokens": 229_376, "pack_budget": budget})()
    runner = AgentRunner(gateway_client=object(), model="m")
    request = AgentRunRequest(run_id="r", task="t", execution_mode=ExecutionMode.CHAT, workspace_root=tmp_path, max_cost_usd=Decimal("0"))
    runner._turn_context(request, "t", packer)  # noqa: SLF001
    assert seen["pack_budget"] is budget


def test_the_memory_turns_assemble_passes_the_target_to_retrieval(monkeypatch):
    """Codex CP1 round 122 finding 7: through MemoryTurn.assemble itself, not only its helpers."""
    import contextlib

    from context_engine.retrieval import Retrieval
    from optimus.context import memory_session

    monkeypatch.setattr(memory_session, "resolve_task_references", lambda *_a, **_k: ())
    monkeypatch.setattr(memory_session, "rank_ambiguity", lambda diagnostics, *_a, **_k: diagnostics)
    monkeypatch.setattr(memory_session, "blocking_from_diagnostics", lambda _d: (None, None))
    seen: dict = {}
    turn = object.__new__(memory_session.MemoryTurn)
    policy = type("P", (), {"forget_ignore_files": staticmethod(lambda: None)})()
    turn._session = type("S", (), {"policy": policy, "foreground": staticmethod(contextlib.nullcontext), "listing_for": staticmethod(lambda _r: ()),  # noqa: SLF001
                                   "hints_for": staticmethod(lambda _s: ())})()
    turn._scope = None  # noqa: SLF001
    turn._capture_buffers = lambda _r: None  # noqa: SLF001

    def retrieve(text, required, estimate, budget, task, target=None, overview_path=None):
        seen.update(budget=budget, target=target, overview=overview_path)
        return Retrieval("unavailable"), None

    turn._retrieve = retrieve  # noqa: SLF001
    turn._today = lambda **_k: "today"  # noqa: SLF001
    assert turn.assemble(run_id="r", task="t", selection_text="t", model_id="m", estimate=len, usable_input_tokens=229_376,
                         pack_budget=BudgetPolicy("model-aware", 32_768, 13_107), overview_path="big.py") == "today"
    assert seen == {"budget": 32_768, "target": 13_107, "overview": "big.py"}  # Plan 12.14 Task 3: the summary target reaches the pack too


def test_the_model_aware_ceiling_holds_for_the_whole_pack_including_its_joiners():
    """Sizes chosen so that some pack fills its optional room exactly: without the joiner charge one of them goes over (QB3's 19,552 of 19,551)."""
    over = [n for n in range(1_000, 1_060) if (pack := _pack(n, budget=32_768, target=13_107)).tokens > pack.budget_tokens or not pack.complete]
    assert over == []
