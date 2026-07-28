# Plan 11.5: P11-FEAT-GATEWAY-COST-OBS Design Specification

**Status:** Draft for user/reviewer review. Implementation planning, source/test mutation,
charter mutation, PDF regeneration, commit, push, and release claims remain unauthorized by this
document.

**Stable feature:** `P11-FEAT-GATEWAY-COST-OBS`.

**Plan number:** 11.5, assigned as the next unused Plan 11 single-decimal slot at pickup. Branch:
`agent/codex/plan-11-5-gateway-cost-obs`, based on `origin/main` at `67621c0`.

**Scope:** This slice owns the corrected OTel/OTLP-to-Phoenix path, provider-native settled-usage
reconciliation and persistence, RedisTimeSeries accounting schema, Plan 7 telemetry compatibility,
and the separately reviewed USD-visible field migration. It does not reopen Plan 11.4 request-path
validation or the merged `ProviderMessageResult` contract.

## 1. Authority and source digests

The 2026-07-27 architecture correction merged by PR #89 is the corrective authority over the stale
2026-07-25 charter wording. The charter correction is an explicit Plan 11.5 work item; this spec
does not silently treat the stale wording as a live requirement.

All hashes below are blob-level SHA-256 digests computed from committed `HEAD` with
`git show HEAD:<path> | sha256sum`, not from working-tree files.

| Source | Committed path | Blob SHA-256 | Use in this design |
|---|---|---|---|
| HLD v2.16 | `docs/Optimus-Cost-Agent-Architecture-v2.16.pdf` | `6c2c98fe2327a6c466cad3eb1800335eb59f0e1f65b2cb8e1e3401d7cfa05801` | One-key boundary, Gateway accounting, trace ingress, Phoenix/OTLP, no LangSmith/amortized charge |
| LLD v2.39 | `docs/Optimus-Cost-Agent-LLD-v2.39.pdf` | `82513729fd1a6e87fad310dd90a18c996981b68024204e56cca65377495585de` | GatewayUsage/ProviderUsage, USD rename, RedisTimeSeries, trace delivery and evidence tiers |
| Guardrails v1.1 | `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf` | `27ef0657ccec5568d3e3769c7320223d1bfe3cf6f4702564cbd0a8a391f11029` | Same Gateway/ledger/OTLP path for evaluators; no second cost path; USD budget-field semantics |
| Test Strategy v1.5 | `docs/Optimus-Cost-Agent-Test-Strategy-v1.5.pdf` | `f3d744ec175b1e18e8b1e4e271997a0bb1266cc33ca7154a40bf5298588da8d` | Real dependency tiers, reconciliation, trace evidence, ACP/golden/release gates |
| Plan 11 charter | `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md` | `d0390e7d17705edb9f7d6fd69ccb9865df792c4c10c7dffdc233a3a5e58b6807` | Scope/sequencing authority, with two stale COST-OBS phrases corrected by a named task |
| Deferred backlog | `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | `5eda59a0a5b7189014e697e99b8b64284e7d5f428ecd45be89aee5295b5844ad` | Feature custody: OTel/OTLP-to-Phoenix and separate USD migration |
| Deep requirement inventory | `docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md` | `c0c9df817473d480005d342c5ee926fa6307100f6a1d13afb2396024eef08aa0` | Row-level evidence aliases and ownership map |

The inventory digest above is recorded exactly from the committed blob as
`c0c9df817473d480005d342c5ee926fa6307100f6a1d13afb2396024eef08aa0`; the visual line wrap in
this document must not be interpreted as a different digest.

### 1.1 Frozen merged contracts

These code blobs were independently hashed at the same baseline and are consumed as given unless a
reviewer approves the one explicit legacy-credit removal called out below.

| Contract | Path | Blob SHA-256 |
|---|---|---|
| `GatewayUsage` / parser | `src/optimus/gateway/models.py` | `80d2152799053bf72e35dad57e29bb1d0ec8b2782ba86d8390aa0d97482215b2` |
| `ProviderMessageResult` / upstream parser | `src/optimus_gateway/upstream_client.py` | `12641002016b5cc38f93e84b703b0f8c8b43c334f20588a15a5cca840fd1e946` |
| Gateway response construction | `src/optimus_gateway/responses.py` | `9d9d9e69facc9adaad5d2197da237c65c56f99d834ee859c1b0c36fdb8eba7d7` |

`ProviderMessageResult` remains unchanged. Plan 11.4's request-path malformed-usage rejection also
remains unchanged. COST-OBS owns only the settled-usage handoff, persistence, reconciliation, and
evidence after that rejection boundary.

## 2. Corrective charter task

The implementation plan must include a small documentation task that changes both stale charter
locations:

- the capability partition at charter lines 39-40; and
- the `P11-FEAT-GATEWAY-TOOLS and P11-FEAT-GATEWAY-COST-OBS` paragraph at charter lines 100-102.

The replacement must say that COST-OBS owns provider-native usage persistence and reconciliation,
the wire-aware USD field migration, authenticated structured **agent-to-Gateway trace ingress**,
Gateway validation/redaction and OTel/OTLP export with Phoenix as the local default, Plan 7
telemetry compatibility, and observability-field compatibility. It must state that trace export
has no allocated or amortized per-request charge and that LangSmith is not part of the architecture.
The word "authenticated" must attach to agent-to-Gateway ingress, not to the Gateway-to-Phoenix
OTLP leg.

## 3. Requirements traceability and custody

The following is the COST-OBS-owned subset of the committed deep inventory. It is independently
checked against the four frozen PDFs; the inventory remains the row-level acceptance source.

| Source rows | Requirement carried into Plan 11.5 | Custody/evidence |
|---|---|---|
| HLD v2.16 §5A p.3, rows 4 and 7-8 | Aggregator-reported normalized USD usage is the settled accounting source; package/OSV are free public calls; trace export carries no invented request charge. | Usage reconciliation and trace separation; E4/E5 |
| HLD v2.16 §11 p.10, rows 6, 8-9 | Validated `GatewayUsage` returns provider cost/usage; usage attribution retains run, session, request, Gateway-request, and provider-request IDs; structured trace ingress maps to OTel/OTLP. | E2/E4/E5 |
| HLD v2.16 §11A p.12, all 5 rows | OTel/OTLP is vendor-neutral across planning, Gateway calls, tools, validation, retries, and final response; ingress is validated/redacted; Phoenix is the local default; no allocated/amortized charge; required attributes and redaction are retained. | E5 |
| HLD v2.16 §10.D p.9 | Gateway usage flows through EvidenceLedger and RedisTimeSeries for per-run audit. | E4/E5 |
| HLD v2.16 §12 p.12 | OTel/OTLP evidence is separate from 80% code coverage and LangSmith is absent. | E5/E9 |
| LLD v2.39 §0.A p.4, COST-OBS rows | Model accounting retains aggregator/provider/model, token/cache detail, provider-reported billing units/cost, IDs; trace delivery records state/trace IDs without charge; USD rename removes legacy credit-named fields without adding cross-run policy. | E4/E5/E12 |
| LLD v2.39 named block p.5 | Trace route is `POST /v1/observability/traces`; path is authenticated ingress -> Gateway validation/redaction -> OTel/OTLP -> Phoenix; no MCP route is inferred. | E5/E7 |
| LLD v2.39 §6 p.20 row 9 | CORE owns request-path fail-closed enforcement; COST-OBS owns settled usage/cost reconciliation, persistence, and release evidence. | E2/E4/E6 split custody |
| LLD v2.39 §6.1 p.21 row 11 | CORE validates/rejects malformed provider accounting; COST-OBS owns the settled GatewayUsage/ledger contract and reconciliation evidence. | E2/E4 split custody |
| LLD v2.39 §9D p.30 | Missing, malformed, negative, or unparseable provider cost cannot reach dispatch or ledger acceptance. | E4/E8, preserved CORE boundary |
| LLD v2.39 §9E p.31 | Evidence entries carry evidence/run/session/request/Gateway/provider IDs, provider/model/version, cache, billing units, USD cost, provenance, trust, policy reason, and timestamp. | EvidenceLedger schema and E4 |
| LLD v2.39 §9E.1 p.32 | Define the USD field, decide compatibility, update schemas and independent client evidence, prove old credit field retirement, preserve USD semantics, and add no cross-run policy. | ACP/golden/acpx and E12 |
| LLD v2.39 §10 p.33 | UsageAccountingService accepts only validated GatewayUsage/ProviderUsage; rejects missing/null/negative/malformed cost; price snapshots are diagnostic only; required identity is preserved. | Provider usage service and E4 |
| LLD v2.39 §10.1 p.34 | RedisTimeSeries uses 30-day `cost_usd` and `billing_units` series, non-destructive `TS.ALTER`, and duplicate-request idempotence/rejection; trace export is not billable. | Redis integration and E4/E5 |
| LLD v2.39 §10A p.35 | ProviderUsage is the persisted superset of GatewayUsage with reconciliation attribution; Gateway validates/redacts/maps/exports traces and records delivery state/trace IDs; Phoenix is default; no amortized trace charge. | E4/E5 |
| LLD v2.39 §11.1 p.37 | Persist Decimal-safe cost/units and IDs; export real OTLP to Phoenix; prove no LangSmith key/dependency/egress; record validation/retry/tool-policy/final disposition. | Release evidence E4/E5/E7/E9 |
| LLD v2.39 §11A p.38 | Test Strategy is authoritative; Redis and Phoenix tiers use real dependencies; ACP uses independent `acpx`; LangSmith/amortized accounting are deleted. | E5/E9/E11 |
| Guardrails v1.1 §7.2 p.10 | Per-iteration evidence and `max_budget_usd` use provider-reported USD; rename does not add cross-run policy. | E4/E12; no budget-enforcement scope |
| Guardrails v1.1 p.11 and §9 p.12 | Evaluator uses the same Gateway, USD ledger, and OTel/OTLP path; malformed usage/cost fails closed; no second ungoverned cost path. | E2/E4/E5 |
| Test Strategy v1.5 §2 p.2 | Provider-reported usage/cost attribution and real Phoenix OTLP export are in scope; cross-run spend policy is out of scope. | E4/E5/E12 |
| Test Strategy v1.5 §7.1 p.6 | Missing/malformed usage/cost fails closed; permanent failures do not retry; transient attempts are bounded and recorded. | E4/E6, CORE mechanism preserved |
| Test Strategy v1.5 §8A p.8 | Real Phoenix evidence must prove attributes, correlation, parent/child relationships, redaction, batching/retry, validation/policy, and final disposition; Phoenix is not an API dependency. | E5 |
| Test Strategy v1.5 §9 p.9 | Budget abort records USD cost; exhausted runs flush partial telemetry; malformed accounting has no side effects. | E4/E5/E6 |
| Test Strategy v1.5 §11 p.10 | Provider cost is attributable; logs/traces retain field names while redacting secrets; golden evidence uses real dependencies and independent `acpx`. | E5/E9/E11 |
| Test Strategy v1.5 §12 p.11 | Golden tasks record usage, Gateway/provider IDs, trace identity, delivery state, and final disposition; trace failure cannot silently count as success. | E4/E5/E11 |
| Test Strategy v1.5 §13 p.12 | Release requires response/ledger/TimeSeries cost reconciliation, real OTLP spans to Phoenix with redaction, and no LangSmith/amortized charge. | E4/E5/E9 |

The three split-custody rows are not reimplemented: CORE's existing request-path enforcement remains
the first gate, and COST-OBS consumes only settled accepted usage for persistence/reconciliation.

## 4. Design goals and explicit exclusions

### Goals

- Keep the one-key local-first Gateway architecture and all vendor credentials Gateway-side.
- Make provider-reported `cost_usd` and provider-native `billing_units` the only settled charge data.
- Persist complete attribution and prevent duplicate charges by `gateway_request_id`.
- Make the ACP-visible field contract USD-named and remove credit-named runtime surfaces.
- Export authenticated structured agent-to-Gateway trace ingress through vendor-neutral OTel/OTLP to
  Phoenix by default, with explicit delivery state and no observability charge.
- Produce evidence at the named real dependency tiers and preserve the 80% coverage gate.

### Explicit exclusions

- No new provider adapter, `ProviderMessageResult` field, direct agent egress, hosted Gateway, or
  Phoenix control-plane API dependency.
- No change to Plan 11.4 request-path retry/fail-closed behavior or typed tool behavior.
- No `P9.85-FU-3` cross-run or cross-session budget policy. Renaming `max_budget_credits` and
  `remaining_budget_credits` to USD semantics preserves current behavior and introduces no new
  budget enforcement.
- No LangSmith dependency, key, endpoint, assertion, or amortized per-request charge.
- No MCP route, registry work, Zed work, search replacement, or Plan 12 context optimization.

## 5. Architecture

### 5.1 Settled usage path

The settled path is:

`ProviderMessageResult` -> existing Gateway request-path validation -> `GatewayUsage` response ->
caller context enrichment (`run_id`, `session_id`, `request_id`, service/native unit) -> immutable
`ProviderUsage` record -> idempotent append-only store -> RedisTimeSeries cost/unit points ->
EvidenceLedger join on `gateway_request_id` -> reconciliation report and telemetry event.

`ProviderMessageResult` and its parser are consumed unchanged. `GatewayUsage` remains the wire-level
envelope and its provider fields are copied verbatim. The current `ProviderUsage.from_gateway_usage`
requirement for `service`, `native_unit`, `optimus_credits_debited`, and `price_snapshot_id` is
replaced by a caller-supplied persistence context for service/native unit. `price_snapshot_id`
remains optional diagnostic metadata. The legacy `optimus_credits_debited` field is removed only as
part of the explicit USD migration task; it is not replaced with an estimate.

The persisted record contains:

- run/session/request/Gateway/provider request IDs;
- aggregator provider and optional actual resolved provider;
- requested alias, resolved model, and model version;
- cache state and token/cache detail when returned;
- provider-native billing units;
- Decimal-safe provider-reported `cost_usd`;
- service/native unit supplied by the call context; and
- optional diagnostic price snapshot identity.

### 5.2 Idempotent ledger and RedisTimeSeries

The provider-usage store keys the append-only record by `gateway_request_id`. Repeating an identical
record is idempotent; a second record with the same ID but different accounting or attribution is
rejected before a second charge is written.

For each accepted request, the Redis integration maintains:

```text
TS.CREATE optimus:usage:<run_id>:cost_usd
  RETENTION 2592000000
  LABELS run_id <run_id> metric cost_usd

TS.CREATE optimus:usage:<run_id>:billing_units
  RETENTION 2592000000
  LABELS run_id <run_id> metric billing_units
```

Existing series are aligned with `TS.ALTER` without dropping measurements. The reconciliation
invariant is:

```text
Gateway response cost_usd
  == ProviderUsage.cost_usd
  == EvidenceLedger cost_usd when evidence-producing
  == RedisTimeSeries appended cost_usd
```

The same invariant applies to provider-native billing units. Free package/advisory operations record
zero units and zero USD without inventing vendor charges.

### 5.3 OTel/OTLP trace path

The agent retains the authenticated `POST /v1/observability/traces` ingress path. The ingress batch
is structurally typed and carries schema version, batch identity, event identity, trace identity,
parent identity, run/session/request IDs, event kind, timestamps, and event payload. Model, tool,
retry, validation, policy, error, and final-disposition events retain the required cost/provider,
policy, retry, and failure attributes.

The Gateway performs this sequence:

1. authenticate the agent bearer token;
2. validate batch and correlation shape without executing or promoting event content;
3. redact credentials and sensitive content while retaining field names and redaction reasons;
4. map accepted events to OTel spans/events with parent/child relationships;
5. export through the vendor-neutral OTLP exporter; and
6. record `gateway_request_id`, trace IDs, batch ID, delivery state, retry count, and final
   disposition.

The implementation uses the OpenTelemetry SDK plus OTLP HTTP/protobuf exporter. Phoenix is a default
OTLP destination, not an instrumentation dependency. The Gateway-only endpoint configuration is
`OTEL_EXPORTER_OTLP_ENDPOINT`; the agent receives no OTLP or Phoenix credential. A missing endpoint
is an explicit not-configured delivery state, not a successful no-op.

The ingress response never contains `gateway_usage`, `billing_units`, or `cost_usd`. Trace delivery
is operational telemetry and is not added to any usage ledger.

### 5.4 Delivery and failure semantics

- Invalid authentication or malformed batch: fail closed with a sanitized error and no partial
  export.
- Valid batch with exporter unavailable: record `queued`/`failed` state and retry according to the
  bounded telemetry retry policy; never fabricate a cost or claim delivery.
- Successful export: record `delivered` with trace and batch identities.
- Runtime trace failure does not invent a model failure or undo a completed mutation, but the final
  run and golden evidence expose the failed delivery state. Release and trace-live gates fail when
  required Phoenix evidence is absent.

## 6. USD migration and complete credit-surface census

### 6.1 Migration rule

The migration is an atomic pre-v1.0 cutover. `ledger_run_total_cost_usd` remains the canonical ACP
field. Credit-named fields are not dual-emitted at completion. No compatibility interval is
introduced because the field already ships on the wire and v1.0 publication has not occurred.

The migration includes, at minimum, the known live surfaces `ledger_run_total_credits`,
`optimus_credits_debited`, `credits_used`, `total_credits`, `total_optimus_credits`,
`max_budget_credits`, `credits_spent`, `cost_credits`, and `remaining_budget_credits`. The live
consumer in `loops/completion.py` that reads `usage.optimus_credits_debited` is migrated in the same
stroke. `cost_credits` and `remaining_budget_credits` are semantic renames to USD values; they do
not add budget enforcement or unpark `P9.85-FU-3`.

### 6.2 Mechanical census and retirement gate

The implementation plan must begin with a fresh machine-readable census from the assigned baseline,
not a hand-maintained identifier list:

```bash
rg -o -i --glob 'src/**' --glob 'tests/**' \
  '\b[A-Za-z_][A-Za-z0-9_]*\b' . \
  | awk -F: '{print $NF}' \
  | grep -i 'credit' \
  | sort | uniq -c
```

The retirement gate is a case-insensitive repo-wide scan, with an explicit allowlist for immutable
architecture/history prose and this design/review record:

```bash
rg -n -i --hidden --glob '!.git/**' \
  '\b[A-Za-z_][A-Za-z0-9_]*credit[A-Za-z0-9_]*\b|\bcredit\w*\b' .
```

The gate artifact must classify every hit as either:

- **retired-surface violation:** any hit in `src`, `tests`, runtime configuration, package metadata,
  release scripts, or active README/runtime examples; or
- **explicit allowlist:** frozen HLD/LLD/Guardrails/Test PDFs and their source publications,
  historical plans/reports/specs that document the retired contract, and this design/checkpoint
  record.

The allowlist is path- and reason-specific. A broad `docs/**` exemption is not permitted, and an
allowlist entry may not cover source or test code. The artifact must include the raw census, the
allowlist, the filtered result, and a zero-unallowlisted-hit assertion. This prevents a split string
or newly introduced credit identifier from evading the retirement check.

### 6.3 Baseline census snapshot

The baseline mechanical census on `67621c0` produced this complete active-source/test token set.
Counts are occurrences, not distinct files, and must be regenerated by the implementation plan
before mutation:

| Token | Baseline occurrences | Disposition |
|---|---:|---|
| `cost_credits` | 39 | Rename to the equivalent USD field; preserve current numeric behavior. |
| `credits_spent` | 22 | Rename to USD semantics; no new budget enforcement. |
| `credits_used` | 37 | Remove/replace with provider-native units or USD where the field is a legacy estimate. |
| `ledger_run_total_credits` | 7 | Remove from all ACP result shapes; retain `ledger_run_total_cost_usd`. |
| `max_budget_credits` | 21 | Rename to `max_budget_usd`; preserve current behavior and keep `P9.85-FU-3` parked. |
| `optimus_credits_debited` | 43 | Remove the legacy field and migrate the live `loops/completion.py` consumer. |
| `remaining_budget_credits` | 4 | Rename to USD semantics; no new budget enforcement. |
| `total_credits` | 11 | Remove/replace with USD or billing-unit totals according to the owning ledger. |
| `total_optimus_credits` | 2 | Remove/replace with USD totals. |
| `tavily_credits` | 5 | Explicit allowlist: provider-native unit literal, not an Optimus credit balance; preserve as a native-unit value where required by the Gateway tool contract. |
| `credit` / `credits` prose and test names | 11 | Rename active comments/test identifiers or classify a narrowly scoped historical/documentation allowlist entry. |
| `test_gateway_usage_rejects_negative_optimus_credits` | 1 | Rename and update to the USD/native-unit contract; do not retain a legacy-credit test name. |
| `test_ledger_credits_used_stays_zero_when_gateway_envelope_carries_no_credit_field` | 1 | Replace with a test for absence of fabricated provider units/cost; do not retain a legacy-credit test name. |

## 7. Implementation work packages (design-level only)

The later implementation plan may decompose these into TDD tasks, but this design does not authorize
their execution:

1. Correct the two stale charter passages and freeze the four-document matrix/digests.
2. Run and commit the mechanical credit census before changing any field.
3. Migrate ProviderUsage/EvidenceLedger/ACP result schemas, duplicate handling, and USD semantics
   without changing ProviderMessageResult or CORE request-path enforcement.
4. Add the idempotent provider/evidence persistence boundary and exact RedisTimeSeries schema.
5. Implement typed trace ingress mapping/redaction, OTel/OTLP exporter configuration, delivery
   states, bounded exporter retry, and flush behavior.
6. Wire agent telemetry fanout so model/tool/error/retry/final events reach the Gateway while local
   append-only JSONL/Redis telemetry remains available.
7. Update independent `acpx`, golden, unit, Redis integration, Gateway-live, and Phoenix-live
   evidence, then run the repo-wide retirement gate.

## 8. Verification and evidence contract

| Claim | Required evidence |
|---|---|
| Settled provider accounting | Unit and real Gateway evidence proving provider cost/units are copied, malformed accounting fails closed, and local estimates never substitute |
| Idempotent persistence | Real TimeSeries-capable Redis proving create/alter, labels, retention, duplicate handling, and response/ledger/TS equality |
| Evidence reconciliation | Unit plus integration evidence joining on `gateway_request_id`, including free operations and divergent duplicate rejection |
| USD wire migration | Unit, integration, golden, and independent `acpx` evidence proving USD field presence and old credit field absence |
| Complete credit retirement | Fresh source/test census plus case-insensitive repo-wide scan with zero unallowlisted hits |
| Trace contract | Unit evidence for schema, correlation, redaction, untrusted content, and delivery-state transitions |
| Live trace export | Real OTLP export to Phoenix proving required fields, parent/child relationships, batching, retry, validation/policy, redaction, and final disposition |
| One-key/egress boundary | Real Plan/Agent/Gateway environment and egress scans; agent sees only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` |
| Release fitness | Narrow tests, full approved suite, coverage >= 80%, safety-critical non-regression, Ruff, and Plan 9.6 live-verification authority |

Evidence tiers retain their named dependencies: fakes only for unit tests, real Redis for Redis
integration, real Optimus credentials and local Gateway for Gateway-live, real Phoenix for trace-live,
and independently authored `acpx` for ACP protocol evidence.

## 9. Definition of Done for this design

- The four frozen source digests and three merged contract digests are recorded from committed blobs.
- The full COST-OBS requirement/custody matrix covers HLD, LLD, Guardrails, and Test Strategy,
  including the three Plan 11.4 split rows.
- The charter repair is an explicit implementation-plan task with corrected authentication wording.
- The architecture preserves ProviderMessageResult and the CORE request-path enforcement boundary.
- The USD migration explicitly covers `cost_credits`, `remaining_budget_credits`, and the live
  `usage.optimus_credits_debited` consumer.
- The retirement gate is mechanical, case-insensitive, repo-wide, and allowlist-audited.
- No budget-enforcement behavior is added; `P9.85-FU-3` remains parked.
- OTel/OTLP-to-Phoenix, delivery state, no amortized charge, no LangSmith, Redis reconciliation,
  independent `acpx`, and real dependency evidence are all concrete enough for a later
  task-by-task implementation plan.
- This specification passes self-review and remains gated on user/reviewer review before invoking
  the `writing-plans` skill.

## 10. Approval record

Reviewer approval of the design direction was given on 2026-07-28, conditional on this specification
adding the complete mechanical credit census and retirement gate, the `cost_credits`/
`remaining_budget_credits` surfaces, the `usage.optimus_credits_debited` consumer, corrected charter
authentication wording, and the explicit no-new-budget-enforcement boundary. Those conditions are
incorporated here. User/reviewer review of this written specification is the next gate.
