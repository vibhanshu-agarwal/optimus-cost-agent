# Plan 12.9 successor sources (HLD v2.24, LLD v2.47, Test Strategy v1.10)

This bundle holds the sources, tools and validation record for HLD v2.24, LLD v2.47 and Test Strategy v1.10. The editions describe Plan 12.9's cost-savings report (#248, ADR-034) and, only as far as the report rests on it, Plan 12.8's durable capture and Gateway-owned Postgres ledger, at main `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498` (PR #462 merged 2026-11-02T14:02:48Z). This discharges finding F8 of `reports/plan12-cost-savings/manifest.json`.

**Authority:**
- The operator's answer, 2026-11-02 (verbatim): "Go ahead". It answered Claude's question "Go ahead with the Plan 12.9 closure steps?", whose second item read: "Design-doc successors: Codex drafts the HLD, LLD and Test Strategy successors against `a88fde8`, and I check and build them. This fixes the stale Redis ledger description, the missing route, and the missing ACP command section and Postgres test tier. The PR gets the one-off skip of the large-file hook for its PDFs, and I'll stop for your merge approval."
- Codex wrote the successor text (`sources/successor-edits.md`, its revision r3, filed byte for byte as Codex produced it; CLI session `01a19c95-6334-7012-903b-70b2b02dacc7`). Its scope ruling D1(a), the option Claude also recommended: Plan 12.9 as merged, plus Plan 12.8's capture and ledger only as far as the report rests on them and as far as the Redis statements would otherwise be false. Plans 12.5–12.7's memory work is not refreshed.
- The editions are local filings and carry the page label `LOCAL FILING - NOT ACTIVATED`; the label describes the document filing, not the product feature. Publication to main (PR and merge) needs the operator's separate approval.

## What changes

The refreshed statements are at `a88fde8`; carried statements and baseline rows keep their earlier pins. The [Plan 12.2 ordinary shipping amendment](../plan-12-2-ordinary-shipping/architecture-amendment.md) still controls the Plan 12.2 material these editions do not refresh.

The covers and `successor-edits.md` list each change:
- **HLD:** the cover; baseline pages 2, 3, 4, 7, 9, 10, 11, 12 and 13 (the Redis ledger statements and the coverage pointers); the appended §14 (edition scope, new §14.10 "Cost-savings report and its durable accounting source") and §15 (status rows and report evidence).
- **LLD:** the cover; baseline pages 2, 3, 4, 33 and 38 (the closed route lists, now ten routes, and the accounting statements); the appended §13 (new §13.13–§13.16: accounting ownership, the read contract, ACP commands, attribution and arithmetic) and §14 (status rows and report evidence).
- **Test Strategy:** the cover; baseline page 3 (the `requires_plan12_capture_postgres` tier); the appended §15 (new §15.8) and §16 (status rows, new §16.1).
- **Indexes:** `docs/README.md` (the three edition rows, the amendment's scope and this bundle) and the root `README.md` documentation table.

## Contents

- `sources/successor-edits.md`: Codex's authored text r3. It holds the three covers, 48 exact OLD/NEW document edits, 8 README edits, author notes (the D1 ruling and every file:line relied on) and the build strings.
- `sources/page-updates.json`, `sources/hld-14-*.md`, `hld-15-*.md`, `lld-13-*.md`, `lld-14-*.md`, `test-15-*.md`, `test-16-*.md`: the predecessor sources with those edits applied, keyed by **native baseline** page (HLD v2.18, LLD v2.41, Test Strategy v1.7). HLD and LLD come from [`../p397-escalation-successor/sources/`](../p397-escalation-successor/sources/); Test Strategy comes from [`../capability-evidence-correction/sources/`](../capability-evidence-correction/sources/), its last edition's bundle.
- `sources/hld-cover.md`, `sources/lld-cover.md`, `sources/test-cover.md`: the cover pages.
- `tools/apply_successor_edits.py`: derives `sources/` from the predecessor bundles and `successor-edits.md`. Each OLD must occur exactly once; every `###` block header outside a code fence must parse as an OLD/NEW block. `--readme` also applies the README blocks.
- `tools/build_successors.py`: builds the three PDFs from the archived native baselines with the filed renderer of `../capability-evidence-correction/tools/build_corrections.py`, and writes a manifest that the filed `validate_corrections.py` checks unchanged.
- `tools/predecessor-page-map.json`: baseline page to predecessor page, from the filed drivers' own build manifests.
- [`validation-record.md`](validation-record.md): identities and check results.

The tools are the v2.23/v2.46 bundle's, changed in their predecessor and bundle paths, versions, predecessor hashes, pin, dates and Codex's build strings, and extended for a third document with its own predecessor bundle. The page map moved to a data file because a third hand-written map would have been harder to check.

## Rebuild

```bash
python -X utf8 -I docs/sources/plan-12-9-cost-savings-successor/tools/apply_successor_edits.py .
python -X utf8 -I docs/sources/plan-12-9-cost-savings-successor/tools/build_successors.py . <out-dir>
python -X utf8 -I docs/sources/capability-evidence-correction/tools/validate_corrections.py . <out-dir>
```

The build needs Python with reportlab and pypdf, and the Windows Arial fonts (the toolchain of the predecessor editions). `apply_successor_edits.py --readme` applies the README rows only once: they are already in the READMEs, so a second run fails.
