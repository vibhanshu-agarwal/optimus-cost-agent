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

### Closed rename record

**State:** Complete on 2026-07-31. The operator selected `evidence_handoff` as the canonical Python
package stem, normalized to the `evidence-handoff` distribution name, and selected
`EVIDENCE-HANDOFF-` as the Feature-ID prefix. Claude reviewed the pair against the frozen
constraints. The existing `FEATURE_ID_BODY` grammar accepted all four final identities unchanged.

The retired tokens below are preserved only as historical provenance. They are not live package
names, live Feature IDs, or owned feature rows:

- Package stem: `optimus_evidence` → `evidence_handoff`.
- Feature-ID prefix: `P11-` → `EVIDENCE-HANDOFF-`.
- `P11-FEAT-REDACTION-GATE` → `EVIDENCE-HANDOFF-FEAT-REDACTION-GATE`.
- `P11-FEAT-EVIDENCE-COLLECTOR` → `EVIDENCE-HANDOFF-FEAT-EVIDENCE-COLLECTOR`.
- `P11-FEAT-A2A-LEDGER` → `EVIDENCE-HANDOFF-FEAT-A2A-LEDGER`.
- `P11-FEAT-APPROVAL-RECORD` → `EVIDENCE-HANDOFF-FEAT-APPROVAL-RECORD`.

The package choice keeps the package and permanent `evidence-handoff-*` document namespace
coherent; path- or artifact-aware greps distinguish them when needed. Case-sensitive searches keep
the `EVIDENCE-HANDOFF-` identities distinct. PyPI's official JSON endpoint returned HTTP 404 for
`evidence-handoff` on 2026-07-31; that point-in-time result is not a reservation and must be
rechecked before publication.

The extraction constraints remain binding:

- Package, module, configuration, schema, artifact, and CLI names are descriptive, brand-free, and
  scheduling-number-free.
- `evidence_handoff` must not import `optimus`, `optimus_gateway`, their subpackages, Optimus launch
  types, Gateway service types, or `tools`; Optimus-specific adaptation remains in the host
  package.
- `evidence_handoff` may consume `optimus_security`, but must not fork its shared security
  primitives or create another redaction-rule engine.
- Product-owned document basenames use `evidence-handoff-*.md`; the two former legacy exceptions
  were renamed together by the mechanical rename.

Execution evidence:

- Naming decision commit: `2043359bc79db044e36775efe6571f963d229f58`.
- Two-commit protocol commit: `8092f1decc1bb7c3df216cbc10fc6c4ef26ce481`.
- Rename commit: `4f7cfeb8d8c4210b31f031385917588ed0687ccf`.
- Renamed design:
  `docs/superpowers/specs/evidence-handoff-redaction-gate-design.md`, committed-blob SHA-256
  `ee07b88186db65d6f0c109d2341147c066df8846fb4de7f80a86bb7b9f296ddb`.
- The commit containing this closed record is the frozen-baseline refresh commit. The renamed
  implementation plan pins the rename commit, design path, and design digest above. Its own final
  digest is verification evidence rather than an in-repository pin, so the sequence terminates
  here without a third metadata-only commit.

## Product-owned documents temporarily hosted in Optimus

These documents travel with this product during eventual extraction. They are the complete
allowlist for relative links from this pool into the current repository:

- `docs/superpowers/specs/evidence-handoff-redaction-gate-design.md`
- `docs/superpowers/specs/evidence-handoff-evidence-collector-design.md`
- `docs/superpowers/specs/evidence-handoff-zed-render-observation-design.md`
- `docs/superpowers/specs/evidence-handoff-a2a-ledger-design.md`
- `docs/superpowers/plans/evidence-handoff-risk-bearing-slice-implementation.md`
- `docs/superpowers/plans/evidence-handoff-redaction-gate-implementation.md`
- `docs/superpowers/plans/evidence-handoff-evidence-collector-implementation.md`

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
| `EVIDENCE-HANDOFF-FEAT-ZED-RENDER-OBSERVATION` | **Design review** 2026-08-01; direction ratified, unscheduled, and blocked on real same-session Zed custody from `P11-FEAT-ZED-RESUME` plus a production-equivalent cooperative receipt feasibility result. No scheduling number is reserved. [Design](../specs/evidence-handoff-zed-render-observation-design.md). | Add a fail-closed producer for the collector's existing render-observation contract. Authority comes from a Zed receipt bound to the exact ACP session, assistant message, content digest, visible viewport, and successful frame presentation; capture or deterministic text recognition is corroboration only. A locally patched Zed build is investigation evidence, not sufficient evidence for a determinate collector outcome. The design explicitly records the approved exception that a future implementation adds `observe-render` to the collector's seven-stage surface, making eight stages without adding a second entry point or an implicit redaction route. |
| `EVIDENCE-HANDOFF-FEAT-REDACTION-GATE` | **Closed** 2026-07-31 on branch `agent/cursor/evidence-handoff-redaction-gate` (from `origin/main` `2b58177b24a06c93e8e14760b85e25341e641178`). Implementation commits `2f5e4b8`…`eb5f5d8` (Tasks 0–8) and this Task 9 closing commit (gate-hardening, living-docs, repository gates). [Implementation plan](evidence-handoff-redaction-gate-implementation.md). Live ACP stream digest `1f848bcf9dca29ade5aedfb7838f0e4e3366044f8faeb3a2a59f766a713bd3e9`. Unblocks sanitized evidence for `P11-FEAT-ZED-RESUME`. | Type-dispatched, fail-closed artifact gate: parse/sanitize/reserialize JSON and NDJSON; stream-sanitize logs and notes; strip screenshot metadata and require human approval; quarantine dumps and retain hashes only. Redact API keys and PII using exact runtime-known-secret matching plus pattern/entropy detection and path canonicalization. Preserve session/run IDs, model/provider names, and git SHAs. [Design](../specs/evidence-handoff-redaction-gate-design.md). |
| `EVIDENCE-HANDOFF-FEAT-EVIDENCE-COLLECTOR` | **Promoted** 2026-07-31 on branch `agent/cursor/evidence-handoff-evidence-collector` (from `origin/main` `398a6cf334938972d7df672914d98ac5fa54952c`). Tasks 0–12 closed and independently reviewed on tip `c6c9b46`. Task 9 partially proven (`indeterminate` and `client_crashed` real; `rendered_then_crashed` / `rendered_stable` blocked on unscoped render-observation production). Task 13 repository gates and docs freshness audit run; feature remains open (not Closed); no merge predicted. [Implementation plan](evidence-handoff-evidence-collector-implementation.md). | One `tools/evidence_gather.py` entry point with subcommands, declarative scenarios, composable collectors/detectors, and the redaction gate as a separately invocable final stage. Outcomes are `rendered_stable`, `rendered_then_crashed`, `client_crashed`, or `indeterminate`; no hardcoded model literals or default report targets. Zed prompt-injection capability remains structurally absent: Tasks 10–12 recorded same-task investigation results (UIA/SendInput unsupported; `zed://` unsupported; hermetic `--user-data-dir` supported) without authorizing a usable injection adapter. [Design](../specs/evidence-handoff-evidence-collector-design.md). [Implementation plan](evidence-handoff-evidence-collector-implementation.md). |
| `EVIDENCE-HANDOFF-FEAT-A2A-LEDGER` | **Promoted** 2026-08-08 to the ordered risk-bearing vertical slice; no scheduling number is reserved. The cross-agent reachability blocker is resolved: Claude Code, Codex, and Cursor each reached the same loopback Docker-hosted Redis service and the host's LAN-bound test service from the host network namespace. [Design](../specs/evidence-handoff-a2a-ledger-design.md). [Implementation plan](evidence-handoff-risk-bearing-slice-implementation.md). | Default-off, opt-in append-only handoff protocol—not a transcript archive—with question, answer, evidence-notice, review-ruling, handoff, and separate acknowledgement entries; large payloads use SHA-256 references. A product-owned MCP Streamable HTTP service fronts loopback PostgreSQL; the store ladder is wslc, Docker, then native Windows. The product-owned lifecycle manager holds infrastructure privilege. Server-mapped asserted agent identity, role-derived authority, ingress redaction, transactional sequence ordering, durable reader-confirmed cursors, per-agent delivery facts, and structural approval-gate exclusion are load-bearing. Wakeup and network-callable evidence collection are v1 non-goals. |
| `EVIDENCE-HANDOFF-FEAT-APPROVAL-RECORD` | Design-needed, investigation only; ratified and unscheduled. Independent of the approved redaction-gate design and implementation plan, and blocks neither. The eventual plan number is assigned at pickup; no number is reserved by this row. | Generalize the redaction gate's digest-bound screenshot approval record into an operator Approval/Denial Record for exact artifacts. This is a convenience audit trail, explicitly **not** a security control, authorization mechanism, or cryptographic proof: it records the artifact digest, decision, timestamp, and asserted identity, including denials as well as approvals. The implementing agent never produces the record and only references one by digest; impose no interactive unlock or key management in its path. Voice is out of scope. The record may reserve an optional, unused signature field so future asymmetric signing is additive, but the artifact itself must not be called a signature. `authority=operator-relay` in the A2A ledger remains asserted, not cryptographically proven. |
