# Plan 9.98 Real ACPX Session Evidence for Plan 9.96 Task 9 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILLS: Use `superpowers:executing-plans` to execute this
> plan task-by-task and `superpowers:test-driven-development` for every behavior change. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft for reviewer-agent and operator review. **This line is retained from the pristine
v1 bytes approved in Task 0 and is never updated to say "Approved" after the fact, mirroring Plan
9.96's own frozen "Draft" header. Approval status is determined only by the digest-pinned approval
records and their matching committed plan blobs, never by this sentence or by the live,
checkbox-mutated working file.** The v1 approval record
`docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md` remains the immutable
historical approval for the pristine plan blob committed at `424940e`. The empirical Task 1 finding
required a substantive agile revision, so **no work after Task 1 Step 1 may proceed until Task 0A
commits these revised bytes together with
`docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md`, whose recorded
digest matches the revised plan blob in that amendment commit.** After that commit, later checkbox
ticks do not invalidate v2 approval. The Task 2 RED investigation exposed a TDD sequencing defect in
incomplete Tasks 3 and 4, so **no Task 3 work may proceed until Task 2A commits the v3 revised bytes
together with `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v3.md`,
whose recorded digest matches that committed v3 plan blob.** Any later substantive change requires
another reviewed, digest-pinned amendment.

The fresh Task 1 session investigation established that ACP stdout has no cost/usage surface while the
same completed run has a real, run-ID-keyed Redis `AgentPlanRecord.cost_usd`. Therefore **no Task 2A
Step 7, Task 3 Step 2, or Task 4 work may proceed until Task 2B commits the v4 revised bytes together
with `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v4.md`, whose
recorded digest matches that committed v4 plan blob.** This is a Plan 9.98 evidence-collection change,
not a reinterpretation or amendment of frozen Plan 9.96.

The completed Task 1 investigation also established a bounded structural completion inference, but
the incomplete Task 4/5/7 and Definition-of-Done wording still assumed only a distinct domain-state
field or a parent-plan amendment. Therefore **no Task 4 Step 2 or later work may proceed until Task
2C commits the v5 revised bytes together with
`docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v5.md`, whose recorded
digest matches that committed v5 plan blob.** This v5 correction preserves the frozen Plan 9.96
contract: for this plan's fixed normal ACP path only, it records the independently observable proof of
`COMPLETED`; it does not treat `end_turn` alone as final-state evidence or generalize the inference.

The first real Task 4 Step 2 driven capture then exposed a two-tier launch-boundary defect in this
plan's own helper: the outer evidence tool computed the correct post-default five-name effective
agent mapping, but passed that mapping to `acpx`; `acpx` inherited it and in turn passed it to the
inner `optimus-agent`, whose own gate correctly reclassified the now-literal values as inherited
launch settings. That made the inner security snapshot differ from the operator-approved clean-shell
snapshot and fail with `SNAPSHOT_MISMATCH`. Therefore **no Task 4 Step 2 or later work may resume
until Task 2D commits the v6 revised bytes together with
`docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v6.md`, whose recorded
digest matches that committed v6 plan blob.** V6 preserves Plan 9.96's core digest semantics and the
already-approved five-name `agent_child` audit claim. It separates the ACPX client's minimal
transport environment from the effective inner-agent mapping, makes the inner agent resolve its own
defaults and keyring credential in the normal production shape, and proves the correction with RED
tests plus a real controlled session.

**Goal:** Give `tools/run_plan996_acpx_security_evidence.py` the ability to drive one real,
independently-authored-`acpx` ordinary session and one real elevated session against the actual
Optimus agent, and prove Plan 9.96 Task 9 Step 2's required properties (mode, tools, cost band,
terminal state/`end_turn`, zero pre-approval mutation, exact child-key manifest, ordinary absence of
an elevated comparison record, elevated run-scoped allowlisted provenance/comparison evidence, and
zero-or-more sanitized correlation tags) from that real evidence — without editing Plan
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

Plan 9.98 is necessary but, after the v6 audit, not by itself sufficient for Plan 9.96 closure:
Task 7's distinct URI-userinfo digest/display conformance finding is owned by Plan 9.99 and must also
land before Plan 9.96 closes. That separate prerequisite does not block implementing or collecting
Plan 9.98's real-session evidence.

**Foundation:** Plan 9.96 Tasks 0-8 as committed on branch `agent/kiro/plan-9-96` at HEAD `d0c4670`
("Sanitize ACP evidence before persistence") and the reviewer's independent verification recorded in
`docs/superpowers/reviews/plan-9-96-review-checkpoints.md`. That proven code and its committed test
suite — not a prior plan document — are this lane's dependency contract, mirroring how Plan 9.96
itself anchored to the Plan 9.9 implementation commit rather than a plan file.

**Architecture:** Extend the already-reviewed Task 8 capture tool with a second capture mode that
constructs `[acpx, "--format", "json", "--cwd", <workspace>, "--agent", <agent invocation>, "exec",
<task>]` as an argument list (never a shell string), reusing the already-approved Task 8 pipeline:
`authorize_capture`/`append_authorized_audit`/`spawn_authorized_capture`
for the gated launch of the `acpx` process itself, `_stream_sanitized`/`StreamingTextSanitizer` for
persistence, `_joined_scan` for promotion-gating, and the HMAC-signed evidence manifest for the
claim-to-evidence trail. The spawn boundary has two explicit roles: the outer `acpx` client receives
only the sanctioned system-key allowlist from the one-time snapshot, while the separately computed
post-default effective-agent mapping remains available for audit and the run-bound Redis collector
but is never inherited by `acpx`. The inner `optimus-agent` therefore starts from the same clean
pre-default environment the operator approved and resolves its own loopback defaults/keyring secret.
The genuinely new work is (a) resolving what "agent invocation" means for
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
The v6 environment-boundary correction is a moderate, self-contained addition: one amendment review,
six RED/GREEN tests, a narrow tool-only implementation, and the mandatory real-session rerun.

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
- `src/optimus/acp/debug_trace.py:19,24,78,160-181` — elevated-diagnostics evidence lives at
  `.optimus/debug-acp.ndjson` under the workspace root. A diagnostic grant causes exactly one
  `launch_authorization_comparison` record at the single `__main__.py:352` call site; an ordinary
  launch with no grant emits none. Its `correlation_tags` array contains zero or more values produced
  by `optimus_security.sanitization.session_correlation_tag`. The array is legitimately empty when
  the shared secret was resolved from keyring/`.env.gateway`, because that secret is fingerprinted as
  `_resolved_shared_secret` but is not present in the inherited-environment `secret_inventory` the
  tag loop examines. Task 1's run-scoped record count — not tag-array cardinality — is therefore the
  elevated oracle.
- `src/optimus/acp/launch_audit.py` / the settled ruling that `runtime_root` = `workspace/.optimus` —
  the workspace's own `launch-audit.ndjson` carries `child_propagation_decisions.agent_child`
  (child-key names, never values) for whichever process's gate wrote it; Task 1 must determine which
  entry (the outer evidence tool's, or the inner `optimus-agent`'s) is authoritative for the "exact
  child-key manifest" assertion.
- `src/optimus/acp/launch_gate.py:441-529,614-624` and
  `src/optimus/acp/local_infra.py:47,77-90` — the gate classifies literal inherited launch settings
  before computing the security snapshot, while `apply_local_defaults()` later adds loopback/default
  values (including the keyring-resolved shared secret under `OPTIMUS_API_KEY`) to the effective agent
  mapping. Passing that post-default mapping through `acpx` makes those values literal inherited
  settings for the nested gate. The real failing capture and a content-free synthetic reproduction
  proved post-default nesting changes the digest while clean pre-default nesting preserves it. There
  is no duplicate-entry bug to patch in the core: the two gates were given genuinely different
  inherited inputs.

Apart from the separately owned Plan 9.99 URI-canonicalization finding recorded in Tasks 7-8, no
other conflict is presently known. If implementation finds one among this plan, Plan 9.96's
committed code, or live `acpx`/agent behavior, stop and request a reviewed amendment to **this**
plan; do not reinterpret either plan's contract in code.

## Global Constraints

1. **Frozen paths, byte-unchanged, `git diff --quiet` gated at every commit:**
   `tools/run_plan987_acpx_live_evidence.py`, `tools/run_plan988_fu4b_live_evidence.py`,
   `src/optimus/acp/operator_verify.py`, `tests/e2e/acp/test_spawned_agent_live.py`,
   `src/optimus/acp/e2e_transcript.py`'s existing `PLAN_9_6_*` constants and writer behavior, and
   Plan 9.96's own plan file, security-contract spec, and both approval records. Every landed Plan
   9.98 approval record is immutable: v1 after Task 0, v2 after Task 0A, v3 after Task 2A, v4
   after Task 2B, v5 after Task 2C, and v6 after Task 2D. This plan reads all of the above for
   precedent only.
2. **No FU-1/2/3/4/5/7 source changes.** Per the 2026-07-18 checkpoint-log ruling, those follow-ups
   are disclosed-and-backlogged by Plan 9.96 Task 9, not fixed. This plan must not touch
   `src/optimus/acp/__main__.py`, `src/optimus/agent/defaults.py`,
   `tools/verify_plan996_logging_surfaces.py`, `src/optimus/acp/trusted_paths.py`,
   `src/optimus/acp/subprocess_env.py`, `src/optimus/acp/launch_policy.py` (read-only citation of the
   existing `DEFAULT_LIVE_MAX_COST_USD` constant is fine; no edits), `src/optimus/acp/errors.py`, or
   `src/optimus/acp/bootstrap.py` for any reason. If evidence work seems to require touching one of
   these, stop and report — do not fold an FU fix into this plan's diff.
3. **Single sanctioned diagnostic-grant consumption per real elevated launch.** The grant is
   consumed exactly once, by whichever process's gate decision the elevated run-scoped comparison
   record actually depends on. Task 1 determines and empirically proves which one;
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
   For **docs-only** commits (the Task 0 planning commit, the Task 0A v2 amendment commit, the Task 2A v3 amendment commit, the Task 2B v4 amendment commit, the Task 2C v5 amendment commit, the Task 2D v6 amendment commit, and the Task 8
   evidence/docs commit, and the Task 8 plan-closure commit — none of which change Python or the
   logging-surface inventory): the full-frozen-path `git diff --quiet HEAD` gate plus `git diff
   --cached --check` only; the test/Ruff/surface-verifier gates are vacuous for a Markdown-only change
   and are deliberately not required there. Every commit runs the frozen-path HEAD gate regardless.
10. **Do not "fix" the nested launch by changing Plan 9.96 core digest/default semantics.**
    `src/optimus/acp/launch_gate.py`, `src/optimus/acp/local_infra.py`,
    `src/optimus/acp/local_gateway_secrets.py`, and `src/optimus/acp/launch_audit.py` are read-only for
    this plan. The v6 correction lives only in this plan's evidence tool and tests. The effective
    five-name agent mapping remains the `agent_child` audit source and Redis-URL source; a distinct
    `acpx_client` audit role is additive and lists only classified/non-system launch-setting names
    actually given to ACPX (expected empty in the approved ceremony). Platform bootstrap keys from
    `_SYSTEM_ENV_KEYS` are transport plumbing, not launch-setting audit names.

---

## File and Responsibility Map

- Create: `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md` — this
  plan's own digest-pinned approval record (Task 0 Step 1), before any other step.
- Create: `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md` — the
  digest-pinned two-signature approval record for this agile revision (Task 0A). The original record
  and `424940e` plan blob stay untouched as the v1 historical baseline.
- Create: `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v3.md` — the
  digest-pinned two-signature approval record for the Task 2A TDD-sequencing amendment. The v1 and
  v2 records, and their committed plan blobs, remain immutable history.
- Create: `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v4.md` — the
  digest-pinned two-signature approval record for Task 2B's Redis-backed cost-evidence amendment. The
  v1/v2/v3 records, and their committed plan blobs, remain immutable history.
- Create: `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v5.md` — the
  digest-pinned two-signature approval record for Task 2C's bounded-final-state-inference amendment.
  The v1/v2/v3/v4 records, and their committed plan blobs, remain immutable history.
- Create: `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v6.md` — the
  digest-pinned two-signature approval record for Task 2D's ACPX-client/inner-agent
  environment-boundary amendment. The v1/v2/v3/v4/v5 records and their committed plan blobs remain
  immutable history.
- Modify: `tools/run_plan996_acpx_security_evidence.py` — add the `exec`-mode command construction,
  agent-invocation resolution, session-result parsing, the grammar-validated `--evidence-run-nonce`
  argument, the distinct real-session deadline + drive-session-only process-tree termination, the
  per-run immutable audit/debug snapshots plus the generalized external-session-evidence snapshot
  (including the run-ID-keyed Redis cost reduction), fail-closed single-writer suffix validation, the
  nonzero-exit/timeout promotion block, the explicit effective-agent versus ACPX-client environment
  split with additive audit roles, and the new content-free manifest fields.
- Modify: `tests/unit/tools/test_run_plan996_acpx_security_evidence.py` — RED capability-gap test,
  new-mode unit tests, nonce-grammar rejection tests, subprocess-isolated non-terminating-child
  tree-kill timeout test, nonzero-exit promotion-block test, foreign-writer suffix-validation test,
  AST + behavioral source-level no-protocol-reimplementation tests, environment-role/digest-parity
  tests, manifest field tamper tests.
- Modify: `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` — classify any
  new persistence/export sink this plan's code introduces (same discipline as Plan 9.96 Task 7/8).
- Create: `tests/e2e/acp/test_plan996_authorized_launch.py` — the real ordinary/elevated E2E node
  Plan 9.96 Task 9 Step 2 requires, including the pre-authorization mutation proof.
- Create: `reports/plan-9-98-real-acpx-session-evidence.md` — this plan's own claim-to-evidence
  report, citing the Task 6 implementation commit SHA and the explicit Plan 9.96 Task 9 dependency
  statement. **Committed in the Task 8 Step 3 evidence/docs commit, separately from the
  implementation, never in the same commit as the SHA it cites.**
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` — add Plan 9.98 and tracked Plan
  9.99 sections; note both prerequisites in the existing Plan 9.96 section.
- Modify: `README.md` — one-sentence planning-status paragraph, mirroring the pattern used for every
  other plan.
- Modify: `docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md` itself — first
  committed pristine in Task 0; substantively revised in Task 0A, Task 2A, Task 2B, Task 2C, and
  Task 2D, each with a new digest and approval record; then re-committed with only its accumulated
  post-v6 `- [ ]`→`- [x]` ticks in
  Task 8 Step 4.
- Note the nine commits this plan produces: (1) Task 0 v1 planning (plan + v1 approval record), (2)
  Task 0A agile amendment (revised plan + v2 approval record), (3) Task 2A TDD-sequencing amendment
  (revised plan + v3 approval record), (4) Task 2B Redis-cost-evidence amendment (revised plan + v4
  approval record), (5) Task 2C bounded-final-state-inference amendment (revised plan + v5 approval
  record), (6) Task 2D ACPX-client/inner-agent environment-boundary amendment (revised plan + v6
  approval record), (7) Task 6 implementation, (8) Task 8 Step 3 evidence/docs (report + roadmap +
  README, no plan file), (9) Task 8 Step 4 plan-closure (plan-file checkbox diff only versus the v6
  amendment commit).
- Do not modify: anything listed under Global Constraint 1, or any FU-1/2/3/4/5/7 file listed under
  Global Constraint 2.

---

### Task 0: Foundation, Approval, and Conflict-Check Gate

**Files:** Create `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md`
(the approval record). Commit this file and the plan file itself as their own docs-only "planning
commit" before Task 1 begins — see Step 2.

- [x] **Step 1: Pin this plan's own approval identity ONCE, over the pristine (unchecked) plan — checkbox ticks afterward do not invalidate it**

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

- [x] **Step 2: Commit the approved plan and its approval record — the contract must exist in repository history before implementation starts**

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

- [x] **Step 3: Verify the exact foundation state before any further mutation**

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

- [x] **Step 4: Confirm no FU-1/2/3/4/5/7 file has drifted since the checkpoint-log ruling**

```bash
git -C . diff --stat HEAD -- src/optimus/acp/__main__.py src/optimus/agent/defaults.py src/optimus/acp/trusted_paths.py src/optimus/acp/subprocess_env.py src/optimus/acp/launch_policy.py src/optimus/acp/errors.py src/optimus/acp/bootstrap.py tools/verify_plan996_logging_surfaces.py
```

Expected: no output (nothing staged/modified). This plan's diff must never touch these files.

---

### Task 0A: Agile Revision and V2 Approval Gate (required before Task 1 Step 2)

Task 1 Step 1 was completed under the approved v1 contract and exposed a real conflict between the
planned non-empty correlation-tag oracle and the committed source/live artifact. That completed investigation is
preserved. This task revises only incomplete or directly affected contract text; it does not rewrite
the v1 approval record or the immutable plan baseline at commit `424940e`.

**Files:**
- Modify: `docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md`
- Create: `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md`

- [x] **Step 1: Prove the revision is grounded in the immutable v1 baseline and confined to the affected incomplete work**

Use `424940e` instead of a stash: it is already the immutable, digest-pinned v1 plan in repository
history and cannot accidentally entangle the unrelated `.claude/` or `uv.lock` working-tree state.
Review the complete plan delta and perform the stale-terminology sweep:

```bash
git diff 424940e -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md
rg -n "elevated_(tag)_present|contains an allowlisted.*session_correlation_(tag)|(?i:tag (presence|absence))|ordinary no[- ]tags" docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md
```

The first command may show the already-valid Task 0 and Task 1 Step 1 checkbox ticks, this Task 0A
approval machinery, and the affected incomplete oracle/manifest/E2E/DoD/commit-accounting text. It
must not silently rewrite the completed Task 0 or Task 1 Step 1 procedures. The second command must
print nothing; any remaining `session_correlation_tag` reference elsewhere in the document must say
explicitly that tags are zero-or-more sanitized metadata and are not the elevated oracle.

- [x] **Step 2: Obtain reviewer-agent and operator approval of the exact revised bytes, then compute the v2 digest with the literal required command**

The reviewer independently checks the full diff against `424940e`, the terminology sweep, and the
frozen Plan 9.96 Task 9 wording. The record-presence design satisfies the parent's "elevated
allowlisted provenance/tags" intent as follows: the run-scoped allowlisted
`launch_authorization_comparison` record proves the inner gate activated elevated diagnostics;
`correlation_tags` remains a zero-or-more, allowlisted/sanitized field within that record; and an
empty array is the required honest result when no eligible inherited secret can be tagged. The plan
must never manufacture a tag merely to make the array non-empty.

After both reviewer-agent and operator approve these exact revised bytes, run this literal command
in a terminal where `uv` is genuinely on PATH — no substitute hashing command:

```bash
uv run python -c "from pathlib import Path; import hashlib; p=Path('docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md'); print(hashlib.sha256(p.read_bytes()).hexdigest().upper())"
```

Create `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md` with the
same two-signature shape as v1: the exact digest, date, Codex reviewer approval, operator approval,
the v1 baseline commit `424940e`, and a statement that the digest covers the exact revised plan bytes
committed with this record. Leave the original v1 approval record untouched.

**Do not tick Steps 1, 2, or 3 before the amendment commit lands.** Ticking any of them would change
the bytes after approval and before the commit intended to pin them. The revised approval snapshot
truthfully includes the Task 0 and Task 1 Step 1 checkboxes already completed under v1, while every
Task 0A checkbox remains unchecked.

- [x] **Step 3: Commit the revised plan and v2 approval record as their own docs-only amendment commit**

Before staging, verify the original record and every parent frozen path are unchanged, and inspect
the complete working tree so unrelated state cannot enter the commit:

```bash
git diff --quiet HEAD -- tools/run_plan987_acpx_live_evidence.py tools/run_plan988_fu4b_live_evidence.py src/optimus/acp/operator_verify.py tests/e2e/acp/test_spawned_agent_live.py src/optimus/acp/e2e_transcript.py docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md docs/superpowers/reviews/2026-07-15-plan-9-96-security-contract-approval.md docs/superpowers/reviews/2026-07-15-plan-9-96-implementation-plan-approval.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md
git status --porcelain --untracked-files=all
git diff 424940e -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md
cat docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md
```

After reviewer and operator approval only:

```bash
git add docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md
git diff --cached -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md
git diff --cached --check
git commit -m "Amend Plan 9.98 elevated evidence oracle"
git rev-parse HEAD
```

Immediately after that commit exists, while the working plan still byte-matches the committed v2
blob, rerun Step 2's literal `uv run python ...` digest command and confirm the result equals the v2
record. Only then tick Steps 1, 2, and 3 in the working tree. They remain ordinary checkbox tracking
to be persisted by the final closure commit.

- [x] **Step 4: Verify the committed v2 identity, then resume at Task 1 Step 2**

Mechanically locate the amendment commit by the commit that first added the v2 approval record. Also
verify neither approval record drifted in the working tree and that the live plan differs from the
v2 committed blob only by the Task 0A checkbox ticks just authorized in Step 3. Record the amendment
SHA in the execution notes. Only then may Task 1 Step 2 continue.

```bash
AMENDED_PLANNING_SHA=$(git log --diff-filter=A --format=%H -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md | tail -1)
echo "V2 amendment commit: $AMENDED_PLANNING_SHA"
git diff --quiet -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md
git diff "$AMENDED_PLANNING_SHA" -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md | grep '^[+-]' | grep -v '^[+-]\{3\}' | grep -vE '^\+- \[x\]' | grep -vE '^-- \[ \]'
```

The last two commands must print nothing.

---

### Task 1: Resolve and Pin the Composite Launch Topology (required before any capture-path code)

This is the one substantive open design question. Do not skip or assume; the wrong answer here
silently mislabels an ordinary session as elevated evidence, exactly the "wrong-mode evidence"
failure class Plan 9.96 has repeatedly guarded against elsewhere.

**Files:** none yet (investigation and a short written ruling; code changes start at Task 2/3).

- [x] **Step 1: Establish the ruling in writing, grounded in the cited source**

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

This completed Step 1 establishes only which process owns the elevated diagnostic decision. Task 1
Step 2's empirical correction controls the observable oracle: `correlation_tags` is zero-or-more
allowlisted/sanitized metadata and may be empty; the current-run comparison-record count proves
ordinary versus elevated.

Write this ruling down verbatim in the plan execution notes before Step 2, so it is falsifiable
rather than assumed.

- [x] **Step 2: Empirically prove the failure mode and the fix — using the store API plus the run-scoped comparison-record count, never `optimus-agent`'s exit behavior**

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
2. **The count of `launch_authorization_comparison` records appended by this specific run to
   `.optimus/debug-acp.ndjson`** as the *indirect* signal that `optimus-agent` actually received a
   diagnostic grant and turned on elevated diagnostics (per Step 3 below, this requires
   `--debug-trace`). The single call site is unconditional when a debug log path exists, while
   `log_authorized_launch_comparison` early-returns only when `diagnostic_grant is None`: exactly one
   current-run record means elevated; zero means ordinary. Scope the count by the pre-invocation file
   offset and validate the appended suffix's single process-local `sessionId`; never ask whether the
   shared append-only file contains such a record anywhere in its history.

**Do not use non-empty `correlation_tags` as the oracle.** The empirical artifact and source trace
proved that keyring/`.env.gateway` credentials are structurally invisible to the tag loop:
`launch_gate.py:442-529` populates `secret_inventory` only from raw inherited `os.environ`, while the
resolved shared secret enters only `secret_fingerprints["_resolved_shared_secret"]` at lines 590-595;
`debug_trace.py:167-181` iterates only `secret_inventory ∩ inherited.values`. A genuine elevated
record can therefore contain `"correlation_tags": []`. That is valid zero-or-more allowlisted
metadata, not evidence of downgrade.

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
downgraded) and that the debug file's current-run suffix contains **zero**
`launch_authorization_comparison` records, proving the downgrade happened even though nothing
printed it.

(b) **Inner-consumes case (the fix):** with a freshly written, unconsumed grant (same fixed session
ID), run the identical bounded `optimus-agent --check-config --no-auto-start` invocation *first* —
confirm the debug file's current-run suffix contains **exactly one**
`launch_authorization_comparison` record (proving elevated diagnostics turned on, which is only
possible if the grant was actually consumed). Accept `correlation_tags: []`; validate that the field
is an array containing zero or more allowlisted/sanitized values rather than requiring a fabricated
non-empty tag.
Then call `store.consume_diagnostic_grant(grant_id, session_id)` directly in the probe — confirm it
now raises `ApprovalError(code="GRANT_NOT_FOUND")`, proving the grant was consumed exactly once by
`optimus-agent` itself and not left over for a second, redundant consumption.

Record both runs' observed outcomes (the direct-store results, the run-scoped comparison-record
counts, each record's zero-or-more sanitized `correlation_tags`, and the `optimus-agent` exit codes)
as this task's evidence; do not proceed on code-reading alone. The already-observed artifact at
`C:/tmp/optimus-plan998-task1-topology-probe/.optimus/debug-acp.ndjson` produced zero comparison
records for outer-consumes-first and exactly one record with `correlation_tags: []` for each
inner-consumes run; preserve that empirical ruling in the evidence report.

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

- [x] **Step 3: Pin the exact agent-invocation construction, including debug tracing**

Determine how `acpx --agent` expects its value (a single shell-parsed string vs. an argv list — check
`acpx --help`/`acpx exec --help` directly, do not assume from the frozen Plan 9.87 helper's string
form). Construct it as `optimus-agent --workspace-root <workspace> --launch-session-id <id>
--debug-trace [--diagnostic-grant-id <id>]` (omit `--launch-approval-id` for the durable-approval
path, matching Plan 9.96's own settled ruling that `authorize_launch` takes the durable path when
`approval_id is None`). **`--debug-trace` is required, not optional:** it is the only path that
creates `.optimus/debug-acp.ndjson` at all (`__main__.py:99-111`, `_apply_debug_trace_args` returns
early when `args.debug_trace` is falsy) — without it, the comparison record cannot be observed
regardless of grant handling. Note also (`debug_trace.py:160-164`,
`log_authorized_launch_comparison`): record emission requires **both** `--debug-trace` enabled and a
present diagnostic grant — `context.enabled` alone with no grant emits nothing. This means the Task
5 ordinary negative control must run **with `--debug-trace` also enabled** (not simply omit the flag),
so zero current-run comparison records proves the absence of a grant, not merely the absence of the
flag. The elevated positive control requires exactly one current-run record; its
`correlation_tags` array may contain zero or more allowlisted/sanitized values. Whatever form `acpx`
requires, the *outer* `Popen` invocation of `acpx` itself remains
`shell=False` with an explicit argument list; only investigate whether the `--agent` value itself
needs internal quoting for `acpx`'s own parser.

- [x] **Step 4: Pin the "exact child-key manifest" evidence source — use the outer (evidence tool's own) audit entry**

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

**V6 boundary clarification, additive to this completed ruling:** the outer event's five-name
`agent_child` tuple remains authoritative for the *effective agent configuration* this evidence tool
computed and for Task 9's exact child-key claim. It is not the environment handed to the intermediary
ACPX client. V6 adds `child_propagation_decisions.acpx_client` to that same outer record, containing
only classified/non-system launch-setting names actually passed to ACPX (expected `[]`); system
bootstrap keys are intentionally outside both name manifests. ACPX receives the system-only mapping,
and the inner `optimus-agent` resolves the same five effective values itself. Thus the existing first-
record/five-name assertion is preserved rather than reinterpreted, while the actual nested process no
longer inherits a post-default snapshot the operator never approved.

- [x] **Step 5: Pin the real `acpx --format json` output shape before specifying any parser — inspect ephemerally, retain only content-free schema notes**

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

**Task 1 resolution, recorded by the reviewed v5 amendment:** no real, named distinct domain-state
signal was found. The normal ACP path for this plan's fixed write-fixture task nevertheless has a
bounded, independently observable completion proof: `stop_reason == "end_turn"`,
`tool_call_count > 0`, and `tool_names` contains `"write_file"`. The source-level construction proof
pins that conjunction to `AgentRunStatus.COMPLETED`; the pre-execution terminal cases that also
produce `end_turn` cannot produce any tool call. Task 4 therefore sets `final_agent_state` to
`"COMPLETED"` only when all three predicates hold. It omits the field when they do not, rather than
fabricating a value or treating `end_turn` alone as proof. This inference is limited to the normal ACP
path without `completion_condition` and this fixed fixture task; it is neither a general completion
rule nor a parent-plan amendment.

- [x] **Step 6: Report findings before Task 2 begins**

Show the ruling, the two empirical proofs (Step 2), the pinned invocation string (Step 3), the pinned
audit-entry source (Step 4), and the pinned real output shape (Step 5) to the reviewer. Do not start
Task 2 until this is acknowledged.

---

### Task 2: RED — Prove the Committed `acpx --version` Path Cannot Satisfy Step 2

**Files:**
- Modify: `tests/unit/tools/test_run_plan996_acpx_security_evidence.py`

- [x] **Step 1: Add a failing capability-gap test that genuinely fails as an assertion, not an import error or a trivial pass**

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

- [x] **Step 2: Run and confirm RED**

```bash
uv run pytest tests/unit/tools/test_run_plan996_acpx_security_evidence.py -k capability_gap -v
```

Expected: FAIL, with a failure message that names the missing capability (no session-result parser,
no `exec`-mode command construction), not an import error or fixture typo.

---

### Task 2A: TDD-Sequencing V3 Amendment and RED Gates (required before Task 3)

Task 2 proved the committed capability gap. Before any Task 3 or Task 4 production behavior is
introduced, this task corrects the plan's deferred-test sequencing without waiving TDD. Task 3 Step
1's three fixture constants are explicitly inert data declarations; they create no runtime behavior
and may remain the first Task 3 step. Every builder, CLI, parser, manifest, snapshot, timeout, or
promotion behavior requires an observed RED test first.

**Files:**
- Modify: `docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md`
- Create: `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v3.md`
- Modify: `tests/unit/tools/test_run_plan996_acpx_security_evidence.py` (Steps 5 and 7 only; it is
  deliberately not staged in the docs-only v3 amendment commit)

- [x] **Step 1: Prove the v3 amendment is confined to the TDD sequencing, named interfaces, and affected accounting**

Use the Task 0A commit `1749747b46aff42d9c487ba62bc1bf38dcf29155` as the immutable v2 baseline.
The complete diff may include the completed Task 0/0A/1/2 checkbox ticks, this Task 2A approval
machinery, Task 3/4's RED-before-GREEN sequencing, one explicit agent-invocation builder interface,
v3 frozen-record/closure references, and six-commit accounting. It must not alter completed Task 0,
Task 0A, Task 1, or Task 2 procedures, nor any production/security contract.

```bash
git diff 1749747b46aff42d9c487ba62bc1bf38dcf29155 -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md
rg -n "Task 3 Step [0-9]|Task 4 Step [0-9]|five commits|FIFTH|v2 amendment commit|approval-v2" docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md
```

- [x] **Step 2: Obtain reviewer-agent and operator approval of the exact v3 bytes, then compute the v3 digest literally**

The reviewer must independently inspect the full diff against `1749747`, check every Task 3/4
interface and ordering reference, confirm Task 2A is the only new gate, and verify that the v1/v2
records remain untouched. After both approvals, run this exact command in a terminal where `uv` is on
`PATH`:

```bash
uv run python -c "from pathlib import Path; import hashlib; p=Path('docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md'); print(hashlib.sha256(p.read_bytes()).hexdigest().upper())"
```

Create the v3 record with the exact digest, both approvals, the v2 amendment commit `1749747`, and a
statement that it approves these exact revised bytes. Do not tick Task 2A Steps 1-4 until the
docs-only amendment commit has landed; the approved snapshot includes the already-complete Task 0,
Task 0A, Task 1, and Task 2 checkboxes, but every Task 2A checkbox remains unchecked.

- [x] **Step 3: Commit the exact v3 plan and v3 approval record as a docs-only amendment**

Before staging, prove all frozen paths and both earlier approval records are byte-unchanged, and
inspect the complete worktree so the Task 2 RED test, `uv.lock`, `.claude/`, and the checkpoint log
cannot enter this commit. After reviewer and operator approval only, stage exactly the plan and v3
record, show the staged diff, run `git diff --cached --check`, and commit with:

```bash
git commit -m "Amend Plan 9.98 TDD sequencing"
```

Immediately rerun Step 2's literal digest command against the committed v3 blob, confirm it matches
the v3 record, then tick only Steps 1-3 in the working plan.

- [x] **Step 4: Verify the v3 identity and frozen baseline before writing any new production behavior**

Mechanically locate the commit that first added the v3 record; verify all three approval records are
unchanged and the live plan differs from that v3 blob only by permitted checkbox ticks. Only then may
the RED-test steps below and Task 3 begin.

```bash
V3_AMENDMENT_SHA=$(git log --diff-filter=A --format=%H -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v3.md | tail -1)
git diff --quiet -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v3.md
git diff "$V3_AMENDMENT_SHA" -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md | grep '^[+-]' | grep -v '^[+-]\{3\}' | grep -vE '^\+- \[x\]' | grep -vE '^-- \[ \]'
```

- [x] **Step 5: Write Task 3's construction and CLI RED tests against pinned interfaces**

Before Task 3 Step 2, add tests for the inert fixture constants and these two pure interfaces:
`_build_agent_invocation(*, optimus_agent: str, workspace: Path, launch_session_id: str,
diagnostic_grant_id: str | None) -> str` and `_build_capture_command(*, acpx: str, workspace: Path,
agent_invocation: str | None, drive_session: bool) -> list[str]`. Assert the former emits only the
Task 1-pinned `optimus-agent` arguments (including optional diagnostic-grant id, never
`--approve-all`); assert the latter returns the untouched default `[acpx, "--version"]` or the exact
outer `acpx --format json --approve-all --cwd ... --agent ... exec SESSION_TASK` argv. Also add RED
tests that default-mode `main()` never resolves `optimus-agent`, drive-session mode fails closed when
that executable is absent, every malformed/oversized/secret-shaped nonce is rejected before
`authorize_capture`, and an elevated drive-session passes the grant only to the inner agent invocation
without outer consumption.

- [x] **Step 6: Run and confirm the Task 3 construction/CLI tests are RED**

```bash
uv run pytest tests/unit/tools/test_run_plan996_acpx_security_evidence.py -k "agent_invocation or build_capture_command or evidence_run_nonce or default_path_never_resolves" -v
```

Expected: FAIL because the named builders, drive-session CLI path, and nonce validation do not yet
exist; failure must not be repaired by adding production code before this command is observed.

- [x] **Step 7: Write Task 4's parser, external-evidence collector, and manifest/snapshot RED tests against pinned interfaces**

Before Task 4 Step 1 and Step 3, add content-free synthetic sanitized-transcript tests for
`_parse_session_result(transcript: str) -> SessionResultEvidence`, where the immutable result exposes
`session_id`, `prompt_request_id`, the derived `run_id`, `stop_reason`, `tool_names`, and derived
`tool_call_count`. The fixture must use only Task 1's observed JSON-RPC shape: the `session/new`
result supplies `sessionId`, the `session/prompt` request supplies its JSON-RPC id, the terminal
response supplies `result.stopReason`, and completed `session/update` records with
`params.update.sessionUpdate == "tool_call"` supply `params.update.title`. Add RED unit tests for the
single generalized outside-transcript collector: it receives this parsed `run_id`, reads the pinned
source exactly once, reduces its response to content-free evidence only, writes a sanitized snapshot,
and fails closed on an absent/mismatched record. For cost, the fake state-store assertion must prove it
calls `latest_plan_for_run(run_id=parsed.run_id)` and returns only `total_cost_usd`, never plan text,
gateway request IDs, provider/model details, or any other record field. Add RED manifest/snapshot
tests for the new session fields, Redis-cost snapshot, offset-derived audit/debug snapshots, HMAC
tampering, ordinary zero versus elevated exactly-one comparison records, valid empty tags, malformed
tags, foreign audit writers, multiple debug `sessionId`s, and nonzero child exit blocking promotion.
These are the fail-closed tests previously deferred to Task 4 Step 4; they are now the required RED
foundation, not post-implementation coverage.

- [x] **Step 8: Run and confirm the Task 4 parser and manifest/snapshot tests are RED**

```bash
uv run pytest tests/unit/tools/test_run_plan996_acpx_security_evidence.py -k "session_result or manifest or snapshot or comparison_record" -v
```

Expected: FAIL because the parser, run-ID-derived external-evidence collector, session fields, and
snapshot pipeline do not yet exist. Preserve the Task 2 capability-gap test as the separate permanent
pin for the default path.

---

+### Task 2B: Redis-Cost-Evidence V4 Amendment Gate (required before Task 2A Step 7)

The fresh real ACP session proves that stdout is raw ACP JSON-RPC and has no cost/usage record. The
same session's transcript supplies `session_id` and prompt request id, which derive the exact
`run_id`; a read-only live lookup of `RedisAgentStateStore.latest_plan_for_run(run_id=...)` returned
that completed run's positive `AgentPlanRecord.cost_usd`. This task corrects the Plan 9.98-only
transcript-cost assumption. It does not amend or reinterpret Plan 9.96: its cost-band requirement is
still met from a real dependency, now using the same run rather than an unavailable ACP field.

**Files:**
- Modify: `docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md`
- Create: `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v4.md`

- [x] **Step 1: Prove the v4 amendment is limited to the unified external-evidence collector and affected accounting**

Use `4e009380c54b56ec8f93bd8f9e06ae61de193864` as the immutable v3 baseline. The diff may add this
Task 2B gate; the v4 record; Redis-cost collector/test/snapshot instructions; the explicit Step 1
parser-to-collector ordering; all-four-record frozen checks; and seven-commit accounting. It must not
alter any completed procedure, Plan 9.96 frozen file, prior approval record, or the settled
`stopReason` + write-file completion rule.

```bash
git diff 4e009380c54b56ec8f93bd8f9e06ae61de193864 -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md
rg -n "total_cost_usd.*transcript|final-state-snapshot|three Plan|all three|six commits|SIX |SIXTH|v3 amendment commit|approval-v3" docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md
```

- [x] **Step 2: Obtain reviewer-agent and operator approval of the exact v4 bytes, then compute the v4 digest literally**

The reviewer independently checks the full diff against `4e00938`, the single-collector design,
parser-before-collector ordering, sanctioned Redis URL path, the stale-reference sweep, and all
v1/v2/v3 records. After both approvals, run this exact command in a terminal where `uv` is on `PATH`:

```bash
uv run python -c "from pathlib import Path; import hashlib; p=Path('docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md'); print(hashlib.sha256(p.read_bytes()).hexdigest().upper())"
```

Create the v4 record with that exact digest, both approvals, the v3 amendment commit `4e00938`, and a
statement approving these exact revised bytes. Do not tick Task 2B Steps 1-4 until the docs-only
amendment commit lands.

- [x] **Step 3: Commit the exact v4 plan and v4 approval record as a docs-only amendment**

Before staging, prove every frozen path and the v1/v2/v3 approval records are byte-unchanged; inspect
the complete worktree so the existing RED tests, `uv.lock`, `.claude/`, and reviewer checkpoint log
cannot enter this commit. After approval, stage exactly the plan and v4 record, show the staged diff,
run `git diff --cached --check`, and commit with:

```bash
git commit -m "Amend Plan 9.98 Redis cost evidence"
```

Immediately rerun Step 2's literal digest command against the committed v4 blob, confirm it matches
the v4 record, then tick only Steps 1-3 in the working plan.

- [x] **Step 4: Verify the v4 identity and frozen baseline before Task 2A Step 7**

Locate the commit that first added the v4 record; verify all four approval records are unchanged and
the live plan differs from that v4 blob only by permitted checkbox ticks. Only then may Task 2A Step 7
write the external-evidence RED tests or any Task 3 Step 2/Task 4 behavior begin.

```bash
V4_AMENDMENT_SHA=$(git log --diff-filter=A --format=%H -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v4.md | tail -1)
git diff --quiet -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v3.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v4.md
git diff "$V4_AMENDMENT_SHA" -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md | grep '^[+-]' | grep -v '^[+-]\{3\}' | grep -vE '^\+- \[x\]' | grep -vE '^-- \[ \]'
```

---

### Task 2C: Bounded-Final-State-Inference V5 Amendment Gate (required before Task 4 Step 2 resumes)

Task 1 Step 5 proved that the fixed normal ACP path reaches `AgentRunStatus.COMPLETED` when, and
only when for this evidence fixture, the already-captured facts satisfy all three predicates:
`stop_reason == "end_turn"`, `tool_call_count > 0`, and `"write_file" in tool_names`. This is a
bounded inference from independent observable evidence, not a new persisted/transcribed field and
not a general rule that `end_turn` alone means completion. The v4 plan still has six affected
locations that only anticipate a real distinct signal or a Plan 9.96 parent-contract amendment. This
task corrects those locations and the resulting approval/commit accounting without modifying Plan
9.96 or any completed empirical procedure.

**Files:**
- Modify: `docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md`
- Create: `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v5.md`

- [x] **Step 1: Prove the v5 amendment is limited to the settled bounded inference and affected accounting**

Use `3e04c29fe09b4ec038fa851e24ac187ea9071ba2` as the immutable v4 baseline. The complete diff may
add this Task 2C gate; the v5 record; the explicit three-predicate `COMPLETED` rule and its
fixed-path boundary; the six affected Task 1/4/5/7/DoD references plus the downstream E2E DoD wording;
v5 frozen-record references; and eight-commit accounting. It must not alter the Task 1 empirical
facts, any Plan 9.96 frozen path, a prior approval record, an existing RED/GREEN test, or production
code.

```bash
git diff 3e04c29fe09b4ec038fa851e24ac187ea9071ba2 -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md
rg -n -i "final.?agent.?state|final agent state|real distinct.*state|parent-contract|parent contract|all four Plan 9.98|seven commits|SIXTH|SEVENTH|v4 amendment commit|approval-v4" docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md
```

Every final-state hit must either state the exact three-predicate, fixed-normal-ACP-path rule or be a
legitimate historical v4 citation in the Task 2B procedure. In particular, no later requirement may
say that `end_turn` alone proves completion, require a distinct signal, or demand a Plan 9.96
amendment. A manifest sets `final_agent_state` to `"COMPLETED"` only when all three predicates hold;
when they do not, it omits the field rather than fabricating a value or reclassifying the run.

- [x] **Step 2: Obtain reviewer-agent and operator approval of the exact v5 bytes, then compute the v5 digest literally**

The reviewer independently checks the full diff against `3e04c29`, the six final-state locations and
the downstream E2E DoD wording, all commit/frozen-record accounting, the absence of changes to the
settled Task 1 findings, and every v1/v2/v3/v4 record. After both approvals, run this exact command
in a terminal where `uv` is on `PATH`:

```bash
uv run python -c "from pathlib import Path; import hashlib; p=Path('docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md'); print(hashlib.sha256(p.read_bytes()).hexdigest().upper())"
```

Create the v5 record with that exact digest, both approvals, the v4 amendment commit `3e04c29`, and a
statement approving these exact revised bytes. Do not tick Task 2C Steps 1-4 until the docs-only
amendment commit lands.

- [x] **Step 3: Commit the exact v5 plan and v5 approval record as a docs-only amendment**

Before staging, prove every frozen path and the v1/v2/v3/v4 approval records are byte-unchanged;
inspect the complete worktree so the existing implementation changes, `uv.lock`, `.claude/`, and the
reviewer checkpoint log cannot enter this commit. After approval, stage exactly the plan and v5
record, show the staged diff, run `git diff --cached --check`, and commit with:

```bash
git commit -m "Amend Plan 9.98 bounded final-state evidence"
```

Immediately rerun Step 2's literal digest command against the committed v5 blob, confirm it matches
the v5 record, then tick only Steps 1-3 in the working plan.

- [x] **Step 4: Verify the v5 identity and frozen baseline before Task 4 Step 2 resumes**

Locate the commit that first added the v5 record; verify all five approval records are unchanged and
the live plan differs from that v5 blob only by permitted checkbox ticks. Only then may Task 4 Step 2
resume its collector/digest integration or any later Task 4 behavior begin.

```bash
V5_AMENDMENT_SHA=$(git log --diff-filter=A --format=%H -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v5.md | tail -1)
git diff --quiet -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v3.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v4.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v5.md
git diff "$V5_AMENDMENT_SHA" -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md | grep '^[+-]' | grep -v '^[+-]\{3\}' | grep -vE '^\+- \[x\]' | grep -vE '^-- \[ \]'
```

---

### Task 2D: ACPX-Client/Inner-Agent Environment-Boundary V6 Amendment Gate (required before Task 4 Step 2 resumes)

The first real driven capture proved that Plan 9.98's helper handed the wrong *role's* environment
to ACPX. `CaptureLaunch.agent_environ` is a correct post-default description of the effective agent
configuration and must remain the source of the outer audit's exact five-name `agent_child` claim
and the run-bound Redis URL. It is not, however, the correct environment for the intermediary ACPX
client. ACPX clones its own inherited environment into the `optimus-agent` child; forwarding the
post-default mapping therefore makes the inner gate observe literal settings the clean operator
shell never contained. The inner gate correctly rejects that changed snapshot. V6 separates the two
roles inside the Plan 9.98 evidence helper and leaves Plan 9.96's gate, defaults, audit schema type,
security contract, and frozen plan untouched.

**Files:**
- Modify: `docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md`
- Create: `docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v6.md`

- [ ] **Step 1: Prove the v6 amendment is limited to the environment-role correction and affected accounting**

Use `5f7dcb379e1a76a0950eccd0f3ba5c99cddf4c64` as the immutable v5 baseline. The complete plan diff
may contain the already-earned post-v5 checkbox ticks plus: this Task 2D gate and v6 record; the
Task 3A RED-before-GREEN environment split; additive `acpx_client` audit semantics that leave
`agent_child` intact; the intentional narrowing of the default `--version` child's environment
without changing its argv, dependency resolution, timeout, stdin, or process-group behavior; the
real `SNAPSHOT_MISMATCH` regression gate; all v6 frozen-record/commit/closure accounting; and the
separately owned URI-canonicalization roadmap observation. It must not change any production code,
test, prior approval record, completed empirical procedure, Plan 9.96 frozen path, or the five-name
`agent_child` expected set.

```bash
git diff 5f7dcb379e1a76a0950eccd0f3ba5c99cddf4c64 -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md
rg -n "SNAPSHOT_MISMATCH|acpx_client|agent_child|agent_environ|--version.*unchanged|byte-unchanged|eight commits|EIGHTH|SEVENTH|v5 amendment commit|approval-v5" docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md
```

Every remaining hit must be role-accurate or a legitimate historical v5 procedure. In particular:
`agent_child` still means the post-default effective five-name mapping; `acpx_client` means only
classified/non-system launch-setting names actually given to ACPX and is empty for the approved
clean-shell ceremony; `_SYSTEM_ENV_KEYS` remain unlisted transport plumbing; and no downstream text
may claim the default smoke's whole environment or spawn call is byte-unchanged after v6.

- [ ] **Step 2: Obtain reviewer-agent and operator approval of the exact v6 bytes, then compute the v6 digest literally**

The reviewer independently checks the full diff against `5f7dcb3`, all environment-role/audit/E2E
references, the RED-before-GREEN sequence, the real-session regression gate, all commit/frozen-record
accounting, the unchanged five-name set, and the byte identity of every v1-v5 record. After both
approvals, run this exact command in a terminal where `uv` is genuinely on `PATH`:

```bash
uv run python -c "from pathlib import Path; import hashlib; p=Path('docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md'); print(hashlib.sha256(p.read_bytes()).hexdigest().upper())"
```

Create the v6 record with that exact digest, both approvals, the v5 amendment commit `5f7dcb3`, and a
statement approving these exact revised bytes. Do not tick Task 2D Steps 1-4 until the docs-only
amendment commit lands.

- [ ] **Step 3: Commit the exact v6 plan and v6 approval record as a docs-only amendment**

Before staging, prove every frozen/core read-only path and every v1-v5 approval record is
byte-unchanged. Inspect the complete worktree so the existing implementation changes, `uv.lock`,
`.claude/`, and the reviewer checkpoint log cannot enter this commit. Stage exactly the plan and v6
record, show the staged diff, run `git diff --cached --check`, and commit only after both approvals:

```bash
git diff --quiet HEAD -- tools/run_plan987_acpx_live_evidence.py tools/run_plan988_fu4b_live_evidence.py src/optimus/acp/operator_verify.py tests/e2e/acp/test_spawned_agent_live.py src/optimus/acp/e2e_transcript.py docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md docs/superpowers/reviews/2026-07-15-plan-9-96-security-contract-approval.md docs/superpowers/reviews/2026-07-15-plan-9-96-implementation-plan-approval.md src/optimus/acp/launch_gate.py src/optimus/acp/local_infra.py src/optimus/acp/local_gateway_secrets.py src/optimus/acp/launch_audit.py
git diff --quiet -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v3.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v4.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v5.md
git add docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v6.md
git diff --cached --check
git commit -m "Amend Plan 9.98 ACPX environment boundary"
```

Immediately rerun Step 2's literal digest command against the committed v6 blob, confirm it matches
the v6 record, then tick only Steps 1-3 in the working plan.

- [ ] **Step 4: Verify the v6 identity and frozen baseline before writing the new RED tests**

Locate the commit that first added the v6 record; verify all six approval records are unchanged and
the live plan differs from that v6 blob only by permitted checkbox ticks. Only then may Task 3A
begin or Task 4 Step 2 resume.

```bash
V6_AMENDMENT_SHA=$(git log --diff-filter=A --format=%H -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v6.md | tail -1)
git diff --quiet -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v3.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v4.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v5.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v6.md
git diff "$V6_AMENDMENT_SHA" -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md | grep '^[+-]' | grep -v '^[+-]\{3\}' | grep -vE '^\+- \[x\]' | grep -vE '^-- \[ \]'
```

---

### Task 3: Implement the `exec`-Mode Command Construction

**Files:**
- Modify: `tools/run_plan996_acpx_security_evidence.py`
- Modify: `tests/unit/tools/test_run_plan996_acpx_security_evidence.py`

- [x] **Step 1: Add the inert fixed session constants — the fixture file itself remains E2E/operator setup**

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

- [x] **Step 2: Implement `_build_agent_invocation()` resolution — optimus-agent arguments ONLY**

Task 2A Steps 5-6 already established the RED tests for this interface. Define
`_build_agent_invocation(*, optimus_agent: str, workspace: Path, launch_session_id: str,
diagnostic_grant_id: str | None) -> str`; `main()` resolves `shutil.which("optimus-agent")` only when
`--drive-session` is set and fails closed with a value-safe message if it is absent (mirrors the
existing `acpx is None` check at `main():718-721`). Construct the invocation per Task 1 Step 3's
pinned form: `optimus-agent --workspace-root <ws> --launch-session-id <id> --debug-trace
[--diagnostic-grant-id <id>]` and nothing else. **The permission-granting flag (`--approve-all` or
its confirmed equivalent) is an `acpx` flag and belongs to the outer `acpx` argv (Step 3), NOT to
this agent-invocation string** — it is not an `optimus-agent` argument at all. This builder contains
only `optimus-agent`'s own arguments. Never reference the retired `run-optimus-agent.cmd`/`.sh`
wrapper scripts.

- [x] **Step 3: Implement the new capture mode's command construction and a distinct real-session deadline in `main()`**

Task 2A Steps 5-6 already established the RED tests for this behavior. Add an additive CLI flag (e.g. `--drive-session`) that, when present, builds the outer `acpx` argv
`[acpx, "--format", "json", <permission flag from Step 1 if confirmed>, "--cwd", str(args.workspace),
"--agent", agent_invocation, "exec", SESSION_TASK]` instead of `[acpx, "--version"]`. The existing
default (no flag) command shape, dependency resolution, timeout, stdin, and process-group behavior
remain unchanged. Task 3A later deliberately narrows only the child's environment to the sanctioned
system-key allowlist; that v6 security correction is the one explicit exception to the earlier
"completely unchanged" wording. Per Task 1's ruling, `authorize_capture()` must
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
promises not to burden with a new executable dependency — an environment with `acpx` but not yet `optimus-agent`
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
environment. The `--version` smoke's argv, dependency resolution, timeout, stdin, and process-group
behavior must not change; Task 3A intentionally narrows only its inherited environment.

- [x] **Step 4: Fix the capture pipeline's timeout ordering before it can safely run a real, potentially long-running or hung session**

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
   promises the `--version` smoke's process-group behavior is unchanged, and `CREATE_NEW_PROCESS_GROUP` /
   `start_new_session` measurably alter the spawn (signal-handling, console-group membership). Thread
   a flag from `main()` (drive-session true/false) into `spawn_authorized_capture` and set the
   creation flags only when it is true; the `--version` smoke keeps its existing creation flags.
   Its environment is the separate, deliberate Task 3A v6 narrowing. After
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

- [x] **Step 5: Run the Task 2A construction/CLI tests as GREEN regression coverage**

Run the direct command-shape, default-path, nonce-rejection, and no-outer-consumption tests written
in Task 2A Step 5. They must now pass. Any newly discovered Task 3 behavior requires its own failing
test before implementation; do not restore the old tests-after-code sequencing.

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

### Task 3A: Separate the ACPX Client Transport Environment from the Effective Agent Environment

**Files:**
- Modify: `tools/run_plan996_acpx_security_evidence.py`
- Modify: `tests/unit/tools/test_run_plan996_acpx_security_evidence.py`

- [ ] **Step 1: Write all six environment-boundary tests first — no production change yet**

Use the existing content-free `FakeKeyring`/authorized-capture fixtures. Add these exact behavioral
tests before editing the tool:

1. `test_nested_agent_snapshot_uses_clean_predefault_environment` constructs the same candidate
   twice from the same sanctioned clean snapshot and workspace. It proves the current post-default
   effective mapping would change the nested candidate digest, while the proposed system-only ACPX
   client mapping preserves equality. It asserts only names/digest equality, never credential values.
2. `test_capture_launch_builds_system_only_acpx_client_environment` proves `CaptureLaunch` retains
   the post-default `agent_environ` (including the five effective names) but also exposes a distinct
   `acpx_client_environ` containing only non-empty `_SYSTEM_ENV_KEYS` from
   `authorized.candidate.inherited.values`. It must contain no `OPTIMUS_*` key and specifically no
   `OPTIMUS_API_KEY`.
3. `test_drive_session_rejects_inherited_classified_launch_settings_before_audit_or_spawn` is
   parameterized over at least one SECRET setting, one SECURITY setting, and one registered
   non-`OPTIMUS_*` provider key. Authorize the matching dirty snapshot so the test reaches the new
   boundary rather than failing earlier on approval mismatch; spy on `append_authorized_audit` and
   `subprocess.Popen` and prove neither is called. Drive the real `main()` wiring so the test also
   proves `--drive-session` is forwarded into authorization rather than defaulted away. The error may
   expose a stable reason code and setting names, never values.
4. `test_default_version_spawn_uses_system_only_client_environment` drives the authorized default
   path against a real short-lived stand-in and proves the command remains `[acpx, "--version"]`
   while its `env` is the system-only client mapping. It also preserves the existing no-
   `optimus-agent`-resolution, 30-second timeout, DEVNULL-stdin, and no-new-process-group assertions.
5. `test_launch_audit_adds_acpx_client_role_without_changing_agent_child_manifest` proves the first
   outer audit event still has `child_propagation_decisions.agent_child` equal to exactly
   `OPTIMUS_AGENT_MODEL`, `OPTIMUS_API_KEY`, `OPTIMUS_GATEWAY_URL`, `OPTIMUS_PRODUCTION_MODE`, and
   `OPTIMUS_REDIS_URL`; `gateway_child` is unchanged; and the new additive `acpx_client` launch-
   setting-name tuple is empty. The platform system-key allowlist is intentionally not represented
   as launch-setting names.
6. `test_spawn_uses_acpx_client_environment_not_effective_agent_environment` spies on the real
   `Popen` boundary and asserts exact environment identity: the child receives
   `capture.acpx_client_environ`, never a merge with `capture.agent_environ`. Include a sentinel
   effective-agent secret to make a mistaken merge fail visibly without logging its value. This
   replaces/renames the committed `test_spawn_authorized_capture_merges_system_env_keys` expectation;
   do not keep an obsolete test that still requires merging the effective agent mapping into ACPX.

- [ ] **Step 2: Run the six tests and capture genuine RED failures**

```bash
uv run pytest tests/unit/tools/test_run_plan996_acpx_security_evidence.py -k "nested_agent_snapshot or system_only_acpx_client or inherited_classified_launch_settings or default_version_spawn or launch_audit_adds_acpx_client_role or spawn_uses_acpx_client_environment" -v
```

Expected: every new test fails by assertion for the missing role split, fail-closed boundary, or
additive audit field — not on import/collection errors. Record the exact count and failure reasons in
the reviewer checkpoint log before any GREEN change.

- [ ] **Step 3: Implement the minimum role split and fail-closed driven-session precondition**

Keep `CaptureLaunch.agent_environ` as the existing post-default **effective agent** mapping so the
Redis collector and five-name `agent_child` audit claim do not churn. Add
`CaptureLaunch.acpx_client_environ`. Build it once, during `authorize_capture()`, from non-empty
`_SYSTEM_ENV_KEYS` in `authorized.candidate.inherited.values`; never reread `os.environ`, never copy
an `OPTIMUS_*` setting, and never call `apply_local_defaults()` on this mapping.

Make the nested-session constraint explicit in the authorization interface (for example,
`authorize_capture(..., drive_session: bool = False)`). When `drive_session=True`, fail closed before
audit or spawn if `candidate.display_rows` is non-empty. That covers every classified inherited
launch setting, including PARENT_ONLY and registered non-`OPTIMUS_*` provider keys that checking
`candidate.agent_environ` alone would miss. Use a stable value-free error such as
`ACPX_CLIENT_ENV_NOT_CLEAN`; never include a setting value. The approved evidence ceremony is
deliberately narrower than the general product launcher: it requires a clean operator environment
and lets the inner agent independently resolve defaults/keyring credentials. Do not invent a general
secret-forwarding or deduplication rule. Thread the same mode through `main()` and any complete-walk
helper such as `capture_acpx()`; a driven call must never reach authorization with the default
`False` and then independently turn process-group/session behavior on only at spawn time.

Change `spawn_authorized_capture()` to pass `capture.acpx_client_environ` verbatim as `env`. Remove
the merge from `capture.agent_environ`; the system keys are already present in the client mapping.
The default `--version` path uses this same minimal client mapping. This is an intentional security
narrowing of environment only: its argv, executable-resolution prerequisite, timeout, DEVNULL stdin,
and process-group flags remain as already tested.

Extend the existing outer `LaunchAuditEvent.child_propagation_decisions` mapping additively:

```python
{
    "agent_child": tuple(sorted(capture.agent_environ)),       # unchanged exact five
    "gateway_child": tuple(sorted(candidate.gateway_environ)), # unchanged
    "acpx_client": tuple(                                     # classified names only
        sorted(name for name in capture.acpx_client_environ if name not in _SYSTEM_ENV_KEYS)
    ),
}
```

The expected `acpx_client` tuple is empty in the approved ceremony even though the real process also
receives system bootstrap keys. Do not rename/remove `agent_child`, do not put system keys in it, and
do not change `launch_gate.py`, `local_infra.py`, `local_gateway_secrets.py`, or `launch_audit.py`.

- [ ] **Step 4: Run the six RED tests GREEN, then the full unit file and focused Ruff**

```bash
uv run pytest tests/unit/tools/test_run_plan996_acpx_security_evidence.py -k "nested_agent_snapshot or system_only_acpx_client or inherited_classified_launch_settings or default_version_spawn or launch_audit_adds_acpx_client_role or spawn_uses_acpx_client_environment" -v
uv run pytest tests/unit/tools/test_run_plan996_acpx_security_evidence.py -v
uv run ruff check tools/run_plan996_acpx_security_evidence.py tests/unit/tools/test_run_plan996_acpx_security_evidence.py
git diff --check
```

Expected: the six new tests pass; the full file has no new regression. The only still-failing tests,
if any, are explicitly identified pre-existing Task 4 RED tests whose production step remains open.

- [ ] **Step 5: Re-run one real clean-shell driven session and prove the original failure is gone**

This is the non-negotiable regression gate because mocked subprocess tests could not reveal ACPX's
environment cloning. Use the already durable-approved fixed workspace and a terminal where `uv` and
`acpx` are genuinely on `PATH`. The tool itself fails value-safely before audit/spawn if any
classified inherited launch setting is present; do not export `OPTIMUS_API_KEY` or any other
credential into the shell to work around that check. Reset the fixture, generate a fresh nonce and
unique artifact directory, then run:

```powershell
$NONCE = uv run python -c "import secrets; print(f'run_{secrets.token_hex(12)}')"
$OUT = "C:/tmp/optimus-plan998-artifacts/v6-$NONCE"
uv run python -c "from pathlib import Path; p=Path('C:/tmp/optimus-plan998-evidence/plan998_fixture.py'); p.write_text(\"def status():\n    return 'pending'\n\", encoding='utf-8')"
uv run python tools/run_plan996_acpx_security_evidence.py capture --workspace C:/tmp/optimus-plan998-evidence --output-dir $OUT --mode ordinary --evidence-run-nonce $NONCE --drive-session
uv run python tools/run_plan996_acpx_security_evidence.py verify --manifest "$OUT/sanitizer-manifest.json" --artifact-dir $OUT
uv run python -c "import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); e=json.loads((p/'external-session-evidence.json').read_text(encoding='utf-8')); m=json.loads((p/'sanitizer-manifest.json').read_text(encoding='utf-8')); assert e['run_id']; assert float(e['total_cost_usd']) > 0; assert 'external-session-evidence.json' in m['artifact_sha256']" $OUT
```

Expected: capture exits 0; stderr contains no `SNAPSHOT_MISMATCH`; the real inner agent completes;
`external-session-evidence.json` is produced with a run ID and positive cost; its digest is present
in the manifest; joined scan/HMAC verification exits 0. Retain only the already-sanitized controlled
artifacts. Do not retain a new raw diagnostic transcript outside the tool's pipeline.

- [ ] **Step 6: Pause for reviewer verification of code, tests, audit compatibility, and the real artifact**

The reviewer independently verifies: no Plan 9.96 core/frozen path changed; the six tests genuinely
went RED then GREEN; `agent_child` stayed exactly five and `acpx_client` is additive/empty; the ACPX
spawn environment contains only the sanctioned system keys; the inner audit/capture got past the
previous snapshot mismatch; and the external evidence + manifest verification are real. Only after
that checkpoint may Task 4 Step 2 be ticked and Task 4 Step 3 begin.

---

### Task 4: Parse Session Results and Extend the Manifest with Content-Free Evidence

**Files:**
- Modify: `tools/run_plan996_acpx_security_evidence.py`
- Modify: `tests/unit/tools/test_run_plan996_acpx_security_evidence.py`

- [x] **Step 1: Implement the RED-pinned session-result parser against Task 1 Step 5's observed shape**

Task 2A Steps 7-8 already established the RED parser test. Implement
`_parse_session_result(transcript: str) -> SessionResultEvidence` (new code, not reusing the frozen
`run_plan987_acpx_live_evidence.py` module). The immutable result exposes `session_id`,
`prompt_request_id`, `run_id`, `stop_reason`, `tool_names`, and derived `tool_call_count`; it does
**not** invent a cost field ACP never emitted. Parse Task 1's observed raw JSON-RPC shape exactly:
the `session/new` response's `result.sessionId`, the `session/prompt` request's JSON-RPC id, the
terminal response's `result.stopReason`, and each completed `session/update` notification's
`params.update.title` when `params.update.sessionUpdate == "tool_call"`. Derive
`run_id = f"{session_id}:{prompt_request_id}"`, matching `spec.py`'s real construction. This parser
operates on sanitized `transcript.stdout` only; its run identity is the required input to Step 2, so
**Step 2 necessarily runs after Step 1**.

- [ ] **Step 2: Implement the single typed outside-transcript collector after parsing run identity**

This checkbox remains open until Task 3A Step 5's real clean-shell session proves the collector is
actually reached after a successful nested authorization, produces the snapshot, and survives the
manifest's digest/scan/verify path. Passing direct collector tests or merely wiring a call site is
not sufficient.

Use one collector for every independently pinned value unavailable in ACP stdout. It receives Step
1's parsed `run_id`, reads each pinned source exactly once, reduces it to only approved content-free
fields, writes one immutable `external-session-evidence.json` snapshot through
`StreamingTextSanitizer`, and extends the digest/joined-scan tuple so `verify` rechecks it. For the
required cost field, construct `RedisAgentStateStore` from the already authorized, resolved
`CaptureLaunch.agent_environ["OPTIMUS_REDIS_URL"]` — the retained effective-agent mapping, not the
system-only `acpx_client_environ`, and never a new `os.environ` read — then call
`latest_plan_for_run(run_id=parsed.run_id)` exactly once. Fail closed (nonzero exit, quarantine, no
manifest) if it returns `None`, returns a different `run_id`, or has invalid/non-positive cost. Reduce
the Redis record to `total_cost_usd` only; never retain `plan_text`, task text, gateway request IDs,
model/provider details, or any other stored field. The existing final-state source is the settled
Step 1 completion combination, so no separate final-state read is added. The collector's unit tests
must prove source-once behavior, run-ID binding, no ambient Redis URL reread, content-free snapshot,
and every fail-closed branch.

- [ ] **Step 3: Implement the RED-pinned manifest and snapshot extension — cover every Plan 9.96 Task 9 Step 2 claim by name**

Task 2A Steps 7-8 already established the RED manifest/snapshot tests. A bare `tool_call_count` does not prove *which* tools ran, and neither `stop_reason` nor any other
field this plan had proposed actually names the agent's own final state — Plan 9.96 Task 9 Step 2's
text lists "final state" and terminal `end_turn` as two *separate* required claims, not one. Add:

- `session_mode` (`"ordinary"`/`"elevated"`)
- `tool_names` (tuple of content-free tool-call identifiers/types observed) and `tool_call_count`
  (`= len(tool_names)`, kept as an explicit field for convenience) — not just a count alone, so the
  manifest can support asserting *which* tools ran, per Task 1 Step 5's pinned real shape. Every
  other reference in this plan (Task 2's RED test, Task 5's E2E assertions) uses this same pair.
- `total_cost_usd` (str/Decimal-safe, not a secret), sourced only from Step 2's HMAC-covered
  `external-session-evidence.json` snapshot after its run-ID-keyed real Redis lookup; never from an
  unavailable ACP transcript field or a new ambient environment read.
- `stop_reason` (str, the ACP-level `stopReason`, expecting `"end_turn"`)
- `final_agent_state` (str) — set to `"COMPLETED"` only when this fixed normal ACP-path fixture's
  already-parsed evidence satisfies all three Task 1 predicates: `stop_reason == "end_turn"`,
  `tool_call_count > 0`, and `"write_file" in tool_names`. It is a bounded inference from those
  HMAC-covered manifest facts, not an ACP/Redis field and not a new collector input. When the
  conjunction does not hold, omit this field rather than fabricate a value. Never treat `end_turn`
  alone as completion, and never apply this inference to a request with `completion_condition` or to
  a different task without a new source-level proof.
- `child_key_names` (tuple of names only, sourced from the workspace's **outer** — evidence tool's
  own — audit entry per Task 1 Step 4's corrected ruling, not the inner `optimus-agent` entry; see
  the mechanical selection rule below)
- `elevated_comparison_record_present` (bool, sourced from the current run's debug-trace snapshot
  per Task 1 Steps 2-3; `True` only when the run-scoped suffix contains exactly one
  `launch_authorization_comparison` record, `False` only when it contains zero; see the mechanical
  selection rule below)
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
  `sessionId` (`debug_trace.py:78`), unrelated to the gate's session id — and a valid elevated run
  may have an empty `correlation_tags` array when the credential was resolved outside the inherited
  environment. Selecting by a tag would therefore discard precisely the valid record this plan must
  retain and would make the ordinary negative control impossible to scope honestly.

Use a non-circular, offset-based boundary instead. In the capture tool, **before** appending the
outer audit entry (i.e. before `append_authorized_audit`) and **before** spawning the child, record
the current byte length (or line count) of `<workspace>/.optimus/launch-audit.ndjson` and
`<workspace>/.optimus/debug-acp.ndjson` (treat a missing file as length 0). After the child completes,
read only the appended **suffix** of each file (from the recorded offset to EOF) — that suffix is
exactly this run's own records. Write each suffix through the same `StreamingTextSanitizer` pipeline
to new, immutable, per-capture snapshot files in `output_dir`: `audit-snapshot.ndjson`,
`debug-snapshot.ndjson`. The Step 2 collector writes the distinct, already-sanitized
`external-session-evidence.json` alongside them. Within the audit snapshot, identify the **outer** entry mechanically as the
**first record in document order** (the tool appends its own audit entry before spawning the child, so
the outer entry is necessarily written first; the inner `optimus-agent` entry follows during the
child run) — never by looking for the desired five-key result, which would be circular. Extend
`_TRANSCRIPT_ARTIFACTS` (or a parallel tuple) to include all three immutable snapshot files so they
get the same SHA-256 digest-in-manifest and joined-scan treatment; `verify` re-checks the snapshots,
never the mutable `.optimus/` originals or Redis. `child_key_names` comes from that first audit-snapshot
record. `elevated_comparison_record_present` is derived from the exact count of
`launch_authorization_comparison` records in the current-run debug snapshot: zero for ordinary,
exactly one for elevated. Each such record's `correlation_tags` must be an array of zero or more
allowlisted/sanitized tags; non-empty content is never required.

V6's audit-role split is additive inside that same first record. Continue deriving
`child_key_names` only from `child_propagation_decisions.agent_child` (the exact five effective-agent
names), and separately validate that `child_propagation_decisions.acpx_client` exists and is an empty
array for the approved clean-shell ceremony. Do not replace `agent_child`, fold the two roles
together, or treat the absence of system bootstrap keys from `acpx_client` as evidence they were not
passed — `_SYSTEM_ENV_KEYS` are deliberately excluded from the launch-setting-name audit schema.

**The offset boundary is only sound if the workspace is single-writer for the run — declare it, and
validate the suffix mechanically, failing closed on any foreign writer.** The offset→EOF suffix
equals "this run's records" ONLY if nothing else appended between offset capture and readback. If an
unrelated capture (or a second elevated-tracing process) appended concurrently, a foreign audit
record could become the first record (corrupting `child_key_names`) or a foreign comparison record
could falsely validate an ordinary run as elevated. Two guards, both
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
   record in the debug suffix shares exactly ONE `sessionId` value when the suffix is non-empty, and
   enforce zero `launch_authorization_comparison` records for ordinary / exactly one for elevated.
   Validate any `correlation_tags` array as zero-or-more allowlisted/sanitized values. On any mismatch
   — wrong record count, a foreign `launch_session_id`, multiple debug `sessionId`s, or malformed tag
   content — quarantine and fail closed
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

- [ ] **Step 4: Run the Task 2A fail-closed manifest tests as GREEN regression coverage**

Task 2A Step 7 has already written this RED suite. Run it here after the implementation, retaining a
case analogous to Task 8's `test_verify_rejects_tampered_manifest_field`: mutate one of the *new*
fields while keeping the stored HMAC and assert `EVIDENCE_HMAC_MISMATCH` and quarantine. It must also
cover a genuinely elevated run's manifest with
`elevated_comparison_record_present=True` with exactly one comparison record and an ordinary run's
has `False` with zero — the run-scoped elevated/ordinary property, pinned at the manifest layer. Add
cases proving `correlation_tags: []` is valid for elevated and that any present tags are
allowlisted/sanitized. Add the nonce-grammar rejection tests from Task 3 Step 3 (malformed /
oversized / secret-shaped
`--evidence-run-nonce` rejected pre-authorization) if not already added there.

- [ ] **Step 5: Classify any new sink in the logging-surface manifest**

```bash
uv run python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
```

If this fails with `UNCLASSIFIED_SINK`, classify the new sink (same discipline as Plan 9.96 Task 7/8:
per-surface connected-path rationale, real resolvable `test_node`, evidence tier) before continuing.
Iterate until green. Note the new snapshot-writing sinks (`audit-snapshot.ndjson`,
`debug-snapshot.ndjson`, and `external-session-evidence.json`) each need classification.

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
passing `--debug-trace` (per Task 1 Step 3's finding that comparison-record emission requires a
present grant *and* the flag — running ordinary with the flag enabled is the genuine negative
control; omitting the flag would only prove the flag was off, not that ordinary mode itself has no
elevated comparison record). Assert, from the
resulting manifest and the immutable snapshot artifacts in `output_dir` (per Task 4 Step 3's
redesign): `manifest["evidence_run_nonce"] == nonce` (freshness), `session_mode == "ordinary"`,
`tool_names` non-empty and matching the expected tool for this fixed task, `tool_call_count > 0`,
`0 < total_cost_usd <= DEFAULT_LIVE_MAX_COST_USD` (or the operator's `OPTIMUS_LIVE_MAX_COST_USD`
override) **from the HMAC-covered `external-session-evidence.json` whose run ID equals the parsed
session ID/request-ID pair**, `stop_reason == "end_turn"`, `final_agent_state == "COMPLETED"` under
the same fixed-fixture conjunction (`tool_call_count > 0` and `"write_file" in tool_names`), and the
field is absent rather than fabricated if that conjunction does not hold; `elevated_comparison_record_present is False`, the
run-scoped debug snapshot contains zero `launch_authorization_comparison` records, and — per Task 1
Step 4's pinned source — the **first record** of the `audit-snapshot.ndjson` (the outer, evidence-tool
audit entry, selected by document order, never by matching the desired result) has its
`child_propagation_decisions.agent_child` naming exactly the 5 registry-authorized names:
`OPTIMUS_AGENT_MODEL`, `OPTIMUS_API_KEY`, `OPTIMUS_GATEWAY_URL`, `OPTIMUS_PRODUCTION_MODE`,
`OPTIMUS_REDIS_URL`; the same first record's additive
`child_propagation_decisions.acpx_client` is present and empty (classified launch-setting names only;
the system-key transport allowlist is intentionally excluded). Also run the tool's own `verify` subcommand against the produced
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
everything Step 2 asserts except the ordinary negative-control values, plus
`elevated_comparison_record_present is True`, exactly one run-scoped
`launch_authorization_comparison` record, and a `correlation_tags` array containing zero or more
allowlisted/sanitized values. Empty is valid for a keyring/`.env.gateway`-resolved credential; any
present provenance/tag content contains no secret material (reuse `_joined_scan`/`verify` — no
second scanner). It does NOT
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
all nine commits — the Task 0 v1 planning commit, Task 0A v2 amendment, Task 2A v3 amendment,
Task 2B v4 amendment, Task 2C v5 amendment, Task 2D v6 amendment, this implementation commit, and
Task 8's evidence/docs and plan-closure commits. From Task 2D onward, all six Plan 9.98 approval
records are included too; Global Constraint 10's four core files are checked separately:

```bash
git diff --quiet HEAD -- tools/run_plan987_acpx_live_evidence.py tools/run_plan988_fu4b_live_evidence.py src/optimus/acp/operator_verify.py tests/e2e/acp/test_spawned_agent_live.py src/optimus/acp/e2e_transcript.py docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md docs/superpowers/reviews/2026-07-15-plan-9-96-security-contract-approval.md docs/superpowers/reviews/2026-07-15-plan-9-96-implementation-plan-approval.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md
git diff --quiet HEAD -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v3.md
git diff --quiet HEAD -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v4.md
git diff --quiet HEAD -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v5.md
git diff --quiet HEAD -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v6.md
git diff --stat HEAD -- src/optimus/acp/__main__.py src/optimus/agent/defaults.py src/optimus/acp/trusted_paths.py src/optimus/acp/subprocess_env.py src/optimus/acp/launch_policy.py src/optimus/acp/errors.py src/optimus/acp/bootstrap.py tools/verify_plan996_logging_surfaces.py src/optimus/acp/launch_gate.py src/optimus/acp/local_infra.py src/optimus/acp/local_gateway_secrets.py src/optimus/acp/launch_audit.py
```

Expected: every diff command is silent (no diff, no output) — every frozen path, core read-only path,
and every FU-1..7 file this plan is forbidden from touching remains byte-unchanged.

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

Record: this plan's v1 historical approval digest (Task 0 Step 1), the controlling v6 approval
digest and amendment SHA (Task 2D), the historical v5 bounded-inference ruling, the foundation SHA,
the Task 1 ruling and
its empirical proofs, **the Task 6 Step 3 implementation commit's full SHA** (not a SHA this same
report's own commit will only receive later), exact test node names/commands/results, the real
ordinary and elevated run outcomes (session mode, tool names, cost, stop reason, child-key names, tag
arrays as zero-or-more sanitized metadata, run-scoped comparison-record count, evidence-run nonce,
the pre-authorization fixture-digest proof) with artifact
SHA-256s (of the immutable per-capture snapshot files `transcript.stdout`/`.stderr`/
`audit-snapshot.ndjson`/`debug-snapshot.ndjson`/`external-session-evidence.json` — NOT the live
`launch-audit.ndjson`/`debug-acp.ndjson` workspace files or the live Redis record, which Task 4
Steps 2–3 deliberately replace with those snapshots), the manifest HMAC
verification results, the documented one-time durable-approval prerequisite for the ordinary
workspace, the v6 real-session proof that the prior `SNAPSHOT_MISMATCH` is absent, the outer audit's
unchanged five-name `agent_child` plus empty classified-name `acpx_client` role, coverage, Ruff, and
`git diff --check` results. **Final-state handling:** record
`final_agent_state == "COMPLETED"` only with the three content-free, observed predicates that justify
the bounded Task 1 inference (`stop_reason == "end_turn"`, `tool_call_count > 0`, and `"write_file"`
in `tool_names`); if the conjunction does not hold, record the field as absent, never fabricated. Do
not include secret or workspace content.

- [ ] **Step 2: State the Plan 9.96 Task 9 dependency explicitly**

Include a clearly labeled section: "Plan 9.96 Task 9 Steps 2, 3, and 5 depend on this plan's
implementation commit `<Task 6 Step 3 SHA>` and were blocked until it landed. Plan 9.96 Task 9 may
now run its own Step 2 commands using `tools/run_plan996_acpx_security_evidence.py capture ...
--drive-session`." This statement is for Plan 9.96's own Task 9 evidence report to cite later; it
does not itself edit Plan 9.96's plan file.

- [ ] **Step 3: Record the distinct URI-canonicalization finding under its named owner, not as v6 work**

The v6 audit also found a separate Plan 9.96 conformance defect: SECURITY-tier URI values are folded
into `security_literals` only after `mask_uri_userinfo()`, so changing only URI userinfo can leave the
security snapshot digest unchanged even though Plan 9.96 requires a URI-userinfo HMAC; additionally,
`OPTIMUS_GATEWAY_URL` currently uses literal display and can expose userinfo during the approval
ceremony. V6 must not touch that core logic. Record this content-free finding and its owner,
**Plan 9.99 (Tracked, Not Yet Scheduled): Credential URI Security-Snapshot Canonicalization**, and
state that Plan 9.99 is a separate security-contract/conformance prerequisite before Plan 9.96 may
close. Do not include any real URI, username, password, or credential value in the report.

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
depend on Plan 9.98's evidence report. Also add a separate
`## Plan 9.99 (Tracked, Not Yet Scheduled): Credential URI Security-Snapshot Canonicalization`
section owning Task 7 Step 3's URI-userinfo digest/display finding. State that it requires its own
reviewed security-contract/implementation plan and must land before Plan 9.96 closes; Plan 9.98 v6
does not implement or waive it.

- [ ] **Step 2: Add the README planning-status paragraph**

One sentence, mirroring the pattern used for every other plan.

- [ ] **Step 3: Commit the evidence report + roadmap + README — the EIGHTH commit; the plan file is NOT in it**

This commit deliberately does **not** include the Plan 9.98 plan file, to avoid the self-reference
Codex identified: a commit cannot include the plan file with "Step 3 done" ticked before Step 3's own
commit exists, and cannot leave it unticked without a dirty tree. The plan file's accumulated
checkbox ticks are committed separately in Step 4. This is a docs-only commit (Global Constraint 9:
frozen-path HEAD gate + `git diff --cached --check` only).

```bash
git diff --quiet HEAD -- tools/run_plan987_acpx_live_evidence.py tools/run_plan988_fu4b_live_evidence.py src/optimus/acp/operator_verify.py tests/e2e/acp/test_spawned_agent_live.py src/optimus/acp/e2e_transcript.py docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md docs/superpowers/reviews/2026-07-15-plan-9-96-security-contract-approval.md docs/superpowers/reviews/2026-07-15-plan-9-96-implementation-plan-approval.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md
git diff --quiet HEAD -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v3.md
git diff --quiet HEAD -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v4.md
git diff --quiet HEAD -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v5.md
git diff --quiet HEAD -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v6.md
git diff --quiet HEAD -- src/optimus/acp/launch_gate.py src/optimus/acp/local_infra.py src/optimus/acp/local_gateway_secrets.py src/optimus/acp/launch_audit.py
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

- [ ] **Step 4: Persist the checkbox-updated plan file — the NINTH (plan-closure) commit; resolves the self-reference**

Every substantive step through Step 3 is now genuinely complete, so every task-step and Definition-of-
Done checkbox except this closing action can be ticked truthfully. Tick them all now (including a tick
for this Step 4 as it is performed — the single irreducible self-reference every plan's final action
carries), then mechanically prove ONLY checkboxes changed versus the approved v6 amendment commit and
commit the plan file alone:

```bash
# Find the Task 2D amendment commit mechanically — it is the commit that FIRST added the v6 approval
# record, so no manually-carried-forward SHA is needed:
AMENDED_PLANNING_SHA=$(git log --diff-filter=A --format=%H -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v6.md | tail -1)
echo "V6 amendment commit: $AMENDED_PLANNING_SHA"
# Prove the plan file changed only in checkbox characters vs that approved v6 plan blob:
git diff "$AMENDED_PLANNING_SHA" -- docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md | grep '^[+-]' | grep -v '^[+-]\{3\}' | grep -vE '^\+- \[x\]' | grep -vE '^-- \[ \]'
```

That pipeline must print **nothing** — every changed line is a `- [ ]` → `- [x]` flip. If it prints
any line, substantive text drifted and the plan needs re-approval + a new pinned digest before
closure. Then, after approval:

```bash
git diff --quiet HEAD -- tools/run_plan987_acpx_live_evidence.py tools/run_plan988_fu4b_live_evidence.py src/optimus/acp/operator_verify.py tests/e2e/acp/test_spawned_agent_live.py src/optimus/acp/e2e_transcript.py docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md docs/superpowers/reviews/2026-07-15-plan-9-96-security-contract-approval.md docs/superpowers/reviews/2026-07-15-plan-9-96-implementation-plan-approval.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval.md docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v2.md
git diff --quiet HEAD -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v3.md
git diff --quiet HEAD -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v4.md
git diff --quiet HEAD -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v5.md
git diff --quiet HEAD -- docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval-v6.md
git diff --quiet HEAD -- src/optimus/acp/launch_gate.py src/optimus/acp/local_infra.py src/optimus/acp/local_gateway_secrets.py src/optimus/acp/launch_audit.py
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

- [ ] This plan's v1 digest is pinned exactly once, over the pristine plan (Task 0 Step 1) — not
  re-verified against a live, checkbox-mutated file at every later step — and both the plan file and
  its approval record are committed in their own docs-only planning commit (Task 0 Step 2) **while
  still entirely `- [ ]`, including Steps 1 and 2's own checkboxes**, which are ticked only after that
  commit lands, before Task 1 begins.
- [ ] The empirical Task 1 finding is incorporated through Task 0A's reviewed agile amendment: the
  v1 plan blob at `424940e` and its approval record remain immutable history; the exact revised plan
  bytes and a same-shape, two-signature v2 approval record land together in their own docs-only
  amendment commit before Task 1 Step 2 resumes; and all later substantive-drift checks use that v2
  commit as the controlling baseline.
- [ ] Task 1's grant-consumption-topology ruling is empirically proven using the keyring store's own
  `consume_diagnostic_grant` calls and the run-scoped `launch_authorization_comparison` record count
  as the observable oracles — never
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
  source-level test is written against it. No real distinct `final_agent_state` domain signal exists
  in acpx output, the real Redis agent state store, or the sanitized transcript. For this plan's fixed
  normal ACP path only, the source-level construction proof instead pins `COMPLETED` to the conjunction
  of `stop_reason == "end_turn"`, `tool_call_count > 0`, and `"write_file" in tool_names`; `end_turn`
  alone is never sufficient, and a failed conjunction omits rather than fabricates the field.
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
  `--drive-session` path so the `--version` smoke's process-group behavior is unchanged. V6
  deliberately narrows only the default child's environment. It is proven by a
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
- [ ] The ACPX-client/inner-agent environment boundary is proven RED then GREEN: the post-default
  effective agent mapping remains the exact five-name `agent_child` audit/Redis source but is never
  inherited by ACPX; `CaptureLaunch.acpx_client_environ` contains only non-empty `_SYSTEM_ENV_KEYS`
  from the one sanctioned snapshot; the default `--version` child uses the same minimal mapping; and
  driven sessions fail value-safely before audit/spawn if any classified inherited launch setting is
  present. The outer audit adds `acpx_client: []` without changing `agent_child` or `gateway_child`.
  A real clean-shell session gets past the former `SNAPSHOT_MISMATCH`, produces positive run-bound
  external cost evidence, and passes manifest HMAC/digest/joined-scan verification. Plan 9.96's
  `launch_gate.py`/`local_infra.py`/`local_gateway_secrets.py`/`launch_audit.py` remain untouched.
- [ ] The diagnostic grant is consumed exactly once, by the process Task 1 determined is
  authoritative for elevated diagnostics — never by both the outer evidence tool and the inner
  agent.
- [ ] Every new manifest field is content-free (no raw secret, no full environment, no raw prompt or
  file content), including `tool_names`/`tool_call_count` (consistent everywhere this plan references
  them); `final_agent_state == "COMPLETED"` only when the fixed-fixture, normal-ACP-path conjunction
  of `stop_reason == "end_turn"`, `tool_call_count > 0`, and `"write_file" in `tool_names` holds;
  otherwise the field is omitted, never fabricated. It is a bounded inference from existing
  HMAC-covered fields, not a transcript/Redis field or a separate final-state collector; and
  `evidence_run_nonce`, whose caller-supplied value is grammar-validated (`^run_[0-9a-f]{24}$`) and
  rejected pre-authorization on any mismatch, because it is written verbatim into the HMAC-signed
  manifest bypassing the sanitizer and "content-free" must be enforced, not merely asserted. The
  pre-authorization mutation proof is deliberately NOT a manifest field (a self-asserted boolean there
  would be unverifiable) — it is its own independently-runnable E2E test against a genuinely
  UNAPPROVED, separate workspace (not the fixed evidence workspace, which is approved).
  `child_key_names`/`elevated_comparison_record_present` are sourced from new, immutable, per-capture
  snapshot files; `total_cost_usd` is likewise sourced from the run-ID-keyed, HMAC-covered
  `external-session-evidence.json` snapshot after one sanctioned Redis lookup, never from raw ACP
  stdout or a new ambient Redis-URL read. Those files are
  inside `output_dir`, extracted from each log file's pre-launch-offset SUFFIX (never the live shared
  append-only originals, and never selected by `launch_session_id` — which both audit entries share —
  nor by correlation tag, which may be empty even for elevated; the outer audit entry is the FIRST
  record of the
  audit snapshot by document order). The offset boundary's single-writer assumption is enforced: the
  controlled workspace runs one capture at a time, and the tool mechanically validates the suffix at
  snapshot time (every audit record carries this run's `launch_session_id`; exactly the expected
  record count; all debug records share one `sessionId`; zero comparison records for ordinary and
  exactly one for elevated), failing closed on any foreign writer. A comparison record's
  `correlation_tags` array contains zero or more allowlisted/sanitized values. Those
  snapshots get the same digest-in-manifest and joined-scan coverage as `transcript.stdout`/`.stderr`
  today.
- [ ] Real ordinary and real elevated sessions both run through independently-authored `acpx`
  0.12.0+, driving the real Optimus agent, real Redis, and real Gateway credentials, against the SAME
  fixed, externally pre-approved workspace (a documented one-time durable-approval prerequisite for
  ordinary; the elevated command additionally carries a fresh single-use diagnostic grant), and both
  are asserted for mode, tools (by name, not just count), cost band, the bounded `COMPLETED` inference
  when its three predicates hold, terminal state (`end_turn`), zero pre-approval mutation, exact
  five-name `agent_child` manifest plus empty classified-name `acpx_client` role (the first
  audit-snapshot record), zero run-scoped comparison records for ordinary, exactly one allowlisted
  comparison/provenance record for elevated, and zero-or-more sanitized tags — the
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
  commit (v1 planning, v2 amendment, v3 amendment, v4 amendment, v5 amendment, v6 amendment,
  implementation, evidence/docs, and plan-closure), not a partial list checked once. Global
  Constraint 10's four core files are also untouched. All six Plan 9.98 approval records are
  byte-unchanged after the v6 amendment lands.
- [ ] Full default test suite passes, aggregate coverage across `optimus`/`optimus_gateway`/
  `optimus_security` is at least 80%, Ruff is clean, the logging-surface verifier is green, and
  `git diff --check` is clean.
- [ ] Every `uv` command in this plan's verification steps was run from a terminal with `uv` actually
  on PATH; no checkbox reflects a substitute computation.
- [ ] NINE separate operator-approved commits: (1) the Task 0 docs-only v1 planning commit (pristine
  plan + v1 approval record); (2) the Task 0A docs-only agile amendment commit (revised plan + v2
  approval record); (3) the Task 2A docs-only TDD-sequencing amendment (revised plan + v3 approval
  record); (4) the Task 2B Redis-cost-evidence amendment (revised plan + v4 approval record); (5) the
  Task 2C bounded-final-state-inference amendment (revised plan + v5 approval record); (6) the Task
  2D ACPX environment-boundary amendment (revised plan + v6 approval record); (7) the Task 6
  implementation commit; (8) the Task 8 Step 3 evidence/docs commit (evidence report + roadmap +
  README), which cites the implementation commit's already-landed SHA, never its own, and does NOT
  include the plan file; (9) the Task 8 Step 4 plan-closure commit, which
  persists the plan file's checkbox-only diff — mechanically proven to contain no substantive-text
  change versus the v6 amendment commit — resolving the self-reference of a plan file that would
  otherwise have to record its own not-yet-existing closing commit.
- [ ] This plan's evidence report explicitly states that Plan 9.96 Task 9 Steps 2/3/5 depended on
  this plan's implementation commit and were blocked until it landed.
- [ ] The distinct URI-userinfo digest/display conformance finding is not silently waived or folded
  into v6: the report and roadmap assign it to Plan 9.99 (Tracked, Not Yet Scheduled), with its own
  reviewed security-contract/implementation work required before Plan 9.96 closes.
- [ ] Final `git status` is a clean tree (modulo disclosed tool-config noise) — no dangling
  uncommitted plan-file checkbox drift; the plan file and all six approval records are tracked in
  repository history from their respective Task 0/Task 0A/Task 2A/Task 2B/Task 2C/Task 2D commits onward,
  never left untracked through to closure.

## Implementation Handoff After Plan Approval

Unlike sibling plans that require a fresh branch, this plan is intended to execute as an addition on
the same worktree/branch that already holds Plan 9.96 Tasks 0-8 (`agent/kiro/plan-9-96`), because
Plan 9.96 Task 9 cannot proceed without this plan's capability and this plan touches no frozen Plan
9.96 bytes. If the operator prefers a separate branch/PR for this plan's commits ahead of Plan 9.96
Task 9 resuming, that is a valid alternative — raise it as an explicit choice at kickoff rather than
assuming either way. Re-open the exact on-disk foundation state (Task 0) before any other step. Use
`superpowers:executing-plans` plus `superpowers:test-driven-development`.
