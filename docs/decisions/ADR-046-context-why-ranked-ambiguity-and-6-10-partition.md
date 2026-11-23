# ADR-046: `/why` explains a session's last context preparation; ambiguity stops are ranked and never chosen; planning evidence is split 6 KiB/10 KiB

**Status:** Proposed. It records mechanisms that Plan 12.13 delivered
([#545](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/545); children
[#242](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/242) and
[#245](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/245)). Codex reviews it at CP3. Operator acceptance is
separate. Drafted by Claude. **Publication:** editable in pre-merge review, frozen byte for byte on first merge to `main`.

**Relationship:**
- **Implements** Plan 12.13's decisions D2–D4 as the operator approved them (Context, below).
- **Changes** Plan 9.85's fixed 4 KiB/12 KiB observation/current-read partition. The 16 KiB combined ceiling is unchanged.
- **Narrows** Plan 12.2's exact history selection in one respect (Decision 4). Everything else in that contract is unchanged.
- **Unchanged:**
  - [ADR-039](ADR-039-provider-cache-breakpoint-after-the-map.md) and [ADR-041](ADR-041-prefix-prompt-caching-on-by-default.md):
    the cache breakpoint and wire shape. The partition changes only the bytes inside the prefix.
  - [ADR-025](ADR-025-models-are-configuration-per-model-admission.md): models stay configuration.
  - [ADR-044](ADR-044-explicit-user-actions-for-user-memory.md): who may change memory.

## Context and provenance

Plan 12.13 v3, SHA-256 `26653bbc2123e66d990d37977f9ab81a6ded9121de7594e358b0c9fdad31ffa0`, carried four open decisions with
agent recommendations. The operator approved the plan and all four in Claude chat on 2026-11-23: "Approve hash + D1-D4". That
quote is as recorded in `reports/plan12-memory-m2a/authority.json`; no transcript export was taken. The recommendations
below are agent text, quoted from the approved plan, and the operator adopted them by that approval:

> D2 — `/why` lifetime: Explain this ACP session’s last terminal, non-command context-preparation attempt. Keep its snapshot in
> RAM; report unavailable after restart/resume without it. Never infer “last turn” from diagnostic timestamps.
>
> D3 — Target authority: Rank suggestions; require an exact workspace-relative path whenever multiple eligible targets remain.
> Ranking never authorizes a target.
>
> D4 — Partition: Calibrate a replacement fixed byte partition from the alternatives below. Preserve the 16 KiB combined ceiling
> and route fitting.

D1 (filing) is recorded in `authority.json` and is not a mechanism.

Under v3, no alternative partition qualified: an exact probe at 4/12's own read limit made every alternative lose. Codex ruled
at CP1 (round 117) that 4/12 should be retained and the plan should stop. The operator then directed "Draft plan successor".
Codex authored v4, in which boundary probes became rejection gates at each candidate's own limits. The operator approved v4,
SHA-256 `d25783eb95517c00c14d9907376e1a71c045b9c5c61235b136566263740013d3`, with "Approve v4 hash" (as recorded in
`authority.json`).

Decisions 4 and 5 below came from Task 4's live runs, not from the plan. Decision 4 follows Codex's round-120 design ruling,
which is posted verbatim on #545. Decision 5 follows an earlier recorded rule for the same Zed behaviour.

## Options considered

| Question | Options | Outcome |
|---|---|---|
| What `/why` explains | A RAM snapshot per session (D2); the newest manifest on disk; re-running retrieval | The snapshot. Disk manifests cannot establish which turn was a session's last, and re-running retrieval would describe today, not the turn |
| Who picks among several eligible files | Rank and require an exact path (D3); pick automatically above a score threshold; keep path order | Rank and require. Ranking is not confidence, and a wrong target edits the wrong file |
| The partition | 2/14, 4/12, 6/10 and 8/8 KiB, calibrated on frozen schedules (D4) | 6/10 (Decision 3) |
| What a turn that did not complete contributes to later selection | A: its prompt and plan, not its host notice; B: only the current prompt's references select; C: unchanged | A (Codex, round 120). B changes Plan 12.2's contract; C leaves the retry broken |
| How a visible workspace stop ends an ACP turn | `refusal`; `end_turn` | `end_turn`. Zed hides a refused turn's text |

## Decision

### 1. `/why`

- **What it explains.** `/why [page]` explains this ACP session's last terminal context-preparation attempt. That includes an
  attempt that was blocked, failed or cancelled. A command never replaces the snapshot.
  - If a later prompt is refused before preparation, page 1 opens with a note that the explanation still covers the earlier
    turn.
- **How it is captured and kept.** The snapshot is captured once, in the prompt turn's `finally`, from the facts assembly and
  dispatch actually produced. It is kept in RAM and bound to its session; each session explains only its own turns.
- **After a restart.** There is no snapshot, and `/why` says so. Diagnostic manifests on disk are never shown, because they
  cannot establish this session's last turn.
- **What it shows:**
  - identity and delivery: outcome and stop, how many times context was prepared, the main model requests the host sent and the
    planning rounds. Each request is listed under its own planning round, with retries counted, from the round and attempt the
    planning loop recorded as it sent the request. The Gateway's own route attempts inside one request are not host requests and
    are not counted. An Auto classifier call is not a main model request;
  - choices, with ranked candidates for an ambiguity;
  - fit: bytes and tokens used against their limits, including the partition;
  - grounding and scope;
  - memory served, as `id@version`.
- **What it never shows:** file bodies, prompts, memory statements or reasoning.
- **Privacy:**
  - Every path passes today's file policy. A typed name is checked by name (`FilePolicy.name_admitter`), whether or not a file
    has it.
  - A path denied today is shown as "(a file not disclosed now)", and its reasons are hidden.
  - Grounding symbols are shown as counts.
  - Output goes through the workspace-aware conversation sanitizer and Markdown escaping.
- **Paging.** At most 40 entries and 12 KiB per page; the byte limit counts the header, navigation and markers. Pages run up to
  1000. The page argument must be ASCII digits; anything else gets the usage line. `/why 0` names the valid range, and a page
  past the end names the last.
- **No calls.** `/why` is answered on the local command path. It makes no classification, maintenance, extraction, embedding or
  provider call, and its answer does not enter later prompts.
- **What the explanation does not prove.** It describes the turn as prepared. It does not show that those files, ranks or
  memory items are still current.

### 2. Ranked ambiguity (#242)

- **One policy for both paths.** Ordinary workspace assembly and `MemoryTurn.assemble` share `rank_candidates`.
- **Eligibility.** The file policy and scope decide which candidates are eligible. Ranking never removes one.
- **Order:**
  1. task-term relevance (the ambiguous basename excluded);
  2. verified dependency proximity to paths the task resolves on its own;
  3. verified-current index metadata;
  4. workspace-relative path.
- **Index hints.** Only current, verified index hints count; stale or missing hints contribute nothing. A session's first
  ambiguity reads the scope's map itself, because the runner assembles a turn before its prompt reads the map.
- **Ambiguity always stops.** With more than one eligible target, the turn stops whatever the scores. The stop lists the
  candidates "most likely first", with their reasons, and says "The order is a suggestion and chose nothing."
- **What settles an ambiguity.** Only an exact workspace-relative path in the person's own current prompt. Ranking uses that
  prompt alone. Earlier turns' text never settles an ambiguity, never adds ranking terms and is never a dependency anchor.

### 3. Partition (#245)

- **The limits.** `PLANNING_OBSERVATION_MAX_BYTES = 6 * 1024` and `PLANNING_NEW_READ_MAX_BYTES = 10 * 1024`. Both count UTF-8
  serialized bytes, headers included, and every consumer reads these two constants.
- **Calibration** (train and development, frozen cases v4, every request fitted by the shipped `ContextPacker.fit` on the
  ordinary implementer route):
  - Non-boundary schedules: 6/10 completes 8 of 9, against 4/12's 4, with no loss among 4/12's successes.
  - Every own-limit probe passes: an exact probe completes with whole evidence, and a one-over probe gives a typed budget stop.
- **Held-out qualification**, consumed once at `b6dd92b`: schedules S08 and S23 gain completions, nothing is lost, and all 7
  probes pass.
- **The capacity trade.** One turn's current reads drop from 12288 to 10240 bytes. A turn that needs 10–12 KiB of reads at once
  no longer fits; schedule S10 records that lost success. No capacity-preservation claim is made.
- **F2.** A turn rejected with `OBSERVATION_TOO_LARGE` reads nothing, and the earlier evidence carries forward. A plan binds the
  evidence digests it saw, and an EDIT of an unseen file is refused with `EDIT_SOURCE_UNSEEN`. No recovery change was needed.

### 4. A turn that did not complete selects only by its prompt and plan

`build_selection_text` takes an earlier turn's `completion_text` only when that turn's protected outcome is `COMPLETED`.
- **Why.** A failed, rejected or cancelled turn ends with the host's own notice. An ambiguity stop lists every candidate, so
  without this rule the retry required them all. An unchosen candidate that was too large or unreadable would even block it.
- **What is unchanged.** This filters selection only. Canonical records, the history the model sees, and approval and effect
  facts stay as they were.
- **What it does not cover.** A history mention that is unreadable, too large, or ambiguous without a path still blocks later
  turns. That is Plan 12.2's behaviour, kept for now, and #555 owns it.

### 5. A visible workspace stop ends the turn normally

Three stops already send the person their corrective text: `AMBIGUOUS_WORKSPACE_REFERENCE`,
`REQUIRED_WORKSPACE_FILE_TOO_LARGE` and `WORKSPACE_REFERENCE_NOT_READABLE`. They now end with stopReason `end_turn`. Their
conversation outcome stays `FAILED`.
- **Why.** Zed rewinds a turn that ends as `refusal` behind a generic content-policy banner, which hid the ranked candidates.
  The same rule already applies to planning terminals, an expired plan, the mixed-line-endings refusal and a full
  conversation; spec.py records the Zed behaviour there (sandbox live check, 2026-09-29).

## Consequences and limits

- `/why` cannot explain a turn from before a restart or resume.
- `/why` reports main model requests only, and says so. An Auto classifier call is not one of them.
- Served memory IDs are unit-tested only. No memory store was released for the live runs.
- The held-out ranking gain carries the disclosed author bias. The index-order comparison is an offline replay of recorded
  index metadata.
- Paid answer quality, model-aware budgets and refinements of the ranking remain with Plan 12.14 (#548).

## Evidence

All under `reports/plan12-memory-m2a/`:
- **Calibration and partition:** `calibration.json`, `split.json`, `qualification.json`, `determinism.json`,
  `cache-identity.json`.
- **Live and boundary runs:** `boundaries.json` (real index), `acpx.json`, `zed-ui.json`, `platforms.json` (P1/P2 on Windows and
  WSL).
- **Reversions:** `revert-checks.json`.
- **`/why` and ranking:** `why.json`, `ambiguity.json`.

Earlier evidence never tests later bytes; each record names its code head.
