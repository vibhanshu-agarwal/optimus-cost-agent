# ADR-001: The Context Engine is a separate, loosely coupled product; the Optimus floor stays

**Status:** Accepted.
**Dates:**

- 2026-09-28 and 09-29: operator decisions.
- 2026-09-30: design details agreed by Claude and Codex, after three rounds.

**Deciders:** the operator decided. Claude and Codex agreed the details.

## Context

**Operator statements.** These are recorded in the operator's handoff folder, outside the repository:
`optimus-handoff\plan-12-discovery\plan-12-brainstorm-diary.md`, entry "2026-09-28 — Big one: the Context
Engine is its own product". The diary entry is Claude's record of
them, so they are paraphrases, not verbatim quotes:

- **Decision:** context-window management, memory management and the rest become a **Context Engine**,
  independent from Optimus and **very loosely coupled**, in the same way the A2A ledger and the evidence
  collector were split out.
- **Clarification:** "Optimus will technically run without the engine, but it would be a very dumb agent,
  so in practice nobody would use it that way. The real reason for separation is **productization**: I
  should be able to move the engine out as its own product and plug it into *any* other agent in the
  future, through an API or some other means."
- **Correction:** "ACP is a common format, like MCP, so there is no reason to avoid it ... For now, do
  **not** spend time on how the engine would work with other agents. The requirement is simply **loose
  coupling**, so that separating the two later is modest effort rather than a major untangling."

**Product boundary (operator, 2026-09-29).** Plan/Chat mode is core Optimus. Context compaction belongs
to the engine. Optimus must keep working when the engine is absent.

## Options considered

| | A: engine code inside Optimus modules | B: separate package in the Optimus repo (chosen) | C: separate repository or service now |
|---|---|---|---|
| Complexity now | Low | Medium | High |
| Cost of extracting it later | High: tangled | Modest | None |
| Speed of iteration | Fastest | Fast | Slow: two release trains |
| Risk to core Optimus | Engine bugs reach core paths | Contained by an import boundary | Contained, but adds network and deployment failure modes |

- **A.** For: least ceremony. Against: violates "loose coupling", and productization later means a major
  untangling.
- **B.** For: meets the operator's "modest effort to separate later" test at low cost today. Against: the
  boundary needs discipline, so it is enforced by a test.
- **C.** For: maximum separation. Against: the operator explicitly said not to spend effort on
  multi-agent use yet.

## Decision

Option B, with these details agreed by Claude and Codex on 2026-09-30.

- **Package boundary.**
  - The engine is its own package and imports nothing from `optimus`, `optimus_gateway`,
    `optimus_security` or `evidence_handoff*`.
  - This is enforced by an AST test and a fresh-process `sys.modules` test.
- **Model access.** The host injects Gateway access, so the engine never holds keys and cost stays on the
  one ledger.
- **Sanitization.** The host passes records in already sanitized, and re-sanitizes engine output before
  it enters a prompt.
- **Records and derived views.**
  - Optimus's conversation records stay authoritative.
  - Engine checkpoints are derived, versioned views, published only for the current history revision.
  - A stale or cancelled checkpoint is discarded, and its cost still counts.
- **The floor stays unchanged when the engine is absent.** Optimus keeps full verbatim history, the 80%
  warning and the 512 KiB cap, per the operator's 2026-09-29 decision.

## Consequences

- **Easier:** extracting the engine later, and testing the engine alone.
- **Harder:** every piece of host–engine data crosses an explicit interface.
- **A prerequisite:** the narrow "context floor" port. It covers notice separators, a readable `end_turn`
  on the cap refusal, and usage updates, reconciled with Chat mode. The engine's new notices would
  otherwise inherit Zed's display defects.
- **Revisit** when a second agent actually needs the engine (the operator said: not now).
