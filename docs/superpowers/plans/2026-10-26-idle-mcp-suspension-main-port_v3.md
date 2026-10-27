# Idle client-MCP lifetime complete successor implementation plan v3

> Private proposal for #427, not implementation authority. Codex is the assigned implementer; actual Claude CLI is the reviewer. Continue inline with `superpowers:executing-plans`. The operator has already chosen this arrangement. One connected correction batch, one commit checkpoint and one final delta review; no per-task review or full-suite rounds.

**Goal:** close every finding in the consolidated review of `6b49a7f3`, then establish source-bound Windows/WSL acceptance for the A-derived main client-MCP lifetime contract.

**Architecture:** retain the existing connection owner, session admission, renewal and IPC generation design. Repair failure ordering in the existing server teardown, distinguish retained shared-listener ownership from failed session-peer release, and make the prerequisite guard inspect the actual commit candidate. Add no new lifecycle framework.

**Tech Stack:** repository Python >=3.14, locked MCP 2.0.0, pytest/asyncio, Ruff/Mypy, normal hooks and product-coverage tooling; separate frozen Windows and WSL environments.

**Spec:** `docs/superpowers/specs/2026-10-26-idle-mcp-suspension-main-port-design.md` and ADR-027. The full inherited operating contract is included below, with the explicit qualifications and corrections in this plan taking precedence. Original main base `be93393fc27f22bafa58fd9c2404e17b347a209d`; continuation pin `6b49a7f3a05230b2714d3ae11baa44d91899d73f`, tree `d01d99043818937cb4aa530da0704e95f9d3ce3e`. Historical A remains provenance, not transferable acceptance.

## Authority and retained evidence

The operator approved the original implementation, the exact consolidated hook-correction plan `e1f2b9b7717c365a747ce3f6aed855697b8a4fdf1b2ef8daaad634d97c14c155`, focused checks, normal-hook local commit, sequential gates and one consolidated Claude review. That correction is complete. Its explicit production/plan freeze and independent-failure hold prevent silently applying the newly found changes. This complete successor proposes one scope extension; it does not reassign the implementer or request another architecture/plan review.

- Local commit `6b49a7f3`: clean, 42 files; all normal hooks passed. Commit-profile evidence is not a clean coverage gate.
- Correction RED: 9 failed /7 passed. Focused GREEN: 319 passed, quick H5=1/100; Ruff and configured Mypy clean. Preserve both, including reduced-depth qualification.
- Windows full gate at that clean pin: 1 failed /9,994 passed /49 skipped /101 deselected, pytest exit 1. The prerequisite grammar assertion failed; all enforced product floors passed. H5 repeat-100 actually passed (100/100, 562 seconds), as did all S1 tests. This does not turn the failed overall gate green.
- Producing-host validity returned 3 (`exit_status_differs`) because pytest exited 1. Root COMPLETE/native-valid/full protection; parent ancestry UNKNOWN; eight lifecycle nodes have setup pass without recorded call phase. Preserve the actual skip reasons and qualifications.
- WSL preparation/gate/validity and both seven-module safety comparisons remain UNRUN. Do not infer Linux acceptance from Windows or historical full-suite results.
- Actual Claude Max Opus5.5/high returned a complete signed **REVISE** review, SHA256 `3b5e3b03b7cbd0ffa34e9c3caa8ea777c486d49358779e6e1b55d17c10e3fee1`. CLI terminal exit 1 /`error_max_budget_usd`: list usage estimate US$6.411528 despite the requested US$3 guard. Verified first-party Max sign-in is established; the list estimate is not evidence of an additional API invoice. No retry or second model call ran. Complete review content is authentic, but neither terminal workflow success nor technical acceptance is claimed.
- The D: lane location departure stays disclosed. No other lane, main, old WSL environment or existing evidence may be reset or cleaned.

## Global constraints

- Preserve main conversation continuity; no durable-resume import, TTL parser, synthetic expiry, eviction/Piece B or new trust writes.
- Idle default 3,600 seconds; positive integers through 2,592,000; monotonic tighten/exact loosening grant, no environment off value. Direct library default remains None; bootstrap validates before constructing resources.
- Chat gets no tools, permission broker or MCP reopen. Plan/Agent renewal remains all-or-nothing; cleanup uncertainty in actual session peers still quarantines the session.
- Keep #377 discovery, main resolution failures, Plan12 context/cost/routes, actual FLUSHED delivery join, existing busy error convention and only the registered MCP_REOPEN_REFUSED new error.
- No dependencies, lockfiles, secret/scanner exemptions, lowered floors, root-conftest changes, launch bypasses, protection weakening, live services, deliberate load or stress workers.
- Preserve failures, hashes, source identities, UNKNOWNs, skips and physical ownership. No retry-to-green and no successful focused check described as a full gate.
- Only the 15 paths below may change. Other ten production modules stay byte-identical to `6b49a7f3`. Guard behavior is strengthened, never exempted. No new logging surface or diagnostic payload is intended.
- Keep #427/#317 and related issues open. No push, PR, issue/review posting, integration, merge, issue closure, branch/worktree/environment cleanup or machine repair. Private recorders/evidence may be prepared outside Git, with no source mutation or process takeover hidden in them.

## Prerequisites

| Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| Approved route, continuity/TTL choices and Codex implementation assignment | yes | Operator | Existing explicit assignment and decisions persist. |
| Clean continuation source and retained review/evidence | yes | Codex | Bound to the pin/tree and retained failures above. |
| This successor's expanded source/guard scope and local version-filing exception | no | Operator | merely unauthorized until approval of this complete v3. |
| Teardown, IPC distinction and candidate-blob guard corrections | no | Codex | genuinely absent but buildable within the exact scope below. |
| Focused checks and normal-hook successor commit | no | Codex | merely unauthorized for the expanded cohort until this plan is approved. |
| Successful clean Windows gate, validity and seven-module safety | no | Codex | genuinely absent; the retained clean attempt failed and must remain failed. |
| Separate source-identical Linux environment and acceptance | unknown | Codex | genuinely absent as demonstrated acceptance; preparation and execution remain held until Windows succeeds. |
| Owned-child and machine envelope at the new checkpoint | unknown | Codex | merely unauthorized to assume from old evidence; refresh bounded preflights before child/gate work. |
| One additional compact changed-source Claude review | no | Operator and Codex | merely unauthorized until this plan's explicit additional-model release is approved. |
| Paid/live/Redis/Gateway/editor acceptance campaign | no | Existing #222/#240 owners | merely unauthorized and outside this technical claim; no substitute test grants that acceptance. |
| Publication, main integration, merge, closure and cleanup | no | Operator | merely unauthorized; explicitly held throughout this plan. |

## Exact mutation scope

Count the move as separate old/new paths: **15 paths**. Against original main, the total cohort becomes **44 files**: current42 minus live v2 plus archived v2 plus v3 plus the guard file. The backlog already belongs to the42, so its link correction adds no cohort file.

| Path | Complete permitted delta |
|---|---|
| `src/optimus/acp/server.py` | B2: capture genuine MCP outcome/failure, attempt writer and reader cleanup, preserve failure/control-flow and Redis-last custody. |
| `src/optimus/mcp/client_disposition.py` | N1: narrow typed listener-stop distinction in the candidate-retirement callback only. |
| `tests/unit/acp/test_server_mcp_shutdown.py` | Physical writer/reader and failure-order controls for B2, including cancellation and combined failures. |
| `tests/unit/acp/test_server_redis_shutdown.py` | Confirm Redis closes once, last, and the primary failure survives. |
| `tests/unit/mcp/test_client_disposition.py` | Exact typed IPC-stop handling and ordinary/forged-failure negative controls. |
| `tests/unit/acp/test_idle_mcp_suspension.py` | Actual retained-endpoint suspension/Chat and uncertain-peer refusal controls. |
| `tests/unit/docs/test_open_work_pool_hygiene.py` | B1: owned candidate-index inventory and blob-byte checking, frozen-exception hash consistency and temporary-Git controls. |
| `docs/superpowers/plans/2026-10-26-idle-mcp-suspension-main-port_v2.md` | Move only, byte-for-byte; no textual correction to approved frozen v2. |
| `docs/superpowers/plans/archive/2026-10-26-idle-mcp-suspension-main-port_v2.md` | Exact frozen v2 destination; SHA256 `8e92ca21092f41c3fc472de3fc092d4a1f47c0c3e3b908a5f65b5f6e6d3d662e`. |
| `docs/superpowers/plans/2026-10-26-idle-mcp-suspension-main-port_v3.md` | File these complete approved bytes as sole current successor. |
| `docs/decisions/ADR-027-idle-client-mcp-lifetime-contract.md` | v3 link, N1 ownership distinction, N2/N3 limitations. |
| `docs/README.md` | Current v3 index link/title, no stale live v2 reference. |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Existing registry row's v2 link/title becomes v3; keep issue authority and no copied status. |
| `docs/superpowers/specs/2026-10-26-idle-mcp-suspension-main-port-design.md` | v3 link, N1 clarified contract and N2/N3 qualifications. |
| `docs/superpowers/reports/2026-10-26-idle-mcp-suspension-main-port-receipt.md` | Full review disposition, binding v3 SHA/approval, frozen predecessor, actual failed/changed-source evidence and holds. |

Read-only connected source includes `outbound_writer.py`, `lifecycle.py`, `settlement.py`, `spec.py`, `local_ipc.py`, `client_sdk.py`, `client_supervisor.py`, `client_trust.py`, `tools/tracked_repository_files.py`, profile/coverage/native protection tooling and both audit tools. Reuse their actual contracts. No local_ipc sticky-failure flag is invented: the endpoint retains generation/handles, while runtime aggregate failure becomes sticky after an incomplete final-close observation.

The current backlog **does contain a v2 link** (line74). A final source refresh corrected an earlier private disposition assertion that it was issue-only without a plan link. This plan includes the real link repair. Preserve the original disposition snapshot and append this correction privately; never silently rewrite reviewed evidence.

**Version-filing sequencing exception proposed for operator approval:** repository AGENTS requires a migrated plan's superseded disposition in its issue before archival. Publication is expressly held. Approval of this v3 therefore specifically permits the local byte-preserving v2 move and canonical receipt's superseded record before posting that issue note. Prepare the note privately; do not post it. This is a document-version sequencing exception, not worktree cleanup or authority to change frozen plan text. All other AGENTS rules remain in force.

## Review focus

1. A raising MCP stage must never bypass the physical owned writer join or reader decision; pin it in B2 tests.
2. A later ordinary failure must not mask an earlier primary failure, and deferred cancellation/control-flow must remain visible after owned cleanup; pin the precedence cases below.
3. Only the exact typed `client_mcp.ipc_stop_incomplete` from candidate retirement is separated from session peer release; genuine/forged/SDK failures remain failures.
4. The guard must inspect the same candidate inventory, bytes and frozen-exception digest, including alternate owned indexes; no valid-worktree false pass.
5. A passing Windows result is not Linux acceptance, successful validity or seven-module safety; preserve each producing-host artifact and gate separately.

## One implementation batch

### B1: candidate guard and complete successor filing

Use the existing public `index_environment(root: Path) -> dict[str,str] | None` from `tools.tracked_repository_files`; do not modify that helper. When its owned commit bridge is present, use that environment for both `git diff --cached --name-status <prerequisites-amendment>` and `git show :<relative-path>`. Outside the bridge use the existing amendment..HEAD inventory and HEAD blob contents, keeping inventory/text/hash in the same source view. A missing owned index must propagate `TrackedFileInventoryError("commit_index_missing")`; never fall back to a repaired working tree.

Preserve the current added-canonical-plan/date/governance/path filters and exact existing pinned exception. `_frozen_disposition_exception` must digest the exact blob bytes being parsed, not filesystem bytes. Keep the current table grammar. No new frozen exception, hash exemption, status whitelist, scanner bypass or broad filter is permitted.

- [ ] Add temporary-Git RED controls in the admitted guard file for first staged addition; alternate owned index; missing owned index; invalid staged blob with valid worktree; valid staged blob with invalid worktree; ordinary negative grammar; and frozen-exception digest bound to the checked blob. Keep controls local and owned, with no real repository commits or global Git settings.
- [ ] Observe one combined RED selection on `6b49a7f3` with only the new controls. Assert the intended failures, not setup accidents. Preserve exact source/commands/results.
- [ ] Implement the narrow candidate/blob changes. File v3 and move v2 unchanged, repoint all five actual live references and record the explicit sequencing exception. v1 remains unchanged. Do not post the prepared issue note.
- [ ] Stage only approved paths for candidate-mode focused checks, using the existing TEST_RUN_COMMIT_INDEX_FILE/ROOT bridge. Without candidate mode, the old committed v2 would correctly remain visible before the successor commit. Do not set SKIP, disable addopts or substitute another index ownership namespace.

### B2: finish owned stages before propagating MCP failure

`shutdown_mcp` must record the real `ClientMcpShutdownOutcome` in outer state even if `adapter.aclose` raises. Always attempt runtime.close after adapter work; capture the adapter failure before that finally so a later ordinary runtime failure does not replace it. Catch a failed shutdown task, including BaseException delivered while awaiting its shield (not just `.result()`), and proceed to classify/report, owned writer join and reader decision. Keep reports' current bounded shape and lazy logging supplier; preserve the genuine returned outcome if available. A failed stage is incomplete even when the returned runtime outcome itself is complete. No fabricated release or new diagnostic code is needed.

Attempt reader handling even if the writer stage raises. Defer propagation until the later owned stages have been attempted and the enclosing Redis-finally still closes Redis once and last. Deterministic precedence: first control-flow failure (including cancellation) takes precedence over ordinary failures; absent control-flow, preserve the first ordinary teardown failure. Preserve the already recorded primary serving error according to the existing enclosing convention, and retain secondary failures through existing diagnostics/chaining without leaking raw exception text. Repeated cancellation joins the same owned MCP worker; it must not detach that worker or launch a replacement. This is a local ordered-cleanup correction, not a generic exception aggregation framework.

- [ ] Add the physical-writer RED control using existing `_PhysicalWriter`/reader harnesses. Make the actual non-daemon `optimus-acp-ndjson-writer` observable, not just a no-op join spy. Hold a real input pipe where needed, verify the reader decision/diagnostic, and release that test-owned producer in finally so the test cannot strand an executor read.
- [ ] Cover adapter failure with genuine returned runtime outcome, runtime failure, simultaneous adapter/runtime ordinary failure, later writer failure, control-flow failure, and repeated cancellation. Assert exactly one MCP-incomplete diagnostic, actual writer exit where the join succeeds, reader decision, original primary identity and Redis close exactly once/last. Existing successful EOF, configured handoff and incomplete-reader semantics stay unchanged.
- [ ] Run the small B2/N1/guard RED set together where possible, then apply all production corrections in one batch. Keep failures separately attributable; do not iterate full gates or model calls while fixing them.

### N1: retain shared IPC ownership without false session quarantine

In `_own_candidates`' retirement callback only, catch `LocalIpcError` only when its `.code` is exactly `client_mcp.ipc_stop_incomplete`. `retire_session` has already removed this session's candidates before trying to stop the shared listener. This exact failure means retained global listener generation/handles, not uncertain release of that session's actual MCP peers. Keep those handles, refusal to replace a live generation and final runtime-close reporting. Catch neither arbitrary exceptions carrying a similar `.code` nor a different LocalIpcError, and do not wrap all close hooks or suppress an SDK failure.

- [ ] Prove retirement actually removes the session's candidates. With a held listener, successful session-peer release reaches MCP_SUSPENDED and admits Chat without tools/permission/reopen. Final runtime close while the listener remains held is incomplete; its aggregate failure stays sticky after that observation. If the listener is genuinely released before any failed final-close observation, no fictional endpoint sticky flag is required.
- [ ] Keep genuine peer-release uncertainty quarantined and Chat-refused. Cover another typed IPC error and a forged-code ordinary exception. Use actual session/endpoint ownership and an owned bounded hold seam; do not rely solely on a fake callback returning success. Release all fixture-owned threads/peers in finally and preserve real Windows/AF_UNIX platform evidence requirements.

### N2/N3: explicit limitations, no new runtime behavior

- [ ] Record in ADR/design/receipt that a hung keyring read or arbitrary close hook has no outer observation bound. Shield/join may wait indefinitely; this supersedes inherited N-c's unimplemented outer-bound promise. Keep #302 custody; no force-kill or timeout policy is added.
- [ ] Record beside the endpoint-snapshot blind spot that foreign logging filters, `dictConfig(disable_existing_loggers=True)` or global WARNING disablement can make the stdio warning channel unobservable. Suspension then stays disabled for those peers with bounded WARNING_UNOBSERVABLE diagnostics. Do not change global logging configuration.

## Focused verification and checkpoint

Run from this lane's own frozen environment, normal repository configuration and protection, sequential child ownership, no extra load. Use `uv run --no-sync` only after verifying it resolves this lane's environment; otherwise invoke its own Python explicitly. Preserve source hashes, terminal exit, native records and stdout/stderr.

- [ ] One combined GREEN selection: `python -m pytest --no-cov -ra --audit-depth=quick tests/unit/docs tests/unit/mcp/test_client_disposition.py tests/unit/mcp/test_local_ipc.py tests/unit/acp/test_idle_mcp_suspension.py tests/unit/acp/test_server_mcp_shutdown.py tests/unit/acp/test_server_reader_ownership.py tests/unit/acp/test_server_redis_shutdown.py tests/unit/acp/test_plan1126_shutdown.py tests/unit/tools/plan1126_runtime_audit/test_serving_custody.py tests/integration/mcp/test_client_sdk_local_stdio.py tests/unit/tools/test_run_context_child_sites.py tests/unit/tools/test_run_context_reviewed_programs.py tests/unit/tools/test_test_profiles.py tests/unit/tools/test_verify_plan996_logging_surfaces.py`. Use the owned index bridge for docs candidate validation, not a protection bypass. No full depth or whole suite at this step; H5 quick remains reduced-depth.
- [ ] Run one configured `python -m mypy`, `python -m ruff check .` and `git diff --check`. Check full cohort, actual live links, v1/v2 hashes, remaining ten production hashes and exact guard exception semantics. If ordinary affordable failures arise within these paths, fix together and rerun affected focused nodes only.
- [ ] Update receipt with full actual failures/results and SHA of this approved plan, then freeze the complete staged44-file cohort relative to original main. Receipt-only post-focus changes must be proven by tracked-hash comparison. Any independent out-of-scope failure is a hold, not permission for silent expansion.
- [ ] Make one local commit using all normal hooks without bypass/narrowing. Preserve commit attempt01/02 and current Windows failure as history; name the changed-source successor attempt distinctly. Verify clean HEAD/tree/parents, full staged-vs-committed identity and all tracked hashes. A further independent hook failure is held, never automatically retried unchanged.

## Sequential clean gates and safety

Only after the successful successor commit, run the ordinary Windows gate once at that clean source, BelowNormal with one coverage writer and sufficient recorder allowance for retained long runs. No deliberately added CPU/disk/memory stress. Capture root/child PID plus creation identity, producing timezone, command, contexts, coverage artifacts and terminal exit. A gate timeout/failure is not acceptance.

```
python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json
python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json
```

- [ ] On Windows success, run same-dataset producing-host validity, then seven-module safety against the retained same-platform `f9af2882` datasets. Hash-check the seven unchanged source modules and every input archive first. The four other main production modules differ from that old pin; no historical full-suite transfer is claimed.
- [ ] Use the existing `tools.testing.coverage_products compare` with `--base`, `--base-report`, `--base-run-record`, `--base-producer-utc-offset`, `--candidate`, `--candidate-report`, `--candidate-run-record`, `--candidate-producer-utc-offset`. Use actual source-bound files and producing offsets (+05:30 for retained Windows, +00:00 for retained Linux, refresh candidate offsets). Do not infer a safety pass from product floor success or validity alone.
- [ ] Only after Windows gate/validity/safety succeed, prepare one new owned WSL source-identical clone/environment (proposed `/root/optimus-idle-mcp-v3-20261027`, must be absent before creation). Verify donor trust/source and locked Python3.14 environment, commit/tree/physical hashes, Linux warning premise, AF_UNIX listener proof and actual protection qualification. Existing WSL lanes remain untouched. No shared/global environment, Docker restart or WSL shutdown.
- [ ] Run the same ordinary WSL gate once, then its producing-host validity and same-platform seven-module safety sequentially at that same source, using nice and one coverage writer. Preserve WSL native-Job unsupported qualification and actual ancestry result. An unsupported control is not native protection. No unchanged failed-gate retry and no automatic source integration.

## One additional compact delta review: explicit new release

The previously commissioned consolidated review has been consumed. This plan requests approval for **one additional** actual Claude Max Opus5.5/high changed-source/evidence review after the whole corrected batch and gates, with existing Max sign-in reverified, read-only mode, no tools/hooks/MCP. It is a material shutdown correction review, not another minor or architecture-plan round. Do not invoke it now or resend the 1.9MB packet.

Freeze a delta packet at most **600,000 UTF-8 bytes** containing the full new change from `6b49a7f3`, complete two changed production modules, new tests/guard, complete v3 and review disposition, dependency-closed relevant unchanged excerpts and exact new focused/hook/Windows/WSL/safety evidence. Include original failures and budget terminal qualification. A smaller packet must not omit a changed failure path to fit the cap. Inventory/hash all supplied and omitted inputs and output destination privately; no remote posting.

Apply a new US$3 CLI list-usage guard, explicitly **not a strict first-request cost ceiling**: the previous call reached US$6.411528 before the CLI returned its budget error. This plan does not promise a hard dollar bound or assert a new API bill. Operator approval of this section accepts one compact call under that disclosed limit, not an automatic budget increase or permission to retry. If strict US$3 is required, hold the model call instead of claiming the flag enforces it.

- [ ] Freeze source, packet SHA/bytes, verified Max status and terminal/evidence manifest; run one call. Preserve a failed/budget-limited terminal independently of any complete content. Apply no automatic follow-up call.
- [ ] Produce one private consolidated disposition mapping every B1/B2/N1/N2/N3 criterion, candidate blob control, platform acceptance and residual. Do not call REVISE accepted. If new independent issues remain, report them together, with one bounded recommendation; no silent out-of-scope fixes or new review loop.

## Completion and approval boundary

Technical acceptance requires the full inherited contract as qualified here, all specified focused checks, normal-hook clean commit, Windows/WSL gates with producing validity, seven-module same-platform safety and independent changed-source acceptance. No global bounded process exit, machine-freeze diagnosis, live client/service campaign or whole-track closure is claimed. #302 retains unbounded hook/keyring observation, request-ID exhaustion and broader resource work; #222/#240 retain external acceptance/durable work; #317 retains programme custody.

Approval of this complete v3 would authorize the15-path batch (including guard strengthening and local frozen-v2 archival sequencing exception), planned focused checks, normal-hook local commit, sequential Windows/WSL preparation/gates/validity/safety, and the one additional compact private delta review with the disclosed non-strict list guard. No further assignment question or intermediate approval for routine mechanics is needed. This document grants no approval by itself. Stop before publication, integration, merge, issue closure or cleanup.

## Full inherited operating contract

The following v2 implementation contract remains binding for the retained source; it is included so an executor needs no workstation archive to understand the product. These are retained requirements, not claims that every old checkbox or result has passed. The exact v3 scope above alone authorizes changes. B2 failure ordering, N1 shared-listener distinction and the N2 no-outer-bound qualification above take precedence over inconsistent historical wording below.

### Inherited package 1 Shared SDK lifetime and truthful cleanup

**Interfaces to preserve/add**
- Keep `ClientMcpSdkAdapter.open/discover/call/close/close_all` public behavior and #377 typed results.
- Preserve existing `_open_owned_sdk_contexts(capability, *, session_id, identity_key)` arguments. Its connection owner enters/exits the SDK contexts. Use the historical bounded request-dispatch design, a queue capacity of two with one operation slot and reserved close admission.
- Add `pending_connections() -> tuple[str, ...]`, `has_pending_connections_for_session(session_id: str) -> bool`, sticky `close_failure_recorded`, and bounded `diagnostics`/drop count. Pending tokens are random opaque IDs; diagnostics expose counts/fixed codes, never raw identity-key or path hashes.
- Session state provides `prepare_suspend() -> tuple[Callable[[], None], ...] | None`, `complete_suspend(failures: tuple[str, ...]) -> bool`, `has_leased_stdio_server() -> bool`. Add `prepare_close() -> tuple[Callable[[], None], ...]` and `complete_close(failures: tuple[str, ...]) -> None`. Preparation marks terminal state and detaches/snapshots hooks exactly once on-loop; completion records sticky failures. Keep sync `close()` as their compatibility wrapper. Disposition wires a `record_session_close_failure() -> None` callback into every real session state; its sticky `close_failure_recorded` is consumed by ClientMcpRuntime.close, including failures observed through old sync callers. Do not move permission cancellation or state mutation off-loop.
- Add `PendingClientMcpCandidateEndpoint.retire(candidate_id: str, *, session_id: str) -> bool` and `retire_session(session_id: str) -> int`. Retire only matching ownership, idempotently. Keep at most one pending candidate per live session/server; publishing a renewal atomically supersedes that server's older candidate. Candidates live through the permission answer and retire on session close/suspension or a same-server successor, preserving the later durable-trust ceremony. Cleanup runs in one serialized off-loop bookkeeping lane, not one unbounded to_thread job per candidate.

- Establish `test_real_sdk_contexts_enter_and_exit_in_same_owner_task` against unmodified main with an actual official ClientSession and local stdio child. Preserve the actual outcome; a missing expected red is a design observation to resolve, not a fabricated failure.
- Implement shared owner dispatch, including cancellation and failure of all queued/active responses in owner `finally`. A subsequent request/close observes the recorded terminal status immediately. A clean owner exit is not sufficient if context release, warning observability or survivor evidence is uncertain.
- Keep a connection pending until context/owner release is established. Never pop it or mark closed before release. Gather all close attempts even if the first fails; propagate control-flow failures, record ordinary failures stickily and make aggregate shutdown incomplete while any owner/failure remains.
- Route discovery and calls through owner dispatch with an internal direct path; retain main's discovery implementation and its budgets. Do not copy old A discovery bodies.
- Install the sanitized SDK warning observer at runtime construction, never module import. Keep at most one shared handler, explicit ownership across multiple runtimes and no strong references that prevent collection. Preserve warning endpoint checks and identity-bound survivor latches independent of ring overflow. Diagnostic capacity is 256 with an exact dropped count. Do not forward raw SDK messages, args, traceback or target data; do not mutate unrelated SDK records outside an owned context. Check the installed MCP 2.0.0 warning premise on each platform.
- Split server shutdown: serving-loop abandonment/cancellation of turns, permissions and reservations; stop sweeper and join all owned close tasks; detach/prepare session close on-loop; run blocking close hooks and runtime.close off-loop; apply state/outcomes on-loop; preserve existing Redis-last cleanup and primary failure behavior. Keep synchronous close_all compatibility for existing callers, but serving uses awaited `aclose()`.
- Clean `NdjsonOutboundChannel.request` in `finally`, including send failure, timeout and cancellation: remove only its own mapped future and cancel an unresolved future. Late responses become ignored, and cannot complete a replacement request.
- Tie candidate retirement to session lifetime, not a permission finally. Both session/new and renewal register ownership of published candidates; an answered permission must not prematurely remove the operator's later IPC trust path. Retire on session close/suspension and atomically replace the prior same-session/server candidate when publishing a successor. Each listener has a generation and fresh address. Stop/join/unlink only the captured generation; while its stop is incomplete, retain/report that handle and refuse or defer new listener start. At most one stale listener thread may remain owned. Serialize all IPC cleanup off-loop; never delete another session, concurrent candidate or newer listener/socket. Test real Windows pipe and WSL AF_UNIX stop/start behavior under owned local fixtures.
- Add focused tests: owner exit before/after queued call; open/exit failure; reserved close under pressure; ordinary and control-flow close failure; close-all attempts remaining peers; owned child exit; session isolation; cancellation/timeout/late response future cleanup; repeated denied renewals return future/candidate counts to baseline; concurrent IPC publish/consume/retire; listener handle retention if join is incomplete; warning unavailable/changed/survivor/ring overflow; no raw target secret in diagnostics; facade/connection/owner weakrefs become collectible after confirmed release.
- Verify `ClientMcpLeaseAuthority.acquire_allow_once` remains in-memory: source currently only returns a dataclass; `lookup_durable` only reads. Add a no-write spy regression across renewals; modify no trust-store production code.

Use one off-loop close worker per serial sweep. The existing eight-connection default and operation timeouts bound scheduled submissions; set a session close observation budget of server count times the effective operation timeout. A timed-out SDK context still retains its owner and is uncertain, not force-released. There is no new promise to forcibly kill Python threads or bound all process exit.

### Inherited package 2 Idle admission and permission renewal

**Interfaces**
- Dedicated `DEFAULT_ACP_MCP_IDLE_SECONDS = 3600`, `MAX_ACP_MCP_IDLE_SECONDS = 2592000`, parser and `resolve_acp_mcp_idle_seconds(environ: Mapping[str,str]) -> int`; invalid input fails before `build_agent_harness_runtime`.
- Add registry/default/display for `OPTIMUS_ACP_MCP_IDLE_SECONDS`, agent-child-only, monotonic tighten/exact loosen. No TTL names or ambient environment reads.
- Adapter and library server constructors default `mcp_idle_seconds: int | None = None`; direct constructions remain disabled and start no sweeper. Bootstrap always resolves and threads the operator default 3600, including real Stage C composition. Keep injectable `monotonic_clock: Callable[[], float] = monotonic`. None is an internal composition default, not a new launch off setting.
- Add `record_turn_commit(session_id: str, turn_seq: int, *, committed: bool | None) -> None`, `note_turn_delivered(control: TurnControl, *, cancelled: bool = False) -> None`, `sweep_idle_mcp_once()`, `start_idle_mcp_sweeper()`, `stop_idle_mcp_sweeper()` and `aclose()`.
- Add public read-only `ConversationState.next_turn_seq`. Use it instead of adding idle reads of `_next_turn_seq`; no allocation behavior changes.
- Disposition adds `reopen_suspended(state: ClientMcpSessionState, request_permission: RequestPermissionFn) -> PermissionOutcome`, all-or-nothing publication.
- `submit_via_turn` and `deliver_envelope` return bool. Join only the normal TurnResponseEnvelope completion path; exception/outbound-error resend paths stay unarmed. Authoritative `rpc_response_delivery is FLUSHED` is separately required.

- In `_commit_turn`, record unknown immediately before prepare_commit, then known committed immediately after commit_after_final_flush (main line1604), before any notice/usage/alert await. In the prompt finally, record known noncommit only if no marker exists. A post-commit cancellation preserves committed; a partially failed preparation remains unknown.
- Verify writer ordering unchanged: normal outbound_writer lines228/233 publish authoritative state before line237 resolves source_future. Add real-writer tests including fallback/ambiguous/fail-closed branches; do not arm from future completion alone or change the writer's settlement algebra.
- Before allocation, use this prompt order: ordinary validation/busy checks; closing/reopen/quarantine gates; conversation.prepare_admission; if refused, retain the deadline and issue no renewal prompt; if admitted, snapshot execution mode and the attached-session context strategy/settings before any renewal await; invalidate the old idle_epoch; reserve/reopen only for a non-Chat suspended prompt according to that snapshot; recheck admission after renewal; then allocate the turn using the snapshot. Leave setters unchanged and responsive. A setter during renewal succeeds and affects only the next prompt. Use the captured configuration for AcpPromptTurn, AttachedTurn and associated notice decisions, and do not clear newer setter-publication/notice obligations. Test switching to Chat during Agent renewal: setter succeeds, the reserved turn still runs as captured Agent, the next prompt is Chat; also test a strategy change.
- Chat never reopens MCP and receives neither service nor permission broker, whether peers are active or suspended. The actual runner dispatches Chat to `_run_chat_answer` before tool planning, and that method accepts no MCP service; keep runner production unchanged. Test this through the real Chat runner with spies that fail on MCP open/list/call/permission. Returning to Plan/Agent later requires full renewal.
- Arm only after a known allocated turn outcome + matching idle_epoch/sequence + actual FLUSHED RPC result + no cancellation/teardown + still-live leased state with at least one actually opened peer. A distinct peer-close-hook indicator is acceptable; candidate-retirement hooks do not count as opened peers. Never-opened leases release nothing and must not trigger needless renewal. Pre-admission nonturns, unknown outcomes, ambiguous/suppressed/failed sends and server exception-resend paths never arm. A known allocated noncommit AcpOutboundError returned through the normal TurnResponseEnvelope does arm after FLUSHED. Writer _fail_closed resolves its future without authoritative publication, so NOT_ATTEMPTED correctly prevents arming. Pop consumed/stale markers and prune session state on teardown. The active map alone is insufficient. Name the idle counter idle_epoch to distinguish it from ConversationState.generation.
- Implement ACTIVE -> IDLE_CANDIDATE -> MCP_CLOSING -> MCP_SUSPENDED/QUARANTINED. The serial sweeper sleeps min(60, effective delay); it never busy-spins. Prepare/detach on-loop, run blocking hooks/pending query off-loop, finish state on-loop. Shield and track close work through sweeper cancellation and final shutdown.
- If warning observability is absent before close, perform no close, clear that deadline, record a fixed diagnostic and permit rearm only after a later determinate turn. Unknown release, changed channel or survivor evidence quarantines with `data.reason=mcp_cleanup_uncertain`. The documented entirely-between-snapshots logging-flip limitation remains.
- Reserve before renewal; renew former leased names in pinned order using fresh allow_once decisions; publish all leases and a new collectible facade atomically only after all succeed. Preserve unavailable servers and main's resolution-failure state. Denial/timeout/failure returns MCP_REOPEN_REFUSED, admits no turn and publishes no partial service set. session/cancel also cancels a pre-allocation reservation and its pending permission. It returns a non-turn success {"stopReason":"cancelled"}, restores MCP_SUSPENDED, allocates nothing, changes no conversation record and arms nothing. Do not log cancellation as a pre-run refusal. Clean its future immediately; manage candidates by the session-lifetime rule above.
- Add only MCP_REOPEN_REFUSED -32912, correct its docstring and error registries. Reuse REQUEST_CANCELLED for busy closing/reservation cases. Add the fixed reasons `mcp_reopen_refused`, `mcp_cleanup_uncertain`, `mcp_reopen_in_progress`, `mcp_closing` to the pre-run refusal allowlist and tests. Keep message content fixed and path-free.
- Tests cover exact boundary/deadline; unknown vs known noncommit vs postcommit cancellation; stale/out-of-order flush; busy refusal retaining markers; cap-closed and reservation refusals retaining deadlines/no permissions; Chat remaining suspended; Plan/Agent all-or-nothing reopen; cancellation before allocation returns a non-turn success with stopReason cancelled; successful setters during renewal affect only the next prompt; no-loop-blocking with another session answered while close remains in progress; shutdown joins through repeated cancellation; policy min/max/invalid/exact grant/default display; configuration invalidity before Redis construction; bootstrap/server wiring; no context/cost/route regressions.

Ordering is the primary responsiveness assertion. Retain the historical 0.5-second controlled slow-close and 0.25-second secondary timing bounds without returning to fragile 50 ms gates. Use events/handshakes; do not add deliberate CPU load.


### Inherited architecture-note disposition

| Note | Plan resolution |
|---|---|
| N1 commit marker | Package2: unknown before preparation; committed immediately after line1604; finally defaults only missing markers. |
| N2 flush ordering | Source verified: writer publishes before resolving future. Preserve writer, add ordering test, normal envelope-only join and public sequence accessor. |
| N3 refusal ordering | Probe admission before invalidating deadline or asking permission; recheck after renewal. |
| N4 dead owner queue | Owner finally fails queued/active responses and records terminal outcome; no dead queue wait. |
| N5 truthful cleanup | Real SDK red control first; pending and sticky failures; close every peer; aggregate reflects uncertainty. |
| N6 loop affinity | Three-phase awaited shutdown; permission cancellation/state on-loop, blocking hooks/runtime off-loop, Redis last. |
| N7 bookkeeping | Future finally cleanup; session-lifetime candidates/successor replacement preserve trust ceremony; listener generations and serialized off-loop cleanup; in-memory allow_once verified; serialized off-loop durable reads; bounded close submissions. F6 renewal growth is included. |
| N8 privacy/logging | Counts/fixed codes/random internal tokens; no raw-path hash. Runtime-owned warning observer, premise tests, audit classification and retained snapshot limitation. |
| N9 configuration | Dedicated parser/default/display; validate before harness construction; no TTL names or hidden off value. |
| N10 errors | Main busy convention, new reopen code only, correct docstring and allowlisted refusal reasons. |
| N11 cancellation | Extend cancel to pre-allocation reopen and cancel/clean its permission; atomic facade publication retained. |
| N12 Chat | Keep suspended with no MCP service/broker and no permission; runner source confirms early no-tools Chat path. Snapshot configuration before await while leaving setters responsive; test old-turn/new-prompt behavior. |


### Inherited final-plan corrections and recorded choices

The immutable v1 review is `evidence/2026-10-26-sandbox-delivery-audit/claude-review/claude-plan-review.md`. Claude accepted the plan conditionally on R1–R3 and explicitly said no further round was needed once those text corrections were folded in. This complete v2 folds all three in, and addresses the affordable material notes together. It does not convert plan acceptance into runtime execution authority.

| Final review item | v2 disposition |
|---|---|
| R1 setters | Setters stay unchanged/responsive. Snapshot the admitted prompt's mode/context configuration before await; allocation uses the snapshot. Add mode and strategy setter concurrency tests, including Agent-to-Chat during renewal. |
| R2 cancel response | Cancelled pre-allocation renewal returns a non-turn success with stopReason cancelled; no allocation/history/idle arm, no pre-run-refusal log. |
| R3 trust ceremony | Candidates survive the permission answer. Retire on session close/suspension or same-server successor; retain at most one candidate per live session/server. No answer-time retirement is authorized without separate ceremony evidence. |
| N-a owner warning record | The owner itself brackets its context exit with both warning snapshots and stores them with survivor/exception/exit facts. A close after natural owner exit consumes that terminal record immediately, never waits on a dead queue; only observable/equal snapshots, no survivor and clean context exit certify release. Test natural child death and unobservable/failed exit. |
| N-b IPC generations | Fresh generation/address; captured-generation-only stop/join/unlink; retain/report an incompletely stopped listener and admit no replacement until it terminates. One serialized off-loop cleanup lane. Tests cover real AF_PIPE/AF_UNIX, concurrent publication, no lost handles and no unlink of a newer socket. |
| N-c repeated cancellation | Shield and track every off-loop session/runtime/IPC close. A second cancellation must not detach the worker: continue joining the same owned job, retaining the underlying worker/future identity. An outer observation bound yields incomplete ownership, never a fabricated release or application of abandoned results. Add double-cancel tests. |
| N-d fixtures/tests | Create the peer script and shared support module; no unit imports from integration/e2e helpers. Admit the enumerated server stream, MCP/Redis shutdown, reader, composition, Stage C and supervisor tests. The live Redis module remains read-only/UNRUN under its separate tier. |
| N-e constructor defaults | Direct adapter/server default None; bootstrap always supplies resolved 3600. Existing library compositions remain disabled unless explicitly wired. |
| N-f join/counter | A normal TurnResponseEnvelope carrying a known allocated noncommit error can arm after FLUSHED; server exception-resend and writer fail-closed/NOT_ATTEMPTED paths cannot. Call the counter idle_epoch, distinct from ConversationState.generation. |
| N-g keyring reads | Newly repeated renewal lookup_durable reads run in the reserved renewal's serialized off-loop lane, with shielded/owned completion and no lease publication after cancellation. Keep trust-store production code read-only. Existing session/new synchronous keyring reads are a recorded pre-existing residual under #302, not newly multiplied by idle cadence or claimed fixed. |
| N-h unnecessary prompts | Arm only when an actual peer was opened; do not count retirement callbacks as peers. Decline the optional separate Chat-activity clock: retain the approved admitted-prompt activity semantics, so admitted Chat can postpone suspension of already-open peers; suspended Chat never reopens them. This avoids an unrequested second idle policy. |
| N-i commands/IDs | Run one configured Mypy selection. The existing finite outbound request-ID iterator (90k IDs) is a disclosed pre-existing server residual under #302, not silently fixed or represented as unbounded by this port. Renewal consumes IDs; the receipt must disclose that limit. No stress loop is authorized to exhaust it. |

**Additional exact interfaces and tests:** session state exposes `has_open_peer() -> bool` based only on registered actual peer ownership, separate from candidate-retirement hooks. Disposition serializes renewal keyring reads and IPC cleanup and provides an awaited drain of its tracked jobs before runtime teardown. Retire-session callbacks are detached/prepared on the serving loop and executed in that owned cleanup lane. Listener generation cleanup removes only the address it created; AF_UNIX ownership is checked before unlinking, and no newer generation may be removed.

Required final focused assertions additionally cover: a clean natural owner exit vs an exit exception or unobservable warning channel; a second serve-task cancellation while a worker is still closing; candidates remaining consumable after an answered permission until session lifetime ends; bounded replacements across repeated idle cycles; fresh listener generation/address and retained incomplete stop; default None library construction starting no sweeper; renewal keyring read leaving the serving loop responsive; current session/new behavior unchanged; known noncommit normal error envelope arming vs writer fail-closed not arming.
