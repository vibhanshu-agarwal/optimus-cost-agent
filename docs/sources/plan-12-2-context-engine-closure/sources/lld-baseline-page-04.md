# 0A. Local vs. Gateway Configuration and Provider-Cost Mapping

## Phase 1 runtime rule

The agent runtime allows only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`. The Gateway owns the
developer's approved aggregator credential. Local agent-side Tavily, OpenAI, OpenRouter, GLM,
LangSmith, or other provider keys are rejected.

## Provider-cost mapping

`OPTIMUS_API_KEY` is a local shared secret, not a wallet key. The developer funds the aggregator
account directly. The Gateway records the aggregator response into one local ledger.

| Call class | Required accounting |
|---|---|
| Model completion | aggregator, actual provider/model when returned, tokens/cache, billing units, provider-reported `cost_usd`, request IDs |
| Deterministic search | separate minimal model call, structured citations, search-use accounting, provider-reported `cost_usd` |
| Package/advisory | operational request evidence; no fabricated provider cost |
| Trace export | delivery state and trace IDs; no allocated/amortized request charge |

```text
Agent shared secret
  -> loopback Gateway trust, capacity and accounting
  -> developer aggregator account
  -> provider-reported usage and USD cost
  -> GatewayUsage + normalized local ledger
```

The separate USD rename removes `optimus_credits_debited` and other legacy credit-named fields
without changing their existing USD semantics or introducing cross-run policy.