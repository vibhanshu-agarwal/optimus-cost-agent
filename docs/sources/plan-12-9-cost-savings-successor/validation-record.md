# Validation record: HLD v2.24, LLD v2.47 and Test Strategy v1.10 (local filing, 2026-11-02)

Scope: the assembly, carried native text, predecessor page coverage, label and footer presence, escape-artifact scan, rebuild determinism, the rendered-text difference and the code references. No product suite, paid call or live run belongs to this record. The product evidence for Plan 12.9 is in [`reports/plan12-cost-savings/`](../../../reports/plan12-cost-savings/).

## Identities

| File | SHA-256 | Pages |
|---|---|---|
| `docs/Optimus-Cost-Agent-Architecture-v2.24.pdf` | `cfd627f2cc5c3c026072940590f535a8c65c282c26fd19f0ed14893e6f3852c5` | 29 |
| `docs/Optimus-Cost-Agent-LLD-v2.47.pdf` | `e8e42bb59dcdcfe17f297ad968854950e8bca3babfaad440221ef1a649ba0d51` | 64 |
| `docs/Optimus-Cost-Agent-Test-Strategy-v1.10.pdf` | `e9346917c705099631d3b171fa70da130ad17619e496802675701ec8b0bab95a` | 26 |
| `docs/archive/Optimus-Cost-Agent-Architecture-v2.23.pdf` (predecessor, moved unchanged) | `3abcc0c047795d91350b8660c6e26943d39fea13bf99568704b91838cfbb2acb` | 27 |
| `docs/archive/Optimus-Cost-Agent-LLD-v2.46.pdf` (predecessor, moved unchanged) | `4a2f9cb64c69d6a8284b72905cb25abf6f979a18d9ccdcad37b98b790e2712a6` | 61 |
| `docs/archive/Optimus-Cost-Agent-Test-Strategy-v1.9.pdf` (predecessor, moved unchanged) | `21ab8cacd90fd56bdce7841c48efaf2642cc45555dc5fa43f40786e12fbb60fd` | 22 |
| `sources/successor-edits.md` (Codex's text r3, CLI session `01a19c95-6334-7012-903b-70b2b02dacc7`) | `36c2aecf0efe401a14543cd84936ca472febba001601ee719a1fefa0cfbb4690` | — |
| `sources/page-updates.json` | `9ae6677c5f4c85f335969bd8838942b70ed0effaae92d76ecf8666ff77cee4cd` | — |

The native baselines are HLD v2.18, LLD v2.41 and Test Strategy v1.7, in `docs/archive/`, with the hashes `build_corrections.py` pins.

The build ran from the repository at base `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498` (origin/main), on branch `agent/claude/plan12-9-design-docs`, with this bundle uncommitted and the predecessors already moved to `docs/archive/`.

Toolchain: Python 3.14.4 with reportlab 5.0.0 and pypdf 6.10.2, Windows Arial fonts (version 7.07), Windows 11. Text was extracted with `pdftotext` (`-enc UTF-8 -layout`).

## Page map

Baseline page numbers refer to the native baselines. `tools/predecessor-page-map.json` holds the predecessor side.

| Edition | Replaced or changed baseline pages → successor pages | Carried natively | Appended |
|---|---|---|---|
| HLD v2.24 | cover → 1; 2 → 2; 3 → 3; 4 → 4–5; 6 → 7–8; 7 → 9; 8 → 10; 9 → 11–12; 10 → 13; 11 → 14–15; 12 → 16; 13 → 17 | 1 page | `hld-14` → 18–23; `hld-15` → 24–29 |
| LLD v2.47 | cover → 1; 2 → 2–3; 3 → 4; 4 → 5; 33 → 38; 38 → 43; other replaced pages keep their v2.46 bodies and positions | 17 pages | `lld-13` → 46–57; `lld-14` → 58–64 |
| Test Strategy v1.10 | cover → 1; 3 → 3; other replaced pages keep their v1.9 bodies and positions | 4 pages | `test-15` → 16–21; `test-16` → 22–26 |

From the predecessors: HLD v2.23 pages 1–16 map to these ranges and 17–27 to 18–29; LLD v2.46 pages 1–45 map one to one and 46–61 to 46–64; Test Strategy v1.9 pages 1–15 map one to one and 16–22 to 16–26.

## Checks

| Check | Result |
|---|---|
| `validate_corrections.py` (filed, unchanged) on the build | **PASS** for all three documents. All ten checks are true: manifest hash, page count, contiguous pages, baseline hash, every baseline page once, carried bodies equal the baseline, predecessor hash, all predecessor pages mapped, label and footer on every page, no escape artifacts |
| Edit application | `apply_successor_edits.py` applied 56 blocks (48 document, 8 README), each OLD found exactly once; every `###` block header outside a code fence parsed as an OLD/NEW block. A dry run before `--readme` found each README OLD exactly once |
| Code references | All 133 `path:line` references in the text exist and are in range at `a88fde8` (a line-count check, not a reading of each) |
| Links | The NEW text and covers hold no Markdown links, which the filed renderer cannot draw |
| Rebuild determinism | Two builds of r1 gave identical hashes. The r3 draft build and the filing build, after the archive moves, are byte-identical, and equal r2's build, because r3 changes only author notes and one build string the tool already held |
| Rendered-text difference, predecessor → successor (`pdftotext`, headers and footers removed, compared word by word) | Every added word is in an edit or a cover, or is an identifier wrapped mid-word by a narrow table: 2,211 HLD, 3,038 LLD and 2,582 Test Strategy added words, 0 unexplained. Every removed word is in an OLD, a predecessor cover or the new text, except 10 LLD fragments, which are identifiers wrapped mid-word in the replaced rows. Codex's independent comparison matched all 51 ordered source/page groups and the 22 natively carried bodies |
| Visual review | Codex: all 119 pages of r1 as contact sheets, enlarged HLD 26, LLD 59 and Test Strategy 20; on r2, HLD 2 and 3, LLD 2 and 5 and Test Strategy 17 and 26. Claude: r2's LLD 2 and Test Strategy 17. Tables fit, and headings and lists render. No one reviewed every page of the filed build by eye; its pages differ from r1's only by the r2 text changes |

## Predecessor rebuilds are not byte-identical here

The filed drivers built the predecessors for the page map, and they do not reproduce the filed bytes in this environment, as they did on 2026-10-29:

| Edition | Filed SHA-256 | Rebuilt SHA-256 | Rebuilt is smaller by |
|---|---|---|---|
| HLD v2.23 | `3abcc0c0…` | `6aeee4006db64ec394bb2a9df73de2a4e71faa87154c40ced4561df691884f7b` | 9 bytes |
| LLD v2.46 | `4a2f9cb6…` | `7df37af434cc4ccdb35b561cb698f32753aebaa1553562964644a8bad05d449c` | 15 bytes |
| Test Strategy v1.9 | `21ab8cac…` | `f40187375aaeeca1cafa9c0b931bdb332cacc19e1fbdd2011d6ca5e795c536f5` | 7 bytes |

Page counts are equal, and the extracted text is identical on every page, so the page map stands. Codex compared the decoded PDF objects: only embedded TrueType fonts differ, only in their `head` and `name` tables, and the inspected name records move from Version 7.06 to Version 7.07. Glyph and metric tables are equal. The rebuilt files are therefore evidence for the page map and not reconstructions of the filed bytes. Rebuilding these successors later, after another font update, can likewise change their bytes.

## History of this edition before filing

- **r1** (Codex CLI, gpt-6.1-sol high): the D1(a) scope ruling, 56 edits, the new HLD §14.10, LLD §13.13–§13.16 and Test Strategy §15.8 and §16.1, covers and build strings.
- **Draft review, r2** (follow-up 1, same session): named #465, filed after r1, as the owner of the Gateway-attachment gap; stated main's push CI result at `a88fde8` (run 41458258151, success); shortened one HLD edit that left a heading alone on a page; qualified the LLD's carried seven-route page; corrected a false tool comment.
- **r3** (follow-up 2, same session): verdict on r2's build "accept with fixes". It removed a transient "unverified" clause from the Test Strategy PDF subject and corrected two author-note line ranges. No cover, document-body edit, README edit or OLD changed.
- **Filing build** from r3, as above.

## Not established here

Repository tests other than the documentation checks run for this change, which are reported with the change.
