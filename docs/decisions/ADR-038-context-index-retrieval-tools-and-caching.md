# ADR-038: A turn gets ranked, verified context and four read-only tools from the context index

**Status:** Proposed. The operator approved Plan 12.10, including the cost bound D7 and the plan's context and tool design, at its exact hash on 2026-11-03
(verbatim below). Codex reviews the mechanism at the plan's third checkpoint; operator acceptance of this record is separate. Delivered under Plan 12.10
([#469](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/469)). Drafted by Claude.

**Relationship:** builds on the storage, setup and worker of [ADR-037](ADR-037-context-index-storage-setup-and-worker.md), and extends the existing context attachment and
automatic workspace path rather than replacing them. Unchanged: alerts, not limits ([ADR-005](ADR-005-cost-alerts-not-limits.md)); models are configuration
([ADR-025](ADR-025-models-are-configuration-per-model-admission.md)), so caching is a route setting and no model is named here. Intended-new-file and version grounding stay with
[#258](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/258); `/why` is M2. There is no memory store yet, so the memory channel is empty.

## Context

An index that nobody reads saves nothing. A turn needs the right evidence inside its budget, must not present a stale or other-branch record as current, must not claim something is
absent when the index could not see it, and must never fail because the index did. A model that wants to look further needs tools no more powerful than reading. Chat in particular must
stay bounded, and a person's unsaved edit is often the thing they are asking about.

## The operator's decision (2026-11-03, verbatim, Claude's Plan 12.10 chat)

"Approve this hash", for Plan 12.10 at SHA-256 `f136397fe605d51bd6dfee1ab4ed8705e7c3a45d05eb52b6c5cf569a7d02adb1`. Its text fixes Chat's "agent-selected cap" as "4 read-only rounds then one
tools-disabled final answer", and its D7 recommends "Zero paid calls for #465, setup, indexing, tool/protocol plumbing and P5-a". For the unsaved buffer it requires that an "advertised
`fs.readTextFile` gates `fs/read_text_file`", and that "Unsupported/inconclusive/unreleased ships explicit disk-only fallback".

## Options considered

| Decision | Option | Outcome | Reason |
|---|---|---|---|
| Ranking | Reciprocal rank fusion of lexical, dense, structure, recency and memory | Chosen (plan) | Channels with incomparable scores combine without calibration. A rank says how channels agreed and is not confidence. |
| | Inferred edges or a graph | Rejected (plan) | Structure means what was named or observed in imports. |
| A record's file has changed | Leave it out and report it, ask the worker to reconcile, retry at most twice | Chosen (plan) | A stale signature reads as true. A short bounded wait usually gets the new record, and a turn never waits longer. |
| | Show it with a warning | Rejected | The model cannot unread it. |
| Tools | Four read-only verbs in the existing reply grammar and guard | Chosen (plan) | No new MCP server and no new authority: each tool passes the FILE_READ guard, and the file policy decides each file. |
| Chat's bound | 4 rounds, then one call with tools withdrawn | Chosen (plan) | The model gets a last chance to answer from what it found, and there is never a fifth search. |
| | Stop at the limit with no answer | Rejected | Throws away what the rounds found. |
| Unsaved text | Ask the client for the files the task names, keep what differs in this turn's memory | Chosen, subject to the Zed proof | It answers the common question with no new store. If Zed's proof fails or is not released, the host stops asking and `zed-ui.json` records the plan's disk-only fallback. |
| | Search across all unsaved buffers | Rejected (plan) | The protocol has no such operation, and asking for every file is a global unsaved search. |
| | Index or embed unsaved text | Rejected (plan) | It would persist what the person has not saved. |
| Agent-selected | Judge a listing by name, and refresh it when something is missing or a disk tool runs | Chosen | Named files, tools and grounding see a file made seconds ago. A full policy walk reads every file: 34 to 47 seconds on Hadoop's 15,499 files, against 1.8 seconds by name. |
| Agent-selected | During a build, reuse a catalogue for up to 60 seconds across publications | Chosen | A catalogue only suggests what to ask for, and every record is then asked for at the retrieval's own epoch, so an older one can miss a new file but cannot make a record current. Without it, a turn during a large build could spend dozens of calls on pages. A complete generation never reuses one. |

## Decision

The mechanism below is an agent recommendation that the operator approved through the plan; names and limits are agent-selected until targets freeze them.

### One turn's context

A session runs one background worker and recomputes its scope each turn and each pass, so changing branch moves to that branch's own line at once. A pass that ends just after a switch never vouches for
the new line, even at the same commit, and once the worktree has left a pass's branch that pass may write nothing more. Ignore files are read again at each turn, tool, map and grounding check, because a policy keeps them once read. One retrieval pins one published epoch; an epoch that expires under it is tried again, never answered in part. Reciprocal rank fusion uses k = 60 and
weights lexical 1.0, dense 1.0, structure 1.5, recency 0.25, memory 1.0, with stable ties, frozen before evaluation.

The pack is required evidence whole, then signatures from a quarter of the room left, then verified bodies. Its budget is the smaller of a quarter of the route's usable input and 16,384
tokens. A body is shown only if the file on disk still has the bytes the index saw. A hash mismatch gives neither the body nor the signature. Required evidence that does not fit is a
refusal, which Agent turns into ranged reads, and is never quietly dropped. A coverage line states the generation, whether it is complete, what each channel did and what was left out, and
that saying something is absent covers only this scope.

The repository map sits in the cacheable prefix and its input is refreshed at most once in five minutes during a build. What it renders is checked on every use: a file now refused or gone leaves at
once, and one that changed keeps its path and loses its symbols. A cache's age never makes a record true, so a change costs that request its cached prefix.

Anything short of a usable index gives today's selection plus a line saying so. A channel that cannot answer, including an embedder that raises, is reported and the rest carry on. The wait for a repair
happens outside the turn's foreground claim, because the worker gives way to a busy turn and could not otherwise do the repair.

### Tools

`SEARCH`, `OUTLINE`, `SYMBOLS` and `LIST` are accepted only as a whole reply of at most four lines. Results are at most 8 KB and state what they covered. A quoted `SEARCH` and `OUTLINE` read
at query time and stay in memory. An index result whose file changed is dropped and counted. A search channel that did not answer is named, so it is never read as "no matches". Terms and
names the route would refuse are left out before they reach it. Disk tools list by name rather than by what the index may hold, so a file too large to index can still be listed and searched, and they name any folder that could not be listed and any file that could not be read. A repeated request is not run again, and a reply of only repeats ends the rounds. Each call records one `tool_call` telemetry event under the same id as its card, with a path argument as it is and search text only as a digest and length, since it can quote source. Tools run in Chat and Agent; Chat executes
no directive either way, and Agent's rounds add to its planning allowance and stop being grammar after four.

### Provider caching

A route's `prompt_cache` is `none`, `implicit` or `top_level`. Absent keeps every approved hash, pinned by digests exported before the change. Only `top_level` changes the wire, adding the
root `cache_control` beside `provider`, and it changes the payload digest so disclosures still cover what is sent. The indexed prompts put what changes last: fixed text and grammar, map, history,
pack, results, then the question or task and per-call lines. Without an index both prompts are byte-identical to before. The map changes at most once in five minutes during a build.

### The unsaved buffer (P5-a)

Only a client that advertised exactly `fs.readTextFile: true` is asked, only for files the task names, and only after the file policy admits them. Text that differs from disk, ignoring line
endings, is used for this turn's pack, tools and grounding, and the coverage line says so. The policy judges again at each use, so unsaved text it has since refused goes as the file on disk would. `SYMBOLS` lists its symbols marked unsaved, and the index's records of that file no longer count. It is never indexed, embedded or written to a manifest, which names only the path and hash. A refusal, a malformed
reply, a two second wait, a binary buffer or one over 8 MiB leaves the turn on disk, and a cancel ends the wait at once and asks for nothing more. The pack's digest is of the unsaved text, so an `EDIT` bound to it is refused until the file on disk agrees.

### Grounding and the manifest

After a reply, a card names cited files and symbols the inspected scope does not hold, or that match more than one file. It reports and decides nothing, and it never fails a turn. Symbols are judged on verified records and this turn's unsaved text. It claims one is absent only from a complete generation of exactly what is on disk now, with nothing in a language the parser cannot see; otherwise it says nothing. A manifest per run holds paths, hashes, symbols, ranks, reasons, budget and grounding, never a body, with the newest 200 kept per scope.

## Consequences

- One turn's context makes up to about 28 route calls by construction, and the map up to 49 on a miss. The measured numbers are in `reports/plan12-memory-m1/assembly.json`, on a 52-file corpus; large-corpus limits are Task 5's.
- A turn whose named files are unsaved shows text the disk does not have. An `EDIT` then needs the file saved first.
- A by-name walk runs for every `LIST` and quoted `SEARCH`, and when a named or cited file is not in the last listing: about 1.8 seconds on Hadoop, on this host. A listing can name a binary file that a read then refuses.
- A worker's revision check is a by-name walk plus a stat of each file, on every turn's request. Only a pass that finds a difference reads files.
- Grounding will often say nothing about a symbol in a repository holding any language the parser cannot see. That is the price of never claiming a false absence.
- The check that a pass is still on its branch runs before each write, so one batch read just before a switch can still land. The pack and tools verify every record against the disk, so it cannot become current evidence, and the next pass on that branch reconciles it.
- One loaded model serves the worker and a person's query at once, with no lock. A real-artifact test proves no errors, not how the two affect each other's speed at scale.
- A failed worker stops indexing for that session and says so; it does not restart by itself.

## Evidence

`tests/unit/context/test_memory_tools_and_turns.py` and `tests/unit/acp/test_memory_wiring.py` for each decision; `tests/unit/optimus_gateway/test_prompt_cache.py` for the wire and digests;
`tests/integration/context/test_memory_session.py` on the released dedicated Redis, real route and real Git, with the real artifact where named; `reports/plan12-memory-m1/revert-check-cp3.json` for discrimination. **Not yet proved:**
the real Zed session, including P5-a and the tool cards, whose record will be `zed-ui.json`; the paid cache pair, `prompt-cache.json`; and retrieval quality, `retrieval.json`.
