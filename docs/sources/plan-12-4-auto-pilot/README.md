# Plan 12.4 Auto-mode pilot: evidence

This bundle holds the content-free evidence for the Plan 12.4 pilot, which chose Auto mode's per-turn judge. The pilot
ran under Plan 12.4 v8 Design 3 on 2026-10-26, with a decision rule fixed before any run. The operator accepted its
result, arm H, in [ADR-028](../../decisions/ADR-028-accepts-adr-007-auto-judge-h.md) (source S13).

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
| [manifest.ndjson](manifest.ndjson) | The per-item manifest (newline-delimited JSON; `.jsonl` is ignored here as runtime data), 300 entries, keyed by pilot item ID. Each entry holds the source, source version and licence, provenance, split, group (as an index), modifications, both raters' labels and the merged label. For the 150 test items it also holds every arm's three final tiers and its first repeat's tier, confidence, route-up flag, latency and billed cost |
| [tools/recompute.py](tools/recompute.py) | Recomputes every view's outcome and metrics from `manifest.ndjson` alone, with `tools/metrics.py` |
| [tools/metrics.py](tools/metrics.py) | The pilot's metrics and pre-registered rule. The only change is the single-letter variable `l` renamed for this repository's lint |

## The manifest: option (ii), approved by the operator on 2026-10-26

- **The kit's original** keys each item by the SHA-256 digest of its private prompt. Those digests trip the local
  secret scan, and they are useful only to someone who holds the private prompts, which stay in the kit.
- **So the filed manifest replaces each digest with the item's pilot ID** (for example `ar-042`), and each group with
  a plain index. Every other field is unchanged.
- **The check:** `tools/recompute.py` reproduces every view, winner, reason, metric and interval in `evidence.json`
  exactly (checked 2026-10-26; 6 views, 0 mismatches).
- **Kept in the review kit** (`task3\runs\test-1\`), pinned by SHA-256:
  - the original `manifest.jsonl`: `076143fc9ff8c6a84b346c6ea457b5a5aa450b7f9e7c93ec49c744453a830534`;
  - `evidence.json`: `b407516c317efecb66f4bf7c873198e5e716ee1fba1805af553cdda36cf50b75`.
- **The identities recorded in `evidence.json`:**
  - the frozen settings: `0a16c2ef0ddd44484799bf5e38d2ce6791395ec0167b3b7747b7e3ef8c81b80a`;
  - D's frozen program: `d9ec7a21ea1719b410d24de1909a359105c50dd99694a3c77a15988d52e9356b`;
  - the original `metrics.py`: `bbf0b4d214f64e159075c264b5fee97a6016c933e39fb5b09cd8c44e74edd129`;
  - the pilot environment's lock: `bc98d16d3a6ce531b51523cc04929d712589fa6809cc65fcee860a93fff94b8b`;
  - `evaluation` `d8d0b90e…`; `auto` prices at `bece741e…`, unchanged at `b93d67ec…` and `f11dc3ab…`.

## Review

Codex CLI round 62 (gpt-6.1-sol, high) recomputed every metric, winner and interval independently and recommended
accepting H, with conditions. It is posted verbatim on #395 (comment 6414706221).
- **Applied:** the documentary corrections (wording, separation, accounting, identities and the acceptance record).
- **Still pending:**
  - the production conditions, which Phase B owns: confidence validation, classifier-failure handling and the live
    slices.

**The `auto` hash:** the operator approved `f11dc3ab…` (defaults plus the Auto overlay, no override) on 2026-10-26,
after Codex round 63 accepted the composition.
