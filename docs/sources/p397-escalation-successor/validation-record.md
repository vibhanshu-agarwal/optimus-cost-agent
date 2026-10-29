# Validation record: HLD v2.23 and LLD v2.46 (local filing, 2026-10-29)

Scope: the assembly, carried native text, predecessor page coverage, label and footer presence, escape-artifact scan, rebuild determinism, the rendered-text difference and the code references. No product suite, paid call or live run belongs to this record. The product evidence for #397 is in [`../p397-escalation/validation-record.md`](../p397-escalation/validation-record.md).

## Identities

| File | SHA-256 | Pages |
|---|---|---|
| `docs/Optimus-Cost-Agent-Architecture-v2.23.pdf` | `3abcc0c047795d91350b8660c6e26943d39fea13bf99568704b91838cfbb2acb` | 27 |
| `docs/Optimus-Cost-Agent-LLD-v2.46.pdf` | `4a2f9cb64c69d6a8284b72905cb25abf6f979a18d9ccdcad37b98b790e2712a6` | 61 |
| `docs/archive/Optimus-Cost-Agent-Architecture-v2.22.pdf` (predecessor, moved unchanged) | `139fc9d25f659f7fbda14c3a1e28c78757dcca288458373b9c3675ecd77f124b` | 25 |
| `docs/archive/Optimus-Cost-Agent-LLD-v2.45.pdf` (predecessor, moved unchanged) | `d65bd0033ce1a3331802ca726a86ff955333fa491f6a77c87807a2f80a7563d8` | 58 |
| `docs/archive/Optimus-Cost-Agent-Architecture-v2.18.pdf` (native baseline) | `0f8725765fecc9a93045fd26630457dfe7112508df164a3ec5bcc55dbc976807` | 13 |
| `docs/archive/Optimus-Cost-Agent-LLD-v2.41.pdf` (native baseline) | `69400fd474eb30711fcc9a061243d6a4d2e35d39d7794d4aa69f5ff51b98109b` | 40 |
| `sources/successor-edits.md` (Codex's text r2, CLI session `01a18876-8978-7232-a3e9-7a470b8da31e`) | `2c91c41bdd021659a598feb5c547ffcfa981abc5089f2099dd47e8e00ab539f1` | — |
| `sources/page-updates.json` | `5359a0f79e53646afc6a670171a6ab81182faf6bc4ef26c8b6fddb538946c7df` | — |

The build ran from the repository at base `5977155c2bce9728156ee5898ff9e17d0ae08750` (origin/main), on branch `agent/claude/p397-design-docs`, with this bundle uncommitted and the predecessors already moved to `docs/archive/`.

Toolchain: Python 3.14 with reportlab 5.0.0 and pypdf 6.10.2, Windows Arial fonts, Windows 11. Pages were rendered with Poppler `pdftoppm` 25.07.0, and the text was extracted with `pdftotext` (`-enc UTF-8 -layout`).

## Page map

Baseline page numbers refer to the native baselines (HLD v2.18 and LLD v2.41).

**HLD v2.23:**
- **Replaced (body changed by this successor):** cover → 1; baseline 4 → 4–5; 6 → 7–8; 8 → 10.
- **Every other baseline page:** keeps its v2.22 action (replaced or carried) at the same successor position; baseline 5 → 6 is the one page carried natively.
- **Appended:** `hld-14` → 17–21 (with the new §14.8 and §14.9); `hld-15` → 22–27.
- **From v2.22:** pages 1–16 map one to one onto these ranges, and v2.22 pages 17–25 (the appended chapters) map to 17–27.

**LLD v2.46:**
- **Replaced (body changed by this successor):** cover → 1; baseline 10 → 11; 11 → 12; 14 → 15–16; 16 → 18; 17 → 19; 18 → 20; 19 → 21–24; 20 → 25; 36 → 41.
- **Every other baseline page:** keeps its v2.45 action (replaced or carried) at the same successor position. 17 pages are carried natively.
- **Appended:** `lld-13` → 46–55 (with the new §13.11 and §13.12); `lld-14` → 56–61.
- **From v2.45:** pages 1–45 map one to one onto these ranges, and v2.45 pages 46–58 map to 46–61.

## Checks

| Check | Result |
|---|---|
| `validate_corrections.py` (filed, unchanged) on the build | **PASS** for both documents. All ten checks are true: manifest hash, page count, contiguous pages, baseline hash, every baseline page once, carried bodies equal the baseline, predecessor hash, all predecessor pages mapped, label and footer on every page, no escape artifacts |
| Edit application | `apply_successor_edits.py` applied 44 blocks (38 document, 6 README), each OLD found exactly once; every `###` block header outside a code fence parsed as an OLD/NEW block. A dry run before `--readme` found each README OLD exactly once |
| Code references | All 57 `path:line` references in the text exist and are in range at `5977155` |
| Links | The NEW text and covers hold no Markdown links, which the filed renderer cannot draw (the v2.22/v2.45 F1 finding) |
| Environment equivalence | In this environment the filed `plan-12-4-auto-mode/tools/build_successors.py` rebuilds v2.22 (`139fc9d2…`) and v2.45 (`d65bd003…`) byte for byte; their build manifest supplied this driver's v2.22/v2.45 page map |
| Rebuild determinism | Two builds of r1, and two of r2, gave identical hashes; the r2 filing build from the repository, after the archive moves, is byte-identical to the r2 draft |
| Rendered-text difference, v2.22 → v2.23 and v2.45 → v2.46 (`pdftotext`, headers and footers removed) | Every changed word comes from an OLD/NEW block or a cover, or moved with a page break: 120 HLD and 106 LLD changed hunks, 0 unexplained, for r1 and again for r2. Codex's independent comparison matched all 57 ordered source/page groups, including the 18 natively carried bodies |
| Visual review (r1's changed and appended pages at 45 dpi; HLD page 24 and LLD page 59 at 80 dpi; r2's HLD pages 25–27 at 60 dpi) | Layout is intact: tables fit, headings and lists render. HLD pages 5 and 8 and LLD pages 16 and 22–24 are continuation pages of replaced bodies; HLD page 27 holds the end of §15's last paragraph |

## History of this edition before filing

- **r1** (Codex CLI, gpt-6.1-sol high): the D1(a) scope ruling, 44 edits, the new HLD §14.8–§14.9 and LLD §13.11–§13.12, covers and build strings.
- **Draft review** (follow-up 1, same session): verdict **accept with fixes**. Its one finding: the two main-push CI paragraphs (HLD §15, LLD §14) and an author note described run 40909335091 as in progress; it had completed with success at `5977155`. r2 changed only those statements and added its revision note. Codex found no other fix in the edits, the tools, the README rows, the page maps, the manifest or this bundle's README and record.
- **Filing build** from r2, as above. HLD v2.23 is one page longer than the r1 draft (27, not 26), because §15's CI paragraph grew.

## Not established here

Repository tests other than the documentation checks run for this change, which are reported with the change.
