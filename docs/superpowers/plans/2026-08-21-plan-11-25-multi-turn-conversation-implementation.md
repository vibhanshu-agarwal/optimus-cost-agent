# Plan 11.25 — Multi-Turn Conversation Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task, and use `superpowers:test-driven-development` for every production behavior change. Steps use checkbox (`- [ ]`) syntax for tracking. Do not mark a checkbox complete until its stated verification command has passed.

**Goal:** Add safe, in-memory, same-process multi-turn conversation to the ACP `session/prompt` path, including canonical history, byte-budget admission/commitment, exact cost accounting, cancellation/teardown settlement, and serialized outbound delivery.

**Architecture:** Keep conversation state session-owned and transient. Give each admitted turn one `TurnControl`, every non-turn response or notice a capability handle owned by one process-lifetime `NoticeControl`, and route every NDJSON notification, request, and response through one dedicated FIFO writer thread. Isolate the pure settlement vocabulary, control state, writer, and conversation framing in focused modules; keep `AcpDuplexAdapter` as the turn orchestrator and `AcpStreamServer` as the request/transport owner.

**Tech Stack:** Python 3.14, asyncio, `threading`, `queue`, `concurrent.futures`, Pydantic 2, existing ACP v1 shapes, existing `optimus_security.sanitization`, existing telemetry fanout, pytest/pytest-asyncio, coverage.py, and Ruff.

**Spec:** `D:\Projects\Development\Python\optimus-agent-handoff\BRAINSTORM-multi-turn-conversation-SETTLED.md`, SHA-256 `9630C0CC67D033DB647587602E2797F4ACE9E937F3F0AB748FF6DE14EDC67F38`, 3,686 logical lines. This settled contract is the normative specification for this plan; do not infer requirements from its revision-history prose when the current §2 or §4 text is more specific.

## Authority and Baseline Anchors

- Source baseline: `e5a796fd79425509d02e3cf17d562f62c5182228` in `D:\Projects\Development\Python\optimus-cost-agent-wt-codex-11-24-v6`.
- Audit binding: `self-audit-run-32.json`, 17/17 PASS, exit 0; audit-script SHA-256 `1F681651E8C70E19692DB887453FA625E0CD537F9840FE0E21E4F0D853AB76EB`. The audit is a binding/premise sentinel, not a semantic implementation test.
- Contract disposition: Review 33 post-repair contract-level GO. Codex authored and accepted the repair; the checkpoint discloses that this is post-repair acceptance, not a second independent external review.
- Workflow gate: `MT-FU-1` and `MT-FU-2` must be restored to the actual main backlog before overall contract approval and design-document ungating. Their absence does not block implementation kickoff under the operator's stated authority.
- Slice boundary: in-session conversation only. No persistence, `session/resume`, `session/load`, compression, summarization, pruning, eviction, fixed teardown deadline, worker-process isolation, or non-AGENT-mode conversation carriage.
- Current-source anchors: `spec.py:356-506` owns the prompt turn; `server.py:245-385` owns NDJSON concurrency and teardown; `runner.py:129-646` owns planning and approved execution; `planning_loop.py:756-1385` owns the existing halt mechanism; `state_store.py:50-257` owns multi-write plan persistence; `fanout.py:58-79` is a raising synchronous telemetry path today.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| workflow/backlog | `MT-FU-1` and `MT-FU-2` are restored to the actual main backlog before overall contract approval and design-document ungating. | no | operator | merely unauthorized operator action; this remains an approval/design-document gate, not a blocker to implementation kickoff. |

## Global Constraints

- Start implementation in a fresh isolated worktree from refreshed `origin/main`. Prove `HEAD == origin/main` and record the implementation base before the first write. Do not implement in this planning/recovery directory or in another contributor's worktree.
- Recompute and record the settled-contract SHA before Task 0. Stop if it is not exactly `9630C0CC67D033DB647587602E2797F4ACE9E937F3F0AB748FF6DE14EDC67F38`.
- Preserve ACP v1 wire compatibility. Refusal and cancellation remain distinct internal settlements even where the existing wire surface collapses them.
- Preserve raw candidate plan text byte-for-byte for hashing, permission, plan persistence, and conditional execution. Sanitization applies only to the conversation representation and its consumers.
- Never add raw credentials, URI passwords, unsanitized prompts, plan text, or final text to telemetry, debug diagnostics, exception messages, test snapshots, or settlement events.
- `CONVERSATION_MAX_BYTES` is the literal integer `524_288`. Admission, warning, and commitment decisions use rendered UTF-8 bytes. Gauge token values are display-only floor division by four.
- `turn_seq`, response IDs, warning IDs, and warning-attempt IDs are monotonic and never reused during the owning session/process lifetime. JSON-RPC request IDs are wire correlation only.
- No sleep-based race test is acceptable. Use events, barriers, injected transports, lock-order hooks, or controllable futures.
- No physical NDJSON write may bypass the dedicated writer after Task 4. A grep for direct `write_line` use outside the writer/legacy framed server must be part of every later review.
- Do not make settlement telemetry a send. It has no send owner, queue slot, start operation, or writer token.
- Do not model shadow-workspace result promotion. It is unreachable from the live ACP/AgentRunner path and is outside this contract.
- Preserve the exact 16 KiB workspace-context allocation and existing lower-layer planning stop precedence except for the already-settled external `halt_requested` integration.
- Each task is a separate review and commit boundary. If a task exposes a design contradiction with the settled contract, stop and return to the architect; Cursor must not silently choose a new product ruling.

## File Map

| Path | Responsibility |
|---|---|
| `src/optimus/acp/settlement.py` | Pure enums, immutable work-class registry, terminal vocabularies, effect algebra, delivery consequences, and frozen settlement values. No asyncio or I/O. |
| `src/optimus/acp/lifecycle.py` | `TurnControl`, `NoticeControl`, typed send keys/tickets, response/warning capability handles, permission handle, request-local ownership slot, and response envelopes. |
| `src/optimus/acp/outbound_writer.py` | Process-lifetime dedicated FIFO writer thread, queue item/token ownership, phase-based delivery classification, future resolution, and drain/join. |
| `src/optimus/acp/conversation.py` | Five-field conversation records, canonical rendering, sanitizer inputs, byte accounting, cap/warning decisions, session cost, and monotonic disposition. |
| `src/optimus/acp/server.py` | Physical NDJSON transport adapter, process-owned writer/notice controls, request ownership slots, response-envelope routing, process transport-loss trigger, and shutdown ordering. |
| `src/optimus/acp/spec.py` | Session/turn admission, cancellation, runner orchestration, governed sends, fallback construction, conversation commit, warning/refusal scheduling, and response-envelope production. |
| `src/optimus/acp/bootstrap.py` | Construct sanitizer inputs and expose the non-debug settlement sink without reading ambient state per turn. |
| `src/optimus/acp/shapes.py` | Add the ACP `UsageUpdate` builder only; retain existing plan/message shapes. |
| `src/optimus/agent/operation_control.py` | Narrow runner-facing protocol implemented by the exact ACP `TurnControl`; avoids copying cancellation or lifecycle state into the agent layer. |
| `src/optimus/agent/models.py` | Add `candidate_plan_text: str | None` to `AgentRunResult`. |
| `src/optimus/agent/runner.py` | Thread per-call control/halt inputs, instrument directives and persistence, and preserve candidate plan text and cost exactly once. |
| `src/optimus/agent/planning_loop.py` | Consume the existing per-call halt callback and instrument planning READ/Gateway attempt terminal states; do not add a new stop reason. |
| `src/optimus/agent/state_store.py` | Report clean versus partial plan-persistence failure without making a partial record authorizing. |
| `src/optimus/telemetry/events.py` | Add content-free `ACP_TURN_SETTLEMENT` event kind/schema fields. |
| `tests/unit/acp/test_settlement.py` | Exact eight-field registry, vocabulary, consequence, effect-algebra, and settlement-value tests. |
| `tests/unit/acp/test_lifecycle.py` | Deterministic `TurnControl`, `NoticeControl`, capability retirement, permission cleanup, and ownership-slot tests. |
| `tests/unit/acp/test_outbound_writer.py` | Dedicated writer ordering, phase classification, future/token completion, exception containment, and shutdown tests. |
| `tests/unit/acp/test_conversation.py` | Canonical framing, sanitization, identity, cap, warning, cost, gauge, and disposition tests. |
| `tests/unit/acp/test_spec_protocol.py` | Real adapter turn/refusal/cancel/fallback/history behavior through existing ACP shapes. |
| `tests/unit/acp/test_stdio_ndjson.py` | Real server routing, concurrency, response ownership, transport teardown, and writer lifecycle. |
| `tests/unit/agent/test_models.py` | Candidate-plan field schema and serialization tests. |
| `tests/unit/agent/test_runner.py` | Per-call control, directive lifecycle, persistence, cost, and approved-execution tests. |
| `tests/unit/agent/test_planning_loop.py` | Halt precedence, planning READ/Gateway state, and cost-completeness tests. |
| `tests/unit/agent/test_state_store.py` | Multi-write persistence success/clean-failure/partial-failure tests. |
| `tests/unit/telemetry/test_events.py` and `tests/unit/telemetry/test_fanout.py` | Settlement event shape and non-raising containment tests. |
| `tests/e2e/acp/test_multi_turn_conversation.py` | Hermetic real-process dependent follow-up, request-ID reuse, warning/cap, and teardown scenarios. |

## Task Dependency Order

```text
Task 0 baseline
  → Task 1 pure settlement model
  → Task 2 TurnControl
  → Task 3 NoticeControl + handles
  → Task 4 dedicated writer
  → Task 5 conversation state
  → Task 6 runner instrumentation
  → Task 7 adapter orchestration
  → Task 8 server/envelope integration
  → Task 9 telemetry and teardown evidence
  → Task 10 contract scenario matrix
  → Task 11 release gates and handoff
```

Tasks 2-4 deliberately precede `spec.py` changes. Cursor must not create a temporary direct-write or ID-map ownership path that will be removed one task later.

## Tasks

### Task 0: Establish implementation custody and a reproducible baseline

**Files:**

- Create: `reports/plan-11-25-multi-turn-baseline.md`
- Audit only: the settled contract, `src/optimus/acp/{server,spec,bootstrap}.py`, `src/optimus/agent/{models,runner,planning_loop,state_store}.py`, and named tests

**Interfaces:** Consumes the exact contract/source binding above. Produces a committed baseline report and no production behavior change.

- [x] **Step 1: Create an isolated implementation worktree.** Use `superpowers:using-git-worktrees`; fetch `origin`, create the implementation branch from `origin/main`, and record `git rev-parse HEAD`, `git rev-parse origin/main`, and `git status --porcelain`.
- [x] **Step 2: Verify authority bytes.** Run `Get-FileHash -Algorithm SHA256` on the settled contract and record the full digest, logical line count, audit-script digest, source baseline, and Review 33 disposition in the report. Expected contract digest: `9630C0CC67D033DB647587602E2797F4ACE9E937F3F0AB748FF6DE14EDC67F38`.
- [x] **Step 3: Record prerequisite custody without blocking implementation.** Search the actual main backlog for `MT-FU-1` and `MT-FU-2`. If either row is absent, record the result in the baseline report as a blocker to overall contract approval and design-document ungating only; it does **not** block this implementation plan, so continue to Task 1. Do not edit the backlog or silently treat the absence as resolved.
- [x] **Step 4: Run the unchanged hermetic baseline.** Run:

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_stdio_ndjson.py tests/unit/agent/test_runner.py tests/unit/agent/test_planning_loop.py tests/unit/agent/test_state_store.py tests/unit/telemetry/test_events.py tests/unit/telemetry/test_fanout.py -q
  uv run --frozen ruff check src/optimus/acp src/optimus/agent src/optimus/telemetry tests/unit/acp tests/unit/agent tests/unit/telemetry
  git diff --check
  ```

  Expected: all selected baseline tests pass. Any pre-existing failure is recorded and resolved as a separate custody decision before this plan continues.
- [x] **Step 5: Record negative-existence anchors.** Record exact searches proving the baseline has no `TurnControl`, `NoticeControl`, `ResponseOwnershipSlot`, `candidate_plan_text`, `ACP_TURN_SETTLEMENT`, conversation accumulation, concurrent-prompt guard, or shared writer serialization.
- [x] **Step 6: Commit the baseline report.** Commit with `docs: record Plan 11.25 implementation baseline`.

### Task 1: Implement the pure settlement model and exact work-class registry

**Files:**

- Create: `src/optimus/acp/settlement.py`
- Create: `tests/unit/acp/test_settlement.py`

**Interfaces:** Produces immutable `WorkClassSpec`, `WORK_CLASS_REGISTRY`, `SendState`, `SendOutcome`, directive terminal enums, `Settlement`, `FinalDelivery`, `RpcResponseDelivery`, `ConversationCommit`, `EffectState`, and `TurnSettlementSnapshot`. Tasks 2-10 import these exact types; no later task defines a competing vocabulary.

- [x] **Step 1: Write RED exact-set registry tests.** Pin all 15 §2.4.0 rows and all eight fields: class, kind, owner, gate/lane, start operation, lifecycle vocabulary, terminal vocabulary, and consequence. Assert nine and only nine rows have `kind == send`; settlement telemetry has no owner/start/lifecycle/terminal; protocol response mutates only `rpc_response_delivery`; plan persistence uses `persisted/persistence_failed/persistence_partial/suppressed`; Planning READ and Gateway include their full terminal sets.
- [x] **Step 2: Write RED algebra tests.** Cover `E == 0 -> none`, all effectful directives succeeded -> `complete`, any `failed_effect_unknown` -> `indeterminate`, otherwise at least one succeeded -> `partial`, and `failed_no_effect`/`suppressed`-only -> `none`. Assert READ, Gateway, and plan persistence never enter `E`.
- [x] **Step 3: Run RED.** Run:

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_settlement.py -q
  ```

  Expected: collection fails because `optimus.acp.settlement` does not exist.
- [x] **Step 4: Implement the immutable values.** Use `StrEnum` and frozen dataclasses. The registry object is one module-level immutable tuple imported by production and tests. Its field values must match the settled table exactly; do not abbreviate terminal vocabularies.

  ```python
  @dataclass(frozen=True, slots=True)
  class WorkClassSpec:
      work_class: WorkClass
      kind: WorkKind
      owner: OwnerKind | None
      gate_lane: GateLane | None
      start_operation: StartOperation | None
      lifecycle_vocabulary: frozenset[str]
      terminal_vocabulary: frozenset[str]
      consequence: Consequence
  ```

  Immediately below this type, define `WORK_CLASS_REGISTRY: tuple[WorkClassSpec, ...]` as the 15-record literal pinned by the RED exact-set test. A generated/default record is forbidden: every field must be visibly supplied for every row.

- [x] **Step 5: Implement pure consequence functions.** Add total functions that map authoritative send outcomes to `final_delivery`, `rpc_response_delivery`, provisional-history state, permission approval eligibility, and notice behavior. Unknown class/outcome combinations raise an invariant error; they never default to best effort.
- [x] **Step 6: Run GREEN and static checks.** Run the Task 1 selector, Ruff on both files, and `git diff --check`.
- [x] **Step 7: Commit.** Commit with `feat: define multi-turn settlement model`.

### Task 2: Implement `TurnControl` and deterministic turn-owned lifecycle transitions

**Files:**

- Create: `src/optimus/acp/lifecycle.py`
- Create: `tests/unit/acp/test_lifecycle.py`
- Modify: `src/optimus/acp/settlement.py` only if a pure value needed by the approved interface was omitted

**Interfaces:** Produces `TurnControl`, `TerminalDecision`, turn-owned `SendSlot`, and the turn half of `SendOwner`. Required public operations are `register_operations`, `try_start`, `complete_directive`, `request_session_cancel`, `halt_requested`, `seal_final_delivery`, `start_terminal_message`, `start_response_send`, `request_transport_teardown`, `publish_authoritative`, `publish_diagnostic`, and `finalize_once`.

- [x] **Step 1: Write RED gate and terminal-lane tests.** Use barriers to exercise both lock orders for execution start versus cancel/teardown, cancel versus terminal-lane sealing, terminal-message start versus teardown, and response start versus already-abandoned transport. Assert direct-denial starts create terminal `suppressed` slots atomically.
- [x] **Step 2: Write RED freeze/idempotence tests.** Cover queued suppression, write-started freeze to `ambiguous`, all message-class consequences, frozen snapshot immutability, repeated teardown as a pure read, late directive reports as diagnostic only, and repeated `finalize_once` returning the first outcome.
- [x] **Step 3: Run RED.** Run `uv run --frozen pytest tests/unit/acp/test_lifecycle.py -q`; expected failure is missing `TurnControl` and related types.
- [x] **Step 4: Implement the single-lock state.** One `threading.Lock` owns the execution gate, terminal lane, cancellation flag, transport flag, registered directive states, turn-owned send slots, frozen terminal decision, teardown snapshot/classification, permission handle reference, and finalization claim/outcome. No method performs I/O or awaits.

  ```python
  def seal_final_delivery(self) -> TerminalDecision:
      with self._lock:
          if self._terminal_decision is None:
              lane = (
                  TerminalLane.DECLINED
                  if self._transport_abandoned or self._terminal_lane is TerminalLane.DECLINED
                  else TerminalLane.GRANTED
              )
              self._terminal_lane = lane
              self._terminal_decision = TerminalDecision(
                  lane=lane,
                  cancellation_accepted=self._cancellation_accepted,
              )
          return self._terminal_decision
  ```

- [x] **Step 5: Implement exact directive vocabularies.** Planning READ, Gateway, READ, WRITE, TEST, and plan persistence receive their declared states. Teardown freezes started Gateway as `cost_unknown`, started WRITE/TEST as `failed_effect_unknown`, started READ as `abandoned_no_effect`, and started plan persistence as `persistence_partial`.
- [x] **Step 6: Implement identity-conditional finalization.** `finalize_once` invokes an injected active-map remover only when `(session_id, turn_seq, object identity)` still matches. It claims and records under the lock, releases the lock, then invokes an injected non-raising settlement callback at most once.
- [x] **Step 7: Run GREEN, stress repeat, and static checks.** Run the selector 20 times using pytest's normal deterministic barriers rather than sleeps, then Ruff and `git diff --check`.
- [x] **Step 8: Commit.** Commit with `feat: add atomic ACP turn control`.

### Task 3: Implement `NoticeControl`, response/warning capabilities, and the permission handle

**Files:**

- Modify: `src/optimus/acp/lifecycle.py`
- Modify: `tests/unit/acp/test_lifecycle.py`
- Modify: `src/optimus/acp/server.py` only for the channel's synchronous request-ID allocator seam; do not route writes yet
- Modify: `tests/unit/acp/test_outbound_errors.py`

**Interfaces:** Produces `ResponseSendKey`, `WarningAttemptSendKey`, `SendTicket`, `SendCompletion`, `ResponseHandle`, `WarningSequenceHandle`, `NoticeControl`, and `PermissionRequestHandle`. Every queued notice item holds a strong handle reference and one writer token; no API finalizes from a bare retired ID.

- [x] **Step 1: Write RED response-capability tests.** Cover ordinary `{response}` and refusal `{response, terminal_refusal_notice}` role sets, exactly-once role start, explicit close-as-not-attempted, direct suppressed completion after abandonment, writer-token acquisition before visibility, finalization-before-writer and writer-before-finalization retirement orders, retained-handle late duplicate finalization, and bare retired ID rejection.
- [x] **Step 2: Write RED warning tests.** Cover process-wide monotonic warning/attempt IDs, typed-key non-collision against response keys, one in-flight attempt, coordinator token handoff/abort, incremental child retirement during a long retry sequence, flush closure, teardown closure, queued-suppressed final attempt, and write-started-frozen final attempt.
- [x] **Step 3: Write RED permission tests.** Assert `allocate_request()` allocates and registers synchronously, two sessions cannot cross-correlate, every send outcome settles/cleans the response future correctly, a flushed-but-unanswered request is cancelled by teardown, a genuine response wins safely, and late replies to removed correlations are no-ops.
- [x] **Step 4: Run RED.** Run the lifecycle and outbound-error selectors; expected failures are missing capability and handle methods.
- [x] **Step 5: Implement typed identities and completions.** Use frozen tagged dataclasses; variant type participates in equality. `SendCompletion` always carries the exact key.

  ```python
  @dataclass(frozen=True, slots=True)
  class ResponseSendKey:
      response_id: int
      part: ResponsePart

  @dataclass(frozen=True, slots=True)
  class WarningAttemptSendKey:
      warning_id: int
      attempt_id: int

  SendKey = str | ResponseSendKey | WarningAttemptSendKey
  ```

- [x] **Step 6: Implement handle-local lifetime authority.** `NoticeControl` uses a registry lock only to allocate/snapshot/compare-remove handles. Each handle owns its own state lock, slots, role closure, tokens, and finalization tombstone. Follow registry-then-handle only as a two-phase snapshot; never nest locks in opposite order.
- [x] **Step 7: Implement permission correlation as one object.** The channel allocates `request_id`, future, payload, and correlation in one non-awaiting call. `handle.send()` obtains the turn's Permission send lease and later pattern-matches `SendCompletion`; `handle.cancel()` removes and resolves the correlation without revising send delivery state.
- [x] **Step 8: Run GREEN and static checks.** Run focused selectors, Ruff, and `git diff --check`.
- [x] **Step 9: Commit.** Commit with `feat: add notice and permission capabilities`.

### Task 4: Replace direct NDJSON writes with the dedicated FIFO writer

**Files:**

- Create: `src/optimus/acp/outbound_writer.py`
- Create: `tests/unit/acp/test_outbound_writer.py`
- Modify: `src/optimus/acp/server.py`
- Modify: `tests/unit/acp/test_stdio_ndjson.py`
- Modify: `tests/unit/acp/test_outbound_errors.py`
- Modify: `tests/unit/acp/test_main_wiring.py`

**Interfaces:** Produces process-lifetime `DedicatedOutboundWriter.start()`, `submit(item: OutboundQueueItem) -> concurrent.futures.Future[SendCompletion]`, and `close_and_join()`. Queue items contain payload, exact `SendKey`, `SendOwner`, optional strong capability handle, exactly one writer token, and the source future.

- [x] **Step 1: Write RED FIFO/serialization tests.** Submit notification, outbound request, and protocol response items from concurrent threads/tasks. Pause the first physical write and prove the second cannot call write or flush until the first completes; prove unrelated `asyncio.to_thread` work still starts while the writer is blocked.
- [x] **Step 2: Write RED phase tests.** Cover preparation failure before `write`, failure during/after `write`, flush failure, normal flush, queued teardown suppression, write-started teardown freeze plus late diagnostic, pre-dequeue source-future cancellation, and an exception from per-item bookkeeping. Assert every branch publishes authority first, resolves `SendCompletion` second, releases its token last, and continues to the next item.
- [x] **Step 3: Write RED shutdown tests.** Push the sentinel after accepted submissions, prove all pre-sentinel suppressed/normal/frozen items resolve and release tokens, prove the thread is non-daemon, and prove join occurs exactly once with no timeout.
- [x] **Step 4: Run RED.** Run:

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_outbound_writer.py tests/unit/acp/test_stdio_ndjson.py tests/unit/acp/test_outbound_errors.py -q
  ```

- [x] **Step 5: Implement a synchronous physical transport seam.** The dedicated thread must own JSON encoding plus the physical `write` and `flush` calls. `StdioNdjsonLineWriter` exposes/injects those synchronous primitives; asyncio request tasks never call them directly.
- [x] **Step 6: Implement the queue algorithm exactly.** Prepare payload before the item lock; call `set_running_or_notify_cancel`; under the exact item lock transition queued to write-started or observe suppressed; perform I/O lock-free; under the same item lock publish authority/diagnostic; resolve the exact keyed completion; release the token. Awaiters use `asyncio.shield(asyncio.wrap_future(source_future, loop=loop))`.
- [x] **Step 7: Remove NDJSON bypasses.** `NdjsonOutboundChannel` and `process_request` may submit only through the dedicated writer. Retain legacy framed `handle_one`/`serve` byte-writer behavior because it is outside the NDJSON ACP path. Add an AST or exact grep test that fails on a new direct NDJSON physical write outside `outbound_writer.py`/the physical adapter.
- [x] **Step 8: Run GREEN and full ACP writer checks.** Run focused tests, all `tests/unit/acp/test_stdio_ndjson.py`, Ruff, and `git diff --check`.
- [x] **Step 9: Commit.** Commit with `feat: serialize ACP NDJSON delivery`.

### Task 5: Implement canonical in-memory conversation, sanitization, budget, gauge, and cost

**Files:**

- Create: `src/optimus/acp/conversation.py`
- Create: `tests/unit/acp/test_conversation.py`
- Modify: `src/optimus/acp/bootstrap.py`
- Modify: `src/optimus/acp/server.py`
- Modify: `src/optimus/acp/shapes.py`
- Modify: `tests/unit/acp/test_bootstrap.py`
- Modify: `tests/unit/acp/test_shapes.py`

**Interfaces:** Produces `ConversationTurn`, `ConversationState`, `ConversationSanitizer`, `AdmissionDecision`, `CommitDecision`, `UsageGauge`, and `CONVERSATION_MAX_BYTES = 524_288`. `AcpSpecSession` will own one `ConversationState` in Task 7.

- [x] **Step 1: Write RED canonical-render tests.** Use quotes, delimiter-like text, Unicode, CR/LF variants, and inert-plan marker text. Assert one deterministic UTF-8 JSON representation, exact byte length after escaping, stable ordering, and an explicit wrapper that keys records by `turn_seq` without adding `turn_seq` as a sixth record field.
- [x] **Step 2: Write RED sanitization tests.** Inject a prefix-detectable secret, exact API key, raw and percent-decoded URI passwords, username, absolute workspace path, and known PII. Assert API key/password/path are absent; username is not blanket-redacted; `known_pii` is empty; and admission measurement, current planner input, history-bearing send, committed record, and next planner envelope receive the identical sanitized value.
- [x] **Step 3: Write RED cap/warning/gauge tests.** Assert literal cap, first warning byte `419_431`, first-crossing-only behavior, warning confirmed by flush not attempt, admission crossing no history/cost, commitment crossing commits then closes, `delivery_indeterminate` dominance, and gauge values `used // 4`, `size // 4` without driving decisions.
- [x] **Step 4: Write RED cost tests.** Assert planning result is applied once before any result-derived send, approved execution is not applied, rejection/cancellation retain planning cost, refusal/concurrency add zero, unknown cost permanently omits cumulative cost, and request-ID reuse cannot trip the per-turn idempotence guard.
- [x] **Step 5: Run RED.** Run the conversation, bootstrap, and shapes selectors; expected failure is the missing module and UsageUpdate builder.
- [x] **Step 6: Implement sanitizer construction at bootstrap.** From the already-authorized `environ`, collect `OPTIMUS_API_KEY`; parse only password components from `OPTIMUS_GATEWAY_URL` and `OPTIMUS_REDIS_URL`; add raw and `urllib.parse.unquote` forms; use `known_pii=()`; build one canonical-workspace `PathAliasRule`. Pass the immutable inputs into `AcpStreamServer`; never reread `os.environ` in session/turn code.
- [x] **Step 7: Implement canonical state and decisions.** Store records in a monotonic `turn_seq -> five-field record` map. Sanitize each text once, render from stored values, measure rendered bytes, and expose explicit `prepare_admission`, `apply_planning_cost_once`, `prepare_commit`, `commit_after_final_flush`, `latch_delivery_indeterminate`, and `usage_gauge` operations.
- [x] **Step 8: Implement the UsageUpdate shape.** Use ACP schema `uint64` integers and no floating-point arithmetic. Keep existing workspace-envelope constants byte-identical.
- [x] **Step 9: Run GREEN and static checks.** Run focused tests, existing sanitization tests, Ruff, and `git diff --check`.
- [x] **Step 10: Commit.** Commit with `feat: add canonical ACP conversation state`.

### Task 6: Instrument the runner, planning loop, Gateway, directives, and plan persistence

**Files:**

- Create: `src/optimus/agent/operation_control.py`
- Modify: `src/optimus/agent/models.py`
- Modify: `src/optimus/agent/runner.py`
- Modify: `src/optimus/agent/planning_loop.py`
- Modify: `src/optimus/agent/state_store.py`
- Modify: `tests/unit/agent/test_models.py`
- Modify: `tests/unit/agent/test_runner.py`
- Modify: `tests/unit/agent/test_planning_loop.py`
- Modify: `tests/unit/agent/test_state_store.py`

**Interfaces:** `AgentRunner.run(request, *, planning_progress_observer=None, client_mcp_service=None, mcp_permission_broker=None, halt_requested: Callable[[], bool] | None = None, operation_control: TurnOperationControl | None = None)` accepts per-call state. `AgentRunResult.candidate_plan_text` is copied directly from `PlanningLoopResult.plan_text`. `PlanningLoopRunner.to_planning_result()` rechecks the per-call halt signal unconditionally before every stop-reason conversion. ACP passes the exact `TurnControl` object as the protocol implementation; non-ACP callers may pass neither and retain baseline behavior.

- [x] **Step 1: Write RED model/candidate tests.** Cover real final plan, refusal, typed planning failure, unparseable output, rejection, and approved execution. Assert only a real parsed candidate produces non-null `candidate_plan_text`, and approved execution preserves the same candidate without duplicating planning cost.
- [x] **Step 2: Write RED halt tests.** Pass two concurrent per-call callbacks into one shared `AgentRunner`; halt A before first iteration, between iterations, during FINAL_PLAN/REFUSE/typed-failure conversion, and after B starts. Separately, for each controller-selected `REPEATED_FAILURE`, `BUDGET_EXHAUSTED`, `WALL_CLOCK`, and `MAX_ITERATIONS` stop, make the callback become true after `_stop_reason()` has selected that stop but before `to_planning_result()` dispatches it. Assert A settles `PLANNING_HALTED`, B is unaffected, completed-iteration cost is retained, the preselected non-completed stop is not reported, and no new stop reason is introduced.
- [x] **Step 3: Write RED directive lifecycle tests.** Cover every Gateway wire attempt/retry, Planning READ, approved READ including implicit pre-WRITE read, WRITE, TEST, and plan persistence. Assert lease denial prevents producer invocation; successful/clean-failure/unknown-effect states are published with unique deterministic operation IDs.
- [x] **Step 4: Write RED persistence tests.** For in-memory and Redis-style controlled clients, cover persisted, clean failure before any write, partial failure after primary write/expiry/pointer boundary, and teardown-frozen partial. Assert only `persisted` can authorize approved execution.
- [x] **Step 5: Run RED.** Run the four named agent selectors; expected failures are missing field, per-call parameters, control protocol, and persistence outcomes.
- [x] **Step 6: Implement the narrow protocol.** The protocol exposes only the exact directive registration/start/completion and halt operations the runner needs. It holds no copied booleans and no ACP transport methods.
- [x] **Step 7: Thread per-call values and hoist the terminal halt recheck.** Add keyword-only parameters to `run`, `_run_once`, and `_run_multi_turn_planning`; pass `halt_requested` into the existing `PlanningLoopRunner` constructor. In `PlanningLoopRunner.to_planning_result()`, move `human_halt_requested or self._halt_requested()` to the first terminal-conversion branch, before the `COMPLETED`, `REPEATED_FAILURE`, and mapped-stop dispatches; return `PLANNING_HALTED` there and remove the now-nested duplicate. Do not alter `_PLANNING_STOP_REASONS`, controller stop selection, or turn state placement in `AgentRunner.__init__`.
- [x] **Step 8: Instrument producers at their real boundaries.** Register when directives become known; call start immediately before the actual producer; complete once from the real result/exception. On `BaseException` escape from a started Gateway attempt, publish `cost_unknown` before re-raising. Planning iteration remains outside registered lifecycle and uses only the existing halt mechanism.
- [x] **Step 9: Make persistence failure explicit.** Add a typed result/error carrying completed substeps. The runner classifies without treating partial persistence as authorizing and without adding persistence to repository `effect_state`.
- [x] **Step 10: Run GREEN and regression checks.** Run focused selectors plus `tests/unit/agent`, Ruff on changed modules, and `git diff --check`.
- [x] **Step 11: Commit.** Commit with `feat: govern ACP runner operations per turn`.

### Task 7: Rewrite the ACP adapter around admission, one `TurnControl`, and one terminal cutoff

**Files:**

- Modify: `src/optimus/acp/spec.py`
- Modify: `src/optimus/acp/lifecycle.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`
- Modify: `tests/unit/acp/test_lifecycle.py`

**Interfaces:** `AcpDuplexAdapter.handle_client_request(request, ownership_slot)` returns `TurnResponseEnvelope | NonTurnResponseEnvelope`. Turn admission synchronously allocates `turn_seq`, constructs/binds/registers the exact `TurnControl`, and then enters the outer `try`. `finalize_once` is the only `_active_turns` removal path.

- [x] **Step 1: Write RED admission/concurrency tests.** Cover two sequential prompts reusing one wire ID, two concurrent same-session prompts, unknown session, empty/invalid prompt, terminal disposition refusal, and admission cap refusal. Assert internal identity uses `session_id:turn_seq`; concurrent error is `REQUEST_CANCELLED` with exact message; non-admitted paths create no turn/history/cost.
- [ ] **Step 2: Write RED cancellation phase tests.** Cover before first iteration, mid-iteration, after candidate/before permission allocation, after allocation/before response, permission rejection/cancel, mid-approved execution, and cancel after cutoff. Assert the atomic terminal decision controls settlement/text, plan-bearing follows `candidate_plan_text`, effects are not undone, and permission correlations are cleaned.
- [ ] **Step 3: Write RED terminal-set/fallback tests.** Cover plan-bearing and planless required sets, pending-plan suppression/flush, partial terminal delivery, conclusive pre-write failure, ambiguous write/flush, fallback before and after normal seal, cancellation racing fallback, and every cell of the §2.6a matrix.
- [ ] **Step 4: Run RED.** Run `test_spec_protocol.py` plus lifecycle selectors; expected failures identify legacy `AcpPromptTurn.cancelled`, direct outbound calls, unconditional active-map pop, and dict-only responses.
- [x] **Step 5: Replace session and turn records.** Add `ConversationState` to `AcpSpecSession`. Replace legacy cancellation/pending fields with the exact `TurnControl` and permission handle. Admission performs construct → slot bind → identity-register without logging, model creation, callbacks, or await between them.
- [x] **Step 6: Pass exact per-turn runtime inputs.** Build `AgentRunRequest.task` from the canonical sanitized conversation envelope and current prompt. Pass the exact control as `operation_control` and `halt_requested=turn_control.halt_requested` only on planning; approved execution receives operation control but no planning halt callback.
- [x] **Step 7: Govern every adapter send.** Progress/provisional/permission use `try_start`; terminal/fallback messages use the frozen terminal decision then `start_terminal_message`; protocol response remains server-owned. Apply planning cost before any result-derived send. Commit conversation only after the final required message's authoritative flush.
- [ ] **Step 8: Implement normal refusal and warning scheduling.** A terminal-disposition refusal allocates a two-role response handle, independently submits the best-effort notice, and returns a non-turn response envelope. An 80% crossing allocates one warning sequence and transfers its coordinator token without an intervening await; retries are independent of the triggering turn and stop only on flush/transport abandonment/abort.
- [ ] **Step 9: Implement fallback as one path.** Seal once, derive cancelled-versus-failed from the returned pair, construct the complete plan-bearing/planless required set, start each sub-send, apply the table consequence, and return a turn envelope. Never send a second copy after ambiguous delivery.
- [x] **Step 10: Run GREEN and adapter regressions.** Run all ACP spec tests, agent runner tests needed by the real adapter, Ruff, and `git diff --check`.
- [ ] **Step 11: Commit.** Commit with `feat: orchestrate multi-turn ACP sessions`.

### Task 8: Bind request ownership and response finalization in the server

**Files:**

- Modify: `src/optimus/acp/lifecycle.py`
- Modify: `src/optimus/acp/server.py`
- Modify: `src/optimus/acp/__main__.py`
- Modify: `tests/unit/acp/test_lifecycle.py`
- Modify: `tests/unit/acp/test_stdio_ndjson.py`
- Modify: `tests/unit/acp/test_main_wiring.py`

**Interfaces:** Produces `ResponseOwnershipSlot`, `TurnResponseEnvelope`, and `NonTurnResponseEnvelope`. `process_request` creates one empty slot, passes it through adapter dispatch, validates the returned envelope against it, submits exactly one response, and finalizes through the exact owner.

- [ ] **Step 1: Write RED routing tests.** Table-drive initialize, session/new success/error, invalid/method-not-found, unknown session, concurrent prompt, empty prompt, terminal refusal, begun-turn success, begun-turn typed error, and generic exceptions before/after admission. Assert empty slot routes to a new response handle; bound slot routes to the same `TurnControl`; mismatched owner/envelope is an invariant failure settled through the bound control.
- [ ] **Step 2: Write RED response-exit tests.** For both envelope kinds cover flushed, conclusive failure, ambiguous, direct suppressed/not-attempted, and server-task cancellation. Assert one queue item, no second physical write, exact `rpc_response_delivery`, one finalizer, and no premature `_active_turns` removal.
- [x] **Step 3: Write RED transport-loss ordering tests.** Prove `NoticeControl.mark_transport_abandoned()` completes before any request-task cancellation, then each bound turn runs idempotent teardown; later notice/warning starts are suppressed. Prove end-of-stream/unroutable no-response input allocates no owner.
- [x] **Step 4: Run RED.** Run lifecycle and stdio selectors; expected failures are missing slot/envelope flow and current direct/generic second-write paths.
- [x] **Step 5: Implement slot-only routing.** Generic handlers must inspect only the slot, never method names or intended envelope type. If post-admission envelope construction/submission fails, freeze/finalize the bound control directly; never borrow `NoticeControl`.
- [x] **Step 6: Remove the second-write exception path.** Pattern-match `SendCompletion.outcome`; future source exceptions are forbidden by writer contract. Server-task cancellation uses immediate frozen state and does not wait for the shielded writer source future.
- [x] **Step 7: Wire process lifetime.** Construct one `NoticeControl` and one `DedicatedOutboundWriter` for the process-owned NDJSON runtime. At connection loss mark notices abandoned before cancelling request tasks. At top-level process shutdown, after `asyncio.run` returns, push one writer sentinel and join without timeout.
- [x] **Step 8: Run GREEN plus bypass search.** Run all stdio/main-wiring tests and the AST/direct-write oracle; confirm no NDJSON send bypasses the dedicated writer.
- [x] **Step 9: Commit.** Commit with `feat: bind ACP response ownership end to end`.

### Task 9: Add contained production settlement evidence and post-teardown policy

**Files:**

- Modify: `src/optimus/telemetry/events.py`
- Modify: `src/optimus/telemetry/fanout.py` only if a narrow helper is needed; do not weaken ordinary fanout semantics globally
- Modify: `src/optimus/acp/bootstrap.py`
- Modify: `src/optimus/acp/lifecycle.py`
- Modify: `tests/unit/telemetry/test_events.py`
- Modify: `tests/unit/telemetry/test_fanout.py`
- Modify: `tests/unit/acp/test_lifecycle.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`

**Interfaces:** `TelemetryEventKind.ACP_TURN_SETTLEMENT` carries only `session_id`, `turn_seq`, interruption phase, settlement, final/rpc delivery, conversation commit, effect state, provider-attempt flag, cost completeness, prior-history-flush flag, and `post_teardown`. `TurnControl.finalize_once` invokes a synchronous non-raising sink adapter after releasing its lock.

- [ ] **Step 1: Write RED schema/privacy tests.** Assert the exact allowed settlement fields and reject prompt, plan, completion text, tool arguments/results, credentials, exception text, and arbitrary metadata.
- [ ] **Step 2: Write RED failure-containment tests.** Inject JSONL, Redis, and Gateway exporter failures separately while finalizing ordinary response, generic exception, and `CancelledError`. Assert the original return/exception survives, no second response is submitted, finalization stays claimed, and telemetry is attempted once.
- [ ] **Step 3: Write RED post-teardown tests.** Assert ordinary `agent_run` is denied after teardown; actual usage from an already-started provider attempt may append with `turn_seq`/`post_teardown=true` but never revises session cost; settlement evidence is still attempted.
- [ ] **Step 4: Run RED.** Run telemetry and lifecycle/spec selectors.
- [ ] **Step 5: Implement the event and containment boundary.** Reuse the production fanout built in bootstrap. Catch/log sink `Exception` only around this evidence attempt, after the finalization lock is released; do not catch or replace the surrounding `CancelledError`.
- [ ] **Step 6: Run GREEN and privacy searches.** Run focused tests, serialize sample events, grep for forbidden content fields, Ruff, and `git diff --check`.
- [ ] **Step 7: Commit.** Commit with `feat: emit ACP turn settlement evidence`.

### Task 10: Execute the complete contract scenario matrix

**Files:**

- Create: `tests/e2e/acp/test_multi_turn_conversation.py`
- Modify: focused unit tests only where a contract predicate lacks direct evidence
- Create: `reports/plan-11-25-multi-turn-contract-evidence.md`

**Interfaces:** Consumes the integrated runtime. Produces a predicate-indexed evidence report; no new production interface is introduced in this task.

- [ ] **Step 1: Build the hermetic dependent-follow-up fixture.** Drive the real ACP NDJSON server and a controlled deterministic runner/model so turn 2 must use a sanitized fact committed by turn 1. Assert neither warning nor refusal fires and the answer cannot be produced from turn 2 alone.
- [ ] **Step 2: Run identity/cap/surface scenarios.** Cover request-ID reuse, exact cap admission/commitment, first warning crossing/retry, unknown session versus terminal refusal, same-session concurrent prompt, approximate gauge, no-history refusal/warning, and failed-refusal state preservation.
- [ ] **Step 3: Run cancellation/teardown scenarios.** Cover every planning outcome row, permission lifecycle, approved execution, fallback table, final-delivery/teardown table, response exits, stale callback, late worker report, plan persistence, Gateway unknown cost, writer shutdown, and no second write on broken transport.
- [ ] **Step 4: Run sanitization/cost/effect scenarios.** Cover both conversation text rows, raw/decoded URI passwords, path aliases, canonical adversarial framing, planning-cost idempotence, unknown-cost permanence, forced partial write, empty-effect plan, failed-no-effect, suppressed directive, and all-success effectful plan.
- [ ] **Step 5: Map every settled DoD predicate.** The report must give a test node ID and passing command for predicates `1`, `2`, `2b`, `3`, `4`, `4b`, `5.1` through `5.30` (including the separately named `5.12a` and `5.21a`, excluding retired `5.24`), `5c`, `5d`, `5e`, `5f`, `5h`, `5k`, `5l`, `5m`, `5n`, `5p`, `5q`, `5r`, `5s`, `5u`, `6`, `7`, and `8`. A predicate with no test node is an implementation gap, not a documentation omission.
- [ ] **Step 6: Run the complete hermetic suite.** Run:

  ```powershell
  uv run --frozen pytest tests/unit/acp tests/unit/agent tests/unit/telemetry tests/e2e/acp/test_multi_turn_conversation.py -q
  uv run --frozen coverage run -m pytest
  uv run --frozen coverage report --fail-under=80
  uv run --frozen ruff check .
  git diff --check
  ```

- [ ] **Step 7: Commit.** Commit the scenario suite and evidence report with `test: prove multi-turn conversation contract`.

### Task 11: Perform the final implementation review and truthful handoff

**Files:**

- Create: `reports/plan-11-25-multi-turn-release-review.md`
- Modify only after all gates pass and custody is authorized: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`, and the global `CURRENT.md`
- Audit only: settled contract, Review 33 checkpoint, README/current-state surfaces, and frozen historical plans

**Interfaces:** Produces the reviewer-ready implementation handoff. It does not declare external Zed/live-provider evidence that was not run.

- [ ] **Step 1: Run structural conformance searches.** Confirm one work registry, one physical NDJSON writer, no bare-ID finalization authority, no legacy `turn.cancelled`, no unconditional `_active_turns.pop`, no raw wire ID in internal run identity, no settlement telemetry in the send registry, and no result-promotion lifecycle.
- [ ] **Step 2: Re-run the contract-bound audit.** Recompute the settled contract and audit-script digests, run `self_audit_multi_turn.py` against the implementation revision, and retain valid JSON separately from stderr. This remains a premise sentinel; cite Task 10 for semantic proof.
- [ ] **Step 3: Run the full repository gates.** Run:

  ```powershell
  uv run --frozen pytest -q
  uv run --frozen coverage run -m pytest
  uv run --frozen coverage report --fail-under=80
  uv run --frozen ruff check .
  uv run --frozen bandit -r src
  git diff --check
  git status --short
  ```

- [ ] **Step 4: Review the diff by ownership boundary.** Review settlement vocabulary, locks/retirement, writer/futures, conversation/cap, runner instrumentation, adapter settlement, server routing, telemetry privacy, and tests as separate lenses. Reject the implementation if any requirement is satisfied only by a test double replacing a real project boundary object.
- [ ] **Step 5: Record named limitations honestly.** Preserve the settled limitations: process-local history only, possible provider overflow, approximate gauge, no fixed worker-exit deadline, terminal plan status always `completed`, unbounded writer queue/no backpressure, and unrecovered writer `BaseException` death.
- [ ] **Step 6: Update custody only with authorization.** Mark Plan 11.25 implemented only after the implementation review is accepted. Keep Slice 2/3, Plan 12, `MT-FU-1`, and `MT-FU-2` ownership unchanged. Do not edit frozen plans to erase historical statements.
- [ ] **Step 7: Commit the review handoff.** Commit with `docs: record Plan 11.25 implementation evidence`.

## Definition of Done and Evidence Map

| Contract area | Primary implementation task | Required evidence |
|---|---:|---|
| Five-field records, turn identity, canonical history | 5, 7 | `test_conversation.py`, real adapter sequential/request-ID-reuse tests, Task 10 dependent follow-up |
| Admission/commitment cap and disposition | 5, 7 | exact-byte boundary tests, ambiguous-history dominance, terminal-refusal tests |
| Exact eight-field class model and effect algebra | 1 | pinned exact-set registry and pure algebra tests |
| Atomic cancel/teardown/start/finalization | 2, 7 | deterministic lock-order/barrier tests and phase-specific adapter tests |
| Response/warning/permission capabilities and retirement | 3 | handle-local tombstone, writer-token, retry, and correlation tests |
| Dedicated writer and delivery classification | 4 | FIFO, phase, freeze/diagnostic, exception-containment, and drain/join tests |
| Planning/runner governed work and plan persistence | 6 | per-call isolation, halt precedence, directive terminal vocabulary, partial persistence tests |
| Required terminal set and fallback | 7 | plan-bearing/planless sets and complete §2.6a matrix |
| Request ownership and server response exits | 8 | table-driven real-envelope routing and no-second-write tests |
| Settlement telemetry and post-teardown policy | 9 | privacy schema, sink-failure containment, post-teardown append-only tests |
| Full settled DoD | 10 | predicate-to-node evidence report with no unmapped active predicate |
| Release readiness | 11 | full tests, coverage ≥80%, Ruff, Bandit, diff check, structural searches, reviewer acceptance |

## Cursor Execution Rules

- Cursor reads the settled contract section named by each task before editing that task. It does not need to ingest all 3,686 lines for every task, but it must re-read the complete current subsection and its mapped DoD predicates.
- Cursor implements one task at a time and stops at its commit/review boundary. No speculative code for a later task is folded into an earlier commit.
- Cursor writes the failing test first, runs the exact RED selector, implements only the named interface, runs GREEN plus regressions, then commits.
- Cursor may split a named module if review proves it cannot retain one responsibility, but must update this plan's file map and interface block before coding the split. It may not merge control, writer, and conversation state into `spec.py` for convenience.
- Cursor reports a blocker rather than choosing new behavior if the contract and source cannot both be satisfied. Mechanical difficulty is not authority to weaken a lifecycle, cleanup, identity, privacy, or settlement guarantee.

## Plan Self-Review

- **Spec coverage:** Every active top-level and numbered DoD predicate is assigned to Tasks 1-10 and must be mapped to a concrete test node in Task 10. Retired predicate 5.24 and out-of-scope Slice 2/3 items are explicitly excluded.
- **Dependency review:** Pure values precede mutable controls; controls/handles precede the writer; all three precede adapter/server integration. No task requires a temporary ownership or direct-write mechanism that contradicts the final model.
- **Type consistency:** `SendKey`, `SendTicket`, `SendCompletion`, `ResponseHandle`, `WarningSequenceHandle`, `TurnControl`, `NoticeControl`, `ResponseOwnershipSlot`, and both envelope variants are defined once and consumed by their later tasks under the same names.
- **Source fidelity:** The plan preserves the real shared `AgentRunner`, existing `PlanningLoopRunner.halt_requested` seam, synchronous state stores, current ACP shape builders, and top-level NDJSON teardown. It does not claim current concurrent-prompt, writer, or multi-turn behavior already exists.
- **Scope review:** This is one coupled vertical slice. Durability/resume/load and Plan 12 context optimization are independent future subsystems and are not smuggled into the implementation.
- **Placeholder review:** Every task names concrete files, interfaces, RED/GREEN commands, expected outcomes, and commit boundaries. No unnamed error handling, generic test instruction, or deferred implementation step remains.
