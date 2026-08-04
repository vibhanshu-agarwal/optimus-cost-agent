# Plan 11.7 Retry Preflight Gate and Live Session Proof Design

**Status:** Draft for independent reviewer and operator approval.

**Purpose:** Close the Plan 11.7 origin-A retry-custody gap by defining how the prompt-only retry
path obtains a current, evidence-backed proof that the exact Zed process, relay connection, and ACP
session from `origin-a-3` are still live before the retry preflight gate can authorize one prompt
ordinal.

**Decision boundary:** This design covers the retry gate and its evidence boundary only. It does not
change the ACP server, session-resume semantics, workspace-reference resolver, Gateway contract,
correlation budget, fixture identity, or Zed behavior. It authorizes no fourth correlation launch,
no settings mutation, and no production implementation under `src/optimus` or
`src/optimus_gateway`.

## Authority and custody

The new open-work item is recorded first in the consolidated pool as
[`P11-FU-11`](../plans/2026-07-23-consolidated-deferred-followups-backlog.md#p11-fu-11-plan-117-retry-preflight-and-live-session-proof).
The executable amendment is
[`2026-08-04-plan-11-7-retry-preflight-gate-amendment.md`](../plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md).

The following documents remain immutable inputs and must be hash-pinned by the amendment before
execution:

- frozen Plan 11.7: `docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md`;
- the approved server-side custody feasibility design and amendment from 2026-08-02;
- the approved origin-A fixture-v2 design and amendment from 2026-08-02; and
- the existing Plan 11.7 reviewer checkpoint log and sealed evidence artifacts.

The exact 2026-08-02 document digests are not copied from memory into this draft. Task 0 of the
amendment must compute and record their LF-byte SHA-256 values from the execution commit, then stop
if the expected parent files are absent or differ. No frozen or parent document may be edited to
make this design fit.

## Confirmed gap

The current retry-gate implementation has three separate gaps:

1. `assert_prompt_retry_preflight` at the reported runner location near line 1457 is complete but
   has no caller.
2. The `origin-a-prompt-retry` branch near lines 1639-1659 validates the fixture hash and prints a
   hardcoded JSON result. It does not load or recompute the stage ledger, call the preflight
   function, or check `live_session_proof`.
3. No runner or relay function constructs `live_session_proof` from real Zed/relay process state.

The source-level line references were verified against the public `origin/main` execution tree at
`c17af17`. The amendment's first task must still revalidate them against the exact approved
execution commit before implementation or live evidence.

## Existing gate contract and deliberate supersession

On `origin/main` at `c17af17`, `tools/run_plan117_custody_feasibility.py:1457` exposes this current
runner API and keeps it in the module's `__all__` export at line 1696:

```python
def assert_prompt_retry_preflight(
    *,
    run_attempt_id: str,
    ledger: StageLedger,
    prompt_fixture: Path,
    live_session_proof: Mapping[str, Any] | None,
) -> None:
```

This amendment deliberately supersedes that signature while preserving the function's module and
export identity. The function remains in `tools/run_plan117_custody_feasibility.py`, remains pure
and exception-based for invalid input, and remains listed in that module's `__all__`. Task 1 adds
`LiveSessionProof` and the new `RetryPreflightResult` type to
`tools/plan117_custody_contract.py`; the runner imports those types but does not relocate the public
gate. The replacement contract is:

```python
def assert_prompt_retry_preflight(
    *,
    run_attempt_id: str,
    ledger: StageLedger,
    prompt_fixture: Path,
    target_sha256: str,
    live_session_proof: LiveSessionProof | None,
) -> RetryPreflightResult:
```

`target_sha256` is computed by the existing exact target-resolution preflight before this call; the
gate compares it to the approved target identity and never resolves a path itself. Successful
validation returns the new immutable result; failed validation continues to raise the existing
`CustodyRunnerError` reason codes. Existing unit fixtures that pass a plain mapping must be replaced
with typed proof fixtures, and the `None` rejection test remains mandatory.

## Design decisions

### 1. Proof is acquired from the live relay, not reconstructed from a file

`live_session_proof` is a current snapshot returned by a private control request to the relay that
owns the active ACP byte connection. A JSON file written during launch is only a locator and
identity record; it is never sufficient to prove that a process or connection is still alive.

The proof uses the existing custody contract's immutable evidence-reference shape and adds the
following normalized fields:

```python
@dataclass(frozen=True)
class LiveSessionProof:
    run_attempt_id: str
    zed_pid: int
    zed_process_start_time_utc: str
    connection_id: str
    acp_session_id: str
    zed_alive: bool
    relay_alive: bool
    acp_session_observed: bool
    captured_utc: str
    evidence: tuple[EvidenceReference, ...]
    proof_sha256: str
```

The proof is eligible only when all of these conditions hold:

- `run_attempt_id` is `origin-a-3` and matches the stage-ledger reservation;
- `zed_pid` is the PID held by the active relay-owned process, and its process-start identity
  still matches the launch record so PID reuse cannot satisfy the proof;
- `connection_id` is the opaque ID allocated by the relay for this exact ACP connection and is
  still attached to that relay connection;
- `acp_session_id` is the exact ID observed in the real `session/new` response for this connection,
  not a CLI argument, timestamp, workspace name, or operator-supplied value;
- the Zed process has not exited, the relay control request succeeds, and the ACP connection has
  not entered EOF or a terminal disconnect state; and
- the evidence references bind the proof to the captured relay/index/debug records without
  exposing credentials or raw private environment data.

The proof must fail closed if process creation time is unavailable, the PID can no longer be
verified, the relay cannot attest the connection, the ACP session was never observed, or any
identity field disagrees. A process-list lookup, PID-only match, workspace match, or timestamp
proximity is not an acceptable fallback.

### 2. The relay gets a private control plane separate from ACP bytes

The existing relay remains byte-opaque. The proof query and retry command use a same-run private
local control endpoint owned by that relay; they never inject control messages into the ACP byte
stream and never turn the control response into ACP-conformance evidence.

The control endpoint is a Windows named-pipe/AF_PIPE endpoint restricted to the current operator and
bound to one run attempt. Its descriptor is stored under the already-approved private custody root
and contains only a locator, `run_attempt_id`, endpoint identity, `connection_id`, and a digest of
the descriptor. The descriptor is not itself proof. The live relay must answer the proof request
from its process handle, active connection state, and previously observed `session/new` response.

The control surface has two bounded operations:

```text
get_live_session_proof(run_attempt_id, descriptor_digest)
send_existing_session_prompt(run_attempt_id, connection_id, acp_session_id, prompt_fixture)
```

The second operation is callable only after the first response has passed the pure preflight
contract and the runner has atomically reserved prompt ordinal 3. It sends `session/prompt` over
the already-open ACP connection; it cannot launch Zed, issue `session/new`, change settings, or
allocate a correlation ordinal.

The control endpoint is closed and its descriptor becomes terminal after the prompt result is
sealed, after a proof failure that makes retry unavailable, or after any terminal process/relay
failure. A stale endpoint must not be reusable by a later run.

### 3. The CLI order is ledger, identity, proof, gate, reservation, prompt

`origin-a-prompt-retry` must execute this order:

1. Load the append-only stage ledger and derive the next prompt ordinal. Do not accept a caller-
   supplied budget or infer state from directory names.
2. Validate the exact fixture and target hashes already required by the origin-A amendment.
3. Require a successful `origin-a-3` correlation stage and an evidence-backed transient prompt
   failure at prompt ordinal 2.
4. Load the private relay descriptor and query the live relay for `LiveSessionProof`.
5. Pass the ledger, proof, fixture identity, and current run identity to
   `assert_prompt_retry_preflight`.
6. If and only if the pure gate succeeds, atomically reserve prompt ordinal 3 and send the existing
   ACP `session/prompt` through the relay.
7. Append the prompt-stage outcome and proof references; never rewrite the reservation or prior
   stage records.

Any failure in steps 1-5 emits the structured fail-closed reason and performs no reservation, Zed
launch, settings mutation, ACP request, or correlation-budget allocation. A failure after the
ordinal-3 reservation remains consumed and is classified from evidence; it is never reclaimed.

### 4. The pure preflight gate remains the policy authority

`assert_prompt_retry_preflight` remains side-effect free. The caller supplies the already-normalized
ledger and the newly acquired proof; the function decides eligibility and returns a structured
result or stable reason code. It must not inspect the process table, open the relay, read mutable
settings, or synthesize missing proof fields.

The minimum positive predicate is:

```text
correlation(origin-a-3) == succeeded
prompt(origin-a-3, ordinal=2) == evidence-backed transient failure
next_prompt_ordinal == 3
live_session_proof.run_attempt_id == origin-a-3
live_session_proof.zed_alive == true
live_session_proof.relay_alive == true
live_session_proof.acp_session_observed == true
live_session_proof.connection_id == launch.connection_id
live_session_proof.acp_session_id == launch.acp_session_id
live_session_proof.zed_process_identity == launch.zed_process_identity
```

The gate rejects missing or stale proof, mismatched IDs, prompt ordinal gaps, permanent failures,
any correlation ordinal other than 3, a prior retry, a changed fixture/target, a second physical
run, or a request that would require `session/new`.

### 5. Evidence remains independently falsifiable

The proof artifact records safe facts and hashes only. The verifier must be able to recompute the
proof digest and cross-check:

- the Zed launch/process record and process-start identity;
- the relay connection record and opaque `connection_id`;
- the exact ACP `session/new` response containing `acp_session_id`;
- the relay index and byte streams; and
- Optimus's independently authored `.optimus/debug-acp.ndjson`.

The control-plane response is corroborating custody evidence, not a replacement for the ACP relay
transcript or debug record. The real Zed/relay run remains mandatory for the live evidence tier;
unit fakes may cover pure contracts only.

## Failure precedence and stable reasons

The existing origin-A precedence remains unchanged. This design adds only retry-specific reasons:

| Reason | Meaning |
|---|---|
| `invalid_probe_retry_ledger_unavailable` | The stage ledger is missing, malformed, forked, or inconsistent with immutable records |
| `invalid_probe_retry_proof_unavailable` | The live relay cannot answer the proof request or the endpoint is stale |
| `invalid_probe_retry_process_identity_mismatch` | PID, process-start identity, or Zed liveness does not match the launch |
| `invalid_probe_retry_connection_identity_mismatch` | The relay connection is absent, closed, or not the reserved connection |
| `invalid_probe_retry_acp_session_identity_mismatch` | The session ID was not observed from the exact prior `session/new` response |
| `blocked_probe_same_session_prompt_retry_unavailable` | The prior prompt was transient but exact same-session proof is unavailable |
| `invalid_probe_retry_control_channel_failure` | The private relay control path failed before prompt transmission |
| `invalid_probe_retry_second_prompt_failure` | The single allowed prompt-only retry also failed and no further retry is allowed |

Identity, custody, restoration, relay, transcript, and Zed-crash precedence remains higher than
retry eligibility. A missing proof never falls back to a new Zed launch.

## Verification requirements

The paired amendment must provide:

- unit tests for canonical proof serialization, proof digest binding, missing-field rejection, PID
  reuse rejection, run/connection/session mismatches, stale endpoint rejection, and pure-gate
  behavior;
- relay-control tests for proof requests, pipe failure, connection closure, EOF, request ordering,
  capability scoping, and no ACP-byte mutation;
- runner tests proving the CLI order and proving the hardcoded JSON path is gone;
- verifier tests for every proof field, evidence hash, control-descriptor digest, and precedence
  reason; and
- one real-Zed/real-relay evidence run showing successful correlation, transient prompt failure,
  live proof, one same-session prompt retry, no new launch, no settings rewrite, exact session
  identity, and hard Gateway usage/cost evidence.

The implementation may add or refine private custody-tool modules, but it must not modify
`src/optimus`, `src/optimus_gateway`, the frozen Plan 11.7 plan, either 2026-08-02 parent
amendment, or sealed prior artifacts.

## Rejected alternatives

- **Trust a persisted `live_session_proof` JSON file:** rejected because it cannot prove current
  process or connection liveness and permits stale/PID-reuse evidence.
- **Accept PID, workspace, or timestamp matching alone:** rejected because none is a unique
  session identity and each can bind a different process or conversation.
- **Pass `acp_session_id` on the retry CLI:** rejected because caller input cannot prove that the
  ID belongs to the still-live connection; the relay must return the observed value.
- **Relaunch Zed when proof is unavailable:** rejected because it consumes a new correlation run and
  violates the one-launch/no-fourth-correlation budget.
- **Send a fresh `session/new` through the relay:** rejected because the allowed operation is a
  prompt-only retry in the exact existing ACP session.
- **Make the ACP server own the proof:** rejected because this is custody evidence for the external
  Zed/relay process and would expand production scope beyond the amendment.

## Acceptance criteria

The paired amendment is ready for independent approval only when it:

1. links this spec and the `P11-FU-11` pool entry, while pinning the frozen plan and both 2026-08-02
   parent documents by exact on-disk digests;
2. names the exact runner symbols and current CLI behavior being replaced;
3. defines a live relay proof with Zed PID/process identity, relay connection ID, ACP session ID,
   current liveness, and independently hashed evidence;
4. defines a same-run private control path without changing ACP byte semantics;
5. wires the CLI order through ledger load, proof acquisition, pure preflight, immutable prompt
   reservation, and existing-session prompt transmission;
6. rejects stale, substituted, mismatched, missing, or unverifiable proof before any retry action;
7. preserves the no-relaunch, no-settings-mutation, no-fourth-correlation, Gateway-only, and
   append-only custody invariants; and
8. maps each claim to unit, integration, verifier, and real-Zed/relay evidence with a final docs
   freshness audit.

Approval of this design or its amendment never authorizes production server-side custody or a new
ACP session-resume implementation.
