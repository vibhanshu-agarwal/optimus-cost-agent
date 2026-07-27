# Plan 11.3: Real Gateway Tool Provider Adapters

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox syntax for tracking.

**Goal:** Wire real Gateway-side HTTP adapters for web search/extract (Tavily), package lookup
(PyPI/npm/maven registry), and security advisory (OSV) so `build_tool_dependencies` can serve the
four `/v1/tools/*` routes from env-sourced Gateway credentials without breaking the one-key client
boundary.

**Architecture:** Keep the Task 4 protocol boundary (`WebToolProvider`, `PackageToolProvider`,
`AdvisoryToolProvider`) and handlers unchanged. Add concrete adapters under `optimus_gateway` that
translate typed Gateway requests to upstream HTTP, reuse the existing bounded retry seam from
`upstream_client.py`, sanitize faults into `ToolProviderError`, and normalize results into the
Task 4 provider-result models. Extend `GatewayServiceConfig` / env loading for tool-provider
secrets and allowlists; leave Plan 11.2 Task 6 as the sole owner of staging §9D evidence.

**Tech Stack:** Python 3.11+, stdlib HTTP (or the existing urllib patterns in
`upstream_client.py`), `redis>=5` already present for tool state, `defusedxml` for
parsing untrusted network-sourced Maven metadata XML (intentional third-party addition;
stdlib `xml.etree` is unsafe against entity-expansion DoS), `pytest`, `pytest-asyncio`,
`pytest-cov`, Ruff. Zero `optimus.*` imports inside `optimus_gateway`.

**Baseline:** Branch `agent/cursor/plan-11-2-gateway-tools` after Plan 11.2 Task 5 commit
`ae03c5c` (or later `main` containing Tasks 0–5). Depends on Plan 11.2 Tasks 1–5 being green;
**blocks** Plan 11.2 Task 6 staging evidence.

**Relationship to frozen Plan 11.2:** This is a **sibling plan**, not an in-place edit of
`docs/superpowers/plans/2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md`. Plan 11.2
Tasks 6–7 remain numbered as frozen; they gain an explicit dependency on Plan 11.3 completion.
Renumbering inside the frozen plan is intentionally avoided so the Plan 11.2 approval record digests
stay valid for the already-executed Tasks 0–5 scope. The plan id uses the next sequential Plan 11
decimal (`11.3`), not a nested sub-decimal under `11.2`.

## Global Constraints

- Local agent resolves only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; Tavily / package-registry /
  OSV credentials remain Gateway-side env only.
- Tool output and provider text remain untrusted data; never execute, eval, or promote to policy.
- Gateway independently revalidates tool class, signal, model, execution mode, domain, provenance,
  and call caps (handlers already do this); adapters must not bypass handlers.
- No MCP (`P11-FEAT-GATEWAY-MCP` / `P11-FU-3` remain out of scope).
- No budget/wallet/spend-cap enforcement (`P9.85-FU-3` remains deferred).
- `cost_usd` / `billing_units` come from Gateway usage construction rules already established;
  adapters must not invent post-hoc token/cost estimates when provider usage is available.
- Extract: 1–10 unique HTTPS URLs; `max_chars_per_source` default 4,000 max 20,000; advanced search
  capped at five results (already enforced in handlers).
- `optimus_gateway` remains independently deployable: no `optimus.*` imports; Redis tool state stays
  on the direct `redis>=5` client.
- Unit tests may use HTTP doubles; any live provider smoke is optional and must be separately marked
  (not a substitute for Plan 11.2 Task 6 `requires_gateway` staging policy evidence).

## Custody / why this plan exists

Plan 11.2 Task 4 correctly scoped concrete network adapters out so local-process evidence could stay
deterministic. Plan 11.2 Task 6 assumes “the staging Gateway’s configured package-registry and
advisory providers” exist. No Plan 11.2 task implements those adapters. Operator independent review
of Task 4/5 ruled that real credential-handling upstream clients deserve a dedicated reviewed task
rather than a silent “Task 6 Step 0”.

Also carried from Task 4 review (Minor → in-scope hardening here): when a real extract adapter
lands, revalidate that provider-returned item URLs match the requested / provenance-approved URL
set before building the success envelope (handlers currently trust returned extract URLs).

## File responsibility map

| File | Responsibility |
|---|---|
| `src/optimus_gateway/models.py` | Extend `GatewayServiceConfig` with tool-provider env fields (Tavily key/base URL, package-registry config, OSV config, tool domain allowlist / org-policy inputs as already consumed by `GatewayToolPolicy`). |
| `src/optimus_gateway/tool_providers.py` | Keep protocols; add concrete adapter classes (or import from sibling modules) that raise only `ToolProviderError` on upstream faults. |
| `src/optimus_gateway/tool_provider_http.py` (create if needed) | Shared urllib/retry helper wrapping `call_with_upstream_retry` semantics for tool upstreams — no parallel retry policy. |
| `src/optimus_gateway/providers.py` | Implement `build_tool_dependencies(config)` to return a real `GatewayToolDependencies` when required secrets/policy are present; return `None` (404 tools) when incomplete, never partially configured. |
| `src/optimus_gateway/tool_handlers.py` | Minimal change: extract-path post-provider URL membership check against requested/provenance URLs (defense-in-depth). |
| `src/optimus_gateway/__main__.py` / env docs as needed | Document new Gateway-only env vars; do not add them to the agent one-key surface. |
| `tests/unit/optimus_gateway/test_tool_providers.py` (create) | Adapter unit tests with fake urlopen / injected HTTP. |
| `tests/unit/optimus_gateway/test_providers.py` (modify/create) | `build_tool_dependencies` complete-vs-incomplete config matrix. |
| `tests/unit/optimus_gateway/test_tool_handlers.py` | Add extract returned-URL mismatch → 403/502 as designed. |
| `tests/unit/release/test_credentials.py` | Confirm new env names are Gateway-only and agent release scan still forbids them locally. |
| `docs/superpowers/reviews/2026-07-27-plan-11-3-implementation-plan-approval.md` | Versioned approval record for this plan’s digests (created after operator/reviewer approval). |

## Explicit exclusions

- Plan 11.2 Task 6 staging §9D policy evidence and `reports/plan-11-2-gateway-tools-staging-evidence.md`.
- Plan 11.2 Task 7 release/coverage/scope gates (run after Plan 11.3 + Task 6 as appropriate).
- MCP brokering; budget debit; client-side provider keys.
- Changing the frozen Plan 11.2 Task 0–5 checkbox history or re-deriving already-approved digests for those tasks.

---

### Task 0: Freeze and approve Plan 11.3 inputs

**Files:** This plan file; new approval record (after digests); checkpoint log (gitignored).

- [x] **Step 1:** Confirm branch/worktree and that Plan 11.2 Tasks 0–5 are committed on the baseline.
- [x] **Step 2:** Compute SHA-256 of this plan file (worktree + `git show HEAD:` after commit of the
  docs batch) and record them in a **new** approval record
  `docs/superpowers/reviews/2026-07-27-plan-11-3-implementation-plan-approval.md`.
- [x] **Step 3:** Operator + reviewer-agent approve the exact digests. Do not begin adapter source
  until that record grants authority.

---

### Task 1: Config + `build_tool_dependencies` wiring (fail closed)

**Files:** `models.py`, `providers.py`, unit tests, release credential scan.

- [x] **Step 1:** Write failing tests: incomplete config → `None`; complete config → non-`None`
  dependencies with all four providers present; agent release scan still rejects Tavily/OSV keys.
- [x] **Step 2:** Confirm RED.
- [x] **Step 3:** Extend `GatewayServiceConfig` / `from_env` for Gateway-only tool credentials and
  policy inputs; implement `build_tool_dependencies` without importing `optimus.*`.
- [x] **Step 4:** Confirm GREEN + Ruff on touched files.

---

### Task 2: Tavily web search/extract adapters

**Files:** `tool_providers.py` and/or dedicated module; `test_tool_providers.py`.

- [x] **Step 1:** Failing tests for search/extract success normalization, HTTPS-only results,
  sanitized `ToolProviderError` on upstream 5xx/timeout (no key leakage), advanced depth behavior
  compatible with handler caps.
- [x] **Step 2:** RED.
- [x] **Step 3:** Minimal Tavily adapters using bounded retry from `upstream_client`.
- [x] **Step 4:** GREEN + secret non-leak assertions.

---

### Task 3: Package-registry + OSV advisory adapters

**Files:** same provider modules; unit tests.

- [x] **Step 1:** Failing tests for pypi/npm/maven lookup and OSV advisory success paths; unsupported
  ecosystem already rejected at request validation (do not re-break); sanitized faults.
- [x] **Step 2:** RED.
- [x] **Step 3:** Minimal registry + OSV adapters; citations HTTPS-only; no raw provider JSON in
  results.
- [x] **Step 4:** GREEN.

---

### Task 4: Extract returned-URL revalidation + local smoke

**Files:** `tool_handlers.py`, handler tests; optional local-process extension with real adapters
behind env (not Task 6 staging).

- [ ] **Step 1:** Failing test: extract provider returns a different URL than requested → reject
  before success envelope.
- [ ] **Step 2:** RED.
- [ ] **Step 3:** Implement membership check; keep status mapping consistent with existing
  policy/provenance failures.
- [ ] **Step 4:** GREEN; rerun Task 4 local-process suite with deterministic providers still green;
  optionally document a Gateway-env local smoke command if credentials exist (do not claim §9D).

---

### Task 5: Fitness gates for Plan 11.3 only

- [ ] **Step 1:** Focused unit suites for providers/handlers/config + Plan 9.96 logging-surface gate
  + full `tests/unit`.
- [ ] **Step 2:** Ruff repo-wide; `git diff --check`; confirm zero `optimus.*` imports in
  `src/optimus_gateway`.
- [ ] **Step 3:** Update gitignored Plan 11 checkpoint: Plan 11.3 complete; Plan 11.2 Task 6
  unblocked for staging credentials.

## Definition of Done (Plan 11.3)

| Claim | Evidence |
|---|---|
| Real adapters exist behind protocols | Unit tests with HTTP doubles for Tavily, package registry, OSV |
| `build_tool_dependencies` wires complete configs only | Config matrix tests; incomplete → `None` / tools 404 |
| One-key agent boundary preserved | Release credential scan forbids provider keys on agent surface |
| No secret leakage on provider faults | Explicit sanitization tests |
| Extract URL defense-in-depth | Handler test for mismatched returned URL |
| Does not replace Task 6 | No `requires_gateway` staging §9D claim in this plan |

## Proposed (pending Task 0 approval)

These items are **proposals**, not settled authority, until Plan 11.3 Task 0 records
reviewer-agent and operator approval of the exact plan digests:

- Prefer **sibling Plan 11.3** over renumbering frozen Plan 11.2 Tasks 6→7 / 7→8 (preserves
  already-approved Plan 11.2 digests for Tasks 0–5; follows Plan 11 sequential decimal numbering).
- Plan 11.2 Task 6 remains blocked until Plan 11.3 Task 0 approval **and** adapter DoD above.
- If operator instead prefers in-plan renumbering, invalidate Plan 11.2 approval digests and issue a
  replacement versioned approval record for the amended Plan 11.2 file — do not do that silently.
