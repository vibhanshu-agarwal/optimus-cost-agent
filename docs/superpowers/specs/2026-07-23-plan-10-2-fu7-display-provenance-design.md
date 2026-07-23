# Plan 10.2: P9.96-FU-7 Effective-Row Display Provenance Design

**Status:** Draft for independent review.

**Stable finding:** `P9.96-FU-7`. This plan closes only the remaining effective-row display
provenance half. It does not mint a new catalog ID or create a second Plan 10 backlog document.

**Baseline:** `origin/main` at `971c5227db1a326b72f3f544f85907a4457ec3d0`, which contains the
landed Plan 10.1 confirmation gate. The dedicated drafting branch is
`agent/codex/plan-10-2-effective-row-display`.

## Goal

Make `optimus-trust approve` display every effective local-Gateway credential setting that will
be used by an authorized launch, including values resolved from the environment, `.env.gateway`,
the OS keyring, or a built-in default. Preserve the existing secret masking, exact authorization,
and security-snapshot digest behavior byte-for-byte.

## Problem and Evidence

`resolve_launch_candidate()` currently creates `LaunchDisplayRow` objects by scanning only the
captured inherited environment. It separately resolves provider credentials and the shared secret
from the environment, `.env.gateway`, and keyring, and already folds those resolved values into
the security digest before calling `compute_security_snapshot_digest()`. Consequently, the
authorization digest covers effective credentials, but the approval ceremony can omit the provider,
provider API key, base URL, or shared secret that the Gateway will actually consume.

The current code already provides the required provenance model:

- `CredentialLayer` has `environment`, `config_file`, `keyring`, `default`, and `missing` values.
- `CredentialProvenance` records the source layer and the source field/key name.
- `ProviderCredentialResolution` already carries `provider_provenance`, `api_key_provenance`, and
  `base_url_provenance`; its dataclass shape does not need new fields.
- `ProviderSecrets` carries the effective provider, API key, and resolved concrete base URL when a
  complete provider credential set exists.
- `LAUNCH_VARIABLE_POLICIES` already owns the display callables for provider, provider-key,
  Anthropic key, base URL, and shared secret.

The missing provenance capability is the shared-secret equivalent of the provider resolver. The
existing `resolve_shared_secret()` must be refactored around one shared environment → `.env.gateway`
→ keyring lookup helper, and a new `resolve_shared_secret_with_provenance()` must expose both its
value and `CredentialProvenance` without changing the compatibility behavior of
`resolve_shared_secret()`.

## Scope

### In scope

- A private, shared precedence helper in `src/optimus/acp/local_gateway_secrets.py` returning a
  resolved value and its `CredentialProvenance`.
- `resolve_shared_secret_with_provenance()` plus the existing value-only wrapper.
- Effective display rows in `resolve_launch_candidate()` for complete provider credentials and the
  shared secret, appended only after the existing security digest is computed.
- A fixed generic missing-provider-key row when the provider resolver reports a missing API key.
  The row must not reveal whether the resolver probed `ANTHROPIC_API_KEY` or
  `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY`.
- `source_class` rendering in `_display_candidate()` for inherited and effective rows.
- Unit tests for precedence, provenance, masking, missing-value non-disclosure, source rendering,
  and digest identity.
- Documentation and status reconciliation after implementation evidence is complete, while keeping
  the original `P9.96-FU-7` catalog row open until the implementation lands.

### Explicit exceptions

- No new fields are added to `ProviderCredentialResolution` or `LaunchCandidate`.
- No changes are made to `security_snapshot_digest` inputs, canonicalization, HMAC domains,
  registry compatibility, approval-record schema, or authorization comparison.
- No new masking function is created. Every non-missing effective row uses the display callable
  already registered for its canonical policy field.
- No provider key, shared secret, URI user information, raw digest, fingerprint, or source secret is
  printed, persisted, or included in a display row.
- No source or test implementation begins before the frozen plan has a digest-pinned reviewer and
  operator approval record.
- No new stable catalog ID, Plan 10 backlog document, live Gateway dependency, Redis dependency, or
  project-authored ACP client is introduced.

## Design

### 1. Shared credential lookup and provenance

Add a private lookup helper with the following behavior:

```python
def _resolve_env_config_keyring(
    environ: Mapping[str, str],
    *,
    dotenv_values: Mapping[str, str],
    env_name: str,
    keyring_name: str,
    keyring_backend: Any,
) -> tuple[str | None, CredentialProvenance]:
    ...
```

The helper strips values and checks exactly this order:

1. `environ[env_name]`, returning `CredentialLayer.ENVIRONMENT` and `env_name`.
2. `dotenv_values[env_name]`, returning `CredentialLayer.CONFIG_FILE` and `env_name`.
3. `_safe_get_password(keyring_backend, keyring_name)`, returning `CredentialLayer.KEYRING` and
   `keyring_name`.
4. No value, returning `None` and `CredentialLayer.MISSING` with `env_name`.

Provider resolution reuses this helper while preserving its current semantics: an absent provider
becomes the built-in `openrouter` value with `CredentialLayer.DEFAULT`; an absent base URL becomes
the shared concrete provider default with `CredentialLayer.DEFAULT`; an absent API key remains
`CredentialLayer.MISSING`. Existing alternate-key validation, provider/key pairing warnings, and
provider configuration exceptions remain unchanged.

Implement the new shared-secret resolver as:

```python
def resolve_shared_secret_with_provenance(
    environ: Mapping[str, str],
    *,
    config_root: Path,
    keyring_backend: Any = keyring,
) -> tuple[str | None, CredentialProvenance]:
    ...
```

It parses `.env.gateway` once, delegates precedence to the shared helper using
`OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET` and the existing `local_gateway_shared_secret` keyring
entry, and returns the tuple. Keep this compatibility wrapper:

```python
def resolve_shared_secret(...) -> str | None:
    value, _provenance = resolve_shared_secret_with_provenance(...)
    return value
```

This prevents the display path from maintaining a second precedence implementation and keeps
existing callers that need only the secret value unchanged.

### 2. Effective display-row construction

`resolve_launch_candidate()` continues to scan inherited values and resolve credentials exactly as
it does today. Replace only the shared-secret call with the provenance-returning resolver and keep
the resolved value used by the current digest block unchanged.

The existing sequence must remain structurally visible:

```python
snapshot_digest = compute_security_snapshot_digest(
    security_literals=security_literals,
    secret_fingerprints=secret_fingerprints,
    workspace_digest=workspace_identity.digest,
    registry_version=LAUNCH_POLICY_COMPATIBILITY,
)

# Only after the digest has been returned:
_append_effective_credential_display_rows(...)
```

The new row helper mutates only the local `display_rows` list. It does not mutate
`security_literals`, `secret_fingerprints`, `monotonic_grants`, or any candidate field used by the
digest. The final `display_rows` tuple remains sorted by row name as it is today.

For a complete `provider_credentials.secrets` result, append these effective rows:

| Effective setting | Canonical policy field | Row value | Source class |
|---|---|---|---|
| Provider | `OPTIMUS_LOCAL_GATEWAY_PROVIDER` | `ProviderSecrets.provider` | `provider_provenance.layer.value` |
| Provider API key | `ANTHROPIC_API_KEY` for Anthropic, otherwise `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY` | The secret value passed only to that policy’s existing display callable | `api_key_provenance.layer.value` |
| Base URL | `OPTIMUS_LOCAL_GATEWAY_BASE_URL` | `ProviderSecrets.base_url` | `base_url_provenance.layer.value` |

For the shared secret, append `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET` using the value and
provenance returned by `resolve_shared_secret_with_provenance()`. Its existing `_display_redacted`
callable is always used; a missing value is passed through the same fixed redaction behavior and is
marked with `source_class="missing"`.

When the provider resolver returns no complete `ProviderSecrets` object but its API-key provenance
is `CredentialLayer.MISSING`, append exactly one generic missing-key row. Use the fixed row label
`provider_api_key` and the existing canonical provider-key policy only for tier, decision, and
display callable selection. Do not use `api_key_provenance.field_name` as the row label, display
value, or any output text. The resulting row must have a fixed, non-informative redacted display,
`source_class="missing"`, and no provider-specific key-name oracle.

If provider resolution raises its existing configuration exception and therefore returns `None`, do
not invent provider or base-URL values; preserve the current fail-closed launch behavior and the
raw inherited rows already produced by the registry scan.

### 3. Policy-driven masking and CLI output

The row builder selects the policy by the canonical field name and invokes its existing display
callable:

- `OPTIMUS_LOCAL_GATEWAY_PROVIDER` → literal display.
- `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY` or `ANTHROPIC_API_KEY` → redacted display.
- `OPTIMUS_LOCAL_GATEWAY_BASE_URL` → URI-userinfo-masked display.
- `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET` → redacted display.

Do not use `CredentialProvenance.field_name` to select a policy for keyring-sourced credentials;
that field contains the keyring storage name rather than the effective environment policy name.

Update `_display_candidate()` so every row prints its `source_class` in addition to tier, name,
display value, and decision. Existing inherited rows therefore render `inherited`, while effective
rows render `environment`, `config_file`, `keyring`, `default`, or `missing`. The CLI never prints
the provenance field name itself.

### 4. Digest identity invariant

The implementation must not move, rewrite, or broaden the digest computation. The digest is based
only on the existing security literal and secret-fingerprint maps, workspace digest, and registry
compatibility version. Effective display rows are presentation metadata and are appended after the
digest function returns.

Tests must establish both sides of the invariant for one fixed snapshot:

1. Capture the exact digest arguments at the shared digest call boundary.
2. Assert the candidate digest equals the digest recomputed from that captured argument set.
3. Assert the fixed-input digest matches the golden value produced by the unchanged `origin/main`
   implementation.
4. Assert the effective rows are present and additive, while the captured digest arguments and
   candidate security maps are unchanged.

Changing a resolved key, shared secret, provider, or base URL must still change the digest exactly
as it did before this plan. Changing only provenance source labels or display-row construction must
not change it.

## Verification Design

### Unit tests: `tests/unit/acp/test_local_gateway_secrets.py`

- Verify the new shared-secret resolver returns the environment value and `ENVIRONMENT` provenance
  over `.env.gateway` and keyring values.
- Verify `.env.gateway` provenance wins over keyring when the environment is empty.
- Verify keyring provenance is returned when only the keyring contains the secret.
- Verify the missing result returns `(None, CredentialLayer.MISSING)` without exposing the keyring
  storage name in a user-facing value.
- Verify the existing value-only wrapper returns exactly the tuple’s value for all four cases.
- Preserve existing tests for provider provenance, provider-key alternate-name behavior, base-URL
  defaults, and secret-free representations.

### Unit tests: `tests/unit/acp/test_launch_gate.py`

- Resolve a complete provider configuration from `.env.gateway` and assert effective provider,
  API-key, base-URL, and shared-secret rows carry `config_file` provenance.
- Resolve the same complete configuration from a fake keyring and assert `keyring` provenance.
- Omit provider and base URL while supplying the generic provider key and assert the effective
  provider and concrete base URL display rows carry `default` provenance.
- Assert all provider-key and shared-secret display values are the registered fixed redaction and
  never contain canary secrets; assert base-URL URI user information remains masked.
- Exercise a missing API key with both provider families and assert the row label and display are
  identical, fixed, and contain neither `ANTHROPIC_API_KEY` nor
  `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY`.
- Capture the digest call arguments and assert the golden fixed-input digest, candidate security
  maps, and digest remain unchanged while effective rows are appended.

### Unit tests: `tests/unit/acp/test_launch_approval_cli.py`

- Assert `_display_candidate()` prints `source: inherited` for existing rows and the correct
  `source: config_file`, `source: keyring`, or `source: default` for effective rows.
- Assert approval output contains no provider-key, shared-secret, URI-userinfo, raw digest, or
  missing-probe canary.
- Keep Plan 10.1’s confirmation-gate tests unchanged and verify the new display lines occur before
  the existing confirmation prompt.

### Fitness gates

Before implementation sign-off, run the affected unit suites, the repository default suite,
aggregate coverage at the repository’s 80% threshold, Ruff, and `git diff --check`. The baseline
captured for this drafting lane is:

```text
uv run --frozen pytest -q
1482 passed, 20 skipped, 27 deselected, 1 warning in 40.25s
```

The baseline required higher-trust filesystem access because the restricted sandbox denied:
`C:\Users\pc\AppData\Local\uv\cache\sdists-v9\.git`,
`C:\Users\pc\AppData\Roaming\uv\python\.lock`, and
`C:\Users\pc\AppData\Local\Python`.

No live Gateway, Redis, provider credential, or project-authored ACP client is needed for these
unit tests. Any future live-tier evidence must use the dependency named by its tier and the
independently authored `acpx` client where ACP protocol evidence is required.

## File Responsibility Map

| File | Responsibility |
|---|---|
| `src/optimus/acp/local_gateway_secrets.py` | Shared precedence helper, provenance-returning shared-secret resolver, and compatibility wrapper reuse. |
| `src/optimus/acp/launch_gate.py` | Post-digest effective credential-row construction without changing digest inputs. |
| `src/optimus/acp/launch_approval_cli.py` | Render `source_class` for every already-safe display row. |
| `tests/unit/acp/test_local_gateway_secrets.py` | Resolver precedence and provenance contracts. |
| `tests/unit/acp/test_launch_gate.py` | Effective-row, masking, missing-placeholder, and digest invariants. |
| `tests/unit/acp/test_launch_approval_cli.py` | Source-class output and approval-display secrecy. |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Update the original `P9.96-FU-7` row after implementation evidence; no new ID. |
| `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` | Link Plan 10.2 and reconcile the remaining FU-7 disposition after evidence. |
| `README.md` | Add a concise Plan 10.2 status pointer after evidence. |
| `docs/superpowers/reviews/plan-10-2-review-checkpoints.md` | Gitignored reviewer/implementation handoff log; never stage. |

## Definition of Done for the Later Frozen Plan

- Effective rows identify environment, `.env.gateway`, keyring, default, or missing source class.
- Provider, base URL, API key, and shared secret rows are present whenever a complete effective
  credential set exists; missing API-key output is fixed and provider-name independent.
- Existing registered display functions provide all masking; no secret or URI user information is
  exposed.
- The digest computation and its inputs are unchanged, and a fixed-input golden digest is byte-
  identical to `origin/main`.
- Existing approval, child propagation, and fail-closed semantics remain unchanged.
- Affected tests, default tests, coverage, Ruff, and diff hygiene pass.
- The original `P9.96-FU-7` catalog row records this implementation as the owner of the effective-row
  display gap; no new stable ID or Plan 10 backlog document is created.
