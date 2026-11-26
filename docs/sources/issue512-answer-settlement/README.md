# #512 Agent-mode answer settlement — HLD v2.26 and LLD v2.50 successor sources

Sources, tools and validation record for HLD v2.26 and LLD v2.50, which bring the documents up to date with [#512](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/512) and PR #657. The issue owns progress, review and completion; this bundle is not a work register.

## What changes

Checked against main `72d2349bba987df419ac69a23694ff1766dee12f` (PR #657 merged):

- **LLD §4B.1 (native baseline page 19).** The multi-turn prompt version is now `MULTI_TURN_PLANNER_PROMPT_VERSION:2026-11-26-p512-answer`, not the #407/#410 version. The grammar has an `ANSWER:` form, and an Agent-mode answer settles as a completed run with `runStopReason` `PLANNING_ANSWERED`: final text only, no plan update, and a continuity checkpoint that claims no completed task.
- **LLD §13.11.1 and §13.11.3 (appended chapter).** A waiting answer follows the same escalation and check-in rules as a waiting refusal.
- **HLD §14.8 (appended chapter).** An answer settled after the recovery nudge is treated as a refusal settled after it, and a first answer outside an episode ends the turn with the answer.

The covers are new. All other content is carried from LLD v2.49 and HLD v2.25 unchanged, each with its own pins. Both editions keep their predecessors' page counts (64 and 29). The comparison with main, including what was checked and found already true or not stated, is in [`validation-record.md`](validation-record.md).

## Contents

- `sources/edits.json`: the four exact OLD/NEW edits, which Codex authored through its CLI and Claude reviewed. One edit is against page 19 of the [#576 bundle's](../issue576-edit-failure-lifecycle/) `page-updates.json`, two against its `lld-13-context-integration.md`, and one against the [#361 bundle's](../issue361-search-independent-metadata/) `hld-14-context-engine.md`.
- `sources/page-updates.json`: the HLD page sources (from #361) and the LLD page sources (from #576) with those edits applied, keyed by native baseline page (HLD v2.18, LLD v2.41).
- `sources/hld-14-context-engine.md` and `sources/lld-13-context-integration.md`: the edited appended chapters. `sources/hld-15-capability-status.md` and `sources/lld-14-capability-status.md` are copied from their predecessors byte for byte.
- `sources/hld-cover.md`, `sources/lld-cover.md`: the covers.
- `tools/derive_sources.py`: the #576 derive step, widened to both documents and to edits of an appended chapter. Each OLD must occur exactly once, and the result must equal the filed sources byte for byte.
- `tools/build_successor.py`: the #576 builder, widened to both documents as #361's was. It reuses the filed renderer of [`../capability-evidence-correction/tools/build_corrections.py`](../capability-evidence-correction/tools/build_corrections.py). HLD v2.25's page map comes from the filed #361 `build-manifest.json`. #576 filed no manifest, so LLD v2.49's map comes from rebuilding v2.49 with #576's own builder, which must reproduce the filed PDF byte for byte.
- [`validation-record.md`](validation-record.md): identities, checks and the comparison with main.

As with #576, no `build-manifest.json` is filed: the build writes it to its output folder for the validator. The PDF, source and predecessor digests are recorded in `validation-record.md` and checked by `tests/unit/docs/test_issue512_source_bindings.py`.

## Rebuild

```bash
python -X utf8 -I docs/sources/issue512-answer-settlement/tools/derive_sources.py . <derived-dir>
python -X utf8 -I docs/sources/issue512-answer-settlement/tools/build_successor.py . <out-dir>
python -X utf8 -I docs/sources/capability-evidence-correction/tools/validate_corrections.py . <out-dir>
```

The validator exits zero even when a check fails: the result is the `status` field of the `document-validation.json` it writes, which must be `PASS` for both documents.

The build needs Python with ReportLab 5.0.0 and pypdf 6.10.2, and the Windows Arial fonts: the toolchain of the predecessor editions. These are documentation tools, not project dependencies.
