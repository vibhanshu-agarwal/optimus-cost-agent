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
