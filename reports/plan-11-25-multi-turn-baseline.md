# Plan 11.25 multi-turn conversation — Task 0 baseline

**Status:** Pre-change characterization completed on a clean implementation branch.
Implementation of multi-turn settlement, lifecycle, writer, and conversation modules has
not started.

**Date:** 2026-08-21 (local 2026-08-22)

## Checkout

| Ref | Value |
|---|---|
| Worktree | `D:\Projects\Development\Python\optimus-cost-agent-wt-cursor` |
| Branch | `agent/cursor/plan-11-25-multi-turn-conversation` |
| `HEAD` | `c116eea7f2acf1bb42f026391c055bf22b3c3d5a` |
| `origin/main` | `c116eea7f2acf1bb42f026391c055bf22b3c3d5a` |
| Status | clean; `HEAD == origin/main` before Task 0 writes |

Operator override (Vibhanshu): use the existing Cursor worktree and a new branch forked
from `main`, rather than a fresh isolated worktree named in the plan's Global Constraints.
Reviewer checkpoint `docs/superpowers/reviews/plan-11-25-review-checkpoints.md` is absent
(expected: reviewer-owned, gitignored, not yet authored).

## Authority bytes

| Item | Recorded value |
|---|---|
| Settled contract path | `D:\Projects\Development\Python\optimus-agent-handoff\BRAINSTORM-multi-turn-conversation-SETTLED.md` |
| Contract SHA-256 | `9630C0CC67D033DB647587602E2797F4ACE9E937F3F0AB748FF6DE14EDC67F38` |
| Logical line count | `3686` |
| Audit script path | `D:\Projects\Development\Python\optimus-agent-handoff\self_audit_multi_turn.py` |
| Audit-script SHA-256 | `1F681651E8C70E19692DB887453FA625E0CD537F9840FE0E21E4F0D853AB76EB` |
| Plan-stated source baseline | `e5a796fd79425509d02e3cf17d562f62c5182228` |
| Implementation base (`HEAD`) | `c116eea7f2acf1bb42f026391c055bf22b3c3d5a` |
| Review 33 disposition | Post-repair contract-level GO (Codex authored and accepted the repair; not a second independent external review) |

Contract digest matches the plan's exact expected value. Task 0 does not stop.

## Prerequisite custody (`MT-FU-1` / `MT-FU-2`)

Searched the actual main backlog at
`docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` and the
Plan 11.25 plan file references.

| Row | Present in main backlog? |
|---|---|
| `MT-FU-1` | **absent** |
| `MT-FU-2` | **absent** |

Per plan Prerequisites and Task 0 Step 3: absence is a blocker to overall contract approval
and design-document ungating only. It does **not** block this implementation plan.
Backlog was not edited; absence is not treated as resolved.

## Hermetic baseline

Commands:

```powershell
uv run --frozen pytest tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_stdio_ndjson.py tests/unit/agent/test_runner.py tests/unit/agent/test_planning_loop.py tests/unit/agent/test_state_store.py tests/unit/telemetry/test_events.py tests/unit/telemetry/test_fanout.py -q
uv run --frozen ruff check src/optimus/acp src/optimus/agent src/optimus/telemetry tests/unit/acp tests/unit/agent tests/unit/telemetry
git diff --check
```

| Gate | Result |
|---|---|
| Selected pytest | **169 passed** in 6.78s |
| Ruff (named paths) | All checks passed |
| `git diff --check` | clean |

No pre-existing failure requiring a separate custody decision.

## Negative-existence anchors

Exact searches on `src/` and `tests/` at implementation base
`c116eea7f2acf1bb42f026391c055bf22b3c3d5a`:

| Anchor | Result |
|---|---|
| `TurnControl` | no matches |
| `NoticeControl` | no matches |
| `ResponseOwnershipSlot` | no matches |
| `candidate_plan_text` | no matches |
| `ACP_TURN_SETTLEMENT` | no matches |
| `src/optimus/acp/settlement.py` | absent |
| `src/optimus/acp/lifecycle.py` | absent |
| `src/optimus/acp/outbound_writer.py` | absent |
| `src/optimus/acp/conversation.py` | absent |
| Conversation accumulation / `CONVERSATION_MAX_BYTES` | absent from production ACP modules |
| Concurrent-prompt guard | absent; `AcpDuplexAdapter` keeps a single `_active_turns: dict[str, AcpPromptTurn]` keyed by `session_id` with unconditional `pop` on exit (`spec.py`) |
| Shared writer serialization | absent; NDJSON path calls `writer.write_line(...)` directly from request handlers (`server.py`) |

Existing `write_line` usage is the pre-Task-4 direct physical write path, not a dedicated
FIFO writer thread.

## Platform provenance

| Item | Value |
|---|---|
| `sys.platform` | `win32` |
| Host | Windows 10.0.26200 |
| Shell for Task 0 | PowerShell + `uv` |
| Tooling | `uv run --frozen` as specified by the plan |

## Next boundary

Task 0 complete. Per Cursor Execution Rules, stop at this commit/review boundary before
Task 1 (pure settlement model).
