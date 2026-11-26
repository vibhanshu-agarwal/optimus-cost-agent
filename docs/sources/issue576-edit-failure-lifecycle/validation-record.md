# #576 LLD v2.49 validation

A dated evidence record, not the work register: [#576](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/576) owns review and completion. Built 2026-11-26 on Windows from main `31c6de5821b994a9498800fdfed2a2ca6b0a13f6`.

## Identities

| Item | SHA-256 |
|---|---|
| `docs/Optimus-Cost-Agent-LLD-v2.49.pdf` (64 pages) | `3a8c05bd37e0be1dd787725fa49ad5aa09a692968a66b66548e49a6d3fac3a24` |
| Predecessor `Optimus-Cost-Agent-LLD-v2.48.pdf` (moved to `docs/archive/` unchanged) | `620ee455216572e71c28ae7923c12ccc7673659089bae01a0199e807cd44644f` |
| `sources/page-updates.json` | `5bbc77b75e05fb02ab8ed46e1286bdbb84ab00fbf110f6fccc808d436fa3f665` |
| `sources/lld-cover.md` | `9c126a82473af214f2ec91094eda994a15c22a838bce32330a54c3261faf8f4f` |
| `sources/edits.json` | `f5216866f5621b6a516d813394cd70085abebe5cdc68ab9431ffc28313ad19e1` |
| `sources/lld-13-context-integration.md` (equal to #361's) | `4150b69b8e2dc2101ffe40461dde8348de3aa567d79f21ef9b48e5f259f9848e` |
| `sources/lld-14-capability-status.md` (equal to #361's) | `352dc4374cda2bf89f2c61edce9d0ae36d934556553d5c28d8c8b834ae6e4fc1` |

Toolchain: Python 3.14, ReportLab 5.0.0, pypdf 6.10.2, Windows Arial fonts; Poppler 25.07 for text extraction and page images.

## Checks

| Check | Result |
|---|---|
| Predecessor reproduced first: the filed #361 `derive_sources.py` and `build_successors.py` at `31c6de5` | 10 sources and 21 edits verified; LLD v2.48 and HLD v2.25 rebuilt byte for byte (`620ee455…`, `30f39922…`) |
| `derive_sources.py` (this bundle) | 3 sources and 2 exact edits verified against the filed sources |
| `build_successor.py`, run twice into separate folders | Same PDF bytes both times, `3a8c05bd…`; 64 pages, the same count and baseline mapping as v2.48 |
| Filed `validate_corrections.py` | PASS, no failures: manifest hash, page count, contiguous pages, baseline hash, every baseline page once, 17 carried bodies equal to the baseline, predecessor hash, all 64 predecessor pages mapped, label and footer on every page, no escape artifacts |
| Rendered pages read | Page 1 (cover) and pages 21 to 24 (baseline page 19, §4A to §5) rendered at 70 dpi and read, and their text extracted and read: no clipping, overprinting or broken table. The completion-text template is two lines in its code block, because the renderer breaks code lines at 105 characters; the text says it is one line. |

## Comparison with main

Source paths under `src/optimus/`, line numbers at `31c6de5`.

| # | Item | What the documents said | What main does | Verdict |
|---|---|---|---|---|
| 1 | Wire stop reason for an unappliable EDIT (#559 / PR #569) | LLD v2.48 §4B.5: `stopReason` is `refusal`. HLD v2.25: only that an EDIT applicability failure stops the run. | `_stop_reason` returns `end_turn` for `EDIT_NOT_APPLICABLE`, before approval (binding) and after it (`acp/spec.py:4135`, `:4288–4299`); a cancel accepted before approval returns `cancelled` (`:2514–2526`). | LLD stale, corrected. HLD already correct. |
| 2 | Completion text (#574) | LLD v2.48 §4B.5: `EDIT not applied to <path> (<code>): <reason>. Nothing was written.` HLD: not stated. | `edit_failure_text`: `The change was not made to {path}, because {reason}. The plan made no changes and ran none of its tests. {next_step}. ({code})` (`agent/edits.py:28–52`, `:66–76`), passed through by `_completion_message` (`acp/spec.py:4141–4142`). | LLD stale, corrected. HLD not stated. |
| 3 | `_meta` `runStopReason` and `outcome` on the prompt response (#268 / PR #561) | Not stated in either. | `_prompt_result` (`acp/spec.py:4302–4308`); a FAILED run settles as `failed` (`:4278–4285`), or `cancelled` if a cancel was accepted first (`acp/lifecycle.py:337–341`). | Not stated. Added to §4B.5 for the EDIT turn only. |
| 4 | `UNSAFE_TEST_DIRECTIVE`, `WRITE_DIRECTIVE_NOT_EXECUTED` end as `end_turn` with new text and no completed plan (#565 / PR #569) | Not stated in either. | `acp/spec.py:4129–4135`, `:4295`; `agent/runner.py:1486–1499`. | Not stated; nothing to correct. |
| 5 | The live verifier requires `_meta.outcome == "completed"` (PR #569) | Not stated in either. | `_not_completed_message` rejects an `end_turn` response whose `_meta.outcome` is present and not `completed`, and accepts a response without that field from an older agent (`acp/operator_verify.py:755–762`). | Not stated; nothing to correct. |
| 6 | Plan 12.13's three workspace-context stops end as `end_turn` (`6dd6b97`) | Not stated. `docs/README.md` records that neither edition covers Plan 12.13; the PDFs do not name it. | `acp/spec.py:4087–4093`, `:4297–4298`. | Not stated; nothing to correct. |
| 7 | A turn that did not complete sends no completed plan and no prose plan entries (#570 / PR #630) | Not stated in either. | The gate is the run result: a stopped planning run sends no plan (`acp/spec.py:3967–3969`); a completed plan goes only with a COMPLETED run (`:4019–4028`). An EDIT that fails after approval was preceded by the pending plan sent for approval. | Not stated. Added to §4B.5 for the EDIT turn only. |
| 8 | §4B.5 pass-through citation `acp/spec.py:2121–2122` | LLD v2.48. | `_completion_message`, `acp/spec.py:4141–4142`. | Citation stale, updated. Other §4B citations keep the section's stated pin `57e2069`. |
| 9 | §4B.6: completion text carries the code into conversation history | LLD v2.48. | The text still ends with `(<code>)`; a history record shortened to fit its storage can lose it (`agent/edits.py:67–69`). | Correct, with that limit; §4B.6 is not changed by this edition. |
| 10 | §4B.7: a mixed-ending WRITE ends `end_turn` | LLD v2.48. | `acp/spec.py:4295`. | Already correct. |

No live run, GUI run or local full suite is part of this record.
