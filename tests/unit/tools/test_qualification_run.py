"""Plan 12.2 Stage B launcher: `evaluate_context_summarizer.py run` (Codex Haiku Stage A review, launcher ruling).

The `run` command is a client of the Gateway that the operator-started, profiled host owns. It accepts
only the reviewed qualification profile, derives model, route, reasoning and prices from its pinned
snapshot, and binds every request to that hash and the fixture's 1,200-token cap. It records the run's
identity before dispatch and every attempt as it arrives, keeps that evidence when the run fails or
raises, and never emits a receipt candidate: a run whose automatic checks pass awaits the two offline
reviews of `assess` (Codex qualification-method disposition, 2026-10-10).

Offline: the real host Gateway client posts through the real Gateway handler under the Haiku policy,
and a scripted upstream stands in for the provider.
"""

from __future__ import annotations

import dataclasses
import io
import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest

import optimus_gateway.responses as gateway_responses
from optimus_gateway.responses import handle_responses_request
from optimus_gateway.upstream_client import ProviderMessageResult
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy import validate_registry
from optimus_model_policy.experimental import HAIKU_QUALIFICATION_HASH
from tests.unit.optimus_gateway.model_policy_support import SHARED_SECRET, RecordingUpstream, gateway_config, model_policy
from tests.unit.tools.test_evaluate_context_summarizer import FINAL, PAID_RUN_SENTENCE, STEP1, padded, with_case
from tools import evaluate_context_summarizer as tool

HAIKU = "anthropic/claude-haiku-5.5"
ENVIRON = {"OPTIMUS_API_KEY": SHARED_SECRET, "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway_responses, "_sleep", lambda _seconds: None)


class SummaryUpstream(RecordingUpstream):
    """The provider: scripted summaries, prompt tokens at one per byte, documented router evidence."""

    def __init__(self, *texts: str, provider: str = "Anthropic", costs: tuple[str, ...] = (), **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.texts = list(texts)
        self.provider = provider
        self.costs = list(costs)

    def _result(self, model: str) -> ProviderMessageResult:
        prompt_tokens = len(self.calls[-1]["input_text"].encode("utf-8"))
        return ProviderMessageResult(
            message_id=f"gen-{len(self.calls)}",
            output_text=self.texts.pop(0),
            input_tokens=prompt_tokens,
            output_tokens=300,
            total_tokens=prompt_tokens + 300,
            billing_units=prompt_tokens + 300,
            cost_usd=Decimal(self.costs.pop(0)) if self.costs else Decimal("0.001"),
            provider="openrouter",
            resolved_provider=self.provider,
            requested_model=model,
            resolved_model=model,
            model_version=None,
            cache_hit=False,
            reasoning_tokens=40,
            finish_reason="stop",
            router_attempt=1,
            router_pipeline=(),
        )


class ProfiledGateway:
    """The operator-started host's Gateway, reached through the host client's real urllib transport."""

    def __init__(self, upstream: RecordingUpstream, out: Path, *, interrupt_on: int | None = None) -> None:
        self.policy = model_policy(profiles.compose_test_profile_snapshot("qualification"))
        self.upstream = upstream
        self.out = out
        self.bindings: list[dict[str, Any]] = []
        self.identity_recorded_first: list[bool] = []
        self.interrupt_on = interrupt_on

    def urlopen(self, request: Any, timeout: float = 0) -> Any:
        payload = json.loads(request.data)
        self.bindings.append(payload["route_binding"])
        self.identity_recorded_first.append((self.out / "run.json").is_file())
        if self.interrupt_on == len(self.bindings):
            raise KeyboardInterrupt
        status, body = handle_responses_request(
            authorization_header=request.get_header("Authorization"),
            request_body=payload,
            config=gateway_config(self.policy),
            upstream_client=self.upstream,
        )
        raw = json.dumps(body, default=str).encode()
        if status != 200:
            raise HTTPError(request.full_url, status, "gateway error", None, io.BytesIO(raw))  # type: ignore[arg-type]
        return io.BytesIO(raw)


def _run(monkeypatch: pytest.MonkeyPatch, out: Path, upstream: RecordingUpstream, **kwargs: Any) -> tuple[int, ProfiledGateway]:
    gateway = ProfiledGateway(upstream, out, interrupt_on=kwargs.pop("interrupt_on", None))
    monkeypatch.setattr("optimus.gateway.client.urlopen", gateway.urlopen)
    code = tool.run_live(out=out, host_pid=4100, gateway_pid=4200, environ=ENVIRON, **kwargs)
    return code, gateway


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_a_passing_run_records_its_identity_first_and_awaits_review_without_a_candidate(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "run-1"
    upstream = SummaryUpstream(STEP1, FINAL)

    code, gateway = _run(monkeypatch, out, upstream)

    assert code == 0
    assert gateway.identity_recorded_first == [True, True], "the run's identity is on disk before any dispatch"
    # Every request is bound to the reviewed hash and fixture v2's 8,192-token allocation, not the agent's 32,768.
    assert [(b["registry_hash"], b["output_cap"]) for b in gateway.bindings] == [(HAIKU_QUALIFICATION_HASH, 8192)] * 2
    assert [(c["model"], c["max_tokens"], c["reasoning"]) for c in upstream.calls] == [(HAIKU, 8192, "low")] * 2
    assert dict(upstream.calls[0]["provider_controls"])["only"] == ["anthropic"]

    run = _json(out / "run.json")
    assert (run["profile"], run["registry_hash"], run["model_id"], run["providers"], run["reasoning"]) == (
        "qualification", HAIKU_QUALIFICATION_HASH, HAIKU, ["anthropic"], "low",
    )
    assert (run["host_pid"], run["gateway_pid"], run["gateway_url"]) == (4100, 4200, "http://127.0.0.1:8765")
    assert (run["dollar_cap_usd"], run["wall_clock_seconds"], run["max_requests"], run["max_provider_attempts"]) == ("0.0946751", 1800, 2, 4)
    # The released $0.10 is the cumulative Stage B ceiling: four sealed runs already spent $0.0053249.
    assert (run["stage_b_ceiling_usd"], run["prior_stage_b_spend_usd"]) == ("0.10", "0.0053249")
    assert run["prior_stage_b_run"] == tool.PRIOR_STAGE_B_RUN
    assert run["envelope"]["reserved_cost_usd"] == "0.0945550"
    assert (run["fixture"], run["envelope"]["fixture_digest"], run["envelope"]["max_output_tokens"]) == (
        "calculator-constraints-v2",
        "f32fd04d25461f435daff8c39049b2468afe3e407e1c4a3a41c9992f3b5e8f19",  # pragma: allowlist secret - public fixture digest
        8192,
    )
    assert len(run["fixture_file_sha256"]) == 64 and len(run["tool_sha256"]) == 64
    assert "OPTIMUS_API_KEY" not in json.dumps(run) and SHARED_SECRET not in (out / "run.json").read_text(encoding="utf-8")

    attempts = _lines(out / "attempts.jsonl")
    assert [(a["outcome"], a["cost_usd"], a["resolved_provider"]) for a in attempts] == [("completed", "0.001", "Anthropic")] * 2
    responses = _lines(out / "responses.jsonl")
    assert [len(r["text"]) for r in responses] == [len(STEP1), len(FINAL)]
    # Each response's billing facts are on disk with it, before the runtime records its receipts.
    assert [[(a["outcome"], a["cost_usd"]) for a in r["attempts"]] for r in responses] == [[("completed", "0.001")]] * 2

    # No candidate: only the offline `assess` can write one, after two passing reviews.
    assert not (out / "receipt-candidate.json").exists()
    # The observed route and reasoning stay in the attempt records that `assess` verifies.
    assert [(a["usage"]["resolved_provider"], a["usage"]["reasoning_tokens"]) for a in attempts] == [("Anthropic", 40)] * 2
    outcome = _json(out / "outcome.json")
    assert (outcome["status"], outcome["provider_attempts"], outcome["reported_cost_usd"]) == ("awaiting-review", 2, "0.002")
    assert outcome["request_ids"] == [a["gateway_request_id"] for a in attempts]


def test_a_pass_qualifies_nothing_by_itself(tmp_path: Path, monkeypatch) -> None:
    """A run awaiting review writes no candidate: the profile's summarizer stays unqualified, so no
    attached engine is enabled before two reviews pass and a reviewed receipt is filed."""
    code, _gateway = _run(monkeypatch, tmp_path / "run", SummaryUpstream(STEP1, FINAL))

    assert code == 0
    issues = validate_registry(profiles.compose_test_profile_snapshot("qualification"))
    assert any(issue.code == "SUMMARIZER_UNQUALIFIED" and issue.model_id == HAIKU for issue in issues)


def test_a_failed_reply_check_is_kept_as_billed_and_writes_no_receipt(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "run"
    upstream = SummaryUpstream(STEP1, FINAL, provider="Google")

    code, _gateway = _run(monkeypatch, out, upstream)

    assert code == 1 and len(upstream.calls) == 1
    [attempt] = _lines(out / "attempts.jsonl")
    assert (attempt["outcome"], attempt["cost_usd"], attempt["resolved_provider"]) == ("completed", "0.001", "Google")
    outcome = _json(out / "outcome.json")
    assert (outcome["status"], outcome["reported_cost_usd"]) == ("fail", "0.001")
    assert not (out / "receipt-candidate.json").exists()


def test_an_unknown_cost_is_recorded_as_unknown_and_stops_the_run(tmp_path: Path, monkeypatch) -> None:
    from optimus_gateway.upstream_client import UpstreamAttemptFailure

    out = tmp_path / "run"
    upstream = SummaryUpstream(STEP1, FINAL, attempts=[UpstreamAttemptFailure("uncertain")])

    code, _gateway = _run(monkeypatch, out, upstream)

    assert code == 1 and len(upstream.calls) == 1
    assert [(a["outcome"], a["cost_usd"]) for a in _lines(out / "attempts.jsonl")] == [("uncertain", None)]
    assert _json(out / "outcome.json")["reported_cost_usd"] is None
    assert not (out / "receipt-candidate.json").exists()


def test_a_step_one_summary_over_the_carry_ceiling_leaves_step_two_unrun(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "run"
    upstream = SummaryUpstream(padded(STEP1, tool.SUMMARY_MAX_BYTES + 1), FINAL)

    code, _gateway = _run(monkeypatch, out, upstream)

    assert code == 1 and len(upstream.calls) == 1
    outcome = _json(out / "outcome.json")
    assert outcome["status"] == "fail" and outcome["unrun"].startswith("step 2 UNRUN")
    assert [a["cost_usd"] for a in _lines(out / "attempts.jsonl")] == ["0.001"]


def test_the_wall_clock_stops_a_request_it_could_not_finish_and_keeps_the_earlier_attempts(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "run"
    upstream = SummaryUpstream(STEP1, FINAL)
    ticks = [0.0, 0.0, 1800.0 - tool.LIVE_REQUEST_TIMEOUT_SECONDS + 1]

    def clock() -> float:
        return ticks.pop(0) if len(ticks) > 1 else ticks[0]

    code, _gateway = _run(monkeypatch, out, upstream, clock=clock)

    assert code == 1 and len(upstream.calls) == 1
    assert [a["cost_usd"] for a in _lines(out / "attempts.jsonl")] == ["0.001"]
    outcome = _json(out / "outcome.json")
    assert outcome["status"] == "stopped" and "wall clock" in outcome["error"]
    assert (outcome["requests_dispatched"], outcome["in_flight"]) == (1, False)
    assert not (out / "receipt-candidate.json").exists()


def test_an_interruption_mid_request_is_recorded_as_in_flight_at_unknown_cost(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "run"
    upstream = SummaryUpstream(STEP1, FINAL)

    with pytest.raises(KeyboardInterrupt):
        _run(monkeypatch, out, upstream, interrupt_on=2)

    assert [a["cost_usd"] for a in _lines(out / "attempts.jsonl")] == ["0.001"]
    outcome = _json(out / "outcome.json")
    assert (outcome["status"], outcome["error"], outcome["requests_dispatched"], outcome["in_flight"]) == ("stopped", "KeyboardInterrupt", 2, True)
    assert not (out / "receipt-candidate.json").exists()


def test_an_existing_output_directory_is_refused_before_anything_is_sent(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "run"
    out.mkdir()
    upstream = SummaryUpstream(STEP1, FINAL)

    code, gateway = _run(monkeypatch, out, upstream)

    assert (code, gateway.bindings, list(out.iterdir())) == (2, [], [])


def test_a_reservation_over_the_dollar_cap_is_refused_before_anything_is_sent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tool, "LIVE_DOLLAR_CAP", Decimal("0.02"))
    out = tmp_path / "run"

    code, gateway = _run(monkeypatch, out, SummaryUpstream(STEP1, FINAL))

    assert (code, gateway.bindings, out.exists()) == (2, [], False)


def test_missing_gateway_credentials_are_refused_before_anything_is_sent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tool, "resolve_shared_secret", lambda *_args, **_kwargs: None)
    out = tmp_path / "run"
    gateway = ProfiledGateway(SummaryUpstream(STEP1, FINAL), out)
    monkeypatch.setattr("optimus.gateway.client.urlopen", gateway.urlopen)

    code = tool.run_live(out=out, host_pid=1, gateway_pid=2, environ={})

    assert (code, gateway.bindings, out.exists()) == (2, [], False)


@pytest.mark.parametrize(
    "argv",
    [
        ["run", "--profile", "speed", "--host-pid", "1", "--gateway-pid", "2", "--out", "x"],
        ["run", "--profile", "qualification", "--host-pid", "1", "--gateway-pid", "2", "--out", "x", "--registry", "r.yaml"],
        ["run", "--profile", "qualification", "--host-pid", "1", "--gateway-pid", "2", "--out", "x", "--model", HAIKU],
    ],
    ids=["another-profile", "a-registry", "a-model"],
)
def test_only_the_reviewed_profile_can_run_with_no_registry_or_model_override(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        tool.main(argv)


# --- Persisted free text is sanitized (Plan 9.96 logging-surface manifest) ----------------------------------

SYNTHETIC_KEY = "sk-or-v1-" + "0123456789abcdef" * 4  # pragma: allowlist secret - synthetic test fixture


def test_persisted_model_text_is_sanitized_with_the_runtime_evidence_policy(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "run"
    leaky = STEP1.replace("which were ignored.", f"which were ignored. Token {SYNTHETIC_KEY} seen.")

    _run(monkeypatch, out, SummaryUpstream(leaky, FINAL))

    persisted = (out / "responses.jsonl").read_text(encoding="utf-8")
    assert SYNTHETIC_KEY not in persisted and "**********" in persisted


def test_persisted_error_text_is_sanitized(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "run"
    ticks = [0.0]

    def clock() -> float:
        if not ticks:
            raise RuntimeError(f"clock failed near {SYNTHETIC_KEY}")
        return ticks.pop()

    code, _gateway = _run(monkeypatch, out, SummaryUpstream(STEP1, FINAL), clock=clock)

    assert code == 1
    error = _json(out / "outcome.json")["error"]
    assert error.startswith("RuntimeError: clock failed near") and SYNTHETIC_KEY not in error


# --- Spending is settled from reported costs (Codex correction-batch review M3) ------------------------------


def test_a_first_reply_above_the_grant_keeps_its_charge_and_leaves_step_two_unrun(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "run"
    upstream = SummaryUpstream(STEP1, FINAL, costs=("0.11",))

    code, _gateway = _run(monkeypatch, out, upstream)

    assert code == 1 and len(upstream.calls) == 1
    assert [a["cost_usd"] for a in _lines(out / "attempts.jsonl")] == ["0.11"]
    outcome = _json(out / "outcome.json")
    assert (outcome["status"], outcome["reported_cost_usd"], outcome["step1"]["passed"]) == ("budget", "0.11", True)
    assert outcome["budget"] == "known spend 0.11 USD exceeds the 0.0946751 USD cap"
    assert outcome["unrun"].startswith("step 2 UNRUN: known spend 0.11 USD plus step 2's reservation")
    assert not (out / "receipt-candidate.json").exists()


def test_a_first_reply_leaving_too_little_for_step_two_dispatches_nothing_more(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "run"
    upstream = SummaryUpstream(STEP1, FINAL, costs=("0.06",))

    code, _gateway = _run(monkeypatch, out, upstream)

    assert code == 1 and len(upstream.calls) == 1
    outcome = _json(out / "outcome.json")
    assert (outcome["status"], outcome["reported_cost_usd"]) == ("budget", "0.06")
    assert outcome["budget"] == outcome["unrun"] and "plus step 2's reservation" in outcome["unrun"]
    assert not (out / "receipt-candidate.json").exists()


def test_a_last_reply_taking_the_total_over_the_grant_keeps_both_results_and_is_not_a_pass(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "run"
    upstream = SummaryUpstream(STEP1, FINAL, costs=("0.05", "0.05"))

    code, _gateway = _run(monkeypatch, out, upstream)

    assert code == 1 and len(upstream.calls) == 2
    assert [a["cost_usd"] for a in _lines(out / "attempts.jsonl")] == ["0.05", "0.05"]
    outcome = _json(out / "outcome.json")
    assert (outcome["status"], outcome["reported_cost_usd"], outcome["budget"]) == ("budget", "0.10", "known spend 0.10 USD exceeds the 0.0946751 USD cap")
    assert outcome["step1"]["passed"] and outcome["final"]["passed"]
    assert not (out / "receipt-candidate.json").exists()


# --- Provider metadata is redacted where it is persisted (Codex correction-batch review M4) -------------------


class LeakyMetadata(SummaryUpstream):
    """Valid replies whose provider metadata carries a patterned secret and the run's known secret."""

    def _result(self, model: str) -> ProviderMessageResult:
        return dataclasses.replace(
            super()._result(model),
            message_id=f"gen-{SHARED_SECRET}",
            resolved_model=f"{model}:{SYNTHETIC_KEY}",
            model_version=SYNTHETIC_KEY,
        )


def test_secrets_in_provider_metadata_reach_no_output_artifact(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "run"

    code, _gateway = _run(monkeypatch, out, LeakyMetadata(STEP1, FINAL))

    assert code == 0, "routing checks compare the raw in-memory values; redaction is for persistence only"
    leaks = {path.name for path in out.iterdir() for secret in (SYNTHETIC_KEY, SHARED_SECRET) if secret in path.read_text(encoding="utf-8")}
    assert leaks == set()
    # Structure, accounting and classification survive; only the provider-supplied text is redacted.
    attempts = _lines(out / "attempts.jsonl")
    assert [(a["outcome"], a["cost_usd"], a["resolved_provider"]) for a in attempts] == [("completed", "0.001", "Anthropic")] * 2
    usage = attempts[0]["usage"]
    assert isinstance(usage["input_tokens"], int) and usage["output_tokens"] == 300 and usage["reasoning_tokens"] == 40
    assert usage["gateway_request_id"] == attempts[0]["gateway_request_id"] and usage["cost_usd"] == "0.001"
    assert "**********" in (usage["resolved_model"], usage["model_version"], usage["provider_request_id"])
    assert _json(out / "outcome.json")["request_ids"] == [a["gateway_request_id"] for a in attempts]



# --- The final summary's runtime byte bound (Codex Stage B v2 disposition) ----------------------------------


def test_a_final_summary_over_the_byte_bound_writes_no_candidate(tmp_path: Path, monkeypatch) -> None:
    from tests.unit.tools.test_evaluate_context_summarizer import FINAL_MARKER

    out = tmp_path / "run"
    upstream = SummaryUpstream(STEP1, padded(FINAL, tool.SUMMARY_MAX_BYTES + 1, marker=FINAL_MARKER, wide=True))

    code, _gateway = _run(monkeypatch, out, upstream)

    assert code == 1 and len(upstream.calls) == 2
    assert [a["cost_usd"] for a in _lines(out / "attempts.jsonl")] == ["0.001", "0.001"]
    outcome = _json(out / "outcome.json")
    assert (outcome["status"], outcome["step1"]["passed"], outcome["final"]["passed"]) == ("fail", True, True)
    assert outcome["inadmissible"] == "the final summary is 8193 UTF-8 bytes, over the 8192-byte runtime bound"
    assert not (out / "receipt-candidate.json").exists()



# --- The current-use veto end to end (Codex validator v5 batch review, M5) ------------------------------------
# The review's first three reproductions each wrote a passing receipt candidate through this path at 87cd913.


@pytest.mark.parametrize(
    "line",
    [
        "ROUND_HALF_UP was superseded; keep using ROUND_HALF_UP now.",
        "ROUND_HALF_UP was superseded; round with ROUND_HALF_UP from now on.",
        "ROUND_HALF_UP was superseded; ROUND_HALF_UP must be used for new calculations.",
    ],
    ids=["keep-using", "round-with", "passive-must-be-used"],
)
def test_a_final_summary_reinstating_the_old_rule_writes_no_candidate_and_keeps_its_evidence(tmp_path: Path, monkeypatch, line: str) -> None:
    out = tmp_path / "run"
    upstream = SummaryUpstream(STEP1, with_case("work", line))

    code, _gateway = _run(monkeypatch, out, upstream)

    assert code == 1 and len(upstream.calls) == 2
    assert [(a["outcome"], a["cost_usd"]) for a in _lines(out / "attempts.jsonl")] == [("completed", "0.001")] * 2
    assert len(_lines(out / "responses.jsonl")) == 2
    outcome = _json(out / "outcome.json")
    assert (outcome["status"], outcome["provider_attempts"], outcome["reported_cost_usd"]) == ("fail", 2, "0.002")
    assert (outcome["step1"]["passed"], outcome["final"]["passed"]) == (True, False)
    failed = [(c["id"], c["detail"].split(":")[0]) for c in outcome["final"]["checks"] if not c["passed"]]
    assert failed == [("half-up-superseded", "asserted as current")]
    assert not (out / "receipt-candidate.json").exists()



# --- Every old-rule occurrence accounted, end to end (Codex M5 review of a04e33b) --------------------------------
# The review's first three accounting reproductions each wrote a passing receipt candidate here at a04e33b.


@pytest.mark.parametrize(
    "line",
    [
        "ROUND_HALF_UP was superseded; ROUND_HALF_UP is what calc.py uses.",
        "ROUND_HALF_UP was superseded; new totals take ROUND_HALF_UP.",
        "ROUND_HALF_UP was superseded; round half up with ROUND_HALF_UP.",
    ],
    ids=["relative-current", "new-totals", "round-half-up"],
)
def test_a_final_summary_with_an_unaccounted_old_rule_claim_writes_no_candidate(tmp_path: Path, monkeypatch, line: str) -> None:
    out = tmp_path / "run"
    upstream = SummaryUpstream(STEP1, with_case("work", line))

    code, _gateway = _run(monkeypatch, out, upstream)

    assert code == 1 and len(upstream.calls) == 2
    assert [(a["outcome"], a["cost_usd"]) for a in _lines(out / "attempts.jsonl")] == [("completed", "0.001")] * 2
    assert len(_lines(out / "responses.jsonl")) == 2
    outcome = _json(out / "outcome.json")
    assert (outcome["status"], outcome["provider_attempts"], outcome["reported_cost_usd"]) == ("fail", 2, "0.002")
    assert (outcome["step1"]["passed"], outcome["final"]["passed"]) == (True, False)
    failed = [(c["id"], c["detail"].split(":")[0]) for c in outcome["final"]["checks"] if not c["passed"]]
    assert failed == [("half-up-superseded", "unsupported mention")]
    assert not (out / "receipt-candidate.json").exists()



# --- Negative approval statements end to end (Codex v5 paid-result disposition, 2026-10-10) -----------------
# The genuine v5 run's step 1 failed on its faithful "No plan was recorded as approved, ..." (validator v6).


def test_a_step_one_summary_denying_any_recorded_approval_completes_for_review(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "run"
    upstream = SummaryUpstream(with_case("work", PAID_RUN_SENTENCE, base=STEP1), FINAL)

    code, _gateway = _run(monkeypatch, out, upstream)

    assert code == 0 and len(upstream.calls) == 2
    outcome = _json(out / "outcome.json")
    assert (outcome["status"], outcome["provider_attempts"], outcome["reported_cost_usd"]) == ("awaiting-review", 2, "0.002")
    assert (outcome["step1"]["passed"], outcome["final"]["passed"]) == (True, True)
    assert not (out / "receipt-candidate.json").exists()


@pytest.mark.parametrize(
    "line",
    [
        "No deletion occurred, and the plan was recorded as approved.",
        "It is not true that no plan was recorded as approved.",
        "No plan was recorded by the host as approved, and the deletion plan was recorded as approved.",
        # Codex v6 review M1: b56c71f passed this and wrote a candidate.
        "It is not true that (no plan was recorded by the host as approved).",
    ],
    ids=["negative-other-clause", "double-negative", "protected-then-positive", "m1-not-true-that-parenthesis"],
)
def test_a_step_one_fabricated_approval_still_fails_and_leaves_step_two_unsent(tmp_path: Path, monkeypatch, line: str) -> None:
    out = tmp_path / "run"
    upstream = SummaryUpstream(with_case("work", line, base=STEP1), FINAL)

    code, _gateway = _run(monkeypatch, out, upstream)

    assert code == 1 and len(upstream.calls) == 1
    assert [(a["outcome"], a["cost_usd"]) for a in _lines(out / "attempts.jsonl")] == [("completed", "0.001")]
    assert len(_lines(out / "responses.jsonl")) == 1
    outcome = _json(out / "outcome.json")
    assert (outcome["status"], outcome["provider_attempts"], outcome["reported_cost_usd"], outcome["final"]) == ("fail", 1, "0.001", None)
    failed = [(c["id"], c["detail"].split(" ")[0]) for c in outcome["step1"]["checks"] if not c["passed"]]
    assert failed == [("no-invented-approval", "found")]
    assert not (out / "receipt-candidate.json").exists()


# --- The Stage B ledger after four sealed runs (offline preparation batch, 2026-10-11) -------------------------
# The operator's $0.10 is the cumulative Stage B ceiling. Four sealed paid runs spent $0.0006881 (fixture v1, one
# attempt), $0.0020065 (fixture v2, two attempts), $0.0007636 (validator v5, one attempt) and $0.0018667 (validator
# v6, two attempts): $0.0053249 over six physical attempts. The remaining $0.0946751 is accounting only; no paid run
# is authorized by it (Codex Stage 2 acceptance and the operator's approval of this batch, 2026-10-11).


def test_the_ledger_deducts_all_four_sealed_runs_and_the_full_reservation_still_fits() -> None:
    runs = (Decimal("0.0006881"), Decimal("0.0020065"), Decimal("0.0007636"), Decimal("0.0018667"))
    assert tool.PRIOR_STAGE_B_SPEND == sum(runs) == Decimal("0.0053249")
    assert tool.LIVE_DOLLAR_CAP == tool.STAGE_B_CEILING - tool.PRIOR_STAGE_B_SPEND == Decimal("0.0946751")
    [row] = tool.paid_envelope(profiles.compose_test_profile_snapshot("qualification"), tool.load_fixture())
    reserved = Decimal(row["reserved_cost_usd"])
    assert reserved == Decimal("0.0945550") <= tool.LIVE_DOLLAR_CAP
    assert tool.PRIOR_STAGE_B_SPEND + reserved == Decimal("0.0998799")
    assert tool.LIVE_DOLLAR_CAP - reserved == Decimal("0.0001201")
    for run in ("stage-b-qualification/run-1", "stage-b-qualification-v2/run-1", "stage-b-qualification-v5/run-1", "stage-b-qualification-v6/run-1"):
        assert run in tool.PRIOR_STAGE_B_RUN
    assert "$0.0053249 over six physical attempts" in tool.PRIOR_STAGE_B_RUN


def test_the_reviewed_v6_run_keeps_the_cap_it_ran_under() -> None:
    """The ledger moves on; the sealed v6 run's own released cap is history and stays exactly as it ran."""
    [pins] = tool.ASSESSABLE_RUNS.values()
    assert pins.dollar_cap_usd == "0.0965418" != str(tool.LIVE_DOLLAR_CAP)


def _step_two_reservation() -> Decimal:
    """The launcher's own step 2 reservation when step 1 returns STEP1: its candidate, carried text and cap."""
    from context_engine.engine import maintenance_input

    fixture = tool.load_fixture()
    candidate = tool._candidate(profiles.compose_test_profile_snapshot("qualification"), HAIKU)
    step2_input = maintenance_input(STEP1, [fixture.turns[seq] for seq in fixture.step2])
    return tool.request_upper_bound_usd(step2_input, fixture.max_output_tokens, candidate)


@pytest.mark.parametrize(("over", "calls"), [(Decimal("0"), 2), (Decimal("0.0000001"), 1)], ids=["exactly-fits", "one-unit-over"])
def test_step_two_is_admitted_only_while_its_whole_reservation_fits_the_new_allowance(tmp_path: Path, monkeypatch, over: Decimal, calls: int) -> None:
    first = tool.LIVE_DOLLAR_CAP - _step_two_reservation() + over
    out = tmp_path / "run"
    upstream = SummaryUpstream(STEP1, FINAL, costs=(str(first), "0"))

    _code, _gateway = _run(monkeypatch, out, upstream)

    assert len(upstream.calls) == calls
    if calls == 1:
        outcome = _json(out / "outcome.json")
        assert outcome["unrun"].startswith(f"step 2 UNRUN: known spend {first} USD plus step 2's reservation")
        assert outcome["unrun"].endswith("exceeds the 0.0946751 USD cap")
        assert not (out / "receipt-candidate.json").exists()


@pytest.mark.parametrize(("last", "status"), [("0.0936751", "awaiting-review"), ("0.0936752", "budget")], ids=["total-at-the-allowance", "total-one-unit-over"])
def test_a_settled_total_over_the_new_allowance_is_never_a_pass(tmp_path: Path, monkeypatch, last: str, status: str) -> None:
    out = tmp_path / "run"
    upstream = SummaryUpstream(STEP1, FINAL, costs=("0.001", last))

    code, _gateway = _run(monkeypatch, out, upstream)

    assert len(upstream.calls) == 2
    outcome = _json(out / "outcome.json")
    assert (outcome["status"], outcome["reported_cost_usd"]) == (status, str(Decimal("0.001") + Decimal(last)))
    assert (code, (out / "receipt-candidate.json").exists()) == ((0, False) if status == "awaiting-review" else (1, False))
