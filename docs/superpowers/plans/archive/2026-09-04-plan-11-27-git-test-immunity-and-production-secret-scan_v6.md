# Plan 11.27 v6 — Production CI Secret Scan Remaining-Work Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task. Claude implements; Codex reviews the plan and candidate. Steps use checkbox (`- [ ]`) syntax for tracking; only fresh passing evidence supports a progress claim.

**Goal:** Complete the still-unstarted Slice B so required CI rejects secrets in every Git-tracked production text file and rejects an empty production inventory, while preserving the existing local hook, baseline, dependencies, runtime behavior and locally committed Slice A.

**Architecture:** Resume the existing independent clone at its reviewed Slice A commit. Add one manual filename-driven production hook and bind CI to a nonempty Git/identify inventory plus that hook. Prove the actual configured command with real subprocess controls on Windows and WSL, apply only the reviewed non-credential source annotations, rehearse in a full-history independent clone, obtain Codex review, and land one final local commit through its own full Windows hook.

**Tech Stack:** Existing locked Python 3.14/dev dependencies; pytest 9.1.1, coverage 7.14.3, pre-commit 4.6.0, detect-secrets 1.5.0, identify 2.6.19; PyYAML, Git Bash, Windows and WSL Ubuntu 24.04. No dependency changes.

**Spec:** This complete remaining-work contract retains the acceptance matrix and exact implementation text from operator-approved v5. Its inputs remain the 2026-09-03 frozen scope, SHA-256 `f5d2b923b280999bb3ac68008b348e4933d59edd692d1b07efd8b5db3a3dad1b`, and reviewer handoff v2, SHA-256 `0b7a6933427bc7565071053e98e774ac2464ddb918e428ed1286216338989e43`.

Input locations: `D:/Projects/Development/Python/optimus-agent-handoff/CODEX-BRIEF-2026-09-03-frozen-secret-scan-scope.md` and `C:/worktrees/optimus-cost-agent-wt-codex-plan-11-26/tmp/static-first-ci-pickup-20260904/reviewer-handoff_v2.md`. Executors read both, the current reviewer checkpoint, and the newest appended/shared-header state in `D:/Projects/Development/Python/optimus-agent-handoff/CURRENT.md` before mutation.

**Status / authority:** Complete v6 successor proposed for technical review and one operator scheduling decision. V5's original 180-minute box stopped after Slice A and expressly forbids reset or expansion, so chat cannot restart that cap. V6 schedules only the remaining Slice B work under a new **120 combined agent-minute** cap beginning at the operator's explicit go. It does not reopen Slice A, enlarge the functional file list, authorize a fresh FU-6 revalidation, or authorize push, PR, merge or installation. Claude implements; Codex authors/reviews.

**Frozen predecessors:** [v5](2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v5.md), SHA-256 `f71006d3eb5662cffa5e8f9619efc83a440d2d92286a03a4ee861bf15fdfbc5a`, remains byte-exact and owns the accepted Slice A history and protocol corrections. V2 SHA-256 `577a1c7e5864d9d5d424f0dbf6ac5bd2b496b2ba809f714cdfe3c4574f641fc1`, v3 SHA-256 `dec4163fb294bfe56805ee6b1d245d25c1904b8424c2e567b90e94bb84168800`, and v4 SHA-256 `6fbb5600d18cfb9d570e68933439a441a12b674732d0fc384ae3e9e906400c83` also remain byte-exact at their review locations. Apply the established mechanical path-relocation proof before archiving any frozen predecessor. Until then their transitional custody remains registered; do not rewrite approved prose or relative links.

### Accepted Slice A prerequisite — read-only in v6

Candidate `C:/worktrees/optimus-cost-agent-wt-claude-ci-production`, branch `agent/claude/ci-production-secret-scan`, is an independent clone. Local commit `c1989985171c3054916732f1306d5ffc85d5b094` has parent `5ea8f8f71548eb05a8562a10e98667e3d2061c4d` and tree `258406df199720d19dbdd1f2640567f4f9aca4a8`, equal to the approved rehearsal. It changes exactly `tests/conftest.py`, `tests/unit/acp/test_stdio_ndjson.py`, and `tests/unit/tools/test_git_env_immunity.py`; reviewed raw hashes are `540decf8869143984ece18ec99fabb626d34c3ba43af1c65d08b75bcefbf5b08`, `87403e00b42a295b8ddc0820d56ba05818398b25c9546f220c7e2da25e31e585`, and `ba5a5329dcf5936fe004fed8dbb3a6addb196a4ac0f420dc165261df4b764619`.

The actual commit log, SHA-256 `cdf3d458daa906051a7c4c97caf5b2e511958275e66251ec19ac9467ae5ddea1`, records eight applicable hooks Passed and YAML/TOML Skipped. No FU-6 hit occurred. The hook-created coverage database is externally sealed at SHA-256 `da133c6b12c6780bbdc4a768a25c635ac8aa921110c67627d19e540f4d469a4e`; Codex independently derived TOTAL 13497 / 1456 missed / 3522 branches / 609 partial / **86.23%** from that external copy without rerunning tests. The report hashes to `b25b579584acee5ffffd3fd6693c5d0b91dca78efeb514d0de5a4a55d7c9f76f`. All 35 entries in external manifest SHA-256 `6522ecf5d80f0cecbd2956085026ea95c2ad9d918ffae1f3fab993a9569a29c8` match. The separate 86.08% figure belongs to the successful rehearsal. One original PATH-setup log remains irrecoverable and operator-accepted as an explicit gap; do not recreate or relabel it.

Candidate and shared Git config were clean/current at the v6 drafting check; no tag, push, PR, merge or installation exists for this lane. Task 0 rechecks live state. Slice A is an immutable prerequisite here: do not amend, rebase, cherry-pick, rerun or restage it merely to begin v6. A relevant mismatch stops for review.

## Global Constraints

- Scope classification: multi-file Slice B changeset, limited to the seven functional files and listed current-state/governance documents below. Slice A is a committed prerequisite and receives no v6 mutation. Codex authors/reviews only; Claude performs implementation after specific v6 approval.
- Bound candidate parent is local Slice A commit `c1989985171c3054916732f1306d5ffc85d5b094`; bound main base remains `5ea8f8f71548eb05a8562a10e98667e3d2061c4d`. These are local-state pins, not remote-freshness claims. Task 0 rechecks main and the already-created branch before resumption; relevant drift stops for review, never a silent transplant or rebase.
- Target: `C:/worktrees/optimus-cost-agent-wt-claude-ci-production`, branch `agent/claude/ci-production-secret-scan`. It is an independent clone, not a linked worktree. The explicit isolation decision overrides the usual linked-worktree default; the contributor naming convention remains intact.
- Preserve the parked `D:/Projects/Development/Python/optimus-cost-agent-wt-codex-ci-production`: staged conftest/immunity test and unstaged Gateway diagnostic are evidence, not input to copy wholesale. Preserve the accepted sandbox at `0071b424c185fb45badb7e75be610ba44b9cfd0e`.
- Hard cap: **120 new combined agent minutes**, beginning only at the operator's explicit v6 go and covering Task 0 pickup, implementation, review, verification, rehearsal and the final local commit. Allocate 10 minutes to Task 0, 45 to Task 2, 25 to Task 3, and 40 to Task 4. Count both agents' active work; record relay idle separately and never double-spend concurrent time. This is a separately authorized remaining-work box, not a reset or reinterpretation of v5's exhausted 180-minute box. Stop before a mandatory gate cannot fit; no partial-success claim or verification compression.
- Main `.secrets.baseline` **SHA-256 of raw Git blob contents** stays `89eb6f47e9a1279ff6b9dad5f12e53a221914a16e0eabd873108bd7001397d71`; the same hash domain for `uv.lock` stays `f1caae185d41b02de2bf9a1cc4970e2517278c8a12b3a4728dd71fc2d826a097`. These are not Git object IDs or raw working-tree-file pins. Use the binary method below. Do not import the sandbox's one-entry baseline.
- No broad baseline regeneration, detector/filter weakening, new dependencies, local-hook coverage change, Ruff rule change, or production runtime behavior change. Four production files receive only the reviewed non-credential annotations below.
- Full default Windows commit hooks remain mandatory, with the existing marker exclusions and coverage threshold of at least 80%. No bypass, marker narrowing, retry loop, timeout widening to hide a failure, or Linux-only landing to avoid a Windows failure.
- Slice A's three-file prerequisite is already committed and may not be modified or restaged by v6. RED safety probes operate only on disposable repositories.
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

Record both `git_blob_sha256` and `working_tree_sha256` in the manifest. For each member of `pins`, require index bytes from `git show :PATH` to equal the bound-base bytes; after the final commit require `git show HEAD:PATH` to equal them too. Separately require `Path(path).read_bytes() == working_tree_start[path]` throughout that checkout's run. Each scanner fixture records its own actual input bytes before scanning and requires exact equality after every invocation; the primary oracle below continues to enforce this raw-byte check. Do not normalize a scanner's mutation away.

The existing main checkout's baseline currently hashes to `1ebd1b22a4b4372aa7a5fce820b76bd44e1cd9affe6332297dce3525e8a4577a` as a raw file (127 CRLF line endings), while its raw blob has the pin above. The review checkout's raw file matches the LF blob. `uv.lock` matches its pin in both inspected checkouts. Current `.gitattributes` requests `eol=lf`; these observations do not assert what every new checkout will produce. A raw-file/blob mismatch prompts attribute/diff inspection, not an automatic drift STOP or a file rewrite. An actual tracked-content difference still stops.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| code/state | Slice A commit `c1989985`, exact reviewed tree and externally sealed evidence exist | yes | Claude custody; Codex review | Verified at v6 drafting. Task 0 rechecks live bytes; drift is genuinely hard pending review. |
| code/state | Existing independent candidate clone and branch remain clean at Slice A | yes | Operator machine state; Claude | Verified at v6 drafting. Missing/conflicting identity is genuinely hard; do not recreate, rebase or repurpose silently. |
| code/state | Bound main baseline, lockfile, hook config and seven Slice B source/config files exist | yes | Codex review | Read from the pinned Git objects and live candidate. No runtime-branch transplant is required. |
| evidence | Slice A custody, runner control and the operator-accepted missing-log disposition are sealed | yes | Claude custody; Codex review | Thirty-five manifest entries match. The accepted original setup-log gap stays disclosed; never recreate it. |
| tooling/binaries | Windows locked environment and installed full hook work at Slice A HEAD | yes | Operator machine state; Claude | The actual Slice A commit hook ran at 17:55-17:58 UTC. Task 0 rechecks identities; unavailable tools are genuinely hard under this box and do not authorize reinstall/shared-cache repair. |
| tooling/binaries | Separate WSL locked environment and pre-commit 4.6.0 classifier interfaces are available | yes | Operator machine state; Claude | Prior WSL focused gates and locked interfaces were verified. Task 0 rechecks exact versions before dependent tests; a mismatch is genuinely hard pending review. |
| evidence | Fresh external Slice B evidence and rehearsal destinations are absent | yes | Operator machine state; Claude | Verified at drafting: `D:/Projects/Development/Python/optimus-ci-production-evidence-slice-b-20260905` and `C:/Users/pc/AppData/Local/Temp/claude/plan1127-v6-slice-b-rehearsal` do not exist. Task 0 rechecks; an existing destination stops rather than being reused or deleted. |
| services | Required dependencies for Slice B | yes | Claude | No Redis, Gateway, PostgreSQL, GUI or paid service is required. Real local Git/pre-commit/scanner subprocesses still run. |
| credentials/authority | Approve this v6 contract and its new 120-minute remaining-work box | no | Operator | Merely unauthorized until explicit approval after Claude's technical review. No provider credential is required. |
| human interaction | Codex review of the final Slice B diff/evidence before commit | no | Codex | Genuinely absent but schedulable inside Task 4 and the cap. No GUI ceremony is required. |
| cost | Paid model/Gateway calls | yes | Operator | None required. Agent time is the only planned cost. |
| revalidation | Authority for a new FU-6 hit | no | Operator | Merely unauthorized and not needed unless a hit occurs; any hit stops pending a fresh written per-hit P1. |
| publication | Push, PR, merge and installation | no | Operator | Merely unauthorized and explicitly excluded; not prerequisites for local delivery. |

Every live prerequisite is rechecked in Task 0 before dependent work. An unexpected failure yields STOPPED with fresh external evidence, never inferred success, a new clone, an environment repair or expanded investigation.

## File Scope and Commit Boundary

All implementation paths are relative to the existing candidate clone. No Slice A file and no other implementation file may change.

| Class | File | Exact responsibility |
|---|---|---|
| B | `.pre-commit-config.yaml` | Add one manual production CI hook; existing local hooks unchanged. |
| B | `.github/workflows/guardrails.yml` | Replace the directory-only CI command with the required inventory check and new hook invocation. |
| B | `tests/unit/guardrails/test_ci_parity.py` | Real configured-command regression, selection and nonempty-boundary controls; retain empty-baseline policy. |
| B | `src/evidence_handoff_runtime/migrations.py` | Annotate only the three recomputed SQL integrity hashes. |
| B | `src/optimus_gateway/observability.py` | Annotate only the four redaction labels, with unchanged AST. |
| B | `src/optimus/acp/launch_policy.py` | Annotate the enum label and synthetic URI text; preserve the docstring value and full AST. |
| B | `src/optimus/acp/local_gateway_secrets.py` | Annotate only the two keyring lookup names. |
| B docs | `README.md` | Describe the production CI boundary accurately, without claiming repository-wide or local-hook repair. |
| B docs | `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Sole registry/custody; record local delivery, exclusions and later publication gate without closing the parent work. |
| B docs | `docs/superpowers/plans/2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v6.md` | Add the exact operator-approved v6 execution contract. |
| Frozen custody | Plan 11.27 v2, v3, v4 and v5 at their current root paths | Add byte-exact approved predecessor records and keep their Blocked transitional registry rows. Do not edit or move them without the mechanical Git-blob relocation proof. |
| Frozen custody | `docs/superpowers/plans/archive/2026-09-03-plan-11-27-git-test-immunity-and-production-secret-scan.md` | Add the byte-exact stopped scratch predecessor already located in the flat archive. |

The designated ignored reviewer checkpoint stays at `docs/superpowers/reviews/plan-11-27-review-checkpoints.md` and is never staged. Raw evidence, reports, scripts, rehearsals, copied trees and scan-bearing caches stay outside every tested tree and are never staged. The unrelated parked `tests/unit/optimus_gateway/test_server.py` diagnostic and parked lane remain untouched. This package neither diagnoses nor closes FU-6 or FU-7.

## Task 0 — Revalidate the Existing Slice A Lane (10 minutes)

**Consumes:** approved v6, local Slice A commit, sealed external evidence and existing locked tools. **Produces:** a fresh external resume manifest and a go/STOP decision before Slice B mutation.

- [ ] Read v6 approval, the review checkpoint and newest shared `CURRENT.md` state. Start one new 120-minute combined-work clock at the operator's explicit v6 go; record both agents' active attribution and relay idle separately. Do not carry unused v5 time forward or charge pre-go v6 drafting/review against a fictitious running box.
- [ ] Verify candidate branch `agent/claude/ci-production-secret-scan` is clean at `c1989985171c3054916732f1306d5ffc85d5b094`, parent `5ea8f8f71548eb05a8562a10e98667e3d2061c4d`, tree `258406df199720d19dbdd1f2640567f4f9aca4a8`, exactly one commit beyond base and no tag. Verify the three Slice A raw hashes stated above; any mismatch stops without reset, checkout, rebase or recommit.
- [ ] Reconfirm the destination is the same independent clone with contained Git/common directories, no alternates/shared object links, installed hook and isolated caches. Verify the shared main config hash `ae6059069cc62fde0eb237ecc9c6c0277974ff257b362c7ad596a5d35c651446`; preserve the parked lane and accepted sandbox without mutation.
- [ ] Verify all 35 Slice A manifest entries, including external coverage data/report and the accepted missing-log disposition. Require absent, then create `D:/Projects/Development/Python/optimus-ci-production-evidence-slice-b-20260905`; every attempt gets a distinct file and the manifest covers the whole directory without an extension filter. Do not rerun Slice A tests or its commit hook.
- [ ] Bind current Windows and WSL executable/version identities to the locked setup. Confirm pre-commit 4.6.0's `Classifier.from_config` and `pre_commit.repository.all_hooks` interfaces used below. Do not reinstall, repair the shared cache or change dependencies merely because this is a pickup; unavailable or incompatible tooling stops.
- [ ] Verify `.secrets.baseline` and `uv.lock` in both Git-blob and working-tree domains using the exact method below. Confirm the seven functional Slice B files match `c1989985` before RED. Record elapsed/remaining budget; proceed only if Task 2 plus its mandatory evidence can fit.

### Accepted Slice A delivery — no v6 execution

Slice A's three files, rehearsal, review, actual commit hook, 86.23% external coverage evidence and clean commit are accepted inputs. V6 performs no Slice A checkbox, test, edit, staging, commit or tag. The earlier 86.08% rehearsal report remains separate evidence. The single operator-accepted original PATH-log gap remains disclosed and does not authorize substituting new bytes.

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

## Task 4 — Final Review, Full-hook Rehearsal and Local Delivery (40 minutes)

The complete v6 allocation is 10 + 45 + 25 + 40 = 120 combined agent minutes. Task 4 contains the only v6 review, rehearsal and real commit. If the remaining cap cannot fit every mandatory gate, deliver STOPPED evidence and exact remaining work. Do not compress verification, review or custody to force the commit.

- [ ] Give Codex the seven-file functional diff and Task 2/3 evidence. Codex performs the required current-state freshness audit and authors the final sole-backlog update in its reviewer checkout; Claude may edit `README.md` but does not invent plan/backlog prose. Copy the exact approved v6, byte-exact v2-v5 predecessors and archived scratch record from `C:/worktrees/optimus-cost-agent-wt-codex-plan-11-26` into their listed candidate paths. Verify v2-v5/scratch hashes against this plan and v6 against its operator-approved digest recorded in the checkpoint. Keep predecessors at the live root under their Blocked rows because no authoritative Git source blob yet exists for the relocation proof. Never copy the ignored checkpoint, review probes or raw evidence.
- [ ] Require `C:/Users/pc/AppData/Local/Temp/claude/plan1127-v6-slice-b-rehearsal` to be absent. Create the final full-history rehearsal with `git clone --no-local --no-checkout C:/worktrees/optimus-cost-agent-wt-claude-ci-production C:/Users/pc/AppData/Local/Temp/claude/plan1127-v6-slice-b-rehearsal`, then switch it detached to exact parent `c1989985171c3054916732f1306d5ffc85d5b094`. Do not clone uncommitted working-tree state. Strip inherited `GIT_*`; verify both Git directories remain inside the rehearsal, no shallow store, no alternates/shared object links, exact parent/tree equality including tracked ignored IDE files/reports, and availability of every history pin required by unchanged document tests. Do not synthesize a root commit with `git add -A`. Apply only the exact candidate Slice B diff and verify the resulting rehearsal tree equals the candidate's complete proposed tree before testing. Preserve Slice A's existing rehearsal/evidence without rerunning it.
- [ ] Use the same locked tools and unchanged applicable hooks as the candidate. Record resolved Python/pytest/pre-commit and cache paths. When invoking from Git Bash, prepend the POSIX venv path (for this lane, `/c/worktrees/optimus-cost-agent-wt-claude-ci-production/.venv/Scripts`) to PATH; a literal `C:/...` element is split at its colon. Keep raw logs, scripts, copied trees and scan-bearing caches outside all tested roots. Do not add scanner/doc-test exclusions. A setup failure remains a failed attempt with a fresh raw log; classify it before any retry.
- [ ] Rehearse the final Windows commit with the installed unchanged pre-commit hook. Capture command, stdout/stderr, exit code, every applicable hook status and pytest/coverage outcome under the exact Slice B evidence directory. Successful hooks can suppress detailed stdout: preserve the emitted log and coverage database/report, and do not infer counts from another run. For the actual commit process only, set `PYTEST_ADDOPTS="--junitxml=D:/Projects/Development/Python/optimus-ci-production-evidence-slice-b-20260905/b-commit-junit.xml"` in that process's environment; in Git Bash this is the one-command prefix immediately before `git commit`. Do not persist the variable or edit the existing `optimus-pytest-coverage` hook mapping: its `entry: pytest --cov=optimus --cov-branch --cov-report=term-missing` and `pass_filenames: false` remain byte-for-byte unchanged while the separately scoped manual secret-scan hook is added. Verify the JUnit report exists, the existing selection/coverage arguments still ran, and the tracked hook mapping is unchanged. Preserve command, environment and report bytes. Record non-applicable hooks as Skipped. Preserve every failed attempt under a fresh name. Require candidate/rehearsal tree equality and report baseline, lockfile, config and shared Git-state invariance.
- [ ] Codex reviews the exact diff and failure-path controls, not just counts. Before the final commit, Codex also audits every current-state claim this change affects in README, roadmap and backlog, without altering frozen history. Any required out-of-scope current-state repair goes back for a complete successor; do not silently expand the file list.
- [ ] After concurrence, run the actual local commit's own full Windows hook. Do not replace it with rehearsal evidence. A real full-hook failure is a failure even when the rehearsal passed. No additional optional full-suite repetition is required.
- [ ] Stage exactly the seven functional Slice B files, listed documentation, v6 and byte-exact predecessor custody; never stage the ignored checkpoint or raw evidence. Commit `fix: enforce production-only CI secret scanning`. Record actual commit/tree IDs, staged paths, coverage/JUnit hashes, invariant hashes, clean working tree and reviewer concurrence. Preserve both local commits without push, tag, PR, merge or installation. No tag is needed.

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
| Main-based isolated deliverable | Existing Slice A `state-start.json`, commit/coverage artifacts and 35-entry manifest, plus fresh `b-state-start.json` and `state-final.json`: ancestry, exact status, both Git stores, invariant hashes and untouched parked lane/sandbox. |
| Git protection is causal and its negative oracle is portable | Accepted Slice A `a-immunity-red.log`, `a-immunity-green.log`, `a-import-provenance.json`, the four `a-v4-control-*` platform logs and the reviewed source pin; do not recreate them. |
| EOF port preserves sanitization and failure handling | Accepted Slice A `a-eof-port-windows.log`, `a-eof-ordering-old.log`, three `a-eof-oracle-*` logs, WSL affected log and Codex review controls; do not recreate them. |
| Actual CI command rejects secrets and empty sets | `b-configured-command.txt`, `b-windows-controls.log`, `b-wsl-controls.log`, `b-inventory.json`, `b-mutant-controls.json`; real scanner/pre-commit, 0/1/0, exact file/line, empty failure and baseline invariance. |
| Only reviewed non-credential dispositions changed | `b-production-classification.json`, `b-ast-and-sql-equality.json`, candidate diff and invariant hashes. |
| Required commit gates passed | Failed and successful rehearsal logs remain distinct (`a-rehearsal.log` is the historyless failure; `a-rehearsal-clone.log` is the later success), plus `a-commit.log`, `b-rehearsal.log`, `b-commit.log`, `runner-negative-control.log`; explicit exits/statuses, actual tree equality, retained coverage/JUnit outputs and full default Windows selection. |
| Scope, review and publication boundary honest | `review-a.md`, `review-b.md`, `document-freshness-audit.md`, final manifest and backlog entry; no parent-item/main-activation closure claim. |

- [ ] Every live v6 prerequisite and scanner acceptance row passes with named evidence; accepted Slice A and final Slice B reviews both concur.
- [ ] Baseline/lock, source behavior/docstrings and migration bytes are unchanged except the listed test/config/docs work and reasoned annotations.
- [ ] Two local commits have their own successful enforced Windows hooks; applicable skips are reported accurately.
- [ ] Current-state documentation and sole registry agree on **locally verified, unpublished**, or on a precise STOPPED state. Main CI activation remains unclaimed.
- [ ] All deferred obligations retain named backlog custody; no further implementation or scheduling is inferred from this successor's existence.
