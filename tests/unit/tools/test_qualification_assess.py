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
from pathlib import Path
from typing import Any

import pytest

from optimus_model_policy import test_profiles as profiles
from optimus_model_policy import validate_registry
from optimus_model_policy.registry import SUMMARY_FIXTURE_DIGEST, SUMMARY_PROMPT_DIGEST, SUMMARY_VALIDATOR, SummaryReceipt
from tests.unit.tools.test_evaluate_context_summarizer import FINAL, STEP1, padded, with_case
from tests.unit.tools.test_qualification_run import HAIKU, SummaryUpstream, _json, _lines, _run
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
    sealed = {path: _sha(path) for path in run_dir.parent.rglob("*") if path.is_file()}
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
    assert [r["reviewer"] for r in record["reviews"]] == ["claude", "codex"]
    assert [r["sha256"] for r in record["reviews"]] == [_sha(tmp_path / "review-0.json"), _sha(tmp_path / "review-1.json")]
    assert candidate["assessment_sha256"] == _sha(out / "assessment.json")
    # The sealed experiment is untouched, and no profile is qualified by the candidate.
    assert {path: _sha(path) for path in run_dir.parent.rglob("*") if path.is_file()} == sealed
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

    record = _denied(*_assess(tmp_path, run_dir, claude, _edited(codex, path, value)), reason)

    # The findings are kept: both reviews' statuses, with the failing one as recorded.
    [kept] = [r for r in record["reviews"] if r["reviewer"] == "codex"]
    assert kept["sha256"] == _sha(tmp_path / "review-1.json")


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
    assert [r["steps"]["final"]["minor"] for r in _json(out / "assessment.json")["reviews"]] == [["linter-paste-attribution"]] * 2


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
    assert _sha(broken) in [r["sha256"] for r in record["reviews"]]


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
    controls = tmp_path / "controls"
    controls.mkdir()
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
