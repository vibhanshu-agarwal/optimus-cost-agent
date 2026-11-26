# Optimus - Low-Level Design

**Version 2.50 — #512 Agent-mode answer settlement, 2026-11-27.**

Predecessor: Optimus-Cost-Agent-LLD-v2.49.pdf; SHA-256 3a8c05bd37e0be1dd787725fa49ad5aa09a692968a66b66548e49a6d3fac3a24. Retain the predecessor byte-for-byte in `docs/archive/`.

**Edition scope.** Only §4B.1, §13.11.1 and §13.11.3 change. At main `72d2349`, the multi-turn planner grammar has an `ANSWER:` form. An Agent-mode answer settles as a completed run with `runStopReason` `PLANNING_ANSWERED`, its terminal message is the answer with no plan update, and loop control treats a waiting answer as it treats a waiting refusal. All other content is carried from v2.49 unchanged, with its own stated pins and qualifications.

**Evidence boundary.** The changed statements were checked against the code at `72d2349`; Codex authored the edits through its CLI and reviewed the built edition. No live run is claimed. HLD v2.26, built from the same bundle, corrects HLD §14.8, which named only a refusal settled after the nudge.

**Authority.** Issue #512 and PR #657, under the operator's decision 1 (2026-11-26: "Yes, completed") and the operator's request for this successor (2026-11-26: "update the LLD successor after the merge"). Publication to main follows the operator's instruction to open and merge this successor's PR.
