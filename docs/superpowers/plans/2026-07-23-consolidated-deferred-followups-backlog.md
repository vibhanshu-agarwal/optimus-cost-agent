# Consolidated Open Work Pool

## Purpose

This document is the single source of truth for all currently open Optimus work: charter-ratified
feature slices, deferred follow-ups, parked items, and tracked defects. It owns each item's existence and
state; the relevant charter or source document owns scope, sequencing, and detailed acceptance
criteria. Anything not listed here is not tracked as Optimus work.

Before this document existed, each follow-up lived only inside the "Deferred Follow-Ups" section of
whichever plan originally raised it, cross-referenced (if at all) by a one-line mention in the
roadmap. Two of them (Plan 9.98-FU-1 and FU-2) were fully implemented and merged without ever
getting a roadmap entry at all, discovered only by manual audit. This document exists so that stops
happening: everything still open lives in exactly one place, and nothing gets promoted into a real
plan without being removed from the open pool first.

This document does not itself implement anything. Every open entry below either becomes its own
numbered plan (following [[plan-numbering-convention]]-style sequential allocation) or gets folded
into an already-designated future plan (e.g. Plan 12 or a reviewed Plan 11 feature slice) when that plan is actually
scheduled. The roadmap's Plan 11 v1.0 milestone section links here; it does
not duplicate this content.

## How to use this document

- **Adding a new item:** When a plan's implementation or review surfaces a new deferred follow-up
  (including ones emerging from Plan 9.96 Task 9 or Plan 11 feature work), record it here first
  with the same fields every other entry uses (Raised / Origin / Designated future plan /
  Trigger or acceptance criteria / Status). Other documents may link to the entry, but must not
  carry its live open-item status or become a second pool.
- **Using status tokens:** Make the first text after `**Status:**` exactly one of these five
  canonical forms, terminated by a period or colon: `Open`, `Promoted -> <markdown link to a file
  under docs/superpowers/plans/>`, `Partially implemented`, `Closed`, or `Reviewed disposition`.
  Free prose may follow the terminating punctuation. `Partially implemented` means merged work
  advances this entry's own acceptance criteria, not merely that work exists in the owning lane.
- **Promoting an item:** When an item is scheduled into an implementation plan or amendment, mark
  its Status as `Promoted -> <linked plan or amendment>` with the date, and leave the entry in place
  (do not delete history) rather than removing the row.
- **Closing an item:** When an item is fully implemented, mark Status as `Closed` with the
  implementation commit/PR and evidence citation, the same way other closed follow-ups are recorded
  elsewhere in this project's roadmap.
- **Applying the v1.0 pool-closure gate:** Only `Closed` and `Reviewed disposition` satisfy the
  gate. `Open`, `Promoted -> ...`, and `Partially implemented` remain incomplete for that purpose.
- **Reading frozen artifacts:** Approval-time status and checkbox text inside a protected artifact
  is historical. The protected-artifact list below identifies the live pool row that owns current
  state; never reconcile that state by editing the approved bytes.

## Frozen approval bytes and live-status authority

These 14 artifacts retain their approved committed bytes. Each live owner named below, rather than
the artifact's approval-time status prose, answers the current-state question.

- `docs/superpowers/plans/2026-07-23-plan-10-2-p9-96-fu7-effective-row-display-provenance.md` — SHA-256 `4303D6AD5C44ED62A85A0509C8C87366505D4D470DD7BC4E0B4309BBE6E3C771` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P9.96-FU-7` disposition](#p996-task-9-disclosed-follow-ups-closed-historical-plan-10-custody).
- `docs/superpowers/plans/2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md` — SHA-256 `E66ECA48C588E7DB618D4850FDF0CEE901B4966BC0AB405E21C857AE6BE24F32` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [Plan 10.3 historical correction](#plan-103-frozen-plan-status-correction-historical).
- `docs/superpowers/plans/2026-07-25-plan-11-1-p11-feat-gateway-core-implementation.md` — SHA-256 `254A6ACC56511BBCCEB8FC101B190F213FD65450327145C88979077D845D6D3E` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-GATEWAY-CORE`](#feature-slices).
- `docs/superpowers/plans/2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md` — SHA-256 `8C96C9BFA67FB87F4A90FAE37169D27B437C5FD0CEE3AB2E6AB399E67B2874E5` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-GATEWAY-TOOLS`](#feature-slices).
- `docs/superpowers/plans/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-implementation.md` — SHA-256 `0BAC146974984EA663B7A59802A1B5ED74F90EB682F855C0E05AAAB5B9A2C396` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-GATEWAY-COST-OBS`](#feature-slices).
- `docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md` — SHA-256 `F52AD9A5A85DC50B0DFD3206B6BD09FD8FF0AE79B1A6049DF1017F978B1C462D` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-ZED-RESUME`](#feature-slices).
- `docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md` — SHA-256 `79F3C92A852CB7EAA6108D8F0757F6612A0C908FE032CE7CFAB58B46721C06E6` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-ZED-RESUME`](#feature-slices).
- `docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md` — SHA-256 `5BB327D88761AE329869B90866839D03F61EFF6AF0E5AE47F8D3D7551F849A4D` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-ZED-RESUME`](#feature-slices).
- `docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md` — SHA-256 `106FD92B8E43F44A7115D7EDB1F9CF1E3EE643E4B6F594FA656FB4119A969B82` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FU-11`](#p11-fu-11-plan-117-retry-preflight-and-live-session-proof).
- `docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md` — SHA-256 `8B67FC187B92F0B66A9932AAAD9A013C476C19C165A1044F57F338245A01786C` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [P9.96 historical summary and disposition](#p996-task-9-disclosed-follow-ups-closed-historical-plan-10-custody).
- `docs/superpowers/specs/2026-07-26-plan-11-2-p11-feat-gateway-tools-design.md` — SHA-256 `2E679F105A250C7DF9F3757F72C43810B92810DD080EC6A4A985B778D163BFEC` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-GATEWAY-TOOLS`](#feature-slices).
- `docs/superpowers/specs/2026-08-04-plan-11-7-retry-preflight-gate-design.md` — SHA-256 `EB34FA10148CE813A03E60E0770116ABA4AC9857E4DFBEE87E00C39BFDB0D392` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FU-11`](#p11-fu-11-plan-117-retry-preflight-and-live-session-proof).
- `docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md` — SHA-256 `AC48C0AEF1778D6EBE93005BC3993AE204F81A1C59CDC8DB17CFB7EDB6A040F8` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-GATEWAY-MCP`](#feature-slices).
- `docs/superpowers/specs/2026-08-15-p11-fu-18-29-durable-approval-workspace-identity-design.md` — SHA-256 `B445693AFB9B110E61D860F1B63D8836FF0EA651E0AC327BABA1CC906C84543B` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FU-18`](#p11-fu-18-workspace-identity-ctime-coalescing-fail-open) and [`P11-FU-29`](#p11-fu-29-durable-approval-identity-instability-on-transient-git-probe-failure).

#### Historical numbering-rule provenance

The following four documents retain statements about the numbering rule used when their work was
scheduled. Those statements are historical provenance, not live governance; the current rule lives
in `AGENTS.md` and the Plan 11 charter. Preserve each document according to its pin status:

- `docs/superpowers/plans/2026-07-23-plan-10-1-p9-96-follow-up-remediation.md` — SHA-256 `FA35912C3E5AC343A1092E7B5A88CA93C0E1293061CB53D5810BB1BA3C1002F8` — Historical closed-plan task instruction. Pin status: not digest-pinned. It is in-scope and editable for Plan 11.10, but deliberately unchanged because its sentence records the rule used at the time.
- `docs/superpowers/specs/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-design.md` — SHA-256 `5608AD5520B8960E070A4A4F32C992D152A2CA19F21C177B44AC9805F371F3AA` — Historical assignment provenance. Pin status: pinned elsewhere by the Plan 11.5 implementation plan and outside the covered set. Never edit to modernize its numbering wording.
- `docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md` — SHA-256 `AC48C0AEF1778D6EBE93005BC3993AE204F81A1C59CDC8DB17CFB7EDB6A040F8` — Historical assignment provenance. Pin status: one of the 13 immutable artifacts above. Never edit; `P11-FEAT-GATEWAY-MCP` owns live state.
- `docs/superpowers/specs/2026-08-08-plan-11-9-p11-7-fu-1-gateway-timeout-design.md` — SHA-256 `BBB033051B8238A50E72D20F6C59A79BF94A0EBE19A43428CCB440EAF8B37F73` — Historical assignment provenance. Pin status: not digest-pinned and outside the covered set. It is deliberately unchanged; any future edit requires its own reviewed scope.

## Feature slices

The pool owns each Optimus feature's existence and state; the [Plan 11 v1.0 milestone charter](2026-07-25-plan-11-v1-milestone-charter.md)
owns feature scope and sequencing. Plan 12 is listed so its post-v1.0 custody cannot fall off the
open-work inventory.

| Identity                        | Status                | Priority   | Scope detail                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
|---------------------------------|-----------------------|------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| ~~`P11-FEAT-GATEWAY-CORE`~~     | ~~Closed~~            | ~~MEDIUM~~ | ~~Plan 11.1 — closed; merged to `main` as PR #85 (`6ae6997`, tip `6c39599`). Migration closed by **Plan 11.4**, merged to `main` as PR #91 (`d80e112`), 2026-07-28. [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-gateway-core---gateway-core-and-observability-route); migration custody: strict-loopback completion, OpenRouter-default OpenAI-compatible aggregator transport, provider-reported accounting, and direct-adapter retirement — all implemented and independently re-verified task-by-task. The bounded Vercel Python transport check is complete as a design decision: Vercel is backlogged under this identity (its public OpenAI-compatible transport doesn't document the mandatory per-response provider-cost fields the settled `GatewayUsage` contract requires; no comparison matrix, no second endpoint added). Closure evidence: [design spec](../specs/2026-07-28-plan-11-4-p11-feat-gateway-core-migration-design.md), [implementation plan](2026-07-28-plan-11-4-gateway-core-migration.md) (all 36 checkboxes checked against their named verification commands)~~                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ~~`P11-FEAT-GATEWAY-TOOLS`~~    | ~~Closed~~            | ~~MEDIUM~~ | ~~Plan 11.2 — closed by PR #88 (merge `4590dbf`); migration follow-ups remain assigned here and receive a new Plan 11.x number only at pickup. [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-gateway-tools-and-p11-feat-gateway-cost-obs); migration custody: deterministic search/direct extract, route-specific dependency availability, replacement acceptance, and Tavily rollback-reviewed retirement; closure evidence: [Plan 11.2 approval](../reviews/2026-07-27-plan-11-2-implementation-plan-approval-v2.md), [local-process evidence](../../../reports/plan-11-2-gateway-tools-local-process-evidence.md), [staging evidence](../../../reports/plan-11-2-gateway-tools-staging-evidence.md), and [fitness report](../../../reports/plan-11-2-gateway-tools-task7-fitness.md)~~                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ~~`P11-FEAT-GATEWAY-COST-OBS`~~ | ~~Closed~~            | ~~MEDIUM~~ | ~~Plan 11.5 — closed by PR #95 (merge `e388258`), 2026-07-29; migration follow-ups remain assigned here (`P11.5-FU-1` open; `P11.5-FU-2` closed via Plan 11.6) and receive a new Plan 11.x number only at pickup. [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-gateway-tools-and-p11-feat-gateway-cost-obs); [implementation plan](2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-implementation.md); migration custody: OTel/OTLP-to-Phoenix and the separately reviewed USD field migration~~                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ~~`P11-FEAT-GATEWAY-MCP`~~      | ~~Retired~~           | ~~MEDIUM~~ | ~~Retired by Plan 11.12. [Plan 11.8](2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md) and [Plan 11.11](2026-08-13-plan-11-11-p11-feat-gateway-mcp-2026-07-28-http-compatibility.md) are historical precursor work; their frozen design and merged implementation records are not rewritten. Plan 11.13 published HLD v2.18, LLD v2.41, Guardrails v1.3, and Test Strategy v1.7 through the sibling reversal package; immutable amendment inputs remain historical. Client-owned MCP remains live and separate. This completed publication remains a pre-`P11-FEAT-REGISTRY` / v1.0 dependency. [Evidence](../reports/2026-08-15-plan-11-13-authoritative-document-reversal-evidence.md). [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-gateway-mcp---gateway-mcp-tool-call-brokering)~~                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `P11-FEAT-ZED-RESUME`           | Partially implemented | MEDIUM     | Partially implemented; blocked. Frozen Task 0 Steps 1-4 sealed (`session/load` unreachable on historical Zed 1.13.1); frozen Plan 11.7 Tasks 0 Steps 5-7 and Tasks 1-11 remain blocked. Standalone feasibility amendment approved (`79F3C92A…C06E6`, 2026-08-02); origin-A fixture v2 amendment approved and merged (`5BB327D8…9A4D` / PR #108, 2026-08-02). Corrected `origin-a-3` executed and sealed as Option B process-invalid (`next_corr=4` / `next_prompt=3` unclaimed; DoD success false). Retry-preflight amendment (`P11-FU-11`, PR #110) implemented through Task 5 **Path A** fail-closed terminal stop (2026-08-05): real CLI fail-closed at acquire; offline `unavailable_proof`; no corr-4 / no settings mutation / no Zed launch; accepted live retry not obtained. Parent Task 5 remains blocked; clean relaunch needs a budget-expansion amendment. Re-probe on 2026-08-15 at `71cb9ed` observed Zed `1.15.0 e17dc4f…`, independent acpx `0.12.0`, and live Redis. Its live `agentCapabilities` omitted `loadSession` and `sessionCapabilities.resume`; the resulting **INDETERMINATE / INTERNAL_CAPABILITY_UNAVAILABLE** establishes the Optimus agent gate only, not Zed support. Acpx made no forced `session/load` call, Zed was not launched, and no origin-A launch occurred. The current repository cannot independently compare the historical 1.13.1 run because its three named Task 0 artifacts are absent from `origin/main`; the [custody note](../../../reports/p11-feat-zed-resume-task0-evidence-custody-note.md) does not classify that absence as loss or invalidate the seal. The real-Zed temporary-advertisement re-probe is separately scoped and must commit its sanitized evidence. See [the re-probe](../../../reports/p11-feat-zed-resume-session-load-reprobe.md). Does not claim server-side custody feasible or an origin-A/amendment disposition. Its unimplemented error-code subset is now completed by `P11-FU-10` / Plan 11.18; frozen Plan 11.7 remains blocked and this transfer does not unblock `session/load`. Carries owned `P11-FU-1`, `P9.8-FU-5`, and `P11-FU-11`; coordinates, but does not own, `P11-FU-4`. [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-zed-resume---zed-integration-fixes-and-session-resume); [feasibility amendment](2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md); [origin-A fixture v2 amendment](2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md); [retry-preflight amendment](2026-08-04-plan-11-7-retry-preflight-gate-amendment.md). Dependency: the [evidence and handoff product pool](evidence-handoff-open-work-pool.md) entry `EVIDENCE-HANDOFF-FEAT-REDACTION-GATE` supplies its sanitized-evidence gate. |
| `P11-FEAT-REGISTRY`             | Open                  | LOW        | Ratified, unscheduled, and held as the last primary Plan 11 slice. The ACP registry has a public authoritative repository, schema, submission guide, and stabilized live process; pickup begins by pinning and executing against the then-current validator/CI behavior, not by searching for an unknown source. Reassess 11.x-last versus a 13.x split for outward publication once this consolidated pool closes. The v1.0 release-version contract and excluded-capability inventory remain in Plan 11. [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-registry---acp-registry-registration-and-v10-cut). Verified local finding carried to pickup: package and ACP versions are both `0.1.0`, and ACP currently returns `authMethods: []`. The registry guide's Agent/Terminal Auth admission rule is an external claim to verify by live execution before implementation scope is frozen.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `P11-FEAT-IDE`                  | Open                  | LOW        | Conditional — opens only by explicit amendment if REGISTRY surfaces an unmet multi-IDE expectation. [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-ide---conditional-ide-specific-testing)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `Plan 12`                       | Open                  | LOW        | Post-v1.0 context-window and intelligent-selection lane; outside the v1.0 cut. [Charter boundary](2026-07-25-plan-11-v1-milestone-charter.md#explicit-exclusions-and-unresolved-inputs)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |

**Plan 11.7 digest-pinned amendment status convention:** the
[server-side custody feasibility amendment](2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md),
[origin-A fixture-v2 amendment](2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md), and
[retry-preflight amendment](2026-08-04-plan-11-7-retry-preflight-gate-amendment.md) intentionally
retain their approval-time `Draft` status text and unchecked checkboxes. That is a load-bearing
choice to preserve their approval digests, not incomplete progress tracking. Current execution state
is owned by this living pool and the committed evidence chain: the
[artifact manifest](../../../reports/plan-11-7-server-custody-artifact-manifest.json),
[origin-A Option B seal](../../../reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/origin-a-3-seal-b.json),
[retry Task 0 digest checkpoint](../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/task0-checkpoint.json),
[Path A terminal seal](../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/path-a-run/path-a-terminal-seal.json), and
[Task 6 checkpoint](../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/task6-checkpoint.json).
Do not reconcile those historical files by changing their status lines or checkboxes.

## Follow-up status index

The detailed entries own explanatory prose; tests enforce this index as the exact ID/title/status
projection of every stable-ID follow-up heading.

**Closure partition:** `Open`, `Promoted -> ...`, and `Partially implemented` are unresolved;
`Closed` and `Reviewed disposition` are resolved. Promotion remains unresolved until the item's own
status changes through the normal status workflow; the target plan's status is not copied here.

**Priority and scheduling policy (2026-08-15):** `MEDIUM` is the default resting state and requires
no justification. Analysis may leave an unresolved entry at `MEDIUM` or move it to `HIGH` or `LOW`.
Every unresolved `HIGH` and `LOW` row must have written justification in its detail entry. Work
`HIGH` and `MEDIUM` entries first; defer `LOW` entries to the end of the Plan. For defects, `LOW`
requires no functional impact and low occurrence rate. Capability gaps, audits, process gates,
reconciliations, and other non-defect entries have no occurrence-rate criterion; justify them on
functional impact alone. This pass changes triage only; it does not change any follow-up status.

**Plan 12 custody note (2026-08-15):** `P9.8-FU-2`, `P9.8-FU-3`, `P9.85-FU-1`, and
`P9.85-FU-2` retain `MEDIUM` only as the default resting state. They do not carry a Plan 11
priority or scheduling claim; their designated owner remains Plan 12.

| ID | Item | Status | Priority   | Owning slice / designated plan | Evidence |
|---|---|---|------------|---|---|
| `P9.8-FU-2` | Intelligent ambiguous-reference ranking | Open | MEDIUM     | Plan 12 | Acceptance criteria in entry |
| `P9.8-FU-3` | Dynamic context budgets and required-file summarization | Open | MEDIUM     | Plan 12 | Acceptance criteria in entry |
| `P9.8-FU-5` | Zed Refusal-Rendering Stability | Promoted -> [Plan 11.7](2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md) | MEDIUM     | `P11-FEAT-ZED-RESUME` | [Path A terminal seal](../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/path-a-run/path-a-terminal-seal.json) |
| `P9.85-FU-1` | Intelligent observation compression | Open | MEDIUM     | Plan 12 | Acceptance criteria in entry |
| `P9.85-FU-2` | Dynamic planning-evidence partition | Open | MEDIUM     | Plan 12 | Acceptance criteria in entry |
| `P9.85-FU-3` | Cross-Run/Session Spend Policy | Open | MEDIUM     | Future budget-governance plan | Acceptance criteria in entry |
| `P9.87-FU-1` | Mechanical Current-Raw-Evidence Grounding Guard | Open | MEDIUM     | Future Plan 11 feature work | Acceptance criteria in entry |
| `P11-FU-1` | ACP Session Resume Capability | Promoted -> [Plan 11.7](2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md) | HIGH       | `P11-FEAT-ZED-RESUME` | [Path A terminal seal](../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/path-a-run/path-a-terminal-seal.json) |
| ~~`P11-FU-2`~~ | ~~Package Lookup and Security Advisory Gateway Capability~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~`P11-FEAT-GATEWAY-TOOLS` / Plan 11.2~~ | ~~PR #88 / `4590dbf`~~ |
| ~~`P11-FU-3`~~ | ~~MCP Route/Typed-Contract Publication Gate~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~`P11-FEAT-GATEWAY-MCP`~~ | ~~PR #112; PR #113 / `edd1f04`~~ |
| `P11-FU-4` | Re-pin FU-4A/FU-5 Live Evidence | Open | MEDIUM     | Coordinated with `P11-FEAT-ZED-RESUME` | Acceptance criteria in entry |
| `P11-FU-5` | Windows Subprocess Handle-Duplication Flake (WinError 6/50) | Open | LOW        | Future Windows subprocess-lifecycle evidence lane | [Plan 11.17 disposition](../../../reports/plan-11-17-p11-fu-5-windows-disposition.md); retains distinct FU-29 custody |
| `P11-FU-6` | Gateway `test_server` Full-Suite Port/Teardown Flake | Open | LOW        | Future Windows Gateway lifecycle-evidence lane | [Plan 11.17 root-cause record](../../../reports/plan-11-17-p11-fu-6-root-cause.md); recurrence retained; 59-clean bound inapplicable |
| `P11-FU-7` | Windows Coverage/`sys.settrace` Timing Flake in ACP NDJSON Sanitization Test | Promoted -> [Plan 11.16](2026-08-15-plan-11-16-p11-fu-7-19-deadline-seams.md) | MEDIUM     | Plan 11.16; closure gate deferred with `P11-FU-6` | [Windows residual](../../../reports/plan-11-16-p11-fu-7-windows-evidence.md); Plan 11.17 recorded FU-6 open disposition |
| `P11.5-FU-1` | Map live OTLPSpanExporter FAILURE into Gateway QUEUED/retry semantics | Open | MEDIUM     | `P11-FEAT-GATEWAY-COST-OBS` | Acceptance criteria in entry |
| `P11-FU-8` | Align `OPTIMUS_LOCAL_GATEWAY_BASE_URL` with `OPTIMUS_GATEWAY_<THING>_BASE_URL` naming | Open | LOW        | Future Gateway migration design | Acceptance criteria in entry |
| ~~`P11-FU-9`~~ | ~~Client-Supplied ACP `mcpServers` Disposition~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Dedicated P11-FU-9 lane~~ | ~~PR #119 / `9a93137`; [closure evidence](../../../reports/p11-fu-9-client-mcp-closure-evidence.md)~~ |
| `P11-FU-10` | Complete ACP Error-Code Registry Audit | Closed | HIGH       | [Plan 11.18](2026-08-15-plan-11-18-acp-error-code-registry-audit-implementation.md) | PR #158 (merge 7d4e466); [acpx evidence](../../../reports/plan-11-18-p11-fu-10-acpx-error-code-evidence.md) |
| ~~`P11.7-FU-1`~~ | ~~Configurable Gateway request timeout for debug/investigation workflows~~ | ~~Closed~~ | ~~HIGH~~   | ~~Plan 11.9~~ | ~~PR #123 / `d0253be`~~ |
| ~~`P11.7-FU-2`~~ | ~~Gateway threaded-test flake under full-suite load~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~`P11-FU-6` Gateway harness custody~~ | ~~Batch B 2026-08-14; misfiled duplicate~~ |
| `P11.7-FU-3` | Committed `plan117_custody_relay.py` docstring `\ufffd` / em-dash corruption | Open | MEDIUM     | Plan 11.7 deferred follow-up | Acceptance criteria in entry |
| `P11-FU-11` | Plan 11.7 Retry Preflight and Live Session Proof | Partially implemented | HIGH       | [Plan 11.7 retry-preflight amendment](2026-08-04-plan-11-7-retry-preflight-gate-amendment.md) | [Path A terminal seal](../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/path-a-run/path-a-terminal-seal.json) |
| ~~`P11-FU-12`~~ | ~~MCP OAuth 2.1 Lifecycle~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Retired `P11-FEAT-GATEWAY-MCP`~~ | ~~Plan 11.12; won't-do~~ |
| ~~`P11-FU-13`~~ | ~~Deferred MCP Capabilities and Long-Lived Interaction~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Retired `P11-FEAT-GATEWAY-MCP`~~ | ~~Plan 11.12; won't-do~~ |
| ~~`P11-FU-14`~~ | ~~MCP Registry Discover-and-Connect~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Retired `P11-FEAT-GATEWAY-MCP`~~ | ~~Plan 11.12; won't-do~~ |
| ~~`P11-FU-15`~~ | ~~MCP Tool Search and Context Minimization~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Retired `P11-FEAT-GATEWAY-MCP`~~ | ~~Plan 11.12; won't-do~~ |
| `P11-FU-16` | Reverse Research-to-Documentation Freshness Gate | Open | MEDIUM     | Future cross-cutting documentation gate | Acceptance criteria in entry |
| ~~`P11-FU-22`~~ | ~~Durable effect-aware MCP indeterminate-call custody~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Retired `P11-FEAT-GATEWAY-MCP`~~ | ~~Plan 11.12; won't-do~~ |
| `P11-FU-23` | Durable client-MCP descriptor-surface pinning and named tool allowlists | Open | MEDIUM     | Future client-MCP trust follow-up | Acceptance criteria in entry |
| `P11-FU-24` | Client-MCP durable HTTP/SSE trust relaxation | Open | MEDIUM     | Future client-MCP trust follow-up | Acceptance criteria in entry |
| `P11-FU-25` | Authenticated client-owned MCP upstream evidence | Open | MEDIUM     | Future client-MCP evidence follow-up | Acceptance criteria in entry |
| ~~`P11-FU-26`~~ | ~~Plan 11.8 Windows `WinError 10053` MCP test flake~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Retired `P11-FEAT-GATEWAY-MCP`; signal under `P11-FU-6`~~ | ~~Plan 11.12; obsolete-by-retirement~~ |
| ~~`P11-FU-27`~~ | ~~Publication-Plan Historical-State Reconciliation~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Plan 11.22~~ | ~~[Plan 11.22 reconciliation evidence](../../../reports/plan-11-22-p11-fu-27-publication-reconciliation.md); merged PR #113 / `verification.md`~~ |
| ~~`P11-FU-28`~~ | ~~WSL2 `uv sync` shared-Windows-`.venv` destruction hazard~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Native WSL clone operating decision~~ | ~~Obsolete for supported Linux-parity gates; `P11-FU-17` proof 2026-08-14~~ |
| ~~`P11-FU-29`~~ | ~~Durable-approval identity instability on transient Git probe failure~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Plan 11.15~~ | ~~[release report](../../../reports/plan-11-15-durable-approval-identity-release.md); preserve-approval / Git-retry / migration evidence only~~ |
| ~~`P11-FU-17`~~ | ~~WSL2 native git cannot parse a Windows-git-created linked worktree's `.git` pointer~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Native WSL clone operating decision~~ | ~~Resolved by verified ext4 native-clone gate; proof report 2026-08-14~~ |
| ~~`P11-FU-18`~~ | ~~Workspace-identity `ctime` coalescing fail-open~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Plan 11.15~~ | ~~[release report](../../../reports/plan-11-15-durable-approval-identity-release.md); equal-ctime topology evidence only~~ |
| ~~`P11-FU-19`~~ | ~~WSL client-SDK operation-deadline supervisor race~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Plan 11.16~~ | ~~[Windows](../../../reports/plan-11-16-p11-fu-19-windows-evidence.md); [WSL](../../../reports/plan-11-16-p11-fu-19-wsl-evidence.md)~~ |
| `P11-FU-20` | Attach per-server catalog/authorizer to session tool service for real one-call issuance | Promoted -> [Plan 11.20](2026-08-17-plan-11-20-p11-fu-20-client-mcp-one-call-approval.md) | MEDIUM     | Future client-MCP runtime follow-up | [release](../../../reports/plan-11-20-p11-fu-20-release.md); [evidence](../../../reports/plan-11-20-p11-fu-20-evidence.md); seam built and unit-tested; production composition not yet wired; live one-call tier unrun |
| ~~`P11-FU-21`~~ | ~~Custody Relay Broken-Pipe Exit-Code Propagation Defect~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Plan 11.14~~ | ~~Plan 11.14; `reports/plan-11-14-p11-fu-21-custody-relay-exit-code-evidence.md`~~ |
| ~~`P11.5-FU-2`~~ | ~~Consistent local env / Redis / Phoenix / Gateway startup for live runs~~ | ~~Closed~~ | ~~HIGH~~   | ~~Plan 11.6~~ | ~~PR #97 / `dc9a080`; [operator runbook](../../runbooks/local-live-dependencies.md)~~ |

## Settled risks and historical entries

This companion table keeps accepted risks and closed historical entries discoverable without
mixing them into the active follow-up index. Its rows still participate in the exact heading/index
bijection.

| Item                                                                                                                                 | Status               | Priority | Disposition / evidence                                                  |
|--------------------------------------------------------------------------------------------------------------------------------------|----------------------|--------|-------------------------------------------------------------------------|
| Plan 11.7 accepted risk: `optimus-redis` ACP-session durability boundary                                                             | Reviewed disposition | MEDIUM | Accepted bounded durability risk recorded in the entry                  |
| ~~Plan 10.3 frozen-plan status correction (historical)~~                                                                             | ~~Closed~~               | ~~MEDIUM~~ | ~~Frozen source remains unchanged; pool-side correction recorded in the entry~~ |
| ~~`uv.lock` missing direct dependencies: `keyring`, `redis`, and their transitive chain (disclosed 2026-07-23 during Plan 10.1 Task 1)~~ | ~~Closed~~               | ~~MEDIUM~~ | ~~Historical dependency-lock correction retained in the entry~~             |
| ~~Tools: `SurfaceAuditError` frozen-dataclass CI wart (disclosed 2026-07-23 during Plan 10.1 Task 7)~~                               | ~~Closed~~               | ~~MEDIUM~~ | ~~Historical CI correction retained in the entry~~                          |

## Open items

### P9.8-FU-2: Intelligent ambiguous-reference ranking

**Raised:** 2026-07-10, in Plan 9.8's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md`).

**Designated future plan:** Plan 12 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** Candidate ranking uses the accepted relevance/trust/freshness/dependency
policy, measures wrong-target regret, and retains a fail-closed threshold. Until this lands,
ambiguity stays visible and deterministic (Plan 9.8's current behavior).

**Status:** Open. The bounded Plan 11.7 current-Zed evidence/correction cycle reached its reviewed
Task 5 Path A fail-closed terminal stop on 2026-08-05: no accepted same-session live retry, no
correlation ordinal 4, no settings mutation, and no Zed relaunch. No approved correction remains
pending in that cycle. This did not implement intelligent ambiguous-reference ranking;
`P9.8-FU-2` remains open under Plan 12 with its original acceptance criteria.

### P9.8-FU-3: Dynamic context budgets and required-file summarization

**Raised:** 2026-07-10, in Plan 9.8's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md`).

**Designated future plan:** Plan 12 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** Budget changes are model-aware, cost-attributed, injection-safe, measured
against the null baseline, and never silently omit required evidence.

**Status:** Open. Not yet scheduled.

### P9.8-FU-5: Zed Refusal-Rendering Stability

**Raised:** 2026-07-11 during Plan 9.8 live evidence. Zed 1.10.2 correctly received and briefly
rendered the ambiguous-refusal corrective text, then panicked in native client code with
`range end index 3 out of range for slice of length 2`. The agent wire contract and independent
`acpx` durable refusal UI remain proven.

**Designated slice:** `P11-FEAT-ZED-RESUME` (plan number assigned at pickup). Plan 9.75 was already complete
when the client-stability issue was discovered, and its evidence report classifies the panic as
separate from the ACP conformance fix. Do not reopen Plan 9.75 and do not fold this work into Plan 12.

**Acceptance criteria:** Reproduce against a supported current Zed build, separate agent payload
correctness from client rendering behavior, preserve the existing fail-closed refusal contract, and
produce durable operator-visible refusal evidence or an explicit externally owned Zed defect
disposition. Any agent-side workaround requires its own reviewed plan and must not weaken ACP
conformance.

**Evidence anchors:** `reports/plan-9-8-task-aware-context-evidence.md`,
`reports/plan-9-75-zed-hitl-runtime-evidence.md`, and the Plan 9.8 `P9.8-FU-5` acceptance criteria.

**Status:** Promoted -> [Plan 11.7](2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md).
Scheduled in Plan 11.7 (`P11-FEAT-ZED-RESUME`). Frozen Task 0 Steps 1-4 sealed the
current-Zed Case 1/2 refusal-rendering evidence (Case 1 wire `end_turn` / stable; Case 2 wire
`refusal` / Zed panic). The bounded origin-A/retry-preflight correction cycle reached Task 5
**Path A** fail-closed terminal stop on 2026-08-05; no approved correction remains pending. An
accepted same-session live retry was not obtained, frozen Plan 11.7 remains blocked, and this item
stays open pending an explicit reviewed Zed-defect disposition or a separately authorized future
budget-expansion/live-evidence path. Evidence:
[Path A terminal seal](../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/path-a-run/path-a-terminal-seal.json).

**Triage justification for HIGH (2026-08-15):** This is an unimplemented ACP protocol capability
that makes a client start a new session instead of restoring an existing one after a connection or
process boundary. The impact is directly user-visible session continuity and cross-client
interoperability, with durable identity, history, and storage-failure semantics still undefined;
that functional impact warrants work ahead of ordinary capability and documentation gaps.

### P9.85-FU-1: Intelligent observation compression

**Raised:** 2026-07-11, in Plan 9.85's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md`).

**Designated future plan:** Plan 12 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** An approved design may replace fixed fail-closed carryover with
provenance-preserving compression, regret measurement, and calibration gates. Until then, overflow
remains terminal (Plan 9.85's current behavior).

**Status:** Open. Not yet scheduled.

### P9.85-FU-2: Dynamic planning-evidence partition

**Raised:** 2026-07-11, in Plan 9.85's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md`).

**Designated future plan:** Plan 12 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** Calibrated evidence justifies changing the fixed 4 KiB/12 KiB
observation/current-read split without weakening Plan 9.8's completeness and ambiguity guarantees.

**Status:** Open. Not yet scheduled.

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

**Architecture resolution (2026-07-28):** The repaired HLD v2.16 §§5A and 11, LLD v2.39 §§0A,
9D, and 10A, Guardrails v1.1 §§7.2 and 9, and the refreshed requirement inventory settle the
local Gateway as the authority for current-run budget caps, provider-reported usage/cost, and the
reconciled cost ledger. The prior architecture conflict about a hosted budget service is resolved.
This entry does not define a cumulative session/project ceiling: that policy remains open,
undesigned, and unscheduled under a future budget-governance plan.

**Plan 11 disposition:** Architecture-unblocked; no implementation or cumulative cross-run policy
design is included in Plan 11. Revisit only under the future budget-governance plan.

**Status:** Open. Not yet scheduled.

### P9.87-FU-1: Mechanical Current-Raw-Evidence Grounding Guard

**Raised:** 2026-07-12, in Plan 9.87's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md`). Carried
forward, unresolved, through Plan 9.88's closure ceremony and Plan 9.95's custody-transfer record.

**Designated future plan:** Plan 11 feature work; no feature slice or plan number is assigned yet.
This item was formerly the sole follow-up in the retired Plan 9.97 lane and is now carried by this
pool without a Plan 10.x slot.

**Trigger:** A content-correct FU-5 final plan or later evidence shows exact policy bytes can pass
through observations despite the prompt prohibition.

**Acceptance criteria:** Define mechanical provenance between final WRITE content and current-turn
raw ranges without logging source bodies or silently absorbing Plan 12's intelligent-selection
scope. This lane must not absorb or be absorbed by Plan 12.

**Status:** Open. Not yet scheduled. This pool records promotion and disposition when this item is
picked up; no Plan 10.x slot is reserved.

### P11-FU-1: ACP Session Resume Capability

**Raised:** 2026-07-25 during Plan 11 scoping. The current ACP adapter dispatches `initialize`,
`session/new`, and `session/prompt`, but has no `session/load` handler. Its initialization response
advertises an empty `sessionCapabilities` object, so the client correctly concludes that resume is
unsupported and starts a new session on every connection.

**Origin:** `src/optimus/acp/spec.py` (`AcpDuplexAdapter.handle_client_request` and
`_handle_initialize`), with the live server wiring `InMemoryAcpSpecSessionStore` in
`src/optimus/acp/server.py`.

**Designated slice:** `P11-FEAT-ZED-RESUME` (plan number assigned at pickup). This item is
owned by `P11-FEAT-ZED-RESUME`, not parked or deferred to a later milestone.

**Acceptance criteria:** The reviewed `P11-FEAT-ZED-RESUME` design and implementation must:

- implement ACP `session/load` and advertise `loadSession` only when its semantics are supported;
- define the session identity, workspace binding, conversation/history, and relevant run metadata
  that persist across client/process boundaries;
- select and document a durable storage mechanism, TTL/expiry, deletion, migration/versioning,
  retention, and storage-failure behavior as a first-class design decision;
- restore the session in the protocol-required shape, including conversation replay or the exact
  supported load semantics, without silently substituting `session/new`; and
- cover successful load, unknown/expired sessions, workspace mismatch, malformed or unavailable
  storage, capability negotiation, and history replay with unit/integration/live ACP evidence.

`InMemoryAcpSpecSessionStore` is process-local. `RedisAgentStateStore` stores expiring agent plans
(`AgentPlanRecord`), not ACP session or conversation state, and cannot be treated as an existing
resume store without an explicit design and migration decision.

**Status:** Promoted -> [Plan 11.7](2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md).
Scheduled in Plan 11.7 (`P11-FEAT-ZED-RESUME`). Frozen Task 0 Steps 1-4 are sealed with
disposition `stop_amend_plan_session_load_unreachable` (historical Zed 1.13.1 did not issue `session/load`
after full restart). The bounded origin-A/retry-preflight correction cycle reached Task 5
**Path A** fail-closed terminal stop on 2026-08-05; no approved correction remains pending. The
accepted same-session live retry was not obtained, parent Task 5 and frozen Plan 11.7 remain blocked,
and a clean relaunch requires a separately authorized budget-expansion amendment. This is still an
unimplemented protocol capability, not a flaky regression or parked architecture blocker. Evidence:
[Path A terminal seal](../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/path-a-run/path-a-terminal-seal.json).

### P11-FU-2: Package Lookup and Security Advisory Gateway Capability

**Raised:** 2026-07-25 during the Plan 11 Gateway requirement review. At intake, the pinned LLD named
`POST /v1/tools/package/lookup` and `POST /v1/tools/security/advisory` as Gateway-facing typed
endpoints, and §9A/§9B define their package/advisory tool class and routing signals. At intake, the
local repository did not yet implement these Gateway routes as dedicated endpoints. Existing policy
behavior is not absent: `src/optimus/tools/policy.py:85-93` routes `DEPENDENCY_VERSION_CHECK` and
`SECURITY_OR_CVE_CHECK` into `WEB_SEARCH_TRIGGERS`, while LLD §9B's `DEFAULT_POLICY_MATRIX`
(p.26) maps both signals to `ToolClass.PACKAGE_AND_ADVISORY_METADATA`. At intake, dependency and
CVE evidence was therefore served via generic web search, against a different tool class than the
LLD specified. Picking up FU-2 changed existing, tested policy behavior, not merely adding routes.

**Origin:** `docs/Optimus-Cost-Agent-LLD-v2.39.pdf`, §0.D (p.3), §9A (p.24), and §9B (p.25).

**Designated slice:** `P11-FEAT-GATEWAY-TOOLS` (Plan 11.2 at pickup). This capability was
implemented and closed in PR #88 / merge `4590dbf`; future search-independence and migration work
remains owned by the same feature identity. It is not part of the `P9.85-FU-3` cumulative
cross-run policy. The reviewed artifacts are the [design specification](../specs/2026-07-26-plan-11-2-p11-feat-gateway-tools-design.md)
and [implementation plan](2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md).

**Acceptance criteria:** The reviewed `P11-FEAT-GATEWAY-TOOLS` design and implementation must:

- define and serve the package-registry lookup and security-advisory request/response contracts;
- route `PACKAGE_AND_ADVISORY_METADATA` using `PACKAGE_VERSION` and `SECURITY_ADVISORY` signals;
- preserve the zero-upstream-credential boundary, Gateway-side provider secrets, policy revalidation, usage/cost
  envelope, and evidence/provenance contracts; and
- provide named unit, integration, and real-Gateway evidence for both endpoint families.

**Closure evidence:** The checked Plan 11.2 Definition of Done and closing approval are recorded
in the [v2 approval record](../reviews/2026-07-27-plan-11-2-implementation-plan-approval-v2.md).
Named evidence reports are the [real local-process HTTP artifact](../../../reports/plan-11-2-gateway-tools-local-process-evidence.md),
[real staging-Gateway artifact](../../../reports/plan-11-2-gateway-tools-staging-evidence.md), and
[fitness/release-gate report](../../../reports/plan-11-2-gateway-tools-task7-fitness.md).

**Status:** Closed. Implemented by PR #88 / merge `4590dbf`; the dedicated package/advisory routes and their
evidence are complete. Remaining migration work stays with `P11-FEAT-GATEWAY-TOOLS` and is not a
reopening of this closed item.

### P11-FU-3: MCP Route/Typed-Contract Publication Gate

**Raised:** 2026-07-25 during the Plan 11 Gateway requirement review. The original LLD §0.B was
clipped at the rendered page boundary around `/v1/tools/web/extract`, and §0.C named MCP tool
brokering without an MCP endpoint or Gateway request/response shape in §0.D.

**Origin:** `docs/Optimus-Cost-Agent-LLD-v2.39.pdf`, §0.B (rendered p.2), §0.C (p.3), and §0.D
(p.3), final SHA-256 `82513729FD1A6E87FAD310DD90A18C996981B68024204E56CCA65377495585DE`.

**Completed source repair:** The v2.39 §0.B clip and hosted-content repair are complete. The
published source is extractable, its component flow is complete, and the §0.B diagram states that
no MCP endpoint is shown or implied. The repair is documentation-complete; it does not authorize
MCP implementation or endpoint inference.

**Operator decision (2026-07-29):** Affirmative—MCP brokering is supported. Operator's stated
rationale: non-negotiable for any agent, especially a coding agent.

**Acceptance criteria (both now met):**

- ~~The operator must explicitly decide whether MCP brokering is supported.~~ Decided 2026-07-29:
  yes.
- ~~The route and typed request/response contract must be represented in the amended, source-pinned
  HLD, LLD, Guardrails, and Test Strategy PDFs.~~ Satisfied 2026-08-06: the MCP Gateway architecture
  amendment charter update (PR #112, merged 2026-08-05) and the publication of all four amended PDFs
  — HLD v2.17, LLD v2.40, Guardrails v1.2, Test Strategy v1.6 (PR #113, merge commit `edd1f04`,
  merged 2026-08-06) — are both live on `main`. Independently confirmed the typed contract is
  actually present, not just nominally referenced: the published LLD contains
  `POST /v1/tools/mcp/discover`, `POST /v1/tools/mcp/call`, and the named component types
  (`MCPProfileRegistry`, `MCPDiscoveryBroker`, `MCPDiscoveryPaginator`, `MCPInvocationBroker`,
  `MCPConnectionManager`).

**Status:** Closed. On 2026-08-06, both acceptance criteria were met. Later pickup produced the
[Plan 11.8 design](../specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md) and living
[Plan 11.8 implementation plan](2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md).
Its partial checkpoint is 27 of 46 checks complete (Tasks 0-7 and Task 8 Step 1 complete; Task 8
Steps 2-4 and Task 9 incomplete), with implementation in PR #116 and CI custody repair in PR #118.
`P11-FEAT-ZED-RESUME` remains a separate, independently blocked lane.

### P11-FU-4: Re-pin FU-4A/FU-5 Live Evidence

**Raised:** 2026-07-15 by the Plan 9.95 Task 5 implementation amendment.

**Origin:** `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, historical backlog section §776.
The Plan 9.87 `fu4a` and `fu5` evidence gates fail with implementation drift against the current
codebase, so fresh live evidence must be captured and re-pinned.

**Designated slice:** Coordinate with `P11-FEAT-ZED-RESUME` where the Zed live-evidence
capture path overlaps; no Plan 11.x plan number is allocated by this entry.

**Acceptance criteria:** Re-capture fresh real-`acpx` FU-4A and FU-5 evidence against the current
codebase, select the reviewed sanitized capture path, record the exact evidence and implementation
SHAs, and close or explicitly disposition the freshness gap before the v1.0 cut. FU-4A may be
partially closed on its own once its fresh evidence is accepted; that partial closure must not claim
the separate FU-5 evidence half is complete.

**Status:** Open. Tracked, not yet scheduled; no implementation plan exists. Evidence-freshness class.

**Prioritization disposition (2026-08-15):** Option 2 — allow partial closure on FU-4A alone. This
keeps the actionable fresh-evidence work at the default `MEDIUM` level without parking it behind
the separate FU-5 evidence residual. The overall entry remains `Open` until the FU-5 half is also
accepted or explicitly dispositioned; no status is changed by this pass.

### P11-FU-5: Windows Subprocess Handle-Duplication Flake (WinError 6/50)

**Raised:** 2026-07-22 during Plan 9.99 Task 7 repository-wide verification.

**Classification:** MISFILED as one combined item. The unreproduced Windows flake and the
deterministically demonstrable durable-approval identity concern have separate mechanisms and
must have separate custody.

**Origin:** `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, historical backlog section §861.
The feasibility findings include both the no-reproduction result and the separately identified
durable-approval identity concern. Batch B splits the latter into `P11-FU-29`; this entry retains
only the rare Windows `DuplicateHandle` flake custody.

**Designated slice:** Future Windows subprocess-lifecycle evidence lane. [Plan 11.17's disposition](../../../reports/plan-11-17-p11-fu-5-windows-disposition.md) established reproduced, context-known custody but no deterministic causal edge. This remains distinct from the durable-approval `P11-FU-29` mechanism.

**Acceptance criteria:** A future pickup must establish an applicable reproduction or durable
non-reproduction disposition for the original Windows flake, and receive a reviewed custody
decision before any fix or exclusion is claimed. It must not fold the independent `P11-FU-29`
identity concern back into this test-infrastructure entry.

**Reproduction disposition (2026-08-14/15):** Reproduced, context known. The operator-recorded
disposition is three Windows `WinError 6` / `DuplicateHandle` occurrences in
`test_immutable_documents_match_approved_head_blobs` and
`test_product_checkpoint_log_location_remains_gitignored`, both of which spawn Git subprocesses.
The [Plan 11.14 evidence](../../../reports/plan-11-14-p11-fu-21-custody-relay-exit-code-evidence.md#ruff-diff-and-sealed-artifact)
names those two selectors and the `DuplicateHandle` incident. The
[Plan 11.15 baseline](../../../reports/plan-11-15-durable-approval-identity-baseline.md#baseline-failures--recorded-as-p11-fu-5-not-plan-1115)
records the same `subprocess.Popen` / `_make_inheritable` mechanism in four other Windows Git/DACL
subprocess tests; those four failures are corroborating mechanism evidence, not part of the three
occurrences above. The [Plan 11.15 Windows evidence](../../../reports/plan-11-15-windows-durable-approval-identity-evidence.md#residuals-not-this-plan)
and [release report](../../../reports/plan-11-15-durable-approval-identity-release.md#unrun--unclaimed-tiers)
retain FU-5 as open and expressly prevent cross-crediting FU-29's injected Git fault.

The historical ten-run no-reproduction result remains historical context, not contrary evidence;
FU-5's recurrence rate is unknown, so later clean runs cannot prove absence. No fix or exclusion is
claimed here.

**Status:** Open. Reproduced, context known; root cause remains unestablished after Plan 11.17.
Its own evidence and reviewed custody decision determine any closure; it cannot borrow FU-6 socket
evidence or its no-reproduction bound.

**Triage justification for LOW (2026-08-15):** Plan 11.17 reproduced the `DuplicateHandle` signal
in the known Git-spawning test context, but the rate remains unknown and no product behavior has
been shown to fail. This is test-infrastructure-only custody with no functional product effect;
the sparse reproduced signal and the decided Plan 11.17 disposition place it at the end-of-Plan
queue while preserving its separate evidence and closure requirements.

**Batch B split (2026-08-14):** The historical ten-run no-reproduction result remains evidence for
the rare Windows flake, not a product fix. The roadmap's fault-injectable behavior in
`_git_repository_root` / `_git_common_dir` is now owned by `P11-FU-29`. It is related to
`P11-FU-18` because both feed the durable workspace-identity/approval contract, but is distinct:
this path can spuriously invalidate approval when a Git probe fails (fail closed), whereas
`P11-FU-18` can miss a real in-place change when `ctime` coalesces (fail open).

### P11-FU-29: Durable-approval identity instability on transient Git probe failure

**Raised:** 2026-08-14 by Batch B triage, split from `P11-FU-5`'s historical feasibility findings.

**Classification:** Durable-approval workspace-identity security design concern; not a test flake.

**Origin:** `src/optimus/acp/trusted_paths.py` catches `OSError` from
`_git_repository_root` / `_git_common_dir` and returns `None`. Those values feed the workspace
identity digest that names durable approval. The roadmap records that fault injection of a transient
Windows `WinError 6` makes an otherwise unchanged workspace acquire a different digest and therefore
produce a spurious `NO_APPROVAL`.

**Designated slice:** Plan 11.15, coordinated with but not merged into `P11-FU-18`. Mechanism remains
durable-approval identity instability on transient Git probe failure (`None` conflation).

**Acceptance criteria (draft):** Define the identity contract for transient Git-probe failure,
including whether to fail closed without changing identity, how to retain diagnostic evidence, and
how any digest/migration behavior affects already-issued approvals. Prove the selected behavior by
fault injection. Do not treat a clean rerun of the unrelated Windows handle flake as resolution.

**Status:** Closed. Plan 11.15 SHA `12b881a28b4a736a0d18ccdf1c02c49b94167e41`. Own evidence:
Git tri-state plus three-attempt transient injection, preserve-approval / no-`NO_APPROVAL` through
real `main()`, exact exclusion policy v1, and HMAC-verified observable v2→v3 migration with
inherited-trust limitation. Windows CLI unavailable cases print retry/repair and never
`NO_APPROVAL`. Reports:
[Windows](../../../reports/plan-11-15-windows-durable-approval-identity-evidence.md),
[WSL](../../../reports/plan-11-15-wsl-durable-approval-identity-evidence.md),
[release](../../../reports/plan-11-15-durable-approval-identity-release.md).
Not closed by `P11-FU-18` topology evidence and not closed by a `P11-FU-5` handle-flake rerun.

### P11-FU-6: Gateway `test_server` Full-Suite Port/Teardown Flake

**Raised:** 2026-07-26 during Plan 11.1 Task 7 final sign-off (PR #85 / `P11-FEAT-GATEWAY-CORE`).

**Origin:** Intermittent failure of the predecessor of current
`tests/unit/optimus_gateway/test_server.py::test_tools_routes_return_not_found_when_dependencies_are_not_configured`
(`test_tools_routes_remain_not_found` at raising) observed once in
five consecutive full-suite runs (`uv run --frozen pytest -q` and the same suite under `--cov`).
The same test passed every isolation run (single node and the full 24-test `test_server.py` file).
Not connected to Plan 11.1 CORE-route feature correctness — focused and live CORE evidence stayed
green throughout review.

**Suspected cause:** Shared `_start_server()` / `_stop_server()` helpers spin a real
`ThreadingHTTPServer` on an OS-assigned loopback port (`socket.bind(("127.0.0.1", 0))`) per test
(~20 siblings in the file). Likely a Windows-specific port-reuse or thread-teardown race
(`server.shutdown()` / `thread.join(timeout=5)` racing the next test's bind), not an assertion
defect in the failing test.

**Related prior art:** Same Windows test-infra flake class as `P11-FU-5` (WinError 6/50) and the
`agent/cursor/windows-subprocess-handle-flake-backlog` branch. Before scoping a numbered plan,
check whether this shares that root cause; do a feasibility pass before any scoped plan, not
before.

**Designated slice:** Future Windows Gateway lifecycle-evidence lane. [Plan 11.17's root-cause
record](../../../reports/plan-11-17-p11-fu-6-root-cause.md) retained the full-suite recurrence and
classified its cause as insufficiently evidenced; no deterministic correction is authorized.

**Acceptance criteria:** Reproduce or disposition under full-suite load on Windows; determine
whether this is the same root cause as `P11-FU-5` or a distinct bind/teardown race; harden
`_start_server`/`_stop_server` (or equivalent) only after a reviewed feasibility pass; preserve
the CORE-route unit coverage that already passes in isolation.

**Status:** Open. Reproduced, root cause unestablished after Plan 11.17 process 5 failed at the
current successor. The 59-clean bound is inapplicable after that recurrence. Its historical 95.2%
conditional detection-power calculation applies only to 59 clean independent processes at the
observed 5% rate and never proves absence. Any harness or production correction remains conditional
on deterministic-red and reviewed-scope gates.

**Additional observation (2026-08-10, evidence-handoff Task 6 interop review):** During a full
suite run on this host, `tests/unit/optimus_gateway/test_server.py::test_unknown_route_remains_not_found`
failed once, then passed in isolation, in its own file, and on a clean full re-run
(3126 passed / 0 failed). Same `test_server.py` ThreadingHTTPServer harness class as the original
`test_tools_routes_remain_not_found` observation; still unreproduced for root-cause. Do not dismiss
as "just flaky" without a disposition — this entry remains the named owner. Unrelated to the
evidence-handoff MCP-Protocol-Version transport fix under review the same day.

**Additional observation (2026-08-10 evening, Option B integrity-latch review):** A second distinct
sibling in the same `test_server` harness failed once during a full-suite run for the
`evidence_handoff_runtime` latch-mirror fix, then passed isolated, in-file, and on a clean full
re-run (3132 passed / 0 failed). `optimus_gateway` was untouched by that change. Two different
harness siblings failing the same evening is stronger race evidence than either alone — keep both
on this entry; do not open a second FU.

**Recurrence:** 2026-08-11 — DoD coverage run: the P11-FU-6 pair recurred (both `test_server`
harness tests) under `--cov`; passed isolated, in-file, and on coverage re-run at 81.34%. Same
port/teardown harness class; do not merge with `P11-FU-7`.

**Additional observation (Plan 11.12):** The Windows `WinError 10053` socket-teardown signal
previously tracked under `P11-FU-26` is transferred here because Plan 11.12 retired the Gateway MCP
transport surface. This entry remains open and continues to own Gateway `test_server` port/teardown
flake custody. No production retry or safety weakening was added.

**Batch B recurrence (2026-08-14):** On current `origin/main` base `da2fc78`, 20 Windows
`pytest tests/unit -q` processes produced 18 clean suites and two unrelated suite failures. The
obsolete predecessor node did not exist and therefore had 0/20 hits; its current successor above
failed once (1/20, 5%) with `ConnectionAbortedError: [WinError 10053]` in
`HTTPConnection.getresponse()` while requesting one of its tool routes. The same
`_start_server()` / `_stop_server()` real `ThreadingHTTPServer` harness is implicated, but this
sample does not establish whether readiness, shutdown, or server-thread exception propagation is
the root cause.

**Classification (Batch B):** REPRODUCED test-infrastructure flake; needs a written Gateway
harness plan. Preserve the route assertions. Do not add retries, widen request timing, or weaken
production safety behavior. `P11.7-FU-2` is duplicate custody and is merged here.

**Triage justification for LOW (2026-08-15):** Every current reproduction is confined to the
test harness's `_start_server()` / `_stop_server()` lifecycle, never an independently driven
`serve_gateway()` path. The observed rate is approximately 5% per full Windows unit run and the
failure has no product effect, so it is a low-priority test-infrastructure investigation rather
than a functional Gateway defect.

### P11-FU-7: Windows Coverage/`sys.settrace` Timing Flake in ACP NDJSON Sanitization Test

**Raised:** 2026-07-27 during the Plan 11.3 Task 1 independent review (operator Vibhanshu).
The failure was observed once in a full-suite run for
`tests/unit/acp/test_stdio_ndjson.py::test_serve_ndjson_sanitizes_request_processing_response_and_stderr`;
the same test passed 2/2 when run in isolation. The same failure pattern has previously
recurred during Plan 10.1 and Plan 11.1 verification.

**Origin:** Repeated diagnosis identifies coverage instrumentation / `sys.settrace` timing
sensitivity racing with the test's `asyncio.wait_for(..., timeout=1)`. This is a test-harness
timing flake, not an identified defect in ACP stdio or NDJSON production behavior. The
failure concerns the test's scheduling deadline under instrumentation and must not be
re-diagnosed as an ACP protocol or sanitization regression at each plan pickup.

**Designated slice:** [Plan 11.16](2026-08-15-plan-11-16-p11-fu-7-19-deadline-seams.md). Test-only
ACP NDJSON wall-clock removal; do not re-diagnose as ACP production behavior.

**Acceptance criteria:** A future pickup must:

- reproduce or disposition the failure under the relevant Windows full-suite and coverage
  configurations, including a clean isolation comparison;
- verify the diagnosis against the test's `asyncio.wait_for(..., timeout=1)` deadline and
  coverage / `sys.settrace` instrumentation timing, distinguishing it from a production
  stdio/NDJSON failure;
- apply a reviewed, narrowly scoped test-infrastructure remedy (or document a durable
  non-reproduction/disposition) without weakening the assertions that request-processing,
  response, and stderr sanitization remain correct;
- demonstrate that the remedy does not hide genuine ACP stdio/NDJSON regressions and record
  the exact Windows, pytest, coverage, and test-suite conditions used; and
- preserve the existing independent test evidence, with no production-code change claimed
  unless new evidence establishes a separate production defect.

**Related prior art:** Follow the Windows/test-infrastructure flake custody pattern used by
`P11-FU-5` (WinError 6/50 subprocess handle-duplication) and `P11-FU-6` (gateway `test_server`
port/teardown race). This item is distinct: its established mechanism is coverage
instrumentation / `sys.settrace` scheduling pressure around an `asyncio.wait_for` deadline
in a unit test, with no current evidence of a subprocess-handle or port-teardown defect.

**Status:** Promoted -> [Plan 11.16](2026-08-15-plan-11-16-p11-fu-7-19-deadline-seams.md). Scheduled
2026-08-15. Test-only `wait_for(..., timeout=1)` wrappers were removed in `72f3cc8`; the clock was
not widened. The 25 full Windows `--cov` gate stopped at 4/25 after unrelated `P11-FU-6` WinError
10053. Residual: [Windows evidence](../../../reports/plan-11-16-p11-fu-7-windows-evidence.md).
Not Closed.

**P11-FU-6 gate (2026-08-15):** The 25-process Windows `pytest --cov -q` closure gate is unrun
after 4/25 because P11-FU-6 recurred. Plan 11.17 recorded FU-6 as reproduced, root cause
unestablished; that is not a pass or partial completion.

**Triage note (2026-08-15):** Keep this entry at `MEDIUM` because the Plan 11.16 test-only fix
landed and its remaining closure gate is a bounded evidence task, not unfinished production work.
The 25-run closure gate is explicitly deferred with `P11-FU-6` and is not actionable during the
HIGH/MEDIUM phase; do not read the `MEDIUM` row as permission to claim closure before that gate runs.

**Next pickup:** P11-FU-6 now has its separate recorded open disposition. Resume, count, or claim
this gate only in Plan 11.16's separate evidence lane; Plan 11.17 did not restart or spend it.

**Recurrence:** 2026-08-10 — ACP NDJSON sanitization flake reproduced in the full suite only (passed isolated and in-file); same coverage/`sys.settrace` timing diagnosis; do not widen `P11-FU-6` or merge these entries.

**Batch B recurrence (2026-08-14):** Five Windows full-suite runs under `pytest --cov -q`
produced four clean passes and one failure of
`test_serve_ndjson_sanitizes_request_processing_response_and_stderr` (1/5, 20%). This confirms
the coverage-specific flake at the bounded sample; it does not establish general suite-load as a
necessary condition. **Classification (Batch B):** REPRODUCED test-infrastructure flake; retain the
controlled timing/readiness-seam plan and do not widen either existing one-second deadline.

### P11.5-FU-1: Map live OTLPSpanExporter FAILURE into Gateway QUEUED/retry semantics

**Raised:** 2026-07-29 during Plan 11.5 Task 4 independent operator verification (and matching
linked task review). Confirmed by reading installed
`opentelemetry-exporter-otlp-proto-http` 1.44.0 `OTLPSpanExporter.export()`: every failure path,
including the exporter's internal retry-with-backoff loop, ends in
`return SpanExportResult.FAILURE` and never raises.

**Origin:** Plan 11.5 Gateway `OpenTelemetryTraceExporter` / `_RetryTrackingSpanExporter` only
classifies `exhausted_transient=True` (→ delivery state `queued`) when the delegate *raises*
`TransientTraceExportError`. Against the real SDK exporter that path is unreachable; unit tests
reach `QUEUED` only via an injected `_AlwaysTransientSpanExporter` double. Live collector
outages therefore surface as `failed` rather than `queued`.

**Severity / non-blocking rationale:** Does not crash the agent, does not mask failure as
success, and does not invent cost/accounting. A genuinely transient network hiccup loses
retry-worthiness signal but remains honest (`failed`). Accepted as non-blocking for Task 4
sign-off; must retain named pool custody before Plan 11.5 close.

**Designated slice:** `P11-FEAT-GATEWAY-COST-OBS` (follow-up plan number assigned at pickup —
do not silently fold into an unfinished Task 4/5/8 checkpoint without a reviewed amendment).

**Acceptance criteria:** A future pickup must:

- preserve the four explicit delivery states (`delivered` / `queued` / `failed` /
  `not_configured`) and the rule that a missing endpoint is never reported as successful
  delivery;
- map real `OTLPSpanExporter` / `SpanExportResult.FAILURE` (and any bounded transient class
  the design chooses) into Gateway delivery results without requiring the SDK to raise;
- keep agent-side code free of OTLP/Phoenix endpoints and credentials;
- prove the path with focused unit evidence against a double that returns `FAILURE` (not only
  a raising double), plus at least one live/Phoenix-tier check or an explicit documented
  disposition if live evidence remains Task 8-owned;
- never invent model failure, reverse a completed mutation, or add a model charge when export
  fails.

**Evidence anchors:** Plan 11.5 Task 4 brief/report/review
(`.superpowers/sdd/task-4-*.md` on the Plan 11.5 branch),
`src/optimus_gateway/observability.py`, and `opentelemetry.exporter.otlp.proto.http.trace_exporter`
1.44.0 source for `OTLPSpanExporter.export`.

**Related Task 8 watch (not this FU's scope):** `_emit_spans` starts a fresh empty `Context()`
for every event with no `parent_span_id`, so multiple independent root-level events that share
a wire `trace_id` may land as separate real OTel traces. Task 4 tests only exercise single-root
batches; Plan 11.5 Task 8 real Phoenix evidence must prove or disposition this.

**Status:** Open. Tracked, not yet scheduled; no implementation plan exists. Drafted 2026-07-29 for
operator review of pool custody wording.

**Operator confirmation (2026-08-15):** Confirmed at the default `MEDIUM`. The gap changes live
telemetry delivery-state semantics when the real exporter returns `FAILURE`, but the current detail
also records that it does not crash the agent, report success, or invent cost/accounting. No priority
change is made.

### P11-FU-8: Align `OPTIMUS_LOCAL_GATEWAY_BASE_URL` with `OPTIMUS_GATEWAY_<THING>_BASE_URL` naming

**Raised:** 2026-07-29 by operator ([Vibhanshu]) during backlog triage.
Status for pickup: **Needs deeper investigation before scoping — not ready to implement.**

**Origin / substance:** The name is functionally correct but inconsistent with sibling Gateway
env naming (`OPTIMUS_GATEWAY_TAVILY_BASE_URL`, `OPTIMUS_GATEWAY_OSV_BASE_URL`, and similar all use
`OPTIMUS_GATEWAY_<THING>_BASE_URL`). This identifier breaks the pattern as
`OPTIMUS_LOCAL_GATEWAY_BASE_URL`. Candidate rename: `OPTIMUS_GATEWAY_PROVIDER_BASE_URL`.

**Why this is not a quick rename (confirmed by direct investigation):**

- Blast radius: ~20 files / ~65 occurrences across three source packages (`optimus.acp`,
  `optimus_gateway`, `optimus_security`) and at least six test files
  (`tests/unit/acp/test_launch_gate.py` alone has ~15 occurrences; a dedicated
  `tests/unit/security/test_gateway_base_url_resolution.py` exists for this surface).
- The variable **name** feeds the HMAC security-snapshot fingerprint via
  `compute_secret_fingerprint(value, field_name=name, ...)` in `launch_gate.py`. Renaming
  invalidates existing operators' durable launch approvals and requires an explicit migration
  story — not a silent swap.
- `resolve_launch_candidate` fails closed on any unrecognized `OPTIMUS_*` name. An operator's
  existing `.env.gateway` that still carries the old name would hard-break post-rename unless a
  compatibility alias (or dual-accept window) is designed first.
- At least one referencing design
  (`docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md`)
  is frozen/digest-pinned; its header requires a matching frozen digest for approval, so any
  edit needs a full reviewed amendment rather than an in-place tweak.
- Historical doc surface: nine plan/spec references across six plan/spec identities (the original pre-9.x local-Gateway-service plan, 9.7, 9.96, 9.99, 10.2, 11.4). Frozen/historical docs must be allowlisted by exact path if touched only for census, or
  amended under their own review rules.

**Designated slice / plan shape:** Future small dedicated naming/canonicalization plan
(precedent: Plan 9.99 existed for this class of security-snapshot naming concern). Do **not**
fold a silent rename into an unfinished Plan 11.5 checkpoint or any unrelated feature slice.
Plan number assigned at pickup after the compat-alias + migration design is reviewed.

**Next step before implementation:** Scope a compatibility-alias + durable-approval migration
design (old name accept window, fingerprint transition, fail-closed behavior for mixed/unknown
names, operator docs, and frozen-spec amendment path). Only then commit to the rename target
(`OPTIMUS_GATEWAY_PROVIDER_BASE_URL` or a reviewed alternative).

**Acceptance criteria (draft — refine at pickup):**

- Reviewed design covers alias window, HMAC fingerprint migration, and fail-closed launch-gate
  behavior for stale vs dual names.
- Implementation (when scheduled) updates all live `src` / `tests` / runtime examples /
  `.env*.example` surfaces; does not silently break existing durable approvals.
- Frozen digest-pinned specs are amended under their own approval path or left untouched with
  exact-path historical custody — no broad `docs/**` rewrite.
- Focused regression coverage extends
  `tests/unit/security/test_gateway_base_url_resolution.py` and launch-gate fingerprint tests for
  the chosen migration semantics.

**Evidence anchors:** operator investigation notes (2026-07-29); `src/optimus_security` launch-gate
fingerprint path; sibling env names `OPTIMUS_GATEWAY_TAVILY_BASE_URL` /
`OPTIMUS_GATEWAY_OSV_BASE_URL`; Plan 9.99
(`docs/superpowers/plans/2026-07-22-plan-9-99-credential-uri-security-snapshot-canonicalization.md`)
as process precedent.

**Status:** Open. Tracked, not yet scheduled; **needs deeper investigation / migration design before
scoping**. No implementation plan exists. Filed 2026-07-29 for pool custody.

**Triage justification for LOW (2026-08-15):** The existing environment-variable name is
functionally correct, so there is no current runtime failure or user-facing behavior loss. This is
a naming/canonicalization design gap whose implementation carries migration risk but no present
functional impact; it belongs at the end of the Plan until a compatibility and durable-approval
migration design exists.

### P11-FU-9: Client-Supplied ACP `mcpServers` Disposition

**Raised:** 2026-07-29 during Plan 11.7 design review after validating the vendored ACP v1 schema.
**Classification:** Protocol-honesty / trust-boundary follow-up; not a Plan 11.7 prerequisite.

**Intake finding (2026-07-29):** ACP requires `mcpServers` on both `NewSessionRequest` and
`LoadSessionRequest`. At raising, Optimus accepted `session/new` while ignoring that field; existing
tests and live payloads sent `[]`. This is not the same system as `P11-FEAT-GATEWAY-MCP`:
ACP `mcpServers` asks the agent to connect outward to client-nominated servers, while Gateway MCP
brokering routes Optimus-owned tool calls through the Gateway. Sequencing Gateway-MCP first would
not resolve the current ACP behavior.

**Designated custody:** This entry owns the cross-lifecycle ACP-input decision for current
`session/new` and future methods, including `session/load`. Plan 11.7 preserves the shipped
posture and records the field without creating a client-nominated connection; it does not claim
that Gateway-MCP implements this capability.

PR #119 subsequently resolved the ignored-`mcpServers` behavior under this entry's acceptance
criteria.

**Acceptance criteria:**

- Decide explicitly whether non-empty client-supplied MCP server arrays are rejected, accepted but
  deliberately unsupported, or honored through a separately reviewed agent-side MCP client.
- Apply the decision consistently to every ACP lifecycle method that carries `mcpServers`; do not
  fix only `session/load` while leaving `session/new` semantically different.
- Preserve the zero-upstream-credential/Gateway trust boundary, reject arbitrary side-effecting connectivity unless
  explicitly authorized, and distinguish client-nominated MCP from Gateway-brokered tools in docs
  and telemetry.
- Add schema-pinned unit tests plus real-client evidence for empty and non-empty arrays, with no
  raw server credentials or untrusted configuration persisted or logged.

**Status:** Closed. All nine tasks were implemented and independently reviewed, then merged to
`main` through PR #119 (`9a93137`) on 2026-08-07. Task 9 completed the documentation/custody audit;
the [closure evidence](../../../reports/p11-fu-9-client-mcp-closure-evidence.md) records the
real-dependency and fitness gates. Design:
[`2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-design.md`](../specs/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-design.md)
(frozen body SHA-256 `66606036b37ddc59cf9f2f4c8a713156a1f839fb771679a16937a5263c9ca4a2`). Deferred capabilities remain
owned by their named backlog headers (descriptor pinning/allowlists, HTTP/SSE trust relaxation,
authenticated upstream evidence, Plan 11.8 `WinError 10053` flake) and are not closed by this entry.
Not a hard prerequisite for Plan 11.7 and not owned by `P11-FEAT-GATEWAY-MCP`.

### P11-FU-10: Complete ACP Error-Code Registry Audit

**Raised:** 2026-07-29 during Plan 11.7 design review after the vendored ACP schema exposed the
current `MUTATION_FORBIDDEN = -32002` collision with ACP `RESOURCE_NOT_FOUND`.
**Classification:** Conformance hardening. The unimplemented forced Plan 11.7 subset is owned by
Plan 11.18 / `P11-FU-10` after the 2026-08-15 operator custody transfer.

**Forced Plan 11.7 subset (now Plan 11.18):** On `7da16b6` the live collision was: reserve ACP
`-32002` for `RESOURCE_NOT_FOUND`, relocate ACP-adapter mutation refusal to Optimus code `-32910`,
map duplicate-ID refusal to `-32911`, and remove the duplicate raw wire-code constant from
`src/optimus/runtime/mutation.py`. That forced Plan 11.7 subset is completed by Plan 11.18 because frozen
Plan 11.7 is blocked. The 2026-08-15 operator ruling transferred this custody forward-only; frozen
Plan 11.7 files and amendments are unchanged and `session/load` work is not unblocked.

**This entry also retains the general audit:**

- audit `DUPLICATE_REQUEST_ID = -32001` against ACP/JSON-RPC allocations and actual client
  behavior;
- eliminate remaining production raw error-code literals outside the central ACP registry;
- reduce the Plan 11.7 exact path-and-symbol legacy allowlist to zero; and
- retain frozen historical plan references as expected evidence rather than rewriting history.

**Acceptance criteria:**

- A schema-derived oracle proves registry uniqueness, disjointness from ACP allocations, and
  exclusion from JSON-RPC's complete `-32768…-32000` reserved band for Optimus application codes.
- An AST-based source audit rejects raw JSON-RPC/application code literals outside the central
  registry. Any temporary baseline allowlist is exact by path and symbol and cannot grow.
- Runtime exceptions remain semantic; the ACP adapter alone maps them to wire codes.
- Current user-facing documentation is updated when codes move, while frozen historical plans
  remain byte-for-byte historical records with explicit audit disposition.

**Status:** Closed. Implemented through [Plan 11.18](2026-08-15-plan-11-18-acp-error-code-registry-audit-implementation.md)
and draft PR #158. Mutation refusal moved from ACP `-32002` (`RESOURCE_NOT_FOUND`) to Optimus `MUTATION_FORBIDDEN = -32910`;
duplicate-ID refusal moved from reserved-band `-32001` to `DUPLICATE_REQUEST_ID = -32911`. The
schema-derived registry oracle and the AST oracle (`EXPECTED_LEGACY_ERROR_CODE_SITES == frozenset()`)
prove the allocation. Real-`acpx` 0.12.0 evidence:
[plan-11-18-p11-fu-10-acpx-error-code-evidence.md](../../../reports/plan-11-18-p11-fu-10-acpx-error-code-evidence.md).
Frozen Plan 11.7 bytes are unchanged and `session/load` was not transferred.

**Operator-confirmed triage justification for HIGH (2026-08-15):** Wrong ACP/application codes
reaching real clients can cause protocol errors to be misclassified. The operator confirmed HIGH
and approved transferring the unimplemented forced Plan 11.7 subset to Plan 11.18.

### P11.7-FU-1: Configurable Gateway request timeout for debug/investigation workflows

**Raised:** 2026-07-30 during Plan 11.7 Task 0 Case 1 live Zed evidence capture, by operator
([Vibhanshu]).

**Origin / core problem:** `GatewayClient` hardcodes `timeout_seconds: float = 30.0`
(`src/optimus/gateway/client.py:96`) with no override anywhere — both construction sites in
`bootstrap.py` (lines 72, 129) call `GatewayClient(settings=settings)` unconditionally. During live
Task 0 evidence capture, `z-ai/glm-5.2` via OpenRouter twice exceeded the 30s window on the
identical fixture/task that had succeeded in ~16s moments earlier, terminating the planning loop as
`PLANNING_GATEWAY_COST_UNKNOWN` — a deliberate fail-closed path
(`planning_loop.py:907-912,953-956`: unknown transport cost stops rather than risks a silent
double-charge on retry). That safety behavior is correct and must not be weakened. The problem is
that there is no way to raise the timeout without a code change, so any investigation/debug
workflow is at the mercy of whatever a given model's live latency happens to be.

**Deliverable:** An overridable Gateway request timeout for debug/investigation workflows (e.g. an
env var and/or CLI flag consumed where `bootstrap.py` constructs `GatewayClient`), leaving default
production behavior (30s, fail-closed on unknown cost) unchanged when unset.

**Designated future plan:** None yet named — tracked in this pool until scheduled. Do not silently
fold into Plan 11.7 Task 0 / implementation without a reviewed plan amendment; Plan 11.7 must keep
the fail-closed unknown-cost path unchanged.

**Acceptance criteria (draft — refine at pickup):**

- A documented override raises `GatewayClient`'s effective `timeout_seconds` for a single
  invocation/session.
- Default behavior (30s timeout, fail-closed/no-retry on unknown cost) is unchanged when the
  override is not set.
- The override is discoverable (e.g. `optimus-agent --help`), not just a source-level constant.

**Evidence anchors:** `src/optimus/gateway/client.py:96`; `src/optimus/acp/bootstrap.py:72,129`;
`src/optimus/agent/planning_loop.py:907-912,953-956`; live Task 0 Case 1 Zed captures 2026-07-30
(two consecutive `PLANNING_GATEWAY_COST_UNKNOWN` timeouts on `z-ai/glm-5.2`, ~30s each, vs. a prior
successful ~16s response on the identical fixture/task, same worktree).

**Status:** Closed. Implemented and merged to `main` through PR #123 (implementation commit `d0253be`, merge commit `11448fe`). All Plan 11.9 Definition-of-Done gates were independently re-verified on Windows (focused tests, full suite, coverage ≥80%, Ruff, diff-check, `--help`); no dedicated `reports/` evidence bundle is required for this single-commit CLI-only follow-up.

### P11.7-FU-2: Gateway threaded-test flake under full-suite load

**Raised:** 2026-08-02 during Plan 11.7 origin-A fixture v2 Task 3 review prep.
**Classification:** MISFILED duplicate of `P11-FU-6`; not a Task 3 blocker.

**Origin:** Pre-existing Gateway threaded-test instability observed under full `tests/unit`
suite load (not introduced by origin-A fixture v2 supersession/ledger work).

**Designated custody:** `P11-FU-6` only. Batch B reproduced the same current `test_server.py`
ThreadingHTTPServer/`WinError 10053` class under full-suite load; this entry had no independently
identified node or mechanism.

**Disposition (2026-08-14):** Merge into `P11-FU-6`; do not create a second Gateway harness plan.

**Status:** Closed. Misfiled duplicate; `P11-FU-6` retains the live Gateway harness custody.

### P11.7-FU-3: Committed `plan117_custody_relay.py` docstring `\ufffd` / em-dash corruption

**Raised:** 2026-08-02 during Plan 11.7 origin-A fixture v2 Task 3 review prep.
**Classification:** Docstring hygiene; not a Task 3 blocker.

**Origin:** Pre-existing replacement-character / em-dash corruption in a committed
`tools/plan117_custody_relay.py` docstring (distinct from the Task 3 ASCII fix already applied
to `tools/run_plan117_custody_feasibility.py`).

**Designated custody:** Plan 11.7 deferred follow-ups. Do not silently fold into Task 3
classification seal.

**Acceptance criteria (draft):** Replace corrupted codepoints with ASCII-safe wording; prove
zero `\ufffd` and zero U+2014 remain in that docstring; keep relay behavior unchanged.

**Status:** Open. Tracked, not yet scheduled. Does not block Task 3 classifications.

### P11-FU-11: Plan 11.7 Retry Preflight and Live Session Proof

**Raised:** 2026-08-04 during review of the Plan 11.7 origin-A fixture-v2 execution amendment. This
is a newly discovered custody-gate gap, not a correlation-budget expansion.

**Pre-implementation finding (2026-08-04):** At raising, the bounded runner contained a complete
`assert_prompt_retry_preflight` function, but never called it. The `origin-a-prompt-retry` CLI
branch then validated the fixture hash and printed a hardcoded JSON result; it did not load the
stage ledger, invoke the preflight gate, or verify `live_session_proof`. No runner or relay path
then constructed that proof from the real Zed process, relay connection, and ACP session state. The
source-level line references are recorded in the linked amendment and must be revalidated against
the exact execution commit at pickup.

**Designated slice / plan shape:** `P11-FEAT-ZED-RESUME`, through the standalone
[retry-preflight gate amendment](2026-08-04-plan-11-7-retry-preflight-gate-amendment.md) and its
paired [design spec](../specs/2026-08-04-plan-11-7-retry-preflight-gate-design.md). The amendment
must preserve the frozen Plan 11.7 plan and the two existing origin-A amendments; it does not create
a new Plan 11.x number or authorize a fourth correlation launch.

**Acceptance criteria:**

- `origin-a-prompt-retry` loads and recomputes the immutable stage ledger before any retry action,
  calls `assert_prompt_retry_preflight`, and fails closed on every ineligible ledger state.
- The preflight gate receives a live proof obtained by querying the active relay control path, not
  by trusting a stale file or hardcoded JSON. The proof binds the exact `run_attempt_id`, Zed PID
  and process identity, relay `connection_id`, ACP `acp_session_id`, and current liveness state.
- The retry reuses the existing Zed/relay/ACP session, allocates only the next prompt ordinal, and
  performs no Zed launch, settings mutation, or correlation-ordinal allocation.
- A missing, stale, mismatched, substituted, or unverifiable process/connection/session proof stops
  before reservation or prompt transmission; a second prompt failure or any Zed/relay failure
  remains terminal under the existing custody precedence.
- Unit tests cover ledger/preflight wiring and tamper cases; relay-control tests cover proof identity,
  liveness, PID reuse protection, and channel failure; real-Zed/relay evidence proves the accepted
  same-session retry path and the no-relaunch/no-settings-mutation invariants.

**Status:** Partially implemented. Work on `agent/cursor/p11-feat-zed-resume` reached Task 5 Path A
fail-closed terminal stop (2026-08-05). Real `origin-a-prompt-retry` CLI fail-closed at
`acquire_live_session_proof` with `invalid_probe_retry_control_channel_failure`; offline
verifier classified `unavailable_proof`; `settings_mutated=false`, `zed_launched=false`; no
correlation ordinal 4. Accepted same-session live retry was **not** obtained (dead origin-a-3
session + exhausted correlation budget). Evidence:
[path-a-terminal-seal](../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/path-a-run/path-a-terminal-seal.json).
Public gate signature supersession vs digest-pinned amendment Required interfaces is recorded as a
non-digest current-state note (Task 6). Remains open only for independent reviewer/operator
disposition of Path A and any future budget-expansion / live-retry path (separately authorized).

**Triage justification for HIGH (2026-08-15):** This entry governs whether a same-session retry can
be proven safe before reservation or prompt transmission. Its acceptance criteria bind the exact
run, process, relay, and ACP session and require fail-closed behavior for stale or substituted proof;
without the completed gate, the live Zed-resume evidence cannot establish no relaunch, no settings
mutation, and no duplicate correlation allocation. That safety-critical custody impact warrants
HIGH even though the current implementation stops safely on the failed Path A attempt.

### P11-FU-12: MCP OAuth 2.1 Lifecycle

**Raised:** 2026-08-05 by the approved MCP Gateway architecture redline.

**Designated custody:** This entry owns a future MCP OAuth 2.1 lifecycle design; a Plan 11.x number
is assigned only when it is picked up.

**Rationale and acceptance boundary:** v1 has static credential profiles only. OAuth acquisition,
token custody, and step-up are absent. A future design must keep automatic same-binding refresh
distinct from reapproval-triggering grant, issuer, resource, subject, scope, client, store, or
policy rotation.

**Status:** Closed. Won't-do because Plan 11.12 retired the Gateway MCP feature. This follow-up
targeted Gateway-brokered OAuth 2.1 lifecycle that no longer exists. Identifier preserved.

### P11-FU-13: Deferred MCP Capabilities and Long-Lived Interaction

**Raised:** 2026-08-05 by the approved MCP Gateway architecture redline.

**Designated custody:** This entry owns future prompts, resources, elicitation, completion,
subscriptions, tasks, and resumable discovery-cursor checkpoints; a Plan 11.x number is assigned
only when it is picked up.

**Rationale and acceptance boundary:** These capabilities need new trust and user-experience
vocabulary. Roots are not access control; sampling reverses the prompt/cost direction and retains a
separate double-human-approval and linked-accounting gate. External MCP logging remains unable to
alter Optimus audit logging.

**Status:** Closed. Won't-do because Plan 11.12 retired the Gateway MCP feature. This follow-up
targeted Gateway-brokered prompts, resources, elicitation, completion, subscriptions, tasks, and
resumable discovery that no longer exist. Identifier preserved.

### P11-FU-14: MCP Registry Discover-and-Connect

**Raised:** 2026-08-05 by the approved MCP Gateway architecture redline.

**Designated custody:** This entry owns future MCP catalog, discover, install, update, connect, and
activation semantics; a Plan 11.x number is assigned only when it is picked up.

**Rationale and acceptance boundary:** Catalog metadata is not code trust or operator approval.
Automated install, update, or connect would invalidate v1's preprovisioned-only safety answer.
This is explicitly distinct from ACP registry publication identity and release work under
`P11-FEAT-REGISTRY`.

**Status:** Closed. Won't-do because Plan 11.12 retired the Gateway MCP feature. This follow-up
targeted Gateway catalog/discover/install/update/connect semantics that no longer exist. Identifier
preserved. Distinct from ACP registry publication identity under `P11-FEAT-REGISTRY`.

### P11-FU-15: MCP Tool Search and Context Minimization

**Raised:** 2026-08-05 by the approved MCP Gateway architecture redline.

**Designated custody:** This entry owns future semantic per-turn tool selection and context
minimization; a Plan 11.x number is assigned only when it is picked up.

**Rationale and acceptance boundary:** v1 bounds and records an operator-selected descriptor subset,
but provides no semantic per-turn selection seam and no code-mode sandbox.

**Status:** Closed. Won't-do because Plan 11.12 retired the Gateway MCP feature. This follow-up
targeted Gateway-brokered semantic per-turn tool selection that no longer exists. Identifier
preserved.

### P11-FU-16: Reverse Research-to-Documentation Freshness Gate

**Raised:** 2026-08-05 by the approved MCP Gateway architecture redline.

**Designated custody:** This entry owns a future reverse research-to-authoritative-documentation
freshness gate; a Plan 11.x number is assigned only when it is picked up.

**Rationale and acceptance boundary:** Current traceability catches normative document requirements
missing from specifications, but not research or implementation learning that is absent from the
authoritative documents. The generalized OWASP material lands in the current architecture amendment
as `REFERENCE — Cross-cutting`; it is not deferred under this entry, and reference voice must not
become a phantom requirement.

**Status:** Open. Tracked, not yet scheduled.

The rejected signed per-call capability design is a decision record, not deferred work. It creates no
sixth MCP follow-up without a real multi-user or off-box threat model.

### P11-FU-22: Durable effect-aware MCP indeterminate-call custody

**Raised:** 2026-08-06 during Plan 11.8 Task 7 closure review.

**Designated custody:** This entry owns durable effect-aware MCP indeterminate-call custody: read-only
explicit re-invocation and side-effecting operator-acknowledgment hold across agent restart. The
follow-up identifier and Plan 11.x number are assigned only when this item is picked up.

**Acceptance criteria:** Extend `PreToolGuard` and its approval store so a post-dispatch timeout or
loss is durably classified by effect: read-only calls can be explicitly re-invoked with the original
binding and `gateway_request_id`, while side-effecting calls remain held until an operator
acknowledges the outcome. Custody must survive agent restart, preserve no-automatic-redispatch
behavior, and produce auditable disposition and accounting evidence.

**Status:** Closed. Won't-do because Plan 11.12 retired the Gateway MCP feature. This follow-up
targeted Gateway-brokered indeterminate-call custody (`gateway_request_id` re-invocation / hold)
that no longer exists. Identifier preserved.

### P11-FU-23: Durable client-MCP descriptor-surface pinning and named tool allowlists

**Raised:** 2026-08-06 by the P11-FU-9 client-supplied ACP MCP design.

**Designated custody:** This entry owns an optional second-stage durable approval that pins a
discovered client-MCP descriptor surface and supports named tool allowlist selection. The follow-up
identifier and Plan 11.x number are assigned only when this item is picked up.

**Acceptance criteria:** A design must resolve discovery-before-approval ordering without treating a
transport approval as descriptor/content trust; bind a reviewed catalog revision to safe identity;
define drift/review/revocation; and preserve `PreToolGuard` as the per-call authority.

**Status:** Open. Tracked, not yet scheduled.

### P11-FU-24: Client-MCP durable HTTP/SSE trust relaxation

**Raised:** 2026-08-06 by the P11-FU-9 client-supplied ACP MCP design.

**Designated custody:** This entry owns any proposal to relax the equal CLI-ceremony baseline for
durable stdio, HTTP, and SSE transport trust. The follow-up identifier and Plan 11.x number are
assigned only when this item is picked up.

**Acceptance criteria:** Establish a materially safer, reviewable HTTP/SSE-specific trust case;
address URL identity, redirects, DNS rebinding, private-address policy, and record migration; and
show why the new path does not mint durable trust from an in-flow IDE decision.

**Status:** Open. Tracked, not yet scheduled.

### P11-FU-25: Authenticated client-owned MCP upstream evidence

**Raised:** 2026-08-06 by the P11-FU-9 client-supplied ACP MCP design.

**Designated custody:** This entry owns real-dependency evidence for a client-owned authenticated MCP
upstream after the base client path is implemented. The follow-up identifier and Plan 11.x number are
assigned only when this item is picked up.

**Acceptance criteria:** Use an operator-approved non-secret test credential with an independent MCP
server and prove that env/header/query values reach only the intended connection, never model context,
argv, telemetry, evidence, durable records, or another server connection.

**Status:** Open. Tracked, not yet scheduled.

### P11-FU-26: Plan 11.8 Windows `WinError 10053` MCP test flake

**Raised:** 2026-08-06 during the paused Plan 11.8 Gateway-MCP lane's test review.

**Designated custody:** This entry owns investigation of the intermittent Windows connection-aborted
(`WinError 10053`) MCP test failure. The follow-up identifier and Plan 11.x number are assigned only
when this item is picked up.

**Acceptance criteria:** Establish a minimized reproduction or bounded no-reproduction evidence;
separate test-fixture teardown/network timing from product behavior; reproduce on Windows and WSL2
where relevant; and avoid weakening production transport safety or masking the failure with retries.

**Status:** Closed. Obsolete-by-retirement: Plan 11.12 removed the Gateway MCP transport and test
code that this investigation targeted, so the original reproduction criteria can no longer be
performed meaningfully. The observed Windows `WinError 10053` socket-teardown signal is transferred
to still-open `P11-FU-6`, which owns Gateway `test_server` port/teardown flake custody. No production
retry or safety weakening was added.

### P11-FU-27: Publication-Plan Historical-State Reconciliation

**Raised:** 2026-08-11 during the Plan 11.10 closing audit, after the named reconciliation owner was
found only in a gitignored task report and an untracked implementation-plan artifact rather than in
the pool.

**Origin:** The excluded
[`2026-08-05-mcp-gateway-architecture-amendment-publication-plan.md`](2026-08-05-mcp-gateway-architecture-amendment-publication-plan.md)
retains historical Task 10 Steps 1-7 as unchecked and still says the four architecture PDFs await
approval, although their final hashes match
[`verification.md`](../../sources/mcp-gateway-architecture-amendment/verification.md) and PR #113
delivered the publication. Task 11 Step 7 is correctly unchecked and is not part of that correction.

**Designated custody:** This entry owns only the publication plan's historical checkbox/status
reconciliation. Pickup requires a separate reviewed scope and the next linear plan number available
at that time; do not fold the edit into another documentation cleanup.

**Acceptance criteria:** Reconcile Task 10 Steps 1-7 and the stale awaiting-approval prose only
against the four published PDF hashes in `verification.md` and PR #113; preserve Task 11 Step 7
unless independent evidence satisfies it; retain the publication plan's historical evidence; and
avoid changing unrelated architecture or implementation scope.

**Status:** Closed. Plan 11.22 reconciled only the historical Task 10 Steps 1-7 and stale
pending-publication wording after independently verifying the four published PDF hashes against
`verification.md` and merged PR #113. Task 11 Step 7 remains unchecked. Evidence:
[Plan 11.22 reconciliation report](../../../reports/plan-11-22-p11-fu-27-publication-reconciliation.md).

### P11-FU-17: WSL2 native git cannot parse a Windows-git-created linked worktree's `.git` pointer

**Raised:** 2026-08-06 during the MCP Gateway architecture amendment publication plan's Task 11 WSL2
full-suite gate.

**Classification:** Resolved test-infrastructure operating decision; not a code defect.

**Origin:** A linked worktree created by Windows' `git.exe` writes its `.git` file as
`gitdir: D:/Projects/Development/Python/optimus-cost-agent/.git/worktrees/<name>` — a correct,
absolute path for Windows git. When that same worktree is accessed from WSL2 and `git` resolves to
Ubuntu's own `/usr/bin/git` (wins over `/mnt/c/Program Files/Git/...` because native `/usr/bin`
entries sit earlier in WSL's default `PATH`), that Linux git binary cannot parse `D:/...` as
absolute, treats it as relative, and prepends the current directory — producing a self-evidently
mangled path in the error (`fatal: not a git repository:
/mnt/d/.../<worktree>/D:/Projects/Development/Python/...`).

**Reproduction:** Fully deterministic — reproduced identically 3 times across 2 independent reviewer
reruns plus the executing agent's own reconciliation rerun, both during Task 11 and again during
Task 12's final WSL2 suite rerun. Any test that shells out to `git` inside such a worktree fails
with returncode 128 every time, for as long as that worktree exists and is tested via native WSL
git — currently observed via
`tests/unit/docs/test_open_work_pool_hygiene.py::test_product_checkpoint_log_location_remains_gitignored`
(which calls `git check-ignore`), but the mechanism is general and not specific to that one test.

**Suspected cause:** Not a code defect — confirmed root cause is the PATH-resolution mismatch above,
not an assertion or production-code problem. A disposable Git-wrapper diagnostic (redirecting WSL's
`git` to the Windows binary for one run) did make the suite pass, but was correctly not counted as
clean POSIX evidence since it changes what is being tested rather than fixing the underlying
mismatch.

**Related prior art:** A different flake class from `P11-FU-5`/`P11-FU-6`/`P11-FU-7` (those are
Windows-native subprocess/coverage timing races; this is WSL2-against-a-Windows-worktree path
resolution) — do not conflate root causes across these entries at pickup.

**Designated slice:** Resolved by the native WSL clone operating decision; no numbered plan or source
change is required.

**Closure criteria (satisfied 2026-08-14):** Demonstrate the current mounted-worktree failure,
choose a POSIX-valid operating environment, retain both Git-calling assertions unchanged, and prove
they pass there under native `/usr/bin/git`. Record the setup and any mounted-worktree exception
rule so future Linux gates do not re-diagnose the pointer mismatch.

**Evidence anchors:** MCP Gateway architecture amendment publication plan Task 11/12 review notes;
`tests/unit/docs/test_open_work_pool_hygiene.py::test_product_checkpoint_log_location_remains_gitignored`.

**Resolution (2026-08-14):** Linux/CI-parity gates run only from a native WSL clone on the WSL ext4
filesystem (for example `~/src/optimus-cost-agent`), never from a Windows-created linked worktree
under `/mnt/d`. The clone is a normal POSIX checkout, not a linked worktree, so native `/usr/bin/git`
resolves its `.git` metadata end to end. The standing setup and exception rule are in
[`docs/runbooks/local-live-dependencies.md`](../../runbooks/local-live-dependencies.md#12-wsl2-linuxci-parity-gates).

**Rejected alternatives:** A repo-local PATH override to Windows `git.exe` can make the tests pass,
but changes the POSIX implementation being tested and crosses the WSL/Windows boundary for every Git
call. A WSL-created linked worktree fixes this particular pointer yet remains on slower `drvfs` and
introduces mixed-path administrative metadata in the shared `.git` that Windows Git cannot reliably
consume. Neither is the supported gate environment.

**Proof:** On native ext4 clone `/root/optimus-cost-agent-p11-fu-17-proof`, `/usr/bin/git` 2.43.0
at `origin/main` `2770e0f` ran `pytest tests/unit -q` with **2973 passed, 11 skipped, 1 warning**
in 72 wall-clock seconds. The two unchanged former FU-17 selectors
`test_immutable_documents_match_approved_head_blobs` and
`test_product_checkpoint_log_location_remains_gitignored` then passed explicitly (2 passed).
The equivalent isolated mounted-worktree run produced **2971 passed, 11 skipped, 2 failed** in 96
seconds, and its only failures were those two selectors with the documented native-Git `D:/...`
pointer error. Full command, environment, and virtual-environment isolation evidence are recorded in
[`reports/p11-fu-17-wsl-native-clone-evidence.md`](../../../reports/p11-fu-17-wsl-native-clone-evidence.md).

**Status:** Closed. Native WSL clone decision accepted and demonstrated; no test assertion or
production code changed.

### P11-FU-28: WSL2 `uv sync` shared-Windows-`.venv` destruction hazard

**Raised:** 2026-08-14 during corrected Batch A triage on `origin/main`.

**Classification:** Obsolete under the resolved native-WSL-clone operating decision; not a
product-code defect.

**Origin:** A WSL2 `uv sync` against a Windows-hosted worktree can select and replace the
repository's shared Windows `.venv`, corrupting the Windows environment and making the WSL
evidence non-isolated.

**Resolution (2026-08-14):** The accepted `P11-FU-17` native ext4 clone has its own `.venv`.
With `UV_PROJECT_ENVIRONMENT` unset, `uv sync --frozen --extra dev` created
`/root/optimus-cost-agent-p11-fu-17-proof/.venv`. A before/after fingerprint of the dedicated
Windows worktree's `.venv/pyvenv.cfg` was identical (length 184, SHA-256
`9C503845220632572999AAD4D94004D287277EC4971A5230D8A12FCD3EE91AFB`, unchanged UTC mtime).
The supported Linux-parity workflow therefore has no shared Windows environment to destroy.

**Exception rule:** A temporary diagnostic run from a mounted Windows worktree remains unsupported
as Linux-parity evidence and must set `UV_PROJECT_ENVIRONMENT=/tmp/<task>-venv`; if it clobbers a
Windows `.venv`, restore it with Windows `uv sync --frozen --extra dev`. This is an operating note,
not a remaining scheduled follow-up.

**Status:** Closed. Obsolete for supported native-clone gates; the exception rule remains in the
runbook and proof report.

### P11-FU-18: Workspace-identity `ctime` coalescing fail-open

**Raised:** 2026-08-06 during the MCP Gateway architecture amendment publication plan's Task 12 final
WSL2 suite rerun.

**Classification:** Durable-approval workspace-identity security concern; prior test-infrastructure
classification was misfiled.

**Origin:**
`tests/unit/acp/test_trusted_paths.py::TestWorkspaceIdentityRevalidation::test_revalidation_fails_after_workspace_directory_metadata_change`
asserts that adding a file to a directory changes that directory's `st_ctime_ns` (part of the
workspace-identity digest `resolve_workspace_identity`/`revalidate_workspace_identity` use for
path-trust revalidation in `src/optimus/acp/trusted_paths.py`), with no sleep between the two
`stat()` calls. A direct filesystem probe in this WSL2 environment confirmed `st_ctime_ns` can read
identically across two `stat()` calls that bracket a real file-creation write, despite genuine
elapsed wall-clock time between them. Because `resolve_workspace_identity()` binds that value into
the durable workspace identity digest, and `revalidate_workspace_identity()` accepts an unchanged
digest, the coalescing can fail open for an in-place workspace-directory change whose path,
device, inode, and Git topology remain unchanged.

**Reproduction:** Nondeterministic. Original isolation probe (2026-08-06): 4 passed, 1 failed in 5
standalone runs. Refined (2026-08-07 Task 7 review): 2 failures in 5 repeated isolated runs on
WSL2 — confirmed as a timing race even without full-suite load, not an order-dependent or
environment-static failure. Not caused by P11-FU-9 Task 7 (different file list).

**Suspected cause:** WSL2's virtual-disk-backed filesystem appears to coalesce or truncate directory
`ctime` updates under some timing conditions, unlike the nanosecond-resolution behavior the test
assumes. This is distinct from `P11-FU-17`: that entry is a git-binary PATH-resolution problem;
this one is filesystem-timestamp granularity/coalescing, and the two must not be conflated at
pickup even though both surfaced during the same WSL2 gate runs.

**Related prior art:** Same general "WSL2 as CI substitute has its own environment quirks" class as
`P11-FU-17`, but a different mechanism. Also loosely related to the Windows-native timing flakes
(`P11-FU-5`, `P11-FU-6`, `P11-FU-7`) in spirit (test asserts on OS-timestamp/scheduling behavior
without a sleep) but on a different platform and different underlying primitive.

**Designated slice:** Plan 11.15. Mechanism remains workspace-identity `ctime` coalescing fail-open.
It must define a cross-filesystem tamper-detection invariant before any production change.

**Acceptance criteria (draft — refine at pickup):**

- Preserve fail-closed revalidation when an authorized workspace changes in place, across the
  supported filesystem matrix; a passing rerun cannot establish this property.
- Design and review a reliable replacement or augmentation for the weak metadata signal. Do not use
  sleeps, retries, or marker skips to conceal it.
- Define migration and durable-approval invalidation behavior before changing the identity digest.

**Evidence anchors:** MCP Gateway architecture amendment publication plan Task 12 review notes;
`tests/unit/acp/test_trusted_paths.py::TestWorkspaceIdentityRevalidation::test_revalidation_fails_after_workspace_directory_metadata_change`;
`src/optimus/acp/trusted_paths.py` (`resolve_workspace_identity`, `revalidate_workspace_identity`).

**Status:** Closed. Plan 11.15 SHA `12b881a28b4a736a0d18ccdf1c02c49b94167e41`. Own evidence: `st_ctime_ns`
removed from v3 identity; non-excluded `added-after-authorization` with equal before/after ctime
fails closed as `WORKSPACE_IDENTITY_CHANGED`/`root_topology_mismatch`
(`test_fu18_equal_ctime_non_excluded_add_is_root_topology_mismatch`, unguarded on Windows and native
WSL). Topology add/remove/rename and symlink-retarget named. Residuals: compiled exclusion drop
locations and path/topology TOCTOU (not content integrity). Reports:
[Windows](../../../reports/plan-11-15-windows-durable-approval-identity-evidence.md),
[WSL](../../../reports/plan-11-15-wsl-durable-approval-identity-evidence.md),
[release](../../../reports/plan-11-15-durable-approval-identity-release.md).
Not closed by `P11-FU-29` Git-retry or preserve-approval evidence.

**Recurrence:** 2026-08-07 during P11-FU-9 Task 4 independent review (operator + Cursor WSL full
`tests/unit` runs). The same node failed intermittently under full-suite WSL/DrvFs load and passed
standalone — same custody as this entry; do not open a duplicate FU.

**Refinement (2026-08-07, P11-FU-9 Task 7 review):** Confirmed flaky even in isolation — 2 failures
in 5 repeated standalone runs on WSL2, not only under full-suite load. Characterization upgraded
from "full-suite-only" to "standalone-reproducible ctime coalescing race"; still not a product defect
and still unrelated to Task 7's file list.

### P11-FU-19: WSL client-SDK operation-deadline supervisor race

**Raised:** 2026-08-07 during P11-FU-9 Task 4 independent review (operator Vibhanshu / Cursor).

**Classification:** Test-harness/supervisor timing race; requires a written reliability plan. Not a
Task 4 feature regression.

**Origin:**
`tests/unit/mcp/test_client_sdk.py::test_operation_deadline_is_enforced` uses a 0.2s
`operation_timeout_seconds` budget around a deliberately slow fake `initialize`. Corrected Batch A
triage on a fresh `origin/main` worktree reproduced 2 failures in 100 standalone WSL2 runs (2%).
Both failures were `MCPSupervisorError(code="SUBMIT_TIMEOUT")` from the outer
`future.result(timeout=1.2)`, rather than the expected `ClientMcpSdkError(code="OPERATION_TIMEOUT")`
from the inner `asyncio.wait_for(..., timeout=0.2)`. One full `tests/unit` WSL2 run passed this
node; its only two failures were the known P11-FU-17 native-Git-pointer tests.

**Mechanism:** The cross-thread supervisor's outer 1.2s wait can expire before the event-loop task
reaches its inner 0.2s timeout. This makes host scheduling the test oracle and exposes either a
supervisor-start/readiness race or an inadequately controlled deadline seam. It is not evidence
that the production 30s default deadline should change.

**Designated slice:** [Plan 11.16](2026-08-15-plan-11-16-p11-fu-7-19-deadline-seams.md). Production
client-MCP deadline unification; Batch A 2/100 standalone WSL correction remains the diagnosis.

**Acceptance criteria (draft — refine at pickup):**

- Preserve the assertion that an over-budget initialize raises
  `ClientMcpSdkError(code="OPERATION_TIMEOUT")`, while removing host scheduling as its oracle.
- Design a controlled supervisor-readiness/deadline test seam; do not widen the 0.2s test budget
  merely to reduce the hit rate, and do not change the production 30s default deadline.
- Establish whether the controlled seam belongs solely in the test harness or requires a
  production supervisor readiness contract before implementation.
- Keep custody distinct from `P11-FU-7` (Windows coverage/trace) and `P11-FU-18` (ctime coalescing).

**Evidence anchors:** P11-FU-9 Task 4 review notes (2026-08-07);
`tests/unit/mcp/test_client_sdk.py::test_operation_deadline_is_enforced`;
`src/optimus/mcp/client_sdk.py`.

**Related prior art:** `P11-FU-7` (NDJSON / coverage timing), `P11-FU-18` (WSL ctime), and the
Task 2 review note that the NDJSON flake remains backlog-owned and non-blocking.

**Status:** Closed. Plan 11.16 production correction: SDK `open`/`discover`/`call`/streamed-byte
entries use exact `operation_timeout_seconds` and surface `ClientMcpSdkError("OPERATION_TIMEOUT")`.
Direct generic supervisor expiry remains `MCPSupervisorError("SUBMIT_TIMEOUT")`. Evidence:
[Windows](../../../reports/plan-11-16-p11-fu-19-windows-evidence.md),
[WSL](../../../reports/plan-11-16-p11-fu-19-wsl-evidence.md). SHA `6159200`. The 0.2s test budget
and 30s production default were not widened. No retry/replay.

### P11-FU-20: Attach per-server catalog/authorizer to session tool service for real one-call issuance

**Raised:** 2026-08-07 during P11-FU-9 Task 6 independent review (operator Vibhanshu).

**Classification:** Real functional gap on the write-approval path; fail-closed seam is in place
for Task 6.

**Origin:** `AcpDuplexAdapter._mcp_permission_broker_for` originally fabricated a
`ClientMcpOneCallApproval` (`token=one-call-…`, empty `identity_fingerprint`) instead of calling
`ClientMcpCallAuthorizer.issue_one_call_approval`. Root cause: `ClientMcpSessionState._tool_service`
never receives `.register(...)` of a per-server `ClientMcpToolService` during
`disposition_for_new_session` (disposition intentionally never opens transport / builds catalogs).
A fabricated token would fail downstream as `mcp.client.one_call_unknown` after an IDE allow —
misleading ceremony. Task 6 now fails closed (`issue` → `None`) until this attachment exists.
Neither Task 7 nor Task 8 in the frozen P11-FU-9 plan covers attaching a real per-server
catalog/authorizer to the session tool service.

**Designated slice:** P11-FU-9 follow-up (plan amendment or Task 8 scope expansion — assign at
pickup; do not silently fold into Task 6 close). Plan ownership decision (Codex/operator) required
before implementation.

**Acceptance criteria (draft — refine at pickup):**

- On allow_once transport lease (and later discovery), register identity-bound
  `ClientMcpToolService` instances on `ClientMcpSessionState.tool_service`.
- `_mcp_permission_broker_for` / `_issue` must call the real
  `ClientMcpCallAuthorizer.issue_one_call_approval` for the matched server/tool/args digest — never
  fabricate unbound tokens.
- Evidence must exercise the **real** adapter closure (not only `AcpMcpPermissionBroker` with a
  hand-fed `issue_approval` lambda), covering allow → usable one-call token → PreToolGuard ALLOW
  for a write-classified tool under `side_effect_eligible`.
- Preserve fail-closed behavior when no authorizer is registered (return `None`, no fake token).
- Do not open MCP transport merely to attach the authorizer during `session/new` disposition.

**Evidence anchors:** P11-FU-9 Task 6 review (2026-08-07);
`src/optimus/acp/spec.py` (`_mcp_permission_broker_for`);
`src/optimus/mcp/client_disposition.py` (`disposition_for_new_session`);
`tests/unit/acp/test_spec_protocol.py::test_spec_mcp_broker_issue_fails_closed_until_catalog_authorizer_attached`.

**Related prior art:** Same "mock manufactures agreement" shape as Task 5's FakeClientMcpService
gap; disposition-never-opens-transport constraint from P11-FU-9 design §3.

**Status:** Promoted -> [Plan 11.20](2026-08-17-plan-11-20-p11-fu-20-client-mcp-one-call-approval.md). Scheduled
2026-08-18. Unit adapter wiring landed at `d718384` (real registry, authorizer, `PreToolGuard`, fail-closed
broker closure). Residual: seam built and unit-tested; production composition not yet wired. Live
one-call write-approval tier **unrun** (`requires_acpx` session capture incomplete;
`requires_mcp_stdio` catalog pass is not one-call evidence). Evidence:
[release](../../../reports/plan-11-20-p11-fu-20-release.md),
[Task 4 disposition](../../../reports/plan-11-20-p11-fu-20-evidence.md). Not Closed. Frozen P11-FU-9 Task 6
fail-closed evidence is not this item's closure.

### P11-FU-21: Custody Relay Broken-Pipe Exit-Code Propagation Defect

**Raised:** 2026-08-11 during PR #128 guardrails / `clean-environment-recheck` on
`ubuntu-latest` (operator Vibhanshu / Cursor).

**Classification:** MISFILED product bug; not a test-infrastructure flake.

**Origin:**
`tests/unit/tools/test_plan117_custody_relay.py::test_eof_either_direction_and_child_first_exit`
failed once with `assert exit_code == 7` observing `1` — the custody-relay child process exited
`1` instead of the expected `7`. Not a WinError, not an assertion about payload content.

**Environment:** GitHub Actions guardrails / `clean-environment-recheck` on `ubuntu-latest`,
PR #128, full suite (3148 passed, 12 skipped, 116 deselected). Immediate re-run with **no code
change** was green — no durable local reproduction.

**Not caused by PR #128:** that branch never touched any `plan117` path, and the code is
pre-existing on `main` (`128af65` is an ancestor of `origin/main`). The commit immediately
before the failure was docs-only (+25 lines of markdown).

**Batch B root cause (2026-08-14):** In the observed child-first-exit race, the child correctly
exits `7` and the parent-to-child forwarding task then receives the normal `BrokenPipeError` caused
by writing its remaining input to the already-exited child. `run_relay()` records that exception,
sets `REASON_BROKEN_PIPE`, terminates/cleans up, and unconditionally returns `1` whenever a reason
code exists. The relay therefore overwrites the child exit code rather than the test misreading it.

**Related prior art — do not merge:** Distinct from `P11-FU-5` (Windows-specific WinError 6/50
handle duplication) and from `P11.7-FU-3` (docstring `\ufffd` / em-dash corruption in the same
file). Neither entry covers this relay behavior defect.

**Designated slice:** Plan 11.14
([`2026-08-14-plan-11-14-p11-fu-21-custody-relay-exit-code.md`](2026-08-14-plan-11-14-p11-fu-21-custody-relay-exit-code.md)).

**Acceptance criteria:** Define the contract for expected child-first exit and the error precedence
between benign post-exit pipe closure and true relay failure; preserve real relay errors; implement
only after a reviewed product plan; and retain the EOF / exit-code assertions as proof.

**Evidence anchors:** PR #128 CI run that failed then passed on re-run with no code change;
`tests/unit/tools/test_plan117_custody_relay.py::test_eof_either_direction_and_child_first_exit`;
`tools/plan117_custody_relay.py`; precursor Linux socket-path fix `128af65`.

**Resolution (2026-08-14):** Plan 11.14 restores opaque-relay transparency. `BrokenPipeError` with
non-`None` pre-cleanup `proc.poll()` returns that child code and records `child_exited` /
`reason_code is None`. `BrokenPipeError` with `proc.poll() is None` remains exit `1`,
`broken_pipe`, and `REASON_BROKEN_PIPE`. Interruption and recorder-failure paths still force `1`.
A deterministic stdin-boundary injection test fails red at `assert exit_code == 7` observing `1`
before the edit and proves `7` / `child_exit_code == 7` / `child_exited` after it. The unchanged
`test_eof_either_direction_and_child_first_exit` is 200/200 on the native WSL ext4 clone. Full
suite, bare `--cov` >=80, Ruff, pool hygiene, and sealed-artifact hash equality are in
[`reports/plan-11-14-p11-fu-21-custody-relay-exit-code-evidence.md`](../../../reports/plan-11-14-p11-fu-21-custody-relay-exit-code-evidence.md).

**Status:** Closed. Plan 11.14 implemented the known-exit versus unknown-pipe discriminator; PR #128
and Batch B remain the historical discovery record.

### P11.5-FU-2: Consistent local env / Redis / Phoenix / Gateway startup for live runs

**Raised:** 2026-07-29 during Plan 11.5 Task 8 (real Redis / Phoenix / ACP release-evidence
capture), by operator ([Vibhanshu]). Surfaced while attempting live E7 `acpx` capture and
`requires_gateway` evidence and hitting four inconsistent mechanisms for getting local
dependencies running before landing on a workaround.

**Origin / core problem at raising (2026-07-29):** `optimus-agent` startup (`__main__.py`) resolved
runtime configuration from the OS keychain + sensible defaults with **zero required env vars** — the
documented Plan 9.7 / Plan 9.6 Phase C "no `.env` files required" path, confirmed then working. But
`src/optimus/acp/subprocess_env.py`'s `build_acp_subprocess_env` (used by both the Plan 11.5 Task 8
`acpx` evidence tool and the older Plan 9.87 one) imposed a separate, stricter gate that
`OPTIMUS_GATEWAY_URL` / `OPTIMUS_API_KEY` / `OPTIMUS_REDIS_URL` be **explicitly present in the
shell**. That stricter gate is not technically required by the agent contract and is what forced
a manual workaround during Task 8.

**Four divergent mechanisms found on 2026-07-29 (do not add a fifth):**

1. **`optimus-agent` auto-start** (`ensure_local_gateway` / `ensure_local_redis`) — zero env vars,
   keychain-based, non-interactive.
2. **`optimus-trust run-gateway`** — interactive ceremony, TTY-required, displays a config
   snapshot.
3. **`tools/run_local_gateway.sh` / `.ps1`** — look like standalone non-interactive launchers
   (names/docstrings still describe old direct-source behavior) but now just delegate to #2.
4. **`build_acp_subprocess_env`** — a stricter, explicit-env-var gate layered on top of #1 for
   evidence tooling specifically.

**Explicit requirement — consolidate, don't bolt on another option:** The fix must reduce this
to **one clear path**. Preferred direction: make #4 honor #1's proven keychain-only contract. If
evidence-capture truly needs stricter/explicit config, that divergence must be deliberate and
documented — and #3 must be deleted or clearly repointed so it is not a false lead. Whichever
direction, there must be exactly one documented answer to "how do I get local deps running for a
live run," not several scripts that look interchangeable but aren't.

**Also found at raising (2026-07-29):** No launcher existed for **Phoenix** — only an inline
`docker run` hint was buried in a test docstring. Plan 11.6 / PR #97 subsequently added the
`optimus-phoenix` launcher using `arizephoenix/phoenix:latest` on port 6006, with `/healthz` and
port-identity checks, and documented the living runbook. Phoenix is now part of the same local
dependency mechanism rather than an ad-hoc path.

**Deliverable:** One short operator runbook (matching the existing Plan 9.6 Phase C runbook
precedent at
`docs/runbooks/plan-9-6-phase-c-operator-path.md`) that is the **single
source of truth**, backed by code that actually matches what the runbook says — not a doc layered
on top of still-divergent scripts.

**Designated slice / plan shape:** Future small dedicated startup/runbook consolidation plan
(Plan number assigned at pickup). Do **not** silently fold into an unfinished Plan 11.5 Task 8
checkpoint without a reviewed amendment; retain named pool custody before Plan 11.5 close.

**Acceptance criteria (draft — refine at pickup):**

- Exactly one documented, operator-usable path for local Redis + Gateway (+ Phoenix where needed)
  for live/evidence runs.
- `build_acp_subprocess_env` either honors the keychain-only agent contract (#1) or documents and
  tests a deliberate, reviewed divergence — no implicit stricter shell-env gate.
- `tools/run_local_gateway.sh` / `.ps1` either match that single path (names + behavior) or are
  removed/repointed so they cannot mislead.
- Phoenix local startup is part of the same mechanism/runbook (not a fifth ad-hoc docker hint).
- Runbook text and code paths are verified against each other (presence tests and/or a focused
  live smoke that follows the runbook steps).
- Does not invent a fifth launcher family; does not weaken launch-trust / zero-upstream-credential /
  Gateway-only OTLP contracts.
  OTLP contracts.

**Evidence anchors:** Plan 11.5 Task 8 review conversation and evidence attempt (E7 /
`requires_gateway` capture that surfaced all four mechanisms); `.superpowers/sdd/task-8-report.md`
incomplete live E7 / `requires_gateway` dispositions; `src/optimus/acp/subprocess_env.py`;
`tools/run_plan115_acpx_cost_obs_evidence.py`; `tools/run_local_gateway.sh` / `.ps1`;
`optimus-trust run-gateway`; Plan 9.6 Phase C runbook
(`docs/runbooks/plan-9-6-phase-c-operator-path.md`).

**New finding (2026-07-29, discovered while attempting live `requires_gateway`/E7 evidence):** the
established `optimus-redis` (`redis:8`, port 6379) container had stopped — likely from a
machine/Docker Desktop restart since its last use, not a code or process regression. In its
absence, an unrelated project's container (`optimus-plan112-redis`, `redis:7-alpine`, no
TimeSeries module) took over the same default host port. `optimus-agent`'s preflight correctly
detected and rejected the TimeSeries-less Redis — the fail-closed check itself worked as
designed — but there is no protection against an unrelated project's container colliding on the
same default port, and no documented recovery path. This also reconfirms the divergent-mechanism
finding above at the Docker/port layer: separately-named, non-default-port containers
(`optimus-task8-redis` on 16379, `optimus-task8-phoenix` on 16006) were found running alongside
the default-port containers, consistent with different sessions standing up isolated instances
instead of one shared, documented one. The eventual design must nail this down explicitly (e.g. a
project-specific non-default port, or an explicit identity check) rather than depend on ambient
port availability.

**Status:** Closed. On 2026-07-29, Plan 11.6 implemented on
`agent/cursor/plan-11-6-local-startup-consolidation` with commits
`d123779`, `01f7849`, `24158ce`, `1618591`, `ef3dbd8` (Tasks 1–5) and Task 6 live evidence in
[`reports/plan-11-6-local-startup-live-evidence.md`](../../../reports/plan-11-6-local-startup-live-evidence.md)
(plus [`reports/plan-11-6-local-startup-acpx-evidence.md`](../../../reports/plan-11-6-local-startup-acpx-evidence.md)
and WSL residual
[`reports/plan-11-6-local-startup-acpx-wsl-evidence.md`](../../../reports/plan-11-6-local-startup-acpx-wsl-evidence.md)).
Operator runbook:
[`docs/runbooks/local-live-dependencies.md`](../../runbooks/local-live-dependencies.md).
Retain this entry for history; do not reopen without a new deferred-follow-up ID.

## Accepted risks and warnings

Entries in this section record operator-accepted limitations. They are not open work and do not
reserve a future plan number.

### Plan 11.7 accepted risk: `optimus-redis` ACP-session durability boundary

**RISK (accepted by operator 2026-07-30):** `optimus-redis` provides no real durability for
[Plan 11.7](2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md)'s "durable Redis ACP
sessions." Live-inspected container state has no volume mounts, `appendonly no` (periodic RDB
snapshots only), and a default user configured as `nopass ~* &* +@all`; strict loopback binding
mitigates the unauthenticated default-user exposure.

**Consequence:** Container removal loses all ACP session state. Container restart recovers only to
the latest RDB snapshot. The accepted Plan 11.7 meaning of "durable" is survival across
process/agent restarts, not container lifecycle events.

**Revisit trigger:** Revisit only if session-state loss occurs in practice or a future plan—such
as the consolidated local-startup configuration source of truth—already changes Redis persistence
configuration.
In that case, fix persistence once in the consolidated startup mechanism under the single-config
rule.

**Status:** Reviewed disposition. Accepted as-is by the operator on 2026-07-30; recorded warning,
not open work.

## P9.96 Task 9 Disclosed Follow-Ups (Closed; historical Plan 10 custody)

**Raised:** Disclosed by Plan 9.96 Task 9 on 2026-07-23 under the 2026-07-18 scope-conflict ruling.
Plan 9.96 closes only `P9.85-FU-7` and `P9.9-FU-1`; these seven disclosures are named custody, not
silent drops.

**Origin:** `reports/plan-9-96-operator-debug-launch-trust-evidence.md`, limitations table.

**Historical designated future plan:** Plan 10 (retired). These seven distinct stable-ID catalog
entries are now closed; no Plan 10.x slot or new Plan 10 work remains.

| ID | Summary | Priority |
|---|---|---|
| `P9.96-FU-1` | `StartupConfigurationError` missing `optimus-agent:` prefix in `acp/__main__.py` | MEDIUM |
| `P9.96-FU-2` | Duplicated TOCTOU comment block in `acp/__main__.py` | MEDIUM |
| `P9.96-FU-3` | `append_launch_audit_event` docstring says trusted external runtime root but uses `workspace/.optimus` | MEDIUM |
| `P9.96-FU-4` | Latent unroutable `DEFAULT_AGENT_MODEL = "glm-5.2"` in `agent/defaults.py` (ACP path injects `claude-haiku`) | MEDIUM |
| `P9.96-FU-5` | Frozen dataclass exceptions mask real codes via `@contextmanager` (`FrozenInstanceError`) | MEDIUM |
| `P9.96-FU-6` | Frozen plan Task 9 CLI arg-order / PATH assumptions; execution uses `uv run` plus `--workspace-root` before the subcommand (applied; not a code defect) | MEDIUM |
| `P9.96-FU-7` | Approve ceremony writes durable approval with no y/N confirm; bare-shell display rows may be empty when settings are keyring/default-sourced | MEDIUM |

**Acceptance / disposition:** The rows were open until a reviewed implementation or explicit closure
record resolved each one with evidence. `P9.96-FU-6` is an applied execution correction, not a code
defect, and closed through the explicit reviewed disposition below.

**Plan 10.1 dispositions (updated 2026-07-23; the pool's first allocated slot):**

| ID | Disposition | Priority |
|---|---|---|
| `P9.96-FU-1` | **Closed** by Plan 10.1, commit `daccb0d7469814930922eae67a86552435258cf6` ("fix(acp): prefix PreflightFailure and StartupConfigurationError stderr"). Named tests: `tests/unit/acp/test_main_check_config.py::test_check_config_prints_preflight_failure`, `tests/unit/acp/test_main_wiring.py::test_startup_configuration_error_has_agent_prefix`. | MEDIUM |
| `P9.96-FU-2` | **Closed** by Plan 10.1, same commit `daccb0d7469814930922eae67a86552435258cf6` (duplicate TOCTOU comment block removed; one copy retained, verified via `rg -n -F "Plan 9.96, Task 5 Step 7 (TOCTOU matrix): workspace identity is a" src/optimus/acp/__main__.py` returning a single hit). | MEDIUM |
| `P9.96-FU-3` | **Closed** by Plan 10.1, commit `d83953880a15419097e91da262678f736905cccd` ("docs(acp): align launch-audit docstrings with workspace-local runtime root"). Named test: `tests/unit/acp/test_launch_audit.py::test_launch_audit_docs_describe_workspace_local_runtime_root`. | MEDIUM |
| `P9.96-FU-4` | **Closed** by Plan 10.1, commit `cc66d660cd8580eb3b821d0eb25ed04b27605dc0` ("fix(agent): use routable shared default"). Named tests: `tests/unit/agent/test_defaults.py::test_resolve_agent_model_falls_back_to_routable_shared_default`, `tests/unit/optimus_gateway/test_models.py::test_resolve_model_id_accepts_shared_agent_default_for_every_provider`. | MEDIUM |
| `P9.96-FU-5` | **Closed** by Plan 10.1 evidence; no source or test change. Static inventory found zero `@contextmanager`/`FrozenInstanceError` occurrences in `src`/`tests`; the two candidate frozen exceptions (`StartupConfigurationError`, `AcpOutboundError`) only ever construct once via `raise ... from` / `future.set_exception(...)` and never reassign a field post-construction on any real call path. Behavior selector (`tests/unit/acp/test_bootstrap.py`, `test_outbound_errors.py`, `test_trusted_paths.py`, `test_preflight.py`) passed 36 passed, 5 skipped (environment-legitimate skips). Full record: `docs/superpowers/reviews/plan-10-1-review-checkpoints.md`, 2026-07-23T13:20:00Z entry. | MEDIUM |
| `P9.96-FU-6` | **Closed** by reviewed Plan 10.1 disposition; execution correction only, no code change — see the disposition paragraph below. | MEDIUM |
| `P9.96-FU-7` | **Closed** by Plan 10.2 for the remaining effective-row display provenance gap, while Plan 10.1's confirmation-gate half remains part of the same stable finding (commit `278d95bec4e9a62c55c5de1237a61af1ca661309`). Plan 10.2 implementation commit `4350ae6f455c83f6d8a79c2a0bbdfe149755a4ef` ("feat(acp): display effective credential provenance in optimus-trust approve"). Named tests: `tests/unit/acp/test_local_gateway_secrets.py` (shared-secret provenance / wrapper / base-URL keyring ignore), `tests/unit/acp/test_launch_gate.py::TestEffectiveCredentialDisplayRows`, `TestMissingKeyNonDisclosureAndGoldenDigest`, `tests/unit/acp/test_launch_approval_cli.py::test_display_candidate_prints_source_class`. Frozen plan: `docs/superpowers/plans/2026-07-23-plan-10-2-p9-96-fu7-effective-row-display-provenance.md` (SHA-256 `4303D6AD5C44ED62A85A0509C8C87366505D4D470DD7BC4E0B4309BBE6E3C771`). Approval: `docs/superpowers/reviews/2026-07-23-plan-10-2-implementation-plan-approval.md`. Evidence: gitignored `docs/superpowers/reviews/plan-10-2-review-checkpoints.md`. Plan 10.2 does **not** change the approval digest contract; golden digest `f7af89af0acce664b27825e5af9823c25b11579490bccc73e8f82d4ec316f248` remains byte-identical. | MEDIUM |

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

**Status:** Closed. `P9.96-FU-1` through `P9.96-FU-4` and `P9.96-FU-6` are closed by Plan 10.1 (see the
dispositions table above); `P9.96-FU-5` is closed by Plan 10.1 evidence with no source/test change;
`P9.96-FU-7` is **closed** under its original stable ID: Plan 10.1 closed the confirmation-gate half
and Plan 10.2 (commit `4350ae6f455c83f6d8a79c2a0bbdfe149755a4ef`) closed the effective-row display
provenance half. No new catalog ID or Plan 10.x plan document was created by either pickup. The
remaining open items are now carried by this pool, except for the parked, undecided
`P9.85-FU-3` entry above.

## Closed Historical Follow-Ups (formerly tracked lightweight notes)

### Plan 10.3 frozen-plan status correction (historical)

**Status:** Closed.

The frozen Plan 10.3 implementation plan retains its pre-approval draft status because its
approval record pins the plan bytes. The digest-pinned approval record and the roadmap's closed
Plan 10.3 entry are authoritative for the lane's closed state; this pool records the closure
without editing the historical frozen plan.

### `uv.lock` missing direct dependencies: `keyring`, `redis`, and their transitive chain (disclosed 2026-07-23 during Plan 10.1 Task 1)

**Status:** Closed.

At disclosure on 2026-07-23, the committed `uv.lock` was out of sync with `pyproject.toml`, not
just stale: `uv lock --dry-run`
shows 13 packages a regeneration would add, including `keyring` and `redis` (both **direct**
dependencies declared in `pyproject.toml`, not stray transitives) and the Linux SecretStorage
keyring-backend chain (`cryptography`, `jeepney`, `secretstorage`, `cffi`, `pycparser`, `jaraco-*`).
`uv run --locked` and `uv lock --check` both fail on current `main`. Confirmed `cryptography` is
genuinely unimportable in a `--frozen`-synced venv on both Windows and a fresh WSL2 environment
(`ModuleNotFoundError`); `keyring`/`redis` only appear to work locally because of packages left over
from an older install, not because the lock is sound — a fresh clone or Linux CI doing
`uv sync --frozen` gets exactly the lock's packages and nothing else, so `keyring`'s SecretStorage
backend would fail to import there. Traced via `git log`: the lock was last regenerated at `9c1206d`
(2026-07-04) while `pyproject.toml` changed again at `1f7116b` (2026-07-15, Plan 9.9's approval-
ceremony work) — the drift predates Plan 10.1 and passed through several already-merged,
already-reviewed plans undetected.

**Fix:** regenerate the lock (`uv lock`), review the diff for anything beyond the expected
keyring/redis/dotenv chain, then re-run the default test suite and a WSL2 cross-check to confirm
`keyring`/`redis`/`cryptography` all import cleanly from a fresh sync. Not a Plan 10.1 blocker —
Plan 10.1 used `uv run --frozen` as a standing substitute for the plan's literal `--locked` command
text rather than regenerate the lock mid-plan, since that would have been its own scope change; not
scheduled.

**Promoted -> Plan 10.3** (2026-07-24): Closed by
[`2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md`](2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md).
Lock commit `1b152a8` ("chore: refresh uv lock for declared gateway dependencies") adds exactly the
reviewed 13-package chain (`cffi`, `cryptography`, `jaraco-classes`, `jaraco-context`,
`jaraco-functools`, `jeepney`, `keyring`, `more-itertools`, `pycparser`, `python-dotenv`,
`pywin32-ctypes`, `redis`, `secretstorage`); `pyproject.toml` unchanged; `uv lock --check` exits 0.
Windows acceptance: `uv run --frozen pytest -q` → 1495 passed, 20 skipped, 27 deselected.
WSL2 Ubuntu-24.04 disposable fresh-sync import printed `keyring redis cryptography`. No new catalog
ID; this note is closed by Plan 10.3.

### Tools: `SurfaceAuditError` frozen-dataclass CI wart (disclosed 2026-07-23 during Plan 10.1 Task 7)

**Status:** Closed.

At disclosure on 2026-07-23, `tools/verify_plan996_logging_surfaces.py` raised a
`@dataclass(frozen=True)` `SurfaceAuditError`.
When that exception is raised under pytest's generator-based failure capture, pytest teardown can
attempt to attach `.__traceback__` and surface a secondary `FrozenInstanceError` in the CI log.
Standalone `main()` outside pytest raises `SurfaceAuditError` cleanly with no crash — this is a
pytest-harness wart, not a production or `src`/`tests` FU-5 recurrence. Trivial later fix: drop
`frozen=True` on that tools-only exception class (nothing in that type needs immutability). Not a
Plan 10.1 blocker; not scheduled.

**Promoted -> Plan 10.3** (2026-07-24): Closed by
[`2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md`](2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md).
Tools commit `4d1f086` ("fix(tools): allow surface audit errors to carry tracebacks") drops only
`frozen=True` from `SurfaceAuditError`. Named regression:
`tests/unit/tools/test_verify_plan996_logging_surfaces.py::test_surface_audit_error_allows_pytest_traceback_attachment`
(RED `FrozenInstanceError` → GREEN); full tools unit file 13 passed; standalone `main()` still exits
0 with `Plan 9.96 logging-surface audit passed`. No new catalog ID; this note is closed by Plan 10.3.

## Closed custody excluded from the open pool

Plan 9.96's two sole-custody follow-ups (`P9.85-FU-7`, `P9.9-FU-1`) are closed with the Plan 9.96
Task 9 evidence report and are intentionally not listed as open backlog entries.
