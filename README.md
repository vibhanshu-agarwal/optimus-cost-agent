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
