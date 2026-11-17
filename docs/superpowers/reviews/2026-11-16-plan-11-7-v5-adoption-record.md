# Plan 11.7 v5 adoption record (#240)

This record makes the delivery of Plan 11.7 v5 understandable from tracked files. It is provenance, not a status
record: [#240](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/240) owns the plan's status, owner and
next gate ([ADR-022](../../decisions/ADR-022-github-issues-as-the-work-register.md)). Drafted by Claude on 2026-11-16;
reviewed locally by Codex on 2026-11-16 and 2026-11-17, whose final readback on 2026-11-17 closed its documentation
findings before this record was committed as part of `11d7f779` (draft PR #476). Changes made after that readback are
reviewed separately. Unpublished draft.

## The adopted plan

| Field | Value |
|---|---|
| File | [`2026-07-29-plan-11-7-p11-feat-zed-resume-implementation_v5.md`](../plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation_v5.md) |
| SHA-256 of the file bytes | `288bf4f896a559a6ca91a14bc1065806357883b5e09ebc4fca6856afe717c83c` |
| Git blob | `df78e84bc44181ebb8ab9d78aeff8c92289506e7` |
| Adopted | 2026-11-14, by the operator; the adoption accepted its decision package D1–D13 |

The operator's words, 2026-11-14, the turn that adopted v5 in the shared Codex coordination chat for #240. Codex's
adoption receipt was recorded at `2026-11-14T17:11:43.662160Z`; that is the receipt's time, and the original message
timestamp is not recorded. No transcript export is filed, which limits provenance but places no condition on the
adoption:

> "Approved. Adopt the reviewed v5 plan and have Claude implement E1–E2 only, with Codex reviewing. Don’t run live
> probes, publish records, commit, push or open a PR yet."

The file is delivered byte for byte. Its header, checklists and Authority section keep the wording they had when it was
reviewed for adoption ("not adopted, published or authorized for implementation"; every box unchecked). That wording
is dated history, kept because a frozen plan is never edited. This record and #240 carry the adoption. The adopted
bytes, including every unchecked box, stay exactly as approved; progress is recorded in #240 and the review records, not
in this file.

[ADR-043](../../decisions/ADR-043-durable-acp-session-retention-and-replay.md) records the rationale for D1–D13, which
the adoption accepted, the agent-selected values and their limits.

## Released scope and holds

- **Released (2026-11-14):** the execution source re-pin for E1–E2, an isolated worktree and environment, E1's pure
  evidence contracts and tests, E2's collector, redaction and offline verifier and their tests, and local review
  preparation. Claude implements; Codex reviews.
- **Held:** E3 and later (the live current-Zed run and its acceptance), production persistence P1–P6, any
  live, paid, GUI or service run, and each GitHub write, commit, push, PR, merge and cleanup unless separately granted.

Later grants released bounded steps one at a time (for example, opening and updating PR #476 and one Windows full gate);
each grant is recorded with its evidence. Two of them authorized bounded corrections that verification found: L1, in
the v5 collector (a filesystem error during preflight escaped raw with a private path and now maps to the fixed
`host_action_failed` code), and the ACP response-handoff fix described below. Neither released E3, P1–P6 or any other
part of the plan.

## Predecessors

| Version | Location | Identity | Disposition |
|---|---|---|---|
| v1 | [`archive/`](../plans/archive/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md) | SHA-256 `F52AD9A5…C462D` | Frozen approval history, unchanged |
| v2 | [`archive/`](../plans/archive/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation_v2.md) | as merged | Frozen, unchanged |
| v3 | [`archive/`](../plans/archive/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation_v3.md) | SHA-256 `51e1a6efc29906387f8efde85659f9ff219e8cf831a01e266ff6c35e8e6fba3a`, blob `ee6cc97671d330a99ba8bc6873ed4d405a91007c` | Superseded by v5; moved byte for byte. #240 must record the supersession before this move merges |
| v4 | Not in the repository | SHA-256 `3436d53b1accda0ca90868206b92962b0fd75e2950167bbceb63cfd5b1c21151` | A local frozen predecessor, never published. v5 says to deliver or archive it only within an explicit documentation publication grant, so it is not delivered here |
| Three amendments (2026-08-02, 2026-08-04) | `archive/` | as merged | Frozen approval history, unchanged |

v3 contains no relative Markdown links, so the move needs no link repair, relocation entry or test change. Its plain-text
mentions of its own folder are historical. Frozen reports, manifests and seals that name v3's former path keep that text.

## What the E1–E2 delivery is

PR #476 (branch `agent/claude/issue240-v5-evidence`) adds the evidence machinery: the v5 current-client contract and
reducer, the collector inside the existing `tools/evidence_gather.py` pipeline, the redaction attestation and private
receipt path, the offline verifier, the v5 scenario and first-refusal descriptors, an **empty** approved-run registry
(`reports/plan-11-7-v5-approved-runs.json`), and their tests. Its one production change is the separately authorized ACP
correction found during verification: a same-session prompt that arrives while the previous turn's response is being written now queues instead of
being refused as "a turn is already in progress" (`src/optimus/acp/lifecycle.py`, `src/optimus/acp/server.py`).

It does **not** establish:

- `session/load`, durable resume or any production persistence (the agent still does not advertise `loadSession`);
- Task 0, the current-Zed gate or the owner reconciliation (E3–E4), or any live result;
- checkpoint 1 acceptance on the final integrated bytes, or acceptance of the whole plan.

Test, coverage and CI results bind to the exact source they ran on and are recorded with their run identities in #240
and PR #476. A later source, including a refresh from main, needs its own results.

## Applicability of later main (D1, D12)

v5 was assessed against `main` `6e5478a0`. The E1–E2 branch started there and later merged `main` at `5715ff1a`,
`a92f45a0` and `71d1c1ef`; the current candidate merges `main` at `84fb87ca`. The E1–E2 files touch none of
`src/optimus/acp/local_infra.py`, `src/optimus/context/memory_session.py` or `src/optimus/context/memory_workspace.py`.
Main changed `local_infra.py` after `a92f45a0` (#480, local Redis attach identity) and again by `84fb87ca` (Plan 12.11,
the memory store's own Redis). D12's release for P1 therefore needs a reviewed integrated pin that includes these
changes, or exact owner clearance. Importing main gives neither.

At `84fb87ca`, main has a durable project memory store behind the Gateway
([ADR-042](../../decisions/ADR-042-memory-store-topology-commit-and-recovery.md), Plan 12.11). It holds accepted memory, and its
route can store and list continuation checkpoint records; main also has a pure helper that picks a predecessor checkpoint
(`src/context_engine/continuity.py`), which nothing in production calls yet. Automatic checkpoint capture and a new
session reading one are Plan 12.11's later continuity task (Task 4), not part of this import. It is not ACP session
persistence either: the agent still does not advertise `loadSession`, and nothing in it restores a session's
conversation or replays it. Three Redis roles therefore
stay distinct: the memory-index Redis (ADR-037), the project-memory store (ADR-042), and the future ACP session store
that [ADR-043](../../decisions/ADR-043-durable-acp-session-retention-and-replay.md) describes, which does not exist yet.

## Publication order

The v3 archive move and its registry row are a proposed version disposition, not a closure of #240, which stays open.
At the operator's later publication grant: first record v5's adoption, v3's supersession, the owner and the next gate
in #240; then merge the change that delivers v5, moves v3, updates the indexes and files ADR-043. Private planning and
review artifacts stay outside the repository as archival provenance; this record does not depend on them.
