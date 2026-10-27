# ADR-027: Idle client-MCP lifetime while retaining in-memory ACP continuity

Status: operator-approved policy; development released 2026-10-26 under [#427](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/427). Parent #317 and related #302 retain broader resource custody. Implementation acceptance and publication remain separate.

## Context and source

Accepted historical Piece A is an architectural source, not current-main acceptance. Main has in-memory conversation continuity and newer discovery/context behavior; importing the sandbox's durable-resume runtime would change that contract and conflate #240 obligations.

Operator words in shared Codex chat `01a157c0-a950-7c60-84b7-8fc7b9208523`, 2026-10-26: “Approved”; “Please get it reviewed”; “It is an advance approval from my end for you and Claude”; “No need to ask again”. The approved assessment proposed preserving main's in-memory continuity and a standalone positive idle delay instead of synthesizing a session TTL. That sentence describes the accepted policy (paraphrase); it is not an invented verbatim operator quote.

Direct role instruction: “Please start with development: for the Optimus sandbox/ 11.x lanes, you are in the developer seat, and Claude is in the reviewer seat. I intend to continue with the arrangement”. Codex implements; actual Claude CLI reviews. This is a scoped exception to architect-only standing guidance, not release authority.

## Decision and alternatives

Retain ACP session identity and in-memory conversation. Give real SDK contexts one persistent owner; account for release truthfully. Suspend only actually opened idle peers after a determinate turn and confirmed response flush. Default 3600 seconds, positive integer ceiling 2592000, existing monotonic tighten/exact loosen authorization, no launch off value and no synthetic TTL parser. Fresh identity-bound allow_once renewal of the entire former set precedes Plan/Agent allocation; Chat remains no-tools/no-permission. A cancelled preallocation renewal returns non-turn cancelled success. Cleanup uncertainty quarantines rather than pretending release.

Rejected for this delivery: merging the complete sandbox (imports unrelated/durable behavior); fabricating a session TTL (changes continuity); closing ACP sessions instead of MCP peers (loses the accepted in-memory conversation); retaining all peer resources indefinitely (leaves the idle-lifetime defect). Defer real TTL/session-load reconciliation to #240, including idle versus TTL policy there.

## Tradeoffs and validation

Very short delays can cause frequent permission prompts. Logging endpoint snapshots cannot detect a flip and revert entirely between them. Existing session/new keyring blocking and finite outbound IDs remain disclosed #302 residuals. One consolidated implementation/evidence review follows focused development checks; full Windows/WSL checkpoint is separately released. No historical count or platform pass transfers.

The [complete design](../superpowers/specs/2026-10-26-idle-mcp-suspension-main-port-design.md), [v3 plan](../superpowers/plans/2026-10-26-idle-mcp-suspension-main-port_v3.md) and [receipt](../superpowers/reports/2026-10-26-idle-mcp-suspension-main-port-receipt.md) define scope and exact review qualifications. Private archives are provenance only.

## Approved v3 correction and explicit limits, 2026-10-27


Candidate retirement first removes the session's actual permission candidates. The exact typed `LocalIpcError("client_mcp.ipc_stop_incomplete")` from that retirement callback denotes a retained shared listener generation, not uncertain release of the session's MCP peers. It does not by itself quarantine a successfully suspended session or refuse its Chat prompts. The endpoint retains its thread/listener/generation, refuses replacement while that generation lives, and final runtime close still reports incomplete while it is held. Actual SDK/peer uncertainty, another IPC error or a forged `.code` still fails session cleanup. After an incomplete final runtime-close observation, aggregate failure remains sticky; no separate endpoint sticky flag is invented.

Failure ordering attempts adapter, client-MCP runtime, owned writer and reader decision before the enclosing Redis-last cleanup. Preserve the genuine runtime outcome and one bounded MCP-incomplete diagnostic even when the adapter raises. Control-flow takes precedence after owned cleanup; otherwise preserve the first ordinary failure and chain a secondary failure. Repeated cancellation keeps the same MCP worker owned and joined.

There is no outer observation bound for a hung keyring read or arbitrary close hook: shield/join may wait indefinitely. The old N-c outer-bound sentence is not implemented or claimed; #302 retains this residual alongside synchronous session/new keyring access and the finite90k outbound request-ID iterator. No force-kill or new timeout policy is added.

A logging flip and revert entirely between endpoint snapshots can go undetected. Foreign filters on `mcp.client.stdio`, `dictConfig(disable_existing_loggers=True)` or global WARNING disablement can also make the channel unobservable; stdio suspension then remains disabled with bounded WARNING_UNOBSERVABLE diagnostics. No global logging reconfiguration is performed. These limits do not prove a PC-freeze cause or whole-process bounded exit.
