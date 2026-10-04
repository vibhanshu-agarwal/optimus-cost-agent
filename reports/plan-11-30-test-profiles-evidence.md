# Plan 11.30 test profiles — evidence report

**Plan:** `docs/superpowers/plans/2026-10-04-plan-11-30-test-profiles-implementation_v4.md` (approved working bytes SHA-256 `8A40DEF6D627EDC722D9FA925BBB0C193DE433ECCB91D2DCA19F1DA6AFC5C790`; LF-normalised blob `7D07ADA39CE1F8987E529C7FD8838952B4607F6F2CBD8773D39220D44DB6AF1E`, differing only by CRLF on lines 32–33).
**Machine-readable index:** [`plan-11-30-test-profiles-manifest.json`](plan-11-30-test-profiles-manifest.json).
**Status:** Task 0 complete pending Checkpoint A (Fable 5.1, then Codex). Every result here is provisional development evidence bound to the stated source identity. The final full-run confirmation of the overhead fix belongs to the first delivery's Task 6. Tasks 1–6 are not started.

This report is the plan's single evidence report. Each later stage appends its own sections and never relabels an earlier one.

## Task 0 — Windows overhead, registry pollution and archival design

### Source, environment and identities

| Item | Value |
|---|---|
| Implementation lane | worktree `C:\worktrees\optimus-cost-agent-worktrees\optimus-cost-agent-wt-claude-p1130`, branch `agent/claude/plan-11-30-test-profiles` |
| Base | `main` `a929aab2092876ab0d83ecc4e46896ae3a0935c0` (unchanged at fetch, 2026-10-04) |
| Pre-fix source | base + intake documentation diff SHA-256 `8bc1c6f984bcccd93df5a97ab255aa59de744999012168f22681630d2fc9a53b` (docs index and backlog only) |
| Post-fix source (first attempt) | base + diff `bd5dabc87546367b898accdc6d9fd88afd57e08921a4c45f61c55e0f37a7af0e` |
| Post-fix source (fix-check runs) | base + diff `8ac5f80f454ef1fd1367011a2324175f9c7612b9884b813495044469e644ccbc` |
| Checkpoint A amended source | recorder code (`tools/testing/run_context.py`, `run_context_records.py`) byte-identical to the fix-check source; after Fable 5.1's review only the lifecycle test file, the maintenance tool and its tests, and these reports changed. Per-file SHA-256 in the manifest |
| Windows | Windows 11 Pro 10.0.26300; Python 3.14.4; pytest 9.1.1; coverage 7.14.3; pytest-cov 7.1.0; uv 0.11.29; Git 2.56.0.windows.1; `pyproject.toml` `9fee0c4c…`, `uv.lock` `f1caae18…`; frozen env from `uv sync --frozen --extra dev` |
| WSL | Ubuntu-24.04, kernel 6.18.40.1-microsoft-standard-WSL2, Python 3.14.6, uv 0.11.31; separate native clone and frozen env |
| pytest-xdist | not installed; version and compatibility are selected in Task 5 (no install is authorised by Task 0) |
| Host security product | Bitdefender Antivirus active; Microsoft Defender passive (`AMRunningMode: Not running`) |

### Provenance inputs (v4 Task 0 item 1)

External research is archival provenance, not a dependency. Each input below was hashed at Task 0 against its v4 pin. Only the qualification shown applies.

| Input | SHA-256 at Task 0 | v4 pin | Original verdict / limitation |
|---|---|---|---|
| Claude research report, corrected §13 / §13.4 | `f991c06a7ae51a30a10cfa1cefd7e7d472a012e303fed379028b45e384c6d9de` | `F991C06A…` match | Windows overhead cause **unknown**; append/antivirus attribution withdrawn. Its Linux-flat observation (2–4 ms CI gaps) is a research observation from retained CI logs, not re-measured here |
| Fable review of the research | `dc97731b7997c14d97adc51847f3cb7d6e6b8dc3b647e44447011f220bc6e3da` | `DC97731B…` match | SOUND WITH AMENDMENTS against the original research version |
| Claude review of the v1 draft | `8fea78cf6d4167ad5689d99195eb45ceb6dc65e48a80d3b26c7a25fffe2f3242` | `8FEA78CF…` match | NOT READY, 7 MAJOR / 6 MINOR |
| Claude re-review of v2 | `797fd9d04184e4fc9ea9136ec0ab9f4520fe1d5dc151d547f008aa2395dc0ef9` | `797FD9D0…` match | SOUND WITH AMENDMENTS, 2 MAJOR / 5 MINOR |
| Claude concurrence on v3 | `dff868d0b255838f49ee5c03c351b75ebf0b88dc085e965c8dddf823f080d2f4` | `DFF868D0…` match | Agreement on reuse, CI grant and staged route |
| New-chat handoff, 2026-10-04 | `b1cafa8914bc79b5762f87f4c5fc4c7691c750344dc38d140b700b62d8990dbd`, reverified by Codex at its original authoring output path (Checkpoint A review) | `B1CAFA89…` match | No copy exists in the shared handoff folder. Not relied on for any Task 0 claim |
| Retained research data `tier-runs-95505c4.txt` | `dafb7e4102b9934188e825514d68e2bd8b9539f2cc393cc565c03a2760bc154a` | named in v4 | Derived table; used only for the transition-kind breakdown below |
| `refrun-analysis.txt`, `tier-sizing.txt`, `win-vs-linux.txt`, `import-map.txt` | `83844b33…`, `76d21891…`, `415514e2…`, `b4f11a9a…` | named in v4 | Older `e9d6be0`/shared-machine data; not used for any Task 0 claim |
| Plan 11.28 acceptance-3 reference run `20261003T104058-46816-ca116c` (`95505c4`) | `run.json` `5e122943e134d19050520e8c24b74b15f5a92294892d17e554813d371348be4d`; `phases.jsonl` `82c71adc992c23f90918e894c10cb8c30b6e6e056cba976975f4b8b8b586c645` | named in v4 | ACTIVE, COMPLETE, exit 0, parent UNKNOWN (`registry_partial`). Used only to show the growth is equal in all three transition kinds |
| Older reference run `20261002T203101-45752-c1999b` | `run.json` `c358780a5fdf5af5f270c51a6b18b8dc91c2c02bf94f053be77adb8ca3f26e49` | named in v4 | Exit 1, completeness **INVALID**; not used |

### Prerequisite dispositions

| Prerequisite (v4) | Disposition at Task 0 |
|---|---|
| Merged 11.28 + shared guidance; clean current main | Satisfied: `a929aab` |
| Cause of Windows overhead and regression fixture | Established and fixed (below); full-run confirmation is Task 6 |
| Context Engine / `optimus_model_policy` on main | Absent on `a929aab` (`src/` holds `optimus`, `optimus_gateway`, `optimus_security`, `evidence_handoff`, `evidence_handoff_runtime`): N/A on this source, never a gate result |
| Registry inventory and housekeeping mechanism | Inventory taken read-only; mechanism built; host archival awaits an exact class grant |
| Tooling versions / xdist | Recorded above; xdist UNKNOWN until Task 5 |
| Real WSL, independent env | Available and used |
| Historical binding objects for bound audits | `tests/plan1126_unrun_binding.json` present; bound-audit claims are outside Task 0 |
| Fable 5.1 and Codex reviewers | Operator schedules; not messaged by the implementer |
| Paid calls / services | None used |

### Inventory

- Default selection on the base: 5,184 collected, 111 deselected by the default marker expression.
- Temporary core node list `tmp/plan-11-30-core-nodeids.txt` (ignored, SHA-256 `062320611a0c6a003ae51a02ff767001de504fca3f020d4333906924d05dcdc7`): 3,821 node IDs, the default selection minus the research tier exclusions (run-context/process-tree, the Plan 11.26 audit family, the five proc-heavy gate files, `tests/e2e`, the MAIN-5 guard). Passed as `@file`; `-m` unchanged, so every run is ACTIVE unless `--test-run-context=passive` is given.
- Child launch-site map `tests/unit/tools/run_context_child_sites.json`: 78 sites in 30 files after this task (one site added, below).

### Reproduction and discrimination (pre-fix)

All runs serial, same frozen environment, identical node-list bytes, one coverage writer. Gap predicate exactly as v4 §6 (`gap_i = next.at - (prev.at + prev.seconds)` in recorded order; first and last `k = floor(N/10)` transitions; ordinary medians; `last <= 2 x first`; UNKNOWN for `N < 10` or a non-positive first median; negative gaps reported, never clamped).

| Run | Mode | Coverage | Wall | Phase sum | Gap sum | N / k | First / last median | Ratio | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| `20261004T103059-24588-6332c9` | ACTIVE | on | 628 s | 203.5 s | 403.0 s | 11443 / 1144 | 7.0 / 58.0 ms | 8.29 | FAIL (reproduces) |
| `20261004T104215-55844-00df20` | ACTIVE | off | 647 s | 207.0 s | 423.7 s | 11443 / 1144 | 7.0 / 65.0 ms | 9.29 | FAIL (reproduces) |
| `20261004T105330-42060-4ddeb5` | PASSIVE | on | 675 s | 204.9 s | 449.5 s | 11443 / 1144 | 7.0 / 60.0 ms | 8.57 | FAIL (reproduces) |
| `20261004T110548-20320-f3b48f` | ACTIVE, instrumented | on | 651 s | 212.8 s | 421.5 s | 11443 / 1144 | 7.0 / 61.0 ms | 8.71 | FAIL (reproduces) |

Every run: exit 1 from one unrelated documentation failure (below), 3,782 passed, 38 skipped, records COMPLETE, 11,444 phases. Precision of these records: 1 ms. Every run's parent is UNKNOWN (`registry_partial`): the host registry holds more than the 512 entries a run reads, so every sample reports `registry: partial`. No ancestry or overlap claim is made from these runs.

**Host load.** The runs' own samples list the other registered runs alive at each phase boundary. Pre-fix runs r1–r3 list no live foreign run; the only listings are stale roots whose process query failed (`unknown`). That is an observation with the partial-registry limit: a run reads at most 512 registry entries, so it cannot establish that no foreign load existed. **Every post-fix run (r5–r8) overlapped, in every sample, a live default run from another lane** (`20261004T114222-51636-016cc7`, worktree `wt-claude-plan12-cp4`, relation `outside`). **The post-fix ratios satisfy the predicate under an identified overlapping lane. Host load was neither matched nor completely observable, so no conservative-comparison claim and no isolated wall-time speedup claim is made.** Contention, scheduling and cache effects can move both decile medians and their ratio in either direction. (Amended after Codex's Checkpoint A review, C-M2.)

**Instrumentation overhead.** The instrumented run d1 versus the uninstrumented r1 (same mode): wall 651 s vs 623 s to the last phase end, phase sum +9.3 s, gap medians 7.0/61.0 ms vs 7.0/58.0 ms, ratio 8.71 vs 8.29. Instrumentation did not create or hide the growth.

**Discrimination.** Coverage off reproduces as strongly as coverage on, and PASSIVE (no job, no guard) reproduces as strongly as ACTIVE. In these controls, then, neither coverage nor the Plan 11.28 job and guard is a necessary trigger of the growth. That does not establish the absence of every possible interaction with them. Both coverage modes are required fix-check modes.

### Diagnosis

Each step was measured before any harness change.

1. **Where the time goes.** A diagnostic plugin timed every `pytest_runtest_makereport`/`pytest_runtest_logreport` implementation per phase (run `20261004T110548-20320-f3b48f`). The whole growing gap is the root conftest's `pytest_runtest_logreport`, i.e. `run_context.record_phase`: decile medians 6.7 → 60.7 ms. Every other hook stayed below 0.2 ms. GC time, Python threads (1–4), native threads (4–7) and the process handle count (≈300) stayed flat. The retained `95505c4` reference run shows the same growth in all three transition kinds (setup→call, call→teardown, teardown→setup), which fits a per-phase-report cost, not a per-test fixture.
2. **Which part of the recorder.** In-process timings over a 1,500-test prefix: `record_phase` ≈ `append_entries` (5.2 → 25.3 ms). The shared sanitizer, the field table, `sys.audit`, `stat` and `open` stayed flat. `close()` of a separate small probe file grew 3.1 → 9.2 ms in the same process.
3. **Kernel wait, not computation.** A raw `os.close()` after a write grew 2.5 → 16.4 ms with zero thread CPU time, while a read-only open/close stayed at 0.3 ms. No Python hook was involved (`open` is `io.open`; no trace, profile or `sys.monitoring` tool). Over run `…6332c9` the job used 175 s of CPU in 628 s of wall time.
4. **Standalone controls, all flat.** Replaying `append_entries` (≈0.17 ms per close), writing 20,000 distinct files, starting 400 child processes, and 120 rounds of `other_runs` (≈61,000 `OpenProcess` calls) all stayed flat in a fresh process.
5. **The trigger.** Milestone probes (retained, d4) showed `close()` fast through configure, session start and collection, then jumping during the call phase of `tests/integration/evidence/test_mixed_artifact_gate.py::test_mixed_artifact_dispositions`. Bisected in bare processes: certain Pillow PNG encode paths flip the process, after which every later `close()` of a file it wrote costs about 2 ms instead of 0.08 ms.
   - One encode into memory suffices.
   - A single encode straight to a file did not flip it, even 3 s later; a second file encode did.
   - zlib alone, opening or decoding a PNG, and the redaction gate's DACL calls do not flip it.
   - Which step inside Pillow, and which host component, is not established.
6. **The growth.** In a flipped process, open/append/close per entry of one growing stream costs ≈5 → 29 ms over 6,000 entries. A held handle with write + flush per entry costs a flat ≈0.011 ms, with one ≈31 ms close at the end. In an unflipped process, reopen per entry stays at ≈0.2 ms and a held handle at ≈0.013 ms. Whether the cost grows with the number of closes or with file size is not separated by this data. The fix removes the per-phase close either way.

   Steps 4–6 were first measured during diagnosis, and their numbers were transcribed into the implementer's ledger. The probes were then re-run after the Checkpoint A review on the same host, with every output retained (`probes-retained-20261004T124616/` in the receipts). The re-runs reproduce the transcribed values; the figures above are the retained ones. Steps 1–3 and the d4 milestones rest on outputs retained from the original runs.

**Cause.** On this host, once a process has encoded a PNG through Pillow, every `close()` of a file that process wrote blocks in the kernel, and for longer as the run proceeds. This is consistent with an on-access file-system filter; which component is not established, and host security settings are out of scope. The run-context recorder opened, appended to and closed `phases.jsonl` once per test phase, so every inter-phase gap paid one such close. The research's observation that Linux CI gaps stay flat (2–4 ms) fits this, but it was not re-measured here. The cause is in the harness's use of the file system, not in product behaviour.

### Fix (test-first)

- **Held streams.** `run_context_records.append_entries(..., held=...)` opens each stream once per run, lazily, after every in-memory check. Each append is written and flushed to the operating system before the call returns. A failed stream is closed and dropped, and the existing restore-by-truncation, deferred-append and INVALID semantics are unchanged. `run_context` passes its `held` map and closes it before the terminal read-back (a failed close is a recording error) and again in `finish_run`'s `finally`.
  - RED → GREEN: `test_each_stream_is_opened_once_and_held_until_the_run_ends` (60 opens → 1).
  - Kept green: `test_an_append_with_unknown_progress_is_restored_then_retried_or_made_invalid`, with its injection moved from a failing close to a failing flush and its assertions unchanged.
  - Durability control: in the abrupt planted case, the setup phase recorded before the kill is readable.
- **Measurement precision.** `record_phase` now keeps phase `at`/`seconds` to microseconds (same fields, more digits). After the fix, gaps fall below 1 ms, and at 1 ms resolution the coverage-off post-fix run's first-decile median was 0, so §6 returned UNKNOWN. RED → GREEN: `test_phase_times_keep_sub_millisecond_precision`.

### Fix check (post-fix, matched)

Same node-list bytes, flags and frozen environment as the pre-fix runs; both coverage modes reproduced pre-fix, so both are fix-check modes. The fix-check result is provisional until the first delivery's serial full Windows coverage run (Task 6).

| Run | Source | Mode | Coverage | Wall | Gap sum | First / last median | Ratio | Verdict |
|---|---|---|---|---|---|---|---|---|
| `20261004T115442-33504-b8e39c` | `bd5dabc8` | ACTIVE | on | 212 s | 11.3 s | 1.0 / 1.0 ms (1 ms precision; 592 negative gaps) | 1.0 | PASS |
| `20261004T115840-42472-aa79f7` | `bd5dabc8` | ACTIVE | off | 200 s | 11.3 s | 0.0 / 1.0 ms (1 ms precision; 604 negative gaps) | — | UNKNOWN (retained) |
| `20261004T120544-17508-047bbb` | `8ac5f80f` | ACTIVE | on | 209 s | 9.5 s | 0.371 / 0.407 ms (1 µs precision; 0 negative gaps) | 1.10 | **PASS** |
| `20261004T120919-34428-c7ee88` | `8ac5f80f` | ACTIVE | off | 204 s | 9.6 s | 0.350 / 0.409 ms (1 µs precision; 0 negative gaps) | 1.17 | **PASS** |

### Registry pollution and archival

**Amended after the Checkpoint A review (Fable 5.1, Finding 1).** Python resolves its temporary directory from TMPDIR first, then TEMP, then TMP, on every platform. The first isolation set only TEMP/TMP. In an environment that exports TMPDIR (as this host's agent shell sometimes does), every child therefore announced itself in the **real** registry. The environment of the original focused gate was not recorded, so that gate's isolation proof is **withdrawn**; the proofs below replace it.
- RED: with TMPDIR set, a nested child listed real-registry runs and never saw the synthetic marker.
- Fix: the fixture now sets TMPDIR, TEMP and TMP, through its own MonkeyPatch, so a test's `monkeypatch.undo()` cannot end the isolation.
- Each test's synthetic registry carries a **passive marker announcement** that exists nowhere else. The nested-outcome and repeated-session children must list it in their own samples, which positively proves they read the synthetic registry. The abrupt planted case asserts its killed root's entry is in the synthetic registry and absent from the real one.
- The module-level negative-space control can attribute added entries only where validated ancestry exists (Windows). Elsewhere the positive marker checks carry the proof.

- **Leak isolation (lifecycle file).** Every nested, planted and repeated-session child now inherits TEMP/TMP pointing at one test-only temporary root, so it announces itself in a synthetic registry. The outer run's own announcement is copied in, so children still find their parent by validated ancestry. The parent reads and withdraws synthetic entries only inside a `view()` block within one phase. Between phases the outer run keeps sampling the real registry, so its overlap records never report a false empty registry. Job, guard and ancestry behaviour are unchanged.
- **Negative-space control.** A module-scoped fixture in `test_run_context_lifecycle.py` compares real registry names and bytes before and after the file while the outer run is active.
  - Added entries count as this file's only when their recorded parent chain reaches this run.
  - Removing an entry whose root had already ended is never legitimate.
  - Bytes of entries that stayed must not change.
  - Concurrent lanes are neither paused nor suppressed.
  - RED (pre-isolation, `abrupt_exit-venv_launcher`): 4 attributable leaked entries, and the killed planted root's entry was in the real registry. GREEN on Windows: the focused gate passes, and the real registry listing is identical before and after.
  - The RED demonstration itself leaked 4 entries into the host registry (`20261004T114340-17304-8fffcf`, `20261004T114340-3484-beeda6`, `20261004T114342-34364-3d06c4`, `20261004T114342-46164-476c42`; their worktree is present, so they are kept by the inventory).
- **Shared positive-end predicate.** `run_context.process_end_status(pid, creation_time)` returns `(ENDED | LIVE | UNKNOWN, basis)`:
  - Windows: `not_found`, `replaced` (the recorded process ended; the replacement is not touched) and `terminated` are ENDED; a denied or failed query and a missing creation time are UNKNOWN.
  - Elsewhere: `proc_absent` is ENDED, and `proc_present` is UNKNOWN, never identity proof.
  - `other_runs` uses it with one handle per root, as before.
- **Maintenance tool.** `python -m tools.testing.registry_maintenance` provides `inventory` (read-only; one new manifest; refuses a manifest the shared sanitizer would change), `archive` (dry run unless `--execute`; requires the manifest's class digest as the grant) and `verify`.
  - Eligible means a conforming record filed under its own run ID, whose recorded worktree is absent and whose root is ENDED.
  - Moves are link-then-unlink to `registry/ended/` (never an overwrite), with one append-only receipt per entry.
  - Changed bytes, changed status or a conflicting destination are refused and kept.
  - Interrupted moves are reconciled from disk.
  - Controls cover LIVE, UNKNOWN, access failure, PID reuse, replaced bytes, destination conflict, interrupted move and receipt, idempotent re-run and verify mismatches.
- **Host inventory (read-only; registry bytes identical before and after).** 732 entries, 724 eligible (701 `not_found`, 23 `replaced`), class digest `28bc1799eebba5f132996b366ee255ca0ccaf85f0a332df4e26316343009134a`.
  - Eligible origins: removed worktrees `wt-claude-runctx` (656), `ptc-int` (30), `ptc-va` (20) and `ptc-vb` (10), plus 8 children dated 2026-10-02 whose worktree was a pytest temp folder of `test_git_env_immunity` (older reason vocabulary; today's runs added none).
  - Kept: 3 UNKNOWN, 4 with a present worktree, and 1 LIVE run in another lane.
  - **No host entry was moved.** Archival needs the operator's grant naming this class digest.

### Verification

| Gate | Platform | Result |
|---|---|---|
| v4 Task 0 focused verify + maintenance gate + cross-cutting guards (logging-surface inventory, child-site map, walker review), final source | Windows | 361 passed, 1 skipped (POSIX-only), 124 s |
| Same, first post-fix source `bd5dabc8` | WSL attempt 3 | 313 passed, 48 skipped (Windows-native), exit 0; clone diff equals the Windows candidate |
| Same, final source `8ac5f80f` | WSL | 314 passed, 48 skipped (Windows-native), exit 0; all 9 changed files byte-identical to Windows (per-file SHA-256 in the manifest; the `git diff` stream hash differs only by git-version formatting) |
| Ruff on changed Python | Windows | clean |
| Focused gate after the Checkpoint A amendments, `TMPDIR` set to the real temp folder | Windows | 363 passed, 1 skipped; registry names unchanged except one foreign `plan12-cp4` run arriving (attributed by its worktree) |
| Same, `TMPDIR` unset | Windows | 363 passed, 1 skipped; real registry names unchanged |
| Same, `TMPDIR=/tmp` and `TMPDIR` unset | WSL (`wsl-final2-a1`) | 316 passed, 48 skipped each, exit 0; all changed files byte-identical to Windows |
| Focused gate after Codex's C-M1 correction and intake import, `TMPDIR` set / unset | Windows (gate5) | 378 passed, 1 skipped in each; registry changes during both runs were only `plan12-cp4` and `ghissues` lane runs arriving and withdrawing |
| Same, `TMPDIR=/tmp` / unset | WSL (`wsl-final3-a1`) | 331 passed, 48 skipped in each, exit 0. Every changed file is byte-identical to Windows except the backlog: Windows keeps Codex's two CRLF bytes in the working copy; the WSL clone holds Git's LF-normalised form, which is what any commit stores |
| Docs gate, imported intake (`tests/unit/docs`) | Windows | 84 passed with the intake plan files untracked. With them visible: 83 passed, 1 failed (the kickoff's link to the gitignored reviewer log; returned to Codex) |

### Failed, invalid and UNKNOWN outcomes (retained)

- Every core run exits 1 on `tests/unit/docs/test_open_work_pool_hygiene.py::test_priority_is_authored_only_in_table_cells`. The intake backlog edit (Codex-authored, uncommitted) contains `Priority:` outside a table cell. It is unrelated to timing and left for Codex.
- WSL attempt 1: 3 failed (the clone did not mirror the intent-to-add index). Attempt 2: 6 failed (`git apply --intent-to-add` replaced the clone index). Both are harness errors, retained; attempt 3 passed.
- Post-fix coverage-off run at 1 ms precision: UNKNOWN (above).
- The isolation RED leaked 4 host entries (above).
- The TMPDIR RED (Checkpoint A amendment) ran only the normal nested case. Its child announced and withdrew in the real registry, leaving nothing.
- The first post-amendment gate failed the logging-surface inventory: the new unreadable-receipt message exported exception text. Fixed by building the message from the line number; the next gate passed.

### Residuals and owners

- The host's per-process close cost still applies to files that tests themselves write after the Pillow trigger, inside their own phases. Phase sum fell 203.5 → 181.3 s rather than staying flat. Diagnosing or isolating the trigger test is outside Task 0. Owner: `P11-FEAT-TEST-PROFILES` (custody pending Codex).
- At microsecond precision the §6 predicate's absolute medians are small. A future full run whose first-decile median reaches 0 µs would be UNKNOWN by contract.
- Plan 11.28 activation, cleanup and branch-folding holds are unchanged.
- `tests/unit/tools/test_run_context_boundaries.py` still plants two malformed/misfiled entries in the real registry and announces one nested run there. This is by ruling: it is `try/finally`-cleaned and proves live ancestry against the real outer run. A run interrupted inside that window would leave `zzz-*` entries the maintenance tool keeps forever. Owner: `P11-FEAT-TEST-PROFILES` (custody pending Codex).
- The host registry exceeds 512 entries, so every run's parent is UNKNOWN (`registry_partial`) until an authorised archival reduces it.

### Raw receipts

Archival provenance, not a project dependency: `optimus-handoff\test-profiles-research\plan-11-30-task0-evidence-20261004\` (first seal: 161 files, `SHA256SUMS.txt` SHA-256 `5dc4c91b1170588ed16a550dfb5a526f25c40f643198353839457d3f4ecbd0d5`; after the Checkpoint A amendments: 208 files, `SHA256SUMS-v2.txt` SHA-256 `4703c118459dc0dad663f8b89cfb056598800a8ac18b86ee76cf5e64f5fea32a`, with v1 left unchanged and still verifying; after Codex's corrections: 223 files, `SHA256SUMS-v3.txt` SHA-256 `885933c55dd32de3e30989ffa261c192d4217ddcbbb8fddf2a6269d1906c0cca`, with v1 and v2 still verifying). It holds every run's `meta.txt`, console output and run-context record, the diagnostic plugin outputs, the WSL attempts, the host registry inventory and the diagnostic scripts and node lists. The manifest names each run's record digests.

### Checkpoint A review — Fable 5.1 (2026-10-04)

Verdict: **SOUND WITH AMENDMENTS**, 3 MAJOR / 8 MINOR. Fable independently re-derived every §6 verdict from the raw records and confirmed the following:
- the diagnosis chain (steps 1–3);
- the fix code and failure semantics;
- `other_runs` equivalence with the base;
- the maintenance tool's safety;
- the host inventory;
- all repository gates.

| Finding | Disposition |
|---|---|
| 1 MAJOR: TMPDIR defeats registry isolation | Fixed (RED → GREEN); positive marker proofs added; proven under TMPDIR set and unset on Windows and WSL; original gate's isolation proof withdrawn |
| 2 MAJOR: diagnosis steps 4–6 lacked retained outputs | Probes re-run with outputs retained and hashed; wording corrected (trigger path; Linux observation softened) |
| 3 MAJOR: provenance hashes not filed | Provenance table added above; the handoff pin was later reverified by Codex at its original authoring path |
| 4 MINOR: parent UNKNOWN / registry partial not surfaced | Stated above and per run in the manifest |
| 5 MINOR: no held-close terminal failure control | Added `test_a_held_stream_that_cannot_be_closed_makes_the_record_invalid` (a coverage control: the behaviour already existed, so it passed on first run) |
| 6 MINOR: scratch contexts keep held handles | Autouse finalizer closes every scratch context's held streams |
| 7 MINOR: `monkeypatch.undo()` could end isolation | Fixture uses its own MonkeyPatch |
| 8 MINOR: damaged receipt file raised a traceback | RED → GREEN: `ReceiptsUnreadable` → named `EXIT_MISMATCH`, nothing moved (`test_a_damaged_receipt_file_is_a_named_mismatch_never_a_crash`) |
| 9 MINOR: boundaries file still plants in the real registry | Recorded as a residual with owner (above) |
| 10 MINOR: instrumentation overhead not stated | Stated above |
| 11 MINOR (Codex-owned): intake backlog text stale | For Codex's intake-doc release and freshness audit |

### Checkpoint A review — Codex (2026-10-04)

Verdict: **HOLD for bounded corrections**. Codex independently verified both receipt seals and the per-file hashes, and recomputed the post-fix ratios (1.096 and 1.169). No new full suite or repeated diagnosis was requested.

| Finding | Disposition |
|---|---|
| C-M1: maintenance accepted a schema-valid but wrong receipt (wrong digest, class, paths, `LIVE`) as proof in `verify` and as `already_archived` in `archive` | Fixed test-first (14 RED → GREEN). A receipt now counts only if it is exactly the receipt the tool writes for that entry under that grant: exact field set; same name, digest, run ID, source, target, end basis and class digest; positive ENDED status; `archived`/`reconciled` disposition; well-formed UTC time. `archive` idempotency and `verify` share that match. Duplicates, mismatches, a receipt of this class that names no eligible entry, and a valid receipt without its archived copy are each named nonzero outcomes, and nothing unrelated moves. Interrupted-move reconciliation, idempotent replay and other grants' receipt history still pass. |
| C-M2: the host-load qualification overclaimed | Wording replaced (Host load and Discrimination paragraphs above). |
| Intake corrections (Codex) | Imported byte-identically into this lane: `.gitattributes` `-text` rules for v4 (filtered blob equals raw blob `3cef47af7a65010391d583b22cffa393959600ac`), corrected backlog and docs index, and the review itself. v4, the archives and the kickoff are unchanged. |
| Docs gate on the imported intake | Untracked intake files: 84 passed. With the intake files visible to index-scoped gates: one failure, `test_relative_markdown_links_resolve_except_registered_stale_links`. The kickoff links to the gitignored reviewer log `plan-11-30-review-checkpoints.md`, which exists only in the drafting checkout. This is Codex's file, so it is returned to Codex. |

### Checkpoint A follow-up — Codex E1 re-check (2026-10-04)

Codex confirmed the forged-receipt correction and reproduced two remaining receipt defects. Both are now fixed test-first, and the whole class was enumerated rather than only the two reported values.

| Defect | Fix and controls |
|---|---|
| `disposition=[]` raised `TypeError` instead of a named refusal | **The receipt file's structure is validated as a whole.** Every line must be a JSON object with exactly the receipt fields, the receipt schema, and **text values only**; otherwise the file is untrusted. `verify` returns `receipts unreadable at line N`; `archive` refuses with nothing moved. Controls (42 RED → GREEN): list, dict, integer and null values in each of the ten receipt fields, an extra field, a missing field, and Codex's exact `disposition=[]`. The enumeration also found a non-text `name`: such a receipt cannot be attributed to an entry, and would otherwise have let the entry be reconciled while a damaged receipt sat in the file. |
| `utc="2026-99-99T99:99:99+00:00"` passed `verify` and idempotency | **A receipt time must be ASCII, in the tool's own form, parse as a real datetime, and carry a zero UTC offset.** Controls (3 RED → GREEN, plus 5 shape cases): Codex's exact value, other impossible fields and days, full-width digits, a non-UTC offset, a space separator, a `Z` suffix and seven fraction digits. The tool's own microsecond times still verify. |

Semantic mismatches (wrong digest, run, paths, end basis, class, status, disposition or time) remain per-entry named mismatches. The structural rule moved the earlier "extra field" and "missing field" cases into the structural test, where they are now reported as unreadable lines.

**Intake documents re-imported** from Codex's corrections, byte-identically: `.gitattributes` (`-text whitespace=cr-at-eol` for v4), the docs index, the decision-log README (source S3, export SHA-256 `3ddd90f7…`, independently re-hashed), the backlog, ADR-016 (unpublished draft), the Codex review, and the kickoff. The kickoff changed from its intake pin `AC182523…` to `34cb257c…`: the reviewer-log reference is now plain text, not a link. v4 and its archives are unchanged; v4's Git blob still equals its raw bytes (`3cef47af…`).

| Gate | Platform | Result |
|---|---|---|
| Docs gate, every intake file visible to index-scoped tests | Windows | 84 passed |
| `git diff --check`, whole tree | Windows | clean |
| Local secret scan, every changed file (including the plan files and ADR-016) | Windows | 0 findings |
| Focused gate, `TMPDIR` set / unset (gate6) | Windows | 428 passed, 1 skipped in each; real registry listing unchanged |
| Same, `TMPDIR=/tmp` / unset (`wsl-final4-a1`) | WSL | 381 passed, 48 skipped in each, exit 0 |

**Retained harness error.** One edit of `tests/unit/tools/test_registry_maintenance.py` was written with CRLF line endings on Windows (Python `write_text`). The WSL byte comparison caught it (433 CR bytes; a commit would have stored LF). The file was normalised to LF and re-tested (86 passed, 1 skipped). The Windows gate6 ran the CRLF copy, which is content-identical to Python. Every other changed file is byte-identical between Windows and WSL; v4 keeps its two approved CRLF lines on both.

**Returned to Codex (ADR-016 draft, line 48):** the predicate row says "Windows identity evidence is weaker than Linux". It is the reverse: Windows checks PID plus creation time through a process handle, while POSIX has only `/proc/<pid>` presence, which v4 §2 calls the weaker capability.

### Checkpoint A accepted; local release (2026-10-04)

Codex accepted Checkpoint A at 15:04:45 UTC (`docs/superpowers/reviews/2026-10-04-plan-11-30-checkpoint-a-codex-review.md`). It released:
- the local intake commit and the local Task 0 commit, with `SKIP=optimus-pytest-coverage` for those two commits only;
- archival of the reviewed 724-entry class `28bc1799eebba5f132996b366ee255ca0ccaf85f0a332df4e26316343009134a`, only if a fresh inventory and dry run still match it;
- Task 1 after local delivery.

Push, PR, merge, service activation and paid calls stay held.

**Final documentation delta imported byte-identically:** the docs index, the decision-log README, the backlog, ADR-016 and the Codex review. Pins re-verified: v4 raw `8A40DEF6…`, staged and committed blob `3cef47af…`; predecessors v1 `E267774C…`, v2 `128E4FED…`, v3 `791E79E2…`, matching v4's own pins.

| Check | Result |
|---|---|
| Docs gate, intake visible (before the intake commit) | 84 passed |
| `ruff check .` | clean |
| `git diff HEAD --check` | clean |
| Local secret scan, every changed file | 1 finding, in this manifest (retained harness error below); 0 after the fix |
| Intake commit `e3fe91f` hooks | trailing whitespace, file size, Ruff, Bandit, ast-grep, config-trust scan and secret scan passed; YAML/TOML had no files; coverage hook skipped as released |
| Lane files after the hook's stash and restore | byte-identical to the pre-commit backup (20 files) |
| Docs gate after the intake commit | **1 failed, 83 passed** (below) |

**Docs gate failure after the intake commit (returned to Codex).** `test_post_amendment_plans_declare_prerequisites_with_required_columns` checks plans added in commits since the prerequisites amendment (`087560a8`). It could not see v4 until v4 was committed, so every earlier docs gate passed. v4's Tooling prerequisite row gives the disposition "early check distinguishes genuinely absent from merely unauthorized". The check requires a disposition that *starts with* "genuinely hard", "genuinely absent" or "merely unauthorized". v4 is byte-frozen, so this cannot be corrected in the implementation lane. Task 0 touches neither v4 nor the check.

**Retained harness error (secret scan).** The E1 follow-up recorded "0 findings", but that scan ran before the follow-up's verification block was added to this manifest. The block's key `secret_scan` trips the scanner's Secret Keyword detector, so Codex's accepted manifest snapshot (`09E90764…`) contained one finding that the commit hook would have refused. This refresh renames the key; nothing else in that snapshot changes.

**Registry archival: STOPPED, nothing moved.** The fresh read-only inventory (15:12:48 UTC; registry listing identical before and after) has 789 entries, 724 of them eligible. Its class digest is `57a4afe0ce9867b23a3d422e87195d7044e023e38e0a1fb61803fcf2e280c98e`, not the granted `28bc1799…`. The read-only delta:
- 722 reviewed entries are still eligible, with identical names and bytes.
- 2 left the class (`20261003T082415-47540-ade221`, `20261003T172719-54948-9e6cbf`). Their recorded root PIDs are now held by processes this account cannot query, so their end status is UNKNOWN (`query_failed`). That is the conservative result.
- 2 joined (`20261002T161642-50540-15569b`, `20261002T191731-50540-19494d`). They were UNKNOWN (`query_failed`) at review time and are now `not_found`.
- 13 stayed eligible with a different ENDED basis (7 `not_found` → `replaced`, 6 `replaced` → `not_found`): PID reuse.
- 58 new names, all with a present worktree (`ghissues` 46, `plan12-cp4` 11, `mut-t4b` 1), so none is eligible. The LIVE `plan12-cp4` run seen at review time has gone.
- A read-only dry run of the reviewed manifest would archive 722 entries and refuse the 2 now-UNKNOWN entries (`changed_since_inventory:root_unknown`, exit 3). The registry was unchanged, and no `ended/` folder exists.

The release says a changed class stops execution, and the fresh manifest goes back to Codex. Receipts are in `codex-release-archival/` under the raw receipts folder.
