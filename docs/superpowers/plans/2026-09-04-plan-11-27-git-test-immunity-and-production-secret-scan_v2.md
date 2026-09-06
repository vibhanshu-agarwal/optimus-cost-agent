# Plan 11.27 v2 — Git Test Immunity and Production Secret Scan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task. Claude implements; Codex reviews the plan and each candidate. Checkboxes record executed, passing verification only.

**Goal:** Produce a locally verified main-based change that protects commit-time tests, removes the known sanitization-test EOF race, and makes CI reject secrets in every tracked production text file.

**Architecture:** Use an independent clone with its own Git store. The first commit combines the reviewed central Git-environment isolation with a narrow response-before-EOF test port. The second adds a filename-driven production CI hook and empty-inventory check, preserving the existing local hook and main baseline.

**Tech Stack:** Existing locked Python 3.14/dev dependencies; pytest 9.1.1, coverage 7.14.3, pre-commit 4.6.0, detect-secrets 1.5.0, identify 2.6.19; pytest-asyncio, PyYAML, Git Bash, Windows and WSL Ubuntu 24.04. No dependency changes.

**Spec:** The complete acceptance contract is below. Its inputs are the 2026-09-03 frozen secret-scan scope (SHA-256 `f5d2b923b280999bb3ac68008b348e4933d59edd692d1b07efd8b5db3a3dad1b`, in the shared handoff directory) and the accepted 2026-09-04 reviewer handoff v2 (SHA-256 `0b7a6933427bc7565071053e98e774ac2464ddb918e428ed1286216338989e43`). The latter chooses main, an independent clone, an explicit EOF port, and the new-hit stop rule.

Input locations: `D:/Projects/Development/Python/optimus-agent-handoff/CODEX-BRIEF-2026-09-03-frozen-secret-scan-scope.md` and `C:/worktrees/optimus-cost-agent-wt-codex-plan-11-26/tmp/static-first-ci-pickup-20260904/reviewer-handoff_v2.md`. Executors read both and the current reviewer checkpoint before mutation. Read historical Git objects from `D:/Projects/Development/Python/optimus-cost-agent` if absent from the new clone; never integrate the runtime branch to obtain a test function.

**Status / authority:** Draft for Claude's technical review and the operator's scheduling decision. This document does not start execution. The operator has already delegated sandbox commit/tag decisions; this new main-based package is scheduled separately. Approval of this complete package includes its two gated local commits and isolated locked-tool setup. Push, PR publication, merge and installation remain withheld. No fresh FU-6 revalidation grant is implied.

**Predecessor:** [Preserved Plan 11.27 scheduling draft](archive/2026-09-03-plan-11-27-git-test-immunity-and-production-secret-scan.md), SHA-256 `4900776b5332a061a148b3ad35db9fa2cfe539504c458eb7b5bca48d5a603751`. That stopped scratch draft never became a live registered plan. Its bytes, original scratch copy and failed evidence remain unchanged. This complete successor replaces its execution instructions; it is not an amendment to it or to PR #194.

## Global Constraints

- Scope classification: a proposed multi-file changeset; drafting changes documentation only. No source/test/config implementation before review and scheduling.
- Main base verified locally: `5ea8f8f71548eb05a8562a10e98667e3d2061c4d`. This is not a remote-freshness claim. Task 0 checks current main before creating a branch; relevant drift stops for review, never a silent transplant.
- Target: `C:/worktrees/optimus-cost-agent-wt-claude-ci-production`, branch `agent/claude/ci-production-secret-scan`. It is an independent clone, not a linked worktree. The explicit isolation decision overrides the usual linked-worktree default; the contributor naming convention remains intact.
- Preserve the parked `D:/Projects/Development/Python/optimus-cost-agent-wt-codex-ci-production`: staged conftest/immunity test and unstaged Gateway diagnostic are evidence, not input to copy wholesale. Preserve the accepted sandbox at `0071b424c185fb45badb7e75be610ba44b9cfd0e`.
- Hard cap: **180 combined agent minutes**, including setup, implementation, review, verification, rehearsals and commits. Track attribution and elapsed time; do not double-spend concurrent time or assume review is free. Stop before a mandatory gate cannot fit. The operator schedules a new box; no earlier allowance silently carries forward.
- Main `.secrets.baseline` SHA-256 stays `89eb6f47e9a1279ff6b9dad5f12e53a221914a16e0eabd873108bd7001397d71`; `uv.lock` stays `f1caae185d41b02de2bf9a1cc4970e2517278c8a12b3a4728dd71fc2d826a097`. Do not import the sandbox's one-entry baseline.
- No broad baseline regeneration, detector/filter weakening, new dependencies, local-hook coverage change, Ruff rule change, or production runtime behavior change. Four production files receive only the reviewed non-credential annotations below.
- Full default Windows commit hooks remain mandatory, with the existing marker exclusions and coverage threshold of at least 80%. No bypass, marker narrowing, retry loop, timeout widening to hide a failure, or Linux-only landing to avoid a Windows failure.
- No full-suite baseline run or commit before the three-file prerequisite is present in the candidate. It protects the first hook's own pytest execution. RED safety probes operate only on disposable repositories.
- Full-suite temporary directories must be short, outside **every** checkout/export. The dedicated immunity-provenance probe may put its child test under its isolated export; that exception does not set the full suite's `--basetemp`.
- Sanitize inherited `GIT_*` before new fixture/setup subprocesses. Before config/index/ref writes, prove both `git rev-parse --absolute-git-dir` and resolved `--git-common-dir` stay inside the intended independent repository. Never copy a linked `.git` pointer or use shared objects/alternates.
- Claude owns shared `CURRENT.md`. Codex owns the ignored `docs/superpowers/reviews/plan-11-27-review-checkpoints.md`. Neither agent treats the other's narration as verification. The checkpoint is local handoff custody, not a required file in a clean Git export.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| code/state | Bound main and reviewed source objects exist; response reader/writer helpers already exist on main | yes | Codex review | Read from Git and main source; no runtime transplant is required. |
| code/state | Latest-main identity and new clone/branch are ready | unknown | Claude; operator owns machine state | Genuinely hard: freshness/access and isolation need Task 0 verification before any dependent work. Destination was absent during drafting. |
| code/state | Three-file prerequisite works on main with the complete Windows hook | no | Claude, Codex review | Genuinely absent: buildable in Task 1, but not yet applied or dynamically verified. |
| tooling/binaries | New Windows environment resolves the locked Python/dev tools, Git Bash, Node and actual hook dependencies | unknown | Operator machine state; Claude setup | Genuinely hard: prior environments exist, but availability/cache integrity for this clone must be established in Task 0. No shared-cache repair belongs here. |
| tooling/binaries | WSL Ubuntu 24.04 and isolated locked Linux environment can execute the same candidate | unknown | Operator machine state; Claude setup | Genuinely hard: check real WSL, Python and package availability in Task 0; use a separate Linux environment, never the Windows venv. |
| credentials/authority | Schedule, isolated downloads and two local commits after review/gates | no | Operator | Merely unauthorized: this draft awaits scheduling; no provider credential is needed. |
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
| A | `tests/unit/tools/test_git_env_immunity.py` | Exact reviewed new 112-line real-process positive/negative regression. |
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
| B docs | This complete v2 plan and its byte-identical archived predecessor | Register the execution contract and record only verified checkboxes. No standalone status-only commit. |

The three-file Slice A replaces the old two-file boundary explicitly: the known EOF race can block the very hook needed to land Git isolation. Both prerequisite fixes must therefore be staged in the first real/rehearsal commit. Do not stage the unrelated parked `tests/unit/optimus_gateway/test_server.py` diagnostic. This package neither diagnoses nor closes FU-6 or FU-7.

Reviewer checkpoints and freshly named raw evidence are ignored custody artifacts, never staged. Keep uncommitted plan/registry copies together outside the rehearsal surface until Slice B; do not erase or amend their authority bytes while preparing Slice A.

## Task 0 — Establish the Independent Lane and Evidence Layout (15 minutes)

**Consumes:** the scheduled plan, current main and read-only source object `c69fd48646645a487b2a9521db8a92c22e536f3a`.
**Produces:** a clean independent main-based clone, verified tools on both OSes, immutable start-state manifest, and a remaining-budget decision.

- [ ] Record schedule/authority and UTC start; read the reviewer checkpoint, frozen inputs and current ledger. Verify source/base hashes and capture parked lane status without changing it.
- [ ] Refresh/read main under the scheduled authority; record the exact commit and changed-path comparison to `5ea8f8f`. If it differs, stop for Codex's base review before applying this bound plan. Do not reset main or reuse the parked branch.
- [ ] In a process with inherited `GIT_*` removed, create the absent destination from main, then create the named branch. The selected clone form is:

```bash
git clone --no-local --branch main \
  D:/Projects/Development/Python/optimus-cost-agent \
  C:/worktrees/optimus-cost-agent-wt-claude-ci-production
git -C C:/worktrees/optimus-cost-agent-wt-claude-ci-production \
  switch -c agent/claude/ci-production-secret-scan
```

`--no-local` prevents hard-linked objects. Verify `.git` is a real directory, common-dir identity, no objects alternates, main ancestry and source-config invariance. If destination already exists, stop; do not delete, overwrite or repurpose it.

- [ ] Create fresh evidence and tool/cache directories for this run. Use isolated `PRE_COMMIT_HOME` and uv cache if the shared cache is damaged; do not repair it. Verify `uv sync --frozen --extra dev` on Windows and WSL with different environments. Record Python, pytest, coverage, pre-commit, detect-secrets, identify, Ruff, Node and Git versions. Pin existing locked versions; setup failure or cache/download overrun stops.
- [ ] Audit both the new clone and original shared Git state: config/index hashes, HEAD, refs, identity, Git directory paths. Main shared config was `ae6059069cc62fde0eb237ecc9c6c0277974ff257b362c7ad596a5d35c651446`; a mismatch is investigated read-only before proceeding, not overwritten from memory.
- [ ] Run `python -m ruff check .` and `git diff --check`, with no fixes. Verify normal temp roots are outside all repositories and child import provenance resolves the intended main-based `tests/conftest.py`. Do not run the unprotected full suite as a baseline. Install the real pre-commit hook only in independent candidate/rehearsal Git stores.

## Task 1 — Three-file Prerequisite, RED/GREEN and First Commit (40 minutes plus review/gates budget)

**Consumes:** isolated lane and reviewed runtime source. **Produces:** central Git protection and a sanitization test that receives its response before issuing EOF. No production interface changes.

### A1. Exact Git-immunity extraction

- [ ] Extract the new test from `git show c69fd48646645a487b2a9521db8a92c22e536f3a:tests/unit/tools/test_git_env_immunity.py`; require SHA-256 `cd438ad0e78ce6b091fcfeb4eb1530802607be6cbbcbbb28741001aa555a0bee`. Never copy the current parked working tree wholesale.
- [ ] Before inserting the central hooks, run the exact five cases in a complete isolated main export. Require the positive victim-equality assertion to fail, with **1 failed / 4 passed**; the no-protection negative control must demonstrate damage only to its disposable victim. Record actual imported conftest path. Setup/import failure is not RED evidence.
- [ ] Insert only the +26-line block from `_INHERITED_GIT_ENV` through `pytest_sessionfinish` in the bound source. Keep main's imports, fixtures and other helpers byte-identical. In particular, do not port `sync_await`, `caller_loop_submit` or WP-27 runtime helpers.

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

- [ ] Repeat the five-case test: all five pass, victim state remains equal in the protected case and differs in the negative case. Verify +26/+112, source hash, both Git-directory identities and unchanged real shared state. Keep RED and GREEN logs separately.

### A2. Explicit main-based EOF port

Bound source: the function `test_serve_ndjson_sanitizes_request_processing_response_and_stderr` at `c69fd48646645a487b2a9521db8a92c22e536f3a`, also present in sandbox `0071b42`. Main already contains `InteractiveLineReader` and `MemoryLineWriter` in `tests/integration/acp/test_server_stream.py`; read/use them without modifying that file.

Preserve both sanitizer modes, IDs 1 and 2, the raised secret-shaped canary, the response/error assertions and both stderr-redaction assertions. Replace immediate BytesIO EOF with the following nested helper and local import. This is a **reviewed-port proposal with one explicit adaptation**, not a claim of byte-identical cherry-picking: server settlement uses `asyncio.wait`, so cancellation resistance cannot defeat the helper's join deadline. The response wait is cooperative/Event-based and may retain `wait_for`.

```python
    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter

    async def request_error(request_id):
        reader, writer = InteractiveLineReader(), MemoryLineWriter()
        serving = None
        try:
            serving = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
            await reader.send({"jsonrpc": "2.0", "id": request_id, "method": "session/prompt"})
            return await asyncio.wait_for(writer.wait_for_response(request_id), timeout=2)
        finally:
            reader.close()
            if serving is not None:
                done, _ = await asyncio.wait({serving}, timeout=2)
                if not done:
                    serving.cancel()
                    raise AssertionError("serve_ndjson did not settle after EOF")
                assert serving.result() is None
```

Use `response = await request_error(1)` and `failed_response = await request_error(2)` at the existing call sites. Remove only their obsolete reader/writer setup and `writer.messages[0]` lookups. Do not rewrite the entire file from the runtime or sandbox branch. The two-second values come from the source port; no existing test deadline is widened. This does not claim a whole-process deadline: run failure probes under an outer process watchdog and terminate only that disposable process if teardown resists cancellation.

- [ ] In a disposable main-based test probe, introduce an Event barrier at the existing patched request handler. Demonstrate the old immediate-EOF schedule cancels before a response can be observed; record that causal failure, without repeated whole-suite flake hunting. Preserve the historical full-hook EOF failure separately; do not relabel FU-7's historical coverage diagnosis as this new mechanism.
- [ ] Apply exactly the helper/import/call-site port above, preserving the original assertion ASTs. Under the same delayed-handler probe, release the handler after entry acknowledgement; require response observation before reader close for both sanitizer modes. Require the real named test to pass on Windows and WSL.
- [ ] Run two isolated oracle controls against the actual ported test: emit the unsanitized canary through the response, then emit it to stderr. Each must fail its corresponding existing redaction assertion; clean restoration must pass. Separately make server settlement raise and resist cancellation: the helper must reject the replacement exception and return an explicit deadline failure; release the resisting probe in its own `finally`. A timeout/collection error is not a successful redaction control.
- [ ] Run the complete two affected test files on both platforms, repository Ruff and `git diff --check`. Preserve all failures. Do not add repetitions to claim FU-7's 25-process coverage gate; that closure remains excluded.

```bash
python -m pytest tests/unit/tools/test_git_env_immunity.py tests/unit/acp/test_stdio_ndjson.py -q
python -m ruff check .
git diff --check
```

- [ ] Rehearse exactly the three-file staged candidate using the complete independent export protocol in Task 4. Give Codex the exact port diff, source binding, red/green/oracle evidence, platform results and full-hook log. Wait for concurrence.
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

This budget is shared by Task 1's first commit and the final commit; it is not 55 minutes per slice. Total allocation is 15 + 40 + 45 + 25 + 55 = 180 minutes. If gate duration consumes the box, deliver STOPPED evidence and remaining work, not a partial success claim.

- [ ] Before each real commit, create a complete `git archive` export of that slice's parent, including reports; initialize an independent Git store, assert Git-directory containment and apply only that slice's actual candidate diff/staged set. Keep evidence fixtures out of config-trust scan discovery; do not skip the scanner. Use the same locked environment and unchanged applicable hooks as the candidate.
- [ ] Rehearse a real Windows commit with the installed pre-commit hook. Capture command, stdout/stderr, exit code, all applicable hook statuses and full pytest/coverage outcome. A hook skipped because no matching file exists is recorded as skipped, never executed/pass. Preserve failed evidence under fresh names. Require candidate/rehearsal tree equality; report baseline, lockfile, config and shared Git-state invariance.
- [ ] Codex reviews the exact diff and failure-path controls, not just counts. Before the final commit, Codex also audits every current-state claim this change affects in README, roadmap and backlog, without altering frozen history. Any required out-of-scope current-state repair goes back for a complete successor; do not silently expand the file list.
- [ ] After each concurrence, run the actual local commit's own full Windows hook. Do not replace it with rehearsal evidence. A real full-hook failure is a failure even when the rehearsal passed. No additional optional full-suite repetition is required.
- [ ] Stage the final seven functional files plus the four listed documentation paths, then commit `fix: enforce production-only CI secret scanning`. Record actual commit/tree IDs, expected staged paths, coverage, invariant hashes, clean working tree or explained pre-existing artifacts, and reviewer concurrence. Preserve both local commits without push, tag, PR, merge or installation. No new tag is needed for this interim gate repair.

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

Use fresh run-named artifacts under ignored evidence custody; list every file's SHA-256, producer, command, platform, base/candidate tree, start/end time and actual exit code. Include a process-runner failing-control: an injected command exiting 7 must make the required-gate runner exit nonzero. Shell redirection, a trailing `cat`, or `tee` must not mask failure. Independent checks may run concurrently only with their own fixtures and all statuses inspected; dependent gates remain sequential.

| Claim | Required named artifact |
|---|---|
| Main-based isolated deliverable | `state-start.json`, `state-after-a.json`, `state-final.json`: base/ancestry, exact status, both Git stores, invariant hashes, untouched parked lane/sandbox. |
| Git protection is causal | `a-immunity-red.log`, `a-immunity-green.log`, `a-import-provenance.json`, `a-victim-state.json`; original positive/negative oracles. |
| EOF port preserves sanitization and failure handling | `a-eof-port.diff`, `a-eof-ordering.json`, `a-eof-controls.log`, platform-focused logs; both sanitizer modes, assertion AST equality and failure-path outcomes. |
| Actual CI command rejects secrets and empty sets | `b-configured-command.txt`, `b-windows-controls.log`, `b-wsl-controls.log`, `b-inventory.json`, `b-mutant-controls.json`; real scanner/pre-commit, 0/1/0, exact file/line, empty failure and baseline invariance. |
| Only reviewed non-credential dispositions changed | `b-production-classification.json`, `b-ast-and-sql-equality.json`, candidate diff and invariant hashes. |
| Required commit gates passed | `a-rehearsal.log`, `a-commit.log`, `b-rehearsal.log`, `b-commit.log`, `runner-negative-control.log`; explicit statuses, actual tree equality and full default Windows coverage. |
| Scope, review and publication boundary honest | `review-a.md`, `review-b.md`, `document-freshness-audit.md`, final manifest and backlog entry; no parent-item/main-activation closure claim. |

- [ ] All prerequisite and scanner acceptance rows pass with their named evidence; both code-review gates concur.
- [ ] Baseline/lock, source behavior/docstrings and migration bytes are unchanged except the listed test/config/docs work and reasoned annotations.
- [ ] Two local commits have their own successful enforced Windows hooks; applicable skips are reported accurately.
- [ ] Current-state documentation and sole registry agree on **locally verified, unpublished**, or on a precise STOPPED state. Main CI activation remains unclaimed.
- [ ] All deferred obligations retain named backlog custody; no implementation or scheduling is inferred from this draft's existence.
