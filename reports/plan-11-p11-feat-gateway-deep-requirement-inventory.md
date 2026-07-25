# P11-FEAT-GATEWAY Deep Requirement Inventory

**Status:** Read-only extraction report; not a Gateway specification and not implementation authority.

**Baseline reviewed:** `origin/main` at `b5fdc65515410719bd03648ea3224bc7e2a9c07d`.

**Working branch:** `agent/codex/p11-authoritative-doc-map` (clean before this report was added).

## Source pin verification

The four source bytes were re-hashed before extraction. All four values match the section map:

| Source | SHA-256 | Result |
|---|---|---|
| `docs/Optimus-Cost-Agent-Architecture-v2.15.pdf` | `A386EEE8463A169A20A18B59BA923CFA80C0F6707DF7FEA3DB91B83FE3386C0B` | Match |
| `docs/Optimus-Cost-Agent-LLD-v2.38.pdf` | `0471DCAE8100F41340AD6F3FE30F19B7CA8042C2949A534973B2A8D9564944DB` | Match |
| `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.0.pdf` | `4669940B34C8C0CAAB5501C193213C3087C45FAE0CBA3011E1DBF87EB74B4D0C` | Match |
| `docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf` | `6F7EB2B48447F1CE3D882FC60E16DA8B41C1DD7C926C359F45185823492DA5DB` | Match |

The map file still carries its historical `Baseline: origin/main at 5229036` prose. That metadata is stale relative to the handoff, but the source digests are unchanged and valid; extraction continued.

## Disposition and evidence conventions

Each row below uses the requested shape. A row may contain several adjacent source sentences when they form one independently testable contract; the wording inside the **Normative statement** column is source wording, not a paraphrase.

Evidence aliases expand to named artifacts:

- **E1 one-key release:** `tests/integration/release/test_phase1_release_gate_cli.py`, `tests/integration/gateway/test_gateway_live.py`, and the Phase 1 real-gateway release artifact.
- **E2 route/schema:** `tests/unit/gateway/test_client.py`, `tests/unit/gateway/test_models.py`, `tests/unit/optimus_gateway/test_server.py`, plus a new P11 route/schema integration target for the added shapes.
- **E3 evidence wrappers:** `tests/unit/evidence/test_acquisition.py`, `tests/unit/evidence/test_gateway_io.py`, `tests/integration/evidence/test_mocked_evidence_flow.py`, plus real-gateway search/extract evidence.
- **E4 ledger:** `tests/unit/usage/test_ledger.py`, `tests/unit/usage/test_accounting.py`, `tests/integration/usage/test_evidence_provider_reconciliation.py`.
- **E5 telemetry:** `tests/unit/telemetry/test_observability.py`, `tests/integration/telemetry/test_usage_telemetry_flow.py`, and `reports/plan-9-95-usage-telemetry-evidence.md`.
- **E6 retry:** `tests/unit/retry/test_policy.py` and `tests/integration/retry/test_gateway_retry_flow.py`.
- **E7 origin/secrets:** `tests/unit/config/test_gateway_settings.py`, `tests/unit/security/test_gateway_base_url_resolution.py`, and the real one-key release scan.
- **E8 policy revalidation:** a direct, real-staging-Gateway integration target covering the §9D checks; fake-only tests are insufficient for the named live tier.
- **E9 coverage/release:** CI `coverage.py` + `pytest-cov` release output and the Phase 1 release-gate artifact.
- **E10 source repair:** repaired authoritative LLD §0.B source or reviewed authoritative replacement, followed by a fresh extraction/digest review.
- **E11 golden tasks:** `tests/fixtures/golden_tasks/phase1_golden_tasks.json` and `tests/integration/agent/test_golden_harness_real_runner.py` against the staging Gateway.
- **E12 budget decision:** the reviewed operator decision and custody record for `P9.85-FU-3`; no Gateway budget-enforcement implementation is authorized by this inventory.

The exact deferred disposition required by the handoff is used for Gateway budget authority rows: **`Deferred → P9.85-FU-3 (parked; operator decision pending)`**.

## Requirement counts

| Tier | Section | Rows | Exhaustion result |
|---|---|---:|---|
| 1 | HLD §5A | 6 | Extracted to exhaustion |
| 1 | HLD §11 | 7 | Extracted to exhaustion |
| 1 | HLD §11A | 5 | Extracted to exhaustion |
| 1 | LLD §0 | 2 | Extracted to exhaustion |
| 1 | LLD §0.A | 9 | Extracted to exhaustion |
| 1 | LLD §0A named endpoint block | 4 | Extracted to exhaustion |
| 1 | LLD §6 | 7 | Extracted to exhaustion |
| 1 | LLD §9D | 7 | Extracted to exhaustion |
| 1 | Guardrails §9 | 6 | Extracted to exhaustion |
| 1 | Test Strategy §7 | 9 | Extracted to exhaustion |
|  | **Tier 1 subtotal** | **62** | **All Tier 1 sections exhausted** |
| 2 | LLD §0.B | 1 | Source defect retained; affected block is unextractable-pending-repair |
| 2 | LLD §0.C | 9 | Extracted to exhaustion; MCP gap explicitly disposed |
| 2 | LLD §0.D | 7 | Extracted to exhaustion; package/security and second shape explicitly disposed |
|  | **Tier 2 subtotal** | **17** | **All Tier 2 sections exhausted** |
| 3 | HLD §6 | 3 | Gateway intersection extracted |
| 3 | HLD §10 | 8 | Gateway intersection extracted, including all four §10.D points |
| 3 | HLD §12 | 2 | Gateway/observability intersection extracted |
| 3 | LLD §9 | 2 | Gateway intersection extracted |
| 3 | LLD §9E | 6 | Gateway/ledger intersection extracted |
| 3 | LLD §10A | 7 | Gateway/cost/trace intersection extracted |
| 3 | LLD §11A | 5 | Gateway coverage/observability intersection extracted |
| 3 | LLD §12 | 1 | Model-touching Gateway boundary extracted |
| 3 | Guardrails §7.2 | 5 | Gateway budget/evidence intersection extracted |
| 3 | Test Strategy §8 | 6 | Gateway accounting intersection extracted |
| 3 | Test Strategy §8A | 5 | Gateway coverage/trace intersection extracted |
| 3 | Test Strategy §9 | 5 | Gateway failure intersection extracted |
| 3 | Test Strategy §10 | 3 | Gateway schema intersection extracted |
| 3 | Test Strategy §13 | 8 | Gateway release intersection extracted |
|  | **Tier 3 subtotal** | **66** | **All requested intersections traced** |
| 4 | HLD §5 | 2 | Preserved as Plan 7 ledger constraints |
| 4 | HLD §8 | 3 | Preserved as Plan 4 evidence/tool constraints |
| 4 | LLD §0.E | 1 | Preserved one-key boundary |
| 4 | LLD §9C | 6 | Preserved Plan 4 wrapper surface |
| 4 | LLD §10 | 3 | Preserved Plan 7 accounting/retention surface |
| 4 | LLD §12C | 3 | Preserved bounded-loop/Gateway evaluator boundary |
|  | **Tier 4 subtotal** | **18** | **All preserve-only constraints traced** |
|  | **Total inventory rows** | **163** | **No blank dispositions** |

## Tier 1 — owned by P11-FEAT-GATEWAY

### HLD v2.15 §5A — 6 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.15 §5A | “The Optimus API key is the only developer-facing credential.”<br>“It maps to an internal tenant/user/project budget wallet.” | In scope | P11-FEAT-GATEWAY | E1, E7 |
| HLD v2.15 §5A | “Upstream provider keys for LLMs, Tavily, LangSmith, and any other vendor are owned by the Optimus Gateway and are never configured locally.” | In scope | P11-FEAT-GATEWAY | E1, E7 |
| HLD v2.15 §5A | “Third-party vendors do not natively consume Optimus credits — each expects its own vendor credential — so the friction-free model is that developers never see those keys”<br>“OPTIMUS_API_KEY authenticates to the Optimus Gateway, and the Gateway owns all downstream provider keys, usage mapping, billing normalization” | In scope | P11-FEAT-GATEWAY | E1, E4 |
| HLD v2.15 §5A | “budget enforcement” | Deferred → P9.85-FU-3 (parked; operator decision pending) | P9.85-FU-3 | E12 |
| HLD v2.15 §5A | “From a cost perspective, OPTIMUS_API_KEY is not a physical upstream key; it is an internal account / wallet key.”<br>“Optimus credits are an internal abstraction over real, heterogeneous vendor costs (LLM tokens, Tavily credits, and trace / observability allocation).”<br>“They do not remove the need for upstream vendor accounts, but they remove the need for every developer to configure and fund them.”<br>“The Gateway converts each provider's native usage into one normalized Optimus ledger.” | In scope | P11-FEAT-GATEWAY | E4 |
| HLD v2.15 §5A | “This preserves the thesis: one key, one budget, one ledger, with many providers behind the curtain.”<br>“Tavily is treated as a first-class Gateway tool and LangSmith as a Gateway-managed observability sink; neither becomes a local developer dependency.” | In scope | P11-FEAT-GATEWAY | E1, E3, E5 |

### HLD v2.15 §11 — 7 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.15 §11 | “The Optimus AI Gateway is Phase 1 mandatory infrastructure. All traffic from the local agent — model completions and every tool call — flows through the gateway from day one. There is no supported configuration in which the local agent calls a provider directly.” | In scope | P11-FEAT-GATEWAY | E1 |
| HLD v2.15 §11 | “The gateway holds all provider credentials server-side in a Vault. The local agent holds only two values: OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY.” | In scope | P11-FEAT-GATEWAY | E1, E7 |
| HLD v2.15 §11 | “Route model completion requests to the correct provider (GLM, Claude Haiku/Sonnet/Opus) based on the model alias in the request.”<br>“Inject provider API keys server-side from Vault; no key is ever transmitted to the local agent.” | In scope | P11-FEAT-GATEWAY | E2, E7 |
| HLD v2.15 §11 | “Record gateway_request_id, provider, cache_hit, billing_units, and cost_usd in every response envelope.” | In scope | P11-FEAT-GATEWAY | E2, E4 |
| HLD v2.15 §11 | “Enforce domain allowlists for web search and extract requests, independent of local agent policy.” | In scope | P11-FEAT-GATEWAY | E3, E8 |
| HLD v2.15 §11 | “Revalidate budgets, call caps, and tool policies server-side as a defence-in-depth layer (Section 9D of LLD).” | Deferred → P9.85-FU-3 (parked; operator decision pending) | P9.85-FU-3 / P11-FEAT-GATEWAY | E8, E12 |
| HLD v2.15 §11 | “Enforce origin allowlist: local agent gateway_url must resolve to a trusted origin; rogue gateway attacks are blocked via production_mode + signed tenant profile.”<br>“Every model completion and tool call follows the same sequence: the local agent sends a single authenticated request to the gateway, which injects provider credentials server-side, forwards to the upstream provider, and returns a unified response envelope containing the model output plus GatewayUsage accounting fields.” | In scope | P11-FEAT-GATEWAY | E1, E2, E7 |

### HLD v2.15 §11A — 5 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.15 §11A | “Phase 1 uses LangSmith for trace observability across planning, gateway calls, tool invocation, validation, retries, and final response generation.” | In scope | P11-FEAT-GATEWAY | E5 |
| HLD v2.15 §11A | “At the architectural level, LangSmith is the trace sink — but its credentials are managed by the Gateway / deployment layer to preserve one-key setup.”<br>“One-key principle. LangSmith — and every other vendor — credential lives in Gateway / deployment secrets, never in local developer config. Local dev requires only OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY.” | In scope | P11-FEAT-GATEWAY | E1, E5, E7 |
| HLD v2.15 §11A | “LangSmith is an observability and production-debugging tool, not a test-coverage tool, and does not contribute to the coverage release gate.” | In scope | P11-FEAT-GATEWAY | E5, E9 |
| HLD v2.15 §11A | “LangSmith cost is recorded the same way as any other provider cost, but the commercial model varies.”<br>“Depending on the plan, the Gateway records either provider-native trace usage (e.g. trace / span / event counts) or an allocated / amortized observability cost where billing is seat- or subscription-based.” | In scope | P11-FEAT-GATEWAY | E4, E5 |
| HLD v2.15 §11A | “In all cases the figure is normalized into the same Optimus ledger as token and tool costs (see §5A; LLD §10A for field-level detail).” | In scope | P11-FEAT-GATEWAY | E4, E5 |

### LLD v2.38 §0 — 2 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §0 | “The Optimus AI Gateway is Phase 1 mandatory infrastructure, not future scope. All traffic from the local agent — model completions and every tool call — flows through the gateway from day one.”<br>“There is no supported configuration in which the local agent calls a provider directly.” | In scope | P11-FEAT-GATEWAY | E1 |
| LLD v2.38 §0 | “Asking every developer to supply a Tavily key, an OpenAI key, and any other provider credential creates credential sprawl and undermines the cost-control story.”<br>“The correct model is single-credential access: the developer authenticates once with Optimus, and the gateway holds all provider credentials server-side in a Vault.” | In scope | P11-FEAT-GATEWAY | E1, E7 |

### LLD v2.38 §0.A — 9 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §0.A | “The control plane is entirely on the gateway side. The local IDE plugin or local Optimus agent only knows two things:” | In scope | P11-FEAT-GATEWAY | E1 |
| LLD v2.38 §0.A | “OPTIMUS_GATEWAY_URL=https://gateway.optimus.ai”<br>“OPTIMUS_API_KEY=opt_live_xxx”<br>“# Or, for IDE integrations:”<br>“# Sign in with Optimus (OAuth / device flow)” | In scope | P11-FEAT-GATEWAY | E1, E7 |
| LLD v2.38 §0.A | “The gateway then maps that credential to the org / user / project context and resolves budgets, allowed tools, provider routes, and backend secrets internally.” | In scope | P11-FEAT-GATEWAY | E2, E8, E12 |
| LLD v2.38 §0.A | “Phase 1 local runtime configuration allows only OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY (or an equivalent OAuth / device-flow session).” | In scope | P11-FEAT-GATEWAY | E1, E7 |
| LLD v2.38 §0.A | “Local TAVILY_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY, and LANGSMITH_API_KEY (and any other provider or observability key) are rejected for Phase 1 runtime use.”<br>“These keys are owned by the Gateway / deployment layer and held server-side in Vault.” | In scope | P11-FEAT-GATEWAY | E1, E7 |
| LLD v2.38 §0.A | “OPTIMUS_API_KEY is not a physical upstream key; it is an internal account / wallet key.”<br>“The Gateway maps it to a tenant / user / project / budget wallet and converts heterogeneous upstream costs into one normalized Optimus ledger.” | In scope | P11-FEAT-GATEWAY / P9.85-FU-3 | E4, E12 |
| LLD v2.38 §0.A | “Provider-native units are not hardcoded in the agent — they are whatever the provider reports, normalized by the Gateway adapter.” | In scope | P11-FEAT-GATEWAY | E4 |
| LLD v2.38 §0.A | “gateway records: provider = openai \| openrouter \| anthropic \| glm \| …; native_unit = tokens; billing_units = input_tokens + output_tokens; cost_usd = price_snapshot(model) applied to usage; optimus_credits_debited = normalized internal charge.”<br>“gateway records: provider = tavily; native_unit = tavily_credits; billing_units = provider-reported Tavily credits, as normalized by the Gateway adapter; cost_usd = gateway-computed from the active price snapshot; optimus_credits_debited = normalized internal charge.” | In scope | P11-FEAT-GATEWAY | E4 |
| LLD v2.38 §0.A | “LangSmith trace: upstream unit depends on the commercial model: • usage-based → trace / span / event counts • seat/subscription → allocated or amortized observability cost”<br>“gateway records native trace usage OR allocated observability cost accordingly; cost_usd is computed or amortized into the same ledger.” | In scope | P11-FEAT-GATEWAY | E4, E5 |

### LLD v2.38 §0A named endpoint block — 4 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §0A named block, p.5 | “The local agent never calls Tavily or LangSmith directly. It calls Gateway-owned adapters; the Gateway injects the server-side vendor key, records usage, normalizes cost, and returns a unified envelope (gateway_request_id, cost_usd, billing_units, cache_hit, citations where applicable).” | In scope | P11-FEAT-GATEWAY | E2, E3, E4, E5 |
| LLD v2.38 §0A named block, p.5 | “POST /v1/responses”<br>“POST /v1/chat/completions” | In scope | P11-FEAT-GATEWAY | E2 |
| LLD v2.38 §0A named block, p.5 | “POST /v1/tools/web/search”<br>“POST /v1/tools/web/extract”<br>“POST /v1/observability/traces” | In scope | P11-FEAT-GATEWAY | E2, E3, E5 |
| LLD v2.38 §0A named block, p.5 | “Canonical Phase 1 LangSmith wiring (single primary path). The local agent emits structured trace events to the Gateway at /v1/observability/traces; the Gateway exports to LangSmith using a server-side service key. Direct Gateway-native spans to LangSmith are retained only as an internal extension, not an equal option. If LangSmith is proxied, LANGSMITH_ENDPOINT is forced to the Optimus Gateway and the real LangSmith key exists server-side only.” | In scope | P11-FEAT-GATEWAY | E5, E7 |

### LLD v2.38 §6 — 7 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §6 | “All model completions route through the Optimus Gateway using the single Optimus credential. The local agent never calls an upstream LLM provider directly and never holds a provider API key.” | In scope | P11-FEAT-GATEWAY | E1, E2 |
| LLD v2.38 §6 | “The gateway resolves the model alias, selects the upstream provider, injects its own Vault-held key, and returns a normalised response.” | In scope | P11-FEAT-GATEWAY | E2 |
| LLD v2.38 §6 | “The gateway exposes two completion endpoints with distinct wire shapes.”<br>“Use /v1/responses for the OpenAI Responses API shape, where the request body uses "input" as the top-level content field.” | In scope | P11-FEAT-GATEWAY | E2 |
| LLD v2.38 §6 | “Use /v1/chat/completions for the Chat Completions shape, where the request body uses a "messages" array.” | In scope | P11-FEAT-GATEWAY | E2 |
| LLD v2.38 §6 | “The local agent must not mix these: sending a "messages" array to /v1/responses, or an "input" string to /v1/chat/completions, will be rejected by the gateway schema validator.” | In scope | P11-FEAT-GATEWAY | E2 |
| LLD v2.38 §6 | “@retry(raise=True, stop=stop_after_attempt(4), wait=wait_random_exponential(min=1, max=12), retry=retry_if_exception(is_retryable_provider_fault), after=log_retry_telemetry)” | In scope | P11-FEAT-GATEWAY | E6 |
| LLD v2.38 §6 | “Routes through the Optimus Gateway (POST /v1/responses). No provider URL or provider API key is present here. The gateway selects the upstream model, injects its Vault credentials, and returns a normalised completion response.”<br>“if response.status_code != 200: raise OptimusToolError(OptimusToolErrorCode.PROVIDER_ERROR, f"Gateway returned non-200: {response.status_code}")” | In scope | P11-FEAT-GATEWAY | E2, E6 |

### LLD v2.38 §9D — 7 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §9D | “The gateway must not trust the local agent's pre-validated parameters. Defense in depth requires the gateway to independently revalidate every policy constraint, regardless of what the local agent sends.”<br>“The local ToolRegistry and EvidenceRequest validators are client-side convenience gates; the gateway is the authoritative enforcement point.” | In scope | P11-FEAT-GATEWAY | E8 |
| LLD v2.38 §9D | “Allowed domains: the gateway re-applies the org/project domain whitelist against the fully-resolved request URL before dispatching to the upstream provider. A misconfigured or malicious local agent cannot bypass this.” | In scope | P11-FEAT-GATEWAY | E8 |
| LLD v2.38 §9D | “Extract URL provenance: the gateway re-checks that all extract URLs appeared in a preceding gateway-logged search response for the same run_id. The local agent's approved_urls set is advisory only.” | In scope | P11-FEAT-GATEWAY | E8, E3 |
| LLD v2.38 §9D | “Budgets: the gateway re-enforces per-org, per-user, and per-project spend caps against its Cost Ledger before dispatching any billable request. Local budget state is informational.” | Deferred → P9.85-FU-3 (parked; operator decision pending) | P9.85-FU-3 | E12 |
| LLD v2.38 §9D | “Call caps: the gateway independently tracks max_calls_per_run against its own Redis counter keyed by run_id + tool_name. It does not trust the local ToolRegistry counter.” | In scope | P11-FEAT-GATEWAY | E8 |
| LLD v2.38 §9D | “Tool policies: the gateway re-checks that the requested tool class and model are permitted for the authenticated org / project / execution mode. Plan-mode constraints are enforced server-side.” | In scope | P11-FEAT-GATEWAY | E8 |
| LLD v2.38 §9D | “Any request that fails a gateway-side policy check returns a structured error with a gateway_request_id, allowing the local agent to surface the rejection through the normal ToolResponse error path. The gateway never silently drops requests.” | In scope | P11-FEAT-GATEWAY | E8, E2 |

### Guardrails v1.0 §9 — 6 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Guardrails v1.0 §9 | “The governing rule is: rules first, a small-model classifier only when needed, and human approval for high-risk uncertainty.” | In scope | P11-FEAT-GATEWAY | E8, E11 |
| Guardrails v1.0 §9 | “Permission rules (§2) Allow/deny lists, mode overlay Zero LLM cost”<br>“Pre-tool guard (§3) Regex / rules / AST / path checks Zero LLM cost”<br>“Shell validation (§4) CommandSafetyValidator Zero LLM cost”<br>“Injection / MCP defense (§5) Registry, hashing, config scan Zero LLM cost”<br>“Pre-commit / CI (§6) Ruff, Bandit, AST-grep, tests Compute, not tokens” | In scope | P11-FEAT-GATEWAY | E8, E9 |
| Guardrails v1.0 §9 | “Bounded loops (§7) Cheap evaluator + hard budgets Net cost reduction under caps” | In scope | P11-FEAT-GATEWAY / P9.85-FU-3 | E6, E12 |
| Guardrails v1.0 §9 | “Workflow skills (§8) On-demand procedure loading Token saving; smaller model viable” | In scope | P11-FEAT-GATEWAY | E11 |
| Guardrails v1.0 §9 | “Borderline classifier Cheap model via Optimus Gateway, strict budget Rare, budgeted, off the hot path” | In scope | P11-FEAT-GATEWAY / P9.85-FU-3 | E2, E12 |
| Guardrails v1.0 §9 | “Every model-touching element in the strategy — the borderline permission/guard classifier and the loop completion evaluator — is routed through the Optimus Gateway under the same budget wallet, normalized ledger, and observability sink as all other calls (HLD §5A / §11; LLD §10, §10A). There is no second, ungoverned cost path introduced by guardrails.” | In scope | P11-FEAT-GATEWAY / P9.85-FU-3 | E2, E4, E5, E12 |

### Test Strategy v1.4 §7 — 9 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Test Strategy v1.4 §7 | “gateway_url set to https://gateway.optimus.ai (built-in): validate_trusted_gateway() passes.”<br>“gateway_url set to https://rogue.attacker.com (not in any trusted set): validate_trusted_gateway() raises ValueError.”<br>“production_mode=True with extra_trusted_origins non-empty: raises ValueError”<br>“production_mode=False with OPTIMUS_EXTRA_GATEWAY_ORIGINS="https://internal.corp.com": origin accepted.”<br>“production_mode=True with OPTIMUS_EXTRA_GATEWAY_ORIGINS set: env var ignored; only built-in + signed tenant profile origins accepted.” | In scope | P11-FEAT-GATEWAY | E7 |
| Test Strategy v1.4 §7 | “optimus_api_key appears in Authorization header as "Bearer <key>"; repr(settings) masks key as "**********".”<br>“str(settings) and model_dump() do not reveal optimus_api_key in plaintext.” | In scope | P11-FEAT-GATEWAY | E1, E7 |
| Test Strategy v1.4 §7 | “POST /v1/responses payload contains input field (not messages); Content-Type is application/json.”<br>“POST /v1/chat/completions payload contains messages array (not input); confirms the two endpoints are not mixed.”<br>“auth_headers() returns {"Authorization": "Bearer opt_live_xxx"} with no provider key present.” | In scope | P11-FEAT-GATEWAY | E2 |
| Test Strategy v1.4 §7 | “Gateway revalidation (§9D): send policy-violating request (blocked domain) directly to staging gateway; confirm 403 response independent of local agent policy.” | In scope | P11-FEAT-GATEWAY | E8 |
| Test Strategy v1.4 §7 | “Provider failover: primary provider returns 503; gateway routes to fallback; local agent receives successful response; GatewayUsage.provider reflects actual provider used.”<br>“Cache hit: repeated identical request returns cache_hit=True in GatewayUsage; cost_usd reflects cache pricing ($0.26/M).” | In scope | P11-FEAT-GATEWAY | E2, E6 |
| Test Strategy v1.4 §7 | “RELEASE GATE: start agent with OPTIMUS_GATEWAY_URL + OPTIMUS_API_KEY only. Verify via environment scan, process inspection, and config file audit that no OPENAI_API_KEY, TAVILY_API_KEY, GLM_API_KEY, LANGSMITH_API_KEY, or any other provider key is resolvable at any point during a full Plan+Agent run.” | In scope | P11-FEAT-GATEWAY | E1 |
| Test Strategy v1.4 §7 | “RELEASE GATE: instrument the test harness with an outbound HTTP intercept (e.g. respx or mitmproxy in CI). Run a full Plan+Agent cycle and assert that every HTTP request originates from OPTIMUS_GATEWAY_URL. Any direct connection to api.openai.com, api.anthropic.com, Tavily, OpenRouter, api.zhipuai.cn, LangSmith (api.smith.langchain.com), or any other provider host fails the test with error "forbidden egress: direct provider contact detected".” | In scope | P11-FEAT-GATEWAY | E1, E11 |
| Test Strategy v1.4 §7 | “Verify that the egress gate fires even if a provider URL is injected via a crafted tool output (prompt injection vector): the test harness emits a fake tool response containing a direct API URL; the agent must not attempt to call it.” | In scope | P11-FEAT-GATEWAY | E8, E11 |
| Test Strategy v1.4 §7 | “Gateway returns HTTP 200 with response body missing gateway_request_id: agent raises GatewayResponseError and transitions to Failed state; no model output is used; no file mutation occurs.”<br>“Gateway returns HTTP 200 with usage field absent (no billing_units, no cost_usd): agent fails closed with GatewayResponseError; EvidenceLedger records no entry for the call; telemetry emits GATEWAY_USAGE_MISSING audit signal.”<br>“Gateway returns HTTP 200 with billing_units present but cost_usd is null: agent fails closed; partial GatewayUsage (with null cost_usd) is NOT appended to the ledger; GATEWAY_COST_MISSING audit signal emitted.”<br>“Gateway returns HTTP 200 with gateway_request_id set to empty string: treated as malformed; agent fails closed identically to the missing-field case.”<br>“All four malformed-response cases above must fail closed before any generated content is applied to the working tree or persisted to RedisTimeSeries.” | In scope | P11-FEAT-GATEWAY | E2, E4, E5, E11 |

## Tier 2 — unowned rows resolved by this extraction

### LLD v2.38 §0.B — 1 row

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §0.B, rendered p.2 | “The following describes the request path from IDE plugin to downstream providers:” | Deferred → LLD §0.B source repair (unextractable-pending-repair) | P11-FEAT-GATEWAY / LLD §0.B source repair | E10 |

No clipped lines are reconstructed here. The visible component-flow content is not treated as a complete requirement, and no endpoint or downstream provider is inferred from the missing continuation.

### LLD v2.38 §0.C — 9 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §0.C | “Single developer authentication — one credential, one session.” | In scope | P11-FEAT-GATEWAY | E1, E7 |
| LLD v2.38 §0.C | “Model routing across OpenAI / OpenRouter / Azure and other LLM providers.” | In scope | P11-FEAT-GATEWAY | E2 |
| LLD v2.38 §0.C | “Tool brokering for Tavily, OSV, package registries” | In scope | P11-FEAT-GATEWAY | E3, E8 |
| LLD v2.38 §0.C | “MCP tools.” | Excluded → no MCP endpoint shape or Gateway request/response contract is present in the pinned LLD §0.D; no MCP route may be inferred from this responsibility bullet. | P11-FEAT-GATEWAY / source-contract gap | E10 |
| LLD v2.38 §0.C | “Centralised prepaid balance or subscription billing.” | In scope | P11-FEAT-GATEWAY / P9.85-FU-3 | E4, E12 |
| LLD v2.38 §0.C | “Cost attribution by org_id, user_id, project_id, run_id.” | In scope | P11-FEAT-GATEWAY | E4, E5 |
| LLD v2.38 §0.C | “Policy enforcement: Plan mode, Agent mode, tool call caps, allowed domains.” | In scope | P11-FEAT-GATEWAY / P9.85-FU-3 | E8, E12 |
| LLD v2.38 §0.C | “Secret isolation: provider keys live in Vault, never on developer machines.” | In scope | P11-FEAT-GATEWAY | E1, E7 |
| LLD v2.38 §0.C | “Caching and de-duplication to amplify the cost-savings story.” | In scope | P11-FEAT-GATEWAY | E2, E11 |

### LLD v2.38 §0.D — 7 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §0.D | “The gateway exposes OpenAI-compatible model endpoints where possible, plus typed tool endpoints:” | In scope | P11-FEAT-GATEWAY | E2 |
| LLD v2.38 §0.D | “POST /v1/responses” and “Authorization: Bearer opt_live_xxx” with `{ "model": "optimus-default", "input": "..." }` | In scope | P11-FEAT-GATEWAY | E2 |
| LLD v2.38 §0.D | “POST /v1/chat/completions” and `{ "model": "optimus-default", "messages": [...] }` | In scope | P11-FEAT-GATEWAY | E2 |
| LLD v2.38 §0.D | “Do NOT mix shapes: "messages" at /v1/responses or "input" at /v1/chat/completions will be rejected by the gateway schema validator.” | In scope | P11-FEAT-GATEWAY | E2 |
| LLD v2.38 §0.D | “POST /v1/tools/web/search” and “POST /v1/tools/web/extract” | In scope | P11-FEAT-GATEWAY | E3, E8 |
| LLD v2.38 §0.D | “POST /v1/tools/package/lookup” | Excluded → no agent-facing caller exists in the current Phase 1 seams and the charter-retained Gateway scope names web search, web extract, and observability; a future owner must be assigned before this endpoint is reintroduced. | P11-FEAT-GATEWAY / future reviewed owner required | E10 |
| LLD v2.38 §0.D | “POST /v1/tools/security/advisory” | Excluded → no agent-facing caller exists in the current Phase 1 seams and the charter-retained Gateway scope names web search, web extract, and observability; a future owner must be assigned before this endpoint is reintroduced. | P11-FEAT-GATEWAY / future reviewed owner required | E10 |

## Tier 3 — cross-cutting intersections

The Tier 3 rows below are limited to Gateway-relevant intersections, as requested. They do not redefine the ownership of Plans 4, 7, 8, or 9.

### HLD v2.15 §6 — 3 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.15 §6 | “[6] Delivery to Optimus AI Gateway → Frontier Model Providers (GLM-5.2 Primary Generation Loop), returning the raw unified diff patch alongside the API usage object.” | In scope | P11-FEAT-GATEWAY | E2, E4 |
| HLD v2.15 §6 | “All provider calls flow through the Optimus AI Gateway; the local agent holds only a single Optimus credential.” | In scope | P11-FEAT-GATEWAY | E1 |
| HLD v2.15 §6 | “Async TS.ADD Numeric Telemetry Tracking (RedisTimeSeries)” and “Real-Time FinOps Console Panel display for IDE Cost Dashboard Live Update Screen.” | In scope | P11-FEAT-GATEWAY / Plan 7 | E4, E5 |

### HLD v2.15 §10 — 8 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.15 §10.A | “All provider calls flow through the Optimus AI Gateway; the local agent holds only a single Optimus credential.” | In scope | P11-FEAT-GATEWAY | E1 |
| HLD v2.15 §10.B | “Every user request traverses the full governance loop. The loop enforces that no model output reaches the working tree without passing through both the feedforward constraint layer and the feedback fitness gate layer.” | In scope | P11-FEAT-GATEWAY | E11 |
| HLD v2.15 §10.C | “Phase 1 is mandatory before any later phase.”<br>“PHASE 1 → Python Local Agent + Optimus Gateway”<br>“Release Gate: one-key setup → no direct provider keys on developer machines” | In scope | P11-FEAT-GATEWAY | E1 |
| HLD v2.15 §10.D | “1. Pre-prompt (Feedforward) — AST slicing + cache anchoring + ADL constraints — Unnecessary tokens sent to expensive models.” | In scope | P11-FEAT-GATEWAY / Plan 12 boundary | E11 |
| HLD v2.15 §10.D | “2. Router (Triage Gate) — Haiku classifies task → routes to cheapest sufficient model — Over-routing simple tasks to Pro/Opus tier.” | In scope | P11-FEAT-GATEWAY / Plan 12 boundary | E2, E11 |
| HLD v2.15 §10.D | “3. Rigor Budget (Runtime) — LOW/MEDIUM/HIGH tier caps tool calls + reflection passes — Token-doubling on ceremonial planning loops.” | In scope | Plan 9 / P11-FEAT-GATEWAY preserve-only | E11 |
| HLD v2.15 §10.D | “4. Post-call (Attribution) — Gateway usage object → EvidenceLedger → RedisTimeSeries — Silent cost accumulation; enables per-run audit.” | In scope | P11-FEAT-GATEWAY / Plan 7 | E4, E5 |
| HLD v2.15 §10.E | “ToolInvocationPolicy blocks casual web calls; reason codes required” | In scope | P11-FEAT-GATEWAY / Plan 4 | E3, E8 |

### HLD v2.15 §12 — 2 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.15 §12 | “Phase 1 targets a minimum 80% Python production-code coverage gate, with materially higher expectations for safety-critical modules (mode enforcement, gateway usage accounting, evidence reconciliation, retry/fail-closed logic, policy enforcement). Coverage is a release gate, not a quality substitute.” | In scope | P11-FEAT-GATEWAY / Test Strategy §8A | E9 |
| HLD v2.15 §12 | “Agent-quality and AI-safety evaluations — DeepEval (task-completion, hallucination, faithfulness, role-adherence), Ragas (retrieval / evidence-quality), and PyRIT (adversarial / red-team) — together with LangSmith trace observability are tracked separately and do not count toward the coverage metric.” | In scope | P11-FEAT-GATEWAY / Test Strategy §8A | E5, E9 |

### LLD v2.38 §9 — 2 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §9 | “Tool use is policy-driven first, model-requested second: the model may request evidence, but the harness alone decides whether a tool is permitted, necessary, and cost-justified for the active execution mode and rigor tier.” | In scope | P11-FEAT-GATEWAY / Plan 4 | E3, E8 |
| LLD v2.38 §9 | “This section defines the typed tool registry, the deterministic invocation policy matrix, and the Evidence Ledger schema that records every external lookup alongside the Assumption Ledger.” | In scope | P11-FEAT-GATEWAY / Plan 4 | E3, E4 |

### LLD v2.38 §9E — 6 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §9E | “Every external lookup is recorded in an Evidence Ledger entry alongside the existing Assumption Ledger, so a reviewer can trace which architectural claims were backed by which external source, under which policy signal and reason code.” | In scope | P11-FEAT-GATEWAY / Plan 4 | E3, E4 |
| LLD v2.38 §9E | “All gateway usage fields (gateway_request_id, provider, cache_hit, billing_units, cost_usd) are populated directly from the gateway response envelope, never estimated after the fact.” | In scope | P11-FEAT-GATEWAY / Plan 7 | E3, E4 |
| LLD v2.38 §9E | “EvidenceLedger exposes three reconciliation methods: total_credits() for backward compatibility with v2.26 callers, total_billing_units() for provider-native unit reconciliation, and total_cost_usd() as the primary cost reconciliation field (since v2.29).” | In scope | P11-FEAT-GATEWAY / Plan 7 | E4 |
| LLD v2.38 §9E | “Key rule, carried from the HLD: local evidence first, external evidence only when policy-triggered, mutation only after mode and fitness gates pass.” | In scope | P11-FEAT-GATEWAY / Plan 4 | E3, E8 |
| LLD v2.38 §9E | “ToolRegistry.authorize_and_record_call enforces mode, policy trigger, and per-run call-count ceiling atomically.” | In scope | P11-FEAT-GATEWAY / Plan 4 | E3, E8 |
| LLD v2.38 §9E | “The two ledgers are kept separate and joined on gateway_request_id.”<br>“Reconciliation: EvidenceLedger.total_cost_usd() and the sum of ProviderUsage.cost_usd (joined by gateway_request_id) must equal the same figure.” | In scope | P11-FEAT-GATEWAY / Plan 7 | E4 |

### LLD v2.38 §10A — 7 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §10A | “ProviderUsage extends GatewayUsage; it does not replace it. GatewayUsage remains the wire-level envelope returned by the Gateway on every billable call.” | In scope | P11-FEAT-GATEWAY / Plan 7 | E2, E4 |
| LLD v2.38 §10A | “ProviderUsage is the canonical persisted ledger record and is a strict superset: it carries the GatewayUsage fields verbatim and adds the normalization fields (service, native_unit, optimus_credits_debited, price_snapshot_id).” | In scope | P11-FEAT-GATEWAY / Plan 7 | E4 |
| LLD v2.38 §10A | “Usage accounting stores both the provider-native unit and the normalized internal charge for every request, so any upstream cost (tokens, Tavily credits, trace events) reconciles to a single Optimus ledger.” | In scope | P11-FEAT-GATEWAY / Plan 7 | E4 |
| LLD v2.38 §10A | “The Evidence Ledger (§9E) is the evidence / audit trail and is joined to this cost ledger on gateway_request_id (audit ↔ cost); it does not duplicate the normalized cost fields.” | In scope | P11-FEAT-GATEWAY / Plan 7 | E4 |
| LLD v2.38 §10A | “The Gateway enforces budget against the wallet before dispatching any billable request; local budget state remains informational.” | Deferred → P9.85-FU-3 (parked; operator decision pending) | P9.85-FU-3 | E12 |
| LLD v2.38 §10A | “optimus_credits_debited is the normalized figure carried into the per-run telemetry and the RedisTimeSeries cost series.” | In scope | P11-FEAT-GATEWAY / P9.85-FU-3 | E4, E5, E12 |
| LLD v2.38 §10A | “The canonical Phase 1 path (see §0A): the local agent sends structured trace events to the Gateway at /v1/observability/traces, and the Gateway forwards them to LangSmith with a server-side service key.”<br>“The LangSmith key is never present locally; if LangSmith is proxied, LANGSMITH_ENDPOINT is forced to the Optimus Gateway.”<br>“Each trace carries: run_id, request_id, execution_mode, generation_scope, model/provider (selected by Gateway), cache_hit, cost_usd, billing_units, policy_signal, tool_class, validation_outcome, failure_classification (when applicable)” | In scope | P11-FEAT-GATEWAY | E5, E7 |

### LLD v2.38 §11A — 5 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §11A | “The authoritative detail lives in the Test Strategy (§8A); the HLD and LLD may summarize the target for context, but Test Strategy §8A remains authoritative.” | In scope | P11-FEAT-GATEWAY / Test Strategy §8A | E9 |
| LLD v2.38 §11A | “Test coverage for production Python code is measured with coverage.py (canonical line and branch coverage) and pytest-cov (CI and local integration).”<br>“The Phase 1 release gate is a minimum 80% aggregate Python coverage threshold; safety-critical modules (ToolRegistry authorization, MutationGuard, GatewayUsage / ProviderUsage accounting, EvidenceLedger reconciliation, JSON-RPC framing, retry / fail-closed logic, policy enforcement) trend materially higher and must not regress.” | In scope | P11-FEAT-GATEWAY / Test Strategy §8A | E9 |
| LLD v2.38 §11A | “Agent-quality and AI-safety tools are tracked separately and do not count toward the coverage metric: DeepEval and Ragas for agent / evidence-quality evaluation, and PyRIT for adversarial / red-team probes. LangSmith traces are used for debugging and regression analysis, not as a coverage metric.” | In scope | P11-FEAT-GATEWAY / Test Strategy §8A | E5, E9 |
| LLD v2.38 §11A | “Critical failures from the DeepEval / Ragas / PyRIT suites do not affect the coverage figure but may still block release through separate quality and security gates.” | In scope | P11-FEAT-GATEWAY / Test Strategy §8A | E9 |
| LLD v2.38 §11A | “Authoritative thresholds, CI commands, eval suites, red-team tests, LangSmith trace assertions, and release gates are defined in the Test Strategy document, §8A.” | In scope | P11-FEAT-GATEWAY / Test Strategy §8A | E9 |

### LLD v2.38 §12 — 1 row

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §12 | “All model-touching elements (the borderline classifier and the loop completion evaluator) route through the Optimus Gateway under the existing budget wallet and normalized ledger (§0A, §10A); the guardrails introduce no second cost path.” | In scope | P11-FEAT-GATEWAY / P9.85-FU-3 | E2, E4, E12 |

### Guardrails v1.0 §7.2 — 5 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Guardrails v1.0 §7.2 | “For Optimus, persistent state lives in files, git history, task manifests, traces, and the evidence ledger — never in an ever-growing chat context.” | In scope | P11-FEAT-GATEWAY / Plan 9 | E4, E5 |
| Guardrails v1.0 §7.2 | “Every loop runs under hard, explicit bounds: max_iterations Hard ceiling on loop turns; max_wall_clock_minutes Time bound independent of iteration count; explicit completion condition Machine-checkable predicate that ends the loop.” | In scope | P11-FEAT-GATEWAY / Plan 9 | E11 |
| Guardrails v1.0 §7.2 | “max_budget_credits Gateway budget cap across the whole loop.” | Deferred → P9.85-FU-3 (parked; operator decision pending) | P9.85-FU-3 | E12 |
| Guardrails v1.0 §7.2 | “per-iteration evidence Each turn writes evidence to the ledger (LLD §9E).”<br>“clean git-diff check Working tree verified between iterations.” | In scope | P11-FEAT-GATEWAY / Plan 9 | E4, E11 |
| Guardrails v1.0 §7.2 | “pre-tool guard active §3 enforcement is never bypassed inside a loop.”<br>“human approval for escalation Out-of-band actions require sign-off.”<br>“stop on repeated failure Identical-failure pattern terminates the loop.” | In scope | P11-FEAT-GATEWAY / Plan 9 | E8, E11 |

### Test Strategy v1.4 §8 — 6 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Test Strategy v1.4 §8 | “These tests prove that cost accounting is accurate, complete, and reconciles against the gateway response.”<br>“total_cost_usd() sums cost_usd across all EvidenceLedgerEntry objects; returns 0.0 on empty ledger.”<br>“total_billing_units() sums billing_units; matches provider-native unit count.”<br>“total_credits() (backward compat) sums credits_used; does not conflict with cost_usd total.” | In scope | P11-FEAT-GATEWAY / Plan 7 | E4 |
| Test Strategy v1.4 §8 | “GatewayUsage fields (gateway_request_id, provider, provider_request_id, cache_hit, billing_units, cost_usd) all propagate correctly from gateway response envelope to EvidenceLedgerEntry.”<br>“Ledger entries are append-only; no existing entry can be modified after record() is called.” | In scope | P11-FEAT-GATEWAY / Plan 7 | E4 |
| Test Strategy v1.4 §8 | “Missing pricing_snapshot.json: usage accounting engine falls back to default pricing matrix and raises telemetry audit signal PRICING_FALLBACK_ACTIVATED.”<br>“pricing_snapshot.json present but stale (> 24h): PRICING_SNAPSHOT_STALE audit signal raised; calculation proceeds with stale data.” | In scope | P11-FEAT-GATEWAY / Plan 7 | E4, E5 |
| Test Strategy v1.4 §8 | “TS.CREATE with retention 30 days: key created; RETENTION verified via TS.INFO.”<br>“Duplicate TS.CREATE on existing key: TS.ALTER applied idempotently; RETENTION updated; no error thrown.”<br>“TS.ADD with run_id tag: confirmed present in TS.RANGE query with tag filter.” | In scope | P11-FEAT-GATEWAY / Plan 7 | E5 |
| Test Strategy v1.4 §8 | “Run metadata hash (HSET): execution_mode, generation_scope, rigor_level, assumption ledger count all written at workflow completion; TTL set to 30 days.” | In scope | P11-FEAT-GATEWAY / Plan 7 | E5 |
| Test Strategy v1.4 §8 | “EvidenceLedger.total_cost_usd() reconciles against sum of GatewayUsage.cost_usd values — delta < $0.000001.”<br>“EvidenceLedger.total_billing_units() reconciles against sum of GatewayUsage.billing_units.” | In scope | P11-FEAT-GATEWAY / Plan 7 | E4 |

### Test Strategy v1.4 §8A — 5 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Test Strategy v1.4 §8A | “This document is the authoritative source of truth for the Phase 1 coverage target, the measurement-tool taxonomy, and trace observability.” | In scope | P11-FEAT-GATEWAY / Test Strategy §8A | E9 |
| Test Strategy v1.4 §8A | “Phase 1 targets a minimum 80% aggregate Python test coverage threshold for production code, measured in CI with coverage.py and surfaced through pytest-cov during normal pytest execution.”<br>“The 80% threshold is a release gate, not a quality substitute.” | In scope | P11-FEAT-GATEWAY / Test Strategy §8A | E9 |
| Test Strategy v1.4 §8A | “deterministic safety-critical modules such as ToolRegistry authorization, MutationGuard, GatewayUsage accounting, EvidenceLedger reconciliation, JSON-RPC framing, retry/fail-closed logic, and policy enforcement should trend materially higher and must not regress without explicit review.” | In scope | P11-FEAT-GATEWAY / Test Strategy §8A | E9 |
| Test Strategy v1.4 §8A | “Each trace should include run_id, request_id, execution_mode, generation_scope, model/provider selected by the Optimus Gateway, cache_hit, cost_usd, billing_units, policy_signal, tool_class, validation outcome, and failure classification where applicable.”<br>“To preserve the one-key developer setup, LangSmith credentials must be configured at the Gateway, CI, or deployment environment layer, not as an additional local developer key.” | In scope | P11-FEAT-GATEWAY | E5, E7 |
| Test Strategy v1.4 §8A | “Coverage and evaluation tools are exercised in CI as follows: pytest --cov=optimus --cov-branch --cov-report=xml enforces the 80% gate; DeepEval, Ragas, and PyRIT suites run as separate, non-blocking-for-coverage jobs whose results are tracked on their own dashboards; LangSmith trace assertions validate that required trace fields are emitted per run.” | In scope | P11-FEAT-GATEWAY / Test Strategy §8A | E5, E9 |

### Test Strategy v1.4 §9 — 5 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Test Strategy v1.4 §9 | “TransientGatewayError on first attempt: tenacity retries up to max_retries=3; succeeds on 3rd attempt; retry_count=2 in metadata.”<br>“ProviderRateLimitError: exponential backoff applied (500ms base); jitter present.” | In scope | P11-FEAT-GATEWAY | E6 |
| Test Strategy v1.4 §9 | “PermanentGatewayError: ABORT_WITH_REPORT returned immediately; no retry; failure report emitted.”<br>“PolicyViolationError: ABORT_WITH_REPORT; escalation signal emitted.” | In scope | P11-FEAT-GATEWAY | E6, E8 |
| Test Strategy v1.4 §9 | “BudgetExhaustedError: ABORT_WITH_REPORT; run terminates; cost_usd at time of abort recorded in ledger.”<br>“Budget exhausted mid-run: run terminates gracefully; partial telemetry flushed; no partial file writes in working tree.” | Deferred → P9.85-FU-3 (parked; operator decision pending) | P9.85-FU-3 | E12 |
| Test Strategy v1.4 §9 | “max_retries=3 exceeded: ESCALATE_TO_USER returned; prior_failures injected into user escalation payload.” | In scope | P11-FEAT-GATEWAY | E6 |
| Test Strategy v1.4 §9 | “Gateway returns 503 twice, then 200: agent retries twice, succeeds; working tree unchanged after failed attempts; final patch applied only on success.”<br>“Fitness gate fails on attempt 1 and 2, passes on attempt 3: replan_context() injected with failure summaries on attempts 2 and 3; final patch differs from attempt 1 (proves replanning occurred).” | In scope | P11-FEAT-GATEWAY / Plan 9 | E6, E11 |

### Test Strategy v1.4 §10 — 3 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Test Strategy v1.4 §10 | “EvidenceRequest with empty query string: ValidationError raised before any gateway call.”<br>“EvidenceExtractRequest with max_chars_per_source=0: ValidationError raised.” | In scope | P11-FEAT-GATEWAY / Plan 4 | E3 |
| Test Strategy v1.4 §10 | “OptimusGatewaySettings with empty optimus_api_key: ValidationError raised.”<br>“GatewayUsage with negative billing_units: ValidationError raised.”<br>“GatewayUsage with negative cost_usd: ValidationError raised.” | In scope | P11-FEAT-GATEWAY | E2, E7 |
| Test Strategy v1.4 §10 | “These tests prove that malformed inputs are rejected before any processing occurs, and that pydantic v2 validators enforce invariants at the boundary.” | In scope | P11-FEAT-GATEWAY | E2, E3 |

### Test Strategy v1.4 §13 — 8 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Test Strategy v1.4 §13 | “OptimusGatewaySettings rejects rogue gateway URLs in both production_mode and non-production_mode.” | In scope | P11-FEAT-GATEWAY | E7 |
| Test Strategy v1.4 §13 | “POST /v1/responses uses input field exclusively; POST /v1/chat/completions uses messages — confirmed by unit + integration test.” | In scope | P11-FEAT-GATEWAY | E2 |
| Test Strategy v1.4 §13 | “Gateway server-side revalidation (§9D) tested via direct policy-violating requests to staging gateway.” | In scope | P11-FEAT-GATEWAY / P9.85-FU-3 | E8, E12 |
| Test Strategy v1.4 §13 | “optimus_api_key never appears in plaintext in logs, telemetry, repr(), str(), or model_dump() — confirmed by log scan post-run.” | In scope | P11-FEAT-GATEWAY | E1, E5, E7 |
| Test Strategy v1.4 §13 | “EvidenceRequest.query sent verbatim — confirmed by request capture in integration tests.”<br>“EvidenceLedger.total_cost_usd() reconciles against sum of GatewayUsage.cost_usd values — delta < $0.000001.”<br>“EvidenceLedger.total_billing_units() reconciles against sum of GatewayUsage.billing_units.” | In scope | P11-FEAT-GATEWAY / Plan 4 / Plan 7 | E3, E4 |
| Test Strategy v1.4 §13 | “Aggregate Python production-code coverage ≥ 80% in CI (coverage.py + pytest-cov); safety-critical modules trend higher and do not regress (see §8A).”<br>“LangSmith trace assertions pass: every run emits the required trace fields; LangSmith credentials are sourced from the Gateway / deployment layer, never local config.” | In scope | P11-FEAT-GATEWAY / Test Strategy §8A | E5, E9 |
| Test Strategy v1.4 §13 | “RedisTimeSeries TS.CREATE + TS.ALTER idempotency confirmed on both new and pre-existing keys.”<br>“Run metadata hash written at workflow completion with correct execution_mode, rigor_level, and assumption ledger count.” | In scope | P11-FEAT-GATEWAY / Plan 7 | E5 |
| Test Strategy v1.4 §13 | “RELEASE GATE: Agent completes a full Plan-mode and Agent-mode run with only OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY present. No provider API key (Tavily, OpenAI, OpenRouter, GLM, LangSmith, or any other upstream credential) is resolvable from the local environment, config files, or process state at any point during the run. This gate supersedes all others and must pass before the sprint is marked complete.” | In scope | P11-FEAT-GATEWAY | E1 |

## Tier 4 — preserve-only constraints

### HLD v2.15 §5 — 2 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.15 §5 | “Attribution calculations bypass tokeniser estimators, treating the provider usage response as the primary request-level cost record, supported by versioned pricing snapshots.” | In scope | Implemented by Plan 7 / P11-FEAT-GATEWAY preserve | E4 |
| HLD v2.15 §5 | “All gateway usage fields — gateway_request_id, provider, cache_hit, billing_units, and cost_usd — are parsed directly from the gateway response envelope, never estimated post-hoc.” | In scope | Implemented by Plan 7 / P11-FEAT-GATEWAY preserve | E4 |

### HLD v2.15 §8 — 3 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.15 §8 | “Optimus treats tool use as policy-driven first, model-requested second: the model may ask for evidence, but the harness alone decides whether a tool is allowed, necessary, and cost-justified.” | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY preserve | E3, E8 |
| HLD v2.15 §8 | “Web evidence acquisition is wrapped behind Optimus-owned typed tools rather than exposing a third-party search API directly to the model.”<br>“This lets the harness enforce allowed domains, timeouts, retries, result caps, and cost telemetry uniformly.” | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY preserve | E3, E8 |
| HLD v2.15 §8 | “Key rule: local evidence first, external evidence only when policy-triggered, mutation only after mode and fitness gates pass.” | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY preserve | E3, E8, E11 |

### LLD v2.38 §0.E — 1 row

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §0.E | “This boundary is strict.”<br>“Developer machine (local agent LLD): OPTIMUS_GATEWAY_URL, OPTIMUS_API_KEY (or OAuth session); production_mode flag; enterprise origins via signed tenant profile only.”<br>“Gateway / Vault (server-side only): tavily_api_key, openai_api_key, openrouter_api_key, etc.” | In scope | Implemented by Plan 3 / P11-FEAT-GATEWAY preserve | E1, E7 |

### LLD v2.38 §9C — 6 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §9C | “In the current Gateway-centric architecture, the local agent no longer holds any provider API key. Authentication to all downstream services (Tavily, OSV, package registries) is handled by the Optimus AI Gateway. The local agent supplies only its Optimus credential; the gateway resolves the provider route and injects its own Vault-held keys server-side.” | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY preserve | E1, E3, E7 |
| LLD v2.38 §9C | “query must be a non-empty search string; reason is metadata only and must never be sent as the query.” | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY preserve | E3 |
| LLD v2.38 §9C | “Advanced search depth is capped to 5 results to bound per-call credit cost.” | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY preserve | E3 |
| LLD v2.38 §9C | “Extract is a follow-up on evidence the harness has already seen, never an independent fetch of arbitrary URLs.”<br>“Extract requested for URLs outside the prior approved search-result set” | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY preserve | E3, E8 |
| LLD v2.38 §9C | “urls: list[str] = Field(..., min_length=1, max_length=10)”<br>“max_chars_per_source: int = Field(default=4000, gt=0, le=20000)”<br>“URLs must not contain duplicates.” | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY preserve | E3 |
| LLD v2.38 §9C | “gateway_request_id = usage_env.get("gateway_request_id", "")”<br>“provider = usage_env.get("provider", "tavily")”<br>“provider_request_id = usage_env.get("provider_request_id")”<br>“cache_hit = usage_env.get("cache_hit", False)”<br>“billing_units = usage_env.get("credits", 0)”<br>“cost_usd = usage_env.get("cost_usd", 0.0)” | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY preserve | E3, E4 |

### LLD v2.38 §10 — 3 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §10 | “TimeSeries Policy Lifetime Management: Keys feature an explicit retention window matching standard 30-day corporate storage stability intervals.” | In scope | Implemented by Plan 7 / P11-FEAT-GATEWAY preserve | E5 |
| LLD v2.38 §10 | “if os.path.exists(self.pricing_path):”<br>“is_fallback_pricing = True”<br>“model_rates = default_rates”<br>“c_key = f"telemetry:run:{run_id}:metrics:cost_usd"”<br>“i_key = f"telemetry:run:{run_id}:metrics:tokens_input"”<br>“o_key = f"telemetry:run:{run_id}:metrics:tokens_output"” | In scope | Implemented by Plan 7 / P11-FEAT-GATEWAY preserve | E4, E5 |
| LLD v2.38 §10 | “await pipe.hset(h_key, mapping={ "execution_mode": state_metadata.get("execution_mode", "PLAN"), "generation_scope": state_metadata.get("generation_scope", "INLINE_SNIPPET"), "rigor_level": state_metadata.get("rigor_level", "LOW"), "user_approval_id": state_metadata.get("user_approval_id", "unauthorized_direct_run"), "assumption_count": str(len(assumptions_list)), })”<br>“await pipe.expire(h_key, 2592000)” | In scope | Implemented by Plan 7 / P11-FEAT-GATEWAY preserve | E5 |

### LLD v2.38 §12C — 3 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.38 §12C | “Persistent state lives in files, git history, task manifests, traces, and the evidence ledger (§9E), not in an ever-growing chat context.” | In scope | Implemented by Plan 9 / P11-FEAT-GATEWAY preserve | E4, E5 |
| LLD v2.38 §12C | “The pre-tool guard (§12A) is never bypassed inside a loop, and the completion evaluator is a cheap Gateway-routed model, not the main reasoning model.” | In scope | Implemented by Plan 9 / P11-FEAT-GATEWAY preserve | E2, E8 |
| LLD v2.38 §12C | “LoopBudgetPolicy (max_iterations, max_budget_credits, max_wall_clock_minutes)” | Deferred → P9.85-FU-3 (parked; operator decision pending) | Implemented by Plan 9 / P9.85-FU-3 | E12 |

## Named findings and decisions required

1. **Budget authority is a real scope finding, not an implementation detail.** HLD §5A and §11, LLD §9D and §10A, Guardrails §7.2, and LLD §12C assign Gateway budget authority or Gateway budget caps. Every such row is explicitly deferred to `P9.85-FU-3 (parked; operator decision pending)`. The Gateway inventory does not scope, implement, or silently discard budget enforcement. The operator must decide whether Gateway work organically reaching cost policy unparks `P9.85-FU-3`.

2. **LLD §0.B remains blocked.** The rendered component-flow block is clipped at the page boundary around `/v1/tools/web/extract`. The affected requirement is recorded as `unextractable-pending-repair`; no clipped line was reconstructed.

3. **Package lookup and security advisory are explicitly excluded from this slice.** They are present in LLD §0.D but have no current agent-facing caller in the repository seam identified by the map, and the charter-retained Gateway scope names web search, web extract, and observability. They require a future reviewed owner before reintroduction; they are not silently omitted.

4. **The second model shape is in scope as a Gateway route/schema contract.** `/v1/chat/completions`, its `messages` shape, `/v1/responses`’s `input` shape, and the do-not-mix validator rule are independently specified and tested by the source set, even though the current local caller uses `/v1/responses`.

5. **MCP brokering is an explicit source-contract gap.** LLD §0.C names MCP tool brokering, but LLD §0.D supplies no MCP endpoint shape. This inventory excludes an inferred MCP route and records the missing endpoint contract as a source gap. Plan 6.5’s local MCP trust boundary remains preserved; it is not redefined as a Gateway API here.

6. **The slice is plausibly too large for one implementation plan.** The inventory supports these candidate split boundaries, subject to reviewed feature-ID/charter amendment; no new `P11-FEAT-*` identity is minted here:

   - Candidate `P11-FEAT-GATEWAY-CORE`: one-key boundary, origin/secrets, model routing, both model wire shapes, schema rejection, retries, and normalized model response.
   - Candidate `P11-FEAT-GATEWAY-TOOLS`: web search/extract adapters, provenance/domain/call-cap revalidation, typed-tool envelopes, and the explicit disposition of package/security/MCP boundaries.
   - Candidate `P11-FEAT-GATEWAY-COST-OBS`: provider-native usage normalization, ledger reconciliation, LangSmith trace export, observability fields, and Plan 7 telemetry compatibility.

   The existing `P11-FEAT-GATEWAY` remains the current charter identity. These are review proposals only; they are not applied to the charter or roadmap.

## Verification record

- SHA-256 re-verification: four source digests matched the map.
- Tier 1: 62 rows across all ten requested sections; extracted to exhaustion.
- Tier 2: 17 rows across §0.B, §0.C, and §0.D; extracted to exhaustion, with §0.B explicitly blocked and every unowned item disposed.
- Tier 3: 66 Gateway-relevant intersection rows; all requested sections traced, including all four HLD §10.D cost-control points.
- Tier 4: 18 preserve-only rows; one-key boundary, Plan 4 wrapper surface, Plan 7 ledger/telemetry contract, and Plan 9 Gateway evaluator boundary retained.
- No blank disposition exists in the inventory.
- No charter, roadmap, frozen specification, or implementation file was changed by this extraction.

