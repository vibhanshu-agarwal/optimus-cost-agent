# Plan 9.87 Live Evidence Report (acpx)

**Status:** FU-4A and FU-4B live capture attempted; **behavioral gates not satisfied** (2026-07-12). `--verify-report --require fu4a --require fu4b` fails at `usage_recorded must be true`. Do not treat this report as closure evidence until qualifying runs are captured.

## Preflight Provenance (Task 6 Step 1)

| Field | Value |
|-------|-------|
| Branch | `agent/cursor/plan-9-87-model-replanning` |
| Implementation SHA | `d0b3572e9caed18a884992ab485bd3bfb8f804c0` |
| OS | Windows-11-10.0.26200-SP0 |
| acpx version | 0.12.0 |
| optimus-agent config | `optimus-agent --check-config --strict --debug-trace` → OK |
| Model (pinned in helper wrapper) | `optimus-chat` |
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

## FU-4A Live Outcome (Task 6 Steps 2–3) — FAILED BEHAVIORAL GATE

| Claim | Observed |
|-------|----------|
| Session ID | `session-dabd9e827df54bd9af1fbafa9e898274` |
| Run ID | `session-dabd9e827df54bd9af1fbafa9e898274:2` |
| Locator debug | `debug: attempt-1` → `reports/.plan987-single_pass-workspace/.optimus/debug-acp.ndjson` |
| Locator transcript | `transcript: attempt-1` → `reports/.plan987-single_pass-workspace/attempt-1-transcript.jsonl` |
| Context fits | yes (`blocking_stop_reason` null; 2536 / 16384 bytes) |
| Settled turns | 2 (loop stopped on turn 2) |
| Wire / gateway | **0** gateway request IDs; `reported_aggregate_cost_usd` = 0 |
| Planning stop | `PLANNING_REPEATED_READ_REQUEST` |
| Permission | 0 |
| Mutation | 0 pre- and post-approval |
| Terminal ACP reason | `end_turn` |
| Required one-turn FINAL_PLAN | **not observed** |

**Command:**

```bash
python tools/run_plan987_acpx_live_evidence.py --scenario single_pass --attempt 1 --approve-all --implementation-sha d0b3572e9caed18a884992ab485bd3bfb8f804c0
```

Per plan Step 3: recorded as a failed behavioral gate. Fake-Gateway unit/integration tests do not substitute. A material prompt/fixture/model change requires design review and prompt-version bump before re-attempt.

## FU-4B Live Outcome (Task 6 Step 4) — FAILED BEHAVIORAL GATE

| Claim | Observed |
|-------|----------|
| Session ID | `session-a3e9cd3f426945918b23fa1c7355f98a` |
| Run ID | `session-a3e9cd3f426945918b23fa1c7355f98a:2` |
| Locator debug | `debug: attempt-1` → `reports/.plan987-replan-workspace/.optimus/debug-acp.ndjson` |
| Locator transcript | `transcript: attempt-1` → `reports/.plan987-replan-workspace/attempt-1-transcript.jsonl` |
| Context fits | yes (`blocking_stop_reason` null; 9680 / 16384 bytes) |
| READ_MORE then FINAL_PLAN | **not observed** — same `PLANNING_REPEATED_READ_REQUEST` on turn 2 |
| Wire / gateway | **0** gateway request IDs; zero reported cost |
| Permission / mutation | 0 |
| Terminal ACP reason | `end_turn` |

**Command:**

```bash
python tools/run_plan987_acpx_live_evidence.py --scenario replan --attempt 1 --approve-all --implementation-sha-from-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
```

## Verify Report (Task 6 Step 5)

```bash
python tools/run_plan987_acpx_live_evidence.py --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md --require fu4a --require fu4b
```

**Result:** FAIL — `usage_recorded must be true` (both summaries show `total_cost_usd: 0.0`, no gateway wire attempts).

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
  "implementation_sha": "d0b3572e9caed18a884992ab485bd3bfb8f804c0",
  "prompt_version": "MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87",
  "model": "optimus-chat",
  "fixture_manifest_sha256": "b6d4d60dbd4866d7063d6490d1d4513609e0ac647137ccc046535f27076a9fd5",
  "task_sha256": "fa5a9ae415e3515bb43209adda3cdce4df46efb29d5396dbef65a66ff4cc656b",
  "session_id": "session-dabd9e827df54bd9af1fbafa9e898274",
  "run_id": "session-dabd9e827df54bd9af1fbafa9e898274:2",
  "debug_trace_locator": "debug: attempt-1",
  "transcript_locator": "transcript: attempt-1",
  "context_fits": true,
  "stop_reason": "PLANNING_REPEATED_READ_REQUEST",
  "settled_turns": 1,
  "wire_attempts": 0,
  "gateway_request_ids": [],
  "total_cost_usd": 0.0,
  "usage_recorded": false,
  "turn_summaries": [
    {
      "settled_turn": 2,
      "model_decision": "READ_MORE",
      "gateway_request_ids": [],
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
  "implementation_sha": "d0b3572e9caed18a884992ab485bd3bfb8f804c0",
  "prompt_version": "MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87",
  "model": "optimus-chat",
  "fixture_manifest_sha256": "a642d014fe0317d3bb8d76fd03ce596721a5d223129da7150ee8c5b4cad082bd",
  "task_sha256": "72ac1a176db8bbe91f8533aa1b701b36f319eeecb5860dcb03d8bfb363175252",
  "session_id": "session-a3e9cd3f426945918b23fa1c7355f98a",
  "run_id": "session-a3e9cd3f426945918b23fa1c7355f98a:2",
  "debug_trace_locator": "debug: attempt-1",
  "transcript_locator": "transcript: attempt-1",
  "context_fits": true,
  "stop_reason": "PLANNING_REPEATED_READ_REQUEST",
  "settled_turns": 1,
  "wire_attempts": 0,
  "gateway_request_ids": [],
  "total_cost_usd": 0.0,
  "usage_recorded": false,
  "turn_summaries": [
    {
      "settled_turn": 2,
      "model_decision": "READ_MORE",
      "gateway_request_ids": [],
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
