# Plan 9.6 Phase B evidence

**Date:** 2026-07-10  
**Checkout:** `optimus-cost-agent-wt-cursor` @ branch `agent/cursor/plan-9-6-phase-a-evidence`  
**Depends on:** [Phase A evidence](plan-9-6-phase-a-evidence.md)

## Gateway provenance (before B2)

Killed prior listener on `127.0.0.1:8765` (pid 48884) and restarted from current checkout:

```
optimus-agent: starting local gateway (pid 36952); logging to reports/local-gateway.log
gateway_pid 36952
gateway_ready True
```

## B1 — `requires_redis` (rows 1–4)

**First run:** 13 passed, 2 failed — `test_server_stream_live_redis.py` expected removed
`params.metadata.runId` from pre-#36 permission shape (test drift, not infra).

**Fix:** Align integration tests with post-#36 permission shape: read `run_id` from
`params["_meta"]["runId"]` (`shapes.py`); approve via `optionId` only (GAP1 — no metadata echo).

**Second run:** **15 passed**, exit **0** (4.11s).

```
tests/integration/agent/test_redis_live_agent.py — 6 passed
tests/integration/acp/test_bootstrap_live_redis.py — 3 passed
tests/integration/telemetry/test_redis_telemetry_live.py — 4 passed
tests/integration/acp/test_server_stream_live_redis.py — 2 passed
```

## B2 — `requires_gateway` (row 5)

**Run:** **3 passed**, exit **0** (5.86s) against gateway pid 36952.

```
test_live_gateway_minimal_response_reports_usage_fields PASSED
test_live_planning_pass_records_directive_or_unparseable_with_one_retry PASSED
test_live_agent_writes_working_calculator PASSED
```

## Code change

`tests/integration/acp/test_server_stream_live_redis.py` — post-#36 ACP conformance alignment
(required for B1 row 4 evidence on current `main`).
