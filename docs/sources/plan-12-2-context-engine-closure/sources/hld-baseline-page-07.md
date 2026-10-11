# 10.A System context diagram
The IDE, local agent, loopback Gateway, Redis, repository and optional Phoenix collector belong to one developer environment. Agent and Gateway are separate processes; the agent receives only Gateway URL/shared secret and cannot read the Gateway aggregator credential.
:::flow
IDE / independent ACP client - user request and exact approval
Optimus local agent - host state, assembly and tool controls
Loopback Gateway - trust, capacity and actual usage
Approved aggregator - exact eligible model/provider endpoint
:::end
| Side edge | Boundary |
|---|---|
| Agent -> repository | Current eligible workspace evidence and controlled approved edits |
| Agent / Gateway -> Redis | Existing state and usage ledger; no new context-engine store |
| Gateway -> Phoenix | Configured OTLP export; no invented billable charge |
| Gateway -> PyPI/npm/Maven | Independent public package APIs |
| Gateway -> OSV | Independent advisory service |
| Gateway -> OpenRouter | Default approved aggregator/model and separately authorized search path |
| Gateway -> Vercel | Optional retained model endpoint; not an automatic route substitute |
No MCP endpoint is shown or implied. Client-supplied MCP trust/execution remains local. WSL2 agent and Windows-host Gateway do not share loopback; Phase 1 requires the same network namespace. Figure 10.A preserves that boundary and retires the product-budget label.
