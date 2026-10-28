# #433 approval-store validation record

Sanitized evidence for [#433](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/433) and
[ADR-030](../../decisions/ADR-030-approval-records-in-bounded-keyring-parts.md). It holds no credential, setting value,
record content or HMAC. Raw logs are workstation provenance only, under the operator's handoff folder
`sandbox-review-kit/p433-approval-store/`; their SHA-256 values are listed so a copy can be checked.

## Claim

On Windows, a launch-approval record over one credential blob (2,560 UTF-16-LE bytes, about 1,280 ASCII characters) is
stored as at most two authenticated, generation-specific parts behind a manifest published last. It round-trips through
the real Credential Manager. Missing, mixed, oversized, tampered or inconsistent parts fail closed. Every value an
approval record is stored as is checked against that limit before it is written; the small fixed-size HMAC key and
diagnostic grants are not checked. Every approvals-service operation holds one service-wide lock, except the read of an
HMAC key that already exists (a read cannot resurrect an entry). Keyring backend failures are typed refusals that carry
no backend message or stored value.

## Probes

| Probe | Result | Log SHA-256 |
|---|---|---|
| Real `WinVaultKeyring` (keyring 25.7.0), isolated throwaway service, random hex values | 1,279 and 1,280 chars stored and read back; 1,281 and 1,800 chars refused by `CredWrite` with winerror 1783; every probe entry removed | `b086ea41373a08e7df504be6af370771bc3365f87eb9c99a9b063ce5c7acaae2` (script `cc539d989fe84ef49d731f5f16f9ebdef5293f7156003b25d8d9048ecedb6701`) |
| `msvcrt.locking` contention between two handles | errno 13 (`EACCES`), the errno the lock retries on Windows | `80b32cda4696ead1ec60fa79800f92610abbbda1ac5f6ff571e53ddecc75f7cb` |
| Directory ctime on Linux (WSL2, kernel 6.18) | creating a subdirectory inside a directory changes that directory's ctime; creating one outside it does not | `659b3ac193561495a6eed6d3d1431b1cf09fd7cee20f651e48e240987021f08b` |

## Runs

| Run | Head and tree | Command | Result | Log SHA-256 |
|---|---|---|---|---|
| Real Credential Manager round trip | `7bc6aa2`, clean | `pytest tests/integration/acp/test_launch_approvals_windows_keyring.py -m requires_os_keyring_write` (Windows 11, Python 3.14, isolated random service, explicit HMAC key) | 5 passed (run `20261028T081951-15828-e1695a`); then `CredEnumerate('*optimus-p433-*')` found no leftover entry | `e6bcca5924c55dba166f14d603e98a38e847d8007d9dd0e622e567f75791654e` |
| Plan 11.26 runtime audits | `7bc6aa2`, clean | `pytest tests/unit/acp/test_plan1126_*.py` (six files: cancellation, delivery contract, queue policy, semantic errors, session lease, shutdown; full audit depth) | 85 passed (run `20261028T081957-40696-d120c2`) | `6a4b406d7cededf9acc6149d64ea0642ddfa3f3d19f035775c969d1373601370` |
| Targeted unit run, provisional | uncommitted working tree on `4a8c492` (before `7bc6aa2` was committed), before the logging-manifest update and the `DELETION_FAILED` detail | `pytest tests/unit/acp tests/unit/mcp tests/unit/tools tests/unit/evidence/test_naming_boundaries.py tests/integration/acp/test_launch_trust_flow.py --ignore-glob="*plan1126*"` | 5,636 passed, 39 skipped, 1 failed (the logging-surface manifest still named the removed lock; fixed in `7bc6aa2`) (run `20261028T075748-24012-8d6a3f`) | `5808f7da16f6aa4c8d88bb26af77318d79fbc0b7e7d4c320a74fd83aaa7ae39b` |
| Focused run after the Fable fixes, provisional | uncommitted working tree on `7bc6aa2` whose content was then committed unchanged as `6c630f1` (tree `a73d58dd4946dc790e27b21182b11aa0145c5359`); not an exact-commit run | `pytest` on the approval-store, CLI, gate, wiring, Stage C, registry-override, auto-composition, logging-surface and docs tests | 544 passed, 13 skipped (run `20261028T084009-53048-e1647f`) | console only; no log retained |
| Windows full suite, void attempt 1 | `6c630f1`, clean | the full-suite command below | stopped by Claude at about 14% because Codex round 79 required a code change; no result claimed | not used |
| Windows full suite, attempt 2 (failed) | `0b4b30a`, clean before and after | `python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json … --coverage-json …`, then `python -m tools.testing.coverage_products validate --coverage-json … --gate-report …` (PowerShell, Windows 11, Python 3.14.4) | 10,289 passed, 50 skipped, 106 deselected, **1 failed**: `test_test_profiles.py::test_the_platform_tag_follows_its_maintained_signal`, because the new multipart test file reads `sys.platform` but was not tagged `platform` in `tests/profiles.toml` (fixed in the next commit; tags do not change the default selection). Coverage: optimus 90.5157%, context_engine 95.9243%, optimus_model_policy 94.6816% (floors 80%, pass); evidence_handoff 68.4810% and aggregate 86.5874% (informational). Validity not established (`exit_status_differs`, from the failure) (run `20261028T085133-51996-307ff9`) | log `8f8dbedb399d1cd74a426f69b0279a5f3e2976c914dfbaa53bcf96b80d3e0325`; report `afa51de67305f04a6a6e0ae691e0edf0e787249472af11e307834e00c6d22cee`; coverage JSON `70c70e37e6604580610b2e0cc0e53087a362c881185f03f74b83a4673aca8632`; validity `f677df31ade4a28ccd8bdd132c7da2e7e55cbd2fa7c0ff55cff3249de5e096e4` |
| Real Credential Manager round trip, final code | `0b4b30a`, clean | as above | 5 passed (run `20261028T085113-21608-de716f`); no leftover entry | `417b3a19e23c6bb47a164cd1fdf1271ba5875457c7add41530582dad01403993` |
| **Windows full suite, attempt 3 (the PR's code before the merge with `main`)** | `408a43e`, clean before and after | the two attempt-2 commands | **10,290 passed, 50 skipped, 106 deselected, 0 failed**. Coverage: optimus 90.5060%, context_engine 95.9243%, optimus_model_policy 94.6816% (floors 80%, pass); evidence_handoff 68.4810% and aggregate 86.5796% (informational). `src/optimus/acp/launch_approvals.py` 94% (87% at `a358d58` before the change). **Full-run validity established** (run `20261028T095644-43224-5b6cee`, 346 records considered) | log `0cccfdbcfecad7d91a4354d372a40fd3a83142bb2e755ee495d50565b4024230`; report `beb287dc53ab61d9527191700facfa03e1d7724ef1f421a38a91a4f67dc3bce4`; coverage JSON `8126c53f4b2b2a92269411a1fb4cab9192e8cfff491c98440b752b6db6aaa1a1`; validity `2d67b3539f93ea261f6aa45b440689c133330108495566ab41394b65d9f9ee9b` |
| Linux PR CI (failed) | `71710e9`, the merge of `origin/main` (#434) into this branch | GitHub Actions run 40676815817, `clean-environment-recheck` | 10,114 passed, 309 skipped, 106 deselected, 1 failed: `tests/unit/acp/test_main_wiring.py::test_migrated_authorization_appends_migration_event_before_authorization`; launch refused with `NO_APPROVAL` (see the Linux CI failure section below) | `aeb2bc01f45d23a743bae63f8f11f61fdd1b0749cd00a1758281da944bd488ca` |
| Windows full suite, void attempt 4 | `71710e9`, clean at start | the two attempt-2 commands | **Void; no result claimed.** It hung at 80% (8,352 tests run) in `tests/unit/tools/test_plan117_custody_relay.py::test_control_channel_rejects_malformed_requests`: pytest used no CPU and the log did not change for 1 h 44 min, so Claude stopped it. Earlier in the run, `tests/unit/tools/plan1126_runtime_audit/test_checkpoints.py::test_checkpoint_store_allows_only_one_concurrent_expected_revision_writer` failed. Its message was never written, because pytest prints failure text only in the end-of-run summary. Neither test, nor the code it exercises, is changed by this PR or by #434; both were last changed in August 2026, and both passed in attempts 2 and 3 (run `20261028T110217-39800-0ae9d1`) | log `218e1d85c92322ecf32f4c79aa28fb992f15b7bc36c91486506f2fd11dde18e0`; phases `7a97447f2ad9b1072881287b0f79e094072b04a80b491ccbbcac5c3cd0a06830`; nodes `bff91a877bd3eb53a3d234b052364941563f6cacdd81fec3e3f79f488d2857f9` |
| Repeats of the two attempt-4 tests | `71710e9`, clean | each test alone in a fresh pytest process, both loops running at once, with `faulthandler_timeout=45` and a 120 s kill | the checkpoint test passed 40 of 40 runs; the relay test file passed 15 of 15 runs (48 passed, 2 skipped each); neither reproduced | summaries `240cfead4dbaa0dfb43243f06b35d6c3d0a4e6c2f99708a9a26880e1f42a46c5` (checkpoint), `05aa23ebaa4dcedad8351250547779a7843b41127f9534bc14208cc00832f9a4` (relay); script `f34750eff7ef622d49c33c86a49960e7b1ccc9f4d0733e6bf68c3f9939a9302e` |
| Checkpoint lock on an unlinked file another handle still holds (Windows 11) | n/a | `O_CREAT\|O_EXCL` open after the lock file is unlinked while a `FILE_SHARE_DELETE` handle is open | the name is gone at once and the create succeeds, so the cause cannot be that the lock refuses a delete-pending file on this host | `b671474e16a489eb44ea9bd5c1f04bbf33104bc5e90324bcf028bf974f534623` (script `595c7854fe0b4ef5d606f4de1a2ecaba3162cd5a004746cd9b1384898b13ced1`) |

Attempt 3 covers the PR's code at `408a43e`. The merge with `origin/main` and the test-only fix that follow it are covered
by the check that Codex rules on for the final head. That check's result, and the Linux PR CI result with its run URL and
head SHA, are recorded on #433. The Linux PR CI job is guardrails → `clean-environment-recheck`, which also runs the
coverage gate and the dataset validation.

## Linux CI failure on `71710e9`

The legacy v2 workspace digest hashes the workspace root's `st_ctime_ns`. The test helper `_seed_legacy_v1_approval`
computed that digest, then built its `KeyringApprovalStore` with a runtime root inside the workspace. Since this PR, the
store creates its HMAC key under the service-wide lock, so it creates `<workspace>/.optimus-runtime/locks` at that point.
On Linux, creating a subdirectory changes the parent's ctime (see Probes). The workspace's digest therefore changed
after the helper had keyed the legacy record to it, and launch found no record. On Windows, ctime is the creation time,
so this test passed in attempts 2 and 3.

Production builds the store with the approval runtime root, which is outside the workspace. The fix is test-only: the
helper's runtime root moves beside the workspace, as other tests in that file already do. The helper now asserts that
seeding leaves the workspace's legacy v2 digest unchanged. Without the fix, that assertion would fail on Linux at the
same change that run 40676815817 later reported as `NO_APPROVAL`. This is inferred from that run and the ctime probe; the
test itself was not run on Linux without the fix.

The attempt-4 failure and hang are unrelated to this PR. Their causes are not established. The run kept no failure
text and no stack, and neither test reproduced in isolation.

## Reviews

- Codex CLI (gpt-6.1-sol, high, read-only): round 76 follow-up 3 (the requirement), round 78 (plan r1) and its
  follow-up 1 (plan r2), each "approve with changes", posted verbatim on #433.
- Fable 5.1 checkpoint review of `7bc6aa2`: approve with changes (one should-fix: an untouched publication must not be
  rolled back when reads fail; three nits), applied in `6c630f1`.
- Codex CLI round 79, checkpoint review of `6c630f1`: approve with changes. It asked for: an exact integer manifest
  version; this record's provisional labels and missing rows; narrowing two claims in this record and ADR-030; and
  dataset validation beside the full suite. All four are applied in the next commit.
