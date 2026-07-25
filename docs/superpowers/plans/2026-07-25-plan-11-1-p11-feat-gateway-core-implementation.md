# Plan 11.1: P11-FEAT-GATEWAY-CORE Implementation Plan

> For agentic workers: REQUIRED SUB-SKILLS: Use superpowers:executing-plans to execute this
> plan task-by-task and superpowers:test-driven-development for every behavior change. Do not
> mark a checkbox complete until its stated verification command has actually passed.

**Status:** Pending reviewer-agent and operator approval; implementation is not authorized.

**Stable feature:** P11-FEAT-GATEWAY-CORE (Plan 11.1). The ratified TOOLS and COST-OBS identities
have no plan numbers reserved by this plan.

**Baseline:** origin/main at b5fdc65515410719bd03648ea3224bc7e2a9c07d; committed Stage 0–2
baseline at 4638b195dc345c695560f4ec248f92948a8480a0.

**Design spec:**
docs/superpowers/specs/2026-07-25-plan-11-1-p11-feat-gateway-core-design.md
(SHA-256 B7AF4288F3CF085FBBCDB146CC4D590CDF34C08F8CA09BE940B343F9CD76CE5F).

**Requirement inventory:**
docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md
(SHA-256 7DD4FA40916B2306C55492B36D37FC0178798CC20552B6E73CF13CBF5B69FDC5).

## Goal

Serve the three CORE routes through the local Gateway process while preserving the one-key agent
boundary, origin/secrets controls, provider routing, distinct model wire shapes, retry behavior,
the normalized response-usage contract, and the /v1/observability/traces ingress surface.

The plan must leave /v1/tools/web/search, /v1/tools/web/extract, package/advisory routes, and MCP
brokering outside CORE. It must not implement budget enforcement, tenant-aware model/tool policy,
wallet mapping, or COST-OBS normalization/amortization depth.

## Global constraints

- The local agent resolves only OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY; provider credentials
  remain Gateway-side. Preserve the current single bearer verifier and constant-time comparison.
- Preserve built-in origin trust, non-production loopback behavior, signed tenant-profile origins,
  production rejection of extra origins, and loopback-only local Gateway binding.
- The request envelope is extensible: validate known fields strictly, tolerate unknown top-level
  keys and unknown metadata keys, and never use unknown fields as policy.
- metadata is reserved for identity/context. Existing run_id/session_id flow remains valid; later
  TOOLS work may add execution_mode, org_id, and project_id additively.
- The explicit non-goal is: Plan 11.1 performs no server-side model-permission or Plan-mode
  revalidation; that is P11-FEAT-GATEWAY-TOOLS.
- /v1/responses uses input; /v1/chat/completions uses messages; both mixed-shape directions fail
  before provider execution.
- For model responses, gateway_request_id, provider, cache_hit, billing_units, and non-null
  decimal cost_usd are required usage-contract fields. Missing usage, empty IDs, absent/null cost,
  and malformed known fields fail closed. The observability route returns a plain accepted
  acknowledgement with gateway_request_id and carries no usage or cost claim.
- Retry only transient timeout/provider faults, with the existing four-attempt ceiling, reraise=True,
  and retry-count telemetry. Never retry auth, validation, pricing, unsupported model, or
  malformed-envelope failures.
- No source or test implementation starts until this frozen plan and its approval record exist.
- Real route evidence must use a served route at the point the evidence is claimed. Unit fakes may
  stand in only for unit-tier dependencies; live-tier evidence must use its named real dependency.
- Every success-path requirement must trace to a committed inventory row or an explicitly named
  existing contract seam. A new success-path usage/cost claim without inventory custody is scope
  creep and must be rejected; every in-scope CORE inventory row cited by this plan must map to an
  executable test or evidence target. Apply the same self-check when TOOLS and COST-OBS are picked
  up.
- No charter, roadmap, frozen source document, README, TOOLS feature, COST-OBS feature, or MCP
  contract is changed by this plan.

## Source and current-state anchors

- src/optimus_gateway/server.py:22 currently serves only /v1/responses; other paths return 404.
- src/optimus_gateway/models.py:15-86 owns local service configuration and authorize_bearer.
- src/optimus_gateway/responses.py:14-76 owns current Responses auth, validation, provider call,
  pricing, and response construction.
- src/optimus/gateway/models.py:46-79 owns open metadata payload construction and strict
  GatewayUsage parsing.
- src/optimus/gateway/client.py:100-146 already has model, tool, and observability client seams.
- src/optimus/telemetry/observability.py:20 already posts events to /v1/observability/traces.
- src/optimus/agent/planning_loop.py:885-890 already sends run_id and session_id in metadata.
- src/optimus/config/gateway.py:76-118 owns production constraints and trusted-origin checks.
- src/optimus/tools/policy.py:85-93 currently routes dependency/CVE signals through generic web
  search; that divergence belongs to P11-FU-2, not this plan.

## File responsibility map

| File/surface | Responsibility |
|---|---|
| src/optimus_gateway/server.py | Dispatch the three CORE routes; retain 404 for TOOLS paths. |
| src/optimus_gateway/models.py | Shared server config/auth and request/response contract models. |
| src/optimus_gateway/responses.py | Responses validation, provider routing, usage envelope, and error mapping. |
| src/optimus_gateway/chat_completions.py or an equivalent existing module | Chat-shape validation and OpenAI-compatible response shaping. Reuse an existing seam if one is present. |
| src/optimus_gateway/observability.py or an equivalent existing module | Structured event validation, ingress, and adapter boundary; no pricing redesign. |
| src/optimus/gateway/models.py | Preserve client payload/usage parsing and open metadata behavior. |
| src/optimus/config/gateway.py | Preserve origin and local-provider-key rejection behavior. |
| tests/unit/optimus_gateway/ | Route, shape, auth, retry, response-envelope, and observability unit tests. |
| tests/integration/ or the existing real-process Gateway test location | Real HTTP evidence for all three CORE routes. |
| docs/superpowers/reviews/plan-11-review-checkpoints.md | Gitignored reviewer/implementation handoff log; never stage. |

## Task 0: Verify freeze inputs before implementation

**Produces:** evidence that the worker is on the approved baseline and that the design and plan
digests match the approval record.

- [ ] Verify branch, HEAD, origin/main, inventory commit, spec SHA-256, and this plan SHA-256.
- [ ] Confirm working-tree bytes equal committed-blob bytes for every pinned artifact before trusting any digest.
- [ ] Confirm no implementation or test path is dirty before starting.
- [ ] Read the reviewer/operator approval record and the checkpoint log Current State section.
- [ ] Do not modify source or tests until these checks and the approval record pass.

Verification:

~~~bash
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
sha256sum docs/superpowers/specs/2026-07-25-plan-11-1-p11-feat-gateway-core-design.md
sha256sum docs/superpowers/plans/2026-07-25-plan-11-1-p11-feat-gateway-core-implementation.md
sha256sum docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md
git show HEAD:docs/superpowers/specs/2026-07-25-plan-11-1-p11-feat-gateway-core-design.md | sha256sum
git show HEAD:docs/superpowers/plans/2026-07-25-plan-11-1-p11-feat-gateway-core-implementation.md | sha256sum
git show HEAD:docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md | sha256sum
[ "$(sha256sum docs/superpowers/specs/2026-07-25-plan-11-1-p11-feat-gateway-core-design.md | cut -d' ' -f1)" = "$(git show HEAD:docs/superpowers/specs/2026-07-25-plan-11-1-p11-feat-gateway-core-design.md | sha256sum | cut -d' ' -f1)" ]
[ "$(sha256sum docs/superpowers/plans/2026-07-25-plan-11-1-p11-feat-gateway-core-implementation.md | cut -d' ' -f1)" = "$(git show HEAD:docs/superpowers/plans/2026-07-25-plan-11-1-p11-feat-gateway-core-implementation.md | sha256sum | cut -d' ' -f1)" ]
[ "$(sha256sum docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md | cut -d' ' -f1)" = "$(git show HEAD:docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md | sha256sum | cut -d' ' -f1)" ]
~~~

## Task 1: Put the three-route dispatch surface in place first

**Files:** src/optimus_gateway/server.py; route/server tests under tests/unit/optimus_gateway/.

**Purpose:** eliminate the route-level 404 gap before any evidence task depends on these paths.

- [ ] Write failing HTTP-handler/server tests proving /v1/responses, /v1/chat/completions, and
  /v1/observability/traces reach distinct handlers, while /v1/tools/web/search and
  /v1/tools/web/extract remain 404.
- [ ] Add explicit path dispatch without moving authentication or provider secrets into the
  client-side package.
- [ ] Preserve invalid JSON, non-object body, and unknown-route status behavior.
- [ ] Run focused server tests and confirm the three route paths are no longer 404 before
  proceeding to route-dependent tasks.

Verification:

~~~powershell
uv run --frozen pytest tests/unit/optimus_gateway/test_server.py -q
~~~

## Task 2: Implement extensible model envelopes and both wire shapes

**Files:** src/optimus_gateway/models.py, src/optimus_gateway/responses.py, the selected chat
module, and focused tests.

- [ ] Write RED tests for Responses input, Chat messages, both do-not-mix rejection directions,
  missing known fields, unknown top-level fields, and unknown metadata keys.
- [ ] Add shared known-field validation that tolerates unknown top-level and metadata keys without
  treating them as policy.
- [ ] Add the Chat Completions route using the existing provider/model seam and return an
  OpenAI-compatible choices response plus the common gateway_usage object.
- [ ] Preserve the existing Responses output and gateway_usage contract.
- [ ] Confirm both routes use one shared bearer-auth path and never forward provider credentials.
- [ ] Extend the existing real-process harness at
  tests/integration/optimus_gateway/test_gateway_live_smoke.py to exercise
  /v1/chat/completions and re-confirm /v1/responses before leaving this task. Record that
  task-level artifact; this is the first real HTTP evidence for the second model route.
- [ ] Run route/schema unit tests and the task-level real-process artifact before adding retry or
  later consolidated evidence work.

Verification:

~~~powershell
uv run --frozen pytest tests/unit/optimus_gateway/test_server.py tests/unit/optimus_gateway/test_responses.py tests/unit/optimus_gateway/test_models.py -q
uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_live_smoke.py -q
~~~

## Task 3: Make the response-usage contract and fail-closed gate executable

**Files:** src/optimus_gateway/responses.py, src/optimus/gateway/models.py only if required by
the existing client contract, and usage/client tests.

- [ ] Write RED tests for missing gateway_request_id, empty request ID, absent usage,
  missing/null cost_usd, malformed numeric fields, and the GATEWAY_COST_MISSING audit path.
- [ ] Ensure successful Responses and Chat responses carry the required usage fields without
  inventing budget or amortization behavior. The observability route is intentionally excluded
  from this usage contract and returns only its accepted acknowledgement.
- [ ] Ensure malformed upstream or downstream envelopes fail closed before output, ledger, or
  RedisTimeSeries persistence is possible.
- [ ] Keep cost_usd validation in CORE while leaving price normalization, provider-native unit
  mapping, and amortization depth to COST-OBS.
- [ ] Preserve existing GatewayUsage parsing and current response compatibility.

Verification:

~~~powershell
uv run --frozen pytest tests/unit/gateway/test_models.py tests/unit/gateway/test_usage_fields.py tests/unit/optimus_gateway/test_responses.py -q
~~~

## Task 4: Serve observability ingress through the CORE adapter boundary

**Files:** src/optimus_gateway/server.py, the selected observability module, and route tests.

- [ ] Write RED tests for authenticated structured-event ingress, required events array,
  non-object event rejection, unknown top-level tolerance, malformed JSON, and sanitized errors.
- [ ] Implement /v1/observability/traces as validated structured-event ingress returning a plain
  accepted acknowledgement containing status and gateway_request_id, with no gateway_usage,
  billing_units, or cost_usd claim. Do not implement LangSmith pricing or amortization here.
- [ ] Ensure event contents are treated as untrusted data: never execute them, follow URLs, or
  promote them to policy.
- [ ] Verify the existing GatewayObservabilityExporter can call the route and no longer receives
  the server unknown-path 404.
- [ ] Extend the existing real-process harness at
  tests/integration/optimus_gateway/test_gateway_live_smoke.py to exercise
  /v1/observability/traces and record the task-level accepted-ack artifact before proceeding.

Verification:

~~~powershell
uv run --frozen pytest tests/unit/optimus_gateway/test_server.py tests/unit/telemetry/test_observability.py -q
uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_live_smoke.py -q
~~~

## Task 5: Preserve origin, secret, retry, and error boundaries

**Files:** existing Gateway config/auth/provider/retry modules and their focused tests.

- [ ] Write or extend tests for missing/wrong bearer, constant-time auth path, server-side
  provider-key isolation, production origin rejection, signed-origin acceptance, and non-production
  loopback behavior.
- [ ] Implement only the narrow retry predicate: timeout/provider transient faults, maximum four
  attempts, reraise=True, and retry_count telemetry.
- [ ] Confirm permanent validation/auth/model/pricing/envelope failures do not retry.
- [ ] Confirm error bodies are sanitized and no provider key, raw upstream response, or secret is
  logged or returned.
- [ ] Explicitly test that CORE does not reject requests because of budget, org/project identity,
  model permission, or Plan-mode policy; those remain outside this plan.

Verification:

~~~powershell
uv run --frozen pytest tests/unit/optimus_gateway tests/unit/config/test_gateway_settings.py tests/unit/gateway -q
uv run --frozen ruff check src/optimus_gateway src/optimus/config/gateway.py src/optimus/gateway
~~~

## Task 6: Produce real route evidence after routes exist

**Files:** real-process integration evidence and the checkpoint log only; do not stage the log.

- [ ] Run the existing real-process harness at
  tests/integration/optimus_gateway/test_gateway_live_smoke.py as the consolidated release-gate
  artifact after the Task 2 and Task 4 route-level artifacts already exist.
- [ ] Record evidence that /v1/responses and /v1/chat/completions are served, authenticated, and
  produce valid model usage envelopes; record that /v1/observability/traces is served,
  authenticated, and returns the plain accepted acknowledgement with gateway_request_id and no
  usage or cost claim.
- [ ] Record evidence that /v1/tools/web/search and /v1/tools/web/extract remain outside CORE.
- [ ] For any named live Gateway/provider tier, use the real dependency rather than a fake. Do not
  claim live evidence from the unit upstream stub.
- [ ] Reconcile the three route results with the one-key release gate and final scope audit; this
  task is consolidated release evidence, not first HTTP contact with any route.

Verification:

~~~powershell
uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_live_smoke.py -q
~~~

The exact command and artifact path must be recorded in the checkpoint log. The named harness
already exists and binds a real loopback port while starting the actual Gateway process; a unit-only
result cannot close this task.

## Task 7: Repository fitness and final security audit

- [ ] Run the affected unit and integration suites.
- [ ] Run the repository default suite.
- [ ] Run aggregate coverage at the repository 80% threshold.
- [ ] Run uv run --frozen ruff check . and git diff --check.
- [ ] Confirm README, charter, roadmap, frozen source PDFs, TOOLS/COST-OBS work, and MCP source
  repair remain outside the diff.
- [ ] Confirm the one-key release scan resolves only OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY
  locally and that no provider host is contacted directly.
- [ ] Update the gitignored checkpoint log with exact commands, artifacts, coverage, Ruff result,
  route evidence, and final implementation SHA. Do not stage or commit the checkpoint log.

Verification:

~~~powershell
uv run --frozen pytest -q
uv run --frozen pytest --cov=optimus --cov=optimus_gateway --cov=optimus_security --cov-report=term-missing --cov-fail-under=80 -q
uv run --frozen ruff check .
git diff --check
git status --short --branch
~~~

## Evidence-to-claim table

| Claim | Required evidence |
|---|---|
| Three CORE routes are served | Real-process HTTP artifact after Task 1–4; focused route tests are supporting evidence. |
| Both model shapes and do-not-mix rule work | Focused unit tests plus real /v1/responses and /v1/chat/completions requests. |
| Envelope is fail-closed | Five malformed-response cases, including null cost_usd and GATEWAY_COST_MISSING, plus client parsing tests. |
| Auth/origin/secret boundary holds | Existing config/auth tests, process configuration evidence, and one-key release scan. |
| Retry behavior is bounded | Focused retry tests with attempt count and telemetry assertions. |
| Observability route is safe | Task 4 and consolidated Task 6 real-process artifacts plus structured-event validation tests; the CORE success response is only an accepted acknowledgement with gateway_request_id and makes no usage or cost claim. |
| Budget remains deferred | Inventory rows, parked P9.85-FU-3 disposition, and explicit absence of budget enforcement in tests/design. |

## Definition of Done

- [ ] The three CORE routes are served by the local Gateway process; TOOLS paths remain outside
  CORE.
- [ ] Both model wire shapes and both do-not-mix directions are validated; unknown top-level and
  metadata keys remain tolerated.
- [ ] metadata is documented as the identity/context channel and the R3 non-goal is explicit.
- [ ] One-key, origin, server-side secret, retry, and fail-closed response contracts are preserved.
- [ ] The observability route is served with validated structured-event ingress and a plain accepted
  acknowledgement containing gateway_request_id and no usage or cost claim; LangSmith export and
  normalization/amortization depth remain COST-OBS.
- [ ] No budget enforcement or tenant-aware model/Plan-mode policy is implemented or claimed.
- [ ] Affected tests, real route evidence, default tests, coverage >=80%, Ruff, and diff hygiene pass.
- [ ] All checkboxes above are backed by their stated verification commands and artifacts.
