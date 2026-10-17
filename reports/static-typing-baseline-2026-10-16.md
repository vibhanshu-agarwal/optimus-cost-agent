# Fresh current-main Mypy baseline — 2026-10-16

Prepared under the operator's direct approval to create the main-based lane, set up Mypy, and run fresh Windows and WSL baselines. Claude reviews before typing implementation. These are measured failing baselines, not type-clean acceptance.

| Run | Actual execution platform | Python / Mypy | Errors | Error files | Checked source files | Exit |
|---|---|---|---:|---:|---:|---:|
| windows-01 | Native Windows 11 | 3.14.4 / 2.3.1 | 233 | 47 | 226 | 1 |
| wsl-01 | Ubuntu-24.04, real WSL2 Linux | 3.14.4 / 2.3.1 | 224 | 46 | 226 | 1 |

Windows ran 22:37:22–22:37:48 IST; WSL ran 22:39:37–22:40:46 IST, on 2026-10-16. Raw records use UTC. Runs were sequential and used separate `.venv` and `.venv-wsl` environments over identical source/configuration/lock bytes. This Linux result is actual WSL execution, not `--platform linux` on Windows.

## Source and setup

- Branch: `agent/codex/static-typing-port`, based directly on then-current local and GitHub main `c5ea5a1673b957f1e2dd3a09321c6a34ff293880`. No feature-branch ancestry was used.
- `HEAD:src`: `d0d443548d3fc956744efd13764e96aadc0aa02d`. Tracked-source SHA-256 manifest digest: `31c870a54014fc0fbb382d191bf2d84792d34031a6a0e862082c225307781c9c` on both platforms.
- Before and after each run, status contained only the authorized setup changes to `pyproject.toml` and `uv.lock`. All recorded identities matched before/after. Results bind HEAD plus the setup diff, not a clean committed candidate.
- Setup declared `mypy>=2.3,<3` in the existing dev extra and locked 2.3.1. Lock delta is 200 insertions; pyproject adds one line. Existing locked versions did not change, and no package was removed. Added distributions: `mypy` 2.3.1, `mypy-extensions` 1.1.0, `ast-serialize` 0.13.0, `librt` 0.16.0, `pathspec` 1.1.1. Platform resolution markers were added for the new dependency graph.
- Windows uv: 0.11.29; WSL uv: 0.11.31. Both environments synced the same lock with `--frozen --extra dev`; WSL explicitly selected Python 3.14.4. No install or sync occurred during either measured Mypy run.
- No production source, tests, hooks or CI were changed. No pytest/coverage, live dependency, paid call, commit, push, PR, merge, watcher or cleanup ran. Evidence scripts are capture/analysis aids, not project tools or future operating dependencies.

## Exact checking policy

Each environment's own Python executed:

```text
python -m mypy --config-file <retained-baseline.ini> --no-incremental --cache-dir <platform-specific-cache> --no-pretty src
```

The configuration was exactly:

```ini
[mypy]
python_version = 3.14
show_error_codes = True
```

The explicit config prevents inherited user settings. `PYTHONPATH` and `MYPYPATH` were removed from the checker environment. There were no source exclusions, transition overrides, missing-import suppressions, new stubs or strictness changes. The default Mypy policy is not a claim that unannotated function bodies are fully checked. Full absolute argv/interpreter/environment inventories are retained in each run record as private provenance; this report gives the reproducible policy without requiring workstation-specific paths.

## Cross-platform differences

The diagnostic multiset comparison normalizes only path separators and compares file, line, optional column, error code and message. There are 222 common diagnostics, 11 Windows-only diagnostics and two WSL-only diagnostics. These are separate observations, not netted into a parity claim.

| Path | Windows-only observations | WSL-only observations |
|---|---|---|
| `src/optimus/acp/trusted_paths.py` | line 402: missing `pwd.getpwuid`, `os.getuid` | none |
| `src/optimus/acp/launch_gate.py` | line 195: missing `os.getuid` | none |
| `src/evidence_handoff_runtime/lifecycle.py` | lines 533–538: `seek`, `read`, `write`, `flush`, `seek`, `fileno`; lines 551–552: `seek`, `fileno`, on `object` handles | lines 542 and 556: `fileno` on `object` handles |

Source inspection locates these in POSIX account lookup and platform-specific lock/unlock paths. This explains the platform-shaped checker surface; it does not establish runtime failure or runtime acceptance. The full 13 unmatched diagnostics remain in the comparison JSON.

Both platforms report four `import-untyped` diagnostics: `confusable_homoglyphs`, `yaml`, `defusedxml`, and `defusedxml.common`, attributed to three source modules. No stub dependency or import exception was installed to hide them. They need an explicit later disposition before the ratchet list is activated.

## Frozen candidate and first cohort

`bootstrap-exceptions.candidate.json` is a frozen measured candidate containing the union of failing source modules on either platform: **47 exact module names**. SHA-256: `be01fbe4103eb6813ee11d85554dbb53c9caa97347c13b2a4996591b9c03d884`. It is not an approved or installed exception list. The per-module counts are in `module-exceptions.candidate.md`; complete normalized diagnostics are in `diagnostics.json`. Under this measured default policy, 179 of the 226 files have no reported diagnostics on either platform; this is not strict-typing coverage.

The telemetry first cohort has exactly **16 `call-arg` diagnostics on each platform**, all missing the named `trace_id` argument to `TelemetryEvent` factory construction. No other diagnostic is reported in that module. This supports the proposed bounded scope, but its actual closure still requires implementation followed by a fresh check. Preserve the existing before-validator, direct-construction explicit trace IDs, redaction and exact settlement payload contract. Claude's prior targeted #328 real-model/no-mock classification applies only to this cohort.

Held MCP/runtime-dependent modules remain visible in the measured candidate under #329 custody; this report does not authorize their implementation. Later stub/import disposition or source changes must report cleared/new diagnostics separately and create a successor candidate rather than silently editing this snapshot.

## Failed attempt and warnings retained

The first WSL setup attempt exited **127** because a non-login shell could not find `uv`. Its script, stderr, exit and time files remain intact. Attempt 2 used the already verified `/root/.local/bin/uv` and exited 0. Its cross-filesystem hardlink warning fell back to copying; the resulting environment/version/lock identities were captured. There was one measured Mypy run per platform; neither diagnostic result was retried or suppressed.

## Evidence identities and review gate

| Input/output | SHA-256 |
|---|---|
| Measured pyproject | `a4b1ef09715a09d4f1039ba4ca056cba9dd97472a685aee7d0c8b97dae0f4c52` |
| Measured lock | `faa5ac4bd5ea6961cb3e249692b727dffc8a3581697fba5dded1c86a1a0d72bb` |
| Baseline configuration | `9a6d50b8cc5dc03931717b24d330c043b5c74ebca87d2f3a0a3c573ffd815b03` |
| Windows stdout | `98119ddbc6bc0bb762753d845269079ef0d451734c9e997a7a692849404bfad4` |
| WSL stdout | `73a26035d9d81fbb872da4ad4665e3658b7c12fcdba377b01cff0e81dd57956a` |
| Either stderr (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

`windows-01/run.json` and `wsl-01/run.json` retain command, environment, distributions, timing, exits, source hashes and before/after status. Setup logs, the original failed WSL attempt, setup diff, source manifest, raw output, normalized diagnostics and candidate lists remain separately attributable. No historical 191-error main or 203-file sandbox result is relabelled as this baseline.

Claude's requested review: validate source/setup attribution and both actual-platform results; independently recompute diagnostic/candidate counts and hashes; assess the four import diagnostics and 13 platform differences; review whether telemetry remains the smallest complete cohort. Implementation stays held until that review and the next applicable operator approval. No passing product-test or delivery claim is made here.
