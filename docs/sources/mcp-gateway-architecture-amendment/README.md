# MCP Gateway architecture amendment publication sources

This package is the page-preserving publication source for the approved MCP Gateway architecture
amendment. It targets these new authoritative documents:

- `Optimus-Cost-Agent-Architecture-v2.17.pdf`
- `Optimus-Cost-Agent-LLD-v2.40.pdf`
- `Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf`
- `Optimus-Cost-Agent-Test-Strategy-v1.6.pdf`

The normative wording contract is the approved design and consolidated redline in
`docs/superpowers/specs/` and `docs/superpowers/reports/`. The security reference is supporting,
non-normative input. The changed-page Markdown files are skeletons until their corresponding
publication task is reviewed.

## Pinned sources and splice policy

The source PDFs are preserved byte-for-byte and are never overwritten or deleted:

| Document | Pinned source | SHA-256 |
|---|---|---|
| HLD | `docs/Optimus-Cost-Agent-Architecture-v2.16.pdf` | `6C2C98FE2327A6C466CAD3EB1800335EB59F0E1F65B2CB8E1E3401D7CFA05801` |
| LLD | `docs/Optimus-Cost-Agent-LLD-v2.39.pdf` | `82513729FD1A6E87FAD310DD90A18C996981B68024204E56CCA65377495585DE` |
| Guardrails | `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf` | `27EF0657CCEC5568D3E3769C7320223D1BFE3CF6F4702564CBD0A8A391F11029` |
| Test Strategy | `docs/Optimus-Cost-Agent-Test-Strategy-v1.5.pdf` | `F3D744EC175B1E18E8B1E4E271997A0BB12666CC33CA7154A40BF5298588DA8D` |

Only reviewed changed pages and diagrams are authored here. Unchanged pages are copied from the
pinned PDFs without OCR, retyping, or substitution from implementation code. Image-backed LLD
code pages remain source-preserved. Target filenames, cover versions, metadata, and running headers
must agree. Any inline body replacement outside a changed page must be explicitly declared in
`build-manifest.json` and bounded by the preservation check.

## Approved toolchain

Changed-page rendering, font copying, and Poppler inspection run in Ubuntu-24.04 under WSL2 with
the pinned toolchain:

- Pandoc 3.1.3
- WeasyPrint 61.1
- Poppler 24.02.0
- DejaVu Sans and DejaVu Sans Mono
- Lato

The page-preserving header-stamping and assembly command is the one narrow exception: the
operator authorized `tools/build_publication.py` to run with Windows Python at
`C:\\Users\\pc\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe`, using `pypdf 6.10.2` and
`reportlab 5.0.0`. This follows the `local-gateway-architecture-v3` publication precedent. It does
not broaden the project dependency surface: neither package is added to `pyproject.toml` or
`uv.lock`, and all other rendering, font-copying, and Poppler work remains in WSL2.

No OCR, Mermaid CLI, Node, Chromium, or MSYS2 is part of this package.

## Build and verification contract

Render each reviewed changed-page Markdown file with Pandoc `--standalone` and `print.css`, then
render the HTML with WeasyPrint using this package directory as the base URL. Place fragments,
fonts, rendered pages, and extracted evidence only under `tmp/pdfs/mcp-gateway/`.

The assembler copies untouched pages from the pinned sources and replaces only the manifest-listed
pages. The publication validator must prove page counts, geometry, metadata, versions, source
preservation, SVG bounds/connectors, critical wording, and exclusion-reversal completeness. Record
commands, visual inspection, hashes, and residuals in `verification.md`.
