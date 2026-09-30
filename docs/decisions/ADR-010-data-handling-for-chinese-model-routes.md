# ADR-010: Data handling on Chinese-model routes: no restriction now

**Status:** Deferred. **Date:** 2026-09-30. **Decider:** the operator.

## Context

Claude asked the operator: "For Chinese-model routes, should we only use providers that don't collect or
keep your data? OpenRouter has settings for both."

**Operator, verbatim (2026-09-30):**

> "5. As of now no, but we can consider such a feature in the future."

**Facts.** OpenRouter provider routing supports all of the following as documented fields (checked
2026-09-30):

- `data_collection: "allow" | "deny"`;
- `zdr` (zero-data-retention endpoints only);
- `order`, `only` and `ignore` (provider lists).

Several providers serve the Chinese models.

## Options considered

| | A: no restriction (chosen for now) | B: `data_collection: "deny"` | C: zero-data-retention endpoints only |
|---|---|---|---|
| Provider pool, price, availability | Widest, cheapest | Narrower | Narrowest |
| Protection of user code and prompts | Provider-dependent | Better | Best |
| Complexity | None | A registry field | A registry field |

## Decision

No restriction now. The registry (ADR-004) reserves per-model provider-constraint fields, so the feature
can be switched on later without redesign.

## Consequences

- **Revisit** when Optimus serves users whose policies forbid data retention, or when the operator
  requests it.
- **Related case, not limited to Chinese routes.** ADR-004 makes `meta/muse-spark-1.3-contributor` the
  cheap-tier default, on the operator's judgment, with a warning before every request. Meta may use that
  tier's prompts and completions for training.
  - The registry records this per model as `data_use`.
  - The same future switch that ADR-010 reserves should be able to exclude such models.
