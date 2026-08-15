# Plan 11.18 `P11-FU-10` ACP Error-Code Registry Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the live ACP/Optimus error-code collision, put every production wire code behind one registry, and enforce the registry with schema-derived and AST-derived oracles.

**Architecture:** `src/optimus/acp/errors.py` becomes the only production module that owns numeric JSON-RPC, ACP, and Optimus application codes. Runtime exceptions (`MutationForbidden` and `DuplicateRequestId`) carry semantic facts only; `JsonRpcDispatcher` translates them at the ACP boundary. A unit oracle derives the protocol allocation set from the vendored ACP schema, while a separate AST oracle rejects every production error-code literal outside that central module.

**Tech Stack:** Python 3.14, pytest, pytest-asyncio, coverage.py/pytest-cov, Ruff, the vendored ACP v1 JSON schema, independent `acpx`, Git, Windows, and a native WSL ext4 clone.

## Global Constraints

- Start from the verified base `7da16b67033819244cc2de00443c67c8687b8019`; `HEAD` and `origin/main` must match before implementation begins.
- Work only in a dedicated worktree and branch: `agent/codex/plan-11-18-acp-error-code-registry`; never use `optimus-cost-agent-wt-vibhanshu`.
- This plan is the forward-only home for `P11-FU-10`, including the stranded, unimplemented forced Plan 11.7 subset, **only after the operator records the custody ruling in Task 0**. The plan-review approval that created this draft is not a substitute for that operator decision.
- Do not edit the frozen Plan 11.7 file or its three dated amendments. Their current digest-pinned bytes, including the historical `-32002` text, are required evidence.
- Treat `tests/fixtures/acp/acp-v1-schema.json` as the source of ACP allocation truth. Do not maintain a copied ACP-code table.
- The Optimus application allocation is fixed by this plan: `MUTATION_FORBIDDEN = -32910` and `DUPLICATE_REQUEST_ID = -32911`. `-32910` continues frozen Plan 11.7’s stated allocation; `-32911` is the adjacent duplicate-ID allocation. The vendored-schema oracle must prove that neither is allocated by ACP.
- The move to `-32911` is unconditional. The real-`acpx` observation records client behavior; it cannot justify retaining a code in the JSON-RPC reserved band.
- JSON-RPC’s complete reserved band is inclusive `-32768..-32000`. Standard JSON-RPC and ACP codes may be represented centrally; no member of `OPTIMUS_APPLICATION_ERROR_CODES` may fall in that band.
- Preserve the one-key Gateway model. This plan must not introduce provider credentials, provider calls, or provider-key configuration.
- Windows is the mandatory verification platform. Repeat the non-live Python fitness gates in a native WSL ext4 clone; do not use a Windows-linked worktree through `/mnt` as the Linux substitute.
- The two mandatory mechanical acceptance oracles are: (1) schema-derived uniqueness/disjointness/reserved-band checks and (2) AST-derived rejection of production raw error-code literals. A green hand-maintained code list is insufficient.
- No code, documentation, test, or report change may be committed until its stated verification succeeds. Run `uv run --frozen ruff check .` before any commit or PR sign-off.

## Baseline Facts and Client-Visible Contract

At the `7da16b6` base, `src/optimus/acp/errors.py` defines `DUPLICATE_REQUEST_ID = -32001` and `MUTATION_FORBIDDEN = -32002`; `src/optimus/runtime/mutation.py` duplicates the latter as `MUTATION_FORBIDDEN_CODE = -32002`. The vendored schema’s `$defs.ErrorCode.anyOf` contains `RESOURCE_NOT_FOUND = -32002`, while it contains neither `-32910` nor `-32911`. `tests/unit/runtime/test_mutation_guard.py` and `tests/unit/runtime/test_state_machine.py` assert the runtime exception’s `-32002` field directly. Repository plan paths, local branches, remote branches, and the consolidated pool contain no Plan 11.18 allocation at this base. No `CURRENT.md` exists at this base, so this plan does not create an unowned parallel status tracker.

The wire contract changes deliberately:

| Condition | Before Plan 11.18 | After Plan 11.18 | Required proof |
|---|---|---|---|
| Mutation is denied in Plan/Chat mode or before approval | ACP response uses `-32002`, incorrectly claiming ACP `RESOURCE_NOT_FOUND` | ACP response uses Optimus `MUTATION_FORBIDDEN = -32910`; the runtime exception has no numeric `code` field | Dispatcher unit tests, schema oracle, AST oracle, README assertion |
| A duplicate inbound JSON-RPC request ID is rejected | ACP response uses `-32001` from a runtime exception; the code is inside the reserved band | ACP response uses Optimus `DUPLICATE_REQUEST_ID = -32911`; the runtime exception has no numeric `code` field | Dispatcher/request-ID unit tests, schema oracle, real-`acpx` evidence |
| Future ACP resource lookup reports not found | No central reservation despite ACP allocation | Registry reserves `RESOURCE_NOT_FOUND = -32002`; this plan does not implement `session/load` | Schema oracle and registry test |

Frozen Plan 11.7 already records its intended allocation at lines 268-285 and 628-633: its Optimus range is `-32999..-32900`, `MUTATION_FORBIDDEN = -32910`, and its remaining raw-literal/duplicate-ID work belongs to `P11-FU-10`. The frozen file remains unchanged; only living custody references may describe the transfer.

## File Map

| Path | Responsibility |
|---|---|
| `src/optimus/acp/errors.py` | The sole production owner of JSON-RPC, ACP, and Optimus application code constants and the two code sets used by the dispatcher/oracles. |
| `src/optimus/acp/request_ids.py` | Semantic duplicate-ID exception and request-ID tracking; no wire-code import or numeric default. |
| `src/optimus/runtime/mutation.py` | Semantic mutation-denial exception; no numeric wire-code constant. |
| `src/optimus/runtime/__init__.py` | Removes the obsolete runtime numeric-code export. |
| `src/optimus/acp/dispatcher.py` | The only mapping point from `DuplicateRequestId`/`MutationForbidden` to central wire-code constants. |
| `tests/unit/acp/test_error_code_registry.py` | Schema-derived registry oracle and AST raw-literal oracle, including the exact empty legacy allowlist assertion. |
| `tests/unit/acp/test_dispatcher.py` | Client-visible wire-code mapping tests for duplicate ID and mutation refusal. |
| `tests/unit/acp/test_request_ids.py` | Semantic duplicate-ID exception tests with no numeric field. |
| `tests/unit/runtime/test_mutation_guard.py` and `tests/unit/runtime/test_state_machine.py` | Semantic mutation-denial tests with no numeric field. |
| `tools/run_p11_fu_10_acpx_error_code_evidence.py` | Independent-`acpx` evidence runner; it records client behavior without becoming a project ACP client. |
| `tests/unit/tools/test_run_p11_fu_10_acpx_error_code_evidence.py` | Deterministic unit tests for the evidence runner’s external-client-only, sanitization, and fail-closed behavior. |
| `reports/plan-11-18-p11-fu-10-acpx-error-code-evidence.md` | Sanitized real-client evidence artifact required for closure. |
| `README.md` | Current user-facing mutation-boundary code, changed from `-32002` to `-32910`. |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Living `P11-FU-10` custody, status, and closure evidence; living `P11-FEAT-ZED-RESUME` reference. |
| `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` | Living Plan 11.7 status reference; records the bounded custody transfer without changing frozen history. |
| `tests/unit/docs/test_open_work_pool_hygiene.py` | Locks the current custody language while retaining the existing frozen-byte digest checks. |

## Explicit Exceptions and Custody

| Excluded work | Named owner |
|---|---|
| `session/load`, session storage, resume implementation, capability advertisement, and `SESSION_BUSY` behavior | Frozen Plan 11.7 / a separately approved unblocking amendment |
| ACP registry publication/version admission | `P11-FEAT-REGISTRY` |
| Zed render behavior, DWM evidence, and session-load reprobe work | `P11-FEAT-ZED-RESUME` and its existing evidence custody |
| Provider/Gateway implementation or credential changes | Existing Gateway lanes; not part of `P11-FU-10` |
| Changing or deleting frozen Plan 11.7 documents/amendments | Prohibited; historical bytes remain evidence |

The only Plan 11.7 work transferred here is the unimplemented forced error-code subset: reserve ACP `RESOURCE_NOT_FOUND = -32002`, map mutation refusal to `-32910`, and remove the duplicate runtime numeric constant. The general audit, raw-literal elimination, and legacy-allowlist reduction remain `P11-FU-10` work and are completed in this same plan. The operator must confirm that transfer before Task 2 begins; if the ruling is withheld or rejected, stop after Task 1, retain the live collision as open custody, and obtain a forward-only plan amendment rather than silently continuing.

---

### Task 1: Record the forward-only custody ruling and pin the implementation baseline

**Files:**

- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Do not modify: `docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md`
- Do not modify: `docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md`
- Do not modify: `docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md`
- Do not modify: `docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md`

**Interfaces:**

- Consumes: an operator-recorded acceptance of the explicit `P11-FU-10`/Plan 11.18 custody transfer; `origin/main == 7da16b6`; the frozen Plan 11.7 digest already protected by `PROTECTED_BLOB_SHA256`.
- Produces: one living custody statement in the `P11-FU-10` entry and one in the living Plan 11.7 status reference; no frozen-byte change.

- [x] **Step 1: Verify the approval and clean, current base.**

  Record the operator’s custody decision in the task evidence (review URL or approved PR comment), then run:

  ```powershell
  git fetch origin main
  git rev-parse HEAD
  git rev-parse origin/main
  git status --short --branch
  git diff --exit-code origin/main -- docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md
  ```

  Expected: `HEAD` and `origin/main` identify the authorized base before edits; the worktree is clean; all four frozen files have no diff. If the operator approval is absent, stop here without changing production code, tests, pool status, or the roadmap.

- [x] **Step 2: Write the RED living-custody documentation test.**

  Add a focused test to `tests/unit/docs/test_open_work_pool_hygiene.py` that reads the pool and roadmap and asserts all of the following exact semantic anchors:

  ```python
  assert "P11-FU-10" in pool
  assert "Plan 11.18" in pool
  assert "forced Plan 11.7 subset" in pool
  assert "-32002" in pool and "-32910" in pool and "-32911" in pool
  assert "frozen Plan 11.7" in pool
  assert "Plan 11.18" in roadmap
  assert "P11-FU-10" in roadmap
  assert "frozen Plan 11.7" in roadmap
  ```

  Keep the existing `PROTECTED_BLOB_SHA256` checks unchanged: the test must prove that living status changed without rewriting frozen bytes.

- [x] **Step 3: Run the new documentation test and verify its RED state.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  ```

  Expected: FAIL only because the current living documents still say that the correction belongs to Plan 11.7/already landed and do not name Plan 11.18. A frozen-digest failure is a stop condition, not an expected RED.

- [x] **Step 4: Record the transfer in living documents only.**

  In the `P11-FU-10` entry, replace the stale assertion that the forced correction “belongs to Plan 11.7”/“already landed” with a dated, forward-only statement that Plan 11.18 owns the named forced subset because it is unimplemented on `7da16b6` and Plan 11.7 is blocked. State that the transfer does not alter frozen files or unblock `session/load` work.

  In the living `P11-FEAT-ZED-RESUME`/Plan 11.7 reference in the pool and the Plan 11 roadmap status paragraph, add one bounded cross-reference: Plan 11.7 remains blocked, but its unimplemented error-code subset is now owned by `P11-FU-10` / Plan 11.18. Do not describe the correction as landed until Task 6 closes it on its own evidence.

- [x] **Step 5: Run the GREEN documentation and frozen-history checks.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  git diff --check
  git diff --exit-code origin/main -- docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md
  ```

  Expected: documentation hygiene is green, whitespace is clean, and frozen files remain byte-identical to the base.

- [x] **Step 6: Commit the approved custody record.**

  After the Task 1 commands pass and with commit authorization, run:

  ```powershell
  git add docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md tests/unit/docs/test_open_work_pool_hygiene.py
  git commit -m "docs(acp): transfer stranded error-code custody"
  ```

### Task 2: Make the schema-derived registry oracle RED

**Files:**

- Create: `tests/unit/acp/test_error_code_registry.py`
- Modify: `src/optimus/acp/errors.py`

**Interfaces:**

- Consumes: `tests/fixtures/acp/acp-v1-schema.json` and central registry exports.
- Produces: `JSON_RPC_STANDARD_ERROR_CODES`, `ACP_PROTOCOL_ERROR_CODES`, and `OPTIMUS_APPLICATION_ERROR_CODES` exported by `optimus.acp.errors`.

- [x] **Step 1: Write failing schema-derived tests.**

  In `tests/unit/acp/test_error_code_registry.py`, load the fixture with `json.loads`, select only integer `const` values from `schema["$defs"]["ErrorCode"]["anyOf"]`, and assert against the exported registry sets. The test must derive the ACP set at runtime; do not add a duplicated literal list of ACP values.

  ```python
  RESERVED_MIN, RESERVED_MAX = -32768, -32000

  def schema_error_codes() -> frozenset[int]:
      schema = json.loads(ACP_SCHEMA_PATH.read_text(encoding="utf-8"))
      return frozenset(
          item["const"]
          for item in schema["$defs"]["ErrorCode"]["anyOf"]
          if isinstance(item.get("const"), int)
      )

  def test_registry_is_unique_and_protocol_aligned() -> None:
      acp_codes = schema_error_codes()
      registry_values = (
          PARSE_ERROR,
          INVALID_REQUEST,
          METHOD_NOT_FOUND,
          INVALID_PARAMS,
          INTERNAL_ERROR,
          AUTHENTICATION_REQUIRED,
          REQUEST_CANCELLED,
          RESOURCE_NOT_FOUND,
          MUTATION_FORBIDDEN,
          DUPLICATE_REQUEST_ID,
      )

      assert len(registry_values) == len(set(registry_values))
      assert JSON_RPC_STANDARD_ERROR_CODES <= ACP_PROTOCOL_ERROR_CODES
      assert ACP_PROTOCOL_ERROR_CODES == acp_codes
      assert frozenset(registry_values) == acp_codes | OPTIMUS_APPLICATION_ERROR_CODES
      assert RESOURCE_NOT_FOUND == -32002
      assert -32910 not in acp_codes
      assert -32911 not in acp_codes
      assert OPTIMUS_APPLICATION_ERROR_CODES.isdisjoint(acp_codes)
      assert all(not (RESERVED_MIN <= code <= RESERVED_MAX) for code in OPTIMUS_APPLICATION_ERROR_CODES)
  ```

  Assert the explicit final application allocation as well:

  ```python
  assert MUTATION_FORBIDDEN == -32910
  assert DUPLICATE_REQUEST_ID == -32911
  assert OPTIMUS_APPLICATION_ERROR_CODES == frozenset({MUTATION_FORBIDDEN, DUPLICATE_REQUEST_ID})
  ```

- [x] **Step 2: Run the schema selector and verify RED.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_error_code_registry.py -q
  ```

  Expected: FAIL because the current registry lacks the protocol/application sets, `RESOURCE_NOT_FOUND`, and the two outside-band application values.

- [x] **Step 3: Implement the central registry without behavior changes outside the adapter.**

  In `src/optimus/acp/errors.py`, keep the five existing JSON-RPC standard constants and add exactly these central names:

  ```python
  AUTHENTICATION_REQUIRED = -32000
  REQUEST_CANCELLED = -32800
  RESOURCE_NOT_FOUND = -32002
  MUTATION_FORBIDDEN = -32910
  DUPLICATE_REQUEST_ID = -32911

  JSON_RPC_STANDARD_ERROR_CODES = frozenset(
      {PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR}
  )
  ACP_PROTOCOL_ERROR_CODES = frozenset(
      {*JSON_RPC_STANDARD_ERROR_CODES, AUTHENTICATION_REQUIRED, REQUEST_CANCELLED, RESOURCE_NOT_FOUND}
  )
  OPTIMUS_APPLICATION_ERROR_CODES = frozenset({MUTATION_FORBIDDEN, DUPLICATE_REQUEST_ID})
  ```

  `REQUEST_CANCELLED` and `RESOURCE_NOT_FOUND` reserve schema allocations in the central registry only. Do not add session/resume/load behavior or `SESSION_BUSY` in this plan.

- [x] **Step 4: Run the schema oracle GREEN.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_error_code_registry.py -q
  ```

  Expected: PASS. The test output establishes that the complete schema-derived set contains `-32002` but excludes `-32910` and `-32911`, and that Optimus application values are unique, disjoint, and outside the complete reserved band.

- [x] **Step 5: Commit the registry/oracle slice.**

  After the selector passes and with commit authorization, run:

  ```powershell
  git add src/optimus/acp/errors.py tests/unit/acp/test_error_code_registry.py
  git commit -m "test(acp): pin schema-derived error-code registry"
  ```

### Task 3: Make the AST raw-literal oracle RED against the current duplicate authority

**Files:**

- Modify: `tests/unit/acp/test_error_code_registry.py`

**Interfaces:**

- Consumes: all `src/**/*.py` files, the central registry module path, and `OPTIMUS_APPLICATION_ERROR_CODES`.
- Produces: `find_non_registry_error_code_literals(source_root: Path) -> frozenset[tuple[str, str]]`, returning exact repository-relative `(path, symbol)` sites; `EXPECTED_LEGACY_ERROR_CODE_SITES = frozenset()`.

- [x] **Step 1: Write the AST-oracle RED test before removing the duplicate constant.**

  Parse every tracked `src/**/*.py` file with `ast.parse`. Visit `Assign`, `AnnAssign`, dataclass field defaults, and call keyword/positional values that establish an error `code`. Treat a negative integer as error-code-like if it is in the inclusive JSON-RPC reserved band or is a member of `OPTIMUS_APPLICATION_ERROR_CODES`. Report its repository-relative path and enclosing class/function/module symbol whenever the literal is outside `src/optimus/acp/errors.py`.

  Define the baseline as a constant and assert it cannot quietly grow:

  ```python
  EXPECTED_LEGACY_ERROR_CODE_SITES = frozenset()

  def signed_int(node: ast.expr) -> int | None:
      if isinstance(node, ast.Constant) and type(node.value) is int:
          return node.value
      if (
          isinstance(node, ast.UnaryOp)
          and isinstance(node.op, ast.USub)
          and isinstance(node.operand, ast.Constant)
          and type(node.operand.value) is int
      ):
          return -node.operand.value
      return None

  def test_production_raw_error_code_allowlist_is_exact_and_empty() -> None:
      actual = find_non_registry_error_code_literals(REPO_ROOT / "src")
      assert actual == EXPECTED_LEGACY_ERROR_CODE_SITES
      assert EXPECTED_LEGACY_ERROR_CODE_SITES == frozenset()
  ```

  `find_non_registry_error_code_literals` must call `signed_int` on each candidate value, skip the one registry path, and return `(relative_path.as_posix(), enclosing_symbol)` pairs. The test must not scan tests, tools, reports, or `docs/`; those include intentional fixtures and frozen historical evidence. It must identify a raw source literal by path and enclosing symbol, never by a broad textual suppression.

- [x] **Step 2: Run the AST selector and verify its deterministic RED.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_error_code_registry.py -q
  rg -n --glob '*.py' -- "-327[0-9]{2}|-3260[0-3]|-32800|-320[0-9]{2}|-329[0-9]{2}" src tests tools
  ```

  Expected: the AST assertion fails on the exact current production bypass `src/optimus/runtime/mutation.py:MUTATION_FORBIDDEN_CODE`. Classify every grep result by source, test, tool, or frozen-history status; do not use grep alone as the oracle.

- [x] **Step 3: Preserve the RED; do not waive it with a baseline entry.**

  Confirm that `EXPECTED_LEGACY_ERROR_CODE_SITES` remains exactly `frozenset()` and leave the AST test RED for Task 4. Do not add `mutation.py` or any other source site to an allowlist: the required final state is zero legacy sites.

### Task 4: Remove runtime wire-code ownership, map semantic failures in the ACP dispatcher, and make both oracles GREEN

**Files:**

- Modify: `src/optimus/acp/request_ids.py`
- Modify: `src/optimus/runtime/mutation.py`
- Modify: `src/optimus/runtime/__init__.py`
- Modify: `src/optimus/acp/dispatcher.py`
- Modify: `tests/unit/acp/test_request_ids.py`
- Modify: `tests/unit/runtime/test_mutation_guard.py`
- Modify: `tests/unit/runtime/test_state_machine.py`
- Modify: `tests/unit/acp/test_dispatcher.py`
- Modify: `tests/unit/acp/test_error_code_registry.py`

**Interfaces:**

- Consumes: `DUPLICATE_REQUEST_ID` and `MUTATION_FORBIDDEN` only from `optimus.acp.errors` at the ACP adapter.
- Produces: `DuplicateRequestId(request_id: str | int)` and `MutationForbidden(message: str)` without a `code` attribute; `JsonRpcDispatcher.dispatch()` emits the designated central code in its JSON-RPC error response.

- [x] **Step 1: Write the semantic-exception RED tests.**

  Replace runtime numeric assertions with absence/semantic assertions:

  ```python
  assert not hasattr(exc_info.value, "code")
  assert str(exc_info.value) == "mutation forbidden in Plan/Chat mode"
  ```

  For duplicate IDs, assert the identifier remains available but no wire code is carried:

  ```python
  assert exc_info.value.request_id == 42
  assert not hasattr(exc_info.value, "code")
  ```

  Extend dispatcher tests so they assert the only wire-level results:

  ```python
  assert duplicate_response["error"]["code"] == DUPLICATE_REQUEST_ID == -32911
  assert mutation_response["error"]["code"] == MUTATION_FORBIDDEN == -32910
  ```

  Keep the current mutation messages, request IDs, blocked file assertions, and audit-event assertions unchanged.

- [x] **Step 2: Run the focused RED selectors.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_request_ids.py tests/unit/runtime/test_mutation_guard.py tests/unit/runtime/test_state_machine.py tests/unit/acp/test_dispatcher.py tests/unit/acp/test_error_code_registry.py -q
  ```

  Expected: the semantic tests fail because `DuplicateRequestId` and `MutationForbidden` still expose `code`, the dispatcher still emits old values, and the AST oracle remains RED on the runtime literal.

- [x] **Step 3: Remove the two runtime code fields and map at the one protocol boundary.**

  Make these exact boundary changes:

  ```python
  # request_ids.py
  @dataclass(frozen=True)
  class DuplicateRequestId(Exception):
      request_id: str | int

  # mutation.py
  @dataclass(frozen=True)
  class MutationForbidden(Exception):
      message: str
  ```

  Delete the `optimus.acp.errors` import and `MUTATION_FORBIDDEN_CODE` definition from `mutation.py`; remove the re-export from `runtime/__init__.py`. In `JsonRpcDispatcher.dispatch()`, map `DuplicateRequestId` to `DUPLICATE_REQUEST_ID` and the existing `MutationForbidden` catch to `MUTATION_FORBIDDEN`. Do not use numeric literals in these files.

- [x] **Step 4: Run both mechanical oracles and semantic tests GREEN.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_request_ids.py tests/unit/runtime/test_mutation_guard.py tests/unit/runtime/test_state_machine.py tests/unit/acp/test_dispatcher.py tests/unit/acp/test_error_code_registry.py -q
  ```

  Expected: PASS. Runtime layers expose only semantic exceptions; ACP responses emit `-32910` and `-32911`; the schema-derived and AST-derived oracles both pass with a zero allowlist.

- [x] **Step 5: Commit the one-authority mapping and AST enforcement change.**

  After the focused suite passes and with commit authorization, run:

  ```powershell
  git add src/optimus/acp/request_ids.py src/optimus/runtime/mutation.py src/optimus/runtime/__init__.py src/optimus/acp/dispatcher.py tests/unit/acp/test_request_ids.py tests/unit/runtime/test_mutation_guard.py tests/unit/runtime/test_state_machine.py tests/unit/acp/test_dispatcher.py tests/unit/acp/test_error_code_registry.py
  git commit -m "fix(acp): map semantic errors at protocol boundary"
  ```

### Task 5: Capture decision-independent real-`acpx` duplicate-code evidence

**Files:**

- Create: `tools/run_p11_fu_10_acpx_error_code_evidence.py`
- Create: `tests/unit/tools/test_run_p11_fu_10_acpx_error_code_evidence.py`
- Create at live-evidence execution only: `reports/plan-11-18-p11-fu-10-acpx-error-code-evidence.md`

**Interfaces:**

- Consumes: an independently installed `acpx` executable found by `shutil.which("acpx")`, its exact `--version`, and a throwaway ACP error-probe agent in an ignored temporary directory.
- Produces: a sanitized report containing the `acpx` version/path digest, the two probed code values, exit/classification observations, and no raw transcript, task prompt, environment, or credentials.

- [x] **Step 1: Write RED unit tests for the external-client evidence runner.**

  Model the runner after the repository’s existing `run_plan115_acpx_cost_obs_evidence.py` and `run_p11_fu_9_acpx_evidence.py` patterns. Unit-test that it:

  ```python
  assert resolve_acpx() == shutil.which("acpx")
  assert "optimus.acp" not in runner_source_for_protocol_client_imports
  assert runner.rejects_missing_acpx_with_controlled_error()
  assert report["probed_codes"] == [-32001, -32911]
  assert "OPTIMUS_API_KEY" not in report_text
  assert "full_transcript" not in report
  ```

  The probe agent may be a minimal fixture server solely to make an external client observe an error envelope. It is not an Optimus ACP client, never imports project protocol code, and does not stand in for an Optimus integration test. `acpx` is the only protocol client and test driver.

- [x] **Step 2: Run the runner unit tests RED.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_run_p11_fu_10_acpx_error_code_evidence.py -q
  ```

  Expected: FAIL because the runner and its sanitization/fail-closed contract do not yet exist.

- [x] **Step 3: Implement the hermetic observation runner.**

  The runner must launch the real external `acpx` with `shell=False`, invoke a temporary probe agent twice—once returning `-32001`, once returning `-32911`—and capture only these outcome fields: `code`, `acpx_version`, SHA-256 of the executable path string, process exit code, and a bounded classification token derived from `acpx` stderr/stdout. It must fail closed if `acpx` is unavailable, either probe cannot be driven, the client output contains a detected secret, or the report destination is outside `reports/`.

  It must state in the report that the application code changed unconditionally because `-32001` is inside the reserved band; the observation is evidence about one real client, not permission to retain a protocol-invalid number.

- [x] **Step 4: Run unit GREEN and Windows real-client evidence.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_run_p11_fu_10_acpx_error_code_evidence.py -q
  acpx --version
  uv run --frozen python tools/run_p11_fu_10_acpx_error_code_evidence.py --report reports/plan-11-18-p11-fu-10-acpx-error-code-evidence.md
  ```

  Expected: unit tests pass; the report names an independently authored `acpx`, records outcomes for both values, has no secret material, and explains that `-32911` remains mandatory regardless of the observation. Do not replace this live step with a project-authored client/harness. If `acpx` is unavailable or does not complete, leave `P11-FU-10` open and record the blocked evidence condition; do not claim closure.

- [x] **Step 5: Commit the evidence runner and its produced report.**

  After both unit and real-client gates pass and with commit authorization, run:

  ```powershell
  git add tools/run_p11_fu_10_acpx_error_code_evidence.py tests/unit/tools/test_run_p11_fu_10_acpx_error_code_evidence.py reports/plan-11-18-p11-fu-10-acpx-error-code-evidence.md
  git commit -m "test(acp): record external duplicate-code behavior"
  ```

### Task 6: Update current documentation, close `P11-FU-10`, and run cross-platform release gates

**Files:**

- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Modify if wording requires it: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Create: no new production file

**Interfaces:**

- Consumes: green Task 2 and Task 4 mechanical oracles; successful Task 5 report; the exact frozen-file digest checks.
- Produces: current documentation that says mutation denial is `-32910`, a closed `P11-FU-10` entry with its own report/PR evidence, and an unchanged frozen Plan 11.7 record.

- [x] **Step 1: Write RED current-document assertions.**

  Add assertions that distinguish current documentation from historical evidence:

  ```python
  assert "ACP callers receive JSON-RPC code `-32910`" in readme
  assert "ACP callers receive JSON-RPC code `-32002`" not in readme
  assert "Plan 11.18" in p11_fu_10_entry
  assert "plan-11-18-p11-fu-10-acpx-error-code-evidence.md" in p11_fu_10_entry
  assert "Closed" in p11_fu_10_status
  assert "-32002" in frozen_plan_117_text  # expected historical evidence, not a current claim
  ```

- [x] **Step 2: Run the documentation test RED.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  ```

  Expected: FAIL until current README and the open-work entry describe the actual final state. Historical `-32002` occurrences must not be “fixed.”

- [x] **Step 3: Make the current-state documentation changes.**

  Change README’s mutation-boundary statement to `-32910`. Mark `P11-FU-10` closed only when Tasks 2–5 have passed, link the Plan 11.18 implementation, its real-`acpx` report, and the merged PR/commit. State both before/after code mappings and that the registry/oracles prove the final allocation. Update the Plan 11.7 living reference to say its frozen implementation remains blocked and that no `session/load` work was transferred; only the now-completed error-code subset moved to Plan 11.18.

- [x] **Step 4: Run Windows fitness gates.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_error_code_registry.py tests/unit/acp/test_request_ids.py tests/unit/acp/test_dispatcher.py tests/unit/runtime/test_mutation_guard.py tests/unit/runtime/test_state_machine.py tests/unit/tools/test_run_p11_fu_10_acpx_error_code_evidence.py tests/unit/docs/test_open_work_pool_hygiene.py -q
  uv run --frozen pytest -q
  uv run --frozen pytest --cov
  uv run --frozen ruff check .
  git diff --check
  ```

  Expected: all selected and default non-live tests pass, bare coverage is at least 80%, Ruff is clean, and there is no whitespace error. Any failure—including an unrelated existing flake—must be recorded and resolved or dispositioned before closure.

- [ ] **Step 5: Repeat the non-live gates in a native WSL ext4 clone.**

  From WSL Ubuntu, create a throwaway clone under the Linux filesystem, check out the exact candidate commit, and run:

  ```bash
  uv sync --frozen --extra dev
  uv run pytest -q
  uv run pytest --cov
  uv run ruff check .
  git diff --check
  ```

  Expected: all gates pass from the ext4 clone. Do not run this parity gate from `/mnt/d/...` or reuse a Windows-created linked worktree. If a platform-specific failure occurs, retain its command/output in the PR and resolve it before sign-off.

- [ ] **Step 6: Perform the documentation freshness audit and final frozen-history verification.**

  Review every living state claim affected by the change: `README.md`, the consolidated pool, the Plan 11 roadmap, the milestone charter if it references Plan 11.7 current state, and current reports linked by the pool. Then run:

  ```powershell
  rg -n -- "-32002|-32001|-32910|-32911" README.md src tests tools docs/superpowers/plans
  git diff --exit-code origin/main -- docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md
  git status --short
  ```

  Expected: live production code has no `-32001`/`-32002` application mapping; README names `-32910`; the only remaining historical old-code references are classified as frozen evidence; all frozen files are unchanged; no untracked secret or scratch output exists.

- [ ] **Step 7: Commit, update from `main`, and open a draft PR.**

  After all Windows and WSL gates pass and with explicit commit/push/PR authorization, run:

  ```powershell
  git add README.md docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md tests/unit/docs/test_open_work_pool_hygiene.py
  git commit -m "docs(acp): close error-code registry audit"
  git fetch origin main
  git merge origin/main
  git push -u origin agent/codex/plan-11-18-acp-error-code-registry
  $prBodyPath = Join-Path $env:TEMP "plan-11-18-pr-body.md"
  @"
  ## Summary
  Transfers the unimplemented Plan 11.7 error-code subset to P11-FU-10 / Plan 11.18; changes mutation refusal from -32002 to -32910 and duplicate-ID refusal from -32001 to -32911.

  ## Evidence
  The schema-derived registry oracle proves -32910/-32911 are unallocated and outside JSON-RPC's reserved band; the AST oracle's legacy allowlist is empty; real-acpx evidence is at reports/plan-11-18-p11-fu-10-acpx-error-code-evidence.md.

  ## Verification
  Windows and native-WSL pytest/coverage/Ruff/diff-check outcomes are recorded in this PR. Frozen Plan 11.7 bytes are unchanged.
  "@ | Set-Content -LiteralPath $prBodyPath -Encoding utf8
  gh pr create --draft --base main --head agent/codex/plan-11-18-acp-error-code-registry --title "Plan 11.18: ACP error-code registry audit" --body-file $prBodyPath
  Remove-Item -LiteralPath $prBodyPath
  ```

  Expand the exact body above before creating the PR if a gate is blocked: state the operator custody ruling, both client-visible before/after values, the schema-derived proof that `-32910`/`-32911` are unallocated, the zero AST allowlist result, real-`acpx` report path/version, Windows and WSL command outcomes, coverage result, frozen-file preservation, and the blocker. The body file lives in the OS temporary directory and must not be staged.

## Definition of Done and Evidence Ledger

| Claim | Required evidence |
|---|---|
| Forced Plan 11.7 subset has legitimate forward-only custody | Operator ruling plus living P11-FU-10 and Plan 11.7 references; frozen Plan 11.7 diff is empty |
| `-32002` is reserved for ACP resource-not-found rather than mutation refusal | Schema-derived unit oracle includes `-32002`; central `RESOURCE_NOT_FOUND`; dispatcher mutation response is `-32910` |
| Optimus application codes are valid and unique | Schema-derived test proves the registry set, `-32910`/`-32911` schema non-allocation, disjointness, and full reserved-band exclusion |
| No production raw wire-code authority survives outside the registry | AST unit oracle with exact `EXPECTED_LEGACY_ERROR_CODE_SITES == frozenset()` |
| Runtime exceptions are semantic | Runtime/request-ID tests assert no `code` field; dispatcher tests assert the two ACP values |
| Duplicate-ID behavior was investigated against a real client | Sanitized `reports/plan-11-18-p11-fu-10-acpx-error-code-evidence.md` produced by external `acpx`; no project client substitute |
| Current documentation is honest while history remains intact | README/pool/roadmap tests and frozen-plan byte/diff evidence |
| Change is fit on supported platforms | Windows and native WSL ext4 `pytest -q`, bare `pytest --cov` at least 80%, Ruff, and `git diff --check` outputs |
