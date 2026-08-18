# Plan 11.24 — Operator-Guided Zed `session/load` Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` or `superpowers:executing-plans` task-by-task, and `superpowers:test-driven-development` for every behavior change. Steps use checkbox syntax. Do not mark a checkbox complete until its stated verification command has passed.

**Goal:** Make one operator-guided, current-Zed `session/load` observation capable of producing verifier-valid sanitized evidence, then use its result to inform—rather than decide—the Zed-resume lane.

**Architecture:** Reuse Plan 11.19’s isolated source/build, hermetic Zed profile, opaque relay, real `acpx` baseline, and result classifier. Before cleanup removes the raw capture root, materialize only reconstructed sanitized relay bytes plus a sanitizer-safe manifest/report in a new Plan 11.24 evidence directory; the unchanged offline verifier remains the authority. Thread a bounded guided timeout into the existing launch seam, retaining its 180-second unattended default. No normal Optimus behavior, Plan 11.19 artifact, or origin-A state changes.

**Tech Stack:** Python 3.14, the existing Plan 11.19 Zed probe/relay/verifier, independently authored `acpx`, Windows Zed, pytest, and Ruff.

**Spec:** `D:\Projects\Development\Python\optimus-agent-handoff\WP-6-codex-plan-11-24-zed-guided-probe.md`; frozen probe contract: `docs/superpowers/specs/2026-08-15-p11-feat-zed-resume-current-version-zed-reprobe-brief.md`; historical harness: `docs/superpowers/plans/2026-08-17-plan-11-19-current-zed-session-load-reprobe.md`.

## Authority and baseline anchors

- This is a forward-only evidence sub-plan for `P11-FEAT-ZED-RESUME`; it does not close, transfer, or alter `P9.8-FU-5`, `P11-FU-1`, `P11-FU-11`, or their pool rows.
- Drafting baseline is `origin/main` `fbdcbfadf8a7b7ee40e48a1216228aec35c3741b`. `Plan 11.23` is allocated; a repository search found no Plan 11.24 document.
- At baseline, `_launch_zed_once()` has `timeout_s: float = 180.0` (`tools/probe_p11_zed_session_load.py:1517-1566`) and `run_plan1119_real_zed()` calls it with no override (`:1806-1811`).
- At baseline, reconstructed sanitized relay bytes are kept only in `_sanitized_relay_zed` and `_sanitized_relay_agent` (`:1849-1850`); sidecar serialization discards `_` keys (`:1914-1918`) after `_cleanup_plan1119_roots()` deletes the run root (`:1892-1900`). The probe contains no `write_bytes` call. The verifier requires `report_dir/relay/zed-to-agent.bin` and `agent-to-zed.bin` to exist and match manifest digests (`tools/verify_plan1119_zed_reprobe_evidence.py:76-98`).
- Plan 11.19’s four empty-capture shots and committed zero-byte artifacts remain valid historical evidence. This plan must neither edit them nor infer anything from their empty-digest compatibility.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| code/state | The harness can persist a complete verifier-valid **nonempty** sanitized relay bundle. | no | implementing agent | genuinely absent but small and buildable now; Task 1 supplies it before any shot. |
| code/state | The harness can keep Zed open long enough for the guided ceremony while preserving the unattended default. | no | implementing agent | genuinely absent but small and buildable now; Task 2 supplies it before any shot. |
| services | Redis is reachable for the isolated ACP server’s real `acpx` baseline. | unknown | operator | merely unauthorized to preflight during this planning package; Task 3 establishes it before launch. |
| tooling/binaries | Real Windows Zed and independently authored `acpx` are installed; execution records fresh identities rather than relying on Zed 1.15.0 / acpx 0.12.0 observations from 2026-08-15. | yes | operator | n/a today; changed/missing tooling is a named preflight failure, never a fake substitute. |
| credentials/authority | A fresh authorization for exactly one real Zed launch is recorded after deterministic gates pass. Gateway credentials are not required. | no | operator | merely unauthorized interactive authority; stop before launch without it. |
| human interaction | The operator trusts the hermetic workspace when **Unrecognized Project / Restricted Mode** appears, then starts **Optimus** from Zed’s Agent panel. | no | operator | merely unauthorized; these are the explicit manual prerequisites Plan 11.19 omitted. |
| cost | The isolated agent uses `--no-auto-start`; the probe sends no prompt and makes no Gateway model call or paid request. | yes | operator | n/a; Task 3 records this non-cost boundary. |

The only `unknown` is Redis. Task 3’s non-launch preflight resolves it before a Zed launch. A failed preflight is `INDETERMINATE / PRECONDITION_UNMET` with `zed_launches: 0`; it is not permission to repair infrastructure ad hoc or retry.

## Global constraints

- Cut the execution branch from refreshed `origin/main`; prove `HEAD == origin/main` before the first write. Do not use this planning branch for implementation.
- Persist **sanitized** reconstructed relay bytes only. Never copy raw capture files, process output, local profile data, credentials, or approval state from the run root.
- The existing manifest digests and verifier checks remain authoritative. Do not weaken or special-case the verifier, and reject a nonempty/foreign report directory rather than overwriting it.
- The 180-second unattended default remains exact. The one guided command explicitly requests 900 seconds; invalid timeout values fail before `subprocess.Popen`.
- The normal agent remains unadvertised for `loadSession`; only the throwaway isolated probe advertises it and returns `{}`. Normal-source digests, normal profile paths, and normal settings remain untouched.
- One Zed launch only: `zed_launches == 1`, `origin_a_launches == 0`, no origin-A fixture, no `origin-a-4`, no correlation claim, no prompt, no retry, and no budget expansion.
- `REACHABLE` requires a captured Zed `session/load` request and isolated `{}` response. `UNREACHABLE` requires a captured protocol/method error. All other results are `INDETERMINATE` with a named reason; normal Optimus non-advertisement is never a Zed result.

## File map

| Path | Responsibility |
|---|---|
| `tools/probe_p11_zed_session_load.py` | Validated timeout input; atomic sanitizer-safe evidence-bundle materialization from reconstructed relay bytes; unchanged classifier/cleanup/verifier contract. |
| `tests/unit/tools/test_probe_p11_zed_session_load.py` | Nonempty bundle round-trip through the real offline verifier; no raw-byte persistence; timeout default/override/invalid-value behavior. |
| `reports/plan-11-24-zed-guided-session-load-probe/` | Created only by the one authorized execution after cleanup: sanitized manifest, report, and relay files. |
| `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe.md` | Approved runbook, prerequisites, one-shot boundary, and outcome consequences. |

## Tasks

### Task 1: Materialize nonempty sanitized relay evidence before the live shot

**Files:**

- Modify: `tools/probe_p11_zed_session_load.py:1728-1968`
- Modify: `tests/unit/tools/test_probe_p11_zed_session_load.py`

**Interfaces:** Add a private `materialize_sanitized_zed_evidence(*, report_dir: Path, result: Mapping[str, Any], zed_to_agent: bytes, agent_to_zed: bytes) -> Path`. It accepts only the outputs of `reconstruct_sanitized_relay_bytes`, creates `relay/zed-to-agent.bin`, `relay/agent-to-zed.bin`, `manifest.json`, and `report.md` in a fresh temporary sibling, validates the result with the existing `verify_manifest()`, then atomically publishes the directory. It rejects an existing/nonempty target and any target outside `REPO_ROOT / "reports"`. On an exception or failed cleanup, remove the temporary bundle and retain only the existing sanitized local sidecar.

- [x] **Step 1: Write RED nonempty-bundle tests.** Build a complete safe `REACHABLE` result fixture with a paired `session/load`/`{}` exchange and nonempty reconstructed NDJSON bytes. Assert that materialization publishes both nonempty relay files, their SHA-256 values equal the manifest and `relay` values, `verify_manifest()` passes, and no raw canary inserted into the original capture bytes appears in files, manifest, or report. Add failure tests for an existing target, a target outside `reports/`, and a cleanup-failed result; each leaves no published bundle.

  ```python
  def test_nonempty_sanitized_relay_bundle_passes_existing_verifier(tmp_path: Path) -> None:
      report_dir = tmp_path / "reports" / "plan-11-24-zed-guided-session-load-probe"
      manifest = materialize_sanitized_zed_evidence(
          report_dir=report_dir,
          result=reachable_result(),
          zed_to_agent=b'{"method":"session/load"}\n',
          agent_to_zed=b'{"result":{}}\n',
      )
      verify_manifest(manifest)
      assert (report_dir / "relay" / "zed-to-agent.bin").read_bytes()
  ```

- [x] **Step 2: Run the RED selector.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -q
  ```

  Expected: new tests fail because the materialization seam does not exist; no Zed, acpx, or external dependency runs.

- [x] **Step 3: Implement safe materialization and wire it before the run returns.** After relay capture, reconstruct sanitised bytes exactly once. Preserve them only in local memory and the temporary sanitized bundle; never write the capture-root raw `.bin` files to the report directory. In `finally`, publish only after `cleanup_verified` is true and the final normal-source digest still matches; otherwise remove the temporary bundle. Generate the verifier-compatible existing schema and a report whose heading says Plan 11.24, states the classifier result, and names the previous Plan 11.19 bundle as unchanged. Do not alter `tools/verify_plan1119_zed_reprobe_evidence.py` or its accepted rules.

- [x] **Step 4: Run GREEN tests and static fitness.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -q
  uv run --frozen ruff check tools/probe_p11_zed_session_load.py tests/unit/tools/test_probe_p11_zed_session_load.py
  git diff --check
  git diff --exit-code -- docs/superpowers/plans/2026-08-17-plan-11-19-current-zed-session-load-reprobe.md reports/plan-11-19-zed-session-load-reprobe
  ```

  Expected: nonempty and historical-empty verifier tests pass; frozen Plan 11.19 plan/evidence is unchanged.

- [x] **Step 5: Commit the deterministic evidence seam.**

  ```powershell
  git add tools/probe_p11_zed_session_load.py tests/unit/tools/test_probe_p11_zed_session_load.py
  git commit -m "test(zed): persist sanitized guided relay evidence"
  ```

### Task 2: Add the bounded guided-timeout seam

**Files:**

- Modify: `tools/probe_p11_zed_session_load.py:1517-1566,1728-1968`
- Modify: `tests/unit/tools/test_probe_p11_zed_session_load.py`

**Interfaces:** Add `DEFAULT_ZED_LAUNCH_TIMEOUT_SECONDS = 180.0` and `validate_zed_launch_timeout_seconds(value: float) -> float`. Extend `run_plan1119_real_zed(parent_workspace: Path, *, launch_timeout_seconds: float = DEFAULT_ZED_LAUNCH_TIMEOUT_SECONDS, report_dir: Path) -> dict[str, Any]`. Add `--zed-launch-timeout-seconds` (float, default 180) and required-for-`real-zed` `--report-dir`; only the guided command supplies 900. The validator accepts finite values in `[60.0, 900.0]`, and the sanitized `zed_launch` metadata records the selected value.

- [x] **Step 1: Write RED timeout tests.** Assert no CLI flag parses as `180.0`; `--zed-launch-timeout-seconds 900` parses as `900.0`; `0`, `-1`, `nan`, `inf`, and `901` fail before `Popen`; and a patched `_launch_zed_once` observes exactly the chosen value while a patched preparation path guarantees no GUI launch.

- [x] **Step 2: Run the RED selector.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -q
  ```

  Expected: the new timeout assertions fail because no public parser/runner seam exists; no Zed starts.

- [x] **Step 3: Implement the minimum timeout path.** Keep `_launch_zed_once(..., timeout_s=180.0)` unchanged as the default; validate and thread the selected value only along the real-Zed path. Preflight and acpx-baseline semantics remain unchanged. Do not add UI automation, retries, alternate profile roots, fallback agents, or normal `loadSession` advertisement.

- [x] **Step 4: Run GREEN tests and static fitness.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -q
  uv run --frozen ruff check tools/probe_p11_zed_session_load.py tests/unit/tools/test_probe_p11_zed_session_load.py
  git diff --check
  git diff --exit-code -- src/optimus src/optimus_gateway
  ```

- [x] **Step 5: Commit the timeout seam.**

  ```powershell
  git add tools/probe_p11_zed_session_load.py tests/unit/tools/test_probe_p11_zed_session_load.py
  git commit -m "test(zed): allow bounded guided probe timeout"
  ```

### Task 3: Establish live prerequisites without launching Zed

**Files:**

- Create locally only: `%LOCALAPPDATA%\Optimus\p11-24-zed-guided-probe\plan1119-preflight-result.json`

**Interfaces:** Consumes Tasks 1-2. Produces a sanitized preflight sidecar with `zed_launches: 0`, current Zed/acpx identities, Redis result, isolated capability proof, and cleanup predicates. Any failed predicate is terminal for this one-shot package.

- [ ] **Step 1: Record fresh operator authority.** The reviewer checkpoint must record authorization for exactly one Windows Zed launch, the 900-second timeout, and the two UI actions in Task 4. Without it, stop before any live command.

- [ ] **Step 2: Run the exact non-launch preflight.** From the checkout containing merged Tasks 1-2:

  ```powershell
  $probeParent = Join-Path $env:LOCALAPPDATA 'Optimus\p11-24-zed-guided-probe'
  New-Item -ItemType Directory -Force -Path $probeParent | Out-Null
  uv run --frozen python tools/probe_p11_zed_session_load.py --mode preflight $probeParent
  Get-Content -Raw (Join-Path $probeParent 'plan1119-preflight-result.json')
  ```

  Expected: `preflight_ok: true`, `zed_launches: 0`, `origin_a_launches: 0`, a current Zed/acpx identity, Redis/acpx baseline success, normal `loadSession: false`, isolated `loadSession: true`, and verified cleanup.

- [ ] **Step 3: Stop on any failed preflight.** Missing Redis, tool drift, failed acpx baseline, isolation/cleanup failure, or already-running Zed is `INDETERMINATE` with its named reason. Retain the sanitized sidecar only; do not repair, retry, or launch Zed.

### Task 4: Execute the single guided capture and state its consequence

**Files:**

- Create: `reports/plan-11-24-zed-guided-session-load-probe/manifest.json`
- Create: `reports/plan-11-24-zed-guided-session-load-probe/report.md`
- Create: `reports/plan-11-24-zed-guided-session-load-probe/relay/zed-to-agent.bin`
- Create: `reports/plan-11-24-zed-guided-session-load-probe/relay/agent-to-zed.bin`

**Interfaces:** Consumes the successful Task 3 preflight, untouched source/evidence baseline, and fresh authorization. Produces one atomically materialized, sanitized bundle. The report uses the existing verifier-compatible schema because the evidence contract is unchanged; its title/directory identify Plan 11.24.

- [ ] **Step 1: Recheck the one-shot boundary.**

  ```powershell
  git status --short --branch
  git rev-parse HEAD
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -q
  ```

  Expected: deterministic tests pass, no report directory already exists, and no Zed target is running. Otherwise stop without launch.

- [ ] **Step 2: Execute this command exactly once.**

  ```powershell
  uv run --frozen python tools/probe_p11_zed_session_load.py --mode real-zed --zed-launch-timeout-seconds 900 --report-dir reports/plan-11-24-zed-guided-session-load-probe $probeParent
  ```

  Expected: a hermetic Zed window opens for the newly generated `zed-workspace` and remains available for up to 15 minutes. Never re-run this command.

- [ ] **Step 3: Perform exactly two UI actions.**

  1. On the **Unrecognized Project / Restricted Mode** dialog for the generated workspace, select the action whose label contains **Trust**. Expected: the restriction banner/dialog disappears. If the dialog or a Trust-labelled action is absent, close the hermetic Zed window immediately; preserve only the bounded `INDETERMINATE` observation.
  2. Open Zed’s **Agent** panel, select **Optimus**, and invoke its visible **Start** action once. Expected: it changes to started/connected and the relay can receive ACP bytes. If Optimus or Start is absent, or the panel errors, close Zed immediately; do not configure another agent or retry.

  After the second action, wait up to the remaining 900-second window for protocol traffic, then close the hermetic Zed window yourself. Closing it is the end-of-capture signal; do not wait for forced `taskkill`.

- [ ] **Step 4: Verify and stage only the atomic bundle.**

  ```powershell
  uv run --frozen python tools/verify_plan1119_zed_reprobe_evidence.py --manifest reports/plan-11-24-zed-guided-session-load-probe/manifest.json
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py tests/unit/docs/test_open_work_pool_hygiene.py -q
  uv run --frozen ruff check .
  git diff --check
  git diff --exit-code -- docs/superpowers/plans/2026-08-17-plan-11-19-current-zed-session-load-reprobe.md reports/plan-11-19-zed-session-load-reprobe
  ```

  Expected: verifier/tests/Ruff pass and Plan 11.19 bytes remain unchanged. If cleanup/materialization/verification fails, do not stage a bundle; retain only local sanitized remediation and stop.

- [ ] **Step 5: Record, but do not decide, the lane consequence.** The Plan 11.24 report must state exactly one applicable consequence:

  | Result | Consequence |
  |---|---|
  | `REACHABLE` | The tested current Zed issued `session/load`; a separately scoped `P11-FU-1` durable ACP session-store/handler design is justified, but this plan does not implement it. |
  | `UNREACHABLE` | A captured Zed protocol/method error requires an operator disposition for the Zed-resume lane rather than presumed durable-store implementation. |
  | `INDETERMINATE` | The named missing precondition/observation remains; no implementation or disposition follows automatically. |

  ```powershell
  git add tools/probe_p11_zed_session_load.py tests/unit/tools/test_probe_p11_zed_session_load.py reports/plan-11-24-zed-guided-session-load-probe
  git commit -m "test(zed): capture guided session-load probe"
  ```

## Definition of done and evidence map

| Claim | Required evidence |
|---|---|
| A successful nonempty capture is preservable and independently verifiable | Task 1 fixture with nonempty bytes, published bundle, SHA-256 assertions, and unchanged real verifier pass. |
| Guided UI time cannot be killed by the unattended default | Default/900-second/invalid-value unit tests and sanitized selected-timeout metadata. |
| The observation is current-Zed and isolated | Fresh identities, hermetic invocation, normal/isolated capability proof, source digests, and cleanup record. |
| Only one authorized shot occurred | Manifest `zed_launches: 1`, `origin_a_launches: 0`, plus reviewer checkpoint authorization. |
| The result does not silently choose a Zed-lane outcome | The report’s exact outcome-consequence row, with no pool-status edit. |

## Explicit exclusions and custody

| Excluded work | Owner | Reason |
|---|---|---|
| Durable ACP store, session identity/history design, `session/load` handler, normal capability advertisement | `P11-FU-1` / `P11-FEAT-ZED-RESUME` | This probe decides whether such implementation is justified; it does not build it. |
| Origin-A fixture, fourth correlation attempt, or budget expansion | Frozen Plan 11.7 custody / operator | The historical correlation budget remains exhausted. |
| Zed refusal-rendering panic | `P9.8-FU-5` / `P11-FEAT-ZED-RESUME` | This plan observes only `session/load`. |
| Same-session retry proof and retry/budget policy | `P11-FU-11` / `P11-FEAT-ZED-RESUME` | This plan sends no prompt and does not reuse the dead session. |
| Plan 11.19 evidence and frozen plan | Frozen historical artifact | Cite them; never modify them. |

## Plan self-review

- The two operator-authorized harness gaps are separate, deterministic Tasks 1-2, before the unknown Redis preflight and the single live shot.
- The prerequisites table covers every applicable category, explicitly gives both missed UI actions to the operator, and names Task 1 for the former nonempty-evidence gap.
- The materialization test proves a nonempty success-shaped bundle through the actual existing verifier, while Plan 11.19’s empty artifacts remain untouched and valid.
- The runbook contains exact commands, expected UI, stop actions, one-shot bounds, origin-A exclusions, result discipline, and all three possible consequences.
