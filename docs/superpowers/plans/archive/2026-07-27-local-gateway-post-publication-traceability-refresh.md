# Local Gateway Post-Publication Traceability Refresh Plan

> **Blocking audit notice (2026-07-27):** The published v3 PDFs failed a source-to-output
> completeness audit. Co-located normative sections were lost from regenerated pages without redline
> authorization. This traceability plan is paused until a separate publication-completeness repair
> restores the source content, adds a mandatory completeness gate, rebuilds all four PDFs, and
> receives independent review. The current map changes in this worktree are not authoritative.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repository’s operational guidance, authoritative source pins, deep Gateway
requirement inventory, and open-work custody agree with the published local-Gateway v3 documents.

**Architecture:** Treat the four newly published PDFs as the authoritative source set. Re-extract
every regenerated section from the final PDFs, while retaining a carried section’s existing
requirement rows only when the publication verification proves its body is unchanged below the
header. Keep implementation work in its existing Plan 11 feature identities; this plan updates
documentation and custody only.

**Tech Stack:** Markdown, JSON, Python 3.12, pypdf, Poppler `pdftotext`, Git, pytest, Ruff.

## Global Constraints

- The v3 amendments in
  `docs/superpowers/reports/2026-07-27-local-gateway-architecture-correction-brief.md` outrank v2
  and v1.
- The source set is HLD v2.16, LLD v2.39, Test Strategy v1.5, and Guardrails v1.1.
- `P11-FU-3` remains open for the unresolved MCP disposition/contract; the repaired LLD diagram
  must not imply an MCP endpoint.
- `P11-FEAT-GATEWAY-MCP` remains blocked.
- `P9.85-FU-3` becomes architecture-unblocked but remains undesigned and unscheduled.
- OpenRouter is the approved default upstream. Vercel remains a bounded model-endpoint option
  pending a modest-effort Python transport check. Direct-provider retirement remains separate
  implementation work.
- Tavily remains temporary migration code until OpenRouter replacement acceptance and rollback
  review pass. Package and OSV routes must remain independent of search configuration.
- OpenTelemetry/OTLP with Phoenix as the documented default replaces LangSmith. No amortized
  observability charge remains.
- This plan does not change production or test code, rebuild PDFs, alter frozen plans, optimize PDF
  size, or correct the non-blocking LLD page-2 diagram-footnote border overlap.
- `.env.example` must retain `OPTIMUS_PRODUCTION_MODE=false` as temporary migration configuration
  required by the current `OptimusGatewaySettings.from_env()` strict-origin behavior. Label it as
  an implementation compatibility setting, not the target architecture; remove it only when the
  strict-loopback code change lands under `P11-FEAT-GATEWAY-CORE`.
- `.env.gateway.example` may be clarified to prevent contradictory setup guidance, but it must
  continue to describe credentials required by the current implementation until the separately
  reviewed provider/search migration lands.

---

### Task 1: Re-pin and reconcile the authoritative section map

**Files:**
- Modify:
  `docs/superpowers/reports/2026-07-25-plan-11-authoritative-doc-section-map.md`
- Read:
  `docs/sources/local-gateway-architecture-v3/build-manifest.json`
- Read:
  `docs/sources/local-gateway-architecture-v3/verification.md`

**Interfaces:**
- Consumes: final PDF filenames, page counts, SHA-256 values, section titles, render findings, and
  settled feature ownership.
- Produces: the authoritative source pin and section-level ownership map consumed by Task 2.

- [ ] **Step 1: Replace all four source pins.**

Use these exact final pins:

| Document | Pages | SHA-256 |
|---|---:|---|
| `docs/Optimus-Cost-Agent-Architecture-v2.16.pdf` | 13 | `B00F92DF7E50E4C642A5FEC3D2C3B5893BC05991E2BACA900FB9AAFD8F7CF564` |
| `docs/Optimus-Cost-Agent-LLD-v2.39.pdf` | 40 | `2F86FFD62EB153CCE0CFDDC98631F046202BC0E9CBB17FC5F35268E78627CAA8` |
| `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf` | 16 | `DE8987CF44897C47563FC48E2E43832180F117A0BBCBE45E4B6E26C68059035A` |
| `docs/Optimus-Cost-Agent-Test-Strategy-v1.5.pdf` | 14 | `A5629907AC477880E86D7AA217FF01FCE92825E057F876AA5CCFBF6476018EBA` |

- [ ] **Step 2: Reconcile render findings and ownership.**

Record the LLD §0.B clip as resolved by the complete v2.39 component flow. Preserve the separate
MCP source-contract gap under `P11-FU-3`, with no MCP route inferred. Replace the stale
LangSmith/amortized-cost finding with the OTel/OTLP/Phoenix contract. Mark package/advisory routes
as implemented by merged Plan 11.2 while retaining the new search-independence migration work
under `P11-FEAT-GATEWAY-TOOLS`.

- [ ] **Step 3: Refresh every section citation and note.**

Update HLD, LLD, Guardrails, and Test Strategy version citations throughout the map. Re-read each
changed section’s title, surface, owner, and note from the final PDF; do not mechanically retain a
hosted-origin, tenant-wallet, direct-provider, Tavily-primary, LangSmith, or amortized-cost note.

- [ ] **Step 4: Verify the map.**

Run:

```powershell
rg -n "v2\.15|v2\.38|v1\.4|Guardrails v1\.0|gateway\.optimus\.ai|signed tenant|LangSmith|amortized" `
  docs/superpowers/reports/2026-07-25-plan-11-authoritative-doc-section-map.md
```

Expected: no stale source pin or superseded architecture claim. Historical explanation is allowed
only when explicitly labelled historical and paired with the current disposition.

### Task 2: Refresh the deep Gateway requirement inventory

**Files:**
- Modify:
  `docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md`
- Read: the four final PDFs from Task 1
- Read:
  `docs/superpowers/reports/2026-07-27-local-gateway-architecture-document-redline-v3.md`
- Read:
  `docs/superpowers/specs/2026-07-27-local-gateway-aggregator-architecture-design.md`
- Read:
  `docs/superpowers/reports/2026-07-27-openrouter-deterministic-web-search-spike.md`

**Interfaces:**
- Consumes: Task 1’s source pins and section ownership.
- Produces: exact current-source requirement rows and dispositions for future Plan 11
  specifications and implementation plans.

- [ ] **Step 1: Re-hash and extract the final PDFs.**

Run SHA-256 verification against Task 1’s values and extract each PDF through pypdf and Poppler.
Record the current branch baseline and the four matching digests at the top of the inventory.

- [ ] **Step 2: Classify rows by changed versus carried source body.**

Use `docs/sources/local-gateway-architecture-v3/build-manifest.json` to identify replacement pages.
For a carried page, retain an existing exact quotation only after confirming the cited body appears
in the final PDF. For a replacement page, delete the old row and re-extract the current normative
statement; a version-number substitution is not sufficient.

- [ ] **Step 3: Re-extract the Gateway-owned sections to exhaustion.**

Cover the current counterparts of HLD §§5A, 11, and 11A; LLD §§0–0A, 6, 9C, 9D, and the named
endpoint block; Guardrails §9; and Test Strategy §7. Required current dispositions include:

- local shared-secret authentication and strict loopback;
- OpenRouter default and bounded Vercel model-endpoint option;
- OpenAI-compatible upstream transport with direct-provider retirement in a separate lane;
- deterministic minimal-call search and direct bounded extract;
- independent package and OSV availability;
- provider-reported usage and USD cost;
- OTel/OTLP with Phoenix and no LangSmith/amortized charge;
- full run/session/request attribution without tenant/org/project identity;
- separate USD field migration;
- open `P11-FU-3` MCP contract gap without an inferred endpoint; and
- architecture-unblocked but undesigned `P9.85-FU-3`.

- [ ] **Step 4: Reconcile cross-cutting and preserve-only rows.**

Re-check every Tier 2–4 row against the final PDF body. Update evidence aliases and named findings
so the repaired §0.B source is extractable, Plan 11.2 package/advisory capability is closed, and
current search/observability migration claims point to future evidence rather than old LangSmith or
Tavily-primary tests.

- [ ] **Step 5: Recalculate counts and validate dispositions.**

Recompute every section subtotal and the total inventory row count. Confirm every table row has a
non-empty disposition, stable owner, and named evidence target. Remove the old invariant that all
budget rows are “parked; operator decision pending”; replace it with the settled
architecture-unblocked/implementation-unscheduled disposition.

- [ ] **Step 6: Scan for stale extracted contracts.**

Run:

```powershell
rg -n "gateway\.optimus\.ai|OAuth / device|tenant/user/project|signed_tenant|production_mode|LangSmith|allocated or amortized" `
  docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md
```

Expected: no current-source requirement row contains a superseded hosted or LangSmith contract.
Any historical mention must be explicitly labelled as superseded history rather than normative
source wording.

### Task 3: Correct operator guidance and environment examples

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify only as described below: `.env.gateway.example`

**Interfaces:**
- Consumes: the approved architecture and current implementation boundaries.
- Produces: operational guidance that distinguishes the settled target architecture from temporary
  migration code.

- [ ] **Step 1: Update all authoritative document links.**

Point the README documentation table to HLD v2.16, LLD v2.39, Test Strategy v1.5, and Guardrails
v1.1.

- [ ] **Step 2: Remove hosted-Gateway operator instructions.**

Replace every `https://gateway.optimus.ai` example with the loopback Gateway, delete the hosted Zed
example, retain `OPTIMUS_PRODUCTION_MODE=false` only as a clearly labelled temporary
current-implementation compatibility setting, and state that an agent and Gateway running under
WSL2 must share the same WSL2 network namespace.

- [ ] **Step 3: Align upstream and tool guidance.**

Document OpenRouter as the approved default. Remove direct OpenAI and Anthropic setup recipes.
Describe Vercel as a future bounded option pending the Python transport check, not a configured
Phase 1 search backend. State that Tavily remains temporary current-implementation migration
configuration until replacement acceptance and rollback review pass; do not describe it as the
target architecture.

- [ ] **Step 4: Update the examples without breaking the current launcher path.**

Keep `OPTIMUS_PRODUCTION_MODE=false` in `.env.example` and label it as temporary migration
configuration required by the current direct `OptimusGatewaySettings.from_env()` path; assign its
removal to the strict-loopback code change under `P11-FEAT-GATEWAY-CORE`. Keep the two agent-facing
Gateway variables, Redis URL, and local model alias. In `.env.gateway.example`, remove the
Anthropic-native recipe, label Tavily as temporary migration-only configuration required by the
current tool bundle, and preserve the variables the current launcher still consumes.

- [ ] **Step 5: Verify operational prose.**

Run:

```powershell
rg -n "v2\.15|v2\.38|v1\.4|gateway\.optimus\.ai|OpenAI direct|Anthropic-native|hosted gateway" `
  README.md .env.example .env.gateway.example
rg -n "^OPTIMUS_PRODUCTION_MODE=false$|temporary migration|current implementation" `
  README.md .env.example
```

Expected: no stale recommendation remains. `OPTIMUS_PRODUCTION_MODE=false` appears in
`.env.example` as an explicitly temporary current-implementation compatibility setting, with
removal owned by `P11-FEAT-GATEWAY-CORE`. A Tavily mention is allowed only as an explicit temporary
migration note.

### Task 4: Record backlog and feature-slice dispositions

**Files:**
- Modify:
  `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`

**Interfaces:**
- Consumes: published PDF evidence, merged Plan 11.2 evidence, and Tasks 1–3 dispositions.
- Produces: single-source-of-truth custody for all remaining implementation work.

- [ ] **Step 1: Correct already-merged Plan 11.2 state.**

Record `P11-FEAT-GATEWAY-TOOLS` and `P11-FU-2` as closed by PR #88 / merge `4590dbf`, citing the
checked Plan 11.2 Definition of Done and its named evidence reports.

- [ ] **Step 2: Partially close and narrow `P11-FU-3`.**

Record the v2.39 §0.B clip and hosted-content repair as complete with the final PDF digest. Keep the
item open solely for the operator’s MCP support decision and, if supported, the route plus typed
request/response contract. Keep `P11-FEAT-GATEWAY-MCP` blocked.

- [ ] **Step 3: Unblock but do not design `P9.85-FU-3`.**

Replace the old architecture-blocked disposition with: local Gateway budget authority is now
settled and the architecture conflict is resolved; the cumulative session/project spend policy
remains open, undesigned, and unscheduled under a future budget-governance plan.

- [ ] **Step 4: Assign architecture-migration custody to existing feature identities.**

Update the feature-slice table so:

- `P11-FEAT-GATEWAY-CORE` owns strict-loopback completion, OpenAI-compatible aggregator transport,
  provider-reported accounting, direct-adapter retirement, and the bounded Vercel Python check;
- `P11-FEAT-GATEWAY-TOOLS` owns deterministic search/direct extract, route-specific dependency
  availability, replacement acceptance, and Tavily rollback-reviewed retirement; and
- `P11-FEAT-GATEWAY-COST-OBS` owns OTel/OTLP-to-Phoenix and the separately reviewed USD field
  migration.

Do not reopen or edit the frozen Plan 11.1/11.2 implementation plans; new Plan 11.x numbers are
assigned only when these follow-ups are picked up.

- [ ] **Step 5: Verify custody.**

Run:

```powershell
rg -n "P9\.85-FU-3|P11-FU-2|P11-FU-3|P11-FEAT-GATEWAY-(CORE|TOOLS|COST-OBS|MCP)|OpenRouter|Tavily|Vercel|OTLP|Phoenix" `
  docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md
```

Expected: each remaining item has one state, one stable owner, and no “unowned” disposition.

### Task 5: Verify and commit the traceability refresh

**Files:**
- Verify all files modified by Tasks 1–4.

**Interfaces:**
- Consumes: completed documentation and custody changes.
- Produces: one reviewable follow-up commit ready for the user’s push/PR decision.

- [ ] **Step 1: Verify source pins mechanically.**

Run the publication validator with the documented temporary font directory and confirm all four
PDF page counts, US Letter geometry, metadata, SHA-256 values, per-page versions, critical text
anchors, and SVG geometry checks pass.

- [ ] **Step 2: Verify inventory and map citations.**

Run pypdf/Poppler extraction checks proving every quoted current-source statement can be found in
the cited final PDF after whitespace normalization. Verify requirement totals and reject blank
disposition, owner, or evidence cells.

- [ ] **Step 3: Run repository gates.**

Run:

```powershell
python -m ruff check .
python -m pytest -q
git diff --check
```

Expected: Ruff clean, full pytest exit code 0, and no whitespace errors.

- [ ] **Step 4: Audit the staged diff.**

Confirm the staged set contains only the plan, README/environment guidance, section map, deep
inventory, and consolidated backlog. Confirm no PDF, production code, test code, frozen plan, or
temporary render artifact is staged.

- [ ] **Step 5: Create the follow-up commit.**

Run:

```powershell
git commit -m "docs: refresh gateway architecture traceability"
```

Do not push or create a PR until the user explicitly selects option 2.
