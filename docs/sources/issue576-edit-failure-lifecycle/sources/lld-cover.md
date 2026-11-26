# Optimus - Low-Level Design

**Version 2.49 — #576 EDIT failure lifecycle, 2026-11-26.**

Predecessor: Optimus-Cost-Agent-LLD-v2.48.pdf; SHA-256 620ee455216572e71c28ae7923c12ccc7673659089bae01a0199e807cd44644f. Retain the predecessor byte-for-byte in `docs/archive/`.

**Edition scope.** Only §4B.5 changes. At main `31c6de5`, a turn whose EDIT cannot be applied ends with wire `stopReason` `end_turn` and `_meta.outcome` `failed` (unless a cancel was accepted first), never sends the stopped run's text as a plan, and shows one fixed message per code that ends with the code in brackets. All content outside §4B.5 is carried from v2.48 unchanged, with its own stated pins and qualifications.

**Evidence boundary.** The changed statements were checked against the code at `31c6de5` and reviewed through the Codex CLI. No live run is claimed. HLD v2.25 states none of the changed facts, so it has no successor.

**Authority.** Issue #576, filed with the operator's approval (Claude chat, 2026-11-24: "Yes, and file LLD issue"). Publication to main needs the operator's separate approval.
