# 11. Optimus Gateway - Phase 1 Local Process Boundary

The Optimus Gateway is a deterministic loopback process run by the developer alongside the local
agent. It is not a hosted Optimus service, tenant control plane, subscription product, or central
wallet.

## Gateway responsibilities

- Bind to strict loopback and authenticate the agent with a local shared secret.
- Isolate the developer's aggregator credential in Gateway-owned local configuration or OS
  credential storage.
- Route explicitly eligible model IDs through the surviving OpenAI-compatible transport after trusted policy composition.
- Enforce trusted model/tool policy, domain rules, request call caps, provenance and complete request capacity when enabled. Host count/time/failure limits remain separate; product dollars are accounting/alerts after the released migration.
- Return provider-reported usage and cost in a validated GatewayUsage envelope.
- Broker deterministic search, bounded extract, package lookup, and OSV advisory independently.
- Accept structured trace ingress, map it to OpenTelemetry, and export OTLP.
- Persist usage attribution across run, session, request, Gateway request, and provider request IDs.

## Process-scoped configuration

| Agent process environment | Gateway process local configuration |
|---|---|
| `OPTIMUS_GATEWAY_URL=http://127.0.0.1:8765` | `OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter` |
| `OPTIMUS_API_KEY=` | `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=` |
| No provider, search, or OTel credentials | `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=` |
| Loopback URL only | allowed domains, Redis URL, optional OTLP endpoint |
| No hosted-origin override | no tenant profile, Vault, or non-loopback mode |

Run the agent and Gateway in the same network namespace. A Windows-host Gateway is not loopback
from an agent running inside WSL2.