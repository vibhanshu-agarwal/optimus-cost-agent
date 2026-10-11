"""Plan 12.2 offline assessment: `evaluate_context_summarizer.py assess` (Codex qualification-method disposition,
2026-10-10; rubric `context-summary-assessment-v1.1`).

A receipt candidate comes only from `assess`: a sealed genuine run that Codex reviewed and released for
assessment, whose mechanical records verify, and two independent reviews (Claude and Codex) that each pass
every rubric item for both steps. Each sealed run here comes from the scripted launcher harness (the real
Gateway handler with a scripted upstream) and is registered as reviewed only inside its test, so nothing
here can qualify a profile. Every denial keeps the findings and writes no candidate.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from optimus_model_policy import test_profiles as profiles
from optimus_model_policy import validate_registry
from optimus_model_policy.registry import SUMMARY_FIXTURE_DIGEST, SUMMARY_PROMPT_DIGEST, SUMMARY_VALIDATOR, SummaryReceipt
from tests.unit.tools.test_evaluate_context_summarizer import FINAL, STEP1, padded, with_case
from tests.unit.tools.test_qualification_run import HAIKU, SYNTHETIC_KEY, SummaryUpstream, _json, _lines, _run
from tools import evaluate_context_summarizer as tool

COMMIT = "1" * 40
RELEASE = "operator release for this test"
# The genuine v6 run's unsupported supersession wording: a complete run whose final lexical check fails.
FLAGGED = "This supersedes the earlier rule of ROUND_HALF_UP from seq 1."


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seal(run_dir: Path, *, commit: str = COMMIT) -> str:
    """Seal the run's folder as a reviewed experiment folder is sealed: console log, process identity and a
    manifest of every file, written last."""
    folder = run_dir.parent
    console = f"HEAD={commit} started=2026-10-10T16:14:13Z\nexit=0 finished=2026-10-10T16:14:32Z\n"
    (folder / f"{run_dir.name}-console.log").write_text(console, encoding="utf-8", newline="\n")
    (folder / "process-identity.json").write_text('{"chain": "scripted"}\n', encoding="utf-8", newline="\n")
    files = sorted(path for path in folder.rglob("*") if path.is_file())
    manifest = "".join(f"{_sha(path)} *{path.relative_to(folder).as_posix()}\n" for path in files)
    (folder / "MANIFEST.sha256").write_text(manifest, encoding="utf-8", newline="\n")
    return _sha(folder / "MANIFEST.sha256")


def _register(monkeypatch: pytest.MonkeyPatch, run_dir: Path, **changes: Any) -> None:
    """Release this synthetic run for assessment, for this test only."""
    run, outcome = _json(run_dir / "run.json"), _json(run_dir / "outcome.json")
    pins = tool.ReviewedRun(
        manifest_sha256=_sha(run_dir.parent / "MANIFEST.sha256"),
        commit=COMMIT,
        tool_sha256=run["tool_sha256"],
        executed_validator="context-summary-validator-v6",
        prompt_digest=SUMMARY_PROMPT_DIGEST,
        dollar_cap_usd=run["dollar_cap_usd"],
        request_ids=tuple(outcome["request_ids"]),
    )
    monkeypatch.setattr(tool, "ASSESSABLE_RUNS", {run["run_id"]: dataclasses.replace(pins, **changes)})


def _sealed_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *texts: str, before_seal=None, **kwargs: Any) -> Path:
    run_dir = tmp_path / "experiment" / "run-1"
    _run(monkeypatch, run_dir, SummaryUpstream(*texts, **kwargs))
    if before_seal is not None:
        before_seal(run_dir)
    _seal(run_dir)
    _register(monkeypatch, run_dir)
    return run_dir


def _review(run_dir: Path, reviewer: str) -> dict[str, Any]:
    """A complete passing review of both steps of `run_dir`, every item cited."""
    run, outcome = _json(run_dir / "run.json"), _json(run_dir / "outcome.json")
    responses = _lines(run_dir / "responses.jsonl")
    steps = {}
    # A run with one reply gets a step 1 record only.
    for (step, (r_items, f_items)), response in zip(tool.REVIEW_ITEMS.items(), responses, strict=False):
        flagged = [check["id"] for check in outcome[step]["checks"] if not check["passed"]]
        steps[step] = {
            "response_sha256": hashlib.sha256(response["text"].encode("utf-8")).hexdigest(),
            "request_id": response["attempts"][-1]["gateway_request_id"],
            "R": {item: {"status": "PASS", "source": "seq 1", "summary": f"passage for {item}"} for item in r_items},
            "F": {item: {"status": "ABSENT", "source": "seq 1-7", "summary": "no such claim"} for item in f_items},
            "lexical": {check: {"resolution": "CLEARED", "source": "seq 7", "summary": "accurate wording"} for check in flagged},
            "minor": [],
            "material": [],
            "overall": "PASS",
        }
    return {
        "assessment": tool.ASSESSMENT_VERSION,
        "rubric_sha256": tool.ASSESSMENT_RUBRIC_SHA256,
        "reviewer": reviewer,
        "exposure": "retrospective; the published failure history was known",
        "run_id": run["run_id"],
        "run_manifest_sha256": _sha(run_dir.parent / "MANIFEST.sha256"),
        "fixture_digest": SUMMARY_FIXTURE_DIGEST,
        "prompt_digest": SUMMARY_PROMPT_DIGEST,
        "steps": steps,
        "overall": "PASS",
    }


def _assess(tmp_path: Path, run_dir: Path, *reviews: dict[str, Any], out: Path | None = None) -> tuple[int, Path]:
    paths = []
    for index, review in enumerate(reviews):
        path = tmp_path / f"review-{index}.json"
        path.write_text(json.dumps(review), encoding="utf-8")
        paths.append(path)
    out = out or tmp_path / "assessment"
    argv = ["assess", "--run", str(run_dir), "--release", RELEASE, "--out", str(out)]
    for path in paths:
        argv += ["--review", str(path)]
    return tool.main(argv), out


def _denied(code: int, out: Path, reason: str) -> dict[str, Any]:
    record = _json(out / "assessment.json")
    assert (code, record["status"]) == (1, "denied"), record
    assert any(reason in item for item in record["reasons"]), record["reasons"]
    assert not (out / "receipt-candidate.json").exists()
    return record


# --- The rubric and the qualification key ---------------------------------------------------------------


def test_the_filed_rubric_is_the_reviewed_one_and_the_registry_requires_its_assessment() -> None:
    assert tool.ASSESSMENT_VERSION == SUMMARY_VALIDATOR == "context-summary-assessment-v1.1"
    assert _sha(tool.RUBRIC_PATH) == tool.ASSESSMENT_RUBRIC_SHA256 == "d982589a06aee03e9f7b70bf5f842b01d976a1a033dfa4dfa1145a9a667c4b4c"  # pragma: allowlist secret - public rubric digest
    assert tool.RUBRIC_PATH.read_text(encoding="utf-8").startswith("# context-summary-assessment-v1.1")


def test_only_the_reviewed_v6_run_is_released_for_assessment() -> None:
    [(run_id, pins)] = tool.ASSESSABLE_RUNS.items()
    assert run_id == "a37f6074135e4392b93b0826391defc0"  # pragma: allowlist secret - public run id
    assert pins == tool.ReviewedRun(
        manifest_sha256="b2cbf077eba8a991bdd3423b0834c8a1d8bc79b8f49e9b9657ea932590825732",  # pragma: allowlist secret - public evidence digest
        commit="80399ca110f36c98edffdc1ddc7d8efac4d2ad1f",  # pragma: allowlist secret - public commit
        tool_sha256="d8a2c9218bbeb72a93f2f843f61bfa7bb51998b92bf1701bd368eaf363a2e54d",  # pragma: allowlist secret - public tool digest
        executed_validator="context-summary-validator-v6",
        prompt_digest="6d1b4e77d77f1a7331932633dbc39ae4f1c3bf5c4a79acf8aed9873b410902db",  # pragma: allowlist secret - public prompt digest
        dollar_cap_usd="0.0965418",
        request_ids=("gw-142d038d8be1423bba3a4c286f813726", "gw-52fac698887f4b69b98f33ad60e0650b"),  # pragma: allowlist secret - public request ids
    )


def test_the_review_covers_every_rubric_item_for_each_step() -> None:
    assert tool.REVIEW_ITEMS == {
        "step1": (("R1", "R2", "R3", "R4", "R5", "R6", "R8", "R9"), ("F1", "F2", "F3", "F4", "F6", "F7")),
        "final": (("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9"), ("F1", "F2", "F3", "F4", "F5", "F6", "F7")),
    }


# --- The one positive path ------------------------------------------------------------------------------


def _backdated(run_dir: Path) -> None:
    """The run started before the assessment day, so the receipt's run date and the assessment date differ."""
    run = _json(run_dir / "run.json")
    run["started_at"] = "2026-10-09T11:36:30+00:00"
    (run_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8", newline="\n")


def test_two_passing_reviews_of_a_verified_run_yield_the_candidate_and_qualify_nothing(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL, before_seal=_backdated)
    sealed = _snapshot(run_dir.parent)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")

    code, out = _assess(tmp_path, run_dir, claude, codex)

    assert code == 0
    run, outcome = _json(run_dir / "run.json"), _json(run_dir / "outcome.json")
    candidate = _json(out / "receipt-candidate.json")
    receipt = SummaryReceipt.model_validate(candidate["receipt"])
    assert (receipt.validator, receipt.fixture_digest, receipt.prompt_digest) == (SUMMARY_VALIDATOR, SUMMARY_FIXTURE_DIGEST, SUMMARY_PROMPT_DIGEST)
    assert (receipt.model_id, receipt.providers, receipt.quantizations, receipt.reasoning) == (HAIKU, tuple(run["providers"]), tuple(run["quantizations"]), run["reasoning"])
    # The original genuine request IDs and run date; the assessment date is recorded separately.
    assert (list(receipt.request_ids), receipt.recorded_on) == (outcome["request_ids"], "2026-10-09")
    record = _json(out / "assessment.json")
    assert record["assessed_at"][:10] != receipt.recorded_on
    assert (record["status"], record["assessment"], record["rubric_sha256"]) == ("pass", tool.ASSESSMENT_VERSION, tool.ASSESSMENT_RUBRIC_SHA256)
    assert record["original_execution"]["validator"] == "context-summary-validator-v6"
    assert record["original_execution"]["status"] == outcome["status"]
    assert record["run"]["run_id"] == run["run_id"] and record["release"] == RELEASE
    # Each review is kept whole, every string through the evidence sanitizer, beside its raw input's hash.
    assert [r["record"] for r in record["reviews"]] == [claude, codex]
    assert [r["raw_input_sha256"] for r in record["reviews"]] == [_sha(tmp_path / "review-0.json"), _sha(tmp_path / "review-1.json")]
    assert candidate["assessment_sha256"] == _sha(out / "assessment.json")
    # The sealed experiment is untouched, and no profile is qualified by the candidate.
    assert _snapshot(run_dir.parent) == sealed
    for name in ("qualification", "attached"):
        if profiles.TEST_PROFILES[name].override is not None:
            issues = validate_registry(profiles.compose_test_profile_snapshot(name))
            assert any(issue.code == "SUMMARIZER_UNQUALIFIED" for issue in issues)


def test_a_complete_run_with_a_lexical_flag_passes_only_once_both_reviews_resolve_it(tmp_path: Path, monkeypatch) -> None:
    final = with_case("constraints", FLAGGED, "ROUND_HALF_UP was superseded by that correction.")
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, final)
    assert _json(run_dir / "outcome.json")["status"] == "fail", "the executed lexical check failed"
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")
    assert list(claude["steps"]["final"]["lexical"]) == ["half-up-superseded"]
    unresolved = json.loads(json.dumps(codex))
    del unresolved["steps"]["final"]["lexical"]["half-up-superseded"]

    _denied(*_assess(tmp_path, run_dir, claude, unresolved, out=tmp_path / "denied"), "lexical")
    code, out = _assess(tmp_path, run_dir, claude, codex, out=tmp_path / "passed")

    assert code == 0 and (out / "receipt-candidate.json").exists()
    record = _json(out / "assessment.json")
    assert [c["id"] for c in record["original_execution"]["final"]["checks"] if not c["passed"]] == ["half-up-superseded"]


# --- Reviewer findings that deny ------------------------------------------------------------------------


def _edited(review: dict[str, Any], path: tuple[Any, ...], value: Any) -> dict[str, Any]:
    edited = json.loads(json.dumps(review))
    node = edited
    for key in path[:-1]:
        node = node[key]
    if value is _DELETE:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return edited


_DELETE = object()


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("steps", "step1", "R", "R4", "status"), "FAIL", "does not pass"),
        (("steps", "final", "R", "R8", "status"), "UNCERTAIN", "does not pass"),
        (("steps", "final", "F", "F6", "status"), "PRESENT", "does not pass"),
        (("steps", "step1", "F", "F1", "status"), "UNCERTAIN", "does not pass"),
        (("steps", "final", "material"), ["the current rule is ambiguous"], "material"),
        (("steps", "final", "overall"), "FAIL", "does not pass"),
        (("overall",), "NOT-PASS-UNCERTAIN", "does not pass"),
    ],
    ids=["R-fail", "R-uncertain", "F-present", "F-uncertain", "material", "step-overall", "run-overall"],
)
def test_either_reviewer_not_passing_denies(tmp_path: Path, monkeypatch, path, value, reason) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")

    failing = _edited(codex, path, value)
    record = _denied(*_assess(tmp_path, run_dir, claude, failing), reason)

    # The findings are kept whole: the failing review exactly as submitted, beside its raw hash.
    [kept] = [r for r in record["reviews"] if r["record"]["reviewer"] == "codex"]
    assert (kept["record"], kept["raw_input_sha256"]) == (failing, _sha(tmp_path / "review-1.json"))


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        (("steps", "step1", "R", "R8"), "R8"),
        (("steps", "final", "R", "R9"), "R9"),
        (("steps", "final", "F", "F5"), "F5"),
        (("steps", "step1", "R", "R2", "summary"), "citation"),
        (("steps", "final", "F", "F6", "source"), "citation"),
        (("exposure",), "exposure"),
        (("steps", "final"), "final"),
    ],
    ids=["missing-R8", "missing-R9", "missing-F5", "R-without-summary-citation", "F-without-source-citation", "no-exposure", "no-final-step"],
)
def test_an_incomplete_review_denies(tmp_path: Path, monkeypatch, path, reason) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")

    _denied(*_assess(tmp_path, run_dir, _edited(claude, path, _DELETE), codex), reason)


def test_an_extra_rubric_item_or_an_unknown_status_denies(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")
    step1_r7 = _edited(claude, ("steps", "step1", "R", "R7"), {"status": "PASS", "source": "seq 7", "summary": "x"})

    _denied(*_assess(tmp_path, run_dir, step1_r7, codex, out=tmp_path / "extra"), "R7")
    _denied(*_assess(tmp_path, run_dir, claude, _edited(codex, ("steps", "final", "R", "R1", "status"), "OK"), out=tmp_path / "status"), "status")


def test_a_confirmed_lexical_flag_denies(tmp_path: Path, monkeypatch) -> None:
    final = with_case("constraints", FLAGGED, "ROUND_HALF_UP was superseded by that correction.")
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, final)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")
    confirmed = _edited(codex, ("steps", "final", "lexical", "half-up-superseded", "resolution"), "CONFIRMED")

    _denied(*_assess(tmp_path, run_dir, claude, confirmed), "does not pass")


def test_a_lexical_resolution_for_a_check_that_did_not_fail_denies(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")
    invented = _edited(claude, ("steps", "final", "lexical", "no-eval"), {"resolution": "CLEARED", "source": "seq 1", "summary": "x"})

    _denied(*_assess(tmp_path, run_dir, invented, codex), "lexical")


def test_reviewers_disclosing_different_minor_findings_deny(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")
    minor = [{"key": "linter-paste-attribution", "note": "the seq 4 linter text is called user-pasted"}]
    agreed = (_edited(claude, ("steps", "final", "minor"), minor), _edited(codex, ("steps", "final", "minor"), minor))

    _denied(*_assess(tmp_path, run_dir, agreed[0], codex, out=tmp_path / "differ"), "minor findings differ")
    code, out = _assess(tmp_path, run_dir, *agreed, out=tmp_path / "agree")

    assert code == 0, _json(out / "assessment.json")["reasons"]
    assert [r["record"]["steps"]["final"]["minor"] for r in _json(out / "assessment.json")["reviews"]] == [minor, minor]


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("assessment",), "context-summary-assessment-v1", "assessment"),
        (("rubric_sha256",), "0" * 64, "rubric"),
        (("run_id",), "0" * 32, "run"),
        (("run_manifest_sha256",), "0" * 64, "manifest"),
        (("fixture_digest",), "0" * 64, "fixture"),
        (("prompt_digest",), "0" * 64, "prompt"),
        (("steps", "final", "response_sha256"), "0" * 64, "response"),
        (("steps", "step1", "request_id"), "gw-other", "request"),
        (("reviewer",), "fable", "reviewer"),
    ],
    ids=["assessment", "rubric", "run", "manifest", "fixture", "prompt", "response", "request", "unknown-reviewer"],
)
def test_a_review_of_anything_else_denies(tmp_path: Path, monkeypatch, path, value, reason) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")

    _denied(*_assess(tmp_path, run_dir, claude, _edited(codex, path, value)), reason)


@pytest.mark.parametrize("count", [1, 3], ids=["one-review", "three-reviews"])
def test_exactly_two_reviews_are_required(tmp_path: Path, monkeypatch, count: int) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    reviews = [_review(run_dir, "claude"), _review(run_dir, "codex"), _review(run_dir, "codex")][:count]

    _denied(*_assess(tmp_path, run_dir, *reviews), "exactly two reviews")


def test_a_duplicate_reviewer_denies(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)

    _denied(*_assess(tmp_path, run_dir, _review(run_dir, "claude"), _review(run_dir, "claude")), "Claude and Codex")


def test_an_unreadable_review_denies_and_keeps_its_hash(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    codex = tmp_path / "codex.json"
    codex.write_text(json.dumps(_review(run_dir, "codex")), encoding="utf-8")
    out = tmp_path / "assessment"

    code = tool.main(["assess", "--run", str(run_dir), "--review", str(broken), "--review", str(codex), "--release", RELEASE, "--out", str(out)])

    record = _denied(code, out, "not a JSON")
    assert [(r["raw_input_sha256"], r["record"]) for r in record["reviews"]][0] == (_sha(broken), None)


# --- Mechanical evidence that denies --------------------------------------------------------------------


def test_an_altered_sealed_file_denies(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")
    outcome = run_dir / "outcome.json"
    outcome.write_text(outcome.read_text(encoding="utf-8") + " ", encoding="utf-8")

    _denied(*_assess(tmp_path, run_dir, claude, codex), "altered")


def test_a_resealed_folder_is_not_the_reviewed_seal(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")
    (run_dir.parent / "note.txt").write_text("added after review\n", encoding="utf-8")
    _seal(run_dir)

    _denied(*_assess(tmp_path, run_dir, claude, codex), "reviewed manifest")


def test_an_unsealed_file_beside_the_run_denies(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")
    (run_dir / "extra.json").write_text("{}\n", encoding="utf-8")

    _denied(*_assess(tmp_path, run_dir, claude, codex), "unsealed")


def test_a_run_not_released_for_assessment_denies(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")
    monkeypatch.setattr(tool, "ASSESSABLE_RUNS", {"0" * 32: next(iter(tool.ASSESSABLE_RUNS.values()))})

    _denied(*_assess(tmp_path, run_dir, claude, codex), "not a run released for assessment")


def test_synthetic_evidence_that_is_not_a_sealed_run_denies(tmp_path: Path) -> None:
    controls = tmp_path / "inputs" / "controls"
    controls.mkdir(parents=True)
    (controls / "F02.txt").write_text(FINAL, encoding="utf-8")

    code, out = _assess(tmp_path, controls, {"reviewer": "claude"}, {"reviewer": "codex"})

    _denied(code, out, "not a sealed run")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("commit", "2" * 40, "commit"),
        ("tool_sha256", "0" * 64, "tool"),
        ("executed_validator", "context-summary-validator-v5", "validator"),
        ("prompt_digest", "0" * 64, "prompt"),
        ("dollar_cap_usd", "0.05", "cap"),
        ("request_ids", ("gw-a", "gw-b"), "request"),
    ],
    ids=["commit", "tool", "executed-validator", "prompt", "cap", "request-ids"],
)
def test_a_run_whose_records_differ_from_its_reviewed_identity_denies(tmp_path: Path, monkeypatch, field, value, reason) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")
    _register(monkeypatch, run_dir, **{field: value})

    _denied(*_assess(tmp_path, run_dir, claude, codex), reason)


def test_a_run_with_step_two_unrun_denies(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1.replace("Use Decimal for every amount, never float. ", ""), FINAL)
    assert len(_lines(run_dir / "responses.jsonl")) == 1
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")

    _denied(*_assess(tmp_path, run_dir, claude, codex), "two replies")


class FinishingUpstream(SummaryUpstream):
    """Scripted replies whose second finishes with `finish`."""

    def __init__(self, *texts: str, finish: str, **kwargs: Any) -> None:
        super().__init__(*texts, **kwargs)
        self.finish = finish

    def _result(self, model: str):
        result = super()._result(model)
        return dataclasses.replace(result, finish_reason=self.finish) if len(self.calls) == 2 else result


def test_a_truncated_final_reply_denies(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "experiment" / "run-1"
    _run(monkeypatch, run_dir, FinishingUpstream(STEP1, FINAL, finish="length"))
    _seal(run_dir)
    _register(monkeypatch, run_dir)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")

    # The reply's own finish status is checked, not only its attempt's.
    _denied(*_assess(tmp_path, run_dir, claude, codex), "the final reply did not finish with stop")


def test_an_oversize_final_summary_denies(tmp_path: Path, monkeypatch) -> None:
    oversize = padded(FINAL, tool.SUMMARY_MAX_BYTES + 1, marker="The plan was not approved.")
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, oversize)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")

    # The byte bound is recomputed from the sealed reply, not only read from the recorded "inadmissible".
    _denied(*_assess(tmp_path, run_dir, claude, codex), f"the final summary is over {tool.SUMMARY_MAX_BYTES} UTF-8 bytes")


def test_a_malformed_final_summary_denies(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL.split("## Unresolved matters")[0])
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")

    _denied(*_assess(tmp_path, run_dir, claude, codex), "format")


def test_an_over_budget_run_denies(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL, costs=("0.001", "0.0965"))
    assert _json(run_dir / "outcome.json")["status"] == "budget"
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")

    _denied(*_assess(tmp_path, run_dir, claude, codex), "budget")


def _unknown_cost(run_dir: Path) -> None:
    attempts = run_dir / "attempts.jsonl"
    lines = attempts.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    record["cost_usd"] = None
    attempts.write_text("\n".join([*lines[:-1], json.dumps(record)]) + "\n", encoding="utf-8")


def test_an_attempt_of_unknown_cost_denies(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL, before_seal=_unknown_cost)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")

    _denied(*_assess(tmp_path, run_dir, claude, codex), "cost")


def test_an_attempt_off_the_reviewed_route_denies(tmp_path: Path, monkeypatch) -> None:
    def off_route(run_dir: Path) -> None:
        attempts = run_dir / "attempts.jsonl"
        attempts.write_text(attempts.read_text(encoding="utf-8").replace('"resolved_provider": "Anthropic"', '"resolved_provider": "Google"'), encoding="utf-8")

    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL, before_seal=off_route)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")

    _denied(*_assess(tmp_path, run_dir, claude, codex), "route")


def test_a_recorded_lexical_finding_that_does_not_match_the_reply_denies(tmp_path: Path, monkeypatch) -> None:
    def rewritten(run_dir: Path) -> None:
        outcome = _json(run_dir / "outcome.json")
        outcome["final"]["checks"][0]["detail"] = "edited"
        (run_dir / "outcome.json").write_text(json.dumps(outcome), encoding="utf-8")

    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL, before_seal=rewritten)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")

    _denied(*_assess(tmp_path, run_dir, claude, codex), "recorded fact report")


# --- Refusals before anything is written ----------------------------------------------------------------


def test_an_existing_output_folder_is_refused_and_left_unchanged(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    out = tmp_path / "assessment"
    out.mkdir()
    (out / "kept.txt").write_text("earlier\n", encoding="utf-8")

    code, _ = _assess(tmp_path, run_dir, _review(run_dir, "claude"), _review(run_dir, "codex"), out=out)

    assert code == 2
    assert sorted(p.name for p in out.iterdir()) == ["kept.txt"]


def test_a_drifted_rubric_file_is_refused(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    monkeypatch.setattr(tool, "ASSESSMENT_RUBRIC_SHA256", "0" * 64)

    code, out = _assess(tmp_path, run_dir, _review(run_dir, "claude"), _review(run_dir, "codex"))

    assert code == 2 and not out.exists()


def test_an_empty_release_reference_is_refused(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    paths = []
    for name in ("claude", "codex"):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(_review(run_dir, name)), encoding="utf-8")
        paths.append(path)
    out = tmp_path / "assessment"

    code = tool.main(["assess", "--run", str(run_dir), "--review", str(paths[0]), "--review", str(paths[1]), "--release", " ", "--out", str(out)])

    assert code == 2 and not out.exists()


# --- Corrections at 10dde0b (Codex Stage 1 review: M1 output location, M2 complete findings) -----------------


def _snapshot(folder: Path) -> dict[str, str]:
    """Every file under `folder`, by relative path, with its SHA-256: the folder's inventory and bytes."""
    return {path.relative_to(folder).as_posix(): _sha(path) for path in folder.rglob("*") if path.is_file()}


def _alias(target: Path, link: Path) -> None:
    """`link` as a directory alias of `target`: a symbolic link, or else a Windows junction."""
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError as symlink_error:
        if sys.platform != "win32":
            pytest.skip(f"no directory alias can be created here: {symlink_error}")
        import _winapi

        _winapi.CreateJunction(str(target), str(link))


@pytest.mark.parametrize("where", ["under-the-run", "beside-the-run", "through-an-alias"])
@pytest.mark.parametrize("reviews", ["passing", "denied"])
def test_an_output_inside_the_sealed_experiment_is_refused_before_any_write(tmp_path: Path, monkeypatch, where: str, reviews: str) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    experiment = run_dir.parent
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")
    if reviews == "denied":
        codex = _edited(codex, ("steps", "final", "R", "R8"), _DELETE)
    if where == "through-an-alias":
        _alias(experiment, tmp_path / "alias")
    out = {"under-the-run": run_dir / "assessment", "beside-the-run": experiment / "assessment", "through-an-alias": tmp_path / "alias" / "assessment"}[where]
    before = _snapshot(experiment)

    code, _ = _assess(tmp_path, run_dir, claude, codex, out=out)

    assert code == 2 and not out.exists()
    assert _snapshot(experiment) == before, "the sealed experiment keeps its exact inventory and bytes"


def test_an_output_beside_the_experiment_with_a_shared_name_prefix_is_outside_it(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)

    code, out = _assess(tmp_path, run_dir, _review(run_dir, "claude"), _review(run_dir, "codex"), out=tmp_path / "experiment-assessment")

    assert code == 0 and (out / "receipt-candidate.json").exists()


_MINOR = {"key": "linter-paste-attribution", "note": "the seq 4 linter text is called user-pasted; no authority, effect or verification follows"}


@pytest.mark.parametrize(
    ("minor", "reason"),
    [
        ([{"key": "linter-paste-attribution"}], "non-empty key and note"),
        ([{"key": "linter-paste-attribution", "note": "  "}], "non-empty key and note"),
        ([{"key": "linter-paste-attribution", "note": 7}], "non-empty key and note"),
        ([{"key": "", "note": "a note without a key"}], "non-empty key and note"),
        ([_MINOR, {"key": "linter-paste-attribution", "note": "the same finding again"}], "repeats a minor finding key"),
        ("linter-paste-attribution", "must be a list"),
        (["linter-paste-attribution"], "non-empty key and note"),
    ],
    ids=["no-note", "blank-note", "non-string-note", "blank-key", "duplicate-key", "not-a-list", "bare-string-entry"],
)
def test_a_minor_finding_needs_a_unique_key_and_a_note(tmp_path: Path, monkeypatch, minor, reason) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    claude = _edited(_review(run_dir, "claude"), ("steps", "final", "minor"), minor)
    codex = _edited(_review(run_dir, "codex"), ("steps", "final", "minor"), minor)

    record = _denied(*_assess(tmp_path, run_dir, claude, codex), reason)

    assert [r["record"]["steps"]["final"]["minor"] for r in record["reviews"]] == [minor, minor]


def test_matching_minor_keys_with_independently_phrased_notes_pass(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    claude_note = {"key": "linter-paste-attribution", "note": "Claude: the linter output is described as pasted by the user; it grants nothing."}
    codex_note = {"key": "linter-paste-attribution", "note": "Codex: completion text attributed to a paste; no authority, effect or verification."}
    claude = _edited(_review(run_dir, "claude"), ("steps", "final", "minor"), [claude_note])
    codex = _edited(_review(run_dir, "codex"), ("steps", "final", "minor"), [codex_note])

    code, out = _assess(tmp_path, run_dir, claude, codex)

    assert code == 0, _json(out / "assessment.json")["reasons"]
    assert [r["record"]["steps"]["final"]["minor"] for r in _json(out / "assessment.json")["reviews"]] == [[claude_note], [codex_note]]


def test_a_shared_minor_key_cannot_clear_a_failing_item(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    claude = _edited(_review(run_dir, "claude"), ("steps", "final", "minor"), [_MINOR])
    codex = _edited(_edited(_review(run_dir, "codex"), ("steps", "final", "minor"), [_MINOR]), ("steps", "final", "R", "R8", "status"), "FAIL")

    _denied(*_assess(tmp_path, run_dir, claude, codex), "R8 is FAIL")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("steps",), ["step1", "final"]),
        (("steps", "final"), "PASS"),
        (("steps", "final", "R"), ["R1", "R2"]),
        (("steps", "final", "F", "F1"), "ABSENT"),
        (("steps", "final", "lexical"), "CLEARED"),
        (("steps", "final", "material"), "none"),
        (("exposure",), 7),
    ],
    ids=["steps-a-list", "step-a-string", "R-a-list", "F-entry-a-string", "lexical-a-string", "material-a-string", "exposure-a-number"],
)
def test_malformed_review_data_is_a_recorded_denial(tmp_path: Path, monkeypatch, path, value) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    malformed = _edited(_review(run_dir, "codex"), path, value)

    code, out = _assess(tmp_path, run_dir, _review(run_dir, "claude"), malformed)

    record = _json(out / "assessment.json")
    assert (code, record["status"], (out / "receipt-candidate.json").exists()) == (1, "denied", False)
    assert record["reviews"][1]["record"] == malformed


def test_a_review_that_is_not_a_json_object_is_a_recorded_denial(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)

    record = _denied(*_assess(tmp_path, run_dir, _review(run_dir, "claude"), ["claude", "PASS"]), "not a JSON object")

    assert record["reviews"][1]["record"] == ["claude", "PASS"]


@pytest.mark.parametrize("step", ["step1", "final"])
@pytest.mark.parametrize("value", [7, True, 1.5, 0, None], ids=["integer", "boolean", "float", "zero", "null"])
def test_a_minor_value_that_is_not_a_list_is_a_recorded_denial(tmp_path: Path, monkeypatch, step, value) -> None:
    # Codex review of 6bf0a48: a scalar here crashed the reviewers' minor-key comparison, losing the record.
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    malformed = _edited(_review(run_dir, "codex"), ("steps", step, "minor"), value)

    record = _denied(*_assess(tmp_path, run_dir, _review(run_dir, "claude"), malformed), f"codex: {step} minor findings must be a list")

    assert (record["reviews"][1]["raw_input_sha256"], record["reviews"][1]["record"]) == (_sha(tmp_path / "review-1.json"), malformed)


def _nested(review: dict[str, Any], depth: int) -> str:
    """`review` as JSON text with an extra field nesting the document `depth` levels deep, counting the review
    object and each value within it. Built as text, so no recursive encoder touches it."""
    return json.dumps({**review, "extra": "NESTED"}).replace('"NESTED"', "[" * (depth - 1) + "]" * (depth - 1))


def _assess_files(tmp_path: Path, run_dir: Path, claude: str, codex: str) -> tuple[int, Path, list[Path]]:
    paths = [tmp_path / "claude.json", tmp_path / "codex.json"]
    for path, text in zip(paths, (claude, codex), strict=True):
        path.write_text(text, encoding="utf-8")
    out = tmp_path / "assessment"
    argv = ["assess", "--run", str(run_dir), "--review", str(paths[0]), "--review", str(paths[1]), "--release", RELEASE, "--out", str(out)]
    return tool.main(argv), out, paths


@pytest.mark.parametrize("depth", [None, 3_000, 100_000], ids=["one-past-the-limit", "past-the-interpreter-limit", "past-the-decoder-limit"])
def test_a_review_nested_too_deeply_is_a_recorded_denial_that_keeps_its_hash(tmp_path: Path, monkeypatch, depth) -> None:
    # Found by the enumeration probe for the Codex review of 6bf0a48: recursion past the interpreter's or the
    # decoder's limit crashed assess, losing the record.
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    deep = _nested(_review(run_dir, "codex"), depth or tool.MAX_REVIEW_DEPTH + 1)

    code, out, paths = _assess_files(tmp_path, run_dir, json.dumps(_review(run_dir, "claude")), deep)

    record = _denied(code, out, f"review 2 nests deeper than {tool.MAX_REVIEW_DEPTH} levels")
    assert [(r["raw_input_sha256"], r["record"]) for r in record["reviews"]] == [(_sha(paths[0]), _review(run_dir, "claude")), (_sha(paths[1]), None)]


def test_a_review_nested_exactly_to_the_limit_is_assessed(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    at_limit = _nested(_review(run_dir, "codex"), tool.MAX_REVIEW_DEPTH)

    code, out, _ = _assess_files(tmp_path, run_dir, json.dumps(_review(run_dir, "claude")), at_limit)

    assert code == 0, _json(out / "assessment.json")["reasons"]
    assert _json(out / "assessment.json")["reviews"][1]["record"] == json.loads(at_limit)


def test_the_assessment_keeps_complete_sanitized_reviews_beside_their_raw_hashes(tmp_path: Path, monkeypatch) -> None:
    final = with_case("constraints", FLAGGED, "ROUND_HALF_UP was superseded by that correction.")
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, final)
    claude, codex = _review(run_dir, "claude"), _review(run_dir, "codex")
    claude["steps"]["final"]["R"]["R6"]["summary"] = f"ROUND_HALF_EVEN is current; pasted token {SYNTHETIC_KEY} aside"
    claude["steps"]["final"]["minor"] = [{"key": "linter-paste-attribution", "note": "Claude: called user-pasted; it grants nothing"}]
    codex["steps"]["final"]["minor"] = [{"key": "linter-paste-attribution", "note": f"Codex: attribution only, {SYNTHETIC_KEY}"}]
    codex["steps"]["final"]["lexical"]["half-up-superseded"]["summary"] = "'This supersedes the earlier rule of ROUND_HALF_UP from seq 1.' states the replacement"

    code, out = _assess(tmp_path, run_dir, claude, codex)

    assert code == 0, _json(out / "assessment.json")["reasons"]
    assert SYNTHETIC_KEY not in (out / "assessment.json").read_text(encoding="utf-8")
    record = _json(out / "assessment.json")
    kept_claude, kept_codex = (r["record"] for r in record["reviews"])
    assert kept_claude["exposure"] == claude["exposure"] and kept_codex["exposure"] == codex["exposure"]
    assert kept_claude["steps"]["final"]["R"]["R6"] == {"status": "PASS", "source": "seq 1", "summary": "ROUND_HALF_EVEN is current; pasted token ********** aside"}
    assert kept_claude["steps"]["step1"]["F"] == claude["steps"]["step1"]["F"]
    assert kept_codex["steps"]["final"]["lexical"] == codex["steps"]["final"]["lexical"]
    assert kept_codex["steps"]["final"]["minor"] == [{"key": "linter-paste-attribution", "note": "Codex: attribution only, **********"}]
    assert kept_claude["steps"]["final"]["minor"] == claude["steps"]["final"]["minor"]
    # Approved identifiers and raw-input hashes stay exact; the raw hash is of the unsanitized bytes.
    assert (kept_codex["rubric_sha256"], kept_codex["steps"]["final"]["request_id"]) == (tool.ASSESSMENT_RUBRIC_SHA256, codex["steps"]["final"]["request_id"])
    assert [r["raw_input_sha256"] for r in record["reviews"]] == [_sha(tmp_path / "review-0.json"), _sha(tmp_path / "review-1.json")]
    assert record["run"]["request_ids"] == _json(run_dir / "outcome.json")["request_ids"]


def test_verified_identifiers_stay_exact_where_the_sanitizer_would_erase_them(tmp_path: Path, monkeypatch) -> None:
    """The evidence sanitizer's entropy rule erases some standalone IDs (this one deterministically). A review's
    identity field is kept exact only when it equals the run's verified identity; otherwise it stays sanitized."""
    sanitizer = tool._evidence_sanitizer()
    erased, unverified = "gw-0ad28bb5689c449caf3e780016b662dc", "gw-0ad28bb5689c449caf3e780016b662dd"  # pragma: allowlist secret - synthetic request ids
    assert sanitizer.sanitize(erased) != erased and sanitizer.sanitize(unverified) != unverified
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    evidence, problems = tool.verify_run(run_dir)
    assert problems == [] and evidence is not None
    evidence = dataclasses.replace(evidence, request_ids={"step1": erased, "final": evidence.request_ids["final"]})
    matching, other = _review(run_dir, "codex"), _review(run_dir, "codex")
    matching["steps"]["step1"]["request_id"], other["steps"]["step1"]["request_id"] = erased, unverified

    assert tool._retained(matching, evidence, sanitizer)["steps"]["step1"]["request_id"] == erased
    assert tool._retained(other, evidence, sanitizer)["steps"]["step1"]["request_id"] == sanitizer.sanitize(unverified)


class _ErasesIdentifiers:
    """A sanitizer policy stricter than today's: its entropy rule erases each of these identifier values."""

    def __init__(self, values: set[str]) -> None:
        self.values = values

    def sanitize(self, text: str) -> str:
        return "**********" if text in self.values else text


def test_every_verified_identity_is_restored_under_a_policy_that_erases_identifiers(tmp_path: Path, monkeypatch) -> None:
    run_dir = _sealed_run(tmp_path, monkeypatch, STEP1, FINAL)
    evidence, problems = tool.verify_run(run_dir)
    assert problems == [] and evidence is not None
    identities = tool._review_identities(evidence)
    review = _review(run_dir, "codex")
    mismatched = dict(review, run_id="0" * 32)
    erasing = _ErasesIdentifiers({*identities.values(), *evidence.request_ids.values(), *evidence.response_sha256.values(), "0" * 32})

    kept = tool._retained(review, evidence, erasing)

    assert {key: kept[key] for key in identities} == identities
    for step in tool.REVIEW_ITEMS:
        assert (kept["steps"][step]["request_id"], kept["steps"][step]["response_sha256"]) == (evidence.request_ids[step], evidence.response_sha256[step])
    # An identity that does not match this run is not restored: it stays as the policy left it.
    assert tool._retained(mismatched, evidence, erasing)["run_id"] == "**********"
