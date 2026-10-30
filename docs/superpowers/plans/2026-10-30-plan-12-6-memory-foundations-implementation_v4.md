# Proposed Plan 12.6 v4: Memory foundations implementation (M0a-1, #390)

> **For agentic workers:** Task 0 was released separately by the operator and its first source step is delivered. Tasks 1–2 require the operator’s exact-revision approval of this successor. Claude implements; Codex reviews read-only through the CLI at the single final checkpoint.

**File:** `docs/superpowers/plans/2026-10-30-plan-12-6-memory-foundations-implementation_v4.md`

**Goal:** close the integrated #385 gate, deliver one includable-files policy and architecture ADR, and establish registered project identity. The original combined M0a scope is preserved in `2026-10-22-plan-12-3-memory-m0a-implementation.md`, SHA-256 `365304b45dfc3ba26df3aaf66be417f148754ab6b8d1fd74fccb3c9936c35a84`.

**Architecture/stack:** CPython 3.14+, uv/pytest/Ruff, existing host permission/workspace APIs, a pure-Python Git-wildmatch parser and per-user locked JSON registry. No native Redis, Postgres, embedding or client capability result is needed to implement or close this plan.

**Authority/base:** source inspected at main `1c9cac7d26887f7182b95160413b30886b1c9efe`; implementation checkout is `agent/claude/plan12-6-memory-foundations`, HEAD `9448aa5b795f50f79a3e0af80dad4b9dcf0e73b0`, comprising that main base plus Task 0’s #385 fix. [Whole-feature spec v4](../specs/2026-10-22-plan12-memory-design_v4.md), SHA-256 `708e0e7831f6d4c56b5f6442cd37c4e02eecffd2659db04f3e6a6b1c54506ff9`, supplies the design. Frozen v12 remains SHA-256 `33670c6b84aceccd629437c14f03609ba4293d70cde95b242dd93a2b0ad4fb14`; its freeze record is `13880f7779a72a51a90444d0f659faaf8f9a251cc430e06cbdc37daa68c4073f`, and the post-freeze brief is `f81a080b3b9065295dd47b817fbd411c00d2cba9b3614b1d69c41dc06796acd9`. Private originals are archival provenance, never execution dependencies.

## Revision v4

Complete successor to the operator-approved v3 input, `2026-10-22-plan-12-3-memory-m0a-implementation_v3.md`, SHA-256 `0f7e066cfa74a428ebc7f7dc5680a8d5c815f120256ffaf025580be91e5ac35d`. Preserve those bytes.

This revision assigns foundations **Plan 12.6**, corrects sibling references and sequencing, absorbs #385 into Task 0, records delivered commit `9448aa5` with Codex round 80 review pending, selects **ADR-031** subject to a filing-time availability check, updates the source base, and applies the binding lean workflow. The proposed remaining estimate becomes **3 working days**.

The operator’s 2026-10-30 direction is:

> “Please fix any issues blocking this plan. Absorb it into this plan please. Plan 12.x tasks are priority, so if anything blocks it we fix that”.

That direction releases Task 0 and supersedes the older separate-hardening dependency in v3 and spec v4’s dated sequencing text. It does not approve Tasks 1–2 or grant GitHub, publication or merge authority.

**Run order:** **Plan 12.5 / M0a-2 evaluation (#389, closed 2026-10-30 through PR #444, merge `1c9cac7`) → Plan 12.6 / M0a-1 foundations (#390) → M0a-3 feasibility (#391, unnumbered)**. Plan 12.3 is loop control; Plan 12.4 is Auto mode. Scheduling does not create implementation dependencies between independently closable slices.

## Authority, roles and filing

Codex authors; Claude Opus reviews the plan, implements and owns the operator chat. The operator approves this exact revision there before Tasks 1–2 execute. Codex reviews through its read-only CLI at the single final checkpoint:

```bash
codex exec -m gpt-6.1-sol -c 'model_reasoning_effort="high"' -s read-only
```

Pass model and effort explicitly on every invocation, including resumed sessions. Fable is used only for genuinely complex points, at Claude’s judgment. No mandatory Fable-first or per-task review cycle applies. Task 0’s already-pending round 80 review remains attributable separately.

Claude maintains `docs/superpowers/reviews/plan-12-6-review-checkpoints.md`, including Current State and dated rulings; it stays gitignored and unstaged. Under authorized GitHub writes, Claude posts CLI reviews verbatim to #390 with the required reviewer/model/effort/session heading. Reviews are evidence; approvals come from the operator in Claude’s chat.

Filing happens in **this plan’s PR**: the plan, docs index, ADR-022 issue-only registry pointer, ADR and decision index. Under explicit GitHub approval, update #390’s title to **“Plan 12.6 — Memory foundations (M0a-1)”** and its agreed labels. No second work register or duplicate issue is created.

**Assessment:** `priority:high`, `handler:claude`, proposed `difficulty:high`, proposed `estimate:3d` remaining. Three working days cover policy/parser qualification, registry/concurrency work, and documentation/final verification. Task 0’s first source step is delivered; separate WSL qualification and routine Fable review are removed. Approval waits and CI queue time are excluded. This is Codex’s estimate for agreement with Claude, not an already agreed label change.

## Prerequisites

| Requirement | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| #385 shared production seam available | yes | Claude | Delivered in `9448aa5`; review and acceptance evidence remain Task 0 obligations. It is not yet merged to main. |
| Exact-revision release for Tasks 1–2 | no | Operator | Merely unauthorized; this successor needs approval. Task 0 has separate authority above. |
| Dedicated contributor checkout and overlap inventory | yes | Claude | Supplied checkout/branch exists. Recheck status, source drift and overlap before execution; do not replace or mutate another lane. |
| #390 filing, ADR number, indexes and agreed label assessment | no | Claude; operator authorizes GitHub writes | Merely unauthorized. File through this plan’s PR; recheck ADR-031 availability first. |
| CPython 3.14+, uv/Git/Bash and frozen dev environment | unknown | Operator owns machine state; Claude inventories | Task 0 establishes versions and environment before dependent tests, distinguishing absent tooling from unauthorized setup. |
| Windows filesystem/locking capabilities and Linux PR CI | unknown | Operator owns machine state; Claude verifies; CI executes Linux checks | Task 0 establishes availability. Required evidence cannot be silently waived. No separate WSL run unless a non-trivial CI failure warrants one. |
| One isolated coverage writer and safe temporary roots | unknown | Operator owns schedule; Claude verifies | Establish in Task 0; no authority to stop another lane. |
| Native services, credentials, GUI/TTY interaction or paid calls | yes | None | None is required for this plan. Tests use synthetic temporary repositories and registries. |
| Evaluation or feasibility results | yes | None | Neither Plan 12.5 nor #391 is a closure prerequisite. Task 1 qualifies its own parser dependency. |

## Constraints and evidence discipline

- No paid calls. Later provider traffic requires Gateway accounting and separately approved budgets. This plan does not implement Auto or change a model picker.
- B1: feature artifacts retain pointers/hashes, sanitized metadata and synthetic data; source/buffer bodies remain RAM-only. Existing Q27 diagnostics remain separate.
- Neutral `context_engine` imports no host/Gateway/security/evidence/model-policy implementation. Existing Optimus and compaction must work when the feature is absent.
- Task 0 source delivery is recorded below; its pending review is not an acceptance claim. New checkboxes start empty. No tests ran during this read-only authoring round; retain earlier evidence under its own source and run identities.
- Preserve failed attempts, skips, UNKNOWN and platform qualifications. No retry-to-green, forced runs, cleared pytest addopts, borrowed hook exceptions or fake substituted for a tier’s named real dependency.
- Use the contributor checkout’s own `.venv` and frozen environment, established with `uv sync --frozen --extra dev` under execution authority. Only one coverage writer per checkout.
- Use targeted tests per change. Commits may skip **only** `optimus-pytest-coverage`; every other applicable hook runs. No commit, push, PR, GitHub write or merge authority is inferred from plan approval.
- Run exactly one Windows full suite with coverage on the final code head, followed by PR CI on Linux as the second full run. WSL is reserved for investigating non-trivial CI failures.
- All implementation, including #385, must satisfy the existing mutation and mode boundaries.

## Planned files and interfaces

| Unit | Paths / contract |
|---|---|
| Delivered #385 seam | `src/optimus/guardrails/secret_paths.py`: `is_secret_path(path: str) -> bool`, `target_secret(target: Path, root: Path) -> bool`; shared by `permissions.py`, `path_safety.py` and `workspace_context.py`. | <!-- pragma: allowlist secret - module and test paths, not a credential -->
| File policy | Create `src/optimus/guardrails/file_policy.py`; modify `src/optimus/agent/workspace_context.py` and relevant guard integration. `FilePolicy.decide(relative_path: str, *, purpose: str) -> FileDecision`, carrying allowed/reason/policy revision/resolved identity. Purposes automatic/index/anchor share security denials. Build on `secret_paths.is_secret_path`; permissions must not import the broader policy module. |
| Parser dependency | `pyproject.toml`, `uv.lock`; exact pure-Python `pathspec` pin and license qualified in Task 1. |
| Registry | Create `src/optimus/context/project_registry.py`; `ProjectRegistry.resolve(identity: WorkspaceIdentity, *, create: bool) -> ProjectRegistration`. UUID, registry version, canonical common-Git-dir/path key, worktree applicability; locked/fsynced atomic JSON and exportable snapshot. |
| Tests and delivered caller update | `tests/unit/guardrails/test_secret_paths.py`, `tests/unit/guardrails/test_file_policy.py`, `tests/unit/context/test_project_registry.py`; existing workspace-context, permissions, trusted-paths and operator-paths tests. Preserve `9448aa5`’s establishing-import closure update in `tools/probe_p11_zed_session_load.py` and its unit test. | <!-- pragma: allowlist secret - module and test paths, not a credential -->
| Decision/provenance | Proposed `docs/decisions/ADR-031-project-memory-and-evidence.md`; recheck number before filing. Record whole-feature architecture, operator/proposed distinctions and separately authorized future slices; update decision/docs indexes. |
| Plan filing | This successor, `docs/README.md`, and the transitional backlog’s issue-only live-plan registry pointer to #390. Issue status, priority, owner and next gate stay in GitHub. |
| Evidence | `reports/plan12-memory-foundations/{manifest,requirements,qualification}.json` plus sanitized Markdown report. These are proposed outputs, not artifacts already generated; no raw source/secrets. |

## Review focus

Resolved-path aliases must not bypass denial; ignore negation must not revive denied files; size/binary exclusions must remain visible without exposing contents; shared project identity must not transfer workspace trust; concurrent or interrupted registry writes must not silently replace identity. The owning tasks below provide executable checks.

## Task 0 — Implement #385 and establish attainable evidence

**Files:** delivered #385 production/test/caller paths above; evidence manifest and requirement provenance; filing changes under their separate authority.

**Consumes:** main `1c9cac7`, frozen requirements and #385 acceptance criteria. **Produces:** accepted shared secret-path seam, pinned source, prerequisite inventory and approved execution boundaries. **Checks:** K1 prerequisite and source/custody requirements.

**Delivered first source step:** Claude implemented commit `9448aa5b795f50f79a3e0af80dad4b9dcf0e73b0`. It introduces `secret_paths.py`, replaces duplicated permission/path-safety predicates, excludes secret names and resolved secret targets from automatic context, and updates the establishing-import closure. Its regressions cover named/filler context, root/nested files, `.env.*`, aliases, omission markers and allowed controls. **Codex round 80 review is pending.** Delivery does not establish final acceptance or close #385.

- [ ] Complete #385’s four acceptance criteria: one secret rule for automatic context, explicitly named files and filler; `.env.*` variants denied for automatic and model-issued reads; root/nested sentinel regressions with allowed controls; and retained proof that the regressions expose the defect on main’s production code. Bind red evidence to main `1c9cac7` and green evidence to the actual fix source. Inspect existing evidence before generating any missing focused proof.
- [ ] Resolve round 80 findings and complete #385 acceptance before dependent product work. Fix in-scope blockers within this lane under the operator’s absorption direction; do not transfer #385 back to a separate hardening owner.
- [ ] Recheck current main/branch/worktree/status and overlap; record drift from the authoring pin, interpreter/uv/Git/Bash versions, environment, temporary roots, Windows capabilities and Linux CI availability. Establish every unknown prerequisite before its dependent task.
- [ ] Obtain exact-revision release for Tasks 1–2 and the necessary filing/GitHub authority. Preserve sanitized, repository-visible requirement provenance, including the dated absorption direction and its shared source reference. Recheck ADR-031, agree the issue assessment, and prepare filing through this plan’s PR.

**Verify:**

```bash
uv run --no-sync pytest --no-cov tests/unit/agent/test_workspace_context.py tests/unit/guardrails/test_secret_paths.py tests/unit/guardrails/test_permissions.py tests/unit/tools/test_probe_p11_zed_session_load.py::test_establishing_import_closure_equals_explicit_module_path_subset -q
```

Expected: production-path secret criteria hold, allowed controls succeed, caller closure remains accurate, main-red/fix-green evidence is attributable, and every prerequisite has an observed disposition and owner. No live Zed probe is required.

## Task 1 — Shared includable-files policy and architecture decision

**Files:** file-policy/dependency paths above; `tests/unit/guardrails/test_file_policy.py`; existing workspace/permission tests; architecture ADR/provenance.

**Consumes:** Task 0’s accepted `secret_paths` seam. **Produces:** one versioned policy callable reused by automatic context and future engine adapters. **Checks:** K1 privacy/source-boundary subset; K2 corpus eligibility.

- [ ] **Red:** test deny precedence for all #385 names/variants, root/nested paths, case aliases, symlinks/junctions and runtime-tree targets. Test `.gitignore`/`.optimusignore` negation, binary/oversized files, an excluded explicitly named file and a normal-file control. Assert denied content is never opened and reasons contain no secret values.
- [ ] **Green:** qualify an exact pure-Python `pathspec` pin/license in the isolated environment, then centralize Git-wildmatch-compatible parsing without weakening #385. Deny rules cannot be negated. Preserve the existing **16 KiB automatic-context pack budget**; the separate **1 MiB indexing-file default** remains configurable. Resolve aliases within the trusted workspace before opening, check resolved identity at read time and recheck source identity after reading. Report exclusions as coverage.
- [ ] Bind policy version/ignore-file digests to decisions. Compare ignore semantics with native Git on a synthetic fixture; parser differences must not silently broaden access. Record architecture options, rejected alternatives, trade-offs, decision status and operator-versus-proposed distinctions in ADR-031. Hand the selected parser pin to M0a-3/#391’s wider matrix; that probe is not a dependency.

**Verify:**

```bash
uv run --no-sync pytest --no-cov tests/unit/guardrails/test_file_policy.py tests/unit/guardrails/test_secret_paths.py tests/unit/agent/test_workspace_context.py tests/unit/guardrails/test_permissions.py -q
```

Expected: positive controls succeed, sentinels never enter packed data, exclusions are explicit, and the two limits retain their separate meanings. Windows-focused checks and Linux PR CI establish their respective platform behavior. Unsupported junction creation is disclosed and cannot prove the junction case.

## Task 2 — Registered project identity without cross-worktree authority transfer

**Files:** registry path; `tests/unit/context/test_project_registry.py`; existing `WorkspaceIdentity`/operator-path APIs.

**Consumes:** Task 0 roots and Task 1 policy. **Produces:** `ProjectRegistration` and exportable registry snapshot. **Checks:** K5 project-boundary/re-key subset.

- [ ] **Red:** create a real temporary Git repository and linked worktree; require one UUID. A separate clone and fork receive distinct UUIDs even with the same root commit/remote. Cover non-Git canonical paths, concurrent subprocess creation, interrupted replacement, corrupted registry and relocation without consent. No real user registry/keyring is touched.
- [ ] **Green:** implement the per-user versioned JSON registry with OS lock, fsynced temporary file and atomic replacement; reuse the existing `msvcrt`/`fcntl` lock pattern without altering launch approvals. Retry contention boundedly or return unavailable. Missing/corrupt identity state with existing data and failed writes must require recovery rather than silently allocate a replacement. Store worktree applicability separately and expose a snapshot for M3 recovery.
- [ ] Show that shared project IDs do not change workspace approval digests, file permissions or branch-specific anchors. Linking/migration requires an authenticated host action; no model directive is added in M0a.

**Verify:**

```bash
uv run --no-sync pytest --no-cov tests/unit/context/test_project_registry.py tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_operator_paths.py -q
```

Expected: stable grouping, no mixed fork state, no partial registry and preserved security identity. Exercise real subprocess/filesystem locking on Windows and through Linux PR CI.

## Checkpoint 1 — Independently accept foundations and close

- [ ] Verify K1’s shared-policy subset and K5’s registry/isolation subset on the actual implementation. Synthetic filesystem inputs exercise production paths; they are not mock policy substitutes.
- [ ] Obtain one consolidated Codex CLI review, resolve in-scope blockers with focused checks, and complete the final verification below. Use Fable only where Claude judges the point genuinely complex. Preserve nonblocking findings with named owning issues/roadmap entries.
- [ ] Record #385 acceptance, ADR/provenance, shared API contracts, selected parser pin/license, platform qualifications and exact source hashes. Hand registry/policy APIs to M0b/M1/M3 and the parser pin to M0a-3/#391.
- [ ] Audit current-state documentation before the closing commit and again before merge, including README, roadmap, docs/decision indexes, transitional registry and linked owning issues. Apply necessary mutable-document corrections in this PR; preserve frozen predecessors. Run the filing hygiene checks.
- [ ] Confirm that evaluation and feasibility results were not used as closure prerequisites. Later K1/K5 obligations remain with their owning slices.
- [ ] After the operator-authorized merge and required CI acceptance, deliberately close **#385 and #390** under explicit GitHub authority, with the merge/evidence references. PR wording uses **“Refs #385, #390”**; merging does not itself establish issue closure.

**Closure:** Tasks 0–2, required own tests, Windows final coverage, Linux PR CI, checkpoint review and evidence must be accepted. Outstanding #385 criteria hold this plan. No probe, service or benchmark is a condition of foundations closure.

## Verification and final review evidence

Record absolute checkout, branch, source HEAD/tree or explicit dirty-diff hash, interpreter/environment/configuration, run IDs, platform, exact commands, exit status and retained output. Record HEAD/status before and after measured runs. Preserve default selection, root conftest, run-context/guard validity and all skips/UNKNOWN observations.

Complete focused fix cycles before freezing the final code head. Run **one Windows full suite with coverage** using the canonical commands, then Ruff:

```bash
uv run --no-sync python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json
uv run --no-sync python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json
uv run --no-sync ruff check .
```

Follow current canonical product floors, the **80% aggregate production-code minimum**, and safety-critical no-regression requirements. Do not infer a gate from rounded output or pytest’s exit code alone.

**PR CI on Linux is the second full run** and provides Linux filesystem/locking evidence. Bind it to the actual candidate/merge SHA and inspect the required cases and skips. No separate WSL run is scheduled; use WSL only to investigate non-trivial CI failures.

Any code change after the Windows full run invalidates its final-code-head attribution. Preserve that run and disclose the exact delta for operator disposition; do not silently repeat the suite, relabel earlier evidence or claim newer bytes were tested.

Filing verification:

```bash
uv run --no-sync pytest --no-cov tests/unit/docs/test_docs_index.py tests/unit/docs/test_plan_directory_hygiene.py tests/unit/docs/test_open_work_pool_hygiene.py -q
```

The final handoff contains the sanitized source/config-bound manifest, per-check status, reviewer responses, requirement-to-check map, exceptions with owners, and full hashes of the reviewed spec and saved plan. Archive/hash required review evidence before temporary records can be pruned. Private memory and raw workstation artifacts are not project dependencies.

## Explicit exceptions and custody

| Outside this plan | Named owner and consequence |
|---|---|
| Cases, offline grader and generic-harness decision | [Plan 12.5 / #389](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/389), delivered through PR #444; independent evaluation scope. |
| Packages/embeddings, Redis/Postgres, ACP/Zed probes | [M0a-3 / #391](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/391), still unnumbered; independent dispositions. Task 1 owns its parser qualification. |
| Former Task 7 experiments | Start of frozen v12 M5a (Initializr), M7 (bounded G1′/G0 graph) and M5b (L2), per spec §8.1; no acceptance content removed. |
| Durable capture, outbox, per-user Gateway diagnostics and #303 contract | Frozen v12 M0b; broad telemetry consolidation stays #303. |
| Indexing/retrieval/worker and real-corpus qualification | Frozen v12 M1/M2. |
| Automatic memory, notice binding, checkpoint, encryption/keys, purge/rotation, backup/restore and imports | Frozen v12 M3, including K5-R1/R2 and native keystore tests; learning/archive remains M6. |
| Dependency tool, compatibility, impact and project graph products | Frozen v12 M5a/M5b/M7; C3/C4 remain there. |
| Savings tables, model runs and held-out acceptance | #248 / Q29; OC-4 remains open. No paid calls here. |
| Session load, picker, diagnostics beyond this scope | Plan 11.7/#240, model-selection work and Q27 respectively. |
| Commit/push/PR/merge, service/keyring/GUI operations and cleanup | Separate operator authority; this plan does not grant it. |

**Authoring checks:** predecessor/spec hashes and Task 0 source inspected read-only; no tests, writes or external-service checks performed in Round 81.  
**Remaining risk:** Task 0 review and acceptance are pending; Tasks 1–2 and final platform evidence are not yet accepted.