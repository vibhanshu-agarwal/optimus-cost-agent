# Static typing port — pre-commit verification snapshot

Captured 2026-10-16T21:02:29.4385007Z. This is historical evidence from a provisional working/index candidate at base `c5ea5a1673b957f1e2dd3a09321c6a34ff293880`, not final-commit acceptance or a live work register. [#329](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329) owns coordination and current gates. No project commit, push or PR existed at this snapshot.

The operator directly approved implementation of reviewed v2, one unpushed local commit after Claude's pre-commit review, then Windows/WSL verification. The [filed contract](../docs/superpowers/plans/hardening-static-type-checking-implementation.md) retains approved-source SHA-256 `68e5a0484243825cd96aa3340723bd5f5e10a5c1535fd362f6de25b0c34f616e` and the reviewed registration correction.

## Scope and retained debt

Mypy 2.3.1 checks all 226 source files with the accepted exact stub pins and third-party import policy. The [accepted C1 baseline](static-typing-baseline-2026-10-16_v2.md) measured Windows 231 errors/46 files and real WSL 222/45, with a union of 46 exact modules. All nine baseline artifacts remain unchanged. The bootstrap fixture remains a one-time, digest-bound anchor; accepted Git history controls subsequent shrinkage.

Telemetry is removed from the exception group, leaving **45 modules as measured debt**. A masked green result does not establish that those modules are clean. The two known registry override diagnostics remain out of scope. Fresh final unmasked totals and exact retained/cleared/new comparisons have not yet been measured.

Production diff: exactly sixteen `trace_id=run_id` additions in telemetry factories and one `"mypy"` name in the existing parity rule set. Removing the sixteen arguments reconstructs the original telemetry AST; signatures, validator behavior, payloads, redaction and settlement fields are unchanged. Runtime tests use real models, with no double conversion.

## Development evidence

All passing pytest runs below are native Windows/Python 3.14.4, active/default-selection, native-valid, full protection, COMPLETE, exit 0. `parent=UNKNOWN:access_denied` remains a qualification. Coverage-free checks do not establish product coverage.

| Check | Result and receipt |
|---|---|
| Task 1 whole-diff checkpoint | Invocation `20261016T195615-23672-c9d06f`, PASS/exit 0; manifest SHA-256 `6c53840ab22bdc39f971ae87ac082339f8433c5a8d0906698ea2ab36aa1035d4`; selected 7332 passed/39 skipped/one existing runpy warning; full audit load 78 passed (100/100 shutdown repetitions); three repeats each 388 passed/8 skipped. Stability complete, obligations empty; before/after candidate hashes and status identical |
| Independent Task 1 check | Claude: 325 passed, 164 s, empty stderr, run `20261016T205031-65424-e7c53d`; [bounded ACCEPT](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329#issuecomment-6224495030) |
| Telemetry runtime invariants before fix | 34 passed, run `20261016T205520-32060-2f00a4`; the existing validator already provided the runtime behavior |
| Telemetry static RED | Removing only its exception reproduced exactly 16 `call-arg` errors in telemetry, checked 226 files, exit 1; no runtime failure invented |
| Telemetry plus ratchet after fix | 55 passed, run `20261016T205551-38652-7b6065`; standard Mypy: zero issues in 226 files with 45 exceptions |
| Task 3 wiring RED | 21 passed/one failed for the absent Mypy parity name, run `20261016T205659-65432-bc0d47`, exit 1 |
| Registration state RED | Existing one-Active assertion failed after registering the typing child, run `20261016T205737-54252-26a4f5`, exit 1; only expected active identities/counts updated |
| Integrated focused checks | 284 passed, run `20261016T205804-56420-66904f`; policy, telemetry, parity, profiles and both documentation hygiene modules |
| Final policy module | 22 passed, run `20261016T210108-37356-0b43c0`; one import-group blank line corrected after Ruff I001, with identical AST; Ruff all-repository check then passed |
| Enforcement commands | New `optimus-mypy --all-files` hook passed; both exact native and `--platform win32` Mypy forms report zero issues in 226 source files |
| New-plan prerequisites | Canonical plan table checked directly before commit-dependent discovery; post-commit hygiene remains required |

The [Task 2 bounded ACCEPT/#328 receipt](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329#issuecomment-6224566531) independently verifies the staged AST, all sixteen factory cases and direct-construction invariants. It does not close the broader test-double track.

Earlier checkpoint attempts are preserved as failed/interrupted evidence, not acceptance. Attempt 1 exposed frozen-byte/index normalization and the Windows WSL-launcher/Git-Bash mismatch; exact frozen-path attributes and task-local Git Bash address them. Attempt 2 exposed a prohibited direct source walk; the existing selected-index inventory and omission controls replace it. Attempt 3 selected 7329 passed/39 skipped/two failed/one setup error, then its remaining owned overlap work was interrupted: the Mypy child needed its existing tripwire/census proof, a direct index listing needed replacement with the validated inventory, and existing hook environments needed a healthy task-owned cache. No scanner/child-proof allowlist was weakened; the shared cache was untouched. [Full cause/fix receipt](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329#issuecomment-6224408397).

## Reviewed support corrections

Ten exact `.gitattributes` entries preserve the bootstrap and nine frozen reports. One existing child-site census row binds the real Mypy test child to its loaded startup tripwire. The existing hardening masterplan registers a linked Active typing child, with no backlog row; the directory-hygiene assertion follows two Active and thirteen Not drafted children while retaining all fifteen identities, link rules and registry-disjointness. [Registration review](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329#issuecomment-6223733211). Private execution contents remain ignored by the existing nested rule and are excluded from staging.

## Candidate hashes

| File | SHA-256 |
|---|---|
| `pyproject.toml` | `1b203ef97964dc2dd8322b2d9bdfab4da3a1d2e5194f2af7934af13d88a31bf3` |
| `uv.lock` | `b3669ad80c64effed108e0a90a33ba00a92814435153b85059889bae6790eb46` |
| `tests/fixtures/typing/mypy-bootstrap.json` | `b6a756129365762efe42c77593313507fd1be1a039a85ef4ebc22490194c5bab` |
| `src/optimus/telemetry/events.py` | `7cbb683749776de4b75d05d65d4e8d84a44548d52839a3f8e9220c69792987dc` |
| `src/optimus/guardrails/ci_parity.py` | `070743f8df19e62ae4582f14f701196cff9c5ae427009548264dd1a07ae2b88f` |
| `tests/unit/telemetry/test_events.py` | `ffc46b38be8fe96245b1e622768c88001b85614093f8d2212970fe7f389fdeb1` |
| `tests/unit/tools/test_mypy_ratchet.py` | `9b612a2eae3b8c89c2ac9dafa7e400431295a66aa368cf1658eb61e0e203b131` |
| Filed implementation plan | `8c7ed7e87a81b6d2ea597817df9741ca471323a3ec36223c5e4e3c05619fe591` |

## Remaining evidence at capture time

The integration whole-diff checkpoint, Claude's whole-diff pre-commit review, normal-hook single local commit, post-commit documentation check, matching native WSL clone and serial final Windows/WSL diagnostics/product coverage/validity are pending. Final results and Claude's review will be recorded in a separate private successor and #329, leaving the measured committed tree unchanged.

The exact-source historical Linux CI coverage export/configuration/lock/groups/tree receipts were verified against the base commit and retained for platform-qualified comparison ([original successful run](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/38909125602)); its Python patch is 3.14.8. No comparable prior-source Windows export was found in existing lane output locations. The Windows safety non-regression comparison remains UNKNOWN unless appropriate evidence becomes available; Linux evidence cannot establish that Windows comparison. Any unavailable required comparison holds acceptance under the approved plan.