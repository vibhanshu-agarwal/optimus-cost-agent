# Agent-mode localized EDIT successor sources (HLD v2.21, LLD v2.44)

This bundle holds the sources, tools and validation record for HLD v2.21 and LLD v2.44. These two editions bring the design documents in line with the Agent-mode localized EDIT directive shipped by PR #411 (merge `d13fd34`, closing #407). They describe main `57e2069`, which also includes the merged follow-through from PR #413 (#410: the parser line rules and WRITE's line-ending fit) and PR #414 (#412: the failed EDIT's closed code in `agent_run`). HLD v2.20 and LLD v2.43 move to `docs/archive/` unchanged.

**Authority:**
- The operator approved the change list (r3, with decisions D1–D4) on 2026-10-24, together with Codex drafting the text, this build, the filing rebuild, and re-pinning these unpublished editions to the latest main before any PR.
- Codex wrote the successor text (`sources/successor-edits.md`, its revision r4, filed byte for byte as Codex produced it). Claude checked it against the code at `57e2069`, assembled the sources and built the PDFs.
- The editions are local filings and carry the page label `LOCAL FILING - NOT ACTIVATED`. Publication to main (push, PR, merge) needs the operator's separate approval.

## What changes

The editions state the Agent-mode EDIT directive and correct the statements about the ACP WRITE/EDIT execution path that follow from it. Provenance is mixed:
- the new statements are at `d13fd34`;
- carried statements and baseline status rows keep their `91fd64a` pin.

The filed 2026-10-18 [Plan 12.2 ordinary shipping amendment](../plan-12-2-ordinary-shipping/architecture-amendment.md) still controls the sections it names. Neither edition folds it in.

The covers and `successor-edits.md` list each change. The change list maps it to:
- **HLD:** the cover; §2; §6 step 7; §7; the §8 key rule plus a qualification of the native §8 tool table; §10.B; §10.E; §13; and §15 (its introduction, a qualified row, a new EDIT row and the EDIT evidence).
- **LLD:** the cover; §4A (the state machine, permission matrix and pathway); the new §4B (directive plan and localized EDIT); §13.4; §13.8; and §14 (its introduction, a qualified row, a new EDIT row and the EDIT evidence).

## Contents

- `sources/successor-edits.md`: Codex's authored text. It holds the two covers, 23 exact OLD/NEW edits, the README rows and the build strings (label, footer, PDF title).
- `sources/page-updates.json` and `sources/hld-14-*.md`, `hld-15-*.md`, `lld-13-*.md`, `lld-14-*.md`: the 2026-10-15 correction sources ([`../capability-evidence-correction/sources/`](../capability-evidence-correction/sources/)) with those edits applied. Only the `hld` and `lld` pages are kept, and `hld-14` is unchanged.
- `sources/hld-cover.md`, `sources/lld-cover.md`: the cover pages.
- `tools/apply_successor_edits.py`: derives `sources/` from the predecessor bundle and `successor-edits.md`. It asserts that each OLD occurs exactly once, and `--readme` also applies the three `docs/README.md` rows.
- `tools/build_successors.py`: builds both PDFs from the archived native baselines (HLD v2.18, LLD v2.41). It reuses the filed renderer of `../capability-evidence-correction/tools/build_corrections.py` and writes a manifest that the filed `validate_corrections.py` checks unchanged.
- [`validation-record.md`](validation-record.md): identities and check results.

## Rebuild

```bash
python -X utf8 -I docs/sources/agent-localized-edit/tools/apply_successor_edits.py .
python -X utf8 -I docs/sources/agent-localized-edit/tools/build_successors.py . <out-dir>
python -X utf8 -I docs/sources/capability-evidence-correction/tools/validate_corrections.py . <out-dir>
```

The build needs Python with reportlab and pypdf, and the Windows Arial fonts (the same toolchain as the 2026-10-15 correction). `apply_successor_edits.py --readme` applies the README rows only once: those rows are already in `docs/README.md`, so a second run fails.
