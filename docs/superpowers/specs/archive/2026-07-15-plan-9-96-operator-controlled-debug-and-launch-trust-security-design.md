# Plan 9.96: Operator-Controlled Debug and Launch Trust Security Design

**Status:** Draft for reviewer-agent and operator approval. No implementation plan or implementation work is authorized by this draft.

**Raised from:** Plan 9.96 in `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, carrying `P9.85-FU-7` and `P9.9-FU-1` after Plan 9.9 landed.

## Goal

Close two operator-trust gaps without weakening the Phase 1 one-key boundary:

1. Provide deliberately elevated, session- and time-scoped ACP diagnostics that help an operator correlate credential and launch failures while never writing literal secret values to logs, telemetry, transcripts, reports, or serialized state.
2. Prevent workspace-influenced launch environments from silently selecting security-relevant runtime settings. Because a flattened process environment does not retain trustworthy variable provenance, authorize exact effective values through a separate operator-controlled channel before the local Gateway or agent starts.

This document is the required security review and architecture contract. Its approval and frozen digest are prerequisites for the Plan 9.96 implementation plan.

## Source Anchors

- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, Plan 9.96 and the Plan 9.97 isolation sentence.
- Plan 9.9 foundation commit `f120a5afde39e3b3a8a405211ae71653b6e75665` and `reports/plan-9-9-operator-packaging-evidence.md`.
- `src/optimus/acp/debug_trace.py` and `src/optimus/telemetry/redaction.py`.
- `src/optimus/acp/e2e_transcript.py` and `src/optimus/acp/ndjson_subprocess_session.py`.
- `src/optimus/acp/local_gateway_secrets.py`, `src/optimus/acp/operator_paths.py`, `src/optimus/acp/local_infra.py`, and `src/optimus/acp/subprocess_env.py`.
- `src/optimus/config/gateway.py`, `src/optimus_gateway/models.py`, and `src/optimus/acp/spec.py`.
- `tools/run_plan988_fu4b_live_evidence.py` and the current real-`acpx` evidence paths.
- Optimus Cost Agent Architecture v2.15, Low-Level Design v2.38, and Test Strategy v1.4.

The HLD, LLD, and Test Strategy remain authoritative. In particular, credentials and API keys must never appear in plaintext in logs, telemetry, or serialized state. If an authoritative source conflicts with this design, implementation stops for an architecture decision.

## Security Review Decision

Plan 9.96 does **not** create an unredacted-secret logging mode. A secret-redaction bypass would contradict the authoritative architecture and would turn a diagnostic artifact into a credential-bearing persistence surface. The approved diagnostic substitute is richer provenance, classification, exact non-secret configuration, keyed session correlation, approval state, and sanitizer disposition while literal secrets remain redacted at every sink.

Plan 9.96 also does **not** attempt to infer whether an inherited environment value came from a shell, an IDE, a workspace file, or another parent layer. That origin information has already been flattened before Python starts and cannot be reconstructed reliably. The launch policy therefore validates exact effective content against an independently stored operator authorization. It preserves legitimate shell and administrator workflows by making them explicitly authorizable rather than trying to label their origin.

## Scope

### In scope

1. A complete inventory and fail-closed classification of every `OPTIMUS_*` setting consumed by Phase 1 source code.
2. An operator-authored approval store outside the repository, workspace, and configurable Optimus config root.
3. Exact-value authorization for security-sensitive non-secret settings and non-reversible authorization fingerprints for secret settings.
4. A single-use, short-lived approval handoff for an interactive launch and a durable exact-match approval for headless use.
5. Immutable environment snapshot validation before any local Gateway or agent process starts.
6. A session- and time-scoped elevated diagnostic grant that never permits literal secret output.
7. A broad audit and shared sanitization boundary for ACP debug traces, telemetry, errors, progress state, subprocess diagnostics, transcripts, reports, and evidence capture.
8. Sanitization before project-controlled `acpx` transcript persistence plus a joined-transcript promotion scan.
9. Mechanically enforced evidence for every security claim in this document.

### Explicit exceptions

- No literal secret values, fragments, reversible encodings, or unkeyed secret hashes in any diagnostic artifact.
- No attempt to distinguish IDE-originated, workspace-originated, shell-originated, or administrator-originated environment values after process launch.
- No trust in approval files stored in the workspace, repository, `.optimus`, or a root selected by inherited `OPTIMUS_CONFIG_ROOT`.
- No approval creation, update, or revocation through the long-running ACP server or an untrusted workspace process.
- No automatic approval of unknown future `OPTIMUS_*` variables.
- No weakening of the agent subprocess environment allowlist or the one-key runtime boundary.
- No replacement of real `acpx` with a project-authored ACP client for protocol-layer evidence.
- No edits to the frozen Plan 9.88 lane or reinterpretation of its spent evidence.
- No Plan 9.97 provider-plugin isolation work; the roadmap sentence assigning that work to Plan 9.97 remains unchanged.
- No implementation work until this design and the later implementation plan are separately approved.

## Threat Model and Trust Boundary

### Protected assets

- Provider credentials and the local Gateway shared secret.
- Gateway, Redis, provider, endpoint, bind, production-mode, and budget/control-plane configuration.
- The integrity of operator approvals and their workspace binding.
- The confidentiality and integrity of diagnostic logs, transcripts, evidence reports, and telemetry.
- The guarantee that the agent process receives only the established allowlisted runtime variables.

### In-scope adversary and failure modes

- A repository or workspace can influence an IDE launch configuration or otherwise inject environment variables into the parent process.
- A malformed or stale inherited environment can select a provider, endpoint, credential, Redis target, bind address, cost ceiling, or planning limit the operator did not intend.
- Concurrent launches, stale approvals, crashes, or environment mutation can create approval replay or time-of-check/time-of-use gaps.
- Secrets can cross logging boundaries through mappings, free-form strings, URLs, exceptions, stderr, JSON-RPC errors, or transcript capture.
- A secret split across lines or stream chunks can evade a line-local sanitizer.

### Out of scope and accepted residual risk

- Compromise of the operating system, the current user's session, the Python runtime, or the OS credential store is outside the Phase 1 boundary.
- The approval command and the serving process run as the same OS user. Separating their code paths reduces accidental and workspace-driven writes but is not an OS-enforced privilege boundary; another same-user process can call credential-store APIs.
- An operator can deliberately approve a malicious literal endpoint or provider. The ceremony makes that choice explicit and auditable; it cannot make a knowingly bad choice safe.
- A session-keyed correlation tag is a one-bit match oracle for a guessed value. Session scope, a random non-exported HMAC key, bounded diagnostic lifetime, and the absence of arbitrary comparison endpoints make this an accepted residual risk.
- Artifacts written directly by an arbitrary external `acpx` invocation outside project-controlled capture are outside the project's persistence guarantee. Project documentation must warn that only the controlled capture path produces Plan 9.96-qualified evidence.

## Trust Sources and Bootstrap Rules

The launch gate uses only these trust sources:

1. Code and fixed defaults from the reviewed installation.
2. Operator configuration from a platform-derived user configuration directory that is resolved without inherited workspace-controllable `APPDATA`, `XDG_CONFIG_HOME`, or `HOME` values.
3. Approval records and HMAC keys in the operating-system credential store.
4. The immutable inherited environment snapshot, treated as untrusted input until classified and approved.

On Windows, the default operator directory must be resolved through the operating-system Known Folder API or an equivalently reviewed OS call. On POSIX systems, it must be derived from the authenticated account record or another reviewed OS API rather than inherited `HOME` or `XDG_CONFIG_HOME`. `OPTIMUS_CONFIG_ROOT` is itself gated and cannot participate in locating the store that approves it. If a platform-safe default cannot be resolved, launch fails closed with a value-free remediation message.

The existing operator `.env.gateway` can remain a value source only after its platform-derived location and file protections pass validation. It is not an approval store. Workspace-local `.env` files, launch configurations, and inherited values remain untrusted sources even when their values are later approved.

## Single Source of Truth for Launch Variables

Implementation must create one typed registry that is the sole policy source for variable classification, parsing, display, comparison, child propagation, and unknown-variable rejection. Production code and tests consume that registry; parallel hand-maintained lists are prohibited.

A repository test scans `src/**/*.py` for literal `OPTIMUS_*` references and fails when a referenced name is absent from the registry. A second test fails when the registry contains a variable without an explicit tier and policy. Dynamic prefixes are represented by an explicit prefix rule whose allowed members are still enumerated. Any new `OPTIMUS_*` variable therefore requires a deliberate security classification in the same change.

### Tier 1: secret settings

These values are never displayed or persisted. Authorization records contain only an HMAC-SHA-256 fingerprint made with an OS-credential-store key plus the variable name, workspace identity, and value length as domain-separated input:

- `ANTHROPIC_API_KEY`
- `GLM_API_KEY`
- `LANGCHAIN_API_KEY`
- `LANGSMITH_API_KEY`
- `OPENAI_API_KEY`
- `OPENROUTER_API_KEY`
- `TAVILY_API_KEY`
- `ZHIPUAI_API_KEY`
- `OPTIMUS_API_KEY`
- `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY`
- `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET`

The registry must also treat any credential embedded in a URI, including Redis user information, as a Tier 1 subfield for approval storage, display, and diagnostics even when the enclosing setting belongs to Tier 2. The non-secret URI components remain Tier 2. Exact full-value matching uses the same keyed HMAC construction as a secret setting; the record stores the normalized URI with user information removed plus a presence flag, never the user information itself. Raw SHA-256, prefixes, suffixes, last-four characters, reversible encoding, or stable cross-session secret identifiers are forbidden.

### Tier 2: non-secret security settings

These settings require exact-value authorization when inherited or overridden. The ceremony displays their complete effective literal value so the operator can make an informed choice, except URI user information is replaced with a fixed mask before display:

- `OPTIMUS_GATEWAY_URL`
- `OPTIMUS_REDIS_URL`
- `OPTIMUS_CONFIG_ROOT`
- `OPTIMUS_PRODUCTION_MODE`
- `OPTIMUS_EXTRA_GATEWAY_ORIGINS`
- `OPTIMUS_LOCAL_GATEWAY_PROVIDER`
- `OPTIMUS_LOCAL_GATEWAY_BASE_URL`

`OPTIMUS_REDIS_URL` belongs here because it controls state persistence and may route data to a different system. Approval comparison uses the exact raw value, while ceremony display and diagnostics mask any URI user information. Provider and base URL are displayed literally; hiding them would make approval a rubber stamp.

List-like and boolean values are parsed into a canonical semantic form for validation, but the record retains the exact non-secret source string and the normalized value. For a URI containing user information, the record instead retains the masked normalized URI and a keyed HMAC fingerprint of the complete raw source string. Approval succeeds only when both the reviewed semantic value and the current exact source representation satisfy the registry policy, preventing ambiguous alternate spellings from bypassing review without persisting embedded credentials.

### Tier 3: monotonic safety limits

These inherited controls may tighten the reviewed default without approval but may never loosen it without exact-value authorization:

- `OPTIMUS_LIVE_MAX_COST_USD`: an unapproved positive value is accepted only when it is less than or equal to `DEFAULT_LIVE_MAX_COST_USD = Decimal("0.25")`, a new launch-policy registry constant provenance-pinned to the Plan 9.6 live-evidence cap. Production code currently forwards this variable but does not consume or enforce it; the Plan 9.96 launch gate becomes its first production enforcement point.
- `OPTIMUS_MAX_PLANNING_TURNS`: an unapproved positive integer is accepted only when it is less than or equal to the reviewed default of `3` turns.

An absent value uses the reviewed default. Zero, negative, non-finite, malformed, or otherwise invalid values fail closed. A value above the default is Tier 2-equivalent for ceremony, exact-match approval, audit, and expiry purposes. The turns clamp deliberately narrows `src/optimus/acp/spec.py`'s current operator testing override, which accepts any integer greater than or equal to `1`; an evidence run needing more than three turns must obtain exact-value approval. If a future source changes either reviewed default, the registry, approval compatibility version, and tests must change together.

### Tier 4: bounded operational selection

`OPTIMUS_AGENT_MODEL` may be inherited without a separate ceremony only while all of the following hold:

1. The effective cost ceiling remains the approved or monotonic-safe Tier 3 value.
2. Model resolution still routes exclusively through the Optimus Gateway.
3. The selected model is recognized by the reviewed Gateway configuration and pricing path.
4. The model value is logged only as non-secret configuration and cannot contain URI user information or credentials.

If any condition fails, model selection fails closed or is elevated to exact-value approval. This exception is safe only because endpoint, credentials, provider routing, and cost ceiling remain independently protected.

### Tier 5: internal-only settings

The following settings may be constructed by reviewed code for a child process but are rejected when inherited from the untrusted parent launch environment:

- `OPTIMUS_LOCAL_GATEWAY_BIND_HOST`
- `OPTIMUS_LOCAL_GATEWAY_PORT`
- `OPTIMUS_ACP_DEBUG_TRACE`
- `OPTIMUS_ACP_DEBUG_LOG`
- `OPTIMUS_ACP_PROVENANCE_ROOT`
- every future implementation-private `OPTIMUS_ACP_*` setting until it is explicitly enumerated and reviewed
- any non-enumerated `OPTIMUS_LOCAL_GATEWAY_*` setting

The bind host is network-security-critical even without the port. Both host and port must come from reviewed local defaults or an explicit future design; inherited values never reach the local Gateway. ACP debug settings may be constructed from reviewed CLI arguments only after the inherited snapshot has rejected same-named parent values. Child construction and parent rejection use the same registry.

### Unknown settings

Any inherited `OPTIMUS_*` name not classified by the registry fails closed before credential resolution, network access, Gateway startup, agent startup, or diagnostic file creation. The error names the variable but never includes its value.

## Immutable Launch Snapshot and Authorization Decision

The entry point copies the inherited environment exactly once into an immutable snapshot before any Optimus configuration or path helper reads `os.environ`. All downstream parsing, source resolution, approval comparison, child-environment construction, and audit fields derive from this snapshot plus trusted sources. Direct late reads of `os.environ` in the gated launch path are prohibited and covered by tests.

The gate then performs this sequence:

1. Enumerate and classify every relevant variable through the registry.
2. Reject unknown and inherited internal-only names.
3. Resolve trusted defaults and external operator configuration without using a gated path override.
4. Resolve the exact effective values from the immutable snapshot and trusted sources.
5. Apply parsing, URI-user-information detection, monotonic-limit rules, and child-propagation policy.
6. Match the resulting security snapshot to a valid operator approval bound to the canonical workspace identity.
7. Recompute the same snapshot immediately before child construction and require byte-for-byte equality with the authorized snapshot.
8. Construct explicit Gateway and agent child environments from the authorized snapshot and registry; never copy the parent wholesale.

Any mismatch fails closed. Gateway and agent startup functions accept the validated snapshot as an argument rather than resolving mutable global environment state again. A crash after consuming a one-shot approval does not restore it.

## Workspace Identity

Approvals are bound to a canonical workspace identity containing:

- normalized absolute workspace path resolved without following a workspace-controlled textual alias after authorization;
- platform file identity when available, such as Windows volume serial plus file ID or POSIX device plus inode;
- repository identity derived from the Git common directory and canonical repository root when Git is present;
- approval schema and launch-policy compatibility versions.

Path comparison uses platform-aware normalization. A missing workspace, changed file identity, repository relocation, or compatibility-version change invalidates the approval. Symlink and junction changes between approval and launch fail closed.

## Operator Approval Store

### Location and authorship

Approval records and HMAC keys live in the OS credential store under a dedicated Optimus service namespace. The credential store was selected because an approval cannot safely live beneath a config root selected by the very `OPTIMUS_CONFIG_ROOT` value being gated.

Only a separate, short-lived operator CLI exposes create, inspect-metadata, revoke, and rotate-key operations. Approval creation requires an interactive terminal, displays the complete normalized security snapshot according to the masking rules, asks for an explicit confirmation, and records the authenticated local user identity where the platform exposes it. The long-running ACP server and ordinary launch path expose read/consume operations only. This code-level write/read split is defense in depth, not an OS security boundary against the same user.

### Record schema

Each approval record contains:

- schema and launch-policy compatibility versions;
- approval ID and mode (`one-shot` or `durable`);
- canonical workspace identity;
- creation time, optional expiry, creator identity, and ceremony command version;
- exact normalized literals for Tier 2 settings, except secret-bearing URI subfields are removed and the complete raw URI is represented only by a keyed HMAC fingerprint;
- HMAC fingerprints and lengths for Tier 1 settings;
- approved elevated values for Tier 3 settings, while monotonic-safe values are recorded as observations rather than grants;
- the Tier 4 model-selection observation and the protected cost-cap decision;
- registry version and a digest of the complete classified security snapshot;
- consumption state for a one-shot record;
- no credential, URI user information, raw secret hash, or workspace content.

The serialized record must be compact UTF-8 JSON of at most 1,800 bytes. This budget stays below the approximately 2.5 KB Windows Credential Manager generic-credential payload limit with implementation margin. Phase 1 rejects an oversized record with value-free remediation rather than chunking it; tests exercise the worst-case supported record and the rejection boundary.

### Durable approval

A durable approval remains valid until a declared expiry, exact-value change, workspace-identity change, registry/policy compatibility change, key rotation, or explicit revocation. Expiry is optional because very short automatic expiry would encourage blind repeated confirmation and would not materially improve an exact-match authorization. Headless launches may only consume a durable approval that was authored once through the interactive operator CLI; a headless process cannot create or expand one.

### One-shot handoff

The interactive CLI creates a cryptographically random 256-bit approval nonce and constructs the lookup handle as `p996_` plus an unpadded base64url encoding of `SHA-256("optimus-plan-9.96-one-shot-v1" || nonce)`. It stores the nonce and `one-shot` record in the OS credential store under that handle, then directly spawns or execs the launch command with only the non-secret handle in a dedicated command-line argument. It does not print the handle for shell substitution. The nonce itself never appears in arguments, environment variables, stdout, workspace files, or logs. The record expires no more than five minutes after creation and is bound to the exact workspace and classified snapshot.

The launch path acquires an OS-level per-workspace approval lock in the platform-derived runtime directory, loads the record by approval ID, recomputes the nonce-derived handle, verifies the record HMAC and exact snapshot, deletes the record before child startup, and only then releases the lock. Delete-before-use provides single-use fail-closed behavior: concurrent launches cannot both consume the record, and a crash loses the grant. A missing record, failed deletion, expired record, lock failure, or snapshot mismatch prevents startup. The audit record stores the approval ID and outcome but not the nonce.

The HMAC integrity key and the record payload are separate credential-store entries. Integrity covers the complete canonical record including mode, workspace, values/fingerprints, timestamps, compatibility versions, and consumption state. Normal concurrency is enforced by the OS lock because the credential-store APIs do not promise an atomic compare-and-swap operation.

## Elevated Diagnostic Grant

Elevated diagnostics are a separate grant from launch authorization. They cannot authorize a setting or bypass launch policy.

The operator CLI may create a diagnostic grant bound to one workspace, one approval ID, one launch/session ID, and an expiry no more than 15 minutes after creation. The serving process consumes it once at session start. Expiry or session mismatch returns logging to the ordinary redacted mode without affecting safety decisions.

Elevated mode may add only:

- effective source class, such as reviewed default, external operator config, inherited snapshot, or generated child value;
- setting name, tier, presence, parser result, authorization result, and propagation decision;
- complete non-secret Tier 2 and Tier 4 values subject to URI-user-information masking;
- normalized monotonic-limit value and whether it tightened, matched, or required approval;
- approval ID, mode, workspace match, compatibility version, expiry, and consumption outcome;
- sanitizer rule identifiers and replacement counts;
- session-local correlation tags.

For a secret field, the correlation tag is `HMAC-SHA-256(session_random_key, domain || field_name || value_length || secret_value)`, truncated to 128 bits for display. The session key is generated in memory, never persisted or exported, and destroyed with the process. Tags cannot be requested for arbitrary caller-provided candidates; they are emitted only for reviewed diagnostic comparison points already reached by runtime flow. Ordinary mode emits no secret correlation tags.

Elevated mode may never emit a secret literal, substring, first/last characters, reversible encoding, raw or unkeyed hash, URI user information, exception representation containing a secret, or full environment mapping.

## Sanitization and Persistence Boundary

One shared sanitizer contract applies before data crosses any diagnostic persistence or export boundary. Structured fields are sanitized recursively by name and value. Free-form strings are scanned for bearer credentials, environment assignments, known current secret values held only in memory, URI user information, and secret-shaped patterns. Sanitization is fail-closed: an unsupported type is summarized by safe type metadata rather than serialized with `repr`.

The broad audit covers at least:

| Surface | Required Plan 9.96 policy |
|---|---|
| ACP debug NDJSON | Shared sanitizer before append; elevated metadata is allowlisted. |
| Application and Gateway structured logs | Shared sanitizer before handler/export; no raw exception or environment dump. |
| Telemetry and Gateway exporters | Shared sanitizer before batching and transport. |
| Progress ledger and serialized agent state | Secret-bearing fields prohibited; safe summaries only. |
| JSON-RPC errors and operator stderr | Value-free errors or shared-sanitized messages before emission. |
| Subprocess stdout/stderr retained by harnesses | Streaming sanitizer before project-controlled persistence. |
| E2E transcript writer | Sanitize every record before append and reject environment-like mappings. |
| Real-`acpx` capture and evidence helpers | Never write raw process output to an interim file; use the controlled sanitized stream. |
| Markdown/JSON evidence reports | Promote only sanitized artifacts that pass the final scan. |

### Cross-line and cross-chunk defense

Streaming sanitization maintains a bounded overlap window large enough for the maximum supported credential and URI token length so patterns split across chunks can be detected before release. No raw chunk is written while awaiting the overlap decision.

Before an artifact is promoted as evidence, the controlled capture process scans the logically joined transcript while the current secret values are still available in memory, then discards those values. The standalone verifier repeats the joined scan using decoded JSON string fields, configured secret canaries, secret-shaped patterns, and the capture's signed sanitizer manifest; it never needs persisted secret literals. These joined scans are the required safety net for values split across lines or chunks. A hit quarantines the artifact outside the promotable evidence set, emits only value-free rule identifiers, and fails the evidence gate.

Project-controlled capture must stream sanitized `acpx` stdout/stderr directly to the destination; raw interim transcript files are forbidden. Existing helpers that persist raw `proc.stdout` must be remediated or excluded from Plan 9.96-qualified capture before the corresponding evidence claim can pass.

## Audit Record

Every authorization decision writes an append-only, shared-sanitized audit event containing:

- timestamp, workspace identity digest, launch/session ID, and process role;
- registry and policy compatibility versions;
- names and tiers of observed settings, never secret values;
- masked/literal non-secret display values according to this design;
- approval ID, mode, creator metadata, expiry, and match/consume outcome;
- unknown/internal-only rejection names;
- monotonic-limit disposition;
- child-propagation decision;
- diagnostic grant state and sanitizer rule/count summary;
- final disposition and a stable value-free reason code.

Audit append failure, sanitizer failure, approval integrity failure, or inability to protect the audit destination fails closed before child startup. Audit data remains subject to the established retention and local access controls; Plan 9.96 does not claim protection from a compromised same-user process.

## Failure Semantics

- **Unknown variable:** name-only error; startup stops.
- **Inherited internal-only variable:** name-only error; startup stops.
- **Unapproved or changed security value:** display-safe comparison and approval remediation; startup stops.
- **Loosened monotonic limit:** exact-value approval required; startup stops without it.
- **Malformed value or embedded credential in a prohibited field:** value-free error; startup stops.
- **Approval expired, revoked, corrupt, oversized, wrong-workspace, wrong-policy, already consumed, or concurrently locked:** startup stops.
- **Environment snapshot changed:** startup stops; the operator must restart the ceremony.
- **Sanitizer or audit failure:** startup or artifact promotion stops, depending on the boundary reached.
- **Diagnostic grant failure:** ordinary redacted logging continues only if the launch itself remains authorized; no elevated metadata is emitted.

No failure path falls back to trusting the inherited value, copying the parent environment, disabling redaction, or logging the rejected value.

## Component Boundaries

The implementation plan must preserve these architectural roles, though it may refine filenames after repository inspection:

- **Launch policy registry:** owns every variable tier, parser, normalization, display, approval, and propagation rule.
- **Trusted path resolver:** derives the operator directory and runtime lock directory independently of inherited gated values.
- **Environment snapshot:** immutable input to all launch resolution and child construction.
- **Approval writer CLI:** interactive create/revoke/inspect-metadata/rotate operations; never imported by the serving path.
- **Approval reader/consumer:** read-only durable validation and delete-before-use one-shot consumption.
- **Diagnostic grant consumer:** verifies and consumes a session-scoped grant without altering launch authorization.
- **Shared sanitizer:** the only project-supported conversion from possibly sensitive runtime data to persistable diagnostic data.
- **Transcript promotion verifier:** joined-content scan and evidence-qualification decision.
- **Explicit child builders:** construct local Gateway and agent environments from the validated snapshot and existing one-key allowlists.

Circular dependencies are prohibited: approval-store location cannot depend on `OPTIMUS_CONFIG_ROOT`; launch authorization cannot depend on a child that has not yet been safely started; and the sanitizer cannot obtain secrets by rereading an unvalidated ambient environment.

## Verification and Evidence Design

### Registry and policy tests

- Scan all `src/**/*.py` literal `OPTIMUS_*` references and fail on an unclassified name.
- Fail on registry entries without an explicit tier, parser, display, approval, and propagation policy.
- Prove unknown `OPTIMUS_*` names fail closed.
- Prove inherited bind host, bind port, and private `OPTIMUS_ACP_*` settings are rejected.
- Prove agent and Gateway child environments contain exactly their registry-authorized names.

### Value and ceremony tests

- Tier 1 records contain only domain-separated HMAC fingerprints and lengths; deterministic raw hashes, fragments, and values are absent.
- Provider and base URL are displayed literally; Redis URI user information is masked while exact raw comparison still governs approval.
- `OPTIMUS_CONFIG_ROOT` cannot influence the approval-store or lock location.
- Cost and turn limits accept unapproved tightening, reject invalid values, and require approval for any increase above the reviewed defaults.
- The model exception fails when the cost cap is not protected or Gateway-only routing is not satisfied.
- Durable records invalidate on exact-value, workspace, file identity, policy, registry, key, expiry, or revocation changes.
- The maximum supported record fits within 1,800 bytes and oversized records fail without partial writes.

### One-shot, integrity, and TOCTOU tests

- The approval nonce has 256 bits of cryptographic randomness and never appears in the child environment, process arguments, stdout, audit event, or workspace.
- Only one of two concurrent consumers succeeds under the per-workspace OS lock.
- Delete-before-use makes a consumed or crash-lost grant unavailable for replay.
- A failed record deletion prevents child startup.
- A changed environment, workspace identity, symlink/junction target, or compatibility version between ceremony and startup fails closed.
- Gated startup paths use the immutable snapshot and do not perform late ambient-environment reads.
- Headless mode can consume but cannot author or expand a durable approval.

### Diagnostic and sanitizer tests

- Ordinary and elevated modes redact every enumerated credential and URI user information across mappings, strings, exceptions, stderr, JSON-RPC errors, logs, telemetry, state, and transcripts.
- Elevated mode emits only its allowlisted metadata and session-local tags.
- Identical secrets at reviewed comparison points match within one session; tags change across sessions.
- Arbitrary correlation guesses are not accepted, and expired/wrong-session grants emit no elevated metadata.
- Secret canaries split across chunks, lines, JSON fields, and exception boundaries are caught by streaming overlap and joined-transcript scans.
- Unsupported objects are safely summarized without calling a potentially secret-bearing `repr`.
- Sanitizer or audit failures are fail-closed and never result in raw fallback output.

### Integration and live evidence

- A subprocess integration test launches through the real gate with workspace-influenced inherited values and proves that no local Gateway or agent child starts before authorization.
- An authorized legitimate shell/admin configuration launches with the exact approved provider, endpoint, Redis target, limits, and one-key agent child environment.
- A real local Gateway plus independently authored `acpx` drives the real agent through ordinary and elevated diagnostic sessions.
- Project-controlled capture persists no raw interim output, the joined promotion scan passes, and a repository-wide canary/credential scan names the exact promoted artifacts checked.
- Evidence records include approval, snapshot, child-environment, sanitizer, transcript, and audit locators without including secret values.

Fakes may validate policy units only. They cannot satisfy the live Gateway, independent-ACP-client, or final evidence claims.

## Security-Review Freeze and Implementation-Plan Gate

This draft becomes the Plan 9.96 security contract only after explicit reviewer-agent and operator approval. At that point:

1. Record the approved status, date, reviewer identities, and full-file SHA-256 in this document or an adjacent approval record.
2. Treat the approved file content and digest as frozen. A security-semantic change requires a new review and approval before downstream work resumes.
3. Create the implementation plan only after the freeze. Task 0 of that plan must verify the exact security-contract digest and approval record before any production or test mutation.
4. Map every implementation task and Definition of Done claim to a section of this contract and a named executable evidence artifact.
5. Include a final variable-inventory sweep and an explicit check that the Plan 9.97 isolation sentence remains unchanged.

The implementation plan may decompose work, name exact files, order TDD steps, and specify verification commands. It may not relax this contract, invent an unlisted exception, or replace a real dependency with a fake at the evidence tier.

## Design Completion Criteria

- The provenance limitation is explicit and the policy authorizes exact effective content instead.
- Secret and non-secret settings, Redis, monotonic limits, the model exception, bind settings, and unknown variables have exhaustive fail-closed policies.
- Approval authorship, workspace binding, integrity, record size, expiry, revocation, concurrency, one-shot handoff, headless use, and TOCTOU behavior are concrete.
- The approval store bootstraps independently of gated `OPTIMUS_CONFIG_ROOT` and inherited user-directory variables.
- Elevated diagnostics provide useful correlation without a literal-secret redaction bypass.
- Every project-controlled persistence/export surface is covered by the shared sanitizer contract.
- Real-`acpx` capture sanitizes before disk and the joined transcript is scanned before promotion.
- The same-user credential-store and correlation-oracle residual risks are disclosed rather than overstated.
- The variable registry is mechanically bound to all `OPTIMUS_*` source references.
- Security-contract approval and digest freeze precede implementation-plan creation.
