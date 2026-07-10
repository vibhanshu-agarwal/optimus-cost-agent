# Plan 8.5 Release-Gate Hardening and Golden-Harness Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the Plan 8 release-gate hardening gaps so shadow promotion matches the state evaluated by gates, one-key scanning covers the release runner's local artifact surface, golden tasks are wired through a real CLI harness path, command gates cannot hang forever, shadow copies are bounded, and fitness-gate telemetry carries reconcilable cost.

**Architecture:** Keep this as a focused hardening layer over the Plan 8 modules already present in `src/optimus/gates`, `src/optimus/retry`, `src/optimus/golden`, and `src/optimus/release`. Use small compatibility-preserving model changes where needed: represent shadow changes explicitly as writes or deletes, snapshot copied shadow files with content digests, centralize release credential scan paths, add bounded command execution, and wire golden-task execution through JSON `GoldenTaskResult` evidence rather than manual in-process injection. Do not reopen Plan 7 usage accounting, Plan 9 bounded loops/skills, or Plan 11 context-window optimization gates.

**Tech Stack:** Python >=3.14, pydantic >=2.8, pytest, pytest-asyncio, coverage.py, pytest-cov, stdlib `argparse`, `dataclasses`, `decimal`, `json`, `pathlib`, `shutil`, `subprocess`, `tempfile`, and existing `optimus.gates`, `optimus.golden`, `optimus.release`, `optimus.retry`, `optimus.runtime`, and `optimus.telemetry` modules. No new runtime dependency is required.

---

## Source Anchors

- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, Plan 8.5: close release-gate hardening gaps after Plan 8 and before Plan 9.
- `docs/superpowers/plans/2026-07-05-retry-fitness-gates-golden-tasks-release-gate.md`, Deferred Follow-Ups:
  - `P8-FU-1`: propagate deletions from shadow workspaces.
  - `P8-FU-2`: make shadow copy ignore rules configurable.
  - `P8-FU-3`: remove `fail_after_promoted_paths` from production APIs.
- Plan 8 implementation currently in this worktree:
  - `src/optimus/gates/shadow_workspace.py`
  - `src/optimus/gates/mutation_flow.py`
  - `src/optimus/retry/gated_run.py`
  - `src/optimus/release/credentials.py`
  - `src/optimus/release/defaults.py`
  - `src/optimus/release/runner.py`
  - `tools/run_phase1_release_gate.py`
- PR #21 review findings from 2026-07-06, reflected in the roadmap Plan 8.5 section: shadow deletion divergence, narrow one-key scan surface, golden harness not reachable from the default CLI, missing command timeout, expensive shadow copies, placeholder fitness-gate cost, test-only promotion failure hook on a production-callable API, and the optional `CompositeGateError` import cleanup.
- `docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf`, sections 9, 12, and 13: bounded retry, no partial writes on failure, golden task expected mode/tools/cost/final state, ordered Phase 1 release gates, and one-key go/no-go.
- `AGENTS.md`: local runtime credentials remain limited to `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; failed fitness gates must leave no partial writes; mutation paths must pass through `MutationGuard` / `assert_mutation_allowed()`.

## Review Finding Traceability

| ID | Finding | Owner Task |
|----|---------|------------|
| P8-FU-1 / Critical #1 | Shadow promotion never deletes files removed by the shadow candidate | Task 1 |
| P8-FU-2 / Review #5 | Shadow workspace copies large local directories with a narrow hardcoded ignore list | Task 2 |
| P8-FU-3 | `fail_after_promoted_paths` is a test hook on production-callable APIs | Task 3 |
| Review #2 | One-key gate scans only `.env`, `.env.local`, and `pyproject.toml` | Task 4 |
| Plan 8 unchecked test-plan item | Release CLI cannot reach a golden-task PASS without manual harness injection | Task 5 |
| Review #4 | `CommandGate` has no subprocess timeout | Task 6 |
| Review #6 | `GatedRetryRunner._emit_fitness_gate` hardcodes `cost_usd=Decimal("0")` | Task 7 |
| Review #7, optional | `classify_failure()` imports `CompositeGateError` lazily even though the current module graph can support a cleaner shared exception import | Task 8 |

## Scope

### In Scope

- Explicit shadow change records for writes and deletions, computed from SHA-256 digests of the copied shadow baseline rather than from the full workspace.
- Deletion promotion after gates pass, with rollback that restores deleted files if any later promotion operation fails.
- Configurable shadow copy ignore patterns that preserve safe defaults and add large local directories such as `.venv`, `node_modules`, build outputs, and caches.
- A test-only promotion fault seam that does not appear on production runtime APIs.
- Release credential scan defaults that include every local artifact class the release runner reads or produces by default.
- CLI support for golden-task result JSON files that satisfy the `GoldenTaskHarness` protocol without code injection.
- A documented Sprint 1 evidence rule: a local JSON harness can make the release gate executable, but Sprint 1 sign-off still requires the JSON results to come from an actual Optimus-only Plan-mode and Agent-mode run, or the missing staging Gateway run must be reported as not run.
- Command timeout support with failed-gate reporting and redacted timeout summaries.
- Fitness-gate telemetry cost emitted from candidate/gate metadata, not a placeholder.
- A clear note that deletion promotion is authorized through the existing `MutationKind.WRITE_FILE` guard because the runtime does not yet have a separate `DELETE_FILE` mutation kind.
- Focused tests, coverage gates, README updates, and diff hygiene checks.

### Out of Scope

- Building the full interactive agent loop or Plan 9 `GoalLoopController`.
- Adding DeepEval, OpenEvals, Ragas, PyRIT, LangSmith SDK, or any local provider-key dependency.
- Adding Plan 11 context-window optimization gates or enforcing uncalibrated cost-savings placeholders.
- Rewriting Plan 7 usage accounting, evidence ledger, or observability export behavior.
- Treating synthetic golden results as Sprint 1 staging evidence. Synthetic fixtures can prove wiring; release evidence must name whether a real Optimus-only run was performed.

### Dependency Notes

- Start this implementation only after the Plan 8 branch has been accepted or merged to `main`.
- Branch from latest `main` following `CONTRIBUTING.md`, for example `agent/cursor/plan-8-5-release-gate-hardening`.
- Preserve the one-key model: do not add local OpenAI, OpenRouter, Tavily, GLM, Anthropic, Azure OpenAI, Google, or LangSmith credentials.
- Keep commits approval-gated. The commit steps below are checkpoints for the implementor; do not run `git commit` unless the user explicitly approves.

## File Structure

- Modify: `src/optimus/gates/shadow_workspace.py` - add a copied-baseline digest snapshot, explicit shadow change operations, deletion promotion, rollback, configurable ignore patterns, and a module-private promotion function that tests can monkeypatch.
- Modify: `src/optimus/gates/mutation_flow.py` - remove `fail_after_promoted_paths` from `ShadowWorkspaceMutationRunner`, pass shadow ignore patterns, and keep production APIs free of fault-injection parameters.
- Modify: `src/optimus/release/credentials.py` - add central `DEFAULT_RELEASE_CREDENTIAL_SCAN_PATHS`, scan-boundary helpers, and JSON-aware artifact scanning that distinguishes provider-key names-as-data from provider-key assignment/object-key leaks.
- Modify: `src/optimus/release/defaults.py` - use central scan paths, accept an optional credential scan root, pass command timeouts, and accept a golden harness from CLI wiring.
- Modify: `src/optimus/release/runner.py` - add command timeout support and timeout failure reporting.
- Modify: `src/optimus/retry/gated_run.py` - thread candidate cost into `GatedAttempt` and fitness-gate telemetry.
- Create: `src/optimus/golden/json_harness.py` - load actual `GoldenTaskResult` records from JSON and expose `JsonGoldenTaskHarness`.
- Modify: `src/optimus/golden/__init__.py` - export JSON harness types if needed.
- Modify: `tools/run_phase1_release_gate.py` - parse `--golden-results`, `--python-executable`, and `--command-timeout-seconds`.
- Modify: `README.md` - document Plan 8.5 hardening behavior, golden result evidence, scan paths, and timeout defaults.
- Modify: `tests/unit/gates/test_mutation_flow.py` - deletion promotion, deletion rollback, ignore patterns, and production signature tests.
- Modify: `tests/unit/release/test_credentials.py` - default scan path and artifact detection tests.
- Modify: `tests/unit/release/test_defaults.py` - default scan wiring, timeout wiring, and CLI smoke tests.
- Modify: `tests/unit/release/test_runner.py` - timeout failure tests.
- Modify: `tests/unit/retry/test_gated_run.py` - candidate cost telemetry tests.
- Create: `tests/unit/golden/test_json_harness.py` - JSON result harness tests.
- Create: `tests/integration/release/test_phase1_release_gate_cli.py` - CLI PASS/FAIL wiring with deterministic local JSON results and injected command gates.
- Optional create: `src/optimus/gates/exceptions.py` - shared `CompositeGateError` home if Task 8 is approved.

## Human Agile Sizing

This is about 1-2 weeks of human development effort:

- Day 1-2: shadow baseline deletion propagation, rollback, and production API cleanup.
- Day 3: shadow ignore patterns and copy-cost tests.
- Day 4: one-key scan path centralization.
- Day 5-6: JSON golden harness and CLI wiring.
- Day 7: command timeout.
- Day 8: telemetry cost threading.
- Day 9: README and focused verification.
- Day 10: optional `CompositeGateError` import cleanup and reviewer fixes.

## Commit Policy for Execution

Each task includes a commit step because the Superpowers workflow favors small reviewable checkpoints. In this repo, commit steps are approval-gated: do not run `git commit`, push, delete branches, or rewrite history unless the user explicitly approves that action. If commit approval has not been granted, treat each commit step as a local checkpoint: run the narrow tests, run `git diff --check`, and leave the working tree ready for review.

---

## Task 1: Shadow-Workspace Deletion Propagation

**Traceability:** P8-FU-1, PR #21 Critical Issue #1

**Files:**
- Modify: `src/optimus/gates/shadow_workspace.py`
- Modify: `tests/unit/gates/test_mutation_flow.py`

**Guardrail note:** Deletion promotion remains covered by the existing `assert_mutation_allowed(context, MutationKind.WRITE_FILE)` check in `ShadowWorkspaceMutationRunner`. The runtime does not currently define `MutationKind.DELETE_FILE`; adding that policy surface is out of scope for Plan 8.5 unless a reviewer explicitly requests a broader mutation taxonomy change.

- [ ] **Step 1: Write failing deletion promotion tests**

Append to `tests/unit/gates/test_mutation_flow.py`:

```python
def test_shadow_deleted_file_is_removed_after_gates_pass(tmp_path):
    target = tmp_path / "obsolete.py"
    target.write_text("remove me\n", encoding="utf-8")
    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (PassingCheck(),))

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        apply_candidate=lambda shadow_root: (shadow_root / "obsolete.py").unlink(),
    )

    assert result.passed is True
    assert not target.exists()


def test_shadow_delete_and_write_promote_together(tmp_path):
    delete_me = tmp_path / "delete_me.py"
    keep_me = tmp_path / "keep_me.py"
    delete_me.write_text("old\n", encoding="utf-8")
    keep_me.write_text("old\n", encoding="utf-8")
    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (PassingCheck(),))

    def apply_candidate(shadow_root: Path) -> None:
        (shadow_root / "delete_me.py").unlink()
        (shadow_root / "keep_me.py").write_text("new\n", encoding="utf-8")

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        apply_candidate=apply_candidate,
    )

    assert result.passed is True
    assert not delete_me.exists()
    assert keep_me.read_text(encoding="utf-8") == "new\n"


def test_shadow_deletion_diff_does_not_delete_ignored_workspace_content(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "pyvenv.cfg").write_text("home = python\n", encoding="utf-8")
    obsolete = tmp_path / "obsolete.py"
    obsolete.write_text("remove me\n", encoding="utf-8")
    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (PassingCheck(),))

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        apply_candidate=lambda shadow_root: (shadow_root / "obsolete.py").unlink(),
    )

    assert result.passed is True
    assert not obsolete.exists()
    assert (tmp_path / ".git" / "config").read_text(encoding="utf-8") == "[core]\n"
    assert (tmp_path / ".venv" / "pyvenv.cfg").read_text(encoding="utf-8") == "home = python\n"
```

Add the import near the top of the file:

```python
from pathlib import Path
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/gates/test_mutation_flow.py::test_shadow_deleted_file_is_removed_after_gates_pass tests/unit/gates/test_mutation_flow.py::test_shadow_delete_and_write_promote_together tests/unit/gates/test_mutation_flow.py::test_shadow_deletion_diff_does_not_delete_ignored_workspace_content -v
```

Expected: FAIL because `ShadowWorkspace.changed_paths()` only walks files that exist in the shadow workspace.

- [ ] **Step 3: Introduce copied-baseline shadow change operations**

In `src/optimus/gates/shadow_workspace.py`, replace `ShadowPromotionPlan.changed_paths` with an operation-aware model while keeping a read-only compatibility property for callers/tests that still inspect changed paths. The key safety rule is that deletions are computed against the files copied into the shadow baseline, not against the full workspace. Ignored files such as `.git`, `.venv`, `node_modules`, caches, and build outputs must never be inferred as deletions merely because they were pruned from the shadow copy.

```python
from enum import StrEnum


class ShadowChangeKind(StrEnum):
    WRITE = "write"
    DELETE = "delete"


@dataclass(frozen=True)
class ShadowChange:
    relative_path: Path
    kind: ShadowChangeKind


@dataclass(frozen=True)
class ShadowPromotionPlan:
    workspace_root: Path
    shadow_root: Path
    changes: tuple[ShadowChange, ...]

    @property
    def changed_paths(self) -> tuple[Path, ...]:
        return tuple(change.relative_path for change in self.changes)
```

In `ShadowWorkspace.__init__()`, take the baseline snapshot immediately after `copytree()`:

```python
        self._baseline_digests = _file_digests_by_relative_path(self.shadow_root)
```

Add the snapshot helper:

```python
import hashlib


def _file_digests_by_relative_path(root: Path) -> dict[Path, str]:
    return {
        path.relative_to(root): _sha256_file(path)
        for path in root.rglob("*")
        if path.is_file()
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
```

Replace `ShadowWorkspace.changed_paths()` with `ShadowWorkspace.changes()` and keep `changed_paths()` as a compatibility wrapper:

```python
    def changes(self) -> tuple[ShadowChange, ...]:
        changes: list[ShadowChange] = []
        shadow_digests = _file_digests_by_relative_path(self.shadow_root)

        for relative in sorted(set(self._baseline_digests) | set(shadow_digests)):
            if relative in self._baseline_digests and relative not in shadow_digests:
                changes.append(ShadowChange(relative_path=relative, kind=ShadowChangeKind.DELETE))
            elif relative not in self._baseline_digests or shadow_digests[relative] != self._baseline_digests[relative]:
                changes.append(ShadowChange(relative_path=relative, kind=ShadowChangeKind.WRITE))
        return tuple(changes)

    def changed_paths(self) -> tuple[Path, ...]:
        return tuple(change.relative_path for change in self.changes())

    def promotion_plan(self) -> ShadowPromotionPlan:
        return ShadowPromotionPlan(
            workspace_root=self.workspace_root,
            shadow_root=self.shadow_root,
            changes=self.changes(),
        )
```

Replace `promote_shadow_changes()` with operation-aware promotion. Keep the existing `fail_after_promoted_paths` keyword temporarily in Task 1 so the module stays green between Task 1 and Task 3; Task 3 removes it from all production-callable surfaces.

```python
def promote_shadow_changes(plan: ShadowPromotionPlan, *, fail_after_promoted_paths: int | None = None) -> None:
    backups: list[tuple[Path, bytes | None]] = []
    promoted_count = 0
    try:
        for change in plan.changes:
            source = plan.shadow_root / change.relative_path
            target = plan.workspace_root / change.relative_path
            backups.append((target, target.read_bytes() if target.exists() else None))
            if change.kind is ShadowChangeKind.DELETE:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            promoted_count += 1
            if fail_after_promoted_paths is not None and promoted_count >= fail_after_promoted_paths:
                raise RuntimeError("simulated promotion failure")
    except Exception:
        _restore_backups(backups)
        raise
```

- [ ] **Step 4: Run deletion tests and full mutation-flow tests**

Run:

```bash
pytest tests/unit/gates/test_mutation_flow.py -v
```

Expected: PASS. Task 1 keeps a temporary compatibility shim for `fail_after_promoted_paths` so this task is independently green. Task 3 removes that shim and migrates rollback coverage to a module-private test seam.

- [ ] **Step 5: Local checkpoint**

Run:

```bash
git diff --check
git status --short
```

Expected: only Plan 8.5 gate files/tests are modified, plus pre-existing unrelated IDE/tooling noise remains untouched.

Commit only if explicitly approved:

```bash
git add src/optimus/gates/shadow_workspace.py tests/unit/gates/test_mutation_flow.py
git commit -m "Propagate shadow workspace deletions."
```

---

## Task 2: Shadow Copy Ignore Defaults

**Traceability:** P8-FU-2, PR #21 Review #5

**Files:**
- Modify: `src/optimus/gates/shadow_workspace.py`
- Modify: `src/optimus/gates/mutation_flow.py`
- Modify: `tests/unit/gates/test_mutation_flow.py`

- [ ] **Step 1: Write failing ignore-pattern tests**

Append to `tests/unit/gates/test_mutation_flow.py`:

```python
def test_shadow_workspace_skips_large_default_ignored_directories(tmp_path):
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "secret_provider.py").write_text("OPENAI_API_KEY='sk-test'\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "module.py").write_text("value = 1\n", encoding="utf-8")

    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (PassingCheck(),))

    seen_shadow_paths: list[Path] = []

    def apply_candidate(shadow_root: Path) -> None:
        seen_shadow_paths.extend(path.relative_to(shadow_root) for path in shadow_root.rglob("*"))
        (shadow_root / "src" / "module.py").write_text("value = 2\n", encoding="utf-8")

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        apply_candidate=apply_candidate,
    )

    assert result.passed is True
    assert Path(".venv") not in seen_shadow_paths
    assert Path(".venv/secret_provider.py") not in seen_shadow_paths
    assert (tmp_path / "src" / "module.py").read_text(encoding="utf-8") == "value = 2\n"


def test_shadow_workspace_accepts_extra_ignore_patterns(tmp_path):
    (tmp_path / ".local-cache").mkdir()
    (tmp_path / ".local-cache" / "large.bin").write_text("skip\n", encoding="utf-8")
    (tmp_path / "module.py").write_text("value = 1\n", encoding="utf-8")

    runner = ShadowWorkspaceMutationRunner(
        checks_factory=lambda shadow_root: (PassingCheck(),),
        ignore_patterns=(".local-cache",),
    )

    def apply_candidate(shadow_root: Path) -> None:
        assert not (shadow_root / ".local-cache").exists()
        (shadow_root / "module.py").write_text("value = 2\n", encoding="utf-8")

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        apply_candidate=apply_candidate,
    )

    assert result.passed is True
    assert (tmp_path / "module.py").read_text(encoding="utf-8") == "value = 2\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/gates/test_mutation_flow.py::test_shadow_workspace_skips_large_default_ignored_directories tests/unit/gates/test_mutation_flow.py::test_shadow_workspace_accepts_extra_ignore_patterns -v
```

Expected: FAIL because `ShadowWorkspace` currently ignores only `.git`, `__pycache__`, and `.pytest_cache`, and `ShadowWorkspaceMutationRunner` has no `ignore_patterns` argument.

- [ ] **Step 3: Add default and caller-provided ignore patterns**

In `src/optimus/gates/shadow_workspace.py`, add:

```python
DEFAULT_SHADOW_IGNORE_PATTERNS = (
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
    "build",
    "dist",
    "*.egg-info",
)
```

Update the constructor:

```python
class ShadowWorkspace:
    def __init__(self, *, workspace_root: Path, ignore_patterns: tuple[str, ...] = ()) -> None:
        self.workspace_root = workspace_root.resolve()
        self.ignore_patterns = tuple(dict.fromkeys((*DEFAULT_SHADOW_IGNORE_PATTERNS, *ignore_patterns)))
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.shadow_root = Path(self._temporary_directory.name) / self.workspace_root.name
        shutil.copytree(
            self.workspace_root,
            self.shadow_root,
            ignore=shutil.ignore_patterns(*self.ignore_patterns),
        )
```

In `src/optimus/gates/mutation_flow.py`, update the runner constructor and shadow creation:

```python
    def __init__(
        self,
        *,
        checks_factory: Callable[[Path], tuple[FitnessCheck, ...]],
        ignore_patterns: tuple[str, ...] = (),
    ) -> None:
        self._checks_factory = checks_factory
        self._ignore_patterns = ignore_patterns
```

```python
        shadow = ShadowWorkspace(workspace_root=Path(workspace_root), ignore_patterns=self._ignore_patterns)
```

- [ ] **Step 4: Run gate tests**

Run:

```bash
pytest tests/unit/gates/test_mutation_flow.py -v
```

Expected: PASS. The copied-baseline diff from Task 1 prevents ignored paths from being promoted as deletions; Task 3 later removes the temporary rollback fault-injection keyword.

- [ ] **Step 5: Local checkpoint**

```bash
git diff --check
```

Commit only if explicitly approved:

```bash
git add src/optimus/gates/shadow_workspace.py src/optimus/gates/mutation_flow.py tests/unit/gates/test_mutation_flow.py
git commit -m "Bound shadow workspace copy surface."
```

---

## Task 3: Remove Promotion Failure Test Hook From Production API

**Traceability:** P8-FU-3

**Files:**
- Modify: `src/optimus/gates/shadow_workspace.py`
- Modify: `src/optimus/gates/mutation_flow.py`
- Modify: `tests/unit/gates/test_mutation_flow.py`

- [ ] **Step 1: Replace the existing rollback test with a module-private fault seam**

Replace `test_promote_failure_rolls_back_previous_file` in `tests/unit/gates/test_mutation_flow.py` with:

```python
def test_promote_failure_rolls_back_write_and_delete(tmp_path, monkeypatch):
    from optimus.gates import shadow_workspace as shadow_workspace_module

    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    delete_me = tmp_path / "delete_me.py"
    first.write_text("value = 1\n", encoding="utf-8")
    second.write_text("value = 1\n", encoding="utf-8")
    delete_me.write_text("delete me\n", encoding="utf-8")

    promoted: list[Path] = []
    original_apply_shadow_change = shadow_workspace_module._apply_shadow_change

    def fail_after_first_change(change, source: Path | None, target: Path) -> None:
        promoted.append(target.name)
        if len(promoted) > 1:
            raise RuntimeError("simulated promotion failure")
        original_apply_shadow_change(change, source, target)

    monkeypatch.setattr(shadow_workspace_module, "_apply_shadow_change", fail_after_first_change)
    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (PassingCheck(),))

    with pytest.raises(RuntimeError, match="simulated promotion failure"):
        runner.run(
            context=approved_context(),
            workspace_root=tmp_path,
            apply_candidate=lambda shadow_root: (
                (shadow_root / "first.py").write_text("value = 2\n", encoding="utf-8"),
                (shadow_root / "second.py").write_text("value = 2\n", encoding="utf-8"),
                (shadow_root / "delete_me.py").unlink(),
            ),
        )

    assert first.read_text(encoding="utf-8") == "value = 1\n"
    assert second.read_text(encoding="utf-8") == "value = 1\n"
    assert delete_me.read_text(encoding="utf-8") == "delete me\n"
```

Add a production signature test:

```python
def test_mutation_runner_public_api_has_no_fail_after_promoted_paths_hook():
    import inspect

    signature = inspect.signature(ShadowWorkspaceMutationRunner)

    assert "fail_after_promoted_paths" not in signature.parameters
    assert "_promote_change" not in signature.parameters
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/gates/test_mutation_flow.py::test_promote_failure_rolls_back_write_and_delete tests/unit/gates/test_mutation_flow.py::test_mutation_runner_public_api_has_no_fail_after_promoted_paths_hook -v
```

Expected: FAIL because the production API still exposes `fail_after_promoted_paths`, and `shadow_workspace.py` does not yet have a module-private `_apply_shadow_change` function to monkeypatch in tests.

- [ ] **Step 3: Add module-private promotion function and remove production hook**

In `src/optimus/gates/shadow_workspace.py`, remove `fail_after_promoted_paths` from `promote_shadow_changes()` and add a module-private operation function:

```python
def _apply_shadow_change(change: ShadowChange, source: Path | None, target: Path) -> None:
    if change.kind is ShadowChangeKind.DELETE:
        target.unlink(missing_ok=True)
        return
    if source is None:
        raise ValueError("write promotion requires a source path")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
```

Update `promote_shadow_changes()` to call the private function and expose no fault-injection keyword:

```python
def promote_shadow_changes(plan: ShadowPromotionPlan) -> None:
    backups: list[tuple[Path, bytes | None]] = []
    try:
        for change in plan.changes:
            source = None if change.kind is ShadowChangeKind.DELETE else plan.shadow_root / change.relative_path
            target = plan.workspace_root / change.relative_path
            backups.append((target, target.read_bytes() if target.exists() else None))
            _apply_shadow_change(change, source, target)
    except Exception:
        _restore_backups(backups)
        raise
```

In `src/optimus/gates/mutation_flow.py`, remove `fail_after_promoted_paths` from `ShadowWorkspaceMutationRunner.__init__()` and remove the stored `_fail_after_promoted_paths` attribute:

```python
    def __init__(
        self,
        *,
        checks_factory: Callable[[Path], tuple[FitnessCheck, ...]],
        ignore_patterns: tuple[str, ...] = (),
    ) -> None:
        self._checks_factory = checks_factory
        self._ignore_patterns = ignore_patterns
```

Then call promotion with no test-only arguments:

```python
                promote_shadow_changes(shadow.promotion_plan())
```

- [ ] **Step 4: Run gate tests**

Run:

```bash
pytest tests/unit/gates/test_mutation_flow.py tests/integration/gates/test_composite_gate_failure_flow.py -v
```

Expected: PASS. Rollback coverage remains equivalent or stronger, and public runtime APIs no longer expose `fail_after_promoted_paths`.

- [ ] **Step 5: Local checkpoint**

```bash
git diff --check
```

Commit only if explicitly approved:

```bash
git add src/optimus/gates/shadow_workspace.py src/optimus/gates/mutation_flow.py tests/unit/gates/test_mutation_flow.py
git commit -m "Hide promotion fault injection from runtime APIs."
```

---

## Task 4: One-Key Scanner Default Wiring

**Traceability:** PR #21 Review #2

**Files:**
- Modify: `src/optimus/release/credentials.py`
- Modify: `src/optimus/release/defaults.py`
- Modify: `tests/unit/release/test_credentials.py`
- Modify: `tests/unit/release/test_defaults.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing default-surface tests**

Append to `tests/unit/release/test_credentials.py`:

```python
from pathlib import Path


def test_default_release_scan_paths_cover_runner_local_artifacts():
    from optimus.release.credentials import DEFAULT_RELEASE_CREDENTIAL_SCAN_PATHS

    expected = {
        Path(".env"),
        Path(".env.local"),
        Path("pyproject.toml"),
        Path("reports/phase1-release-gate.json"),
        Path("reports/phase1-golden-results.json"),
        Path("reports/process-state.json"),
    }

    assert expected.issubset(set(DEFAULT_RELEASE_CREDENTIAL_SCAN_PATHS))


def test_scanner_detects_provider_key_in_default_release_artifact(tmp_path, monkeypatch):
    from optimus.release.credentials import default_release_credential_scan_paths

    for key in PROVIDER_CREDENTIAL_NAMES | ALLOWED_LOCAL_CREDENTIAL_NAMES:
        monkeypatch.delenv(key, raising=False)
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "phase1-golden-results.json").write_text(
        '{"results": [{"provider_keys_resolvable": ["OPENAI_API_KEY"], "OPENAI_API_KEY": "sk-test"}]}',
        encoding="utf-8",
    )

    result = scan_local_credentials(
        environ={"OPTIMUS_GATEWAY_URL": "https://gateway.example", "OPTIMUS_API_KEY": "opt-test"},
        config_paths=default_release_credential_scan_paths(root=tmp_path),
    )

    assert result.passed is False
    assert result.provider_keys_resolvable == ("OPENAI_API_KEY",)
    assert "sk-test" not in result.summary


def test_scanner_does_not_fail_on_provider_key_names_as_report_data(tmp_path, monkeypatch):
    from optimus.release.credentials import default_release_credential_scan_paths

    for key in PROVIDER_CREDENTIAL_NAMES | ALLOWED_LOCAL_CREDENTIAL_NAMES:
        monkeypatch.delenv(key, raising=False)
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "phase1-golden-results.json").write_text(
        '{"results": [{"provider_keys_resolvable": ["OPENAI_API_KEY"]}]}',
        encoding="utf-8",
    )

    result = scan_local_credentials(
        environ={"OPTIMUS_GATEWAY_URL": "https://gateway.example", "OPTIMUS_API_KEY": "opt-test"},
        config_paths=default_release_credential_scan_paths(root=tmp_path),
    )

    assert result.passed is True
    assert result.provider_keys_resolvable == ()


def test_scanner_detects_provider_key_assignment_inside_json_string_value(tmp_path, monkeypatch):
    from optimus.release.credentials import default_release_credential_scan_paths

    for key in PROVIDER_CREDENTIAL_NAMES | ALLOWED_LOCAL_CREDENTIAL_NAMES:
        monkeypatch.delenv(key, raising=False)
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "phase1-release-gate.json").write_text(
        '{"results": [{"name": "unit-and-integration-tests", "output_summary": "OPENAI_API_KEY=sk-test"}]}',
        encoding="utf-8",
    )

    result = scan_local_credentials(
        environ={"OPTIMUS_GATEWAY_URL": "https://gateway.example", "OPTIMUS_API_KEY": "opt-test"},
        config_paths=default_release_credential_scan_paths(root=tmp_path),
    )

    assert result.passed is False
    assert result.provider_keys_resolvable == ("OPENAI_API_KEY",)
    assert "sk-test" not in result.summary
```

Append to `tests/unit/release/test_defaults.py`:

```python
def test_default_one_key_gate_uses_release_scan_paths(monkeypatch, tmp_path):
    from optimus.release import defaults

    captured_paths: list[Path] = []

    class ScanResult:
        passed = True
        summary = "ok"

    def fake_scan_local_credentials(*, config_paths=(), environ=None):
        captured_paths.extend(Path(path) for path in config_paths)
        return ScanResult()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(defaults, "scan_local_credentials", fake_scan_local_credentials)

    gate = next(
        gate
        for gate in build_phase1_release_gates(credential_scan_root=tmp_path)
        if gate.name == "one-key-credential-scan"
    )
    result = gate.run()

    assert result.passed is True
    assert (tmp_path / "reports" / "phase1-golden-results.json").resolve() in captured_paths
    assert (tmp_path / "reports" / "process-state.json").resolve() in captured_paths
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/release/test_credentials.py::test_default_release_scan_paths_cover_runner_local_artifacts tests/unit/release/test_credentials.py::test_scanner_detects_provider_key_in_default_release_artifact tests/unit/release/test_credentials.py::test_scanner_does_not_fail_on_provider_key_names_as_report_data tests/unit/release/test_credentials.py::test_scanner_detects_provider_key_assignment_inside_json_string_value tests/unit/release/test_defaults.py::test_default_one_key_gate_uses_release_scan_paths -v
```

Expected: FAIL because scan paths are hardcoded in `defaults.py`, do not include runner artifacts, are not rooted for isolated tests, and raw artifact scanning does not yet distinguish provider-key names-as-data from key assignment leaks while still detecting assignment-style leaks inside JSON string fields.

- [ ] **Step 3: Centralize default release scan paths**

In `src/optimus/release/credentials.py`, add:

```python
DEFAULT_RELEASE_CREDENTIAL_SCAN_PATHS = (
    Path(".env"),
    Path(".env.local"),
    Path("pyproject.toml"),
    Path("reports/phase1-release-gate.json"),
    Path("reports/phase1-golden-results.json"),
    Path("reports/process-state.json"),
)


def default_release_credential_scan_paths(*, root: str | Path = ".") -> tuple[Path, ...]:
    base = Path(root).resolve()
    return tuple((base / path).resolve() for path in DEFAULT_RELEASE_CREDENTIAL_SCAN_PATHS)
```

In `src/optimus/release/defaults.py`, import the helper:

```python
from optimus.release.credentials import default_release_credential_scan_paths, scan_local_credentials
```

```python
def _one_key_credential_gate(credential_scan_root: str | Path) -> tuple[bool, str]:
    result = scan_local_credentials(config_paths=default_release_credential_scan_paths(root=credential_scan_root))
    return result.passed, result.summary
```

Then update `build_phase1_release_gates()` and `_one_key_credential_gate()` so tests and callers can scan an isolated root. Do not add `command_timeout_seconds`, `include_command_gates`, or `CommandGate(..., timeout_seconds=...)` in Task 4; Task 6 owns command timeouts, and Task 5 owns `include_command_gates`.

```python
def build_phase1_release_gates(
    *,
    python_executable: str = "python",
    golden_harness: GoldenTaskHarness | None = None,
    credential_scan_root: str | Path = ".",
) -> tuple[ReleaseGate, ...]:
    return (
        CommandGate(
            name="unit-and-integration-tests",
            command=(python_executable, "-m", "pytest", "tests/unit", "tests/integration", "-q"),
        ),
        CommandGate(
            name="coverage-80",
            command=(
                python_executable,
                "-m",
                "pytest",
                "--cov=optimus",
                "--cov-branch",
                "--cov-report=term-missing",
                "--cov-fail-under=80",
                "-q",
            ),
        ),
        CommandGate(
            name="diff-whitespace-check",
            command=("git", "diff", "--check"),
        ),
        CallableGate(name="golden-task-suite", run=lambda: _golden_task_suite_gate(golden_harness)),
        CallableGate(name="one-key-credential-scan", run=lambda: _one_key_credential_gate(credential_scan_root)),
    )


def _one_key_credential_gate(credential_scan_root: str | Path) -> tuple[bool, str]:
    result = scan_local_credentials(config_paths=default_release_credential_scan_paths(root=credential_scan_root))
    return result.passed, result.summary
```

Make `_scan_config_files()` JSON-aware for `.json` artifacts: provider credential names under explicit names-as-data fields such as `provider_keys_resolvable` are not findings, provider credential names used as object keys with non-empty values are findings, and string leaves are still scanned with the assignment regex so report summaries such as `OPENAI_API_KEY=...` fail the gate. Keep the existing assignment-pattern scan for dotenv, TOML, YAML-like text, and unparseable JSON.

Update imports in `src/optimus/release/credentials.py`:

```python
import json
```

```python
JSON_NAMES_AS_DATA_KEYS = frozenset({"provider_keys_resolvable"})


def _scan_json_value(value: object, *, parent_key: str | None = None) -> set[str]:
    hits: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            canonical = _canonical_name(key)
            if canonical in PROVIDER_CREDENTIAL_NAMES and child not in (None, "", [], {}):
                hits.add(canonical)
            hits.update(_scan_json_value(child, parent_key=key))
    elif isinstance(value, list) and parent_key not in JSON_NAMES_AS_DATA_KEYS:
        for child in value:
            hits.update(_scan_json_value(child, parent_key=parent_key))
    elif isinstance(value, str) and parent_key not in JSON_NAMES_AS_DATA_KEYS:
        hits.update(_scan_text_for_provider_assignments(value))
    return hits


def _scan_text_for_provider_assignments(text: str) -> set[str]:
    hits: set[str] = set()
    names_pattern = "|".join(re.escape(name) for name in sorted(PROVIDER_CREDENTIAL_NAMES, key=len, reverse=True))
    pattern = re.compile(rf'["\']?\b({names_pattern})\b["\']?\s*[:=]', re.IGNORECASE)
    for match in pattern.finditer(text):
        hits.add(_canonical_name(match.group(1)))
    return hits
```

In `_scan_config_files()`, parse `.json` files with `json.loads()` first and use `_scan_json_value()` when parsing succeeds; fall back to `_scan_text_for_provider_assignments()` for non-JSON files or invalid JSON. This keeps the old assignment detection while suppressing only the names-as-data fields.

- [ ] **Step 4: Run release tests**

Run:

```bash
pytest tests/unit/release/test_credentials.py tests/unit/release/test_defaults.py -v
```

Expected: PASS.

- [ ] **Step 5: Update README scan boundary**

In the Phase 1 release-gate README section, replace the selected-config-file sentence with:

```markdown
The default one-key gate scans the local process environment plus `.env`,
`.env.local`, `pyproject.toml`, `reports/phase1-release-gate.json`,
`reports/phase1-golden-results.json`, and `reports/process-state.json`.
These report paths are scanned because the release runner reads or produces
them during Sprint 1 sign-off. Add any future release-runner local artifact to
`DEFAULT_RELEASE_CREDENTIAL_SCAN_PATHS` before it can carry credentials.
```

- [ ] **Step 6: Local checkpoint**

```bash
git diff --check
```

Commit only if explicitly approved:

```bash
git add src/optimus/release/credentials.py src/optimus/release/defaults.py tests/unit/release/test_credentials.py tests/unit/release/test_defaults.py README.md
git commit -m "Centralize release credential scan paths."
```

---

## Task 5: Golden Result JSON Harness and CLI Wiring

**Traceability:** Plan 8 unchecked test-plan item for golden-harness CLI and staging Gateway E2E evidence

**Files:**
- Create: `src/optimus/golden/json_harness.py`
- Modify: `src/optimus/golden/__init__.py`
- Modify: `tools/run_phase1_release_gate.py`
- Modify: `src/optimus/release/defaults.py`
- Create: `tests/unit/golden/test_json_harness.py`
- Modify: `tests/unit/release/test_defaults.py`
- Create: `tests/integration/release/test_phase1_release_gate_cli.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing JSON harness tests**

Create `tests/unit/golden/test_json_harness.py`:

```python
from __future__ import annotations

from decimal import Decimal

import pytest

from optimus.golden.json_harness import JsonGoldenTaskHarness, load_golden_results
from optimus.golden.tasks import GoldenTask, GoldenTaskResult


def task(task_id: str = "explain-small-function") -> GoldenTask:
    return GoldenTask(
        task_id=task_id,
        description="Explain a function.",
        expected_mode="plan_chat",
        expected_tools=("file_reader",),
        max_cost_usd=Decimal("0.005"),
        expected_final_state="chat_only",
        mutation_expected=False,
        release_gate=False,
    )


def test_load_golden_results_maps_results_by_task_id(tmp_path):
    path = tmp_path / "phase1-golden-results.json"
    path.write_text(
        """
        {
          "results": [
            {
              "task_id": "explain-small-function",
              "actual_mode": "plan_chat",
              "actual_tools": ["file_reader"],
              "actual_cost_usd": "0.004",
              "actual_final_state": "chat_only",
              "mutation_count": 0,
              "provider_keys_resolvable": []
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    results = load_golden_results(path)

    assert results["explain-small-function"] == GoldenTaskResult(
        task_id="explain-small-function",
        actual_mode="plan_chat",
        actual_tools=("file_reader",),
        actual_cost_usd=Decimal("0.004"),
        actual_final_state="chat_only",
        mutation_count=0,
        provider_keys_resolvable=(),
    )


def test_json_harness_returns_result_for_requested_task(tmp_path):
    path = tmp_path / "phase1-golden-results.json"
    path.write_text(
        '{"results":[{"task_id":"explain-small-function","actual_mode":"plan_chat","actual_tools":["file_reader"],"actual_cost_usd":"0.004","actual_final_state":"chat_only","mutation_count":0,"provider_keys_resolvable":[]}]}',
        encoding="utf-8",
    )

    harness = JsonGoldenTaskHarness.from_path(path)

    assert harness.run(task()).task_id == "explain-small-function"


def test_json_harness_fails_closed_for_missing_task_result(tmp_path):
    path = tmp_path / "phase1-golden-results.json"
    path.write_text('{"results":[]}', encoding="utf-8")

    harness = JsonGoldenTaskHarness.from_path(path)

    with pytest.raises(KeyError, match="missing golden result for explain-small-function"):
        harness.run(task())
```

- [ ] **Step 2: Write failing CLI wiring tests**

Append to `tests/unit/release/test_defaults.py`:

```python
def test_phase1_release_gate_script_accepts_golden_results_argument():
    text = Path("tools/run_phase1_release_gate.py").read_text(encoding="utf-8")

    assert "--golden-results" in text
    assert "JsonGoldenTaskHarness.from_path" in text
```

Create `tests/integration/release/test_phase1_release_gate_cli.py`:

```python
from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from optimus.golden.tasks import load_golden_tasks


def write_matching_results(path: Path) -> None:
    tasks = load_golden_tasks("tests/fixtures/golden_tasks/phase1_golden_tasks.json")
    payload = {
        "results": [
            {
                "task_id": task.task_id,
                "actual_mode": task.expected_mode,
                "actual_tools": list(task.expected_tools),
                "actual_cost_usd": str(min(task.max_cost_usd, Decimal("0.001"))),
                "actual_final_state": task.expected_final_state,
                "mutation_count": 1 if task.mutation_expected else 0,
                "provider_keys_resolvable": [],
            }
            for task in tasks
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_release_cli_accepts_golden_results_path(tmp_path, monkeypatch):
    results_path = tmp_path / "phase1-golden-results.json"
    write_matching_results(results_path)
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt-test")
    for provider_key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "TAVILY_API_KEY", "GLM_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(provider_key, raising=False)

    completed = subprocess.run(
        [
            sys.executable,
            "tools/run_phase1_release_gate.py",
            "--golden-results",
            str(results_path),
            "--credential-scan-root",
            str(tmp_path),
            "--skip-command-gates-for-test",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0
    report = json.loads(completed.stdout)
    assert report["passed"] is True
    assert any(result["name"] == "golden-task-suite" and result["passed"] for result in report["results"])
```

The `--skip-command-gates-for-test` flag must be hidden from README and used only to keep this integration test from recursively invoking the full release gate. It should build only callable gates (`golden-task-suite` and `one-key-credential-scan`). The test must pass `--credential-scan-root tmp_path` so the one-key gate does not depend on the developer's ambient `.env`, `.env.local`, `pyproject.toml`, or `reports/*` files.

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/golden/test_json_harness.py tests/unit/release/test_defaults.py::test_phase1_release_gate_script_accepts_golden_results_argument tests/integration/release/test_phase1_release_gate_cli.py -v
```

Expected: FAIL because `optimus.golden.json_harness` and CLI arguments do not exist.

- [ ] **Step 4: Implement JSON harness**

Create `src/optimus/golden/json_harness.py`:

```python
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from optimus.golden.tasks import GoldenTask, GoldenTaskResult


def load_golden_results(path: str | Path) -> dict[str, GoldenTaskResult]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"), parse_float=Decimal)
    results: dict[str, GoldenTaskResult] = {}
    for item in payload.get("results", ()):
        result = GoldenTaskResult(
            task_id=str(item["task_id"]),
            actual_mode=str(item["actual_mode"]),
            actual_tools=tuple(str(tool) for tool in item["actual_tools"]),
            actual_cost_usd=Decimal(str(item["actual_cost_usd"])),
            actual_final_state=str(item["actual_final_state"]),
            mutation_count=int(item["mutation_count"]),
            provider_keys_resolvable=tuple(str(key) for key in item.get("provider_keys_resolvable", ())),
        )
        results[result.task_id] = result
    return results


class JsonGoldenTaskHarness:
    def __init__(self, *, results: dict[str, GoldenTaskResult]) -> None:
        self._results = dict(results)

    @classmethod
    def from_path(cls, path: str | Path) -> JsonGoldenTaskHarness:
        return cls(results=load_golden_results(path))

    def run(self, task: GoldenTask) -> GoldenTaskResult:
        try:
            return self._results[task.task_id]
        except KeyError as exc:
            raise KeyError(f"missing golden result for {task.task_id}") from exc
```

Optionally export it in `src/optimus/golden/__init__.py`:

```python
from optimus.golden.json_harness import JsonGoldenTaskHarness, load_golden_results
```

- [ ] **Step 5: Wire release CLI arguments**

Replace `tools/run_phase1_release_gate.py` with:

```python
from __future__ import annotations

import argparse
from pathlib import Path

from optimus.golden.json_harness import JsonGoldenTaskHarness
from optimus.release.defaults import build_phase1_release_gates
from optimus.release.runner import ReleaseGateRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 1 Optimus release gate.")
    parser.add_argument("--golden-results", type=Path, help="Path to actual GoldenTaskResult JSON captured from a real Optimus-only run.")
    parser.add_argument("--python-executable", default="python", help="Python executable used for command gates.")
    parser.add_argument("--credential-scan-root", type=Path, default=Path("."), help="Root used for default release credential artifact scans.")
    parser.add_argument("--skip-command-gates-for-test", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    golden_harness = JsonGoldenTaskHarness.from_path(args.golden_results) if args.golden_results is not None else None
    gates = build_phase1_release_gates(
        python_executable=args.python_executable,
        golden_harness=golden_harness,
        include_command_gates=not args.skip_command_gates_for_test,
        credential_scan_root=args.credential_scan_root,
    )
    report = ReleaseGateRunner(gates=gates).run()
    print(report.to_json())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

Update `src/optimus/release/defaults.py` signature and command gate construction:

```python
def build_phase1_release_gates(
    *,
    python_executable: str = "python",
    golden_harness: GoldenTaskHarness | None = None,
    include_command_gates: bool = True,
    credential_scan_root: str | Path = ".",
) -> tuple[ReleaseGate, ...]:
    command_gates: tuple[ReleaseGate, ...] = ()
    if include_command_gates:
        command_gates = (
            CommandGate(
                name="unit-and-integration-tests",
                command=(python_executable, "-m", "pytest", "tests/unit", "tests/integration", "-q"),
            ),
            CommandGate(
                name="coverage-80",
                command=(
                    python_executable,
                    "-m",
                    "pytest",
                    "--cov=optimus",
                    "--cov-branch",
                    "--cov-report=term-missing",
                    "--cov-fail-under=80",
                    "-q",
                ),
            ),
            CommandGate(
                name="diff-whitespace-check",
                command=("git", "diff", "--check"),
            ),
        )
    return (
        *command_gates,
        CallableGate(name="golden-task-suite", run=lambda: _golden_task_suite_gate(golden_harness)),
        CallableGate(name="one-key-credential-scan", run=lambda: _one_key_credential_gate(credential_scan_root)),
    )
```

Do not add `command_timeout_seconds` in Task 5. Task 6 adds that argument together with the `CommandGate.timeout_seconds` field so Tasks 4 and 5 remain green when executed in order.

- [ ] **Step 6: Run harness and CLI tests**

Run:

```bash
pytest tests/unit/golden/test_json_harness.py tests/unit/golden/test_runner.py tests/unit/release/test_defaults.py tests/integration/release/test_phase1_release_gate_cli.py -v
```

Expected: PASS. Command timeouts are not part of Task 5; Task 6 adds them later.

- [ ] **Step 7: Update README golden evidence rule**

Replace the current fail-closed harness paragraph with:

````markdown
Golden tasks are executable through a JSON harness path. First capture actual
`GoldenTaskResult` records from an Optimus-only Plan-mode and Agent-mode run,
then run:

```bash
python tools/run_phase1_release_gate.py --golden-results reports/phase1-golden-results.json
```

When `--golden-results` is omitted, the `golden-task-suite` gate fails closed
with `golden task harness not configured`. A synthetic JSON file may be used to
test release-runner wiring, but Sprint 1 sign-off requires the JSON results to
come from a real Optimus Gateway-backed run with only `OPTIMUS_GATEWAY_URL` and
`OPTIMUS_API_KEY` present locally. If staging Gateway E2E is unavailable, record
that as "not run" in the release evidence instead of marking Sprint 1 complete.
````

- [ ] **Step 8: Local checkpoint**

```bash
git diff --check
```

Commit only if explicitly approved:

```bash
git add src/optimus/golden/json_harness.py src/optimus/golden/__init__.py tools/run_phase1_release_gate.py src/optimus/release/defaults.py tests/unit/golden/test_json_harness.py tests/unit/release/test_defaults.py tests/integration/release/test_phase1_release_gate_cli.py README.md
git commit -m "Wire golden task results into the release CLI."
```

---

## Task 6: Release-Gate Command Timeout

**Traceability:** PR #21 Review #4

**Files:**
- Modify: `src/optimus/release/runner.py`
- Modify: `src/optimus/release/defaults.py`
- Modify: `tools/run_phase1_release_gate.py`
- Modify: `tests/unit/release/test_runner.py`
- Modify: `tests/unit/release/test_defaults.py`

- [ ] **Step 1: Write failing timeout tests**

Append to `tests/unit/release/test_runner.py`:

```python
def test_command_gate_reports_timeout_as_failed_gate():
    def executor(command: tuple[str, ...], timeout_seconds: float | None) -> tuple[int, str, str]:
        raise TimeoutError(f"command timed out after {timeout_seconds} seconds")

    gate = CommandGate(
        name="slow-tests",
        command=("python", "-m", "pytest"),
        timeout_seconds=0.01,
        executor=executor,
    )

    result = gate.run()

    assert result.passed is False
    assert "timed out after 0.01 seconds" in result.output_summary


def test_release_runner_continues_after_command_timeout():
    def timeout_executor(command: tuple[str, ...], timeout_seconds: float | None) -> tuple[int, str, str]:
        raise TimeoutError("command timed out after 1.0 seconds")

    report = ReleaseGateRunner(
        gates=(
            CommandGate(name="slow", command=("slow",), timeout_seconds=1.0, executor=timeout_executor),
            CallableGate(name="after", run=lambda: (True, "ok")),
        )
    ).run()

    assert report.passed is False
    assert [(result.name, result.passed) for result in report.results] == [("slow", False), ("after", True)]
```

Append to `tests/unit/release/test_defaults.py`:

```python
def test_default_command_gates_receive_timeout():
    gates = build_phase1_release_gates(command_timeout_seconds=123.0)

    command_gates = [gate for gate in gates if getattr(gate, "command", None)]

    assert command_gates
    assert all(gate.timeout_seconds == 123.0 for gate in command_gates)


def test_phase1_release_gate_script_accepts_command_timeout_argument():
    text = Path("tools/run_phase1_release_gate.py").read_text(encoding="utf-8")

    assert "--command-timeout-seconds" in text
    assert "command_timeout_seconds=args.command_timeout_seconds" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/release/test_runner.py::test_command_gate_reports_timeout_as_failed_gate tests/unit/release/test_runner.py::test_release_runner_continues_after_command_timeout tests/unit/release/test_defaults.py::test_default_command_gates_receive_timeout tests/unit/release/test_defaults.py::test_phase1_release_gate_script_accepts_command_timeout_argument -v
```

Expected: FAIL because `CommandGate` has no `timeout_seconds`, injected executors accept only `command`, and the CLI does not yet expose `--command-timeout-seconds`.

- [ ] **Step 3: Add timeout-aware command execution**

In `src/optimus/release/runner.py`, update imports:

```python
from collections.abc import Callable
```

Update `CommandGate`:

```python
CommandExecutor = Callable[[tuple[str, ...], float | None], tuple[int, str, str]]


@dataclass(frozen=True)
class CommandGate:
    name: str
    command: tuple[str, ...]
    timeout_seconds: float | None = 600.0
    executor: CommandExecutor | None = None

    def run(self) -> ReleaseGateResult:
        started = datetime.now(tz=UTC)
        try:
            exit_code, stdout, stderr = (self.executor or _run_command)(self.command, self.timeout_seconds)
            output = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)
            passed = exit_code == 0
            summary = output or f"exit_code={exit_code}"
        except TimeoutError as exc:
            passed = False
            summary = str(exc)
        return ReleaseGateResult(
            name=self.name,
            passed=passed,
            output_summary=_safe_summary(summary),
            duration_ms=_duration_ms(started),
        )
```

Update `_run_command()`:

```python
def _run_command(command: tuple[str, ...], timeout_seconds: float | None) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"command {' '.join(command)} timed out after {timeout_seconds} seconds") from exc
    return completed.returncode, completed.stdout, completed.stderr
```

Update every existing injected executor to accept the new timeout argument. At minimum, update `test_command_gate_uses_injected_executor_and_redacts_output` in `tests/unit/release/test_runner.py`; also update any future injected executors added in `tests/unit/release/test_defaults.py` or integration release tests.

```python
def executor(command: tuple[str, ...], timeout_seconds: float | None) -> tuple[int, str, str]:
    commands.append(command)
    return (1, "OPENAI_API_KEY=sk-test", "")
```

Update `src/optimus/release/defaults.py` so Task 6, and only Task 6, wires timeouts into command gates:

```python
def build_phase1_release_gates(
    *,
    python_executable: str = "python",
    golden_harness: GoldenTaskHarness | None = None,
    include_command_gates: bool = True,
    credential_scan_root: str | Path = ".",
    command_timeout_seconds: float = 600.0,
) -> tuple[ReleaseGate, ...]:
    command_gates: tuple[ReleaseGate, ...] = ()
    if include_command_gates:
        command_gates = (
            CommandGate(
                name="unit-and-integration-tests",
                command=(python_executable, "-m", "pytest", "tests/unit", "tests/integration", "-q"),
                timeout_seconds=command_timeout_seconds,
            ),
            CommandGate(
                name="coverage-80",
                command=(
                    python_executable,
                    "-m",
                    "pytest",
                    "--cov=optimus",
                    "--cov-branch",
                    "--cov-report=term-missing",
                    "--cov-fail-under=80",
                    "-q",
                ),
                timeout_seconds=command_timeout_seconds,
            ),
            CommandGate(
                name="diff-whitespace-check",
                command=("git", "diff", "--check"),
                timeout_seconds=command_timeout_seconds,
            ),
        )
    return (
        *command_gates,
        CallableGate(name="golden-task-suite", run=lambda: _golden_task_suite_gate(golden_harness)),
        CallableGate(name="one-key-credential-scan", run=lambda: _one_key_credential_gate(credential_scan_root)),
    )
```

Update `tools/run_phase1_release_gate.py` to add the CLI timeout argument:

```python
    parser.add_argument("--command-timeout-seconds", type=float, default=600.0, help="Timeout for each subprocess-backed release gate.")
```

Pass it into the builder:

```python
        command_timeout_seconds=args.command_timeout_seconds,
```

- [ ] **Step 4: Run release runner tests**

Run:

```bash
pytest tests/unit/release/test_runner.py tests/unit/release/test_defaults.py tests/integration/release/test_phase1_release_gate_cli.py -v
```

Expected: PASS.

- [ ] **Step 5: Local checkpoint**

```bash
git diff --check
```

Commit only if explicitly approved:

```bash
git add src/optimus/release/runner.py src/optimus/release/defaults.py tools/run_phase1_release_gate.py tests/unit/release/test_runner.py tests/unit/release/test_defaults.py tests/integration/release/test_phase1_release_gate_cli.py
git commit -m "Bound release gate command execution."
```

---

## Task 7: Fitness-Gate Telemetry Cost Accuracy

**Traceability:** PR #21 Review #6, Plan 7 reconciliation dependency

**Files:**
- Modify: `src/optimus/retry/gated_run.py`
- Modify: `tests/unit/retry/test_gated_run.py`

- [ ] **Step 1: Write failing telemetry cost test**

Append to `tests/unit/retry/test_gated_run.py`:

```python
from decimal import Decimal
from optimus.telemetry.events import TelemetryEventKind


def test_fitness_gate_telemetry_uses_candidate_cost(tmp_path):
    events = []

    class PassingGate:
        name = "fitness"
        required = True

        def run(self) -> GateResult:
            return GateResult.pass_(name=self.name, summary="passed")

    runner = GatedRetryRunner(
        policy=RetryPolicy(max_retries=1, base_delay_ms=1, jitter_ms=(0,)),
        sleep_ms=lambda delay_ms: None,
        event_sink=events.append,
    )

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        checks_factory=lambda candidate, shadow_root: (PassingGate(),),
        plan_candidate=lambda attempt, prior_failures: "candidate",
        apply_candidate=lambda candidate, shadow_root: (shadow_root / "candidate.txt").write_text(candidate, encoding="utf-8"),
        candidate_cost_usd=lambda candidate: Decimal("0.019"),
    )

    assert result.succeeded is True
    fitness_events = [event for event in events if event.kind is TelemetryEventKind.FITNESS_GATE]
    assert fitness_events
    assert fitness_events[0].payload["cost_usd"] == Decimal("0.019")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/retry/test_gated_run.py::test_fitness_gate_telemetry_uses_candidate_cost -v
```

Expected: FAIL because `GatedRetryRunner.run()` has no required `candidate_cost_usd` argument and `_emit_fitness_gate()` hardcodes `Decimal("0")`.

- [ ] **Step 3: Thread explicit candidate cost into telemetry**

In `src/optimus/retry/gated_run.py`, update `GatedAttempt`:

```python
@dataclass(frozen=True)
class GatedAttempt(Generic[T]):
    attempt: int
    candidate: T
    gate_result: CompositeGateResult
    failure_summary: str | None
    cost_usd: Decimal = Decimal("0")
```

Update `GatedRetryRunner.run()` signature:

```python
        candidate_cost_usd: Callable[[T], Decimal],
```

After planning the candidate:

```python
            cost_usd = candidate_cost_usd(candidate)
```

Update fitness telemetry emission:

```python
            self._emit_fitness_gate(gate_result=gate_result, attempt=attempt, cost_usd=cost_usd)
```

Update both `GatedAttempt(...)` constructions to include `cost_usd=cost_usd`.

Update `_emit_fitness_gate()`:

```python
    def _emit_fitness_gate(self, *, gate_result: CompositeGateResult, attempt: int, cost_usd: Decimal) -> None:
        if self._event_sink is None:
            return
        self._event_sink(
            TelemetryEvent.fitness_gate(
                run_id=self._run_id,
                session_id=self._session_id,
                request_id=f"attempt-{attempt}",
                occurred_at=datetime.now(tz=UTC),
                passed=gate_result.passed,
                required_gate_names=gate_result.required_gate_names,
                failed_gate_names=gate_result.failed_gate_names,
                duration_ms=gate_result.duration_ms,
                cost_usd=cost_usd,
            )
        )
```

Update the existing `GatedRetryRunner.run()` call sites in `tests/unit/retry/test_gated_run.py` to pass `candidate_cost_usd=lambda candidate: Decimal("0")` where those tests do not model gateway usage. At the time of this plan, the real call sites are the two tests in `tests/unit/retry/test_gated_run.py`; `tests/integration/retry/test_gateway_retry_flow.py` uses `RetryController`, not `GatedRetryRunner`. Any future production or integration path that has gateway-normalized usage must pass the real `Decimal` from gateway usage or usage ledger records; do not estimate tokens or cost post-hoc. Making the hook required prevents new real callers from silently inheriting the old placeholder.

- [ ] **Step 4: Run retry and telemetry tests**

Run:

```bash
pytest tests/unit/retry/test_gated_run.py tests/unit/telemetry/test_events.py tests/integration/telemetry/test_usage_telemetry_flow.py -v
```

Expected: PASS.

- [ ] **Step 5: Local checkpoint**

```bash
git diff --check
```

Commit only if explicitly approved:

```bash
git add src/optimus/retry/gated_run.py tests/unit/retry/test_gated_run.py
git commit -m "Report candidate cost in fitness telemetry."
```

---

## Task 8 Optional: Shared Composite Gate Exception Module

**Traceability:** PR #21 Review #7, lower priority cosmetic cleanup

**Files:**
- Create: `src/optimus/gates/exceptions.py`
- Modify: `src/optimus/gates/fitness.py`
- Modify: `src/optimus/retry/policy.py`
- Verify: retry and gates tests

Run this task only if the reviewer approves the optional cleanup. It is not required to close Plan 8.5 release correctness. The current code does not have an actual `retry` to `gates` import cycle because `retry/gated_run.py` already imports gate modules at top level; this task simply removes an unnecessary deferred import and gives the shared exception a clearer home.

- [ ] **Step 1: Move `CompositeGateError` to a low-level module**

Create `src/optimus/gates/exceptions.py`:

```python
from __future__ import annotations

from typing import Protocol


class CompositeGateResultLike(Protocol):
    @property
    def failed_gate_names(self) -> tuple[str, ...]:
        raise NotImplementedError


class CompositeGateError(Exception):
    def __init__(self, result: CompositeGateResultLike) -> None:
        self.result = result
        names = ", ".join(result.failed_gate_names)
        super().__init__(f"required fitness gates failed: {names}")
```

In `src/optimus/gates/fitness.py`, import and remove the local duplicate:

```python
from optimus.gates.exceptions import CompositeGateError
```

In `src/optimus/retry/policy.py`, replace any deferred in-function import with:

```python
from optimus.gates.exceptions import CompositeGateError
```

- [ ] **Step 2: Run tests**

Run:

```bash
pytest tests/unit/retry tests/unit/gates tests/integration/retry tests/integration/gates -v
```

Expected: PASS.

- [ ] **Step 3: Local checkpoint**

```bash
git diff --check
```

Commit only if explicitly approved:

```bash
git add src/optimus/gates/exceptions.py src/optimus/gates/fitness.py src/optimus/retry/policy.py
git commit -m "Move composite gate errors to shared module."
```

---

## Task 9: README and Release Evidence Notes

**Traceability:** Plan 8.5 operator handoff and Sprint 1 sign-off clarity

**Files:**
- Modify: `README.md`
- Verify: `tools/run_phase1_release_gate.py`

- [ ] **Step 1: Update Plan 8 README section**

In `README.md`, revise the Plan 8 release-gate paragraphs so they state:

````markdown
Plan 8.5 hardens the release runner. Shadow promotion now carries both writes
and deletions, rolls back partial promotion failures, and skips common large
local directories such as `.venv`, `node_modules`, build outputs, and caches.
Release command gates have a per-command timeout; timeout is reported as a
failed gate and the runner continues to collect the remaining gate results.

Golden tasks are wired through actual result JSON:

```bash
python tools/run_phase1_release_gate.py --golden-results reports/phase1-golden-results.json
```

When `--golden-results` is omitted, `golden-task-suite` fails closed. A
synthetic result file may be used for CLI wiring tests only. Sprint 1 sign-off
requires result JSON captured from a real Optimus-only Plan-mode and Agent-mode
run, or the release evidence must state that staging Gateway E2E was not run.
````

- [ ] **Step 2: Run markdown-adjacent smoke checks**

Run:

```bash
pytest tests/unit/release/test_defaults.py::test_phase1_release_gate_script_exists_and_uses_default_builder tests/unit/release/test_defaults.py::test_phase1_release_gate_script_accepts_golden_results_argument -v
```

Expected: PASS.

- [ ] **Step 3: Local checkpoint**

```bash
git diff --check
```

Commit only if explicitly approved:

```bash
git add README.md tools/run_phase1_release_gate.py tests/unit/release/test_defaults.py
git commit -m "Document hardened release gate evidence."
```

---

## Task 10: Focused Verification and Sign-Off

**Files:**
- Verify: `src/optimus/gates`
- Verify: `src/optimus/golden`
- Verify: `src/optimus/release`
- Verify: `src/optimus/retry/gated_run.py`
- Verify: `tools/run_phase1_release_gate.py`

- [ ] **Step 1: Run focused Plan 8 and 8.5 tests**

Run:

```bash
pytest tests/unit/retry tests/unit/gates tests/unit/golden tests/unit/release tests/integration/retry tests/integration/gates tests/integration/release -v
```

Expected: PASS.

- [ ] **Step 2: Run telemetry regression**

Run:

```bash
pytest tests/unit/telemetry tests/integration/telemetry -v
```

Expected: PASS.

- [ ] **Step 3: Run Plan 8 module coverage gate**

Run:

```bash
pytest tests/unit/retry tests/unit/gates tests/unit/golden tests/unit/release tests/integration/retry tests/integration/gates tests/integration/release --cov=optimus.retry --cov=optimus.gates --cov=optimus.golden --cov=optimus.release --cov=optimus.telemetry --cov-branch --cov-report=term-missing --cov-fail-under=80
```

Expected: PASS with coverage >= 80 for the affected production packages.

- [ ] **Step 4: Run default fail-closed CLI**

Run with provider keys cleared and only Optimus credentials present:

```bash
python tools/run_phase1_release_gate.py
```

Expected: exit code 1, JSON output, `golden-task-suite` failed with `golden task harness not configured`, command gates either pass or report their real failures, and no provider secret value appears in output.

- [ ] **Step 5: Run CLI with golden result JSON**

Use actual Optimus-only result JSON when available:

```bash
python tools/run_phase1_release_gate.py --golden-results reports/phase1-golden-results.json
```

Expected: PASS only when unit/integration, coverage, diff, golden task, and one-key gates all pass. If `reports/phase1-golden-results.json` is synthetic, mark the run as CLI wiring evidence only, not Sprint 1 staging evidence.

- [ ] **Step 6: Run full package gate if the environment has all dev dependencies**

Run:

```bash
pytest --cov=optimus --cov-branch --cov-report=term-missing -v
```

Expected: PASS with aggregate Python production-code coverage >= 80. If the local environment lacks a dependency such as `confusable_homoglyphs`, report the exact import error and the narrower passing gates instead of claiming full-suite success.

- [ ] **Step 7: Check diff hygiene**

Run:

```bash
git status --short
git diff --check
```

Expected: only intentional Plan 8.5 files are modified or added. Pre-existing `.idea`, `.claude`, `.cursor`, or other unrelated noise remains unstaged and untouched.

- [ ] **Step 8: Commit**

Only if explicitly approved:

```bash
git add src/optimus/gates src/optimus/golden src/optimus/release src/optimus/retry/gated_run.py tests/unit/gates tests/unit/golden tests/unit/release tests/unit/retry tests/integration/release tools/run_phase1_release_gate.py README.md
git commit -m "Harden Phase 1 release gate wiring."
```

## Deferred Decisions and Follow-Ups

- **Staging Gateway E2E evidence:** This plan wires the release gate so actual golden results can be supplied through `--golden-results`. It does not build the full staging runner that produces those results. Sprint 1 sign-off must include actual Optimus-only result JSON or explicitly state that staging Gateway E2E was not run.
- **Shadow reuse across retries:** This plan chooses broader/configurable ignore patterns instead of reusing a shadow workspace across retry attempts. Reuse can be revisited only after semantics are defined for restoring a clean shadow baseline between candidates.
- **Optional exception import cleanup:** Task 8 may be skipped if the reviewer wants Plan 8.5 limited to release correctness.

## Self-Review

- Spec coverage: P8-FU-1 is covered by Tasks 1 and 3; P8-FU-2 by Task 2; P8-FU-3 by Task 3; one-key scan wiring by Task 4; golden-harness CLI wiring by Task 5; command timeout by Task 6; telemetry cost accuracy by Task 7; optional exception import cleanup by Task 8.
- No provider-key regression: all release and golden wiring keeps local credentials limited to `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`.
- No false release evidence: JSON harness wiring makes the CLI executable, but the plan explicitly distinguishes synthetic wiring tests from real Sprint 1 staging evidence.
- Fail-closed behavior: ignored workspace paths cannot be inferred as deletions, missing golden results, missing task results, command timeouts, provider key hits, and gate failures all produce failed gate results.
- Cost correctness: `GatedRetryRunner.run()` requires callers to provide a candidate-cost function, so future production callers must either pass gateway-normalized cost or make an explicit zero-cost test decision at the call site.
- TDD compliance: every production change starts with a failing unit or integration test and exact commands to prove red/green progress.
- Placeholder scan: this plan avoids unresolved placeholders and names exact files, functions, tests, and commands. Optional scope is limited to Task 8 and is not required for release correctness.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-06-plan-8-5-release-gate-hardening.md`.

Plan 8.5 should be implemented by Cursor after Plan 8 is accepted or merged to `main`. Use `superpowers:subagent-driven-development` if available, or `superpowers:executing-plans` for inline execution. Branch from latest `main` with the repo convention, for example `agent/cursor/plan-8-5-release-gate-hardening`, and keep implementation commits limited to the files named in this plan unless review feedback expands scope.
