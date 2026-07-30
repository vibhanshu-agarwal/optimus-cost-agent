# P11-FEAT-REDACTION-GATE Design Specification

**Status:** Approved by Claude and the operator on 2026-07-30, including the operator-directed
extractability amendment verified by Claude on 2026-07-30. Implementation remains unauthorized
pending a separately reviewed implementation plan.

**Feature identity:** `P11-FEAT-REDACTION-GATE`. Numbering is assigned at pickup.

**Baseline:** `origin/main` at `79cd37cf37b2740f7580b2ed3859c0401a47f6a4`.

## Naming and document-custody rules

- This document references the feature exclusively as `P11-FEAT-REDACTION-GATE`.
- The feature identity is provisional but remains a unique, greppable token until an approved
  mechanical rename.
- Live feature state belongs only in the
  [consolidated open-work pool](../plans/2026-07-23-consolidated-deferred-followups-backlog.md).
  This design owns architecture, scope, and verification requirements, not status.
- Eventual package, module, configuration, and CLI names are descriptive of their behavior
  (`evidence`, `redaction`, `handoff`). They never contain a feature identity or scheduling number.
- The implementation package boundary is `optimus_evidence`. The shared security primitives remain
  in `optimus_security`; the evidence package must not fork them.
- `optimus_evidence` is a portable package. It must not import `optimus.*` or
  `optimus_gateway.*`; Optimus-specific adaptation lives in the host package.

## Goal

Create one fail-closed redaction gate for evidence artifacts before they enter a promotable report
or another durable evidence sink. The gate must redact API keys and scoped personally identifiable
information (PII), preserve required correlation evidence, and produce content-free proof of what
was checked.

The gate is designed for later extraction into a standalone evidence connector or plugin without
moving Optimus ACP or Gateway runtime code into that distribution. Package separation alone is not
the claim: the dependency graph, portable input contracts, and static boundary tests must make the
extraction mechanical.

The first consumer is sanitized evidence for `P11-FEAT-ZED-RESUME`. Later consumers include the
evidence collector and the A2A handoff ledger, but this feature does not implement either consumer.

## Existing evidence and load-bearing constraints

The repository already establishes a single sanitization source of truth:

- `src/optimus_security/sanitization.py` owns structured and free-text sanitization,
  exact known-secret replacement, URI-userinfo masking, streaming overlap, and content-free rule
  counts.
- `src/optimus_security/__init__.py` requires every persistence/export wrapper to delegate to that
  implementation rather than fork its rules (Global Constraint 17).
- `src/optimus_security/launch_manifest.py` records the established neutral-package pattern: shared
  primitives live outside both deployables so the ACP parent and Gateway child do not import each
  other. Its current imports are standard-library-only.
- `src/optimus/telemetry/redaction.py` is only a compatibility wrapper. It currently calls
  `sanitize_for_persistence(..., known_secrets=())`, so an unlabeled configured secret is not
  protected by exact matching at this boundary.
- `src/optimus/telemetry/subjects.py` canonicalizes only the supplied workspace root. It does not
  canonicalize an external Windows user-data path.
- The existing controlled ACP security-evidence helper's `_known_secrets` function already
  demonstrates the correct inventory principle: include values projected into child environments
  plus resolved provider and shared credentials that came from configuration or the OS keyring.
- The current ACP live-evidence helper marks output sanitized but writes raw `proc.stdout` to a
  transcript before parsing it and sanitizes only operator rationale through
  `sanitize_workspace_text`.
- `src/optimus/acp/debug_trace.py::log_provenance_once` records absolute interpreter, source, log,
  and working-directory paths that can contain the operator username.
- `pyproject.toml` currently uses setuptools package discovery with `where = ["src"]`, so
  `optimus`, `optimus_gateway`, `optimus_security`, and the future evidence package ship in one
  distribution today. A later distribution split remains cheap only if the import graph stays
  portable now.

The design therefore extends the existing sanitizer and controlled-capture precedent. It does not
introduce a second redaction stack.

## Scope

### In scope

- Exact replacement of runtime-known secrets sourced through the existing configuration and
  keyring resolution boundary.
- Pattern and entropy detection as a safety net for unlabeled API keys.
- Scoped PII handling: operator username, configured identity values, email-shaped values, and
  username-bearing workspace, profile, user-data, and temporary paths.
- Explicit preservation of session IDs, run IDs, model/provider names, git SHAs, and artifact
  SHA-256 digests as correlation evidence.
- Type-dispatched handling for JSON, NDJSON, streaming text, screenshots, and process dumps.
- Metadata-free screenshot staging followed by fail-closed human approval.
- Quarantine-and-hash-only handling for process dumps.
- A final joined-content scan before promotion.
- Content-free manifests containing digests, rule identifiers/counts, artifact kind, disposition,
  and approval metadata where applicable.
- A descriptive, extractable `optimus_evidence` package boundary.

### Explicit non-goals

- Implementing the evidence collector or A2A handoff ledger.
- Automating Zed prompt entry, window capture, crash detection, or evidence scenario execution.
- Retaining full conversations or raw unredacted transcripts.
- Persisting a known-secret or known-PII inventory in any form.
- General natural-language entity recognition for arbitrary names in prompt content.
- Automatically declaring screenshot pixels safe. Human approval remains mandatory.
- Promoting, parsing, symbolizing, or uploading process dumps.
- Adding a redaction-disable switch. A sink that requires this gate cannot bypass it.
- Replacing the existing telemetry wrappers where their current contracts remain adequate.

## Security model

### Protected assets

- API keys, shared secrets, bearer tokens, passwords, and credential-bearing URI user information.
- Operator identity values and username-bearing absolute paths.
- Raw screenshots and dumps that may contain sensitive pixels or memory.
- The in-memory known-sensitive-value inventory itself.

### Required evidence that remains visible

- `session_id` and `run_id` values.
- Model and provider names.
- Git commit SHAs.
- Artifact SHA-256 digests and gateway request IDs.
- Content-free sanitizer rule identifiers and counts.

Preservation is contextual, not a blanket allowlist. A structured field named `git_sha` may retain
a valid SHA, while the same unlabeled high-entropy token in free text remains subject to the safety
scan.

### In-scope failure and adversary cases

- A configured secret appears without a label or recognized vendor prefix.
- A secret is split across stream chunks, NDJSON records, or decoded JSON string fragments.
- JSON escaping hides a literal from a raw-text scan.
- An absolute path discloses the operator username outside the workspace root.
- An attacker-controlled object attempts to leak data through `repr`, `str`, or a serializer hook.
- A malformed artifact causes a parser, image decoder, or sanitizer exception containing input.
- Screenshot metadata or visible pixels expose PII or a credential.
- A dump contains arbitrary process memory.
- A secret inventory value reaches logging, an exception, a manifest, or a report through careless
  debugging.

### Accepted residual boundaries

- Python cannot guarantee zeroization of immutable strings. Implementations minimize lifetime,
  retain only process-local references, and discard the inventory immediately after the final scan.
- A compromised same-user process may read process memory or quarantine files. This feature
  controls project persistence and promotion; it is not an operating-system isolation boundary.
- Arbitrary natural-language PII that is neither injected as known PII nor matched by an approved
  deterministic pattern requires human review. No broad de-identification claim is made.

## Architecture

### Component boundary

`optimus_security` remains the security authority:

- `sanitization.py` owns every exact-match, structured-key, URI, PII, pattern, entropy, and
  preservation rule.
- A descriptive sensitive-value inventory module owns the in-memory value container, length
  validation, deduplication, and content-free metadata.
- The sanitizer never reads `os.environ`, `.env` files, the keyring, or artifact paths on its own.
- The neutral security package remains standard-library-only unless a separately reviewed
  amendment changes that portability contract.

`optimus_evidence.redaction` owns orchestration:

- artifact-kind dispatch;
- safe parsing and bounded streaming;
- staging, atomic promotion, quarantine, and filesystem permissions;
- screenshot approval state;
- dump hashing;
- final-scan invocation; and
- content-free manifest construction.

`optimus_evidence` may import `optimus_security`, the Python standard library, and explicitly
reviewed portable dependencies. It must not import `optimus`, `optimus_gateway`, ACP launch types,
Gateway service types, or project tools. Its public call boundary accepts only portable
protocols/dataclasses defined in `optimus_evidence` or `optimus_security`.

`src/optimus/acp/evidence_redaction_adapter.py` is the named Optimus host adapter. It is the only
component in this feature that understands `AuthorizedLaunch`, `LaunchCandidate`, projected child
environments, operator paths, or Optimus credential-resolution objects. It converts those
host-specific objects into portable `RedactionRuntimeInputs` and calls the evidence gate. The
portable package must not use reflection, `Any` mappings, or delayed imports to reach back into the
host.

The dependency direction is:

```text
optimus.acp.evidence_redaction_adapter -> optimus_evidence -> optimus_security
                                      \--------------------> optimus_security
```

`optimus_security` must not import the evidence package, and neither portable package may import
either deployable. Core redaction logic must not live in the host adapter.

### Conceptual data flow

1. The Optimus host captures an immutable runtime/configuration snapshot through the existing
   launch and credential resolution path.
2. The host adapter converts resolved Optimus objects into portable `RedactionRuntimeInputs`,
   including an in-memory sensitive-value inventory and canonical path aliases.
3. The portable gate classifies the artifact by an explicit requested type and validates that type
   against its content.
4. The gate sanitizes into a private staging destination without creating a second raw copy.
5. The gate runs the final exact/pattern/entropy/PII scan over the logical sanitized content.
6. The gate quarantines on any scan, parse, sanitizer, I/O, or policy failure.
7. The gate requires explicit human approval for a metadata-stripped screenshot.
8. The gate atomically promotes only an eligible sanitized artifact and writes its content-free
   manifest.
9. The host and gate drop all references to the sensitive-value inventory.

## Sensitive-value inventory

### Sources

The portable inventory builder receives values, never authority to rediscover them. It accepts only
portable typed inputs. For the Optimus host, the adapter derives those inputs from:

- secret-tier values from an immutable captured environment, selected through the existing launch
  variable registry;
- the exact values projected into the authorized agent and Gateway child environments;
- the resolved local shared secret;
- the resolved Gateway-side provider credential, whether its winning source was environment,
  operator configuration, or OS keyring; and
- explicitly injected known PII such as operator username, configured email, host identity, and
  trusted path roots.

The Optimus adapter reuses the already-resolved launch/configuration objects. It must not
independently parse `.env` files, query the keyring a second time, or reread ambient environment
state. A standalone connector supplies its own host adapter that constructs the same portable
`RedactionRuntimeInputs` contract; `optimus_evidence` never imports or invokes an Optimus bootstrap
path.

### Lifetime and non-disclosure

- Secret and PII values are deduplicated in memory and validated against the streaming maximum
  before any artifact is processed.
- The value container suppresses value-bearing representation and serialization.
- Logging receives only inventory counts and source-class counts, never values, hashes, prefixes,
  suffixes, lengths per item, or value-derived identifiers.
- Exceptions use stable value-free codes. They do not interpolate values or chain an exception
  whose text may contain one.
- Manifests contain sanitizer policy version, rule counts, artifact digests, and disposition only.
- No inventory cache or sidecar is written. The final scan runs while the values remain in memory;
  references are then released.

The existing session-scoped HMAC correlation primitive is not used for ordinary redaction
manifests. This gate has no need to reveal whether two secret values match.

## Sanitization policy

### Exact-match layer

Exact replacement is the primary guarantee for configured secrets. Longest values are matched
first using the existing `sanitize_for_persistence` and `StreamingTextSanitizer` contracts. The
empty `known_secrets=()` compatibility path remains valid for callers with no inventory, but every
evidence-gate invocation supplies the populated inventory.

### Structured-key and syntax layer

The shared sanitizer retains its current secret-field, bearer-token, assignment, API-key-header,
and URI-userinfo rules. The rule registry is extended centrally for:

- recognized API-key prefixes and token shapes;
- deterministic email masking;
- canonical path replacement;
- known-PII exact replacement; and
- entropy candidates not already handled by exact or structured rules.

Agent, Gateway, telemetry, evidence, and future handoff wrappers delegate to these shared rules.

### Entropy safety net

The entropy detector is deterministic and versioned. It considers bounded, token-like candidates
with a minimum length and mixed character classes, plus recognized key prefixes regardless of
entropy. It does not scan unbounded strings as one candidate.

To preserve evidence:

- typed structured fields for session IDs, run IDs, gateway request IDs, model/provider names, git
  SHAs, and SHA-256 digests are preserved after shape validation;
- free-text identifiers and hashes are preserved only when an adjacent approved label establishes
  their type;
- unlabeled high-entropy tokens are redacted; and
- ambiguous candidates fail safe toward redaction rather than promotion.

The free-text label grammar includes the syntax emitted by the first consumer, not only conventional
JSON or `key=value` spellings. In particular, a fixture derived from a real Zed log line must cover
the observed Rust-debug representation:

```text
... "json": Object {"sessionId": String("session-zed-canary-0123456789abcdef"), "update": Object {"sessionUpdate": String("plan"), ...}
```

Only the captured identifier is replaced with a deterministic canary when the fixture is prepared;
the surrounding real-log grammar remains unchanged. This fixture must prove that the session ID
survives while unrelated unlabeled high-entropy material on the same line is redacted.

Exact thresholds and token grammars are frozen in the implementation plan only after canary tests
show that an unlabeled API key is caught while the required correlation fixtures survive.

### Path and PII canonicalization

Path aliases are built from trusted resolved roots, normalized for separator and Windows
case-folding behavior, sorted longest-prefix-first, and matched only on path-segment boundaries.
The initial aliases are:

| Sensitive root | Persisted form |
|---|---|
| Active workspace | `<workspace>` |
| Operator profile/home and application-data roots | `<user-data>` |
| Approved temporary capture root | `<temp>` |
| Quarantine root | `<quarantine>` |

The source absolute path never appears in a manifest. Output filenames are generated from
descriptive artifact roles rather than copied from an unsafe input name.

Known operator username, configured email, and host identity values are exact-replaced when they
appear outside a recognized path. Email-shaped values use the shared deterministic pattern rule.
This scoped inventory is the minimum PII contract; implementation must not claim arbitrary
natural-language de-identification.

## Type-dispatched artifact handling

### JSON

- Parse with a non-executing standard JSON parser and no caller-provided hooks.
- Enforce bounded input size, nesting depth, string length, and collection count before promotion.
- Sanitize the parsed structure through `optimus_security.sanitization`.
- Serialize the sanitized value using deterministic UTF-8 JSON.
- Run the final scan over raw serialized text and decoded string values.
- A parse, bound, or serialization failure quarantines the input; there is no text-mode fallback.

### NDJSON

- Read as a bounded stream and parse every non-empty record independently.
- Sanitize each parsed record structurally, then serialize one normalized record per line.
- Maintain the existing overlap guarantee across raw chunks.
- Join decoded strings by structural path in record order for the final scan so a secret split
  across delta records is still detected.
- Any malformed or over-limit interior record quarantines the entire artifact.
- A malformed newline-terminated final record also quarantines the artifact.

One narrow, versioned exception applies to an append-only ACP debug trace interrupted during its
final write. The gate may drop the final physical tail and continue only when every condition below
holds:

1. The request explicitly declares the allowlisted append-only ACP debug-trace schema; generic
   NDJSON is not eligible.
2. At least one preceding record exists, and every preceding record is valid, within bounds, and
   sanitized normally.
3. The file does not end with a line terminator, and only the bytes after the last complete line
   fail to parse.
4. The tail is valid UTF-8, within the tail-size bound, starts as a JSON object, and a deterministic
   non-executing JSON-prefix validator proves that all complete tokens are valid and only a missing
   suffix token or closing delimiter prevents completion. An invalid token, invalid ordering, or
   extra trailing data is corruption and quarantines the artifact.
5. The incomplete tail is scanned in memory for rule accounting but none of its decoded fields or
   bytes is copied into the sanitized artifact, manifest, error, or report.
6. The sanitized preceding records pass the same joined final scan and promotion gates as any
   complete artifact.

An eligible result remains disposition `promoted`, with manifest fields
`truncated_tail_dropped: true` and `dropped_tail_bytes: <aggregate byte count>`. The manifest does
not retain the dropped bytes or a raw-tail digest. Any case outside this exact predicate
quarantines the whole artifact. This exception preserves valid crash evidence without converting a
malformed interior record or arbitrary corrupt final line into promotable content.

### Text logs and notes

- Stream through `StreamingTextSanitizer`; no raw interim transcript is written.
- Apply shared PII/path/pattern/entropy rules with enough overlap for every supported candidate.
- Preserve original newline semantics.
- Run the final joined scan before atomic promotion.
- Sanitizer failure may leave only a private partial sanitized staging file, which is immediately
  quarantined or removed; raw fallback is forbidden.

### Screenshots

- Accept only explicitly supported image formats and validate content rather than trusting the
  extension.
- Decode and re-encode to a canonical PNG with EXIF, XMP, IPTC, comments, textual chunks, source
  filename, and other non-pixel metadata omitted.
- Generate a descriptive output filename and content digest.
- Hold the metadata-stripped image in private staging with disposition `awaiting_human_approval`.
- Require an approval record bound to the exact staged SHA-256, sanitized approver identifier,
  timestamp, and a sanitized rationale.
- Promote only that exact approved digest. A changed image invalidates approval.

The decoder/encoder choice is reviewed for dependency and malformed-input behavior in the
implementation plan. Metadata stripping does not establish pixel safety; visual approval is
mandatory and cannot be self-awarded by the collecting agent.

### Process dumps

- Never copy a dump into a report or parse it for evidence.
- Move or retain it only in an approved, non-cloud-synced quarantine location with restrictive
  same-user permissions.
- Persist only its SHA-256, byte size, canonical quarantine locator, discovery timestamp, and
  value-free reason code.
- No approval path promotes the dump itself. A separately authorized human debugging workflow may
  inspect the quarantined source outside this feature's evidence contract.

### Unknown or mismatched types

Extension-only inference is insufficient. An unknown kind, content/type mismatch, unsupported
format, or ambiguous parser result is quarantined with a value-free reason. The dispatcher never
falls back from a stricter structured/image/dump policy to permissive text handling.

## Staging, quarantine, and promotion

The gate uses four dispositions:

| Disposition | Meaning |
|---|---|
| `promoted` | Sanitization and final scan passed; any required approval matches the exact digest. |
| `awaiting_human_approval` | Metadata-stripped screenshot is staged but cannot enter the report. |
| `quarantined` | Sensitive hit or processing failure prevents promotion; only safe metadata is reportable. |
| `rejected` | Request is invalid before artifact processing begins. |

Raw input is never copied into the promotable directory. Sanitized output is written to a private
same-filesystem staging file, flushed, rescanned, and atomically renamed only after every gate
passes. Destination creation, manifest writing, and promotion use fail-closed ordering so a
manifest cannot claim an artifact that was not promoted.

Quarantine lives outside the repository and outside cloud-synchronized directories. Quarantine
paths are canonicalized in any operator-visible record.

## Manifest contract

Each gate attempt emits at most one content-free manifest containing:

- schema and sanitizer-policy versions;
- artifact kind and final disposition;
- SHA-256 and byte size of the sanitized artifact, or hash-only dump metadata;
- canonical, non-PII artifact locator;
- rule identifiers and aggregate counts;
- `truncated_tail_dropped` plus aggregate `dropped_tail_bytes` when the narrow ACP debug-trace
  exception was applied;
- final-scan result and value-free failure reason;
- approval digest, sanitized approver identifier, and timestamp for an approved screenshot; and
- creation timestamp.

The manifest excludes:

- raw or sanitized artifact bodies;
- environment mappings;
- secret/PII values, fragments, lengths per value, deterministic value hashes, or correlation tags;
- raw exception messages;
- original absolute source paths; and
- dump contents.

A canary scan of the serialized manifest is mandatory before it can be promoted alongside an
artifact.

## Failure semantics

- Missing or invalid sensitive-value inventory: reject before processing.
- Over-length inventory value: reject with a name-free, value-free code.
- Parser, decoder, sanitizer, scan, permission, staging, or atomic-promotion failure: quarantine
  and emit only a stable reason code, except for the exact versioned ACP debug-trace final-tail
  predicate defined above.
- Final scan hit: quarantine; never auto-retry with weaker rules.
- Human approval absent, stale, mismatched, or self-authored by the collector: keep the screenshot
  non-promotable.
- Quarantine unavailable or unsafe: stop without creating another copy.
- Manifest sanitization failure: do not promote the manifest or artifact.

No error path logs the inventory, includes input text in an exception, changes artifact type, or
falls back to unsanitized persistence.

## Descriptive implementation surface

The eventual implementation may refine file boundaries, but it must preserve this dependency
direction and naming discipline:

| Descriptive surface | Responsibility |
|---|---|
| `src/optimus_security/sanitization.py` | Sole rule engine, preservation policy, and final content scan primitives. |
| `src/optimus_security/sensitive_values.py` | Non-serializable in-memory sensitive-value inventory and safe metadata. |
| `src/optimus/acp/evidence_redaction_adapter.py` | Optimus-only adapter from `AuthorizedLaunch`/`LaunchCandidate`, projected environments, and operator paths into portable `RedactionRuntimeInputs`; calls the portable gate. |
| `src/optimus_evidence/redaction/models.py` | Portable request, runtime-input, path-alias, result, disposition, and approval contracts; no Optimus types. |
| `src/optimus_evidence/redaction/gate.py` | Orchestration, dispatch, state transitions, and promotion decision. |
| `src/optimus_evidence/redaction/structured.py` | Bounded JSON/NDJSON parsing and sanitized serialization; no independent rules. |
| `src/optimus_evidence/redaction/text.py` | Streaming adapter over the shared sanitizer; no independent patterns. |
| `src/optimus_evidence/redaction/images.py` | Canonical metadata-free image staging and approval binding. |
| `src/optimus_evidence/redaction/quarantine.py` | Safe quarantine placement and hash-only dump records. |
| `src/optimus_evidence/redaction/manifest.py` | Content-free manifest assembly and pre-promotion scan. |
| `tests/unit/evidence/test_import_boundaries.py` | AST enforcement for portable-package imports plus an isolated import smoke with both deployable roots blocked. |
| `tests/unit/acp/test_evidence_redaction_adapter.py` | Host-to-portable mapping, inventory completeness, and proof that no Optimus object crosses the adapter boundary. |

Any future CLI uses a descriptive surface such as `optimus-evidence redact`. Configuration uses an
`OPTIMUS_EVIDENCE_` namespace only where configuration is genuinely required. There is no
feature-ID-bearing or number-bearing import path, command, setting, schema name, or artifact name.

All packages currently ship together because `pyproject.toml` discovers packages under `src`.
That packaging convenience does not relax the import boundary. A later standalone distribution may
select `optimus_evidence` plus `optimus_security` without pulling in `optimus` or
`optimus_gateway`.

## Verification design

### Unit evidence

- Exact known secrets from environment-, configuration-, and keyring-resolved fixtures are removed.
- The existing unlabeled API-key canary is caught by exact matching when configured and by the
  pattern/entropy layer when not configured.
- Inventory values, substrings, deterministic hashes, and per-value lengths never appear in
  representations, exceptions, logs, manifests, or reports.
- Secret canaries split at every chunk boundary, across NDJSON records, and through JSON escaping
  are caught.
- A real-Zed-log-derived fixture preserves its `sessionId": String("session-...")` value while
  redacting an unrelated unlabeled high-entropy canary on the same line.
- Windows and POSIX workspace/profile/user-data/temp paths canonicalize without substring or
  case-boundary mistakes.
- Email and injected operator-identity canaries are removed.
- Session IDs, run IDs, gateway request IDs, model/provider names, git SHAs, and artifact SHA-256
  values survive in typed fields.
- Unlabeled high-entropy tokens are redacted; labeled valid correlation fields are preserved.
- Unsupported objects never invoke `repr`, `str`, or custom serialization.
- JSON and ordinary NDJSON parse or bound failure quarantines without text fallback.
- The allowlisted ACP debug trace promotes sanitized complete records after dropping exactly one
  valid-prefix, non-newline-terminated final tail and records only
  `truncated_tail_dropped`/`dropped_tail_bytes`.
- Interior malformed records, newline-terminated malformed final records, invalid JSON prefixes,
  multiple malformed records, and over-limit tails all quarantine the complete artifact.
- Streaming sanitizer failure cannot write raw input.
- Image re-encoding removes metadata; approval binds to the exact digest; missing or stale approval
  cannot promote.
- Dumps produce only quarantine/hash metadata and have no promotion path.
- Manifest canaries prove the manifest contains no sensitive inventory material.
- A static naming audit covers the new package, entry points, configuration names, schema names,
  and artifact names and rejects scheduling-number or feature-ID coupling.
- A static AST import-boundary test scans every module under `src/optimus_evidence` and rejects
  imports rooted at `optimus`, `optimus_gateway`, or `tools`; it permits `optimus_security` and
  reviewed portable dependencies.
- The same boundary test keeps `optimus_security` standard-library-only: imports may resolve only
  to the Python standard library or another `optimus_security` module.
- Adapter tests prove `src/optimus/acp/evidence_redaction_adapter.py` is the host-side owner of
  `AuthorizedLaunch`/`LaunchCandidate` access and that the resulting portable runtime inputs contain
  no Optimus object.

### Integration evidence

- The canonical authorized-launch/configuration path supplies environment-, configuration-, and
  OS-keyring-resolved secrets through the named host adapter to the portable in-memory inventory
  without rereading sources.
- A mixed fixture set containing JSON, NDJSON, text, an image with metadata, and a synthetic dump
  yields the required disposition for every artifact.
- A real controlled ACP capture streams through the gate without writing raw stdout/stderr and
  passes the joined final scan.
- A crash-interrupted ACP debug trace with valid preceding records and a valid-prefix,
  non-newline-terminated tail promotes only the sanitized complete records and records the dropped
  byte count; the same fixture with an interior malformed record quarantines in full.
- Current debug provenance containing workspace and external Windows user-data paths is
  canonicalized while its session/run/model/provider/git evidence remains usable.
- The `P11-FEAT-ZED-RESUME` evidence fixture can be promoted only after all non-image artifacts
  pass and the screenshot receives an independent human approval.

Fakes are sufficient only for unit policy tests. Any final live-evidence claim uses the real
configuration resolver, OS credential store, process boundary, and independently authored ACP
client required by the repository evidence-tier rules.

### Repository and release checks

- Narrow security, telemetry, and evidence-package tests pass.
- The complete unit suite and aggregate coverage gate pass with the new package included in
  coverage configuration.
- Ruff and the repository secret scanner pass.
- A repository search proves no new evidence implementation surface contains feature-ID or
  scheduling-number names.
- The static import-boundary test plus an isolated import smoke that blocks `optimus` and
  `optimus_gateway` while allowing the standard library and declared portable dependencies prove
  there is no runtime dependency on either deployable. Built-wheel inventory records that all
  packages remain co-shipped today and makes no premature standalone-wheel claim.
- A canary scan names every promoted artifact and reports no credential or scoped-PII hit.

## Design completion criteria

- `optimus_security.sanitization` remains the sole redaction-rule implementation.
- `optimus_evidence` imports neither `optimus` nor `optimus_gateway`; all host state crosses a
  portable typed boundary through the named Optimus adapter.
- The evidence gate always receives a populated exact-match inventory from canonical resolved
  runtime state and never rereads ambient sources.
- The inventory is held only in memory and cannot appear in any output or error.
- JSON, NDJSON, text, screenshot, and dump policies are distinct and fail closed.
- API keys and scoped PII are removed; required correlation fields remain usable.
- No raw interim transcript is created by project-controlled capture.
- Screenshots require digest-bound human approval; dumps remain hash-only quarantine artifacts.
- Only sanitized, rescanned artifacts reach promotable destinations.
- Package, module, configuration, CLI, schema, and artifact names remain descriptive and independent
  of feature identity or scheduling.
- A standalone distribution can select `optimus_evidence` and `optimus_security` without shipping
  either deployable package.
- Implementation remains blocked until Claude verifies the extractability amendment and a
  separately reviewed implementation plan is assigned at pickup.

## Amendment record

### 2026-07-30 — Structural extractability

A post-approval dependency audit found that the original one-way
`optimus_evidence -> optimus_security` rule did not prohibit `optimus_evidence` from importing
Optimus ACP runtime objects. This operator-directed amendment:

- makes standalone connector/plugin extraction an explicit goal;
- prohibits portable-package imports from `optimus` and `optimus_gateway`;
- defines `RedactionRuntimeInputs` as the portable call-boundary contract;
- assigns `AuthorizedLaunch`/`LaunchCandidate` conversion to the named
  `optimus.acp.evidence_redaction_adapter` host adapter;
- records the current co-shipped setuptools packaging shape without treating it as proof of
  standalone distribution; and
- makes the boundary executable through AST and isolated-import tests.

No implementation work is authorized by this amendment.
