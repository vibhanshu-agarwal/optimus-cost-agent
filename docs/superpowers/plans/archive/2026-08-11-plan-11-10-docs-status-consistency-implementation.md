# Plan 11.10 Docs Status Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Use
> superpowers:test-driven-development for every documentation-hygiene behavior. Steps use checkbox
> (`- [ ]`) syntax for tracking. Stop for review after every task; do not begin the next task until
> the reviewer records approval in the Plan 11.10 checkpoint log.

**Goal:** Make the consolidated Optimus open-work pool a complete table-first source for live
status and priority while preserving every approved immutable blob and repairing the living roadmap,
charter, plan-status, and plan-versioning documentation around it.

**Architecture:** Use hybrid status authority: editable plans own accurate document-level status,
while the pool owns current state for 13 immutable approval artifacts through one protected
path/digest/owner ledger. Strengthen the existing documentation test so exact entry-index coverage,
table-only priority, canonical feature status, promoted-item resolution, nested-status preservation,
and immutable-byte custody fail mechanically rather than relying on review memory.

**Tech Stack:** Markdown, Python 3.14, `pytest`, `hashlib`, `subprocess`, existing documentation-test
helpers, Git committed-blob inspection, `uv`, pre-commit, Ruff, Bandit, ast-grep, prompt-injection
guardrails, detect-secrets, and pytest-cov.

## Global Constraints

- The approved Gate 1 boundary is the living pool plus 26 covered documents: 13 immutable and 13
  editable. Do not re-derive, narrow, or widen that boundary.
- Gate 2 is approved subject to the binding 2026-08-11T13:36Z checkpoint corrections. Those
  corrections override the two affected factual passages and the uniform-priority statements in
  the design specification.
- Plans 9.85 and 9.87 have no current document-level status. Add one under each H1. Never rewrite
  their fenced examples or nested follow-up status lines.
- Plan 9.87's H1-owned status cites Plan 9.88 Task 8 Outcome B as primary closure evidence, records
  FU-4B as accepted-open (exhausted, not qualifying), and discloses that one commit step plus all ten
  Definition-of-Done items remain historically unchecked. Do not treat the roadmap as closure
  authority and do not tick those historical boxes.
- Preserve these operator-assigned priorities in the follow-up table: `P11-FU-8` = `LOW`,
  `P11-FU-11` = `HIGH`, `P11.7-FU-1` = `HIGH`, and `P11.5-FU-2` = `HIGH`. Every other row in every
  pool table starts `MEDIUM`.
- Priority exists only in pool table cells. No body `Priority:` label, body projection, priority
  bijection, or cross-table priority comparison is permitted.
- Preserve the accepted five-token status grammar. `Open`, `Promoted -> ...`, and
  `Partially implemented` are unresolved; `Closed` and `Reviewed disposition` are resolved.
- Every one of the current 42 `###` entries must be indexed exactly once. The invariant is a
  bijection, not a hard-coded count, so a future unindexed heading fails automatically.
- Mint only the approved unused identities `P11-FU-22` through `P11-FU-26`, in the order recorded
  in Task 3.
- Do not modify any file under `src/`, any dependency or lock file, any authoritative PDF, any
  evidence-handoff product document, or any test outside `tests/unit/docs/`.
- Do not rename the consolidated pool. Do not create retrospective `_v2` copies or rename the
  three dated Plan 11.7 amendments.
- Do not introduce wiki-link syntax into repository files.
- `tests/unit/docs/test_open_work_pool_hygiene.py` is the only test file authorized to change. The
  product-owned assertions named below remain textually and semantically unchanged.
- A task checkbox may be marked complete only after its stated verification command ran and
  passed. Narrative claims do not substitute for checkbox evidence.
- No task approval authorizes commit, push, PR, or merge. Stop before each of those actions unless
  separate explicit authorization is recorded.

## Gate 2 corrections carried into execution

### Correction 1: document status is heading-owned

The status parser added by Task 1 must ignore fenced code and associate every real `**Status:**`
line with its active Markdown heading stack. A plan-level status is a line owned directly by the
document H1 before the first H2. The charter is the explicit exception: its document status is owned
by `## Status and baseline`.

The editable status result is:

| Document | Required document-level status | Nested-status rule |
|---|---|---|
| Plan 9.85 | `Partially implemented`; 72 of 78 checkboxes complete | Preserve the real `P9.85-FU-6` status; ignore the fenced Plan 9.87 example while parsing. |
| Plan 9.87 | `Closed` through Plan 9.88 Task 8 Outcome B; FU-4B remains accepted-open (exhausted, not qualifying); one commit step plus all ten Definition-of-Done items were never ticked and remain historical record | Preserve the three statuses under `P9.87-FU-1`, `P9.85-FU-6`, and `Plan 11` byte-for-byte. |
| Plan 9.99 | `Partially implemented`; Tasks 1-6 landed and three final verification steps remain unchecked | Add under the H1; no nested status exists. |
| Plan 11.4 | `Closed`; merged by PR #91 | Add under the H1; no nested status exists. |
| Plan 11.9 | `Closed`; implemented through PRs #123 and #124 | Replace only the current H1-owned draft status. |

### Correction 2: preserve four operator priorities

The complete non-MEDIUM seed is exactly:

| Follow-up | Initial table priority |
|---|---|
| `P11-FU-8` | `LOW` |
| `P11-FU-11` | `HIGH` |
| `P11.7-FU-1` | `HIGH` |
| `P11.5-FU-2` | `HIGH` |

Every row not named in this table starts `MEDIUM`, including every Feature slice row, all four
settled companion rows, and both P9.96 historical tables. The existing mixed-case `Low` body value
normalizes to `LOW` in its table cell.

The nine body labels that are classifications rather than values retain their facts under a
`**Classification:**` label: `P11-FU-9`, `P11-FU-10`, `P11.7-FU-2`, `P11.7-FU-3`, `P11-FU-17`,
`P11-FU-18`, `P11-FU-19`, `P11-FU-20`, and `P11-FU-21`. The four value-bearing body labels are
removed after their values are seeded into table cells; adjacent raised/custody prose remains.

### Correction 3: deferred publication-plan custody

The excluded file
`docs/superpowers/plans/2026-08-05-mcp-gateway-architecture-amendment-publication-plan.md` remains
untouched. Its Task 10 Steps 1-7 are unchecked even though the four published PDFs hash-match
`verification.md` and PR #113 delivered the publication; its stale prose still says those PDFs await
approval. Task 11 Step 7 is correctly unchecked and must remain so.

**Owning roadmap entry:** **Publication-Plan Historical-State Reconciliation (Tracked, Not Yet
Scheduled).** This named entry owns only the excluded file's historical checkbox/status correction.
Pickup requires a separate reviewed scope and receives the next linear plan number available at
that time; Plan 11.10 neither edits the file nor allocates a new plan number for it.

## Protected immutable ledger

Task 1 copies this exact ledger into the test and the pool-side frozen-authority list. Digests are
uppercase SHA-256 of committed `HEAD` blobs, never hashes of CRLF-normalized working-tree reads.

| Path | SHA-256 | Live pool owner |
|---|---|---|
| `docs/superpowers/plans/2026-07-23-plan-10-2-p9-96-fu7-effective-row-display-provenance.md` | `4303D6AD5C44ED62A85A0509C8C87366505D4D470DD7BC4E0B4309BBE6E3C771` | P9.96 historical disposition row `P9.96-FU-7` |
| `docs/superpowers/plans/2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md` | `E66ECA48C588E7DB618D4850FDF0CEE901B4966BC0AB405E21C857AE6BE24F32` | settled entry `Plan 10.3 frozen-plan status correction (historical)` |
| `docs/superpowers/plans/2026-07-25-plan-11-1-p11-feat-gateway-core-implementation.md` | `254A6ACC56511BBCCEB8FC101B190F213FD65450327145C88979077D845D6D3E` | `P11-FEAT-GATEWAY-CORE` |
| `docs/superpowers/plans/2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md` | `8C96C9BFA67FB87F4A90FAE37169D27B437C5FD0CEE3AB2E6AB399E67B2874E5` | `P11-FEAT-GATEWAY-TOOLS` |
| `docs/superpowers/plans/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-implementation.md` | `0BAC146974984EA663B7A59802A1B5ED74F90EB682F855C0E05AAAB5B9A2C396` | `P11-FEAT-GATEWAY-COST-OBS` |
| `docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md` | `F52AD9A5A85DC50B0DFD3206B6BD09FD8FF0AE79B1A6049DF1017F978B1C462D` | `P11-FEAT-ZED-RESUME` |
| `docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md` | `79F3C92A852CB7EAA6108D8F0757F6612A0C908FE032CE7CFAB58B46721C06E6` | `P11-FEAT-ZED-RESUME` |
| `docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md` | `5BB327D88761AE329869B90866839D03F61EFF6AF0E5AE47F8D3D7551F849A4D` | `P11-FEAT-ZED-RESUME` |
| `docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md` | `106FD92B8E43F44A7115D7EDB1F9CF1E3EE643E4B6F594FA656FB4119A969B82` | `P11-FU-11` |
| `docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md` | `8B67FC187B92F0B66A9932AAAD9A013C476C19C165A1044F57F338245A01786C` | P9.96 historical summary/disposition |
| `docs/superpowers/specs/2026-07-26-plan-11-2-p11-feat-gateway-tools-design.md` | `2E679F105A250C7DF9F3757F72C43810B92810DD080EC6A4A985B778D163BFEC` | `P11-FEAT-GATEWAY-TOOLS` |
| `docs/superpowers/specs/2026-08-04-plan-11-7-retry-preflight-gate-design.md` | `EB34FA10148CE813A03E60E0770116ABA4AC9857E4DFBEE87E00C39BFDB0D392` | `P11-FU-11` |
| `docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md` | `AC48C0AEF1778D6EBE93005BC3993AE204F81A1C59CDC8DB17CFB7EDB6A040F8` | `P11-FEAT-GATEWAY-MCP` |

Every pool list item uses the exact marker sentence:

> Frozen approval bytes — live status is owned by the consolidated open-work pool.

## File responsibility map

| File | Responsibility |
|---|---|
| `tests/unit/docs/test_open_work_pool_hygiene.py` | Immutable-blob and marker guards; fence-aware status ownership; exact entry-index bijection; table-only priority validation; feature status and promoted resolution; roadmap, charter, and versioning assertions. |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Frozen-authority list, complete indexes, five stable IDs, five table Priority columns, canonical feature status, promoted legend, settled companion table, and current immutable-plan state. |
| `docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md` | Add an H1-owned partial status; preserve fenced and nested statuses. |
| `docs/superpowers/plans/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md` | Add an H1-owned closed status; preserve all three nested statuses. |
| `docs/superpowers/plans/2026-07-22-plan-9-99-credential-uri-security-snapshot-canonicalization.md` | Add the missing H1-owned partial status. |
| `docs/superpowers/plans/2026-07-28-plan-11-4-gateway-core-migration.md` | Add the missing H1-owned closed status. |
| `docs/superpowers/plans/2026-08-08-plan-11-9-p11-7-fu-1-gateway-timeout-implementation.md` | Replace the H1-owned draft status with PR #123/#124 closure. |
| `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` | Add a compact Plan 11.1-11.9 execution snapshot and point to the pool for item-level state. |
| `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md` | Record ratification, current sub-plan mapping including 11.3/11.9, the pool authority pointer, and numbering language consistent with the forward rule. |
| `AGENTS.md` | Define forward-only same-plan `_vN` files, immutable prior versions, live-pool pointers, and linear plan allocation. |
| `README.md` | Audit only. Change nothing unless its current-state claim is demonstrably false and a reviewed amendment authorizes the edit. |

The Gate 2 design specification and this implementation plan are Plan 11.10 planning artifacts.
No other covered document is expected to change.

## Test interfaces to establish

Task 1 adds fence-aware heading ownership and immutable committed-blob helpers. Task 3 consumes the
existing `_entry_sections` and `_status_token` interfaces and introduces table parsers. Task 4
consumes those table parsers for feature and resolution checks. Use these stable interfaces:

```python
def _status_lines_by_owner(text: str) -> tuple[tuple[tuple[str, ...], str], ...]: ...
def _document_status(text: str) -> str: ...
def _head_blob_sha256(relative_path: str) -> str: ...
def _markdown_tables(
    text: str,
) -> tuple[tuple[tuple[str, int], tuple[str, ...], tuple[dict[str, str], ...]], ...]: ...
def _fu_index_rows(text: str) -> dict[str, tuple[str, str]]: ...
def _settled_index_rows(text: str) -> dict[str, str]: ...
def _resolution(status: str) -> str: ...
```

`_status_lines_by_owner` excludes fenced code. `_document_status` accepts exactly one status owned
directly by the H1. `_fu_index_rows` deliberately returns `(item, status)` only: Priority is parsed
and validated separately and is not part of any projection tuple.

## Mandatory per-task verification gate

Run the narrow RED and GREEN commands named inside each task first. Before claiming any task ready
for review, run every command in this section from repository root. Capture return codes directly;
do not inspect a pipeline's final-element status as a substitute for the command under test.

```bash
uv run pre-commit run trailing-whitespace --all-files
uv run pre-commit run check-yaml --all-files
uv run pre-commit run check-toml --all-files
uv run pre-commit run check-added-large-files --all-files
uv run ruff check .
uv run bandit -q -r src -c pyproject.toml
uv run pre-commit run optimus-ast-grep --all-files
uv run python -m optimus.guardrails.prompt_injection
uv run detect-secrets-hook --baseline .secrets.baseline src
uv run pytest --cov=optimus --cov-branch --cov-report=term-missing -v
git diff --check
git status --short --branch
```

At each review stop, also prove the boundary and committed blobs:

```bash
git diff --name-only
git diff --exit-code -- \
  docs/superpowers/plans/2026-07-23-plan-10-2-p9-96-fu7-effective-row-display-provenance.md \
  docs/superpowers/plans/2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md \
  docs/superpowers/plans/2026-07-25-plan-11-1-p11-feat-gateway-core-implementation.md \
  docs/superpowers/plans/2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md \
  docs/superpowers/plans/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-implementation.md \
  docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md \
  docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md \
  docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md \
  docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md \
  docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md \
  docs/superpowers/specs/2026-07-26-plan-11-2-p11-feat-gateway-tools-design.md \
  docs/superpowers/specs/2026-08-04-plan-11-7-retry-preflight-gate-design.md \
  docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md
git diff --exit-code origin/main...HEAD -- \
  docs/superpowers/plans/2026-07-23-plan-10-2-p9-96-fu7-effective-row-display-provenance.md \
  docs/superpowers/plans/2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md \
  docs/superpowers/plans/2026-07-25-plan-11-1-p11-feat-gateway-core-implementation.md \
  docs/superpowers/plans/2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md \
  docs/superpowers/plans/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-implementation.md \
  docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md \
  docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md \
  docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md \
  docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md \
  docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md \
  docs/superpowers/specs/2026-07-26-plan-11-2-p11-feat-gateway-tools-design.md \
  docs/superpowers/specs/2026-08-04-plan-11-7-retry-preflight-gate-design.md \
  docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md
```

Any non-empty immutable diff, digest mismatch, product-owned assertion failure, or new required edit
outside the file map stops execution and requires a reviewed amendment.

---

### Task 1: Protect frozen artifacts and repair document-level status

**Files:**

- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md:23`
- Modify: `docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md:1`
- Modify: `docs/superpowers/plans/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md:1`
- Modify: `docs/superpowers/plans/2026-07-22-plan-9-99-credential-uri-security-snapshot-canonicalization.md:1`
- Modify: `docs/superpowers/plans/2026-07-28-plan-11-4-gateway-core-migration.md:1`
- Modify: `docs/superpowers/plans/2026-08-08-plan-11-9-p11-7-fu-1-gateway-timeout-implementation.md:1`

**Interfaces:**

- Consumes: the protected immutable ledger and exact marker sentence in this plan.
- Produces: `_status_lines_by_owner`, `_document_status`, `_head_blob_sha256`, and a pool-side
  frozen-authority section used by the remaining tasks.

- [x] **Step 1: Add fence-aware status-ownership and committed-blob tests.**

  Add `hashlib`, the 13-entry `PROTECTED_BLOB_SHA256` mapping, the exact
  `FROZEN_AUTHORITY_MARKER`, and parsers that toggle on Markdown fences before updating a heading
  stack. The tests must compare `hashlib.sha256(git show HEAD:<path>).hexdigest().upper()` with the
  protected mapping and parse the pool list into an exact path/digest set.

  ```python
  FROZEN_AUTHORITY_MARKER = (
      "Frozen approval bytes — live status is owned by the consolidated open-work pool."
  )

  def _head_blob_sha256(relative_path: str) -> str:
      result = subprocess.run(
          ["git", "show", f"HEAD:{relative_path}"],
          cwd=REPO_ROOT,
          check=True,
          capture_output=True,
      )
      return hashlib.sha256(result.stdout).hexdigest().upper()

  def _status_lines_by_owner(text: str) -> tuple[tuple[tuple[str, ...], str], ...]:
      owners: list[tuple[tuple[str, ...], str]] = []
      stack: list[str] = []
      in_fence = False
      for line in text.splitlines():
          if line.lstrip().startswith("```"):
              in_fence = not in_fence
              continue
          if in_fence:
              continue
          heading = re.match(r"^(?P<marks>#{1,6}) (?P<title>.+)$", line)
          if heading is not None:
              level = len(heading.group("marks"))
              stack[level - 1 :] = [heading.group("title")]
              continue
          status = STATUS_LINE_RE.fullmatch(line)
          if status is not None:
              owners.append((tuple(stack), status.group("value").strip()))
      return tuple(owners)
  ```

  Add exact nested-status baselines for Plans 9.85 and 9.87. For Plan 9.85, only the real
  `P9.85-FU-6` status is nested; the fenced Plan 9.87 example must not parse. For Plan 9.87, assert
  the three nested owners and full values are unchanged. Add expected H1-owned tokens for all five
  editable plan files.

- [x] **Step 2: Run the focused tests and capture RED.**

  ```bash
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py \
    -k "immutable or document_level or nested_status" -vv
  ```

  Expected: FAIL because the pool lacks the complete 13-row marker list, Plans 9.85/9.87/9.99/11.4
  lack an H1-owned status, and Plan 11.9 still has an H1-owned draft status. The 13 `HEAD` digest
  checks themselves must pass.

- [x] **Step 3: Add the frozen-authority list and make only document-level status repairs.**

  Add a non-table pool section listing each protected path, digest, exact marker, and live owner
  from the ledger. Expand `How to use this document` so approval-time status inside a listed frozen
  artifact is historical and the linked pool row is live authority.

  Add H1-owned status prose to Plans 9.85, 9.87, 9.99, and 11.4 using the matrix above. Plan 9.87's
  line must name Plan 9.88 Task 8 Outcome B, preserve FU-4B as accepted-open (exhausted, not
  qualifying), and state that the one commit step and ten Definition-of-Done items were never
  ticked and remain historical record. Replace only Plan 11.9's H1-owned draft status. Do not edit
  line 789's fenced example in Plan 9.85, its `P9.85-FU-6` status, any of Plan 9.87's three nested
  status lines, or any historical Plan 9.87 checkbox.

- [x] **Step 4: Run GREEN, the complete docs test, and the mandatory per-task gate.**

  ```bash
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py \
    -k "immutable or document_level or nested_status" -vv
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py -v
  uv run pytest tests/unit/docs -q
  ```

  Then run every command under **Mandatory per-task verification gate** and both immutable diff
  commands. Expected: all pass; no immutable path appears in either working-tree or branch diff.

- [x] **Step 5: Stop for Task 1 review.**

  Write `.superpowers/sdd/gate-task-1-report.md` with RED/GREEN output, full-gate return codes,
  changed paths, immutable-digest results, and explicit nested-status preservation evidence. Do not
  stage or commit. After reviewer approval, proceed only if execution of Task 2 is authorized.

---

### Task 2: Repair roadmap and charter freshness

**Files:**

- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md:1006`
- Modify: `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md:3`

**Interfaces:**

- Consumes: the pool as live per-item authority and the verified Plan 11 status matrix below.
- Produces: compact roadmap/charter summaries that name every Plan 11.1-11.9 lane without becoming
  duplicate item-level status stores.

  | Plan | Summary state/evidence |
  |---|---|
  | 11.1 | Closed, PR #85 |
  | 11.2 | Closed, PR #88 |
  | 11.3 | Closed, PR #88 |
  | 11.4 | Closed, PR #91 |
  | 11.5 | Closed, PR #95 |
  | 11.6 | Merged, PR #97 |
  | 11.7 | Partially implemented and blocked |
  | 11.8 | Partially implemented, 27 of 46 checks, PRs #116/#118 |
  | 11.9 | Closed, PRs #123/#124 |

- [x] **Step 1: Add narrow roadmap and charter freshness tests.**

  Define path constants for the roadmap and charter. Assert both point to the consolidated pool;
  the Plan 11 section names `Plan 11.1` through `Plan 11.9`; the summary contains the matrix's state
  and PR/count evidence; the charter status starts with `Ratified`; and the stale draft/no-subplan
  sentence is absent.

  ```python
  PLAN_11_SUMMARY_EVIDENCE = {
      "Plan 11.1": ("Closed", "PR #85"),
      "Plan 11.2": ("Closed", "PR #88"),
      "Plan 11.3": ("Closed", "PR #88"),
      "Plan 11.4": ("Closed", "PR #91"),
      "Plan 11.5": ("Closed", "PR #95"),
      "Plan 11.6": ("Merged", "PR #97"),
      "Plan 11.7": ("Partially implemented", "blocked"),
      "Plan 11.8": ("Partially implemented", "27 of 46", "PR #116", "PR #118"),
      "Plan 11.9": ("Closed", "PR #123", "PR #124"),
  }
  ```

- [x] **Step 2: Run the focused test and capture RED.**

  ```bash
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py \
    -k "roadmap or charter" -vv
  ```

  Expected: FAIL because Plans 11.3 and 11.9 are absent and the charter still claims draft/no
  sub-plan authority.

- [x] **Step 3: Add compact Plan 11 summaries and ratified charter status.**

  Add one concise execution-snapshot table or list to the roadmap's Plan 11 section using the exact
  matrix. Keep the existing detailed Zed and MCP boundary prose. Add a direct link telling readers
  that the consolidated pool owns per-item live state.

  In the charter, replace the false status with ratified/current wording, update the revised
  sub-plan map so Plan 11.3 is represented with the Gateway work it completed and Plan 11.9 with
  the Zed-resume follow-up it completed, and point to the pool for item-level status. Do not copy
  all follow-up rows into either document.

- [x] **Step 4: Run GREEN and the mandatory per-task gate.**

  ```bash
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py \
    -k "roadmap or charter" -vv
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py -v
  uv run pytest tests/unit/docs -q
  ```

  Then run every mandatory per-task command and both immutable diff checks.

- [x] **Step 5: Stop for Task 2 review.**

  Write `.superpowers/sdd/gate-task-2-report.md` with the exact summary matrix, RED/GREEN evidence,
  full-gate results, and diff boundary. Do not stage or commit.

---

### Task 3: Enforce exact entry coverage and table-only priority

**Files:**

- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md:44`

**Interfaces:**

- Consumes: `_entry_sections`, `_status_token`, and the existing stable-ID projection.
- Produces: six-column follow-up rows, a settled-index parser, a collision-safe generic pool-table
  parser keyed by `(H2 title, ordinal within that H2)`, exact index/heading bijection, and
  independent priority validation.

- [x] **Step 1: Write the failing exact-coverage and priority tests.**

  Update `FU_INDEX_ROW_RE` to parse six columns in this order:

  ```python
  FU_INDEX_ROW_RE = re.compile(
      rf"^\|\s*`(?P<identity>{FU_ID_BODY})`\s*\|\s*(?P<item>[^|]+?)\s*\|"
      r"\s*(?P<status>.*?)\s*\|\s*(?P<priority>HIGH|MEDIUM|LOW)\s*\|"
      r"\s*(?P<owner>.*?)\s*\|\s*(?P<evidence>.*?)\s*\|\s*$",
      re.MULTILINE,
  )
  ```

  Keep `_fu_index_rows` returning only `(item, status)`. Add `_settled_index_rows` keyed by exact
  heading title. `_markdown_tables` must give every table an identity of `(nearest H2 title,
  ordinal within that H2)`, retain the parsed header alongside its rows, reject duplicate
  identities, and assert that exactly five tables were discovered. It must not use H2 title alone:
  both P9.96 tables share one H2 and must remain independently validated. Replace the
  `len(entries) >= 41` floor with these assertions:

  ```python
  indexed_headings = {
      f"{identity}: {item}" for identity, (item, _status) in _fu_index_rows(pool_text).items()
  }
  settled_headings = set(_settled_index_rows(pool_text))
  assert indexed_headings.isdisjoint(settled_headings)
  assert indexed_headings | settled_headings == set(entries)
  assert all(_status_token(body) for body in entries.values())
  ```

  The settled parser must also compare each row's status to `_status_token(entries[heading])`.
  Generic table validation first asserts `len(tables) == 5`, then asserts every discovered pool
  table has exactly one `Priority` header, every row has the same cell count as its own header, and
  each Priority cell is one of `HIGH`, `MEDIUM`, `LOW`. Add a separate seed assertion:

  ```python
  EXPECTED_NON_MEDIUM_PRIORITIES = {
      "P11-FU-8": "LOW",
      "P11-FU-11": "HIGH",
      "P11.7-FU-1": "HIGH",
      "P11.5-FU-2": "HIGH",
  }
  ```

  Assert these are the only non-MEDIUM follow-up priorities and every row outside the follow-up
  table is `MEDIUM`. Assert no non-table line matches `Priority:`. Do not add Priority to the FU
  status projection tuple or compare repeated P9.96 row priorities with one another.

- [x] **Step 2: Run the focused tests and capture RED.**

  ```bash
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py \
    -k "canonical_status or exact_projection or settled or priority" -vv
  ```

  Expected: FAIL because five headings lack IDs, four settled headings lack rows, all existing table
  schemas lack Priority, and 13 body lines still use a `Priority:` label.

- [x] **Step 3: Mint the five approved IDs and make the two entry indexes bijective.**

  Rename only these headings and add their status-projection rows to the main follow-up index:

  | ID | Existing heading title |
  |---|---|
  | `P11-FU-22` | Durable effect-aware MCP indeterminate-call custody |
  | `P11-FU-23` | Durable client-MCP descriptor-surface pinning and named tool allowlists |
  | `P11-FU-24` | Client-MCP durable HTTP/SSE trust relaxation |
  | `P11-FU-25` | Authenticated client-owned MCP upstream evidence |
  | `P11-FU-26` | Plan 11.8 Windows `WinError 10053` MCP test flake |

  Add `## Settled risks and historical entries` with `Item | Status | Priority | Disposition /
  evidence` and exactly these four rows: the Plan 11.7 accepted risk, Plan 10.3 frozen-plan status
  correction, historical `uv.lock` missing-direct-dependencies entry, and historical
  `SurfaceAuditError` frozen-dataclass entry. Keep their detailed `###` headings in place.

- [x] **Step 4: Add one Priority column to all five tables and remove body priority labels.**

  The final table set is Feature slices, Follow-up status index, Settled risks and historical
  entries, P9.96 historical summary, and P9.96 historical disposition. Insert Priority once in
  every header and row. Seed only the four approved exceptions; use `MEDIUM` everywhere else.

  Convert the nine classification labels named in Correction 2 to `**Classification:**` without
  changing their descriptive text. Remove the four value-bearing body labels after placing their
  values in the follow-up cells. Preserve `P11-FU-11`'s custody-gap sentence and all raised-by
  provenance.

- [x] **Step 5: Run GREEN and the mandatory per-task gate.**

  ```bash
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py \
    -k "canonical_status or exact_projection or settled or priority" -vv
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py -v
  uv run pytest tests/unit/docs -q
  ```

  Confirm the exact bijection has no numeric floor and that product-owned tests remain unchanged.
  Then run every mandatory per-task command and both immutable diff checks.

- [x] **Step 6: Stop for Task 3 review.**

  Write `.superpowers/sdd/gate-task-3-report.md` containing the indexed-heading set, settled set,
  four non-MEDIUM values, proof that all other rows are MEDIUM, proof that no body `Priority:` label
  remains, RED/GREEN evidence, and full-gate results. Do not stage or commit.

---

### Task 4: Canonicalize feature status and promoted resolution

**Files:**

- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md:44`

**Interfaces:**

- Consumes: Task 3's generic table parser and existing exact detail-entry status projection.
- Produces: canonical Feature `Status`, unconstrained `Scope detail`, and an explicit resolution
  classifier that treats every promoted row as unresolved without changing its token.

- [x] **Step 1: Write failing Feature-status and promoted-resolution tests.**

  Parse the Feature slices table by header and assert its header is exactly
  `Identity | Status | Priority | Scope detail`. Enforce this matrix:

  ```python
  EXPECTED_FEATURE_STATUS = {
      "P11-FEAT-GATEWAY-CORE": "Closed",
      "P11-FEAT-GATEWAY-TOOLS": "Closed",
      "P11-FEAT-GATEWAY-COST-OBS": "Closed",
      "P11-FEAT-GATEWAY-MCP": "Partially implemented",
      "P11-FEAT-ZED-RESUME": "Partially implemented",
      "P11-FEAT-REGISTRY": "Open",
      "P11-FEAT-IDE": "Open",
      "Plan 12": "Open",
  }
  ```

  Add an explicit classifier and test every detail/index status:

  ```python
  def _resolution(status: str) -> str:
      if status in {"Closed", "Reviewed disposition"}:
          return "resolved"
      if status in {"Open", "Partially implemented"} or status.startswith("Promoted -> "):
          return "unresolved"
      raise AssertionError(status)
  ```

  Assert both `P9.8-FU-5` and `P11-FU-1` retain their exact `Promoted -> [Plan 11.7](...)` token and
  classify unresolved. Preserve the existing target-resolution test beneath `PLANS_ROOT`.

- [x] **Step 2: Run the focused tests and capture RED.**

  ```bash
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py \
    -k "feature_status or promoted or gateway_mcp_row" -vv
  ```

  Expected: FAIL because Feature uses a free-prose `State` cell rather than a canonical `Status`
  cell. The existing promoted-target path checks and Gateway MCP factual assertions must still pass.

- [x] **Step 3: Reshape Feature rows and add the adjacent closure legend.**

  Rename `State` to `Status`, insert the canonical token from the matrix, and move all existing
  state prose into `Scope detail` without dropping evidence. Keep each row's Task/PR/blocker facts.
  In particular, preserve Plan 11.8's computed `27 of 46`, PR #116, PR #118, both plan links, and the
  repository-wide absence of the phrase prohibited by
  `test_gateway_mcp_row_records_the_real_plan_118_boundary`.

  Beside the entry indexes, state the exact closure partition: unresolved is `Open`,
  `Promoted -> ...`, or `Partially implemented`; resolved is `Closed` or
  `Reviewed disposition`. Do not add a binary column or change promoted tokens.

- [x] **Step 4: Run GREEN and the mandatory per-task gate.**

  ```bash
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py \
    -k "feature_status or promoted or gateway_mcp_row" -vv
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py -v
  uv run pytest tests/unit/docs -q
  ```

  Then run every mandatory per-task command and both immutable diff checks.

- [x] **Step 5: Stop for Task 4 review.**

  Write `.superpowers/sdd/gate-task-4-report.md` with the exact feature matrix, promoted tokens and
  resolution output, Gateway MCP boundary evidence, RED/GREEN evidence, and full-gate results. Do
  not stage or commit.

---

### Task 5: Establish forward-only plan versioning and linear numbering

**Files:**

- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Modify: `AGENTS.md:67`
- Modify: `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md:70`

**Interfaces:**

- Consumes: the accepted forward-only W4 ruling and the immutable Plan 11.7 ledger.
- Produces: one noncontradictory repository rule for same-plan versions and plan-number allocation.

- [x] **Step 1: Add failing governance-language tests.**

  Treat the following block as illustrative semantics, not exact required sentences:

  ```text
  XYZ.md -> XYZ_v2.md -> XYZ_v3.md
  going forward
  existing dated amendment documents are not retroactively renamed
  _v1 is immutable once _v2 exists
  consolidated pool points to the live version
  11.9 -> 11.10 -> 11.11
  interstitial allocations are forbidden
  N.M.1 is forbidden
  ```

  Implement the test with narrow anchor groups rather than whole-sentence equality: same-plan
  examples must contain `XYZ.md`, `XYZ_v2.md`, and `XYZ_v3.md`; immutability must relate `_v1` and
  `_v2`; live authority must relate the consolidated pool and live version; linear numbering must
  contain `11.9`, `11.10`, and `11.11` in order; forbidden shapes must include `9.975` and `N.M.1`.
  Assert the charter no longer says a two-decimal number such as 11.11 is invalid or requires a
  next-unused-single-decimal slot. Assert the three historical dated Plan 11.7 amendment paths still
  exist and remain covered by the immutable digest test. Task 5's report must state that these are
  semantic anchor groups and not exact-prose assertions.

- [x] **Step 2: Run the focused tests and capture RED.**

  ```bash
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py \
    -k "plan_versioning or linear_numbering" -vv
  ```

  Expected: FAIL because `AGENTS.md` has the old generic new-file rule and the charter explicitly
  rejects `11.11`.

- [x] **Step 3: Replace the forward rule and reconcile charter numbering prose.**

  In `AGENTS.md`, replace only the frozen-plan amendment bullet and add the linear numbering rule.
  Cite the unchanged evidence-handoff risk-bearing-slice v1/v2 pair as precedent. State that the
  rule is forward-only, prior versions become immutable when the next version exists, and the pool
  points to the live version. Preserve all existing dated Plan 11.7 artifacts and pins.

  In the charter, replace the conflicting single-decimal/two-decimal paragraph with the same linear
  semantics. Plan numbers remain scheduling labels; new independently schedulable work gets the
  next linear number, while revisions keep the existing plan number and increment `_vN`. Forbid
  interstitial insertions such as the historical 9.8/9.85/9.975 shape and nested `N.M.1` numbers.

- [x] **Step 4: Run GREEN and the mandatory per-task gate.**

  ```bash
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py \
    -k "plan_versioning or linear_numbering" -vv
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py -v
  uv run pytest tests/unit/docs -q
  ```

  Then run every mandatory per-task command and both immutable diff checks.

- [x] **Step 5: Stop for Task 5 review.**

  Write `.superpowers/sdd/gate-task-5-report.md` with the old/new rule diff, unchanged historical
  amendment paths/digests, RED/GREEN evidence, and full-gate results. Do not stage or commit.

---

### Task 6: Run the closing freshness, product-boundary, and release audit

**Files:**

- Audit: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Audit: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Audit: `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md`
- Audit: `README.md`
- Audit: `AGENTS.md`
- Audit: all paths shown by `git diff --name-only`

**Interfaces:**

- Consumes: all Task 1-5 tests and documentation outputs.
- Produces: final claim-to-evidence record; no new implementation behavior.

- [x] **Step 1: Prove the protected product tests are unchanged.**

  Compare the current test function bodies against `origin/main` for:

  ```text
  test_product_features_have_exactly_one_pool_owner
  test_a2a_ledger_reachability_blocker_is_resolved_and_design_is_owned
  test_a2a_ledger_plan_freezes_ordered_risk_slice_scope
  test_a2a_ledger_freezes_recipient_visibility_in_the_first_slice
  test_a2a_ledger_integrity_detection_is_a_first_slice_contract
  test_a2a_ledger_integrity_failure_is_loud_latched_and_non_retryable
  test_a2a_ledger_chain_break_recovery_and_rollback_residual_are_explicit
  test_new_pool_has_no_scheduling_plan_numbers
  test_new_pool_links_only_to_explicitly_product_owned_documents
  test_optimus_dependency_references_resolve_to_product_pool_without_status_custody
  ```

  Use `git diff origin/main -- tests/unit/docs/test_open_work_pool_hygiene.py` and inspect every
  hunk. Any semantic or textual change inside those functions is a scope breach and stops closure.

- [x] **Step 2: Audit all current-state documentation claims affected by Plan 11.10.**

  ```bash
  rg -n "Plan 11\.(1|2|3|4|5|6|7|8|9)|P11-FEAT-|P11-FU-|Priority:|Promoted ->|11\.11|single-decimal|two-decimal" \
    README.md AGENTS.md \
    docs/superpowers/plans/2026-07-01-phase-1-roadmap.md \
    docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md \
    docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md
  ```

  Verify every matching claim against the approved matrix and pool. `README.md` changes only if a
  false claim is found and a reviewed amendment authorizes that path. A newly discovered required
  edit outside the file map stops this task; it is not silently folded in.

- [x] **Step 3: Run focused documentation tests, all docs tests, and the complete mandatory gate.**

  ```bash
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py -v
  uv run pytest tests/unit/docs -q
  ```

  Then run every mandatory per-task command and both immutable diff checks one final time. Confirm
  aggregate production-code coverage remains at least 80% and Ruff is clean.

- [x] **Step 4: Record the exact final diff and deferred custody.**

  ```bash
  git diff --stat
  git diff --name-only
  git status --short --branch
  git diff --check
  ```

  Confirm the excluded publication plan is absent from the diff and its defect remains named under
  **Publication-Plan Historical-State Reconciliation (Tracked, Not Yet Scheduled)** in this plan.
  Confirm no `src/`, product-owned document, PDF, dependency, or lock file appears.

- [x] **Step 5: Stop for final implementation review.**

  Write `.superpowers/sdd/gate-task-6-report.md` with the claim-to-evidence matrix, full command
  outputs/return codes, immutable digests, product-function diff proof, documentation freshness
  disposition, deferred-custody pointer, and final path list. Do not stage, commit, push, open a PR,
  merge, or claim Plan 11.10 complete without the required final approval.

---

### Task 7: Make the closing-audit custody records durable

**Files:**

- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`

**Interfaces:**

- Consumes: the accepted Task 6 audit, the verified-free identity `P11-FU-27`, the existing exact
  entry/index bijection, and the frozen-authority section.
- Produces: tracked pool custody for the publication-plan historical-state reconciliation and the
  four historical numbering-rule dispositions.

- [x] **Step 1: Add failing durable-custody tests.**

  Assert that the frozen-authority section records all four historical numbering-rule documents in
  local bullet groups with their pin status: Plan 10.1 is in-scope/editable and deliberately
  unchanged; the Plan 11.5 design is pinned elsewhere at `5608AD55...`; the Plan 11.8 design is one
  of the 13 immutable artifacts; and the Plan 11.9 design is unpinned and outside the covered set.
  Assert that `P11-FU-27: Publication-Plan Historical-State Reconciliation` is a real `Open` detail
  entry, has the matching follow-up-index row, has `MEDIUM` priority, and cites the excluded
  publication plan, Task 10 Steps 1-7, Task 11 Step 7, `verification.md`, and PR #113.

- [x] **Step 2: Run the focused tests and capture RED.**

  ```bash
  uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py \
    -k "historical_numbering or publication_plan_custody" -vv
  ```

  Expected: FAIL because neither durable pool record exists.

- [x] **Step 3: Add the two durable pool records.**

  Add a clearly labelled bullet-only historical-numbering provenance subsection beneath
  `## Frozen approval bytes and live-status authority`; do not add a sixth pool table and do not
  edit any historical source document. Add `P11-FU-27` to the follow-up index with `Open` status and
  `MEDIUM` priority, then add its detailed entry with the exact publication-plan custody described
  in Step 1.

- [x] **Step 4: Run GREEN and the complete mandatory gate.**

  Run the focused selector, the complete hygiene file, all docs tests, every command under
  **Mandatory per-task verification gate**, both immutable diff checks, and the protected-product
  function comparison.

- [x] **Step 5: Stop for Task 7 review.**

  Write `.superpowers/sdd/gate-task-7-report.md` with RED/GREEN evidence, the exact new row/entry,
  all four durable dispositions, full-gate results, immutable evidence, and final path inventory.
  Do not stage, commit, push, or open a PR.

## Definition of Done

- [x] The living pool plus settled 26-document boundary is unchanged.
- [x] All 13 protected `HEAD` blobs match the approved SHA-256 ledger and have no working-tree or
  branch diff.
- [x] Plans 9.85 and 9.87 have H1-owned status; their fenced and nested statuses are unchanged.
- [x] Plans 9.99 and 11.4 have accurate H1-owned status; Plan 11.9 records PR #123/#124 closure.
- [x] Roadmap and charter name Plans 11.1-11.9, record the approved summary matrix, and defer
  per-item live state to the pool.
- [x] Every `###` entry maps to exactly one follow-up or settled row, and every such row maps back
  to one heading, without a magic count.
- [x] The five formerly ID-less entries own `P11-FU-22` through `P11-FU-26` in the approved order.
- [x] All five pool tables have exactly one Priority column; the four preserved non-MEDIUM values
  are exact; all other rows are MEDIUM; no body `Priority:` label remains.
- [x] Feature status is canonical; its detailed evidence remains in Scope detail; the Plan 11.8
  27-of-46 and PR #116/#118 boundary remains enforced.
- [x] Promoted rows remain exact existing tokens and classify unresolved through the accepted
  five-token closure partition.
- [x] The four settled non-FU entries appear in the clearly labelled companion table.
- [x] `AGENTS.md` and the charter agree on forward-only `_vN` amendment files and linear plan
  numbering; historical dated amendments remain untouched.
- [x] The publication-plan defect has named pool custody under `P11-FU-27` and the excluded file remains
  untouched.
- [x] The four historical numbering-rule documents have durable pool-side provenance and pin-status
  dispositions; no historical source is edited.
- [x] Protected product tests are unchanged; all focused, documentation, full-suite, coverage,
  pre-commit, Ruff, Bandit, ast-grep, prompt-injection, detect-secrets, and diff gates pass.
- [x] No unauthorized commit, push, PR, merge, or completion claim has occurred.

## Execution handoff

This plan is a Gate 3 artifact only. It does not authorize Task 1. After Gate 3 approval, execute one
task at a time with the required superpowers workflow, write the task gate report to disk, and stop
for review before proceeding.
