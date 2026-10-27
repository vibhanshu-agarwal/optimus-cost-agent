# Ordering, lifecycle, signals and queue continuation contract

Date: 2026-10-27. Decider: Operator. Developer: Codex. Reviewer: actual Claude CLI.

Decision status: operator-approved requirements and mechanisms, with staged implementation authority. This record is an unpublished draft until first merge. Batch A implementation/focused checks and the checkpoint in S4 are authorized; Batch B, publication, merge, issue closure and cleanup are not released. Technical acceptance requires the measured checkpoint and consolidated review. This is a decision record, not a second work-status register.

## Exact operator source and provenance

Source: the operator turns in Codex chat `01a157c0-a950-7c60-84b7-8fc7b9208523`, reproduced below as a scoped transcript excerpt. The date is this filing's execution date; individual chat timestamps were not supplied. S2 followed the complete corrected plan and its disclosed daemon-stdin proposal. S3 approved only the two-path amendment described below. Headings delimit the excerpt; the operator's words are verbatim.

The UTF-8 excerpt inside the following text fence, from `S1` through the final LF after S4, has SHA256 `7754af85720c382f289c6f8096be7cff3d17fd2250efe0c8bb95f41b63258da1`. A raw private archive is provenance only; the complete scoped text needed to understand this decision is here.

```text
S1 — Operator planning request, Codex chat 01a157c0-a950-7c60-84b7-8fc7b9208523
Please prepare one current-main plan for ordering/lifecycle/signals first, then queue backpressure, including the relevant #427 notes, and have Claude review it. Do not change code, run tests, commit, publish or clean up yet.

S2 — Operator reply to the complete corrected plan and disclosed C2(b) mechanism
Approved

S3 — Operator reply to the exact two-file support amendment question
Approve the two-file amendment

S4 — Operator Batch A checkpoint release
I approve the filing, normal-hook local commit, Windows/WSL full gates and one consolidated Claude review for Batch A. Complete these in one batch. Keep the issues open; do not publish, merge or clean up.
```

## Accepted requirements and agent proposals

The requirements are progress-before-dependent-frame ordering, truthful resource custody through cancellation/shutdown, original failure preservation, useful responsiveness under queue pressure, bounded retained work, and a finite health observation. The numerical choices and mechanisms below are agent proposals accepted through S2 and the approved complete plan; they were not original numeric operator requirements.

- Progress ordering is FIFO admission. One executing and one newest unsubmitted progress event may be retained; the final barrier can own those two completions without waiting for physical flush. Coalesce only unsubmitted progress. Forward every original default-observer event once. Started planner workers and admitted physical sends stay owned until actual completion, with actual settlement receipts.
- One CLI process-stop coordinator covers authorized startup, serving/Runner lifetime, cleanup and the owned Gateway stop. First reason wins; repeated signals count without escalation. Restore exact previous handlers. Atexit may inspect retained state, never create a loop/thread or perform blocking cleanup/I/O.
- Accepted C2(b): one lazy daemon reader owns exclusive ACP stdin operations and one physical completion. Borrowed stdin is not closed or fabricated EOF. The actual CLI uses chunked descriptor reads so a blocked daemon does not hold Python's shared buffered-stdin lock at interpreter finalization. The existing outbound writer remains non-daemon. Arbitrary workers/hooks or a stalled writer may still prevent exit.
- The proposed exit map is clean EOF0, clean SIGINT130, clean POSIX SIGTERM143, completed-but-failed owned cleanup74, and borrowed-stdio-only signal incompleteness75 after the shared10-second observation. Other incomplete ownership stays retained; no clean exit or universal process bound is promised. Windows forced termination is not graceful SIGTERM evidence.
- For #427 F1/F2, capture only this invocation's actual primary, preserve its instance and existing cause/context, prefer control-flow failures, and report secondary failures through one bounded idempotent fixed-stage/count note. This explicitly supersedes only ADR-027's secondary-cause-chain sentence and the identical idle-MCP design sentence. [ADR-027](ADR-027-idle-client-mcp-lifetime-contract.md) remains byte-frozen; its other policy stands.
- #427 F3 uses `--no-renames` in both staged-index and amendment..HEAD prerequisite inventories, checks candidate blobs/digests in that same view, preserves missing-index refusal and frozen exceptions, and records the missing archived-v2 filing pointer.
- Batch B's accepted proposals remain unimplemented here:64 pending application items/16MiB shared resident payload, separate8-slot prompt and non-prompt active pools,256 physical outbound items/16MiB with required/control reserves and one independent stop marker,8MiB frame maximum,64-item/16MiB subprocess inbound retention,256KiB stderr tail with bounded whole-line handling, and a2-second full Redis health deadline. The complete approved plan owns the exact reserve/accounting/control semantics. These are retained-work bounds, not a process RSS guarantee.

## Binding plan and amendment

The [complete plan](../superpowers/plans/2026-10-27-ordering-lifecycle-signals-queue-plan.md) is filed byte-identically to approved SHA256 `59c876f8e065199f0169964c334a289f868a2c8b1345490fd6018fb15ea33b86`. Its dated planning restrictions and unchecked boxes are preserved; this record/S4 supplies subsequent checkpoint authority without rewriting approved bytes.

S3 adds exactly `tools/plan1126_runtime_audit/registry.py` and `tests/unit/acp/test_stage_c_launch.py`, patch SHA256 `5d4473cc8151b63b823aad9d4905d7dafe44643117d9ff133dbc83f5de0a86be`. The former binds the new executing modules without lowering verification floors. The latter keeps the Stage C wiring proof and gives its Redis facade the existing genuine offline runtime/owner fixture, asserting clean physical termination and exactly one client/pool close. No external Redis, provider, Gateway child or real keyring is introduced by that fixture.

Subsequent operator statement S5, verbatim: **“Approve H4 amendment and continue the batch.”** This approves the prepared H4 support proposal SHA256 `96821e660407e60dbe737b1098b56179c96c76408bb1b73f424ae8628a03e0d1` and adds exactly `tools/plan1126_runtime_audit/delivery_characterization.py` and `tests/unit/acp/test_plan1126_delivery_contract.py`. The original S1–S4 transcript excerpt and its digest above are unchanged.

H4's historical execution explicitly selects its complete pinned writer and queue-item definitions in an isolated namespace. Both supplied historical texts must match the same complete source digest before compilation; unknown or altered text is refused. Module registration is temporary for declarations and is removed on both success and failure. Live `optimus.*` modules, import paths and files are not replaced. The remaining lifecycle/settlement/adapter/conversation authority checks and annotation-only exception stay in force. The default live-source mode still rejects changed writer authority, and historical mode refuses the custom-repository test seam. Historical citations now name the writer bytes actually executed; current writer behavior is established by the current writer/lifecycle checks. Historical fixtures, findings, pins and outcomes remain unchanged. This is a Python-only audit mode, never a production/environment/CLI override.

S5 also continues the already authorized affected checks, normal-hook local commit, clean-pin Windows/WSL gate/validity/safety and one final consolidated Claude review. It grants no additional publication, integration, issue closure, Batch B or cleanup authority.

## Alternatives, reasons and costs

1. Maxsize-only blocking queues were rejected: an event-loop producer or a full-queue stop marker can deadlock; count alone does not bound bytes or parked tasks. Batch B instead specifies nonblocking shared credits, finite physical containers, reserved control and explicit terminal outcomes.
2. A wholesale historical sandbox port was rejected: it would mix source pins, unrelated mechanisms and unaccepted evidence. This is a main-based continuation with narrow current-discovery support; historical inventories/replay and masterplan custody stay unchanged.
3. Forced agent/thread termination was rejected: it loses physical ownership and settlement facts and may affect shared resources. Daemon-stdin code75 is a deliberately narrow incomplete result, while non-stdio hangs remain a disclosed limitation.
4. Indefinitely waiting on borrowed stdin was considered for truthful ownership but rejected as the default signal experience. The accepted daemon option retains the pending read and reports incompleteness. It requires safe descriptor ownership and separate native process proof; it does not solve arbitrary blocked work.

## Review, evidence and retained limits

The plan's actual Claude Opus5.5/high review conditionally approved C1–C8 and N1–N12 closure, with an explicit no-further-model-call route for those exact text corrections. The corrected plan bytes were not separately reread. The implementation/filing/evidence receive one consolidated actual Claude review after the source-bound checkpoint; that review has not run at this filing pin. Both agents must review this record before repository delivery.

The [filing receipt](../superpowers/reports/2026-10-27-ordering-lifecycle-signals-queue-receipt.md) distinguishes focused development from authorized-but-unrun full gates at this initial commit. Preserve original failures, UNKNOWN/UNRUN/skips, cache/environment failures, Python/platform differences and actual source pins. No reuse of a pass for changed production bytes is inferred.

Windows native console capability was demonstrated with exact owned target/broker membership and real SIGINT. Earlier containment refusals and one original descendant-completion UNKNOWN remain disclosed. Linux focused signal checks passed but the Windows-specific process guard is unsupported there. External MCP/Gateway/Redis/editor acceptance, whole-resource growth, arbitrary hook termination and PC-freeze attribution remain outside this claim.

## Work authority and next gates

GitHub issues remain the work register: [#302](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/302), [#317](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/317), [#288](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/288), [#333](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/333), [#305](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/305), [#320](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/320) and [#427](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/427). None is closed here; broader #240/#222 and existing #287/#328 custody is unchanged. Batch B waits for Batch A checkpoint disposition or a separate qualified continuation grant. S4 grants no push, PR, merge, issue/label update, archival or worktree/environment cleanup.
