# Plan 12.2 Stage C: live run and guard (release r9)

> **Authority:** the operator's direct approval on 2026-10-17 of Codex's r9 proposal `235d7b7e`: one preparation batch and, after Codex accepts it and the operator confirms a free hour, one fresh full Stage C run ($8, 138 attempts, one shared 60-minute window). r8 stopped at B7.6 on a charged reply refusal.
> Use it only on the candidate Codex has accepted; the operator's own L1 and L2 approvals and A2's artifact approval stay personal.
> Test-only: no production enforcement, engine attachment, default or route change, publication, push or merge.

This is the single current sequence for the Stage C editor run (Plan 12.2 Task 13). The exact commands come from the schedule tool (schedule v10); this page says what they rely on and when to stop.

## The release and its guard

- **One envelope:** release `plan12-2-stage-c-r9` covers both test profiles (`qualification`, `attached`), every Zed and acpx launch, and the one eligible qualification restart.
  - At most **$8** of known charges plus outstanding reservations.
  - At most **138** physical upstream attempts, unbilled ones included.
  - **One 60-minute window**, starting at the first Stage C Gateway open; nothing resets or extends it.
  - It covers the accepted complete-case reservation bound: $7.518097, 69 calls, at most 138 attempts.
- **One ledger:** `<workspace>/.optimus/plan12-stage-c/plan12-2-stage-c-r9.jsonl`.
  - `optimus-trust approve ... --plan12-stage-c` creates it once; later approvals keep it as it is.
  - Every Gateway start only reopens it, under an exclusive lock: one writer, one attempt in flight.
  - Earlier releases (r1 to r8) keep their own ledgers and approval literals; r9 never opens any of them.
- **Admission:** an attempt is dispatched only if it can time out inside the window, the attempt count allows it, and known charges plus its full reservation fit within $8 (equality allowed). The reservation is written to disk before dispatch.
- **Approvals:** the durable approval is keyed by workspace, so the L2 (attached) approval replaces L1's. The order is therefore always L1, the qualification and acpx cases, isolation, then L2.

## Before the first launch

1. Check out the accepted candidate. Run every tool from the repository root with its own venv Python (`.venv\Scripts\python.exe`). Quote any path that contains spaces.
2. Claude checks that no earlier Optimus host, Zed, acpx process or Gateway listener is running.
3. Every launch (Zed, acpx, `optimus-trust`) gets the same `OPTIMUS_*` environment the approvals capture, with `OPTIMUS_MAX_PLANNING_TURNS` at its default of 3. A difference refuses the launch with `SNAPSHOT_MISMATCH` before any service starts. Never print secret values.
4. Check the pinned clients: acpx 0.12.0 with the inspected hashes, and Zed 1.24.2 (`87a6f2c6…`). Do not install or upgrade either.
5. Generate the schedule into a new folder: `.venv\Scripts\python.exe tools\plan12_stage_c_schedule.py --out <new folder> --evidence <evidence folder>`. It writes the cases with their dependencies, the synthetic workspace, the paste files and the numbered runbook (`stage-c-schedule.md`).
6. The preparation's acpx rehearsal receipt must be fresh (the runbook's first step), and the full inert dress rehearsal must have passed.

## The sequence

Follow the generated runbook. In outline:

1. The operator approves L1 (TTY `y`). Fixture check, then custody check 00.
2. **Claude starts Zed** through the ordinary shortcut (explorer.exe, the pinned `Zed.exe`, the workspace), and verifies the process. Codex drives A1 to A5. A2 uses the handshake: Codex captures the pending request, then signals "capture taken — approve now" in its own chat, and only then does the operator approve.
3. Quit Zed, capture the runtime logs, then a custody check. A6 (one-shot `exec`) and A7 (`sessions new`, `set-mode chat`, `--ttl 0 prompt`, `sessions close`), each followed by its capture and custody check.
4. With Zed not running, isolate the attached entry. The operator approves L2 (TTY `y`; the ledger is kept), then a custody check.
5. Claude starts Zed again. Codex runs the B cases in the schedule's selected order: B2 right after B3.1, returning to T1 through Zed's thread history, or B2 last. Press Cancel within 30 s when B8.7's pause notice appears. Quit Zed, capture, then the final custody check.

**Custody check:** `tools/plan12_stage_c_transition_check.py --workspace-root <ws> --out <new receipt> --previous <previous receipt>`. It exits 0 only when nothing listens on the Gateway URL, no Gateway holds the ledger, no Optimus host or Gateway process is left, and the window and the never-decreasing totals match the previous check. Clear means custody is free, not that budget or time remains.

**Approval ceremony refusals:** the ceremony prepares the ledger before it persists any approval. If preparation refuses, nothing is persisted. It refuses with `STAGE_C_LEDGER_WRITE_FAILED` (creation failed, and any partial file is kept), `MISSING` (not a regular file), `UNREADABLE`, `CORRUPT`, `ENVELOPE_MISMATCH`, `LOCKED` (a Gateway still holds it) or `HALTED` (halted or in doubt). After `WRITE_FAILED`, or a `CORRUPT` that follows one, inspect the ledger file and remove a partial file by hand before retrying. Never reset an initialized ledger. A kept ledger prints its replayed attempts, charge and window.

## Stop and continuation rules

- **Absolute stops** end the run: every later case is UNRUN, and no restart clears it. They are:
  - a guard refusal (budget, attempts or window);
  - a ledger halt, write divergence or overrun;
  - an unknown, outstanding or unresolved charge;
  - an accounting-integrity failure;
  - a custody check that is not clear;
  - a security, approval, source or fixture mismatch;
  - unauthorized or uncertain effects;
  - uncertain permission provenance or isolation.
- **Any other case failure** is captured at once and recorded FAILED. It is never retried, given a substitute prompt, repaired or removed.
- **Continue only** with cases whose predecessors ran and whose state preconditions are proved from evidence (the schedule's `after` and `requires`). A case missing a precondition is BLOCKED with its cause, and its prompt is never sent.
- **Route stop:** on the experimental route, a refused or unverifiable reply stops every later call on that launch. That launch's later route cases are BLOCKED.
- **No attached relaunch.** A new attached host reseeds its first session and restarts its live-turn count, so earlier state cannot resume.
- **One qualification restart,** at most once. It is allowed only after a charged, fully settled reply-policy refusal (422 with its usage kept, every charge known and settled, no halt), with custody clear and time, budget and attempts left. It runs only the L1 cases not yet run, under the same r9 L1 durable approval, ledger, totals, deadline and limits.
- **Acceptance:** any required case FAILED, BLOCKED or UNRUN means the run is not full Stage C acceptance.

## After the run

- Quit Zed, close any acpx session the runbook opened, and run the final custody check.
- Restore Zed's settings exactly, and remove the temporary shortcut and keymap.
- Keep the receipts, transcripts, screenshots and the ledger as they are. Seal the evidence folder and return it for Codex's closing review.

Full CP4, client compatibility and publication stay open until that review.
