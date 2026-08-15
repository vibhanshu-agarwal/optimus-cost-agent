# Authoritative Four-Document Gateway-MCP Reversal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish v2.18/v2.41/v1.3/v1.7 as the authoritative documents, removing the retired Gateway-brokered MCP contract while preserving the live client-supplied ACP `mcpServers` path and its real-dependency evidence boundary.

**Architecture:** A new sibling, page-preserving package at `docs/sources/gateway-mcp-authoritative-document-reversal/` consumes the four frozen current PDFs and produces new versioned PDFs with the existing Pandoc/WeasyPrint/Poppler plus pypdf/ReportLab pattern. A bidirectional reversal-completeness audit gates publication: every Gateway-broker claim must be absent and every client-MCP claim must be present with current, client-owned semantics.

**Tech Stack:** Markdown, SVG, JSON, Python publication helpers (`pypdf`, `reportlab`, Pillow), Pandoc 3.1.3, WeasyPrint 61.1, Poppler 24.02.0, WSL2 Ubuntu-24.04, the approved Windows Python assembly exception, `pytest`, Ruff, Git, and SHA-256.

**Status:** Draft planning artifact. No PDF/source publication work has started. This plan is the implementation contract only after this documentation-only plan PR is reviewed and merged.

## Global Constraints

- Start the publication branch from refreshed `origin/main` with a clean status and equal `HEAD` / `origin/main` hashes. On drift, recreate or intentionally rebase before editing.
- The four old PDFs are immutable inputs, not editable outputs:

  | Input | Required SHA-256 |
  |---|---|
  | `docs/Optimus-Cost-Agent-Architecture-v2.17.pdf` | `A21BDB01BC737FA3D8EBFFBA8B8B7DF96C65101812E17F31C3C7324368D15024` |
  | `docs/Optimus-Cost-Agent-LLD-v2.40.pdf` | `0329AEF8B5392E05DDBB19AC3F76F3CE7F4FE3C4B728AEF6CBFC4DE84B324D03` |
  | `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf` | `461A720FA28576523C87C2F2F89EE1FC52C99971E51ACC22EDC85E8C375A7070` |
  | `docs/Optimus-Cost-Agent-Test-Strategy-v1.6.pdf` | `B435E55687116BD7C4D7E78B48E50D8DA9ED0801575B7B5485F262D35C1B31A4` |

- Preserve, without modification, the four old PDFs; `docs/sources/mcp-gateway-architecture-amendment/**`; the Plan 11.8 design/implementation plan; the original publication plan; and the Plan 11.15 design. They are provenance or frozen approval bytes.
- Create only new PDF filenames: `Architecture-v2.18`, `LLD-v2.41`, `Guardrails-v1.3`, and `Test-Strategy-v1.7`. Never overwrite, rename, delete, or regenerate the old PDF names.
- `P11-FEAT-GATEWAY-MCP` is retired. Remove claims of Gateway MCP profiles, discovery/call routes, remote/stdio brokering, Gateway-owned MCP credentials, binding/freshness/allowlist/budget admission, Gateway MCP accounting, Context7 Gateway probing, and Gateway-specific MCP evidence.
- `P11-FU-9` is shipped client-supplied ACP `mcpServers`. Preserve local `MCPTrustRegistry`, descriptor validation, `validate_tool_call`, `PreToolGuard.check`, untrusted tool output, `requires_mcp_http`, and `requires_mcp_stdio`. Marker descriptions must identify independently authored client-MCP dependencies, not the retired Gateway.
- Do not use a global ban on generic terms such as `MCP`, `approval`, `HTTP`, `stdio`, or `retry`: classify every claimed occurrence. A shared term alone is not ownership evidence.
- `P11-FU-12/13/14/15/22` remain closed historical won't-do custody in the pool/charter/roadmap. Do not represent their retired Gateway capabilities as current PDF scope; keep `P11-FU-14` distinct from `P11-FEAT-REGISTRY`.
- Audit base HLD v2.16 and LLD v2.39 for workspace-identity/durable-approval wording. The amendment did not add it. If base wording is stale after Plan 11.15, file the named `P11-FU-30` entry; do not add an identity correction to this PDF cycle.
- Rendered-page inspection is a separate gate. A passing Markdown diff, fragment build, or validator is insufficient: inspect changed fragments and final changed pages for fenced-div defects, overflow, clipping, tables, diagrams, headers, and page transitions.
- Record old input baseline and new output SHA-256s in `reports/plan-11-13-authoritative-document-reversal-evidence.md`. Add each new output hash/page count to the authoritative section map. Do not edit this frozen plan later to insert execution facts.
- Keep extracted text, fragments, fonts, contact sheets, and page renders only in `tmp/pdfs/plan-11-13/`; do not commit them or add publication packages to `pyproject.toml` / `uv.lock`.
- The gitignored `docs/superpowers/reviews/plan-11-13-review-checkpoints.md` is reviewer custody. If it exists, read Current State before work and do not stage it.

## File Structure

### Create during later publication execution

- `docs/sources/gateway-mcp-authoritative-document-reversal/README.md` — source/pin policy, versions, toolchain, and retired-Gateway/retained-client boundary.
- `docs/sources/gateway-mcp-authoritative-document-reversal/{print.css,build-manifest.json,changed-pages-manifest.md,reversal-completeness-audit.md,verification.md}` — reused style, exact source/output map, page mapping, bidirectional audit, and execution evidence.
- `docs/sources/gateway-mcp-authoritative-document-reversal/tools/{build_publication.py,validate_publication.py}` — copies rooted in the new package, reading only its manifest/audit.
- `docs/sources/gateway-mcp-authoritative-document-reversal/{hld-v2.18-changed-pages.md,lld-v2.41-changed-pages.md,guardrails-v1.3-changed-pages.md,test-strategy-v1.7-changed-pages.md}` — page-replacement sources.
- `docs/sources/gateway-mcp-authoritative-document-reversal/assets/` — only new HLD/LLD assets embedded by changed pages.
- `docs/Optimus-Cost-Agent-Architecture-v2.18.pdf`
- `docs/Optimus-Cost-Agent-LLD-v2.41.pdf`
- `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.3.pdf`
- `docs/Optimus-Cost-Agent-Test-Strategy-v1.7.pdf`
- `reports/plan-11-13-authoritative-document-reversal-evidence.md` — committed provenance, hash, audit, inspection, and documentation-sweep evidence.

### Modify only after publication gates pass

- `docs/superpowers/reports/2026-07-25-plan-11-authoritative-doc-section-map.md` — new version/hash/page/source-package overlay while preserving v2.17/v2.40/v1.2/v1.6 as historical pins.
- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` — close the Plan 11.13 prerequisite; retain historical closed follow-ups; add `P11-FU-30` only if Task 1 requires it.
- `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md` and `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` — replace Plan 11.13 future tense with exact output/evidence pointers while retaining historical retirement context.
- `README.md`, `docs/runbooks/**`, and `tests/unit/docs/test_open_work_pool_hygiene.py` only when the final freshness audit proves a current claim/assertion stale.

---

### Task 0: Establish the execution base and seal the old PDFs

**Files:** Read `AGENTS.md`, `CONTRIBUTING.md`, Plan 11.12, Plan 11.15 release evidence, current section map/pool/charter/roadmap, old publication package, and all four immutable PDFs. Preserve every old PDF/source listed above.

**Interfaces:** Consumes a refreshed main and four committed PDF blobs. Produces a clean branch, an immutable byte baseline, and an exact write boundary.

- [ ] **Step 1: Create a fresh dedicated publication worktree from main.**

```powershell
git fetch origin main
git worktree add -b agent/codex/plan-11-13-authoritative-doc-reversal-implementation ../optimus-cost-agent-wt-codex-11-13-publication origin/main
Set-Location ../optimus-cost-agent-wt-codex-11-13-publication
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

Expected: clean status and matching revisions in the dedicated publication worktree. If the branch/base is stale or the reviewer log has a ruling that conflicts with observed files, stop before creating sources.

- [ ] **Step 2: Confirm the frozen plan is the sole Plan 11.13 plan artifact and `P11-FU-30` remains free.**

```powershell
rg --files docs/superpowers/plans -g '*11-13*'
rg -n '^### P11-FU-30:|\| `P11-FU-30` \|' docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md
```

Expected: exactly `docs/superpowers/plans/2026-08-15-plan-11-13-authoritative-four-document-gateway-mcp-reversal.md`, no `_v2` or second Plan 11.13 artifact, and no `P11-FU-30`. A conflict requires a reviewed plan amendment; never invent a number.

- [ ] **Step 3: Compute old-PDF baselines from committed blobs, never from working-tree files.**

Run under WSL2 so binary Git output is hashed without text conversion:

```bash
BASE=$(git rev-parse HEAD)
git show "$BASE:docs/Optimus-Cost-Agent-Architecture-v2.17.pdf" | sha256sum
git show "$BASE:docs/Optimus-Cost-Agent-LLD-v2.40.pdf" | sha256sum
git show "$BASE:docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf" | sha256sum
git show "$BASE:docs/Optimus-Cost-Agent-Test-Strategy-v1.6.pdf" | sha256sum
```

Expected: the exact four Global Constraints hashes. Record the base SHA, command, and values in both future evidence files. Any mismatch blocks work; do not repin a frozen spec or accept working-tree bytes as substitute evidence.

- [ ] **Step 4: Record the exact Gateway/client claim boundary.**

```powershell
rg -n -i 'P11-FEAT-GATEWAY-MCP|MCPProfileRegistry|MCPDiscovery|MCPInvocation|/v1/tools/mcp|server/discover|MCPUsageRecord|Context7' docs/sources/mcp-gateway-architecture-amendment docs/superpowers/reports/2026-07-25-plan-11-authoritative-doc-section-map.md
rg -n -i 'P11-FU-9|mcpServers|requires_mcp_http|requires_mcp_stdio|MCPTrustRegistry|validate_tool_call|PreToolGuard' docs/sources/mcp-gateway-architecture-amendment docs/superpowers/plans/2026-08-13-plan-11-12-p11-feat-gateway-mcp-retirement.md pyproject.toml tests/integration/mcp tests/unit/mcp tests/unit/guardrails
```

Expected: each match is assigned Gateway-retired, client-retained, generic retained, historical, or procedural-only ownership in the reversal audit.

---

### Task 1: Answer the base-document workspace-identity question without widening scope

**Files:** Read HLD v2.16/v2.17, LLD v2.39/v2.40, amendment changed pages, Plan 11.15 design/release report, and current identity rows. Create a finding in the new `verification.md` and evidence report. Conditionally modify the pool/roadmap only for `P11-FU-30`.

**Interfaces:** Consumes base authoritative text and Plan 11.15 v3 contract. Produces a `NOT_REPRESENTED`, `CURRENT`, or `STALE` finding, never an identity change in these new PDFs.

- [ ] **Step 1: Extract and search base/current HLD and LLD text.**

```bash
mkdir -p tmp/pdfs/plan-11-13/extracted
pdftotext -layout docs/Optimus-Cost-Agent-Architecture-v2.16.pdf tmp/pdfs/plan-11-13/extracted/hld-v2.16.txt
pdftotext -layout docs/Optimus-Cost-Agent-Architecture-v2.17.pdf tmp/pdfs/plan-11-13/extracted/hld-v2.17.txt
pdftotext -layout docs/Optimus-Cost-Agent-LLD-v2.39.pdf tmp/pdfs/plan-11-13/extracted/lld-v2.39.txt
pdftotext -layout docs/Optimus-Cost-Agent-LLD-v2.40.pdf tmp/pdfs/plan-11-13/extracted/lld-v2.40.txt
rg -n -i 'workspace identity|durable approval|st_ctime|st_ino|workspace_digest|revalidate_workspace_identity|WorkspaceIdentity' tmp/pdfs/plan-11-13/extracted
```

Expected: page-level evidence. The already-established amendment result is zero HLD changed-page hits and LLD revalidation only for Gateway URL/redirect/profile policy; neither is workspace identity.

- [ ] **Step 2: Compare each base hit to v3 and record one deterministic finding.**

Compare page text to Plan 11.15: v3 excludes `st_ctime_ns` from stable identity, uses tri-state Git context and immediate-root topology, retries transient probes at most three times, preserves approval on unavailable evidence, and makes v2-to-v3 promotion observable. Record exactly one of:

1. `NOT_REPRESENTED` — no base HLD/LLD mechanism exists;
2. `CURRENT` — base text is compatible, with the exact cited clause; or
3. `STALE` — base text names a superseded mechanic, with the exact mismatch.

`NOT_REPRESENTED` is a required successful result, not a skipped audit.

- [ ] **Step 3: Create `P11-FU-30` only for a `STALE` result.**

Add `P11-FU-30 — Authoritative Workspace-Identity Contract Alignment` to the tracked/not-yet-scheduled pool and roadmap. It must name the stale source page/text, Plan 11.15 evidence, required v3 properties, its future authoritative-document owner, and the explicit rule that Plan 11.13 preserves this wording. If the result is `NOT_REPRESENTED` or `CURRENT`, create no row. In all cases, do not add workspace identity to v2.18/v2.41 changed pages.

---

### Task 2: Create a sibling reversal package and enforce immutable inputs

**Files:** Create all new-package skeleton files. Read/copy `print.css`, both helpers, manifest, and mapping from `docs/sources/mcp-gateway-architecture-amendment/`. Preserve the historical package unchanged.

**Interfaces:** Consumes v2.17/v2.40/v1.2/v1.6 as sources. Produces self-contained reversal tooling and exact page maps for v2.18/v2.41/v1.3/v1.7.

- [ ] **Step 1: Copy rather than repurpose the proven pipeline.**

Copy `print.css`, `tools/build_publication.py`, and `tools/validate_publication.py` to the sibling package. Update only copies to root manifests, redline/audit references, and temporary paths in the new package. Verify:

```powershell
git diff -- docs/sources/mcp-gateway-architecture-amendment
```

Expected: no historical-source diff.

- [ ] **Step 2: Write the exact new build manifest.**

| Document | Source | Output | Expected pages | Replacement pages |
|---|---|---|---:|---|
| HLD | v2.17 | v2.18 | 13 | `1, 3, 4, 7, 9, 10, 11, 12` |
| LLD | v2.40 | v2.41 | 40 | `1-5, 20-21, 26-40` |
| Guardrails | v1.2 | v1.3 | 16 | `1, 4, 6, 8, 10-12, 14, 16` |
| Test Strategy | v1.6 | v1.7 | 14 | `1-3, 5-6, 8-14` |

Set each source to its full immutable repo path/hash; set every output filename, embedded title, cover, and running header to the new version. Carry unlisted pages through the existing safe header/version stamping path. Output hashes are populated only after real assembly.

- [ ] **Step 3: Add the old-PDF integrity validator gate.**

The copied validator must compare inputs to Task 0's four hashes. Before commit, run:

```bash
sha256sum docs/Optimus-Cost-Agent-Architecture-v2.17.pdf docs/Optimus-Cost-Agent-LLD-v2.40.pdf docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf docs/Optimus-Cost-Agent-Test-Strategy-v1.6.pdf
git diff --exit-code "$BASE" -- docs/Optimus-Cost-Agent-Architecture-v2.17.pdf docs/Optimus-Cost-Agent-LLD-v2.40.pdf docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf docs/Optimus-Cost-Agent-Test-Strategy-v1.6.pdf
```

Expected: four expected values and zero frozen-file diff. Any mismatch fails publication.

---

### Task 3: Make reversal completeness a two-way executable audit

**Files:** Create `reversal-completeness-audit.md`. Modify new `build-manifest.json` and copied validator only for its explicit marker/audit inputs. Read historical completeness audit, all four changed sources, Plan 11.12 boundaries, and retained client tests/configuration.

**Interfaces:** Consumes every historical amendment claim/cluster and retained client seam. Produces a human-readable and validator-enforced inverse census.

- [ ] **Step 1: Classify every original amendment row.**

Seed the audit with all 26 historical `Design §12 required-evidence rows` and all `HLD-MCP-*`, `LLD-MCP-*`, `GR-MCP-*`, and `TS-MCP-*` clusters. For each, record source/PDF page, exact claim, former owner, disposition (`REMOVE_GATEWAY`, `RESTORE_PRE_AMENDMENT`, or `REWRITE_CLIENT_CURRENT_STATE`), candidate page, and final extracted-PDF proof. No generic claim may escape classification.

- [ ] **Step 2: Fail on surviving Gateway claims.**

The negative inventory includes `P11-FEAT-GATEWAY-MCP`, `MCPProfileRegistry`, `MCPDiscoveryBroker`, `MCPInvocationBroker`, `MCPConnectionManager`, `/v1/tools/mcp/discover`, `/v1/tools/mcp/call`, `server/discover`, Gateway remote/stdio profiles, `MCPUsageRecord`, Gateway Context7 probes, profile binding/revision admission, and normative Gateway-MCP rows. Use page/phrase context, not a global `MCP` ban. List every approved historical/procedural occurrence outside the new PDFs with its path and reason.

- [ ] **Step 3: Fail on missing client claims.**

Require candidate evidence for client-supplied ACP `mcpServers` / `P11-FU-9` separation; local trust registration/descriptor validation; `validate_tool_call` plus `PreToolGuard.check` before client execution; untrusted tool outputs; and both HTTP/stdio marker names with independently authored client-server meaning. The prior v1.6 phrase `Real Gateway + ...` is intentionally not retained: preserving the capability and marker while correcting ownership is a pass.

- [ ] **Step 4: Prove the audit catches both directions before final assembly.**

In an untracked scratch copy, make a Gateway marker survive and separately remove a required client anchor. Run the validator: each case must fail its relevant direction. Delete the scratch copy, run the complete source audit, and record the two expected failures plus final pass in `verification.md`.

---

### Task 4: Author all four replacement-page sets

**Files:** Modify the four new changed-page files, new assets, new mapping/audit/README. Preserve all unlisted input pages and every historical source asset.

**Interfaces:** Consumes Tasks 1-3. Produces exact page replacements with no Gateway/client conflation.

- [ ] **Step 1: Author HLD v2.18 pages and diagrams.**

Remove the v2.17 Gateway-MCP branch: Gateway-to-MCP edges, Gateway MCP credentials/profiles, profile/binding/allowlist/budget claims, discovery/pagination, Context7, and MCP accounting. Retain the one-key model for model/provider access and ordinary Gateway boundaries. Where client MCP is described, say that ACP `mcpServers` are client supplied and local trust/descriptor validation plus pre-tool approval happen before client-side execution. No retired Gateway MCP route or credential returns; no Plan 11.15 identity wording is added.

- [ ] **Step 2: Author LLD v2.41 pages and component flow.**

Remove Gateway MCP components, typed discovery/call API, `MCPProfileRegistry` lifecycle, adapters, profile state, result/usage writers, MCP retry/capacity contract, and Gateway-MCP normative rows. Preserve only factual non-MCP Gateway routes/usage/guardrails. Retained client text must cover local validation, pre-tool guard, and inert/untrusted outputs; it must not convert a former profile concept into a client claim.

- [ ] **Step 3: Author Guardrails v1.3 pages.**

Remove Gateway-MCP split agency, direct-bearer residual, profiles/credentials/containment, discovery/pagination, Gateway accounting, indeterminate Gateway call, Context7, and normative Gateway traceability. Retain general Plan/Chat-versus-Agent approval, deterministic pre-tool checks, output distrust, and client-MCP validation where factual. Keep OWASP material `REFERENCE — Cross-cutting`; do not relabel retired Gateway ownership as unverified client scope.

- [ ] **Step 4: Author Test Strategy v1.7 pages.**

Delete Gateway broker tiers, Context7 probe, Gateway profile/transport/accounting/retry matrices, and retired normative claims. Retain `P11-FU-9` as shipped and separate from registry/session resume. Preserve `requires_mcp_http` / `requires_mcp_stdio`, naming independently authored client-MCP servers rather than a real Gateway. ACP protocol claims still require independent `acpx`; a project-authored client is never protocol-layer evidence.

- [ ] **Step 5: Update every document-control/version surface.**

Set new cover text, metadata, headers, page fields, README, audit citations, and mapping to v2.18/v2.41/v1.3/v1.7. Guardrails v1.3 appends a reversal event while retaining v1.2 amendment history. Do not erase historical v1.2 facts.

---

### Task 5: Render, visually inspect, assemble, and validate

**Files:** Create new PDFs and untracked `tmp/pdfs/plan-11-13/**`; modify new package audit/verification/manifest only when a real defect requires it. Preserve all frozen inputs.

**Interfaces:** Consumes authored pages/maps/assets. Produces visual and mechanical evidence for four new PDFs.

- [ ] **Step 1: Render exact fragments in WSL2.**

Use Pandoc 3.1.3 and WeasyPrint 61.1 with copied CSS. Render under `tmp/pdfs/plan-11-13/build/`; put fonts under `tmp/pdfs/plan-11-13/fonts/`. Fragment count must equal Task 2's exact replacement list; fix source/CSS instead of changing a map to fit output.

- [ ] **Step 2: Inspect every rendered fragment page.**

Use Poppler at 150 dpi into `tmp/pdfs/plan-11-13/rendered-fragments/`. Inspect every page for fenced-div rendering, overflow/clipping, wrapping, SVG bounds/connectors, header/footer collisions, blanks, and transitions. Record inspector, UTC time, document, page, verdict, and repair in `verification.md`.

- [ ] **Step 3: Assemble only four new filenames.**

Use the approved Windows Python/pypdf/ReportLab assembly exception. The script copies input pages unless listed for replacement, stamps new versions safely, sets exact metadata, and writes only v2.18/v2.41/v1.3/v1.7 files. It must never have an old filename as output.

- [ ] **Step 4: Inspect rendered final changed pages and adjacent carried pages.**

Render final PDFs at 150 dpi to `tmp/pdfs/plan-11-13/rendered-final/`. Visually inspect every changed page plus its adjacent carried page. Record the page-level ledger separately from fragment inspection and rerender until every entry passes.

- [ ] **Step 5: Run final mechanical and semantic validation.**

The copied validator must prove page count/geometry, title/metadata, new version on every page, source-page preservation, old hashes, SVG safety, two-way audit, and required/forbidden extracted text. Extract final PDFs and rerun audit searches. Any unclassified row, surviving Gateway claim, absent client claim, old-version leak, or hash mismatch blocks publication.

---

### Task 6: Make new versions authoritative in living pointers

**Files:** Create Plan 11.13 evidence report. Modify section map/pool/charter/roadmap and only freshness-proven current-state files.

**Interfaces:** Consumes Tasks 1, 3, and 5. Produces pin-ready output identities and closed Plan 11.13 dependency without rewriting history.

- [ ] **Step 1: Record new PDF identities.**

```bash
sha256sum docs/Optimus-Cost-Agent-Architecture-v2.18.pdf docs/Optimus-Cost-Agent-LLD-v2.41.pdf docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.3.pdf docs/Optimus-Cost-Agent-Test-Strategy-v1.7.pdf
pdfinfo docs/Optimus-Cost-Agent-Architecture-v2.18.pdf
pdfinfo docs/Optimus-Cost-Agent-LLD-v2.41.pdf
pdfinfo docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.3.pdf
pdfinfo docs/Optimus-Cost-Agent-Test-Strategy-v1.7.pdf
```

Record exact output hash, page count, title, producer, input/hash, replacement map, visual ledger, and audit result in the evidence report and section map. These are execution facts, not estimated placeholders.

- [ ] **Step 2: Move the section map to current versions.**

Replace the Task-10 amendment overlay as current state with a v2.18/v2.41/v1.3/v1.7 table containing filename, version, page count, SHA-256, changed-page count, reversal package, and current owner summary. Keep old versions/hashes as immutable provenance. Explicitly distinguish retired Gateway MCP, retained `mcpServers`, and registry publication identity.

- [ ] **Step 3: Close only the live Plan 11.13 prerequisite.**

Pool, charter, and roadmap replace "Plan 11.13 must reverse" with this plan/evidence report and exact four versions/hashes before registry/v1.0. Keep retired feature and Plans 11.8/11.11/11.12 historical. Keep five closed Gateway follow-ups historical; do not reopen/reassign them. If `P11-FU-30` exists, name owner/acceptance boundary and say this publication did not fix it.

- [ ] **Step 4: Conduct a complete documentation freshness audit.**

Search `README.md`, section map, pool, charter, roadmap, `docs/runbooks/`, reports, and both source roots. Classify each match as live pointer to update, frozen/historical provenance to retain, or procedural evidence to retain. Specifically verify client `mcpServers`, `P11-FU-9`, both MCP markers, and registry separation remain current.

---

### Task 7: Prove final integrity and request independent review

**Files:** Test/read all Plan 11.13 sources/outputs and immutable inputs. Modify only a concrete failed-gate source/document/test. Preserve all frozen artifacts and scratch output.

**Interfaces:** Consumes completed sources, PDFs, map, live pointers, and evidence. Produces a reviewable documentation-publication PR.

- [ ] **Step 1: Re-run immutable-input proof after all final edits.**

Repeat Task 0 committed-blob hashes and Task 2 working-tree `sha256sum` / `git diff --exit-code`. Evidence records before/after equality. A mismatch blocks commit.

- [ ] **Step 2: Run source/document quality gates.**

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
uv run --frozen ruff check .
git diff --check
git status --short
```

Also rerun the final publication validator and extracted-text/reversal commands. Expected: green hygiene/Ruff/validators, no whitespace error, no unclassified audit row, and no untracked artifact except ignored scratch material.

- [ ] **Step 3: Review the mutation boundary.**

```powershell
git diff --name-status origin/main...HEAD
git diff -- docs/Optimus-Cost-Agent-Architecture-v2.17.pdf docs/Optimus-Cost-Agent-LLD-v2.40.pdf docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf docs/Optimus-Cost-Agent-Test-Strategy-v1.6.pdf
git diff -- docs/sources/mcp-gateway-architecture-amendment
```

Expected: new PDFs/source package/evidence/listed living pointers only; both preservation diffs empty; reviewer log and `tmp/pdfs/plan-11-13/**` absent from staging.

- [ ] **Step 4: Commit and open a draft review PR.**

```powershell
git add docs reports tests/unit/docs/test_open_work_pool_hygiene.py
git commit -m "docs: reverse retired Gateway MCP authority"
git push -u origin agent/codex/plan-11-13-authoritative-doc-reversal-implementation
gh pr create --draft --base main --head agent/codex/plan-11-13-authoritative-doc-reversal-implementation --title "docs: reverse retired Gateway MCP authority" --body "Plan 11.13 publishes the authoritative-document reversal. The PR records exact v2.18/v2.41/v1.3/v1.7 SHA-256s, proves pinned predecessor PDFs unchanged, passes a bidirectional Gateway-removal/client-retention audit, and includes rendered-page inspection evidence."
```

The PR must state exact output hashes, old-PDF proof, two-way audit, rendered-page inspection, Plan 11.15 base-identity finding, and conditional `P11-FU-30` custody. It remains draft until independent review approves the PDFs, hashes, audit, identity finding, and current-state sweep.

## Definition of Done

- [ ] New v2.18/v2.41/v1.3/v1.7 PDFs have exact recorded SHA-256s, valid metadata/version/page count, and completed rendered-page inspection.
- [ ] The four v2.17/v2.40/v1.2/v1.6 inputs equal their committed-blob baselines and have no working-tree diff.
- [ ] The historical amendment package is unchanged; the sibling reversal package is reproducible and self-contained.
- [ ] The audit proves every Gateway-brokered claim absent and every client-MCP/marker claim retained with accurate ownership.
- [ ] Base HLD/LLD identity result is recorded; a stale finding has the named `P11-FU-30` owner without widening this plan.
- [ ] Section map, pool, charter, roadmap, and every proven stale live pointer cite new versions/hashes and retain historical facts.
- [ ] Publication validator, text audit, immutable-input proof, pool hygiene, Ruff, `git diff --check`, and mutation-boundary checks pass.
- [ ] A draft PR contains the evidence report and awaits independent review; it does not claim merger, v1.0 readiness, or unrun live tiers.

## Plan Self-Review

| Requirement | Coverage |
|---|---|
| Fresh base/unclaimed identifiers | Task 0 |
| Committed-blob old-PDF integrity baseline | Tasks 0, 2, 7 |
| Gateway/client non-conflation | Global Constraints; Tasks 0, 3, 4 |
| Bidirectional reversal audit | Task 3; Tasks 5 and 7 |
| Existing pipeline without provenance loss | Task 2 |
| New versions/hashes in evidence and map | Tasks 5-6 |
| Rendered-page inspection | Task 5 |
| Plan 11.15 base-identity answer and custody | Task 1; Task 6 |
| Closed retirement follow-ups and live pointers | Task 6 |
| Review-ready draft PR | Task 7 |

No task modifies production code, client-MCP runtime/markers, frozen Plan 11.8/11.15 bytes, old PDFs, or historical amendment sources. The only permitted new deferral is named `P11-FU-30` when Task 1 proves it necessary.

## Execution Handoff

After this plan is independently reviewed and merged, execute it from a dedicated fresh worktree using `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Do not start publication on this plan-PR branch. The executor reads the review checkpoint log, verifies every input pin from disk, then works the unchecked tasks in order.
