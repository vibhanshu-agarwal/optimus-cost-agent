# Plan 12.2 Context Engine implementation plan — complete v3

> **For agentic workers:** Claude implements the accepted scope; Codex architects and reviews only. The operator replaced per-task reviews with at most four remaining package checkpoints, Fable 5.1 then one consolidated Codex review. Between checkpoints, focused tests and local task commits run every applicable hook except the expressly approved optimus-pytest-coverage skip. Package A is locally accepted at 38a465f with its exact NOT MET residual, and its docs commit/push/PR are authorized after Claude review. The operator accepted the Task 1 contracts and this complete successor on 2026-10-02, releasing CP1–CP3 as offline work; paid/live/service/sandbox/merge authority stays separate. No Codex implementation or unrequested agent dispatch.

**Goal:** Deliver the optional three-strategy Context Engine while preserving the source floor, exact host authority, curated routing and truthful cost accounting.

**Architecture:** A neutral `context_engine` package prepares derived conversation views. Optimus owns source records, selection, ACP configuration and authorization; the Gateway enforces the trusted model-policy snapshot and complete request capacity. Existing usage accounting receives every stage/attempt receipt.

**Tech stack:** Existing Python >=3.14, Pydantic, pytest/pytest-asyncio, Ruff, coverage and setuptools; PyYAML added as a locked runtime dependency, with a custom SafeLoader rejecting duplicate keys, anchors, aliases, `<<` keys and unsupported tags before typed validation; YAML remains the accepted format. Use existing Gateway/Redis/ACP infrastructure; no new provider credential in CORE.

**Spec:** Read the [Task 1 contracts v2](../specs/2026-10-02-plan-12-2-task1-contracts_v2.md) with the [Context Engine design specification v2](../specs/2026-10-01-plan-12-2-context-engine-design_v2.md), first dated 2026-10-01. Read both documents. Historical spec/first-edition baseline `83fafb9606fb81992508554aa302d3b62c603236`; this successor accounts for Package A at `38a465fda38c73712162ab2b144c1d8da3cceeeb`. The frozen first edition derives from reviewed local revision 5, SHA-256 `6FDB902A6DC476E60A1DA2A35633F20EDE7FAFAC06C740F92ADF1F6A833AC18C`. Plan 12.2 is the next linear Plan 12 slice after existing Plan 12.1; current status belongs only to the [sole backlog](2026-07-23-consolidated-deferred-followups-backlog.md). Q1–Q3 are recorded in [ADR-013](../../decisions/ADR-013-plan12-effect-producer-repair.md), [ADR-014](../../decisions/ADR-014-all-session-request-guard-floor-clarification.md) and [ADR-015](../../decisions/ADR-015-cost-stop-removal-sequencing.md). [S2](../../decisions/README.md#rules-for-every-record) also records the operator’s Package A and Docs PR first selections; ADR-013 reproduces their exact question/option text and selected labels. Filing the complete plan releases no remaining tasks.

**v3, 2026-10-04:** a complete successor of v2, which is archived unchanged. Its only changes are this paragraph, the title, the specification links above (now version 2 of each, carrying the CP4 corrections C1–C3 from Codex's final corrections note `2026-10-04-plan12-final-corrections-and-release-draft.md`) and Task 12's allocation wording and correction item. The operator released those corrections on 2026-10-04 for offline implementation only.

## Global constraints

- Frozen ADR-001–012 bytes remain unchanged; accepted completions/corrections use new records. Proposed/Deferred mechanisms are not accepted by this plan.
- `context_engine` imports no `optimus`, `optimus_gateway`, `optimus_security` or `evidence_handoff*` package; host injects sanitized records and model calls.
- Engine-absent source limit remains `524288`; warning remains `used_bytes * 5 >= cap * 4`; projected byte boundary is inclusive at the limit.
- Compaction is default; hybrid pins the first fitting complete turn and has a larger exact tail; sliding keeps newest complete turns and makes zero summary calls.
- Required outcome/effect/approval facts remain exact in all strategies. Model text never grants permission or feeds exact file/skill selection.
- Total context ceiling is `262144`, including output reserve exactly once. Every provider attempt needs a verified route/estimator/output cap.
- Explicit role eligibility precedes per-token price ranking; no general coding qualification or Contributor equivalence test is added. Summarizer quality qualification is mandatory.
- Contributor warning precedes every new host Contributor request/payload, including fallbacks and maintenance; identical bounded transport retries on the same approved route share that disclosure but retain distinct billing identities. Its Standard-only `max` setting is not allowed.
- Product cost controls become alerts only; authorized evaluation/test dollar and call caps remain. Removal of runtime cost stops requires accounting and the accepted D6 unknown-cost/policy successor; Accepted Q3 retains existing finite count/time/repeated-failure bounds without waiting for ADR-009. No invented substitute monetary cap.
- Default pytest/CI success does not establish marked live tiers; report individual exits and pass/fail/skip/unrun evidence.
- Repository promotion, worktree/branch creation, paid calls, committing and operational actions require the authority applicable to that implementing session. This plan supplies no automatic commit step.

## Prerequisites

These findings are planning-time observations. “Unknown” means an explicit early task must establish it, not permission to assume it works.

| Category / prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? | Establish before |
|---|---|---|---|---|
| Frozen merged ADRs and exact source baseline | yes | Operator / reviewers | Not applicable; merge and 18 blobs verified | Task 0 |
| Written Task 1 contracts/complete successor accepted; named backlog slice | yes | Operator, reviewers | Accepted by the operator on 2026-10-02, releasing CP1–CP3 offline; CP4 paid/live/service work remains separately authorized | Each applicable package |
| Isolated latest-main implementation checkout and conflict disposition | unknown | Implementer / operator | Merely unauthorized if creation is needed; verify latest ref/diff and prescribed location/naming at intake | Task 0 |
| Floor-display port reconciled with Plan 12.1 and F3 fixed | yes | Implementer / Codex review | Package A local offline proof accepted; actual production-base/live gates separate | Engine integration |
| Registry, trusted approval binding, capacity/output transport | no | Implementer / Codex review | Genuinely absent but buildable | Paid summaries and registry release |
| D1–D3 measured strategy/source/estimator/reserve policy | no | Claude measures; Codex reviews; operator accepts | Genuinely absent, local/free investigation first; any missing provider contract is genuinely hard pending evidence | Policy activation |
| D4 accepted summary format/fixture and eligible receipts | no | Reviewers / operator | Genuinely absent format/fixtures, buildable; qualification calls merely unauthorized | Paid compaction/hybrid |
| D5 registry/fallback/price-ceiling dispositions | no | Operator / architects | Merely unauthorized pending concrete reviewed snapshot | Registry/fallback activation |
| D6 unknown-cost and alerts policy; governed budget-document succession | no | Operator / Codex; `P9.85-FU-3` | Merely unauthorized / unresolved policy, not a technical impossibility | Task 11 activation |
| D7 accepted guard clarification: full-floor route/estimator proof | no | Operator / architects | Genuinely absent representative full-floor estimator evidence; Q2 interpretation is accepted in ADR-014 | Capacity migration release |
| D8 future bounded-loop/check-in mechanism and cancellation integration | no | Plan 12 owner; `P12.1-FU-2` | Genuinely absent new mechanism; existing 3-turn/30-minute/repeated-failure bounds remain, with interim sequencing accepted in ADR-015 | Future loop behavior only; Q3 accepts interim cost-stop removal after D6/accounting |
| Current free model/endpoint/capability facts | unknown | Implementer / registry maintainer | Genuinely absent verified pickup facts; free external lookup first; inability to verify is genuinely hard for that route | Task 4 |
| P11.26 typed attribution interfaces and error-attempt correlation | unknown | `P11.26-CAND-2-TELEMETRY-CONTRACT` | Genuinely absent verified narrow interface contract; establish first; broad telemetry completion retains its owner | Tasks 5, 11 |
| Correct authoritative WRITE/TEST effect terminals and cancellation boundaries | yes | Plan 12 Task 2 under accepted Q1; Codex drafts/reviews, Claude implements after scope authority | Package A local implementation/real-boundary proof accepted at 13410c8; actual production-base promotion remains a release prerequisite | Attached production activation; offline Tasks 6–12 use synthetic facts |
| Python 3.14, uv, locks, acpx, real supported Zed versions | unknown | Operator owns machine; implementer inventories | Merely unauthorized if tools need setup; no installation assumed | Task 0 / live evidence |
| Real TimeSeries Redis and local Gateway health/ports | unknown | Operator | Merely unauthorized to start/change services; inspect approved state first | Named live tiers |
| Gateway keys and trusted launch/keyring approval | unknown | Operator | Merely unauthorized; no secret export or alternate provider keys | Paid/live model tier |
| Human TTY launch ceremony and real-Zed interactions | no | Operator | Merely unauthorized/manual interaction | Tasks 10, 13 |
| Synthetic qualification/live call envelope: model, route, inputs, output, dollars, attempts | no | Operator approves concrete estimate | Merely unauthorized; no rerun-until-green | Task 8 paid portion / Task 13 |
| Default CI and repo validation commands identified | yes | Implementer | Existing `pyproject.toml` / guardrails workflow; execution not done in this drafting session | Each package gate |

## Review focus

The first hardening gate is Task 2: real operation starts/terminals and canonical effects, including cancellation between a completed WRITE and a suppressed TEST. The following five engine cases retain their named checks.

1. Old permission facts or hostile summary/tool text must never authorize a new mutation; tests belong to Tasks 3, 6 and 9.
2. Engine failure after source exceeds 512 KiB must leave the thread OPEN across repeated refusals and recover on the next healthy attempt; Task 9.
3. A setting change during maintenance/approval and a half-sent picker update must not alter the current turn or erase another picker; Task 10.
4. Late/cancelled receipts and stored-plan execution must charge each actual model attempt once, preserve later known subtotals and mark unknown totals incomplete; Tasks 5 and 11.
5. Prompt growth from files, framing, Unicode and tool evidence must be checked at the final Gateway boundary, including fallback/retry paths; Tasks 4, 5 and 9.

## Delivery packages and order

This remains one Plan 12.2 umbrella with independently rejectable package checkpoints, not new plan numbers or another work pool. The operator chose Package A PR then CP1 and authorized the new cadence. Accepting Task 1 contracts and this complete successor releases the offline B-D scope through the four named checkpoints; paid/live E work remains separately authorized. No per-task reviewer or commit clearance is added.

| Package | Tasks | Independent outcome | Activation dependency |
|---|---|---|---|
| A: intake, first-step hardening and core floor | 0, 2, 3 | Intake, runner effect/cancellation proof and narrow floor/order baseline | Offline accepted locally at 38a465f; docs-first merge/base gates satisfied; docs/push/PR now authorized after Claude review; merge/live separate |
| B: registry and request transport | 4–5 | Approved registry/capacity/output plumbing, free drift tooling | D3/D5/D7; live launch/schema approval separate |
| C: engine contracts and views | 6–8 | Extractable deterministic views, summary gate tooling/receipts | D1/D2/D4; no paid calls before their authority |
| D: host, picker, accounting | 9–11 | Captured attached views, full-set ACP UX, cost-policy migration | Prior packages; accounting/D6 before cost-stop removal under accepted Q3; Task 2 proof before attached activation |
| E: live evidence and delivery | 12–13 | Measured finite limits, real-client evidence, reviewed release claims | Every needed policy/receipt/service/paid prerequisite satisfied |

**Historical execution decision (Package A, completed locally):** the operator selected “Package A (Recommended)” and “Docs PR first (Recommended)” in S2 on 2026-10-01. Claude implements Tasks 0, 2 and 3 in a fresh latest-main worktree. Task 0 remains read-only; Tasks 2/3 start only after the docs PR merges, with a fresh base/drift check. Those historical Task 2/3 reviews and local deliveries are complete. The 2026-10-02 authority releases Task 1 drafting and Package A publication; the operator accepted the contracts and this successor on 2026-10-02, releasing the dependent offline work through CP1–CP3. No paid calls are released. Task 1’s filing subset is handled by the separately authorized docs PR, not silently added to Claude’s implementation scope. Unrelated D6/registry/summary decisions, paid qualification and later engine live evidence do not block this package’s offline technical review. It ends with a reviewed branch. Package A docs commit/push/PR are now authorized after Claude review; merge and live activity remain separate. Actual Zed rendering is not proved by unit tests.

At each task, the implementer writes the named failing tests first, records their initial failure, implements the listed contract, then runs the narrow verification. A reviewer may accept one package while holding another. Checkboxes remain unchecked until their named evidence actually passes. Publication and merge are separate decisions even when package tests pass.

**Build versus activation order:** Task 0 intake first; Task 2 is the first product-code step under accepted Q1 and the Package A selection, after docs-first merge. Task 1's engine/registry/D6 drafting does not block the narrow Task 2 repair; its contracts gate their dependent later tasks. Task 2 passed its focused effect/cancellation review and local delivery; its actual production-base publication remains explicit. Task 3 floor/order can then proceed independently of numeric-policy decisions. Task 1 establishes accepted architecture/schema/error-policy contracts and the successor workflow; it does not require final sizing measurements from Task 12. Tasks 4–11 build/test against explicitly supplied offline fixture policies, in dependency order. Task 12 measures the working paths and records reviewed numeric completions before production activation. Task 11's accounting foundation can precede its cost-stop-removal activation; that activation separately awaits D6/accounting under accepted Q3, not the proposed ADR-009 mechanism. Attached production activation waits for Task 2's reviewed repair on its actual production base, whether delivered earlier or with a later package; Tasks 6–12 may build offline with synthetic terminals. Task 13 requires all relevant activation prerequisites. This ordering avoids a cycle in which final measurements require a deployed engine that itself requires those measurements.

## Checkpoint execution contract (operator direction, 2026-10-02)

This complete successor retains every original task/requirement, replacing obsolete per-task gates.
New Task 1 contracts refine the previously proposed mechanisms; measurement/paid holds remain.
The operator reviewed this combined contract/scope once before CP1 and accepted it on 2026-10-02;
there is no review after each local task.

| Checkpoint | Tasks | Review sequence |
|---|---|---|
| CP1 / B | 4-5 | One scheduled full suite/coverage, Fable 5.1, Claude focused fixes, one Codex review |
| CP2 / C | 6-8 | Same sequence; tooling only, no paid calls |
| CP3 / D | 9-11 | Same sequence; unresolved D6/governed activation holds stated |
| CP4 / E | 12-13 | Same sequence; paid/live/service envelopes separately approved |

Between checkpoints Claude runs focused TDD/checks and commits each completed task with all hooks
except optimus-pytest-coverage. No per-task Codex clearance or intermediate review. Keep failure,
skip and UNRUN evidence; checkpoint review identifies tested full-suite commit and any later focused
fix delta. Do not attribute a full-run PASS to later bytes or erase a failed gate. A safety/integration
problem is handled within that checkpoint; no extra checkpoint or automatic favorable rerun.
Publication/merge remain their applicable operator decisions. ADR-017 is the historical four-line
exception at 38a465f only, not a new-code coverage exemption. Package A's frozen first edition and
raw evidence remain historical; file/archive this complete successor only after acceptance, repairing
frozen relative paths only through the repository's mechanically proven relocation rule.

## File structure and read-only source references

All execution file paths below are repository-relative in the authorized latest-main checkout. The reviewed baseline tree matches the pin. Do not execute this plan in the earlier ADR worktree or sandbox by implication. Verify the checkout against CONTRIBUTING.md and the Evidence and Local Artifact Policy; branch isolation and no upstream do not prevent an explicit push to main.

Existing integration points read for this plan:

- `src/optimus/acp/conversation.py`: canonical serializer, storage admission/cost accumulator; `render_conversation_envelope` line 176, `prepare_admission` line 232.
- `src/optimus/acp/spec.py`: session/turn state, `_planner_inputs` line 318, setters line 494, prompt handler line 624 (admission call 670), refusal line 925, commit line 1018.
- `src/optimus/acp/shapes.py`: mode-only full-set builder line 68; usage shape line 280.
- `src/optimus/agent/runner.py`: skill matching line 209; workspace assembly line 306; plan record matching line 1092; Chat path line 931.
- `src/optimus/agent/models.py`, `planning_loop.py`, `prompts.py`, `state_store.py`: request, budget/planning, history rendering and approval binding.
- `src/optimus/gateway/models.py`, `client.py`; `src/optimus_gateway/models.py`, `responses.py`, `chat_completions.py`, `upstream_client.py`, `model_mapping.py`: request flattening, output/route transport, provider attempts and usage.
- `src/optimus/agent/defaults.py` and `src/optimus/acp/local_infra.py`: shared and local model defaults.
- `tests/fixtures/acp/acp-v1-schema.json`: config options use `id`, setter requests use `configId`, updates carry the full set.

### Task 0: Establish execution intake and every unknown prerequisite

**Historical Package A task:** local offline delivery/acceptance is already recorded. Retained requirements below are provenance, not a direction to redo implementation, tests or per-task reviews. Live/production-base gates retain their separate meaning.

**Files:** read `AGENTS.md`, `CONTRIBUTING.md`, frozen ADR index/records, sole consolidated backlog and governing current specs; authorized filing only in current docs indexes/backlog and the assigned reviewer checkpoint log.

**Consumes:** pinned merge and spec section 14. **Produces:** named package owners/slice allocations, current-main reconciliation, prerequisite inventory and evidence directory; no product change.

- [ ] Read the operator's direct execution scope, including permitted commands/paid boundaries; obtain a suitable isolated checkout under repository naming rules if authorized. Verify branch, HEAD, cleanliness and worktree registration.
- [ ] Check whether session/load, durable history or replay has shipped since the pin. Current main starts fresh history after process restart; if persistence ships first, assign its history-provenance integration to the persistence owner before attached activation. Compare latest `main` with `83fafb9` and review any source drift; never branch from the ADR feature branch. Record the actual implementation base and unchanged ADR blobs.
- [ ] Inventory tooling/services/credentials by approved read-only checks. Do not print secret values, start services or write settings/keyring entries to turn “unknown” into “yes”.
- [ ] Establish existing cancellation/receipt/plan-hash APIs and actual proof gaps. Map P11.26 attribution interfaces and sandbox floor changes to the narrow main paths; do not copy the sandbox wholesale. Record the verified missing WRITE/TEST registration/start/completion, discarded operation controls and unconditional NONE commit. No existing scheduled repair is established. Under accepted Q1, place the narrow repair in Task 2 of this Plan 12 scope; no separate runtime item. Codex drafts the Plan 11.25 correction note; Claude reviews/implements only after scope acceptance. Main-based branch/PR delivery includes hardening; the sandbox remains unfixed until separately synced. Block attached activation until repaired real-boundary evidence; do not turn fixture success into a producer claim.
- [ ] Register intended packages and exception owners in the sole backlog. Flag stale Plan 12.1 summary/registry rows for the owning documentation lane; do not claim that ADR merge alone closed them.
- [ ] Review gate: each unknown has a verified state or a named blocked dependent task. D1–D10 remain open unless a recorded operator disposition exists.

**Verification:** baseline manifest and drift diff, inventory with versions/authority/service states, and prerequisite matrix. “Not tested” is not PASS.

### Task 1: Record policy completions and governed succession

**Files:** new `docs/decisions/ADR-<next-id>-<accepted-subject>.md` records (allocate from actual latest index); mutable `docs/decisions/README.md`, `docs/README.md`, assigned plan/spec; `P9.85-FU-3` in the sole backlog. Governed successors for current Architecture v2.18, LLD v2.41, Guardrails v1.3 and Test Strategy v1.7; governing requirement inventory identified during Task 0.

**Authorship:** Codex drafts ADR completions and governed Architecture/LLD/Guardrails/Test Strategy successors; Claude reviews; the operator accepts and separately authorizes filing. Claude implements the accepted product tasks, not authoring these policy decisions.

**Consumes:** accepted Q1–Q3 plus D1–D10's remaining design/evidence items and concrete proposals available before implementation. **Produces:** reviewed draft ADR completions, accepted architecture/schema/error-policy contracts, governed successor workflow and explicit numeric/paid holds. Task 12 supplies later measured numeric completions; this task does not depend on a finished engine. ADR-013–015 and S2 are filed by the docs-first package; check the actual decision index before allocating any later completion. No governing document version is allocated before its actual current predecessor is checked.

- [ ] Verify the docs-first filed ADR-013–015, S2 source entry and Plan 11.25 correction note against the reviewed package. Their exact Q1–Q3 questions/options/selected labels, typed effort question and recommendation/estimate attribution remain preserved; archived bytes stay unchanged. This verification is a future Task 1 dependency check, not authority to edit merged records. Present the still-open D6 unknown-cost successor concretely; neither automatic maintenance suspension nor retry is adopted silently.
- [ ] Agree summary format/fixture, structural matrix, route/fallback behavior and alert thresholds where required. Preserve accepted initial model roles; unresolved price/Kimi/Auto/review matters stay labelled.
- [ ] Draft the ADR-005 governed successor language: product alerts-only, separate test caps and unchanged safety/context/authorization controls. Update `P9.85-FU-3` acceptance in place; do not add a parallel alerts owner or modify frozen Plan 9.96 approval bytes.
- [ ] Carry ADR-015's accepted Q3 explicitly: accepted Task 11 cost-stop removal depends on D6/accounting, retaining existing planning-count, wall-clock and repeated-failure bounds. ADR-009's future check-in/escalation mechanism and cancellation owner remain separate; retain the known interim loop-stop trade-off without implementing Proposed behavior.
- [ ] Run `uv run pytest tests/unit/docs tests/unit/tools/test_doc_paths.py -q`, the repository's governed-document validators applicable to the chosen successor sources, and `git diff --check`. Expected: all applicable checks pass and frozen predecessor blobs are unchanged.
- [ ] Claude/Codex agree document content; operator separately authorizes filing/publication. Hold only dependent packages when a disposition remains unresolved.

### Task 2: Repair runner effect producers and cancellation as the first code step

**Historical Package A task:** local offline delivery/acceptance is already recorded. Retained requirements below are provenance, not a direction to redo implementation, tests or per-task reviews. Live/production-base gates retain their separate meaning.

**Modify:** `src/optimus/agent/runner.py`, `src/optimus/acp/spec.py`, and **required** `src/optimus/acp/lifecycle.py` for cancellation/denial effect recalculation; the existing narrow `TurnOperationControl` protocol/per-call context only if identity threading requires it. **Tests:** `tests/unit/agent/test_runner.py`, existing lifecycle/conversation/Chat tests; create `tests/unit/agent/test_turn_directive_boundaries.py`, `tests/unit/acp/test_authoritative_effect_commit.py`. **Documentation:** [Plan 11.25 correction note](../reviews/2026-10-01-plan-11-25-effect-instrumentation-correction.md); mutable current indexes and sole-backlog scheduling text under the selected docs-first authority; later implementation-status changes require their corresponding authority. Archived Plan 11.25 is unchanged.

**Consumes:** accepted Q1/ADR-013, existing operation-control protocol and effect vocabulary. **Produces:** the three runner executors register operations, call `try_start` immediately before producers, publish exact terminal results and preserve the exact per-turn control through `_run_approved_from_store`; `_commit_turn` receives the authoritative current effect, not NONE. The renderer/engine later consumes those facts. No new cost ledger, replay port or general cancellation architecture.

- [ ] Write failing producer-spy tests: cancel before approved execution blocks all subsequent READ/WRITE/TEST starts; cancel between WRITE and TEST leaves the completed write and suppresses tests; implicit pre-WRITE READ has its own lease; a denied lease invokes zero producers. Use synchronization at real boundaries, not timing sleeps.
- [ ] Write effect tests: completed WRITE and TEST -> COMPLETE; returned non-zero TEST exit still counts as executed and retains a failing test verdict; successful WRITE plus suppressed TEST -> PARTIAL; all-suppressed -> NONE; possible partial write or uncertain TEST completion -> INDETERMINATE. READ-only and Chat remain NONE. Test real `_commit_turn` projection under each existing outcome/commit eligibility, without inventing commits after indeterminate final delivery.
- [ ] Write tests for typed pre-producer guard denial -> failed_no_effect versus an arbitrary exception after possible start -> failed_effect_unknown. A generic PermissionError/OSError is not proof of zero effect; inspect the actual typed boundary, not error text. Preserve propagated exceptions and existing safety refusals. The existing unsafe-TEST message check is a pre-producer parse refusal, not a lifecycle terminal-classification rule; preserve that distinction without refactoring unrelated parsing.
- [ ] Write deterministic-ID tests: per-call host turn/run identity plus phase/invocation/directive ordinals distinguish repeated paths/commands and implicit reads; concurrent turns never share counters. No model-generated ID or raw path/command grants control. No-control non-ACP callers retain existing behavior.
- [ ] Thread control through approved READ/WRITE/TEST and applicable single-shot/final-plan callers, including `_finish_agent_planning`. Register known WRITE/TEST operations before execution; denial/suppression must be included in the settled effect snapshot even if no later producer runs. Recompute after suppression in request_session_cancel/denied try_start, or expose a locked fresh effect read at commit; lifecycle.py must change. Test completed WRITE plus cancelled TEST directly on TurnControl as well as through commit, rather than relying on a later complete_directive to accidentally refresh an old COMPLETE. Preserve the existing disconnect recomputation. Preserve post-teardown frozen authority and late-diagnostic policy.
- [ ] State the lease grant as the existing start linearization point; take it immediately before each real boundary. Cancellation prevents later starts, without promising to kill an already-running shell command or roll back an already-started write. Read failures never contribute mutation effects. Keep the separate ranged planning READ_MORE path outside this narrow scope; it is read-only. The archived plan excludes planning iterations in Step 8 but lists Planning READ in Steps 3/5. State that as historical ambiguity, not a second proved overclaim or new repair item.
- [ ] Run `uv run pytest tests/unit/agent/test_turn_directive_boundaries.py tests/unit/agent/test_runner.py tests/unit/acp/test_authoritative_effect_commit.py tests/unit/agent/test_plan121_chat_runner.py tests/unit/acp/test_plan121_chat_mode.py -q`, plus the existing lifecycle selectors identified in Task 0; Ruff on changed files and `git diff --check`. Record individual outcomes and meaningful initial failures. These commands are proposed for Claude's later authorized session, not run by Codex.
- [x] Historical Package A exact-blob/evidence review and local technical acceptance recorded; 2026-10-02 cadence supersedes per-task reviews for subsequent packages. The repair reaches main through Plan 12's later authorized main-based PR or PRs. The operator chooses PR boundaries when reviewed work is ready; a single combined engine PR is not assumed. Preserve sandbox code; disclose its same gap until separately synced. Correction-note filing is separate authority and never edits the completed archived plan.

### Task 3: Port the floor presentation fixes and fix F3

**Historical Package A task:** local offline delivery/acceptance is already recorded. Retained requirements below are provenance, not a direction to redo implementation, tests or per-task reviews. Live/production-base gates retain their separate meaning.

**Modify:** `src/optimus/acp/conversation.py`, `spec.py`, `shapes.py`, relevant lifecycle notice path only if needed. **Tests:** existing `tests/unit/acp/test_conversation.py`, `test_plan121_chat_mode.py`; create `tests/unit/acp/test_context_floor_presentation.py`, `test_conversation_model_order.py`.

**Consumes:** existing five-field records and authoritative turn delivery. **Produces:** `render_model_conversation(records: Mapping[int, ConversationTurn]) -> str`; legacy storage serializer retained. This establishes the new absent-engine presentation baseline: 80% warnings and usage updates become visible for the first time; existing source admission calculations remain unchanged.

- [ ] Add failing `test_model_turn_and_field_order`: sequences 1, 2, 9, 10, 11 render numerically with `_RECORD_FIELD_ORDER`; canonical values/blob output stay unchanged.
- [ ] Add failing `test_order_fix_preserves_floor_bytes_and_admission`: Unicode/escaped-string fixtures, exactly 524288 and 524289 projected bytes, warning at 419431; byte counts and floor decisions match the old serializer.
- [ ] Add failing `test_notice_separation_and_cap_end_turn` and `test_floor_usage_live_only`: capacity text remains separated/readable, no provider call on refusal, usage uses floor bytes//4 and complete known cost only, compatible with Chat completion/cancellation.
- [ ] Implement just those behaviors in current main lifecycle; no durable/replay/lease/session-load transplant. Preserve delivery-indeterminate and canonical commit predicates.
- [ ] Run `uv run pytest tests/unit/acp/test_conversation.py tests/unit/acp/test_plan121_chat_mode.py tests/unit/acp/test_context_floor_presentation.py tests/unit/acp/test_conversation_model_order.py -q`. Expected: PASS, including all legacy floor boundaries.
- [ ] Review package A source diff before committing under the implementing session's authority. Real display evidence is Task 13, not established by these unit tests.

### Task 4: Build the neutral registry and route-capacity contract

**Create:** `src/optimus_model_policy/{__init__,registry,validation,capacity}.py`, `defaults.yaml`; `tools/check_model_registry_drift.py`; `tests/unit/model_policy/test_registry.py`, `test_capacity.py`. **Modify:** `pyproject.toml`, `uv.lock` when dependency/package/coverage configuration is approved.

**Consumes:** accepted schema/role/route dispositions. **Produces:** `load_registry(defaults: Path, override: Path | None) -> RegistrySnapshot`; `validate_registry(snapshot: RegistrySnapshot) -> tuple[ValidationIssue, ...]`; `select_eligible_models(snapshot: RegistrySnapshot, role: str) -> tuple[str, ...]`.

Capacity APIs: `estimate_complete_input(request: PackedModelRequest, profile: EstimatorProfile) -> InputEstimate`; `guard_request(request: PackedModelRequest, snapshot: RegistrySnapshot, approved_hash: str) -> CapacityDecision`. Typed packed request includes final messages/material and actual output cap; estimate identifies method/version and framing profile. Decisions return allowed/reason/input/reserve/usable fields, never a monetary debit.

- [ ] Add failing registry tests for nested duplicate keys, anchors, aliases, `<<` keys (including quoted keys), ordinary scalar text containing anchor-like characters, unsafe tags, unknown fields, replacement-list merge, semantic hash stability, drift, explicit role assignments, unqualified summarizer, unsupported reasoning and missing data-use/route facts.
- [ ] Assert the exact role ordering from spec 9.2; GLM Flash has no role, Qwen has no coding role, inventory origin coverage remains valid, and tier membership never grants eligibility. No coding/equivalence task test.
- [ ] Add failing capacity tests: input at `262144 - reserve` allowed; one over refused; reserve counted once; max-output too small refused; each permitted endpoint checked; unknown estimator/alias refused. Include framing, Unicode, escaped JSON and future tool material.
- [ ] Add Q2 representative full-floor tests: exactly 524288 projected English/code bytes plus maximum allowed workspace/tool/evidence material and framing on each enabled absent-engine route, with measured reserves. Separately test Unicode/adversarial estimator safety; never weaken the estimator to force admission. Failure returns a route/floor exception to the operator before release.
- [ ] Add crossed-price tests: configured role blend required, ties use China origin. Do not derive a blend/default ceiling absent its disposition.
- [ ] Implement a custom PyYAML SafeLoader subclass rejecting duplicate keys at every nesting depth, all parsed anchors/aliases, `<<` merge keys, unsafe/custom tags and non-string map keys, followed by strict typed validation. Lock PyYAML as a runtime dependency, not merely transitive dev tooling. Implement immutable validated snapshot and pure capacity functions. Include new production package in coverage and wheel resources.
- [ ] Run the free drift tool against documented public catalog/endpoints. Report ID/window/output/price/capability/expiration/endpoint discrepancies without editing policy automatically. Save dated source snapshots; unresolved endpoint facts bar that route.
- [ ] Run `uv run pytest tests/unit/model_policy -q` and `uv run ruff check src/optimus_model_policy tools/check_model_registry_drift.py`. Expected: PASS and clean lint.

### Task 5: Enforce snapshot, output reserve and disclosed requests in Gateway/launch

**Modify:** `src/optimus/gateway/{models,client}.py`; `src/optimus_gateway/{models,responses,chat_completions,upstream_client,model_mapping}.py`; `src/optimus/acp/{launch_policy,launch_approvals,launch_gate,launch_approval_cli,subprocess_env,bootstrap,local_infra}.py`; `src/optimus/agent/defaults.py`. **Create:** `src/optimus_gateway/model_policy.py`; `tests/unit/optimus_gateway/test_model_policy.py`, `test_context_admission.py`; extend existing request/retry/launch tests.

**Consumes:** Task 4 snapshot/capacity contract. **Produces:** typed per-attempt Gateway request with trusted registry/route binding, output cap and stable correlation; versioned launch approval binding. Wire field mapping is explicitly versioned, with unsupported combinations rejected rather than ignored.

- [ ] Add failing tests that a missing trusted launch snapshot (including absent caller hash), forged/missing registry hashes, arbitrary `vendor/model`, stale launch snapshots and unapproved provider/quantization overrides make zero upstream calls. Test both `/v1/responses` and `/v1/chat/completions` after their actual flattening.
- [ ] Add failing tests for output cap transport, final framing growth and unsupported required parameters; Gateway independently recomputes admission on the final upstream request. Replace fabricated completion status (`chat_completions.py:54` currently always reports `stop`) with actual verified provider termination status through both Gateway APIs and host models.
- [ ] Add disclosure tests: one host notice authorizes bounded identical-payload transport retries on the same approved route; changed payload, fallback to Contributor or maintenance requires a new notice. Bind authorization to request/route/payload digest; forged/missing authorization makes zero upstream calls. Every retry remains individually correlated; unknown-cost behavior follows the accepted successor.
- [ ] Add `test_length_limited_write_is_not_a_candidate`: propagate completion status, reject even a syntactically valid WRITE prefix after length-limit termination, and make zero plan-store/permission/mutation calls. Keep its receipt; missing completion status fails the verified route contract. Test complete status succeeds and capped Chat text is marked incomplete. Measure plan-output/file-content distributions for D3 before setting reserves.
- [ ] Implement trusted snapshot composition/HMAC-schema successor within the approval record byte bound. Old incompatible approvals require the approved migration/re-approval path; no caller-supplied digest grants trust.
- [ ] Remove Haiku from actual shared/local defaults and alias passthrough; set the accepted fixed medium default. Recognize `auto` only with an accepted installed resolver; do not silently send “auto” upstream or call it medium classification.
- [ ] Run `uv run pytest tests/unit/optimus_gateway tests/unit/gateway tests/unit/acp/test_launch_policy.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py -q`; Ruff on changed modules. Expected: PASS, including unauthorized request zero-call assertions and legacy safety checks.
- [ ] Real launch/keyring/Gateway evidence stays separately gated in Task 13. Strict unsupported-model/usage errors are not cost-policy stops.

### Task 6: Define extractable contracts and exact authority projection

**Create:** `src/context_engine/{__init__,contracts,checkpoints}.py`; `src/optimus/context/{__init__,adapter}.py`; `tests/unit/context_engine/test_boundaries.py`, `test_checkpoints.py`; `tests/unit/agent/test_context_authority_projection.py`.

**Consumes:** canonical five-field host records and real approval/settlement facts. **Produces:** the exact neutral types/API in spec section 5 and `make_history_snapshot(...) -> HistorySnapshot` in the host adapter. No engine-side ledger or approval types.

- [ ] Add AST forbidden-import and fresh-process import tests. Exercise only `import context_engine` in a new process and assert forbidden packages were not loaded; package relative imports/re-exports must not evade the AST check.
- [ ] Add failing `test_protected_projection_matches_host_facts`: completed/rejected/failed/cancelled turns, effect states and granted/denied/cancelled artifact scopes are exact; model claims of approval create no fact. An actual completed WRITE, partial execution and unknown effect must project COMPLETE/PARTIAL/INDETERMINATE respectively from verified terminals, rather than copied placeholder NONE. Offline fixtures establish the projection only. Real-host acceptance requires Task 2's reviewed producer repair and cancellation audit. On current main, verify rollout restart and fresh sessions; no unconditional legacy-history migration belongs to Q1. If durable sessions/replay arrive first, their owning lane must provide reviewed provenance treatment before restored placeholder NONE records are presented as authoritative.
- [ ] Add failing checkpoint tests for revision/digest/strategy/parameter/format mismatch, missing/future/overlapping source IDs and cancelled publication. Add append-only prefix reuse plus changed-prefix rejection if the recommended reuse contract is accepted. A stale paid result cannot publish or authorize anything.
- [ ] Implement immutable records and compare-and-publish. Preserve the existing host storage serializer and define the new HistoryRevision digest separately; no conversation-envelope hash exists on main. Keep that digest distinct from the plan approval hash and sanitize both engine input and returned summary boundaries.
- [ ] Run `uv run pytest tests/unit/context_engine/test_boundaries.py tests/unit/context_engine/test_checkpoints.py tests/unit/agent/test_context_authority_projection.py -q`. Expected: PASS, no forbidden import or mutation path.

### Task 7: Implement deterministic complete-turn strategies

**Create:** `src/context_engine/{selection,engine}.py`; `tests/unit/context_engine/test_selection.py`, `test_strategies.py`. **Consumes:** Task 6 immutable contract and explicit test-policy limits. **Produces:** `ContextEngine.prepare_view(...) -> PreparedView` with the exact signature in spec section 5.

- [ ] Add failing compaction/hybrid discriminator test with a fitting first turn outside both tails. Assert first turn exact only in hybrid, hybrid declared tail allocation larger, protected facts identical.
- [ ] Add failing oversized-anchor and head/tail overlap tests: oversized ordinary anchor enters summary range, protected anchor facts exact, deduplicated complete-turn partitions.
- [ ] Add failing sliding tests: newest complete suffix only, no older skip around oversized newest turn, zero maintenance calls including strategy switch, omission manifest accurate, canonical source untouched.
- [ ] Add failing exact-authority exhaustion and prompt-only tests: required state never summarized, truncation or unsafe approximate-fit never used, empty history yields no maintenance.
- [ ] Implement the algorithms with test-policy allocations, finite maintenance allowance and explicit unavailable result. Production values are supplied only from D1/D2/D3 policy; do not ship test fixture sizes as defaults.
- [ ] Run `uv run pytest tests/unit/context_engine/test_selection.py tests/unit/context_engine/test_strategies.py -q`. Expected: PASS with deterministic complete-turn/zero-call assertions.

### Task 8: Implement bounded summarization and the qualification gate

**Create:** `src/context_engine/summary.py`, `src/optimus/context/maintenance.py`; `tests/unit/context_engine/test_summary.py`, `tests/unit/agent/test_context_maintenance.py`; fixture `tests/fixtures/context_engine/calculator-constraints-v1.json`; evaluation tool `tools/evaluate_context_summarizer.py`.

**Consumes:** Tasks 4–7, accepted D4 format and Task 5 attempt receipts through existing `UsageAccountingService`. **Produces:** `MaintenanceCallback` from spec contract; fixture fact report; route/settings/format-bound quality receipt. Maintenance callback records each receipt even when it returns failure. Task 11 later adds the combined aggregate/alert projection; it is not a prerequisite for building this callback.

- [ ] Add failing tests for bounded complete source ranges, huge single turn, finite maintenance calls, malformed/empty/oversized/length-truncated output, output re-sanitization and hostile summary delimiter content.
- [ ] Add failing tests ensuring the summarizer never generates trusted coverage IDs, selection paths or host approval state; stale/cancelled results return unavailable and keep charge receipts.
- [ ] Prepare the synthetic fixture and expected facts from spec 6.6, including a two-step incremental/chunked variant: HALF_UP enters summary 1; the later HALF_EVEN chunk merges into summary 2. Evaluate retained facts in step 1 and supersession/all facts in the final merged summary. Ensure early constraints **and** late correction are in the summary range, not rescued by exact head/tail. Test the fact-report validator with a deliberately missing/contradictory summary.
- [ ] Implement the accepted bounded text/schema format and fixture runner with immutable input, captured reasoning/route, explicit evaluation call/dollar cap and no auto-retry-until-pass. Qualification keys include fixture/prompt/format digests.
- [ ] Run `uv run pytest tests/unit/context_engine/test_summary.py tests/unit/agent/test_context_maintenance.py -q`. Expected: PASS offline, including missing-fact negative case.
- [ ] Prepare, but do not execute, the paid request envelope: each structurally eligible candidate, exact synthetic input/output caps, attempt count, estimated authorized upper cost and resulting receipt fields. Request operator authority only for that concrete envelope.
- [ ] If authorized, run at most two initial fixture requests per candidate route (early chunk, then incremental merge), save output/usage/fact evidence and review once. Failed/skipped/unrun candidates remain unqualified. Record an eligible receipt only after the reviewed pass; no unqualified fallback.

### Task 9: Integrate attached views, exact selection, pure fallback and plan identity

**Create:** `src/optimus/context/assembly.py`; `tests/unit/acp/test_context_engine_admission.py`; `tests/unit/agent/test_context_selection.py`, `test_context_plan_binding.py`. **Modify:** `src/optimus/acp/{conversation,spec,bootstrap}.py`; `src/optimus/agent/{models,runner,prompts,planning_loop,state_store}.py`; existing Chat/Agent tests.

**Consumes:** Task 3 compatibility baseline, Task 4 policy/capacity, Tasks 6–8 prepared view. **Produces:** `probe_floor(records: Mapping[int, ConversationTurn], sanitized_prompt: str) -> int`; `build_selection_text(prompt: str, snapshot: HistorySnapshot, view: PreparedView) -> str`; `render_context_view(snapshot: HistorySnapshot, view: PreparedView) -> str`; captured `AdmittedContext` and plan context digest.

- [ ] Add failing attached/absent request-shape tests for both modes. Absent Agent still has full envelope in task, absent Chat retains prior selection behavior; attached selection uses exact prompt/head/tail/protected facts with no summary.
- [ ] Add failing selection tests for late correction, summary-invented path, sliding-omitted path and ambiguous “that file” follow-up. Assert omitted-only paths are not selected and no fabricated read/approval occurs.
- [ ] Add failing pure-probe tests at projected floor 524288/524289. Repeated unavailable-engine refusals above floor leave OPEN, consume no planning/answer calls, and the next healthy view is admitted. Actual source exhaustion/delivery-indeterminate cannot be overridden.
- [ ] Add failing growth/cancellation tests: files/tool evidence force repack under the captured revision and finite allowance; cancel stops dispatch/publication; missing summarizer uses stated fallback; no current prompt enters checkpoint.
- [ ] Add failing stored-plan binding tests: a mode/strategy change while waiting cannot alter application, changed context digest invalidates stored authorization, repeated stored planning cost is not a new receipt.
- [ ] Implement the captured split fields and every task consumer; exact selection feeds skills and workspace assembly for attached modes, model history feeds planners separately. Maintain canonical commit and final-flush rules.
- [ ] Implement measured attached source/reservation limits; genuine source cap retains its disposition, reservation/view refusals remain recoverable. Never truncate an applied turn's protected outcome.
- [ ] Run `uv run pytest tests/unit/acp/test_context_engine_admission.py tests/unit/agent/test_context_selection.py tests/unit/agent/test_context_plan_binding.py tests/unit/agent/test_plan121_chat_runner.py tests/unit/acp/test_plan121_chat_mode.py -q`, then existing runner/planning-loop tests. Expected: PASS and compatibility exceptions limited to reviewed ones.

### Task 10: Publish full configuration and truthful live notices/meters

**Create:** `src/optimus/acp/session_config.py`, `tests/unit/acp/test_context_config_options.py`, `test_context_notices.py`. **Modify:** `src/optimus/acp/{spec,shapes}.py`; extend `tests/e2e/acp/test_plan121_mode_wire_order.py` or its scheduled successor.

**Consumes:** Task 9 captured turn state and registry model availability. **Produces:** `build_session_config_options(snapshot: SessionConfigSnapshot) -> list[dict[str, object]]`, one locked setter/resync path and dispatch-derived usage readings.

- [ ] Add failing full-set tests for new session, both mode surfaces, strategy/model setter and partial-send recovery. Options include every enabled selector; strategy absent without attachment, visible through temporary failure; no false current-mode update on strategy-only change.
- [ ] Add failing interleaving test: a setter during maintenance changes next turn only, and a stale config send cannot clear newer resync state. Do not hold config lock through model/permission waits.
- [ ] Add failing warning tests with exact spec text: first admitted sliding turn only, switch-away-before-prompt cancels, fallback separately disclosed, no replay into canonical history.
- [ ] Add failing attached meter tests for largest actually sent complete input and matching usable capacity, excluded summary calls, no fabricated reading on zero-call refusal; floor meter stays unchanged.
- [ ] Add failing Contributor request-disclosure tests including routed provider failures; every new payload/request notice precedes dispatch authorization, while identical bounded same-route transport retries share the existing notice and retain individual attempt receipts. No extra permission dialog.
- [ ] Implement wire `id`/setter `configId` distinction and `_context_strategy` category against the pinned ACP schema, with parameter validation and no engine attachment via setter.
- [ ] Run `uv run pytest tests/unit/acp/test_context_config_options.py tests/unit/acp/test_context_notices.py tests/unit/acp/test_plan121_chat_mode.py -q`. Expected: PASS. Validate generated messages against the pinned schema using the repository's existing validator.
- [ ] Free real-Zed persisted-default probe precedes release. If unsupported-option rejection breaks a new absent-engine thread, return evidence for a narrow recorded remedy; do not auto-edit user settings or add a fake strategy picker.

### Task 11: Settle all stage costs and migrate the product cost policy

**Create:** `src/optimus/usage/{turn_settlement,cost_alerts}.py`; `tests/unit/usage/test_turn_settlement.py`, `test_cost_alerts.py`; `tests/unit/agent/test_product_cost_policy.py`. **Modify:** `src/optimus/usage/{models,accounting,ledger}.py` only under agreed telemetry interface; `src/optimus/acp/conversation.py`; `src/optimus/agent/{models,runner,planning_loop,prompts,state_store}.py`; `src/optimus/loops/{models,controller}.py`; `src/optimus/telemetry/events.py` under the agreed schema; affected loop/test adapters. Include single-shot/PLAN budget check `runner.py:531`, Chat check `:1009`, loop model positive-budget constraint `loops/models.py:24`, controller predicate `:163`, planning policy construction `planning_loop.py:92–99`, its cost predicate, planner remaining-dollar prompt `prompts.py:183–196`, and `max_budget_usd` telemetry.

**Consumes:** Tasks 5/8 attempt receipts and P11.26 schema interface for the accounting foundation; D6 accepted successor additionally required for product migration activation under accepted Q3; the future ADR-009 mechanism is separate. **Produces:** `record_attempt(receipt: StageReceipt) -> None`; `settle_turn(turn_id: str) -> TurnCostSummary`; `evaluate_alerts(summary: CostScopeSummary, policy: AlertPolicy) -> tuple[CostNotice, ...]`. Types are defined in spec section 11; receipt has optional reported cost plus explicit unknown state, never fake zero.

- [ ] Add failing exactly-once tests for every spec 11 exit: duplicate identical receipt, divergent duplicate, cancelled/stale summary, capacity rejection after maintenance, approval denial, exception and post-teardown receipt. Test stored-plan application does not double count planning and preserves incomplete planning cost. Version AgentPlanRecord to retain cost completeness/attempt references; legacy records missing completeness must not default to complete. Route duplicate agent_run emission to existing P11.26-CAND-2-TELEMETRY-CONTRACT and verify the agreed interface.
- [ ] Add failing incomplete-subtotal tests: known cost before **and after** unknown attempts remains recorded; incomplete cumulative cost is omitted/labelled, not zeroed or presented as definitive.
- [ ] Add failing alert tests for threshold crossing identities, higher thresholds, session scope, unavailable daily ledger, explicit day/timezone boundary and actual resolved model/provider cost. No alert causes product dispatch refusal.
- [ ] Add failing product/evaluation split tests: a successful product response above the former $0.05 is delivered; an independently capped evaluation stops under its approved envelope. No summarizer subtraction/reserve or hidden renamed product spend cap.
- [ ] Implement actual-receipt projections through the existing ledger and stage schema. Preserve strict usage failure handling under the accepted unknown-cost disposition; no parallel spend authority.
- [ ] After D6/accounting acceptance, under recorded Q3, remove all product monetary stop predicates, positive-dollar construction requirements, remaining-dollar planner prompt and stop-bearing telemetry semantics. Keep cost accounting; use explicit optional monetary policy only for independently capped evaluation/non-product callers, never a large/infinite sentinel. Regression-test default 3-round, 30-minute and repeated-failure-2 boundaries without a dollar stop, Chat single-call and the non-ACP goal-loop boundary. New ADR-009 behavior remains separately held; no new acceptance of that mechanism is needed for cost-stop removal.
- [ ] Run `uv run pytest tests/unit/usage tests/unit/agent/test_product_cost_policy.py tests/unit/agent/test_planning_loop.py tests/unit/agent/test_planning_loop_runner.py -q`; narrow Gateway unknown-cost/retry tests. Expected: PASS under the accepted successors; all separate test limits retained.

### Task 12: Calibrate finite limits and prove extraction/package fitness

**Create:** measurement tool `tools/measure_context_engine_limits.py`; `tests/unit/context_engine/test_limits.py`; extend noneditable wheel verification for new resources. **Modify:** proposed registry bounds only after review; approved current docs/report sources.

**Consumes:** offline working Tasks 4–10 plus Task 11's accounting foundation, using explicit fixture policies and synthetic histories. Product-policy activation is unnecessary for these local measurements. **Produces:** reviewed D1/D2/D3 policy values with basis, new ADR completions where needed, measured report and package acceptance.

- [ ] Exercise increasing complete-record sizes, Unicode, huge anchor, protected-state growth, serialization copies/checkpoint buffers and representative session concurrency. Record peak memory and admitted/refused boundaries; measure canonical and temporary bounds separately.
- [ ] Measure complete WRITE-plan output/file-content sizes and route completion-status behavior; propose implementer reserves that admit the representative plans and reject all length-truncated candidates safely. Measure complete request/history allocations across role fixtures with files/tool evidence and the accepted output reserves. Compare capacity-driven versus ADR-003 proposed percentage/role-target history ceilings without choosing it silently; the per-tier value bounds the history allocation and is not the point at which compaction begins (C3).
- [ ] Apply the CP4 corrections C1 (reason-specific refusal and recovery messages; a missing or incompatible summarizer is unavailable) and C2 (summary byte bound and dual-budget whole-turn packing) from the design spec and Task 1 contracts v2 with their focused checks, then re-run the limits checker and measurements with the corrected planner and report actual call counts. This corrective scope is not CP4 closure.
- [ ] Produce exact proposed `SOURCE_MAX_BYTES`, commit reservation, transient response bound, allocations and maintenance call allowance with measurements. Operator accepts values in the policy snapshot/new ADR completion before activation; report any genuinely unavailable route-estimator proof.
- [ ] Add regression boundary assertions using the **accepted** measured values. Do not assert a universal bytes/4 tokenizer or a fixed savings percentage.
- [ ] Build wheel with `uv build --wheel --out-dir <authorized-evidence>/wheel` and run the existing noneditable verifier with that directory and an isolated approved scratch root. Verify `context_engine` imports independently and the YAML defaults are present without a source checkout.
- [ ] Run new limits tests, boundary import tests and changed-source coverage. Expected: ≥80% aggregate production coverage including new packages and no safety-critical regression. Evidence excludes no new package by omission.

### Task 13: Obtain real-client evidence and review delivery

**Files:** authorized acpx evidence tool under `tools/`, tests in `tests/e2e/acp/` and `tests/integration/` with truthful real-dependency markers; sanitized report under `reports/`; mutable current docs/backlog entries. No frozen ADR update.

**Consumes:** all required dispositions/measurements, qualified incremental-summary receipt, reviewed Task 2 effect-producer repair/cancellation evidence and verified fresh-session rollout (or persistence-owner provenance evidence if durable history ships first), package gates and operator's live envelope. **Produces:** claim-to-evidence report with hashes, individual exits, exact SHAs and explicit skipped/unrun tiers.

- [ ] Present concrete live envelope: models/routes, actual synthetic prompts, per-call input/output/cost and total call count; service/credential/TTY/Zed operations. Obtain only the authority those actions require; paid authority is not implied by design acceptance.
- [ ] Use independently authored acpx and the real Optimus process/Gateway/Redis for named live tiers. Prove Chat stays non-mutating; Agent still requires exact artifact approval; no direct provider keys are available in CORE.
- [ ] With real Zed, show attached-only picker, mode switch preserving all options, sliding warning, separated storage/fallback notices, readable zero-call capacity refusal, meter and absent-engine persisted-default behavior. Do not use project-authored fake clients to claim ACP acceptance.
- [ ] Exercise >512 KiB attached history, repeated simulated engine unavailability through a bounded approved fault seam, healthy recovery, and cancel during maintenance. No destructive user-data/real-files fixture. Preserve actual receipt evidence even for discarded work.
- [ ] Run `uv run ruff check .`, repository pre-commit checks under actual approved hook policy, `git diff --check`, and `uv run pytest --cov=optimus --cov=optimus_gateway --cov=optimus_security --cov=evidence_handoff --cov=evidence_handoff_runtime --cov=context_engine --cov=optimus_model_policy --cov-branch --cov-report=term-missing -q`. Expected: applicable default suite PASS, coverage gate met; report marked tiers separately. Include every existing production package and both new packages.
- [ ] Run authorized marked tiers explicitly with the repository marker selection overriding defaults; record each selected test set and dependencies. Skip/unrun is non-passing; do not fill live evidence gaps with stub results or rely on an aggregate wrapper exit.
- [ ] Independently review accepted ADR coverage, spec/plan contract, effective registry/launch hashes, changed source and documentation freshness. Audit README, roadmap, sole backlog and every current-state claim affected, not only files implementer volunteered.
- [ ] Require the Plan 12 PR description to identify the runtime-hardening repair, cancellation/effect proof, and the sandbox's retained gap until later synchronization. Use a reviewed main-based feature branch and PR; do not interpret the delivery route as permission to edit main directly or update the sandbox.
- [ ] Return exact cleared Git blobs, evidence/checksum manifest, remaining risks and per-package disposition to the operator. No retry-until-green, commit/push/PR/merge, cleanup or live-service acceptance without the corresponding direct authority.

## Definition of done and exception custody

The engine deliverable passes only when all four operator checkpoints, accepted engine/registry/cost requirements and relevant package gates have named evidence. A held dependent package prevents claiming the complete product migration is done. Proposed features may remain unimplemented under their named exception owners; accepted requirements cannot disappear behind a “Proposed” label.

The narrow effect/cancellation repair is now inside Plan 12 Task 2, not an exception or separate runtime item. Broader goal-loop cancellation remains P12.1-FU-2. The sandbox remains uncorrected until later separately authorized synchronization, and the Plan 12 PR must state that.

Exceptions retain spec section 13's owners: Auto/review/loop mechanisms in the Plan 12 lane pending named promotion; cost cross-run/day in `P9.85-FU-3`; typed telemetry in `P11.26-CAND-2-TELEMETRY-CONTRACT`; savings report in `P12-FU-2`; resume in existing `P11-FEAT-ZED-RESUME` lanes; startup in `P12.1-FU-1`; loop cancellation in `P12.1-FU-2`; deferred data restrictions in ADR-010/Plan 12. Task 0 verifies/makes repository-visible scheduling custody without creating a parallel work pool.

The manual fixed-model registry/engine path can be reviewed independently. It is not a completion claim for ADR-004's Auto picker/routing requirement, ADR-008 review or ADR-012 savings. Promotion must make that package boundary explicit; classifier/review/savings behavior gets its own accepted specification rather than improvised code in these tasks.

## Plan self-review and handoff

Draft self-review maps every accepted ADR to the spec trace table and Tasks 0–13. Exact engine/registry/assembly/settlement signatures are stated at the producing task; consumers refer to those contracts. All five Review Focus cases have named tests. Codex has written no product code or product tests. Focused docs validation is separate from unrun engine verification. Historical Package A evidence is recorded explicitly; remaining task checkboxes are intentionally empty. Real-client, service, paid and policy holds are prerequisites, not fabricated passing evidence.

Claude should review the spec first, then task coverage, package boundaries, D7 interpretation, actual source consumers and prerequisite reachability. Return section/task-specific alternatives. Claude reviews both revised artifacts, then implements only after the operator accepts execution scope. Fable 5.1 then Codex review only at CP1-CP4. Filing and later publication use the applicable direct authority; merge remains the operator decision. This handoff does not itself authorize execution or delegation.

## Filing and execution boundary

This complete v2 retains all original tasks, adds the Task 1 contract supplement and replaces obsolete cadence/authority text. The operator accepted it on 2026-10-02. Claude filed it as CP1's first commit, moving the first edition unchanged into `archive/` and updating the mutable references; frozen documents keep their original links, which resolve across the archive move. Historical Package A evidence does not establish later engine prerequisites, and filing proves no new product behavior. Use `docs/superpowers/reviews/plan-12-2-review-checkpoints.md` for the reviewer-owned, gitignored checkpoint log; never stage it. A substantive later contract change is a complete same-number `_v2` successor, not an amendment or a new task allocation.

## V2 provenance and filing

Complete successor to the frozen 2026-10-01 first edition, accepted by the operator on 2026-10-02.
Operator source S3 covers cadence/publication selections; the acceptance itself follows S3 and is
recorded in the sole backlog. The Task 1 contracts identify all new mechanisms, which are architect
proposals the operator accepted, and their dependent activation gates. Package A acceptance/evidence is historical at 38a465f, not a claim
of main/engine/live completion. Current status belongs to the sole backlog. No product code, paid
call, commit, push or merge is performed by filing this plan. Do not edit the first edition in place.
