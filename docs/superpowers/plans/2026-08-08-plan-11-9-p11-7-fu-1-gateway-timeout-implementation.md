# Plan 11.9: P11.7-FU-1 Configurable Gateway Request Timeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:test-driven-development` for every production behavior change. Steps use checkbox (`- [ ]`) syntax for tracking. Do not mark a checkbox complete until its stated verification command has actually passed.

**Status:** Draft implementation plan. Execution requires approval of the companion design
specification: `docs/superpowers/specs/2026-08-08-plan-11-9-p11-7-fu-1-gateway-timeout-design.md`.

**Goal:** Add a documented, per-process `--gateway-timeout-seconds` override that reaches both
ACP Gateway clients while preserving the 30-second default and fail-closed unknown-cost behavior.

**Architecture:** Reuse the existing `GatewayClient(timeout_seconds=...)` injection seam. Parse one
optional positive-finite CLI value in `optimus.acp.__main__`, forward it through the two bootstrap
functions, and apply it to both the AgentRunner and dispatcher clients. The absent-flag path keeps
the existing constructor call shape, so default behavior remains owned by `GatewayClient`.

**Tech Stack:** Python 3.14, `argparse`, stdlib `math`, existing Gateway client/urllib transport,
pytest, pytest-asyncio, pytest-cov/coverage.py, Ruff, and Markdown operator documentation.

## Global Constraints

- Baseline is `origin/main` commit `cb820684cfea1b68f3b7e9e5341508977e77aa58`.
- Scope is `P11.7-FU-1` only; do not fold this into frozen Plan 11.7 or another in-flight plan.
- The authoritative pool acceptance criteria are:
  - A documented override raises `GatewayClient`'s effective `timeout_seconds` for a single
    invocation/session.
  - Default behavior (30s timeout, fail-closed/no-retry on unknown cost) is unchanged when the
    override is not set.
  - The override is discoverable (e.g. `optimus-agent --help`), not just a source-level constant.
- Do not modify the `PLANNING_GATEWAY_COST_UNKNOWN` behavior or any retry/no-retry decision in
  `src/optimus/agent/planning_loop.py:907-912,953-956`.
- The public interface is CLI-only in this plan: `--gateway-timeout-seconds SECONDS`. Do not add
  `OPTIMUS_GATEWAY_TIMEOUT_SECONDS`; a future environment interface would need its own launch-policy
  and approval review.
- The default remains exactly 30.0 seconds. Invalid values are positive-finite validation errors;
  they must not silently fall back to the default.
- Keep the existing one-key model. No provider credentials, Gateway API fields, telemetry schema,
  or local Gateway startup behavior may change.
- Use TDD: write or update a failing test, run the focused test to establish RED, implement the
  minimum change, and run the focused test to establish GREEN before proceeding.
- Unit doubles are permitted in unit tests. No live Gateway, Redis, or ACPX evidence is required
  for this CLI/bootstrap-only change, but all affected unit tests and the full suite must pass before
  sign-off.
- Before implementation sign-off, run the affected tests, full test suite, production coverage,
  `python -m ruff check .`, `git diff --check`, and the documentation freshness audit.

## File map

Implementation files:

- Modify `src/optimus/gateway/client.py` only if needed to centralize the positive-finite timeout
  validator and the shared 30.0 default constant. Preserve the existing constructor seam and
  transport behavior.
- Modify `src/optimus/acp/__main__.py` to add the public argument, parse validation, help text,
  and conditional forwarding.
- Modify `src/optimus/acp/bootstrap.py` to accept `gateway_timeout_seconds` on both builder
  functions and apply one value to both `GatewayClient` construction sites.
- Modify `README.md` to document the flag, process scope, default, and unchanged fail-closed cost
  behavior.

Test files:

- Modify `tests/unit/gateway/test_client.py` for default, explicit, and invalid timeout behavior.
- Modify `tests/unit/acp/test_bootstrap.py` for both bootstrap client paths.
- Modify `tests/unit/acp/test_main_wiring.py` for CLI parsing, help, validation, forwarding, and
  absent-flag compatibility.

No launch-policy registry or planning-loop file is in scope.

## Frozen acceptance and evidence map

| Acceptance claim | Required evidence | Planned location |
|---|---|---|
| Explicit value raises the effective Gateway timeout for one process | Transport request records the explicit seconds; both bootstrap clients receive the same value | `tests/unit/gateway/test_client.py`, `tests/unit/acp/test_bootstrap.py` |
| Default stays 30 seconds | Absent constructor/flag request records `30.0`; existing constructor call shape remains intact | `tests/unit/gateway/test_client.py`, `tests/unit/acp/test_main_wiring.py` |
| Unknown-cost fail-closed behavior is unchanged | No production diff under `planning_loop.py`; targeted planning-loop tests remain green in the full suite | Review diff plus full pytest run |
| Override is documented and discoverable | `--help` output includes the flag; README flags table and example describe it | `tests/unit/acp/test_main_wiring.py`, `README.md` |

## Task 0: Re-verify the pickup baseline

**Files:** Read-only inspection of the pool, source, and tests. No files are created or modified.

- [ ] **Step 1: Verify branch, baseline, and clean starting tree.**

  Run:

  ```powershell
  git status --short --branch
  git rev-parse HEAD
  git rev-parse origin/main
  ```

  Expected: the branch is `agent/codex/plan-11-9-gateway-timeout`, the worktree is clean, and
  both `HEAD` and `origin/main` resolve to `cb820684cfea1b68f3b7e9e5341508977e77aa58`.

- [ ] **Step 2: Re-check the pool acceptance text and current constructor sites.**

  Run:

  ```powershell
  rg -n -C 14 '^### P11\.7-FU-1|\*\*Acceptance criteria|\*\*Evidence anchors|\*\*Status' docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md
  rg -n -C 3 'timeout_seconds|GatewayClient\(' src/optimus/gateway/client.py src/optimus/acp/bootstrap.py
  rg -n -C 3 'add_argument|build_configured_server' src/optimus/acp/__main__.py
  ```

  Expected: `GatewayClient` defaults to `30.0`, both bootstrap construction sites omit an
  override, and the fail-closed planning-loop anchors are unchanged. If the pool or source has
  drifted, stop and amend the plan rather than relying on the stale line numbers.

## Task 1: Pin the client contract and create the RED tests

**Files:**

- Modify: `tests/unit/gateway/test_client.py`
- Modify: `tests/unit/acp/test_bootstrap.py`
- Modify: `tests/unit/acp/test_main_wiring.py`

**Interfaces:**

- Consumes: the existing `GatewayClient(settings=..., transport=..., timeout_seconds=...)`
  constructor and the `GatewayRequest.timeout_seconds` capture already exposed by the fake
  transport.
- Produces: failing tests that define the exact Plan 11.9 CLI/bootstrap contract.

- [ ] **Step 1: Add the client default and validation tests.**

  Extend `tests/unit/gateway/test_client.py` with the following cases, using the existing
  `settings()` and `FakeTransport` fixtures/helpers:

  ```python
  def test_gateway_client_default_timeout_remains_thirty_seconds():
      transport = FakeTransport()
      client = GatewayClient(settings=settings(), transport=transport)

      client.create_response(model="glm-5.2", input_text="hello")

      assert transport.requests[0].timeout_seconds == 30.0


  def test_gateway_client_explicit_timeout_reaches_transport():
      transport = FakeTransport()
      client = GatewayClient(settings=settings(), transport=transport, timeout_seconds=90.0)

      client.create_response(model="glm-5.2", input_text="hello")

      assert transport.requests[0].timeout_seconds == 90.0


  @pytest.mark.parametrize("value", [0.0, -1.0, float("inf"), float("-inf"), float("nan")])
  def test_gateway_client_rejects_non_positive_or_non_finite_timeout(value):
      with pytest.raises(ValueError):
          GatewayClient(settings=settings(), transport=FakeTransport(), timeout_seconds=value)
  ```

  Keep the existing transport test that proves `urlopen(..., timeout=request.timeout_seconds)`
  unchanged; it is the transport-level evidence that the client field controls the actual wait.

- [ ] **Step 2: Add bootstrap pass-through tests.**

  Extend the existing `test_bootstrap_builds_agent_configured_server` fixture setup so it builds
  with `gateway_timeout_seconds=90.0`, then assert both private client fields:

  ```python
  assert server._dispatcher._gateway_client._timeout_seconds == 90.0
  assert server._dispatcher._agent_runner._gateway_client._timeout_seconds == 90.0
  ```

  Add a companion call without `gateway_timeout_seconds` and assert both values are `30.0`. This
  pins the default path as well as the explicit path without opening a real Redis connection.

- [ ] **Step 3: Add CLI parsing, help, invalid-input, and forwarding tests.**

  In `tests/unit/acp/test_main_wiring.py`, add:

  ```python
  def test_parse_args_accepts_gateway_timeout_seconds():
      args = acp_main.parse_args(["--gateway-timeout-seconds", "90"])

      assert args.gateway_timeout_seconds == 90.0


  @pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "not-a-number"])
  def test_parse_args_rejects_invalid_gateway_timeout_seconds(value):
      with pytest.raises(SystemExit):
          acp_main.parse_args(["--gateway-timeout-seconds", value])
  ```

  Add a help test that calls `acp_main.parse_args(["--help"])`, catches `SystemExit`, and asserts
  the captured stdout contains `--gateway-timeout-seconds` and `SECONDS`. Extend the existing
  server-factory capture test to invoke `main([... , "--gateway-timeout-seconds", "90"])` and
  assert the builder received `gateway_timeout_seconds == 90.0`. Keep a no-flag assertion that the
  builder receives no timeout override, preserving exact-signature test doubles and the old default
  path.

- [ ] **Step 4: Run the focused tests to verify RED.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/gateway/test_client.py tests/unit/acp/test_bootstrap.py tests/unit/acp/test_main_wiring.py -q
  ```

  Expected: the overall focused run FAILS because the invalid-value validation, CLI argument, and
  bootstrap keyword do not exist yet. The characterization tests for the already-supported
  explicit client value and 30-second default may pass before implementation; the new contract is
  RED when the command has at least one failure in the CLI/bootstrap/validation cases.

## Task 2: Implement the validated CLI-to-bootstrap wiring

**Files:**

- Modify: `src/optimus/gateway/client.py`
- Modify: `src/optimus/acp/__main__.py`
- Modify: `src/optimus/acp/bootstrap.py`

**Interfaces:**

- Consumes: the failing tests from Task 1.
- Produces: `parse_args(...).gateway_timeout_seconds: float | None`, optional
  `gateway_timeout_seconds: float | None` parameters on both bootstrap builders, and two clients
  sharing the same effective timeout.

- [ ] **Step 1: Add one positive-finite validator and preserve the 30.0 default.**

  In `src/optimus/gateway/client.py`, import the stdlib `math`, then define a shared
  `DEFAULT_GATEWAY_TIMEOUT_SECONDS = 30.0`
  and a validator with this contract:

  ```python
  def validate_gateway_timeout_seconds(value: object) -> float:
      parsed = float(value)
      if not math.isfinite(parsed) or parsed <= 0:
          raise ValueError("gateway timeout must be a positive finite number of seconds")
      return parsed
  ```

  Catch `TypeError`/`ValueError` from `float()` and raise the same stable `ValueError` message.
  Use the constant for the existing `GatewayRequest` and `GatewayClient` defaults. Validate an
  explicit `GatewayClient(timeout_seconds=...)` value before storing it. Do not change request
  payloads, error mapping, transport calls, retries, or usage parsing.

- [ ] **Step 2: Add the public argument and argparse error boundary.**

  In `src/optimus/acp/__main__.py`, import the constant and validator. Add a small argparse type
  adapter that converts `ValueError` into `argparse.ArgumentTypeError`, then register:

  ```python
  parser.add_argument(
      "--gateway-timeout-seconds",
      type=_parse_gateway_timeout_seconds,
      default=None,
      metavar="SECONDS",
      help=f"Gateway request timeout in seconds for this process (default: {DEFAULT_GATEWAY_TIMEOUT_SECONDS:.1f}).",
  )
  ```

  Keep the default `None` so the absent-flag path uses the existing `GatewayClient` default and
  does not add a new keyword to old builder/test-double calls.

- [ ] **Step 3: Thread the optional value through both bootstrap construction sites.**

  In `src/optimus/acp/bootstrap.py`, add `gateway_timeout_seconds: float | None = None` to
  `build_agent_runner_for_harness()` and `build_configured_server()`. Use a private helper with
  this exact behavior:

  ```python
  def _build_gateway_client(*, settings, timeout_seconds):
      if timeout_seconds is None:
          return GatewayClient(settings=settings)
      return GatewayClient(settings=settings, timeout_seconds=timeout_seconds)
  ```

  Replace both direct constructor calls with the helper. Pass the same optional value from
  `build_configured_server()` into `build_agent_runner_for_harness()` and into the dispatcher’s
  client. The explicit value is validated by `GatewayClient`; the default path remains byte-for-
  byte equivalent at the call boundary.

- [ ] **Step 4: Forward the value from `main()` only when explicitly set.**

  Build the existing `build_configured_server` keyword mapping in `main()`. Add
  `gateway_timeout_seconds` to that mapping only when `args.gateway_timeout_seconds is not None`.
  This preserves compatibility with current exact-signature test doubles and ensures the override
  is scoped to this invocation rather than inherited by later sessions.

- [ ] **Step 5: Run the focused tests to verify GREEN.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/gateway/test_client.py tests/unit/acp/test_bootstrap.py tests/unit/acp/test_main_wiring.py -q
  ```

  Expected: all tests in the three files pass, including the new explicit/default/invalid timeout,
  bootstrap, CLI, and help cases.

## Task 3: Document the operator workflow

**Files:**

- Modify: `README.md`

**Interfaces:**

- Consumes: the final CLI spelling and default from Task 2.
- Produces: operator-facing documentation that maps directly to `optimus-agent --help`.

- [ ] **Step 1: Add the flag to the Quick Start flags table.**

  Add a row to the existing flags table:

  ```markdown
  | `--gateway-timeout-seconds SECONDS` | Raise the Gateway request timeout for this process; default is 30 seconds |
  ```

- [ ] **Step 2: Add a debug/investigation example and safety note.**

  Add the following operator guidance near the flags table:

  ```markdown
  For a slow Gateway/model response during a one-off investigation, run
  `optimus-agent --gateway-timeout-seconds 90`. The value applies only to that agent process;
  omitting it preserves the 30-second default. It changes how long the first Gateway request may
  wait; it does not enable retries or weaken the fail-closed `PLANNING_GATEWAY_COST_UNKNOWN`
  behavior when the Gateway cannot report cost.
  ```

- [ ] **Step 3: Check the documentation diff.**

  Run:

  ```powershell
  git diff --check
  rg -n -C 3 'gateway-timeout-seconds|PLANNING_GATEWAY_COST_UNKNOWN' README.md
  ```

  Expected: no whitespace errors, one flags-table row, and the process-scoped safety note are
  present.

## Task 4: Run the complete verification gates

**Files:** No additional files; this task produces verification output only.

- [ ] **Step 1: Run affected tests and CLI help.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/gateway/test_client.py tests/unit/acp/test_bootstrap.py tests/unit/acp/test_main_wiring.py -q
  uv run --frozen python -m optimus.acp --help
  ```

  Expected: the focused tests pass, and help exits successfully while displaying
  `--gateway-timeout-seconds SECONDS` and its 30-second default text without requiring Gateway or
  Redis credentials.

- [ ] **Step 2: Run the full test suite and production coverage.**

  Run:

  ```powershell
  uv run --frozen pytest -q
  uv run --frozen pytest --cov=src/optimus --cov-report=term-missing --cov-fail-under=80
  ```

  Expected: zero failures and aggregate production coverage at least 80%. If a platform-specific
  failure appears, record it and reproduce the affected command under WSL2 before sign-off as
  required by the repository instructions.

- [ ] **Step 3: Run Ruff and repository hygiene checks.**

  Run:

  ```powershell
  python -m ruff check .
  git diff --check
  rg -n 'OPTIMUS_GATEWAY_TIMEOUT_SECONDS' src tests README.md 2>$null
  if ($LASTEXITCODE -eq 0) { throw 'Deferred environment-variable interface was added unexpectedly.' }
  rg -n -C 2 'PLANNING_GATEWAY_COST_UNKNOWN' src/optimus/agent/planning_loop.py
  ```

  Expected: Ruff is clean; the diff has no whitespace errors; the deferred environment variable
  is absent; and the fail-closed planning-loop code remains present and unchanged.

- [ ] **Step 4: Perform the documentation freshness audit.**

  Read the current-state claims in `README.md`,
  `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, and
  `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`. Confirm that:

  - the pool index and detailed `P11.7-FU-1` entry agree on the Plan 11.9 promotion;
  - the README flag table matches the actual `argparse` spelling and default;
  - the roadmap does not falsely claim that Plan 11.9 implementation is complete; and
  - no frozen plan/spec was edited as part of implementation.

  Record any required documentation correction in the implementation commit only when it is
  directly necessary to keep a current-state claim true; do not rewrite historical documents.

## Task 5: Implementation handoff

**Files:** The plan and design documents are already committed by the drafting PR. The implementing
agent must modify only the files listed in the File map and the explicitly approved documentation
corrections from Task 4.

- [ ] **Step 1: Review the final diff against this plan.**

  Run:

  ```powershell
  git status --short --branch
  git diff --stat
  git diff -- src/optimus/gateway/client.py src/optimus/acp/__main__.py src/optimus/acp/bootstrap.py README.md
  ```

  Expected: only the timeout wiring, validation, tests, and operator documentation are present;
  there is no planning-loop, launch-policy, provider-key, retry, or Gateway API change.

- [ ] **Step 2: Commit the implementation after all gates pass.**

  ```powershell
  git add src/optimus/gateway/client.py src/optimus/acp/__main__.py src/optimus/acp/bootstrap.py README.md tests/unit/gateway/test_client.py tests/unit/acp/test_bootstrap.py tests/unit/acp/test_main_wiring.py
  git commit -m "Add configurable Gateway request timeout"
  ```

  Expected: the commit succeeds without `--no-verify`, and the staged paths contain no unrelated
  changes.

## Definition of Done

- [ ] `optimus-agent --gateway-timeout-seconds 90` is accepted and visible in `--help`.
- [ ] Both bootstrap-created Gateway clients use 90 seconds for that process.
- [ ] The absent-flag path still uses 30 seconds.
- [ ] Invalid values fail closed before startup side effects.
- [ ] `PLANNING_GATEWAY_COST_UNKNOWN` and its no-retry behavior are unchanged.
- [ ] README documentation, focused tests, full tests, coverage, Ruff, diff hygiene, and the
  documentation freshness audit all pass.
