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
