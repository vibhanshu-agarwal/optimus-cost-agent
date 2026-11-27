# Repeatability attribution

This report describes supplied observations. Supported facts on an INVALID input do not establish aggregate acceptance.
A historical PASS or a terminal residual disposition does not establish stable product behavior.

- Input SHA-256: d5b0bddaea80ece66e5e35e401a2927847fa62b5c4c701ff480a820a276b16de
- Manifest SHA-256: f7de6ce22d2568c3a681751bccc9246318048574b2d09496f0e9eaed414bf675
- Selection: Historically accepted complete generation c18-latest-complete-v1. Narrow 10 and group 25. Other generations remain separate.

## Cohort results

| Scope | Input | Observations | PASS | FAIL | TIMEOUT | ERROR | HARNESS | UNRESOLVED | Harness instability | Product variability | Product repeatability |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| Overall | VALID | 35 | 21 | 0 | 14 | 0 | 10 | 4 | true | false | INDETERMINATE |
| group | VALID | 25 | 15 | 0 | 10 | 0 | 8 | 2 | true | false | INDETERMINATE |
| narrow | VALID | 10 | 6 | 0 | 4 | 0 | 2 | 2 | true | false | INDETERMINATE |

## Observations

| Observation | Cohort | Repeat | Outcome | Subject | Original timeout subject | Evidence kind | Valid row |
| --- | --- | ---: | --- | --- | --- | --- | --- |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-01 | group | 1 | PASS | NONE | — | NONE | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-02 | group | 2 | TIMEOUT | HARNESS | HARNESS | DECLARED\_HARNESS\_NODE\_MATCH | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-03 | group | 3 | PASS | NONE | — | NONE | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-04 | group | 4 | TIMEOUT | HARNESS | HARNESS | DECLARED\_HARNESS\_NODE\_MATCH | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-05 | group | 5 | PASS | NONE | — | NONE | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-06 | group | 6 | PASS | NONE | — | NONE | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-07 | group | 7 | TIMEOUT | HARNESS | HARNESS | DECLARED\_HARNESS\_NODE\_MATCH | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-08 | group | 8 | PASS | NONE | — | NONE | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-09 | group | 9 | TIMEOUT | HARNESS | HARNESS | DECLARED\_HARNESS\_NODE\_MATCH | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-10 | group | 10 | PASS | NONE | — | NONE | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-11 | group | 11 | TIMEOUT | HARNESS | HARNESS | DECLARED\_HARNESS\_NODE\_MATCH | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-12 | group | 12 | PASS | NONE | — | NONE | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-13 | group | 13 | TIMEOUT | HARNESS | HARNESS | DECLARED\_HARNESS\_NODE\_MATCH | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-14 | group | 14 | PASS | NONE | — | NONE | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-15 | group | 15 | TIMEOUT | HARNESS | HARNESS | DECLARED\_HARNESS\_NODE\_MATCH | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-16 | group | 16 | PASS | NONE | — | NONE | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-17 | group | 17 | PASS | NONE | — | NONE | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-18 | group | 18 | TIMEOUT | UNRESOLVED | UNRESOLVED | ACCEPTED\_LEGACY\_UNRESOLVED | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-19 | group | 19 | PASS | NONE | — | NONE | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-20 | group | 20 | PASS | NONE | — | NONE | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-21 | group | 21 | TIMEOUT | HARNESS | HARNESS | DECLARED\_HARNESS\_NODE\_MATCH | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-22 | group | 22 | PASS | NONE | — | NONE | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-23 | group | 23 | PASS | NONE | — | NONE | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-24 | group | 24 | TIMEOUT | UNRESOLVED | UNRESOLVED | ACCEPTED\_LEGACY\_UNRESOLVED | true |
| task11-group-task6\_shutdown\_group-c18-latest-complete-v1-repeat-25 | group | 25 | PASS | NONE | — | NONE | true |
| task11-narrow-task6\_shutdown-c18-latest-complete-v1-repeat-01 | narrow | 1 | PASS | NONE | — | NONE | true |
| task11-narrow-task6\_shutdown-c18-latest-complete-v1-repeat-02 | narrow | 2 | PASS | NONE | — | NONE | true |
| task11-narrow-task6\_shutdown-c18-latest-complete-v1-repeat-03 | narrow | 3 | TIMEOUT | UNRESOLVED | UNRESOLVED | ACCEPTED\_LEGACY\_UNRESOLVED | true |
| task11-narrow-task6\_shutdown-c18-latest-complete-v1-repeat-04 | narrow | 4 | PASS | NONE | — | NONE | true |
| task11-narrow-task6\_shutdown-c18-latest-complete-v1-repeat-05 | narrow | 5 | PASS | NONE | — | NONE | true |
| task11-narrow-task6\_shutdown-c18-latest-complete-v1-repeat-06 | narrow | 6 | TIMEOUT | UNRESOLVED | UNRESOLVED | ACCEPTED\_LEGACY\_UNRESOLVED | true |
| task11-narrow-task6\_shutdown-c18-latest-complete-v1-repeat-07 | narrow | 7 | PASS | NONE | — | NONE | true |
| task11-narrow-task6\_shutdown-c18-latest-complete-v1-repeat-08 | narrow | 8 | TIMEOUT | HARNESS | HARNESS | DECLARED\_HARNESS\_NODE\_MATCH | true |
| task11-narrow-task6\_shutdown-c18-latest-complete-v1-repeat-09 | narrow | 9 | PASS | NONE | — | NONE | true |
| task11-narrow-task6\_shutdown-c18-latest-complete-v1-repeat-10 | narrow | 10 | TIMEOUT | HARNESS | HARNESS | DECLARED\_HARNESS\_NODE\_MATCH | true |

## Ancillary dispositions

| ID | Preserved verdict | Decision | Owner | Decision source | Disposition |
| --- | --- | --- | --- | --- | --- |
| D1 | TIMEOUT / UNRESOLVED (four rows) | ACCEPTED | #306 | operator | Accept these four named historical observations as terminal accepted-unresolved residuals for #306/#321 after their immutable per-row reporting ships. This explicitly substitutes risk acceptance for resolving their cause: the active test exercises Optimus shutdown, so a possible product shutdown hang remains an accepted unknown risk. Preserve TIMEOUT/UNRESOLVED, do not rank them as attributed product defects, and make no stable-product or root-cause claim. No repeat campaign is authorized. |
| D2 | Original Git timeout failure and later isolated PASS | ACCEPTED | #306 | operator | Accept the historical audit-Git cause as unresolved, with the recovered failed hook and later isolated attempt retained separately, conditional on #306's bounded failure-path controls passing. No missing-data waiver is requested. The original legacy attempt lacks modern run/native context; no retrospective completeness claim follows. Do not increase the per-subprocess10-second bound or authorize historical retries. |
| D3 | Historical coverage varied. ADR-017 criterion NOT MET with its exact accepted residual. | ACCEPTED | #306 | operator | Accept the recovered historical coverage variation as not causally resolved. Keep ADR-017 limited to its four statements and exact head. Close #306's forward-control obligation only after every varied statement/arc in the three saved datasets maps to the listed current deterministic behavior/negative controls and those controls pass. No missing-data waiver, later-head numeric waiver, claim of exhaustive variability across all possible runs, coverage union or new sampling campaign is approved. |
| D4 | ERROR / INVALID\_CAPTURE / UNKNOWN | ACCEPTED | #287 | operator | Accept #287's original H5 event as terminal accepted-unresolved, with diagnostics delivered but historical cause unestablished. Permit this residual disposition to satisfy the CAND-5 closure obligation after #306 ships its retained ledger. No retry, loaded run, claim of repair or Phase 1 working-agent sign-off follows. Issue closure/publication requires separate authorization. |
| D5 | Cancellation group 24 PASS / 1 FAIL, FLAKY | ACCEPTED | #306 | operator | Accept cancellation of a still-running request task when reader EOF is observed as intended transport-loss behavior for this disposition, consistent with \`tests/unit/acp/test\_stdio\_ndjson.py::test\_serve\_ndjson\_eof\_cancels\_pending\_requests\_and\_closes\_owned\_state\_once\`. Existing physical-write ownership/drain limits remain unchanged. The original product FLAKY observation is retained as history with this semantic disposition; the response-before-EOF test change is not evidence of a product fix. |
| D6 | Open unscheduled ambient lookup work | ACCEPTED | #232 | operator | Retain unrelated ambient lookups as open, unscheduled scope under #232, with the next gate a bounded site inventory and separately authorized owning issue before implementation. Accept #306/#321 closure as per-observation repeatability delivery only; no ambient-elimination claim follows. |
