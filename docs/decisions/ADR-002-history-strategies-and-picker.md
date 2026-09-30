# ADR-002: History strategies (compaction default, hybrid, sliding window) and the IDE picker

**Status:** Accepted.
**Dates:**

- 2026-09-29: operator decisions.
- 2026-09-30: exact definitions agreed by Claude and Codex.

**Deciders:** the operator decided the strategies and picker. Claude and Codex agreed the definitions.

## Context

**Operator decisions, 2026-09-29.** These are paraphrases. They are recorded in Claude's memory note "Plan
12 discovery inventory" and in the handoff
`optimus-handoff\plan-12-discovery\2026-09-30-context-compaction-handoff.md` §3, which is outside the
repository:

- The engine offers three history strategies: **compaction (the default)**, **hybrid** and **sliding
  window**.
- The **user** may choose in the IDE. This refines the operator's 2026-09-28 "no profiles" ruling for
  this one choice.
- Sliding-window use case: "sequential independent tasks A->B->C in one thread, where the start of the
  conversation is no longer needed."
- The picker appears **only when the engine is attached**.
- Choosing sliding window **must tell the user that older content is dropped**.

**Source of the hybrid definition.** The operator's 2026-09-28 brainstorm list defines hybrid as "pinned
head + recent turns verbatim + summary of the middle" (diary line 36).

## Options considered

| | A: one strategy (compaction only) | B: three strategies, chosen by the user (chosen) | C: the engine picks automatically |
|---|---|---|---|
| User control | None | Full | None |
| Complexity | Lowest | Medium: three code paths and a picker | High: needs a reliable policy |
| Fit with the A→B→C use case | Poor: old tasks are still summarized into the context | Good: sliding window | Depends on the policy |
| Risk of surprise | Low | Medium: sliding window drops content, hence the warning | High |

- **A.** For: simplest. Against: does not serve the operator's sliding-window use case.
- **B.** For: user intent is explicit, and the default is safe. Against: more to test, and users must
  understand the options, hence the warnings.
- **C.** For: no user effort. Against: opaque. A later automation (see ADR-007/009, for example Jev
  detecting task boundaries) can suggest a switch; it should not silently change the user's choice.

## Decision

Option B. The exact definitions are selection rules over committed turns.

- **Compaction (default).** Structured summaries of older ordinary history, plus a bounded exact recent
  tail.
- **Hybrid.**
  - The first committed turn stays exact as an anchor, if it fits the anchor allocation. Otherwise it
    joins the summary.
  - The middle is summarized, and a larger bounded exact tail is kept.
  - There is no user-pin API in this slice.
  - "Later turns take precedence" is conveyed by numeric order and turn numbers only. There is no
    semantic correction detector.
- **Sliding window.** The newest complete turns that fit the history allocation. There are no summary
  calls, so the strategy has no summarizer cost.
- **In all strategies,** each turn's outcome, effect state and approval decisions stay exact, and
  summary text is fenced as inert data. If required exact state cannot fit, the turn is refused; it is
  never summarized away.
- **The picker.**
  - An ACP config option with `configId: "context_strategy"` and category `_context_strategy`, advertised
    only when the engine is attached.
  - Updates are sent as `config_option_update` carrying the **full** option set (mode + strategy),
    because the pinned ACP schema defines the set as full.
  - Mode and strategy share one per-session lock and one resync flag.
- **Sliding-window warning.** The option's description says older content is dropped, and a live-only
  notice appears on the first turn after switching.
- **Per-turn capture.** Each admitted turn freezes its strategy, its parameters and the history revision.

## Consequences

- **Harder:** three selection paths to test; compaction and hybrid must produce different views of the
  same history.
- **Harder:** the Zed persisted default (`default_config_options`) will send `context_strategy` even
  when the engine is absent. A free check must confirm that the rejection does not break new threads.
- **Revisit** once a user-pin surface exists in ACP clients, or once measured quality shows hybrid and
  compaction are indistinguishable.
