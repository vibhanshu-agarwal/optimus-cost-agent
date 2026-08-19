# Plan 11.24 — Relay Child-Argv Root Cause

**Status:** The v3 shot is preserved, approval is revoked, and the offline root cause is established.
This report authorizes no Zed launch, does not implement the repair, and does not disposition the
Zed-resume lane.

## V3 guided-shot outcome

The v3 Gate 4 shot ended **`INDETERMINATE / OBSERVATION_INCOMPLETE`** at Optimus commit
`728a29d0312b0298c3352f5af8a92dda9da954c4` with `zed_launches: 1` and
`origin_a_launches: 0`. It ran against Zed **1.15.1** at
`b962c0ab00b3d368503d8cd4000a6de2895b535c`.

The byte-exact evidence is
`reports/plan-11-24-zed-guided-session-load-probe-v3/`. Its relay contains a 424-byte
`zed-to-agent.bin` with SHA-256
`2b0f9ac7e9c3cdb861fb4c8c957bf9324596cbe7f85865c0682630694923a107` and a zero-byte
`agent-to-zed.bin` with the empty-stream SHA-256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`. The manifest has no captured
`session/load` exchange. The question whether Zed proceeds to `session/load` after a successful
agent handshake therefore remains unanswered.

The shot also establishes that the v3 prerequisites held:

- Option A created a durable approval for the exact Zed child workspace, kept it live through the
  launch, matched that workspace at the relay boundary, and revoked it afterward:
  `zed_workspace_approval == {created: true, mode: durable, child_workspace_match: true, revoked:
  true}`.
- The hermetic settings file existed before and after launch at the discovered custom-data
  `config/settings.json` path with the same digest, and `environment_bind` was empty.
- The operator observed Optimus registered in the Agent panel.
- Cleanup and isolation were verified.

The separately recorded launch grant was consumed. None of these facts grants another shot.

## Accepted offline bisection

After approval revocation, the failure was reproduced and bisected entirely offline. The repro run
root and scratch files were then removed; this report preserves the reviewed results rather than
recreating revoked state.

| Step | Command shape | Result |
|---|---|---|
| 1 | Direct-shell agent with empty stdin | Exit 0, empty stderr. The agent is healthy; Redis, environment setup, and approval TOCTOU do not explain this observed process failure. |
| 2 | Direct spawn of the isolated launcher with Zed's exact captured `initialize` bytes on stdin | Exit 0 and a correct 345-byte response advertising `loadSession: true`. |
| 3 | The same bytes through `tools/plan117_custody_relay.py`, using the child argv assembled by `run_plan1119_real_zed()` | Relay exit 1; `agent-to-zed.bin` is zero bytes. Child stderr reports Python treating `.venv\Scripts\python.exe` as source: `MZ… SyntaxError: Non-UTF-8 code starting with '\x90'`. |
| 4 | The same real relay and bytes, with the interpreter removed only from `child_args` | Relay exit 0; `agent-to-zed.bin` contains the same correct 345-byte response; child stderr is empty. |

This is a controlled one-variable result. The relay, captured `initialize`, isolated launcher,
workspace, and environment were held constant between Steps 3 and 4. Removing only the duplicated
interpreter changes zero reply/exit 1 into the correct reply/exit 0.

## Root cause

The relay's public child-argv contract is:

```python
child_argv = [str(child_executable), *[str(a) for a in child_args]]
```

That contract is implemented at `tools/plan117_custody_relay.py:1173`. The relay tests use it
correctly by taking `child_argv[0]` as `child_executable` and `child_argv[1:]` as `child_args`
(`tests/unit/tools/test_plan117_custody_relay.py:133-134`).

The probe violates the contract:

```python
child_args = [str(sys.executable), str(launcher), "--workspace-root", str(workspace), "--no-auto-start"]
...
child_executable=Path(sys.executable),
```

Those two inputs are at `tools/probe_p11_zed_session_load.py:1967,1971`. The relay consequently
executes:

```text
python.exe python.exe isolated_optimus_agent.py --workspace-root ... --no-auto-start
```

The first interpreter treats the second `python.exe` PE binary as a Python source file. It fails
before the isolated launcher imports or starts Optimus, so no ACP response can reach Zed.

Commit `f713aef8fa8f3d328bf42c467cf439d5a882d2f1` introduced this real-Zed production call. The defect
was latent on all seven live shots that used the path.

## Test blind spot

The only direct `build_opaque_relay_command` unit test at
`tests/unit/tools/test_probe_p11_zed_session_load.py:731-740` omits `child_args` and exercises the
`child_args=None` default. That default deliberately supplies `child_executable` after the relay
separator, so it does not reproduce the production call's explicit list.

The v3 call-boundary spy records `child_args` for workspace-approval assertions but never asserts the
fully resolved child argv or counts `sys.executable`. The missing test is a production-path assertion
that the resolved child command contains `sys.executable` exactly once at index 0 and the launcher
at index 1. It is RED on the preserved v3 implementation.

## Secondary diagnostic defects

### Relay-child stderr was inherited and lost

`tools/plan117_custody_relay.py:1188-1197` calls Popen with `stderr=None`. On this path, the child's
SyntaxError is inherited by the relay process, whose own stderr belongs to Zed. The probe captures
neither stream. All seven shots were therefore blind to the child process's direct explanation.

The Plan 11.24 v4 repair is deliberately separate from ACP custody: raw child stderr stays in a
private throwaway run-dir file, and only a bounded `_safe_payload` excerpt may enter the sanitized
sidecar/manifest.

### The Zed launch log is the wrong diagnostic channel

`_launch_zed_once()` captures stdout/stderr from the Zed GUI process
(`tools/probe_p11_zed_session_load.py:1723-1772`). It does not capture stderr from the later relay
child that Zed spawns. `zed_launch.log_excerpt == ""` in every shot is therefore unsurprising and
does not mean the relay child emitted no diagnostic.

## Exonerated components and bounded non-claims

- **Option A:** The committed lifecycle record proves exact-workspace durable approval, live-window
  coverage, and revocation. The offline direct-launch success also proves approval was usable.
- **Settings seeding:** Optimus registered, and the committed before/after settings evidence pins the
  corrected custom-data path.
- **Agent health and isolated launcher:** The exact captured `initialize` produced the correct
  345-byte `loadSession: true` reply under direct spawn.
- **Relay byte forwarding:** The relay preserved the 424-byte Zed request. With only the duplicate
  interpreter removed, the same relay preserved the correct 345-byte reverse response.

These findings exonerate relay forwarding, not the probe's construction of the relay child argv.
They also do not exonerate the inherited-stderr diagnostic contract, which is independently defective.

The 345-byte offline reply proves only that a successful `initialize` handshake can traverse the
real relay. It is not evidence that Zed sent `session/load`, and it is not substituted into the
historical zero-byte bundle.

## Seven-shot causal custody

The doubled interpreter was latent, but it does not erase the earlier necessary repairs:

| Shots | Layer | Preserved causal statement |
|---|---|---|
| Plan 11.19 shots 1–2 | Launch executable/argv | Shot 1's CLI wrapper produced no window. Shot 2 passed invalid arguments to the GUI binary and returned 2. |
| Plan 11.19 shots 3–4 and Plan 11.24 v1 shot 5 | Settings path | The seeded `agent_servers` file was outside the custom-data `config` path and could not register the relay. |
| Plan 11.24 guided shot 6 | Workspace approval | The Zed child workspace lacked its own durable approval. That was a real independent authorization defect; inherited stderr prevented discriminating it from the latent child-argv defect in the empty reverse stream. |
| Plan 11.24 v3 shot 7 | Relay child argv | Option A, settings, registration, and forward traffic held. Offline replay then isolated the doubled interpreter as the cause of zero reverse bytes. |

Each layer had to close before the next could be observed cleanly. No single defect is retroactively
claimed as the sole cause of all seven shots.

## Required outcome consequence

For the committed result:

> **`INDETERMINATE`:** The named missing precondition/observation remains; no implementation or
> disposition follows automatically.

The child-argv repair and stderr capture are offline Tasks 9–10 in Plan 11.24 v4. After they merge, a
future separately reviewed package may establish prerequisites and request exactly one new launch
grant. Its falsifiable prediction is that `agent-to-zed.bin` is nonempty and begins with the
`initialize` result. Only the resulting capture can establish whether Zed then sends
`session/load`.

This report makes no pool, roadmap, README, `CURRENT.md`, normal-agent, origin-A, or durable-session
implementation change.
