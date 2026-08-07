# Open-Work Pool Status Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this
> plan inline and task-by-task. The operator explicitly selected sequential inline execution because
> Tasks 2-3 consume Task 1's parser state; do not dispatch this plan across fresh subagents. Use
> `superpowers:test-driven-development` for every documentation-hygiene behavior change. Steps use
> checkbox (`- [ ]`) syntax for tracking. Do not mark a checkbox complete until its stated
> verification command has actually passed.

**Status:** Approved by the operator on 2026-08-07 for sequential inline execution, with independent
review at every task boundary.

**Goal:** Make the consolidated Optimus open-work pool mechanically self-consistent by normalizing
all entry statuses, adding a complete stable-ID FU index, correcting verified stale facts and broken
links, and enforcing those invariants with documentation unit tests.

**Architecture:** Keep the detailed pool entries authoritative and make the new index a mechanically
checked projection keyed only by stable FU IDs. Parse Markdown sections and links in the existing
documentation hygiene test, then use TDD to normalize the pool and update the living Plan 11.8
status without changing any frozen artifact. Feature-table state remains free-form by deliberate
design; targeted factual assertions and blanket link resolution provide partial protection while
the PR records the remaining semantic anti-drift gap.

**Tech Stack:** Python 3.14 standard library (`re`, `pathlib`, `urllib.parse`, `collections`),
pytest, Ruff, Markdown files, Git/GitHub CLI, and PowerShell only for Windows SHA-256 verification.

## Global Constraints

- Execute in the existing worktree on `agent/codex/pool-status-normalization`, whose merge base with
  `origin/main` is `364fc9d6bc122ace3e7c9fc5042b7b2c094827cf` (merged PR #120).
- The approved design is
  `docs/superpowers/specs/2026-08-07-open-work-pool-status-normalization-design.md` at commit
  `3b4dd3c9e2beeda54df900889d35b2ddcd8b5894`, Git blob
  `c4d6b1c089762942a200f2acd595a04b899b78b3`, with frozen design-body SHA-256
  `4ff6cc2591e2fe446d422847206769cfa96e20fad1356cb37947824a82525446`.
- Scope contains exactly one test file and living documentation: the consolidated pool, the living
  Plan 11.8 implementation-plan status, this plan, and the approved design already committed on the
  branch. Do not modify production source, dependencies, lockfiles, authoritative PDFs, evidence
  artifacts, README, or roadmap unless the final freshness audit proves a directly affected
  current-state claim false and the operator approves that scope change.
- The Plan 11.8 implementation plan is the only previously existing plan file this work may edit.
  Its pre-edit Git blob is `5bcdc0b9e95de94867517d8732f04b3f093880a5`; its pre-edit SHA-256 is
  `09d5b257ac52556c15ae10cd9f1e222251400102d13f05a288de49bc6ea16cc5`.
- Preserve the frozen Plan 11.8 design, Plan 11.5 plan, Plan 11.7 parent plan and amendments, and
  Plan 10.3 plan byte-for-byte. Their exact baseline identities are recorded in Task 0.
- Every `###` pool entry begins with exactly one of `Open`, `Promoted -> [target](plan-link)`,
  `Partially implemented`, `Closed`, or `Reviewed disposition`, followed by `.` or `:`.
- `Partially implemented` requires merged work that advances that entry's own acceptance criteria;
  unrelated merged work in the same owning plan does not qualify.
- `Closed` and `Reviewed disposition` are the only tokens that satisfy the pool-closure gate.
- A promoted target is a relative Markdown link resolving to an existing file beneath
  `docs/superpowers/plans/`; a numeric Plan identifier is not required.
- The stable-ID index has an exact bijection with every `### <FU-ID>:` heading. All current 41
  headings, including the nine unnumbered/historical headings, remain subject to canonical-status
  and blanket relative-link validation. The entry floor is `>= 41`, not an exact-count gate.
- Do not write a concrete "next unused Plan 11.x slot is N" claim. Cite the numbering convention.
- The feature-slice State column is not forced into FU tokens. Record its residual semantic-drift
  risk in the PR description.
- Follow TDD: add the focused failing assertion, run it and record the expected failure, make the
  minimum documentation change, rerun to green, then commit that coherent slice.
- Before pushing, fetch and merge current `origin/main`, rerun the full verification set, and
  resolve drift deliberately. Never use `--no-verify`.
- Do not stage reviewer checkpoint logs or unrelated user changes.

---

## Frozen input ledger

Task 0 re-derives every value from committed bytes before test or pool mutation.

| Input | Git blob | SHA-256 / identity | Mutation rule |
|---|---|---|---|
| Approved normalization design | `c4d6b1c089762942a200f2acd595a04b899b78b3` | body `4ff6cc2591e2fe446d422847206769cfa96e20fad1356cb37947824a82525446` | Frozen |
| Plan 11.8 Gateway-MCP design | `59cdb3a07611a3bf12396861c227f10e55cde97f` | file `ac48c0aef1778d6ebe93005bc3993ae204f81a1c59cdc8db17cfb7edb6a040f8`; body `1eb6cb626e1ed74e83f9ce81b048cb68da8105a1468f8f12272620bf2325f911` | Frozen |
| Plan 11.5 implementation plan | `431255bc9fc9a248ce1811f4e8b033adf509f4cf` | `0bac146974984ea663b7a59802a1b5ed74f90eb682f855c0e05aaab5b9a2c396` | Frozen |
| Plan 11.7 parent implementation plan | `43fcf71450305d369c2d3f7dd5da31a65991fe83` | `f52ad9a5a85dc50b0dfd3206b6bd09fd8ff0ae79b1a6049df1017f978b1c462d` | Frozen |
| Plan 11.7 feasibility amendment | `30f4bbac9b7f3af2e79db849bc3fa01c1973324c` | `79f3c92a852cb7eaa6108d8f0757f6612a0c908fe032ce7cfab58b46721c06e6` | Frozen |
| Plan 11.7 origin-A fixture-v2 amendment | `7b72d9f164dc5d62f0f836df9b68b022f5d7e826` | `5bb327d88761ae329869b90866839d03f61eff6af0e5ae47f8d3d7551f849a4d` | Frozen |
| Plan 11.7 retry-preflight amendment | `c607a51ee16107926bb9702a7aa1512bf6aa18fc` | `106fd92b8e43f44a7115d7edb1f9cf1e3ee643e4b6f594fa656fb4119a969b82` | Frozen |
| Plan 10.3 implementation plan | `aed34819eb684b5f454966acb4a36a0bcce32548` | `e66eca48c588e7db618d4850fdf0cee901b4966bc0ab405e21c857ae6be24f32` | Frozen |
| Plan 11.8 implementation plan | `5bcdc0b9e95de94867517d8732f04b3f093880a5` | `09d5b257ac52556c15ae10cd9f1e222251400102d13f05a288de49bc6ea16cc5` | Living; status-only edit authorized |

## File responsibility map

| File | Responsibility |
|---|---|
| `tests/unit/docs/test_open_work_pool_hygiene.py` | Parse entry sections, canonical status tokens, stable-ID index rows, promoted targets, all relative links, and targeted settled-entry/current-state regressions. |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Own the five-token contract, 32-row FU index, normalized 41-entry statuses, factual corrections, and repaired relative links. |
| `docs/superpowers/plans/2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md` | Replace the stale approval-only status with the exact 27/46 partially implemented boundary and pause date; change no checkbox or task body. |
| `docs/superpowers/specs/2026-08-07-open-work-pool-status-normalization-design.md` | Frozen approved contract; read-only during execution. |
| `docs/superpowers/plans/2026-08-07-open-work-pool-status-normalization-implementation.md` | Execution checklist and verification contract; checkbox updates require their named commands to pass. |

## Task 0: Re-derive the approved baseline and protected bytes

**Files:** Read-only inspection of Git objects and the paths in the frozen input ledger.

**Interfaces:**

- Consumes the final approved design commit, branch merge base, pool, test file, Plan 11.8 plan, and
  every frozen input in the ledger.
- Produces a verified baseline in the execution log. It changes no repository file.

- [x] **Step 1: Verify branch, merge base, and clean execution baseline.**

  Run:

  ```powershell
  git status --short --branch
  git merge-base HEAD origin/main
  git rev-parse origin/main
  git log --oneline --decorate -5
  ```

  Expected: branch `agent/codex/pool-status-normalization`; merge base and `origin/main` are
  `364fc9d6bc122ace3e7c9fc5042b7b2c094827cf` unless main advanced, in which case stop and merge main
  before proceeding; only this implementation plan may be untracked or modified.

- [x] **Step 2: Recompute the approved design body from its committed blob.**

  Run:

  ```powershell
  git show 3b4dd3c9e2beeda54df900889d35b2ddcd8b5894:docs/superpowers/specs/2026-08-07-open-work-pool-status-normalization-design.md | uv run --frozen python -c "import hashlib,sys; text=sys.stdin.buffer.read().decode('utf-8').replace('\r\n','\n').replace('\r','\n'); body=''.join(line for line in text.splitlines(keepends=True) if not line.startswith('**Frozen design-body SHA-256:**')); print(hashlib.sha256(body.encode('utf-8')).hexdigest())"
  ```

  Expected: exactly `4ff6cc2591e2fe446d422847206769cfa96e20fad1356cb37947824a82525446`.

- [x] **Step 3: Verify every protected file and the mutable Plan 11.8 pre-image.**

  Run this exact script from the repository root:

  ```powershell
  $expected = @{
    'docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md' = 'AC48C0AEF1778D6EBE93005BC3993AE204F81A1C59CDC8DB17CFB7EDB6A040F8'
    'docs/superpowers/plans/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-implementation.md' = '0BAC146974984EA663B7A59802A1B5ED74F90EB682F855C0E05AAAB5B9A2C396'
    'docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md' = 'F52AD9A5A85DC50B0DFD3206B6BD09FD8FF0AE79B1A6049DF1017F978B1C462D'
    'docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md' = '79F3C92A852CB7EAA6108D8F0757F6612A0C908FE032CE7CFAB58B46721C06E6'
    'docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md' = '5BB327D88761AE329869B90866839D03F61EFF6AF0E5AE47F8D3D7551F849A4D'
    'docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md' = '106FD92B8E43F44A7115D7EDB1F9CF1E3EE643E4B6F594FA656FB4119A969B82'
    'docs/superpowers/plans/2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md' = 'E66ECA48C588E7DB618D4850FDF0CEE901B4966BC0AB405E21C857AE6BE24F32'
    'docs/superpowers/plans/2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md' = '09D5B257AC52556C15AE10CD9F1E222251400102D13F05A288DE49BC6EA16CC5'
  }
  foreach ($item in $expected.GetEnumerator()) {
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $item.Key).Hash
    if ($actual -ne $item.Value) { throw "$($item.Key): expected $($item.Value), got $actual" }
  }
  ```

  Expected: exit 0 with no output.

- [x] **Step 4: Confirm the Plan 11.8 status edit has no downstream digest pin.**

  Run:

  ```powershell
  rg -l -F '5bcdc0b9e95de94867517d8732f04b3f093880a5' .
  rg -l -F '09d5b257ac52556c15ae10cd9f1e222251400102d13f05a288de49bc6ea16cc5' .
  ```

  Expected: only this implementation plan is returned. Any other tracked file is a stop condition.

## Task 1: Normalize the 41 entry statuses with a canonical parser

**Files:**

- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`

**Interfaces:**

- Consumes the existing `_read()` helper and pool path.
- Produces `_entry_sections(text) -> dict[str, str]`,
  `_status_token(section_body) -> str`, and canonical-status tests used by Tasks 2 and 3.

- [x] **Step 1: Add the section and status-token parser.**

  Add these constants and helpers below the existing Markdown regular expressions:

  ```python
  FU_ID_BODY = r"P\d+(?:\.\d+)*-FU-\d+"
  SECTION_HEADING_RE = re.compile(r"^(?P<level>##|###) (?P<title>.+)$", re.MULTILINE)
  FU_HEADING_RE = re.compile(rf"^(?P<identity>{FU_ID_BODY}): (?P<title>.+)$")
  STATUS_LINE_RE = re.compile(r"^\*\*Status:\*\*\s*(?P<value>.+)$", re.MULTILINE)
  FIXED_STATUS_RE = re.compile(
      r"^(?P<token>Open|Partially implemented|Closed|Reviewed disposition)[.:](?:\s|$)"
  )
  PROMOTED_STATUS_RE = re.compile(
      r"^(?P<token>Promoted -> \[[^\]]+\]\((?P<target>[^)]+)\))[.:](?:\s|$)"
  )


  def _entry_sections(text: str) -> dict[str, str]:
      headings = tuple(SECTION_HEADING_RE.finditer(text))
      entries: dict[str, str] = {}
      for index, heading in enumerate(headings):
          if heading.group("level") != "###":
              continue
          end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
          title = heading.group("title")
          assert title not in entries
          entries[title] = text[heading.end() : end]
      return entries


  def _status_token(section_body: str) -> str:
      matches = tuple(STATUS_LINE_RE.finditer(section_body))
      assert len(matches) == 1
      value = matches[0].group("value").strip()
      promoted = PROMOTED_STATUS_RE.match(value)
      if promoted is not None:
          return promoted.group("token")
      fixed = FIXED_STATUS_RE.match(value)
      assert fixed is not None, value
      return fixed.group("token")
  ```

- [x] **Step 2: Add failing canonical-status and history-retention tests.**

  Add:

  ```python
  def test_every_optimus_pool_entry_has_one_canonical_status() -> None:
      entries = _entry_sections(_read(OPTIMUS_POOL))

      assert len(entries) >= 41
      assert all(_status_token(body) for body in entries.values())


  def test_p996_aggregate_uses_canonical_closed_status() -> None:
      pool_text = _read(OPTIMUS_POOL)
      section = pool_text.split("## P9.96 Task 9 Disclosed Follow-Ups", 1)[1].split(
          "\n## Closed Historical Follow-Ups", 1
      )[0]

      assert _status_token(section) == "Closed"
  ```

- [x] **Step 3: Run the new tests and verify RED.**

  Run:

  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/docs/test_open_work_pool_hygiene.py::test_every_optimus_pool_entry_has_one_canonical_status tests/unit/docs/test_open_work_pool_hygiene.py::test_p996_aggregate_uses_canonical_closed_status -v
  ```

  Expected: FAIL because three `###` entries lack `**Status:**`, existing entries use noncanonical
  prefixes, and the P9.96 aggregate does not start with `Closed.`.

- [x] **Step 4: Normalize every status without changing its substantive disposition.**

  Apply this exact mapping, preserving the existing explanatory prose after the new token:

  | Token | Entries |
  |---|---|
  | `Open.` | `P9.8-FU-2`, `P9.8-FU-3`, `P9.85-FU-1`, `P9.85-FU-2`, `P9.85-FU-3`, `P9.87-FU-1`, `P11-FU-4` through `P11-FU-8`, `P11.5-FU-1`, `P11-FU-10`, `P11.7-FU-1` through `P11.7-FU-3`, `P11-FU-12` through `P11-FU-20`, plus `Durable effect-aware MCP indeterminate-call custody`, `Durable client-MCP descriptor-surface pinning and named tool allowlists`, `Client-MCP durable HTTP/SSE trust relaxation`, `Authenticated client-owned MCP upstream evidence`, and `Plan 11.8 Windows WinError 10053 MCP test flake` |
  | `Promoted -> [Plan 11.7](2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md).` | `P9.8-FU-5`, `P11-FU-1` |
  | `Partially implemented.` | `P11-FU-11` |
  | `Closed.` | `P11-FU-2`, `P11-FU-3`, `P11-FU-9`, `P11.5-FU-2`, Plan 10.3 frozen-plan status correction, historical `uv.lock` item, historical `SurfaceAuditError` item, and the P9.96 aggregate section |
  | `Reviewed disposition.` | Plan 11.7 accepted Redis durability risk |

  Add the five-token meanings and the exact `Closed` or `Reviewed disposition` closure-gate rule to
  `## How to use this document`. Keep the existing Raised, ownership, acceptance, evidence, and
  non-claim prose intact.

- [x] **Step 5: Run the status tests and all existing pool hygiene tests.**

  Run:

  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/docs/test_open_work_pool_hygiene.py -v
  .venv\Scripts\python.exe -m ruff check .
  ```

  Expected: all tests pass at this checkpoint and Ruff is clean.

- [x] **Step 6: Commit the canonical vocabulary slice.**

  ```powershell
  git add tests/unit/docs/test_open_work_pool_hygiene.py docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md
  git commit -m "docs: normalize open-work pool statuses"
  ```

## Task 2: Add the complete 32-row stable-ID FU index

**Files:**

- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`

**Interfaces:**

- Consumes `FU_HEADING_RE`, `_entry_sections()`, and `_status_token()` from Task 1.
- Produces `_fu_index_rows(text) -> dict[str, tuple[str, str]]` and an exact ID/title/status
  projection invariant.

- [x] **Step 1: Add the index parser and bijection test.**

  Add:

  ```python
  FU_INDEX_ROW_RE = re.compile(
      rf"^\|\s*`(?P<identity>{FU_ID_BODY})`\s*\|\s*(?P<item>[^|]+?)\s*\|"
      r"\s*(?P<status>.*?)\s*\|\s*(?P<owner>.*?)\s*\|\s*(?P<evidence>.*?)\s*\|\s*$",
      re.MULTILINE,
  )


  def _fu_index_rows(text: str) -> dict[str, tuple[str, str]]:
      section = text.split("## Follow-up status index", 1)[1].split("\n## ", 1)[0]
      rows: dict[str, tuple[str, str]] = {}
      for match in FU_INDEX_ROW_RE.finditer(section):
          identity = match.group("identity")
          assert identity not in rows
          rows[identity] = (match.group("item").strip(), match.group("status").strip())
      return rows


  def test_fu_index_is_an_exact_projection_of_stable_id_entries() -> None:
      pool_text = _read(OPTIMUS_POOL)
      entries = _entry_sections(pool_text)
      expected: dict[str, tuple[str, str]] = {}
      for heading, body in entries.items():
          match = FU_HEADING_RE.fullmatch(heading)
          if match is None:
              continue
          identity = match.group("identity")
          assert identity not in expected
          expected[identity] = (match.group("title"), _status_token(body))

      assert _fu_index_rows(pool_text) == expected
  ```

- [x] **Step 2: Run the index test and verify RED.**

  Run:

  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/docs/test_open_work_pool_hygiene.py::test_fu_index_is_an_exact_projection_of_stable_id_entries -v
  ```

  Expected: FAIL because `## Follow-up status index` does not exist.

- [x] **Step 3: Insert the exact 32-row index before `## Open items`.**

  Use these rows; copy status cells byte-for-byte from the corresponding entry token:

  | ID | Item | Status | Owning slice / designated plan | Evidence |
  |---|---|---|---|---|
  | `P9.8-FU-2` | Intelligent ambiguous-reference ranking | Open | Plan 12 | Acceptance criteria in entry |
  | `P9.8-FU-3` | Dynamic context budgets and required-file summarization | Open | Plan 12 | Acceptance criteria in entry |
  | `P9.8-FU-5` | Zed Refusal-Rendering Stability | Promoted -> [Plan 11.7](2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md) | `P11-FEAT-ZED-RESUME` | [Path A terminal seal](../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/path-a-run/path-a-terminal-seal.json) |
  | `P9.85-FU-1` | Intelligent observation compression | Open | Plan 12 | Acceptance criteria in entry |
  | `P9.85-FU-2` | Dynamic planning-evidence partition | Open | Plan 12 | Acceptance criteria in entry |
  | `P9.85-FU-3` | Cross-Run/Session Spend Policy | Open | Future budget-governance plan | Acceptance criteria in entry |
  | `P9.87-FU-1` | Mechanical Current-Raw-Evidence Grounding Guard | Open | Future Plan 11 feature work | Acceptance criteria in entry |
  | `P11-FU-1` | ACP Session Resume Capability | Promoted -> [Plan 11.7](2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md) | `P11-FEAT-ZED-RESUME` | [Path A terminal seal](../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/path-a-run/path-a-terminal-seal.json) |
  | `P11-FU-2` | Package Lookup and Security Advisory Gateway Capability | Closed | `P11-FEAT-GATEWAY-TOOLS` / Plan 11.2 | PR #88 / `4590dbf` |
  | `P11-FU-3` | MCP Route/Typed-Contract Publication Gate | Closed | `P11-FEAT-GATEWAY-MCP` | PR #112; PR #113 / `edd1f04` |
  | `P11-FU-4` | Re-pin FU-4A/FU-5 Live Evidence | Open | Coordinated with `P11-FEAT-ZED-RESUME` | Acceptance criteria in entry |
  | `P11-FU-5` | Windows Subprocess Handle-Duplication Flake (WinError 6/50) | Open | Future Windows investigation | Acceptance criteria in entry |
  | `P11-FU-6` | Gateway `test_server` Full-Suite Port/Teardown Flake | Open | Future Gateway unit-harness investigation | Acceptance criteria in entry |
  | `P11-FU-7` | Windows Coverage/`sys.settrace` Timing Flake in ACP NDJSON Sanitization Test | Open | Future Windows test-infrastructure work | Acceptance criteria in entry |
  | `P11.5-FU-1` | Map live OTLPSpanExporter FAILURE into Gateway QUEUED/retry semantics | Open | `P11-FEAT-GATEWAY-COST-OBS` | Acceptance criteria in entry |
  | `P11-FU-8` | Align `OPTIMUS_LOCAL_GATEWAY_BASE_URL` with `OPTIMUS_GATEWAY_<THING>_BASE_URL` naming | Open | Future Gateway migration design | Acceptance criteria in entry |
  | `P11-FU-9` | Client-Supplied ACP `mcpServers` Disposition | Closed | Dedicated P11-FU-9 lane | PR #119 / `9a93137`; [closure evidence](../../../reports/p11-fu-9-client-mcp-closure-evidence.md) |
  | `P11-FU-10` | Complete ACP Error-Code Registry Audit | Open | Future ACP audit | Acceptance criteria in entry |
  | `P11.7-FU-1` | Configurable Gateway request timeout for debug/investigation workflows | Open | Plan 11.7 deferred follow-up | Acceptance criteria in entry |
  | `P11.7-FU-2` | Gateway threaded-test flake under full-suite load | Open | Plan 11.7 deferred follow-up | Acceptance criteria in entry |
  | `P11.7-FU-3` | Committed `plan117_custody_relay.py` docstring `\ufffd` / em-dash corruption | Open | Plan 11.7 deferred follow-up | Acceptance criteria in entry |
  | `P11-FU-11` | Plan 11.7 Retry Preflight and Live Session Proof | Partially implemented | [Plan 11.7 retry-preflight amendment](2026-08-04-plan-11-7-retry-preflight-gate-amendment.md) | [Path A terminal seal](../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/path-a-run/path-a-terminal-seal.json) |
  | `P11-FU-12` | MCP OAuth 2.1 Lifecycle | Open | Future `P11-FEAT-GATEWAY-MCP` follow-up | Acceptance criteria in entry |
  | `P11-FU-13` | Deferred MCP Capabilities and Long-Lived Interaction | Open | Future `P11-FEAT-GATEWAY-MCP` follow-up | Acceptance criteria in entry |
  | `P11-FU-14` | MCP Registry Discover-and-Connect | Open | Future `P11-FEAT-GATEWAY-MCP` follow-up | Acceptance criteria in entry |
  | `P11-FU-15` | MCP Tool Search and Context Minimization | Open | Future `P11-FEAT-GATEWAY-MCP` follow-up | Acceptance criteria in entry |
  | `P11-FU-16` | Reverse Research-to-Documentation Freshness Gate | Open | Future cross-cutting documentation gate | Acceptance criteria in entry |
  | `P11-FU-17` | WSL2 native git cannot parse a Windows-git-created linked worktree's `.git` pointer | Open | Future WSL2 test infrastructure | Acceptance criteria in entry |
  | `P11-FU-18` | WSL2 directory `ctime` timestamp-coalescing test flake | Open | Future WSL2 test infrastructure | Acceptance criteria in entry |
  | `P11-FU-19` | WSL full-suite load flake in client SDK operation-deadline unit test | Open | Future WSL2 test infrastructure | Acceptance criteria in entry |
  | `P11-FU-20` | Attach per-server catalog/authorizer to session tool service for real one-call issuance | Open | Future client-MCP runtime follow-up | Acceptance criteria in entry |
  | `P11.5-FU-2` | Consistent local env / Redis / Phoenix / Gateway startup for live runs | Closed | Plan 11.6 | PR #97 / `dc9a080`; [operator runbook](../../runbooks/local-live-dependencies.md) |

  Precede the table with one sentence stating that entries own explanatory prose and tests enforce
  ID/title/status projection. Do not add the nine unnumbered/historical headings to this table.

- [x] **Step 4: Run the index and complete pool hygiene tests.**

  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/docs/test_open_work_pool_hygiene.py -v
  .venv\Scripts\python.exe -m ruff check .
  ```

  Expected: all tests pass; the index parser returns the same 32 ID/title/status tuples as the
  detailed headings; Ruff is clean.

- [x] **Step 5: Commit the index slice.**

  ```powershell
  git add tests/unit/docs/test_open_work_pool_hygiene.py docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md
  git commit -m "docs: add stable follow-up status index"
  ```

## Task 3: Guard relative links and correct verified stale current-state claims

**Files:**

- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Modify: `docs/superpowers/plans/2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md`

**Interfaces:**

- Consumes the canonical parser and index from Tasks 1-2.
- Produces blanket relative-link validation, promoted-target confinement, settled-history wording
  protection, and targeted Plan 11.8/feature-row regression assertions.

- [x] **Step 1: Add relative-link and promoted-target tests.**

  Add `from urllib.parse import urlsplit` to the imports, add
  `PLANS_ROOT = REPO_ROOT / "docs/superpowers/plans"`, and add:

  ```python
  def _relative_link_targets(text: str) -> tuple[str, ...]:
      targets: list[str] = []
      for match in MARKDOWN_LINK_RE.finditer(text):
          target = match.group("target").strip()
          parsed = urlsplit(target)
          if parsed.scheme or target.startswith("#"):
              continue
          assert parsed.path
          targets.append(parsed.path)
      return tuple(targets)


  def test_every_relative_optimus_pool_link_resolves() -> None:
      targets = _relative_link_targets(_read(OPTIMUS_POOL))

      assert targets
      for target in targets:
          assert (OPTIMUS_POOL.parent / target).resolve().exists(), target


  def test_promoted_targets_resolve_inside_plan_directory() -> None:
      entries = _entry_sections(_read(OPTIMUS_POOL))
      promoted = tuple(
          token
          for token in (_status_token(body) for body in entries.values())
          if token.startswith("Promoted -> ")
      )

      assert promoted
      for token in promoted:
          match = PROMOTED_STATUS_RE.match(f"{token}.")
          assert match is not None
          target = urlsplit(match.group("target"))
          assert not target.scheme and target.path
          resolved = (OPTIMUS_POOL.parent / target.path).resolve()
          assert resolved.is_relative_to(PLANS_ROOT.resolve())
          assert resolved.is_file()
  ```

- [x] **Step 2: Add settled-history and targeted factual regression tests.**

  Add:

  ```python
  def _feature_row(text: str, identity: str) -> str:
      prefix = f"| `{identity}` |"
      return next(line for line in text.splitlines() if line.startswith(prefix))


  def test_settled_entries_do_not_label_historical_defects_as_current() -> None:
      forbidden = (
          "**Origin / current behavior:**",
          "**Also found:** No launcher exists",
          "The committed `uv.lock` is out of sync",
          "`tools/verify_plan996_logging_surfaces.py` raises",
      )
      for body in _entry_sections(_read(OPTIMUS_POOL)).values():
          token = _status_token(body)
          if token not in {"Closed", "Partially implemented", "Reviewed disposition"}:
              continue
          assert all(phrase not in body for phrase in forbidden)


  def test_gateway_mcp_row_records_the_real_plan_118_boundary() -> None:
      pool_text = _read(OPTIMUS_POOL)
      row = _feature_row(pool_text, "P11-FEAT-GATEWAY-MCP")
      plan = _read(
          REPO_ROOT
          / "docs/superpowers/plans/2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md"
      )
      checked = len(re.findall(r"^- \[x\]", plan, re.MULTILINE))
      unchecked = len(re.findall(r"^- \[ \]", plan, re.MULTILINE))

      assert "2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md" in row
      assert "2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md" in row
      assert checked and unchecked
      assert f"{checked} of {checked + unchecked}" in row
      assert "PR #116" in row and "PR #118" in row
      assert "next unused" not in pool_text.lower()


  def test_plan_118_status_matches_its_checked_task_boundary() -> None:
      plan = _read(REPO_ROOT / "docs/superpowers/plans/2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md")
      normalized = re.sub(r"\s+", " ", plan)
      checked = len(re.findall(r"^- \[x\]", plan, re.MULTILINE))
      unchecked = len(re.findall(r"^- \[ \]", plan, re.MULTILINE))

      assert "**Status:** Partially implemented." in plan
      assert "Tasks 0-7 are complete" in normalized
      assert "Task 8 Step 1 is complete" in normalized
      assert "Task 8 Steps 2-4 and Task 9 are incomplete" in normalized
      assert checked and unchecked
      assert f"{checked} of {checked + unchecked}" in normalized
  ```

- [x] **Step 3: Run the new tests and verify RED.**

  Run:

  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/docs/test_open_work_pool_hygiene.py::test_every_relative_optimus_pool_link_resolves tests/unit/docs/test_open_work_pool_hygiene.py::test_promoted_targets_resolve_inside_plan_directory tests/unit/docs/test_open_work_pool_hygiene.py::test_settled_entries_do_not_label_historical_defects_as_current tests/unit/docs/test_open_work_pool_hygiene.py::test_gateway_mcp_row_records_the_real_plan_118_boundary tests/unit/docs/test_open_work_pool_hygiene.py::test_plan_118_status_matches_its_checked_task_boundary -v
  ```

  Expected: FAIL on the four broken report links, stale settled-entry labels, false Gateway-MCP row,
  and stale Plan 11.8 status. The promoted-target test may already pass from Task 1.

- [x] **Step 4: Apply the verified feature and Plan 11.8 corrections.**

  Make these exact semantic changes:

  - `P11-FEAT-GATEWAY-MCP`: state `Partially implemented`; link the frozen design and living Plan
    11.8 plan; record 27 of 46 checks, Tasks 0-7 complete, Task 8 Step 1 complete, remaining Task 8
    steps and Task 9 incomplete; cite PR #116 and repair PR #118; record the 2026-08-06 pause/pivot;
    cite the Plan 11 numbering convention without naming a next slot.
  - Plan 11.8 implementation plan: change only the Status paragraph to `Partially implemented.`
    followed by the same exact task boundary, PR #116 merge, PR #118 repair, and pause/pivot. Do not
    alter any checkbox or task body.
  - `P11-FEAT-ZED-RESUME`: replace `Plan 11.7 active` with `Partially implemented; blocked` and
    retain all current seals and non-claims.
  - `P11-FEAT-GATEWAY-CORE`: remove `no migration follow-ups remain open under this identity` while
    retaining the verified Plan 11.1/11.4 closure and Vercel backlog disposition.

- [x] **Step 5: Convert resolved findings to dated history and repair evidence links.**

  - `P11-FU-3`: retain `Closed`; replace the no-plan/Plan-11.8-next-slot prose with a later-pickup
    pointer to the Plan 11.8 design, plan, and partial checkpoint.
  - `P11-FU-9`: rename `Origin / current behavior` to an intake finding dated 2026-07-29 and state
    that PR #119 resolved the ignored-`mcpServers` behavior.
  - `P11-FU-11`: rename `Origin / current behavior` to a pre-implementation finding dated
    2026-08-04; retain the Path A non-claim and `Partially implemented` token.
  - `P11.5-FU-2`: date the core-problem/mechanism inventory and Phoenix absence to 2026-07-29;
    state that Plan 11.6 / PR #97 added `optimus-phoenix`, its image/port/health/identity checks, and
    the living runbook.
  - Historical `uv.lock`: begin `At disclosure on 2026-07-23, ... was out of sync` and retain the
    Plan 10.3 closure evidence.
  - Historical `SurfaceAuditError`: begin `At disclosure on 2026-07-23, ... raised` and retain the
    Plan 10.3 closure evidence.
  - Change the P11-FU-11 seal and the three Plan 11.6 report targets from `../../reports/` to
    `../../../reports/`.

- [x] **Step 6: Run the complete pool hygiene file and diff checks.**

  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/docs/test_open_work_pool_hygiene.py -v
  .venv\Scripts\python.exe -m ruff check .
  git diff --check
  ```

  Expected: all pool hygiene tests pass, Ruff is clean, and diff hygiene is clean.

- [x] **Step 7: Commit the factual/link correction slice.**

  ```powershell
  git add tests/unit/docs/test_open_work_pool_hygiene.py docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md docs/superpowers/plans/2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md
  git commit -m "docs: correct pool facts and guard relative links"
  ```

## Task 4: Re-audit every claim, run release gates, and publish the documentation PR

**Files:** Read-only verification of the complete repository; PR metadata after all gates pass.

**Interfaces:**

- Consumes the committed documentation/test slices and protected input ledger.
- Produces a clean, pushed branch and one draft PR whose description separates factual corrections
  from structural changes and records the feature-State residual.

- [x] **Step 1: Re-run the negative-existence sweep and disposition every hit.**

  ```powershell
  rg -in "no .{0,40}(exists|yet)|does not exist|nothing in-repo|unresearched|not yet known" docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md
  ```

  Expected: no false current-state denial remains. Retained hits must correspond to rechecked facts:
  absent `session/load`, genuinely unallocated/open work, or explicitly dated historical findings.

- [x] **Step 2: Verify structural counts without making additions brittle.**

  Run:

  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/docs/test_open_work_pool_hygiene.py -v
  ```

  Expected: at least 41 entry headings; the current document has 41; the stable-ID heading/index
  bijection currently has 32 rows; every entry has exactly one canonical status; every relative
  link resolves.

- [x] **Step 3: Recompute all frozen hashes and the Plan 11.8 checkbox boundary.**

  Re-run Task 0 Step 3 without the mutable Plan 11.8 plan row, then run:

  ```powershell
  $plan = 'docs/superpowers/plans/2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md'
  (Select-String -LiteralPath $plan -Pattern '^- \[x\]' -CaseSensitive).Count
  (Select-String -LiteralPath $plan -Pattern '^- \[ \]' -CaseSensitive).Count
  ```

  Expected: every frozen hash is unchanged; Plan 11.8 remains 27 checked and 19 unchecked.

- [x] **Step 4: Run documentation tests, full suite, Ruff, and diff hygiene.**

  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/docs -q
  .venv\Scripts\python.exe -m pytest -q
  .venv\Scripts\python.exe -m ruff check .
  git diff --check
  ```

  Expected: all commands exit 0. Record exact pass/skip/deselect counts in the PR description.

- [x] **Step 5: Audit README and roadmap current-state claims.**

  ```powershell
  rg -n -i "Plan 11\.8|P11-FEAT-GATEWAY-MCP|P11-FEAT-ZED-RESUME|P11-FU-9|Phoenix|open.work pool|follow-up" README.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md
  ```

  Expected: no directly affected current-state claim is false. If one is false, stop for operator
  approval before widening the file set; do not silently edit it.

- [x] **Step 6: Check final scope and commit any verification-only plan checkbox updates.**

  ```powershell
  git status --short
  git diff --stat origin/main...HEAD
  git diff --name-only origin/main...HEAD
  git diff --check origin/main...HEAD
  ```

  Expected tracked PR scope: approved design, this implementation plan, consolidated pool, living
  Plan 11.8 implementation plan, and the documentation hygiene test only. If plan checkbox updates
  are made after their commands pass, stage only this implementation plan and commit them as
  `docs: record pool normalization verification`.

- [ ] **Step 7: Update from current main and rerun the complete safety gates.**

  ```powershell
  git fetch origin main
  git merge --no-edit origin/main
  .venv\Scripts\python.exe -m pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  .venv\Scripts\python.exe -m pytest -q
  .venv\Scripts\python.exe -m ruff check .
  git diff --check origin/main...HEAD
  ```

  Expected: merge completes without unresolved conflicts; focused and full tests, Ruff, and diff
  hygiene pass.

- [ ] **Step 8: Push and open one draft documentation PR.**

  ```powershell
  $body = @'
  ## Summary

  Documentation and documentation-hygiene tests only: normalize the consolidated pool's five-token
  status contract, add the 32-row stable-ID FU index, correct the verified Plan 11.8/Phoenix/
  historical findings, and make every relative pool link mechanically resolvable.

  ## Part 1 - factual corrections

  Record the exact Plan 11.8 27/46 boundary and pause, repair settled-entry history and four broken
  report links, remove hardcoded next-slot numbering, and retain all frozen plans byte-for-byte.

  ## Parts 3-4 - structural work

  Enforce canonical status grammar across at least the 41-entry reviewed baseline, exact stable-ID
  heading/index projection, promoted-plan confinement, blanket relative-link resolution, and
  settled-history wording checks.

  ## Verification

  Include the exact focused documentation-test, full-suite, Ruff, diff-hygiene, status/index count,
  and protected-hash outputs recorded in Tasks 0 and 4.

  ## Recorded residual

  Feature-slice State prose is not constrained by the five FU tokens because feature identities can
  span multiple plans. Semantic feature-state drift remains a documentation-freshness review
  responsibility; blanket relative-link validation still covers feature-row links.
  '@
  git push -u origin agent/codex/pool-status-normalization
  gh pr create --draft --base main --head agent/codex/pool-status-normalization --title "docs: normalize open-work pool status and indexing" --body $body
  ```

  The PR body must have separate review sections for:

  - Part 1 factual corrections: Plan 11.8, settled-entry history, Phoenix, feature rows, and links;
  - Parts 3-4 structural work: five-token grammar, 41-entry floor, 32-row index, and hygiene tests;
  - verification commands and exact results;
  - protected frozen-file hashes; and
  - residual decision: feature-slice State prose is not constrained by the five FU tokens, so
    semantic feature-state drift remains a documentation-freshness review responsibility while
    blanket relative-link validation covers feature-row links.

## Definition of Done

- The approved design digest re-verifies from committed blob bytes.
- All frozen artifacts in the ledger remain byte-for-byte unchanged.
- The Plan 11.8 living plan states the exact 27/46 partially implemented boundary without changing
  any checkbox.
- Every current pool `###` entry has exactly one canonical status; the parser enforces a floor of
  41 entries without blocking legitimate additions.
- The FU index is an exact ID/title/status projection of all stable-ID headings, currently 32 rows.
- Promoted targets resolve within `docs/superpowers/plans/`; every relative pool link resolves.
- Verified stale present-tense findings are dated and point to their resolution evidence.
- No concrete next-unused Plan number remains in the pool.
- The full test suite, documentation tests, Ruff, and diff hygiene pass.
- The branch is updated from current main, pushed, and represented by one draft PR with the
  feature-State residual explicitly recorded.
