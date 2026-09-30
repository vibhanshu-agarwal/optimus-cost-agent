# ADR-011: How decisions are recorded

**Status:** Accepted. **Date:** 2026-09-30. **Decider:** the operator set the requirement and chose the
repository home. Claude proposed the mechanism, and Codex agreed and drafted the AGENTS.md rule.

## Context

**Operator, verbatim (2026-09-30):**

> "Importantly, I hope this context can be saved in some way - often my requirements gets lost or
> oversimplified losing the original context and reasoning. Architectural decisions should not be binary
> - must be supported by proper reasoning and tradeoff analysis"

**Observed failures:**

- **Agent choices read as operator requirements:**
  - the $0.05 per-turn budget (Plan 9.5 default);
  - "100K inside 128K" (Claude's withdrawn proposal);
  - the 3-planning-turn cap.
- **A real operator requirement shrank to one diary line:** "curbing unnecessary agent loops".
- **Operator rulings were paraphrased** in handoffs and memory, losing the reasoning.

**Existing mechanisms and their limits:**

- **Claude's memory is private.** Codex cannot read it, and AGENTS.md says a private memory is only a
  backstop.
- **Reviewer checkpoint logs** (`docs/superpowers/reviews/*-review-checkpoints.md`) are gitignored and
  kept per worktree. An agent in another worktree has read one as "absent".
- **The handoff folder** is shared but not versioned.

## Options considered

| | A: Claude memory | B: shared handoff folder (the first drafts) | C: in-repo `docs/decisions/` plus an AGENTS.md rule (chosen) | D: reviewer checkpoint logs |
|---|---|---|---|---|
| Readable by every agent | No | Yes | Yes | No: per worktree |
| Versioned and reviewed | No | No | Yes | No |
| Survives machine or folder loss | Partly | No | Yes (git remote) | No |
| Friction | None | Low | A docs PR per decision batch | Low |

## Decision

**Operator, verbatim (2026-09-30):** "These should be in the repo and agreed by both you and Codex".

- **Option C.** The log lives in `docs/decisions/` and follows the rules in its [README](README.md).
  - A fully superseded record moves unchanged to `archive/`, following the repository convention. The
    decisions index keeps a resolvable link to its archived location and marks its effective status.
  - `docs/README.md` indexes each record, and `tests/unit/docs/test_docs_index.py` includes the folder.
  - Records freeze byte for byte when they first merge to `main`.
- **Records enter the repository only after Claude and Codex both agree.** The operator then decides the
  push, the PR and the merge.
- **AGENTS.md rule.** Codex drafted the section "Architectural decisions and requirement provenance" on
  2026-09-30. Claude reviewed it and applied it verbatim in the same change as this log.
- **Verbatim quotes need a shared source.** The operator's messages come from a hashed transcript export
  (README rule 1, source S1). Private agent memory is not a source.
- **Claude and Codex decided the testing.** The operator delegated it: "The doc tests were written by
  agents not my requirements, so you and Codex decide".
  - Keep the three-line docs-index integration. A negative probe proves it catches an unindexed record.
  - Add no byte-pin test for immutability; git history and review enforce it.

**Authority boundary:**

- **Accepted by the operator:** the requirement and the repository home.
- **Agreed by Claude and Codex:** the mechanism.
- **Not commissioned:** any commit, publication or merge.

## Consequences

- **Easier:** no requirement is lost again, and a fresh agent can read why something was decided.
- **Harder:** recording is a small extra step at each decision.
