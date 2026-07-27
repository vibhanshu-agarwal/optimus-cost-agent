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
pages. Carried pages receive an opaque header band, a corrected hyphen-style running header, and
the original horizontal rule. The old header text objects are removed before the new header is
merged so obsolete versions do not remain in text extraction.

Copy the exact fonts used by the assembly step to a temporary build directory:

```powershell
New-Item -ItemType Directory -Force ../../../tmp/pdfs/fonts
Copy-Item \\wsl.localhost\Ubuntu-24.04\usr\share\fonts\truetype\dejavu\DejaVuSans.ttf `
  ../../../tmp/pdfs/fonts/
Copy-Item \\wsl.localhost\Ubuntu-24.04\usr\share\fonts\truetype\dejavu\DejaVuSans-Bold.ttf `
  ../../../tmp/pdfs/fonts/
Copy-Item \\wsl.localhost\Ubuntu-24.04\usr\share\fonts\truetype\dejavu\DejaVuSans-Oblique.ttf `
  ../../../tmp/pdfs/fonts/
Copy-Item \\wsl.localhost\Ubuntu-24.04\usr\share\fonts\truetype\lato\Lato-Italic.ttf `
  ../../../tmp/pdfs/fonts/
```

Render the four changed-page fragments as `hld.pdf`, `lld.pdf`, `test.pdf`, and `guard.pdf` in
`tmp/pdfs/build`, then run the committed assembler from the repository root:

```powershell
python docs/sources/local-gateway-architecture-v3/tools/build_publication.py `
  --fragment-dir tmp/pdfs/build `
  --font-dir tmp/pdfs/fonts
```

The assembler validates replacement-page cardinality, requires an old header block on every
carried page, applies the HLD page-2 self-reference correction declared in the manifest, writes
metadata, and updates output SHA-256 values in `build-manifest.json`.

## Verification

For every final PDF:

- render every page with Poppler and inspect diagrams, tables, code, headers, and transitions;
- confirm page count and page size;
- confirm filename, cover version, and embedded metadata title agree;
- confirm critical replacement text extracts successfully;
- confirm the target version appears on every page and the superseded version is absent outside
  explicitly allowlisted historical change-log pages;
- confirm every carried page is pixel-identical to its pinned source below the header except for
  manifest-declared inline replacements;
- confirm SVG text stays inside its canvas and boxes and connectors do not cross labels;
- record SHA-256 in `build-manifest.json`.

Run the committed publication validator from the repository root:

```powershell
python docs/sources/local-gateway-architecture-v3/tools/validate_publication.py `
  --font-dir tmp/pdfs/fonts
```

Guardrails page 16 is the only historical-version exception: its change log legitimately records
v1.0. The exception is explicit in `build-manifest.json`; it does not permit a stale running
header.

The completed verification record is in `verification.md`.
