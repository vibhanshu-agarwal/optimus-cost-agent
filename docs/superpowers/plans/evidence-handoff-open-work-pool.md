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
- `docs/superpowers/plans/evidence-handoff-risk-bearing-slice-implementation_v2.md`
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
| `EVIDENCE-HANDOFF-FEAT-A2A-LEDGER` | **Closed** 2026-08-11 for the risk-bearing slice at `72c3b82`; 21 commits `8735885..72c3b82` pushed to `origin/agent/cursor/evidence-handoff-a2a-ledger-risk-slice` (no PR opened). The cross-agent reachability blocker is resolved: Claude Code, Codex, and Cursor each reached the same loopback Docker-hosted Redis service and the host's LAN-bound test service from the host network namespace. [Design](../specs/evidence-handoff-a2a-ledger-design.md). Closing [v2 plan](evidence-handoff-risk-bearing-slice-implementation_v2.md) (Docker Desktop sole implemented/default PostgreSQL rung; wslc removed from runtime); DoD PASS with criterion 2 citing Task 3 Docker artifacts (`bd17dac`) rather than re-running torn-down live infra. Historical [v1 plan](evidence-handoff-risk-bearing-slice-implementation.md) remains frozen. Does **not** close OAuth/rotation (`EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE`), at-rest integrity (`EVIDENCE-HANDOFF-FEAT-AT-REST-INTEGRITY`), peer-liveness (`EVIDENCE-HANDOFF-FEAT-PEER-LIVENESS-SIGNAL`), or the design refresh (`EVIDENCE-HANDOFF-FEAT-A2A-LEDGER-DESIGN-REFRESH`) — those keep their own open rows. | Default-off, opt-in append-only handoff protocol—not a transcript archive—with question, answer, evidence-notice, review-ruling, handoff, and separate acknowledgement entries; large payloads use SHA-256 references. A product-owned MCP Streamable HTTP service fronts loopback PostgreSQL. The product-owned lifecycle manager holds infrastructure privilege and installation signing-key custody (OS keyring). Server-mapped asserted agent identity, role-derived authority, ingress redaction, transactional sequence ordering, durable reader-confirmed cursors, per-agent delivery facts, and structural approval-gate exclusion are load-bearing. Wakeup and network-callable evidence collection are v1 non-goals. |
| `EVIDENCE-HANDOFF-FEAT-A2A-LEDGER-DESIGN-REFRESH` | **Tracked, Not Yet Scheduled** 2026-08-10; non-blocking owner for an operator-directed architecture correction. Create `docs/superpowers/specs/evidence-handoff-a2a-ledger-design_v2.md` from the frozen design; do not edit or rename the frozen parent. This item does not block `evidence-handoff-risk-bearing-slice-implementation_v2.md`. | Restate the local store ladder as Docker Desktop PostgreSQL (sole implemented/default rung) then native Windows PostgreSQL (deferred), with wslc removed. Preserve loopback-only bind, lifecycle-owned infrastructure privilege, MCP access layer, and explicit stopped-lifecycle selection/no runtime failover. The implementation plan retains a pluggable backend protocol/factory so native Windows later is a configuration choice plus adapter, not a lifecycle rewrite. **Task 6 live findings to fold into v2 (2026-08-10, not fixed mid-capstone):** (1) integrity guards belong at operation entry, not only on per-method paths that happen to call `_refuse_if_integrity_latched` — `delivery.read_entries` still issues a delivery token on an empty unread page over a latched/broken chain (design line 493); (2) read-path verification only covers the unread range behind confirmed cursors (pairs with `EVIDENCE-HANDOFF-FEAT-AT-REST-INTEGRITY`); (3) Option B session protocol admission vs binding to the negotiated initialize-response version remains on this agenda. |
| `EVIDENCE-HANDOFF-FEAT-APPROVAL-RECORD` | Design-needed, investigation only; ratified and unscheduled. Independent of the approved redaction-gate design and implementation plan, and blocks neither. The eventual plan number is assigned at pickup; no number is reserved by this row. | Generalize the redaction gate's digest-bound screenshot approval record into an operator Approval/Denial Record for exact artifacts. This is a convenience audit trail, explicitly **not** a security control, authorization mechanism, or cryptographic proof: it records the artifact digest, decision, timestamp, and asserted identity, including denials as well as approvals. The implementing agent never produces the record and only references one by digest; impose no interactive unlock or key management in its path. Voice is out of scope. The record may reserve an optional, unused signature field so future asymmetric signing is additive, but the artifact itself must not be called a signature. `authority=operator-relay` in the A2A ledger remains asserted, not cryptographically proven. |
| `EVIDENCE-HANDOFF-FEAT-PEER-LIVENESS-SIGNAL` | Design-needed, investigation only; recorded and unscheduled. Independent of the in-flight `EVIDENCE-HANDOFF-FEAT-A2A-LEDGER` risk-bearing slice and blocks neither its Task 10 capstone nor Task 11 release gates. The eventual plan number is assigned at pickup; no number is reserved by this row. | Operator ask: can an agent detect that its A2A counterparty is down and raise its own alert? The frozen design's [Per-agent delivery observability](../specs/evidence-handoff-a2a-ledger-design.md#per-agent-delivery-observability) deliberately does **not** provide this — it states "The view reports facts, not guessed process liveness. It must not label an agent online, dead, or healthy solely from cursor activity," because six distinct causes (between turns, context compaction, session errored, dead transcript, delayed-but-alive, broken MCP config) produce identical "no recent cursor advance" facts. Any authenticated `ledger.read`-scoped agent can already poll the existing delivery-facts view for raw per-peer timestamps/cursor state, but the service will never synthesize a "down" verdict from it. A real liveness/failure-detection capability needs a new, explicit mechanism (for example a heartbeat/session-health signal) — new scope requiring its own design decision, not a bug in the current design. |
| `EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE` | **HIGH** priority; design-needed; recorded 2026-08-09 and unscheduled. Named owner for remaining OAuth / rotation / `kid` / JWKS / dynamic client registration after v2 Tasks 4–5 landed Option A installation keyring custody (pre-crash tokens survive LedgerService kill/restart; remint forbidden while an instance exists). Does not change the current slice's ephemeral auth-bundle delete-after-read contract. The eventual plan number is assigned at pickup; no number is reserved by this row. | Remaining gap: locally HMAC-signed bearer issuance and operator-distributed credentials still lack OAuth 2.1-shaped lifecycle (issuer/audience/expiry already validated). Candidate direction: OAuth (MCP's OAuth 2.1 authorization framework) plus rotation/`kid`/JWKS. **Live interoperability driver (2026-08-10 Task 6):** Streamable HTTP auth gate returns **401 on `/.well-known/oauth-protected-resource`** (a public discovery path) instead of 404, and **401 responses carry no `WWW-Authenticate` challenge** (only `x-evidence-handoff-code: auth_gate_rejected`). Spec-compliant clients that probe OAuth discovery then hang/`mcp_auth` timeout; Claude Code (static Bearer, no probe) connects; Cursor (probe) fails tool discovery despite a correct static header. Non-OAuth servers should 404 unknown `/.well-known/*` and emit a proper Bearer challenge on 401 — belongs here, not as an ad-hoc mid-run fix. Historical driver (partially superseded by Option A): before durable keyring custody, `service_cli.py` delete-after-read left the signing key only in process memory so a crash invalidated outstanding credentials (observed 2026-08-09 Task 10 Step 3). Secondary benefit: dynamic client registration (RFC 7591) would remove manual token distribution from a shared `credentials.json`. Possible additional driver (explicitly **unverified**): the consolidated pool's `P11-FEAT-REGISTRY` row records ACP `authMethods: []` and that the registry guide's Agent/Terminal Auth admission rule must be verified by live execution before implementation scope is frozen — do not treat registry admission as an established requirement yet. |
| `EVIDENCE-HANDOFF-FEAT-AT-REST-INTEGRITY` | **Tracked, Not Yet Scheduled** 2026-08-10; design-needed; independent of the in-flight Task 6 latch phase. Raised from live Task 6 evidence: after all readers confirmed through watermark, a behind-cursor tamper is invisible to every `ledger.delivery_read` because `delivery.py` only verifies the unread range (`confirmed+1..watermark`) and overrides client-supplied cursors with the stored confirmed cursor. The frozen design's "periodic at-rest checks remain defense in depth" is not implemented in this slice — only on-scan verification exists. The eventual plan number is assigned at pickup; no number is reserved by this row. | Ship a real at-rest / full-chain integrity detector (for example scheduled or operator-invoked `IntegrityMonitor.verify_full()`) that covers historical sequences behind all confirmed cursors, latches on chain breaks, and does not rely on unread delivery traffic. Do not weaken the on-scan path; do not treat client-supplied cursor overrides as a substitute. Independent of OAuth/`WWW-Authenticate` work under `EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE`. |
