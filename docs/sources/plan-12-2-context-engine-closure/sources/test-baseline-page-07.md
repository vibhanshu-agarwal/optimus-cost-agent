# 8A. Coverage policy and shared gate interface

coverage.py with pytest-cov is the canonical line/branch engine. Use one identified full-suite dataset, including unloaded tracked production files from every top-level src/ package, regular or namespace. Focused datasets cannot substitute. The all-source aggregate is informational.

| Product group | Exactly-once members | Floor / disposition |
|---|---|---|
| Optimus | optimus, optimus_gateway, optimus_security, optimus_model_policy | 80% enforced group |
| Context Engine | context_engine | 80% enforced package/group |
| Evidence Handoff | evidence_handoff, evidence_handoff_runtime | 80% informational; enforcement deferred |

Independently enforce optimus_model_policy at 80% in addition to its Optimus group. This extra report does not create duplicate ownership. Inventory comes from Git’s tracked-file index, not a filesystem walk. Reject missing/duplicate/stale/unmapped groups, top-level src modules with no package ownership, inconsistent coverage sources, missing unloaded files and missing/stale datasets. Native package patterns must not match a similarly named neighbor.

The comparison uses coverage.py/pytest-cov should_fail_under at configured precision 0: round(measured_percentage, 0) < 80 fails. 79.5% compares as 80% and passes; 79.0% fails. Print and retain both measured and compared percentages. This preserves the existing comparison, rather than claiming an unrounded 80% boundary.

Implemented interface at cf9bb9d:
```text
tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json <report.json>
tools/check_product_coverage.py --data-file <full-run-data> --run-record <report.run.json> --groups tools/product-coverage-groups.json --report-json <report.json>
```

Exactly one mode is required. Run mode invokes sys.executable -m pytest once with --cov --cov-branch --cov-fail-under=0 --cov-report=term-missing -q, preserving repository addopts/run-context and the true pytest exit. No nested uv or narrowed selection. It writes <report>.run.json with schema, HEAD, dirty flag, fixed command, times, true exit and dataset SHA-256. Report mode never reruns tests and rejects a dataset that does not match its record hash. A nonzero suite exit fails the gate even when floors pass. Required floor failures also fail; informational rows retain BELOW but do not fail the wrapper. The wrapper calls coverage’s reporting/comparison API, not additional coverage CLI subprocesses; therefore no per-row process exit is claimed.

The sidecar is provenance for a trusted recorded run, not an authenticated artifact, a dirty-tree digest or a complete configuration snapshot. Reuse only with the corresponding reviewed full-run log/run context and unchanged source/configuration. Verify those externally when accepting a sealed dataset; do not infer full selection or changed-configuration validity from the hash alone. The current final clean-candidate datasets were independently checked in evidence-verification.json.

Until the profiles lane lands, the hook entry is unchanged and keeps pyproject fail_under=80 (an Optimus-only interim floor). Only CI switches to --run-full-suite. The profiles lane later moves the hook to commit with no coverage gate. The released final CP4 gate also uses run mode. Retain hook ID optimus-pytest-coverage, optimus-check: pytest-coverage and existing ADR-016 skip custody; no new ad hoc waiver. Shared source-scope custody remains HARDENING-ITEM-COVERAGE-SOURCE-SCOPE.

CI’s rows survive in the step log. JSON report upload is not implemented and is not a claimed retained artifact. No new Evidence Handoff tests are required for informational coverage.
