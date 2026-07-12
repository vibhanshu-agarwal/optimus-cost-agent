# Plan 9.87 Live Evidence Report (acpx)

**Status:** FU-4A behavioral gate **satisfied** (`claude-haiku`). FU-4B **not satisfied** — haiku failed grammar (2 attempts); `z-ai/glm-5.2` diagnostic achieved turn-1 `READ_MORE` with guarded reads but terminated `PLANNING_MODEL_REFUSED` on turn 3 (no `FINAL_PLAN`). FU-5 not started. `--require fu4a` passes; `--require fu4b` fails. Do not treat FU-4B as closure evidence.

## Preflight Provenance (Task 6 Step 1)

| Field | Value |
|-------|-------|
| Branch | `agent/cursor/plan-9-87-model-replanning` |
| Implementation SHA (evidence pin) | `1387f17b4f7d160f6d86058ac56c886b011e54a9` |
| Live capture SHA (FU-4A retry) | `26098ba66f0e2a25ce45c93c1a615eb55dd3633b` (model-resolution fix) |
| OS | Windows-11-10.0.26200-SP0 |
| acpx version | 0.12.0 |
| optimus-agent config | `optimus-agent --check-config --strict --debug-trace` → OK |
| Model (FU-4A/FU-4B retry) | `claude-haiku` via `OPTIMUS_AGENT_MODEL` |
| Prompt version | `MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87` |
| Credential source | optimus-agent local setup (`OPTIMUS_GATEWAY_URL` + `OPTIMUS_API_KEY` via agent config; not echoed here) |
| Provider keys in operator shell | none detected |
| FU-4A fixture manifest SHA-256 | `b6d4d60dbd4866d7063d6490d1d4513609e0ac647137ccc046535f27076a9fd5` |
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

## FU-4A Retry — SATISFIED BEHAVIORAL GATE

Retry after model-resolution fix with `OPTIMUS_AGENT_MODEL=claude-haiku`. Summary rebuilt from live artifacts at evidence pin `1387f17` (debug-trace run filtering).

| Claim | Observed |
|-------|----------|
| Session ID | `session-74761046bcb9427e8968eca4b2cf0bb5` |
| Run ID | `session-74761046bcb9427e8968eca4b2cf0bb5:2` |
| Locator debug | `debug: attempt-1` → `reports/.plan987-single_pass-workspace/.optimus/debug-acp.ndjson` |
| Locator transcript | `transcript: attempt-1` → `reports/.plan987-single_pass-workspace/attempt-1-transcript.jsonl` |
| Context fits | yes |
| Settled turns | 1 |
| Wire / gateway | 1 (`gw-476928148a63439b805c6fdb2c7f6dfc`); `total_cost_usd` = 0.004737 |
| Model decision | `FINAL_PLAN` on turn 1 |
| Permission | 1 (final only) |
| Mutation | 0 pre-approval; 1 post-approval (`write_file`) |
| Terminal ACP reason | `end_turn` |

**Command:**

```bash
OPTIMUS_AGENT_MODEL=claude-haiku python tools/run_plan987_acpx_live_evidence.py --scenario single_pass --attempt 1 --approve-all --implementation-sha 26098ba66f0e2a25ce45c93c1a615eb55dd3633b
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

## Verify Report (Task 6 Step 5)

```bash
python tools/run_plan987_acpx_live_evidence.py --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md --require fu4a --require fu4b
```

**Result:** terminal blocker recorded — the verifier rejects the report's multiple `implementation_sha` values before predicate evaluation, and no qualifying FU-4B summary exists. FU-4A remains independently satisfied; FU-4B remains unproven.

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
  "implementation_sha": "1387f17b4f7d160f6d86058ac56c886b011e54a9",
  "prompt_version": "MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87",
  "model": "claude-haiku",
  "fixture_manifest_sha256": "b6d4d60dbd4866d7063d6490d1d4513609e0ac647137ccc046535f27076a9fd5",
  "task_sha256": "fa5a9ae415e3515bb43209adda3cdce4df46efb29d5396dbef65a66ff4cc656b",
  "session_id": "session-74761046bcb9427e8968eca4b2cf0bb5",
  "run_id": "session-74761046bcb9427e8968eca4b2cf0bb5:2",
  "debug_trace_locator": "debug: attempt-1",
  "transcript_locator": "transcript: attempt-1",
  "context_fits": true,
  "stop_reason": "end_turn",
  "settled_turns": 1,
  "wire_attempts": 1,
  "gateway_request_ids": [
    "gw-476928148a63439b805c6fdb2c7f6dfc"
  ],
  "total_cost_usd": 0.004737,
  "usage_recorded": true,
  "turn_summaries": [
    {
      "settled_turn": 1,
      "model_decision": "FINAL_PLAN",
      "gateway_request_ids": [
        "gw-476928148a63439b805c6fdb2c7f6dfc"
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

## replan attempt 1
Locator debug: debug: attempt-1
Locator transcript: transcript: attempt-1
- scenario=replan
- attempt=1
- debug_trace=debug-acp.ndjson
- note=latest post-fu4b attempt (retry 2 of 2); pre-fu4b GLM diagnostic and post-fix attempt 1 retained in prose only
```json
{
  "schema_version": "plan-9-87-evidence-summary-v1",
  "scenario": "replan",
  "attempt": 1,
  "implementation_sha": "df47d3d02a83edbabc289b8a07138d3b6b455d61",
  "prompt_version": "MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu4b",
  "model": "z-ai/glm-5.2",
  "fixture_manifest_sha256": "24ca2920e1069ca36c3075aaba2f1a2d5f0600c24131fdc994192f6e933317a4",
  "task_sha256": "72ac1a176db8bbe91f8533aa1b701b36f319eeecb5860dcb03d8bfb363175252",
  "session_id": "session-9bfc0d16432c45cd80dad321241de25c",
  "run_id": "session-9bfc0d16432c45cd80dad321241de25c:2",
  "debug_trace_locator": "debug: attempt-1",
  "transcript_locator": "transcript: attempt-1",
  "context_fits": true,
  "stop_reason": "PLANNING_READ_FILE_NOT_FOUND",
  "settled_turns": 1,
  "wire_attempts": 1,
  "gateway_request_ids": [
    "gw-810233c4cf134bf692cb1b0340316c32"
  ],
  "total_cost_usd": 0.0008538,
  "usage_recorded": true,
  "turn_summaries": [
    {
      "settled_turn": 2,
      "model_decision": "FINAL_PLAN",
      "gateway_request_ids": [
        "gw-810233c4cf134bf692cb1b0340316c32"
      ],
      "current_read_ranges": [],
      "plan_hash_present": false,
      "permission_count": 0,
      "mutation_count": 0
    }
  ],
  "intermediate_plan_hash_count": 0,
  "final_plan_hash_present": false,
  "intermediate_permission_count": 0,
  "final_permission_count": 0,
  "intermediate_mutation_count": 0,
  "pre_approval_mutation_count": 0,
  "post_approval_mutation_count": 0,
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

## replan attempt 1
Locator debug: debug: attempt-1
Locator transcript: transcript: attempt-1
- scenario=replan
- attempt=1
- debug_trace=debug-acp.ndjson
```json
{
  "schema_version": "plan-9-87-evidence-summary-v1",
  "scenario": "replan",
  "attempt": 1,
  "implementation_sha": "34411ed5ac08da7a2826d7d2d72c7eacf05080a9",
  "prompt_version": "MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu4b",
  "model": "z-ai/glm-5.2",
  "fixture_manifest_sha256": "24ca2920e1069ca36c3075aaba2f1a2d5f0600c24131fdc994192f6e933317a4",
  "task_sha256": "72ac1a176db8bbe91f8533aa1b701b36f319eeecb5860dcb03d8bfb363175252",
  "session_id": "session-3ee5e8dc7b4348508a8ee6fec54b61bd",
  "run_id": "session-3ee5e8dc7b4348508a8ee6fec54b61bd:2",
  "debug_trace_locator": "debug: attempt-1",
  "transcript_locator": "transcript: attempt-1",
  "context_fits": true,
  "stop_reason": "PLANNING_REPEATED_READ_REQUEST",
  "settled_turns": 2,
  "wire_attempts": 2,
  "gateway_request_ids": [
    "gw-6d3662ef13aa47269ad207e37bc43d41"
  ],
  "total_cost_usd": 0.00324936,
  "usage_recorded": true,
  "turn_summaries": [
    {
      "settled_turn": 1,
      "model_decision": "READ_MORE",
      "gateway_request_ids": [
        "gw-6d3662ef13aa47269ad207e37bc43d41"
      ],
      "current_read_ranges": [
        {
          "path": "policy.txt",
          "start_byte": 0,
          "end_byte": 4096,
          "source_sha256": "6577dc3c894810f19c221a28bc64e8df87495c3ace54c4d480f3a6099c310b27"
        },
        {
          "path": "target.py",
          "start_byte": 0,
          "end_byte": 4096,
          "source_sha256": "dcfe98c1394d297d51cc0d82b88ecb0c1cfccf71182cd7354c5bfef992a39908"
        }
      ],
      "plan_hash_present": false,
      "permission_count": 0,
      "mutation_count": 0
    },
    {
      "settled_turn": 3,
      "model_decision": "READ_MORE",
      "gateway_request_ids": [
        "gw-6d3662ef13aa47269ad207e37bc43d41"
      ],
      "current_read_ranges": [],
      "plan_hash_present": false,
      "permission_count": 0,
      "mutation_count": 0
    }
  ],
  "intermediate_plan_hash_count": 0,
  "final_plan_hash_present": false,
  "intermediate_permission_count": 0,
  "final_permission_count": 0,
  "intermediate_mutation_count": 0,
  "pre_approval_mutation_count": 0,
  "post_approval_mutation_count": 0,
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

## replan attempt 1
Locator debug: debug: attempt-1
Locator transcript: transcript: attempt-1
- scenario=replan
- attempt=1
- debug_trace=debug-acp.ndjson
```json
{
  "schema_version": "plan-9-87-evidence-summary-v1",
  "scenario": "replan",
  "attempt": 1,
  "implementation_sha": "d71b29390c7bafe57612bcc0ea3a0fcf5c06d7e9",
  "prompt_version": "MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu4c",
  "model": "z-ai/glm-5.2",
  "fixture_manifest_sha256": "3ba5a8c4fd379167974b5b5a8752901ba4fe149e3617dfe7093c197c25e4a46d",
  "task_sha256": "72ac1a176db8bbe91f8533aa1b701b36f319eeecb5860dcb03d8bfb363175252",
  "session_id": "session-b5581cd55286457e96ebe81689f9be3d",
  "run_id": "session-b5581cd55286457e96ebe81689f9be3d:2",
  "debug_trace_locator": "debug: attempt-1",
  "transcript_locator": "transcript: attempt-1",
  "context_fits": true,
  "stop_reason": "PLANNING_READ_FILE_NOT_FOUND",
  "settled_turns": 1,
  "wire_attempts": 1,
  "gateway_request_ids": [
    "gw-8bf0549b6e804b8d9dbe0824783294a2"
  ],
  "total_cost_usd": 0.00150552,
  "usage_recorded": true,
  "turn_summaries": [
    {
      "settled_turn": 2,
      "model_decision": "PLANNING_READ_FILE_NOT_FOUND",
      "gateway_request_ids": [
        "gw-8bf0549b6e804b8d9dbe0824783294a2"
      ],
      "current_read_ranges": [],
      "plan_hash_present": false,
      "permission_count": 0,
      "mutation_count": 0
    }
  ],
  "intermediate_plan_hash_count": 0,
  "final_plan_hash_present": false,
  "intermediate_permission_count": 0,
  "final_permission_count": 0,
  "intermediate_mutation_count": 0,
  "pre_approval_mutation_count": 0,
  "post_approval_mutation_count": 0,
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
