# P11-FU-9 Task 8 live evidence status

**Commit:** `fb231f2`  
**Generated:** 2026-08-07 (post-commit evidence refresh).  
**Platforms:** verified on native Windows (authoritative platform) + reproduced on WSL2 (CI-parity check).  
**Secrets:** content-free only — no credentials, raw transcripts, or env values.

## Commands (native Windows authoritative)

```powershell
uv run --frozen pytest tests/unit/tools/test_run_p11_fu_9_acpx_evidence.py -q
# 20 passed

uv run --frozen pytest -m requires_mcp_stdio tests/integration/mcp/test_client_mcp_live.py -q
# 1 passed, 1 deselected — Terraform digest-pinned stdio via Docker Desktop

uv run --frozen pytest -m requires_mcp_http tests/integration/mcp/ -q
# 3 passed, 1 deselected — Context7 catalog + real SDK httpx2 composition + byte budget

uv run --frozen pytest -m requires_acpx tests/e2e/test_client_mcp_acpx.py -q -rs
# 2 passed, 1 skipped — scratch ignore + harness verifier GREEN;
#   live empty-array acpx capture incomplete (exit=1, stop=None) — NOT DoD evidence

uv run --frozen pytest tests/unit/mcp tests/unit/acp tests/unit/guardrails tests/unit/agent -q
# 999 passed, 19 skipped

uv run --frozen pytest tests/unit -q
# 2772 passed, 25 skipped, 0 failed

uv run --frozen ruff check .
git diff --check
uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
# Plan 9.96 logging-surface audit passed
```

## Tier outcomes

| Tier | Result | Notes |
|---|---|---|
| Unit harness (`test_run_p11_fu_9_acpx_evidence`) | PASSED (20) | JSONL parse, check-ignore/.gitignore fallback, report secret scan, write_reports/main/run_capture sinks |
| `requires_mcp_stdio` Terraform digest `bd095e2b…f18d324` | PASSED | Negotiated `2025-11-25`; tokenized read=9/network=0/write=0; legacy differs; native Docker Desktop |
| `requires_mcp_http` Context7 catalog distributions | PASSED | Negotiated `2025-11-25`; tokenized read=2/network=0/write=0; Accept `application/json, text/event-stream` |
| `requires_mcp_http` real SDK httpx2 composition | PASSED | Injected `httpx2.AsyncClient(follow_redirects=False, trust_env=False)` + Context7 initialize/list_tools; no fake session/transport |
| `requires_mcp_http` real httpx2 byte budget | PASSED | Adapter `REMOTE_BYTE_OVERFLOW` against real httpx2 stream |
| `requires_acpx` scratch ignore + verifier | PASSED | |
| `requires_acpx` empty `mcpServers` live capture | SKIPPED | `acpx_capture_incomplete exit=1 stop=None` — known acpx↔optimus-agent gap; **not DoD evidence** |

## Task 3 httpx2 composition claim

**Closed:** real-SDK tests in `tests/integration/mcp/test_client_sdk_real.py` ran green with official `mcp` Streamable HTTP + injected hardened `httpx2.AsyncClient` and Optimus streamed byte-budget enforcement. No fake session/transport.

## Residuals (still open)

1. Live acpx empty-array / per-advertised-transport ACP capture (`acpx_capture_incomplete`) — pre-existing, documented skip; not a Task 8 regression.
2. Authenticated upstream support remains out of scope.

## Windows hang fix (verification note)

Step 4’s four-directory selector previously hung indefinitely on native Windows due to leaked `ProactorEventLoop` in `MCPAsyncSupervisor.close()` and blocking named-pipe `Client()` after listener stop in `local_ipc`. Both fixed in `fb231f2`; selector completes (~999 passed / 19 skipped).

## pyproject / .gitignore

Verified complete on branch: `requires_mcp_stdio` / `requires_mcp_http` markers + default deselection; `.acpxrc.json`, `mcpServers.json`, `tmp/` ignored.
