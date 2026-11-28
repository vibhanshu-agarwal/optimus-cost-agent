# Repeatability attribution evidence

The #306 report covers 35 sealed shutdown observations. The original 14 timeouts retain their split of 10 HARNESS and four UNRESOLVED. Product repeatability for this history is INDETERMINATE.

- The `optimus-repeatability-input-v1` input retains the original outcomes and provenance.
- The `optimus-repeatability-manifest-v1` manifest binds the input digest, complete cohort identities, attribution references and residual decisions.
- The disposition ledger mirrors the manifest array. The path map binds the finite current controls.
- The [JSON](composite.json) and [Markdown](composite.md) reports represent the same `optimus-repeatability-report-v1` result.

From the repository root, create the parent of an absent output directory. On Windows and compatible Linux filesystems the two reports publish together with one no-replace rename.

```bash
mkdir -p outputs/issue306/local-check
uv run --frozen python tools/report_repeatability_attribution.py \
  --input reports/repeatability-attribution/historical-input.json \
  --manifest reports/repeatability-attribution/historical-manifest.json \
  --output-dir outputs/issue306/local-check/report
```

When the repository is on a Windows volume mounted in WSL, choose an output parent on the Linux filesystem, for example with mktemp -d. The mounted volume can refuse the atomic no-replace directory rename.

Exit 0 publishes a valid pair. Exit 2 publishes an invalid pair for readable data that fails validation. Usage errors and unparseable inputs also return 2. I/O errors return 1. Output stays outside the input and repository reports directories. Reproduction uses only the two supplied files.

The owning issues record the current delivery and closure status.
