# Plan 9.6: Live Verification and LLD Alignment Implementation Plan

> **For agentic workers:** Plan 9.6 is the proof plan for the agent Plan 9.5 builds. Plan 9.5
> (`docs/superpowers/plans/2026-07-07-plan-9-5-working-acp-agent-completion.md`) delivers the code
> with unit/fake-tier tests; Plan 9.6 delivers the evidence that the composed deliverable works
> against real dependencies, aligns Redis usage with the HLD/LLD, and owns the Phase 1 operator
> sign-off gate. Neither plan is complete without the other, but their scopes do not overlap:
> build questions go to 9.5, proof and LLD-conformance questions go here.

**Goal:** Every dependency named by a test tier is real: a live TimeSeries-capable Redis instance
on the operator's machine, real Optimus Gateway credentials, and a real spawned ACP stdio process.
Pre-flight checks verify the environment before any live test or agent session runs and fail
closed with operator action messages. Redis usage conforms to Architecture v2.15 and LLD v2.38.

**Status:** Approved for implementation. Owns Plan 9.5/Phase 1 operator sign-off.

## Scope Transfer From Plan 9.5

Plan 9.5 is frozen at its current task list (Tasks 0-8) so in-flight implementation is not
disrupted. The following concerns are transferred to and owned by this plan:

- The live-dependency test tiers (`requires_redis`, `requires_gateway`, `e2e`) and pre-flight
  checks (Tasks L1-L8).
- Real-Gateway/real-Redis E2E evidence, the committed transcripts, and the Zed HITL artifact.
- LLD/HLD Redis alignment: TimeSeries capability, live telemetry contract tests, async pool
  migration, telemetry wiring in bootstrap (Tasks L2A, L9).
- The plan-text persistence governance decision (Task L10).
- The sign-off gate. Plan 9.5 completion now means "implementation merged with its own DoD tests
  green"; it does NOT mean the working-agent story is proven. Only this plan's sign-off gate does.

---

## Audit Findings (2026-07-07, this worktree)

Implemented by the in-flight completion-plan work:

- `src/optimus/acp/spec.py` (duplex ACP adapter), `src/optimus/agent/state_store.py`
  (in-memory + Redis store with `ping()` and `from_url`), `src/optimus/agent/prompts.py`,
  `src/optimus/agent/directives.py`, runner/tools/model updates, `redis>=5` dependency.

Not implemented yet (completion-plan Tasks 4, 5, 7, 8):

- `src/optimus/acp/bootstrap.py`, `src/optimus/acp/__main__.py`, `[project.scripts]`,
  README operator section, release-CLI wiring.

Live-verification gaps this plan closes:

- Zero registered pytest markers; `--strict-markers` is enabled, so live-tier markers must be
  registered in `pyproject.toml` before first use.
- No `tests/e2e/` directory. No test anywhere runs against a real Redis, a real Gateway, or a real
  subprocess.
- `RedisAgentStateStore` (constructed with `decode_responses=True`) has never executed a real
  Redis command. `FakeRedis` hides exactly the failure class most likely in production:
  bytes-vs-str decoding, `hset` mapping type coercion, real TTL expiry, Decimal/enum wire
  round-trips.
- `AcpDuplexAdapter`, prompt contract, and plan replay have never seen real model output or a real
  process boundary.

## HLD/LLD Alignment Findings (Architecture v2.15, LLD v2.38)

The design docs specify Redis usage precisely; the live tier must verify the documented contract,
not only the new plan store:

1. **RedisTimeSeries is required, so `redis:7-alpine` is the wrong image.** LLD §10 mandates
   `TS.CREATE key RETENTION 2592000000` with idempotent `TS.ALTER` fallback and pipelined `TS.ADD`
   for `telemetry:run:{run_id}:metrics:{cost_usd,tokens_input,tokens_output}`. Plain Redis has no
   `TS.*` commands. Operators must run `redis:8` (TimeSeries bundled) or
   `redis/redis-stack-server:latest`. Pre-flight gains a capability probe (below).
2. **Run metadata hash contract (LLD §10, §A):** `run:{run_id}:metadata` HASH carrying
   `execution_mode`, `generation_scope`, `rigor_level`, assumption-ledger fields, with
   `EXPIRE 2592000`. Implemented in `src/optimus/telemetry/redis_adapter.py` — but only ever
   exercised with fakes, and never constructed with a real client anywhere in production wiring.
3. **Async contract:** LLD §10 uses `redis.asyncio` with one **shared ConnectionPool**. The new
   `RedisAgentStateStore` is synchronous; inside the asyncio ACP server a sync Redis call blocks
   the event loop. Remediation in Task L9.
4. **LLD verification checklist items** (LLD §"Confirm RedisTimeSeries entries…") map one-to-one
   onto live tests: TS retention alignment on new and pre-existing keys, metadata hash piping on
   every workflow completion, ledger/gateway cost reconciliation. Task L2A implements them.
5. **Data governance flag (Architecture §4):** persistent stores may catalogue signatures,
   summaries, and relative paths; unparsed source code must not enter persistent vector indexes.
   The plan store persists `plan_text`, whose `WRITE` bodies contain file content. This needs an
   explicit, documented governance decision (short-TTL operational state vs. indexed store) — see
   Task L10. Do not let it pass silently.
6. **Structural memory store (Architecture §6 step [3]):** the `Local Redis State Store` of
   topology/code-signature HASHes that feeds the Context Optimization Node is documented but
   unbuilt — it is the Plan 11 state dependency ("no context management without state"). Out of
   scope here, but the pool, pre-flight, and live tier built now are its foundation and must be
   reusable by it.

## Policy: The Dependency Under Test Must Be Real

- **unit** (default tier): fakes allowed. Verifies component logic only. Existing tests unchanged.
- **requires_redis**: Redis is REAL — a live instance on the operator's machine. No Redis fake may
  appear in these files. The Gateway MAY remain a deterministic fake in this tier only because
  Redis, not the model, is the dependency under test.
- **requires_gateway**: Gateway credentials and calls are REAL. Redis is also real (it is local and
  free; nothing justifies faking it once it is running).
- **e2e**: everything real, including the OS process boundary (`python -m optimus.acp` spawned as a
  subprocess speaking ndjson over real pipes).
- A fake standing in for the dependency named by the tier is a review-rejectable defect.
- Sign-off requires all four tiers executed. Green unit tests alone can never pass QA.

## Pre-Flight Checks (first-class deliverable, not test setup)

Pre-flight runs before any live tier or agent session and fails closed:

1. `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` present — else exit 2 with
   `Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY before launching the Optimus ACP agent.`
2. `OPTIMUS_REDIS_URL` present and password-free — else exit 2 with
   `Set OPTIMUS_REDIS_URL=redis://127.0.0.1:6379/0 (start one with: docker run --rm -d -p 6379:6379 redis:8)`.
3. Redis `PING` succeeds within `socket_connect_timeout=2` — else exit 2 with
   `Redis is not reachable. Start Redis or fix OPTIMUS_REDIS_URL.`
3b. RedisTimeSeries capability probe: issue `TS.ADD` on a namespaced probe key (then delete it) or
   inspect `MODULE LIST` — else exit 2 with
   `Redis lacks TimeSeries support. Use redis:8 or redis/redis-stack-server (LLD §10 requires TS.* commands).`
4. (strict mode) Gateway auth probe: one minimal authenticated request; 401/403 → exit 2 with
   `OPTIMUS_API_KEY was rejected by the gateway.`; network failure → exit 2 naming the URL.
5. Workspace root exists, is a directory, and is writable.

Surfaces that must all share this one implementation (`src/optimus/acp/preflight.py`):

- `python -m optimus.acp --check-config` (checks 1-3, 5) and `--check-config --strict` (adds 4).
- A `live_redis_store` / `live_gateway_settings` pytest fixture pair (below).
- `tools/verify_live_agent.py` (below).
- `tools/run_phase1_release_gate.py --agent-harness`.

## Task L1: Markers, Conftest Fixtures, and Fail-Loud Policy

**Status:** Implemented (2026-07-07). `src/optimus/acp/preflight.py`, `tests/conftest.py`,
`tests/unit/acp/test_preflight.py`, and `pyproject.toml` marker registration are on disk.

**Files:** `pyproject.toml`, `tests/conftest.py`, `src/optimus/acp/preflight.py`,
`tests/unit/acp/test_preflight.py`

These files now use `tests/conftest.py` fail-loud fixtures (`pytest.fail()`, not
`skip_unless_redis()`). They are deselected by default until `pytest -m requires_redis`.

- Register markers in `[tool.pytest.ini_options]`:
  `requires_redis`, `requires_gateway`, `e2e`.
- Default run excludes live tiers:
  `addopts += ['-m', 'not requires_redis and not requires_gateway and not e2e']`.
  Live runs select explicitly, e.g. `pytest -m requires_redis`.
- `tests/conftest.py` fixtures:
  - `live_redis_store`: builds `RedisAgentStateStore.from_url(os.environ['OPTIMUS_REDIS_URL'])`,
    calls `ping()`. If the env var is missing or ping fails, the fixture calls `pytest.fail()`
    (NOT `skip`) with the pre-flight message. A selected live tier with a broken environment is a
    failure, never a silent pass or quiet skip.
  - `live_gateway_settings`: `OptimusGatewaySettings.from_env()` + strict auth probe; same
    fail-loud rule.
  - `redis_key_namespace`: unique `run_id` prefix per test (`live-{uuid4}`); teardown deletes only
    keys under that prefix. `FLUSHDB`/`FLUSHALL` are forbidden — the operator's Redis may be shared.
- Unit tests for preflight logic itself may use fakes (it is component logic).
- TDD: failing tests first, then implement, then `pytest tests/unit/acp/test_preflight.py -v`.

## Task L2: Live Redis Agent State Tests

**Status:** Implemented (2026-07-07). `tests/integration/agent/test_redis_live_agent.py` aligned to
spec (round-trip fidelity, real TTL, cross-process replay, key hygiene). Verify with
`pytest tests/integration/agent/test_redis_live_agent.py -m requires_redis -v` after setting
`OPTIMUS_REDIS_URL`, `OPTIMUS_GATEWAY_URL`, and `OPTIMUS_API_KEY` and starting `redis:8`.

**File:** `tests/integration/agent/test_redis_live_agent.py` (marker: `requires_redis`)

- Round-trip fidelity: `save_plan` then `load_plan` against real Redis returns a record equal to
  the original — Decimal cost, `ExecutionMode` wire value, `None` session_id, multi-line
  `plan_text` with embedded newlines all intact through `decode_responses=True`.
- Real TTL: save with `ttl_seconds=1`, `time.sleep(1.5)`, `load_plan` raises
  `KeyError("stored plan not found")`. Real `EXPIRE`, not a fake's bookkeeping.
- Cross-process replay (the reason Redis exists): runner A with fake gateway A plans and persists;
  a NEW `RedisAgentStateStore.from_url(...)` instance plus runner B with fake gateway B replays the
  approval — zero calls on gateway B, file mutated on disk, replayed content is plan A's.
- Key hygiene: all records under the `redis_key_namespace` prefix; teardown verified.

## Task L2A: Live Redis Telemetry Tests (LLD §10 Verification Checklist)

**Status:** Implemented (2026-07-07). `tests/integration/telemetry/test_redis_telemetry_live.py` and
`live_redis_telemetry` fixture in `tests/conftest.py`. Verify with
`pytest tests/integration/telemetry/test_redis_telemetry_live.py -m requires_redis -v` after
`redis:8` pre-flight env is set (same as L2).

**File:** `tests/integration/telemetry/test_redis_telemetry_live.py` (marker: `requires_redis`)

Implements the LLD's own verification checklist against a real TimeSeries-capable Redis, using the
existing `RedisTelemetryAdapter` with a real `redis.asyncio` client:

- `ensure_series` idempotency: first call issues `TS.CREATE` with `RETENTION 2592000000`; calling
  it again on the pre-existing key takes the `TS.ALTER` path; assert via `TS.INFO` that
  `retentionTime == 2592000000` in both the brand-new and pre-existing cases (LLD checklist item 1).
- `record_metric` writes real samples to
  `telemetry:run:{run_id}:metrics:cost_usd|tokens_input|tokens_output`; read back via `TS.RANGE`
  and assert values.
- `write_run_metadata` produces a real `run:{run_id}:metadata` HASH containing `execution_mode`,
  `generation_scope`, `rigor_level`, and assumption fields, with `TTL` set to 2592000 seconds
  (assert `TTL` is within tolerance) — LLD checklist item on metadata piping.
- All keys under the `redis_key_namespace` prefix pattern; teardown deletes them.

## Task L3: Live Redis Bootstrap Tests

**Status:** Implemented (2026-07-07). `tests/integration/acp/test_bootstrap_live_redis.py` aligned to
spec (live sentinel round-trip, unreachable port fail-fast, password URL rejection). Verify with
`pytest tests/integration/acp/test_bootstrap_live_redis.py -m requires_redis -v` after L2 env setup.

**File:** `tests/integration/acp/test_bootstrap_live_redis.py` (marker: `requires_redis`)

**Depends on completion-plan Task 4 (`bootstrap.py`) landing first.**

- `build_configured_server()` with real env vars returns a wired server; the Redis `PING` in
  bootstrap executed against the live instance (assert via a namespaced sentinel write/read).
- Unreachable Redis: point `OPTIMUS_REDIS_URL` at a closed port (`redis://127.0.0.1:6390/0`) →
  `StartupConfigurationError`, `exit_code == 2`, message contains `Redis is not reachable`.
  Implementation requirement this test forces: `from_url` must set `socket_connect_timeout=2`
  so failure is fast, not a hang.
- Password URL rejected before any connection attempt.

## Task L4: Live Redis ACP Server Stream Tests

**Status:** Implemented (2026-07-07). `tests/integration/acp/test_server_stream_live_redis.py`
covers ndjson duplex approval flow with Redis `HGETALL` persistence checks and second-server
replay. Verify with
`pytest tests/integration/acp/test_server_stream_live_redis.py -m requires_redis -v`.

**File:** `tests/integration/acp/test_server_stream_live_redis.py` (marker: `requires_redis`)

**Depends on completion-plan Tasks 4-5.**

- Full duplex ndjson session through `serve_ndjson` with the REAL Redis store (fake gateway):
  `initialize` → `session/new` → `session/prompt` → agent-initiated `session/request_permission` →
  approve → file mutated, `stopReason == "end_turn"`.
- Persistence assertions go to Redis directly: after the plan pass, `HGETALL` the expected key and
  assert `plan_text`/`plan_hash` fields; after approval, assert the gateway was called exactly once
  (replay came from Redis, not re-planning).
- Server-restart replay (mirrors IDE reconnect): tear down the first server object, build a second
  one sharing the same real Redis, deliver the approval there, assert replay succeeds with zero new
  gateway calls.

## Task L5: Live Gateway Tests

**Blocked on:** `docs/superpowers/plans/2026-07-07-local-optimus-gateway-service.md`. No Optimus
Gateway backend exists to issue real credentials against — L5's tests are implemented but were last
verified against fake gateway credentials (correct for L1-L4/L9, where Redis is the dependency under
test, but not sufficient here, where the model itself is). The local-gateway plan builds the missing
piece; re-run L5 against it once that lands before treating this task's live tier as proven.

**File:** `tests/integration/gateway/test_gateway_live.py` (marker: `requires_gateway`)

- One minimal real `GatewayClient.create_response()` call: assert non-empty `response_id`,
  `gateway_usage.cost_usd >= 0`, provider fields present. Hard cap via
  `OPTIMUS_LIVE_MAX_COST_USD` (default `0.25`); exceeding it fails the test.
- Real planning pass: `AgentRunner` plan-mode run with the real Gateway and versioned directive
  prompt. Acceptable outcomes: parsed directives, or `FAILED/UNPARSEABLE_PLAN`. Both are recorded;
  `UNPARSEABLE_PLAN` on the first attempt triggers exactly one retry, then the test fails WITH the
  raw model output attached — that failure is a prompt-contract finding, never to be papered over.
- Functional correctness (`test_live_agent_writes_working_calculator`): real `AgentRunner` +
  `build_agent_runner_for_harness` equivalent, model `claude-haiku`, pinned calculator task prompt,
  approve plan, verify `calculator.py` by subprocess execution (not `exec()`/`import` in-process).
  Assert `add(2,3)`, `subtract(10,4)`, `multiply(3,4)`, `divide(10,2)` with `timeout=10`. On any
  failure, attach generated `calculator.py` content. No retry on this test — one call, one verdict.
  Phase 1 enforces at most one `WRITE` per plan (single-guarded mutation); multi-WRITE impl+test
  pairs are a legitimate Phase 2 consideration — models naturally emit them.
  Phase 1 feeds capped workspace file content into the planner prompt; Phase 2 two-pass planning
  (execute READs, feed results back, then plan WRITE) is the architecturally honest follow-on.
  Same `OPTIMUS_LIVE_MAX_COST_USD` cap (default `0.25`).

## Task L6: E2E Spawned Agent (Keystone)

**Status:** Implemented (2026-07-08). Keystone verified 3/3 consecutive green live runs;
committed evidence at `reports/plan-9-6-e2e-acp-transcript.json`. Verify with
`pytest tests/e2e/acp/test_spawned_agent_live.py -m e2e -v` after local gateway, Redis, and
`OPTIMUS_*` env are up.

**File:** `tests/e2e/acp/test_spawned_agent_live.py` (marker: `e2e`)

**Depends on completion-plan Tasks 4-5 (entrypoint).**

- Spawn `sys.executable -m optimus.acp --workspace-root <tmp-workspace>` as a real subprocess with
  piped stdin/stdout. Temp workspace fixture: git-initialized directory with one small Python file.
- Speak ndjson over the real pipes: `initialize` → `session/new` → `session/prompt` (docstring
  task) → consume real `session/update` notifications → answer the real agent-initiated
  `session/request_permission` with approve.
- Assert: the file on disk changed; `stopReason == "end_turn"`; cost fields are Gateway-reported
  and `> 0`; the plan record existed in the operator's real Redis during the turn.
- Guards: 120s wall-clock timeout kills the subprocess and fails; `OPTIMUS_LIVE_MAX_COST_USD` cap;
  one retry on `UNPARSEABLE_PLAN` then fail with transcript retained.
- Every stdio line (both directions) teed to `reports/plan-9-6-e2e-acp-transcript.json`. Secrets
  never cross stdio; the transcript writer must still refuse to serialize process env.
- No fake of any kind crosses the process boundary. This one test transitively proves entrypoint,
  bootstrap, pre-flight, protocol adapter, prompt contract, live-model directive parsing, Redis
  persistence, replay, and guarded mutation — composed.

## Task L7: `tools/verify_live_agent.py` (Operator Sign-Off Command)

**Status:** Implemented and live-verified (2026-07-08). Full flow, `--plan-only`, and
`--require-manual-approval` decline all verified live; committed evidence at
`reports/plan-9-6-live-agent-transcript.json`. Verify with
`python tools/verify_live_agent.py --workspace-root <scratch-dir>` after local gateway, Redis, and
`OPTIMUS_*` env are up. CLI behavior covered by
`tests/integration/release/test_verify_live_agent_cli.py`.

**Files:** `tools/verify_live_agent.py`, `tests/integration/release/test_verify_live_agent_cli.py`

- Phase 1 — pre-flight: runs all checks from `preflight.py`, prints a PASS/FAIL table per check,
  exits 2 on any failure with the operator action message.
- Phase 2 — live session: performs the Task L6 flow against `--workspace-root` (default
  `reports/.verify-live-agent-workspace` under the project root),
  writing `reports/plan-9-6-live-agent-transcript.json` and printing a summary: model, prompt
  version, plan hash, approval id, tool trajectory, files changed, total cost USD.
- Flags: `--workspace-root`, `--model`, `--task` (default docstring task on a generated scratch
  file inside the workspace), `--plan-only` (cheap check, no mutation),
  `--require-manual-approval` (prints the plan text and waits for operator y/n — the human
  approval demo without an IDE).
- Exit codes: 0 success, 2 pre-flight/config failure, 3 runtime failure.
- CLI test tier: argument/exit-code behavior with fakes is unit-tier; one `e2e`-marked invocation
  runs it for real.

## Task L8: Wire Pre-Flight into Existing Surfaces

**Status:** Implemented (2026-07-07). `run_preflight()` is shared by `--check-config [--strict]`,
`build_agent_runner_for_harness()`, and `run_phase1_release_gate.py --agent-harness`. README
operator runbook added. Live fixtures call `RedisRuntime.close()` and session teardown shuts down
the background Redis bridge loop.

**Files:** `src/optimus/acp/bootstrap.py`, `src/optimus/acp/__main__.py`,
`tools/run_phase1_release_gate.py`, `README.md`

- `--check-config` / `--check-config --strict` use `preflight.py` (no duplicated checks).
- `run_phase1_release_gate.py --agent-harness` runs pre-flight before any golden task.
- README gains the operator runbook below, verbatim-tested by the existing text-presence test
  pattern.

## Task L9: Async Redis Alignment (LLD §10 Contract)

**Status:** Implemented (2026-07-07). Chose remediation **(a)**: `RedisRuntime` builds one
`redis.asyncio.ConnectionPool` in bootstrap, `AsyncRedisAgentStateStore` backs the sync
`RedisAgentStateStore` facade, and `RedisTelemetryEventSink` wires `RedisTelemetryAdapter` into
production `AgentRunner`. `spec.py` runs `AgentRunner.run` via `asyncio.to_thread` to avoid
blocking the ndjson event loop. Verify with `pytest -q`, live tiers L2/L2A/L4, and
`pytest tests/unit/redis/test_runtime.py tests/unit/telemetry/test_redis_sink.py -v`.

**Files:** `src/optimus/agent/state_store.py`, `src/optimus/acp/bootstrap.py`,
`src/optimus/redis/runtime.py`, `src/optimus/telemetry/redis_sink.py`, `src/optimus/acp/spec.py`

- LLD §10 specifies `redis.asyncio` with one shared `ConnectionPool`. The current
  `RedisAgentStateStore` is synchronous inside an asyncio server — a blocked event loop stalls
  `session/update` streaming and permission round-trips.
- Remediation (pick one, document the choice in the plan checkbox):
  (a) preferred: migrate `RedisAgentStateStore` to `redis.asyncio`, sharing one
  `aioredis.ConnectionPool` between the state store and `RedisTelemetryAdapter`, built once in
  bootstrap; or (b) interim: wrap sync store calls in `asyncio.to_thread()` with a follow-up item.
- Bootstrap wires `RedisTelemetryAdapter` with the real client from the same pool — closing the
  audit finding that the adapter is never constructed in production wiring. Cost telemetry is
  "always-on internal telemetry" per Architecture §7 table; agent runs must emit it.
- Task L2A and L4 rerun green after the migration.

## Task L10: Plan-Text Persistence Governance Decision

**Status:** DECIDED (owner: Vibhanshu, 2026-07-08) — recommended position accepted. The Redis
plan store keeps raw plan text as short-TTL (3600s) operational approval state, documented as a
bounded exception to Architecture §4 with the TTL as the control; the exception explicitly does
not extend to indexed/long-lived structures (the Plan 11 structural memory store stays
signatures/summaries/paths only). Recorded in the Plan 9.5 completion doc (governance note under
Definition Of Done) and the README plan-persistence section.

**Files:** `docs/superpowers/plans/2026-07-07-plan-9-5-working-acp-agent-completion.md` (governance
note), `README.md`

- Architecture §4 bounds what may persist locally: HASH-catalogued signatures, summaries, relative
  paths; no unparsed source code in persistent vector indexes. The plan store persists `plan_text`
  whose `WRITE` bodies contain file content.
- Required outcome: an explicit, written decision — recommended position: the plan store is
  short-TTL (3600s) operational approval state, not an index, and replay correctness requires the
  exact text; document this as a bounded exception in the governance section with the TTL as the
  control. If compliance instead rejects it, the alternative is storing plan text on disk under the
  workspace with only its hash and path in Redis.
- HITL: this is an owner decision, not an implementer decision. Flag to Vibhanshu explicitly.

## Operator Runbook (README content and sign-off procedure)

```bash
# 1. Start Redis WITH TimeSeries on your machine (LLD §10 requires TS.* commands;
#    plain redis:7-alpine will fail pre-flight check 3b)
docker run --rm -d --name optimus-redis -p 6379:6379 redis:8

# 2. Real credentials — no fakes, no placeholders
export OPTIMUS_GATEWAY_URL=https://gateway.optimus.ai
export OPTIMUS_API_KEY=<real key>
export OPTIMUS_REDIS_URL=redis://127.0.0.1:6379/0

# 3. Pre-flight
python -m optimus.acp --workspace-root . --check-config --strict

# 4. Live tiers, in cost order
pytest -m requires_redis -v
pytest -m requires_gateway -v
pytest -m e2e -v

# 5. Operator sign-off command (defaults to reports/.verify-live-agent-workspace)
python tools/verify_live_agent.py
```

## Claim → Evidence Table (Definition of Done addendum)

| DoD claim | Real evidence artifact |
| --- | --- |
| Redis-backed plan state works in production | `test_redis_live_agent.py` green against live Redis |
| Bootstrap fails closed on bad/down Redis | `test_bootstrap_live_redis.py` green |
| LLD §10 telemetry contract (TS retention, metadata hash, TTL) holds on real Redis | `test_redis_telemetry_live.py` green |
| ACP server persists and replays via Redis | `test_server_stream_live_redis.py` green, including restart replay |
| Real model honors the directive prompt | `test_gateway_live.py` green (or its recorded failure drives a prompt fix) |
| An IDE-spawnable agent works end to end | `test_spawned_agent_live.py` green + committed `reports/plan-9-6-e2e-acp-transcript.json` |
| An operator can verify the deliverable alone | `tools/verify_live_agent.py` exit 0 + committed transcript |
| A real IDE can drive it | Zed session recording/log + workspace diff under `reports/` (HITL) |

## Known Open Defects

### Zed HITL: agent panel appears stuck after `session/prompt` (fixed 2026-07-10)

**Tracking:** [Plan 9.75](2026-07-09-plan-9-75-zed-hitl-acp-toolcall-permission.md) (P0,
2026-07-09 — confirmed on Plan 9.7 operator PATH install + Zed minimal `agent_servers` config).

**Status:** Fixed (2026-07-10). Evidence:
`reports/plan-9-75-zed-hitl-runtime-evidence.md` (pre-fix RCA + post-fix Cancel/Approve Zed
verification on operator PATH install). Root causes: non-conformant plan `entries` and permission
`toolCall`, plus JSON-RPC error masking as `stopReason: cancelled`. Merged via PR #36.

**Symptom:** Zed shows a loading indicator indefinitely after sending a prompt (for example
"Can you help me write a calculator?") with no visible completion, plan text, or error.

**Likely causes (not mutually exclusive):**

1. **Blocked on plan approval** — Agent mode emits `session/request_permission` after planning
   and keeps `session/prompt` pending until Zed replies. The approval card may be hidden,
   subtle, or not rendered for custom `agent_servers` entries.
2. **Workspace mismatch** — `session/new` sends Zed's opened project as `cwd`. If
   `--workspace-root` does not contain that folder, `session/new` fails; if misconfigured
   across sibling worktrees, later turns may behave unexpectedly. Use `"."` for
   `--workspace-root` and open Zed on the same repository folder.
3. **Infrastructure not ready** — Gateway or Redis down/slow; planning blocks up to the
   gateway client timeout (~30s) before any permission UI.
4. **ACP payload shape gap (fixed — Plan 9.75)** — Optimus `session/request_permission` now
   sends conformant plan `entries` and nested `toolCall`; error masking removed. Verified in Zed
   1.10 per `reports/plan-9-75-zed-hitl-runtime-evidence.md`.

**Workarounds to try:**

- Set `"agent": { "always_allow_external_agent_tools": true }` in Zed settings to auto-approve
  external ACP permission requests.
- Install the console script as a `uv` tool once — `uv tool install --editable .` — so Zed's
  `agent_servers` config can use `"command": "optimus-agent"` with no `.venv` python path and no
  per-worktree path juggling (see README "Install the `optimus-agent` command"). A raw path to a
  worktree's `.venv\Scripts\python.exe` is project-specific and was a stopgap, not the target
  shape; do not reintroduce it as the documented fix.
- Open Zed on the target worktree so `session/new`'s `cwd` resolves under `--workspace-root "."`.
- Confirm preflight: `optimus-agent --workspace-root . --check-config --strict`
  with gateway and Redis running.
- Smoke without Zed: `python tools/verify_live_agent.py --workspace-root <scratch-dir>`.
- Start a **new** agent session after config changes; cancel stuck turns with `session/cancel`.

**Follow-up (implementation):** ACP conformance fix landed in PR #36 — see **Plan 9.75**
(`docs/superpowers/plans/2026-07-09-plan-9-75-zed-hitl-acp-toolcall-permission.md`) and
`reports/plan-9-75-zed-hitl-runtime-evidence.md`.

## Execution Order Against In-Flight Work

- L1, L2, and L2A can start immediately (`state_store.py` and `redis_adapter.py` exist).
- L3, L4, L6, L7, L8 require completion-plan Tasks 4-5 (`bootstrap.py`, `__main__.py`,
  console script) — implement those next, before any further polish tasks.
- L5 requires only the existing runner + prompts and real credentials.
- L9 lands with or immediately after bootstrap (Task 4) so the shared pool is built once.
- L10 is a de