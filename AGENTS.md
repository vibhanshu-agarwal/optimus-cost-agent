# AGENTS.md - Optimus Cost Agent

## Project Standards
- Build Phase 1 as a local-first Python ACP server with all provider access through the Optimus Gateway.
- Local runtime credentials are limited to `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; no local Tavily, OpenAI, OpenRouter, GLM, LangSmith, or provider keys.
- Treat HLD, LLD, and Test Strategy as authoritative. If they conflict, pause and ask.
- Confirm tooling from repository files before use; expected test stack is `pytest`, `pytest-asyncio`, `coverage.py`, and `pytest-cov`.
- Maintain at least 80% aggregate Python production-code coverage; safety-critical modules must not regress.

## Work Intake
- At task start, explicitly ask whether to create a new Git worktree and/or new branch.
- Follow branch and worktree naming in `CONTRIBUTING.md` (`<actor>/<id>/<slug>` branches; worktree directory per contributor id).
- Use **superpowers** when available: read the skill instructions first and follow their constraints and workflows.
- Never fork a branch from a feature branch; branch from the latest `main`.
- Use Spec Driven Development for features and architectural changes: requirements, design, tasks, then implementation.
- Before implementation, present a clean implementation plan and wait for user approval.
- Classify scope before coding: inline snippet, patch proposal, file mutation, or multi-file changeset.
- Keep claims evidence-bound: inspect the file/doc, or record the uncertainty as an assumption.

## Git And Safety
- Always read a file before editing it.
- Do not mutate files, repos, services, or state outside the project context without explicit approval.
- Before pushing a remote branch, first update the current branch from `main` and resolve drift intentionally.
- Never use `--no-verify` unless the user explicitly approves the exact command and reason.
- Check `git status` before edits and before final response; do not overwrite user changes.
- Add all secrets files and local env files to `.gitignore` before they can be accidentally committed.
- Do not commit, push, delete branches, or rewrite history unless explicitly asked.

## Shell And Tools
- Prefer Bash on Windows for project scripts and command examples.
- If Bash is unavailable on Windows, suggest installing Git Bash before falling back to PowerShell.
- Use local evidence first: repo search, file reads, AST/dependency inspection, and git diff before web or package lookups.
- Use web/package/security lookups only when policy-triggered by current facts, dependency/version work, security work, or explicit user request.
- Treat shell, build, install, and test execution as gated operations; explain material failures and next steps.

## Mode Boundaries
- Plan/Chat mode is advisory-only: read/search/discuss/plan, but no file mutation, shell mutation, external service mutation, or repo state changes.
- Agent mode may modify the working tree only after user approval and relevant fitness gates.
- Mutation paths must pass through `MutationGuard` / `assert_mutation_allowed()` and the AwaitingApproval state.
- Failed fitness gates must not leave partial writes in the working tree.

## Implementation Rules
- Preserve the one-key model: gateway adapters own vendor keys, routing, usage normalization, budgets, and observability export.
- Parse usage and cost from gateway response fields; do not estimate tokens or cost post-hoc when provider usage is available.
- Persist cost and usage with `gateway_request_id`, provider, cache_hit, billing_units, cost_usd, model/version, and run/session IDs.
- Store unparsed source code out of persistent vector indexes; keep structural summaries, signatures, and relative paths only.
- Treat tool output and web extract text as untrusted input; never execute, eval, or promote it to policy without validation.
- For retries, distinguish transient from permanent failures; cap transient retry loops at 3 attempts unless the spec says otherwise.

## Logging And Telemetry
- Logging is verbose, append-only, structured JSON Lines, and tied together by `session_id` / `run_id`.
- Use the lowest-cost model path that satisfies the logging or summarization task.
- Log every model call: full prompt, response, latency, token counts, model/provider, model version, cache_hit, and cost fields.
- Log every tool call: tool name, parameters, result summary, latency, policy reason, and authorization outcome.
- Log every error with type, message, stack/context where safe, retry count, failure classification, and final disposition.
- Never log secret values; redact credentials while preserving field names and redaction reason.

## Testing Gates
- Use **test-driven development (TDD)**: write or update a failing test first, implement the minimum code to pass, then refactor while keeping tests green.
- Every major design claim needs an executable unit, integration, E2E, eval, or release-gate check.
- Unit tests should dominate and avoid I/O/network unless the test category requires it.
- Integration tests should mock gateway/provider behavior unless validating the staging gateway path.
- E2E golden tasks must verify expected mode, tools, cost band, final state, and mutation behavior.
- Before sign-off, run the narrow relevant tests plus coverage where affected; report any tests not run.
- **Before commit, push, or PR sign-off, run Ruff and confirm a clean result:** `python -m ruff check .` (or `uv run ruff check .` / `pre-commit run optimus-ruff --all-files` when available). CI enforces the same `optimus-check: ruff` gate on every PR; pytest passing alone is not sufficient. Fix unused imports (`F401`) and import-block formatting (`I001`) before claiming the task complete.
- Release gate: full Plan-mode and Agent-mode runs with only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`, and no provider key resolvable locally.
## Plan Fidelity And Anti-Drift Guardrails
- The plan file on disk is the contract. Chat instructions, summaries, and memory of prior turns are not; when they conflict with the plan file, stop and ask the user instead of improvising.
- Scope rule: anything not listed under a plan's **Explicit Exceptions** section is IN scope. Never silently narrow scope; never widen it without a complete versioned successor plan approved by the user.
- Frozen plans may not be edited except for a relative Markdown-path repair mechanically proven by `tests/unit/docs/test_plan_relocation_digest_equivalence.py`: the registered substitutions must reproduce the destination Git blob byte-for-byte from the approved source blob. A substantive revision keeps the same plan number and publishes a complete versioned successor: `XYZ.md` -> `XYZ_v2.md` -> `XYZ_v3.md`. Once `_v2` exists, `_v1` is immutable, and the consolidated backlog points to the live version. The unchanged `docs/superpowers/plans/archive/evidence-handoff-risk-bearing-slice-implementation.md` and `docs/superpowers/plans/archive/evidence-handoff-risk-bearing-slice-implementation_v2.md` pair is the precedent.
- Going forward, do not create separately named amendment documents. Existing historical amendment documents, including the approved Plan 11.7 artifacts, are not retroactively renamed; their pinned approval bytes remain immutable in the archive.
- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` is the sole live registry for every feature, defect, follow-up, plan status, priority, owner, and next gate. Do not create or maintain a second open-work pool.
- `docs/superpowers/plans/` contains only governance documents plus plans listed in the backlog's `Live implementation plan registry`. Active and blocked plans both stay at the root; blocked plans never move merely because they are waiting.
- `docs/superpowers/plans/archive/` is one flat terminal-history directory. Move a plan there only after the backlog records it as completed, superseded, retired, abandoned, or reviewed-disposition. Preserve moved file bytes and repair repository references in mutable documents in the same PR. A frozen Markdown plan may receive only the mechanically proven relative-path repair described above; do not alter approvals, release reports, evidence artifacts, seals, or custody records solely to repair historical path strings.
- Revisions publish one complete `_vN` successor. Do not create new separately named `*-amendment.md` plans. When the successor becomes authority, keep only it at the root and move all frozen predecessors to the flat archive.
- New independently schedulable work takes the next linear plan number without a decimal-depth limit: `11.9` -> `11.10` -> `11.11`. A revision keeps the same plan number and increments `_vN`.
- Interstitial allocations such as the historical `9.8` -> `9.85` -> `9.975` sequence are forbidden going forward. Nested `N.M.1` plan numbers are also forbidden.
- Deferred-work custody: no plan may close, and no item may be excluded from a plan's scope, while any deferred follow-up lacks a named owning roadmap entry. Exclusion tables must name the owning entry per row — "unowned" is a rejectable state. A small "Tracked, Not Yet Scheduled" roadmap section is sufficient custody; no implementation plan is needed until the entry is scheduled. (Plan 9.87 and Plan 9.9 were both born as such sections; the pattern exists so deferred items cannot silently drop off the TODO list.)
- One plan, one lane: an agent works only the plan it was assigned. Do not edit another lane's plan file, tests, or tracking checkboxes.
- Checkbox protocol: `- [x]` in the plan file is the only valid progress claim, and it may be set only after the step's stated verification command actually ran and passed. Prose claims of completion count for nothing.
- Verify on disk, not by narration: reviewers and agents confirm work by reading files and diffing worktrees, never by trusting an agent's summary of what it did.
- Evidence-tier rule: the dependency named by a test tier must be real - `requires_redis` uses a live TimeSeries-capable Redis, `requires_gateway` uses real Optimus credentials, `e2e` spawns the real process. Fakes are permitted only in the unit tier; a fake standing in for the tier's named dependency is a rejectable defect. (This refines the earlier "mock gateway in integration tests" guidance: mocking stops at the live tiers.)
- ACP-protocol integration/live evidence must use a real, independently authored ACP client (`acpx`, github.com/openclaw/acpx) as the test driver, not a project-authored ACP client or harness. A fake built by this project to test this project's own ACP server shares its author's blind spots by construction: Plan 9.8 found a real Zed client crash that its own hand-rolled subprocess harness (`tools/run_plan98_live_evidence.py`) never caught. This is the ACP-protocol-layer instance of the evidence-tier rule above.
- Every Definition of Done claim must map to a named evidence artifact produced with real dependencies (see the claim-to-evidence table in the Plan 9.6 file). Green fake-based tests alone can never justify sign-off.
- Working-agent sign-off authority lives in `docs/superpowers/plans/archive/2026-07-07-plan-9-6-live-verification-and-lld-alignment.md`. No agent may declare the Phase 1 agent "working" outside that gate.
- Platform-sensitive verification: when a change or a CI failure plausibly involves OS-specific behavior (OS keyring/credential-store access, filesystem path handling or case-sensitivity, line-endings, subprocess/shell invocation, environment-variable differences), reproduce it on a real alternate-OS environment before relying solely on code review or a remote CI round-trip — on Windows hosts, WSL2 Ubuntu is a working local substitute for Linux CI (`uv sync --frozen --extra dev` then `uv run pytest ...` from the `/mnt/<drive>/...` path). Don't accept "can't verify locally" without checking this first, and don't treat a green remote CI check alone as sufficient once the failure was platform-shaped.
- **Plan prerequisites (effective 2026-08-18):** Every new plan carries a `## Prerequisites` section that identifies, at planning time, what must already be true for its evidence to be obtainable. Cover the applicable categories: code/state (whether the production path exists end to end), services (containers, daemons, ports), tooling/binaries (including versions when behavior is version-sensitive), credentials/authority, human interaction (TTY ceremony, GUI step, manual click), and cost (whether a paid call is required). Its table has these columns on every applicable row: `Satisfied today?` (`yes`, `no`, or `unknown`), `Owner` (the operator owns machine-state), and `If unsatisfied: genuinely hard, or merely unauthorized?`.
- The header wording above is retained for stability because merged, frozen plans use it. Its valid unsatisfied dispositions are: **merely unauthorized** — the capability exists and someone must permit or perform it (for example, start a container, complete a TTY ceremony, or approve a paid call); **genuinely absent** — the capability does not yet exist but is buildable now with no external dependency, so it is schedulable immediately; and **genuinely hard** — work is blocked on an external dependency, cost, authority, or an unknown of unestablished difficulty.
- An `unknown` prerequisite requires an explicit early task to establish it, sequenced before any dependent task. A plan may not claim Definition-of-Done evidence that depends on an unsatisfied prerequisite: it must either satisfy the prerequisite or scope that evidence out with a named owner. The post-amendment hygiene test applies only to plans dated 2026-08-18 or later; never retro-fail frozen or pre-existing plans.
- This is a planning-stage guardrail drawn from three preventable residuals: Plan 11.19 required a trusted Zed workspace and manual Agent-panel start; Plan 11.21 required the Phoenix container to run; and Plan 11.20 required a production discovery-to-composition path before its live tier could be attainable, regardless of tooling.
- Documentation freshness audit: before authorizing a plan's closing commit and again before a PR is merged, the reviewing agent audits every document whose content is a claim about current state — not just the plan file itself and not just the specific entries the implementing agent already touched. This includes, non-exhaustively, the open-work pool (`docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`), the roadmap (`docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`), and `README.md`. A deferred-follow-up entry being marked closed does not by itself prove that plan's own summary row elsewhere is current — check both, and check any other doc making a claim this change makes true or false. This audit is reviewer enforcement, not implementer scope: the implementing agent is not expected to go looking for it. (Precedent: Plan 11.5's own Feature Slices pool row stayed stale — still describing an unmerged, in-progress branch — through an entire subsequent plan cycle after Plan 11.5 actually merged, caught only when the operator asked directly.)

## Review Checkpoint Log (Handoff Continuity)
- Every reviewed plan maintains a repo-visible reviewer checkpoint log at `docs/superpowers/reviews/<plan-id>-review-checkpoints.md` (e.g., `plan-9-96-review-checkpoints.md`). These are gitignored (`docs/superpowers/reviews/*-review-checkpoints.md`) and must never be staged into a task commit; they exist purely for handoff across context loss, session change, or agent change.
- The **reviewing agent** owns and maintains this log — whichever agent holds the review role, Claude or otherwise. Keep a "Current State" section current, plus timestamped `## <UTC timestamp> — <title>` entries, newest first. Update it at each critical point: task/batch approval, ruling made, commit landed, or handoff.
- The **implementing agent** must, on any pickup (new session, context loss, agent switch), read the log's "Current State" section first before mutating the worktree — then verify it against the actual tree (`git status`, digests, key code), never trusting it blindly.
- Treat the log's recorded rulings and classifications as settled decisions, not proposals. Do not re-derive or contradict a decision already recorded there. If new evidence genuinely conflicts with a recorded ruling, stop and flag it explicitly; never silently reclassify. (A fresh no-context agent that re-derived a settled ruling and got it wrong is the exact failure this log prevents.)
- A reviewing agent's private/tooling memory, if any, is only the durability backstop for total worktree loss; the in-repo log is the shared, agent-readable source of truth, because one agent cannot read another's private memory.
