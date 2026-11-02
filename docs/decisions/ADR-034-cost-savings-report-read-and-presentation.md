# ADR-034: The cost-savings report: a Gateway read route, dated reference columns and `/savings` in Zed

**Status:** Proposed. The operator decided D1–D4 on 2026-11-01 (verbatim below) and approved Plan 12.9 v2 at its exact
hash. Codex reviews the mechanisms at the plan's checkpoints; operator acceptance of this record is separate. Delivered
by Plan 12.9 ([#248](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/248)). Drafted by Claude.

**Relationship:** settles [ADR-012](ADR-012-cost-savings-report.md)'s open items 1 (surface) and 2 (B1 reference and
grouping), and keeps item 3 (paid B3 authority) closed for this delivery. ADR-012 stays frozen and unchanged. It reads
the ledger of [ADR-032](ADR-032-durable-usage-capture-and-gateway-drain.md) (accepted by
[ADR-033](ADR-033-accepts-adr-032-durable-usage-capture.md)) without changing its credential boundary. Unchanged:
alerts, not limits ([ADR-005](ADR-005-cost-alerts-not-limits.md)); models are configuration
([ADR-025](ADR-025-models-are-configuration-per-model-admission.md)).

## Context

The operator, 2026-10-22: "Cost Analytics are absolutely needed. We need to show cost savings with "Auto" mode. This is
a core premise". ADR-012 accepted the requirement and the baselines B1–B4. Memory design v4 §7 adds: "Usage tables show
measured known cost with coverage", with the same reported tokens repriced at dated reference prices, explicitly
estimated.

What was shipped at `9e87d67` (Plan 12.9 Task 0 manifest, `reports/plan12-cost-savings/manifest.json`):
- **The ledger has no reader:** the M0b ledger (ADR-032) records measured cost and coverage epochs. The Gateway serves
  POST only, and only the Gateway holds the Postgres credential.
- **Auto is not in the ledger:** Auto routing decisions go to telemetry only, and nothing records whether a turn ran
  under Auto.
- **Prices are thin:** registry prices are input and output only, undated in data, and `price_snapshot_id` is never
  set.
- **No commands:** Optimus advertises no ACP slash commands.

## The operator's decisions (2026-11-01, verbatim, Claude's Plan 12.9 chat)

- **D1, surface:** "/savings in Zed (Recommended)".
- **D2, scope:** "Current session (Recommended)".
- **D3, comparison:** "I recollect showing a tabular view that means showing cost savings against various options for
  e.g. against Claude Sonnet 5.5 , Opus 5.5 - it does not have to be models included in Optimus (vs comparison)".
- **D4, paid calls:** zero paid calls, recorded with "Approve and file (Recommended)" for plan v1, then "Approve v2 and
  file (Recommended)" for v2 (SHA-256 `aede5628ec2f8e41a6457e48f199b3151e89157240d874f1470a163d0dc4159e`).

## Options considered

| Decision | Chosen | Rejected or unselected, with the reason |
|---|---|---|
| D1 surface | `/savings`, an ACP slash command, rendered as Markdown in Zed's Agent Panel | A workspace Markdown file creates files and stale copies. A dashboard is a separate product surface outside the IDE. |
| D2 scope | The current session, with its Auto subset and per-turn/stage detail | A UTC day crosses sessions and needs a wider completeness boundary. A project needs durable project attribution that the ledger lacks. |
| D3 comparison | One estimated B1 column per configured reference model, priced at that model's own dated list prices. A reference need not be an Optimus model. | A fixed-selection role or tier would answer a narrower question and tie references to Optimus eligibility. Measured Auto-on/Auto-off runs are B3 and need a commissioned campaign. |
| D4 paid calls | None. B2 and B3 are separate sections that show their unavailable state. | A paid campaign needs separate task, quality, call-count and cost authority. |
| Read path | An authenticated Gateway route, `POST /v1/observability/usage-report`. The Gateway queries Postgres. | A host DSN would add the forbidden local credential (ADR-032 option 1). A file export would be stale and unbounded. |
| Auto attribution | One content-free host record per turn, `turn.report_context` (`selection: auto\|fixed`) | Inferring Auto from a model or role is not evidence. Copying the full routing telemetry into the ledger is broad consolidation, which belongs to #303. |

## Decision

**Read path.**
- **Route:** `POST /v1/observability/usage-report`, contract `optimus_security.usage_report_contract`. The Gateway
  authenticates with the existing bearer key before it reads the body or opens Postgres. It answers from a short,
  read-only, repeatable-read transaction.
- **Bounds:** 16 KiB requests, 1 MiB responses, 100 detail rows per page and 10,000 attempts or turns per scope. Above
  those bounds the totals are reported unavailable, never truncated.
- **Cursors:** each cursor is sealed under a key only the Gateway holds. A changed ledger, revision or reference
  configuration answers `409 REPORT_CHANGED`.
- **Errors:** error bodies carry a stable code only.
- **Capabilities:** a capabilities request lists the features a Gateway supports. A host writes a capture kind added
  after Plan 12.8 only to a Gateway that lists it. An older Gateway refuses an unknown kind, and that would stop the
  host stream's delivery. A launch that starts its own Gateway asks before it serves a prompt, so its first turns are
  attributed; otherwise the first delivery pass asks.

**Measured cost and coverage.**
- **Totals:** the session total sums the canonical receipts' provider-reported costs once. An unknown cost is counted
  and never read as zero.
- **When a total is definitive:** only when every expected turn reached the ledger with a complete epoch, no cost is
  unknown, there is no conflict or late receipt, and delivery is caught up. Otherwise the report names each reason.
- **Prior history:** history before durable capture is always labelled qualified.

**B1 columns (D3).**
- **Repricing:** each attempt's reported tokens are repriced at a reference's dated list prices, using the
  reference's long-context tier when its threshold is reached. Then the actual fully loaded total is subtracted once.
  Optimus's overhead (classification, summarization, retries, escalation) is already in that total and is never
  deducted again.
- **Token categories:** they nest as the provider reports them. Cached tokens are a breakdown of input tokens, and
  reasoning tokens of output tokens. This is pinned by a test of the adapter.
- **A category that cannot be priced:** a null split, a missing price or inconsistent counts leaves the attempt unpriced,
  with its reason. The attempt is never charged at another category's price. A split that cannot change the price is not
  needed.
- **Each column stands alone.** Savings and the percentage appear only when the column and the actual total are
  complete. Savings stay signed, and a zero baseline has no percentage.
- **Cache writes:** Optimus does not capture cache-write tokens, so no column includes them, and the report says so.
  Since the actual cost does include them, the omission can only understate savings.

**Reference configuration.**
- **Format:** `optimus_model_policy/savings_references.yaml` is strict YAML with a frozen schema. Each reference has a
  content-derived snapshot ID. An operator override replaces the file whole.
- **Independence from the registry:** a reference is never looked up in the registry, admitted, routed, called, or
  used for price ordering or settled cost. No model is named in code or tests.

**Snapshots.** The Gateway captures registry snapshots (actual-side provenance and tier attribution) and reference
snapshots as immutable records through its existing outbox. It populates `price_snapshot_id` only once its snapshot is
durably accepted locally.

**Surface (D1).** `/savings` is advertised through `available_commands_update`, sent after the successful
`session/new` response, because Zed drops commands sent earlier (zed-industries/zed#60199). A report makes no model
call and enters no conversation context. `/savings turn <run-id>` scopes it to one turn. `/savings next` continues the
report that session last received, and `/savings next <continuation>` returns to a particular page. The operator added
the plain form on 2026-11-02 after trying the token form in Zed, as a deviation from Plan 12.9 v2's three forms.

**Exact labels.** `usage_report_contract.LABELS` holds the user-facing wording, among them "Estimated B1 — same reported
tokens at reference prices; not realized savings" and "Auto comparison — configured reference models; not measured
Auto-off results".

## Consequences and limits

- **What the Auto table answers:** what the same reported tokens would cost at each reference's dated list prices. It
  does not predict the calls, context, retries, output or quality of another model or of turning Auto off. That needs
  B3.
- **Classification calls:** a Jev classification receipt reports no cached or reasoning split. It is unpriced for any
  reference whose cached and uncached input prices differ, so an Auto column stays incomplete while one is present.
  This is a disclosed limit. A fix would need the provider to report the split.
- **Reference prices are dated evidence, not current prices:** capturing a price today does not make it current, and a
  missing date makes its column unavailable.
- **Not established here:** provider billing correctness, realized savings, or a B2 or B3 result.
- **Not commissioned:** paid calls and campaigns. An OC-4 follow-up is filed at closure.

## Decider and provenance

- **D1–D4 and the plan:** the operator, 2026-11-01, in Claude's Plan 12.9 chat (quoted above).
- **Mechanisms:** agent-selected. Codex authored the plan (CLI round 92, session
  `01a19620-5c88-7a51-a90b-f958c88c4029`); Claude implements; Codex reviews at the plan's checkpoints.
