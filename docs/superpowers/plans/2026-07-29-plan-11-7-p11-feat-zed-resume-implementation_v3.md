# Plan 11.7 `P11-FEAT-ZED-RESUME` Implementation Plan v3

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Plan 11.7 v2 Task 0 with a pipeline-native, two-layer current-Zed evidence gate,
then implement the unchanged v2 durable `session/load` design only after that gate and the Plan 11.25
architectural reconciliation are independently accepted.

**Architecture:** Preserve v2 Tasks 1-11 without reinterpretation. Replace only Task 0 with one
scenario-driven `prepare -> collect -> classify -> redact` run that produces a private raw manifest
containing exact paths and a committed sanitized manifest containing opaque aliases, content hashes,
and keyed path commitments. A deterministic reducer derives every count, request identity, binding,
hash, and Lifecycle A-prime classification from custody-bound artifacts; no human-authored manifest
field may authorize the gate.

**Tech Stack:** Python 3.14, ACP v1 vendored schema, asyncio, Redis 8 with TimeSeries, redis-py async
client, Pydantic, pytest/pytest-asyncio, Ruff, current Zed for Windows, SQLite offline inspection,
Git, HMAC-SHA-256, and the repository `evidence_gather.py` collection/redaction pipeline.

**Spec:** This v3 file is the current Plan 11.7 execution authority once approved. It incorporates
Tasks 1-11 and the production contracts from
`docs/superpowers/plans/archive/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation_v2.md` unchanged by
reference and replaces v2 Task 0, its current-client manifest schemas, its report paths, and its
Task-0 verifier commands. The accepted architectural rulings and review history are recorded in
`D:\Projects\Development\Python\optimus-agent-handoff\CURRENT.md`.

## Global Constraints

- Never edit, re-check, rename, or normalize the v1 plan, the three frozen amendments, or the
  approved v2 plan. Verify their pinned bytes read-only.
- This plan does not authorize a live Zed launch, evidence promotion, paid model call, push, merge,
  or history rewrite. Each still requires its existing operator authority.
- The private raw manifest is never staged. The committed verifier accepts only the sanitized v3
  schema and must run successfully with no private directory available.
- Exact paths are private evidence. A plain, unsalted hash of a raw path is forbidden because it is
  both representation-sensitive and dictionary-guessable.
- Every live-derived field must be computed from one verified `CollectionBatch` family and its
  digest-bound artifacts. CLI values may identify inputs but may not supply observed counts,
  classifications, request IDs, response hashes, module lists, or database results.
- Real Zed remains the ACP client for Task 0 and Task 10. Project-authored clients and `acpx` may not
  substitute for the Zed tier.
- A positive Lifecycle A-prime reachability signal is a non-waivable terminal stop even when another
  field is inconsistent, missing, unredacted, or not yet promoted.
- Production replay remains unchanged: a stored non-empty session emits every required
  `session/update` through `DedicatedOutboundWriter` before successful `{}`; production never
  returns successful `{}` for a zero-entry ledger.

---

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---:|---|---|
| credentials/authority | Operator approves this forward-only v3 as current Plan 11.7 authority | no | Operator | merely unauthorized; this draft does not approve itself. |
| code/state | At planning time `origin/main == 3e9b8fa26e00d3c90d0b9ea4182bc67f13a3de47`; v2 and all frozen historical files are byte-identical to their approved bytes | yes | Task 0 implementer and independent reviewer | N/A; branch from the then-latest `origin/main`, record any advance, and keep the isolated live-probe source pinned separately as specified below. |
| code/state | The isolated Optimus source baseline `3e9b8fa` is source-equivalent to v2's planned `cd7014d894576483fe4d2f9d59d2ecbb2c67ee03` across `src/` and `tools/` before the authorized temporary patch | yes | Task 0 collector and offline verifier | N/A; the observed diff is documentation-only, but v3 requires the equivalence digest to be recomputed. |
| code/state | Candidate v2 verifier repairs through `fc80403060f578986c287686c27d935a8043dc5a` exist on `agent/claude/plan-11-7-v2-task0` | yes | Task 0 implementer | N/A; they are useful candidate machinery, not accepted or promoted Task 0 evidence. |
| code/state | A pipeline-native Plan 11.7 collector, two-layer manifest contract, redaction attestation, and v3 offline verifier exist | no | Task 0 implementer | genuinely absent but buildable now; Tasks 0.1-0.4 schedule them. |
| code/state | The 2026-08-22 and 2026-08-23 raw artifacts have committed sanitized derivatives | no | Task 0 evidence custodian | merely unauthorized promotion; they remain private, untracked, and non-authorizing. |
| code/state | Plan 11.25 architecture reconciliation is independently accepted | no | Task 0 implementer and independent reviewer | genuinely absent but buildable now; Task 0.8 owns it. |
| services | SQLite inspection tools are available; Redis and Gateway are reachable for Tasks 9-10 | unknown | Operator owns machine state | genuinely hard until preflight records exact availability; Task 0 requires SQLite but no Redis or paid Gateway call. |
| tooling/binaries | Exact current Zed executable/version/revision, exact `optimus-agent` trampoline, and Git are available | unknown | Operator owns machine state; Task 0 preflight verifies | genuinely hard version-sensitive external state until measured. |
| credentials/authority | Bounded live Zed launch, GUI ceremony, and redaction/promotion are approved | no | Operator | merely unauthorized; Task 0.5 stops before launch without an approval identifier. |
| human interaction | Operator can create/reopen the two hermetic Zed threads and perform clean shutdowns | no | Operator performs or explicitly delegates | merely unauthorized; the collector records checkpoints but cannot invent GUI actions. |
| cost | Task 0 load-only stub requires no paid call; later Tasks 8-10 may require paid Gateway calls | no | Operator | merely unauthorized for the later paid tiers; not a Task 0 tooling blocker. |

## Authority and Forward-Only Supersession

Approval of v3 is a forward-only authority event. It does not rewrite historical evidence or claim
that any rejected or unsealed run was accepted.

| Historical document, item, or run | v3 disposition |
|---|---|
| v1 Plan 11.7 and its three dated amendments | Preserved unchanged as historical approval/evidence. Their current-execution supersession remains exactly as v2 states. |
| Plan 11.7 v2 | Preserved unchanged. Its production design and Tasks 1-11 remain incorporated by reference; its Task 0 and current-client evidence schemas are superseded. |
| `P11-FU-11` | **Retired — superseded premise.** Never Closed and never represented as completed. |
| `P11-FU-1` / `P11-FEAT-ZED-RESUME` | Remain open until all incorporated v2 Tasks 1-11 and v3 evidence gates pass. |
| 2026-08-22 matched A/B probe | Supporting current-client evidence only after redaction; W1 remains “most likely,” never demonstrated. It cannot authorize Task 0. |
| 2026-08-23 ad-hoc and corrected Lifecycle runs | Preserved private evidence of defects and process learning. They are non-authorizing because collection was not pipeline-native. |
| Candidate commits through `fc80403` | Forward implementation history to inspect and reuse. Their green tests do not satisfy v3 Task 0. |

When this file and v2 disagree about Task 0, schema identity, report location, exact-path handling,
collector ownership, reducer precedence, or Task-0 verification commands, v3 controls. For all
production behavior and Tasks 1-11, v2 controls without reinterpretation.

The implementation baseline fields have distinct meanings:

- `planned_baseline` is immutable `cd7014d894576483fe4d2f9d59d2ecbb2c67ee03`.
- `ratified_execution_baseline` is immutable
  `3e9b8fa26e00d3c90d0b9ea4182bc67f13a3de47` for the Task 0 rerun.
- `actual_execution_head` is measured from the isolated source and must equal the ratified baseline.
- `baseline_equivalence_diff_sha256` hashes the exact `git diff cd7014d..3e9b8fa -- src tools`
  bytes. The verifier recomputes it; recording three plausible-looking hashes is insufficient.

## Frozen Replay and Architecture Requirements

The following v2 requirement remains verbatim and is not open to Task-0 implementation choice:

> For a stored non-empty session, `session/load` MUST emit every required replay `session/update`
> through the authoritative writer before returning successful `{}`. A successful zero-entry replay is
> forbidden unless an explicit empty-session policy proves that Zed retains a resumable binding. Zed
> evidence must verify the database binding remains non-null across clean shutdown and reopen.

V3 retains v2's provisional production policy: zero-entry ledgers return `INVALID_REQUEST`, emit no
replay, and never return `{}`. Tasks 1-11 remain blocked unless Task 0 independently accepts
`ZERO_ENTRY_UNREACHABLE`. A Task 0 load-only stub may return `{}` only as an isolated reachability
probe; its observed binding loss is evidence that production must not copy that behavior.

`ConversationState`, `TurnControl`, `NoticeControl`, settlement, `DedicatedOutboundWriter`,
`AcpDuplexAdapter`, `AcpSpecSession`, `RedisRuntime`, and `ClientMcpDisposition` remain the unique
owners listed in v2. V3 authorizes no second conversation model, writer, lifecycle controller,
session adapter, or Redis pool.

## Two-Layer Evidence Contract

### Private raw manifest

The private schema is `plan-11-7-v3-current-client-raw-v1`. It is written only beneath
`tmp/plan-11-7-v3-current-client-gate/<run-id>/` and must include:

- scenario ID/digest, run ID, raw-bundle digest, provisional-classification digest, collector
  version, wall/monotonic bounds, and operator approval ID;
- exact raw and canonical Zed executable paths, binary SHA-256, CLI/app versions, and source revision;
- exact raw and canonical trampoline path, executable SHA-256, contents SHA-256, and literal launcher
  bytes as a private artifact;
- every file-backed imported module whose resolved file is inside the isolated source root, captured
  from the running agent after bootstrap and before the first ACP request; each entry carries module
  name, exact raw/canonical path, file SHA-256, and source-relative path;
- planned, ratified, and actual Git baselines; baseline-equivalence, tracked-diff, untracked-source,
  and normal-source before/after digests;
- exact private profile/workspace/database paths for both arms, SQLite main/WAL/SHM hashes at each
  custody checkpoint, thread BLOB identity, and bindings derived only from read-only copies taken
  after clean shutdown;
- complete ordered initialize/session-new/session-load/session-update observations, JSON-RPC request
  IDs, `sessionId` parameters, and the exact response-result bytes whose SHA-256 must equal the hash
  of `b"{}"` for the prompted load-only arm;
- cleanup targets and post-cleanup existence checks; and
- a randomly generated 32-byte path-commitment key held in private custody and never serialized into
  a promotable artifact.

Unknown keys, coercible types, duplicate semantic roles, missing required module entries, artifact
hash mismatches, cross-run IDs, or observations outside the run window fail raw-manifest derivation.

### Canonical path identity and commitment

`canonicalize_windows_path_identity(path)` is versioned as `windows-path-v1` and performs, in order:

1. require an existing absolute path and resolve it strictly;
2. normalize Unicode to NFC;
3. normalize separators to `\\`, remove redundant `.` components, and uppercase only the drive letter;
4. preserve the remaining path casing and do not expand environment variables, aliases, or symlinks
   after strict resolution; and
5. UTF-8 encode `b"windows-path-v1\\0" + canonical_path`.

The committed path commitment is
`HMAC-SHA-256(run_private_key, b"plan-11-7-v3:path:v1\\0" + canonical_bytes)`. Aliases are semantic,
run-local identifiers such as `zed-executable-01` or `module-optimus-acp-spec`; they contain no user,
drive, profile, workspace, or repository fragments. The same canonical path within one run must yield
the same commitment; different roles retain distinct aliases. The private reviewer recomputes every
commitment before promotion. The committed offline verifier checks format and cross-file agreement but
does not claim it can reconstruct a private path without the private key.

### Committed sanitized manifest and attestation

The committed schema is `plan-11-7-v3-current-client-sanitized-v1`. It contains no raw or canonical
absolute path. Each path-bearing entry contains only semantic role, opaque alias, keyed commitment,
source-relative path where safe, content SHA-256, and size.

`redaction-attestation.json` uses schema
`plan-11-7-v3-current-client-redaction-attestation-v1` and binds:

- run/scenario identity;
- raw manifest SHA-256 and raw bundle SHA-256;
- sanitized manifest SHA-256;
- the ordered role/alias/path-commitment/content-hash mapping;
- every promoted artifact locator and digest;
- the redaction report digest; and
- independent reviewer identity plus acceptance timestamp, without embedding the private key or path.

The redaction adapter creates the sanitized manifest and attestation from the verified raw manifest.
They cannot be caller-authored inputs. Raw SQLite files, relay bytes, profiles, logs, launcher bytes,
and path keys remain private unless the existing redaction gate independently marks a derivative
eligible.

## Lifecycle Reducer Contract

The reducer returns one primary disposition plus ordered secondary reason codes. Primary precedence is:

1. `ZERO_ENTRY_REACHABLE_STOP` when any independent A-prime reopen signal is positive: pre-reopen
   binding non-null, reopen `session/load` count greater than zero, or any captured reopen load ID.
2. Schema/custody invalidity, including classification-label mismatch, cross-run evidence, unknown
   fields, hash mismatch, missing artifact, incomplete module closure, or impossible chronology.
3. A-prime single-thread choreography invalidity.
4. Prompted-arm protocol/binding invalidity.
5. Source/profile/cleanup/redaction invalidity.
6. `ACCEPTED_CURRENT_CLIENT_GATE` only when every earlier predicate is false.

The A-prime valid choreography is exact:

- first launch: one initialize, one session/new, zero session/load, one fresh profile/workspace;
- clean shutdown and closed-database copy: exact row exists and pre-reopen binding is null;
- reopen: one initialize, one session/new, zero session/load, zero load IDs; and
- second clean shutdown/copy: binding remains null and both database aliases/commitments identify the
  same A-prime database.

Any positive reopen load signal latches the stop before count/list inconsistency, duplicate IDs,
unknown fields, pending redaction, or cleanup failure. Those defects remain secondary reason codes and
must not replace the stop. A first-launch load does not prove the targeted reopen reachability; it is
`INVALID_A_PRIME_FIRST_LAUNCH_SEQUENCE`, because it contradicts the fresh-profile ceremony.

The prompted arm is valid only when Lifecycle A creates exactly one prompted session and its closed
database binds the thread to that session; Lifecycle B sends one initialize, exactly one distinct
`session/load` for that session ID, zero session/new, zero replay updates, and receives exact `{}`
result bytes; after clean shutdown the copied database binding is null.

## File and Responsibility Map

| Path | Responsibility |
|---|---|
| `tools/evidence_gather_support/plan117_current_client_contract.py` | V3 raw/sanitized/attestation DTOs, canonical serialization, path commitments, deterministic reducer, and cross-field invariants. No process launch or filesystem mutation. |
| `tools/evidence_gather_support/plan117_current_client.py` | Windows/Zed host adapter: isolated source preparation, operator checkpoints, launch observation, module closure capture, clean-shutdown custody, and one `CollectionBatch`. |
| `tools/evidence_gather_support/registry.py` | Allowlist `plan117_current_client_collector`; no generic arbitrary-artifact importer. |
| `tools/evidence_gather_support/redaction.py` | Dispatch the verified raw gate manifest through the existing redaction boundary and create the sanitized manifest/attestation. |
| `tools/evidence_gather.py` | Route the v3 scenario through existing `validate`, `prepare`, `check`, `collect`, `classify`, `redact`, and `inspect` commands. Do not add a second CLI. |
| `tools/probe_p11_zed_session_load.py` | Existing isolated-copy, patch, trampoline, trace, and SQLite primitives. It must not remain the owner of the v3 manifest contract. |
| `tools/verify_plan117_v3_current_client_evidence.py` | Offline verifier for committed sanitized bundles only; strict keys, leakage scan, rehash, reducer, and attestation checks. |
| `tests/fixtures/evidence/scenarios/plan117-current-client-gate-v3.toml` | Exact registered client/fixture/collector/detector selections and required bindings for both arms. |
| `tests/unit/tools/test_plan117_current_client_contract.py` | Raw/sanitized schemas, path commitments, reducer precedence, chronology, completeness, and derivation tests. |
| `tests/unit/tools/test_plan117_current_client_collector.py` | Deterministic fake-process unit tests for the orchestration state machine; fakes never satisfy the live tier. |
| `tests/unit/tools/test_verify_plan117_v3_current_client_evidence.py` | Sanitized verifier omission/tamper/leakage/file-rehash/attestation tests. |
| `tests/unit/tools/test_evidence_gather.py` | CLI scenario dispatch, registry, raw-bundle, classify-binding, redact, and inspect tests. |
| `reports/plan-11-7-v3-current-client-gate/` | Committed sanitized manifest, attestation, report, promoted derivatives, and offline-verifier result. |
| `reports/plan-11-7-v3-architecture-reconciliation.md` | Independently accepted Plan 11.25 ownership map. |

## Task 0: Replace the current-client gate and reconcile current architecture

### Task 0.1: Freeze v3 authority and write the schema contracts RED

**Files:**

- Create: `tools/evidence_gather_support/plan117_current_client_contract.py`
- Create: `tests/unit/tools/test_plan117_current_client_contract.py`
- Modify: living backlog/roadmap and `tests/unit/docs/test_open_work_pool_hygiene.py`
- Do not modify: v1, the three amendments, or v2

**Interfaces:** Produces `Plan117RawManifest`, `Plan117SanitizedManifest`,
`Plan117RedactionAttestation`, `GateVerificationResult`, and the three exact schema constants above.

- [ ] **Step 1: Verify authority and historical bytes.** Record `origin/main`, v1/v2/amendment
  digests, candidate-branch HEAD, clean status, and the exact diff from planned to ratified baseline.
  Fail before edits if any frozen byte differs.
- [ ] **Step 2: Write RED exact-schema tests.** Require every field in the two-layer contract, reject
  unknown keys recursively, reject coercible JSON types, reject malformed hashes/commitments, and
  prove raw-path fields are absent from the sanitized type.
- [ ] **Step 3: Write RED reducer tests.** Include both masking constructions from the second Codex
  checkpoint, first-launch load/count anomalies, 99 initialize/new counts, cross-arm reuse, mismatched
  aliases/commitments, missing module closure entries, and declared-vs-derived classification.
- [ ] **Step 4: Run RED.** Run the new contract test file alone. Expected: imports or assertions fail
  because the v3 contract does not yet exist.
- [ ] **Step 5: Implement only pure contracts and reducer.** No path reads, process launches, SQLite,
  or redaction are permitted in this file. `reduce_gate(raw)` must calculate the primary disposition
  and all secondary reasons from raw observations.
- [ ] **Step 6: Run GREEN, Ruff, and diff integrity.** Run the contract tests, Ruff on the new files,
  `git diff --check`, then commit this independently reviewable unit.

### Task 0.2: Implement private path commitments and raw-to-sanitized derivation

**Files:**

- Modify: `tools/evidence_gather_support/plan117_current_client_contract.py`
- Modify: `tests/unit/tools/test_plan117_current_client_contract.py`

**Interfaces:** Produces:

```python
def canonicalize_windows_path_identity(path: Path) -> bytes: ...
def commit_private_path(path: Path, *, run_key: bytes) -> str: ...
def derive_sanitized_manifest(
    raw: Plan117RawManifest,
    *,
    run_key: bytes,
    promoted_artifacts: Sequence[CapturedArtifact],
    redaction_report_sha256: str,
) -> tuple[Plan117SanitizedManifest, Plan117RedactionAttestation]: ...
```

- [ ] **Step 1: Write RED canonicalization vectors.** Pin drive-letter handling, separators, Unicode
  NFC, strict resolution, same-run equality, differing-path inequality, a 32-byte key requirement,
  and deterministic HMAC output for fixed fixtures.
- [ ] **Step 2: Write RED privacy/linkage tests.** Prove raw paths and key bytes never appear in
  sanitized JSON, aliases contain no path fragments, every sanitized role maps exactly once to a raw
  role, and changing any raw/sanitized/artifact/report digest breaks attestation validation.
- [ ] **Step 3: Run RED, implement minimally, then GREEN.** Use `hmac.compare_digest` for commitment
  comparisons. Never persist the private key through the sanitizer.
- [ ] **Step 4: Run focused tests, Ruff, secret/path scans, and `git diff --check`; commit.**

### Task 0.3: Build the pipeline-native current-client collector

**Files:**

- Create: `tools/evidence_gather_support/plan117_current_client.py`
- Create: `tests/unit/tools/test_plan117_current_client_collector.py`
- Modify: `tools/evidence_gather_support/registry.py`
- Modify: `tools/evidence_gather.py`
- Modify: `tests/unit/tools/test_evidence_gather.py`
- Create: `tests/fixtures/evidence/scenarios/plan117-current-client-gate-v3.toml`
- Reuse, modify only when RED proves necessary: `tools/probe_p11_zed_session_load.py`

**Interfaces:** Produces:

```python
def collect_plan117_current_client_gate(
    *,
    context: RunContext,
    scenario: Scenario,
    inputs: Plan117CurrentClientInputs,
    operator: Plan117OperatorCheckpoint,
) -> CollectionBatch: ...

def build_plan117_raw_manifest(
    *,
    context: RunContext,
    batches: Sequence[CollectionBatch],
    provisional_result_path: Path,
) -> Plan117RawManifest: ...
```

`build_plan117_raw_manifest` is the sole manifest-producing function. It accepts no observed counts,
IDs, bindings, module lists, or hashes from a human or CLI.

- [ ] **Step 1: Write RED registry/scenario tests.** The v3 scenario selects real Zed, a hermetic
  fixture, the new collector, and existing custody stages. An unregistered adapter, wrong contract
  version, missing live approval ID, or arbitrary-artifact adapter fails before launch.
- [ ] **Step 2: Write RED state-machine tests.** With fake unit-tier process/checkpoint adapters,
  cover prepare, A-prime first launch, closed DB copy, reopen, second copy, prompted Lifecycle A,
  pre-B copy, Lifecycle B, post-B copy, cleanup, and terminal abort. Every transition consumes the
  prior transition token and emits ordered observations.
- [ ] **Step 3: Write RED derivation tests.** Assemble synthetic `CollectionBatch` artifacts and prove
  the builder independently rehashes files, derives counts/IDs/response digest/bindings, enumerates
  every imported module beneath the isolated root, binds scenario/run/provisional digests, and rejects
  a caller-supplied replacement value.
- [ ] **Step 4: Write RED custody tests.** Require SQLite main/WAL/SHM copying after confirmed shutdown,
  read-only URI inspection, exact BLOB thread identity, no ambient profile, no live DB read, source
  before/after equality, and verified cleanup targets constrained beneath the run root.
- [ ] **Step 5: Run RED.** Run collector, evidence CLI, and existing probe tests. Expected: missing
  adapter/dispatch/derivation failures.
- [ ] **Step 6: Implement the adapter by composing existing proven primitives.** Do not duplicate
  isolated-copy patching, trampoline generation, or SQLite querying. Refactor only the minimal seam
  needed for the collector to receive structured observations rather than ad-hoc shell output.
- [ ] **Step 7: Make `evidence_gather.py collect` dispatch by the registered scenario collector.** The
  existing acpx/default scenarios remain byte-for-byte behavior-compatible. V3 writes one raw bundle;
  rerunning `collect` for the same run ID fails rather than merging two live runs.
- [ ] **Step 8: Bind `classify` without overloading its generic outcome.** The existing provisional
  classification remains a custody artifact; the v3 gate disposition is derived only by
  `build_plan117_raw_manifest`. Record and verify the provisional file digest and raw-bundle digest;
  never translate `rendered_stable` or generic `indeterminate` into gate acceptance.
- [ ] **Step 9: Run GREEN, the legacy evidence suite, existing probe suite, Ruff, and
  `git diff --check`; commit.**

### Task 0.4: Build redaction integration and the offline sanitized verifier

**Files:**

- Modify: `tools/evidence_gather_support/redaction.py`
- Modify: `tools/evidence_gather_support/reports.py`
- Create: `tools/verify_plan117_v3_current_client_evidence.py`
- Create: `tests/unit/tools/test_verify_plan117_v3_current_client_evidence.py`
- Modify: redaction/report/evidence CLI tests

**Interfaces:** The verifier accepts exactly:

```powershell
uv run --frozen python tools/verify_plan117_v3_current_client_evidence.py `
  --manifest reports/plan-11-7-v3-current-client-gate/manifest.json `
  --attestation reports/plan-11-7-v3-current-client-gate/redaction-attestation.json `
  --bundle-root reports/plan-11-7-v3-current-client-gate
```

- [ ] **Step 1: Write RED raw-to-sanitized pipeline tests.** Start from a verified raw bundle and
  manifest; run the real redaction adapter; require only eligible derivatives, sanitized manifest,
  attestation, and safe report output. Raw paths, private key, SQLite, relay bytes, and launcher bytes
  are absent unless separately sanitized and promoted.
- [ ] **Step 2: Write RED offline-verifier tamper tests.** Delete/rename/alter every committed
  artifact in turn; mutate file hashes, aliases, commitments, module count/order, scenario/run IDs,
  reducer fields, attestation digests, and report digest. Each mutation must fail from a copy with no
  private directory.
- [ ] **Step 3: Write RED leakage tests against raw JSON.** Unknown fields, unknown nested fields,
  mapping keys, values, absolute Windows/UNC paths, profile fragments, secret-shaped strings, and
  traversal locators fail before typed parsing. Error messages must not echo the leaked value.
- [ ] **Step 4: Implement redaction dispatch and strict verifier.** Rehash committed bytes instead of
  trusting `file_hashes`; require exact schema keys recursively; recompute sanitized classification;
  verify the attestation mapping and require the redaction report to promote every listed artifact.
- [ ] **Step 5: Run focused/legacy tests, Ruff, docs hygiene, and `git diff --check`; commit.**

### Task 0.5: Obtain the pre-live machinery acceptance

**Files:**

- Create and maintain privately: `docs/superpowers/reviews/plan-11-7-v3-review-checkpoints.md`
- No production or evidence mutation during review

**Interfaces:** Produces a reviewer verdict covering Tasks 0.1-0.4. It is not Task 0 acceptance.

- [ ] **Step 1: Freeze the review inputs.** Record exact commits, changed files, test commands/counts,
  scenario digest, schema constants, and candidate live command. Confirm the review log is gitignored.
- [ ] **Step 2: Independent reviewer re-runs omission/tamper/masking tests.** The reviewer must add at
  least one unknown-field attack, one raw-path attack, one missing-module attack, and both positive-
  reachability masking constructions without relying on implementer summaries.
- [ ] **Step 3: Review collector provenance end to end.** Trace each manifest field backward to one
  observation/artifact and forward to one sanitized field. Any hand-entered observed value rejects the
  checkpoint.
- [ ] **Step 4: Accept or reject explicitly.** No live run is authorized until the reviewer records
  machinery acceptance and the operator separately supplies the live approval ID.

### Task 0.6: Execute one pipeline-native live run

**Files:**

- Private only: `tmp/plan-11-7-v3-current-client-gate/<run-id>/`
- Do not write directly to `reports/`

**Interfaces:** Produces one immutable raw bundle and raw manifest containing both arms.

- [ ] **Step 1: Preflight exact provenance.** Verify Zed identity, daily trampoline target, branch,
  ratified baseline, isolated-source HEAD, allowed temporary patch digest, module-capture hook,
  scenario digest, empty run directory, profile separation, and source before digest. Record the live
  approval ID. Stop on any mismatch.
- [ ] **Step 2: Execute A-prime through the collector.** Fresh profile/workspace; no prompt or
  permission response; exact first-launch choreography; clean stop; copied SQLite triple; reopen same
  profile/thread; clean stop; second triple. If any positive reopen load signal appears, latch
  `ZERO_ENTRY_REACHABLE_STOP` and continue only the already-authorized prompted arm, cleanup, redaction,
  and sealing.
- [ ] **Step 3: Execute prompted A/B through the same collector run.** A second fresh profile creates
  one real prompted session and cleanly binds it. Reopen against the load-only stub, require exactly
  one load for the same session, zero new/replay, exact `{}`, then cleanly stop and capture the null
  binding consequence.
- [ ] **Step 4: Restore and prove custody.** Remove only collector-recorded throwaway roots, confirm
  nonexistence, recompute source/trampoline/import provenance, and require before/after equality. Do
  not touch the operator's daily profile or integration source.
- [ ] **Step 5: Run pipeline `classify` and derive the raw manifest.** The builder reopens verified
  artifacts read-only and computes the result; no manual JSON assembly or correction is allowed. A
  flawed run is preserved as flawed evidence and cannot be edited into validity.

### Task 0.7: Redact, promote, and verify from committed bytes

**Files:**

- Create: `reports/plan-11-7-v3-current-client-gate/manifest.json`
- Create: `reports/plan-11-7-v3-current-client-gate/redaction-attestation.json`
- Create: `reports/plan-11-7-v3-current-client-gate/report.md`
- Create: eligible sanitized derivatives beneath that directory

**Interfaces:** Produces the only Task 0 evidence eligible for independent acceptance.

- [ ] **Step 1: Private reviewer verifies path commitments.** Recompute canonical identities and every
  HMAC mapping with the private key, compare raw artifact hashes, and sign the redaction attestation.
- [ ] **Step 2: Run `evidence_gather.py redact`.** Use distinct capture, staging, quarantine, and
  sanitized roots. Copy to `reports/` only after every required derivative is promoted.
- [ ] **Step 3: Promote the 2026-08-22/earlier-2026-08-23 material separately.** If eligible, label it
  historical/supporting and preserve W1 as under-evidenced. It must not share the authorizing manifest
  or be counted as the v3 live run.
- [ ] **Step 4: Run the offline verifier with the private directory unavailable.** Then run focused
  contract, collector, verifier, legacy evidence, probe, docs-hygiene, Ruff, coverage, and diff gates.
- [ ] **Step 5: Tamper a copy and require failure.** At minimum alter one promoted byte, one module
  digest, one commitment, and one lifecycle count. Record commands and dispositions in the report.
- [ ] **Step 6: Commit sanitized evidence only.** Re-scan the staged set for raw paths, SQLite/WAL/SHM,
  relay bytes, private key material, credentials, profiles, and unapproved logs before commit.

### Task 0.8: Reconcile Plan 11.25 and obtain final independent acceptance

**Files:**

- Create: `reports/plan-11-7-v3-architecture-reconciliation.md`
- Modify: living backlog/roadmap only after evidence identities exist
- Do not modify: v1, amendments, or v2

**Interfaces:** Produces the two acceptances required before incorporated v2 Task 1 starts.

- [ ] **Step 1: Freeze exact architecture owners.** Record paths/symbols for `ConversationState`,
  `TurnControl`, `NoticeControl`, settlement, `DedicatedOutboundWriter`, `AcpDuplexAdapter`,
  `AcpSpecSession`, `RedisRuntime`, and `ClientMcpDisposition` at exact source HEAD.
- [ ] **Step 2: Run negative-existence searches.** Prove no second conversation model, writer,
  lifecycle controller, session adapter, or Redis pool would be introduced by incorporated v2
  Tasks 1-11. Map every v1 responsibility to its current owner.
- [ ] **Step 3: Independent reviewer verifies the committed evidence from scratch.** Clone/fresh-checkout
  verification must succeed without private data. Separately, the reviewer confirms the signed
  private-to-sanitized mapping was performed; the public verifier does not claim that authority.
- [ ] **Step 4: Apply the terminal decision.** `ZERO_ENTRY_REACHABLE_STOP` cannot be waived and blocks
  incorporated Tasks 1-11 pending another forward-only policy revision. Any invalid/indeterminate
  result requires a new clean run, never manifest repair. Only accepted `ZERO_ENTRY_UNREACHABLE` plus
  accepted architecture reconciliation unblocks Task 1.
- [ ] **Step 5: Update living status truthfully.** Preserve `P11-FU-11` as retired, keep W1
  under-evidenced, cite only committed sanitized artifacts, and record exact commits/reviewer verdicts.

## Incorporated Tasks 1-11

Tasks 1-11, their files, interfaces, test-first order, production condition/error table, durable
ledger, replay ordering, Redis lease/revision/TTL behavior, MCP re-disposition, live Redis/acpx tier,
real-Zed non-empty replay tier, release gates, and Definition of Done are incorporated unchanged from
v2. Apply these substitutions only:

| v2 reference | v3 controlling reference |
|---|---|
| v2 Task 0 acceptance | v3 Tasks 0.1-0.8 acceptance |
| `plan-11-7-v2-current-client-gate-v2` | `plan-11-7-v3-current-client-sanitized-v1` plus its attestation |
| `tools/verify_plan117_v2_current_client_evidence.py` for new evidence | `tools/verify_plan117_v3_current_client_evidence.py` |
| `reports/plan-11-7-v2-current-client-gate/` | `reports/plan-11-7-v3-current-client-gate/` |
| `reports/plan-11-7-v2-architecture-reconciliation.md` | `reports/plan-11-7-v3-architecture-reconciliation.md` |
| exact Task 0 source `cd7014d` | planned `cd7014d`, ratified/actual `3e9b8fa`, with verified source-equivalence digest |

No substitution changes production session/load behavior. If an implementer believes any other v2
Task 1-11 text conflicts with v3, stop and request review instead of improvising.

## Required Verification Matrix

Before the pre-live checkpoint:

```powershell
uv run --frozen pytest tests/unit/tools/test_plan117_current_client_contract.py -q
uv run --frozen pytest tests/unit/tools/test_plan117_current_client_collector.py -q
uv run --frozen pytest tests/unit/tools/test_verify_plan117_v3_current_client_evidence.py -q
uv run --frozen pytest tests/unit/tools/test_evidence_gather.py tests/unit/tools/test_probe_p11_zed_session_load.py -q
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
uv run --frozen ruff check tools/evidence_gather.py tools/evidence_gather_support tools/probe_p11_zed_session_load.py tools/verify_plan117_v3_current_client_evidence.py tests/unit/tools
git diff --check
```

After sanitized evidence is committed, repeat the matrix and additionally run:

```powershell
uv run --frozen python tools/verify_plan117_v3_current_client_evidence.py --manifest reports/plan-11-7-v3-current-client-gate/manifest.json --attestation reports/plan-11-7-v3-current-client-gate/redaction-attestation.json --bundle-root reports/plan-11-7-v3-current-client-gate
uv run --frozen pytest --cov=src/optimus --cov=src/optimus_security --cov-report=term-missing --cov-fail-under=80
git diff --check
```

The report records exact commands, exit codes, test counts, tool versions, and committed artifact
digests. “Tests passed” without those identities is not acceptance evidence.

## Definition of Done

- V3 is approved as current authority; v1, amendments, and v2 remain byte-identical.
- Candidate verifier repairs are either incorporated with preserved history or superseded by tested
  v3 equivalents; no rejected manifest is silently repaired.
- One pipeline-native live run produces one immutable raw bundle and private exact-path manifest.
- The redaction adapter, not a human, produces the sanitized manifest and attestation.
- The committed bundle contains no raw paths, path key, SQLite/WAL/SHM, raw relay bytes, credentials,
  profiles, or unapproved logs.
- Offline verification rehashes every committed artifact and passes with no private directory.
- A-prime terminal reachability cannot be masked by schema, consistency, cleanup, or redaction defects.
- A-prime accepts only exact fresh-profile, single-thread `ZERO_ENTRY_UNREACHABLE` choreography.
- The prompted arm proves one load-only `session/load` for Lifecycle A's session, exact empty response,
  zero replay/new activity, and the post-shutdown null-binding consequence.
- Exact Zed/trampoline/module/source/database provenance is privately reviewed and cryptographically
  linked to committed sanitized roles without exposing raw paths.
- Plan 11.25 ownership reconciliation is independently accepted.
- Only after both acceptances may incorporated v2 Task 1 begin; Tasks 1-11 otherwise remain blocked.
- All later v2 production, acpx, real-Zed non-empty replay, release, documentation, and independent
  review requirements remain required for Plan 11.7 closure.

## Implementation Handoff

Start from a clean worktree/branch created from the then-latest `origin/main`, as required by repository
branch hygiene, and record its exact HEAD. Preserve the twelve candidate commits on
`agent/claude/plan-11-7-v2-task0`; integrate them by reviewed forward commits or cherry-picks without
squashing away the defect/correction history. An advance of `origin/main` does not silently advance the
live-probe source baseline: that isolated source remains ratified `3e9b8fa` unless another forward-only
plan revision changes it. Do not execute live Zed until Tasks 0.1-0.5 are complete and independently
accepted.

The operator's daily `optimus-agent` remains an editable install pointing at the integration worktree;
the collector must re-measure its exact target for every run. The Task 0 isolated source is built from
ratified `3e9b8fa`, receives only the approved load-only patch, and never modifies daily source.

After Task 0.8 acceptance, continue with v2 Task 1 under the substitutions above. Any conflict,
unavailable prerequisite, reachable stop, provenance ambiguity, raw leakage, or custody break halts
dependent work and is recorded as evidence rather than patched around.

## Plan Self-Review

- Required `## Prerequisites` table covers code/state, services, tooling, authority, human interaction,
  and cost with exact owner/disposition fields.
- V3 changes only Task 0/evidence authority and incorporates v2 production work unchanged.
- Raw exact paths and committed sanitized evidence are separate schemas with an explicit attestation.
- Unsalted raw-path hashing is forbidden; the canonicalization and keyed commitment algorithms are exact.
- The collector is pipeline-native, scenario-registered, and cannot import arbitrary artifacts.
- One deterministic builder derives the complete raw manifest; no human enters observed values.
- Reducer precedence latches every positive A-prime reachability signal before all invalidity checks.
- First-launch/reopen choreography is bounded and testable; “recorded separately” is not fail-open.
- Unknown fields and raw leakage fail before typed parsing, and verifier errors do not echo leaked data.
- File/module/artifact completeness is verified from bytes, not non-empty lists or asserted hashes.
- The pre-live checkpoint is mandatory and distinct from final Task 0 acceptance.
- Previous raw evidence remains supporting/non-authorizing and W1 remains under-evidenced.
- No placeholders, unowned deferrals, implementation-authority ambiguity, or live-action authorization
  are present.
