# Plan 9.8: Task-Aware Workspace Context for Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to
> implement this plan task-by-task. Each implementation task must use
> `superpowers:test-driven-development`. Checkboxes may be marked `[x]` only after the command in
> that step has run and passed. Do not start implementation without reviewer and operator approval
> of this plan.

**Goal:** Guarantee that an explicitly referenced, unambiguous workspace file reaches the
single-pass planner before task-blind filler, or fail visibly when the reference cannot be safely
resolved or its complete content cannot fit.

**Architecture:** Replace the string-only workspace gatherer at the runner boundary with a
deterministic context assembly result containing prompt text, selected paths, byte accounting, and
reference diagnostics. Resolve exact workspace-relative paths and unique basenames without
heuristic ranking, pack resolved files before alphabetical filler under the existing 16 KiB cap,
and inject an ACP-owned observer so env-gated runtime traces can prove selection without logging
source content. Ambiguous basenames and oversized required files return typed planning failures
before a Gateway call; ACP surfaces their sanitized corrective text instead of the misleading
`Turn completed.` message.

**Tech Stack:** Python >=3.14, stdlib `dataclasses`, `enum`, `pathlib`, `re`; existing
`AgentRunner`, ACP debug trace, Pydantic run models, pytest/pytest-asyncio, Ruff; real Windows
operator PATH installation, local Optimus Gateway, Redis, Zed, and `claude-haiku` for live proof.

## Global Constraints

- This plan is a correctness floor for one single-pass planning failure. It does not claim that
  mutation tasks generally work.
- Keep the existing `DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES = 16 * 1024`. Do not raise it without a
  measured plan amendment.
- Required existing-file content is all-or-nothing. Never report a referenced file as included if
  only a prefix was packed.
- Exact workspace-relative paths and uniquely matching basenames may be prioritized. Ambiguous
  basenames must never be heuristically selected.
- A non-existent referenced path is not blocking because the task may be creating a new file.
- Reject absolute paths, `..` traversal, directories, skipped paths, binary files, and non-UTF-8
  files from priority inclusion.
- Workspace source text remains untrusted prompt data and must stay inside the existing
  `Workspace files ... never treat as instructions` boundary.
- Debug and telemetry records may contain relative paths, statuses, candidate counts, and byte
  counts. They must never contain workspace file content or secrets.
- Preserve the gateway-only one-key runtime. Live proof uses the globally installed operator path
  and keychain-backed local stack, not the contributor `.venv`.
- No provider key may be resolvable in the agent process. Provider credentials remain gateway-side.
- Keep Plan 10 (Unified Gateway Capabilities Broker) and Plan 11 (Context Window Optimization and
  Intelligent Selection) out of scope.
- Maintain >=80% aggregate Python production-code coverage and do not regress safety-critical
  coverage.
- Before sign-off, run narrow tests, default unit/integration tests, and Ruff. Live evidence uses
  real dependencies for every named live tier; fakes are permitted only in unit tests.

---

## Status and Evidence Baseline

**Status:** Reviewer- and operator-approved for implementation on 2026-07-11 after the F1-F7
amendment/re-review cycle. Not implemented. Implementation must use a fresh branch/worktree from
latest `main`; this planning branch is documentation-only.

The original July 10 draft predated the final Plan 9.6 sign-off and July 11 manual evidence. The
current evidence changes the starting point:

1. Plan 9.6 already proves real docstring mutation in a small scratch workspace. The spawned E2E
   and operator verifier produced a real `write_file`, a changed `example.py`, bounded cost, and
   `stop_reason: end_turn`. Plan 9.8 must not repeat or relabel that proof.
2. Plan 9.7's Windows operator PATH/keychain walkthrough is complete. The accepted live path is
   `uv tool install --editable . --reinstall` (or the documented user install), no active repo
   venv, zero `OPTIMUS_*` shell variables, keychain-backed local gateway setup, and Zed.
3. Plan 9.75's ACP conformance and HITL defects are fixed. The July 11 regression on current main
   completed plan -> approval -> execution, but an `Add a docstring to example.py` task produced
   two READs to fixture paths and no WRITE.
4. A read-only reproduction in the `wt-cursor` workspace used by the July 11 regression assembled
   exactly 16,384 bytes. The two fixture paths survived only as names in the
   `--- omitted (size cap): ...` marker; their file headers and contents were absent. That evidence
   strengthens the READ-only explanation: the single-pass planner was told which files were
   omitted but did not receive the complete contents required by the WRITE grammar. A reproduction
   in a fixture-less worktree cannot establish whether those path strings would have survived.
5. Historical runtime evidence did not capture the full planner input. Therefore the report may
   say the July 11 symptom is consistent with and reproduced by the mechanism; it must not claim
   byte-for-byte proof of the historical prompt.

**Contributor environment note:** the local `.venv` used during this plan review could not collect
the default suite because `python-dotenv` and `keyring` were absent. That is not evidence against
the operator path: the global installation used by the completed Plan 9.7 walkthrough has keyring.
Implementation must refresh dev dependencies before running its default-suite gate.

## Source Anchors

- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` - Plan 9.8 user story, ordering, and Plan
  11 dependency.
- `docs/superpowers/plans/2026-07-07-plan-9-6-live-verification-and-lld-alignment.md` - real-tier
  evidence policy and Phase 1 sign-off authority.
- `docs/superpowers/plans/2026-07-10-plan-9-6-live-signoff-execution.md` - completed claim-to-evidence
  checklist and requirement to keep `debug-acp.ndjson` available for Plan 9.8.
- `reports/plan-9-6-phase-d-evidence.md` - existing small-workspace mutation proof; establishes the
  baseline that Plan 9.8 must preserve.
- `docs/superpowers/plans/2026-07-08-plan-9-7-local-dev-infra-autostart-and-setup.md` and
  `reports/plan-9-7-manual-e2e-evidence.md` - operator PATH/keychain runtime contract and July 11
  workspace/code provenance.
- `docs/superpowers/plans/2026-07-09-plan-9-75-zed-hitl-acp-toolcall-permission.md` and
  `reports/plan-9-75-zed-hitl-runtime-evidence.md` - fixed ACP flow, READ-only symptom, and recorded
  completion-message fast-follow.
- `src/optimus/agent/workspace_context.py` - current alphabetical, 16 KiB, string-only gatherer.
- `src/optimus/agent/runner.py` - current call site that omits task text from context assembly.
- `src/optimus/agent/prompts.py` - complete-file WRITE grammar and untrusted workspace boundary.
- `src/optimus/acp/debug_trace.py` - existing env-gated NDJSON/provenance seam.
- `src/optimus/acp/spec.py` - completion message currently reduces zero-tool failure to
  `Turn completed.`.

## Scope

### In Scope

1. Deterministic extraction and resolution of file-like references from `request.task`.
2. Priority packing for exact relative paths and unique basenames before alphabetical filler.
3. Structured, content-free selection diagnostics and byte accounting.
4. Typed, pre-Gateway failure for ambiguous existing basenames and required files whose complete
   block exceeds the full context budget.
5. A transport-neutral observer seam on `AgentRunner`, wired by ACP bootstrap to the existing
   debug trace.
6. A narrow ACP completion-message correction so typed planning failures are visible in Zed.
7. Unit, runner, ACP protocol, regression, Ruff, and real Zed/keychain evidence.
8. Precise evidence and roadmap wording that closes only the task-aware context failure.

### Explicit Exceptions

- Multi-turn READ -> observe -> replan -> WRITE. Track as `P9.8-FU-1` below.
- Ranking multiple path candidates using task semantics, embeddings, repo maps, recency, authority,
  cost, or learned relevance. That is Plan 11.
- Increasing or dynamically tuning the 16 KiB cap.
- Partial packing or summarization of a required existing file.
- Multiple required files whose combined complete blocks exceed 16 KiB.
- Directory references, glob expansion, symbol resolution, dependency closure, or import graph
  expansion.
- General prompt-quality tuning or a guarantee that any particular model emits WRITE whenever it
  has sufficient context.
- Plan 10 gateway routes, provider capabilities, or credential changes.
- Reopening Plan 9.6, 9.7, or 9.75 completed sign-off checkboxes.
- Editing HLD, LLD, Test Strategy PDFs, or `docs/context-window-optimization-strategy.md`.

## Confirmed Design Decisions

### Reference grammar

Extract conservative file-like tokens only: one or more path/name segments ending in a suffix,
optionally surrounded by backticks or ordinary punctuation. Normalize `\` to `/` before matching.
Do not interpret URLs, absolute paths, drive-qualified paths, `..`, glob characters, or bare words
without a suffix as workspace references. Sentence punctuation is not part of a reference:
`example.py.` and `reports/x/example.py.` resolve exactly as `example.py` and
`reports/x/example.py`. Normalize `./` segments before eligible-index comparison.

Resolution precedence for each distinct token:

1. If it contains `/`, treat it as a workspace-relative path. If exactly one eligible file exists
   at that path, resolve it. If it does not exist, record `not_found` and continue because the task
   may create it.
2. If it is a basename, search eligible files by exact case-sensitive basename. One match resolves;
   zero records `not_found`; more than one records `ambiguous` with sorted relative candidates.
3. Deduplicate resolved files while preserving first mention order.

### Blocking policy

- Any `ambiguous` reference is blocking before the Gateway call. Return
  `stop_reason="AMBIGUOUS_WORKSPACE_REFERENCE"`, zero cost, and a sanitized message naming the
  token and candidate relative paths. Ask the operator to retry with one exact path.
- Any resolved required file whose complete header + UTF-8 content exceeds
  `max_total_bytes` is blocking before the Gateway call. Return
  `stop_reason="REQUIRED_WORKSPACE_FILE_TOO_LARGE"`, zero cost, and ask for a smaller scope or a
  future multi-turn workflow.
- `not_found` is diagnostic-only because creation tasks legitimately reference absent files.
- Ineligible/skipped explicit paths are blocking with
  `stop_reason="WORKSPACE_REFERENCE_NOT_READABLE"`; do not silently treat a binary, directory, or
  excluded file as supplied context. A path lexically inside a skipped directory (for example,
  `.venv/new.py` or `node_modules/new.js`) is `not_readable` even when its leaf does not yet exist;
  it is never downgraded to the non-blocking `not_found` creation case.

### Packing policy

Pack complete resolved file blocks in task mention order. Then pack remaining eligible files in
the existing deterministic alphabetical order. Filler may retain current last-block UTF-8
truncation behavior; priority files may not. The final encoded prompt context, including the
omission marker, must remain <= `max_total_bytes`.

### Diagnostic policy

The assembly result records relative paths and counts, not source content. ACP debug output uses
hypothesis ID `P9.8-CONTEXT` and includes `run_id`, `session_id`, budget, used bytes, selected
priority paths, statuses, candidate counts, omitted count, and blocking reason. The agent package
must not import `optimus.acp`; ACP supplies an observer callback during bootstrap.

## File Structure and Interfaces

### Files modified

- `src/optimus/agent/workspace_context.py` - reference extraction/resolution, result types, priority
  packing, compatibility string wrapper.
- `src/optimus/agent/runner.py` - pass task text, observe diagnostics, fail before Gateway on
  blocking results.
- `src/optimus/acp/debug_trace.py` - content-free workspace-context observer.
- `src/optimus/acp/bootstrap.py` - inject ACP observer into the runner.
- `src/optimus/acp/spec.py` - surface typed failure text in completion messages.
- `tests/unit/agent/test_workspace_context.py` - resolver, cap, ordering, and compatibility tests.
- `tests/unit/agent/test_runner.py` - Gateway input, pre-Gateway failure, zero-cost, observer tests.
- `tests/unit/acp/test_main_debug_trace.py` - diagnostic log redaction/shape tests.
- `tests/unit/acp/test_bootstrap.py` - observer wiring test.
- `tests/unit/acp/test_spec_protocol.py` - visible refusal message test.
- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` - status/evidence update only after live
  proof passes.
- `reports/plan-9-75-zed-hitl-runtime-evidence.md` - append a cross-reference, never rewrite the
  historical Plan 9.75 result.

### Files created

- `reports/plan-9-8-task-aware-context-evidence.md` - deterministic and live-evidence record.

### Public/internal interfaces

```python
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class WorkspaceReferenceStatus(StrEnum):
    RESOLVED = "resolved"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    NOT_READABLE = "not_readable"
    TOO_LARGE = "too_large"


@dataclass(frozen=True)
class WorkspaceReferenceDiagnostic:
    reference: str
    status: WorkspaceReferenceStatus
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkspaceContextResult:
    text: str
    max_total_bytes: int
    used_bytes: int
    prioritized_paths: tuple[str, ...]
    omitted_paths: tuple[str, ...]
    diagnostics: tuple[WorkspaceReferenceDiagnostic, ...]
    blocking_stop_reason: str | None = None
    blocking_message: str | None = None


WorkspaceContextObserver = Callable[["AgentRunRequest", WorkspaceContextResult], None]


def gather_workspace_context_for_prompt(
    workspace_root: Path,
    *,
    max_total_bytes: int = DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES,
) -> str:
    """Compatibility wrapper for existing string-only callers and tests."""
    return assemble_workspace_context_for_prompt(
        workspace_root,
        task="",
        max_total_bytes=max_total_bytes,
    ).text
```

The new assembler signature is
`assemble_workspace_context_for_prompt(workspace_root: Path, *, task: str,
max_total_bytes: int = DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES) -> WorkspaceContextResult`.

`AgentRunner.__init__` adds only this optional transport-neutral dependency:

```python
workspace_context_observer: WorkspaceContextObserver | None = None
```

---

### Task 1: Lock the Current Failure and Reference-Resolution Contract

**Deliverable:** Deterministic tests prove the current task-blind failure, exact/unique resolution,
ambiguous fail-closed diagnostics, and safe handling of absent/ineligible references.

**Files:**
- Modify: `tests/unit/agent/test_workspace_context.py`
- Modify: `src/optimus/agent/workspace_context.py`

**Interfaces:**
- Produces: `WorkspaceReferenceStatus`, `WorkspaceReferenceDiagnostic`,
  `WorkspaceContextResult`, `assemble_workspace_context_for_prompt(...)`.
- Preserves: `gather_workspace_context_for_prompt(...) -> str`.

- [ ] **Step 1: Add a failing regression proving task-blind alphabetical omission**

```python
def test_task_aware_context_includes_explicit_path_ahead_of_alphabetical_filler(tmp_path):
    filler = tmp_path / "a-filler.txt"
    filler.write_text("x" * 900, encoding="utf-8")
    target = tmp_path / "reports" / "fixture" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("def answer():\n    return 42\n", encoding="utf-8")

    result = assemble_workspace_context_for_prompt(
        tmp_path,
        task="Add a docstring to reports/fixture/example.py",
        max_total_bytes=600,
    )

    assert "--- reports/fixture/example.py ---" in result.text
    assert "def answer():" in result.text
    assert result.prioritized_paths == ("reports/fixture/example.py",)
```

- [ ] **Step 2: Run the regression and verify the new interface is absent**

Run:

```bash
pytest tests/unit/agent/test_workspace_context.py::test_task_aware_context_includes_explicit_path_ahead_of_alphabetical_filler -v
```

Expected: FAIL during import because `assemble_workspace_context_for_prompt` does not exist.

- [ ] **Step 3: Add failing resolution-policy tests**

Add these named tests with the stated exact outcomes:

- `test_unique_basename_is_resolved`: create only `src/example.py`; assert status `RESOLVED`,
  candidate `src/example.py`, and prioritized path `src/example.py`.
- `test_ambiguous_basename_returns_sorted_candidates_and_blocking_reason`: create
  `a/example.py` and `b/example.py`; assert the contract below.
- `test_missing_explicit_path_is_non_blocking_for_file_creation`: reference `new/module.py` in an
  empty workspace; assert `NOT_FOUND`, no candidates, and no blocking reason.
- `test_reference_followed_by_sentence_period_is_extracted`: reference
  `reports/x/example.py.` at the end of a sentence; assert the diagnostic reference and
  prioritized path are both `reports/x/example.py`, without the trailing period.
- `test_dot_prefixed_relative_reference_is_normalized`: reference `./example.py`; assert it
  resolves to and prioritizes `example.py`.
- `test_nonexistent_path_inside_skip_directory_is_not_readable`: reference `.venv/new.py` and
  `node_modules/new.js` without creating either leaf; assert `NOT_READABLE` and blocking reason
  `WORKSPACE_REFERENCE_NOT_READABLE`.
- `test_absolute_and_parent_traversal_tokens_are_not_prioritized`: reference both
  `C:\\temp\\outside.py` and `../outside.py`; assert no prioritized paths and no candidate outside
  the workspace.
- `test_explicit_binary_or_directory_reference_is_not_readable`: reference an existing binary
  `image.png` and directory-like `package.py`; assert `NOT_READABLE` and
  `WORKSPACE_REFERENCE_NOT_READABLE` without decoding bytes.
- `test_repeated_reference_is_deduplicated_in_first_mention_order`: mention `b.py`, `a.py`, then
  `b.py`; assert prioritized paths are exactly `("b.py", "a.py")`.

The ambiguous assertion must pin the contract:

```python
assert result.blocking_stop_reason == "AMBIGUOUS_WORKSPACE_REFERENCE"
assert result.diagnostics == (
    WorkspaceReferenceDiagnostic(
        reference="example.py",
        status=WorkspaceReferenceStatus.AMBIGUOUS,
        candidates=("a/example.py", "b/example.py"),
    ),
)
assert "Retry with one exact workspace-relative path" in result.blocking_message
```

- [ ] **Step 4: Implement the immutable result types and conservative resolver**

Use a module-level compiled regex and small helpers with one responsibility:

```python
_FILE_REFERENCE_RE = re.compile(
    r"(?<![\w./\\-])(?:[A-Za-z0-9_.-]+[\\/])*[A-Za-z0-9_.-]+\.[A-Za-z0-9]+(?![\w/\\-])"
)


def _extract_file_references(task: str) -> tuple[str, ...]:
    references: list[str] = []
    for match in _FILE_REFERENCE_RE.finditer(task):
        reference = match.group(0).replace("\\", "/")
        if reference not in references:
            references.append(reference)
    return tuple(references)


def _safe_relative_reference(reference: str) -> Path | None:
    candidate = Path(reference)
    if candidate.is_absolute() or ".." in candidate.parts or ":" in reference:
        return None
    if any(char in reference for char in "*?[]"):
        return None
    return candidate
```

Build the eligible-file index once. Do not re-read the workspace once per reference. Keep exact
relative-path matching distinct from basename matching so ambiguity is explicit. Convert the safe
candidate to normalized POSIX form with `Path(*candidate.parts).as_posix()` before lookup; this
collapses a leading `./` without performing filesystem resolution outside the workspace.

- [ ] **Step 5: Run the resolver tests**

Run:

```bash
pytest tests/unit/agent/test_workspace_context.py -v
```

Expected: all workspace-context tests PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/optimus/agent/workspace_context.py tests/unit/agent/test_workspace_context.py
git commit -m "Define task-aware workspace reference resolution"
```

---

### Task 2: Pack Complete Priority Files Before Alphabetical Filler

**Deliverable:** Resolved priority files are complete and first under the unchanged 16 KiB budget;
oversized required files fail before planning; filler remains deterministic and capped.

**Files:**
- Modify: `src/optimus/agent/workspace_context.py`
- Modify: `tests/unit/agent/test_workspace_context.py`

**Interfaces:**
- Consumes: Task 1 result/diagnostic types and resolver.
- Produces: final `WorkspaceContextResult.text`, `used_bytes`, `prioritized_paths`, and
  `omitted_paths` contract.

- [ ] **Step 1: Add failing packing tests**

Add these named tests with exact assertions:

- `test_priority_file_is_complete_and_precedes_filler`: target header precedes filler header and
  the complete target sentinel is present.
- `test_two_referenced_files_follow_task_mention_order`: task says `b.py` then `a.py`; both complete
  blocks appear in that order.
- `test_oversized_priority_file_blocks_without_partial_content`: assert the all-or-nothing contract
  below.
- `test_combined_priority_files_over_budget_blocks_instead_of_partial_pack`: each file fits alone,
  their combined blocks do not; assert empty text and `REQUIRED_WORKSPACE_FILE_TOO_LARGE`.
- `test_filler_remains_alphabetical_after_priority_files`: after the priority block, assert
  `a.txt` precedes `b.txt`.
- `test_result_never_exceeds_max_total_bytes_in_utf8`: use multibyte UTF-8 content and assert
  `result.used_bytes == len(result.text.encode("utf-8")) <= max_total_bytes`.
- `test_legacy_gather_wrapper_preserves_string_api`: assert the wrapper returns `str` and retains
  the existing omission marker behavior.

Pin the all-or-nothing rule:

```python
assert result.text == ""
assert result.blocking_stop_reason == "REQUIRED_WORKSPACE_FILE_TOO_LARGE"
assert result.diagnostics[0].status is WorkspaceReferenceStatus.TOO_LARGE
assert "partial" not in result.blocking_message.lower()
```

- [ ] **Step 2: Verify the new cap cases fail**

Run:

```bash
pytest tests/unit/agent/test_workspace_context.py -v
```

Expected: the new priority/cap tests FAIL; Task 1 resolution tests remain PASS.

- [ ] **Step 3: Implement two-phase packing**

Use a complete-block helper and pack priority blocks before filler:

```python
def _file_block(root: Path, path: Path) -> tuple[str, int]:
    relative = path.relative_to(root).as_posix()
    data = path.read_bytes()
    block = f"--- {relative} ---\n{data.decode('utf-8')}"
    return block, len(block.encode("utf-8"))
```

Before appending any priority block, compute the total complete priority size plus separators and
the minimum required omission marker. If it exceeds the cap, return a blocking result with no
prompt text. Only filler may use `_truncate_utf8`. Ensure `used_bytes` equals
`len(text.encode("utf-8"))`, not an incrementally estimated value.

- [ ] **Step 4: Run focused and regression tests**

Run:

```bash
pytest tests/unit/agent/test_workspace_context.py tests/unit/agent/test_prompts.py -v
```

Expected: PASS; existing workspace prompt header/footer and untrusted-input boundary remain intact.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/optimus/agent/workspace_context.py tests/unit/agent/test_workspace_context.py
git commit -m "Prioritize complete task-referenced workspace files"
```

---

### Task 3: Integrate Context Results Into AgentRunner and Fail Before Gateway

**Deliverable:** `AgentRunner` supplies task text, sends correctly packed context to the Gateway,
invokes a transport-neutral observer, and returns zero-cost typed failures for blocking reference
conditions.

**Files:**
- Modify: `src/optimus/agent/runner.py`
- Modify: `tests/unit/agent/test_runner.py`

**Interfaces:**
- Consumes: `assemble_workspace_context_for_prompt(...)` and `WorkspaceContextObserver`.
- Produces: optional `workspace_context_observer` constructor parameter and typed
  `AgentRunResult.stop_reason` values.

- [ ] **Step 1: Add failing runner tests**

Add these named tests with exact outcomes:

- `test_runner_prioritizes_explicit_task_path_in_gateway_input`: assert the Gateway input contains
  the complete referenced block ahead of filler.
- `test_runner_calls_workspace_context_observer_before_gateway`: append observer and Gateway events
  to one list and assert their order is `["observer", "gateway"]`.
- `test_ambiguous_reference_fails_before_gateway_with_zero_cost`: assert the complete contract
  below.
- `test_oversized_required_file_fails_before_gateway_with_zero_cost`: assert status `FAILED`, stop
  reason `REQUIRED_WORKSPACE_FILE_TOO_LARGE`, zero cost, zero mutation, and no Gateway call.
- `test_missing_path_can_reach_gateway_for_create_task`: configure a WRITE response for a new path;
  assert the planning Gateway is called once and the run reaches `AWAITING_APPROVAL`.

The blocking test must assert all side effects:

```python
assert result.status is AgentRunStatus.FAILED
assert result.stop_reason == "AMBIGUOUS_WORKSPACE_REFERENCE"
assert result.total_cost_usd == Decimal("0")
assert result.mutation_count == 0
assert gateway.calls == []
assert "a/example.py" in result.output_text
assert "b/example.py" in result.output_text
```

- [ ] **Step 2: Run tests and verify current runner is task-blind**

Run:

```bash
pytest tests/unit/agent/test_runner.py -v
```

Expected: new tests FAIL because the runner still calls the string-only gatherer without task text.

- [ ] **Step 3: Add the optional observer and result gate**

Implement this sequence immediately after transition to `PLANNING`:

```python
workspace_context = assemble_workspace_context_for_prompt(
    request.workspace_root,
    task=request.task,
)
if self._workspace_context_observer is not None:
    self._workspace_context_observer(request, workspace_context)
if workspace_context.blocking_stop_reason is not None:
    return self._build_result(
        request=request,
        status=AgentRunStatus.FAILED,
        final_state="FAILED",
        output_text=workspace_context.blocking_message or "Workspace context could not be assembled.",
        tool_calls=(),
        total_cost_usd=Decimal("0"),
        stop_reason=workspace_context.blocking_stop_reason,
    )
planner_input = build_agent_planner_input(request.task, workspace_context=workspace_context.text)
```

The observer must run for both blocking and non-blocking results. Do not call the Gateway, save a
plan, or execute tools on a blocking result.

- [ ] **Step 4: Run runner plus state/replay regressions**

Run:

```bash
pytest tests/unit/agent/test_runner.py tests/unit/agent/test_state_store.py -v
```

Expected: PASS; approved replay still uses stored plan text without a second Gateway call.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/optimus/agent/runner.py tests/unit/agent/test_runner.py
git commit -m "Gate planning on task-aware workspace context"
```

---

### Task 4: Wire Content-Free ACP Diagnostics and Visible Refusals

**Deliverable:** The global ACP runtime records selection evidence in `debug-acp.ndjson`, and Zed
shows the corrective failure message for ambiguous/oversized references.

**Files:**
- Modify: `src/optimus/acp/debug_trace.py`
- Modify: `src/optimus/acp/bootstrap.py`
- Modify: `src/optimus/acp/spec.py`
- Modify: `tests/unit/acp/test_main_debug_trace.py`
- Modify: `tests/unit/acp/test_bootstrap.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`

**Interfaces:**
- Consumes: Task 3 `workspace_context_observer`.
- Produces: `log_workspace_context_result(request, result) -> None` in ACP debug trace.
- Preserves: debug tracing remains opt-in and never writes to ACP stdout.

- [ ] **Step 1: Add a failing debug-trace redaction test**

The test must enable tracing to a temporary log, construct a `WorkspaceContextResult` whose `text`
contains `UNIQUE_SECRET_SENTINEL`, call `log_workspace_context_result`, parse the single NDJSON
line, and assert exactly:

```python
assert payload["hypothesisId"] == "P9.8-CONTEXT"
assert payload["data"]["prioritized_paths"] == ["src/example.py"]
assert payload["data"]["used_bytes"] > 0
assert "UNIQUE_SECRET_SENTINEL" not in log_path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Add failing bootstrap and visible-refusal tests**

Bootstrap test: capture the `AgentRunner` constructor arguments and assert
`workspace_context_observer is log_workspace_context_result`.

Protocol test: make the fake runner return `AgentRunStatus.FAILED`,
`stop_reason="AMBIGUOUS_WORKSPACE_REFERENCE"`, zero tool calls, and a corrective `output_text`.
Assert:

```python
assert response["result"]["stopReason"] == "refusal"
messages = [
    item["params"]["update"]["content"]["text"]
    for item in outbound.notifications
    if item["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
]
assert messages[-1] == failure.output_text
assert messages[-1] != "Turn completed."
```

Also add `test_unparseable_plan_completion_does_not_echo_raw_model_output`: return a failed result
with `stop_reason="UNPARSEABLE_PLAN"` and a unique raw-model sentinel in `output_text`; assert the
agent message remains `Turn completed.` and does not contain the sentinel.

- [ ] **Step 3: Run the new ACP tests and verify failure**

Run:

```bash
pytest tests/unit/acp/test_main_debug_trace.py tests/unit/acp/test_bootstrap.py tests/unit/acp/test_spec_protocol.py -v
```

Expected: new diagnostics/wiring/refusal assertions FAIL.

- [ ] **Step 4: Implement the ACP-owned observer**

Add a function in `debug_trace.py` that maps dataclass fields to JSON-safe primitives and calls
`acp_debug_log`. Example payload fields:

```python
{
    "run_id": request.run_id,
    "session_id": request.session_id,
    "max_total_bytes": result.max_total_bytes,
    "used_bytes": result.used_bytes,
    "prioritized_paths": list(result.prioritized_paths),
    "omitted_count": len(result.omitted_paths),
    "references": [
        {
            "reference": item.reference,
            "status": item.status.value,
            "candidate_count": len(item.candidates),
            "candidates": list(item.candidates),
        }
        for item in result.diagnostics
    ],
    "blocking_stop_reason": result.blocking_stop_reason,
}
```

Do not include `result.text` or any file bytes.

- [ ] **Step 5: Inject the observer and correct failure completion text**

Pass `log_workspace_context_result` from `build_agent_runner_for_harness` into `AgentRunner`. In
`_completion_message`, preserve existing mutation/tool-call branches, then surface sanitized
failure text only for the three workspace-context failures introduced by this plan:

```python
_VISIBLE_WORKSPACE_CONTEXT_FAILURES = frozenset(
    {
        "AMBIGUOUS_WORKSPACE_REFERENCE",
        "REQUIRED_WORKSPACE_FILE_TOO_LARGE",
        "WORKSPACE_REFERENCE_NOT_READABLE",
    }
)

if result.stop_reason in _VISIBLE_WORKSPACE_CONTEXT_FAILURES:
    return result.output_text
return "Turn completed."
```

The Step 2 `UNPARSEABLE_PLAN` regression pins that raw model output is not echoed. This change
closes only the Plan 9.75 fast-follow needed by Plan 9.8. Do not redesign other ACP failure UX.

- [ ] **Step 6: Run ACP, runner, and workspace regressions**

Run:

```bash
pytest tests/unit/acp/test_main_debug_trace.py tests/unit/acp/test_bootstrap.py tests/unit/acp/test_spec_protocol.py tests/unit/agent/test_runner.py tests/unit/agent/test_workspace_context.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/optimus/acp/debug_trace.py src/optimus/acp/bootstrap.py src/optimus/acp/spec.py tests/unit/acp/test_main_debug_trace.py tests/unit/acp/test_bootstrap.py tests/unit/acp/test_spec_protocol.py
git commit -m "Expose workspace context diagnostics through ACP"
```

---

### Task 5: Verify the Correctness Floor and Record Real Operator Evidence

**Deliverable:** Automated gates are green and a current-build Zed run proves exact-path mutation
in a large workspace with correlated context-selection evidence.

**Files:**
- Create: `reports/plan-9-8-task-aware-context-evidence.md`
- Modify: `reports/plan-9-75-zed-hitl-runtime-evidence.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Modify: `docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md` (checkboxes/status only)

**Interfaces:**
- Consumes: Tasks 1-4 and the Plan 9.7 operator PATH/keychain runbook.
- Produces: deterministic and live evidence mapped one-to-one to the Definition of Done.

- [ ] **Step 1: Restore the contributor test environment and run narrow tests**

Use repository-declared dev dependencies; do not install ad hoc unpinned packages:

```bash
uv sync --all-extras
pytest tests/unit/agent/test_workspace_context.py tests/unit/agent/test_runner.py tests/unit/acp/test_main_debug_trace.py tests/unit/acp/test_bootstrap.py tests/unit/acp/test_spec_protocol.py -v
```

Expected: PASS. Record exact counts in the evidence file.

- [ ] **Step 2: Run default tests, coverage, and Ruff**

```bash
pytest -q
pytest --cov=src/optimus --cov-report=term-missing --cov-fail-under=80 -q
python -m ruff check .
```

Expected: default suite PASS; aggregate production coverage >=80%; Ruff clean. Record commands,
counts, coverage, and current Git SHA. If live tiers are deselected by default, state that rather
than implying they ran.

- [ ] **Step 3: Prove deterministic exact-path inclusion under filler pressure**

Run the named regression with `-vv` and add a small evidence table containing:

- task reference;
- target relative path;
- max/used bytes;
- target header present;
- target sentinel present;
- alphabetical filler omitted/truncated;
- blocking reason `None`.

Do not paste source content into the evidence report.

- [ ] **Step 4: Prove ambiguous basename fails visibly without Gateway cost**

Run the runner unit test and ACP protocol test by exact node ID. Record that:

- candidate paths are sorted and shown;
- Gateway call count is zero;
- total cost is `0`;
- mutation count is zero;
- Zed-facing message is not `Turn completed.`;
- stop reason is `refusal` on ACP and `AMBIGUOUS_WORKSPACE_REFERENCE` internally.

- [ ] **Step 5: Install the exact implementation build on the operator PATH**

From the implementation checkout:

```powershell
uv tool install --editable . --reinstall
where.exe optimus-agent
optimus-agent --workspace-root . --check-config --strict --debug-trace
```

Evidence requirements:

- fresh terminal, no active venv;
- no `OPTIMUS_*` or provider keys in shell environment;
- `where.exe` and debug `PROVENANCE` identify the intended executable, source checkout, Git SHA,
  Python executable, and workspace root;
- local gateway credentials come through the Plan 9.7 keychain path;
- never copy secret values into reports.

- [ ] **Step 6: Run the real large-workspace Zed acceptance scenario**

Create or reset one dedicated text fixture under the Zed workspace with content small enough to fit
fully. Ensure alphabetical filler alone exceeds 16 KiB. Use an exact task:

```text
Add a docstring to reports/.plan98-e2e-workspace/example.py.
```

Start a fresh Zed session with `optimus-agent --workspace-root . --debug-trace`, approve the plan,
and require all of:

- `P9.8-CONTEXT` line correlates by `run_id`/`session_id`;
- exact target is in `prioritized_paths` with `resolved` status;
- trace contains byte/path metadata but no fixture source content;
- real Gateway/model emits a WRITE for the exact target;
- approval is explicit;
- real `file_reader` and `write_file` calls occur;
- the target changes and contains the requested docstring;
- `mutation_count == 1`;
- `stopReason: end_turn`;
- no ACP `-32602`, no provider key in the agent process, and cost fields are present.

If the target is confirmed present but the real model still emits READ-only, do **not** mark the
live gate complete and do not weaken the deterministic contract. Record the result and propose a
separate prompt/model or multi-turn follow-up.

- [ ] **Step 7: Run the ambiguous-path live refusal scenario**

Place two eligible `example.py` files in distinct fixture directories and submit:

```text
Add a docstring to example.py.
```

Require a visible Zed refusal listing both relative candidates, no permission request, no Gateway
model call attributable to that run, no file mutation, and correlated `P9.8-CONTEXT` evidence with
`AMBIGUOUS_WORKSPACE_REFERENCE`.

- [ ] **Step 8: Write and cross-link the evidence**

`reports/plan-9-8-task-aware-context-evidence.md` must contain:

- date, OS, Zed version, model, branch, commit, executable/source/workspace provenance;
- deterministic test table;
- exact-path live table;
- ambiguous-path refusal table;
- redacted debug excerpts containing no source or secrets;
- file hash or before/after semantic assertion for the mutated fixture;
- commands and exit codes;
- limitations and explicit non-claims.

Append only a short dated cross-reference to the Plan 9.75 evidence. Preserve its historical
READ-only result unchanged.

- [ ] **Step 9: Update roadmap status only after every gate passes**

Change Plan 9.8 from `Drafted` to `Implemented and live-verified`, link the evidence file, and retain
this exact limitation:

> Plan 9.8 guarantees context inclusion for exact relative paths and unique basenames and visibly
> rejects ambiguous/oversized required references. It does not provide multi-turn replanning or
> Plan 11 intelligent selection and does not prove mutation tasks generally.

Do not change Plan 11 to started/scheduled. Its dependency on the landed 9.8 floor remains.

- [ ] **Step 10: Final verification and documentation commit**

```bash
git diff --check
python -m ruff check .
pytest -q
git status --short
git add reports/plan-9-8-task-aware-context-evidence.md reports/plan-9-75-zed-hitl-runtime-evidence.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md
git diff --cached --name-status
git diff --cached --check
git commit -m "Record Plan 9.8 task-aware context evidence"
```

Expected: checks PASS; staged paths contain only the intended Plan 9.8 evidence/tracking documents.

---

## Definition of Done

### Deterministic code contract

- [ ] Exact eligible relative path is completely included before filler under cap pressure.
- [ ] A unique basename resolves to its one eligible path.
- [ ] Ambiguous basename returns sorted candidates and blocks before Gateway/tool/mutation work.
- [ ] Missing path remains non-blocking for file-creation tasks.
- [ ] Absolute/traversal/glob/ineligible references cannot escape or bypass workspace policy.
- [ ] Oversized or collectively over-budget required files are never partially represented as
  included.
- [ ] Final UTF-8 context size never exceeds 16 KiB.
- [ ] Existing task-blind compatibility wrapper and prompt untrusted-data boundary remain green.

### Runtime and observability contract

- [ ] ACP trace proves selected path/status/byte budget for the exact run and logs no source content.
- [ ] Typed ambiguous/oversized failures cost zero and are visible in Zed as corrective refusals.
- [ ] Exact-path large-workspace Zed run produces an approved real WRITE and one mutation.
- [ ] Plan 9.75 protocol remains conformant: no `-32602`, approval works, and turn ends explicitly.
- [ ] Operator proof uses global PATH/keychain runtime with zero local provider keys.

### Quality and documentation gates

- [ ] Narrow tests pass.
- [ ] Default suite passes.
- [ ] Aggregate production coverage is >=80%.
- [ ] `python -m ruff check .` is clean.
- [ ] Evidence artifact maps every claim to deterministic or real-dependency proof.
- [ ] Roadmap and cross-plan wording make no general mutation-success claim.

## Deferred Follow-Ups

### P9.8-FU-1: Multi-turn read-observe-replan workflow

**Trigger:** A required task spans files whose complete priority blocks exceed 16 KiB, or the real
model still needs READ evidence before it can safely form a WRITE.

**Acceptance criteria:** A separate approved plan defines bounded READ -> observe -> replan
iterations, budget/cost accounting across calls, approval hash semantics for the final plan, and
real evidence. Candidate plan number: 9.85. Do not fold it into Plan 11 implicitly.

### P9.8-FU-2: Intelligent ambiguous-reference ranking

**Owner:** Plan 11.

**Acceptance criteria:** Candidate ranking uses the accepted relevance/trust/freshness/dependency
policy, measures wrong-target regret, and retains a fail-closed threshold. Until then, ambiguity is
visible and deterministic.

### P9.8-FU-3: Dynamic context budgets and required-file summarization

**Owner:** Plan 11.

**Acceptance criteria:** Budget changes are model-aware, cost-attributed, injection-safe, measured
against the null baseline, and never silently omit required evidence.

### P9.8-FU-4: Operator packaging and credential diagnostics

**Owner:** Plan 9.9 in `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`.

**Acceptance criteria:** Plan 9.9 owns cross-layer provider/key mismatch diagnostics and reliable
project-root discovery for non-editable operator installs. Until it lands, Plan 9.8 live evidence
must continue using `uv tool install --editable . --reinstall`; these operator-runtime concerns
must not be silently absorbed into this context-selection plan.

## Reviewer Checklist Before Approval

- [ ] Every in-scope requirement maps to a task and DoD checkbox.
- [ ] The plan uses current post-Plan-9.75 ACP shapes and July 11 operator evidence.
- [ ] No agent-to-ACP package dependency was introduced; diagnostics use callback injection.
- [ ] Blocking failures occur before Gateway cost, state persistence, approval, or tools.
- [ ] Source content cannot enter debug trace or persistent vector indexes.
- [ ] The 16 KiB cap and complete-priority-file rule are internally consistent.
- [ ] Ambiguous and oversized live cases are visible, not merely logged.
- [ ] Plan 9.6 small-workspace mutation proof remains baseline evidence, not a new 9.8 claim.
- [ ] Plan 10 and Plan 11 scope remains separate.
- [ ] No checkbox is pre-checked without a passing command/evidence artifact.

## Implementation Handoff After Approval

After the reviewer agent and operator approve this document, execute with one of:

1. **Subagent-driven development (recommended):** fresh implementation agent per task with
   requirements and code-quality review between tasks.
2. **Inline executing-plans workflow:** implement task-by-task in a dedicated implementation
   worktree with explicit review checkpoints.

The implementer must create a fresh branch/worktree from latest `main`; this planning branch is not
the implementation lane.
