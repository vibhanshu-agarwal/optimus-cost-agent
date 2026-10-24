# Plan 12.3 — Loop control Phase 1: detect, nudge, check in

- **Goal:** replace the interactive hard stops for repetition and planning limits with ADR-009's bounded recovery: detect → one corrective nudge → a Continue/Stop check-in. Bound and cancel hung TEST commands. Retire the unused legacy goal-loop behaviour.
- **Authority:** the operator, 2026-10-23, verbatim: "Approved: D1 accept ADR-009 as scoped (detector, one nudge, check-in; escalation after Auto), D2 thresholds 3 / one nudge / Continue +3, D3 retire the legacy goal-loop path if no supported client uses it."
  - **Priority:** the operator, 2026-10-23, verbatim: "P1(a), A1, A2, A3, A5 are approved". P1(a) makes loop control Plan 12.3, ahead of Auto (Plan 12.4, #395).
  - ADR-015 keeps today's limits only "until … ADR-009 replaces them". There is no dollar stop (ADR-005).
- **Workflow** (operator, 2026-10-23):
  - Claude implements, and Codex reviews through the CLI at two checkpoints. Fable is consulted only if Claude judges a point complex.
  - Each task runs only its own tests; the full suite runs once at the end. There is no WSL run: Linux CI failures are fixed in the PR.
- **Base:** current main, **after #388 merges** (its fix is PR #393). This is an unconditional dependency, with no stacking on its branch.
- **Estimate:** **6–8 active days** (Codex's figure, confirmed at every review), excluding #388, approval and live-check waits.
- **Revisions:** the Design sections keep their numbers, so each earlier mapping table still applies. Codex's reviews are posted verbatim on #394.

| Version | Codex verdict | Findings | Review |
|---|---|---|---|
| v1 (`bad828c4…`) | rework | 12; v2 addressed them | posted on #394 (`447d6e28…`) |
| v2 (`a6f1030c…`) | rework | 7 remaining; v3 addressed them | posted on #394 (`321d193f…`) |
| v3 (`54b16861…`) | rework | 4 remaining; v4 addressed them (mapping at the end) | posted on #394 (`e32a2f68…`) |
| v4 (`b412887d…`) | **approve** | none; this filed version is v4 plus the filing edits only | posted on #394 (`e8c8f292…`) |

## Prerequisites

| Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| A new acceptance record "Accepts ADR-009 as scoped" (D1–D3), at the next free ADR number at filing, plus the mutable decisions-index update; ADR-009 itself stays frozen (`docs/decisions/README.md:127-139`) | no | Claude writes it in Task 0; the operator decided on 2026-10-23 | Merely unauthorized: a docs change inside this plan's PR |
| The decision source for D1–D3: the app's export of this session, registered as Source S10 | yes | Claude, at filing | — |
| #388 merged to main | no | Claude (#388 lane); the operator approves the merge | Merely unauthorized: the fix is in PR #393, awaiting review and the operator's merge approval. Task 1 starts only after the merge; #388's parser reason codes are reused, and its focused regressions are re-run |
| This plan's issue (#394), its priority and number, its registry pointer, and an owning issue for every Explicit Exceptions row | yes | Claude filed them; the operator approved each write | — |
| An execution checkout from current main, with its own `.venv` (Python 3.14, uv, Git) | unknown | Claude inventories it at Task 0 | Merely unauthorized: created when execution is released |
| Windows can create a Job Object and assign a child to it, through the ported containment code | unknown | Claude checks at Task 0 | Genuinely hard if not: TEST directives are refused on that host (fail closed, Design 8). There is no uncontained fallback |
| `acpx` 0.12.0, the version main's recorded denial behaviour is pinned to (`tools/plan12_stage_c_launch_rehearsal.py:81`), for the final live check | unknown | The operator (machine state); Claude checks `acpx --version` at Task 0 | Merely unauthorized: the operator installs or updates it |
| The Gateway and its services (the shared Redis, never stopped by Claude) running with Optimus credentials, for the final live check | unknown | The operator (machine state and credentials; Claude never reads or handles a key) | Merely unauthorized: the operator starts them; Claude checks reachability at Task 0 without reading any credential |
| **One bounded live turn** for the final acpx check: up to 4 planning steps, plus their existing retry attempts, in a scenario built to reach recovery | no | The operator | Merely unauthorized: the operator releases it at Checkpoint B; otherwise that check stays UNRUN |
| The Zed rendering of the Continue/Stop options | unknown | The operator, optionally by glancing in Zed; acpx cannot prove it | Genuinely hard to automate: recorded as unverified until observed |

**Task 0 settles every `unknown` row before the work that depends on it.**

## Design

### 1. Signals and novelty (`src/optimus/loops/signals.py`, new)

**`ActionFingerprint`** is the action kind plus a normalised target:

| Kind | Fingerprint |
|---|---|
| READ | The path plus the exact byte range (`start_byte`, `end_byte`), with no bucketing |
| MCP | server + tool + a canonical argument hash. Today it is `MCP:{op}:{server}` (`src/optimus/agent/planning_loop.py:1462`) |
| Parse failure | #388's parser reason code |
| Permanent error | Its class |

**`ResultDigest`** is the outcome's identity:
- **READ:** the whole-file `source_sha256` (`src/optimus/loops/tools.py:105-106`).
- **MCP:** the SHA-256 of the evidence envelope the planner receives, `format_mcp_evidence_envelope(output)` (`planning_loop.py:1456-1457`). Main returns no separate result digest.
- **An error:** its class.

**Novelty** means a new result digest, new evidence, or a changed plan draft. For READ it is range-aware:
- **A read is novel** if any byte of its range was not covered by earlier reads, in this turn, of the same path with the same `source_sha256`, or if the hash changed.
- **A fully covered re-read of unchanged content is not novel.**

### 2. Detector (`src/optimus/loops/detector.py`, new). Every trigger is result-aware

**The triggers:**

| Trigger | Fires when |
|---|---|
| Repeat | The same fingerprint **and the same result digest** 3 times in a row. A changed result resets the streak, so **polling that returns changing results never fires** |
| Cycle | An A–B alternation over **3 cycles**, as ADR-009 specifies (`docs/decisions/ADR-009-loop-control-without-stopping-the-user.md:95-105`), with unchanged result digests |
| No progress | 3 consecutive steps with no novelty (Design 1) |
| Repeated error | 3 consecutive identical error classes, parse failures included |

**Configuration and scope:** thresholds are configurable, with the defaults from D2. The detector replaces the consecutive counter at `src/optimus/loops/models.py:117-128` (limit 2, at `planning_loop.py:123`) for the interactive planning path only.

### 3. The nudge

`build_multi_turn_planner_input` (`planning_loop.py:1273-1290`) gains a bounded, sanitised **recovery note**:
- what repeated;
- the last error class and message;
- the parser reason for a parse failure.

**One nudge per episode** (D2).

### 4. Recovery transitions (interactive mode)

**Episodes:**
- **An episode starts at the first detection and always ends at a check-in** (ADR-009:114-116).
- **This holds even when the episode's nudge produces a final plan.** The plan is kept, and the recovery check-in comes first: Continue goes on to the normal plan approval, and Stop ends the turn. The check-in never approves the plan (ADR-009:130-134).
- **Help always comes before asking** (ADR-009:76-77). So a detection never goes straight to a check-in without its nudge first.

**The order after each step:**
1. **Record the outcome.**
2. **Run the detector.**
3. **Apply the allowance checks** (`src/optimus/loops/controller.py:121-125`, `:157-169`).

**What follows from the state:**

| State after the step | Next |
|---|---|
| A first detection in an episode, with the allowance remaining | The nudge goes into the next planning step |
| A first detection on the allowance's last step, or after the clock expired | **One budgeted nudge step** beyond the allowance: exactly one more planning step carries the nudge, then the check-in |
| A second detection in the episode | The check-in |
| A final plan while an episode is open | The plan is kept; the check-in, then the normal plan approval |
| The allowance exhausted (3 steps, or 30 minutes) with no detection | The check-in: count caps become check-ins (ADR-009:142-144) |
| Continue | **The episode ends.** If a final plan is waiting, it goes to the normal plan approval. Otherwise a new allowance of **+3 steps and a fresh 30 minutes** (D2) starts; a later detection starts a new episode with its own nudge. Repeated Continues are allowed, each asked separately. Costs, carried evidence and receipts are preserved |
| Stop | The turn ends with the actual cause |

**So each check-in cycle is at most four planning steps under the default allowance** (3, plus one budgeted nudge step). Two other kinds of attempt are counted separately and keep their existing policies:
- transport retries (`planning_loop.py:843-845`, `:1213-1223`);
- context repacking (`src/optimus/context/assembly.py:667-672`).

**Two rules that apply throughout:**
- **A final plan that arrives in the step where the clock expired is kept.** Today expiry discards completed work (`planning_loop.py:1485-1491`, `:1549-1555`). The plan goes on to the normal plan approval, after any open episode's check-in. This exception is **interactive-only**; headless keeps today's behaviour.
- **First-occurrence typed failures stay stops:** Gateway or provider faults (D4 unchanged), read errors and guard blocks.

### 5. The check-in bridge (separate from approval)

**The bridge:**
- **It is a new recovery callback,** distinct from the WRITE/TEST approval path (`src/optimus/acp/spec.py:1242-1248`). It is called from the planning worker (`:1087-1101`) through a thread-safe bridge, like the existing approval request (`:874-875`, `:1786-1818`).
- **It has its own options:** `loop-continue` (kind `allow_once`) and `loop-stop` (kind `reject_once`). These are the same kinds as the plan approval's options (`src/optimus/acp/shapes.py:155-166`), because clients such as acpx select by kind.

**How the response is handled:**
- **Validation:** a malformed or unknown response is treated as Stop, with a recoverable explanation.
- **Cancellation or disconnect** while waiting cancels the turn, with cleanup.
- **Before resuming,** the halt request is re-checked.
- **Continue can never grant WRITE or TEST.** That is asserted in code and tested.

### 6. Interactivity policy

**One setting** in the existing Optimus configuration selects `interactive` or `headless` recovery.
- **Precedence:** the explicit setting, then the caller's default.
- **Caller defaults:**
  - an ACP session prompt is interactive;
  - golden, evaluation, Stage C and every other non-ACP caller is headless (ADR-009:146-147).
- **Headless keeps today's hard caps and behaviour unchanged,** including on clock expiry.

**Two cases need care:**
- **An auto-approving ACP client is effectively headless.** acpx `--approve-all` would answer every check-in with Continue, so such runs set headless.
- **If the check-in cannot be presented** (the request fails, or the client lacks support), the turn ends with a recoverable explanation and does not spin.

**The live check at Checkpoint B:**
- **The client:** acpx `--deny-all`. It selects the `reject_once` option, as main's recorded denial shows (`tools/plan12_stage_c_launch_rehearsal.py:82`). So the check-in should end in Stop.
- **The scenario** is built to reach recovery, for example a task that needs more than 3 planning steps.
- **The check verifies the denial it observed:** the `loop-stop` option of a recovery check-in, not the plan approval's `cancel`.
- **If the run does not reach recovery,** that is recorded as the result. It is not retried until it passes.

### 7. Honest reasons

- **Stop reasons per kind:** `REPEATED_READ`, `REPEATED_MCP`, `CYCLE`, `NO_PROGRESS`, `REPEATED_PARSE_ERROR`. This fixes `planning_loop.py:723` and `:1583`.
- **The user text names what repeated** (`:731-770`).
- **A content-free telemetry record** is emitted per detection and per check-in decision.

### 8. TEST deadline, containment and cancellation

**The deadline:**
- **Who owns it:** the approved-plan replay (`src/optimus/agent/runner.py:1398-1418`) sets one monotonic deadline per TEST directive (default 15 minutes, configurable).
- **How it reaches the command:** it is passed with the turn's cancellation through `AgentToolbox.run_tests` (`src/optimus/agent/tools.py:116-128`) to `shell_exec` (`src/optimus/tools/mutation_tools.py:81-108`, which today blocks in `subprocess.run` at `:108`).
- **Every wait uses the remaining time.**

**The launch:**
- **It goes through the ported containment code** from `tools/process_tree.py:47-85`, moved into the runtime package. `src/optimus/mcp/client_supervisor.py:35-36` only selects a seam name.
- **If containment fails, the launch is refused before the command runs.** This keeps the existing abort-and-clean-up behaviour (`tools/process_tree.py:57-66`, `:88-113`). The result is "containment failed", and there is **no uncontained fallback**.

**Output:** the pipes are drained with `communicate(timeout=remaining)`, so a full pipe cannot block the call.

**Expiry or cancellation:**
- **The teardown:** `kill_tree`, then the root is reaped and the pipes are drained.
- **The teardown is bounded:** 10 s, matching `_CLEANUP_SECONDS` (`tools/process_tree.py:39`).
- **If either does not finish within the bound,** the result is "stop unconfirmed".
- **So a TEST always returns within deadline + 10 s.**

**A timeout, a containment failure or an unconfirmed stop is terminal for that plan.** The later directives are suppressed, and the outcome is reported ("timed out after N s", "containment failed", or "stop unconfirmed").

### 9. Retire the goal-loop behaviour only (D3)

**What the evidence shows:**
- Production serves NDJSON (`src/optimus/acp/__main__.py:714-726`).
- The framed transport, the only one that reaches `optimus.agent.run`, is **refused at startup under the enforced registry** (`__main__.py:182-187`). So no supported client reaches it today.

**What changes:**
- **The route stays for one-shot requests** (`src/optimus/acp/dispatcher.py:302-323`).
- **A request carrying `completion_condition` is rejected with a clear error,** never silently run once.
- **What is removed:** the runner's goal-loop branch and its injection seams (`runner.py:156`, `:297-312`, `:359-364`, `:408-454`), and `AgentRequest.completion_condition` (`src/optimus/agent/models.py:111`).
- **`GoalLoopController` stays,** because the planning loop uses it (`planning_loop.py:903`).

**The consumer inventory:**
- `tests/unit/agent/test_product_cost_policy.py:107-136`;
- `tests/unit/agent/test_plan121_chat_runner.py:260-275`;
- `tests/integration/agent/test_loop_skill_agent_flow.py:53-81`;
- `tests/integration/loops/test_goal_loop_guardrail_flow.py`;
- `tests/integration/acp/test_server_stream.py:252-298`;
- the unit tests of the runner and models.

**Their safety and accounting assertions** move to the planning-loop tests where they still apply. #270 is resolved by this; closing it is a GitHub write that needs approval.

## Tasks and checkpoints

| Task | Work | Targeted tests |
|---|---|---|
| 0 | **Records and checks:** the acceptance record and the index, citing Source S10; settle the `unknown` prerequisites (checkout, Job Object, acpx, Gateway reachability).<br>**Rebase:** onto main after #388; re-run #388's focused regressions | `tests/unit/docs`, after staging; #388's tests |
| 1 | **Signals and the result-aware detector.**<br>Negative tests, through the real planning runner: polling with changing READ and MCP results, a changed-file re-read, three previously unread ranges of one unchanged file, distinct MCP tools, progress.<br>Positive tests: repeat, 3-cycle alternation, no novelty including fully covered re-reads, repeated error | new `tests/unit/loops/test_detector.py`, `test_signals.py`; `tests/unit/agent/test_planning_loop_runner.py` |
| 2 | The nudge, honest reasons, the MCP fingerprint and digest | the planner tests |
| 3 | **The transitions and the check-in bridge:**<br>- a detection on the allowance's last step gets its nudge step before the check-in;<br>- **a nudge that produces a final plan still ends at the check-in, then goes to plan approval;**<br>- Continue ends the episode, and a later detection gets a new nudge; repeated Continue;<br>- final-plan expiry (interactive only);<br>- preserved costs and evidence;<br>- a late Continue after cancel; malformed responses;<br>- Continue never approves a mutation; the option kinds;<br>- an unavailable check-in;<br>- the mode setting and its precedence; headless caps unchanged | `tests/unit/acp` (permission and bridge); `tests/unit/loops/test_controller.py` |
| **Checkpoint A** | **Codex CLI review** of Tasks 0–3 | — |
| 4 | **The TEST deadline, containment and cancellation:**<br>- the real-process tests on Windows: a real child timeout and a real cancellation, with no surviving descendants;<br>- through the approved replay path: an injected termination failure returns "stop unconfirmed" within deadline + 10 s; an injected containment failure refuses the launch;<br>- suppression of later directives | `tests/unit/tools`; the mutation and replay tests |
| 5 | **Goal-loop retirement (D3), with the consumer inventory moved** | the runner, models, dispatcher, server-stream and loop tests |
| **Checkpoint B** | **The full suite once,** plus Ruff; the PR; fix Linux CI in the PR; a **Codex CLI review** of the full diff; the live acpx check (Design 6), if the turn is released | — |

## Acceptance

**Detection:**
- **What is detected:** repeats, 3-cycle alternations, no-novelty runs (fully covered re-reads included) and repeated error classes.
- **What is not detected:** polling with changing results, changed-file re-reads, previously unread ranges of an unchanged file, distinct MCP tools and progress.
- **The proof:** all of this goes through the real planning runner.

**The nudge:** every episode's nudge comes before its check-in, including a detection on the allowance's last step. It is delivered in a real model request, and a parse failure can recover in a fixture.

**The check-in:**
- **It follows the transition table.** Every episode ends at a check-in, including one whose nudge produced a final plan; that plan is kept and goes to approval afterwards. There is no interactive hard stop for repetition or the planning limits.
- **Continue** ends the episode and grants +3 steps and a fresh 30 minutes, **and never a WRITE or TEST approval.**
- **Each check-in cycle** is at most four planning steps under the default allowance, with retries and repacking unchanged.
- **The setting** selects the mode, in the specified precedence. Headless caps and behaviour are unchanged.
- **An unavailable check-in** ends the turn recoverably.

**Reasons:** stop and telemetry reasons name the actual cause.

**TEST:**
- **A hung TEST and its children** are stopped by the deadline or by cancellation, on Windows, and on Linux through CI.
- **Every TEST returns within deadline + 10 s.**
- **A containment failure** refuses the launch.
- **An unconfirmed stop** is reported, and later directives are suppressed.

**The goal loop:** `completion_condition` requests are rejected clearly, one-shot `optimus.agent.run` still works, and the planning loop is otherwise unchanged.

**Live:** the live check observes a recovery check-in ending in `loop-stop`, or records that the run did not reach recovery, or is recorded UNRUN if the turn is not released.

**Final checks:** the full suite and Ruff pass once at the end, and CI is green.

## Explicit Exceptions

Each row names its owning issue.

| Deferred | Owning issue |
|---|---|
| Cross-turn fingerprints ("same failure as turn k"); alert thresholds; the Chat repeated-text notice; one shared retry and failure taxonomy; the provider 429/5xx check-in (D4) | #396 (loop control Phase 2) |
| Escalation to a stronger model | #397 (loop control Phase 3, after Plan 12.4) |
| Persisted episode accounting, before delegated autonomy | #396 |

## Codex re-review (v3) findings mapping

| # | Finding | Addressed in |
|---|---|---|
| 1 | A final plan from the nudge still ends at the check-in | Design 4 (episodes, the transition table); Task 3; Acceptance |
| 2 | The bound counts planning steps, not requests | Design 4; Acceptance |
| 3 | The live check: one bounded turn, option kinds, a denial of the right prompt | Prerequisites (the live-turn and acpx rows); Designs 5–6; Acceptance |
| 4 | The MCP digest source | Design 1; Tasks 1–2 |
