# Local-Gateway Architecture Correction — Brief for Codex

> **AMENDED 2026-07-27 (v3) — read BOTH amendment sections at the bottom before using this brief.**
> v2 accepted Codex's five scope corrections. **v3 supersedes a core assumption of v1 and v2:**
> the "one key, one balance" goal is *achievable* without a hosted service, so it is being kept, not
> dropped. This changes the upstream architecture, retires Tavily and the direct provider adapters,
> and replaces LangSmith with OTel. **Read "Amendments v3" first — it outranks v2, which outranks v1.**
> **Do not begin the PDF rewrite until the v3 architecture design note is approved.**

**Status:** Operator-directed correction, pre-drafting brief. Codex drafts all replacement prose,
code, and backlog updates described below; Claude reviews each deliverable against this brief and
the current codebase before anything is finalized. Do not skip the review checkpoints in
"Delivery expectations."

**Origin:** 2026-07-27 operator correction. The HLD, LLD, and one production code path describe a
hosted, multi-tenant SaaS Gateway (OAuth sign-in, org/tenant/project budget wallet, Vault-held
credentials at `gateway.optimus.ai`). That was a misunderstanding at drafting time. This is an
open-source project; the operator will not host or maintain a separate Gateway service. **The
Gateway is, and remains, a local process the developer runs alongside the agent on their own
machine** — exactly as `docs/superpowers/plans/archive/2026-07-07-local-optimus-gateway-service.md` and the
current `.env.gateway` / `.env` split already implement it.

This brief also resolves the blocker on two backlog items:
- `P11-FU-3` (LLD source repair — the `§0.B` diagram is clipped at the page boundary).
- `P9.85-FU-3` (cross-run spend ceiling), paused because the docs assigned budget authority to a
  hosted Gateway that does not exist. See
  [plan-10-4-cross-run-spend-paused-gateway-conflict.md] in memory for the paused-item history —
  this brief is what un-blocks it, not what re-scopes the feature itself. Re-scoping
  `P9.85-FU-3`/`Plan 10.4` as an implementation plan is separate follow-on work, after these docs
  are corrected.

## The correction principle

Everywhere the source documents describe a **separate, centrally-hosted, multi-tenant Gateway
service** — reached over a public URL, authenticated via OAuth/device flow, keyed by
`org_id`/`user_id`/`project_id`, billing a centralized "org account" — replace it with: **a local
Gateway process, run by the developer on their own machine (default `127.0.0.1:8765`), holding the
developer's own provider credentials in its own local environment, separate from the agent
process's environment.**

The *reason* for the Gateway boundary does not disappear — keep it, just reframe its source:

- **Before:** the Gateway is authoritative because it is a separate, remote, hardened service the
  developer cannot tamper with.
- **After:** the Gateway is authoritative because it is a separate **process** from the agent — a
  small, deterministic, non-LLM-driven daemon — and the agent (which runs LLM-generated tool calls
  and is the thing being defended against, not the developer) never holds provider keys or sees
  budget state directly. Defense-in-depth between agent-process and Gateway-process is still real
  and still worth keeping, even when both run on the same machine under the same user.

What drops entirely, with no replacement needed: OAuth/device-flow sign-in, org/tenant/project
multi-tenancy, centralized prepaid balance or subscription billing, a public Gateway hostname, and
any installer/enterprise-admin tooling for provisioning tenant profiles. None of that exists today
and none of it is being built.

### Vocabulary swap (apply consistently, cite each instance)

| Old (hosted-SaaS framing) | New (local-process framing) |
|---|---|
| `OPTIMUS_GATEWAY_URL=https://gateway.optimus.ai` | `OPTIMUS_GATEWAY_URL=http://127.0.0.1:8765` (or whatever port the developer configures) |
| "Sign in with Optimus (OAuth / device flow)" | Local shared secret between the agent process and the Gateway process (already implemented: `OPTIMUS_API_KEY` / `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET`) |
| "maps to an internal tenant/user/project budget wallet" | "tracked by the local Gateway process against the developer's own configured budget" — no tenant, no org, single local user |
| "Gateway holds provider credentials server-side in a Vault, never on developer machines" | "Gateway process holds provider credentials in its own local environment (`.env.gateway`); the agent process's environment (`.env`) never sees them" — separation is between *processes*, not between *developer machine and a remote host* |
| "Centralised prepaid balance or subscription billing," "bill Optimus / org account" | Removed. The developer funds and is billed directly by their own upstream provider accounts (OpenAI, OpenRouter, Tavily, etc.) — Optimus credits/wallet abstraction is dropped unless a future feature explicitly reintroduces it |
| Cost attribution "by org_id, user_id, project_id, run_id" | Cost attribution by `run_id` only (single local user, no tenant concept) |
| "This mirrors the model used by Cursor, JetBrains AI" | Remove this justification — those are hosted commercial products; it is not this project's precedent |

## HLD v2.15 → v2.16

Every row below is a real citation confirmed by reading the source PDF directly (not the section
map's paraphrase). Quote the existing sentence exactly in your redline, propose the replacement,
and cite the page.

| Citation | What's wrong |
|---|---|
| §5A title + body ("Provider-Cost Normalization & Single-Key Wallet Model") | "maps to an internal tenant/user/project budget wallet," "bill Optimus / org account," "Third-party vendors ... expects its own vendor credential" framing assumes hosted multi-tenant billing. The "single credential, many providers behind the curtain" *thesis* is still true locally and can be kept — just drop the tenant/org/billing layer. |
| §6 diagram step [6] ("Delivery to Optimus AI Gateway → Frontier Model Providers") | No hosted-specific text here, but cross-check after §5A/§11 changes for consistency. |
| §10.A "System Context Diagram" + caption ("single Optimus credential; all provider keys Vault-held server-side") + the diagram image itself | The diagram draws the Gateway as an external box separate from "Developer Environment," with "Vault-held keys (Vault-injected)." Must be redrawn/relabeled so the Gateway sits **inside** the developer environment, alongside the local agent, both on the same box/host. This is a diagram edit, not just prose — flag if diagram regeneration needs a different process than the text redline. |
| §11 body ("The gateway holds all provider credentials server-side in a Vault... eliminates credential sprawl on developer machines and centralises cost attribution") | "Server-side" here reads as "on a remote server." Reframe as "in the Gateway process's own local config, never in the agent process's." Drop "centralises cost attribution" (no multi-tenant center to centralize into). |
| §11 "Gateway Responsibilities" bullets ("Inject provider API keys server-side from Vault," "Enforce origin allowlist: local agent gateway_url must resolve to a trusted origin; rogue gateway attacks are blocked via production_mode + signed tenant profile") | The "signed tenant profile" mechanism doesn't exist and isn't being built — ties directly to the code correction below. |
| §11 "Single-Credential Model" code block (`OPTIMUS_GATEWAY_URL=https://gateway.optimus.ai`) | Replace with the real local example from `.env.example` / `.env.gateway.example`. |
| §11A "Trace Observability" ("credentials managed by the Gateway / deployment layer") | "Deployment layer" implies a hosted deploy target. Reframe as the local Gateway process's own config. |

## LLD v2.38 → v2.39

| Citation | What's wrong |
|---|---|
| §0 intro ("the developer authenticates once with Optimus, and the gateway holds all provider credentials server-side in a Vault. This mirrors the model used by Cursor, JetBrains AI...") | Full hosted-SaaS framing plus the false precedent. |
| §0.A "Recommended Architecture" ("The control plane is entirely on the gateway side," `OPTIMUS_GATEWAY_URL=https://gateway.optimus.ai`, "Sign in with Optimus (OAuth / device flow)") | OAuth/device flow doesn't exist. Replace with the real local shared-secret model. |
| §0.B "Gateway Component Flow" diagram | **This is the already-known `P11-FU-3` clip** — rendered page 2 cuts off mid-block around `/v1/tools/web/extract`. Fix the clip **and** the content in the same pass: the diagram currently reads "1 Optimus key or OAuth token," "Auth + Project Policy (resolves org/project)," "Secret Vault (holds provider credentials, never exposed)" — all need the local-process reframing above, not just an unclipped render of the same wrong content. |
| §0.C "Gateway Responsibilities" ("Centralised prepaid balance or subscription billing," "Cost attribution by org_id, user_id, project_id, run_id") | Drop billing bullet; cost attribution by `run_id` only. |
| §0.E "Developer-Facing vs. Server-Side Configuration Boundary" table | The "Gateway / Vault (server-side only)" column header and framing needs to become "Gateway process's local config (`.env.gateway`)" — still a real boundary (the agent process's `.env` never holds these), just not a remote server. |
| §0A "Local vs. Gateway Configuration & Provider-Cost Mapping" ("OPTIMUS_API_KEY... maps to a tenant/user/project budget wallet," "Vendors... bill the Optimus org account") | Same tenant/wallet/billing correction as HLD §5A. |
| §9C "Typed Evidence Acquisition Wrappers" intro ("the gateway resolves the provider route and injects its own Vault-held keys server-side. This eliminates credential sprawl on developer machines and centralises cost attribution") | Same "server-side = remote" correction. |
| §9C `OptimusGatewaySettings` / `load_trusted_origins` / `_read_signed_tenant_profile_origins` example code, and the `OPTIMUS_BUILTIN_TRUSTED_ORIGINS` block (`https://gateway.optimus.ai`, `https://gateway.optimus-eu.ai`, installer/enterprise-admin-provisioned signed tenant profile) | This is real example code in the spec, not just prose, and it directly maps to `src/optimus/config/gateway.py` (see code correction below). Rewrite this example to match whatever the corrected `gateway.py` looks like after that fix — do the code fix first, then update this LLD section to describe the actual resulting code, not the other way around. |
| §9D "Gateway Server-Side Policy Revalidation" ("the gateway re-enforces per-org, per-user, and per-project spend caps... Local budget state is informational") | This is the exact sentence blocking `P9.85-FU-3`. Correct to: the local Gateway process independently tracks and enforces spend caps against its own local ledger, regardless of what the agent process claims; there is no org/user/project dimension, only the single local developer. Keep "local [agent-process] budget state is informational, the Gateway [process] is authoritative" — that boundary is still real and still worth having between the two local processes. |
| §10A "Provider Usage Ledger Schema" | Check for the same org/tenant framing per the section map's note; confirm and correct if present (pages not yet pulled in this brief — Codex should read the actual page before drafting). |

## Guardrails v1.0 — consistency check only

`§7.2` ("Gateway budget cap across the whole loop") and `§9` ("routed through the Optimus Gateway
under the same budget wallet") reference the HLD/LLD budget-wallet terminology but don't themselves
assert hosting/OAuth/tenancy. After the HLD/LLD vocabulary swap, re-read these two sections: if
"budget wallet" reads inconsistently against the corrected local-ledger terminology, redline the
minimal wording needed for consistency and bump to v1.1. If the existing wording still reads
correctly under the new terminology, leave v1.0 and note in your delivery that this document was
checked and required no edit — do not bump the version without an actual text change.

## Code correction: `src/optimus/config/gateway.py`

This is a real implementation change, not a docs-only fix, and the operator has explicitly asked
for it to be folded into this same effort. Treat it as its own reviewed sub-task with its own test
run — do not bundle it into the doc redline review.

**What's wrong today:**
- `BUILT_IN_TRUSTED_GATEWAY_ORIGINS = frozenset({"https://gateway.optimus.ai"})` (line 10) is the
  only built-in trusted origin for `production_mode=True` (the model's own default, line 48).
  Loopback (`127.0.0.1`/`localhost`) is only trusted when `production_mode=False`, documented in
  the code's own comment as a "non-production trust-boundary exception... for the local Optimus
  Gateway stub."
- `signed_tenant_profile_origins` (line 55) exists to receive origins from an "already-verified
  tenant profile loader" that doesn't exist and isn't being built.
- In practice this is currently dead in the real launch path: `src/optimus/acp/local_infra.py:86-87`
  and `src/optimus/acp/subprocess_env.py:117-118` both force `OPTIMUS_PRODUCTION_MODE` to default to
  `"false"` before `OptimusGatewaySettings.from_env()` ever runs, and the shipped `.env.example` sets
  `OPTIMUS_PRODUCTION_MODE=false` explicitly. But the Pydantic model's own default
  (`production_mode: bool = True`) and the hardcoded hosted origin still exist and are exercised by
  any direct construction/test that doesn't go through the launcher.

**What to fix:** make loopback/local the real trusted default, not a "non-production stub"
exception. Retire `gateway.optimus.ai` and `signed_tenant_profile_origins` as concepts (or keep the
`extra_trusted_origins`-style override mechanism if there's a legitimate reason a developer might
run the Gateway on a non-loopback host they explicitly trust — your call, but justify it in the
redline rather than silently keeping the tenant-profile machinery). Decide what `production_mode`
should mean now that there's no hosted tier to distinguish from — e.g., "strict validation for a
packaged/installed release build" vs. "relaxed dev settings" — and make sure the meaning is
documented in the corrected LLD §9C, not just in code comments.

**Blast radius — 23 test files reference this today, confirmed by grep:**
`tests/unit/acp/test_local_infra.py`, `tests/unit/release/test_credentials.py`,
`tests/unit/gateway/test_client.py`,
`tests/integration/usage/test_evidence_provider_reconciliation.py`,
`tests/integration/evidence/test_package_advisory_flow.py`,
`tests/integration/evidence/test_mocked_evidence_flow.py`, `tests/unit/tools/test_mutation_tools.py`,
`tests/unit/telemetry/test_observability.py`, `tests/unit/loops/test_tools.py`,
`tests/unit/loops/test_completion.py`, `tests/unit/guardrails/test_pre_tool_guard.py`,
`tests/unit/guardrails/test_network_safety.py`, `tests/unit/guardrails/test_command_safety.py`,
`tests/unit/config/test_gateway_settings.py`, `tests/unit/acp/test_preflight.py`,
`tests/unit/acp/test_live_fixture_policy.py`, `tests/unit/acp/test_bootstrap.py`,
`tests/integration/telemetry/test_usage_telemetry_flow.py`,
`tests/integration/runtime/test_mode_boundary.py`,
`tests/integration/release/test_phase1_release_gate_cli.py`,
`tests/integration/guardrails/test_pre_tool_guard_blocks_side_effects.py`,
`tests/integration/gateway/test_one_key_mocked_run.py`,
`tests/integration/acp/test_bootstrap_live_redis.py`. Expect most of these only need a fixture/const
update, not a logic rewrite — but verify each one, don't assume.

## PDF regeneration

The operator does not want a bespoke PDF-generation script built for this. Instead: **propose your
own approach** for producing HLD v2.16 and LLD v2.39 as real PDF files checked into `docs/`,
preserving the existing layout, tables, and diagrams as closely as is practical. Exact visual theme
match is not required — the operator is fine if it's not pixel-identical — but the layout, text
fidelity, and diagrams must not be degraded (no more clipped diagrams, no reformatted tables that
lose information). Present your proposed approach/tooling before generating anything, so it can be
reviewed.

## Section-map re-pin

Once the new PDFs exist, refresh
`docs/superpowers/reports/2026-07-25-plan-11-authoritative-doc-section-map.md`: recompute the
SHA-256 digests for the new HLD v2.16 / LLD v2.39 (and Guardrails v1.1 if it changed), update every
citation that referenced the old version pin, and re-check the "Diagram and render-survey scope"
note — the §0.B clip finding should now read as resolved rather than open.

## Backlog updates (you draft, Claude reviews — per existing convention)

In `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`:
- Expand `P11-FU-3`'s description: it was scoped as "the LLD §0.B diagram is clipped," but the
  actual defect was the hosted-SaaS content underneath the clip, not just the clip itself. Record
  both, and record this brief as the resolution.
- Add a disposition note to the `P9.85-FU-3` / `Plan 10.4` entry: the HLD/LLD architecture conflict
  that paused it is resolved by this correction (Gateway-as-local-process is now the documented and
  coded reality, and it can be authoritative over budget without requiring a hosted tier). This
  brief does **not** re-scope or design `P9.85-FU-3` itself — that's separate follow-on work the
  operator picks up next, now unblocked.

## Delivery expectations

1. Redline HLD and LLD sections as quote-old / quote-new pairs, cited by section and page, before
   touching the PDFs. Claude reviews the redline against the actual source PDF pages and the real
   codebase before anything is regenerated.
2. The `gateway.py` code correction is reviewed and tested independently of the doc redline —
   normal task-by-task cadence, re-run the real test suite, don't report counts without re-running
   them.
3. Propose the PDF regeneration approach and get it reviewed before running it.
4. Section-map refresh and backlog updates land after the above are approved, not before.

---

# Amendments (v2, 2026-07-27) — supersede v1 where they conflict

Codex reviewed brief v1 and raised five scope gaps. Claude verified each independently against the
source PDFs, the backlog, and the codebase (not against Codex's summary). **All five were confirmed
correct; brief v1 was wrong or incomplete in every case.** The operator then ruled on the four open
decisions. This section is authoritative.

## Accepted corrections to v1

1. **`P11-FU-3` is only half-addressed by v1.** Its acceptance criteria
   ([backlog:256-267](../plans/2026-07-23-consolidated-deferred-followups-backlog.md)) require both
   the unclipped §0.B flow **and** a decision on whether MCP brokering is supported plus its Gateway
   route and typed request/response contract. v1 addressed only the clip.
   **`P11-FEAT-GATEWAY-MCP` remains blocked** unless this effort also designs and gets approval for
   that endpoint contract. Do not infer an MCP route into the §0.B diagram.
2. **Cost attribution must NOT become `run_id` only.** v1 was wrong. `ProviderUsage`
   ([src/optimus/usage/models.py:14-20](../../../src/optimus/usage/models.py)) already carries
   `run_id`, `session_id`, `request_id`, `gateway_request_id`, and `provider_request_id`. Remove the
   **tenant/org identity** dimension only; preserve full session and request traceability — it is
   required by session resume (`P11-FU-1`) and `P9.85-FU-3`.
3. **Test Strategy v1.4 must become v1.5.** v1 omitted this document entirely, treating only
   Guardrails as needing a consistency check. That was the largest gap: Test Strategy §7 does not
   merely *describe* the hosted model, it **mandates it as normative test requirements** — e.g.
   "gateway_url set to `https://gateway.optimus.ai` (built-in): `validate_trusted_gateway()` passes"
   and "`production_mode=True` with `OPTIMUS_EXTRA_GATEWAY_ORIGINS` set: env var ignored; only
   built-in + signed tenant profile origins accepted" (rendered p.5). §8A's "One-key principle" box
   and the §7 "staging gateway" evidence path (p.6) carry the same assumption. Leaving this at v1.4
   would mandate tests for mechanisms the corrected code no longer implements.
4. **The Gateway deep-requirement inventory and README also carry hosted assumptions** and stale
   quotations; both are in scope.
5. **Blast radius is larger than v1's stated 23 test files — and larger than Codex's 32.** Claude's
   independent union across both naming patterns (`gateway.optimus.ai` / `production_mode` /
   `signed_tenant_profile_origins` / `OPTIMUS_EXTRA_GATEWAY_ORIGINS`, plus `OptimusGatewaySettings` /
   `LOCAL_PROVIDER_KEY_NAMES` / `ProviderKeyPolicy` / `validate_trusted_gateway`) finds
   **~11 production files and ~35 test files** referencing the surface. **Treat no published count as
   final — re-derive the list at implementation time** rather than inheriting 23, 32, or 35.

## Operator rulings

**1. Strict-loopback architecture — APPROVED as Codex ruled.**
- The Gateway is a deterministic local process bound to loopback.
- The agent authenticates with the shared secret exposed as `OPTIMUS_API_KEY`.
- Provider credentials live only in Gateway-owned configuration or OS credential storage, never in
  the agent process.
- Non-loopback Gateway deployment is **out of scope** for Phase 1; supporting it later requires a
  separate TLS/authentication design.
- **Remove** `production_mode`, hosted built-in origins, extra trusted origins, and signed tenant
  profiles — do **not** redefine them. (This supersedes v1's "decide what `production_mode` should
  mean now"; removing the dead concepts is cleaner than repurposing them.)
- The Gateway stays authoritative for policy and budget enforcement because it is a separate process
  from the LLM-driven agent.

*Verification note:* the repo has no Dockerfile, docker-compose, or devcontainer, so no split-container
deployment breaks under loopback-only. **Flag for the redline:** this project uses WSL2 as a Linux CI
substitute; a WSL2-agent → Windows-host-Gateway split would not be loopback. Running both inside WSL2
avoids this. State the constraint explicitly in the corrected docs rather than leaving it implicit.

**2. Credit-field migration — APPROVED as a SEPARATE reviewed subtask.**
Rename/remove `optimus_credits_debited`, `max_budget_credits`, `cost_credits`, and `credits_spent` to
USD-named fields. **Add no cross-run budget policy** in that subtask — that remains `P9.85-FU-3`.

*Claude's finding that de-risks this:* the credit fields **already carry USD values** —
[runner.py:49](../../../src/optimus/agent/runner.py) does `cost_credits=result.total_cost_usd` and
[planning_loop.py:170](../../../src/optimus/agent/planning_loop.py) does
`max_budget_credits=max(request.max_cost_usd, ...)`. This is a **rename, not a semantic change**.
It still touches 10 production files, so it gets its own review and test run.

**3. Expanded document scope — APPROVED in full.**
HLD v2.16, LLD v2.39, **Test Strategy v1.5**, Guardrails v1.1 *only if* its wording actually changes
(do not bump a version without a real text change), plus the Gateway deep-requirement inventory,
README, and `.env.example`.

**4. Branch — new branch off `main`.** Do not reuse `agent/codex/p11-gateway-tools-mcp`; this
correction is distinct enough to warrant its own branch and PR, keeping the review scoped.

## PDF regeneration — approach accepted, install still gated

Codex's source-first proposal (Markdown + CSS + SVG → Pandoc → WeasyPrint, editable sources committed
alongside the PDFs, Poppler render inspection, then filename/cover/metadata/page-count/text-extraction/
SHA-256 verification) is the right shape and satisfies the operator's "no bespoke generator" direction.
Pandoc and WeasyPrint are not installed in this environment — **installing them is a separate gated
action; ask before installing.**

## Sequencing

The MCP endpoint contract (correction 1) is a *design* deliverable with its own approval gate — it is
not unlocked by the doc correction landing. Either design and get it approved within this effort, or
leave `P11-FU-3` open and `P11-FEAT-GATEWAY-MCP` blocked, and say plainly which was chosen.

---

# Amendments (v3, 2026-07-27) — OUTRANKS v2 and v1

**This section reverses a premise both earlier versions were built on.** v1 and v2 assumed that
"one key, one balance" was inseparable from a hosted Optimus service, and therefore had to be
deleted along with the hosted framing. **That was wrong.** The operator challenged it, research
confirmed the challenge, and the goal is now being *kept* — with a different implementation.

## The corrected thesis

The Gateway does not need to *be* the billing aggregator. **An upstream aggregator already is one.**
OpenRouter (and Vercel AI Gateway) provide many models, normalized cross-provider billing, *and*
web search on the same key and same balance. So:

> One developer credential funds models **and** web search. The local Gateway keeps its real jobs —
> credential isolation from the LLM-driven agent process, policy enforcement, and cost recording —
> and delegates billing aggregation to the upstream aggregator.

**Consequence for the redline:** HLD §5A's "one key, one budget, one ledger, with many providers
behind the curtain" thesis **largely survives**. Do not delete it. Retarget it: the wallet is the
developer's aggregator account, not an Optimus tenant account. Several v1/v2 instructions that said
to strip wallet/credit language are now **too aggressive** — re-read every one of them against this
section before applying.

## Operator rulings (2026-07-27, second round)

**1. Upstream: OpenRouter is the default; Vercel AI Gateway is the allowed second option.**
If Vercel turns out to require significant effort — note its search tools are documented only via
the TypeScript AI SDK, and this is a Python project — **do not force it; file it as a backlog item.**

**2. Remove direct single-provider adapters (OpenAI, Anthropic, etc.).**
Operator's rationale, recorded verbatim in intent: *the whole point of this effort is cost control;
a provider that does not enable strong cost control is dead weight.* Aggregators give model choice,
cheap-model routing, and unified billing; direct adapters give none of that.
- Concrete scope: [providers.py:15-20](../../../src/optimus_gateway/providers.py) branches to
  `UrllibAnthropicClient` when `provider == "anthropic"`. Delete that branch and
  `src/optimus_gateway/anthropic_client.py`.
- **This is a simplification, not a loss:** OpenRouter and Vercel both speak the OpenAI-compatible
  API, so the surviving `UrllibOpenAICompatibleClient` covers both approved upstreams.
- The operator explicitly accepted that this changes the architecture: *"it is better to
  course-correct now rather than later."*

**3. Web search: retire Tavily, pending a spike.** Fulfil `/v1/tools/web/search` through the
aggregator's search on the same key. **Do not delete the Tavily adapter until the spike passes.**

**4. Search invocation: minimal model call per search.** The Gateway fulfils the typed tool by
calling the aggregator with search attached and low `max_tokens`, harvesting structured citations.
The harness gate, `ToolInvocationPolicy`, and the EvidenceLedger are unchanged — the agent never
sees the mechanism. **Rejected:** attaching `:online` to the main generation call, which would let
the model search unbidden and break HLD §8's evidence-first gate.

**5. Observability: OTel-native, Phoenix as the documented default.** The Gateway emits standard
OTLP spans; Optimus depends only on an OTel exporter. Docs recommend Arize Phoenix
(`docker run -p 6006:6006 -p 4317:4317 arizephoenix/phoenix:latest`, ~319 MB, no GPU, SQLite at
`~/.phoenix/`, or `pip install arize-phoenix`), and mention Langfuse for team scale (six services,
~4 CPU / 16 GB RAM — disproportionate for a local dev tool).
- **LangSmith is deleted from the architecture, not merely reframed.** It is currently *documented
  but never implemented*: no `langsmith`/`langchain` dependency exists in `pyproject.toml`, and
  `LANGSMITH_API_KEY` appears only in the agent-side **rejection** lists
  ([config/gateway.py:23](../../../src/optimus/config/gateway.py),
  [release/credentials.py:18](../../../src/optimus/release/credentials.py)). This change is nearly
  free in code.
- **Delete the amortized-observability-cost model outright** from HLD §11A and LLD §0A. Self-hosted
  OTel tracing has no seat or subscription cost to amortize. v1/v2 said to *preserve* that rule —
  that instruction is now void.

## Findings Codex must account for

**A. Tavily is currently a hard gate on all four tools — including the free ones.**
[providers.py:34](../../../src/optimus_gateway/providers.py) returns `None` from
`build_tool_dependencies()` unless `tavily_api_key` is present, and `None` means the Gateway exposes
**no tool routes at all**. PyPI, npm, Maven Central, and OSV.dev are free public APIs needing no key,
yet today they cannot be used without paying for Tavily. **This fail-closed bundle must be
restructured regardless of which search backend wins** — free tools must not be gated behind a paid
search credential.

**B. Only search was ever a funding problem.** Package lookup (PyPI/npm/Maven) and security advisory
(OSV) are free. Do not carry "provider funding" language into those tool sections.

**C. OpenRouter's plugin is deterministic; Vercel's is model-elected.** OpenRouter's
`plugins:[{id:"web"}]` performs the search and injects results (`search_prompt` customizes how they
are introduced). Vercel's `gateway.tools.exaSearch()` is passed as a *tool* the model chooses to
call. **Deterministic is required** for harness-gated evidence-first search — this is a substantive
reason OpenRouter is the better default, and it must survive into the design note.

**D. Why tutorials still use Tavily** (operator asked; record it so the decision is not re-litigated):
Tavily predates provider-native search (Anthropic's launched May 2025), LangChain integrated it early
with a generous free tier, it is model-agnostic, and it is a *true standalone search API* — the one
property no aggregator offers. The tutorials are not wrong, they are mostly older.

## Required spike — gate before deleting anything

**Operator has approved running this against a real OpenRouter key on live endpoints.**

Prove from **Python**, before the Tavily adapter is removed:
1. `plugins:[{id:"web"}]` returns `annotations[].url_citation` (`url`, `title`, `content`) reliably
   **when `max_tokens` is minimal** — we want evidence, not prose.
2. `include_domains`/`exclude_domains` genuinely enforce the policy allowlist.
3. Real measured cost per search vs Tavily's ~$0.008 baseline.
4. Citation quality is adequate for the evidence contract.
5. An `extract` path: confirm whether plain HTTP fetch + HTML-to-text suffices, given the LLD already
   restricts extract to URLs from a prior approved search. Exa `/contents` ($1/1k pages) is fallback.
6. Vercel AI Gateway reachability from Python — if it is more than modest effort, **backlog it**.

### Model selection — keep this simple

**Use one cheap Flash/Haiku-class model and the default engine.** The model is nearly irrelevant to
this pattern: `annotations[].url_citation` is produced by the *search plugin*, not the model, and the
generated prose is discarded. Do not build a model or engine comparison matrix.

**Operator ruling (2026-07-27):** search volume for a single-developer local tool will not reach a
scale where per-search engine pricing is a material expense — at a few hundred searches a month the
spread between engine options is well under a dollar. **Note the options; do not optimize for them
now.**

**Options noted for later, deliberately not acted on:**
- Engine pricing spread: Parallel ~$0.001/req, Exa ~$0.005/req, Perplexity ~$0.005/req. Revisit only
  if search volume ever becomes material.
- OpenRouter's default engine depends on the model — its docs list *Native* search for
  OpenAI/Anthropic/Google/Perplexity/xAI models and *Exa* as the "default for unsupported models."
  Pinning `engine` explicitly buys **predictability** (the same request always uses the same search
  backend) rather than meaningful savings. Worth doing if it is a one-line change; not worth a spike
  dimension.

**Spike scope — only the genuine unknowns:**
1. Do annotations come back with a minimal `max_tokens`? Find one value that works; do not sweep.
2. Does `include_domains`/`exclude_domains` actually enforce the allowlist? **This is a policy
   control, not a cost question — it must be verified.**
3. Is citation quality adequate for the evidence contract?
4. Does the `extract` path work via plain HTTP fetch + HTML-to-text?

Report what was measured. Do not report expectations.

## Revised sequencing

The architecture must settle **before** the documents are rewritten, so the PDFs are written once.

1. **Codex drafts an architecture design note** covering rulings 1–5 and findings A–D. Claude reviews.
2. **Run the spike.** Report real numbers, not expectations.
3. Operator approves the design note.
4. Only then: HLD/LLD/Test Strategy/Guardrails redline, folding in this architecture.
5. Then the code subtasks (strict-loopback trust boundary; USD field rename; upstream/tool
   restructuring), each reviewed and tested independently.
6. Then PDFs, section-map re-pin, README, `.env.example`, backlog dispositions.

**The v1/v2 document redline is now stale in the places noted above.** Re-derive it from this
section rather than applying the earlier tables verbatim.
