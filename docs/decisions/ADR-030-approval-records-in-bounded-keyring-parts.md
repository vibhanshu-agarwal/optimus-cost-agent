# ADR-030: Approval records larger than one Windows credential blob are stored as bounded parts

Status: Proposed — mechanism recommended by Codex and drafted by Claude for [#433](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/433); the operator's decision is recorded here before merge.

## Context

The archived [Plan 9.96 security design](../superpowers/specs/archive/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md) (§ approval record size) caps a serialized launch-approval record at 1,800 UTF-8 bytes. It says that budget "stays below the approximately 2.5 KB Windows Credential Manager" limit, and that an oversized record is rejected rather than chunked.

The sizing assumption is wrong. The Windows keyring backend (keyring 25.7.0, `WinVaultKeyring`) writes each value as UTF-16-LE, and Windows caps a credential blob at 2,560 bytes (`CRED_MAX_CREDENTIAL_BLOB_SIZE`). Records are ASCII JSON, so a record of 1,281–1,800 characters passed Optimus's own check and then failed in `CredWrite` with winerror 1783. The error was untyped and nothing was written. On 2026-10-28 this blocked two durable approvals for #397's scripted-provider workspace.

A probe of the real backend, under an isolated throwaway service, stored 1,280 characters and refused 1,281 with winerror 1783 (see [the validation record](../sources/p433-approval-store/validation-record.md)).

## Decision

- **Kept:** the 1,800-byte UTF-8 policy limit, and the typed `RECORD_TOO_LARGE` rejection of a record over it. The canonical record JSON and its record HMAC are unchanged.
- **Corrected:** every stored keyring value is checked against 2,560 UTF-16-LE bytes, on every platform.
- **Permitted:** a record over one value is stored as at most two immutable, generation-specific parts, plus an HMAC-authenticated, versioned manifest that is published last at the record's existing key. A record that fits one value is stored as a single entry, as before. Missing, mixed-generation, oversized, tampered or inconsistent parts fail closed.
- **Locking:** every operation on the approvals keyring service holds one service-wide lock file under the approval runtime root. This replaces the per-workspace locks. `WinVaultKeyring.set_password` re-saves whatever entry occupies the shared service slot. Without serialization, a writer could therefore resurrect an entry that another process had just consumed or revoked.
- **Failures:** keyring backend failures become typed `ApprovalError`s that carry no backend message, record, value or key material. A failed publication reports whether the previous approval was confirmed in place, removed, or left in an unknown state.

## Options considered

1. **Lower the policy limit to about 1,280 characters.** Rejected: launches that the policy allows, such as #397's stub launch, could never be approved.
2. **Compress the record.** Rejected: it cannot guarantee that every record within the 1,800-byte policy fits. A policy-sized record with high-entropy content still exceeds one value after compression and base64.
3. **Bounded multipart storage.** Chosen.

## Consequences and limits

- Approvals the policy allows can now be written on Windows.
- Revocation of a migrated record uses the legacy source recorded in its authenticated manifest or record. Revoking an entry that cannot be authenticated refuses (`REVOCATION_INCOMPLETE`) rather than exposing a legacy fallback.
- Residual, owned by #433: if a migrated entry loses authentication through corruption, approving again and then revoking can leave its legacy source promotable.
- Protection against the slot race assumes every process that writes the approvals service uses this locking protocol.
- Orphan parts left by a crash between part writes and publication are unreferenced and inert. They are not swept.

## Decider and provenance

- Mechanism: recommended by Codex (CLI review, round 76 follow-up 3 and round 78, posted verbatim on #433), designed and implemented by Claude.
- Operator decision: _to be recorded verbatim before merge._
- The frozen Plan 9.96 design is not edited; this record supersedes only its record-size and no-chunking statements.
