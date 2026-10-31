# H4 historical replay test-contract repair (#447)

This test-only repair addresses [#447](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/447), found while publishing the [#324](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/324) Ruff tranche. Four tests still invoked the old historical schedule executor against current runtime classes. On the recorded main baseline they correctly failed closed on changed lifecycle authority. The production historical builder already consumes sealed observations; historical verification must not regenerate those observations by executing today's code.

The frozen [2026-10-27 contract](../../decisions/2026-10-27-ordering-lifecycle-signals-queue-contract.md) approved a pinned-writer historical-execution mechanism. That retained helper currently refuses the canonical historical request because current lifecycle authority has drifted; this repair neither restores it nor decides its future retention, re-pinning or retirement. Its production source-drift safeguards remain unchanged. Four historical tests migrate to the production sealed-replay contract, and one existing negative control is strengthened after review. Scenario/count/citation invariants remain checked, while the former behavioral-mutation execution-test obligation is explicitly retired; replay-integrity and declared-authority membership checks are not equivalent fresh runtime evidence. Current writer/lifecycle suites retain ownership of current runtime behavior. This report grants no broader waiver or historical runtime acceptance.

## Changed obligations and inventories

All names below are in `tests/unit/acp/test_plan1126_delivery_contract.py`.

| Original node | Replacement node | Assertion after repair |
|---|---|---|
| `test_delivery_contract_model_1000_seed_schedule` | Same artifact-bound legacy ID | Real H4 builder replays 4 literal plus 1,000 derived rows; seed order/origin/anchor, all phases, vocabulary, canonical classification and settlement/commit invariants remain checked. The docstring identifies current replay validation rather than fresh schedule execution. |
| `test_h4_execution_emits_only_citations_for_behaviors_it_runs` | `test_h4_replayed_citations_match_immutable_definitions` | Independently resolves every operation and site citation's path, symbol, merged-anchor line and exact AST source-segment SHA-256; checks segment hashes in both authenticated source views and membership in ten explicitly declared primary definitions grounded in the retained harness record callsites. Path/line/symbol/digest mutations require their exact refusal reasons; a genuine unrelated definition with valid line/hash is refused specifically for membership. Overlay line positions can differ; citations are anchored to merged lines. |
| `test_h4_literal_scenarios_are_coherent_primary_transitions` | `test_h4_sealed_scenarios_preserve_primary_transition_evidence` | Checks the original eight fixed expected scenario tuples against every sealed row grouped by `seed % 8`, requires all eight groups, and confirms literal-corpus ordering. It manufactures no new rows. |
| `test_h4_behavioral_mutations_change_or_invalidate_primary_observation` | `test_h4_replay_refuses_missing_or_tampered_evidence_without_execution` | A valid replay/build/public-verify positive control succeeds while actual factory/probe lookup sites, diagnostic execution and live runtime constructors refuse execution. Missing H4 records and empty delivery rows raise the specific sealed-evidence refusal. A citation mutation with recomputed enclosing digests passes model validation but public verification rejects its divergence from the canonical sealed-row rebuild. That equality check does not authenticate citation source bytes; the separate static citation control performs authentication. |

Only the three renamed node references change in the binding manifest; its 37 unique, sorted IDs, owner, binding identity and conditional UNRUN semantics remain unchanged. The three renamed controls retain explicit `audit-current` tier rules with an explanation of conservative scheduling for replay/negative-execution checks. Their old measured-slow-node entries are removed without replacements: the historical measurement runs never timed the new IDs. No tier or selection is relaxed, and this is not a new timing survey. No test is dropped or newly skipped. The legacy 1,000-seed ID remains because the sealed artifact embeds its command.

The existing `test_h4_transition_authority_rejects_immutable_byte_drift` keeps its node ID but now uses an accepted same-view positive source fixture and requires the exact mutated writer/conversation path in each denial. Its previous broad match falsely attributed existing lifecycle drift to a conversation mutation; the earlier passing test did not prove conversation-path rejection. Other historical-writer digest, default live-source drift and annotation controls remain unchanged. No production module, public API, historical-execution helper, source comparison, annotation allowance, report fixture, source pin, snapshot, marker, test runner, coverage policy or skip rule changes.

## Source and evidence identities

Windows source base: `76848d0dd02cb5db569099418e7a5990ccc1d697`, tree `816c453cddc457a7c6cbf045b161690d6d576a1a`, branch `agent/codex/h4-historical-authority`. The baseline tracked tree was clean; repaired runs were provisional dirty-tree development evidence, bound below to exact candidate file bytes. Each run retains its own source binding; the pre-review 61-test result is not a result for the later review-fix delta.

| Input or tested candidate | Identity |
|---|---|
| Merged historical source | `5ea8f8f71548eb05a8562a10e98667e3d2061c4d` |
| Overlay historical source / local binding object | `fac32284888850bacde93815265cbabe3afd4663`; authenticated historical source reader; binding object present locally |
| Unchanged `reports/plan-11-26-acp-runtime-audit.json` SHA-256 | `8dc32bf425c501c1a2ec8282b0c68754839c1662dbf38f36fc109b3b4b7815df` |
| Unchanged frozen 2026-10-27 contract SHA-256 | `9bb6f087857df9767a48f7a7c76fadafc21db7809400f5664b43cafeb574a53b` |
| Unchanged `uv.lock` SHA-256 | `5f664bfb26fbe63ff6d99112fb8b3f180e3572379313b22b19362ef907add3c2` |
| Pre-review 61-test delivery-contract module SHA-256 | `dc73aa3f2ab7d8c216e5feda0bb16141bfdb67fd5d4bd62845f6127f0cdea118` |
| Pre-review 61-test `tests/profiles.toml` SHA-256 | `c7804f7b459ec06ef0d98251ad9502c3cd194e357045347dd6e16f92d78783c5` |
| Tested binding-manifest SHA-256 | `54f50d0a13f75f0305adb24cf534c4f1c5a2fef8de9200b85920d796d44aebc1` |
| First module run's source-patch SHA-256 | `da8d313cd4bacf044ba730b25723d21e23eb712fea8632571f68b2d26b9c0c39` |
| Pre-review 61-test three-file source-patch SHA-256 | `166fb9e226dcccfa7203c27cc3900d8ab3813922609f74b26b9a5096cec81ee8` |

## Commands and outcomes

Environment: dedicated frozen `.venv`, CPython 3.14.4, pytest 9.1.1, native Windows. Normal repository addopts and markers were preserved; focused pytest commands used `--no-cov`. No quick audit-depth override was used. The completed native pytest runs below each reported `mode=active`, `reason=default_selection`, native validity `valid`, `guard=pytest_process_guard`, `protection=full`, records `COMPLETE`, and parent observation `UNKNOWN` (access denied). Native validity and completeness do not turn a failed test run into a pass.

| Attempt | Run identity and result |
|---|---|
| Initial frozen environment setup | `uv sync --frozen --extra dev` failed on sandbox cache access and download DNS. The same frozen setup succeeded with authorized escalation; 92 packages installed, hardlink-to-copy fallback warning retained. |
| Baseline launcher attempt | `uv run --no-sync pytest --no-cov` with the four original target IDs failed before pytest because the sandbox interpreter cache could not be persisted; exit 2. |
| Baseline direct-interpreter attempt | The four-target command below failed during normal native run-registry initialization; sandbox access denied, pytest internal error, exit 3. No test result is attributed to this attempt. |
| Attributable original baseline | `20261030T170557-58408-588825`: all four original targets failed with `production transition authority bytes drifted for src/optimus/acp/lifecycle.py`; 4 failed, exit 1, 11.09 seconds. |
| First repaired delivery-module run | `20261030T170819-49912-e957c4`: 46 passed, 2 failed, exit 1, 176.01 seconds. Introduced test errors were an overlay line incorrectly treated as merged line (349 versus 291) and a refusal patch naming the removed live `_placeholder_settlement` method. Corrected the line-anchor check and patched the actual adapter constructor. This failed run remains separate evidence. |
| Pre-review focused validation | `20261030T171210-18704-ba776d`: 61 passed, 0 skipped, exit 0, 320.64 seconds: delivery module 48, binding-manifest controls 7, profile identity/selection controls 4, historical replay/non-execution controls 2. |
| Docs-index validation | `.venv/Scripts/python.exe -m pytest --no-cov tests/unit/docs/test_docs_index.py`; `20261030T172047-30768-f527c9`: 7 passed, 0 skipped, exit 0, 1.15 seconds. This separate run checked the new report and README index entry, with the same Python and inventory bytes as the 61-test run. |
| Static checks | `.venv/Scripts/python.exe -m ruff check .` and `git diff --check` passed. `git diff --exit-code -- src tools reports tests/fixtures docs/decisions` passed. |

The attributable baseline used this exact target set:

```powershell
.venv/Scripts/python.exe -m pytest --no-cov tests/unit/acp/test_plan1126_delivery_contract.py::test_delivery_contract_model_1000_seed_schedule tests/unit/acp/test_plan1126_delivery_contract.py::test_h4_execution_emits_only_citations_for_behaviors_it_runs tests/unit/acp/test_plan1126_delivery_contract.py::test_h4_literal_scenarios_are_coherent_primary_transitions tests/unit/acp/test_plan1126_delivery_contract.py::test_h4_behavioral_mutations_change_or_invalidate_primary_observation
```

The first repaired run used `.venv/Scripts/python.exe -m pytest --no-cov tests/unit/acp/test_plan1126_delivery_contract.py`. The pre-review 61-test focused command was:

```powershell
.venv/Scripts/python.exe -m pytest --no-cov tests/unit/acp/test_plan1126_delivery_contract.py tests/unit/tools/test_plan1126_unrun_binding.py tests/unit/tools/test_test_profiles.py::test_the_manifest_classifies_the_whole_default_selection_with_no_dead_rule tests/unit/tools/test_test_profiles.py::test_every_measured_slow_node_has_an_explicit_rule tests/unit/tools/test_test_profiles.py::test_every_selection_declaration_still_names_something tests/unit/tools/test_test_profiles.py::test_current_source_guards_are_gates_or_audit_current tests/unit/tools/plan1126_runtime_audit/test_current_measurement.py::test_historical_verification_and_rendering_execute_no_probe tests/unit/tools/plan1126_runtime_audit/test_current_measurement.py::test_the_replay_carrier_reads_every_family_and_refuses_a_gap
```

The final two controls verify/render the actual unchanged sealed artifact with every current probe refused and check every stored observation family's counts and missing-evidence refusals. Profile checks collect the default selection; they do not execute a broad suite. Binding controls cover both object-present execution and object-absent attributed UNRUN semantics without changing this checkout's object store.

Raw logs and native records are retained as local archival provenance, not repository dependencies. Attributable baseline log SHA-256: `02788d750ed498ecdbc6d48a024d9dab8869d65f3778ce353a43c860b70fa8b3`; first module log: `8830b2a9f13384e4625dfcb3b57a923a008f669692e125f80029673155af0a01`; pre-review validation log: `47b1e1984b42f11308cbfa0842579cb9b5b493181469c0b5bed2ddee02b003dd`; pre-review native terminal record: `056d20877aa917084f88073ccd43a13ea9a817c44c04c7cd4e4674ccba4cde84`.

The docs-index run tested report v1 SHA-256 `099148cb48a8b4b7c676e2ecc8c8d31af87376e60fbbddd59ce5c8e0e1abd2db` and README SHA-256 `cfbe58f7be7233638d0cd615885a7b4c87e73a99ed77e09ef0da1a3376634921`. Report v1 and candidate patch v1 SHA-256 `a3e09a59ba86ad4a09e779b1d7f935f12109d43c66967a66e1af9dcf6e2a1557` remain preserved. Report v2 then corrected the fixed-versus-literal scenario wording and added the docs result/source distinction; it adds no link or changes to indexed filenames. These prose-only additions were not part of the earlier test runs. Docs log SHA-256: `f3c605af3cebce938f72f4f0909ac93ede157282f2587e6352a1b0012a3144e1`; docs native terminal record: `599cb47bef0cf5db5f272cc761ab667aeab2ffc78a7ee77f73d9759a1862702b`.

## Consolidated review-fix validation

Candidate v2 patch SHA-256 `90f50a856bd733f6acff535f11eecca740cf54933add49a2393a3b6c6b8bf021`, report SHA-256 `831cb432dc04982919f414f9886053f9e21a885c309d81bf08a60c6b49d3158f`, manifest and all three test/inventory files were preserved before this fix wave. The pre-review 61-test and 7-test results above remain bound to their earlier source bytes.

The read-only false-attribution diagnostic mutated only historical conversation text and invoked the old control's historical authority path. Its actual refusal named `src/optimus/acp/lifecycle.py`; the old broad matcher returned true and the intended conversation-path matcher returned false. Exit 0 means this diagnostic confirmed the attribution defect, not that a runtime characterization passed. Diagnostic log SHA-256: `8c03aaa11a4defab3f1b3772a78f47a1f782066330022f6a7b2fc8dfb3d4b080`.

The consolidated delta strengthens that existing negative control, restores explicit declared primary-authority membership with a valid-but-unrelated definition counterexample, requires each exact citation-refusal reason, removes the three untimed new IDs from the measurement snapshot, and explains their conservatively retained scheduling. Report corrections distinguish sealed-row rebuild equality from independent source authentication and describe the approved historical-execution helper's current lifecycle refusal without changing its policy. The scope is four migrated tests plus one strengthened existing negative control; production safeguards and the 37-node skip contract remain unchanged.

The narrow validation command was:

```powershell
.venv/Scripts/python.exe -m pytest --no-cov tests/unit/acp/test_plan1126_delivery_contract.py::test_delivery_contract_model_1000_seed_schedule tests/unit/acp/test_plan1126_delivery_contract.py::test_h4_replayed_citations_match_immutable_definitions tests/unit/acp/test_plan1126_delivery_contract.py::test_h4_sealed_scenarios_preserve_primary_transition_evidence tests/unit/acp/test_plan1126_delivery_contract.py::test_h4_replay_refuses_missing_or_tampered_evidence_without_execution tests/unit/acp/test_plan1126_delivery_contract.py::test_h4_transition_authority_rejects_immutable_byte_drift tests/unit/tools/test_plan1126_unrun_binding.py tests/unit/tools/test_test_profiles.py::test_the_manifest_classifies_the_whole_default_selection_with_no_dead_rule tests/unit/tools/test_test_profiles.py::test_every_measured_slow_node_has_an_explicit_rule tests/unit/tools/test_test_profiles.py::test_every_selection_declaration_still_names_something tests/unit/tools/test_test_profiles.py::test_current_source_guards_are_gates_or_audit_current tests/unit/docs/test_docs_index.py
```

Run `20261030T173224-57540-ed05f2`: **22 passed, 1 failed, 0 skipped**, exit 1, 48.93 seconds. The strengthened path-attribution control, binding/profile/docs checks and other migrated controls passed. The citation control failed because pytest assertion rewriting appends expression diagnostics after the explicit error message, defeating an end-of-entire-string regex anchor. This failed run and its complete source snapshot remain preserved. Its delivery module SHA-256 is `44a5f359402f61aecc898995aaa133ba13b63818e49d07eeecad408d685e2452`; report tested by its docs checks is `9efe4f757112aec96c157f228a55c002b81482fef37b43a8803c6781b085da39`. Log SHA-256: `8b67a6bc246e743f2ae4b21435e362af0e86a9d34d410ff8cac9f980d795076e`; native terminal record: `0d85e8f798af84eabecd2e22b3c6ff0660bf9f6d8b66a7d0eac815a6273d7dbb`.

The only subsequent Python delta adds multiline regex mode to the two exact reason-line matchers. The complete explicit message remains anchored; appended pytest diagnostics no longer invalidate it. The exact citation-node rerun was `.venv/Scripts/python.exe -m pytest --no-cov tests/unit/acp/test_plan1126_delivery_contract.py::test_h4_replayed_citations_match_immutable_definitions`. Run `20261030T173357-7480-99c671`: **1 passed, 0 skipped**, exit 0, 3.70 seconds, including path/line/symbol/digest and genuine-unrelated-definition refusals. The other 22 passing checks were not rerun or relabelled as testing later bytes. Both fix-round runs have active/default-selection, valid native, full guard protection, COMPLETE records and parent UNKNOWN qualifications as above.

Final delivery module SHA-256: `6133dd2f395711888cb155e95fca34d2792eb73c73d1b741ba077db25519b5c4`; final profiles SHA-256: `bb72cfeb4a0fd419d5e43c974e47ce27a7742f2a6279a05078f702c58c2e1377`. The binding manifest and README retain their earlier hashes. Citation-rerun log SHA-256: `e6919efaaae0c1408d539a3c163cd468e8c6bee8d5d723a0307c477be6793769`; native terminal record: `c02abf1966d748ee85d382cf58e241843ff4d2eec46d805298a4ad918064bf0b`. Ruff, diff checks and unchanged production/evidence checks passed after the regex correction. This result/source metadata was appended afterward; it changes no links or indexed filenames and is not part of the preceding docs-test source.

No manual broad/full suite, coverage gate, alternate-OS run, live service, provider call or fresh historical schedule execution was performed for this repair. Normal final integration/publication hooks are a separate source-bound run; these focused results must not be relabelled as full-suite, coverage, final-integrated-tree or renewed historical runtime evidence.
