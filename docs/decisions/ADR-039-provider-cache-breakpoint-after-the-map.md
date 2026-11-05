# ADR-039: Provider caching marks only the stable start of a request

**Status:** Proposed. The operator chose this mechanism on 2026-11-05 and approved the Plan 12.10 v2 hash the same day (both verbatim below). Still owed: the operator's acceptance of this record. The released paid pair ran on 2026-11-05 and showed a changed question reusing the prefix on the qualified route ([`prompt-cache.json`](../../reports/plan12-memory-m1/prompt-cache.json)); that establishes neither production hit rates nor savings. Delivered under Plan 12.10 ([#469](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/469)). Drafted by Claude; Codex reviewed the code and the plan text in CLI review 17 on #469.

**Relationship:** changes how [ADR-038](ADR-038-context-index-retrieval-tools-and-caching.md)'s opt-in provider caching is delivered for M1, and leaves ADR-038's bytes and its other decisions alone. Plan 12.10 v1, SHA-256 `f136397fe605d51bd6dfee1ab4ed8705e7c3a45d05eb52b6c5cf569a7d02adb1`, specified root `cache_control`, so this needed its `_v2` successor (AGENTS.md), approved at SHA-256 `73e4df57f1613d0c428a70b3834d056c145be340e232ea40ae6508162940cdb4`. Unchanged: alerts, not limits ([ADR-005](ADR-005-cost-alerts-not-limits.md)); models are configuration ([ADR-025](ADR-025-models-are-configuration-per-model-admission.md)), so the measured route is named only in the evidence.

## Context

Plan 12.10 put the question last so a follow-up would share a prefix, and sent the whole prompt as one text block with root `cache_control`. Provider documentation says writes happen only at a breakpoint, and that lookback finds earlier writes, not an uncached stable start. The operator released a diagnostic to measure it: three requests through the real Gateway at `6e5478a`, on the cheapest qualified route, pinned, in `top_level` mode set by an override file. Three physical attempts, no recovery, USD 0.00068458 reported.

| Request | Prompt tokens | Read | Written | Reported USD | Seconds |
|---|---:|---:|---:|---:|---:|
| Cold | 2,592 | 0 | 2,588 | 0.0003274 | 1.94 |
| Byte-identical repeat | 2,592 | 2,588 | 0 | 0.00002978 | 1.52 |
| Same prefix, changed question | 2,592 | 0 | 2,588 | 0.0003274 | 1.17 |

Calculated, not measured: the same request uncached would cost USD 0.0002627, so a changed question costs 24.63% more than no cache, and the repeat costs 90.90% less than cold. One changed-question sample, with the repeat as its control and the documented behaviour, is enough to choose a mechanism. It says nothing about production hit rates. Sanitized figures, the raw record's digest and the script's digest are in [`prompt-cache.json`](../../reports/plan12-memory-m1/prompt-cache.json); the raw record stays in the local handoff kit as provenance.

**Severity:** medium. No shipped route turns it on, so nobody pays this today, but explicitly enabling it can increase charges: M1's caching as built adds about 25% to a real next turn and saves only on an exact repeat. An earlier assessment given to the operator said it "can't overspend or harm"; that was too strong, and this sentence corrects it.

## The operator's decision (2026-11-05, verbatim, Claude's Plan 12.10 chat)

Asked "Do you want the prefix-breakpoint fix or repeat-only caching?", the operator answered: "Build the prefix fix".

This authorized implementation only. Later the same day: "I will be going on vacation tomorrow morning, so just get it to a stable checkpoint today, so that when I pick this up later we are not in an inconsistent state".

Then, given three numbered requests (approve the v2 hash `73e4df57f1613d0c428a70b3834d056c145be340e232ea40ae6508162940cdb4`; confirm Releases A and B still stand; release the cache pair at 2 requests and USD 0.25, and the Zed pair), the operator answered: "Approved. Go ahead. #1 - #3". This approves the hash and those releases. It does not approve publication, merge or this record.

## Options considered

The option text is as it was put to the operator, with the review's facts added.

| Option | Outcome | For | Against |
|---|---|---|---|
| One breakpoint after the repository map, in a new opt-in mode | **Chosen by the operator; recommended by Claude and Codex** | Delivers the caching M1 set out to deliver; a new question reuses the start of the request; the saving grows on pricier routes. | About 2–3 days, a plan successor and this record, and one more paid pair. The saving is small on this route: for an illustrative 4,400-token prefix at the diagnostic's prices, a hit saves USD 0.000396 against uncached input and a write adds USD 0.00011; production prefix sizes and hit rates remain unmeasured. |
| Repeat-only: keep the code, leave the mode off, record that M1 only caches exact repeats | Not chosen | No code, no further paid run, keeps the schedule. | Narrows required M1 work and leaves real turns uncached; needs the operator's recorded disposition. |
| Rely on a route that caches implicitly | Not recommended | No wire change. | Plan v1 says implicit alone is insufficient for the cheapest qualified route; no such route is verified in the shipped registry, so it adds qualification without solving the requirement. |
| Redefine `top_level` to mean the new behaviour | Rejected (Codex) | No fourth mode. | Silently changes what an existing approved identity means. |
| A second breakpoint after the pack | Not taken (Codex) | Could capture Chat's repeated pack. | Agent sends the pack only on its first planning call, and a second point cannot rescue a prefix whose earlier text changed. Unneeded for a first useful version. |
| Mark the boundary with a marker in the text and parse it | Rejected (Codex) | No binding change. | Prompt content could choose its own boundary. |

## The decision

- **Mode.** Route setting `prompt_cache: prefix`. A registry that says nothing keeps every approved hash and wire byte; opting in enters the identities. `top_level` stays for compatibility and is not selected for M1.
- **Where.** One breakpoint immediately after the repository map, before history, pack, results and the question, in both indexed builders. Indexed prompt bytes do not change.
- **How it travels.** The host names an optional `route_binding.cache_prefix_chars` only when the final input begins with the string the builder supplied, and only on a `prefix` route. It counts Unicode code points of the final flattened input. It enters the payload digest and the Contributor disclosure, verified by both host and Gateway, so moving or removing it after issue is refused.
- **The Gateway.** It validates a positive boundary, an approved route and two non-blank parts, or refuses with `CACHE_PREFIX_INVALID` before any provider call. It sends one user message with two text blocks, `cache_control` on the first only, and no root control. Decision requests refuse a boundary. A prefix route with no boundary, such as a turn without an index, sends today's wire and digest.
- **Stage C.** A request that can write the cache reserves its whole input at 1.25 times the input price, the qualified provider's documented five-minute write premium. This fixes write-price under-reservation under the configured input estimate and prices; it does not remove empirical estimation error or price drift. It repairs a test guard and adds no product cost stop.

## Consequences and limits

- A changed map or tool grammar changes the prefix, and that request may miss and require a fresh write. Withdrawing tools removes grammar before the map; this is rare, since tools close only after the fourth round or a reply of only repeats, and rearranging the prompt was not worth changing its bytes.
- An empty map still names a boundary after the fixed text. A prefix below the route's minimum is processed uncached and a long enough one may cache; the actual size is unmeasured and no outcome is assumed.
- Two text blocks add no text, and the qualified estimator has a large margin (1 token per byte against about 0.34 measured). No padding was added. The paid pair must still check reported prompt tokens against the admitted estimate.
- M1's capture schema is unchanged: durable capture records cache writes as `not_captured`. The diagnostic's write counts come from the provider's reply and are attributed to it alone.
- The route stays off by default. Turning it on for real use follows the paid pair and an operator decision.

## Release and approval boundaries

- The diagnostic ran under the operator's Release D: 3 requests, at most 6 physical attempts, USD 0.25. Disclosed: it read the stored provider key through the product's resolver, which the release table did not list. The key was never printed or recorded. Its unused allowance releases nothing further.
- Releases A and B (index runs, no provider calls), Release C (the paid Zed pair) and CACHE-PREFIX-PAIR-1 are released; their use is recorded in the plan's reports.

## Outstanding

Operator acceptance of this record; M1's remaining Task 5 work and CP4. The cold and changed-question pair through the final production path is done: the cold request wrote 4,876 tokens, the changed question read all of them, 2 physical attempts, USD 0.00296866 reported. One pair proves reuse is possible, and says nothing about production hit rates or savings. Revert checks of the guards are in the handoff kit (`revert-check-prefix.json`).
