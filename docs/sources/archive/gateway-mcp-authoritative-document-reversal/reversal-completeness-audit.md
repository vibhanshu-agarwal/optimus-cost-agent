# Plan 11.13 reversal-completeness audit

## Gate and method

This is the inverse of the v2.17/v2.40/v1.2/v1.6 amendment completeness audit. It is a hard, bidirectional gate over text extracted from the four final PDFs. Every historical Gateway-brokering claim must be absent, while the client-supplied ACP MCP seam must remain present with client-owned wording. The validator reads the inventories in build-manifest.json and fails either direction.

## Design §12 required-evidence inverse census

| # | Original amendment claim | Historical source page | Former owner | Disposition | Candidate page | Final extracted-PDF proof |
|---:|---|---|---|---|---|---|
| 1 | Agent holds no upstream MCP credential | HLD v2.17 p.3; p.9 | Gateway credential custody | RESTORE_PRE_AMENDMENT | HLD v2.18 pp.3,9 | no Gateway MCP credential phrase |
| 2 | Direct bearer caller cannot widen tools | HLD v2.17 p.10; Guardrails v1.2 p.4 | Gateway allowlist | RESTORE_PRE_AMENDMENT | HLD p.10; Guardrails p.4 | no Gateway allowlist residual |
| 3 | Profile changes force reapproval | LLD v2.40 p.39; Test Strategy v1.6 p.6 | Gateway profile lifecycle | RESTORE_PRE_AMENDMENT | LLD p.39; Test Strategy p.6 | no profile lifecycle claim |
| 4 | Rotation property survives migration | Test Strategy v1.6 pp.5-6; LLD p.40 | Gateway rotation/reapproval | RESTORE_PRE_AMENDMENT | Test Strategy pp.5-6; LLD p.40 | no Gateway rotation claim |
| 5 | Bootstrap is satisfiable | LLD v2.40 pp.2-3; Test Strategy p.5 | Gateway registration | RESTORE_PRE_AMENDMENT | LLD pp.2-3; Test Strategy p.5 | no registration/broker claim |
| 6 | Descriptor drift is bounded | LLD v2.40 p.2; Guardrails p.8 | Gateway freshness | RESTORE_PRE_AMENDMENT | LLD p.2; Guardrails p.8 | no Gateway profile freshness |
| 7 | Tool namespace is collision-safe | LLD v2.40 p.2; Test Strategy p.5 | Gateway profile namespace | RESTORE_PRE_AMENDMENT | LLD p.2; Test Strategy p.5 | no profile namespace claim |
| 8 | Deferred protocol features fail closed | Guardrails v1.2 p.6; Test Strategy pp.10-14 | Gateway MCP feature scope | RESTORE_PRE_AMENDMENT | Guardrails p.6; Test Strategy pp.10-14 | client-side fail-closed wording remains |
| 9 | HTTP header mirroring is absent | LLD v2.40 p.2; Guardrails p.8 | Gateway HTTP adapter | RESTORE_PRE_AMENDMENT | LLD p.2; Guardrails p.8 | no Gateway HTTP adapter claim |
| 10 | Stdio credential isolation is real | Guardrails v1.2 p.8; Test Strategy p.5 | Gateway stdio custody | RESTORE_PRE_AMENDMENT | Guardrails p.8; Test Strategy p.5 | no Gateway stdio custody |
| 11 | Resource controls are symmetric | HLD v2.17 p.11; Guardrails p.8 | Gateway resource admission | RESTORE_PRE_AMENDMENT | HLD p.11; Guardrails p.8 | no MCP admission contract |
| 12 | Unknown spend is never zero | LLD v2.40 p.31; Test Strategy p.8 | MCP usage accounting | RESTORE_PRE_AMENDMENT | LLD p.31; Test Strategy p.8 | MCPUsageRecord absent |
| 13 | Indeterminate mutation is not silently repeated | LLD v2.40 p.40; Guardrails p.10 | Gateway call lifecycle | RESTORE_PRE_AMENDMENT | LLD p.40; Guardrails p.10 | no Gateway call lifecycle |
| 14 | Accounting failure cannot escape budget control | LLD v2.40 p.31; Test Strategy pp.8-9 | MCP result release/accounting | RESTORE_PRE_AMENDMENT | LLD p.31; Test Strategy pp.8-9 | MCPUsageRecord absent |
| 15 | Protocol interoperability is real | Test Strategy v1.6 pp.1-3 | Gateway live tier | REWRITE_CLIENT_CURRENT_STATE | Test Strategy v1.7 p.13 | independently authored client-MCP servers |
| 16 | Protocol generation is correct | LLD v2.40 p.2; Test Strategy p.6 | Gateway typed routes | RESTORE_PRE_AMENDMENT | LLD p.2; Test Strategy p.6 | server/discover and routes absent |
| 17 | Context7 compatibility dependency is honest | HLD v2.17 p.10; Test Strategy pp.10-14 | Gateway Context7 probe | RESTORE_PRE_AMENDMENT | HLD p.10; Test Strategy pp.10-14 | Gateway-originated Context7 absent |
| 18 | Pagination is complete or absent | HLD v2.17 p.4; LLD p.2; Test Strategy p.6 | Gateway discovery broker | RESTORE_PRE_AMENDMENT | HLD p.4; LLD p.2; Test Strategy p.6 | MCPDiscoveryBroker absent |
| 19 | Registry cannot become autoload | HLD v2.17 p.7; Guardrails p.10 | Gateway catalog/provisioning | RESTORE_PRE_AMENDMENT | HLD p.7; Guardrails p.10 | no Gateway catalog authority |
| 20 | Provisioning and connections stay separate | LLD v2.40 pp.20-21; Guardrails p.10; Test Strategy p.9 | Gateway profile/connection state | RESTORE_PRE_AMENDMENT | LLD pp.20-21; Guardrails p.10 | MCPConnectionManager absent |
| 21 | Elicitation remains triply closed | LLD v2.40 p.40; Test Strategy pp.10-14 | Gateway MCP contract | RESTORE_PRE_AMENDMENT | LLD p.40; Test Strategy pp.10-14 | no retired protocol contract |
| 22 | Sampling cannot spend or inject | HLD v2.17 p.3; LLD p.31; Test Strategy p.9 | Gateway MCP accounting | RESTORE_PRE_AMENDMENT | HLD p.3; LLD p.31; Test Strategy p.9 | MCPUsageRecord absent |
| 23 | Descriptor context is cost-bounded | HLD v2.17 p.3; Guardrails p.8; Test Strategy p.10 | Gateway descriptor admission | RESTORE_PRE_AMENDMENT | HLD p.3; Guardrails p.8 | no Gateway admission claim |
| 24 | MCP errors extend existing retry | LLD v2.40 pp.20-21; Test Strategy pp.8-9 | Gateway retry/capacity | RESTORE_PRE_AMENDMENT | LLD pp.20-21; Test Strategy pp.8-9 | no MCP broker retry claim |
| 25 | OWASP voice and ownership are non-ambiguous | HLD v2.17 p.10; LLD p.40; Test Strategy p.14 | Gateway MCP normative owner | RESTORE_PRE_AMENDMENT | HLD p.10; LLD p.40; Test Strategy p.14 | P11-FEAT-GATEWAY-MCP absent |
| 26 | Exclusion provenance is honest | Guardrails v1.2 p.16; HLD p.10 | Gateway amendment provenance | RESTORE_PRE_AMENDMENT | Guardrails p.16; HLD p.10 | retired amendment claims absent |

## Redline-cluster inverse coverage

| Cluster | Historical source | Gateway claim cluster | Disposition | Candidate page(s) |
|---|---|---|---|---|
| HLD-MCP-1 | HLD v2.17 p.3 | credential, descriptor cost, MCP usage | RESTORE_PRE_AMENDMENT | HLD v2.18 p.3 |
| HLD-MCP-2 | HLD v2.17 p.4 | guarded Gateway branch and discovery | RESTORE_PRE_AMENDMENT | HLD v2.18 p.4 |
| HLD-MCP-3 | HLD v2.17 p.7 | Gateway-to-MCP topology | RESTORE_PRE_AMENDMENT | HLD v2.18 p.7 |
| HLD-MCP-4 | HLD v2.17 p.9 | Gateway profile-secret phase gate | RESTORE_PRE_AMENDMENT | HLD v2.18 p.9 |
| HLD-MCP-5 | HLD v2.17 p.10 | Gateway MCP component/Context7/normative owner | RESTORE_PRE_AMENDMENT | HLD v2.18 p.10 |
| HLD-MCP-6 | HLD v2.17 pp.11-12 | Gateway sequence/accounting/evidence | RESTORE_PRE_AMENDMENT | HLD v2.18 pp.11-12 |
| LLD-MCP-1 | LLD v2.40 pp.1-2 | broker components and dual registries | RESTORE_PRE_AMENDMENT | LLD v2.41 pp.1-2 |
| LLD-MCP-2 | LLD v2.40 pp.2-3 | typed discovery/call routes and transport | RESTORE_PRE_AMENDMENT | LLD v2.41 pp.2-3 |
| LLD-MCP-3 | LLD v2.40 pp.3-5 | profile union/revision/configuration | RESTORE_PRE_AMENDMENT | LLD v2.41 pp.3-5 |
| LLD-MCP-4 | LLD v2.40 pp.31-35 | MCP attribution and persistence | RESTORE_PRE_AMENDMENT | LLD v2.41 pp.31-35 |
| LLD-MCP-5 | LLD v2.40 pp.39-40 | trust integration and normative rows | REWRITE_CLIENT_CURRENT_STATE | LLD v2.41 p.39 |
| LLD-MCP-6 | LLD v2.40 pp.20-21,26-30 | retry and connection lifecycle | RESTORE_PRE_AMENDMENT | LLD v2.41 pp.20-21,26-30 |
| GR-MCP-1 | Guardrails v1.2 pp.4,6 | split agency/direct bearer | RESTORE_PRE_AMENDMENT | Guardrails v1.3 pp.4,6 |
| GR-MCP-2 | Guardrails v1.2 p.8 | pins, discovery, result/resource | REWRITE_CLIENT_CURRENT_STATE | Guardrails v1.3 p.8 |
| GR-MCP-3 | Guardrails v1.2 pp.8,10-14 | stdio, accounting, sandbox residual | RESTORE_PRE_AMENDMENT | Guardrails v1.3 pp.8,10-14 |
| GR-MCP-4 | Guardrails v1.2 p.16 | amendment document-control chain | RESTORE_PRE_AMENDMENT | Guardrails v1.3 p.16 |
| TS-MCP-1 | Test Strategy v1.6 pp.1-3 | Gateway tiers and ACP custody | REWRITE_CLIENT_CURRENT_STATE | Test Strategy v1.7 pp.1-3,13 |
| TS-MCP-2 | Test Strategy v1.6 pp.5-6 | profile/bootstrap/transport evidence | REWRITE_CLIENT_CURRENT_STATE | Test Strategy v1.7 pp.5-6,13 |
| TS-MCP-3 | Test Strategy v1.6 pp.8-9 | MCP accounting/retry/schema | RESTORE_PRE_AMENDMENT | Test Strategy v1.7 pp.8-9 |
| TS-MCP-4 | Test Strategy v1.6 pp.10-14 | Context7/normative traceability | REWRITE_CLIENT_CURRENT_STATE | Test Strategy v1.7 pp.10-14,13 |

## Forbidden Gateway inventory

The validator rejects the following surviving final-PDF phrases: P11-FEAT-GATEWAY-MCP, MCPProfileRegistry, MCPDiscoveryBroker, MCPInvocationBroker, MCPConnectionManager, /v1/tools/mcp/discover, /v1/tools/mcp/call, server/discover, MCPUsageRecord, and Gateway-originated Context7. The contextual boundary is deliberate: ordinary Gateway model/usage claims and non-Gateway MCP descriptor language are not prohibited.

## Required client-owned inventory

| Required anchor | Client-owned final evidence |
|---|---|
| P11-FU-9 and mcpServers | HLD v2.18 p.1 cover callout: ACP mcpServers are client supplied. |
| MCPTrustRegistry | HLD v2.18 p.1 cover callout: local descriptor validation. |
| validate_tool_call and PreToolGuard.check | LLD v2.41 p.1 cover callout: both run before client execution. |
| untrusted tool output | Guardrails v1.3 p.1 cover callout: remains a local agent control. |
| requires_mcp_http and requires_mcp_stdio | Test Strategy v1.7 p.1 cover callout. |
| independently authored client-MCP servers | Test Strategy v1.7 p.1 cover callout; never a Gateway. |

## Approved non-candidate occurrences

| Location | Reason retained |
|---|---|
| docs/sources/mcp-gateway-architecture-amendment/ | Immutable historical amendment evidence; never a final-PDF input. |
| Plan 11.13 v1 and v2 | Frozen/execution provenance describing the retired contract and its reversal. |
| Historical reports, reviews, and prior PDFs | Evidence of earlier authority only; section map identifies the new current PDFs. |

## Deliberate validator proof cases

Before the final pass, the validator receives a scratch injected MCPProfileRegistry marker and separately a scratch deletion of mcpServers. Each invocation must fail. Neither proof case changes an output PDF. The clean invocation must then pass.
