# Plan 11.2 (P11-FEAT-GATEWAY-TOOLS) — Task 7 Fitness / Release Gates

- **Date:** 2026-07-27
- **Branch:** `agent/cursor/plan-11-2-gateway-tools`
- **HEAD at verification:** `38989f59881ce6be6c84692f673a0c1f87880c88` (Task 6 evidence commit; Task 7 docs land on top)
- **Sibling lane:** Plan 11.3 real provider adapters (complete; unblocked Task 6)

## Step 1 — Affected suites

```
uv run --frozen pytest tests/unit/tools tests/unit/evidence tests/unit/gateway tests/unit/optimus_gateway tests/unit/acp/test_dispatcher.py tests/integration/evidence tests/integration/usage/test_evidence_provider_reconciliation.py tests/integration/optimus_gateway/test_gateway_tools_live.py tests/integration/optimus_gateway/test_gateway_tool_state_live.py -q
```

**Result:** `657 passed, 22 deselected in 26.77s`

Deselections are live-tier markers without forced credentials in this pass
(`requires_gateway` / `requires_redis` / related). Task 6 already recorded the
`requires_gateway` staging suite separately (`7 passed`); Redis live coverage is
in `test_gateway_tool_state_live.py` / Task 3 evidence.

## Step 2 — Default suite and aggregate coverage

```
uv run --frozen pytest -q
```

**First run:** `1 failed, 1778 passed, 20 skipped, 54 deselected` —
`tests/unit/optimus_gateway/test_server.py::test_unknown_route_remains_not_found`
raised `ConnectionAbortedError: [WinError 10053]` (Windows socket abort under
full-suite load). Isolation re-run of that node: **passed**. Full-suite **re-run:**
`1779 passed, 20 skipped, 54 deselected, 1 warning in 41.03s`.

Disposition: same Windows Gateway `ThreadingHTTPServer` bind/teardown flake class
already owned by backlog **`P11-FU-6`** (originally observed on a sibling
`test_server` node). Not a TOOLS feature regression; no production change claimed.

```
uv run --frozen pytest --cov=optimus --cov=optimus_gateway --cov=optimus_security --cov-report=term-missing --cov-fail-under=80 -q
```

**Result:** `1779 passed, 20 skipped, 54 deselected` —
**Required test coverage of 80% reached. Total coverage: 86.90%**
(`TOTAL 10398 stmts / 1084 miss; branch 2636 / 415`).

### Safety-critical policy / trust modules (no aggregate-only hiding)

| Module | Coverage |
|---|---|
| `src/optimus_gateway/tool_policy.py` | **88%** |
| `src/optimus_gateway/tool_state.py` | **84%** |
| `src/optimus/tools/policy.py` | **96%** |

Domain/provenance denial paths are exercised by unit `test_tool_policy` /
`test_tool_handlers` plus Task 6 staging denials
(`EMPTY_DOMAIN_INTERSECTION`, `URL_NOT_IN_SEARCH_PROVENANCE`,
`POLICY_SIGNAL_MISMATCH`, `CALL_CAP_EXCEEDED`).

### Closing remediation (reviewer finding): `request_bytes` sanitization

Reviewer flagged `src/optimus_gateway/tool_provider_http.py` at ~59% with
`request_bytes()` exception branches (Maven-only path) unproven for
secret-non-leakage, unlike `request_json`.

Fix (tests only; no production change):
`tests/unit/optimus_gateway/test_tool_providers.py::test_maven_request_bytes_upstream_failures_raise_sanitized_provider_error`
parametrized over `timeout` / `http_transient` (503) / `http_permanent` (404) /
`os_error`, routed through Maven metadata fetch. Asserts
`ToolProviderError("Maven lookup failed")` with planted secrets absent from the
message.

Post-fix module cover under `test_tool_providers.py`:
`tool_provider_http.py` **83%**. Remaining miss on `request_bytes` is line 78
(non-retryable `URLError`/`TimeoutError` arm), which is unreachable under the
current `is_retryable_upstream_fault` classifier (both shapes always retry).
Remaining `request_json` misses (permanent/network/non-object arms) were already
covered elsewhere via Tavily/PyPI/OSV suites for the security property; this
finding was specifically the Maven/`request_bytes` gap.

## Step 3 — Ruff and diff hygiene

```
uv run --frozen ruff check .
git diff --check
git status --short --branch
```

**Result:** Ruff **All checks passed**; `git diff --check` clean.
Working tree for Task 7 is documentation/report only (plus gitignored
`.superpowers/` scratch). Transient untracked Ruff noise under
`.superpowers/sdd/*-proof/*.py` was deleted before the clean `ruff check .`
pass; those scripts were never staged.

**Scope:** `git diff --name-only origin/main...HEAD` → 56 paths. No
`src/optimus/mcp/**`, budget, or spend-cap implementation paths. MCP remains
gated; budget remains deferred.

## Step 4 — One-key release scan

```
uv run --frozen pytest tests/unit/release/test_credentials.py -q
```

**Result:** `12 passed` (includes parametrized rejection of `TAVILY_API_KEY`,
`OSV_API_KEY`, `OPTIMUS_GATEWAY_OSV_API_KEY`).

Live process proofs (same helpers the release gate uses):

| Check | Result |
|---|---|
| `ALLOWED_LOCAL_CREDENTIAL_NAMES` | exactly `{OPTIMUS_GATEWAY_URL, OPTIMUS_API_KEY}` |
| Scan with only those two env names | `passed=True` |
| Scan with Tavily / OSV / `OPTIMUS_GATEWAY_OSV_API_KEY` present | `passed=False`; key listed in `provider_keys_resolvable` |
| Default scan paths include `.env` / reports, **not** `.env.gateway` | confirmed |
| `LAUNCH_VARIABLE_POLICIES`: `OPTIMUS_GATEWAY_URL` / `OPTIMUS_API_KEY` | `AGENT_CHILD` |
| `TAVILY_API_KEY`, `OPTIMUS_GATEWAY_OSV_API_KEY`, tool domain/redis/base URLs | `GATEWAY_CHILD` only |

Provider credentials may appear only in the Gateway deployment boundary
(`.env.gateway` → child projection via `project_gateway_tool_child_env`).

## Step 5 — Traceability / evidence-to-claim reconciliation

| Claim (plan table) | Artifact |
|---|---|
| Four typed tool routes served | `reports/plan-11-2-gateway-tools-local-process-evidence.md` + unit handler/server tests |
| Gateway Redis state isolated / fail-closed | `tests/unit/optimus_gateway/test_tool_state.py` + `test_gateway_tool_state_live.py` (`requires_redis`); zero `optimus.*` imports in `optimus_gateway` |
| Web search domains independently revalidated | Task 6 staging blocked-domain 403 (`EMPTY_DOMAIN_INTERSECTION`) |
| Extract requires same-run Gateway provenance | Task 6 staging 403 (`URL_NOT_IN_SEARCH_PROVENANCE`) + local search-then-extract |
| Package/advisory dedicated tool class | Policy unit tests + ACP/evidence flows + Task 6 success paths |
| Typed envelopes / usage / fail-closed | Contract/parser tests + staging sanitized summaries |
| One-key / provider isolation | `test_credentials.py`, launch-policy projection, Task 6 staging client boundary |
| Call caps Gateway-owned | State unit tests + Task 6 staging `CALL_CAP_EXCEEDED` |
| Budget deferred | Explicit **`P9.85-FU-3`** exclusion; no spend-cap src/tests in branch diff |
| MCP gated | Explicit **`P11-FU-3`** / `P11-FEAT-GATEWAY-MCP` exclusion; no MCP src/test diff |
| Release fitness | This report (suite, 86.90% coverage, Ruff, hygiene, one-key scan) |

## Step 6 — Digest freeze

Original Plan 11.2 approval record v1 digests are **invalidated for closing
sign-off** because committed bytes drifted:

| Artifact | v1 frozen | Current HEAD blob (LF) | Drift cause |
|---|---|---|---|
| Design spec | `2E679F…BFEC` | **unchanged** | — |
| Implementation plan | `F62634…7817` | **changed** | Task checkbox progress (Tasks 0–7) |
| Requirement inventory | `7DD4FA…FDC5` | **unchanged** | — |
| Charter | `D0390E…6807` | **unchanged** | — |
| Backlog | `0EFA96…B485` | **changed** | `P11-FU-7` NDJSON flake custody (`911ded2`) |

Replacement versioned record:
`docs/superpowers/reviews/2026-07-27-plan-11-2-implementation-plan-approval-v2.md`

Closing LF digests after Task 7 checkboxes / DoD ticks:

| Artifact | SHA-256 |
|---|---|
| Design spec | `2E679F105A250C7DF9F3757F72C43810B92810DD080EC6A4A985B778D163BFEC` |
| Implementation plan | `8C96C9BFA67FB87F4A90FAE37169D27B437C5FD0CEE3AB2E6AB399E67B2874E5` |
| Requirement inventory | `7DD4FA40916B2306C55492B36D37FC0178798CC20552B6E73CF13CBF5B69FDC5` |
| Charter | `D0390E7D17705EDB9F7D6FD69CCB9865DF792C4C10C7DFFDC233A3A5E58B6807` |
| Backlog | `59DE93FEE5BCB7B2C11EB6D9456D874B7B62A43DF903F7512606463112B14A94` |
