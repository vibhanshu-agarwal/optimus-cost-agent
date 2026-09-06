# Plan 11.27 v5 — Git Test Immunity and Production Secret Scan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task. Claude implements; Codex reviews the plan and each candidate. Checkboxes record executed, passing verification only.

**Goal:** Produce a locally verified main-based change that protects commit-time tests, removes the known sanitization-test EOF race, and makes CI reject secrets in every tracked production text file.

**Architecture:** Use an independent clone with its own Git store. The first commit combines the reviewed central Git-environment isolation with a narrow response-before-EOF test port. The second adds a filename-driven production CI hook and empty-inventory check, preserving the existing local hook and main baseline.

**Tech Stack:** Existing locked Python 3.14/dev dependencies; pytest 9.1.1, coverage 7.14.3, pre-commit 4.6.0, detect-secrets 1.5.0, identify 2.6.19; pytest-asyncio, PyYAML, Git Bash, Windows and WSL Ubuntu 24.04. No dependency changes.

**Spec:** The complete acceptance contract is below. Its inputs are the 2026-09-03 frozen secret-scan scope (SHA-256 `f5d2b923b280999bb3ac68008b348e4933d59edd692d1b07efd8b5db3a3dad1b`, in the shared handoff directory) and the accepted 2026-09-04 reviewer handoff v2 (SHA-256 `0b7a6933427bc7565071053e98e774ac2464ddb918e428ed1286216338989e43`). The latter chooses main, an independent clone, an explicit EOF port, and the new-hit stop rule.

Input locations: `D:/Projects/Development/Python/optimus-agent-handoff/CODEX-BRIEF-2026-09-03-frozen-secret-scan-scope.md` and `C:/worktrees/optimus-cost-agent-wt-codex-plan-11-26/tmp/static-first-ci-pickup-20260904/reviewer-handoff_v2.md`. Executors read both and the current reviewer checkpoint before mutation. Read historical Git objects from `D:/Projects/Development/Python/optimus-cost-agent` if absent from the new clone; never integrate the runtime branch to obtain a test function.

**Status / authority:** Complete successor proposed for a single operator decision: adopt the existing one-line portability correction from v4, replace historyless full-hook rehearsals with independent history-preserving clones, and require raw evidence outside every tested tree. Claude technically approved v4 and proceeded; this reviewer conversation contains no separate operator approval of that specific exception. Do not relabel Claude's technical concurrence as operator authorization or retroactively claim the deviation was approved. The original execution go still covers the owned candidate, locked setup and two gated local commits. V5 does not create another time box, enlarge implementation-file scope or authorize publication. Candidate commit concurrence is held until this successor is approved and the evidence gaps below are resolved. Claude implements; Codex reviews.

**Predecessor:** [Preserved Plan 11.27 scheduling draft](archive/2026-09-03-plan-11-27-git-test-immunity-and-production-secret-scan.md), SHA-256 `4900776b5332a061a148b3ad35db9fa2cfe539504c458eb7b5bca48d5a603751`. That stopped scratch draft never became a live registered plan. Its bytes, original scratch copy and failed evidence remain unchanged. This complete successor replaces its execution instructions; it is not an amendment to it or to PR #194.

**Frozen predecessors:** v2 (`2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v2.md`, SHA-256 `577a1c7e5864d9d5d424f0dbf6ac5bd2b496b2ba809f714cdfe3c4574f641fc1`) and the approved v3 (`2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v3.md`, SHA-256 `dec4163fb294bfe56805ee6b1d245d25c1904b8424c2e567b90e94bb84168800`) remain byte-exact at their review locations. V3 is stopped at Task 1, not an alternative way to bypass this correction. V4 is also preserved at `2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v4.md`, SHA-256 `6fbb5600d18cfb9d570e68933439a441a12b674732d0fc384ae3e9e906400c83`. On operator approval, v5 owns execution. Apply the established mechanical path-relocation proof before archiving frozen predecessors; until that proof is available their transitional custody remains explicitly registered Blocked. No approved prose, historical evidence or relative links may be silently rewritten.

### Retained Task 1 portability finding and exact correction

Claude's run started at `2026-09-04T15:52:54Z` in the already authorized clone. The clone still has base `5ea8f8f71548eb05a8562a10e98667e3d2061c4d`, no later commit and exactly the three Slice A candidate files. At the first stop Claude reported Task 0 complete and a 16-minute implementation attribution; subsequent work is charged in addition, as recorded below. Codex independently checked the clone identity/status, exact test source, +26-line central insertion and the existing start-state manifest. These checks do not certify every Task 0 tool/setup claim or complete Slice A.

Claude's affected-file logs report Windows 17 passed and WSL 1 failed / 16 passed. The original bound test's negative case requires `bare = true`; real Linux Git left `bare = false` while writing `name = Probe` into the disposable victim. Codex reproduced this with Linux-native temporary files. This is a portability defect in the negative oracle; the protected full-state equality case passed. No FU-6 hit or commit is reported here.

The sole implementation change from v3 remains this exact replacement at line 105 of `tests/unit/tools/test_git_env_immunity.py`:

```diff
-    assert "bare = true" in victim_config
+    assert after["config"] != before["config"]
```

Keep the existing `assert after != before`, `assert "Probe" in victim_config`, and protected-case `assert after == before` unchanged. Do not use an OS guard, skip WSL or weaken any original EOF/redaction assertion. The reviewed input remains SHA-256 `cd438ad0e78ce6b091fcfeb4eb1530802607be6cbbcbbb28741001aa555a0bee`; the corrected 112-line file must be SHA-256 `ba5a5329dcf5936fe004fed8dbb3a6addb196a4ac0f420dc165261df4b764619`, hashing raw file bytes (LF). Every other byte of that file is unchanged.

Codex's disposable complete-export controls passed on Windows (Python 3.14.4, Git 2.55.0.windows.5) and WSL (Python 3.14.6, Git 2.43.0), both pytest 9.1.1: original 5 pass on Windows / 1 fail + 4 pass on WSL; proposed 5 pass on each; removing central protection fails the full-state equality assertion on each; replacing only the child command's `Probe` identity with `CleanControl` fails the retained identity assertion on each. The latter prevents other Git-init config damage from masking missing identity contamination. Each export contains all 969 archived main files, then the added immunity test; no Git pointer/store is copied. These are focused review controls, not the actual candidate's two-file gate, full Windows hook, rehearsal or commit.

Review artifacts: `C:/worktrees/optimus-cost-agent-wt-codex-plan-11-26/tmp/plan1127-marker-review-r1/`, including the exact proposal `portable-config-marker.diff` (SHA-256 `8da01085ca59589e494317405cc94bb4e49fcbd5cdafa703c0a70f3f32c285cd`), `inputs.json`, `windows-results.json`, `wsl-results.json`, raw per-case logs and `probe_portability.py`. Existing failed runs and original source stay unchanged. The preparer's initial blank-line counting assertion failed before tests or archive/proposal writes; `preparation-failure.json` records that separate setup error and its exact-boundary correction.

Claude moved the retained run artifacts from `C:/worktrees/optimus-cost-agent-wt-claude-ci-production/tmp/ci-production-run-20260904T155254Z/` to `D:/Projects/Development/Python/optimus-ci-production-evidence-20260904T155254Z/`. The old location no longer exists. Preserve the raw bytes at the new location and record the relocation mapping; do not rewrite historical logs to update paths. Reuse verified, correctly attributed evidence only at its actual source hash. The current candidate contains the corrected file, and its two-file Windows/WSL gates have since passed; details and remaining evidence obligations follow.

### Slice A review, protocol repairs and evidence still owed

Codex verified the actual candidate is still uncommitted at the bound base with exactly the three Slice A paths. The history-preserving independent rehearsal at `C:/Users/pc/AppData/Local/Temp/claude/rehearsal-clone` has parent `5ea8f8f71548eb05a8562a10e98667e3d2061c4d`, commit `192fe1d3ae87eebffc1b89bc26673a401d1f6a5e`, tree `258406df199720d19dbdd1f2640567f4f9aca4a8`, and exactly those three changed files. Their committed bytes equal the candidate files; unchanged paths retain the same base content. Both Git stores are contained and independent, without alternates. Hook configuration, installed hook script, baseline and lockfile match. No implementation defect was found in that diff.

Codex independently ran the actual two candidate files: Windows **17 passed**, WSL **17 passed**, with repository Ruff clean. The actual extracted `request_error` AST equals v4's helper and the six original redaction assertions remain unchanged. Six failure-path controls using that actual helper passed without shortening its 2+2-second bounds; the coordinator settled every owned task with zero unobserved loop reports. A real-server Event-barrier control, extracting the same helper, observed `entered -> released -> response -> eof` in both sanitizer modes and preserved response/stderr redaction. Its first invocation lacked the repository pytest configuration and failed before exercising the async body; that output is retained separately from the passing explicit-config invocation.

The retained successful rehearsal log contains **eight applicable hooks Passed, YAML/TOML Skipped**, and the rehearsal commit result. "All ten hooks passed" is incorrect. Reading the retained successful rehearsal coverage database gives **86.08026323520771%**, with no test rerun; the earlier failed historyless run's 86.16% belongs to that failed run only. Codex did not rerun the full hook or infer a passing pytest count from the earlier failed suite.

**Protocol repair 1 — full-hook rehearsals require history.** The one-commit export lacks objects needed by the real documentation gates: `087560a8b2e6b2893004d768a81f55a4a5ea1c35` for the prerequisites diff and `63b5d8f7853c57030426a01776905b0c521f1036` for frozen relocation bytes. Codex confirmed these objects are absent from the failed rehearsal and present in the successful clone. The claim is about a historyless store, not a universal inability to test exported files. A pristine export without any `.git` additionally fails HEAD/check-ignore checks; that is a different, weaker control, not an equivalent one-commit rehearsal. Task 4 now uses a full-history independent clone at the exact slice parent; archive exports remain suitable for isolated controls that do not require history. No check is skipped or weakened.

**Protocol repair 2 — ignore status is not a scan boundary.** `test_plan_directory_hygiene` walks working-tree files directly; its plan-path check does not consult Git ignore rules. The retained failure names a captured path inside the old rehearsal log under candidate `tmp/`; the post-relocation log reports 65 documentation tests passed. Raw logs, scripts, copied trees and scan-bearing cache contents must live outside every tree on which full checks run. Keep only the required ignored reviewer checkpoint in its designated location; write no transcripts, fake path examples or copied code into it. Its contents must themselves satisfy unchanged document gates. Do not solve this by exclusions, allowlists, output rewriting or deleting failed evidence.

**Before commit, seal the remaining evidence.** The submitted folder does not contain the required runner `EXIT=7` negative-control artifact or a separate raw record of the first PATH-resolution failure. This is a statement about the reviewed package, not proof that no transcript exists elsewhere. Recover the original command/output/exit from retained tool/session records where available; give it a fresh immutable name and producer attribution. Supply a relocation/hash manifest and bind the actual required-gate runner to an injected exit-7 command that makes the runner fail. Do not recreate a historical failure and label it the original, or substitute an unrelated toy runner. If original bytes are unavailable, record that precisely and STOP for the operator's evidence disposition; no blanket preservation claim or silent waiver. The later successful rehearsal need not be repeated merely to reformat evidence. Seal its command, tree, log, coverage data/report and known exit outcome without inventing stdout suppressed by pre-commit.

Codex review artifacts are external: `C:/Users/pc/AppData/Local/Temp/codex/p1127-review-a-20260904/`, including `review-state.json`, `candidate.diff`, Windows/WSL affected logs, `probe_actual_helper.py`, `actual-helper-probes.json`, the barrier script/commands/logs and retained-coverage report. Claude's existing response/stderr mutants and original immediate-EOF control remain attributed to Claude. Review/checkpoint records identify the remaining evidence gate; a technical code concurrence alone is not permission to commit.

## Global Constraints

- Scope classification: complete successor adopting the existing exact test-line correction and repairing rehearsal/evidence protocols. No additional implementation file or production behavior changes. Codex authors/reviews only; no further candidate mutation or commit before this successor's specific approval and remaining gates.
- Main base verified locally: `5ea8f8f71548eb05a8562a10e98667e3d2061c4d`. This is not a remote-freshness claim. Task 0 rechecks current main and the already-created branch before resumption; relevant drift stops for review, never a silent transplant.
- Target: `C:/worktrees/optimus-cost-agent-wt-claude-ci-production`, branch `agent/claude/ci-production-secret-scan`. It is an independent clone, not a linked worktree. The explicit isolation decision overrides the usual linked-worktree default; the contributor naming convention remains intact.
- Preserve the parked `D:/Projects/Development/Python/optimus-cost-agent-wt-codex-ci-production`: staged conftest/immunity test and unstaged Gateway diagnostic are evidence, not input to copy wholesale. Preserve the accepted sandbox at `0071b424c185fb45badb7e75be610ba44b9cfd0e`.
- Hard cap: **180 combined agent minutes**, including setup, implementation, review, verification, rehearsals and commits. Track attribution and elapsed time; do not double-spend concurrent time or assume review is free. Stop before a mandatory gate cannot fit. This is the same already-started box, not a new allowance. Charge Claude's initial 16 minutes, all later Claude execution, Codex's approximately 20-minute prior review, this current review/authoring and any other post-go work. Claude's later 61-minute wall-clock report includes relay idle and is not an active-work subtotal. Reconcile attribution before resuming; neither quoted figure is the combined remaining balance. Keep the original start record and record idle relay time separately. No reset or expansion is authorized by this successor.
- Main `.secrets.baseline` **SHA-256 of raw Git blob contents** stays `89eb6f47e9a1279ff6b9dad5f12e53a221914a16e0eabd873108bd7001397d71`; the same hash domain for `uv.lock` stays `f1caae185d41b02de2bf9a1cc4970e2517278c8a12b3a4728dd71fc2d826a097`. These are not Git object IDs or raw working-tree-file pins. Use the binary method below. Do not import the sandbox's one-entry baseline.
- No broad baseline regeneration, detector/filter weakening, new dependencies, local-hook coverage change, Ruff rule change, or production runtime behavior change. Four production files receive only the reviewed non-credential annotations below.
- Full default Windows commit hooks remain mandatory, with the existing marker exclusions and coverage threshold of at least 80%. No bypass, marker narrowing, retry loop, timeout widening to hide a failure, or Linux-only landing to avoid a Windows failure.
- No full-suite baseline run or commit before the three-file prerequisite is present in the candidate. It protects the first hook's own pytest execution. RED safety probes operate only on disposable repositories.
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

Record both `git_blob_sha256` and `working_tree_sha256` in the manifest. Before each commit require index blob bytes (`git show :<path>`) to equal the bound base; after each commit require `git show HEAD:<path>` to equal it too. Separately require `Path(path).read_bytes() == working_tree_start[path]` throughout that checkout's run. Each scanner fixture records its own actual input bytes before scanning and requires exact equality after every invocation; the primary oracle below continues to enforce this raw-byte check. Do not normalize a scanner's mutation away.

The existing main checkout's baseline currently hashes to `1ebd1b22a4b4372aa7a5fce820b76bd44e1cd9affe6332297dce3525e8a4577a` as a raw file (127 CRLF line endings), while its raw blob has the pin above. The review checkout's raw file matches the LF blob. `uv.lock` matches its pin in both inspected checkouts. Current `.gitattributes` requests `eol=lf`; these observations do not assert what every new checkout will produce. A raw-file/blob mismatch prompts attribute/diff inspection, not an automatic drift STOP or a file rewrite. An actual tracked-content difference still stops.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| code/state | Bound main and reviewed source objects exist; response reader/writer helpers already exist on main | yes | Codex review | Read from Git and main source; no runtime transplant is required. |
| code/state | Bound main and existing independent clone/branch match the stopped lane | yes | Claude; operator owns machine state | Codex checked the stopped lane; Task 0 rechecks live identity/status before resuming. Unexpected drift is genuinely hard pending review. |
| code/state | Exact three-file candidate passes focused gates and has a history-preserving rehearsal | yes | Claude, Codex review | Verified as described above; evidence sealing and the actual candidate commit's own hook remain gates. |
| code/state | Full-hook rehearsal resolves the historical objects used by document gates | yes | Claude, Codex review | The existing independent rehearsal contains them; every future rehearsal proves this before its full suite. A historyless export is insufficient. |
| code/state | Raw evidence custody is outside every tested tree | yes | Claude; Codex verifies paths | Existing relocated custody is outside the candidate; maintain this boundary for all fresh outputs. It does not prove old-file hash continuity where no prior digest exists. |
| tooling/binaries | Existing Windows environment still resolves the locked tools and actual hook dependencies | unknown | Operator machine state; Claude setup | Genuinely hard until the original setup record and current executable identities are checked in Task 0. Codex used its Python/pytest for the focused proposal controls; no complete hook-tool claim follows. No redundant reinstall or shared-cache repair. |
| tooling/binaries | Existing isolated locked Linux environment can execute the resumed candidate | unknown | Operator machine state; Claude setup | Genuinely hard until Task 0 binds the original Linux setup to its current executable path/versions. Codex's WSL-native proposal controls used an existing Linux Python, not the Windows venv; they do not certify Claude's entire toolchain. |
| credentials/authority | Original schedule, isolated downloads and two gated local commits | yes | Operator | Already granted on 2026-09-04; no repeat approval is needed. No provider credential is required. |
| credentials/authority | Adopt the existing one-line correction plus the history/custody repairs in this complete successor | no | Operator | Merely unauthorized: specific successor approval remains unrecorded in this conversation. Original clone/setup/gated-local-commit authority and the single cap stand. |
| evidence | Runner failure propagation and first failed-attempt custody are sealed | unknown | Claude, Codex review | Genuinely hard until retained records are located in Task 0; recover rather than replay historical evidence. Missing original bytes requires an explicit disposition, not a preservation claim. |
| services | Required test dependencies for this package | yes | Claude | No live Redis, external Gateway, PostgreSQL, GUI or paid model service is required by the scoped/default-selected gates. Real local subprocesses and test loopback servers still run. |
| human interaction | Independent candidate review before each local commit | no | Codex | Genuinely absent: reviews are obtainable after the evidence exists; included in the cap. No GUI ceremony is required. |
| cost | Paid model/Gateway calls | yes | Operator | None required. Tool downloads and agent time are the only planned costs. |
| revalidation | Authority for a new FU-6 hit | no | Operator | Merely unauthorized: not needed unless a hit occurs; a hit stops this package pending a fresh written, per-hit P1. |
| publication | Push, PR, merge, installation | no | Operator | Merely unauthorized and explicitly excluded; not prerequisites for local delivery. |

Every unknown above is resolved in Task 0 before dependent tests/edits. A failed prerequisite yields STOPPED, not an inferred pass or an expanded investigation.

## File Scope and Commit Boundaries

All paths in this table are relative to the new clone. No other implementation file may change.

| Slice | File | Exact responsibility |
|---|---|---|
| A | `tests/conftest.py` | Exact reviewed +26-line central strip/restore block; preserve main imports and fixtures. |
| A | `tests/unit/tools/test_git_env_immunity.py` | Reviewed 112-line real-process regression, with only the exact line-105 portability replacement above; both input and corrected raw-byte hashes are pinned. |
| A | `tests/unit/acp/test_stdio_ndjson.py` | Only the named sanitization test's local imports, request helper and two request-driving call sites, as specified in Task 1. Existing assertions remain. |
| B | `.pre-commit-config.yaml` | Add one manual production CI hook; existing local hooks unchanged. |
| B | `.github/workflows/guardrails.yml` | Replace the directory-only CI command with required inventory check and new hook invocation. |
| B | `tests/unit/guardrails/test_ci_parity.py` | Real command regression, selection and nonempty-boundary controls; retain empty-baseline policy. |
| B | `src/evidence_handoff_runtime/migrations.py` | Annotate the three recomputed SQL integrity hashes. |
| B | `src/optimus_gateway/observability.py` | Annotate the four redaction labels, with unchanged AST. |
| B | `src/optimus/acp/launch_policy.py` | Annotate enum label and synthetic URI text; preserve docstring value as well as executable AST. |
| B | `src/optimus/acp/local_gateway_secrets.py` | Annotate the two keyring lookup names. |
| B docs | `README.md` | Describe the production CI boundary accurately, without claiming repository-wide or local-hook repair. |
| B docs | `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Sole registry/custody; record local delivery, exclusions and later publication gate without closing parent work. |
| B docs | This complete v5 plan and preserved predecessor records | Register the execution contract and record only verified checkboxes. Relocate an authoritative predecessor only through the established mechanical path-proof gate. No standalone status-only commit. |

The three-file Slice A replaces the old two-file boundary explicitly: the known EOF race can block the very hook needed to land Git isolation. Both prerequisite fixes must therefore be staged in the first real/rehearsal commit. Do not stage the unrelated parked `tests/unit/optimus_gateway/test_server.py` diagnostic. This package neither diagnoses nor closes FU-6 or FU-7.

The designated ignored reviewer checkpoint stays at its required path and is never staged. Fresh raw evidence lives outside every tested tree and is never staged. Keep uncommitted plan/registry copies together outside the rehearsal surface until Slice B; do not erase or amend authority bytes while preparing Slice A. Record old-to-new custody mappings with actual hashes; no log rewriting or retroactive claim of measured pre-move equality.

## Task 0 — Revalidate the Existing Independent Lane at Resume (original 15-minute allocation)

**Consumes:** approved v5, the reviewed but uncommitted candidate, original start manifest, external evidence and accumulated attribution. **Produces:** a fresh resume manifest and a remaining-budget decision. This is a pickup check within the original Task 0 allocation, not a new setup task or permission to restart the clock.

- [ ] Read the reviewer checkpoint, original frozen inputs, v5 operator approval and current ledger. Retain original UTC start and existing logs. Reconcile Claude/Codex work already charged against the single 180-minute cap before another implementation action.
- [ ] Verify main and candidate HEAD are both `5ea8f8f71548eb05a8562a10e98667e3d2061c4d`; candidate branch is `agent/claude/ci-production-secret-scan`, with no later commit and exactly modified `tests/conftest.py`, modified `tests/unit/acp/test_stdio_ndjson.py`, and untracked `tests/unit/tools/test_git_env_immunity.py`. An unexpected change stops for review; do not reset, restage, delete or overwrite it.
- [ ] Require the existing destination `C:/worktrees/optimus-cost-agent-wt-claude-ci-production` to be the same independent clone described in `state-start.json`: real `.git` directory, both Git-directory identities contained, no alternates. Its existence is expected and authorized. Do not clone again or switch/recreate branches. Missing or conflicting identity stops; this exception applies only to this exact already-owned destination.
- [ ] At this pickup verify the already-corrected candidate, without reapplying it. Require raw file SHA-256 values: conftest `540decf8869143984ece18ec99fabb626d34c3ba43af1c65d08b75bcefbf5b08`; stdio test `87403e00b42a295b8ddc0820d56ba05818398b25c9546f220c7e2da25e31e585`; corrected immunity test `ba5a5329dcf5936fe004fed8dbb3a6addb196a4ac0f420dc165261df4b764619`. A mismatch prompts read-only inspection before mutation. Compare main config with `ae6059069cc62fde0eb237ecc9c6c0277974ff257b362c7ad596a5d35c651446`, and candidate config/index/HEAD/refs plus parked-lane/sandbox state against the recorded stop. Keep baseline/lock checks in both hash domains exactly as above.
- [ ] Bind the original successful `uv sync --frozen --extra dev` setup records to current Windows and separate Linux executable paths/versions, and confirm the installed candidate hook and isolated caches. Resolve the tooling unknowns here, before dependent work. Do not rebuild environments or rerun setup merely because this is a successor. Missing evidence or unavailable locked tools stops under the same budget and no-shared-cache-repair rule.
- [ ] Resolve the remaining evidence unknown before dependent commit work: locate original failed-attempt records, seal the external custody mapping and hashes, and prove the actual required-gate runner propagates the injected exit 7. Preserve all earlier bytes and STOP if required original evidence is unavailable without a disposition. Write a fresh resume/attribution manifest outside tested trees; bind current passing artifacts to producer, exact commands, hashes, platforms and exits. Do not rerun an unprotected full suite or mark a checkbox from narration.

## Task 1 — Three-file Prerequisite, RED/GREEN and First Commit (40 minutes plus review/gates budget)

**Consumes:** isolated lane and reviewed runtime source. **Produces:** central Git protection and a sanitization test that receives its response before issuing EOF. No production interface changes.

### A1. Bound Git-immunity extraction and exact portability correction

- [ ] Extract the new test from `git show c69fd48646645a487b2a9521db8a92c22e536f3a:tests/unit/tools/test_git_env_immunity.py`; require SHA-256 `cd438ad0e78ce6b091fcfeb4eb1530802607be6cbbcbbb28741001aa555a0bee`. Never copy the current parked working tree wholesale. At this pickup verify the original object as input and the corrected file at its separate pin; never overwrite the corrected candidate with the original.
- [ ] Preserve and verify the original five-case Windows RED in the complete isolated main export before central hooks: **1 failed / 4 passed**, failing the positive victim-equality assertion, with damage confined to the disposable victim. Retain its original source hash and actual imported conftest path. The original-file WSL marker failure is separate evidence, not valid RED for missing protection. Setup/import failure is never RED evidence.
- [ ] Verify the already-inserted exact +26-line block from `_INHERITED_GIT_ENV` through `pytest_sessionfinish` against the bound source; do not insert it twice. Keep main's imports, fixtures and other helpers byte-identical. In particular, do not port `sync_await`, `caller_loop_submit` or WP-27 runtime helpers.

The copied functions have these exact interfaces and operations (retain the reviewed docstrings in the actual extraction):

```python
_INHERITED_GIT_ENV: dict[str, str] = {}

def pytest_sessionstart(session: pytest.Session) -> None:
    for key in [name for name in os.environ if name.startswith("GIT_")]:
        _INHERITED_GIT_ENV[key] = os.environ.pop(key)

def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    os.environ.update(_INHERITED_GIT_ENV)
    _INHERITED_GIT_ENV.clear()
```

- [ ] Verify the existing +26 block and original Windows GREEN rather than reapplying them. Verify the already-applied line-105 replacement specified above against the original input SHA-256; require corrected raw-file SHA-256 `ba5a5329dcf5936fe004fed8dbb3a6addb196a4ac0f420dc165261df4b764619` and exactly 112 lines. All other bytes remain identical to the source.
- [ ] Require all five corrected cases to pass on both platforms, retaining full protected-state equality, explicit unprotected config-hash inequality and the `Probe` assertion. In isolated controls, removal of central protection must fail the positive equality assertion and replacement of the child's identity must fail the negative identity assertion on both OSes. The bound Codex review controls above are reusable after script/input/log verification; the actual candidate still owes A2's two-file gate. Verify +26/+112, both original/corrected test hashes, Git-directory containment and unchanged real shared state. Keep original failure, proposal-control and actual candidate logs separately.

### A2. Explicit main-based EOF port

Bound source: the function `test_serve_ndjson_sanitizes_request_processing_response_and_stderr` at `c69fd48646645a487b2a9521db8a92c22e536f3a`, also present in sandbox `0071b42`. Main already contains `InteractiveLineReader` and `MemoryLineWriter` in `tests/integration/acp/test_server_stream.py`; read/use them without modifying that file.

Preserve both sanitizer modes, IDs 1 and 2, the raised secret-shaped canary, the response/error assertions and both stderr-redaction assertions. Replace immediate BytesIO EOF with the following nested helper and local import. This is a **reviewed-port proposal with one explicit adaptation**, not a claim of byte-identical cherry-picking: server settlement uses `asyncio.wait`, so cancellation resistance cannot defeat the helper's join deadline. The response wait is cooperative/Event-based and may retain `wait_for`.

```python
    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter

    async def request_error(request_id):
        reader, writer = InteractiveLineReader(), MemoryLineWriter()
        serving = None
        primary_error = None
        try:
            serving = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
            await reader.send({"jsonrpc": "2.0", "id": request_id, "method": "session/prompt"})
            return await asyncio.wait_for(writer.wait_for_response(request_id), timeout=2)
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            try:
                try:
                    reader.close()
                finally:
                    if serving is not None:
                        try:
                            done, _ = await asyncio.wait({serving}, timeout=2)
                            if done:
                                assert serving.result() is None
                        finally:
                            if not serving.done():
                                serving.cancel()
                                try:
                                    await asyncio.wait({serving}, timeout=2)
                                finally:
                                    cause = None
                                    if serving.done():
                                        state = "settled after cancellation"
                                        if not serving.cancelled():
                                            cause = serving.exception()
                                    else:
                                        state = "still pending after cancellation"
                                        serving.add_done_callback(
                                            lambda task: None if task.cancelled() else task.exception()
                                        )
                                    failure = AssertionError(f"serve_ndjson missed EOF deadline; {state}")
                                    if cause is None:
                                        raise failure
                                    raise failure from cause
            except BaseException as cleanup_error:
                if primary_error is None:
                    raise
                primary_error.add_note(f"EOF cleanup also failed: {type(cleanup_error).__name__}")
```

Use `response = await request_error(1)` and `failed_response = await request_error(2)` at the existing call sites. Remove only their obsolete reader/writer setup and `writer.messages[0]` lookups. Do not rewrite the entire file from the runtime or sandbox branch. The initial two-second values come from the source port. The additional two-second post-cancel wait is cleanup only: after the EOF deadline is missed, late completion never converts the test to a pass.

F1 requires both the bounded second wait and exception retrieval: a completed task that raises during cancellation is observed via `serving.exception()` before the deadline failure is reported. A genuinely resisting task can still be pending after both bounds; the helper reports that explicitly and installs a callback to observe a later exception. This callback does not terminate the task or prove cleanup complete. The negative-control coordinator must retain strong references to all probe tasks, release its resistance latch in `finally`, then join and retrieve their outcomes before closing the loop. If the probe cannot settle even then, its external watchdog terminates only that disposable process and records failure. Never claim a whole-process deadline or leak-free completion from a bounded wait alone.

F2 is addressed by the nested `finally`: failure of `reader.close()` cannot skip task settlement/cancellation. A body/response exception remains the primary raised object if cleanup also fails; it receives a fixed-content note naming only the cleanup exception type. If there was no body exception, cleanup failure propagates. When two cleanup operations themselves fail, Python's chained context remains available. No response or exception-message content is added to the note.

- [ ] In a disposable main-based test probe, introduce an Event barrier at the existing patched request handler. Demonstrate the old immediate-EOF schedule cancels before a response can be observed; record that causal failure, without repeated whole-suite flake hunting. Preserve the historical full-hook EOF failure separately; do not relabel FU-7's historical coverage diagnosis as this new mechanism.
- [ ] Apply exactly the helper/import/call-site port above, preserving the original assertion ASTs. Under the same delayed-handler probe, release the handler after entry acknowledgement; require response observation before reader close for both sanitizer modes. Require the real named test to pass on Windows and WSL.
- [ ] Run two isolated oracle controls against the actual ported test: emit the unsanitized canary through the response, then emit it to stderr. Each must fail its corresponding existing redaction assertion; clean restoration must pass. Independently exercise: normal EOF completion; cancellation settling normally; cancellation raising; resistance beyond both waits; reader-close failure; and a primary response error combined with cleanup failure. Deadline cases always fail, including late normal returns; task exceptions are retrieved; a close failure cannot bypass cancellation; the primary response exception retains identity. The resisting coordinator retains/releases/joins every probe task in `finally` and asserts no pending probe task or unobserved loop-exception report remains. A timeout/collection error is not a successful redaction control.
- [ ] Run the complete two affected test files on both platforms, repository Ruff and `git diff --check`. Preserve all failures. Do not add repetitions to claim FU-7's 25-process coverage gate; that closure remains excluded.

```bash
python -m pytest tests/unit/tools/test_git_env_immunity.py tests/unit/acp/test_stdio_ndjson.py -q
python -m ruff check .
git diff --check
```

- [ ] Rehearse exactly the three-file staged candidate using the complete independent full-history clone protocol in Task 4; the existing equal-tree rehearsal can be reused after evidence sealing and this protocol's approval. Give Codex the exact port diff, source binding, red/green/oracle evidence, platform results and full-hook log. Wait for concurrence.
- [ ] After concurrence, stage exactly the three Slice A files and commit locally with the installed unchanged hook: `test: isolate git fixtures and order sanitization before EOF`. Capture its real full Windows hook output and tree identity. Any new FU-6 hit stops under the rule below; do not proceed to Slice B after a failed commit.

## Task 2 — Production CI Gate and Executable Rejection Controls (45 minutes)

**Consumes:** committed Slice A and unchanged main baseline. **Produces:** a required CI step whose real invocation scans all tracked production text, rejects a nested secret, and rejects an empty inventory.

- [ ] In `tests/unit/guardrails/test_ci_parity.py`, add production-named tests before editing the YAML. Keep all existing parity/baseline assertions. Read the workflow's actual `optimus-check: secret-scan` step and the actual hook configuration. Run the step's `run` string with real Git Bash on Windows and Bash on WSL (`bash -e -o pipefail -c ...`), through the verified locked environment. Do not substitute a test-owned scanner command for the configured one.
- [ ] Fixtures initialize independent Git repositories, stage an exact copy of main's baseline plus selected files, and remove inherited Git variables before the first command. Assert both Git directories are inside the fixture before config or staging. Use an isolated pre-commit cache. Preserve real process return code/stdout/stderr; command logs must not print credentials. Set finite outer subprocess timeouts with failure cleanup of fixture-owned processes.

The primary executable oracle is this sequence; `run_configured_step(repo)` means executing the YAML step as described above, and `write_canary` creates the split-built synthetic value only inside the disposable fixture:

Fixture helper contracts in the existing test module:

- `run_configured_step(repo: Path) -> subprocess.CompletedProcess[str]`: read that fixture's copied workflow with `yaml.safe_load`, select the unique secret-scan step in `clean-environment-recheck`, pass its exact `run` string to the real shell, and return stdout/stderr/status without `check=True`. Use the verified activated environment, a finite subprocess deadline and fixture-owned process cleanup. Assert `uv run python` resolves that environment before relying on scanner output; outside-project uv resolution is not assumed.
- `stage_fixture_files(repo: Path) -> None`: sanitized-environment `git add --all` inside the already verified disposable repository only; require exit 0, including baseline staging.
- `write_canary(path: Path) -> None`: create parent directories and write `"access_key = " + repr("AKIA" + "IOSFODNN7EXAMPLE") + "\n"` as UTF-8. The value is synthetic; no environment credential is read.
- `restore_clean_probe(repo: Path) -> None`: replace the same nested file with `"answer = 42\n"`. The initial fixture contains this exact clean line and an outside-src synthetic canary; neither detector configuration nor baseline changes during the sequence.

```python
baseline_bytes = (repo / ".secrets.baseline").read_bytes()
clean = run_configured_step(repo)
assert clean.returncode == 0
write_canary(repo / "src" / "nested" / "utf8-é" / "probe.py")
stage_fixture_files(repo)
rejected = run_configured_step(repo)
assert rejected.returncode == 1
assert "AWS Access Key" in rejected.stdout + rejected.stderr
assert "src/nested/utf8-é/probe.py:1" in rejected.stdout + rejected.stderr
restore_clean_probe(repo)
stage_fixture_files(repo)
assert run_configured_step(repo).returncode == 0
assert (repo / ".secrets.baseline").read_bytes() == baseline_bytes
```

Use `"AKIA" + "IOSFODNN7EXAMPLE"` as the synthetic fixture value, encoded in a one-line `probe.py` assignment. Normalize path separators/ANSI presentation in captured findings before asserting the exact file and line; do not weaken this to a generic nonzero assertion. Assert baseline byte identity after **each** invocation, including failures. The outside-src canary stays present during the entire 0/1/0 sequence.

- [ ] Execute that oracle against the old workflow: it must fail specifically because the canary invocation returns 0. A missing new hook is a separate structural RED, not the primary directory-no-op proof. Record both.
- [ ] Add exactly this new manual hook under the existing local repository. Preserve all existing hooks byte-for-byte and leave filename passing enabled explicitly:

```yaml
      - id: optimus-secret-scan-ci-production
        name: "optimus-check: secret-scan CI production-only tracked text"
        entry: python -X utf8 -m detect_secrets.pre_commit_hook --baseline .secrets.baseline
        language: system
        types: [text]
        files: ^src/
        stages: [manual]
        pass_filenames: true
```

- [ ] Retain the workflow step name `optimus-check: secret-scan` for existing parity. Replace only its `run` body with this required preflight followed by the hook; no `if`, `continue-on-error`, shell success fallback or empty-set skip:

```yaml
        run: |
          uv run python -X utf8 - <<'PY'
          import os
          import subprocess
          from identify.identify import tags_from_path

          raw = subprocess.check_output(["git", "ls-files", "-z", "--", "src/"])
          paths = [os.fsdecode(path) for path in raw.split(b"\0") if path]
          text_paths = [path for path in paths if "text" in tags_from_path(path)]
          if not text_paths:
              raise SystemExit("No tracked production text files under src/")
          print(f"Tracked production text files: {len(text_paths)}")
          PY
          uv run pre-commit run optimus-secret-scan-ci-production --all-files --hook-stage manual
```

The inventory is derived from the chosen base, not the historical 200/203 Python counts. Do not introduce a new runner subsystem.

- [ ] Implement and pass the acceptance matrix below with real pre-commit/scanner subprocesses. Use fixed fixture names and exact collection assertions, not a permissive regex on a green hook message. Mutation runs modify only independent fixture copies, never the implementation YAML in place.

| Test in the existing parity file | Required proof / deliberate rejection |
|---|---|
| `test_production_secret_scan_rejects_nested_canary_and_restores_clean` | Actual configured step: 0/1/0, expected detector and exact UTF-8 location, unchanged baseline each time, outside-src canary excluded. |
| `test_production_secret_scan_selects_exact_tracked_text` | Compare all filenames selected by real pre-commit's classifier for the real hook to an independently enumerated `git ls-files -z` plus identify-text inventory; include every source package, nested/UTF-8 paths, staged tracked fixtures, binary files, outside-src text and ignored/untracked files. Exact set equality. |
| `test_production_secret_scan_rejects_empty_inventory` | Parameterize no files, only outside-src text, and only binary src files. All fail with the exact preflight message, even though pre-commit alone would skip. |
| `test_production_secret_scan_binding_is_required` | Assert the real job/step remains unconditional and failing, real command is bound to the correct manual hook, filename passing and text/src filters exact, baseline/settings invariant. Reject added skip, `continue-on-error`, wrong hook, disabled filenames or broadened exclusion. |
| `test_production_secret_scan_regression_controls` | Replace the fixture workflow command with the old directory-only form: canary oracle must reject its false exit 0. An unchanged-copy control passes. Each other binding mutant targets one assertion so a second defect cannot mask it. |

For exact selection, use pre-commit 4.6.0's real `Classifier.from_config(tracked_files, config["files"], config["exclude"]).filenames_for_hook(hook)`, with the hook produced from the actual normalized configuration by `pre_commit.repository.all_hooks(config, store)`. Execute this inside a subprocess whose cwd is the fixture, with an isolated `Store` and clean environment. Compare its selected set to the separate Git/identify inventory. The primary scanner rejection test remains public-command based. Verify these installed interfaces in Task 0; an unexpected API/version difference stops rather than substituting a test-owned selection approximation.

## Task 3 — Narrow Production Dispositions and Platform Evidence (25 minutes)

- [ ] Before adding each annotation, reproduce its finding on the chosen main bytes and verify the classification below. Duplicate-suppression can expose an additional occurrence after the first is annotated; iterate to clean, but annotate only the approved occurrences. Any actual/unclassified value or extra scope stops.

| Main occurrence | Permitted annotation and proof |
|---|---|
| `migrations.py` lines 19, 23, 27 | Add `# pragma: allowlist secret` with a SQL-integrity reason. Recompute each named migration's SHA-256 after LF normalization and match the pinned value; migration bytes unchanged. |
| `observability.py` lines 43, 46, 47, 48 | Same-line reasoned pragma: redaction labels, not credentials. Full module AST unchanged. |
| `launch_policy.py` line 28 | Same-line reasoned pragma: enum classification label. |
| `launch_policy.py` line 227 | Pragma for the synthetic URI example. Re-express only `_model_value_has_userinfo`'s docstring as adjacent string literals with the external comment generated below. The **entire AST including the original docstring constant must remain equal**. |
| `local_gateway_secrets.py` lines 18, 19 | Same-line reasoned pragma: keyring service/account names, not retrieved credential values. |

The exact docstring representation is generated from its original value, avoiding hand-transcribed whitespace or Unicode changes. Apply the generated replacement to the docstring statement only, together with the separately listed enum annotation:

```python
tree = ast.parse(source)
function = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "_model_value_has_userinfo")
doc = function.body[0]
parts = ["    ("]
for line in doc.value.value.splitlines(keepends=True):
    reason = ("  # pragma: allowlist secret - synthetic URI example, not a credential"
              if "scheme://user:pass@host" in line else "")
    parts.append("        " + repr(line) + reason)
parts.append("    )")
lines = source.splitlines(keepends=True)
candidate = ("".join(lines[:doc.lineno - 1]) + "\n".join(parts) + "\n"
             + "".join(lines[doc.end_lineno:]))
assert ast.dump(tree, include_attributes=False) == ast.dump(ast.parse(candidate), include_attributes=False)
```

Here `source` is the UTF-8 main file read before editing, and `ast` is Python's standard module. A drafting-time in-memory check of this transformation passed full-module AST equality on the bound main bytes; no source file was written. Execution must still verify the real scanner and the final file. The annotation is an external Python comment; no “comment-only” claim may include changed literal contents. Do not change secret values or baseline bytes to avoid this gate.

- [ ] Obtain a clean full production CI step on Windows and WSL. Retain inventory filename manifests, counts, version information, exit codes, baseline hashes and the primary canary/restored/empty controls. No repository-wide cleanliness claim is permitted.
- [ ] Run the focused unit files below on both OSes; run full-tree Ruff, diff checks and module AST/SQL equality checks. Existing default marker exclusions remain unchanged.

```bash
python -m pytest -q tests/unit/guardrails/test_ci_parity.py \
  tests/unit/evidence_handoff/test_migration_manifest.py \
  tests/unit/optimus_gateway/test_observability_export.py \
  tests/unit/acp/test_launch_policy.py tests/unit/acp/test_local_gateway_secrets.py
python -m ruff check .
git diff --check
```

Update README to say the required CI secret scan rejects an empty inventory and scans Git-tracked text under every `src/` package; the existing local commit hook still receives staged filenames. Main's baseline and all detectors/filters remain unchanged. Do not describe a directory argument exiting 0 as a clean production scan.

## Task 4 — Two Reviews, Full-hook Rehearsals and Local Delivery (55 minutes shared across both slices)

This budget is shared by Task 1's first commit and the final commit; it is not 55 minutes per slice. Total allocation is 15 + 40 + 45 + 25 + 55 = 180 minutes. **For scheduling, plan around STOPPED in Task 2 or 3 as the expected outcome of this box**, with accepted evidence and exact remaining gates preserved. This is a conservative planning assumption, not a measured statistical median or a completion promise. If gate duration consumes the box, deliver STOPPED evidence and remaining work, not a partial success claim. Do not compress verification or reviews to force both commits into the box.

- [ ] Before each real commit, use a fresh, full-history independent clone at that slice's exact parent. Clone with `git clone --no-local --no-checkout <verified-source> <absent-rehearsal-directory>`, then `git -C <rehearsal-directory> switch --detach <parent-commit>`. The source is the owned candidate repository with the required parent committed; do not clone an uncommitted working-tree state. Strip inherited `GIT_*`, verify both Git directories stay within the rehearsal, no shallow store, no alternates/shared object links, exact parent/tree equality including tracked ignored IDE files and reports, and availability of every history pin required by the unchanged doc tests. Do not synthesize a root commit with `git add -A`, since that loses history and can omit tracked ignored files. Apply only the actual slice diff and verify its complete expected tree against the candidate before testing. The existing Slice A rehearsal named above already supplies a real result under this corrected protocol; retain and seal it rather than recreate it for wording compliance.
- [ ] Use the same locked tools and unchanged applicable hooks as the candidate. Record resolved Python/pytest/pre-commit and cache paths. When invoking from Git Bash, prepend the POSIX venv path (for this lane, `/c/worktrees/optimus-cost-agent-wt-claude-ci-production/.venv/Scripts`) to PATH; a literal `C:/...` element is split at its colon. Keep raw logs, scripts, copied trees and scan-bearing caches outside all tested roots. Do not add scanner/doc-test exclusions. A setup failure remains a failed attempt with a fresh raw log; classify it before any retry.
- [ ] Rehearse a real Windows commit with the installed pre-commit hook. Capture command, stdout/stderr, exit code, all applicable hook statuses and the pytest/coverage outcome. Successful pre-commit hooks can suppress their detailed stdout: preserve the actual emitted log and coverage database/report, and do not invent a passing test count from an earlier failure. For the next actual commit, capture pytest's JUnit report to an external fresh path using only its reporting option, without replacing/narrowing the existing selection or coverage arguments; preserve the command/environment and report bytes. A hook skipped because no matching file exists is recorded as skipped, never executed/pass. Preserve failed evidence under fresh names. Require candidate/rehearsal tree equality; report baseline, lockfile, config and shared Git-state invariance.
- [ ] Codex reviews the exact diff and failure-path controls, not just counts. Before the final commit, Codex also audits every current-state claim this change affects in README, roadmap and backlog, without altering frozen history. Any required out-of-scope current-state repair goes back for a complete successor; do not silently expand the file list.
- [ ] After each concurrence, run the actual local commit's own full Windows hook. Do not replace it with rehearsal evidence. A real full-hook failure is a failure even when the rehearsal passed. No additional optional full-suite repetition is required.
- [ ] Stage the final seven functional files plus the listed documentation and mechanically verified predecessor custody, then commit `fix: enforce production-only CI secret scanning`. Record actual commit/tree IDs, expected staged paths, coverage, invariant hashes, clean working tree or explained pre-existing artifacts, and reviewer concurrence. Preserve both local commits without push, tag, PR, merge or installation. No new tag is needed for this interim gate repair.

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
| Main-based isolated deliverable | `state-start.json`, `state-after-a.json`, `state-final.json`: base/ancestry, exact status, both Git stores, invariant hashes, untouched parked lane/sandbox. |
| Git protection is causal and its negative oracle is portable | `a-immunity-red.log`, `a-immunity-green.log`, `a-import-provenance.json`, `a-victim-state.json`; preserve original input evidence, bind corrected-file platform logs and the exact proposal/removal/identity controls listed above. |
| EOF port preserves sanitization and failure handling | `a-eof-port.diff`, `a-eof-ordering.json`, `a-eof-controls.log`, platform-focused logs; both sanitizer modes, assertion AST equality and failure-path outcomes. |
| Actual CI command rejects secrets and empty sets | `b-configured-command.txt`, `b-windows-controls.log`, `b-wsl-controls.log`, `b-inventory.json`, `b-mutant-controls.json`; real scanner/pre-commit, 0/1/0, exact file/line, empty failure and baseline invariance. |
| Only reviewed non-credential dispositions changed | `b-production-classification.json`, `b-ast-and-sql-equality.json`, candidate diff and invariant hashes. |
| Required commit gates passed | Failed and successful rehearsal logs remain distinct (`a-rehearsal.log` is the historyless failure; `a-rehearsal-clone.log` is the later success), plus `a-commit.log`, `b-rehearsal.log`, `b-commit.log`, `runner-negative-control.log`; explicit exits/statuses, actual tree equality, retained coverage/JUnit outputs and full default Windows selection. |
| Scope, review and publication boundary honest | `review-a.md`, `review-b.md`, `document-freshness-audit.md`, final manifest and backlog entry; no parent-item/main-activation closure claim. |

- [ ] All prerequisite and scanner acceptance rows pass with their named evidence; both code-review gates concur.
- [ ] Baseline/lock, source behavior/docstrings and migration bytes are unchanged except the listed test/config/docs work and reasoned annotations.
- [ ] Two local commits have their own successful enforced Windows hooks; applicable skips are reported accurately.
- [ ] Current-state documentation and sole registry agree on **locally verified, unpublished**, or on a precise STOPPED state. Main CI activation remains unclaimed.
- [ ] All deferred obligations retain named backlog custody; no further implementation or scheduling is inferred from this successor's existence.
