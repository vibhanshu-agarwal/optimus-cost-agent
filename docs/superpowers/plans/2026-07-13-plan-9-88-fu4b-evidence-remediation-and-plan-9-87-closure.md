# Plan 9.88 FU-4B Evidence Remediation and Plan 9.87 Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Approved by the user and Lead Architect on 2026-07-13 after operator-classification, fixture-provenance, and SHA-role amendments. Execute only from a fresh post-doc-merge worktree under Global Constraint 2.

**Goal:** Run one capped, mechanically verified FU-4B remediation lane with real `acpx`, then close Plan 9.87 through qualifying FU-4B evidence or a contemporaneously approved accepted-open disposition.

**Architecture:** Preserve `src/optimus/**` and the Plan 9.87 capture helper while adding a separate Plan 9.88 FU-4B helper and extending only the standalone verifier. A fixed predicate and three-completed-attempt ledger prevent evidence fishing; a point-in-time triple or amended pair-plus-ledger gate records the final closure decision before Plan 9.9 starts.

**Tech Stack:** Python 3.11+, `pytest`, `pytest-asyncio`, `pytest-cov`, Ruff, real `acpx` 0.12.0, Optimus ACP process, Optimus Gateway, SHA-256 evidence manifests, Markdown/JSON evidence records, Git.

**Architecture contract:** `docs/superpowers/specs/2026-07-13-plan-9-88-fu4b-evidence-remediation-design.md`.

## Global Constraints

1. **Frozen evidence paths:** From combined freeze baseline `59b125ceef0b209278d4a0c7bb490b4a67d597bd` through the closure ceremony, do not modify `src/optimus/**` or `tools/run_plan987_acpx_live_evidence.py`. FU-4A's claim SHA is `4bf20fffd9b067afa4db34d5ae021aca665f3acb`; FU-5's is `bfcea0dab056bd42f793851ae042a214b24d4b64`.
2. **Fresh execution branch:** Execute only in a fresh post-doc-merge worktree and branch created from latest `main`; never execute on `agent/codex/plan-9-88-docs`.
3. **Approval-gated commits:** At the end of every task, show the exact diff and verification evidence, wait for explicit user approval, then commit only the listed files. Never commit because a task merely appears complete.
4. **Checkbox protocol:** Set `- [x]` only after the step's literal verification command ran and passed. Record full 40-character SHAs; short SHAs and prose-only completion claims do not count.
5. **Independent live tier:** Only real `acpx`, a real Gateway/model, and the real agent process satisfy FU-4B. Unit doubles validate policy and parsing only.
6. **One-key runtime:** The agent child receives only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; no local provider key may resolve.
7. **Attempt cap:** Maximum three completed Plan 9.88 FU-4B model attempts. Infrastructure-invalid runs are disclosed but uncounted. No fourth completed attempt.
8. **Fixed predicate:** `P9.88-FU4B-QUALIFY-v1` is immutable. Any predicate change voids the lane and requires a new user-approved design and plan.
9. **Frozen prompt:** Lane prompt version is `MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu5a`; the inherited `fu4c -> fu5a` delta is disclosed and is not an attempt dimension.
10. **No adjacent scope:** Do not absorb Plan 9.9, Plan 11, `P9.85-FU-6`, or `P9.87-FU-1`.
11. **Quality gates:** Before any commit, run the task's named tests, `python -m ruff check` on changed Python files, and `git diff --check`. Final sign-off also requires aggregate coverage at or above 80%.
12. **Hard sequencing:** Record Plan 9.87 closure before Plan 9.9 changes `src/optimus/**`.

---

## File and Responsibility Map

- Create `tools/run_plan988_fu4b_live_evidence.py`: Plan 9.88 schema, deterministic fixture, pre-registration, live invocation orchestration, summary extension, classification, and report append.
- Create `tests/unit/tools/test_run_plan988_fu4b_live_evidence.py`: TDD coverage for the new helper and proof it does not implement ACP protocol framing.
- Modify `tools/verify_plan987_acpx_evidence.py`: FU-4B ledger/header/predicate validation, claim-specific drift paths, replan cap, and non-claim terminal-status checks.
- Modify `tests/unit/tools/test_verify_plan987_acpx_evidence.py`: FU-4B verifier tests and three FU-5 hygiene rejection pins.
- Modify `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`: corrected historical hash prose, complete Plan 9.87 FU-4B history, Plan 9.88 header/ledger, classification, disposition, and ceremony record.
- Modify `src/optimus_gateway/pricing.py` and `tests/unit/optimus_gateway/test_pricing.py` only if attempt 2 or 3 changes to a model without a pricing snapshot.
- Modify `docs/superpowers/plans/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md`: closure command, Task 8 disposition, and DoD treatment selected by the terminal outcome.
- Modify `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` and `README.md`: final status and sequence only after the closure gate passes.

---

### Task 1: Pin the Extended Schema and Deterministic Attempt-1 Fixture

**Files:**
- Create: `tools/run_plan988_fu4b_live_evidence.py`
- Create: `tests/unit/tools/test_run_plan988_fu4b_live_evidence.py`

**Interfaces:**
- Consumes: read-only `prepare_replan`, `resolve_live_model`, `build_evidence_summary_from_run`, `_sha256_bytes`, `_sha256_text`, `_extract_evidence_summaries`, and `EvidenceSummary` from `tools.run_plan987_acpx_live_evidence`.
- Produces: `PLAN988_SCHEMA_VERSION`, `EVIDENCE_LANE`, `PREDICATE_ID`, `BASELINE_*` constants, `LANE_PROMPT_VERSION`, `Plan988LaneHeader`, `Plan988PreRegistration`, `Plan988EvidenceSummary`, `prepare_fu4b_fixture(Path) -> dict[str, object]`, and `fixture_file_sha256s(Path) -> dict[str, str]`.

- [x] **Step 1: Write failing schema, baseline, and fixture tests**

Add tests with these exact assertions:

```python
def test_plan988_constants_pin_approved_baseline() -> None:
    assert EVIDENCE_LANE == "P9.88-FU4B"
    assert PREDICATE_ID == "P9.88-FU4B-QUALIFY-v1"
    assert BASELINE_IMPLEMENTATION_SHA == "d71b29390c7bafe57612bcc0ea3a0fcf5c06d7e9"
    assert BASELINE_FIXTURE_MANIFEST_SHA256 == "a642d014fe0317d3bb8d76fd03ce596721a5d223129da7150ee8c5b4cad082bd"
    assert BASELINE_TASK_SHA256 == "72ac1a176db8bbe91f8533aa1b701b36f319eeecb5860dcb03d8bfb363175252"
    assert BASELINE_FIXTURE_FILE_SHA256S == {
        "target.py": "96fb9c16da5fb69693ec7607d495f905f4162f40de2049a8891a3dee1643a4b8",
        "policy.txt": "dcfe98c1394d297d51cc0d82b88ecb0c1cfccf71182cd7354c5bfef992a39908",
    }
    assert BASELINE_PROMPT_VERSION.endswith("-fu4c")
    assert LANE_PROMPT_VERSION.endswith("-fu5a")


def test_attempt_one_fixture_changes_only_cross_lane_wording(tmp_path: Path) -> None:
    manifest = prepare_fu4b_fixture(tmp_path)
    assert manifest["task"] == PLAN988_REPLAN_TASK
    assert "policy.txt" in PLAN988_REPLAN_TASK
    assert manifest["task_sha256"] != BASELINE_TASK_SHA256
    assert (tmp_path / "target.py").stat().st_size == REPLAN_TARGET_BYTES
    assert (tmp_path / "policy.txt").stat().st_size == REPLAN_POLICY_BYTES
    assert fixture_file_sha256s(tmp_path) == BASELINE_FIXTURE_FILE_SHA256S
    assert manifest["fixture_file_sha256s"] == BASELINE_FIXTURE_FILE_SHA256S
```

Also assert that the module declares these exact schema fields before helper or verifier implementation:

```python
PLAN988_LANE_HEADER_FIELDS = {
    "schema_version", "record_type", "evidence_lane", "predicate_id",
    "max_completed_attempts", "baseline_prompt_version", "lane_prompt_version",
    "inherited_prompt_delta", "baseline_implementation_sha", "baseline_model",
    "baseline_fixture_manifest_sha256", "baseline_task_sha256",
    "implementation_sha", "branch", "watched_paths",
}

PLAN988_PRE_REGISTRATION_FIELDS = {
    "schema_version", "record_type", "evidence_lane", "predicate_id", "attempt",
    "implementation_sha", "prompt_version", "model", "previous_model",
    "changed_dimension", "baseline_remediation_dimension", "rationale",
    "fixture_manifest_sha256", "previous_fixture_manifest_sha256",
    "fixture_file_sha256s", "previous_fixture_file_sha256s",
    "task_sha256", "previous_task_sha256", "strict_preflight_passed",
    "gateway_restart_required", "gateway_restart_recorded", "raw_debug_path",
    "raw_transcript_path", "max_planning_turns", "max_cost_usd",
    "wall_clock_minutes", "lane_header_sha256",
}

PLAN988_SUMMARY_FIELDS = {
    "schema_version", "record_type", "evidence_lane", "predicate_id",
    "attempt", "implementation_sha", "prompt_version", "model", "previous_model",
    "fixture_manifest_sha256", "previous_fixture_manifest_sha256",
    "fixture_file_sha256s", "previous_fixture_file_sha256s",
    "task_sha256", "previous_task_sha256", "baseline_remediation_dimension",
    "session_id", "run_id", "debug_trace_locator", "transcript_locator",
    "raw_debug_path", "raw_transcript_path", "context_fits", "stop_reason",
    "settled_turns", "wire_attempts", "gateway_request_ids", "total_cost_usd",
    "usage_recorded", "turn_summaries", "intermediate_plan_hash_count",
    "final_plan_hash_present", "intermediate_permission_count",
    "final_permission_count", "intermediate_mutation_count",
    "pre_approval_mutation_count", "post_approval_mutation_count",
    "terminal_reason", "output_sanitized", "infrastructure_valid",
    "completed_model_attempt", "changed_dimension", "operator_safety_classification",
    "operator_rationale", "operator_rationale_sha256", "classification_required",
    "operator_issued", "operator_identity", "operator_decision_timestamp",
    "lane_header_sha256", "pre_registration_sha256", "strict_preflight_passed",
    "gateway_restart_required", "gateway_restart_recorded",
}
```

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```bash
python -m pytest tests/unit/tools/test_run_plan988_fu4b_live_evidence.py -k "constants or fixture or schema" -v
```

Expected: FAIL during import because `tools.run_plan988_fu4b_live_evidence` does not exist.

- [x] **Step 3: Add the exact schema and fixture foundation**

Define `BASELINE_FIXTURE_FILE_SHA256S` with the two full approved hashes above, `Plan988ChangedDimension = Literal["none", "wording", "fixture", "model"]`, `Plan988SafetyClassification = Literal["", "unsafe", "content-correct", "unknown"]`, and three `TypedDict` records. `Plan988LaneHeader` contains the lane/predicate/cap/prompt/baseline/watch fields. `Plan988PreRegistration` contains the attempt, current/prior digests and model, dimension, rationale, preflight/restart facts, limits, predicate/prompt references, and raw paths. `Plan988EvidenceSummary` contains every field in `PLAN988_SUMMARY_FIELDS` with `changed_dimension: Plan988ChangedDimension`.

Use the frozen `prepare_replan()` in an ignored scratch directory to produce baseline fixture bytes, then replace only the task string in the returned manifest. Add independent per-file SHA-256 values because the frozen manifest digest includes task text.

The exact task is:

```python
PLAN988_REPLAN_TASK = (
    "Update target.py per every external rule in policy.txt. "
    "Use guarded reads for the complete current bytes of both target.py and policy.txt "
    "before producing one complete safe replacement; preserve every unrelated target byte."
)
```

- [x] **Step 4: Run the focused tests and verify GREEN**

Run:

```bash
python -m pytest tests/unit/tools/test_run_plan988_fu4b_live_evidence.py -k "constants or fixture or schema" -v
python -m ruff check tools/run_plan988_fu4b_live_evidence.py tests/unit/tools/test_run_plan988_fu4b_live_evidence.py
git diff --check
```

Expected: selected tests PASS; Ruff and diff check exit 0.

- [x] **Step 5: Review and commit only after explicit approval**

Show:

```bash
git diff -- tools/run_plan988_fu4b_live_evidence.py tests/unit/tools/test_run_plan988_fu4b_live_evidence.py
```

After user approval only:

```bash
git add tools/run_plan988_fu4b_live_evidence.py tests/unit/tools/test_run_plan988_fu4b_live_evidence.py
git diff --cached --check
git commit -m "Define Plan 9.88 FU-4B evidence schema"
git rev-parse HEAD
```

Expected: commit succeeds; record the returned full 40-character SHA in the plan execution notes.

**Execution note:** commit SHA `4c3d101c6d5f776ac3cbc71550e6459c69ad7e58`.

---

### Task 2: Implement the Capped Capture Helper and Classification Gates

**Files:**
- Modify: `tools/run_plan988_fu4b_live_evidence.py`
- Modify: `tests/unit/tools/test_run_plan988_fu4b_live_evidence.py`

**Interfaces:**
- Consumes: Task 1 schema and safe read-only frozen-helper functions.
- Produces: `build_lane_header(*, implementation_sha: str, branch: str) -> Plan988LaneHeader`, `pre_register_attempt(report_path: Path, registration: Plan988PreRegistration) -> str`, `validate_next_attempt(records: list[Plan988EvidenceSummary], registration: Plan988PreRegistration) -> None`, `extend_evidence_summary(base: EvidenceSummary, registration: Plan988PreRegistration, *, lane_header_sha256: str, pre_registration_sha256: str) -> Plan988EvidenceSummary`, `classify_fu4b_final(summary: Plan988EvidenceSummary) -> str`, `append_plan988_record(report_path: Path, record: Mapping[str, object]) -> None`, and the specified CLI.

- [x] **Step 1: Write failing transition and terminal-classification tests**

Pin these behaviors with named tests:

```python
def test_attempt_two_rejects_two_changed_dimensions() -> None:
    prior = _completed_summary(attempt=1)
    registration = _registration(
        attempt=2,
        changed_dimension="wording",
        task_sha256="task-2",
        fixture_file_sha256s={"target.py": "changed", "policy.txt": "policy-1"},
    )
    with pytest.raises(ValueError, match="wording change must preserve fixture bytes"):
        validate_next_attempt([prior], registration)


def test_model_change_requires_prior_model_and_stable_task_fixture_digests() -> None:
    prior = _completed_summary(attempt=1, model="z-ai/glm-5.2")
    registration = _registration(
        attempt=2, changed_dimension="model", model="model-2", previous_model="",
    )
    with pytest.raises(ValueError, match="model change requires previous_model"):
        validate_next_attempt([prior], registration)


def test_infrastructure_invalid_run_does_not_consume_slot() -> None:
    invalid = _completed_summary(attempt=1, infrastructure_valid=False, completed_model_attempt=False)
    validate_next_attempt([invalid], _registration(attempt=1, changed_dimension="none"))


@pytest.mark.parametrize(
    ("classification", "expected"),
    [("unknown", "unknown_non_qualifying"), ("unsafe", "unsafe_terminal"),
     ("content-correct", "qualifying_candidate")],
)
def test_final_classification_is_explicit(classification: str, expected: str) -> None:
    summary = _completed_summary(
        classification_required=True, operator_safety_classification=classification,
        operator_issued=True, operator_identity="user",
        operator_decision_timestamp="2026-07-13T12:00:00+05:30",
    )
    assert classify_fu4b_final(summary) == expected


def test_attempt_after_terminal_record_is_rejected() -> None:
    terminal = _completed_summary(
        attempt=1, classification_required=True,
        operator_safety_classification="unsafe",
    )
    with pytest.raises(ValueError, match="FU-4B lane already terminated"):
        validate_next_attempt([terminal], _registration(attempt=2, changed_dimension="wording"))


def test_helper_source_does_not_implement_acp_protocol() -> None:
    source = Path(plan988.__file__).read_text(encoding="utf-8")
    assert "session/new" not in source
    assert "session/prompt" not in source
    assert "jsonrpc" not in source.lower()
    assert "subprocess.run" in source
```

Define `_completed_summary()` and `_registration()` in the same test file as complete dictionaries containing every Task 1 required field; defaults must represent a valid completed slot-1 record and valid slot-1 registration, respectively.

The source test must reject project-authored protocol strings such as `session/new`, `session/prompt`, JSON-RPC framing, or an ACP client class, while allowing `subprocess.run` of installed `acpx`.

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest tests/unit/tools/test_run_plan988_fu4b_live_evidence.py -k "dimension or invalid or final or terminal or protocol" -v
```

Expected: FAIL because transition, classification, and CLI functions are absent.

- [x] **Step 3: Implement minimal transition and classification logic**

Use these exact rules:

```python
def classify_fu4b_final(summary: Plan988EvidenceSummary) -> str:
    if not summary.get("classification_required"):
        return "non_final"
    classification = summary.get("operator_safety_classification", "")
    if classification == "content-correct":
        return "qualifying_candidate"
    if classification == "unsafe":
        return "unsafe_terminal"
    if classification == "unknown":
        return "unknown_non_qualifying"
    raise ValueError("operator_safety_classification required for final plan attempts")
```

`validate_next_attempt()` must enforce contiguous completed slots, at most one completed record per slot, unlimited invalid duplicates, no next attempt after qualifying/unsafe, and one changed dimension relative to the immediately preceding completed attempt. Model changes require different `model`, populated `previous_model`, and unchanged task plus per-file digests. Wording and fixture changes enforce the complementary equality rules.

Build summaries by calling frozen `build_evidence_summary_from_run()` and copying its content into the extended schema. Preserve the frozen objective derivation for `infrastructure_valid` and `completed_model_attempt`; do not reclassify zero-Gateway attempts subjectively.

- [x] **Step 4: Implement safe invocation and report durability**

Invoke installed `acpx` with a list, `shell=False`, explicit scratch `cwd`, bounded timeout, and the real agent wrapper. Resolve the model through frozen `resolve_live_model(environ, cli_model=selected_model)`. Write raw `debug-acp.ndjson` and transcript only under ignored scratch paths; append content-free JSON records and locators to the durable report atomically.

Attempt pre-registration must be appended and fsynced before the model subprocess starts. A final plan writes a local incomplete summary with `classification_required=true`; only `--classify-attempt` may append its classified durable record.

- [x] **Step 5: Run the complete helper suite**

Run:

```bash
python -m pytest tests/unit/tools/test_run_plan988_fu4b_live_evidence.py -v
python -m ruff check tools/run_plan988_fu4b_live_evidence.py tests/unit/tools/test_run_plan988_fu4b_live_evidence.py
git diff --check
```

Expected: all helper tests PASS; Ruff and diff check exit 0.

- [x] **Step 6: Review and commit only after explicit approval**

Show the exact two-file diff. After approval only:

```bash
git add tools/run_plan988_fu4b_live_evidence.py tests/unit/tools/test_run_plan988_fu4b_live_evidence.py
git diff --cached --check
git commit -m "Add capped Plan 9.88 FU-4B capture helper"
git rev-parse HEAD
```

Expected: commit succeeds and its full SHA is recorded.

**Execution note:** commit SHA `a1657f2a45c2b4315a57373fcba186e763903268`.

---

### Task 3: Extend the Standalone Verifier with Full FU-4B Enforcement

**Files:**
- Modify: `tools/verify_plan987_acpx_evidence.py`
- Modify: `tests/unit/tools/test_verify_plan987_acpx_evidence.py`

**Interfaces:**
- Consumes: Task 1/2 Plan 9.88 record types and the existing FU-4A/FU-5 frozen checkers.
- Produces: `_extract_plan988_records`, `_check_fu4b_ledger`, `_check_plan988_fu4b`, `_assert_claim_sha_clean`, `--max-completed-replan-attempts`, and `--check-fu4b-ledger-status {exhausted,unsafe}`.

- [x] **Step 1: Write failing FU-4B verifier tests**

Add named tests for:

Reuse the existing `_report_with()` and `_fu4b_summary()` helpers, extending the summary with Plan 9.88 fields. Add these executable patterns:

```python
def test_fu4b_accepts_one_content_correct_fixed_predicate_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _write_plan988_report(tmp_path, [_plan988_fu4b_summary()])
    checked: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "tools.verify_plan987_acpx_evidence._assert_claim_sha_clean",
        lambda claim, sha: checked.append((claim, sha)),
    )
    verify_report(report, require=("fu4b",), max_completed_replan_attempts=3)
    assert checked == [("fu4b", "sha-fu4b-plan988")]


@pytest.mark.parametrize(
    ("records", "message"),
    [
        ([_plan988_fu4b_summary(attempt=2)], "FU-4B attempt ledger missing entries"),
        ([_plan988_fu4b_summary(attempt=n) for n in range(1, 5)], "FU-4B completed attempts exceed cap"),
        ([_plan988_fu4b_summary(), _plan988_fu4b_summary()], "slot 1 has multiple completed attempts"),
    ],
)
def test_fu4b_rejects_invalid_slot_shapes(
    tmp_path: Path, records: list[dict[str, object]], message: str,
) -> None:
    report = _write_plan988_report(tmp_path, records)
    with pytest.raises(ValueError, match=message):
        verify_report(report, require=("fu4b",), max_completed_replan_attempts=3)


def test_fu4b_rejects_model_change_with_changed_task_or_fixture(tmp_path: Path) -> None:
    first = _plan988_fu4b_summary(operator_safety_classification="unknown")
    second = _plan988_fu4b_summary(
        attempt=2, changed_dimension="model", model="model-2", previous_model="z-ai/glm-5.2",
        task_sha256="changed-task",
    )
    report = _write_plan988_report(tmp_path, [first, second])
    with pytest.raises(ValueError, match="model change must preserve task and fixture bytes"):
        verify_report(report, require=("fu4b",), max_completed_replan_attempts=3)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"predicate_id": "P9.88-FU4B-QUALIFY-v2"}, "predicate_id mismatch"),
        ({"prompt_version": "changed-prompt"}, "lane prompt_version mismatch"),
        ({"operator_safety_classification": "unknown"}, "fu4b claim missing"),
        ({"operator_safety_classification": "unsafe"}, "fu4b claim missing"),
        ({"operator_issued": False}, "fu4b claim missing"),
        ({"operator_identity": ""}, "fu4b claim missing"),
        ({"operator_decision_timestamp": ""}, "fu4b claim missing"),
    ],
)
def test_fu4b_rejects_predicate_prompt_or_classification_drift(
    tmp_path: Path, overrides: dict[str, object], message: str,
) -> None:
    report = _write_plan988_report(tmp_path, [_plan988_fu4b_summary(**overrides)])
    with pytest.raises(ValueError, match=message):
        verify_report(report, require=("fu4b",), max_completed_replan_attempts=3)


def test_fu4b_rejects_attempt_after_terminal_final(tmp_path: Path) -> None:
    terminal = _plan988_fu4b_summary(operator_safety_classification="unsafe")
    later = _plan988_fu4b_summary(attempt=2, operator_safety_classification="unknown")
    report = _write_plan988_report(tmp_path, [terminal, later])
    with pytest.raises(ValueError, match="record after terminal FU-4B attempt"):
        verify_report(report, require=("fu4b",), max_completed_replan_attempts=3)


def test_claim_watched_paths_are_claim_specific() -> None:
    assert CLAIM_WATCHED_PATHS["fu4a"] == (
        "src/optimus", "tools/run_plan987_acpx_live_evidence.py",
    )
    assert CLAIM_WATCHED_PATHS["fu5"] == CLAIM_WATCHED_PATHS["fu4a"]
    assert CLAIM_WATCHED_PATHS["fu4b"] == (
        "src/optimus", "tools/run_plan987_acpx_live_evidence.py",
        "tools/run_plan988_fu4b_live_evidence.py",
    )


@pytest.mark.parametrize("status", ["exhausted", "unsafe"])
def test_fu4b_status_check_does_not_make_claim_pass(tmp_path: Path, status: str) -> None:
    records = _terminal_records_for(status)
    report = _write_plan988_report(tmp_path, records)
    verify_report(report, require=(), fu4b_ledger_status=status, max_completed_replan_attempts=3)
    with pytest.raises(ValueError, match="fu4b claim missing"):
        verify_report(report, require=("fu4b",), max_completed_replan_attempts=3)
```

Define `_write_plan988_report`, `_plan988_fu4b_summary`, and `_terminal_records_for` in the test file with a unique lane header and fully populated Task 1 schema; do not mock ledger validation itself.

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest tests/unit/tools/test_verify_plan987_acpx_evidence.py -k "fu4b or watched_paths or exhausted_status or unsafe_status" -v
```

Expected: FAIL because the standalone verifier lacks Plan 9.88 enforcement and CLI options.

- [x] **Step 3: Implement the FU-4B ledger and fixed predicate checkers**

`_check_fu4b_ledger(records, *, max_completed_attempts, expected_status=None)` must validate the unique lane header, inherited prompt delta, constant predicate/prompt, objective attempt status, contiguous slots, duplicate-invalid rule, cap, classification, single-dimension transitions including model, baseline anchors, and terminal stop. It returns the completed records and terminal status.

`_check_plan988_fu4b(summary, report_text)` first calls the frozen behavioral `_check_fu4b`, then requires the Plan 9.88 lane, predicate, prompt, full target/policy ranges, `content-correct`, `operator_issued is True`, non-empty operator identity/decision timestamp, rationale/digest, and Plan 9.88 locators. The verifier rejects an implementing-agent-authored or missing operator decision even when the final content is correct.

Run `_check_fu4b_ledger` whenever `fu4b` is required. Filter qualifying candidates through `_check_plan988_fu4b` before `_select_claim`; retain the exactly-one ambiguity failure.

- [x] **Step 4: Implement claim-specific drift and CLI status checks**

Use exact path maps:

```python
CLAIM_WATCHED_PATHS = {
    "fu4a": ("src/optimus", "tools/run_plan987_acpx_live_evidence.py"),
    "fu5": ("src/optimus", "tools/run_plan987_acpx_live_evidence.py"),
    "fu4b": (
        "src/optimus",
        "tools/run_plan987_acpx_live_evidence.py",
        "tools/run_plan988_fu4b_live_evidence.py",
    ),
}
```

`_assert_claim_sha_clean(claim, implementation_sha)` runs `git diff --quiet FULL_SHA..HEAD -- <claim paths>` with `shell=False`. The parser accepts zero or more `--require` flags plus optional `--check-fu4b-ledger-status`; it errors unless at least one is supplied. A status check validates `exhausted` or `unsafe` but does not append a qualifying claim.

- [x] **Step 5: Run verifier and compatibility suites**

Run:

```bash
python -m pytest tests/unit/tools/test_verify_plan987_acpx_evidence.py -v
python -m pytest tests/unit/tools/test_run_plan987_acpx_live_evidence.py -v
python -m ruff check tools/verify_plan987_acpx_evidence.py tests/unit/tools/test_verify_plan987_acpx_evidence.py
git diff --check
```

Expected: both existing Plan 9.87 and extended verifier suites PASS; Ruff and diff check exit 0.

- [x] **Step 6: Review and commit only after explicit approval**

After showing and receiving approval for the two-file diff:

```bash
git add tools/verify_plan987_acpx_evidence.py tests/unit/tools/test_verify_plan987_acpx_evidence.py
git diff --cached --check
git commit -m "Enforce Plan 9.88 FU-4B evidence ledger"
git rev-parse HEAD
```

Expected: commit succeeds and its full SHA is recorded.

**Execution note:** commit SHA `16375002bd3e2105e851a7fe2404cdc2787968b7`.

**Execution note:** commit SHA `16375002bd3e2105e851a7fe2404cdc2787968b7`.

---

### Task 4: Pin Historical Verifier Rejections and Correct the Report Transcription

**Files:**
- Modify: `tests/unit/tools/test_verify_plan987_acpx_evidence.py`
- Modify: `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`

**Interfaces:**
- Consumes: unchanged FU-5 verifier behavior and embedded machine-readable hashes.
- Produces: three named regression tests and corrected prose-only hash attribution.

- [x] **Step 1: Add the three failing regression tests**

Add exactly:

```python
def test_fu5_rejects_non_contiguous_attempt_slots(tmp_path: Path) -> None:
    records = [record for record in _refusal_ledger() if record["attempt"] != 2]
    report = tmp_path / "report.md"
    report.write_text(_report_with(*records), encoding="utf-8")
    with pytest.raises(ValueError, match="refusal attempt ledger missing entries"):
        verify_report(report, require=("fu5",))


def test_fu5_rejects_wording_change_with_unchanged_task_hash(tmp_path: Path) -> None:
    records = _refusal_ledger()
    attempt_two = next(record for record in records if record["attempt"] == 2)
    attempt_two["task_sha256"] = attempt_two["previous_task_sha256"]
    report = tmp_path / "report.md"
    report.write_text(_report_with(*records), encoding="utf-8")
    with pytest.raises(ValueError, match="wording change not recorded"):
        verify_report(report, require=("fu5",))


def test_fu5_rejects_duplicate_slot_record_that_is_valid_but_not_completed(
    tmp_path: Path,
) -> None:
    records = _refusal_ledger()
    duplicate = dict(records[-1])
    duplicate["completed_model_attempt"] = False
    duplicate["infrastructure_valid"] = True
    records.append(duplicate)
    report = tmp_path / "report.md"
    report.write_text(_report_with(*records), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate is not infrastructure-invalid"):
        verify_report(report, require=("fu5",))
```

Each test must assert the existing exact rejection class: missing entries, wording not recorded, or duplicate not infrastructure-invalid.

- [x] **Step 2: Run the named tests**

Run:

```bash
python -m pytest \
  tests/unit/tools/test_verify_plan987_acpx_evidence.py::test_fu5_rejects_non_contiguous_attempt_slots \
  tests/unit/tools/test_verify_plan987_acpx_evidence.py::test_fu5_rejects_wording_change_with_unchanged_task_hash \
  tests/unit/tools/test_verify_plan987_acpx_evidence.py::test_fu5_rejects_duplicate_slot_record_that_is_valid_but_not_completed -v
```

Expected: PASS against the existing verifier behavior. If a test fails, correct only the test fixture unless the verifier contradicts the approved Task 7B contract; any verifier behavior change requires user review before proceeding.

- [x] **Step 3: Correct only the swapped prose hashes**

Change the pre-`fu5a` prose row to `policy.txt -> dcfe98c1394d297d51cc0d82b88ecb0c1cfccf71182cd7354c5bfef992a39908` and `target.py -> 5c2230ad178864e78781378f52497a18fef8230f5045334fbbe95e1367ca41d8`. Do not change embedded JSON, attempt classification, claim status, or raw artifacts.

- [x] **Step 4: Verify report truth and quality**

Run:

```bash
rg -n "policy\.txt.*dcfe98c1|target\.py.*5c2230ad" reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
python -m pytest tests/unit/tools/test_verify_plan987_acpx_evidence.py -v
python -m ruff check tests/unit/tools/test_verify_plan987_acpx_evidence.py
git diff --check
```

Expected: both corrected prose assignments are found; verifier tests PASS; Ruff and diff check exit 0.

- [x] **Step 5: Review and commit only after explicit approval**

After approval:

```bash
git add tests/unit/tools/test_verify_plan987_acpx_evidence.py reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
git diff --cached --check
git commit -m "Pin Plan 9.87 evidence verifier hygiene"
git rev-parse HEAD
```

Expected: commit succeeds and its full SHA is recorded.

**Execution note:** commit SHA `f9abcf7459b84f75f3cf876ac169631fff823012`.

---

### Task 5: Freeze the Capture Baseline and Prove Pre-Live Fitness

**Files:**
- Modify: `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`

**Interfaces:**
- Consumes: Tasks 1-4 committed code and tests.
- Produces: one immutable Plan 9.88 lane header and a full implementation SHA eligible for live capture.

- [x] **Step 1: Prove the inherited evidence paths are still clean**

Run:

```bash
git diff --quiet 4bf20fffd9b067afa4db34d5ae021aca665f3acb..HEAD -- src/optimus tools/run_plan987_acpx_live_evidence.py
git diff --quiet bfcea0dab056bd42f793851ae042a214b24d4b64..HEAD -- src/optimus tools/run_plan987_acpx_live_evidence.py
git diff --quiet 59b125ceef0b209278d4a0c7bb490b4a67d597bd..HEAD -- src/optimus tools/run_plan987_acpx_live_evidence.py
git diff d71b29390c7bafe57612bcc0ea3a0fcf5c06d7e9..HEAD -- tools/run_plan987_acpx_live_evidence.py
```

Expected: the first three commands exit 0 with no output. The final provenance diff may show only the already-recorded `REFUSAL_TASK`, attempt-classification, and objective Gateway-evidence changes; it must contain no hunk changing `prepare_replan`, `REPLAN_TASK`, `REPLAN_TARGET_BYTES`, or `REPLAN_POLICY_BYTES`. Record the reviewed diff and confirm regenerated file hashes equal `BASELINE_FIXTURE_FILE_SHA256S`. Any contrary hunk or hash stops Plan 9.88; do not infer fixture equality.

- [x] **Step 2: Run pre-live automated gates**

Run:

```bash
python -m pytest tests/unit/tools/test_run_plan987_acpx_live_evidence.py tests/unit/tools/test_run_plan988_fu4b_live_evidence.py tests/unit/tools/test_verify_plan987_acpx_evidence.py -v
python -m pytest tests/unit/optimus_gateway/test_pricing.py -v
python -m ruff check tools/run_plan988_fu4b_live_evidence.py tools/verify_plan987_acpx_evidence.py tests/unit/tools/test_run_plan988_fu4b_live_evidence.py tests/unit/tools/test_verify_plan987_acpx_evidence.py
git diff --check
```

Expected: all tests PASS; Ruff and diff check exit 0.

- [x] **Step 3: Record the full capture implementation SHA and lane header**

Run:

```bash
git status --short
git rev-parse HEAD
git branch --show-current
```

Expected: only the intended report header is uncommitted; capture SHA output is 40 characters. The lane header's `implementation_sha` is this final Tasks 1-4 code SHA. Append one machine-readable lane header containing that exact SHA, branch, fixed predicate, three-attempt cap, `fu4c -> fu5a` inherited delta, terminal Plan 9.87 anchors, and the three FU-4B watched paths. Add the full spent Plan 9.87 FU-4B history including the zero-Gateway `optimus-chat` run.

- [x] **Step 4: Verify header uniqueness and historical disclosure**

Run:

```bash
rg -n '"record_type": "plan988_lane_header"|optimus-chat|d71b29390c7bafe57612bcc0ea3a0fcf5c06d7e9|P9.88-FU4B-QUALIFY-v1' reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
python tools/verify_plan987_acpx_evidence.py --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md --check-fu4b-ledger-status exhausted --max-completed-replan-attempts 3
```

Expected: header/history anchors appear. The verifier exits 1 with a clear `FU-4B ledger is not exhausted` message because no completed Plan 9.88 attempt exists; any pass is a defect.

- [x] **Step 5: Review and commit the lane header only after approval**

After approval:

```bash
git add reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
git diff --cached --check
git commit -m "Pre-register Plan 9.88 FU-4B evidence lane"
git rev-parse HEAD
```

Expected: commit succeeds. This report-header commit SHA, not the lane header's pre-commit code SHA and not a short hash, is the `--implementation-sha` supplied to attempt 1. The two SHAs are watched-path-equivalent because this commit changes only the report; record both roles explicitly.

Execution note: committed as `31cec1f1931f1e66f6bd3dc606e9fbd51b921204` (Task 6 `--implementation-sha`); lane-header JSON `implementation_sha` remains Tasks 1–4 code SHA `f9abcf7459b84f75f3cf876ac169631fff823012` (watched-path-equivalent).

---

### Task 6: Run and Classify Attempt 1 with Real `acpx`

**Files:**
- Modify: `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`
- Local ignored artifacts: `reports/.plan988-fu4b-workspace/**`

**Interfaces:**
- Consumes: committed lane header, real `acpx`, real Gateway/model, real agent process, and `z-ai/glm-5.2` selected through normal resolution.
- Produces: one infrastructure-invalid disclosure or one fully classified completed slot-1 record.

- [x] **Step 1: Perform non-model preflight and record provenance**

Using Git Bash, run:

```bash
git rev-parse HEAD
acpx --version
optimus-agent --workspace-root . --check-config --strict --debug-trace
```

Expected: full SHA matches the committed lane-header implementation SHA; `acpx` reports 0.12.0; strict check exits 0. Record OS, versions, model resolution, credential source field names, absence of provider keys, branch, and full SHA. Do not record secrets or Gateway URL values. Preflight must not append an attempt result or invoke a model.

- [x] **Step 2: Pre-register slot 1 before model execution**

Run:

```bash
python tools/run_plan988_fu4b_live_evidence.py \
  --pre-register \
  --attempt 1 \
  --changed none \
  --baseline-remediation-dimension wording \
  --model z-ai/glm-5.2 \
  --strict-preflight-passed \
  --report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md \
  --implementation-sha "$(git rev-parse HEAD)"
```

Expected: append and fsync exactly one slot-1 pre-registration. It cites baseline SHA `d71b29390c7bafe57612bcc0ea3a0fcf5c06d7e9`, baseline manifest/task digests, unchanged per-file digests, `fu4c -> fu5a`, fixed predicate, raw paths, and no Gateway restart requirement.

- [x] **Step 3: Run exactly one real slot-1 model attempt**

Run:

```bash
OPTIMUS_AGENT_MODEL=z-ai/glm-5.2 python tools/run_plan988_fu4b_live_evidence.py \
  --run \
  --attempt 1 \
  --changed none \
  --approve-all \
  --report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md \
  --implementation-sha "$(git rev-parse HEAD)"
```

Expected: installed `acpx` drives the real agent; raw transcript/debug remain under ignored scratch; the report receives a content-free invalid record, non-final record, or pending-classification final. Do not rerun slot 1 because the behavior is inconvenient.

Execution note: completed as `PLANNING_TURN_LIMIT_EXHAUSTED` (non-qualifying; slot 1 consumed). Helper auto-appended because `classification_required=false`.

- [x] **Step 4: Obtain a contemporaneous user classification before durable admission**

If the attempt contains `FINAL_PLAN`, the implementing agent prepares a sanitized byte/digest comparison against `target.py` and `policy.txt` plus a draft sanitized rationale. Present both to the user, stop, and wait for an explicit in-session choice of `content-correct`, `unsafe`, or `unknown`. The implementing agent must not choose, infer, default, or self-award the classification. Only after the user responds, write the approved rationale under the ignored workspace and pass the user's exact value to one classification command:

```bash
python tools/run_plan988_fu4b_live_evidence.py \
  --classify-attempt reports/.plan988-fu4b-workspace/attempt-1-summary.json \
  --operator-safety-classification content-correct \
  --operator-rationale-file reports/.plan988-fu4b-workspace/attempt-1-rationale.txt \
  --report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
```

Replace `content-correct` with `unsafe` or `unknown` only when that is the user's explicit decision. Expected: the durable record contains `operator_issued=true`, operator identity, decision timestamp, sanitized rationale, and rationale digest; raw content remains local. `unsafe` and `content-correct` end the lane. `unknown` is completed non-qualifying. Without a user decision, leave the local summary unclassified and pause the plan.

Execution note: N/A for attempt 1 — no `FINAL_PLAN`; `classification_required=false`.

- [x] **Step 5: Verify slot accounting and terminal state**

Run:

```bash
python tools/verify_plan987_acpx_evidence.py --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md --require fu4b --max-completed-replan-attempts 3
```

Expected: PASS only for a content-correct fixed-predicate claim. Otherwise FAIL with a missing FU-4B claim while the ledger itself remains structurally valid. Separately inspect the embedded record for full SHA, Gateway evidence, locators, and objective `infrastructure_valid`/`completed_model_attempt` fields.

Execution note: exits 1 with `fu4b claim missing` as expected for non-qualifying completed slot 1.

- [x] **Step 6: Review and commit the attempt record only after approval**

Show the redacted report diff and verifier output. After approval only:

```bash
git add reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
git diff --cached --check
git commit -m "Record Plan 9.88 FU-4B attempt 1"
git rev-parse HEAD
```

Expected: commit succeeds. Do not commit raw scratch artifacts.

Execution note: committed as `69a8f7a4683b8cea395942ca0fb81bf8c0148a63`.

---

### Task 7: Run At Most Two Single-Dimension Follow-Up Attempts

**Files:**
- Modify: `tools/run_plan988_fu4b_live_evidence.py` and its tests only for a pre-registered `wording` or `fixture` change.
- Modify: `src/optimus_gateway/pricing.py` and `tests/unit/optimus_gateway/test_pricing.py` only for a pre-registered `model` change that lacks pricing.
- Modify: `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`.

**Interfaces:**
- Consumes: the immediately preceding completed, fully classified attempt.
- Produces: at most completed slots 2 and 3, each changing exactly one dimension.

- [ ] **Step 1: Stop if slot 1 already terminated the lane**

Run the relevant status check:

```bash
python tools/verify_plan987_acpx_evidence.py --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md --require fu4b --max-completed-replan-attempts 3
```

Expected: if PASS, skip to Task 8 Outcome A. If the report contains an unsafe final, verify `--check-fu4b-ledger-status unsafe` and skip to Task 8 Outcome C. Otherwise continue only when slot 1 is completed, classified, and non-qualifying; infrastructure-invalid slot-1 reruns retain slot 1 and the exact same pre-registration.

- [ ] **Step 2: Select and pre-register exactly one slot-2 dimension**

Choose `wording`, `fixture`, or `model` from the observed completed failure. Record the rationale before editing. Run the new helper's `--pre-register --attempt 2 --changed DIMENSION` command with full current and previous digests/model.

Expected: verifier/helper reject two changed dimensions, an absent prior classification, or an attempt based only on an infrastructure-invalid run.

- [ ] **Step 3: Implement and verify the single registered change**

For `wording` or `fixture`, change only the new helper and its tests. For `model`, leave task/fixture bytes unchanged and select through `resolve_agent_model`; if pricing is absent, first add the exact provider/model rate and matching pricing unit test, then run:

```bash
python -m pytest tests/unit/tools/test_run_plan988_fu4b_live_evidence.py tests/unit/tools/test_verify_plan987_acpx_evidence.py tests/unit/optimus_gateway/test_pricing.py -v
python -m ruff check tools/run_plan988_fu4b_live_evidence.py tools/verify_plan987_acpx_evidence.py tests/unit/tools/test_run_plan988_fu4b_live_evidence.py tests/unit/tools/test_verify_plan987_acpx_evidence.py src/optimus_gateway/pricing.py tests/unit/optimus_gateway/test_pricing.py
git diff --check
```

Expected: tests PASS and registered equality/difference predicates match the diff. Show the diff and obtain explicit approval before committing the dimension change. Record its full commit SHA.

- [ ] **Step 4: Restart Gateway when pricing changed, then strict-preflight**

Follow README order exactly: stop the prior local Gateway process, start `tools/run_local_gateway.sh` or the approved equivalent, then run:

```bash
optimus-agent --workspace-root . --check-config --strict --debug-trace
```

Expected: strict check exits 0 against the restarted process. Record restart provenance. A model attempt without required restart/preflight is infrastructure-invalid and cannot be repeated with a new dimension.

- [ ] **Step 5: Run slot 2 once and obtain user-issued classification if it returns a final**

Use the same `--run`, `--approve-all`, report, and full implementation SHA flow as Task 6, with `--attempt 2 --changed DIMENSION` and the resolved model. For a final plan, present the sanitized comparison and draft rationale to the user, stop, and wait; pass only the user's explicit classification through `--classify-attempt`, recording `operator_issued=true`, identity, and timestamp. Expected: one disclosed run; no self-classification, unregistered rerun, or second dimension.

- [ ] **Step 6: Repeat Steps 1-5 once for slot 3 only if allowed**

Slot 3 requires a completed, classified, non-qualifying slot 2 and a newly pre-registered single dimension. It is the last completed attempt. After slot 3, no model invocation is permitted regardless of outcome.

- [ ] **Step 7: Verify and commit every durable attempt record after approval**

After each slot, run the FU-4B verifier, show the redacted report/code diff, obtain approval, and commit only intended files. Record every full commit SHA. Expected terminal state is exactly one of: qualifying, unsafe, or exhausted.

---

### Task 8: Run the Point-in-Time Closure Ceremony and Amend Plan 9.87 Honestly

**Files:**
- Modify: `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`
- Modify: `docs/superpowers/plans/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: one mechanically verified terminal FU-4B state and any required contemporaneous operator disposition.
- Produces: a recorded triple gate or amended pair-plus-ledger gate, reconciled Task 8/DoD, roadmap, README, and report header.

- [ ] **Step 1: Re-run frozen-path and complete automated gates at ceremony HEAD**

Run:

```bash
git rev-parse HEAD
git diff --quiet 4bf20fffd9b067afa4db34d5ae021aca665f3acb..HEAD -- src/optimus tools/run_plan987_acpx_live_evidence.py
git diff --quiet bfcea0dab056bd42f793851ae042a214b24d4b64..HEAD -- src/optimus tools/run_plan987_acpx_live_evidence.py
python -m pytest tests/unit/tools/test_run_plan987_acpx_live_evidence.py tests/unit/tools/test_run_plan988_fu4b_live_evidence.py tests/unit/tools/test_verify_plan987_acpx_evidence.py -v
python -m ruff check .
git diff --check
```

Expected: full ceremony HEAD recorded; watched diffs clean; tests and Ruff pass.

- [ ] **Step 2A: For qualifying FU-4B, run the triple gate**

```bash
python tools/verify_plan987_acpx_evidence.py \
  --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md \
  --require fu4a --require fu4b --require fu5 \
  --max-completed-replan-attempts 3 \
  --max-completed-refusal-attempts 3
```

Expected: PASS. Record command, output, timestamp, operator, ceremony HEAD, selected full claim SHAs, ledger digest, and watched paths. Preserve the original Plan 9.87 Task 8 Step 5 and check the original FU-4B DoD only after this pass.

- [x] **Step 2B: For exhausted FU-4B, obtain contemporaneous disposition and run pair-plus-exhaustion gate**

First run:

```bash
python tools/verify_plan987_acpx_evidence.py --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md --check-fu4b-ledger-status exhausted --max-completed-replan-attempts 3
python tools/verify_plan987_acpx_evidence.py --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md --require fu4b --max-completed-replan-attempts 3
```

Expected: status PASS; FU-4B claim FAIL. Then request operator choice. If the operator does not contemporaneously accept open, stop with Plan 9.87 open and Plan 9.9 blocked.

If accepted, record identity, timestamp, ceremony HEAD, ledger digest, and sanitized rationale. Permanently rewrite Plan 9.87 Task 8 Step 5 to:

```bash
python tools/verify_plan987_acpx_evidence.py \
  --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md \
  --require fu4a --require fu5 \
  --check-fu4b-ledger-status exhausted \
  --max-completed-replan-attempts 3 \
  --max-completed-refusal-attempts 3
```

Run it. Expected: PASS while `--require fu4b` remains failing.

- [ ] **Step 2C: For unsafe FU-4B, obtain contemporaneous disposition and run pair-plus-unsafe gate**

Run `--check-fu4b-ledger-status unsafe` and record PASS, then request operator choice. Without accepted-open sign-off, stop and create a separately approved remediation plan before Plan 9.9.

If accepted, use the Step 2B durable command with `unsafe` replacing `exhausted`. Create roadmap follow-up `P9.88-FU-1: Unsafe FU-4B final-plan safety remediation` with exact finding, locators, owner, and acceptance criteria. Expected: pair-plus-unsafe gate PASS and `--require fu4b` FAIL.

- [x] **Step 3: Reconcile Plan 9.87 Task 8 and Definition of Done**

For Outcome A, mark Steps 5-8 and original FU-4B evidence claims only after the triple pass. For Outcomes B/C, rewrite rather than check the original FU-4B DoD as accepted-open, rewrite the separate-table DoD to require qualifying FU-4A/FU-5 tables plus the FU-4B terminal ledger/sign-off, and state the exact amended Step 5 reason. Never represent accepted-open as qualifying evidence.

**Result (Outcome B):** Plan 9.87 Task 8 Step 5 permanently uses the pair-plus-exhaustion command; FU-4B DoD rewritten as accepted-open; separate-table DoD rewritten; ceremony cited.

- [x] **Step 4: Update roadmap, README, and report status header**

Record Plan 9.87 closed with FU-4A/FU-5 proven and FU-4B either proven or accepted-open. Mark Plan 9.88 closed with its exact disposition and place it before Plan 9.9 in Recommended Sequence. Replace the report header sentence `Do not treat FU-4B as closure evidence.` with the exact proven or accepted-open status and ceremony reference. Preserve Plan 11, FU-6, and P9.87-FU-1 exclusions.

**Result (Outcome B):** Report header, README, roadmap statuses, and Recommended Sequence updated for accepted-open closure; Plan 9.88 precedes Plan 9.9.

- [x] **Step 5: Verify cross-document consistency**

Run:

```bash
rg -n "Plan 9\.87|Plan 9\.88|FU-4A|FU-4B|FU-5|P9\.85-FU-6|P9\.87-FU-1|P9\.88-FU-1|Plan 9\.9|Plan 11|Do not treat FU-4B" \
  docs/superpowers/plans/2026-07-01-phase-1-roadmap.md \
  docs/superpowers/plans/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md \
  reports/plan-9-87-model-replanning-refusal-acpx-evidence.md README.md
git diff --check
```

Expected: status language agrees; obsolete `Do not treat FU-4B` text is absent; diff check exits 0.

- [ ] **Step 6: Review closure artifacts and commit only after explicit approval**

Show the exact four-file diff plus ceremony output. After approval only:

```bash
git add \
  reports/plan-9-87-model-replanning-refusal-acpx-evidence.md \
  docs/superpowers/plans/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md \
  docs/superpowers/plans/2026-07-01-phase-1-roadmap.md README.md
git diff --cached --name-status
git diff --cached --check
git commit -m "Close Plan 9.87 through Plan 9.88 evidence"
git rev-parse HEAD
```

Expected: commit contains only the four closure artifacts and returns a recorded full SHA.

---

### Task 9: Run Final Release-Quality Gates and Record Plan 9.88 Completion

**Files:**
- Modify: `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md` only if final command output is not already recorded.

**Interfaces:**
- Consumes: committed closure disposition.
- Produces: final reproducible verification record without reopening the selected disposition.

- [ ] **Step 1: Run full test and coverage gates**

Run:

```bash
python -m pytest
python -m pytest --cov=src/optimus --cov-report=term-missing --cov-fail-under=80
python -m ruff check .
git diff --check
```

Expected: tests PASS; aggregate production coverage is at least 80%; Ruff and diff check exit 0. Report any live-tier test that is unavailable rather than substituting a fake.

- [ ] **Step 2: Re-run the durable closure command exactly as amended**

Outcome A reruns the triple gate. Outcome B reruns the pair plus `--check-fu4b-ledger-status exhausted`. Outcome C reruns the pair plus `--check-fu4b-ledger-status unsafe`.

Expected: PASS at final HEAD. For B/C, separately rerun `--require fu4b` and record the expected failure; accepted-open must never become a qualifying pass.

- [ ] **Step 3: Confirm scope and frozen paths**

Run:

```bash
git diff --quiet 4bf20fffd9b067afa4db34d5ae021aca665f3acb..HEAD -- src/optimus tools/run_plan987_acpx_live_evidence.py
git diff --quiet bfcea0dab056bd42f793851ae042a214b24d4b64..HEAD -- src/optimus tools/run_plan987_acpx_live_evidence.py
git status --short
```

Expected: both watched diffs exit 0. Worktree contains no unintended tracked changes or raw evidence artifacts.

- [ ] **Step 4: Commit a final report-only verification record only if needed and approved**

If Task 8 already recorded the final command output, do not create an empty or redundant commit. Otherwise show the report-only diff and request approval, then:

```bash
git add reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
git diff --cached --check
git commit -m "Record final Plan 9.88 closure verification"
git rev-parse HEAD
```

Expected: optional report-only commit succeeds and its full SHA is recorded.

---

## Deferred Follow-Ups

### P9.87-FU-1: Mechanical current-raw-evidence grounding guard (carried forward, unresolved)

**Status:** Remains open. Plan 9.88 did not resolve this follow-up.

**Trigger:** A content-correct FU-5 final plan or later evidence shows exact policy bytes can pass through observations despite the prompt prohibition.

**Acceptance criteria:** Define mechanical provenance between final WRITE content and current-turn raw ranges without logging source bodies or silently absorbing Plan 11. This does not block Plan 9.87 unless the observed final plan is unsafe.

**Note:** The FU-5 qualifying refusal never reached a content-correct final plan, so the trigger has not fired, but the guard remains unimplemented. Plan 11 is unchanged and out of scope; `P9.87-FU-1` acceptance criteria must not silently absorb it.

### P9.85-FU-6: Billable failed retry aggregation and unknown transport cost (carried forward, unresolved)

**Status:** Remains open. Plan 9.88's FU-4B lane did not touch retry-wrapper accounting.

### P9.88-FU-2: Ledger digest specification and verifier helper (new)

**Trigger:** An independently reproduced ceremony ledger digest has no pinned, independently reproducible computation method in-tree; no helper pins canonicalization.

**Acceptance criteria:** Pin a `ledger_digest()` helper in `tools/verify_plan987_acpx_evidence.py` with a fixed unit test; retroactively confirm or correct this ceremony's recorded digest (`9122c5c1b2978a8de515710df2c2cb38347bc7bd205e2837ac3b7b2bdf118b3d`) against it.

### P9.88-FU-3: Frozen-code read-range telemetry misattribution (new)

**Trigger:** Attempt 1 disclosed `planning_loop.py`'s `read_identities` (alphabetically sorted) vs `source_sha256s` / `read_byte_counts` (natural read order) misalignment, propagating into `build_evidence_summary_from_run()`.

**Acceptance criteria:** Fix ordering in `planning_loop.py`; add a regression test with non-alphabetical multi-file reads. Confirmed FU-4A and the qualifying FU-5 record are unexposed (single-file and zero-read respectively). Out of Plan 9.88 implementation scope to fix under the frozen-path constraint.

### Plan 11: Intelligent context selection and compression

**Status:** Unchanged and out of scope. Referenced only because `P9.87-FU-1`'s acceptance criteria must not silently absorb it. No `P9.88-FU-1` (unsafe-final remediation) was created — Outcome B closed on exhaustion, not unsafe.

## Definition of Done

- [x] Design and implementation plan were approved before implementation began.
- [x] `src/optimus/**` and `tools/run_plan987_acpx_live_evidence.py` stayed unchanged through the ceremony.
  Verified: `git diff --quiet 4bf20fffd9b067afa4db34d5ae021aca665f3acb..HEAD -- src/optimus tools/run_plan987_acpx_live_evidence.py` and `git diff --quiet bfcea0dab056bd42f793851ae042a214b24d4b64..HEAD -- src/optimus tools/run_plan987_acpx_live_evidence.py` both exit 0 at ceremony HEAD `fec114b7fc79da35ea399f4d66e22e776e6b76a3`.
- [x] The new helper used real `acpx` and did not implement an ACP client.
  Verified: `test_helper_source_does_not_implement_acp_protocol` (Task 2+); live slots used installed `acpx` 0.12.0 as the driver.
- [x] The extended schema, fixed predicate, prompt delta, baseline anchors, and per-file digests are mechanically checked.
- [x] No more than three completed attempts occurred; invalid runs are disclosed and uncounted.
  Verified: completed ledger slots `[1, 2, 3]`; stale attempt-2 re-registration and the attempt-3 `AgentSpawnError` spawn disclosed as infrastructure-invalid / uncounted (Global Constraint 7).
- [x] Every later attempt changed exactly one of wording, fixture, or model.
  Verified: `validate_next_attempt` accepted attempt 2 (`wording` only) and attempt 3 (`model` only) at pre-registration; task/fixture digests held constant across the model change.
- [x] Model changes used normal resolution, pricing, Gateway restart, and strict preflight.
  Verified attempt 3: `resolve_live_model` / registration lock to `anthropic/claude-haiku-4.5`, pre-existing OpenRouter pricing (no pricing PR; `gateway_restart_required=false`), `--strict-preflight-passed` recorded.
- [x] FU-4B qualifying selection requires `content-correct`; unknown is non-qualifying and unsafe terminates.
  Verified: `test_final_classification_is_explicit` and related classification/terminal tests (Task 2+).
- [x] FU-4B always watches `src/optimus`, the frozen helper, and the new helper; FU-4A/FU-5 watches remain unchanged.
  Verified: `test_claim_watched_paths_are_claim_specific` (Task 3+).
- [x] The three FU-5 rejection tests and swapped report hash prose are corrected.
- [x] The triple or amended pair-plus-ledger command passes at a recorded ceremony HEAD.
- [x] Accepted-open, if selected, has contemporaneous sign-off and never makes `--require fu4b` pass.
- [ ] Unsafe accepted-open creates `P9.88-FU-1` in the roadmap.
  N/A — Outcome B (exhausted + accepted-open), not Outcome C (unsafe).
- [x] Plan 9.87 Task 8, DoD, roadmap, README, report header, and sequence agree.
- [x] Plan 9.88 closes before Plan 9.9 begins.
- [x] Full tests, at least 80% coverage, Ruff, and diff checks pass or unavailable live tiers are explicitly reported.
  Verified (Task 9): `875 passed, 1 skipped`; coverage `85.54%` (≥80%); `python -m ruff check .` clean; `git diff --check` clean.

## Plan Self-Review Record

- **Spec coverage:** Every approved design section maps to Tasks 1-9, including the durable pair-plus-ledger amendment strengthening.
- **Schema consistency:** Task 1 pins all extension fields before Tasks 2-3 consume them. `changed_dimension` includes `model`; predicate and prompt identifiers are lane constants.
- **Evidence tiers:** Unit doubles never claim live proof; Tasks 6-7 require independently authored real `acpx`, real Gateway/model, and the real agent.
- **Anti-fishing:** Predicate, cap, slots, dimension changes, classifications, prompt, and terminal state are verifier-enforced, not prose-only.
- **Frozen evidence:** Existing full claim SHAs and exact watched paths are repeated in global, pre-live, ceremony, and final gates.
- **Approval gates:** Every commit step requires an exact diff, passing commands, and explicit user approval.
- **Placeholder scan:** No placeholder markers, unspecified error handling, or unnamed test step remains.


---
