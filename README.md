# Optimus Cost Agent

Local-first Python ACP (Agent Client Protocol) server for building **cost-aware AI agents**. All model and provider access routes through the **local Optimus Gateway** so the agent process resolves zero upstream provider credentials; only the Gateway URL and agent-facing API key are local inputs, while provider credentials stay isolated in the Gateway process.

**Status:** Early initialization (Phase 1). Design docs and project standards are in place; application code is under active development.

## Features (Phase 1)

- **Gateway-only credential runtime** — only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` are required locally; no upstream provider credential is resolved in the agent process
- **Gateway-native usage and cost** — parse billing from gateway responses, not post-hoc estimates
- **Plan and Agent modes** — advisory planning vs. gated mutations with approval workflows
- **Structured telemetry** — JSON Lines logging tied by `session_id` / `run_id`
- **Spec-driven development** — HLD, LLD, and Test Strategy in `docs/` are authoritative

### Phase 1 Transport Foundation

The initial runtime foundation implements ACP-style `Content-Length` framing,
JSON-RPC response helpers, duplicate request ID rejection, and a minimal
`optimus.ping` dispatch path. This is the first transport foundation slice for
the authoritative Phase 1 Test Strategy; later hardening adds the continuous
stdio loop, 50-burst fragmented-header simulation, and full release-gate
transport coverage.

### Phase 1 Mode Boundary Foundation

The runtime governance foundation implements execution modes, generation-scope
classification, lifecycle transition validation, AwaitingApproval handling, and
the `assert_mutation_allowed()` primitive. Mutation wrappers for file writes,
shell execution, and shadow patch application call the primitive before any
side effect, and ACP callers receive JSON-RPC code `-32910` when the boundary is
violated.

### Phase 1 Gateway Configuration Foundation

The gateway configuration foundation keeps zero upstream provider credentials in
the agent process: `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` are the only local
inputs. `OptimusGatewaySettings`
masks the Optimus API key in safe dumps and representations, rejects local
provider keys, and accepts strict loopback Gateway URLs only. The gateway client
posts model requests to `/v1/responses` using the Responses API `input` shape and
parses the GatewayUsage envelope before returning generated text.

**Rejected POST routes are bounded (P11-FU-6).** For POSTs to unknown routes and to tool routes
without configured dependencies, the Gateway consumes a correctly framed request body of at most
64 KiB within a 2-second total deadline before returning the existing `404 {"error":"not found"}`,
and writes that response under a separate 2-second budget. A complete, validly framed body within
that limit and deadline still receives the real 404. For malformed framing (conflicting or
duplicate `Content-Length`, non-decimal values), `Transfer-Encoding`, any `Expect` header,
oversized declarations, incomplete bodies and body timeouts the server selects `400`/`501`/`417`/
`413`/`400`/`408`, makes one bounded best-effort attempt to write that JSON error, and closes the
connection; receipt of the error body is not guaranteed for an undrained or disconnected peer.
These limits apply only to that rejection path; recognized routes are unchanged and are not
hardened by this change.

### Phase 1 Tool Policy and Evidence Foundation

Tool calls are authorized by `ToolInvocationPolicy` before execution and are
recorded through `ToolRegistry.authorize_and_record_call()` so per-run caps are
enforced atomically. Web search and extract have local defense-in-depth checks
and remote gateway policy enforcement: the local runtime intersects requested
domains with the configured evidence allowlist, validates returned URLs before
they become provenance, sends only authenticated Optimus Gateway requests, keeps
URL provenance per run, and records `GatewayUsage` fields into
`EvidenceLedgerEntry` objects without estimating cost locally. Extracted web
content is untrusted evidence text and must not be executed or promoted to
policy without a separate harness decision.

### Phase 1 Permission and Pre-Tool Guardrails

Tool calls pass through a deny-before-allow permission policy and `PreToolGuard`
before side effects. Plan/Chat mode blocks shell, file-write, web, MCP, and
external side-effect surfaces before allow-list evaluation. Agent mode still
requires the existing mutation approval boundary, then pre-tool validation for
shell commands, file paths, and web/network calls. The local
`CommandSafetyValidator` explicitly allows only deterministic safe command
families, blocks enumerated destructive/fetch-execute/credential/env/control
sequence/insecure-transport/confusable patterns, and holds opaque or
unclassified shell commands for review. Web and shell network checks hold
unexpected or non-HTTP egress and block plain HTTP before wrapped subprocess,
writer, applier, transport, or gateway calls are invoked. Guard decisions are
recorded in an in-memory append-only audit sink as `ToolInvocationAuditEvent`
entries with sanitized subjects. Durable tamper-evident audit persistence is
owned by Plan 7.

### Phase 1 Prompt-Injection, MCP Trust, and CI Parity

Agent config files, repo rule files, MCP manifests, launch parameters, and MCP
tool descriptors are treated as untrusted input. `ConfigTrustScanner` blocks an
enumerated set of embedded instruction override attempts, exfiltration
endpoints, secret-read instructions, fetch-and-execute instructions,
ANSI/control text, and Unicode spoofing before guarded content can influence
planner or tool behavior. MCP servers are never auto-loaded from cloned
repositories. `MCPTrustRegistry` requires explicit approval, records manifest
hashes, launch-parameter digests, allowed tools, permission scopes, and derived
tool side-effect classes, and forces reapproval when a manifest changes.
Planner descriptor exposure and MCP tool execution both go through the
registry for local/legacy manifest-backed servers. Gateway MCP brokering is
retired (Plan 11.12). Client-supplied ACP
`mcpServers` (P11-FU-9) use a separate agent-owned client path with CLI durable
trust and `PreToolGuard` / `ConfigTrustScanner`; they are not auto-loaded from
cloned repositories and are not Gateway-brokered. Local pre-commit configuration and CI use the same named guardrail
checks so skipped hooks and clean-checkout drift are caught by CI; a generated
detect-secrets baseline keeps the real secret scan separate from the
config-trust scan.

The required CI secret-scan step enumerates Git-tracked text files under every
`src/` package and runs the scanner over that inventory. It rejects an empty
inventory rather than reporting success, so a selection that matches nothing
fails the job instead of passing silently. Passing a directory argument to the
scanner is not a production scan: it exits 0 without examining any file, and
that exit is not treated as a clean result. The scan covers tracked text under
`src/`; it is not a repository-wide cleanliness claim. The existing local
commit hook is unchanged and still receives staged filenames. The
detector and filter settings are unchanged. The baseline permits exactly three
reviewed identities in the frozen Plan 11.27 v9 document and 31 reviewed
identities in five frozen Plan 11.26 JSON reports. Exact identity and document
digest checks bind these 34 exceptions; no directory exclusion is implied.

### Phase 1 Plan 6.5 Guardrail Hardening

Plan 6.5 closes review and CI follow-ups from prompt-injection, MCP trust, and
CI parity work. MCP manifest ingestion now fails closed for unreadable paths,
shell validation inspects both argv and explicit environment mappings for git
config bypasses, Unicode spoofing uses maintained confusable detection, and MCP
runtime calls use a default trust context that wires manifest scanning,
workspace-bundled autoload denial, descriptor exposure, explicit per-call
approval, and pre-tool execution through the same registry. Usage accounting
and observability remain in Plan 7; Plan 6.5 only emits guardrail events for
that later telemetry layer to persist or export.

### Phase 1 Usage Accounting and Observability

Gateway response usage remains the source of truth for billable calls.
`GatewayUsage` captures the response envelope returned by the Optimus Gateway,
while `ProviderUsage` persists the normalized provider/native-unit cost record
joined by `gateway_request_id`, with `cost_usd` and `billing_units` as the
canonical USD/billing fields. `EvidenceLedger` remains the audit trail for
external evidence and reconciles against the provider usage ledger by cost,
billing units, and request IDs. Local telemetry is append-only JSONL and
RedisTimeSeries-backed Redis adapter writes are isolated behind TimeSeries/HASH
boundaries. Trace export uses the Optimus Gateway `/v1/observability/traces`
endpoint, the OTel/OTLP contract, and a typed `TraceDeliveryState` (delivered,
queued, failed, not_configured) for export outcomes; Phoenix is the documented
local default, and provider credentials stay Gateway-side and are never
required locally. Trace export carries no allocated or amortized per-request charge,
and LangSmith is not a dependency.

### Phase 1 Retry, Fitness Gates, Golden Tasks, and Release Gate

Plan 8 adds the Sprint 1 validation and release skeleton. `RetryController`
classifies gateway, policy, budget, and fitness-gate failures into transient,
permanent, and escalate paths, caps transient retries at three with bounded
backoff, and records retry metadata for telemetry. `CompositeFitnessGateRunner`
runs required and optional checks, fails closed on exceptions, and blocks
mutation unless every required gate passes. `ShadowWorkspace` and
`ShadowWorkspaceMutationRunner` apply candidate changes to an isolated copy of
the workspace, promote only after `assert_mutation_allowed()` and composite gates
pass, and roll back on partial promotion failure so failed fitness gates never
leave partial writes in the real working tree. `GatedRetryRunner` replans after
gate failures and mutates only after validation succeeds.

Plan 8.5 hardens the release runner. Shadow promotion now carries both writes
and deletions, rolls back partial promotion failures, and skips common large
local directories such as `.venv`, `node_modules`, build outputs, and caches.
Release command gates have a per-command timeout; timeout is reported as a
failed gate and the runner continues to collect the remaining gate results.

Golden tasks provide deterministic, keyless regression checks. Versioned
fixtures in `tests/fixtures/golden_tasks/phase1_golden_tasks.json` load into
`GoldenTask` models; a `GoldenTaskHarness` produces `GoldenTaskResult` records
that `evaluate_golden_task_suite()` compares against expected mode, tool
trajectory, cost band, final state, and mutation count. LLM-judged evaluation
remains a Gateway-routed extension and is not required locally.

The Phase 1 release runner composes ordered unit, integration, coverage,
golden-task-suite, diff-hygiene, and Gateway-only credential gates into a single
`ReleaseGateReport`. `scan_local_credentials()` enforces the zero-upstream-credential
invariant by
rejecting resolvable provider keys from the local environment and configured
release scan artifacts. The default Gateway-only credential gate scans the local process
environment plus `.env`, `.env.local`, `pyproject.toml`,
`reports/phase1-release-gate.json`, `reports/phase1-golden-results.json`, and
`reports/process-state.json`. These report paths are scanned because the release
runner reads or produces them during Sprint 1 sign-off. Add any future
release-runner local artifact to `DEFAULT_RELEASE_CREDENTIAL_SCAN_PATHS` before
it can carry credentials.

Golden tasks are wired through actual result JSON:

```bash
python tools/run_phase1_release_gate.py --golden-results reports/phase1-golden-results.json
```

When `--golden-results` is omitted, `golden-task-suite` fails closed. A
synthetic result file may be used for CLI wiring tests only. Sprint 1 sign-off
requires result JSON captured from a real Optimus-only Plan-mode and Agent-mode
run, or the release evidence must state that live Gateway E2E was not run.
The final go/no-go rule is strict: a Plan-mode and Agent-mode release run must
complete with only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` available locally.
Provider keys, including temporary Tavily migration credentials, remain Gateway-side; LangSmith is
not a dependency. Plan 9 bounded loops and skill loading, and Plan 12
context-window optimization gates, are out of scope for the Phase 1 golden
fixture set described above.

### Bounded Goal Loops and Curated Workflow Skills

Plan 9 adds architectural support for bounded goal-driven loops and curated
workflow skills. Loops are not the default execution mode. They are enabled only
when a task has a machine-checkable completion condition and explicit
`LoopBudgetPolicy` bounds for iterations, USD budget, wall-clock time, and
repeated failures.

Loop iterations persist progress to an append-only ledger and must use the same
`PreToolGuard` and permission policy as ordinary Agent-mode tool calls. A loop
that reaches completion, budget exhaustion, max iterations, wall-clock timeout,
repeated failure, or human halt records a stable `LoopStopReason`.

Skills are reviewed Markdown artifacts with frontmatter metadata. Trusted skills
may be loaded only when their description or globs match the task. Draft skills
are blocked in Agent mode, and a skill's `allowed_tools` list can only narrow
tool use. It cannot override project or user deny rules.

Plan 9 loop and skill behavior is covered by `tests/unit/loops`,
`tests/unit/skills`, `tests/integration/loops`, and `tests/integration/skills`.
It is not added to `phase1_golden_tasks.json` until the golden schema can assert
loop stop reasons and skill trust decisions directly.

### Phase 1 Agent Orchestration

Plan 9.5 composes the Phase 1 primitives into a task-level coding agent. The
agent runner accepts a typed task request, plans through the Optimus Gateway,
pauses for approval before Agent-mode mutation, executes side-effecting tools
only through guardrails, validates the result, and records the observed tool
trajectory for golden-task evaluation.

**Plan 9.6** (live verification and LLD alignment) completed the Phase 1
working-agent sign-off gate on 2026-07-11: all 8/8 claim-table rows and Phases
A-F are checked in the active execution checklist. Phase D alignment/evidence
merged through PR #40; final Phase F sign-off merged through PR #42. The Zed
HITL row is closed by the Plan 9.75 runtime evidence.

**Plan 9.7** (local dev infra auto-start and keychain setup) merged to `main`
(2026-07-09). Operators install `optimus-agent` on PATH, run `--setup` once,
and rely on auto-start Redis/gateway — no hand-edited `.env` files required for
the default local path. The full keychain-only PATH walkthrough and real planning
call were signed off on 2026-07-11 in
`reports/plan-9-7-manual-e2e-evidence.md`; IDE turn completion closed through
Plan 9.75.

**Plan 9.75** is complete (2026-07-10), merged through PR #36 at
`4fe353bb21ff3a39914e5cf84979a4494c54e25b`. It fixed the Zed
`session/prompt` hang with ACP-conformant plan `entries`, nested permission
`toolCall`, approval handling, and visible completion. See the plan's Verified
defects section, `reports/plan-9-75-zed-hitl-runtime-evidence.md`, and
`reports/plan-9-75-zed-hitl-defect-notes.md`. The later Zed 1.10.2 refusal-rendering
panic (`P9.8-FU-5`) is tracked in the [consolidated open-work pool](docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md)
and does not reopen this completed lane or belong to Plan 12.

**Plan 9.8** (task-aware workspace context) guarantees the planner receives an
explicitly referenced file's content even when task-blind workspace filler
would otherwise exhaust the single-pass context budget. Exact relative paths
and unique basenames resolve deterministically; ambiguous or oversized
required references fail closed with a visible corrective message instead of
silently truncating or guessing. Implemented and live-verified 2026-07-11 —
see `reports/plan-9-8-task-aware-context-evidence.md`. Plan 9.8 does not add
multi-turn replanning (Plan 9.85) or Plan 12 intelligent selection.

**Plan 9.85** (multi-turn read-observe-replan) extends Plan 9.8: when a
required file's complete content exceeds the single-pass context budget, the
agent runs a bounded READ → observe → replan loop (default 3 turns, 30 minute
wall clock, both overridable per request) instead of failing closed on every
oversized reference. Every Gateway call across every turn — including
retries — is charged against the same run-level `max_cost_usd` ceiling, and
only the final settled plan is ever hashed, persisted, or exposed for ACP
approval; intermediate turns never surface a plan hash or a permission
request. Implemented and live-verified 2026-07-12 over real `acpx` — see
`reports/plan-9-85-multi-turn-acpx-evidence.md`. Model-initiated replanning
when Plan 9.8's context already fits, and a live model-emitted `REFUSE:`
demonstration, are tracked separately as **Plan 9.87** below.

**Plan 9.87** is **closed**: FU-4A and FU-5 are verified qualifying claims; FU-4B is
**accepted-open** (exhausted, not qualifying) under the Plan 9.88 Task 8 Outcome B ceremony at
HEAD `fec114b7fc79da35ea399f4d66e22e776e6b76a3` (operator `vibhanshu-agarwal`,
`2026-07-14T08:13:56Z`). Accepted-open is not qualifying FU-4B evidence. Its original scope
covers model-initiated replanning when Plan 9.8's single-pass context already fits but the model
needs more evidence before a safe WRITE, plus a live model-emitted `REFUSE:` demonstration —
deferred from Plan 9.85 as `P9.85-FU-4` and `P9.85-FU-5`.
The FU-4A/FU-5 claims remain valid at their pinned implementation SHAs, but the durable verifier's
current `--require fu4a` / `--require fu5` freshness checks fail with `implementation drift`.
Re-capture and re-pinning are tracked as `P11-FU-4` in the [consolidated open-work pool](docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md),
which accounts for Plan 9.96's additional watched-path drift and sanitized-capture decision.

**Plan 9.88** is **closed** (Outcome B accepted-open). It used a new capture helper and a
capped, anti-fishing FU-4B ledger to remediate the known filename-hallucination failure without
altering the evidence-frozen runtime or Plan 9.87 capture helper, then recorded the Plan 9.87
pair-plus-exhaustion closure gate before Plan 9.9 may change `src/optimus/**` or
`tools/run_plan987_acpx_live_evidence.py`. See
`reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`.

**Plan 9.9** (implemented and live-verified 2026-07-14; implementation SHA
`f120a5afde39e3b3a8a405211ae71653b6e75665`, evidence report SHA
`cde9cb9d22c32d0d0fe05b019543d6b1b5ba78a5`) covers operator packaging and
credential diagnostics — cross-layer provider/key mismatch warnings and
non-editable-install resource-root discovery. `optimus-agent` and
`optimus-local-gateway` now install and run correctly from a non-editable
wheel outside the checkout; operator credentials resolve from an
operator-owned config directory that can never be inside the workspace. See
`reports/plan-9-9-operator-packaging-evidence.md` for the real `acpx`
packaging evidence. `P9.9-FU-1` (workspace-influenced agent launch
environment) is closed under Plan 9.96.

**Plan 9.95** (implemented) closed `P9.85-FU-6` (billable failed-retry
aggregation and unknown transport cost), `P9.88-FU-2` (ledger digest
specification), and `P9.88-FU-3` (read-range telemetry misattribution).
Implementation SHA `41a9cddddbacad766d8a432b7129a18d8976b54a`; evidence in
`reports/plan-9-95-usage-telemetry-evidence.md`. Remaining open Plan 9.9x
custody for deferred debug/launch follow-ups moved to Plan 9.96's disclosed
`P9.96-FU-*` backlog; `P9.87-FU-1` is now in the consolidated open-work pool. FU-4B accepted-open is
deliberately not included — it is a closed disposition, not a TODO.

**Plan 9.96** is implemented. Tasks 0–8 landed via PR #60; Task 9 real-dependency
evidence verified 2026-07-23 against implementation base
`031fc651dbc6b1d21cd714a0c8f5db9ea006b028`. Evidence:
`reports/plan-9-96-operator-debug-launch-trust-evidence.md`. Closes
`P9.85-FU-7` and `P9.9-FU-1`. The frozen security contract remains
SHA-256 `8B67FC187B92F0B66A9932AAAD9A013C476C19C165A1044F57F338245A01786C`.

**Plan 9.98** is implemented at `74d4ff21173a597c3b274cf6e6cbdf8a7eb43697`, with real ordinary
and elevated ACPX evidence in `reports/plan-9-98-real-acpx-session-evidence.md` (unblocked Plan 9.96
Task 9). **Plan 9.99** is implemented at `f2b6b21` (PR #66) for credential-URI security-snapshot
canonicalization and was a prerequisite for Plan 9.96 closure.

**Plan 10.1** is implemented and closes six of the seven Plan 9.96 disclosures
(`P9.96-FU-1..FU-4` by implementation commit, `FU-5` by evidence, `FU-6` by a
no-code disposition) plus the confirmation-gate half of `FU-7` — see the
[Plan 10.1 implementation plan](docs/superpowers/plans/archive/2026-07-23-plan-10-1-p9-96-follow-up-remediation.md).
**Plan 10.2** closes the remaining `P9.96-FU-7` effective-row display provenance
gap at `4350ae6f455c83f6d8a79c2a0bbdfe149755a4ef` without changing the approval
digest contract — see the
[Plan 10.2 implementation plan](docs/superpowers/plans/archive/2026-07-23-plan-10-2-p9-96-fu7-effective-row-display-provenance.md)
and the [consolidated open-work pool](docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md).
**Plan 10.3** closes the frozen dependency lock drift and the traceback-safe tools
`SurfaceAuditError` exception — see the
[Plan 10.3 implementation plan](docs/superpowers/plans/archive/2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md).

## Prerequisites

- **Python** ≥ 3.14
- **Optimus Gateway** access (`OPTIMUS_GATEWAY_URL`, `OPTIMUS_API_KEY`)
- **Git** with worktree support (for parallel development)

## Quick start (operators)

Use this path for **running `optimus-agent` from PATH** (IDEs, shells, Plan 9.7 manual sign-off).
It is **not** the repo `.venv` contributor workflow in [Contributor development setup](#contributor-development-setup) below.

### 1. Clone the repository

```bash
git clone https://github.com/vibhanshu-agarwal/optimus-cost-agent.git
cd optimus-cost-agent
```

Keep this clone on `main` for docs, releases, and merging. Do day-to-day feature work in a [worktree](#development-worktrees) on your own branch.

### 2. Install and configure (keychain — operator path)

On Windows, `optimus-agent` can store local gateway credentials in the OS keychain and
auto-start Redis (Docker) plus the local gateway process on launch — no `.env` files required.

**Install on PATH** (pick one; do **not** activate a repo `.venv` for this path):

```bash
# Recommended — uv builds a non-editable wheel from this checkout and adds its
# tool bin dir to PATH via update-shell
uv tool install . --reinstall
uv tool update-shell   # then open a new terminal

# Windows fallback when uv/pipx are unavailable
pip install --user -e . --force-reinstall
```

`uv tool install . --reinstall` builds and installs a wheel from this checkout into an
isolated `uv`-managed environment; it does **not** create an editable link back to
`src/`, so `optimus-agent` and `optimus-local-gateway` run the same way whether the
checkout later moves or is deleted. Once this project is published, the long-term
form of this command will be:

```bash
# Future — not yet published to PyPI:
# uv tool install optimus-cost-agent
```

**Operator configuration location (non-editable install):** `optimus-agent` no
longer implicitly reads a repo-root `.env.gateway`. Its provider key and shared
secret resolve from an **operator config directory** that can never be inside the
workspace: on Windows this defaults to `%APPDATA%/optimus-cost-agent/.env.gateway`;
set `OPTIMUS_CONFIG_ROOT` to an absolute directory outside the workspace to override
it explicitly. `optimus-agent --setup` writes to the OS keychain, not to this file —
use `.env.gateway` in the config directory only if you prefer a file over the
keychain. For the single local Redis / Gateway / Phoenix operator sequence, see
[Plan 11.6 local live dependencies operator runbook](docs/runbooks/local-live-dependencies.md)
— checkout-root `.env.gateway` is untrusted data for the retained trust CLI
ceremony, not an implicit `optimus-agent` discovery path.

**Local gateway and debug logs (singleton semantics):** the workspace that starts
the loopback local gateway owns `<that-workspace>/.optimus/local-gateway.log`. If a
gateway is already reachable on the configured loopback port, later `optimus-agent`
invocations from other workspaces reuse that process and do **not** create their own
gateway log. Debug tracing (`--debug-trace`) always writes to the current
workspace's own `<workspace>/.optimus/debug-acp.ndjson`, regardless of gateway
ownership.

**Required after `pip install --user` on Windows:** Python installs scripts to
`%APPDATA%\Python\Python<version>\Scripts` (for example
`C:\Users\<you>\AppData\Roaming\Python\Python314\Scripts`). Windows does **not** add this
directory to PATH automatically. Add it to your **user** PATH, then open a **new terminal**:

```powershell
# Discover your scripts directory
python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))"

# Add to user PATH (PowerShell — replace the path if yours differs)
[Environment]::SetEnvironmentVariable(
  'Path',
  [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + (python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))"),
  'User'
)
```

**IDE note:** JetBrains IDEs and Cursor may cache PATH from launch time. After fixing user PATH,
**fully quit and restart the IDE** (not just a new integrated terminal) before configuring
`"command": "optimus-agent"`.

Verify from a **new terminal** (no venv activated, no `VIRTUAL_ENV` set):

```powershell
where.exe optimus-agent
# Must NOT resolve to .venv\Scripts\optimus-agent.exe
# Must NOT resolve to a stale shim (see Troubleshooting below)
```

```bash
optimus-agent --setup
```

`--setup` interactively stores your model provider choice, provider API key, and a generated
shared secret in the Windows credential store. After setup, launch with no environment variables:

```bash
optimus-agent --workspace-root .
```

Before pointing an IDE at the agent, validate configuration (Redis reachability; no gateway
spawn on this path):

```bash
optimus-agent --workspace-root . --check-config
```

`--check-config --strict` additionally probes gateway authentication, so the gateway must
already be reachable (for example because `optimus-agent` is serving in another terminal, or you
started one manually). Plain `--check-config` is the right pre-launch check for the auto-start
flow.

**If you kill or restart the local gateway manually:** `--check-config` does **not** spawn it.
After changing gateway source (for example a new `pricing.py` entry), the running process keeps
the old in-memory config until restarted. Safe order: (1) restart the persistent Gateway using the
[Plan 11.6 local live dependencies operator runbook](docs/runbooks/local-live-dependencies.md),
(2) `optimus-agent --check-config --strict` with your intended `OPTIMUS_AGENT_MODEL`, (3) only then
run live evidence or IDE sessions. Skipping step 1 after a code change produces misleading
`no pricing snapshot` errors from a stale process.

**Flags**

| Flag | Purpose |
|------|---------|
| `--setup` | One-time wizard: store provider key + shared secret in the OS keychain, then exit |
| `--no-auto-start` | Skip auto-starting Redis and the local gateway; assume both are already running |
| `--check-config` | Validate credentials, Redis, and workspace; exit without serving |
| `--gateway-timeout-seconds SECONDS` | Raise the Gateway request timeout for this process; default is 30 seconds |

For a slow Gateway/model response during a one-off investigation, run
`optimus-agent --gateway-timeout-seconds 90`. The value applies only to that agent process;
omitting it preserves the 30-second default. It changes how long the first Gateway request may
wait; it does not enable retries or weaken the fail-closed `PLANNING_GATEWAY_COST_UNKNOWN`
behavior when the Gateway cannot report cost.

`--no-auto-start` disables **both** Redis and gateway auto-start consistently.

**Auto-managed Redis container:** when auto-start creates the named `optimus-redis`
container (`redis:8`), it runs detached **without** auto-remove and binds to `127.0.0.1`
only, so the container can be restarted by name across launches. Operator-facing startup,
conflict diagnosis, and consumer wiring live in the
[Plan 11.6 local live dependencies operator runbook](docs/runbooks/local-live-dependencies.md).

**First-run note:** the first auto-start may pull the `redis:8` image and can take several
minutes on a slow network; container create/start have no timeout in this path.

**Zed `agent_servers` (local auto-start — no `env` block):**

```json
{
  "agent_servers": {
    "optimus": {
      "command": "optimus-agent",
      "args": ["--workspace-root", "."]
    }
  }
}
```

Do **not** point Zed at `.venv\Scripts\optimus-agent.exe` — use the PATH command above.

**Troubleshooting (Windows PATH)**

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| `where.exe optimus-agent` finds nothing after `pip install --user` | Scripts dir not on user PATH | Add `%APPDATA%\Python\Python<ver>\Scripts` to user PATH (see above); new terminal + full IDE restart |
| `ModuleNotFoundError: No module named 'keyring'` | Stale `optimus-agent.exe` shim on PATH (often `~/.local/bin/`) from an old install | `where.exe optimus-agent` — remove or rename the broken shim; reinstall with `uv tool install . --reinstall` or `pip install --user -e . --force-reinstall` + PATH fix |
| Wrong binary wins on PATH | `.venv\Scripts` or `.local\bin` shadows the working install | Close venv (`deactivate`); fix PATH order; prefer Roaming Python `Scripts` or `uv tool` bin dir |
| `uv: command not found` | uv not installed | Install [uv](https://docs.astral.sh/uv/) (preferred) or use `pip install --user -e .` **with the PATH step above** |
| IDE still can't find `optimus-agent` after PATH fix | IDE inherited old PATH at startup | Fully quit and restart JetBrains/Cursor/Zed — not just a new terminal tab |

### Manual / advanced setup (transitional)

Keychain setup above is the intended long-term default. `.env` and operator-config
`.env.gateway` remain supported for operators who prefer files or need to override
keychain values (explicit env vars and `.env.gateway` take precedence over the keychain).

**Local Redis, Gateway, and Phoenix startup has one living sequence:** the
[Plan 11.6 local live dependencies operator runbook](docs/runbooks/local-live-dependencies.md).
Use that runbook for keychain setup, durable approval, the persistent trust-CLI Gateway
ceremony (optional local Phoenix), the `--no-auto-start` / external-`acpx` consumer path,
and the bounded `--check-config --strict` auto-start smoke. Do not revive retired wrapper
scripts or paste one-off container launchers from older docs.

Checkout-root `.env.gateway` is untrusted key=value data for that trust-CLI ceremony and for
live Gateway subprocess tests — never sourced into the interactive shell, and never an
implicit `optimus-agent` discovery path. The operator config directory's `.env.gateway`
(`%APPDATA%/optimus-cost-agent/.env.gateway` by default, or an absolute `OPTIMUS_CONFIG_ROOT`
override) remains the file-backed alternative for agent credential resolution — see
[Install and configure](#2-install-and-configure-keychain--operator-path) above.

For this project the Optimus Gateway is a **local process you run yourself**, not a hosted
service that issues credentials. The agent resolves zero upstream provider credentials: only
`OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` are in the agent environment.
If the agent and Gateway run under WSL2, they must share the same WSL2 network namespace; a
Windows-host Gateway is not loopback from an agent running inside WSL2.

Use **two gitignored files** so agent and gateway secrets never mix:

| File | Loaded by | Purpose |
|------|-----------|---------|
| `.env` | your agent shell / launchers | `OPTIMUS_GATEWAY_URL`, `OPTIMUS_API_KEY`, `OPTIMUS_REDIS_URL`, `OPTIMUS_AGENT_MODEL` |
| `.env.gateway` (repo root) | trust-CLI Gateway ceremony / live Gateway tests as data | provider key + `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET` |

Copy the examples and edit locally (never commit the real files):

```bash
cp .env.example .env
cp .env.gateway.example .env.gateway
```

Set the same shared secret in both files:

- `.env` → `OPTIMUS_API_KEY=...`
- `.env.gateway` → `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=...`

Agent-side `.env` example:

```bash
OPTIMUS_GATEWAY_URL=http://127.0.0.1:8765
OPTIMUS_API_KEY=<shared-secret-you-generate>
OPTIMUS_REDIS_URL=redis://127.0.0.1:6379/0
OPTIMUS_AGENT_MODEL=claude-haiku
```

The current implementation default model is `glm-5.2`. The local Gateway
maps `claude-haiku` to the configured provider's economy model, so set
`OPTIMUS_AGENT_MODEL=claude-haiku` for local development unless you pass `--model` explicitly.

**OpenRouter is the approved default** (`OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter`).
Vercel AI Gateway is a future bounded model-endpoint option pending a modest Python transport
check; it is not the Phase 1 search backend. Direct-provider adapters are a separate retirement
lane. Tavily is temporary current-implementation migration configuration only, pending replacement
acceptance and rollback review.

Live gateway smoke tests also read `.env.gateway`, but only into the gateway **subprocess**
environment via `dotenv_values()` — the pytest process itself never receives provider keys.
Default `pytest` deselects `requires_live_gateway`; opt in explicitly when `.env.gateway` is
configured:

```bash
pytest tests/integration/optimus_gateway/test_gateway_live_smoke.py -m requires_live_gateway -v
```

Security: bind stays on loopback (`127.0.0.1` by default). Do not expose this service beyond
localhost without adding real TLS first.

Smoke-test the wire contract before pytest live tiers:

```bash
curl -sS http://127.0.0.1:8765/v1/responses \
  -H "Authorization: Bearer <shared-secret>" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-haiku","input":"Reply with one short word."}'
```

## Contributor development setup

Use this section for **pytest, coverage, and code changes** inside a repo checkout. It does
**not** satisfy Plan 9.7 operator manual sign-off or IDE `"command": "optimus-agent"` integration
— see [Quick start (operators)](#quick-start-operators) for PATH install and keychain setup.

### Create a virtual environment

Using `uv` (recommended):

```bash
uv sync --all-extras
# Source the environment if not using `uv run`:
# source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate     # Windows
```

Using `pip`:

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS/Git Bash
# .venv\Scripts\activate    # Windows PowerShell
pip install -e ".[dev]"
```

### Run tests

Using `uv`:

```bash
uv run pytest
```

Using `pytest` directly (after activating venv):

```bash
pytest
```

See `pyproject.toml` and `AGENTS.md` for the expected stack: `pytest`, `pytest-asyncio`, `pytest-cov`, and `coverage.py`.

## Run The ACP Agent From An IDE

The Optimus ACP agent is a stdio JSON-RPC server. IDEs such as Zed spawn it as an
`agent_servers` child process, exchange Agent Client Protocol messages over
newline-delimited JSON, and keep `session/prompt` pending while the agent emits
`session/update` notifications and outbound `session/request_permission` requests.

### Install the `optimus-agent` command (recommended: `uv tool install`)

IDEs and shells should never need a project-specific `.venv` path or a
`python -m optimus.acp` invocation tied to one checkout. Install the console script as a
`uv`-managed tool instead — `uv` resolves and runs it from its own isolated environment, so
`optimus-agent` works as a plain command from any directory, with no venv to activate:

```bash
uv tool install . --reinstall
```

This builds a wheel from the checkout and installs it non-editably into an isolated
`uv`-managed environment — the same non-editable-install contract Plan 9.9 established and
live-verified with `tools/verify_plan99_noneditable_install.py` (see
`reports/plan-9-9-operator-packaging-evidence.md`). Source edits under `src/` do **not** take
effect until you rerun this command. After changing source or adding/upgrading a dependency in
`pyproject.toml`, reinstall:

```bash
uv tool install . --reinstall
```

Once this project is published, the long-term form of this command will be
`uv tool install optimus-cost-agent` (not yet available).

If `optimus-agent` isn't found after installing, `uv`'s tool bin directory isn't on `PATH` yet:

```bash
uv tool update-shell
```

To remove it: `uv tool uninstall optimus-cost-agent`.

### Required environment

```bash
export OPTIMUS_GATEWAY_URL=http://127.0.0.1:8765
export OPTIMUS_API_KEY=<local-shared-secret>
export OPTIMUS_REDIS_URL=redis://localhost:6379/0
```

The provider credential stays in `.env.gateway` and is passed only to the local Gateway process;
it is never exported into the agent environment.

Redis stores approved plans for replay.

- plan approval expires after 3600 seconds

If approval arrives after expiry, the runtime returns `PLAN_NOT_FOUND_OR_EXPIRED`
and the IDE must ask the user to re-run planning and approve the new plan.

**Plan-text persistence (governance):** stored plan text includes raw file content from
WRITE bodies. This is a deliberate, bounded exception to the project rule against persisting
unparsed source code: the plan store is short-TTL operational approval state (the 3600-second
expiry is the control), keyed by run and plan hash, never indexed or searched by content, and
exact text is required for replay correctness. The exception does not extend to long-lived or
indexed Redis structures (vector/structural memory stores), which hold only signatures,
summaries, and relative paths — never raw source code.

### Operator runbook (live verification)

Follow the single living sequence in
[Plan 11.6 local live dependencies operator runbook](docs/runbooks/local-live-dependencies.md)
for Redis, local Gateway, optional Phoenix, durable approval, the persistent trust-CLI ceremony,
and consumer / `acpx` terminals. Summary only:

1. Zero-Optimus shell; keychain credentials; durable workspace approval.
2. Bounded smoke (prefer the PATH binary; module form remains valid with the project venv):

```bash
python -m optimus.acp --workspace-root . --check-config --strict
```

   Add Phoenix only via the runbook's documented flag on the equivalent `optimus-agent` invocation.
3. Persistent Gateway terminal + `--no-auto-start` / external-`acpx` consumer terminal per the
   runbook — not one-off container paste commands.
4. Live tiers, in cost order, then operator sign-off (defaults to
   `reports/.verify-live-agent-workspace`):

```bash
pytest -m requires_redis -v
pytest -m requires_gateway -v
pytest -m e2e -v
python tools/verify_live_agent.py
# Or pass an explicit scratch directory:
# python tools/verify_live_agent.py --workspace-root /tmp/optimus-verify-workspace
```

Keep the provider credential in `.env.gateway`; only the local shared secret belongs in the agent
environment when you use file-backed config.

### Config check

Validate credentials, Redis reachability, and TimeSeries support before the IDE spawns the agent:

```bash
optimus-agent --workspace-root . --check-config
optimus-agent --workspace-root . --check-config --strict
```

`--strict` adds a gateway authentication probe in addition to the default Redis and workspace
checks. **`--check-config` never spawns the local gateway** — use plain `--check-config` before
first launch with auto-start; use `--strict` only when a gateway is already up.

If you manually stop the gateway or change gateway code (for example add a model pricing
snapshot), restart the gateway process before `--strict` or live runs — the old process does not
reload `pricing.py` from disk. Order: restart gateway → `--check-config --strict` → live work.

To skip auto-starting Redis and the gateway (manage them yourself), pass `--no-auto-start`.

Equivalent from inside a repo checkout without installing the tool (e.g. during development,
with the project venv active): `python -m optimus.acp --workspace-root . --check-config`.

### Launch commands

```bash
optimus-agent --workspace-root .
```

Module-invocation equivalent from inside a repo checkout:

```bash
python -m optimus.acp --workspace-root .
```

If `OPTIMUS_GATEWAY_URL` or `OPTIMUS_API_KEY` is missing, startup fails with:

```text
Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY before launching the Optimus ACP agent (or run `optimus-agent --setup` to configure the local gateway).
```

See **Quick start → Install and configure** for the local auto-start Zed example (no `env` block).

### Zed plan-approval troubleshooting

Plan 9.75 fixed the historical endless-loading defect on 2026-07-10 and verified Cancel plus
Approve/Completed Plan flows in real Zed. If a current session appears stuck, the agent may still
be waiting on **plan approval** (`session/request_permission`) or planning against the gateway;
check the approval UI, workspace root, preflight, and current debug trace rather than treating the
old ACP-shape defect as open. The completed fix and evidence are in
`docs/superpowers/plans/archive/2026-07-09-plan-9-75-zed-hitl-acp-toolcall-permission.md` and
`reports/plan-9-75-zed-hitl-runtime-evidence.md`. Historical symptom analysis and operational
checks (`always_allow_external_agent_tools`, workspace-root `"."`, preflight, and
`verify_live_agent.py`) remain in the Plan 9.6 Zed section.

### Approval handshake

1. The IDE sends `initialize`, creates a workspace session with `session/new`, and
   submits work through `session/prompt`.
2. While planning runs, `session/prompt` stays pending and the agent emits
   `session/update` notifications (for example plan and tool-call updates).
3. When Agent-mode mutation requires approval, the agent sends
   `session/request_permission` with approval `options`, `_meta` containing the
   retained run/plan identity, and the ACP v1 nested `toolCall` object
   (`toolCallId`, `kind`, `status`, `title`, `locations`). Plan 9.75 completed
   this wire-shape correction so IDEs such as Zed can render the approval UI.
4. The IDE shows the plan and replies with the selected approval `optionId`.
   Optimus generates an internal `approval_id` and binds it to the retained
   `plan_hash` when constructing the approval; it does not require Zed to echo
   either value or any other custom approval metadata.
5. The runtime replays the stored plan from Redis and does not call the Gateway
   again for a new plan.
6. If the user cancels the turn, the IDE sends `session/cancel`; the runtime
   resolves the pending `session/prompt` with `stopReason="cancelled"`.

Framed Content-Length JSON-RPC methods such as `optimus.agent.run` remain available
for harnesses and integration tests. IDE integrations should use the ndjson Agent
Client Protocol flow above.

### Verify with real Redis

Unit and default integration tests use in-memory fakes. To prove Redis-backed plan
replay works on your machine, start the named Redis dependency using the
[Plan 11.6 local live dependencies operator runbook](docs/runbooks/local-live-dependencies.md)
(default URL `redis://127.0.0.1:6379/0`, image `redis:8`), then run:

```bash
export OPTIMUS_REDIS_URL=redis://127.0.0.1:6379/0
pytest -m requires_redis tests/integration/agent/test_redis_live_agent.py tests/integration/acp/test_bootstrap_live_redis.py tests/integration/acp/test_server_stream_live_redis.py -v
# Default uses reports/.verify-live-agent-workspace (gitignored scratch dir).
python tools/verify_live_agent.py
```

Without Redis, `requires_redis` tests are deselected by default (`pyproject.toml` addopts). When you
explicitly select a live tier (`pytest -m requires_redis`) and the environment is broken, fixtures
call `pytest.fail()` with the operator action message — silent skips are forbidden.
The smoke script exits non-zero when Redis is unreachable or approval replay fails.

## Development worktrees

Multiple humans and coding agents may work in parallel. Each contributor uses a **dedicated worktree** and **named branch**—see [CONTRIBUTING.md](CONTRIBUTING.md) for full rules.

| Item | Convention | Example |
|------|------------|---------|
| Branch | `<actor>/<id>/<slug>` | `human/vibhanshu/phase-1-acp-server` |
| Worktree directory | `../optimus-cost-agent-wt-<id>` | `../optimus-cost-agent-wt-vibhanshu` |

```bash
git fetch origin
git switch main
git pull --ff-only origin main

git worktree add -b human/vibhanshu/phase-1-acp-server \
  ../optimus-cost-agent-wt-vibhanshu \
  main
```

Need a second checkout? Use a suffixed path such as `../optimus-cost-agent-wt-vibhanshu-phase-2`.

**Commits:** only push from your branch when tests pass (TDD required for agents; preferred for humans).

## Repository layout

```
optimus-cost-agent/
├── AGENTS.md          # Standards and rules for coding agents
├── CONTRIBUTING.md    # Worktrees, branches, TDD, and PR workflow
├── docs/              # Architecture, LLD, Test Strategy (authoritative)
├── pyproject.toml     # Python project metadata
└── LICENSE            # MIT
```

## Documentation

| Document | Purpose |
|----------|---------|
| [docs/Optimus-Cost-Agent-Architecture-v2.16.pdf](docs/Optimus-Cost-Agent-Architecture-v2.16.pdf) | High-level design |
| [docs/Optimus-Cost-Agent-LLD-v2.39.pdf](docs/Optimus-Cost-Agent-LLD-v2.39.pdf) | Low-level design |
| [docs/Optimus-Cost-Agent-Test-Strategy-v1.5.pdf](docs/Optimus-Cost-Agent-Test-Strategy-v1.5.pdf) | Testing approach |
| [docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf](docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf) | Execution guardrails |
| [AGENTS.md](AGENTS.md) | Agent behavior, logging, safety, and testing gates |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Human and agent contribution workflow |
| [plan backlog](docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md) | Sole live registry; the flat `plans/archive/` holds terminal history |

If HLD, LLD, and Test Strategy conflict, pause and resolve before implementing.

Archived Markdown normally preserves its committed bytes. A relative-link repair is permitted
only when the executable relocation-equivalence test proves that the approved source Git blob,
after exact registered substitutions, equals the new committed blob. Evidence artifacts, seals,
and custody records remain byte-immutable even when their historical paths are stale.

## Contributing

1. Read [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md).
2. Branch from latest `main` into your worktree.
3. Use TDD (required for agents).
4. Open a PR from your `human/*` or `agent/*` branch.

## License

[MIT](LICENSE) — Copyright (c) 2026 vibhanshu-agarwal
