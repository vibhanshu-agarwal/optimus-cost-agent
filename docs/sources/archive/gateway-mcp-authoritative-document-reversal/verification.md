# Plan 11.13 verification evidence

## Task 0 baseline

Base commit 5875d46f5de62aa87ced474488346fc441385655. Input SHA-256 values match the approved HLD A21BDB01BC737FA3D8EBFFBA8B8B7DF96C65101812E17F31C3C7324368D15024; LLD 0329AEF8B5392E05DDBB19AC3F76F3CE7F4FE3C4B728AEF6CBFC4DE84B324D03; Guardrails 461A720FA28576523C87C2F2F89EE1FC52C99971E51ACC22EDC85E8C375A7070; Test Strategy B435E55687116BD7C4D7E78B48E50D8DA9ED0801575B7B5485F262D35C1B31A4.

## Task 1 all-four-base-document identity audit

| Base document | Result | Page evidence | Classification |
|---|---|---|---|
| HLD v2.16 | NOT_REPRESENTED | p.13 human-approval path | generic permission control |
| LLD v2.39 | NOT_REPRESENTED | p.39 requires_human_approval; pp.21/32-33 identifiers | pre-tool/telemetry, not durable workspace binding |
| Guardrails v1.1 | NOT_REPRESENTED | p.5 human approval; p.8 MCPTrustRegistry manifest identity; p.15 manifest reapproval | MCP descriptor trust, not durable workspace identity |
| Test Strategy v1.5 | NOT_REPRESENTED | p.4 AwaitingApproval; p.13 manifest reapproval | mode/state and test evidence, not durable workspace identity |

Summary NOT_REPRESENTED: strict workspace identity terms had zero hits in all eight base/current PDFs. No P11-FU-30 is created and no identity mechanics are added to these PDFs.

## Task 2 immutable-input and source-boundary gate

The copied validator rechecked every immutable input against the approved SHA-256 baseline before
each final validation run. The historical amendment source tree has no diff; this sibling package
is the only new publication source root.

## Task 3 executable bidirectional proof

| Invocation | Expected result | Observed result |
|---|---|---|
| Clean validator | PASS | PASS: all ten Gateway phrases absent; all nine client anchors present |
| Scratch --inject-forbidden MCPProfileRegistry | FAIL | FAIL: forbidden phrase survives |
| Scratch --drop-required mcpServers | FAIL | FAIL: client anchor missing |

The two scratch hooks change extracted candidate text in memory only; no PDF or source file is
modified. Anchor matching is tolerant only of extractor whitespace/hyphen splits; the ACP
mcpServers field remains an exact field-name match so generic MCP-server prose cannot satisfy it.

## Task 5 fragment render ledger

Inspector: Codex. Toolchain: WSL2 Ubuntu-24.04, Pandoc 3.1.3, WeasyPrint 61.1, Poppler 24.02.0.
All fragment pages were rendered at 150 dpi and visually inspected for fenced-div rendering,
overflow/clipping, wrapping, header/footer collisions, blank pages, and transitions.

| Fragment PDF | Pages inspected | Verdict | Repair |
|---|---:|---|---|
| hld.pdf | 1-8 | PASS | none |
| lld.pdf | 1-22 | PASS | none |
| guard.pdf | 1-9 | PASS | Guardrails cover title compacted before final pass |
| test.pdf | 1-12 | PASS | none |

## Task 5 final rendered-page ledger

Inspector: Codex, 2026-08-15T05:05Z. Each changed page and its adjacent carried page was rendered
at 150 dpi and visually inspected. All listed pages PASS.

| Final PDF | Changed pages | Adjacent carried pages | Verdict |
|---|---|---|---|
| HLD v2.18 | 1, 3, 4, 7, 9, 10, 11, 12 | 2, 5, 6, 8, 13 | PASS |
| LLD v2.41 | 1-5, 20-21, 26-40 | 6, 19, 22, 25 | PASS |
| Guardrails v1.3 | 1, 4, 6, 8, 10-12, 14, 16 | 2-3, 5, 7, 9, 13, 15 | PASS |
| Test Strategy v1.7 | 1-3, 5-6, 8-14 | 4, 7 | PASS |

The first final inspection found that a 54-point header whiteout obscured restored HLD p.10,
LLD p.39, and Test Strategy p.13 headings. The repair narrowed the whiteout to the running-header
band and moved the client-boundary anchors to dedicated rendered cover callouts. A fresh complete
final inspection passed. A transient HLD p.2 v2.17 footer leak was replaced with v2.18 before the
same final pass.

## Task 6 documentation freshness audit

The final search covered `README.md`, section map, pool, charter, roadmap, `docs/runbooks/`,
reports, and both source roots. README and living pointers are current. Remaining matches are
classified as frozen/historical provenance (the original amendment source, dated drafts, and
read-only reports) or procedural evidence (this sibling package). No runbook change was required.
The audit separately confirmed that `P11-FU-9`, client-supplied ACP `mcpServers`, both MCP
markers, and registry/publication identity remain distinct from retired Gateway brokering.

## Final PDF identities

| PDF | Pages | Embedded title | SHA-256 |
|---|---:|---|---|
| Architecture v2.18 | 13 | Optimus-Cost-Agent - Architecture v2.18 | 0F8725765FECC9A93045FD26630457DFE7112508DF164A3EC5BCC55DBC976807 |
| LLD v2.41 | 40 | Optimus-Cost-Agent - LLD v2.41 | 69400FD474EB30711FCC9A061243D6A4D2E35D39D7794D4AA69F5FF51B98109B |
| Guardrails v1.3 | 16 | Optimus-Cost-Agent - Agent Execution Guardrails and Workflow Strategy v1.3 | 94F8F829D60FB9945237227B16E82CB523659E4D67C8488909035FE9BDB27957 |
| Test Strategy v1.7 | 14 | Optimus-Cost-Agent - Test Strategy v1.7 | 31A60C6A198C60CC1203FF5C4A8E6E0300A820EC18CC702E25F246EDC51DC0B0 |

All four PDFs report producer `Pandoc 3.1.3 + WeasyPrint 61.1 + ReportLab header stamp + pypdf
reversion assembly`; all four have US-Letter geometry.
