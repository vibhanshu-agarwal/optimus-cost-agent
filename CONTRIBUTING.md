# Contributing to Optimus Cost Agent

Thank you for contributing. This project is designed for **parallel work by multiple
human developers and multiple coding agents**. Follow these rules to avoid branch
collisions, lost work, and accidental commits to the wrong tree.

## Before You Start

1. Read `AGENTS.md` for project standards, safety rules, and agent behavior.
2. Treat `docs/` (HLD, LLD, Test Strategy) as authoritative for design decisions.
3. Confirm tooling from repository files (`pyproject.toml`, CI config when present).
4. Never commit secrets. Local credentials are limited to `OPTIMUS_GATEWAY_URL` and
   `OPTIMUS_API_KEY`.

## Git Worktrees and Branches (Required)

Each contributor—human or agent—works in a **dedicated git worktree** on a **dedicated
branch**. Do not share a worktree across people or agents, and do not stack feature
branches on other feature branches.

### Branch naming

```
<actor>/<id>/<slug>
```

| Segment | Values | Example |
|---------|--------|---------|
| `actor` | `human` or `agent` | `human` |
| `id` | Short lowercase identifier: GitHub username, agent name, or machine slug | `vibhanshu`, `cursor`, `claude` |
| `slug` | Kebab-case task description (3–6 words) | `phase-1-acp-server` |

**Examples**

- `human/vibhanshu/phase-1-acp-server`
- `human/alice/gateway-usage-parser`
- `agent/cursor/cost-persistence-store`
- `agent/claude/mutation-guard-tests`

### Worktree path

Create worktrees as **sibling directories** next to the main clone (never inside the
repository working tree):

```
../optimus-cost-agent-wt/<actor>-<id>-<slug>
```

**Examples**

- `../optimus-cost-agent-wt/human-vibhanshu-phase-1-acp-server`
- `../optimus-cost-agent-wt/agent-cursor-cost-persistence-store`

### Create a worktree

Always branch from the latest `main`:

```bash
git fetch origin
git switch main
git pull --ff-only origin main

git worktree add -b <actor>/<id>/<slug> \
  ../optimus-cost-agent-wt/<actor>-<id>-<slug> \
  main
```

### One branch, one worktree

- **One active branch per actor per task.** If scope changes materially, open a new
  branch and worktree rather than reusing a stale branch.
- **Do not** check out someone else's branch in your primary clone while they are
  actively using its worktree.
- **Remove** worktrees when the branch is merged or abandoned:

```bash
git worktree remove ../optimus-cost-agent-wt/<actor>-<id>-<slug>
git branch -d <actor>/<id>/<slug>    # after merge
git worktree prune
```

### Coordinating parallel work

- Announce or document ownership of areas (e.g. in the PR description or issue) when
  multiple branches may touch related modules.
- Rebase or merge `main` into your branch before opening a PR; resolve drift
  intentionally—do not force-push to `main`.
- Agents must ask at task start whether to create a new worktree and branch (see
  `AGENTS.md`).

## Development Workflow

1. **Spec first** — For features and architectural changes: requirements, design,
   tasks, then implementation. Pause if HLD, LLD, and Test Strategy conflict.
2. **Plan before code** — Present an implementation plan and get approval before
   mutating the tree (especially for agents in Agent mode).
3. **Small PRs** — Prefer focused changesets that are easy to review and revert.
4. **Tests** — Use `pytest`, `pytest-asyncio`, and `pytest-cov`. Maintain at least 80%
   aggregate Python production-code coverage; do not regress safety-critical modules.
5. **No `--no-verify`** — Unless explicitly approved with a documented reason.

## Pull Requests

- Target `main` only from your named `human/*` or `agent/*` branch.
- Include: what changed, why, how to test, and any spec/doc references.
- Ensure CI-relevant tests pass locally for affected areas before requesting review.
- Do not merge your own PR without review when another maintainer is available.

## Commit Messages

Use clear, imperative subjects focused on **why**:

```
Add gateway usage parser for billing_units normalization.

Parse provider usage from gateway response fields instead of post-hoc estimates.
```

## Questions

Open an issue or discuss in the PR if design docs are unclear or parallel work might
conflict. When in doubt, branch from `main` in a new worktree rather than sharing
trees.
