# EVIDENCE-HANDOFF-FEAT-EVIDENCE-COLLECTOR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to execute this plan task by task.

**Goal:** Implement the approved evidence collector as one explicit, staged
`tools/evidence_gather.py` interface backed by portable scenario, observation,
classification, and bundle contracts, with the existing public redaction gate invoked
only by the separately selected final stage.

**Architecture:** `evidence_handoff.collector` owns portable, deterministic data
contracts and reducers. `tools/evidence_gather.py` is the sole executable entry point
and wires non-entry-point host adapters from `tools/evidence_gather_support`.
Dependency flow is `tools -> evidence_handoff.collector`; the portable package never
imports `tools`, `optimus`, or `optimus_gateway`. Only the explicit `redact` subcommand
crosses into the gate through its public `evidence_handoff.redaction` surface and the
canonical Optimus host adapter. `redact` re-resolves and reauthorizes the current launch
in memory against an existing durable approval; it never persists or reloads an
`AuthorizedLaunch`. Collection outcome and redaction disposition remain independent.

**Tech Stack:** Python 3.14, standard-library dataclasses/enums/TOML/JSON/AST/hash/
filesystem/subprocess primitives, setuptools/uv, pytest/pytest-asyncio/pytest-cov,
coverage.py, Ruff, detect-secrets, real Windows DWM and Zed 1.13.1, real filesystem
and OS credential-store paths, and the independently authored `acpx` ACP client.

**Frozen design baseline:** Commit
`28af3b5cf51900c07490c4cbb6841248b22bd568`, file
`docs/superpowers/specs/evidence-handoff-evidence-collector-design.md`, SHA-256
`145607ce3f86e70c26b2ad95e3b5af4981efdb87b1b0975fbc9730bd78091a86`.
The implementation worker must hash the committed blob, never the working-tree file.
Any mismatch blocks pickup.

---

## Global Constraints

- The frozen collector design is the contract. Do not edit it during implementation.
  If execution reveals a contradiction or missing architectural decision, stop and
  request a design amendment.
- This work is sequenced after `EVIDENCE-HANDOFF-FEAT-REDACTION-GATE`. Task 0 must
  prove that the approved gate implementation is merged and that its public contract
  module is importable before collector implementation begins. Do not create temporary
  collector-owned gate models or compatibility aliases.
- The current authority set is
  `docs/Optimus-Cost-Agent-Architecture-v2.16.pdf`,
  `docs/Optimus-Cost-Agent-LLD-v2.39.pdf`, and
  `docs/Optimus-Cost-Agent-Test-Strategy-v1.5.pdf`. Recheck their repository versions
  at pickup and stop on conflict. They require at least 80% aggregate production
  coverage, secret redaction before export, real named dependencies for live claims,
  and independently authored `acpx` for ACP protocol evidence.
- Reference this work only as
  `EVIDENCE-HANDOFF-FEAT-EVIDENCE-COLLECTOR`. Do not assign, reserve, or speculate
  about a scheduling number. Package, module, setting, command, schema, artifact, test,
  and document names remain descriptive, brand-free, and scheduling-number-free.
- `tools/evidence_gather.py` is the sole feature entry point. There is no console
  script, package `__main__`, wrapper executable, additional command module, `all`,
  `run`, or implicit collection-plus-redaction path.
- `tools/evidence_gather_support` modules have no `if __name__ == "__main__"` block,
  console-script registration, or direct executable semantics. Sibling imports within
  that package are allowed. Outside that package, only `tools/evidence_gather.py` may
  import it. Tests exercise support behavior through the entry-point module or through
  portable package contracts; they do not import support modules directly.
- Import direction is fixed:

  ```text
  tools/evidence_gather.py
      -> tools/evidence_gather_support.*
      -> evidence_handoff.collector.*

  tools/evidence_gather_support.* -> evidence_handoff.collector.*
  tools/evidence_gather_support.redaction
      -> evidence_handoff.redaction.models       gate-owned public models only
      -> evidence_handoff.redaction              gate-owned public callables only
      -> optimus.acp.evidence_redaction_adapter  canonical host wiring only
      -> optimus.acp launch/trusted-path APIs     redact-time authorization only

  evidence_handoff.collector -X-> tools
  evidence_handoff.collector -X-> optimus
  evidence_handoff.collector -X-> optimus_gateway
  evidence_handoff.collector -X-> optimus_security
  ```

- Host implementations may be supplied behind portable protocols. Concrete host types
  may not appear in portable dataclass fields, function signatures, protocol
  definitions, serialized contracts, or annotations. Portable code must not
  introspect or retain a concrete host type.
- `evidence_handoff.collector` is standard-library-only. It does not consume
  `optimus_security`. The `evidence_handoff.redaction -> optimus_security` dependency
  belongs to the gate and does not authorize a collector import or a second rule
  engine.
- The collector may import gate-owned public names exported by
  `evidence_handoff.redaction.models` when required by the public request/result
  graph. This includes `ArtifactKind`, `Disposition`, `RedactionRuntimeInputs`,
  `ScreenshotApproval`, `RedactionRequest`, and `RedactionGateResult`; it is not an
  exact six-name allowlist. It may also call the gate's public callable. It does not
  import policy constants, sanitizer helpers, sensitive-value inventory types,
  entropy thresholds, token grammars, preservation rules, or any private/internal
  symbol.
- `evidence_handoff.redaction.models` is the single authority for every gate-owned
  public model. If the gate implementation renames or reshapes a public model used by
  the collector, the contract-changing task must sweep this plan's named call sites,
  the collector implementation, fixtures, and contract tests in the same changeset.
  Do not preserve a compatibility alias, stringly typed fallback, or silent stale
  binding.
- `EvidenceRedactionHostContext` is a host-only input owned by
  `optimus.acp.evidence_redaction_adapter`; `AuthorizedLaunch` is an Optimus host type.
  They may exist only in the `redact` host call path. Neither may enter a portable
  signature, stage document, artifact, log, report, checkpoint, or serialized cache.
- `redact` always resolves and authorizes a fresh current launch from the explicit
  workspace root and the existing durable approval. It does not accept a one-shot
  approval ID and does not reuse, serialize, persist, or reload authorization state
  from `collect`. Configuration drift therefore fails the durable approval check at
  redact time rather than reusing stale credentials.
- Scenario files are untrusted declarative data. They select only allowlisted IDs and
  bounded typed parameters. They cannot specify imports, Python expressions, shell
  fragments, executable hooks, templates with evaluation semantics, environment
  expansion, arbitrary argument vectors, or package entry points.
- A model-aware adapter requires an explicit `model` runtime binding. Source code,
  shipped scenarios, tests intended as product fixtures, command defaults, and
  configuration contain no model literal or model fallback. Missing, empty, unknown,
  duplicate, or multiply supplied bindings fail before mutation or process launch.
- Every destination-bearing command requires an explicit absolute path. Report target,
  capture root, provisional-result path, staging root, quarantine root, sanitized root,
  and approval locator have no defaults. Nothing derives a destination from a scenario
  ID, model, timestamp, current directory, user profile, or repository root.
- `validate`, `prepare`, `check`, `collect`, `classify`, `redact`, and `inspect` are
  separate resumable stages. Only `redact` invokes the gate. `collect` and `classify`
  always stop with private, non-promotable outputs.
- Raw evidence remains under the explicit approved private capture root until the
  separately invoked gate handles it. Raw bodies, absolute source/user-profile/Zed-log
  paths, environment mappings, secret-inventory facts, and raw exception text never
  enter observations, stage metadata, provisional results, reports, or diagnostics.
- Stage metadata and output publication are atomic and digest-bound. A later stage
  verifies the scenario digest, run manifest, preceding-stage digest, and declared
  artifacts. It never repairs, silently regenerates, or trusts a partial stage.
- Process execution uses a fixed adapter-owned argument vector and `shell=False`.
  External output is untrusted data and is never executed, evaluated, imported, or
  promoted to scenario policy.
- Outcome values are exactly `rendered_stable`, `rendered_then_crashed`,
  `client_crashed`, and `indeterminate`. Required integrity/correlation failure outranks
  all determinate outcomes; a stable result requires the complete declared interval;
  absence is never converted into a positive claim.
- A DWM screenshot proves only physical-bounds capture. It never creates a semantic
  render claim. Semantic render evidence must be an explicit, digest-bound,
  scenario-specific observation. That observation is evidence input, not human
  screenshot approval, an authorization record, a security control, or the separate
  approval-record feature.
- Automated Zed prompt injection is structurally absent. No prompt-injection adapter
  ID, portable enum member, scenario capability, dormant implementation, feature flag,
  or environment switch is permitted. The three named investigations live only under
  `tests/investigation/evidence/`, are invoked by pytest, and never enter the host
  registry or support package.
- Every task that first touches a real dependency proves it in that task. Unit fakes
  cannot justify a live claim. The final task may index and audit evidence already
  produced, but may not be the first exercise of `acpx`, Zed, DWM, the canonical gate
  adapter, the real gate/filesystem, UIA/SendInput, `zed://`, or hermetic user-data
  instances.
- Follow TDD for every behavior: add the failing test, run it and record the expected
  failure, implement the minimum behavior, rerun green, then refactor without changing
  the contract.
- Before any task commit, run that task's narrow tests,
  `uv run --frozen ruff check .`, and `git diff --check`. A commit is allowed only
  after the operator relays the task evidence to the reviewer, the reviewer approves
  it, and the operator separately authorizes the commit. Stop after each approved
  commit.
- Never push, open a PR, merge, delete branches, or rewrite history under this plan.
- The reviewer-owned ignored checkpoint log is
  `docs/superpowers/reviews/evidence-handoff-evidence-collector-review-checkpoints.md`.
  Read its `Current State` first at every pickup, verify it against Git and on-disk
  evidence, and never stage it.

## Frozen Portable Contracts

Private helpers may be split differently, but these portable types and directions are
fixed. Use frozen, slotted dataclasses and `StrEnum`; serialize tuples as JSON arrays
and enums as their values.

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, Sequence


class BindingKind(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ABSOLUTE_PATH = "absolute_path"


class Outcome(StrEnum):
    RENDERED_STABLE = "rendered_stable"
    RENDERED_THEN_CRASHED = "rendered_then_crashed"
    CLIENT_CRASHED = "client_crashed"
    INDETERMINATE = "indeterminate"


class ClaimKind(StrEnum):
    COMPLETION_OBSERVED = "completion_observed"
    RENDER_OBSERVED = "render_observed"
    CLIENT_ALIVE = "client_alive"
    OBSERVATION_WINDOW_COMPLETE = "observation_window_complete"
    CLIENT_CRASH_OBSERVED = "client_crash_observed"
    INTEGRITY_VALID = "integrity_valid"


@dataclass(frozen=True, slots=True)
class RequiredBinding:
    name: str
    kind: BindingKind
    required: bool
    min_length: int | None = None
    max_length: int | None = None


@dataclass(frozen=True, slots=True)
class AdapterParameter:
    name: str
    kind: BindingKind
    value: str | int | bool


@dataclass(frozen=True, slots=True)
class AdapterSpec:
    adapter_id: str
    contract_version: str
    parameters: tuple[AdapterParameter, ...]


@dataclass(frozen=True, slots=True)
class Scenario:
    schema: str
    scenario_id: str
    required_bindings: tuple[RequiredBinding, ...]
    client: AdapterSpec
    fixture: AdapterSpec
    preconditions: tuple[AdapterSpec, ...]
    collection: tuple[AdapterSpec, ...]
    detection: tuple[AdapterSpec, ...]
    required_evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunContext:
    schema: str
    scenario_id: str
    run_id: str
    scenario_sha256: str
    capture_root: Path
    monotonic_origin_ns: int


@dataclass(frozen=True, slots=True)
class CapturedArtifact:
    role: str
    media_type: str
    relative_locator: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class Observation:
    schema: str
    scenario_id: str
    run_id: str
    collector_id: str
    sequence: int
    monotonic_offset_ns: int
    observed_at: str
    observation_kind: str
    correlation: tuple[tuple[str, str], ...]
    artifact_role: str | None
    artifact_sha256: str | None
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class CollectionBatch:
    collector_id: str
    contract_version: str
    observations: tuple[Observation, ...]
    artifacts: tuple[CapturedArtifact, ...]


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    claim_kind: ClaimKind
    scenario_id: str
    run_id: str
    detector_id: str
    contract_version: str
    evidence_sha256: tuple[str, ...]
    starts_at_ns: int
    ends_at_ns: int
    reason_code: str


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    schema: str
    scenario_id: str
    run_id: str
    outcome: Outcome
    claims: tuple[EvidenceClaim, ...]
    reason_codes: tuple[str, ...]
    raw_bundle_sha256: str


class Collector(Protocol):
    collector_id: str
    contract_version: str

    def collect(self, context: RunContext) -> CollectionBatch: ...


class Detector(Protocol):
    detector_id: str
    contract_version: str

    def detect(
        self,
        *,
        context: RunContext,
        observations: Sequence[Observation],
        artifacts: Sequence[CapturedArtifact],
    ) -> tuple[EvidenceClaim, ...]: ...
```

Host objects implement `Collector` or another separately named portable capability
protocol. Portable code sees only the protocol shape above; it never imports, annotates,
serializes, introspects, or retains the concrete host class.

The first shipped schema identifiers are:

- `evidence-scenario-v1`
- `evidence-run-v1`
- `evidence-observation-v1`
- `evidence-raw-bundle-v1`
- `evidence-classification-v1`
- `evidence-render-observation-v1`
- `evidence-report-v1`

`CapturedArtifact` deliberately uses a portable media type and role rather than
duplicating gate `ArtifactKind`. Task 8 owns one exhaustive, tested conversion into the
gate authority's enum.

## CLI Contract

The parser exposes exactly these subcommands:

```text
validate  --scenario ABSOLUTE_PATH [--bind NAME=VALUE ...]
prepare   --scenario ABSOLUTE_PATH --capture-root ABSOLUTE_PATH [--bind NAME=VALUE ...]
check     --scenario ABSOLUTE_PATH --capture-root ABSOLUTE_PATH
collect   --scenario ABSOLUTE_PATH --capture-root ABSOLUTE_PATH
classify  --scenario ABSOLUTE_PATH --capture-root ABSOLUTE_PATH
          --result ABSOLUTE_PATH
          [--render-observation ABSOLUTE_PATH]
redact    --scenario ABSOLUTE_PATH --workspace-root ABSOLUTE_PATH
          --user-data-root ABSOLUTE_PATH [--user-data-root ABSOLUTE_PATH ...]
          [--forbidden-root ABSOLUTE_PATH ...]
          --capture-root ABSOLUTE_PATH
          --result ABSOLUTE_PATH --staging-root ABSOLUTE_PATH
          --quarantine-root ABSOLUTE_PATH --sanitized-root ABSOLUTE_PATH
          --report ABSOLUTE_PATH [--screenshot-approval ABSOLUTE_PATH]
inspect   --report ABSOLUTE_PATH
```

The CLI may add bounded, non-destination options required by an approved adapter, but
must not add a destination default, model default, general command passthrough,
environment fallback, implicit redaction, or another executable route.

`--render-observation` is an optional explicit path to a run-local,
`evidence-render-observation-v1` document. It names the scenario/run, the positive
scenario-specific detector ID, bounded observation time, supporting artifact digest,
and assertion provenance. The classifier verifies its digest and correlation. It is
not generated from screenshot success, does not approve a screenshot, and does not
replace the redaction gate's independent approval.

## Redact-Time Host Context

`redact` uses reauthorization, not a carried credential reference. The subcommand
captures current launch inputs once, resolves the current candidate with the canonical
public launch APIs, and authorizes it against the real keyring-backed durable approval.
It generates a fresh in-memory launch session ID and calls
`authorize_launch(..., approval_id=None, ...)`; the absent approval ID deliberately
selects durable authorization and prevents one-shot consumption.

The host-only call path uses these public types and functions:

```python
from evidence_handoff.redaction.models import (
    ArtifactKind,
    Disposition,
    RedactionGateResult,
    RedactionRequest,
    RedactionRuntimeInputs,
    ScreenshotApproval,
)
from optimus.acp.evidence_redaction_adapter import (
    EvidenceRedactionHostContext,
    build_redaction_runtime_inputs,
)
from optimus.acp.launch_approvals import KeyringApprovalStore
from optimus.acp.launch_gate import (
    AuthorizedLaunch,
    authorize_launch,
    resolve_launch_candidate,
)
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.operator_paths import resolve_authorized_operator_paths
from optimus.acp.trusted_paths import (
    resolve_trusted_operator_roots,
    resolve_workspace_identity,
)
```

The implementation must not import private helpers from `launch_approval_cli.py`.
`tools.evidence_gather_support.redaction` composes the same public primitives as the
canonical launch path:

1. resolve trusted operator roots from OS APIs;
2. capture `LaunchEnvironmentSnapshot` exactly once;
3. resolve authorized operator paths from `--workspace-root` and that snapshot;
4. construct the real `KeyringApprovalStore` without writing it;
5. resolve workspace identity and the current `LaunchCandidate`;
6. call `authorize_launch` with `approval_id=None` and a fresh session ID;
7. build the eight-field `EvidenceRedactionHostContext`;
8. immediately convert it through `build_redaction_runtime_inputs`; and
9. retain neither the host context nor `AuthorizedLaunch` after gate requests finish.

Every host-context field has exactly one source:

| `EvidenceRedactionHostContext` field | Source and validation |
|---|---|
| `authorized_launch` | Fresh in-memory result of current candidate resolution plus `authorize_launch(..., approval_id=None, ...)` against the existing durable keyring approval. Never serialized. |
| `operator_profile_root` | Authenticated OS profile APIs: `FOLDERID_Profile` on Windows; `pwd.getpwuid(os.getuid()).pw_dir` on POSIX. Failure is fatal; inherited profile environment variables are not accepted. |
| `user_data_roots` | One or more explicit `--user-data-root` values. Each must be absolute, canonical, non-overlapping with custody destinations, and consistent with the selected scenario/client precondition. |
| `temporary_capture_root` | Explicit `--capture-root`, after custody, containment, and overlap validation. |
| `staging_root` | Explicit `--staging-root`, after custody and overlap validation. |
| `quarantine_root` | Explicit `--quarantine-root`, after custody and overlap validation. |
| `operator_identity_values` | Non-empty values from authenticated OS identity APIs only: account name and host name on every platform, plus Windows user principal name when available. They are passed directly in memory and never printed or serialized. |
| `forbidden_persistence_roots` | Canonical tuple containing `--workspace-root` unconditionally plus every repeatable `--forbidden-root`. Known cloud-sync segments are rejected independently, so the control cannot become an empty tuple or be disabled by omitting optional arguments. |

The host support module owns small OS adapters for profile and identity lookup so their
real and fake forms remain outside the portable package. Unit tests inject fakes;
Task 8's live test uses the real OS APIs and records only value-free source classes and
counts.

`--sanitized-root` maps directly to `RedactionRequest.destination_root` for every
request. It is not a field of `EvidenceRedactionHostContext` or
`RedactionRuntimeInputs`. The explicit root is validated once, then supplied unchanged
to each request. `--screenshot-approval`, when present, is parsed into the gate-owned
public `ScreenshotApproval`; dispositions are compared as `Disposition` enum members,
never raw strings.

## File and Responsibility Map

### Portable production files to create

- `src/evidence_handoff/collector/__init__.py`: deliberate public exports only.
- `src/evidence_handoff/collector/models.py`: frozen scenario, binding, observation,
  claim, artifact, run, classification, and outcome models.
- `src/evidence_handoff/collector/scenarios.py`: strict TOML/JSON parse, binding
  resolution, adapter-ID validation inputs, and deterministic scenario digest.
- `src/evidence_handoff/collector/protocols.py`: collector, detector, clock, and
  artifact-store protocols without host types.
- `src/evidence_handoff/collector/pipeline.py`: ordered stage transitions, digest
  verification, composition, and atomic stage metadata.
- `src/evidence_handoff/collector/classification.py`: deterministic detector reducers
  and exact four-value precedence.
- `src/evidence_handoff/collector/bundles.py`: deterministic run manifest, raw bundle,
  render observation, provisional result, and safe report schemas.

### Host production files to create

- `tools/evidence_gather.py`: sole parser, dispatch entry point, exit-code semantics,
  host registry construction, public gate invocation, and report/inspect commands.
- `tools/evidence_gather_support/__init__.py`: non-executable internal package marker;
  no public re-export surface.
- `tools/evidence_gather_support/common.py`: stable host errors, absolute-path and
  custody checks, atomic file helpers, process identity, and bounded clocks.
- `tools/evidence_gather_support/registry.py`: explicit allowlists for client, fixture,
  precondition, collector, and detector IDs; no prompt-injection ID.
- `tools/evidence_gather_support/fixtures.py`: idempotent fixture preparation and
  precondition implementations.
- `tools/evidence_gather_support/acp.py`: real `acpx`/agent process collection,
  argument-vector construction, correlation, and bounded process custody.
- `tools/evidence_gather_support/ndjson.py`: byte-offset/file-identity suffix
  extraction and exact completion-event normalization.
- `tools/evidence_gather_support/zed_logs.py`: pre-run Zed-log snapshot, bounded watch,
  new/changed artifact capture, and process correlation.
- `tools/evidence_gather_support/windows_capture.py`: top-level window resolution, DWM
  physical bounds, DPI/process identity, and bounded image capture.
- `tools/evidence_gather_support/redaction.py`: redact-time durable reauthorization,
  authenticated OS profile/identity resolution, complete host-context assembly,
  exhaustive artifact-kind mapping, canonical runtime adapter call, public gate
  requests/results, and eligibility.
- `tools/evidence_gather_support/reports.py`: safe deterministic report rendering and
  body-free inspection.

### Test and fixture files to create

- `tests/fixtures/evidence/scenarios/zed-session.toml`: declarative scenario with a
  required `model` binding and no assigned model value.
- `tests/fixtures/evidence/scenarios/zed-session.json`: deterministic equivalent used
  to prove TOML/JSON parity.
- `tests/unit/evidence/test_collector_models.py`
- `tests/unit/evidence/test_collector_scenarios.py`
- `tests/unit/evidence/test_collector_pipeline.py`
- `tests/unit/evidence/test_collector_classification.py`
- `tests/unit/evidence/test_collector_boundaries.py`
- `tests/unit/tools/test_evidence_gather.py`
- `tests/integration/evidence/test_collector_filesystem.py`
- `tests/integration/evidence/test_collector_acpx_live.py`
- `tests/integration/evidence/test_collector_zed_logs_live.py`
- `tests/integration/evidence/test_collector_dwm_live.py`
- `tests/integration/evidence/test_collector_redaction_live.py`
- `tests/e2e/evidence/test_collector_staged_live.py`
- `tests/investigation/evidence/test_zed_uia_sendinput_live.py`
- `tests/investigation/evidence/test_zed_scheme_live.py`
- `tests/investigation/evidence/test_zed_user_data_live.py`

### Existing files to modify

- `pyproject.toml`: add the collector live markers, keep them out of the default test
  selection, and include `src/evidence_handoff` in aggregate coverage after the gate
  package exists.
- `tests/unit/evidence/test_import_boundaries.py`: extend the gate-owned package scan
  with collector-specific `optimus_security` rejection and dynamic/relative escape
  cases.
- `tests/unit/evidence/test_naming_boundaries.py`: include collector package, entry
  point, support package, scenarios, schemas, and artifacts.
- `docs/superpowers/plans/evidence-handoff-open-work-pool.md`: update the one live
  product row only when execution is actually picked up and again when evidence
  justifies closure.
- Current-state repository documents identified by Task 13's freshness audit: change
  only statements made true or false by the implementation.

The plan document itself and its two hygiene registrations land together before
implementation and are not execution-task files.

## Real-Dependency Introduction Map

| Real dependency | First task | Required evidence produced in that task |
|---|---|---|
| Real filesystem and atomic replace | Task 2 | Portable integration over real files, partial writes, identity changes, resume, and Windows plus alternate-OS paths. |
| Independent `acpx` and real agent process | Task 5 | Correlated real `server.py:process_request:exit` event driven through `acpx`; no project ACP client. |
| Real Zed 1.13.1 logs | Task 6 | Pre-run exclusion and new/changed `%LOCALAPPDATA%\Zed\logs\` evidence from a real instance. |
| Real Windows DWM/client window | Task 7 | Physical bounds, DPI, process/window identity, and captured real client window. |
| Canonical Optimus runtime adapter and OS credential store | Task 8 | Real resolver/credential-store path with no credential mutation and no value crossing into evidence. |
| Public gate and real staging/promotion filesystem | Task 8 | Real public gate dispositions, promotion behavior, and raw-output canary scan. |
| UIA/SendInput against Zed 1.13.1 | Task 10 | Same-task real probe evidence and bounded supported/unsupported/indeterminate result. |
| Real `zed://` scheme | Task 11 | Same-task scheme invocation and observed Zed behavior. |
| Real hermetic `--user-data-dir` instances | Task 12 | Same-task instance isolation and custody evidence. |

Task 9 combines dependencies already proven in Tasks 5 through 8. Task 13 only
audits/indexes prior evidence and cannot repair a missing introducing-task proof.

## Task 0: Freeze inputs, prove sequencing, and mark execution pickup

**Files:** Read the frozen collector design, the merged gate implementation and tests,
the three authoritative PDFs, `pyproject.toml`, the product pool, and the reviewer
checkpoint. Modify only the product pool after all pickup gates pass.

- [ ] **Step 1: Verify Git topology and the frozen collector blob**

  ```bash
  git status --short --branch
  git merge-base --is-ancestor 28af3b5cf51900c07490c4cbb6841248b22bd568 HEAD
  git show 28af3b5cf51900c07490c4cbb6841248b22bd568:docs/superpowers/specs/evidence-handoff-evidence-collector-design.md | sha256sum
  ```

  Expected: clean assigned worktree, ancestor check exits zero, and the digest is
  exactly `145607ce3f86e70c26b2ad95e3b5af4981efdb87b1b0975fbc9730bd78091a86`.
  A mismatch blocks execution.

- [ ] **Step 2: Prove the gate implementation is merged and authoritative**

  ```bash
  uv run --frozen python - <<'PY'
  from evidence_handoff.redaction.models import (
      ArtifactKind,
      Disposition,
      RedactionGateResult,
      RedactionRequest,
      RedactionRuntimeInputs,
      ScreenshotApproval,
  )
  from optimus.acp.evidence_redaction_adapter import (
      EvidenceRedactionHostContext,
      build_redaction_runtime_inputs,
  )
  print(
      ArtifactKind.__module__,
      Disposition.__module__,
      RedactionRuntimeInputs.__module__,
      ScreenshotApproval.__module__,
      RedactionRequest.__module__,
      RedactionGateResult.__module__,
      EvidenceRedactionHostContext.__module__,
      build_redaction_runtime_inputs.__module__,
  )
  PY
  uv run --frozen pytest tests/unit/evidence tests/integration/evidence -q
  ```

  Expected: the complete public model graph needed by the collector resolves from
  `evidence_handoff.redaction.models`; the host context and canonical adapter resolve
  from `optimus.acp.evidence_redaction_adapter`; and the gate suites pass. Missing or
  renamed contracts require the same-task sweep rule. An unimplemented gate blocks
  the collector.

- [ ] **Step 3: Recheck authorities and baseline gates**

  ```bash
  git status --short
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  uv run --frozen ruff check .
  ```

  Read the current authority PDFs and the checkpoint's `Current State`. Expected:
  clean baseline and no authority conflict.

- [ ] **Step 4: Record actual pickup only after reviewer and operator approval**

  In the collector row of
  `docs/superpowers/plans/evidence-handoff-open-work-pool.md`, change only the live
  state cell to `Promoted`, add the actual pickup date, and retain the implementation
  plan link. This is the pool's already-defined custody term from its **How to use**
  section, not a redaction-gate disposition. Do not add a scheduling number or edit
  the ratified scope cell.

- [ ] **Step 5: Verify and hand off Task 0**

  ```bash
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  uv run --frozen ruff check .
  git diff --check
  git diff -- docs/superpowers/plans/evidence-handoff-open-work-pool.md
  ```

  Expected: only the product pool live-state cell changes. Relay the blob digest,
  gate contract imports, gate test result, authority check, pool diff, Ruff result,
  and unrun gates. Stop for reviewer approval and separate commit authorization.

## Task 1: Establish portable models, strict scenarios, and mechanical boundaries

**Files:** Create `src/evidence_handoff/collector/__init__.py`, `models.py`,
`scenarios.py`, the two scenario fixtures, `tests/unit/evidence/test_collector_models.py`,
`tests/unit/evidence/test_collector_scenarios.py`,
`tests/unit/evidence/test_collector_boundaries.py`; modify the existing evidence import
and naming boundary tests.

- [ ] **Step 1: Write failing model and scenario tests**

  Cover frozen/slot behavior, exact enum values, canonical serialization, TOML/JSON
  parity, unknown fields, duplicate keys, unknown schema, unsafe scenario ID, binding
  type/bounds, missing/empty/duplicate model binding, and the complete non-executable
  input rejection list.

  ```bash
  uv run --frozen pytest \
    tests/unit/evidence/test_collector_models.py \
    tests/unit/evidence/test_collector_scenarios.py -q
  ```

  Expected RED: the collector package does not exist.

- [ ] **Step 2: Implement the minimum portable scenario surface**

  Implement the frozen contracts, strict recursive key allowlists, canonical TOML/JSON
  normalization, explicit binding resolution, and SHA-256 over canonical scenario
  JSON. Reject ambiguous TOML types rather than coercing them.

  Public functions:

  ```python
  def load_scenario(path: Path) -> Scenario: ...
  def resolve_bindings(
      scenario: Scenario,
      supplied: Sequence[str],
  ) -> tuple[AdapterParameter, ...]: ...
  def scenario_sha256(
      scenario: Scenario,
      bindings: Sequence[AdapterParameter],
  ) -> str: ...
  ```

- [ ] **Step 3: Add import, naming, model-literal, and prompt-injection absence tests**

  The AST test scans all `src/evidence_handoff` modules for forbidden roots and
  dynamic-import/relative escape hatches, then applies the stricter
  `optimus_security` prohibition to `evidence_handoff.collector`. Scan new product
  surfaces for retired names, scheduling coupling, model defaults/literals, and any
  prompt-injection capability or adapter ID.

  ```bash
  uv run --frozen pytest \
    tests/unit/evidence/test_import_boundaries.py \
    tests/unit/evidence/test_naming_boundaries.py \
    tests/unit/evidence/test_collector_boundaries.py -q
  ```

  Expected GREEN.

- [ ] **Step 4: Prove isolated portability**

  ```bash
  uv run --frozen python -I -c \
    "from evidence_handoff.collector.scenarios import load_scenario; print(load_scenario.__module__)"
  uv run --frozen pytest \
    tests/unit/evidence/test_collector_models.py \
    tests/unit/evidence/test_collector_scenarios.py -q
  uv run --frozen ruff check .
  git diff --check
  ```

  Expected: isolated import succeeds without importing a forbidden root. Relay test,
  AST scan, isolated-import, Ruff, and unrun evidence. Stop for approval and separate
  commit authorization.

## Task 2: Build portable protocols, atomic pipeline, and real-filesystem bundles

**Files:** Create `protocols.py`, `pipeline.py`, `bundles.py`,
`tests/unit/evidence/test_collector_pipeline.py`, and
`tests/integration/evidence/test_collector_filesystem.py`.

- [ ] **Step 1: Write failing protocol, composition, and filesystem tests**

  Unit cases cover deterministic collector order, independent observation sort,
  duplicate sequence, foreign run ID, digest mismatch, clock regression, collision,
  stable reason codes, body-free errors, and concrete-host-type absence. Integration
  cases use real files for fixture idempotence, immutable mismatch, partial stage
  metadata, atomic replacement, file identity change, resume, explicit targets, path
  overlap, and forbidden custody roots.

  ```bash
  uv run --frozen pytest \
    tests/unit/evidence/test_collector_pipeline.py \
    tests/integration/evidence/test_collector_filesystem.py -q
  ```

  Expected RED: protocol/pipeline/bundle modules are missing.

- [ ] **Step 2: Implement deterministic stage and bundle contracts**

  Implement:

  ```python
  def compose_collection(
      context: RunContext,
      collectors: Sequence[Collector],
  ) -> tuple[CollectionBatch, ...]: ...

  def write_run_manifest(
      *,
      capture_root: Path,
      scenario: Scenario,
      bindings: Sequence[AdapterParameter],
  ) -> RunContext: ...

  def write_raw_bundle(
      *,
      context: RunContext,
      batches: Sequence[CollectionBatch],
  ) -> Path: ...

  def load_verified_raw_bundle(
      *,
      context: RunContext,
      bundle_path: Path,
  ) -> tuple[CollectionBatch, ...]: ...
  ```

  All locators stored in portable documents are validated relative locators. Atomic
  writes use a sibling temporary file, flush/fsync where supported, and one replace;
  no temporary file can be parsed as a completed stage.

- [ ] **Step 3: Run same-task real-filesystem evidence on Windows**

  ```bash
  uv run --frozen pytest \
    tests/integration/evidence/test_collector_filesystem.py -q
  ```

  Expected: real filesystem cases pass, including partial write, replacement, resume,
  and overlap rejection.

- [ ] **Step 4: Run the portable filesystem suite on the alternate OS**

  From WSL2 Ubuntu at the repository `/mnt/<drive>/...` path:

  ```bash
  uv sync --frozen --extra dev
  uv run --frozen pytest \
    tests/unit/evidence/test_collector_models.py \
    tests/unit/evidence/test_collector_scenarios.py \
    tests/unit/evidence/test_collector_pipeline.py \
    tests/integration/evidence/test_collector_filesystem.py -q
  ```

  Expected: same portable behavior passes. Windows paths in fixtures remain data; no
  DWM or Zed live claim is made here.

- [ ] **Step 5: Verify and hand off Task 2**

  ```bash
  uv run --frozen ruff check .
  git diff --check
  ```

  Relay Windows and alternate-OS outputs, filesystem identity/atomicity evidence, Ruff,
  and unrun gates. Stop for approval and separate commit authorization.

## Task 3: Implement evidence claims and fail-closed four-value classification

**Files:** Create `classification.py` and
`tests/unit/evidence/test_collector_classification.py`; extend `bundles.py` and its
pipeline tests for render observations and provisional results.

- [ ] **Step 1: Write the complete failing decision table**

  Parameterize every determinate outcome, precedence edge, equal/boundary timestamp,
  missing completion, missing render, crash before/after render, incomplete interval,
  collector failure, timeout, foreign run, ambiguous multi-instance evidence,
  contradictory claims, bad digest, duplicate sequence, clock regression, and
  screenshot-without-render-observation.

  ```bash
  uv run --frozen pytest \
    tests/unit/evidence/test_collector_classification.py -q
  ```

  Expected RED: the classifier is absent.

- [ ] **Step 2: Implement detector validation and the exact reducer**

  ```python
  def validate_claims(
      *,
      context: RunContext,
      claims: Sequence[EvidenceClaim],
      required_collectors: Sequence[str],
  ) -> tuple[str, ...]: ...

  def classify(
      *,
      context: RunContext,
      raw_bundle_sha256: str,
      claims: Sequence[EvidenceClaim],
      required_collectors: Sequence[str],
      stability_interval_ns: int,
  ) -> ClassificationResult: ...
  ```

  Apply precedence exactly: required integrity/correlation failure;
  render-then-crash; crash without earlier render; completed stable interval; otherwise
  indeterminate. Never infer render from capture success or crash from missing process
  state.

- [ ] **Step 3: Implement and test explicit render-observation ingestion**

  Parse only `evidence-render-observation-v1`, verify scenario/run/artifact correlation,
  digest, bounded time, and allowlisted scenario detector ID. Reject a screenshot
  locator without a positive observation and reject any document that claims to be
  gate approval or general authorization.

- [ ] **Step 4: Verify and hand off Task 3**

  ```bash
  uv run --frozen pytest \
    tests/unit/evidence/test_collector_pipeline.py \
    tests/unit/evidence/test_collector_classification.py -q
  uv run --frozen ruff check .
  git diff --check
  ```

  Relay the decision-table matrix and explicit proof that screenshot success,
  completion alone, and absence cannot produce a positive outcome. Stop for approval
  and separate commit authorization.

## Task 4: Create the sole CLI, host registry, fixtures, and precondition stages

**Files:** Create `tools/evidence_gather.py`,
`tools/evidence_gather_support/__init__.py`, `common.py`, `registry.py`, `fixtures.py`,
and `tests/unit/tools/test_evidence_gather.py`; modify `pyproject.toml`.

- [ ] **Step 1: Write failing CLI ownership and parser tests**

  Parse all seven subcommands. Prove there is no `all`, `run`, implicit redaction,
  destination default, model default, environment fallback, pass-through argument
  vector, second entry point, console script, support `__main__`, or prompt-injection
  ID. AST-check the importer allowlist: sibling support imports pass; imports by any
  outside file other than `tools/evidence_gather.py` fail.

  ```bash
  uv run --frozen pytest tests/unit/tools/test_evidence_gather.py -q
  ```

  Expected RED: the entry point does not exist.

- [ ] **Step 2: Implement parser and explicit handler dispatch**

  ```python
  def build_parser() -> argparse.ArgumentParser: ...
  def main(argv: Sequence[str] | None = None) -> int: ...
  ```

  Every subcommand has a real handler when merged; a parser-only stub is not accepted.
  Task 4 implements `validate`, `prepare`, and `check`. Register later commands in the
  same parser only when their owning task supplies the actual handler and tests.
  Unknown adapters and unsafe paths fail before fixture mutation.

- [ ] **Step 3: Implement bounded registry, fixture preparation, and checks**

  Registry entries are fixed Python data constructed by the entry point. Scenario data
  selects IDs only. Preparation is digest-idempotent and mismatch-safe. Preconditions
  record stable codes and never launch a client or manufacture an outcome.

- [ ] **Step 4: Register live markers without weakening default tests**

  Add:

  ```toml
  requires_acpx = "requires independently authored acpx and a real agent process"
  requires_zed = "requires a real supported Zed instance and its real logs"
  requires_windows_desktop = "requires an interactive Windows desktop and real DWM"
  evidence_investigation = "runs a named evidence-only investigation with its real dependency"
  ```

  Default pytest selection excludes these markers. Existing gate markers remain
  unchanged.

- [ ] **Step 5: Verify and hand off Task 4**

  ```bash
  uv run --frozen pytest \
    tests/unit/tools/test_evidence_gather.py \
    tests/unit/evidence/test_collector_scenarios.py \
    tests/unit/evidence/test_collector_boundaries.py -q
  uv run --frozen python tools/evidence_gather.py --help
  uv run --frozen python tools/evidence_gather.py validate \
    --scenario "$(pwd)/tests/fixtures/evidence/scenarios/zed-session.toml"
  uv run --frozen ruff check .
  git diff --check
  ```

  The sample `validate` command is expected to fail before side effects because the
  required explicit model binding is absent. Relay its stable failure code, the
  ownership AST evidence, parser tests, Ruff, and unrun gates. Stop for approval and
  separate commit authorization.

## Task 5: Add ACP/NDJSON collection and prove real completion with `acpx`

**Files:** Create `tools/evidence_gather_support/acp.py`, `ndjson.py`,
`tests/integration/evidence/test_collector_acpx_live.py`; extend
`tests/unit/tools/test_evidence_gather.py`, `registry.py`, and the `collect` handler.

- [ ] **Step 1: Write failing unit cases through the entry point**

  Cover pre-run byte offset/file identity, ordered suffix extraction, partial final
  record, malformed interior record, rotation/replacement, foreign suffix, bounded
  reads, argument vector ownership, `shell=False`, process timeout, content-free
  failure codes, and exact event-location/correlation matching. Prove the completion
  event never creates `render_observed`.

  ```bash
  uv run --frozen pytest tests/unit/tools/test_evidence_gather.py \
    -k "ndjson or acp or completion or collect" -q
  ```

  Expected RED: ACP/NDJSON adapters are unregistered.

- [ ] **Step 2: Implement ACP collection and completion normalization**

  Resolve `acpx` from PATH, require its independently authored executable, launch the
  real approved agent invocation with an explicit vector and `shell=False`, and record
  bounded raw artifacts only under the capture root. Match only
  `server.py:process_request:exit` with scenario request/session/run correlation and
  reject error-bearing, older, foreign, or ambiguous events.

- [ ] **Step 3: Prove the real dependency in the introducing task**

  Run with explicit operator-approved real Gateway/Redis inputs if the real agent
  requires them and with an explicit model binding supplied at invocation:

  ```bash
  uv run --frozen pytest \
    tests/integration/evidence/test_collector_acpx_live.py \
    -m requires_acpx -q -s
  ```

  The live test must:

  - resolve and record the real `acpx --version`;
  - spawn the real agent process through `acpx`;
  - obtain the exact correlated completion event;
  - prove a foreign event and error-bearing event are rejected;
  - record content-free process/config identities and artifact digests;
  - scan captured diagnostics for raw known-secret canaries; and
  - make no UI-render claim.

  A project-authored ACP client or fake process fails this step.

- [ ] **Step 4: Verify and hand off Task 5**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_evidence_gather.py \
    -k "ndjson or acp or completion or collect" -q
  uv run --frozen ruff check .
  git diff --check
  ```

  Relay unit output, real `acpx` identity, real process/event evidence, canary scan,
  and unrun gates. Stop for approval and separate commit authorization.

## Task 6: Add Zed crash-log collection and prove it against real Zed 1.13.1

**Files:** Create `tools/evidence_gather_support/zed_logs.py` and
`tests/integration/evidence/test_collector_zed_logs_live.py`; extend the entry-point
tests and host registry.

- [ ] **Step 1: Write failing crash-watch cases through the entry point**

  Cover pre-run snapshot exclusion, new/changed identity, timestamp bounds, process
  identity, log versus dump roles, multiple instances, unrelated process, clock
  ambiguity, watcher timeout, changed file during hash, and content-free failures.

  ```bash
  uv run --frozen pytest tests/unit/tools/test_evidence_gather.py \
    -k "zed and (crash or log)" -q
  ```

  Expected RED: the Zed collector is absent.

- [ ] **Step 2: Implement the bounded Zed watcher**

  Require an explicit supported client identity and explicit Zed-log root; verify the
  resolved root is the real `%LOCALAPPDATA%\Zed\logs\` location for live evidence.
  Snapshot before scenario start, watch only the bounded interval, digest only
  new/changed candidates, and emit enough process/time/file identity to reject an
  unrelated instance. Never infer crash from process lookup failure alone.

- [ ] **Step 3: Prove the real dependency in the introducing task**

  With a real Zed 1.13.1 instance in an operator-approved test session:

  ```bash
  uv run --frozen pytest \
    tests/integration/evidence/test_collector_zed_logs_live.py \
    -m requires_zed -q -s
  ```

  Evidence must record the real version/process, real log-root identity, pre-run
  snapshot, real post-start log change, bounded timestamps, and digest. If a safe,
  operator-approved crash exercise is unavailable, the task remains incomplete; do
  not substitute a fixture or assert crash from ordinary log change.

- [ ] **Step 4: Verify and hand off Task 6**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_evidence_gather.py \
    -k "zed and (crash or log)" -q
  uv run --frozen ruff check .
  git diff --check
  ```

  Relay unit output, Zed version/process/log evidence, pre-run exclusion, any
  incomplete crash exercise, Ruff, and unrun gates. Stop for approval and separate
  commit authorization.

## Task 7: Add DWM physical-bounds capture and prove a real client window

**Files:** Create `tools/evidence_gather_support/windows_capture.py` and
`tests/integration/evidence/test_collector_dwm_live.py`; extend the entry-point tests
and host registry.

- [ ] **Step 1: Write failing Windows-capture cases through the entry point**

  Cover top-level visible-window resolution, PID mismatch, multiple candidates,
  `DWMWA_EXTENDED_FRAME_BOUNDS`, physical rectangle validation, DPI context, capture
  timestamp, image digest, bounds changed during capture, and API failure. Assert that
  a successful screenshot produces an artifact observation but no render claim.

  ```bash
  uv run --frozen pytest tests/unit/tools/test_evidence_gather.py \
    -k "dwm or physical_bounds or screenshot" -q
  ```

  Expected RED: Windows capture is absent.

- [ ] **Step 2: Implement the Windows-only host adapter**

  Use standard Windows APIs behind the host module. Resolve the intended process and
  top-level window, obtain DWM physical bounds immediately before capture, record DPI
  awareness and process/window identity, capture only the declared rectangle, and
  reject ambiguity. Portable modules receive only normalized models.

- [ ] **Step 3: Prove the real dependency in the introducing task**

  On an interactive Windows desktop with a real Zed 1.13.1 window:

  ```bash
  uv run --frozen pytest \
    tests/integration/evidence/test_collector_dwm_live.py \
    -m requires_windows_desktop -q -s
  ```

  Evidence must include real DWM bounds, DPI context, PID/HWND identity, capture time,
  image dimensions, and digest. It must also show that no semantic render claim was
  emitted.

- [ ] **Step 4: Verify and hand off Task 7**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_evidence_gather.py \
    -k "dwm or physical_bounds or screenshot" -q
  uv run --frozen ruff check .
  git diff --check
  ```

  Relay unit output, real DWM/window evidence, non-render assertion, Ruff, and unrun
  gates. Stop for approval and separate commit authorization.

## Task 8: Bind the separate redaction stage and safe report surface

**Files:** Create `tools/evidence_gather_support/redaction.py`, `reports.py`, and
`tests/integration/evidence/test_collector_redaction_live.py`; extend
`tools/evidence_gather.py`, its unit tests, bundle/report tests, and contract-sweep
tests.

- [ ] **Step 1: Write failing public-contract and report tests**

  Through the entry point, cover:

  - only `redact` imports/calls redaction orchestration;
  - all `CapturedArtifact` roles map exhaustively to gate `ArtifactKind`;
  - every gate model import is a public export of
    `evidence_handoff.redaction.models`, including `Disposition` and
    `ScreenshotApproval`;
  - no gate policy internal or entropy constant is referenced;
  - all roots/result/report targets are explicit and absolute;
  - `--workspace-root` is required and durable reauthorization runs at redact time;
  - launch environment is captured exactly once and no downstream ambient reread can
    diverge candidate resolution from authorization;
  - one or more `--user-data-root` arguments are required;
  - the forbidden-root tuple always contains the workspace root;
  - authenticated profile/identity lookup failure is fatal and no inherited profile
    environment variable is trusted;
  - `AuthorizedLaunch` and `EvidenceRedactionHostContext` never enter a serialized
    stage, diagnostic, report, or portable annotation;
  - configuration drift, missing durable approval, or stale approval fails before a
    gate request;
  - upstream `SNAPSHOT_MISMATCH` maps to
    `REDACTION_AUTHORIZATION_SNAPSHOT_MISMATCH`;
  - upstream `NO_APPROVAL` maps to
    `REDACTION_AUTHORIZATION_NO_DURABLE_APPROVAL`;
  - both authorization failures leave the raw bundle and provisional outcome
    byte-identical, create no gate request or report, and emit no upstream exception
    detail;
  - collector outcome remains unchanged by gate disposition;
  - required rejected/quarantined evidence blocks report creation;
  - screenshot requires matching independent `promoted` approval;
  - dump bytes never enter a report;
  - renderer receives only promoted locators and safe manifest fields;
  - reports reject raw paths/bodies/exceptions/policy constants;
  - `inspect` verifies digests without printing bodies; and
  - a gate contract rename breaks every collector fixture/call site in the same suite.

  ```bash
  uv run --frozen pytest tests/unit/tools/test_evidence_gather.py \
    -k "redact or report or inspect or contract" -q
  ```

  Expected RED: redaction/report handlers are absent.

- [ ] **Step 2: Implement redact-time durable authorization and full host context**

  Import:

  ```python
  from evidence_handoff.redaction.models import (
      ArtifactKind,
      Disposition,
      RedactionGateResult,
      RedactionRequest,
      RedactionRuntimeInputs,
      ScreenshotApproval,
  )
  from optimus.acp.evidence_redaction_adapter import (
      EvidenceRedactionHostContext,
      build_redaction_runtime_inputs,
  )
  ```

  Use the public launch/trusted-path sequence in **Redact-Time Host Context** to
  re-resolve the current candidate and obtain an in-memory `AuthorizedLaunch` from the
  existing durable approval. Build all eight `EvidenceRedactionHostContext` fields
  from their specified sources and convert them only with the canonical adapter.
  Never persist the candidate, authorization, context, resolved credentials, or
  identity values.

  Host-only function shapes:

  ```python
  def authorize_redaction_launch(*, workspace_root: Path) -> AuthorizedLaunch: ...

  def build_redaction_host_context(
      *,
      authorized_launch: AuthorizedLaunch,
      workspace_root: Path,
      user_data_roots: Sequence[Path],
      temporary_capture_root: Path,
      staging_root: Path,
      quarantine_root: Path,
      operator_forbidden_roots: Sequence[Path],
  ) -> EvidenceRedactionHostContext: ...
  ```

  `authorize_redaction_launch` captures the environment once and uses only public
  launch/trusted-path APIs. `build_redaction_host_context` resolves the authenticated
  profile and identity values, canonicalizes roots, inserts `workspace_root` into the
  forbidden set unconditionally, and rejects empty user-data or identity sets.

  Redact-time authorization failure is an expected stage outcome, not a collector
  failure. Translate `LaunchGateError.code` through this closed mapping:

  | Upstream launch code | Collector-side redaction-stage code |
  |---|---|
  | `SNAPSHOT_MISMATCH` | `REDACTION_AUTHORIZATION_SNAPSHOT_MISMATCH` |
  | `NO_APPROVAL` | `REDACTION_AUTHORIZATION_NO_DURABLE_APPROVAL` |

  Either code stops before host-context conversion, gate request construction, or
  report creation. It must not modify, replace, or reclassify the raw bundle or
  provisional result. Diagnostics contain only the mapped stable code; they do not
  chain or print the upstream detail. The remediation is to renew the durable approval
  for the current configuration and invoke `redact` again, never to weaken snapshot
  verification or reuse authorization captured during `collect`.

- [ ] **Step 3: Implement public gate requests and eligibility**

  Map `--sanitized-root` to `RedactionRequest.destination_root`. Parse an explicitly
  supplied screenshot approval into `ScreenshotApproval`. Submit one public request
  per declared artifact, compare dispositions through the public `Disposition` enum,
  consume only public result fields, and preserve the provisional outcome. Do not bind
  any gate policy constant.

- [ ] **Step 4: Implement deterministic safe reporting and body-free inspection**

  Write `evidence-report-v1` only after every required artifact is eligible. Use
  promoted relative locators and content-free manifest references. Atomically create
  the explicitly named report; failure must not leave a report claiming unpromoted
  evidence.

- [ ] **Step 5: Prove both real dependencies in the introducing task**

  Use a real OS credential-store backend and the canonical host resolver without
  writing, deleting, rotating, or echoing credential values. Then run the real public
  gate over real filesystem artifacts:

  ```bash
  uv run --frozen pytest \
    tests/integration/evidence/test_collector_redaction_live.py \
    -m requires_os_keyring -q -s
  ```

  Required evidence:

  - current launch snapshot/candidate resolution from the explicit workspace;
  - successful existing durable approval check with no one-shot consumption;
  - expected, value-free handling of a separately exercised missing durable approval
    or configuration-drift case, with unchanged input digests and no gate request;
  - all eight host-context fields populated from their specified real sources;
  - real resolver and credential-store backend identity;
  - real authenticated profile/account/host identity source classes and value-free
    counts;
  - non-empty forbidden roots containing the workspace plus supplied forbidden roots;
  - explicit user-data roots and proof that root overlap/cloud-sync rejection remains
    active;
  - proof that runtime values did not enter diagnostics, observations, or reports;
  - real staging/quarantine/sanitized roots and atomic gate dispositions;
  - promoted sanitized JSON/NDJSON/text;
  - screenshot `awaiting_human_approval` followed only by independent matching
    approval where available;
  - hash-only dump quarantine;
  - unchanged provisional collector outcome; and
  - raw-output known-secret canary scan.

- [ ] **Step 6: Verify and hand off Task 8**

  ```bash
  uv run --frozen pytest \
    tests/unit/tools/test_evidence_gather.py \
    tests/integration/evidence/test_collector_redaction_live.py \
    -k "redact or report or inspect or contract" -q
  uv run --frozen ruff check .
  git diff --check
  ```

  Relay public contract imports, authorization source and durable approval result, all
  eight value-free host-context source records, exhaustive mapping result, real
  adapter/store and gate evidence, canary scan, disposition/outcome separation, Ruff,
  and unrun gates. Stop for approval and separate commit authorization.

## Task 9: Prove the staged real Zed scenario end to end

**Files:** Create `tests/e2e/evidence/test_collector_staged_live.py`; extend the
declarative Zed scenario only if its already-approved typed fields require a
non-executable correction.

This task combines dependencies already proven in Tasks 5 through 8. It may not be
used to replace any missing same-task proof.

- [ ] **Step 1: Write the staged E2E assertions**

  The test invokes only `tools/evidence_gather.py` and calls `prepare`, `check`,
  `collect`, `classify`, `redact`, and `inspect` separately. It supplies explicit
  model binding, scenario, workspace, user-data, forbidden, capture/result/gate/report
  paths, and an operator-approved existing Zed session backed by a current durable
  launch approval. The operator manually initiates the scenario action; no automated
  prompt injection is introduced.

- [ ] **Step 2: Run real indeterminate and determinate paths**

  ```bash
  uv run --frozen pytest \
    tests/e2e/evidence/test_collector_staged_live.py \
    -m "requires_acpx and requires_zed and requires_windows_desktop and requires_os_keyring" \
    -q -s
  ```

  Prove:

  - missing semantic render observation stays `indeterminate`;
  - incomplete interval, collector failure, or ambiguous multi-instance crash stays
    `indeterminate`;
  - real render followed by real correlated crash yields
    `rendered_then_crashed`;
  - real correlated crash before positive render yields `client_crashed`;
  - real completion, positive render, liveness, complete interval, and no correlated
    crash yields `rendered_stable`;
  - collection/classification alone create no promotable report;
  - explicit redaction preserves outcome while enforcing disposition; and
  - inspect verifies digests without artifact bodies.

  Each determinate claim requires the corresponding real evidence. If an
  operator-approved real crash/render exercise cannot be completed, record the
  missing claim and leave the task and feature open; do not synthesize it.

- [ ] **Step 3: Verify structural injection absence after the live run**

  ```bash
  uv run --frozen pytest \
    tests/unit/evidence/test_collector_boundaries.py \
    tests/unit/tools/test_evidence_gather.py \
    -k "prompt or entry_point or registry" -q
  ```

  Expected: no prompt-injection capability became usable to support the manual run.

- [ ] **Step 4: Hand off Task 9**

  ```bash
  uv run --frozen ruff check .
  git diff --check
  ```

  Relay each outcome's real evidence digests, stage commands, process/window/log/gate
  identities, unavailable cases, structural-absence result, Ruff, and unrun gates.
  Stop for approval and separate commit authorization.

## Task 10: Investigate UIA/SendInput against real Zed 1.13.1

**Files:** Create
`tests/investigation/evidence/test_zed_uia_sendinput_live.py` only.

- [ ] **Step 1: Write the test-only probe and bounded result contract**

  The pytest module may contain private probe helpers. It must not add a package
  entry point, `__main__`, support module, host registry ID, portable enum/model field,
  feature flag, or scenario capability. Its result is exactly `supported`,
  `unsupported`, or `indeterminate`, with bounded process/window/control identities,
  timestamps, and artifact digests.

- [ ] **Step 2: Exercise real UIA/SendInput in the introducing task**

  ```bash
  uv run --frozen pytest \
    tests/investigation/evidence/test_zed_uia_sendinput_live.py \
    -m "evidence_investigation and requires_zed and requires_windows_desktop" \
    -q -s
  ```

  Use real Zed 1.13.1 and real UIA/SendInput. Record control discovery, focus,
  attempted bounded input, observed editor effect or stable failure reason, cleanup,
  and evidence digests. A negative result completes the investigation; a fake result
  does not.

- [ ] **Step 3: Prove the capability remains structurally absent**

  ```bash
  uv run --frozen pytest \
    tests/unit/evidence/test_collector_boundaries.py \
    tests/unit/tools/test_evidence_gather.py \
    -k "prompt or registry or entry_point" -q
  uv run --frozen ruff check .
  git diff --check
  ```

  Relay real probe evidence and result. Stop for approval and separate commit
  authorization. Do not add a usable adapter even if this one investigation passes.

## Task 11: Investigate the real `zed://` scheme

**Files:** Create `tests/investigation/evidence/test_zed_scheme_live.py` only.

- [ ] **Step 1: Write the test-only scheme probe**

  Require an explicit operator-supplied test URI payload and bounded expected
  observation. Do not embed a model, shell fragment, arbitrary executable vector, or
  host registry ID. Record `supported`, `unsupported`, or `indeterminate`.

- [ ] **Step 2: Invoke the real registered scheme in the introducing task**

  ```bash
  uv run --frozen pytest \
    tests/investigation/evidence/test_zed_scheme_live.py \
    -m "evidence_investigation and requires_zed" -q -s
  ```

  Record scheme registration identity, real invocation time, Zed process/window/log
  changes, observed editor effect or stable failure, and artifact digests. Invocation
  must use the real OS scheme path, not a mocked handler.

- [ ] **Step 3: Reprove structural absence and hand off**

  ```bash
  uv run --frozen pytest \
    tests/unit/evidence/test_collector_boundaries.py \
    tests/unit/tools/test_evidence_gather.py \
    -k "prompt or registry or entry_point" -q
  uv run --frozen ruff check .
  git diff --check
  ```

  Relay the real scheme result and evidence. Stop for approval and separate commit
  authorization. Do not add a usable adapter.

## Task 12: Investigate real hermetic Zed user-data instances

**Files:** Create `tests/investigation/evidence/test_zed_user_data_live.py` only.

- [ ] **Step 1: Write the test-only isolation probe**

  Require explicit temporary user-data roots and explicit Zed executable identity.
  Refuse existing profile roots, repository paths, cloud-synchronized roots, overlap,
  symlinks/reparse escapes, or ambiguous process custody. Record `supported`,
  `unsupported`, or `indeterminate`.

- [ ] **Step 2: Exercise real `--user-data-dir` instances in the introducing task**

  ```bash
  uv run --frozen pytest \
    tests/investigation/evidence/test_zed_user_data_live.py \
    -m "evidence_investigation and requires_zed" -q -s
  ```

  Launch at least two real isolated Zed instances with distinct explicit roots and
  `shell=False`. Record process/window/root identities, observed cross-root isolation,
  log custody, bounded teardown, and artifact digests. Do not delete an operator
  profile or reuse ambient Zed state.

- [ ] **Step 3: Reprove structural absence and hand off**

  ```bash
  uv run --frozen pytest \
    tests/unit/evidence/test_collector_boundaries.py \
    tests/unit/tools/test_evidence_gather.py \
    -k "prompt or registry or entry_point" -q
  uv run --frozen ruff check .
  git diff --check
  ```

  Relay the real isolation result and evidence. Stop for approval and separate commit
  authorization. Even if all three investigations pass, proposing a usable adapter is
  separate reviewed design work and is not authorized here.

## Task 13: Run repository gates, audit documentation, and hand off

**Files:** Modify only current-state documents whose claims became true or false,
including the evidence/handoff pool. Do not edit the frozen collector design, frozen
gate documents, or the Optimus open-work pool.

This task may index and relay earlier evidence. It may not first exercise a real
dependency, replace missing introducing-task evidence, or turn an incomplete live claim
into completion.

- [ ] **Step 1: Audit all Definition of Done claims against named evidence**

  Build a content-free claim-to-evidence table from Tasks 2 and 5 through 12. Every
  live claim names its producing task, exact command, real dependency identity,
  artifact digest, and reviewer ruling. Leave any claim without that evidence
  unchecked and the feature open.

- [ ] **Step 2: Run the complete local verification matrix**

  ```bash
  uv run --frozen pytest tests/unit/evidence tests/unit/tools/test_evidence_gather.py -q
  uv run --frozen pytest tests/integration/evidence -q
  uv run --frozen pytest tests/e2e/evidence -q
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  uv run --frozen pytest \
    --cov=src/optimus \
    --cov=src/optimus_gateway \
    --cov=src/optimus_security \
    --cov=src/evidence_handoff \
    --cov-report=term-missing \
    --cov-report=xml \
    --cov-fail-under=80
  uv run --frozen ruff check .
  uv run --frozen detect-secrets scan --baseline .secrets.baseline
  uv run --frozen bandit -c pyproject.toml -r src
  uv build
  git diff --check
  ```

  Live-marker tests are not silently counted as passed when skipped. Their already
  produced introducing-task evidence remains part of the handoff.

- [ ] **Step 3: Re-run isolated import, ownership, naming, and artifact scans**

  ```bash
  uv run --frozen python -I -c \
    "import evidence_handoff.collector; print(evidence_handoff.collector.__name__)"
  uv run --frozen pytest \
    tests/unit/evidence/test_import_boundaries.py \
    tests/unit/evidence/test_naming_boundaries.py \
    tests/unit/evidence/test_collector_boundaries.py \
    tests/unit/tools/test_evidence_gather.py -q
  uv run --frozen pytest \
    tests/unit/evidence/test_naming_boundaries.py \
    tests/unit/evidence/test_collector_boundaries.py -q
  ```

  Expected: isolated import and tests pass; the naming-boundary tests report no retired
  names in new product surfaces. The closed rename provenance in the pool is outside
  that test perimeter.

- [ ] **Step 4: Perform documentation freshness and custody audit**

  Read every repository document whose current-state claims may have changed,
  including the evidence/handoff pool, roadmap, and README. Update only stale claims.
  The product pool remains the only live status authority. Do not add collector status
  to another document and do not add an Optimus-side dependency clause.

  If and only if every required real evidence claim passed and the reviewer approves
  closure, update the collector pool row to `Closed` with the actual implementation
  commit/merge evidence after it exists. Before that merge exists, record only the
  strongest truthful current state; never predict a merge reference.

- [ ] **Step 5: Assemble the reviewer bundle and stop**

  Include:

  - frozen design commit/path/digest verification;
  - exact committed implementation diff and commit list;
  - unit, integration, E2E, coverage, Ruff, secrets, Bandit, build, and docs results;
  - per-task real-dependency identity/evidence/digest table;
  - all investigation results without claiming a usable injection capability;
  - four-outcome real evidence and any unavailable case;
  - gate contract/import and outcome/disposition separation evidence;
  - isolated import, entry-point/importer ownership, and naming scans;
  - documentation freshness diff;
  - reviewer checkpoint state; and
  - every unrun or failed gate with reason.

  Relay the bundle to the reviewer. Do not make a closing commit until reviewer
  approval and separate operator authorization. After an authorized closing commit,
  stop. Do not push, open a PR, merge, delete branches, or rewrite history.

## Definition of Done

- [ ] The implementation matches the frozen design commit/path/digest and no design
  amendment is pending.
- [ ] The redaction gate implementation is merged; every gate model used by the
  collector is a public export of `evidence_handoff.redaction.models`, with no
  internal symbol or stringly typed disposition fallback.
- [ ] `tools/evidence_gather.py` is the only executable feature surface and exposes
  exactly the seven explicit stages without an implicit redaction route.
- [ ] Support modules are non-entry-point modules; sibling imports are allowed only
  within their package and the outside importer allowlist contains only the entry
  point.
- [ ] `evidence_handoff.collector` is standard-library-only and imports none of
  `optimus`, `optimus_gateway`, `tools`, or `optimus_security`; host types do not leak
  into portable contracts.
- [ ] Strict equivalent TOML/JSON scenarios reject executable content and unknown
  adapters before side effects; model-aware work requires an explicit model binding.
- [ ] Every destination-bearing command requires an explicit absolute target; no
  report, capture, staging, quarantine, sanitized, result, or approval default exists.
- [ ] Raw bundles and stage transitions are immutable, atomic, digest-bound,
  resumable, and content-free outside declared raw artifacts.
- [ ] Completion accepts only the correlated
  `server.py:process_request:exit` event and does not imply UI rendering.
- [ ] Zed crash evidence excludes pre-run/foreign/multi-instance ambiguity and DWM
  evidence records real physical bounds/DPI/process-window identity without creating
  a render claim.
- [ ] Classification produces exactly the four approved outcomes with integrity-first
  precedence and complete-interval stability.
- [ ] The separate `redact` stage uses the canonical host adapter, public gate
  contracts, redact-time durable reauthorization, all eight host-context fields,
  exhaustive artifact mapping, and no policy internal or entropy constant.
- [ ] Missing durable approval and authorization snapshot drift map to the two stable
  redaction-stage codes without mutating the raw bundle, provisional outcome, or
  creating a gate request/report.
- [ ] Provisional outcome and gate disposition remain separate; reports contain only
  eligible promoted evidence, independently approved screenshots, and hash-only dump
  metadata.
- [ ] Prompt-injection capability is structurally absent. Each of UIA/SendInput,
  `zed://`, and hermetic user-data investigations has same-task real evidence, but no
  usable adapter is added.
- [ ] Real filesystem, independently authored `acpx`/agent, Zed 1.13.1 logs, Windows
  DWM, canonical runtime adapter/OS credential store, and public gate evidence passed
  in their introducing tasks.
- [ ] Cross-component staged evidence supports every claimed determinate outcome and
  retains `indeterminate` for missing, incomplete, conflicting, or ambiguous evidence.
- [ ] Aggregate production coverage is at least 80%; Ruff, secret scan, Bandit, build,
  import, naming, ownership, and document hygiene gates are clean.
- [ ] Current-state documentation is fresh, the product pool is the sole status
  authority, the Optimus pool is untouched, the reviewer checkpoint is unstaged, and
  no push/PR/merge occurred under this execution plan.

## Review Handoff

The reviewer must approve this plan against the frozen committed design before any
implementation pickup. During execution, the operator relays one completed task at a
time. A task approval authorizes only the separately requested commit for that task;
it does not authorize the next task or any remote Git operation.
