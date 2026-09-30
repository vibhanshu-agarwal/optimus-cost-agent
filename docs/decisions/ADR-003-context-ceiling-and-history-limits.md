# ADR-003: Context ceiling of about 256K for all models; history may exceed 512 KiB while the engine is attached; Haiku removed

**Status:** Accepted-with-open-items. **Date:** 2026-09-30. **Decider:** the operator.

## Context

**Operator, verbatim (2026-09-30):**

> "1. Yes. I was looking forward to your and Codex's inputs on this. The 128 K ceiling was decided taking
> the lowest bar of the models. If the allowed models lowest bar is 256 K we can go to 256 K also."

> "1. Claude Haiku is out - it is too old now - can we have ~256K window Option A"

> "4. This was decided by agents, not me." (about the "100K usable inside 128K" figure)

**Where the old numbers came from:**

- **128K.** The operator's Plan 11.25 ruling, 2026-08-20. It shipped as `CONVERSATION_MAX_BYTES =
  524_288` bytes of rendered history (`acp/conversation.py:20`), about 131K tokens at the rough bytes/4
  rate.
- **"100K usable inside 128K".** Claude's proposal on 2026-08-20 (A1). Claude withdrew it when Codex
  noted Haiku 4.5 has a 200K window, and it never shipped. **An agent decided it, not the operator.**
- **What shipped has no headroom.** History alone may use the whole 512 KiB. It works only because Haiku
  4.5 has a 200K window.

**Facts on 2026-09-30.** OpenRouter's catalog shows every model on the operator's tier list (ADR-004) with
a window of at least 1,000,000 tokens. There is no allowed-model list in the code yet (ADR-004).

**Industry practice** (research sweep, 2026-09-30; sources in the
[evidence file](2026-09-30-industry-context-cost-and-model-evidence.md)):

- Agents compact at a **percentage of each model's own window**: 80–90% in Codex CLI, Copilot, Cline,
  Goose and opencode.
- An explicit reserve for output and overhead is common: 5–30%.
- Anthropic's docs warn that accuracy and recall degrade as the token count grows ("context rot").

## Options considered: the ceiling

| | A: one global ceiling for all models (chosen) | B: each model's own window |
|---|---|---|
| Simplicity and predictability | High | Medium: needs per-model limits everywhere |
| Use of large windows | Capped at about 256K | Up to about 1M |
| Cost per call at the limit | Bounded; illustrative input-only cost of 256K input tokens at list price, excluding output, cache and other billable classes: about $0.03 on Luna and $0.51 on Sonnet 5.5 | Up to 4× higher |
| Quality (context rot) | Better: less dilution | Worse near 1M |
| Safety across models | Safe while every eligible route's verified window is at least the ceiling; enforced by a registry test | Safe by construction |

**Reasoning.** With every listed model at about 1M, Option A gives up little capacity. It bounds the
size, and so the cost, of each call and the quality loss, and it is simple to reason about. The ceiling is
not a price guarantee. The operator's "lowest bar" rule still holds, through the capacity formula below
and the registry validator (ADR-004).

## Decision

1. **Engine attached:** history may exceed 512 KiB.
   - It is bounded by a stated `SOURCE_MAX_BYTES`, sized from memory measurements.
   - The 80% warning then refers to that storage limit.
   - A temporary engine failure never closes the thread (the non-latching fallback agreed by Claude and
     Codex).
2. **One global context ceiling of about 256K tokens** (262,144) for the whole request, meaning the
   complete packed input **plus** the output reserve (Option A).
   - The output reserve is counted exactly once. This was corrected after Codex's review on 2026-09-30:
     an earlier draft of ADR-004 added the reserve a second time.

   ```text
   effective_total = min(262144, verified_route_window)
   usable_input    = effective_total - output_reserve
   complete_input_estimate <= usable_input
   output_reserve  <= verified_route_max_output
   ```

   - If policy requires every eligible route to support the full ceiling, the registry requires
     `verified_route_window >= 262144`. It does not require the ceiling plus the reserve.
   - A capacity table alone does not guarantee capacity for an alias or provider that can change. Either
     restrict the route (ADR-004 provider pinning) or use the smallest verified capacity among the routes
     that are allowed.
   - The input estimate covers all request framing and material, using a stated conservative method.
3. **Claude Haiku 4.5 is removed** from the default and from any list.
4. **Engine absent:** the floor is unchanged (512 KiB, 80% warning, refusal), per ADR-001.
   - **Removing Haiku is an explicit exception.** It changes the shared default model, so it is an
     exception to the earlier "unchanged baseline" for engine-absent sessions.
   - Storage, admission and task assembly for engine-absent sessions stay unchanged, apart from the
     separately approved floor port and the history-ordering fix.
   - No claim is made that the whole product stays byte-identical once the default model changes.

**Authority boundary.**

- **Accepted by the operator:** the policy above (items 1–4).
- **Proposed:** the formula's parameters and the open items below.
- **Not commissioned:** implementation.

## Open items

- **When compaction triggers: proposed, awaiting the operator.** Trigger at the smaller of:
  - about 80% of usable input under the ceiling;
  - a **per-tier history target** set in the registry: generous for cheap tiers, tighter for the review
    tier, where 100K tokens of history costs about $0.20–$0.30 of input per call at list price
    (illustrative only).

  The numbers come from measurement. This keeps "100K" only as a possible cost target, not as a safety
  limit.
- **The `SOURCE_MAX_BYTES` value** is to be measured.

## Consequences

- **Removing Haiku is a code change:**
  - the default model in `agent/defaults.py:5` and `acp/local_infra.py:58`;
  - the Gateway's only alias in `optimus_gateway/model_mapping.py:5`;
  - tests and evidence that pin `claude-haiku`.
- **The meter shows the complete estimated request** against the usable input under the ceiling. It is
  an estimate, not a tokenizer count.
- **Revisit** if a listed model with a window under about 300K is ever admitted.
