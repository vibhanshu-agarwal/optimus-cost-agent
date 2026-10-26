# Plan 12.4 Auto-mode pilot: evidence

This bundle holds the content-free evidence for the Plan 12.4 pilot, which chose Auto mode's per-turn judge. The pilot
ran under Plan 12.4 v8 Design 3 on 2026-10-26, with a decision rule fixed before any run. The operator accepted its
result, arm H, in [ADR-027](../../decisions/ADR-027-accepts-adr-007-auto-judge-h.md) (source S13).

**No prompt text is filed here.** The labelled requests stay in the local review kit beside the worktrees
(`optimus-handoff\sandbox-review-kit\plan12-4-auto\task3\`).

## Files

| File | What it is |
|---|---|
| [evidence-report.md](evidence-report.md) | The evidence report: arms, data, separation, pooled results, errors, robustness, the exploratory combinations, limitations, spend, deviations and the conditions before Auto ships |
| [evidence-tables.md](evidence-tables.md) | Every view's full metrics table, rendered from `evidence.json` |
| [extra-facts.txt](extra-facts.txt) | Confusion matrices, H against B, the 2× and 5× sensitivity, and the hybrid's rule share |
| [combo-explore.txt](combo-explore.txt) | The exploratory Jev + DSPy combinations, computed after the test from existing rows; not deciding |
| [frozen.json](frozen.json) | The settings frozen on the tuning items before any test call. Filed with LF line endings, SHA-256 `0489f3e4e06c9503706255f6768961a28ed1e36ef05fb565030e7ad13696d29e`; the review kit's original has CRLF endings, SHA-256 `0a16c2ef0ddd44484799bf5e38d2ce6791395ec0167b3b7747b7e3ef8c81b80a`. Same JSON |

## Kept in the review kit, pinned by SHA-256

These files carry a digest per item, which trips the local secret scan, so they stay in the review kit
(`task3\runs\test-1\`), as in the 2026-10-05 filing precedent:
- `manifest.jsonl`: 300 entries. Each holds the item's digest, source, source version and licence, provenance,
  split, group, modifications, both raters' labels and, for the 150 test items, every arm's three final tiers and its
  first repeat's other metric inputs. SHA-256 `076143fc9ff8c6a84b346c6ea457b5a5aa450b7f9e7c93ec49c744453a830534`.
- `evidence.json`: every view's metrics and rule outcome, plus the identities of the frozen settings, the DSPy
  program, the harness, the pilot environment and the registry compositions. SHA-256
  `b407516c317efecb66f4bf7c873198e5e716ee1fba1805af553cdda36cf50b75`.

## Review

Codex CLI round 62 (gpt-6.1-sol, high) recomputed every metric, winner and interval independently and recommended
accepting H, with conditions now applied. It is posted verbatim on #395 (comment 6414706221).
