# Local Gateway Architecture v3 document sources

These sources produce the changed pages for:

- `Optimus-Cost-Agent-Architecture-v2.16.pdf`
- `Optimus-Cost-Agent-LLD-v2.39.pdf`
- `Optimus-Cost-Agent-Test-Strategy-v1.5.pdf`
- `Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf`

The authoritative wording comes from
`docs/superpowers/reports/2026-07-27-local-gateway-architecture-document-redline-v3.md`.

## Source and splice policy

The original repository contains PDFs but no complete Markdown, HTML, TeX, or Word authoring
sources. Most source PDF text is extractable, but the LLD's illustrative code pages are
image-backed. This correction therefore uses a page-preserving splice:

1. Changed pages are authored here as editable Markdown, CSS, and SVG.
2. Untouched source pages are copied from the pinned prior-version PDFs without OCR, retyping, or
   substitution from current implementation code.
3. LLD pages 6-13, 15-19, and 22-25 remain source-preserved. Editable recovery of those pages is a
   separate follow-up.
4. LLD section 6 on pages 20-21 is rewritten because its Vault language is architecturally stale.
5. Final PDF metadata, cover version, and filename use the new version.

This avoids publishing OCR-corrupted Python while preserving unchanged illustrative specification
content.

## Toolchain

The approved build environment is Ubuntu-24.04 under WSL2:

- Pandoc 3.1.3
- WeasyPrint 61.1
- Poppler 24.02.0
- DejaVu Sans and DejaVu Sans Mono
- Lato
- Liberation Sans as a fallback only

No Mermaid CLI, Node, Chromium, MSYS2, or OCR tool is used.

## Changed-page rendering

From this directory:

```bash
pandoc hld-v2.16-changed-pages.md --standalone --css print.css \
  --metadata title="Optimus-Cost-Agent - Architecture v2.16" \
  --output ../../../tmp/pdfs/build/hld-v2.16.html
weasyprint --base-url "$PWD" \
  ../../../tmp/pdfs/build/hld-v2.16.html \
  ../../../tmp/pdfs/build/hld-v2.16-changed-pages.pdf
```

Repeat for the LLD, Test Strategy, and Guardrails Markdown files. The Markdown uses fixed US Letter
`.sheet` divisions, so each generated page maps to one `replacement_pages` entry in
`build-manifest.json`.

Final assembly copies untouched pages from the pinned source PDFs and replaces only the listed
pages. The assembly is deliberately a one-time pypdf operation, not a committed bespoke PDF
generator.

## Verification

For every final PDF:

- render every page with Poppler and inspect diagrams, tables, code, headers, and transitions;
- confirm page count and page size;
- confirm filename, cover version, and embedded metadata title agree;
- confirm critical replacement text extracts successfully;
- confirm every carried page has the same content-stream digest as its pinned source page;
- record SHA-256 in `build-manifest.json`.

The completed verification record is in `verification.md`.
