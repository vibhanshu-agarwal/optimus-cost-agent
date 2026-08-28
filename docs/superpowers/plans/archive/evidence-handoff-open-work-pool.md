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
- `docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md`
- `docs/superpowers/plans/evidence-handoff-risk-bearing-slice-implementation.md`
- `docs/superpowers/plans/evidence-handoff-risk-bearing-slice-implementation_v2.md`
- `docs/superpowers/plans/evidence-handoff-redaction-gate-implementation.md`
- `docs/superpowers/plans/evidence-handoff-evidence-collector-implementation.md`
- `docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md`
- `docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v2.md`
- `docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v3.md`

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

| Identity | State | Priority | Scope detail |
|---|---|---|---|
| `EVIDENCE-HANDOFF-FEAT-ZED-RENDER-OBSERVATION` | **Design review** 2026-08-01; direction ratified, unscheduled, and blocked on real same-session Zed custody from `P11-FEAT-ZED-RESUME` plus a production-equivalent cooperative receipt feasibility result. No scheduling number is reserved. [Design](../../specs/evidence-handoff-zed-render-observation-design.md). | MEDIUM | Add a fail-closed producer for the collector's existing render-observation contract. Authority comes from a Zed receipt bound to the exact ACP session, assistant message, content digest, visible viewport, and successful frame presentation; capture or deterministic text recognition is corroboration only. A locally patched Zed build is investigation evidence, not sufficient evidence for a determinate collector outcome. The design explicitly records the approved exception that a future implementation adds `observe-render` to the collector's seven-stage surface, making eight stages without adding a second entry point or an implicit redaction route. |
| `EVIDENCE-HANDOFF-FEAT-REDACTION-GATE` | **Closed** 2026-07-31 on branch `agent/cursor/evidence-handoff-redaction-gate` (from `origin/main` `2b58177b24a06c93e8e14760b85e25341e641178`). Implementation commits `2f5e4b8`…`eb5f5d8` (Tasks 0–8) and this Task 9 closing commit (gate-hardening, living-docs, repository gates). [Implementation plan](evidence-handoff-redaction-gate-implementation.md). Live ACP stream digest `1f848bcf9dca29ade5aedfb7838f0e4e3366044f8faeb3a2a59f766a713bd3e9`. Unblocks sanitized evidence for `P11-FEAT-ZED-RESUME`. | MEDIUM | Type-dispatched, fail-closed artifact gate: parse/sanitize/reserialize JSON and NDJSON; stream-sanitize logs and notes; strip screenshot metadata and require human approval; quarantine dumps and retain hashes only. Redact API keys and PII using exact runtime-known-secret matching plus pattern/entropy detection and path canonicalization. Preserve session/run IDs, model/provider names, and git SHAs. [Design](../../specs/evidence-handoff-redaction-gate-design.md). |
| `EVIDENCE-HANDOFF-FEAT-EVIDENCE-COLLECTOR` | **Promoted** 2026-07-31 on branch `agent/cursor/evidence-handoff-evidence-collector` (from `origin/main` `398a6cf334938972d7df672914d98ac5fa54952c`). Tasks 0–12 closed and independently reviewed on tip `c6c9b46`. Task 9 partially proven (`indeterminate` and `client_crashed` real; `rendered_then_crashed` / `rendered_stable` blocked on unscoped render-observation production). Task 13 repository gates and docs freshness audit run; feature remains open (not Closed); no merge predicted. [Implementation plan](../evidence-handoff-evidence-collector-implementation.md). | MEDIUM | One `tools/evidence_gather.py` entry point with subcommands, declarative scenarios, composable collectors/detectors, and the redaction gate as a separately invocable final stage. Outcomes are `rendered_stable`, `rendered_then_crashed`, `client_crashed`, or `indeterminate`; no hardcoded model literals or default report targets. Zed prompt-injection capability remains structurally absent: Tasks 10–12 recorded same-task investigation results (UIA/SendInput unsupported; `zed://` unsupported; hermetic `--user-data-dir` supported) without authorizing a usable injection adapter. [Design](../../specs/evidence-handoff-evidence-collector-design.md). [Implementation plan](../evidence-handoff-evidence-collector-implementation.md). |
| `EVIDENCE-HANDOFF-FEAT-A2A-LEDGER` | **Not shipped / not supported / not trusted.** Independent audit at `e5f7e339` returned **NOT SOUND** (17 findings, 3 Critical). Corrected facts: the risk-bearing slice's tip is `658042d`, 25 inclusive commits from `8735885`, PR #128 merged `7b5865f`, PR #129 merged `74f7104` — code remains merged to `main` and the `evidence-handoff-lifecycle`/`evidence-handoff-service` console scripts remain installed. [Design](../../specs/evidence-handoff-a2a-ledger-design.md). No ordinary Optimus agent or gateway runtime import constructs or invokes any A2A ledger component, and lifecycle activation is default-off/opt-in. The feature is not on the ordinary Optimus runtime path and lifecycle activation is opt-in by default. However, merged code and installed console entry points remain manually callable. They are unsupported and untrusted and must not be enabled or used for trusted workflows. Full disposition, corrected scoping, and the six deferred remediation slices below: live [closure plan `_v3`](evidence-handoff-a2a-not-shipped-closure_v3.md) and the tracked [remediation-scoping contract](../../specs/evidence-handoff-a2a-ledger-remediation-scoping.md); historical [v1 plan](evidence-handoff-a2a-not-shipped-closure.md) and historical [`_v2`](evidence-handoff-a2a-not-shipped-closure_v2.md) preserve the prior review chronology and are not the execution target. Independent audit `docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md`; sealed reviewer findings `docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md`; scoping review chronology `docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md`; this closure review chronology `docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md`. | MEDIUM | Default-off, opt-in append-only handoff protocol—not a transcript archive—with question, answer, evidence-notice, review-ruling, handoff, and separate acknowledgement entries; large payloads use SHA-256 references. A product-owned MCP Streamable HTTP service fronts loopback PostgreSQL. The product-owned lifecycle manager holds infrastructure privilege and installation signing-key custody (OS keyring). Server-mapped asserted agent identity, role-derived authority, ingress redaction, transactional sequence ordering, durable reader-confirmed cursors, per-agent delivery facts, and structural approval-gate exclusion are load-bearing. Wakeup and network-callable evidence collection are v1 non-goals. Six deferred remediation slices own the audit's fixable findings: `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION`, `EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY`, `EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH`, `EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY`, `EVIDENCE-HANDOFF-FEAT-LEDGER-AUDIT-WIRING`, and `EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD`. This row does not close OAuth/rotation (`EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE`), at-rest integrity (`EVIDENCE-HANDOFF-FEAT-AT-REST-INTEGRITY`), peer-liveness (`EVIDENCE-HANDOFF-FEAT-PEER-LIVENESS-SIGNAL`), or the design refresh (`EVIDENCE-HANDOFF-FEAT-A2A-LEDGER-DESIGN-REFRESH`) — those keep their own open rows. |
| `EVIDENCE-HANDOFF-FEAT-A2A-LEDGER-DESIGN-REFRESH` | **Tracked, Not Yet Scheduled** 2026-08-10; non-blocking owner for an operator-directed architecture correction. Create `docs/superpowers/specs/evidence-handoff-a2a-ledger-design_v2.md` from the frozen design; do not edit or rename the frozen parent. This item does not block `evidence-handoff-risk-bearing-slice-implementation_v2.md`. | MEDIUM | Restate the local store ladder as Docker Desktop PostgreSQL (sole implemented/default rung) then native Windows PostgreSQL (deferred), with wslc removed. Preserve loopback-only bind, lifecycle-owned infrastructure privilege, MCP access layer, and explicit stopped-lifecycle selection/no runtime failover. The implementation plan retains a pluggable backend protocol/factory so native Windows later is a configuration choice plus adapter, not a lifecycle rewrite. **Task 6 live findings to fold into v2 (2026-08-10, not fixed mid-capstone):** (1) read-path verification only covers the unread range behind confirmed cursors (pairs with `EVIDENCE-HANDOFF-FEAT-AT-REST-INTEGRITY`); (2) Session protocol admission is Option A (operator ruling 2026-08-10, shipped): `SessionRegistry` accepts any version in the supported range rather than binding to the negotiated initialize-response version. The operation-entry integrity-guard finding (design line 493, `delivery.read_entries` issuing a delivery token on an empty unread page over a latched/broken chain) is now owned by `EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY` (audit finding C2), not this row. |
| `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | **Tracked, Not Yet Scheduled** 2026-08-12; independent-audit remediation owner for the risk-bearing slice's composition/runbook and credential-custody defects (audit findings C1, C3, H7, H9, M15; `docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md`). | MEDIUM | Ship a real production composition root and operator runbook joining lifecycle start, PostgreSQL migration, service construction, principal/credential issuance, and readiness into one exposed path instead of a hand-built test fixture (C1); fix the circular first-run signing-key bootstrap so the lifecycle-owned API can mint its own initial key without bypassing its own custody rule (C3); include the SQL migration directory in the built/installed wheel so an installed ledger can initialize its schema (H7); run the service under a least-privilege database role instead of the shared lifecycle/administrator credential (H9); and make lifecycle status/instance-file handling safe across process restarts and corrupted control metadata instead of silently generating a replacement UUID (M15). |
| `EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY` | **Tracked, Not Yet Scheduled** 2026-08-12; independent-audit remediation owner for integrity detection/latching not being wired into production plus two related integrity-boundary defects (audit findings C2, H13, M16c; `docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md`). | MEDIUM | Construct and wire `IntegrityMonitor` (or an equivalent) into the actual production service path so a detected corruption durably latches and stops append, read, delivery confirmation, cursor advance, and acknowledgement, and so restart/readiness correctly reflect an existing latch instead of reporting ready (C2); make linked-replacement full verification load replacement genesis metadata instead of hardcoding ordinary genesis, so a valid replacement instance doesn't fail its own full audit (H13); and restore the distinguished `INTEGRITY_FAILED` typed status instead of collapsing an integrity incident into ordinary `UNAVAILABLE` (M16c). |
| `EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH` | **Tracked, Not Yet Scheduled** 2026-08-12; independent-audit remediation owner for three read/write data-path defects (audit findings H4, H5, H6; `docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md`). | MEDIUM | Route `review_ruling_read` through the same recipient-visibility and latched-read guards as the normal read path instead of bypassing them via a caller-selected global sequence (H4); make mandatory redaction fail closed on any sanitizer result that isn't the expected `SanitizedDraft` type instead of defaulting an untyped result to success (H5); and make a normal read one coherent snapshot — status, cursor, and head witness from one consistent view — so a concurrent append can't mint a token whose witness disagrees with its own watermark (H6). |
| `EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY` | **Tracked, Not Yet Scheduled** 2026-08-12; independent-audit remediation owner for the service CLI's fail-open auth stub plus two related runtime-boundary defects (audit findings H8, M14, M16b; `docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md`). | MEDIUM | Require a real auth bundle, or explicitly refuse to start, instead of letting the public service CLI launch a stub that advertises the full tool surface and accepts any nonempty Bearer value (H8); make secret-bundle deletion and file-permission hardening fail closed instead of swallowing the failure and starting the server anyway (M14); and add the pre-parse rate/concurrency limiting the frozen design requires instead of enforcing only `max_body_bytes` (M16b). |
| `EVIDENCE-HANDOFF-FEAT-LEDGER-AUDIT-WIRING` | **Tracked, Not Yet Scheduled** 2026-08-12; independent-audit remediation owner for the missing production audit-recorder wiring (audit finding M16a; `docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md`). | MEDIUM | Construct and wire `AuditRecorder` (or an equivalent) into the transport, auth, session, delivery, and integrity call sites in the production service path — currently only a narrow principal-retirement DB event is recorded and the append call omits the optional audit argument entirely, so the frozen design's mandatory observability is not produced (M16a). |
| `EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD` | **Tracked, Not Yet Scheduled** 2026-08-12; independent-audit remediation owner for the slice's evidence/Definition-of-Done soundness gap (audit findings H10, H11, H12b; `docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md`). | MEDIUM | Replace the unsigned three-file assertion bundle with evidence that can actually establish cross-agent delivery and native-client participation — signed receipts, a raw transcript/DB export, or an equivalent verifiable record instead of internally-consistent but unauthenticated JSON (H10); fix the capstone verifier so it cannot pass without the frozen scenario's required `explicit_recipient_delivery_reaches_other_agents` outcome, a live service connection, and recipient/page binding, instead of trusting client-asserted labels (H11); and correct the specific DoD checkbox/evidence defects this slice's closure admitted — an unchecked acceptance-review step recorded as complete and a deselected/failing integration command marked `[x]` — leaving the broader plan-vs-CI gate-list reconciliation to the separate, unscheduled program-gate-contract pre-work (H12a) that this row does not own (H12b). |
| `EVIDENCE-HANDOFF-FEAT-APPROVAL-RECORD` | Design-needed, investigation only; ratified and unscheduled. Independent of the approved redaction-gate design and implementation plan, and blocks neither. The eventual plan number is assigned at pickup; no number is reserved by this row. | MEDIUM | Generalize the redaction gate's digest-bound screenshot approval record into an operator Approval/Denial Record for exact artifacts. This is a convenience audit trail, explicitly **not** a security control, authorization mechanism, or cryptographic proof: it records the artifact digest, decision, timestamp, and asserted identity, including denials as well as approvals. The implementing agent never produces the record and only references one by digest; impose no interactive unlock or key management in its path. Voice is out of scope. The record may reserve an optional, unused signature field so future asymmetric signing is additive, but the artifact itself must not be called a signature. `authority=operator-relay` in the A2A ledger remains asserted, not cryptographically proven. |
| `EVIDENCE-HANDOFF-FEAT-PEER-LIVENESS-SIGNAL` | Design-needed, investigation only; recorded and unscheduled. Independent of `EVIDENCE-HANDOFF-FEAT-A2A-LEDGER` (not shipped / not supported / not trusted) and blocks none of its six deferred remediation slices. The eventual plan number is assigned at pickup; no number is reserved by this row. | MEDIUM | Operator ask: can an agent detect that its A2A counterparty is down and raise its own alert? The frozen design's [Per-agent delivery observability](../../specs/evidence-handoff-a2a-ledger-design.md#per-agent-delivery-observability) deliberately does **not** provide this — it states "The view reports facts, not guessed process liveness. It must not label an agent online, dead, or healthy solely from cursor activity," because six distinct causes (between turns, context compaction, session errored, dead transcript, delayed-but-alive, broken MCP config) produce identical "no recent cursor advance" facts. Any authenticated `ledger.read`-scoped agent can already poll the existing delivery-facts view for raw per-peer timestamps/cursor state, but the service will never synthesize a "down" verdict from it. A real liveness/failure-detection capability needs a new, explicit mechanism (for example a heartbeat/session-health signal) — new scope requiring its own design decision, not a bug in the current design. |
| `EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE` | design-needed; recorded 2026-08-09 and unscheduled. Named owner for remaining OAuth / rotation / `kid` / JWKS / dynamic client registration after v2 Tasks 4–5 landed Option A installation keyring custody (pre-crash tokens survive LedgerService kill/restart; remint forbidden while an instance exists). Does not change the current slice's ephemeral auth-bundle delete-after-read contract. The eventual plan number is assigned at pickup; no number is reserved by this row. | HIGH | Remaining gap: locally HMAC-signed bearer issuance and operator-distributed credentials still lack OAuth 2.1-shaped lifecycle (issuer/audience/expiry already validated). Candidate direction: OAuth (MCP's OAuth 2.1 authorization framework) plus rotation/`kid`/JWKS. **Live interoperability driver (2026-08-10 Task 6):** Streamable HTTP auth gate returns **401 on `/.well-known/oauth-protected-resource`** (a public discovery path) instead of 404, and **401 responses carry no `WWW-Authenticate` challenge** (only `x-evidence-handoff-code: auth_gate_rejected`). Spec-compliant clients that probe OAuth discovery then hang/`mcp_auth` timeout; Claude Code (static Bearer, no probe) connects; Cursor (probe) fails tool discovery despite a correct static header. Non-OAuth servers should 404 unknown `/.well-known/*` and emit a proper Bearer challenge on 401 — belongs here, not as an ad-hoc mid-run fix. Historical driver (partially superseded by Option A): before durable keyring custody, `service_cli.py` delete-after-read left the signing key only in process memory so a crash invalidated outstanding credentials (observed 2026-08-09 Task 10 Step 3). Secondary benefit: dynamic client registration (RFC 7591) would remove manual token distribution from a shared `credentials.json`. Possible additional driver (explicitly **unverified**): the consolidated pool's `P11-FEAT-REGISTRY` row records ACP `authMethods: []` and that the registry guide's Agent/Terminal Auth admission rule must be verified by live execution before implementation scope is frozen — do not treat registry admission as an established requirement yet. Any future claim that a specific native client (Claude Code, Cursor, Codex) fully supports this OAuth flow depends on `EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD` first establishing verified native-client identity; this row does not itself prove client identity. |
| `EVIDENCE-HANDOFF-FEAT-AT-REST-INTEGRITY` | **Tracked, Not Yet Scheduled** 2026-08-10; design-needed. Raised from completed and archived Task 6 evidence (`evidence-handoff-risk-bearing-slice-implementation_v2.md` Steps 1-3 checked, all six DoD criteria checked, closure PASS): after all readers confirmed through watermark, a behind-cursor tamper is invisible to every `ledger.delivery_read` because `delivery.py` only verifies the unread range (`confirmed+1..watermark`) and overrides client-supplied cursors with the stored confirmed cursor. The frozen design's "periodic at-rest checks remain defense in depth" is not implemented in this slice — only on-scan verification exists. The eventual plan number is assigned at pickup; no number is reserved by this row. | MEDIUM | Ship a real at-rest / full-chain integrity detector (for example scheduled `IntegrityMonitor.verify_full()`) that covers historical sequences behind all confirmed cursors, latches on chain breaks, and does not rely on unread delivery traffic. Do not weaken the on-scan path; do not treat client-supplied cursor overrides as a substitute. Independent of OAuth/`WWW-Authenticate` work under `EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE`. |

## A2A ledger audit obligations

This table is an index projecting slice state, not a second owner. Owning-slice values in backticks
are the six deferred remediation slices above; `program gate contract (pre-work, unscheduled)` and
`this closure plan` are not Feature IDs.

| Obligation | Severity | Owning slice | Status | Priority |
|---|---|---|---|---|
| C1 | CRITICAL | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | MEDIUM |
| C2 | CRITICAL | `EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY` | Open | MEDIUM |
| C3 | CRITICAL | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | MEDIUM |
| H4 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH` | Open | MEDIUM |
| H5 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH` | Open | MEDIUM |
| H6 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH` | Open | MEDIUM |
| H7 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | MEDIUM |
| H8 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY` | Open | MEDIUM |
| H9 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | MEDIUM |
| H10 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD` | Open | MEDIUM |
| H11 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD` | Open | MEDIUM |
| H12a | HIGH | program gate contract (pre-work, unscheduled) | Open | MEDIUM |
| H12b | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD` | Open | MEDIUM |
| H13 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY` | Open | MEDIUM |
| M14 | MEDIUM | `EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY` | Open | MEDIUM |
| M15 | MEDIUM | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | MEDIUM |
| M16a | MEDIUM | `EVIDENCE-HANDOFF-FEAT-LEDGER-AUDIT-WIRING` | Open | MEDIUM |
| M16b | MEDIUM | `EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY` | Open | MEDIUM |
| M16c | MEDIUM | `EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY` | Open | MEDIUM |
| M17 | MEDIUM | this closure plan | **Closed** | MEDIUM |

Counts: 3 CRITICAL, 11 HIGH, 6 MEDIUM. Owners: COMPOSITION 5, INTEGRITY-BOUNDARY 3, DATAPATH 3,
RUNTIME-BOUNDARY 3, EVIDENCE-DOD 3, AUDIT-WIRING 1, gate contract 1, closure plan 1.
