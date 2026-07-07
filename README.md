# Optimus Cost Agent

Local-first Python ACP (Agent Client Protocol) server for building **cost-aware AI agents**. All model and provider access routes through the **Optimus Gateway** so developers run with a single API key locally—no Tavily, OpenAI, OpenRouter, or other vendor credentials on the machine.

**Status:** Early initialization (Phase 1). Design docs and project standards are in place; application code is under active development.

## Features (Phase 1)

- **One-key runtime** — only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` required locally
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
side effect, and ACP callers receive JSON-RPC code `-32002` when the boundary is
violated.

### Phase 1 Gateway Configuration Foundation

The gateway configuration foundation keeps the local runtime on the one-key
model: `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`. `OptimusGatewaySettings`
validates trusted gateway origins, masks the Optimus API key in safe dumps and
representations, rejects local provider keys in strict mode, and supports
development-only extra trusted origins. The gateway client posts model requests
to `/v1/responses` using the Responses API `input` shape and parses the
GatewayUsage envelope before returning generated text.

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
registry. Local pre-commit configuration and CI use the same named guardrail
checks so skipped hooks and clean-checkout drift are caught by CI; a generated
detect-secrets baseline keeps the real secret scan separate from the
config-trust scan.

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
joined by `gateway_request_id`. `EvidenceLedger` remains the audit trail for
external evidence and reconciles against the provider usage ledger by cost,
billing units, and request IDs. Local telemetry is append-only JSONL and Redis
adapter writes are isolated behind TimeSeries/HASH boundaries. Trace export
uses the Optimus Gateway `/v1/observability/traces` endpoint; LangSmith and
provider credentials stay server-side and are never required locally.

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
golden-task-suite, diff-hygiene, and one-key credential gates into a single
`ReleaseGateReport`. `scan_local_credentials()` enforces the one-key model by
rejecting resolvable provider keys from the local environment and configured
release scan artifacts. The default one-key gate scans the local process
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
run, or the release evidence must state that staging Gateway E2E was not run.
The final go/no-go rule is strict: a Plan-mode and Agent-mode release run must
complete with only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` available locally.
Provider keys such as Tavily, OpenAI, OpenRouter, GLM, Anthropic, and LangSmith
must remain Gateway-side. Plan 9 bounded loops and skill loading, and Plan 10
context-window optimization gates, are out of scope for the Phase 1 golden
fixture set described above.

### Bounded Goal Loops and Curated Workflow Skills

Plan 9 adds architectural support for bounded goal-driven loops and curated
workflow skills. Loops are not the default execution mode. They are enabled only
when a task has a machine-checkable completion condition and explicit
`LoopBudgetPolicy` bounds for iterations, Optimus credits, wall-clock time, and
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

Plan 10 context-window optimization builds on this runner. It does not create
the task lifecycle, approval boundary, tool adapters, or golden harness.

## Prerequisites

- **Python** ≥ 3.14
- **Optimus Gateway** access (`OPTIMUS_GATEWAY_URL`, `OPTIMUS_API_KEY`)
- **Git** with worktree support (for parallel development)

## Quick start

### 1. Clone the repository

```bash
git clone https://github.com/vibhanshu-agarwal/optimus-cost-agent.git
cd optimus-cost-agent
```

Keep this clone on `main` for docs, releases, and merging. Do day-to-day feature work in a [worktree](#development-worktrees) on your own branch.

### 2. Configure environment

Create a local `.env` (never commit this file):

```bash
OPTIMUS_GATEWAY_URL=https://your-gateway.example
OPTIMUS_API_KEY=your-optimus-api-key
```

### 3. Create a virtual environment

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

### 4. Run tests

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

### Required environment

```bash
export OPTIMUS_GATEWAY_URL=https://gateway.optimus.ai
export OPTIMUS_API_KEY=...
export OPTIMUS_REDIS_URL=redis://localhost:6379/0
```

Redis stores approved plans for replay.

- plan approval expires after 3600 seconds

If approval arrives after expiry, the runtime returns `PLAN_NOT_FOUND_OR_EXPIRED`
and the IDE must ask the user to re-run planning and approve the new plan.

### Config check

Validate credentials and Redis reachability before the IDE spawns the agent:

```bash
python -m optimus.acp --workspace-root . --check-config
```

### Launch commands

```bash
python -m optimus.acp --workspace-root .
```

Console script equivalent:

```bash
optimus-agent --workspace-root .
```

If `OPTIMUS_GATEWAY_URL` or `OPTIMUS_API_KEY` is missing, startup fails with:

```text
Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY before launching the Optimus ACP agent.
```

### Zed `agent_servers` example

```json
{
  "agent_servers": {
    "optimus": {
      "command": "optimus-agent",
      "args": ["--workspace-root", "."],
      "env": {
        "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
        "OPTIMUS_API_KEY": "set-in-your-local-environment",
        "OPTIMUS_REDIS_URL": "redis://localhost:6379/0"
      }
    }
  }
}
```

### Approval handshake

1. The IDE sends `initialize`, creates a workspace session with `session/new`, and
   submits work through `session/prompt`.
2. While planning runs, `session/prompt` stays pending and the agent emits
   `session/update` notifications (for example plan and tool-call updates).
3. When Agent-mode mutation requires approval, the agent sends
   `session/request_permission` to the IDE with plan text and `plan_hash`.
4. The IDE shows the plan to the user and replies to the agent's outbound JSON-RPC
   request with approval metadata containing `approval_id` and the same `plan_hash`.
5. The runtime replays the stored plan from Redis and does not call the Gateway
   again for a new plan.
6. If the user cancels the turn, the IDE sends `session/cancel`; the runtime
   resolves the pending `session/prompt` with `stopReason="cancelled"`.

Framed Content-Length JSON-RPC methods such as `optimus.agent.run` remain available
for harnesses and integration tests. IDE integrations should use the ndjson Agent
Client Protocol flow above.

### Verify with real Redis

Unit and default integration tests use in-memory fakes. To prove Redis-backed plan
replay works on your machine, start Redis and run the live checks:

```bash
docker run --rm -d --name optimus-redis -p 6379:6379 redis:8
export OPTIMUS_REDIS_URL=redis://127.0.0.1:6379/0
pytest -m requires_redis tests/integration/agent/test_redis_live_agent.py tests/integration/acp/test_bootstrap_live_redis.py tests/integration/acp/test_server_stream_live_redis.py -v
python tools/verify_live_agent.py --workspace-root .
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
| [docs/Optimus-Cost-Agent-Architecture-v2.15.pdf](docs/Optimus-Cost-Agent-Architecture-v2.15.pdf) | High-level design |
| [docs/Optimus-Cost-Agent-LLD-v2.38.pdf](docs/Optimus-Cost-Agent-LLD-v2.38.pdf) | Low-level design |
| [docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf](docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf) | Testing approach |
| [AGENTS.md](AGENTS.md) | Agent behavior, logging, safety, and testing gates |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Human and agent contribution workflow |

If HLD, LLD, and Test Strategy conflict, pause and resolve before implementing.

## Contributing

1. Read [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md).
2. Branch from latest `main` into your worktree.
3. Use TDD (required for agents).
4. Open a PR from your `human/*` or `agent/*` branch.

## License

[MIT](LICENSE) — Copyright (c) 2026 vibhanshu-agarwal
