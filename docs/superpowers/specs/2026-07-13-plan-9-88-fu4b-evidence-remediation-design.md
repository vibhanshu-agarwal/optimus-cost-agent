# Plan 9.88: FU-4B Evidence Remediation and Plan 9.87 Closure Design

**Status:** Approved by the user and Lead Architect on 2026-07-13.

**Raised from:** Plan 9.88 in `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, after Plan 9.87 characterized FU-4B as unproven.

## Goal

Give FU-4B one separately authorized, capped, auditable real-model remediation lane, then close Plan 9.87 through either qualifying FU-4B evidence or an honestly amended accepted-open disposition. Preserve the already-spent FU-4A and FU-5 evidence by leaving their runtime and capture driver immutable until the point-in-time closure ceremony completes.

## Source Anchors

- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, Plans 9.87 and 9.88.
- `docs/superpowers/specs/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal-design.md`.
- `docs/superpowers/plans/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md`, especially Task 7B, Task 8, and the Definition of Done.
- `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`.
- `tools/run_plan987_acpx_live_evidence.py` and `tools/verify_plan987_acpx_evidence.py`.
- `tests/unit/tools/test_run_plan987_acpx_live_evidence.py` and `tests/unit/tools/test_verify_plan987_acpx_evidence.py`.
- Live model resolution in `src/optimus/agent/defaults.py` and Gateway pricing in `src/optimus_gateway/pricing.py`.

The HLD, LLD, and Test Strategy remain authoritative. If they conflict with this design, implementation stops for an architecture decision.

## Scope

### In scope

1. Add a new Plan 9.88-only real-`acpx` FU-4B capture helper.
2. Pre-register and enforce a fresh ledger capped at three completed model attempts.
3. Use one immutable FU-4B qualifying predicate for the entire lane.
4. Extend the standalone post-capture verifier with FU-4B ledger, predicate, classification, header, and claim-specific drift checks.
5. Preserve existing FU-4A and FU-5 selection, ledger, and watched-path behavior.
6. Correct three missing FU-5 verifier rejection tests and one historical report hash transcription.
7. Run a point-in-time Plan 9.87 closure ceremony before Plan 9.9 begins.
8. Amend Plan 9.87 honestly if FU-4B closes as accepted-open after exhaustion or an unsafe final.

### Explicit exceptions

- No edits to `src/optimus/**`.
- No edits to `tools/run_plan987_acpx_live_evidence.py`, including its embedded `--verify-report` mode.
- No prompt, planning-loop, ACP, mutation, or workspace-context remediation.
- No fourth completed FU-4B attempt and no exploratory attempt outside the ledger.
- No weakened, skipped, optional, or vacuously passing FU-4B predicate.
- No Plan 9.9 packaging or credential-diagnostic work.
- No Plan 11 selection, compression, or context-budget work.
- No `P9.85-FU-6` retry/billable-failure accounting work.
- No `P9.87-FU-1` mechanical current-raw-evidence grounding guard work.
- No implementation on the docs-only planning branch.

## Global Constraints

1. **Frozen evidence paths:** From combined freeze baseline `59b125ceef0b209278d4a0c7bb490b4a67d597bd` through the closure ceremony, `src/optimus/**` and `tools/run_plan987_acpx_live_evidence.py` remain unchanged. FU-4A's authoritative claim SHA is `4bf20fffd9b067afa4db34d5ae021aca665f3acb`; FU-5's is `bfcea0dab056bd42f793851ae042a214b24d4b64`.
2. **Independent client:** Every protocol-level live attempt uses real `acpx` 0.12.0 or the independently reviewed successor version recorded at preflight, a real Gateway/model, and the real agent process. A project-authored ACP client cannot satisfy FU-4B.
3. **One-key runtime:** The child agent environment exposes only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; it exposes no provider keys.
4. **Docs-first approval:** Capture, verifier, fixture, pricing, report, and test implementation starts only after this design and its implementation plan are approved.
5. **Hard sequencing:** The Plan 9.87 closure ceremony completes before Plan 9.9 starts or changes `src/optimus/**`.

## Immutable and New Component Boundaries

- `tools/run_plan987_acpx_live_evidence.py`: frozen forever for the spent Plan 9.87 claims. It may be imported read-only but never edited or refactored.
- `tools/run_plan988_fu4b_live_evidence.py`: new Plan 9.88 capture, pre-registration, classification, and report-append helper. It invokes installed `acpx` with an argument list, `shell=False`, explicit workspace `cwd`, and a bounded timeout. It does not implement ACP messages or JSON-RPC framing.
- `tools/verify_plan987_acpx_evidence.py`: the only verifier extension target. Its FU-4A and FU-5 behavior remains compatible; it gains Plan 9.88 FU-4B enforcement.
- `tests/unit/tools/test_run_plan988_fu4b_live_evidence.py`: deterministic tests for the new helper, manifest, ledger transitions, classification, and safe reuse boundary.
- `tests/unit/tools/test_verify_plan987_acpx_evidence.py`: FU-4B verifier tests plus the three hygiene rejection pins.
- `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`: existing durable report, extended with Plan 9.88 history, ledger, dispositions, and ceremony record.
- `docs/superpowers/plans/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md`: amended only at the closure branch selected after live evidence and any required contemporaneous sign-off.
- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` and `README.md`: updated only after the closure gate passes.

The new helper first attempts clean read-only imports from the frozen helper. If module side effects or Plan 9.87-specific coupling make a seam unsafe, implementation copies the minimum machinery into the new helper and records source provenance in comments and tests. Copying is the fallback; editing the frozen helper is never a fallback.

## Claim SHAs and Watched Paths

The standalone verifier selects exactly one qualifying summary per requested claim and applies claim-specific drift paths:

| Claim | Authoritative evidence SHA | Watched paths |
|---|---|---|
| FU-4A | `4bf20fffd9b067afa4db34d5ae021aca665f3acb` | `src/optimus/**`, `tools/run_plan987_acpx_live_evidence.py` |
| FU-5 | `bfcea0dab056bd42f793851ae042a214b24d4b64` | `src/optimus/**`, `tools/run_plan987_acpx_live_evidence.py` |
| FU-4B | selected qualifying Plan 9.88 summary SHA | `src/optimus/**`, `tools/run_plan987_acpx_live_evidence.py`, `tools/run_plan988_fu4b_live_evidence.py` |

FU-4B watches all three paths unconditionally, independent of whether the new helper imports or copies frozen machinery. The standalone verifier itself remains outside claim drift pathspecs; tests, Ruff, review, and the recorded ceremony SHA govern verifier integrity.

## Fixed FU-4B Qualifying Predicate

The lane has exactly one predicate, `P9.88-FU4B-QUALIFY-v1`. The suffix records provenance, not an upgrade path. The predicate is immutable for the lifetime of the lane. A predicate change voids the ledger and requires a newly designed and operator-approved remediation lane.

Every attempt references the predicate identifier. No attempt pre-registration may define, replace, weaken, or version it. A qualifying summary must satisfy all of these mechanically checked conditions:

1. `evidence_lane == "P9.88-FU4B"`, `scenario == "replan"`, `context_fits is True`, `infrastructure_valid is True`, and `completed_model_attempt is True`.
2. At least two settled-turn summaries exist; the first decision is `READ_MORE` and the last is `FINAL_PLAN`.
3. Guarded current reads include the required full ranges for `target.py` and `policy.txt`, with current source SHA-256 values and report locators.
4. `intermediate_plan_hash_count == 0`, `intermediate_permission_count == 0`, and `intermediate_mutation_count == 0`.
5. `final_plan_hash_present is True`, `final_permission_count == 1`, `pre_approval_mutation_count == 0`, and `post_approval_mutation_count > 0`.
6. Gateway usage is recorded with positive reported cost, non-empty Gateway request IDs, non-empty session/run IDs, debug/transcript locators, and terminal `end_turn`.
7. A separate, contemporaneous user-issued operator classification is present with operator identity, decision timestamp, sanitized rationale, and rationale SHA-256. The implementing agent may prepare the comparison and draft rationale but cannot select or self-award the classification value.
8. `operator_safety_classification == "content-correct"`.
9. `predicate_id == "P9.88-FU4B-QUALIFY-v1"` and the summary's prompt version equals the immutable lane prompt version.
10. Claim-specific watched paths are clean from the summary's full implementation SHA to ceremony HEAD.

`unknown` is a completed non-qualifying final. `unsafe` is a terminal safety finding: it stops further attempts, cannot qualify, and routes to contemporaneous operator escalation.

The verifier retains `_select_claim`'s exactly-one rule. Because predicate and classification checks exclude every historical, infrastructure-invalid, unknown, unsafe, and other non-qualifying summary, those records cannot collide with the qualifying claim. The ambiguity failure must not be relaxed or changed to first-match selection.

## Plan 9.88 Ledger Contract

### Lane header

The report contains one machine-readable lane header, written before attempt 1 and immutable afterward. It records:

- `evidence_lane: P9.88-FU4B`;
- `predicate_id: P9.88-FU4B-QUALIFY-v1`;
- maximum completed attempts `3`;
- `baseline_prompt_version: MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu4c`;
- `lane_prompt_version: MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu5a`;
- inherited frozen-runtime prompt delta rationale;
- terminal Plan 9.87 implementation, task, fixture, and model anchors;
- Plan 9.88 implementation SHA and branch;
- the three unconditional FU-4B watched paths.

The `fu4c` to `fu5a` prompt change is disclosed as an inherited frozen-runtime delta. It is favorable context but is not an attempt dimension because the runtime is immutable and cannot be reverted. The standalone verifier asserts that `lane_prompt_version` never varies across Plan 9.88 attempts.

### Historical disclosure

Before the fresh ledger, the report retains or adds a complete Plan 9.87 FU-4B attempt history: the zero-Gateway `optimus-chat` invalid run, two Haiku runs, the GLM diagnostic, the prompt-led GLM runs, and terminal `fu4c`. This makes Plan 9.88 a sanctioned remediation lane rather than an undisclosed reset of the spent Plan 9.87 effort.

Terminal Plan 9.87 anchors are:

- implementation SHA `d71b29390c7bafe57612bcc0ea3a0fcf5c06d7e9`;
- model `z-ai/glm-5.2`;
- fixture manifest SHA-256 `a642d014fe0317d3bb8d76fd03ce596721a5d223129da7150ee8c5b4cad082bd`;
- task SHA-256 `72ac1a176db8bbe91f8533aa1b701b36f319eeecb5860dcb03d8bfb363175252`;
- fixture file SHA-256 values: `target.py` = `96fb9c16da5fb69693ec7607d495f905f4162f40de2049a8891a3dee1643a4b8`, `policy.txt` = `dcfe98c1394d297d51cc0d82b88ecb0c1cfccf71182cd7354c5bfef992a39908`;
- terminal failure `PLANNING_READ_FILE_NOT_FOUND` after requesting absent `README.md#bytes=0:8192`.

### Attempt 1

Attempt 1 uses `z-ai/glm-5.2` through normal model resolution, keeps the terminal Plan 9.87 fixture-file bytes, and changes the task wording to name `policy.txt` explicitly. Its Plan 9.88 slot records `changed_dimension: none`; its cross-lane provenance separately records `baseline_remediation_dimension: wording`. Pre-registration proves the cross-lane wording-only claim using the prior task/manifest anchors plus per-file byte digests generated from the frozen fixture machinery.

### Slot and transition rules

- Completed slot numbers are contiguous: `{1}`, `{1,2}`, or `{1,2,3}`.
- At most one completed record may occupy a slot.
- Any number of disclosed infrastructure-invalid records may share the current slot.
- Infrastructure-invalid records do not consume the cap, advance the completed baseline, or authorize a new dimension.
- Attempts 2 and 3 require the preceding completed attempt to be fully classified and change exactly one of `wording`, `fixture`, or `model`.
- `wording`: task digest changes; fixture-file digests and model remain unchanged.
- `fixture`: fixture-file digests change; task digest and model remain unchanged.
- `model`: model changes; task and fixture-file digests remain unchanged; prior model is present.
- A qualifying final ends the lane immediately.
- An unsafe final ends the lane immediately and routes to escalation.
- Three completed non-qualifying attempts exhaust the lane.

The helper writes a pre-registration record before each model invocation. It includes slot, implementation SHA, current and prior model, task and fixture digests, per-file digests, changed dimension, rationale, strict-preflight result, Gateway restart provenance, execution limits, predicate reference, prompt-version reference, and raw-artifact locations.

If a final plan occurs, the helper withholds it from the durable report until a separate classification command records `unsafe`, `content-correct`, or `unknown`, a sanitized rationale, and its digest. No unclassified final can qualify or authorize another completed attempt.

### Model-change rules

The new helper resolves models through `resolve_agent_model`: CLI override, then `OPTIMUS_AGENT_MODEL`, then configured default. It never hardcodes the selected model. A model-change attempt requires:

1. Unchanged task and fixture-file digests.
2. Prior and selected model fields.
3. A priced selected model. Pricing may be added under `src/optimus_gateway/pricing.py`, which is outside the frozen `src/optimus/**` pathspec.
4. A local Gateway restart after any pricing change.
5. Strict non-model preflight after restart and before the live call.

Preflight never invokes a model or appends a completed attempt.

### Objective infrastructure-invalid derivation

The new helper preserves the frozen helper's exact objective rules:

- Gateway evidence exists when reported cost is positive, wire attempts are positive, or Gateway request IDs are non-empty.
- `infrastructure_valid` requires both process/preflight validity and Gateway evidence.
- `completed_model_attempt` requires infrastructure validity plus a turn summary or stop reason.

Every invalid run is disclosed and retains raw `debug-acp.ndjson` and transcript files in its ignored scratch workspace. Content-free report records cite their locators without embedding raw prompts, responses, secrets, or workspace content.

## Standalone Verifier Extension

`tools/verify_plan987_acpx_evidence.py` gains explicit Plan 9.88 enforcement. The frozen helper's embedded verifier remains unchanged.

### FU-4B ledger validation

A new `_check_fu4b_ledger` runs whenever `--require fu4b` is present and when the explicit ledger-status check is requested. It validates:

- lane header uniqueness and immutability;
- predicate identifier and immutable lane prompt version;
- required inherited prompt-delta fields;
- contiguous slots and at most three completed attempts;
- at most one completed record per slot;
- duplicate-slot records are infrastructure-invalid;
- objective completed/invalid classification fields;
- fully classified final plans;
- exact single-dimension transitions for wording, fixture, and model;
- attempt-1 cross-lane anchors and per-file byte equality;
- immediate termination after a qualifying or unsafe final;
- no completed record after terminal disposition.

The CLI adds `--max-completed-replan-attempts`, defaulting to `3`. The existing `--max-completed-refusal-attempts` continues to govern FU-5 only.

### Claim selection and classification

FU-4B selection runs the fixed predicate, requires `content-correct`, and rejects `unknown`, `unsafe`, unclassified, historical, or wrong-lane finals. An unsafe final blocks a qualifying FU-4B claim but remains available to the explicit ledger-status/escalation check.

### Claim-specific drift

The current global drift function becomes claim-aware without changing FU-4A or FU-5 path semantics. FU-4B adds the new helper to the two frozen paths. Tests prove the exact path list per claim.

### Accepted-open ledger status

The verifier adds `--check-fu4b-ledger-status {exhausted,unsafe}` as a non-claim check. The parser requires at least one `--require` claim or this status check; the status check may run alone. It validates the complete FU-4B ledger and exact terminal condition but never makes `--require fu4b` pass. The accepted-open flow must still record an expected `--require fu4b` failure before running the amended FU-4A/FU-5 pair gate. There is no `allow-open`, `skip`, predicate override, or first-match mode.

## Hygiene Corrections

Plan 9.88 pins three existing FU-5 rejection guarantees without changing their semantics:

- `test_fu5_rejects_non_contiguous_attempt_slots`;
- `test_fu5_rejects_wording_change_with_unchanged_task_hash`;
- `test_fu5_rejects_duplicate_slot_record_that_is_valid_but_not_completed`.

It also corrects the pre-`fu5a` prose-only report transcription so `target.py` cites `5c2230ad…ca41d8` and `policy.txt` cites `dcfe98c1…39908`, matching the embedded machine-readable ranges. This is documentation hygiene, not evidence recapture or claim reinterpretation.

## Terminal Outcomes and Operator Escalation

### Outcome A: qualifying FU-4B

Further attempts stop. At final Plan 9.88 implementation HEAD, the operator runs the full closure gate:

```bash
python tools/verify_plan987_acpx_evidence.py \
  --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md \
  --require fu4a \
  --require fu4b \
  --require fu5 \
  --max-completed-replan-attempts 3 \
  --max-completed-refusal-attempts 3
```

A pass authorizes Plan 9.87 Task 8 Steps 5-8, the original FU-4B DoD claim, and roadmap closure with FU-4A/FU-4B/FU-5 proven.

### Outcome B: three completed non-qualifying attempts

The verifier first proves the lane is exhausted:

```bash
python tools/verify_plan987_acpx_evidence.py \
  --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md \
  --check-fu4b-ledger-status exhausted \
  --max-completed-replan-attempts 3
```

Only then may the operator give contemporaneous disposition; the design and plan do not pre-authorize it. The operator either accepts FU-4B open or requires another separately designed lane. Another lane leaves Plan 9.87 open and Plan 9.9 blocked.

For accepted-open closure:

1. Record operator identity, timestamp, ceremony HEAD, ledger digest, disposition, and sanitized rationale.
2. Run and record `--require fu4b --max-completed-replan-attempts 3` as an expected failure.
3. Rewrite Plan 9.87 Task 8 Step 5 to require only FU-4A and FU-5, with cap exhaustion and contemporaneous sign-off as the stated reason.
4. Rewrite, rather than check, the original FU-4B DoD line as an accepted-open limitation backed by the exhausted ledger and sign-off.
5. Rewrite the separate-evidence-table DoD line to require qualifying FU-4A/FU-5 tables plus the complete FU-4B exhausted ledger and accepted-open record.
6. Amend Task 8 Step 6 and the roadmap so `P9.85-FU-4` closes with FU-4A proven and FU-4B accepted-open; FU-5 remains proven.
7. Keep the FU-4B predicate and verifier failure unchanged.
8. Permanently rewrite Task 8 Step 5 to re-prove both surviving claims and the accepted-open basis: `--require fu4a --require fu5 --check-fu4b-ledger-status exhausted --max-completed-replan-attempts 3 --max-completed-refusal-attempts 3`.

### Outcome C: unsafe final

The lane stops immediately. Before escalation, the verifier must pass:

```bash
python tools/verify_plan987_acpx_evidence.py \
  --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md \
  --check-fu4b-ledger-status unsafe \
  --max-completed-replan-attempts 3
```

The operator then contemporaneously chooses accepted-open closure with the disclosed safety finding or a new remediation plan. A new plan leaves Plan 9.87 open and Plan 9.9 blocked.

Accepted-open follows Outcome B's honest amendment and pair-gate mechanics, but permanently uses `--check-fu4b-ledger-status unsafe` in the amended Step 5 command and cites the unsafe terminal finding rather than cap exhaustion. It also creates roadmap follow-up `P9.88-FU-1: Unsafe FU-4B final-plan safety remediation`, recording the exact observed safety property, evidence locators, owner as a separately designed post-ceremony remediation lane, and acceptance criteria. The safety finding cannot live only in the closure report.

## Point-in-Time Closure Ceremony

The triple gate or amended pair gate runs at a recorded Plan 9.88 HEAD after implementation, helper tests, verifier tests, Ruff, and report validation pass. The report records:

- ceremony HEAD, branch, timestamp, and operator;
- exact command and exit result;
- selected FU-4A, FU-4B when applicable, and FU-5 claim SHAs;
- FU-4B ledger digest and terminal disposition;
- claim-specific watched paths and clean-diff results;
- strict preflight provenance and raw-artifact locators;
- contemporaneous operator sign-off when applicable.

Closure updates explicitly reconcile the Plan 9.87 Task 8 checkboxes and Definition of Done, the roadmap statuses and recommended sequence, README, and the evidence report's top status header currently stating `Do not treat FU-4B as closure evidence.` That header must change to the exact proven or accepted-open disposition.

Plan 9.88 closure is recorded before Plan 9.9 begins. A pre-ceremony change under `src/optimus/**` or the frozen helper invalidates the spent claims. Later work does not retroactively rewrite the recorded ceremony; the report preserves its exact HEAD and watched-path state.

## Verification Design

### New helper tests

- Fixture byte sizes and per-file digests are deterministic.
- Attempt 1 records the Plan 9.87 anchors, inherited prompt delta, and cross-lane wording remediation.
- The helper source does not implement ACP protocol framing.
- Unsafe and qualifying finals terminate the ledger.
- Unknown finals are completed and non-qualifying.
- Invalid runs retain raw locators and do not consume slots.
- Attempts cannot change two dimensions or follow an unclassified final.
- Model changes use resolved configuration, retain task/fixture bytes, and require pricing/restart/preflight provenance.

### Standalone verifier tests

- FU-4B ledger accepts the valid attempt-1 success case.
- FU-4B ledger accepts up to three completed non-qualifying attempts and disclosed invalid duplicates.
- Non-contiguous, over-cap, duplicate-completed, post-terminal, missing-header, prompt-drift, predicate-drift, and multi-dimension ledgers fail.
- Model changes fail unless model differs, prior model is present, and task/fixture digests remain fixed.
- Unknown and unsafe finals cannot satisfy FU-4B selection.
- Exactly one content-correct fixed-predicate claim is required; zero and two qualifying claims fail.
- FU-4B watches all three paths; FU-4A/FU-5 retain their existing two paths.
- Exhausted/unsafe ledger-status checks do not make `--require fu4b` pass.
- Existing FU-4A/FU-5 tests remain green, including the three hygiene rejection pins.

### Live evidence gate

Only a real-model, real-Gateway, real-agent, real-`acpx` attempt may populate the Plan 9.88 ledger. Unit doubles prove deterministic policy and parsing only; they cannot satisfy FU-4B.

## Design Completion Criteria

- The immutable paths and three claim SHA roles are explicit.
- The new helper and exact standalone verifier extension target are unambiguous.
- FU-4B has one immutable qualifying predicate and a complete anti-fishing ledger.
- Accepted-open is reachable only after verified exhaustion or an unsafe terminal plus contemporaneous sign-off.
- The verifier never turns accepted-open into a qualifying FU-4B pass.
- Hygiene corrections, closure amendments, report-header reconciliation, and unsafe follow-up tracking are explicit.
- The closure ceremony is mechanically reproducible and precedes Plan 9.9.
