# Plan 11.27 v9 — Production CI Secret Scan Remaining-Work Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task. Claude implements; Codex reviews the plan and candidate. Steps use checkbox (`- [ ]`) syntax for tracking; only fresh passing evidence supports a progress claim.

**Goal:** Complete Task 4 only: review, rehearse and locally commit the accepted Slice B candidate through its full Windows hook, preserving prior evidence and all publication limits.

**Architecture:** Preserve the accepted eight-file candidate and recovered Windows environment. Complete current-state documentation and frozen-plan custody, prove a full-history independent rehearsal at the bound parent with the exact candidate tree, review actual evidence, then perform one final local commit with its own enforced Windows hook and externally sealed coverage/JUnit.

**Tech Stack:** Existing locked Python 3.14/dev dependencies; pytest 9.1.1, coverage 7.14.3, pre-commit 4.6.0, detect-secrets 1.5.0, identify 2.6.19; PyYAML, Git Bash, Windows and WSL Ubuntu 24.04. No dependency changes.

**Spec:** This complete Task 4 successor retains prior final-delivery requirements, accepted Tasks 2/3 and recovery custody. Frozen scope SHA-256 `f5d2b923b280999bb3ac68008b348e4933d59edd692d1b07efd8b5db3a3dad1b`; reviewer handoff v2 SHA-256 `0b7a6933427bc7565071053e98e774ac2464ddb918e428ed1286216338989e43`.

Input locations: `D:/Projects/Development/Python/optimus-agent-handoff/CODEX-BRIEF-2026-09-03-frozen-secret-scan-scope.md` and `C:/worktrees/optimus-cost-agent-wt-codex-plan-11-26/tmp/static-first-ci-pickup-20260904/reviewer-handoff_v2.md`. Executors read both, the current reviewer checkpoint, and the newest appended/shared-header state in `D:/Projects/Development/Python/optimus-agent-handoff/CURRENT.md` before mutation.

**Status / authority:** Operator approved separately scheduling Task 4 with at least 40 combined-agent minutes, then said "Approved". This opens a new **40-minute Task 4 box** at the current Codex turn start, **2026-09-05 07:36:45 UTC**. Codex successor/final-document preparation is the first Task 4 activity and counts inside that box; Claude continues the same task after handoff. No separate pickup allocation or reset of earlier boxes. Original Option 1 approval was directly confirmed by the operator; recovery/Task 3 are accepted. No new operator approval is required for the authorized Task 4 sequence. The actual candidate commit still requires Codex concurrence on the final rehearsal/evidence. No push, PR, merge, installation, tag or fresh FU-6 revalidation.

**Frozen predecessors:** [v8](2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v8.md), SHA-256 `d41d6ba0ed1dc5e4a4e7e7c116dc12594501734277bb84d307f673897e811c7f`, remains the unrevised recovery proposal; operator Option 1 disposition overrides its reservation only for historical recovery/Task 3. Do not backdate it. [v7](2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v7.md), SHA-256 `9e05956c971310cbf9f6b31600c054e6172bdc4f29d98ddc0c63b2eb70d22b1b`, retains the preceding 75-minute box. [v6](2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v6.md), SHA-256 `83a8edf069863599830d9274e9073997aebe289490a762f942c6198afa130544`, owns accepted Task 2 and the budget stop before Task 3. Preserve all 34 Task 2 artifacts and the original failed attempts. [v5](2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v5.md), SHA-256 `f71006d3eb5662cffa5e8f9619efc83a440d2d92286a03a4ee861bf15fdfbc5a`, remains byte-exact and owns the accepted Slice A history and protocol corrections. V2 SHA-256 `577a1c7e5864d9d5d424f0dbf6ac5bd2b496b2ba809f714cdfe3c4574f641fc1`, v3 SHA-256 `dec4163fb294bfe56805ee6b1d245d25c1904b8424c2e567b90e94bb84168800`, and v4 SHA-256 `6fbb5600d18cfb9d570e68933439a441a12b674732d0fc384ae3e9e906400c83` also remain byte-exact at their review locations. The archived scratch predecessor SHA-256 is `4900776b5332a061a148b3ad35db9fa2cfe539504c458eb7b5bca48d5a603751`. Apply the established mechanical path-relocation proof before archiving any frozen predecessor. Until then their transitional custody remains registered; do not rewrite approved prose or relative links.

### Accepted Slice A prerequisite — read-only in v9

Candidate `C:/worktrees/optimus-cost-agent-wt-claude-ci-production`, branch `agent/claude/ci-production-secret-scan`, is an independent clone. Local commit `c1989985171c3054916732f1306d5ffc85d5b094` has parent `5ea8f8f71548eb05a8562a10e98667e3d2061c4d` and tree `258406df199720d19dbdd1f2640567f4f9aca4a8`, equal to the approved rehearsal. It changes exactly `tests/conftest.py`, `tests/unit/acp/test_stdio_ndjson.py`, and `tests/unit/tools/test_git_env_immunity.py`; reviewed raw hashes are `540decf8869143984ece18ec99fabb626d34c3ba43af1c65d08b75bcefbf5b08`, `87403e00b42a295b8ddc0820d56ba05818398b25c9546f220c7e2da25e31e585`, and `ba5a5329dcf5936fe004fed8dbb3a6addb196a4ac0f420dc165261df4b764619`.

The actual commit log, SHA-256 `cdf3d458daa906051a7c4c97caf5b2e511958275e66251ec19ac9467ae5ddea1`, records eight applicable hooks Passed and YAML/TOML Skipped. No FU-6 hit occurred. The hook-created coverage database is externally sealed at SHA-256 `da133c6b12c6780bbdc4a768a25c635ac8aa921110c67627d19e540f4d469a4e`; Codex independently derived TOTAL 13497 / 1456 missed / 3522 branches / 609 partial / **86.23%** from that external copy without rerunning tests. The report hashes to `b25b579584acee5ffffd3fd6693c5d0b91dca78efeb514d0de5a4a55d7c9f76f`. All 35 entries in external manifest SHA-256 `6522ecf5d80f0cecbd2956085026ea95c2ad9d918ffae1f3fab993a9569a29c8` match. The separate 86.08% figure belongs to the successful rehearsal. One original PATH-setup log remains irrecoverable and operator-accepted as an explicit gap; do not recreate or relabel it.

At Task 4 entry the candidate has the accepted eight-file delta at Slice A HEAD. Slice A and accepted Tasks 2/3 are prerequisites, not new implementation work. No amendment/rebase/recreation or historical RED rerun. Recheck live identity without restarting accepted tasks.

## Global Constraints

- Scope classification: multi-file Slice B changeset, limited to the seven functional files and listed current-state/governance documents below. Slice A is a committed prerequisite and receives no v9 mutation. Codex authors/reviews only; Claude performs implementation after specific v9 approval.
- Bound candidate parent is local Slice A commit `c1989985171c3054916732f1306d5ffc85d5b094`; bound main base remains `5ea8f8f71548eb05a8562a10e98667e3d2061c4d`. These are local-state pins, not remote-freshness claims. Task 4 rechecks main and the already-created branch before resumption; relevant drift stops for review, never a silent transplant or rebase.
- Target: `C:/worktrees/optimus-cost-agent-wt-claude-ci-production`, branch `agent/claude/ci-production-secret-scan`. It is an independent clone, not a linked worktree. The explicit isolation decision overrides the usual linked-worktree default; the contributor naming convention remains intact.
- Preserve the parked `D:/Projects/Development/Python/optimus-cost-agent-wt-codex-ci-production`: staged conftest/immunity test and unstaged Gateway diagnostic are evidence, not input to copy wholesale. Preserve the accepted sandbox at `0071b424c185fb45badb7e75be610ba44b9cfd0e`.
- Hard cap: **40 new combined agent minutes for Task 4**, beginning 2026-09-05 07:36:45 UTC. Entry gate is satisfied with all 40 allocated at task entry. Successor documentation, audit, pickup, rehearsal, review, actual commit and evidence all consume it. Claude does not receive a second 40-minute allowance and need not reapply the entry reservation midway through the same task. Track each agent turn including reporting, exclude relay idle, sum concurrent work separately. Stop if all remaining mandatory gates cannot fit; never compress verification or stop mid-custody to claim delivery. No balance transfer from earlier boxes.
- Main `.secrets.baseline` **SHA-256 of raw Git blob contents** stays `89eb6f47e9a1279ff6b9dad5f12e53a221914a16e0eabd873108bd7001397d71`; the same hash domain for `uv.lock` stays `f1caae185d41b02de2bf9a1cc4970e2517278c8a12b3a4728dd71fc2d826a097`. These are not Git object IDs or raw working-tree-file pins. Use the binary method below. Do not import the sandbox's one-entry baseline.
- No broad baseline regeneration, detector/filter weakening, new dependencies, local-hook coverage change, Ruff rule change, or production runtime behavior change. Four production files receive only the reviewed non-credential annotations below.
- Full default Windows commit hooks remain mandatory, with the existing marker exclusions and coverage threshold of at least 80%. No bypass, marker narrowing, retry loop, timeout widening to hide a failure, or Linux-only landing to avoid a Windows failure.
- Slice A's three-file prerequisite is already committed and may not be modified or restaged by v9. RED safety probes operate only on disposable repositories.
- Full-suite temporary directories, raw evidence and scan-bearing caches/copies must be short and outside **every** tested checkout/export, using resolved paths. Git ignore rules do not establish exclusion from the document/config-trust gates. The dedicated immunity-provenance probe may put its child test under its own isolated export; that exception does not set full-suite `--basetemp` or authorize candidate-local transcripts.
- Sanitize inherited `GIT_*` before new fixture/setup subprocesses. Before config/index/ref writes, prove both `git rev-parse --absolute-git-dir` and resolved `--git-common-dir` stay inside the intended independent repository. Never copy a linked `.git` pointer or use shared objects/alternates.
- Claude owns shared `CURRENT.md`. Codex owns the ignored `docs/superpowers/reviews/plan-11-27-review-checkpoints.md`. Neither agent treats the other's narration as verification. The checkpoint is local handoff custody, not a required file in a clean Git export.

### Hash domains and exact verification method (F3)

Run this in the intended clone, with the already verified clean Git environment. `subprocess.check_output` returns bytes: do not use `text=True`, decode/re-encode the output, or pipe Git output through PowerShell's text pipeline.

```python
import hashlib
import subprocess
from pathlib import Path

base = "5ea8f8f71548eb05a8562a10e98667e3d2061c4d"
pins = {
    ".secrets.baseline": "89eb6f47e9a1279ff6b9dad5f12e53a221914a16e0eabd873108bd7001397d71",
    "uv.lock": "f1caae185d41b02de2bf9a1cc4970e2517278c8a12b3a4728dd71fc2d826a097",
}
working_tree_start = {}
for path, expected in pins.items():
    approved_blob = subprocess.check_output(["git", "show", f"{base}:{path}"])
    assert hashlib.sha256(approved_blob).hexdigest() == expected
    assert subprocess.check_output(["git", "show", f":{path}"]) == approved_blob
    subprocess.run(["git", "diff", "--exit-code", base, "--", path], check=True)
    working_tree_start[path] = Path(path).read_bytes()
```

Record both `git_blob_sha256` and `working_tree_sha256` in the manifest. For each member of `pins`, require index bytes from `git show :PATH` to equal the bound-base bytes; after the final commit require `git show HEAD:PATH` to equal them too. Separately require `Path(path).read_bytes() == working_tree_start[path]` throughout that checkout's run. Each scanner fixture records its own actual input bytes before scanning and requires exact equality after every invocation; the accepted primary oracle continues to enforce this raw-byte check. Do not normalize a scanner's mutation away.

The existing main checkout's baseline currently hashes to `1ebd1b22a4b4372aa7a5fce820b76bd44e1cd9affe6332297dce3525e8a4577a` as a raw file (127 CRLF line endings), while its raw blob has the pin above. The review checkout's raw file matches the LF blob. `uv.lock` matches its pin in both inspected checkouts. Current `.gitattributes` requests `eol=lf`; these observations do not assert what every new checkout will produce. A raw-file/blob mismatch prompts attribute/diff inspection, not an automatic drift STOP or a file rewrite. An actual tracked-content difference still stops.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| code/state | Existing candidate at c1989985 with accepted eight-file delta b54da0a4... | yes | Claude custody; Codex review | Verify exact full pins below before further work. Mismatch stops for review, no automatic repair. |
| evidence | 55 artifact manifest and preserved failures, Tasks 2/3 acceptance, Slice A custody | yes | Claude custody; Codex review | Independently verified. Preserve prior manifest bytes before additions; no rerun to recreate history. |
| tooling/binaries | Recovered Windows Python 3.14.4 and installed full hook | yes | Operator machine state; Claude | Recovery validated, focused Windows gates passed. Verify identities; new incompatibility stops, no fresh repair authority. |
| tooling/binaries | Existing WSL native environment | yes | Claude | Verified no-sync retry passed. No new WSL run required solely for Task 4; if needed pin it and disable sync to protect Windows .venv. |
| evidence | Independent rehearsal destination absent | yes | Claude | Checked during prior review; recheck before clone. Collision stops; never reuse/delete silently. |
| services | Real local Git/pre-commit/scanner and default Windows hook dependencies | yes | Claude | Accepted locked setup; no Redis/Gateway/GUI/paid API prerequisite added. A new unavailable dependency stops. |
| credentials/authority | Separate Task 4 40-minute box and execution | yes | Operator | Explicitly approved. No publication or new dependency repair authority. |
| human interaction | Final Codex concurrence on exact candidate/rehearsal/evidence before actual commit | no | Codex | Genuinely absent but scheduled within this Task 4 box. Not waived by execution approval. |
| cost | Paid model/Gateway calls | yes | Operator | None required; agent active time is budgeted. |
| revalidation | Fresh FU-6 authority | no | Operator | Merely unauthorized. Any fresh hit stops pending new per-hit P1. |
| publication | Push/PR/merge/installation/tag | no | Operator | Merely unauthorized and excluded from local delivery. |

## File Scope and Commit Boundary

All implementation paths are relative to the existing candidate clone. No Slice A file and no other implementation file may change.

| Class | File | Exact responsibility |
|---|---|---|
| B | `.pre-commit-config.yaml` | Preserve accepted Task 2 manual hook; include its existing delta in the final commit; existing local hooks unchanged. |
| B | `.github/workflows/guardrails.yml` | Preserve accepted Task 2 inventory check and production-hook invocation; include existing delta in final commit. |
| B | `tests/unit/guardrails/test_ci_parity.py` | Preserve accepted Task 2 real-command, selection, binding, timeout/containment controls and baseline policy; run in Task 3 focused verification. |
| B | `src/evidence_handoff_runtime/migrations.py` | Annotate only the three recomputed SQL integrity hashes. |
| B | `src/optimus_gateway/observability.py` | Annotate only the four redaction labels, with unchanged AST. |
| B | `src/optimus/acp/launch_policy.py` | Annotate the enum label and synthetic URI text; preserve the docstring value and full AST. |
| B | `src/optimus/acp/local_gateway_secrets.py` | Annotate only the two keyring lookup names. |
| B docs | `README.md` | Describe the production CI boundary accurately, without claiming repository-wide or local-hook repair. |
| B docs | `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Sole registry/custody; record local delivery, exclusions and later publication gate without closing the parent work. |
| B docs | `docs/superpowers/plans/2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v9.md` | Add the complete Task 4 contract recording the operator-approved scope and box. |
| Frozen custody | Plan 11.27 v2, v3, v4, v5, v6, v7 and v8 at their current root paths | Add byte-exact approved predecessor records and keep their Blocked transitional registry rows. Do not edit or move them without the mechanical Git-blob relocation proof. |
| Frozen custody | `docs/superpowers/plans/archive/2026-09-03-plan-11-27-git-test-immunity-and-production-secret-scan.md` | Add the byte-exact stopped scratch predecessor already located in the flat archive. |

The designated ignored reviewer checkpoint stays at `docs/superpowers/reviews/plan-11-27-review-checkpoints.md` and is never staged. Raw evidence, reports, scripts, rehearsals, copied trees and scan-bearing caches stay outside every tested tree and are never staged. The unrelated parked `tests/unit/optimus_gateway/test_server.py` diagnostic and parked lane remain untouched. This package neither diagnoses nor closes FU-6 or FU-7.

## Accepted Candidate and Entry Verification — inside Task 4

No separate Task 0, Task 2 or Task 3 allocation. Accepted candidate:

- Existing clone `C:/worktrees/optimus-cost-agent-wt-claude-ci-production`, branch `agent/claude/ci-production-secret-scan`; HEAD `c1989985171c3054916732f1306d5ffc85d5b094`, tree `258406df199720d19dbdd1f2640567f4f9aca4a8`, parent/main `5ea8f8f71548eb05a8562a10e98667e3d2061c4d`.
- Eight unstaged paths: seven functional files listed above plus README. Entire `git diff --no-ext-diff --binary` must equal external `task3-final-functional-diff-20260905T072708Z.patch`, SHA-256 `b54da0a496eb5c649f9e190583e578009d42c87a9802487dac3fde4899af5a4b` before adding final documentation. No staged files or unexpected changes; preserve all untracked files.
- Task 2 three-file subdiff SHA-256 `bff2b1a13689fb0296c8dd82f884b523b6ab95b41f75c4986f6bd332dbbdcbd9`: real configured-command 0/1/0 canary, exact tracked-text selection, nonempty guard, ten independent binding mutants, bounded timeout/tree/reap and Git common-dir controls. Accepted final Task 2 logs 29 passed per OS; prior failures preserved.
- Task 3 full-module AST/docstring equality and three unchanged SQL files/hash proofs accepted. Recovered Windows final log: 144 passed, Ruff/diff clean, full production command 200 text paths/exit 0. WSL direct focused run: 144 passed; safe production retry: exact same 200 paths/exit 0, native venv pinned and no sync, candidate Windows cfg/layout preserved. Codex inspected logs and independently verified source/custody, without claiming a fresh independent test execution.
- Current external custody: `D:/Projects/Development/Python/optimus-ci-production-evidence-slice-b-20260905`, 55 valid entries plus current manifest. Preserve incident Linux environment at `C:/Users/pc/AppData/Local/Temp/claude/plan1127-venv-incident-20260905`; no new repair/delete. Windows cfg SHA-256 `9c503845220632572999aad4d94004d287277ec4971a5230d8a12fcd3ee91afb`, Python 3.14.4, uv 0.11.29, pytest 9.1.1, pre-commit 4.6.0, detect-secrets 1.5.0, Ruff 0.15.20, coverage 7.14.3, Git 2.55.0.windows.5. Installed hook hash `e9e5a93b689822e50f6bb00c706332f4ff290f9c36811d9c2a48be58690e4f7c`.
- Shared main `D:/Projects/Development/Python/optimus-cost-agent/.git/config` SHA-256 `ae6059069cc62fde0eb237ecc9c6c0277974ff257b362c7ad596a5d35c651446`. Check raw blob/index/working baseline/lock pins by the method above, contained Git/common dirs, no shared object stores, and installed hook. No full-suite or incident replay for pickup.

Preserve all failed attempts, corrections and the accepted missing PATH-log disposition. Before extending any manifest, preserve its previous bytes under a fresh name. Final evidence naming may point to already-sealed named records through an explicit claim-to-artifact mapping; never rename or recreate prior logs as new executions.

## Task 4 — Final Review, Full-hook Rehearsal and Local Delivery (40 minutes)

Task 4 entered with the newly approved 40-minute allocation at 07:36:45 UTC. All work below and Codex preparation/review count within it. Before each expensive gate, check whether all remaining mandatory work fits. Stop with preserved evidence if not; no automatic extension or gate compression.

- [ ] Give Codex the seven-file functional diff and Task 2/3 evidence. Codex performs the required current-state freshness audit and authors the final sole-backlog update in its reviewer checkout; Claude may edit `README.md` but does not invent plan/backlog prose. Copy the exact approved v9, byte-exact v2-v8 predecessors and archived scratch record from `C:/worktrees/optimus-cost-agent-wt-codex-plan-11-26` into their listed candidate paths. Verify v2-v8/scratch hashes against this plan and v9 against its operator-approved digest recorded in the checkpoint. Keep predecessors at the live root under their Blocked rows because the required authoritative Git-source relocation proof is not yet available. Never copy the ignored checkpoint, review probes or raw evidence.
- [ ] Require `C:/Users/pc/AppData/Local/Temp/claude/plan1127-v7-slice-b-rehearsal` to be absent. Create the final full-history rehearsal with `git clone --no-local --no-checkout C:/worktrees/optimus-cost-agent-wt-claude-ci-production C:/Users/pc/AppData/Local/Temp/claude/plan1127-v7-slice-b-rehearsal`, then switch it detached to exact parent `c1989985171c3054916732f1306d5ffc85d5b094`. Do not clone uncommitted working-tree state. Strip inherited `GIT_*`; verify both Git directories remain inside the rehearsal, no shallow store, no alternates/shared object links, exact parent/tree equality including tracked ignored IDE files/reports, and availability of every history pin required by unchanged document tests. Do not synthesize a root commit with `git add -A`. Apply only the exact candidate Slice B diff and verify the resulting rehearsal tree equals the candidate's complete proposed tree before testing. Preserve Slice A's existing rehearsal/evidence without rerunning it.
- [ ] Use the same locked tools and unchanged applicable hooks as the candidate. Record resolved Python/pytest/pre-commit and cache paths. Before any uv invocation in candidate or rehearsal, pin invocation-only UV_PROJECT_ENVIRONMENT and VIRTUAL_ENV to the recovered Windows candidate .venv and set UV_NO_SYNC=1; verify actual Windows interpreter resolution. Do not allow uv to create/sync a rehearsal-local environment or replace the recovered one. No fresh sync/dependency repair is authorized. When invoking from Git Bash, prepend the POSIX venv path (for this lane, `/c/worktrees/optimus-cost-agent-wt-claude-ci-production/.venv/Scripts`) to PATH; a literal `C:/...` element is split at its colon. Keep raw logs, scripts, copied trees and scan-bearing caches outside all tested roots. Do not add scanner/doc-test exclusions. A setup failure remains a failed attempt with a fresh raw log; classify it before any retry.
- [ ] Rehearse the final Windows commit with the installed unchanged pre-commit hook. Capture command, stdout/stderr, exit code, every applicable hook status and pytest/coverage outcome under the exact Slice B evidence directory. Successful hooks can suppress detailed stdout: preserve the emitted log and coverage database/report, and do not infer counts from another run. For the actual commit process only, set `PYTEST_ADDOPTS="--junitxml=D:/Projects/Development/Python/optimus-ci-production-evidence-slice-b-20260905/b-commit-junit.xml"` in that process's environment; in Git Bash this is the one-command prefix immediately before `git commit`. Do not persist the variable or edit the existing `optimus-pytest-coverage` hook mapping: its `entry: pytest --cov=optimus --cov-branch --cov-report=term-missing` and `pass_filenames: false` remain byte-for-byte unchanged while the separately scoped manual secret-scan hook is added. Verify the JUnit report exists, the existing selection/coverage arguments still ran, and the tracked hook mapping is unchanged. Preserve command, environment and report bytes. Record non-applicable hooks as Skipped. Preserve every failed attempt under a fresh name. Require candidate/rehearsal tree equality and report baseline, lockfile, config and shared Git-state invariance.
- [ ] Codex reviews the exact diff and failure-path controls, not just counts. Before the final commit, Codex also audits every current-state claim this change affects in README, roadmap and backlog, without altering frozen history. Any required out-of-scope current-state repair goes back for a complete successor; do not silently expand the file list.
- [ ] After concurrence, stage exactly the seven functional Slice B files, README, sole backlog, v9 and listed byte-exact predecessor custody; exclude ignored checkpoint, raw evidence and unrelated files. Verify the staged proposed tree equals the reviewed/rehearsed tree. Then run the actual local commit's own full Windows hook. Do not replace it with rehearsal evidence. A real full-hook failure is a failure even when the rehearsal passed. No additional optional full-suite repetition is required.
- [ ] Use commit message `fix: enforce production-only CI secret scanning`. Record actual commit/tree IDs, staged paths, coverage/JUnit hashes, invariant hashes, clean working tree and reviewer concurrence. Preserve both local commits without push, tag, PR, merge or installation. No tag is needed.

## FU-6 and Other Stop Conditions

The historical P1 grant names failed log SHA-256 `987c7444bfadf2f52a2387f65e3a45ad9b07a291fc2a85186a58b4d8b01ae632`. Its authorized attempts are historical; it is **spent**, not reusable. P1-P9 govern any later operator-authorized revalidation, but this plan does not grant one.

A new FU-6 hit in a focused gate, rehearsal or actual commit means STOP: retain the exact failed command/log/hash, tree and platform; notify the operator and Codex. No automatic retry, commit from WSL, timeout widening, skip, suppression or claim of closure. A later P1 must name that hit and its STOPPED artifact in writing. P8 allows one revalidation for the named hit; P9 still requires the actual commit hook. Retain failed evidence above any separately authorized clean result, preserve source equality, record the required dated FU-6 observation without changing its Status, and prove the full default Windows selection/normal temp layout. The old 111-deselected count is bound to its old base; do not manufacture that count on a different base.

Other STOP triggers: relevant base drift; unavailable locked tooling; config/Git-store escape; missing independent review; actual or unclassified secret; unapproved file/detector/baseline change; an out-of-scope test failure; production behavioral change; or cap exhaustion. Defects introduced by this implementation may be corrected within the listed scope and remaining box. Prior failing evidence is never overwritten or converted into a passing row.

## Explicit Exceptions

These obligations stay with the named owner in the [sole backlog](2026-07-23-consolidated-deferred-followups-backlog.md); this plan does not close them.

| Excluded obligation | Owning entry / next gate |
|---|---|
| Broader baseline migration, repository-wide scan promotion, PR #194 collision, frozen-artifact custody, local-hook redesign and security-gate tension | `P11-FEAT-ACP-RUNTIME-HARDENING`; separately reviewed migration/design. |
| Focused production S110 enforcement; other Ruff families; evidence-handoff test findings | `P11-FEAT-ACP-RUNTIME-HARDENING`; next bounded static-analysis plan after CI. Preserve outbound-writer settlement/worker survival when disposing S110; do not introduce fallible logging or global ignores. |
| Gateway intermittent diagnosis, priority adjudication and closure; parked diagnostic | `P11-FU-6`; its separate Windows lifecycle lane. A per-hit observation does not change that Status. |
| Historical NDJSON coverage-flake closure and its remaining 25-process evidence gate | `P11-FU-7`; separate evidence lane. The explicit EOF prerequisite does not spend that gate or rewrite its diagnosis. |
| WP-27 runtime integration, helper-level isolation, live session evidence, publication and installation | `P11-FEAT-ZED-RESUME`; accepted runtime lane and operator publication authority. |
| Earlier unexplained watchdog assertion and shared-cache repair | `P11-FEAT-ACP-RUNTIME-HARDENING`; separate evidence/environment disposition. A capture abort before tests ran does not explain an executed-test assertion. |
| Main CI activation, branch protection, remote publication and merge | `P11-FEAT-ACP-RUNTIME-HARDENING`; operator publication gate after local review. No sandbox merge route is assumed. |

## Evidence and Definition of Done

Use fresh run-named artifacts in resolved external evidence custody outside every tested tree; list every file's SHA-256, producer, command, platform, base/candidate tree, start/end time and actual exit code. Include a process-runner failing-control: an injected command exiting 7 must make the required-gate runner exit nonzero. Shell redirection, a trailing `cat`, or `tee` must not mask failure. Independent checks may run concurrently only with their own fixtures and all statuses inspected; dependent gates remain sequential.

| Claim | Required named artifact |
|---|---|
| Main-based isolated deliverable | Existing Slice A `state-start.json`, commit/coverage artifacts and 35-entry manifest, accepted Task 2 patch/logs and 34-entry custody, plus fresh `b-state-start.json` and `state-final.json`: ancestry, exact status, both Git stores, invariant hashes and untouched parked lane/sandbox. |
| Git protection is causal and its negative oracle is portable | Accepted Slice A `a-immunity-red.log`, `a-immunity-green.log`, `a-import-provenance.json`, the four `a-v4-control-*` platform logs and the reviewed source pin; do not recreate them. |
| EOF port preserves sanitization and failure handling | Accepted Slice A `a-eof-port-windows.log`, `a-eof-ordering-old.log`, three `a-eof-oracle-*` logs, WSL affected log and Codex review controls; do not recreate them. |
| Actual CI command rejects secrets and empty sets | Accepted Task 2 named artifacts plus final `b-configured-command.txt`, `b-windows-controls.log`, `b-wsl-controls.log`, `b-inventory.json`, `b-mutant-controls.json`; real scanner/pre-commit, 0/1/0, exact file/line, empty failure and baseline invariance. |
| Only reviewed non-credential dispositions changed | `b-production-classification.json`, `b-ast-and-sql-equality.json`, candidate diff and invariant hashes. |
| Required commit gates passed | Failed and successful rehearsal logs remain distinct (`a-rehearsal.log` is the historyless failure; `a-rehearsal-clone.log` is the later success), plus `a-commit.log`, `b-rehearsal.log`, `b-commit.log`, `runner-negative-control.log`; explicit exits/statuses, actual tree equality, retained coverage/JUnit outputs and full default Windows selection. |
| Scope, review and publication boundary honest | `review-a.md`, `review-b.md`, `document-freshness-audit.md`, final manifest and backlog entry; no parent-item/main-activation closure claim. |

- [ ] Every live v9 prerequisite and scanner acceptance row passes with named evidence; accepted Slice A and final Slice B reviews both concur.
- [ ] Baseline/lock, source behavior/docstrings and migration bytes are unchanged except the listed test/config/docs work and reasoned annotations.
- [ ] Two local commits have their own successful enforced Windows hooks; applicable skips are reported accurately.
- [ ] Current-state documentation and sole registry agree on **locally verified, unpublished**, or on a precise STOPPED state. Main CI activation remains unclaimed.
- [ ] All deferred obligations retain named backlog custody; no further implementation or scheduling is inferred from this successor's existence.
