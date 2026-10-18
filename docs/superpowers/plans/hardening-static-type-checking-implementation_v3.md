# Static typing cohort 2: strict YAML registry Implementation Plan — repository v3

> Repository successor v3 maps to the approved cohort-2 private draft v2, SHA-256 `2165034036fedd906bde44319ad5c350a0da57448a36a309ecfb80686c81bf57`.
> Direct operator instruction on 2026-10-17: "Approved. Get Plan 12 ownership clearance, then implement v2 with one unpushed local commit and Windows/WSL verification. Have Claude review the results before bringing them to me. Do not push or open a PR."
> [Exact plan review ACCEPT](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329#issuecomment-6237076348); [execution grant recorded](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329#issuecomment-6237141651); [signed Plan 12 owner clearance](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329#issuecomment-6237178681).
> Owner clearance binds CP4 `70bc3dafa77b5bb526b345f563f439cc2b7cc1e9`. While its r9 live window is open, only light serial Mypy and `tests/unit/model_policy/test_registry.py` may run: no xdist, broader/full/profile/ACP/agent/Gateway/integration runs, port 8765 use or redis container. Broader preflights and every remaining verification gate wait for explicit closure on #237 and #329. Static baselines and the narrowly permitted RED/GREEN work run first; no acceptance gate is waived.
> The reviewed contract below retains its draft-freeze prerequisite states as provenance; this receipt supplies operator, exact-plan review and file-owner authority. It does not claim final verification or source delivery. One unpushed local commit only; no push, PR, merge, issue closure, cleanup or watcher restart.
> Repository v2 is archived byte-for-byte as Git blob `347251f7f4423c241ec53c9d4465e9afc8d83abc`. Master-plan impact: updated - existing source-typing child points here. Work tracking impact: unchanged - #329 owns live state; no new work item.

Complete successor to the unchanged first draft. Incorporates Claude's review of draft SHA-256 `e601d4adbcba5a5aa4f5fe7cbefd16856b4a2795e75d2ed7fdb6e08e6627caa6`: explicit local Git-bundle delivery to WSL and the existing secret-scanner disposition boundary. No execution is authorized by this revision.

> **For agentic workers:** After direct operator approval, use `superpowers:executing-plans` for inline execution. Codex implements; Claude independently reviews. These checkboxes grant no execution authority.

**Goal:** Make `optimus_model_policy.registry` type-clean and reduce #329's exact source exception set from 45 to 44 without changing YAML acceptance or registry values.

**Architecture:** Match PyYAML's invariant dictionary return contract in the private loader's annotations. Preserve its existing runtime rejection of every non-string key. Reuse the existing Git-backed ratchet, hook, CI and real-model tests.

**Tech Stack:** Python 3.14; frozen uv lock; Mypy 2.3.1; types-pyyaml 6.0.12.20260906; pytest; native Windows and Ubuntu-24.04 WSL.

**Spec:** [#329's accepted remaining-debt custody](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329#issuecomment-6234945637), the contract below, and [the existing hardening masterplan](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/f704db0c8cd1905807fb334af9bcd332e9143f1f/docs/superpowers/plans/hardening-runtime-quality-masterplan.md). Issue #329 remains the live authority; #328 records only this cohort's test-double classification.

## Approval requested — operator section

Approve a **single-module registry cohort**, a new main-based Windows lane and separate WSL environment, fresh static baselines, one normal-hook **unpushed local commit**, and serial Windows/WSL final verification followed by Claude review. Publication, merge, issue closure, cleanup and restarting the retired watcher remain separate decisions. **This request prepares the plan only; no implementation or environment creation has started.**

At main `f704db0c` (tree `1873d9e2`), the 45 exceptions contain two `override` errors in `registry.py:148`, both caused by `dict[str, Any]` overriding PyYAML's `dict[Hashable, Any]`. Change only the `Hashable` import, method return annotation and local accumulator annotation; keep the string-key guard, control flow, errors, schema and hashes unchanged. Remove only `optimus_model_policy.registry` from the source override list. Extend the existing real-YAML rejection matrix with boolean, nested integer and sequence keys.

This closes one complete module with no dependency upgrade, new suppression, Protocol/property change or credential coercion. Platform diagnostic forecasts and the detailed verification contract are below.

## Prerequisites at draft freeze

| Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| Current main, 45-module set and accepted diagnostic evidence identified | yes | Codex | main f704db0c has the exact accepted b69038e1 tree; selected module has two errors on each host |
| Exact loader contract and existing real-value tests inspected | yes | Codex | no source code or tests executed for this planning request |
| Plan 12 overlap disposition | no | Codex / Claude | Genuinely absent; unmerged CP4 also changes registry.py, its tests and pyproject.toml; clean status alone is not owner clearance |
| Independent review of this exact plan | no | Claude | Genuinely absent at draft freeze; required before presenting it for operator approval |
| Fresh lane, environments and execution grant | no | Operator / Codex | Merely unauthorized; schedulable after direct approval; the cleaned-up cohort-1 lanes will not be resurrected |

**Non-goals:** the other 44 modules; whole-track mock conversion; MCP/Plan 11.7 contracts; model catalogs, prices, roles or qualification receipts; YAML grammar changes; ratchet/bootstrap redesign; dependency or secret-scanner policy changes; live services, UI exercises, paid probes or watchers. #329/#328 and parent tracks stay open.

---

## Global constraints — agent-facing contract

- Planning pin: main `f704db0c8cd1905807fb334af9bcd332e9143f1f`, tree `1873d9e287562ecdd0e1a42d543ac5c3da11fcad`. Recheck remote main, local status, ownership and overlapping lanes before execution. A changed pin or overlapping writer stops implementation for an explicit disposition; do not silently transplant the approval or pause another lane.
- Proposed Windows lane: `C:\worktrees\optimus-cost-agent-worktrees\optimus-cost-agent-wt-codex-typing-c2`, branch `agent/codex/static-typing-registry-cohort`, from the approved main pin. Do not switch/update the canonical stale main checkout. Fresh WSL source verification uses its own Git-native clone under `/root/optimus-verification/typing-c2-20261017`.
- Native Windows uses Python 3.14.4; WSL uses the previously reviewed official Astral Python 3.14.8 build 20261013 in a fresh task-owned neutral path, e.g. `/root/optimus-verification/typing-c2-runtime-20261017/py3148`. The matching archive is `cpython-3.14.8+20261013-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz`, SHA-256 `d8faa1b588506b9e3e5a3f57807bb056d534a1641a6b10d15b6ea3f0b413b960`; the retained original is an optional verified cache, never a repository operating dependency. Do not retry the known-failing WSL 3.14.4 full-run route.
- Each environment has its own `.venv`, Mypy cache and `PRE_COMMIT_HOME`. Sync with `uv sync --frozen --extra dev` before measured runs, then use `uv run --no-sync`. Provision configured hook environments under the verification PATH; a native WSL clone may install its own hook. Do not rewrite shared Windows hooks or change global Python/cache/config stores.
- Preserve `files = ["src"]`, Python target 3.14, all diagnostic defaults, the exact `confusable_homoglyphs` import exception and all other 44 source exceptions. No new `Any`, cast, ignore, source exclusion or wildcard. Keep `uv.lock`, bootstrap fixtures, ratchet implementation, hook/CI wiring, test profiles, secret baseline and historical reports unchanged.
- Preserve errors, failed/interrupted attempts, skips and UNKNOWN evidence. A failed gate stops the attempt; no retry-to-green, bypass, extra source commit or automatic recovery. Historical Windows-safety qualifications remain historical; new results do not retroactively waive them.

The forecast is **45→44 exceptions**, Windows **215→213** unmasked diagnostics and WSL **206→204**, with zero new diagnostics. These are forecasts until fresh execution; the baseline inventory distinguishes accepted measurements from current source inspection.

## Review focus

1. Widened annotations must not admit boolean, integer, null or sequence keys: exercise the existing YAML rejection test, including the three Task 1 additions.
2. Nested duplicates, anchors, aliases, merge keys and executable/custom tags must keep `RegistryError.code == "YAML_REJECTED"`: retain the existing rejection matrix.
3. Valid defaults/overrides must produce identical values and effective hashes: reuse the existing fixture, override and canonical-hash tests unchanged.
4. A removed exception must stay removed, including staged-file tricks: run the existing history, staged-growth and repository ratchet controls without changing their allowance mechanism.
5. Platform evidence must expose every remaining diagnostic: compare complete unmasked multisets by path/line/column/code/message/multiplicity, recording cleared, retained and new entries separately; a lower net count is insufficient.

## Exact future file surface

| File | Permitted change |
|---|---|
| `src/optimus_model_policy/registry.py` | Import `Hashable` from `collections.abc`; return and local mapping annotations become `dict[Hashable, Any]` |
| `pyproject.toml` | Delete the one exact source exception `optimus_model_policy.registry` |
| `tests/unit/model_policy/test_registry.py` | Add three cases to `_SYNTAX_REJECTIONS`, using its existing parametrized test |
| `docs/superpowers/plans/hardening-static-type-checking-implementation_v3.md` | File this complete approved cohort contract with exact private-draft/review identities |
| `docs/superpowers/plans/hardening-static-type-checking-implementation_v2.md` → `docs/superpowers/plans/archive/hardening-static-type-checking-implementation_v2.md` | One byte-identical archival move after successor approval; old Git blob `347251f7f4423c241ec53c9d4465e9afc8d83abc` must be preserved |
| `docs/superpowers/plans/hardening-runtime-quality-masterplan.md` | Repoint only the existing static-typing child-plan link to repository v3 |
| `docs/README.md` | Repoint its existing source-typing row to repository v3 and describe the registry cohort |
| `reports/static-typing-cohort-2-verification.md` | New **pre-commit candidate snapshot**, explicitly provisional; exact-source post-commit final receipts go on #329 and in retained external evidence without amending this file |

Use the existing hardening-child registration route; no new issue, backlog work entry or duplicated progress authority. Frozen predecessor plans/reports are not rewritten to repair links; use the existing archive-aware resolver. No other file/interface expansion is implicit.

## Task 1 — establish source custody and the static red case

**Consumes:** the approved pin, frozen environment and 45-module configuration. **Produces:** refreshed overlap disposition, attributable static baseline and two unsuppressed registry errors.

- [ ] Obtain a signed comment on #329 from the current Plan 12 file owner resolving the registry/test/config overlap. A fresh technical reviewer cannot grant that ownership. Observed CP4 head `70bc3daf` is unmerged and changes the same three files, although its registry diff is outside `_StrictLoader`; this observation grants no ownership. Refresh immediately before mutation. If the cohort cannot remain independent at the approved pin, stop and revise the plan; do not absorb CP4 or claim its unmerged tests.
- [ ] Create the approved isolated lane only after operator approval; prepare both separate environments and hooks. Capture actual resolved executable, clone and pytest basetemp paths and scan the current literal repr-absence sentinels before tests. Run coverage-free preflight modules `tests/unit/tools/test_process_tree.py`, `tests/unit/mcp/test_client_config.py`, `tests/unit/tools/test_debug_trace_message_rule.py`. Then use the canonical `python -m tools.testing.run_profile --profile commit` with no `--base` against the clean index; record its actual selection. A checkpoint's `--base` interface is not the commit interface.
- [ ] Before source edits, run configured all-source Mypy and capture a fresh unmasked run on each host. For the latter derive a temporary config from the actual project config by removing only the measured source-debt override, retaining the third-party import exception and every other option; record its bytes/hash. Use `python -m mypy --config-file <derived-config> --no-incremental --cache-dir <fresh-own-cache> --no-pretty src`. Require the current 45-module union and the two expected registry errors; report/resolve drift before continuing. No fresh run is claimed by this plan.
- [ ] Add these three entries to the existing `_SYNTAX_REJECTIONS` map: `"boolean key": "true: one\n"`, `"nested non-string key": "models:\n  1: one\n"`, `"sequence key": "? [a, b]\n: one\n"`. The existing `test_the_loader_rejects_ambiguous_or_executable_yaml` must raise `RegistryError` with code `YAML_REJECTED` for each. Existing passing behavior tests may remain passing; do not invent a runtime defect.
- [ ] Remove only the registry exception in `pyproject.toml`, before changing production annotations. Run `uv run --no-sync python -m mypy --config-file pyproject.toml`; require the two registry `override` errors against `SafeConstructor` and `BaseConstructor`. This is the meaningful static RED case. All 226 source files remain checked.

## Task 2 — close the registry module without changing its behavior

**Consumes:** the two static failures. **Produces:** a type-clean module, unchanged string-only loader semantics and exactly 44 remaining exceptions.

- [ ] In `_StrictLoader.construct_mapping(self, node: Any, deep: bool = False)`, use return type `dict[Hashable, Any]` and the same local accumulator type. Add `Hashable` to the existing `collections.abc` import. Preserve every executable statement, guard ordering, exception text, public model, serialized value and hash constant. `_load_yaml` keeps its existing `tuple[dict[str, Any], bytes]` contract and runtime string-key validation; no assertion/cast is added to bridge it.
- [ ] Run `uv run --no-sync pytest --no-cov tests/unit/model_policy tests/unit/tools/test_mypy_ratchet.py`; require all selected tests to pass, including real-file YAML/schema/hash controls and all existing ratchet controls. The #328 receipt classifies registry tests as real models/files, no mock conversion. No broad test-double rewrite is included.
- [ ] Run configured all-source Mypy and its explicit `--platform win32` form, plus `uv run --no-sync pre-commit run optimus-mypy --all-files` and `uv run --no-sync ruff check .`. Require zero configured diagnostics, exactly 44 literal exceptions and registry permanently outside that list. Compare the production diff semantically: only the import and two annotations may change.

## Task 3 — one local delivery and serial final verification

**Consumes:** the closed cohort and approved exact filing surface. **Produces:** one unpushed commit, source-bound platform evidence and Claude's final review for the operator.

- [ ] File repository v3 and its new pre-commit verification snapshot, preserving the predecessor bytes and changing only the named mutable pointers. Do not add another issue or alter historical baseline data. Stage only declared paths; inspect the staged source/config/doc diff and execute focused docs hygiene, ratchet and runtime checks before the normal commit. Run `git diff --check`, Ruff and the configured `optimus-secret-scan` hook against the complete staged text selection. The existing UTF-8 adapter scans new Markdown normally: neither new document receives a path exclusion or an inline allowlist. Its existing R100 exemption applies **only** to the byte/mode-identical predecessor archival rename. Cohort 1's approved three JSON baseline identities and five Python pragmas remain unchanged and grant no equivalent exemption for new files. If any new document hash is flagged, retain the finding, staged bytes and baseline before/after identities and stop before a successful commit; any pragma, baseline growth or scanner change needs its own exact reviewed/operator-approved successor. Do not regenerate the baseline or borrow a historical exception. Obtain Claude's bounded pre-commit review, then create **one** local commit with normal hooks. Re-run `tests/unit/docs/test_open_work_pool_hygiene.py` at committed HEAD because its document selection is commit-sensitive.
- [ ] Deliver that unpushed commit to the WSL clone by a **local Git bundle**, never by a remote source push or filesystem/venv copy. From the Windows lane run `git bundle create <external-evidence>/cohort2-source.bundle agent/codex/static-typing-registry-cohort`; retain its SHA-256 and run `git bundle verify` on the saved bundle. From the WSL clone run `git bundle verify <same-bundle-under-/mnt/d>`, then `git fetch <same-bundle-under-/mnt/d> refs/heads/agent/codex/static-typing-registry-cohort` and `git switch --detach FETCH_HEAD`. Require the exact Windows commit SHA, tree SHA and clean status in the clone before any candidate acceptance run. The full-history bundle retains ancestors for the ratchet. The bundle lives in the retained external campaign, not either measured checkout. No additional commit is created to transfer it.
- [ ] Verify Windows first and WSL second at the identical clean commit/tree, with frozen separate environments and preflights. Run both configured Mypy forms and a fresh unmasked comparison. Predicted totals: Windows 213 diagnostics/44 error files; WSL 204/43; 226 checked on each. Require exactly the two registry errors cleared and zero new diagnostics, retaining every other diagnostic and platform difference. The other 44 modules remain deferred.
- [ ] On each host run the canonical single full default coverage gate: `uv run --no-sync python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json`, then `uv run --no-sync python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json`. Bind the export/report to exactly one eligible full session at this commit using repository record readers and an explicit eligibility receipt; merely naming a run record is not proof. One coverage writer per checkout; preserve default marker selection and all skips/native capability/UNKNOWN qualifications.
- [ ] Retain before/after source identities, commands, interpreter/dependency/config hashes, stdout/stderr, exits, normalized deltas, run contexts and coverage/eligibility receipts outside the measured source tree before retention can prune them. Do not amend/add a commit to attach later finals. Claude reviews the complete exact-source results on #329 before the operator sees them. Publish no source, open no PR, merge nothing, leave issues open and retain the new environments pending a separate cleanup decision.

## Planning provenance and handoff

The exact private draft and supplied-source Claude review receipts are retained as external archival provenance, with their identities recorded above and on #329. They are not repository operating dependencies. The contract here is self-contained. The approved source pin, exact file surface, platform versions/counts, diagnostic-multiset comparison, Git-bundle transfer, runtime semantics, scanner boundary and all acceptance gates are specified here. The predecessor report and immutable original bootstrap remain historical evidence; this cohort does not rewrite either.

At draft freeze no implementation, setup or fresh tests had run. The filing receipt and the explicitly provisional candidate report distinguish subsequent development evidence from post-commit finals. #329 owns the source-bound final receipts and Claude's results review. Both #329 and #328 stay open.
