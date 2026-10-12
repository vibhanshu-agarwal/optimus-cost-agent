# Plan 12.2 Stage C: live run and guard (release r3)

> **Authority:** the operator's new bounded Stage C grant of 2026-10-12 for release r3 ($8, 138 attempts, one shared 60-minute window), approving Codex's r3 proposal after r2 stopped at A2.
> Use it only on the candidate Codex has verified, after the operator grants fresh launch approvals.
> Test-only: no production enforcement, engine attachment, default or route change, publication, push or merge.

This is the single current sequence for the Stage C editor run (Plan 12.2 Task 13). The exact commands come from the schedule tool; this page says what they rely on and when to stop.

## The release and its guard

- **One envelope:** release `plan12-2-stage-c-r3` covers both test profiles (`qualification`, `attached`), every Zed and acpx launch, and every restart.
  - At most **$8** of known charges plus outstanding reservations.
  - At most **138** physical upstream attempts, unbilled ones included.
  - **One 60-minute window**, starting at the first Stage C Gateway open.
  - It covers the accepted complete-case reservation bound: $7.518097, 69 calls, at most 138 attempts.
- **One ledger:** `<workspace>/.optimus/plan12-stage-c/plan12-2-stage-c-r3.jsonl`.
  - `optimus-trust approve ... --plan12-stage-c` creates it once; later approvals keep it as it is.
  - Every Gateway start only reopens it, under an exclusive lock: one writer, one attempt in flight.
  - It is never reset, and a restart never extends the window.
  - The superseded releases have their own ledgers and approval literals, and r3 never opens either: r2 ($8, 138 attempts; stopped at A2, its window expired) and r1 ($0.50, 24 attempts).
- **Admission:** an attempt is dispatched only if:
  - it can time out inside the window;
  - the attempt count allows it;
  - known charges plus its full reservation fit within $8 (equality allowed).

  The reservation is written to disk before dispatch.
- **Stops:** an unknown charge, an overrun, a divergent or failed ledger write, or an attempt left unresolved at a restart stops every later dispatch.
- **Accounting:** a refusal that reached no provider is recorded by the host as a rejected attempt costing exactly $0.

## Before the first launch

1. Check out the verified candidate. Run every tool from the repository root with its own venv Python (`.venv\Scripts\python.exe`). Quote any path that contains spaces.
2. Stop any earlier Optimus host still running, through its owner (Ctrl+C in its terminal).
3. Make sure every launch (Zed, acpx, `optimus-trust`) gets the same `OPTIMUS_*` environment the approvals capture, with `OPTIMUS_MAX_PLANNING_TURNS` at its default of 3. A difference refuses the launch with `SNAPSHOT_MISMATCH` before any service starts. Never print secret values.
4. Check that the installed acpx is still 0.12.0 with the inspected hashes (`acpx.cmd` `212da5e5…`, `dist/cli.js` `7da1d8b2…`). Do not install or upgrade it.
5. Generate the schedule into a new folder:
   `.venv\Scripts\python.exe tools\plan12_stage_c_schedule.py --out <new folder> --evidence <evidence folder>`

   It writes the case list, the pinned agent wrapper `run-optimus-agent.cmd`, the synthetic workspace, the paste files and the numbered runbook (`stage-c-schedule.md`, "Runbook").
   The workspace prepares every case target's folder: `notes/` (holding the calculator fixture) and an empty `scratch/`. No case target exists before the first launch. The writer creates no parent folder, and r2's A2 stopped on a missing `scratch/`.

## The sequence

Follow the generated runbook step by step. In outline:

1. Approve the L1 release (`--plan12-test-profile qualification --plan12-stage-c`; TTY `y`). Run the workspace fixture check (`tools\plan12_stage_c_schedule.py --verify-workspace <ws>`, which must print `workspace fixture clear`), then custody check 00.
2. Zed L1 launch, cases A1 to A5, quit Zed, custody check.
3. acpx A6, the denied Agent case (one-shot `exec`), then a custody check.
4. acpx A7, the Chat case:
   - `sessions new` for a fresh named session, then a custody check;
   - `set-mode chat`, then a custody check;
   - `--ttl 0 prompt` (acpx replays Chat on the prompt's fresh runtime session);
   - `sessions close`, then a custody check.
5. Approve the L2 release (`--plan12-test-profile attached --plan12-stage-c`; the ledger is kept), then a custody check.
6. Zed L2 launch: B3 to B8 in the seeded first thread, then B2 in a second thread. Press Cancel within 30 s when the pause notice appears. Quit Zed, then the final custody check.

**Custody check:** `tools/plan12_stage_c_transition_check.py --workspace-root <ws> --out <new receipt> --previous <previous receipt>`.
- It writes a new receipt and exits 0 only when:
  - nothing listens on the Gateway URL;
  - no Gateway holds the ledger;
  - no Optimus host or Gateway process is left;
  - the window and the never-decreasing totals match the previous check.
- **Clear means custody is free, not that budget or time remains.** Read the receipt's ledger fields and apply the stop rules before the next launch.

## Stop rules

- A guard refusal, an expired window, an unknown charge, an overrun or a failed required case ends the run there. The remaining cases are UNRUN; none is a pass.
- A custody check that is not clear stops the run before the next launch.
- On the experimental route, a failed or unverifiable reply stops every later call until the Gateway restarts. A relaunch needs a fresh bound approval and keeps the same ledger, totals and deadline.
- Never retry with changed settings, remove a case, lower a limit, reset or replace the ledger, or delete evidence. The only resend is the Gateway's own safe resend after a proven unbilled attempt.

## After the run

- Quit Zed, close any acpx session the runbook opened, and run the final custody check.
- Keep the receipts, transcripts, screenshots and the ledger as they are.
- Seal the evidence folder and return it for Codex's closing review.

Full CP4, client compatibility and publication stay open until that review.
