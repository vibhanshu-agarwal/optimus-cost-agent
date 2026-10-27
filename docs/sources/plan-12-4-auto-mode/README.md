# Plan 12.4 Auto-mode successor sources (HLD v2.22, LLD v2.45)

This bundle holds the sources, tools and validation record for HLD v2.22 and LLD v2.45. The two editions describe opt-in Auto mode (Plan 12.4, #395) and the enforced-registry facts it rests on, at main `bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1` (PR #428 merged 2026-10-27). HLD v2.21 and LLD v2.44 move to `docs/archive/` unchanged.

**Authority:**
- The operator's instruction, 2026-10-27 (verbatim): "Start the HLD v2.22 / LLD v2.45 successor for Plan 12.4 under #395, built from the baseline page keys with Codex authoring the replace-edits. SKIP=check-added-large-files is approved for its PDFs."
- Codex wrote the successor text (`sources/successor-edits.md`, its revision r2, filed byte for byte as Codex produced it; CLI round 69, session `01a17c98-af4d-71e2-b407-c8ba2516fa9c`). Its scope ruling D1(a), the option Claude also recommended: Auto mode together with the registry facts Auto rests on (the enforced trusted registry, ADR-025's per-entry admission and operator override, ADR-026's guardrail-stage exception, ADR-007 as accepted by ADR-028). Claude checked the text against the code, assembled the sources and built the PDFs.
- The editions are local filings and carry the page label `LOCAL FILING - NOT ACTIVATED`; the label describes the document filing, not the product feature. Publication to main (PR and merge) needs the operator's separate approval.

## What changes

The refreshed statements are at `bf440cb`; carried statements and baseline status rows keep their earlier pins. The filed 2026-10-18 [Plan 12.2 ordinary shipping amendment](../plan-12-2-ordinary-shipping/architecture-amendment.md) still controls the Plan 12.2 material these editions do not refresh (compaction, numeric policy, profiles, maintenance, Guardrails and historical evidence), and ADR-024 governs interactive loop control. Neither edition folds in the full Plan 12.2 amendment or Plan 12.3.

The covers and `successor-edits.md` list each change:
- **HLD:** the cover; baseline pages 4, 6, 8, 9, 10 and 11 (the fixed-model path, enforcement and the Auto classifier statements); the appended §14 (the edition scope, registry and enforcement statements, and the new §14.7 "Auto mode: opt-in per-turn routing"); the appended §15 (its introduction, refreshed rows, new Auto rows and the Auto evidence).
- **LLD:** the cover; baseline page 10 (the model-tier table: the registry's price tiers stay and the task tiers are added); baseline pages 11, 14, 16, 17 and 18 (the figures and strategies that said Auto was not activated); the appended §13 (the edition scope, construction and registry statements, and the new §13.10 "Auto composition and per-turn routing"); the appended §14 (its introduction, refreshed rows, new Auto contract rows and the Auto evidence).
- **Indexes:** `docs/README.md` (the HLD and LLD rows, the amendment's scope, this bundle, ADR-023's qualification and the Plan 12.4 row's ADR-028 number) and the root `README.md` documentation table.

## Contents

- `sources/successor-edits.md`: Codex's authored text r2. It holds the two covers, 40 exact OLD/NEW document edits, 8 README edits, author notes (the D1 ruling and every file:line relied on) and the build strings.
- `sources/page-updates.json`, `sources/hld-14-*.md`, `hld-15-*.md`, `lld-13-*.md`, `lld-14-*.md`: the v2.21/v2.44 sources ([`../agent-localized-edit/sources/`](../agent-localized-edit/sources/)) with those edits applied, keyed by **native baseline** page (HLD v2.18, LLD v2.41).
- `sources/hld-cover.md`, `sources/lld-cover.md`: the cover pages.
- `tools/apply_successor_edits.py`: derives `sources/` from the predecessor bundle and `successor-edits.md`. Each OLD must occur exactly once; every `###` block header outside a code fence must parse as an OLD/NEW block. `--readme` also applies the README blocks, the root `README.md` ones where the block title names it.
- `tools/build_successors.py`: builds both PDFs from the archived native baselines with the filed renderer of `../capability-evidence-correction/tools/build_corrections.py`, as v2.21/v2.44 did, and writes a manifest that the filed `validate_corrections.py` checks unchanged.
- [`validation-record.md`](validation-record.md): identities and check results.

## Rebuild

```bash
python -X utf8 -I docs/sources/plan-12-4-auto-mode/tools/apply_successor_edits.py .
python -X utf8 -I docs/sources/plan-12-4-auto-mode/tools/build_successors.py . <out-dir>
python -X utf8 -I docs/sources/capability-evidence-correction/tools/validate_corrections.py . <out-dir>
```

The build needs Python with reportlab and pypdf, and the Windows Arial fonts (the toolchain of the predecessor editions). `apply_successor_edits.py --readme` applies the README rows only once: they are already in the READMEs, so a second run fails.
