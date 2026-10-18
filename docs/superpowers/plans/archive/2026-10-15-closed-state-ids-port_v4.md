# Closed State ID Lifecycle Port Implementation Plan

> Proposed complete v4 documentation-correction successor for #357, 2026-10-15 (Asia/Calcutta). Pending operator approval and Claude review. Preserve exact approved v2 and reviewed v3 bytes. Behavior, production/test scope, reviewer cadence and coverage gates stay unchanged. This successor corrects prerequisite syntax, records the already granted local-commit authority, and proposes unchanged archival of v3 with registry/index reconciliation. Publication, issue metadata, services, cleanup and private-memory writes remain separately gated.

**Goal:** remove the extra retained session-ID string left by each failed MCP-bearing `session/new` request that reaches `remove`, preserving close-once and exception behavior. This does not unload successful sessions or fix the larger process-lifetime growth of `_sessions`.

**Architecture:** adapt only the unconditional cleanup in `InMemoryAcpSpecSessionStore.remove(session_id: str) -> None` to current main. Keep the existing store as the lifecycle owner; discard the removed ID in `finally`, without changing `_close_state_once`, `close_all`, adapter failure handling or public interfaces.

**Tech stack:** repository-pinned Python >=3.14, uv frozen dev environment, pytest/pytest-asyncio, current product-coverage and run-validity tools, Ruff and normal hooks; canonical native Windows full coverage/validity gate and Linux PR CI. A separate frozen local WSL/Linux run is optional unless a platform-shaped change or failure makes alternate-OS reproduction necessary. No new dependency.

**Spec:** the bounded contract below; the remaining-portfolio entry in [the archived main port plan](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/9e7626df3eff9e9a643650dd7af406ba723c120d/docs/superpowers/plans/archive/MAIN-PORT-PLAN-v5.md); sandbox `MAIN-PORT-PLAN-v2.md` P3 and `MCP-CLOSED-STATE-IDS-CLASS-RECORD.md` at the pinned source below. Sandbox-only APIs and failure wrappers are historical context, not the main contract.

## Source snapshot and requirement

Read-only verification on 2026-10-15 established:

| Source | Identity and finding |
|---|---|
| Live GitHub main and local `origin/main` | `9e7626df3eff9e9a643650dd7af406ba723c120d`. The primary checkout's local `main` is older (`d23a0e0`); do not branch from that stale ref. |
| Sandbox | Clean `experiment/cross-cutting-sandbox`, HEAD `e521264e9f0fae08a8b1e42887ce2e0ae8bd1c2c`; describe `sandbox-main7-ported-register-docs-20261014-0-ge521264`; post-tag commit range empty. The latest tag checkpoints documentation, not a fresh code acceptance. |
| Accepted source class | Annotated, local-only `sandbox-mcp-closed-state-ids` -> `e5b29d76b77e62ef79a758287f459ec67e0011e0`, tree `269dc7ece91197a384650b09ec3de9ce1ffe6a19`. Review MANIFEST `0fa79c0019ba9c6ab6bbe265271c13c7ffb8d74734b826bf647b3265cb88e6c0`; final evidence MANIFEST `c023641067310dcaf0222e1dd5f5b3aa8af17a3c0f8b4d2798473b538247fa28`. These identify historical sandbox acceptance, not current-main acceptance. |
| Current-main store | `src/optimus/acp/spec.py:318-351`; `remove` at line 335 pops and closes but never discards the ID. `close_all` retains live sessions and their close-once markers. There is no `attach()` API. |
| Current-main failure path | `_handle_session_new` at lines 791-854 attaches `empty_state` before checking the runtime. Missing-runtime, configuration-error and generic-error paths call `remove`, so each can leave the empty state's ID behind. A separately returned provisional state can also be closed directly by the existing adapter. |

The bounded work record is now #357; live status, owner and next gate belong there, not in this draft. The [v1 review](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/357#issuecomment-6188226730) and [follow-up](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/357#issuecomment-6188519479) request this complete successor. V1 SHA-256 is `f04175c3cc08c7d60bd4659483ddabcec7b14f54dab2a23985ad9f4d743d925a`. Main and sandbox snapshots above were rechecked unchanged for v2.

**Approved execution roles and authority:** on 2026-10-15 the human pasted the three-part instruction approving exact v2 `e45a9f9038662af0c212510e7335847cd41d41658f13bb0a7ff0439e47fdab44`, isolated current-main implementation/local verification, and dropping Fable in favor of Claude as the single independent reviewer, followed by `[Vibhanshu] Approved by me.` That direct message in this Codex chat is the authority; the [Claude issue record](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/357#issuecomment-6188807103) is corroborating history only. The pasted instruction keeps commits, push, PR and merge separately gated. V3 records those already approved decisions without changing the behavioral contract, four test groups or coverage gates.

This serves the original single-owner resource-lifetime and centralize-then-migrate requirements in the sandbox register, under [resource lifetime/signals #317](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/317), related to [resource-lifetime candidate #302](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/302). It completes neither parent. MAIN-7 already merged through #352; this is a separate slice.

## Global constraints and bounded contract

1. After `remove(id)` returns or propagates a close exception, `get(id)` is `None` and `id` is absent from `_closed_state_ids`. Apply cleanup even when no session/state exists; preserve the return value `None` and the original exception object/type.
2. Under the supported sequential store access, a given session state's `close()` is invoked at most once across removal, repeated removal, `close_all` and repeated `close_all`. Count invocations, not just close hooks: `ClientMcpSessionState.close()` is itself idempotent and could hide a broken store guard.
3. `close_all` continues to retain live sessions and their markers. Removing A must not clear B's marker or close B again. After each completed sequential operation, `_closed_state_ids` is a subset of live session IDs; after all sessions are removed, both collections are empty.
4. Preserve current `session/new` results, error codes/messages, permission behavior, and direct provisional-state cleanup. Do not transplant the sandbox's best-effort exception wrapper. A direct provisional `state.close()` failure that currently interrupts adapter cleanup is outside this fix.
5. Keep signatures, call sites, logging, wire behavior, session ownership, configuration and dependencies unchanged. Make no performance, full memory-profile, cross-thread safety or broader MCP acceptance claim.

## Exact change scope and explicit exceptions

| Path in the implementing checkout | Permitted change |
|---|---|
| `src/optimus/acp/spec.py` | Only `InMemoryAcpSpecSessionStore.remove`, plus an immediately adjacent comment if needed. No other production method. |
| `tests/unit/acp/test_spec_protocol.py` | Focused store and `session/new` regressions below; local test helpers/imports only. Reuse `_rpc`, `FakeRunner`, `RecordingOutboundChannel` and existing isolated MCP runtime helpers. |
| `docs/superpowers/plans/2026-10-15-closed-state-ids-port_v4.md` | Proposed complete documentation-correction successor; same technical scope and gates. |
| `docs/superpowers/plans/archive/2026-10-15-closed-state-ids-port_v3.md` | Move the reviewed v3 unchanged only after explicit archival/path-expansion approval. |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Exactly one issue-only live-plan registry pointer; no new backlog work entry or duplicate status narrative. |
| `docs/README.md` | Index the adopted current plan and sanitized evidence receipt. |
| `docs/superpowers/reports/2026-10-15-closed-state-ids-port-checkpoint.md` | One sanitized source/commands/results/qualifications/hash receipt; no private raw evidence. |

The seven paths above are the proposed cumulative delivery scope; only documentation changes are proposed after the existing six-path local commit. A reviewer-owned `docs/superpowers/reviews/closed-state-ids-port-review-checkpoints.md` is local, ignored continuity only and must never be staged. Report any necessary path/interface expansion before changing it; a later material change requires an approved complete `_v5` successor. Do not amend frozen port plans, source tags or sealed evidence.

Explicitly excluded: `attach`, `session/load`, durable-session/Plan 11.7 runtime, held MCP T1/T2/N1/R1 and tool visibility, idle suspension, eviction/K-scaling, conversation unloading, state fallback/reader hygiene, typing/Ruff migrations and profiling. Their existing owners remain in the sandbox register and archived v5 portfolio; #240 owns the runtime lane, #302/#317 retain broader lifecycle custody, and #314/#324 retain typing/lint work. This slice adds no new deferred work; discoveries requiring independent work need separately approved issue custody before closure. No changes to MCP production modules, `server.py`, root conftest, runner/coverage tools, hooks, inventories, secret baseline, `pyproject.toml` or `uv.lock`.

## Dated v4 correction proposal

The full Windows candidate at local commit `7c3b5971b89860568b4076471141f28891428e66` failed one documentation hygiene check: 7,781 passed, 40 skipped and 111 deselected; gate exit 1. Default producer validation exit 3 retained the failed session binding; safety comparison exit 1 declared the candidate incomparable. This is failed evidence, not CP2 acceptance. The accepted clean baseline remains sealed and must not be rerun.

Root cause: the prerequisite guard discovers added plans from Git history through HEAD. Earlier uncommitted docs checks and normal commit hooks therefore omitted the newly added v3 plan. At committed HEAD, unsatisfied dispositions require a recognized classification and status cells require yes/no/unknown. V3 has unclassified dispositions and a not-required status. Preserve reviewed v3 unchanged; do not weaken the guard.

After approval: adopt this complete v4, move v3 unchanged to the flat archive, reconcile its one registry pointer, docs index and existing sanitized receipt. Check the new table directly before normal docs checks so Git-history discovery cannot hide it, then run normal installed hooks and make a bounded documentation-only local commit. Check the actual committed-head docs gate before the expensive full run. Obtain a fresh clean-source full Windows candidate gate, default producer validation and safety comparison in a new packet using the same qualified invocation environment, then Claude CP2. Preserve all prior evidence and source qualifications. No production/test/tool/config change, repeated unchanged suite, publication or cleanup is proposed.

## Prerequisites

| Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| Defect, failure branches and selected sandbox hunk exist | yes | Implementer/reviewer | Verified against the execution base and retained regression evidence. |
| Direct plan/implementation approval and normal local commits with passing hooks | yes | Operator | Exact v2 scope and implementation approved directly; normal local commits separately approved in this chat. Publication remains separately gated. |
| Bounded issue under #317, related #302 | yes | #357 | Existing issue remains the work record; no metadata change or duplicate issue. |
| Adoption of complete v4, unchanged v3 archive and documentation path expansion | no | Operator | Merely unauthorized: approve this complete correction and seven-path cumulative scope before candidate adoption or archival. |
| Direct execution-role/cadence confirmation | yes | Operator in this chat | Codex implements; Claude is the sole independent reviewer; Fable removed for #357. |
| Dedicated current-main branch/worktree | yes | Implementer; operator owns machine state | Candidate branch and clean pin verified; preserve the isolated lane. |
| Own frozen Windows environment and current review tools | yes | Implementer/operator | Retain qualified Git/bin/bash 5.3.15, frozen environment and healthy pinned ast-grep 0.36.2 cache. Linux PR CI is a later gate; local alternate OS is required if a platform-shaped change appears. |
| Source-class acceptance provenance available to reviewers | yes | Source custodian/reviewer | Source manifests and bindings reviewed at CP1; raw evidence stays local and the sanitized receipt stays the repository artifact. |
| Services, credentials, human ceremony and cost for local verification | yes | Implementer/operator | Unit/default local gates require no live Redis/Gateway/MCP activation, real keyring, GUI ceremony or paid calls; retain default live-tier exclusions. |
| Push, PR, merge, issue metadata, services, cleanup and private-memory writes | no | Operator | Merely unauthorized: each remains separately gated and excluded from this proposed local correction. |

## Review focus and regression matrix

Use real main store/adapter code and isolated unit seams. Never mock `remove` or manufacture its success. Temporary close spies must count calls by state identity and delegate to the real method unless intentionally raising. All proposed tests live in `tests/unit/acp/test_spec_protocol.py`.

| Proposed test | Required setup and assertions | Pre-port expectation |
|---|---|---|
| `test_session_store_remove_releases_closed_state_id` | Synchronous test parameterized over normal close and a spy raising `RuntimeError`, `asyncio.CancelledError`, `KeyboardInterrupt` or `SystemExit`. Catch each supplied exception with `pytest.raises` inside the sync test, asserting the same exception object. After removal require session/marker absent and one close invocation; repeated removal and close-all add none. Normal return remains `None`. | Red on retained ID; existing propagation/close counts are compatibility controls. |
| `test_session_store_remove_without_state_or_session` | Parameterize no attached state and missing session. Exercise both ordinary and explicitly synthetic stale-marker setups. Require no close, `None` return and that ID absent; another live session's marker must remain intact. | Unseeded controls green; seeded stale-marker assertions red. |
| `test_session_store_close_ordering_preserves_live_markers` | Distinct real states A/B with close-invocation spies. Close-all twice: sessions/markers remain and each closes once. Remove A twice, close-all again: A absent, B's marker retained and B still closes once. Remove B: both collections empty. A second parameter covers remove-before-close-all. Check marker subset and invocation counts after each operation. | ID-release assertions red; existing close-once/live-marker controls green. |
| `test_session_new_failure_releases_closed_state_id` | One call per parameter through real `_rpc`/adapter/store: runtime missing; duplicate-name configuration error; disposition raising ordinary `RuntimeError` before returning state; returned real provisional state followed by resolver-attachment `RuntimeError`. Require `-32600`, message `client MCP runtime not configured` for the first and `invalid request` for the others, empty sessions/markers and no unexpected permission/transport activity. Count the empty-state close; in the resolver case separately count the returned state's direct close, each once. Use successful closes in adapter cases. | Each parameter red on its stale empty-state marker. Missing APIs/imports/fixtures do not count as regressions. |

Five review risks are explicitly covered: close exceptions masking cleanup; absent-state defensive branches; clearing another live session's marker; state idempotence hiding duplicate store calls; and adapter failure tests accidentally bypassing the real provisional-state path. Preserve existing `test_close_all_closes_session_states_exactly_once`, malformed-server and session-load-method-not-found controls.

## Execution sequence and acceptance gates

### Task 1 — establish current-main contract and baseline (checkpoint 1)

- [ ] Record the direct v2 implementation approval and this exact cadence decision, then establish the authorized isolated latest-main lane. Read current `AGENTS.md`, `CONTRIBUTING.md`, evidence policy, ADR-016/ADR-022 and the reviewer checkpoint log. Use existing #357 and prepare the canonical six-path documentation projection; adopt only with the required approvals. No new issue is needed. Assign the next available linear plan identity at intake rather than inventing a reserved number in this draft.
- [ ] Record live main SHA, branch/HEAD/status, worktree inventory, source tag target/type/local-only custody, `git describe --tags --long HEAD` and every post-tag sandbox commit by class. Refresh this snapshot if main has advanced. Record selected hunk/test intersections with the day-0 range `63b5d8f..c69fd48`; exclude all day-0/held-MCP imports and whole-file transplants.
- [ ] Confirm serving access still serializes store methods on the event loop and waits for request tasks before adapter teardown. `remove`/`close_all` have no await; inspect current callers for background-thread/reentrant access. If unsupported concurrency is now required, stop for a scope decision rather than adding locks here.
- [ ] Resolve environment/provenance unknowns. Prepare each lane with `uv sync --frozen --extra dev`; verify imported module origins belong to that lane. In a clean unchanged Windows base lane run the canonical full product gate and validity command below; retain baseline safety rows for candidate comparison. Preserve native/protection/parent UNKNOWN qualifications.
- [ ] Add only the proposed tests in the candidate lane; run them against unmodified main production blobs with the focused command below. Preserve attributable reds for the stated retained-ID assertions and separately identify passing controls. Import/API/fixture failures are not regression evidence. Do not change production code before the behavioral red witness is captured.

**CP1 deliverable:** fresh-main hunk/contract matrix, clean full baseline with valid evidence, and test-only regression packet. Claude alone performs the independent checkpoint review under the direct operator decision. No per-test reviews. This checkpoint closes the early unknowns, not implementation acceptance.

### Task 2 — port the bounded fix and prove the final candidate (checkpoint 2)

- [ ] Adapt only `remove`'s close path to unconditionally discard that ID in `finally`. Keep the existing pop order, close-once guard and exception propagation. Do not add an adapter catch, clear the whole set, change `close_all`, or add an absent API.
- [ ] Run the unchanged regression matrix green, the complete protocol file, and existing default ACP/MCP unit suites. Preserve all default markers/root conftest. Run Ruff, docs checks and every applicable normal hook. No sandbox hook exception or Plan 12-only skip authority transfers to this slice. Local commits require explicit authority and passing selected checks; do not commit the failing test-only state.
- [ ] Complete the approved docs/receipt and normal local commits. On the final clean committed candidate run the canonical full Windows gate and validation. Required Linux PR CI follows in Task 3; a separate frozen local WSL/Linux run is optional for additional confidence, not an acceptance prerequisite for in-memory set handling. If the diff/failure becomes platform-shaped, reproduce on an alternate OS before acceptance. Serialize coverage writers per checkout/environment. Keep each platform's source pin, record and capability labels distinct. Report all default skips/deselections and any required regression not collected as UNRUN.
- [ ] Compare clean base/candidate safety statement and branch rows using the current `tools.testing.coverage_products compare` contract and its verified source-bound producer receipts. Require the producer's separate exactly-one eligible full-default-session validity receipt; naming `--run-record` alone does not establish uniqueness. Use project record readers, not ad hoc JSON parsing. Explain source-line remapping for the changed method; do not silently waive a regression.
- [ ] Audit exact diff (`git diff --stat`, `--numstat`, `--check` and full hunks), all six paths and imported dependencies. Record failures, raw exits, source hashes, skips and UNKNOWNs in retained packets; put sanitized claims/digests in the tracked receipt. Claude gives the consolidated independent assessment of the full candidate evidence; Codex must not sign off its own implementation. A product/test change after final runs needs new source-bound finals; preserve earlier results and disclose any docs-only delta.

**CP2 acceptance:** all required regressions green; protected Windows evidence valid; Linux PR CI remains a Task 3 gate, with its platform qualifications retained; current enforced coverage floors pass; aggregate production coverage >=80% and safety-critical statement/branch coverage does not regress; Ruff/docs/hooks pass; independent review has no unresolved blocking findings. The coverage tool reports aggregate/Evidence Handoff informationally: its exit 0 alone is insufficient for the AGENTS aggregate requirement. No new Mypy gate/dependency is introduced; run any applicable existing typed-module gate without expanding typing scope.

### Task 3 — publication, integration and actual-main verification (checkpoint 3)

- [ ] After local technical acceptance, obtain separate push/PR authority. Refresh main before publication, resolve drift intentionally and disclose/reverify changed source; do not reuse old finals as a new-source claim. Target only main with the bounded approved diff, issue link, regression evidence, rollback and limitations.
- [ ] Require all current PR checks and attributable full-default CI at the exact proposed integration revision. Verify product floors and producer validity in the CI artifacts, not check names alone. Claude alone independently reviews the integration packet, consolidates findings and audits current-state docs/issue freshness before the operator's separate merge decision. Keep CP3 as one package checkpoint; no per-task review loop.
- [ ] Only on explicit merge authority, merge and verify actual parents/tree and main-push CI, including canonical full coverage/validity. Do not call a pending check a pass. Preserve differences between PR revision, local accepted source and actual merged source. Record the bounded terminal result in its issue and the approved receipt; leave #302/#317 open for their remaining scope. Any frozen-plan archive, final custody-only update or cleanup needs its own applicable approval; implementation/merge grants none automatically.

**Stop rules:** preserve any failed/invalid gate and report its cause; do not retry an unchanged gate to obtain green, bypass hooks, weaken guards, reclassify live-tier fakes or broaden the patch. A diagnosed correction within scope can be reverified when authorized; unrelated failures or scope expansion need a recorded disposition before acceptance.

## Verification commands

Run from the implementing checkout with its prepared environment. These are handoff commands; none was executed to prepare this plan.

```bash
# Focused red/green, retaining normal selection and context instrumentation.
uv run --no-sync pytest --no-cov tests/unit/acp/test_spec_protocol.py -k 'session_store or session_new or close_all or session_load_still_method_not_found' -v
# Relevant unit compatibility surface.
uv run --no-sync pytest --no-cov tests/unit/acp tests/unit/mcp
uv run --no-sync pytest --no-cov tests/unit/docs
uv run --no-sync ruff check .

# One full default run/coverage dataset per clean base or final candidate lane.
uv run --no-sync python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json
uv run --no-sync python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json
```

At the snapshot, enforced precision-0 floors are 80% for Optimus product group, Context Engine and model-policy package; Evidence Handoff and aggregate tool outputs are informational. Preserve the current policy if it changes: do not transplant old configuration. Before and after reviewed runs record absolute checkout, branch, HEAD/tree/status, interpreter/platform, command, configuration/lock identities, stdout/stderr, exit code, full run record and validity/uniqueness receipts. Archive required evidence before another run can prune it. Do not clear `addopts` or launch a second suite just to validate the first dataset.

## Rollback and handoff

Rollback is a separately approved revert of this bounded production/test change, with corresponding issue/docs reconciliation. It restores the extra retained ID per failed MCP-bearing `session/new` reaching `remove`; successful sessions remain in `_sessions` with or without this fix. Disclose that narrow consequence. Do not revert MAIN-7, other lifecycle work or accepted guard tooling.

Codex executes the approved v2 technical scope under this complete cadence successor, #357 and the source/provenance receipt; Claude alone reviews independently. Normal local commits with passing hooks were directly approved; publication and this specific archival/path expansion remain separately gated. Definition of done is release of failed-request close markers, the exact merged slice and passing source-bound main checks recorded in #357. Successful-session unloading, broader session-table growth, parent-track closure, live-service acceptance and memory-profile acceptance are excluded. This proposed v4 has not been adopted or committed and has no new acceptance suite; the failed v3 candidate stays preserved separately.
