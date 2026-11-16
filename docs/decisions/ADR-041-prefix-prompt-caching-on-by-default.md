# ADR-041: Prefix prompt caching is on by default on the shipped Haiku route

**Status:** Accepted, effective on the operator-approved merge of this record. **Decision date:** 2026-11-16.
**Decider:** the operator (verbatim below; Claude's ADR-040 session, no source export filed yet). The change and the
choice of routes are Claude's, reviewed by Codex CLI; each review is posted verbatim on
[#485](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/485). **Publication:** editable in pre-merge
review, frozen byte for byte on first merge to `main`.

**Relationship:**
- **Completes** [ADR-039](ADR-039-provider-cache-breakpoint-after-the-map.md)'s deferred operator decision about
  enabling prefix caching by default on the shipped Haiku route. ADR-039 was accepted by
  [ADR-040](ADR-040-accepts-adr-036-to-039-plan-12-10-memory-m1.md), and said: "The route stays off by default.
  Turning it on for real use follows the paid pair and an operator decision." The paid pair is done, and this is the
  decision. ADR-039's mechanism is unchanged and its bytes stay as merged.
- **Unchanged:** alerts, not limits ([ADR-005](ADR-005-cost-alerts-not-limits.md)); models are configuration
  ([ADR-025](ADR-025-models-are-configuration-per-model-admission.md)), so the default is a route setting in
  `src/optimus_model_policy/defaults.yaml`, not code.

## The operator's decision (2026-11-16, verbatim)

> "It should be turned on by default"

It answered Claude's explanation that ADR-039's `prefix` mode exists, has passed its paid pair and is set on no
shipped route.

## Context

ADR-039 added the `prompt_cache: prefix` route mode. On a `prefix` route, an indexed turn names the end of its stable
start, which runs through the repository map, and the Gateway marks only that part for the provider's cache. The paid
pair ran on 2026-11-05 through the final production path. The cold request wrote 4,876 tokens, and a changed question
read all of them back (`reports/plan12-memory-m1/prompt-cache.json`, `prefix_pair`). It ran with the mode set by an
override file, on registry effective hash `2e9a5181…`.

## Options considered

| | (a) `prefix` on the shipped Haiku 5.5 route | (b) An absent setting means `prefix` everywhere | (c) (a) plus dormant Anthropic routes | (d) Keep it off |
|---|---|---|---|---|
| What changes | One line in `defaults.yaml`; the shipped and test-profile hashes move | Every registry's meaning and identity, including operator overrides | Also Sonnet 5.5, whose reviewer role is dormant and whose route is unverified | Nothing |
| Fit with the evidence | The new shipped hash is `2e9a5181…`, exactly the composition the paid pair ran on | Breaks the rule that a registry saying nothing keeps its approved hash (ADR-039). Untested on routes from other providers | Nothing would run there while the reviewer role is dormant | Contradicts the operator's decision |
| Recommendation | **Claude; chosen** | Not recommended | Not now | Rejected by the operator |

## Decision

- `anthropic/claude-haiku-5.5`'s route in `defaults.yaml` sets `prompt_cache: prefix`. It is the only shipped model
  currently eligible for a role.
- The review pins move with it, because the test profiles compose over the shipped defaults. The test profiles
  deliberately inherit the new default. Explicit `prompt_cache: null` could preserve their earlier hashes, but this
  change keeps them aligned with the shipped route.
  - `SHIPPED_DEFAULTS_HASH` and `HAIKU_ATTACHED_HASH` become `2e9a5181…`, and stay equal;
  - `HAIKU_QUALIFICATION_HASH` becomes `9a9df66a…`;
  - `EVALUATION_HASH` becomes `d5df7f14…`;
  - the Auto composition, which is defaults, then the Auto overlay, then any override, moves from `f11dc3ab…` to
    `7992f727…`.

## Consequences and limits

- **Launch approvals bind the registry hash,** so each launch approved against the old hash, ordinary or Auto, asks for
  approval once more. This is the launch gate's existing rule for any registry change.
- **Upstream payloads.** Indexed Haiku planning and answer requests that name a valid prefix boundary use two text
  blocks, with cache control on the first. Requests without a boundary, including summaries and non-indexed turns,
  retain their upstream payload bytes and payload digest. Registry hashes and Haiku route identities nevertheless
  change.
- **Cost.** Under Stage C, a request that can write the cache reserves its entire estimated input at 1.25 times the
  configured input price; output pricing is unchanged. Haiku's documented five-minute cache-write and cache-read
  multipliers are 1.25 and 0.1. For equal-sized prefixes, caching beats uncached input when reads exceed 21.74% of all
  prefix appearances: `1.25(1−h) + 0.1h < 1`. For varying sizes, this is token-weighted, not the fraction of distinct
  prefixes reused. Production hit rates are unmeasured. Prefixes below the provider's minimum are processed uncached.
- **Reporting.** Durable capture does not capture cache-write token counts; `not_captured` is the qualification
  report's label for that limitation, not a serialized capture field. The savings report omits cache-write charges
  from reference columns. Measured known provider cost includes any premium contained in the provider-reported total,
  but does not itemize it.
- **Earlier approvals** remain evidence for their original hashes and do not authorize the new ones. The launch gate's
  fresh approval covers launch authority for ordinary, Auto and named-profile launches. Any separately bounded paid
  release still needs its own authority, and Stage C's historical envelope pins stay unchanged.
- **Operator overrides compose over the defaults.** An override that sets its own `prompt_cache` on Haiku keeps it. One
  that does not inherits `prefix`, and its effective hash changes too.
- **Evidence stays as recorded.** Earlier reports, approvals, ADR-028 and LLD v2.47 name the old hashes, and they record
  what was true then. A future paid run on a test profile binds that profile's new hash.
- Not claimed: production hit rates or realized savings.
- No paid call is made or authorized by this record.

## Decider and provenance

- **Decision:** the operator, 2026-11-16, in Claude's ADR-040 session. The source export is owed; the record cites the
  words verbatim.
- **This record and the change:** drafted and implemented by Claude; reviewed by Codex CLI on #485.
