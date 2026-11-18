# Pyscn evaluation for Optimus issue #332

**Decision: decline pyscn for the evaluated second-opinion use.** The qualified eight-file scan returned seven unique clone pairs and no dead-code findings at the recorded minimum severity. Three of the seven clone/dead-code rows corroborated already accepted work. No reviewed row established a distinct actionable class. Both conditions for recommending manual second opinion in the [evaluated plan](../plans/archive/hardening-analysis-oracle-evaluation.md) therefore failed. The separate complexity ranking is descriptive. [Issue #332](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/332) owns the evaluation disposition.

## Reproduction and qualification

The [evidence manifest](2026-11-18-issue332-pyscn-evaluation-evidence.yaml) has the pinned Git commit/tree, eight source blob and byte hashes, Task 13 inputs, exact scanner recipe and ranked source rows. Export the eight blobs into their repo-relative paths under an owned read-only input directory using git cat-file blob. Do not copy a working tree or include any other source. The manifest's source was verified against the Git objects and against the export after the sample run.

Use the pinned existing Linux amd64 image and verified release wheel in the manifest. Create and inspect the three isolated containers in plan order. Retain the named stopped containers and their receipts. The shell commands below describe the steps within each scanner container. Use a fresh private executable tmpfs and network isolation as specified by the plan. From the read-only input root run:

```sh
python -m venv /tmp/issue332-wheel
/tmp/issue332-wheel/bin/python -m pip --isolated install --no-index --no-deps --no-cache-dir --disable-pip-version-check /wheel/pyscn-1.33.2-py3-none-manylinux_2_34_x86_64.whl
/tmp/issue332-wheel/bin/pyscn analyze --select complexity,deadcode,clones --min-complexity 1 --json --no-open --config /inputs/scanner.toml --output /results/report.json src
```

The pre-download check passed as UID/GID 65534. It read the expected control bytes, verified the wheel mount was empty, and confirmed the filesystem type was tmpfs. It observed loopback only, no IPv4 or IPv6 default route, immediate ENETUNREACH for a documentation address, EROFS on both input mounts and the root, a successful owned result write, and direct exit 0 from the copied binary under the private tmpfs. Inspections confirmed all three containers used the same pinned image, network isolation, mount roles, capability settings and bounded temporary filesystem. No application endpoint was contacted.

The pinned wheel was written after preflight and before synthetic controls, as recorded by host UTC file metadata. The installs used the extra offline flag --disable-pip-version-check. The control and sample used independent offline installs with identical verified wheel, native executable and explicit comment-only configuration. The wheel metadata reported Python >=3.8, the manylinux glibc 2.34 baseline, and no runtime dependencies. The installed native program reported v1.33.2 on Linux amd64. The installed binary matched the wheel entry. Control and sample processes each exited 0 within their limit, without a timeout or OOM. Report request sections identified the intended eight paths and explicit config in the sample and supplied per-analyzer counts for all eight files. The interface reported two cognitive-complexity advisories, zero skipped files, zero parser diagnostics and no analyzer errors. Its nested no_open fields were false although the outer recorded invocation supplied --no-open. No open/browser step was requested or observed. Scanner stderr carried ordinary report progress and summary output with no parse or analyzer error diagnostic.

The two-file control found the expected exact cross-file lines 1–99 clone, the unreachable statement on alpha line 103, and cyclomatic score 49 for the repeated shape. The independent short beta function scored 1 and appeared in no clone or unreachable finding. Each file contained the same 48 independent comparisons and result accumulator, followed by the distinct control function. The shared fragment had 343 scanner nodes. The control exceeded three times the default size values in both dimensions and twice the high cyclomatic threshold.

## Findings and limits

| Analysis | Raw result | Reviewed | Unreviewed |
|---|---:|---:|---:|
| Clone | 12 clone fragments, 7 groups, 7 raw pairs, 7 unique path/span pairs | 7 | 0 |
| Dead code | 0 findings at warning-or-higher selection, 177 reported functions, 1,593 blocks | 0 | 0 |
| Complexity | 185 tool rows: 177 actual function definitions and 8 synthetic module rows; separate 51 class scopes | 10 tool rows | 175 tool rows |

Every function definition in the pinned sources had a complexity row at minimum 1. Four rows had the scanner's high risk label, including the function whose cognitive complexity triggered a high label below a cyclomatic score of 20. The two cognitive-complexity advisories are retained in the manifest. They describe high branch load in Gateway evidence ingestion and physical-attempt reconciliation. The ten source-checked hotspots include evidence reconciliation, usage receipt invariants, retry classification and Redis teardown. A complexity score alone establishes no defect. The absence of reported unreachable code in eight files at the selected severity cannot support a repository-wide dead-code or reachability claim.

Of the seven clone/dead-code rows, three met the two-sided corroboration rule, three one-sided Redis matches were indeterminate, one was intentional repetition, and zero added an actionable class. The observed signal fraction was 3/7 (42.9%), below the plan's half threshold. Each emitted clone pair appears once. The raw IDs (1, 2, 3, 6, 11, 12, 14) have gaps in the tool output itself. Grouping by qualified method pair would change the ratio to 3/6. The absence of a distinct actionable class is sufficient to decline under either counting unit. The larger class pair counts once even though it contains four accepted method pairs checked on both sides.

| Historical finding | Observation at the pinned sample |
|---|---|
| T13-FIND-011 | Pair 6 matches both async health-check members. The runtime method has an added absent-client guard. The three one-sided sync-adapter edges are indeterminate and add no distinct remediation. [#346](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/346) |
| T13-FIND-012, 013, 019, 037 | Partial. Pair 14 localizes both ledger classes. Source inspection confirms the accepted cost, record, unit-total and request-lookup members on both sides. The tool emitted one enclosing class pair. [#341](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/341) |
| T13-FIND-018 | Miss. The unchanged fingerprint functions are outside the reported class spans and have no separate pair. Cause unestablished. [#341](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/341) |
| T13-FIND-038 | Exact two-sided pair 1 for the relocated, AST-identical retry delay conversions. The tool output includes this pair despite the generic minimum sizes in the recorded request, so the defaults alone cannot explain other misses. [#347](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/347) |

The adjacent usage settlement and Gateway store files did not exist at the Task 13 source and have zero members in the pinned group index. No new issue was justified. The existing track and optional transfer decision remain with their issue owners. [#316](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/316), [#363](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/363).

The results characterize this bounded corpus, settings, and scan date only. The repository evidence is content-free with respect to source excerpts in scanner output. Raw report bytes, complete receipts and fixture source remain in private task custody. The board's measured-scope row records the original evaluation intake and the child-plan status row links this disposition.

## Executed checklist

The steps below reproduce the adopted v5 checkbox lines. The digest is recorded as adopted_plan_sha256 in the evidence manifest. Checks that require the final artifacts, PR, merge, post-merge CI or tracker readback are accounted for in #332's delivery receipt.

- [x] Recheck open issue, branch overlap, current main, governance and accepted artifacts. Verify the adopted activation labels `handler:codex`, `priority:high`, `difficulty:medium`, `estimate:1d` and keep kind/product and the existing open status. File the new adopted digest and estimate agreement on #332, preserving v3 and its blocked preflight record. Use branch `agent/codex/issue332-pyscn-evaluation` and worktree `C:/worktrees/optimus-cost-agent-worktrees/optimus-cost-agent-wt-codex-issue332`. Keep the planning checkout and other task worktrees untouched. The Windows preflight checkpoint is https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/332#issuecomment-6971163356.

  Evidence or gate: base_commit, historical, adoption_issue_comment

- [x] **Before downloading**, run a bounded isolation control using only the pinned local image and approved scratch. Use `--pull never --platform linux/amd64 --network none --read-only --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 --pids-limit 128 --memory 512m --cpus 2`. Mount only task-owned inputs read-only under `/inputs`, the exact verified wheel directory read-only under `/wheel` (empty at preflight) and owned results read-write under `/results`. Provide the venv and temporary files with exactly `--tmpfs /tmp:rw,exec,nosuid,nodev,size=128m,mode=1777`. This mount exists only inside each task container, enables the intended native binary execution, rules out set-ID and device use, and fits within the 512 MiB container limit. Keep scan inputs and verified wheel read-only and never bind the temporary mount to the host. No Docker socket, shared host paths, Git directories or host credentials are mounted or passed. Use `docker create` with unique names `issue332-pyscn-preflight`, `issue332-pyscn-control` and `issue332-pyscn-sample`; inspect image ID, network mode, read-only root, bind mounts, capabilities, running user, and the exact /tmp flags and size in HostConfig.Tmpfs before starting each container. Start only after the inspection matches. Retain stdout/stderr, exit and post-run inspection in task scratch. Verify exact Python version and glibc ≥2.34, readable input control bytes, denied write to input and root paths, a successful owned result write, only loopback, no default route and immediate network denial for a documentation-only address. Before downloading, verify the effective /tmp mount is tmpfs with nosuid and nodev and without noexec. As UID/GID 65534, copy the existing image's /bin/true into /tmp/issue332-exec-control, set mode 0700, and execute the copy directly (no shell, interpreter or working-directory fallback). Require exit 0 and record the executed path, mount options and result. If execution fails or observations are incomplete, stop before acquisition. Any successful connection, timeout, malformed inspection or unproven mount keeps the issue open. No real service endpoint is contacted by controls. Retain the stopped container(s) and receipts. Use the same reviewed isolation flags and mount topology for each scanner run. If a host change, privilege escalation inside the container, new image, or altered network policy is needed, stop.

  Evidence or gate: isolation, receipts.preflight

- [x] After isolation preflight, download only the exact Linux wheel from [PyPI's pinned file](https://files.pythonhosted.org/packages/dc/b4/1c043da471510241eac564c1ad13f84539a273b7cb90fcb3aff27a5f69b1/pyscn-1.33.2-py3-none-manylinux_2_34_x86_64.whl) to task scratch. Verify its SHA-256 and size before inspecting metadata. Require name/version, platform, compatible Python and no runtime dependencies outside the wheel. Inside the same restricted runtime configuration create an owned `/tmp` venv using the image's Python. Install via the venv interpreter's `python -m pip --isolated install --no-index --no-deps --no-cache-dir <verified-mounted-wheel>`. Verify binary hash, version, help and exact glibc/Python identities. Record config and offline flags. No global install, user environment edits, agent integrations or project lock changes.

  Evidence or gate: scanner, receipts.control, receipts.sample

- [x] Export exactly these public Git blobs, preserving relative paths. Capture a sorted path/blob/SHA-256/line-count manifest before and after, exact container image and wheel, command, platform, CWD and timestamps. Bind only the intended corpus and config beneath /inputs. Only scratch results and private tmpfs are writable. The scanner has no application credentials, worktree or host Git metadata.

  Evidence or gate: corpus, base_tree

- [x] From each corpus root use `pyscn analyze --select complexity,deadcode,clones --min-complexity 1 --json --no-open --config <owned-explicit-config> --output <owned-report> src`. Keep clone and dead-code thresholds at the pinned tool defaults. Require all three analyzers. Record any equivalent version-specific option spelling confirmed by help. Another analysis or change in measurement needs a plan revision. Explicitly verify config discovery and analyzer outputs. No retuning after seeing results. Time limit 10 minutes per scan. Bound preflight to two minutes and each approved scan with an existing command timeout or a task-owned watchdog that stops only the named running container, retains its state and never removes it. Parse diagnostics fail closed. All Windows focused docs checks and normal hooks remain required.

  Evidence or gate: scanner.scan, receipts.control, receipts.sample

- [x] Run the synthetic control separately first. Use two normally named (non-test) files containing identical multi-branch functions at least three times the pinned minimum fragment size. Include an unreachable statement immediately after an unconditional return, a function with complexity at least twice the high threshold, and a separate short, distinctive reachable negative control. Require the expected cross-file pair, exact unreachable location, expected high score and no spurious clone or unreachable classification for the negative control. These fixtures qualify the scanner only. Clean source accounting also requires all expected file counts and exact path sets in the returned analysis (including per-function complexity coverage at reporting threshold 1), zero dropped/extra files, no analyzer failures or parse diagnostics, and parseable sections with all requested analyzers enabled.

  Evidence or gate: control, receipts.control

- [x] Run the real sample once after controls. **Setup, control, isolation or unrelated infrastructure failure** keeps #332 open with the exact reason. **Reproducible-by-evidence tool incompatibility on an intact sample after a successful control run** can support a terminal decline. Require an attributable scanner-specific error on a named matched input or a scan-limit timeout bound to valid controls and intact input, describe what could not be measured, and retain failed/partial output with no finding-rate or cleanliness claim. Unknown failure cannot support closure. No retry-to-green. Do not infer causality merely because the subprocess failed or returned an empty result.

  Evidence or gate: sample, receipts.sample

- [x] For a valid full sample, retain exact raw counts and consolidate clone observations into unordered path/span pairs using normalized repo-relative paths; record raw pair/group counts separately. Map spans to qualified current functions or methods using AST bounds. Only a two-sided match to a confirmed Task 13 member pair counts as corroboration. Intentional and similarity-only partitions are not new findings. One-sided or file-only resemblance is indeterminate. Compare historical file presence and symbol drift at the audit commit. Findings in later source stay outside historical scope unless independent verification establishes useful additional signal on current source. Dead code and complexity have no Task 13 comparison label; assess those directly against the source. Account for hit, miss, partial, or drift for each of the seven selected historical findings. Threshold-size misses are recorded as such only when established.

  Evidence or gate: historical_comparison, triage.clone_rows

- [x] Review at most 30 observations (10 from each analyzer). Rank clone pairs by similarity descending, dead code by severity descending and complexity by score descending. Resolve ties by normalized path, start/end span and raw ID. For each row record exact source location and version, prior ownership/deduplication, decision and reason. Classifications are corroboration, verified additional signal (including a genuinely new class where evidence supports it), noise/intentional repetition, or indeterminate. Record unreviewed counts. Complexity is a hotspot signal rather than a bug determination. Unreachable spans are distinct from unused project-wide code.

  Evidence or gate: triage.ranking, triage.reviewed, triage.unreviewed

- [x] Recommend **manual second opinion** only if there is at least one verified actionable additional class in the reviewed clone/dead-code sample and at least half of reviewed clone/dead-code rows are verified signals. Verified signals are corroboration plus verified additional signals. Denominator includes indeterminate and noise. Complexity is reported separately, and a zero denominator yields decline for the sample. Label the estimate as the result for these top-ranked reviewed rows. All other valid completed outcomes recommend decline. A qualified scanner incompatibility uses the decline path above and reports metrics as unavailable where they were unmeasured.

  Evidence or gate: triage.verified_signal_rows, triage.recommendation

- [x] Map verified actionable remediation to existing owners where applicable. Unvalidated ideas and scanner scores are observations, not follow-ups. If a distinct confirmed actionable gap has no owner, the single future grant includes up to three narrowly scoped issues with `kind:follow-up`, `product:optimus`, `status:open` and the ADR-022 defaults, each natively linked as a sub-issue of #316. Post only proven gaps. An additional ownerless action beyond this bound is a stop and rescope, never silently dropped or counted done. Issue #363 keeps its existing optional transfer decision.

  Evidence or gate: triage.new_issues, historical_comparison

- [ ] **CP2:** Claude verifies the source, tool and command bindings, controls and raw-data denominators, direct source triage, custody and recommendation. Inspect README, docs index, roadmap, backlog, current master plan and linked owners for freshness; include exact candidate filing delta. Before the archive becomes visible on main, publish the technical terminal evaluation acceptance in #332 with its evidence identifiers and review. Distinguish this disposition from the still-open publication/CI gate.

  Evidence or gate: Pending review and issue posting at evidence preparation.

- [ ] Deliver **one PR with six tracked paths**:

  Evidence or gate: Pending published PR and closing acceptance.

- [x] Use the board-owned hardening plan route. The governance test forbids an added backlog registry pointer for this child plan, and the board requires the reserved `hardening-*.md` filename. No plan number, separate registry entry, live child-plan PR, or second archive PR. This fills the existing reserved child plan. Archive first publishing after terminal acceptance preserves the actual plan lifecycle. If current-main policy contradicts this reviewed route, stop before moving any plan.

  Evidence or gate: base_tree and the exact six-path filing. The issue receipt records gate outcomes.

- [x] Run narrow Windows docs checks on `tests/unit/docs/test_plan_directory_hygiene.py`, `test_docs_index.py`, and `test_open_work_pool_hygiene.py` under `tests/unit/docs/` (pytest `--no-cov`), Ruff, and `git diff --check`. Scan all three staged artifacts (report, evidence manifest and archived plan) with the owned interpreter: `uv run --no-sync python -X utf8 tools/local_secret_scan.py --baseline .secrets.baseline <staged-artifact-paths>` and retain exact outcome, size and sanitized paths. Use the existing reviewed YAML precedent for public wheel/source/checksum lines: `docs/superpowers/reports/2026-10-30-ruff-first-tranche-manifest.yaml`. Apply any supported line-local annotation only to a reviewed verified public digest where needed. Run the unchanged scanner on the final files and keep all other checks active. Before publication run `uv run --no-sync python tools/verify_masterplan_impact.py --body-file <draft-PR-body> --changed-files-file <six-path-list> --masterplan docs/superpowers/plans/hardening-runtime-quality-masterplan.md`, using scratch inputs and exact reviewed paths. If that policy or file size requires an exception, stop; no bypass is included. Record protected input identities, selection, actual terminal result and any skips. Hooks use the frozen owned Python dev+memory environment with normal checked-in configuration. A separate local full run is outside scope; required CI supplies full-depth gates.

  Evidence or gate: The #332 technical acceptance receipt records the focused gates and binds them to all six final staged files.

- [ ] Publish one PR with `Refs #332` and exactly `Master-plan impact: updated — HARDENING-TRACK-ANALYSIS-ORACLE`. Record GitHub test SHA/tree, required PR checks and same-dataset full coverage validity. Claude verifies final diff and documentation again immediately before merge on current main. Merge normally only if all gates are valid. Verify the actual merge SHA/tree, its own workflow terminal results, coverage gate and same-dataset validity. If CI failure is beyond this PR's scope, retain evidence and stop at the failing gate.

  Evidence or gate: Pending publication, fresh Claude review and distinct PR / actual-merge CI.

- [ ] Post final post-merge receipt and verbatim Claude records on #332. Remove only its open status label immediately before closing as completed. Verify hosted Done, and refresh the #332 projection in the existing ignored local tracker outside this PR's tracked delivery (no tracked file changes after merge), while retaining dated inventory bytes and previous Done entries. One approved pointer comment on #316 may record child plan completion and retain #363's optional transfer in #363. Leave #316 open and unassigned. No writes to other existing issues besides the expressly granted #316 comment and conditional native sub-issue links.

  Evidence or gate: Pending #332 completion, label readback and both tracker verifications.
