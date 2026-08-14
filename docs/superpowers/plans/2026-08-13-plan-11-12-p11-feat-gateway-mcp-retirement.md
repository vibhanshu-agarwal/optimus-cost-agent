# P11-FEAT-GATEWAY-MCP Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Gateway-owned MCP brokering surface and its custody without weakening the retained client-owned MCP path, its trust checks, or its real-dependency test markers.

**Architecture:** Delete the Gateway MCP implementation, typed Gateway MCP contract, Gateway startup/profile bootstrap, routes, usage accounting path, and Gateway-only tests. Retain the local/client MCP runtime and its common trust boundary; `execute_tool()` continues to validate the tool call and run `PreToolGuard.check()` before invoking the local runner. Update only the living status/custody documents in this plan; reversal of the authoritative architecture amendment is Plan 11.13.

**Tech Stack:** Python 3.14, `pytest`, `pytest-asyncio`, `coverage.py`, `pytest-cov`, Ruff, the existing ACP/client-MCP runtime, and the repository's Markdown custody/evidence documents.

**Status:** Approved planning artifact. Implementation has not started. This file is the contract for the later Cursor implementation branch.

## Global Constraints

- The implementation branch MUST be cut from the then-current `origin/main`, never from `agent/codex/plan-11-8-mcp-resumption` or another feature branch.
- The implementation is one retirement PR and one combined verification gate; it does not implement Plan 11.13's PDF/source-document reversal.
- The client-owned MCP path remains live, including `src/optimus/mcp/runtime.py`, local trust registration, descriptor exposure, `validate_tool_call`, `PreToolGuard.check`, client-MCP integrations, and client-MCP closure evidence.
- `requires_mcp_http` and `requires_mcp_stdio` are shared client-MCP real-dependency markers. Keep both registered in `pyproject.toml` and keep both in the default deselection expression.
- Remove only `requires_mcp_context7`; its sole retained consumer is the Gateway Context7 test being deleted by this plan.
- Preserve the one-key model: the local agent receives only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; no provider or upstream MCP credential is reintroduced locally.
- Use TDD where behavior remains: preserve or update tests for the retained local/client MCP guard path before changing its implementation, and do not add tests for retired Gateway behavior.
- Maintain at least 80% aggregate Python production-code coverage. Both coverage runs MUST use bare `--cov` so they inherit the same five configured source packages and `fail_under = 80` from `pyproject.toml`.
- The raw coverage JSON is temporary evidence and MUST be written under `$env:TEMP`, not under tracked `reports/`. Commit only the named Markdown coverage evidence report.
- The gitignored `docs/superpowers/reviews/plan-11-12-review-checkpoints.md` is reviewer custody, not implementation scope, and MUST NOT be staged.
- Historical documents may retain retired Gateway-MCP terminology. The live-code residue census is deliberately restricted to `src`, `tests`, and `tools`; `reports/` is not part of that zero-match census.

## Explicit Exceptions

- Do not edit the frozen Plan 11.8 design specification or rewrite its historical implementation record. Living status surfaces will identify Plan 11.8 as historical after retirement.
- Do not edit the merged Plan 11.11 implementation to rewrite its historical details. Living status surfaces will identify Plan 11.11 as historical precursor work.
- Do not edit HLD v2.17, LLD v2.40, Guardrails v1.2, Test Strategy v1.6, or `docs/sources/mcp-gateway-architecture-amendment/`; their authoritative reversal belongs exclusively to Plan 11.13.
- Do not delete or rename `tests/integration/mcp/test_client_mcp_live.py`, `tests/integration/mcp/test_client_sdk_real.py`, or other client-owned MCP tests.
- Do not remove `requires_mcp_http` or `requires_mcp_stdio`. Removing either marker would cause retained client-MCP tests to fail collection under `--strict-markers` and would make the default suite attempt real-server tests without their intended deselection.
- Do not change README or environment example files unless the live-status audit finds a Gateway-MCP claim; the approved preflight found none.
- Do not commit the raw JSON coverage files or the gitignored review checkpoint log.

## Review Findings Incorporated

| Finding | Durable plan rule |
|---|---|
| F1 | Delete `requires_mcp_context7`, the Context7 Gateway test, and all Context7 Gateway residue. Keep the shared HTTP/stdio markers. |
| F2 | Close `P11-FU-26` as obsolete-by-retirement and transfer its Windows socket-teardown signal to the still-open `P11-FU-6`. |
| F3 | Capture a pre-removal aggregate baseline before deletion and compare it with an identically configured post-removal run. |
| F4 | Remove Gateway imports/types and narrow `MCPRuntimeTrustContext.execute_tool()` to `MCPToolRunner -> dict[str, Any]` while retaining the common guards above execution. |
| F5 | Require an exact pre-edit hash match with `origin/main`; no stale-worktree or conditional file-existence language is permitted. |
| F6 | Bound the live residue census to `src tests tools`; preserve historical `reports/` evidence. |
| F7 | State that bare `--cov` inherits all five configured source packages and the configured threshold; do not compare against a narrowed source list. |
| F8 | Treat `MCPProfileRegistry` and `GatewayMCPDependencies` as modified-file residue risks and retain both in the census along with module-path catch-alls. |

## File Map

### Delete: Gateway implementation

- `src/optimus_gateway/mcp_connections.py`
- `src/optimus_gateway/mcp_discovery.py`
- `src/optimus_gateway/mcp_handlers.py`
- `src/optimus_gateway/mcp_invocation.py`
- `src/optimus_gateway/mcp_models.py`
- `src/optimus_gateway/mcp_profiles.py`
- `src/optimus_gateway/mcp_transports.py`
- `src/optimus_gateway/mcp_usage.py`
- `src/optimus/gateway/mcp_models.py`

### Delete: Gateway-only tests

- `tests/integration/optimus_gateway/test_gateway_mcp_context7_live.py`
- `tests/integration/optimus_gateway/test_gateway_mcp_live.py`
- `tests/integration/optimus_gateway/test_gateway_mcp_redis_live.py`
- `tests/unit/mcp/test_gateway_payload_boundary.py`
- `tests/unit/mcp/test_gateway_runner.py`
- `tests/unit/mcp/test_mcp_discovery_binding.py`
- `tests/unit/mcp/test_models.py`
- `tests/unit/optimus_gateway/test_mcp_accounting.py`
- `tests/unit/optimus_gateway/test_mcp_connections.py`
- `tests/unit/optimus_gateway/test_mcp_discovery.py`
- `tests/unit/optimus_gateway/test_mcp_handlers.py`
- `tests/unit/optimus_gateway/test_mcp_import_boundary.py`
- `tests/unit/optimus_gateway/test_mcp_invocation.py`
- `tests/unit/optimus_gateway/test_mcp_models.py`
- `tests/unit/optimus_gateway/test_mcp_profiles.py`
- `tests/unit/optimus_gateway/test_mcp_result_policy.py`
- `tests/unit/optimus_gateway/test_mcp_transports.py`
- `tests/unit/optimus_gateway/test_mcp_usage.py`
- `tests/unit/security/test_mcp_profile_manifest.py`

### Modify: retained source and tests

- `src/optimus/gateway/client.py` — remove Gateway MCP models, `discover_mcp`, `call_mcp`, `_post_mcp`, and the `/v1/tools/mcp/` special dispatch path while preserving ordinary typed Gateway tool calls.
- `src/optimus/mcp/runtime.py` — remove Gateway runner types and imports, remove Gateway discovery binding, narrow the runner/return types, and preserve the common trust/pre-tool guard sequence.
- `src/optimus/guardrails/mcp_trust.py` — remove Gateway manifest-hash binding state and methods while retaining local/client trust registration, descriptor exposure, and tool-call validation.
- `src/optimus_gateway/server.py` — remove Gateway MCP route dispatch, `MCPProfileRegistry`, `GatewayMCPDependencies`, MCP server configuration fields, and MCP startup defaults while preserving non-MCP Gateway routes.
- `src/optimus_gateway/__main__.py` — stop loading Gateway MCP profiles from the launch manifest and stop passing Gateway MCP dependencies to `serve_gateway`.
- `src/optimus_security/launch_manifest.py` — remove Gateway `mcp_profiles` bootstrap metadata, normalization, canonical serialization, and verification fields.
- `src/optimus/acp/local_infra.py` — remove Gateway MCP profile arguments and forwarding from local launch metadata.
- `src/optimus/acp/launch_approval_cli.py` — remove Gateway MCP profile arguments and launch-approval serialization.
- `pyproject.toml` — remove only `requires_mcp_context7`; retain `requires_mcp_http` and `requires_mcp_stdio` in both marker registration and default deselection.
- `tests/unit/optimus_gateway/test_server.py` — remove MCP fixtures/assertions and retain ordinary Gateway server tests.
- `tests/unit/acp/test_local_infra.py` — remove the Gateway MCP profile fixture and assertions; retain non-MCP launch metadata coverage.
- `tests/unit/docs/test_open_work_pool_hygiene.py` — update expected retired feature, historical plan, and closed-follow-up status surfaces.

### Preserve explicitly

- `tests/integration/mcp/test_client_mcp_live.py`
- `tests/integration/mcp/test_client_sdk_real.py`
- `tests/unit/mcp/test_runtime.py`
- `tests/unit/mcp/test_client_catalog.py`
- `tests/unit/mcp/test_client_config.py`
- `tests/unit/mcp/test_client_disposition.py`
- `tests/unit/mcp/test_client_mcp_closure.py`
- `tests/unit/mcp/test_client_sdk.py`
- `tests/unit/mcp/test_client_supervisor.py`
- `tests/unit/mcp/test_client_trust.py`
- `tests/integration/guardrails/test_mcp_trust_blocks_side_effects.py`
- `reports/plan-11-11-gateway-mcp-context7-compatibility.md`

### Modify: living custody and status surfaces

- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md`
- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`

### Create during implementation, not in this plan PR

- `reports/plan-11-12-coverage-evidence.md` — committed Markdown containing the pre-removal and post-removal aggregate coverage, exact commands, commit hashes, exit dispositions, and the five inherited coverage source packages. Raw JSON remains under `$env:TEMP`.

---

### Task 0: Establish the implementation base and capture the coverage baseline

**Files:**

- Read: `AGENTS.md`
- Read: `pyproject.toml`
- Create later: `reports/plan-11-12-coverage-evidence.md`

**Interfaces:**

- Consumes: merged Plan 11.12 document on the updated `origin/main`.
- Produces: a clean implementation branch and an immutable pre-removal coverage baseline.

- [x] **Step 1: Cut the implementation branch from the updated main.** Cursor must run this after the plan PR merges:

```powershell
git fetch origin main
git switch -c agent/cursor/plan-11-12-gateway-mcp-removal origin/main
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

Expected before edits: clean status and identical `HEAD`/`origin/main` hashes. If the hashes differ, stop and rebase/recreate from the current `origin/main`; do not proceed from a feature branch.

- [x] **Step 2: Verify the marker boundary before changing configuration.**

```powershell
git grep -n -E 'requires_mcp_(http|stdio)' -- pyproject.toml tests/integration/mcp/test_client_mcp_live.py tests/integration/mcp/test_client_sdk_real.py
git grep -n 'requires_mcp_context7' -- pyproject.toml tests/integration/optimus_gateway/test_gateway_mcp_context7_live.py
```

Expected: HTTP/stdio matches remain in `pyproject.toml` and retained client tests; Context7 matches exist only in the Gateway configuration/test slated for removal.

- [x] **Step 3: Run the pre-removal coverage baseline with raw JSON outside the repository.**

```powershell
$baselineJson = Join-Path $env:TEMP 'optimus-plan-11-12-pre-removal-coverage.json'
uv run --frozen pytest -q --cov --cov-report=term-missing "--cov-report=json:$baselineJson"
$baselineExit = $LASTEXITCODE
```

Record the aggregate percentage, `$baselineExit`, the command, `git rev-parse HEAD`, and the configured sources (`src/optimus`, `src/optimus_gateway`, `src/optimus_security`, `src/evidence_handoff`, `src/evidence_handoff_runtime`) in `reports/plan-11-12-coverage-evidence.md` before deletion. If the JSON/report shows that the existing tree is already below 80% and the only nonzero disposition is `fail_under`, record it as a pre-existing finding and continue; do not misclassify it as an 11.12 regression or stall the retirement slice. A nonzero exit caused by test failures is a baseline failure requiring investigation before edits.

---

### Task 1: Remove Gateway MCP execution and preserve the local trust boundary

**Files:**

- Delete: the nine Gateway implementation files in the File Map.
- Modify: `src/optimus/gateway/client.py`
- Modify: `src/optimus/mcp/runtime.py`
- Modify: `src/optimus/guardrails/mcp_trust.py`
- Modify: `src/optimus_gateway/server.py`
- Modify: `src/optimus_gateway/__main__.py`
- Test: `tests/unit/mcp/test_runtime.py`
- Test: `tests/unit/guardrails/test_mcp_trust.py`
- Test: `tests/unit/optimus_gateway/test_server.py`

**Interfaces:**

- Consumes: the pre-removal Gateway/client boundary and common MCP guardrail types.
- Produces: non-MCP Gateway startup/routes and a client/local MCP runtime whose public execution signature is `MCPToolRunner -> dict[str, Any]`.

- [x] **Step 1: Remove the Gateway MCP client surface.** Delete the agent-side Gateway MCP model imports and remove `GatewayClient.discover_mcp`, `GatewayClient.call_mcp`, `_post_mcp`, and any `/v1/tools/mcp/` special-case dispatch. Preserve ordinary `post_tool_json` behavior and all non-MCP typed Gateway operations.

- [x] **Step 2: Remove Gateway MCP server/bootstrap wiring.** Delete the MCP route table and dispatch from `server.py`, remove `MCPProfileRegistry` and `GatewayMCPDependencies` imports/fields/parameters, and simplify `serve_gateway` to the non-MCP startup contract. In `__main__.py`, stop reading `verified_manifest.mcp_profiles` and stop constructing or passing a Gateway MCP registry.

- [x] **Step 3: Narrow `src/optimus/mcp/runtime.py` without moving the guard boundary.** Remove the `GatewayClient` and `optimus.gateway.mcp_models` imports, `MCPGatewayRunner`, `GatewayClientMCPRunner`, `bind_gateway_discovery`, and the `hasattr(runner, "call")` branch. Change `execute_tool` to:

```python
runner: MCPToolRunner
-> dict[str, Any]
```

Keep `registry.validate_tool_call(...)` and `self.pre_tool_guard.check(...)` before `return runner(manifest.server_id, tool_name, arguments)`. The retained path must still fail closed on a rejected trust binding or pre-tool verdict.

- [x] **Step 4: Remove only Gateway binding state from `mcp_trust.py`.** Delete `gateway_manifest_hash`, `bind_gateway_manifest`, and Gateway-specific lookup/state. Preserve `MCPServerTrustRecord` fields and registry methods required by local/client explicit registration, descriptor exposure, and `validate_tool_call`.

- [x] **Step 5: Run the retained guard/server tests.**

```powershell
uv run --frozen pytest tests/unit/mcp/test_runtime.py tests/unit/guardrails/test_mcp_trust.py tests/unit/optimus_gateway/test_server.py -q
uv run --frozen ruff check src/optimus/gateway/client.py src/optimus/mcp/runtime.py src/optimus/guardrails/mcp_trust.py src/optimus_gateway/server.py src/optimus_gateway/__main__.py tests/unit/mcp/test_runtime.py tests/unit/guardrails/test_mcp_trust.py tests/unit/optimus_gateway/test_server.py
```

Expected: retained local/client guard behavior and ordinary Gateway server tests pass; no deleted Gateway MCP import remains.

---

### Task 2: Remove Gateway MCP launch metadata and profile bootstrap

**Files:**

- Modify: `src/optimus_security/launch_manifest.py`
- Modify: `src/optimus/acp/local_infra.py`
- Modify: `src/optimus/acp/launch_approval_cli.py`
- Modify: `tests/unit/acp/test_local_infra.py`
- Delete: `tests/unit/security/test_mcp_profile_manifest.py`

**Interfaces:**

- Consumes: the non-MCP launch manifest and approval metadata contracts.
- Produces: launch-manifest serialization, verification, and local startup with no Gateway `mcp_profiles` field or forwarding path.

- [x] **Step 1: Remove `mcp_profiles` from the launch manifest contract.** Delete the dataclass field, canonical field, normalization helper, build/serialize/verify handling, and any Gateway profile validation that exists only to bootstrap `MCPProfileRegistry`. Preserve all non-MCP manifest signatures, hashes, and verification behavior.

- [x] **Step 2: Remove local bootstrap forwarding.** Delete Gateway MCP profile parameters and forwarding from `local_infra.py` and `launch_approval_cli.py`. Remove only the Gateway profile fixture and assertion from `tests/unit/acp/test_local_infra.py`; retain non-secret launch metadata tests.

- [x] **Step 3: Run launch/manifest regression tests.**

```powershell
uv run --frozen pytest tests/unit/acp/test_local_infra.py tests/unit/security -q
uv run --frozen ruff check src/optimus_security/launch_manifest.py src/optimus/acp/local_infra.py src/optimus/acp/launch_approval_cli.py tests/unit/acp/test_local_infra.py
```

Expected: non-MCP launch-manifest signing/verification remains green and no `mcp_profiles` field is produced by local startup metadata.

---

### Task 3: Delete Gateway-only tests while preserving client-MCP evidence

**Files:**

- Delete: every Gateway-only test listed in the File Map.
- Modify: `tests/unit/optimus_gateway/test_server.py`
- Modify: `tests/unit/acp/test_local_infra.py`
- Preserve: `tests/integration/mcp/test_client_mcp_live.py`
- Preserve: `tests/integration/mcp/test_client_sdk_real.py`
- Preserve: `tests/unit/mcp/test_client_mcp_closure.py`

**Interfaces:**

- Consumes: the narrowed source/runtime contracts from Tasks 1–2.
- Produces: no Gateway-MCP tests, while retained client-MCP tests continue to collect under strict markers and remain default-deselected when their real dependencies are unavailable.

- [x] **Step 1: Delete only Gateway-owned tests.** Delete the exact Gateway integration/unit/model/profile/usage tests in the File Map, including `test_gateway_mcp_context7_live.py`, `test_mcp_discovery_binding.py`, and `test_models.py` after verifying their imports are Gateway-owned.

- [x] **Step 2: Prune mixed files instead of deleting them.** In `tests/unit/optimus_gateway/test_server.py`, remove MCP fixtures, route tests, and Gateway MCP imports while retaining ordinary server tests. In `tests/unit/acp/test_local_infra.py`, remove only the Gateway profile bootstrap fixture/assertion.

- [x] **Step 3: Verify retained client markers and closure evidence.**

```powershell
uv run --frozen pytest tests/integration/mcp/test_client_mcp_live.py tests/integration/mcp/test_client_sdk_real.py tests/unit/mcp/test_client_mcp_closure.py -q
```

Expected: client real-dependency tests remain collected and default-deselected by the retained HTTP/stdio markers; the historical P11-FU-9 closure test remains green and continues to reference its existing evidence report.

---

### Task 4: Retire only the Context7 marker and install the bounded residue gate

**Files:**

- Modify: `pyproject.toml`
- Create/update during implementation: `reports/plan-11-12-coverage-evidence.md`

**Interfaces:**

- Consumes: the deleted Gateway modules/tests and retained client-MCP marker contract.
- Produces: a zero-match live-code census that cannot be satisfied by deleting shared client infrastructure.

- [x] **Step 1: Remove only the Context7 marker.** Delete `requires_mcp_context7` from the `addopts` deselection expression and marker declarations in `pyproject.toml`. Keep both `requires_mcp_http` and `requires_mcp_stdio` in place, byte-for-byte in meaning, and keep them in the default deselection expression.

- [x] **Step 2: Run the retained-marker assertion.**

```powershell
git grep -n -E 'requires_mcp_(http|stdio)' -- pyproject.toml tests/integration/mcp/test_client_mcp_live.py tests/integration/mcp/test_client_sdk_real.py
```

Expected: known retained matches in `pyproject.toml` and the two client test files.

- [x] **Step 3: Run the exact live-code residue census.**

```powershell
git grep -n -E '/v1/tools/mcp|discover_mcp|call_mcp|MCPUsageRecord|MCPProfileRegistry|GatewayMCPDependencies|MCPGatewayRunner|GatewayClientMCPRunner|bind_gateway_discovery|gateway_manifest_hash|bind_gateway_manifest|mcp_profiles|MCPDiscover(Request|Response)|MCPCall(Request|Response)|requires_mcp_context7|OPTIMUS_MCP_CONTEXT7_|optimus_gateway\.mcp_|optimus\.gateway\.mcp_models' -- src tests tools
```

Expected: no matches. This command intentionally includes `MCPProfileRegistry`, `GatewayMCPDependencies`, `optimus_gateway.mcp_*`, and `optimus.gateway.mcp_models` because modified server/bootstrap/runtime files are residue risks. It intentionally excludes `requires_mcp_http`, `requires_mcp_stdio`, `docs`, and `reports`.

- [x] **Step 4: Run focused configuration/path assertions.**

```powershell
git grep -n 'requires_mcp_context7' -- pyproject.toml src tests tools
git ls-files src tests | Select-String 'test_gateway_mcp_context7_live\.py|optimus_gateway/mcp_|optimus/gateway/mcp_models\.py'
```

Expected: no matches. The historical Context7 report is not part of these assertions.

---

### Task 5: Close Gateway custody and mark historical status surfaces

**Files:**

- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Modify: `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py`

**Interfaces:**

- Consumes: the verified removal and residue evidence from Tasks 1–4.
- Produces: a current pool/charter/roadmap state in which Gateway MCP is retired, every deferred Gateway-MCP follow-up has named custody or a documented closure, and Plan 11.13 is an explicit pre-Registry/v1.0 dependency.

- [x] **Step 1: Retire the feature in the pool, charter, and roadmap.** Change `P11-FEAT-GATEWAY-MCP` to `Retired`, cite Plan 11.12, and identify Plans 11.8 and 11.11 as historical work. Do not rewrite their frozen or merged historical details.

- [x] **Step 2: Close Gateway-only deferred follow-ups.** Mark `P11-FU-12`, `P11-FU-13`, `P11-FU-14`, `P11-FU-15`, and `P11-FU-22` closed as won’t-do because the Gateway MCP feature is retired. Preserve their identifiers and record the retirement rationale rather than silently deleting them.

- [x] **Step 3: Resolve the Windows MCP flake custody.** Mark `P11-FU-26` closed as obsolete-by-retirement with this rationale: its original reproduction criteria target transport/test code removed by Plan 11.12, so the investigation can no longer be performed meaningfully. Transfer the observed Windows `WinError 10053` socket-teardown signal to the still-open `P11-FU-6`, which owns Gateway `test_server` port/teardown flake custody. State that no production retry or safety weakening was added.

- [x] **Step 4: Pin the documentation dependency.** Record that Plan 11.13 must reverse HLD v2.17, LLD v2.40, Guardrails v1.2, Test Strategy v1.6, and the amendment source tree before `P11-FEAT-REGISTRY` or the v1.0 cut. Leave those authoritative documents untouched in this plan.

- [x] **Step 5: Update the hygiene tests.** Change only assertions that encode the current Gateway-MCP feature/follow-up/plan status. Add assertions for the retired feature, closed won’t-do rows, obsolete-by-retirement P11-FU-26, retained open P11-FU-6 custody, and historical Plan 11.8/11.11 status.

- [x] **Step 6: Run the documentation hygiene tests.**

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
```

Expected: status surfaces agree with the pool and no unrelated current-state document becomes stale.

---

### Task 6: Produce the final evidence and run the single combined gate

**Files:**

- Create: `reports/plan-11-12-coverage-evidence.md`
- Read-only audit: `README.md`, `.env.example`, `.env.gateway.example`, living pool, charter, roadmap, and the merged Plan 11.11 status document
- Do not stage: `docs/superpowers/reviews/plan-11-12-review-checkpoints.md`

**Interfaces:**

- Consumes: all source, test, configuration, and custody changes from Tasks 1–5.
- Produces: named evidence for each Definition of Done claim and a clean implementation PR boundary.

- [x] **Step 1: Run the post-removal coverage command with the same inherited configuration.**

```powershell
$postJson = Join-Path $env:TEMP 'optimus-plan-11-12-post-removal-coverage.json'
uv run --frozen pytest -q --cov --cov-report=term-missing "--cov-report=json:$postJson"
$postExit = $LASTEXITCODE
```

Record the aggregate, exit disposition, command, commit hash, and inherited five-package source list in `reports/plan-11-12-coverage-evidence.md`. The aggregate must be at least 80% for the retirement PR to claim the coverage DoD. If the pre-removal baseline was already below 80%, report that fact separately from any post-removal change; do not manufacture tests for deleted Gateway code.

- [x] **Step 2: Run the full Windows gate.**

```powershell
uv run --frozen pytest -q
uv run --frozen ruff check .
git diff --check
```

Expected: full default suite green with the shared HTTP/stdio markers still deselected, Ruff clean, and no whitespace errors.

- [x] **Step 3: Run the alternate-platform gate.** From the WSL2 path for this same implementation branch, run `uv sync --frozen --extra dev` and `uv run pytest -q`. If the retained Gateway `test_server` harness reproduces the known Windows teardown signal, record it under `P11-FU-6`; do not mask it with retries or close `P11-FU-6` from this plan. WSL2 result: 2 failed / 3065 passed; both failures are `P11-FU-17` (Windows worktree `.git` pointer). `P11-FU-6` did not reproduce. No clean-WSL2 claim.

- [x] **Step 4: Re-run the exact live-code census and marker assertions.** The commands from Task 4 must produce zero live Gateway-MCP matches, known retained HTTP/stdio matches, and no Context7 marker/file matches.

- [x] **Step 5: Audit the documentation freshness boundary.** Confirm that every current-state claim changed by this plan is current in the pool, charter, roadmap, and README/environment surfaces, while historical Plan 11.8/11.11 and Context7 evidence remain intentionally historical.

- [x] **Step 6: Check the final PR boundary.**

```powershell
git status --short --branch
git diff --stat origin/main...HEAD
git diff --name-only origin/main...HEAD
```

Expected: only the intended plan implementation files and `reports/plan-11-12-coverage-evidence.md` are changed; the gitignored review checkpoint log is absent from the staged/committed set.

## Definition of Done

- `src/optimus_gateway/mcp_*.py` and `src/optimus/gateway/mcp_models.py` are deleted.
- Gateway MCP client methods, `/v1/tools/mcp/*` routes, `MCPUsageRecord` path, Gateway manifest binding, and Gateway bootstrap metadata are removed.
- `src/optimus/mcp/runtime.py` retains the common trust checks and local runner path with `MCPToolRunner -> dict[str, Any]` typing.
- `requires_mcp_context7` is absent from live code/config; `requires_mcp_http` and `requires_mcp_stdio` remain registered and default-deselected for retained client tests.
- The exact `src tests tools` residue census returns no matches, including `MCPProfileRegistry`, `GatewayMCPDependencies`, `optimus_gateway.mcp_*`, and `optimus.gateway.mcp_models`.
- The full Windows suite and WSL2 suite pass, or any pre-existing `P11-FU-6` teardown signal is recorded without being misrepresented as a product fix.
- Post-removal aggregate coverage is at least 80%, with the pre-removal baseline and any pre-existing sub-80 disposition recorded in `reports/plan-11-12-coverage-evidence.md`.
- `uv run --frozen ruff check .` and `git diff --check` pass.
- `P11-FEAT-GATEWAY-MCP` is retired; `P11-FU-12/13/14/15/22` are closed won’t-do; `P11-FU-26` is closed obsolete-by-retirement; `P11-FU-6` retains named custody of the Windows teardown signal.
- Plans 11.8 and 11.11 are marked historical in living status surfaces, and Plan 11.13 is pinned as required before Registry/v1.0.
- Plan 11.13's authoritative PDFs/source tree remain untouched by this PR.

## Execution Handoff

This plan PR is documentation-only. After it is reviewed and merged, Cursor must create `agent/cursor/plan-11-12-gateway-mcp-removal` from the updated `origin/main`, read the review checkpoint log before mutating, execute this plan task-by-task, and present the implementation diff plus named evidence for review. No implementation checkbox may be marked complete until its stated verification command has run and passed.
