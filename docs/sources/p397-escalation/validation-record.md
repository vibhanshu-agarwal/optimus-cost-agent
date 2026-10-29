# #397 escalation validation record

Sanitized evidence for [#397](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/397),
[#432](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/432) and
[ADR-029](../../decisions/ADR-029-accepts-adr-009-rung-2-one-escalation.md). It holds no credential, prompt text,
model output, session or request identifier. Raw logs, screenshots and run scripts are workstation provenance only,
under the operator's handoff folder (`p397-stub/`, `p397-live/` and `sandbox-review-kit/p397-*`); their SHA-256
values are listed so a copy can be checked. All times are UTC.

## Claim

In an interactive Auto session, a recovery episode whose nudge did not help moves the rest of the turn once to the
escalation role's first routable model, with a live notice and price line, and still ends at the Continue/Stop
check-in. A turn already on that model has no step, and the check-in says so. Two defects found while testing are
fixed: loop-detection novelty counts the bytes a read returned (#432, `3272ce0`), and the agent waits out the
Gateway's upstream budget, with every upstream attempt bounded (`07e7ed2`, with `bfee317` and `5630fe9` after the
Checkpoint C reviews).

## Heads

| Head | What it adds | Committed |
|---|---|---|
| `a358d58` | the escalation (plan r5), before the merge with `main` | 2026-10-28 02:40 |
| `ca66625` | the merge of `origin/main` (PRs #434, #435) | 2026-10-28 16:16 |
| `3272ce0` | #432: novelty by the bytes returned | 2026-10-29 11:02 |
| `07e7ed2` | the host/Gateway timing contract (#397 Z2) | 2026-10-29 13:22 |
| `bfee317` | a retry the budget refuses after its backoff is reported once, as final (Fable, Checkpoint C) | 2026-10-29 14:56 |
| `6ca4bee` | the two inventory fixes the `07e7ed2` full suite found (no product change) | 2026-10-29 15:09 |
| `5630fe9` | a retried failure is reported only after its retry is dispatched (Codex, Checkpoint C) | 2026-10-29 15:29 |

## Test runs

| Run | Head and tree | Command | Result | Log SHA-256 |
|---|---|---|---|---|
| Windows full suite with coverage | `a358d58` (tree `c805784`), clean before and after | `python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json … --coverage-json …` (PowerShell, Windows 11, Python 3.14) | 10,245 passed, 50 skipped, 101 deselected, 0 failed. Coverage: optimus 90.4276%, context_engine 95.9243%, optimus_model_policy 94.6816% (floors 80%, pass); evidence_handoff 68.4810% and aggregate 86.5137% (informational) (run `20261028T024039-39760-971a22`) | `be8a0d32f79e14643a5fdedadf8d1b1a9ba6b0126f705cb55a57b7bab353e758` |
| Windows full suite with coverage | `ca66625` (tree `7104fba`), clean before and after | as above | **10,417 passed, 52 skipped, 106 deselected, 0 failed.** Coverage: optimus 90.2135%, context_engine 95.9243%, optimus_model_policy 94.6816% (floors 80%, pass); evidence_handoff 68.4810% and aggregate 86.4924% (informational) (run `20261028T162114-36360-389801`) | log `9ccc50b132ecc042882abc0b9fff6c140b2539a7be2bc9816b9d4d03b5606eed`; report `b0fa8cc599586bca14d7db9402d4e4a904d7c60799f69bc785229518852d5afe` |
| Targeted, #432 | the content committed as `3272ce0`, per its commit message | loops, the planning loop, escalation, loop check-in, debug trace, spec protocol and plan987 live evidence | 449 passed | console only; no log retained |
| Targeted, the timing contract, provisional | uncommitted working tree on `3272ce0`, before `07e7ed2` was committed; one comment-wording change (Codex round 4) followed | optimus_gateway with its integration tests, the gateway client, model_policy, security, bootstrap and main wiring, the planning loop and its recovery, loops, Auto escalation end to end, the failure diagnostics and every README-reading test | 3,052 passed, 5 skipped, 22 deselected (run `20261029T131432-48560-e2d33e`) | `283a5a7a113c9e8e26467a9cecebe3b589890faeb7d9a4d6c256bf21795b999d` |
| Windows full suite with coverage | `07e7ed2` (tree `b370407`), clean before and after | as above | 10,462 passed, 52 skipped, 106 deselected, **2 failed**, both inventory checks: `test_test_profiles.py::test_the_platform_tag_follows_its_maintained_signal` (the reset-host test in `tests/unit/optimus_gateway/test_server.py` reads `sys.platform`, but the file was not tagged `platform`) and `test_verify_plan996_logging_surfaces.py::test_checked_in_manifest_covers_current_surface_inventory` (two manifest entries still named the functions that `07e7ed2` moved the `OpenerDirector.open` calls out of). Both fixed in `6ca4bee`. Coverage: optimus 90.3160%, context_engine 95.9243%, optimus_model_policy 94.7038% (floors 80%, pass); evidence_handoff 68.4810% and aggregate 86.5944% (informational) (run `20261029T135539-41632-3ca8f7`) | log `ca3164a1adeabe1c35725f32c27f0c0b93553a2b8e91f42a8f1f6ef0e15a241d`; report `4959c8ae6c35e0524280c0ede6bd823a8ac283fda33a1694c7578b816e94b2ca` |
| Targeted, Fable finding 6 | the content committed as `bfee317` | `tests/unit/optimus_gateway` and `tests/integration/optimus_gateway`; ruff and mypy | 729 passed | console only; no log retained |
| Targeted, the inventory fix | `6ca4bee`'s content, staged on `bfee317` | `test_test_profiles.py`, `test_verify_plan996_logging_surfaces.py`, `test_test_profile_selection.py` and the two real-socket tests the manifest now cites | 195 passed (run `20261029T150711-53516-9b2246`) | console only; no log retained |
| Targeted, Codex finding 1 | the content committed as `5630fe9` | `tests/unit/optimus_gateway`, `tests/integration/optimus_gateway`, `test_verify_plan996_logging_surfaces.py` and `test_test_profiles.py`; ruff and mypy | 852 passed, 22 deselected (run `20261029T152540-46964-148cb5`) | console only; no log retained |
| Linux PR CI | the PR's final head | GitHub Actions, `clean-environment-recheck` | owed: a merge gate of the PR | — |

`bfee317` and `5630fe9` (one helper and its tests) and `6ca4bee` (one test tag and two manifest entries) follow the
`07e7ed2` full suite. Each was checked by its targeted run, and the helper also by revert checks. No further full
suite was run; Linux CI covers the final head.

## Revert checks

Each part of a fix was undone in turn, with the targeted tests run against it.

| Fix | Parts | Result | Log SHA-256 |
|---|---|---|---|
| #432 (`3272ce0`) | 5 | all 5 caught | `1e30823218d256f3f7a1ba4141dab3b3f1e9ed2f6aa0b1438925dcd4227c511d` |
| The timing contract (`07e7ed2`), round 4 | 26 | 25 caught; one survived: no test covered the refusal of a TLS handshake that finishes after the deadline | `8cd223b202fdf2629e0c2a6d960a87a3ab53d178c9960632bbc7f67f4e566a50` |
| The same, after the late-handshake test was added | the two late-connection parts | both caught, so all 26 parts are caught | `a6ed1fad24bccf56da06c13ba0b98314189c06f2ce5041641f1907344d4665e7` |
| Fable finding 6 (`bfee317`) | 1: the post-backoff budget recheck removed. `bfee317`'s commit message names a different mutation, restoring the old report order; `5630fe9`'s message corrects it | caught | console only |
| The retry reporting (`5630fe9`, which replaces `bfee317`'s order) | 5: a retry reported before it is dispatched; no post-backoff recheck; no report for a retry that then succeeds; none for one that fails again; no terminal report | all 5 caught | `b40690e3cb97604aa0e595ba1419be4c9f32b983e08b82abb21b36bdc9443304` |

## Live evidence

The scripted runs use a local stub provider under plan r6's evidence exception S1, which the operator accepted by
running its approval. They cost nothing. The real-model runs use OpenRouter through the Gateway.

| Case | Head | Date | Provider | What the records show | Record SHA-256 |
|---|---|---|---|---|---|
| A1′, acpx | `ca66625` | 2026-10-28 | scripted | Easy turn on the easy model; two repeated-read detections; the escalation granted at step 4 to the escalation model, with the notice and price line delivered; a third detection at step 7; the check-in answered Stop | analysis `63ebc04aa063c88cda2b7dad068d3bde58c3f1e701281e1f3f00126a2457772c`; acpx output `a5c6b276d5259df41d93a0ababd99ca13aaef0c35f93a50b8d36d2652340b075` |
| U2, Zed, attempt 1 | `ca66625` | 2026-10-29 | scripted | Granted at step 4; Stop at the step-7 check-in; terminated | verification `757fcafe33e99aab8915bce6c02b262b2694eebad52a19cd5cfa1f39052c0444`; stub requests `ca23a9336b5e0c9f41efd80329dc0a0d41ec556e75448343ce259c88d4aae347` |
| U5, U4, U3, Zed, attempt 2 | `ca66625` | 2026-10-29 | scripted | U5: granted at step 4; cancelled while the step-7 check-in was pending, recorded as a stop; terminated. U4: a complex turn already on the escalation model; no target at step 4; Stop at the check-in; terminated. U3: granted at step 4; Continue at the step-7 check-in; completed after the separate plan approval | verification `915594d75b35461eda221f9636b4d1f64a3841dadcafc7d00004b5da031f3a05`; stub requests `406503e7b4eb2ea2b74b779e730aca07d27b6dae8ad614a05073a68657b6ec85` |
| U1, Z1, Zed | `3272ce0` | 2026-10-29 | real | Easy, answered by the rules with high confidence; the easy model; the notice delivered; completed | verification `cefc387aed8454cf920e0714c968e0bf1750988179a2cfd56c61de0c15147b90` (all four real cases) |
| Z2, Zed | `3272ce0` | 2026-10-29 | real | The classifier predicted medium with low confidence, so the turn was routed one tier up, to complex, as the case requires; the notice delivered. The third planning request then lost a reply the provider had billed (USD 0.0401, 10,372 output tokens) to the agent's 30 s Gateway timeout, while the Gateway's attempt allowed 60 s; the turn stopped as `PLANNING_GATEWAY_COST_UNKNOWN`, and the Gateway logged a traceback on the closed socket. Fixed in `07e7ed2`; Z2 was not re-run | finding `a8302fa04f06fd230fbd3c737f5a988289e4019b70b9054e6357ed6cd8fd4631` |
| Z3, Zed | `07e7ed2` | 2026-10-29 | real | Complex, answered by the rules with high confidence; the notice delivered. The planning reply arrived after 51.0 s with its cost known (USD 0.0043, no unknown-cost attempt), which the 30 s timeout would have lost. The model then refused the task on its first turn (`PLANNING_MODEL_REFUSED`), which is model behaviour | as U1 |

Part 2 ran in two attempts because the stub provider's two-hour lifetime ended after U2; attempt 2 ran the remaining
chain with a longer lifetime. The verifiers check each case against its records, not the screen alone: the tier, the
model, one escalation or none, its target, one check-in and the final state (scripted), or the tier, the model for
that tier, the delivered notice and one settled run (real). Verifier SHA-256: Part 2
`fda0a3df1dfff99a0f75d7de59f6a0c6b35d8ea4dedc7e2a7a20997cf38c72eb`, Part 1
`7e915aa8ad309bac0a4e89896546634a5b64f96665e1826d4038ceb41e7d59c7`.

Part 1 logs: debug trace `c6b87097a4014b1fadb1aaaef2a622f2cdfca4e188c7ad13d43182125c54dbb3`, Gateway log
`65ce74327ec9b5d2128cbca4ae951e79d725d82e715a4acbcefa4ece3fa49ac3`, telemetry
`ead2e97410dc69c472d2b771771a493c26ee657a375efed05f86e55c9b620f05`, launch audit
`513b5fc86ea71d8a12c50f8d8e1accf6ce90d8b9cbf43571e471c1271adf1988`.

## Spend

Known spend for #397's paid runs: USD 0.0587, under the USD 0.30 threshold the operator released. The easy model
USD 0.0105; the complex and escalation model USD 0.0482, which includes Z2's lost reply; an entry under the
sanitized label `unrecognized` USD 0.00002 (spend record `67f9e735ac92c3e14d34584f174921fd92c566b7fe81c12acce7b73b133d6d67`).

## Reviews

- Checkpoint B: Fable, then Codex CLI.
- #432: Codex CLI round 1, approve with changes; its one finding applied.
- The timing contract: Codex CLI rounds 1–4 (rework three times, then approve with changes), each posted verbatim on
  #397.
- Checkpoint C: Fable 5.1 on `07e7ed2`, `3272ce0` and the ADR-029 draft, approve with changes. Findings 1–4 (the ADR
  text) and 6–7 (`bfee317`) are applied. Finding 5, an optional simplification, is not. Finding 8 belongs to the HLD/LLD
  successor PR.
- Checkpoint C: Codex CLI (gpt-6.1-sol, high, read-only) on the code since its round 4, the ADR, this record, the
  indexes and the freshness audit, approve with changes (review SHA-256
  `aaa2ceb8b992353888264f8706feb7c8c7c9fa6a9d07561d0c7758a7a6422535`). Finding 1 (an observer could delay a retry
  past its dispatch-time budget check) is fixed in `5630fe9`; findings 2 (option (c)'s wording) and 3 (this record's
  revert-check entry) are applied. It found no further stale doc beyond Fable's finding 8.
- Codex follow-up 1, on `5630fe9` and these docs: approve. It accepted the disclosed gap: an interrupt that is not an
  `Exception` can lose a held retry report.
- All three Checkpoint C reviews are posted verbatim on #397.

## Still owed in #397

- a real model getting stuck enough to escalate (plan r6, S3);
- prompt cancellation during an in-flight Gateway call;
- an end-to-end deadline on the Gateway's own processing;
- the HLD v2.23 / LLD v2.46 successors, as a docs PR.
