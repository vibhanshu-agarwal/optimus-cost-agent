# P11-FU-9 Task 8 live evidence status (honest; not fabricated)

**Generated:** 2026-08-07 (Task 8 reviewer checkpoint). Plan checkboxes not marked.

## Commands run (WSL, `UV_PROJECT_ENVIRONMENT=.venv-wsl`)

```bash
UV_PROJECT_ENVIRONMENT=.venv-wsl uv run --frozen pytest tests/unit/tools/test_run_p11_fu_9_acpx_evidence.py -q
# 17 passed

UV_PROJECT_ENVIRONMENT=.venv-wsl uv run --frozen pytest -m requires_mcp_stdio tests/integration/mcp/test_client_mcp_live.py -rs
# 1 skipped — docker_daemon_unavailable (WSL Docker Desktop integration off;
#   docker.exe PE binary not exec-able from Linux; Windows .venv broken)

UV_PROJECT_ENVIRONMENT=.venv-wsl uv run --frozen pytest -m requires_mcp_http tests/integration/mcp/ -rs
# 3 passed, 1 skipped(stdio) — Context7 catalog + real SDK httpx2 composition + byte budget GREEN

UV_PROJECT_ENVIRONMENT=.venv-wsl uv run --frozen pytest -m requires_acpx tests/e2e/test_client_mcp_acpx.py -rs
# 2 passed, 1 skipped — scratch ignore + harness verifier GREEN;
#   live empty-array acpx capture incomplete (exit=1, stop=None) — NOT evidence

UV_PROJECT_ENVIRONMENT=.venv-wsl uv run --frozen ruff check tools/run_p11_fu_9_acpx_evidence.py \
  tests/unit/tools/test_run_p11_fu_9_acpx_evidence.py \
  tests/integration/mcp/test_client_mcp_live.py \
  tests/integration/mcp/test_client_sdk_real.py \
  tests/e2e/test_client_mcp_acpx.py \
  src/optimus/mcp/client_sdk.py tests/unit/mcp/test_client_sdk.py
```

## Tier outcomes

| Tier | Result | Notes |
|---|---|---|
| Unit harness (`test_run_p11_fu_9_acpx_evidence`) | PASSED (17) | JSONL parse, check-ignore/.gitignore fallback, no secrets |
| `requires_mcp_stdio` Terraform digest `bd095e2b…f18d324` | SKIPPED | No usable Docker from WSL; Windows uv `.venv` broken — **not DoD evidence** |
| `requires_mcp_http` Context7 catalog distributions | PASSED | Negotiated `2025-11-25`; tokenized read=2/network=0/write=0; legacy false positives; Accept header |
| `requires_mcp_http` real SDK httpx2 composition | PASSED | Injected `httpx2.AsyncClient(follow_redirects=False, trust_env=False)` + Context7 initialize/list_tools |
| `requires_mcp_http` real httpx2 byte budget | PASSED | Adapter `REMOTE_BYTE_OVERFLOW` against real httpx2 stream |
| `requires_acpx` empty `mcpServers` live capture | SKIPPED | Capture incomplete — **not DoD evidence** |
| `requires_acpx` scratch ignore + verifier | PASSED | |

## Task 3 httpx2 composition claim

**May close:** real-SDK tests in `tests/integration/mcp/test_client_sdk_real.py` ran green with official `mcp` Streamable HTTP + injected hardened `httpx2.AsyncClient` and Optimus streamed byte-budget enforcement. No fake session/transport.

## Residuals (not closed by this checkpoint)

1. Terraform stdio digest-pinned catalog distributions (Docker unavailable in this environment).
2. Live acpx empty-array / per-advertised-transport ACP evidence (capture incomplete).
3. Process-tree teardown proof on Windows vs WSL POSIX group (deferred to authorized WSL worktree with working Docker/gitdir).
4. Authenticated upstream support remains out of scope.

## pyproject / .gitignore

Verified already complete on branch: `requires_mcp_stdio` / `requires_mcp_http` markers + default deselection; `.acpxrc.json`, `mcpServers.json`, `tmp/` ignored. No changes required.
