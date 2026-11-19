# Audit-tool integrity and typing implementation plan v2

**Reviewed successor and delivery record.** [#315](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/315) owns the parent track, [#330](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/330) owns the completed inventory guard, [#447](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/447) owns the completed replay repair, and [#331](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/331) owns Tasks 2–4.

**Goal.** Add a required, zero-error Mypy check for the audit package and launcher in default and `win32` modes. Preserve the pinned inventory, accepted artifact and renderer bytes, and existing runtime and replay contracts.

**Approach.** Give the audit tools a separate Mypy configuration with explicit namespace roots and resolve the launcher’s missing third-party stubs first. Clear source diagnostics in measured batches. Promote the new check only after both modes reach zero and the original source gates pass. The current checkout and tool settings are described at [the v1 plan](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/8008791770e1d96f12a498d158e40c789ed0d94d/docs/superpowers/plans/hardening-audit-tool-integrity-and-typing-implementation.md) and in the Task 2 baseline below.

## Delivery record

- Task 1 shipped through [PR #471](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/471). #330 recorded the accepted 176-group re-derivation and audit binding. #447 recorded the sealed-replay disposition and retained drift refusal.
- Tasks 2–4 shipped through [PR #507](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/507). The audit-only mapping and pinned dev stub preceded the six typing batches. Both Mypy modes now report zero errors across 28 audit files. The audit pre-commit hook, required CI steps and audit INI exception ratchet are enforced.
- On main at `6d6597667eda93b7b3d01aabf7c42f7a320ccf43`, required guardrails passed both audit and both source Mypy modes, the full suite and same-run coverage validation. All five frozen audit and inventory blobs matched the reviewed candidate. [Independent PR review](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/331#issuecomment-7003741502) · [Actual-merge guardrails](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/44488708445) · [#331 completed acceptance](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/331#issuecomment-7004709774)
- The completed plan and its [byte-preserved v1 predecessor](hardening-audit-tool-integrity-and-typing-implementation.md) are filed in the flat plans archive. The [masterplan status board](../hardening-runtime-quality-masterplan.md#child-plan-status-board) records the terminal disposition, with work custody in [#315](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/315).

The following sections preserve the reviewed plan and its release gates as historical instructions. The original independently reviewed draft is identified by SHA-256 `769d3d5df20a8a2e65ac5d563082e6d604260750785175b73491bf05dbe2822b`.

## Custody and constraints

- Use current `main`, a dedicated checkout and its own frozen environment. At each checkpoint record the commit and tree, working-tree status, commands, interpreter, Mypy and lock identities, exact exit status, and retained raw outputs. Refresh scoped baseline diagnostics on a newer `main` before applying a reviewed batch. When the target files, Mypy configuration, import graph or lock change, reconcile the refreshed findings and file list with the reviewer before proceeding.
- Retain `reports/plan-11-26-duplication-candidates.json`, `reports/plan-11-26-duplication-audit.json`, `reports/plan-11-26-duplication-audit.md` and the frozen G6/G7 custody inputs. Preserve environment identity, artifact verification and historical drift refusal. #273, broader POSIX work under #369 and Evidence/A2A keep their existing custody.
- Preserve the current `src/` Mypy configuration, exact third-party exception and exception ratchet. Audit typing uses normal import following. Additions to the runtime dependency set, generalized missing-import or error suppression, broad casts, new runtime assertions and new raised-error paths are outside these batches.
- Treat annotation effects on serialized data, schema generation or runtime reflection as behavior changes. Stop and record any such finding for owner review before widening a batch. Record unchanged artifact bytes and explicit negative-test outcomes at the relevant checkpoint.
- Use bounded offline checks and the ordinary required CI attached to authorized publication. The plan calls for no manual full-suite invocation or workflow rerun. If the normal commit profile selects a near-full run, record the dry-run selection and follow the owner’s no-full-suite constraint before committing. Each scoped release stays separate from commit, publication, merge and closure authorization.

## Task 1 — Pinned inventory guard · accepted

PR #471 added a permanent comparison of newly derived canonical inventory bytes against the committed 176-group inventory and bound its digest to the accepted audit at source `b62462f11abe858f58af12fa2d2f159eae09d832`. The pinned test was retained. Its historical Windows/WSL focused observations and three mutation differentials are carried by v1. The exact #471 merge `026b3fd18dbed0793b93a0072a430fac62ff56e4` passed its actual-merge checks, and #330 closed as completed. The inventory and audit Git blobs at reviewed main `8008791770e1d96f12a498d158e40c789ed0d94d` still match that accepted merge. [Historical Task 1 evidence](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/8008791770e1d96f12a498d158e40c789ed0d94d/docs/superpowers/plans/hardening-audit-tool-integrity-and-typing-implementation.md#L95-L110) · [Actual-merge acceptance](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/330#issuecomment-6606666395) · [Current pinned assertion](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/8008791770e1d96f12a498d158e40c789ed0d94d/tests/unit/tools/plan1126_runtime_audit/test_duplication.py#L311-L324)

PR #450 repaired four historical sealed-replay tests. #447 closed with drift refusal retained, and its separate Windows observation and Linux UNRUN limitations continue to apply. [Replay receipt](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/447#issuecomment-6536861786)

## Task 2 — Locked diagnostic baseline · captured

Reviewed main `8008791770e1d96f12a498d158e40c789ed0d94d`, tree `a89844fed5ce3828a74037b7c419dfd505eb0dda`, matched the clean measurement checkout byte for byte. Locked uv/Mypy used CPython 3.14.6 and Mypy 2.3.1 in WSL2. The `win32` result is static platform selection on that host. The baseline records each command, exit and explicit file/module identity.

| Invocation | Default | `win32` |
| --- | ---: | ---: |
| Audit package only with existing options | 153 | 150 |
| Package and launcher with existing options | Aborted at 46 | Aborted at 46 |
| Both targets with explicit bases | 168 | 164 |
| Both targets with explicit bases and an explicit `src` root | **153** | **149** |

In the aborted combination the same `checkpoints.py` resolves under two names, with and without the `tools.` prefix. Explicit bases resolve that collision. The explicit-bases-only run still treats 46 first-party imports per mode as untyped. Exposing `src` resolves those imports and increases the source diagnostics by 31 per mode on net. Each complete comparison has 28 explicit roots and errors in 15 files. The audit package accounts for 133 errors in each mode. The launcher accounts for 14/13 and the imported `tools/concurrency_capture.py` for 6/3. An absent `jsonschema` stub is one error in each launcher count.

Every `win32` diagnostic is present in default mode. The four default-only errors are the three Windows-only `ctypes` attributes in `tools/concurrency_capture.py` and the launcher’s `subprocess.CREATE_NEW_PROCESS_GROUP`. The helper is a followed import from `shutdown.py`. Batch 3 explicitly proposes authority to edit it, with a limited file boundary. [Import site](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/8008791770e1d96f12a498d158e40c789ed0d94d/tools/plan1126_runtime_audit/shutdown.py#L25)

## Task 3 — Six proposed batches · awaiting release

Counts are the allocations in the source-resolved baseline, including its one stub diagnostic per mode. Source and import resolution can expose additional type errors. Record the actual diagnostic difference and assign any newly exposed error to its reviewed owner before extending a batch. Exact remaining diagnostic identities should shrink for the released slice. Reviewed non-target diagnostics may remain pending their own slice.

| Batch | Default / win32 |
| --- | ---: |
| 1. Module discovery and stubs | 1 / 1 |
| 2. Evidence shape and inventory | 29 / 29 |
| 3. Shutdown and concurrency capture | 54 / 51 |
| 4. Client, custody and lifecycle probes | 20 / 20 |
| 5. Delivery, telemetry and semantic evidence | 36 / 36 |
| 6. Launcher and platform dispatch | 13 / 12 |

### 3.1 — Module mapping and jsonschema stubs

**Planned writes.** `tools/mypy_audit.ini` for mapping, then the existing `[project.optional-dependencies].dev` list in `pyproject.toml` and the corresponding `uv.lock` change for the stub. The launcher’s runtime code is outside this batch.

- [ ] **3.1a mapping first.** Use `tools/mypy_audit.ini`, explicitly selected from the repo root. Propose `python_version = 3.14`, `show_error_codes = True`, `namespace_packages = True`, `explicit_package_bases = True` and `mypy_path = src` in `[mypy]`. Use normal import following. Carry over the current exact `confusable_homoglyphs` exception if the reached graph needs that same exception. The `[tool.mypy]` section in `pyproject.toml` stays byte-identical. Verify with ambient `MYPYPATH` unset, since the proof should derive its mapping from the new config. Repo-root relative `src` keeps the path portable across Windows and Linux. [Mypy 2.3.1 configuration semantics](https://raw.githubusercontent.com/python/mypy/v2.3.1/docs/source/config_file.rst) · [Current source configuration](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/8008791770e1d96f12a498d158e40c789ed0d94d/pyproject.toml#L123-L133)
- [ ] Use verbose discovery for the mapping-only receipt. Require the same 28 unique roots: the 27 `tools.plan1126_runtime_audit` package modules and `tools.run_plan1126_runtime_audit`. Confirm `src/` imports resolve as first-party and that `tools.concurrency_capture` remains followed. The expected mapping-only result is the source-resolved diagnostic multiset at the same base, including one `jsonschema` import error per mode. Investigate any discrepancy, including loss of a reached module or addition of a new exception, before progressing.
- [ ] **3.1b stubs second.** Propose `types-jsonschema==4.26.0.20261006` in the existing dev extra. The current lock contains `jsonschema==4.26.0`, `mypy==2.3.1` and `referencing==0.37.0`. The published stubs target `jsonschema~=4.26.0`, declare `referencing` in their typeshed metadata and were tested with Mypy 2.3.1. Review PyPI wheel identity and hashes, then require a narrow lock delta covering the dev extra reference and approved stub package. Review any new transitive requirement before release. Keep the runtime versions and unrelated entries fixed. [Pinned PyPI release and checksums](https://pypi.org/project/types-jsonschema/4.26.0.20261006/) · [Typeshed metadata](https://raw.githubusercontent.com/python/typeshed/0b28ac87099d7e3d40612e07ed104ef98143bbe6/stubs/jsonschema/METADATA.toml) · [Current lock](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/8008791770e1d96f12a498d158e40c789ed0d94d/uv.lock)
- [ ] Verify that both scoped modes finish with the same root mapping and the `jsonschema` import error absent. Record any errors newly exposed by the typed validator and assign them to Batch 6 before releasing that batch. Preserve the existing source-only checks and their exact wired commands. Keep mapped-run and stub-run receipts separate. Review the lock and config diffs, then run the existing `test_mypy_gate_wiring` and `test_repository_mypy_exception_ratchet` as scoped tests. [Existing ratchet tests](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/8008791770e1d96f12a498d158e40c789ed0d94d/tests/unit/tools/test_mypy_ratchet.py#L382-L436)

Proposed scoped commands from repository root after a frozen all-extras sync. These are future execution commands under the release gate.

```text
uv sync --locked --all-extras
uv run --frozen --no-sync python -m mypy --config-file tools/mypy_audit.ini tools/plan1126_runtime_audit/ tools/run_plan1126_runtime_audit.py
uv run --frozen --no-sync python -m mypy --config-file tools/mypy_audit.ini --platform win32 tools/plan1126_runtime_audit/ tools/run_plan1126_runtime_audit.py
```

For the before/after diagnostics add `--no-incremental --show-column-numbers --no-color-output`. Add `--verbose` to record the checker’s file/module mapping. Measure the dual-mode entry from WSL and verify the same portable config and root mapping on native Windows before accepting the config.

### 3.2 — Evidence shapes and inventory · 29 / 29

- [ ] Release `model.py` (16), `measurement.py` (6), `evidence_store.py` (2) and `inventory.py` (5) under `tools/plan1126_runtime_audit/`. Resolve the evidence-variant fields, `EnvironmentBinding` vs mapping return, optional evidence identifiers and AST source locations using already validated contracts. Land or accept the shared evidence type decisions before changing consumers. Preserve serialized fields and order, measurement reuse identity, inventory discovery and digest.
- [ ] Run `tests/unit/tools/plan1126_runtime_audit/test_artifact.py`, `test_inventory.py`, `test_measurement_reuse.py` and `test_render.py::test_render_is_deterministic_regeneration_from_canonical_json_and_content_free` in that same test directory, plus the common integrity checks below.

### 3.3 — Shutdown and concurrency capture · 54 / 51

- [ ] Name both files explicitly in the release. `tools/concurrency_capture.py` has 6 / 3 diagnostics and `tools/plan1126_runtime_audit/shutdown.py` has 48 in each mode. Use two substeps under this batch: address Task vs Future and platform-specific typing in the imported helper, then resolve shutdown AST locations, client fixture protocols, typed outcomes and close call signatures. Verify current branching and exception contracts before selecting any typing adjustment. If a fixture’s invocation is actually wrong, record a separate runtime disposition before altering it.
- [ ] Use `tests/unit/support/test_concurrency_diagnostics.py`, `tests/unit/acp/test_plan1126_shutdown.py` and `tests/unit/tools/plan1126_runtime_audit/test_shutdown_diagnostics.py`. Preserve close and cancellation order, deadlines, and recorded stack/context. Capture focused native Windows and WSL results and record platform-specific skips.

### 3.4 — Client, custody and lifecycle probes · 20 / 20

- [ ] Release `clients.py` (5), `serving_custody.py` (5), `session_lease.py` (3), `cancellation.py` (2) and `queue_policy.py` (5) under the audit package. Preserve parser refusals, probe seams and existing client lifecycles. Type already checked input values and injected clients using the evidence shapes from 3.2. Review AST variant and callback typing without altering site selection.
- [ ] Use audit `test_clients.py` and `test_serving_custody.py`, plus `tests/unit/acp/test_plan1126_session_lease.py`, `test_plan1126_cancellation.py` and `test_plan1126_queue_policy.py` in that ACP directory. Verify request recording, terminal outcomes and refusal paths.

### 3.5 — Delivery, telemetry and semantic evidence · 36 / 36

- [ ] Release `delivery_characterization.py` (31), `telemetry.py` (3) and `semantic_errors.py` (2) under the audit package. Handle the delivery fixture’s recorder callables and optional state first, then the telemetry and semantic AST visitor and record variants. Use existing validation or narrow annotations at the already-proven boundary. Preserve redaction, diagnostic classifications and wire dispositions.
- [ ] Use `tests/unit/acp/test_plan1126_delivery_contract.py`, `tests/unit/acp/test_plan1126_semantic_errors.py` and `tests/unit/telemetry/test_plan1126_runtime_contract.py`. Compare emitted audit evidence and renderer bytes under the common checks.

### 3.6 — Launcher and platform dispatch · 13 / 12 after allocation of the stub

- [ ] Release `tools/run_plan1126_runtime_audit.py` only. Resolve command-argument and evidence variant typing, validated object access and the platform-bound subprocess constant. Incorporate any named validator errors newly exposed in 3.1b, after reviewing their exact locations. Preserve CLI status, canonical JSON output, schema validation, input rejection, current vs historical dispatch and sealed replay.
- [ ] Use `tests/unit/tools/plan1126_runtime_audit/test_render.py::test_cli_verify_and_render_use_json_as_authority`, `test_render.py::test_cli_script_runs_directly_from_outside_repository` in the same module, and `test_current_measurement.py::test_the_cli_measures_verifies_renders_and_replays_in_fresh_processes` and its historical verify/render no-probe control. Capture scoped native Windows and WSL evidence for the platform path.

### Common integrity and review gates

- [ ] For each released batch, bind named focused tests, the scoped diagnostic identity comparison in both modes and the pinned re-derivation node to the recorded candidate. Run `tests/unit/tools/plan1126_runtime_audit/test_duplication.py::test_duplication_inventory_is_deterministic_and_reconciles_prior_seeds` on the frozen inventory. Capture exact source, status and bytes during the batch, and retain negative results with their own identities.
- [ ] Run the existing offline `duplication verify` CLI with the accepted JSON inputs. Render the same inputs to a disposable output. Compare generated bytes against a clean pre-batch renderer receipt on the same platform and compare the tracked frozen JSON/Markdown bytes separately. Keep the source pin, digest, inventory count, render ordering and final newline unchanged. Preserve all reports and all historical byte receipts. [CLI options](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/8008791770e1d96f12a498d158e40c789ed0d94d/tools/run_plan1126_runtime_audit.py#L288-L299)

```text
uv run --frozen --no-sync python tools/run_plan1126_runtime_audit.py duplication verify --inventory reports/plan-11-26-duplication-candidates.json --artifact reports/plan-11-26-duplication-audit.json
uv run --frozen --no-sync python tools/run_plan1126_runtime_audit.py duplication render --inventory reports/plan-11-26-duplication-candidates.json --artifact reports/plan-11-26-duplication-audit.json --report <disposable-output>
```

- [ ] Require independent review and owner approval of v2 before releasing 3.1. Release mapping and the named dependency change explicitly. Combine later independent reviews into three checkpoints: 3.1, then 3.2–3.4, then 3.5–3.6 with Task 4 as separately released. Preserve before/after evidence and reviewed scope for each individual batch. Stop for changed behavior, scope drift, unexpected lock edits, missing evidence, artifact mismatch or a typing result that only passes with a new suppression.

## Task 4 — Required audit typing gate and closeout · awaiting release

- [ ] After reviewed Task 3 completion in both platform modes, release the new gate and its wiring test. Planned files are `.github/workflows/guardrails.yml`, `.pre-commit-config.yaml` and `tests/unit/tools/test_mypy_ratchet.py`. Leave the existing `optimus-mypy` hook, source Mypy CI steps and exception ratchet intact. Add a distinct native-mode audit pre-commit hook `optimus-mypy-audit` and two distinct mandatory audit steps in the existing required guardrails job for default and `win32`. Both CI steps use the same config and explicit package and launcher targets. Use `language: system`, `pass_filenames: false` and `always_run: true` for the audit hook so the full audit target is checked even for indirectly related changes.
- [ ] Extend the wiring assertions alongside the existing stable ratchet test node. Have them assert exact scope, configs, both platform modes in CI and no change to source-hook wiring. Demonstrate that deliberately missing audit targets or the Win32 step fail that check in a disposable fixture. Capture a successful normal local audit hook and both zero-error scoped commands in the locked environment.
- [ ] Obtain separate authorization for commit, publication and merge. Verify the normal required PR checks and actual-merge CI on the accepted tree. Capture both zero-error audit results, the existing source gates, reviewed diagnostic and artifact receipts, and the locked configuration identity. Record the required check names and the source-bound closure record before closing #331.
- [ ] Obtain owner approval for terminal plan filing and #315 closure after #331 acceptance. When separately authorized, file this complete successor under `docs/superpowers/plans/hardening-audit-tool-integrity-and-typing-implementation_v2.md`, preserve v1 byte-for-byte in its flat archive if moving it, and reconcile the masterplan pointer, plan status, README and relevant hygiene tests. Keep issue custody in GitHub. [Current v1 filing and closeout rules](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/8008791770e1d96f12a498d158e40c789ed0d94d/docs/superpowers/plans/hardening-audit-tool-integrity-and-typing-implementation.md#L77-L91)
