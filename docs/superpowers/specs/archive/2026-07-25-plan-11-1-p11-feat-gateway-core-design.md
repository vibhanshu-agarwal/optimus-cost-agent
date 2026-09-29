# Plan 11.1: P11-FEAT-GATEWAY-CORE Design Specification

**Status:** Pending reviewer-agent and operator approval; implementation is not authorized.

**Stable feature:** `P11-FEAT-GATEWAY-CORE` (Plan 11.1). This specification covers the Gateway
core and the `/v1/observability/traces` route. It does not create plan numbers for
`P11-FEAT-GATEWAY-TOOLS` or `P11-FEAT-GATEWAY-COST-OBS`.

**Baseline:** `origin/main` at `b5fdc65515410719bd03648ea3224bc7e2a9c07d`, with the committed
Stage 0–2 inventory baseline at `4638b195dc345c695560f4ec248f92948a8480a0`.

**Authoritative inventory:**
`docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md`
(SHA-256 `7DD4FA40916B2306C55492B36D37FC0178798CC20552B6E73CF13CBF5B69FDC5`).

## Goal

Make the local Optimus Gateway serve the CORE agent-facing surface under the one-key boundary:

- `POST /v1/responses`, preserving the existing route and client contract;
- `POST /v1/chat/completions`, with the distinct Chat Completions wire shape;
- `POST /v1/observability/traces`, so the existing observability exporter no longer receives a
  404; and
- a common, validated response-usage envelope for the model routes containing `gateway_request_id`,
  `provider`, `cache_hit`, `billing_units`, and non-null `cost_usd`.

The Gateway remains the only process that holds provider credentials. The local agent continues to
use only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` as its runtime credential set. The local
Gateway service's current single bearer verifier (`GatewayServiceConfig.shared_secret` checked by
`authorize_bearer`) remains one shared credential value; this plan does not introduce tenant or
project identity resolution.

## Problem and evidence

The client already calls three Gateway paths, but the local server currently dispatches only
`/v1/responses` (`src/optimus_gateway/server.py:22`). The client-side seams are present:

- `build_responses_payload()` already emits an optional open `metadata` dictionary
  (`src/optimus/gateway/models.py:46-55`);
- the planning loop already sends `run_id`, `session_id`, `purpose`, and `planning_turn` through
  that metadata channel (`src/optimus/agent/planning_loop.py:885-890`);
- `GatewayObservabilityExporter` posts structured events to `/v1/observability/traces`
  (`src/optimus/telemetry/observability.py:20`); and
- `GatewayUsage` and `parse_gateway_usage()` already define the client-side usage contract
  (`src/optimus/gateway/models.py:11-79`).

The current local service authenticates one bearer value and routes model requests through the
existing provider/model/pricing seams (`src/optimus_gateway/models.py:15-86` and
`src/optimus_gateway/responses.py:14-76`). It does not yet provide the second model route or the
observability ingress route.

The committed inventory establishes the source boundary: HLD §5A/§11, LLD §0/§0.A/§0A/§6/§9C/§9D,
Guardrails §9, and Test Strategy §7 are CORE-owned; budget enforcement remains parked under
`P9.85-FU-3`; package/advisory routes remain `P11-FU-2`; and MCP endpoint shape remains the
`P11-FU-3` source-repair gap.

## Scope

### In scope

- The one-key local-agent boundary and server-side provider-secret isolation.
- Built-in origin trust, non-production loopback behavior, signed tenant-profile origins, and
  production rejection of `OPTIMUS_EXTRA_GATEWAY_ORIGINS`, preserving the existing
  `OptimusGatewaySettings.validate_trusted_gateway()` contract.
- Shared bearer authentication through the existing `authorize_bearer` seam.
- Model routing through the existing provider/model mapping and upstream client seams.
- Both `/v1/responses` and `/v1/chat/completions` request shapes, including the bidirectional
  do-not-mix rejection rule.
- Retry classification and telemetry for transient provider faults: timeouts and the existing
  provider/time-out error codes may retry up to the existing four-attempt ceiling; validation,
  authentication, unsupported-model, pricing, and other permanent failures do not retry.
- A common model-response usage contract and fail-closed validation for malformed success
  envelopes, including absent or null `cost_usd`, absent `gateway_request_id`, absent usage, and
  empty request IDs.
- `POST /v1/observability/traces` as an authenticated, structured event-ingress route. Its route
  availability and request validation are CORE; downstream LangSmith export and normalization or
  amortization depth remain the COST-OBS boundary.
- Real process/HTTP route evidence in the implementation plan, with route work sequenced before
  evidence tasks that depend on a served endpoint.

### Explicit non-goals and exclusions

- **Budget enforcement:** Plan 11.1 performs no server-side model or tool budget enforcement. Every
  budget-authority requirement remains
  `Deferred → P9.85-FU-3 (parked; operator decision pending)`. CORE carries and validates
  `cost_usd`; it does not debit wallets, compare caps, or reject requests for spend.
- **Model-permission and Plan-mode revalidation:** *Plan 11.1 performs no server-side
  model-permission or Plan-mode revalidation; that is `P11-FEAT-GATEWAY-TOOLS`.* The required
  org/project identity layer is not built, and resolving it is entangled with the parked wallet
  decision. CORE may authenticate the shared bearer and preserve extensible metadata, but must not
  imply tenant-aware policy enforcement.
- `/v1/tools/web/search` and `/v1/tools/web/extract` remain TOOLS and are not served by this plan.
- `/v1/tools/package/lookup` and `/v1/tools/security/advisory` remain owned by `P11-FU-2` and are
  not served by this plan.
- MCP brokering is not inferred or implemented; its endpoint shape remains owned by `P11-FU-3`
  and the LLD source-repair work.
- COST-OBS owns provider-native normalization, ledger reconciliation, LangSmith export, and
  observability cost allocation/amortization depth. CORE supplies the model-route wire-level usage
  contract and the traces accepted acknowledgement but does not redefine that accounting model.
- No hosted multi-tenant Gateway, new provider credential, provider-key exposure, or direct local
  provider call is introduced.

## Design decisions

### 1. Route surface and dispatch order

The server dispatch table is explicit and ordered before provider execution:

| Route | CORE behavior | Not CORE |
|---|---|---|
| `/v1/responses` | Preserve and harden the existing Responses route, auth, routing, retry, and usage envelope. | Budget decisions and tool policy. |
| `/v1/chat/completions` | Add a served Chat Completions route using the same auth, routing, retry, and usage seams. | Treating `messages` as `input`, or vice versa. |
| `/v1/observability/traces` | Add authenticated structured-event ingress and a stable accepted acknowledgement. | Usage, cost accounting, LangSmith pricing, export policy, and amortization implementation. |
| `/v1/tools/*` | Return the existing not-found behavior from this CORE server. | Web, package/advisory, MCP, and tool-policy implementation. |

Route selection happens before request-specific provider work. Every route rejects invalid JSON,
non-object model bodies, and malformed known fields before dispatching upstream. Unknown routes
remain 404. Authentication is checked before provider execution and never leaks provider details.

### 2. Extensible model request envelope

The model request envelope is intentionally extensible. Known fields are validated strictly, while
unknown top-level fields and unknown keys inside `metadata` are tolerated and preserved for the
route's request context. This is a load-bearing compatibility rule: Test Strategy §10's malformed
input gate rejects malformed known shapes, but a closed `extra="forbid"` envelope would prevent the
TOOLS slice from adding identity context later without breaking CORE.

For both model routes:

- `model` is required and must be a non-empty string;
- `metadata`, when present, is a JSON object; its unknown keys are tolerated;
- top-level unknown keys are tolerated and are not interpreted as policy; and
- provider credentials, authorization tokens, and raw provider responses are never copied into
  metadata or persisted as request context.

`metadata` is the reserved identity/context channel. `run_id` and `session_id` already flow there.
The later TOOLS extension may add `execution_mode`, `org_id`, and `project_id` additively. CORE
does not require, resolve, or authorize those future fields.

### 3. Distinct model wire shapes

`POST /v1/responses` accepts `input` as the top-level content field and rejects a `messages` field.
`POST /v1/chat/completions` accepts a non-empty `messages` array and rejects an `input` field.
The validator must reject both directions explicitly:

| Route | Required shape | Rejected mixed shape |
|---|---|---|
| `/v1/responses` | `{ "model": "...", "input": "..." }` | `messages` at `/v1/responses` |
| `/v1/chat/completions` | `{ "model": "...", "messages": [...] }` | `input` at `/v1/chat/completions` |

The internal provider request may normalize both forms to the existing upstream seam, but the
agent-facing validation and response shape remain distinct. The chat response is OpenAI-compatible
(`id`, `object`, `choices`, and a single assistant message) and carries the same `gateway_usage`
object as the Responses response. The Responses response preserves the existing `output_text`
contract and `gateway_usage` object.

### 4. Response envelope and malformed-response fail-closed behavior

`gateway_usage` is the current wire-level normalized envelope consumed by
`parse_gateway_usage()`. Every successful model response carries:

```json
{
  "gateway_request_id": "gw-...",
  "provider": "...",
  "provider_request_id": "...",
  "cache_hit": false,
  "billing_units": 42,
  "cost_usd": "0.0004"
}
```

`gateway_request_id`, `provider`, and `billing_units` are required; `billing_units` is non-negative;
`cost_usd` is required, non-null, decimal-parseable, and non-negative. The response parser and
server-side response builder must fail closed on missing usage, missing/empty request ID, missing
or null cost, and malformed known fields. No partial model output is applied or persisted when the
agent receives a malformed envelope. The five-case malformed-response gate in Test Strategy §7,
including `GATEWAY_COST_MISSING`, is therefore a CORE response-contract gate even though
normalization and amortization depth belong to COST-OBS.

The existing normalized response fields from LLD §6 (`status`, `generated_patch`,
`gateway_request_id`, `provider`, and `cache_hit`) are an agent-side helper output shape, not a
second wire envelope. The CORE wire contract remains the current nested `gateway_usage` object;
the LLD helper's flat fields must not be interpreted as a requirement to add duplicate top-level
usage fields. Any additional route-specific fields are additive.

### 5. Observability ingress boundary

`POST /v1/observability/traces` requires the same bearer authentication and a JSON object with an
`events` array. Each event is a structured JSON object. The route does not execute event content,
follow URLs, accept provider credentials, or promote event fields to policy. It acknowledges
validated ingress with a plain acknowledgement containing `status: "accepted"` and a
`gateway_request_id`. The acknowledgement carries no `gateway_usage`, `billing_units`, or
`cost_usd` claim. Do not substitute zero, placeholder, or estimated cost; observability usage and
cost accounting arrive with COST-OBS. Acceptance means the Gateway accepted the structured event
ingress, not that downstream LangSmith export or cost accounting has completed.

Validation failures still fail closed with a sanitized structured error. LangSmith service-key
injection and the canonical downstream export path remain server-side and are not exposed to the
local agent.

### 6. R3 envelope guardrails

The following three rules are mandatory CORE design constraints:

1. The known model fields are strict, but unknown top-level request keys and unknown `metadata`
   keys are tolerated. The validator must implement the do-not-mix rule without closing the entire
   envelope.
2. `metadata` is reserved as the identity/context channel. Existing `run_id`/`session_id` flow is
   preserved; `execution_mode`/`org_id`/`project_id` are documented as additive TOOLS context, not
   CORE authorization inputs.
3. The explicit non-goal is: *Plan 11.1 performs no server-side model-permission or Plan-mode
   revalidation; that is `P11-FEAT-GATEWAY-TOOLS`.*

### 7. Authentication, origins, and secrets

- The local agent sends one bearer credential and `Content-Type: application/json`.
- The Gateway verifies the bearer through the existing constant-time `authorize_bearer` path
  against its one configured shared value.
- Provider keys are read only by Gateway-side configuration and upstream adapters. They are never
  returned in response bodies, errors, logs, metadata, or usage fields.
- `OptimusGatewaySettings` continues to enforce built-in trusted origins, signed tenant-profile
  origins, non-production loopback handling, and production rejection of extra origins.
- `GatewayServiceConfig` remains loopback-bound and rejects non-loopback bind hosts.
- CORE does not add org/project lookup, wallet mapping, budget state, or server-side tool policy.

### 8. Retry and error policy

The retry predicate is narrow and explicit: timeout exceptions and the existing
`OptimusToolErrorCode.PROVIDER_ERROR` / `TIMEOUT_ERROR` faults may retry, with the existing
four-attempt ceiling and `reraise=True`. Each retry records `retry_count`. Authentication failures,
JSON/schema failures, mixed-shape requests, unsupported models, missing pricing, malformed usage,
and other permanent faults return structured errors without retry. Error bodies are sanitized and
never contain provider keys or raw upstream secrets.

## Verification design

### Unit and route tests

- Validate both request shapes, the two mixed-shape rejection directions, unknown top-level-key
  tolerance, and unknown metadata-key tolerance.
- Validate `/v1/responses`, `/v1/chat/completions`, and `/v1/observability/traces` dispatch through
  the real server handler with a deterministic fake upstream/observability adapter.
- Validate missing/wrong bearer behavior, malformed JSON, non-object bodies, missing known fields,
  unknown-route 404, and provider-error sanitization.
- Validate the response-usage contract and the five malformed-response cases, including null
  `cost_usd` and `GATEWAY_COST_MISSING`.
- Validate retry classification, four-attempt ceiling, `reraise=True`, and retry telemetry.
- Validate origin/secrets behavior using the existing settings tests, including production-mode
  extra-origin rejection and non-production loopback acceptance.

### Real-dependency evidence

The implementation plan must produce a real-process HTTP artifact for all three CORE routes before
claiming route completion. Model-provider live evidence uses the named real Gateway/provider tier
when available; fake upstreams are limited to unit tests. The route-first sequence must ensure that
no later task claims evidence from a route that is still a 404. ACP protocol evidence is not part
of this Gateway plan; if a future ACP tier is added, it must use the independently authored `acpx`
client.

### Release gates

- Start the local agent with only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` resolvable locally;
  provider keys remain server-side.
- Verify all CORE route requests use the Gateway origin and no direct provider host is contacted.
- Verify malformed usage fails closed before generated content is applied or ledger state is
  persisted.
- Verify no budget enforcement is claimed or tested as an implemented CORE behavior.
- Run affected tests, the repository default suite, aggregate coverage at the 80% threshold, Ruff,
  and `git diff --check` before implementation sign-off.

### Requirement traceability self-check

Every CORE success-path requirement must trace to a committed inventory row or an explicitly named
existing contract seam. A new success-path usage/cost claim without inventory custody is scope
creep and must be rejected. Conversely, every CORE inventory row cited by this design must map to
an executable test or evidence target. Apply the same check to TOOLS and COST-OBS at their later
pickup.

## File responsibility map

| File or surface | CORE responsibility |
|---|---|
| `src/optimus_gateway/server.py` | Route dispatch for the three CORE endpoints; preserve 404 for TOOLS paths. |
| `src/optimus_gateway/models.py` | Server configuration/auth and request/response contract models. |
| `src/optimus_gateway/responses.py` | Responses validation, provider routing, retry/error seam, and usage envelope. |
| `src/optimus_gateway/chat_completions.py` (or an equivalent existing module) | Chat-shape validation and OpenAI-compatible response shaping; no new module is required if an existing seam is preferable. |
| `src/optimus_gateway/observability.py` (or an equivalent existing module) | Structured event ingress and adapter boundary; no LangSmith pricing redesign. |
| `src/optimus/gateway/models.py` | Preserve client payload/usage parsing and open metadata behavior. |
| `src/optimus/config/gateway.py` | Preserve origin and local-provider-secret rejection behavior. |
| `src/optimus_gateway/server.py` tests | Real-process route dispatch/auth evidence. |
| `tests/unit/optimus_gateway/` | Unit coverage for shapes, routing, envelopes, retry/error, and observability ingress. |
| `docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md` | Committed requirement and custody baseline; no silent scope expansion. |

## Definition of Done for the frozen implementation plan

- The three CORE routes are served by the local Gateway process, while `/v1/tools/*` remains
  explicitly outside CORE.
- Both model wire shapes are independently validated and the two do-not-mix directions are
  rejected; unknown top-level and metadata keys remain tolerated.
- `metadata` is documented as the identity/context channel, and the CORE non-goal for model/
  Plan-mode policy revalidation is explicit.
- Provider credentials remain server-side; the one-key agent boundary and origin trust behavior
  are preserved.
- Retry classification, response envelope validation, non-null `cost_usd`, and fail-closed
  malformed-response behavior are covered by executable tests and route evidence.
- `/v1/observability/traces` is no longer a 404 and has validated structured-event ingress with a
  plain accepted acknowledgement containing `gateway_request_id` and no usage or cost claim;
  LangSmith export and normalization/amortization depth remain COST-OBS.
- No budget enforcement is implemented or claimed; all budget rows retain the parked operator
  decision.
- The implementation plan is frozen with a SHA-256 approval record before source/test mutation.
