# EVIDENCE-HANDOFF-FEAT-REDACTION-GATE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to execute this plan task by task.

**Goal:** Implement the approved, fail-closed evidence-artifact redaction gate while
preserving the existing sanitizer behavior of all current callers and keeping the new
portable packages mechanically extractable.

**Architecture:** `optimus_security` remains the only rule engine and gains an explicit,
versioned evidence policy. `evidence_handoff` owns portable artifact dispatch,
bounded parsing, private staging, quarantine, approval, manifests, and atomic
promotion. `optimus.acp.evidence_redaction_adapter` is the only host adapter allowed
to receive Optimus launch objects. Existing callers keep the compatibility policy;
the evidence gate opts into the stronger policy explicitly.

**Tech Stack:** Python 3.14, standard-library JSON/streaming/filesystem/AST/crypto
primitives, Pillow 12.3.x for bounded image decode and canonical PNG re-encoding,
setuptools/uv, pytest/pytest-asyncio/pytest-cov, coverage.py, Ruff, detect-secrets,
real OS credential stores, real subprocess boundaries, and the independently authored
`acpx` client for live ACP evidence.

**Status:** Draft pending Claude and operator review. This document authorizes no
implementation, dependency mutation, commit, push, PR, or merge. Numbering is
assigned at pickup.

**Frozen design baseline:** Commit
`a1f51e2cc9ddc0e64c137bea2a6fbf2639f36c81`, file
`docs/superpowers/specs/2026-07-30-p11-feat-redaction-gate-design.md`, SHA-256
`86d8dd9e54c4767ff519b79a28fce2143491fb732e4317f02b33de0d2f06e459`.
The implementation worker must hash the committed blob, not the working-tree file.
Any mismatch blocks pickup.

---

## Global Constraints

- The frozen design is the contract. Do not edit it. If a task reveals a contradiction
  or missing architectural decision, stop and request a design amendment.
- The current authority set is
  `docs/Optimus-Cost-Agent-Architecture-v2.16.pdf`,
  `docs/Optimus-Cost-Agent-LLD-v2.39.pdf`, and
  `docs/Optimus-Cost-Agent-Test-Strategy-v1.5.pdf`. It requires at least 80%
  aggregate production coverage, secret redaction before export, real named
  dependencies for live claims, and independent `acpx` for ACP protocol evidence.
  Recheck their repository versions at pickup and stop on any conflict.
- Reference this work only as `EVIDENCE-HANDOFF-FEAT-REDACTION-GATE`. Do not assign or speculate
  about a scheduling number. Source packages, modules, settings, commands, schemas,
  and artifact names must remain descriptive and contain neither the Feature ID nor a
  scheduling number.
- `optimus_security.sanitization` is the sole implementation of exact-secret,
  structured-key, URI, path, email, known-PII, token-pattern, entropy, and contextual
  preservation rules. Evidence adapters may orchestrate those rules but may not copy
  or fork them.
- New PII, path, prefix, entropy, and contextual-preservation behavior is enabled only
  by the explicit `EVIDENCE_REDACTION_POLICY`. The default
  `COMPATIBILITY_SANITIZATION_POLICY` must reproduce every existing caller's current
  output and rule-count behavior. This per-call policy is required because the live
  tree has a 37-file behavioral sanitizer footprint; silently applying evidence rules
  globally would change telemetry, protocol errors, release reports, audit records,
  and Gateway responses without a reviewed migration.
- The grep perimeter is 40 files: 22 under `src`, four under `tools`, and 14 under
  `tests`. The 37-file behavioral baseline excludes the two package/export-only
  initializers and the launch-time secret-length-only source hit. Task 0 must record
  both sets and fail if either classification changes before implementation.
- `evidence_handoff` may import only the standard library, `optimus_security`, and
  the explicitly enumerated portable dependency root `PIL`. It must not import
  `optimus`, `optimus_gateway`, `tools`, launch types, Gateway service types, or use
  reflection/delayed imports to reach them.
- `optimus_security` remains standard-library-only. No Pillow import may cross into
  it.
- Pillow is pinned as `Pillow>=12.3,<13`. Pillow 12 is the first stable line with
  official Python 3.14 support. The gate accepts only PNG and JPEG input, converts to
  a new single-frame RGB/RGBA image, emits canonical PNG, omits `pnginfo`, EXIF, XMP,
  ICC, comments, and source filename, and treats decompression warnings as errors.
  Sources: [Python support](https://pillow.readthedocs.io/en/stable/installation/python-support.html),
  [platform support](https://pillow.readthedocs.io/en/stable/installation/platform-support.html),
  and [security guidance](https://pillow.readthedocs.io/en/stable/handbook/security.html).
- The entropy policy candidates are fixed for the Task 1 canary gate: token length
  24 through 256 characters, at least two of lowercase/uppercase/digit/symbol
  classes, Shannon entropy at least 4.0 bits per character, and recognized prefixes
  handled regardless of entropy. These values become the frozen
  `evidence-redaction-v1` contract only after the Task 1 canaries pass and Claude and
  the operator approve that task. If they do not pass exactly, stop; do not tune
  production constants ad hoc.
- Recognized prefix grammars are anchored and bounded:
  `sk-or-v1-`, `sk-ant-`, `sk-proj-`, `sk-`, `tvly-`, `AIza`, `ghp_`, and
  `github_pat_`, followed by 16 through 240 token characters. Adding or weakening a
  grammar requires review.
- Contextual free-text preservation accepts only these labels:
  `session_id`/`sessionId`, `run_id`/`runId`,
  `gateway_request_id`/`gatewayRequestId`, `model`, `provider`,
  `git_sha`/`gitSha`, and `artifact_sha256`/`sha256`. Accepted spellings are JSON,
  `key=value`, `key: value`, and the captured Rust-debug
  `label": String("value")` shape. Identifier values are 1 through 128 characters
  from `[A-Za-z0-9._:-]`; model/provider values additionally allow `/+`; git SHAs
  are 7 through 64 hexadecimal characters; artifact SHA-256 values are exactly 64
  hexadecimal characters. Unlabeled candidates are never preserved by shape alone.
- Use these artifact bounds unless a reviewed design amendment changes them:
  64 MiB input for JSON/NDJSON/text, 64 nesting levels, 1 MiB per decoded string or
  NDJSON physical record, 100,000 aggregate JSON collection members, 1 MiB maximum
  incomplete NDJSON tail, and 64 KiB stream reads. Image input is bounded at 32 MiB,
  10,000 pixels on either axis, 40,000,000 decoded pixels, and exactly one frame.
- Strict UTF-8 is required for JSON, NDJSON, and text. A crash tail cut within a
  multibyte character is invalid UTF-8 and must quarantine the whole artifact.
- No secret or known-PII value, fragment, per-value length, deterministic value hash,
  source absolute path, raw exception text, or raw/sanitized body may enter logs,
  errors, manifests, reports, snapshots, test IDs, or checkpoint records.
- Do not emit the existing session-scoped HMAC correlation tag in ordinary evidence
  manifests; this gate has no requirement to reveal whether two sensitive values
  match.
- There is no redaction-disable switch and no text fallback from a stricter artifact
  kind. Scoped deterministic PII handling must not be described as general
  natural-language de-identification.
- Raw controlled-capture stdout/stderr must stream directly through the gate. Do not
  write a raw transcript first. File-backed inputs must be under the approved
  temporary capture root or already in quarantine; successful processing moves the
  raw source into quarantine rather than leaving a second durable copy.
- A process dump is never parsed or promoted. It is recognized only as a Windows
  minidump (`MDMP`) or an ELF `ET_CORE` file, then retained/moved within quarantine
  and represented by content-free hash metadata.
- A screenshot cannot be promoted without independent, digest-bound human approval.
  The collector identity and approver identity must differ.
- Unit tests may use fakes. A test or evidence command named for an OS credential
  store, filesystem permission, Pillow decoder, process boundary, Gateway, ACP, or
  `acpx` must use that real dependency.
- Every task ends with its own narrow tests and real-dependency evidence appropriate
  to that task. Do not defer all integration/live evidence to the final task.
- Follow TDD: add the failing test, run it and record the expected failure, implement
  the minimum behavior, rerun green, then refactor without changing the contract.
- Before any task commit, run its narrow tests, `uv run --frozen ruff check .`, and
  `git diff --check`. A commit is allowed only after the operator relays the task
  output to Claude, Claude approves it, and the operator separately authorizes the
  commit. Stop after every approved commit; the next task requires a fresh pickup.
- Never push, open a PR, merge, delete a branch, or rewrite history under this plan.
- The reviewer-owned ignored checkpoint log is
  `docs/superpowers/reviews/p11-feat-redaction-gate-review-checkpoints.md`. Read its
  `Current State` first at every pickup and verify it against Git and on-disk
  evidence. Never stage it.

## Frozen public contracts and policy constants

The implementation may split private helpers differently, but these public contracts
and dependency directions are fixed:

```python
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from optimus_security.sanitization import PathAliasRule
from optimus_security.sensitive_values import SensitiveValueInventory


class ArtifactKind(StrEnum):
    JSON = "json"
    NDJSON = "ndjson"
    ACP_DEBUG_TRACE = "acp_debug_trace"
    TEXT = "text"
    SCREENSHOT = "screenshot"
    PROCESS_DUMP = "process_dump"


class Disposition(StrEnum):
    PROMOTED = "promoted"
    AWAITING_HUMAN_APPROVAL = "awaiting_human_approval"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


@dataclass(frozen=True)
class RedactionRuntimeInputs:
    sensitive_values: SensitiveValueInventory
    path_aliases: tuple[PathAliasRule, ...]
    temporary_capture_root: Path
    staging_root: Path
    quarantine_root: Path
    forbidden_persistence_roots: tuple[Path, ...]


@dataclass(frozen=True)
class ScreenshotApproval:
    staged_sha256: str
    approver_id: str
    collector_id: str
    approved_at: datetime
    rationale: str


@dataclass(frozen=True)
class RedactionRequest:
    source_path: Path
    destination_root: Path
    artifact_kind: ArtifactKind
    artifact_role: str
    runtime: RedactionRuntimeInputs
    screenshot_approval: ScreenshotApproval | None = None


@dataclass(frozen=True)
class RedactionGateResult:
    disposition: Disposition
    artifact_locator: str | None
    manifest_locator: str | None
    reason_code: str | None
```

`SensitiveValueInventory` is a slot-based, non-dataclass container with no `__dict__`,
value-suppressing `repr`/`str`, blocked pickle/copy serialization, longest-first
deduplication, source-class aggregate counts, and narrowly named
`secret_values_for_sanitizer()` and `pii_values_for_sanitizer()` accessors. It
validates all values against `MAX_SECRET_TEXT_CHARS` before a source artifact is
opened.

The shared sanitizer has this exact callable shape:
`sanitize_for_persistence(value: object, *, known_secrets: Sequence[str] = (),
known_pii: Sequence[str] = (), path_aliases: Sequence[PathAliasRule] = (),
policy: SanitizationPolicy = COMPATIBILITY_SANITIZATION_POLICY) ->
SanitizationResult`. `PathAliasRule` is a frozen standard-library-only contract in
`optimus_security.sanitization`; `evidence_handoff.redaction.models` re-exports it as
part of the portable gate boundary without defining a competing type.

`StreamingTextSanitizer` receives the same policy/PII/path inputs. The compatibility
policy enables only the existing exact-secret, URI-userinfo, bearer/header/assignment,
and secret-key rules. The evidence policy enables every compatibility rule plus the
approved prefix, entropy, email, known-PII, path, and contextual-preservation rules.

## File and responsibility map

### Production files to create

- `src/optimus_security/sensitive_values.py`: in-memory inventory and value-free
  errors/metadata.
- `src/evidence_handoff/__init__.py`: portable package declaration only.
- `src/evidence_handoff/redaction/__init__.py`: narrow public exports.
- `src/evidence_handoff/redaction/models.py`: portable request/result/approval/path
  contracts and bounds.
- `src/evidence_handoff/redaction/private_files.py`: private staging, restrictive
  permissions, containment, same-filesystem checks, and atomic rename.
- `src/evidence_handoff/redaction/text.py`: streaming adapter over the shared
  sanitizer.
- `src/evidence_handoff/redaction/structured.py`: bounded JSON/NDJSON parsing,
  prefix validation, normalized serialization, and joined-string scans.
- `src/evidence_handoff/redaction/images.py`: Pillow decode, canonical PNG re-encode,
  and approval binding.
- `src/evidence_handoff/redaction/quarantine.py`: source custody, dump recognition,
  streaming hash, and quarantine records.
- `src/evidence_handoff/redaction/manifest.py`: content-free manifest assembly and
  manifest canary scan.
- `src/evidence_handoff/redaction/gate.py`: dispatch, state machine, final scan, and
  promotion ordering.
- `src/optimus/acp/evidence_redaction_adapter.py`: Optimus-only launch/configuration
  adapter.
- `tools/run_redaction_gate_live_evidence.py`: explicit-output-root live runner using
  real launch resolution, process boundaries, and `acpx`; no default report target.

### Production/configuration files to modify

- `src/optimus_security/sanitization.py`: policy, shared rules, contextual
  preservation, final scanner, and streaming support.
- `src/optimus/telemetry/subjects.py`: remove its private secret-value regex and
  delegate the behavior to the shared compatibility policy.
- `pyproject.toml`: Pillow range, explicit test marker, and
  `src/evidence_handoff` coverage.
- `uv.lock`: reviewed Pillow resolution only.
- `.gitignore`: local live-capture workspace pattern if the evidence runner creates
  one below the repository.
- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`:
  living pickup/task/closure state and links only.

### Tests and fixtures to create

- `tests/fixtures/evidence/redaction_canaries.json`
- `tests/fixtures/evidence/zed_rust_debug_line.txt`
- `tests/unit/security/test_redaction_policy_calibration.py`
- `tests/unit/security/test_sensitive_values.py`
- `tests/unit/evidence/test_import_boundaries.py`
- `tests/unit/evidence/test_naming_boundaries.py`
- `tests/unit/evidence/test_models.py`
- `tests/unit/evidence/test_private_files.py`
- `tests/unit/evidence/test_text_redaction.py`
- `tests/unit/evidence/test_structured_redaction.py`
- `tests/unit/evidence/test_image_redaction.py`
- `tests/unit/evidence/test_quarantine.py`
- `tests/unit/evidence/test_manifest.py`
- `tests/unit/evidence/test_gate.py`
- `tests/unit/acp/test_evidence_redaction_adapter.py`
- `tests/unit/tools/test_run_redaction_gate_live_evidence.py`
- `tests/integration/evidence/test_runtime_inputs_live.py`
- `tests/integration/evidence/test_private_files_platform.py`
- `tests/integration/evidence/test_subprocess_truncation.py`
- `tests/integration/evidence/test_mixed_artifact_gate.py`
- `tests/integration/evidence/test_acpx_capture_live.py`

### Existing tests to modify

- `tests/unit/security/test_sanitization.py`: compatibility contract plus new shared
  policy rules.
- `tests/unit/telemetry/test_serialization.py`: prove the wrapper remains behaviorally
  compatible after its private regex is removed.
- `tests/unit/acp/test_trusted_paths.py`: only if a host-context fixture must expose
  an already-resolved profile root; do not add ambient environment reads.

## Task 0: Freeze inputs, re-derive the call surface, and mark pickup

**Files:** Read-only repository/spec sources; modify the consolidated pool only after
pickup approval; append only to the ignored reviewer checkpoint log.

- [ ] **Step 1: Verify branch, baseline, and committed design digest**

Run:

```bash
git status --short --branch
git merge-base --is-ancestor 79cd37cf37b2740f7580b2ed3859c0401a47f6a4 HEAD
git show a1f51e2:docs/superpowers/specs/2026-07-30-p11-feat-redaction-gate-design.md | sha256sum
```

Expected: the worktree has no unexplained changes, the ancestry command succeeds, and
the digest is exactly the frozen digest in this document.

- [ ] **Step 2: Reproduce the 40-file grep perimeter and 37-file behavioral baseline**

Run:

```bash
rg -l --glob '*.py' 'optimus_security\.sanitization|sanitize_for_persistence|StreamingTextSanitizer|redact_for_telemetry|sanitize_workspace_text' src tools tests
rg -n --glob '*.py' 'sanitize_for_persistence\(|StreamingTextSanitizer\(|redact_for_telemetry\(|sanitize_workspace_text\(' src tools tests
```

Classify every result by caller, wrapper/export, rule engine, or length-only launch
guard. Record the exact paths and counts in the ignored checkpoint. If the perimeter
is no longer 40 or the behavioral baseline is no longer 37, stop and return the diff
to the reviewer before touching code.

- [ ] **Step 3: Characterize existing behavior before changing the signature**

Run the current sanitizer-dependent suites:

```bash
uv run --frozen pytest tests/unit/security tests/unit/telemetry tests/unit/acp tests/unit/agent tests/unit/guardrails tests/unit/loops tests/unit/release tests/unit/optimus_gateway tests/unit/tools tests/integration/acp -q
```

Record pass/skip counts and any environment-gated exclusions. These outputs are the
compatibility baseline, not a license to change untested callers.

- [ ] **Step 4: Update living status only**

Change only the `EVIDENCE-HANDOFF-FEAT-REDACTION-GATE` pool row to say that implementation-plan
review/pickup is active, link this plan, and retain “assigned at pickup.” Do not alter
the frozen design or any other feature row.

- [ ] **Step 5: Run the documentation/naming check**

```bash
rg -n 'Plan [0-9]|plan-[0-9]' docs/superpowers/plans/evidence-handoff-redaction-gate-implementation.md
git diff --check
git status --short
```

Expected: no scheduling-number match in this plan, and only the approved pool/plan
state is modified.

- [ ] **Step 6: Stop for review**

Update the ignored checkpoint with the baseline, counts, command outputs, and pool
diff. Do not commit until Claude approves and the operator authorizes a docs-only
checkpoint commit. After that commit, stop; Task 1 is not automatically authorized.

## Task 1: Prove canaries, add policy contracts, and preserve all existing callers

**Files:** Modify `src/optimus_security/sanitization.py`,
`src/optimus/telemetry/subjects.py`, `tests/unit/security/test_sanitization.py`, and
`tests/unit/telemetry/test_serialization.py`; create the calibration test and two
fixtures.

- [ ] **Step 1: Add RED canary and compatibility tests**

The fixtures must include:

```json
{
  "unlabeled_api_key": "Q7mV2xN9pR4tY8kL3cD6wF1hJ5sB0zUa",
  "session_id": "session-zed-canary-0123456789abcdef",
  "run_id": "run-canary-0123456789abcdef",
  "gateway_request_id": "gw-canary-0123456789abcdef",
  "git_sha": "0123456789abcdef0123456789abcdef01234567",
  "artifact_sha256": "fe7dc4ae7c8730844b5104762dcf9fa5eec8ad8670c53480f0ece4e6da481569"
}
```

The Zed fixture must retain the captured Rust-debug grammar from the frozen design,
replace only the identifier with the deterministic session canary, and place the
unlabeled API-key canary on the same physical line.

Tests must prove:

- the API-key canary is a 32-character, five-bit-per-character candidate;
- every recognized prefix grammar catches its bounded canary independently of the
  entropy threshold;
- deterministic email masking and exact known-PII replacement use distinct,
  content-free rule identifiers;
- the session, run, and Gateway request canaries exceed the entropy threshold and
  survive only through their approved typed/free-text label validators;
- the git SHA and artifact SHA-256 are valid correlation shapes but deliberate
  entropy non-candidates: each is below 4.0 bits per character, each passes its
  dedicated field-shape and label validator directly, and neither is cited as proof
  that label preservation overrode the entropy detector;
- the unlabeled canary is detected;
- the same canary is preserved nowhere merely because another token on the line is
  labeled;
- every current `sanitize_for_persistence` and `StreamingTextSanitizer` call without
  a policy produces its pre-task value and rule counts; and
- `sanitize_workspace_text` keeps its existing whitespace-assignment behavior after
  that rule moves into the shared engine.

Run:

```bash
uv run --frozen pytest tests/unit/security/test_redaction_policy_calibration.py tests/unit/security/test_sanitization.py tests/unit/telemetry/test_serialization.py -q
```

Expected RED: missing policy/entropy/preservation APIs and the wrapper-delegation
assertion fail; existing baseline assertions remain green.

- [ ] **Step 2: Implement immutable policies and pure candidate scanners**

Add frozen `SanitizationPolicy`, `COMPATIBILITY_SANITIZATION_POLICY`, and
`EVIDENCE_REDACTION_POLICY`. The evidence policy version is
`evidence-redaction-v1`. Add bounded entropy, anchored prefix, field-shape, and
free-text-label scanners. Do not activate evidence-only rules in the compatibility
policy.

Move the whitespace secret-assignment rule from `subjects.py` into the shared
compatibility rule registry and leave `subjects.py` responsible only for workspace
normalization plus shared delegation.

- [ ] **Step 3: Run canaries before freezing the constants**

```bash
uv run --frozen pytest tests/unit/security/test_redaction_policy_calibration.py -q
```

Expected: the unlabeled key is caught, the actual Zed grammar preserves only the
labeled session ID, the unrelated token on the same line is caught, and all other
required labeled correlation shapes survive. Record rule identifiers and counts,
never values, in the ignored checkpoint. If any assertion fails, stop without
changing thresholds or grammars.

- [ ] **Step 4: Run the whole behavioral call surface in the same task**

```bash
uv run --frozen pytest tests/unit/security tests/unit/telemetry tests/unit/acp tests/unit/agent tests/unit/guardrails tests/unit/loops tests/unit/release tests/unit/optimus_gateway tests/unit/tools tests/integration/acp -q
uv run --frozen ruff check .
git diff --check
```

Expected: all baseline callers remain green and only explicit evidence-policy tests
observe new PII/path/prefix/entropy behavior.

- [ ] **Step 5: Stop for threshold and compatibility review**

Claude must review the actual RED/GREEN canary output and the 37-file compatibility
result before the policy constants become frozen by commit. Only after operator
authorization may the worker commit `feat: add evidence redaction policy contracts`.
Stop after the commit.

## Task 2: Establish portable packages, dependency allowlists, and typed models

**Files:** Modify `pyproject.toml`, `uv.lock`, and coverage configuration; create the
portable package initializers, `models.py`, import/naming/model tests.

- [ ] **Step 1: Write RED boundary and model tests**

The AST test must enumerate, not describe, the third-party allowlist:

```python
ALLOWED_EVIDENCE_IMPORT_ROOTS = frozenset({"PIL", "optimus_security"})
FORBIDDEN_EVIDENCE_IMPORT_ROOTS = frozenset({"optimus", "optimus_gateway", "tools"})
```

It must resolve standard-library modules using `sys.stdlib_module_names`, reject
dynamic imports (`__import__`, `importlib`), reject relative imports escaping the
portable package, and scan every Python file under both portable roots.

The naming test scans new source, test-tool, configuration-key, schema-name, and
artifact-name surfaces for Feature-ID or scheduling-number coupling. Version suffixes
such as `v1` are allowed.

Model tests must reject relative paths, source/destination containment, staging or
quarantine below the workspace/promotable destination, unsafe artifact roles,
invalid approval digests, timezone-naive timestamps, and an approver equal to the
collector.

Run:

```bash
uv run --frozen pytest tests/unit/evidence/test_import_boundaries.py tests/unit/evidence/test_naming_boundaries.py tests/unit/evidence/test_models.py -q
```

Expected RED: packages/models do not exist and Pillow is not declared.

- [ ] **Step 2: Add Pillow and create the portable model layer**

Add `Pillow>=12.3,<13` to runtime dependencies, update `uv.lock`, and add
`src/evidence_handoff` to coverage sources. Add only the model/package code needed
for the tests. Do not implement dispatch or image processing yet.

Register:

```toml
"requires_os_keyring: integration test that reads existing operator-approved credentials from the real OS credential store without writing or deleting them"
```

Exclude that marker from default pytest selection.

- [ ] **Step 3: Prove the real package/dependency shape**

```bash
uv lock --check
uv sync --frozen --extra dev
uv run --frozen pytest tests/unit/evidence/test_import_boundaries.py tests/unit/evidence/test_naming_boundaries.py tests/unit/evidence/test_models.py -q
uv build
uv run --frozen python -c "from PIL import Image; import evidence_handoff, optimus_security; print(Image.__version__)"
uv run --frozen ruff check .
git diff --check
```

Inspect the built wheel and record that all packages still co-ship. Do not claim a
standalone wheel. The isolated-import test must block `optimus` and
`optimus_gateway` while successfully importing `evidence_handoff.redaction.models`.

- [ ] **Step 4: Stop for dependency and extraction review**

The review must examine `pyproject.toml`, the lock diff, AST escape-hatch checks,
wheel contents, and isolated import output. Only after approval may the worker commit
`build: add portable evidence package boundary`. Stop after the commit.

## Task 3: Build the non-disclosing inventory and Optimus host adapter

**Files:** Create `src/optimus_security/sensitive_values.py`,
`src/optimus/acp/evidence_redaction_adapter.py`, their unit tests, and the live
runtime-input integration test.

- [ ] **Step 1: Write RED non-disclosure and adapter tests**

Inventory tests cover longest-first deduplication, aggregate source counts, empty and
over-length rejection, absent `__dict__`, blocked pickle/copy/dataclass conversion,
value-free `repr`/`str`, and value-free exceptions/log records.

Define `EvidenceRedactionHostContext` as a frozen host-only dataclass with these exact
fields: `authorized_launch: AuthorizedLaunch`,
`operator_profile_root: Path`, `user_data_roots: tuple[Path, ...]`,
`temporary_capture_root: Path`, `staging_root: Path`, `quarantine_root: Path`, and
`operator_identity_values: tuple[str, ...]`, plus
`forbidden_persistence_roots: tuple[Path, ...]` for workspace, cloud-sync, and other
operator-declared forbidden sinks. The sole conversion entry point is
`build_redaction_runtime_inputs(context: EvidenceRedactionHostContext) ->
RedactionRuntimeInputs`.

Tests must prove the adapter includes:

- values named by `candidate.secret_inventory` from both projected child mappings;
- the resolved provider key and resolved shared secret even when their provenance is
  configuration or keyring;
- injected username/email/host identity values as known PII;
- workspace, operator profile, user-data, temporary, staging, and quarantine aliases,
  longest-root-first; and
- no `AuthorizedLaunch`, `LaunchCandidate`, Optimus dataclass, `Any` mapping, or
  reflection-derived value in the portable result.

Run:

```bash
uv run --frozen pytest tests/unit/security/test_sensitive_values.py tests/unit/acp/test_evidence_redaction_adapter.py -q
```

Expected RED: inventory and adapter modules do not exist.

- [ ] **Step 2: Implement the inventory and one-way adapter**

The adapter consumes only already-resolved objects and explicit host context. It must
not call `os.environ`, dotenv parsing, a keyring API, the configuration resolver, or
trusted-root discovery. Catch source exceptions at the host boundary and replace them
with stable codes without chaining input-bearing messages.

- [ ] **Step 3: Verify unit behavior and semantic extraction**

```bash
uv run --frozen pytest tests/unit/security/test_sensitive_values.py tests/unit/acp/test_evidence_redaction_adapter.py tests/unit/evidence/test_import_boundaries.py -q
uv run --frozen ruff check .
git diff --check
```

- [ ] **Step 4: Run real resolver/keyring evidence for this task**

The integration test calls the canonical launch-candidate resolver with the real
operator configuration and real OS credential-store backend, passes the resolved
candidate through the adapter, and asserts only content-free counts and aliases. It
must not write, rotate, or delete any credential.

```bash
uv run --frozen pytest tests/integration/evidence/test_runtime_inputs_live.py -m requires_os_keyring -q
```

Expected: environment-, configuration-, and/or keyring-resolved source classes are
reported without values, and a canary scan of captured logs/exceptions is clean.

- [ ] **Step 5: Stop for source-custody review**

Claude must verify the live test used the real resolver/store and that no value or
Optimus object crossed the portable boundary. After authorization, commit
`feat: adapt resolved launch secrets into portable inputs`. Stop after the commit.

## Task 4: Enforce private staging, path aliases, and platform permissions

**Files:** Create `private_files.py`, its unit/integration tests, and extend shared
sanitizer path tests.

- [ ] **Step 1: Write RED path and filesystem tests**

Cover Windows case-folding and separator variants, POSIX case sensitivity,
longest-root-first replacement, segment-boundary rejection, symlink/junction escape,
source/destination overlap, unsafe quarantine placement, same-filesystem enforcement,
generated role-based filenames, atomic rename ordering, and cleanup/quarantine of
partial sanitized staging files.

The real platform test must assert:

- POSIX files/directories are `0o600`/`0o700` after creation; and
- Windows staging/quarantine paths have a protected DACL granting the current user
  and required system principals only, using real ACL enumeration rather than mode
  bits.

Run:

```bash
uv run --frozen pytest tests/unit/evidence/test_private_files.py tests/unit/security/test_sanitization.py -q
```

Expected RED: private filesystem and expanded alias behavior are absent.

- [ ] **Step 2: Implement portable private-file primitives**

Use descriptor-based creation (`os.open` with exclusive creation), `lstat`/resolved
containment checks, non-symlink parents, flush plus `os.fsync`, and `os.replace` only
on the same filesystem. Implement Windows DACL creation/validation with conditional
standard-library `ctypes`; do not import the host package or shell out to `icacls`.
All errors expose stable codes only.

- [ ] **Step 3: Run narrow and real-host evidence**

```bash
uv run --frozen pytest tests/unit/evidence/test_private_files.py tests/unit/security/test_sanitization.py -q
uv run --frozen pytest tests/integration/evidence/test_private_files_platform.py -q
uv run --frozen ruff check .
git diff --check
```

On this Windows host, record the real DACL result. Then run the POSIX permission test
inside WSL from the same worktree:

```bash
uv sync --frozen --extra dev
uv run --frozen pytest tests/integration/evidence/test_private_files_platform.py -q
```

If WSL cannot access the worktree or uv environment, report the exact failure; do not
substitute a mocked POSIX test.

- [ ] **Step 4: Stop for cross-platform review**

After approval, commit `feat: add private evidence staging primitives`. Stop after
the commit.

## Task 5: Implement bounded text, JSON, and NDJSON sanitization

**Files:** Create `text.py`, `structured.py`, their unit tests, and the real
subprocess-truncation integration test.

- [ ] **Step 1: Write RED text/JSON/NDJSON tests**

Tests must cover:

- exact secrets split at every stream boundary;
- prefix/entropy/email/PII/path candidates split across 64 KiB reads;
- original newline preservation;
- strict UTF-8 and no raw fallback;
- JSON depth/string/member/byte bounds and unsupported-object safety;
- deterministic UTF-8 JSON serialization;
- decoded JSON escape scanning;
- generic NDJSON all-or-nothing behavior;
- per-structural-path joined scans across record order;
- the allowlisted ACP trace final-tail six-condition predicate;
- a malformed newline-terminated final record;
- malformed interior records, invalid prefixes, excess tails, and multiple malformed
  regions; and
- an incomplete tail cut in the middle of a multibyte UTF-8 character, which must
  yield `QUARANTINED` and the stable invalid-UTF-8 reason.

The prefix validator must be an incremental, non-executing JSON lexer/state machine.
It accepts only a valid object prefix whose sole defect is missing suffix token(s) or
closing delimiter(s); illegal tokens, invalid ordering, or trailing data fail.

Run:

```bash
uv run --frozen pytest tests/unit/evidence/test_text_redaction.py tests/unit/evidence/test_structured_redaction.py -q
```

Expected RED: handlers and validators do not exist.

- [ ] **Step 2: Implement text and structured handlers**

Text uses `StreamingTextSanitizer` with the evidence policy and writes only sanitized
chunks to private staging. JSON/NDJSON use standard `json` without object hooks,
enforce bounds before promotion, sanitize parsed values through the shared engine,
and run both serialized-text and decoded-string final scans.

For an eligible ACP tail, scan the tail in memory for aggregate rule counts, discard
all tail bytes/fields, and emit only:

```json
{
  "truncated_tail_dropped": true,
  "dropped_tail_bytes": 137
}
```

The numeric example is illustrative of the field type only; the runtime value is the
actual aggregate byte count.

- [ ] **Step 3: Run narrow tests and the real process-boundary crash test**

`test_subprocess_truncation.py` must spawn a real writer process, terminate it during
the final record, and feed the resulting bytes through the gate. One case cuts after
a valid UTF-8 JSON prefix and promotes preceding sanitized records; a second cuts
inside a multibyte character and quarantines the whole artifact.

```bash
uv run --frozen pytest tests/unit/evidence/test_text_redaction.py tests/unit/evidence/test_structured_redaction.py -q
uv run --frozen pytest tests/integration/evidence/test_subprocess_truncation.py -q
uv run --frozen ruff check .
git diff --check
```

- [ ] **Step 4: Stop for truncation-contract review**

Claude must inspect the byte-level fixtures, confirm no raw tail digest/body is
persisted, and verify the real subprocess was used. After authorization, commit
`feat: sanitize bounded text and structured evidence`. Stop after the commit.

## Task 6: Implement canonical screenshots and hash-only dump quarantine

**Files:** Create `images.py`, `quarantine.py`, and their tests.

- [ ] **Step 1: Write RED Pillow and dump tests**

Image fixtures must contain EXIF, XMP, ICC, PNG textual chunks, a comment, and an
unsafe source filename. Tests cover PNG/JPEG magic validation, unsupported format,
multiframe input, byte/dimension/pixel bounds, decompression warnings, malformed
decoder input, canonical deterministic PNG output, absent metadata, generated output
name, awaiting-approval state, exact-digest approval, stale approval, self-approval,
and sanitized approval identity/rationale.

Dump tests cover Windows minidump and both-endian ELF `ET_CORE` headers, unknown
magic, streaming SHA-256, same-filesystem atomic move, already-quarantined retention,
cross-device refusal without copying, restrictive permissions, hash-only records,
and absence of any promotion API.

Run:

```bash
uv run --frozen pytest tests/unit/evidence/test_image_redaction.py tests/unit/evidence/test_quarantine.py -q
```

Expected RED: image and quarantine modules do not exist.

- [ ] **Step 2: Implement image and dump handlers**

For Pillow, open from the bounded private source, force `load()`, reject warnings and
extra frames, copy pixels into a fresh `Image.new`, clear/omit all metadata, convert
to RGB/RGBA, and save PNG with explicit deterministic parameters. Catch
`UnidentifiedImageError`, decompression failures, and encoder errors and replace them
with value-free reason codes using `from None`.

After canonical re-encoding, move the raw screenshot source to quarantine before
exposing the staged sanitized image for approval. Never overwrite approval state;
recompute the staged digest immediately before promotion.

For dumps, inspect only the bounded header needed for type recognition, hash by
chunks, move/retain in quarantine, and return content-free metadata.

- [ ] **Step 3: Run real dependency and filesystem evidence**

```bash
uv run --frozen pytest tests/unit/evidence/test_image_redaction.py tests/unit/evidence/test_quarantine.py -q
uv run --frozen pytest tests/integration/evidence/test_private_files_platform.py -q
uv run --frozen python -c "from PIL import Image; print(Image.__version__)"
uv run --frozen ruff check .
git diff --check
```

Inspect one emitted PNG with Pillow and a raw-byte metadata-canary scan. Expected:
Pillow is within the locked 12.3.x line, all metadata canaries are absent, and the raw
source exists only in approved quarantine.

- [ ] **Step 4: Stop for dependency-security and custody review**

After approval, commit `feat: canonicalize images and quarantine dumps`. Stop after
the commit.

## Task 7: Compose the gate, content-free manifest, and atomic promotion state machine

**Files:** Create `manifest.py`, `gate.py`, their unit tests, and the mixed-artifact
integration test.

- [ ] **Step 1: Write RED manifest and state-machine tests**

Freeze manifest schema `evidence-redaction-manifest-v1` with:

- sanitizer policy version;
- artifact kind and disposition;
- sanitized artifact SHA-256/size or dump hash/size;
- canonical non-PII locator;
- rule identifiers and aggregate counts;
- final-scan result and stable reason code;
- ACP tail fields when applicable;
- digest-bound approval metadata when applicable; and
- timezone-aware creation timestamp.

Tests must reject arbitrary extra fields and prove serialized manifests cannot contain
artifact bodies, mappings, values/fragments, per-value lengths, derived secret hashes,
raw errors, source absolute paths, or dump content. A manifest canary scan runs before
artifact promotion.

State-machine tests cover all four dispositions, type/content mismatch, no permissive
fallback, private stage before manifest, final scan before rename, approval recheck,
manifest-write failure, atomic-rename failure, quarantine-unavailable failure, and the
invariant that no manifest claims an unpromoted artifact.

Run:

```bash
uv run --frozen pytest tests/unit/evidence/test_manifest.py tests/unit/evidence/test_gate.py -q
```

Expected RED: manifest and gate do not exist.

- [ ] **Step 2: Implement fail-closed orchestration**

The order is fixed:

1. validate request/runtime/inventory without opening the source;
2. validate source custody and explicit kind;
3. sanitize/re-encode/hash into private state;
4. run decoded/joined final scans while inventory remains live;
5. bind/check screenshot approval where required;
6. assemble and scan the content-free manifest;
7. place the artifact and manifest in one private same-filesystem bundle directory;
8. flush/fsync both files and the bundle directory;
9. atomically rename the complete bundle into the promotable destination;
10. release inventory references and return only portable result metadata.

The destination exposes neither file before the bundle rename and both afterward.
Recovery removes or quarantines an abandoned private bundle; it never completes a
promotion by trusting an unscanned manifest.

- [ ] **Step 3: Run mixed real-filesystem integration evidence**

The integration test creates real JSON, generic NDJSON, crash-tail ACP NDJSON, text,
metadata-bearing PNG/JPEG, and synthetic dump files on disk; uses the real Pillow
decoder and real atomic filesystem operations; and verifies the required disposition
for each.

```bash
uv run --frozen pytest tests/unit/evidence tests/unit/security tests/unit/acp/test_evidence_redaction_adapter.py -q
uv run --frozen pytest tests/integration/evidence/test_mixed_artifact_gate.py -q
uv run --frozen ruff check .
git diff --check
```

- [ ] **Step 4: Stop for promotion-contract review**

Claude must inspect failure ordering and the produced manifest set, then run an
independent canary scan. After authorization, commit
`feat: enforce atomic evidence redaction promotion`. Stop after the commit.

## Task 8: Prove real authorized configuration, process, ACP, and Zed-consumer evidence

**Files:** Create the descriptive live runner, its unit test, and the live integration
test; update `.gitignore` only for its local workspace if needed.

- [ ] **Step 1: Write RED runner contract tests**

The runner must:

- require explicit capture, staging, quarantine, and output roots;
- reject any root overlap, known cloud-sync path segment, or containment within an
  explicitly supplied forbidden persistence root;
- use the canonical launch snapshot/resolver and an existing durable approval;
- use the real OS credential store without writing it;
- resolve `acpx` from PATH and record its version;
- spawn the real agent process with `shell=False`;
- stream stdout/stderr directly into the redaction gate;
- never materialize a raw transcript;
- record content-free process/config/dependency identities and artifact digests;
- require a separate operator-provided screenshot approval file bound to the staged
  digest; and
- produce no default report path.

Run:

```bash
uv run --frozen pytest tests/unit/tools/test_run_redaction_gate_live_evidence.py -q
```

Expected RED: runner does not exist.

- [ ] **Step 2: Implement the runner as test tooling, not a collector**

The runner exercises only this feature's gate and fixed `P11-FEAT-ZED-RESUME`
fixtures. It must not add declarative scenarios, UI automation, prompt injection,
crash classification, or general collector functionality.

- [ ] **Step 3: Run the real credential/process/ACP evidence**

Use operator-approved absolute roots outside cloud synchronization and a real durable
launch approval. Before the command, the operator supplies four absolute,
non-overlapping values as the non-exported shell-local variables
`evidence_capture_root`, `evidence_staging_root`, `evidence_quarantine_root`, and
`evidence_output_root`. Do not export them: the runner accepts them only as explicit
CLI arguments, does not read ambient environment itself, and must not project them
into the agent process.

```bash
test -n "${evidence_capture_root:?operator approval required}"
test -n "${evidence_staging_root:?operator approval required}"
test -n "${evidence_quarantine_root:?operator approval required}"
test -n "${evidence_output_root:?operator approval required}"
uv run --frozen python tools/run_redaction_gate_live_evidence.py verify \
  --capture-root "$evidence_capture_root" \
  --staging-root "$evidence_staging_root" \
  --quarantine-root "$evidence_quarantine_root" \
  --output-root "$evidence_output_root"
```

Then run:

```bash
uv run --frozen pytest tests/integration/evidence/test_runtime_inputs_live.py -m requires_os_keyring -q
uv run --frozen pytest tests/integration/evidence/test_acpx_capture_live.py -m "requires_os_keyring and requires_gateway and e2e" -q
```

Expected evidence:

- real config/keyring values reach the in-memory inventory without appearing in any
  artifact;
- `acpx` is independently authored and drives the real ACP process;
- no raw stdout/stderr transcript exists;
- the real-Zed-log grammar preserves session correlation while redacting the
  unrelated unlabeled token;
- workspace and external Windows user-data paths canonicalize;
- crash-tail handling records only the aggregate dropped byte count;
- all non-image artifacts are promotable only after final scan; and
- the screenshot remains awaiting approval until a different human identity approves
  its exact digest.

- [ ] **Step 4: Run live-output canary and provenance checks**

```bash
uv run --frozen python tools/run_redaction_gate_live_evidence.py inspect \
  --output-root "$evidence_output_root"
uv run --frozen ruff check .
git diff --check
```

The inspection command names every output artifact, verifies digests/manifests,
reports zero credential/scoped-PII hits, and emits no bodies or absolute source paths.

- [ ] **Step 5: Stop for live-evidence review**

Relay the runner output, `acpx` version, process/config dependency identities, artifact
digest table, and screenshot approval state to Claude. After approval and operator
authorization, commit `test: prove live redaction gate evidence`. Stop after the
commit.

## Task 9: Run repository gates, audit current-state documentation, and hand off

**Files:** Read all changed files and current-state docs; modify only the consolidated
pool and implementation-plan checkboxes whose named commands have passed.

- [ ] **Step 1: Re-run the behavioral blast-radius sweep**

```bash
rg -l --glob '*.py' 'optimus_security\.sanitization|sanitize_for_persistence|StreamingTextSanitizer|redact_for_telemetry|sanitize_workspace_text' src tools tests
uv run --frozen pytest tests/unit/security tests/unit/telemetry tests/unit/acp tests/unit/agent tests/unit/guardrails tests/unit/loops tests/unit/release tests/unit/optimus_gateway tests/unit/tools tests/integration/acp -q
```

Compare with Task 0 and explain every new/removed caller. Confirm every old caller
still uses the compatibility policy unless an explicit, reviewed test proves
otherwise.

- [ ] **Step 2: Run complete unit/integration/coverage gates**

```bash
uv run --frozen pytest tests/unit -q
uv run --frozen pytest tests/integration -q
uv run --frozen pytest --cov=src/optimus --cov=src/optimus_gateway --cov=src/optimus_security --cov=src/evidence_handoff --cov-report=term-missing --cov-report=xml --cov-fail-under=80
```

Named live markers are not satisfied by the default integration command; cite the
successful real commands from Tasks 3, 4, 5, 6, and 8 separately.

- [ ] **Step 3: Run repository security, style, packaging, and naming gates**

```bash
uv lock --check
uv run --frozen ruff check .
uv run --frozen detect-secrets-hook --baseline .secrets.baseline src
uv run --frozen bandit -q -r src -c pyproject.toml
uv build
uv run --frozen pytest tests/unit/evidence/test_import_boundaries.py tests/unit/evidence/test_naming_boundaries.py -q
git diff --check
git status --short
```

Inspect wheel contents and repeat the isolated import smoke. Confirm the distribution
still co-ships all packages while the import graph remains separable.

- [ ] **Step 4: Audit current-state documentation**

Read the consolidated pool, roadmap, README, this plan, and every current-state
document whose claims change. Update only living status/links. Do not rewrite frozen
design/history. The pool row must name exact commits and reviewed evidence when
closing; if any required evidence is absent, keep the feature open and name the
blocker.

- [ ] **Step 5: Produce the final review bundle and stop**

Record in the ignored checkpoint:

- exact commit and frozen-design digest;
- every test command and pass/skip count;
- coverage percentage;
- Ruff, detect-secrets, lock, wheel, naming, and import-boundary results;
- Windows and WSL permission evidence;
- real OS keyring/config, subprocess, Pillow, Gateway, ACP, and `acpx` dependency
  identities;
- content-free manifest/digest table;
- live-output canary result;
- documentation freshness diff; and
- any unrun gate with reason.

Relay the bundle to Claude. Do not make a closing commit until Claude approves and
the operator authorizes it. After an authorized closing commit, stop. Do not push,
open a PR, merge, delete branches, or rewrite history.

## Definition of Done

- [ ] The committed implementation matches the frozen design digest and no design
  amendment is pending.
- [ ] `optimus_security.sanitization` is the single rule engine.
- [ ] All pre-existing callers retain compatibility-policy outputs and rule counts.
- [ ] Evidence-policy canaries catch the unlabeled key and preserve only valid,
  labeled correlations, including the real Zed Rust-debug grammar.
- [ ] Exact runtime secrets and known PII are supplied from already-resolved host
  state and never persist or appear in diagnostics.
- [ ] `evidence_handoff` imports only stdlib, `optimus_security`, and `PIL`;
  `optimus_security` remains stdlib-only; the isolated import smoke passes.
- [ ] JSON, generic NDJSON, ACP crash-tail NDJSON, text, screenshots, dumps, unknown
  types, and mismatches follow their fail-closed policies.
- [ ] The mid-multibyte UTF-8 crash-tail case quarantines.
- [ ] Screenshots are metadata-free, digest-bound, and independently approved; dumps
  are hash-only and never promotable.
- [ ] Raw controlled ACP stdout/stderr is never written before sanitization.
- [ ] Private staging/quarantine permissions pass on real Windows and WSL/POSIX.
- [ ] Every promoted artifact has a scanned, content-free matching manifest and no
  unmanifested promotable artifact survives a failure.
- [ ] Real config/keyring, process, Pillow, Gateway, ACP, and independently authored
  `acpx` evidence has passed at the named tiers.
- [ ] Aggregate production coverage is at least 80%, Ruff and detect-secrets are
  clean, the lock is current, the wheel/import audits pass, and no descriptive code
  surface contains Feature-ID or scheduling-number coupling.
- [ ] Current-state documentation is fresh, the reviewer checkpoint is complete and
  unstaged, and no push/PR/merge occurred.

## Review handoff

Claude reviews this plan against the frozen committed design before implementation
pickup. During execution, the operator relays one completed task at a time. A task
approval authorizes only the separately requested commit for that task; it does not
authorize the next task or any remote Git operation.
