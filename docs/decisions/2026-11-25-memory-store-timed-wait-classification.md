# Memory Store timed waits that expire before the request clock

**Decision status** The operator accepted the early-expiration rule and its five approved boundaries on 2026-11-25. Codex selected the implementation below. The decision clarifies [ADR-042](ADR-042-memory-store-topology-commit-and-recovery.md). Work ownership, source review, and delivery gates live in [#614](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/614).

## Context and provenance

The [#325](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/325) Windows ordinary hook observed a stalled Redis fsync recheck classified as unavailable and a timed read-lock wait classified as busy. A separate guarded native run showed that both platform waits expired about 8 ms before the outer monotonic request deadline. [ADR-042](ADR-042-memory-store-topology-commit-and-recovery.md) supplies the original absolute deadline, connection verification, and durability rules. It did not settle the classification of an earlier native wait expiration.

The operator gave this direction in the #325 Codex remediation chat on 2026-11-25.

> Approved. Please proceed with the remediation batch for both failure classes through review and PR/CI, without further per-file approvals. Keep the fixed 694-path cohort, merge hold and broader rollout hold.

That approved the packet identified by SHA-256 `277c42711b461341591db68ef68be6560cee03636156a9813a57197093c90061`. Its classification rule is stated below so this record needs no copy of the local packet. The quoted approval covers implementation and review through PR CI. Merge authority remains separate.

The Windows candidate passed the two original fixes but its initial focused run had three independent failures at the service's capabilities reply, verification startup and lease confirmation. A separate instrumented observation attributed the repeated lease failure to a typed socket timeout before the outer deadline, after `EXEC` and during `WAITAOF`. That observation also demonstrated a watchdog closing the capabilities socket and a wrapped verification timeout. Both passed in that observation. The first failures retain their original outcomes and unobserved timing. [Published evidence](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/614#issuecomment-7170244087).

The operator expanded the approved scope in the same chat on 2026-11-25.

> Approved v2. Please proceed with the memory remediation through review and PR/CI without per-file approvals. Keep the fixed 694-path cohort, merge and broader rollout holds, and Gateway’s separate block.

That approval binds the v2 packet identified by SHA-256 `59c985339987e94c1c07f3462b5032d08a5862586881a96c249bbaaa50fa6126`. [Published approval](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/614#issuecomment-7170395951).

## Decision

A primitive wait that consumes the offered full request budget reports `MEMORY_TIMEOUT` even when the outer monotonic comparison shows a small remaining slice. A genuine early disconnection retains its boundary's prior result. A lock wait with no explicit caller deadline keeps `MEMORY_BUSY`. The absolute request deadline and write-confirmation rules in ADR-042 still apply.

The approved boundaries are the full-budget read lock, fsync recheck, capabilities reply, verification startup, and lease acquisition confirmation. The read lock uses its timed acquire result and the caller's deadline. The fsync recheck preserves a typed Redis timeout or explicit local deadline expiration after invalidating its connection.

For the added boundaries, Codex selected evidence tied to the tracked socket. A typed Redis read timeout can carry the full-budget result when the read used the configured request remainder. A local closed-socket error can carry the watchdog result when the watchdog closed that same socket. A coincident peer reset or a cut of another socket provides no such evidence. Redis retains its original exception type and cleanup. On redis-py upgrades, recheck the default response timeout, wrapped socket errors, and the native regression controls. Verification follows the startup exception's cause. Lease confirmation invalidates the connection on transport failure and reports timeout when it has request-budget evidence. A sent lease stays uncertain and yields no token. Capped server waits that return zero, shorter socket waits, and other write confirmation paths retain their prior behavior.

## Alternatives and trade-offs

The original outer-clock-only mapping lost a typed budget failure when the platform returned just before the clock boundary. A global elapsed-time tolerance would also classify some genuine disconnections as timeouts. Waiting on the lock again adds another platform wait. Repeating a Redis probe or write risks acting again after a potentially effective first attempt. The chosen design reports observable failure evidence at the approved boundaries and can return before the absolute deadline. Any scope expansion requires a separate decision and evidence.
