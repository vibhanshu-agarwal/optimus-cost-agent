# Plan 9.95 Usage, Telemetry, and Evidence-Tooling Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILLS: Use `superpowers:executing-plans` to execute this
> plan task-by-task and `superpowers:test-driven-development` for every behavior change. Do not use
> `superpowers:subagent-driven-development` unless the operator explicitly authorizes subagents for
> the implementation session.

**Status:** Approved by the reviewer-agent and operator on 2026-07-14. Implementation has not
begun. Execution must start only after this documentation PR merges, from a fresh branch based on
the latest `origin/main`, as required by the handoff below.

**Goal:** Close `P9.85-FU-6`, `P9.88-FU-2`, and `P9.88-FU-3` by making failed-attempt cost handling
honest and budget-safe, keeping multi-file read telemetry mechanically aligned, and pinning a
reproducible Plan 9.88 ceremony-ledger digest.

**Architecture:** Treat each Gateway wire attempt as one of two accounting outcomes: a valid
Gateway-reported usage envelope, which is charged and persisted exactly once whether the attempt
succeeds or fails, or unknown cost, which is never represented as zero and terminates the retry
sequence before another potentially billable request. Preserve the public parallel telemetry fields
for compatibility, but derive all of them from one canonically ordered read-evidence sequence and
validate their cardinality. Define the ceremony ledger as all Plan 9.88 JSON records in report order,
canonicalize each record deterministically, and expose the digest through the existing verifier.

**Tech Stack:** Python 3.14+, Pydantic v2, `Decimal`, standard-library `urllib`, `json`, `hashlib`,
`pytest`, `pytest-asyncio`, `pytest-cov`, Ruff, `uv`, the existing Optimus Gateway client,
`RetryController`, usage ledger, ACP progress/debug trace, and Plan 9.87/9.88 evidence verifier.

**Estimated implementation size:** 2-3 weeks for one implementation lane, including TDD,
real-transport integration, evidence correction, and reviewer/operator checkpoints.

**Design approval:** On 2026-07-14 the operator approved the three-plan split: Plan 9.95 owns only
`P9.85-FU-6`, `P9.88-FU-2`, and `P9.88-FU-3`; Plan 9.96 owns `P9.85-FU-7` and `P9.9-FU-1`; Plan
9.97 owns `P9.87-FU-1`. The roadmap custody update on this branch is part of the planning artifact,
not implementation evidence. The reviewer-agent approved the amended detailed plan on 2026-07-14;
the operator approved the detailed plan on 2026-07-14. This approval does not authorize
implementation on the planning branch.

## Source Anchors and Conflict Check

- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, Plan 7 and Plans 9.85/9.87/9.88/9.95:
  Gateway/Provider usage custody, exact FU-6/FU-2/FU-3 triggers, and accepted-open FU-4B boundary.
- Architecture v2.15, pages 9-13: Gateway usage envelope, post-call attribution, one-key provider
  boundary, and observability flow.
- LLD v2.38, pages 31-40: evidence ledger, `ProviderUsage`, reconciliation, accounting/telemetry
  gates, and retry guardrails.
- Test Strategy v1.4, pages 5-10: malformed Gateway responses, cost accounting, trace fields,
  transient/permanent failure injection, and secret masking.
- `docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md`, Deferred
  Follow-Ups: FU-6 remaining acceptance for billable transient failures and unknown transport cost.
- `docs/superpowers/plans/2026-07-13-plan-9-88-fu4b-evidence-remediation-and-plan-9-87-closure.md`,
  Deferred Follow-Ups: the digest-helper acceptance and read-range telemetry misattribution trigger.
- `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`: current eight-record Plan 9.88
  ledger, the unpinned `9122...` value, and the disclosed multi-file telemetry defect.
- Live code seams: `src/optimus/gateway/{client,errors,models}.py`,
  `src/optimus/agent/{planning_loop,runner,models}.py`, `src/optimus/acp/{spec,debug_trace}.py`,
  `src/optimus/usage/{accounting,ledger,models}.py`, and
  `tools/verify_plan987_acpx_evidence.py`.

No conflict was found among these anchors for this scope: all require authoritative Gateway usage,
honest failure accounting, structured content-free telemetry, and deterministic evidence. If the
implementation agent finds a newer authoritative document or current wire behavior that conflicts
with the fixed semantics below, stop and request a plan amendment before changing code.

## Global Constraints

1. **Exactly three follow-ups:** This plan implements only `P9.85-FU-6`, `P9.88-FU-2`, and
   `P9.88-FU-3`. No implementation work outside these three follow-ups is in scope; **Explicit
   Exceptions** enumerates adjacent work that must remain separate. Widening or narrowing these
   three follow-ups requires a reviewed plan amendment.
2. **Gateway usage is authoritative:** Charge only a successfully validated `GatewayUsage` envelope.
   Never estimate tokens, billing units, credits, or dollars from prompts, response text, latency,
   provider status, or retry count.
3. **Unknown is not zero:** A wire attempt without a valid usage envelope makes the aggregate cost
   incomplete. Preserve the sum of previously reported usage as a known lower bound, set
   `cost_complete=False`, increment `unknown_cost_attempt_count`, and terminate with
   `PLANNING_GATEWAY_COST_UNKNOWN` before any further retry.
4. **Reported failures are billable:** If a failed attempt carries valid usage, append its Gateway
   request ID, add its reported cost to the planning aggregate, and invoke the existing usage
   callback exactly once before retry classification decides whether another attempt is allowed.
5. **Budget is checked between wire attempts:** A retry is allowed only when all earlier attempt
   costs are complete and the reported aggregate remains strictly below the run cap. If a reported
   failed attempt reaches or exceeds the cap, stop with `PLANNING_BUDGET_EXHAUSTED`; do not dispatch
   another request.
6. **Settled turns remain distinct from wire attempts:** Failed attempts and retries never increment
   `settled_turns`. `wire_retry_count` remains the count of retries actually dispatched, while each
   reported usage record keeps request ID `run_id:planning:{settled_turn}:{wire_attempt}`.
7. **No double charge:** A valid usage envelope is recorded through one helper shared by success and
   failure paths. The success path must not append or charge the same attempt a second time.
8. **Normalized persistence rule stays explicit:** The planning aggregate always uses valid wire
   `GatewayUsage`. `UsageAccountingService` persists a `ProviderUsage` row only when the Gateway
   supplied its existing required normalized fields. Plan 9.95 does not synthesize missing
   `service`, `native_unit`, `optimus_credits_debited`, or `price_snapshot_id`.
9. **Content-free telemetry:** Cost-completeness state, counts, request IDs, paths, byte ranges,
   hashes, stop reasons, and exception class names may be logged. Exception messages, Gateway
   bodies, prompts, responses, source bodies, credentials, and authorization values may not be
   added to progress or debug telemetry.
10. **Misattribution, not cosmetic ordering:** `P9.88-FU-3` is closed only when every
    `read_identity`, `source_sha256`, and byte count refers to the same read after canonical ordering,
    and the downstream evidence summary preserves that association. Sorting one tuple alone is a
    failing implementation.
11. **Compatibility at the ACP boundary:** Keep the existing progress message text and public
    `read_identities`, `source_sha256s`, and `read_byte_counts` field names. Additive cost-completeness
    fields are allowed; do not expose raw evidence or change the approval protocol.
12. **Digest domain is closed:** The Plan 9.88 digest covers all and only JSON object blocks whose
    `evidence_lane` equals `P9.88-FU4B`, in physical report order. That includes the lane header,
    original and corrected pre-registrations, infrastructure-invalid records, and evidence summaries.
13. **Digest canonicalization is exact:** Recursively sort object keys with
    `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`,
    encode UTF-8, and terminate every record, including the last, with one LF byte. Preserve list
    order and record order. Reject an empty ledger.
14. **Historical correction is transparent:** The current ceremony value
    `9122c5c1b2978a8de515710df2c2cb38347bc7bd205e2837ac3b7b2bdf118b3d` is not silently overwritten.
    Amend the report to retain it as the unpinned originally recorded value and record the pinned
    value plus verifier command. Do not alter the Plan 9.88 plan file.
15. **Evidence tiers are honest:** Unit doubles prove branching and invariants. The transport
    integration uses the real `UrllibGatewayTransport` against a local standard-library HTTP server.
    It is not labeled `requires_gateway` and does not claim real-provider behavior. No fake may be
    presented as a live Gateway or provider.
16. **No paid failure fishing:** This plan does not deliberately provoke billable provider failures.
    A real staging Gateway run is neither necessary nor sufficient for deterministic failure-path
    sign-off. Existing live Gateway tests remain regression coverage, not evidence for injected
    error cases.
17. **One-key boundary:** Product code continues to use only `OPTIMUS_GATEWAY_URL` and
    `OPTIMUS_API_KEY`. No provider key or provider-specific API behavior is added to the agent.
18. **Approval-gated commits:** At each task boundary, show the exact diff and named verification
    output, wait for explicit operator approval, then commit only the task's listed files. Never use
    `--no-verify`.
19. **Checkbox protocol:** Set `- [x]` only after the step's literal verification command ran and
    passed. Prose summaries and screenshots are not substitutes.
20. **Quality gates:** Before each code commit run focused tests, Ruff on changed Python, and
    `git diff --check`. Final sign-off requires the full default suite, aggregate Python production
    coverage at or above 80%, full Ruff, the pinned ledger verifier, and the integration evidence
    report.

## Requirements Traceability

| Requirement | Owning tasks | Mechanical evidence |
|---|---|---|
| R1: failed attempts with reported usage are aggregated and persisted once | Tasks 1-3 and 6 | Gateway error-envelope tests; planning retry tests; ledger request IDs; real-transport integration |
| R2: unknown transport cost is never reported as zero/complete and prevents another retry | Tasks 2, 3, and 6 | `PLANNING_GATEWAY_COST_UNKNOWN`; `cost_complete=False`; one HTTP request; no plan/hash/mutation |
| R3: failed-attempt cost participates in the run cap before retry | Task 2 | exact-cap and over-cap tests assert no later wire attempt |
| R4: settled-turn, wire-attempt, provider usage, and telemetry identifiers remain correlated | Tasks 2 and 3 | callback sequence and `ProviderUsage.request_id` assertions; final progress/debug assertions |
| R5: non-alphabetical multi-file read telemetry cannot misattribute hashes or byte counts | Task 4 | planning-loop regression plus downstream evidence-summary association test |
| R6: Plan 9.88 ledger digest is deterministic and independently checkable | Task 5 | fixed vector; CLI mismatch/pass tests; amended ceremony report command |
| R7: historical evidence and deferred-scope custody remain honest | Tasks 5 and 7 | Plan 9.88 plan unchanged; report amendment; roadmap/README exclusions |

## Explicit Exceptions

- `P9.85-FU-7` deliberate access to unredacted traces and the logging-surface security audit are
  owned solely by tracked Plan 9.96. Plan 9.95 does not add a redaction opt-out.
- `P9.9-FU-1` workspace-influenced launch-environment trust is owned solely by tracked Plan 9.96.
  Plan 9.95 does not change environment or credential precedence.
- `P9.87-FU-1` mechanical final-WRITE grounding is owned solely by tracked Plan 9.97. It must not
  absorb or be absorbed by Plan 11. Aligning telemetry tuples is not a grounding guard.
- FU-4B remains accepted-open under the Plan 9.88 Outcome B ceremony. Pinning its ledger digest
  does not make `--require fu4b` pass, reopen the attempt cap, or change the disposition.
- Plan 10 Gateway capability brokering and non-model usage normalization remain separate.
- Plan 11 intelligent context selection/compression remains separate.
- General retry-policy redesign, retry telemetry for non-planning consumers, provider SDK changes,
  price-table changes, and Gateway-side provider-key handling are out of scope.
- Missing normalized fields in legacy Gateway usage are not backfilled or estimated in this plan.
- Existing Plan 9.6, 9.7, 9.75, 9.8, 9.85, 9.87, 9.88, and 9.9 plan files are frozen. Only the
  named Plan 9.87 evidence report may receive the explicit digest amendment required by
  `P9.88-FU-2`.
- Plans 9.96 and 9.97 receive roadmap custody entries only on this planning branch. They do not get
  implementation-plan files here.

## Fixed Interfaces and Semantics

### Gateway failure usage

Extend both typed Gateway errors with optional validated usage:

```python
class GatewayHttpError(GatewayError):
    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        gateway_usage: GatewayUsage | None = None,
    ) -> None: ...


class GatewayResponseError(GatewayError):
    gateway_usage: GatewayUsage | None
```

`parse_gateway_usage(body: Mapping[str, Any]) -> GatewayUsage` is the single strict parser for a
`gateway_usage` object. Successful-response parsing calls it. HTTP-error parsing may call it only
when the decoded error body is an object containing `gateway_usage`; an absent or invalid envelope
leaves `GatewayHttpError.gateway_usage is None`. The transport must not replace the primary HTTP
status/message with usage-validation errors.

When a successful HTTP status contains valid usage but malformed output or response ID,
`parse_gateway_response()` raises `GatewayResponseError(..., gateway_usage=usage)`. That attempt is
reported and billable even though no usable model response exists.

### Planning cost completeness

Add these fields, defaulting compatibly for existing callers:

```python
class PlanningLoopResult(BaseModel):
    total_cost_usd: Decimal = Decimal("0")  # sum of valid reported usage; lower bound if incomplete
    cost_complete: bool = True
    unknown_cost_attempt_count: int = Field(default=0, ge=0)


class PlanningProgressEvent(BaseModel):
    cost_complete: bool = True
    unknown_cost_attempt_count: int = Field(default=0, ge=0)


class AgentRunResult(BaseModel):
    cost_complete: bool = True
    unknown_cost_attempt_count: int = Field(default=0, ge=0)
```

Use two internal terminal exceptions in `planning_loop.py` so `RetryController` remains the one
retry-decision engine while `run_iteration()` receives an exact planning stop:

```python
class PlanningGatewayCostUnknownError(PermanentGatewayError):
    """A dispatched planning attempt has no valid authoritative usage envelope."""


class PlanningGatewayInvocationError(RuntimeError):
    def __init__(self, stop_reason: str, *, reported_cost_usd: Decimal) -> None: ...
```

The retry operation raises `PlanningGatewayCostUnknownError` after setting incomplete state.
`_invoke_planning_gateway()` inspects the `RetryResult` and raises
`PlanningGatewayInvocationError` with either `PLANNING_GATEWAY_COST_UNKNOWN`,
`PLANNING_BUDGET_EXHAUSTED`, or `PLANNING_GATEWAY_FAILURE`. `run_iteration()` converts that typed
exception to `_typed_planning_failure()` using the invocation's reported sequence-cost delta.

A failure proven to occur before `GatewayTransport.post_json()` dispatch has known-zero incremental
cost. The planning wrapper has no authoritative dispatch marker for an arbitrary non-`GatewayError`
raised after `GatewayClient.create_response()` begins, so this plan deliberately treats that case as
unknown rather than guessing pre- versus post-dispatch. This conservative choice can overstate cost
uncertainty for a genuine pre-dispatch code bug, but it cannot hide possible spend. Emit one
content-free `P9.95-USAGE-UNKNOWN` debug record with `run_id`, `session_id`, `planning_turn`,
`wire_attempt`, and `error_type=type(exc).__name__`; never include `str(exc)` or a traceback in that
record. A future dispatch-marker optimization requires its own reviewed evidence and must not infer
dispatch state from exception type alone.

Use one `_record_reported_gateway_usage(usage, planning_turn, wire_attempt)` helper to append the
Gateway request ID, add `cost_usd`, set provider, and call `PlanningGatewayUsageCallback`. Invoke it
exactly once on success or on a typed Gateway exception carrying usage.

The terminal matrix is fixed:

| Last wire outcome | Retry behavior | Stop reason | Cost fields |
|---|---|---|---|
| reported transient failure, aggregate below cap | normal `RetryController` decision | none yet | complete; failed usage included |
| reported transient failure, aggregate at/above cap | no next request | `PLANNING_BUDGET_EXHAUSTED` | complete; failed usage included |
| reported permanent/malformed response failure | no retry | `PLANNING_GATEWAY_FAILURE` | complete; failed usage included |
| failure with no valid usage | no retry regardless of HTTP retryability | `PLANNING_GATEWAY_COST_UNKNOWN` | incomplete; prior reported sum retained |
| reported failure(s), then success | settle normally | existing result | complete; every reported attempt included once |

Add `PLANNING_GATEWAY_COST_UNKNOWN` to planning corrective text and ACP terminal-stop handling. Its
operator-facing text must say the Gateway attempt cost could not be verified and planning stopped
before retrying; it must not include an error body.

### Read telemetry alignment

Add a pure helper with one ordering decision:

```python
def planning_read_telemetry_fields(
    read_evidence: tuple[PlanningReadEvidence, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[int, ...]]:
    ordered = tuple(
        sorted(
            read_evidence,
            key=lambda item: (item.path, item.start_byte, item.end_byte, item.source_sha256),
        )
    )
    return (
        tuple(f"{item.path}#bytes={item.start_byte}:{item.end_byte}" for item in ordered),
        tuple(item.source_sha256 for item in ordered),
        tuple(item.end_byte - item.start_byte for item in ordered),
    )
```

`PlanningProgressEvent` receives an after-validator requiring
`read_request_count == len(read_identities) == len(source_sha256s) == len(read_byte_counts)`.
The READ_MORE branch calls the helper once and passes the three returned tuples. The original read
execution and observation order remain unchanged; only the telemetry projection is canonicalized.

### Ceremony ledger digest

Add this public helper to `tools/verify_plan987_acpx_evidence.py`:

```python
def ledger_digest(records: Sequence[Mapping[str, object]]) -> str:
    _require(bool(records), "FU-4B ledger is empty")
    payload = b"".join(
        json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
        for record in records
    )
    return hashlib.sha256(payload).hexdigest()
```

The fixed unit vector is two records in this order:

```text
{"a":"alpha","z":2}\n{"a":1}\n
```

Its SHA-256 is `083d33790eef3a46cebde05f11206acfe01598a08bc3ab610d81c9fafe6bf2ec`.
Applying the same proposed contract to the eight current `P9.88-FU4B` records produces
`e265065147f505e56ed1ad8d60571f9d1f212fb8f8d192ec407121c0e7ac4195`. Implementation must
recompute this value with the checked-in helper before amending the report; a mismatch stops Task 5
for review rather than changing the contract to fit a desired digest.

Extend `verify_report(..., fu4b_ledger_digest: str | None = None)` and add composable CLI option
`--check-fu4b-ledger-digest SHA256`. Supplying it requires Plan 9.88 records and compares the exact
lowercase hexadecimal digest. The argument parser rejects any value outside `^[0-9a-f]{64}$` before
reading the report. It may be used with `--require` and
`--check-fu4b-ledger-status`; it does not alter claim selection or watched-path checks.

## File and Responsibility Map

- Modify `src/optimus/gateway/errors.py`: optional validated usage on typed Gateway failures.
- Modify `src/optimus/gateway/models.py`: strict reusable usage parser and usage-preserving malformed
  response errors.
- Modify `src/optimus/gateway/client.py`: parse valid usage from HTTP error JSON without inventing it
  for transport/no-body/invalid-body failures.
- Modify `src/optimus/agent/planning_loop.py`: per-attempt aggregation, unknown-cost terminal state,
  between-attempt budget gate, aligned read telemetry, result/progress completeness fields, and
  corrective text.
- Modify `src/optimus/agent/models.py`: additive cost-completeness fields on `AgentRunResult`.
- Modify `src/optimus/agent/runner.py`: propagate planning completeness to the final run result and
  retain stable per-attempt usage persistence identifiers.
- Modify `src/optimus/acp/spec.py`: recognize `PLANNING_GATEWAY_COST_UNKNOWN` as a terminal planning
  result with `end_turn` and no permission request.
- Modify `src/optimus/acp/debug_trace.py`: log content-free cost completeness and unknown-attempt
  count beside reported aggregate cost.
- Modify `tools/verify_plan987_acpx_evidence.py`: canonical ledger digest helper, API, and CLI gate.
- Modify `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`: transparent digest amendment
  and durable verifier command only.
- Create `tests/integration/gateway/test_failed_usage_transport_flow.py`: actual urllib/local-HTTP
  transport coverage for reported and unknown failed-attempt cost.
- Modify the focused unit tests named in Tasks 1-5.
- Create `reports/plan-9-95-usage-telemetry-evidence.md`: sanitized claim-to-evidence record.
- Modify `README.md` and `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` only at closure.
- Update this plan's checkboxes only after the literal gates pass.

---

### Task 0: Reconfirm the Approved Baseline Before Implementation

**Deliverable:** The implementation agent starts from current `main`, confirms the three-FU scope,
and proves the planning artifact was approved before code changes.

**Files:**
- Read: `AGENTS.md`
- Read: `CONTRIBUTING.md`
- Read: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Read: this plan

- [x] **Step 1: Confirm branch ancestry and a clean scoped baseline**

Run:

```bash
git fetch origin
git merge-base --is-ancestor origin/main HEAD
git status --short --branch
```

Expected: the ancestry command exits 0. Stop if the worktree contains unrelated changes that overlap
any file in the File and Responsibility Map; do not reset or overwrite them.

- [x] **Step 2: Confirm custody and exclusions mechanically**

Run:

```bash
rg -n "Plan 9\.95|P9\.85-FU-6|P9\.88-FU-2|P9\.88-FU-3|Plan 9\.96|Plan 9\.97" \
  docs/superpowers/plans/2026-07-01-phase-1-roadmap.md \
  docs/superpowers/plans/2026-07-14-plan-9-95-usage-telemetry-evidence-tooling-correctness.md
```

Expected: Plan 9.95 owns exactly the three implementation follow-ups; Plans 9.96 and 9.97 remain
tracked-only with no implementation plans.

- [x] **Step 3: Record reviewer-agent and operator approval**

Add the approval date and review disposition to this plan's `Status` and `Design approval` fields.
Do not mark this step complete from chat memory; use the approved plan text on disk.

Evidence (2026-07-14): the reviewer-agent and operator both approved the amended detailed plan;
their dispositions are recorded in the `Status` and `Design approval` fields above.

- [x] **Step 4: Request approval for the Task 0 documentation-only commit**

Run:

```bash
git diff --check
git diff -- docs/superpowers/plans/2026-07-01-phase-1-roadmap.md \
  docs/superpowers/plans/2026-07-14-plan-9-95-usage-telemetry-evidence-tooling-correctness.md
```

After explicit operator approval only:

```bash
git add docs/superpowers/plans/2026-07-01-phase-1-roadmap.md \
  docs/superpowers/plans/2026-07-14-plan-9-95-usage-telemetry-evidence-tooling-correctness.md
git commit -m "Plan usage telemetry and evidence correctness"
```

---

### Task 1: Preserve Reported Usage on Gateway Failures

**Deliverable:** Typed Gateway errors carry a valid Gateway usage envelope when one exists, while
missing or malformed error usage remains explicitly absent.

**Files:**
- Modify: `src/optimus/gateway/errors.py`
- Modify: `src/optimus/gateway/models.py`
- Modify: `src/optimus/gateway/client.py`
- Modify: `tests/unit/gateway/test_models.py`
- Modify: `tests/unit/gateway/test_client.py`
- Modify: `tests/unit/gateway/test_usage_fields.py`

- [ ] **Step 1: Write failing model tests for usage-preserving malformed responses**

Add exact tests:

- `test_missing_output_preserves_valid_gateway_usage_on_response_error`
- `test_invalid_response_id_preserves_valid_gateway_usage_on_response_error`
- `test_invalid_gateway_usage_has_no_partial_usage`

The first two assert `exc_info.value.gateway_usage.gateway_request_id == "gw-failed-1"`; the last
asserts `exc_info.value.gateway_usage is None`. Run:

```bash
uv run pytest tests/unit/gateway/test_models.py tests/unit/gateway/test_usage_fields.py -q
```

Expected RED: valid usage is currently discarded by later response-validation failures.

- [ ] **Step 2: Extract the strict usage parser and preserve usage on later parse failures**

Implement `parse_gateway_usage()` and route `parse_gateway_response()` through it. Attach `usage`
to every `GatewayResponseError` raised after usage validation succeeds. Do not attach a partially
validated dict.

- [ ] **Step 3: Write failing transport tests for reported and unknown HTTP-error cost**

Add exact tests:

- `test_urllib_http_error_with_valid_gateway_usage_attaches_usage`
- `test_urllib_http_error_without_gateway_usage_has_unknown_cost`
- `test_urllib_http_error_with_malformed_gateway_usage_has_unknown_cost`
- `test_urllib_url_error_has_unknown_cost`

Assert status codes remain intact, no raw authorization header appears in `str(error)`, and only the
first case has `gateway_usage`.

Run:

```bash
uv run pytest tests/unit/gateway/test_client.py -q
```

Expected RED: `GatewayHttpError` currently has no usage field and the transport treats the body only
as message text.

- [ ] **Step 4: Parse optional error usage without changing primary error semantics**

Decode an HTTP error body once. If it is an object with a valid `gateway_usage`, attach the model.
If decoding or usage validation fails, retain `gateway_usage=None` and preserve the HTTP status.
Do not let error-usage parsing raise `GatewayResponseError` out of the transport.

- [ ] **Step 5: Verify Task 1**

Run:

```bash
uv run pytest tests/unit/gateway/test_models.py tests/unit/gateway/test_client.py \
  tests/unit/gateway/test_usage_fields.py -q
uv run ruff check src/optimus/gateway/errors.py src/optimus/gateway/models.py \
  src/optimus/gateway/client.py tests/unit/gateway
git diff --check
```

Expected: all focused tests pass, Ruff is clean, and diff check is clean. Show the diff and wait for
operator approval before committing only Task 1 files.

---

### Task 2: Aggregate Every Reported Planning Attempt and Fail Closed on Unknown Cost

**Deliverable:** Planning cost and request IDs include reported failed attempts; unknown transport
cost cannot be retried or presented as complete.

**Files:**
- Modify: `src/optimus/agent/planning_loop.py`
- Modify: `tests/unit/agent/test_planning_loop_runner.py`
- Modify: `tests/unit/retry/test_policy.py` only if a new typed terminal exception needs direct
  classification coverage

- [ ] **Step 1: Write failing aggregation and terminal-state tests**

Add exact planning-loop tests:

- `test_reported_transient_failure_then_success_aggregates_both_wire_attempts`
- `test_reported_permanent_failure_is_charged_before_gateway_stop`
- `test_unknown_transport_cost_stops_before_retry`
- `test_unknown_after_reported_failure_retains_known_cost_lower_bound`
- `test_reported_failed_attempt_at_budget_cap_stops_before_retry`
- `test_unexpected_attempt_exception_logs_type_only_and_stops_cost_unknown`

Required assertions include:

```python
assert result.total_cost_usd == Decimal("0.003")
assert result.gateway_request_ids == ("gw-failed-1", "gw-success-2")
assert result.cost_complete is True
assert result.unknown_cost_attempt_count == 0
assert callback_attempts == [(1, 1, "gw-failed-1"), (1, 2, "gw-success-2")]
```

For unknown cost:

```python
assert gateway.attempts == 1
assert result.stop_reason == "PLANNING_GATEWAY_COST_UNKNOWN"
assert result.total_cost_usd == Decimal("0")
assert result.cost_complete is False
assert result.unknown_cost_attempt_count == 1
assert result.plan_hash is None
```

For the unexpected-exception test, raise `TypeError("SENTINEL-PAYLOAD-BUG")` from the injected
Gateway client. Assert exactly one `P9.95-USAGE-UNKNOWN` debug record contains
`error_type == "TypeError"`, that neither the record nor corrective text contains
`SENTINEL-PAYLOAD-BUG`, and that the terminal/cost assertions above still hold.

Run:

```bash
uv run pytest tests/unit/agent/test_planning_loop_runner.py -q
```

Expected RED: only successful usage is currently charged and unknown transport failure follows the
generic retry path.

- [ ] **Step 2: Add the result/progress completeness contract**

Add the fixed fields to `PlanningLoopResult` and `PlanningProgressEvent`. Update
`planning_corrective_text()` for `PLANNING_GATEWAY_COST_UNKNOWN` using content-free wording.

- [ ] **Step 3: Centralize per-attempt reported-usage recording**

Create `_record_reported_gateway_usage()` on `_PlanningIterationRunner`. Move request-ID append,
cost accumulation, provider capture, and callback invocation into it. Call it once from the
successful response path and once from a Gateway-exception path only when `gateway_usage` is not
`None`.

- [ ] **Step 4: Enforce cost completeness and the between-attempt budget gate**

Inside the retry operation:

1. Catch `Exception` at the attempt boundary. Read `gateway_usage` only from a typed `GatewayError`;
   an unexpected exception has no authoritative usage and therefore follows the same unknown-cost
   terminal path rather than being retried or treated as zero. Before raising the terminal error,
   emit the fixed content-free `P9.95-USAGE-UNKNOWN` record with the exception class name only.
2. If a typed Gateway exception carries usage, record that usage, then re-raise for normal classification unless the new
   aggregate is at/above the cap; in that case surface a terminal budget classification.
3. If it lacks usage, set incomplete state and surface a terminal typed failure so
   `RetryController` dispatches no later attempt.
4. After `RetryController.run`, map the terminal classification/state through
   `PlanningGatewayInvocationError` to the exact stop matrix.

Do not make unknown cost retryable merely because the underlying HTTP status is 503/429.

- [ ] **Step 5: Make iteration cost include the whole wire sequence**

Capture `_total_cost_usd` at invocation entry and return the delta after the wire sequence. Every
`IterationOutcome` for that settled turn uses this sequence cost, not only the final response cost.
Remove the old post-invocation append/add path to prevent double charging.

- [ ] **Step 6: Verify Task 2 and adjacent retry behavior**

Run:

```bash
uv run pytest tests/unit/agent/test_planning_loop_runner.py tests/unit/retry/test_policy.py -q
uv run ruff check src/optimus/agent/planning_loop.py tests/unit/agent/test_planning_loop_runner.py \
  tests/unit/retry/test_policy.py
git diff --check
```

Expected: all focused tests pass; the pre-existing 503 retry-policy tests remain green; no test
equates unknown cost with zero. Show the diff and wait for operator approval before the Task 2
commit.

---

### Task 3: Propagate Cost Completeness Through Runner, Usage Ledger, ACP, and Debug Evidence

**Deliverable:** The final agent result and content-free progress evidence distinguish a complete
reported total from a known lower bound, and reported failed attempts persist with stable IDs.

**Files:**
- Modify: `src/optimus/agent/models.py`
- Modify: `src/optimus/agent/runner.py`
- Modify: `src/optimus/acp/spec.py`
- Modify: `src/optimus/acp/debug_trace.py`
- Modify: `tests/unit/agent/test_runner.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`
- Modify: `tests/unit/acp/test_debug_trace.py`
- Modify: `tests/unit/usage/test_accounting.py` only if a regression assertion is needed

- [ ] **Step 1: Replace the FU-6-annotated placeholder coverage with failing closure tests**

Confirm the current number and locations of FU-6 annotations with
`rg -n "FU-6|billable failed|unknown transport cost" tests/unit/agent/test_runner.py` rather than
assuming a count. Update the relevant oversized/fitting flaky planning coverage and add:

- `test_fitting_context_records_reported_failed_and_successful_attempt_usage`
- `test_unknown_planning_cost_terminates_without_plan_or_usage_row`

The reported-failure test supplies normalized usage for both wire attempts and asserts:

```python
assert [entry.request_id for entry in accounting.provider_ledger.entries] == [
    "run-fit-retry:planning:1:1",
    "run-fit-retry:planning:1:2",
]
assert accounting.provider_ledger.gateway_request_ids(run_id="run-fit-retry") == {
    "gw-failed-1",
    "gw-success-2",
}
assert accounting.provider_ledger.total_cost_usd(run_id="run-fit-retry") == Decimal("0.003")
assert result.total_cost_usd == Decimal("0.003")
assert result.cost_complete is True
```

The unknown test asserts one wire attempt, zero persisted fabricated rows,
`cost_complete is False`, `unknown_cost_attempt_count == 1`, terminal status, no plan hash, and zero
mutation.

Run:

```bash
uv run pytest tests/unit/agent/test_runner.py -q
```

Expected RED until result propagation is implemented.

- [ ] **Step 2: Propagate completeness through `AgentRunResult`**

Add the two defaulted fields to the model and `_build_result()`. The multi-turn planning path copies
them for both success and terminal results. Existing single-call planning remains complete with zero
unknown attempts.

- [ ] **Step 3: Add the unknown-cost ACP terminal contract**

Add `PLANNING_GATEWAY_COST_UNKNOWN` to `_PLANNING_TERMINAL_STOP_REASONS`. Add protocol tests proving
the operator receives the sanitized corrective text, ACP returns `end_turn`, and no
`session/request_permission`, plan update, or mutation occurs.

- [ ] **Step 4: Extend content-free debug progress**

Log `cost_complete` and `unknown_cost_attempt_count` next to
`reported_aggregate_cost_usd`. Update debug-trace tests to assert the fields and scan the serialized
record for supplied prompt/response/credential sentinel strings.

- [ ] **Step 5: Verify Task 3**

Run:

```bash
uv run pytest tests/unit/agent/test_runner.py tests/unit/acp/test_spec_protocol.py \
  tests/unit/acp/test_debug_trace.py tests/unit/usage/test_accounting.py -q
uv run ruff check src/optimus/agent/models.py src/optimus/agent/runner.py \
  src/optimus/acp/spec.py src/optimus/acp/debug_trace.py tests/unit/agent/test_runner.py \
  tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_debug_trace.py
git diff --check
```

Expected: all focused tests and lint pass. Show the diff and wait for approval before committing the
Task 3 files.

---

### Task 4: Eliminate Read-Range Telemetry Misattribution

**Deliverable:** Non-alphabetical multi-file reads retain path/range/hash/byte-count association in
progress events, debug JSONL, and the downstream evidence summary.

**Files:**
- Modify: `src/optimus/agent/planning_loop.py`
- Modify: `tests/unit/agent/test_planning_loop_runner.py`
- Modify: `tests/unit/agent/test_planning_loop.py`
- Modify: `tests/unit/acp/test_debug_trace.py`
- Modify: `tests/unit/tools/test_run_plan987_acpx_live_evidence.py`

- [ ] **Step 1: Write the non-alphabetical multi-file regression first**

Use read execution order `zeta.py` then `alpha.py`, unequal byte lengths, and distinct hashes. Assert
the emitted event has this exact aligned projection:

```python
assert event.read_identities == (
    "alpha.py#bytes=2:9",
    "zeta.py#bytes=0:3",
)
assert event.source_sha256s == (alpha_sha, zeta_sha)
assert event.read_byte_counts == (7, 3)
```

Run the named test and confirm it fails because identities sort independently today:

```bash
uv run pytest tests/unit/agent/test_planning_loop_runner.py \
  -k "non_alphabetical_multi_file_read_telemetry" -q
```

- [ ] **Step 2: Add the cardinality invariant tests**

Add parameterized model tests that reject a mismatch in each parallel tuple and accept the final
zero-read progress event. Error text must name alignment with `read_request_count`.

- [ ] **Step 3: Implement the single-projection helper and validator**

Implement `planning_read_telemetry_fields()` exactly as fixed above. In the READ_MORE branch call it
once, unpack three tuples, and pass them to `PlanningProgressEvent`. Do not sort observation or tool
execution order.

- [ ] **Step 4: Prove downstream association, not only tuple ordering**

First assert the serialized debug event keeps each byte count aligned with the corresponding
identity and hash. Then feed that debug trace to `build_evidence_summary_from_run()` and assert each
`current_read_ranges` entry associates the expected path/range with its own hash; that downstream
schema does not carry byte counts. Do not change `tools/run_plan987_acpx_live_evidence.py` unless the
corrected producer exposes another independently demonstrated consumer defect.

- [ ] **Step 5: Verify Task 4**

Run:

```bash
uv run pytest tests/unit/agent/test_planning_loop.py \
  tests/unit/agent/test_planning_loop_runner.py tests/unit/acp/test_debug_trace.py \
  tests/unit/tools/test_run_plan987_acpx_live_evidence.py -q
uv run ruff check src/optimus/agent/planning_loop.py tests/unit/agent/test_planning_loop.py \
  tests/unit/agent/test_planning_loop_runner.py tests/unit/acp/test_debug_trace.py \
  tests/unit/tools/test_run_plan987_acpx_live_evidence.py
git diff --check
```

Expected: the multi-file mapping and cardinality tests pass. Show the diff and wait for approval
before the Task 4 commit.

---

### Task 5: Pin and Apply the Plan 9.88 Ceremony Ledger Digest

**Deliverable:** The post-capture verifier owns one deterministic ledger-digest contract and the
historical ceremony report records a transparent, mechanically verified correction.

**Files:**
- Modify: `tools/verify_plan987_acpx_evidence.py`
- Modify: `tests/unit/tools/test_verify_plan987_acpx_evidence.py`
- Modify: `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`

- [ ] **Step 1: Write fixed-vector and domain tests first**

Add exact tests:

- `test_ledger_digest_has_fixed_canonical_vector`
- `test_ledger_digest_preserves_record_and_list_order`
- `test_ledger_digest_rejects_empty_ledger`
- `test_plan988_extraction_keeps_all_eight_records_in_report_order`

The fixed-vector test asserts
`083d33790eef3a46cebde05f11206acfe01598a08bc3ab610d81c9fafe6bf2ec`.

Run:

```bash
uv run pytest tests/unit/tools/test_verify_plan987_acpx_evidence.py \
  -k "ledger_digest or extraction_keeps_all_eight" -q
```

Expected RED: `ledger_digest()` does not exist.

- [ ] **Step 2: Implement canonicalization exactly once**

Add `hashlib` and `Sequence` imports and implement the fixed helper. Use the existing
`_extract_plan988_records()` output directly; do not re-sort records by attempt or type.

- [ ] **Step 3: Add failing API/CLI pass and mismatch tests**

Add:

- `test_verify_report_accepts_matching_fu4b_ledger_digest`
- `test_verify_report_rejects_mismatched_fu4b_ledger_digest`
- `test_cli_digest_gate_composes_with_exhausted_status_and_fu4a_fu5`
- `test_cli_digest_gate_rejects_non_lowercase_or_non_sha256_value`

Mismatch text must include expected and actual digest but no report bodies.

- [ ] **Step 4: Wire the API and CLI without changing claim semantics**

Add `fu4b_ledger_digest` to `verify_report()` and
`--check-fu4b-ledger-digest` to `main()`. A digest-only invocation satisfies the verifier's
"at least one check" precondition. Existing FU-4A/FU-5 and accepted-open FU-4B behavior must remain
unchanged.

- [ ] **Step 5: Verify and commit the helper before changing historical evidence**

Run:

```bash
uv run pytest tests/unit/tools/test_verify_plan987_acpx_evidence.py -q
uv run ruff check tools/verify_plan987_acpx_evidence.py \
  tests/unit/tools/test_verify_plan987_acpx_evidence.py
git diff --check
git diff -- tools/verify_plan987_acpx_evidence.py \
  tests/unit/tools/test_verify_plan987_acpx_evidence.py
```

After explicit operator approval only:

```bash
git add tools/verify_plan987_acpx_evidence.py \
  tests/unit/tools/test_verify_plan987_acpx_evidence.py
git commit -m "Pin Plan 9.88 ledger digest"
git rev-parse HEAD
```

Record the full output as `LEDGER_HELPER_SHA`. This removes the circularity of asking the report to
cite a helper commit that does not exist yet.

- [ ] **Step 6: Recompute the historical ledger with the committed helper**

Run:

```bash
uv run python -c "from pathlib import Path; from tools.verify_plan987_acpx_evidence import _extract_plan988_records, ledger_digest; text=Path('reports/plan-9-87-model-replanning-refusal-acpx-evidence.md').read_text(encoding='utf-8'); print(ledger_digest(_extract_plan988_records(text)))"
```

Expected before report amendment:

```text
e265065147f505e56ed1ad8d60571f9d1f212fb8f8d192ec407121c0e7ac4195
```

If the output differs, stop and request plan review. Do not edit the expected value or report to
force a pass.

> **Implementation Amendment (2026-07-15, reviewer-agent + operator approved):** Steps 7-8 originally
> specified a single durable command combining `--require fu4a --require fu5` with the new digest/status
> checks. Independent reviewer verification found `--require fu4a` and `--require fu5` already fail with
> `implementation drift after <SHA>` against the real report — `CLAIM_WATCHED_PATHS` for both claims
> covers the entire `src/optimus` tree, and `git merge-base --is-ancestor` confirmed the report's pinned
> `fu4a` implementation SHA (`4bf20fffd9b067afa4db34d5ae021aca665f3acb`, committed 2026-07-13) predates
> the Plan 9.95 branch-cut point (`7554c85`) with 34 files/1135 lines already drifted from unrelated
> prior work (Plan 9.9 and others) before Plan 9.95 Task 1 ever ran. This is pre-existing evidence rot,
> not something this plan's tasks caused. Re-establishing FU-4A/FU-5 evidence freshness would require
> re-capturing live evidence, which is out of scope for Plan 9.95 (Global Constraint 1: exactly three
> follow-ups; the Explicit Exceptions section authorizes only the digest amendment to this report) and
> in tension with Global Constraint 16 (no paid failure fishing). Steps 7-8 below are amended to prove
> only the digest/status gate Task 5 actually owns, and to transparently disclose the fu4a/fu5 drift
> rather than silently drop it. Tracked separately: add a tracked-not-yet-scheduled roadmap backlog note
> for re-pinning/re-capturing FU-4A/FU-5 evidence (not a Plan 9.95 deliverable).

- [ ] **Step 7: Amend the ceremony report transparently**

Retain the original `9122...` value labeled as the unpinned contemporaneous value. Add the pinned
digest, the exact canonicalization rule, the eight-record domain statement, `LEDGER_HELPER_SHA`,
and this durable command:

```bash
uv run python tools/verify_plan987_acpx_evidence.py \
  --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md \
  --check-fu4b-ledger-status exhausted \
  --check-fu4b-ledger-digest e265065147f505e56ed1ad8d60571f9d1f212fb8f8d192ec407121c0e7ac4195 \
  --max-completed-replan-attempts 3
```

Do not change the accepted-open disposition or make `--require fu4b` succeed. Also add one transparent
disclosure statement (per the Implementation Amendment above): `--require fu4a` and `--require fu5`
independently fail today with `implementation drift after <SHA>` because unrelated `src/optimus`
changes landed after their pinned implementation SHAs, predating Plan 9.95; re-establishing that
freshness is out of scope for `P9.88-FU-2` and is tracked separately, not silently dropped.

- [ ] **Step 8: Verify and commit the report amendment**

Run:

```bash
uv run python tools/verify_plan987_acpx_evidence.py \
  --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md \
  --check-fu4b-ledger-status exhausted \
  --check-fu4b-ledger-digest e265065147f505e56ed1ad8d60571f9d1f212fb8f8d192ec407121c0e7ac4195 \
  --max-completed-replan-attempts 3
uv run python tools/verify_plan987_acpx_evidence.py \
  --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md \
  --require fu4b
```

Expected: unit suite PASS; the digest/status gate above PASSES; the final command FAILS with `fu4b
claim missing`. Record both the expected pass and expected non-qualifying failure. Then:

```bash
git diff --check
git diff -- docs/superpowers/plans/2026-07-13-plan-9-88-fu4b-evidence-remediation-and-plan-9-87-closure.md
```

Expected: diff check is clean and the frozen Plan 9.88 plan has no diff. Show the report-only diff
and wait for approval. After explicit operator approval only:

```bash
git add reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
git commit -m "Record pinned Plan 9.88 ledger digest"
```

---

### Task 6: Prove the Failure Paths Through the Real Urllib Transport

**Deliverable:** A local HTTP integration demonstrates that reported 503 usage is charged before a
successful retry and a 503 without usage stops after one request with incomplete cost.

**Files:**
- Create: `tests/integration/gateway/test_failed_usage_transport_flow.py`
- Modify only if an integration-discovered defect requires it: Task 1-3 product files and their tests

- [ ] **Step 1: Write the reported-failure transport integration**

Start a local `ThreadingHTTPServer` on loopback. Its first `/v1/responses` response is HTTP 503 with
an error object and fully normalized `gateway_usage` costing `0.001`; its second response is HTTP
200 with a final-plan response and fully normalized usage costing `0.002`.

Use the real `GatewayClient` and default `UrllibGatewayTransport`. Assert two HTTP requests, one
settled turn, one retry, total `0.003`, two Gateway IDs, two persisted provider-usage rows, complete
cost, and an awaiting-approval result. The server fixture may hold only deterministic test data and
must shut down in `finally`/fixture teardown.

- [ ] **Step 2: Write the unknown-cost transport integration**

Return HTTP 503 with `{"error":"temporary outage"}` and no usage. Assert exactly one HTTP request,
`PLANNING_GATEWAY_COST_UNKNOWN`, incomplete cost, one unknown attempt, no provider-usage rows, no
plan hash, no permission, and zero mutation.

- [ ] **Step 3: Run the integration and focused regression bundle**

Run:

```bash
uv run pytest tests/integration/gateway/test_failed_usage_transport_flow.py \
  tests/integration/retry/test_gateway_retry_flow.py \
  tests/unit/gateway tests/unit/agent/test_planning_loop_runner.py \
  tests/unit/agent/test_runner.py tests/unit/acp/test_spec_protocol.py \
  tests/unit/acp/test_debug_trace.py tests/unit/tools/test_verify_plan987_acpx_evidence.py \
  tests/unit/tools/test_run_plan987_acpx_live_evidence.py -q
```

Expected: all tests pass. The local HTTP integration is not marked `requires_gateway` and makes no
real-provider claim.

- [ ] **Step 4: Verify Task 6 quality and isolation**

Run:

```bash
uv run ruff check src/optimus tests/integration/gateway/test_failed_usage_transport_flow.py \
  tests/unit/gateway tests/unit/agent tests/unit/acp tests/unit/tools \
  tools/verify_plan987_acpx_evidence.py
git diff --check
```

Expected: Ruff and diff checks pass. Show the integration output and diff; wait for approval before
committing the Task 6 test and any reviewed integration-driven correction.

---

### Task 7: Produce the Evidence Artifact and Close Only Plan 9.95

**Deliverable:** One sanitized report maps every Plan 9.95 claim to executable evidence; living docs
close the three owned follow-ups while Plans 9.96 and 9.97 remain tracked and unscheduled.

**Files:**
- Create: `reports/plan-9-95-usage-telemetry-evidence.md`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Modify: this plan's checkboxes/status

- [ ] **Step 1: Create the evidence report skeleton before final gates**

First run:

```bash
git rev-parse HEAD
git status --short
```

Record the full HEAD as `PLAN995_IMPLEMENTATION_SHA`. It is the reviewed Task 1-6 implementation
identity before the closure report/living-doc commit, avoiding a self-referential SHA.

The report must contain:

- `PLAN995_IMPLEMENTATION_SHA` and a clean watched-path statement;
- claim-to-test-node table for reported failed usage, unknown cost, budget cap, stable IDs,
  read-range association, and ledger digest;
- reported-vs-unknown terminal matrix with exact observed outputs;
- the local HTTP integration command and result;
- fixed-vector and ceremony digest values plus durable verifier command;
- expected `--require fu4b` failure disclosure;
- the pre-existing `--require fu4a`/`--require fu5` implementation-drift disclosure (Task 5 Steps 7-8
  Implementation Amendment) — out of scope for Plan 9.95, tracked separately;
- explicit statement that no real provider failure was provoked and no live-provider claim is made;
- redaction scan and no-secret statement;
- final Ruff, full pytest, coverage, and diff outputs.

Do not paste prompts, model responses, source bodies, provider error bodies, keys, or authorization
headers.

- [ ] **Step 2: Run focused closure gates**

Run:

```bash
uv run pytest tests/unit/gateway tests/unit/agent/test_planning_loop.py \
  tests/unit/agent/test_planning_loop_runner.py tests/unit/agent/test_runner.py \
  tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_debug_trace.py \
  tests/unit/usage tests/unit/retry/test_policy.py tests/unit/tools/test_verify_plan987_acpx_evidence.py \
  tests/unit/tools/test_run_plan987_acpx_live_evidence.py \
  tests/integration/gateway/test_failed_usage_transport_flow.py \
  tests/integration/retry/test_gateway_retry_flow.py -q
uv run python tools/verify_plan987_acpx_evidence.py \
  --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md \
  --check-fu4b-ledger-status exhausted \
  --check-fu4b-ledger-digest e265065147f505e56ed1ad8d60571f9d1f212fb8f8d192ec407121c0e7ac4195 \
  --max-completed-replan-attempts 3
```

Expected: all focused tests and the digest/status verifier gate pass. Per the Task 5 Steps 7-8
Implementation Amendment, this closure gate does not include `--require fu4a --require fu5` — that
combination independently fails on pre-existing, out-of-scope implementation drift and is not part of
what Plan 9.95 closes.

- [ ] **Step 3: Run full default tests and aggregate coverage**

Run:

```bash
uv run pytest -q
uv run pytest --cov=optimus --cov=optimus_gateway --cov-branch --cov-report=term-missing \
  --cov-fail-under=80 -q
```

Expected: the repository's default marker exclusions apply; all selected tests pass and aggregate
production coverage is at least 80%. Record exact counts and coverage in the report.

- [ ] **Step 4: Run final static and secret-safe checks**

Run:

```bash
uv run ruff check .
git diff --check
rg -n "(sk-[A-Za-z0-9]|Bearer [A-Za-z0-9]|OPTIMUS_API_KEY=|ANTHROPIC_API_KEY=|OPENAI_API_KEY=)" \
  reports/plan-9-95-usage-telemetry-evidence.md \
  reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
git status --short
```

Expected: Ruff/diff clean; secret scan has no secret-value matches; status contains only reviewed
Plan 9.95 files plus separately disclosed operator-owned noise.

- [ ] **Step 5: Update living documentation without closing later lanes**

Update README and roadmap to say Plan 9.95 implemented only after Steps 2-4 pass. Name the final
implementation SHA and `reports/plan-9-95-usage-telemetry-evidence.md`. Remove
`P9.85-FU-6`, `P9.88-FU-2`, and `P9.88-FU-3` from open custody. Preserve Plan 9.96 and Plan 9.97 as
tracked-not-yet-scheduled and preserve the exact Plan 9.97 isolation sentence. Do not create plans
for them.

- [ ] **Step 6: Run custody and frozen-history assertions**

Run:

```bash
rg -n "P9\.85-FU-6|P9\.88-FU-2|P9\.88-FU-3|P9\.85-FU-7|P9\.9-FU-1|P9\.87-FU-1" \
  README.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md
rg -n "must not absorb or be absorbed by Plan 11" \
  docs/superpowers/plans/2026-07-01-phase-1-roadmap.md
git diff --quiet -- \
  docs/superpowers/plans/2026-07-13-plan-9-88-fu4b-evidence-remediation-and-plan-9-87-closure.md
```

Expected: the three Plan 9.95 FUs are closed with evidence; the other three have exactly their new
owners; the isolation sentence exists. The final command exits 0 because the frozen Plan 9.88 plan
was not edited.

- [ ] **Step 7: Request final sign-off and commit only after approval**

Show:

```bash
git diff --stat
git diff --check
git status --short
```

After reviewer-agent and operator approve the evidence and exact diff, stage only reviewed Plan
9.95 files and commit. Do not include IDE files, local agent configuration, lockfile drift unrelated
to this plan, or Plans 9.96/9.97 implementation artifacts.

## Definition of Done

- [ ] Reviewer-agent and operator approved this implementation plan before code work began.
- [ ] Every valid Gateway-reported failed-attempt usage envelope is aggregated exactly once.
- [ ] Normalized reported failed-attempt usage persists with stable settled-turn/wire-attempt IDs.
- [ ] An attempt without valid usage stops before another retry with
  `PLANNING_GATEWAY_COST_UNKNOWN`, incomplete cost, no plan hash, no permission, and zero mutation.
- [ ] Reported failed-attempt cost participates in the budget cap before another wire request.
- [ ] `total_cost_usd` is never presented as complete when any wire-attempt cost is unknown.
- [ ] Non-alphabetical multi-file telemetry preserves identity/hash/byte-count association through
  `build_evidence_summary_from_run()`.
- [ ] `ledger_digest()` has the fixed canonicalization, fixed vector, empty-ledger rejection, and
  report-order domain.
- [ ] The historical `9122...` value is retained as unpinned and the mechanically recomputed pinned
  digest is recorded with a durable command.
- [ ] FU-4B remains accepted-open and `--require fu4b` still fails.
- [ ] The real urllib/local-HTTP integration passes without being mislabeled as a real Gateway tier.
- [ ] `reports/plan-9-95-usage-telemetry-evidence.md` maps each DoD claim to named evidence.
- [ ] Plans 9.96 and 9.97 remain tracked-not-yet-scheduled with no implementation-plan files.
- [ ] Plan 9.97 still says it **must not absorb or be absorbed by Plan 11**.
- [ ] Full default tests pass; aggregate production coverage is at least 80%; `uv run ruff check .`
  and `git diff --check` are clean.
- [ ] Final status contains no unintended `.idea`, `.claude`, `.cursor`, `.superpowers`, secret,
  environment, or unrelated lockfile changes in the reviewed commit.

## Implementation Handoff After Approval

1. Start a fresh implementation branch from the latest `origin/main`; do not execute this planning
   branch as a feature branch if it has drifted behind main.
2. Re-open this exact plan file from disk and use `superpowers:executing-plans` plus
   `superpowers:test-driven-development`.
3. Execute one task at a time. At each boundary, show the focused test output, Ruff output, exact
   diff, and `git status`; wait for explicit operator approval before committing.
4. Stop on any conflict between this plan, HLD, LLD, Test Strategy, or current Gateway wire
   behavior. Record the conflict and request a reviewed plan amendment; do not improvise.
5. Do not schedule or design Plans 9.96 or 9.97 while implementing Plan 9.95.

## Plan Self-Review Record

- **Scope fidelity:** All six former umbrella follow-ups are accounted for; only the approved three
  are implemented here.
- **Accounting fidelity:** Reported usage is authoritative, unknown cost is not zero, and budget
  checks occur before another wire attempt.
- **Retry fidelity:** Known transient failures retain the normal retry classifier; unknown-cost
  attempts are terminal because the budget can no longer be proven.
- **Telemetry fidelity:** The fix addresses misattribution across the complete tuple association,
  not merely alphabetical ordering.
- **Evidence fidelity:** Unit tests prove branches; the integration uses the actual urllib transport;
  no fake or paid failure fishing is called live evidence.
- **Digest fidelity:** Domain, record order, key order, list order, Unicode, separators, LF policy,
  empty input, fixed vector, and historical correction are all explicit.
- **Custody fidelity:** Plan 9.96 begins with its security review; Plan 9.97 retains its Plan 11
  isolation; neither gets an implementation plan on this branch.
- **Placeholder scan:** No `TBD`, `TODO`, “similar to,” unspecified canonicalization, or unspecified
  error-handling step remains.
