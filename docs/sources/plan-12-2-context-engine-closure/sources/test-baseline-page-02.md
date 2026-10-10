# 1. Test objectives

The strategy proves that a developer can complete full Plan and Agent runs with only
`OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` in the agent process. No upstream credential is
resolvable by the agent. Separately, the loopback Gateway receives exactly its approved aggregator
credential and never exposes it.

# 2. Scope and non-scope

In scope:

- strict loopback URL and bind enforcement, including WSL2 same-network-namespace topology;
- OpenRouter default and bounded Vercel option through the OpenAI-compatible transport;
- deterministic search live compatibility and plugin deprecation gate;
- include/exclude domain enforcement and returned-URL revalidation;
- independent package/OSV routes without search configuration;
- bounded extract provenance, redirect, SSRF, media, size, and time controls;
- provider-reported usage/cost authority and full request attribution;
- OTel/OTLP export to a real Phoenix tier;
- separate agent and Gateway credential/egress scans.

Out of scope:

- hosted staging Gateway, OAuth/device flow, tenants, org/project wallets, Vault;
- direct provider adapters;
- cross-run spend policy (`P9.85-FU-3`);
- MCP Gateway endpoint or contract;
- engine/model comparison matrices.