# 15. Plan 12 claim-to-evidence strategy

**Edition scope.** The retained Plan 12.2 strategy and evidence below keep their original pins. The 2026-10-18 ordinary shipping amendment (`docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`) controls unrefreshed Plan 12.2 production and evidence statements. Section 15.8 adds Plan 12.9 and its necessary Plan 12.8 accounting prerequisite, inspected at main `a88fde86a2ddf382a9bb39a6e2c1a74a1db20498`. Plans 12.5–12.7's memory work and the remainder of Plan 12.8 are not refreshed; no historical result is transferred to that pin.

## 15.1 Coverage and checkpoint evidence

Section 8A defines one complete coverage dataset, independent product reports and separate 80% floors for `context_engine` and `optimus_model_policy`. The source-group inventory must cover every top-level import package under `src/` exactly once, including informational groups. A new package, duplicate membership or unassigned package fails the guard rather than disappearing from aggregate measurement. The top-level model-policy package floor is an extra report, not a second product ownership.

Historical candidate/test/coverage seals and post-run deltas belong in the closure records. They do not prove changed executable bytes, route quality, persistent enforcement or live editor behavior.

The three historical strict xfails are resolved at cf9bb9d: their assertions now pass and the markers are removed. This does not turn skipped, deselected or UNRUN evidence into passes. Skips, deselections, failed/invalidated attempts and unrun marked tiers remain explicit. Later testing may measure more files and reduce percentages. A `tail`/wrapper exit never substitutes for the underlying coverage/test exit.

Use existing focused checks for accepted-value assertions and documentation-only fixes. Do not repeat the full suite simply for numeric test additions or provenance wording. A newly released substantive product migration requires its applicable checkpoint verification; do not claim the earlier full run tested those new bytes. Keep this within CP4 rather than inventing per-task review gates.

## 15.2 Offline claims and required cases

| Claim | Required cases / source scopes | Tier |
|---|---|---|
| Extractability | Forbidden imports; independent noneditable wheel import; packaged YAML; negative tainted extraction probe | Unit + isolated wheel |
| Exact authority | All-turn outcomes/effects/approvals preserved when ordinary history is omitted; model text cannot manufacture facts | Unit + host integration |
| Strategies differ | Hybrid anchor/tail discriminator, deduplication, complete newest-turn sliding, zero sliding maintenance | Unit |
| Packing safety | ASCII/code/CJK/emoji; exact/one-over token and byte input; maximal fresh/reused summary; non-subadditive negative backstop; preflight zero-call rejection | Unit |
| Checkpoint integrity | Prefix append/change/reorder, stale configuration/revision, cancellation, malformed/oversized/partial output, no publication on rejection | Unit + host integration |
| Refusal/fallback | Every known and unknown reason, unavailable zero-provider case, failed-summary receipt retained, <=floor full fallback, >floor OPEN refusal and healthy recovery | Unit + host integration |
| Selection and approval | Exact retained hints use current files; summary never directly selects; stored-view digest and exact artifact approval; changed-target handling | Unit + controlled-tool integration |
| Picker/config/meter | Attached-only strategy option; full option set; setter interleaving; old flush/new pending; first sliding notice; largest actual dispatched request and no fabricated refused reading | Unit + real client |
| Final request guard | Equality/one-over at actual attempt boundary; trusted snapshot; all framing/material and one output reserve; incomplete finish blocked before plan approval | Unit + route evidence |
| Accounting | Exactly-once known/unknown/cancelled/stale attempts; divergent duplicate rejection; known subtotal retained; no re-debit on stored-plan application | Unit + real ledger |
| Product/evaluation split | Product result above former $0.05 delivered; no dollar predicates/prompts/constructor requirements; finite count/time/failure retained; separate capped evaluation stops | Completed former strict-xfail assertions + integration |

Use actual source scopes including tests/unit/context_engine, model_policy, acp, agent, usage, loops, optimus_gateway, tools, telemetry, retry, package-import tests and tests/integration/loops; use actual collection to select relevant names. Do not invent a passing test file or apply blanket xfail removal.

## 15.3 Per-route eligibility and D7 boundary evidence

Record exact model/provider/endpoint/quantization/reasoning, window >=262144 and output caps >=role reserve, estimator algorithm/assets/version/digest, normalization/pre-tokenization and framing proof, enforced cap parameter and true finish semantics. Verify both actual request paths at exact and one-over complete capacity, with maximum permitted additional material and one output reserve.

The named ADR-014 exception retains 524288-byte source/admission and its warning but permits readable OPEN refusal when full history cannot fit. The operator's acceptance is recorded verbatim in ADR-018 (source S4; decision 2026-10-04, filed 2026-10-07). No source-floor reduction or capacity exemption. Public JSON/config inspection does not count tokens or install libraries; exact route-tokenizer dependencies remain deferred. Samples/family labels cannot establish conservative safety; unknown/expanding normalization remains ineligible. Verified r=1 substantially reduces usable exact tail/history in bytes, disclosed in the closure proposal.

## 15.4 Summary qualification

Use the existing `tools/evaluate_context_summarizer.py` and `tests/fixtures/context_engine/calculator-constraints-v1.json`. Step 1 summarizes turns 1-5; step 2 merges that actual summary with turns 6-7. Turns 8-9 are exact tail and cannot mask omission of either early constraints or the late correction. Evaluate the summary itself for Decimal, public calculate API, no eval/exec/network, negative inputs, HALF_EVEN as current, HALF_UP as superseded, both rounding examples, no invented approval/deletion and inert injection text. Protected approval projection must separately equal the host source.

The fixture output cap is **1200 tokens**, not the proposed production summary cap of 8192. Record this scope honestly. Require complete stop status and exact prompt/format/validator/fixture/model/endpoint/reasoning identities; a changed qualification key invalidates receipt reuse. Human review complements the deterministic lexical report. Two steps are a limited gate, not a statistical quality guarantee.

The current offline envelope reports two requests, input-token upper bounds 2333/2766 and up to two allowed provider attempts per request. Its old-price estimates and route blockers are not current paid eligibility. Qualification permits two logical requests, at most four physical attempts: one identical-route/payload resend only after NOT_SENT (including proven pre-connection timeout)/429. Require current complete input/framing/cost bounds and host non-retryable propagation; uncertain timeout/5xx/usage never retries. No alternative model recovery.

## 15.5 Real dependencies and editor

Status: Task 13 is deferred and UNRUN by the operator's 2026-10-08 disposition (recorded in `docs/superpowers/reviews/2026-10-08-plan-12-2-cp4-offline-delivery-disposition.md`); its absent-engine cases may run before summary qualification once their own route, service and execution prerequisites are met. Task 13 uses independently authored acpx, the real Optimus process, real loopback Gateway, real TimeSeries-capable Redis and actual Zed rendering, under scoped credentials/TTY/service authority. The reviewed named test composition implements real server dependency injection and enabled GatewayModelPolicy, with HMAC launch approval/authenticated child-manifest hash binding. Positive offline proof uses a synthetic eligible profile; the real qualification profile remains ineligible. It cannot replace the client or claim production bootstrap activation. Use separate absent-engine and small Chat/Agent sessions; reuse one seeded attached session for large source, sliding, fault/recovery and cancellation, restoring compaction before maintenance. Maintenance requires real quality receipt/profile B; otherwise it is UNRUN. Vibhanshu supplies the named Zed prompts/approvals at the keyboard. Do not import old placeholder effects as real authority.

Prove mode/model/strategy option preservation, attached-only picker, sliding disclosure, separate storage/fallback/refusal notices, readable OPEN no-call refusal, truthful meter and absent-engine defaults. Exercise >512 KiB attached source, bounded fault/unavailable recovery and cancellation during maintenance. Record whether >floor history was generated through client traffic or explicitly seeded as synthetic canonical records; seeding is test setup, not proof of a natural conversation or durable resume.

Do not silently introduce a missing production seam to obtain evidence. Establish launch/tool/service prerequisites first and produce claim-specific non-passing rows when unavailable. A test seam's simulated unavailable response proves fault handling, not provider outage. Live cancellation can bill a started request; retain it.

## 15.6 Evidence package and closing verdict

Every claim records exact source/configuration/registry/launch identities, commands, dependency versions, selected test names, genuine individual exits, attempt receipts, sanitized conclusions and hashes. Preserve failures and seals. A unit fake cannot fill an acpx, Zed, Redis, Gateway or Phoenix live claim. Existing search/plugin and Phase 1 working-agent gates remain unchanged outside this Plan 12 package.

The offline implementation and documentation through `2068366` were accepted by the operator on 2026-10-08 and merged to `main` via PR #276 (`c509fc8`); that acceptance is the offline merge gate, not a full CP4 pass. CP4 clears only when all its required measured-value, route, quality, migration and real-client obligations have named passing evidence or a separately recorded operator disposition. Coverage gates use full-suite data. The existing full WSL run before finalization remains unchanged; inventory that environment early and retain exact candidate, selection and exit. The two independent package floors are settled operator requirements. Evidence Handoff's 80% threshold is deferred in enforcement until revisited; interim coverage requires no new tests. Do not declare the broader Auto/reviewer/savings/loop/resume scopes complete. Deferred work retains its existing owners in the authoritative tracking venue, according to the actual Plan 11.29 cutover. Publication, merge and production activation remain separate decisions.


## 15.7 Completed offline evidence and remaining claims

**Observed offline candidate, 2026-10-04:** cf9bb9d (clean local CP4 branch). V1 capacity text/meter, V3 remaining-allowance preflight, Task 11 product/evaluation separation, named trusted test composition, tracked-source coverage gate and Task 12 boundaries pass offline verification. Windows (`final-gate-2`): 6830 passed, 0 failed, 39 skipped, 111 deselected, 1 warning, exit 0, 1:10:40; WSL (`wsl-full-1`): 6641 passed, 0 failed, 228 skipped, 111 deselected, 1 warning, exit 0, 40:09. Scope: the repository's full default marker selection at clean cf9bb9d; the 111 deselected tests are those the default marker selection excludes (live-dependency and other marked tiers). The failed `final-gate-1` attempt (3 failed, 6807 passed) preceded them and remains failed in the sealed evidence; its walker violation and two frozen-lane regressions were corrected before `final-gate-2`. Required coverage at cf9bb9d: Optimus group 89.4393% (Windows) / 88.9078% (WSL); context_engine 95.9243%; optimus_model_policy 96.9880%; Evidence Handoff 68.4165% / 65.9629%, BELOW its informational 80% threshold; the aggregate is informational. The limits and wheel proofs (zero proposal violations, max_repacks=1, planning material 43795 bytes, D7 upper bound 185581 bytes / 35.40%; wheel SHA-256 13b06132...ffd36, shipped effective registry hash unchanged) were produced at cc6959b and carried to cf9bb9d only because `src/`, `pyproject.toml` and the lockfile were unchanged between those commits; they were not rebuilt at cf9bb9d. All of these are historical measurements at their stated pins, not measurements at 91fd64a. At the filing state of this correction the documentation checks passed; the coverage-free commit-profile hook (`run_profile --profile commit`) selected a broad fallback of 6697 tests and failed on this host's unprovisioned ast-grep hook environment (6659 passed, 37 skipped, 1 warning, 1 error, exit 1), and it emitted the platform obligation `wsl-platform: next checkpoint`, which is undischarged (see §16 and the validation record). No new full-suite, coverage, live-qualification or activation result is claimed. Production ENFORCEMENT_ACTIVE=False, trusted_snapshot() returns None, and the shipped claude-haiku-4.5 default are unchanged. Luna remains ineligible, Qwen remains unqualified, and paid qualification/real editor Task 13 remain UNRUN. See review-disposition.md and evidence-verification.json. This source review is not production activation or full CP4 closure.

The actual HostMaintenance callback and GatewaySummarizerCall boundary test includes summary-prompt/wire framing and one output reserve: equality admission, one-over INPUT_EXCEEDS_CAPACITY and zero upstream attempts on rejection. The final numeric proposal includes max_repacks=1. The refused case requires two repacks: one refuses after exactly one, while two fit. Positive profile capacity/finish proofs use synthetic test estimators and do not establish Luna eligibility.

The Windows and WSL run records name the exact clean candidate and full command; the sealed logs retain each environment’s test-run context. WSL’s Redis 6379 guard blocked its positive control and one existing reachability probe, which sent no Redis command. This is not evidence of arbitrary service isolation or Windows job parity.

Plan 9.88 historical claims use the frozen lane prompt version and retain all evidence checks. Its runner refuses new captures when the product prompt differs. Plan 9.87 keeps current-prompt validation. This preserves old evidence, not a new live acceptance.

## 15.8 Durable usage capture and cost-savings reporting

### Claims and executable checks

The production contracts are HLD §14.10 and LLD §13.13–§13.16. ADR-032 is accepted by ADR-033; ADR-034 remains Proposed. Test sources at `a88fde8` provide the following checks; their existence alone is not a passing run.

| Claim | Named executable source and discriminating cases | Evidence class |
|---|---|---|
| Canonical actual cost and honest coverage | `tests/unit/optimus_gateway/test_usage_report.py`: duplicate-attempt refusal, unknown cost, missing/open/incomplete epochs, late/conflicting receipts, expected-turn and frontier gaps, unattributed Auto turns, unallocated overhead | Unit |
| Independent B1 arithmetic | Same file: one fully loaded subtraction, signed negative savings, zero baseline without percentage, nested token categories, missing splits/prices, long-context thresholds, independent reference availability and all-stage fixture | Unit |
| Reference and snapshot integrity | `tests/unit/model_policy/test_savings_references.py`, `tests/unit/optimus_gateway/test_usage_price_snapshots.py`: strict configuration, content identities, approved overrides and durable-before-stamp behavior | Unit |
| Read-route contract and bounds | `tests/unit/usage/test_usage_report_contract.py`, `tests/unit/optimus_gateway/test_usage_report.py`, `tests/unit/optimus_gateway/test_server.py`: strict schema, authentication, bounded pages, stable errors, sealed cursors, changed revisions and worker deadlines/cap | Unit/contract |
| Host transport and rendering | `tests/unit/usage/test_savings_report.py`: whole-exchange deadline, slow headers/body, byte bounds, malformed replies, escaping, exact labels and unavailable sections | Unit with local socket checks where required |
| ACP command lifecycle | `tests/unit/acp/test_savings_command.py`: advertisement after `session/new`, local no-turn handling, session/turn continuation, confirmed flush, cancellation, late reads, retirement and teardown | Unit and real-channel composition; not independent-client acceptance |
| Auto attribution through escalation | `tests/unit/acp/test_savings_escalation_capture.py`: one Auto context and each captured classifier/planning receipt counted once | Offline composition; no real-model or campaign claim |
| Durable capture substrate | `tests/integration/usage/test_durable_capture_postgres.py`: pinned migrations, atomic commit, replay, aliases/conflicts, database immutability, concurrency, outage/restart, killed writer and real capture HTTP | Real Postgres tier |
| Consistent report reading | `tests/integration/usage/test_savings_report_postgres.py`: 001-to-002 migration, immutable snapshots, canonical rows, concurrent ingest between/during pages, lock/read deadlines, outage/restart, replaced ledger, capture frontier and production HTTP | Real Postgres tier |
| Gateway-only database credential | Both Postgres files' subprocess boundary cases: provisioned Gateway resolves its keyring credential while the host/test environment has no ledger password | Real Postgres plus real OS keyring and Gateway process |
| ACP compatibility and Zed rendering | Independent acpx and actual editor proof, separately attributed in `reports/plan12-cost-savings/zed-ui.json` | Real protocol/UI dependencies; synthetic costs do not establish real-provider savings |

The all-stage fixture is a reducer-level unit check. Real Postgres report receipt fixtures use planning; they do not prove every production stage against Postgres. Preserve that distinction.

### Selection and prerequisites

`pyproject.toml` excludes `requires_plan12_capture_postgres` from the default marker expression. A green default suite therefore does not exercise it. After the operator releases the disposable resource, an explicit database-tier selection is:

`uv run pytest -q -m requires_plan12_capture_postgres tests/integration/usage/test_durable_capture_postgres.py tests/integration/usage/test_savings_report_postgres.py`

This supplies a marker selection while retaining the repository configuration and root conftest. Record the emitted run mode/reason and actual selected tests; it is focused dependency evidence, not a full-default-suite result or proof of active default-run protection.

The ordinary database fixtures require `P128_CAPTURE_K3_CONFIG` and `P128_CAPTURE_K3_PASSWORD`. The configuration names the released container, image identity, dedicated volume, loopback endpoint, database and role. The fixture inspects the container before connecting. Missing prerequisites skip as UNRUN; no shared, production or another plan's database is an acceptable substitute. These tests can create/drop scratch databases and stop/restart the released container, so resource release is a real prerequisite, not implicit permission from this command example.

Credential-boundary cases require a separate invocation: omit `P128_CAPTURE_K3_PASSWORD`, provision the credential in the Gateway's real keyring namespace, and provide `P128_CAPTURE_K3_CONFIG`, `P128_CAPTURE_K3_ACCOUNTING_ROOT` and `P128_CAPTURE_K3_RUN_ID`. Those cases also carry `requires_os_keyring`; select the intended boundary cases explicitly and retain any skips. A pytest process that possesses the password cannot establish the password-absent boundary.

Record source/configuration identities, exact commands, resource identity, platform, every selected/skipped test, genuine exits and retained evidence. Separate focused database, credential-boundary, full-suite, independent-client and editor runs. Provisioning or running any of them requires its applicable service, credential and interaction authority; this document performs none.

### Acceptance limits

B1 uses the same reported tokens at dated reference prices and is not realized savings or an Auto-off workload. The actual total already includes captured overhead. B2/B3 remain unavailable and require no speculative reader. OC-4 (#463: https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/463) owns their commissioning, producer contracts and paid authority, plus the deferred native memory-evaluation campaign.

Section 16.1 records the reported Plan 12.9 results, failed Windows gate, operator disposition and final paging-fix limitations. No test tier silently substitutes synthetic provider values for a real-provider claim.
