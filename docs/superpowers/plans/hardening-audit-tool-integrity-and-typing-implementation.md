# Audit-tool integrity and typing implementation plan

> **Custody:** The hardening runtime-quality masterplan owns the parent-level status; this plan owns task checkboxes and evidence gates. Plan promotion alone grants no implementation authority.

**Goal:** Preserve the accepted Task 13 inventory by enforcing an independent pinned-source comparison, then type-check the audit tools without altering accepted evidence or generated output.

**Architecture:** Extend the existing pinned discovery test to compare fresh canonical bytes with the committed inventory and bind its digest to the accepted audit. The subsequent typing lane first measures current diagnostics, then removes them in reviewed batches while repeatedly checking the guard and frozen artifacts. The operator released only Task 1 (#330); Task 2 (#331) requires separate operator release; Tasks 3–4 additionally require a complete reviewed `_v2` successor and operator authority. The masterplan owns the child-plan projection; this plan owns task checkboxes only.

**Tech stack:** locked Python 3.14, uv, Git, pytest, Ruff, mypy and existing audit tooling. **Spec:** `docs/superpowers/plans/hardening-runtime-quality-masterplan.md`, particularly its custody register, integrity prerequisite, program waves and child-plan pickup contract. Work issues: #330 and #331; track #315; feature #232. Frozen evidence: `reports/plan-11-26-duplication-candidates.json`, `reports/plan-11-26-duplication-audit.json`, and the G6/G7 records; source commit `b62462f11abe858f58af12fa2d2f159eae09d832`.

## Custody boundary

`HARDENING-TRACK-AUDIT-TOOLING` owns Task 1, `HARDENING-ITEM-AUDIT-INVENTORY-REDERIVATION` (#330), and Tasks 2–4, `HARDENING-ITEM-AUDIT-TOOL-TYPING` (#331). Check the historical backlog for conflicts; do not create a backlog registry row.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| Custody | #315, #330 and #331 open without conflicting work | yes | Codex | satisfied; issues open and no competing audit-tool PR at main `f49b8dd` on 2026-11-03; recheck before delivery |
| Historical source | Pinned Git object and committed artifacts readable | yes | Codex | satisfied; native Windows and WSL2 read the pin and artifacts on main `f49b8dd` |
| Baseline | Fresh discovery equals inventory and accepted audit identity | yes | Codex | satisfied; Windows 3.14.4 and Linux 3.14.6 independently reproduced the 176-group inventory; future mismatches stop Task 1 |
| Review | Independent plan review accepted | yes | reviewer | satisfied; Claude Opus 5.5 high session `00c5af95-00ab-4a68-a2a3-93f44e678576` gave technical GO with limitations for the approved plan |
| Authority | Plan approved and Task 1 separately authorized | yes | operator | satisfied; operator approved the plan and Task 1 on 2026-11-03; commits and publication require separate authority |
| Authority | Tasks 2–4 released | no | operator | merely unauthorized: Task 1 release grants no later task |
| Typing baseline | Current diagnostics and files measured | unknown | future Task 2 owner | merely unauthorized: measure after separate release |
| Services | Offline work without real service or paid calls | yes | Codex | satisfied; no disposition required |

Update prerequisite values only to reflect evidence and authority actually received when the plan is committed.

## Global constraints

- Frozen inventory, audit, historical G6/G7 custody tuples and discovery behavior remain unchanged by Task 1. Task 1 adds no dependencies. No coverage-floor reductions or global suppression; future stub dependencies must be named in a reviewed successor.
- Status is issue-owned after Plan 11.29; parent board is the file-consistency record. No child self-status or backlog registry row.
- The masterplan waves are a default order, not dependency edges. The earlier Guardrail truth wave is unfinished; Task 1 uses nothing from it and reorders no dependency. Tasks 2–4 remain behind the guard and in their later typing wave. If the operator requires a masterplan successor first, stop until it exists.
- Use isolated current-main worktree, own locked environment, capture exact HEAD/status, interpreter, commands, platform and output; never reuse evidence between hosts, PR CI and actual merge. Preserve all failures, skips, unsupported and UNRUN results.
- Require independent review before behavior-bearing commits, and explicit separate commit, publication, merge and issue-state authorization. Post reviews verbatim according to project rules; retain reviewer checkpoint record. Use `Refs #330` rather than any closing-keyword construction in PR text.
- Keep #369 broader POSIX, #273, and Evidence/A2A untouched. No #331 execution is authorized.

## Task 1 — Permanent inventory guard (#330; released)

**Files:** modify `tests/unit/tools/plan1126_runtime_audit/test_duplication.py`; create the intended child plan; update `docs/superpowers/plans/hardening-runtime-quality-masterplan.md`, `docs/README.md`, and `tests/unit/docs/test_plan_directory_hygiene.py`. Existing inventory, audit, discovery and profiles are inputs, not change targets. Profile test stays at its existing node ID.

- [x] Reconcile #232, #315, #330, #331, open PRs, current main, historical backlog and file hashes; stop on material conflict.
- [x] Prepare each execution and disposable worktree with its own environment using `uv sync --frozen --all-extras`; record the source and platform before measurement.
- [x] Record source pin, artifact hashes, group count, audit source and digest, and Python version. Compare freshly derived bytes on separately attributed Windows and WSL environments; stop on mismatch or missing source. Use the discovery command below with `--inventory` pointing outside the worktree, then compare hashes.
- [x] **C1 — plan and parent:** only after plan approval, explicit Task 1 release and commit authorization, create the plan. In the same change set the masterplan row to:

  | Track | Child plan | Status | Scope | Next gate |
  |---|---|---|---|---|
  | `HARDENING-TRACK-AUDIT-TOOLING` | [Audit-tool integrity and typing](hardening-audit-tool-integrity-and-typing-implementation.md) | `Active` | `HARDENING-ITEM-AUDIT-INVENTORY-REDERIVATION` and `HARDENING-ITEM-AUDIT-TOOL-TYPING` | Task 1 (#330) is the only released task. Tasks 2-4 (#331) are unreleased and stay behind the guard and the later typing wave. No track completion is claimed. |

  Remove `future` from the owner cells of the three prerequisite rows for this plan. In `test_hardening_masterplan_owns_exactly_fifteen_child_plan_statuses`, expect Active `{"HARDENING-TRACK-CI-GUARDRAILS", "HARDENING-TRACK-AUDIT-TOOLING"}` and 11 `Not drafted` rows. After the CI-guardrail row in `docs/README.md`, add `| [Hardening: audit-tool integrity and typing](superpowers/plans/hardening-audit-tool-integrity-and-typing-implementation.md) | Inventory re-derivation guard and audit-tool typing contract |`. If staged landing is chosen, revise these values before execution.

- [x] **C2 — guard:** With separate commit authorization and independent review, in the existing `test_duplication_inventory_is_deterministic_and_reconciles_prior_seeds`, add `import sys` at module level after `import json`, then insert the following after the determinism assertion:

```python
committed = (_ROOT / "reports" / "plan-11-26-duplication-candidates.json").read_bytes()
audit = json.loads((_ROOT / "reports" / "plan-11-26-duplication-audit.json").read_bytes())
fresh = canonical_json_bytes(first)
matches = fresh == committed  # not inline: on CI pytest would ndiff both full inventories
assert matches, f"fresh {_sha256(fresh)} != committed {_sha256(committed)}; {sys.version}"
assert first["inventory_digest"] == audit["inventory_digest"]
assert audit["source_commit"] == _PINNED_COMMIT
assert len(first["candidate_groups"]) == audit["counts"]["raw_groups"] == 176
```

- [x] In disposable Git worktrees with frozen environments, record exact inputs, outcomes and `duplication.__file__`. Against the parent of C2 and C2 respectively, M1 changes a member character in the inventory: the old node passes and the candidate guard fails byte comparison. M2 changes `feature_similarity >= 0.92` to `>= 0.50`: the old node passes and the guard fails byte comparison. M3 applies M2 then regenerates inventory in the disposable worktree with `uv run --frozen python tools/run_plan1126_runtime_audit.py duplication discover --source-commit b62462f11abe858f58af12fa2d2f159eae09d832 --inventory reports/plan-11-26-duplication-candidates.json` from the mutant worktree root: the old node passes, the guard's byte comparison passes, and audit digest comparison fails. If M2 produces identical bytes, the sole predeclared fallback is `_digest(material)[:20]` to `[:19]` in `_callable_record`. Stop on other surprises; retain all results and never publish mutant artifacts.
- [x] On Windows and WSL2 separately run `uv run --frozen pytest tests/unit/tools/plan1126_runtime_audit/test_duplication.py tests/unit/docs/test_plan_directory_hygiene.py tests/unit/docs/test_open_work_pool_hygiene.py tests/unit/docs/test_docs_index.py tests/unit/tools/test_verify_masterplan_impact.py tests/unit/tools/test_test_profiles.py -q`, `uv run --frozen ruff check .`, and `uv run --frozen pre-commit run optimus-secret-scan --files <changed files>`; run normal applicable hooks and record every skip or unsupported gate. Verify the plan hygiene test sees the plan at committed HEAD. Before commit, call its `_assert_prerequisites_table` helper directly on the final text.
- [x] **C3 — records:** tick only verified steps; add `## Task 1 evidence` bound to the C2 head with platforms, interpreter, commands, run IDs, artifact hashes, mutant outcomes and skips, retaining raw logs locally. Set the masterplan re-derivation prerequisite to `yes` and `satisfied; no disposition required`, update the next gate and do not mark the track complete. Rerun documentation tests on C3 and disclose C3 as the delta from the tested head.
- [ ] **Review and delivery:** verify the changed-file list excludes `reports/`, `tools/`, profiles and backlog. Seek independent review and distinct commit/publication/merge/closure authorizations. Use `Master-plan impact: updated — HARDENING-TRACK-AUDIT-TOOLING` and `Refs #330` in the PR. Check actual-merge CI separately before any authorized closure.


## Task 2 — Audit-tool typing baseline (#331; unreleased)

- [ ] After separate authorization, run the locked mypy against `tools/plan1126_runtime_audit/` and separately include `tools/run_plan1126_runtime_audit.py`, in both default and Windows platform modes; capture command, source, environment, full diagnostic identities/counts and actual files, classify stub/config and source diagnostics, and independently review a proposed exact batch/file inventory and tests. 130 errors in 11 of 21 files is historical only. No implementation or dependency change is released by this plan. Develop a complete versioned successor before further implementation as required by plan fidelity.

## Task 3 — Audit-tool typing batches (#331; unreleased)

- [ ] On an approved source-bound baseline and separately approved exact file/diagnostic batches, clear stub/config problems first, then source diagnostics, using existing validated types, `TypedDict` or `typing.cast` where justified. No `assert isinstance` solely to appease the checker, no new runtime raise path, no blanket missing-import exemption, and no changes to frozen/generated bytes. Each batch gets focused tests, inventory guard, `duplication verify`, render byte-check, diagnostic multiset delta, independent review and separate commit authority. File lists and detailed commands must be specified by the reviewed `_v2` successor before any such task starts.

## Task 4 — Audit-tool typing acceptance (#331; unreleased)

- [ ] After separately authorized batches, demonstrate a required additive audit-tool Mypy gate with no errors in both platform modes; assess `.github/workflows/guardrails.yml`, `.pre-commit-config.yaml`, `pyproject.toml` and the existing `test_mypy_gate_wiring` ratchet. Preserve source gates and accepted artifacts, pass the pinned guard and relevant CI checks. On terminal acceptance and operator authority, archive the plan, rewrite the parent link and `Complete` row, and update hygiene sets and README.

## Review focus and stop conditions

- Source pin absent, Git export timeout, changed serialization/Python version, artifact mismatch, digest mismatch, missing audit or unexpected 176-group count: record exact result and stop.
- Deterministic but changed discovery or a refreshed self-consistent inventory must not bypass the frozen audit binding; demonstrate with attributable mutants, no historical rewrite.
- Failure output stays bounded; no full-inventory pytest diff.
- Preserve the existing selected test node and prove profile/CI includes it; missing full-history checkout is not a pass.
- Parent status/plan links, active-count hygiene and issue state must agree. The plan contains no self-status; do not declare the later typing track complete.



## Task 1 baseline evidence

At clean main `f49b8dd436e61b20b0e60e0f5440f3533541dfad`, independently ran `uv run --frozen python tools/run_plan1126_runtime_audit.py duplication discover --source-commit b62462f11abe858f58af12fa2d2f159eae09d832 --inventory <output-outside-worktree>` in native Windows (Python 3.14.4) and WSL2 Ubuntu 24.04 (Python 3.14.6), after separate frozen all-extras syncs. Both discovery commands returned PASS and produced SHA-256 `25afe9ecaf2e13e7d302027782fada04f73d3436ba3a099cfc0e702d0f927e40`, exactly matching the committed inventory: 176 groups, source `b62462f11abe858f58af12fa2d2f159eae09d832`, inventory digest `193cc3f963aee9515b2828fbac734a6fb3dda228af31845b3205f6a2084c1797`. Accepted audit SHA-256 is `14e8fd8a69032c3ee6a832c9af78350e6721e14e668929b1dc8e9b87f5c4c07c`; its inventory digest and source agree. The Windows baseline record captured a clean status. A later `git status --short` in the same Linux clone listed only the four C1 paths; retained OS identity and source/hash verification establish that the source pin and frozen artifacts are unchanged.

Qualifications: first restricted Windows uv launch exited 2 before Python because its cache was inaccessible; a separate permitted launch performed the successful derivation. First Linux wrapper exited 127 at missing uv PATH before derivation; the PATH-corrected run synchronized and derived successfully, then its final status command exited 128 due a wrapper carriage return. A retained later status/hash verification exited 0 and listed only the four C1 paths. These failures remain retained in local raw logs. No pytest, guard or failure-control acceptance is claimed by these CLI baseline results. Execution environments were synced at C1; at C1, disposable mutant worktrees were not yet prepared. This C1 record claims no guard implementation.

## Task 1 evidence

Implementation C2 `bec8dd54f91333cc212d4cc6246a7d76f8202767`, parent C1 `40877f2dc78b766920c6aa33bb580e833ba62b08`. The guard preserves its test node and discovery code and adds only the approved frozen-inventory and accepted-audit assertions. Frozen artifacts retain the baseline hashes above. C1 and C2 normal-hook commits passed. C1's first global-environment attempt failed with unavailable tools, missing libraries and a sibling-checkout import; the subsequent frozen-environment command passed without bypass. This failure remains historical evidence.

On clean C2, ran the six-file focused pytest command above, with source and status recorded before each run: Windows Python 3.14.4 **289 passed, 1 skipped**, run `20261103T122222-51452-d9b8c0`, active/default selection, native valid, parent UNKNOWN, full guard, COMPLETE, exit 0; the skip requires Windows symlink privilege. WSL2 Python 3.14.6 **272 passed, 18 skipped**, run `20261103T122454-724-f45491`, active/default selection, COMPLETE, exit 0, native/parent unsupported and guard unsupported_platform; skips require native Windows H5 capture. Ruff and scoped secret checks passed. These are focused results, not full-suite or CI evidence.

The three isolated Linux mutation differentials used C1 for the old node and C2 for the new node, each with its own frozen environment and recorded module path. M1 changed an inventory member: old passed, new failed byte comparison. M2 changed feature similarity 0.92 to 0.50: old passed, new failed byte comparison. M3 made the same discovery change and regenerated only the disposable inventory: old passed, new passed bytes then failed accepted-audit digest. All six outcomes matched predictions; no fallback was needed. Linux Python 3.14.6. Runs: M1 old `20261103T122328-498-419d95`, new `20261103T122347-532-5fe1d2`; M2 old `20261103T122401-558-7acba9`, new `20261103T122414-584-087b1b`; M3 old `20261103T122431-628-1fc470`, new `20261103T122448-672-8e8461`. Each pytest context completed; Linux native/parent/guard limitations apply. The initial control launcher failed shell parsing before Python; its replacement script ran the controls. No mutant artifacts or algorithm changes enter the delivery.

Known residual: the pre-existing fresh-versus-fresh determinism assertion remains inline and could render a large diff on actual nondeterminism; the new frozen-byte comparison has bounded hash diagnostics. Windows parent attribution remains UNKNOWN. GitHub issue labels and delivery publication, PR, merge and actual-merge CI are not established. C3 is the documentation delta from the tested C2; documentation tests and normal hooks verify that delta before its authorized commit. The track and #331 remain open and unreleased for further work.
