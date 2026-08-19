# Plan 11.24 v4 — Relay Child-Argv and Diagnostic-Capture Amendment

> **Status:** Live offline-only version of Plan 11.24. This file supersedes v3's execution authority
> only where stated below, authorizes only offline Tasks 9–11, records Tasks 9–10 as not started, and
> records Task 11 as completed in the amendment PR. The evidence-based live observation belongs only
> to the separately scoped `_v5` two-lifecycle successor. This file does not authorize a Zed launch,
> a preflight that starts external processes, an approval ceremony, a keyring mutation, or any
> paid/network call.
>
> **Frozen predecessors:**
> `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe.md`, git blob
> `421f9a9595dda1d55b9895b148839de8163e6556`;
> `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v2.md`, git blob
> `85cea53cbec6ca9faf1cee85f5c81e15999321b8`; and
> `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v3.md`, git blob
> `220000b208059030488c920fef3f15e9f8834e89`. Leave all three byte-identical.
>
> **Live-version pointer:** This `_v4` file is the sole live Plan 11.24 contract for the offline
> relay/argv/diagnostic package. A source audit established that the former single-launch future
> ceremony cannot observe `session/load`; the separately authored
> `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v5.md` owns the
> corrected two-lifecycle observation after it becomes live. No committed pool, roadmap, README, or
> other index points at a predecessor filename, so these headers are the required forward-only
> pointers; do not manufacture another tracking row.
>
> **Authoring baseline:** `origin/main` at
> `728a29d0312b0298c3352f5af8a92dda9da954c4` (PR #179 merged).

## Purpose and amendment boundary

The v3 Gate 4 shot ran once on Zed 1.15.1 at the authoring baseline under a separately recorded
Gate 2 grant. The v3 Option A lifecycle worked as designed:
`zed_workspace_approval == {created: true, mode: durable, child_workspace_match: true, revoked:
true}`. Settings seeding held, Optimus registered, and the relay captured Zed's 424-byte
`initialize` request. The agent-to-Zed stream remained zero bytes, so the result was
`INDETERMINATE / OBSERVATION_INCOMPLETE` with `zed_launches: 1`. The grant is spent.

Task 11 in this amendment preserves that shot as the byte-exact, verifier-valid four-file bundle at
`reports/plan-11-24-zed-guided-session-load-probe-v3/` and records the accepted root-cause analysis
at `reports/plan-11-24-relay-child-argv-root-cause.md`. Those artifacts are historical evidence, not
a target for another run.

The accepted offline bisection established the next defect without a Zed launch:

| Offline step | Result |
|---|---|
| Run the agent directly with empty stdin | Exit 0 and empty stderr. This exonerates Redis, environment setup, approval TOCTOU, and basic agent health for the observed failure shape. |
| Spawn the isolated launcher directly and pipe in Zed's exact captured `initialize` | Exit 0 and a correct 345-byte reply advertising `loadSession: true`. |
| Send the same bytes through the real relay with the child argv assembled exactly as the probe assembles it | Relay exit 1, zero-byte `agent-to-zed.bin`, and child stderr reporting Python parsing `.venv\Scripts\python.exe` as source: `MZ… SyntaxError: Non-UTF-8 code starting with '\x90'`. |
| Repeat through the same relay after removing the interpreter from `child_args` | Relay exit 0, the same correct 345-byte reply in `agent-to-zed.bin`, and empty child stderr. |

The contract mismatch is exact:

- `tools/plan117_custody_relay.py:1173` constructs
  `child_argv = [str(child_executable), *child_args]`. Its unit helper honors that contract at
  `tests/unit/tools/test_plan117_custody_relay.py:133-134`.
- `tools/probe_p11_zed_session_load.py:1967,1971` supplies `Path(sys.executable)` as
  `child_executable` and repeats `str(sys.executable)` at the front of `child_args`. The actual
  child command is therefore `python.exe python.exe launcher.py ...`, so Python tries to execute its
  own PE binary as source and never reaches the isolated launcher.
- Commit `f713aef8fa8f3d328bf42c467cf439d5a882d2f1` introduced the production call. The only direct
  `build_opaque_relay_command` unit test at
  `tests/unit/tools/test_probe_p11_zed_session_load.py:731-740` leaves `child_args=None`, so it did
  not exercise the production call shape.

Two diagnostic defects are part of the same offline package:

1. `tools/plan117_custody_relay.py:1194` launches the child with `stderr=None`, inheriting stderr
   into Zed's process stream. None of the seven live shots captured that stream.
2. `zed_launch.log_excerpt` is empty on every shot because `_launch_zed_once()` records the Zed GUI
   process's stdout/stderr, not the relay child's stderr. It is not evidence that the agent emitted
   no diagnostic.

Tasks 9–10 are one offline implementation package: correct the child argv at the probe call
boundary and add private relay-child stderr capture with a bounded sanitized evidence excerpt.
Task 11 is the evidence/report package carried by this amendment PR. No task in this file grants a
launch or changes normal Optimus behavior.

## Seven-shot causal custody

The later argv finding must not flatten the preceding observations into a single cause:

| Shots | Layer closed | Causal discipline |
|---|---|---|
| Plan 11.19 shots 1–2 | Zed launch executable and argv | Shot 1 used a CLI wrapper that produced no window; shot 2 passed invalid arguments to the GUI binary and returned 2. Those proximate launch failures remain historical facts. |
| Plan 11.19 shots 3–4 and Plan 11.24 v1 shot 5 | Hermetic settings path | The seeded `agent_servers` file was outside Zed's actual custom-data `config` path. That defect directly prevented relay registration in those shots and was a necessary repair. |
| Plan 11.24 guided shot 6 | Workspace approval | The Zed child workspace lacked its own durable approval. Option A was a real independent authorization requirement. The inherited-stderr blind spot meant the zero reverse stream could not distinguish that gate from the still-latent doubled interpreter. |
| Plan 11.24 v3 shot 7 | Relay child argv | Option A, seeding, and Zed-to-agent forwarding all held. The offline replay then proved the doubled interpreter caused the zero reverse stream and proved the one-interpreter command returns the correct `initialize` reply through the real relay. |

The doubled interpreter was latent from `f713aef` onward. Earlier blockers still had to be removed
before this contract could be isolated. Every repair above remains necessary; none is retroactively
rewritten as the sole cause of all seven shots.

## Superseded and preserved provisions

The following v3 provisions are superseded:

- v3's `-v3` future report target is now immutable historical evidence committed by Task 11. This
  offline amendment defines no future report target; the `_v5` two-lifecycle successor owns a fresh
  report directory and all live observation evidence.
- v3's Future Gates 1–5 are not carried forward. The source audit establishes that their
  one-fresh-profile/single-launch shape always creates `session/new`, never a resumed
  `session/load`; `_v5` owns the corrected resume shape and its separately granted live gates.
- v3's statement that only Tasks 6–8 are authorized is replaced by this amendment's authorization
  of offline Tasks 9–11. Tasks 6–8 remain accepted merged history.

For Tasks 9–11, all applicable v1–v3 constraints remain in force: hermeticity, sanitized
reconstructed evidence only, unchanged normal Optimus capability behavior, no origin-A launch, no
inference from an absent observation, Option A's workspace-specific approval lifecycle, and exact
outcome-consequence reporting. `_v4` neither restates nor grants a live-launch, prompt, Gateway, or
retry boundary; `_v5` defines those observation-specific constraints from the audited run shape.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| plan/state | This `_v4` amendment is reviewed and merged before Cursor starts Tasks 9–10. | no | Codex + operator | merely unauthorized until the authored bytes and Task 11 package are approved and merged. |
| evidence/state | The v3 four-file bundle is available byte-exact, verifies at exit 0, and the revoked repro scratch/run roots are absent. | yes | Codex | n/a; Task 11 pins the preserved bundle without recreating or editing it. |
| code/state | The real-Zed call passes the interpreter exactly once to the relay child contract. | no | Cursor | genuinely absent but one-line buildable offline; Task 9 supplies it. |
| code/state | The relay privately captures child stderr and the probe persists only a bounded sanitized excerpt while older bundles remain verifier-valid. | no | Cursor | genuinely absent but buildable offline; Task 10 supplies it. |
| tooling/binaries | The frozen `uv` environment can run pytest, Ruff, the Plan 9.96 surface verifier, the evidence verifier, and Git without dependency drift. | yes | implementing agent | n/a; stop if the named offline gates cannot execute. |
| services | Tasks 9–11 require no Redis, daemon, port, ACP server, Zed, acpx, or network service. | yes | implementing agent | n/a; any service dependency is scope drift. |
| credentials/authority | Tasks 9–11 require no Optimus credentials, provider key, OS-keyring mutation, trust approval, live-process authority, or launch budget. | yes | implementing agent | n/a; tests stub every external/interactive boundary. |
| human interaction | Tasks 9–11 require no TTY, `y` confirmation, GUI trust action, Agent-panel action, or manual click. | yes | implementing agent | n/a; an interactive request is a stop condition. |
| cost | Tasks 9–11 make no Gateway/provider call and incur no paid cost. | yes | implementing agent | n/a; any paid call is forbidden. |

Tasks 9–11 have no external unsatisfied prerequisite after `_v4` merges. All prerequisites for a
future observation—including the open persistence fact, a two-launch shared-profile grant, the one
send/cost boundary, machine readiness, and TTY/GUI ceremony—are owned and sequenced in `_v5`, not
silently inherited here.

## Global constraints for Tasks 9–11

- Start implementation from the then-current `origin/main`; read this live plan and the reviewer
  checkpoint Current State before mutation. Never reuse a capture or amendment branch.
- Scope is the probe, relay, their unit tests, the existing evidence verifier and its unit tests,
  the Plan 9.96 surface-audit manifest, this v4 plan's checkboxes, and Task 11's new immutable
  evidence/report paths. Do not modify `src/`, v1, v2, v3, the v1-era bundle, the launch-approval
  root-cause report, `CURRENT.md`, the pool, roadmap, or README.
- Preserve the relay's ACP opacity. Child stderr is a separate diagnostic stream: never merge it
  into child stdout, parent stdout, either directional ACP bin, or relay reason-code stderr.
- Raw child stderr exists only at
  `<capture-root>/<run-id>/relay-child-stderr.txt` inside the throwaway run root. Do not publish,
  stage, hash into the reconstructed bundle, or quote it raw. Cleanup removes it with the run root.
- Keep `SCHEMA_SUMMARY = "plan117-custody-relay-summary-v1"` and every existing summary field.
  `verify_relay_capture()` continues to verify the existing four custody files; the extra private
  diagnostic file neither weakens nor redefines ACP byte custody.
- The only persisted diagnostic is top-level optional
  `relay_child_stderr_excerpt: str`. It is produced after the relay child exits, passed through
  `_safe_payload`, collapsed to one line, and bounded to at most 4000 characters.
- The evidence verifier keeps `SCHEMA` and `REQUIRED_FIELDS` unchanged. Older bundles with no
  `relay_child_stderr_excerpt` must remain accepted byte-for-byte. When the optional field is
  present, the verifier requires a string of at most 4000 characters and the existing whole-manifest
  credential scan still applies.
- Do not weaken `sanitize_for_persistence`, `EVIDENCE_REDACTION_POLICY`, the joined canary scan,
  report-directory constraints, digest checks, or outcome classification. A raw fallback is
  forbidden.
- The new raw diagnostic persistence boundary must appear in the Plan 9.96 surface inventory and be
  classified under the exact key emitted by the verifier. Never suppress, exclude, or bypass it.
- Do not alter Option A, settings seeding, the parser-derived command, approval revocation, evidence
  cleanup, or the settled historical consequences. The `_v5` successor separately defines the
  two-lifecycle observation controls and its launch/time/cost limits.
- Task 11's `-v3` bundle has exactly four files. Its zero-byte `agent-to-zed.bin` is evidence; never
  replace it with the offline 345-byte reply or add the offline scratch artifacts.

## File map

| Path | Required change |
|---|---|
| `tools/probe_p11_zed_session_load.py` | Remove the duplicate interpreter from explicit `child_args`; extract a bounded sanitized relay-child stderr excerpt before cleanup; carry the optional field into sidecar/manifest. |
| `tests/unit/tools/test_probe_p11_zed_session_load.py` | Genuine RED call-boundary argv test, explicit-`child_args` helper test, sanitized/bounded sidecar and bundle coverage. |
| `tools/plan117_custody_relay.py` | Capture child stderr to the private run-dir file while preserving opaque forwarding, parent diagnostics, child exit behavior, and summary v1. |
| `tests/unit/tools/test_plan117_custody_relay.py` | Exact stderr file/cross-stream/close tests; update the inherited-stderr Popen assertion; preserve all custody-verifier cases. |
| `tools/verify_plan1119_zed_reprobe_evidence.py` | Validate the optional bounded excerpt without adding a required field or rejecting older bundles. |
| `tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py` | Backward compatibility, optional-field type/length, and sanitizer-rejection tests. |
| `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` | Classify the exact new relay child-stderr persistence sink with a resolvable test node; preserve existing keys/classifications. |
| `reports/plan-11-24-zed-guided-session-load-probe-v3/` | Task 11 byte-exact four-file historical bundle; no generated or offline-replay substitutions. |
| `reports/plan-11-24-relay-child-argv-root-cause.md` | Task 11 causal report, bisection, origin, blind spot, exonerations, secondary defects, and exact consequence. |
| `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v4.md` | Live offline-only contract; Task 9–11 checkboxes only after their named gates pass. The `_v5` successor owns every future live-observation gate. |

## Task 9: Correct the relay child argv at the real-Zed call boundary

**Owner:** Cursor implements; Codex reviews.

**Scope classification:** Focused offline patch in the probe and its unit test.

**Interface contract:** `run_plan1119_real_zed()` passes
`child_executable=Path(sys.executable)` and explicit
`child_args=[str(launcher), "--workspace-root", str(workspace), "--no-auto-start"]`.
The relay resolves that to
`[sys.executable, launcher, "--workspace-root", workspace, "--no-auto-start"]`. The interpreter
appears exactly once, at index 0; the launcher is index 1.

- [x] **Step 1: Establish the frozen and causal baseline.**
  - Read this plan, the checkpoint Current State, and
    `reports/plan-11-24-relay-child-argv-root-cause.md`.
  - Confirm `HEAD` was cut from current `origin/main` and v1/v2/v3 resolve to the three pinned blobs
    in the header.
  - Confirm the current production call repeats `sys.executable` in `child_executable` and
    `child_args`, while `run_relay()` prepends `child_executable` exactly once.

- [x] **Step 2: Write the genuine RED call-boundary test.** Add
  `test_real_zed_relay_child_argv_contains_interpreter_exactly_once`. Extend the existing real-Zed
  stub's spy around the real `build_opaque_relay_command()` to record
  `[str(kwargs["child_executable"]), *map(str, kwargs["child_args"])]`. Run the fully stubbed
  `run_plan1119_real_zed()` production path, normalize the recorded executable/launcher paths, and
  assert:
  1. the resolved child argv contains `sys.executable` exactly once;
  2. index 0 resolves to `sys.executable`;
  3. index 1 resolves to the generated isolated launcher;
  4. `--workspace-root` still names the approved `zed-workspace`; and
  5. `--no-auto-start` remains present.

  This test must call through the real builder. A hand-assembled assertion disconnected from
  `run_plan1119_real_zed()` is not valid RED evidence.

- [x] **Step 3: Cover the explicit helper branch directly.** Extend or add
  `test_opaque_relay_command_preserves_explicit_child_args_without_repeating_executable`. Call
  `build_opaque_relay_command(..., child_executable=Path(sys.executable),
  child_args=[str(launcher), "--workspace-root", str(workspace), "--no-auto-start"])` and assert the
  command segment after `--` is exactly that explicit list. Parse `--child-executable` separately
  and prove the resolved relay child argv has one interpreter followed by the launcher. Retain the
  existing `child_args=None` test.

- [x] **Step 4: Run RED and retain the production-path diagnostic.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -k "relay_child_argv_contains_interpreter_exactly_once or preserves_explicit_child_args_without_repeating_executable" -q
  ```

  Expected: the call-boundary test fails because current main records `sys.executable` twice, at
  indices 0 and 1. An unstubbed process/TTY failure or a synthetic assertion is not valid RED.

- [x] **Step 5: Implement the minimum one-line production correction.** Change only the explicit
  list at the real-Zed call from
  `[str(sys.executable), str(launcher), "--workspace-root", ...]` to
  `[str(launcher), "--workspace-root", ...]`. Keep
  `child_executable=Path(sys.executable)`, the relay CLI, workspace, approval lifecycle, launcher
  contents, and all flags unchanged.

- [x] **Step 6: Prove GREEN at both call boundaries.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -k "relay_child_argv_contains_interpreter_exactly_once or preserves_explicit_child_args_without_repeating_executable or approves_actual_workspace_only_for_launch" -q
  uv run --frozen python -m ruff check tools/probe_p11_zed_session_load.py tests/unit/tools/test_probe_p11_zed_session_load.py
  ```

  Expected: the actual production-path argv is
  `python launcher.py --workspace-root <zed-workspace> --no-auto-start`, Option A remains green, and
  no external process or approval ceremony runs.

## Task 10: Capture relay-child stderr without weakening custody or evidence verification

**Owner:** Cursor implements; Codex reviews.

**Scope classification:** Multi-file offline relay-contract and evidence-diagnostic patch.

**Relay interface:** Add `RELAY_CHILD_STDERR_NAME = "relay-child-stderr.txt"` and a private
`_open_private_child_stderr(run_dir: Path) -> BinaryIO` that opens the run-dir path in binary write
mode. `run_relay()` passes that file object as the child's `stderr` target and closes it on normal
exit, spawn failure, relay failure, and interruption. It never uses `PIPE`, never decodes the live
stream, and never copies child stderr to ACP or parent relay stderr.

**Evidence interface:** Add `RELAY_CHILD_STDERR_EXCERPT_LIMIT = 4000` and a private post-run helper
that reads the raw scratch file with UTF-8 replacement, collapses whitespace, keeps at most the
trailing 4000 characters, and passes the result through `_safe_payload`. Store the resulting string
at optional top-level `relay_child_stderr_excerpt` before cleanup. The sidecar and
`_manifest_from_sanitized_result()` therefore receive the same safe value; the raw file never enters
the reconstructed bundle.

- [x] **Step 1: Write RED relay-capture tests.** Add
  `test_child_stderr_is_captured_privately_without_touching_protocol_streams` using a real
  `sys.executable -c` child that writes a fixed sentinel to stderr and protocol bytes to stdout.
  Assert:
  1. `relay-child-stderr.txt` contains the exact sentinel bytes;
  2. parent-forwarded stdout and `agent-to-zed.bin` contain only the stdout bytes;
  3. `zed-to-agent.bin` is unchanged;
  4. the parent relay stderr buffer contains no child sentinel; and
  5. `verify_relay_capture()` still passes.

  Rename/update
  `test_popen_receives_env_none_cwd_none_exact_argv_inherited_stderr_no_shell` so its Popen spy
  asserts `stderr` is the open private run-dir file, not `None` or `PIPE`, while `env=None`,
  `cwd=None`, `shell=False`, and exact argv remain unchanged. Add a spawn-error/interrupt case that
  proves the file handle is closed.

- [x] **Step 2: Pin the unchanged relay summary contract.** In the same tests assert
  `SCHEMA_SUMMARY == "plan117-custody-relay-summary-v1"`, the existing summary fields and child exit
  semantics are unchanged, and `relay-child-stderr.txt` is not counted as either directional bin.
  The raw diagnostic is additional scratch data, not a third ACP direction.

- [x] **Step 3: Write RED probe persistence tests.** Extend the stubbed real-Zed capture to create
  `<capture-root>/<run-id>/relay-child-stderr.txt` containing a credential canary, irregular
  whitespace, and more than 4000 characters. Add
  `test_real_zed_sidecar_and_bundle_include_bounded_sanitized_child_stderr_excerpt` and assert:
  1. the returned result, written sidecar, and materialized manifest contain the same
     `relay_child_stderr_excerpt`;
  2. it is a string of at most 4000 characters;
  3. the credential canary and raw scratch path are absent;
  4. the four reconstructed bundle files remain report, manifest, and two relay bins only; and
  5. `verify_manifest()` accepts the new bundle.

  Retain `test_launch_log_excerpt_runs_through_evidence_sanitizer`, but do not use
  `zed_launch.log_excerpt` as the relay-child channel.

- [x] **Step 4: Write RED verifier compatibility tests.** Add
  `test_optional_relay_child_stderr_excerpt_is_backward_compatible_and_bounded`:
  - the existing fixture/bundle shape with no optional field passes unchanged;
  - a sanitized string at lengths 0 and 4000 passes;
  - a non-string or 4001-character value fails with a field-only diagnostic; and
  - a credential-like value fails through the existing sanitizer scan without echoing the value.

  Keep `SCHEMA == "plan-11-19-zed-session-load-reprobe-v1"` and do not add the optional field to
  `REQUIRED_FIELDS`. Also run the verifier against both committed historical Plan 11.24 bundles.

- [x] **Step 5: Run RED selectors and the surface inventory.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py -k "child_stderr or popen_receives" -q
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -k "bounded_sanitized_child_stderr_excerpt" -q
  uv run --frozen pytest tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -k "optional_relay_child_stderr_excerpt" -q
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
  ```

  Expected: behavior tests fail on inherited/missing stderr capture and missing optional-field
  validation. The surface verifier reports the new `_open_private_child_stderr` persistence sink
  once production code is introduced; record its exact generated key for Step 7.

- [x] **Step 6: Implement the minimum private-capture and additive evidence path.**
  - Open the raw diagnostic in the already-private relay run dir before Popen and pass the file
    object as `stderr`. Close it in the outer relay lifecycle even if Popen or forwarding fails.
  - Keep `err_out` exclusively for fixed relay reason codes. Do not forward or print child bytes.
  - Leave `_write_summary()`, `SCHEMA_SUMMARY`, and `verify_relay_capture()` acceptance rules for
    existing custody files unchanged.
  - After `_launch_zed_once()` returns and before any return-code/capture classification branch,
    read the child stderr file through the bounded sanitizer helper and set
    `relay_child_stderr_excerpt`. Missing files produce `""` rather than raw exception text.
  - In the evidence verifier, validate the optional field only when present. Do not change the
    schema constant, required-field tuple, existing digests, or old-bundle acceptance.

- [x] **Step 7: Classify the new Plan 9.96 surface instead of bypassing it.** Add exactly the
  inventory key emitted for `_open_private_child_stderr` to
  `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json`. Its rationale must state
  that raw child stderr is confined to the throwaway private run root, never promoted, and only the
  separately bounded `_safe_payload` result crosses into sidecar/manifest. Point `test_node` at
  `test_child_stderr_is_captured_privately_without_touching_protocol_streams` or the exact final
  equivalent. Preserve every pre-existing key and classification.

- [x] **Step 8: Prove GREEN across relay, probe, verifier, backward compatibility, and policy.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py -q
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -q
  uv run --frozen pytest tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -q
  uv run --frozen python tools/verify_plan1119_zed_reprobe_evidence.py --manifest reports/plan-11-24-zed-guided-session-load-probe/manifest.json
  uv run --frozen python tools/verify_plan1119_zed_reprobe_evidence.py --manifest reports/plan-11-24-zed-guided-session-load-probe-v3/manifest.json
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
  uv run --frozen python -m ruff check tools/plan117_custody_relay.py tools/probe_p11_zed_session_load.py tools/verify_plan1119_zed_reprobe_evidence.py tests/unit/tools/test_plan117_custody_relay.py tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py
  ```

  Expected: raw stderr is private and cross-stream safe, only the bounded sanitized excerpt is
  persisted, both old bundles remain accepted unchanged, and the surface verifier reports zero
  unclassified sinks, zero stale entries, and zero unresolved test nodes.

## Task 11: Pin the v3 bundle and relay-child-argv root-cause report

**Owner:** Codex authors and verifies in the v4 amendment PR; Claude reviews; operator alone merges.

**Scope classification:** Historical evidence copy plus one new causal report; no code change and no
reproduction.

- [x] **Step 1: Verify the source bundle before copying.** Confirm the capture worktree contains
  exactly these four files and hashes:

  | Relative path | Bytes | SHA-256 |
  |---|---:|---|
  | `manifest.json` | 4199 | `204205cbe48c928b2cb93b1eca8a1c791315ae0dc2d60ff1140b1ffa206d159f` |
  | `relay/agent-to-zed.bin` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
  | `relay/zed-to-agent.bin` | 424 | `2b0f9ac7e9c3cdb861fb4c8c957bf9324596cbe7f85865c0682630694923a107` |
  | `report.md` | 446 | `b8c986326ef573c6e70c43a30b3d4c6f91e70c1f67b9e14d9ea9e7d88fa6181a` |

  Run the unchanged verifier and require exit 0 before and after the copy. Do not reconstruct the
  bundle from prose or the offline 345-byte reply.

- [x] **Step 2: Copy the bundle byte-exact and author the causal report.** The report must:
  - state `INDETERMINATE / OBSERVATION_INCOMPLETE`, `zed_launches: 1`, Zed 1.15.1, the 424-byte
    request, and zero-byte reply from the committed manifest;
  - reproduce the four-step offline bisection and its 345-byte success;
  - cite the relay contract at `tools/plan117_custody_relay.py:1173` and the doubled production call
    at `tools/probe_p11_zed_session_load.py:1967,1971`;
  - name `f713aef` and the `child_args=None` unit-test blind spot;
  - exonerate Option A, settings seeding, agent health, and relay byte forwarding while distinguishing
    relay child construction and diagnostic capture;
  - record inherited child stderr and empty Zed GUI log as the two secondary defects;
  - preserve the seven-shot causal layering above; and
  - state the exact `INDETERMINATE` consequence and that no new launch follows.

- [x] **Step 3: Prove byte identity, verifier validity, and forward-only scope.**

  ```bash
  uv run --frozen python tools/verify_plan1119_zed_reprobe_evidence.py --manifest reports/plan-11-24-zed-guided-session-load-probe-v3/manifest.json
  uv run --frozen pytest tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py tests/unit/docs/test_open_work_pool_hygiene.py -q
  git hash-object docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe.md
  git hash-object docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v2.md
  git hash-object docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v3.md
  git diff --check
  ```

  Expected: verifier exit 0; hygiene green; frozen blobs match the header; the four copied hashes
  match Step 1; and the amendment diff contains only this v4 plan, the new `-v3` bundle, and the new
  relay-child-argv report. Record explicitly that no Zed/acpx/Redis/ACP process, TTY ceremony,
  keyring mutation, network request, provider call, or paid call ran.

## Task 9–10 atomic offline verification and publication

After Tasks 9–10 are GREEN, run:

```bash
uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -q
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
uv run --frozen python tools/verify_plan1119_zed_reprobe_evidence.py --manifest reports/plan-11-24-zed-guided-session-load-probe/manifest.json
uv run --frozen python tools/verify_plan1119_zed_reprobe_evidence.py --manifest reports/plan-11-24-zed-guided-session-load-probe-v3/manifest.json
uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
uv run --frozen python -m ruff check .
git diff --check
```

Then prove:

- the implementation diff contains only Task 9–10 code/tests/audit changes plus this v4 plan's
  checkbox updates;
- `git diff --exit-code -- src/optimus src/optimus_gateway` is clean;
- v1/v2/v3 blobs remain pinned;
- both historical Plan 11.24 bundles and both root-cause reports are byte-identical to
  `origin/main`;
- no raw `relay-child-stderr.txt` exists in a committed report directory;
- `relay_child_stderr_excerpt` is optional, sanitized, bounded, and absent from required fields;
- no `--launch-approval-id` or synthesized confirmation input was added; and
- no live, interactive, keyring, network, credential, or paid action ran.

Stage only the authorized implementation files, create one atomic implementation commit, push the
Cursor branch, and open one draft PR. The PR description carries genuine RED output, GREEN commands,
the exact file list, surface-audit result, both old-bundle verifier passes, frozen blob checks, and
the explicit no-live-action fact. Do not merge.

## Live-observation custody

Nothing in `_v4` may execute a future Zed observation. The former single-launch Future Gates are
removed rather than retained as a dormant ceremony: Zed source establishes that a fresh hermetic
profile has no persisted `ThreadMetadata.session_id`, so its first **Start** creates `session/new` and
cannot emit `session/load`. Repeating that path would spend a shot on an observation that is
unreachable by construction.

The corrected observation requires the two-lifecycle resume run shape in
`docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v5.md`: Lifecycle A
creates and persists a thread after exactly one send; Lifecycle B relaunches on the same hermetic
`--user-data-dir` and opens that persisted thread to observe `session/load`. `_v5` owns the explicit
early proof of the no-Gateway prompt path, its shared-profile/two-launch/one-send boundary, any
future report target, all live prerequisites, and every separately recorded operator grant.

The hermetic-profile, sanitized-evidence, isolation, origin-A exclusion, normal-advertisement, and
no-inference constraints carry forward to `_v5`. This `_v4` amendment retains only the offline
relay-child argv, diagnostic-capture, and historical-evidence package in Tasks 9–11.

## Stop conditions

Stop and return to the reviewer if any of these becomes true:

1. Task 9 requires changing the relay's prepend contract, launcher semantics, Option A, or any
   `src/` module rather than removing the duplicated probe argument.
2. Child stderr cannot be captured without mutating ACP bytes, using an undrained `PIPE`, changing
   relay-summary v1, or weakening `verify_relay_capture()`.
3. The optional diagnostic requires changing `SCHEMA` or `REQUIRED_FIELDS`, rejects either existing
   Plan 11.24 bundle, or otherwise changes accepted rules for bundles that omit the field.
4. Raw child stderr, an ambient path, a credential, or unsanitized exception text would enter the
   sidecar, manifest, report, reconstructed relay bins, or committed tree.
5. The new persistence sink cannot be classified with a truthful Plan 9.96 rationale and resolvable
   test node without suppressing inventory.
6. The v3 bundle differs from Task 11's four hashes, gains a fifth file, or its zero-byte reverse
   stream is replaced.
7. The offline diff extends beyond the file map, modifies a frozen predecessor/status artifact, or
   reopens the settled Option A/B/C ruling.
8. Any task needs Zed, Redis, acpx, ACP, a TTY ceremony, OS-keyring mutation, network access,
   credentials, or paid-call authority.

An ordinary test failure inside the authorized offline scope is not a stop condition. Diagnose it,
preserve genuine TDD evidence, and continue within the settled design.

## Definition of Done and evidence map

| Claim | Required evidence |
|---|---|
| The probe obeys the relay child-executable contract. | Genuine RED→GREEN production-call spy proves resolved `sys.executable` exactly once at index 0 and the isolated launcher at index 1; direct explicit-`child_args` helper test pins the other branch. |
| The corrected command is causally sufficient for the handshake layer. | Accepted offline bisection sends the same captured `initialize` through the real relay: doubled interpreter exits 1 with zero reply; one interpreter exits 0 with the correct 345-byte reply. No live claim extends beyond that handshake. |
| Child stderr is diagnosable without corrupting ACP custody. | Real-child relay test proves exact private stderr bytes, unchanged directional bins/forwarded stdout, no leak to parent relay stderr, closed handles, and unchanged summary-v1 verifier pass. |
| Persisted diagnostics are safe and bounded. | Probe test proves identical at-most-4000-character `_safe_payload` excerpt in result/sidecar/manifest, no canary/raw path, no raw diagnostic file in the bundle, and real verifier pass. |
| Existing evidence remains accepted unchanged. | Both historical Plan 11.24 manifests verify at exit 0; optional-field tests keep schema/required fields unchanged and reject invalid/new unsafe values without echo. |
| Plan 9.96 coverage remains truthful. | Surface verifier is green with the exact new persistence key, truthful scratch-only rationale, and resolvable cross-stream test node; no existing entry drifts. |
| The v3 shot and root cause are preserved accurately. | Four exact hashes, verifier exit 0, causal report with file/line and `f713aef` origin, test blind spot, exonerations, secondary defects, seven-shot layering, and exact `INDETERMINATE` consequence. |
| The package stayed offline and forward-only. | Authorized file diff, clean tests/Ruff/hygiene/CI, frozen v1/v2/v3 blobs, unchanged historical artifacts, and explicit no-live-action PR record. |

Tasks 9–11 do not establish `REACHABLE` or `UNREACHABLE`, do not answer whether Zed sends
`session/load` after the now-proven handshake, and do not define or authorize a live ceremony. The
two-lifecycle observation is exclusively `_v5` custody.

## Explicit exclusions and custody

| Excluded item | Custody |
|---|---|
| Any corrected preflight, TTY ceremony, GUI action, Zed launch, prompt/cost decision, or launch-budget grant | `_v5` two-lifecycle run shape; operator owns machine state and is sole budget authority. |
| Changes to Option A or use of `--launch-approval-id` | Frozen v3 authorization design / Plan 9.96 production security contract; unavailable without a separately approved architecture change. |
| Shared acpx and Zed workspace | Rejected v3 Option C; no scheduled implementation. |
| Raw relay-child stderr publication or a committed fifth bundle file | Forbidden diagnostic path; raw bytes remain private throwaway scratch only. |
| Changes to relay ACP framing, forwarding, index, summary schema, or parent reason-code stderr | Plan 11.7 custody contract; untouched except the separately captured child diagnostic target. |
| Changes to v1, v2, v3, the v1-era bundle, or the launch-approval root-cause report | Frozen historical artifacts; cite only. |
| Changes to `src/optimus`, normal `loadSession` advertisement, durable ACP store/handler, or session history | `P11-FU-1` / `P11-FEAT-ZED-RESUME`; only a future `REACHABLE` result can justify separate design. |
| Origin-A fixture/correlation, Zed refusal-rendering panic, or same-session retry policy | Existing Plan 11.7 / `P9.8-FU-5` / `P11-FU-11` custody; untouched by this repair. |
| Pool, roadmap, README, or manufactured plan-index changes | Reviewer documentation-freshness audit; no current Plan 11.24 pointer exists to advance. |
| `CURRENT.md` and reviewer checkpoint updates | Reviewer/operator handoff lane; never stage them in the implementation commit. |

## Plan self-review

- The Status line is written for the merged amendment state: v4 is live, Tasks 9–10 are not started,
  Task 11 is present in the same PR, and no live authority exists.
- All three predecessor blobs are pinned and immutable; the header supplies the only required live
  pointer.
- The argv repair is one line at the production call boundary and has a genuine RED assertion on the
  resolved child command, not only the builder's default branch.
- The stderr design separates raw scratch custody from sanitized evidence: no live decode, no ACP
  merge, no undrained pipe, no raw promotion, and a fixed 4000-character optional field.
- Relay-summary v1, the evidence schema, required fields, old-bundle acceptance, sanitizers, and
  verifier rules remain intact; any incompatible discovery is an explicit stop.
- The new persistence surface is audited rather than hidden, with both behavioral and policy gates.
- Task 11 preserves the zero-byte reverse stream as evidence and records the accepted four-step
  bisection without recreating revoked scratch state.
- The seven-shot table keeps launch/argv, settings, approval, and relay-child argv as distinct
  necessary layers.
- `_v4` carries no known-wrong future ceremony: Zed source proves a fresh single-launch profile cannot
  answer the resume question. `_v5` owns the distinct, falsifiable two-lifecycle observation.
- The prerequisites cover only Tasks 9–11. `_v5` supplies the separate live machine state, TTY/GUI,
  shared-profile, one-send/cost, and launch-grant prerequisites, with the remaining inference as an
  early establishing task.
