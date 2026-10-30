# Plan 12.5 memory evaluation: Checkpoint 1 report

Plan 12.5 (M0a-2, [#389](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/389)) delivers an offline memory evaluation contract: case and trace records, a seed set, a grader and a pinned generic-harness choice. Nothing here ran a model, a service or a real memory store.

The full record, with hashes, is [`qualification.json`](qualification.json). The other records in this folder:
- [`manifest.json`](manifest.json): source, split and custody;
- [`case-review.json`](case-review.json): drafting, verification, corrections and pre-registration;
- [`harness-choice.json`](harness-choice.json): the harness pin and its runtime obligations.

## Delivered

- **Records and grader** in `tools/plan12_memory/`. The grader scores four layers: authority, retrieval, answer and cost. Each layer is PASS, FAIL, INCONCLUSIVE or UNRUN. A missing trace is UNRUN, and incomplete evidence is INCONCLUSIVE; neither is ever PASS.
- **88 seed cases** in `tests/fixtures/plan12_memory/`:
  - 68 lifecycle cases across 24 families;
  - 12 chronological localization cases;
  - 8 accounting cases.

  They are split train 40, development 18 and held out 30.
- **Harness pin:** mini-SWE-agent at one exact commit, plus a narrow adapter to the Optimus Gateway chat route.

## Review and approval

- **Fable** reviewed first, then **Codex CLI** in six rounds. The code and fixtures were approved in round 5, and this closure record in round 6. Every review is on #389 with its hash.
- **The operator approved** the sampled review of the 30 held-out cases under Q29, with no corrections.
- **Revert checks:** every rule mutant was killed (35 + 21 + 17).

## Verification

- **The single full run on d8fef6c failed.** It had 10559 passed, 2 failed and 36 errors.
  - The required coverage floors passed, and Ruff passed.
  - The coverage validity check failed because the suite exited 1.
- **Two causes:**
  - **A missing reviewed rationale** for the grader's fixture-directory scan. It was added in 2ba2f0b.
  - **A broken local pre-commit hook cache.** It was reprovisioned outside the repository.
- **A focused run passed after the fix.** It ran on d8fef6c with that one-line delta, which was committed unchanged as 2ba2f0b. All 173 tests passed, including all 38 that had failed or errored.
- **The failed full run is not a passing gate.** The pull request's CI is the second full run.

## Not run

- Runtime K1–K6 on any real memory, ledger, index or service.
- The harness runtime obligations R1–R10.
- Model compatibility.
- Benchmark quality, statistical acceptance and performance.

These belong to M0b, M1/M3 and the #248 campaign. The exceptions are as listed in the plan.
