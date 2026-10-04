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

## Task 1 — Classification and additive plugin (2026-10-04)

**Status: complete, uncommitted** (base `d562e95`; a commit waits for Codex's answer on Task 1–2 commits). Receipts: `optimus-handoff/test-profiles-research/plan-11-30-task1-evidence-20261004/`.

### What was built

| File | Responsibility |
|---|---|
| `tests/profiles.toml` | The one manifest: 18 tier rules, 3 tag rules and a measured-slow snapshot (164 nodes) |
| `tools/testing/test_profiles.py` | Pure contract: `load_manifest`, `classify_nodes`, `profile_members`, `unexplained_slow_nodes`, and the two maintained signals |
| `tests/support/profiles_plugin.py` | `--profile`: after every other deselection, it deselects through `pytest_deselected` and prints one `test-profiles:` line |
| `tests/conftest.py` | Registers the plugin. The UNRUN count is now taken from the final items. |
| `tests/unit/tools/test_test_profiles.py` | 55 nodes: the pure contract, the plugin controls and the repository guards |
| `tests/unit/tools/run_context_child_sites.json` | One new `nested_pytest` launch site |

**Precedence.** The longest matching node rule decides. Otherwise the single matching path rule decides; otherwise the node is `core`.
- Two path rules claiming one file are a conflict.
- A rule that decides no node fails the full-universe guard.
- Static profiles: `full` (identity), `core`, `proc`, `audit`, `platform`, `concurrency`.
- `quick`, `commit` and `checkpoint` arrive with the Task 2 selector.
- The effective `-m` is never touched, so run-context ACTIVE/PASSIVE classification is unchanged.

### Classification of the default selection (5,329 nodes)

| Tier | Nodes | Source of the rules |
|---|---|---|
| core | 3,999 | Default, plus reviewed explicit rules for 7 measured-slow in-process tests and the cheap remainder of the audit family |
| proc | 835 | Run-context/process-tree files, child-launching tool files, subprocess-heavy nodes |
| gates | 325 | Current-source guards (S1 and Zed closures, logging manifest, walker allowlist, debug-trace, boundaries, credit surface, docs hygiene, UNRUN binding, this manifest's own guards) |
| audit-sealed | 90 | Pinned-commit or sealed-artifact replay |
| audit-current | 67 | Current-tree measurement or current-source reads |
| e2e-local | 12 | Unmarked `tests/e2e/**` |

Tags: `platform` 1,488 nodes (28 signal files), `concurrency` 381 nodes (9 signal files plus 4 reviewed product-race files).

**Source of the audit/gates split.** A per-node survey of the audit family (357 nodes) and the proc candidates (504 nodes), plus a repository-wide search for current-source guards (278 nodes in 50 files). Each row carries file:line evidence. The survey was parsed mechanically: 0 node-count or target mismatches against the real collection. Its 16 ambiguities were ruled in the ledger: the proposed tier stands in each case, and A11 (unrun-binding guards) is `gates`.

### Controls (test-first)

- **Pure contract.** RED (module missing), then 37 passed. 5/5 classifier mutants were killed: prefix boundary, shortest-wins, no conflict check, shadowed rule counted, audit as one tier.
- **Plugin controls.** 9 RED (no option, no manifest, no final-items UNRUN), then GREEN. They cover:
  - no-profile output byte-identical with the plugin blocked (MAIN-5 argument shape);
  - honest deselected counts;
  - composition with `-k` and explicit targets;
  - single-file sessions;
  - unknown or change-selected profile names as usage errors;
  - unchanged ACTIVE/PASSIVE classification (active default, `-m` passive, requested passive);
  - UNRUN counted from the final items.
- **Repository guards** (whole default selection):
  - no dead rule;
  - every measured-slow node has an explicit rule;
  - run-context/process-tree files are `proc` except current-source gate nodes;
  - `tests/e2e/**` is `e2e-local`;
  - concurrency and platform tags follow their maintained signals;
  - every child-launching file with `core` nodes has a written review (17 files);
  - v4's named current-source guards are `gates` or `audit-current`.
- **9/9 manifest mutants killed.** The first pass found a real defect: the manifest generator kept the measured-seconds column, so every snapshot entry matched no node, and the duration guard was vacuous. The guard now requires every snapshot entry to be a collected node ID (RED 164, then GREEN after the generator fix).

### Verification

| Check | Platform | Result |
|---|---|---|
| Task 1 gate command + cross-cutting guards, `TMPDIR` set / unset | Windows | 629 passed, 2 skipped in each |
| Same, `TMPDIR=/tmp` / unset (native clone at `d562e95` + Task 1 diff) | WSL | 580 passed, 51 skipped in each |
| Changed files Windows vs WSL | both | 6/6 byte-identical, no CR bytes |
| No-profile collection, plugin vs plugin blocked | Windows | identical (5,329/5,440, 111 deselected by `-m`) |
| Default collection vs the pre-Task-1 baseline | Windows | +55 nodes, all in `test_test_profiles.py`; nothing removed |
| Each static profile through the plugin vs the classifier | Windows | identical for full, core, proc, audit, platform and concurrency |
| `ruff check .`, `git diff HEAD --check`, local secret scan of changed files | Windows | clean, clean, 0 findings |

The real registry listing changed during the Windows runs only through another lane's runs (`mut-t4b`); no run of this lane remained.

### Residuals and limits

- **The selection record is deferred to Task 2**, because it carries the base/head/index/diff. In Task 1 a profile's deselection is visible in run-context's node stream, pytest's deselected count and the `test-profiles:` line.
- **The measured-slow snapshot comes from the 2026-10-02 reference run.** Tests added since then are unmeasured until Task 6 refreshes the snapshot. Stale snapshot entries fail the guard.
- **Tags and launcher reviews are file-level.** The `platform` tag selects every node of a file that reads the platform.
- **The tier survey is a reviewed snapshot.** New tests default to `core` unless a maintained-signal, launcher, slow-node or named-guard check catches them. A new current-source guard outside the named categories is caught only by review.

## Task 2 — Per-commit selector, bounded broad fallback and supported-load checkpoint runner (2026-10-04)

**Status: complete, uncommitted.** Base `d562e95`; Task 1 lies beneath it. Receipts: `optimus-handoff/test-profiles-research/plan-11-30-task2-evidence-20261004/`.

### What was built

| File | Responsibility |
|---|---|
| `tools/testing/test_profiles.py` | Adds the pure selector: `parse_name_status`, `build_dependency_map`, `select_tests`, plus the `[selection]` and `[[inputs]]` manifest sections |
| `tools/testing/run_profile.py` | `python -m tools.testing.run_profile --profile commit\|checkpoint\|quick [--base SHA] [--exact] [--dry-run]`: Git change views, selection record, supervised subruns, Windows load-overlap repeats, evidence manifest |
| `tests/profiles.toml` | Broad paths, docs gates and three declared inputs (sealed Plan 11.26 data → audit-sealed; `tools/testing/**`, the process tree and `tests/support/child_*` → run-context proc tests; `src/optimus/**` → the e2e tests' dynamic launch of the ACP server) |
| `tests/unit/tools/test_test_profile_selection.py`, `tests/unit/tools/test_run_profile.py` | Selector controls over a synthetic repository; runner controls with temporary Git repositories and real nested sessions |

### Selection contract (as built)

- **Views.**
  - `commit` is the index against HEAD. Unstaged divergence is selected and hashed as provisional.
  - `checkpoint` is the recorded base against the working tree, plus untracked files. Everything not yet committed is provisional.
  - `--exact` refuses any provisional divergence.
  - An empty index is `no-commit-input` and runs nothing; it is never a pass.
  - Git is read with the caller's environment, so inside a hook the selection follows the hook's `GIT_INDEX_FILE`.
- **Dependencies.**
  - Import edges are keyed by module name. They cover packages, relative imports and string imports, including `-m` launches.
  - A deleted or renamed module still finds its importers by its old name.
  - Data references (a tracked file, or a folder without Python code) propagate through importers. Only the changed path's own readers count; the importers of those readers then carry the change further.
  - Naming a folder of code (`ROOT / "src"`, `"tests/unit"`) scans or runs it. The reading test is selected, but it never makes a change count as mapped.
  - A change is mapped only when it reaches a test.
- **Fallback.**
  - Broad paths (configuration, conftest files, `tests/support/**`, the manifest), unmapped non-prose paths and an unavailable old view select all `core`, all `gates` and native platform tests.
  - Expensive domains are included only through declared inputs or real dependencies.
  - `fallback:broad` reasons and every expensive domain's included/omitted reason are recorded.
- **Prose.**
  - `docs/**` other than machine-readable data, root `*.md` and `reports/**/*.md` select the docs gates and the readers of the changed file.
  - Prose never falls back.
  - Every non-prose change selects all gates.
- **R5.** Current audits stay out of commits until audit optimization G is accepted. Checkpoints run all of them at full depth.
- **Platform.**
  - Triggers:
    - a source that reads the platform or imports `ctypes`, `msvcrt`, `winreg`, `keyring` or `_winapi`;
    - production code that imports `subprocess`;
    - a declared platform path;
    - the broad path.
  - A trigger adds platform-tagged `core` and `gates` nodes.
  - A commit records a WSL obligation, which the next checkpoint's own whole-diff selection on WSL discharges.
- **Checkpoint load (Windows only).**
  1. The full-depth current-audit subrun runs as load.
  2. The selected concurrency nodes run as three separately attributable repeats.
  3. A repeat starts only after the load has recorded its first test phase. It counts only if that same load run is still running when the repeat ends, and run-record times confirm it.
  4. The load workload is repeated only as needed.
  5. A failure stops the lane and is kept.
  6. Overlap that cannot be held is `stability-unrun` (exit 3), never a pass.
  7. Cleanup stops only this runner's own process trees.

  POSIX runs the selection, including its concurrency nodes, serially without load.
- **Selection record and evidence manifest.**
  - Node IDs appear only as digests plus run-context labels, because some carry credential-shaped test parameters.
  - Each document is refused if the shared sanitizer would change it.
  - Subrun console output is not kept: identity, mode and times come from each subrun's own run records.

### How the real repository shaped the rules (test-first refinements)

A mapping survey over all 1,218 tracked files led to five refinements, each RED → GREEN in the selector controls:
- Only whole `a / b / c` chains name paths.
- Whole-code-folder scanners never make a change mapped.
- A rename is mapped when either of its paths is.
- `docs/**` is prose except machine-readable data.
- Code-folder references select only test readers, and mapped means reaching a test.

A "reaches a conftest ⇒ broad" rule was tried and then removed (ruling in the ledger). 129 of 135 `src/optimus` modules sit in the root conftest's import closure, and v4 maps `tools/testing/**` explicitly. Conftest-imported code runs inside every selected session anyway.

### Controls and mutation

- **Selector:** 38 controls. Every dependency kind is planted: imports, package `__init__`, relative imports (single-dot and parent), string imports, `-m` launches, path joins, tool readers, declared inputs, rename, delete, prose, machine data, configuration, platform and the old view. Also covered: determinism, reasons, `no-commit-input`, and that no single change turns a commit into the full suite.
- **Runner:** 16 controls.
  - Temporary Git repositories: index-vs-HEAD only, earlier commits in the checkpoint view only, unstaged provisional hashing, `--exact`, untracked files, rename/delete/Unicode names, a missing base.
  - Real nested sessions: an ACTIVE recorded subrun, complete overlap, a kept failure, unobtainable overlap reported as `unrun`, an interrupt that stops only owned processes, a dry-run CLI selection record, and sanitizer refusals.
- **Mutation:** 14/14 mutants killed across the selector and the runner. One equivalent mutant was dropped with its boundary proof, after the missing relative-import control had been added.

### Defects found and fixed during the task

- **The runner hung on the first execution.** On Windows a venv's `python.exe` is a launcher, and the run record names its child. The runner now matches the root or root-parent PID, and load iterations are bounded.
  - Stopping my own stuck session leaked one real-registry entry, `20261004T165602-47672-d6a805`. Its worktree is present, so it was kept, not deleted.
- **In-loop counting overcounted repeats.** The loop now stops on covered repeats.
- **The selection record carried raw node IDs.** The sanitizer refused it; the record now uses digests.
- **Four cross-cutting guards caught real gaps**, all fixed:
  - 2 child sites;
  - 3 logging sinks, now classified with demonstrating tests;
  - test globs;
  - the platform tag and tier of `test_run_profile.py`.

### Verification

| Check | Platform | Result |
|---|---|---|
| Tasks 1–2 focused gate (both briefs' commands + cross-cutting guards), `TMPDIR` set | Windows | 684 passed, 2 skipped |
| Same, `TMPDIR` unset | Windows | 684 passed, 2 skipped |
| Same (native clone at `d562e95` + Tasks 1–2 diff), `TMPDIR=/tmp` / unset | WSL | 632 passed, 54 skipped in each |
| Changed files Windows vs WSL | both | 12/12 byte-identical, no CR bytes |

Checkpoint B's own `--profile checkpoint` runs on Windows and WSL follow in the Checkpoint B section.

## Checkpoint B — Tasks 0–2 cumulative checkpoint profile (2026-10-04)

**Status: attempt 3 passed on the final Tasks 1–2 source on both platforms; Fable 5.1 accepted (SOUND WITH AMENDMENTS, report-only, applied); awaiting Codex.** Nothing is committed: the Task 1–2 commits (coverage-hook skip only) need Fable then Codex to accept Checkpoint B on this tested source. Push, PR and merge stay held.

Checkpoint B runs the change-selected `checkpoint` profile itself (`python -m tools.testing.run_profile --profile checkpoint --base a929aab2092876ab0d83ecc4e46896ae3a0935c0`) on native Windows and real WSL: the cumulative Tasks 0–2 selection from main, every current audit at full depth, the triggered platform lanes, Windows concurrency repeats overlapping the current audit and serial WSL concurrency without load. No full suite.

### Attempts (all sealed; failures and invalid runs retained)

| Attempt | Source | Windows | WSL | Receipts (seal) |
|---|---|---|---|---|
| 1 | Tasks 1–2 as first delivered | `win1` aborted by me (block-buffered console misread as lost); its orphaned subrun finished 4 failed / 4,992 passed: the two failures below plus two child-site tests whose real ancestor chain ended at the killed runner. `win2` cancelled before launch | **failed**: 2 failed / 4,949 passed / 86 skipped; audits 67 passed | `plan-11-30-checkpoint-b-attempt1-evidence-20261004` (`f2ffefcf…`) |
| 2 | after the fix pass below | **pass** (selected 5,028 passed / 40 skipped; audit load 67 passed; 3 counted repeats). Each record carries `parent=not_found:ancestor_exited`, which that runner did not yet label (round 2 adds it) | **invalid**: every test passed (4,982 / 86 skipped; audits 67) but the selected subrun's own record was INVALID | `plan-11-30-checkpoint-b-attempt2-evidence-20261004` (`e67c3ac2…`) |
| 3 | after the recorder clock fix | **pass** (exit 0) | **pass** (exit 0) | `plan-11-30-checkpoint-b-attempt3-evidence-20261004` (`e170d993…`) |

Correction to the sealed attempt-2 note (Fable M1): the WSL lane ended at 19:03:35.89Z, before the Windows overlap lane began (19:05:24.99Z); it overlapped only the Windows `selected` subrun, not the stability repeats.

Attempt-1 failures: the committed-plan docs gate (frozen v4 Tooling cell) and the provider-balance retirement guard (the Task 1 manifest and guard map spelled its retired token). The second was a real Task 1 defect that the Tasks 1–2 focused gates had missed because they did not run the whole `gates` tier; every later pre-checkpoint gate does.

### Reviews and the fix pass (test-first; one pass, then the recorder fix)

Fable 5.1 reviewed attempt 1 and returned **NOT SOUND** (three MAJOR). Codex independently recorded **B-M1**. Fable's re-review of that fix pass returned **NOT SOUND** again (R1 MAJOR: F2 only partly closed; R2–R4 MINOR), and all four were fixed before attempt 3. Fable then found R1–R4 and the recorder fix **SOUND** (with report corrections M1–M3), and its final check of attempt 3 and this section is **SOUND WITH AMENDMENTS** (C1–C3, report-only, applied): it recomputed both lanes from the raw run records, verified every seal, and accepts Checkpoint B on `d562e95` + `9d123df2…`. Every fix has a control that failed first; 19 + 6 + 10 + 2 + 2 mutants were killed (`cpb-fix/mutate_fixes.py`, `cpb-fix/mutate_docs.py`, `cpb3/mutate_round2.py`, the clock-site mutants, the two sanitizer demonstrations).

| Finding | Fix | Control |
|---|---|---|
| F1 (MAJOR) retirement token in `tests/` | the guard is classified by a gates path rule `tests/unit/test_*_surface_retirement.py`; the test-side name is assembled at runtime; the guard still runs as `gates` | the guard itself (failed in attempt 1) and the current-source guard map |
| F2 (MAJOR) prose omitted gates that scan the docs tree | a prose change also selects the **gates-tier** whole-folder readers of its folder | `test_prose_in_a_scanned_folder_selects_the_gates_that_scan_it_and_no_cost_tier_scanner` |
| F3 (MAJOR) a root-conftest change omitted the run-context controls | the root conftest and the profile plugin are inputs of the run-context lane | `test_a_session_hook_change_selects_the_run_context_controls` (both paths) |
| B-M1 (Codex) / F6 a pass without valid terminal or capability evidence | `record_validity` reads each finished subrun's own terminal record: terminal checkpoint and time, ACTIVE, no terminal failure, COMPLETE, recorded exit equal to the process exit, and on Windows a valid native job and an installed guard. POSIX unsupported labels, an UNKNOWN parent (with its reason) and reduced protection are kept as qualifications, never failures. A subrun never validated is `not_validated`. Failures stay failures | 13 refusal cases, 5 qualification cases, Codex's exit-0/ACTIVE/no-terminal-time probe, verdict-level controls, real supported-Windows and qualified-POSIX subruns |
| F5 overlap bounded by the load's session end | a repeat counts only inside the load's recorded test phases (first phase start to last recorded phase end); both records must support a pass, except a load this runner stopped | `test_a_repeat_counts_only_inside_its_load_s_recorded_test_phases` |
| F7 a start timeout escaped as a traceback (exit 1) | the run stops its own process trees and is `invalid` with the sanitized reason in the manifest | two controls, one with credential-shaped text |
| R1 (MAJOR, re-review) prose still omitted gates that scan the docs through a tool (`tools/doc_paths.py`) | for prose only, a scanning tool's importers are followed to tests (then gates-tier only); code changes keep direct scanners, as the earlier "a runner's own tests do not consume the folder it runs" ruling requires, and already run every gate | `test_prose_in_a_folder_a_tool_scans_selects_the_gates_that_use_the_tool`; on the real repository a new `docs/new-topic.md` now selects `test_document_names_under_docs_are_unique` |
| R2 a stall after repeats dropped what ran | the overlap lane catches a start timeout, stops its own load, keeps every load and repeat, and is `invalid` with the sanitized reason | a real-process stall after `repeat-1`; a sanitizer demonstration (new classified sink `run_profile:overlap:exception_export`) |
| R3 weaker labels dropped | `parent=not_found[:reason]`, `processes=QUERY_FAILED` and `members=incomplete` are kept as qualifications, as the run's own summary line shows them | three qualification cases |
| R4 `unrun` hid a load's record problem | record problems are named before `unrun`; any other overlap verdict is `invalid` (an `invalid` outcome previously fell through to `pass` in the control before the fix) | three verdict-mapping cases |
| F8 snapshot provenance | the reference run is stated as exit 1 / INVALID diagnostic data | — |
| Docs gate (Codex-authorized) | a hash-pinned exception for exactly v4's Tooling disposition cell of exactly the approved raw bytes; every other check stays | approved snapshot passes only with it; same bytes under another name, altered bytes, another row with the same text and a broken status/owner all fail; 6/6 mutants |

**Attempt-2 WSL invalid, root cause and fix.** `tests/unit/tools/test_probe_p11_zed_session_load.py`'s two-lifecycle tests patch the global `time.monotonic` (through the probe module's `time`) to 100–1,100. The enclosing session's run-context recorder read that clock while their call phase was reported. On a WSL VM booted minutes earlier (session start at monotonic ≈253 s) the patched 1,100 fired a sample at 846.74 s (gap 707.138 s, exactly the patched value minus the last real sample), pushed the next sample 707 s out, and made the terminal sample's gap negative, which the samples table refuses: one recording error, so the record was INVALID. Windows uptime is far above 1,100, so it never triggers there; attempt 1 ran on an older VM. B-M1 refused the pass, as intended. Fix: the recorder binds its clocks at import (`tools/testing/run_context.py`), so no test's patch reaches it. Control `test_a_test_that_patches_the_global_clock_cannot_move_the_session_s_sampling` reproduced the failure in-process (1 sample, 1 recording error) before the fix; both clock-site mutants are killed. The probe tests are unchanged.

**Pre-checkpoint focused gate on the final source (Windows):** 1,009 nodes (the whole gates tier, the Tasks 1–2 gate files, the docs file and the retirement guard): 1,007 passed, 2 skipped. The commit hooks (ast-grep through pre-commit's own environment, Ruff, TOML, trailing whitespace, config trust, Bandit), both secret scans and `git diff --check` pass over the working tree. The fix pass also classified one new logging sink (`run_profile:execute:exception_export`, shared sanitizer, with a demonstrating test).

### Attempt 3 (final source) — results

Source: HEAD `d562e95` plus the working diff `9d123df294f7…` (Windows) / the identical patch on a native WSL clone. Selection on both: **5145 selected, 281 deselected**, fallback `broad` (`.gitattributes`, `tests/conftest.py`, `tests/profiles.toml`, `tests/support/profiles_plugin.py`; `unmapped: reports/plan-11-30-test-profiles-manifest.json`), platform `triggered` (8 triggers), expensive domains: audit-current and audit-sealed included, proc included, e2e-local omitted (no dependency or declared input changed), audit depth `full`, 381 concurrency nodes.

| Platform | Subrun | Run ID | Nodes | pytest | Exit | Record | Qualifications |
|---|---|---|---|---|---|---|---|
| Windows | `selected` | `20261004T195132-15248-06ed9d` | 5078 | 5038 passed, 40 skipped, 1 warning in 1027.43s (0:17:07) | exit 0 | valid | parent=not_found:ancestor_exited |
| Windows | `load-1` | `20261004T200844-7248-98efd6` | 67 | 67 passed in 812.78s (0:13:32) | exit 0 | valid | parent=not_found:ancestor_exited |
| Windows | `repeat-1` | `20261004T200848-41940-2e9039` | 381 | 373 passed, 8 skipped in 61.16s (0:01:01) | exit 0 | valid | parent=not_found:ancestor_exited |
| Windows | `repeat-2` | `20261004T200953-52988-073933` | 381 | 373 passed, 8 skipped in 44.54s | exit 0 | valid | parent=not_found:ancestor_exited |
| Windows | `repeat-3` | `20261004T201042-35188-e01641` | 381 | 373 passed, 8 skipped in 44.49s | exit 0 | valid | parent=not_found:ancestor_exited |
| WSL | `selected` | `20261004T195200-522-b5f07d` | 5078 | 4988 passed, 90 skipped, 1 warning in 228.70s (0:03:48) | exit 0 | valid | native=unsupported, guard=unsupported_platform, parent=unsupported |
| WSL | `audit-current` | `20261004T195606-4381-099015` | 67 | 67 passed in 555.02s (0:09:15) | exit 0 | valid | native=unsupported, guard=unsupported_platform, parent=unsupported |

- **Windows verdict:** **pass** (exit 0). Stability: **complete**: 3 repeats each inside one load run's recorded test phases; load run `20261004T200844-7248-98efd6`; counted repeats `20261004T200848-41940-2e9039`, `20261004T200953-52988-073933`, `20261004T201042-35188-e01641`.
- **WSL verdict:** **pass** (exit 0). Stability: none (POSIX runs the selection, its concurrency nodes included, serially without load).

Windows overlap (UTC; a repeat counts only inside its load's recorded test phases):

| Subrun | Run ID | Started | First phase | Last phase end | Finished | Counted inside |
|---|---|---|---|---|---|---|
| `load-1` | `20261004T200844-7248-98efd6` | 2026-10-04T20:08:44.278259+00:00 | 2026-10-04T20:08:45.396193+00:00 | 2026-10-04T20:22:17.023296+00:00 | 2026-10-04T20:22:17.277579+00:00 | — |
| `repeat-1` | `20261004T200848-41940-2e9039` | 2026-10-04T20:08:48.254385+00:00 | 2026-10-04T20:08:51.693219+00:00 | 2026-10-04T20:09:32.708857+00:00 | 2026-10-04T20:09:32.980502+00:00 | 20261004T200844-7248-98efd6 |
| `repeat-2` | `20261004T200953-52988-073933` | 2026-10-04T20:09:53.888485+00:00 | 2026-10-04T20:09:57.451751+00:00 | 2026-10-04T20:10:38.388195+00:00 | 2026-10-04T20:10:38.678429+00:00 | 20261004T200844-7248-98efd6 |
| `repeat-3` | `20261004T201042-35188-e01641` | 2026-10-04T20:10:42.655635+00:00 | 2026-10-04T20:10:45.889000+00:00 | 2026-10-04T20:11:27.108869+00:00 | 2026-10-04T20:11:27.403396+00:00 | 20261004T200844-7248-98efd6 |

The WSL lane ran 19:52:00–20:06:08Z and overlapped these Windows subruns: `selected`. Other lanes' runs may also have been active. No timing claim is made from these runs.

**Receipts after the final edit of this section** (Fable C3): the docs gate and detect-secrets were re-run on the final report and manifest; their outputs and run record are sealed in `plan-11-30-checkpoint-b-report-receipts-20261004`, named in the Codex packet.

### Registry archival (Codex option A, executed 2026-10-04 ~18:15 UTC)

Against the original reviewed manifest (class `28bc1799…`, 724 eligible): the fresh dry run was 723 `would_archive` and 1 `changed_since_inventory:root_unknown`; execution archived 723 and refused the same member (exit 3); `verify` exited 4 with 3 problems, all on that refused member, which is still in place, byte-unchanged, with no copy and no receipt. **PARTIAL, NON-PASSING**: 723 archived with per-member proof; the original manifest remains incompletely reconciled. Receipts: `plan-11-30-archival-evidence-20261004` (`6a4bec8d…`).

### Residuals and deferred items

- **Abrupt runner kill** (Fable F4, deferred): `tools.process_tree` jobs carry no kill-on-close, so killing the runner process itself orphans its subruns (as `win1` showed). Interrupts, failures, start timeouts and normal ends stop every owned tree.
- **Hook context** (F9, deferred to Task 3): no control yet runs the runner inside a real hook with `GIT_INDEX_FILE`; Task 3 wires the hook and adds it.
- **Two cheap AST audits stay `audit-current`** (A4): tiered by audit family; checkpoints run them; `gates` would fit equally.
- **Selection limits** (Task 2 rulings): a fixture used only by name through conftest-wrapped product code is not followed; `Path(__file__).parent / "fixtures"` readers and `reports/*.json` take the bounded broad path; `no-commit-input` exits 0 with that label, never `pass`. The final full runs remain the backstop.
- **Subrun console output** is kept only because the checkpoint scripts redirect the runner's console; their digests are in the attempt receipts.
- **Recorder clock**: fixed at the recorder; other code that reads a patchable clock during a test is not audited here.
- **WSL wall-clock timestamps** (Fable C2): in attempt 3 the WSL guest wall clock advanced about 47 s (audits) and 15 s (selected) more than monotonic time (VM time re-sync: wall spans 602.0 s and 243.8 s against 554.8 s and 228.5 s monotonic, pytest 555.02 s and 228.70 s; inter-phase wall gaps up to 24.3 s, Windows at most 0.044 s). WSL `started_utc`/`finished_utc`/phase `at` values are therefore accurate only to about a minute. No claim here depends on them: WSL runs serially without load, counts and outcomes are unaffected, and the lane-overlap statement survives a one-minute error. Gap arithmetic on WSL records needs this caveat.
- **Scans seen through path joins only** (Fable M3): a gate that scans the docs solely through a loose pathspec string (for example `tracked_repository_files(..., pathspecs=["docs"])`) would be invisible to the prose scanner rule. None exists outside `tests/unit/docs/**` today, and `tools/doc_paths.py` joins `REPO_ROOT / "docs"`, so it is reached.
