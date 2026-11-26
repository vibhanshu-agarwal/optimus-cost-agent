# Optimus - Architecture (HLD)

**Version 2.26 — #512 Agent-mode answer settlement, 2026-11-27.**

Predecessor: Optimus-Cost-Agent-Architecture-v2.25.pdf; SHA-256 30f3992275ebf223de1f2c5217f8fff171795ba42765ccbdda655604d98638a6. Retain the predecessor byte-for-byte in `docs/archive/`.

**Edition scope.** Only §14.8 changes. At main `72d2349`, the planner can settle a question with an answer, and in an interactive Auto recovery episode an answer settled after the nudge is treated as a refusal settled after the nudge. All other content is carried from v2.25 unchanged, with its own stated pins and qualifications.

**Evidence boundary.** The changed statement was checked against the code at `72d2349`; Codex authored the edit through its CLI and reviewed the built edition. No live run is claimed. LLD v2.50 carries the detail.

**Authority.** Issue #512 and PR #657, under the operator's decision 1 (2026-11-26: "Yes, completed") and the operator's request for this successor (2026-11-27: "build the HLD successor too"). Publication to main follows the operator's instruction to open and merge this successor's PR.
