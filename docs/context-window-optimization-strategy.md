# Context Window Optimization and Intelligent Selection Strategy

Status: standalone evaluation/design document
Sign-off: senior architect approved on 2026-07-01
Scope: Optimus Cost Agent context-window optimization policy. This document is intentionally separate from the HLD and LLD until gates, traces, and ablations are defined.

## Executive Summary

Optimus uses **Context Window Optimization** as the umbrella. Intelligent Pruning is a named strategy inside it, but the primary control plane is **Intelligent Selection**: select, pack, summarize, invalidate, evict, and measure.

The objective is to make the agent smarter while reducing fully-loaded cost. Fully-loaded cost includes final prompt tokens plus the selection, retrieval, reranking, compression, summarization, and evaluation machinery used to construct the prompt.

The accepted sequencing is:

1. Keep this document as the standalone evaluation/design doc.
2. Define gates, traces, ablations, and calibration baselines.
3. Fold only the accepted policy into the HLD and LLD later.

## Cost Attribution Prerequisite

Cost attribution is a hard prerequisite. Every prompt block, retrieval step, compression step, summarization step, reranking step, and model call must be attributed by the Optimus Gateway to:

- strategy
- stage
- run_id and session_id
- token count
- cost_usd
- cache_hit
- model and provider

Without this attribution, cost gates are not measurable and the optimization layer must fail closed.

## Context Type x Mechanism Matrix

These mechanisms run simultaneously on different context slots. "Fallback" is not a global strategy swap; it is criteria-triggered graceful degradation, scoped per context slot, time-bounded, traceable, and protected by hysteresis/cooldown.

| Context slot | Normal mechanism | Degraded mechanism |
| --- | --- | --- |
| Policy, mode, approvals, mutation state | Pinned, cache-stable prefix | Fail closed; never compress |
| Active task, latest user intent | Pinned dynamic block | Ask/refresh; never infer silently |
| Decision, constraint, and evidence ledger | Pointer-backed exact evidence plus compact state | Exact pointer refresh; never lossy-summarize approvals, diffs, or errors |
| Code symbols and call sites | Freshness-gated intelligent selection plus dependency closure | Repo-map ranking or exact reread |
| Tests, configs, fixtures | Dependency closure from selected code | Refresh required artifacts |
| Conversation history | Condensation with exact recent turns | Recent-only trim |
| Tool output, logs, web/docs | Trust-gated retrieval compression | Extractive snippets or drop optional items |
| Long reference docs | Retrieval compression plus summaries | Section-level retrieval |
| Prose overflow | Last-mile compression | Summarize or omit optional prose |

## Selection Pipeline

```text
cost attribution check
-> source trust pre-filter
-> source freshness/index confidence pre-filter
-> retrieve candidates
-> per-candidate trust check
-> per-candidate freshness re-check
-> score marginal utility
-> resolve dependency closure
-> pack under budget
-> compact if needed
-> trace outcomes and regret
```

Trust and freshness are two-phase controls. Source/index filters reduce bad candidates before retrieval, but the hard guarantee is enforced after retrieval on each concrete span or artifact. Retrieved content must carry:

- source type
- authority class
- file path or artifact pointer
- content hash or commit/mtime
- retrieval time
- freshness state

Retrieved files, docs, web output, and tool output are treated as data, not instructions. Policy, approval state, tool contracts, and developer instructions remain non-prunable and instruction-bearing.

## Freshness and Dependency Precedence

Freshness wins all conflicts. If a required dependency is stale, the resolver refreshes it by rereading the current artifact. It must not keep stale evidence, and it must not silently drop required evidence.

If the fresh, required dependency closure still cannot fit within the current budget, the resolver must use this precedence order:

1. Evict lower-priority optional slots according to the context matrix.
2. Degrade optional mechanisms for the affected slot.
3. Request a bounded budget escalation if policy allows.
4. Abort the turn cleanly with an evidence report.

Required fresh evidence is never silently dropped to satisfy a token budget.

## Selection Model

Candidate chunks are scored using normalized, weighted features. Token cost is primarily the packing constraint, not also a numerator penalty.

```text
utility(chunk | selected) =
  weighted_relevance
+ dependency_coverage_gain
+ authority
+ recency
+ user_pin
+ failure_recurrence
+ evidence_diversity_gain
- redundancy_penalty
```

`evidence_diversity_gain` measures coverage of distinct symbols, files, concepts, tests, configs, or failure modes. `redundancy_penalty` measures near-duplicate text or already-covered evidence. These should remain separate only if implemented on distinct axes.

Selection is a coverage-aware packing problem with prerequisites, not a clean independent knapsack. Greedy utility-per-token is acceptable for Phase 1, but each selected chunk must include required dependency closure: definitions, relevant config, fixtures, failing tests, or call-site context.

## Prompt Packing and Cost Controls

Prompt/KV caching is a first-class cost feature. Stable policy, mode rules, safety contracts, tool schemas, and workflow scaffolding should form a byte-stable cached prefix. Dynamic task state, latest diff, latest error, and tool output should appear later.

Cache savings must be modeled conservatively: prefixes must be byte-stable, timestamps or reordering can bust the cache, and provider TTLs mean cache benefits are strongest within active work bursts.

Cheap model tiers may perform summarization, reranking, and completion evaluation, but only behind a quality floor. A cheap reranker must not materially degrade coverage@line-budget, patch correctness, or downstream task success compared with the stronger baseline.

Retrieval results should be cached per task and invalidated using the same file hash, commit, and freshness metadata used for stale-context filtering.

## Compaction

Compaction is triggered by explicit high-water marks:

- Context window usage exceeds threshold.
- Agent loop reaches an iteration boundary.
- Tool output exceeds a configured budget.
- Repeated failure indicates the working set is polluted or incomplete.
- Model tier downgrade requires smaller prompt input.
- User changes scope or approval state.

Compaction stores structured pointers and hashes for exact evidence. Approvals, diffs, error traces, signatures, policy constraints, and test failures should remain pointer-backed or verbatim. Summaries are appropriate for reasoning history, prior attempts, and narrative progress.

## Offline Promotion Gates

Offline promotion gates decide whether Intelligent Selection remains enabled for a tested distribution. Thresholds such as 15% savings and "no material regression" are tunable placeholders until calibrated on Optimus eval runs.

| Gate | Baseline | Threshold | Label |
| --- | --- | --- | --- |
| Patch correctness | truncate-at-limit plus current policy | no regression | critical |
| Fully-loaded cost per successful task | current policy | >= 15% lower | critical |
| Stale-context rejection | synthetic stale fixtures | 100% required-code rejection/refresh | critical |
| Context regret | current policy | <= baseline | critical |
| coverage@line-budget | strong-model/retrieval baseline | no material regression | critical |
| Injection safety | poisoned docs/tool output fixtures | 100% pass | critical |

`coverage@line-budget` applies to selection and retrieval mechanisms, not to condensation or last-mile compression.

## Online Guardrails

Online guardrails are per-turn circuit breakers.

| Guardrail | Threshold | Action |
| --- | --- | --- |
| Missing cost attribution | any missing stage | fail closed |
| Budget overshoot | > 0 | degrade optional slot or abort |
| Incomplete dependency closure | required artifact missing | refresh, escalate, or abort |
| Incomplete optional closure | optional artifact missing | drop candidate or degrade slot |
| Low freshness confidence | required evidence uncertain | refresh |
| Evidence dropped then re-requested | repeated in same task | increase failure_recurrence |
| Latency | p95 > baseline + 20% | degrade affected slot |
| Cache hit rate | below expected burst baseline | advisory trace, then reorder stable prefix |

Anti-thrash rule: once a context slot degrades, keep that mode for a minimum cooldown window or until a new task boundary. Every switch records trigger, slot, mechanism, baseline, and resulting prompt block IDs.

## Runtime Safety

Offline gates certify only the tested distribution. Runtime must use fail-closed defaults: no positive health signal for the current context means degrade, refresh, ask, or abort.

Cheap per-turn proxy signals feed provenance traces and `failure_recurrence`:

- dropped evidence later requested
- budget pressure
- closure failure
- low freshness confidence
- stale artifact refresh
- model request for in-scope evidence that was cut

## Context Regret

Context regret is operationally defined as either:

- a chunk was dropped or compacted away, then later re-retrieved and present in the successful context; or
- a failure analysis attributes the failure to missing evidence that the selector previously had available.

Context regret is both an offline metric and an online learning signal for future selection weights.

## Baseline and Ablation Plan

Evaluate null truncate-at-limit first, then each mechanism alone, then combinations:

- repo map
- condensation
- retrieval compression
- last-mile compression
- intelligent selection
- full matrix policy

Promote only combinations that improve fully-loaded cost without reducing task correctness or safety. SWE-ContextBench-style findings that bad selection can actively hurt should be treated as a design constraint, not a footnote.

## Calibration Items

The following values are intentionally not fixed in this document. They require Optimus eval runs:

- fully-loaded cost savings target, currently placeholder >= 15%
- "no material regression" threshold
- latency baseline and p95 allowance
- cache-hit burst baseline
- cooldown window duration
- budget escalation limits
- context-regret acceptable bound

## Reuse and Custom Ownership

Reusable commodity mechanisms should be preferred where mature:

- message trimming
- condensation/summarization
- contextual compression
- long-context reordering
- repo-map symbol ranking
- last-mile prompt compression

Optimus-owned logic remains required for:

- Gateway-based cost attribution
- two-phase trust and freshness gates
- code-span freshness by hash/commit/mtime
- dependency closure and over-budget precedence
- cache-stable prompt packing
- context regret and failure_recurrence telemetry
- runtime fail-closed behavior

## Reference Anchors

- LangChain short-term memory: https://docs.langchain.com/oss/python/langchain/short-term-memory
- LangMem short-term API: https://langchain-ai.github.io/langmem/reference/short_term/
- LangChain contextual compression: https://blog.langchain.com/improving-document-retrieval-with-contextual-compression/
- LlamaIndex node postprocessors: https://developers.llamaindex.ai/python/framework/module_guides/querying/node_postprocessors/node_postprocessors/
- OpenHands Context Condenser: https://docs.openhands.dev/sdk/guides/context-condenser
- Aider repo map: https://aider.chat/docs/repomap.html
- Aider tree-sitter repo map article: https://aider.chat/2023/10/22/repomap.html
- LLMLingua paper: https://arxiv.org/abs/2310.05736
- CodeRAG paper: https://arxiv.org/abs/2504.10046
- SWE-ContextBench paper: https://arxiv.org/abs/2602.08316
- SWE-Explore paper: https://arxiv.org/abs/2606.07297
- When Retrieval Hurts Code Completion paper: https://arxiv.org/abs/2605.14478

## Sign-Off Summary

This standalone evaluation/design doc is approved as the canonical source for context-window optimization until the calibration pass is complete. Fold only the accepted policy into the HLD and LLD after gates, traces, and ablations are defined.
