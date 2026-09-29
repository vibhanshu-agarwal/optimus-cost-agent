# Plan 9.99: Credential URI Security-Snapshot Canonicalization

**Status:** Design approved in review; implementation plan draft pending approval.

**Raised:** 2026-07-18 by the Plan 9.98 v6 security audit.

**Owner:** Plan 9.99. This work must land before Plan 9.96 closes.

## Goal

Correct the Plan 9.96 launch-trust handling of credential-bearing URI values so that
URI userinfo is never displayed or persisted, while changing only URI userinfo still
invalidates the security snapshot and requires fresh approval.

## Finding and scope

The v6 finding is structural: SECURITY-tier URI values currently enter
`security_literals` only after `mask_uri_userinfo()`, which makes the digest
insensitive to userinfo-only changes. `OPTIMUS_GATEWAY_URL` and
`OPTIMUS_LOCAL_GATEWAY_BASE_URL` also use literal display, and the resolved provider
base URL is assigned directly to `_resolved_base_url`, allowing raw URI userinfo to
enter the durable approval record.

The four in-scope value sources are:

1. `OPTIMUS_GATEWAY_URL`;
2. `OPTIMUS_REDIS_URL`;
3. `OPTIMUS_LOCAL_GATEWAY_BASE_URL`; and
4. the resolved provider base URL stored under `_resolved_base_url`.

The scope is value-kind based, not a fixed three-variable or four-field allowlist.
Registry URI values must declare their URI behavior explicitly, and the registry test
must reject a SECURITY-tier name ending in `_URL` or `_URI` when that declaration is
missing. The resolved provider base URL uses the same shared recording helper through
its synthetic field name.

## Frozen-contract constraints

- Preserve the Plan 9.96 one-key and Gateway-only credential model.
- Preserve the immutable launch snapshot and exact candidate/approval digest seam.
- Preserve raw effective URI values in the authorized child propagation path; URI
  canonicalization applies only to approval, display, and persistence metadata.
- Never write literal URI userinfo into `security_literals`, display rows, approval
  records, logs, or direct operator output.
- Do not add an `ApprovalRecord` field or change its schema shape.
- Do not migrate or reinterpret existing `P9.96-v1` approval records. They become
  incompatible and require fresh approval.
- Do not change Redis, Gateway, provider credential, or manifest transport behavior
  for authorized launches merely to canonicalize approval metadata.
- Do not include real credentials, usernames, passwords, or credential-bearing URIs
  in this specification, tests' committed fixtures, or evidence artifacts.

## Design

### 1. Shared URI canonicalization

Add a shared result type and helper in `src/optimus_security/sanitization.py`:

```python
@dataclass(frozen=True)
class CredentialUriCanonicalization:
    normalized_uri: str
    display_uri: str
    userinfo_present: bool
```

The helper parses the already validated, stripped URI once and returns:

- `normalized_uri`: the URI with the complete userinfo authority component removed;
- `display_uri`: the URI with that component replaced by the fixed
  `**********` marker; and
- `userinfo_present`: whether a userinfo component exists.

Presence detection must use parser-field presence, not truthiness:

```python
parsed.username is not None or parsed.password is not None
```

This treats all five required credential-bearing shapes as present:

| Shape | Presence result | Display behavior |
|---|---:|---|
| `scheme://user:pass@host` | `True` | `scheme://**********@host` |
| `scheme://@host` | `True` | `scheme://**********@host` |
| `scheme://:pass@host` | `True` | `scheme://**********@host` |
| `scheme://user:@host` | `True` | `scheme://**********@host` |
| `scheme://user@host` | `True` | `scheme://**********@host` |
| `scheme://host` | `False` | unchanged |

For a URI with no userinfo, both returned strings equal the stripped input. For a URI
with userinfo, the helper preserves the non-userinfo authority, path, query, and
fragment text while removing or replacing only userinfo. It must preserve bracketed
IPv6 authority syntax and must not reconstruct host/port from `parsed.hostname` in a
way that changes valid non-userinfo text. The implementation must locate the userinfo
substring in the original stripped authority (for example with `netloc.rpartition("@")`)
and slice or replace only that substring; it must not round-trip through
`urlunparse`, `parsed.hostname`, or `parsed.port` for the canonicalized output.

`mask_uri_userinfo()` delegates to this helper and returns `display_uri`. This fixes
the current implementation/docstring mismatch deliberately: display output carries
an explicit fixed marker, while approval persistence uses the credential-free
`normalized_uri`.

### 2. Registry metadata and security recording

Extend the frozen `LaunchVariablePolicy` dataclass with explicit URI metadata, such as
`uri_userinfo: bool`, and set it for the three registry URI variables. Their display
function becomes URI-safe and their approval descriptor becomes `exact_hmac_uri`.

Add an executable registry test in
`tests/unit/acp/test_launch_policy.py`:

```text
test_every_url_named_security_variable_declares_uri_userinfo
```

The test iterates `LAUNCH_VARIABLE_POLICIES` and fails when a SECURITY-tier name
ending in `_URL` or `_URI` does not set `uri_userinfo=True`. The launch path uses the
explicit metadata rather than name matching.

Add one shared recording helper in `src/optimus/acp/launch_gate.py`, called from both
the registry-driven SECURITY-tier loop and the resolved-provider block:

```text
record_security_value(
    field_name,
    value,
    uri_userinfo,
    security_literals,
    secret_fingerprints,
    hmac_key,
)
```

For non-URI values it preserves the existing literal behavior. For URI values it:

1. stores `normalized_uri` under the ordinary `security_literals[field_name]` key;
2. detects presence using the shared helper's `userinfo_present` result;
3. when present, computes a keyed HMAC of the complete stripped raw URI; and
4. stores that fingerprint under the exact key:

   ```text
   f"{field_name}::uri_userinfo"
   ```

The same string is passed as `compute_secret_fingerprint(..., field_name=...)`, so
the map key and HMAC domain are deterministic and explicit. When userinfo is absent,
that key is absent. The existing sorted-key digest computation therefore distinguishes
both userinfo changes and userinfo presence/absence transitions without persisting
userinfo.

The resolved provider base URL block calls this helper with:

```text
field_name = "_resolved_base_url"
uri_userinfo = True
```

It must no longer assign `resolved.base_url` directly to `security_literals`.

The raw resolved URL remains in `ProviderSecrets.base_url` and the authorized child
environment because the Gateway transport needs the effective value. This is an
intentional transport/persistence boundary; the raw value does not enter approval
metadata or operator display.

### 3. Compatibility and approval behavior

Set:

```text
LAUNCH_POLICY_COMPATIBILITY = "P9.99-v1"
```

This is the load-bearing invalidation mechanism: any stored `P9.96-v1` approval fails
the existing compatibility check and requires fresh approval.

Advance the digest domain from `security-snapshot-v2` to `security-snapshot-v3` as
cryptographic namespace defense-in-depth. The digest walk itself is unchanged; the
domain bump documents that the semantic representation of URI values changed. It is
not relied on as the stored-approval invalidation mechanism.

Keep `APPROVAL_SCHEMA_VERSION = 1` and all existing `security_literals` and
`secret_fingerprints` fields. No record migration is permitted.

### 4. Operator display

The registry-driven approval display uses the URI-safe policy display function. The
separate `optimus-trust run-gateway` path in
`src/optimus/acp/launch_approval_cli.py` must call `mask_uri_userinfo()` before printing
the resolved base URL. The raw value remains available to the authorized Gateway
transport path but is never printed.

## Files and responsibilities

| File | Responsibility |
|---|---|
| `src/optimus_security/sanitization.py` | Shared URI canonicalization result/helper and safe display wrapper. |
| `src/optimus/acp/launch_policy.py` | Explicit URI metadata and URI-safe policy display descriptors. |
| `src/optimus/acp/launch_gate.py` | One shared security-value recording helper used for registry and `_resolved_base_url`. |
| `src/optimus/acp/launch_approvals.py` | `P9.99-v1` compatibility and `security-snapshot-v3` domain. |
| `src/optimus/acp/launch_approval_cli.py` | Safe `run-gateway` base-URL display. |
| `tests/unit/security/test_sanitization.py` | Five userinfo shapes, no-userinfo stability, marker behavior, and URI preservation. |
| `tests/unit/acp/test_launch_policy.py` | Registry-wide URI metadata invariant. |
| `tests/unit/acp/test_launch_gate.py` | Four-source digest sensitivity, presence transitions, child propagation, and authorization regression. |
| `tests/unit/acp/test_launch_approvals.py` | Compatibility rejection and serialized-record integrity/size behavior. |
| `tests/unit/acp/test_launch_approval_cli.py` | Direct `run-gateway` display leak prevention. |
| `tests/integration/acp/test_launch_trust_flow.py` | Real candidate-to-approval-to-authorization URI flow. |

No changes are expected in `src/optimus/acp/local_gateway_secrets.py`,
`src/optimus/acp/local_infra.py`, or `src/optimus_security/launch_manifest.py` because
the authorized raw transport value must remain unchanged. Any test of those paths is
limited to proving raw child propagation remains intact.

## Verification strategy

### Unit coverage

Tests must include:

- full, bare-empty, password-only, empty-password, and username-only userinfo;
- no-userinfo URI unchanged behavior;
- userinfo-only mutation for each registry URI source;
- userinfo presence/absence transitions for each registry URI source;
- `_resolved_base_url` resolution from operator configuration;
- deterministic `field_name::uri_userinfo` fingerprint keys;
- distinct fingerprints for distinct raw URI values;
- bracketed IPv6 authority such as `scheme://user:pass@[::1]:port/path`, with brackets
  intact in both normalized and display output;
- mixed-case host such as `scheme://user:pass@MyHost.EXAMPLE.com`, with host casing
  preserved through normalization;
- a distinctive URI-userinfo leak canary absent from every affected display row,
  `candidate.security_literals`, serialized approval JSON, and `run-gateway` output;
- raw `snapshot.values`, `ProviderSecrets.base_url`, and Gateway-facing environment
  values unchanged;
- identical candidate/record inputs still authorize;
- a `P9.96-v1` approval rejected after the compatibility bump.

### Integration and repository gates

The implementation must run the focused security/ACP tests, the ACP launch-trust
integration test, the full pytest suite with the repository coverage threshold, Ruff,
and `git diff --check`. No live Redis, Gateway credential, or ACPX session is required:
the changed claims are pure canonicalization, HMAC, serialization, display, and
authorization behavior, while transport preservation is proven by exact string
equality.

## Acceptance criteria

1. All four in-scope URI sources use the same canonicalization and recording helper.
2. No raw URI userinfo appears in display output, security literals, approval records,
   or direct `run-gateway` output.
3. Changing only URI userinfo always changes the security snapshot digest.
4. Adding or removing URI userinfo always changes the security snapshot digest.
5. Non-credential URI values preserve their existing display and digest behavior.
6. Identical new candidate and approval inputs authorize successfully.
7. Existing `P9.96-v1` approvals fail closed with policy incompatibility and require
   re-approval under `P9.99-v1`.
8. Raw authorized child propagation and Gateway transport values remain unchanged.
9. Focused tests, full tests, coverage, Ruff, and diff checks pass.
10. No code, plan, approval record, environment file, or unrelated working-tree change
    is modified outside the files listed in this specification.

## Risks and mitigations

- **Empty userinfo bypass:** use `is not None` detection and test `scheme://@host`.
- **Digest/display divergence:** use one canonicalizer and one launch-gate recording
  helper; policy display delegates to the same canonicalizer.
- **Future URI policy omission:** enforce the registry-wide `_URL`/`_URI` invariant.
- **Approval replay under old semantics:** bump `P9.99-v1` and reject old records.
- **Transport regression:** keep raw `ProviderSecrets.base_url` and child environment
  values unchanged and assert exact equality in tests.
- **Credential persistence through test artifacts:** use only synthetic canaries and
  assert their absence from serialized and displayed outputs.
