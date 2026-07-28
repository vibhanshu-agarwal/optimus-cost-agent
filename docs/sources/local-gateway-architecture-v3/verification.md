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

| Document | Final pages | Changed pages | Carried pages | Body preservation below header |
|---|---:|---:|---:|---:|
| HLD v2.16 | 13 | 8 | 5 | 4 identical; 1 declared inline version correction |
| LLD v2.39 | 40 | 22 | 18 | 18/18 pixel-identical |
| Test Strategy v1.5 | 14 | 10 | 4 | 4/4 pixel-identical |
| Guardrails v1.1 | 16 | 4 | 12 | 12/12 pixel-identical |

All 39 carried pages received corrected running headers. At 100 dpi, 38 pages are pixel-identical
to their pinned sources below the header band. HLD page 2 differs only within the measured
8 × 11-pixel bounding box for the manifest-declared `v2.15` to `v2.16` body self-reference.
There were no unexpected below-header differences. The LLD's unchanged image-backed code pages
were preserved without OCR, retyping, or substitution from current implementation code.

## Machine checks

For each final PDF:

- every page is exactly 612 × 792 points;
- actual page count equals the manifest's expected page count;
- embedded title metadata agrees with the output document and version;
- critical architecture text extracts from the changed pages;
- the cover reports the same version as the filename and metadata title.
- the target version appears on every page;
- the superseded version is absent outside the explicit Guardrails page-16 historical change-log
  exception.

Critical extraction anchors included OpenRouter as default aggregator, deterministic separate
search, `UrllibOpenAICompatibleClient`, Tavily retirement custody, protocol-visible USD rename
custody, Phoenix/OTLP evidence, independent package and OSV routes, completion-evaluation cost
control, and the blocked `P11-FEAT-GATEWAY-MCP` disposition.

The consolidated redline contains 33 entries: 8 HLD, 14 LLD, 8 Test Strategy, and 3 Guardrails.

The SVG validator measured 13 text bounds and 6 connectors in the HLD sequence, 25 text bounds and
9 connectors in the HLD system context, and 39 text bounds and 16 connectors in the LLD component
flow. Every text bound remained inside its canvas and containing box; no connector intersected a
text bound.

## Visual inspection

All 83 final pages were rendered with Poppler at 100 dpi and inspected in full-document contact
sheets. Covers, headers, footers, diagrams, tables, code blocks, and transitions between changed
and carried pages were legible and unclipped. The three SVG diagrams were also inspected in their
final PDF context. The LLD component diagram exposes trace ingress but no MCP endpoint.

The environment was synchronized from the locked project definition, installing the previously
missing declared dependency `defusedxml==0.7.1`. Ruff passed. The full test suite passed with
1,783 passed, 20 skipped, 54 deselected, and one pre-existing runtime warning.

## Output digests

| Output | SHA-256 |
|---|---|
| `Optimus-Cost-Agent-Architecture-v2.16.pdf` | `B00F92DF7E50E4C642A5FEC3D2C3B5893BC05991E2BACA900FB9AAFD8F7CF564` |
| `Optimus-Cost-Agent-LLD-v2.39.pdf` | `2F86FFD62EB153CCE0CFDDC98631F046202BC0E9CBB17FC5F35268E78627CAA8` |
| `Optimus-Cost-Agent-Test-Strategy-v1.5.pdf` | `A5629907AC477880E86D7AA217FF01FCE92825E057F876AA5CCFBF6476018EBA` |
| `Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf` | `DE8987CF44897C47563FC48E2E43832180F117A0BBCBE45E4B6E26C68059035A` |
