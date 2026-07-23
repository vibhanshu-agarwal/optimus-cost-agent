# Plan 10.1: P9.96 Follow-Up Remediation Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILLS: Use superpowers:executing-plans to execute
> this plan task-by-task and superpowers:test-driven-development for every behavior change.
> Use superpowers:systematic-debugging if Task 1 finds a live FU-5 defect. Steps use checkbox
> (- [ ]) syntax for tracking.

**Status:** Frozen after reviewer and operator approval on 2026-07-23. Implementation is authorized;
no source implementation has started.

**Goal:** Close P9.96-FU-1, FU-2, FU-3, and FU-4, resolve FU-5 by evidence, land only the
confirmation-gate half of FU-7, and record a reviewed no-code disposition for FU-6.

**Architecture:** Preserve the existing ACP launch and one-key boundaries. The error-prefix and
comment corrections remain local to acp/__main__.py; the documentation and default-model fixes
do not alter runtime protocols. The approval ceremony gains one explicit operator confirmation
after the existing effective configuration display and before an approval record is built or
written. This plan intentionally does not change launch-candidate resolution or display-row
construction; the remaining FU-7 effective-row gap stays open under the original stable ID.

**Tech Stack:** Python 3.14+, existing dataclasses, argparse, pathlib, keyring-backed approval
store, pytest, pytest-asyncio, pytest-cov, coverage.py, Ruff, and uv. No new dependency.

## Global Constraints

- Baseline is the latest fetched origin/main, commit 21220209421145b583eaca9a65b19cf6b5128caa.
- The working tree already contains user-owned uv.lock changes and an untracked .claude/ directory;
  neither may be staged, reverted, regenerated, or otherwise modified by this plan.
- Reuse the existing worktree on branch agent/codex/plan-10-1-p996-remediation; do not create a
  second worktree for this plan. After approval, implementation may continue on this branch or on a
  separately approved branch, but it must first verify the then-current origin/main baseline and the
  frozen plan digest.
- Plan 10.1 is the first allocated Plan 10.x slot after the backlog-renumbering merge. Do not allocate
  another Plan 10.x number unless Task 1 triggers the explicit FU-5 split rule.
- The plan implements P9.96-FU-1, FU-2, FU-3, FU-4, FU-5, and only the confirmation-gate half of
  FU-7; FU-6 receives a closure disposition note only and no source or test change. FU-7's
  effective-row display gap remains open under P9.96-FU-7 and is not minted as a new finding.
- If Task 1 finds FU-5 needs new exception semantics, a cross-layer design, a persistent-schema change,
  or more than a contained local fix, stop that lane, create and separately review the next unused
  Plan 10.x item for FU-5, and keep the remaining bundle numbered Plan 10.1. Do not broaden this plan.
- Use TDD for behavior changes: add the named failing test, run its narrow selector and confirm the
  intended failure, implement the smallest correction, then rerun the selector and affected suite.
- Preserve the one-key model, gateway-owned provider credentials, existing approval digest fields,
  child propagation, redaction rules, and fail-closed launch behavior.
- Preserve the existing secret-redaction and display behavior. The confirmation change must never
  print, persist, assert, or place in a new display row a provider API key, shared secret, URI user
  information, raw hash, approval nonce, or other secret-bearing value.
- Do not use a project-authored ACP client, live Gateway, Redis, or provider credential for this bundle's
  unit evidence. No new live-tier test may be mislabeled as a unit test.
- Do not edit the frozen Plan 9.96 implementation plan, security design, approval records, or evidence
  report. Living status belongs in the consolidated backlog, the phase roadmap, and the short README
  status section only after the implementation evidence is complete.
- Do not mark a plan checkbox complete until its literal verification command passed. Update the
  gitignored checkpoint log after each task with the command and result; never stage that log.
- Before sign-off, run the affected tests, the default suite, aggregate coverage with the repository's
  80% gate, uv run --locked ruff check ., and git diff --check.

## Source Anchors and Current Evidence

- src/optimus/acp/__main__.py:379 prints PreflightFailure.user_message without the sibling
  optimus-agent: prefix; :411 prints StartupConfigurationError.user_message the same way.
- src/optimus/acp/__main__.py:317-338 contains the same 11-line Plan 9.96 TOCTOU comment twice,
  consecutively. Keep exactly one copy.
- src/optimus/acp/launch_audit.py:4 and :63 say trusted external runtime root, while
  src/optimus/acp/operator_paths.py:214 and :298 resolve runtime_root as
  resolved_workspace / ".optimus".
- src/optimus/agent/defaults.py:5 returns glm-5.2 when no CLI or environment model exists.
  src/optimus_gateway/model_mapping.py accepts claude-haiku as an alias for all supported
  providers, while bare glm-5.2 is not a valid OpenRouter passthrough; the priced OpenRouter
  identifier is z-ai/glm-5.2. The ACP entry point passes args.model through, so the default
  remains reachable when no model is supplied even though the live evidence path commonly passes
  claude-haiku explicitly.
- There is no literal @contextmanager or FrozenInstanceError reference in current src; the
  current candidate frozen exception classes are StartupConfigurationError and AcpOutboundError.
  Task 1 must prove whether FU-5 is already resolved before changing either class.
- src/optimus/acp/launch_approval_cli.py:292-316 has the existing FU-7 confirmation gap: it
  displays the candidate and immediately builds/writes the durable or one-shot record.
- P9.96-FU-7 also names a separate effective-row display gap for keyring/config/default-sourced
  settings. That gap is explicitly deferred by this plan under the same stable ID; no candidate or
  credential-resolution change is included.
- Authoritative HLD v2.15, LLD v2.38, and Test Strategy v1.4 agree on gateway-owned provider keys,
  secret-free persisted/displayed data, deterministic unit evidence, and real dependencies only in
  their named live tiers. No conflict was found with this narrow remediation bundle.

## File and Responsibility Map

| File | Responsibility in this plan |
|---|---|
| src/optimus/acp/__main__.py | Prefix both raw user-facing startup/preflight error messages and remove one duplicate TOCTOU comment block. |
| src/optimus/acp/launch_audit.py | Correct two docstrings to say workspace-local runtime root. |
| src/optimus/agent/defaults.py | Replace the unreachable bare default with the existing routable claude-haiku alias. |
| src/optimus/acp/launch_approval_cli.py | Ask for explicit confirmation after display and before record construction/write. |
| tests/unit/acp/test_main_wiring.py | Regression pin for StartupConfigurationError prefix and the duplicate-comment source contract. |
| tests/unit/acp/test_main_check_config.py | Regression pin for PreflightFailure prefix. |
| tests/unit/acp/test_launch_audit.py | Docstring contract for workspace-local runtime root wording. |
| tests/unit/agent/test_defaults.py | Default model contract. |
| tests/unit/acp/test_preflight.py | Keep the invalid-model preflight test explicit instead of depending on the removed default. |
| tests/unit/acp/test_launch_approval_cli.py | Confirm/decline/no-write behavior and secret-free output. |
| docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md | Stable-ID catalog promotion/closure evidence after landing. |
| docs/superpowers/plans/2026-07-01-phase-1-roadmap.md | Plan 9.96 and Plan 10.1 status reconciliation after landing. |
| README.md | Short Plan 10/Plan 10.1 status pointer after landing. |
| docs/superpowers/reviews/plan-10-1-review-checkpoints.md | Gitignored reviewer/implementation handoff log; never stage. |

---

### Task 0: Freeze the Reviewed Plan and Verify the Plan 10 Allocation

**Files:**
- Create: docs/superpowers/reviews/2026-07-23-plan-10-1-implementation-plan-approval.md after reviewer/operator approval
- Modify: docs/superpowers/plans/2026-07-23-plan-10-1-p9-96-follow-up-remediation.md only for approved checkbox progress
- Modify: docs/superpowers/reviews/plan-10-1-review-checkpoints.md as a gitignored handoff log

**Produces:** A digest-pinned, reviewer- and operator-approved Plan 10.1 scope with proof that no
other Plan 10.x number existed on the allocation baseline.

- [x] **Step 1: Verify the branch, baseline, and preserved user changes.**

Run:

~~~
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git diff --name-only -- uv.lock
git status --short -- .claude
~~~

Expected: branch agent/codex/plan-10-1-p996-remediation tracks origin/main; both revision
commands return 21220209421145b583eaca9a65b19cf6b5128caa; the pre-existing uv.lock modification
and .claude/ untracked path remain visible; no plan task stages them.

- [x] **Step 2: Confirm no Plan 10.x slot was allocated on origin/main.**

Run:

~~~
git ls-tree -r --name-only origin/main docs/superpowers/plans | Select-String -Pattern 'plan-10'
git grep -n -E 'Plan 10\.[0-9]' origin/main -- docs/superpowers/plans README.md
~~~

Expected: no output from either command. The existing Plan 10 umbrella and its sequential-slot
allocation rule remain; this pickup assigns the first actual slot, Plan 10.1.

- [x] **Step 3: Obtain review and operator approval for these exact plan bytes.**

The reviewer verifies the FU-5 split trigger, FU-7 confirmation-gate safety boundary, explicit
statement that the effective-row display gap remains open under FU-7, task-level evidence, and
explicit exclusions. The operator approves the same scope. Record both
statements and the exact plan path in docs/superpowers/reviews/2026-07-23-plan-10-1-implementation-plan-approval.md.

- [x] **Step 4: Freeze the approved plan digest before implementation.**

Run:

~~~
(Get-FileHash -Algorithm SHA256 docs/superpowers/plans/2026-07-23-plan-10-1-p9-96-follow-up-remediation.md).Hash
~~~

Record the exact uppercase hash, baseline commit, reviewer statement, operator statement, and scope
in the approval record. Any substantive plan-text change after this step requires fresh review and a
new approval record; checkbox-only progress is allowed only under the repository's established plan
protocol.

- [x] **Step 5: Start the implementation lane only after the approval record exists.**

Implementation must begin from a fresh branch based on the latest origin/main, and the implementing
agent must first read this plan's checkpoint log and verify it against git status, the plan digest,
and the named source anchors. No production or test mutation belongs in the planning branch before
that handoff.

---

### Task 1: Investigate and Disposition P9.96-FU-5 Before Any Bundle Expansion

**Files:**
- Inspect: src/optimus/acp/bootstrap.py, src/optimus/acp/errors.py, src/optimus/acp/trusted_paths.py, src/optimus/acp/preflight.py
- Inspect: tests/unit/acp/test_bootstrap.py, tests/unit/acp/test_outbound_errors.py, tests/unit/acp/test_trusted_paths.py, tests/unit/acp/test_preflight.py
- Modify only if the investigation proves a contained live defect: the smallest owning source/test file pair
- Record: docs/superpowers/reviews/plan-10-1-review-checkpoints.md

**Interfaces:**
- Consumes the current exception constructors and catch sites; no new exception contract is assumed.
- Produces exactly one of: a closure disposition for FU-5; a contained fix landed inside Plan 10.1;
  or a reviewed split-out Plan 10.2-or-later design for FU-5 while the rest of this plan remains Plan 10.1.

- [x] **Step 1: Run the static recurrence inventory.**

Run:

~~~
rg -n -i '@contextmanager|FrozenInstanceError|StartupConfigurationError|AcpOutboundError|dataclass\(frozen=True\)' src tests -g '*.py'
~~~

Expected on the current baseline: no @contextmanager or FrozenInstanceError reference in
src; StartupConfigurationError and AcpOutboundError remain the candidate frozen exception
classes; the Plan 9.98-FU-1 trusted-path exception correction is already represented by its own
non-frozen error contract. Record the actual output, not a narration of it.

- [x] **Step 2: Run the behavior selectors before changing code.**

Run:

~~~
uv run --locked pytest tests/unit/acp/test_bootstrap.py tests/unit/acp/test_outbound_errors.py tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_preflight.py -q
~~~

Expected: the selector collects and passes or exposes a concrete failure; a collection error,
missing dependency, or generic environment error is not evidence of FU-5. If a failure occurs,
reduce it to a named constructor/catch/str()/attribute assertion before deciding that FU-5 is live.

- [x] **Step 3: Classify the result using the explicit split boundary.**

Close FU-5 with a checkpoint-log disposition and no source/test change when the inventory and behavior
selectors show no current recurrence and the existing types preserve their codes/messages through
their real call paths. A contained fix may remain in Plan 10.1 only when it adds no new exception
policy, persistence schema, cross-layer interface, or design decision and its RED test fails for the
specific observed symptom before the fix.

If the symptom needs real exception redesign, a context-manager contract, a new error propagation
policy, or cross-layer changes, stop this task. Create the next unused single-decimal Plan 10.x plan
for FU-5, obtain separate review, and leave FU-5 out of the Plan 10.1 implementation lane. Do not
renumber the remaining Plan 10.1 tasks.

- [x] **Step 4: Verify the selected disposition.**

For closure, run the exact focused selector from Step 2 again and record the passing output plus the
static-inventory result. For a contained fix, run the new named RED selector, then the Step 2 selector,
uv run --locked ruff check ., and git diff --check. For a split, record
the new plan path, allocation evidence, and the fact that no Plan 10.1 source/test scope widened.

---

### Task 2: Correct ACP Error Prefixes and Remove the Duplicate TOCTOU Comment

**Files:**
- Modify: src/optimus/acp/__main__.py:379-411
- Modify: tests/unit/acp/test_main_check_config.py
- Modify: tests/unit/acp/test_main_wiring.py

**Interfaces:**
- main() still returns the existing exception exit_code values.
- User-facing stderr for both PreflightFailure.user_message and StartupConfigurationError.user_message
  begins with the exact optimus-agent: prefix.
- The TOCTOU explanation remains once, with no runtime behavior change.

- [x] **Step 1: Add the failing prefix regressions.**

In tests/unit/acp/test_main_check_config.py, extend the existing
test_check_config_prints_preflight_failure assertion:

~~~
stderr = capsys.readouterr().err
assert stderr == "optimus-agent: Redis is not reachable.\n"
~~~

In tests/unit/acp/test_main_wiring.py, add a test beside the existing startup/serve-path tests:

~~~
def test_startup_configuration_error_has_agent_prefix(monkeypatch, tmp_path, capsys):
    env = _base_env()
    _authorize(monkeypatch, tmp_path, env)

    def fail_build(**_kwargs):
        raise acp_main.StartupConfigurationError(exit_code=2, user_message="startup configuration failed")

    monkeypatch.setattr(acp_main, "build_configured_server", fail_build)

    assert acp_main.main(["--no-auto-start", "--workspace-root", str(tmp_path)]) == 2
    assert capsys.readouterr().err == "optimus-agent: startup configuration failed\n"
~~~

Run the two RED selectors:

~~~
uv run --locked pytest tests/unit/acp/test_main_check_config.py::test_check_config_prints_preflight_failure tests/unit/acp/test_main_wiring.py::test_startup_configuration_error_has_agent_prefix -q
~~~

Expected: the new/strengthened assertions fail only because the two production prints omit the prefix.

- [x] **Step 2: Apply the minimal production correction and delete one comment copy.**

Change only these two prints:

~~~
print(f"optimus-agent: {exc.user_message}", file=sys.stderr)
~~~

Use it in both the PreflightFailure and StartupConfigurationError handlers. Delete the second
verbatim 11-line TOCTOU block, retaining the first block immediately before
revalidate_workspace_identity(candidate.workspace_identity).

- [x] **Step 3: Verify behavior and source hygiene.**

Run:

~~~
uv run --locked pytest tests/unit/acp/test_main_check_config.py tests/unit/acp/test_main_wiring.py -q
rg -n -F "Plan 9.96, Task 5 Step 7 (TOCTOU matrix): workspace identity is a" src/optimus/acp/__main__.py
git diff --check
~~~

Expected: the focused suite passes; the TOCTOU marker occurs once; git diff --check is clean.

---

### Task 3: Align Launch-Audit Docstrings with the Workspace-Local Runtime Root

**Files:**
- Modify: src/optimus/acp/launch_audit.py:1-5,62-70
- Modify: tests/unit/acp/test_launch_audit.py

**Interfaces:**
- append_launch_audit_event() keeps the signature and LaunchAuditError behavior unchanged.
- Both the module and function documentation call the location a workspace-local runtime root.
- No claim remains that the audit file lives under an external runtime root.

- [x] **Step 1: Add the failing documentation contract test.**

Add:

~~~
import inspect

import optimus.acp.launch_audit as launch_audit


def test_launch_audit_docs_describe_workspace_local_runtime_root() -> None:
    assert "workspace-local runtime root" in (launch_audit.__doc__ or "")
    function_doc = inspect.getdoc(launch_audit.append_launch_audit_event) or ""
    assert "workspace-local runtime root" in function_doc
    assert "trusted external runtime root" not in (launch_audit.__doc__ or "")
    assert "trusted external runtime root" not in function_doc
~~~

Run:

~~~
uv run --locked pytest tests/unit/acp/test_launch_audit.py::test_launch_audit_docs_describe_workspace_local_runtime_root -q
~~~

Expected: FAIL against the current wording.

- [x] **Step 2: Correct only the two misleading phrases.**

Use workspace-local runtime root in the module docstring and in the
append_launch_audit_event() docstring. Keep the existing security properties and the
require_workspace_runtime_root() call unchanged.

- [x] **Step 3: Verify the narrow documentation change.**

Run:

~~~
uv run --locked pytest tests/unit/acp/test_launch_audit.py -q
uv run --locked ruff check src/optimus/acp/launch_audit.py tests/unit/acp/test_launch_audit.py
git diff --check
~~~

Expected: all launch-audit unit tests, Ruff, and diff hygiene pass.

---

### Task 4: Replace the Unroutable Agent Default

**Files:**
- Modify: src/optimus/agent/defaults.py:5
- Modify: tests/unit/agent/test_defaults.py
- Modify: tests/unit/optimus_gateway/test_models.py
- Modify: tests/unit/acp/test_preflight.py only where the invalid-model fixture currently relies on the old implicit default

**Interfaces:**
- resolve_agent_model(environ, cli_model=None) -> str remains unchanged.
- The no-override default becomes the existing gateway alias claude-haiku.
- Explicit OPTIMUS_AGENT_MODEL and CLI values, including explicit glm-5.2 test values used by
  direct runner fixtures, remain unchanged.

- [ ] **Step 1: Pin the routing evidence and add the RED default assertion.**

Change the default test to assert the reviewed routable value while keeping the public constant
assertion:

~~~
def test_resolve_agent_model_falls_back_to_routable_shared_default():
    assert DEFAULT_AGENT_MODEL == "claude-haiku"
    assert resolve_agent_model({}) == "claude-haiku"
~~~

Add a routing regression beside the existing model-mapping tests:

~~~
def test_resolve_model_id_accepts_shared_agent_default_for_every_provider():
    assert resolve_model_id(provider="anthropic", model=DEFAULT_AGENT_MODEL) == "claude-haiku-4-5-20251001"
    assert resolve_model_id(provider="openrouter", model=DEFAULT_AGENT_MODEL) == "anthropic/claude-haiku-4.5"
    assert resolve_model_id(provider="openai", model=DEFAULT_AGENT_MODEL) == "gpt-4o-mini"
~~~

Import DEFAULT_AGENT_MODEL and resolve_model_id through their existing public modules. Before
production code changes, run:

~~~
uv run --locked pytest tests/unit/agent/test_defaults.py::test_resolve_agent_model_falls_back_to_routable_shared_default tests/unit/optimus_gateway/test_models.py::test_resolve_model_id_accepts_shared_agent_default_for_every_provider -q
~~~

Expected: the RED default assertion fails against glm-5.2 and the mapping selector passes against
the existing routing table. Add the imports before running this command; a collection error is not
an acceptable substitute for the intended assertion failure.

- [ ] **Step 2: Make the smallest fix and make invalid-model tests explicit.**

Set:

~~~
DEFAULT_AGENT_MODEL = "claude-haiku"
~~~

If tests/unit/acp/test_preflight.py has a fake Gateway that rejects glm-5.2 to prove strict
model failure, add OPTIMUS_AGENT_MODEL: glm-5.2 to that test's input mapping so it tests an
explicit invalid request rather than depending on a dead default. Do not mass-rewrite direct runner
fixtures that intentionally use glm-5.2 as a fake model string.

- [ ] **Step 3: Verify model resolution, preflight, and pricing compatibility.**

Run:

~~~
uv run --locked pytest tests/unit/agent/test_defaults.py tests/unit/optimus_gateway/test_models.py tests/unit/optimus_gateway/test_pricing.py tests/unit/acp/test_preflight.py -q
uv run --locked ruff check src/optimus/agent/defaults.py tests/unit/agent/test_defaults.py tests/unit/optimus_gateway/test_models.py tests/unit/acp/test_preflight.py
git diff --check
~~~

Expected: the default resolves to claude-haiku, all three provider aliases resolve to priced
identifiers, explicit invalid-model coverage remains meaningful, and no secret or gateway contract
changes appear in the diff.

---

### Task 5: Add the FU-7 Confirmation Gate Only

**Files:**
- Modify: src/optimus/acp/launch_approval_cli.py:264-316
- Modify: tests/unit/acp/test_launch_approval_cli.py

**Interfaces:**
- _cmd_approve(workspace_root, *, mode, target_argv) remains the command entry point and returns
  the existing success/nonzero codes. A declined confirmation returns 1, writes no approval,
  spawns no one-shot target, and prints a value-free cancellation message.
- _display_candidate(candidate) remains display-only.
- Candidate resolution, LaunchDisplayRow construction, credential resolution, approval digests, and
  child-environment projections are unchanged by this task.
- This closes only the confirmation-gate half of P9.96-FU-7. The effective-row display gap for
  keyring/config/default-sourced settings remains open under P9.96-FU-7; it is not a new catalog ID,
  new plan document, or scope of this task.

- [ ] **Step 1: Add RED tests for confirmation ordering and no-write decline.**

In tests/unit/acp/test_launch_approval_cli.py, add a small private helper beside the existing
approval tests. It must create tmp_path / "workspace", create tmp_path / "config", set
OPTIMUS_GATEWAY_URL, OPTIMUS_API_KEY, OPTIMUS_REDIS_URL, and OPTIMUS_CONFIG_ROOT, construct the
existing FakeKeyring and KeyringApprovalStore, and patch _resolve_store to return that store. Import
launch_approval_cli as cli_module, KeyringApprovalStore, and FakeKeyring through their existing
modules. Each test then patches cli_module._require_tty to return None and patches builtins.input.
Define the helper concretely as follows, then use it to add these assertions:

~~~
def _approval_cli_case(tmp_path, monkeypatch):
    from optimus.acp import launch_approval_cli as cli_module
    from optimus.acp.launch_approvals import KeyringApprovalStore
    from tests.unit.acp.conftest import FakeKeyring

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    for name, value in {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "test-key",
        "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        "OPTIMUS_CONFIG_ROOT": str(config_root),
    }.items():
        monkeypatch.setenv(name, value)
    fake_keyring = FakeKeyring()
    runtime_root = tmp_path / "approval-runtime"
    store = KeyringApprovalStore(keyring_backend=fake_keyring, runtime_root=runtime_root)
    monkeypatch.setattr(cli_module, "_resolve_store", lambda _workspace: (store, runtime_root))
    return cli_module, workspace, store


def test_approve_decline_does_not_build_or_write_record(monkeypatch, tmp_path, capsys):
    cli_module, workspace, store = _approval_cli_case(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_module, "_require_tty", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    build_calls: list[object] = []
    write_calls: list[object] = []
    real_build = cli_module.build_approval_record

    def observe_build(**kwargs):
        build_calls.append(kwargs)
        return real_build(**kwargs)

    monkeypatch.setattr(cli_module, "build_approval_record", observe_build)
    monkeypatch.setattr(store, "write_durable", lambda record: write_calls.append(record))

    assert cli_module._cmd_approve(workspace, mode="durable", target_argv=[]) == 1
    assert build_calls == []
    assert write_calls == []
    assert "cancel" in capsys.readouterr().out.lower()


@pytest.mark.parametrize("answer", ["", "n", "no", "anything"])
def test_approve_decline_does_not_build_or_write_for_non_yes(monkeypatch, tmp_path, answer):
    cli_module, workspace, store = _approval_cli_case(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_module, "_require_tty", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: answer)
    monkeypatch.setattr(cli_module, "build_approval_record", lambda **_: pytest.fail("record must not build"))
    monkeypatch.setattr(store, "write_durable", lambda _record: pytest.fail("durable record must not write"))

    assert cli_module._cmd_approve(workspace, mode="durable", target_argv=[]) == 1


@pytest.mark.parametrize("answer", ["y", "Y", "yes", "YES"])
def test_approve_accepts_only_explicit_yes_answers(monkeypatch, tmp_path, answer):
    cli_module, workspace, store = _approval_cli_case(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_module, "_require_tty", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: answer)
    written: list[object] = []
    monkeypatch.setattr(store, "write_durable", lambda record: written.append(record))

    assert cli_module._cmd_approve(workspace, mode="durable", target_argv=[]) == 0
    assert len(written) == 1
~~~

Add a parallel one-shot decline test that supplies a non-yes answer, patches store.write_one_shot
and cli_module.subprocess.run to fail if called, and asserts
_cmd_approve(workspace, mode="one-shot", target_argv=[sys.executable, "-c", "pass"]) returns 1.
The implementation test fixture must assert the ordering directly: build_approval_record is not
called until after the answer is accepted. Run the RED selector before touching production code:

~~~
uv run --locked pytest tests/unit/acp/test_launch_approval_cli.py -k "approve and (decline or explicit_yes)" -q
~~~

Expected: the decline test fails because the current command builds/writes without asking, and the
acceptance test fails because no input is read. Update the existing durable and one-shot success
tests in this file to feed an explicit y answer before rerunning the suite; otherwise they would
block on captured stdin rather than test the intended behavior.

- [ ] **Step 2: Implement the confirmation gate after display and before record construction.**

Add a small helper in launch_approval_cli.py:

~~~
def _confirm_approval() -> bool:
    try:
        answer = input("optimus-trust: approve this exact launch configuration? [y/N]: ")
    except EOFError:
        answer = ""
    if answer.strip().casefold() in {"y", "yes"}:
        return True
    print("optimus-trust: approval cancelled; no record was written.")
    return False
~~~

Call it immediately after _display_candidate(candidate) and before hmac_key = store.hmac_key
or the build_approval_record call. Add this source comment directly at the call site:

~~~
_display_candidate(candidate)

# P9.96-FU-7: the confirmation gate is enforced here; the effective-row display gap
# for keyring/config/default-sourced settings remains open under this same finding.
if not _confirm_approval():
    return 1
~~~

On False, return 1; do not create a nonce, write a durable or one-shot record, substitute argv, or
spawn a target. Apply the same gate to both durable and one-shot approval modes. Update all existing
successful durable and one-shot approval tests in this file to supply an explicit y/yes answer.
Then run:

~~~
uv run --locked pytest tests/unit/acp/test_launch_approval_cli.py -q
uv run --locked pytest tests/unit/acp/test_launch_approval_cli.py -k "approve or one_shot" -q
uv run --locked ruff check src/optimus/acp/launch_approval_cli.py tests/unit/acp/test_launch_approval_cli.py
git diff --check
~~~

Expected: decline never builds/writes/spawns; affirmative y, Y, yes, and YES write exactly one
valid record; blank/n/other input declines; the existing candidate display, digest, one-key child
environment, and all pre-existing FU-7 display behavior remain unchanged.

---

### Task 6: Reconcile the Stable-ID Catalog, Roadmap, README, and FU-6 Disposition

**Files:**
- Modify: docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md
- Modify: docs/superpowers/plans/2026-07-01-phase-1-roadmap.md
- Modify: README.md
- Modify: docs/superpowers/reviews/plan-10-1-review-checkpoints.md only; never stage it

**Interfaces:**
- The consolidated backlog remains the sole detailed catalog for the seven P9.96-FU-* IDs.
- The roadmap remains the plan-status and sequencing source; README remains a short pointer.
- The documentation records exact implementation commit/evidence identifiers obtained from the
  completed task, not prose-only completion claims.

- [ ] **Step 1: Record task-level evidence before editing status.**

Update the checkpoint log with each task's focused test command, pass result, changed-file list,
and the full implementation commit SHA once the implementation lane has committed. For FU-5, record
the static inventory and behavior-selector result and the selected closure/split disposition. For
FU-6, record that the already-applied correction was verified as uv run plus global options before
the subcommand and required no code change.

- [ ] **Step 2: Promote or close each catalog entry without deleting history.**

In the P9.96 Task 9 Disclosed Follow-Ups section, update the statuses as follows after evidence is
complete:

~~~
FU-1, FU-2, FU-3, FU-4: Closed by Plan 10.1, with the full implementation commit and named tests.
FU-5: Closed by Plan 10.1 only if Task 1 found no recurrence or a contained fix; otherwise Promoted
      to the separately reviewed FU-5 Plan 10.x file named in the checkpoint log.
FU-6: Closed by reviewed Plan 10.1 disposition; execution correction only, no code change.
FU-7: Partially addressed by Plan 10.1 (confirmation gate landed); effective-row display gap remains
      open under P9.96-FU-7. Keep this original row open; add no new catalog ID or plan document.
~~~

Keep each stable ID and its original summary. Add a short Plan 10.1 disposition paragraph for FU-6
that states the corrected command shape, the applied date/evidence, and that FU-6 was not a source
defect. Do not invent a commit for the no-code disposition.

- [ ] **Step 3: Update roadmap and README consistently.**

In 2026-07-01-phase-1-roadmap.md, retain the Plan 10 umbrella allocation rule, add a dated
Plan 10.1 entry linked to this plan, and replace the Plan 9.96 sentence that says all seven
disclosures are merely tracked with the exact FU-1..FU-7 dispositions, including FU-7's partial
status and remaining open display gap. If FU-5 split out, name its own Plan 10.x link and leave it
open under that plan. Update the recommended sequence so Plan 10.1 appears as the first allocated
Plan 10.x item without implying the entire Plan 10 pool is closed.

In README.md, keep the Plan 10 pool description and add one concise sentence linking Plan 10.1,
its six-item scope, FU-7's partial confirmation-gate status, and the FU-6 no-code disposition. Do
not duplicate the full catalog or create a separate Plan 10 backlog document.

- [ ] **Step 4: Verify cross-document custody and no accidental scope.**

Run:

~~~
rg -n -i "Plan 10\.1|P9\.96-FU-[1-7]|FU-6|consolidated deferred follow-ups" README.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md
git diff --check
~~~

Expected: every P9.96-FU-* row has exactly one honest closure, partial-open status, or owning Plan
10.x disposition; FU-7 remains open under its original row; FU-6 explicitly says no code change; the
Plan 10 pool remains open for unrelated items; no new catalog ID or Plan 10 backlog document appears;
and no frozen Plan 9.96 file appears in the diff.

---

### Task 7: Repository-Wide Fitness and Handoff Gate

**Files:**
- Inspect all changed files from Tasks 1-6.
- Modify: docs/superpowers/reviews/plan-10-1-review-checkpoints.md only for final evidence; never stage it.

**Produces:** A complete, evidence-backed Plan 10.1 handoff with no unverified checkbox or scope claim.

- [ ] **Step 1: Run the affected unit suites and default suite.**

Run:

~~~
uv run --locked pytest tests/unit/acp/test_main_check_config.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_launch_audit.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_preflight.py tests/unit/agent/test_defaults.py tests/unit/optimus_gateway/test_models.py tests/unit/optimus_gateway/test_pricing.py -q
uv run --locked pytest -q
~~~

Expected: both commands pass under the repository's default marker policy, with live Redis/Gateway,
ACPX, and E2E tests still deselected unless explicitly requested by their markers.

- [ ] **Step 2: Run coverage, Ruff, and diff hygiene.**

Run:

~~~
uv run --locked pytest --cov=optimus --cov=optimus_gateway --cov=optimus_security --cov-report=term-missing --cov-fail-under=80 -q
uv run --locked ruff check .
git diff --check
git status --short --branch
~~~

Expected: aggregate production coverage is at least 80%, Ruff is clean, diff hygiene is clean, and
the final status shows only intentional Plan 10.1 files plus the pre-existing uv.lock and .claude/
state. Do not stage the checkpoint log, uv.lock, or .claude/.

- [ ] **Step 3: Perform the final safety audit.**

Run:

~~~
rg -n -i "P9\.96-FU-7|effective-row display gap" src/optimus/acp/launch_approval_cli.py
rg -n -i "trusted external runtime root" src/optimus/acp/launch_audit.py
rg -n -i "@contextmanager|FrozenInstanceError" src/optimus tests
~~~

Expected: the first command finds the source comment naming the remaining FU-7 display gap; the
second has no output because the corrected docstrings contain only the workspace-local wording; FU-5
terms in the third command appear only if the investigation found a real recurrence and its
disposition records the owning Plan 10.x split.

- [ ] **Step 4: Complete the handoff.**

Update the checkpoint log with the final full commit SHA, all passing command outputs, coverage
percentage, Ruff result, catalog/roadmap status, FU-5 outcome, FU-6 disposition, and the intentional
pre-existing dirty paths. The implementer then presents the exact diff and evidence for reviewer and
operator sign-off. No merge, push, branch deletion, or history rewrite is authorized by this plan.

## Definition of Done

- The reviewed Plan 10.1 plan and approval record are digest-pinned before implementation.
- FU-5 has a recorded evidence-based closure, contained fix, or separately owned Plan 10.x split;
  no speculative exception redesign is hidden inside this bundle.
- Both raw ACP startup/preflight messages have the optimus-agent: prefix, and the duplicate TOCTOU
  comment is gone with the surviving explanation intact.
- Launch-audit documentation accurately says workspace-local runtime root.
- The no-override agent default is claude-haiku, and provider routing tests prove it resolves through
  the existing aliases and pricing snapshots.
- optimus-trust approve requires explicit y/yes confirmation after display and before any record
  build/write/spawn; all decline paths are safe and tested.
- P9.96-FU-7's confirmation-gate half is landed and tested; its effective-row display gap remains
  explicitly open under the original FU-7 row, with no new ID or plan document.
- The stable-ID catalog, roadmap, README, and checkpoint log agree on every FU-1..FU-7 disposition;
  FU-6 explicitly has no code change.
- Affected tests, default tests, coverage >=80%, Ruff, diff hygiene, and final secret/scope audits pass.
