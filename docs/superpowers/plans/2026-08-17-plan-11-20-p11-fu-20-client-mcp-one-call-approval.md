# Plan 11.20 — P11-FU-20 Client-MCP One-Call Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` or `superpowers:executing-plans` task-by-task, and `superpowers:test-driven-development` for every production behavior change. Steps use checkbox syntax. Do not mark a checkbox complete until its stated verification command has passed.

**Goal:** Make an ACP client’s approved one-call write permission issue the real, identity- and argument-bound `ClientMcpOneCallApproval`, while retaining a fail-closed response when that session has no matching registered authorizer.

**Architecture:** Keep `ClientMcpDisposition.disposition_for_new_session()` as a lease-and-permission decision only: it neither opens transport nor discovers catalogs. Once the already-authorized session’s lazy catalog/service path has a real identity-bound catalog, it creates and registers the real `ClientMcpToolService` and its `ClientMcpCallAuthorizer` in the same `ClientMcpSessionState.tool_service` registry. The ACP adapter’s broker closure resolves the matched registered service/authorizer and asks it to issue the approval; `PreToolGuard` remains the operation-entry authority that consumes the resulting token.

**Tech Stack:** Python 3.14, existing `optimus.acp`, `optimus.mcp.client_catalog`, `optimus.mcp.client_disposition`, `optimus.guardrails.pre_tool`, pytest, pytest-asyncio, coverage.py, Ruff, and the existing independently authored `acpx` live-client tier.

## Authority and source anchors

- The open-work entry `P11-FU-20` in `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md:1426-1469` is this plan’s custody source.
- The frozen P11-FU-9 design body is retained unchanged. Its §3/session-new contract makes disposition transport-free; its §5 keeps the ordinary per-call `PreToolGuard`/ACP approval control for write tools.
- The baseline anchors exist at this plan’s drafting commit: `AcpDuplexAdapter._mcp_permission_broker_for` in `src/optimus/acp/spec.py:554`, `ClientMcpDisposition.disposition_for_new_session` in `src/optimus/mcp/client_disposition.py:127`, and `test_spec_mcp_broker_issue_fails_closed_until_catalog_authorizer_attached` in `tests/unit/acp/test_spec_protocol.py:1502`.
- This is an independent Plan 11.20 slice, not an in-place amendment to frozen P11-FU-9. The pool entry is scheduled to this plan before implementation; frozen P11-FU-9 plan/spec bytes remain immutable.

## Global Constraints

- Cut the implementation worktree and branch from refreshed `origin/main`; prove `HEAD == origin/main` before its first write. Never use `optimus-cost-agent-wt-vibhanshu` or this planning branch.
- Preserve the local-first, one-key model. No local provider, Gateway, MCP, or Phoenix credential is introduced, logged, serialized, or placed in a prompt, tool output, or persistent state.
- `disposition_for_new_session()` must not call SDK `open`, `discover`, `call`, or a service factory that opens transport. It may normalize input, request the existing allow-once transport lease, and retain safe per-session state only.
- A client-supplied server remains untrusted until the existing transport lease, safe identity, bounded discovery, descriptor scan, and client-session authorization paths admit it. Do not add a manifest or bypass `PreToolGuard`.
- An unregistered server, unknown server/tool, mismatched session/identity/arguments, rejected/timeout/outbound-failure ACP response, or consumed token remains fail closed. Never construct a `ClientMcpOneCallApproval` directly in ACP adapter code.
- `PreToolGuard.check()` remains at `ClientMcpToolService.call_tool()` operation entry before dispatch. The broker issues a token after ACP approval; it does not authorize or dispatch a tool itself.
- Preserve the four P11-FU-9 boundaries: static `mcp_list_tools`/`mcp_call` model surface, non-serializable runtime service, no automatic retry/replay, and untrusted/sanitized tool output.
- Unit tests may use controlled dispatch behavior, but wiring evidence must construct the actual `AcpDuplexAdapter`, `ClientMcpSessionState`, registry, `ClientMcpToolService`, `ClientMcpCallAuthorizer`, and `PreToolGuard` classes. A hand-fed `AcpMcpPermissionBroker(issue_approval=...)` double cannot satisfy the adapter-wiring claim.
- Mark any skipped real-dependency tier as unrun, never as passed. Before commit, push, or PR sign-off run `uv run --frozen ruff check .`; preserve aggregate production-code coverage of at least 80%.

## File Map

| Path | Implementation responsibility |
|---|---|
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Schedule P11-FU-20 to Plan 11.20, then close it only after its own evidence is complete. |
| `tests/unit/docs/test_open_work_pool_hygiene.py` | Enforce Plan 11.20 custody and prevent a P11-FU-9 historical closure from being credited as this fix. |
| `src/optimus/mcp/client_catalog.py` | Expose the narrow real-authorizer issuance operation through the identity-bound session/service registry without making it serializable or an alternate policy authority. |
| `src/optimus/mcp/client_disposition.py` | Retain per-server lease/identity state and connect the existing lazy catalog/service materialization to `ClientMcpSessionState.tool_service`, without transport use in disposition. |
| `src/optimus/acp/spec.py` | Resolve the adapter broker’s request through the session’s registered real authorizer; return `None` when no exact registered authorizer exists. |
| `tests/unit/mcp/test_client_disposition.py` | Prove disposition itself remains transport-free while approved sessions can hold the required later materialization state. |
| `tests/unit/mcp/test_client_catalog.py` | Prove registry lookup/issuance is server-, session-, tool-, and canonical-argument-bound and cannot issue through an absent or mismatched service. |
| `tests/unit/acp/test_spec_protocol.py` | Drive the actual ACP adapter closure from lease/service registration through an ACP allow and a token consumed by the real `PreToolGuard`. |
| `tests/e2e/test_client_mcp_acpx.py` and existing client-MCP live evidence/report locations | Later, independently authored ACP-client evidence only; no live invocation belongs to this planning package. |

## Explicit Exceptions and Custody

| Excluded work | Disposition / named owner |
|---|---|
| `session/load` advertising, temporary advertisement probes, and Zed behavior | Out of scope; `P11-FEAT-ZED-RESUME` owns it. This plan must not change ACP session capabilities. |
| New MCP transports, HTTP/SSE capability relaxation, authentication, SDK/dependency changes, retries, or replay | Out of scope; retain their existing P11-FU-9 / client-MCP backlog custody. |
| Descriptor pinning/allowlists and dynamic descriptor-to-model-tool promotion | Out of scope; retain the named P11-FU-9 deferred entries. |
| A fresh-empty-`Context()` trace grouping concern | Out of scope; `P11.5-FU-1`/Plan 11.21 Task 8 watch ownership remains unchanged. |
| Real client-MCP, `acpx`, Docker/HTTP, Gateway, Phoenix, credential-store, or GUI runs | Not run by this plan’s drafting package. The implementer records any selected real tier as executed or unrun and retains its named evidence/disposition. |

## Tasks

### Task 0: Establish isolated custody and a behavior baseline

**Files:** Modify `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`, `tests/unit/docs/test_open_work_pool_hygiene.py`; create `reports/plan-11-20-p11-fu-20-baseline.md`.

**Interfaces:** Consumes the P11-FU-20 entry and baseline anchors. Produces a Plan 11.20-scheduled row, a baseline SHA, and a hygiene assertion that P11-FU-20 cannot close from P11-FU-9’s old evidence.

- [ ] **Step 1: Create and prove the implementation checkout.**

  ```powershell
  git fetch origin main
  git worktree add -b agent/cursor/plan-11-20-client-mcp-one-call ..\optimus-cost-agent-wt-cursor-11-20 origin/main
  git -C ..\optimus-cost-agent-wt-cursor-11-20 status --short --branch
  git -C ..\optimus-cost-agent-wt-cursor-11-20 rev-parse HEAD
  git -C ..\optimus-cost-agent-wt-cursor-11-20 rev-parse origin/main
  ```

  Expected: clean checkout and equal hashes. Stop for drift, unrelated edits, or a review-checkpoint contradiction.

- [ ] **Step 2: Write a documentation-custody RED test.**

  Parse both the pool index and P11-FU-20 detail text. Require `Scheduled` plus `Plan 11.20`, and reject closure wording that cites only the frozen P11-FU-9 Task 6 seam or a fabricated token.

  ```powershell
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  ```

  Expected: FAIL while P11-FU-20 is open and unscheduled. If it passes first, stop and repair the projection rather than treating an unrelated row as proof.

- [ ] **Step 3: Schedule only P11-FU-20 and record the baseline.**

  Update only its status to `Scheduled — Plan 11.20`; retain the original diagnosis and all other entries. Record committed-base SHA, exact anchors, existing fail-closed result, and the fact that no transport opens during disposition.

- [ ] **Step 4: Prove the custody change and commit it separately.**

  ```powershell
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  git diff --check
  git add docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md tests/unit/docs/test_open_work_pool_hygiene.py reports/plan-11-20-p11-fu-20-baseline.md
  git commit -m "docs: schedule client MCP one-call approval fix"
  ```

### Task 1: Specify the real session-registry issuance seam with RED tests

**Files:** Modify `src/optimus/mcp/client_catalog.py`, `tests/unit/mcp/test_client_catalog.py`.

**Interfaces:** Consumes `PreToolRequest` with `mcp_authority="client_session"`, server, tool, session, and argument mapping. Produces a registry/service method that delegates only to the matched `ClientMcpCallAuthorizer.issue_one_call_approval(session_id=..., tool_name=..., arguments=...)`, or `None`.

- [ ] **Step 1: Add focused RED cases against real catalog primitives.**

  Construct a real `ClientMcpCatalog`, `ClientMcpSessionLease(effect_ceiling="side_effect_eligible")`, `ClientMcpCallAuthorizer`, `PreToolGuard`, concrete test-only `ClientMcpToolService`, and `ClientMcpSessionService`. Assert successful issuance is bound to exact session, server fingerprint, tool, and `arguments_digest`; then assert absent server/service, wrong server, wrong session, and non-client request return `None` without creating a token.

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_catalog.py -q
  ```

  Expected: FAIL because the registry lacks a real issuance entry point.

- [ ] **Step 2: Add the narrow delegation operation.**

  Add a public registry operation whose only inputs are a `PreToolRequest` and the existing service mapping. It selects by `request.mcp_server_id`, rejects missing/non-`client_session` fields, and delegates to a service-private authorizer method that passes the request’s existing session/tool/argument values to `issue_one_call_approval`. It must not create token text, choose an identity fingerprint, call dispatch, or call `guard.check()` itself.

- [ ] **Step 3: Prove binding, no fabrication, and guard placement.**

  Extend the RED cases to show the issued token is accepted exactly once by the real service’s existing `PreToolGuard.check()` operation-entry path and that replay/mismatch is blocked by the existing authorizer. Include an assertion that issuance did not call `_dispatch`.

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_catalog.py tests/unit/guardrails/test_pre_tool_guard.py -q
  git diff --check
  ```

  Expected: green focused suite; guard remains the sole operation-entry decision point.

- [ ] **Step 4: Commit the registry seam.**

  ```powershell
  git add src/optimus/mcp/client_catalog.py tests/unit/mcp/test_client_catalog.py
  git commit -m "fix: expose bound client MCP approval issuance"
  ```

### Task 2: Attach the real per-server service only after lazy catalog materialization

**Files:** Modify `src/optimus/mcp/client_disposition.py` and the existing production lazy catalog/service composition seam identified from the Task 2 RED; modify `tests/unit/mcp/test_client_disposition.py` and its direct composition tests.

**Interfaces:** Consumes an allow-once lease, durable ceiling where present, safe identity/fingerprint, and an admitted bounded catalog. Produces exactly one identity-bound `ClientMcpToolService` registered under that catalog’s server name in that session’s `ClientMcpSessionState.tool_service`.

- [ ] **Step 1: Write the transport-free disposition RED and a later-materialization RED.**

  Reuse a probe whose `open()` fails if invoked. Drive an allow-once `disposition_for_new_session()` with a side-effect-eligible durable record. Assert it returns a lease and no transport use. Separately invoke the existing lazy catalog/service materialization path with a controlled admitted catalog and assert the actual session registry receives the real service for only that leased identity.

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_disposition.py -q
  ```

  Expected: the later-registration assertion fails on the baseline; the disposition probe remains at zero opens. A first-run pass means the test has not reached the actual session registry and must be repaired.

- [ ] **Step 2: Make registration a consequence of successful lazy materialization.**

  Thread the existing `ClientMcpSessionState` (not a serializable copy) through the existing lazy catalog/service composition boundary. After the catalog passes existing scan/budget checks, create the production concrete `ClientMcpToolService` with the same catalog, lease/durable identity, authorizer, and `PreToolGuard` used for dispatch, then call `state.tool_service.register(service)`. Registration must occur before that service becomes available to `mcp_list_tools`/`mcp_call`.

  Do not put catalog discovery, SDK open, or a transport call into `disposition_for_new_session`; rejected, timeout, unavailable, and no-catalog paths register nothing.

- [ ] **Step 3: Prove isolation and no transport regression.**

  Cover two sessions and two server names. Assert a service/token in one session cannot be found or consumed in another, an unavailable server stays unregistered, and the `RecordingTransportProbe` sees zero calls during every disposition branch.

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_disposition.py tests/unit/mcp/test_client_catalog.py -q
  git diff --check
  ```

- [ ] **Step 4: Commit the lazy registration behavior.**

  ```powershell
  git add src/optimus/mcp/client_disposition.py src/optimus/mcp tests/unit/mcp/test_client_disposition.py tests/unit/mcp/test_client_catalog.py
  git commit -m "fix: register client MCP authorizers after discovery"
  ```

### Task 3: Route ACP broker issuance through the real session registry

**Files:** Modify `src/optimus/acp/spec.py`, `tests/unit/acp/test_spec_protocol.py`.

**Interfaces:** Consumes `AcpDuplexAdapter._mcp_permission_broker_for(session)` and a real `PreToolRequest`. Produces an `AcpMcpPermissionBroker` whose `_issue` closure returns the registry-issued approval or `None`.

- [ ] **Step 1: Replace the current fail-closed-only test with two RED paths.**

  Preserve the existing no-authorizer assertion verbatim in substance: a real adapter/session with no registered service returns `None` and exposes no token. Add a separate fixture that drives the actual adapter/session registry to a real registered service, obtains the broker via `_mcp_permission_broker_for`, and asserts its internal issuance returns a real token bound to `tools`, `write_thing`, the session, and `{"x": 1}`.

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_spec_protocol.py::test_spec_mcp_broker_issue_fails_closed_until_catalog_authorizer_attached -q
  ```

  Expected: the registered-service half fails before the ACP adapter edit; the no-authorizer half stays green.

- [ ] **Step 2: Replace only the fabricated/fail-closed closure body.**

  In `_mcp_permission_broker_for`, keep the existing session-null and outbound ACP request behavior. Make `_issue(request)` delegate to `session.client_mcp_state.tool_service`’s new narrow registry operation. It returns `None` for no state, no service, mismatched identity, or unsupported request; it never imports token generation or directly calls a test callback.

- [ ] **Step 3: Drive allow → token → real guard ALLOW through the adapter closure.**

  In the same ACP protocol test, use an allow-once result for the write permission, pass the returned token to the actual registered `ClientMcpToolService.call_tool`, and assert the real `PreToolGuard` yields `ALLOW` for a write-classified tool under `side_effect_eligible`. Assert a second use of the same token blocks and that no user arguments/credentials appear in the safe output or audit subject.

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_spec_protocol.py tests/unit/mcp/test_client_catalog.py tests/unit/guardrails/test_pre_tool_guard.py -q
  git diff --check
  ```

- [ ] **Step 4: Commit the ACP wiring correction.**

  ```powershell
  git add src/optimus/acp/spec.py tests/unit/acp/test_spec_protocol.py
  git commit -m "fix: issue client MCP approvals through session authorizers"
  ```

### Task 4: Verify real-dependency disposition and preserve honest evidence

**Files:** Modify existing `tests/integration/mcp/test_client_mcp_live.py` and/or `tests/e2e/test_client_mcp_acpx.py` only where the current real tier lacks the one-call flow; create `reports/plan-11-20-p11-fu-20-evidence.md`.

**Interfaces:** Consumes the implementation SHA, independently authored `acpx`, and the existing real client-MCP fixture. Produces a sanitized, content-free disposition for the real one-call flow or an explicit unrun/blocked record.

- [ ] **Step 1: Add a real-tier assertion before any live run.**

  Require the existing independently authored ACP client to drive `session/new`, a transport allow-once response, a guarded write call, its separate one-call allow, and a terminal result. The verifier records only client version/path digest, safe server/tool names, token presence/consumption boolean, protocol disposition, and implementation SHA; never a token, configuration, header, argument, or transcript body.

- [ ] **Step 2: Run the tier only in its approved environment.**

  ```powershell
  uv run --frozen pytest -m requires_acpx tests/e2e/test_client_mcp_acpx.py -q
  uv run --frozen pytest -m requires_mcp_stdio tests/integration/mcp/test_client_mcp_live.py -q
  ```

  Record each command as passed, failed, or unrun. A marker deselection/skip is unrun. Do not replace this claim with a project-authored ACP harness or a fake SDK client.

- [ ] **Step 3: Write the claim-to-evidence report.**

  Map lease/service registration, fail-closed absence, exact one-call binding/consumption, no `session/new` transport, and real-tier disposition to focused test nodes, command outputs, and sanitized artifact locations. If the live tier cannot run under its real dependency contract, leave P11-FU-20 open with that named residual; do not claim closure.

### Task 5: Close custody only with complete evidence and freshness audit

**Files:** Modify the pool on pass only; create `reports/plan-11-20-p11-fu-20-release.md`; audit `README.md`, roadmap, charter, runbooks, and current-state references without rewriting frozen artifacts.

**Interfaces:** Consumes all task evidence. Produces a truthful P11-FU-20 closure or an explicitly open row with its remaining owner.

- [ ] **Step 1: Perform the documentation freshness audit.**

  ```powershell
  rg -n "P11-FU-20|one-call|ClientMcpOneCallApproval|mcp.client.one_call_unknown|Plan 11.20" README.md docs reports
  ```

  Classify each result as current state to update, historical/frozen provenance to retain, or evidence. Do not edit frozen P11-FU-9 files.

- [ ] **Step 2: Apply the evidence-gated closure decision.**

  Set P11-FU-20 to `Closed — Plan 11.20` only if the real adapter closure, fail-closed absence, transport-free disposition, real `PreToolGuard` consumption, focused tests, and selected real tier all have passing named evidence. Otherwise retain `Scheduled — Plan 11.20` and name the missing tier/evidence exactly.

- [ ] **Step 3: Run final fitness and immutable-artifact checks.**

  ```powershell
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py tests/unit/mcp/test_client_catalog.py tests/unit/mcp/test_client_disposition.py tests/unit/acp/test_spec_protocol.py tests/unit/guardrails/test_pre_tool_guard.py -q
  uv run --frozen coverage run -m pytest
  uv run --frozen coverage report --fail-under=80
  uv run --frozen ruff check .
  git diff --check
  git diff --name-only origin/main...HEAD
  git show HEAD:docs/superpowers/plans/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-implementation.md | sha256sum
  git status --short --branch
  ```

  Expected: relevant tiers green, coverage at least 80%, Ruff/diff clean, and the frozen plan digest taken from its committed blob. Record any deselected marker as unrun.

- [ ] **Step 4: Commit only truthful release material and request review.**

  ```powershell
  git add docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md reports/plan-11-20-p11-fu-20-release.md
  git commit -m "docs: record client MCP approval evidence"
  git push -u origin agent/cursor/plan-11-20-client-mcp-one-call
  ```

  Stage only files that changed. Do not stage a reviewer checkpoint log, live scratch output, credentials, tokens, or frozen-plan edits.

## Definition of Done and Evidence Map

| Claim | Required evidence |
|---|---|
| P11-FU-20 has independent scheduled/closure custody | Task 0/5 pool hygiene RED-green and P11-FU-20-only report links |
| `session/new` never opens MCP transport | Task 2 controlled probe across allow/reject/timeout/unavailable branches |
| A matching service is real, per-server, and session-isolated | Task 2 real state/registry composition tests |
| ACP cannot fabricate an unbound approval | Task 3 actual adapter closure plus no-authorizer `None` test |
| Token is bound and one-call-only | Task 1/3 real authorizer digest, mismatch, and replay assertions |
| `PreToolGuard` remains operation-entry authority | Task 1/3 service-call assertions and unchanged guard branch |
| ACP/protocol claim does not rest on a project-authored client | Task 4 `acpx` run or explicit unrun disposition |
| No safety or documentation regression | Task 5 focused suite, coverage, Ruff, diff check, frozen committed-blob digest, and freshness audit |

## Plan Self-Review

- **Spec and pool coverage:** Task 1 covers exact authorizer issuance, Task 2 covers deferred real-service registration without disposition transport, Task 3 covers the actual adapter closure and fail-closed seam, and Tasks 4-5 cover independently authored evidence, custody, and closure. No P11-FU-9 frozen artifact is amended.
- **Resolved drafting decision:** Although the pool uses the phrase “on allow_once transport lease (and later discovery),” a usable catalog cannot exist during transport-free `session/new`. This plan resolves it as: lease state is recorded at allow-once; service/authorizer registration happens immediately after the existing successful lazy catalog materialization. The Task 2 zero-open proof makes the constraint executable.
- **Real-object review:** Every wiring claim constructs the real adapter, session state, registry, catalog, authorizer, service, and guard. Test-only subclasses supply dispatch output only; they do not replace the wiring or authorization interface under test.
- **Guard and safety review:** Token issuance neither dispatches nor checks policy; `ClientMcpToolService.call_tool()` still builds a `PreToolRequest` and invokes `PreToolGuard.check()` before dispatch. No capability gate rejects an existing side-effect-eligible durable record.
- **Evidence review:** The real tier is an independently authored `acpx` driver and live fixtures; it is explicitly unrun if unavailable. Unit fakes cannot discharge it. Evidence is attached to the owning behavior task, not deferred to a generic final claim.
- **Digest and blast-radius review:** The final frozen artifact check hashes `git show HEAD:<path>`, not the worktree. Tasks 1-3 require a whole-codebase search for all registry/issuance call sites before changing their contract and include affected callers in their focused suite.
- **Placeholder scan:** No unresolved placeholder or unnamed deferred work remains. The precise production lazy composition file is intentionally discovered by Task 2’s real-materialization RED rather than guessed from a non-existent production `ClientMcpToolService` subclass; this reflects the current repository fact that `client_catalog.py` supplies the registry/authorizer primitives while tests currently provide the concrete dispatch subclass.

