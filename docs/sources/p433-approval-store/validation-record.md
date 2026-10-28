# #433 approval-store validation record

Sanitized evidence for [#433](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/433) and
[ADR-030](../../decisions/ADR-030-approval-records-in-bounded-keyring-parts.md). It holds no credential, setting value,
record content or HMAC. Raw logs are workstation provenance only, under the operator's handoff folder
`sandbox-review-kit/p433-approval-store/`; their SHA-256 values are listed so a copy can be checked.

## Claim

On Windows, a launch-approval record over one credential blob (2,560 UTF-16-LE bytes, about 1,280 ASCII characters) is
stored as at most two authenticated, generation-specific parts behind a manifest published last. It round-trips through
the real Credential Manager. Missing, mixed, oversized, tampered or inconsistent parts fail closed. Every
approvals-service operation holds one service-wide lock. Keyring backend failures are typed refusals that carry no
backend message or stored value.

## Measured limit

| Probe | Result | Log SHA-256 |
|---|---|---|
| Real `WinVaultKeyring` (keyring 25.7.0), isolated throwaway service, random hex values | 1,279 and 1,280 chars stored and read back; 1,281 and 1,800 chars refused by `CredWrite` with winerror 1783; every probe entry removed | `b086ea41373a08e7df504be6af370771bc3365f87eb9c99a9b063ce5c7acaae2` (script `cc539d989fe84ef49d731f5f16f9ebdef5293f7156003b25d8d9048ecedb6701`) |
| `msvcrt.locking` contention between two handles | errno 13 (`EACCES`), the errno the lock retries on Windows | `80b32cda4696ead1ec60fa79800f92610abbbda1ac5f6ff571e53ddecc75f7cb` |

## Runs

| Run | Head and tree | Command | Result | Log SHA-256 |
|---|---|---|---|---|
| Real Credential Manager round trip | `7bc6aa2`, clean | `pytest tests/integration/acp/test_launch_approvals_windows_keyring.py -m requires_os_keyring_write` (Windows 11, Python 3.14, isolated random service, explicit HMAC key) | 5 passed (run `20261028T081951-15828-e1695a`); then `CredEnumerate('*optimus-p433-*')` found no leftover entry | `e6bcca5924c55dba166f14d603e98a38e847d8007d9dd0e622e567f75791654e` |
| Targeted unit run, provisional | pre-commit working tree of the same change, before the logging-manifest update and the `DELETION_FAILED` detail | `pytest tests/unit/acp tests/unit/mcp tests/unit/tools tests/unit/evidence/test_naming_boundaries.py tests/integration/acp/test_launch_trust_flow.py --ignore-glob="*plan1126*"` | 5,636 passed, 39 skipped, 1 failed (the logging-surface manifest still named the removed lock; fixed in `7bc6aa2`) (run `20261028T075748-24012-8d6a3f`) | `5808f7da16f6aa4c8d88bb26af77318d79fbc0b7e7d4c320a74fd83aaa7ae39b` |

The Windows full suite with coverage on the final head and the Linux PR CI job (guardrails → `clean-environment-recheck`)
are recorded below when they finish.

## Reviews

- Codex CLI (gpt-6.1-sol, high, read-only): round 76 follow-up 3 (the requirement), round 78 (plan r1) and its
  follow-up 1 (plan r2), each "approve with changes", posted verbatim on #433.
- Fable 5.1 checkpoint review of `7bc6aa2`: approve with changes (one should-fix: an untouched publication must not be
  rolled back when reads fail; three nits).
