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

The [complete design](../superpowers/specs/2026-10-26-idle-mcp-suspension-main-port-design.md), [v2 plan](../superpowers/plans/2026-10-26-idle-mcp-suspension-main-port_v2.md) and [receipt](../superpowers/reports/2026-10-26-idle-mcp-suspension-main-port-receipt.md) define scope and exact review qualifications. Private archives are provenance only.
