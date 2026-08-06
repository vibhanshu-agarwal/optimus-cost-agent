# MCP Gateway architecture amendment publication verification

## Status

Tasks 2-9 are complete and signed off. Task 10's machine validation, completeness/provenance audit,
carried-page preservation, diagram validation, and final render inspection are complete; the four
candidate PDFs remain pending the Task 10 review checkpoint and operator approval. The four pinned
source PDFs remain unchanged.

## Pinned toolchain

- WSL2 Ubuntu-24.04
- Pandoc 3.1.3
- WeasyPrint 61.1
- Poppler 24.02.0

## Task 9 assembly environment exception (operator-authorized)

Changed-page rendering, font copying, and Poppler inspection remain pinned to the WSL2 toolchain
above. Following the `local-gateway-architecture-v3` assembly precedent, the operator authorized
only the page-preserving header-stamping and assembly command to use Windows Python:

```text
C:\\Users\\pc\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe
pypdf 6.10.2
reportlab 5.0.0
```

`reportlab` was installed only into that Windows Python environment to unblock this one-off
publication step. Neither `pypdf` nor `reportlab` is added to `pyproject.toml` or `uv.lock`.

## Task 10 validation environment exception (operator-authorized)

The validator's PDF-parsing dependency is isolated in
`tmp/pdfs/mcp-gateway/.venv` under WSL2 Ubuntu-24.04. The operator authorized `uv` to create that
temporary venv with CPython 3.12.3 and install only `pypdf 6.14.2`; no global WSL environment,
`pyproject.toml`, or `uv.lock` changes. Pandoc, WeasyPrint, Poppler, and font-copying remain on the
pinned WSL2 system toolchain. Pillow 10.2.0 was already available in the WSL system environment for
the validator's SVG text-bound calculation.

The manifest also declares the one carried-page body-version replacement required by the HLD:
page 2's source-preserved `v2.16` stamp at `(437.79316, 673.7097)` is erased and replaced with
`v2.17`. The coordinates and dimensions are carried forward from the exact
`local-gateway-architecture-v3` predecessor manifest; this is a bounded, declared exception, not
an inferred content substitution.

## Task 9 candidate assembly (2026-08-06, superseded intermediate)

The hashes in this historical section describe the first Task 9 assembly. HLD and LLD were
subsequently rebuilt after the authorized diagram corrections; the final hashes are recorded in the
Task 10 section below. Guardrails and Test Strategy retained the values shown here.

### Command

```text
C:\\Users\\pc\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe docs\\sources\\mcp-gateway-architecture-amendment\\tools\\build_publication.py --fragment-dir tmp\\pdfs\\mcp-gateway\\build --font-dir tmp\\pdfs\\mcp-gateway\\fonts
```

### Results

| Candidate PDF | Size (bytes) | Pages | SHA-256 |
|---|---:|---:|---|
| `docs/Optimus-Cost-Agent-Architecture-v2.17.pdf` | 4,975,727 | 13 | `634C681BBBEEB42049AD3567A33DB189965743606423E84EDD876AE2754854A2` |
| `docs/Optimus-Cost-Agent-LLD-v2.40.pdf` | 20,117,009 | 40 | `A265495FA1AC7E80EF4AB5F57B1ABD36B75D250FBFB2FC3865205DEA15311F6F` |
| `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf` | 945,285 | 16 | `461A720FA28576523C87C2F2F89EE1FC52C99971E51ACC22EDC85E8C375A7070` |
| `docs/Optimus-Cost-Agent-Test-Strategy-v1.6.pdf` | 1,801,004 | 14 | `B435E55687116BD7C4D7E78B48E50D8DA9ED0801575B7B5485F262D35C1B31A4` |

The assembler completed successfully: HLD stamped 5 carried pages and removed 6 old header blocks;
LLD stamped 18 and removed 18; Guardrails stamped 7 and removed 7; Test Strategy stamped 2 and
removed 2. WSL2 Poppler confirmed the four candidate titles and page counts. The source hashes
were immediately rechecked and still match the four pinned values in `build-manifest.json`:
`6C2C98FE…5801`, `82513729…85DE`, `27EF0657…1029`, and `F3D744EC…DA8D`.

## LLD cross-reference correction, rerender, and targeted reassembly (2026-08-06, superseded)

The Task 10 current-state sweep found two unlabelled sibling-document references in the LLD:
source page 38 named Test Strategy v1.5 and source page 39 named Guardrails & Workflow Strategy
v1.1. The approved narrow correction changed only those labels to v1.6 and v1.2 respectively.

The LLD fragment was rerendered with the pinned WSL2 Pandoc/WeasyPrint toolchain using the package
directory as both Pandoc CSS source and WeasyPrint base URL. Poppler confirmed 22 Letter-sized
fragment pages. Extracted-text scans found both corrected target labels, all existing MCP anchors,
and no LLD match for `v1.5|v1.1|v2.16|v2.39`. At 150 dpi, physical fragment pages 20 and 21
(source pages 38 and 39) showed the corrected citations, stable table layout, and visible page-39
footer.

Only the existing assembler's LLD document function was invoked. This intermediate candidate was
subsequently superseded by the diagram-aware Task 10 rebuild recorded below. The final LLD hash,
and the final HLD hash after its corresponding diagram-aware rebuild, are recorded in the final
validation section.
The pinned v2.39 source remained unchanged by this correction.

## LLD page-3 containment correction and replacement-page presence sweep (2026-08-06)

Task 10's inventory validation found that page 3's trailing **E. Process-scoped configuration
boundary** and its five-row table were clipped by the fixed-height `.sheet` with hidden overflow.
The source was intact but the candidate omitted the heading and all three
`OPTIMUS_LOCAL_GATEWAY_*` values. The approved correction changed only page 3 from `.compact` to
the existing page-local `.ultra-tight` layout class; no prose, page map, or global CSS changed.

The rerendered LLD fragment remains 22 Letter pages. A disposable containment assertion requires
the page-3 fragment to contain both the E heading and `OPTIMUS_LOCAL_GATEWAY_PROVIDER`; it passes.
At 150 dpi, the assembled candidate page 3 visibly contains the complete E table above its footer.
Targeted LLD-only assembly produced an intermediate candidate; it was superseded by the final
diagram-aware rebuild recorded below.

To guard against the repeated silent-clipping failure mode, the isolated WSL validator environment
ran `tmp/pdfs/mcp-gateway/replacement_page_presence_sweep.py` across every replacement page in all
four candidates. For each manifest-declared replacement page, the sweep requires every source
`##` heading and two deterministic source-derived terms in the corresponding assembled candidate
page text. All 51 replacement pages passed; the page-level evidence is recorded in
`tmp/pdfs/mcp-gateway/replacement-page-presence-sweep.md`.

## Task 10 final validation and diagram-aware rebuild (2026-08-06)

After the authorized diagram corrections, HLD and LLD changed-page fragments were rerendered with
the pinned WSL2 Pandoc/WeasyPrint toolchain and only those two documents were reassembled. Guardrails
and Test Strategy candidates remained byte-identical. The final fragment counts are HLD `8` and LLD
`22`; the assembled document counts remain HLD `13`, LLD `40`, Guardrails `16`, and Test Strategy
`14`.

The final diagram corrections were deliberately bounded: HLD system-context label positioning only;
HLD sequence-note rectangle width only; and LLD reuse of the existing `white-small` class for
`Descriptor-context admission` and `upstream tool + arguments`. No other SVG geometry, connector, or
wording changed. The full validator passed:

```text
PASS hld-gateway-sequence.svg: 23 text bounds and 5 connectors are collision-free
PASS hld-system-context.svg: 28 text bounds and 8 connectors are collision-free
PASS lld-gateway-component-flow.svg: 50 text bounds and 18 connectors are collision-free
```

The isolated WSL2 validator then passed all four candidates: US Letter page size, final metadata,
candidate SHA-256, target-version coverage, superseded-version exclusion, and source/candidate
inventory. The exclusion-reversal scan against freshly extracted candidate text returned zero
matches. The 51-page replacement-page presence sweep also passed: every manifest-declared page
contained all source `##` headings and two deterministic source-derived terms. Its per-page record is
at `tmp/pdfs/mcp-gateway/replacement-page-presence-sweep.md`.

### Final candidate artifacts

| Candidate | Bytes | Pages | SHA-256 |
|---|---:|---:|---|
| `Optimus-Cost-Agent-Architecture-v2.17.pdf` | 4,975,722 | 13 | `a21bdb01bc737fa3d8ebffba8b8b7df96c65101812e17f31c3c7324368d15024` |
| `Optimus-Cost-Agent-LLD-v2.40.pdf` | 20,117,010 | 40 | `0329aef8b5392e05ddbb19ac3f76f3ce7f4fe3c4b728aef6cbfc4de84b324d03` |
| `Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf` | 945,285 | 16 | `461a720fa28576523c87c2f2f89ee1fc52c99971e51acc22edc85e8c375a7070` |
| `Optimus-Cost-Agent-Test-Strategy-v1.6.pdf` | 1,801,004 | 14 | `b435e55687116bd7c4d7e78b48e50d8da9ed0801575b7b5485f262d35c1b31a4` |

Fresh source rechecks still match the pinned Task 1 values: HLD `6c2c98fe2327a6c466cad3eb1800335eb59f0e1f65b2cb8e1e3401d7cfa05801`,
LLD `82513729fd1a6e87fad310dd90a18c996981b68024204e56cca65377495585de`, Guardrails
`27ef0657ccec5568d3e3769c7320223d1bfe3cf6f4702564cbd0a8a391f11029`, and Test Strategy
`f3d744ec175b1e18e8b1e4e271997a0bb12666cc33ca7154a40bf5298588da8d`.

Carried-page preservation passed for all `32/32` carried pages across the four candidates using
Poppler raster comparison below the header band. The only excluded body region was the manifest-
declared HLD page-2 inline version replacement. Final Poppler renders were produced at both 100 dpi
and 150 dpi for all `83` pages; all eight contact sheets and representative dense/diagram pages were
inspected. No clipping, blank-page anomaly, broken page transition, unreadable table/code region,
header/footer defect, or diagram collision was found.

The completeness and provenance audit is recorded in
[`completeness-audit.md`](completeness-audit.md). It maps all 26 design evidence rows, 20 redline
clusters, the security-reference checklist, OWASP voice/ownership, provenance/rulings, custody IDs,
and exclusion/residual obligations. Remaining runtime/live-dependency obligations are explicitly
deferred to their named custody entries rather than treated as publication evidence.

## Task 8 fragment rendering and mapping (2026-08-05)

### Commands

```text
wsl -d Ubuntu-24.04 -- bash -lc "pandoc --version | head -1; weasyprint --version; pdftoppm -v 2>&1 | head -1"
pandoc --standalone --css=print.css --metadata title=<manifest title> <changed-page Markdown> -o tmp/pdfs/mcp-gateway/build/<fragment>.html
weasyprint --base-url <package directory> tmp/pdfs/mcp-gateway/build/<fragment>.html tmp/pdfs/mcp-gateway/build/<fragment>.pdf
pdfinfo tmp/pdfs/mcp-gateway/build/{hld,lld,guard,test}.pdf
pdftoppm -r 150 -png tmp/pdfs/mcp-gateway/build/<fragment>.pdf tmp/pdfs/mcp-gateway/rendered-fragments/<fragment>
pdftotext -layout tmp/pdfs/mcp-gateway/build/<fragment>.pdf tmp/pdfs/mcp-gateway/extracted/fragments/<fragment>.txt
rg -n -i "zero upstream credentials|MCPUsageRecord|server/discover|nextCursor|Context7|input_required|sampling|split authority|P11-FEAT-GATEWAY-MCP|REFERENCE.*Cross-cutting|P11-FU-12|P11-FU-16|complete-only|image/audio|RetryPolicy" tmp/pdfs/mcp-gateway/extracted/fragments
rg -n -i "No MCP endpoint is shown or implied|MCP is explicitly outside this correction|MCP Gateway contract.{0,120}out of scope|P11-FEAT-GATEWAY-MCP remains blocked pending P11-FU-3" tmp/pdfs/mcp-gateway/extracted/fragments
```

### Results

- Toolchain matched the approved versions exactly: Pandoc 3.1.3, WeasyPrint 61.1, and Poppler
  24.02.0 under WSL2 Ubuntu-24.04. WeasyPrint emitted only non-fatal unsupported browser-style CSS
  warnings (`gap`, `overflow-x`, and `user-select`).
- Fragment page counts and source totals were verified with Poppler: HLD `8 -> 13`, LLD `22 -> 40`,
  Guardrails `9 -> 16`, and Test Strategy `12 -> 14`. `build-manifest.json` and
  `changed-pages-manifest.md` contain the exact one-to-one mappings.
- Poppler rendered every fragment page at 150 dpi. Contact-sheet and full-page inspection found
  headings, tables, diagrams, page transitions, and footers clean. The initial LLD render had 23
  pages because source page 39 overflowed after the five-row normative table. A page-specific
  `.ultra-tight` layout class corrected it; the final page-39 table ends above the visible
  `Page 39 of 40` footer, and the rerendered LLD has 22 pages.
- Extracted covers contain target versions 2.17, 2.40, 1.2, and 1.6. The widened MCP-anchor scan
  found the required credential, discovery, pagination, accounting, Context7, deferred-capability,
  result-boundary, retry, and two-voice controls across the fragments.
- The stale exclusion scan returned no matches. The scan ran with PowerShell `rg` because WSL's
  inherited `rg` shim is not executable there; extraction and all byte-producing work remained in
  the approved WSL toolchain.
- `git diff --check` passed after the mapping and layout updates.

## Task 11 documentation freshness and repository gates (2026-08-06)

The repo-wide current-state scan and classifications are recorded in
[`completeness-audit.md`](completeness-audit.md). README, roadmap, backlog, and the authoritative
section map now use the zero-upstream-credential/Gateway-only terminology; the section map records
the Task 10-approved candidate filenames, versions, page counts, output hashes, replacement-page
counts, diagram survey, and MCP ownership overlay. Historical v3/pre-amendment “no endpoint” and
“blocked” statements remain labelled as provenance rather than current conclusions.

Custody consistency passed across the charter, backlog, roadmap, section map, redline, and candidate
text extracts: `P11-FU-12` through `P11-FU-16` retain the exact five names and boundaries, while
`P11-FU-9`, `P11-FEAT-ZED-RESUME`, and `P11-FEAT-REGISTRY` remain distinct.

### Repository gate results

- `python -m pytest tests/unit/docs -v` could not launch through the Windows Python manager
  (`WinError 5`, access denied). The same command through the existing project venv passed all
  `5/5` documentation tests.
- `python -m ruff check .` initially found ten import-order findings in disposable `tmp/` evidence
  helpers. Ruff’s mechanical fix was applied only under `tmp/pdfs/mcp-gateway/`; the full command
  then passed with `All checks passed!`.
- Windows full suite through the project venv: `2576 passed, 26 skipped, 68 deselected, 1 warning`
  in `79.77s`.
- The exact WSL2 `uv sync --frozen --extra dev && uv run pytest -q` run completed dependency sync
  but exposed the linked-worktree `.git` path as `/mnt/.../D:/...`. A clean native-WSL rerun using
  `/mnt/.../.venv/bin/python -m pytest -q` reproduced the same deterministic result:
  `2590 passed, 1 failed, 11 skipped, 68 deselected, 1 warning` in `68.89s`. The sole failure is
  `test_product_checkpoint_log_location_remains_gitignored`; Ubuntu `/usr/bin/git` cannot parse
  this worktree's Windows-style `.git` pointer. A narrow disposable Git wrapper was tested as a
  diagnostic and made the suite pass, but it is not counted as clean POSIX evidence. The directory
  metadata test reported elsewhere passed in isolation and is not reproducibly failing here.
- `git diff --check` passed after the freshness edits; no `src/` or `tests/` path changed.

The Task 10-approved candidate PDFs were not edited by the freshness changes. The final publication
validator was rerun afterward with the recorded split runtime: the isolated WSL2 venv for PDF
parsing and the system WSL2 Pillow environment for SVG geometry.

## Task 12 final review gate

Task 11's documentation-freshness audit and repository gates are complete, with the native WSL2
linked-worktree Git-path mismatch recorded above as a known environment limitation rather than a
clean POSIX pass. Task 12 Step 4 remains operator-only: the four candidate PDFs and documentation
changeset require explicit final approval before any staging or commit. No candidate PDF is treated
as published solely by this verification record.
