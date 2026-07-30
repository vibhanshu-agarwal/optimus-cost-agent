# Evidence and Handoff Open Work Pool

## Purpose

This document is the single source of truth for the evidence and handoff product's open work. It
owns each item's existence and state; product-owned designs and implementation plans own detailed
scope and acceptance criteria. Anything not listed here is not tracked as open work for this
product.

The pool remains the custody record while work is unscheduled. Other products may link here by
Feature ID, but must not duplicate a moved item's live state or status.

## How to use this document

- **Adding an item:** Record it here first with a unique Feature ID, state, and scope detail. Other
  documents may reference the Feature ID, but this pool remains the sole owner of live status.
- **Promoting an item:** When an item is scheduled, mark it `Promoted`, add the pickup date and a
  link to its implementation artifact, and retain the row as custody history.
- **Closing an item:** Mark it `Closed` with the implementation commit or merge reference and the
  evidence citation. Do not delete the historical row.

## Naming and extraction convention

The current `P11-` Feature-ID prefix is provisional. Rename it only as one reviewed mechanical
change bundled with the package-name decision, before `P11-FEAT-REDACTION-GATE` Task 2. Until then,
the four IDs below remain unique greppable tokens and must not appear as owned rows in another
open-work pool.

New product-owned document basenames start with `evidence-handoff-` and use a descriptive,
brand-free, scheduling-number-free remainder: `evidence-handoff-*.md`. This keeps eventual
extraction glob-based. The two digest-bound documents listed below are explicit legacy-name
exceptions and must not be renamed independently.

## Product-owned documents temporarily hosted in Optimus

These documents travel with this product during eventual extraction. They are the complete
allowlist for relative links from this pool into the current repository:

- `docs/superpowers/specs/2026-07-30-p11-feat-redaction-gate-design.md`
- `docs/superpowers/plans/2026-07-30-p11-feat-redaction-gate-implementation.md`

Adding a document to this list requires an explicit ownership decision. Documents that remain with
Optimus are referenced across the product boundary by Feature ID only, never by relative path.

## Reference rewrites during custody transfer

The source rows are preserved from commit `5511792` except for the approved extraction-safe
reference rewrites:

- The redaction gate's numbered Zed-resume owner reference became
  `P11-FEAT-ZED-RESUME`.
- The A2A ledger's numbered local-startup implementation reference became the durable architectural
  phrase "the consolidated local-startup configuration source of truth."
- The redaction-gate design link remains unchanged because the design is product-owned and appears
  in the explicit allowlist above.

## Feature slices

| Identity | State | Scope detail |
|---|---|---|
| `P11-FEAT-REDACTION-GATE` | **HIGH; ratified, unscheduled.** First slice in the future independent handoff/evidence train because it unblocks sanitized `P11-FEAT-ZED-RESUME` Task 0 evidence. The eventual plan number is assigned at pickup; no number is reserved by this row. | Type-dispatched, fail-closed artifact gate: parse/sanitize/reserialize JSON and NDJSON; stream-sanitize logs and notes; strip screenshot metadata and require human approval; quarantine dumps and retain hashes only. Redact API keys and PII using exact runtime-known-secret matching plus pattern/entropy detection and path canonicalization. Preserve session/run IDs, model/provider names, and git SHAs. [Design draft](../specs/2026-07-30-p11-feat-redaction-gate-design.md). |
| `P11-FEAT-EVIDENCE-COLLECTOR` | Ratified, unscheduled; sequenced after `P11-FEAT-REDACTION-GATE`. The eventual plan number is assigned at pickup; no number is reserved by this row. | One `tools/evidence_gather.py` entry point with subcommands, declarative scenarios, composable collectors/detectors, and the redaction gate as a separately invocable final stage. Outcomes are `rendered_stable`, `rendered_then_crashed`, `client_crashed`, or `indeterminate`; no hardcoded model literals or default report targets. Its Zed prompt-injection gate remains investigation-only until UIA/SendInput on Zed 1.13.1, the `zed://` scheme, and hermetic `--user-data-dir` instances produce evidence. |
| `P11-FEAT-A2A-LEDGER` | Ratified, unscheduled; sequenced after the redaction gate and evidence collector. **Blocked on the cross-agent localhost-TCP reachability investigation** for Claude Code, Cursor, and Codex. The eventual plan number is assigned at pickup; no number is reserved by this row. | Default-off, opt-in append-only handoff protocol—not a transcript archive—with question, answer, evidence-notice, review-ruling, handoff, and separate acknowledgement entries; large payloads use SHA-256 references. PostgreSQL in Docker is primary only if the reachability spike passes; otherwise use global SQLite under a non-cloud-synced `%LOCALAPPDATA%`-class path. Keep the store independent of Redis/general memory, preserve reviewer/implementer role separation, apply ingress redaction before every write, and place any eventual container configuration in the consolidated local-startup configuration source of truth. |
| `P11-FEAT-APPROVAL-RECORD` | Design-needed, investigation only; ratified and unscheduled. Independent of the approved redaction-gate design and implementation plan, and blocks neither. The eventual plan number is assigned at pickup; no number is reserved by this row. | Generalize the redaction gate's digest-bound screenshot approval record into an operator Approval/Denial Record for exact artifacts. This is a convenience audit trail, explicitly **not** a security control, authorization mechanism, or cryptographic proof: it records the artifact digest, decision, timestamp, and asserted identity, including denials as well as approvals. The implementing agent never produces the record and only references one by digest; impose no interactive unlock or key management in its path. Voice is out of scope. The record may reserve an optional, unused signature field so future asymmetric signing is additive, but the artifact itself must not be called a signature. `authority=operator-relay` in the A2A ledger remains asserted, not cryptographically proven. |
