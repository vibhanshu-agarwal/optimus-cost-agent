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
::: {.sheet .guard data-doc="Optimus-Cost-Agent - Guardrails and Workflow v1.1" data-page="10" data-total="16"}
# 7. Bounded Agent Loops and Goal-Driven Execution

## 7.2 Required controls

| Control | Purpose |
|---|---|
| `max_iterations` | Hard ceiling on loop turns |
| `max_budget_usd` | Local Gateway USD cap across the whole loop, reconciled from provider-reported cost |
| `max_budget_tokens` | Optional token ceiling for diagnostic policy |
| `max_wall_clock_seconds` | Time-bound independent of provider latency |
| explicit completion condition | Deterministic stop when the task is complete |
| stop on repeated failure | Prevent unproductive retries |

`max_budget_usd` is part of the separately reviewed USD field rename. It does not add a cross-run
limit; cross-run policy remains independently owned.

The Gateway process is authoritative for the current run's budget because it is isolated from the
LLM-driven agent and owns the validated provider-usage ledger.
:::

::: {.sheet .guard data-doc="Optimus-Cost-Agent - Guardrails and Workflow v1.1" data-page="11" data-total="16"}
# Completion evaluation cost control

The completion evaluator must be a cheap model routed through the strict-loopback Optimus Gateway,
not the main reasoning model. `max_budget_usd` is enforced by the same local Gateway budget policy
against provider-reported cost as every other model call.

The evaluator:

- uses the developer-owned aggregator account through the Gateway;
- has no direct provider credential or provider adapter;
- emits OTel/OTLP telemetry through authenticated Gateway trace ingress;
- has no separate observability backend or billing path;
- fails closed when reported usage/cost is missing or malformed.

::: {.callout}
This is part of the separately reviewed, wire-aware USD field rename. It changes naming, not the
existing USD meaning, and adds no cross-run budget policy.
:::

# 8. Curated Workflow Skills

Skills remain curated, reviewed, versioned, narrow procedural artifacts. They cannot widen tool
permissions, override deny rules, or promote model-authored drafts without review.
:::

::: {.sheet .guard data-doc="Optimus-Cost-Agent - Guardrails and Workflow v1.1" data-page="12" data-total="16"}
# 9. Cost Model Alignment

Every model-touching guardrail uses the same:

- strict-loopback Gateway;
- developer-owned aggregator account;
- current-run USD budget;
- provider-reported cost ledger;
- OTel/OTLP trace path.

Guardrails introduce no second credential, direct provider adapter, ungoverned cost path, or
observability backend dependency.

| Control layer | Mechanism | Cost path |
|---|---|---|
| Permission rules | allow/deny tools, modes, and paths | zero model cost |
| Pre-tool guard | policy classification and validation | zero model cost |
| Shell validation | deterministic command checks | zero model cost |
| Prompt-injection defense | deterministic patterns plus gated model check | Gateway-governed when used |
| Completion evaluator | cheap dedicated model | Gateway provider-reported USD cost |
| Workflow skill | on-demand procedural knowledge | zero model cost |
| Bounded loop | current-run `max_budget_usd` | Gateway-authoritative |

# 10. Implementation contracts

The LLD remains authoritative for permission enforcement, prompt-injection and MCP trust controls,
bounded loops, curated skills, and the local Gateway accounting/telemetry boundary.
:::
