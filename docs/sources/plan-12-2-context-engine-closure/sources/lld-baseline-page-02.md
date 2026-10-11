# 0. Optimus AI Gateway architecture
The Gateway is a deterministic strict-loopback process. Agent-facing configuration remains only OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY. The Gateway holds the approved developer aggregator credential in its own local environment or OS credential storage. No hosted Optimus service, OAuth/device flow, tenant wallet, Vault or public origin is introduced.
OpenRouter remains the default aggregator. Vercel is an optional second OpenAI-compatible endpoint only where its existing modest integration is retained; direct provider adapters remain removed.
:::flow
Local Optimus agent - URL/shared secret only
Authenticated loopback Gateway at 127.0.0.1:8765
Trusted policy + domains + finite calls + complete request capacity
Independent adapters -> approved upstream / public tools / OTLP
Provider-reported usage -> normalized existing ledger
:::end
| Ingress / adapter | Downstream responsibility |
|---|---|
| /v1/responses; /v1/chat/completions | One approved OpenAI-compatible model transport; preserve distinct input/messages shapes |
| /v1/tools/web/search | Separate authorized search request; actual usage and compatibility gate |
| /v1/tools/web/extract | Bounded HTTPS extract with provenance and revalidation |
| /v1/tools/package/lookup | Public PyPI/npm/Maven clients, independent of search |
| /v1/tools/security/advisory | Public OSV client, independent of search |
| /v1/observability/traces | Structured trace validation/redaction -> OTel/OTLP -> Phoenix by default |
All seven routes authenticate locally. No MCP endpoint is added. Product dollar stops retire only under the accepted migration; independent evaluation ceilings remain.

| External component | Preserved edge |
|---|---|
| OpenRouter | Approved default model transport and separately authorized search |
| Vercel | Optional retained OpenAI-compatible transport; never an automatic substitute |
| PyPI / npm / Maven | Independent package APIs |
| OSV | Independent advisory API |
| Phoenix / OTLP collector | Sanitized configured trace export |
| RedisTimeSeries | Existing usage/state attribution |
The host owns Agent planning count/time/failure bounds; the Gateway owns enabled trusted request policy and capacity.
