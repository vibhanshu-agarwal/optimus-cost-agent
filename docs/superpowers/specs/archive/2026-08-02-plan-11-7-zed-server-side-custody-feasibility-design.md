# Plan 11.7 Zed Server-Side Custody Feasibility Design

**Status:** Operator-approved design, updated with the final review findings. The reviewer must
record the approval checkpoint before probe execution. Probe execution and any server-side custody
implementation remain unauthorized until their respective approval gates pass.

**Purpose:** Amend Plan 11.7 without changing its frozen file or orphaning its sealed Task 0
approval chain. The amendment will authorize one bounded feasibility probe that determines whether
Zed 1.13.1 exposes a durable, non-ambiguous signal by which a fresh `session/new` after a full Zed
restart can be correlated with one prior Zed-originated Optimus session rather than with a genuinely
new conversation in the same workspace.

**Decision boundary:** Approval of the amendment authorizes only the probe described here. A
successful probe returns to the operator for a separate go/no-go before any production or evidence-
pipeline implementation of server-side custody. `infeasible_for_production_target` is a valid
terminal result. No result from this probe authorizes Plan 11.7 Task 0 Steps 5-7 or Tasks 1-11.

## Authority and immutable trigger chain

The frozen implementation plan remains:

`docs/superpowers/plans/archive/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md`

Its authoritative Git-blob SHA-256 is:

`F52AD9A5A85DC50B0DFD3206B6BD09FD8FF0AE79B1A6049DF1017F978B1C462D`

Task 0 Step 1 sealed the operator approval against that exact digest. Editing or replacing the
frozen file would change the digest and orphan the approval-of-record already embedded in sealed
Steps 1-4 evidence. The amendment must therefore be a separate plan file. It may supersede the
blocked execution path only through explicit text and its own approval record; it must not modify
the frozen plan or its checkboxes.

The triggering Step 4 facts are immutable inputs:

- discovery disposition: `stop_amend_plan_session_load_unreachable`;
- discovery finding:
  `reports/plan-11-7-task0-artifacts/step4-discovery/discovery-finding.json`;
- sealed evidence report:
  `reports/plan-11-7-task0-artifacts/step4-discovery/evidence-report.json`;
- evidence-report-v1 SHA-256:
  `1579A5B1A84F1AE46C0B09B317F61B93D919E5E03725FFA8BD0F9F6BD32565BF`;
- pinned Zed target: Zed 1.13.1 at source commit
  `00bd72e7838f4b875a913cd112b47a0ebe1ca62b`.

The amendment approval must itself be represented by approver identity, UTC timestamp, and exact
amendment-file SHA-256. The reviewer records that triple in the existing gitignored
`docs/superpowers/reviews/plan-11-7-review-checkpoints.md`. The probe operator reads the log's
Current State first and verifies it against the files and Git objects on disk. The implementing
agent must not edit the reviewer-owned checkpoint log.

Hash methodology is part of the contract. Repository-controlled text uses authoritative Git-blob
bytes so Windows CRLF conversion cannot change the result. External binaries and promoted evidence
use raw on-disk bytes. The manifest records the method beside every digest.

### Amendment identity and ownership

The derived amendment has the fixed identity:

- title: `Plan 11.7 Standalone Zed Server-Side Custody Feasibility Amendment`;
- path:
  `docs/superpowers/plans/archive/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md`;
- owning roadmap entry: `P11-FEAT-ZED-RESUME`; and
- governance log: `docs/superpowers/reviews/plan-11-7-review-checkpoints.md`.

It allocates no new Plan 11.x number and creates no deferred or parallel ownership lane. It is the
standalone amendment required by the frozen Plan 11.7 Task 0 Step 4 stop rule. Its exact LF-byte
SHA-256 becomes authoritative only when the operator approves the identity + UTC + digest triple.

## Problem statement

Task 0 Step 4 proved that Zed 1.13.1 neither automatically restored the target session nor exposed
a usable manual reopen. After relaunch it cleared the stored session ID and did not issue
`session/load`. The two no-terminal predicates were proven before launch, so the result is not a
profile-seed confounder and cannot be classified as `profile_auto_restore_unsupported`.

The surviving architectural possibility is server-side custody of a Zed-originated session. That
does not mean correlating activity within one connection. The load-bearing question is whether,
after a **full Zed restart**, the fresh ACP connection and fresh `session/new` contain or are bound
to a durable signal that tells the server all of the following:

1. this is an attempted continuation of one exact earlier Zed-originated session;
2. it is not a request for a genuinely new conversation in the same workspace;
3. the signal is available at or before the new-session decision, before a new user prompt can be
   used as an accidental correlator;
4. the signal is within the existing launch and same-user trust model and cannot be substituted by
   ordinary prompt text, title text, timestamps, workspace root, or process proximity; and
5. a separately approved implementation could validate it without reading or injecting Zed profile
   state, returning an old session from `session/new`, or weakening ACP semantics.

Workspace identity alone fails this test. A policy such as "attach the newest session for this
folder" conflates continuation with a fresh conversation and is therefore an evidenced
`infeasible_for_production_target` result, not a candidate route.

## Goals

- Inventory every signal actually available to Optimus at `initialize` and `session/new` across a
  full Zed restart on the exact pinned target.
- Bind each observation to exact Zed, relay, Optimus, workspace, run, request, session, message, and
  Gateway identities without relying on timestamps or PIDs alone.
- Compare the restart/continuation attempt with a fresh-thread control in the same workspace whenever
  a candidate discriminator survives the initial inventory.
- Prove that the capture relay preserves both the byte stream and the inherited launch environment.
- Produce a sealed, independently verifiable result that is either a candidate route, target
  infeasibility, an explicit Zed crash stop, a dependency block, or a named invalid probe.
- Preserve independent real-`acpx` conformance as a mandatory requirement of any later Plan 11.7
  implementation amendment.

## Non-goals and explicit exceptions

- No edit to the frozen Plan 11.7 file or its checkboxes.
- No production change under `src/optimus`, `src/optimus_gateway`, or the Zed source tree.
- No durable-session implementation, `session/load` implementation, correlation implementation,
  render observer, Zed patch, registry submission, or client workaround.
- No claim that Zed can resume, that `session/load` is reachable, that rendering occurred, or that a
  model response was visually presented.
- No project-authored ACP client. Zed is the client in every live custody run.
- No profile injection, session-ID rewriting, old-session return from `session/new`, prompt copying
  between clients, UI automation, `SendInput`, or timestamp/PID-only correlation.
- No collector-originated prompt and no concurrent `acpx` session during a Zed observation interval.
- No plan-specific sanitization and no direct import of `tools.evidence_gather_support`.
- No screenshot requirement. If a screenshot is retained as optional corroboration, the merged
  redaction gate's existing explicit screenshot approval still applies and it cannot prove custody.
- No implementation authorization bundled into amendment approval, even after a feasible result.

## Probe architecture

### Independent records

The probe uses three records with distinct authorship:

1. **Passive relay record.** A scratch byte relay records the bytes Zed sends and the bytes Optimus
   sends, with direction, monotonic offset, chunk sequence, and SHA-256. It forwards the same bytes
   without ACP-aware behavior.
2. **Optimus debug record.** The existing `.optimus/debug-acp.ndjson` is emitted by Optimus, not by
   the relay. It records request/session/run progression and outbound update points.
3. **Process and launch record.** OS process snapshots plus the existing append-only launch audit and
   durable approval record bind the client, relay, and server processes to the authorized workspace
   and security snapshot.

No one record is sufficient. The live result is valid only when the relay transcript and Optimus
debug suffix agree on ordered request methods, request IDs, server-assigned session IDs, run IDs,
terminal response, and observation interval. A relay unit test proves the code's intended behavior;
this independent live cross-corroboration proves the observed run did not silently drop or reorder
traffic.

### Passive relay constraints

The relay is custody instrumentation, not an ACP client and not ACP-conformance evidence. It may:

- inherit the exact Zed-supplied environment;
- start the exact pinned Optimus executable with the exact original argument vector;
- connect its stdin/stdout to the child;
- forward opaque byte chunks in order;
- record direction, sequence, monotonic offsets, byte counts, and raw-byte digests in the protected
  raw bundle; and
- record its own executable/script digest, PID, start identity, parent PID, and child PID.

It may not:

- deserialize ACP to make a forwarding decision;
- create, retry, suppress, reorder, split semantically, merge semantically, or rewrite an ACP
  request, response, notification, or ID;
- add an environment variable, remove an inherited environment variable, change a value, read a
  secret value into normalized output, or substitute a different approval;
- modify cwd, executable, arguments, stdin EOF behavior, stdout/stderr routing, or exit status; or
- launch a fallback client or second Optimus server.

The relay may parse a completed, immutable copy of the transcript only after the child and capture
interval end. Parsing is used for structural projection and verification, never for live routing.

The relay is necessarily **not** transparent for process ancestry: Optimus's parent is the relay,
not Zed, in relay-mediated runs. The `Zed -> relay -> Optimus` chain proves capture custody but is not
production-representative ancestry. No parent PID, process topology, job relationship, or other
ancestry-derived signal may be ruled eligible from a relay-mediated run. If a correlation candidate
depends on process topology, the candidate must pass an additional full-restart control with Zed
launching Optimus directly, without the relay, before the probe may emit a feasible result. That
direct control uses the independent Optimus debug record and OS process snapshots; it does not
retroactively promote ancestry proximity into a thread-specific signal.

### Environment equivalence

`LaunchEnvironmentSnapshot.capture()` snapshots the Optimus child's inherited environment and the
launch gate derives `security_snapshot_digest` from that security state. The relay controls the
environment supplied to its child, so byte equality alone cannot establish transparency.

Before the cross-restart runs, the probe performs a direct Zed-to-Optimus launch control without the
relay. The direct control and every relay-mediated launch must consume the **same existing durable
approval record** and produce:

- the same approval ID and approval mode;
- `final_reason_code: AUTHORIZED` in the append-only launch audit;
- the same full `security_snapshot_digest` from the protected approval record;
- the same workspace digest, registry/policy versions, setting-decision names/tiers/source classes,
  monotonic dispositions, and child-propagation name sets; and
- no rejected or unclassified variable, including no probe-only `OPTIMUS_*` variable.

Because authorization requires the candidate digest to equal the durable record digest, successful
use of the same record by both paths is the production launch gate's own proof of exact security-
snapshot equivalence. The probe does not duplicate or approximate the digest algorithm. Environment
values and secret fingerprints remain inside their existing protected stores; normalized evidence
contains only digests, names, classifications, and outcomes already authorized for persistence.

Any mismatch is `invalid_probe_relay_environment_mismatch`. It is never a correlation result.

### Settings mutation and restoration

Pointing Zed at the relay requires a temporary edit to the applicable Zed `settings.json`. That is an
external state mutation and requires explicit operator authorization at probe execution time.

The probe must:

1. resolve the exact settings file and record whether it existed;
2. capture its pre-image bytes and SHA-256 in protected custody;
3. apply only the agent command/arguments change needed to insert the relay;
4. record the mutated-file SHA-256 and structured changed-key allowlist;
5. restore the exact pre-image bytes after every success, failure, timeout, or crash; and
6. prove the final existence state and SHA-256 equal the pre-probe state.

If the file did not exist, restoration means removing only the exact file created by the probe after
verifying its path and digest. No directory or unrelated setting may be deleted. Failure to restore
is `invalid_probe_settings_not_restored`, has precedence over every feasibility conclusion, and is
reported immediately to the operator.

## Probe phases

### Phase 0: Verify authority and the immutable trigger

The probe verifies the frozen-plan Git-blob digest, Step 4 evidence-report digest, discovery
disposition, amendment digest, amendment approval triple, existing checkpoint Current State, and
Git ancestry. It proves that the Plan 11.7 execution worktree has no production-source diff against
the approved baseline before any external launch or settings mutation.

Failure stops with `invalid_probe_trigger_chain_mismatch`. The probe must not attempt to repair,
re-seal, or reinterpret Steps 1-4.

### Phase 1: Reacquire the exact production target

The probe re-hashes what it actually executes. It does not inherit Task 0's identity table by
reference. Required identities include:

- installed Zed executable and launcher path, raw-byte SHA-256, FileVersion, and ProductVersion;
- Zed 1.13.1 source checkout commit
  `00bd72e7838f4b875a913cd112b47a0ebe1ca62b`;
- authoritative Git-blob hashes for `crates/agent_servers/src/acp.rs`,
  `crates/agent_ui/src/conversation_view.rs`, `crates/agent_ui/src/agent_panel.rs`, and every
  additional source file used to justify a candidate correlation signal;
- the exact Zed registry file digest and the selected Optimus command/argument structure;
- Optimus executable, package, current Git commit, and Git-blob hashes for
  `src/optimus/acp/server.py`, `src/optimus/acp/spec.py`,
  `src/optimus/acp/launch_policy.py`, `src/optimus/acp/launch_gate.py`, and
  `src/optimus/acp/debug_trace.py`; and
- real Redis TimeSeries and Gateway readiness identities needed for a real prompt, with credentials
  omitted from promoted output.

The pinned workspace must contain a readable regular file named `README.md` inside the authorized
workspace root. The probe records its relative path, raw-byte SHA-256, file identity, and pre-run
existence/readability result. A missing, unreadable, external, or path-retargeted README fails the
precondition before Zed launch; the prompt is never improvised against a different file.

An updated binary, source mismatch, missing source, ambiguous binary/source relationship, or
unavailable real dependency stops without a feasibility conclusion.

### Phase 2: Prove relay behavior and environment equivalence

Offline tests exercise empty input, arbitrary binary chunks, partial NDJSON lines, interleaved
full-duplex traffic, EOF, child exit, relay termination, and backpressure. For each direction the
input bytes, forwarded bytes, and captured bytes must be identical. Mutation-based verifier tests
must reject inserted, removed, changed, duplicated, and reordered bytes or sequence records.

The direct launch control and a relay-mediated launch then consume the same durable approval record.
The environment-equivalence fields above must match exactly, and both launches must be authorized.
The relay-mediated control's ACP traffic must also agree with its independent Optimus debug suffix.
If later phases identify an ancestry-dependent candidate, this phase is extended with the required
direct, non-relayed full-restart control before any feasible disposition.

### Phase 3: Capture origin session A

The operator launches one hermetic Zed instance on one digest-pinned workspace with no active or
restorable terminal and no unrelated Optimus thread. Exactly one Zed-originated ACP connection and
one `session/new` are permitted in the observation interval.

The operator performs the only content-bearing action: submit the exact fixture text:

> Read README.md and answer with one sentence naming this project. Do not modify files.

The fixture is UTF-8 without BOM, followed by exactly one LF byte. Its SHA-256 is
`8EEA4738E72159A863FEA22A542F92D6A99E3681803BA21863F734C577480D82`. The fixture bytes
and SHA-256 are verified before entry. The relay and Optimus debug trace capture
`initialize`, `session/new`, `session/prompt`, ordered `session/update` notifications, and the
terminal prompt response. Raw text remains in protected custody; normalized evidence records
structural fields and normalized prompt/assistant-message SHA-256 values.

The origin manifest binds session A to Zed/relay/Optimus PIDs plus process-start identities,
executables, workspace, request/run/Gateway IDs, provider-reported usage/cost, source and fixture
digests, and one monotonic interval. A model refusal, timeout, or other permanent prompt failure does
not prove correlation feasibility and is classified before any retry.

Capturing the new-session boundary and completing a model prompt use separate attempt budgets. Once
the probe has a valid `initialize` + `session/new` capture, a Gateway/model timeout does not consume
another correlation-capture attempt or require recreating that session. Up to three separately
recorded prompt attempts may run within the same valid session when the failure is evidenced as
transient. A permanent prompt failure stops immediately. Exhausting the prompt-only budget produces
`blocked_probe_post_new_prompt_unavailable`; it never erases a valid correlation inventory and never
becomes target infeasibility. Conversely, a valid Zed observation showing that the restart path does
not issue `session/new` is a correlation result, not an incidental prompt failure.

### Phase 4: Full restart and restart session B

The probe closes the entire hermetic Zed process tree, not merely the Optimus child. It proves all
captured Zed, relay, and Optimus processes from session A exited. It then starts a new Zed process on
the same hermetic profile and same workspace and records new process-start identities.

Without injecting or rewriting profile state, the operator attempts the prior-thread continuation
path actually exposed by Zed. If no prior-thread affordance exists and the only available action is
"New Optimus Thread", that fact is recorded; the fresh thread must not be narrated as a continuation.
Any resulting ACP connection and `session/new` become restart session B.

For both A and B the protected transcript records the complete `initialize` and `session/new`
parameter sets. The normalized correlation-signal inventory lists every field or launch-context
value available to Optimus at or before the B new-session decision, with:

- origin and availability point;
- A value digest and B value digest;
- persistence across the restart;
- scope and cardinality;
- whether it is supplied by Zed, derived by Optimus, or merely host observation;
- whether it distinguishes one prior thread from every fresh thread in the same workspace;
- whether it is protected by the existing trust model or user-controlled text/state; and
- an explicit eligible/ineligible reason.

Workspace path/digest, project path, cwd, MCP-server collection, agent identity, model, thread title,
wall-clock proximity, PID proximity, and "most recent session" are presumptively ineligible unless
the evidence proves a narrower durable thread identity. A server-generated B session ID cannot
identify A, and a user prompt cannot retroactively authorize the B new-session decision.

If no eligible signal exists, the valid result is `infeasible_for_production_target` with reason
`workspace_only_or_no_restart_discriminator`. This is the central result the probe exists to decide.

### Phase 5: Fresh-thread control C when a candidate survives

A feasible claim requires a same-workspace fresh-thread control. If Phase 4 identifies an otherwise
eligible candidate, the operator creates an explicitly new Optimus thread in the same workspace
under a separately bounded observation interval. No session may be concurrent with the observed
`session/new`; prior process and transcript boundaries remain immutable.

The candidate must differ or be absent for control C while remaining stable between the intended A
to B continuation. If it is shared by B and C, selected only by recency, or available only after the
new-session decision, the probe concludes `infeasible_for_production_target` with a field-specific
reason. Control C may be skipped only when Phase 4 already established that no candidate exists;
skipping it can never support a feasible result.

### Phase 6: Negative verification, redaction, and seal

The offline verifier rejects independent mutations of:

- frozen-plan, amendment, trigger-evidence, source, binary, registry, fixture, and run-manifest
  digests;
- approval ID/mode, security-snapshot digest, launch outcome, workspace digest, policy versions,
  setting decisions, or child-propagation names;
- PID, parent PID, process-start identity, executable identity, process-exit boundary, or observation
  interval;
- transcript bytes, directions, sequence, request/session/run/Gateway IDs, terminal response,
  normalized content digest, or agreement with Optimus's debug trace;
- A/B/C role, full-restart boundary, signal inventory, eligibility reason, or same-workspace control;
- supplied `restart_stable`, `fresh_thread_distinct`, or `eligible` booleans that disagree with
  verifier recomputation from the captured A/B/C digests and the other eligibility predicates;
- attempt number, transient/permanent classification, retry custody, and final disposition; and
- artifact hashes, redaction result, restored-settings proof, or reviewer checkpoint reference.

Raw evidence is promoted only through the merged public entry point:

`tools/evidence_gather.py redact`

The probe must not implement plan-specific sanitization or import `tools.evidence_gather_support`.
Raw content and environment-sensitive artifacts remain under the approved private custody root.
Only artifacts accepted by the merged redaction gate enter the report bundle.

The offline verifier is hermetic with respect to credentials and approval storage: it performs no
keyring reads or writes and derives every approval comparison from manifest-recorded, hashed
evidence. The live runner may read the durable approval store through the production read-only path
while capturing the launch evidence; the verifier never repeats that access.

After the offline verifier passes, the working agent stops. The reviewer independently recomputes
hashes, checks the process/transcript/debug relationships, validates the stop-code precedence, and
records the ruling in the existing Plan 11.7 checkpoint log. The operator then decides whether to
authorize a separately drafted implementation amendment, accept infeasibility, or direct another
bounded investigation.

## Correlation eligibility rules

A candidate restart signal is eligible only if all conditions pass:

1. **Available in time:** Optimus receives or derives it no later than the B `session/new` decision.
2. **Thread-specific:** It names or cryptographically binds one prior Zed thread/session, not merely
   a workspace, agent, project, process, user, or recent record.
3. **Restart-stable:** It remains the same across the complete A-to-B Zed process restart.
4. **Fresh-thread-distinct:** It differs or is absent for control C in the same workspace.
5. **Protocol-honest:** Using it would not change `session/new` into an undeclared resume operation,
   return an old ID, or require unsupported client semantics.
6. **Trust-compatible:** It is not raw user text, editable profile data, a timestamp heuristic, or an
   unbound host observation. Its integrity can be checked inside the existing same-user/launch-
   approval trust model.
7. **Persistable safely:** The future server could retain the binding without storing secrets,
   client-nominated MCP configuration, source content, or unredacted prompt/response text.
8. **Independently falsifiable:** The offline verifier and fresh-thread control can prove a wrong
   binding fails closed.

Failure of any condition disqualifies the signal. Multiple individually ineligible fields do not
become eligible merely by concatenation unless the evidence establishes a new thread-specific,
trust-compatible invariant.

The verifier, rather than the manifest author, owns the two digest relationships:

```text
restart_stable = a_sha256 is not None and a_sha256 == b_sha256
fresh_thread_distinct = c_sha256 is None or c_sha256 != b_sha256
```

It rejects either supplied boolean when it disagrees with those expressions, just as it rejects a
supplied `eligible` value that disagrees with the full eligibility conjunction. A missing C digest
can make the field-level distinction expression true, but it cannot support a feasible result:
`feasible_server_side_custody_candidate` separately requires a valid, completed C control whenever
a candidate survives Phase 4.

## Evidence contract

| Layer | Required evidence |
|---|---|
| Trigger | Frozen-plan blob digest, Step 4 evidence-report digest and disposition, amendment digest and approval triple |
| Target | Recomputed Zed binary/launcher/source/registry identities; Optimus executable/package/source identities; real dependency identities |
| Launch | Direct and relayed use of the same durable approval; identical security-snapshot digest, approval ID/mode, workspace digest, policy/registry versions, decisions, propagation names, and `AUTHORIZED` outcome |
| Process | Zed -> relay -> Optimus PID and process-start chain for each relayed run; direct-control chain; complete exit boundary before restart |
| Protocol | Immutable directional transcript for A, B, and required C; exact `initialize` and `session/new` parameter inventories; ordered prompt/update/terminal-response structure |
| Independent corroboration | Matching Optimus debug suffix for every relayed live interval, including methods, IDs, order, terminal result, and bounded monotonic interval |
| Correlation | Field-level A/B/C signal inventory with availability, persistence, scope, trust, fresh-thread distinction, and eligibility ruling |
| Content and runtime | Fixed prompt fixture digest, normalized assistant-message digest, request/run/Gateway IDs, provider/model/version, provider-reported usage/cost, workspace and manifest digests |
| State restoration | Zed settings pre-image/mutated/final hashes and existence state; exact changed-key allowlist |
| Integrity | Attempt manifests, transient/permanent classifications, raw-bundle digest, promoted-artifact hashes, redaction result, and mutation-negative verifier results |
| Governance | Existing Plan 11.7 checkpoint log, independent review ruling, and mandatory operator return gate |

The normalized report must not contain raw environment values, secrets, raw MCP-server
configuration, raw prompt/response text, or source bodies. It preserves field names, classifications,
hashes, structural counts, protocol IDs, process identities, model/provider identity, usage/cost, and
safe reason codes needed for independent verification.

## Stop taxonomy and precedence

The reducer is fail-closed and evaluates in this order:

1. `invalid_probe_trigger_chain_mismatch`
2. `invalid_probe_target_identity_mismatch`
3. `invalid_probe_relay_environment_mismatch`
4. `invalid_probe_settings_not_restored`
5. `invalid_probe_non_zed_client_or_injected_traffic`
6. `invalid_probe_process_custody_ambiguous`
7. `invalid_probe_transcript_debug_divergence`
8. `invalid_probe_correlation_inventory_incomplete`
9. `invalid_probe_redaction_or_seal_failure`
10. `stop_probe_zed_client_crashed`
11. `blocked_probe_post_new_prompt_unavailable`
12. `blocked_probe_dependency_unavailable`
13. `infeasible_for_production_target`
14. `feasible_server_side_custody_candidate`

The categories mean:

- **Invalid probe:** required authority, target, transparency, restoration, custody, or evidence
  invariants were not established. No feasibility inference is allowed.
- **Zed crash stop:** the pinned Zed process panicked or crashed during an observation interval. The
  crash is sealed with process/panic evidence and returned to the operator; it is not silently
  converted to dependency failure, transcript ambiguity, infeasibility, or feasibility. A crash is
  permanent by default. A retry requires a recorded evidence-based transient classification.
- **Post-new prompt block:** the correlation boundary was captured validly, but the fixed read-only
  prompt could not produce the message-level evidence after its independent prompt retry budget.
  The sealed correlation inventory is preserved, but no feasible result is allowed until message
  binding succeeds.
- **Dependency block:** a real dependency or required identity is unavailable before a valid attempt.
  This is not target infeasibility.
- **Infeasible:** every higher-precedence validity gate passed, but no correlation signal satisfies
  the eligibility rules on the exact production target. Workspace-only evidence, indistinguishable
  continuation/fresh control, and a signal available only after `session/new` are named infeasible
  reasons.
- **Feasible candidate:** all gates passed and one exact signal satisfies every eligibility rule,
  including the fresh-thread control. This records a candidate for separate design and operator
  review; it is not build authorization.

Correlation-capture attempts and post-new prompt attempts each have independent caps of three.
Retries require an evidence-backed transient classification. Each attempt has its own immutable
manifest and artifacts and records phase, failure class, evidence supporting transient/permanent
classification, retry number within the applicable budget, and final disposition. A valid
`session/new` capture is never discarded or repeated merely because its later prompt timed out.
Attempts are never overwritten or merged into a cleaner narrative. Permanent failures stop
immediately unless the operator explicitly authorizes another bounded run.

## Documentation freshness

The amendment's approval review and the post-probe verdict review each audit every document that
makes a current-state claim affected by this work. At minimum this includes:

- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`;
- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`;
- `docs/superpowers/plans/archive/evidence-handoff-open-work-pool.md`; and
- `README.md`.

The Plan 11.7 and render-observation rows must state the actual gate: frozen implementation blocked
after Task 0 Step 4, standalone feasibility amendment awaiting approval/execution/verdict, or sealed
post-probe disposition. A row cannot remain at generic "drafting/review in progress" once the
amendment changes that fact. Documents that make no affected current-state claim are recorded as
checked/no-change rather than edited gratuitously. This is a reviewer-enforced freshness audit; it
does not transfer ownership of the reviewer checkpoint log to the working agent.

## Result-specific handoff

### Feasible candidate

The handoff identifies the exact eligible signal, evidence fields, trust boundary, validation point,
candidate Optimus and evidence-tool change surfaces, negative cases, and remaining risks. It also
states that real independent-`acpx` restart/load/replay conformance remains mandatory. The operator
must separately authorize writing and then executing a production implementation amendment.

### Infeasible production target

The handoff identifies every observed signal and why it failed, including the same-workspace fresh-
thread comparison where applicable. It leaves the frozen Plan 11.7 implementation blocked and does
not substitute recency, workspace affinity, UI/profile state, or prompt content as a fallback.

### Crash, block, or invalid probe

The handoff preserves the exact stop code, artifacts, restoration result, and the earliest failed
precedence rule. It makes no feasibility claim. Further work requires operator direction; the probe
does not retry a permanent failure or broaden scope on its own.

## Verification strategy

- Unit tests dominate scratch relay, transcript projection, correlation eligibility, reducer
  precedence, manifest parsing, and mutation-negative verification.
- Correlation mutation tests independently falsify both verifier-derived digest relationships and
  reject supplied `restart_stable`, `fresh_thread_distinct`, and `eligible` values that disagree
  with recomputation.
- Every task checkpoint runs `uv run --frozen pytest tests/unit -q`, not only the new tools'
  selectors. The new `tools/` modules' discovered persistence/export surfaces are classified in
  `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` as they appear, and the
  checked-in logging-surface verifier must pass at the same checkpoint.
- Live evidence uses real Zed 1.13.1, the real Optimus executable, real Redis TimeSeries, and the real
  Optimus Gateway. Fakes cannot satisfy a live claim.
- Zed is the only ACP client in the custody runs. The relay's result cannot satisfy independent ACP-
  client conformance; that remains assigned to real `acpx` in any future implementation amendment.
- The direct environment control, sessions A/B, and conditional control C have distinct immutable
  run manifests and non-overlapping observation intervals.
- Settings restoration and production-source cleanliness are verified after every live attempt and
  again before the reviewer accepts the seal.
- The reviewer verifies files and digests on disk, not the working agent's narrative.

## Acceptance boundary for the written amendment

The implementation amendment derived from this design is acceptable for operator review only if it:

- is a standalone file and pins the immutable trigger chain by full digest;
- uses the exact amendment title, path, existing `P11-FEAT-ZED-RESUME` ownership, and no new Plan
  11.x number defined in this design;
- carries the amendment approval triple and existing checkpoint continuity explicitly;
- authorizes only the bounded probe and keeps frozen Plan 11.7 implementation tasks blocked;
- specifies the exact direct control, sessions A/B, conditional fresh control C, environment-
  equivalence proof, ancestry limitation and any direct ancestry revalidation, transcript/debug
  cross-corroboration, README precondition, separate correlation/prompt retry budgets, settings
  restoration, negative tests, redaction path, and stop reducer described here;
- requires approval-time and verdict-time documentation-freshness audits across every affected
  current-state document;
- contains no production implementation task or implicit post-feasibility authorization; and
- treats both infeasibility and a separately named crash stop as first-class, evidence-bearing
  outcomes.
