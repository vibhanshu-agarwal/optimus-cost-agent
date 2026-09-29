---
title: "Optimus-Cost-Agent - Agent Execution Guardrails and Workflow Strategy v1.1"
lang: en
---

::: {.sheet .cover .guard data-doc="Optimus-Cost-Agent - Guardrails and Workflow v1.1" data-page="1" data-total="16"}
<div class="eyebrow">Optimus-Cost-Agent</div>

# Agent Execution Guardrails and Workflow Strategy

<div class="subtitle">Layered Safety Controls and Bounded Execution - Phase 1 Companion Specification</div>

<div class="version">Version 1.1</div>

<div class="credit">Architected by: Vibhanshu Agarwal</div>
:::
::: {.sheet .guard .tight data-doc="Optimus-Cost-Agent - Guardrails and Workflow v1.1" data-page="10" data-total="16"}
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
| `max_iterations` | Hard ceiling on loop turns. |
| `max_budget_usd` | Gateway USD cap across the whole loop, reconciled from provider-reported cost. |
| `max_wall_clock_minutes` | Time bound independent of iteration count. |
| explicit completion condition | Machine-checkable predicate that ends the loop. |
| per-iteration evidence | Each turn writes evidence to the ledger (LLD §9E). |
| clean git-diff check | Working tree verified between iterations. |
| pre-tool guard active | §3 enforcement is never bypassed inside a loop. |
| human approval for escalation | Out-of-band actions require sign-off. |
| stop on repeated failure | Identical-failure pattern terminates the loop. |

`max_budget_usd` is the separately reviewed USD field rename; it does not add a cross-run limit.
:::

::: {.sheet .guard .tight data-doc="Optimus-Cost-Agent - Guardrails and Workflow v1.1" data-page="11" data-total="16"}
The completion evaluator must be a cheap model routed through the strict-loopback Optimus Gateway,
not the main reasoning model, and `max_budget_usd` is enforced by the same local Gateway budget
policy against provider-reported cost as every other call. The evaluator uses the developer-owned
aggregator account through the Gateway, has no direct provider credential or provider adapter, and
emits OTel/OTLP telemetry through authenticated Gateway trace ingress with no separate observability
backend or billing path. It fails closed when reported usage/cost is missing or malformed.

# 8. Curated Workflow Skills

Project configuration is for always-on rules; skills are on-demand procedural workflows loaded only
when relevant. A skill is Markdown with YAML frontmatter - a name and description tell the agent when
it applies, and an optional `globs` field narrows it by file type or path. Keeping procedures out of
the always-on context and loading them only on match keeps the live prompt small while preserving
repeatable execution knowledge.

The evidence is strong that this matters for cost as much as quality. On SkillsBench (86 tasks across
11 domains), a small model given good human-curated skills outperformed a flagship model without
them. When models were allowed to write their own skills the gains disappeared: generic,
self-generated boilerplate makes things worse. Config files therefore hold always-relevant rules,
curated skills hold reusable task-specific procedures, and the live prompt holds what is unique to
the current task.

## 8.1 Skill Rules

- Curated, reviewed, and versioned - skills are managed artifacts, not ad-hoc notes.
- Short and focused - prefer narrow skills over broad documentation dumps.
- Procedures, not advice - a skill encodes a concrete workflow, not vague guidance.
- Support files allowed - scripts, templates, and examples may accompany a skill.
- Metadata required - name, description, applicable file globs, allowed tools, owner, version, and
  trust level.
- Generated skills are draft-only - a model-authored skill is never trusted until reviewed and
  promoted.

## 8.2 Trust & Invocation

Skills are governed by the same permission posture as everything else. A skill's declared
`allowed_tools` are enforced by the pre-tool guard (§3) - a skill cannot widen the agent's tool
surface - and a skill can never override project or user deny rules (§2.2). The `SkillRegistry`
resolves a matching `SkillManifest` only when its description/globs match the task, and
`SkillTrustPolicy` blocks any untrusted or unreviewed (draft) skill from loading in Agent mode.
:::

::: {.sheet .guard .tight data-doc="Optimus-Cost-Agent - Guardrails and Workflow v1.1" data-page="12" data-total="16"}
# 9. Cost Model Alignment

The guardrail and workflow strategy fits Optimus precisely because most of it is deterministic and
low-token. The governing rule is: rules first, a small-model classifier only when needed, and human
approval for high-risk uncertainty.

| Control layer | Mechanism | Cost profile |
|---|---|---|
| Permission rules (§2) | Allow/deny lists, mode overlay | Zero LLM cost |
| Pre-tool guard (§3) | Regex / rules / AST / path checks | Zero LLM cost |
| Shell validation (§4) | `CommandSafetyValidator` | Zero LLM cost |
| Injection / MCP defense (§5) | Registry, hashing, config scan | Zero LLM cost |
| Pre-commit / CI (§6) | Ruff, Bandit, AST-grep, tests | Compute, not tokens |
| Bounded loops (§7) | Cheap evaluator + hard budgets | Net cost reduction under caps |
| Workflow skills (§8) | On-demand procedure loading | Token saving; smaller model viable |
| Borderline classifier | Cheap model via Optimus Gateway, strict budget | Rare, budgeted, off the hot path |

Every model-touching element in the strategy - the borderline permission/guard classifier and the
loop completion evaluator - is routed through the same loopback Gateway, developer-owned aggregator
account, USD budget, provider-reported cost ledger, and OTel/OTLP trace path as all other calls.
There is no second, ungoverned cost path introduced by guardrails.

# 10. Implementation Contracts (LLD Anchor)

The following components form the Phase 1 enforcement and workflow surface. They are specified in
full in LLD §12 (Guardrail & Workflow Component Contracts); this section is the authoritative
inventory and the representative shape of the core types.
:::
