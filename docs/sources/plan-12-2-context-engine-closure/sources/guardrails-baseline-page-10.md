# 7. Bounded Agent Loops / Goal-Driven Execution

An agent loop re-runs a single agent with fresh context each iteration, tracking progress in files
and git rather than in an ever-growing chat context. It uses the same compression principle as
subagents - keep the live context small, push state out to the filesystem, restart clean - but
applies it every iteration rather than once per delegation. The result is long-running work that
does not degrade as the context window fills with stale reasoning and dead ends.

The pattern excels at grindy, well-bounded work: migrating a large codebase one file at a time,
processing a queue of items, or refactoring across many call sites. A completion condition is set
(for example, "all tests in test/auth pass and lint is clean"); after each iteration a small evaluator
model checks whether the condition holds, and the loop stops when it does.

## 7.1 Phase 1 Stance

Support the pattern architecturally - the contracts below are part of Phase 1. Do not make it the
default execution mode. Enable only for tasks with measurable completion criteria. Representative
valid loop tasks include migrating all call sites from API A to API B and stopping when tests pass,
processing a queue until all items are marked complete, and refactoring until lint, type-check, and
tests pass.

## 7.2 Required Controls

Persistent state lives in files, git history, task manifests, traces, and the evidence ledger -
never in an ever-growing chat context. Every loop runs under hard, explicit bounds:

| Control | Purpose |
|---|---|
| max_iterations | Hard ceiling on loop turns. |
| Independent evaluation cap | Optional explicit policy only for independently capped evaluation callers; not a product LoopBudgetPolicy requirement. Actual product costs and alerts remain. |
| max_wall_clock_minutes | Time bound independent of iteration count. |
| explicit completion condition | Machine-checkable predicate that ends the loop. |
| per-iteration evidence | Each turn writes evidence to the ledger (LLD §9E). |
| clean git-diff check | Working tree verified between iterations. |
| pre-tool guard active | §3 enforcement is never bypassed inside a loop. |
| human approval for escalation | Out-of-band actions require sign-off. |
| stop on repeated failure | Identical-failure pattern terminates the loop. |

Retain exactly-once cost accounting and configured alerts. Product count/time/failure controls remain finite; evaluation monetary policy is explicitly scoped.

At cf9bb9d, product LoopBudgetPolicy retains count/time/repeated-failure bounds with max_budget_usd=None. Only an explicit independently capped evaluation supplies a dollar ceiling; non-ACP execution is not automatically evaluation. Unknown accounting never latches a product goal-loop session; an independent evaluation can stop its own calls.
