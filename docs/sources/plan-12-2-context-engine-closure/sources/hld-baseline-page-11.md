Target contract after the named trusted-policy / Task 11 / coverage migration as applicable; the dated inactive production baseline is stated on the cover.

# 11.1 Gateway request / response sequence

The actual request path retains the four actors: local agent, loopback Gateway, approved aggregator and Redis/Phoenix. The accepted product migration replaces the old monetary budget precheck with trust, complete capacity and finite work controls.

:::flow
Local agent -> loopback Gateway: bearer shared secret + request
Gateway: authenticate + trusted policy + complete input/output capacity
Gateway -> approved aggregator: Gateway-owned credential + request
Aggregator -> Gateway: output + actual reported usage/cost
Gateway -> Redis: normalized ledger record (exactly once)
Gateway -> Phoenix: OTel span export via OTLP (no invented model cost)
Gateway -> local agent: normalized GatewayUsage + response
:::end

| Sequence boundary | Preserved behavior |
|---|---|
| Agent to Gateway | One authenticated request over the strict loopback boundary. The aggregator credential never enters the agent process or response. |
| Gateway to aggregator | Only the configured approved aggregator with Gateway-owned credential. Final complete-request and output enforcement applies to every actual attempt. |
| Aggregator result | Parse output/true finish status and actual reported usage/cost. Unknown cost is explicit, never manufactured as zero. |
| Ledger and trace | Persist normalized receipt exactly once and export sanitized OTel spans independently; trace export is not a billed inference request. |
| Search | A separate authorized request and annotation path. Package and OSV routes do not depend on search availability. |

Independent evaluation dollar caps remain scoped to their authorized evaluations. Product dollar stops are removed on the reviewed cf9bb9d branch; production context enforcement remains inactive. Evaluation ceilings remain scoped to independently authorized evaluations.
