# Plan 11.19 Current-Zed `session/load` Re-probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine, on the Zed version installed at execution time, whether a real Zed client sends ACP `session/load` after an isolated temporary agent advertises top-level `agentCapabilities.loadSession: true` and returns an empty successful response.

**Architecture:** Extend the existing non-launching `acpx` probe into a separate real-Zed path that manufactures an isolated source/build outside the normal workspace, changes only the temporary probe's top-level capability and empty `session/load` response, and runs Zed through an opaque byte relay. A deterministic verifier accepts only sanitized committed evidence, enforces the four isolation predicates and exact result classification, and leaves the normal committed agent unreachable from the temporary behavior.

**Tech Stack:** Python 3.14, pytest, pytest-asyncio, coverage.py/pytest-cov, Ruff, Git, independently authored `acpx`, the installed Windows Zed binary, a hermetic Zed user-data root, and a native WSL ext4 clone for non-live parity checks.

## Global Constraints

- Start from `origin/main` and prove `git rev-parse HEAD` equals `git rev-parse origin/main` before implementation; do not reuse a stale checkout.
- Work only in a dedicated worktree/branch; never use `optimus-cost-agent-wt-vibhanshu`.
- This is a forward-only Plan 11.19 amendment. The frozen Plan 11.7 implementation file and its three dated amendments remain byte-identical; do not amend them or reconstruct their absent Task 0 artifacts.
- The task answers a current-version question only. Its result is a new baseline and cannot affirm, reject, or re-diagnose Zed 1.13.1's sealed finding.
- The three-attempt origin-A budget is exhausted. Do not send an origin-A fixture, create `origin-a-4`, make a correlation claim, or alter any stage ledger.
- The normal committed `optimus-agent` must continue to omit top-level `agentCapabilities.loadSession`. The temporary advertisement may exist only in a throwaway source/build rooted outside the normal workspace and removed after the run.
- Before any real Zed process is launched, prove predicates 1-3 and dry-run the cleanup mechanism: normal non-advertisement, isolated-only probe behavior, and an unchanged normal-workspace source digest. Predicate 4 (actual removal of the isolated source/build and hermetic user-data root) is necessarily observed after the run; it is a hard evidence/staging gate, so no result can qualify or be committed until it passes.
- Establish the installed Zed version's hermetic-user-data invocation at execution time. Do not assume an option from the 1.13.1 plan; the operator profile, settings, workspaces, and any already-running Zed process are out of scope and must remain untouched.
- The real-Zed connection uses an opaque byte relay. A project-authored parser may classify captured bytes after the run, but it must not be the source of the claim that Zed issued a request.
- Use real independently authored `acpx` as the ACP baseline client. A unit fake is allowed only in the unit tier; it cannot stand in for the real-Zed or `acpx` evidence tier.
- Persist only sanitizer-approved evidence. Never commit raw credentials, normal-profile data, unsanitized ACP streams, or raw relay bytes. Run the sanitizer and verifier before staging any report.
- Classify exactly: `REACHABLE` requires a captured real-Zed `session/load` request plus its empty successful response; `UNREACHABLE` requires the captured request plus an identified real method/protocol error; all missing dependencies, isolation failures, cleanup failures, or absent captured exchange are `INDETERMINATE` with a named reason.
- Windows is the mandatory live platform. Run only non-live Python fitness gates in a native WSL ext4 clone—never a `/mnt/d` worktree.
- Do not commit, push, or open a PR without the operator's explicit authorization. Run `uv run --frozen ruff check .` before any commit or PR sign-off.

## Baseline Facts and Non-Claims

At base `7d4e466`, `tools/probe_p11_zed_session_load.py` is deliberately an `acpx`-only capability probe: it observes `Zed --version` but has `zed_launches: 0`, does not alter the production agent, and reports `INDETERMINATE / INTERNAL_CAPABILITY_UNAVAILABLE` when the normal agent omits `loadSession`. `reports/p11-feat-zed-resume-session-load-reprobe.md` records that bounded 1.15.0/acpx 0.12.0 run; it is not real-Zed evidence and remains unchanged. `reports/p11-feat-zed-resume-task0-evidence-custody-note.md` records that the frozen 1.13.1 Task 0 raw artifacts are absent from `origin/main`; Plan 11.19 does not replace them.

The temporary probe is permitted to return only the conformant empty successful result below. It must not implement durable session storage, replay, `session/resume`, `session/list`, a persistent configuration switch, or a production capability change.

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "result": {}
}
```

## File Map

| Path | Responsibility |
|---|---|
| `tools/probe_p11_zed_session_load.py` | Existing `acpx` baseline plus a separately selected real-Zed mode that creates, verifies, and removes the isolated probe source/build and hermetic Zed root. |
| `tools/plan117_custody_relay.py` | Existing opaque full-duplex relay, reused without interpreting protocol bytes in transit. |
| `tools/verify_plan1119_zed_reprobe_evidence.py` | Offline verifier for evidence schema, isolation proof, relay digests, sanitizer proof, cleanup, and result discipline. |
| `tests/unit/tools/test_probe_p11_zed_session_load.py` | Deterministic tests for isolated-only patch scope, normal-agent guard, command construction, cleanup failure, and classification. |
| `tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py` | Deterministic positive and tampered-manifest tests for the offline verifier. |
| `reports/plan-11-19-zed-session-load-reprobe/manifest.json` | Sanitized, machine-verifiable current-version evidence manifest. |
| `reports/plan-11-19-zed-session-load-reprobe/report.md` | Sanitized review narrative with the result, limitation, and links to manifest fields. |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Living `P11-FU-10` evidence-reference correction only: `Draft PR #158` becomes `PR #158 (merge 7d4e466)`. |

## Explicit Exceptions and Custody

| Excluded work | Named owner |
|---|---|
| Production `session/load`, durable state, replay, `session/resume`, list/delete behavior, or normal capability advertisement | Frozen Plan 11.7 / `P11-FEAT-ZED-RESUME`, still blocked |
| Historical Zed 1.13.1 Task 0 diagnosis or recovery of absent raw artifacts | Frozen Plan 11.7 evidence custody; `reports/p11-feat-zed-resume-task0-evidence-custody-note.md` |
| Origin-A fixture/correlation execution or budget expansion | `P11-FEAT-ZED-RESUME` budget-expansion amendment, not this plan |
| Zed rendering/DWM/screenshot claims | `EVIDENCE-HANDOFF-FEAT-ZED-RENDER-OBSERVATION` |
| Gateway/provider changes, credentials, or local provider keys | Existing Gateway lanes; prohibited by the one-key model |
| `P11-FU-10` substantive implementation | Closed Plan 11.18; only its one-line merged-PR evidence correction is included here |

---

### Task 1: Create the isolated temporary-advertisement probe and prove normal-operation isolation

**Files:**

- Modify: `tools/probe_p11_zed_session_load.py`
- Modify: `tests/unit/tools/test_probe_p11_zed_session_load.py`
- Reuse without modification: `tools/plan117_custody_relay.py`
- Do not modify: `src/optimus/**`, `src/optimus_gateway/**`, frozen Plan 11.7 files, or the existing Plan 9.96/`acpx`-only report

**Interfaces:**

- Consumes: a clean normal-workspace Git identity; a caller-supplied existing non-repository scratch parent; an installed `acpx`, Zed executable, and `optimus-trust`; and a current-version Zed hermetic invocation descriptor.
- Produces: `prepare_real_zed_probe(...) -> ProbePreparation`, `verify_normal_operation_isolation(...) -> IsolationEvidence`, and an isolated probe executable whose initialize payload contains only the additional top-level `loadSession: true` capability and whose `session/load` handler returns `{}`.

- [ ] **Step 1: Pin the clean base and prove the existing normal-agent guard.**

  Run before writing code:

  ```powershell
  git fetch origin main
  git rev-parse HEAD
  git rev-parse origin/main
  git status --short --branch
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -q
  ```

  Expected: `HEAD` equals `origin/main`, the worktree is clean, and the existing probe tests pass. Inspect the normal initialize path and record the exact payload proving no top-level `loadSession` is advertised. If the payload already includes it, stop: this plan's isolation premise is false and needs a reviewed amendment.

- [ ] **Step 2: Write RED tests for the isolated-only patch and four gate fields.**

  Add unit tests that operate entirely in `tmp_path` and do not launch Zed, `acpx`, Redis, the Gateway, or `optimus-agent`. Require an isolated-copy plan whose semantic patch surface is exactly the temporary initialize capability and the empty `session/load` response. The tests must reject a path inside the normal checkout, an extra modified production file, a normal capability payload containing `loadSession`, a missing before/after source digest, or unremoved scratch roots.

  ```python
  def test_prepare_probe_rejects_normal_workspace_and_extra_patch_surface(tmp_path: Path) -> None:
      normal_root = tmp_path / "normal"
      normal_root.mkdir()
      with pytest.raises(ProbeError, match="outside the normal workspace"):
          prepare_real_zed_probe(normal_root, normal_root=normal_root, scratch_parent=tmp_path)

      plan = ProbePatchPlan(
          changed_paths=("src/optimus/acp/spec.py", "README.md"),
          capability_patch={"loadSession": True},
          load_response={},
      )
      with pytest.raises(ProbeError, match="unexpected patch surface"):
          validate_probe_patch_plan(plan)
  ```

- [ ] **Step 3: Run the new isolation tests RED.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -q
  ```

  Expected: FAIL only because the isolated real-Zed preparation and isolation evidence interfaces do not exist. A failure of an existing `acpx`-only test is a stop condition.

- [ ] **Step 4: Implement a generated isolated source/build, never a normal-workspace switch.**

  Add a real-Zed mode that creates a fresh throwaway source tree under the caller's scratch parent, records the normal tree's Git commit and deterministic tracked-source digest, then creates the probe source/build there. It may use Git archive/worktree mechanics, but it must reject a source root equal to, nested in, or containing the normal checkout. It must record and validate an allowlisted patch manifest before execution:

  ```python
  ALLOWED_PROBE_SEMANTICS = {
      "initialize.agentCapabilities.loadSession": True,
      "request.session/load.response.result": {},
  }

  def classify_real_zed_result(exchange: RelayExchange | None, isolation: IsolationEvidence) -> Finding:
      if not isolation.all_four_predicates_pass:
          return Finding.INDETERMINATE
      if exchange is None:
          return Finding.INDETERMINATE
      if exchange.response.get("result") == {}:
          return Finding.REACHABLE
      if isinstance(exchange.response.get("error"), Mapping):
          return Finding.UNREACHABLE
      return Finding.INDETERMINATE
  ```

  The generated executable must advertise `loadSession` only at the top-level `agentCapabilities`, must return `{}` only to `session/load`, and must retain the normal behavior for every other request. Do not make an environment variable, config option, default flag, or persistent source change capable of selecting the probe in normal operation.

- [ ] **Step 5: Build the mandatory pre-launch isolation record.**

  Before any Zed launch, have the runner record the first three predicates plus a successful cleanup dry-run in a structured `IsolationEvidence` object; after the run it must replace the dry-run field with the observed removal result:

  ```python
  @dataclass(frozen=True)
  class IsolationEvidence:
      normal_agent_load_session_advertised: bool
      isolated_probe_load_session_advertised: bool
      normal_source_sha256_before: str
      normal_source_sha256_after: str
      isolated_source_root: str
      isolated_build_root: str
      hermetic_zed_root: str
      cleanup_dry_run_verified: bool
      cleanup_verified: bool

      @property
      def prelaunch_predicates_pass(self) -> bool:
          return (
              not self.normal_agent_load_session_advertised
              and self.isolated_probe_load_session_advertised
              and self.normal_source_sha256_before == self.normal_source_sha256_after
              and self.cleanup_dry_run_verified
          )

      @property
      def all_four_predicates_pass(self) -> bool:
          return (
              self.prelaunch_predicates_pass
              and self.cleanup_verified
          )
  ```

  `cleanup_verified` remains false until the isolated source/build and hermetic root are absent. `cleanup_dry_run_verified` must be true before launch. A pre-launch failure must prevent Zed invocation, set `zed_launches: 0`, preserve only sanitized diagnostics, and classify the run `INDETERMINATE` with the failed predicate name; a post-run cleanup failure likewise prohibits a qualifying/staged result.

- [ ] **Step 6: Run the unit suite GREEN and the normal-source diff check.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -q
  git diff --check
  git diff --exit-code -- src/optimus src/optimus_gateway
  ```

  Expected: the new deterministic tests pass, whitespace is clean, and the normal production source is unchanged. Commit only after operator authorization:

  ```powershell
  git add tools/probe_p11_zed_session_load.py tests/unit/tools/test_probe_p11_zed_session_load.py
  git commit -m "test(zed): isolate temporary session-load probe"
  ```

### Task 2: Make current-version hermetic Zed invocation and opaque capture fail closed

**Files:**

- Modify: `tools/probe_p11_zed_session_load.py`
- Modify: `tests/unit/tools/test_probe_p11_zed_session_load.py`
- Reuse: `tools/plan117_custody_relay.py`

**Interfaces:**

- Consumes: Task 1's passing `IsolationEvidence`, a real installed-Zed version command, and an explicit current-version hermetic invocation descriptor.
- Produces: `ZedInvocationEvidence`, opaque relay SHA-256 values, and `RelayExchange | None`; raw captured bytes remain untracked scratch artifacts.

- [ ] **Step 1: Write RED tests for current-version invocation discipline and opaque relay boundaries.**

  Add deterministic tests that require an explicit discovered invocation descriptor rather than a hard-coded historical flag, confirm every user-data path is under the generated hermetic root, and prove that protocol classification consumes a sanitized post-run relay extract—not a project-authored client call. Test that an absent descriptor, a path outside the hermetic root, an already-running Zed target, a relay failure, or a nonempty cleanup root prevents a `REACHABLE`/`UNREACHABLE` conclusion.

  ```python
  def test_real_zed_launch_rejects_ambient_profile_and_missing_discovery() -> None:
      invocation = ZedInvocation(argv=("Zed.exe",), user_data_root=None, discovered_from="")
      with pytest.raises(ProbeError, match="current-version hermetic invocation"):
          validate_zed_invocation(invocation, hermetic_root=Path(r"C:\scratch\zed-home"))
  ```

- [ ] **Step 2: Run the invocation tests RED.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -q
  ```

  Expected: FAIL only on the new invocation/relay contracts.

- [ ] **Step 3: Implement discovery, but keep the live launch behind Task 3's approval gate.**

  Implement a no-launch discovery operation that records the exact installed Zed executable path, `--version` output, executable hash, invocation-help/provenance, and the tested current-version argument/environment mapping that binds Zed to a newly created hermetic root. The runner must not silently fall back to `%APPDATA%`, `%LOCALAPPDATA%`, `%USERPROFILE%`, a normal workspace, or an existing Zed process.

  The first actual launch is permitted only when Task 1's pre-launch isolation record passes and the descriptor is complete. Run Zed through `tools/plan117_custody_relay.py` in opaque byte-forwarding mode. Record raw input/output only in the throwaway root, calculate digests, sanitize a bounded parsed classification after process exit, and leave byte interpretation out of the relay process.

- [ ] **Step 4: Require independent `acpx` baseline evidence before Zed execution.**

  Reuse the real `acpx` preparation only against the isolated executable, record its exact version/executable SHA-256 and the isolated initialize payload, and fail closed if it does not confirm the temporary top-level `loadSession: true` advertisement. It establishes the server-side protocol baseline; it does not classify the Zed result.

  ```powershell
  acpx --version
  uv run --frozen python tools/probe_p11_zed_session_load.py --mode acpx-baseline <scratch-parent>
  ```

  Expected: the sanitised baseline record includes `loadSession: true`; it has no origin-A action and no claim about Zed.

- [ ] **Step 5: Run unit checks GREEN.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -q
  uv run --frozen ruff check tools/probe_p11_zed_session_load.py tests/unit/tools/test_probe_p11_zed_session_load.py
  ```

  Expected: all deterministic preparation, path-containment, and opaque-relay boundary checks pass. Commit only after authorization:

  ```powershell
  git add tools/probe_p11_zed_session_load.py tests/unit/tools/test_probe_p11_zed_session_load.py
  git commit -m "test(zed): fail closed on hermetic relay capture"
  ```

### Task 3: Add the offline evidence verifier and its tamper-resistant unit suite

**Files:**

- Create: `tools/verify_plan1119_zed_reprobe_evidence.py`
- Create: `tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py`
- Create at live execution only: `reports/plan-11-19-zed-session-load-reprobe/manifest.json`
- Create at live execution only: `reports/plan-11-19-zed-session-load-reprobe/report.md`

**Interfaces:**

- Consumes: a sanitized manifest produced by Tasks 1-2 and files only below the supplied report directory.
- Produces: process exit `0` only for a complete, sanitized, internally consistent evidence set; otherwise a safe field-level failure and nonzero exit.

- [ ] **Step 1: Write RED verifier tests with a complete valid manifest fixture.**

  Define an in-test manifest containing current commit, UTC timestamp, exact Zed/acpx identities, normal and isolated source/build identities, current-version invocation provenance, pre-launch isolation record, relay digests, sanitized capability payload, sanitized request/response classification, cleanup result, and one of the three exact findings. Require the verifier to reject every missing field and every result-rule violation.

  ```python
  def test_reachable_requires_captured_zed_request_and_empty_response(tmp_path: Path) -> None:
      manifest = valid_manifest(finding="REACHABLE")
      manifest["captured_exchange"] = None
      path = write_manifest(tmp_path, manifest)

      assert main(["--manifest", str(path)]) == 1
  ```

  Include separate negative cases for: normal source digest drift; normal-agent advertisement; isolated probe not advertising; root cleanup false; a raw credential-like value; relay digest mismatch; `UNREACHABLE` without a captured error; and `INDETERMINATE` without a named reason.

- [ ] **Step 2: Run verifier tests RED.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -q
  ```

  Expected: FAIL because the verifier entrypoint is absent.

- [ ] **Step 3: Implement strict offline validation.**

  The verifier reads only the supplied manifest and committed report-relative files, recomputes declared SHA-256 values, invokes the repository evidence sanitizer check, and rejects paths outside the report directory. It must enforce this rule verbatim in code and error output:

  ```python
  if finding == "REACHABLE":
      require(exchange and exchange["request"]["method"] == "session/load")
      require(exchange["response"].get("result") == {})
  elif finding == "UNREACHABLE":
      require(exchange and isinstance(exchange["response"].get("error"), dict))
  else:
      require(manifest["indeterminate_reason"] in ALLOWED_INDETERMINATE_REASONS)
  ```

  Verify the report says only what the manifest supports, names `INDETERMINATE` limitations, and never describes a normal-agent non-advertisement as a Zed finding.

- [ ] **Step 4: Run verifier tests GREEN.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -q
  uv run --frozen ruff check tools/verify_plan1119_zed_reprobe_evidence.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py
  ```

  Expected: valid evidence passes and every tamper/misclassification fixture fails. Commit only after authorization:

  ```powershell
  git add tools/verify_plan1119_zed_reprobe_evidence.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py
  git commit -m "test(zed): verify current-version reprobe evidence"
  ```

### Task 4: Execute the bounded real-Zed probe, sanitize the new baseline, and reconcile living documentation

**Files:**

- Create: `reports/plan-11-19-zed-session-load-reprobe/manifest.json`
- Create: `reports/plan-11-19-zed-session-load-reprobe/report.md`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Do not modify: frozen Plan 11.7 documents, `reports/p11-feat-zed-resume-session-load-reprobe.md`, or `reports/p11-feat-zed-resume-task0-evidence-custody-note.md`

**Interfaces:**

- Consumes: Task 1-3 commits, current explicit operator authorization for the live Windows evidence action, a real installed Zed, real `acpx`, a complete hermetic invocation descriptor, and passing pre-launch isolation evidence.
- Produces: a committed sanitized current-version baseline, a verifier pass, and the one-line P11-FU-10 evidence correction.

- [ ] **Step 1: Obtain live-action authorization and verify all preconditions without launching Zed.**

  Record the operator's explicit approval of this exact real-Zed launch in the review checkpoint. Then run:

  ```powershell
  git status --short --branch
  git rev-parse HEAD
  git rev-parse origin/main
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -q
  uv run --frozen python tools/probe_p11_zed_session_load.py --mode preflight <scratch-parent>
  ```

  Expected: current branch evidence is clean except reviewed Task 1-3 changes, the normal production digest is unchanged, the normal agent omits `loadSession`, only the isolated executable advertises it and answers `{}`, the current Zed hermetic invocation is recorded, and `zed_launches` remains `0`. If any condition fails, write only sanitized `INDETERMINATE` evidence with the named reason; do not launch Zed.

- [ ] **Step 2: Run the real-Zed capture once through the opaque relay.**

  On an interactive Windows desktop only, execute the approved command that the preflight generated; it must include the scratch parent and no normal-profile path. The runner launches the real installed Zed with its discovered hermetic root, routes its ACP connection through the opaque relay to the isolated executable, records bounded traffic digests, and cleans up in `finally`.

  ```powershell
  uv run --frozen python tools/probe_p11_zed_session_load.py --mode real-zed <scratch-parent>
  ```

  Do not retry as origin-A, do not use a project-authored ACP client, and do not launch the normal agent. A no-exchange result, missing dependency, failed isolation, or failed cleanup is `INDETERMINATE`; it is not permission to alter the test or run a second undisclosed experiment.

- [ ] **Step 3: Verify cleanup before staging evidence.**

  Confirm the normal workspace digest matches the pre-run value; the isolated source/build, temporary launch approval, and hermetic Zed root are all absent; and no normal Zed profile path appears in the captured report. If cleanup is not verified, do not stage an evidence artifact. Retain only the local sanitized remediation instructions required to clean the scratch root, report `INDETERMINATE / CLEANUP_UNVERIFIED`, and stop for operator direction.

- [ ] **Step 4: Generate and verify committed-safe evidence.**

  Create the report directory only after successful cleanup. The manifest must contain the UTC timestamp, execution commit, Zed/acpx versions and executable identities, normal/isolated source/build identities, invocation provenance, all four isolation predicates, temporary-advertisement proof, capability payload, opaque-relay digests, sanitized exchange or bounded no-exchange observation, finding/reason, and cleanup result.

  ```powershell
  uv run --frozen python tools/verify_plan1119_zed_reprobe_evidence.py --manifest reports/plan-11-19-zed-session-load-reprobe/manifest.json
  git diff --check
  ```

  Expected: verification passes only for a sanitized, complete, correctly classified result. Preserve the literal sanitized `session/load` request/response when present; otherwise state exactly why the observation is bounded.

- [ ] **Step 5: Correct the closed P11-FU-10 evidence reference and run document hygiene.**

  Change only the evidence cell on the `P11-FU-10` index row from `Draft PR #158` to `PR #158 (merge 7d4e466)`. Do not alter status, priority, ownership, or frozen history. Run:

  ```powershell
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  git diff --check
  ```

  Expected: living pool hygiene passes and the diff contains the evidence report plus exactly the approved one-line backlog correction outside implementation/tool/test files.

- [ ] **Step 6: Run final Windows and WSL fitness gates, then commit only with authorization.**

  On Windows:

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py tests/unit/docs/test_open_work_pool_hygiene.py -q
  uv run --frozen ruff check .
  ```

  In the native WSL ext4 clone, run the same non-live Python tests and Ruff. Do not substitute `/mnt/d`, rerun the real-Zed action, or claim the live tier passed on Linux. With all gates green and explicit commit authorization:

  ```powershell
  git add tools/probe_p11_zed_session_load.py tools/verify_plan1119_zed_reprobe_evidence.py tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py reports/plan-11-19-zed-session-load-reprobe docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md
  git commit -m "test(zed): pin current session-load reprobe evidence"
  ```

## Definition of Done and Evidence Map

| Claim | Required committed evidence |
|---|---|
| Normal operation cannot reach the temporary advertisement | Manifest's normal initialize payload, allowlisted isolated patch record, normal before/after source digests, and cleanup proof |
| The probe is a genuine real-Zed observation | Installed Zed identity, current-version hermetic invocation provenance, opaque relay digests, and captured/sanitized Zed-side exchange or named limitation |
| The temporary server conforms to the narrow probe contract | `acpx` identity/baseline payload plus manifest proof of top-level `loadSession: true` and empty `session/load` result |
| Result does not overclaim | Offline verifier pass enforcing `REACHABLE`/`UNREACHABLE`/`INDETERMINATE` rules |
| No sensitive or ambient state entered Git | Sanitizer proof, report-relative file digest validation, hermetic-root cleanup proof, and reviewer inspection before staging |
| P11-FU-10's closure reference is current | One-line pool correction to `PR #158 (merge 7d4e466)` plus hygiene-test pass |

## Plan Self-Review

- The frozen brief's question, isolated probe shape, four normal-operation isolation predicates, opaque-relay requirement, real-`acpx` baseline, committed evidence contract, and exact verdict discipline each map to Tasks 1-4.
- Origin-A, historical-1.13.1, production session/resume implementation, render claims, and Gateway/provider work are explicit exceptions with named owners.
- The plan contains no automatic live launch: Task 4 requires a fresh recorded operator authorization after deterministic gates pass.
- No existing report or frozen Plan 11.7 artifact is rewritten; the only unrelated living-document modification is the approved one-line P11-FU-10 evidence correction.
