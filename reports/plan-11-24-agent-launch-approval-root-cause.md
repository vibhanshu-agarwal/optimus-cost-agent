# Plan 11.24 — Agent Launch-Approval Root Cause

**Status:** Evidence preserved; root cause established. This report does not choose an authorization
design, authorize another Zed launch, or disposition the Zed-resume lane.

## Guided-shot outcome

The corrected guided shot ended **`INDETERMINATE / OBSERVATION_INCOMPLETE`** at Optimus commit
`a8d875559dbc3f09d336144e211511eeacca63d1`, with `zed_launches: 1` and
`origin_a_launches: 0` (`plan-11-24-zed-guided-session-load-probe/manifest.json:21,27,36,75,101`).
It ran against Zed **1.15.1** at
`b962c0ab00b3d368503d8cd4000a6de2895b535c` (`manifest.json:87`). The capture contains no
`session/load` exchange (`manifest.json:20`), so the headline question—whether this Zed issues
`session/load`—remains unanswered.

The WP-10 seeding correction was nevertheless proven in the production path. The operator observed
**Optimus** registered in Zed's Agent panel. The committed evidence corroborates the corrected
contract: `hermetic_settings.config_dir` is the discovered user-data root's `config` directory,
settings existed before and after launch, and `invocation.environment_bind` is empty
(`manifest.json:29-32,44`). The guided path published the project's first verifier-valid bundle with
a nonempty Zed-to-agent stream (`manifest.json:24,81`).

## Established causal chain

1. The ACP entry point resolves and authorizes a launch before starting the server
   (`src/optimus/acp/__main__.py:244-250`). When authorization raises `NO_APPROVAL`, it writes the
   durable-approval remediation to **stderr** and returns exit code 2
   (`src/optimus/acp/__main__.py:150-155,251-258`). That branch writes nothing to stdout.

2. Durable approval lookup is workspace-specific. A launch candidate carries its resolved
   `workspace_identity` (`src/optimus/acp/launch_gate.py:686-691`); the store looks up
   `durable:{current_identity.digest}` (`src/optimus/acp/launch_approvals.py:598-622`). If no current
   record is reachable, `authorize_launch` raises `NO_APPROVAL`
   (`src/optimus/acp/launch_gate.py:738-752`). An approval for one workspace therefore cannot
   authorize a different workspace.

3. The acpx baseline creates `<run_root>/acpx-workspace`
   (`tools/probe_p11_zed_session_load.py:1425-1426`), performs the approval ceremony for that exact
   workspace (`tools/probe_p11_zed_session_load.py:1442`), and runs the successful baseline while
   that approval is live. Its capability payload advertises `loadSession: true`
   (`manifest.json:8`). The function then revokes the temporary approval in its `finally` block
   before returning control to the real-Zed caller (`tools/probe_p11_zed_session_load.py:1477-1480`;
   lifecycle contract at `tools/probe_p11_zed_session_load.py:4-7`).

4. Only after the acpx call returns does the real-Zed path create
   `<run_root>/zed-workspace` and construct the agent child command with
   `--workspace-root <run_root>/zed-workspace`
   (`tools/probe_p11_zed_session_load.py:1909-1914`). This is a different workspace from the one
   temporarily approved for acpx, and the acpx approval has already been revoked.

5. The Zed-spawned agent consequently has no reachable approval for its own workspace. Its
   deterministic path is `NO_APPROVAL` → stderr remediation → exit 2 → no ACP stdout. The committed
   `relay/agent-to-zed.bin` is therefore correctly zero bytes; its manifest digest is
   `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`, the SHA-256 of the empty
   byte string (`manifest.json:23,79`). This exactly matches the established failure path.

The same chain explains the apparent contrast within one run: acpx succeeded because it exercised
the agent while `acpx-workspace` had a live approval; Zed's later agent process used unapproved
`zed-workspace` after revocation.

## Exonerated components

- **Opaque relay:** Zed-to-agent evidence is present and nonempty (424 bytes), and the post-run
  manifest records its digest and source (`manifest.json:24,80-81`). The relay faithfully preserved
  the one Zed `initialize` message; the empty reverse stream is explained upstream by the agent's
  approval failure.
- **WP-10 seeding correction:** the file existed at the corrected custom-data `config` path before
  and after launch, with no environment bind (`manifest.json:29-32,44`).
- **Guided timeout seam:** the launch used the selected 900-second window and returned successfully
  (`manifest.json:98-99`).
- **Isolation and cleanup:** both cleanup predicates are true and the isolated/normal evidence is
  recorded (`manifest.json:51-60,70-73`).

## Required outcome consequence

Plan 11.24 requires the report to state the consequence associated with its result
(`docs/superpowers/plans/archive/2026-08-18-plan-11-24-zed-guided-session-load-probe.md:216-223,229-237`).
For this result:

> **`INDETERMINATE`:** The named missing precondition/observation remains; no implementation or
> disposition follows automatically.

The missing precondition is an authorized launch for the Zed-spawned agent's actual workspace. The
missing observation remains whether Zed 1.15.1 proceeds to `session/load` after a successful agent
handshake.

## Report-generator defect

The generated bundle report records only the finding, reason, timestamp, and commit
(`plan-11-24-zed-guided-session-load-probe/report.md:1-7`). Its generator builds those fields but has
no outcome-consequence mapping (`tools/probe_p11_zed_session_load.py:1549-1565`), although the frozen
plan requires the exact consequence row
(`docs/superpowers/plans/archive/2026-08-18-plan-11-24-zed-guided-session-load-probe.md:216-223,237`). The
generator was never given the consequence table.

Because `manifest.json` pins `report.md`'s digest (`manifest.json:22-25`), changing the generated
report after publication would invalidate the evidence bundle. This separate report records the
missing consequence without altering the bundle. The generator repair is small—a few lines plus a
test—but is deliberately not implemented in WP-12.

## No remedy or disposition in WP-12

Authorizing a future Zed-spawned agent is design-shaped. At least three materially different shapes
exist: a second durable-approval ceremony for `zed-workspace`; establishing and using the hidden
`--launch-approval-id` contract (`src/optimus/acp/__main__.py:115-120`); or restructuring the probe so
acpx and Zed share one approved workspace root. Each changes what the operator authorizes and has a
security consequence.

WP-12 selects none of them. Plan 11.24 v1 is frozen and `_v2` authorizes only the completed offline
seeding repair. Any remedy and any further live shot require an operator scope ruling and a
forward-only `_v3` amendment. This report makes no pool, README, roadmap, plan-status, or
`CURRENT.md` change.
