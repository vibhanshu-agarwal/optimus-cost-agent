# Plan 11.13 authoritative-document reversal evidence

## Publication result

Plan 11.13 publishes the authoritative removal of the retired Gateway-brokered MCP contract.
It creates four successor PDFs and the self-contained sibling source package
`docs/sources/gateway-mcp-authoritative-document-reversal/`. The historical amendment source
package remains immutable.

| Current authoritative PDF | Prior immutable input | Pages | Replacement pages | SHA-256 |
|---|---|---:|---:|---|
| Architecture v2.18 | v2.17 | 13 | 8 | `0F8725765FECC9A93045FD26630457DFE7112508DF164A3EC5BCC55DBC976807` |
| LLD v2.41 | v2.40 | 40 | 22 | `69400FD474EB30711FCC9A061243D6A4D2E35D39D7794D4AA69F5FF51B98109B` |
| Guardrails v1.3 | v1.2 | 16 | 9 | `94F8F829D60FB9945237227B16E82CB523659E4D67C8488909035FE9BDB27957` |
| Test Strategy v1.7 | v1.6 | 14 | 12 | `31A60C6A198C60CC1203FF5C4A8E6E0300A820EC18CC702E25F246EDC51DC0B0` |

The PDF metadata title, producer (`Pandoc 3.1.3 + WeasyPrint 61.1 + ReportLab header stamp + pypdf
reversion assembly`), US-Letter geometry, page count, target version on every page, predecessor
body preservation, and recorded output hash pass the publication validator.

## Immutable predecessor proof

The validator and committed-blob verification agree on the unchanged inputs:

| Input | SHA-256 |
|---|---|
| Architecture v2.17 | `A21BDB01BC737FA3D8EBFFBA8B8B7DF96C65101812E17F31C3C7324368D15024` |
| LLD v2.40 | `0329AEF8B5392E05DDBB19AC3F76F3CE7F4FE3C4B728AEF6CBFC4DE84B324D03` |
| Guardrails v1.2 | `461A720FA28576523C87C2F2F89EE1FC52C99971E51ACC22EDC85E8C375A7070` |
| Test Strategy v1.6 | `B435E55687116BD7C4D7E78B48E50D8DA9ED0801575B7B5485F262D35C1B31A4` |

## Bidirectional reversal audit

The final-PDF audit rejects the retired Gateway markers
`P11-FEAT-GATEWAY-MCP`, `MCPProfileRegistry`, `MCPDiscoveryBroker`,
`MCPInvocationBroker`, `MCPConnectionManager`, retired typed routes, `MCPUsageRecord`,
and Gateway-originated Context7. It also requires the surviving client-owned anchors:
`P11-FU-9`, ACP `mcpServers`, `MCPTrustRegistry`, `validate_tool_call`,
`PreToolGuard.check`, untrusted tool output, both MCP test markers, and independently authored
client-MCP servers.

The clean invocation passed. Scratch-only proof hooks independently failed when
`MCPProfileRegistry` was injected and when `mcpServers` was removed.

## Rendered-page inspection

Pandoc 3.1.3 and WeasyPrint 61.1 rendered 51 exact-count control fragments. Poppler 24.02.0
rendered all fragments and every final changed page plus adjacent carried page at 150 dpi.
The first final inspection caught a header-whiteout collision; the repaired final rerender passed
with no clipped headings, overflow, blank pages, diagram faults, table faults, or header/footer
collisions. The page-level ledger is in the sibling package
`verification.md`.

## Plan 11.15 identity audit

The all-four-base-document typed result is **NOT_REPRESENTED**. HLD v2.16, LLD v2.39,
Guardrails v1.1, and Test Strategy v1.5 contain generic approval, descriptor/manifest identity,
or test-mode language only—not Plan 11.15 durable workspace identity/approval mechanics.
The strict identity term set had zero hits in all eight base/current PDFs. Therefore no
`P11-FU-30` custody entry is created and this publication makes no identity-mechanics change.

## Current boundary

Gateway-brokered MCP is retired. ACP `mcpServers` remains client supplied and local validation,
pre-tool guarding, and untrusted-output handling remain client/agent-owned. The revised Test
Strategy states that `requires_mcp_http` and `requires_mcp_stdio` require independently
authored client-MCP servers, never a Gateway.

## Documentation freshness audit

The final search covered `README.md`, the authoritative section map, pool, charter, roadmap,
`docs/runbooks/`, reports, and both source roots. The README and four living pointers were
updated where they made current-state claims. The remaining matches were classified as follows:

| Match class | Treatment | Evidence |
|---|---|---|
| Live pointer | Updated | Section map, pool, charter, and roadmap name the four successor PDFs and this evidence; the README retains the client-owned boundary. |
| Frozen/historical provenance | Retained | The original amendment source root, its assets, dated redline drafts, and read-only historic reports remain unchanged and explicitly retain their dated/pinned status. |
| Procedural publication evidence | Retained | The new sibling reversal package contains the permitted audit vocabulary solely to prove absence/presence and to build the successor PDFs. |

No `docs/runbooks/` current-state claim required a change. The audit separately confirmed that
`P11-FU-9`, ACP `mcpServers`, `requires_mcp_http`, `requires_mcp_stdio`, and registry/publication
identity remain distinct from the retired Gateway broker.
