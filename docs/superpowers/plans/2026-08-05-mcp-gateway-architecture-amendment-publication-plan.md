# MCP Gateway Architecture Amendment Publication Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the approved MCP Gateway architecture amendment into the four authoritative PDFs
and Plan 11 charter, with complete source, custody, validation, and preservation evidence.

**Architecture:** The approved design and consolidated redline are the wording contract. Publication
uses the existing page-preserving splice pipeline: author only changed pages and diagrams, copy
untouched pages from pinned PDFs, assemble new versioned PDFs, and prove content, geometry, visual,
and digest integrity. This plan changes architecture documentation only; it does not implement MCP
runtime, Gateway routes, profiles, transports, accounting, or tests.

**Tech Stack:** Markdown, SVG, JSON, Python, Pandoc 3.1.3, WeasyPrint 61.1, Poppler 24.02.0,
WSL2 Ubuntu-24.04, DejaVu Sans/Mono, Lato, Ruff, pytest.

## Global Constraints

- This plan is not executable until the operator approves both the consolidated design and this
  publication plan.
- The normative design is
  `docs/superpowers/specs/2026-08-05-mcp-gateway-brokering-architecture-amendment-design.md`.
- The exact redline source is
  `docs/superpowers/reports/2026-08-05-mcp-gateway-architecture-document-redline-draft.md`.
- The required external-guidance compilation is
  `docs/superpowers/reports/2026-08-05-mcp-gateway-security-best-practices-reference.md`.
- Do not implement or modify Python production/runtime code, tests for runtime behavior, MCP
  routes, profile models, transport adapters, or ledger schemas in this lane.
- Do not edit frozen implementation plans. The Plan 11 milestone charter and consolidated
  open-work pool may change only as the approved architecture amendment and custody rules require.
- Preserve the pinned source PDFs. Create new versioned outputs; do not overwrite or delete the
  v2.16/v2.39/v1.1/v1.5 sources.
- The agent-facing invariant is zero upstream credentials in the agent process, not one upstream
  credential in the Gateway.
- Every no-MCP exclusion must be replaced, not silently deleted. Every deferred item must retain a
  reason and named owner.
- The profile freshness control is enforced by both agent and Gateway. Detected drift remains a
  denial; a recoverable failed refresh serves only the last approved binding with a stale marker.
  Direct bearer callers remain subject to profile state, binding, allowlist, resource, and budget
  checks.
- Existing `GatewayUsage`/`ProviderUsage` settled-cost contracts remain unchanged; MCP accounting
  is described as a separate envelope/row.
- Tool arguments are the only agent-originated payload sent to MCP servers. System prompts,
  conversation history, policy text, and approval records never cross.
- Target MCP `2026-07-28` uses the official Go SDK v1.7.0 release as the support citation and
  immutable `f817239f4d6b1efff2c4dfc2f7af85c985d73076` only as the frozen wire-content snapshot.
  At that commit the 2026 material is under `schema/draft/`, not a released per-version schema
  directory; the plan must never mislabel that snapshot as final specification publication.
  Remote HTTP credential profiles use per-request `_meta`, `server/discover`, `tools/list`, and
  `tools/call` at `2026-07-28`, with no initialization fallback, client ping, protocol session, or
  standalone GET stream. This breaking HTTP floor yields the narrow
  `mcp.protocol_version_unsupported` disposition rather than legacy downgrade. Docker-contained
  stdio profiles instead use discovery-first modern/legacy negotiation. The remote rule deliberately
  narrows the Go SDK's ability to negotiate down to `2025-11-25` or earlier.
- Context7 is the named remote-compatibility dependency of `P11-FEAT-GATEWAY-MCP`. Its public
  Streamable HTTP configuration is not proof of `2026-07-28` support. No document may claim
  Context7 reachability until an authenticated Gateway-originated live probe of the configured
  endpoint establishes the exact version and tools capability; another HTTP server or a fake does
  not discharge that dependency.
- External MCP logging is deprecated and closed in v1. It must not be confused with, feed, or
  alter Optimus's append-only audit logging and telemetry.
- Every generalized OWASP statement in HLD/LLD is explicitly labelled
  `REFERENCE — Cross-cutting`, uses non-normative voice, and creates no test obligation. Every
  normative MCP control is physically separate and labelled `NORMATIVE — P11-FEAT-GATEWAY-MCP`.
- Treat the hosted-SaaS exclusion hypothesis as unconfirmed. Local-Gateway v3 explicitly reaffirmed
  the no-MCP rule; publication must repair the incomplete Guardrails v1.1 change-log chain and must
  not claim the exclusion was merely carried forward accidentally.
- Every stdio profile requires Docker containment: immutable image digest, no host mounts/devices/
  Docker socket, and safe `docker run --env NAME` credential projection. Daemon/image trust and any
  permitted container-network egress remain explicit residuals.
- Real platform/process-confinement claims require Windows and Linux/WSL2 evidence; the documents
  must not claim that the current repository already has this machinery.
- Every byte-producing publication command--Pandoc/WeasyPrint rendering, PDF assembly, Poppler
  extraction/rendering used for recorded evidence, and publication validation--runs inside the
  approved Ubuntu-24.04 WSL2 toolchain from the mounted worktree. PowerShell is allowed only for
  Git/status/read-only repository checks and the separate Windows verification run. Do not install
  or upgrade Pandoc, WeasyPrint, Poppler, fonts, or Python packages without separate operator
  approval.
- Use `apply_patch` for authored text changes. Mechanical copies of approved precedent files are
  allowed, but must be followed by an explicit stale-name/version scan.
- Before every task and before final handoff, run `git status --short --branch`; stop on unexpected
  changes or overlap with user-owned files.
- Maintain
  `docs/superpowers/reviews/mcp-gateway-architecture-publication-review-checkpoints.md`; it is
  gitignored and must never be staged.
- Do not stage, commit, push, open a PR, or merge without the operator's explicit authorization for
  that exact action.

---

## File Structure

### New publication source package

- `docs/sources/mcp-gateway-architecture-amendment/README.md` — source pins, splice policy,
  toolchain, build commands, and verification contract.
- `docs/sources/mcp-gateway-architecture-amendment/print.css` — fixed US Letter layout copied from
  the approved v3 publication baseline unless a reviewed page requires a narrowly documented style
  addition.
- `docs/sources/mcp-gateway-architecture-amendment/hld-v2.17-changed-pages.md` — changed HLD pages.
- `docs/sources/mcp-gateway-architecture-amendment/lld-v2.40-changed-pages.md` — changed LLD pages.
- `docs/sources/mcp-gateway-architecture-amendment/guardrails-v1.2-changed-pages.md` — changed
  Guardrails pages.
- `docs/sources/mcp-gateway-architecture-amendment/test-strategy-v1.6-changed-pages.md` — changed
  Test Strategy pages.
- `docs/sources/mcp-gateway-architecture-amendment/assets/hld-system-context.svg` — MCP-aware system
  context.
- `docs/sources/mcp-gateway-architecture-amendment/assets/hld-gateway-sequence.svg` — dual-gate MCP
  call sequence.
- `docs/sources/mcp-gateway-architecture-amendment/assets/lld-gateway-component-flow.svg` — typed
  discovery/call broker component flow.
- `docs/sources/mcp-gateway-architecture-amendment/build-manifest.json` — pinned inputs, target
  versions, replacement-page map, critical anchors, historical-version exceptions, and hashes.
- `docs/sources/mcp-gateway-architecture-amendment/tools/build_publication.py` — page-preserving
  assembly adapted from the approved v3 tool.
- `docs/sources/mcp-gateway-architecture-amendment/tools/validate_publication.py` — content,
  geometry, preservation, version, metadata, and SVG validation.
- `docs/sources/mcp-gateway-architecture-amendment/changed-pages-manifest.md` — section-to-page and
  redline-cluster mapping.
- `docs/sources/mcp-gateway-architecture-amendment/completeness-audit.md` — dropped-entry,
  exclusion-reversal, checklist, and current-state audit.
- `docs/sources/mcp-gateway-architecture-amendment/verification.md` — executed commands, visual
  survey, output hashes, and final evidence.

### New authoritative PDF outputs

- `docs/Optimus-Cost-Agent-Architecture-v2.17.pdf`
- `docs/Optimus-Cost-Agent-LLD-v2.40.pdf`
- `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf`
- `docs/Optimus-Cost-Agent-Test-Strategy-v1.6.pdf`

### Existing repository documents to amend

- `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md`
- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- `docs/superpowers/reports/2026-07-25-plan-11-authoritative-doc-section-map.md`
- `README.md` only where it makes a current-state MCP/Gateway/credential claim affected by this
  amendment.

### Review-only, never staged

- `docs/superpowers/reviews/mcp-gateway-architecture-publication-review-checkpoints.md`

---

### Task 1: Freeze the approved source and reviewer checkpoint

**Files:**

- Read: `docs/superpowers/specs/2026-08-05-mcp-gateway-brokering-architecture-amendment-design.md`
- Read: `docs/superpowers/reports/2026-08-05-mcp-gateway-architecture-document-redline-draft.md`
- Read: `docs/superpowers/reports/2026-08-05-mcp-gateway-security-best-practices-reference.md`
- Create or update, never stage:
  `docs/superpowers/reviews/mcp-gateway-architecture-publication-review-checkpoints.md`

**Interfaces:**

- Consumes: formal operator approval of the design and this plan.
- Produces: immutable source hashes and a checkpoint record used by every later task.

- [x] **Step 1: Confirm the formal approval gates**

Read the latest task message and the checkpoint log. Stop unless the operator has explicitly
approved the consolidated design and this publication plan. Approval to draft the plan is not
approval to execute it.

- [x] **Step 2: Verify the worktree and branch**

Run:

```powershell
git status --short --branch
git branch --show-current
git rev-parse --show-toplevel
```

Expected: branch `agent/codex/mcp-gateway-architecture-amendment`; only the reviewed draft/reference
files and checkpoint log are untracked or modified. Stop on any unrelated overlap.

- [x] **Step 3: Pin the four binary source PDFs and the tracked charter blob**

Run:

```powershell
Get-FileHash -Algorithm SHA256 docs/Optimus-Cost-Agent-Architecture-v2.16.pdf
Get-FileHash -Algorithm SHA256 docs/Optimus-Cost-Agent-LLD-v2.39.pdf
Get-FileHash -Algorithm SHA256 docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf
Get-FileHash -Algorithm SHA256 docs/Optimus-Cost-Agent-Test-Strategy-v1.5.pdf
wsl -d Ubuntu-24.04 -- bash -lc "cd /mnt/d/Projects/Development/Python/optimus-cost-agent-wt-codex && git show HEAD:docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md | sha256sum"
```

Expected PDF hashes from the authoritative section map:

```text
HLD v2.16:        6C2C98FE2327A6C466CAD3EB1800335EB59F0E1F65B2CB8E1E3401D7CFA05801
LLD v2.39:        82513729FD1A6E87FAD310DD90A18C996981B68024204E56CCA65377495585DE
Guardrails v1.1:  27EF0657CCEC5568D3E3769C7320223D1BFE3CF6F4702564CBD0A8A391F11029
Test Strategy v1.5: F3D744EC175B1E18E8B1E4E271997A0BB12666CC33CA7154A40BF5298588DA8D
```

Stop if a PDF differs. Record the charter digest as `git_blob_sha256`; keeping `git show` and
`sha256sum` inside WSL prevents PowerShell from transforming the blob's line endings.

- [x] **Step 4: Pin the approved wording inputs using LF-normalized content**

The four untracked Markdown drafts have no Git blob yet. Hash their UTF-8 content after normalizing
CRLF to LF, and record each digest as `lf_normalized_sha256`. Run:

```powershell
wsl -d Ubuntu-24.04 -- bash -lc "cd /mnt/d/Projects/Development/Python/optimus-cost-agent-wt-codex && tr -d '\r' < docs/superpowers/specs/2026-08-05-mcp-gateway-brokering-architecture-amendment-design.md | sha256sum"
wsl -d Ubuntu-24.04 -- bash -lc "cd /mnt/d/Projects/Development/Python/optimus-cost-agent-wt-codex && tr -d '\r' < docs/superpowers/reports/2026-08-05-mcp-gateway-architecture-document-redline-draft.md | sha256sum"
wsl -d Ubuntu-24.04 -- bash -lc "cd /mnt/d/Projects/Development/Python/optimus-cost-agent-wt-codex && tr -d '\r' < docs/superpowers/reports/2026-08-05-mcp-gateway-security-best-practices-reference.md | sha256sum"
wsl -d Ubuntu-24.04 -- bash -lc "cd /mnt/d/Projects/Development/Python/optimus-cost-agent-wt-codex && tr -d '\r' < docs/superpowers/plans/2026-08-05-mcp-gateway-architecture-amendment-publication-plan.md | sha256sum"
```

Record all four hashes and their digest kind in the checkpoint log and later in
`build-manifest.json`. Recompute the same LF-normalized digests immediately before final staging;
after the first commit, record the committed blob hashes as the durable publication pins.

- [x] **Step 5: Record the execution checkpoint**

Use `apply_patch` to write a `Current State` section and a newest-first UTC entry containing the
approval evidence, branch, source hashes, accepted rulings, and next task.

- [x] **Step 6: Verify Task 1**

Run:

```powershell
git status --short --branch
git check-ignore docs/superpowers/reviews/mcp-gateway-architecture-publication-review-checkpoints.md
```

Expected: the checkpoint path is ignored; no authoritative PDF or charter has changed.

---

### Task 2: Create the publication source skeleton

**Files:**

- Create the complete `docs/sources/mcp-gateway-architecture-amendment/` structure listed above.
- Copy from: `docs/sources/local-gateway-architecture-v3/`.

**Interfaces:**

- Consumes: Task 1 source pins and the v3 splice implementation.
- Produces: a version-correct source package with no changed-page prose yet treated as final.

- [x] **Step 1: Copy the approved reusable baseline mechanically**

Copy `print.css`, `tools/build_publication.py`, and `tools/validate_publication.py` from
`local-gateway-architecture-v3`. Copy the three SVGs as editing baselines. Create the README,
manifest, changed-page, audit, and verification files with `apply_patch`.

- [x] **Step 2: Replace package names and target versions**

Use `apply_patch` to set:

```text
Architecture v2.17
LLD v2.40
Guardrails v1.2
Test Strategy v1.6
```

Set the four pinned source filenames and hashes exactly as verified in Task 1. Do not guess
replacement pages yet.

- [x] **Step 3: Document the splice policy**

The README must state that unchanged pages are copied from the four pinned PDFs, image-backed LLD
code pages are not OCR-retyped, target metadata/headers are version-consistent, and any inline body
replacement outside a changed page must be manifest-declared and pixel-bounded.

- [x] **Step 4: Scan for stale precedent identifiers**

Run:

```powershell
rg -n "local-gateway-architecture-v3|v2\.16|v2\.39|v1\.1|v1\.5|P11-FU-3 remains open|No MCP endpoint|no MCP endpoint" docs/sources/mcp-gateway-architecture-amendment
```

Expected: old versions appear only as explicit pinned-source or provenance references; no old
package path or current no-MCP conclusion remains. The v3 exclusion may appear only in the clearly
labelled historical provenance record, never as current architecture.

- [x] **Step 5: Review checkpoint**

Update the checkpoint log with created files, stale-scan output, and approval request for the source
skeleton. Do not begin prose redlining until the reviewer accepts the package shape.

---

### Task 3: Author and review HLD v2.17 changed pages and diagrams

**Files:**

- Modify: `docs/sources/mcp-gateway-architecture-amendment/hld-v2.17-changed-pages.md`
- Modify: `docs/sources/mcp-gateway-architecture-amendment/assets/hld-system-context.svg`
- Modify: `docs/sources/mcp-gateway-architecture-amendment/assets/hld-gateway-sequence.svg`
- Update: `docs/sources/mcp-gateway-architecture-amendment/changed-pages-manifest.md`

**Interfaces:**

- Consumes: redline clusters HLD-MCP-1 through HLD-MCP-6 and revised ruling 9's two-voice rule.
- Produces: complete HLD wording for §§5A, 6, 10.A, 10.C, 11, 11.1, and 12 plus two diagrams.

- [x] **Step 1: Re-extract the pinned HLD pages**

Run under WSL2:

```bash
pdftotext -layout docs/Optimus-Cost-Agent-Architecture-v2.16.pdf tmp/pdfs/mcp-gateway/hld-v2.16.txt
```

Compare the extracted sections to the section map and v3 changed-page source. Do not author from
memory.

- [x] **Step 2: Write the changed HLD sheets**

Use `apply_patch` and preserve unchanged surrounding text. Insert the exact approved rules for:

- zero upstream credentials in the agent and N Gateway MCP profiles;
- dual-gate MCP data flow;
- both transport edges and no agent-to-MCP edge;
- split authority and direct-route residual including Gateway freshness enforcement;
- separate MCP accounting rows; and
- remote HTTP `2026-07-28` stateless methods, containerized-stdio discovery-first negotiation, and
  bounded discovery pagination;
- its deliberately breaking HTTP version floor, typed unsupported-version disposition, immutable
  source snapshot/Go-SDK support-citation split, transport-scoped no-downgrade divergence, and named
  Context7 remote-compatibility dependency;
- catalog-only registry use and provisioning/connection separation;
- OAuth refresh-versus-rotation position and elicitation/sampling future-open conditions;
- external MCP logging closed without altering Optimus audit logging;
- HLD cost/context admission for an operator-selected descriptor subset;
- generalized OWASP reference rows individually labelled `REFERENCE — Cross-cutting`, followed by
  separately labelled normative MCP controls; and
- expanded quality/evidence gates and honest exclusion provenance.

- [x] **Step 3: Update the system-context SVG**

Add Gateway-owned stdio and remote HTTP MCP edges, profile/credential custody, and both trust gates.
Keep all secrets inside the Gateway boundary. Preserve the local network-namespace warning. A
catalog may appear only as operator-side pre-provisioning reference; draw no registry-to-agent,
registry-to-model, or registry-to-Gateway-data-plane edge.

- [x] **Step 4: Update the sequence SVG**

Show agent pre-tool/context-admission gates, Gateway bearer/profile/freshness/binding/allowlist/
pagination/resource/budget checks, profile-scoped connection open/close and execution, untrusted-
result validation, MCP usage persistence, and result release. Connection lifetime must not look
like profile activation or MCP session resume.

- [x] **Step 5: Run the HLD content scan**

Run:

```powershell
rg -n "zero upstream credentials|profile-scoped|server/discover|tools/list|pagination|manifest hash|profile revision|Streamable HTTP|stdio|untrusted|MCPUsageRecord|descriptor|Context7|mcp\.protocol_version_unsupported|f817239|logging|REFERENCE — Cross-cutting|NORMATIVE — P11-FEAT-GATEWAY-MCP|unconfirmed|strict-loopback" docs/sources/mcp-gateway-architecture-amendment/hld-v2.17-changed-pages.md docs/sources/mcp-gateway-architecture-amendment/assets/hld-*.svg
rg -n "No MCP endpoint|no MCP endpoint|exactly one upstream credential|Gateway receives only its approved aggregator key" docs/sources/mcp-gateway-architecture-amendment/hld-v2.17-changed-pages.md docs/sources/mcp-gateway-architecture-amendment/assets/hld-*.svg
```

Expected: every required anchor is present; the exclusion scan returns no stale normative claim.

- [x] **Step 6: Review checkpoint**

Record the exact HLD sections/pages and request reviewer approval before starting LLD authoring.

---

### Task 4: Author and review LLD v2.40 changed pages and component flow

**Files:**

- Modify: `docs/sources/mcp-gateway-architecture-amendment/lld-v2.40-changed-pages.md`
- Modify: `docs/sources/mcp-gateway-architecture-amendment/assets/lld-gateway-component-flow.svg`
- Update: `docs/sources/mcp-gateway-architecture-amendment/changed-pages-manifest.md`

**Interfaces:**

- Consumes: LLD-MCP-1 through LLD-MCP-6 and the approved design §§1.1-10.1.
- Produces: the typed route/profile/state/accounting/trust contract used by later implementation
  planning.

- [x] **Step 1: Re-extract the pinned LLD target pages**

Run:

```bash
pdftotext -layout docs/Optimus-Cost-Agent-LLD-v2.39.pdf tmp/pdfs/mcp-gateway/lld-v2.39.txt
```

Inspect §§0.B-0.E, §0A, §§9/9E-10A, and §§12/12B/12D. Preserve image-backed code pages unless they
are explicitly replaced by the approved changed-page map.

- [x] **Step 2: Write the route and profile contract**

Add only:

```text
POST /v1/tools/mcp/discover
POST /v1/tools/mcp/call
```

Define registration versus refresh discovery, upstream versus namespaced tool names, profile
revision rules, restart activation, state transitions, `server/discover`, bounded complete
`tools/list` pagination, effective `min(local_max_age, ttlMs)` freshness, profile-partitioned cache,
Gateway-side stale-marker admission, argument-only upstream payloads, and the typed
`mcp.protocol_version_unsupported` disposition. Require `2026-07-28` with no fallback for remote
HTTP credential profiles; require Docker-contained stdio discovery-first negotiated/legacy tools-
only behavior. Separate hostile cursor integrity from transient retry and capacity exhaustion; v1
restarts complete scans and defers cursor checkpoints under `P11-FU-13`. Record Context7 as the
named real-server HTTP compatibility dependency: its configured endpoint must pass the authenticated
Gateway discovery/version/tools probe before any Context7 reachability claim.

- [x] **Step 3: Write trust, result, transport, and failure contracts**

Include complete-only results, inert resources, image/audio disposition, `x-mcp-header` validation
without `Mcp-Param-*`, call-scoped input-required denial, HTTP POST-SSE bounds, mandatory Docker
stdio isolation, profile/connection-axis separation, catalog-only registry use, OAuth binding
discriminator, descriptor-context admission, existing-`RetryPolicy` integration, typed errors,
persistence-only accounting recovery, durable indeterminate holds, and external MCP logging closed
without changing Optimus audit logging. Add generalized OWASP reference rows with explicit
`REFERENCE — Cross-cutting` labels and a separate normative MCP table.

- [x] **Step 4: Write the separate MCP accounting contract**

Keep legacy settled rows unchanged. Define `MCPUsageRecord`, the three attribution states,
operator-declared-free revision-bound `explicit_zero`, strict-budget denial for `unavailable`,
consumer sweep, and never-zero-for-unknown display/reconciliation semantics.

- [x] **Step 5: Update the component-flow SVG**

Show the existing agent `MCPTrustRegistry` separately from Gateway `MCPProfileRegistry`, discovery
paginator and call brokers, connection manager, two transport adapters, result validation, usage
writing, and agent-side descriptor-context admission. Do not show the Gateway re-evaluating
permission scope/effect class or a registry performing runtime connect/activation.

- [x] **Step 6: Run the LLD completeness scan**

Run:

```powershell
rg -n "POST /v1/tools/mcp/discover|POST /v1/tools/mcp/call|server/discover|nextCursor|ttlMs|PENDING_REGISTRATION|STALE|DISABLED|profile_id\.tool_name|mcp\.manifest_hash_changed|mcp\.budget\.unattributed_spend_denied|mcp\.protocol_version_unsupported|Context7|MCPUsageRecord|input_required|logging|Mcp-Param|system prompt|conversation history|RetryPolicy|REFERENCE — Cross-cutting|NORMATIVE — P11-FEAT-GATEWAY-MCP|durable" docs/sources/mcp-gateway-architecture-amendment/lld-v2.40-changed-pages.md docs/sources/mcp-gateway-architecture-amendment/assets/lld-gateway-component-flow.svg
rg -n "arbitrary MCP method|runtime activation endpoint|roots.*security boundary|filesystem.*enforced containment" docs/sources/mcp-gateway-architecture-amendment/lld-v2.40-changed-pages.md
```

Expected: required anchors are present and rejected claims are absent.

- [x] **Step 7: Review checkpoint**

Record LLD sections/pages and obtain reviewer approval before Guardrails/Test Strategy authoring.

---

### Task 5: Author and review Guardrails v1.2 changed pages

**Files:**

- Modify: `docs/sources/mcp-gateway-architecture-amendment/guardrails-v1.2-changed-pages.md`
- Update: `docs/sources/mcp-gateway-architecture-amendment/changed-pages-manifest.md`

**Interfaces:**

- Consumes: GR-MCP-1 through GR-MCP-4.
- Produces: normative split-authority, result-trust, stdio-residual, and acknowledgment policy.

- [x] **Step 1: Re-extract the Guardrails target sections**

Run:

```bash
pdftotext -layout docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf tmp/pdfs/mcp-gateway/guardrails-v1.1.txt
```

Inspect §§1-3, 5/5.2, 9, 11, and page-16 §13 document control before authoring.

- [x] **Step 2: Author the changed sheets**

Preserve Plan 6.5 no-autoload, descriptor scanning, manifest reapproval, allowed tools, scope, and
effect rules. Add Gateway allowlist/detected-drift freshness enforcement, stale-marked last-binding
use on recoverable refresh failure, exact namespace handling, durable indeterminate holds, argument-
only upstream payload, call-scoped method/result/content denials, accounting states, mandatory Docker
stdio containment, remote-HTTP `2026-07-28` versus stdio negotiation, pagination safety/capability
classification, catalog-only behavior, profile/connection separation, context admission,
OAuth/elicitation/sampling positions, and existing-`RetryPolicy` integration. Keep generalized OWASP
reference out of normative Guardrails; extend only the MCP controls Plan 6.5 actually anchors.

Repair the document-control section by preserving the v1.0 entry, adding the missing v1.1 local-
Gateway correction entry, and adding the v1.2 amendment entry. State that v3 explicitly reaffirmed
no-MCP as global rule 14 but recorded no causal rationale; the hosted-SaaS-premise theory remains
unconfirmed.

- [x] **Step 3: Run the Guardrails scan**

Run:

```powershell
rg -n "Gateway allowlist|server/discover|nextCursor|stale_marked|profile_id\.tool_name|durable|indeterminate|arguments|system prompt|input_required|resource_link|explicit_zero|unavailable|RetryPolicy|Windows Job Object|Docker|--env NAME|v1\.1|v1\.2|global rule 14|unconfirmed|split agency|Plan 6\.5|sampling|human decision|complete-only|inert|image/audio|enforced|platform-gated|code-execution" docs/sources/mcp-gateway-architecture-amendment/guardrails-v1.2-changed-pages.md
```

Expected: every control and residual appears explicitly.

- [x] **Step 4: Review checkpoint**

Record the Guardrails sections/pages and obtain reviewer approval.

---

### Task 6: Author and review Test Strategy v1.6 changed pages

**Files:**

- Modify: `docs/sources/mcp-gateway-architecture-amendment/test-strategy-v1.6-changed-pages.md`
- Update: `docs/sources/mcp-gateway-architecture-amendment/changed-pages-manifest.md`

**Interfaces:**

- Consumes: TS-MCP-1 through TS-MCP-4 and every design evidence row.
- Produces: executable evidence requirements without implementing runtime tests in this lane.

- [x] **Step 1: Re-extract the Test Strategy target sections**

Run:

```bash
pdftotext -layout docs/Optimus-Cost-Agent-Test-Strategy-v1.5.pdf tmp/pdfs/mcp-gateway/test-strategy-v1.5.txt
```

Inspect §§1-3, 6-10, and 11-14, especially §8A and §§14.4-14.5.

- [x] **Step 2: Author scope, tier, and interoperability wording**

Bring tools-only Gateway MCP into scope for both transports. Require real Gateway plus
independently authored stdio and HTTP MCP servers for live claims. Keep fakes in unit tier and keep
ACP `mcpServers`/session resume distinct. Context7 is additionally the named remote-compatibility
dependency: its configured endpoint must receive a live authenticated Gateway-originated discovery
probe proving `2026-07-28` plus tools support before any Context7 reachability claim. A fake or
another HTTP server is insufficient; unsupported or indeterminate evidence is fail-closed.

- [x] **Step 3: Author the security and accounting matrices**

Map every design evidence row, including direct bearer misuse, freshness on both sides, profile
changes, rotation successor test, restart activation, namespace collisions, deferred features,
`x-mcp-header`, platform confinement, argument-only payload, separate MCP accounting, durable holds,
persistence-only recovery, `2026-07-28` method/version behavior, complete pagination, registry non-
autoload, profile/connection separation, descriptor-context limits, existing-`RetryPolicy`
integration, elicitation triple denial, sampling producing no model call or spend, external MCP
logging unable to alter Optimus audit logging, and the Context7 exact-version probe. Reference-only
HLD/LLD OWASP statements must not acquire Test Strategy acceptance criteria.

- [x] **Step 4: Run the Test Strategy scan**

Run:

```powershell
rg -n "independently authored|Streamable HTTP|stdio|server/discover|nextCursor|ttlMs|mcp\.protocol_version_unsupported|Context7|logging|Gateway-side freshness|agent restart|test_launch_env_change_forces_reapproval_without_logging_secret_values|unattributed|consumer sweep|input_required|sampling|catalog|descriptor-context|RetryPolicy|x-mcp-header|Mcp-Param|P11-FU-9|P11-FEAT-ZED-RESUME|split agency|Plan 6\.5|human decision|complete-only|inert|image/audio|enforced|platform-gated|code-execution|MCPUsageRecord" docs/sources/mcp-gateway-architecture-amendment/test-strategy-v1.6-changed-pages.md
```

Expected: every anchor appears and §§14.4-14.5 are extended rather than replaced.

- [x] **Step 5: Review checkpoint**

Record the Test Strategy sections/pages and obtain reviewer approval.

---

### Task 7: Amend the charter and deferred-work custody documents

**Files:**

- Modify: `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`

**Interfaces:**

- Consumes: approved redline §§7-8 and publication approval.
- Produces: authoritative feature scope and named custody without assigning speculative Plan 11.x
  numbers.

- [x] **Step 1: Re-read the current charter and pool entries**

Run:

```powershell
rg -n -C 5 "P11-FEAT-GATEWAY-MCP|P11-FU-3|P11-FU-9|one-key|Explicit exclusions" docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md
```

- [x] **Step 2: Apply the charter amendment**

Use `apply_patch` to replace the one-upstream-key wording with zero upstream credentials in the
agent, define the approved v1 static-profile/dual-transport/tools-only scope, and state that the
route/contract design gate closes only with approved published PDFs. Add Context7 as the named
remote-compatibility dependency of `P11-FEAT-GATEWAY-MCP`, requiring a configured-endpoint,
authenticated Gateway discovery/version/tools probe before Context7 support may be claimed; do not
create a sixth follow-up for this in-scope feature acceptance dependency.

- [x] **Step 3: Add exactly five custody entries**

Add `P11-FU-12` MCP OAuth lifecycle, `P11-FU-13` deferred capabilities/long-lived interaction,
`P11-FU-14` MCP registry discover-and-connect, `P11-FU-15` tool-search/context minimization, and
`P11-FU-16` reverse research-to-documentation freshness. Preserve the distinct rationales and keep
`P11-FU-14` visibly separate from ACP `P11-FEAT-REGISTRY`. Generalized OWASP reference lands now;
it is not deferred under `P11-FU-16`.

Do not create a follow-up for signed per-call capabilities.

- [x] **Step 4: Preserve non-conflation**

Keep `P11-FU-9` client-supplied ACP `mcpServers` and `P11-FEAT-ZED-RESUME` session custody explicitly
separate from Gateway-brokered MCP. Keep MCP catalog/discover-and-connect custody under
`P11-FU-14` separate from ACP publication identity `P11-FEAT-REGISTRY`.

- [x] **Step 5: Run custody hygiene tests**

Run:

```powershell
python -m pytest tests/unit/docs/test_open_work_pool_hygiene.py -v
rg -n "unowned|UNOWNED" docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md
```

Expected: hygiene tests pass; no new MCP deferral is unowned.

- [x] **Step 6: Review checkpoint**

Record the exact charter/pool/roadmap diff and obtain reviewer approval.

---

### Task 8: Complete manifest mappings and render changed-page fragments

**Files:**

- Modify: `docs/sources/mcp-gateway-architecture-amendment/build-manifest.json`
- Modify: `docs/sources/mcp-gateway-architecture-amendment/changed-pages-manifest.md`
- Modify only if required by approved layout:
  `docs/sources/mcp-gateway-architecture-amendment/print.css`
- Write build artifacts only under: `tmp/pdfs/mcp-gateway/`

**Interfaces:**

- Consumes: approved changed-page sources from Tasks 3-6.
- Produces: one fragment PDF per document and an exact replacement-page map.

- [x] **Step 1: Verify the approved toolchain without installing anything**

Run:

```powershell
wsl -d Ubuntu-24.04 -- bash -lc "pandoc --version | head -1; weasyprint --version; pdftoppm -v 2>&1 | head -1"
```

Expected: Pandoc 3.1.3, WeasyPrint 61.1, Poppler 24.02.0. Stop on version drift and request review.

- [x] **Step 2: Render each Markdown fragment**

From the WSL-mounted repository path, run Pandoc and WeasyPrint for:

```text
hld-v2.17-changed-pages.md -> tmp/pdfs/mcp-gateway/build/hld.pdf
lld-v2.40-changed-pages.md -> tmp/pdfs/mcp-gateway/build/lld.pdf
guardrails-v1.2-changed-pages.md -> tmp/pdfs/mcp-gateway/build/guard.pdf
test-strategy-v1.6-changed-pages.md -> tmp/pdfs/mcp-gateway/build/test.pdf
```

Use `--standalone`, the package `print.css`, matching metadata titles, and the package directory as
WeasyPrint's base URL.

- [x] **Step 3: Count and inspect fragment pages**

Run:

```powershell
pdfinfo tmp/pdfs/mcp-gateway/build/hld.pdf
pdfinfo tmp/pdfs/mcp-gateway/build/lld.pdf
pdfinfo tmp/pdfs/mcp-gateway/build/guard.pdf
pdfinfo tmp/pdfs/mcp-gateway/build/test.pdf
```

Update `replacement_pages` only from actual fragment cardinality and the approved source-page map.
Record every mapping in `changed-pages-manifest.md`.

- [x] **Step 4: Render fragment contact sheets**

Use Poppler to render every fragment page at 150 dpi under `tmp/pdfs/mcp-gateway/rendered-fragments/`.
Inspect headings, tables, diagrams, line wrapping, clipping, and page transitions. Fix source/layout
with `apply_patch`, rerender, and repeat until clean.

- [x] **Step 5: Run stale-version and anchor scans**

Extract fragment text and verify target versions, required MCP anchors, and absence of stale
exclusion wording. Record commands and results in `verification.md`.

- [x] **Step 6: Review checkpoint**

Record fragment page counts and replacement mapping; obtain reviewer approval before assembly.

---

### Task 9: Assemble the four versioned PDFs

**Files:**

- Modify: `docs/sources/mcp-gateway-architecture-amendment/tools/build_publication.py`
- Create: the four new PDFs listed in File Structure.
- Update: `docs/sources/mcp-gateway-architecture-amendment/build-manifest.json`

**Interfaces:**

- Consumes: pinned sources, approved fragments, exact page map, and approved font files.
- Produces: four candidate authoritative PDFs with output hashes.

- [x] **Step 1: Adapt the assembler narrowly**

Use `apply_patch` to change input/output filenames, metadata titles, version assertions, fragment
names, and manifest path. Preserve the v3 cardinality, old-header, carried-page, metadata, and hash
checks. Remove only exceptions that are demonstrably inapplicable; add new historical-version
exceptions explicitly.

- [x] **Step 2: Copy the exact approved fonts to the temporary build directory**

Copy DejaVu Sans, DejaVu Sans Bold, DejaVu Sans Oblique, and Lato Italic from Ubuntu-24.04 into
`tmp/pdfs/mcp-gateway/fonts/`, matching the precedent.

- [x] **Step 3: Run the assembler**

Run:

```powershell
wsl -d Ubuntu-24.04 -- bash -lc "cd /mnt/d/Projects/Development/Python/optimus-cost-agent-wt-codex && python docs/sources/mcp-gateway-architecture-amendment/tools/build_publication.py --fragment-dir tmp/pdfs/mcp-gateway/build --font-dir tmp/pdfs/mcp-gateway/fonts"
```

Expected: exit 0; four new PDFs created; output hashes written to the manifest; source PDFs
unchanged.

- [x] **Step 4: Verify source immutability immediately**

Re-run the four source hashes from Task 1. Expected: exact match.

- [x] **Step 5: Review checkpoint**

Record candidate PDF paths, sizes, page counts, and hashes. Do not call them authoritative yet.

---

### Task 10: Run machine, visual, and completeness validation

**Files:**

- Modify: `docs/sources/mcp-gateway-architecture-amendment/tools/validate_publication.py`
- Modify: `docs/sources/mcp-gateway-architecture-amendment/completeness-audit.md`
- Modify: `docs/sources/mcp-gateway-architecture-amendment/verification.md`

**Interfaces:**

- Consumes: four candidate PDFs and the approved redline/checklist.
- Produces: evidence that every architecture claim landed and unchanged material was preserved.

- [ ] **Step 1: Adapt and run the publication validator**

Use `apply_patch` for target versions, filenames, anchors, page counts, diagram geometry, historical
exceptions, carried-page regions, protocol-generation exclusions, and OWASP voice/ownership checks.
The validator must prove every generalized HLD/LLD row has the literal
`REFERENCE — Cross-cutting` label and no normative keyword, while every normative MCP row has the
literal `NORMATIVE — P11-FEAT-GATEWAY-MCP` label and a Test Strategy citation. Then run:

```powershell
wsl -d Ubuntu-24.04 -- bash -lc "cd /mnt/d/Projects/Development/Python/optimus-cost-agent-wt-codex && python docs/sources/mcp-gateway-architecture-amendment/tools/validate_publication.py --font-dir tmp/pdfs/mcp-gateway/fonts"
```

Expected: exit 0 for all four PDFs.

- [ ] **Step 2: Run explicit exclusion-reversal scans**

Extract all four candidate PDFs with `pdftotext` and scan for:

```powershell
wsl -d Ubuntu-24.04 -- bash -lc "cd /mnt/d/Projects/Development/Python/optimus-cost-agent-wt-codex && rg -n -i 'No MCP endpoint is shown or implied|MCP is explicitly outside this correction|MCP Gateway contract.{0,120}out of scope|P11-FEAT-GATEWAY-MCP remains blocked pending P11-FU-3' tmp/pdfs/mcp-gateway/extracted"
```

Expected: no current normative instance remains. Historical discussion is allowed only when
clearly labelled and manifest-allowlisted.

- [ ] **Step 3: Run the full claim, voice, and provenance completeness audit**

For each row in design §12, record the exact HLD/LLD/Guardrails/Test citation and extracted phrase.
Also map every security-reference closing-checklist item and every redline cluster. A missing row
blocks publication.

Also map every ruling 8/revised-9/10-15 area. Record a separate voice audit proving generalized
OWASP statements are reference-only and produce no Test Strategy obligation, while each normative
MCP statement has `P11-FEAT-GATEWAY-MCP` ownership and evidence. Record the provenance evidence from
local-Gateway v3 redline rule 14 and the repaired Guardrails v1.0/v1.1/v1.2 change log; reject any
claim that hosted-SaaS causality was confirmed. Record the Go SDK v1.7.0 support citation and the
immutable `f817239` wire-content snapshot separately; prove the published text says the latter is
under `schema/draft/` and does not call it final per-version specification publication. Record the
transport-conditional compatibility outcome: no remote HTTP fallback but Docker-contained stdio
negotiation, and the deliberate narrowing of Go SDK downgrade behavior; Context7's named real-server
probe, and the external-logging non-conflation. A Context7 transport configuration snippet alone is
insufficient evidence.

- [ ] **Step 4: Validate carried-page preservation**

Compare every carried page below the header band against its pinned source at the precedent DPI.
Require pixel identity except for explicitly manifest-declared, bounded inline replacements.

- [ ] **Step 5: Validate diagrams**

Run SVG text-bound and connector-intersection checks. Require all text inside the canvas and
containing box and zero connector/label intersections. Confirm visually that no agent-to-MCP edge
or agent-held upstream credential is implied.

- [ ] **Step 6: Render and inspect every final page**

Render all final pages with Poppler at 100 and 150 dpi. Inspect covers, headers, footers, diagrams,
tables, code, section transitions, clipping, and historical-version exceptions. Record the survey
in `verification.md`.

- [ ] **Step 7: Record final metadata and hashes**

Record filename, metadata title, cover version, page count, page size, source hash, output hash,
changed pages, carried pages, and preservation result for each document.

- [x] **Step 8: Review checkpoint**

Provide the validator output, contact-sheet locations, completeness audit, and hashes to the
reviewer. Candidate PDFs remain unapproved until this checkpoint passes.

---

### Task 11: Perform documentation freshness and repository gates

**Files:**

- Modify: `docs/superpowers/reports/2026-07-25-plan-11-authoritative-doc-section-map.md`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Modify: `README.md` only if its current-state claims are stale.
- Update: `docs/sources/mcp-gateway-architecture-amendment/verification.md`

**Interfaces:**

- Consumes: reviewer-approved candidate PDFs and charter/custody edits.
- Produces: consistent current-state claims and clean repository quality gates.

- [x] **Step 1: Audit all current-state claims**

Run:

```powershell
rg -n -i "no mcp endpoint|mcp.*out of scope|mcp.*blocked|P11-FU-3|P11-FEAT-GATEWAY-MCP|one upstream credential|one aggregator credential|single-key" README.md docs/superpowers docs/sources
```

Classify every hit as updated normative state, historical evidence, or stale text requiring an
approved edit. Record the classification in `completeness-audit.md`.

- [x] **Step 2: Refresh the authoritative section map**

Update filenames, versions, page counts, hashes, diagram survey, and MCP section ownership. Replace
the old no-endpoint conclusion with the approved typed-contract summary.

- [x] **Step 3: Verify custody consistency**

Confirm the charter, pool, roadmap, section map, redline, and PDFs use identical feature and
follow-up names, and keep `P11-FU-9`/`P11-FEAT-ZED-RESUME` separate.

- [x] **Step 4: Run documentation tests**

Run:

```powershell
python -m pytest tests/unit/docs -v
```

Expected: all documentation hygiene tests pass.

- [x] **Step 5: Run Ruff**

Run:

```powershell
python -m ruff check .
```

Expected: exit 0 with no findings.

- [x] **Step 6: Run the full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: exit 0. Record pass/skip/deselection counts and warnings exactly. Do not describe an
environment-blocked or partial run as a pass.

- [ ] **Step 7: Run the full test suite in the separate WSL2 execution environment**

Run against the WSL-mounted view of this worktree:

```powershell
wsl -d Ubuntu-24.04 -- bash -lc "cd /mnt/d/Projects/Development/Python/optimus-cost-agent-wt-codex && uv sync --frozen --extra dev && uv run pytest -q"
```

Expected: exit 0. Record pass/skip/deselection counts and warnings separately from the Windows run.
This is the required pre-finalize POSIX evidence; an environment-blocked or partial run is not a
pass.

- [x] **Step 8: Run the publication validator again**

Run the exact Task 10 validator inside Ubuntu-24.04 WSL2 after all freshness edits:

```powershell
wsl -d Ubuntu-24.04 -- bash -lc "cd /mnt/d/Projects/Development/Python/optimus-cost-agent-wt-codex && python docs/sources/mcp-gateway-architecture-amendment/tools/validate_publication.py --font-dir tmp/pdfs/mcp-gateway/fonts"
```

Expected: exit 0 and unchanged output hashes.

- [x] **Step 9: Review checkpoint**

Record all gate outputs and the final freshness audit. Request approval for the final diff.

---

### Task 12: Final review, staging, and optional commit gate

**Files:**

- Review every file listed in this plan.
- Never stage:
  `docs/superpowers/reviews/mcp-gateway-architecture-publication-review-checkpoints.md`.

**Interfaces:**

- Consumes: approved outputs and clean gates from Tasks 1-11.
- Produces: an operator-approved publication changeset; staging/commit only if separately ordered.

- [x] **Step 1: Inspect the complete diff and untracked set**

Run:

```powershell
git status --short --branch
git diff --stat
git diff --check
git diff -- docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md README.md
```

Review new files directly because ordinary `git diff` omits untracked content.

- [x] **Step 2: Confirm lane purity**

Run:

```powershell
git status --short | Select-String -Pattern '^.. (src|tests)/'
```

Expected: no production or runtime-test file appears. Documentation tests may remain unchanged; this
lane specifies them but does not implement MCP behavior.

- [x] **Step 3: Confirm the checkpoint is excluded**

Run:

```powershell
git check-ignore docs/superpowers/reviews/mcp-gateway-architecture-publication-review-checkpoints.md
git diff --cached --name-only
```

Expected: checkpoint is ignored and absent from the index.

- [x] **Step 4: Obtain final operator approval**

Present the complete file list, four PDF hashes, validation/test outputs, residuals, custody entries,
and freshness audit. Stop until the operator approves the publication changeset.

- [x] **Step 5: Stage only if explicitly authorized**

If and only if the operator explicitly asks to stage, use an exact path list with `git add`; do not
use `git add .` or `git add -A`. Re-run `git diff --cached --name-only` and prove the checkpoint and
temporary build files are absent.

- [ ] **Step 6: Commit only if explicitly authorized**

If and only if the operator explicitly asks to commit, first rerun the Task 11 Ruff, full pytest,
and publication-validator commands. Then commit with the operator-approved message. Never use
`--no-verify`.

- [ ] **Step 7: Do not push or open a PR implicitly**

Report the branch and commit hash, if any. Pushing and PR creation require separate explicit
authorization and the branch must first be updated from `main` per repository policy.

---

## Plan Self-Review Mapping

| Approved design area | Publication task |
|---|---|
| Zero-upstream-credential invariant and split authority | Tasks 3-5 |
| Profile revisions, restart activation, and state transitions | Task 4 |
| Registration/refresh discovery and Gateway freshness | Task 4 |
| Transport-conditional protocol contract: remote HTTP `2026-07-28` floor and containerized stdio negotiation | Tasks 3-6, 10 |
| Breaking HTTP floor, Go SDK support citation/frozen draft-snapshot split, and Context7 real-server dependency | Tasks 3-7, 10-11 |
| Complete bounded pagination with safety/capability classification and stale-marked refresh | Tasks 3-6, 10 |
| Two name spaces and filtered descriptors | Tasks 4-6 |
| Tools-only method/result/content boundary | Tasks 4-6 |
| Elicitation future-open triple and v1 denial | Tasks 3-6, 10 |
| Sampling prompt/double-approval/linked-cost position and v1 no-spend proof | Tasks 3-7, 10 |
| Deprecated external MCP logging versus Optimus audit logging | Tasks 3-6, 10 |
| Static stdio and Streamable HTTP profiles | Tasks 3-6 |
| Provisioning/connection-axis separation | Tasks 3-6, 10 |
| Catalog-only MCP registry and ACP-registry non-conflation | Tasks 3-7, 10-11 |
| Mandatory Docker stdio containment and explicit daemon/image/network residuals | Tasks 4-6, 10 |
| Separate MCP accounting, budgets, and consumer sweep | Tasks 3-6, 10-11 |
| Descriptor-context cost admission and deferred semantic tool search | Tasks 3-7, 10 |
| Indeterminate durable hold and bounded retries | Tasks 4-6 |
| Existing `RetryPolicy` extension and typed UX | Tasks 4-6, 10 |
| Argument-only upstream payload | Tasks 3-6 |
| Threat-model residuals | Tasks 3-5 |
| OAuth refresh/rotation discriminator and deferred lifecycle | Tasks 3-7 |
| Generalized OWASP reference voice versus normative MCP ownership | Tasks 3-6, 10 |
| Exclusion provenance, Guardrails change-log repair, and reverse-gap custody | Tasks 3, 5, 7, 10-11 |
| Five deferred custody entries (`P11-FU-12` through `P11-FU-16`) | Task 7 |
| ACP `mcpServers` and session-resume non-conflation | Tasks 6-7, 11 |
| Four-PDF/charter redline and publication evidence | Tasks 3-12 |

No runtime implementation task appears in this plan. The next implementation lane, if later
authorized, must be a separate spec-driven plan that consumes the published HLD, LLD, Guardrails,
and Test Strategy as its contract.
