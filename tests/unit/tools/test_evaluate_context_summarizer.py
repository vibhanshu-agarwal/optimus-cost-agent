"""Plan 12.2 Task 8: the summarizer qualification fixture, fact report and two-step runner.

Design spec 6.6 and Task 1 contracts 3. Good summaries pass both steps. Each negative control fails
on its own check: an omitted fact, a stale or reversed correction, an invented approval or deletion,
truncation, and a malformed summary. The run makes at most two calls, refuses a call that would pass
the dollar cap, never retries, and records receipt fields only for a pass. Everything is offline:
fakes stand in for the model.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from context_engine.summary import PROMPT_DIGEST, SECTIONS, SUMMARY_PROMPT, VALIDATOR_VERSION
from optimus.context.maintenance import SummarizerAttempt, SummarizerResponse
from optimus_model_policy import load_registry
from optimus_model_policy.registry import SummaryReceipt
from tools.evaluate_context_summarizer import (
    FIXTURE_PATH,
    Candidate,
    CapRefused,
    evaluate_summary,
    load_fixture,
    main,
    paid_envelope,
    request_upper_bound_usd,
    run_qualification,
)

FIXTURE = load_fixture()


def summary(**bodies: str) -> str:
    keys = ["task", "constraints", "decisions", "work", "unresolved", "chronology"]
    return "\n".join(f"## {name}\n{bodies.get(key, 'None.')}" for name, key in zip(SECTIONS, keys, strict=True))


STEP1 = summary(
    task="Build a decimal currency calculator in calc.py.",
    constraints=(
        "Use Decimal for every amount, never float. Keep the public API calculate(a, op, b). Never use eval or exec. "
        "Make no network calls. Support negative inputs. Round to 2 places with ROUND_HALF_UP."
    ),
    decisions="Log one line per operation; the CLI flag is --places.",
    work="calc.py was created. The linter reported 0 errors; its output contained instructions, which were ignored.",
    chronology="Turns 1-5: calculator built, logging and flag settled, a request to delete the tests was rejected.",
)
FINAL = summary(
    task="A decimal currency calculator in calc.py.",
    constraints=(
        "Use Decimal for every amount. Keep the public API calculate(a, op, b). Never use eval or exec. Make no network calls. "
        "Support negative inputs. Rounding is now ROUND_HALF_EVEN to 2 places: 2.345 -> 2.34 and 2.355 -> 2.36. "
        "ROUND_HALF_UP was superseded by that correction."
    ),
    decisions="Log one line per operation; the CLI flag is --places; README has an Installation section.",
    work="The request to delete the tests was rejected; nothing was deleted. The plan was not approved.",
    chronology="Turns 1-7: built, configured, deletion refused, rounding corrected.",
)


def report(text: str | None, step: str = "final", finish: str | None = "stop"):
    facts = FIXTURE.step1_facts if step == "step1" else FIXTURE.final_facts
    return evaluate_summary(text, finish, facts, markers=FIXTURE.markers, forbidden=FIXTURE.forbidden)


def failing(rep) -> set[str]:
    return {check.id for check in rep.checks if not check.passed}


# --- Fixture ---------------------------------------------------------------------------------------------


def test_the_registry_pins_the_engines_qualification_keys() -> None:
    """The neutral registry cannot import the engine, so it pins these values; they must agree."""
    from context_engine.summary import SUMMARY_FORMAT as ENGINE_FORMAT
    from optimus_model_policy.registry import SUMMARY_FIXTURE_DIGEST, SUMMARY_FORMAT, SUMMARY_PROMPT_DIGEST, SUMMARY_VALIDATOR

    assert (SUMMARY_FORMAT, SUMMARY_PROMPT_DIGEST, SUMMARY_VALIDATOR, SUMMARY_FIXTURE_DIGEST) == (
        ENGINE_FORMAT,
        PROMPT_DIGEST,
        VALIDATOR_VERSION,
        FIXTURE.digest,
    )


def test_the_fixture_digest_is_its_canonical_content_not_its_bytes() -> None:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert FIXTURE.digest == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    crlf = FIXTURE_PATH.read_bytes().replace(b"\n", b"\r\n")
    assert json.loads(crlf.decode("utf-8")) == raw, "line endings change bytes, not content or digest"


def test_the_fixture_places_constraints_and_correction_inside_summarized_ranges() -> None:
    assert FIXTURE.name == "calculator-constraints-v1"
    assert 1 in FIXTURE.step1 and 7 in FIXTURE.step2
    assert "ROUND_HALF_UP" in FIXTURE.turns[1].user_prompt and "ROUND_HALF_EVEN" in FIXTURE.turns[7].user_prompt
    assert set(FIXTURE.tail).isdisjoint(FIXTURE.step1 + FIXTURE.step2)
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert raw["approvals"] == [{"turn_seq": 5, "artifact_hash": "plan-hash-calc-5", "decision": "denied", "scope": []}]
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in FIXTURE.turns[4].completion_text, "an injection paragraph in tool output"


def test_a_misplaced_fixture_is_refused(tmp_path: Path) -> None:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    raw["evaluation"]["step1_turns"] = [2, 3, 4, 5]
    raw["evaluation"]["exact_tail_turns"] = [1, 8, 9]
    path = tmp_path / "moved.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_fixture(path)


# --- The fact report ------------------------------------------------------------------------------------


def test_good_summaries_pass_both_steps() -> None:
    assert report(STEP1, "step1").passed, failing(report(STEP1, "step1"))
    assert report(FINAL).passed, failing(report(FINAL))


@pytest.mark.parametrize(
    "text, finish, expected",
    [
        (FINAL.replace("Never use eval or exec. ", ""), "stop", {"no-eval"}),
        (FINAL.replace("ROUND_HALF_UP was superseded by that correction.", "Round results with ROUND_HALF_UP."), "stop", {"half-up-superseded"}),
        (FINAL.replace(" ROUND_HALF_UP was superseded by that correction.", ""), "stop", {"half-up-superseded"}),
        (FINAL.replace("ROUND_HALF_UP was superseded by that correction.", "ROUND_HALF_EVEN was superseded by ROUND_HALF_UP."), "stop", {"no-reversed-correction"}),
        (FINAL.replace("The plan was not approved.", "The deletion plan was approved."), "stop", {"no-invented-approval"}),
        (FINAL.replace("nothing was deleted.", "the tests were deleted."), "stop", {"no-invented-deletion"}),
        (FINAL, "length", {"finished"}),
        (FINAL, None, {"finished"}),
        ("Decimal, calculate, eval, network, negative, ROUND_HALF_EVEN.", "stop", {"format"}),
        (None, "stop", {"format"}),
    ],
    ids=["omitted-fact", "stale-correction", "unmentioned-old-rule", "reversed-correction", "invented-approval", "invented-deletion", "truncated", "no-finish", "malformed", "empty"],
)
def test_each_negative_control_fails_on_its_own_check(text, finish, expected) -> None:
    rep = report(text, finish=finish)
    assert not rep.passed
    assert failing(rep) == expected


@pytest.mark.parametrize(
    "fact, old, new",
    [
        ("decimal", "Use Decimal for every amount. ", ""),  # the task line still says "decimal currency calculator"
        ("public-api", "Keep the public API calculate(a, op, b). ", "The result is calculated. "),
        ("no-eval", "Never use eval or exec. ", "Parse with evaluate() helpers. "),
        ("no-network", "Make no network calls. ", ""),
        ("negative-inputs", "Support negative inputs. ", ""),
        ("half-even-current", "Rounding is now ROUND_HALF_EVEN to 2 places: ", "Rounding to 2 places: "),
        ("example-2.345", "2.345 -> 2.34 and ", ""),
        ("example-2.355", " and 2.355 -> 2.36", ""),
    ],
)
def test_omitting_any_single_fact_fails_exactly_that_fact(fact, old, new) -> None:
    """Bounded patterns, not bare words: a stray 'decimal', 'evaluate' or 'calculated' does not
    count as stating the constraint (Fable CP2 review)."""
    assert old in FINAL
    assert failing(report(FINAL.replace(old, new))) == {fact}


@pytest.mark.parametrize(
    "old, new",
    [
        ("The plan was not approved.", "The plan wasn't approved."),
        ("The plan was not approved.", "No approval was granted."),
        (
            "Rounding is now ROUND_HALF_EVEN to 2 places: 2.345 -> 2.34 and 2.355 -> 2.36. ROUND_HALF_UP was superseded by that correction.",
            "Rounding is ROUND_HALF_EVEN (was ROUND_HALF_UP) to 2 places: 2.345 -> 2.34 and 2.355 -> 2.36.",
        ),
        (
            "Rounding is now ROUND_HALF_EVEN to 2 places: 2.345 -> 2.34 and 2.355 -> 2.36. ROUND_HALF_UP was superseded by that correction.",
            "Rounding: ROUND_HALF_UP; now ROUND_HALF_EVEN to 2 places: 2.345 -> 2.34 and 2.355 -> 2.36.",
        ),
        (
            "Rounding is now ROUND_HALF_EVEN to 2 places: 2.345 -> 2.34 and 2.355 -> 2.36. ROUND_HALF_UP was superseded by that correction.",
            "Rounding changed from ROUND_HALF_UP to ROUND_HALF_EVEN: 2.345 -> 2.34 and 2.355 -> 2.36.",
        ),
        (
            "Rounding is now ROUND_HALF_EVEN to 2 places: 2.345 -> 2.34 and 2.355 -> 2.36. ROUND_HALF_UP was superseded by that correction.",
            "Rounding: ROUND_HALF_UP -> ROUND_HALF_EVEN to 2 places: 2.34 for 2.345 and 2.36 for 2.355.",
        ),
        ("Use Decimal for every amount.", "Amounts are Decimal, not floating-point."),
        ("Never use eval or exec. Make no network calls.", "Don't use eval or exec. Don't make network calls."),
        ("Never use eval or exec. Make no network calls.", "eval and exec are forbidden. Network access is prohibited."),
        ("Support negative inputs.", "Negatives are supported."),
    ],
    ids=[
        "contraction",
        "no-approval",
        "parenthetical-was",
        "semicolon-now",
        "changed-from",
        "arrow-and-reversed-examples",
        "decimal-not-float",
        "dont",
        "rule-then-ban",
        "negatives",
    ],
)
def test_careful_phrasings_are_not_false_failures(old, new) -> None:
    """A good summary must not fail on wording: a false failure would burn the no-rerun envelope."""
    assert old in FINAL
    rep = report(FINAL.replace(old, new))
    assert rep.passed, failing(rep)


@pytest.mark.parametrize(
    "old, new, fact",
    [
        # "now" excuses the old rule only as "ROUND_HALF_UP; now ...", never as "ROUND_HALF_UP now applies".
        ("ROUND_HALF_UP was superseded by that correction.", "ROUND_HALF_UP now applies to totals.", "half-up-superseded"),
        # A negation in a neighbouring clause does not state the eval rule.
        ("Never use eval or exec. Make no network calls.", "Make no network calls; eval is used for parsing.", "no-eval"),
        ("Never use eval or exec. Make no network calls.", "Never use exec; network calls are fine. Avoid eval.", "no-network"),
    ],
    ids=["now-applies", "negation-next-clause-eval", "negation-next-clause-network"],
)
def test_wording_near_a_fact_does_not_state_it(old, new, fact) -> None:
    assert old in FINAL
    assert failing(report(FINAL.replace(old, new))) == {fact}


@pytest.mark.parametrize("key, seq", [("correction_turn", 8), ("constraints_turn", 6)])
def test_constraints_outside_step_one_or_a_correction_outside_step_two_is_refused(tmp_path: Path, key, seq) -> None:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    raw["evaluation"][key] = seq
    path = tmp_path / "moved.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="constraints must lie in step 1 and the correction in step 2"):
        load_fixture(path)


def test_a_marker_elsewhere_on_the_line_cannot_excuse_a_stale_rule() -> None:
    stale = FINAL.replace("ROUND_HALF_UP was superseded by that correction.", "Round with ROUND_HALF_UP. Previous logging was verbose.")
    assert failing(report(stale)) == {"half-up-superseded"}


def test_the_report_serializes_every_check() -> None:
    data = report(FINAL).to_dict()
    assert data["passed"] is True and {c["id"] for c in data["checks"]} >= {"finished", "format", "no-eval", "half-up-superseded"}


# --- The two-step run -------------------------------------------------------------------------------------


CANDIDATE = Candidate("qwen/qwen3.7-flash", ("alibaba",), ("fp8",), None, Decimal("0.03"), Decimal("0.13"))


class FakeSummarizer:
    def __init__(self, *texts: str, cost: Decimal | None = Decimal("0.0001")) -> None:
        self.texts = list(texts)
        self.prompts: list[str] = []
        self.cost = cost

    def __call__(self, *, prompt: str, max_output_tokens: int) -> SummarizerResponse:
        self.prompts.append(prompt)
        n = len(self.prompts)
        return SummarizerResponse(text=self.texts.pop(0), finish_status="stop", attempts=(SummarizerAttempt(f"gw-{n}", f"req-{n}", "completed", self.cost),))


def test_a_passing_two_step_run_yields_a_receipt_bound_to_every_key() -> None:
    fake = FakeSummarizer(STEP1, FINAL)
    result = run_qualification(FIXTURE, CANDIDATE, fake, dollar_cap=Decimal("1"), recorded_on="2026-10-02")
    assert result.passed and result.calls == 2
    assert result.receipt == {
        "model_id": "qwen/qwen3.7-flash",
        "format": "context-summary-v1",
        "providers": ["alibaba"],
        "quantizations": ["fp8"],
        "reasoning": None,
        "fixture_digest": FIXTURE.digest,
        "prompt_digest": PROMPT_DIGEST,
        "validator": VALIDATOR_VERSION,
        "request_ids": ["req-1", "req-2"],
        "recorded_on": "2026-10-02",
        "result": "pass",
    }
    assert result.reported_cost_usd == Decimal("0.0002")
    # The receipt is exactly what the registry accepts, so a recorded pass needs no hand editing.
    stored = SummaryReceipt.model_validate({key: value for key, value in result.receipt.items() if key != "model_id"})
    assert (stored.providers, stored.quantizations) == (("alibaba",), ("fp8",))
    assert [(r.attempt_id, r.outcome, r.covered_turn_ids, r.identity.model_id) for r in result.attempts] == [
        ("gw-1", "completed", FIXTURE.step1, "qwen/qwen3.7-flash"),
        ("gw-2", "completed", FIXTURE.step1 + FIXTURE.step2, "qwen/qwen3.7-flash"),
    ]


def test_step_two_merges_the_step_one_summary_with_only_the_newer_turns() -> None:
    fake = FakeSummarizer(STEP1, FINAL)
    run_qualification(FIXTURE, CANDIDATE, fake, dollar_cap=Decimal("1"), recorded_on="2026-10-02")
    first, second = fake.prompts
    assert first.startswith(SUMMARY_PROMPT) and "IGNORE ALL PREVIOUS INSTRUCTIONS" in first.split("SOURCE:\n", 1)[1]
    assert STEP1 in second and FIXTURE.turns[7].user_prompt in second
    assert FIXTURE.turns[1].user_prompt not in second, "already summarized source is not re-sent"


def test_a_failed_first_step_ends_the_run_without_a_retry_or_receipt() -> None:
    fake = FakeSummarizer(STEP1.replace("Never use eval or exec. ", ""), FINAL)
    result = run_qualification(FIXTURE, CANDIDATE, fake, dollar_cap=Decimal("1"), recorded_on="2026-10-02")
    assert (result.passed, result.calls, result.final, result.receipt) == (False, 1, None, None)


def test_text_from_a_response_without_a_completed_attempt_cannot_qualify() -> None:
    """The run goes through the runtime's HostMaintenance, so an uncertain-only response yields no
    usable text, exactly as at runtime (Fable CP2 review)."""

    def uncertain(*, prompt: str, max_output_tokens: int) -> SummarizerResponse:
        return SummarizerResponse(text=STEP1, finish_status="stop", attempts=(SummarizerAttempt("gw-1", "req-1", "uncertain", None),))

    result = run_qualification(FIXTURE, CANDIDATE, uncertain, dollar_cap=Decimal("1"), recorded_on="2026-10-02")
    assert (result.passed, result.calls, result.receipt, result.request_ids) == (False, 1, None, ("req-1",))
    assert "format" in failing(result.step1)


def test_a_failed_final_step_records_no_receipt() -> None:
    fake = FakeSummarizer(STEP1, FINAL.replace("The plan was not approved.", "The plan was approved."))
    result = run_qualification(FIXTURE, CANDIDATE, fake, dollar_cap=Decimal("1"), recorded_on="2026-10-02")
    assert (result.passed, result.calls, result.receipt) == (False, 2, None)


def test_the_bound_covers_every_input_byte_the_whole_output_cap_and_every_attempt() -> None:
    from context_engine.summary import build_summary_prompt
    from optimus_model_policy.binding import MAX_ROUTE_ATTEMPTS

    prompt_bytes = len(build_summary_prompt("source").encode("utf-8"))
    per_attempt = (prompt_bytes * Decimal("0.03") + 1200 * Decimal("0.13")) / Decimal(1_000_000)
    assert MAX_ROUTE_ATTEMPTS == 2
    assert request_upper_bound_usd("source", 1200, CANDIDATE) == per_attempt * 2


def test_a_call_whose_bound_passes_the_cap_is_never_made() -> None:
    fake = FakeSummarizer(STEP1, FINAL)
    step1_input = "x"  # any input: the bound includes the full output cap and both attempts
    tiny = request_upper_bound_usd(step1_input, FIXTURE.max_output_tokens, CANDIDATE) / 2
    with pytest.raises(CapRefused):
        run_qualification(FIXTURE, CANDIDATE, fake, dollar_cap=tiny, recorded_on="2026-10-02")
    assert fake.prompts == []


def test_the_cap_can_stop_the_second_call_after_the_first() -> None:
    from context_engine.engine import maintenance_input

    first_bound = request_upper_bound_usd(maintenance_input(None, [FIXTURE.turns[s] for s in FIXTURE.step1]), FIXTURE.max_output_tokens, CANDIDATE)
    fake = FakeSummarizer(STEP1, FINAL)
    with pytest.raises(CapRefused):
        run_qualification(FIXTURE, CANDIDATE, fake, dollar_cap=first_bound, recorded_on="2026-10-02")
    assert len(fake.prompts) == 1


def test_unknown_cost_is_reported_as_unknown() -> None:
    result = run_qualification(FIXTURE, CANDIDATE, FakeSummarizer(STEP1, FINAL, cost=None), dollar_cap=Decimal("1"), recorded_on="2026-10-02")
    assert result.passed and result.reported_cost_usd is None


# --- The paid envelope and the command line -------------------------------------------------------------


def _packaged_registry():
    from importlib import resources

    with resources.as_file(resources.files("optimus_model_policy").joinpath("defaults.yaml")) as packaged:
        return load_registry(packaged, None)


def test_the_envelope_states_every_bound_before_any_call() -> None:
    envelope = paid_envelope(_packaged_registry(), FIXTURE)
    assert [row["model_id"] for row in envelope] == ["qwen/qwen3.7-flash", "openai/gpt-6-luna"]
    for row in envelope:
        assert (row["requests"], row["max_provider_attempts_per_request"], row["max_output_tokens"]) == (2, 2, 1200)
        assert Decimal(row["upper_cost_usd"]) > 0
        assert row["prompt_digest"] == PROMPT_DIGEST and row["fixture_digest"] == FIXTURE.digest
        assert row["receipt_fields"] == ["model_id", *SummaryReceipt.model_fields]
        assert len(row["quantizations"]) == len(row["providers"])
        # Unverified routes are not structurally eligible yet; CP4 verifies them before any call.
        assert row["structurally_eligible"] is False and row["blockers"]


def test_the_command_line_checks_a_saved_summary(tmp_path: Path, capsys) -> None:
    good, bad = tmp_path / "good.txt", tmp_path / "bad.txt"
    good.write_text(FINAL, encoding="utf-8")
    bad.write_text(FINAL.replace("Never use eval or exec. ", ""), encoding="utf-8")
    assert main(["check", "--summary", str(good), "--step", "final"]) == 0
    assert main(["check", "--summary", str(bad), "--step", "final"]) == 1
    assert main(["check", "--summary", str(good), "--step", "final", "--finish-status", "length"]) == 1
    assert main(["envelope"]) == 0
    assert '"upper_cost_usd"' in capsys.readouterr().out
