# P11-FU-6 — Bounded early POST rejection implementation plan v2

> **For agentic workers:** Use the executing-plans workflow task-by-task. Implementation belongs to a separately authorized agent; Codex authors and reviews. Do not execute this draft merely because it exists.

**Status:** Design and plan drafted under the operator's approval to Codex. **Implementation, diagnostic execution and delivery revalidation are not authorized by this document.** Those are later decisions. FU-6 remains Open; Plan 11.27 Slice B remains STOPPED. No source or test implementation was changed while drafting.

**Proposed executor:** Fable 5.1, subject to explicit operator implementation approval. Codex remains the plan author and independent reviewer. The previous Fable investigation assignment is not an implementation grant. Keep the FU-keyed filename; no new linear Plan 11.x number or backlog owner is invented.

**Review incorporation:** Fable's review is `D:/Projects/Development/Python/optimus-agent-handoff/REVIEW-2026-09-05-fable-p11-fu6-bounded-early-post-rejection-v1.md`. V1 remains immutable reviewer/output history at SHA-256 `e0e5c41b15d5ba734908defdcdc92671756d59f767088fa97ce7c3dd67fa5fc7`; it is not a required correction-package commit input. This complete v2 replaces v1 as the proposed execution contract.

**Goal:** On unknown and unconfigured-tool POST routes, consume a small, correctly framed request body within a strict deadline before returning the existing 404, while bounding work on malformed, oversized and incomplete requests.

**Architecture:** Keep route selection and recognized-route dispatch intact. Replace only the early-404 branch with a private framing classifier, bounded discard operation and terminal response selection. Use the existing buffered input stream; never mix direct socket reads with `rfile`. Prove the body-before-response property through deterministic event-driven tests and verify real Windows HTTP behavior.

**Tech stack:** Existing CPython 3.14, `BaseHTTPRequestHandler`/`ThreadingHTTPServer`, socket timeouts, monotonic clock and pytest. No dependencies, environment changes, protocol-version upgrade or external services.

**Spec:** The design contract in sections 2–5 below. Evidence basis: Fable's investigation and additive addendum, including the accepted narrow verdict. The specific body-size and time limits below are **proposed design choices**, not inherited application guarantees; approval of this plan must include them.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| authority | Approval to draft this plan | yes | Operator / Codex | Already granted; this document completes drafting only. |
| authority | Implementation approval of v2 limits, status policy and scope | no | Operator | Merely unauthorized; awaiting explicit implementation approval, not another investigation verdict. |
| executor | Named implementation executor | no | Operator | Merely unauthorized; Fable 5.1 is proposed, not assigned to implement yet. |
| budget | New 120 combined-agent-minute correction-only box | no | Operator | Merely unauthorized; no box has started and no prior balance is transferred. |
| code/state | Exact c1989985 base and unchanged Gateway source identities | yes | Executor / Codex | Established by prior custody; recheck read-only at entry before using those pins. |
| isolation | Fresh independent correction clone and external evidence/temp siblings | no | Executor | Genuinely absent until authorized setup; destination must be absent and Git/common stores contained. |
| tooling | Windows interpreter 3.14.4, locked tools and recorded venv fingerprint | unknown | Executor | Genuinely absent fresh entry verification; reuse last verified installation only after checking identity, no repair authority. |
| tooling | Native WSL environment /root/optimus-ci-venv and import provenance | unknown | Executor | Genuinely absent fresh entry verification; prior investigation verified it, but that is not a fresh execution claim. |
| evidence | Governing investigation addendum, incident log and preserved failure custody | yes | Fable / Codex | Exact paths and hashes below; verify at entry, preserve all original bytes. |
| governance | V2 and exactly one live-registry row in its future correction package | no | Codex / Executor | Genuinely absent from the not-yet-created correction checkout; reviewer row exists, exact scoped delivery is required below. |
| review | Independent final correction review | no | Codex | Genuinely absent until the implementation and named evidence exist. |
| delivery | Slice B integration and hit-bound full delivery revalidation | no | Operator | Merely unauthorized and outside this correction-only phase. |

## 1. Evidence, identities and authority

Incident log: `D:/Projects/Development/Python/optimus-ci-production-evidence-slice-b-20260905/gate3-05-full-hook-rehearsal-updated-backlog-20260905T095009Z.log`, SHA-256 `d51138933d75f042cd8aebb19590f4d68b09d6c4e25a2aa13f64aa57ce14ecea`. Test: `tests/unit/optimus_gateway/test_server.py::test_tools_routes_return_not_found_when_dependencies_are_not_configured`; WinError10053 during response reception. Full Windows hook failed. Proposed failed tree: `b32fd96997836a5749b60951398860b34e6c1d7d`.

Candidate: `C:/worktrees/optimus-cost-agent-wt-claude-ci-production`, HEAD `c1989985171c3054916732f1306d5ffc85d5b094`, parent tree `258406df199720d19dbdd1f2640567f4f9aca4a8`. Treat its complete uncommitted Slice B package as preserved evidence, not an implementation workspace. Do not stage it, alter its object store or transplant the fix into it under this plan.

Investigation: `C:/Users/pc/AppData/Local/Temp/fu6-fable51-20260905T103323Z`. Read `root-cause-report.md`, `experiments.csv`, `fu6_diag.py`, and governing `root-cause-report-addendum-01-codex-review.md` (SHA-256 `a33b4e0a4b978432222ec00935e8c5e95e663e3259cb44b6c166c7a40156fc8a`). The 37-entry manifest SHA-256 is `3fda91c0be201c67e4003fd79ec17a503317e35dbfeedb0b9eccf41c36aa1653`. Original evidence and earlier manifests are immutable.

Established scope: the early-404/unread-body behavior is causally involved in the reproduced failure on the tested Windows host. The exact packet-level reset/discard chain, universality across hosts, and identity of every historical recurrence's cause remain unproven. Do not claim otherwise in code comments, reports or acceptance.

Reviewer: `C:/worktrees/optimus-cost-agent-wt-codex-plan-11-26`. Sole owner entry: `P11-FU-6` in `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`. Preserve its Open status until separately reviewed closure criteria are met. Do not merge FU-5 or FU-7 into this item.

## 2. Scope and alternatives

**Chosen:** bounded discard on the early rejection path. This addresses the demonstrated handler lifecycle while containing compatibility changes to requests that already lack a valid route.

**Rejected:** coalescing the test client's writes or retrying response reads. Either could conceal the server failure mode without correcting it. An unbounded drain reproduces the diagnostic reversal but adds a stalled-client hazard. Replacing the HTTP server or hardening all recognized routes is a larger change and is deferred.

Allowed future implementation paths, relative to the isolated correction checkout:

| Path | Responsibility |
|---|---|
| `src/optimus_gateway/server.py` | Three private limits, framing/deadline helpers and early-rejection integration only. |
| `tests/unit/optimus_gateway/test_request_body_rejection.py` | New event-controlled regression, framing, deadline and resource-lifecycle tests. |
| `tests/unit/optimus_gateway/test_server.py` | Execute unchanged existing route tests. Read-only by default; any proposed edit needs reviewer disposition before it is made. |
| `README.md` | Document rejected-route limits and explicit scope; no global Gateway-hardening claim. |
| `docs/superpowers/plans/2026-09-05-p11-fu6-bounded-early-post-rejection_v2.md` | Approved plan custody only after implementation approval; never edit a subsequently frozen plan. |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Codex-authored dated progress and named deferred work; no premature closure. |

No edits to model configuration, recognized-route authorization/providers, baseline, hook mappings, lockfile, marker selection, coverage threshold, Fable's artifacts or Slice B's frozen documents. In particular, this plan does not extend baseline exceptions to a new document.

**Deferred explicitly:** recognized JSON routes currently have unbounded body reads and incomplete framing handling, including malformed Content-Length raising ValueError to handle_error without a deliberate response. Request-header deadlines, global connection/thread admission limits and overall denial-of-service resistance are also outside this correction. Record these under the existing Gateway hardening owner `P11-FEAT-ACP-RUNTIME-HARDENING`; do not claim this change fixes them. Applying limits to recognized routes requires a separate compatibility decision.

## 3. Behavior contract

Private production defaults proposed for approval:

- `_REJECTED_POST_MAX_BYTES = 65_536` (64 KiB).
- `_REJECTED_POST_BODY_SECONDS = 2.0`: one total monotonic deadline beginning when the early-rejection handler starts, after request headers have been parsed.
- `_REJECTED_POST_WRITE_SECONDS = 2.0`: one total monotonic deadline for the small terminal JSON response.

No environment flags or user configuration are added. Tests may override time limits locally for efficient checks, while a separate assertion pins production defaults. These bounds control blocking I/O; host descheduling means they are not hard real-time wall-clock guarantees.

**Compatibility:** Recognized working routes keep their existing behavior. For rejected routes the status changes on malformed, oversized or incomplete inputs are intentional; valid rejected requests also now wait for body completion within the deadline before receiving the same 404. Thus the compatibility change is not limited to malformed-request status codes. Requests using Expect or unsupported transfer coding also have explicit new outcomes. No request-header or whole-Gateway hardening claim is made.

Pin `OptimusGatewayHandler.protocol_version == "HTTP/1.0"` in the regression suite. The current stdlib only auto-handles Expect:100-continue when protocol conditions permit HTTP/1.1. This pin preserves the specified behavior of no interim 100 response before the 417 branch; a future protocol upgrade needs a new Expect policy review. An interim 100 followed by a final response is not inherently a protocol-invalid “double response”; it would violate this plan's explicit no-100 contract.

For a complete, correctly framed body at or below the cap, preserve `404` and `{"error":"not found"}` exactly. Discard bytes without JSON parsing: malformed JSON on an unknown route is still a validly framed unknown-route request. No upstream/provider/auth operation is invoked. Retain the existing HTTP protocol version and close the connection after this terminal response.

For framing/limit failures, select the status below and attempt one bounded terminal response. If a peer withholds or overruns the declared body, sends unsupported framing or has already disconnected, the contract guarantees bounded handling and no dispatch/reuse, **not reliable receipt of an error body**. Do not suppress an exception and count it as a successful valid-body 404.

### Framing and terminal status matrix

Apply this ordering only once the route is classified into the existing early-404 branch:

| Input | Action/status | Body handling |
|---|---|---|
| Both Transfer-Encoding and Content-Length present | 400 `{"error":"invalid request framing"}` | Do not read; close. |
| Multiple Content-Length fields, even identical; comma-list; empty, signed, negative or non-ASCII-decimal value | 400, same JSON | Do not read; close. Strict duplicate rejection is intentional. |
| Transfer-Encoding present without Content-Length, including chunked | 501 `{"error":"transfer encoding not supported"}` | No chunk decoder; do not read; close. |
| Any Expect header on this rejected route | 417 `{"error":"expectation failed"}` | Do not wait for a body the client may withhold awaiting 100 Continue; close. |
| No Content-Length and no Transfer-Encoding | Existing 404 | Treat declared body length as zero. Extra undeclared bytes are outside the valid-request guarantee. |
| Content-Length zero | Existing 404 | No body read. |
| One valid length 1–65,536 and complete body before deadline | Existing 404 | Discard exactly the declared length first. |
| One valid length above 65,536 | 413 `{"error":"request body too large"}` | Do not drain or allocate from the advertised length; close. |
| Valid in-range length, EOF before it is satisfied | 400 `{"error":"incomplete request body"}` | No further reading or dispatch; close. |
| Valid in-range length, total body deadline expires | 408 `{"error":"request body timeout"}` | No retry/reuse of the timed-out buffered stream; close. |
| Peer reset/abort or response write failure | Existing server error/lifecycle behavior | Cleanup still runs; never label a delivered 404 or add a retry. |

Trim HTTP optional whitespace around a single Content-Length value, then require nonempty ASCII digits only. Handle huge decimal strings without converting an attacker-controlled arbitrarily long integer: validate ASCII characters, strip leading zeros (all zeros becomes zero), reject more than five significant digits as oversized, then convert at most five digits and compare against `65_536`. Do not rely on interpreter integer-conversion limits: their settings are distinct from this HTTP policy. Missing is distinct from an explicitly empty field. Use `headers.get_all` so duplicate fields cannot disappear behind `get`.

The strict duplicate policy and unsupported-transfer-coding response are deliberate local policy choices based on HTTP framing requirements, not a claim that every permitted HTTP message form is supported. See [RFC 9112 §6.3](https://www.rfc-editor.org/rfc/rfc9112.html#section-6.3).

## 4. Proposed implementation interfaces and algorithm

Keep helpers private to `server.py`; do not add a framework or generic parser module. Suggested interfaces:

```text
_rejected_post_length(headers) -> int
    returns declared length, including zero
    raises a private rejection exception carrying the selected status and fixed error label

_discard_rejected_post_body(stream, connection, length, deadline) -> None
    consumes exactly length bytes, in chunks <= 8192
    distinguishes EOF, total deadline and peer failure

OptimusGatewayHandler._reject_unhandled_post() -> None
    terminal lifecycle orchestration for existing early-404 branch only

OptimusGatewayHandler._send_json(status, body, *, write_deadline=None) -> None
    optional private deadline for rejection responses; recognized callers keep default behavior
```

The rejection exception must be a simple private type; fixed status/error fields only, no raw request or credentials. No fallible logging in the cleanup/error path and no catching arbitrary exceptions to convert them to 404.

Required orchestration:

1. Mark `close_connection = True`; compute the one absolute deadline before framing/body work.
2. Classify headers once. Read nothing on framing, expectation or size rejection.
3. For a valid positive length, loop until remaining bytes are zero. Before each read, compute `deadline - monotonic()` and reject if nonpositive. Set the socket timeout to that remaining interval.
4. Read `min(8192, remaining)` through **`self.rfile.read1`**, discarding the returned chunk. An empty chunk before completion is EOF, not success. Check the deadline after each read too; a late final byte does not turn an expired operation into success. Do not restart the deadline per chunk.
5. Use the existing buffered stream so header prefetch remains visible. A plain `read(n)` can perform several underlying reads; resetting a per-read inactivity timeout does not enforce the total deadline. `read1` is selected for its at-most-one-raw-read behavior. Verify the installed stream supports it; do not silently substitute raw `recv`. [Python buffered I/O documentation](https://docs.python.org/3/library/io.html#io.BufferedIOBase.read1).
6. After successful discard select the unchanged 404. After a classified rejection select the matrix error. Pass a new monotonic response deadline to the single `_send_json` call. Within that method, only when this optional deadline is present, recompute remaining time before `end_headers()` and again before the body write, setting the socket timeout to the remaining budget each time. Check expiry before both operations. Do not give headers and body a fresh two seconds each; there is one total response budget. Existing callers omit the argument and retain their current behavior. Preserve exception visibility for unexpected peer/write failures; no blanket WinError10053 suppression.
7. Let normal handler cleanup close the connection; do not return it to request parsing. A timed-out socket file may have inconsistent buffered state, so it must not be reused. No SO_LINGER tricks, shutdown sleeps, FIN/RST assertions or global socket defaults. [Python socket timeout and file-object caveat](https://docs.python.org/3/library/socket.html#socket.socket.makefile).

Do not introduce the limits in `setup()` or recognized routes as an incidental refactor. Do not read the body twice. Do not return errors through `send_error` if that silently changes the fixed JSON contract above.

## 5. Deterministic regression and acceptance matrix

### Primary regression: body completion precedes 404

Test all four unconfigured tool paths plus an unknown path against the real handler/server. A test-only subclass or wrapper may observe method calls; it must call the original implementation and must not implement draining itself.

Use an event queue and bounded events, never a sleep chosen to make the race likely:

1. Connect a real loopback client and send only headers declaring a small nonzero body.
2. Install the observer after header parsing, around body-stream reads and `_send_json` (forward every argument, including the optional deadline). It publishes `body_read_requested` or `response_attempted` without changing their result. A response observer records body bytes consumed, not bytes only sent by the client.
3. Wait for the first event. On the old handler it is `response_attempted` with zero consumed bytes: fail with the specific assertion “response attempted before declared body was consumed.” This is the required deterministic RED, not an incidental socket timeout.
4. On the corrected handler the first event is `body_read_requested`. Release a first fragment from the client, observe the next read request, release the remainder, then assert `response_attempted` occurs only after the full count is consumed. Finally read and assert the real 404 JSON with no retry.
5. Always release test latches, close client sockets and tear down/join the server in `finally`, including the intentional RED and failed assertions. Give every wait a deadline. Propagate observer/thread exceptions to the test result. If the old implementation emits response_attempted first, preserve that precise RED and do not send the held body afterward merely to finish the choreography. During unconditional client cleanup only, ignore OSError from shutdown/close after recording it; never ignore body-send/getresponse failures on the corrected valid-body path, server observer failures, or assertions. Do not wait for a 404 before sending the body: that would deadlock the corrected design.

For zero-length/no-body controls, permit an immediate response and assert no read. The observer must distinguish header reads from body reads. Use opaque bytes that are invalid JSON as one complete-body case to prove early rejection does not invoke JSON parsing.

### Test watchdog and error-delivery oracles

For the stalled-client test with production defaults, set an external process/test watchdog of **10 seconds**: the two body/write budgets total four seconds of permitted I/O before scheduling and shutdown overhead. The watchdog is not a widened production timeout and must not turn an unfinished run into success. Record handler completion and thread join; a watchdog firing is a failed control with guaranteed cleanup. Verify `ThreadingHTTPServer.daemon_threads` and `block_on_close` for the pinned interpreter rather than assuming server_close always joins request threads: daemon request threads can be excluded from that join. The existing helper joins only the serve thread. Explicit handler completion is therefore mandatory regardless of server_close behavior.

Every error/framing matrix case must assert server-side status selection, body-read count, no dispatch, and terminal handler completion. Read client error JSON only as supplementary evidence when available; never require receipt for a rejected/undrained body on Windows. This restriction does not weaken the valid complete-body 404 test: its real client must receive the exact status/body without socket-error tolerance. Use raw headers for duplicate/malformed cases so an HTTP client library cannot normalize the specimen away.

### Additional tests

| Requirement | Specific oracle |
|---|---|
| Exact body cap | 65,536 bytes is accepted for discard; 65,537 selects 413 without a body read. No allocation proportional to the oversized declaration. |
| Total deadline, not inactivity timeout | A deterministic fake clock/stream returns small chunks while advancing time; once cumulative time exceeds two seconds, helper selects timeout even if each individual interval is short. No clock reset on progress. Separately consume the response budget during a headers-write stub and verify the body write receives only the remainder or is rejected when expired. |
| Real stalled client | Send valid headers and withhold body. With a test-local short body limit, capture timeout decision and bounded handler completion. Do not require a reliably delivered 408 if the body remains unread. One test retains production defaults to verify practical cleanup under normal scheduling, with the separate 10-second test watchdog specified above. |
| Incomplete body | Half-close the client's send side after a fragment; EOF must select 400 and close, without provider calls. |
| Framing | Parameterize duplicate equal/different CL, comma values, negative, plus sign, alphabetic, empty, enormous decimal, leading-zero valid number, TE alone and CL+TE. Assert chosen status and no read on rejection. |
| Expect | Reject Expect without waiting for body or writing 100 Continue. |
| Buffering | Deliver headers+body together and in fragments; both valid cases produce the same 404. Include data already in the buffered reader. |
| Deadline failure path | After timeout, no second read, no parser reuse and exactly one bounded error-response attempt. Inject a response write error and prove cleanup still completes and the exception is not reported as success. |
| Lifecycle | Capture request-handler completion as well as serve-thread join. Assert no owned handler or socket remains after each scenario. Do not mistake a serve thread's exit for all request threads finishing. |
| Recognized routes | Existing configured tool/model/observability tests remain unchanged and pass; provider invocation and response semantics are unchanged. |

Mutation controls: remove the body discard; restore a per-chunk resetting deadline; remove the size check; hide duplicate headers using `get`; accept EOF as complete. Each must fail its own named oracle. Run mutants only in memory or disposable copies, never alter source pins to manufacture RED. Do not create tests whose expected configuration is read back from the implementation under test.

The deterministic regression establishes the ordering invariant. A separate bounded real Windows check exercises that invariant with the unmodified client and unchanged route assertions; it must not claim a universal “zero flake” rate. The Fable forced-send-delay harness is supporting historical evidence, not a replacement for this regression or a shipping workaround.

### Environment preservation for the executor

Windows direct interpreter: `C:/worktrees/optimus-cost-agent-wt-claude-ci-production/.venv/Scripts/python.exe`, CPython 3.14.4, using installed locked tools. Set `PYTHONDONTWRITEBYTECODE=1`; verify `optimus_gateway.server.__file__` resolves inside the correction checkout despite any editable installation. Do not write new packages into that shared environment. If uv is unavoidable, pin invocation-only VIRTUAL_ENV and UV_PROJECT_ENVIRONMENT to that exact Windows .venv and set UV_NO_SYNC=1 and UV_OFFLINE=1. No sync, install, upgrade or repair.

WSL uses `/root/optimus-ci-venv/bin/python` (3.14.6), not the Windows .venv; pin the two environment variables to `/root/optimus-ci-venv` and retain no-sync/offline. Verify candidate Windows pyvenv.cfg SHA-256 `9c503845220632572999aad4d94004d287277ec4971a5230d8a12fcd3ee91afb` and Scripts layout before/after. Record versions rather than silently aligning them. Keep source, baseline, lock and all candidate/rehearsal refs/indexes unchanged; allow only the new correction checkout and its sibling evidence/temp area to receive writes.

## 6. Future execution plan and time box

**Proposed future allowance: 120 combined-agent active minutes**, including review and reporting. This drafting approval has not started that box. No automatic continuation. Count all agents' work, exclude relay idle, and finish evidence/reporting within the allowance. No full delivery rehearsal or commit is included.

### Plan and registry custody for the correction package

At first approved setup, include v2 at its exact scoped plan path and **exactly one** `Active` live-registry row for that path in the correction checkout's sole backlog. Preserve every existing base registry row. The operator's future approval changes v2 from the reviewer's current Blocked state to executable Active; record the real approval and box start in an external entry record, never by rewriting a sealed plan.

Codex supplies the scoped row/progress patch against the correction checkout's own bound base. Do not copy the entire current reviewer backlog into the base clone: it also contains unrelated uncommitted Slice B plan rows whose files are not correction inputs. V1 stays at its existing reviewer/output locations, unchanged, with its reviewer-side Blocked historical row. It is not newly staged, copied into the correction package, archived, deleted or retrofitted with a table. If v1 custody is later requested, resolve its own post-2026-08-18 prerequisites requirement first; do not discover that issue at a commit gate.

The exact new row shape, activated only after implementation approval, is:

| Plan | State | Owner | Next gate |
|---|---|---|---|
| [P11-FU-6 — bounded early POST rejection corrective plan v2](2026-09-05-p11-fu6-bounded-early-post-rejection_v2.md) | `Active` | `P11-FU-6` | Approved correction-only implementation under the recorded 120-minute box; deterministic RED, bounded rejected-route handling, Windows/WSL controls and Codex review. No candidate integration, commit or delivery revalidation. |

V2 and that row form one custody unit in the uncommitted correction handoff and any separately authorized later custody commit. No commit is permitted by this correction phase. Do not create a standalone amendment or new owner ID. Future archiving needs its own mechanical custody proof and corresponding row transition.

Validate the new plan directly with the repository's `_assert_prerequisites_table` helper as well as document-directory hygiene. The history-based prerequisite test discovers additions through `git diff <amendment>..HEAD`, so an uncommitted new document can be missed by a passing ordinary test run. Explicitly validate the actual new v2 bytes and prospective added-path classification before any later commit. Do not change a test or exclusion to admit this plan.

### Task 1 — Isolated source and deterministic RED (30 minutes maximum)

- [ ] After explicit implementation approval, record UTC start and budget. Read the current reviewer checkpoint, this approved plan digest and governing investigation addendum. Verify incident log and source identities.
- [ ] Create a fresh independent correction clone at exact c1989985, destination `C:/Users/pc/AppData/Local/Temp/fu6-correction-<actual-UTC-start>/checkout`, only if absent. Use --no-local, sanitize inherited Git environment, prove both Git stores contained and no alternates. Preserve all existing checkouts/rehearsals, refs and untracked files; no reset/clean/tag operations.
- [ ] Keep evidence and test temp under the sibling `evidence` and `tmp` directories, outside the tested checkout. Use existing verified Windows tooling with no sync and explicit import provenance to this correction source. Do not claim the base checkout contains the whole failed Slice B delta.
- [ ] Add the new regression test file. Execute the focused old-handler RED and no-body control once; preserve exact assertion, command and cleanup result. No shipping source edit before that RED.
- [ ] Codex verifies the RED is the premature-response assertion rather than an observer bug, exception from teardown or unrelated connection error. If no credible deterministic RED within 30 minutes, stop with evidence and remaining questions; do not consume the whole box on trial-and-error timing.

### Task 2 — Minimal early-rejection correction (40 minutes maximum)

- [ ] Implement only the scoped helpers and early-404 call site with the precise limits/status ordering above. Preserve recognized dispatch code. Record the small implementation diff.
- [ ] Add/execute framing, exact-limit, total-deadline, buffered-body and cleanup tests. Run the independent mutants against their specific oracles.
- [ ] Run existing Gateway route tests and the new file using direct verified Python:

```text
python -X utf8 -m pytest -q tests/unit/optimus_gateway/test_request_body_rejection.py tests/unit/optimus_gateway/test_server.py
python -X utf8 -m ruff check src/optimus_gateway/server.py tests/unit/optimus_gateway/test_request_body_rejection.py
git diff --check
```

These are command shapes; invoke the verified absolute interpreter, with PYTHONDONTWRITEBYTECODE=1 and a resolved external basetemp. Preserve existing pytest selection settings and import-path evidence. Any diagnostic targeted selector must be labelled as such, never full-suite acceptance.

### Task 3 — Cross-platform review evidence (30 minutes maximum)

- [ ] Execute the deterministic/new tests and existing Gateway file on Windows and native WSL with environments separately pinned and candidate Windows cfg/layout checked before/after. WSL results are comparison evidence; Windows remains required.
- [ ] A future approval to implement this plan includes these bounded corrective RED/GREEN diagnostic tests, not a retry-until-green loop. Any unexpected FU-6 error in the corrected suite stops for review with a new log; no blind retry, timeout widening, marker change or suppression. Expected old-code RED is separately labelled.
- [ ] Review connection/error lifetimes, two deadlines, cap boundaries and compatibility. Run relevant static checks already installed; do not install dependencies or change scanner settings to clear new findings. Individually review new non-credential literals before pragmas; no baseline expansion.
- [ ] Draft the scoped README note and Codex-owned backlog disposition, retaining the v2 registry row in the same correction package as v2. Explicitly register recognized-route/body-header/global-resource hardening as deferred. Do not claim FU-6 closure, final delivery or packet-level proof.

### Task 4 — Independent review and STOP handoff (20 minutes reserved)

- [ ] Codex reviews exact source/test/doc diff and raw evidence. Record final hash, source identity, output manifest, passed/failed/timeout rows and any remaining risk. Preserve old RED, mutants and diagnostic variants externally.
- [ ] Stop with an uncommitted correction in the separate checkout. No candidate staging, commit, cherry-pick, merge, full delivery hook, publication or installation.
- [ ] Prepare a proposed integration sequence for later approval: how this correction and Slice B are combined, what exact final tree is reviewed, and which Windows revalidation and actual commit gates are required. Do not invent a new branch/base or reuse a passing old tree to bypass the failed final tree.

If any task overruns, check all remaining mandatory work against the remaining box and stop rather than compressing review. There is no 40-minute Slice B reservation within this correction-only proposal; its delivery window remains a separate decision.

## 7. Done for this correction phase; not delivery

The phase is reviewable only when the old-code regression fails for the intended ordering reason; the corrected implementation passes all scoped functional/framing/deadline/cleanup cases on Windows; WSL comparison is recorded; mutants prove the controls are load-bearing; recognized routes remain unchanged; and Codex accepts the exact diff with complete evidence. No broad reliability rate is inferred.

Required artifacts: `entry-state.json`, `red-ordering.log`, `green-windows.log`, `green-wsl.log`, `mutants.json`, `framing-deadline-cases.json`, `thread-cleanup.json`, `correction.patch`, `review.md`, `MANIFEST-sha256.txt`. Preserve command, version, source/tree, times and true exit status for every run. Preserve any failed attempt before appending a manifest. Never write evidence into frozen incident custody.

Later implementation approval must explicitly accept this phase's 64 KiB/two-second body and two-second write choices, status/compatibility changes and 120-minute allowance. Later Slice B integration/revalidation needs a separate approval tied to the exact failed log and final source tree; the historical P1 is not reusable.

**Current next action:** operator reviews this draft corrective design and names the executor when approving implementation (Fable 5.1 proposed). Codex has completed planning only. No executor has been dispatched and no new runtime experiment has run.
