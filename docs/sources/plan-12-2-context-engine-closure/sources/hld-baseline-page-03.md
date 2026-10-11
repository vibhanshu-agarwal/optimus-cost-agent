Target contract after the named trusted-policy / Task 11 / coverage migration as applicable; the dated inactive production baseline is stated on the cover.

# 5A. Upstream Aggregator Cost Normalization and Single-Key Model

`OPTIMUS_API_KEY` is the only agent-facing credential. It is a local shared secret used to
authenticate the agent process to the loopback Optimus Gateway; it is not an upstream vendor key
or an Optimus tenant wallet. The Gateway process holds one developer-owned aggregator credential
in its own local configuration or OS credential storage. OpenRouter is the default aggregator.
Vercel AI Gateway is an allowed second OpenAI-compatible endpoint when its Python integration is
modest.

The developer funds the aggregator account directly. The aggregator supplies access to many
models, routes across upstream providers, reports normalized usage and USD cost, and debits one
developer-owned balance. The local Gateway preserves the one-key, one-account, one-ledger model by
isolating that credential from the LLM-driven agent, enforcing trusted policy and capacity controls; host finite-work bounds remain separate, and
recording provider-reported usage.

There is no Optimus-hosted account, prepaid balance, subscription, tenant, org, project wallet,
OAuth/device flow, or public Optimus Gateway.

## Normalized cost path

| Stage | Credential and responsibility |
|---|---|
| Local agent | `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` only |
| Loopback Gateway | Shared-secret auth, policy, capacity, attribution, aggregator credential isolation |
| Aggregator | Models, routing, provider-reported billing units and `cost_usd` |
| Local ledger | Run/session/request/Gateway/provider request attribution |

Web search currently shares the OpenRouter credential and balance through a dedicated,
deterministic plugin request. Package registry and OSV calls are free public APIs and are not
funding paths. OpenTelemetry trace export has no invented per-request charge.

The one-key property for search is explicitly conditional: OpenRouter has deprecated its
deterministic plugin, and no deterministic aggregator successor is presently documented. Plugin
withdrawal may require a verified-or-fail server-tool design or a standalone search provider with
a second key and balance.