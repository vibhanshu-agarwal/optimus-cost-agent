# #361 search-independent metadata — specification successor sources

Complete successor inputs for HLD v2.25, LLD v2.48 and Test Strategy v1.11, built by Codex and reviewed by Claude under the operator's 2026-11-17 adoption and end-to-end delivery authority for [#361](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/361). Live probes and cleanup remain prohibited.

The changes implement only package/OSV construction and dispatch independent of Tavily configuration. Redis URL and normalized domain policy remain required. Current search and extract remain Tavily-backed; both fail closed without the key. The broader independent-extract target remains specified/not implemented, with [operator-approved custody accepted by #362](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/362#issuecomment-6953756630).

## Inputs and preservation

The current predecessor editions HLD v2.24, LLD v2.47 and Test Strategy v1.10 were reproduced **byte-for-byte** from the complete [Plan12.9 source bundle](../plan-12-9-cost-savings-successor/) before deriving this successor. Their later accounting, Auto, timing and other qualified claims are retained at their own pins. No frozen predecessor source or historical evidence is edited. Predecessor PDFs move unchanged into `docs/archive/`.

`sources/edits.json` records each exact OLD/NEW change; `derive_sources.py` requires unique predecessor matches and checks all generated complete source files against the filed inputs. The new Test Strategy native-baseline page5 preserves the original tool/settings requirements while adding named unit verification and an explicit unmet live release gate. Covers identify the current narrow edition scope rather than relabelling historical evidence.

The builder reuses the existing correction renderer/validator and the immediately preceding three-document driver, changing only versions, identities, date, ownership, edition metadata and predecessor maps. `tools/predecessor-page-map.json` derives directly from the byte-reproduced predecessor build manifest. `sources/page-updates.json` uses the original native-baseline page numbering, not current PDF page numbers.

## Rebuild and verification

Use a dedicated Python environment with ReportLab 5.0.0 and pypdf 6.10.2, plus installed Windows Arial fonts. Poppler is used for visual inspection. These are documentation tooling, not production dependencies.

```bash
python -X utf8 docs/sources/issue361-search-independent-metadata/tools/derive_sources.py . tmp/issue361/derived-sources
python -X utf8 docs/sources/issue361-search-independent-metadata/tools/build_successors.py . tmp/issue361/successor-build
python -X utf8 docs/sources/capability-evidence-correction/tools/validate_corrections.py . tmp/issue361/successor-build
```

The filed `build-manifest.json`, `document-validation.json` and `validation-record.md` bind outputs, predecessor preservation, source identities and checks. #361 holds current progress, review, CI and completion records; this bundle is not a second work register.

## Evidence boundary

The named builder, handler, config-built real-loopback HTTP and bounded-rejection tests verify configuration/dispatch with controlled external boundaries. Real provider classes reach a local HTTP fixture through configured base URLs; only the Redis factory is replaced in positive tests. No live provider, live Redis or GUI result is claimed. Test Strategy's real release gate remains UNRUN. Focused Windows and WSL evidence, scoped coverage, final PR CI and actual-merge CI keep separate identities and qualifications; prior failed/skip/UNRUN/reused measurements remain visible.
