# Independent Audit — A2A Ledger Risk-Bearing Slice (preserved record)

Preserved from gitignored `.superpowers/sdd/a2a-audit-independent-findings.md` on 2026-08-12.
Audited commit `e5f7e339`. Author: Codex (independent auditor). Reviewer: n/a — this is the audit itself.

**Current authority:** this is the authoritative independent audit. Its verdict — NOT SOUND
AS A SHIPPED, TRUSTED SLICE — stands. Remediation is scoped but **not scheduled**.

The region between the PRESERVED-BODY markers below is byte-identical to the source and
must not be edited. Any later material (for example a custody manifest) goes **outside** it.

<!-- PRESERVED-BODY-START -->
# Independent Audit — A2A Ledger Risk-Bearing Slice

**Audit date:** 2026-08-12  
**Auditor:** Codex (independent of the Cursor implementation and Claude task review)  
**Branch:** `agent/codex/a2a-ledger-independent-audit`  
**Audited commit:** `e5f7e33929efb8b2e3a85d429aa4d0d0b8bc9e2c`  
**Base verification:** `HEAD == origin/main == merge-base(HEAD, origin/main)`  
**Platform:** Windows (mandatory platform); no WSL result is used as primary evidence  
**Verdict:** **NOT SOUND AS A SHIPPED, TRUSTED SLICE**

The implementation contains useful, tested building blocks, but the committed product cannot be
provisioned into the secured system described by the frozen design. More importantly, several
security properties that define the risk-bearing slice—durable integrity failure, recipient
confidentiality, mandatory redaction, coherent delivery snapshots, least privilege, and
independently reproducible evidence—are absent or bypassable in the shipped configuration. The
slice should not be trusted for A2A handoff until the Critical and High findings below are fixed and
re-proven from a clean installation.

## Independence and evidence boundary

This section and all findings through **Independent conclusion** were completed before the sealed
reviewer findings were opened.

- The sealed file `.superpowers/sdd/a2a-audit-SEALED-reviewer-findings.md` was not read, searched,
  previewed, hashed, or supplied to any sub-auditor before this independent findings list was
  complete.
- The pre-existing reviewer checkpoint for the original A2A review was not read. The audit used the
  frozen design, both implementation plans, current source and tests, Git history, CI workflow, and
  the read-only external capstone archive.
- Frozen-artifact SHA-256 values were independently checked:

  | Artifact | SHA-256 |
  |---|---|
  | Frozen design | `B792B80F66ACB79F8521DF2EEB7944445DCBD34FCB2B959F2F8751D18B75EAFF` |
  | Historical v1 plan | `C93D2EE4C0DC6B8B9FE026EAEE60F317D5551F256A9FE7318FF15A6F1CD381BB` |
  | Live v2 plan | `DE7D2E9CFBD2004A154CC217A218C95906E6BD999A58960A3BA301938D748607` |

- No production source or digest-pinned document was modified. No live Docker container,
  PostgreSQL instance, service, keyring entry, or native agent was started, so there was nothing to
  tear down. This was not a discretionary omission: no committed start-to-finish operator
  procedure exists to follow, which is Finding 1.
- All dynamic security probes were local, bytecode-disabled/fake-boundary probes or package builds.
  Temporary directories were removed. The external archive was read-only and remained unchanged.
- Windows baseline command:

  ```text
  uv run --frozen pytest tests/unit/evidence_handoff tests/unit/evidence -q
  486 passed, 2 skipped in 37.34s
  ```

  This establishes that the existing unit suite is green; it does not rebut the composition,
  packaging, concurrency, production-wiring, or evidence findings below.

## Ranked findings

### Critical 1 — No shipped composition root or runbook can provision the claimed product

**Evidence**

- The frozen design makes the lifecycle manager responsible for starting, stopping, status,
  initialization, migrations, and health for both PostgreSQL and the MCP service
  (`docs/superpowers/specs/evidence-handoff-a2a-ledger-design.md:135-141`).
- `evidence-handoff-lifecycle` exposes only `start`, `stop`, `status`, and `health`; it requires six
  filesystem roots and an already-created password file
  (`src/evidence_handoff_runtime/lifecycle_cli.py:18-45,84-97`).
- `LifecycleManager.start()` starts Docker PostgreSQL and writes `ledger_instance.json`
  (`src/evidence_handoff_runtime/lifecycle.py:143-190,250-258`). Its method named migration only
  executes `SHOW server_version`.
- Production call-site searches found no caller for `apply_migrations`, `LedgerService.start`,
  `CredentialIssuer`, `IntegrityMonitor`, `RecoveryManager`, or the lifecycle signing-key resolver.
- The integration fixture manually supplies every missing composition step: start PostgreSQL, apply
  migrations, construct the store, initialize metadata, create enrollments and an issuer, and start
  the service (`tests/integration/evidence_handoff/test_authenticated_service.py:80-155`).
- Neither `README.md` nor `docs/runbooks/` contains an A2A ledger operator procedure. The plan says
  the operator provisions three credentials/configures clients, but supplies no commands or data
  schema (`archive/evidence-handoff-risk-bearing-slice-implementation.md:752-755`).

**Root cause:** tested components were never joined by a production composition root or operational
contract.

**Impact:** following committed documentation from nothing can at most produce a bare PostgreSQL
container that reports `store_ready`. It cannot produce a migrated, authenticated MCP ledger; issue
credentials; configure principals; run full readiness; start/stop the MCP service; or remove the
installation. Security controls exercised by hand-built fixtures are not evidence that the shipped
product reaches them. This divergence is silent; the custody pool instead calls the slice Closed.

### Critical 2 — Integrity detection, durable latching, and readiness are not wired into production

**Evidence**

- The service child creates a raw `PostgresLedgerStore` with no `control_root`
  (`src/evidence_handoff_runtime/service.py:314-351`) and passes it directly to delivery/policy.
  `IntegrityMonitor`, the only component that persists the external latch and DB mirror
  (`integrity.py:223-312`), has no production construction site.
- `LedgerService.start()` waits for a TCP port; it does not invoke full chain verification. The
  design requires genesis/recovery-anchor-to-head verification before traffic
  (`evidence-handoff-a2a-ledger-design.md:328-335`).
- `verify_unfiltered_range()` can raise a `LedgerIntegrityError`, but the service converts that to an
  error response without constructing/persisting an incident. An append counter/head fault is a
  plain `LedgerStoreError` and is likewise not latched.
- A production-shape fake-store probe produced:

  ```text
  detection_exception ledger_integrity_failed
  detection_mirror_calls 0
  detection_token_calls 0
  ```

  The failing request avoided a token, but no durable side effect occurred—the exact guard the
  design requires was not reached.
- `health_from_control_root()` loads a valid latch but discards the returned incident and reports
  `ready=True, code=ok` (`service.py:180-192`).
- Malformed DB latch JSON is treated as no incident (`store.py:841-872`). Because the production
  store has no control root, it cannot fall back to the lifecycle-owned file latch. Probe result:

  ```text
  malformed_mirror_latched False
  production_file_latch_visible False
  attached_file_latch_visible True
  ```

- On an already latched store, a caught-up/empty read skips verification, issues a token, and
  confirmation consumes it and advances the cursor (`delivery.py:122-183`). Probe result:

  ```text
  latched_empty_token_calls 1
  latched_empty_refuse_calls 0
  latched_confirm_consume_calls 1
  latched_confirm_cursor_calls 1
  latched_confirm_refuse_calls 0
  ```

**Root cause:** integrity enforcement is incidental to selected store methods rather than a
mandatory operation-entry guard, and the monitor is dead production code.

**Impact:** a request can detect corruption without making the service remain stopped; later
appends/reads can proceed, a restart does not reliably preserve the hold, and status can say ready
despite a valid latch. This contradicts the frozen requirement to latch detection durably and stop
append, read, delivery confirmation, cursor advance, and acknowledgement
(`design.md:649-663`). The narrower empty-unread defect is recorded in the pool, but the absent
production monitor/readiness and fail-open latch composition are silent.

### Critical 3 — First-run signing-key custody is circular through the only lifecycle path

**Evidence**

- `LifecycleManager.start()` creates `ledger_instance.json` before any signing-key resolution
  (`lifecycle.py:183-185,250-253`).
- `LifecycleManager.resolve_installation_signing_key()` requires a store fact, while the lower-level
  custody rule permits minting only when both durable instance facts are absent
  (`lifecycle.py:285-314`; `signing_key_custody.py:63-86`).
- Isolated lifecycle-boundary probe:

  ```text
  START=store_ready
  INSTANCE_FILE=True
  CUSTODY_AFTER_START=signing_key_mint_forbidden
  ```

- The live custody test avoids the shipped sequence by directly calling the lower-level resolver
  before lifecycle start (`tests/integration/evidence_handoff/test_signing_key_custody_restart.py:83-89`).

**Impact:** the lifecycle-owned API cannot bootstrap its first durable key after the only exposed
start operation. DoD criterion 3 passed because the test used a sequence that no production
composition or operator command exposes.

### High 4 — Direct `review_ruling_read` bypasses recipient visibility and integrity

**Evidence**

- The policy authenticates `ledger.read` but discards the returned principal, accepts a
  caller-selected global sequence, and invokes `get_entry_by_sequence`
  (`policy.py:265-318`).
- The query returns `entry_id`, sequence, ledger instance, and content digest for any sequence; it
  applies no recipient predicate and no verified global-range read (`store.py:354-374`).
- A real credential/session boundary probe for an outsider whose agent ID was not a recipient
  returned the hidden entry metadata and performed one store read:

  ```text
  {'entry_id': 'hidden-entry', 'sequence': 7,
   'ledger_instance_id': 'inst', 'content_sha256': 'ffff…'}
  store_reads 1
  ```

**Impact:** any enrolled read principal can enumerate whether hidden entries exist and obtain their
commitments. This violates the explicit rule that the service must not disclose hidden-entry
commitments, existence, or count (`design.md:337-341`) and also bypasses the latched read guard. The
unit test checks only that body text is absent, not recipient authorization. This divergence is
silent.

### High 5 — Mandatory redaction is type-fail-open at the policy/store seam

**Evidence**

- `attempt_review_ruling_append()` treats any sanitizer result without an `ok` attribute as success
  because `getattr(sanitized, "ok", True)` defaults to true, then passes that object to persistence
  (`policy.py:213-234`).
- An unsanitized `EntryDraft` exposes the fields consumed by the append path. A fake ingress that
  returned its input draft produced:

  ```text
  append_called true
  persisted_type EntryDraft
  raw_text RAW-SECRET
  sequence 1
  ```

**Root cause:** the policy checks for one rejection shape but never requires the success type to be
`SanitizedDraft`.

**Impact:** a sanitizer contract regression, adapter mistake, or wrong injected dependency can send
raw content to persistence. This contradicts mandatory in-memory structured ingress/redaction
(`design.md:170-178,184-187,425-429`). A thrown sanitizer exception does correctly prevent
persistence; the defect is the accepted wrong success type. Silent.

### High 6 — A normal read is not one coherent snapshot and can mint a contradictory token

**Evidence**

- Status, durable cursor, and head witness are fetched in separate calls/connections, followed by
  separate range verification and token insertion (`delivery.py:94-158`;
  `store.py:336-352,433-526,550-592`).
- `head_witness()` labels its separately sampled value verified. A controlled concurrent-append
  probe returned:

  ```text
  page_watermark 1
  token_witness_sequence 2
  token_issued true
  ```

**Impact:** an append between status and head reads can produce a token whose cursor watermark is 1
but whose resulting witness is for head 2. Confirmation stores an incoherent anchor and can make the
next legitimate read report a false chain break. This violates the design’s single-snapshot read
and token/cursor contract (`design.md:328-335,489-502,511-520`). Silent.

### High 7 — The built wheel omits every SQL migration

**Evidence**

- Packaging discovers packages under `src` only (`pyproject.toml:82-84`), while runtime migration
  lookup points to repository-top-level `migrations/evidence_handoff`
  (`migrations.py:11-12,67-74`).
- A wheel built from an explicit clean Git archive reported:

  ```text
  WHEEL=optimus_cost_agent-0.1.0-py3-none-any.whl
  ENTRY_COUNT=209
  MIGRATION_ENTRIES=0
  PACKAGE_RUNTIME_ENTRIES=23
  TEMP_REMOVED=True
  ```

- The equivalent source-tree migration/CLI tests passed (`8 passed in 2.63s`) because the checkout
  provides the missing top-level files.
- CI’s noneditable verifier tests the Optimus agent/gateway entry points, not either ledger console
  script or migration loading (`tools/verify_plan99_noneditable_install.py:264-283`).

**Impact:** even a manually composed installed ledger cannot initialize its schema. `uv build`
proves a wheel can be produced, not that the ledger product is contained in or runnable from it.

### High 8 — The public service CLI can launch an authenticated-looking stub

**Evidence**

- `--auth-bundle-file` is optional. Without it, the CLI calls `build_asgi_app(...,
  auth_bundle=None)` (`service_cli.py:18-34,51-65`).
- That path registers stubs for all advertised tools (`service.py:454-466`).
- When no validator is present, authorization degrades to presence-only checking; any nonempty
  Bearer value passes (`auth.py:239-242`).
- Probe result: `ALLOWED=True CODE=ok`, while the selected tool path had no database-backed ledger.

**Impact:** an operator can start a service that appears healthy, advertises the ledger surface, and
accepts arbitrary Bearer text but has no persistence or real policy behavior. This is a dangerous
false-success mode, especially because no runbook explains the distinction.

### High 9 — The service runs with the lifecycle/database-administrator credential

**Evidence**

- The only configured DB identity is `store_admin_user/store_admin_password`; Docker uses it as
  `POSTGRES_USER/PASSWORD` (`config.py:98-99`; `backends.py:133-143`).
- `LedgerService.start()` copies the source store’s exact connection string into its child auth
  bundle, and the child constructs its store with it (`service.py:228-245,348-351`).
- No runtime/migration statement creates a service role or applies `GRANT`/`REVOKE`.

**Impact:** compromise of the network-facing service grants the infrastructure/admin authority the
frozen design expressly withholds from request handlers (`design.md:137-141,163-168`). This is a
silent, material trust-boundary failure.

### High 10 — The surviving capstone is an unsigned assertion bundle, not proof of three native clients

**Evidence**

- The archive contains only three unsigned JSON files—no raw MCP transcript, DB/audit export,
  signed receipt, certificate/public key, MAC, or detached signature.
- Every process identity is explicitly `asserted:*`; the manifest says identity is asserted and
  “NOT cryptographically proven.” Claude version/client metadata was not captured.
- `manifest.py:85-107` checks that digest/fingerprint/identity strings are truthy; it does not
  recompute them, validate digest format, or verify signatures. Runtime bearer validation proves
  possession of a service-issued HMAC credential, not which native executable possessed it.
- Fresh archive hashes are:

  | File | SHA-256 |
  |---|---|
  | `task6-manifest.json` | `5F9E5FE4CDECFE4DF3C51E80C1F79AACA1F9019DEAF261C32A9A67C8F5F7DB70` |
  | `task6-integrity-latch.json` | `28E88C831A8B1014A17D9D56888617DF90184C92F884141D3979DC79C03992F2` |
  | `task6-session-info.json` | `38219A4160B5EA9823281BA3481089F642DE0F961D3A2B8BD23747E8E851AE56` |

- The files agree on instance, endpoint, container, and incident IDs. The manifest hash matches the
  committed eight-hex prefix. That is internal corroboration and a 32-bit historical fingerprint,
  not authenticated provenance. Relevant closure commits are unsigned.

**Impact:** the archive supports the statement “an operator recorded three sessions with internally
consistent outcomes.” It cannot prove that Claude Code, Cursor, and Codex executables originated
those operations. Verified executable identity and cryptographic non-repudiation are explicit
non-goals (`design.md:65-68,893-896`), so the defect is the strength of the evidence/sign-off claim,
not a missing promised identity primitive.

### High 11 — The capstone verifier can pass without proving cross-agent delivery or service liveness

**Evidence**

- The frozen scenario requires `explicit_recipient_delivery_reaches_other_agents`; it is absent
  from `REQUIRED_OUTCOMES` (`three_agent_scenario.json:40-48`;
  `tools/evidence_handoff_live_support/verify.py:15-23`). The archive does not contain that outcome.
- The verifier trusts client names and outcome labels from the same manifest. It does not bind page
  confirmation to a nonempty page, recipient IDs, or the original append.
- `service_endpoint` receives only URL syntax validation; the verifier never connects to it.
- An adversarial read-only copy of the archive, renamed as expected, was verified against the
  deliberately dead endpoint `http://127.0.0.1:1/mcp`; the verifier returned exit 0 and
  `"passed": true`. The temporary copy was removed.
- The checked v2 plan command omits the CLI’s required repeated `--expected-agent-id` arguments, and
  the archive filename is `task6-manifest.json` while the verifier hardcodes `manifest.json`
  (`implementation_v2.md:551-556`; `tools/verify_evidence_handoff_live.py:62-68`;
  `verify.py:78-86`).

**Impact:** the surviving artifact and its verifier do not establish the scenario’s central
recipient-delivery claim, a live service, or independently authored client participation. The
checked command is not reproducible from the archived bytes as recorded.

### High 12 — The Definition of Done admitted false greens and does not match CI

**Evidence**

- Task 5 acceptance review remains unchecked (`implementation_v2.md:508-512`), yet all six DoD
  boxes are checked and closure says PASS (`:592-610`).
- The named default integration command exited 5 with all 34 tests deselected, yet its step is
  checked (`:444,456-459`). This violates the repository’s checkbox protocol: a command that did
  not pass cannot justify `[x]`.
- The post-closure addendum records CI finding a latent Bandit failure and a fail-open mirror-write
  defect. The latter was fixed in `c963416`; it is historical evidence that closure gates were
  insufficient, not a claim that the exact swallowed exception remains current.
- Current false-green examples include the low-level key-custody test bypass, checkout-relative
  migration tests, dead production monitor, and unauthenticated service stub.
- Gate-list comparison:

  | Area | Plan | `.github/workflows/guardrails.yml` |
  |---|---|---|
  | Clean/install | `uv build`; no clean ledger install execution | `uv sync --all-extras`; wheel build plus a noneditable verifier that does not cover ledger entry points |
  | Hygiene | Not listed | Four pre-commit hygiene hooks |
  | Security | Ruff + detect-secrets | Ruff, Bandit, ast-grep, prompt-injection scan, detect-secrets |
  | Secret scope | `src tools` | `src` only |
  | Coverage | Five production trees | `--cov=optimus` only |
  | Lock/diff | `uv lock --check`, `git diff --check` | Neither |
  | Live tiers | Docker/keyring/native-agent evidence | Default marker expression deselects live tiers |

- The addendum itself wrongly describes detect-secrets as absent although plan line 448 already runs
  it, and it omits CI’s noneditable/hygiene mismatch.

**Impact:** DoD PASS is not a sound trust decision. Neither the plan nor CI is a superset of the
other, and neither executes the installed A2A product from scratch.

### High 13 — Linked-replacement full verification hardcodes ordinary genesis

**Evidence**

- Recovery creation correctly seeds a replacement anchor, and first append can continue it
  (`store.py:782-820,221-277`).
- `_audit_through_head()` nevertheless initializes `prev_digest=None`, starts at sequence 1, and
  never loads replacement genesis metadata (`store.py:899-970`). `find_last_verified_anchor()` has
  the same ordinary-genesis assumption.
- A valid replacement anchored at sequence 2 with no local rows produced
  `ledger_integrity_failed / sequence_gap / safe_boundary_sequence=0` in a fake-DB boundary probe.

**Impact:** the required recovery path can create a replacement instance that its own full
readiness/audit rejects. This contradicts declared-genesis-or-recovery-anchor verification
(`design.md:323-335,694-703`) and is not covered by the integration test, which appends a first
replacement row but does not full-audit the replacement. Silent.

### Medium 14 — Secret bundle deletion and restrictive permissions fail open

**Evidence**

- The service child swallows failure to delete the auth bundle containing signing key and DB
  connection information, then starts the server (`service_cli.py:51-65`). Parent cleanup is also
  best effort, and `_write_json_private()` swallows chmod failures (`service.py:149-160,305-310`).
- A fake-path probe forced `unlink` to raise and observed `serve_rc=0` and
  `uvicorn_run_called=true`.

**Impact:** a service can run while high-value credentials remain on disk with permissions that
were never proven restrictive. This contradicts the plan/design’s ephemeral-secret intent. The
correct behavior is to fail closed or use an OS primitive whose protection is verified.

### Medium 15 — Lifecycle/status and instance-file corruption are unsafe or misleading

**Evidence**

- Lifecycle `_running` is process-local. Every CLI command constructs a new manager, so a second
  process reports `store_not_running` while `health` reports true:

  ```text
  FIRST_START=store_ready
  NEW_PROCESS_STATUS=store_not_running
  NEW_PROCESS_HEALTH=True
  ```

- An unreadable/malformed `ledger_instance.json` is treated as absence; start generates and
  overwrites a new UUID without first reconciling the DB instance (`lifecycle.py:418-429,250-253`).

**Impact:** automation cannot trust status across ordinary invocations, and corrupted control
metadata can be silently replaced instead of classified as an instance/integrity failure.

### Medium 16 — Required audit, resource bounds, and typed integrity status are missing

**Evidence**

- `AuditRecorder` has no production construction site; the service append call omits the optional
  audit argument. Transport/auth/session/delivery/integrity have no recorder composition, apart
  from a narrow principal-retirement DB event.
- Only `max_body_bytes` is enforced. No pre-parse rate or concurrency limiter exists, contrary to
  `design.md:244,848-849`.
- Although `Availability.INTEGRITY_FAILED` exists, control/lifecycle state report an incident as
  `Availability.UNAVAILABLE` (`control_state.py:26-34`; `lifecycle.py:451-462`). This collapses the
  distinguished non-retryable integrity outcome the design requires (`design.md:640-647`).

**Impact:** mandatory observability is not produced, resource exhaustion remains unbounded at the
application layer, and typed consumers can confuse corruption with ordinary unavailability.

### Medium 17 — The authoritative pool is factually stale and overstates closure

**Evidence**

- The pool says Closed at `72c3b82`, 21 commits through that tip, and “no PR opened.” At that commit
  the row was still Promoted and all DoD boxes were unchecked.
- Closure was recorded at `99922ee`; `c963416`, `f46165a`, and `658042d` followed. PR #128 and PR
  #129 merged the slice/follow-up, and all 25 inclusive feature commits through `658042d` are on
  main.
- The same row claims Redis/LAN evidence although the delivered product is PostgreSQL/loopback and
  the surviving capstone identifies those local endpoints. Other rows still call the slice and
  Task 6 “in-flight.”
- Pool wording suggests all six entry kinds are in the closed surface; the frozen risk-bearing slice
  intentionally implements `review-ruling` append/read only (`design.md:788-790`). The other five
  kinds belong to protocol completion and are not independently defects in this slice.

**Impact:** the declared custody source misstates the actual closure/merge history and encourages an
operator to infer a broader, differently deployed product. This is the warned factual error plus
additional freshness drift.

## Frozen-design conformance: recorded versus silent

| Design divergence or limitation | Current status | Custody |
|---|---|---|
| Docker-only backend instead of frozen wslc-primary ladder | Current divergence | Recorded in v2/pool design refresh |
| Session protocol Option A rather than strict negotiated-version behavior | Current divergence | Recorded in v2/pool |
| Empty-unread delivery can issue a token while latched | Current defect | Recorded in pool, but broader integrity wiring is not |
| Behind-cursor/history tamper is not rechecked periodically | Current defect/limitation | Recorded under at-rest integrity |
| OAuth discovery, `WWW-Authenticate`, rotation/revocation interoperability | Deferred | Recorded credential-lifecycle work |
| Five non-`review-ruling` entry kinds | Deferred by slice boundary | Recorded in frozen delivery chunks; not a slice defect |
| Product composition/runbook, full readiness, monitor wiring | Missing | **Silent** |
| Recipient-filtered direct read | Missing | **Silent** |
| Sanitizer success-type enforcement | Missing | **Silent** |
| Coherent read transaction/snapshot | Missing | **Silent** |
| Least-privileged service role | Missing | **Silent** |
| Recovery-anchor-aware full audit | Missing | **Silent** |
| Production audit recorder, rate/concurrency limits | Missing | **Silent** |
| Installed migrations/ledger entry-point proof | Missing | **Silent** |

## Security controls: what is reachable

When a knowledgeable developer manually constructs the authenticated service—as the tests do—the
following controls are real and correctly ordered in the paths examined:

- closed server-derived identity fields, reviewer-only write policy, and recipient validation occur
  before ingress/store;
- sanitizer exceptions stop persistence;
- present Origin, Host, protocol, request-size, authentication, and session checks run before MCP
  parsing; absent Origin does not bypass authentication;
- unknown/expired/principal-mismatched presented sessions are rejected;
- no network-callable collector/capture tool is advertised;
- screenshot promotion rechecks the approved digest;
- portable evidence-handoff code does not import Optimus infrastructure/authorization callbacks;
- the feature is default-off and Docker loopback binding rejects non-`127.0.0.1` configuration.

Those are genuine controls, but they do not rescue the shipped composition. The product entry
points do not create the secured service, the stand-alone service path can select stubs, and the
production-authenticated child omits the integrity monitor, control-root latch, application DB role,
audit recorder, and full readiness gate.

## What the evidence proves—and does not

**Proves/corroborates:** the three surviving files currently have the hashes above; their fields are
internally consistent; the manifest carries three asserted client labels and expected-looking
outcome strings; the operator recorded a plausible latch/warning chronology; the current verifier
can validate that internal schema/string consistency.

**Does not prove:** that the endpoint was live when verified; that the named native executables
originated requests; that each used a distinct credential; that the acknowledged pages were
nonempty or recipient-correct; that one client’s append reached another; that the DB rows, audit
records, redaction results, and cursor transitions existed; or that the archive was generated by
the claimed service rather than authored consistently after the fact.

This distinction matters because the design deliberately does not promise verified executable
identity, same-user adversary resistance, or cryptographic non-repudiation. The archive can be
honest corroboration without being independent cryptographic evidence.

## The operator’s complaint: broken behavior versus assumed behavior

**Actually broken as delivered:** clean provisioning; key bootstrap; installed migrations;
production integrity/readiness/latch behavior; recipient confidentiality on direct reads; sanitizer
type safety; coherent delivery snapshots; least-privileged DB access; replacement audit; reliable
status; secret cleanup; audit/rate/concurrency controls; and reproducible capstone verification.

**Assumed but never promised:** automatic agent wakeup, real-time relay, peer liveness, verified
native-process identity, cryptographic non-repudiation, resistance to a malicious same-OS-user, and
the other five protocol entry kinds in this risk-bearing slice. Failure to provide those features is
not an implementation defect. Presenting the capstone as stronger evidence than the non-goals allow
is nevertheless an overclaim.

There is also a current Cursor interoperability limitation in the pool: OAuth discovery is gated
and 401 responses omit `WWW-Authenticate`. The unsigned archive cannot establish that stock Cursor
tool discovery works generally; at most it records a probe/session that the operator labeled
Cursor.

## Required remediation before trust

1. **Build one fail-closed composition root and runbook.** It must provision the application role,
   resolve first-run key custody in a valid order, apply packaged migrations, initialize metadata,
   enroll/issue credentials, full-audit readiness, start/stop the real service, expose truthful
   cross-process status, and document cleanup/recovery.
2. **Make integrity state an unavoidable service boundary.** Construct the monitor in production;
   verify the full declared genesis/recovery anchor before accepting traffic; latch every detected
   chain/counter/instance fault; reject corrupt latch representations; guard append, all reads,
   delivery confirmation/cursor/acknowledgement at operation entry; and report the distinct typed
   state.
3. **Close data-path authorization and atomicity holes.** Remove or recipient-filter/chain-verify
   direct reads; require `SanitizedDraft`; execute status/range/witness/token creation in one
   consistent transaction/snapshot; make replacement audits anchor-aware.
4. **Restore privilege and secret boundaries.** Create a least-privileged service DB role; make the
   no-auth stub explicitly test-only and impossible from the public CLI; fail closed on bundle
   protection/deletion failures.
5. **Make the installed artifact self-contained.** Package migrations and test both ledger console
   scripts plus schema application from an isolated wheel, not a repository checkout.
6. **Replace assertion-only capstone sign-off.** Preserve raw independently authored MCP-client
   transcripts or server-signed receipts plus DB/audit extracts; bind client, request, entry,
   recipient, page/token, and confirmation; require the cross-agent recipient outcome; probe the
   endpoint; archive exactly the filename/layout the verifier consumes; publish full digests.
7. **Reopen DoD.** Reconcile the plan and CI into one explicit gate inventory; require every checked
   command to exit 0 with the intended tier actually selected; execute a clean Windows operator
   walkthrough and installed-package run; then perform documentation-freshness review.

## Independent conclusion

The correct trust decision is **not sound**, not merely “documentation could be better.” The unit
suite demonstrates substantial component work, and several perimeter controls behave correctly
when experts manually compose the service. But the deliverable advertised as a closed risk-bearing
slice has no production path to that configuration and fails multiple core invariants once assessed
at the real composition boundary. The highest-value corrections are Findings 1–6; evidence and DoD
must then be regenerated rather than retroactively reinterpreted.

---

## Sealed-review differential

**Ordering record:** the independent portion above was complete at 32,387 bytes and SHA-256
`050668C6AFB641B5826A88932FE6641777366D85D93CBB145618036D8A515336` before the sealed file was
opened. The sealed file was first read at `2026-08-11T22:56:39Z`; its unchanged bytes are 4,350
bytes with SHA-256 `510E110750F2A8B1079DB8F339BDD69D1BFC22DF0EC9E0336D5103F85EF9CE44`.

### Material findings this independent audit found that the sealed review missed

These are the highest-value results of the independent pass:

1. **The product has no composition root, not merely an untried runbook.** The sealed review knew
   nobody had provisioned from scratch, but did not identify that the lifecycle command cannot
   possibly do so: it launches only PostgreSQL, does not apply migrations, initialize metadata,
   resolve key custody, enroll/issue credentials, full-audit readiness, or start/stop the MCP
   service. This turns a process concern into a Critical shipped-architecture blocker.
2. **First-run signing-key custody is circular.** The only exposed start sequence creates the
   instance fact that then forbids first minting; the live test bypasses the lifecycle API by
   resolving the key first.
3. **The wheel omits all migrations.** Source-tree tests conceal this, and the CI noneditable
   verifier does not exercise the ledger entry points.
4. **The public service CLI admits a false-success stub**, while any nonempty Bearer passes its
   presence-only fallback.
5. **There is no least-privileged service DB identity.** The network-facing service receives the
   lifecycle/PostgreSQL administrator connection string.
6. **The current integrity system is still not composed.** The sealed review found/fixed a narrow
   DB-mirror lookup defect, but missed that production never constructs `IntegrityMonitor`, never
   runs full readiness, does not latch newly detected read/append faults, ignores a valid latch in
   service health, treats malformed mirror data as no incident, and permits confirmation/cursor
   change while latched. This is broader and more severe than the known empty-read bypass.
7. **Direct `review_ruling_read` discloses hidden entry existence and commitment** to a non-recipient
   and bypasses verified delivery/integrity.
8. **Mandatory redaction is type-fail-open.** A wrong sanitizer return type such as the original
   `EntryDraft` is accepted and persisted.
9. **Normal read/token creation is not one coherent snapshot.** A concurrent append can mint a
   token whose watermark and chain witness refer to different heads.
10. **Recovery full audit does not understand a linked replacement anchor**, so a valid replacement
    can fail its own required readiness/audit.
11. **Secret-bundle deletion and private-permission failures are swallowed**, allowing the service
    to run with key/DB material left on disk.
12. **Cross-process status is false and corrupt instance metadata is overwritten as absence.**
13. **Production audit recording, pre-parse rate/concurrency limits, and distinct typed integrity
    status are missing.**
14. **The capstone verifier omits the explicit cross-recipient outcome and can pass against a dead
    endpoint.** The archived layout/checked command are not directly reproducible, and the archive
    contains no raw/signed evidence binding an append to another agent’s nonempty delivery.
15. **DoD had additional concrete false-green mechanisms:** an unchecked acceptance-review step,
    an integration command that exited 5/all deselected but was checked, materially asymmetric
    plan/CI coverage, and no clean installed-ledger execution.
16. **Pool drift is broader than the three warned Git facts:** Redis/LAN wording is unsupported by
    the PostgreSQL/loopback artifact, “in-flight” rows remain stale, and six-kind wording overstates
    the deliberately one-kind risk slice.

### Items the sealed review listed that this audit did not independently elevate

- **Three historical protocol interop defects** (single-value admission, doubled-header parsing,
  and default-versus-negotiated session version) were not raised as current findings because the
  current source/plan records their fixes and this audit found no contrary current behavior. I agree
  they were real historical defects and useful evidence of iterative live construction.
- **The reviewer’s `$?`-after-a-pipe error** was not independently identified as its own finding.
  After opening the sealed file, it is corroborated by the live v2 plan at lines 642–646. I agree it
  is a real review-process failure and a concrete reason not to trust the original bandit ruling.
- **The old `control_root=None` latch lookup failure and swallowed mirror exception** are real
  historical defects. Current code does call the DB mirror directly, so I agree those exact code
  shapes were repaired. I do not agree that this repaired the integrity property as a whole; see
  the current composition failures above.
- **The expectation-gap framing** is correct in part. I agree that automatic wakeup, liveness,
  cryptographic executable identity, and a persistent real-time communication channel were not
  promised by the frozen risk slice. The implementation is nevertheless broken against the
  narrower ledger/read/delivery/integrity promises it did make.

### Statements in the sealed review that are wrong or materially incomplete

1. **“Detect-secrets was CI-only / absent from the plan” is false.** The plan already runs
   `detect-secrets-hook` at line 448. The real mismatch is broader: CI adds noneditable package and
   hygiene checks plus Bandit/ast-grep/prompt scanning, uses a narrower secret path, covers only
   `optimus`, and omits plan lock/diff gates. The plan addendum repeats the same detect-secrets
   mistake.
2. **Calling the production latch failure “fixed by reading the DB mirror” is materially
   incomplete.** A valid pre-existing DB mirror can now block store methods that call the guard,
   but the production service does not create the monitor that writes the mirror on detection, its
   service store cannot see the external file, health ignores a valid incident, malformed mirror
   content fails open, and some read/confirmation paths never call the guard. The narrow lookup bug
   is fixed; the promised fail-closed integrity system is not.
3. **The sealed file names “Option B” as the shipped decorative session behavior.** The live v2 plan
   explicitly says **Option A is shipped** and Option B is not (`implementation_v2.md:529-538`). The
   underlying concern is real—current admission accepts any service-admitted version rather than
   enforcing the session’s exact negotiated version—but the option label is wrong.
4. **“Corroborated by DB side effects” is stronger than the surviving evidence permits.** The live
   DB is gone. The remaining unsigned JSON files assert internally consistent DB effects; they do
   not contain a DB export, signed server receipt, raw transcript, or audit record from which those
   effects can now be independently established. The reviewer may have observed them live, but that
   observation did not survive as independently verifiable evidence.
5. **The expectation gap does not explain the operator’s whole complaint.** It explains why agents
   did not wake or behave like a live message bus. It does not explain away the missing production
   composition, current integrity bypasses, hidden-entry disclosure, redaction type hole, or
   unverifiable cross-recipient capstone. Those are failures inside the approved slice boundary.

### Differential conclusion

The sealed review correctly remembered several historical interop/fail-open defects, the untried
from-scratch workflow, stale Git facts, and genuine non-goal/expectation gaps. It did **not** contain
the majority of the current architecture and security blockers found independently. Its most
important incorrect implication is that integrity fail-closed behavior was repaired: selected
helper methods were repaired, but the production service still does not compose or enforce the
system that those helpers were meant to protect.

<!-- PRESERVED-BODY-END -->
