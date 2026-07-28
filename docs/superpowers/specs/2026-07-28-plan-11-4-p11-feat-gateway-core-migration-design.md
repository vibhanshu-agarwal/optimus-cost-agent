# Plan 11.4: P11-FEAT-GATEWAY-CORE Migration Design Specification

**Status:** Reviewer-agent and operator approved; implementation remains unauthorized until an execution decision and the plan's verification gates.

**Stable feature:** `P11-FEAT-GATEWAY-CORE`. Plan 11.1 delivered the initial Gateway route
surface. Plan 11.4 is the migration follow-up that completes the already-ratified local-first
Gateway boundary and transport. It does not reopen the architecture and it does not absorb the
`P11-FEAT-GATEWAY-TOOLS` or `P11-FEAT-GATEWAY-COST-OBS` feature identities.

**Plan number:** 11.4, confirmed free at pickup. The branch is
`agent/codex/plan-11-4-gateway-core`, based on `origin/main` at `8b9486d950b9bf74dc5149ff7e2dc9c957b2593d`.

**Implementation boundary:** This document is the design-spec deliverable only. No source or test
mutation, implementation plan, PDF regeneration, commit, or release claim is authorized by this
specification. The implementation plan may be written only after this design is reviewed and
approved.

## 1. Frozen authoritative source set

The design is an implementation migration against the merged documents and the committed
requirement inventory. It does not invent a new provider, trust model, wallet, search contract, or
observability allocation model.

| Source | SHA-256 / identity | Use in this spec |
|---|---|---|
| HLD v2.16 | `docs/Optimus-Cost-Agent-Architecture-v2.16.pdf`; `6C2C98FE2327A6C466CAD3EB1800335EB59F0E1F65B2CB8E1E3401D7CFA05801` | §§5A, 11, 11A boundary, aggregator, accounting, and credential custody |
| LLD v2.39 | `docs/Optimus-Cost-Agent-LLD-v2.39.pdf`; `82513729FD1A6E87FAD310DD90A18C996981B68024204E56CCA65377495585DE` | §§0, 0.A, 6, 6.1, and 9C settings/transport requirements |
| Test Strategy v1.5 | `docs/Optimus-Cost-Agent-Test-Strategy-v1.5.pdf`; `F3D744EC175B1E18E8B1E4E271997A0BB12666CC33CA7154A40BF5298588DA8D` | §7 settings, §7.1 egress/failure behavior, and release evidence |
| Deep requirement inventory | `docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md`; `C0C9DF817473D480005D342C5EE926FA6307100F6A1D13AFB2396024EEF08AA0` | Exact acceptance-custody rows and evidence aliases |
| Approved aggregator design note | `docs/superpowers/specs/2026-07-27-local-gateway-aggregator-architecture-design.md`; `965A46BEDB3CE01CAE7C9ECD18BC265BCE266C481254F634EDC826C7AEEC37F8` | Settled migration findings, OpenRouter transport, provider accounting, and Vercel disposition |

The inventory's 54 Tier 1 rows are the acceptance baseline: HLD §5A (8), HLD §11 (10), HLD §11A
(5), LLD §0 (3), LLD §0.A (3), LLD §6 plus §6.1 (11), LLD §9C settings/origin trust (5), and Test
Strategy §7 (9). The inventory remains the row-level source of truth; this section records how
Plan 11.4 handles each row group without copying or drifting its normative text.

| Inventory row group | Plan 11.4 disposition |
|---|---|
| HLD §5A, rows 1-3 and 5-6 | Implement the two-variable agent boundary, Gateway-owned aggregator credential, OpenRouter default, one-key/one-ledger boundary, and the no-hosted-service exclusions. |
| HLD §5A, rows 4, 7-8 | Preserve as cross-lane contracts. Provider-reported cost is consumed by the transport here; full ledger normalization and observability/search behavior remain owned by COST-OBS/TOOLS. No search or Phoenix implementation is added. |
| HLD §11, rows 1-5 and 10 | Implement the deterministic loopback process, shared secret, surviving aggregator transport, alias routing, and process-scoped configuration boundary. |
| HLD §11, rows 6-9 | Preserve the validated GatewayUsage handoff and cross-lane responsibility. Plan 11.4 supplies the provider fields required by the wire contract; it does not implement current-run budget policy, typed tools, OTel export, or ledger persistence. |
| HLD §11A, all 5 rows | Explicit COST-OBS exception. The existing structured trace ingress route remains compatible; OTel/OTLP-to-Phoenix mapping, redaction depth, and observability field migration are not changed here. |
| LLD §0 and §0.A, all 6 rows | Implement the local loopback control plane, OpenRouter-owned credential, absence of hosted/tenant/Vault seams, and direct-adapter retirement. |
| LLD §6, rows 1-8 | Implement shared-secret routing, alias resolution, OpenRouter default, distinct request shapes, and bounded model retries. |
| LLD §6, row 9 (`P11-FEAT-GATEWAY-COST-OBS`) | CORE implements the request-path fail-closed enforcement for provider-reported usage/cost; COST-OBS retains custody of settled-usage reconciliation, persistence, and release evidence. |
| LLD §6.1, row 10 | Implement the sole OpenAI-compatible transport and permissive parser for provider/model/cache metadata. |
| LLD §6.1, row 11 (`P11-FEAT-GATEWAY-COST-OBS`) | CORE validates and rejects malformed provider accounting at the request path; COST-OBS owns the settled `GatewayUsage`/ledger contract and reconciliation evidence. |
| LLD §9C settings/origin trust, all 5 rows | Implement construction-time strict-loopback validation and remove every hosted-origin, production-mode, extra-origin, signed-tenant-profile, and non-loopback seam. |
| Test Strategy §7, rows 1-5 | Implement and verify strict-loopback settings, secret masking, the two distinct completion shapes, and mixed-shape rejection. |
| Test Strategy §7, row 6 | Explicit TOOLS exception. Real policy-violation requests remain a TOOLS evidence gate and are not reimplemented in Plan 11.4. |
| Test Strategy §7, rows 7-8 | Implement aggregator provider/model attribution, agent/Gateway egress separation, and bounded retry behavior. |
| Test Strategy §7, row 9 (`P11-FEAT-GATEWAY-COST-OBS`) | CORE supplies the permanent-failure/no-retry enforcement mechanism; COST-OBS owns the provider usage/cost evidence and settled-usage reconciliation. |

The row counts above are a custody map, not a second acceptance list. Each implementation task must
cite the exact inventory rows it executes and produce the named E1-E9 evidence appropriate to that
row.

## 2. Goal

Complete the Gateway-core migration so Phase 1 has one local trust boundary and one surviving model
transport:

- the agent-facing Gateway settings accept only strict loopback URLs and a local shared secret;
- the agent process has no hosted-origin, tenant-profile, production-mode, or non-loopback override;
- OpenRouter is the sole Phase 1 aggregator endpoint after the bounded Vercel check is recorded as
  backlogged;
- both `/v1/responses` (`input`) and `/v1/chat/completions` (`messages`) converge on the same
  OpenAI-compatible transport without mixing their wire shapes;
- provider-reported usage, cost, cache state, resolved model, and provider identity are parsed and
  retained when returned, with provider-reported cost authoritative;
- missing, null, negative, non-finite, or malformed provider accounting fails closed before a model
  success is accepted or downstream usage is recorded;
- the direct Anthropic branch and compatibility re-export are retired together with the direct
  provider-selection/configuration surfaces that make that branch reachable; and
- model retries follow the merged LLD/Test Strategy contract of at most three attempts for
  transient upstream faults, with retry evidence carrying attempt, classification, latency, and
  disposition.

The Gateway remains a developer-run loopback process. It is not a hosted Optimus service, tenant
control plane, subscription product, OAuth/device-flow service, Vault, public Gateway, or wallet.

## 3. Explicit scope boundary

### In scope

- `OptimusGatewaySettings` strict-loopback completion and secret redaction.
- Retirement of `production_mode`, built-in hosted origins, `extra_trusted_origins`, signed tenant
  profile origins, `ProviderKeyPolicy.IGNORE`, and the legacy environment propagation that gives
  those concepts meaning.
- OpenRouter-default Gateway configuration and the single OpenAI-compatible upstream transport.
- Removal of direct OpenAI/Anthropic provider selection from the Phase 1 model path; OpenRouter
  model aliases remain the agent policy input.
- OpenAI-compatible response parsing for message text, request identity, aggregator/provider/model
  attribution, token and cache detail, and provider-reported cost.
- GatewayUsage fields needed to carry provider-reported accounting without fabricating local cost.
- Model-route retry classification and the three-attempt ceiling. Existing typed-tool retry
  behavior remains a TOOLS concern and must not be changed accidentally.
- Unit, contract, real local-process, live Gateway, credential, and egress evidence for the above.
- A time-boxed Vercel Python transport check whose only accepted success outcome would be a second
  endpoint requiring base URL, credential, model-name, and response-accounting mapping changes.

### Explicit exceptions and named custody

- **`P11-FEAT-GATEWAY-TOOLS`:** deterministic search, direct extract, Tavily rollback/deletion,
  package/advisory capability availability, tool policy, provenance, and tool-call accounting are
  not implemented or redesigned here. The model transport remains reusable by that lane.
- **`P11-FEAT-GATEWAY-COST-OBS`:** OTel/OTLP export to Phoenix, observability redaction/mapping,
  the separate USD field rename, ledger normalization/amortization, and full ProviderUsage schema
  migration are not implemented here. For the three explicitly COST-OBS-tagged request-path rows
  in LLD §6/§6.1 and Test Strategy §7, CORE implements only the parser validation and fail-closed
  enforcement needed before model success; COST-OBS retains ownership of settled usage/cost
  reconciliation, persistence, schema migration, and release evidence. Plan 11.4 emits the
  provider fields needed by that lane and preserves existing optional compatibility fields.
- **`P9.85-FU-3`:** no cross-run or cross-session spend ceiling is designed or implemented. Current
  run budget authority remains a named future budget-governance lane.
- **`P11-FEAT-GATEWAY-MCP`, `P11-FU-2`, registry, Zed-resume, and Windows-flake entries:** no
  implementation or source-document reinterpretation is included.
- **Vercel:** the bounded check is complete as a design decision: Vercel is **backlogged under the
  existing `P11-FEAT-GATEWAY-CORE` migration custody**. Its public OpenAI-compatible transport
  documents base URL, API key, model, Chat Completions, and Responses support, but do not document
  the mandatory per-response provider cost/accounting fields needed by the settled GatewayUsage
  contract. Adding provider-specific reporting/correlation or non-trivial response translation
  would exceed the approved modest Python integration. No Vercel endpoint is added in Plan 11.4,
  and no comparison matrix is produced.
- No source redline, PDF rebuild, MCP diagram, hosted service, new credential, or direct agent
  egress is introduced.

## 4. Current verified violations and migration decisions

These are verified current-tree findings from the pre-spec review. They ground the design; the
implementation plan must re-derive the final diff and must not treat this list as a substitute for
that check.

### 4.1 Trust boundary

`src/optimus/config/gateway.py` still contains:

- `BUILT_IN_TRUSTED_GATEWAY_ORIGINS = {"https://gateway.optimus.ai"}`;
- `production_mode=True` as the default;
- `extra_trusted_origins` and `signed_tenant_profile_origins` fields;
- `ProviderKeyPolicy.IGNORE`; and
- `validate_trusted_gateway()` logic that treats loopback HTTP as a non-production exception.

The migration makes loopback the only accepted origin in the settings model itself. The model keeps
the existing callable `validate_trusted_gateway()` as an idempotent defense-in-depth invariant so
`GatewayClient` and existing callers do not gain a new unvalidated path; construction-time
validation becomes authoritative, and the old hosted/production/tenant/extra-origin inputs are
deleted rather than reinterpreted. This preserves low-drift call sites while removing the trust
seams.

The class default becomes `http://127.0.0.1:8765` and `optimus_api_key` remains a masked
`SecretStr`. Validation uses safe URL parsing and fails closed for non-HTTP(S), userinfo, malformed
or ambiguous hosts, and every hostname other than `127.0.0.1`, `localhost`, or `::1`. No field or
environment variable can authorize a non-loopback origin.

The launch path removes the `OPTIMUS_PRODUCTION_MODE` default injection and the legacy
`OPTIMUS_EXTRA_GATEWAY_ORIGINS`/production-mode propagation. `OPTIMUS_GATEWAY_URL` and
`OPTIMUS_API_KEY` remain the agent-facing Gateway credential surface; provider and Gateway-only
secrets remain out of the agent environment. `validate_no_local_provider_keys()` always rejects
local provider keys; the ignore policy is not retained as a compatibility escape hatch.

### 4.2 Aggregator transport and direct-adapter retirement

`src/optimus_gateway/providers.py` still branches to `UrllibAnthropicClient`, while
`src/optimus_gateway/anthropic_client.py` re-exports that direct adapter. The current
`GatewayServiceConfig`, model mapping, launch credential resolver, child manifest URL resolver, and
tests also expose `anthropic` and direct `openai` choices.

The migration has one transport path:

```text
agent /v1/responses (input)              \
                                          > shared completion service
agent /v1/chat/completions (messages)    /
                                                  |
                                                  v
                                     UrllibOpenAICompatibleClient
                                                  |
                                                  v
                                       OpenRouter /v1/chat/completions
```

`build_upstream_client()` constructs only `UrllibOpenAICompatibleClient`. The Anthropic branch,
`UrllibAnthropicClient`, `parse_anthropic_message`, the compatibility module, direct-provider model
aliases, Anthropic-native credential projection, and direct OpenAI provider selection are retired
together. `GatewayServiceConfig` defaults to and accepts the OpenRouter aggregator configuration;
tool-only configuration remains intact for the TOOLS lane.

The surviving client posts the OpenAI-compatible payload with the Gateway-owned credential and
requests OpenRouter routing metadata (`X-OpenRouter-Metadata: enabled`) so a successful response can
retain actual provider/model attribution when available. The HTTP transport must retain response
headers as well as the decoded body so OpenRouter cache status (`X-OpenRouter-Cache-Status: HIT|MISS`)
and cache age/TTL can be represented without guessing. Unknown additive metadata is preserved as
opaque data or ignored safely; it is never promoted to policy.

### 4.3 Provider-reported accounting

The current `src/optimus_gateway/responses.py` looks up a local static price table before dispatch,
then calculates `cost_usd` from token counts and emits `cache_hit=False`. The current upstream
parser returns only text, request ID, and prompt/completion token counts.

The new `ProviderMessageResult`/equivalent normalized result carries, at minimum:

- the upstream request/generation ID;
- aggregator identity (`openrouter`) and actual resolved provider when returned;
- requested alias and returned resolved model/version when returned;
- prompt, completion, total, reasoning, and cached token detail when returned;
- cache status/details from the provider response headers or documented body fields; and
- provider/aggregator-reported `usage.cost` normalized as a non-negative finite Decimal.

`GatewayUsage.provider` remains the billing/aggregator identity required by the current wire and
ledger contracts; a separate optional resolved-provider field carries the actual selected provider
when the aggregator returns it. A cache hit may omit router metadata, as documented by OpenRouter,
but must still carry the explicit cache status and generation identity. The implementation must not
pretend that an absent actual-provider field identifies a provider.

`billing_units` comes from the provider-reported total/billing-unit field when present. Summing local
token counters is not a substitute for a provider-reported billing unit. Missing, null, negative,
non-finite, malformed, or type-invalid cost/usage is a permanent malformed-upstream failure. The
Gateway rejects the response before emitting model output as a successful response or recording a
settled usage entry.

The local `MODEL_RATES` success-path dependency and `compute_cost_usd()` calculation are removed.
No local estimate overwrites or fabricates settled cost. If a diagnostic price snapshot is retained
for comparison, it is explicitly labelled diagnostic metadata, excluded from the GatewayUsage
settled `cost_usd`, and never used as a missing-cost fallback. The separate `price_snapshot_id` and
legacy credit/USD field migration remains COST-OBS custody.

### 4.4 Retry policy

The current model helper allows four attempts and reports only an integer retry callback. Plan 11.4
sets the model completion call to at most three total attempts. Transient network, timeout,
rate-limit, and provider-availability faults may retry; authentication, schema, policy, unsupported
model, malformed JSON, and malformed usage/cost faults do not retry. Every retry record includes:

- 1-based attempt number;
- failure classification;
- measured latency for the failed attempt;
- whether the next action was retry, terminal failure, or escalation; and
- sanitized error context with no credential value.

The shared retry helper receives an explicit per-call attempt limit so existing typed-tool callers
retain their separately owned behavior. Plan 11.4 changes only the model completion path and its
evidence.

## 5. Component and file responsibility map

The implementation plan must re-derive this map before task checkboxes are frozen. The listed
production files are mutation candidates; the listed tests are regression/evidence surfaces, not a
claim that every file must change.

| Surface | Plan 11.4 responsibility |
|---|---|
| `src/optimus/config/gateway.py` | Replace trust model with construction-time strict loopback, remove hosted/production/tenant/extra-origin fields and ignore policy, retain constant-time auth and secret masking. |
| `src/optimus/config/__init__.py` | Retire exports for hosted-origin and ignore-policy surfaces; preserve the public settings/key-violation exports that remain valid. |
| `src/optimus/acp/local_infra.py` | Remove production-mode default injection; preserve separate Gateway-child credential construction and loopback bind controls. |
| `src/optimus/acp/subprocess_env.py` | Remove special production-mode handling and ensure only the approved agent environment projection survives. |
| `src/optimus/acp/launch_policy.py` | Remove legacy production/extra-origin policy registrations and direct-provider credential branches; retain Gateway-child secret and egress policy. |
| `src/optimus/acp/local_gateway_secrets.py` | Resolve only the OpenRouter aggregator credential through the generic Gateway provider-key name; remove Anthropic-native key selection. |
| `src/optimus/acp/launch_gate.py` and `launch_approval_cli.py` | Display/approve the generic Gateway aggregator credential and signed base URL without a direct-provider branch. |
| `src/optimus_security/launch_manifest.py` | Make effective base URL resolution consistent with the surviving OpenRouter-compatible endpoint; remove Anthropic special casing. |
| `src/optimus_gateway/models.py` | Restrict Phase 1 model provider configuration to the approved aggregator and preserve distinct request-shape validators/tool configuration. |
| `src/optimus_gateway/model_mapping.py` | Keep OpenRouter alias and plausible-model rules; retire direct OpenAI/Anthropic mappings. |
| `src/optimus_gateway/providers.py` | Construct only `UrllibOpenAICompatibleClient`; leave tool dependency ownership to TOOLS. |
| `src/optimus_gateway/upstream_client.py` | Expand the normalized result, retain response headers, parse provider/model/cache/accounting metadata, and apply the model retry ceiling. |
| `src/optimus_gateway/anthropic_client.py` | Delete the compatibility re-export with the Anthropic branch as one retirement. |
| `src/optimus_gateway/pricing.py` and `responses.py` | Remove settled-cost calculation from the request path; build GatewayUsage from provider-reported fields and fail closed on malformed accounting. |
| `src/optimus/gateway/models.py` | Extend the optional wire envelope only for provider-reported attribution/detail needed by the new transport; preserve existing client parsing and legacy compatibility fields owned by COST-OBS. |
| `src/optimus/gateway/client.py`, `src/optimus/acp/bootstrap.py`, `src/optimus/acp/preflight.py`, `src/optimus/telemetry/observability.py` | Regression surfaces for settings construction, per-call trust checks, Gateway route use, and secret redaction; no OTel/Phoenix redesign. |
| `README.md`, `.env.example`, `.env.gateway.example` | Remove hosted-origin, production-mode, direct-provider, and Anthropic-native runtime examples; document the local OpenRouter-owned Gateway credential boundary. |
| `tests/unit/config/`, `tests/unit/acp/`, `tests/unit/gateway/`, `tests/unit/optimus_gateway/`, `tests/unit/telemetry/`, `tests/unit/release/` | TDD coverage for trust, environment projection, adapter retirement, parser/accounting, retries, client behavior, and redaction. |
| `tests/integration/optimus_gateway/test_gateway_live_smoke.py`, `gateway_env.py`, `tests/integration/gateway/` | Real-process and real-credential evidence for both model shapes, provider/accounting fields, malformed-cost failure, and one-key boundary. |

The following are intentionally not mutation targets for this spec: `src/optimus_gateway/tool_*`,
tool route behavior, OTel exporter implementation, Phoenix integration, and the separate USD field
rename. They may require compatibility test updates only when the core wire contract changes, and
any such update must remain additive and be attributed to the owning lane.

## 6. Alternatives considered

### A. One OpenRouter-compatible transport with provider-reported accounting — selected

It matches HLD/LLD §5A/§6/§6.1, preserves one Gateway credential and one agent-facing model
contract, and makes the provider response—not a stale local table—the source of settled cost. The
transport can retain OpenRouter routing and cache metadata without exposing the upstream credential
or URL to the agent.

### B. Keep direct adapters and normalize them behind a common facade — rejected

This preserves the current Anthropic branch and direct-provider credential paths, contradicts the
merged LLD requirement that direct single-provider adapters are removed, and leaves two accounting
semantics to reconcile. It also keeps a trust boundary the corrected architecture explicitly
removed.

### C. Keep the local price table as a fallback when provider cost is absent — rejected

It would fabricate a release-grade value precisely when the provider response is incomplete, making
budget and ledger evidence non-authoritative. Diagnostic comparison metadata is allowed only when
it is clearly labelled and never substitutes for provider-reported cost.

### D. Retain Vercel as a second endpoint in this plan — rejected after bounded check

The official Vercel material confirms a Python/OpenAI-compatible base URL and one-key model access,
but the reviewed public transport contract does not provide the mandatory per-response provider cost
and accounting fields. Adding a second reporting/correlation path or non-trivial translation would
not be a modest transport check. The item remains backlogged under the existing CORE migration
custody for a separately approved design.

## 7. Error, security, and data-handling rules

- Validate the agent bearer before provider dispatch and never echo upstream credentials, raw
  authorization headers, or untrusted provider metadata in errors, logs, responses, or telemetry.
- Treat provider response bodies, headers, annotations, and metadata as untrusted data. Parse typed
  fields only; ignore unknown additive fields; never execute or promote content to policy.
- Treat malformed provider accounting as permanent. Do not retry it, return a successful model
  envelope, apply partial output, or persist a settled usage record.
- Preserve `gateway_request_id`, provider/aggregator identity, optional resolved provider/model,
  provider request ID, cache status, billing units, cost, and run/session correlation for downstream
  accounting. Do not add a second direct-provider cost path.
- Keep the agent egress limited to the loopback Gateway. The Gateway egress remains the configured
  OpenRouter endpoint plus the already-owned tool/Redis/OTLP destinations; no Vercel or direct
  Anthropic/OpenAI endpoint is added.
- Preserve the existing Gateway server's typed route shapes and independent tool-route ownership.
  A model transport migration must not make Tavily configuration a prerequisite for package/advisory
  routes.

## 8. Verification and evidence design

### Unit and contract evidence

- Settings: default loopback, `localhost`, `::1`, HTTP(S), userinfo rejection, ambiguous/malformed
  host rejection, non-loopback rejection, no legacy override field, and secret masking across repr,
  serialization, logs, telemetry, and child state.
- Environment/launch: no production-mode or extra-origin projection; no direct-provider key branch;
  generic Gateway provider key stays Gateway-child-only; signed manifest binds the configured
  OpenRouter base URL and credential.
- Shape/routing: `/v1/responses` accepts only `input`, `/v1/chat/completions` accepts only
  `messages`, mixed shapes fail before upstream dispatch, and both use one upstream client.
- Parser: provider request ID, aggregator/actual-provider attribution, model/version, token/cache
  detail, explicit header cache status, and provider cost are retained; unknown additive metadata is
  harmless.
- Accounting: provider cost is preferred over any diagnostic snapshot; absent, null, negative,
  non-finite, malformed, and type-invalid cost fail closed; provider-reported billing units are not
  recomputed locally.
- Retry: transient faults retry within three total model attempts with per-attempt evidence;
  permanent authentication/schema/policy/usage faults do not retry.
- Retirement: no import, branch, alias, credential resolver, or test fixture can select the direct
  Anthropic adapter; no direct OpenAI model path remains in the Gateway provider selector.

### Real-process and live evidence

The implementation plan must produce these artifacts with the named dependencies:

| Claim | Required evidence |
|---|---|
| E1 one-key release | Real Plan/Agent process and child-environment scan with only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` in the agent-facing Gateway credential surface; no provider key resolvable by the agent. |
| E2 route/schema | Unit/contract plus real local-process evidence for both completion routes, shared transport, provider/model attribution, and validated GatewayUsage. |
| E4 ledger/accounting | Real provider response or approved `requires_gateway` evidence proving provider cost is settled, malformed cost fails closed, and no local estimate replaces it. Full persistence reconciliation remains COST-OBS. |
| E6 retry | Unit and Gateway-tier failure injection proving transient-only retries, three-attempt cap, permanent-failure abort, and attempt telemetry. |
| E7 origin/secrets | Strict-loopback settings, credential redaction, process-scoped environment, and egress scan; WSL2 same-namespace evidence remains a release gate. |
| E9 coverage/release | Narrow affected tests, full repository suite as approved by the implementation plan, aggregate coverage at or above 80%, Ruff, and `git diff --check`. |

Fake upstreams are permitted only for unit/contract tests. `requires_gateway` evidence uses the real
loopback Gateway and approved credentials; the real ACP protocol tier, if later invoked, uses the
independently authored `acpx` client, not a project-authored ACP harness.

### Re-derived regression surfaces

The following search-derived surfaces must be rechecked in the implementation plan before tests are
edited: `src/optimus/config/gateway.py`, `src/optimus/config/__init__.py`,
`src/optimus/acp/local_infra.py`, `src/optimus/acp/subprocess_env.py`,
`src/optimus/acp/launch_policy.py`, `src/optimus/acp/local_gateway_secrets.py`,
`src/optimus/acp/launch_gate.py`, `src/optimus_security/launch_manifest.py`,
`src/optimus/gateway/client.py`,
`src/optimus_gateway/models.py`, `model_mapping.py`, `providers.py`, `upstream_client.py`,
`anthropic_client.py`, `pricing.py`, `responses.py`, and the environment/docs surfaces. Regression
tests include the settings, ACP launch/preflight/wiring, Gateway client, telemetry exporter,
release credential, upstream, provider, response, retry, server, and live-smoke suites named in the
responsibility map. No numeric blast-radius claim is made until the implementation plan records a
fresh `rg`/AST inventory that can be rerun.

## 9. Definition of Done for this design spec

- The document cites the merged HLD v2.16, LLD v2.39, Test Strategy v1.5, approved aggregator note,
  and exact inventory baseline.
- The 54 inventory rows are partitioned by their existing ownership; TOOLS, COST-OBS, and budget
  exceptions are explicit and named.
- The strict-loopback, OpenRouter-only, provider-accounting, direct-adapter-retirement, retry, and
  Vercel decisions are concrete enough for a task-by-task TDD implementation plan.
- The bounded Vercel outcome is one outcome—backlogged under `P11-FEAT-GATEWAY-CORE` for the
  provider-accounting compatibility gap—not a comparison matrix or an unowned exclusion.
- The file passes self-review for placeholders, contradictions, ambiguous authority, and scope
  drift. User/operator review is required before invoking the writing-plans skill.

## 10. Approval record

Reviewer-agent approval was recorded on 2026-07-28T09:02:51Z after the three-row COST-OBS custody
addendum was independently verified. Operator approval was explicitly recorded on 2026-07-28T09:04:49Z
from Vibhanshu with the message `[Vibhanshu] Approved`. This approval authorizes the separate Plan
11.4 implementation plan with TDD task checkboxes, a fresh blast-radius inventory, named evidence
artifacts, and the required checkpoint cadence. It does not itself authorize source/test mutation,
commit, push, or release activity; those require the execution decision and the plan's verification
gates.
