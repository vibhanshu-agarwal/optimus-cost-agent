# Validation record: HLD v2.22 and LLD v2.45 (local filing, 2026-10-27)

Scope: the assembly, carried native text, predecessor page coverage, label and footer presence, escape-artifact scan, rebuild determinism, the rendered-text difference and the code references. No product suite, paid call or live run belongs to this record.

## Identities

| File | SHA-256 | Pages |
|---|---|---|
| `docs/Optimus-Cost-Agent-Architecture-v2.22.pdf` | `139fc9d25f659f7fbda14c3a1e28c78757dcca288458373b9c3675ecd77f124b` | 25 |
| `docs/Optimus-Cost-Agent-LLD-v2.45.pdf` | `d65bd0033ce1a3331802ca726a86ff955333fa491f6a77c87807a2f80a7563d8` | 58 |
| `docs/archive/Optimus-Cost-Agent-Architecture-v2.21.pdf` (predecessor, moved unchanged) | `44a11f53eb6c55b27fa369b5849e2c454f383c0604b4e62ce148f83b88e33b38` | 23 |
| `docs/archive/Optimus-Cost-Agent-LLD-v2.44.pdf` (predecessor, moved unchanged) | `80305863042581aa1bde2517c3d9473923bcd20db2c939a2925163592c63f885` | 52 |
| `docs/archive/Optimus-Cost-Agent-Architecture-v2.18.pdf` (native baseline) | `0f8725765fecc9a93045fd26630457dfe7112508df164a3ec5bcc55dbc976807` | 13 |
| `docs/archive/Optimus-Cost-Agent-LLD-v2.41.pdf` (native baseline) | `69400fd474eb30711fcc9a061243d6a4d2e35d39d7794d4aa69f5ff51b98109b` | 40 |
| `sources/successor-edits.md` (Codex's text r2, CLI round 69, session `01a17c98-af4d-71e2-b407-c8ba2516fa9c`) | `f38d1f15cbebdc9eb5b6c6c8263cf45293f7d21561978108d874ba1151d3504e` | — |
| `sources/page-updates.json` | `04e53dee314142b717200140849f00afe146892faab40f008f97a7e1edc6fdf6` | — |

The build ran from the repository at base `bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1` (origin/main), on branch `agent/claude/plan12-4-design-docs`, with this bundle uncommitted and the predecessors already moved to `docs/archive/`.

Toolchain: Python 3.14 with reportlab 5.0.0 and pypdf 6.10.2, Windows Arial fonts, Windows 11. Pages were rendered with Poppler `pdftoppm` 25.07.0, and the text was extracted with `pdftotext` (`-enc UTF-8`).

## Page map

Baseline page numbers refer to the native baselines (HLD v2.18 and LLD v2.41).

**HLD v2.22:**
- **Replaced (body changed by this successor):** cover → 1; baseline 4 → 4–5; 6 → 7–8; 8 → 10; 9 → 11–12; 10 → 13; 11 → 14.
- **Replaced (body unchanged from v2.21):** 2 → 2; 3 → 3; 7 → 9; 12 → 15; 13 → 16.
- **Carried natively:** 5 → 6.
- **Appended:** `hld-14` → 17–20 (with the new §14.7); `hld-15` → 21–25.
- **From v2.21:** pages 1–16 map one to one onto these ranges, and v2.21 pages 17–23 (the appended chapters) map to 17–25.

**LLD v2.45:**
- **Replaced (body changed by this successor):** cover → 1; baseline 10 → 11; 11 → 12; 14 → 15–16; 16 → 18; 17 → 19; 18 → 20.
- **Every other baseline page:** keeps its v2.44 action (replaced or carried), at the same successor position up to baseline 13 and one page later from baseline 15 onward (baseline 14 now fills two pages).
- **Appended:** `lld-13` → 46–53 (with the new §13.10); `lld-14` → 54–58.
- **Carried natively:** 17 pages.

## Checks

| Check | Result |
|---|---|
| `validate_corrections.py` (filed, unchanged) on the build | **PASS** for both documents. All ten checks are true: manifest hash, page count, contiguous pages, baseline hash, every baseline page once, carried bodies equal the baseline (HLD 1 page, LLD 17 pages), predecessor hash, all predecessor pages mapped, label and footer on every page, no escape artifacts |
| Edit application | `apply_successor_edits.py` applied 48 blocks (40 document, 8 README), each OLD found exactly once; every `###` block header outside a code fence parsed as an OLD/NEW block |
| Code references | All 43 `path:line` references in the new text and covers exist and are in range at `bf440cb`; spot checks against the code (for example the decision question types `choice`, `noul`, `score` at `src/optimus_gateway/decisions.py:33`) |
| Environment equivalence | In this environment the filed `agent-localized-edit/tools/build_successors.py` rebuilds v2.21 (`44a11f53…`) and v2.44 (`80305863…`) byte for byte; their build manifest supplied this driver's v2.21/v2.44 page map |
| Rebuild determinism | Two builds of r1 gave identical hashes; the r2 filing build from the repository, after the archive moves, is byte-identical to the reviewed r2 draft |
| Rendered-text difference, v2.21 → v2.22 and v2.44 → v2.45 (`pdftotext`, headers and footers removed) | Every changed word comes from an OLD/NEW block or a cover, or moved with a page break; the single residual is `` `decision`/`action`/`guardrail_scope` `` rendering as one token. Codex's independent comparison confirmed all 39 source groups in order and all 18 natively carried bodies |
| Visual review (every page at 60 dpi; the two corrected evidence pages at 80 dpi) | Layout is intact: tables fit, headings and lists render. HLD pages 5, 8 and 12 and LLD pages 3, 16 and 22–24 are continuation pages of replaced bodies |

## History of this edition before filing

- **r1** (Codex CLI round 69, gpt-6.1-sol high): the D1(a) scope ruling, 48 edits, the new HLD §14.7 and LLD §13.10, covers and build strings.
- **Draft review** (round 69 follow-up 1, same session): verdict **accept with fixes**. Finding F1 (Claude's): seven Markdown links rendered as raw brackets on HLD page 24 and LLD page 57, because the filed renderer has no link support. r2 rewrote only those links as "label (URL)". Codex also noted that the vocabulary-based text check cannot establish order on its own, which its own comparison covered.
- **Filing build** from r2, as above.

## Not established here

Repository tests other than the documentation checks run for this change, which are reported with the change. No post-merge CI result for `bf440cb` is claimed.
