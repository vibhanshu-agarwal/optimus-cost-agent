# Plan 9.99 Security Design Approval Record

**Status:** Reviewer-agent approved on 2026-07-22; operator approval pending.

**Contract:** `docs/superpowers/specs/2026-07-22-plan-9-99-credential-uri-security-snapshot-canonicalization-design.md`

**Frozen SHA-256:** `B2B236EEF191EC74046A9FF32EA63F91A08E6519BA30ADF8FA3599F4DBC77CF8`

## Approvals

- **Reviewer-agent:** Approved on 2026-07-22 after independently verifying the scope ruling against
  the live `LAUNCH_VARIABLE_POLICIES` registry (confirming three SECURITY-tier `_URL`-named entries
  plus the unmasked `_resolved_base_url` path, rather than trusting the finding's prose), verifying the
  sorted-key digest mechanics that make userinfo presence/absence detectable via fingerprint-key
  presence, requiring the original-text `rpartition("@")` slicing technique (rather than
  `urlunparse`/`parsed.hostname`/`parsed.port` reconstruction) after empirically reproducing a real
  IPv6-bracket-loss and host-case-folding bug in the existing `mask_uri_userinfo`, confirming the
  `_project_child_env` raw-propagation path is unaffected by normalization, and identifying the
  additional `run-gateway` literal base-URL print (`launch_approval_cli.py:564`) as in-scope.
- **Operator:** Pending.

## Freeze Semantics

Any byte change to the contract invalidates this approval and requires a new digest, reviewer-agent
approval, operator approval, and replacement approval record before implementation planning may
continue. This approval authorizes creation and review of the Plan 9.99 implementation plan; it does
not authorize implementation.

## Mechanical Verification

Run from the repository root:

```powershell
(Get-FileHash -Algorithm SHA256 `
  docs/superpowers/specs/2026-07-22-plan-9-99-credential-uri-security-snapshot-canonicalization-design.md).Hash
```

Expected exact output:

```text
B2B236EEF191EC74046A9FF32EA63F91A08E6519BA30ADF8FA3599F4DBC77CF8
```
