# HARDENING-FEAT-RUNTIME-QUALITY Masterplan

> **For agentic workers:** This is a sequencing and custody charter, not an
> implementation plan. Do not change code, dependencies, configuration, evidence,
> or live services directly from this document. Each implementation slice requires
> its own reviewed `hardening-*-implementation.md` child plan. No item is authorized
> merely because it is listed here.

**Goal:** Sequence the accepted Plan 11.26 runtime and duplication remediation
program together with the newly measured hardening work, while preserving one
authoritative custody location for every open item.

**Architecture:** Status authority is a one-way parent projection: consolidated
backlog → this masterplan → individual child plan → that plan's tasks. Each parent
reports the state of its direct children; no document or task declares its own state.
This masterplan owns cross-program sequencing, the exact 16-item new-work scope, and
the status of its 15 independently reviewed child plans. The accepted Plan 11.26
candidate and obligation rows remain historical G6/G7 acceptance evidence rather than
live plan status.

**Tech Stack:** Python 3.14, uv and `uv.lock`, pytest/pytest-cov/coverage.py, Ruff,
Bandit, detect-secrets, ast-grep, Mypy 2.3.x, pip-audit, Dependabot, actionlint,
zizmor, stdlib logging and lifecycle primitives, and the existing Plan 11.26
deterministic audit tooling.

**Spec and evidence authorities:**

- `docs/superpowers/specs/2026-08-29-plan-11-26-acp-runtime-hardening-audit-design.md`
- `reports/plan-11-26-acp-runtime-audit.json`
- `reports/plan-11-26-acp-runtime-audit.md`
- `reports/plan-11-26-terminal-characterization.md`
- `reports/plan-11-26-duplication-candidates.json`
- `reports/plan-11-26-duplication-audit.json`
- `reports/plan-11-26-duplication-audit.md`
- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`

**Governance location:**
`docs/superpowers/plans/hardening-runtime-quality-masterplan.md`. This promoted
document is a governance charter like the Plan 11 milestone charter, not a live
implementation plan.

## Authority chain

Promotion creates exactly one new backlog feature row:
`HARDENING-FEAT-RUNTIME-QUALITY`, priority `HIGH`. That row alone reports this
masterplan's current status. The masterplan does not repeat that status. The row does
not absorb or replace
`P11-FEAT-ACP-RUNTIME-HARDENING`, any `P11.26-CAND-*` row, any `T13-CAND-*` row, any
`P11.26-UNRUN-*` obligation, or `P11-FU-30`.

This masterplan is the fifth root governance document, with its filename present in
the root-governance allowlists in both documentation-hygiene test modules. Its
child-plan board below is the sole status authority for hardening child plans; those
plans do not also receive consolidated-backlog registry rows. Each child plan, in
turn, owns the checked/unchecked state of its own tasks and contains no self-status
field.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| Evidence | Plan 11.26 Tasks 0-12 canonical audit artifacts are committed and accepted through G6 | yes | `P11-FEAT-ACP-RUNTIME-HARDENING` evidence custody | satisfied; no disposition required |
| Evidence | Task 13 candidate inventory and reviewed duplication artifacts are committed and accepted at G7 | yes | `P11-FEAT-ACP-RUNTIME-HARDENING` evidence custody | satisfied; no disposition required |
| Custody | Five runtime candidates, twelve duplication candidates, and three `UNRUN` obligations exist exactly once in the consolidated backlog | yes | consolidated backlog | satisfied; no disposition required |
| Baseline | Mypy 2.3.1 reproduces 191 errors in 42 files across 200 `src/` files | yes | future `hardening-static-type-checking-implementation.md` | satisfied; no disposition required |
| Baseline | Audit-tool baseline reproduces 130 errors in 11 files across 21 tool files | yes | future `hardening-audit-tool-integrity-and-typing-implementation.md` | satisfied; no disposition required |
| Integrity | Fresh Task 13 discovery is byte-identical to the committed candidate inventory at `b62462f` | yes | future `hardening-audit-tool-integrity-and-typing-implementation.md` | satisfied; no disposition required |
| Integrity | A permanent fresh-versus-committed re-derivation assertion exists before audit-tool typing changes | no | future `hardening-audit-tool-integrity-and-typing-implementation.md` | genuinely absent but buildable now; this is the first child-plan gate for audit-tool typing |
| Governance | Independent reviewer accepts this masterplan and the exact 16-item custody register | yes | reviewer and operator | satisfied for charter promotion; child execution remains separately unauthorized |
| Execution | Operator authorizes each child plan separately | no | operator | merely unauthorized; masterplan approval never grants child execution |
| Live evidence | The three existing `P11.26-UNRUN-*` gates become satisfiable | unknown | their existing consolidated-backlog rows | merely unauthorized or externally gated exactly as those rows state; this masterplan does not replace their gates |

## Global constraints

- Status ownership follows exactly one chain: consolidated backlog → masterplan →
  child plans → tasks. The backlog reports the masterplan's status; this masterplan
  reports child-plan status; each child plan reports task status. No level reports its
  own status or duplicates a direct child's status in another register.
- The G6/G7 custody tables are immutable historical acceptance records. This
  masterplan contains no competing status, priority, disposition, or owner projection
  for the 17 accepted candidates or three existing obligations. When accepted work is
  instantiated as a child plan, only the child plan's status appears here.
- The 93 underlying findings remain in their committed, digest-verified artifacts.
  Do not copy finding bodies, member-symbol lists, evidence classifications, or
  reviewer dispositions into this masterplan or a child plan.
- Existing candidates are cited by stable identity and sequenced. Their backlog rows
  continue to own pickup conflicts, owner-to-be, disposition, and next gate.
- The 16 `HARDENING-ITEM-*` identities below are the only new-work custody introduced
  by this program. Adding a seventeenth requires a reviewed forward-only masterplan
  successor and a corresponding backlog feature-scope update.
- `P11-FU-30` remains owned by `P11.26-CAND-2-TELEMETRY-CONTRACT`. The logging child
  plan implements that existing custody; it does not create a second logging item.
- Bounded admission remains owned by `P11.26-CAND-4-QUEUE-BACKPRESSURE`. Absence of a
  semaphore is supporting evidence, not a second queue-backpressure item.
- Resource lifetime remains owned by `P11.26-CAND-1-RESOURCE-LIFETIME`. The new signal
  adapter item is implemented in the same child plan because a signal without an owned
  teardown path, or teardown without a termination adapter, is incomplete.
- The corrected source baseline contains seven `global` statements across four
  modules. This is a classification input, not a blanket removal quota or a seventeenth
  hardening item. Redis bridge loop/thread ownership strengthens
  `P11.26-CAND-1-RESOURCE-LIFETIME`; its separately accepted full-operation deadline
  remains with `P11.26-CAND-4-QUEUE-BACKPRESSURE`. Diagnostic globals are handled by
  `P11.26-CAND-2-TELEMETRY-CONTRACT`. The synchronized outbound counter and the ctypes
  SID-buffer lifetime receive explicit keep-or-migrate dispositions rather than being
  called defects merely because they use `global`.
- Broad diagnostics remain owned by `P11.26-CAND-2-TELEMETRY-CONTRACT` and existing
  `P11-FU-30`. Context propagation, request middleware, decorator coverage, and the
  C15 sink-class correction are phases of that existing work, not new hardening items.
- Diagnostic records and `TelemetryEvent` are different types accepted by different
  sink protocols. Sharing correlation and redaction does not authorize a diagnostic
  record to enter `TelemetryFanout` or reach `gateway_export`.
- Semantic runtime-to-wire selection remains owned by
  `P11.26-CAND-3-SEMANTIC-ERROR-SELECTION`. The new exception-site disposition item
  broadens the assessment corpus without duplicating the accepted candidate.
- Every child filename is descriptive, unnumbered, and begins with `hardening-`.
  Forward-only successors use `_v2`, `_v3`, and so on. Do not allocate a Plan 11.x,
  Plan 12.x, or interstitial number.
- Every child plan contains the CI-enforced `## Prerequisites` table with the exact
  required columns and records real-service authorization separately from technical
  availability.
- Every child plan follows TDD, names focused verification commands, ends each task at
  an independently reviewable gate, and requires separate commit authorization.
- No child plan lowers the 80% production coverage policy, suppresses a security or
  type-checking family globally to obtain green, or claims a live result from a fake.
- Ruff formatting is a coordinated mechanical migration. It must not share a commit
  with behavioral remediation or broad rule-family cleanup.
- Mypy is declared in the dev dependency set as `mypy>=2.3,<3`, and the lockfile records
  the exact accepted version. Ephemeral measurement does not substitute for declared
  project custody.
- `tools/plan1126_runtime_audit/` remains outside the first Mypy ratchet. No audit-tool
  typing change begins until fresh derivation is mechanically compared with the
  committed Task 13 inventory.
- Audit-tool narrowing prefers `typing.cast` and `TypedDict` where runtime validation
  is already established. Do not introduce `assert isinstance` solely to satisfy the
  checker because it creates a new runtime raise path.
- The three `UNRUN` obligations retain their existing authorization and provenance
  gates. Program sequencing never authorizes Redis, Zed, paid calls, or evidence
  promotion.

## Source-of-truth map

| Information | Sole authority | Masterplan treatment |
|---|---|---|
| 29 Tasks 0-12 findings and 18 scope-out entries | Plan 11.26 runtime audit artifacts | cite aggregate and artifact paths only |
| 64 Task 13 findings and 142 confirmed member symbols | Task 13 duplication artifacts | cite aggregate and artifact paths only |
| Five accepted runtime candidate dispositions | consolidated backlog Task 12 custody table | historical G6 acceptance record; reference candidate identity and sequence only |
| Twelve accepted duplication candidate dispositions | consolidated backlog Task 13 custody table | historical G7 acceptance record; reference candidate identity and sequence only |
| Three `UNRUN` obligation states and owners | consolidated backlog Task 12 custody table | reference obligation identity and ordering only |
| `P11-FU-30` state and acceptance | consolidated backlog follow-up entry | route to the existing telemetry candidate only |
| This masterplan's status | single `HARDENING-FEAT-RUNTIME-QUALITY` backlog row | never repeat here |
| Sixteen newly measured hardening items | this masterplan | define stable identity, scope boundary, child plan, and acceptance gate |
| Fifteen child-plan statuses | this masterplan's child-plan board | one row per child plan; no duplicate backlog registry row and no self-status inside the child |
| Task status | owning child plan | checkbox/task table owned by the plan; task does not self-attest |
| Child-plan execution evidence | each reviewed child plan and its reports | link from this board when the parent changes the child status |

## Program inventory boundary

The program sequences, but does not merge, these bodies of work:

| Source body | Count | Custody rule |
|---|---:|---|
| Plan 11.26 Tasks 0-12 findings | 29 findings, 18 scope-outs | immutable evidence; no new custody here |
| Plan 11.26 Task 13 findings | 64 findings, 142 member symbols | immutable evidence; no new custody here |
| Accepted remediation candidates | 17 | existing backlog custody; identity-only sequence below |
| Existing live-evidence obligations | 3 | existing backlog custody; parallel gated sequence below |
| Newly measured hardening work | 16 | new custody under `HARDENING-FEAT-RUNTIME-QUALITY` |

The 93 findings are not implementation tasks. The 17 accepted candidates and 3
obligations are not re-filed. The only newly created work identities are the following
16 rows.

## New-work custody register

This table assigns item scope to a designated child plan. Item identities are not
plans and therefore do not acquire a second plan-status column here; the 15-plan board
below reports the status of the plans that consume them.

| Identity | Measured scope | Designated child plan | Acceptance boundary |
|---|---|---|---|
| `HARDENING-ITEM-RUFF-LINT-RATCHET` | Ruff 0.15.20 finds 1,433 repo-wide / 459 `src/` findings across proposed `C4`, `PERF`, `SIM`, `RET`, `ASYNC`, and `TRY`; `TRY003` alone contributes 1,078 / 351 | `hardening-ruff-lint-ratchet-implementation.md` | Adopt `C4,PERF,RET,ASYNC`, then `SIM`, then `TRY` minus `TRY003` as reviewed tranches; never enable `TRY003` or switch all families on as one cold gate |
| `HARDENING-ITEM-RUFF-FORMAT-MIGRATION` | 249 of 482 Python files require formatting | `hardening-ruff-format-migration.md` | One behavior-neutral formatting changeset, coordinated against active branches, followed by formatter checks in CI and pre-commit |
| `HARDENING-ITEM-COVERAGE-SOURCE-SCOPE` | `--cov=optimus` overrides the configured five-package source list; true aggregate baseline is below policy | `hardening-ci-guardrail-truthfulness-implementation.md` | CI reports all five production packages, preserves the existing Optimus gate, ratchets uncovered packages without lowering policy, and reaches 80% aggregate before closure |
| `HARDENING-ITEM-LOCKFILE-CI-ENFORCEMENT` | CI runs `uv sync --all-extras` without rejecting stale lock metadata | `hardening-ci-guardrail-truthfulness-implementation.md` | CI uses `uv sync --locked --all-extras`; stale `uv.lock` fails instead of being rewritten |
| `HARDENING-ITEM-SECRET-SCAN-SCOPE` | detect-secrets command is explicitly scoped to `src` | `hardening-ci-guardrail-truthfulness-implementation.md` | Repository-relevant text surfaces are scanned with narrow documented exclusions; baseline and hook scopes agree |
| `HARDENING-ITEM-BANDIT-B310` | Five reachable stdlib `urlopen` paths: B310 detects the three direct-call sites (one loopback-defended path and two without in-module scheme guards), while two production calls through default `urlopen_fn` parameters are invisible to Bandit and have no scheme validation in `tool_provider_http.py` | `hardening-ci-guardrail-truthfulness-implementation.md` | Re-enable B310 globally, route all five paths through one shared scheme guard, retain narrow `nosec B310` comments only at the three syntactically detected sites, and enforce a separate exact inventory that detects direct and default-callable paths |
| `HARDENING-ITEM-DEPENDENCY-CVE-SCAN` | No dependency CVE scanner or automated dependency update owner | `hardening-dependency-workflow-security-implementation.md` | Lock-derived pip-audit gate plus Dependabot configuration, with a documented advisory exception and expiry policy |
| `HARDENING-ITEM-WORKFLOW-LINT-SECURITY` | actionlint and zizmor are absent | `hardening-dependency-workflow-security-implementation.md` | Both tools check every workflow; every baseline finding is fixed or narrowly dispositioned before the gate becomes required |
| `HARDENING-ITEM-AUTOSPEC-BOUNDARIES` | 125 Mock/MagicMock constructor calls concentrated in eight files | `hardening-test-double-contracts-implementation.md` | Classify real boundary doubles; use autospec/spec-set against actual contracts; replace value-bag mocks with real models or factories; do not impose a 125-site conversion quota |
| `HARDENING-ITEM-MYPY-SRC-RATCHET` | Joint Mypy 2.3.1 baseline: 191 errors in 42 files, 200 checked | `hardening-static-type-checking-implementation.md` | Declare Mypy as a dev dependency, check all `src/`, use only enumerated per-module transition exceptions, enforce clean modules immediately, and shrink the exception set monotonically |
| `HARDENING-ITEM-AUDIT-INVENTORY-REDERIVATION` | Task 13 verifier checks a self-digest but never compares fresh discovery with the committed candidate inventory | `hardening-audit-tool-integrity-and-typing-implementation.md` | Test re-derives from pinned `b62462f` and requires `canonical_json_bytes(fresh) == committed_bytes`; the assertion passes against the current 176-group artifact |
| `HARDENING-ITEM-AUDIT-TOOL-TYPING` | 130 Mypy errors in 11 of 21 audit-tool files; 28 import-untyped and 66 attr-defined | `hardening-audit-tool-integrity-and-typing-implementation.md` | Begin only after the re-derivation guard; clear stub/config errors first; preserve generated bytes and frozen-artifact verification throughout every typing batch |
| `HARDENING-ITEM-PYSCN-EVALUATION` | Clone/dead-code/complexity tool absent; overlap with accepted Task 13 evidence unknown | `hardening-analysis-oracle-evaluation.md` | Time-boxed independent spike classifies corroboration, genuinely new classes, and noise; it cannot supersede or reopen accepted Task 13 findings |
| `HARDENING-ITEM-SIGNAL-ADAPTER` | No SIGINT/SIGTERM/atexit integration in production source | `hardening-resource-lifetime-and-signals-implementation.md` | Process-boundary adapters invoke the single ordered, bounded, idempotent lifecycle owned by `P11.26-CAND-1-RESOURCE-LIFETIME`; platform differences and forced termination are tested explicitly |
| `HARDENING-ITEM-EXCEPTION-SITE-DISPOSITION` | Raw broad-catch and pass counts exceed the narrow Plan 11.26 assessment; Ruff currently surfaces 41 BLE001 and 20 SIM105 production findings | `hardening-semantic-error-selection-implementation.md` | Produce a unique AST-site inventory and reviewed disposition; cleanup suppression, containment, translation, telemetry, and re-raise are distinguished; only confirmed findings are changed |
| `HARDENING-ITEM-PUBLIC-API-DOCSTRINGS` | 194 of 1,006 mechanically public functions have docstrings; export boundary is not defined | `hardening-public-api-documentation-implementation.md` | Define the supported public API first, select one style, document exported contracts and invariants, and avoid a quota-driven retrofit of every non-underscore function |

## Existing candidate sequence

The following tables deliberately omit owner, status, priority, disposition, surface,
and next gate. Those fields remain solely in the consolidated backlog.

### Runtime candidates

| Existing identity | Sequence wave | Intended child filename | Masterplan relationship |
|---|---|---|---|
| `P11.26-CAND-1-RESOURCE-LIFETIME` | lifecycle foundation | `hardening-resource-lifetime-and-signals-implementation.md` | combined only with the new signal-adapter item; existing custody unchanged |
| `P11.26-CAND-2-TELEMETRY-CONTRACT` | diagnostics after lifecycle contract | `hardening-logging-and-telemetry-implementation.md` | includes existing `P11-FU-30`; no new logging custody created |
| `P11.26-CAND-3-SEMANTIC-ERROR-SELECTION` | semantic remediation | `hardening-semantic-error-selection-implementation.md` | combined only with the new exception-site disposition item |
| `P11.26-CAND-4-QUEUE-BACKPRESSURE` | bounded admission | `hardening-queue-backpressure-implementation.md` | no separate semaphore item is created |
| `P11.26-CAND-5-REPEATABILITY-ATTRIBUTION` | repeatability evidence | `hardening-repeatability-attribution-implementation.md` | retains existing audit custody |

### Duplication candidates

These become the twelve independently reviewable tasks of
`hardening-duplication-remediation-implementation.md`, remain last in the program, and
retain their accepted rank order. The candidate dispositions remain historical G7
evidence; task checkboxes and evidence links live only in that child plan.

| Existing identity | Child-plan task order |
|---|---:|
| `T13-CAND-RUNNER-CONTRACTS` | 1 |
| `T13-CAND-AUDIT-PRIMITIVES` | 2 |
| `T13-CAND-CREDENTIAL-CONTRACTS` | 3 |
| `T13-CAND-SECURITY-TEXT` | 4 |
| `T13-CAND-DOMAIN-HTTPS` | 5 |
| `T13-CAND-LEDGER-ACCOUNTING` | 6 |
| `T13-CAND-REDACTION-LIFETIME` | 7 |
| `T13-CAND-DIRECTIVE-GRAMMAR` | 8 |
| `T13-CAND-EVIDENCE-SERVICE` | 9 |
| `T13-CAND-SHARED-DEFAULTS` | 10 |
| `T13-CAND-REDIS-HEALTH` | 11 |
| `T13-CAND-RETRY-TIMING` | 12 |

## Child-plan status board

This board is the sole status authority for the masterplan's direct children. The
allowed vocabulary is:

- `Not drafted`: the filename and scope are reserved here, but no tracked child plan
  exists;
- `In review`: a tracked child plan exists and is undergoing independent review;
- `Ready`: review and stated prerequisites are satisfied, but execution has not been
  authorized;
- `Active`: execution is separately authorized and at least one task is open;
- `Blocked`: execution started or was ready, but the next task cannot proceed until a
  named external or authority gate changes; and
- `Complete`: the parent has accepted terminal evidence and the child plan is archived.

A filename remains inline code while it is untracked. The parent converts it to a
relative Markdown link only in the same change that creates the tracked child plan;
completion rewrites that link to the same filename under `archive/`. This prevents the
status hub from publishing dangling links to working documents.

| Track | Child plan | Status | Scope owned by that plan | Next status gate |
|---|---|---|---|---|
| `HARDENING-TRACK-RUFF-LINT` | `hardening-ruff-lint-ratchet-implementation.md` | `Not drafted` | `HARDENING-ITEM-RUFF-LINT-RATCHET` | independently reviewed child plan |
| `HARDENING-TRACK-RUFF-FORMAT` | `hardening-ruff-format-migration.md` | `Not drafted` | `HARDENING-ITEM-RUFF-FORMAT-MIGRATION` | independently reviewed child plan and branch-coordination window |
| `HARDENING-TRACK-CI-GUARDRAILS` | [hardening-ci-guardrail-truthfulness-implementation.md](hardening-ci-guardrail-truthfulness-implementation.md) | `Active` | `HARDENING-ITEM-COVERAGE-SOURCE-SCOPE`, `HARDENING-ITEM-LOCKFILE-CI-ENFORCEMENT`, `HARDENING-ITEM-SECRET-SCAN-SCOPE`, and `HARDENING-ITEM-BANDIT-B310` | PR #194 is merged at `0ec91225` with post-merge guardrails passed. The separately approved local-hook UTF-8 repair has accepted Task 1 and corrected Task 2 checkpoints; Fable now assembles Task 3 governance and platform evidence before Codex candidate concurrence and the normal local commit. Preserve production-only CI, commit-time coverage, locked dependency sync and the 34 baseline identities. Wider venues and later coverage/B310 tasks remain separate; no additional child task is released. |
| `HARDENING-TRACK-DEPENDENCY-WORKFLOW` | `hardening-dependency-workflow-security-implementation.md` | `Not drafted` | `HARDENING-ITEM-DEPENDENCY-CVE-SCAN` and `HARDENING-ITEM-WORKFLOW-LINT-SECURITY` | independently reviewed child plan |
| `HARDENING-TRACK-TEST-DOUBLES` | `hardening-test-double-contracts-implementation.md` | `Not drafted` | `HARDENING-ITEM-AUTOSPEC-BOUNDARIES` | independently reviewed child plan |
| `HARDENING-TRACK-STATIC-TYPING` | `hardening-static-type-checking-implementation.md` | `Not drafted` | `HARDENING-ITEM-MYPY-SRC-RATCHET` | independently reviewed child plan after targeted test-double contracts |
| `HARDENING-TRACK-AUDIT-TOOLING` | `hardening-audit-tool-integrity-and-typing-implementation.md` | `Not drafted` | `HARDENING-ITEM-AUDIT-INVENTORY-REDERIVATION` and `HARDENING-ITEM-AUDIT-TOOL-TYPING` | independently reviewed child plan whose first task is the re-derivation guard |
| `HARDENING-TRACK-ANALYSIS-ORACLE` | `hardening-analysis-oracle-evaluation.md` | `Not drafted` | `HARDENING-ITEM-PYSCN-EVALUATION` | independently reviewed time-boxed evaluation plan |
| `HARDENING-TRACK-LIFECYCLE-SIGNALS` | `hardening-resource-lifetime-and-signals-implementation.md` | `Not drafted` | `P11.26-CAND-1-RESOURCE-LIFETIME` plus `HARDENING-ITEM-SIGNAL-ADAPTER` | independently reviewed child plan |
| `HARDENING-TRACK-LOGGING-TELEMETRY` | `hardening-logging-and-telemetry-implementation.md` | `Not drafted` | `P11.26-CAND-2-TELEMETRY-CONTRACT` and existing `P11-FU-30` | lifecycle contract and independently reviewed child plan |
| `HARDENING-TRACK-SEMANTIC-ERRORS` | `hardening-semantic-error-selection-implementation.md` | `Not drafted` | `P11.26-CAND-3-SEMANTIC-ERROR-SELECTION` plus `HARDENING-ITEM-EXCEPTION-SITE-DISPOSITION` | independently reviewed child plan |
| `HARDENING-TRACK-QUEUE-BACKPRESSURE` | `hardening-queue-backpressure-implementation.md` | `Not drafted` | `P11.26-CAND-4-QUEUE-BACKPRESSURE` | independently reviewed child plan |
| `HARDENING-TRACK-REPEATABILITY` | `hardening-repeatability-attribution-implementation.md` | `Not drafted` | `P11.26-CAND-5-REPEATABILITY-ATTRIBUTION` | independently reviewed child plan |
| `HARDENING-TRACK-PUBLIC-API-DOCS` | `hardening-public-api-documentation-implementation.md` | `Not drafted` | `HARDENING-ITEM-PUBLIC-API-DOCSTRINGS` | supported export surface defined and child plan independently reviewed |
| `HARDENING-TRACK-DUPLICATION` | `hardening-duplication-remediation-implementation.md` | `Not drafted` | twelve `T13-CAND-*` tasks in accepted order | all earlier runtime remediation tracks complete and child plan independently reviewed |

**2026-09-06 reconciliation custody.** PR #195 merged at `32f32ef4` with the accepted production-only CI secret scan and bounded Gateway rejected-POST correction. The Gateway correction belongs to the delivered FU-6 work and supersedes the earlier C-CG4 drain; it does not close broader FU-6 reliability obligations. The current PR #194 reconciliation preserves those contents, retains commit-time pytest/coverage, and carries locked dependency sync plus the operator-approved 31 report exceptions in addition to the existing three. Its local delivery at `cd4a3805` is independently accepted, and publication to PR #194 has passed both required CI jobs. The operator has authorized normal merge and post-merge verification; this grants no additional child-task execution. Historical audit acceptance and the other fourteen child-track statuses are unchanged; later coverage/B310 implementation and a wider secret-scan venue are not commissioned by this reconciliation.

No item above is authorized merely by being listed. A transition to `Ready` does not
grant execution authority, and a child plan never edits its own row.

## What is actually usable today

| Capability | Usable now? | Honest boundary |
|---|---|---|
| Canonical Plan 11.26 runtime and duplication evidence | yes | accepted audit evidence and historical dispositions only; it authorizes no remediation |
| Hardening sequencing and custody map | yes | this masterplan is the status authority for its 15 child plans through the promoted backlog row and hygiene tests |
| CI guardrail child implementation plan | yes | Task 0 baseline is reviewer-accepted at `1ff7761`; Task 1 locked synchronization is accepted at `82798bd`; Tasks 2-6 retain separate review, execution, and commit gates |
| Other hardening child implementation plans | no | the remaining fourteen reserved child filenames are untracked and `Not drafted` |
| Required CI and production-only secret scanning | yes | `clean-environment-recheck` and `verify` remain required on main; CI scans tracked text under `src/` and rejects an empty inventory. This candidate's local hook strictly validates selected text as UTF-8 before delegating, without a report-directory exclusion or expanded selection. The baseline remains exactly three frozen-v9 identities plus 31 approved report identities. Task 3 platform evidence and local-delivery acceptance remain separate gates; historical UTF-16 transcripts reject if selected, and existing findings are not closed. |
| New lint, type, dependency, five-package coverage, or B310 gate | no | those child tasks remain open and separately authorized; current CI still reports the existing narrow coverage command until the coverage task lands |
| New lifecycle, logging, error, queue, repeatability, or duplication behavior | no | no production implementation is authorized or claimed |

## Existing obligation sequence

These obligations run as a parallel evidence lane as soon as their own backlog gates
are satisfied. They are not prerequisites for offline guardrail, test-double, or type
checking work, and the masterplan does not authorize them.

| Existing identity | Sequence rule |
|---|---|
| `P11.26-UNRUN-BINDING` | establish the accepted binding/provenance basis before either live dependency obligation |
| `P11.26-UNRUN-REDIS` | run only after its existing binding, revision, and authorization gates are satisfied |
| `P11.26-UNRUN-ZED` | run only after its existing trusted-workspace, installed-artifact, evidence, and authorization gates are satisfied |

Results from these obligations may change prioritization through a reviewed masterplan
successor. They never silently expand an active child plan.

## Program waves

| Wave | Child plans or existing custody | Exit gate |
|---|---|---|
| Governance | promote this charter; create the single HIGH feature row; update governance tests | reviewer accepts exact inventory and no-duplicate-custody proof; docs hygiene is green |
| Guardrail truth | `hardening-ruff-lint-ratchet-implementation.md`; `hardening-ruff-format-migration.md`; `hardening-ci-guardrail-truthfulness-implementation.md`; `hardening-dependency-workflow-security-implementation.md` | existing gates describe what they actually enforce; formatter migration is isolated; new security gates have disposition policy |
| Contract foundation | `hardening-test-double-contracts-implementation.md`; `hardening-static-type-checking-implementation.md` | boundary doubles are contract-bound; Mypy is declared and the `src/` ratchet is enforced |
| Audit-tool integrity prerequisite | first task of `hardening-audit-tool-integrity-and-typing-implementation.md` | fresh discovery is mechanically byte-compared with the committed Task 13 inventory |
| Lifecycle foundation | `P11.26-CAND-1-RESOURCE-LIFETIME` plus `HARDENING-ITEM-SIGNAL-ADAPTER` | one composition-root lifecycle owns ordered, bounded, idempotent teardown and process termination adapters |
| Diagnostics | `P11.26-CAND-2-TELEMETRY-CONTRACT` and existing `P11-FU-30` | C15 sink classes and the local diagnostic protocol exist; request-scoped `ContextVar` middleware supplies breadth before coverage-enforced decorators supply depth; typed domain telemetry remains a separate channel |
| Runtime remediation | `P11.26-CAND-3-SEMANTIC-ERROR-SELECTION`, `P11.26-CAND-4-QUEUE-BACKPRESSURE`, and `P11.26-CAND-5-REPEATABILITY-ATTRIBUTION` child plans | semantic selection, bounded admission, and repeatability attribution close under their existing rows |
| Parallel quality lanes | staged Ruff work; analysis-oracle spike; public API documentation | each new item closes under `HARDENING-FEAT-RUNTIME-QUALITY` without blocking unrelated live obligations |
| Audit-tool typing | remaining tasks of `hardening-audit-tool-integrity-and-typing-implementation.md` | audit-tool Mypy gate is green and frozen/generated bytes remain identical where required |
| Duplication remediation | twelve ordered tasks in `hardening-duplication-remediation-implementation.md` | each accepted candidate receives its own test/review cycle and evidence without creating twelve competing plan-status owners |

Waves express default order, not blanket authorization. Independent guardrail and
workflow-security work may proceed in parallel after its own child plan is approved.
Any reordered dependency is recorded in a reviewed masterplan successor before
implementation.

## Logging child-plan boundary

The later `hardening-logging-and-telemetry-implementation.md` child plan is a migration
of the existing `optimus.acp.debug_trace` diagnostic path, not a greenfield logging
channel. It must preserve these architecture rulings:

1. **Characterize the existing owner first.** `acp_debug_log` already provides local
   NDJSON diagnostics, unconditional `redact_for_telemetry` processing, no stdout
   writes, an authorized in-memory enablement path, and sink-failure containment.
   Freeze those properties in focused tests and inventory its production callers and
   evidence consumers before changing its record schema. Do not introduce a parallel
   diagnostic API and leave this path behind.
2. **Sink-class boundary before broadening.** `TelemetryEvent` remains the typed domain-fact
   channel. Levelled diagnostics use a distinct record type and a local-only sink
   protocol that cannot accept a `GatewayExporterProtocol`. The separation is a type
   and composition boundary, not a `local_only` boolean checked at runtime. C15 is
   closed before broad request or method narration is enabled.
3. **Separate process configuration from request correlation.** The existing
   `_ACTIVE_CONTEXT.session_id` is a debug-trace-session identifier, not an ACP
   request/session identifier. Authorized enablement, path, provenance root, and
   correlation-key material become process-lifetime configuration owned from the
   composition root; they are not copied wholesale into ambient request context.
   Request/run/session correlation uses a separate immutable value in
   `contextvars.ContextVar`; `threading.local` is forbidden. Every scope stores the
   token returned by `set()` and restores it in `finally` with `reset(token)`. Ambient
   context is diagnostic convenience, never authorization or durable identity.
4. **Disposition legacy audit vocabulary.** `run_id="pre-fix"` and `hypothesis_id`
   are not permanent defaults for a production levelled-diagnostic API. The child plan
   inventories their test, evidence-tool, and live-artifact consumers, then either
   migrates them through a versioned compatibility adapter or retains them only in an
   explicitly named audit/evidence mode. It must not silently break existing evidence
   parsers or reinterpret old NDJSON records.
5. **Add levels to the existing path.** Severity and filtering extend the owned
   diagnostic record/sink and remain configurable without source changes. Adding a
   level does not convert diagnostics into `TelemetryEvent` or route them to Gateway
   export.
6. **Two ingress adapters, one scope abstraction.** Framed JSON-RPC reaches
   `JsonRpcDispatcher.dispatch`; concurrent NDJSON requests reach the nested
   `process_request` task and do not call that dispatcher. A shared request-scope
   abstraction is applied once on each path. Do not wrap `handle_one`, `serve`, and
   `dispatch` independently, which would double-count framed traffic. Notifications,
   client responses, parse/framing errors, and id-bearing requests are classified
   separately.
7. **Middleware breadth before decorator depth.** The middleware phase emits one request start and
   one terminal diagnostic with monotonic duration, correlation, outcome, and
   cancellation preservation. The decorator phase instruments the mechanically
   selected method corpus only after middleware is stable and the source Mypy ratchet
   is active.
8. **The source-derived coverage contract is the Python pointcut.** Every freshly
   selected method is classified as `INSTRUMENTED`, `EXPLICIT_BODY`, or `EXCLUDED`
   with a reason. The test re-derives from source and validates decorator resolution
   and stacking; it cannot validate only a stored manifest or its self-digest.
9. **Observation cannot change behavior.** The diagnostic wrapper preserves return
   values and exception/cancellation identity, never retries, suppresses, times out,
   or converts an exception, and contains sink failure. Arguments and return values
   are not logged by default.
10. **One observational implementation, separate behavioral policy.** Shared
   cross-cutting primitives may live in one package, but broad diagnostic advice is
   isolated from deliberately applied `deadline`, retry, and idempotency behavior.
   Behavioral decorators are never selected or coverage-enforced by the diagnostic
   predicate.
11. **Decorator correctness is explicit.** The wrapper supports synchronous and
   asynchronous callables; uses `functools.wraps`, `ParamSpec`, and a fixed stacking
   order; preserves name, module, documentation, signature, and introspection; and
   uses `time.monotonic()` for elapsed time. Descriptor decorators remain outermost;
   operation instrumentation observes retry/cache behavior as one logical call.
12. **Task propagation is bounded.** Child tasks inherit context at creation, so
   request-owned tasks retain it deliberately while detached or process-lifetime
   tasks clear it. Tests cover concurrent-request isolation, nested scopes, task
   creation, cancellation, and reset after every terminal path.
13. **Output and scope exclusions stay explicit.** Diagnostics never write to stdout
    on an ACP serving path and reuse the existing redaction owner. Abstract
    declarations, properties, generators, context-manager factories, tight loops,
    telemetry/diagnostic internals, and secret-bearing transformation helpers require
    explicit disposition rather than automatic wrapping.

The instrumentation decorator emits diagnostic records by default. Domain telemetry
remains explicit at the business event site; a shared correlation value does not turn
method entry/exit narration into a seventeenth `TelemetryEventKind` or send it through
all five telemetry sinks. Logging may observe lifecycle and repeatability outcomes but
does not repair resource ownership, exception selection, swallowed exceptions,
backpressure, or admission.

The logging child plan is drafted section by section only after this masterplan is
accepted. Its implementation remains sequenced after the source Mypy ratchet and the
lifecycle ownership contract.

## Child-plan pickup contract

Every child plan must:

1. run a backlog conflict check for its new item or existing candidate identity;
2. cite this masterplan and the relevant canonical evidence artifact;
3. cite the historical backlog custody row without restating its status, disposition,
   owner, or next gate;
4. state exactly which `HARDENING-ITEM-*` identities or accepted candidates its tasks
   implement, without assigning plan status to those non-plan identities;
5. contain a compliant `## Prerequisites` table;
6. name all files and focused tests before implementation begins;
7. contain no plan-level `Status`, `State`, `Active`, `Blocked`, or `Complete`
   declaration; its parent row in this masterplan owns that projection;
8. own the checked/unchecked state and evidence of its own tasks;
9. require independent review before every behavior-bearing task commit;
10. update this masterplan row in the same change that creates, blocks, readies,
    activates, supersedes, or completes the child plan;
11. on terminal acceptance, move the child to `archive/`, rewrite the parent link and
    parent-owned status to `Complete`, and remove or rewrite every statement in the
    masterplan that the accepted evidence has made false; and
12. leave the frozen G6/G7 tuple rows unchanged while linking terminal evidence from
    the masterplan's child row.

No child plan may claim another child plan's item merely because both touch the same
file. Shared-file conflicts are sequencing constraints, not custody transfers.

### Parent update checklist

Every pull request that changes a hardening child plan or its implementation must:

1. update that child's row in this masterplan, or declare why no update is required;
2. verify that filename/link, status, next gate, and evidence remain mutually true;
3. remove or rewrite claims in the program waves, usability table, prerequisites, and
   logging boundary that have become false;
4. preserve exactly one status owner at every level of the chain; and
5. leave no link to an untracked working document.

## Promotion mechanics

Promotion is one governance/control-plane changeset. It must:

- create `docs/superpowers/plans/hardening-runtime-quality-masterplan.md`;
- modify `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
  with exactly one `HARDENING-FEAT-RUNTIME-QUALITY` feature row at HIGH whose status
  is the sole projection of the masterplan's status;
- add one sentence immediately before each G6/G7 candidate custody table stating that
  the table is a historical acceptance record, not live remediation-plan status;
  preserve every tested custody tuple byte-for-byte;
- modify `tests/unit/docs/test_plan_directory_hygiene.py` to recognize the masterplan
  as a root governance document and derive hardening child-plan placement from the
  15-row masterplan board rather than the consolidated live-plan registry;
- modify `tests/unit/docs/test_open_work_pool_hygiene.py` to recognize the same
  governance document, the exact feature-row projection, the historical-note
  placement, and the prohibition on hardening child rows in the backlog live-plan
  registry;
- create `.github/pull_request_template.md` with exactly one required declaration:
  for example, `Master-plan impact: updated — HARDENING-TRACK-STATIC-TYPING` or
  `Master-plan impact: none: changes do not affect a hardening track`; the author must
  replace the example with the applicable track list or concrete rationale;
- create `tools/verify_masterplan_impact.py` and focused unit tests that reject a
  missing, duplicate, malformed, or empty declaration; require every `updated` track
  to exist in the 15-row board; require the masterplan to be in the changed-file set
  for `updated`; and reject `none` when a hardening child-plan document changes; and
- create `.github/workflows/masterplan-impact.yml`, triggered for pull-request open,
  edit, synchronize, reopen, and ready-for-review events, to run only that verifier
  and its focused tests. PR body data is passed as data, never interpolated into a
  shell command.

It does not create any child plan, add Mypy or another dependency, change `uv.lock`,
modify production source or product-test behavior, close a candidate, run a live
service, or change the three obligation rows. The new verifier and documentation-test
changes are governance enforcement, not authorization for any hardening implementation.

The feature-row projection must include these semantic anchors:

- `HARDENING-FEAT-RUNTIME-QUALITY`;
- `Open` and `HIGH`;
- `hardening-runtime-quality-masterplan.md`;
- `the backlog row owns this masterplan's status`;
- `the masterplan owns its 15 child-plan statuses`;
- `16 new items`;
- `17 existing candidates`;
- `3 existing obligations`;
- `G6/G7 custody tables are historical acceptance records`;
- `no implementation authority`.

## Verification for promotion

Run the focused documentation gates from a clean environment:

```text
uv run --frozen pytest tests/unit/docs/test_plan_directory_hygiene.py -q
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
uv run --frozen pytest tests/unit/tools/test_verify_masterplan_impact.py -q
uv run --frozen ruff check tests/unit/docs/test_plan_directory_hygiene.py tests/unit/docs/test_open_work_pool_hygiene.py tools/verify_masterplan_impact.py tests/unit/tools/test_verify_masterplan_impact.py
git diff --check
git status --short
```

Expected result: both documentation suites and the PR-declaration suite pass; Ruff
and diff checks pass; status contains only the explicitly enumerated governance,
workflow, verifier, template, and test files. No production, integration, live, or
full-suite claim is made by the promotion.

## Program completion

`HARDENING-FEAT-RUNTIME-QUALITY` may close only when:

- all 15 child-plan rows in this masterplan are `Complete` and link to tracked archived
  plans;
- all 16 new items have terminal evidence reachable from their owning child rows;
- the 17 existing candidates have terminal task evidence in their designated child
  plans without rewriting the historical G6/G7 custody tuples;
- the three existing obligations have terminal outcomes in their own backlog rows;
- `P11-FU-30` closes only through its existing telemetry-candidate custody;
- no child plan declares its own plan-level status and no hardening child appears in
  the consolidated live-plan registry;
- the root masterplan remains a status hub for its direct child plans, not a second
  feature backlog or a duplicate task ledger;
- every statement made false by terminal evidence has been removed or rewritten; and
- documentation hygiene proves the final parent-owned status, archive, feature, and
  link state.

Closure of this feature does not, by itself, close
`P11-FEAT-ACP-RUNTIME-HARDENING`, `P11-FEAT-ZED-RESUME`, or any other feature. Their
own backlog rows remain authoritative.

## Reviewer checklist

- [ ] Exactly 16 unique `HARDENING-ITEM-*` identities exist and each is assigned to exactly one child-plan row.
- [ ] Exactly five `P11.26-CAND-*` identities are referenced without copied live state.
- [ ] Exactly twelve `T13-CAND-*` identities are referenced without copied live state.
- [ ] Exactly three `P11.26-UNRUN-*` identities are referenced without copied owner or status.
- [ ] `P11-FU-30` is routed only to the existing telemetry candidate.
- [ ] The 93 findings remain citations to canonical artifacts rather than copied rows.
- [ ] The Prerequisites table contains the CI-required columns and nonempty dispositions.
- [ ] The document contains no declaration of its own status; only the backlog row reports it.
- [ ] Exactly 15 child-plan rows exist, every row has one allowed status, and no child declares its own plan status.
- [ ] The G6/G7 custody tables receive only the historical-record note; their tested tuples remain unchanged.
- [ ] The masterplan is classified as governance; its child board, not the backlog live registry, owns hardening child-plan status.
- [ ] Promotion creates one HIGH feature row and no individual backlog rows for the 16 new items.
- [ ] Untracked child filenames are plain code, tracked children are valid relative links, and completed children link into `archive/`.
- [ ] The `Master-plan impact:` PR declaration and dedicated lightweight workflow are mechanically enforced.
- [ ] The update checklist requires removal or rewriting of statements made false by new evidence.
- [ ] Mypy source and audit-tool work remain separate, with re-derivation guarding audit-tool changes.
- [ ] Ruff formatting is isolated from behavior-bearing work.
- [ ] No live dependency, commit, push, PR, merge, or implementation authority is implied.
