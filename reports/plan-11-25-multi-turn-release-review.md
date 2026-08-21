# Plan 11.25 — Multi-turn conversation Slice 1 release review

**Date:** 2026-08-22  
**Branch:** `agent/cursor/plan-11-25-multi-turn-conversation`  
**Implementation tip (pre-this-commit):** `7b82d3f1c8890297904d75708ee8dbb45e742e67`  
**Settled contract:** `BRAINSTORM-multi-turn-conversation-SETTLED.md`  
**Contract SHA-256:** `9630C0CC67D033DB647587602E2797F4ACE9E937F3F0AB748FF6DE14EDC67F38` (3,686 logical lines)  
**Audit-script SHA-256:** `1F681651E8C70E19692DB887453FA625E0CD537F9840FE0E21E4F0D853AB76EB`  
**Review 33:** post-repair contract-level GO (Codex authored/accepted; not a second independent external review)

This handoff is reviewer-ready for Slice 1 hermetic evidence. It does **not** claim Zed live-provider continuity, `session/resume`/`session/load`, or overall contract approval while `MT-FU-1` / `MT-FU-2` remain absent from the main backlog.

## Structural conformance (Step 1)

| Check | Result |
|---|---|
| One work registry | **PASS** — sole `WORK_CLASS_REGISTRY` in `src/optimus/acp/settlement.py` (15 rows; settlement telemetry is `evidence-append` with `owner/start/lifecycle/terminal = none`, not a send) |
| One dedicated NDJSON writer | **PASS** — `DedicatedOutboundWriter` owns physical `write_bytes`+`flush`; `__main__` constructs process-lifetime writer; `serve_ndjson` joins when owned |
| Fallback `write_line` | **PASS (scoped)** — `NdjsonOutboundChannel` / `submit_via_*` use `write_line` only when `dedicated_writer is None` (non-physical test transports). Production physical path uses the dedicated writer |
| No bare-ID finalization authority | **PASS** — `TurnControl.finalize_once` + identity-conditional `_remove_active_turn(session_id, turn_seq, control)`; no unconditional `_active_turns.pop` |
| No legacy `turn.cancelled` | **PASS** — zero matches under `src/` |
| Internal run identity | **PASS** — `run_id = f"{session_id}:{turn_seq}"` on `AcpPromptTurn`; wire JSON-RPC ids are correlation only |
| No result-promotion lifecycle | **PASS** — zero matches for result-promotion symbols under `src/` |
| Direct physical-write bypass grep | Covered by `tests/unit/acp/test_outbound_writer.py::test_no_direct_ndjson_physical_write_outside_writer_and_adapter` |

## Contract-bound audit (Step 2)

Command (stdout retained as JSON):

```text
uv run --frozen python D:/Projects/Development/Python/optimus-agent-handoff/self_audit_multi_turn.py \
  <repo> <contract> \
  --expect-contract-sha 9630C0CC67D033DB647587602E2797F4ACE9E937F3F0AB748FF6DE14EDC67F38 \
  --expect-script-sha 1F681651E8C70E19692DB887453FA625E0CD537F9840FE0E21E4F0D853AB76EB \
  --expect-revision 7b82d3f1c8890297904d75708ee8dbb45e742e67
```

Artifact: `reports/plan-11-25-self-audit-task11.json`

| Layer | Result |
|---|---|
| Binding (contract SHA, script SHA, HEAD, clean `src`/`tests`) | **4/4 PASS** |
| Premise line-number sentinels (facts 1b/15*/17 pinned to pre-Slice-1 line numbers) | **8 FAIL** — expected after Task 7–8 rewrite relocated notify/except/`run_id` sites |
| Overall `all_pass` | **false** (sentinel drift only) |

**Disposition:** The audit remains a **premise/binding sentinel**, not semantic correctness. Semantic proof is Task 10 (`reports/plan-11-25-multi-turn-contract-evidence.md`). Do not treat sentinel FAILs as implementation defects without rebinding the sentinel to post-Slice-1 anchors under a separate custody decision.

## Full repository gates (Step 3)

| Gate | Result |
|---|---|
| `uv run --frozen pytest -q` | **PASS** — 3475 passed, 28 skipped, 111 deselected |
| `uv run --frozen coverage run -m pytest` + `coverage report --fail-under=80` | **PASS** — aggregate **82%** (reconfirmed under Task 11) |
| `uv run --frozen ruff check .` | **PASS** |
| `uv run --frozen bandit -r src` | **RAN** — exit non-zero on pre-existing Medium findings (e.g. `urlopen`); Plan 11.25 modules show only Low `assert_used` in writer invariant paths — no High findings introduced |
| `git diff --check` | **PASS** |
| `git status --short` | clean at tip before this handoff commit (Task 11 files then staged) |

## Ownership-boundary review (Step 4)

| Lens | Verdict |
|---|---|
| Settlement vocabulary | Immutable registry + pure algebra; no I/O |
| Locks / retirement | Single-lock `TurnControl` / `NoticeControl`; capability retirement + writer tokens |
| Writer / futures | Dedicated non-daemon FIFO; phase freeze/diagnostic; drain/join |
| Conversation / cap | Five-field records; `524_288` / `419_431`; rendered UTF-8 admission |
| Runner instrumentation | `TurnOperationControl`; `candidate_plan_text`; halt; `PlanPersistenceResult` |
| Adapter settlement | Session conversation; concurrent-prompt guard; refusal vs cancel; `finalize_once` exclusivity |
| Server routing | `ResponseOwnershipSlot` + turn/non-turn envelopes; transport abandonment before cancel |
| Telemetry privacy | Content-free `ACP_TURN_SETTLEMENT`; contained fanout |
| Tests | Unit barriers (no sleeps) + hermetic NDJSON e2e; no fake standing in for a named live tier |

No requirement is satisfied only by a test double replacing a real project boundary object for Slice 1 hermetic claims.

## Named limitations (Step 5) — preserved from settled §5

- Conversation is process-local / same-thread-session only (no durability across restart).
- Provider overflow remains possible; the byte cap is a budget, not a guarantee.
- Gauge token figures are approximate (floor division by four; display-only).
- No fixed process-exit deadline after transport teardown; non-cooperative `to_thread` workers may outlive teardown.
- Fallback plan-status update always reads ACP `completed` (schema has no other terminal).
- Writer queue is unbounded (no backpressure); correctness preferred over latency.
- Unrecovered writer `BaseException` death remains a known limitation.
- Slice 2/3, Plan 12 compression/summarization/pruning/eviction, and non-AGENT carriage remain out of scope.
- `MT-FU-1` / `MT-FU-2` still **absent** from the main backlog — blocks overall contract approval and design-document ungating only (unchanged ownership; not silently resolved).

## Custody updates (Step 6)

Authorized by operator Task 11 approval. Updates:

- Roadmap execution snapshot: add Plan 11.25 as **Implemented (Slice 1 on branch; awaiting merge)**.
- Consolidated backlog Feature slices: add `P11-FEAT-MULTI-TURN-CONVERSATION` implemented-on-branch entry; **do not** invent `MT-FU-1`/`MT-FU-2` rows; leave Plan 12 / ZED-RESUME ownership unchanged.
- Global `CURRENT.md` (handoff, outside git): append Cursor Task 11 completion entry and refresh Header.

## Evidence index

| Artifact | Role |
|---|---|
| `reports/plan-11-25-multi-turn-baseline.md` | Task 0 baseline |
| `reports/plan-11-25-multi-turn-contract-evidence.md` | Task 10 DoD predicate map |
| `reports/plan-11-25-self-audit-task11.json` | Task 11 audit JSON (binding PASS / sentinel FAIL expected) |
| `reports/plan-11-25-multi-turn-release-review.md` | This document |

## Reviewer ask

Accept Slice 1 implementation for merge when structural + hermetic gates above are independently verified. Rebind or retire line-pinned premise sentinels under a separate decision. Restore `MT-FU-1` / `MT-FU-2` to the main backlog before overall contract approval / design-document ungating.
