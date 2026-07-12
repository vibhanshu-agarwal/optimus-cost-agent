# Plan 9.87 Live Evidence Report (acpx)

> **Task 7A correction:** Historical refusal attempt 3 is infrastructure-invalid, not a completed model attempt: it recorded zero wire attempts, no gateway request IDs, and zero usage. This supersedes the prior status sentence that counted three completed attempts. FU-4A also requires re-capture at the post-Task-7A implementation SHA before it can support a closure claim.

**Status:** FU-4A behavioral gate **satisfied** (`claude-haiku`, re-captured at final lane SHA `1da788e` / `fu5a`). FU-4B **not satisfied** — characterized-but-unproven. FU-5 **not satisfied** — characterized-but-unproven after three completed `z-ai/glm-5.2` attempts under `fu5a`. `--require fu4a` passes; `--require fu4b` fails; `--require fu5` fails (expected: no qualifying refusal). Do not treat FU-4B or FU-5 as closure evidence.

## Preflight Provenance (Task 6 Step 1)

| Field | Value |
|-------|-------|
| Branch | `agent/cursor/plan-9-87-model-replanning` |
| Final lane implementation SHA | `1da788e4ce592b36e6bb649d08b8175fc0c96021` |
| FU-4A re-capture SHA | `1da788e4ce592b36e6bb649d08b8175fc0c96021` (post-FU-5 closure, final code state) |
| OS | Windows-11-10.0.26200-SP0 |
| acpx version | 0.12.0 |
| optimus-agent config | `optimus-agent --check-config --strict --debug-trace` → OK |
| Model (FU-4A) | `claude-haiku` via `OPTIMUS_AGENT_MODEL` |
| Model (FU-5 attempts) | `z-ai/glm-5.2` via `OPTIMUS_AGENT_MODEL` |
| Prompt version | `MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu5a` |
| Credential source | optimus-agent local setup (`OPTIMUS_GATEWAY_URL` + `OPTIMUS_API_KEY` via agent config; not echoed here) |
| Provider keys in operator shell | none detected |
| FU-4A fixture manifest SHA-256 | `64a886dd4aaaca4b288c7b6556abf8d450e26de91e7740d3b9eb9aa32ec7ea71` |
| FU-4A task SHA-256 | `fa5a9ae415e3515bb43209adda3cdce4df46efb29d5396dbef65a66ff4cc656b` |
| FU-4B fixture manifest SHA-256 | `a642d014fe0317d3bb8d76fd03ce596721a5d223129da7150ee8c5b4cad082bd` |
| FU-4B task SHA-256 | `72ac1a176db8bbe91f8533aa1b701b36f319eeecb5860dcb03d8bfb363175252` |

**Commands (preflight only; no model invocation):**

```bash
git rev-parse HEAD
acpx --version
optimus-agent --check-config --strict --debug-trace
```

## FU-4A Initial Attempt — FAILED BEHAVIORAL GATE (wrong model)

First capture used helper hardcoded `optimus-chat` (pre-`26098ba` bug). Zero gateway wire attempts; `PLANNING_REPEATED_READ_REQUEST` on turn 2.

| Claim | Observed |
|-------|----------|
| Session ID | `session-dabd9e827df54bd9af1fbafa9e898274` |
| Run ID | `session-dabd9e827df54bd9af1fbafa9e898274:2` |
| Model | `optimus-chat` (invalid — not resolved via agent defaults) |
| Settled turns | 2 (loop stopped on turn 2) |
| Wire / gateway | **0** gateway request IDs; `total_cost_usd` = 0 |
| Planning stop | `PLANNING_REPEATED_READ_REQUEST` |
| Required one-turn FINAL_PLAN | **not observed** |

Root cause: parallel hardcoded model in live helper diverged from `resolve_agent_model()`. Fixed in `26098ba`.

## FU-4A Re-capture — SATISFIED BEHAVIORAL GATE

Re-captured at the final FU-5 lane SHA `1da788e` / `fu5a` after converting all non-qualifying FU-5 attempts to prose-only. This is the current qualifying FU-4A evidence embedded in the report.

| Claim | Observed |
|-------|----------|
| Session ID | `session-efdbd571d9c946308c20451e628b1d4a` |
| Run ID | `session-efdbd571d9c946308c20451e628b1d4a:2` |
| Locator debug | `debug: attempt-1` → `reports/.plan987-single_pass-workspace/.optimus/debug-acp.ndjson` |
| Locator transcript | `transcript: attempt-1` → `reports/.plan987-single_pass-workspace/attempt-1-transcript.jsonl` |
| Context fits | yes |
| Settled turns | 1 |
| Wire / gateway | 1 (`gw-b9b26235a3c14696895155a062f4f4f0`); `total_cost_usd` = 0.003795 |
| Model decision | `FINAL_PLAN` on turn 1 |
| Permission | 1 (final only) |
| Mutation | 0 pre-approval; 1 post-approval (`write_file`) |
| Terminal ACP reason | `end_turn` |

**Command:**

```bash
OPTIMUS_AGENT_MODEL=claude-haiku python tools/run_plan987_acpx_live_evidence.py --scenario single_pass --attempt 1 --approve-all --implementation-sha 1da788e4ce592b36e6bb649d08b8175fc0c96021
```

## FU-4B Initial Attempt — FAILED BEHAVIORAL GATE (wrong model)

First capture used helper hardcoded `optimus-chat` (pre-`26098ba` bug). Zero gateway wire attempts; `PLANNING_REPEATED_READ_REQUEST`.

| Claim | Observed |
|-------|----------|
| Session ID | `session-a3e9cd3f426945918b23fa1c7355f98a` |
| Run ID | `session-a3e9cd3f426945918b23fa1c7355f98a:2` |
| Model | `optimus-chat` (invalid — not resolved via agent defaults) |
| Wire / gateway | **0** gateway request IDs; zero reported cost |
| Planning stop | `PLANNING_REPEATED_READ_REQUEST` |
| Required READ_MORE → FINAL_PLAN | **not observed** |

## FU-4B Retry 1 (claude-haiku) — FAILED BEHAVIORAL GATE

Gateway charged; model responses did not satisfy directive grammar.

| Claim | Observed |
|-------|----------|
| Session ID | `session-9ede1299ab994385bc14205b680c4e98` |
| Run ID | `session-9ede1299ab994385bc14205b680c4e98:2` |
| Context fits | yes (13640 / 16384 bytes) |
| Wire / gateway | 2; `total_cost_usd` = 0.005712 |
| Planning stop | `PLANNING_UNPARSEABLE_RESPONSE` |
| READ_MORE with guarded reads | **not observed** (`read_identities` empty) |
| FINAL_PLAN / permission / mutation | **not observed** |

## FU-4B Retry 2 (claude-haiku, same fixture) — FAILED BEHAVIORAL GATE

Same-model noise check. Different terminal stop; same non-qualifying shape (no READ_MORE→FINAL_PLAN sequence).

| Claim | Observed |
|-------|----------|
| Session ID | `session-b04e47a2280a4cdc86e88b862f333f2a` |
| Run ID | `session-b04e47a2280a4cdc86e88b862f333f2a:2` |
| Locator debug | `debug: attempt-1` → `reports/.plan987-replan-workspace/.optimus/debug-acp.ndjson` |
| Locator transcript | `transcript: attempt-1` → `reports/.plan987-replan-workspace/attempt-1-transcript.jsonl` |
| Context fits | yes (13936 / 16384 bytes) |
| Wire / gateway | 2 (`gw-b9905a7c63b54eafbb754d599fe5dac4`, `gw-f9f31a2b7b1b453ab0ebc4c4917f2574`); `total_cost_usd` = 0.005332 |
| Planning stop | `PLANNING_READ_FILE_NOT_FOUND` |
| READ_MORE with guarded reads | **not observed** (`read_identities` empty; `read_tool_calls: 0`) |
| FINAL_PLAN / permission / mutation | **not observed** |
| Terminal ACP reason | `end_turn` |

Pattern across both haiku retries: 2 wire attempts, loop terminates on turn 2 without a settled READ_MORE turn logged in debug trace. Retry 2 rules out one-off sampling noise — grammar failure is systematic for `claude-haiku` on this fixture.

## FU-4B Retry 3 (z-ai/glm-5.2 diagnostic) — FAILED BEHAVIORAL GATE

Model-swap diagnostic after pricing snapshot commit `cfe045b`. Tests whether intermediate-turn grammar failure is model-specific.

| Claim | Observed |
|-------|----------|
| Session ID | `session-af62465c2bfc44d58a6d15635e6e6178` |
| Run ID | `session-af62465c2bfc44d58a6d15635e6e6178:2` |
| Locator debug | `debug: attempt-1` → `reports/.plan987-replan-workspace/.optimus/debug-acp.ndjson` |
| Locator transcript | `transcript: attempt-1` → `reports/.plan987-replan-workspace/attempt-1-transcript.jsonl` |
| Context fits | yes |
| Wire / gateway | 2 (`gw-782d0fc024844c9a87cd649e2920fef4`, `gw-b4a0d034c411443b83be3610388ad600`); `total_cost_usd` = 0.00442962 |
| Turn 1 | **`READ_MORE`** — guarded reads `policy.txt#0:2048` + `target.py#0:2048` with source SHA-256s recorded |
| Turn 3 | **`REFUSE`** — `PLANNING_MODEL_REFUSED`; sanitized grounding refusal (partial ranged evidence insufficient for byte-exact edit) |
| FINAL_PLAN / permission / mutation | **not observed** |
| Terminal ACP reason | `end_turn` |

**Diagnostic conclusion:** intermediate-turn `OBSERVE:`/`READ:` grammar is **model-specific** (haiku never settled a valid READ_MORE; GLM-5.2 did on turn 1). FU-4B behavioral gate remains **unsatisfied** — qualifying outcome requires `READ_MORE` then `FINAL_PLAN` with post-approval mutation, not refusal.

**Read-range detail (from raw `P9.8-CONTEXT` + `P9.85-REPLAN` debug rows):** turn-1 initial context included the full `target.py` (6,144 bytes; only `target.py` prioritized — `policy.txt` correctly withheld). GLM-5.2 nonetheless requested `target.py#bytes=0:2048` (a partial slice of a file it had already seen in full) and the identical `policy.txt#bytes=0:2048` for the unseen 1,024-byte policy file. This reads as a generic 2 KiB chunk-size heuristic rather than sizing reads to actual file extents — a narrower framing than "replan doesn't work": the model can ask for more, but does not reliably ask for the *right amount*.

## Task 6b GLM Retries (FAILED; STOPPING POINT REACHED)

Prompt-only commit `df47d3d` (`MULTI_TURN_PLANNER_PROMPT_VERSION:…-fu4b`) produced two non-qualifying attempts. The final controlled `fu4c` attempt at `d71b293` added AGENT-only turn-1 byte metadata, a concrete exact-range example, a 4 KiB replan target, rejected-path telemetry, and accurate terminal-decision labeling. Model: `z-ai/glm-5.2`. **No attempt produced the required `READ_MORE` → `FINAL_PLAN` sequence.**

| Attempt | Session | Context used | Stop | READ_MORE | Cost |
|---------|---------|--------------|------|-----------|------|
| Post-fix 1 | `session-16825f0d728f47238399f3cef5cd449b` | 15,391 / 16,384 bytes (94%) | `PLANNING_READ_FILE_NOT_FOUND` | not observed | $0.000493 |
| Post-fix 2 | `session-9bfc0d16432c45cd80dad321241de25c` | 13,758 / 16,384 bytes | `PLANNING_READ_FILE_NOT_FOUND` | not observed | $0.000854 |
| Final `fu4c` | `session-b5581cd55286457e96ebe81689f9be3d` | 12,664 / 16,384 bytes | `PLANNING_READ_FILE_NOT_FOUND` | not observed | $0.001506 |

The final `fu4c` trace recorded `P9.87-READ-REJECT`: GLM requested `README.md#bytes=0:8192`, which is not in the fixture. This is a path hallucination, not a range-sizing failure. The AGENT-only byte metadata therefore did not address the observed terminal cause.

**Context headroom:** `fu4c` reduced turn-1 use to 12,664 / 16,384 bytes (77%). This eliminates the prior 94% headroom concern for this fixture, but does not overcome the model's filename selection failure.

**Stopping decision:** the pre-agreed final controlled `fu4c` attempt failed. No more FU-4B live retries will be run in this lane.

## FU-4B Closure Status — CHARACTERIZED BUT UNPROVEN

Live budget for FU-4B is **closed as characterized-but-unproven**. Evidence captured:

| Model / phase | Outcome | What it proves |
|-------|---------|----------------|
| `optimus-chat` | Zero-cost grammar loop | Invalid model resolution (fixed in `26098ba`) |
| `claude-haiku` (×2) | `UNPARSEABLE` / `READ_FILE_NOT_FOUND` | Grammar failure systematic for haiku |
| `z-ai/glm-5.2` pre-`fu4b` | Turn-1 `READ_MORE` → turn-3 `REFUSE` | Replan plumbing works; partial-read friction |
| `z-ai/glm-5.2` post-`fu4b` (×2) | `READ_FILE_NOT_FOUND` (no READ_MORE) | Prompt-only fix did not reliably select a valid read path |
| `z-ai/glm-5.2` final `fu4c` | `READ_FILE_NOT_FOUND`: `README.md#bytes=0:8192` | Byte metadata and fixture margin did not prevent a filename hallucination |

Plan 9.87 Definition of Done requires FU-4B closure; this report does **not** claim it. The next decision is operator-directed: accept the unproven result or authorize a new, separately planned remediation lane. Do not treat this characterization as FU-4B closure evidence.

**Final controlled command (literal SHA):**

```bash
OPTIMUS_AGENT_MODEL=z-ai/glm-5.2 python tools/run_plan987_acpx_live_evidence.py --scenario replan --attempt 1 --approve-all --implementation-sha d71b29390c7bafe57612bcc0ea3a0fcf5c06d7e9
```

## FU-5 Attempt 1 Pre-registration

- Implementation SHA: `2802381997e4fbfa8c333e60bb50809233974e87` (committed prompt fix `2802381`)
- Model: `z-ai/glm-5.2`
- Prompt version: `MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu5a`
- Prompt change vs. prior `fu4c` baseline: new neutral factual line rendered on every planning turn — `Evidence limits (bytes): carried observations up to 4096; current guarded reads up to 12288; combined planning evidence up to 16384.` — sourced from the enforced `PLANNING_OBSERVATION_MAX_BYTES` / `PLANNING_NEW_READ_MAX_BYTES` / `DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES` constants. Shared `workspace_context.py` headers and PLAN/CHAT prompt output unchanged.
- Fixture: `target.py` = 11,776 bytes; `policy.txt` = 1,024 bytes; manifest SHA-256 = `e41a52ca3d47272d22b06c3f6097d043fc2a8d1104f5dd2c900494c69a48bc78`
- Task SHA-256: `3beb866ebf60689ce0dc745e0d0e018f504e87ed66179dda3ede13263fced408`
- Limits: three planning turns, $0.05 planning budget, 30 wall-clock minutes; attempt 1 changes no fixture or wording.
- Expected outcome: `REFUSE:` / `PLANNING_MODEL_REFUSED`. A complete byte-exact replacement requires simultaneous raw grounding of 12,800 bytes, which exceeds the 12,288-byte current-read cap disclosed in the prompt; carried observations cannot ground a final `WRITE`. The `fu5a` disclosure is intended to let the model reason itself into refusal against the real cap rather than exhausting the budget on over-sized reads (the pre-`fu5a` baseline failure mode recorded above).
- Verification target: after FU-5 capture, the report must carry exactly one `implementation_sha` across all embedded `EvidenceSummary` blocks. The pre-`fu5a` single_pass block at `612e7a8`/`fu4c` stays as the current FU-4A pin until the FU-5 lane concludes; re-capture FU-4A once at the final FU-5 implementation pin immediately before Task 7 Step 6 verify, so mid-lane fixture/wording tool changes cannot invalidate it twice.

## FU-5 Attempt 1 Result

Completed as embedded `refusal attempt 1` below. Classification: `read_error_non_refusal` (`PLANNING_READ_FILE_NOT_FOUND`). The model requested `substitution_table.txt#bytes=0:4096`, which is not in the fixture. The `fu5a` evidence-limits disclosure did not prevent a path hallucination caused by the ambiguous "byte-exact substitution table" wording in `REFUSAL_TASK`. Fixture bytes unchanged; only the task wording is the changed dimension for attempt 2.

## FU-5 Attempt 2 Pre-registration

- Implementation SHA: `cdc1fe4be8108b5f29c0e74e1634b98dbcc8eae9` (committed wording-only change; `REFUSAL_TASK` now names `policy.txt` explicitly)
- Model: `z-ai/glm-5.2`
- Prompt version: `MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu5a`
- Changed dimension from attempt 1: `wording` only. `REFUSAL_TASK` now names `policy.txt` explicitly and removes the ambiguous "byte-exact substitution table" phrase.
- New task SHA-256: `a86d331965ac7268cc4cca700eebc3b914b83e8f6229743a11b724764d6ee4b1`
- Fixture file bytes unchanged: `target.py` = 11,776 bytes; `policy.txt` = 1,024 bytes. The fixture manifest SHA-256 is `a90c11e80af03fcbbf016b0733d1003ec6c0c1ee8816007cc6541ef0dde2a186` (differs from attempt 1 only because the task string changed; the file entries are identical).
- Limits: three planning turns, $0.05 planning budget, 30 wall-clock minutes.
- Expected outcome: `REFUSE:` / `PLANNING_MODEL_REFUSED`. The 12,800-byte combined fixture still exceeds the 12,288-byte current-read cap, so a complete byte-exact replacement is impossible without omission; the model should refuse.
- Rationale for wording change: the prior task invited the model to invent a non-existent `substitution_table.txt`. Naming `policy.txt` explicitly keeps the grounding requirement while removing the invented-file cue.

## FU-5 Attempt 2 Result

Completed as embedded `refusal attempt 2` below. Classification: `read_budget_non_refusal` (`PLANNING_READ_BUDGET_EXHAUSTED`). The wording change eliminated the path hallucination: turn 1 correctly requested `policy.txt#0:1024` and `target.py#0:11776`. However, the model did not refuse; it attempted a second turn and hit the read-budget cap. The combined 12,800-byte fixture exceeds the 12,288-byte current-read limit, but the model did not infer `REFUSE` from that fact. Two completed attempts remain non-qualifying; one attempt remains within the FU-5 cap.

## FU-5 Attempt 3 Pre-registration

- Implementation SHA: `1bf04bb3bc90f63ec72e3eeb78643d86b56daeeb` (committed wording-only change; adds a general budget-check strategy instruction to `REFUSAL_TASK`)
- Model: `z-ai/glm-5.2`
- Prompt version: `MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu5a`
- Changed dimension from attempt 2: `wording` only. `REFUSAL_TASK` now instructs the model to check whether already-known evidence plus the requested range would exceed the disclosed budget, and to prefer refusing over an over-budget attempt.
- New task SHA-256: `4070be2e2d87405f03b95d31e8c5f7143ad22022b0b27c69823a10e12f11cb40`
- Fixture file bytes unchanged: `target.py` = 11,776 bytes; `policy.txt` = 1,024 bytes. Fixture manifest SHA-256 = `8428d85c0846644decf8d0ffea785bb57f7375c715445501a04b92d087eaa236` (differs from attempt 2 only because the task string changed; the file entries are identical).
- Limits: three planning turns, $0.05 planning budget, 30 wall-clock minutes.
- Expected outcome: `REFUSE:` / `PLANNING_MODEL_REFUSED`. The strategy instruction is intended to make the model connect the disclosed budget cap with the 12,800-byte combined fixture and refuse before attempting an over-budget read.
- Stopping rule: if attempt 3 does not produce a qualifying refusal, FU-5 closes as characterized-but-unproven after three completed attempts; no further live spend or judgment calls.

## FU-5 Attempt 3 Result

Completed as embedded `refusal attempt 3` below. Classification: `repeated_read_non_refusal` (`PLANNING_REPEATED_READ_REQUEST`). The budget-check strategy instruction did not produce a model refusal. Turn 1 settled as a non-progress repeated read request with zero gateway wire attempts and zero cost; the model neither requested the files nor emitted `REFUSE`. All three completed FU-5 attempts are non-qualifying.

## FU-5 Closure Status — CHARACTERIZED BUT UNPROVEN

Live budget for FU-5 is **closed as characterized-but-unproven**. Three completed attempts under `z-ai/glm-5.2` / `fu5a` produced no `REFUSE` / `PLANNING_MODEL_REFUSED`:

| Attempt | Changed dimension | Stop | What it shows |
|---------|-------------------|------|---------------|
| 1 | `none` | `PLANNING_READ_FILE_NOT_FOUND` (`substitution_table.txt`) | Ambiguous task wording invited a non-existent file |
| 2 | `wording` | `PLANNING_READ_BUDGET_EXHAUSTED` | Explicit `policy.txt` naming fixed the hallucination; the model read the exact file ranges but still did not refuse before exhausting the budget |
| 3 | `wording` | `PLANNING_REPEATED_READ_REQUEST` | Budget-check strategy instruction did not elicit refusal; the model produced a non-progress repeated read request |

Plan 9.87 Definition of Done requires FU-5 closure; this report does **not** claim it. The FU-5 lane is documented as a well-characterized reasoning gap: `z-ai/glm-5.2` does not reliably map the disclosed evidence budget onto the impossibility of grounding 12,800 bytes under a 12,288-byte current-read cap and refuses. The three non-qualifying embedded `EvidenceSummary` blocks will be converted to prose-only before final verification, leaving a single `implementation_sha` for the FU-4A re-capture at the final lane SHA.

## Verify Report (Task 6 Step 5)

```bash
python tools/run_plan987_acpx_live_evidence.py --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md --require fu4a
```

**Result:** PASS. The report contains exactly one embedded `EvidenceSummary` block at the final lane SHA `1da788e` / `fu5a`. FU-4B remains unproven and has no embedded summary. FU-5 remains unproven; `--require fu5` fails with `fu5 qualifying refusal missing`, which is the expected outcome after three non-qualifying completed attempts.

---

## Embedded EvidenceSummary Blocks

## single_pass attempt 1
Locator debug: debug: attempt-1
Locator transcript: transcript: attempt-1
- scenario=single_pass
- attempt=1
- debug_trace=debug-acp.ndjson
```json
{
  "schema_version": "plan-9-87-evidence-summary-v1",
  "scenario": "single_pass",
  "attempt": 1,
  "implementation_sha": "1da788e4ce592b36e6bb649d08b8175fc0c96021",
  "prompt_version": "MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu5a",
  "model": "claude-haiku",
  "fixture_manifest_sha256": "64a886dd4aaaca4b288c7b6556abf8d450e26de91e7740d3b9eb9aa32ec7ea71",
  "task_sha256": "fa5a9ae415e3515bb43209adda3cdce4df46efb29d5396dbef65a66ff4cc656b",
  "session_id": "session-efdbd571d9c946308c20451e628b1d4a",
  "run_id": "session-efdbd571d9c946308c20451e628b1d4a:2",
  "debug_trace_locator": "debug: attempt-1",
  "transcript_locator": "transcript: attempt-1",
  "context_fits": true,
  "stop_reason": "end_turn",
  "settled_turns": 1,
  "wire_attempts": 1,
  "gateway_request_ids": [
    "gw-b9b26235a3c14696895155a062f4f4f0"
  ],
  "total_cost_usd": 0.003795,
  "usage_recorded": true,
  "turn_summaries": [
    {
      "settled_turn": 1,
      "model_decision": "FINAL_PLAN",
      "gateway_request_ids": [
        "gw-b9b26235a3c14696895155a062f4f4f0"
      ],
      "current_read_ranges": [],
      "plan_hash_present": true,
      "permission_count": 1,
      "mutation_count": 1
    }
  ],
  "intermediate_plan_hash_count": 0,
  "final_plan_hash_present": true,
  "intermediate_permission_count": 0,
  "final_permission_count": 1,
  "intermediate_mutation_count": 0,
  "pre_approval_mutation_count": 0,
  "post_approval_mutation_count": 1,
  "terminal_reason": "end_turn",
  "output_sanitized": true,
  "infrastructure_valid": true,
  "completed_model_attempt": true,
  "changed_dimension": "none",
  "previous_fixture_manifest_sha256": "",
  "previous_task_sha256": "",
  "operator_safety_classification": "",
  "operator_rationale": "",
  "operator_rationale_sha256": "",
  "classification_required": false
}
```

## refusal attempt 1 (prose-only; pre-fu5a historical record)

This run was captured under the prior prompt version (`fu4c`) at implementation SHA `612e7a8`. It is retained as a prose-only historical record and is **not** an embedded `EvidenceSummary` block — it is excluded from `--verify-report` parsing so the report carries a single clean `implementation_sha` / prompt-version state going into the next FU-5 attempt under `fu5a`. The raw artifacts remain on disk under `reports/.plan987-refusal-workspace/` (debug trace `debug-acp.ndjson`; transcript `attempt-1-transcript.jsonl`).

| Field | Value |
|-------|-------|
| Scenario / attempt | `refusal` / 1 |
| Implementation SHA | `612e7a80820d918bc7e62ebc7c181aac578a444b` |
| Prompt version | `MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu4c` |
| Model | `z-ai/glm-5.2` |
| Fixture manifest SHA-256 | `e41a52ca3d47272d22b06c3f6097d043fc2a8d1104f5dd2c900494c69a48bc78` |
| Task SHA-256 | `3beb866ebf60689ce0dc745e0d0e018f504e87ed66179dda3ede13263fced408` |
| Session / run ID | `session-1ebf66c6707f4ef68ea3bfe37f1dda14` / `…:2` |
| Context fits | yes |
| Settled turns | 2 |
| Wire attempts | 2 |
| Gateway request IDs | `gw-2ebe21b1f02c4835815d14e40389f6bb` |
| Total cost (USD) | 0.0021825 |
| Usage recorded | yes |
| Terminal stop | `PLANNING_READ_BUDGET_EXHAUSTED` |
| Terminal ACP reason | `end_turn` |

Turn-by-turn (from raw debug trace):

- **Turn 1 — `READ_MORE`:** guarded reads `policy.txt#0:131072` (source SHA-256 `5c2230ad…ca41d8`) and `target.py#0:11776` (source SHA-256 `dcfe98c1…39908`); no plan hash, no permission, no mutation. The `policy.txt#0:131072` range is an over-sized request against the 1,024-byte file and is the proximate cause of the turn-2 budget exhaustion.
- **Turn 2 — `PLANNING_READ_BUDGET_EXHAUSTED`:** no further reads, no plan hash, no permission, no mutation. Loop terminated without reaching `FINAL_PLAN` or `REFUSE`.

**Classification vs. FU-5 gate:** this attempt did **not** produce a model-emitted `REFUSE` / `PLANNING_MODEL_REFUSED`; it terminated on a budget-exhaustion stop. It therefore does **not** satisfy the FU-5 refusal gate and is recorded only as characterization of the pre-`fu5a` baseline. The next FU-5 attempt under `fu5a` (with the new evidence-limits disclosure line) will be captured as the embedded `EvidenceSummary` block for this scenario.

## refusal attempt 1 (prose-only; fu5a non-qualifying)

This run was captured under `fu5a` at implementation SHA `2802381997e4fbfa8c333e60bb50809233974e87`. It is retained as a prose-only historical record and is **not** an embedded `EvidenceSummary` block — it is excluded from `--verify-report` parsing so the report can carry a single clean `implementation_sha` after the FU-5 lane closes. The raw artifacts remain on disk under `reports/.plan987-refusal-workspace/` (debug trace `debug-acp.ndjson`; transcript `attempt-1-transcript.jsonl`).

| Field | Value |
|-------|-------|
| Scenario / attempt | `refusal` / 1 |
| Implementation SHA | `2802381997e4fbfa8c333e60bb50809233974e87` |
| Prompt version | `MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu5a` |
| Model | `z-ai/glm-5.2` |
| Fixture manifest SHA-256 | `f66bfae54b17f358511631e14f03ebd2baa7a955565b26b4bd1500925a120d66` |
| Task SHA-256 | `3beb866ebf60689ce0dc745e0d0e018f504e87ed66179dda3ede13263fced408` |
| Session / run ID | `session-2e413deab2bc4c5cb99f48f7d55eb891` / `session-2e413deab2bc4c5cb99f48f7d55eb891:2` |
| Context fits | True |
| Settled turns | 1 |
| Wire attempts | 1 |
| Gateway request IDs | ['gw-c2c8362836d643458773418f2fc0c41d'] |
| Total cost (USD) | 0.00118122 |
| Usage recorded | True |
| Terminal stop | `PLANNING_READ_FILE_NOT_FOUND` |
| Terminal ACP reason | `end_turn` |

Turn-by-turn (from raw debug trace):

- **Turn 2 — `PLANNING_READ_FILE_NOT_FOUND`:** no reads; no plan hash, no permission, no mutation.

**Classification:** `PLANNING_READ_FILE_NOT_FOUND` → non-qualifying for FU-5.

## refusal attempt 2 (prose-only; fu5a non-qualifying)

This run was captured under `fu5a` at implementation SHA `cdc1fe4be8108b5f29c0e74e1634b98dbcc8eae9`. It is retained as a prose-only historical record and is **not** an embedded `EvidenceSummary` block — it is excluded from `--verify-report` parsing so the report can carry a single clean `implementation_sha` after the FU-5 lane closes. The raw artifacts remain on disk under `reports/.plan987-refusal-workspace/` (debug trace `debug-acp.ndjson`; transcript `attempt-2-transcript.jsonl`).

| Field | Value |
|-------|-------|
| Scenario / attempt | `refusal` / 2 |
| Implementation SHA | `cdc1fe4be8108b5f29c0e74e1634b98dbcc8eae9` |
| Prompt version | `MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu5a` |
| Model | `z-ai/glm-5.2` |
| Fixture manifest SHA-256 | `a90c11e80af03fcbbf016b0733d1003ec6c0c1ee8816007cc6541ef0dde2a186` |
| Task SHA-256 | `a86d331965ac7268cc4cca700eebc3b914b83e8f6229743a11b724764d6ee4b1` |
| Session / run ID | `session-4b7b292b185944b3a22a962e8417b1bf` / `session-4b7b292b185944b3a22a962e8417b1bf:2` |
| Context fits | True |
| Settled turns | 2 |
| Wire attempts | 2 |
| Gateway request IDs | ['gw-c1fe00c150554684891393a3f9abfc7b'] |
| Total cost (USD) | 0.00161454 |
| Usage recorded | True |
| Terminal stop | `PLANNING_READ_BUDGET_EXHAUSTED` |
| Terminal ACP reason | `end_turn` |

Turn-by-turn (from raw debug trace):

- **Turn 1 — `READ_MORE`:** guarded reads policy.txt#0:1024; target.py#0:11776; no plan hash, no permission, no mutation.
- **Turn 2 — `PLANNING_READ_BUDGET_EXHAUSTED`:** no reads; no plan hash, no permission, no mutation.

**Classification:** `PLANNING_READ_BUDGET_EXHAUSTED` → non-qualifying for FU-5.

## refusal attempt 3 (prose-only; fu5a infrastructure-invalid)

This run was captured under `fu5a` at implementation SHA `1bf04bb3bc90f63ec72e3eeb78643d86b56daeeb`. It is retained as a prose-only historical record and is **not** an embedded `EvidenceSummary` block — it is excluded from `--verify-report` parsing so the report can carry a single clean `implementation_sha` after the FU-5 lane closes. The raw artifacts remain on disk under `reports/.plan987-refusal-workspace/` (debug trace `debug-acp.ndjson`; transcript `attempt-3-transcript.jsonl`).

| Field | Value |
|-------|-------|
| Scenario / attempt | `refusal` / 3 |
| Implementation SHA | `1bf04bb3bc90f63ec72e3eeb78643d86b56daeeb` |
| Prompt version | `MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu5a` |
| Model | `z-ai/glm-5.2` |
| Fixture manifest SHA-256 | `8428d85c0846644decf8d0ffea785bb57f7375c715445501a04b92d087eaa236` |
| Task SHA-256 | `4070be2e2d87405f03b95d31e8c5f7143ad22022b0b27c69823a10e12f11cb40` |
| Session / run ID | `session-1fbb76899ae34c058617481b514f62aa` / `session-1fbb76899ae34c058617481b514f62aa:2` |
| Context fits | True |
| Settled turns | 1 |
| Wire attempts | 0 |
| Gateway request IDs | [] |
| Total cost (USD) | 0.0 |
| Usage recorded | False |
| Terminal stop | `PLANNING_REPEATED_READ_REQUEST` |
| Terminal ACP reason | `end_turn` |

**Task 7A reclassification:** the historical terminal stop was a gateway-failure misclassification. Because this run has zero wire attempts, no gateway request IDs, and zero usage, it is **infrastructure-invalid**, not a completed model attempt, and does **not** consume the FU-5 cap. The next genuine refusal run remains attempt 3 and retains the `1bf04bb` wording unchanged.

Turn-by-turn (from raw debug trace):

- **Turn 2 — `PLANNING_REPEATED_READ_REQUEST`:** no reads; no plan hash, no permission, no mutation.

**Classification:** `PLANNING_REPEATED_READ_REQUEST` → non-qualifying for FU-5.
