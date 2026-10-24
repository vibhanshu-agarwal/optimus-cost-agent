## Covers

### H1 — HLD v2.21

```markdown
# Optimus - Architecture (HLD)

**Version 2.21 — Agent-mode localized EDIT, 2026-10-24; local filing — not activated.**

Predecessor: Optimus-Cost-Agent-Architecture-v2.20.pdf; SHA-256 52c35442a0d9027dc4b18a693284c45406cf02913001a59f2df364c77a2e176a. The predecessor is retained unchanged in `docs/archive/`.

Native carried page bodies originate from Optimus-Cost-Agent-Architecture-v2.18.pdf (SHA-256 0f8725765fecc9a93045fd26630457dfe7112508df164a3ec5bcc55dbc976807). This complete successor retains the predecessor's carried bodies and source corrections except for the approved localized EDIT changes. Sources are in `docs/sources/agent-localized-edit/`.

**What this edition changes.** It describes Agent-mode localized EDIT (#407, PR #411, merged as `d13fd34`) and corrects the consequent ACP WRITE/EDIT execution-path statements at main `57e2069414fef32c6a6e4de42bd0dc7fb9f4f1ac`, including the merged parser and failure-telemetry changes from PR #413 and PR #414. Carried statements and baseline status rows retain their inspected source `91fd64ac78025efe1076bddb106ff89e6adb2030` (origin/main, 2026-10-15). They have not been reverified at the newer pin. Accepted requirements and historical evidence retain their original authority and pins.

**Inspected production facts at 91fd64a.** ENFORCEMENT_ACTIVE is False and trusted_snapshot() returns None; no production path constructs ContextAttachment; the shipped alias claude-haiku resolves to anthropic/claude-haiku-4.5; the Gateway web-search provider is Tavily with a Gateway-only key; package/OSV routes still depend on that search configuration; no PyTestArch, maintainability-index, DeepEval, Ragas, PyRIT, Tirith or Vercel dependency, import or test exists; no Rust source exists.

**Historical acceptance stays attached to its pins.** Offline implementation candidate cf9bb9d (Codex review 2026-10-04); documentation filing 5ee081e; operator acceptance of the offline delivery through 2068366 (2026-10-08); merge c509fc8 (PR #276). The deferred live obligations (Luna route/estimator qualification, genuine summary-quality receipt, real-editor Task 13) remain UNRUN under Plan 12.2 ownership (issue #237). Offline acceptance is not production acceptance, a full CP4 pass or permission to remove the shipped model default.

**Controlling Plan 12.2 amendment.** The two preceding paragraphs are carried unchanged from v2.20 and retain their stated pins. The filed 2026-10-18 ordinary shipping amendment, `docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`, still controls §14.2, §14.4–§14.6 and the §15 Context Engine and registry rows. It is not folded into this successor.

**Authority.** Codex's architecture wording; local filing by Claude under the operator's 2026-10-24 approval of change list r3 and decisions D1–D4, with the same unpublished editions re-pinned under the operator's 2026-10-24 decision. Local filing is separate from publication to main. This document grants no build, commit, paid or live call, activation, push, PR or merge authority. No product suite was run to author this text.
```

### L1 — LLD v2.44

```markdown
# Optimus - Low-Level Design

**Version 2.44 — Agent-mode localized EDIT, 2026-10-24; local filing — not activated.**

Predecessor: Optimus-Cost-Agent-LLD-v2.43.pdf; SHA-256 3fb89935201eb5947eff666a97431653d264ee482b8a5a8a6a4d229d4c8b7c27. The predecessor is retained unchanged in `docs/archive/`.

Native carried page bodies originate from Optimus-Cost-Agent-LLD-v2.41.pdf (SHA-256 69400fd474eb30711fcc9a061243d6a4d2e35d39d7794d4aa69f5ff51b98109b). This complete successor retains the predecessor's carried bodies and source corrections except for the approved localized EDIT changes. Sources are in `docs/sources/agent-localized-edit/`.

**What this edition changes.** It specifies the Agent-mode directive plan and localized EDIT in §4B (#407, PR #411, merged as `d13fd34`), with consequent ACP WRITE/EDIT execution-path corrections at main `57e2069414fef32c6a6e4de42bd0dc7fb9f4f1ac`, including the merged parser and failure-telemetry changes from PR #413 and PR #414. Carried statements and baseline status rows retain their inspected source `91fd64ac78025efe1076bddb106ff89e6adb2030` (origin/main, 2026-10-15). They have not been reverified at the newer pin. Accepted requirements and historical evidence retain their original authority and pins.

**Inspected production facts at 91fd64a.** ENFORCEMENT_ACTIVE is False and trusted_snapshot() returns None; no production path constructs ContextAttachment; the shipped alias claude-haiku resolves to anthropic/claude-haiku-4.5; the Gateway web-search provider is Tavily with a Gateway-only key; package/OSV routes still depend on that search configuration; no PyTestArch, maintainability-index, DeepEval, Ragas, PyRIT, Tirith or Vercel dependency, import or test exists; no Rust source exists.

**Historical acceptance stays attached to its pins.** Offline implementation candidate cf9bb9d (Codex review 2026-10-04); documentation filing 5ee081e; operator acceptance of the offline delivery through 2068366 (2026-10-08); merge c509fc8 (PR #276). The deferred live obligations (Luna route/estimator qualification, genuine summary-quality receipt, real-editor Task 13) remain UNRUN under Plan 12.2 ownership (issue #237). Offline acceptance is not production acceptance, a full CP4 pass or permission to remove the shipped model default.

**Controlling Plan 12.2 amendment.** The two preceding paragraphs are carried unchanged from v2.43 and retain their stated pins. The filed 2026-10-18 ordinary shipping amendment, `docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`, still supplies the controlling newer Plan 12.2 statements for §13 and the §14 status rows. It is not folded into this successor.

**Authority.** Codex's architecture wording; local filing by Claude under the operator's 2026-10-24 approval of change list r3 and decisions D1–D4, with the same unpublished editions re-pinned under the operator's 2026-10-24 decision. Local filing is separate from publication to main. This document grants no build, commit, paid or live call, activation, push, PR or merge authority. No product suite was run to author this text.
```

## Edits

### H2 — hld/4

OLD:
```text
- **Agent Mode:** Execution mode. The agent is write-authorised and empowered to actively modify
  code, run tools, create files, update tests, and apply patches within approved workspace
  boundaries. Modifications reach the working tree only through the mediated path:
  `assert_mutation_allowed` / `MutationGuard`, exact artifact approval and `ShadowWorkspaceMutationRunner`,
  which promotes shadow changes only after the composition-supplied fitness checks pass. This guarantee
  covers tool paths that use that runner and is verified by unit and integration tests; it is not a
  host-wide guarantee over processes outside the agent.
```

NEW:
```text
- **Agent Mode:** Execution mode. The agent is write-authorised and empowered to actively modify
  code, run tools, create files, update tests, and apply patches within approved workspace
  boundaries. At `57e2069`, the ACP WRITE/EDIT path requires exact approval of the plan text and
  hash, then `assert_mutation_allowed` / `MutationGuard` and `PreToolGuard`, before a direct
  working-tree write. Plan TESTs run afterwards in the working tree. Shadow execution and pre-write
  fitness checks apply only to compositions using `ShadowWorkspaceMutationRunner`; no ACP
  production path uses it at this pin. An EDIT applicability failure stops the run rather than
  entering fitness-driven replanning. This is not a host-wide guarantee over external processes.
```

### H3 — hld/4

OLD:
```text
  `CodeGenerationScope` enum is not present as such at 91fd64a.
```

NEW:
```text
  `CodeGenerationScope` enum is not present as such at 91fd64a.

  At `57e2069`, a plan declares at most one WRITE/EDIT target. Multi-target mutation directives
  cannot be expressed (#408). This does not confine the effects of TEST subprocesses. The guarded
  write declares `FILE_MUTATION` for WRITE and EDIT alike; EDIT is not assigned `PATCH_PROPOSAL`
  (`src/optimus/agent/directives.py`, `src/optimus/tools/mutation_tools.py`).
```

### H4 — hld/6

OLD:
```text
Key rule: local evidence first, external evidence only when policy-triggered, mutation only after mode and fitness gates pass.
```

NEW:
```text
Key rule: local evidence first, external evidence only when policy-triggered, mutation only after mode gates and, where composed, fitness gates pass. On the ACP Agent-mode WRITE/EDIT path, mutation follows mode, exact approval and guard checks; no fitness gate runs before the write (§7).

The preceding page's “Patch workspace” row (“Shadow apply, diff parser, rollback, working-tree apply”) and “Patch generated → shadow apply + fitness gates” trigger do not describe the ACP WRITE/EDIT path at `57e2069`. EDIT is not a diff. Exact OLD/NEW blocks are parsed by `src/optimus/agent/directives.py`, applied by `src/optimus/agent/edits.py` and written through the guarded write in `src/optimus/tools/mutation_tools.py`. This path uses no diff parser, shadow apply or rollback. Plan TESTs run after the direct working-tree write.
```

### H5 — hld/2

OLD:
```text
- **Feedback Sensors (Post-Generation Evaluation):** Once the primary model provider emits a candidate patch, the engine catches the text stream inside a validation loop. It intercepts execution blocks and evaluates them via automated, triggered fitness functions before any source mutations are applied to the active working tree. The implemented gate is the composite fitness runner in `optimus.gates` (`FitnessGateRunner` over composition-supplied `FitnessCheck` callables, run against the shadow workspace by `ShadowWorkspaceMutationRunner`); the set of checks is supplied by the composition, not fixed by this document.
```

NEW:
```text
- **Feedback Sensors (Post-Generation Evaluation):** Once the primary model provider emits a candidate patch, the engine catches the text stream inside a validation loop. It intercepts execution blocks and evaluates them via automated, triggered fitness functions before any source mutations are applied to the active working tree. The implemented gate is the composite fitness runner in `optimus.gates` (`FitnessGateRunner` over composition-supplied `FitnessCheck` callables, run against the shadow workspace by `ShadowWorkspaceMutationRunner`); the set of checks is supplied by the composition, not fixed by this document. This describes compositions using that runner. On the ACP Agent-mode WRITE/EDIT path, no shadow execution or fitness check precedes the write (§7); an EDIT applicability failure stops the run rather than entering fitness-driven replanning.
```

### H5 — hld/4

OLD:
```text
   approves the code patch execution path.
```

NEW:
```text
   approves the code patch execution path. On the ACP Agent-mode WRITE/EDIT path, no shadow execution or
   fitness check precedes the write (§7); an EDIT applicability failure stops the run rather than
   entering fitness-driven replanning.
```

### H5 — hld/8

OLD:
```text
:::graph
User intent / mode capture
Workspace evidence + Redis metadata + bounded context view (AST/ADL intended)
Trusted eligible fixed model and verified route
Final Gateway input/output guard and upstream attempt
fitness|Complete candidate + shadow fitness checks (composition-supplied)
approval|Exact current approval + mutation gate
Working-tree effects + actual receipt settlement / telemetry
branch|fitness|FAIL -> bounded replan / truthful stop
branch|approval|Denied / stale -> advisory / replan
:::end
```

NEW:
```text
:::graph
User intent / mode capture
Workspace evidence + Redis metadata + bounded context view (AST/ADL intended)
Trusted eligible fixed model and verified route
Final Gateway input/output guard and upstream attempt
fitness|Complete candidate + shadow fitness checks (where composed)
approval|Exact current approval + mutation gate
Working-tree effects + actual receipt settlement / telemetry
branch|fitness|FAIL -> bounded replan / truthful stop
branch|approval|Denied / stale -> advisory / replan
:::end

On the ACP Agent-mode WRITE/EDIT path, no shadow execution or fitness check precedes the write (§7); plan TESTs run afterwards in the working tree. An EDIT applicability failure stops the run rather than entering fitness-driven replanning.

```

### H5 — hld/9

OLD:
```text
| 4. Fitness Functions | Composite fitness gate (`optimus.gates`); PyTestArch and static-metric checks intended, not integrated | Structurally invalid or low-quality changes. |
```

NEW:
```text
| 4. Fitness Functions | Composite fitness gate (`optimus.gates`); PyTestArch and static-metric checks intended, not integrated; no shadow execution or fitness check precedes an ACP Agent-mode WRITE/EDIT write (§7). EDIT applicability failure stops the run without fitness-driven replanning | Structurally invalid or low-quality changes. |
```

### H5 — hld/13

OLD:
```text
Agent execution safety is enforced through a layered guardrail model that wraps every tool call between the moment the agent decides to act and the moment the action takes effect: mode constraints (§7), a permission policy (allow/deny lists with a human-approval path), a pre-tool guard that deterministically validates shell, file, MCP, and network calls, sandboxed execution (the shadow workspace; OS-level sandboxing is not claimed), post-tool audit against the Gateway cost and trace ledgers (§5A, §11, §11A), and commit/CI gates (§12). The same plane governs two execution patterns — bounded goal-driven agent loops and curated workflow skills — so that long-running or procedure-driven work inherits the identical constraints and the same Gateway trust, capacity and accounting policy.
```

NEW:
```text
Agent execution safety is enforced through a layered guardrail model that wraps every tool call between the moment the agent decides to act and the moment the action takes effect: mode constraints (§7), a permission policy (allow/deny lists with a human-approval path), a pre-tool guard that deterministically validates shell, file, MCP, and network calls, sandboxed execution where composed (the shadow workspace; OS-level sandboxing is not claimed), post-tool audit against the Gateway cost and trace ledgers (§5A, §11, §11A), and commit/CI gates (§12). The same plane governs two execution patterns — bounded goal-driven agent loops and curated workflow skills — so that long-running or procedure-driven work inherits the identical constraints and the same Gateway trust, capacity and accounting policy. On the ACP Agent-mode WRITE/EDIT path, no shadow execution or fitness check precedes the write (§7); an EDIT applicability failure stops the run rather than entering fitness-driven replanning.
```

### H6 — hld-15-capability-status.md

OLD:
```text
This section records, for the material capabilities this document names, three independent facts at the inspected source `91fd64ac78025efe1076bddb106ff89e6adb2030` (origin/main, 2026-10-15): whether the capability is implemented, how far it has been verified, and whether it is active. The fields are independent: an implemented guard can be offline-verified and production-inactive; an approved roadmap requirement is not an unapproved idea, but neither is it implemented. A negative repository search supports "integration not established", not a claim that a tool has never been used anywhere. Accepted requirements and historical evidence are unchanged by this section; the correction map filed with the sources (`docs/sources/capability-evidence-correction/correction-map.md`) lists every change with its source reference.
```

NEW:
```text
This section records, for the material capabilities this document names, three independent facts: whether the capability is implemented, how far it has been verified, and whether it is active. Carried statements and baseline rows retain the inspected source `91fd64ac78025efe1076bddb106ff89e6adb2030` (origin/main, 2026-10-15). The fields are independent: an implemented guard can be offline-verified and production-inactive; an approved roadmap requirement is not an unapproved idea, but neither is it implemented. A negative repository search supports "integration not established", not a claim that a tool has never been used anywhere. Accepted requirements and historical evidence are unchanged by this section; the correction map filed with the sources (`docs/sources/capability-evidence-correction/correction-map.md`) lists every change in that correction with its source reference.

Agent-mode localized EDIT statements and the consequent execution-path corrections are at main `57e2069414fef32c6a6e4de42bd0dc7fb9f4f1ac` (2026-10-24), including the merged parser and failure-telemetry changes from PR #413 and PR #414. Other capabilities have not been reverified at this newer pin. EDIT implementation paths in the new row below are under `src/optimus/`. The 2026-10-18 Plan 12.2 ordinary shipping amendment (`docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`) still controls §14.2, §14.4–§14.6 and the §15 Context Engine and registry rows. It is not folded into this successor.
```

### H6 — hld-15-capability-status.md

OLD:
```text
| Mutation guard, shadow workspace and composite fitness gate (§2, §7) | Implemented (`optimus/gates`, `optimus/runtime`) | Unit and integration tests | Active for mediated tool paths |
```

NEW:
```text
| Mutation guard, shadow workspace and composite fitness gate (§2, §7) | Implemented (`optimus/gates`, `optimus/runtime`) | Unit and integration tests | Active for mediated tool paths at `91fd64a`. MutationGuard remains active on ACP WRITE/EDIT at `57e2069`; shadow execution and composite pre-write fitness checks are not composed on that path |
| Agent-mode localized EDIT directive (§7, §8) | Implemented at `57e2069` (`agent/directives.py`, `agent/edits.py`, `agent/models.py`, `agent/planning_loop.py`, `agent/runner.py`, `agent/tools.py`, `agent/prompts.py`, `agent/workspace_context.py`, `loops/tools.py`, `tools/line_endings.py`, `tools/mutation_tools.py`, `runtime/mutation.py`, `telemetry/events.py`, `acp/dispatcher.py`, `acp/spec.py`) | Unit and real-AgentRunner tests; Windows suites and PR CI at `92df22f`, `a970189` and `87b7b06`; post-merge CI at `57e2069`. One live acpx success at `92df22f` only; failure paths have unit/runner evidence only. See EDIT evidence below | Active in Agent mode at `57e2069` |
```

### H6 — hld-15-capability-status.md

OLD:
```text
**Evidence anchors.**
```

NEW:
```text
**EDIT evidence.** Unit and runner tests (`tests/unit/agent/test_edit_directives.py`, `test_edits.py`, `test_runner_edit.py`, through the real `AgentRunner`). PR #411 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/411): Windows full suite failed at `271c16a` with 4 probe import-closure failures; final run at `92df22f`: 9,430 passed, 49 skipped, 101 deselected, 1 warning. guardrails run 40069592519 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40069592519): pull_request, head `92df22f`, success. #407 comment 6382141300 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/407#issuecomment-6382141300): live acpx 0.12.0, Haiku 5.5, 2026-10-24, exact-byte edit of a 110,167-byte file, USD 0.0014817. Failure paths have unit/runner evidence only, not live evidence. These are PR-head results, not merge-commit reruns.

PR #413 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/413), head `a970189`, merged as `159a712`: its reported Windows full suite with coverage gave 9,610 passed, 49 skipped, 101 deselected, 1 warning. guardrails run 40093667921 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40093667921): pull_request, head `a970189`, success. Codex CLI round 55 accepted that head for its full-suite gate; rounds 48–55, including the earlier NOT ACCEPTED reviews, remain on #410 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/410#issuecomment-6384154573).

PR #414 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/414), head `87b7b06`, merged as `57e2069`: its reported Windows full suite with coverage gave 9,431 passed, 49 skipped, 101 deselected, 1 warning; its Codex CLI checkpoint review reported APPROVE. guardrails run 40093673312 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40093673312): pull_request, head `87b7b06`, success. The first Masterplan impact run 40093673253 failed for a missing declaration (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40093673253); replacement run 40094074645 succeeded at the same head (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40094074645).

Post-merge main `57e2069`: guardrails run 40096867014 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40096867014) and Work status page run 40096866988 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40096866988), both push events at that merge head, succeeded. These CI results are separate from the Windows PR-head suites. Neither PR #413 nor PR #414 adds live evidence; the only live run above remains at `92df22f`.

**Evidence anchors.**
```

### L2 — lld/19

OLD:
```text
# 5. ADL parser continuity and architectural evolution
```

NEW:
````text
# 4B. Agent-mode directive plan and localized EDIT

These contracts are implemented at main `57e2069` (#407 / PR #411, with the merged #410 / PR #413 and #412 / PR #414 changes). Source paths in this section are under `src/optimus/`.

## 4B.1 Final plan and grammar

Every Agent-mode plan comes from the multi-turn planning loop (`agent/runner.py:476–495`). The final-plan directive set is READ, WRITE, EDIT and TEST. WRITE replaces the whole file from an opaque body (literal EDIT headers and marker lines remain content), fitting LF/CRLF body breaks to the existing file's uniform style (LF if it has no terminators), retaining its UTF-8 BOM, and replacing the body's last terminator according to the existing file's final-newline convention while preserving earlier empty lines (an empty body clears the text but retains an existing BOM); a new file uses LF and ends as the body does, and a mixed-ending target, including one with a lone CR, is refused unchanged as `WRITE_LINE_ENDINGS_MIXED` (`agent/tools.py:108–142`; `tools/mutation_tools.py:95–111`; `tools/line_endings.py:18–44`). MCP directives are invalid in a final plan.

A model emits EDIT without a base digest:

```text
EDIT <relative-path>
<<<<<<< OLD
<one or more OLD lines>
======= NEW
<zero or more NEW lines>
>>>>>>> END
```

Repeat the block for further changes to the same existing file. Each OLD contains at least one line; NEW may be empty to delete its OLD lines. Markers are whole lines compared after strip. They are reserved at directive positions and within EDIT parsing, with the WRITE-body exception above. A marker outside EDIT, out-of-order markers, an unterminated block, an empty OLD or zero blocks rejects the parse. Only CR, LF and CRLF end EDIT lines. Every non-EDIT plan uses the R1 `plan_lines` split: LF ends a line, CRLF stays paired, terminators are retained, and every other `str.splitlines()` separator is content. In that R1 split, `directive_text` prevents any line holding a content separator from becoming directive syntax. READ, WRITE, EDIT, TEST, MCP_LIST and MCP_CALL tokens use only spaces and tabs as separators and padding. If exact EDIT parsing did not return a valid EDIT, `_invents_an_edit` rejects an EDIT header visible only under `str.splitlines()` outside a WRITE body, even when that EDIT is malformed. One empty LF/CRLF line directly before the next recognized directive separates it from a WRITE body; other lines, including space-only lines, remain content. Planning-loop surface checks keep OLD/NEW bodies opaque and use R1 outside them (`agent/directives.py:10–25`, `:118–213`, `:265–305`, `:319–355`; `agent/planning_loop.py:633–649`).

The model must not supply `base_sha256` (`edit_base="forbidden"`). The harness rewrites only the header to `EDIT <relative-path> base_sha256=<64 lowercase hex>`. Re-parsing proves that nothing else changed (`agent/directives.py:244–276`; `agent/planning_loop.py:817–820`; `agent/runner.py:722–724`). Both prompt grammars document EDIT and the WRITE fitting/refusal rule under `AGENT_PLANNER_PROMPT_VERSION:2026-10-24-p407-edit-p410-write-line-endings` and `MULTI_TURN_PLANNER_PROMPT_VERSION:2026-10-24-p407-edit-p410-write-line-endings` (`agent/prompts.py:10–15`, `:40–50`).

## 4B.2 Evidence and binding before approval

The evidence digest is SHA-256 of the whole file's bytes when evidence was shown to the model. Turn-1 workspace context records it for each included file, whether shown whole or truncated (`agent/workspace_context.py:463–473`). A ranged READ records the whole-file `source_sha256` and `line_endings` from the same byte snapshot; its displayed READ_BLOCK header includes `eol=lf|crlf|mixed|none` (`loops/tools.py:112–130`; `agent/planning_loop.py:534–541`).

Only the final plan's turn counts. Initial-context digests are available only when that is planning turn 1, plus that turn's current reads (`agent/planning_loop.py:1951–1956`). The digest does not establish mechanical grounding of OLD; that remains #258.

`_finish_agent_planning` binds EDIT before calculating the plan hash. No evidence digest gives `EDIT_SOURCE_UNSEEN`; a changed file gives `EDIT_SOURCE_CHANGED`; a missing target with evidence gives `EDIT_TARGET_MISSING`. Binding failure occurs before the hash and approval. Approval text, plan hash and stored record use the bound text (`agent/runner.py:738–756`, `:1982–1994`). Approval shows the exact plan text, without an ACP diff.

## 4B.3 Apply and write

Fresh execution and stored-plan replay use the same sequence; replay never binds an EDIT (`agent/runner.py:1470–1536`):

1. Refuse an unbound EDIT with `EDIT_SOURCE_UNSEEN`.
2. Refuse a target that is not a file with `EDIT_TARGET_MISSING`.
3. Perform a gated raw read with `newline=""`. A decode error gives `EDIT_NOT_UTF8`.
4. Compare the base digest. A mismatch gives `EDIT_SOURCE_CHANGED`.
5. Run `apply_edit_blocks` against the base.
6. Perform the exact gated write through `AgentToolbox.write_file`, which forwards EDIT's `newline=""` and `expected_sha256` to `write_file` rather than the WRITE fitting adapter. The shared `_authorize_file_mutation` runs `assert_mutation_allowed(WRITE_FILE)` / `MutationGuard`, then `PreToolGuard` with `FILE_WRITE` and `generation_scope=FILE_MUTATION`. After the guard allows it, re-hash the target bytes immediately before writing. A mismatch raises `WriteSourceChanged`, a `MutationForbidden`, and gives `EDIT_SOURCE_CHANGED`. The write uses `write_text(encoding="utf-8", newline="")` (`agent/tools.py:104–147`; `tools/mutation_tools.py:67–92`, `:114–140`; `runtime/mutation.py:40–41`). The exact `write_file` primitive now defaults to `newline=""` for every caller.

This is a direct working-tree write after exact approval and guards. The ACP WRITE/EDIT path uses no diff parser, `ShadowWorkspaceMutationRunner`, shadow apply, rollback or pre-write fitness check. The shadow runner is constructed only in `retry/gated_run.py:103`; no production path constructs `GatedRetryRunner`. Plan TESTs run afterwards in the working tree (`agent/runner.py:869–907`, `:1190–1225`). The sequence is not atomic against concurrent external writers.

## 4B.4 Matching and byte preservation

`apply_edit_blocks` matches OLD whole lines exactly once, excluding terminators. Blocks must not overlap and are applied to the base, not successively to earlier replacement results. Only CR, LF and CRLF end a line (`agent/edits.py:55–110`).

A leading BOM is excluded from OLD matching and kept, unless every line is deleted, which leaves zero bytes. NEW lines use the first matched line's terminator, or LF when it has none. The last NEW line keeps the last matched line's terminator. Deleting trailing lines keeps the newly exposed line's existing terminator. Bytes outside matched lines are unchanged.

## 4B.5 Typed failure and lifecycle

The closed applicability codes are `EDIT_TARGET_MISSING`, `EDIT_NOT_UTF8`, `EDIT_SOURCE_UNSEEN`, `EDIT_SOURCE_CHANGED`, `EDIT_OLD_NOT_FOUND`, `EDIT_OLD_NOT_UNIQUE` and `EDIT_BLOCKS_OVERLAP` (`agent/edits.py:15–25`). An applicability failure ends the run with status FAILED and internal stop reason `EDIT_NOT_APPLICABLE`; ACP wire `stopReason` is `refusal` (`acp/spec.py:2212–2221`).

The fixed completion text is:

```text
EDIT not applied to <path> (<code>): <reason>. Nothing was written.
```

During execution, the plan's WRITE terminal is `suppressed`, or `failed_no_effect` after the post-guard digest re-check. Every plan TEST is `suppressed` (`agent/runner.py:1482–1526`, `:1547–1552`). Binding failures occur before approval. Applicability failure stops the run; it does not enter fitness-driven replanning. Ordinary guard, I/O and cancellation failures keep their existing effect classification (`agent/runner.py:203–234`). Completion text is passed through by `acp/spec.py:2121–2122`.

## 4B.6 Logging and persistence

Typed applicability failures and successful application are offered to the opt-in ACP debug trace at `runner.py:edit`, hypothesis `P407-EDIT`. Digests are populated where available: a failure has no result digest, and a binding failure has no base digest. These EDIT debug records contain no file or model content (`agent/runner.py:2002–2012`).

`AgentRunResult.edit_failure_code` is set by `_edit_failure_result` to the specific closed `EDIT_*` applicability code for an `EDIT_NOT_APPLICABLE` run; it is `None` for other runner results. The seven-code vocabulary is enforced by the producing failure paths, not by the field's `str | None` type (`agent/models.py:175–177`; `agent/runner.py:1615–1639`; `agent/edits.py:15–52`).

Always-on `agent_run` telemetry now carries that code in the always-present nullable `edit_failure_code` key beside `stop_reason`; ordinary composition attempts to append it to `.optimus/telemetry.jsonl` (#412 / PR #414). This key carries no path, file or model content. Persistence is attempted, not guaranteed: sink errors are contained. After transport abandonment, ordinary `agent_run` emission is suppressed and no such persistence is attempted (`agent/runner.py:356–361`, `:1320–1350`; `telemetry/events.py:568–611`; `acp/bootstrap.py:129–156`; `telemetry/jsonl.py:34–43`; `telemetry/fanout.py:108–123`).

The ACP `agent/run` result payload also includes `edit_failure_code` because the dispatcher serializes the whole result model; this response field is not itself durable persistence (`acp/dispatcher.py:376–382`). Completion text still carries the code into transient conversation history, and the opt-in EDIT trace still carries it (`acp/spec.py:1589–1597`, `:2121–2122`; `agent/runner.py:2002–2012`). The code is not stored in Redis run metadata or the plan record: the Redis sink maps selected metadata fields and `AgentPlanRecord` has no such field (`telemetry/redis_sink.py:70–86`; `telemetry/redis_adapter.py:30–36`, `:134–146`; `agent/state_store.py:89–114`).

## 4B.7 Retained limits and ownership

| Limit | Owning issue or retained contract |
|---|---|
| At most one declared WRITE/EDIT target; multi-target mutation directives cannot be expressed. This does not confine TEST subprocess effects | #408 |
| Locating the target lines in large files | #409 |
| Mechanical grounding of OLD | #258 |
| No atomicity against external writers | #407 / PR #411 execution contract; `agent/runner.py`, `tools/mutation_tools.py` |
| Exact plan-text approval, without an ACP diff | #407 / PR #411 approval contract; `agent/runner.py` |
| WRITE remains a whole-file replacement, with line-ending/BOM/last-line fitting and mixed-ending refusal implemented at this pin; it does not use EDIT's localized byte-preservation contract | #410 / PR #413 implemented contract; `agent/directives.py`, `agent/tools.py`, `tools/line_endings.py`, `tools/mutation_tools.py` (§4B.1) |

A mixed-ending WRITE raises `WriteRefused` before writing, settles WRITE as `failed_no_effect`, ends the run FAILED with `WRITE_LINE_ENDINGS_MIXED`, and suppresses every plan TEST; ACP forwards the refusal text and reports wire `stopReason=end_turn` (`agent/runner.py:203–234`, `:1272–1297`, `:1455–1465`; `acp/spec.py:2123–2124`, `:2212–2221`). The refusal speaks only for that WRITE and its subsequent TESTs, not earlier planning-turn effects.

The guarded write declares `FILE_MUTATION` for WRITE and EDIT alike; EDIT is not assigned `PATCH_PROPOSAL`. Section 14 records the unit/runner, full-suite, CI and bounded live evidence with their original pins.

# 5. ADL parser continuity and architectural evolution
````

### L3 — lld/14

OLD:
```text
# 4A. Agent lifecycle state machine
:::graph
Idle
Planning
ready|PlanReady
approval|AwaitingApproval (Agent only)
Executing
ToolCalling
validating|Validating / fitness gate
Completed
branch|ready|Plan/Chat -> ChatOnly (read-only)
branch|approval|Denied / timeout -> ChatOnly
branch|validating|FAIL -> Failed -> bounded Planning
branch|validating|Limit / halt -> Terminated
:::end
| Branch | Required transition |
|---|---|
| Plan/Chat | PlanReady -> ChatOnly; no mutation |
| Agent | PlanReady -> AwaitingApproval; current exact approval -> Executing |
| Tool result | ToolCalling -> Validating; PASS -> Executing or Completed |
| Fitness failure | Failed -> Planning only within finite count/time/failure bounds |
| Exhaustion / cancellation | Failed -> Terminated with true reason and retained effects/receipts |
No direct PlanReady -> Executing transition is allowed. Historical approval and model prose cannot bypass the current artifact gate. This figure does not activate Auto routing.
```

NEW:
```text
# 4A. Agent lifecycle state machine
:::graph
Idle
Planning
ready|PlanReady
approval|AwaitingApproval (Agent only)
Executing
ToolCalling
validating|Validating / fitness gate (where composed)
Completed
branch|ready|Plan/Chat -> ChatOnly (read-only)
branch|approval|Denied / timeout -> ChatOnly
branch|validating|FAIL -> Failed -> bounded Planning
branch|validating|Limit / halt -> Terminated
:::end
For ACP WRITE/EDIT at `57e2069`, exact plan approval is followed by `assert_mutation_allowed` / `MutationGuard` and `PreToolGuard`, then a direct working-tree write. There is no Validating/fitness step or shadow execution before that write. Plan TESTs run afterwards in the working tree. An EDIT applicability failure stops the run without fitness-driven replanning (§4B).

| Branch | Required transition |
|---|---|
| Plan/Chat | PlanReady -> ChatOnly; no mutation |
| Agent | PlanReady -> AwaitingApproval; current exact approval -> Executing |
| Tool result | ToolCalling -> Validating where fitness is composed; PASS -> Executing or Completed. The ACP WRITE/EDIT path is the exception below (§4B) |
| Fitness failure | Failed -> Planning only within finite count/time/failure bounds |
| Exhaustion / cancellation | Failed -> Terminated with true reason and retained effects/receipts |
No direct PlanReady -> Executing transition is allowed. Historical approval and model prose cannot bypass the current artifact gate. This figure does not activate Auto routing.
```

### L3 — lld/16

OLD:
```text
| Shadow apply patch | No | Yes | assert_mutation_allowed gate |
| Mutate working tree | No | Yes | assert_mutation_allowed + MutationGuard + approval |
| Shell / build / test | No | Yes | Agent mode and applicable fitness/approval gates |
```

NEW:
```text
| Shadow apply patch | No | Yes | assert_mutation_allowed gate; not used by ACP WRITE/EDIT at `57e2069` (§4B) |
| Mutate working tree | No | Yes | ACP WRITE/EDIT: exact plan approval, then assert_mutation_allowed / MutationGuard and PreToolGuard, then direct working-tree write; no shadow execution or pre-write fitness check (§4B) |
| Shell / build / test | No | Yes | Agent mode, approval, applicable guards and fitness gates where composed; ACP plan TESTs run after the write in the working tree, not as pre-write fitness checks (§4B) |
```

### L3 — lld/17

OLD:
```text
| Feedback | Complete finish required for executable candidate; shadow validation and fitness gates |
```

NEW:
```text
| Feedback | Complete finish required for executable candidate. ACP WRITE/EDIT: exact approval, then assert_mutation_allowed / MutationGuard and PreToolGuard, then direct working-tree write and plan TESTs afterwards. No shadow execution or fitness check precedes the write; EDIT applicability failure stops the run without fitness-driven replanning (§4B) |
```

### L4 — lld-13-context-integration.md

OLD:
```text
A WRITE-bearing result is usable only with a verified complete successful finish.
```

NEW:
```text
A WRITE- or EDIT-bearing result is usable only with a verified complete successful finish.
```

### L5 — lld-13-context-integration.md

OLD:
```text
Maintain Task 2's real WRITE/TEST registration, start gates, terminal evidence and cancellation behavior.
```

NEW:
```text
Maintain Task 2's real WRITE/TEST registration, start gates, terminal evidence and cancellation behavior. At `57e2069`, EDIT registers and settles as the plan's WRITE operation, plus its read-before-write READ. During execution, `EDIT_NOT_APPLICABLE` settles WRITE as `suppressed`, or `failed_no_effect` after the post-guard digest re-check; every TEST is `suppressed`. Binding failure is before approval. Applicability failure stops the run without fitness-driven replanning (§4B).
```

### L6 — lld-14-capability-status.md

OLD:
```text
This section classifies the executable contracts this document specifies at the inspected source `91fd64ac78025efe1076bddb106ff89e6adb2030` (origin/main, 2026-10-15). Implementation, verification and activation are independent fields. Conceptual or retained-prototype interfaces are labelled as such where they appear; this table is the collected view. It changes no accepted contract. The correction map filed with the sources (`docs/sources/capability-evidence-correction/correction-map.md`) lists each change and its source reference.
```

NEW:
```text
This section classifies the executable contracts this document specifies with carried statements and baseline rows at the inspected source `91fd64ac78025efe1076bddb106ff89e6adb2030` (origin/main, 2026-10-15). Implementation, verification and activation are independent fields. Conceptual or retained-prototype interfaces are labelled as such where they appear; this table is the collected view. It changes no accepted contract. The correction map filed with the sources (`docs/sources/capability-evidence-correction/correction-map.md`) lists each change in that correction and its source reference.

Agent-mode EDIT statements and the consequent execution-path corrections are at main `57e2069414fef32c6a6e4de42bd0dc7fb9f4f1ac` (2026-10-24), including the merged parser and failure-telemetry changes from PR #413 and PR #414. Other contracts have not been reverified at this newer pin. EDIT implementation paths in the new row below are under `src/optimus/`. The 2026-10-18 Plan 12.2 ordinary shipping amendment (`docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`) still supplies the controlling newer Plan 12.2 statements for §13 and the §14 status rows. It is not folded into this successor.
```

### L6 — lld-14-capability-status.md

OLD:
```text
| Composite fitness engine scaffolding (§7, carried page) | Illustrative scaffolding; the implemented runner is `optimus/gates/fitness.py`; the placeholder architecture and metric gates have no PyTestArch or maintainability-index implementation | Unit tests of the runner | Active for composition-supplied checks |
```

NEW:
```text
| Composite fitness engine scaffolding (§7, carried page) | Illustrative scaffolding; the implemented runner is `optimus/gates/fitness.py`; the placeholder architecture and metric gates have no PyTestArch or maintainability-index implementation | Unit tests of the runner | Active for composition-supplied checks; not composed on the ACP WRITE/EDIT path at `57e2069`, which has no pre-write fitness check |
| Agent-mode EDIT directive (§4B) | Implemented at `57e2069` (`agent/directives.py`, `agent/edits.py`, `agent/models.py`, `agent/planning_loop.py`, `agent/runner.py`, `agent/tools.py`, `agent/prompts.py`, `agent/workspace_context.py`, `loops/tools.py`, `tools/line_endings.py`, `tools/mutation_tools.py`, `runtime/mutation.py`, `telemetry/events.py`, `acp/dispatcher.py`, `acp/spec.py`) | Unit and real-AgentRunner tests; Windows suites and PR CI at `92df22f`, `a970189` and `87b7b06`; post-merge CI at `57e2069`. One live acpx success at `92df22f` only; failure paths have unit/runner evidence only. See EDIT evidence below | Active in Agent mode at `57e2069` |
```

### L6 — lld-14-capability-status.md

OLD:
```text
**Activation prerequisites, restated.**
```

NEW:
```text
**EDIT evidence.** Unit and runner tests (`tests/unit/agent/test_edit_directives.py`, `test_edits.py`, `test_runner_edit.py`, through the real `AgentRunner`). PR #411 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/411): Windows full suite failed at `271c16a` with 4 probe import-closure failures; final run at `92df22f`: 9,430 passed, 49 skipped, 101 deselected, 1 warning. guardrails run 40069592519 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40069592519): pull_request, head `92df22f`, success. #407 comment 6382141300 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/407#issuecomment-6382141300): live acpx 0.12.0, Haiku 5.5, 2026-10-24, exact-byte edit of a 110,167-byte file, USD 0.0014817. Failure paths have unit/runner evidence only, not live evidence. These are PR-head results, not merge-commit reruns.

PR #413 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/413), head `a970189`, merged as `159a712`: its reported Windows full suite with coverage gave 9,610 passed, 49 skipped, 101 deselected, 1 warning. guardrails run 40093667921 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40093667921): pull_request, head `a970189`, success. Codex CLI round 55 accepted that head for its full-suite gate; rounds 48–55, including the earlier NOT ACCEPTED reviews, remain on #410 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/410#issuecomment-6384154573).

PR #414 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/414), head `87b7b06`, merged as `57e2069`: its reported Windows full suite with coverage gave 9,431 passed, 49 skipped, 101 deselected, 1 warning; its Codex CLI checkpoint review reported APPROVE. guardrails run 40093673312 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40093673312): pull_request, head `87b7b06`, success. The first Masterplan impact run 40093673253 failed for a missing declaration (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40093673253); replacement run 40094074645 succeeded at the same head (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40094074645).

Post-merge main `57e2069`: guardrails run 40096867014 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40096867014) and Work status page run 40096866988 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40096866988), both push events at that merge head, succeeded. These CI results are separate from the Windows PR-head suites. Neither PR #413 nor PR #414 adds live evidence; the only live run above remains at `92df22f`.

**Activation prerequisites, restated.**
```

## docs/README.md

### D1 / H1 — HLD index row

OLD:
```text
| [Architecture (HLD) v2.20](Optimus-Cost-Agent-Architecture-v2.20.pdf) | High-level design; v2.20 is the capability and evidence correction of 2026-10-15 (reviewed local filing candidate); its Context Engine and registry sections are amended by the [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) |
```

NEW:
```text
| [Architecture (HLD) v2.21](Optimus-Cost-Agent-Architecture-v2.21.pdf) | High-level design; Agent-mode localized EDIT and consequent execution-path corrections at `57e2069` (2026-10-24); carried statements and baseline status rows retain `91fd64a` provenance. The [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) still controls §14.2, §14.4–§14.6 and the §15 Context Engine and registry rows |
```

### D1 / L1 — LLD index row

OLD:
```text
| [LLD v2.43](Optimus-Cost-Agent-LLD-v2.43.pdf) | Low-level design; v2.43 is the capability and evidence correction of 2026-10-15 (reviewed local filing candidate); its §13 and §14 status rows are amended by the [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) |
```

NEW:
```text
| [LLD v2.44](Optimus-Cost-Agent-LLD-v2.44.pdf) | Low-level design; Agent-mode directive plan and localized EDIT (§4B), with consequent execution-path corrections at `57e2069` (2026-10-24); carried statements and baseline status rows retain `91fd64a` provenance. The [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) still supplies the controlling newer Plan 12.2 statements for §13 and the §14 status rows |
```

### D1 — New sources-bundle row

OLD:
```text
| [Capability and evidence correction sources](sources/capability-evidence-correction/) | Sources, authoring tools, correction map and validation record for HLD v2.20, LLD v2.43, Roadmap v11 and Test Strategy v1.9, and the Guardrails v1.5 cover |
```

NEW:
```text
| [Agent-mode localized EDIT successor sources](sources/agent-localized-edit/) | Sources, replaced page bodies, authoring driver and validation record for HLD v2.21 and LLD v2.44; preserves the mixed provenance and the separate Plan 12.2 ordinary shipping amendment |
| [Capability and evidence correction sources](sources/capability-evidence-correction/) | Sources, authoring tools, correction map and validation record for HLD v2.20, LLD v2.43, Roadmap v11 and Test Strategy v1.9, and the Guardrails v1.5 cover |
```

## Author notes

- r4 revises the same unpublished HLD v2.21 / LLD v2.44 editions under the operator's 2026-10-24 re-pin decision. All production assertions added by this successor use main `57e2069414fef32c6a6e4de42bd0dc7fb9f4f1ac`; `d13fd34` appears only as PR #411 merge history. Carried `91fd64a` provenance and the separate Plan 12.2 amendment remain unchanged.
- H1/L1 — changed both inspected pins, named the merged PR #413/#414 parser and failure-telemetry follow-through, retained PR #411's merge as history, and added the re-pin decision to Authority. Predecessor identities, carried acceptance text, D2/D3 qualifications and edition numbers are unchanged.
- H2, H3 and H4 — changed their ACP execution-path pins to `57e2069`; their execution and scope statements still hold. All five H5 blocks are unchanged.
- H6 — changed the status introduction and both affected rows to the new pin; added `agent/models.py`, `tools/line_endings.py`, `telemetry/events.py` and `acp/dispatcher.py` to the implementation list. The verification cell and evidence note now distinguish #407's `92df22f` results, PR #413's `a970189` results, PR #414's `87b7b06` results and post-merge main `57e2069` CI. The `271c16a` failure and original #407 live receipt remain.
- L2 introduction and §4B.1 — re-pinned and identified the merged follow-through; replaced the legacy non-EDIT split statement with R1, spaces/tabs syntax, content-separator protection, `_invents_an_edit` and the WRITE separator convention. Replaced WRITE's one-sentence semantics with the implemented fitting and mixed-ending refusal. Updated model/bound-header references and both complete prompt-version strings.
- L2 §4B.2 — added snapshot-bound `line_endings` / `eol=` evidence and recomputed the ranged-read, final-turn and binding references. The whole-file hash and approval contracts are unchanged.
- L2 §4B.3 — described the toolbox's exact EDIT writer versus WRITE fitting, the shared `_authorize_file_mutation`, and the exact writer's `newline=""` default; recomputed execution, guard and TEST references. §4B.4 is unchanged; its `agent/edits.py:55–110` reference remains correct.
- L2 §4B.5 — recomputed the code-vocabulary, wire projection, WRITE/TEST-terminal, ordinary failure and completion-text references. The seven EDIT codes and lifecycle contract are unchanged.
- L2 §4B.6 — replaced the unimplemented #412 follow-up with the implemented nullable result/telemetry field, producer-enforced vocabulary, ACP result projection and precise persistence boundaries. Recomputed trace and emission references; added event, JSONL, dispatcher, conversation, Redis metadata and plan-record references. Retained sink-error containment and transport-abandonment qualifications.
- L2 §4B.7 — replaced the obsolete unchanged-WRITE / future-#410 row with #410 / PR #413's implemented fitting contract and its distinction from localized EDIT. Added the typed mixed-ending refusal, FAILED run, `failed_no_effect` WRITE, suppressed TESTs, ACP `end_turn`, and the refusal's scope. The other limit owners are unchanged; no issue/PR status is copied into the design text.
- L3 — re-pinned lld/14 and lld/16; lld/17 is unchanged. L4 is unchanged. L5 — re-pinned the EDIT registration and settlement statement; its contract is unchanged.
- L6 — made the corresponding status-introduction, row, implementation-list and evidence-note changes described for H6; retained its composite-fitness qualification and D2/D3 boundaries.
- docs/README.md — re-pinned the HLD and LLD rows. The new sources-bundle row is unchanged. All 23 OLD anchors, block identifiers, block order and wrappers are unchanged. Build strings retain their r3 values; only the final verification/risk note now names r4.
- Delta correction — the unconditional shorthand that WRITE keeps the existing file's final-newline state is too strong: `fit_body_to_file` replaces only the body's last terminator and preserves earlier empty lines; an empty body clears text while retaining an existing BOM. For example, existing `b"x"` and body `"y\n\n"` yield `"y\n"` by the inspected procedure. The revised sentence states that procedure. No other delta fact was contradicted by the pinned source. The ACP result-field claim and the absence from Redis metadata / plan records were independently verified.
- Evidence qualification — Windows counts and CLI review verdicts are attributed to their PR/issue records, not rerun here. PR #413's round-55 verdict is ACCEPT for its full-suite gate, not operator approval. PR #414's first Masterplan impact failure (40093673253, missing declaration) remains alongside its replacement success (40094074645). Neither new PR supplies a live run.
- Read-only verification — inspected production files only through `git show 57e2069:<path>` and the requested baseline-to-pin `git diff`. `gh` failed on inaccessible configuration, then required authentication with a configuration-free directory; the connected GitHub reader supplied the same read-only PR/issue records and linked workflow evidence. All 23 OLD anchors were checked for sequential uniqueness against the new pin; their contents match r3 exactly. No files or GitHub records were changed.

Not run: PDF rebuild/rendering, product tests or new live calls.  
Risk: r4 pagination, table fit and rendered carried-body verification require the filing rebuild.

## Build strings

- Page-header `LABEL`: `LOCAL FILING - NOT ACTIVATED`  
  Reason: identifies the filed local editions while preserving the activation boundary; “candidate” and “draft” no longer describe their filing state.
- Footer: `Agent-mode localized EDIT | 2026-10-24`  
  Reason: the subject and edition date are unchanged.
- PDF `/Title` suffix: ` - Agent-mode localized EDIT (local filing - not activated)`  
  Reason: matches the filing label using the existing title format and keeps local filing distinct from activation or publication to main.

Not run: r4 PDF rebuild/rendering or product tests.  
Risk: the filing build requires fresh hashes and layout verification.
