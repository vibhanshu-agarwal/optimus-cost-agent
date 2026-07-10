# Plan 9.8: Task-Aware Workspace Context for Planning

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development before
> implementation. Do not start without reviewer approval of this plan.

**Goal:** Fix the silent READ-only fallback on ordinary mutation requests ("add a docstring," "fix this function") caused by the planner's workspace context being size-capped and task-blind. Correctness floor, not an optimization — high priority because a user who asks the agent to change a file and gets nothing, with no error, is a first-order "the agent doesn't work" failure, independent of the ACP transport fix in Plan 9.75.

**Status:** Drafted 2026-07-10 (priority: high). Not yet implemented. Surfaced during Plan 9.75 Zed verification — the ACP fix made this defect *visible* for the first time; it did not cause it and does not fix it.

**Scope note:** Likely the first of several follow-up plans, not a single fix for "the agent handles mutation tasks generally." Do not describe this plan, once done, as closing more than the specific failure mode below.

## Working hypothesis (mechanism validated by code review; not yet proven as the cause of the observed run)

- `AgentRunner._run_once` builds the planning prompt from `build_agent_planner_input(request.task, workspace_context=gather_workspace_context_for_prompt(request.workspace_root))` (`src/optimus/agent/runner.py:154-155`).
- `gather_workspace_context_for_prompt` caps total included file content at `DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES = 16 * 1024` (16KB) for the **entire workspace** (`src/optimus/agent/workspace_context.py:5`), selecting files via `sorted(root.rglob("*"))` (`workspace_context.py:76`) — alphabetical, task-blind. Anything over budget becomes an `"omitted (size cap)"` marker instead of content.
- The planner grammar requires any `WRITE` to contain "the complete final content of the file... include all existing content that must be preserved" (`src/optimus/agent/prompts.py:18-21`) — the model must have already seen a file to safely rewrite it.
- **This mechanism would produce exactly the observed symptom** (Plan 9.75 Turn 2: "Add a docstring to example.py" against `reports/.plan97-e2e-workspace/example.py` produced READ-only, no WRITE) on any repo whose alphabetically-early content exceeds ~16KB, which this repo's `docs/` tree does.
- **This is a validated hypothesis, not confirmed root cause of that specific run.** Nobody has yet inspected the actual `workspace_context` string passed to the gateway for the Turn 2 planning call to confirm the target file's content was genuinely absent, as opposed to present-but-the-model-chose-READ-only for an unrelated reason.

## Task order (TDD)

1. **Confirm before building:** add a debug-trace line (extend existing `debug_trace.py` instrumentation, or a targeted unit-level introspection) logging whether the target file's content is present in `workspace_context` for a given planning call. Re-run the Turn 2 scenario (or an equivalent) and confirm absence. This is a cheap, fast falsification step before investing in the fix — if the file *was* present and the model still chose READ-only, the root cause and the fix are different.
2. Implement task-aware file prioritization once confirmed.
3. Unit tests per Definition of Done below.
4. Live Zed/gateway re-run.

## Explicit scope boundaries

**In scope:**

1. Task-aware file prioritization: extract file paths referenced in `request.task` and guarantee they're included in context ahead of alphabetical filler, regardless of sort order.
2. **Ambiguous basename handling, explicitly defined, not left implicit.** If the task references a bare filename (e.g. `example.py`) matching multiple files in the workspace, the fix must not silently pick one (that just reintroduces this plan's own failure mode in a new shape). Define one of: (a) include all candidates' content, bounded, and let the model's plan disambiguate via its READ/WRITE path choice; (b) treat as unresolved and fall back to current behavior with a distinct log/telemetry signal for "ambiguous reference, no prioritization applied" so it's diagnosable, not silent. Pick and document the choice as part of this plan, don't defer it.
3. Distinguish budget-driven omission from a deliberate model READ-only decision — today both look identical to the user.
4. Review whether 16KB remains defensible after prioritization — allowed to raise it, not required to.

**Out of scope (expect a follow-up plan, not a single fix):**

- Multi-turn read-observe-then-write loop redesign, if prioritization alone proves insufficient for tasks touching many/large files — candidate Plan 9.85 if needed.
- Full context-window intelligence (relevance ranking, embeddings, context-regret scoring, ablation suites, calibrated cost-savings gates) — remains **Plan 11** (renumbered from Plan 10), unchanged.
- Plan 10 (renumbered from Plan 9.8)'s Unified Gateway Capabilities Broker — unrelated.

## Definition of Done

**Unit-provable (deterministic guarantee):**

- A test asserting that for an explicit, unambiguous relative path referenced in `request.task`, that file's content is present in the assembled `workspace_context` even when alphabetical filler exceeds the 16KB budget on its own. This tests the context-assembly function directly.
- A test asserting the defined ambiguous-basename behavior from scope item 2 (not "the fake model returned a WRITE" — that only proves the fake was configured to do so).

**Not unit-provable — requires live evidence:**

- A real Zed/gateway run (actual model, not a mock) against a scenario equivalent to Plan 9.75 Turn 2, producing an actual `WRITE` directive and a real file mutation after approval, with `debug-acp.ndjson` + Zed log correlation committed to `reports/`, matching the evidentiary bar already established for Plan 9.75. A mocked-runner test turning READ-only into WRITE is not acceptable as the sole proof of the fix — it only tests the mock's configured response, not real model behavior given correctly-populated context.

**Docs:**

- Evidence/README updates describe this as closing one specific failure mode (silent READ-only fallback due to budget/ordering), not "mutation tasks now work generally."

## Relationship to other plans

- Directly downstream of Plan 9.75's runtime evidence — that fix made this defect observable; this plan fixes what became visible.
- Distinct from Plan 10 (Unified Gateway Capabilities Broker, renumbered) — no overlap.
- Distinct from Plan 11 (Context Window Optimization and Intelligent Selection, renumbered) — 9.8 is a correctness floor; Plan 11 is an efficiency/intelligence layer built once that floor holds. Update Plan 11's roadmap entry to note it now depends on Plan 9.8 having landed.
