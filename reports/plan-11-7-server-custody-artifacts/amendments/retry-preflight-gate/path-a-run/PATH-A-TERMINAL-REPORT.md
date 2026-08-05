# Plan 11.7 Retry Preflight — Path A Terminal Stop

**Disposition:** fail-closed terminal stop (not a defect)
**Operator authorization:** Path A only (2026-08-05)
**HEAD:** f8c51f217ea4c281dee50a4dd47d0dfc4b35160d

## What ran

Real origin-a-prompt-retry CLI against current sealed ledger state with a dead relay control
endpoint. No Redis/Gateway wiring, no Zed reinstall, no settings mutation, no correlation ordinal 4.

## Result

| Field | Value |
|---|---|
| CLI reason_code | invalid_probe_retry_control_channel_failure |
| CLI field_path | control_channel |
| Offline outcome | unavailable_proof |
| settings_mutated | false |
| zed_launched | false |
| reservation (prompt 3) | not created |
| origin-a-4 | not allocated |

## Why this is terminal (not a defect)

1. The live origin-a-3 Zed/relay/ACP session from the Option B seal is dead.
2. Correlation budget is exhausted (
ext_correlation_ordinal=4); a fourth correlation launch remains unauthorized.
3. The retry gate correctly fail-closed at cquire_live_session_proof when the control channel could not answer.
4. Offline erify_retry_preflight_offline independently classified unavailable_proof.

Accepted same-session retry evidence was not produced and is not claimed.

## Explicit non-claims

- production server-side custody feasibility
- live LiveSessionProof from real Zed
- authorization to expand correlation budget
