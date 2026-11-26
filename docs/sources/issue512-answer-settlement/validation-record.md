# #512 HLD v2.26 and LLD v2.50 validation

This is a dated evidence record, not the work register: [#512](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/512) owns review and completion. Built 2026-11-27 on Windows from main `72d2349bba987df419ac69a23694ff1766dee12f` (PR #657 merged).

## Identities

| Item | SHA-256 |
|---|---|
| `docs/Optimus-Cost-Agent-Architecture-v2.26.pdf` (29 pages) | `cb75f9d46613d91dc1fc6501bd651d99779ae2881307f77b44215ea1a5bcd9a6` |
| `docs/Optimus-Cost-Agent-LLD-v2.50.pdf` (64 pages) | `260ec305a2e7218085f91a42985731ffa7c5280a19bd3cef7a7f07ed0bfa5c75` |
| Predecessor `Optimus-Cost-Agent-Architecture-v2.25.pdf` (moved to `docs/archive/` unchanged) | `30f3992275ebf223de1f2c5217f8fff171795ba42765ccbdda655604d98638a6` |
| Predecessor `Optimus-Cost-Agent-LLD-v2.49.pdf` (moved to `docs/archive/` unchanged) | `3a8c05bd37e0be1dd787725fa49ad5aa09a692968a66b66548e49a6d3fac3a24` |
| `sources/edits.json` | `72c3cece07b45ad90300c9473c9b78dbe99b31a921265fd677981e302e3a7948` |
| `sources/page-updates.json` | `0b7c409e55c63d6a1a5a9e182a98b2e74c3d1479e18695d902edd8e992e53d7d` |
| `sources/hld-cover.md` | `47f7a66baa068bbd1e56d0dfeeefcdf4e1f08264935a0950727b32795fb59034` |
| `sources/lld-cover.md` | `870a41d206df30ad4f25fb65158162fd91bf045e0bb5624d89f9c990f7566f8d` |
| `sources/hld-14-context-engine.md` (edited) | `9f6029e296178f617efa97835c74ecccae04cd68b2a2cab9fb8fdbec1f1a0db4` |
| `sources/lld-13-context-integration.md` (edited) | `dd6d3112a69dffc309be39841dda2a0e685ab3c5dcaf998a53d32d733ebcf794` |
| `sources/hld-15-capability-status.md` (equal to #361's) | `023aa0619d3d5e3801856a37c804aa692c05be89fe10044c68fcb1fcca1ca7f3` |
| `sources/lld-14-capability-status.md` (equal to #576's) | `352dc4374cda2bf89f2c61edce9d0ae36d934556553d5c28d8c8b834ae6e4fc1` |

Toolchain: Python 3.14, ReportLab 5.0.0, pypdf 6.10.2, Windows Arial fonts; Poppler for text extraction and page images.

## Checks

| Check | Result |
|---|---|
| Predecessor reproduced first: the filed #576 `derive_sources.py` and `build_successor.py` at `72d2349` | 3 sources and 2 edits verified; LLD v2.49 rebuilt byte for byte (`3a8c05bd…`). HLD v2.25's page map is read from the filed #361 `build-manifest.json`, whose HLD digest equals the archived v2.25. |
| `derive_sources.py` (this bundle) | 5 sources and 4 exact edits verified against the filed sources |
| `build_successor.py`, run twice into separate folders | Same PDF bytes both times (`cb75f9d4…`, `260ec305…`); the same page counts and baseline mapping as the predecessors (29 and 64) |
| Filed `validate_corrections.py` | `document-validation.json` status PASS for both documents, no failures: manifest hash, page count, contiguous pages, baseline hash, every baseline page once, carried bodies equal to the baseline (HLD 1, LLD 17), predecessor hash, every predecessor page mapped, label and footer on every page, no escape artifacts |
| Rendered pages read | Both covers, LLD pages 21 and 22 (§4B.1, baseline page 19), LLD pages 53 and 54 (§13.11) and HLD page 21 (§14.8): text extracted and read; LLD pages 1, 21 and 22 and HLD page 21 also rendered at 60 dpi and read. No clipping, overprinting or broken table. |
| Codex CLI review of the built editions (gpt-6.2-sol, high; posted on #512) | Two Medium and two Low findings. All four were taken up: this record and the binding test are filed; §4B.1 now states the bare-CR fence limit and the conditions on delivery and on the checkpoint; the README says the validator's result is its JSON `status`. Both editions were rebuilt and rechecked afterwards. |

## Comparison with main

Source paths under `src/optimus/`, line numbers at `72d2349`.

| # | Item | What the documents said | What main does | Verdict |
|---|---|---|---|---|
| 1 | Multi-turn planner prompt version | LLD v2.49 §4B.1: `MULTI_TURN_PLANNER_PROMPT_VERSION:2026-10-24-p407-edit-p410-write-line-endings`. HLD: not stated. | `MULTI_TURN_PLANNER_PROMPT_VERSION:2026-11-26-p512-answer` (`agent/prompts.py:14`). | LLD stale, corrected. |
| 2 | The `ANSWER:` form and how an answer settles | Not stated in either. | The grammar's ANSWER form (`agent/prompts.py:119–122`), the parser (`agent/planning_loop.py:104`, `:961–988`), the settlement (`agent/runner.py:171–176`), the ACP delivery and `_meta` (`acp/spec.py:3972–3974`, `:4024–4057`, `:4144–4146`, `:4286–4316`), and the checkpoint (`acp/spec.py:3052–3058`; `context/memory_continuity.py:150–158`). | Not stated. Added to LLD §4B.1, with the conditions on delivery and on the checkpoint, and the bare-CR fence limit. |
| 3 | Escalation and check-in with a waiting reply | LLD v2.49 §13.11.1 and §13.11.3, HLD v2.25 §14.8: a refusal only. | `_MODEL_REPLIES` (`agent/planning_loop.py:119–120`), used by `next_recovery_move`, `record_checkin`, `record_escalation` and `end_episode`, with the answer's own check-in text (`:1584–1618`, `:1640–1655`, `:1696–1705`). | Incomplete, corrected in both. |
| 4 | Indexed planner prompt version | Not stated in either. | `INDEXED_PLANNER_PROMPT_VERSION:2026-11-26-p512-answer`. | Not stated; nothing to correct. |
| 5 | D7 planning-material figures (46581, 182795) | Not stated in either. | 46838 and 182538, pinned in `tests/unit/context_engine/test_limits.py`. | Not stated; nothing to correct. |
| 6 | A genuine refusal's settlement | LLD v2.49 states none for planning refusals. | Unchanged: `PLANNING_MODEL_REFUSED`, FAILED (`agent/runner.py:171–176`). | Not stated; nothing to correct. |

No live run, GUI run or local full suite is part of this record. The live Zed check of an Agent-mode answer follows the merge.
