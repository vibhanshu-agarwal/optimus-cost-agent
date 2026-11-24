"""Plan 12.14 Task 1: the optional-packing candidates (baseline greedy, density, coverage) and the quota places they protect.

Pure: the pack and the policies are fed tables here; the real index runs in tools/plan12_memory/m2b_evaluate.py."""

from __future__ import annotations

import hashlib

import pytest

from context_engine.context_pack import SECTION_BODIES, SECTION_SIGNATURES, assemble_pack
from context_engine.pack_utility import POLICIES, Candidate, marginal_terms, select
from context_engine.retrieval import Hit, Ranked, fuse, quota_ids


def _estimate(text: str) -> int:
    return len(text.encode("utf-8"))


def _c(ident: str, text: str, ordinal: int, score: float = 0.02) -> Candidate:
    return Candidate(id=ident, text=text, score=score, ordinal=ordinal)


def _fits(header: str, chosen: list[Candidate], room: int) -> bool:
    return _estimate("\n".join([header, *(c.text for c in sorted(chosen, key=lambda c: c.ordinal))])) <= room


def test_the_policies_are_exactly_the_plans_three():
    assert POLICIES == ("baseline", "density", "coverage")
    with pytest.raises(ValueError):
        select("H", [], room=10, estimate=_estimate, policy="learned", task_terms=(), protected=frozenset())


def test_baseline_is_greedy_fill_in_fused_order():
    big, small1, small2 = _c("a", "x" * 50, 0), _c("b", "y" * 10, 1), _c("c", "z" * 10, 2)
    chosen = select("H", [big, small1, small2], room=25, estimate=_estimate, policy="baseline", task_terms=("x",), protected=frozenset())
    assert [c.id for c in chosen] == ["b", "c"]  # a does not fit; the rest are taken in order


def test_density_divides_by_the_candidates_own_cost():
    large = _c("a", "alpha " * 20, 0, score=0.03)
    small = _c("b", "alpha", 1, score=0.02)
    chosen = select("H", [large, small], room=40, estimate=_estimate, policy="density", task_terms=("alpha",), protected=frozenset())
    assert [c.id for c in chosen][0] == "b"


def test_coverage_prefers_new_task_terms_without_dividing_by_size():
    redundant = _c("a", "one", 0, score=0.03)
    novel = _c("b", "two three", 1, score=0.025)
    order = select("H", [redundant, novel], room=1_000, estimate=_estimate, policy="coverage", task_terms=("one", "two", "three"), protected=frozenset())
    assert [c.id for c in order] == ["b", "a"]  # 0.025 * (1 + 2/3) > 0.03 * (1 + 1/3)


def test_marginal_coverage_is_recomputed_after_each_selection():
    first = _c("a", "alpha beta", 0, score=0.02)
    same = _c("b", "alpha beta", 1, score=0.02)
    other = _c("c", "gamma", 2, score=0.019)
    order = select("H", [first, same, other], room=1_000, estimate=_estimate, policy="coverage", task_terms=("alpha", "beta", "gamma"), protected=frozenset())
    assert [c.id for c in order] == ["a", "c", "b"]  # once a covers alpha and beta, b adds nothing and c's one new term wins
    assert marginal_terms(same, {"alpha"}, frozenset({"alpha", "beta", "gamma"})) == 1


def test_quota_places_go_first_in_their_existing_order_when_they_fit():
    protected = _c("q", "zzz", 3, score=0.001)
    strong = _c("s", "alpha", 0, score=0.05)
    order = select("H", [strong, protected], room=1_000, estimate=_estimate, policy="density", task_terms=("alpha",), protected=frozenset({"q"}))
    assert [c.id for c in order] == ["q", "s"]


def test_a_quota_place_that_does_not_fit_is_skipped_not_forced():
    protected = _c("q", "z" * 100, 0)
    other = _c("o", "alpha", 1)
    order = select("H", [protected, other], room=20, estimate=_estimate, policy="coverage", task_terms=("alpha",), protected=frozenset({"q"}))
    assert [c.id for c in order] == ["o"]


def test_ties_go_to_the_fused_ordinal():
    a, b = _c("b-id", "alpha", 1), _c("a-id", "alpha", 0)
    order = select("H", [a, b], room=1_000, estimate=_estimate, policy="density", task_terms=("beta",), protected=frozenset())
    assert [c.id for c in order] == ["a-id", "b-id"]


@pytest.mark.parametrize("policy", POLICIES)
def test_no_policy_exceeds_the_room_as_rendered(policy):
    pool = [_c(str(i), ("alpha beta gamma " * (i % 4 + 1)).strip(), i, score=0.02 - i / 10_000) for i in range(30)]
    chosen = select("HEADER", pool, room=200, estimate=_estimate, policy=policy, task_terms=("alpha", "gamma"), protected=frozenset({"3", "7"}))
    assert chosen and _fits("HEADER", chosen, 200)
    assert len({c.id for c in chosen}) == len(chosen)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


SOURCE = b"def first():\n    return 1\n\ndef second():\n    return 2\n\ndef third():\n    return 3\n"


def _ranked(ident: str, symbol: str, lines: tuple[int, int], score: float) -> Ranked:
    hit = Hit(id=ident, kind="symbol", path="a.py", file_hash=_sha(SOURCE), symbol=symbol, signature=f"def {symbol}()", start_line=lines[0], end_line=lines[1])
    return Ranked(hit, score, {"lexical": 1})


def _read(path: str) -> bytes | None:
    return SOURCE if path == "a.py" else None


RANKED = [_ranked("1", "first", (1, 2), 0.03), _ranked("2", "second", (4, 5), 0.02), _ranked("3", "third", (7, 8), 0.01)]


def test_the_default_pack_is_the_baseline_byte_for_byte():
    default = assemble_pack(required=(), ranked=RANKED, read=_read, estimate=_estimate, budget_tokens=150)
    baseline = assemble_pack(required=(), ranked=RANKED, read=_read, estimate=_estimate, budget_tokens=150, policy="baseline", task="third", protected=())
    assert default == baseline


def test_a_utility_changes_only_which_optional_items_fit_and_keeps_fused_order_in_the_text():
    close = [_ranked("1", "first", (1, 2), 0.012), _ranked("2", "second", (4, 5), 0.011), _ranked("3", "third", (7, 8), 0.010)]
    baseline = assemble_pack(required=(), ranked=close, read=_read, estimate=_estimate, budget_tokens=150)
    pack = assemble_pack(required=(), ranked=close, read=_read, estimate=_estimate, budget_tokens=150, policy="coverage", task="third", protected=())
    assert [s.symbol for s in baseline.selected if s.disclosure == "body"] == ["first", "second"]
    assert [s.symbol for s in pack.selected if s.disclosure == "body"] == ["first", "third"]  # 0.010 * (1 + 1/1) outranks 0.011
    assert [s.symbol for s in pack.selected] == [s.symbol for s in baseline.selected] and pack.tokens <= 150
    bodies = pack.text.split(SECTION_BODIES)[1] if SECTION_BODIES in pack.text else ""
    positions = [bodies.find(f"a.py:{lines}") for lines in ("1-2", "4-5", "7-8") if f"a.py:{lines}" in bodies]
    assert len(positions) == 2 and positions == sorted(positions)
    assert SECTION_SIGNATURES not in pack.text  # a quarter of 150 holds no signature line here, for either policy


def test_required_evidence_is_untouched_by_the_policy():
    for policy in POLICIES:
        pack = assemble_pack(required=("a.py",), ranked=RANKED, read=_read, estimate=_estimate, budget_tokens=10, policy=policy, task="third", protected=())
        assert not pack.complete and pack.missing_required == ("a.py",)


def _hit(ident: str) -> Hit:
    return Hit(id=ident, kind="symbol", path=f"{ident}.py", file_hash="0" * 64)


def test_quota_ids_are_the_places_fuse_puts_first():
    channels = {"dense": [_hit("d1"), _hit("d2")], "lexical": [_hit("l1"), _hit("d1"), _hit("l2")]}
    assert quota_ids(channels) == ("d1", "l1", "d2")  # d1 is lexical's second too: a duplicate takes no place
    assert tuple(item.hit.id for item in fuse(channels))[:3] == quota_ids(channels)
    assert quota_ids(channels, named=("x.py",)) == ()
    assert quota_ids({**channels, "structure": [_hit("s")]}) == ()
