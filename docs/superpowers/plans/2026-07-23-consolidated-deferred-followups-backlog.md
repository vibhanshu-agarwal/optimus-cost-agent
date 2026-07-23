# Consolidated Deferred Follow-Ups Backlog

## Purpose

This document is the single source of truth for every currently open, unscheduled `P#-FU-#`
follow-up raised across the Plan 9-series (Plan 9 through Plan 9.99). Before this document existed,
each follow-up lived only inside the "Deferred Follow-Ups" section of whichever plan originally
raised it, cross-referenced (if at all) by a one-line mention in the roadmap. Two of them
(Plan 9.98-FU-1 and FU-2) were fully implemented and merged without ever getting a roadmap entry at
all, discovered only by manual audit. This document exists so that stops happening: everything
still open lives in exactly one place, and nothing gets promoted into a real plan without being
removed from here first.

This document does not itself implement anything. Every entry below either becomes its own
numbered plan (following [[plan-numbering-convention]]-style sequential allocation) or gets folded
into an already-designated future plan (e.g. Plan 12 or the Plan 10 pool) when that plan is actually
scheduled. The roadmap's `## Plan 10: Consolidated Deferred Follow-Ups Pool` section links here; it does
not duplicate this content.

## How to use this document

- **Adding a new item:** When a plan's implementation or review surfaces a new deferred follow-up
  (including ones emerging from Plan 9.96 Task 9 or the Plan 10 pool, once either actually lands), add it
  here with the same fields every other entry uses (Raised / Origin / Designated future plan /
  Trigger or acceptance criteria / Status), rather than leaving it only inside that plan's own
  Deferred Follow-Ups section or a scattered roadmap backlog entry.
- **Promoting an item:** When an item is scheduled into a real numbered plan, mark its Status as
  `Promoted -> Plan N` with the date and a link to the new plan file, and leave the entry in place
  (do not delete history) rather than removing the row.
- **Closing an item:** When an item is fully implemented, mark Status as `Closed` with the
  implementation commit/PR and evidence citation, the same way other closed follow-ups are recorded
  elsewhere in this project's roadmap.

## Open items

### P9.8-FU-2: Intelligent ambiguous-reference ranking

**Raised:** 2026-07-10, in Plan 9.8's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md`).

**Designated future plan:** Plan 12 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** Candidate ranking uses the accepted relevance/trust/freshness/dependency
policy, measures wrong-target regret, and retains a fail-closed threshold. Until this lands,
ambiguity stays visible and deterministic (Plan 9.8's current behavior).

**Status:** Open, not yet scheduled.

### P9.8-FU-3: Dynamic context budgets and required-file summarization

**Raised:** 2026-07-10, in Plan 9.8's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md`).

**Designated future plan:** Plan 12 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** Budget changes are model-aware, cost-attributed, injection-safe, measured
against the null baseline, and never silently omit required evidence.

**Status:** Open, not yet scheduled.

### P9.8-FU-5: Zed Refusal-Rendering Stability

**Raised:** 2026-07-11 during Plan 9.8 live evidence. Zed 1.10.2 correctly received and briefly
rendered the ambiguous-refusal corrective text, then panicked in native client code with
`range end index 3 out of range for slice of length 2`. The agent wire contract and independent
`acpx` durable refusal UI remain proven.

**Designated future plan:** None yet — sole custody is this entry. Plan 9.75 was already complete
when the client-stability issue was discovered, and its evidence report classifies the panic as
separate from the ACP conformance fix. Do not reopen Plan 9.75 and do not silently fold this work
into Plan 12.

**Acceptance criteria:** Reproduce against a supported current Zed build, separate agent payload
correctness from client rendering behavior, preserve the existing fail-closed refusal contract, and
produce durable operator-visible refusal evidence or an explicit externally owned Zed defect
disposition. Any agent-side workaround requires its own reviewed plan and must not weaken ACP
conformance.

**Evidence anchors:** `reports/plan-9-8-task-aware-context-evidence.md`,
`reports/plan-9-75-zed-hitl-runtime-evidence.md`, and the Plan 9.8 `P9.8-FU-5` acceptance criteria.

**Status:** Open, not yet scheduled.

### P9.85-FU-1: Intelligent observation compression

**Raised:** 2026-07-11, in Plan 9.85's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md`).

**Designated future plan:** Plan 12 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** An approved design may replace fixed fail-closed carryover with
provenance-preserving compression, regret measurement, and calibration gates. Until then, overflow
remains terminal (Plan 9.85's current behavior).

**Status:** Open, not yet scheduled.

### P9.85-FU-2: Dynamic planning-evidence partition

**Raised:** 2026-07-11, in Plan 9.85's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md`).

**Designated future plan:** Plan 12 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** Calibrated evidence justifies changing the fixed 4 KiB/12 KiB
observation/current-read split without weakening Plan 9.8's completeness and ambiguity guarantees.

**Status:** Open, not yet scheduled.

### P9.85-FU-3: Cross-Run/Session Spend Policy

**Raised:** 2026-07-11, in Plan 9.85's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md`), disclosed as
owned by an unnamed future budget-governance plan rather than silently dropped.

**Designated future plan:** None yet named — a future budget-governance plan.

**Acceptance criteria:** Define an operator-configurable cumulative session/project spend ceiling
above the existing per-run `max_cost_usd` monotonic limit and the Plan 7 usage ledger. Any new
cross-run/session ceiling must not weaken or duplicate the existing per-run
monotonic-tighten-or-exact approval contract (Plan 9.96), must be enforced from the same reconciled
Plan 7 usage ledger rather than a new parallel accounting path, and must fail closed rather than
silently permit overspend when ledger data is unavailable. Plan 9.85 records all usage completely
and accurately but does not itself invent any cross-run denial policy.

**Status:** Open, not yet scheduled.

### P9.87-FU-1: Mechanical Current-Raw-Evidence Grounding Guard

**Raised:** 2026-07-12, in Plan 9.87's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md`). Carried
forward, unresolved, through Plan 9.88's closure ceremony and Plan 9.95's custody-transfer record.

**Designated future plan:** Plan 10 (Consolidated Deferred Follow-Ups Pool). This item was formerly
the sole follow-up in the retired Plan 9.97 lane and now receives a Plan 10.x slot only when picked
up.

**Trigger:** A content-correct FU-5 final plan or later evidence shows exact policy bytes can pass
through observations despite the prompt prohibition.

**Acceptance criteria:** Define mechanical provenance between final WRITE content and current-turn
raw ranges without logging source bodies or silently absorbing Plan 12's intelligent-selection
scope. This lane must not absorb or be absorbed by Plan 12.

**Status:** Open, not yet scheduled. The Plan 10 pool assigns its next unused sequential
plain-integer/single-decimal slot at pickup time; no slot is reserved now.

## P9.96 Task 9 Disclosed Follow-Ups (Tracked, Not Yet Scheduled)

**Raised:** Disclosed by Plan 9.96 Task 9 on 2026-07-23 under the 2026-07-18 scope-conflict ruling.
Plan 9.96 closes only `P9.85-FU-7` and `P9.9-FU-1`; these seven disclosures are named custody, not
silent drops.

**Origin:** `reports/plan-9-96-operator-debug-launch-trust-evidence.md`, limitations table.

**Designated future plan:** Plan 10 (Consolidated Deferred Follow-Ups Pool). These are seven
distinct stable-ID catalog entries; no Plan 10.x slot is reserved until an item is actually picked
up.

| ID | Summary |
|---|---|
| `P9.96-FU-1` | `StartupConfigurationError` missing `optimus-agent:` prefix in `acp/__main__.py` |
| `P9.96-FU-2` | Duplicated TOCTOU comment block in `acp/__main__.py` |
| `P9.96-FU-3` | `append_launch_audit_event` docstring says trusted external runtime root but uses `workspace/.optimus` |
| `P9.96-FU-4` | Latent unroutable `DEFAULT_AGENT_MODEL = "glm-5.2"` in `agent/defaults.py` (ACP path injects `claude-haiku`) |
| `P9.96-FU-5` | Frozen dataclass exceptions mask real codes via `@contextmanager` (`FrozenInstanceError`) |
| `P9.96-FU-6` | Frozen plan Task 9 CLI arg-order / PATH assumptions; execution uses `uv run` plus `--workspace-root` before the subcommand (applied; not a code defect) |
| `P9.96-FU-7` | Approve ceremony writes durable approval with no y/N confirm; bare-shell display rows may be empty when settings are keyring/default-sourced |

**Acceptance / disposition:** Each row remains open until a reviewed Plan 10.x implementation or an
explicit closure record resolves it with evidence. `P9.96-FU-6` is an applied execution correction,
not a code defect, and may close only through an explicit reviewed disposition.

**Plan 10.1 dispositions (updated 2026-07-23; the pool's first allocated slot):**

| ID | Disposition |
|---|---|
| `P9.96-FU-1` | **Closed** by Plan 10.1, commit `daccb0d7469814930922eae67a86552435258cf6` ("fix(acp): prefix PreflightFailure and StartupConfigurationError stderr"). Named tests: `tests/unit/acp/test_main_check_config.py::test_check_config_prints_preflight_failure`, `tests/unit/acp/test_main_wiring.py::test_startup_configuration_error_has_agent_prefix`. |
| `P9.96-FU-2` | **Closed** by Plan 10.1, same commit `daccb0d7469814930922eae67a86552435258cf6` (duplicate TOCTOU comment block removed; one copy retained, verified via `rg -n -F "Plan 9.96, Task 5 Step 7 (TOCTOU matrix): workspace identity is a" src/optimus/acp/__main__.py` returning a single hit). |
| `P9.96-FU-3` | **Closed** by Plan 10.1, commit `d83953880a15419097e91da262678f736905cccd` ("docs(acp): align launch-audit docstrings with workspace-local runtime root"). Named test: `tests/unit/acp/test_launch_audit.py::test_launch_audit_docs_describe_workspace_local_runtime_root`. |
| `P9.96-FU-4` | **Closed** by Plan 10.1, commit `cc66d660cd8580eb3b821d0eb25ed04b27605dc0` ("fix(agent): use routable shared default"). Named tests: `tests/unit/agent/test_defaults.py::test_resolve_agent_model_falls_back_to_routable_shared_default`, `tests/unit/optimus_gateway/test_models.py::test_resolve_model_id_accepts_shared_agent_default_for_every_provider`. |
| `P9.96-FU-5` | **Closed** by Plan 10.1 evidence; no source or test change. Static inventory found zero `@contextmanager`/`FrozenInstanceError` occurrences in `src`/`tests`; the two candidate frozen exceptions (`StartupConfigurationError`, `AcpOutboundError`) only ever construct once via `raise ... from` / `future.set_exception(...)` and never reassign a field post-construction on any real call path. Behavior selector (`tests/unit/acp/test_bootstrap.py`, `test_outbound_errors.py`, `test_trusted_paths.py`, `test_preflight.py`) passed 36 passed, 5 skipped (environment-legitimate skips). Full record: `docs/superpowers/reviews/plan-10-1-review-checkpoints.md`, 2026-07-23T13:20:00Z entry. |
| `P9.96-FU-6` | **Closed** by reviewed Plan 10.1 disposition; execution correction only, no code change — see the disposition paragraph below. |
| `P9.96-FU-7` | **Partially addressed** by Plan 10.1, commit `278d95bec4e9a62c55c5de1237a61af1ca661309` ("feat(acp): add FU-7 explicit confirmation gate to optimus-trust approve"). Named tests: `tests/unit/acp/test_launch_approval_cli.py::TestConfirmationGate` (parametrized decline/explicit-yes cases plus a one-shot decline case). The confirmation-gate half is closed; the effective-row display gap for keyring/config/default-sourced settings **remains open** under this same stable ID — no new catalog ID or plan document was created. |

**`P9.96-FU-6` disposition paragraph:** `P9.96-FU-6` named the frozen Plan 9.96 Task 9 plan's own CLI
arg-order assumption against `optimus-trust`'s `argparse` contract. `--workspace-root`
(`src/optimus/acp/launch_approval_cli.py:78-82`) is declared on the top-level `ArgumentParser`
*before* `subparsers = parser.add_subparsers(dest="command")` (line 84), so under normal `argparse`
semantics it must be supplied before the subcommand token — e.g.
`optimus-trust --workspace-root <path> approve --mode durable`, not after. The corrected command
shape (`uv run` plus global options such as `--workspace-root` preceding the subcommand) was already
applied during Plan 9.96 Task 9's own real-`acpx` evidence capture
(`reports/plan-9-96-operator-debug-launch-trust-evidence.md`), not by Plan 10.1. Plan 10.1 (Task 6,
2026-07-23) re-verified this reviewed disposition by re-reading the current `argparse` source and
confirming the contract is unchanged. `P9.96-FU-6` was never a source-code defect and required no
production or test change under Plan 10.1 or any prior plan; no commit is recorded for this
disposition.

**Also disclosed (Plan 9.98 custody handoff):** inner `optimus-agent` launch-audit `agent_child`
may omit keyring-resolved `OPTIMUS_API_KEY` because audit precedes `apply_local_defaults`; outer
post-default audit remains the authoritative child-key evidence source. This is a custody note, not
an additional Plan 10 item.

**Status:** `P9.96-FU-1` through `P9.96-FU-4` and `P9.96-FU-6` are closed by Plan 10.1 (see the
dispositions table above); `P9.96-FU-5` is closed by Plan 10.1 evidence with no source/test change;
`P9.96-FU-7` is partially addressed by Plan 10.1 (confirmation-gate half only) and remains open under
its original stable ID for the effective-row display gap. No new catalog ID or Plan 10.x plan
document was created by this pickup. The rest of the Plan 10 pool (see Open items above) remains
tracked, not yet scheduled.

## Closed custody excluded from the open pool

Plan 9.96's two sole-custody follow-ups (`P9.85-FU-7`, `P9.9-FU-1`) are closed with the Plan 9.96
Task 9 evidence report and are intentionally not listed as open backlog entries.
