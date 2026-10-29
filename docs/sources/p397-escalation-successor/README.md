# #397 successor sources (HLD v2.23, LLD v2.46)

This bundle holds the sources, tools and validation record for HLD v2.23 and LLD v2.46. The two editions describe ADR-029's single Auto escalation (#397) and the host/Gateway timing contract, at main `5977155c2bce9728156ee5898ff9e17d0ae08750` (PR #437 merged 2026-10-29). HLD v2.22 and LLD v2.45 move to `docs/archive/` unchanged.

**Authority:**
- The operator's answer, 2026-10-29 (verbatim): "Yes, all four". It answered Claude's question "Go ahead with the post-merge follow-ups?", whose fourth item read: "The HLD v2.23 / LLD v2.46 successor PR: Codex writes the edits and I check and build them. It covers escalation, the host/Gateway timing contract and `docs/README.md` rows 17–18. #397 closes after it merges."
- Codex wrote the successor text (`sources/successor-edits.md`, its revision r2, filed byte for byte as Codex produced it; CLI session `01a18876-8978-7232-a3e9-7a470b8da31e`). Its scope ruling D1(a), the option Claude also recommended: ADR-029's escalation, the ADR-024 recovery it extends as far as rung 2 requires, the host/Gateway timing boundary and the documentation indexes. A full Plan 12.3 refresh, ADR-030's approval storage and #434's ordering/lifecycle/queue contract are outside it. Claude checked the text against the code, assembled the sources and built the PDFs.
- The editions are local filings and carry the page label `LOCAL FILING - NOT ACTIVATED`; the label describes the document filing, not the product feature. Publication to main (PR and merge) needs the operator's separate approval.

## What changes

The refreshed statements are at `5977155`; carried statements and baseline rows keep their earlier pins. The [Plan 12.2 ordinary shipping amendment](../plan-12-2-ordinary-shipping/architecture-amendment.md) still controls the Plan 12.2 material these editions do not refresh.

The covers and `successor-edits.md` list each change:
- **HLD:** the cover; baseline pages 4, 6 and 8 (§6 step 5, and the loop-control statements of §9 and §10.B); the appended §14 (its edition scope, the Auto statements, and the new §14.8 "One recovery escalation in interactive Auto planning" and §14.9 "Host/Gateway timing boundary"); the appended §15 (its introduction, the escalation and timing rows, and the #397 evidence).
- **LLD:** the cover; baseline pages 10, 11, 14, 16, 17, 18, 19, 20 and 36 (the model-tier and scope statements, the fixed-model-per-turn statements, and the resend descriptions, now qualified by the planning-level escalation); the appended §13 (its edition scope, §13.4 and §13.10.3 qualifications, and the new §13.11 "ADR-029: one mid-turn Auto recovery move" and §13.12 "Host/Gateway timing contract"); the appended §14 (its introduction, the escalation and timing contract rows, and the #397 evidence).
- **Indexes:** `docs/README.md` (the HLD and LLD rows, the amendment's scope and this bundle) and the root `README.md` documentation table.

## Contents

- `sources/successor-edits.md`: Codex's authored text r2. It holds the two covers, 38 exact OLD/NEW document edits, 6 README edits, author notes (the D1 ruling and every file:line relied on) and the build strings.
- `sources/page-updates.json`, `sources/hld-14-*.md`, `hld-15-*.md`, `lld-13-*.md`, `lld-14-*.md`: the v2.22/v2.45 sources ([`../plan-12-4-auto-mode/sources/`](../plan-12-4-auto-mode/sources/)) with those edits applied, keyed by **native baseline** page (HLD v2.18, LLD v2.41).
- `sources/hld-cover.md`, `sources/lld-cover.md`: the cover pages.
- `tools/apply_successor_edits.py`: derives `sources/` from the predecessor bundle and `successor-edits.md`. Each OLD must occur exactly once; every `###` block header outside a code fence must parse as an OLD/NEW block. `--readme` also applies the README blocks, the root `README.md` ones where the block title names it.
- `tools/build_successors.py`: builds both PDFs from the archived native baselines with the filed renderer of `../capability-evidence-correction/tools/build_corrections.py`, as v2.22/v2.45 did, and writes a manifest that the filed `validate_corrections.py` checks unchanged.
- [`validation-record.md`](validation-record.md): identities and check results.

The tools are the v2.22/v2.45 bundle's, changed only in their predecessor and bundle paths, versions, predecessor hashes and page map, pin, dates and Codex's build strings.

## Rebuild

```bash
python -X utf8 -I docs/sources/p397-escalation-successor/tools/apply_successor_edits.py .
python -X utf8 -I docs/sources/p397-escalation-successor/tools/build_successors.py . <out-dir>
python -X utf8 -I docs/sources/capability-evidence-correction/tools/validate_corrections.py . <out-dir>
```

The build needs Python with reportlab and pypdf, and the Windows Arial fonts (the toolchain of the predecessor editions). `apply_successor_edits.py --readme` applies the README rows only once: they are already in the READMEs, so a second run fails.
