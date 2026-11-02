## Covers

### H1 — HLD v2.24

```markdown
# Optimus - Architecture (HLD)

**Version 2.24 — Cost-savings report, 2026-11-02; local filing — not activated.**

Predecessor: Optimus-Cost-Agent-Architecture-v2.23.pdf; SHA-256 3abcc0c047795d91350b8660c6e26943d39fea13bf99568704b91838cfbb2acb. Retain the predecessor unchanged in `docs/archive/`.

Native carried page bodies originate from Optimus-Cost-Agent-Architecture-v2.18.pdf (SHA-256 0f8725765fecc9a93045fd26630457dfe7112508df164a3ec5bcc55dbc976807). This complete successor retains the predecessor's carried bodies and corrections except for the changes identified below. Page keys remain those of the native baseline.

**What this edition changes.** It describes Plan 12.9's current-session `/savings` report, its measured-cost and coverage boundary, the Auto subset and dated B1 reference columns (§14.10). It corrects the Redis ledger descriptions and explains Plan 12.8's host outbox and Gateway-owned Postgres drain only as needed to identify the report's source and credential boundary. These refreshed statements describe main `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498`, PR #462 merged 2026-11-02T14:02:48Z, with parents `99e6ce7fda20e2a468ef4ce3b17b613e6998f2ad` and PR head `f808289b5d0ebf377538e7b72b94e9c3ffca8a29`.

**Inspected production facts at a88fde8.** The host settles receipts and captures durable records locally; it uploads them using its existing Gateway URL and key. Only the Gateway holds the Postgres credential. The authenticated report route reads that ledger without a model call. Auto attribution comes from `turn.report_context`, not inference from a model name. Reference prices are configuration, independent of model admission and settled charges. B1 is estimated token repricing; B2 and B3 remain unavailable.

**Provenance and controlling Plan 12.2 amendment.** Baseline statements retain `91fd64a` provenance; localized EDIT corrections retain `57e2069`; original registry, production-construction and Auto statements retain `bf440cb`; escalation and host/Gateway timing retain `5977155`. The 2026-10-18 amendment, `docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`, remains controlling for unrefreshed Plan 12.2 material, including source/compaction policy, profiles, maintenance and historical evidence. ADR-024 and ADR-029 retain their recovery scope. Plans 12.5–12.7's memory work is not refreshed, and Plan 12.8 is covered only to the extent stated above. Guardrails is unchanged.

**Evidence and decision status.** Section 15 preserves the failed Windows full suite, the later paging fix's focused evidence and Linux PR CI at `c2ec782`. Separately, main-push guardrails run 41458258151 completed successfully at actual merge `a88fde8`, with full-run coverage validity established. Neither Linux result establishes Windows parity or a Zed rerun. Zed proof costs are synthetic; the unauthorized paid-call incident is separately disclosed. The unrepaired cross-launch Gateway attachment gap is owned by #465. B2/B3 commissioning and the deferred native memory-evaluation campaign belong to #463. ADR-032 is accepted by ADR-033; ADR-034 remains Proposed, with operator acceptance separate. Frozen ADR-012 is unchanged.

**Authority.** Codex's architecture wording; local filing by Claude under the operator's 2026-11-02 answer, verbatim, "Go ahead", to "Go ahead with the Plan 12.9 closure steps?", including Codex drafting these successors and Claude checking and building them. That instruction includes the one-off large-file-hook skip for these PDFs. Publication to main requires the operator's separate approval. The filing label describes this document, not feature activation. This text grants no additional implementation, service-change or paid-call authority. No product suite or live call was run to author it.
```

### L1 — LLD v2.47

```markdown
# Optimus - Low-Level Design

**Version 2.47 — Cost-savings report, 2026-11-02; local filing — not activated.**

Predecessor: Optimus-Cost-Agent-LLD-v2.46.pdf; SHA-256 4a2f9cb64c69d6a8284b72905cb25abf6f979a18d9ccdcad37b98b790e2712a6. Retain the predecessor unchanged in `docs/archive/`.

Native carried page bodies originate from Optimus-Cost-Agent-LLD-v2.41.pdf (SHA-256 69400fd474eb30711fcc9a061243d6a4d2e35d39d7794d4aa69f5ff51b98109b). This complete successor retains the predecessor's carried bodies and corrections except for the changes identified below. Page keys remain those of the native baseline.

**What this edition changes.** It completes the closed Gateway route lists, corrects the production accounting and Redis descriptions, and adds the durable capture prerequisite, report read contract, ACP command lifecycle, Auto attribution and reference-price contracts (§13.13–§13.16). These refreshed statements describe main `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498`, PR #462 merged 2026-11-02T14:02:48Z, with parents `99e6ce7fda20e2a468ef4ce3b17b613e6998f2ad` and PR head `f808289b5d0ebf377538e7b72b94e9c3ffca8a29`.

**Inspected production facts at a88fde8.** `POST /v1/observability/usage-report` authenticates before reading the body or opening Postgres. It serves bounded pages from a read-only repeatable-read transaction. Cursors bind the request, principal, ledger and revision. The host advertises `/savings` after the successful `session/new` response and handles it before ordinary turn admission. Plain `/savings next` advances only after confirmed report delivery. Actual costs remain provider-reported; B1 reprices reported tokens at independent dated reference prices and subtracts the fully loaded actual total once.

**Provenance and controlling Plan 12.2 amendment.** Baseline contracts retain `91fd64a` provenance; localized EDIT corrections retain `57e2069`; original registry, production-construction and Auto contracts retain `bf440cb`; escalation and host/Gateway timing retain `5977155`. The 2026-10-18 amendment, `docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`, remains controlling for unrefreshed Plan 12.2 material, including compaction, numeric policy, profiles, maintenance and historical evidence. ADR-024 and ADR-029 retain their recovery scope. This edition does not refresh Plans 12.5–12.7's memory work or Plan 12.8 beyond the report's accounting prerequisite and necessary Redis corrections. Guardrails is unchanged.

**Evidence and decision status.** Section 14 separates inspected contracts and test sources from reported execution. The Windows full suite failed and its coverage validation refused it. Later focused checks do not become a Windows full-suite or Zed pass. Final Linux PR CI and the formal safety comparison remain attributed to `c2ec782`. Separately, main-push guardrails run 41458258151 completed successfully at actual merge `a88fde8`, with full-run coverage validity established. The cross-launch Gateway attachment gap remains open and unrepaired under #465. B2/B3 commissioning and the deferred native memory-evaluation campaign belong to #463. ADR-032 is accepted by ADR-033; ADR-034 remains Proposed, with operator acceptance separate. Frozen ADR-012 is unchanged.

**Authority.** Codex's architecture wording; local filing by Claude under the operator's 2026-11-02 answer, verbatim, "Go ahead", to "Go ahead with the Plan 12.9 closure steps?", including Codex drafting these successors and Claude checking and building them. That instruction includes the one-off large-file-hook skip for these PDFs. Publication to main requires the operator's separate approval. The filing label describes this document, not feature activation. This text grants no additional implementation, service-change or paid-call authority. No product suite or live call was run to author it.
```

### T1 — Test Strategy v1.10

```markdown
# Optimus - Test Strategy

**Version 1.10 — Cost-savings report, 2026-11-02; local filing — not activated.**

Predecessor: Optimus-Cost-Agent-Test-Strategy-v1.9.pdf; SHA-256 21ab8cacd90fd56bdce7841c48efaf2642cc45555dc5fa43f40786e12fbb60fd. Retain the predecessor unchanged in `docs/archive/`.

Native carried page bodies originate from Optimus-Cost-Agent-Test-Strategy-v1.7.pdf (SHA-256 31a60c6a198c60cc1203ff5c4a8e6e0300a820ec18cc702e25f246edc51dc0b0). This complete successor retains v1.9's carried bodies and corrections except for the changes identified below. Page keys remain those of the native baseline.

**What this edition changes.** It adds the real Postgres capture/report tier, its explicit selection and resource prerequisites (§3, §15.8), and the claim-to-check and reported-evidence distinctions for Plan 12.9 (§15.8, §16.1). The production and test-source inspection pin is main `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498`, PR #462 merged 2026-11-02T14:02:48Z, with parents `99e6ce7fda20e2a468ef4ce3b17b613e6998f2ad` and PR head `f808289b5d0ebf377538e7b72b94e9c3ffca8a29`.

**Inspected facts at a88fde8.** `requires_plan12_capture_postgres` is deselected by default. Its tests require a released disposable Postgres resource and inspect its container identity before connecting. Credential-boundary cases run separately with the password absent from the pytest environment and resolved by the Gateway child. Unit checks cover arithmetic, coverage qualifications, references, snapshots, command advertisement and delivery-aware continuation. Real Postgres tests cover migration, immutable readback, concurrent ingest, deadlines, outages and the Gateway read boundary. Test presence is distinct from an executed passing result.

**Historical provenance and controlling Plan 12.2 amendment.** Unchanged v1.9 statements retain their `91fd64ac78025efe1076bddb106ff89e6adb2030` inspection pin and the named `cf9bb9d` or earlier evidence pins. Their production-absence and deferred-status descriptions are historical, not a new current-state assessment. The 2026-10-18 amendment, `docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`, remains controlling for unrefreshed Plan 12.2 material and evidence. HLD v2.24 and LLD v2.47 retain their intervening scoped successors. This edition does not refresh Plans 12.5–12.7's memory work or Plan 12.8 beyond the report's durable-accounting prerequisite. Guardrails is unchanged.

**Evidence qualification.** The one Plan 12.9 Windows full suite at `f1cb559` failed; its coverage numbers are not a validated passing result. The operator accepted no Windows rerun, conditional on Linux PR CI and the formal safety comparison passing. Final PR evidence is reported at `c2ec782`, separately from the earlier `5613c98` receipt retained in `qualification.json`. Main-push guardrails run 41458258151 subsequently completed successfully at actual merge `a88fde8`, with full-run coverage validity established. The final plain-next delivery fix was not rerun in Zed or a Windows full suite. Zed proof costs are synthetic, and the out-of-plan paid-call incident remains disclosed. Its unrepaired Gateway attachment gap is owned by #465. B2/B3 commissioning and the deferred native memory-evaluation campaign belong to #463. ADR-034 remains Proposed; ADR-032 is accepted by ADR-033; frozen ADR-012 is unchanged.

**Authority.** Codex's testing-strategy wording; local filing by Claude under the operator's 2026-11-02 answer, verbatim, "Go ahead", to "Go ahead with the Plan 12.9 closure steps?", including Codex drafting these successors and Claude checking and building them. That instruction includes the one-off large-file-hook skip for these PDFs. Publication to main requires the operator's separate approval. The filing label describes the document. No product suite, container, editor session or paid call was run to author this text.
```

## Edits

### H2 — hld/3

OLD:
```text
| Local ledger | Run/session/request/Gateway/provider request attribution |
```

NEW:
```text
| Host settlement and durable capture | Receipt acceptance and run/session/request attribution; local outbox delivery with the existing Gateway URL and key |
| Gateway-owned Postgres ledger | Durable capture and report source when accounting is configured; only the Gateway holds its credential (§14.10) |
```

### H3 — hld/4

OLD:
```text
8. Storage inside the Local Storage Engine Persistence Layer via Async TS.ADD Numeric Telemetry
   Tracking (RedisTimeSeries) and Async HSET Workspace Metrics Serialisation (Redis HASH
   Architecture Indexes).
```

NEW:
```text
8. Preserve existing Redis state and telemetry. At `a88fde8`, production receipt settlement is
   host-owned; durable capture appends to the local outbox and drains through the Gateway into
   its Optimus-owned Postgres ledger (§14.10). Redis telemetry is not that durable usage ledger.
   This accounting correction does not refresh the memory/index design.
```

### H4 — hld/7

OLD:
```text
The IDE, local agent, loopback Gateway, Redis, repository and optional Phoenix collector belong to one developer environment. Agent and Gateway are separate processes; the agent receives only Gateway URL/shared secret and cannot read the Gateway aggregator credential.
```

NEW:
```text
The IDE, local agent, loopback Gateway, Redis, repository, local capture outboxes, configured Postgres ledger and optional Phoenix collector belong to the developer's deployment. Agent and Gateway are separate processes. The host receives only the Gateway URL and shared secret as runtime credentials; aggregator and Postgres credentials belong to the Gateway. Existing Redis state and telemetry remain separate from the durable report ledger (§14.10).
```

### H5 — hld/7

OLD:
```text
| Agent / Gateway -> Redis | Existing state and usage ledger; no new context-engine store |
```

NEW:
```text
| Agent -> Redis | Existing agent state and telemetry; not the durable report ledger |
| Host -> local outbox -> Gateway | Durable capture uploaded with the existing Gateway URL and key |
| Gateway -> Postgres | Optimus-owned usage ledger and report reads; Gateway-only database credential |
```

### H6 — hld/9

OLD:
```text
| 4. Post-call (Attribution) | Gateway usage object -> EvidenceLedger -> RedisTimeSeries | Silent cost accumulation; enables per-run audit. |
```

NEW:
```text
| 4. Post-call (Attribution) | Provider-reported Gateway usage -> host settlement -> durable outbox -> Gateway-owned Postgres ledger (§14.10) | Exposes measured known cost and incomplete coverage; supplies the report without inventing a charge. |
```

### H7 — hld/11

OLD:
```text
The actual request path retains the four actors: local agent, loopback Gateway, approved aggregator and Redis/Phoenix. The accepted product migration replaces the old monetary budget precheck with trust, complete capacity and finite work controls.
```

NEW:
```text
The model request path is local agent -> loopback Gateway -> approved aggregator. At `a88fde8`, host receipt settlement and durable capture are distinct from Redis telemetry and optional Phoenix export. The local outbox drains through the Gateway into its configured Postgres ledger; a separate authenticated read returns report pages (§14.10). Trust, complete capacity and finite work controls remain independent of cost reporting.
```

### H8 — hld/11

OLD:
```text
Gateway -> Redis: normalized ledger record (exactly once)
Gateway -> Phoenix: OTel span export via OTLP (no invented model cost)
Gateway -> local agent: normalized GatewayUsage + response
```

NEW:
```text
Gateway -> local agent: normalized GatewayUsage + response
Local agent: settle receipt and append durable capture to local outbox
Host outbox -> Gateway -> Postgres: idempotent capture drain and committed acknowledgement
Gateway -> Phoenix: OTel span export via OTLP (no invented model cost)
Local agent -> Gateway -> Postgres: authenticated usage-report read
```

### H9 — hld/11

OLD:
```text
| Ledger and trace | Persist normalized receipt exactly once and export sanitized OTel spans independently; trace export is not a billed inference request. |
```

NEW:
```text
| Settlement, capture and trace | The host accepts receipts; durable capture drains idempotently into Gateway-owned Postgres. Canonical receipts contribute once; replays and conflicts retain their dispositions. Redis telemetry and sanitized OTel export are separate, and neither supplies a second debit. Accounting outages qualify the report and retain local backlog without stopping model work. |
```

### H10 — hld/2

OLD:
```text
Numeric performance histories are channelled separately to RedisTimeSeries (tracking tokens_input, tokens_output, cost_usd) tagged by unique run_id strings with a 30-day retention (2,592,000,000 ms, `TS.CREATE` with `TS.ALTER` fallback in `optimus.telemetry.redis_adapter`).
```

NEW:
```text
RedisTimeSeries retains token/cost telemetry by run_id with 30-day retention (2,592,000,000 ms; TS.CREATE/TS.ALTER). At `a88fde8`, this is not host settlement or the durable Postgres report ledger (§14.10), and does not prove billing completeness.
```

### H11 — hld/10

OLD:
```text
| Loopback URL only | allowed domains, Redis URL, optional OTLP endpoint |
```

NEW:
```text
| Loopback URL only; no database credential | allowed domains, Redis URL, optional OTLP endpoint; approved accounting configuration and Gateway-keyring Postgres credential (§14.10) |
```

### H12 — hld-14-context-engine.md

OLD:
```text
this is not a full Plan 12.3 refresh.
```

NEW:
```text
this is not a full Plan 12.3 refresh.

Plan 12.9's report and its necessary Plan 12.8 accounting prerequisite are refreshed separately at main `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498` (§14.10). Plans 12.5–12.7's memory work is not refreshed. The controlling amendment and the prior EDIT, registry, Auto, escalation and timing pins remain as stated.
```

### H13 — hld-14-context-engine.md

OLD:
```text
Reviewer/depth behavior and savings-report surfaces remain outside that delivery.
```

NEW:
```text
Reviewer/depth behavior remains outside that delivery. Savings reporting was delivered separately by Plan 12.9 at `a88fde8` (§14.10); it is not evidence that the original Auto delivery established realized savings.
```

### H14 — hld-14-context-engine.md

OLD:
```text
LLD §13.12 specifies the transport details.
```

NEW:
```text
LLD §13.12 specifies the transport details.

## 14.10 Cost-savings report and its durable accounting source

At main `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498`, Plan 12.9 supplies a current-session `/savings` report through ACP. ADR-012's requirement remains accepted with open items. ADR-034 describes the delivered mechanism but remains Proposed; its operator acceptance is separate. ADR-032's durable-capture design is accepted by ADR-033. None of those frozen records is rewritten by this edition.

**Accounting ownership.** The host's `TurnSettlement` accepts attempt receipts and maintains session settlement. Durable capture extends that path: an append-only local host outbox records intents, receipts and coverage epochs; delivery uses the existing Gateway URL and key to upload to `POST /v1/observability/usage-capture`. The Gateway owns the Postgres connection and drain transaction, committed cursors, immutable facts and replay/conflict dispositions. Its physical-attempt stream is diagnostic evidence, not a second receipt charge. Only the Gateway resolves the Postgres credential, from its own keyring namespace after approved configuration checks. The host receives no database credential.

Redis remains in the existing agent-state and telemetry paths. `UsageAccountingService` and its Redis settled-usage sink are retained components, not the production ACP settlement path or the report's durable store. The corresponding older ledger arrows and carried TimeSeries descriptions must be read with this qualification.

**Availability and coverage.** Capture and database failures leave visible incomplete accounting and local backlog; they do not introduce a product cost stop or stop model work. A committed acknowledgement permits bounded compaction of eligible acknowledged segments. Unacknowledged records are not discarded to cap the backlog. Capture is prospective: history before durable capture remains qualified, and platform fsync is not a hardware power-loss guarantee.

**Report boundary.** `/savings` asks the authenticated `POST /v1/observability/usage-report` route for the current session; `/savings turn <run-id>` narrows it to one turn. The host supplies its expected turn count and capture frontier. The Gateway reads Postgres and returns bounded pages with known cost, unknown-cost counts, coverage reasons, the explicitly attributed Auto subset and turn/stage detail. Missing epochs, pending delivery, stream gaps, late receipts and conflicts prevent the corresponding definitive claim. Auto selection is recorded in `turn.report_context`; a model name or role is not Auto evidence.

The command makes no model call, enters no conversation context and changes no execution mode or strategy. `/savings next` continues the report that session last received; an explicit continuation is also supported. A cancelled or unconfirmed delivery does not advance plain next. ACP advertises the command after the successful `session/new` response. LLD §13.14–§13.15 specifies the route and delivery contracts.

**Comparison meaning.** The Auto table contains one B1 estimate per configured reference: the same reported tokens at that reference's dated list prices, minus the actual fully loaded Auto total once. Classification, summarization, retries and escalation already contribute to that actual total and are not deducted again. Negative savings remain visible. Missing costs or price-relevant token splits leave the affected comparison incomplete; unknown is never zero.

References live in `optimus_model_policy/savings_references.yaml`, with a validated whole-file operator override. They need not belong to the routing registry and never affect admission, selection or settled charges. Immutable registry and reference snapshots preserve provenance; a usage envelope receives `price_snapshot_id` only after its registry snapshot is durable locally. Reference dates are dated evidence, not a promise of current prices.

B1 does not predict another model's calls, context, retries, output or quality. B2 and B3 are separate unavailable sections; they have no amount or speculative input reader. Sourced B4 material is benchmark context only. B2/B3 commissioning, producer-owned contracts, paid authority and the deferred native memory-evaluation campaign belong to OC-4 (#463: https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/463). Section 15 states the reported verification and its limits.
```

### H15 — hld-15-capability-status.md

OLD:
```text
they do not re-pin the retained Auto, EDIT or baseline evidence.
```

NEW:
```text
they do not re-pin the retained Auto, EDIT or baseline evidence.

Plan 12.9 report statements and the necessary Plan 12.8 accounting corrections below describe main `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498` (2026-11-02). Their execution evidence retains its own source identities. Plans 12.5–12.7's memory work and the remainder of Plan 12.8 are outside this refresh.
```

### H16 — hld-15-capability-status.md

OLD:
```text
| Provider-reported usage ledger and exactly-once settlement (§5A, §11.1) | Implemented (`optimus/usage`, `optimus/evidence`, `optimus/telemetry/redis_adapter.py`) | Unit tests; `requires_redis` tier; sealed offline suites | Active |
```

NEW:
```text
| Provider-reported settlement and durable usage capture (§5A, §11.1, §14.10) | Host `TurnSettlement`; local outbox -> authenticated Gateway capture -> Optimus-owned Postgres; canonical receipt counted once, with replay/conflict evidence | Unit sources and real `requires_plan12_capture_postgres` checks; reported Plan 12.9 evidence below | Capture composed in the ordinary host; durable drain requires approved Gateway accounting configuration and credential. Redis state/telemetry is separate |
```

### H17 — hld-15-capability-status.md

OLD:
```text
| Final reviewer step (ADR-008) and net savings report (ADR-012) | Reviewer step proposed (ADR-008, status Proposed); savings report specified (ADR-012 accepted with open items, issue #248); neither implemented | None | Deferred under existing owners |
```

NEW:
```text
| Final reviewer step (ADR-008) | Proposed; unchanged by Plan 12.9 | None added here | Retains its existing owner |
| Cost-savings report (§14.10; ADR-012, ADR-034) | `/savings`, current-session and turn scopes, measured cost/coverage and estimated Auto B1 columns at `a88fde8`; ADR-034 remains Proposed | Unit sources, real Postgres tier and reported independent ACP/Zed proof; qualification below | Offered when durable capture is composed; usable totals depend on ledger availability and coverage |
| Gateway usage-report read (§14.10) | Authenticated `POST /v1/observability/usage-report`; bounded read-only pages and sealed continuation | Contract/unit and real Postgres/HTTP checks | Gateway-only database credential; no model call |
| Auto attribution and price provenance (§14.10) | Capability-negotiated `turn.report_context`; independent dated reference configuration; durable registry/reference snapshots | Attribution, reference, snapshot and report tests | Missing attribution or price-relevant facts qualify the affected comparison |
| B2/B3 comparisons and native memory-evaluation campaign | Report sections state unavailable; no campaign or speculative reader delivered | No qualifying B2/B3 result claimed | Commissioning, contracts and paid authority belong to #463 |
```

### H18 — hld-15-capability-status.md

OLD:
```text
**#397 escalation and timing evidence.**
```

NEW:
```text
**Plan 12.9 report evidence.** Implementation inspection is at `a88fde8`; execution is separately attributed in `reports/plan12-cost-savings/qualification.json` and `zed-ui.json`. The one Windows full suite at `f1cb559` failed: 14 failed, 11,508 passed, 54 skipped and 165 deselected. Its coverage validator refused the run. The later plain-next delivery fix had focused and revert checks; it was not rerun in Zed or a Windows full suite.

The operator's "Accept, no rerun" disposition was conditional on Linux PR CI and the formal safety comparison. Final PR evidence is reported on #248, comment 6579096728 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/248#issuecomment-6579096728): test merge `c2ec782`, 11,272 passed, 318 skipped and 165 deselected; required coverage floors and full-run validation passed; the formal comparison against main `99e6ce7` passed with no safety-row regression. The checked-in qualification retains the earlier `5613c98` receipt. Those PR results retain their own source identities.

Separately, main-push guardrails run 41458258151 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/41458258151) completed successfully at actual merge `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498`. Its Linux/Python 3.14.10 job reports 11,272 passed, 318 skipped, 165 deselected and 2 warnings. Required product floors passed and the validity step established full-run validity for session `20261102T140403-3002-56d82c`. Source was clean before and after; records were COMPLETE with active default selection and unsupported Linux native/parent/guard capability. This is separate main-push evidence, not Windows parity or an editor rerun.

The independent ACP/Zed proof used synthetic costs and does not establish realized savings. D4 authorized zero paid calls. A separate setup incident made unauthorized paid requests through another launch's Gateway; `zed-ui.json` retains it outside proof evidence. The cross-launch attachment gap remains open and unrepaired, now owned by #465 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/465). The pinned reports' earlier temporary #248 custody is historical; filing #465 changes ownership, not the product. B2/B3 and the deferred native memory-evaluation campaign belong to #463. Test Strategy §16.1 gives the evidence distinctions. This document does not close #248 or confer general Phase 1 sign-off.

**#397 escalation and timing evidence.**
```

### H19 — hld/12

OLD:
```text
Test Strategy v1.9 §8A governs.
```

NEW:
```text
Test Strategy v1.10 §8A governs; its retained coverage policy is unchanged.
```

### H20 — hld/13

OLD:
```text
Coverage policy is authoritative in Test Strategy v1.9 §8A
```

NEW:
```text
Coverage policy is authoritative in Test Strategy v1.10 §8A
```

### L2 — lld/2

OLD:
```text
The Gateway holds the approved developer aggregator credential in its own local environment or OS credential storage.
```

NEW:
```text
The Gateway holds the approved developer aggregator credential in its own local environment or OS credential storage. With durable accounting configured, it alone resolves the Postgres credential from its Gateway-owned keyring namespace; the host uses only its existing Gateway URL and key (§13.13).
```

### L3 — lld/2

OLD:
```text
Provider-reported usage -> normalized existing ledger
```

NEW:
```text
Provider-reported usage -> host settlement -> durable outbox -> Gateway-owned Postgres
```

### L4 — lld/2

OLD:
```text
| /v1/observability/traces | Structured trace validation/redaction -> OTel/OTLP -> Phoenix by default |
```

NEW:
```text
| /v1/observability/traces | Structured trace validation/redaction -> OTel/OTLP -> Phoenix by default |
| /v1/decisions | Typed Auto classifier decision; original contract in §13.10.4 |
| /v1/observability/usage-capture | Host outbox upload -> Gateway-owned Postgres transaction and committed acknowledgement (§13.13) |
| /v1/observability/usage-report | Capabilities or bounded read-only session/turn report; no model call (§13.14) |
```

### L5 — lld/2

OLD:
```text
All seven routes authenticate locally. No MCP endpoint is added. Product dollar stops retire only under the accepted migration; independent evaluation ceilings remain.
```

NEW:
```text
All ten listed routes are POST routes and authenticate locally at `a88fde8`. No MCP endpoint is added. Product dollar stops remain removed under the accepted migration; independent evaluation ceilings retain their own authority.
```

### L6 — lld/2

OLD:
```text
| RedisTimeSeries | Existing usage/state attribution |
```

NEW:
```text
| Redis / RedisTimeSeries | Existing agent state and telemetry; not the durable report ledger |
| Postgres | Optimus-owned durable capture/report ledger; credential resolved only by the Gateway |
```

### L7 — lld/3

OLD:
```text
# Authenticated structured trace ingress
POST /v1/observability/traces
```

NEW:
```text
# Authenticated structured trace ingress
POST /v1/observability/traces

# Typed Auto classifier decision (§13.10.4)
POST /v1/decisions

# Durable capture upload (§13.13)
POST /v1/observability/usage-capture

# Capabilities and read-only usage report (§13.14)
POST /v1/observability/usage-report
```

### L8 — lld/3

OLD:
```text
- Isolate upstream credentials from the agent process.
```

NEW:
```text
- Isolate upstream credentials and the Gateway-owned Postgres credential from the agent process.
```

### L9 — lld/3

OLD:
```text
| Strict loopback URL | domains, Redis URL, optional OTLP endpoint |
```

NEW:
```text
| Strict loopback URL; no Postgres credential | domains, Redis URL, optional OTLP endpoint; approved accounting configuration and Gateway-keyring database credential (§13.13) |
```

### L10 — lld/4

OLD:
```text
account directly. The Gateway records the aggregator response into one local ledger.
```

NEW:
```text
account directly. The Gateway returns normalized provider-reported usage. At `a88fde8`, the host accepts receipts through `TurnSettlement`; durable capture drains from its local outbox through the Gateway into an Optimus-owned Postgres ledger (§13.13). Redis telemetry is separate.

The carried "Gateway Tool and Observability Endpoints" page that follows is historical: its seven-route listing is not exhaustive at `a88fde8`. The current ten-route inventory is in §0 and §D, including decisions, usage capture and usage report. This qualification preserves the native page without presenting its incomplete list as the current API.
```

### L11 — lld/4

OLD:
```text
  -> GatewayUsage + normalized local ledger
```

NEW:
```text
  -> GatewayUsage + host receipt settlement
  -> local durable outbox -> authenticated Gateway capture -> Postgres ledger
```

### L12 — lld/4

OLD:
```text
| Trace export | delivery state and trace IDs; no allocated/amortized request charge |
```

NEW:
```text
| Trace export | delivery state and trace IDs; no allocated/amortized request charge |
| Usage-report read | existing canonical ledger facts and explicitly labelled estimates; no model dispatch or new provider charge |
```

### L13 — lld/33

OLD:
```text
## Required identity
```

NEW:
```text
**Production qualification at a88fde8.** The preceding `UsageAccountingService` listing is a retained component contract, not the production ACP settlement wiring. Production uses host `TurnSettlement`, extended by durable capture and Gateway-owned Postgres delivery (§13.13). The Redis settled-usage sink is not wired into that production settlement path. Existing Redis agent state and telemetry remain.

This qualification also applies to the carried §10.1/§10A material that follows: its RedisTimeSeries implementation and historical policy do not identify the durable ledger read by the savings report. Provider-reported charges remain authoritative. Registry snapshots preserve actual-side provenance; independent dated reference snapshots support B1 estimates only (§13.16), never replacement settled charges.

## Required identity
```

### L14 — lld/38

OLD:
```text
The Test Strategy v1.9 is authoritative for coverage, release, live-dependency, and trace evidence.
```

NEW:
```text
The Test Strategy v1.10 is authoritative for coverage, release, live-dependency, and trace evidence. Its §15.8 and §16.1 add the durable capture/report checks and their qualified execution evidence; the retained coverage policy is unchanged.
```

### L15 — lld/38

OLD:
```text
| Redis integration | Real TimeSeries-capable Redis |
```

NEW:
```text
| Redis integration | Real TimeSeries-capable Redis |
| Durable usage capture/report | Real released disposable Postgres under `requires_plan12_capture_postgres`; credential-boundary cases additionally require their separately provisioned Gateway keyring configuration |
```

### L16 — lld-13-context-integration.md

OLD:
```text
this is not a full Plan 12.3 refresh.
```

NEW:
```text
this is not a full Plan 12.3 refresh.

Sections 13.13–13.16 describe Plan 12.9 and its necessary Plan 12.8 accounting prerequisite at main `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498`. They do not refresh Plans 12.5–12.7's memory work or the remainder of Plan 12.8, and do not re-pin earlier contracts or evidence.
```

### L17 — lld-13-context-integration.md

OLD:
```text
Section 14 distinguishes this inspected test coverage from reported execution, live evidence and remaining obligations.
```

NEW:
```text
Section 14 distinguishes this inspected test coverage from reported execution, live evidence and remaining obligations.

## 13.13 Durable accounting prerequisite and ownership

At `a88fde8`, production receipt acceptance belongs to host `TurnSettlement`. `DurableCapture` extends that settlement path with intents, accepted receipts, coverage epochs and terminal/late dispositions in an append-only per-user outbox. `CaptureDelivery` uploads through the existing Gateway URL and key to `POST /v1/observability/usage-capture`; it does not connect to Postgres.

The Gateway owns `UsageStore`, the Postgres connection and drain transaction. A committed batch advances the ledger cursor and returns an acknowledgement binding ledger instance, stream, sequence and digest. Identical replay does not add a second charge; aliases and contradictory receipts retain explicit dispositions. Database constraints and triggers protect append-only facts. The Gateway's physical-attempt outbox records evidence the host may not receive, but does not create a second settled debit.

`<config_root>/accounting/gateway-accounting.json` contains non-secret connection facts and the credential entry's name. Approved configuration bytes are launch-bound. Only the Gateway resolves the password from `optimus-gateway-accounting`; it is not projected into the host environment, command line, capture records or diagnostics. Migrations belong to `migrations/optimus_usage/`: `001_durable_capture.sql` and `002_savings_report.sql`.

The authorized ordinary host composes capture even when delivery is unavailable. An accounting outage retains backlog and exposes incomplete coverage without stopping model work. Eligible acknowledged closed segments may be compacted; unacknowledged records are not deleted to enforce a storage cap. Capture is prospective and preserves ADR-032's platform durability and orphan-tail limitations. ADR-033 accepts ADR-032, whose original Proposed status line remains frozen.

Redis still serves existing agent state and telemetry. `UsageAccountingService`, `EvidenceLedger` and the Redis settled-usage component must not be mistaken for this production durable report path.

## 13.14 Gateway usage-report read contract

`optimus_security.usage_report_contract` is the shared request/response authority for `POST /v1/observability/usage-report`. The Gateway authenticates the existing bearer key before reading the body or opening the ledger.

- `operation: capabilities` returns supported features without database access.
- `operation: report` supplies `schema_version`, `session_id`, optional `turn_id` and `reference_ids`, `page_size`, optional `cursor`, `expected_turns` and optional per-stream `frontier`. Nullable fields are still fields in the strict request schema.
- Bounds are 16 KiB per request, 1 MiB per response, at most 100 detail rows per page and 10,000 attempts or turns per selected scope. An oversized scope returns unavailable totals, not truncated totals.
- Monetary values are decimal text; null means unknown. Responses distinguish session totals, the Auto subset, attribution counts, unallocated session-less overhead, comparison columns, detail, B2/B3 unavailable states, optional sourced benchmark context and continuation.
- Reads use a read-only repeatable-read transaction. The reader verifies pinned migrations but never migrates or writes the ledger.

The server gives body reading and reply writing separate five-second bounds. The report worker has a five-second budget for database reading, arithmetic and serialization; two outstanding worker slots bound concurrency. An expired worker's late result is discarded and its slot remains occupied until it exits. The host report transport independently bounds the complete exchange to 15 seconds and caps response bytes; this is separate from model-request timing in §13.12.

Cursors are sealed under a Gateway-process-only key. They bind the authenticated principal, request scope and reference selection, ledger instance, revision and position. A changed ledger, relevant facts, request or reference configuration, altered cursor, or Gateway restart refuses continuation with `409 REPORT_CHANGED`.

Errors have stable codes and no exception text: `REQUEST_INVALID` (400), `UNAUTHORIZED` (401), `REPORT_CHANGED` (409), `REQUEST_TOO_LARGE` (413), `ACCOUNTING_NOT_CONFIGURED`, `LEDGER_UNAVAILABLE` or `REPORT_BUSY` (503), and `REPORT_TIMEOUT` (504). A report failure affects that report, not model-work availability.

## 13.15 ACP commands and delivery-aware continuation

The configured host offers reports when `DurableCapture` is composed. After a successful `session/new` response has been written, the adapter attempts `session/update` with `sessionUpdate: available_commands_update` and the `savings` command. Advertisement failure does not disable a correctly typed command.

Supported forms are `/savings`, `/savings turn <run-id>`, `/savings next` and `/savings next <continuation>`. Attachments or malformed savings syntax receive usage guidance. The current-session form is the selected product scope; no day/project aggregation is supplied.

The adapter recognizes the command before ordinary turn admission or classification. It holds the session's prompt slot while reading and delivering the report, but creates no conversation turn or accounting epoch, calls no model or workspace tool, reopens no MCP tools, and changes no mode or strategy. Rendering uses validated Gateway values and escapes and bounds untrusted identifiers.

`SavingsReports.answer` prepares a report without moving the session's plain-next position. The adapter calls `delivered` only after a report notification has a confirmed flush. Cancellation, an abandoned late read, an undelivered page or a stated report failure preserves the prior continuation. Session retirement and server teardown suppress a send that has not begun; a begun write remains in custody. An ambiguous delivery is not reported as confirmed success. The host retains a bounded continuation cache; Gateway cursor validation remains authoritative.

The plain-next form was an operator-approved addition on 2026-11-02 to the plan's original forms. Its final delivery-publication correction was covered by focused and revert checks, not a later Zed or Windows full-suite run (§14).

## 13.16 Attribution, snapshots and comparison arithmetic

Before classification, the host supplies `turn.report_context` with the admitted turn's explicit `auto` or `fixed` selection, registry hash and strategy where present. Capture emits this added kind only after the Gateway advertises `capture.turn.report_context`; an older Gateway must not receive a kind that would block its stream. A newly started owned Gateway is queried before prompts; otherwise delivery negotiates on its passes. Missing or contradictory selection remains unattributed and qualifies the Auto comparison.

The reader folds canonical receipts rather than summing aliases or replays. Known cost is summed once; unknown costs remain counted and unknown. Expected turns and the host capture frontier prevent an empty or lagging ledger from certifying completeness. Missing/open/incomplete epochs, conflicts, late receipts, stream gaps or unproven delivery qualify the affected totals. Session-less overhead on the host streams is shown separately and is never added to the session total.

B1 reprices the Auto subset's reported tokens independently for each configured reference, then subtracts the actual fully loaded Auto total once. All captured stage costs already belong to that total. Cached tokens are nested within input, and reasoning tokens within output; neither is added twice. Long-context pricing uses the reference's configured threshold and schedule. A missing split needed to distinguish prices, missing category price or inconsistent token counts leaves the attempt unpriced with its reason. A split that cannot change the price is not required.

Savings remain signed. A zero baseline has no percentage. A reference's savings and percentage are withheld when its baseline or the actual scope is incomplete. Cache-write tokens are not captured and are excluded from reference columns with an explicit disclosure. B1 columns are alternatives, never additive, and are not measured Auto-off results.

`optimus_model_policy/savings_references.yaml` and its strict frozen schema supply independent reference configuration. A whole-file operator override is bound with the approved accounting literal. References need not be admitted registry models; they never participate in routing, price ordering or settled cost. Source locators and price dates qualify each column independently. Dates record the price evidence, not guaranteed present-day prices.

The Gateway captures content-derived registry and reference snapshots through its outbox. Registry snapshots preserve effective registry, role/tier, route and price provenance; their price date remains unknown where the registry has no date in data. Responses and decisions usage envelopes receive `price_snapshot_id` only after the registry snapshot is durable locally. Snapshot failure leaves the ID absent and does not manufacture or replace a provider charge.

B2 and B3 remain separate unavailable sections with no speculative producer formats or readers. Sourced B4 is context only. Their commissioning and the deferred native memory-evaluation campaign belong to #463 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/463). ADR-034 remains Proposed; delivery does not change its acceptance status. The ability to attach to another launch's Gateway remains open and unrepaired under #465 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/465); the ownership transfer does not change the pinned production behavior.
```

### L18 — lld-14-capability-status.md

OLD:
```text
they do not re-pin the original Auto, EDIT or baseline evidence.
```

NEW:
```text
they do not re-pin the original Auto, EDIT or baseline evidence.

Plan 12.9 contracts and the necessary Plan 12.8 accounting corrections below describe main `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498` (2026-11-02). Their reported execution retains separate source identities. Plans 12.5–12.7's memory work and the remainder of Plan 12.8 are outside this refresh.
```

### L19 — lld-14-capability-status.md

OLD:
```text
| Gateway routes `/v1/responses`, `/v1/chat/completions`, four typed tools, `/v1/observability/traces` (§0, §D) | Implemented (`optimus_gateway/server.py`, `tool_handlers.py`, `observability.py`) | Unit tests; `requires_gateway` and `requires_phoenix` live tiers | Active |
```

NEW:
```text
| Gateway routes (§0, §D) | Ten authenticated POST routes at `a88fde8`: responses, chat completions, decisions, four typed tools, traces, usage capture and usage report | Route/contract tests; each live dependency requires its own tier | Dispatch present; route-specific configuration still applies |
| Durable capture and Postgres ledger (§13.13) | Host outbox and `CaptureDelivery`; Gateway `UsageStore`, transactional drain, immutable facts and pinned migrations | Unit sources and real `requires_plan12_capture_postgres` checks; reported evidence below | Capture composed; durable delivery requires approved accounting configuration and Gateway-only credential |
| Usage-report route (§13.14) | Shared neutral contract; bounded read-only repeatable-read pages, sealed cursors and stable errors | Unit/contract, real Postgres and HTTP/process-boundary checks | Capabilities without a database; reports require available accounting |
| ACP `/savings` (§13.15) | Post-response command advertisement; local handling and confirmed-delivery plain-next publication | Unit/channel tests and reported independent ACP/Zed proof; final paging fix has focused evidence | Offered when durable capture is composed; no model call or conversation turn |
| Auto attribution and price provenance (§13.16) | Negotiated `turn.report_context`; independent dated references and immutable snapshots | Attribution, reference, snapshot, arithmetic and Postgres checks | Missing facts qualify the affected comparison; references grant no model admission |
| B2/B3 and native memory-evaluation campaign | Unavailable sections; no campaign or speculative reader delivered | No qualifying B2/B3 result claimed | Commissioning, contracts and paid authority owned by #463 |
```

### L20 — lld-14-capability-status.md

OLD:
```text
| Evidence ledger and USD run totals (§9E, §9E.1) | Implemented (`optimus/evidence`); rename complete, fields `ledger_run_total_cost_usd` and `ledger_run_total_billing_units` | Unit tests; `requires_redis` tier | Active |
```

NEW:
```text
| Evidence ledger and USD run-total wire contract (§9E, §9E.1) | Retained `optimus/evidence` component and completed field rename: `ledger_run_total_cost_usd`, `ledger_run_total_billing_units` | Historical component evidence retains its pin | Does not identify the production durable report store; see §13.13 |
```

### L21 — lld-14-capability-status.md

OLD:
```text
| Usage accounting (§10) | Implemented (`UsageAccountingService.record_gateway_usage` in `optimus/usage/accounting.py`); the `record_usage` listing is illustrative | Unit tests | Active |
```

NEW:
```text
| Usage accounting (§10, §13.13) | `UsageAccountingService.record_gateway_usage` remains implemented; the listing is illustrative. Production ACP settlement uses `TurnSettlement` and durable capture | Component/unit sources; capture/report evidence below | The retained service and Redis settled-usage sink are not wired into production ACP settlement |
```

### L22 — lld-14-capability-status.md

OLD:
```text
| RedisTimeSeries retention and idempotent creation (§10.1) | Implemented (`optimus/telemetry/redis_adapter.py`, 2,592,000,000 ms, `TS.CREATE` then `TS.ALTER`) | Unit tests; `requires_redis` tier | Active |
```

NEW:
```text
| RedisTimeSeries retention and idempotent creation (§10.1) | Retained telemetry implementation (`optimus/telemetry/redis_adapter.py`, 2,592,000,000 ms, `TS.CREATE` then `TS.ALTER`) | Unit tests; real Redis tier for Redis claims | Existing telemetry remains; this is not the durable Postgres report ledger |
```

### L23 — lld-14-capability-status.md

OLD:
```text
Reviewer behavior and savings reporting retain their separate owners.
```

NEW:
```text
Reviewer behavior retains its separate owner. Plan 12.9 delivers the savings-report contracts at `a88fde8` (§13.13–§13.16), with the qualifications recorded above; ADR-034 remains Proposed and B2/B3 commissioning belongs to #463.
```

### L24 — lld-14-capability-status.md

OLD:
```text
**#397 escalation and timing evidence.**
```

NEW:
```text
**Plan 12.9 evidence and limits.** Production inspection is at `a88fde8`; `reports/plan12-cost-savings/qualification.json` retains separately pinned runs and the operator's conditional "Accept, no rerun" disposition. The Windows full suite at `f1cb559` exited 1: 14 failed, 11,508 passed, 54 skipped and 165 deselected. Required coverage percentages were measured, but the failed run and its refused validation do not establish a passing coverage gate. Later test-double, continuation-publication and manifest corrections retain their focused and revert evidence. The final plain-next correction was not run in Zed or a Windows full suite.

The checked-in Linux qualification concerns `5613c98`. The final publication result is separately reported on #248, comment 6579096728 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/248#issuecomment-6579096728): PR head `f808289`, test merge `c2ec782` into main `99e6ce7`, run 41452867293, 11,272 passed, 318 skipped and 165 deselected. Full-run validation and required product floors passed; formal comparison against main's run 41343980617 exited 0 with all seven safety rows equal. The final report discloses one timing-sensitive non-safety coverage difference from the earlier PR run and does not infer identical skipped tests from equal counts.

Separately, main-push guardrails run 41458258151 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/41458258151) completed successfully at actual merge `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498`. Job `clean-environment-recheck` (125320405517), Linux/Python 3.14.10, reports 11,272 passed, 318 skipped, 165 deselected and 2 warnings. Required floors passed: Optimus 89.7957%, Context Engine 95.9243% and model policy 95.1062%; Evidence Handoff 66.8335% and aggregate 86.4312% are informational. The validity step established full-run validity for session `20261102T140403-3002-56d82c`. Source was clean before and after; active default selection and COMPLETE records retain unsupported Linux native/parent/guard capability. Main-push evidence is separate from the formal PR comparison and establishes no Windows native-guard parity or editor rerun.

`zed-ui.json` reports independent acpx and Zed command/rendering, paging, stale-cursor and outage proof with a synthetic upstream and synthetic costs. It is not provider-billing or realized-savings evidence. D4 authorized zero paid calls; the separately recorded setup incident made 26 unauthorized requests with known cost USD 0.01436675 after attachment to another launch's Gateway. The incident is excluded from proof evidence. That attachment gap remains open and unrepaired, now owned by #465 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/465). The pinned reports' earlier #248 custody is historical; filing the owner did not repair the product.

OC-4 (#463) owns B2/B3 commissioning, producer-owned contracts, paid authority and the deferred native memory-evaluation campaign. Test Strategy §15.8 and §16.1 separate executable checks, reported results and remaining limits. Neither this document nor report delivery closes #248 or establishes general Phase 1 sign-off.

**#397 escalation and timing evidence.**
```

### T2 — test/3

OLD:
```text
| `requires_redis` | Real TimeSeries-capable Redis | No | Persistence and retention |
```

NEW:
```text
| `requires_redis` | Real TimeSeries-capable Redis | No | Persistence and retention |
| `requires_plan12_capture_postgres` | Real released disposable Postgres, with admitted container identity; separate Gateway-keyring setup for credential-boundary cases | No substitute for Postgres | Durable usage capture, report reads, migrations, concurrency and outage behavior (§15.8) |
```

### T3 — test-15-context-evidence.md

OLD:
```text
# 15. Plan 12 claim-to-evidence strategy
```

NEW:
```text
# 15. Plan 12 claim-to-evidence strategy

**Edition scope.** The retained Plan 12.2 strategy and evidence below keep their original pins. The 2026-10-18 ordinary shipping amendment (`docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`) controls unrefreshed Plan 12.2 production and evidence statements. Section 15.8 adds Plan 12.9 and its necessary Plan 12.8 accounting prerequisite, inspected at main `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498`. Plans 12.5–12.7's memory work and the remainder of Plan 12.8 are not refreshed; no historical result is transferred to that pin.
```

### T4 — test-15-context-evidence.md

OLD:
```text
This preserves old evidence, not a new live acceptance.
```

NEW:
```text
This preserves old evidence, not a new live acceptance.

## 15.8 Durable usage capture and cost-savings reporting

### Claims and executable checks

The production contracts are HLD §14.10 and LLD §13.13–§13.16. ADR-032 is accepted by ADR-033; ADR-034 remains Proposed. Test sources at `a88fde8` provide the following checks; their existence alone is not a passing run.

| Claim | Named executable source and discriminating cases | Evidence class |
|---|---|---|
| Canonical actual cost and honest coverage | `tests/unit/optimus_gateway/test_usage_report.py`: duplicate-attempt refusal, unknown cost, missing/open/incomplete epochs, late/conflicting receipts, expected-turn and frontier gaps, unattributed Auto turns, unallocated overhead | Unit |
| Independent B1 arithmetic | Same file: one fully loaded subtraction, signed negative savings, zero baseline without percentage, nested token categories, missing splits/prices, long-context thresholds, independent reference availability and all-stage fixture | Unit |
| Reference and snapshot integrity | `tests/unit/model_policy/test_savings_references.py`, `tests/unit/optimus_gateway/test_usage_price_snapshots.py`: strict configuration, content identities, approved overrides and durable-before-stamp behavior | Unit |
| Read-route contract and bounds | `tests/unit/usage/test_usage_report_contract.py`, `tests/unit/optimus_gateway/test_usage_report.py`, `tests/unit/optimus_gateway/test_server.py`: strict schema, authentication, bounded pages, stable errors, sealed cursors, changed revisions and worker deadlines/cap | Unit/contract |
| Host transport and rendering | `tests/unit/usage/test_savings_report.py`: whole-exchange deadline, slow headers/body, byte bounds, malformed replies, escaping, exact labels and unavailable sections | Unit with local socket checks where required |
| ACP command lifecycle | `tests/unit/acp/test_savings_command.py`: advertisement after `session/new`, local no-turn handling, session/turn continuation, confirmed flush, cancellation, late reads, retirement and teardown | Unit and real-channel composition; not independent-client acceptance |
| Auto attribution through escalation | `tests/unit/acp/test_savings_escalation_capture.py`: one Auto context and each captured classifier/planning receipt counted once | Offline composition; no real-model or campaign claim |
| Durable capture substrate | `tests/integration/usage/test_durable_capture_postgres.py`: pinned migrations, atomic commit, replay, aliases/conflicts, database immutability, concurrency, outage/restart, killed writer and real capture HTTP | Real Postgres tier |
| Consistent report reading | `tests/integration/usage/test_savings_report_postgres.py`: 001-to-002 migration, immutable snapshots, canonical rows, concurrent ingest between/during pages, lock/read deadlines, outage/restart, replaced ledger, capture frontier and production HTTP | Real Postgres tier |
| Gateway-only database credential | Both Postgres files' subprocess boundary cases: provisioned Gateway resolves its keyring credential while the host/test environment has no ledger password | Real Postgres plus real OS keyring and Gateway process |
| ACP compatibility and Zed rendering | Independent acpx and actual editor proof, separately attributed in `reports/plan12-cost-savings/zed-ui.json` | Real protocol/UI dependencies; synthetic costs do not establish real-provider savings |

The all-stage fixture is a reducer-level unit check. Real Postgres report receipt fixtures use planning; they do not prove every production stage against Postgres. Preserve that distinction.

### Selection and prerequisites

`pyproject.toml` excludes `requires_plan12_capture_postgres` from the default marker expression. A green default suite therefore does not exercise it. After the operator releases the disposable resource, an explicit database-tier selection is:

`uv run pytest -q -m requires_plan12_capture_postgres tests/integration/usage/test_durable_capture_postgres.py tests/integration/usage/test_savings_report_postgres.py`

This supplies a marker selection while retaining the repository configuration and root conftest. Record the emitted run mode/reason and actual selected tests; it is focused dependency evidence, not a full-default-suite result or proof of active default-run protection.

The ordinary database fixtures require `P128_CAPTURE_K3_CONFIG` and `P128_CAPTURE_K3_PASSWORD`. The configuration names the released container, image identity, dedicated volume, loopback endpoint, database and role. The fixture inspects the container before connecting. Missing prerequisites skip as UNRUN; no shared, production or another plan's database is an acceptable substitute. These tests can create/drop scratch databases and stop/restart the released container, so resource release is a real prerequisite, not implicit permission from this command example.

Credential-boundary cases require a separate invocation: omit `P128_CAPTURE_K3_PASSWORD`, provision the credential in the Gateway's real keyring namespace, and provide `P128_CAPTURE_K3_CONFIG`, `P128_CAPTURE_K3_ACCOUNTING_ROOT` and `P128_CAPTURE_K3_RUN_ID`. Those cases also carry `requires_os_keyring`; select the intended boundary cases explicitly and retain any skips. A pytest process that possesses the password cannot establish the password-absent boundary.

Record source/configuration identities, exact commands, resource identity, platform, every selected/skipped test, genuine exits and retained evidence. Separate focused database, credential-boundary, full-suite, independent-client and editor runs. Provisioning or running any of them requires its applicable service, credential and interaction authority; this document performs none.

### Acceptance limits

B1 uses the same reported tokens at dated reference prices and is not realized savings or an Auto-off workload. The actual total already includes captured overhead. B2/B3 remain unavailable and require no speculative reader. OC-4 (#463: https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/463) owns their commissioning, producer contracts and paid authority, plus the deferred native memory-evaluation campaign.

Section 16.1 records the reported Plan 12.9 results, failed Windows gate, operator disposition and final paging-fix limitations. No test tier silently substitutes synthetic provider values for a real-provider claim.
```

### T5 — test-16-capability-status.md

OLD:
```text
The sealed cf9bb9d runs therefore remain the latest full-suite evidence cited; no new full-suite, coverage, live-qualification or activation result is claimed.
```

NEW:
```text
The sealed cf9bb9d runs remain historical evidence for that correction. This successor separately records Plan 12.9's later evidence in §16.1; it does not re-pin those old runs, their activation statements or their unresolved obligations. The 2026-10-18 ordinary shipping amendment controls unrefreshed Plan 12.2 material.
```

### T6 — test-16-capability-status.md

OLD:
```text
| OS keyring credential tiers | `requires_os_keyring`, `requires_os_keyring_write` | Deselected in the sealed runs | UNRUN here | Platform-specific; WSL does not establish Windows parity |
```

NEW:
```text
| OS keyring credential tiers | `requires_os_keyring`, `requires_os_keyring_write` | Deselected in the sealed runs | UNRUN here | Platform-specific; WSL does not establish Windows parity |
| Plan 12.9 report arithmetic, coverage, references and ACP lifecycle | Named unit/contract sources in §15.8 | Source inspection at `a88fde8`; separately pinned execution in qualification records | Reported focused/revert checks and qualified Linux PR evidence (§16.1) | Test presence is not a new execution result; final plain-next fix lacks a Zed/Windows-full rerun |
| Durable capture and Postgres report read | `requires_plan12_capture_postgres`; two integration files in §15.8 | Reported database tier at `7cce51c` | 55 passed, 2 skipped; separate boundary checks reported (§16.1) | Default suite deselects the tier; real database fixtures do not cover every production stage |
| Independent ACP and Zed report surface | `zed-ui.json` | Reported proof with real client/editor and synthetic upstream costs | Command, report/paging and outage observations | No realized-savings or provider-billing claim; later delivery fix not rerun there |
| B2/B3 and native memory-evaluation campaign | No qualifying campaign result supplied | OC-4, #463 | B2/B3 unavailable | Requires separate commissioning, producer contracts and paid authority |
```

### T7 — test-16-capability-status.md

OLD:
```text
The deferred route, receipt and editor items keep their existing ownership and were not restarted by this correction.
```

NEW:
```text
The retained deferred route, receipt and editor statements keep their original provenance and are read with the controlling Plan 12.2 amendment; this report successor does not restart those historical checks.

## 16.1 Plan 12.9 reported evidence and qualification

The implementation inspection pin is main `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498`. The execution records below concern their own named sources. `reports/plan12-cost-savings/qualification.json`, `final-run-evidence.json`, `test-exclusions.json` and `zed-ui.json` retain the detailed attribution and limitations; none is replaced by this summary.

**Windows full suite remains failed.** At `f1cb559`, `full-suite-final` exited 1 with 14 failed, 11,508 passed, 54 skipped, 165 deselected and 2 warnings. Its active default-selection context reported COMPLETE records and native valid protection, but the tests failed. The recorded required coverage floors were numerically met; the gate failed and `coverage-validate-final` exited 3. Those measurements are not a validated passing coverage result.

The failures came from a stale configuration double in the Plan 12.5 harness tests. The later double correction was test-only. The subsequent `70c809e` correction was a product change: plain `/savings next` moves only after confirmed report delivery. `6124a90` repaired its logging-surface manifest key. Focused checks and discriminating revert checks cover those changes; the earlier full suite did not execute them. The final product fix was not run in Zed or a Windows full suite.

**Operator disposition.** The operator selected "Accept, no rerun" on 2026-11-02, expressly preserving those limitations and requiring Linux PR CI's full suite/coverage validation plus the formal comparison against main. The checked-in qualification records their earlier successful `5613c98` evaluation, not the final publication run.

**Final Linux PR evidence.** #248 comment 6579096728 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/248#issuecomment-6579096728) reports PR head `f808289` tested at merge ref `c2ec782f8f5912486ee889ee22505e084fc4fbfb` against main `99e6ce7`. Run 41452867293 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/41452867293) produced artifact `product-coverage-c2ec782f8f5912486ee889ee22505e084fc4fbfb-1`: 11,272 passed, 318 skipped and 165 deselected. Bound session `20261102T132659-3011-d247f2` established full-run validity. Required floors passed: Optimus 89.80%, Context Engine 95.92% and model policy 95.11%; Evidence Handoff 66.83% and aggregate 86.43% are informational.

The reported formal comparison against main's run 41343980617 exited 0 with "safety rows comparable, no regression"; all seven safety rows equal main's. Compared coverage SHA-256 values are base `d2a4c441eb5e46a276b5ed8e15cf0a0ab40a78a6dd4afdc40b7e563e4466d95d` and final candidate `58e9c2ec2b100d71a0f15043a6588b59a44e180577b5309519aa16114f8e3f88`.

The final report preserves a timing-sensitive non-safety coverage difference at `src/optimus/acp/spec.py:3070` between the two PR runs. Equal skip counts do not identify identical skipped tests; the retained Windows exclusions inventory does not supply Linux skip identities. Linux records retain their unsupported native-guard-platform qualification and do not establish Windows parity.

**Actual main-push evidence.** Guardrails run 41458258151 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/41458258151), event `push`, completed with conclusion `success` at actual main merge `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498`. Its `clean-environment-recheck` job (125320405517) used Linux and Python 3.14.10. The full default suite reports 11,272 passed, 318 skipped, 165 deselected and 2 warnings, with exit 0.

The job recorded clean source before and after at that exact SHA, active default selection, COMPLETE records and session `20261102T140403-3002-56d82c`. Native, parent and guard capability were unsupported on Linux. Required floors passed: Optimus 89.7957%, Context Engine 95.9243% and model policy 95.1062%; Evidence Handoff 66.8335% remains below its informational threshold, and aggregate 86.4312% is informational. The "Validate the product coverage run" step established full-run validity. Artifact `product-coverage-a88fde86a2ddf382a9bb39a6e2c1a74a1db20498-1` was uploaded.

This main-push result is separately attributable execution evidence. It neither replaces the formal PR-versus-main safety comparison nor changes the failed Windows result, Linux capability qualification or absence of a final Zed rerun.

**Database and boundary evidence.** The qualification records `db-tier-final` at `7cce51c`: 55 passed, 2 skipped, exit 0. Separate `boundary-report-final` and `boundary-capture-final` each report one pass at that source. These are real dependency checks with their own scope, not part of the default full suite. The all-stage fixture was added at reducer level; real Postgres receipt cases use planning. Later host continuation publication does not become a database-tier or editor rerun.

**Protocol/UI proof and incident.** `zed-ui.json` reports independent acpx 0.12.0 and real Zed proof, including advertisement after `session/new`, report rendering/paging, `REPORT_CHANGED`, unavailable-ledger behavior, model work during the outage and delayed delivery after restart. The proof uses a synthetic upstream and synthetic costs; it does not establish actual provider prices, provider billing correctness, matched Auto-off behavior or realized savings.

D4 authorized zero paid calls. A separate setup error attached the host to another launch's real Gateway and caused 26 unauthorized requests, known cost USD 0.01436675. The incident is recorded separately and excluded from proof evidence. The launch-attachment gap remains open and unrepaired, now owned by #465 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/465). The pinned reports' temporary #248 custody is historical; the later transfer does not change the pinned code.

**Remaining custody and authority.** #463 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/463) owns B2/B3 commissioning, producer-owned contracts, paid authority and the deferred native memory-evaluation campaign, including sampled held-out approval. Filing that issue authorizes no campaign. ADR-034 remains Proposed; frozen ADR-012 is unchanged. This successor records qualified evidence and does not close #248 or declare the Phase 1 agent generally working.
```

## docs/README.md

### D1 — HLD edition and scope

OLD:
```text
| [Architecture (HLD) v2.23](Optimus-Cost-Agent-Architecture-v2.23.pdf) | High-level design; ADR-029's single interactive Auto escalation and the host/Gateway timing boundary at `5977155` (2026-10-29), extending v2.22's Auto/registry scope. Carried statements keep their pins. The [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) controls unrefreshed Plan 12.2 material; ADR-024 supplies detection, one nudge and the check-in, extended by ADR-029's one Auto move |
```

NEW:
```text
| [Architecture (HLD) v2.24](Optimus-Cost-Agent-Architecture-v2.24.pdf) | High-level design; Plan 12.9's cost-savings report and its necessary durable-capture/Postgres accounting source at `a88fde8` (2026-11-02), §14.10. Prior EDIT, registry, Auto, escalation and timing pins remain. The [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) controls unrefreshed Plan 12.2 material; Plans 12.5–12.7's memory work is not refreshed. ADR-034 remains Proposed |
```

### D2 — LLD edition and scope

OLD:
```text
| [LLD v2.46](Optimus-Cost-Agent-LLD-v2.46.pdf) | Low-level design; ADR-029's trigger, graph, one-move bound, notices/records, attachment/binder switch and approved application (§13.11), plus the host/Gateway timing contract (§13.12), at `5977155` (2026-10-29). Prior pins remain. The [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) controls unrefreshed material; ADR-024's recovery is extended by ADR-029's single Auto escalation |
```

NEW:
```text
| [LLD v2.47](Optimus-Cost-Agent-LLD-v2.47.pdf) | Low-level design; durable accounting ownership, authenticated usage-report route, ACP `/savings` lifecycle, Auto attribution and reference/snapshot arithmetic at `a88fde8`, §13.13–§13.16. Corrects Redis ledger descriptions and closed route lists. Prior pins and the [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) remain; ADR-034 is Proposed |
```

### D3 — Test Strategy edition and scope

OLD:
```text
| [Test Strategy v1.9](Optimus-Cost-Agent-Test-Strategy-v1.9.pdf) | Testing approach; v1.9 is the capability and evidence correction of 2026-10-15 (reviewed local filing candidate); current Plan 12.2 evidence status is in the [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) |
```

NEW:
```text
| [Test Strategy v1.10](Optimus-Cost-Agent-Test-Strategy-v1.10.pdf) | Testing approach; adds the real Postgres capture/report tier, selection and credential-boundary prerequisites, and Plan 12.9's qualified evidence (§15.8, §16.1). Preserves the failed Windows full suite and later paging-fix limitations; Linux PR evidence at `c2ec782` and successful main-push run 41458258151 at `a88fde8` are separately attributed. Retained Plan 12.2 material is read with the [ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) |
```

### D4 — Continuing amendment scope

OLD:
```text
| [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) | Filed 2026-10-18 Plan 12.2 statements and historical evidence. HLD v2.23 / LLD v2.46 retain v2.22/v2.45's registry, production-construction and Auto refresh, adding ADR-029 escalation and host/Gateway timing. This amendment remains controlling for unrefreshed Plan 12.2 material and retains its Guardrails/evidence/roadmap scope. The frozen amendment and 2026-10-15 correction sources stay unchanged |
```

NEW:
```text
| [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) | Filed 2026-10-18 Plan 12.2 statements and historical evidence. HLD v2.24 / LLD v2.47 retain their earlier registry, production-construction, Auto, escalation and timing refreshes and add Plan 12.9 with its necessary accounting prerequisite; Test Strategy v1.10 adds that report's checks and qualified evidence. This amendment remains controlling for unrefreshed Plan 12.2 material and retains its Guardrails/evidence/roadmap scope. The frozen amendment and predecessor sources stay unchanged |
```

### D5 — Successor sources and predecessor provenance

OLD:
```text
| [#397 escalation successor sources](sources/p397-escalation-successor/) | Codex's replacement text, assembled baseline-keyed sources and filing validation for HLD v2.23 and LLD v2.46; ADR-029 escalation and host/Gateway timing at `5977155` |
```

NEW:
```text
| [Plan 12.9 cost-savings successor sources](sources/plan-12-9-cost-savings-successor/) | Codex's successor text, assembled baseline-keyed sources and filing validation for HLD v2.24, LLD v2.47 and Test Strategy v1.10; scoped report/accounting inspection at `a88fde8`, with separately attributed execution evidence |
| [#397 escalation successor sources](sources/p397-escalation-successor/) | Preserved predecessor text, sources and validation for HLD v2.23 and LLD v2.46 at `5977155`; inputs to the Plan 12.9 successor |
```

### R1 — root README.md documentation table: HLD

OLD:
```text
| [docs/Optimus-Cost-Agent-Architecture-v2.23.pdf](docs/Optimus-Cost-Agent-Architecture-v2.23.pdf) | High-level design; scoped Auto-escalation and host/Gateway timing successor at `5977155` |
```

NEW:
```text
| [docs/Optimus-Cost-Agent-Architecture-v2.24.pdf](docs/Optimus-Cost-Agent-Architecture-v2.24.pdf) | High-level design; cost-savings report and its durable accounting source at `a88fde8`; earlier scoped pins retained |
```

### R2 — root README.md documentation table: LLD

OLD:
```text
| [docs/Optimus-Cost-Agent-LLD-v2.46.pdf](docs/Optimus-Cost-Agent-LLD-v2.46.pdf) | Low-level design; one Auto recovery move and host/Gateway timing contracts at `5977155` |
```

NEW:
```text
| [docs/Optimus-Cost-Agent-LLD-v2.47.pdf](docs/Optimus-Cost-Agent-LLD-v2.47.pdf) | Low-level design; usage-report route, ACP commands, accounting ownership and reference/snapshot contracts at `a88fde8` |
```

### R3 — root README.md documentation table: Test Strategy

OLD:
```text
| [docs/Optimus-Cost-Agent-Test-Strategy-v1.9.pdf](docs/Optimus-Cost-Agent-Test-Strategy-v1.9.pdf) | Testing approach |
```

NEW:
```text
| [docs/Optimus-Cost-Agent-Test-Strategy-v1.10.pdf](docs/Optimus-Cost-Agent-Test-Strategy-v1.10.pdf) | Testing approach; real Postgres report tier and Plan 12.9's qualified evidence, preserving failed Windows and separately successful Linux PR/main gates |
```

## Author notes

- **r3 revision — 2026-11-02, follow-up 2. Verdict on r2's build: accept with fixes.** The fixes are documentary: remove the transient “R2 build/rendering unverified” clause from the Test Strategy `/Subject`, using exactly the builder's existing string; correct the predecessor README citation to `:1–38`, its observed line count; and correct the adjacent predecessor validation-record citation to `:1–59`, also verified on disk. Update the handoff notes to record completed r2 inspection rather than leaving its checks pending. No cover, document-body edit, README edit, OLD anchor, version, label or footer changes from r2. The actual r2 PDF already has the requested corrected subject. No additional document-content or executable-tool fix was found.

- **r2 revision — 2026-11-02, follow-up 1.** Reviewed Claude's unchanged r1 assembly, both tools, predecessor page map, manifests, validation result, all 119 rendered draft pages as contact sheets, and enlarged HLD page 26, LLD page 59 and Test Strategy page 20. Changes from r1: (1) the covers, H18, L17, L24, T7 and custody notes name #465 as owner of the open, unrepaired attachment gap; (2) all three covers, H18, L24, T7, D3, R3 and the evidence notes distinguish successful actual-main run 41458258151 from earlier PR evidence; (3) H10 is shortened to remove the introduced heading-only HLD draft page 3; (4) L10 explicitly qualifies the incomplete seven-route list on the following native-carried endpoint page; (5) notes record predecessor font-metadata drift and the builder-comment finding; (6) unrun/risk prose is kept in the author notes; (7) the Test Strategy subject describes PR/main evidence and #465. R3 removes r2's transient drafting-status clause from that subject. All 56 OLD blocks, versions, the D1 ruling, label and footer remain unchanged.

- **D1 ruling: (a), unchanged.** Cover Plan 12.9 as merged, plus Plan 12.8's durable capture and Gateway-owned Postgres ledger only where the report depends on them or inherited Redis descriptions would otherwise misidentify its accounting source. A bare ADR-032 pointer would leave the writer, credential boundary and report completeness unexplained. A full Plans 12.5–12.8 memory refresh exceeds this commission. No absence-of-memory claim is introduced.

- **Authority.** The operator's 2026-11-02 instruction supplied for this round is, verbatim, “Go ahead”, answering “Go ahead with the Plan 12.9 closure steps?” Its second item commissioned Codex's successor wording against `a88fde8`, Claude's mechanical checks/build, the one-off large-file-hook skip for these PDFs and a stop for separate merge approval. Follow-up 2 commissions read-only r2 build review and r3 wording. No file, branch, worktree, checkpoint log, issue, label, service or plan checkbox was changed by Codex.

- **Checkout identity.** Inspected `C:\worktrees\optimus-cost-agent-worktrees\optimus-cost-agent-wt-claude-p129doc`, branch `agent/claude/plan12-9-design-docs`, HEAD `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498`. Parents remain `99e6ce7fda20e2a468ef4ce3b17b613e6998f2ad` and `f808289b5d0ebf377538e7b72b94e9c3ffca8a29`; merge time is 2026-11-02T14:02:48Z. The r1 authoring pass reported a clean checkout. Both follow-ups' initial/final status report only Claude's untracked `docs/sources/plan-12-9-cost-savings-successor/` bundle. Git's inaccessible-global-ignore warning remains disclosed.

- **Predecessors and source custody.** `docs/sources/p397-escalation-successor/README.md:1–38`, `docs/sources/p397-escalation-successor/validation-record.md:1–59` and its `sources/successor-edits.md` establish predecessor format and provenance. The supplied HLD v2.23, LLD v2.46 and Test Strategy v1.9 hashes and all three native-baseline hashes independently match the filed PDFs. Preserve those PDFs and source bundles unchanged; archive the superseded PDFs during authorized filing. Test Strategy's predecessor is the `test` dictionary in `docs/sources/capability-evidence-correction/sources/page-updates.json`. That bundle's `tools/build_corrections.py:40–64`, `:297–328` establishes native v1.7 and its generated cover.

- **Independent r1 assembly check.** Replayed all 56 OLD/NEW blocks in memory, requiring exactly one OLD occurrence at each sequential application. All 48 document blocks reproduce the assembled page dictionary and six appended Markdown files exactly; the eight README blocks pass a sequential dry run against the unchanged READMEs. No source file was written. Follow-up 2 separately repeated these checks against r2 as recorded below.

- **Independent r1 PDF check.** Draft and repeat PDFs are byte-identical and match their manifest hashes: HLD, 30 pages, `8e988eeb519d5b7daaf1bd5ff1046de6cbf33267f9b07058e1e492c3361ac69f`; LLD, 64 pages, `090f1ba4d255e6b5a5dd986e7df4b2efe033f36eb82efe9cc6939b66607ffe8e`; Test Strategy, 25 pages, `c8a4532ec7e9b58ba3d5faab360473fdbb8b82b2323720c2a7b1003a811b1141`. Independently matched all 51 ordered cover/replaced/appended source groups to normalized rendered text, accounting for Markdown formatting, diagram drawing order and repeated table headers. The 22 native-carried bodies—HLD 1, LLD 17, Test Strategy 4—match their filed predecessor bodies. Physical page mappings are contiguous, and predecessor maps match reconstruction manifests. Claude's filed `document-validation.json` reports all ten checks true for each document; it was read, not rerun because its driver writes that record.

- **Independent r2 assembly and PDF check.** Replayed all 56 blocks again, with exactly one OLD at every sequential application and a passing README dry run. The assembled page dictionary, six appended files and all three covers match r2's authored text exactly. All manifest/source/PDF hashes checked match. R2 identities are: HLD, 29 pages, `cfd627f2cc5c3c026072940590f535a8c65c282c26fd19f0ed14893e6f3852c5`; LLD, 64 pages, `e8e42bb59dcdcfe17f297ad968854950e8bca3babfaad440221ef1a649ba0d51`; Test Strategy, 26 pages, `e9346917c705099631d3b171fa70da130ad17619e496802675701ec8b0bab95a`. Independently matched the same 51 ordered source/render groups—14 HLD, 25 LLD, 12 Test Strategy—and all 22 native carries, with contiguous mappings. No unexplained normalized text difference remained. Claude's r2 validator record reports every check true for all three documents. No r2 repeat-build determinism claim is made from the single supplied r2 build directory.

- **Visual review and H10/L10 disposition.** R1's contact sheets covered all 119 pages. Follow-up 2 inspected the supplied r2 HLD page 3, LLD page 2 and Test Strategy page 17 images, and independently rendered HLD page 2, LLD page 5 and Test Strategy page 26 in memory. H10's correction works: the trailing “5. Request-Level Cost Attribution” heading is back on HLD page 2; page 3 contains §5A rather than an otherwise empty heading page. The HLD page 3 accounting table is intact. LLD page 2 shows all ten routes; page 5 explicitly qualifies the following native-carried seven-route page. Its table and flow remain legible. Test Strategy page 26 contains the continued custody/evidence text without observed body overlap. No further body or layout correction is requested.

- **Predecessor environment difference — accepted with recorded qualification.** Follow-up 1 independently confirmed that reconstructed HLD v2.23, LLD v2.46 and Test Strategy v1.9 are respectively 9, 15 and 7 bytes smaller than the filed PDFs, with equal page counts and identical extracted text on every page. Inspection of decoded PDF objects localizes differences to embedded TrueType font objects: 55 HLD, 111 LLD and 45 Test Strategy objects. Every differing font's changed tables are limited to `head` and `name`; inspected name records change from Version 7.06 to Version 7.07. All other decoded objects compare equal, and other font tables—including glyph/metric data—compare equal. This identifies font metadata drift rather than unexplained document content drift; it is not a claim that the Python/zlib difference caused it. The maps are acceptable. Preserve filed predecessor hashes and record the actual build/font environment and reconstruction hashes; do not call the reconstruction byte-identical.

- **Findings for Claude.** The prior builder-comment finding is resolved at `docs/sources/plan-12-9-cost-savings-successor/tools/build_successors.py:51–53`: the comment now correctly distinguishes page-count/text equivalence from byte equality and names font-version drift. Its Test Strategy `PDF_SUBJECT` already equals r3's exact string, and the actual r2 PDF metadata matches it. No executable-tool change is required. File r3's corrected notes and build string, refresh the authored-text identity in the final manifest, and retain the corresponding final validation and required repeat-build receipt. Keep r1 and r2 evidence separately attributed; do not present their hashes as newly built r3 results.

- **Page-key map.** Changed HLD native keys are `2`, `3`, `4`, `7`, `9`, `10`, `11`, `12`, `13`; changed LLD keys are `2`, `3`, `4`, `33`, `38`; changed Test Strategy key is `3`. Relevant source locations are `docs/sources/p397-escalation-successor/sources/page-updates.json:3–13`, `:16–24`, and `docs/sources/capability-evidence-correction/sources/page-updates.json:41`. These are native keys, not rendered page numbers. L10 qualifies the native-only endpoint page from adjacent replaced `lld/4`; L13 qualifies carried §10.1/§10A from adjacent replaced `lld/33`.

- **Appended-source anchors.** HLD anchors are `docs/sources/p397-escalation-successor/sources/hld-14-context-engine.md:3`, `:44`, `:97`; `hld-15-capability-status.md:5–9`, `:21`, `:40`, `:45`. LLD anchors are `lld-13-context-integration.md:3`, `:223`; `lld-14-capability-status.md:5–20`, `:47`, `:74`. These four leaf paths are relative to that bundle's `sources/`. Test Strategy anchors are `docs/sources/capability-evidence-correction/sources/test-15-context-evidence.md:1`, `:60–68`, and `test-16-capability-status.md:3`, `:29–31`. Existing §15.7 is retained; the new strategy section is §15.8.

- **Additional stale statements corrected.** HLD §10.D's attribution arrow also identified RedisTimeSeries as the ledger. HLD step 8, telemetry description and configuration views receive matching qualifications. The LLD's seven-route list omitted decisions and usage capture as well as usage report; §0/§D now lists the ten pinned POST routes. The retained `UsageAccountingService` and `EvidenceLedger` descriptions are labelled as component contracts, not production ACP settlement. HLD/LLD coverage references point to Test Strategy v1.10 without changing its inherited policy.

- **Decision and scope authority.** `docs/decisions/README.md:299`, `:319–321` distinguishes ADR-012's accepted requirement, ADR-032's acceptance by ADR-033 and Proposed ADR-034. `docs/decisions/ADR-005-cost-alerts-not-limits.md:68–93` preserves alerts-only policy and independent evaluation authority. `docs/decisions/ADR-012-cost-savings-report.md:40–79`, `:82–97` supplies B1–B4, one subtraction, negative/incomplete disclosure and open items. `docs/decisions/ADR-034-cost-savings-report-read-and-presentation.md:3–12`, `:30–37`, `:43–64`, `:66–106`, `:108–125` supplies D1–D4, mechanism, references, snapshots, command forms and separate acceptance. No frozen ADR is edited or assigned a new status.

- **Controlling amendment.** `docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md:3–21`, `:23–37` retains control of unrefreshed Plan 12.2 policy and evidence. Its dated candidate, model configuration and work-status statements are not promoted to new current-state claims. The predecessor's EDIT/Auto/escalation/timing pins remain intact. No full amendment fold-in, Guardrails rebuild, general Plan 12.3 refresh or memory architecture refresh is attempted.

- **Durable substrate and credentials.** `docs/decisions/ADR-032-durable-usage-capture-and-gateway-drain.md:7–18`, `:20–53`, `:63–68` establishes ownership, outboxes, epochs, acknowledgement, configuration and limitations. `docs/decisions/ADR-033-accepts-adr-032-durable-usage-capture.md:3–14`, `:39–46` establishes effective acceptance without changing ADR-032. `src/optimus/acp/__main__.py:897–927`, `:993–996`; `src/optimus/acp/bootstrap.py:66–76`, `:135–158`, `:345–352`; `src/optimus/usage/capture_delivery.py:1–7`, `:30–62`; and `src/optimus_gateway/usage_capture.py:192–233` establish composition, delivery, negotiation and Gateway-only credential resolution. `src/optimus_security/accounting_config.py:1–29` identifies non-secret configuration, reference override binding and keyring namespace.

- **Redis qualification.** `src/optimus/acp/bootstrap.py:138–158` constructs Redis agent state and telemetry fanout. `src/optimus/telemetry/redis_sink.py:31–56` distinguishes event-driven telemetry and its retained settled-usage handler. ADR-032 `:9–11` explicitly records that `UsageAccountingService` and the Redis settled-usage sink are not production-wired. These facts support retaining Redis state/telemetry while removing its identification as the report ledger; they do not justify changing the separate memory design.

- **Route, bounds and reads.** `src/optimus_gateway/server.py:44–50`, `:145–151`, `:215–262` supplies route registration, authentication-before-body, framing and read/write bounds. `src/optimus_security/usage_report_contract.py:1–17`, `:32–91`, `:156–225`, `:228–257`, `:262–312` supplies schema, bounds, labels, codes, cursor rules and response validation. `src/optimus_gateway/usage_store.py:167–199`, `:201–260` supplies read-only repeatable-read, deadlines, migration verification, canonical facts and frontier checks. `src/optimus_gateway/usage_report.py:305–355`, `:355–407`, `:420–474` supplies request/revision binding, pagination, process-key lifetime, worker slots and errors. The report reader does not migrate.

- **Arithmetic and provenance.** `src/optimus_gateway/usage_report.py:97–132`, `:140–221`, `:225–229`, `:324–380` supplies unique attempts, known/unknown totals, category pricing, independent columns, Auto scope, unavailable B2/B3 and sourced B4. `src/optimus_model_policy/savings_references.py:1–13`, `:42–80` supplies independent strict configuration and price units. `src/optimus_model_policy/savings_references.yaml:11–48` holds dated configuration; model identities remain data, not design elements. `src/optimus_gateway/usage_price_snapshots.py:1–10`, `:65–90`, `:101–135`, plus `src/optimus_gateway/responses.py:383` and `src/optimus_gateway/decisions.py:130`, supplies content identities and durable-before-stamp behavior. Registry price provenance is not falsely described as dated when its date is absent.

- **Attribution and ACP lifecycle.** `src/optimus/usage/durable_capture.py:123–152`, `src/optimus/usage/turn_settlement.py:209–221` and `src/optimus/acp/spec.py:1868–1876` establish explicit Auto/fixed context and host scope. `src/optimus/usage/savings_report.py:30–39`, `:93–108`, `:118–193`, `:199–253`, `:259–313`, `:316–360`, `:367–414` establishes forms, transport, validation, continuation and rendering. `src/optimus/acp/spec.py:1336–1426`, `:1723–1727` establishes local no-turn handling, send custody, confirmed flush and post-response advertisement. Advertisement is attempted, not guaranteed.

- **Executable checks inspected.** Sources include `tests/unit/optimus_gateway/test_usage_report.py:44–175`, `:235–246`, `:249–328`, `:356–407`, `:441–491`; `tests/unit/acp/test_savings_command.py:84–108`, `:179–282`, `:359–406`, `:444–627`; `tests/unit/usage/test_savings_report.py:173–240`, `:252–359`; `tests/unit/optimus_gateway/test_usage_price_snapshots.py:48–154`; and `tests/unit/acp/test_savings_escalation_capture.py:89–127`. These identify arithmetic, provenance, transport and delivery-aware continuation checks. They were inspected, not executed here. The all-stage reducer fixture remains distinct from planning-only real-Postgres fixtures.

- **Postgres tier and prerequisites.** `pyproject.toml:50–79` supplies default deselection and the marker. `tests/conftest.py:14–32` preserves run-context/profile plumbing. `tests/integration/usage/test_durable_capture_postgres.py:1–7`, `:36–59`, `:96–236`, `:328`, `:621`, `:713`; and `tests/integration/usage/test_savings_report_postgres.py:1–9`, `:44–91`, `:189–377`, `:408–455`, `:461–600` establish resource admission, destructive resource operations, readback/concurrency/outage cases and password-absent boundary prerequisites. The §15.8 command is a future selection, not an executed run or resource-start instruction.

- **Evidence qualification checked.** `reports/plan12-cost-savings/manifest.json:113–121` supplies F8/F9. `qualification.json:6–15`, `:18–48`, `:90–104`, `:180–203`, `:245–309`, `:346–370`, `:372–429`, `:485–552` preserves failed Windows evidence, deltas, focused/revert results, operator disposition and earlier Linux comparison. `reports/plan12-cost-savings/zed-ui.json:10–22`, `:25–90`, `:610–646` separates protocol/UI proof, synthetic costs and the incident. Raw screenshots and sealed external run bundles were not revalidated.

- **Final PR evidence and later custody.** #248 comment 6579096728 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/248#issuecomment-6579096728) supplies `c2ec782` identities, counts, validation, comparison hashes and timing-sensitive coverage difference, separately from checked-in `5613c98`. #248 comment 6579177133 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/248#issuecomment-6579177133) and #463 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/463) establish OC-4 custody. Follow-up 1 independently read #465 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/465): it is the filed owner of the open attachment gap and expressly says the changed-port rerun was not a product fix. This later issue state supplements older custody wording at the code pin. PR #464's proposed report updates are not treated as changes to `a88fde8`.

- **Actual main-push CI — follow-up 1 verification.** Attempted exactly `gh run view 41458258151 --repo vibhanshu-agarwal/optimus-cost-agent --json status,conclusion,headSha`; it failed before network access because the sandbox could not read `C:\Users\pc\AppData\Roaming\GitHub CLI\config.yml`. Used the read-only GitHub connector instead. The final run GET in follow-up 1 confirmed event `push`, status `completed`, conclusion `success` and head SHA `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498`, updated 2026-11-02T14:31:10Z. Independently read job 125320405517 and its decoded log: actual checkout, Python 3.14.10, Ruff success, full-suite exit 0/counts, required floors, clean before/after source, active default selection, COMPLETE records and unsupported Linux native/parent/guard capability. The validity step explicitly says `coverage-products: full-run validity established` for session `20261102T140403-3002-56d82c`. The artifact upload is recorded; its archive was not downloaded and no new formal safety comparison was run. Follow-up 2 preserves that completed result without rerunning the workflow. The main result remains separate from PR CI and the failed Windows gate.

- **Indexes and filing destination.** `docs/README.md:17–23` and `README.md:1077–1079` supply predecessor rows. D1–D5 apply to `docs/README.md`; R1–R3 apply to root `README.md`. Claude's current untracked bundle is `docs/sources/plan-12-9-cost-savings-successor/`. Its index row applies when that bundle and final validation are filed; it is not a claim that Codex wrote them.

- **Inspection mechanics and retained failed attempts.** Read-only PDF extraction used installed `pdftotext`; in-memory comparison used directly invoked Python 3.12.13 with standard-library modules, distinct from Claude's reported Python 3.14.4/zlib-ng build environment. The default Python launcher and another worktree's venv executable were unavailable under sandbox permissions, and the direct inspection interpreter had no pypdf. No dependency was installed. Preliminary follow-up 1 comparisons exposed shell encoding, title parsing and layout-order differences; corrected comparisons preserve ordered source text and account explicitly for renderer transformations. Rendering used Windows' PDF API and memory streams, without writing images or opening an editor. An attempted bounding-box extraction in follow-up 2 was unsupported by the installed Xpdf `pdftotext`; no bounding-box result is claimed.

- **Build handoff and remaining risk.** Preserve native keys, carried bodies, source pins and historical evidence. R1's 30/64/25 and r2's 29/64/26 page counts and hashes belong to those builds. R3 changes no rendered body or cover, and its corrected subject already matches the actual r2 metadata; final manifest provenance must nevertheless identify the filed r3 text. No product suite, Ruff, container/Docker operation, Zed session, paid call or GitHub write was run here. No final r3 filing build or r2 repeat build was executed by Codex. The attachment defect remains open under #465; this review grants no general Phase 1 sign-off, ADR acceptance or merge approval.

## Build strings

- Page-header `LABEL`: `LOCAL FILING - NOT ACTIVATED`
- Footer for all three: `Cost-savings report | 2026-11-02`
- HLD PDF `/Title`: `Optimus - Architecture (HLD) v2.24 - Cost-savings report (local filing - not activated)`
- LLD PDF `/Title`: `Optimus - Low-Level Design v2.47 - Cost-savings report (local filing - not activated)`
- Test Strategy PDF `/Title`: `Optimus - Test Strategy v1.10 - Cost-savings report (local filing - not activated)`
- HLD PDF `/Subject`: `Plan 12.9 cost-savings report and necessary durable-capture/Postgres accounting corrections at main a88fde86a2ddf382a9bb39a6e2c1a74a1db20498; prior pins and controlling unrefreshed Plan 12.2 amendment preserved. Qualified evidence; ADR-034 Proposed. Local filing; publication to main requires separate operator approval.`
- LLD PDF `/Subject`: `Usage-report route, ACP savings commands, durable accounting ownership, Auto attribution and independent reference/snapshot contracts at main a88fde86a2ddf382a9bb39a6e2c1a74a1db20498; earlier contracts and evidence retain their pins. ADR-034 Proposed. Local filing; publication to main requires separate operator approval.`
- Test Strategy PDF `/Subject`: `Real Postgres capture/report tier and Plan 12.9 evidence at main a88fde86a2ddf382a9bb39a6e2c1a74a1db20498; failed Windows gate and separately attributed successful Linux PR/main CI preserved. Local filing; publication to main requires separate operator approval. Open Gateway attachment gap owned by #465.`