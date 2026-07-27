# Local Gateway Architecture v3 PDF verification

Verification date: 2026-07-27

## Build environment

- WSL2 distribution: Ubuntu-24.04
- Pandoc: 3.1.3
- WeasyPrint: 61.1
- Poppler: 24.02.0
- Fonts: DejaVu Sans, DejaVu Sans Mono, Lato, and Liberation Sans fallback
- Page geometry: US Letter, 612 × 792 points
- OCR, Mermaid CLI, Node, Chromium, and MSYS2: not used

The pinned HLD, LLD, and Test Strategy use DejaVu Sans and DejaVu Sans Mono. The pinned
Guardrails document uses Lato and DejaVu Sans Mono. The changed-page sources retain those font
families.

## Assembly and preservation

The repository has no complete editable source for the pinned PDFs. Changed pages were rendered
from the Markdown, CSS, and SVG files in this directory. Unchanged pages were copied from the
pinned PDFs.

| Document | Final pages | Changed pages | Carried pages | Carried content-stream identity |
|---|---:|---:|---:|---:|
| HLD v2.16 | 13 | 8 | 5 | 5/5 |
| LLD v2.39 | 40 | 22 | 18 | 18/18 |
| Test Strategy v1.5 | 14 | 10 | 4 | 4/4 |
| Guardrails v1.1 | 16 | 4 | 12 | 12/12 |

All 39 carried pages have SHA-256-identical decoded page-content streams to the corresponding
pinned-source pages. The LLD's unchanged image-backed code pages were therefore preserved without
OCR, retyping, or substitution from current implementation code.

## Machine checks

For each final PDF:

- every page is exactly 612 × 792 points;
- actual page count equals the manifest's expected page count;
- embedded title metadata agrees with the output document and version;
- critical architecture text extracts from the changed pages;
- the cover reports the same version as the filename and metadata title.

Critical extraction anchors included OpenRouter as default aggregator, deterministic separate
search, `UrllibOpenAICompatibleClient`, Tavily retirement custody, protocol-visible USD rename
custody, Phoenix/OTLP evidence, independent package and OSV routes, completion-evaluation cost
control, and the blocked `P11-FEAT-GATEWAY-MCP` disposition.

The consolidated redline contains 33 entries: 8 HLD, 14 LLD, 8 Test Strategy, and 3 Guardrails.

## Visual inspection

All 83 final pages were rendered with Poppler at 100 dpi and inspected in full-document contact
sheets. Covers, headers, footers, diagrams, tables, code blocks, and transitions between changed
and carried pages were legible and unclipped. The three SVG diagrams were also inspected in their
final PDF context. The LLD component diagram exposes trace ingress but no MCP endpoint.

## Output digests

| Output | SHA-256 |
|---|---|
| `Optimus-Cost-Agent-Architecture-v2.16.pdf` | `BA18B539F99C1FDE06F85C9D601942E489D95268BB883811CC2BC47161CF85E4` |
| `Optimus-Cost-Agent-LLD-v2.39.pdf` | `73D8CE4CB119BF32D8191CE30F848E2193C212D7CD81DE674307DBC7574C99ED` |
| `Optimus-Cost-Agent-Test-Strategy-v1.5.pdf` | `64D90CEEA4CDAC3739F1D896D18227575CEC9348202BA3492A7E07C1715DCA2A` |
| `Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf` | `93523880576834F970E6401618E18280D45DFBF964CDBB11332D8412B167BF2D` |
