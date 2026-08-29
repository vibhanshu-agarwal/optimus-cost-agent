# P11-FEAT-GATEWAY-MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:test-driven-development` for every production behavior change. Steps use checkbox (`- [ ]`) syntax for tracking. Do not mark a checkbox complete until its stated verification command has actually passed.

**Status:** Partially implemented. PR #116 merged implementation work and PR #118 repaired the
resulting CI custody regressions. At the 2026-08-06 pause/pivot, 27 of 46 checkboxes were complete:
Tasks 0-7 are complete, Task 8 Step 1 is complete, and Task 8 Steps 2-4 and Task 9 are incomplete.
Remaining work is paused pending a separately authorized resumption.

**Goal:** Implement the bounded v1 MCP Gateway data plane ratified by the approved design spec:
typed discovery and call routes, static Gateway-owned profiles, complete tools-only discovery over
remote Streamable HTTP and Docker-contained stdio, split agent/Gateway authority, complete-only
untrusted result handling, and additive `MCPUsageRecord` accounting before result release.

**Architecture:** The agent remains a one-key client. It performs the existing local MCP trust,
configuration, descriptor-exposure, permission, effect, and `PreToolGuard` checks, then sends only
typed profile/binding metadata and JSON arguments to the authenticated Gateway. The Gateway owns
operator-provisioned profile state, static upstream credential custody, protocol discovery,
allowlist filtering, connection and transport lifecycle, independent binding checks, budget and
resource admission, result validation, and MCP usage persistence. The two authorities are
deliberately complementary: a local approval cannot widen a Gateway profile, and possession of the
Gateway bearer cannot bypass the local trust gate for the normal agent path.

**Tech Stack:** Python 3.14, Pydantic 2, stdlib `urllib` and `subprocess`, `ThreadingHTTPServer`,
Redis 5/RedisTimeSeries where the existing Gateway state contract requires it, pytest,
pytest-asyncio, pytest-cov/coverage.py, Ruff, Docker with digest-pinned images, Ubuntu-24.04
WSL2 for Linux evidence, real Windows process containment, independently authored MCP HTTP/stdio
servers, the real configured Context7 endpoint, and independently authored `acpx` for ACP evidence.

## Global Constraints

- The implementation baseline is branch `agent/codex/plan-11-8-p11-feat-gateway-mcp`, based on
  `origin/main` commit `662e88666093bb93e51d35ed25f8dd7bc1159ce0`. The approved design commit is
  `4a7ad47c13fe23420d6c9c97daaee784c47493c5`.
- The approved design is the contract:
  `docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md`, whose frozen
  design-body digest is
  `1eb6cb626e1ed74e83f9ce81b048cb68da8105a1468f8f12272620bf2325f911`.
- The authoritative PDFs are frozen only by their committed `origin/main` blob bytes and the
  SHA-256 values re-verified in Task 0. Do not use a working-copy PDF, a rendered page image, or a
  hand-copied digest as the source of truth.
- Scope is exactly tools-only MCP discovery and call. The only public routes are
  `POST /v1/tools/mcp/discover` and `POST /v1/tools/mcp/call`. There is no arbitrary MCP-method
  proxy, prompt/resource/elicitation/completion/subscription/task/resume surface, or sixth route.
- Static operator-provisioned profiles are the only credential mode. Reject OAuth 2.1 lifecycle
  fields and flows. The agent process receives no upstream MCP credential, endpoint secret,
  provider credential, or secret-derived identifier; the Gateway owns upstream credentials and
  connection state.
- The two transports are remote Streamable HTTP and Docker-contained stdio. Remote v1 requires
  protocol floor `2026-07-28`, `server/discover`, `tools/list`, and `tools/call`; it has no legacy
  HTTP fallback, GET/SSE stream, or resumable protocol session. Containerized stdio uses
  discovery-first modern/legacy negotiation, digest-pinned image execution, bounded lifetime and
  output, deterministic teardown, and no mounts/devices/socket mounts.
- Preserve the existing local MCP trust/guardrail layer in `src/optimus/mcp/runtime.py` and
  `src/optimus/guardrails/mcp_trust.py`. Do not replace its registry, scanner, exposure guard, or
  `PreToolGuard` decision with a Gateway-only decision, and do not conflate it with P11-FU-9
  client-supplied ACP `mcpServers`.
- Do not absorb P11-FU-9, P11-FU-12, P11-FU-13, P11-FU-14, or P11-FU-15. Any implementation gap
  that would require one of those follow-ups is a review stop, not permission to widen this plan.
- `MCPUsageRecord` is additive. Do not rename, weaken, or reinterpret existing model/tool
  `GatewayUsage`, `ProviderUsage`, or web/package/advisory accounting. Unknown monetary attribution
  is `unavailable`, never zero; strict-dollar admission denies it unless the profile revision
  explicitly permits unattributed spend.
- Unit doubles are permitted only in unit tests. Integration and live claims use the real named
  dependency: real Redis for `requires_redis`, real loopback Gateway and approved credentials for
  `requires_gateway`, an independently authored real MCP HTTP server for `requires_mcp_http`, an
  independently authored Docker-contained stdio server for `requires_mcp_stdio`, external `acpx`
  for ACP, real Windows and Ubuntu-24.04 WSL2 for platform claims, and the actual configured
  Context7 endpoint for Context7 compatibility.
- Linux evidence must run in a separate WSL2 worktree, not by treating Windows results as Linux
  results. The planned WSL worktree is
  `D:\Projects\Development\Python\optimus-cost-agent-wt-codex-wsl` on branch
  `agent/codex/plan-11-8-p11-feat-gateway-mcp-wsl`; creation is an execution-time operator action
  after plan approval.
- Every production behavior change follows RED test, focused failing run, minimum implementation,
  focused green run, and then the next step. No checkbox is a prose-only completion claim.
- Before implementation sign-off, run affected tests, the default suite, aggregate production
  coverage at or above 80%, `python -m ruff check .`, the relevant real dependency tiers,
  `git diff --check`, the credential/secret scan, and the documentation freshness audit.
- Existing untracked `tmp/` content belongs to the user and must remain untouched. The plan itself
  is the only file this drafting stage is authorized to create.

---

## Frozen authoritative inputs and re-verification record

Task 0 must repeat this verification from the actual committed bytes before defining or executing
any implementation task. The values below are the independently re-derived baseline for this draft:

| Input | Exact committed object | SHA-256 / identity |
|---|---|---|
| HLD v2.17 | `origin/main:docs/Optimus-Cost-Agent-Architecture-v2.17.pdf` | `a21bdb01bc737fa3d8ebffba8b8b7df96c65101812e17f31c3c7324368d15024` |
| LLD v2.40 | `origin/main:docs/Optimus-Cost-Agent-LLD-v2.40.pdf` | `0329aef8b5392e05ddbb19ac3f76f3ce7f4fe3c4b728aef6cbfc4de84b324d03` |
| Guardrails v1.2 | `origin/main:docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf` | `461a720fa28576523c87c2f2f89ee1fc52c99971e51acc22edc85e8c375a7070` |
| Test Strategy v1.6 | `origin/main:docs/Optimus-Cost-Agent-Test-Strategy-v1.6.pdf` | `b435e55687116bd7c4d7e78b48e50d8da9ed0801575b7b5485f262d35c1b31a4` |
| Approved design commit | `4a7ad47c13fe23420d6c9c97daaee784c47493c5` | `docs: freeze Plan 11.8 Gateway MCP design spec` |
| Design body | approved design commit, body hashed by the design’s stated method | `1eb6cb626e1ed74e83f9ce81b048cb68da8105a1468f8f12272620bf2325f911` |
| Charter | `origin/main:docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md`, Git blob `b10e1c884f06f24778969afbbe6e5cde2fb5a6a8`, `P11-FEAT-GATEWAY-MCP` | ratified scope; no implementation-plan widening |

The four authoritative citation anchors used by this plan are: HLD §5A p.3, §§6–7 pp.4–5,
§11 p.10, §11.1 p.11, §§11A–12 p.12; LLD §§0/0A pp.2–5, §0D p.3, §§9C–9C.4 pp.26–29, §9D
p.30, §§9E–9E.1 pp.31–32, §§11–11A pp.36–38, §12B p.39; Guardrails §5 pp.8–9, §7.3 p.10,
§8.3 p.11, §§9–10.2 pp.12–13, §11.2 p.14, §13 p.16; Test Strategy §§1/3 pp.2–3, §6 p.5,
§7 p.6, §8 pp.7–8, §§9–10 pp.9–10, §11 p.10, §12 p.11, §13 p.12, §14.10 p.14.

Supporting rationale files are used only to explain why a frozen design decision exists:
`docs/superpowers/specs/2026-08-05-mcp-gateway-brokering-architecture-amendment-design.md`,
`docs/superpowers/reports/2026-08-05-mcp-gateway-architecture-document-redline-draft.md`, and
`docs/superpowers/reports/2026-08-05-mcp-gateway-security-best-practices-reference.md`. If a
rationale file conflicts with an authoritative PDF or the approved design, stop for review.

## Frozen acceptance ledger

| Requirement | Implementation task(s) | Required evidence artifact |
|---|---:|---|
| Actual source/PDF/design custody and clean baseline | 0 | `reports/plan-11-8-gateway-mcp-baseline.md` |
| Exact typed routes and duplicated agent/Gateway contracts | 1, 6 | `reports/plan-11-8-gateway-mcp-contract.md` |
| Static profiles, revisions, lifecycle, startup activation, no bearer admin route | 2 | `reports/plan-11-8-gateway-mcp-profile-lifecycle.md` |
| Complete discovery, namespace, allowlist, cursor integrity, freshness | 3 | `reports/plan-11-8-gateway-mcp-discovery.md` |
| Remote HTTP exact protocol and Docker stdio containment/negotiation | 4, 8, 9 | `reports/plan-11-8-gateway-mcp-transport.md` |
| Existing local trust gate plus Gateway binding gate | 2, 5, 6, 8 | `reports/plan-11-8-gateway-mcp-split-authority.md` |
| Complete-only result handling and untrusted content | 1, 6 | `reports/plan-11-8-gateway-mcp-results.md` |
| Additive usage, attribution, persistence-before-release, no redispatch | 7, 8 | `reports/plan-11-8-gateway-mcp-accounting.md` |
| Real Redis, Gateway, HTTP, stdio, Context7, and external ACP dependencies | 8, 9 | named live reports below; skipped tiers are not evidence |
| Four-document traceability, deferred custody, coverage, Ruff, freshness | 9 | `reports/plan-11-8-gateway-mcp-release.md` |

## File responsibility map

The following paths are implementation responsibilities after approval. Existing files are extended
only at the named seam; unrelated Plan 11.2 web/package/advisory behavior remains unchanged.

### Production files

| File | Responsibility |
|---|---|
| `src/optimus/gateway/mcp_models.py` | Agent-side typed discover/call requests, descriptor/result/disposition models, canonical manifest serialization, and response usage-summary parsing. |
| `src/optimus/gateway/client.py` | Narrow typed `discover_mcp` and `call_mcp` methods over the existing authenticated JSON transport; no arbitrary proxy. |
| `src/optimus/mcp/runtime.py` | Existing local trust sequence plus a typed Gateway runner seam after local approval; no replacement trust decision. |
| `src/optimus/guardrails/mcp_trust.py` | Existing registry/scanner/exposure semantics plus binding/revision adapters only if required by the frozen contract. |
| `src/optimus_gateway/mcp_models.py` | Independently deployable Gateway-side duplicate of the wire contract; no `optimus.*` imports. |
| `src/optimus_gateway/mcp_profiles.py` | Static profile schema, `MCPProfileRegistry`, lifecycle/revision/binding validation, startup activation, and Gateway-only credential-reference custody. |
| `src/optimus_gateway/mcp_discovery.py` | `MCPDiscoveryBroker` and `MCPDiscoveryPaginator`, protocol/version validation, complete pagination, cursor integrity, filtering, namespace, manifest, freshness, and dispositions. |
| `src/optimus_gateway/mcp_invocation.py` | `MCPInvocationBroker`, Gateway admission recheck, binding/allowlist/resource/budget checks, arguments-only forwarding, result validation, and indeterminate outcomes. |
| `src/optimus_gateway/mcp_connections.py` | `MCPConnectionManager`; profile state and transport connection lifetime remain separate. |
| `src/optimus_gateway/mcp_transports.py` | Remote Streamable HTTP 2026-07-28 adapter and digest-pinned Docker stdio adapter with bounded I/O and teardown. |
| `src/optimus_gateway/mcp_usage.py` | Additive `MCPUsageRecord`, attribution, persistence-before-release, idempotency, Redis boundary, and reconciliation hooks. |
| `src/optimus_gateway/mcp_handlers.py` | Authenticated typed handlers for exactly the two MCP routes, sanitized errors, and status/disposition mapping. |
| `src/optimus_gateway/server.py` | Route dispatch and dependency injection for MCP while preserving existing route behavior. |
| `src/optimus_gateway/providers.py`, `src/optimus_gateway/models.py`, `src/optimus_gateway/__main__.py` | Gateway-only profile configuration/bootstrap seams; preserve existing provider and signed-bind behavior. |
| `src/optimus_security/launch_manifest.py` | Non-secret HMAC startup-manifest binding for static MCP profile metadata if the existing manifest needs this extension; never carry raw MCP credentials. |
| `src/optimus/acp/local_infra.py`, `src/optimus/acp/launch_approval_cli.py` | Pass only authorized non-secret profile bootstrap metadata to the Gateway child; preserve one-key agent environment and existing manifest tests. |

### Tests, tools, and evidence

| Path | Responsibility |
|---|---|
| `tests/unit/mcp/` | Agent contract, runner, trust/binding, namespace, result, error, and credential-boundary tests. |
| `tests/unit/optimus_gateway/test_mcp_*.py` | Gateway models, profiles, discovery, transports, connections, invocation, usage, handlers, and import-boundary tests. |
| `tests/unit/security/test_launch_manifest.py`, `tests/unit/acp/test_local_infra.py`, `tests/unit/acp/test_launch_approval_cli.py` | Signed startup profile metadata and no-secret bootstrap regressions. |
| `tests/integration/optimus_gateway/test_gateway_mcp_live.py` | Real local Gateway route, split authority, independent HTTP/stdio transport, direct bearer denial, restart activation, and typed failure evidence. |
| `tests/integration/optimus_gateway/test_gateway_mcp_redis_live.py` | Real TimeSeries-capable Redis persistence, retention/idempotency, attribution, and consumer reconciliation. |
| `tests/integration/optimus_gateway/gateway_env.py` | Gateway-only live configuration helpers; no upstream MCP secret may enter agent subprocess environment. |
| `tests/e2e/` and `tools/run_plan118_acpx_gateway_mcp_evidence.py` | Golden ACP task and external `acpx` evidence; the tool orchestrates `acpx` but does not implement an ACP or MCP client. |
| `reports/plan-11-8-gateway-mcp-*.md` | Sanitized live evidence with dependency identity, digests, commands, exit codes, and dispositions; never raw secrets or unredacted untrusted bodies. |
| `pyproject.toml` | Register `requires_mcp_http` and `requires_mcp_stdio` in `markers` and add `and not requires_mcp_http and not requires_mcp_stdio` to the default `addopts -m` deselection expression; preserve default deselection of every real dependency tier. |
| `README.md`, `.env.gateway.example`, roadmap/backlog/charter current-state entries | Documentation freshness updates only when the audit proves a current-state claim changed. |

## Task 0: Freeze inputs, verify bytes, and re-derive the implementation blast radius

**Files:** Read-only repository/spec/PDF/charter inspection; later append-only evidence report.

**Interfaces:**

- Consumes the approved design commit, `origin/main`, current branch, current working tree, and
  the four committed PDF blobs.
- Produces `reports/plan-11-8-gateway-mcp-baseline.md` after approval with exact hashes, current
  file ownership, marker inventory, and the no-mutation baseline. It never edits source, tests,
  PDFs, charter text, `tmp/`, or dependencies.

- [x] **Step 1: Verify branch, baseline, design commit, and worktree state.**

  Run from the current worktree:

  ```powershell
  git status --short --branch
  git rev-parse HEAD
  git rev-parse origin/main
  git rev-parse 4a7ad47c13fe23420d6c9c97daaee784c47493c5
  git show --stat --oneline --decorate 4a7ad47c13fe23420d6c9c97daaee784c47493c5
  ```

  Expected: the current branch is `agent/codex/plan-11-8-p11-feat-gateway-mcp`, `HEAD` is the
  approved design commit, `origin/main` resolves to `662e88666093bb93e51d35ed25f8dd7bc1159ce0`,
  and the pre-existing untracked `tmp/` remains the only unrelated worktree item. If any source,
  test, PDF, charter, lockfile, or dependency drift is present, stop and report it.

- [x] **Step 2: Hash the actual committed PDF blobs and approved design body.**

  Use a binary-preserving command in Ubuntu-24.04 WSL2 or Git Bash; do not hash a checked-out PDF:

  ```bash
  git show origin/main:docs/Optimus-Cost-Agent-Architecture-v2.17.pdf | sha256sum
  git show origin/main:docs/Optimus-Cost-Agent-LLD-v2.40.pdf | sha256sum
  git show origin/main:docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf | sha256sum
  git show origin/main:docs/Optimus-Cost-Agent-Test-Strategy-v1.6.pdf | sha256sum
  git show 4a7ad47c13fe23420d6c9c97daaee784c47493c5:docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md | uv run --frozen python -c "import hashlib,sys; text=sys.stdin.buffer.read().decode('utf-8').replace('\\r\\n','\\n').replace('\\r','\\n'); header,body=text.split('\\n',1); assert 'Frozen design-body SHA-256' in header; print(hashlib.sha256(body.encode('utf-8')).hexdigest())"
  ```

  Expected, in order: `a21bdb01bc737fa3d8ebffba8b8b7df96c65101812e17f31c3c7324368d15024`,
  `0329aef8b5392e05ddbb19ac3f76f3ce7f4fe3c4b728aef6cbfc4de84b324d03`,
  `461a720fa28576523c87c2f2f89ee1fc52c99971e51acc22edc85e8c375a7070`,
  `b435e55687116bd7c4d7e78b48e50d8da9ed0801575b7b5485f262d35c1b31a4`, and the design-body
  digest `1eb6cb626e1ed74e83f9ce81b048cb68da8105a1468f8f12272620bf2325f911`. A mismatch blocks
  all later tasks.

- [x] **Step 3: Re-read the frozen scope and map every current seam.**

  Run:

  ```powershell
  rg -n "POST /v1/tools/mcp/(discover|call)|P11-FU-9|P11-FU-12|P11-FU-13|P11-FU-14|P11-FU-15|MCPProfileRegistry|MCPDiscoveryBroker|MCPDiscoveryPaginator|MCPInvocationBroker|MCPConnectionManager|MCPUsageRecord" docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md
  rg -n "TOOL_ROUTE_PATHS|def do_POST|def serve_gateway|class GatewayClient|post_tool_json|class MCPRuntimeTrustContext|class MCPTrustRegistry|build_gateway_child_manifest" src tests
  rg -n "requires_redis|requires_gateway|requires_live_gateway|requires_acpx|requires_windows_desktop" pyproject.toml tests
  git diff --check
  ```

  Record the path-level responsibility map and confirm that existing Plan 11.2 tool state and
  usage contracts are not silently assigned to MCP.

- [x] **Step 4: Write E0 and stop at the approval gate.**

  Record the exact outputs, source identities, scope exclusions, current branch, and the fact that
  no implementation mutation occurred in `reports/plan-11-8-gateway-mcp-baseline.md`. Do not create
  a commit or begin Task 1 until the implementation plan is approved.

## Task 1: Add the duplicated typed MCP wire contracts and canonical namespace/result rules

**Files:** Create `src/optimus/gateway/mcp_models.py`, `src/optimus_gateway/mcp_models.py`,
`tests/unit/mcp/test_models.py`, `tests/unit/optimus_gateway/test_mcp_models.py`, and
`tests/unit/optimus_gateway/test_mcp_import_boundary.py`.

**Interfaces:** Define the same JSON shape independently in both deployables. The agent package
must not import Gateway implementation modules, and `optimus_gateway` must not import `optimus.*`.
The contract includes these typed shapes:

```python
class MCPDiscoverRequest(BaseModel):
    profile_id: str
    profile_revision: str
    manifest_hash: str | None = None  # absent for registration, required for refresh

class MCPCallRequest(BaseModel):
    run_id: str
    session_id: str | None
    request_id: str
    profile_id: str
    profile_revision: str
    manifest_hash: str
    tool_name: str  # exactly profile_id.tool_name on the wire
    arguments: dict[str, Any]

class MCPUsageRecordSummary(BaseModel):
    gateway_request_id: str
    attribution: Literal["settled", "explicit_zero", "unavailable"]
    billing_units: int | None
    cost_usd: Decimal | None

class MCPDiscoverResponse(BaseModel):
    profile_id: str
    profile_revision: str
    transport: Literal["http", "stdio"]
    protocol_version: str
    descriptors: tuple[MCPToolDescriptor, ...]
    unmatched_allowlist: tuple[str, ...]
    manifest_hash: str
    freshness: Literal["fresh", "stale", "unchanged"]
    disposition: str

class MCPCallResponse(BaseModel):
    result_type: Literal["complete", "input_required"]
    content: tuple[MCPContent, ...]
    disposition: str
    binding: MCPBindingSummary
    transport: Literal["http", "stdio"]
    protocol_version: str
    attribution: Literal["settled", "explicit_zero", "unavailable"]
    usage: MCPUsageRecordSummary
```

  `MCPContent` must represent text, structured content, inert resource links, and embedded
  resources while rejecting or dropping image/audio content according to the frozen result policy.
  All descriptors are untrusted and have validated names, schemas, annotations, and effect
  metadata. Canonical manifest hashing must be deterministic over ordered namespaced descriptors,
  protocol/transport data, allowlist result, and profile revision; it must never include a secret.

- [x] **Step 1: Write failing validation and canonicalization tests.** Cover registration versus
  refresh requirements, exact namespaced `profile_id.tool_name` parsing, duplicate/invalid names,
  unsupported content, `input_required`, non-finite numeric values, absent-versus-null attribution,
  stable descriptor ordering, stable manifest bytes, and cross-package JSON equivalence.
- [x] **Step 2: Implement the two independent Pydantic contract modules.** Keep field names,
  discriminators, canonical JSON separators/sorting, and error codes identical without importing
  one package from the other. `MCPCallRequest` must not contain endpoint, command, credential,
  policy, approval, prompt, system, or conversation fields.
- [x] **Step 3: Run focused unit tests and import-boundary checks.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_models.py tests/unit/optimus_gateway/test_mcp_models.py tests/unit/optimus_gateway/test_mcp_import_boundary.py -q
  uv run --frozen ruff check src/optimus/gateway/mcp_models.py src/optimus_gateway/mcp_models.py tests/unit/mcp/test_models.py tests/unit/optimus_gateway/test_mcp_models.py tests/unit/optimus_gateway/test_mcp_import_boundary.py
  ```

## Task 2: Implement static profile registry, revision lifecycle, and signed startup activation

**Files:** Create `src/optimus_gateway/mcp_profiles.py`; extend the existing signed bootstrap only
at `src/optimus_security/launch_manifest.py`, `src/optimus_gateway/__main__.py`,
`src/optimus_gateway/models.py`, `src/optimus_gateway/providers.py`,
`src/optimus/acp/local_infra.py`, and `src/optimus/acp/launch_approval_cli.py` as necessary;
create `tests/unit/optimus_gateway/test_mcp_profiles.py`,
`tests/unit/security/test_mcp_profile_manifest.py`, and update the existing manifest/bootstrap
tests without removing their current assertions.

**Interfaces:**

```python
class MCPProfileState(StrEnum):
    PENDING_REGISTRATION = "PENDING_REGISTRATION"
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    DISABLED = "DISABLED"

@dataclass(frozen=True)
class MCPProfile:
    profile_id: str
    revision: str
    state: MCPProfileState
    transport: Literal["http", "stdio"]
    credential_ref: str
    upstream_allowlist: tuple[str, ...]
    manifest_hash: str | None
    limits: MCPResourceLimits
    attribution_policy: MCPAttributionPolicy
    transport_config: MCPHTTPProfile | MCPStdioProfile

class MCPProfileRegistry(Protocol):
    def for_discovery(self, request: MCPDiscoverRequest) -> ProfileAdmission: ...
    def for_call(self, request: MCPCallRequest) -> ProfileAdmission: ...
    def activate_from_startup(self, *, profile_id: str, revision: str, manifest_hash: str) -> MCPProfile: ...
    def mark_stale(self, *, profile_id: str, revision: str, reason: str) -> None: ...
```

  A profile change to credential reference/value, endpoint or executable, arguments, allowlist,
  limits, isolation, attribution, or unattributed-spend permission mints a new opaque revision.
  Disable is immediate and does not mint; re-enable mints and returns to pending. Only the initial
  approved-manifest synchronization may activate the existing revision. There is no bearer-authenticated
  profile administration route.

- [x] **Step 1: Write failing lifecycle and credential-boundary tests.** Cover absent→pending→active,
  refresh drift→stale→pending replacement, disabled/re-enable, revision changes, exact binding
  pair checks, profile-scoped allowlists, OAuth-field rejection, catalog/autoload rejection, and
  direct bearer attempts that cannot create or activate a profile.
- [x] **Step 2: Extend the HMAC startup manifest with non-secret profile bootstrap metadata only.**
  Reuse the existing `GatewayChildManifest` verification domain and signed-bind checks. The child
  manifest may carry profile ID, revision, transport, endpoint/image digest, allowlist, limits,
  attribution policy, and a credential reference; it must carry no raw credential, token, password,
  credential fingerprint, secret-derived ID, or Gateway bearer. The Gateway child alone resolves
  the credential reference from Gateway-only bootstrap input and rejects a missing or divergent
  binding. Preserve direct unmanifested-startup failure and existing provider manifest tests.
- [x] **Step 3: Wire registry construction into `serve_gateway`/`__main__` without coupling MCP to
  Tavily or existing Plan 11.2 tool state.** Unit-inject profiles and registry dependencies. The
  standalone child must fail closed on malformed, duplicated, OAuth-bearing, or unbound profiles.
- [x] **Step 4: Run focused profile/security tests.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_profiles.py tests/unit/security/test_mcp_profile_manifest.py tests/unit/security/test_launch_manifest.py tests/unit/acp/test_local_infra.py tests/unit/acp/test_launch_approval_cli.py -q
  uv run --frozen ruff check src/optimus_gateway/mcp_profiles.py src/optimus_security/launch_manifest.py src/optimus_gateway/__main__.py src/optimus_gateway/models.py src/optimus_gateway/providers.py src/optimus/acp/local_infra.py src/optimus/acp/launch_approval_cli.py
  ```

## Task 3: Implement complete discovery and deterministic pagination

**Files:** Create `src/optimus_gateway/mcp_discovery.py`,
`tests/unit/optimus_gateway/test_mcp_discovery.py`, and `tests/unit/mcp/test_mcp_discovery_binding.py`.

**Interfaces:**

```python
class MCPDiscoveryPaginator:
    def collect_tools(
        self,
        *,
        transport: MCPTransport,
        profile: MCPProfile,
    ) -> CompleteToolSet: ...

class MCPDiscoveryBroker:
    def discover(
        self,
        *,
        request: MCPDiscoverRequest,
        registry: MCPProfileRegistry,
        connection_manager: MCPConnectionManager,
    ) -> MCPDiscoverResponse: ...
```

  Registration sends profile ID/revision without a manifest hash; refresh requires the full binding
  pair. The broker must call `server/discover` at the required HTTP protocol floor, require the
  tools capability, then exhaust every bounded `tools/list` page. It filters only to the operator
  allowlist, reports unmatched allowlist entries, rejects invalid definitions and `x-mcp-header`
  requirements, never sends `Mcp-Param-*`, and constructs `profile_id.tool_name` identities.
  Repeated/malformed cursors, incomplete pages, byte/tool/page/time-limit exhaustion, or any
  partial failure return no approvable manifest. Only discovery/list transient faults use the
  existing retry policy, capped at three attempts; no resumable cursor checkpoint is created.

- [x] **Step 1: Write RED tests for protocol and pagination.** Cover exact HTTP `server/discover`
  version/capability requirements, no legacy HTTP initialize fallback, modern/legacy stdio hook,
  page order, complete-or-absent behavior, cursor loops, cursor mutation, malformed pages,
  unmatched allowlist reporting, invalid schemas/headers, namespace collisions, refresh freshness,
  and stale marking after a recoverable refresh failure.
- [x] **Step 2: Implement paginator and broker against injected transport/protocol seams.** Keep
  profile state immutable during a transport call except the explicit stale transition. Canonical
  manifest data must include the selected protocol era/version and ordered descriptors. Do not
  add semantic search, per-turn selection, background refresh, or a resumable cursor.
- [x] **Step 3: Run the focused discovery suite.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_discovery.py tests/unit/mcp/test_mcp_discovery_binding.py -q
  uv run --frozen ruff check src/optimus_gateway/mcp_discovery.py tests/unit/optimus_gateway/test_mcp_discovery.py tests/unit/mcp/test_mcp_discovery_binding.py
  ```

## Task 4: Implement transport adapters and the profile/connection lifecycle boundary

**Files:** Create `src/optimus_gateway/mcp_transports.py`,
`src/optimus_gateway/mcp_connections.py`, `tests/unit/optimus_gateway/test_mcp_transports.py`,
`tests/unit/optimus_gateway/test_mcp_connections.py`, and platform-specific unit seams under
`tests/unit/optimus_gateway/`.

**Interfaces:**

```python
class MCPTransport(Protocol):
    def server_discover(self, *, protocol_version: str, client_meta: MCPClientMeta) -> dict[str, Any]: ...
    def tools_list(self, *, cursor: str | None, protocol_version: str, client_meta: MCPClientMeta) -> dict[str, Any]: ...
    def tools_call(self, *, upstream_tool_name: str, arguments: dict[str, Any], protocol_version: str) -> dict[str, Any]: ...
    def close(self) -> None: ...

class MCPConnectionManager:
    def open_for(self, profile: MCPProfile) -> MCPTransport: ...
    def close_profile(self, *, profile_id: str, revision: str) -> None: ...
    def close_all(self) -> None: ...
```

  The HTTP adapter must pin scheme/origin/path, require HTTPS except explicitly provisioned
  loopback, disable redirects, use per-request `_meta` for protocol/client/capabilities, and open
  no GET/SSE/session. The stdio adapter must validate image `@sha256:` syntax, fixed command and
  arguments, no host mounts/devices/Docker socket, safe `docker run --env NAME` projection with
  no `NAME=value` secret argument, no inherited Gateway/model/telemetry credentials, bounded
  30-second/default and 1 MiB/default limits, process-group/tree termination, and Windows Job
  Object plus Linux/WSL2 process-limit seams. Opening or closing a transport must not mutate
  profile lifecycle or create activation.

- [x] **Step 1: Write RED policy tests.** Assert the exact outbound method/header/version set,
  redirect and origin rejection, TLS/loopback policy, no forbidden MCP capabilities, digest-only
  images, no mount/device/socket flags, exact safe env argument vector, byte/time limits, child
  cleanup, and profile/connection-axis separation.
- [x] **Step 2: Implement the two adapters and manager.** Use injected clock, HTTP opener, Docker
  process factory, and platform process-control seams for unit tests. Do not create a project-authored
  MCP server or client fixture to make live tests pass.
- [x] **Step 3: Run focused transport and existing route regressions.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_transports.py tests/unit/optimus_gateway/test_mcp_connections.py tests/unit/optimus_gateway/test_server.py tests/unit/optimus_gateway/test_tool_handlers.py -q
  uv run --frozen ruff check src/optimus_gateway/mcp_transports.py src/optimus_gateway/mcp_connections.py tests/unit/optimus_gateway/test_mcp_transports.py tests/unit/optimus_gateway/test_mcp_connections.py
  ```

## Task 5: Add typed agent Gateway calls while preserving the local MCP trust gate

**Files:** Extend `src/optimus/gateway/client.py`, `src/optimus/mcp/runtime.py`, and
`src/optimus/guardrails/mcp_trust.py`; create `tests/unit/mcp/test_gateway_runner.py`,
`tests/unit/mcp/test_gateway_payload_boundary.py`, and update the existing runtime/trust tests.

**Interfaces:**

```python
class GatewayClient:
    def discover_mcp(self, *, request: MCPDiscoverRequest) -> MCPDiscoverResponse: ...
    def call_mcp(self, *, request: MCPCallRequest) -> MCPCallResponse: ...

class MCPGatewayRunner(Protocol):
    def discover(self, request: MCPDiscoverRequest) -> MCPDiscoverResponse: ...
    def call(self, request: MCPCallRequest) -> MCPCallResponse: ...
```

  `GatewayClient` must constrain paths to the two exact MCP routes, use the existing bearer/header
  boundary, parse typed responses, and redact authorization in representations/errors. The runtime
  flow remains `ConfigTrustScanner` → explicit manifest/descriptor trust → `MCPDescriptorExposureGuard`
  → `PreToolGuard` → typed Gateway runner. The runner payload contains only run/session/request
  context, profile ID/revision, manifest hash, namespaced tool name, and JSON arguments. It contains
  no upstream credential, endpoint, command, policy text, approval record, prompt, system message,
  conversation history, or secret-derived identifier.

- [x] **Step 1: Write RED tests for client paths and local ordering.** Cover exact route rejection,
  bearer-only headers, canonical body, invalid response errors, local denial before any Gateway
  transport call, approved call after the existing guard, binding/revision drift hold, and no
  credential leakage in payloads, repr, logs, or errors.
- [x] **Step 2: Implement typed client methods and the narrow runtime runner seam.** Preserve all
  current `MCPRuntimeTrustContext` behavior and existing `MCPTrustRegistry`/prompt-injection
  parity. If a binding adapter is added, it must bind the existing approval to `(manifest_hash,
  profile_revision)` without creating a second permission registry.
- [x] **Step 3: Run the focused agent/trust suite and one-key scans.**

  ```powershell
  uv run --frozen pytest tests/unit/gateway/test_client.py tests/unit/mcp/test_runtime.py tests/unit/mcp/test_gateway_runner.py tests/unit/mcp/test_gateway_payload_boundary.py tests/unit/guardrails/test_mcp_trust.py tests/unit/guardrails/test_pre_tool_guard.py tests/unit/guardrails/test_prompt_injection.py -q
  rg -n "OPTIMUS_LOCAL_GATEWAY_MCP|MCP.*(TOKEN|SECRET|PASSWORD|API_KEY)|upstream.*credential|credential.*identifier" src/optimus tests/unit/mcp tests/unit/gateway
  uv run --frozen ruff check src/optimus/gateway/client.py src/optimus/mcp/runtime.py src/optimus/guardrails/mcp_trust.py tests/unit/mcp
  ```

## Task 6: Implement invocation, result validation, and the two authenticated Gateway routes

**Files:** Create `src/optimus_gateway/mcp_invocation.py`,
`src/optimus_gateway/mcp_handlers.py`, update `src/optimus_gateway/server.py` and the narrow
Gateway dependency/config seams, and create `tests/unit/optimus_gateway/test_mcp_invocation.py`,
`tests/unit/optimus_gateway/test_mcp_handlers.py`, `tests/unit/optimus_gateway/test_mcp_result_policy.py`,
and update `tests/unit/optimus_gateway/test_server.py`.

**Interfaces:**

```python
class MCPInvocationBroker:
    def call(
        self,
        *,
        request: MCPCallRequest,
        registry: MCPProfileRegistry,
        connection_manager: MCPConnectionManager,
        usage_writer: MCPUsageWriter,
    ) -> MCPCallResponse: ...

MCP_ROUTE_PATHS = frozenset({
    "/v1/tools/mcp/discover",
    "/v1/tools/mcp/call",
})

def handle_mcp_request(
    *, authorization_header: str | None,
    path: str,
    request_body: Mapping[str, Any],
    config: GatewayServiceConfig,
    dependencies: GatewayMCPDependencies,
) -> tuple[int, dict[str, Any]]: ...
```

  Route order is authentication → strict typed parsing → profile/revision/manifest binding →
  Gateway allowlist and resource/budget checks → transport open → upstream `tools/call` with only
  arguments and derived upstream name → strict result validation → usage persistence → release.
  A direct bearer caller cannot widen the Gateway allowlist or invoke stale/disabled/drifted state.
  `complete` is the only releasable result; `input_required` is a typed call-scoped denial. Text,
  structured content, embedded resources, and resource links remain untrusted/inert. Image/audio
  content is not released. No result body may trigger a fetch, execute code, alter policy, approve a
  tool, or become a trusted manifest. All errors are sanitized dispositions with no raw challenge,
  credential, secret-derived ID, or unredacted server text.

- [x] **Step 1: Write RED handler/invocation tests.** Cover unauthorized, malformed, wrong route,
  inactive/stale/disabled profile, wrong revision/hash, allowlist widening, wrong namespace,
  resource/budget denial, untrusted result/content rejection, `input_required`, complete-only
  release, direct-bearer policy limits, and preservation of all existing CORE/TOOLS/observability
  route status behavior.
- [x] **Step 2: Implement the invocation broker and handlers.** Keep profile and transport state
  separate, recheck the binding immediately before dispatch, derive the internal upstream tool name
  from the validated namespace, and delegate accounting to Task 7. Add exactly the two MCP paths to
  `server.py`; unknown routes and existing `TOOL_ROUTE_PATHS` remain unchanged.
- [x] **Step 3: Run focused route/invocation tests.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_invocation.py tests/unit/optimus_gateway/test_mcp_handlers.py tests/unit/optimus_gateway/test_mcp_result_policy.py tests/unit/optimus_gateway/test_server.py tests/unit/optimus_gateway/test_tool_handlers.py -q
  uv run --frozen ruff check src/optimus_gateway/mcp_invocation.py src/optimus_gateway/mcp_handlers.py src/optimus_gateway/server.py tests/unit/optimus_gateway/test_mcp_invocation.py tests/unit/optimus_gateway/test_mcp_handlers.py tests/unit/optimus_gateway/test_mcp_result_policy.py
  ```

## Task 7: Add additive MCP usage accounting and persistence-before-release

**Files:** Create or extend `src/optimus_gateway/mcp_usage.py`,
`tests/unit/optimus_gateway/test_mcp_usage.py`, `tests/unit/optimus_gateway/test_mcp_accounting.py`,
and the Gateway Redis test support used by the existing tool-state seam. Do not modify existing
`GatewayUsage`/`ProviderUsage` semantics.

**Interfaces:**

```python
class MCPUsageRecord(BaseModel):
    gateway_request_id: str
    run_id: str
    session_id: str | None
    request_id: str
    profile_id: str
    profile_revision: str
    namespaced_tool_name: str
    upstream_tool_name: str
    transport: Literal["http", "stdio"]
    disposition: str
    attribution: Literal["settled", "explicit_zero", "unavailable"]
    duration_ms: int
    request_bytes: int
    response_bytes: int
    provider_request_id: str | None
    billing_units: int | None
    cost_usd: Decimal | None

class MCPUsageWriter(Protocol):
    def persist(self, record: MCPUsageRecord) -> None: ...
```

  `MCPUsageWriter` must accept an identical same-ID replay, reject a divergent same-ID record, and
  expose a typed unavailable/persistence failure. The invocation broker calls `persist` after the
  upstream response is validated and before releasing it. If persistence fails, the response is
  withheld and the Gateway never redispatches; recovery retries persistence only with the same
  `gateway_request_id`. Settled monetary fields are copied from authoritative upstream/Gateway
  data. Explicit zero is valid only when bound to the profile revision’s declared free policy.
  Unavailable is not normalized to `0` and is not reconciled as settled spend. Discovery/list
  retries are capped at three; call retries are never automatic. Post-dispatch timeout or loss is
  indeterminate: read-only may be explicitly re-invoked, side-effecting calls are held durably for
  operator acknowledgement.

**Closure note (2026-08-06):** Task 7 closes on the delivered accounting core and the existing
fail-closed invocation behavior: calls are never automatically redispatched or retried, and
indeterminate outcomes surface as explicit errors. Durable effect-aware custody and re-invocation
(read-only explicit re-invocation plus side-effecting operator-acknowledgment hold across agent
restart) is deferred to the named backlog entry
[`Durable effect-aware MCP indeterminate-call custody`](../2026-07-23-consolidated-deferred-followups-backlog.md#durable-effect-aware-mcp-indeterminate-call-custody),
which requires a `PreToolGuard` approval-store extension.

- [x] **Step 1: Write RED accounting tests.** Cover all three attribution states, strict-dollar
  admission, explicit-zero revision binding, identical/divergent duplicate records, persistence
  failure without redispatch, the no-automatic-call-retry and explicit-indeterminate-error
  behavior, byte/duration fields, and sanitized error paths. Discovery/list retry capping remains
  covered by the Task 3 discovery tests. Durable effect-aware indeterminate custody and
  re-invocation are deferred to the named backlog entry above.
- [x] **Step 2: Implement the immutable record and Gateway-owned store.** Use a direct Gateway-side
  Redis boundary for live persistence; do not import `optimus.*` or reuse the agent’s Redis runtime.
  Preserve existing Plan 11.2 tool-state keys and TTL behavior. Make the route’s release decision
  depend on the same store result that records the response’s `gateway_request_id`.
- [x] **Step 3: Run focused accounting tests.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_usage.py tests/unit/optimus_gateway/test_mcp_accounting.py tests/unit/optimus_gateway/test_tool_state.py tests/unit/gateway/test_usage_fields.py -q
  uv run --frozen ruff check src/optimus_gateway/mcp_usage.py src/optimus_gateway/mcp_invocation.py tests/unit/optimus_gateway/test_mcp_usage.py tests/unit/optimus_gateway/test_mcp_accounting.py
  ```

## Task 8: Exercise the complete local Gateway flow with real named dependencies

**Files:** Create `tests/integration/optimus_gateway/test_gateway_mcp_live.py`,
`tests/integration/optimus_gateway/test_gateway_mcp_redis_live.py`, extend
`tests/integration/optimus_gateway/gateway_env.py` only for Gateway-child configuration, register
`requires_mcp_http` and `requires_mcp_stdio` in `pyproject.toml` if they are not already present,
and produce the named reports under `reports/`.

**Interfaces and evidence:** The integration tests must start the real Gateway process through the
existing signed-manifest launch path or an equivalent real `serve_gateway` process, drive the two
typed routes through `GatewayClient`, and retain the existing local trust path. They must not
implement an MCP server or MCP client in this repository. Configure the real independent fixtures
through these execution-only values: `OPTIMUS_MCP_HTTP_TEST_URL`, `OPTIMUS_MCP_HTTP_TEST_BEARER`,
`OPTIMUS_MCP_STDIO_IMAGE_DIGEST`, `OPTIMUS_MCP_STDIO_CREDENTIAL_REF`, and the existing Gateway
secret/configuration mechanism. Raw values must be redacted from reports.

- [x] **Step 1: Add RED integration coverage and markers.** Add `requires_mcp_http` and
  `requires_mcp_stdio` to the `markers` list and add both `and not requires_mcp_http` and
  `and not requires_mcp_stdio` clauses to the default `addopts -m` deselection expression before
  marking tests precisely:
  `requires_gateway` for approved real Gateway credentials, `requires_mcp_http` for the actual
  independent HTTP server, `requires_mcp_stdio` for the actual independent digest-pinned Docker
  server, and `requires_redis` for the actual TimeSeries-capable Redis. A skipped/deselected tier
  is not a passing evidence claim.
- [ ] **Step 2: Implement the independent-dependency harness.** Prove pending registration →
  complete discovery → local explicit approval → restart activation → refresh → call; multi-page
  complete-or-absent behavior; cursor integrity; stale/revision drift; profile/connection-axis
  separation; direct bearer denial; result validation; accounting-before-release; and no
  redispatch after persistence failure. The HTTP case must prove the exact 2026-07-28 method set.
  The stdio case must prove digest pinning, no mounts/devices/socket, safe credential projection,
  modern/legacy discovery-first negotiation, bounded output, and deterministic teardown.
- [ ] **Step 3: Run real Windows tiers and write sanitized reports.**

  ```powershell
  uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_mcp_live.py -m "requires_gateway and requires_mcp_http" -q
  uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_mcp_live.py -m "requires_gateway and requires_mcp_stdio" -q
  uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_mcp_redis_live.py -m requires_redis -q
  ```

  Write `reports/plan-11-8-gateway-mcp-discovery.md`,
  `reports/plan-11-8-gateway-mcp-transport.md`,
  `reports/plan-11-8-gateway-mcp-split-authority.md`, and
  `reports/plan-11-8-gateway-mcp-accounting.md` with commit, test counts, real dependency identity,
  image digest, request/response summaries, exit codes, and redaction checks.
- [ ] **Step 4: Run the existing Gateway regression suites.**

  ```powershell
  uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_live_smoke.py tests/integration/optimus_gateway/test_gateway_tools_live.py tests/integration/gateway/test_gateway_live.py tests/integration/optimus_gateway/test_gateway_tool_state_live.py -q
  ```

  Expected: existing web/package/advisory/core/observability behavior remains green and MCP
  configuration is not required for those routes.

## Task 9: Prove Context7, external ACP compatibility, WSL2/Linux containment, and release fitness

**Files:** Create `tools/run_plan118_acpx_gateway_mcp_evidence.py`, its unit command-construction
test, the named live evidence report files, and update only stale current-state documentation
identified by the audit. Use the separate WSL worktree defined in Global Constraints.

- [ ] **Step 1: Run the real Gateway-originated Context7 probe.** Configure the actual intended
  Context7 endpoint as a Gateway-owned HTTP profile and invoke only
  `POST /v1/tools/mcp/discover` and, if discovery proves the floor and tool, the narrow call route
  through the Gateway. The probe must verify `server/discover` support for `2026-07-28`, the tools
  capability, complete `tools/list`, namespace/allowlist output, and a sanitized disposition. It
  must not use a substitute server or project-authored upstream MCP client. Write
  `reports/plan-11-8-gateway-mcp-context7-live.md`; if the actual endpoint does not prove the
  floor, record `mcp.protocol_version_unsupported` and leave Context7 support unclaimed.

  ```powershell
  uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_mcp_live.py -m "requires_gateway and requires_mcp_http" -k context7 -q
  ```

- [ ] **Step 2: Run independent ACP evidence through external `acpx`.** The new evidence tool may
  manage process startup and report parsing, but the ACP protocol driver must be the independently
  authored `acpx` binary, not a project-authored ACP client. The task must assert Gateway-only
  agent environment (`OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`), expected MCP tool exposure,
  local trust denial/approval, typed result, usage disposition, and absence of upstream credentials.

  ```powershell
  command -v acpx
  uv run --frozen python tools/run_plan118_acpx_gateway_mcp_evidence.py --workspace . --task "Use the approved MCP tool and return a one-sentence result." --report reports/plan-11-8-gateway-mcp-acpx-live.md
  ```

  Record the external `acpx` identity/version, agent/Gateway commit, child environment key census,
  exit code, result shape, and sanitized output. A project-authored ACP subprocess harness cannot
  discharge this evidence.

- [ ] **Step 3: Reproduce Docker process containment in the separate WSL2 worktree.** Create the
  separate WSL worktree only after approval, sync the frozen dependencies, and run the same focused
  stdio/platform suite from Ubuntu-24.04:

  ```powershell
  git worktree add -b agent/codex/plan-11-8-p11-feat-gateway-mcp-wsl D:\Projects\Development\Python\optimus-cost-agent-wt-codex-wsl agent/codex/plan-11-8-p11-feat-gateway-mcp
  wsl.exe -d Ubuntu-24.04 -- bash -lc "cd /mnt/d/Projects/Development/Python/optimus-cost-agent-wt-codex-wsl && uv sync --frozen --extra dev && uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_mcp_live.py -m 'requires_mcp_stdio' -q && uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_transports.py tests/unit/optimus_gateway/test_mcp_connections.py -q"
  ```

  The report must identify the distro, kernel, Docker engine, image digest, child PID/process
  limits, teardown observation, exit codes, and whether the assertion was Windows Job Object or
  Linux process-group/limit evidence. Write `reports/plan-11-8-gateway-mcp-wsl2-live.md`. Do not
  claim Linux enforcement from Windows or a unit fake.

- [ ] **Step 4: Run final credential, scope, documentation, and fitness gates.** Audit every current
  state document that may be affected, including `README.md`,
  `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`,
  `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, the P11 charter, and `.env.gateway.example`.
  Update only statements made stale by the implementation; retain deferred custody with named
  owners. Then run:

  ```powershell
  rg -n "P11-FEAT-GATEWAY-MCP|P11-FU-9|P11-FU-12|P11-FU-13|P11-FU-14|P11-FU-15|MCPUsageRecord|/v1/tools/mcp/(discover|call)|OPTIMUS_LOCAL_GATEWAY_MCP|OPENAI_API_KEY|OPENROUTER_API_KEY|TAVILY_API_KEY" README.md .env.example .env.gateway.example docs/superpowers/plans src tests tools
  uv run --frozen pytest -q
  uv run --frozen pytest --cov=src/optimus --cov=src/optimus_gateway --cov=src/optimus_security --cov-report=term-missing --cov-fail-under=80
  uv run --frozen ruff check .
  git diff --check
  git status --short --branch
  ```

  The final report `reports/plan-11-8-gateway-mcp-release.md` must list every executed tier and
  artifact, coverage, Ruff, diff hygiene, credential scan, direct-route denial, Context7 result,
  WSL2 result, and any explicitly unclaimed capability. No report may claim a skipped tier.

## Four-authoritative-document requirement traceability

| Authority | Exact section/page | Implementation obligation | Task/evidence |
|---|---|---|---|
| HLD v2.17 | §5A p.3 | Agent has only Gateway URL/shared key; Gateway owns profile-scoped MCP credentials and separate MCP usage. | 2, 5, 7, 8, 9; credential report |
| HLD v2.17 | §§6–7 pp.4–5 | Approved call is a guarded branch; binding/manifest/arguments cross to Gateway; Gateway rechecks profile/allowlist/resource/connection. | 5–6, 8; split-authority report |
| HLD v2.17 | §11 p.10; §11.1 p.11; §§11A–12 p.12 | Gateway owns routes, profile state, transports, credentials, untrusted results, accounting, and transport/trust tests. | 2–8; live reports |
| LLD v2.40 | §§0/0A pp.2–5; §0D p.3 | Tools-only static profiles, two transports, zero upstream agent credentials, typed routes/components, no arbitrary proxy. | 1–6, 9; contract report |
| LLD v2.40 | §§9C–9C.4 pp.26–29 | Extend existing typed Gateway/client seam while preserving existing web/package/advisory boundaries. | 5–6, 8; regression suite |
| LLD v2.40 | §9D p.30 | Gateway independently validates active profile, binding pair, freshness, allowlist, resource, and budget. | 2–3, 6, 8 |
| LLD v2.40 | §§9E–9E.1 pp.31–32 | Separate MCP usage, complete-only release, inert content, three attribution states, persistence-before-release. | 1, 6–8; accounting/results reports |
| LLD v2.40 | §§11–11A pp.36–38; §12B p.39 | Real dependencies, independent ACP, Context7 probe, coverage, split trust, reapproval, and indeterminate holds. | 2, 5, 8–9 |
| Guardrails v1.2 | §5 pp.8–9; §7.3 p.10 | Preserve deterministic MCP/config trust, prompt-injection parity, indeterminate holds, and profile/connection separation. | 2, 5–6; split-authority report |
| Guardrails v1.2 | §8.3 p.11 | Tools-only capability table, request-scoped HTTP, Docker-contained stdio discovery-first negotiation. | 3–4, 8–9; transport report |
| Guardrails v1.2 | §§9–10.2 pp.12–13; §11.2 p.14 | Separate accounting and required protocol/trust/isolation/error/platform tests. | 4, 7–9; accounting/transport/release reports |
| Guardrails v1.2 | §13 p.16 | Preserve document control, cross-reference, and review/freshness obligations. | 0, 9; release report |
| Test Strategy v1.6 | §§1/3 pp.2–3; §6 p.5 | Real dependency tiers, zero upstream credentials, exact remote method set, stdio negotiation, independent ACP. | 8–9; named live reports |
| Test Strategy v1.6 | §§7–8 pp.6–8 | Egress, lifecycle/cache, credential isolation, accounting, and unknown-cost handling. | 2, 4, 7–9 |
| Test Strategy v1.6 | §§9–10 pp.9–10 | Retry/failure taxonomy and schema/result validation. | 3, 6–7 |
| Test Strategy v1.6 | §§11–13 pp.10–12; §14.10 p.14 | Security/trust, golden tasks, Phase 1 release gates, and exact traceability evidence. | 5, 8–9; release report |

## Deferred-work custody and explicit exclusions

| Excluded capability | Owning roadmap entry | This plan’s enforcement boundary |
|---|---|---|
| Client-supplied ACP `mcpServers` | P11-FU-9 | No client-nominated server configuration or direct agent MCP connection path. |
| OAuth 2.1 lifecycle | P11-FU-12 | Static credential references only; reject OAuth fields and flows. |
| Prompts, resources as operations, elicitation, completion, subscriptions, tasks, progress, roots, sampling, external MCP logging, long-lived interaction, resumable discovery cursors | P11-FU-13 | Only tools/list and tools/call; resource content is inert; no session/resume channel. |
| Catalog/discover-and-connect/autoload/install/update | P11-FU-14 | Operator provisioning and signed restart only; no registry or runtime admin route. |
| Semantic per-turn tool selection/context minimization/code mode | P11-FU-15 | Operator allowlist and deterministic descriptor filtering only. |
| ACP resume/registry feature | Existing separate ACP/Zed/registry roadmap entries | Do not reuse or extend this plan’s MCP profile registry for ACP session state. |

## Definition of Done for implementation

- [ ] Task 0 records the re-verified design/PDF digests from committed bytes and blocks on mismatch.
- [ ] The two exact typed routes exist and no arbitrary MCP-method route, admin route, or deferred
  capability has been added.
- [ ] The six named LLD Gateway components exist with the responsibilities and import boundaries
  above: `MCPProfileRegistry`, `MCPDiscoveryBroker`, `MCPDiscoveryPaginator`,
  `MCPInvocationBroker`, `MCPConnectionManager`, and the additive `MCPUsageRecord` path.
- [ ] Static profiles, revisions, lifecycle, startup activation, credentials, allowlists, and
  transport policy fail closed and cannot be widened by a direct bearer caller.
- [ ] The existing local MCP trust/runtime/guardrail path remains mandatory for the agent flow and
  binds approval to the profile revision and manifest hash.
- [ ] Remote HTTP and Docker stdio satisfy the exact protocol, containment, credential projection,
  bounds, and teardown rules, with real Windows and WSL2 evidence before claiming platform support.
- [ ] Discovery is complete-or-absent, namespaced, allowlist-filtered, cursor-integrity checked,
  freshness-aware, and capped at three transient discovery/list attempts.
- [ ] Calls forward only JSON arguments, release only validated `complete` results after usage
  persistence, treat all returned content as untrusted, never auto-retry, and durably hold
  indeterminate side-effecting calls.
- [ ] `MCPUsageRecord` preserves settled/explicit-zero/unavailable attribution, never treats
  unavailable cost as zero, is idempotent on `gateway_request_id`, and never redispatches after a
  persistence failure.
- [ ] Real `requires_redis`, `requires_gateway`, `requires_mcp_http`, `requires_mcp_stdio`,
  external `acpx`, Windows, WSL2, and Context7 evidence is either passing with a named artifact or
  explicitly unclaimed; fake tests cannot substitute for a named live tier.
- [ ] The one-key credential scan, full suite, 80% aggregate coverage, Ruff, diff hygiene, and
  current-state documentation audit pass. Deferred custody remains named and unchanged.
- [ ] The reviewer checkpoint log is updated by the reviewing agent, remains gitignored, and is
  never staged. Only after operator approval may implementation commits be made.
