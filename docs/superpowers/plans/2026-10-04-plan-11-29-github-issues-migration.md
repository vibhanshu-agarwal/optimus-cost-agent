# Plan 11.29 — GitHub Issues Migration and Live Status View Implementation Plan

> For implementing agents: use the approved execution workflow task by task and TDD for tooling/page behavior. Claude is the implementer. Fable 5.1 independently reviews each of four execution checkpoints, then Codex performs one consolidated review. Codex is the architect/reviewer, not the production implementer. Every checkbox remains unchecked until its stated verification actually passes.

**Source:** shared review draft v2 (`2026-10-03-github-issues-migration-implementation-plan_v2.md`, sha256 `ead476ef6b38b068d813bc75835657475e783d38bdcf13fb123aded66b490a81`), which superseded draft v1 and incorporated Claude reply 9. Filed with bookkeeping edits only: the plan number and title, this source and approval record, the Spec sentence on approval, the location paragraph, and the Prerequisites cells that the approval and the operator's browser check settled.

**Approval:** operator, 2026-10-04: "I haven't read the plan, but I did see the pilot screens, and I approved them. As long as you and Codex agree, it is fine with me." Claude (reply 10) and Codex agreed on v2. The operator also gave one grant for Task 5's cutover merge and trial-wording removal: "I authorize the merge and trial copy wording removal." Claude re-confirms that grant at the cutover moment, because the cutover PR does not exist yet. Approval of this written plan does not authorize the remaining issue writes.

**Goal:** Provide one clean tabular view of every plan and issue, refreshed from GitHub on open/reload, while removing duplicated status narratives without losing obligations or evidence.

**Architecture:** GitHub issue state, labels and native relationships own current work status after a coordinated cutover. A standalone repository page reads that data directly; the existing backlog path becomes a minimal navigation/compatibility document. Repository plans, accepted decisions and sanitized evidence retain their contractual roles.

**Tech stack:** Existing Python 3.14/uv/pytest/Ruff; GitHub REST via the executor's existing gh connection; one standalone HTML/JavaScript page; Node's standard library for offline page tests. No new Python/JavaScript package, provider, server, Project or credential is required by the proposed baseline.

**Spec:** The Design contract below is the complete mechanism. The operator approved it with this task plan on 2026-10-04 (see Approval). That approval does not authorize GitHub writes, merges or cutover; each keeps its own grant.

**Location:** Filed as Plan 11.29, the next linear number after Plan 11.28 (reserved by the unmerged parallel-test-context branch). Its live state is its row in the consolidated backlog's live implementation plan registry, not this file. No decimal/nested/interstitial allocation. Any later approved substantive revision publishes a complete `_vN` successor.

## Requirement provenance and decisions

Direct operator statements in this Codex chat, 2026-10-03:

- "my requirement is simply to have a clean status and an always updated status, right? That I can view and get to know where each plan, each issue stands."
- "Whatever is the easiest for you, that makes sense, with the least amount of error and the least amount of drift that you can do, is I am open to that."
- "We should not delete any current evidence, but we absolutely need to remove the fat from those documents."
- "Let us also add a Complexity/Difficulty and a Planned Estimate."
- "The defaults for Planned Estimate = NA and Difficulty and Priority should be Medium"
- "We go with this - I need a tabular view. Will this be easy to update for you and Claude?" (selecting Claude's live table).

Operator accepted the compact table layout and selected a live page refreshed on open/reload; no manual status-table maintenance. Claude reply 8 agrees the approach does not authorize migration/cutover. Closed-state behavior, location, mapping/relationship rules and maintenance gates below are joint-review proposals unless explicitly identified as operator requirements. They must not become attributed operator choices by repetition.

Pilot baseline: main `980dad08cece20e109a5ee4eeecfcde04df2d71c`, rechecked locally and through GitHub during drafting. Trial issues: Plan 11.23 #222, FU20 #223 under #222, FU40 #224, A2A C1 #225. Publication independently verified against exact reviewed bodies and 12-file evidence seal `7a789680f0a0f996e7203a6004fa9db0d508a734e75f2bb15d42c4cd85dcc510`. The backlog remains authoritative until cutover. Exact counts from a status table are not an inventory or a target issue count.

## Design contract

### 1. Authority, content and grouping

- Current status is GitHub open/closed state plus one `status:` label on open issues; Priority, Difficulty, Planned Estimate and handler are issue labels. Product and kind identify membership. Body holds description, scope, acceptance criteria, next gate, custody and evidence links. Do not maintain an additional live status summary in the body or repository. Quoted source status is explicitly historical, tied to its baseline.
- Missing Priority/Difficulty receives explicit Medium defaults at authorized creation; Planned Estimate receives `estimate:na`. Existing explicit source values survive. Missing handler is explicitly `handler:unassigned`, never inferred from reviewer identity. At view time missing/conflicting labels remain visible errors, not silently supplied defaults. Severity, including C1 CRITICAL, remains distinct from scheduling priority and difficulty.
- Initial estimate is NA everywhere without an established estimate. A non-NA estimate requires explicit amount/unit and attribution; do not invent estimates during migration. The initial page can display escaped `estimate:` text, but this plan does not approve a unit convention or manufacture a due date.
- Native sub-issue parent represents one owning plan/feature. Related owners and dependencies are links in the body, not extra parents. Keep a separate plan issue and an item issue when their acceptance surfaces differ, including pilot #222/#223. Plan closure requires its own gates and relevant child obligations; child progress is not plan acceptance.
- Identical repeated references to one obligation map to the same issue. Distinct acceptance obligations remain separate even if they share a repair. Every source record maps to exactly one target or an explicit reviewed terminal/exclusion disposition; many records may map to one issue only with source-derived duplicate rationale. Conflicting source statuses are an early reviewed disposition, never automatically normalized.
- Existing legacy identifiers remain searchable aliases. New items use issue numbers; plan documents keep their plan number and complete successor versioning. No second handcrafted task hierarchy; plan steps stay in the approved file.
- Every actionable finding is resolved within its source task/PR or has an issue link and named custody before handoff/sign-off. Existing issue #33 requires current-scope reconciliation; open age or later plan coverage never proves closure. No blind duplicate issue or automatic closure.

### 2. Live table and durable location

Propose `docs/work-status.html` as the durable page, opened in a real browser from a checkout. Changes to the page follow ordinary reviewed PRs. `docs/README.md` and the existing consolidated-backlog path link it and the GitHub fallback. This avoids new hosting/publication surface; it is not a committed status snapshot. Native direct-file browser execution and cross-origin reads must pass Task 0/3 before this mechanism is accepted. If they cannot, stop for a recorded design disposition; do not silently publish Pages or install a service.

- Columns: linked Issue/Title, Status, Priority, Difficulty, Estimate, Owner. Preserve the accepted compact 1000px-wide layout; enough room for Partially implemented. Accessible horizontal overflow on narrow screens; no sprawling full-window title column.
- Open/Closed/All selector; Open by default. Opening, reloading or explicitly changing the selector triggers one new read cycle. No polling, automatic retry or stale persistent cache. Show successful read time, population/filter and errors. A page left open is a snapshot of its last read, not continuously current or an atomic GitHub transaction.
- Production reads all repository issues in the selected state, all pages, excluding PR objects. Separate Plans/Items from an Untriaged issues section; malformed managed issues remain visible with red metadata cells. A triaged issue has recognized product and kind labels; neither its author nor text grants authority. Outside submissions remain untriaged until an authorized agent explicitly classifies them, and no issue is silently hidden. Pilot mode explicitly filters shadow-pilot. Both modes identify their population.
- Open Status: exactly one valid `status:` label. Closed Status: zero status labels and `state_reason=completed` -> Done, `not_planned` -> Not planned. Null/unrecognized reason -> Closed (reason unavailable), never assumed Done. Any status label on a closed issue is red/conflicting. Native issue state wins over source-history prose.
- Product/kind/handler/priority/difficulty/estimate dimensions are validated before rendering. Render unknown values as invalid rather than crash. Support source status vocabulary discovered and approved in inventory, including promoted/accepted-open where actually used; do not substitute in-progress for approved source semantics.
- Build the hierarchy from `parent_issue_url` in the paginated issue-list response, independently verified for #223 -> #222 during this revision. No parent or child endpoint calls in the viewer. Validate the URL repository/path before extracting a parent number. Place matching children once under their parent; if the parent is outside the selected population show an under-#N link without fetching it. Multi-level relationships render once with bounded traversal and malformed/cyclic-relation errors. Missing parent fields mean no known parent; native summaries must never be used to invent one.
- Paginate the complete issue list and deduplicate issue numbers. A native child summary may show total/progress plus a note that some children are outside the selected view; do not claim the filtered list contains all children. Child progress is not acceptance.
- Escape issue/label text and validate repository URLs before using them. No eval, execution of issue text, token embedded in HTML, mutation requests, external libraries or private evidence uploads.
- On network, malformed-response, pagination or rate-limit failure, clear the current table and show a specific failure plus GitHub fallback. Ignore late results from superseded selector requests. Do not misrepresent an empty successful result as failure, or failure as an empty work list.
- Use only paginated issue-list reads: normally one request per up-to-100 returned objects, including PR objects discarded after fetching. Closed/All may therefore cost more than their issue-row counts suggest. Surface available quota/reset headers and record the actual full-population budget. No fixed opens/hour guarantee or token-in-browser workaround. Conditional-request savings are outside the baseline: authenticated 304 quota exemptions do not establish savings for this unauthenticated browser. Do not promise free reloads or add persistent stale data to obtain them.

### 3. Repository filing and history

- Preserve the consolidated backlog filename. After cutover it contains a short authority statement, live-page/fallback links, history permalink and seven compatibility anchors. No status tables, commit timelines, evidence dumps or long alias tables.
- Preserve these anchors: `p11-fu-11-plan-117-retry-preflight-and-live-session-proof`, `durable-effect-aware-mcp-indeterminate-call-custody`, `live-implementation-plan-registry`, `plan-1126-h4-verifier-follow-ups-from-seam-2-checkpoint-a`, `p11-fu-9-client-supplied-acp-mcpservers-disposition`, `p11-fu-5-windows-subprocess-handle-duplication-flake-winerror-650`, `p11-fu-4-re-pin-fu-4a-fu-5-live-evidence`. Inventory additional inbound anchors at the actual cutover base; seven is a baseline, not a ceiling. Each points to correct issue(s) or exact historical source.
- Historical backlog is preserved through a commit-bound permalink and Git object, not a rewritten archive copy. Explicitly record this history disposition when replacing the root content; do not silently introduce an archive-policy exception. All separately frozen files/approvals/evidence retain exact bytes. Mutable summaries lose duplicated status boards and link the new authority.
- Keep one sanitized machine-readable migration manifest, proposed `reports/github-work-tracking-migration.json`. It records baseline sources, mappings, issue identities and terminal/exclusion dispositions, not live status. One sanitized release report, proposed `reports/github-work-tracking-migration.md`, records the bounded migration/cutover evidence. Raw workstation artifacts remain archival provenance, never active dependencies.
- The migration manifest is a one-time baseline record, finalized and hashed in the approved cutover PR and sealed unchanged after final reconciliation; never updated for future plans/status. New and mutable plan files carry a single `**Tracking issue:** <repository issue URL>` header; offline checks validate it alongside filename/archive invariants. Existing frozen plans cannot acquire that line: resolve their baseline identity through the sealed migration manifest, verifying filename/blob identity. A substantive successor gains the header when independently authorized; do not create successors just to add metadata. Actual archive moves require recorded terminal disposition and preserve bytes. This hybrid avoids both a living central map and forbidden frozen edits.
- Approved specifications, requirements and plan steps remain intact. This is tracking restructuring, not permission to weaken an acceptance gate or edit another implementation lane. Policy/ADR filing explicitly replaces the old live-pool authority at cutover, without revising unrelated Plan 11.28 or Plan 12 behavior.

## Prerequisites

| Category | What must already be true | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| code/state | Reviewed baseline and four verified pilot issues exist | yes | reviewers | — |
| code/state | Whole-source obligation inventory, duplicate/custody dispositions and full draft bodies are approved | no | Claude; Fable 5.1 then Codex review | genuinely absent; buildable by Task 1 |
| code/state | Migration tool, page filters and offline checks exist | no | implementing agent | genuinely absent; buildable by Tasks 2–3 |
| tooling | Executor's gh REST writes/sub-issue binding work under the public repo account | yes | Claude | exercised in pilot; authority remains separate |
| tooling | Locked repo Python/dev tools available in the eventual dedicated lane | yes | Claude | — (2026-10-04: `uv sync --frozen --extra dev` in worktree `optimus-cost-agent-wt-claude-ghissues`; Python 3.14.4, pytest 9.1.1) |
| tooling | Node for separate page-test command and CI job | no | Claude | genuinely absent but buildable now: the executor has Windows Node v26.5.0; Task 3 adds the dedicated CI job with explicit Node setup |
| services | GitHub public REST reachable from the actual viewing browser | yes | operator | — (2026-10-04: the operator's browser loaded four live rows from GitHub) |
| human interaction | Direct-file opening in the intended Windows browser executes the exact saved page | yes | operator + implementer | — (2026-10-04: the operator opened the saved `pilot-live-status.html` from disk and it rendered four live rows, "fetched 4/10/2026, 12:01:10 am"; Task 0 records it) |
| credentials/authority | Approved design/plan and dedicated main-based implementation lane | yes | operator | — (approved 2026-10-04; lane `agent/claude/plan-11-29-github-issues-migration-filing` from `main` `980dad0`) |
| credentials/authority | Full issue writes, draft-body changes to pilot issues and cutover/merge grant | no | operator, in executor chat | merely unauthorized; separate concrete gates |
| cost | No paid Gateway/provider, Project or hosting call needed by proposed mechanism | yes | architect | no provider calls under this plan |
| external limits | Read quota and pagination support usable at full planned population | unknown | implementer + operator | genuinely hard external dependency: GitHub's unauthenticated limit (60 requests/hour per IP); Task 3 records the full-population request budget |

No required unknown is deferred past its dependent task. A hard prerequisite failure stops dependent work with named custody. No pass from skipped/UNRUN tests, injected stand-ins for actual viewing, or CI instead of the real browser.

## Explicit Exceptions

- Production feature fixes, real Zed/acpx/Gateway/Redis/PostgreSQL drives, provider calls and product/live acceptance are excluded; their existing issue/plan owners survive migration unchanged.
- Closed/historical records and accepted risks explicitly marked not open work are not newly opened as issues. Task 1 still inventories and gives each a reviewed terminal/history disposition. An accepted risk with outstanding mitigation work is not excluded merely because it is called a risk.
- GitHub Project, GitHub Pages, new credentials, auth refresh, new hosting/service installation and background polling are excluded from this baseline. Any needed alternative requires recorded disposition and a complete successor before implementation.
- No branch/worktree deletion, evidence cleanup, raw evidence upload or edits to frozen predecessor bytes. No automatic closure/reopening or deletion of #33, pilot records or other work during migration.

## Global Constraints and Review Focus

Use current repository AGENTS/CONTRIBUTING, Evidence and Local Artifact Policy and accepted decisions. Ask implementation-lane intake, branch only from latest main and inspect clean status/HEAD/worktrees before writes. Confirm task-specific mutation authority and preserve caller/operator changes. Ruff is mandatory before any delivery sign-off; relevant production coverage must not regress. No commit/push/PR/merge is authorized by this unapproved draft. Authorize those actions separately in the implementing agent's visible context. Never no-verify. Keep reviewer checkpoints ignored and out of task commits. Exactly four execution checkpoints: inventory; tooling/page; before publication; after cutover. Each uses independent Fable 5.1 review, fixes by Claude, then one consolidated Codex review. Claude works between checkpoints without additional external review rounds. The present written-design review/operator approval is the pre-execution gate, not a fifth execution checkpoint. This cadence adopts Claude reply 9's relayed 2 October rule; its private-memory provenance is not represented as an independently verified operator quote.

Five high-risk input classes and owning checks:
1. Source record outside a familiar table, repeated alias or conflicting status -> Task 1 complete coverage/explicit disposition checks.
2. Unknown create outcome, concurrent edit or duplicate marker -> Task 2 no-retry/intent/hash/reconciliation fixtures.
3. Closed record, null reason, child beyond page 1 or hidden parent -> Task 3 view fixtures and actual-browser probe.
4. Private/malformed issue data, quota failure or late selector result -> Task 3 escaping/URL/error/request-generation fixtures.
5. GitHub and main change between staging and merge -> Tasks 4–5 freeze/delta/authority-transition rehearsal and terminal stop gate.

## File and interface map (proposed, subject to Task 0 collision check)

| File | Responsibility |
|---|---|
| `tools/github_work_tracking.py` | Source inventory validation, deterministic draft plan, gh read/write adapter, bounded publication/update/reconciliation CLI |
| `tests/unit/tools/test_github_work_tracking.py` | Offline migration/capture-control tests; no GitHub writes |
| `docs/work-status.html` | Standalone live viewer with inline pure data functions and UI controller |
| `tools/testing/work_status_page.test.cjs` | Standalone Node standard-library fixtures over the exact page script; outside default pytest collection |
| `.github/workflows/work-status-page.yml` | Explicit page-test CI job with pinned Node setup; not a new prerequisite for ordinary pytest/pre-commit lanes |
| `reports/github-work-tracking-migration.json` | Baseline identity/coverage/plan-path manifest; no live status store |
| `reports/github-work-tracking-migration.md` | Sanitized migration release evidence and authority-transition record |
| Existing pool/masterplan/roadmap, AGENTS, CONTRIBUTING, README, docs indexes, relevant decisions index | Minimal policy/current-state authority updates; immutable predecessors untouched |
| Existing docs hygiene/verifier tests and `.github/workflows/masterplan-impact.yml`, PR template | Repoint obsolete content parsing; retain offline custody and file invariants |

Inventory interfaces in the proposed Python tool: `load_inventory(path: Path) -> Inventory`; `validate_inventory(inventory: Inventory, sources: Mapping[str, bytes]) -> CoverageReport`; `plan_migration(inventory: Inventory, existing: Sequence[IssueSnapshot]) -> MigrationBatch`; `publish_batch(batch: MigrationBatch, client: GitHubClient, journal: Journal) -> PublicationResult`; `reconcile(inventory: Inventory, observed: Sequence[IssueSnapshot]) -> ReconciliationReport`. Every dataclass/schema is defined in the same module, versioned as `optimus-work-tracking-migration-v1`; client injected for unit fixtures. No runtime import of the shared handoff publisher/private evidence.

Each inventory record has unique source ID, repo/source path and blob digest, anchor/row identity, legacy aliases, original metadata snapshot, acceptance/custody links, source clauses, disposition, target identity and duplicate rationale when applicable. All source sections receive migrated/history/excluded/not-work classification with reviewer rationale. Issue snapshots include number/id/title/body/labels/state/reason/native parent and last observed body/metadata fingerprint. Planned writes carry operation, target and prepared payload hash; apply uses last-read checks, journals safe intent before each write, preserves IDs and validates result before the next mutation. PublicationResult distinguishes pass, failed and unknown outcome; none triggers an automatic retry.

### Task 0: Lock design, current authority and obtainable evidence

**Files:** shared draft; later approved numbered plan/decision record/spec at their permitted paths; ignored reviewer checkpoint. No GitHub mutations.

- [ ] Record latest remote/local base, lane status, current instructions/decisions, known plan reservations and this draft's review disposition. Allocate official number only for authorized repository filing. Label agent proposals separately from operator quotes.
- [ ] Prove direct-file execution/read from the exact pilot-live-status.html in the intended browser; record visible four-row output, request/error behavior and zero write requests. Verify that its unauthenticated issue-list response exposes #223's parent link, rather than assuming the authenticated connector observation establishes browser behavior. Check Node version/runtime and chosen lane dev tooling. The operator owns browser/machine prerequisites; do not install silently.
- [ ] Inventory inbound pool anchors and all files/tests/tools that parse status authority; classify mutable/frozen with current hashes. Establish the source/PR intake manifest: whole pool, live registry, masterplan boards, roadmap/current README claims, linked evidence/A2A obligations and PR bodies/reviews/comments starting with #219–#221 and their governing linked deliveries. Follow explicit unresolved-finding/deferral links recursively and record the boundary; no crawl of all historical PRs. This bound is not a claim that unrelated older PRs contain no work. A known unresolved finding from outside the seed set must be included, and incomplete coverage cannot receive completeness sign-off.
- [ ] **Pre-execution design gate:** Claude reviews this written draft, Codex disposes findings, and the operator approves the complete contract/plan before implementation. Verify executor Node and the dedicated page CI setup; no Node dependency enters default pytest collection. Browser capability remains a named prerequisite, not inferred from injected-page proof. Unmet capability causes recorded disposition.

### Task 1: Produce the complete obligation and duplicate/custody inventory

**Files:** migration manifest draft, Python inventory validator and its tests. Source documents read-only. No issue publication.

- [ ] Write RED `test_inventory_covers_all_source_sections`, `test_missing_obligation_fails`, `test_duplicate_status_conflict_requires_disposition`, `test_plan_item_distinct_acceptance_preserved`, `test_many_source_aliases_require_duplicate_rationale`, `test_accepted_risk_with_unfinished_mitigation_not_excluded`. Fixtures include out-of-table A2A C1, FU20/Plan11.23, promoted two-item plans, MAIN-5/candidates/H4/masterplan tracks and #33 scope.
- [ ] Run `uv run --frozen --extra dev pytest tests/unit/tools/test_github_work_tracking.py -k inventory -q`; expect the new assertions to fail because validation is absent, not because fixtures/import paths are broken.
- [ ] Implement the inventory schema/validator; source-derive every section and linked unresolved finding. Count records and unique obligations separately. Preserve legacy identities, original contradictory claims and explicit reviewed dispositions. No fixed 32/51 completion target or heuristic defect count.
- [ ] Same selector must pass. Review semantic completeness by reading source/diffs, not only parser outputs. All required source clauses have target/link custody, no orphan/no unexplained exclusion. Unknown scope remains blocked before publication.
- [ ] **Checkpoint 1 — inventory:** Fable 5.1 independently reviews the exact inventory/cardinality, source boundary, history and #33 disposition; Claude fixes findings; Codex gives one consolidated review. Task 3 may proceed alongside inventory after the design gate with one agreed schema and separate file ownership. It requires no intermediate external review. Task 2 may develop against that schema, but no publication batch is finalized before approved inventory.

### Task 2: Build bounded, restart-safe migration publication and reconciliation

**Files:** Python migration tool/tests; approved inventory/draft bodies. No live writes in implementation tests.

- [ ] Write RED `test_all_pages_and_pr_exclusion`, `test_unknown_create_outcome_stops_without_retry`, `test_marker_hit_reuses_reviewed_pilot_identity`, `test_conflicting_labels_prevent_first_write`, `test_concurrent_body_or_label_edit_blocks_update`, `test_required_parent_binding_verified_both_ways`, `test_write_result_mismatch_blocks_next_write`, `test_metadata_defaults_preserve_explicit_values`, `test_migration_reconciliation_exact_coverage`. Use the accepted pilot control cases without depending on its workstation files.
- [ ] Run `uv run --frozen --extra dev pytest tests/unit/tools/test_github_work_tracking.py -q`; confirm genuine RED, implement the interfaces and versioned journals, then obtain GREEN.
- [ ] Plan all conflicts before the first write; list every issue and label page via REST, excluding PRs. Source markers and reviewed semantic match govern reuse, not lagging search. Reuse #222–225; do not create another copy. #33 update/reuse is a specific reviewed operation, never an incidental relabel.
- [ ] Updates re-read current body and full labels against last approved fingerprint, preserving unrelated labels/text. Since REST has no assumed transactional body-hash compare, use one designated executor and flag concurrent writes; do not promise race-free compare-and-swap.
- [ ] Source-checked dry-run emits every exact issue body/label/relationship operation and write budget. Log write intents/IDs/semantic result before next mutation. Unknown outcomes halt, seal success/failure evidence, reconcile read-only and require fresh authority before another write.

### Task 3: Make the durable live page work across all states and populations

**Files:** docs/work-status.html, tools/testing/work_status_page.test.cjs, dedicated page CI workflow, docs index. No public issue edits for testing. This task can run alongside Task 1 after design approval; Claude coordinates any parallel workers, with no added review rounds.

- [ ] Write RED `test_closed_reason_mapping`, `test_closed_with_status_label_is_invalid`, `test_missing_and_conflicting_dimensions`, `test_unknown_enum_and_unclassified_issue_visible`, `test_issue_list_pagination`, `test_child_visible_without_selected_parent`, `test_multilevel_relations_render_once`, `test_late_fetch_cannot_replace_newer_filter`, `test_failed_fetch_clears_rows`, `test_text_escaping_and_url_validation`, `test_only_get_requests_and_no_tokens`.
- [ ] Run `node --test tools/testing/work_status_page.test.cjs` with the Task 0 established Node runtime. Missing Node fails this explicitly invoked page check, not default pytest/pre-commit. Fixtures execute the exact page script with Node built-in VM/assert, no network/packages. Dedicated CI uses explicit Node v26.5.0 setup and the same command; it must pass before page delivery sign-off. Any required-check registration is a separately authorized repository-settings operation.
- [ ] Implement pure functions `statusCell(issue)`, `metadataCell(issue, prefix)`, `buildRows(issues, relationships, stateFilter)` and `loadView(client, stateFilter, population)`. UI renders the validated result and ignores stale read generations. Implement all Design contract view cases, not only the four pilot rows.
- [ ] Same selector GREEN; then real-browser check exact saved file with public trial data. Exercise Open/Closed/All and error case with offline fixtures, not public fake closures. Record full-migration request budget and quota limitations. Direct file open must work on the intended Windows browser; Python/Node path-shaped behavior must be checked on real WSL/Linux when affected.
- [ ] **Checkpoint 2 — tooling and page:** Fable 5.1 independently reviews Task 2/3 source, offline control/fixture outcomes and actual-browser evidence; Claude fixes findings; Codex performs one consolidated review. Operator can review the view without approving issue migration. No Project/Pages/token fallback is implicit.

### Task 4: Prepare staged issues, minimal docs and replacement offline governance gates

**Files:** source manifest/release report; minimal pool/masterplan/roadmap/index changes; current policy/decision records; relevant existing docs/verifier tests, workflow and PR template. Frozen contract bytes untouched.

- [ ] Write RED `test_live_plan_files_have_issue_identity`, `test_source_mapping_has_no_unclassified_record`, `test_source_to_issue_coverage_and_unique_aliases`, `test_pool_anchors_survive`, `test_frozen_blobs_unchanged`, `test_status_stub_has_no_duplicate_board`, `test_issue_impact_declaration_offline`. Repoint existing status-parsing tests individually with a retained/changed/retired rationale, not wholesale deletion or exemptions.
- [ ] Replace the old masterplan-impact mechanism with an offline `Work tracking impact:` PR declaration: repository-qualified issue links, or `none:` with concrete rationale. No mandatory legacy-track alias on new PRs. Keep its required-check job identity and modify verifier/tests/workflow coherently. Validate declaration structure, plan-local tracking links and sealed baseline identities; do not query GitHub in CI or pretend syntax proves semantic finding capture.
- [ ] Resolve docs-root plan identities from plan-local tracking links or sealed frozen-plan baseline mappings, not the deleted Active/Blocked table. Preserve archive/filename/link/digest invariants and reviewed terminal disposition before moves. Map all fifteen hardening tracks; do not delete track custody with its old board. Preserve superseded historical evidence without editing pinned bytes.
- [ ] Run `uv run --frozen --extra dev pytest tests/unit/docs tests/unit/tools/test_doc_paths.py tests/unit/tools/test_verify_masterplan_impact.py tests/unit/tools/test_github_work_tracking.py -q`; expect GREEN after reviewed changes. Separately run `node --test tools/testing/work_status_page.test.cjs` and its explicit CI job; Node is outside the default Python hook. Run `uv run --frozen --extra dev ruff check .` and `git diff --check`. No network in CI tests. Do not claim Ruff/coverage/test skips pass.
- [ ] **Checkpoint 3 — before publication:** Independent Fable 5.1 review, Claude fixes, then one consolidated Codex review of exact full-source inventory/body/label operations, evidence/redaction and current-state freshness across all claiming docs. Obtain separate executor-chat authority for full GitHub writes, including removal of trial wording/labels from #222–225 at cutover. Publication not implied by code approval.
- [ ] With that grant, publish remaining records as staged/trial copies using the bounded tool; seal outcomes and independently reconcile every mapping/native relationship/live body. Repository pool remains authoritative; no status authority cutover or closure yet. Approve the proposed cutover PR separately after main drift is intentionally resolved.

### Task 5: Perform one coordinated authority cutover and verify maintenance

**Files:** prepared approved cutover changes; final manifest/release evidence; issue staging markers; ignored reviewer checkpoint. No changes to product contracts.

- [ ] Obtain an explicit short pool-edit freeze and cutover/merge authority in the executor's own chat. Re-read main, source fingerprints and staged issue bodies/labels; reconcile every delta with Task 2's read-only tool. A freeze is a human coordination step, not an assumed lock. Drift or failed reconcile stops before merge; no automatic repair/retry.
- [ ] Merge the exact approved minimal-doc/policy/page/manifest changes only with operator authority. This merge commit/time is the authority-switch point. Trial wording still present on staged issues does not override the merged policy. If merge fails, the pool remains authoritative and trial copies stay marked. No separate merge-failure rehearsal suite: Task 2's existing failure-control tests and these explicit stop conditions cover the tool boundary.
- [ ] After verified merge, remove trial labels/procedural wording through separately approved fingerprint-checked bounded operations. Keep source-history/evidence intact. Every write is journaled/validated; stop and seal on mismatch/unknown outcome without retry. Partial cleanup is a visible transition inconsistency with named Claude custody; GitHub remains authoritative and migration is not declared complete. Fresh executor-chat authority is required for recovery writes, even if the same tool is used.
- [ ] Independently re-read merged main and issue pages; reconcile full mapping/native custody, browser output, current-state docs and frozen/evidence digests. Seal the merged one-time manifest unchanged. Record marker cleanup and authority-switch commit in a sanitized final release record; post-merge repository filing requires its own authorized reviewed PR, never a direct main write or edit to a frozen release report. Rehearse new-finding/closure behavior with existing offline fixtures, not public fake closures.
- [ ] **Checkpoint 4 — after cutover:** Fable 5.1 independently reviews final exact-head CI/tests/Ruff, real-browser/live reads, coverage/counts, evidence digests and remaining limitations; Claude fixes findings under the applicable authority; Codex performs one consolidated review. Completion requires all checks and cleanup, not merely merge. Product/Plan12/Plan11.28 acceptance stays unchanged.

## Maintenance contract after cutover

Agents update GitHub under their assigned task authority; no issue text grants permission. Signed comments identify authorship. On every new finding: search/list existing issues and preserve source/custody/acceptance before creating a duplicate. Any agent may perform an authorized closure after all acceptance criteria and evidence pass, with signed reason/proof; otherwise use Refs, never a closing keyword. Remove open-status label when closing; reopens restore one justified status label. All criteria/gates unmet means the issue stays open. Operator merge approval remains separate.

Page changes are reviewed source PRs; issue status changes require no page/table PR. New/mutable plans carry their tracking link in the file header; frozen predecessors use the sealed baseline mapping until an independently approved successor exists. Future work does not edit the migration manifest. Offline CI enforces identity/custody compatibility; live all-issue reads flag new/unclassified metadata. Source migration omissions are addressed by inventory reconciliation, not by red-cell checks. A signed handoff names issue links, unresolved gates and last observations without copying a new status board.

## Definition of Done / claim-to-evidence

| Claim | Required evidence |
|---|---|
| No work lost or duplicated | Approved full-source/PR intake manifest, semantic duplicate dispositions, offline mapping checks and sealed live reconciliation |
| Every plan/item has correct custody | Exact issue identities/native links plus preserved acceptance contracts, including #222/#223 and #33 reviewed disposition |
| Clean current tabular view | Actual saved-file browser read, all-state fixtures, real GitHub metadata, request/quota evidence; refresh semantics shown |
| Closed/unknown states truthful | Done/Not planned/unknown reason/conflicting-label fixtures; no fake live closure |
| Evidence and frozen history retained | Unchanged frozen Git-blob digests, sealed historical/publication manifests and exact history permalink/anchor checks |
| One current status authority | Authorized exact-head merge and transition record, no active duplicate status boards or private dependencies |
| Capture failures do not disappear | Unknown-write/concurrent-edit/error fixtures, signed source-to-issue finding capture and no-retry outcome journals |
| Delivery is accepted | Four Fable 5.1 -> Codex execution checkpoints, operator grants, Python tests, separate Node page check, Ruff, applicable coverage and exact-head CI; no unrun tier presented as passing |

## Review status and sources

All task checkboxes are intentionally unchecked; drafting is not task execution. Self-review mapped each Design contract requirement to Tasks 0–5 and each Review Focus class to named verification. Remaining approval decisions are the complete written design/plan, repository filing/implementation lane and bounded publication/cutover grants; required capability unknowns have early tasks. No production implementation performed while drafting.

Technical references checked during drafting: [GitHub issue states/reasons and pagination](https://docs.github.com/en/rest/issues/issues), [native sub-issue endpoints](https://docs.github.com/en/rest/issues/sub-issues), [public API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api), [CORS](https://docs.github.com/en/rest/using-the-rest-api/using-cors-and-jsonp-to-make-cross-origin-requests). Unauthenticated reads currently have 60 requests/hour per IP; handle actual response headers/secondary limits rather than treating this as guaranteed viewing capacity.

## Disposition of Claude reply 9

1. Accepted: viewer hierarchy uses list `parent_issue_url`, no per-plan requests. Missing/filtered parents remain context links. Verified #223's parent directly, rather than relying only on the review narration.
2. Accepted: Claude implements; four execution checkpoints use Fable 5.1 then one consolidated Codex review. The design gate is pre-execution. The reported prior rule is attributed to Claude's relay, not quoted as independently established operator provenance.
3. Accepted with frozen-file constraint: plan-local tracking headers for new/mutable plans; sealed baseline manifest for existing frozen files. No recurring central-map maintenance and no unauthorized frozen edit.
4. Accepted: merge switches authority before trial markers are removed. Dedicated transition rehearsal suite removed. Existing publication safety tests, read-only reconciles, freeze, stop/no-retry and fresh recovery authority remain.
5. Selected separate page tests/CI: Node does not become a default pytest/pre-commit requirement. Claude's Windows Node v26.5.0 observation is attributed; actual executor/CI version checks remain prerequisites.

Smaller points: bounded PR seeds #219–#221 plus linked/known unresolved findings; separate Untriaged section without treating author identity as trust; issue-list pagination accounts for PR objects; page and inventory can progress concurrently after design approval; future impact declarations use issue links without legacy aliases. Conditional-request optimization is deferred because unauthenticated quota savings have not been established.
