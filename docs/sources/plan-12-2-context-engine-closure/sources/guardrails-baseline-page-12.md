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
| Bounded loops (§7) | Cheap evaluator + finite work bounds | Net cost reduction under caps |
| Workflow skills (§8) | On-demand procedure loading | Token saving; smaller model viable |
| Borderline classifier | Cheap model via Optimus Gateway, finite work bound | Rare, bounded, off the hot path |

Every model-touching element in the strategy - the borderline permission/guard classifier and the
loop completion evaluator - is routed through the same loopback Gateway, developer-owned aggregator
account, finite work/capacity controls, provider-reported cost ledger, and OTel/OTLP trace path as all other calls.
There is no second, ungoverned cost path introduced by guardrails.

# 10. Implementation Contracts (LLD Anchor)

The following components form the Phase 1 enforcement and workflow surface. They are specified in
full in LLD §12 (Guardrail & Workflow Component Contracts); this section is the authoritative
inventory and the representative shape of the core types.

Classifier/completion-evaluator model capabilities in this cost posture are reserved, not proof of current activation.
