# #576 EDIT failure lifecycle — LLD v2.49 successor sources

Sources, tools and validation record for LLD v2.49, which corrects §4B.5 for [#576](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/576). The issue owns progress, review and completion; this bundle is not a work register.

## What changes

Only LLD §4B.5 (native baseline page 19), checked against main `31c6de5821b994a9498800fdfed2a2ca6b0a13f6`:

- **Wire stop reason.** A turn whose EDIT cannot be applied ends with `stopReason` `end_turn`, not `refusal` (#559 / PR #569), and its prompt response carries `_meta` `{"runStopReason": "EDIT_NOT_APPLICABLE", "outcome": "failed"}` (#268 / PR #561). An accepted cancel makes the outcome `cancelled`, and before approval the wire value too.
- **Plan updates.** The stopped run's text is never sent as a plan: a binding failure sends no plan update, and after approval no completed-plan update is sent (#570 / PR #630).
- **Completion text.** One fixed message per code that ends with the code in brackets (#574), replacing `EDIT not applied to <path> (<code>): <reason>. Nothing was written.`
- **One citation.** The completion-text pass-through now cites `_completion_message` at `31c6de5`.

The cover is new. All content outside §4B.5, including the appended §13 and §14, is carried from v2.48 unchanged with its own pins; the longer §4B.5 moves the §4B.7 table from page 23 to page 24. HLD v2.25 states none of these facts (it says only that an EDIT applicability failure stops the run, which is still true), so it has no successor. The item-by-item comparison, including the items recorded as not stated, is in [`validation-record.md`](validation-record.md).

## Contents

- `sources/edits.json`: the exact OLD/NEW edits against page 19 of the [#361 bundle's](../issue361-search-independent-metadata/) `page-updates.json`.
- `sources/page-updates.json`: the LLD page sources with those edits applied, keyed by native baseline page (LLD v2.41), as in #361. It holds only the `lld` key, because this edition builds only the LLD.
- `sources/lld-13-context-integration.md`, `sources/lld-14-capability-status.md`: the appended chapters, copied from #361 byte for byte.
- `sources/lld-cover.md`: the cover.
- `tools/derive_sources.py`: the #361 derive step narrowed to the LLD. Each OLD must occur exactly once, and the result must equal the filed sources byte for byte.
- `tools/build_successor.py`: the #361 builder narrowed to the LLD. It reuses the filed renderer of [`../capability-evidence-correction/tools/build_corrections.py`](../capability-evidence-correction/tools/build_corrections.py), and it reads the predecessor page map from the filed #361 `build-manifest.json` instead of copying it.
- [`validation-record.md`](validation-record.md): identities, the comparison table and check results.

No `build-manifest.json` is filed. A manifest is a JSON file of SHA-256 digests, which the secret-scan hook reports, and #361's filed manifest needed an operator-adopted baseline exception. The Plan 12.9 bundle filed none either. The build still writes the manifest to its output folder for the validator. The PDF, source and predecessor digests are recorded in `validation-record.md` and checked by `tests/unit/docs/test_issue576_source_bindings.py`.

## Rebuild

```bash
python -X utf8 -I docs/sources/issue576-edit-failure-lifecycle/tools/derive_sources.py . <derived-dir>
python -X utf8 -I docs/sources/issue576-edit-failure-lifecycle/tools/build_successor.py . <out-dir>
python -X utf8 -I docs/sources/capability-evidence-correction/tools/validate_corrections.py . <out-dir>
```

The build needs Python with ReportLab 5.0.0 and pypdf 6.10.2, and the Windows Arial fonts: the toolchain of the predecessor editions. These are documentation tools, not project dependencies.
