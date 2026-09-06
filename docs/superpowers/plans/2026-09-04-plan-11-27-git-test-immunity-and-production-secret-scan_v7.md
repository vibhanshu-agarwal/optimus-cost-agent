# Plan 11.27 v7 — Production CI Secret Scan Remaining-Work Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task. Claude implements; Codex reviews the plan and candidate. Steps use checkbox (`- [ ]`) syntax for tracking; only fresh passing evidence supports a progress claim.

**Goal:** Complete Tasks 3 and 4 of Slice B from its accepted, uncommitted Task 2 delta so required CI rejects secrets in every Git-tracked production text file and rejects an empty production inventory, while preserving the existing local hook, baseline, dependencies, runtime behavior and locally committed Slice A.

**Architecture:** Resume the existing independent clone at its reviewed Slice A commit. Preserve the accepted manual production hook, required nonempty inventory command and regression controls. Apply only the reviewed non-credential source annotations, rehearse in a full-history independent clone, obtain Codex review, and land one final local commit through its own full Windows hook.

**Tech Stack:** Existing locked Python 3.14/dev dependencies; pytest 9.1.1, coverage 7.14.3, pre-commit 4.6.0, detect-secrets 1.5.0, identify 2.6.19; PyYAML, Git Bash, Windows and WSL Ubuntu 24.04. No dependency changes.

**Spec:** This complete remaining-work contract retains v6 Task 3 byte-for-byte and all final-delivery safeguards; it carries accepted Task 2 as a pinned prerequisite rather than a new implementation task. Its inputs remain the 2026-09-03 frozen scope, SHA-256 `f5d2b923b280999bb3ac68008b348e4933d59edd692d1b07efd8b5db3a3dad1b`, and reviewer handoff v2, SHA-256 `0b7a6933427bc7565071053e98e774ac2464ddb918e428ed1286216338989e43`.

Input locations: `D:/Projects/Development/Python/optimus-agent-handoff/CODEX-BRIEF-2026-09-03-frozen-secret-scan-scope.md` and `C:/worktrees/optimus-cost-agent-wt-codex-plan-11-26/tmp/static-first-ci-pickup-20260904/reviewer-handoff_v2.md`. Executors read both, the current reviewer checkpoint, and the newest appended/shared-header state in `D:/Projects/Development/Python/optimus-agent-handoff/CURRENT.md` before mutation.

**Status / authority:** Operator explicitly approved execution, then approved the recommended new 75 combined-agent-minute box: 10 for successor-plan/pickup work, 25 for Task 3 and 40 for Task 4. This v7 records that decision and unchanged remaining technical scope. New-box work begins with this approval turn, recorded start 2026-09-05 06:48:50 UTC (first clock reading 06:49:07); use actual turn-start/end times for attribution. V5 and v6 remain stopped historical boxes: neither is reset and no balance carries forward. Claude implements; Codex authors/reviews. Task 3 may begin after Task 0 succeeds and its complete gate fits. Task 4 requires all 40 minutes and final reviewer concurrence before the actual local commit. No push, PR, merge, installation, tag or fresh FU-6 revalidation.

**Frozen predecessors:** [v6](2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v6.md), SHA-256 `83a8edf069863599830d9274e9073997aebe289490a762f942c6198afa130544`, owns accepted Task 2 and the budget stop before Task 3. Preserve all 34 Task 2 artifacts and the original failed attempts. [v5](2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v5.md), SHA-256 `f71006d3eb5662cffa5e8f9619efc83a440d2d92286a03a4ee861bf15fdfbc5a`, remains byte-exact and owns the accepted Slice A history and protocol corrections. V2 SHA-256 `577a1c7e5864d9d5d424f0dbf6ac5bd2b496b2ba809f714cdfe3c4574f641fc1`, v3 SHA-256 `dec4163fb294bfe56805ee6b1d245d25c1904b8424c2e567b90e94bb84168800`, and v4 SHA-256 `6fbb5600d18cfb9d570e68933439a441a12b674732d0fc384ae3e9e906400c83` also remain byte-exact at their review locations. The archived scratch predecessor SHA-256 is `4900776b5332a061a148b3ad35db9fa2cfe539504c458eb7b5bca48d5a603751`. Apply the established mechanical path-relocation proof before archiving any frozen predecessor. Until then their transitional custody remains registered; do not rewrite approved prose or relative links.

### Accepted Slice A prerequisite — read-only in v7

Candidate `C:/worktrees/optimus-cost-agent-wt-claude-ci-production`, branch `agent/claude/ci-production-secret-scan`, is an independent clone. Local commit `c1989985171c3054916732f1306d5ffc85d5b094` has parent `5ea8f8f71548eb05a8562a10e98667e3d2061c4d` and tree `258406df199720d19dbdd1f2640567f4f9aca4a8`, equal to the approved rehearsal. It changes exactly `tests/conftest.py`, `tests/unit/acp/test_stdio_ndjson.py`, and `tests/unit/tools/test_git_env_immunity.py`; reviewed raw hashes are `540decf8869143984ece18ec99fabb626d34c3ba43af1c65d08b75bcefbf5b08`, `87403e00b42a295b8ddc0820d56ba05818398b25c9546f220c7e2da25e31e585`, and `ba5a5329dcf5936fe004fed8dbb3a6addb196a4ac0f420dc165261df4b764619`.

The actual commit log, SHA-256 `cdf3d458daa906051a7c4c97caf5b2e511958275e66251ec19ac9467ae5ddea1`, records eight applicable hooks Passed and YAML/TOML Skipped. No FU-6 hit occurred. The hook-created coverage database is externally sealed at SHA-256 `da133c6b12c6780bbdc4a768a25c635ac8aa921110c67627d19e540f4d469a4e`; Codex independently derived TOTAL 13497 / 1456 missed / 3522 branches / 609 partial / **86.23%** from that external copy without rerunning tests. The report hashes to `b25b579584acee5ffffd3fd6693c5d0b91dca78efeb514d0de5a4a55d7c9f76f`. All 35 entries in external manifest SHA-256 `6522ecf5d80f0cecbd2956085026ea95c2ad9d918ffae1f3fab993a9569a29c8` match. The separate 86.08% figure belongs to the successful rehearsal. One original PATH-setup log remains irrecoverable and operator-accepted as an explicit gap; do not recreate or relabel it.

At v7 pickup the candidate has the accepted three-file Task 2 delta at Slice A HEAD. Slice A is immutable: do not amend, rebase, cherry-pick, rerun or restage its three files merely to resume. Task 0 verifies live bytes; relevant mismatch stops for review.

## Global Constraints

- Scope classification: multi-file Slice B changeset, limited to the seven functional files and listed current-state/governance documents below. Slice A is a committed prerequisite and receives no v7 mutation. Codex authors/reviews only; Claude performs implementation after specific v7 approval.
- Bound candidate parent is local Slice A commit `c1989985171c3054916732f1306d5ffc85d5b094`; bound main base remains `5ea8f8f71548eb05a8562a10e98667e3d2061c4d`. These are local-state pins, not remote-freshness claims. Task 0 rechecks main and the already-created branch before resumption; relevant drift stops for review, never a silent transplant or rebase.
- Target: `C:/worktrees/optimus-cost-agent-wt-claude-ci-production`, branch `agent/claude/ci-production-secret-scan`. It is an independent clone, not a linked worktree. The explicit isolation decision overrides the usual linked-worktree default; the contributor naming convention remains intact.
- Preserve the parked `D:/Projects/Development/Python/optimus-cost-agent-wt-codex-ci-production`: staged conftest/immunity test and unstaged Gateway diagnostic are evidence, not input to copy wholesale. Preserve the accepted sandbox at `0071b424c185fb45badb7e75be610ba44b9cfd0e`.
- Hard cap: **75 new combined agent minutes**, including this successor-plan drafting/review/pickup (10), Task 3 (25), and Task 4 (40). The operator approved execution and this exact allocation. Record every agent turn start and end including reporting, and sum both agents active time; exclude relay idle, count concurrent agent work separately, and never substitute time-since-go for active use. Do not reset v5/v6 or carry their balances into v7. Stop before a complete mandatory next task cannot fit. Task 4 must not begin below 40 remaining. No partial-success claim or verification compression.
- Main `.secrets.baseline` **SHA-256 of raw Git blob contents** stays `89eb6f47e9a1279ff6b9dad5f12e53a221914a16e0eabd873108bd7001397d71`; the same hash domain for `uv.lock` stays `f1caae185d41b02de2bf9a1cc4970e2517278c8a12b3a4728dd71fc2d826a097`. These are not Git object IDs or raw working-tree-file pins. Use the binary method below. Do not import the sandbox's one-entry baseline.
- No broad baseline regeneration, detector/filter weakening, new dependencies, local-hook coverage change, Ruff rule change, or production runtime behavior change. Four production files receive only the reviewed non-credential annotations below.
- Full default Windows commit hooks remain mandatory, with the existing marker exclusions and coverage threshold of at least 80%. No bypass, marker narrowing, retry loop, timeout widening to hide a failure, or Linux-only landing to avoid a Windows failure.
- Slice A's three-file prerequisite is already committed and may not be modified or restaged by v7. RED safety probes operate only on disposable repositories.
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
| code/state | Slice A commit `c1989985`, exact reviewed tree and externally sealed evidence exist | yes | Claude custody; Codex review | Verified at v7 drafting. Task 0 rechecks live bytes; drift is genuinely hard pending review. |
| code/state | Existing independent candidate clone remains at Slice A with exactly the accepted Task 2 delta | yes | Operator machine state; Claude | HEAD/tree/parent and three-file delta verified during v7 drafting. Missing/conflicting identity is genuinely hard; do not recreate, rebase or repurpose silently. |
| code/state | Bound main baseline, lockfile, hook config and seven Slice B source/config files exist | yes | Codex review | Read from the pinned Git objects and live candidate. No runtime-branch transplant is required. |
| evidence | Slice A custody, runner control and the operator-accepted missing-log disposition are sealed | yes | Claude custody; Codex review | Thirty-five manifest entries match. The accepted original setup-log gap stays disclosed; never recreate it. |
| tooling/binaries | Windows locked environment and installed full hook work at Slice A HEAD | yes | Operator machine state; Claude | The actual Slice A commit hook ran at 17:55-17:58 UTC. Task 0 rechecks identities; unavailable tools are genuinely hard under this box and do not authorize reinstall/shared-cache repair. |
| tooling/binaries | Separate WSL locked environment and pre-commit 4.6.0 classifier interfaces are available | yes | Operator machine state; Claude | Prior WSL focused gates and locked interfaces were verified. Task 0 rechecks exact versions before dependent tests; a mismatch is genuinely hard pending review. |
| evidence | Existing external Slice B custody is intact and fresh rehearsal destination is absent | yes | Operator machine state; Claude | All 34 artifacts were verified at acceptance. Reuse the existing evidence directory additively; never recreate it or overwrite artifacts. V7 rehearsal destination `C:/Users/pc/AppData/Local/Temp/claude/plan1127-v7-slice-b-rehearsal` was checked absent during drafting. Task 0 rechecks; collision stops. |
| services | Required dependencies for Slice B | yes | Claude | No Redis, Gateway, PostgreSQL, GUI or paid service is required. Real local Git/pre-commit/scanner subprocesses still run. |
| credentials/authority | Execution and new 75-minute remaining-work box | yes | Operator | Explicitly approved in the current conversation, including the 10/25/40 allocation. This successor records that authorization without expanding technical scope. No provider credential required. |
| human interaction | Codex review of the final Slice B diff/evidence before commit | no | Codex | Genuinely absent but schedulable inside Task 4 and the cap. No GUI ceremony is required. |
| cost | Paid model/Gateway calls | yes | Operator | None required. Agent time is the only planned cost. |
| revalidation | Authority for a new FU-6 hit | no | Operator | Merely unauthorized and not needed unless a hit occurs; any hit stops pending a fresh written per-hit P1. |
| publication | Push, PR, merge and installation | no | Operator | Merely unauthorized and explicitly excluded; not prerequisites for local delivery. |

Every live prerequisite is rechecked in Task 0 before dependent work. An unexpected failure yields STOPPED with fresh external evidence, never inferred success, a new clone, an environment repair or expanded investigation.

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
| B docs | `docs/superpowers/plans/2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v7.md` | Add the exact operator-approved v7 execution contract. |
| Frozen custody | Plan 11.27 v2, v3, v4, v5 and v6 at their current root paths | Add byte-exact approved predecessor records and keep their Blocked transitional registry rows. Do not edit or move them without the mechanical Git-blob relocation proof. |
| Frozen custody | `docs/superpowers/plans/archive/2026-09-03-plan-11-27-git-test-immunity-and-production-secret-scan.md` | Add the byte-exact stopped scratch predecessor already located in the flat archive. |

The designated ignored reviewer checkpoint stays at `docs/superpowers/reviews/plan-11-27-review-checkpoints.md` and is never staged. Raw evidence, reports, scripts, rehearsals, copied trees and scan-bearing caches stay outside every tested tree and are never staged. The unrelated parked `tests/unit/optimus_gateway/test_server.py` diagnostic and parked lane remain untouched. This package neither diagnoses nor closes FU-6 or FU-7.

## Task 0 — Publish the Successor and Verify Accepted Pickup (10 combined minutes)

**Consumes:** operator approval, frozen v6, accepted Slice A HEAD, accepted uncommitted Task 2 patch and existing evidence. **Produces:** sealed v7 digest in reviewer checkpoint, additive pickup record and go/STOP before Task 3. Codex drafting/review and Claude pickup share these 10 minutes; neither receives a second allocation.

- [ ] Codex publishes this complete v7 and its SHA-256 in the reviewer checkpoint, updates only the sole registry/current-state custody, verifies frozen v6 byte identity and checks the plan/registry. The operator already approved the 75-minute recommendation and execution; no second identical approval is required. If Claude finds substantive contract drift, stop for review rather than expanding scope.
- [ ] Claude reads v7, the checkpoint and shared ledger, records this turn start, then verifies the existing candidate branch `agent/claude/ci-production-secret-scan`, HEAD `c1989985171c3054916732f1306d5ffc85d5b094`, tree `258406df199720d19dbdd1f2640567f4f9aca4a8`, parent/main `5ea8f8f71548eb05a8562a10e98667e3d2061c4d`. No staged files; exactly `.github/workflows/guardrails.yml`, `.pre-commit-config.yaml`, `tests/unit/guardrails/test_ci_parity.py` modified. Preserve all untracked files. Do not recreate, reset or replace a clone/worktree.
- [ ] Compare the entire binary-safe live `git diff --no-ext-diff --binary` output against `D:/Projects/Development/Python/optimus-ci-production-evidence-slice-b-20260905/task2-fix4-functional-diff-20260905T045402Z.patch`: exact bytes and SHA-256 `bff2b1a13689fb0296c8dd82f884b523b6ab95b41f75c4986f6bd332dbbdcbd9`. All other seven-file-scope members still equal HEAD. An unexpected delta stops; do not repair it silently.
- [ ] Verify both Git stores stay inside this independent clone, no alternates/shared objects, installed hook, unchanged shared main `D:/Projects/Development/Python/optimus-cost-agent/.git/config` SHA-256 `ae6059069cc62fde0eb237ecc9c6c0277974ff257b362c7ad596a5d35c651446`. Verify Slice A raw file pins stated above and baseline/lock in both hash domains by the exact method above. Preserve parked lanes.
- [ ] Verify all 34 entries in the existing Slice B manifest, and accepted Slice A 35-entry custody without rerunning its tests. Before extending a manifest preserve its current bytes under a fresh path; manifest the whole directory without extension filters. Keep prior failure/correction artifacts byte-identical. Add fresh timestamped v7 pickup records to this same evidence directory; no evidence recreation or estimated timestamp labels.
- [ ] Recheck installed Windows/WSL runner identities without installation or cache/dependency repair. Accepted Windows Git 2.55.0.windows.5 / uv 0.11.29 and WSL Git 2.43.0 / uv 0.11.31 are platform identities, not drift. Windows uses candidate `.venv`; WSL uses `/root/optimus-ci-venv`, uv `/root/.local/bin/uv`, native temp `/root/tmp`. Preserve invocation-scoped MSYS path-conversion workaround evidence when needed. No new classifier-interface experiment is required: its installed 4.6.0 interfaces have already executed in accepted Task 2.
- [ ] Require the v7 rehearsal destination named in Task 4 absent. Reconcile Codex drafting plus Claude pickup/reporting active minutes against 75. Report exact entry balance and proceed to Task 3 only if its full 25-minute gate and evidence fit. At Task 4 separately require all 40 minutes; never assume the original allocation remains unused.

### Accepted Task 2 — prerequisite, no separate reimplementation or RED rerun

Codex accepted Task 2 at 2026-09-05 06:30:52 UTC. Its exact patch pin above includes the two YAML changes and parity tests. Final logs record Windows 29 passed in 36.30s and WSL 29 passed in 14.07s, with the preceding WSL injected-failure result preserved separately (1 failed / 28 passed). All 34 hashes matched. These are Claude's executions inspected by Codex; do not label them independent Codex reruns.

The accepted contract remains binding:

| Boundary | Accepted invariant retained in Tasks 3/4 |
|---|---|
| Public configured-command oracle | Fixture copy of real YAML `run` executed by Git Bash/Bash with `-e -o pipefail`; pinned venv; clean/canary/restored exits 0/1/0, AWS Access Key detector and exact `src/nested/utf8-é/probe.py:1`, baseline bytes equal after each call, outside-src canary stays excluded. |
| Selection | Real pre-commit 4.6.0 `Classifier.from_config` / `all_hooks` selected set equals independent Git/identify text inventory; five actual packages, nested UTF-8, binary, outside-src, truly untracked and ignored src controls. |
| Empty inventory | No files, outside-src-only text and binary-src-only cases fail with `No tracked production text files under src/`. |
| Binding | Unconditional required job/step; no continue-on-error or success fallback; exact manual hook entry `python -X utf8 -m detect_secrets.pre_commit_hook --baseline .secrets.baseline`, system language, types `[text]`, files `^src/`, stages `[manual]`, explicit filename passing, no broadened exclusion. Ten independent mutants assert their intended message. |
| Failure paths | Bounded process-tree cleanup/reap independent of pipe draining; teardown encloses invocation/expectation. Injected tree-kill failure control, genuine descendant control, isolated common-dir escape rejection after the first check passes, and ordinary linked-worktree rejection. Both Git dirs checked before writes. |
| Causality and custody | Old directory-only command false exit 0 and unchanged-copy control retained; Windows old/new descendant negative-control log retained. Do not run that historical Windows-only probe on POSIX. All original failures/corrections remain. |

Task 3's listed focused test run and Task 4's required full hooks still run against the final candidate. This prerequisite prevents duplicate pickup RED/rehearsal work; it does not waive those mandatory later verifications. Accepted Task 2 files are preserved unless a newly evidenced in-scope defect requires correction and fits the box; such a correction must be reviewed and resealed, not silently substituted.

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

## Task 4 — Final Review, Full-hook Rehearsal and Local Delivery (40 minutes)

The complete v7 allocation is 10 + 25 + 40 = 75 combined agent minutes. Task 4 contains final Slice B review, rehearsal and the actual local commit; drafting/pickup belongs to Task 0. If the remaining cap cannot fit every mandatory gate, deliver STOPPED evidence and exact remaining work. Do not compress verification, review or custody to force the commit.

- [ ] Give Codex the seven-file functional diff and Task 2/3 evidence. Codex performs the required current-state freshness audit and authors the final sole-backlog update in its reviewer checkout; Claude may edit `README.md` but does not invent plan/backlog prose. Copy the exact approved v7, byte-exact v2-v6 predecessors and archived scratch record from `C:/worktrees/optimus-cost-agent-wt-codex-plan-11-26` into their listed candidate paths. Verify v2-v6/scratch hashes against this plan and v7 against its operator-approved digest recorded in the checkpoint. Keep predecessors at the live root under their Blocked rows because the required authoritative Git-source relocation proof is not yet available. Never copy the ignored checkpoint, review probes or raw evidence.
- [ ] Require `C:/Users/pc/AppData/Local/Temp/claude/plan1127-v7-slice-b-rehearsal` to be absent. Create the final full-history rehearsal with `git clone --no-local --no-checkout C:/worktrees/optimus-cost-agent-wt-claude-ci-production C:/Users/pc/AppData/Local/Temp/claude/plan1127-v7-slice-b-rehearsal`, then switch it detached to exact parent `c1989985171c3054916732f1306d5ffc85d5b094`. Do not clone uncommitted working-tree state. Strip inherited `GIT_*`; verify both Git directories remain inside the rehearsal, no shallow store, no alternates/shared object links, exact parent/tree equality including tracked ignored IDE files/reports, and availability of every history pin required by unchanged document tests. Do not synthesize a root commit with `git add -A`. Apply only the exact candidate Slice B diff and verify the resulting rehearsal tree equals the candidate's complete proposed tree before testing. Preserve Slice A's existing rehearsal/evidence without rerunning it.
- [ ] Use the same locked tools and unchanged applicable hooks as the candidate. Record resolved Python/pytest/pre-commit and cache paths. When invoking from Git Bash, prepend the POSIX venv path (for this lane, `/c/worktrees/optimus-cost-agent-wt-claude-ci-production/.venv/Scripts`) to PATH; a literal `C:/...` element is split at its colon. Keep raw logs, scripts, copied trees and scan-bearing caches outside all tested roots. Do not add scanner/doc-test exclusions. A setup failure remains a failed attempt with a fresh raw log; classify it before any retry.
- [ ] Rehearse the final Windows commit with the installed unchanged pre-commit hook. Capture command, stdout/stderr, exit code, every applicable hook status and pytest/coverage outcome under the exact Slice B evidence directory. Successful hooks can suppress detailed stdout: preserve the emitted log and coverage database/report, and do not infer counts from another run. For the actual commit process only, set `PYTEST_ADDOPTS="--junitxml=D:/Projects/Development/Python/optimus-ci-production-evidence-slice-b-20260905/b-commit-junit.xml"` in that process's environment; in Git Bash this is the one-command prefix immediately before `git commit`. Do not persist the variable or edit the existing `optimus-pytest-coverage` hook mapping: its `entry: pytest --cov=optimus --cov-branch --cov-report=term-missing` and `pass_filenames: false` remain byte-for-byte unchanged while the separately scoped manual secret-scan hook is added. Verify the JUnit report exists, the existing selection/coverage arguments still ran, and the tracked hook mapping is unchanged. Preserve command, environment and report bytes. Record non-applicable hooks as Skipped. Preserve every failed attempt under a fresh name. Require candidate/rehearsal tree equality and report baseline, lockfile, config and shared Git-state invariance.
- [ ] Codex reviews the exact diff and failure-path controls, not just counts. Before the final commit, Codex also audits every current-state claim this change affects in README, roadmap and backlog, without altering frozen history. Any required out-of-scope current-state repair goes back for a complete successor; do not silently expand the file list.
- [ ] After concurrence, run the actual local commit's own full Windows hook. Do not replace it with rehearsal evidence. A real full-hook failure is a failure even when the rehearsal passed. No additional optional full-suite repetition is required.
- [ ] Stage exactly the seven functional Slice B files, listed documentation, v7 and byte-exact predecessor custody; never stage the ignored checkpoint or raw evidence. Commit `fix: enforce production-only CI secret scanning`. Record actual commit/tree IDs, staged paths, coverage/JUnit hashes, invariant hashes, clean working tree and reviewer concurrence. Preserve both local commits without push, tag, PR, merge or installation. No tag is needed.

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

- [ ] Every live v7 prerequisite and scanner acceptance row passes with named evidence; accepted Slice A and final Slice B reviews both concur.
- [ ] Baseline/lock, source behavior/docstrings and migration bytes are unchanged except the listed test/config/docs work and reasoned annotations.
- [ ] Two local commits have their own successful enforced Windows hooks; applicable skips are reported accurately.
- [ ] Current-state documentation and sole registry agree on **locally verified, unpublished**, or on a precise STOPPED state. Main CI activation remains unclaimed.
- [ ] All deferred obligations retain named backlog custody; no further implementation or scheduling is inferred from this successor's existence.
