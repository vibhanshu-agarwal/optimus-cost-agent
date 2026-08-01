# Zed Render Observation Design

- **Feature:** `EVIDENCE-HANDOFF-FEAT-ZED-RENDER-OBSERVATION`
- **Status:** Design review; direction ratified, implementation not authorized
- **Baseline:** `main` merge commit `2cf2f42aa7d1072f09d0678a3c75eb43516c8808`
- **Target client source pin:** Zed commit `00bd72e7838f4b875a913cd112b47a0ebe1ca62b`

## Decision summary

The evidence collector must not infer a successful Zed render from pixels alone. A determinate
render claim requires a cooperative Zed receipt that binds the collector run to the same ACP
session and assistant message, identifies the expected content without persisting it in normalized
evidence, proves that the message intersected the visible viewport, and is emitted only after the
containing frame was presented successfully. A digest-bound capture and deterministic recognition
of a run-specific visual witness selected from the actual response corroborate the receipt; neither
is authoritative.

This design is deliberately capable of ending in **infeasible**. If the required receipt cannot be
produced by an official or otherwise operator-accepted production-equivalent Zed build, the two
render-dependent collector outcomes remain unproven. A locally patched or diagnostic Zed build may
validate the hook and contract, but its receipt alone cannot satisfy `rendered_then_crashed` or
`rendered_stable` for production Zed.

## Authority and custody

This is a new, unscheduled product-owned follow-up. Its live state is owned only by
`docs/superpowers/plans/evidence-handoff-open-work-pool.md`. It does not reopen, edit, or silently
reinterpret the merged collector design or implementation plan.

The operator-approved design direction creates one explicit exception to the merged collector
Definition of Done:

- the future implementation surface has eight explicit stages—`validate`, `prepare`, `check`,
  `collect`, `observe-render`, `classify`, `redact`, and `inspect`—instead of exactly seven.

This exception supersedes only the stage-count sentence in the collector Definition of Done. The
single executable entry point, absence of an implicit redaction route, immutable artifacts,
explicit destinations, portable-core boundaries, and every other frozen collector constraint
remain binding. The future implementation plan must quote this exception; it must not edit the
merged plan to make history agree retroactively.

The stale merge wording in the existing collector pool row is a separate documentation-freshness
matter and is not corrected or absorbed by this feature.

## Authoritative-source check

The repository HLD, LLD, and Test Strategy were checked before this design. None defines a
render-observation producer or contradicts the fail-closed approach here. Their real-dependency,
evidence-tier, credential, logging, and coverage rules remain authoritative.

At the exact Zed source pin above, official source establishes the candidate cooperative boundary:

| Source | Design-relevant fact |
|---|---|
| [`crates/gpui/src/window/a11y.rs`](https://github.com/zed-industries/zed/blob/00bd72e7838f4b875a913cd112b47a0ebe1ca62b/crates/gpui/src/window/a11y.rs#L45-L64) | GPUI builds an accessibility `TreeUpdate` from the current frame during prepaint. |
| [`crates/gpui_windows/src/window.rs`](https://github.com/zed-industries/zed/blob/00bd72e7838f4b875a913cd112b47a0ebe1ca62b/crates/gpui_windows/src/window.rs#L1023-L1049) | Windows installs and updates an AccessKit adapter, but that bridge alone does not bind a node to an ACP message or a presented frame. |
| [`crates/agent_ui/src/conversation_view/thread_view.rs`](https://github.com/zed-industries/zed/blob/00bd72e7838f4b875a913cd112b47a0ebe1ca62b/crates/agent_ui/src/conversation_view/thread_view.rs#L6248-L6292) | This assistant-message rendering branch passes message chunks into Markdown rendering but exposes no stable ACP-message identity at this boundary. |
| [`crates/gpui/src/window.rs`](https://github.com/zed-industries/zed/blob/00bd72e7838f4b875a913cd112b47a0ebe1ca62b/crates/gpui/src/window.rs#L2796-L2953) | GPUI produces a `rendered_frame` during draw and presents it later; a candidate hook must carry any message/frame association across that boundary. |
| [`crates/gpui_windows/src/directx_renderer.rs`](https://github.com/zed-industries/zed/blob/00bd72e7838f4b875a913cd112b47a0ebe1ca62b/crates/gpui_windows/src/directx_renderer.rs#L237-L245) | DirectX `Present` provides the success boundary after which Zed may emit an authoritative receipt. |

The 2026-08-01 spec review re-fetched the raw files from the exact commit, verified the ranges above,
and recorded these file SHA-256 digests:

- `crates/gpui/src/window/a11y.rs`:
  `048dcfb31e77ee5c5c3d7d9e17efcbec33add31b746b57dbc52c5ad6e21a0894`
- `crates/gpui_windows/src/window.rs`:
  `ffc7a9eead526ffb5daff5d8ed69e129f6b26dee997c3544ca7c6dbac586a775`
- `crates/agent_ui/src/conversation_view/thread_view.rs`:
  `26b00c00410154a5db8694101beb026e4ae64d552e55bbb879e5510293789d4f`
- `crates/gpui/src/window.rs`:
  `84e9ae61b01e0004cf1a01583bc287bc79cecf4bf50d2c55835a1b2596a14d1a`
- `crates/gpui_windows/src/directx_renderer.rs`:
  `dda0569ff2c75e15a1053f3d0d3d39ec01d6c33469ebfe14f52fa424a16f95b8`

These are source-level feasibility facts, not proof that the installed binary has such a receipt.
Implementation pickup must re-fetch and verify the source evidence and additionally re-identify the
target Zed binary, version, source commit, and executable SHA-256; a matching version string is
insufficient.

## Problem statement

The current evidence path cannot prove Zed rendering:

1. `tools/evidence_gather.py` creates an ACP session by launching `acpx`.
2. `--zed-pid` identifies a separately running Zed instance by process discovery.
3. Current window, crash, log, and screenshot observations therefore have no demonstrated custody
   of the ACP session that produced the response.
4. A more accurate screenshot detector would still be unable to bind those pixels to that ACP
   response.

The existing classifier already encodes the correct trust boundary: it rejects
`assertion_provenance="screenshot-success"` and accepts a render claim only from a declared
scenario detector. The missing component is not merely image recognition. It is a producer that
can establish same-session custody and emit normalized, independently checkable evidence.

## Claim definition

For this feature, **rendered** means all of the following:

1. Zed loaded or created the exact ACP session identified by the run manifest.
2. The expected assistant message is identified by a stable message identity and a digest derived
   from the exact normalized response bytes defined by the scenario.
3. A run-specific visual witness selected deterministically from the collected assistant response
   appears in that message and nowhere else in the loaded session fixture.
4. The laid-out message bounds have a non-empty intersection with the Zed conversation viewport
   in the presented frame.
5. Zed reports successful presentation of that containing frame.
6. An independent, digest-bound capture corroborates the reported window, bounds, and visual
   witness while the message and frame correlation remain current.

This does **not** claim that a human looked at the display, that every pixel was unobscured on a
physical monitor, that an operating-system compositor displayed the frame for a minimum duration,
or that the response was semantically correct. The claim is intentionally limited to successful
client presentation in the visible conversation viewport with corroborating capture.

### Visual-witness selection

Production evidence must not depend on a model echoing an injected run canary. After `collect` has
recorded the completed assistant response, `observe-render` deterministically selects a bounded,
printable span from that exact response as the visual witness. The selection contract must require
the normalized span to be unique across the loaded session, absent from the prompting user turn,
long enough for deterministic recognition, and fully present in the message content covered by the
receipt digest. Raw witness text and offsets remain private evidence; normalized output carries only
the selector version, witness digest, and recognition bounds.

If no eligible span exists, the stage records `render_visual_witness_unavailable` and emits no
render claim. That is a scenario/content feasibility result, not a detector malfunction. A bounded
exact-echo prompt may be used as an explicitly labeled feasibility fixture, but neither production
acceptance nor the general live matrix may rely on model compliance with such a prompt. Gateway or
model timeout/refusal remains a collect-stage failure and must not be reported as render-detector
failure.

## Sequencing dependency: same-session custody

Same-session custody is a hard prerequisite, not a parallel convenience. The preferred unattended
route is `P11-FEAT-ZED-RESUME`: real evidence driven by the independently authored `acpx` client
shows that Zed loads the acpx-created ACP session and replays the same message history through
`session/load`. The evidence must bind at least:

- session ID and session-load request/response;
- assistant message identity and normalized content digest;
- ACP server process and endpoint identity;
- Zed process, top-level window, version, source commit, and executable digest;
- run ID and immutable fixture/run-manifest digests; and
- monotonic observation intervals sufficient to exclude stale or foreign sessions.

At this design baseline, the `P11-FEAT-ZED-RESUME` owner is not near completion: its status is
`Draft for operator approval. Implementation is not authorized.`, with 85 unchecked task boxes and
zero checked task boxes. Its draft has now been amended to pin the exact Zed 1.13.1 source target,
but still requires operator authorization, production implementation, and real discovery/reopen
evidence. A successful project-authored fake, a hand-written ACP harness, or a new acpx session
observed beside an unrelated Zed session does not satisfy custody. The checkbox counts are a
point-in-time baseline fact and must be re-read from the owning plan at every pickup.

### Alternative custody route and failed-probe semantics

`session/load` is not the only technically valid way to obtain custody. A separately approved route
may let Zed originate the ACP connection and `session/new`, then have the Optimus server bind its
server-assigned session ID to the exact connection transcript, dedicated child-server identity,
parent Zed PID/process start, run manifest, message digest, and later cooperative render receipt.
That is server-side custody of a Zed-originated session; it does not pretend that Zed adopted an
unrelated acpx session.

This alternative has lower automation and different evidence weight. It does not satisfy the
independent-`acpx` protocol evidence requirement by itself, and the current collector's fresh-acpx
entry point cannot drive it unchanged. Selecting it therefore requires an explicit operator-approved
amendment that keeps separate acpx conformance evidence and defines how the Zed-originated prompt,
connection, and receipt are captured without a project-authored client.

Returning an old session from `session/new`, injecting conversation content into Zed's profile,
copying acpx output into the UI, or correlating only by timestamps/PIDs are not custody alternatives:
they violate protocol semantics, bypass ACP, or remain ambiguous.

Consequently, a failed real `session/load` probe proves that the preferred acpx-to-Zed transfer
approach failed; it does **not** prove that a determinate render outcome is unreachable. The result
must stop that implementation path and trigger operator review of the server-side route. Render
outcomes become unreachable for the production target only after no approved custody route and no
eligible production receipt producer survive their respective feasibility gates.

## Architecture

### Stage boundary

`observe-render` runs only after a completed immutable raw collection bundle and before
`classify`. It consumes explicit absolute input paths and writes a separate, immutable render-
observation bundle under the private capture root. It never appends to or rewrites the raw bundle.

The stage may attach to the already identified Zed process/window and receive a cooperative
receipt. It must not create another ACP session, send a model prompt, inject user/content/navigation
input into Zed, launch redaction, or infer an outcome. Its sole input to Zed is the fixed-schema,
content-free diagnostic challenge defined below. `classify` remains the only outcome reducer and
reads both verified bundle digests.

There remains one executable surface: `tools/evidence_gather.py observe-render`. There is no
implicit `all`/`run` route, and `redact` remains separately and explicitly invoked.

### Producer components

The preferred producer has four components:

1. **Zed receipt hook.** An official or operator-accepted production-equivalent hook associates an
   ACP assistant-message identity and digest with its laid-out bounds and frame ID, then emits only
   after the renderer reports successful `Present`.
2. **Host receipt adapter.** The host supplies a cryptographically random run nonce over the
   constrained Windows named-pipe channel below; verifies Zed process, executable, source, window,
   session, message, frame, timestamps, and receipt syntax; and preserves the raw receipt privately.
3. **Capture corroborator.** A host capture tied to the same PID/HWND, physical bounds, DPI, and
   receipt interval produces an immutable image digest. Deterministic recognition locates the
   selected visual witness only inside the receipt-reported message/viewport intersection.
4. **Portable normalizer.** Standard-library-only code validates declared inputs and emits the
   content-free normalized contract consumed by the existing detector/classifier boundary.

### Nonce channel security decision

The reference and production design uses a local Windows named pipe. The eligible Zed receipt hook
creates a versioned pipe endpoint derived only from its PID and process-start identity, rejects
remote clients, and applies an explicit current-user SID ACL. The host connects only after it has
identified the target Zed process and must verify the pipe server PID with the Windows named-pipe
process-identity API before sending any bytes. PID without process-start identity is insufficient.

The host sends exactly one length-bounded, versioned challenge containing only a 256-bit random
nonce, run ID, raw-bundle digest, expected session/message identities, response-content digest, and
visual-witness digest. It carries no prompt, response text, path, executable content, UI action,
command, model choice, or session mutation. Zed uses the challenge only to filter and bind an
observation of state it has already loaded; receiving it cannot cause session load, message render,
navigation, or model execution. The receipt returns over the same framed channel, after which the
hook closes the connection and zeroes the nonce from mutable buffers where the platform permits.

This fixed diagnostic challenge is an explicit, narrow control-plane input exception to the broader
input-injection prohibition; it is not a prompt-injection capability. File polling, command-line or
environment payloads, window messages, UI Automation, SendInput, loopback TCP, arbitrary pipe
messages, and a host-created fake Zed endpoint are not fallbacks. A different official upstream
transport requires an operator-approved design amendment with equivalent peer identity, locality,
size, schema, replay, and non-mutation properties before an implementation plan may adopt it.

The receipt's authority is semantic and provenance-based, not cryptographic non-repudiation. A
same-user local process can tamper with local files and IPC; this feature does not pretend
otherwise. Nonces, hashes, file identity, process identity, and atomic custody prevent accidental
reuse and ambiguity within the stated local evidence threat model.

### Instrumented-build ruling

Evidence weight is fixed as follows:

| Producer | Permitted evidentiary weight |
|---|---|
| Locally patched/forked Zed or debug-only instrumentation | Feasibility spike, contract tests, timestamp/geometry calibration, and upstream proposal evidence only. Never sufficient by itself for a determinate production outcome. |
| Official upstream diagnostic hook in the exact released binary | Eligible as authoritative receipt evidence after exact source/binary identity and the full live matrix pass. |
| Operator-designated production build made from reviewed source with the hook enabled | Eligible only if that exact binary is the client under test, its build is reproducible or independently attested, and the operator explicitly accepts it as the production target before evidence collection. It does not prove an unmodified Zed release. |
| Screenshot, OCR, UI Automation, logs, or human observation without an eligible receipt | Corroboration or investigation only; never a render claim. |

This resolves the real-dependency rule: a patched build is a real Zed process, but it is not the
named production dependency unless the operator has made that exact binary the production target.
Tests and reports must name which row supplied the receipt and must not generalize across rows.

## Normalized observation contract

The producer emits `evidence-render-observation-v2`. Version 1 remains readable for historical
bundles but is not upgraded in place and is ineligible for new production evidence under this
feature. A future parser must dispatch explicitly by schema: it preserves the strict version 1
field set and behavior, and validates version 2 against a separate closed field set. It must never
reinterpret a version 1 document as a version 2 receipt.

The normalized document contains metadata only:

| Field group | Required content |
|---|---|
| Identity | schema version, feature ID, scenario ID, run ID, run nonce digest, raw bundle SHA-256 |
| ACP custody | endpoint/process identity, session ID, assistant message ID, normalized content SHA-256, visual-witness selector version and SHA-256 |
| Zed custody | PID plus process start identity, top-level HWND, client version, source commit, executable SHA-256, receipt-hook ID/version |
| Frame | Zed frame ID, message layout generation, viewport and message physical bounds, visible intersection, DPI, present completion timestamp |
| Corroboration | capture adapter/version, capture interval, image SHA-256, recognized visual-witness digest and bounds |
| Integrity | raw receipt locator/digest, raw capture locator/digest, source clock IDs, normalization result, complete flag, stable reason codes |
| Claim | `assertion_type="client-rendered"`, `assertion_provenance="scenario-detector"`, allowlisted `detector_id="zed-present-receipt"`, `receipt_provenance="zed-present-receipt-v1"`, point timestamp equal to successful present completion |

Session content, response text, visual-witness plaintext/offsets, screenshot bytes, log bodies, and
receipt bodies remain declared raw artifacts in the private capture root. Normalized paths are
relative, canonical, containment-checked locators. No normalized or promoted field may contain
secrets or raw assistant content.

The redaction gate remains authoritative for promotion. The observation bundle does not bypass
screenshot approval or make a raw screenshot promotable merely because it corroborated a claim.

## Closed acceptance predicate

A render claim exists only when every required predicate is true:

- the producer is eligible under the instrumented-build ruling;
- run, raw-bundle, endpoint, session, message, response digest, and nonce match exactly;
- the Zed PID includes process-start identity, the HWND belongs to it, and neither was reused;
- client version, source commit, executable digest, and receipt-hook version are allowlisted;
- the receipt is fresh, unique, atomically complete, digest-valid, and emitted after successful
  presentation of the identified frame;
- message and viewport bounds share a non-empty physical-pixel intersection for that frame;
- Zed is visible and not minimized at presentation and corroboration time;
- capture identity, bounds, DPI, interval, and digest agree with the receipt;
- the deterministically selected visual-witness bounds are fully contained within the reported
  message/viewport intersection and no competing window/session/message match exists;
- source clocks have a proven mapping into the run's monotonic timeline; and
- all required artifacts and collectors completed without ambiguity or integrity failure.

There are no partial-credit predicates. Missing, unsupported, stale, conflicting, duplicated,
offscreen, minimized, foreign, or digest-invalid evidence produces no render claim and a stable
reason code. Receipt success without capture corroboration is insufficient. Capture success
without an eligible receipt is insufficient.

For an accepted claim, the render timestamp is the receipt's successful present completion time.
The capture interval validates the claim but does not move that semantic point forward. A crash
before corroboration completes prevents claim acceptance. Live `rendered_then_crashed` evidence
must therefore arrange the crash only after the stage has durably accepted the receipt and capture.

## Stable reason codes

The implementation plan must freeze a closed enumeration at least as specific as:

- `render_same_session_unavailable`
- `render_receipt_unsupported`
- `render_producer_ineligible`
- `render_client_identity_mismatch`
- `render_session_mismatch`
- `render_message_mismatch`
- `render_content_digest_mismatch`
- `render_receipt_stale_or_duplicate`
- `render_nonce_channel_unavailable`
- `render_nonce_peer_mismatch`
- `render_present_not_successful`
- `render_message_not_visible`
- `render_window_minimized_or_hidden`
- `render_capture_missing_or_mismatched`
- `render_visual_witness_unavailable`
- `render_visual_witness_not_correlated`
- `render_clock_mapping_unproven`
- `render_artifact_integrity_failed`
- `render_observation_ambiguous`

Human-readable details stay private and content-safe. Unknown producer codes fail closed rather
than being copied into portable state.

## Failure semantics and classifier interaction

The existing four classifier outcomes and integrity-first precedence do not change:

- eligible accepted render plus later correlated crash may yield `rendered_then_crashed`;
- eligible accepted render plus a complete stable observation interval may yield
  `rendered_stable`;
- correlated client crash without an accepted earlier render remains `client_crashed`; and
- everything else remains `indeterminate`.

`client_crashed` means only that a correlated client crash was proven and no render claim had been
accepted earlier. It is not evidence that rendering did not occur. In particular, a real crash in
the interval after `Present` but before receipt/capture corroboration completes remains
`client_crashed`, because the design chooses a false negative over an uncorroborated render claim.
Downstream consumers must not treat `client_crashed` as the logical negation of either
render-dependent outcome. Consequently, `rendered_then_crashed` is provable only in a staged live
case where the induced crash occurs after durable receipt/capture acceptance; reports must disclose
that staging constraint.

`observe-render` never writes one of these outcome values. A producer failure is evidence absence,
not a synthetic crash or success. Classifier input must include the immutable raw-bundle digest and
render-observation-bundle digest; conflicting or multiple candidate observations are integrity
failures.

## Feasibility gate

Before an implementation plan is authorized, a bounded spike must answer all of the following with
artifacts rather than narration:

1. Can the exact target Zed source associate an ACP assistant-message identity and content digest
   with its layout bounds without persisting raw content in normalized output?
2. Can the exact containing frame be carried through to a successful renderer `Present` result?
3. Can an eligible build implement the exact named-pipe peer-identity and fixed-challenge contract
   and emit a nonce-bound receipt atomically after that success without mutating client state?
4. Can a deterministic selector find a unique, recognizable visual witness in actual model output
   without depending on an echo prompt, and distinguish witness unavailability from detector
   failure and collect-stage timeout/refusal?
5. Can an independent capture be bound to the same PID/HWND, physical bounds, DPI, frame interval,
   session, and visual witness?
6. Can the receipt/capture pair survive the negative matrix without a false determinate claim?
7. Can the producer operate with an approved same-session custody route without creating or
   conflating a second session? For the preferred route, this means real `session/load` custody and
   no injected prompt. For an approved server-side route, it means a Zed-originated session with the
   separately specified prompt/capture boundary and independent acpx conformance evidence.

The spike first uses a locally instrumented build because its purpose is discovery. It must then
identify a credible route to an eligible producer: accepted upstream hook or an explicitly
operator-designated production build. If no such route exists, the recorded result is
`infeasible_for_production_target`; no detector implementation or optimistic fallback is planned.

## Verification strategy

Unit fakes may test parsing, validation, normalization, reason-code reduction, and classifier
interaction only. They cannot prove Zed, AccessKit, DirectX presentation, capture, ACP protocol, or
the two render-dependent outcomes.

The required live matrix uses a real independently authored `acpx`, real ACP server, real eligible
Zed binary, real Windows renderer, and real capture path:

| Case | Required result |
|---|---|
| Same session, expected message visible, successful present, corroborated visual witness, complete stability interval | `rendered_stable` |
| Same setup, crash induced only after durable receipt/capture acceptance | `rendered_then_crashed` |
| Correlated crash before any accepted render | `client_crashed` |
| No eligible receipt | No render claim |
| Screenshot/OCR match without receipt | No render claim |
| Receipt without matching capture/visual witness | No render claim |
| Actual response has no eligible unique visual witness | No render claim with `render_visual_witness_unavailable`; not a detector failure |
| Pipe server PID/process-start mismatch, remote peer, replayed nonce, or malformed challenge/receipt | Integrity failure; no render claim |
| Wrong/stale session, message, nonce, frame, PID/HWND, process start, or bundle digest | Integrity failure; no render claim |
| Modified/unallowlisted binary or hook | No render claim |
| Hidden, minimized, off-viewport, zero-intersection, or competing match | No render claim |
| Tampered/truncated/duplicate receipt or capture | Integrity failure; no render claim |
| Clock regression or unproven cross-clock mapping | No render claim |

Windows live evidence is mandatory because the renderer, window identity, DPI, and capture boundary
are platform-specific. Portable contract and normalization tests must also run in the repository's
Linux/WSL gate where applicable. Remote CI alone does not replace the real Windows evidence.

Every Definition of Done claim in the future implementation plan must name a real artifact with
dependency identity, command, result, SHA-256, and reviewer ruling. A fake, patched feasibility
spike, screenshot, or prose statement cannot close a live claim.

## Security, privacy, and logging

- Runtime credentials remain only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; this feature adds no
  provider credential.
- The host provides a random per-run nonce only through the fixed-schema named-pipe challenge; the
  scenario never embeds executable content.
- Receipt and capture ingestion are untrusted-input boundaries with strict size, schema, path,
  enum, integer-range, and digest validation.
- Full receipt/capture bodies remain private raw artifacts and pass through the existing redaction
  and screenshot-approval policy before promotion.
- Structured logs record stage, adapter, reason code, artifact digest, latency, policy reason, and
  authorization outcome without raw assistant content, visual-witness text, credentials, or
  artifact body.
- The producer cannot execute receipt fields, dynamically load adapters, follow embedded absolute
  paths, or promote tool output to policy.

## Explicit exceptions and non-goals

- No edit to the frozen collector design or implementation plan.
- No correction of the existing collector pool row's stale merge wording in this design change.
- No second executable entry point and no implicit pipeline or redaction route.
- No Zed prompt injection, UIA/SendInput revival, `zed://` revival, model call, or session creation
  by `observe-render`; the sole client-directed input is the content-free diagnostic challenge
  defined above.
- No generalized OCR/computer-vision subsystem; recognition is bounded corroboration for the
  deterministic visual witness selected from the collected response.
- No claim that AccessKit alone proves message identity or presentation.
- No claim that a patched research build proves an unmodified production release.
- No weakening of raw-bundle immutability, path custody, redaction, screenshot approval, provider-
  key, independent-ACP-client, or real-dependency policy.
- No new outcome and no change to outcome precedence.
- No claim of human visual attention, cryptographic non-repudiation, or resistance to a malicious
  same-user host.

## Design acceptance and next step

This design is ready for operator and independent architecture review when:

- the exact Zed source links and file digests above have been independently reviewed, and the
  installed-binary/source relationship has been re-verified;
- the eight-stage exception is explicitly accepted as the sole supersession of the merged
  seven-stage constraint;
- the instrumented-build evidence table is accepted without broadening patched-build claims;
- the preferred `P11-FEAT-ZED-RESUME` route, the server-side alternative, their distinct evidence
  weights, and the target-version reconciliation are accepted;
- the post-collection visual-witness selection and its explicit unavailable result are accepted;
- consumers accept that `client_crashed` does not prove non-rendering and that
  `rendered_then_crashed` requires staged post-acceptance crash timing;
- the named-pipe diagnostic challenge is accepted as the sole narrow client-input exception; and
- reviewers agree that `infeasible_for_production_target` is a valid terminal spike result.

After design approval, write a separate implementation plan beginning with the same-session and
feasibility gates. Do not schedule code work, reserve a plan number, or implement the eighth stage
before those gates and the implementation plan receive operator approval.
