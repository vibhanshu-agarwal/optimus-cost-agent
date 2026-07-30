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

### Step 0 — Package-name and Feature-ID decision

**State:** Decided on 2026-07-31. The operator selected `evidence_handoff` as the canonical package
stem and `EVIDENCE-HANDOFF-` as the Feature-ID prefix. Claude reviewed the pair against the frozen
constraints and verified that all four resulting identities satisfy the existing
`FEATURE_ID_BODY` grammar without a regex change. Step 0 has exited; the mechanical rename has not
started.

The decision covers exactly two tokens:

1. The canonical distribution/package stem `evidence_handoff`, which replaces the provisional
   `optimus_evidence`.
   Python packaging mechanically renders an underscore import name as the corresponding normalized
   hyphenated distribution name; those two spellings are one decision, not separate tokens.
2. The Feature-ID prefix `EVIDENCE-HANDOFF-`, which replaces the provisional `P11-`.

Every candidate must be descriptive of evidence, redaction, or handoff behavior, brand-free, and
free of feature identities and scheduling numbers. The package is intended for extraction into a
standalone product: it must not import `optimus`, `optimus_gateway`, their subpackages, Optimus
launch types, or Gateway service types. Optimus-specific adaptation remains in the host package.
The package may consume `optimus_security`, but it must not fork the shared security primitives or
create another redaction-rule engine.

Package-stem candidates:

| Candidate | Normalized distribution name | Rationale and trade-off |
|---|---|---|
| `evidence_handoff` | `evidence-handoff` | Matches the established product-document namespace and directly describes the broader evidence-transfer boundary. It keeps redaction as an explicit subsystem rather than implying that handoff alone makes content safe. The shared `evidence-handoff` stem also means broad greps match both package and document names, so searches must distinguish paths or artifact kinds. This is Codex's recommendation for operator consideration. |
| `evidence_custody` | `evidence-custody` | Emphasizes private capture, hashing, quarantine, approval, and controlled promotion. It describes the safety lifecycle well, but makes the inter-agent handoff purpose less obvious. |
| `evidence_exchange` | `evidence-exchange` | Emphasizes portable evidence transfer across hosts and agents. It makes handoff intent clear, but says less about the fail-closed redaction and custody boundary. |

The namespace trade-off is symmetric: `evidence_handoff` keeps the package and the permanently
established `evidence-handoff-*` document namespace coherent but requires path- or artifact-aware
greps. Either alternative makes unfiltered package-name greps more selective but permanently gives
the package and its product-owned documents different names.

PyPI's official JSON endpoints returned HTTP 404 for all three normalized distribution names on
2026-07-31, so none was registered at the time of this check. This point-in-time result is not a
name reservation and must be rechecked before publication.

Feature-ID-prefix candidates:

| Candidate | Example resulting identity | Rationale and trade-off |
|---|---|---|
| `EVIDENCE-HANDOFF-` | `EVIDENCE-HANDOFF-FEAT-REDACTION-GATE` | Fully descriptive, brand-free, and unambiguous in cross-product references. It is longer than the alternatives, but Feature IDs are planning and custody tokens rather than runtime names. This is Codex's recommendation for operator consideration. |
| `EVIDENCE-` | `EVIDENCE-FEAT-REDACTION-GATE` | Shorter while remaining self-descriptive and brand-free. It does not distinguish this product's handoff scope from other evidence features. |
| `EH-` | `EH-FEAT-REDACTION-GATE` | Compact and aligned with “evidence and handoff” once defined. The acronym is less self-explanatory and more collision-prone outside this pool. |

Until Step 1 applies the recorded decision, `optimus_evidence` and the four `P11-` identities below
remain the current provisional repository tokens. No naming question remains open.

### Step 1 — Mechanical rename

**State:** Unblocked; not started. Execute from the clean committed branch tip that contains this
protocol and descends from the approved decision commit
`2043359bc79db044e36775efe6571f963d229f58`. That decision commit is an ancestry floor, not a
checkout or reset target. Deliver the reviewed mechanical change in exactly two commits before
`P11-FEAT-REDACTION-GATE` Task 2. Keep both commits in the same branch and pull request, and do not
begin the Evidence Collector design between them. The change must include all of the following;
none is an optional cleanup.

The mechanical replacements apply only to live identifier, package, document-path, and dependency
usages. Do not token-swap the Step 0 decision record or these Step 1 instructions in place. When
Step 1 completes in the second commit, rewrite this naming section as a closed historical record:
preserve the explicit old-to-new token decision, remove transitional pre-execution statements,
mark Step 1 complete, and cite the first commit plus the re-frozen design digest. Retained old
tokens in that closed record are historical provenance, not live references.

Mandatory commit sequence:

1. **Rename commit.** Starting from that clean committed branch tip, perform every live token
   replacement, both document renames, the stale-pointer correction, the Optimus-owned
   dependency-pointer update, and the required test updates below, except for the implementation
   plan's frozen-baseline commit, path, and digest pins and its executable baseline checks. Those
   values are intentionally reserved for the second commit because the rename commit does not
   exist yet. Run the applicable rename, hygiene, Ruff, and diff gates and create no red
   intermediate commit. This commit establishes the authoritative renamed design blob. Record its
   commit SHA as `<rename-commit>`; do not guess it in advance and do not claim that the
   implementation plan's frozen-baseline block is current yet.
2. **Frozen-baseline refresh commit.** Compute the renamed design digest from:

   ```bash
   git show <rename-commit>:docs/superpowers/specs/evidence-handoff-redaction-gate-design.md | sha256sum
   ```

   In the renamed implementation plan, update the frozen-baseline commit pin to
   `<rename-commit>`, update its design path and SHA-256, and update the executable `git show`
   command to use that exact commit and path. Replace the obsolete ancestry check with
   `git merge-base --is-ancestor <rename-commit> HEAD`. Rewrite this naming section as the closed
   historical record described above, rerun the gates, and commit the refresh. The implementation
   plan's own digest is pinned nowhere in the repository, so this second commit terminates the
   sequence; do not create a third metadata-only commit.

- Rename all four product-owned Feature IDs and their live references atomically:
  `P11-FEAT-REDACTION-GATE`, `P11-FEAT-EVIDENCE-COLLECTOR`, `P11-FEAT-A2A-LEDGER`, and
  `P11-FEAT-APPROVAL-RECORD`. Update both hardcoded sites in
  `tests/unit/docs/test_open_work_pool_hygiene.py`: the `PRODUCT_FEATURE_IDS` set and the separate
  exact `dependency_ids` assertion for `P11-FEAT-REDACTION-GATE`. The existing `FEATURE_ID_BODY`
  grammar already accepts the selected prefix and must not change as part of this rename.
- Update the single product Feature-ID dependency reference in the Optimus-owned
  `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`. Preserve it as a
  pointer to this product pool and do not add live state or status language; the hygiene test
  enforces both constraints.
- Rename the live provisional `optimus_evidence` package usages to the chosen package token without
  changing the frozen extraction boundary or dependency direction. The token currently appears
  outside this naming section in both frozen redaction documents.
- Rename the two digest-bound document paths atomically to
  `docs/superpowers/specs/evidence-handoff-redaction-gate-design.md` and
  `docs/superpowers/plans/evidence-handoff-redaction-gate-implementation.md`. Update every link,
  command, and path allowlist entry, including `PRODUCT_OWNED_DOCS` in the hygiene test, in the
  same change.
- Re-freeze both digest-bound documents from committed Git blobs, never from the working tree;
  CRLF/LF conversion makes working-tree hashes untrustworthy. The second commit pins the design's
  first-commit SHA and digest in the implementation plan. After the second commit, compute the
  final implementation-plan digest with:

  ```bash
  git show HEAD:docs/superpowers/plans/evidence-handoff-redaction-gate-implementation.md | sha256sum
  ```

  Report that digest as verification evidence; it has no in-repository pin.
- After renaming the design to
  `docs/superpowers/specs/evidence-handoff-redaction-gate-design.md`, fix its stale live-state
  pointer: it must point to `docs/superpowers/plans/evidence-handoff-open-work-pool.md`, not the
  consolidated Optimus backlog. This is a pointer correction only; custody is already clean.

New product-owned document basenames start with `evidence-handoff-` and use a descriptive,
brand-free, scheduling-number-free remainder: `evidence-handoff-*.md`. This keeps eventual
extraction glob-based. The two digest-bound documents listed below are temporary legacy-name
exceptions until Step 1 completes: no separate change may rename either one. Step 1 removes the
exception by renaming both documents together to the explicit target paths above.

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
