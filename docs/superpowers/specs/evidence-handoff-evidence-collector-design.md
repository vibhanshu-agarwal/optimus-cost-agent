# EVIDENCE-HANDOFF-FEAT-EVIDENCE-COLLECTOR Design Specification

**Feature identity:** `EVIDENCE-HANDOFF-FEAT-EVIDENCE-COLLECTOR`.

**Design baseline:** `origin/main` at
`2f954ba2905c2efff68c81c3f34aed2996c44dfb`.

## Document authority and custody

- This document owns the collector's architecture, scope, contracts, failure semantics, and
  verification requirements.
- Live feature state belongs only in the
  [evidence and handoff open-work pool](../plans/archive/evidence-handoff-open-work-pool.md). This design
  does not duplicate status, scheduling, or progress.
- The product is on an independent implementation train. This design creates no roadmap entry and
  reserves no scheduling identifier.
- Product-owned document basenames use the descriptive `evidence-handoff-*.md` namespace. Package,
  module, command, schema, configuration, and artifact names remain descriptive and contain neither
  a feature identity nor a scheduling identifier.
- The ratified pool row is the scope authority. This design makes its requirements executable
  without adding another product capability.

## Goal

Create one reusable evidence-gathering surface that turns a declarative scenario into a
correlated, classifiable evidence bundle. The collector must compose independently testable
collectors and detectors, distinguish client rendering from client failure without overclaiming,
and hand raw artifacts to the separately invoked redaction gate before any report is promotable.

The operator-facing executable is exactly `tools/evidence_gather.py`. Portable scenario,
observation, composition, and classification behavior lives under `evidence_handoff`; concrete
Optimus, process, Zed, and Windows integration remains host-side tooling.

## Authoritative scope

The binding scope is:

> One `tools/evidence_gather.py` entry point with subcommands, declarative scenarios, composable
> collectors/detectors, and the redaction gate as a separately invocable final stage. Outcomes are
> `rendered_stable`, `rendered_then_crashed`, `client_crashed`, or `indeterminate`; no hardcoded
> model literals or default report targets. Its Zed prompt-injection gate remains investigation-only
> until UIA/SendInput on Zed 1.13.1, the `zed://` scheme, and hermetic `--user-data-dir` instances
> produce evidence.

### In scope

- A strict, versioned declarative scenario contract.
- Required runtime bindings with no model default.
- Portable collector and detector protocols.
- Normalized observations, evidence claims, artifact declarations, run manifests, and provisional
  classification results.
- Deterministic composition and the four-value outcome reducer.
- One CLI entry point with explicit stage subcommands.
- Host-side fixture preparation and precondition checks.
- Host-side NDJSON extraction and completion detection through the correlated
  `server.py:process_request:exit` event.
- Host-side crash detection by watching new evidence under `%LOCALAPPDATA%\Zed\logs\`.
- Host-side Windows capture using DWM physical window bounds.
- A separately invoked final redaction stage that consumes only the redaction gate's public
  interface.
- Promotable report construction from sanitized artifacts and content-free gate metadata only.
- Investigation harnesses for the three named Zed prompt-injection mechanisms, without a usable
  prompt-injection adapter.

### Explicit non-goals

- Implementing, replacing, or weakening the redaction gate.
- Defining redaction patterns, entropy thresholds, preservation rules, secret inventories, path
  rules, or screenshot-approval policy.
- Importing Optimus, Optimus Gateway, or project tooling from `evidence_handoff`.
- Creating a second redaction-rule engine or calling `optimus_security` directly from collector
  code.
- Loading third-party collectors, detectors, or scenario code dynamically.
- Treating arbitrary shell strings, Python expressions, or import paths as scenario data.
- Providing a monolithic command that silently performs collection and redaction.
- Providing a default model, capture root, staging root, quarantine root, result path, destination,
  or report target.
- Enabling automated Zed prompt injection through a disabled flag, undocumented adapter identifier,
  or configuration-only change.
- Reopening fixture preparation, precondition checks, NDJSON extraction, ACP completion detection,
  Zed crash-log watching, or DWM physical-bounds capture as research questions.
- Implementing the handoff ledger, a general approval/denial record, or transcript archival.
- Changing Optimus roadmap or backlog custody.

## Settled evidence and design inputs

The following capabilities are established inputs, not spikes:

- Fixture preparation and precondition checks are automatable.
- NDJSON evidence can be extracted deterministically.
- ACP completion is detected through the
  `server.py:process_request:exit` debug event, with scenario/run correlation.
- Zed crash evidence is detected by taking a pre-run snapshot and watching for new evidence under
  `%LOCALAPPDATA%\Zed\logs\`.
- Windows capture uses DWM physical window bounds rather than logical client bounds.

The collector design composes these capabilities and requires fresh real-dependency proof when
their reusable implementations are introduced. It does not ask an implementation worker to
rediscover whether they are possible.

## Architecture

### Dependency direction

The dependency graph is intentionally one-way:

```text
tools/evidence_gather.py
    |---> tools/evidence_gather_support.*             host-side adapters
    |---> evidence_handoff.collector                  portable collection core
    |---> evidence_handoff.redaction                  public gate surface, redact subcommand only
    \---> optimus.acp.evidence_redaction_adapter      host runtime-input adaptation
              \---> evidence_handoff.redaction

evidence_handoff.redaction ---> optimus_security
```

The `evidence_handoff.redaction -> optimus_security` edge belongs to the redaction gate. It is not a
collector dependency. Modules under `evidence_handoff.collector` neither import
`optimus_security` nor reproduce its behavior.

The following directions are forbidden:

```text
evidence_handoff -X-> optimus
evidence_handoff -X-> optimus_gateway
evidence_handoff -X-> tools
evidence_handoff.collector -X-> optimus_security
optimus_security -X-> evidence_handoff
```

`tools` may import `evidence_handoff`, the Optimus host adapter, and other host dependencies. The
portable package never reaches back into host tooling through reflection, dynamic imports,
untyped mappings, or delayed imports. Host implementations may satisfy and be passed behind
portable protocols, but host types must not appear in portable models, function signatures,
protocol definitions, or serialized contracts; the portable layer neither introspects nor retains
their concrete types.

### Portable package responsibilities

`evidence_handoff.collector` owns:

- frozen scenario and runtime-binding models;
- strict scenario parsing and validation;
- collector, detector, clock, and artifact-store protocols;
- normalized observations and evidence claims;
- deterministic stage ordering and composition;
- run-manifest and provisional-result schemas;
- artifact-kind and artifact-role declarations for later redaction;
- the outcome enum and classification reducer; and
- stable, value-free failure codes.

The portable layer accepts paths, values, clocks, and protocol implementations from its caller. It
does not read ambient environment variables, invoke an Optimus bootstrap path, discover Zed,
enumerate Windows processes, select a model, or choose persistence roots.

### Host-side tooling responsibilities

`tools/evidence_gather.py` owns:

- CLI parsing and subcommand dispatch;
- explicit path and runtime-binding intake;
- the allowlisted host adapter registry;
- construction of portable run contexts;
- invocation of host-side fixture, process, ACP, Zed, log, and window adapters;
- construction of gate runtime inputs through the Optimus host adapter;
- invocation of the redaction gate for the `redact` subcommand only;
- sanitized report rendering; and
- process exit codes and concise operator diagnostics.

Support code may live under `tools/evidence_gather_support/`, but those modules are not entry
points. They have no `__main__` blocks, no console-script registrations, and no executable wrapper
files. Imports between sibling modules inside `tools/evidence_gather_support` are permitted so
adapters can share internal helpers. Outside that support package, only `tools/evidence_gather.py`
may import its modules; an AST ownership test enforces that importer allowlist. Their purpose is to
keep the sole entry point readable, not to create additional invocation surfaces.

### Why the boundary is portable

Scenario parsing, observation normalization, evidence ordering, claim validation, and outcome
classification do not require Optimus objects or Windows APIs. A future host can supply different
protocol implementations while preserving the same scenario and result contracts.

Concrete launch authorization, independently authored ACP client invocation, Zed log locations,
Windows handles, DWM bounds, and Optimus credential resolution are host facts. Keeping them under
`tools` or the existing Optimus adapter prevents portable models from acquiring deployable-package
types.

## Declarative scenario contract

### Schema

Scenarios use a strict, versioned schema such as `evidence-scenario-v1`. TOML is the canonical
human-authored form; deterministic JSON is accepted for generated fixtures. Both representations
produce the same portable model and reject unknown fields.

Each scenario declares:

| Field | Contract |
|---|---|
| `schema` | Exact supported schema identifier. |
| `scenario_id` | Descriptive stable identifier; no feature or scheduling identifier. |
| `required_bindings` | Names, types, and bounds for values supplied at invocation. |
| `client` | Allowlisted client adapter ID and typed, non-executable parameters. |
| `fixture` | Allowlisted preparation adapter ID and typed fixture recipe. |
| `preconditions` | Ordered allowlisted checks with stable failure codes. |
| `collection` | Ordered collector IDs, timeouts, and artifact declarations. |
| `detection` | Detector IDs and typed correlation/observation-window parameters. |
| `required_evidence` | Claims and artifact roles required before an outcome can be promotable. |

Report paths and redaction roots are not scenario fields. They are operator-supplied CLI arguments
at the stage that uses them.

### Model binding

Any model-aware client adapter receives a named runtime binding. A scenario may require a binding
named `model`, but neither source code nor a shipped scenario assigns it a model literal. The CLI
requires the operator or invoking harness to supply the value explicitly and records the resolved
value as evidence. Missing, empty, or multiply supplied model bindings fail validation before
fixture mutation or process launch.

There is no environment-variable fallback and no "recommended" model. Tests scan the entry point,
support modules, portable package, shipped scenarios, and configuration surfaces for model
literals and default-bearing model arguments.

### Non-executable data

Scenario files are untrusted input. They may select only IDs already present in the host registry.
They cannot contain:

- module or class import paths;
- Python expressions or templates with evaluation semantics;
- shell commands or shell fragments;
- executable hooks;
- environment-variable expansion;
- arbitrary subprocess argument vectors; or
- dynamic package/entry-point names.

Each adapter owns a bounded typed parameter model and produces a fully constructed argument vector
with `shell=False` when process execution is required. Unknown IDs, unknown keys, invalid bounds,
and unsupported combinations fail before preparation begins.

## Single entry point and stage commands

`tools/evidence_gather.py` exposes these subcommands:

| Subcommand | Responsibility |
|---|---|
| `validate` | Parse a scenario, resolve required bindings, validate adapter IDs, and emit only a content-free summary. |
| `prepare` | Materialize declared fixtures and record immutable pre-run source snapshots in an explicit private capture root. |
| `check` | Run declared preconditions without launching the scenario client. |
| `collect` | Launch or attach through host adapters, run collectors, and write a raw, non-promotable observation bundle. |
| `classify` | Run detectors over a completed raw bundle and write a provisional four-value result to an explicit path inside the private capture root. |
| `redact` | Invoke the public redaction gate over declared artifacts, then create a report only from eligible sanitized outputs and safe gate metadata. |
| `inspect` | Verify a promoted report bundle, gate manifests, artifact digests, and provenance without printing artifact bodies. |

There is no `all`, `run`, or equivalent command that implicitly invokes `redact`. Collection and
classification always stop with a raw private bundle. Promotion requires a later, explicit
`redact` invocation with all required roots and the report target supplied.

Every path-bearing subcommand requires absolute paths, validates containment and overlap, and
rejects repository, cloud-synchronized, or otherwise forbidden persistence roots where the
artifact's custody class prohibits them. The tool never derives a report filename from the
scenario ID, current directory, timestamp, or model.

## Portable execution contracts

### Run identity and manifest

`prepare` creates a versioned run manifest in the explicit private capture root. It includes:

- scenario schema and scenario-content digest;
- scenario ID and generated run ID;
- content-free binding-source metadata and the explicitly supplied model value;
- selected adapter IDs and adapter contract versions;
- fixture and precondition declarations;
- collection and detection configuration;
- required artifact roles;
- monotonic-clock origin and wall-clock start time; and
- stage input/output digests.

The manifest contains no secret inventory, environment mapping, credential value, raw exception,
or implicit destination. Each later subcommand verifies the scenario and preceding-stage digests
before acting. A mismatch is not repaired or silently regenerated.

### Observations

Collectors emit immutable normalized observations with:

- schema version;
- scenario and run IDs;
- collector ID and monotonically increasing sequence;
- monotonic offset plus timezone-aware wall-clock timestamp;
- observation kind;
- bounded typed correlation fields;
- referenced artifact role and digest where applicable; and
- a stable value-free reason code when collection could not complete.

Raw log text, image pixels, subprocess streams, and dump bytes live only in declared raw artifacts.
They are not copied into observation records or exception text.

### Collector protocol

A collector:

1. declares the observation kinds and artifact roles it can produce;
2. validates its typed configuration before side effects;
3. accepts only a portable run context and a host-provided implementation behind a portable
   capability protocol;
4. emits normalized observations and artifact descriptors;
5. closes or releases resources deterministically; and
6. reports failures using stable codes without converting them into detector claims.

Collectors do not classify outcomes and do not invoke the redaction gate.

### Detector protocol

A detector is a deterministic reducer over the normalized observation set and declared artifact
metadata. It emits zero or more claims containing:

- claim kind;
- scenario/run correlation;
- the ordered evidence references supporting the claim;
- claim timestamp or bounded interval;
- detector ID and contract version; and
- a stable reason code.

Detectors never read ambient logs, launch processes, mutate fixtures, or invoke redaction. Host
collectors first turn external state into normalized evidence; detectors then reason only over that
bounded evidence.

### Composition

The pipeline preserves scenario order for side-effecting stages and uses deterministic ordering
for independent observations. Multiple collectors may contribute to a claim, but no collector can
overwrite another collector's evidence. Duplicate sequence numbers, foreign run IDs, conflicting
correlations, clock regressions, missing required collectors, or artifact-digest mismatches make
the affected claim invalid.

## Settled collectors and detectors

### Fixture and precondition adapters

Fixture preparation is idempotent for the same run manifest and refuses to overwrite a fixture
whose observed digest differs from the manifest. Preconditions run after preparation and before
client launch. A failed precondition prevents collection and records a stable code; it does not
manufacture a client outcome.

### NDJSON collector

The NDJSON collector records a pre-run byte offset or file identity, reads only the run-scoped
suffix, preserves record order, and rejects foreign or malformed interior records. Raw extraction
remains in the private capture root for the redaction gate. Parsing failures are explicit
collection failures, not a text-mode fallback.

### ACP completion detector

The completion detector recognizes the exact debug event location
`server.py:process_request:exit`. It requires the scenario's request/session/run correlation and
rejects older, foreign, ambiguous, or error-bearing events. The event proves that the agent-side
client request handler completed; it does not by itself prove that a UI rendered the response.

### Zed crash collector

The host takes a pre-run snapshot of `%LOCALAPPDATA%\Zed\logs\` and watches for new or changed
evidence after scenario start. The collector records file identity, bounded timestamps, process
identity when available, artifact digest, and evidence kind. Pre-existing dumps or log entries
cannot satisfy a crash claim.

The crash detector requires temporal and run/process correlation strong enough to exclude an
unrelated Zed instance. Ambiguous multi-instance evidence yields no crash claim and therefore
cannot be used to assert a crash outcome.

### DWM physical-bounds capture

The Windows host adapter resolves the intended top-level client window and obtains DWM physical
bounds immediately before capture. The captured artifact records the window/process identity,
physical rectangle, DPI context, capture timestamp, and image digest.

A successful capture proves that the declared physical window region was captured. It is evidence
transport, not semantic render proof. A scenario-specific detector must produce a positive render
claim from approved evidence; otherwise rendering remains unproven.

## Outcome classification

### Evidence claims

The classifier consumes these logical claims:

- `completion_observed`: a valid correlated ACP completion event;
- `render_observed`: a positive scenario-specific render detector result;
- `client_alive`: positive liveness at a bounded time;
- `observation_window_complete`: all required collectors remained healthy through the configured
  post-render interval;
- `client_crash_observed`: a valid correlated crash claim; and
- integrity claims covering required collectors, correlations, clocks, and artifact digests.

The classifier does not infer a positive claim merely because an expected negative artifact was
absent.

### Decision table and precedence

Exactly one outcome is produced:

| Conditions | Outcome |
|---|---|
| A valid render claim exists and a valid correlated crash occurs later. | `rendered_then_crashed` |
| A valid correlated crash exists and no valid render claim precedes it. | `client_crashed` |
| Valid completion and render claims exist, the client remains alive, every required collector completes the full stability interval, and no valid crash exists in that interval. | `rendered_stable` |
| Evidence is missing, foreign, conflicting, temporally ambiguous, digest-invalid, collector-incomplete, timed out before the full interval, or otherwise insufficient for the three determinate outcomes. | `indeterminate` |

Precedence is:

1. Integrity or correlation failure affecting a required claim yields `indeterminate`.
2. An ordered render-then-crash claim yields `rendered_then_crashed`.
3. A valid crash without an earlier render claim yields `client_crashed`.
4. `rendered_stable` is available only after the entire declared stability interval completes.
5. Every remaining case yields `indeterminate`.

`rendered_stable` is never inferred from process presence at one instant, a successful screenshot
call, missing crash files, or ACP completion alone. `client_crashed` is never inferred solely from
a process lookup failure. Contradictory positive render and crash ordering is not resolved by
guessing.

The provisional outcome and the redaction disposition are separate axes. Redaction cannot rewrite
what the evidence classifier observed; it determines whether the supporting artifacts may enter a
promotable report.

## Zed prompt-injection investigation boundary

Automated prompt injection is structurally absent from the usable collector:

- no prompt-injection adapter ID appears in the allowlisted host registry;
- no prompt-injection capability exists in portable scenario enums or models;
- no dormant implementation is selected by a disabled feature flag;
- no environment variable or scenario field can enable it; and
- a scenario naming an unknown prompt-injection adapter fails validation before side effects.

Investigation-only test probes may gather evidence for:

1. UIA/SendInput against Zed 1.13.1;
2. the `zed://` scheme; and
3. hermetic `--user-data-dir` instances.

Each investigation must exercise its real named mechanism and produce its evidence in the same
implementation task that introduces the probe. Fakes can test parsing and failure handling but do
not satisfy the investigation. These probes live in test-only surfaces invoked by the test runner;
they are not registered collector adapters, `tools/evidence_gather_support` modules, console
scripts, or additional executable wrappers. A usable prompt-injection adapter may be proposed only
after all three real evidence sets exist and have been reviewed. Adding the adapter ID, scenario
capability, or implementation before that gate is a design violation, not an incomplete toggle.

## Redaction-gate integration

### Contract authority

The collector binds to `ArtifactKind`, `RedactionRuntimeInputs`, `RedactionRequest`, and
`RedactionGateResult` as defined by `evidence_handoff.redaction.models` in the approved
redaction-gate implementation plan. These are approved-but-not-yet-implemented design-time
contracts; this document does not redefine them. That module is the single authority for their
names and fields. If gate implementation renames or reshapes any public contract, the same
contract-changing task must sweep this design, collector call sites, fixtures, and contract tests;
a compatibility alias or silent stale binding is not acceptable.

The gate's public dispositions are:

- `promoted`;
- `awaiting_human_approval`;
- `quarantined`; and
- `rejected`.

### Separate invocation

Only `tools/evidence_gather.py redact` invokes the gate. `collect` and `classify` neither import nor
call redaction orchestration. The `redact` subcommand:

1. verifies the completed raw-bundle and provisional-result digests;
2. obtains `RedactionRuntimeInputs` through the public Optimus host adapter;
3. maps each declared artifact to an explicit public `ArtifactKind` and role;
4. submits one public `RedactionRequest` per artifact;
5. consumes only `RedactionGateResult`, its public disposition, promoted artifacts, and
   content-free manifests;
6. checks the scenario's required-evidence eligibility rules; and
7. writes the explicitly named report only after all required evidence is safely representable.

The collector does not import the shared sanitizer, sensitive-value inventory, entropy detector,
pattern registry, policy constants, or other gate internals. In particular, it neither freezes nor
asserts entropy thresholds, minimum lengths, token grammars, or preservation constants. Gate
calibration remains wholly gate-owned.

### Artifact eligibility

| Artifact class | Report eligibility |
|---|---|
| JSON, NDJSON, ACP debug trace, and text | The required sanitized artifact and manifest must be `promoted`. |
| Screenshot | The exact digest must receive independent gate approval and become `promoted`; `awaiting_human_approval` blocks a report that requires the screenshot. |
| Process dump | Dump bytes never enter the report. Only gate-approved hash/size/quarantine metadata may be referenced. |
| Rejected artifact or unexpected quarantine | Required evidence is unavailable; report creation fails closed. |

The report renderer reads no raw capture artifact. It receives an allowlist of promoted locators and
safe manifest fields from the redaction stage. It never follows source paths embedded in scenario
data or provisional observations.

### Failure separation

A gate failure does not change the provisional collector outcome. It blocks report promotion and
returns a stable redaction-stage failure code. This preserves the distinction between "what the
client did" and "whether its evidence is safe to promote."

The collector identity cannot satisfy screenshot approver identity. Missing, stale, mismatched, or
self-authored approval remains `awaiting_human_approval` or fails according to the gate contract;
the collector supplies no fallback.

## Report contract

A promotable report contains:

- scenario and run IDs;
- scenario and resolved-input digests;
- explicitly supplied model and client identity;
- the four-value outcome;
- ordered claim summaries with evidence digests;
- collector/detector IDs and contract versions;
- observation-window bounds;
- sanitized artifact locators;
- content-free redaction manifest locators and dispositions;
- process/config/dependency identities needed to assess real-dependency evidence; and
- stable value-free limitations or failure codes.

It excludes:

- raw artifact bodies;
- raw capture-root, source, user-profile, or Zed-log paths;
- environment mappings or secret inventory information;
- raw exception text;
- screenshots lacking matching approval;
- process dump bytes;
- policy constants or inferred redaction thresholds; and
- a claim of stability when the full observation window did not complete.

Report serialization is deterministic. `inspect` recomputes digests, verifies report-to-manifest
references, confirms that every referenced artifact has an eligible public gate disposition, and
prints no evidence body.

## Failure semantics and safety

- Scenario parse, unknown field, unknown adapter, missing binding, or unsafe path: reject before
  fixture mutation.
- Fixture digest mismatch: stop without overwrite.
- Precondition failure: do not launch the client; produce no client outcome.
- Collector failure before sufficient evidence: classify `indeterminate`.
- Required collector timeout: classify `indeterminate`; absence is not a negative claim.
- Correlation, sequence, clock, or digest conflict: invalidate affected claims and classify
  `indeterminate` when a determinate result depends on them.
- Process launch uses an explicit argument vector and `shell=False`.
- Raw evidence stays in an explicit private capture root until the separate gate invocation.
- Stage metadata is written atomically; a partial stage cannot claim completion.
- Raw external text is never executed, evaluated, imported, or promoted to scenario policy.
- Diagnostics use stable reason codes and content-free summaries rather than raw exception strings.
- Report write or final rename failure cannot leave a report that claims unpromoted evidence.

## Descriptive implementation surface

The implementation may refine file granularity while preserving these ownership boundaries:

| Surface | Responsibility |
|---|---|
| `tools/evidence_gather.py` | Sole executable entry point, subcommand parser, host registry wiring, gate invocation, and exit semantics. |
| `tools/evidence_gather_support/` | Non-entry-point host adapters for fixtures, preconditions, ACP/process collection, Zed logs, Windows capture, and report rendering. |
| `src/evidence_handoff/collector/models.py` | Portable scenario, binding, observation, claim, artifact, and result models. |
| `src/evidence_handoff/collector/scenarios.py` | Strict TOML/JSON parsing and validation; no execution. |
| `src/evidence_handoff/collector/protocols.py` | Collector, detector, clock, and artifact-store protocols. |
| `src/evidence_handoff/collector/pipeline.py` | Deterministic stage composition and digest-bound run transitions. |
| `src/evidence_handoff/collector/classification.py` | Four-value outcome reducer and decision-table enforcement. |
| `src/evidence_handoff/collector/bundles.py` | Raw-bundle and provisional-result schemas. |
| `src/evidence_handoff/redaction/models.py` | Gate-owned public contracts consumed only by the separate redaction stage. |
| `src/optimus/acp/evidence_redaction_adapter.py` | Host conversion into gate-owned portable runtime inputs. |

No path in this table creates a new console script, package entry point, wrapper command, or
feature-bearing executable name.

## Verification design

### Unit evidence

- Strict scenario parsing accepts equivalent TOML/JSON and rejects unknown fields, executable
  constructs, dynamic imports, shell fragments, environment expansion, and unknown adapters.
- Model-aware scenarios fail without an explicit model binding; scans find no model literal or
  model default in implementation, shipped scenarios, CLI options, or configuration.
- Every destination-bearing subcommand fails without its explicit absolute target.
- The CLI has no implicit collection-plus-redaction command.
- `tools/evidence_gather_support` contains no `__main__`, console-script registration, or executable
  wrapper. An AST ownership test permits sibling imports within the support package and proves that
  only `tools/evidence_gather.py` imports support modules from outside the package.
- AST boundary tests scan every `src/evidence_handoff` module and reject imports rooted at
  `optimus`, `optimus_gateway`, or `tools`, including dynamic-import and relative-import escape
  hatches.
- Collector-specific AST tests reject `optimus_security` imports under
  `evidence_handoff.collector`.
- Redaction-binding tests import the four gate contracts only from
  `evidence_handoff.redaction.models` and fail on policy-internal or entropy-constant imports.
- Contract sweep tests make a gate public-contract rename fail collector fixtures and call sites in
  the same changeset.
- Collector composition preserves deterministic sequence and cannot overwrite another collector's
  evidence.
- Detector tests reject foreign run IDs, invalid ordering, duplicate sequence numbers, clock
  regressions, digest mismatches, and unbounded claims.
- Table-driven classifier tests cover all four outcomes, precedence, boundary timestamps,
  incomplete observation windows, missing collectors, contradictory claims, and ambiguous
  multi-instance crashes.
- Completion tests accept only the correlated `server.py:process_request:exit` event and prove it
  does not imply UI rendering.
- DWM capture tests prove a screenshot alone does not create a render claim.
- Crash tests ignore pre-run Zed artifacts and require correlated new evidence.
- Prompt-injection adapter IDs are absent from portable models and the host allowlist; configuration
  cannot enable them.
- Report tests reject raw locators, unsafe dispositions, unapproved screenshots, dump bodies,
  policy constants, raw exceptions, and non-deterministic serialization.

Fakes are appropriate for these bounded unit contracts only.

### Portable integration evidence

- Real filesystem fixtures exercise preparation idempotence, digest mismatch, raw-bundle writes,
  atomic stage metadata, resumed subcommands, and explicit-target enforcement.
- Real append-only NDJSON files exercise offset capture, ordered extraction, partial final writes,
  malformed interiors, rotation/replacement, and foreign suffix rejection.
- An isolated import smoke blocks `optimus`, `optimus_gateway`, `tools`, and
  `optimus_security` while importing `evidence_handoff.collector`.
- The full portable suite runs on Windows and an actual alternate-OS environment. Windows-path
  fixtures remain data on the alternate OS; real DWM and Zed claims still require Windows.

### Real-dependency evidence belongs to the introducing task

An implementation plan must place each proof in the task that first touches the real dependency:

| Introduced surface | Required same-task proof |
|---|---|
| ACP completion collection | Real agent process driven by independently authored `acpx`, with the real correlated completion event. |
| Zed crash-log collection | Real Zed 1.13.1 instance and real `%LOCALAPPDATA%\Zed\logs\` changes, including pre-run exclusion. |
| DWM physical-bounds capture | Real Windows DWM bounds and a captured real client window, with DPI and process/window identity evidence. |
| Optimus gate runtime adaptation | Real canonical resolver and OS credential-store path without writing or deleting credentials; no value crosses into evidence. |
| Redaction composition | Real public gate, real filesystem staging/promotion, real artifact dispositions, and a raw-output canary scan. |
| UIA/SendInput investigation | Real UIA/SendInput against Zed 1.13.1 in the task that introduces that probe. |
| `zed://` investigation | Real scheme invocation and observed Zed behavior in the task that introduces that probe. |
| Hermetic user-data investigation | Real isolated `--user-data-dir` instances and custody/isolation evidence in the task that introduces that probe. |

A later closing task may audit, index, and relay evidence already produced. It may not be the first
task to run any real dependency, replace missing same-task proof, or convert fake-based confidence
into a real-dependency claim.

### Cross-component integration evidence

- A declarative scenario drives fixture preparation, precondition checks, real ACP collection,
  NDJSON extraction, completion detection, Zed-log watching, DWM capture, deterministic
  classification, and a separate redaction invocation.
- `collect` and `classify` leave no promotable report.
- `redact` consumes public gate contracts and creates a report only from eligible sanitized
  artifacts and content-free metadata.
- A render followed by a real correlated Zed crash produces `rendered_then_crashed`.
- A correlated Zed crash before any positive render claim produces `client_crashed`.
- A completed response with a positive render claim and a fully observed stable interval produces
  `rendered_stable`.
- Missing semantic render evidence, incomplete observation, collector failure, or ambiguous
  multi-instance crash evidence produces `indeterminate`.
- A screenshot remains unavailable to a required report until an independent matching approval
  reaches public disposition `promoted`.
- A process dump contributes only safe hash/size/quarantine metadata.

### Repository gates

- The evidence/handoff pool lists this product-owned design.
- `PRODUCT_OWNED_DOCS` contains the same exact allowlist and every listed file exists.
- The Optimus open-work pool remains unchanged.
- A repository scan finds no retired package or feature names in new product surfaces.
- A manual scan finds no scheduling number in this design.
- Narrow documentation, collector, redaction-integration, and import-boundary tests pass.
- The complete unit suite and aggregate production-code coverage gate pass when implementation
  adds collector code.
- Ruff, the secret scanner, dependency-lock checks, and `git diff --check` pass.
- Final review inspects the actual diff and named evidence artifacts rather than relying on task
  narration.

## Design completion criteria

- `tools/evidence_gather.py` is the only executable collector surface.
- Support modules cannot become entry points or independent consumers.
- Scenarios are strict data and select only allowlisted typed adapters.
- Model values and all persistence/report targets are explicit, with no defaults.
- Portable collector code imports neither deployable package, project tooling, nor
  `optimus_security`.
- Fixture, precondition, NDJSON, completion, Zed-log, and DWM capabilities remain settled
  implementation inputs.
- Collectors gather; detectors make bounded claims; the classifier alone chooses one of the four
  outcomes.
- Stability requires a complete observation interval and positive evidence; missing evidence never
  becomes a positive claim.
- Automated Zed prompt injection is structurally absent until all three named real investigations
  pass review.
- Redaction is a separately invoked final stage bound only to the gate-owned public interface.
- The collector copies no entropy or other redaction-policy internals.
- Raw artifacts never enter a promotable report.
- Every real dependency is proven in the implementation task that first introduces its use.
- Documentation ownership remains exact and the Optimus backlog remains untouched.
