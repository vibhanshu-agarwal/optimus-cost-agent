# Plan 9.98 Real ACPX Session Evidence for Plan 9.96 Task 9 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILLS: Use `superpowers:executing-plans` to execute this
> plan task-by-task and `superpowers:test-driven-development` for every behavior change. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft for reviewer-agent and operator review. **This line is a permanent, unedited
artifact of the pristine hashed content approved in Task 0 Step 1 — it is never updated to say
"Approved" after the fact, mirroring Plan 9.96's own frozen "Draft" header
(`docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md`), whose
own note states plainly: "The embedded Draft header is retained because it is part of the frozen
bytes." Approval status is never determined by this sentence.** The single authoritative source of
truth is: **approval is absent until
`docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md` exists and its
recorded digest matches the PRISTINE bytes committed in Task 0 Step 2's planning commit — never the
live, currently-checked-out file, which legitimately diverges via checkbox ticks per Task 0's own
deferral rule.** (Retrieve those pristine bytes for comparison via `git show
<planning-commit-SHA>:docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md`, not
by reading the working-tree file directly.) Once that record exists and matches the planning-commit
blob, approval is in effect and no header edit is required or expected — checkbox ticks afterward
never affect this.

**Goal:** Give `tools/run_plan996_acpx_security_evidence.py` the ability to drive one real,
independently-authored-`acpx` ordinary session and one real elevated session against the actual
Optimus agent, and prove Plan 9.96 Task 9 Step 2's required properties (mode, tools, cost band,
terminal state/`end_turn`, zero pre-approval mutation, exact child-key manifest, ordinary no-tags
behavior, elevated allowlisted provenance/tags) from that real evidence — without editing Plan
9.96's frozen plan file, security contract, approval records, or either frozen Plan 9.87/9.88
helper.

**This is a separate, narrow plan — not an amendment to Plan 9.96.** Plan 9.96's Global Constraint
#3 ("Exactly two follow-ups: this plan implements only `P9.85-FU-7` and `P9.9-FU-1`") and Task 9's
own Files list forbid modifying `tools/run_plan996_acpx_security_evidence.py` inside Plan 9.96
itself. This plan owns that file change under its own review and its own commits.

**Hard dependency, stated explicitly per the operator's instruction: Plan 9.96 Task 9 Steps 2, 3,
and 5 cannot execute, and Task 9 cannot close, until this plan's real-session capture capability is
implemented, reviewed, and evidenced.** Plan 9.96's Task 9 Step 2 literal commands
(`tools/run_plan996_acpx_security_evidence.py capture ... --mode ordinary/elevated`) assume this
capability exists; as committed at the foundation SHA below, it does not — the tool always spawns
`acpx --version` regardless of `--mode` (verified: `tools/run_plan996_acpx_security_evidence.py:758`
hardcodes `command=[acpx, "--version"]`; `spawn_authorized_capture` at :206 hardcodes
`stdin=subprocess.DEVNULL`; no CLI surface passes a different command). Task 9 Step 1 (the real
OS-store ceremony) does not depend on this plan and may proceed independently.

**Foundation:** Plan 9.96 Tasks 0-8 as committed on branch `agent/kiro/plan-9-96` at HEAD `d0c4670`
("Sanitize ACP evidence before persistence") and the reviewer's independent verification recorded in
`docs/superpowers/reviews/plan-9-96-review-checkpoints.md`. That proven code and its committed test
suite — not a prior plan document — are this lane's dependency contract, mirroring how Plan 9.96
itself anchored to the Plan 9.9 implementation commit rather than a plan file.

**Architecture:** Extend the already-reviewed Task 8 capture tool with a second capture mode that
constructs `[acpx, "--format", "json", "--cwd", <workspace>, "--agent", <agent invocation>, "exec",
<task>]` as an argument list (never a shell string), reusing every already-approved piece of the
Task 8 pipeline unchanged: `authorize_capture`/`append_authorized_audit`/`spawn_authorized_capture`
for the gated launch of the `acpx` process itself, `_stream_sanitized`/`StreamingTextSanitizer` for
persistence, `_joined_scan` for promotion-gating, and the HMAC-signed evidence manifest for the
claim-to-evidence trail. The genuinely new work is (a) resolving what "agent invocation" means for
`acpx --agent` under Plan 9.96's committed gate — the `optimus-agent` console script, not the
retired Plan 9.87 wrapper scripts — and (b) parsing `acpx`'s own JSON output for the Step 2
properties instead of a bare version string. See Task 1 for the one substantive open design
question (diagnostic-grant consumption topology) this plan must resolve empirically before writing
any capture-path code.

**Tech Stack:** Python 3.14+, `argparse`, `subprocess` (`shell=False` throughout), `json`, `hashlib`,
`hmac`, existing `optimus_security.sanitization`/`optimus_security.launch_manifest`, `pytest`,
`pytest-asyncio`, `pytest-cov`, Ruff, `uv`, real Redis, real Optimus Gateway, real Windows
Credential Manager, and independent `acpx` 0.12.0+.

**Estimated implementation size:** 5-8 focused review rounds. Narrower than a full Plan 9.96 task in
surface area (one tool + one E2E node), but the empirical Task 1 investigation (grant topology, real
acpx output shape, permission mechanism, final-state source), the process-tree/timeout fix, and the
snapshot/freshness/mutation-proof evidence design each carry real risk; this is not a trivial lane.

## Source Anchors and Conflict Check

- Plan 9.96 committed code at HEAD `d0c4670`, specifically
  `tools/run_plan996_acpx_security_evidence.py` (the file this plan extends) and
  `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` (the sink manifest this
  plan must extend for any new persistence sink, same discipline as Plan 9.96 Task 7/8).
- Plan 9.96's own plan file
  `docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md` and its
  Task 9 text (Step 2's literal capture commands, the Definition of Done items this plan's evidence
  must satisfy). This plan does not edit that file. Plan 9.96 Task 9 still performs its own
  mechanical checkbox sweep and closure commit, using the capability this plan adds.
- Reviewer checkpoint log `docs/superpowers/reviews/plan-9-96-review-checkpoints.md`, top two
  2026-07-18 entries: the P9.96-FU-1..7 scope-conflict ruling (this plan must not touch any of those
  six files either — see Global Constraint 2) and the Task 9 Step 2 structural-blocker finding this
  plan exists to resolve.
- Frozen precedent for a real, non-interactive `acpx` session invocation:
  `tools/run_plan987_acpx_live_evidence.py:1216-1229` — `[acpx, "--format", "json", "--cwd",
  workspace, "--agent", _agent_invocation(), "exec", task]`, run via plain `subprocess.run` with no
  stdin PIPE-feeding. `exec <task>` takes the prompt as a CLI argument, not stdin — this directly
  supersedes the earlier (incorrect) checkpoint-log assumption that real sessions require
  stdin-driven JSON-RPC. This file is frozen and must not be modified or imported from; it is cited
  here as read-only precedent only.
- Reference-only precedent for session-result parsing (NOT the transport this plan uses — see
  Global Constraint 8): `src/optimus/acp/operator_verify.py` (`OperatorLiveSessionResult`,
  `run_operator_live_session`) and `tests/e2e/acp/test_spawned_agent_live.py`. That tool drives a
  real gated agent session and extracts exactly the shape of properties Task 9 Step 2 needs
  (`stop_reason`, `total_cost_usd`, `tool_trajectory`, `files_changed`), which is why it is useful
  reading — but it is a project-authored NDJSON/JSON-RPC client (`NdjsonSubprocessSession`), not
  independently-authored `acpx`, so it does not itself qualify as Plan 9.96 Task 9 evidence and must
  not be repurposed as this plan's transport. Its own docstring already distinguishes "process tier"
  from "acpx protocol tier" (`test_spawned_agent_live.py:1`). Read-only; not modified by this plan.
- `pyproject.toml:17` — `optimus-agent = "optimus.acp.__main__:main"` is the real console-script
  entry point `acpx --agent` must invoke; the Plan 9.87-era wrapper scripts `run-optimus-agent.cmd`
  / `run-optimus-agent.sh` no longer exist in the repository (confirmed absent) and must not be
  referenced.
- `src/optimus/acp/launch_policy.py:77` — `DEFAULT_LIVE_MAX_COST_USD = Decimal("0.25")`, the
  registry cost ceiling for the "cost band" assertion.
- `src/optimus/acp/spec.py` (multiple sites, e.g. lines 580/584/586) — `"end_turn"` is the real ACP
  `stopReason` value for a completed turn; `src/optimus/acp/operator_verify.py:357-359` already
  contains a verified pattern for asserting it from a captured `session/prompt` response.
- `src/optimus/acp/debug_trace.py:19,24,170` — elevated-diagnostics evidence lives at
  `.optimus/debug-acp.ndjson` under the workspace root and is tagged via
  `optimus_security.sanitization.session_correlation_tag`; this is the locator for the "elevated
  allowlisted provenance/tags" assertion.
- `src/optimus/acp/launch_audit.py` / the settled ruling that `runtime_root` = `workspace/.optimus` —
  the workspace's own `launch-audit.ndjson` carries `child_propagation_decisions.agent_child`
  (child-key names, never values) for whichever process's gate wrote it; Task 1 must determine which
  entry (the outer evidence tool's, or the inner `optimus-agent`'s) is authoritative for the "exact
  child-key manifest" assertion.

No other conflict is presently known. If implementation finds one among this plan, Plan 9.96's
committed code, or live `acpx`/agent behavior, stop and request a reviewed amendment to **this**
plan; do not reinterpret either plan's contract in code.

## Global Constraints

1. **Frozen paths, byte-unchanged, `git diff --quiet` gated at every commit:**
   `tools/run_plan987_acpx_live_evidence.py`, `tools/run_plan988_fu4b_live_evidence.py`,
   `src/optimus/acp/operator_verify.py`, `tests/e2e/acp/test_spawned_agent_live.py`,
   `src/optimus/acp/e2e_transcript.py`'s existing `PLAN_9_6_*` constants and writer behavior, and
   Plan 9.96's own plan file, security-contract spec, and both approval records. This plan reads all
   of the above for precedent only.
2. **No FU-1/2/3/4/5/7 source changes.** Per the 2026-07-18 checkpoint-log ruling, those follow-ups
   are disclosed-and-backlogged by Plan 9.96 Task 9, not fixed. This plan must not touch
   `src/optimus/acp/__main__.py`, `src/optimus/agent/defaults.py`,
   `tools/verify_plan996_logging_surfaces.py`, `src/optimus/acp/trusted_paths.py`,
   `src/optimus/acp/subprocess_env.py`, `src/optimus/acp/launch_policy.py` (read-only citation of the
   existing `DEFAULT_LIVE_MAX_COST_USD` constant is fine; no edits), `src/optimus/acp/errors.py`, or
   `src/optimus/acp/bootstrap.py` for any reason. If evidence work seems to require touching one of
   these, stop and report — do not fold an FU fix into this plan's diff.
3. **Single sanctioned diagnostic-grant consumption per real elevated launch.** The grant is
   consumed exactly once, by whichever process's gate decision the "elevated allowlisted
   provenance/tags" claim actually depends on. Task 1 determines and empirically proves which one;
   no code may consume the grant a second time defensively "just in case."
4. **RED before GREEN, specifically at the capability boundary.** A test proving the *currently
   committed* `acpx --version` capture path cannot satisfy Step 2's session assertions must exist,
   run, and be shown failing for the right reason before any `exec`-mode implementation is written
   (Task 2).
5. **`shell=False` everywhere; no raw interim files; extend, don't bypass, the existing sanitize /
   joined-scan / HMAC-manifest pipeline.** Every new artifact this plan's capture mode writes goes
   through `StreamingTextSanitizer` before touching disk, exactly like the committed `--version`
   path. No new artifact type is exempt from the joined promotion scan.
6. **No new ACP protocol implementation.** This plan's tool only ever shells out to installed,
   independently-authored `acpx`; it must never hand-construct `jsonrpc`/`session/new`/
   `session/prompt` framing itself (that is exactly the "process tier" `operator_verify.py`
   pattern this plan is not allowed to reuse as its transport). A source-level test enforces this,
   mirroring Plan 9.88's `test_helper_source_does_not_implement_acp_protocol`.
7. **Approval-gated commits; every `uv` command in this plan's own verification steps must be run
   from a terminal that actually has `uv` on PATH.** No checkbox may be marked complete from a
   substitute/manual hash or test run computed outside the prescribed command, even if the result is
   independently reproduced by other means. Record the exact terminal/session used.
8. **Plan 9.96 Task 9 dependency is a hard fact, not a suggestion.** This plan's own evidence report
   (Task 7) must state explicitly that Plan 9.96 Task 9 Steps 2/3/5 are blocked on this plan's
   commit SHA landing first.
9. **Quality gates before any commit.** For any **code-touching** commit (the Task 6 implementation
   commit): the task's named tests, `uv run ruff check .`, `uv run python
   tools/verify_plan996_logging_surfaces.py --manifest
   docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json`, and `git diff --check`.
   For **docs-only** commits (the Task 0 planning commit, the Task 8 evidence/docs commit, and the
   Task 8 plan-closure commit — none of which change Python or the logging-surface inventory): the
   full-frozen-path `git diff --quiet HEAD` gate plus `git diff --cached --check` only; the test/Ruff/
   surface-verifier gates are vacuous for a Markdown-only change and are deliberately not required
   there. Every commit runs the frozen-path HEAD gate regardless.

---

## File and Responsibility Map

- Create: `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md` — this
  plan's own digest-pinned approval record (Task 0 Step 1), before any other step.
- Modify: `tools/run_plan996_acpx_security_evidence.py` — add the `exec`-mode command construction,
  agent-invocation resolution, session-result parsing, the grammar-validated `--evidence-run-nonce`
  argument, the distinct real-session deadline + drive-session-only process-tree termination, the
  per-run immutable audit/debug (and, if needed, final-state) snapshots with fail-closed single-writer
  suffix validation, the nonzero-exit/timeout promotion block, and the new content-free manifest
  fields.
- Modify: `tests/unit/tools/test_run_plan996_acpx_security_evidence.py` — RED capability-gap test,
  new-mode unit tests, nonce-grammar rejection tests, subprocess-isolated non-terminating-child
  tree-kill timeout test, nonzero-exit promotion-block test, foreign-writer suffix-validation test,
  AST + behavioral source-level no-protocol-reimplementation tests, manifest field tamper tests.
- Modify: `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` — classify any
  new persistence/export sink this plan's code introduces (same discipline as Plan 9.96 Task 7/8).
- Create: `tests/e2e/acp/test_plan996_authorized_launch.py` — the real ordinary/elevated E2E node
  Plan 9.96 Task 9 Step 2 requires, including the pre-authorization mutation proof.
- Create: `reports/plan-9-98-real-acpx-session-evidence.md` — this plan's own claim-to-evidence
  report, citing the Task 6 implementation commit SHA and the explicit Plan 9.96 Task 9 dependency
  statement. **Committed in the Task 8 Step 3 evidence/docs commit, separately from the
  implementation, never in the same commit as the SHA it cites.**
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` — add a Plan 9.98 section; note the
  Task 9 dependency in the existing Plan 9.96 section.
- Modify: `README.md` — one-sentence planning-status paragraph, mirroring the pattern used for every
  other plan.
- Modify (checkbox-only, at closure): `docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md`
  itself — committed pristine in the Task 0 planning commit, then re-committed with its accumulated
  `- [ ]`→`- [x]` ticks in the Task 8 Step 4 plan-closure commit, mechanically proven to contain no
  substantive-text change.
- Note the four commits this plan produces: (1) Task 0 planning (plan + approval record), (2) Task 6
  implementation, (3) Task 8 Step 3 evidence/docs (report + roadmap + README, no plan file), (4) Task
  8 Step 4 plan-closure (plan-file checkbox diff only).
- Do not modify: anything listed under Global Constraint 1, or any FU-1/2/3/4/5/7 file listed under
  Global Constraint 2.

---

### Task 0: Foundation, Approval, and Conflict-Check Gate

**Files:** Create `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md`
(the approval record). Commit this file and the plan file itself as their own docs-only "planning
commit" before Task 1 begins — see Step 2.

- [ ] **Step 1: Pin this plan's own approval identity ONCE, over the pristine (unchecked) plan — checkbox ticks afterward do not invalidate it**

This plan itself needs the same digest-pinned approval discipline Plan 9.96 required of its own plan
file (Plan 9.96 Task 0 Global Constraint 1). Two things the first draft got wrong, both fixed here:

1. **It never established the approval it referenced.** Task 7 cited "this plan's approval digest"
   without Task 0 ever pinning one.
2. **An exact-byte digest re-checked at every later step is incompatible with this plan's own
   checkbox protocol.** Every checkbox this plan ticks changes the file's bytes — a live re-check of
   "does the on-disk file's digest still match Step 1's recorded digest" would fail the moment the
   very first checkbox (including this one) is ticked. The fix is not to re-check the live digest at
   every step; it's to compute the digest **exactly once**, at the moment of approval, over the plan
   in its pristine `- [ ]` state, and treat checkbox-only changes afterward as working-tree tracking
   that does not require re-approval — the same freeze-except-checkbox convention Plan 9.96 itself
   uses (its own plan file's Status/DoD checkboxes tick during implementation without invalidating
   its Task 0-pinned digest, because that digest was taken once, before implementation, and a
   substantive *content* change — not a checkbox — is what would require re-approval).

Once the reviewer-agent and operator both approve this plan's content (while it is still entirely
`- [ ]`), compute its SHA-256 immediately, in the same sitting, before any checkbox is touched:

```bash
uv run python -c "from pathlib import Path; import hashlib; p=Path('docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md'); print(hashlib.sha256(p.read_bytes()).hexdigest().upper())"
```

Record that digest, the approving parties, and the date in
`docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md` (mirroring
`docs/superpowers/reviews/2026-07-15-plan-9-96-implementation-plan-approval.md`'s shape), and state
explicitly in that record: "this digest is a one-time approval snapshot of the plan's content;
subsequent checkbox ticks in the working tree do not invalidate it; any change to this plan's
substantive text requires a new approval and a new recorded digest."

**Do NOT tick this Step 1's own checkbox, or Step 2's, yet — doing so now would make the committed
snapshot (Step 2) diverge from the pristine bytes just hashed.** The approval record's digest
describes the plan file with EVERY checkbox still `- [ ]`, including this one. If Step 1's checkbox is
ticked immediately (the plan's normal per-step convention), the file's bytes change before Step 2's
commit — so the committed "planning commit" would already have one checkbox ticked, and would no
longer byte-match what the approval record's digest actually covers. Leave both this checkbox and
Step 2's unticked until AFTER Step 2's commit lands (see Step 2's closing note); they are ticked
retroactively then, as an ordinary working-tree change like any other step, captured later in the
Task 8 Step 4 closure commit along with everything else. Every step from Task 1 onward ticks normally
as usual — this special handling applies ONLY to these first two steps, because they are the ones
that establish and then commit the pristine baseline.

- [ ] **Step 2: Commit the approved plan and its approval record — the contract must exist in repository history before implementation starts**

The first draft never staged the plan file or its approval record in any commit — both would have
remained untracked forever while implementation proceeded, meaning the repository history would
never contain the contract that authorized the work (the same gap Plan 9.96 itself avoided via its
own docs-only planning-branch-then-merge step). Fix it with one small, separate, operator-approved
commit, before Task 1 begins. **The plan file committed here must be byte-identical to Step 1's
approved/hashed pristine state — zero checkboxes ticked anywhere in the file, including Steps 1 and 2
themselves** (see the note at the end of Step 1). **Both files are untracked at this point, so a
plain `git diff -- <paths>` shows nothing** — review them read-only first, then show the staged diff
after staging:

```bash
# Frozen-path gate applies to EVERY commit, including this planning commit (Global Constraint 1),
# compared against HEAD so a previously-staged frozen-path change cannot pass silently:
git diff --quiet HEAD -- tools/run_plan987_acpx_live_evidence.py tools/run_plan988_fu4b_live_evidence.py src/optimus/acp/operator_verify.py tests/e2e/acp/test_spawned_agent_live.py src/optimus/acp/e2e_transcript.py docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md docs/superpowers/reviews/2026-07-15-plan-9-96-security-contract-approval.md docs/superpowers/reviews/2026-07-15-plan-9-96-implementation-plan-approval.md
git status --porcelain --untracked-files=all
# Untracked files won't show in `git diff` — review their content directly instead:
cat docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md
```

After operator approval only — stage, then show the STAGED diff (the reviewable one for
now-tracked-but-uncommitted files) and the full pre-commit gates:

```bash
git add docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md
git diff --cached -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md
git diff --cached --check
git commit -m "Approve Plan 9.98 real acpx session evidence planning"
git rev-parse HEAD
```

Record this commit's SHA. **Only now, after this commit exists, tick Step 1's and this Step 2's own
checkboxes** in the working tree (the commit itself stayed pristine, matching the approval digest
exactly — see Step 1's closing note). Later checkbox ticks — Steps 1 and 2 now, and every subsequent
step's as it completes — are working-tree changes; they are committed once at closure in the
dedicated Task 8 Step 4 plan-closure commit, which re-adds this plan file with a checkbox-only diff
and a mechanical proof that no substantive text changed — see Task 8 Step 4. They are not
re-committed here, and NOT in the Task 8 Step 3 evidence/docs commit (which deliberately excludes the
plan file to avoid the self-reference).

- [ ] **Step 3: Verify the exact foundation state before any further mutation**

```bash
git -C . rev-parse HEAD
git -C . branch --show-current
git -C . diff --quiet -- tools/run_plan987_acpx_live_evidence.py tools/run_plan988_fu4b_live_evidence.py src/optimus/acp/operator_verify.py tests/e2e/acp/test_spawned_agent_live.py
git -C . status --porcelain --untracked-files=all
ls tests/e2e/acp/test_plan996_authorized_launch.py 2>&1 || true
uv run python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
```

Expected: HEAD is Step 2's planning-commit SHA (built on `d0c4670` on `agent/kiro/plan-9-96`, or
whatever later Plan-9.96-Task-9-Step-1-only SHA the reviewer confirms touched no source files this
plan depends on); the frozen-path diff-quiet checks are silent; the E2E test file does not yet exist;
the verifier is green. **`git status` is expected to show, at most, disclosed tool-config noise
(`.claude/`, `.zed/`, `.kiro/`, `.idea/`, `.air/`, `uv.lock`) — `.claude/` is NOT covered by this
repository's own `.gitignore` (confirmed: it's excluded only via a machine-local global gitignore on
one operator machine, so a different environment/session will see it as untracked) — it is not
required to be perfectly empty, only free of anything this plan didn't itself put there.** If HEAD
has moved further because Plan 9.96 Task 9 Step 1 (the OS-store ceremony) has already landed real
evidence, that is expected and fine — Step 1 does not touch any file this plan also touches;
re-verify the frozen-path diffs against the new HEAD before continuing.

- [ ] **Step 4: Confirm no FU-1/2/3/4/5/7 file has drifted since the checkpoint-log ruling**

```bash
git -C . diff --stat HEAD -- src/optimus/acp/__main__.py src/optimus/agent/defaults.py src/optimus/acp/trusted_paths.py src/optimus/acp/subprocess_env.py src/optimus/acp/launch_policy.py src/optimus/acp/errors.py src/optimus/acp/bootstrap.py tools/verify_plan996_logging_surfaces.py
```

Expected: no output (nothing staged/modified). This plan's diff must never touch these files.

---

### Task 1: Resolve and Pin the Composite Launch Topology (required before any capture-path code)

This is the one substantive open design question. Do not skip or assume; the wrong answer here
silently mislabels an ordinary session as elevated evidence, exactly the "wrong-mode evidence"
failure class Plan 9.96 has repeatedly guarded against elsewhere.

**Files:** none yet (investigation and a short written ruling; code changes start at Task 2/3).

- [ ] **Step 1: Establish the ruling in writing, grounded in the cited source**

`optimus-agent` (`pyproject.toml:17` → `optimus.acp.__main__:main`) performs its own complete
`resolve_launch_candidate`/`authorize_launch`/grant-consumption gate whenever it is spawned as a
fresh process (confirmed: `src/optimus/acp/operator_verify.py` spawns `python -m optimus.acp`
directly with no outer gate call of its own, and its module docstring states the spawned child "now
runs through the gated `__main__.py` launch gate" as the *only* gate for that launch). Elevated
diagnostics (session-local correlation tags, allowlisted metadata) are emitted by *that* process's
own debug trace (`src/optimus/acp/debug_trace.py:170`, `session_correlation_tag`), not by any outer
wrapper. Therefore: for this plan's real-session capture mode, the diagnostic grant must be consumed
by `optimus-agent`'s own internal gate (i.e., passed through unconsumed to the `--agent` invocation
string), not by the evidence tool's outer `authorize_capture()`. If the outer tool also calls
`consume_diagnostic_grant` on the same grant id (as the committed `--version`-mode `authorize_capture`
does today), the grant is already gone by the time `optimus-agent` tries to consume it, `optimus-agent`
silently downgrades to ordinary per its documented fail-open-to-safe behavior, and the "elevated"
claim becomes false while every test still passes.

Write this ruling down verbatim in the plan execution notes before Step 2, so it is falsifiable
rather than assumed.

- [ ] **Step 2: Empirically prove the failure mode and the fix — using the store's own API as the oracle, never `optimus-agent`'s exit behavior**

A diagnostic grant is bound to a specific `launch_session_id` (`launch_approvals.py:626-627`:
`consume_diagnostic_grant` raises `GRANT_SESSION_MISMATCH`, not `GRANT_NOT_FOUND`, when the supplied
session ID doesn't match the grant's own). `optimus-agent`'s own CLI generates a **fresh random**
session ID whenever `--launch-session-id` is omitted (`__main__.py:191`), so every command in this
proof must carry the **same** fixed session ID or a session mismatch will mask the result regardless
of consumption order.

**More fundamentally: `optimus-agent` can never be used as the oracle for "did it report
`GRANT_NOT_FOUND`" at all.** Confirmed by reading `__main__.py:209-226`
(`_authorize_or_exit`'s grant-consumption block): it wraps `consume_diagnostic_grant` in
`except ApprovalError: diagnostic_grant = None` and swallows **every** `ApprovalError` code
identically — the comment states this is deliberate ("silent downgrade, no stderr noise... from the
operator's perspective, just 'elevated diagnostics didn't turn on'"). There is no external signal —
no distinct exit code, no stderr message — that would let an outside observer tell `GRANT_NOT_FOUND`
apart from "no grant id was ever passed." The proof must therefore use two *independently observable*
oracles instead of trying to read `optimus-agent`'s own behavior as a report:

1. **The keyring store's own `consume_diagnostic_grant` call, invoked directly in the test/probe
   harness** (not through the `optimus-agent` CLI) — this genuinely raises/returns observably, since
   it's your own test code calling the store API, not something routed through `__main__.py`'s
   swallow layer.
2. **The presence or absence of an allowlisted `session_correlation_tag` entry in
   `.optimus/debug-acp.ndjson`** as the *indirect* signal that `optimus-agent` actually turned on
   elevated diagnostics for that launch (per Step 3 below, this requires `--debug-trace`).

In a scratch workspace with a durable approval, construct one `DiagnosticGrant` directly (reuse the
existing test pattern `_sample_diagnostic_grant` at `tests/unit/acp/test_launch_approvals.py:37-52`,
which signs it correctly via `compute_grant_hmac`) with a **fixed, known** `launch_session_id`, and
write it via `store.write_diagnostic_grant(grant)`. Then, using that exact same session ID and grant
ID throughout:

**Every direct `optimus-agent` invocation in this probe must run in a terminating mode with isolated,
bounded stdin — never bare, and never sharing the probe's own TTY.** Confirmed by reading
`__main__.py:368-383,407-421`: without `--check-config`, `main()` reaches
`asyncio.run(server.serve_ndjson(StdioNdjsonLineReader(sys.stdin.buffer), ...))`, which reads from
the process's own stdin in a loop and never returns on its own — an inherited interactive TTY (or any
stdin the probe doesn't explicitly bound) blocks this invocation forever. `--check-config
--no-auto-start` returns at line 383 (`return 0`), **after** the grant-consumption block
(`__main__.py:209-226`) and after `_apply_debug_trace_args`/`log_authorized_launch_comparison` run,
but **before** `serve_ndjson` is ever reached, and skips real Redis/Gateway auto-start — the correct
terminating route for this narrow probe. Invoke it as a bounded subprocess with `stdin=subprocess.DEVNULL`
and a hard timeout (e.g. `subprocess.run([..., "--check-config", "--no-auto-start", ...],
stdin=subprocess.DEVNULL, timeout=30)`), and kill/clean up on timeout rather than letting the probe
itself hang.

(a) **Outer-consumes-first case:** call `store.consume_diagnostic_grant(grant_id, session_id)`
*directly* in the probe (simulating the outer evidence tool having already consumed it) — confirm
this direct call succeeds once. Then call `store.consume_diagnostic_grant(grant_id, session_id)`
*again* — confirm it now raises `ApprovalError(code="GRANT_NOT_FOUND")` (this is the observable,
non-swallowed proof that the grant is genuinely gone). Then run `optimus-agent --workspace-root <ws>
--launch-session-id <same id> --diagnostic-grant-id <same grant id> --debug-trace --check-config
--no-auto-start` (bounded, `stdin=DEVNULL`, as above) — confirm exit 0 (ordinary, silently
downgraded) and that `.optimus/debug-acp.ndjson` contains **no** `session_correlation_tag` entry,
proving the downgrade happened even though nothing printed it.

(b) **Inner-consumes case (the fix):** with a freshly written, unconsumed grant (same fixed session
ID), run the identical bounded `optimus-agent --check-config --no-auto-start` invocation *first* —
confirm `.optimus/debug-acp.ndjson` **does** contain an allowlisted `session_correlation_tag` entry
(proving elevated diagnostics turned on, which is only possible if the grant was actually consumed).
Then call `store.consume_diagnostic_grant(grant_id, session_id)` directly in the probe — confirm it
now raises `ApprovalError(code="GRANT_NOT_FOUND")`, proving the grant was consumed exactly once by
`optimus-agent` itself and not left over for a second, redundant consumption.

Record both runs' observed outcomes (the two direct-store results, the tag presence/absence, the
`optimus-agent` exit codes) as this task's evidence; do not proceed on code-reading alone.

**Cleanup — grounded in what the store actually exposes, not an assumed "delete" method, and not an
assumed passive expiry either.** Checked `launch_approvals.py`: `KeyringApprovalStore` has no
standalone "delete this grant" method, and `revoke_workspace(workspace_digest)` only deletes the
`durable:{workspace_digest}` entry — it never touches a `grant:{grant_id}` entry, so it does NOT
clean up diagnostic grants. The only code path that removes a grant's keyring entry is
`consume_diagnostic_grant` itself, which deletes on every successful consumption
(`launch_approvals.py:634`) and on the expired path (`:630`) — but NOT on
`GRANT_NOT_FOUND`/`GRANT_CORRUPT`/`GRANT_INTEGRITY_FAILURE`/`GRANT_SESSION_MISMATCH`, which raise
before reaching any delete call. Consequence: **both scenario (a) and (b) above are self-cleaning by
construction** — each ends with the grant genuinely consumed (deleted) as a direct side effect of the
proof's own oracle calls (the first successful `consume_diagnostic_grant` in each scenario), so no
separate cleanup action is needed on the happy path.

**The residue risk is a scenario that errors out (a failed assertion) BEFORE its first successful
consume — and "the TTL will retire it" is FALSE for this case, not just unavailable.**
`DIAGNOSTIC_TTL_SECONDS` (`launch_approvals.py:34`, 900s) governs only whether a *future*
`consume_diagnostic_grant` call treats the entry as expired (raising `GRANT_EXPIRED` and deleting it
as a side effect of *that* call) — there is no background process, no OS-native per-entry keyring
TTL, nothing that passively removes an untouched entry after 900 seconds elapse. If nothing ever
calls `consume_diagnostic_grant` against a leftover entry again, it sits in the operator's real
Windows Credential Manager indefinitely, expired-but-never-deleted.

**Therefore: wrap every scenario in this probe in `try/finally`, and in the `finally` block,
unconditionally attempt the raw fallback delete AND VERIFY THE OUTCOME — do not just swallow whatever
exception `delete_password` happens to raise.** A bare `try: delete_password(...) except: pass` is
unsafe: `delete_password` legitimately raises when the entry is already gone (the expected happy-path
case, since a successful `consume_diagnostic_grant` already deleted it) — but it could ALSO raise for
a genuine keyring failure (a real OS/Credential-Manager error), and different keyring backends do not
reliably distinguish these two cases by exception type. Catching broadly and moving on would let a
real deletion failure masquerade as "already clean," leaving residue while the probe reports success.
The correct check is on the **outcome**, not the exception. **`service_name` is not a bare local — pin
it to the real value.** `KeyringApprovalStore._service_name` is a dataclass field defaulting to the
module-level `_KEYRING_SERVICE = "optimus-cost-agent-approvals"` constant
(`launch_approvals.py:36,422`) — never a value the probe invents. The probe already constructs a
`store = KeyringApprovalStore(...)` in this same section to call
`write_diagnostic_grant`/`consume_diagnostic_grant`; reuse that same instance's own attribute rather
than importing the constant separately: attempt
`keyring_backend.delete_password(store._service_name, f"grant:{grant_id}")` inside its own try/except
(any exception here is expected and ignored — it usually just means "already gone"), then, regardless
of whether that raised, call `keyring_backend.get_password(store._service_name, f"grant:{grant_id}")`
and **assert it returns `None`**. If it does not, the entry is genuinely still present — surface that
as a real test failure (do not swallow it), because it means a real deletion failure happened and left
residue. This is a disclosed, non-store-API workaround (there is no delete method on the store
itself), required unconditionally, never offered as an alternative to a passive TTL mechanism that
does not exist.

- [ ] **Step 3: Pin the exact agent-invocation construction, including debug tracing**

Determine how `acpx --agent` expects its value (a single shell-parsed string vs. an argv list — check
`acpx --help`/`acpx exec --help` directly, do not assume from the frozen Plan 9.87 helper's string
form). Construct it as `optimus-agent --workspace-root <workspace> --launch-session-id <id>
--debug-trace [--diagnostic-grant-id <id>]` (omit `--launch-approval-id` for the durable-approval
path, matching Plan 9.96's own settled ruling that `authorize_launch` takes the durable path when
`approval_id is None`). **`--debug-trace` is required, not optional:** it is the only path that
creates `.optimus/debug-acp.ndjson` at all (`__main__.py:99-111`, `_apply_debug_trace_args` returns
early when `args.debug_trace` is falsy) — without it, elevated correlation tags can never be observed
regardless of grant handling. Note also (`debug_trace.py:160-164`,
`log_authorized_launch_comparison`): tags require **both** `--debug-trace` enabled **and** a present
diagnostic grant — `context.enabled` alone with no grant emits nothing. This means the Task 5
"ordinary no-tags" proof must run ordinary **with `--debug-trace` also enabled** (not simply omit the
flag), so the negative control proves the absence of a grant suppresses tags, not the absence of the
flag. Whatever form `acpx` requires, the *outer* `Popen` invocation of `acpx` itself remains
`shell=False` with an explicit argument list; only investigate whether the `--agent` value itself
needs internal quoting for `acpx`'s own parser.

- [ ] **Step 4: Pin the "exact child-key manifest" evidence source — use the outer (evidence tool's own) audit entry**

The evidence tool's own audit entry, not `optimus-agent`'s inner one, is authoritative here — the two
differ because of an ordering asymmetry inside already-committed `__main__.py`, not because the inner
entry is somehow more direct. Confirmed by reading `__main__.py:281-366`: `_append_audit_or_exit`
(the inner audit) runs at line 313, using `candidate.agent_environ` **before** `apply_local_defaults`
runs at line 362; the comment at lines 354-361 states plainly that `candidate.agent_environ` "does
not fill in loopback URL defaults or fold in a keyring/.env.gateway-resolved shared secret the
operator never set explicitly as `OPTIMUS_API_KEY`." In Task 9's real configuration (credentials
sourced from the Windows Credential Manager keyring, no `.env`), the inner audit's `agent_child` tuple
therefore **under-reports** — it is missing `OPTIMUS_API_KEY` even though the real agent process ends
up with it. The evidence tool's own `authorize_capture()` (Task 8, already committed) calls
`apply_local_defaults` *before* constructing `CaptureLaunch`, so its own audit entry
(`append_authorized_audit`, built from `capture.agent_environ`) already reflects the post-default set
and is the correct source. Use the **exact 5 names already empirically observed** in the real gated
smoke (checkpoint log, "REAL GATED ACPX SMOKE PASSED" entry): `OPTIMUS_AGENT_MODEL`, `OPTIMUS_API_KEY`,
`OPTIMUS_GATEWAY_URL`, `OPTIMUS_PRODUCTION_MODE`, `OPTIMUS_REDIS_URL` — not the ambiguous "one-key set"
language used in an earlier draft of this plan. Confirm by inspecting both entries from a real run and
showing the inner entry is missing `OPTIMUS_API_KEY` while the outer entry has it, exactly as this
reasoning predicts. **Do not fix the inner-audit ordering itself — `__main__.py` is out of scope for
this plan (Global Constraint 2); note it in Task 7's evidence report as a new backlog observation for
a future plan, and work around it here by using the outer entry.**

- [ ] **Step 5: Pin the real `acpx --format json` output shape before specifying any parser — inspect ephemerally, retain only content-free schema notes**

Do not assume the output shape. Run `acpx --format json --cwd <ws> --agent <invocation> exec <task>`
for real, through the gate, with a genuinely approved workspace, and inspect its actual raw JSON
output. **This is a real session with real credentials and a real prompt — the raw output may
contain content this plan's own security posture forbids persisting.** Inspect it ephemerally only
(in memory, or a scratch location that is deleted immediately after inspection and never staged or
committed) — do not write or retain the raw output as a tracked or permanent artifact; that would
itself be exactly the "raw interim file" Global Constraint 5 forbids. Record only content-free
findings in the plan execution notes: which record/field names exist (e.g. does it echo the
underlying ACP JSON-RPC frames verbatim, in which case literal method names like `"session/prompt"`
and fields like `result.stopReason` are real, observed strings, or does `acpx` emit its own
summarized/flattened schema with different field names?) and where the terminal stop reason, the
tool-call events, and the cost-bearing usage record live structurally — never the actual field
*values* from this real run (real prompt text, real cost figures, real file contents). This pinned,
observed shape — not an assumption — is what Task 4's parser is written against and what Task 5's
source-level test must be consistent with (see the correction in Task 5 Step 1).

**Additionally, and separately: determine whether a `final_agent_state` signal — distinct from the
ACP-level `stop_reason` — actually exists as a real, independently-evidenced source.** Plan 9.96 Task
9 Step 2's text lists "final state" and terminal `end_turn` as two *separate* required claims, but
nothing in this plan (or in `acpx`'s real output, until checked) has actually proven a second, named
domain-state signal exists. Look in three places: `acpx`'s own JSON output, the workspace's real
agent state store (Redis `RedisAgentStateStore` — the agent's own ledger/completion status, which is
where a genuine domain "final state" distinct from the protocol stop reason would live if anywhere),
and the sanitized transcript. Do not fabricate a field name for something unverified.

**If a real, named signal is found, pin its exact source and expected successful value here for Task
4 to consume. If no such distinct signal exists, STOP AND REPORT — and understand that the
resolution is NOT within this plan's authority to decide.** Plan 9.96's frozen Task 9 Step 2 lists
"final state" as a distinct required claim; this separate plan cannot unilaterally decide that
`stop_reason` also satisfies that separately-enumerated claim, because doing so would reinterpret the
frozen parent contract in exactly the way this plan's own Source-Anchors conflict rule ("do not
reinterpret either plan's contract in code") forbids. If Task 1 finds no distinct final-state source,
the only valid resolutions are (a) a reviewed amendment to Plan 9.96's own contract explicitly
collapsing the two claims (an operator/reviewer decision on the *parent* plan, recorded there — not
a disclosure buried in this plan's evidence report), or (b) locating another genuinely independent
final-state evidence source. Task 4 must NOT omit the `final_agent_state` field on the strength of a
this-plan-local disclosure alone; that path is closed. This is a real, live risk that could block
this plan pending a parent-contract decision — surface it as such, do not paper over it.

- [ ] **Step 6: Report findings before Task 2 begins**

Show the ruling, the two empirical proofs (Step 2), the pinned invocation string (Step 3), the pinned
audit-entry source (Step 4), and the pinned real output shape (Step 5) to the reviewer. Do not start
Task 2 until this is acknowledged.

---

### Task 2: RED — Prove the Committed `acpx --version` Path Cannot Satisfy Step 2

**Files:**
- Modify: `tests/unit/tools/test_run_plan996_acpx_security_evidence.py`

- [ ] **Step 1: Add a failing capability-gap test that genuinely fails as an assertion, not an import error or a trivial pass**

The first draft of this step was self-contradictory: asserting that the *default* `--version`
output contains no parseable session records would simply **pass** on the committed code (there is
genuinely nothing there — that's not a RED test, it's a true statement about the status quo), while
asserting against a not-yet-existing `_extract_stop_reason` function would fail with an import/name
error — exactly the "wrong reason" this same step's own Expected text (Step 2 below) forbids.

Instead, run the tool's **current, default** capture path for real (or against a stub `acpx`) exactly
as it exists today, load the resulting signed evidence manifest it already writes
(`json.loads(manifest_path.read_text())`), and assert the **desired contract** against it:
`manifest.get("stop_reason") == "end_turn"` and `manifest.get("tool_call_count", 0) > 0` (or
equivalent, once Task 1 Step 5 pins the exact field names this plan adds). This fails today as a
genuine `AssertionError` — `stop_reason`/`tool_call_count` do not exist in the current manifest
schema at all — because the capability is missing, not because of a typo or a nonexistent import.
This is the plan's required falsification proof, not a placeholder.

- [ ] **Step 2: Run and confirm RED**

```bash
uv run pytest tests/unit/tools/test_run_plan996_acpx_security_evidence.py -k capability_gap -v
```

Expected: FAIL, with a failure message that names the missing capability (no session-result parser,
no `exec`-mode command construction), not an import error or fixture typo.

---

### Task 3: Implement the `exec`-Mode Command Construction

**Files:**
- Modify: `tools/run_plan996_acpx_security_evidence.py`
- Modify: `tests/unit/tools/test_run_plan996_acpx_security_evidence.py`

- [ ] **Step 1: Add the fixed, deterministic session task and fixture — created as E2E/operator setup, not by the evidence tool itself**

Define exact, concrete constants — not just a description — so every later reference to "the fixture"
in this plan (Task 5's Stage A reset command, the E2E assertions) can use real, executable values
instead of bracket placeholders:

```python
_SESSION_FIXTURE_FILENAME = "plan998_fixture.py"
_SESSION_FIXTURE_PRISTINE_CONTENT = "def status():\n    return 'pending'\n"
SESSION_TASK = (
    "Add a module docstring to `plan998_fixture.py` describing its function. "
    "Modify only `plan998_fixture.py`; do not create any other files or tests."
)
```

(A single-file docstring edit, analogous in shape to Plan 9.88's `PLAN988_REPLAN_TASK` pattern, but
its own distinct artifact — do not reuse Plan 9.6/9.87/9.88's own fixture text verbatim.) **The
fixture file itself must be created by Task 5's E2E test / operator scratch-workspace setup,
immediately before the gated capture command runs — never by the evidence tool internally as a side
effect of `authorize_capture()`/`_capture_to_disk`.** Creating it inside the tool would mix "test
setup writes" with the actual session-triggered mutations the "zero pre-approval mutation" assertion
(Task 4 Step 3, Task 5 Step 2) needs to measure cleanly, and would itself run before authorization if
placed carelessly.

**A docstring task does not "guarantee" a tool call merely by being chosen — the write must actually
be permitted to happen.** ACP tool calls typically require the client (`acpx`) to grant edit
permission; empirically confirm (via `acpx --help`/`acpx exec --help`, per Task 1 Step 3's "don't
assume" discipline) whether `acpx exec` needs an explicit auto-approve flag for file-write
permissions.

**Pin two SEPARATE builders, not one — the permission flag belongs to the outer `acpx` argv, never to
the `--agent` value string.** Re-reading the frozen Plan 9.87 helper's own construction
(`run_plan987_acpx_live_evidence.py:1216-1228`) precisely: `cmd = [acpx, "--format", "json",
*approve_flag, "--cwd", str(workspace), "--agent", _agent_invocation(), "exec", task]` —
`--approve-all` sits in the **outer acpx command**, between `--format json` and `--cwd`; the
`--agent` VALUE is just the separate agent-invocation string (`_agent_invocation()`), with no
permission flag inside it at all. Task 1 Step 3 pins the `--agent` value (the `optimus-agent
--workspace-root ... --launch-session-id ... --debug-trace [--diagnostic-grant-id ...]` string);
this task's Step 3 builds the outer `acpx` argv. If Task 1 Step 3's empirical check confirms `acpx`
needs an equivalent auto-approve flag, it goes into **this task's outer-argv builder** (alongside
`--format`/`--cwd`), never appended to or folded into the `--agent` invocation string — a compliant
implementer must not be able to silently pass it to the wrong parser. Without it in the right place,
the session can stall on a pending/denied permission and never produce the tool-call or mutation
evidence this plan exists to gather.

- [ ] **Step 2: Add `agent_invocation()` resolution — optimus-agent arguments ONLY**

Resolve `shutil.which("optimus-agent")`; fail closed with a value-safe message if absent (mirrors the
existing `acpx is None` check at `main():718-721`). Construct the invocation per Task 1 Step 3's
pinned form: `optimus-agent --workspace-root <ws> --launch-session-id <id> --debug-trace
[--diagnostic-grant-id <id>]` and nothing else. **The permission-granting flag (`--approve-all` or
its confirmed equivalent) is an `acpx` flag and belongs to the outer `acpx` argv (Step 3), NOT to
this agent-invocation string** — it is not an `optimus-agent` argument at all. This builder contains
only `optimus-agent`'s own arguments. Never reference the retired `run-optimus-agent.cmd`/`.sh`
wrapper scripts.

- [ ] **Step 3: Add the new capture mode's command construction and a distinct real-session deadline in `main()`**

Add an additive CLI flag (e.g. `--drive-session`) that, when present, builds the outer `acpx` argv
`[acpx, "--format", "json", <permission flag from Step 1 if confirmed>, "--cwd", str(args.workspace),
"--agent", agent_invocation, "exec", SESSION_TASK]` instead of `[acpx, "--version"]`. The existing
default (no flag) behavior — the already-reviewer-approved `--version` smoke — must be completely
unchanged; this is a strictly additive capability. Per Task 1's ruling, `authorize_capture()` must
not consume the diagnostic grant when `--drive-session` is set; pass `diagnostic_grant_id` straight
through into the constructed `--agent` invocation string instead of calling
`store.consume_diagnostic_grant` in this path.

**Extract this into a pure, directly-testable function — do not inline it in `main()` only. And do
NOT make `agent_invocation`/`optimus-agent` resolution a new prerequisite for the frozen `--version`
path, which never needs it.** Add `_build_capture_command(*, acpx: str, workspace: Path,
agent_invocation: str | None, drive_session: bool) -> list[str]` — `agent_invocation` is `Optional`,
not required, because the `--version` argv (`drive_session=False`) never references it at all (no
`--agent` flag in that command). Return either `[acpx, "--version"]` (when `drive_session` is
`False` — `agent_invocation` is accepted but ignored, may be `None`) or the `--drive-session` argv
(when `True`, in which case `agent_invocation` must be non-`None` — raise if it isn't, that's a
caller bug, not a runtime condition to design around). No side effects, no dependency on `main()`'s
own argument parsing or the gate.

**`main()` must only resolve `agent_invocation` (i.e., call `shutil.which("optimus-agent")`, per
Step 2) when `--drive-session` is actually set — never unconditionally.** The already-reviewer-approved
`--version` smoke's prerequisites must stay byte-identical to what's committed today: it currently
requires only `acpx` on PATH, nothing else. Making `optimus-agent` resolution unconditional (running
even for plain `--version` invocations) would silently add a new prerequisite to a path this plan
promises to leave completely unchanged — an environment with `acpx` but not yet `optimus-agent`
installed would newly fail the smoke it previously passed. Guard Step 2's resolution call with `if
args.drive_session:`. This gives Task 5's source-level tests (Step 1) a real, isolated seam to call
`_build_capture_command()` directly, instead of needing to drive the whole CLI to observe the
constructed command.

**Add and GRAMMAR-VALIDATE the `--evidence-run-nonce` argument — it is caller-controlled text written
verbatim into the HMAC-signed manifest, bypassing the sanitizer, so "content-free" must be enforced,
not merely asserted.** Add a `--evidence-run-nonce <str>` argument (required when `--drive-session`
is set) recorded verbatim into the manifest's `evidence_run_nonce` field (Task 4 Step 3). Because
this value skips the `StreamingTextSanitizer` (it's not child output — it's a caller argument copied
straight into a signed field), a caller could otherwise smuggle secret material or arbitrary text
into a persisted, HMAC-attested artifact. Enforce an exact bounded grammar — reject with a value-safe
error and a non-zero exit **before** authorization/any capture side effect if it does not match
`^run_[0-9a-f]{24}$` (i.e. the literal prefix `run_` followed by exactly 24 lowercase hex chars,
matching the `f"run_{secrets.token_hex(12)}"` generator). Add unit tests for malformed (`bad-nonce`),
oversized (a 10 KB string), and secret-shaped (`run_` + a real-looking key fragment that is not
24-hex) inputs, asserting each is rejected pre-authorization.

**Pin a distinct real-session deadline — the committed 30 s smoke timeout will kill a legitimate
session.** The committed `_CAPTURE_WAIT_TIMEOUT_SECONDS = 30.0`
(`run_plan996_acpx_security_evidence.py:71`) is correct for the sub-second `acpx --version` smoke but
far too short for a real Gateway-backed `exec` turn; the frozen real-`acpx` helpers
(`run_plan987_acpx_live_evidence.py:28`, `run_plan988_fu4b_live_evidence.py:59`) both use
`ACP_TIMEOUT_SECONDS = 600` for exactly this reason. Reusing 30 s for `--drive-session` would kill a
perfectly healthy tool turn as if it were a hang. Keep the existing `_CAPTURE_WAIT_TIMEOUT_SECONDS =
30.0` for the default `--version` path **byte-unchanged**; add a separate
`_DRIVE_SESSION_WAIT_TIMEOUT_SECONDS` defaulting to 600 (matching the frozen helpers) for
`--drive-session`. **The test-injectable short bound is a direct function parameter / hidden
`argparse.SUPPRESS` CLI arg only — NOT an environment override.** An env-var deadline would introduce
a new inherited-environment dependency that conflicts with Plan 9.96's single-capture / no-late-reads
discipline and its frozen `OPTIMUS_*` registry scope (an unregistered override is outside that
scope). The RED test in Step 4 forces its short bound through that parameter, never through the
environment. The `--version` smoke's behavior and timeout must not change at all.

- [ ] **Step 4: Fix the capture pipeline's timeout ordering before it can safely run a real, potentially long-running or hung session**

**Do not reuse `_capture_to_disk` unchanged for real sessions — it has a real, confirmed hang risk
that the `--version` smoke never exposed because that child exits almost immediately.** Read
`tools/run_plan996_acpx_security_evidence.py:289-327` (`_capture_to_disk`): both reader threads are
started, then `for worker in workers: worker.join()` runs to completion **before** the
`try: process.wait(timeout=_CAPTURE_WAIT_TIMEOUT_SECONDS)` block is ever reached. Each reader thread
blocks on `source.read(_STREAM_READ_SIZE)` inside `_stream_sanitized`, which only returns once the
child closes that pipe (i.e., only at child exit, or an explicit close) — there is no timeout on the
`read()` call itself. A real `acpx exec` session that hangs (a stalled permission prompt with no one
to answer it, a network stall, a genuine bug) blocks `worker.join()` forever, so
`_CAPTURE_WAIT_TIMEOUT_SECONDS` never gets a chance to fire at all. This is the same defect class the
checkpoint log already caught once for the `--version` smoke (PRE-SMOKE FIX 4) — this time in the
reader-thread ordering rather than `process.wait()`/stdin, and only latent-not-triggered for a
sub-second child.

**The RED test must run the hang-prone call in an isolated subprocess, not the pytest process itself
— a same-process hang cannot be safely terminated — AND it must clean up its own descendant, because
before the fix exists the outer timeout leaves the descendant orphaned (that is the very defect being
demonstrated).** Python threads cannot be forcibly killed; if the RED test calls `_capture_to_disk`
directly in-process and it hangs, wrapping the *test* in an outer timeout leaves the blocked reader
threads alive and the pytest worker unrecoverable. Instead, run the RED probe as its own subprocess
invoking `_capture_to_disk`/`capture_acpx` against a stub command. **The stub must spawn a sleeping
DESCENDANT as well as a non-terminating parent** — e.g. a parent stub that launches
`python -c "import time; time.sleep(999)"` and then also sleeps — because a single sleeping child only
proves immediate-child termination and would let a broken tree-kill (that misses the descendant) pass;
`acpx` spawns an `optimus-agent` descendant, so the fixture must model that two-level tree.

**Harness-owned cleanup is mandatory, in a `finally` — AND it must independently target the
acpx-stub-child's OWN process group, not just the harness's, because once the fix below lands the
target code detaches the child into a brand-new group the harness's own group-kill cannot reach.** A
plain `subprocess.run(..., timeout=...)` on the probe kills only the probe's immediate process on
timeout, orphaning the sleeping descendant — the un-fixed code's exact failure, reproduced by the test
itself. So the RED harness owns its own process group: launch the probe with `start_new_session=True`
(POSIX) / `CREATE_NEW_PROCESS_GROUP` (Windows), record the probe PID and — by reading them from a file
the stub writes, or by group enumeration — the acpx-stub-child's own PID and the descendant's PID.

**This same test file exercises the code both pre-fix (RED, proving the hang) and post-fix (GREEN,
proving clean termination) — and the two cases have DIFFERENT process-group topology.** Pre-fix, the
acpx-stub-child inherits the probe's own process group (normal child inheritance), so a single
`os.killpg`/`taskkill` on the harness's own group reaches everything. **Post-fix, item 1 below makes
`spawn_authorized_capture` itself call `start_new_session=True`/`CREATE_NEW_PROCESS_GROUP` on the
acpx-stub-child** — `setsid()` (POSIX) detaches it into a brand-new session and process group of its
own, no longer a member of the harness's/probe's group at all. A harness cleanup that only kills its
OWN group would, post-fix, kill the probe but silently miss the now-detached acpx-stub-child and its
descendant entirely — the opposite of what the RED test is supposed to prove clean. (In the intended
GREEN behavior the target's OWN internal tree-kill, item 1, should already have cleaned up before the
harness's outer bound even fires; this harness-level cleanup is the backstop for the pre-fix case and
for a bug in the fix's own internal timeout — it must work correctly in both topologies, not just one.)

Fix: in the `finally` block, attempt group-kill on **both** targets independently — the harness's own
group (`os.killpg(harness_pgid, SIGKILL)` / `taskkill /F /T /PID <probe_pid>`), AND, using the
separately-recorded acpx-stub-child PID, `os.killpg(os.getpgid(child_pid), SIGKILL)` (POSIX) /
`taskkill /F /T /PID <child_pid>` (Windows) — wrapping each in its own try/except so one target's
absence (e.g. it already exited) doesn't block the other's cleanup attempt. Before the RED test
returns, assert (via `os.kill(pid, 0)` / a platform-equivalent liveness probe) that neither the probe,
the recorded acpx-stub-child PID, nor the recorded descendant PID is still alive — this assertion must
hold in both the pre-fix and post-fix topology. The RED test proves the defect **and** leaves no
orphan behind, in either process-group shape.

Then implement a bounded, fail-closed fix with two independent parts:

1. **Bounded joins + a pinned, dependency-free process-tree termination strategy.** Give the
   reader-thread joins their own deadline (e.g. `worker.join(timeout=...)`), and if exceeded,
   terminate the **entire process tree**, not just the immediate `acpx` child — `process.kill()` on
   the `Popen` object only signals that one process; it does not reach the `optimus-agent` descendant
   `acpx` spawned via `--agent`. **Do not use `psutil` — it is not a project dependency and adding it
   expands this plan's scope.** Use only the standard library / OS built-ins, pinned exactly:
   - **POSIX:** spawn the `acpx` child with `start_new_session=True` (puts it in its own process
     group), then on timeout `os.killpg(os.getpgid(process.pid), signal.SIGKILL)` — reaches the whole
     group including the `optimus-agent` descendant.
   - **Windows:** spawn with `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP`, then on timeout run
     `subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], ...)` — `taskkill /T`
     terminates the entire tree; `taskkill` is a Windows built-in, no new Python dependency.
   **Apply these `Popen` creation flags ONLY on the `--drive-session` path, not globally** — the plan
   promises the `--version` smoke's spawn is completely unchanged, and `CREATE_NEW_PROCESS_GROUP` /
   `start_new_session` measurably alter the spawn (signal-handling, console-group membership). Thread
   a flag from `main()` (drive-session true/false) into `spawn_authorized_capture` and set the
   creation flags only when it is true; the `--version` smoke spawns exactly as it does today. After
   the tree kill, do the final bounded join so the blocked `read()` calls get EOF and the threads
   finish shortly after.
2. **Nonzero exit code must ALSO block promotion, independent of the timeout path.** Read
   `run_plan996_acpx_security_evidence.py`'s current `main()`: after `_capture_to_disk` returns, it
   proceeds unconditionally to `_joined_scan`/`_write_evidence_manifest` and only returns
   `result.exit_code` as the CLI's own exit code at the very end — it never checks
   `result.exit_code != 0` before writing the manifest. A real session where `acpx` genuinely fails
   (crash, refusal, error — not a hang) would still produce a fully HMAC-signed manifest that looks
   like verified, successful evidence. Add an explicit check: if `result.exit_code != 0` (from either
   a genuine nonzero exit or the new timeout path), quarantine whatever was written and do not call
   `_write_evidence_manifest` at all. (Note: this only affects `--drive-session`; the `--version`
   smoke legitimately exits 0, so its existing behavior is unchanged.)

**Never promote a partial or failed artifact** — a timed-out or failed session must not produce a
manifest that looks like a completed, verified capture. Confirm both the timeout RED test and a new
nonzero-exit-code test are resolved by the fix.

- [ ] **Step 5: Add unit tests for the new construction**

Test the command list shape directly (no real `acpx` needed for this test — assert the constructed
`Sequence[str]` equals the expected argv), and test that `--drive-session --mode elevated` does not
consume the grant via the outer gate (spy on `store.consume_diagnostic_grant` the same legitimate way
the existing tests spy on `spawn_authorized_capture`/`_capture_to_disk` — asserting a call that must
NOT happen, never replacing code under test).

- [ ] **Step 6: Run focused tests, Ruff, diff-check**

```bash
uv run pytest tests/unit/tools/test_run_plan996_acpx_security_evidence.py -v
uv run ruff check tools/run_plan996_acpx_security_evidence.py tests/unit/tools/test_run_plan996_acpx_security_evidence.py
git diff --check
```

Expected: all pass; the Task 2 RED test now either still correctly demonstrates the *default* path's
limitation, or is retargeted to prove the *old* behavior only (do not delete it — keep it as a
permanent regression pin that the `--version` default never silently starts behaving like the new
mode).

---

### Task 4: Parse Session Results and Extend the Manifest with Content-Free Evidence

**Files:**
- Modify: `tools/run_plan996_acpx_security_evidence.py`
- Modify: `tests/unit/tools/test_run_plan996_acpx_security_evidence.py`

- [ ] **Step 1: Add a session-result parser, written against Task 1 Step 5's pinned real shape**

Write a parser (new function, not reusing the frozen `run_plan987_acpx_live_evidence.py` module)
against the **actual, empirically pinned** output shape from Task 1 Step 5 — not an assumed
`session/prompt`/`result.stopReason` shape. **The transcript parser is responsible ONLY for fields
actually present in `transcript.stdout`:** the terminal stop reason (expecting `"end_turn"` on
success, using whatever field/record Task 1 Step 5 identified); `tool_names` (a tuple of content-free
tool-call identifiers/types observed — this and `tool_call_count = len(tool_names)` are the two
fields this plan uses everywhere; `tool_names` is primary, `tool_call_count` is derived from it, and
every reference in this plan (Task 2's RED test, this step's manifest fields, Task 5's E2E
assertions) uses this same pair); and `total_cost_usd` (from whatever cost/usage record the real
Gateway-backed session emits, per Task 1 Step 5's finding). This parser operates on the **sanitized**
`transcript.stdout` only, never on raw child output, consistent with Constraint 5. If Task 1 Step 5
found that `acpx --format json` echoes raw ACP JSON-RPC frames
verbatim, the parser may legitimately contain literal protocol strings as *data it reads*, which is
why Task 5 Step 1's source test checks for outbound protocol construction, not for the presence of
any particular substring (see that step).

- [ ] **Step 2: If `final_agent_state`'s source is OUTSIDE the transcript, add a separate typed collector — the stdout parser cannot reach it**

If (and only if) Task 1 Step 5 proved the distinct `final_agent_state` signal lives somewhere other
than `transcript.stdout` (e.g. the real Redis `RedisAgentStateStore` ledger), then Step 1's
transcript parser structurally cannot produce it — a stdout parser reads stdout. Define a **separate,
typed final-state collector** with its own contract: (a) it reads the pinned source once, after the
session completes (e.g. a keyed read from the real state store for this run's workspace/session), (b)
reduces the result to a single content-free metadata value (the completion-state enum/string only —
never plan text, file contents, or any payload), (c) writes that value into a new immutable
per-capture snapshot file in `output_dir` (e.g. `final-state-snapshot.json`) through the same
`StreamingTextSanitizer` pipeline, so it is digested-in-manifest and joined-scanned exactly like the
audit/debug snapshots, and (d) has its own unit test proving it reduces a realistic source record to
the expected content-free value and never leaks payload. The manifest's `final_agent_state` field is
then populated from that collector's snapshot, not from the transcript parser. If Task 1 Step 5 found
the signal DOES live in the transcript, no separate collector is needed — the Step 1 parser handles
it and this step is a no-op. If Task 1 Step 5 found NO distinct signal at all, neither path applies
and the parent-contract-amendment ruling (Task 1 Step 5) governs.

- [ ] **Step 3: Extend the evidence manifest fields — cover every Plan 9.96 Task 9 Step 2 claim by name, and extend digest/scan coverage beyond stdout/stderr**

A bare `tool_call_count` does not prove *which* tools ran, and neither `stop_reason` nor any other
field this plan had proposed actually names the agent's own final state — Plan 9.96 Task 9 Step 2's
text lists "final state" and terminal `end_turn` as two *separate* required claims, not one. Add:

- `session_mode` (`"ordinary"`/`"elevated"`)
- `tool_names` (tuple of content-free tool-call identifiers/types observed) and `tool_call_count`
  (`= len(tool_names)`, kept as an explicit field for convenience) — not just a count alone, so the
  manifest can support asserting *which* tools ran, per Task 1 Step 5's pinned real shape. Every
  other reference in this plan (Task 2's RED test, Task 5's E2E assertions) uses this same pair.
- `total_cost_usd` (str/Decimal-safe, not a secret — Plan 9.87/9.88 already record this in the clear)
- `stop_reason` (str, the ACP-level `stopReason`, expecting `"end_turn"`)
- `final_agent_state` (str) — **only if Task 1 Step 5 confirmed a real, distinct domain-state signal
  exists**, populated from the Step 1 transcript parser if the signal lives in the transcript, or from
  the Step 2 separate typed collector if it lives outside (e.g. Redis). If Task 1 Step 5 found none,
  this field is NOT omitted by local decision: per Task 1 Step 5's ruling this plan cannot waive Plan
  9.96's separately-enumerated "final state" claim itself; the resolution is a reviewed Plan 9.96
  parent-contract amendment or another independent final-state source, decided outside this plan. Do
  not fabricate a value and do not silently drop the claim.
- `child_key_names` (tuple of names only, sourced from the workspace's **outer** — evidence tool's
  own — audit entry per Task 1 Step 4's corrected ruling, not the inner `optimus-agent` entry; see
  the mechanical selection rule below)
- `elevated_tag_present` (bool, sourced from the current run's debug-trace snapshot per Task 1 Step
  3's pinned `--debug-trace` requirement; see the mechanical selection rule below)
- `evidence_run_nonce` (str) — a content-free freshness anchor the caller supplies via a new
  `--evidence-run-nonce` argument (see Task 5 Step 3's freshness redesign). It is a random token the
  E2E test generated, recorded verbatim into the manifest and thus HMAC-signed; it is NOT the
  `launch_session_id` (which is owned by the diagnostic-grant binding ceremony and must not be
  repurposed — see the critical correction in Task 5 Step 3).

No raw prompt text, no file contents, no secret values, no full environment mapping. (The
pre-authorization mutation proof is deliberately NOT a manifest field — see the redesign below.)

**Do not digest or scan the live, shared workspace log files directly — snapshot the current run's
records into `output_dir` first, selected by pre-launch offset, NOT by any per-run identifier.**
`launch-audit.ndjson` and `debug-acp.ndjson` live under `<workspace>/.optimus/`, are shared and
append-only across every capture run against that workspace, and grow with each subsequent run.
Digesting them directly would make a later elevated run's append spuriously break an earlier ordinary
manifest's digest. **The previous revision proposed selecting "the audit entry matching this run's
`launch_session_id`" and "debug entries carrying this run's correlation tag" — neither is mechanically
possible:**
- Both the outer (evidence-tool) audit entry AND the inner (`optimus-agent`) audit entry carry the
  **same** `launch_session_id` (the inner agent must receive that exact value to consume the grant),
  so matching on it cannot distinguish outer from inner.
- Debug records carry NO `launch_session_id` at all — `acp_debug_log()` writes a process-local random
  `sessionId` (`debug_trace.py:78`), unrelated to the gate's session id — and an ordinary run
  intentionally has NO correlation tag, so "entries carrying this run's correlation tag" selects
  *nothing* for the ordinary case, which is precisely the case that needs to prove tag ABSENCE.

Use a non-circular, offset-based boundary instead. In the capture tool, **before** appending the
outer audit entry (i.e. before `append_authorized_audit`) and **before** spawning the child, record
the current byte length (or line count) of `<workspace>/.optimus/launch-audit.ndjson` and
`<workspace>/.optimus/debug-acp.ndjson` (treat a missing file as length 0). After the child completes,
read only the appended **suffix** of each file (from the recorded offset to EOF) — that suffix is
exactly this run's own records. Write each suffix through the same `StreamingTextSanitizer` pipeline
to new, immutable, per-capture snapshot files in `output_dir`: `audit-snapshot.ndjson`,
`debug-snapshot.ndjson`. Within the audit snapshot, identify the **outer** entry mechanically as the
**first record in document order** (the tool appends its own audit entry before spawning the child, so
the outer entry is necessarily written first; the inner `optimus-agent` entry follows during the
child run) — never by looking for the desired five-key result, which would be circular. Extend
`_TRANSCRIPT_ARTIFACTS` (or a parallel tuple) to include these two immutable snapshot files so they
get the same SHA-256 digest-in-manifest and joined-scan treatment; `verify` re-checks the snapshots,
never the mutable `.optimus/` originals. `child_key_names` comes from that first audit-snapshot
record; `elevated_tag_present` is whether any allowlisted `session_correlation_tag` entry appears
anywhere in the debug snapshot.

**The offset boundary is only sound if the workspace is single-writer for the run — declare it, and
validate the suffix mechanically, failing closed on any foreign writer.** The offset→EOF suffix
equals "this run's records" ONLY if nothing else appended between offset capture and readback. If an
unrelated capture (or a second elevated-tracing process) appended concurrently, a foreign audit
record could become the first record (corrupting `child_key_names`) or a foreign
`session_correlation_tag` could falsely validate an ordinary run as elevated. Two guards, both
required:
1. **Single-writer by construction:** the controlled evidence workspace runs exactly one capture at a
   time — document this operational constraint in Task 5's runbook (the ordered ceremony already
   serializes ordinary vs elevated) and in Task 7's evidence report.
2. **Mechanical suffix validation, fail-closed, in the tool at snapshot time** (the tool knows its own
   run's `launch_session_id`): assert every audit record in the suffix carries that exact
   `launch_session_id`; and assert the suffix contains EXACTLY the expected number of audit records
   (the outer entry plus the inner `optimus-agent` entry — i.e. 2). **Do NOT also assert "the first
   record is the outer event shape" — there is no such shape to check.** Both the outer (evidence
   tool's own) and inner (`optimus-agent`'s) audit entries are the identical `LaunchAuditEvent`
   dataclass with the identical field set (`launch_audit.py`) — there is no field that structurally
   differs between an outer-authored and an inner-authored record, so a "shape" assertion has nothing
   to check and cannot be implemented as written. The outer/inner distinction is established PURELY by
   POSITION: the evidence tool's own `append_authorized_audit` call happens before it spawns `acpx`
   (Task 8, already committed), and `optimus-agent`'s own `_append_audit_or_exit` runs later, during
   the child's own execution — this append-before-spawn ordering is a structural guarantee of the
   code's control flow (confirmed once, empirically, in Task 1 Step 4's investigation), not something
   re-verified per snapshot via content. The two REAL, implementable checks — exact count (2) and
   matching `launch_session_id` on every record — are what catch a foreign writer; assert every debug
   record in the debug suffix shares exactly ONE `sessionId` value. On any mismatch — wrong record
   count, a foreign `launch_session_id`, multiple debug `sessionId`s — quarantine and fail closed
   (nonzero exit, no manifest), because a foreign writer means the snapshot boundary is unsound and
   the evidence cannot be trusted. Test this: construct a suffix with an injected foreign audit record
   / a second debug `sessionId` and assert the tool quarantines rather than promoting.

**The pre-authorization mutation proof does not belong in the HMAC-signed capture manifest at all —
a self-asserted boolean there would be unverifiable evidence, AND it needs a genuinely unapproved
workspace, which the fixed evidence workspace is not.** There is no trustworthy path for a "the
fixture digest was unchanged" claim to reach the manifest as a plain field (nothing stops an
implementer hardcoding `true`); and Task 5's fixed workspace (`C:/tmp/optimus-plan998-evidence`)
already holds the reusable durable approval that ordinary and elevated captures require, so a capture
attempt *there* would be authorized and could never exercise the `NO_APPROVAL` rejection path this
proof depends on. Instead, prove it as its own dedicated E2E test against a **separate, genuinely
unapproved workspace**: (1) create a distinct scratch workspace with its own identity — explicitly
NOT `C:/tmp/optimus-plan998-evidence` — e.g. a fresh `tmp_path`-based directory; (2) create the
fixture file inside it and compute the fixture's SHA-256; (3) mechanically confirm no durable approval
record exists for that workspace's identity (query the store's `read_durable(ws_digest)` and assert
`None`, so the test proves the precondition rather than assuming it); (4) run one real
`--drive-session` capture attempt against that unapproved workspace — passing a throwaway
`--evidence-run-nonce` value so the command is well-formed and the rejection is genuinely the gate's
`NO_APPROVAL`, not an argparse missing-required-argument error (both would exit 2, so the test must
assert on the gate's specific value-safe message, not the bare exit code, to fail for the right
reason) — and assert it is rejected before any side effect (`LaunchGateError(NO_APPROVAL)`, exit 2,
no traceback), binding the exact rejected message, the workspace identity, and this test's own run
together in the assertions; (5) recompute the fixture's SHA-256 and assert byte-identical. This is
directly, mechanically re-runnable — no manifest field, no boolean flag, no self-reported claim.

The existing `_compute_evidence_manifest_hmac` already signs "every field except `hmac`," so the new
top-level fields are automatically covered — confirm with a mutation test. The extended digest/scan
coverage over the new snapshot files is a separate mechanism from the top-level-field HMAC and needs
its own confirmation.

- [ ] **Step 4: Add fail-closed manifest tests**

Add a test analogous to Task 8's `test_verify_rejects_tampered_manifest_field`, mutating one of the
*new* fields while keeping the stored HMAC, asserting `EVIDENCE_HMAC_MISMATCH` and quarantine. Add a
test that a genuinely elevated run's manifest has `elevated_tag_present=True` and an ordinary run's
has `False` — the "ordinary no-tags / elevated allowlisted tags" property, pinned at the manifest
layer. Add the nonce-grammar rejection tests from Task 3 Step 3 (malformed / oversized / secret-shaped
`--evidence-run-nonce` rejected pre-authorization) if not already added there.

- [ ] **Step 5: Classify any new sink in the logging-surface manifest**

```bash
uv run python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
```

If this fails with `UNCLASSIFIED_SINK`, classify the new sink (same discipline as Plan 9.96 Task 7/8:
per-surface connected-path rationale, real resolvable `test_node`, evidence tier) before continuing.
Iterate until green. Note the new snapshot-writing sinks (`audit-snapshot.ndjson`,
`debug-snapshot.ndjson`, and `final-state-snapshot.json` if Step 2 added it) each need classification.

- [ ] **Step 6: Run focused tests, Ruff, diff-check**

```bash
uv run pytest tests/unit/tools/test_run_plan996_acpx_security_evidence.py -v
uv run ruff check tools/run_plan996_acpx_security_evidence.py tests/unit/tools/test_run_plan996_acpx_security_evidence.py
git diff --check
```

---

### Task 5: Add the Real E2E Evidence Node

**Files:**
- Create: `tests/e2e/acp/test_plan996_authorized_launch.py`

- [ ] **Step 1: Add the source-level no-protocol-reimplementation test — test intent, not substrings**

Plan 9.88's own precedent test (`test_helper_source_does_not_implement_acp_protocol`) bans literal
`"session/prompt"`/`"jsonrpc"` substrings outright, but Task 4's parser reads whatever field/record
Task 1 Step 5 empirically pins — which may legitimately include those exact strings **as data it
parses from acpx's real output**, if that is what Task 1 Step 5 finds acpx actually emits. Banning
any protocol field-name substring — including a residual ban on the literal `"jsonrpc"` key, which
the previous revision of this step still had — would reject a fully compliant parser, since real
JSON-RPC 2.0 frames (if that is what `acpx --format json` echoes) legitimately carry a `"jsonrpc"`
key. **Do not ban any protocol field-name substring at all.** The real dividing line is *sending* a
request versus *reading* one `acpx` already produced, and that is a structural/behavioral property,
not a string-matching one: never import or instantiate the project's own ACP client
(`NdjsonSubprocessSession`, `optimus.acp.ndjson_subprocess_session`), and never open a writable pipe
to a child's stdin (sending a JSON-RPC request requires writing one) — the committed
`spawn_authorized_capture` already uses `stdin=subprocess.DEVNULL` (`run_plan996_acpx_security_evidence.py:206`),
which structurally rules out ever feeding the child anything, so asserting that property holding is a
real, non-vacuous guarantee, not string-matching:

**(P2, still worth fixing properly) A pure substring test is trivially bypassable** — an import alias
(`import subprocess as sp`), a differently-named helper, or reformatted whitespace defeats a literal
string match, and the positive assertions (`"subprocess.Popen" in source`) are vacuous once *any*
code anywhere in the file happens to contain those tokens. Use two layers instead: an AST-based
structural check for the forbidden import/instantiation, and a **behavioral** test that intercepts
the actual command the tool spawns and asserts its real properties (installed `acpx` resolved,
`stdin=subprocess.DEVNULL`) rather than reading source text at all:

**These two tests are offline (no real `acpx`, no live dependencies) — keep them in the unit-test
file `tests/unit/tools/test_run_plan996_acpx_security_evidence.py`, NOT in the `-m e2e` E2E module.
Only the genuinely live ordinary/elevated tests (Steps 2-3) are marked `e2e`.** The AST check must
inspect each import's **original** `alias.name` (never the local alias), and check the fully-qualified
module-plus-symbol, so `from optimus.acp.ndjson_subprocess_session import NdjsonSubprocessSession as
client` and `from optimus.acp import ndjson_subprocess_session as client` are both caught:

**These tests need real imports. The committed test file (Task 8) already has `sys`, `Path`,
`tools.run_plan996_acpx_security_evidence` (aliased `capture_tool`), and
`authorize_capture`/`append_authorized_audit`/`spawn_authorized_capture` in its existing import
block (`tests/unit/tools/test_run_plan996_acpx_security_evidence.py:1-38`) — reuse the SAME
`capture_tool` alias, do not introduce a second, differently-named import of the same module. Add
`ast` and `subprocess` (both stdlib, likely not yet imported) and extend the EXISTING
`from tools.run_plan996_acpx_security_evidence import (...)` block with the two new names Task 3/4
add:**

```python
import ast          # add to the existing stdlib imports
import subprocess   # add to the existing stdlib imports

# extend the EXISTING `from tools.run_plan996_acpx_security_evidence import (...)` block with:
#     _build_capture_command,
#     SESSION_TASK,
```

```python
def test_capture_tool_does_not_import_project_acp_client() -> None:
    tree = ast.parse(Path(capture_tool.__file__).read_text(encoding="utf-8"))
    forbidden_symbol = "NdjsonSubprocessSession"
    forbidden_module = "ndjson_subprocess_session"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:                      # `import optimus.acp.ndjson_subprocess_session ...`
                assert forbidden_module not in alias.name  # original name, ignore asname
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert forbidden_module not in module          # `from ...ndjson_subprocess_session import X`
            for alias in node.names:                       # `from ...acp import ndjson_subprocess_session`
                assert alias.name != forbidden_symbol      # original imported symbol, ignore asname
                assert forbidden_module not in alias.name


# Test 2a — stdin behavior, exercised against a REAL short-lived stand-in child (which is NOT
# acpx, so this test does not assert anything about the executable path). Reuses the exact
# real-fixture pattern the committed test_spawn_authorized_capture_merges_system_env_keys already
# uses (tests/unit/tools/test_run_plan996_acpx_security_evidence.py:960) — real
# authorize_capture -> append_authorized_audit -> spawn_authorized_capture, only the keyring backend
# faked, per the standing evidence bar:
def test_spawn_authorized_capture_uses_devnull_stdin(monkeypatch, tmp_path: Path) -> None:
    captured = {}
    real_popen = subprocess.Popen

    def _spy(cmd, *args, **kwargs):
        captured.update(kwargs)
        return real_popen(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", _spy)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace, environment=environment, keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    capture = authorize_capture(
        workspace=workspace, environment=environment, keyring_backend=keyring,
        approval_runtime_root=approval_runtime_root, launch_session_id="sess_stdin_devnull",
    )
    audited = append_authorized_audit(capture)

    process = spawn_authorized_capture(audited, command=[sys.executable, "-c", "pass"])
    process.communicate(timeout=10)  # let the real short-lived child actually finish — do not
    # leave it running/unreaped when the test returns, matching the committed
    # test_spawn_authorized_capture_merges_system_env_keys pattern exactly

    assert process.returncode == 0
    assert captured["stdin"] is subprocess.DEVNULL


# Test 2b — the extracted _build_capture_command() builder (Task 3 Step 3) places a SUPPLIED
# resolved path at command[0] — it does not itself perform any resolution (no shutil.which call
# lives inside this pure function; resolution is the caller's job, see Test 2c):
def test_build_capture_command_places_supplied_acpx_path_first() -> None:
    command = _build_capture_command(
        acpx="/fake/bin/acpx",
        workspace=Path("C:/tmp/fake-workspace"),
        agent_invocation="optimus-agent --workspace-root C:/tmp/fake-workspace --launch-session-id sess_x --debug-trace",
        drive_session=True,
    )
    assert command[0] == "/fake/bin/acpx"          # exact equality, not name.startswith
    assert command[-2:] == ["exec", SESSION_TASK]


# Test 2c — regression: main()'s DEFAULT path (no --drive-session) must NEVER resolve
# optimus-agent. This is what Test 2b's pure-function test cannot catch: main() could still call
# shutil.which("optimus-agent") unconditionally even though _build_capture_command() itself is
# correctly Optional — the bug would live in main()'s own resolution guard, not the builder.
#
# MUST use an AUTHORIZED (successful) path, not an unapproved-workspace rejection — an unapproved
# workspace exits at authorize_capture(), which happens BEFORE command construction; if the
# wrongly-unconditional resolution bug is placed near command construction (the natural spot, since
# that's where the committed code already builds `command=[acpx, "--version"]`, right after
# authorization succeeds), a test that rejects early would never reach it and would pass regardless
# of whether the bug exists. Mirrors the committed test_main_generates_launch_session_id_when_absent
# pattern exactly: authorize_capture/append_authorized_audit/_capture_to_disk/_known_secrets/
# _joined_scan/_write_evidence_manifest are all stubbed to complete successfully (no real gate, no
# real workspace, no real acpx), so execution reaches all the way through main()'s default-path
# command construction and returns 0 — the shutil.which SPY (not a blanket fake, so every queried
# name is recorded) is what actually observes whether optimus-agent was resolved along the way:
def test_main_default_path_never_resolves_optimus_agent(monkeypatch) -> None:
    queried_names: list[str] = []

    def _which_spy(name):
        queried_names.append(name)
        return "acpx" if name == "acpx" else None

    monkeypatch.setattr(capture_tool.shutil, "which", _which_spy)
    monkeypatch.setattr(capture_tool, "authorize_capture", lambda **kwargs: object())
    monkeypatch.setattr(capture_tool, "append_authorized_audit", lambda _capture: object())
    monkeypatch.setattr(
        capture_tool, "_capture_to_disk",
        lambda *a, **k: CaptureResult(exit_code=0, rule_counts={}),
    )
    monkeypatch.setattr(capture_tool, "_known_secrets", lambda _capture: ())
    monkeypatch.setattr(
        capture_tool, "_joined_scan",
        lambda *a, **k: {"hit": False, "rules_fired": [], "scanned_artifacts": []},
    )
    monkeypatch.setattr(capture_tool, "_write_evidence_manifest", lambda *a, **k: None)

    arguments = [
        "capture", "--workspace", "workspace", "--output-dir", "output", "--mode", "ordinary",
        # deliberately NO --drive-session flag — this is the default `--version` path
    ]
    exit_code = main(arguments)

    assert exit_code == 0  # reached the end of the default path, not an early rejection
    assert "acpx" in queried_names
    assert "optimus-agent" not in queried_names
```

The AST check inspects the *original* imported name/module (not the local alias), so no aliasing or
spelling escapes it — structural, not textual. **Test 2a** proves the DEVNULL property against a real
stand-in child (deliberately not acpx, so it makes no claim about the executable path — the previous
revision's single test wrongly asserted `startswith("acpx")` against a Python stand-in, which can
never hold), reusing the exact real-fixture pattern the committed
`test_spawn_authorized_capture_merges_system_env_keys` already establishes, and now also asserts
`returncode == 0` so the child's own completion status is checked, not just its stdin kwarg. **Test
2b** proves `_build_capture_command()` (Task 3 Step 3's extracted pure function) places a SUPPLIED
resolved path at `command[0]` by **exact** equality — it needs no `Popen`/`shutil.which` faking at
all, since the function performs no resolution itself; resolution is `main()`'s job, which is exactly
why Test 2b alone cannot catch a `main()`-level regression (a bug where `main()` calls
`shutil.which("optimus-agent")` unconditionally, even though the pure builder correctly accepts
`None`) — **Test 2c** closes that gap directly, spying on every name `shutil.which` is actually
queried with over a real `main()` invocation on the default (no `--drive-session`) path, and asserting
`optimus-agent` is never among them. Together these three give genuine structural + behavioral
coverage without the self-contradiction, and without a string-matching test a reformatted or aliased
implementation could trivially pass.

- [ ] **Step 2: Add the real ordinary-session E2E test — against a fixed, operator-pre-approved workspace, not a fresh pytest-generated one**

`test_spawned_agent_live.py`'s own pattern (a fresh `tmp_path`-based scratch workspace per run) does
not obviously work here: durable approval is an interactive, TTY-gated ceremony bound to a specific
workspace identity, and nothing in that pattern explains how a brand-new `tmp_path` workspace, created
fresh by pytest on every run, would already have one. Rather than assume that resolves itself, use the
**same fixed external workspace as the elevated test** (`C:/tmp/optimus-plan998-evidence`), with a
documented one-time operator prerequisite:

```bash
uv run optimus-trust --workspace-root C:/tmp/optimus-plan998-evidence approve --mode durable
```

This is authored **once**, interactively, before Task 5's E2E suite is ever run — unlike the
single-use diagnostic grant the elevated test needs fresh each time, a durable approval is reusable
across repeated ordinary captures against the same workspace, matching Plan 9.96 Task 9's own runbook
shape (Step 1 authors durable approval once via TTY; Step 2's ordinary capture then runs
non-interactively). Document this prerequisite explicitly in this step and in Task 7's evidence
report; the E2E test itself does not attempt to author it.

**Unlike the elevated test, the ordinary test drives the capture subprocess directly** (no
`optimus-trust run --elevated-debug` ceremony — ordinary mode passes no diagnostic grant, so
`_cmd_run`'s grant/session binding is not involved), which means pytest CAN generate the freshness
nonce and pass it in the same invocation it launches, then assert it — no two-stage split is needed
here. Generate `nonce = f"run_{secrets.token_hex(12)}"` in the test, then drive the session via
`tools/run_plan996_acpx_security_evidence.py capture --workspace C:/tmp/optimus-plan998-evidence
--output-dir C:/tmp/optimus-plan998-artifacts/ordinary --mode ordinary --evidence-run-nonce <nonce>
--drive-session` as a real subprocess (the fixture file itself created by this test, immediately
before the capture command, per Task 3 Step 1), with the underlying `optimus-agent` invocation still
passing `--debug-trace` (per Task 1 Step 3's finding that tags require a present grant *and* the flag
— running ordinary with the flag enabled is the genuine negative control; omitting the flag would
only prove the flag was off, not that ordinary mode itself suppresses tags). Assert, from the
resulting manifest and the immutable snapshot artifacts in `output_dir` (per Task 4 Step 3's
redesign): `manifest["evidence_run_nonce"] == nonce` (freshness), `session_mode == "ordinary"`,
`tool_names` non-empty and matching the expected tool for this fixed task, `tool_call_count > 0`,
`0 < total_cost_usd <= DEFAULT_LIVE_MAX_COST_USD` (or the operator's `OPTIMUS_LIVE_MAX_COST_USD`
override), `stop_reason == "end_turn"`, the `final_agent_state` field (if Task 1 Step 5 confirmed one
exists) matches its expected successful value, `elevated_tag_present is False`, and — per Task 1 Step
4's pinned source — the **first record** of the `audit-snapshot.ndjson` (the outer, evidence-tool
audit entry, selected by document order, never by matching the desired result) has its
`child_propagation_decisions.agent_child` naming exactly the 5 registry-authorized names:
`OPTIMUS_AGENT_MODEL`, `OPTIMUS_API_KEY`, `OPTIMUS_GATEWAY_URL`, `OPTIMUS_PRODUCTION_MODE`,
`OPTIMUS_REDIS_URL`. Also run the tool's own `verify` subcommand against the produced
manifest/snapshots and assert it exits 0. **Do not assert a manifest field for the pre-approval
mutation proof** — that proof is its own separate, independently-run test against a genuinely
UNAPPROVED workspace (see Task 4 Step 3's redesign): a distinct fresh workspace (not
`C:/tmp/optimus-plan998-evidence`), confirm no durable record exists for it, run one unapproved
capture attempt, assert `NO_APPROVAL` rejection, recompute and compare the fixture digest.

- [ ] **Step 3: Add the real elevated-session E2E test — consume operator-produced artifacts at a fixed, discoverable root; don't invent a grant/session pairing from pytest**

`optimus-trust run --elevated-debug -- <target argv>` creates the diagnostic grant itself and
substitutes the **literal placeholder tokens** `{approval_id}`, `{launch_session_id}`, and
`{diagnostic_grant_id}` into the target argv it spawns (`launch_approval_cli.py:6`, `:371-426`) — the
caller must write those exact curly-brace tokens in the command, not a description placeholder. A
pytest process cannot author a valid grant/session pairing on its own (matching Plan 9.96 Task 9's
own established rule that this ceremony requires a real TTY and correctly refuses non-interactive
callers).

**The `{launch_session_id}` placeholder MUST stay literal — do NOT substitute a pytest nonce for it.**
The previous revision proposed replacing `{launch_session_id}` with a pytest-generated value; that is
wrong and would break the elevated path entirely. Confirmed by reading
`launch_approval_cli.py:395,407-426`: `_cmd_run` generates its own `launch_session_id =
f"sess_{secrets.token_hex(12)}"`, signs the diagnostic grant against **that exact value**
(`DiagnosticGrant(..., launch_session_id=launch_session_id, ...)` then `compute_grant_hmac`), and the
`{launch_session_id}` substitution is the *only* channel carrying that value to the child so the
child's `consume_diagnostic_grant(grant_id, launch_session_id)` finds a session match. Substituting an
unrelated pytest nonce for `{launch_session_id}` guarantees `GRANT_SESSION_MISMATCH` → the inner agent
silently downgrades to ordinary → the "elevated" evidence becomes false while tests may still pass.
**Freshness must ride on a SEPARATE anchor, not `launch_session_id`.**

The exact operator-run command — `uv run` prefix on `optimus-trust`, P9.96-FU-6 global-argument order
(`--workspace-root` before the subcommand), fixed external artifact root, `--agent-approval-id
{approval_id}` threaded so the evidence tool resolves the *same* approval record `optimus-trust run`
validated, all three literal `{...}` tokens preserved for `_cmd_run` to substitute, PLUS a new
`--evidence-run-nonce $NONCE` carrying the pytest-generated freshness anchor (an executable variable
read from the marker file, not a `_cmd_run` placeholder — `_cmd_run` only knows
`{approval_id}`/`{launch_session_id}`/`{diagnostic_grant_id}`) — is given in full, once, as Stage B
below. (An earlier revision of this step duplicated the command here as a "preview" separately from
Stage B, which let the two copies drift out of sync — one still carrying a stale
`<NONCE from .evidence-run-nonce, see the two-stage protocol below>` placeholder after the other was
fixed. There is now exactly one copy of this command in the plan, in Stage B.)

**Two-stage ceremony — one pytest invocation cannot generate a nonce, pause for a TTY ceremony, and
resume, so split it exactly as Plan 9.96 Task 9 splits its own Step 2/3.** Provide these exact
commands:

*Stage A (setup, non-interactive):* a helper (`-m e2e`-excluded node or script) both (1) **resets the
elevated fixture file to its pristine pre-edit content immediately before the operator runs the
capture** — otherwise Stage B may see an already-edited fixture and the agent emits no write tool
call, producing empty `tool_names` — and (2) generates `NONCE = f"run_{secrets.token_hex(12)}"`,
writes it to `C:/tmp/optimus-plan998-evidence/.evidence-run-nonce`, and exits. It does NOT run the
capture. Uses the exact, concrete fixture filename and content Task 3 Step 1 pins
(`_SESSION_FIXTURE_FILENAME`, `_SESSION_FIXTURE_PRISTINE_CONTENT`) — no bracket placeholders:

```bash
uv run python -c "import pathlib, secrets; ws=pathlib.Path('C:/tmp/optimus-plan998-evidence'); (ws/'plan998_fixture.py').write_text(\"def status():\n    return 'pending'\n\", encoding='utf-8'); n=f'run_{secrets.token_hex(12)}'; (ws/'.evidence-run-nonce').write_text(n, encoding='utf-8'); print(n)"
```

*Stage B (operator TTY):* the operator reads the nonce from the marker file **into a shell variable**
and runs the elevated command with `--evidence-run-nonce $NONCE` — an executable variable read, not a
manual `<NONCE ...>` paste. **The three `{...}` grant/approval tokens must be SINGLE-QUOTED, not
bare** — in PowerShell, an unquoted `{approval_id}` is parsed as a `[ScriptBlock]` literal, not a
plain string; when PowerShell converts that ScriptBlock to a string for the native `optimus-trust`
executable's argv, `.ToString()` on a ScriptBlock returns only the text *inside* the braces (i.e.
`approval_id`, braces stripped) — so `_cmd_run`'s `arg.replace("{approval_id}", ...)` would find no
`{approval_id}` substring to replace at all, and the literal string `approval_id` would leak straight
through into the real command instead of being substituted. Single-quoting (`'{approval_id}'`) forces
PowerShell to treat it as a literal string — no scriptblock parsing, no variable interpolation — so
the braces survive intact and reach `_cmd_run` as the exact substring it expects:

```powershell
# PowerShell:
$NONCE = Get-Content C:/tmp/optimus-plan998-evidence/.evidence-run-nonce
uv run optimus-trust --workspace-root C:/tmp/optimus-plan998-evidence run --elevated-debug -- uv run python tools/run_plan996_acpx_security_evidence.py capture --workspace C:/tmp/optimus-plan998-evidence --output-dir C:/tmp/optimus-plan998-artifacts/elevated --mode elevated --agent-approval-id '{approval_id}' --launch-session-id '{launch_session_id}' --diagnostic-grant-id '{diagnostic_grant_id}' --evidence-run-nonce $NONCE --drive-session
```

*Stage C (verification, the elevated `-m e2e` node ONLY):* the E2E node reads the SAME marker file,
consumes the artifacts at `C:/tmp/optimus-plan998-artifacts/elevated`, runs the tool's own `verify`
subcommand (asserting exit 0 → HMAC + digest integrity), and asserts `manifest["evidence_run_nonce"]`
**equals the marker-file value** (a stale prior capture carries a different nonce → fails), plus
everything Step 2 asserts, plus `elevated_tag_present is True` and that the allowlisted provenance/tag
content contains no secret material (reuse `_joined_scan`/`verify` — no second scanner). It does NOT
invoke `optimus-trust run --elevated-debug` itself. **It must be run as a single targeted node, never
the whole E2E file** (see Step 4's ordering rule).

- [ ] **Step 4: Run the E2E nodes in a pinned, non-interleaving order — never `-m e2e` over the whole file mid-ceremony**

The three real tests share the fixed workspace, so running the whole `-m e2e` module at once would
let the ordinary test mutate the workspace *after* the elevated capture but *before* elevated
verification, corrupting the elevated evidence. Run discrete, individually-selected nodes in this
exact order, each preceded by its own fixture reset:

```bash
# 1. Unapproved mutation proof — independent, its own fresh unapproved workspace (Task 4 Step 3 redesign):
uv run pytest "tests/e2e/acp/test_plan996_authorized_launch.py::test_unapproved_capture_leaves_fixture_unmutated" -q

# 2. Ordinary: this node resets the ordinary fixture, drives the capture (pytest supplies its own nonce), and verifies — all in one node:
uv run pytest "tests/e2e/acp/test_plan996_authorized_launch.py::test_ordinary_session_evidence" -q

# 3. Elevated Stage A (reset elevated fixture, emit nonce) — repeated verbatim from Step 3 above:
uv run python -c "import pathlib, secrets; ws=pathlib.Path('C:/tmp/optimus-plan998-evidence'); (ws/'plan998_fixture.py').write_text(\"def status():\n    return 'pending'\n\", encoding='utf-8'); n=f'run_{secrets.token_hex(12)}'; (ws/'.evidence-run-nonce').write_text(n, encoding='utf-8'); print(n)"
```

Then, in a PowerShell TTY, the operator runs Stage B verbatim from Step 3 above:

```powershell
$NONCE = Get-Content C:/tmp/optimus-plan998-evidence/.evidence-run-nonce
uv run optimus-trust --workspace-root C:/tmp/optimus-plan998-evidence run --elevated-debug -- uv run python tools/run_plan996_acpx_security_evidence.py capture --workspace C:/tmp/optimus-plan998-evidence --output-dir C:/tmp/optimus-plan998-artifacts/elevated --mode elevated --agent-approval-id '{approval_id}' --launch-session-id '{launch_session_id}' --diagnostic-grant-id '{diagnostic_grant_id}' --evidence-run-nonce $NONCE --drive-session
```

Then, back in the automated runner:

```bash
# 4. Elevated Stage C — the verification node ONLY, not the whole file:
uv run pytest "tests/e2e/acp/test_plan996_authorized_launch.py::test_elevated_session_evidence_verification" -q
```

Expected: each node passes against the real process and real dependencies; the elevated command
substitutes identifiers without printing them; no test's workspace mutation bleeds into another's
window. The durable approval (one-time, Step 2's prerequisite) and the per-run diagnostic grant
(Stage B) are the operator's TTY steps, exactly as in Plan 9.96 Task 9's runbook — schedule these as
interactive, not something the implementing agent runs alone.

---

### Task 6: Full Gate Re-Run and Frozen-Path Verification

**Files:** none (verification only).

- [ ] **Step 1: Run the complete gate set**

```bash
uv run pytest tests/unit/acp tests/unit/security tests/unit/telemetry tests/unit/tools/test_verify_plan996_logging_surfaces.py tests/unit/tools/test_run_plan996_acpx_security_evidence.py tests/e2e/acp/test_plan996_authorized_launch.py -m "not e2e" -q
uv run pytest -q
uv run pytest --cov=optimus --cov=optimus_gateway --cov=optimus_security --cov-branch --cov-report=term-missing --cov-fail-under=80 -q
uv run ruff check .
uv run python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
git diff --check
```

- [ ] **Step 2: Prove the frozen-path constraint held — the full declared list, not a partial one**

The previous revision's command omitted two paths Global Constraint 1 actually declares frozen:
`src/optimus/acp/e2e_transcript.py` (its existing `PLAN_9_6_*` behavior) and
`docs/superpowers/reviews/2026-07-15-plan-9-96-implementation-plan-approval.md` (only the
security-contract approval record was checked, not the separate implementation-plan approval
record). Both are now included below. The check compares against **HEAD** (`git diff --quiet HEAD --
...`), not the unstaged-only form, so a frozen-path change that was already `git add`-ed cannot pass
silently. Since Global Constraint 1 applies "at every commit," this same HEAD comparison runs before
all four commits — the Task 0 planning commit, this implementation commit, and Task 8's evidence/docs
and plan-closure commits:

```bash
git diff --quiet HEAD -- tools/run_plan987_acpx_live_evidence.py tools/run_plan988_fu4b_live_evidence.py src/optimus/acp/operator_verify.py tests/e2e/acp/test_spawned_agent_live.py src/optimus/acp/e2e_transcript.py docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md docs/superpowers/reviews/2026-07-15-plan-9-96-security-contract-approval.md docs/superpowers/reviews/2026-07-15-plan-9-96-implementation-plan-approval.md
git diff --stat HEAD -- src/optimus/acp/__main__.py src/optimus/agent/defaults.py src/optimus/acp/trusted_paths.py src/optimus/acp/subprocess_env.py src/optimus/acp/launch_policy.py src/optimus/acp/errors.py src/optimus/acp/bootstrap.py tools/verify_plan996_logging_surfaces.py
```

Expected: both commands are silent (no diff, no output) — every frozen path and every FU-1..7 file
this plan is forbidden from touching remains byte-unchanged.

- [ ] **Step 3: Commit the implementation — separately from the evidence report, to avoid a commit-identity cycle**

**The evidence report (Task 7) records "the final implementation SHA" and states that Plan 9.96 Task
9 is unblocked by this plan's commit — neither claim can be true if the report is bundled into the
same commit it's describing** (you cannot know a commit's own SHA before creating it, and a single
commit can't truthfully say of itself "this has landed"). Commit the implementation now, separately:

```bash
git status --porcelain --untracked-files=all
git diff -- tools/run_plan996_acpx_security_evidence.py tests/unit/tools/test_run_plan996_acpx_security_evidence.py tests/e2e/acp/test_plan996_authorized_launch.py docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
```

After reviewer and operator approval only:

```bash
git add tools/run_plan996_acpx_security_evidence.py tests/unit/tools/test_run_plan996_acpx_security_evidence.py tests/e2e/acp/test_plan996_authorized_launch.py docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
git diff --cached --check
git commit -m "Add real acpx session-drive capture mode for Plan 9.96 Task 9"
git rev-parse HEAD
```

Record this commit's full 40-character SHA — it is "the final implementation SHA" Task 7's report
cites, mirroring how Plan 9.88 Task 5 split its own capture-baseline commit from the report commit
that references it ("the two SHAs are watched-path-equivalent because this commit changes only the
report; record both roles explicitly").

---

### Task 7: Record This Plan's Evidence and the Plan 9.96 Task 9 Dependency

**Files:**
- Create: `reports/plan-9-98-real-acpx-session-evidence.md`

- [ ] **Step 1: Write the claim-to-evidence report**

Record: this plan's own approval digest (Task 0 Step 1), the foundation SHA, the Task 1 ruling and
its empirical proofs, **the Task 6 Step 3 implementation commit's full SHA** (not a SHA this same
report's own commit will only receive later), exact test node names/commands/results, the real
ordinary and elevated run outcomes (session mode, tool names, cost, stop reason, child-key names, tag
presence/absence, evidence-run nonce, the pre-authorization fixture-digest proof) with artifact
SHA-256s (of the immutable per-capture snapshot files `transcript.stdout`/`.stderr`/
`audit-snapshot.ndjson`/`debug-snapshot.ndjson` — NOT the live `launch-audit.ndjson`/`debug-acp.ndjson`
workspace files, which Task 4 Step 3 deliberately replaced with those snapshots), the manifest HMAC
verification results, the documented one-time durable-approval prerequisite for the ordinary
workspace, coverage, Ruff, and `git diff --check` results. **Final-state handling:** if Task 1 Step 5
found a real distinct `final_agent_state` source, record its outcome; if it did NOT and the resolution
was a reviewed Plan 9.96 parent-contract amendment (per Task 1 Step 5's ruling — this plan cannot
waive that claim by local disclosure), cite that amendment. Do not include secret or workspace
content.

- [ ] **Step 2: State the Plan 9.96 Task 9 dependency explicitly**

Include a clearly labeled section: "Plan 9.96 Task 9 Steps 2, 3, and 5 depend on this plan's
implementation commit `<Task 6 Step 3 SHA>` and were blocked until it landed. Plan 9.96 Task 9 may
now run its own Step 2 commands using `tools/run_plan996_acpx_security_evidence.py capture ...
--drive-session`." This statement is for Plan 9.96's own Task 9 evidence report to cite later; it
does not itself edit Plan 9.96's plan file.

---

### Task 8: Roadmap/README Entry and Operator-Gated Docs Commit

**Files:**
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Modify: `README.md`
- (Task 7's `reports/plan-9-98-real-acpx-session-evidence.md` is committed here too — it was
  created, not committed, in Task 7.)

- [ ] **Step 1: Add the Plan 9.98 roadmap section**

Add a `## Plan 9.98 (Implemented): Real ACPX Session Evidence for Plan 9.96 Task 9` section citing
the Task 6 Step 3 implementation SHA, this plan's own foundation anchor, and the explicit Task 9
dependency. Add one sentence to the existing Plan 9.96 section noting that Task 9 Steps 2/3/5
depend on Plan 9.98's evidence report.

- [ ] **Step 2: Add the README planning-status paragraph**

One sentence, mirroring the pattern used for every other plan.

- [ ] **Step 3: Commit the evidence report + roadmap + README — the THIRD commit; the plan file is NOT in it**

This commit deliberately does **not** include the Plan 9.98 plan file, to avoid the self-reference
Codex identified: a commit cannot include the plan file with "Step 3 done" ticked before Step 3's own
commit exists, and cannot leave it unticked without a dirty tree. The plan file's accumulated
checkbox ticks are committed separately in Step 4. This is a docs-only commit (Global Constraint 9:
frozen-path HEAD gate + `git diff --cached --check` only).

```bash
git diff --quiet HEAD -- tools/run_plan987_acpx_live_evidence.py tools/run_plan988_fu4b_live_evidence.py src/optimus/acp/operator_verify.py tests/e2e/acp/test_spawned_agent_live.py src/optimus/acp/e2e_transcript.py docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md docs/superpowers/reviews/2026-07-15-plan-9-96-security-contract-approval.md docs/superpowers/reviews/2026-07-15-plan-9-96-implementation-plan-approval.md
git status --porcelain --untracked-files=all
git diff -- reports/plan-9-98-real-acpx-session-evidence.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md README.md
```

After both reviewer and operator approval only:

```bash
git add reports/plan-9-98-real-acpx-session-evidence.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md README.md
git diff --cached --check
git commit -m "Record Plan 9.98 real acpx session evidence"
git rev-parse HEAD
```

- [ ] **Step 4: Persist the checkbox-updated plan file — the FOURTH (plan-closure) commit; resolves the self-reference**

Every substantive step through Step 3 is now genuinely complete, so every task-step and Definition-of-
Done checkbox except this closing action can be ticked truthfully. Tick them all now (including a tick
for this Step 4 as it is performed — the single irreducible self-reference every plan's final action
carries), then mechanically prove ONLY checkboxes changed versus the pinned planning commit and commit
the plan file alone:

```bash
# Find the Task 0 Step 2 planning commit mechanically — it is, by construction, the commit that
# FIRST added this plan file to history (nothing earlier in this plan's lineage commits it), so no
# manually-carried-forward SHA is needed:
PLANNING_SHA=$(git log --diff-filter=A --follow --format=%H -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md | tail -1)
echo "Planning commit: $PLANNING_SHA"
# Prove the plan file changed only in checkbox characters vs that approved planning commit:
git diff "$PLANNING_SHA" -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md | grep '^[+-]' | grep -v '^[+-]\{3\}' | grep -vE '^\+- \[x\]' | grep -vE '^-- \[ \]'
```

That pipeline must print **nothing** — every changed line is a `- [ ]` → `- [x]` flip. If it prints
any line, substantive text drifted and the plan needs re-approval + a new pinned digest before
closure. Then, after approval:

```bash
git diff --quiet HEAD -- tools/run_plan987_acpx_live_evidence.py tools/run_plan988_fu4b_live_evidence.py src/optimus/acp/operator_verify.py tests/e2e/acp/test_spawned_agent_live.py src/optimus/acp/e2e_transcript.py docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md docs/superpowers/reviews/2026-07-15-plan-9-96-security-contract-approval.md docs/superpowers/reviews/2026-07-15-plan-9-96-implementation-plan-approval.md
git add docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md
git diff --cached --check
git commit -m "Close Plan 9.98: mark all steps complete (checkbox-only)"
git rev-parse HEAD
git status --porcelain --untracked-files=all   # clean tree — no dangling checkbox drift
```

The final `git status` must show a clean tree (modulo the disclosed `.claude/`/`.zed/`/etc. noise).
Never stage `.idea/`, `.kiro/`, `.zed/`, `.air/`, `uv.lock`, or any FROZEN file from Global Constraint
1 (the Plan 9.98 plan file is committed here for its checkbox-only diff, which is not a
frozen-content change — the one deliberate exception).

## Definition of Done

- [ ] This plan's own digest is pinned exactly once, over the pristine plan (Task 0 Step 1) — not
  re-verified against a live, checkbox-mutated file at every later step — and both the plan file and
  its approval record are committed in their own docs-only planning commit (Task 0 Step 2) **while
  still entirely `- [ ]`, including Steps 1 and 2's own checkboxes**, which are ticked only after that
  commit lands, before Task 1 begins.
- [ ] Task 1's grant-consumption-topology ruling is empirically proven using the keyring store's own
  `consume_diagnostic_grant` calls and debug-trace tag presence as the observable oracles — never
  `optimus-agent`'s own exit behavior, which silently swallows every `ApprovalError` code identically
  and cannot report `GRANT_NOT_FOUND` to an outside observer. Every direct `optimus-agent` invocation
  in the probe runs in a terminating mode (`--check-config --no-auto-start`) with bounded,
  `stdin=DEVNULL` execution — never bare, never inheriting the probe's own TTY. Both proof scenarios
  are self-cleaning (each ends in a real successful `consume_diagnostic_grant` that deletes the entry);
  every scenario is ALSO wrapped in `try/finally` with an unconditional raw
  `keyring_backend.delete_password` fallback attempt, followed by a `get_password(...) is None`
  assertion verifying the OUTCOME, not just that the delete call didn't raise — a bare
  catch-and-ignore around `delete_password` would let a genuine keyring failure masquerade as "already
  clean" and silently leave residue while the probe reports success. `TTL expiry is NOT a passive
  cleanup mechanism` (nothing removes an untouched entry on its own; `DIAGNOSTIC_TTL_SECONDS` only
  governs what a *future* consume attempt does), so the `finally` fallback and its outcome check are
  both required unconditionally, never optional or "TTL will handle it."
- [ ] `acpx --format json ... exec`'s real output shape is pinned by an actual run (Task 1 Step 5),
  inspected ephemerally with no raw discovery artifact retained, before Task 4's parser or Task 5's
  source-level test is written against it. The same investigation determines whether a real, distinct
  `final_agent_state` domain signal exists (in acpx output, the real Redis agent state store, or the
  sanitized transcript). If none exists, this plan CANNOT waive Plan 9.96's separately-enumerated
  "final state" claim by local disclosure — the only valid resolutions are a reviewed amendment to
  Plan 9.96's own contract or another independent final-state source; this is a live risk that can
  block the plan pending a parent-contract decision.
- [ ] `acpx`'s real permission-granting mechanism for file-write tool calls (e.g. `--approve-all` or
  an empirically confirmed equivalent) is pinned in the correct command layer — the outer `acpx`
  argv, never folded into the `--agent` invocation string — and included in the real invocation; a
  chosen task string alone does not guarantee a tool call happens.
- [ ] A RED test demonstrating the committed `acpx --version` path's manifest cannot satisfy Step 2's
  session assertions exists (a genuine `AssertionError` against the current manifest schema, not an
  import error or a trivially-true statement about the old output), is committed, and stays green as
  a permanent regression pin against the default (non-`--drive-session`) behavior.
- [ ] The new capture mode constructs `[acpx, "--format", "json", "--cwd", ..., "--agent", ...,
  "exec", ...]` as an argument list, `shell=False`, with no stdin PIPE-feeding, via a pure, extracted
  `_build_capture_command()` whose `agent_invocation` parameter is `Optional` — the frozen `--version`
  path never needs it, and `main()` only resolves `optimus-agent` (a new prerequisite) when
  `--drive-session` is actually set, never unconditionally; the `--version` smoke's real-world
  prerequisites (only `acpx` on PATH) stay exactly as committed today, proven by Test 2c's `shutil.which`
  spy over a real default-path `main()` invocation, not just the pure builder's own (structurally
  incapable of catching this) test. It uses a distinct
  real-session deadline (a separate ~600 s `_DRIVE_SESSION_WAIT_TIMEOUT_SECONDS` plus a test bound
  injected via a DIRECT function parameter / hidden CLI arg — never an environment override, which
  would add an unregistered inherited-env dependency conflicting with the frozen registry scope — NOT
  the 30 s `--version` smoke timeout, which would kill a legitimate Gateway turn; the smoke's own 30 s
  stays unchanged). The reader-thread-join-before-process-wait ordering is fixed with a bounded,
  fail-closed timeout that terminates the ENTIRE process tree using stdlib/OS built-ins only (POSIX
  `start_new_session=True` + `os.killpg`; Windows `CREATE_NEW_PROCESS_GROUP` + `taskkill /F /T` —
  never `psutil`, which is not a project dependency), with those creation flags applied ONLY on the
  `--drive-session` path so the `--version` smoke's spawn is byte-unchanged. It is proven by a
  subprocess-isolated RED test (not a same-process test, which cannot be safely terminated) whose stub
  spawns a sleeping DESCENDANT as well as a parent so tree-kill (not just immediate-child kill) is
  what the test verifies, and whose harness cleanup independently group-kills BOTH its own process
  group AND the separately-recorded acpx-stub-child's own group — because once the fix's own
  `start_new_session`/`CREATE_NEW_PROCESS_GROUP` is active, the child is detached into a NEW group the
  harness's own group-kill alone cannot reach — asserting neither the probe, the acpx-stub-child, nor
  the descendant PID survives before the test returns, in both the pre-fix and post-fix process-group
  topology. A nonzero `CaptureResult.exit_code` —
  independent of the timeout path — also blocks manifest promotion; neither a hung nor a failed real
  session can produce a manifest that looks like verified, successful evidence.
- [ ] The diagnostic grant is consumed exactly once, by the process Task 1 determined is
  authoritative for elevated diagnostics — never by both the outer evidence tool and the inner
  agent.
- [ ] Every new manifest field is content-free (no raw secret, no full environment, no raw prompt or
  file content), including `tool_names`/`tool_call_count` (consistent everywhere this plan references
  them); a `final_agent_state` field only if Task 1 Step 5 proved a real distinct source (otherwise
  handled per the parent-contract ruling above, never fabricated) — and if that source is OUTSIDE the
  transcript (e.g. Redis), it is produced by a separate typed final-state collector with its own
  content-free snapshot, digest, and test, NOT by the stdout parser (which cannot reach it); and
  `evidence_run_nonce`, whose caller-supplied value is grammar-validated (`^run_[0-9a-f]{24}$`) and
  rejected pre-authorization on any mismatch, because it is written verbatim into the HMAC-signed
  manifest bypassing the sanitizer and "content-free" must be enforced, not merely asserted. The
  pre-authorization mutation proof is deliberately NOT a manifest field (a self-asserted boolean there
  would be unverifiable) — it is its own independently-runnable E2E test against a genuinely
  UNAPPROVED, separate workspace (not the fixed evidence workspace, which is approved).
  `child_key_names`/`elevated_tag_present` are sourced from new, immutable, per-capture snapshot files
  inside `output_dir`, extracted from each log file's pre-launch-offset SUFFIX (never the live shared
  append-only originals, and never selected by `launch_session_id` — which both audit entries share —
  nor by correlation tag, which ordinary runs lack; the outer audit entry is the FIRST record of the
  audit snapshot by document order). The offset boundary's single-writer assumption is enforced: the
  controlled workspace runs one capture at a time, and the tool mechanically validates the suffix at
  snapshot time (every audit record carries this run's `launch_session_id`; exactly the expected
  record count; all debug records share one `sessionId`), failing closed on any foreign writer. Those
  snapshots get the same digest-in-manifest and joined-scan coverage as `transcript.stdout`/`.stderr`
  today.
- [ ] Real ordinary and real elevated sessions both run through independently-authored `acpx`
  0.12.0+, driving the real Optimus agent, real Redis, and real Gateway credentials, against the SAME
  fixed, externally pre-approved workspace (a documented one-time durable-approval prerequisite for
  ordinary; the elevated command additionally carries a fresh single-use diagnostic grant), and both
  are asserted for mode, tools (by name, not just count), cost band, final agent state (if defined),
  terminal state (`end_turn`), zero pre-approval mutation, exact child-key manifest (the first
  audit-snapshot record), ordinary no-tags behavior, and elevated allowlisted provenance/tags — the
  elevated E2E test consumes artifacts from a fixed, discoverable root produced by an operator-run TTY
  command with the correct `uv run` prefix, corrected global argument order, all three literal
  `{approval_id}`/`{launch_session_id}`/`{diagnostic_grant_id}` substitution tokens PRESERVED (the
  `{launch_session_id}` placeholder is load-bearing for diagnostic-grant binding — `_cmd_run` signs
  the grant against its own generated value, so substituting a pytest nonce for it would guarantee
  `GRANT_SESSION_MISMATCH` and a false-elevated downgrade), and a SEPARATE `--evidence-run-nonce`
  value as the freshness anchor, communicated to pytest via a marker file in a two-stage
  setup/TTY/verify ceremony — HMAC validity and a matching workspace digest alone do not prove an
  artifact is fresh rather than a replayed prior capture. The three real tests share one workspace, so
  each runs as its own individually-selected node in a pinned order, each preceded by its own fixture
  reset (the elevated Stage A resets the fixture and emits the nonce immediately before the operator's
  TTY command, which reads the nonce via an executable shell variable) — the whole `-m e2e` module is
  never run at once, so no test's workspace mutation bleeds into another's verification window.
- [ ] The source-level no-protocol-reimplementation test uses AST inspection of each import's original
  (un-aliased) name/module for the forbidden project client (not a substring match an alias or
  reformatting could dodge) plus THREE behavioral tests: one reusing the committed real-fixture
  pattern (`authorize_capture` → `append_authorized_audit` → `spawn_authorized_capture`) to assert
  `stdin=subprocess.DEVNULL` and `returncode == 0` against a real stand-in child; one calling Task 3
  Step 3's extracted pure `_build_capture_command()` directly to assert it places a SUPPLIED resolved
  path at `command[0]` by EXACT equality (not `name.startswith("acpx")` against a Python stand-in,
  which can never hold, and not a claim that the function itself resolves anything — it doesn't); and
  one spying on every name `shutil.which` is queried with over a real `main()` invocation on the
  default (no `--drive-session`) path — using the FULLY STUBBED SUCCESSFUL-path pattern the committed
  `test_main_generates_launch_session_id_when_absent` establishes (`authorize_capture` and every
  downstream step stubbed to succeed), not an unapproved-workspace rejection, which exits before
  command construction and would let the assertion pass vacuously without ever reaching the code
  that could contain the bug — asserting `optimus-agent` is never among the queried names. This is
  the one that actually catches a `main()`-level regression the pure builder test structurally cannot
  reach. None of the three ban a protocol field-name substring a compliant parser might legitimately
  read
  from real `acpx` output.
- [ ] No FU-1/2/3/4/5/7 file is touched; Plan 9.96's plan file, security contract, both approval
  records, `src/optimus/acp/e2e_transcript.py`'s existing behavior, and both frozen Plan 9.87/9.88
  helpers remain byte-unchanged; `operator_verify.py` and `test_spawned_agent_live.py` remain
  byte-unchanged — checked against the FULL declared list from Global Constraint 1, before EVERY
  commit (planning, implementation, evidence/docs, and plan-closure), not a partial list checked once.
- [ ] Full default test suite passes, aggregate coverage across `optimus`/`optimus_gateway`/
  `optimus_security` is at least 80%, Ruff is clean, the logging-surface verifier is green, and
  `git diff --check` is clean.
- [ ] Every `uv` command in this plan's verification steps was run from a terminal with `uv` actually
  on PATH; no checkbox reflects a substitute computation.
- [ ] FOUR separate operator-approved commits: (1) the Task 0 docs-only planning commit (plan +
  approval record, pristine); (2) the Task 6 implementation commit; (3) the Task 8 Step 3 evidence/docs
  commit (evidence report + roadmap + README), which cites the implementation commit's already-landed
  SHA, never its own, and does NOT include the plan file; (4) the Task 8 Step 4 plan-closure commit,
  which persists the plan file's checkbox-only diff — mechanically proven to contain no
  substantive-text change vs the pinned planning commit — resolving the self-reference of a plan file
  that would otherwise have to record its own not-yet-existing closing commit.
- [ ] This plan's evidence report explicitly states that Plan 9.96 Task 9 Steps 2/3/5 depended on
  this plan's implementation commit and were blocked until it landed.
- [ ] Final `git status` is a clean tree (modulo disclosed tool-config noise) — no dangling
  uncommitted plan-file checkbox drift; the plan file and its approval record are tracked in
  repository history from Task 0 Step 2 onward, never left untracked through to closure.

## Implementation Handoff After Plan Approval

Unlike sibling plans that require a fresh branch, this plan is intended to execute as an addition on
the same worktree/branch that already holds Plan 9.96 Tasks 0-8 (`agent/kiro/plan-9-96`), because
Plan 9.96 Task 9 cannot proceed without this plan's capability and this plan touches no frozen Plan
9.96 bytes. If the operator prefers a separate branch/PR for this plan's commits ahead of Plan 9.96
Task 9 resuming, that is a valid alternative — raise it as an explicit choice at kickoff rather than
assuming either way. Re-open the exact on-disk foundation state (Task 0) before any other step. Use
`superpowers:executing-plans` plus `superpowers:test-driven-development`.
