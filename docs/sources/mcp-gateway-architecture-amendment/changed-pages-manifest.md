# MCP Gateway architecture amendment changed-pages manifest

## Status

Tasks 3 through 6 are signed off. Task 8 rendered the fragments with Pandoc 3.1.3 and WeasyPrint
61.1 under WSL2 Ubuntu-24.04. The verified fragment cardinalities are HLD 8, LLD 22, Guardrails 9,
and Test Strategy 12; their source PDFs have 13, 40, 16, and 14 pages respectively. These mappings
remain pending Task 8 reviewer approval before assembly.

## Rendered fragment mappings

| Document | Rendered fragment | Wording task | Replacement pages |
|---|---|---:|---|
| HLD | `hld-v2.17-changed-pages.md` | Task 3 | `1, 3, 4, 7, 9, 10, 11, 12` |
| LLD | `lld-v2.40-changed-pages.md` | Task 4 | `1, 2, 3, 4, 5, 20, 21, 26-40` |
| Guardrails | `guardrails-v1.2-changed-pages.md` | Task 5 | `1, 4, 6, 8, 10-12, 14, 16` |
| Test Strategy | `test-strategy-v1.6-changed-pages.md` | Task 6 | `1-3, 5-6, 8-14` |

## Exact fragment-to-source-page mappings

| Document | Fragment page -> source page |
|---|---|
| HLD | `1->1, 2->3, 3->4, 4->7, 5->9, 6->10, 7->11, 8->12` |
| LLD | `1->1, 2->2, 3->3, 4->4, 5->5, 6->20, 7->21, 8->26, 9->27, 10->28, 11->29, 12->30, 13->31, 14->32, 15->33, 16->34, 17->35, 18->36, 19->37, 20->38, 21->39, 22->40` |
| Guardrails | `1->1, 2->4, 3->6, 4->8, 5->10, 6->11, 7->12, 8->14, 9->16` |
| Test Strategy | `1->1, 2->2, 3->3, 4->5, 5->6, 6->8, 7->9, 8->10, 9->11, 10->12, 11->13, 12->14` |

## HLD v2.17 redline coverage

| Source page | Redline clusters | Sections |
|---:|---|---|
| 1 | HLD-MCP-4 | Cover/version |
| 3 | HLD-MCP-1 | 5A credentials, MCP accounting, descriptor-context cost, sampling |
| 4 | HLD-MCP-2 | 6 data flow, guarded MCP branch, discovery/pagination, transport axes |
| 7 | HLD-MCP-3 | 10.A system context, Gateway-owned MCP edges, catalog-only reference |
| 9 | HLD-MCP-4 | 10.C release gate, descriptor admission and cost control |
| 10 | HLD-MCP-5 | 11 responsibilities, protocol floor, Context7, two-voice ownership |
| 11 | HLD-MCP-6 | 11.1 guarded sequence and result/accounting release |
| 12 | HLD-MCP-6 | 11A logging distinction and 12 quality/evidence gates |

## LLD v2.40 redline coverage

| Source pages | Redline clusters | Contract surfaces |
|---:|---|---|
| 1-5 | LLD-MCP-1, LLD-MCP-2, LLD-MCP-3 | Component flow, typed routes, registration/refresh, namespaces, profile state, restart activation, transport and Context7 contract |
| 20-21 | LLD-MCP-6 | Existing `RetryPolicy`, typed MCP failures, stateless HTTP, bounded stdio lifecycle |
| 26-30 | LLD-MCP-2, LLD-MCP-3, LLD-MCP-6 | Strict loopback, profile/binding revalidation, stale-marker admission, resource and budget gates |
| 31-35 | LLD-MCP-4 | `MCPUsageRecord`, attribution states, strict-dollar denial, persistence recovery, consumer sweep, logging separation |
| 36-38 | LLD-MCP-4, LLD-MCP-6 | Release checklist, live evidence, transport and credential-isolation gates |
| 39-40 | LLD-MCP-5 | Agent/Gateway trust integration, indeterminate holds, elicitation future-open contract, OWASP voice and normative ownership |

## Guardrails v1.2 redline coverage

| Source pages | Redline clusters | Sections / controls |
|---:|---|---|
| 1 | GR-MCP-4 | Cover and version metadata |
| 4 | GR-MCP-1 | §§2-3 permission order, split authority, direct-bearer residual, Gateway allowlist |
| 6 | GR-MCP-1, GR-MCP-2 | Pre-tool MCP gate, descriptor-context admission, deferred-feature boundaries |
| 8 | GR-MCP-2, GR-MCP-3 | §5/§5.2 supply-chain, discovery/pagination, transport, OAuth, elicitation/sampling, stdio residuals |
| 10-12 | GR-MCP-2, GR-MCP-3 | Bounded holds/retry, capability posture, accounting states, persistence recovery, LLD anchor |
| 14 | GR-MCP-3 | §11 MCP traceability and executable evidence categories |
| 16 | GR-MCP-4 | §13 v1.0/v1.1/v1.2 document-control chain and exclusion provenance |

## Test Strategy v1.6 redline coverage

| Source pages | Redline clusters | Sections / evidence |
|---:|---|---|
| 1-3 | TS-MCP-1 | Cover, scope/non-scope, evidence tiers, real dependencies, Context7 and ACP non-conflation |
| 5-6 | TS-MCP-2 | Registration/restart, direct-route and namespace tests, protocol generation, egress, Docker/WSL2 evidence |
| 8-9 | TS-MCP-3 | §8A MCP accounting consumer sweep, result withholding, bounded retry, indeterminate holds, schema/result denial |
| 10-12 | TS-MCP-4 | Security/trust, catalog and descriptor-context controls, golden tasks, release gates, Context7 live probe |
| 13-14 | TS-MCP-4 | Extended §14.4/§14.5 and complete normative MCP claim-to-evidence matrix |
