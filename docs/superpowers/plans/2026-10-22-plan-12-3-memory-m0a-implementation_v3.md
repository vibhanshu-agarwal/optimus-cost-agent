# Proposed Plan 12.3 v3: safe memory foundations (M0a-1)

> **For agentic workers:** after exact-revision approval, execute Tasks 0–2 in order, then the single final checkpoint. Do not execute this draft now.

**Goal:** close the integrated #385 gate, one includable-files policy and architecture ADR, and the registered project identity. The original combined M0a scope is preserved in `2026-10-22-plan-12-3-memory-m0a-implementation.md`, SHA-256 `365304b45dfc3ba26df3aaf66be417f148754ab6b8d1fd74fccb3c9936c35a84`.

**Architecture/stack:** CPython 3.14+, uv/pytest/Ruff, existing host permission/workspace APIs, a pure-Python Git-wildmatch parser and per-user locked JSON registry. No native Redis, Postgres, embedding or client capability result is needed to implement or close this plan.

**Authority/base:** frozen v12 SHA-256 `33670c6b84aceccd629437c14f03609ba4293d70cde95b242dd93a2b0ad4fb14`; updated freeze record `13880f7779a72a51a90444d0f659faaf8f9a251cc430e06cbdc37daa68c4073f`; post-freeze brief `f81a080b3b9065295dd47b817fbd411c00d2cba9b3614b1d69c41dc06796acd9`. Source inspected at main `dbdfaa3210b329c9fae6de2fb80811174e361786`. [Whole-feature spec v3](../specs/2026-10-22-plan12-memory-design_v3.md) defines the accepted boundaries and proposed mechanisms.

**Publication/authority:** unregistered review draft in an artifact folder, not a live root plan or execution release. Recheck the proposed linear number, ADR number, source drift and overlap before authorized filing. Each plan needs its own issue and issue-only work-register pointer, plus the current docs index entry, under ADR-022. Preserve predecessor documents and frozen handoff inputs. No issue/label, branch, infrastructure, commit, push, PR or merge is authorized by authoring this plan.

**Roles:** Codex authors; Claude reviews and owns the operator chat; the operator approves the exact spec/plan revision there. Claude implements only after that release. At each named checkpoint Fable reviews first, then Codex. No per-task review ceremony or execution delegation is implied. Record reviewer evidence under the repository's owner/reviewer workflow; private memory is never authority.

**Assessment:** proposed `priority:high`, `handler:claude`, `difficulty:high`, `estimate:5d`. Claude/Codex consensus is five active working days, excluding #385 integration/approval waits, subject to exact-revision operator approval. Cross-platform resolved-path/ignore parity and concurrent, crash-safe registry proof justify the increase from 3d; the split still replaces the prior 13-day bundle estimate. No labels are written.

**Review revision (2026-10-23):** complete successor to preserved `2026-10-22-plan-12-3-memory-m0a-implementation_v2.md`, SHA-256 `d379e744bc3bb3ecfe5c1c48e8f1b9153ccef422288c38a3e27f6bb8592d9114`. Claude review: `1872834f0d8c344abd6dedbf18dd74f1797dc0ac5dcffd1086c9bca946dc7bac`; endorsed cover note: `ebde0286753248ca7bdf3b230b4abc87579115a16debeebdaa5b887627941633`. All review dispositions are in spec §10. Reviewed drafts and frozen inputs stay unchanged.

**Run order:** **12.4 → 12.3 → 12.5**, as endorsed. #385 remains open/unassigned and gates 12.3; assigning its hardening owner is a separate GitHub write. Scheduling does not create implementation dependencies between these independently closable plans.

## Prerequisites

| Requirement | Satisfied today? | Owner | Disposition / first task |
|---|---|---|---|
| Accepted #385 fix integrated on chosen base: automatic/named reads and root/nested `.env.*` | no | #385 hardening handler is unassigned; Claude coordinates a proposed owner, operator authorizes assignment | Genuinely absent at inspected main; source work is blocked at Task 0, so run 12.4 first. Assignment and #385 implementation require separate authority; no duplicate hardening work transfers to this lane. |
| Approved revision, contributor checkout, clean source/overlap inventory | no | Operator releases; Claude establishes | Merely unauthorized; current folder is an artifact workspace. Task 0 prepares the exact setup. |
| Own plan issue, available number, ADR/index/register filing | no | Claude; operator authorizes external writes | Merely unauthorized. Task 0 files only after approval; no live status in this draft. |
| CPython 3.14+, uv/Git/Bash and frozen dev environment | unknown | Operator owns machine state; Claude inventories | Task 0 distinguishes absent tooling from unauthorized setup before dependent tests. |
| Real Windows and WSL/Linux filesystem/locking test lanes | unknown | Operator; Claude verifies | Task 0 inventories. Both are required for this plan's platform acceptance; an unavailable lane stays open rather than silently waived. |
| One isolated coverage writer and safe temporary filesystem roots | unknown | Operator owns schedule; Claude verifies | Establish in Task 0. No right to stop another lane. |
| Plans 12.4/12.5, paid calls or storage/client probes | yes — not prerequisites | None | Their status cannot block this plan. Qualify the policy parser locally in Task 1 as an ordinary dependency choice. |

## Constraints and evidence discipline

- No paid calls. All later provider traffic must use Gateway accounting and separately approved budgets. This plan does not implement Auto or change a model picker.
- B1: feature artifacts retain pointers/hashes, sanitized metadata and synthetic data; source/buffer bodies remain RAM-only. Existing Q27 diagnostics are separate scope.
- Neutral `context_engine` imports no host/Gateway/security/evidence/model-policy implementation. Existing Optimus/compaction must work when the feature is absent.
- All checkboxes start empty; every implementation/test/probe result is **UNRUN** at authoring. Fixture validity, administrative closure and production acceptance are different claims.
- Preserve failed attempts, skips, UNKNOWN and platform qualifications. No retry-to-green, forced runs, cleared pytest addopts, borrowed hook exceptions or mock substituted for a named real dependency.
- Use an isolated contributor checkout and test context, its own `.venv` and `uv sync --frozen --extra dev`, after authorized setup. Never mutate another lane or adopt a production/default test service. Only one coverage writer per checkout.

## Planned files and interfaces

| Unit | Paths / contract |
|---|---|
| File policy | `src/optimus/guardrails/file_policy.py`; modify `src/optimus/agent/workspace_context.py`, `src/optimus/guardrails/permissions.py`. `FilePolicy.decide(relative_path: str, *, purpose: str) -> FileDecision`; fields allowed/reason/policy revision/resolved identity. Purposes automatic/index/anchor share security denials. Public `is_secret_path(path: str) -> bool` delegates to #385's accepted predicate; permissions must not import the broader policy module. |
| Registry | `src/optimus/context/project_registry.py`; `ProjectRegistry.resolve(identity: WorkspaceIdentity, *, create: bool) -> ProjectRegistration`. UUID, registry version, canonical common-Git-dir/path key, worktree applicability; locked/fsynced atomic JSON and exportable snapshot. |
| Tests | `tests/unit/guardrails/test_file_policy.py`; `tests/unit/context/test_project_registry.py`; existing workspace-context, permissions, trusted-paths and operator-paths tests. |
| Decision/provenance | Proposed `docs/decisions/ADR-024-project-memory-and-evidence.md`, recheck number before filing; decision/docs indexes. Record whole-feature architecture and operator/proposed distinctions, with separately authorized future slices. |
| Evidence | `reports/plan12-memory-foundations/{manifest,requirements,qualification}.json` plus sanitized Markdown report. Proposed paths, not files already generated; no raw source/secrets. |

## Review focus

Follow resolved identities before reading, prove deny precedence with allowed controls, preserve trust approval identity when memory groups worktrees, and test concurrent/crashed registry writes with real subprocess/filesystem behavior. Neither a clean issue label nor an approved architecture replaces these checks.

## Task 0 — Establish #385, authority and attainable evidence

**Files:** evidence manifest and requirement provenance above; issue/registry/index changes only under separately approved filing scope. #385 product files belong to its hardening owner.

**Consumes:** frozen v12 and freeze record; current main; #385 acceptance criteria. **Produces:** pinned base, dependency receipt, approved paths/authorities and prerequisite inventory used by all tasks. **Checks:** K1 prerequisite and source/custody requirements for this foundations plan.

- [ ] Read current #385 issue and reviewer evidence, including handler status. Coordinate a proposed hardening owner and obtain separate approval for any GitHub assignment; do not assign or implement #385 under this plan. Verify the integrated fix on the chosen source, not merely an issue label. Run the actual production policy/workspace tests on synthetic root/nested `.env`, `.env.local`, `.env.production`, named and filler cases, plus allowed-file controls. Until #385 is accepted on that base, do not proceed to dependent product work or real-workspace ingestion.
- [ ] Verify current main/branch/worktree/cleanliness and live registry before creating the separately authorized contributor checkout. Record source drift from the authoring pin, interpreter/uv/Git/Bash versions, isolated test roots and alternate-OS readiness. Never reuse someone else's checkout.
- [ ] Obtain exact execution and filing authority; establish the plan issue/number and approved label assessment. Add only its issue-only registry pointer. File sanitized, repository-visible v12 decision provenance so later tasks need no private handoff path. Keep implementation, service, GUI/network and publication releases distinct.
- [ ] Inventory every unknown prerequisite above and attach a next action before dependent tasks. Record only foundations resources here, including the selected policy-parser dependency and native Windows/WSL test availability. Package-matrix, storage and client probes are owned independently by Plan 12.5.

**Verify:** `uv run --no-sync pytest --no-cov tests/unit/agent/test_workspace_context.py tests/unit/guardrails/test_permissions.py -q`; record the integrated #385 source and positive/negative sentinel outcomes. Read-only Git/status/issue evidence establishes the remaining gates. Expected: production-path criteria hold and every dependency is yes/no with an owner; no unresolved prerequisite is silently passed.

## Task 1 — Shared includable-files policy and architecture decision

**Files:** policy paths above; `tests/unit/guardrails/test_file_policy.py`; existing workspace/permission tests; architecture ADR/provenance. **Consumes:** Task 0 accepted #385 seam. **Produces:** one versioned policy callable reused by automatic context and future engine adapters. **Checks:** K1 privacy/source-boundary subset; K2 corpus eligibility.

- [ ] **Red:** test deny precedence for all #385 names/variants, root/nested paths, case aliases, symlinks/junctions and runtime-tree targets. Test `.gitignore`/`.optimusignore` negation, binary/oversized files, an excluded explicitly named file and a normal-file control. Assert denied content is never opened and reasons contain no secret values.
- [ ] **Green:** first qualify an exact pure-Python `pathspec` pin/license in the isolated Task 0 environment, then centralize Git-wildmatch-compatible parsing without weakening #385. Plan 12.5 later records this already selected pin in its wider matrix; Task 1 does not depend on that probe or any other plan. Deny rules cannot be negated. Preserve the existing 16 KiB automatic-context pack budget; the separate 1 MiB indexing-file default is configurable. Check resolved identity at read time and report exclusions as coverage.
- [ ] Bind policy version/ignore-file digests to decisions. Compare ignore semantics with native Git on a synthetic fixture; do not let parser differences silently broaden access. Record architecture options and the frozen/operator-versus-proposed distinction in the ADR.

**Verify:** `uv run --no-sync pytest --no-cov tests/unit/guardrails/test_file_policy.py tests/unit/agent/test_workspace_context.py tests/unit/guardrails/test_permissions.py -q`; repeat platform-sensitive cases on real WSL/Linux with its own environment. Expected: all positive controls succeed, sentinels never enter packed data, and exclusions are explicit. Unsupported junction creation is disclosed and cannot prove the junction case.

## Task 2 — Registered project identity without cross-worktree authority transfer

**Files:** registry path; `tests/unit/context/test_project_registry.py`; use existing `WorkspaceIdentity`/operator-path APIs. **Consumes:** Task 0 roots and Task 1 policy. **Produces:** `ProjectRegistration` and exportable registry snapshot. **Checks:** K5 project-boundary/re-key subset.

- [ ] **Red:** create a real temporary Git repository and linked worktree; require one UUID. A separate clone and fork receive distinct UUIDs even with the same root commit/remote. Cover non-Git canonical paths, concurrent subprocess creation, interrupted replacement, corrupted registry and relocation without consent. No real user registry/keyring is touched.
- [ ] **Green:** implement per-user versioned JSON registry with OS lock, fsynced temporary file and atomic replacement; reuse the existing platform lock pattern without altering launch approvals. Retry contention boundedly or return unavailable. Failed/corrupt writes never allocate a replacement silently. Store worktree applicability separately and expose a snapshot for M3 recovery.
- [ ] Show that shared project IDs do not change workspace approval digests, file permissions or branch-specific anchors. A link/migration needs an authenticated host action; no model directive is added in M0a.

**Verify:** `uv run --no-sync pytest --no-cov tests/unit/context/test_project_registry.py tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_operator_paths.py -q`; run new filesystem/lock cases on real Windows and WSL/Linux. Expected: stable grouping, no mixed fork state, no partial registry and preserved security identity.


## Checkpoint 1 — Independently accept foundations and close

- [ ] Verify K1 shared-policy subset and K5 registry/isolation subset on the actual implementation, including native Windows and WSL/Linux portability cases. Synthetic fixture inputs exercise production paths; they are not mock policy substitutes.
- [ ] Run final canonical checks below, source-bind the evidence and obtain Fable's review followed by Codex's. Resolve all in-scope blockers; preserve any nonblocking finding with an owning issue/roadmap entry.
- [ ] Record accepted #385 integration, ADR/provenance, shared API contracts, selected parser pin/license, platform qualifications and exact source hashes. Close this plan's issue only under the normal authorized workflow. Hand registry/policy APIs to M0b/M1/M3 and the parser pin to 12.5 as information.
- [ ] Confirm neither evaluation nor any feasibility probe was used as a closure prerequisite. All later K1/K5 obligations remain with their owning slices, not marked complete here.

**Closure:** Tasks 0–2, required own tests/platform checks, final reviews and evidence must be accepted. #385 absence may hold this plan; 12.4 remains independently executable. No probe, service or benchmark is a condition of foundations closure.

## Verification and final review evidence

Record checkout, branch, source HEAD/tree or explicit dirty-diff hash, interpreter/environment/config, run IDs, platform, exact command, exit status and retained output. Focused tests prove only their named scope. At the final checkpoint run the canonical default selection and validity check once on the implementation revision, then Ruff:

```bash
uv run --no-sync python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json
uv run --no-sync python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json
uv run --no-sync ruff check .
```

Follow current canonical product floors (Optimus/context engine/model policy), repository minimums and aggregate reporting; do not infer a gate from rounded output. Inspect run-context/guard validity. A fix after the full run requires relevant focused proof and disclosure of the exact delta; the earlier run cannot be attributed to newer bytes. Filing/index changes also require the repository docs-index, plan-directory and open-work-pool hygiene tests. Preserve any failure and resolve it under the current workflow, with no inherited bypass.

Final handoff includes sanitized source/config-bound manifest, per-check status, reviewer responses, requirement-to-check map, exceptions with owners and full hashes of the reviewed spec/plan. Claude reviews the returned artifacts; the operator's exact-revision approval and later publication/execution releases remain separate.

## Explicit exceptions and custody

| Outside this plan | Named owner and consequence |
|---|---|
| #385 production hardening | GitHub #385 hardening lane; Task 0 only verifies accepted integration. |
| Cases, offline grader and generic-harness decision | [Plan 12.4](2026-10-22-plan-12-4-memory-evaluation-implementation_v2.md); independent, no blocker either way. |
| Packages/embeddings, Redis/Postgres, ACP/Zed probes | [Plan 12.5](2026-10-22-plan-12-5-memory-feasibility-implementation_v2.md); independent dispositions. |
| Former Task 7 experiments | Start of frozen v12 M5a (Initializr), M7 (bounded G1′/G0 graph) and M5b (L2), per spec §8.1; no acceptance content removed. |
| Durable capture, outbox, per-user Gateway diagnostics and #303 contract | Frozen v12 M0b; broad telemetry consolidation stays #303. |
| Indexing/retrieval/worker and real-corpus qualification | Frozen v12 M1/M2. |
| Automatic memory, notice binding, checkpoint, encryption/keys, purge/rotation, backup/restore and imports | Frozen v12 M3, including K5-R1/R2 and native keystore tests; learning/archive remains M6. |
| Dependency tool, compatibility, impact and project graph products | Frozen v12 M5a/M5b/M7; C3/C4 remain there. |
| Savings tables, model runs and held-out acceptance | #248 / Q29; OC-4 remains open. No paid calls here. |
| Session load, picker, diagnostics beyond this scope | Plan 11.7/#240, model-selection work, Q27 respectively. |
| Commit/push/PR/merge, service/keyring/GUI operations and cleanup | Separate operator authority; this plan does not grant it. |
