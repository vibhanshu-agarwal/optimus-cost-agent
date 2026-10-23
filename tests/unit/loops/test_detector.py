from __future__ import annotations

from optimus.loops.detector import LoopDetector, LoopSignalKind, LoopThresholds
from optimus.loops.signals import ActionKind, LoopStep, parse_failure_step


def _step(name: str, digest: str = "d", *, novel: bool = False, kind: ActionKind = ActionKind.READ) -> LoopStep:
    return LoopStep(kind=kind, fingerprint=name, result_digest=digest, novel=novel, subject=name)


def _run(detector: LoopDetector, steps: list[LoopStep]) -> list[LoopSignalKind | None]:
    return [None if (found := detector.observe(step)) is None else found.kind for step in steps]


def test_three_identical_reads_with_unchanged_results_fire_a_repeat():
    assert _run(LoopDetector(), [_step("A", novel=True), _step("A"), _step("A")])[-1] is LoopSignalKind.REPEATED_READ


def test_an_mcp_repeat_is_named_as_mcp():
    steps = [_step("M", kind=ActionKind.MCP, novel=True), _step("M", kind=ActionKind.MCP), _step("M", kind=ActionKind.MCP)]
    assert _run(LoopDetector(), steps)[-1] is LoopSignalKind.REPEATED_MCP


def test_polling_with_changing_results_never_fires():
    steps = [_step("poll", digest=str(n), novel=True) for n in range(10)]
    assert _run(LoopDetector(), steps) == [None] * 10


def test_a_changed_result_resets_the_repeat_streak():
    steps = [_step("A", "1", novel=True), _step("A", "1"), _step("A", "2", novel=True), _step("A", "2")]
    assert _run(LoopDetector(), steps) == [None] * 4


def test_three_steps_without_novelty_fire_no_progress():
    steps = [_step("A", novel=True), _step("B"), _step("C"), _step("D")]
    assert _run(LoopDetector(), steps) == [None, None, None, LoopSignalKind.NO_PROGRESS]


def test_progress_resets_the_no_progress_streak():
    steps = [_step("A"), _step("B"), _step("C", novel=True), _step("D"), _step("E")]
    assert _run(LoopDetector(), steps) == [None] * 5


def test_an_a_b_alternation_over_three_cycles_fires_a_cycle():
    detector = LoopDetector(LoopThresholds(no_progress=10))
    steps = [_step("A", novel=True), _step("B", novel=True)] + [_step("A"), _step("B")] * 2
    assert _run(detector, steps) == [None] * 5 + [LoopSignalKind.CYCLE]


def test_an_alternation_with_a_changed_result_is_not_a_cycle():
    detector = LoopDetector(LoopThresholds(no_progress=10))
    steps = [_step("A"), _step("B"), _step("A"), _step("B"), _step("A", "changed", novel=True), _step("B")]
    assert _run(detector, steps) == [None] * 6


def test_one_action_alternating_between_two_results_is_polling_not_a_cycle():
    detector = LoopDetector(LoopThresholds(no_progress=10))
    steps = [_step("poll", digest) for digest in ("1", "2") * 3]
    assert _run(detector, steps) == [None] * 6


def test_three_identical_parse_failures_fire_a_repeated_parse_error():
    steps = [parse_failure_step(code="GRAMMAR_UNRECOGNIZED", message="m")] * 3
    assert _run(LoopDetector(), steps)[-1] is LoopSignalKind.REPEATED_PARSE_ERROR


def test_three_different_parse_failures_fire_no_progress_not_a_repeated_error():
    steps = [parse_failure_step(code=code, message="m") for code in ("GRAMMAR_UNRECOGNIZED", "OBSERVE_MULTIPLE", "READ_RANGE_EMPTY")]
    assert _run(LoopDetector(), steps)[-1] is LoopSignalKind.NO_PROGRESS


def test_reset_forgets_the_streak():
    detector = LoopDetector()
    _run(detector, [_step("A"), _step("A")])
    detector.reset()
    assert _run(detector, [_step("A"), _step("A")]) == [None, None]


def test_thresholds_are_configurable():
    assert _run(LoopDetector(LoopThresholds(repeat=2)), [_step("A", novel=True), _step("A")])[-1] is LoopSignalKind.REPEATED_READ
