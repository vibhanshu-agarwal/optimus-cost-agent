# Plan 9.85 — Multi-Turn Planning Live `acpx` Evidence

**Date:** 2026-07-12  
**OS:** Windows 11 Pro (10.0.26200)  
**Branch:** `agent/cursor/plan-9-85-multi-turn-planning`  
**Commit (implementation HEAD):** `6aba8fb59403ccd2483d77bc003c0a4ce932a4e4`  
**Model (operator / acpx live):** `claude-haiku`  
**Client:** `acpx` **0.12.0** (`npm install -g acpx`)  
**Agent:** `optimus-agent` **0.1.0** (`uv tool install --force -e .`)  
**Source checkout:** `D:\Projects\Development\Python\optimus-cost-agent-wt-cursor`  
**PROVENANCE (operator):** `git_sha=6aba8fb`, keychain / local-default credentials (`shell_has_gateway_url=false`, `shell_has_optimus_api_key=false`); no local provider keys in shell.

**Plan:** [`docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md`](../docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md)

---

## Summary

Plan 9.85's **oversized-required-context** multi-turn planning path is **live-verified** over real
**`acpx` 0.12.0** with local Optimus Gateway and TimeSeries-capable Redis under the one-key model.

| Scenario | Status |
|----------|--------|
| Step 2 — multi-turn success (READ_MORE → final plan → approve → mutate) | **Proven live** |
| Step 3 — turn-limit terminal (`PLANNING_TURN_LIMIT_EXHAUSTED`) | **Proven live** |
| Step 4 — superseded / wrong plan hash via live `acpx` injection | **Closed by design proof** (see below) |
| `P9.85-FU-4` model-initiated replan when Plan 9.8 context fits | **Deferred → Plan 9.87** |
| `P9.85-FU-5` live `REFUSE:` demonstration as Plan 9.85 closure | **Deferred → Plan 9.87** (supplementary early-run artifact noted) |

This does **not** claim intelligent compression (Plan 11), general mutation success for all tasks,
or model-initiated replanning when the initial Plan 9.8 block already fits.

---

## Evidence tiers (policy)

| Tier | Tool | Role in this report |
|------|------|---------------------|
| Unit / integration (fake Gateway) | `pytest` | Deterministic contract; not sufficient alone for live sign-off |
| Automated ACP (primary) | **`acpx` 0.12.0** (third-party) | Steps 2–3 live protocol proof |
| Operator helper (non-evidence) | `tools/run_plan985_acpx_live_evidence.py` | Workspace prep + `acpx` invocation; **not** an ACP client (untracked per repo convention) |
| Superseded | Project subprocess ACP harnesses | Not used (`P9.8-FU-6` policy) |

---

## Prerequisites (Task 8 Step 1)

| Check | Result |
|-------|--------|
| `acpx --version` | `0.12.0` |
| `optimus-agent --check-config --strict --debug-trace` | exit **0**, `Optimus ACP agent configuration OK.` |
| Redis TimeSeries | reachable via local defaults |
| Gateway auth probe | passed (`strict` preflight) |
| Shell provider keys | none (`provider_keys_in_env: []`) |
| Credential source | keychain / `apply_local_defaults` (no `OPTIMUS_*` in shell) |

**Windows `acpx` agent spawn:** `run-optimus-agent.cmd` wrapper in workspace (`--agent run-optimus-agent.cmd`, `--cwd` set). Required because `acpx` 0.12.0 on Windows cannot spawn `optimus-agent.exe` with inline arguments.

---

## Fixture and tasks

**Shared workspace file** (`large.py`, ~17 KiB):

- First line: `# large module` (readable header)
- Remainder: `x` filler to exceed Plan 9.8 single-pass complete-file inclusion

**Step 2 task (success path):**

```text
Edit large.py: replace the first line with # updated header
```

**Step 3 task (turn-limit path):**

```text
Edit large.py
```

(Vague task nudges the live model toward `READ_MORE` on turn 1; with `OPTIMUS_MAX_PLANNING_TURNS=1` there is no turn 2 for a final plan.)

---

## Step 2 — Multi-turn success (`acpx`)

**Artifact (local, not committed):** `reports/plan985-acpx-multiturn-output.jsonl`  
**Debug trace:** `reports/.plan985-acpx-workspace/.optimus/debug-acp.ndjson`  
**Workspace:** `reports/.plan985-acpx-workspace`  
**session_id:** `session-7cc6f451c06f47bdb37c71ea50fa170e`  
**run_id:** `session-7cc6f451c06f47bdb37c71ea50fa170e:2`  
**plan_hash:** `2be03177a7df5d136fd5828638d51cb40d03f5ddd2b08403c196a292129e3031`

| Claim | Evidence |
|-------|----------|
| Oversized required context trigger | `P9.8-CONTEXT`: `blocking_stop_reason=REQUIRED_WORKSPACE_FILE_TOO_LARGE`, `used_bytes=0` |
| ≥2 settled planning turns | Three `P9.85-REPLAN` events: `settled_turn` 1, 2, 3 |
| No permission after intermediate turns | `session/request_permission` appears only after turn 3 progress; transcript lines 6–8 are progress only |
| Content-free range telemetry | Turn 1: `large.py#bytes=0:200`; turn 2: `bytes=0:50`; sha256 + gateway IDs, no source bodies |
| Distinct Gateway request IDs | `gw-a121e6304f0443ac82ca61d292c2e188`, `gw-5c3dd6db5a8742f9930286ea1790033f`, `gw-ddd3512b44d94c2ab5c1d96688ca607c` |
| Aggregate reported cost | `reported_aggregate_cost_usd=0.002283` at settled turn 3 |
| One final permission | `session/request_permission` id **10000**; `--approve-all` → `optionId=approve` |
| Server-selected plan hash | `_meta.planHash` and options metadata match `2be03177…` |
| Post-approval mutation (gated write) | Transcript: `write_file` tool_call **after** permission id 10000 approve; debug `H7:approved_done`: `mutation_count=1`, `tool_names=["file_reader","file_reader","write_file"]`, `status=completed` |
| Terminal | `stopReason: end_turn` |

**Post-capture workspace note:** The DoD requires post-approval **mutation**, not proof of a
specific on-disk string. No artifact records write payload (content-free telemetry by design).
Immediately after this run, the operator script's post-run check reported `large_py_mutated: true`
(first line `# updated header`). At independent review time, `reports/.plan985-acpx-workspace/large.py`
had been reset to the pristine fixture (`# large module`; mtime later than the transcript). Only one
`session/prompt` for this `run_id` appears in the debug trace, so a second `acpx` pass is not the
explanation — a later local workspace rewrite (e.g. script `_prepare_workspace` on a subsequent
invocation) is the likely cause. **Mutation gating is cited from transcript + `H7` only**, not
current disk contents.

**Operator command:**

```powershell
uv tool install --force -e .
Remove-Item -Recurse -Force reports\.plan985-acpx-workspace -ErrorAction SilentlyContinue
uv run python tools/run_plan985_acpx_live_evidence.py --scenario multiturn
```

**Note:** Earlier attempts with `alpha` + `x` filler and vague task `"Edit large.py"` failed live
(repeated-read stop or model `REFUSE:`). Those runs are **not** cited as Step 2 evidence; they
informed fixture/task selection only.

---

## Step 3 — Turn-limit terminal (`acpx`)

**Artifact (local):** `reports/plan985-acpx-turn-limit-output.jsonl`  
**Debug trace:** `reports/.plan985-acpx-turn-limit-workspace/.optimus/debug-acp.ndjson`  
**Workspace:** `reports/.plan985-acpx-turn-limit-workspace`  
**session_id:** `session-f804cbaf3d244082bf9742e52cbfe1d1`  
**run_id:** `session-f804cbaf3d244082bf9742e52cbfe1d1:2`  
**Env:** `OPTIMUS_MAX_PLANNING_TURNS=1` (operator script child env)

| Claim | Evidence |
|-------|----------|
| Turn cap honored | Progress: `Planning turn 1 of 1: reading 1 guarded range.`; trace `max_planning_turns: 1` |
| `READ_MORE` on turn 1 | `read_identities: ["large.py#bytes=0:500"]` |
| Typed stop (wire = sanitized text only) | User-visible: `Planning stopped before a final plan could be settled.` |
| Template linkage | Unique string from `planning_corrective_text()` for `PLANNING_TURN_LIMIT_EXHAUSTED` (`planning_loop.py` ~line 555) |
| Telemetry stop (post-`6aba8fb`) | Second `P9.85-REPLAN`: `loop_stop: PLANNING_TURN_LIMIT_EXHAUSTED` |
| Zero permission | No `session/request_permission` in transcript |
| Zero mutation | `large_py_mutated: false`; `planning_done` `plan_hash: null`, `status: terminated` |
| Terminal | `stopReason: end_turn` |

**Operator command:**

```powershell
Remove-Item -Recurse -Force reports\.plan985-acpx-turn-limit-workspace -ErrorAction SilentlyContinue
uv run python tools/run_plan985_acpx_live_evidence.py --scenario turn_limit
```

**Note:** A mistaken rerun with the Step 2 concrete task under `max_planning_turns=1` produced a
**single-turn success** (permission + mutation). That file was superseded by the run above.

**ACP progress side effect (post-`6aba8fb`):** Both live transcripts include an extra
`agent_message_chunk` at settlement — multiturn `"Planning turn 3 of 3."`, turn-limit
`"Planning turn 1 of 1."` (no "reading N guarded ranges" clause). This is `emit_final_progress()`
through the same observer chain that feeds ACP `session/update` (Task 5 wiring). Harmless:
content-free; does not affect permission timing or `stopReason`.

---

## Step 4 — Superseded / wrong plan hash (design closure)

Live `acpx` cannot inject a client-supplied plan hash into execution:

1. **ACP replay uses server hash only** — `spec.py` builds `AgentApproval` with
   `plan_hash=planning_result.plan_hash`, not client permission metadata.
2. **`optimus.agent.run` is not on the NDJSON wire** — `serve_ndjson()` routes only through
   `AcpDuplexAdapter`; `JsonRpcDispatcher.dispatch("optimus.agent.run")` is unreachable during
   `acpx` sessions.
3. **Unit / ACP tests prove fail-closed behavior** — `tests/unit/agent/test_runner.py`
   (`PLAN_NOT_FOUND_OR_EXPIRED` on stale/missing hash); `test_superseded_approval_hash_does_not_execute_plan`
   proves `runner.requests[-1].approval.plan_hash == "hash-final"` regardless of client
   `metadata.planHash` (test name is misleading; assertion is still valuable).

**Disposition:** Step 4 is closed as **documented ACP trust boundary + deterministic tests**, not
a live `acpx` injection scenario. Hash approval replay integrity is a server-side property by design.

---

## Redacted debug excerpts (no source / secrets)

### `P9.8-CONTEXT` (multiturn, oversized trigger)

```json
{
  "hypothesisId": "P9.8-CONTEXT",
  "data": {
    "run_id": "session-7cc6f451c06f47bdb37c71ea50fa170e:2",
    "max_total_bytes": 16384,
    "used_bytes": 0,
    "blocking_stop_reason": "REQUIRED_WORKSPACE_FILE_TOO_LARGE",
    "references": [{"reference": "large.py", "status": "too_large"}]
  }
}
```

### `P9.85-REPLAN` (multiturn turn 1 — content-free)

```json
{
  "hypothesisId": "P9.85-REPLAN",
  "data": {
    "settled_turn": 1,
    "max_planning_turns": 3,
    "read_identities": ["large.py#bytes=0:200"],
    "source_sha256s": ["90619842132fdfa298d81ccb3b7c25ed94b386f689f69ed6cf311b59ec7cefcc"],
    "gateway_request_ids": ["gw-a121e6304f0443ac82ca61d292c2e188"],
    "loop_stop": null
  }
}
```

### `P9.85-REPLAN` (turn-limit terminal stop, post-`6aba8fb`)

```json
{
  "hypothesisId": "P9.85-REPLAN",
  "data": {
    "settled_turn": 1,
    "max_planning_turns": 1,
    "read_identities": [],
    "gateway_request_ids": ["gw-4f454e4d606d4dccabb5c10684719980"],
    "loop_stop": "PLANNING_TURN_LIMIT_EXHAUSTED"
  }
}
```

---

## Redaction notes

| Omitted from this report | Reason |
|--------------------------|--------|
| `OPTIMUS_API_KEY`, gateway URLs | secrets |
| Full `acpx` JSONL transcripts | local operator artifacts; contain plan bodies with `x` filler |
| Plan text in permission `toolCall.content` | truncated to metadata in tables above |
| Specific write payload / post-run file bytes | not retained as durable evidence; workspace may be reset locally after capture |
| Raw model completions | not pasted; ACP shows sanitized progress / corrective text only |
| `acpx` client transcript bodies | external to codebase; operator-reviewed before excerpting |

Runtime debug trace (`debug_trace.py`) applies `redact_for_telemetry` at write time (Task 7).

---

## Supplementary (not Plan 9.85 closure)

An early multiturn attempt (vague task, `alpha`+`x` fixture) produced a live
`PLANNING_MODEL_REFUSED`-shaped user message (~408 bytes, single line) consistent with Task 3's
`REFUSE:` → `sanitize_workspace_text` path. That artifact matches **`P9.85-FU-5` / Plan 9.87**
scope and is **not** claimed here as Plan 9.85 Step 2 evidence.

---

## Definition of Done — claim → evidence

| DoD item (live-relevant) | Evidence |
|---------------------------|----------|
| Multi-turn READ_MORE then final approval | Step 2 transcript + `P9.85-REPLAN` turns 1–2 reads, turn 3 final |
| No intermediate approval | Step 2: permission only after line 9 plan update |
| Distinct gateway IDs + aggregate cost | Step 2 debug trace `gateway_request_ids` (3 unique), `0.002283` USD |
| Post-approval mutation | Step 2: `write_file` after permission id 10000; `H7:approved_done` `mutation_count=1` (not current disk state) |
| Turn-limit typed failure live | Step 3 transcript + `loop_stop` + `planning_corrective_text` linkage |
| Content-free telemetry (ranges, hashes, costs) | `P9.85-REPLAN` excerpts; no `read_identities` on final success turn |
| Telemetry proves stop reason | Turn-limit only (`loop_stop` post-`6aba8fb`); success path `loop_stop: null` by convention |
| Superseded hash fail-closed | Step 4 design section + unit tests |
| Real `acpx`, not project client | `acpx` 0.12.0 JSONL artifacts |
| One-key environment | Prerequisites table |

Items requiring **Plan 9.87** or scripted-only tiers are not marked live-proven here.

---

## Verification gates (Task 8 Step 6)

**Status at report draft:** operator to run before roadmap commit.

```bash
uv run pytest tests/unit/agent tests/unit/loops tests/unit/acp tests/unit/usage -v
uv run pytest tests/integration/agent tests/integration/acp tests/integration/usage -v
uv run pytest --cov=src/optimus --cov-report=term-missing --cov-fail-under=80
uv run ruff check .
git diff --check
```

Record pass/fail in the roadmap PR; do not imply live Redis/Gateway/e2e tiers ran unless explicitly executed.

---

## Shipped limitations (retained)

- Fixed 4 KiB / 12 KiB observation vs current-read partition  
- Raw evidence visible for one turn; earlier evidence carried as untrusted observations only  
- No intelligent compression  
- Typed failure when safe WRITE cannot be grounded in visible raw evidence or policy cannot settle  
- Oversized-required-context trigger only (not model-initiated replan when Plan 9.8 context fits)

---

## Deferred follow-ups → Plan 9.87

- **`P9.85-FU-4`** — model-initiated guarded READ_MORE when Plan 9.8 context fits but WRITE cannot settle single-pass  
- **`P9.85-FU-5`** — live `REFUSE:` with `PLANNING_MODEL_REFUSED` as dedicated Plan 9.87 evidence (supplementary shape observed in early failed run)
