# Validation record: HLD v2.21 and LLD v2.44 (local filing, 2026-10-24)

Scope: the assembly, carried native text, predecessor page coverage, label and footer presence, escape-artifact scan, rebuild determinism and the rendered-text difference. No product suite, paid call or live run belongs to this record.

## Identities

| File | SHA-256 | Pages |
|---|---|---|
| `docs/Optimus-Cost-Agent-Architecture-v2.21.pdf` | `44a11f53eb6c55b27fa369b5849e2c454f383c0604b4e62ce148f83b88e33b38` | 23 |
| `docs/Optimus-Cost-Agent-LLD-v2.44.pdf` | `80305863042581aa1bde2517c3d9473923bcd20db2c939a2925163592c63f885` | 52 |
| `docs/archive/Optimus-Cost-Agent-Architecture-v2.20.pdf` (predecessor, moved unchanged) | `52c35442a0d9027dc4b18a693284c45406cf02913001a59f2df364c77a2e176a` | 20 |
| `docs/archive/Optimus-Cost-Agent-LLD-v2.43.pdf` (predecessor, moved unchanged) | `3fb89935201eb5947eff666a97431653d264ee482b8a5a8a6a4d229d4c8b7c27` | 48 |
| `docs/archive/Optimus-Cost-Agent-Architecture-v2.18.pdf` (native baseline) | `0f8725765fecc9a93045fd26630457dfe7112508df164a3ec5bcc55dbc976807` | 13 |
| `docs/archive/Optimus-Cost-Agent-LLD-v2.41.pdf` (native baseline) | `69400fd474eb30711fcc9a061243d6a4d2e35d39d7794d4aa69f5ff51b98109b` | 40 |
| `sources/successor-edits.md` (Codex's text r4, CLI session `01a16e2f-4d47-7263-9e2d-68c5e55d8fd8`) | `3bfa99fa874663203ac963d5c983a54669c124f77f329155d5449b11bbadd926` | — |
| `sources/page-updates.json` | `698467a43107784306cd7481da8f4c6b87f862e59270a1b4bff2d036f23cea36` | — |

The build ran from the repository at base `57e2069414fef32c6a6e4de42bd0dc7fb9f4f1ac` (origin/main), on branch `agent/claude/p407-design-doc-successors`, with this bundle uncommitted.

Toolchain: Python 3.14.4, reportlab 5.0.0, pypdf 6.10.2, Windows Arial fonts, Windows 11. Contact sheets were rendered with Poppler `pdftoppm` 25.07.0, and the text was extracted with `pdftotext` 4.06 (xpdf).

## Page map

Baseline page numbers refer to the native baselines (HLD v2.18 and LLD v2.41).

**HLD v2.21:**
- **Replaced (body changed by this successor):**
  - cover → 1;
  - baseline 2 → 2;
  - baseline 4 → 4–5;
  - baseline 6 → 7–8;
  - baseline 8 → 10;
  - baseline 9 → 11–12;
  - baseline 13 → 16.
- **Replaced (body unchanged from v2.20):** 3 → 3; 7 → 9; 10 → 13; 11 → 14; 12 → 15.
- **Carried natively:** 5 → 6.
- **Appended:** `hld-14` → 17–19; `hld-15` → 20–23.
- **From v2.20:** pages 1–14 map one to one onto these ranges, and v2.20 pages 15–20 (the appended chapters) map to 17–23.

**LLD v2.44:**
- **Replaced (body changed by this successor):**
  - cover → 1;
  - baseline 14 → 15;
  - baseline 16 → 17;
  - baseline 17 → 18;
  - baseline 19 → 20–23 (§4A failure lifecycle, the new §4B, then §5).
- **Every other baseline page:** keeps its v2.43 action (replaced or carried) at a successor position one or four pages later.
- **Appended:** `lld-13` → 45–48; `lld-14` → 49–52.
- **Carried natively:** 17 pages.

## Checks

| Check | Result |
|---|---|
| `validate_corrections.py` (filed, unchanged) on the build | **PASS** for both documents. All ten checks are true: manifest hash, page count, contiguous pages, baseline hash, every baseline page once, carried bodies equal the baseline (HLD 1 page, LLD 17 pages), predecessor hash, all predecessor pages mapped, label and footer on every page, no escape artifacts |
| Edit application | `apply_successor_edits.py` applied 23 edits, each found exactly once. `hld-14` is byte-identical to its predecessor. A regeneration without `--readme` leaves `docs/README.md` unchanged |
| Code references | Every file:line reference in the new §4B resolves at `57e2069` to the construct it names (52 ranges checked) |
| Rebuild determinism | Two builds give identical hashes, as did each earlier build pair, including one made after the predecessors moved to `docs/archive/` |
| Environment equivalence | In this environment the filed `build_corrections.py` rebuilds v2.20 (`52c35442…`) and v2.43 (`3fb89935…`) byte for byte |
| Rendered-text difference, v2.20 → v2.21 and v2.43 → v2.44 (`pdftotext`, headers and footers removed) | The only changes are the edits, the new label and footer, and moved page breaks |
| Visual review (contact sheets of every page, 70 dpi) | Layout is intact: tables, the §10.B figure, the §4B code blocks, numbered steps and the limits table. HLD pages 5 and 8 are short overflow pages (the §7 scope note; the end of §9 plus the §10 introduction) |

## History of this edition before filing

- **Draft, pinned at `d13fd34`.** Codex reviewed the rendered draft: Codex CLI gpt-6.1-sol, high, session `01a16de4-1764-7363-aee9-6ca186744d7a`, verdict ACCEPT WITH FIXES.
  - **Confirmed:** rendered fidelity (all 39 source groups in order), the recorded hashes and the Git blobs of the archive moves.
  - **Finding: the tool asserted README rows without `--readme`.** Fixed: they now apply only with `--readme`.
  - **Finding: the draft label and the owner placeholder.** Resolved by the filing revision (Codex's text r3).
  - **Finding: drift in the root `README.md`.** Its documentation table linked HLD v2.19, LLD v2.42, Test Strategy v1.8 and Guardrails v1.4 at paths that no longer exist. Those links now point to the current editions.
- **First filing build, at `d13fd34`.** It was committed locally, never pushed, and then superseded. PRs #413 and #414 merged into main and made three of its statements stale, so the operator decided to re-pin before publication.
- **Re-pin to `57e2069`.** The branch was rebased onto `57e2069`, and Claude verified the fact changes in the code. Codex's text r4 re-pins every code statement and recomputes every reference. It also restates §4B.1 (#410's R1 line rules and WRITE's line-ending fit and mixed-ending refusal), §4B.6 (`edit_failure_code` in `agent_run`) and §4B.7, and adds the evidence for PRs #413 and #414 and for main's CI.

## Not established here

Repository tests other than the documentation checks run for this change, which are reported with the change.
