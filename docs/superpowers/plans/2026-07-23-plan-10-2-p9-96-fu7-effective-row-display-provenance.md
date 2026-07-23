# Plan 10.2: P9.96-FU-7 Effective-Row Display Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILLS: Use superpowers:executing-plans to execute
> this plan task-by-task and superpowers:test-driven-development for every behavior change.
> Steps use checkbox syntax (- [ ]) for tracking.

**Status:** Frozen after reviewer and operator approval on 2026-07-23. Implementation is authorized;
no source implementation has started.

**Goal:** Close the remaining effective-row display half of P9.96-FU-7 so optimus-trust approve shows
effective provider, provider-key, base-URL, and shared-secret settings with safe provenance, without
changing authorization or security_snapshot_digest behavior.

**Architecture:** Reuse one private environment -> .env.gateway -> keyring lookup helper for provider
and shared-secret provenance. Resolve credentials exactly once as today, compute the existing digest
unchanged, then append a complete, source-labelled effective credential view to the display-row list.
The inherited snapshot view and effective view are intentionally both displayed, so an environment
row and its effective source_class="environment" row may have the same name; the source label makes
the two views explicit rather than silently hiding either one.

**Tech Stack:** Python 3.14+, existing dataclasses and enums, keyring, pathlib, pytest,
pytest-asyncio, pytest-cov, coverage.py, Ruff, and uv. No new dependency.

## Global Constraints

- Baseline is origin/main commit 971c5227db1a326b72f3f544f85907a4457ec3d0.
- The approved design spec is
  docs/superpowers/specs/2026-07-23-plan-10-2-fu7-display-provenance-design.md at SHA-256
  30C0554C720D50E6F2CF198A21627E9441FAEBA9D632C405E90F334964538897.
- Stable custody remains P9.96-FU-7; do not create a new catalog ID or a second Plan 10 backlog
  document.
- Preserve the current branch's user-owned modified uv.lock and untracked .claude/ path. Do not
  stage, revert, regenerate, or otherwise modify either path.
- Work only on agent/codex/plan-10-2-effective-row-display, based directly on latest origin/main.
  Do not fork from the Plan 10.1 feature branch.
- Do not implement source or tests until the reviewer/operator approval record exists and contains
  the final plan SHA-256. This plan is currently a draft; checkbox progress is not implementation
  evidence.
- Do not add fields to ProviderCredentialResolution or LaunchCandidate.
- Preserve the one-key model, gateway-owned provider keys, exact approval comparison, secret
  redaction, child propagation, and fail-closed behavior.
- Reuse existing display callables in LAUNCH_VARIABLE_POLICIES; do not create new masking or
  fingerprint logic.
- Effective rows must compute decision by calling _compute_decision(policy, raw_value) with the same
  policy and raw effective value used for display. Secret rows pass the actual secret only to the
  registered redaction callable; missing secret rows pass an empty string to that same callable.
- The effective display view is complete, even for CredentialLayer.ENVIRONMENT. Do not deduplicate
  environment-sourced effective rows against inherited rows. The inherited row has
  source_class="inherited"; the effective row has source_class="environment".
- Append effective rows only after compute_security_snapshot_digest() returns. Do not change the
  digest function, its arguments, canonicalization, HMAC domains, registry compatibility, or
  approval-record schema.
- The missing provider-key row must always use the fixed synthetic row label provider_api_key and
  the fixed canonical policy OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY; never use
  CredentialProvenance.field_name for output or policy selection in that case.
- No provider API key, shared secret, URI user information, raw digest, HMAC fingerprint, or source
  secret may appear in output, persisted state, or test failure messages.
- Unit tests may use fake keyring backends and temporary files. No live Gateway, Redis, provider
  credential, or project-authored ACP client is permitted in this plan's unit evidence.
- Before implementation sign-off, run affected tests, the default suite, aggregate coverage at the
  repository's 80% gate, Ruff, and git diff --check. If the restricted sandbox denies uv/Python
  caches, rerun the same literal command with approved higher-trust/on-request filesystem mode and
  record the denied paths in the checkpoint log.

## Source Anchors and Current Evidence

- src/optimus/acp/local_gateway_secrets.py:60-71 already defines CredentialProvenance and the three
  provider provenance fields on ProviderCredentialResolution.
- src/optimus/acp/local_gateway_secrets.py:109-123 resolves the shared secret with no provenance.
- src/optimus/acp/launch_gate.py:424-532 builds inherited display rows and digest inputs from the
  immutable environment snapshot.
- src/optimus/acp/launch_gate.py:561-605 resolves provider/shared credentials and folds effective
  values into the digest inputs.
- src/optimus/acp/launch_gate.py:616-621 computes security_snapshot_digest; effective rows must be
  appended after this call and before the final LaunchCandidate return at :627-642.
- src/optimus/acp/launch_policy.py:256-268 defines the existing redacted, literal, and masked-URI
  display functions; :303-347 registers provider-key/shared-secret policies; :405-422 registers
  provider/base URL policies.
- src/optimus/acp/launch_approval_cli.py:264-273 displays tier/name/value/decision but not
  source_class; Plan 10.1's confirmation gate already runs after this display.
- The fixed-input golden digest from unchanged baseline is
  f7af89af0acce664b27825e5af9823c25b11579490bccc73e8f82d4ec316f248 for the exact fixture in Task 4.

## File and Responsibility Map

| File | Responsibility in this plan |
|---|---|
| src/optimus/acp/local_gateway_secrets.py | Extract shared precedence lookup, add shared-secret provenance, preserve value-only wrapper. |
| src/optimus/acp/launch_gate.py | Append effective credential rows after unchanged digest computation. |
| src/optimus/acp/launch_approval_cli.py | Render each row's source_class before Plan 10.1 confirmation. |
| tests/unit/acp/test_local_gateway_secrets.py | Precedence, provenance, wrapper parity, and secret-free resolver tests. |
| tests/unit/acp/test_launch_gate.py | Effective rows, source classes, policy masking, missing-key label, and digest golden test. |
| tests/unit/acp/test_launch_approval_cli.py | Source-class display and no-leak approval output tests. |
| docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md | Reconcile original P9.96-FU-7 after implementation evidence. |
| docs/superpowers/plans/2026-07-01-phase-1-roadmap.md | Add Plan 10.2 status and stable-ID custody link after evidence. |
| README.md | Add concise Plan 10.2 status pointer after evidence. |
| docs/superpowers/reviews/plan-10-2-review-checkpoints.md | Gitignored reviewer/implementation handoff log; never stage. |
| docs/superpowers/reviews/2026-07-23-plan-10-2-implementation-plan-approval.md | Create only after reviewer/operator approval and final plan digest. |

---

### Task 0: Verify allocation, baseline, spec digest, and freeze inputs

**Files:**
- Inspect AGENTS.md, CONTRIBUTING.md, the approved design spec, and source anchors above.
- Create after approval: docs/superpowers/reviews/2026-07-23-plan-10-2-implementation-plan-approval.md.
- Create/update as a gitignored handoff log: docs/superpowers/reviews/plan-10-2-review-checkpoints.md.

**Produces:** Evidence that this plan owns the next unused Plan 10.x slot, is based on current
origin/main, and will be approved against a precise SHA-256 before implementation.

- [ ] Step 1: Verify branch, baseline, and preserved dirty paths.

Run:

~~~powershell
git status --short --branch
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git diff --name-only -- uv.lock
git status --short -- .claude
~~~

Expected: branch agent/codex/plan-10-2-effective-row-display; HEAD and origin/main both equal
971c5227db1a326b72f3f544f85907a4457ec3d0; uv.lock remains modified; .claude/ remains untracked;
no source or test path is dirty.

- [ ] Step 2: Verify Plan 10.2 allocation on current baseline.

Run:

~~~powershell
git ls-tree -r --name-only origin/main docs/superpowers/plans | Select-String -Pattern 'plan-10'
git grep -n -E 'Plan 10\.[0-9]' origin/main -- docs/superpowers/plans README.md
~~~

Expected: only already allocated Plan 10.1 appears as a Plan 10.x path/reference; no Plan 10.2
path or reference exists on origin/main. Do not reserve another number or create a backlog document.

- [ ] Step 3: Verify design-spec digest and baseline tests.

Run:

~~~powershell
(Get-FileHash -Algorithm SHA256 docs/superpowers/specs/2026-07-23-plan-10-2-fu7-display-provenance-design.md).Hash
uv run --frozen pytest -q
~~~

Expected: spec hash is
30C0554C720D50E6F2CF198A21627E9441FAEBA9D632C405E90F334964538897, and the baseline suite reports
1482 passed, 20 skipped, 27 deselected, 1 warning. If restricted sandbox denies
C:\Users\pc\AppData\Local\uv\cache\sdists-v9\.git,
C:\Users\pc\AppData\Roaming\uv\python\.lock, or C:\Users\pc\AppData\Local\Python, rerun the same
command with approved higher-trust access and record the denial and successful result.

- [ ] Step 4: Freeze only after review and operator approval.

After reviewer and operator approval, run:

~~~powershell
(Get-FileHash -Algorithm SHA256 docs/superpowers/plans/2026-07-23-plan-10-2-p9-96-fu7-effective-row-display-provenance.md).Hash
~~~

Create docs/superpowers/reviews/2026-07-23-plan-10-2-implementation-plan-approval.md with the
same structure as Plan 10.1's approval record, using the actual printed plan hash, actual reviewer
approval, actual operator approval, the frozen-plan path, and the mechanical hash command. State
that any byte change invalidates the approval and requires a replacement digest and approvals. Do
not create or claim this record before the named approvals exist.

---

### Task 1: Extract shared credential precedence and expose shared-secret provenance

**Files:**
- Modify src/optimus/acp/local_gateway_secrets.py:80-139.
- Test tests/unit/acp/test_local_gateway_secrets.py.

**Interfaces:**
- Produces _resolve_env_config_keyring(...) -> tuple[str | None, CredentialProvenance].
- Produces resolve_shared_secret_with_provenance(...) -> tuple[str | None, CredentialProvenance].
- Preserves resolve_shared_secret(...) -> str | None as a value-only wrapper.
- Leaves ProviderCredentialResolution and CredentialProvenance field definitions unchanged.

- [ ] Step 1: Add failing precedence/provenance tests.

Add these tests using the file's existing FakeKeyring:

~~~python
@pytest.mark.parametrize(
    ("environment", "dotenv", "keyring_value", "expected", "layer"),
    [
        ("from-env", "from-dotenv", "from-keyring", "from-env", CredentialLayer.ENVIRONMENT),
        ("", "from-dotenv", "from-keyring", "from-dotenv", CredentialLayer.CONFIG_FILE),
        ("", "", "from-keyring", "from-keyring", CredentialLayer.KEYRING),
        ("", "", "", None, CredentialLayer.MISSING),
    ],
)
def test_resolve_shared_secret_with_provenance_reports_precedence(
    tmp_path,
    environment,
    dotenv,
    keyring_value,
    expected,
    layer,
) -> None:
    if dotenv:
        (tmp_path / ".env.gateway").write_text(
            f"OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET={dotenv}\n",
            encoding="utf-8",
        )
    fake_keyring = FakeKeyring()
    if keyring_value:
        fake_keyring.set_password("optimus-cost-agent", "local_gateway_shared_secret", keyring_value)

    environ = {"OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": environment} if environment else {}
    value, provenance = resolve_shared_secret_with_provenance(
        environ,
        config_root=tmp_path,
        keyring_backend=fake_keyring,
    )

    assert value == expected
    assert provenance.layer is layer


def test_resolve_shared_secret_wrapper_returns_provenance_resolver_value(tmp_path) -> None:
    fake_keyring = FakeKeyring()
    fake_keyring.set_password("optimus-cost-agent", "local_gateway_shared_secret", "from-keyring")

    value, provenance = resolve_shared_secret_with_provenance(
        {}, config_root=tmp_path, keyring_backend=fake_keyring
    )

    assert resolve_shared_secret({}, config_root=tmp_path, keyring_backend=fake_keyring) == value
    assert provenance.layer is CredentialLayer.KEYRING
~~~

Import resolve_shared_secret_with_provenance in the test module. Run the RED selector:

~~~powershell
uv run --frozen pytest tests/unit/acp/test_local_gateway_secrets.py -k "shared_secret_with_provenance or wrapper_returns" -q
~~~

Expected: FAIL because the new resolver is not defined.

- [ ] Step 2: Implement the shared lookup helper and resolver.

Add this private helper:

~~~python
def _resolve_env_config_keyring(
    environ: Mapping[str, str],
    *,
    dotenv_values: Mapping[str, str],
    env_name: str,
    keyring_name: str,
    keyring_backend: Any,
) -> tuple[str | None, CredentialProvenance]:
    environment_value = environ.get(env_name, "").strip()
    if environment_value:
        return environment_value, CredentialProvenance(CredentialLayer.ENVIRONMENT, env_name)
    config_value = dotenv_values.get(env_name, "").strip()
    if config_value:
        return config_value, CredentialProvenance(CredentialLayer.CONFIG_FILE, env_name)
    keyring_value = _safe_get_password(keyring_backend, keyring_name)
    if keyring_value:
        return keyring_value, CredentialProvenance(CredentialLayer.KEYRING, keyring_name)
    return None, CredentialProvenance(CredentialLayer.MISSING, env_name)
~~~

Refactor provider provider/API-key/base-URL env/config/keyring lookups to use the helper while
preserving these existing special cases exactly:

- No provider becomes openrouter with DEFAULT provenance.
- No API key remains MISSING with existing alternate-key errors and warnings.
- No base URL becomes the existing concrete resolve_effective_base_url() default with DEFAULT
  provenance.
- Keyring field_name remains its storage name for internal provenance; the display builder never
  prints or uses it as a policy key.

Add:

~~~python
def resolve_shared_secret_with_provenance(
    environ: Mapping[str, str],
    *,
    config_root: Path,
    keyring_backend: Any = keyring,
) -> tuple[str | None, CredentialProvenance]:
    dotenv_values = _parse_env_gateway_file(config_root / ".env.gateway")
    return _resolve_env_config_keyring(
        environ,
        dotenv_values=dotenv_values,
        env_name="OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET",
        keyring_name=_KEY_SHARED_SECRET,
        keyring_backend=keyring_backend,
    )
~~~

Rewrite resolve_shared_secret() as a wrapper returning only the first tuple element. Do not alter
the keyring service, env name, parser, stripping behavior, or _safe_get_password() exception
behavior.

- [ ] Step 3: Run focused resolver tests and existing resolver suite.

Run:

~~~powershell
uv run --frozen pytest tests/unit/acp/test_local_gateway_secrets.py -k "shared_secret" -q
uv run --frozen pytest tests/unit/acp/test_local_gateway_secrets.py -q
uv run --frozen ruff check src/optimus/acp/local_gateway_secrets.py tests/unit/acp/test_local_gateway_secrets.py
~~~

Expected: all shared-secret tests and the full resolver unit module pass; existing provider
precedence, default base URL, alternate-key, and secret-free representation tests remain green;
Ruff is clean.

---

### Task 2: Add effective credential rows after the unchanged digest

**Files:**
- Modify src/optimus/acp/launch_gate.py:31-49, 561-642.
- Test tests/unit/acp/test_launch_gate.py.

**Interfaces:**
- Modify resolve_launch_candidate() to receive
  (resolved_shared_secret, shared_secret_provenance) from the new resolver.
- Add private helper
  _append_effective_credential_display_rows(display_rows, *, provider_credentials, shared_secret,
  shared_secret_provenance) -> None.
- Do not change LaunchDisplayRow, LaunchCandidate, digest arguments, or candidate security maps.

- [ ] Step 1: Add RED tests for complete config, keyring, default, and source-labelled rows.

Add a row filter that preserves duplicates:

~~~python
def _rows(candidate: LaunchCandidate, name: str) -> list[LaunchDisplayRow]:
    return [row for row in candidate.display_rows if row.name == name]
~~~

Add a config-source test with an owner-only .env.gateway containing provider, provider API key,
base URL, and shared secret. Use an empty fake keyring and the existing sample workspace/operator
helpers. Assert that the effective provider, provider-key, base-URL, and shared-secret rows all
have source_class == "config_file". Assert canary provider and shared secrets do not occur in any
display_value.

Add a keyring-source test containing model_provider, model_provider_api_key, and
local_gateway_shared_secret in a fake keyring. Assert the effective provider, provider-key,
base-URL, and shared-secret rows have source_class == "keyring"; every secret display equals
"**********".

Add a default-source test with only OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY in the captured
environment and no provider/base URL. Assert an effective provider row displays openrouter with
source_class == "default", an effective base-URL row displays
https://openrouter.ai/api/v1 with source_class == "default", and the key row is redacted.

Run the RED selectors before production changes:

~~~powershell
uv run --frozen pytest tests/unit/acp/test_launch_gate.py -k "effective_config or effective_keyring or effective_default" -q
~~~

Expected: FAIL because no effective rows are appended.

- [ ] Step 2: Implement the post-digest row helpers.

Add one row-construction helper:

~~~python
def _append_display_row(
    display_rows: list[LaunchDisplayRow],
    *,
    policy_name: str,
    row_name: str,
    raw_value: str,
    provenance: CredentialProvenance,
) -> None:
    policy = LAUNCH_VARIABLE_POLICIES[policy_name]
    display_rows.append(
        LaunchDisplayRow(
            name=row_name,
            tier=policy.tier,
            source_class=provenance.layer.value,
            display_value=policy.display(raw_value),
            decision=_compute_decision(policy, raw_value),
        )
    )
~~~

Add _append_effective_credential_display_rows() with this behavior:

1. If provider_credentials.secrets is present, append provider, canonical provider-key, and base-URL
   rows. Use ANTHROPIC_API_KEY only when secrets.provider == "anthropic"; otherwise use
   OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY. Do not append a base-URL row when secrets.base_url is
   None because Anthropic has no effective base URL.
2. If provider credentials exist but secrets is None and api_key_provenance.layer is
   CredentialLayer.MISSING, append one missing row with policy_name
   OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY, row_name provider_api_key, and raw_value "". This
   fixed policy is safe because both provider-key policies have identical secret-tier,
   redaction, and decision behavior, and output never includes the probed field name.
3. If provider resolution is None because it raised its existing configuration exception, append no
   invented provider/base/API rows.
4. Always append the shared-secret row with policy and row name
   OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET, using shared_secret or "" as raw_value and returned
   provenance. A missing shared secret uses existing fixed redaction and source_class missing.

Call the helper only after the existing snapshot_digest = compute_security_snapshot_digest(...)
call returns and before LaunchCandidate(...) is constructed. Do not add effective rows to any
digest input map. Keep final sort key lambda r: r.name unchanged.

Every effective row, including environment-sourced rows, must call _compute_decision(policy, raw_value).
The duplicate environment rows are intentional and must be asserted in the tests with
source_class values inherited and environment.

- [ ] Step 3: Run effective-row and regression tests.

Run:

~~~powershell
uv run --frozen pytest tests/unit/acp/test_launch_gate.py -k "effective or display or secret_values" -q
uv run --frozen pytest tests/unit/acp/test_launch_gate.py -q
uv run --frozen ruff check src/optimus/acp/launch_gate.py tests/unit/acp/test_launch_gate.py
~~~

Expected: config, keyring, default, masking, inherited, URI, authorization, and existing digest
regression tests pass; effective rows coexist with inherited rows by design; no secret canary is
present in any row; Ruff is clean.

---

### Task 3: Pin missing-key non-disclosure and digest byte identity

**Files:**
- Modify tests/unit/acp/test_launch_gate.py.
- Inspect only src/optimus/acp/launch_approvals.py for the shared digest function.

**Interfaces:**
- No production interface changes beyond Task 2.
- The fixed fixture uses existing _HMAC_KEY and _sample_workspace_identity() helpers.

- [ ] Step 1: Add missing-key provider-family comparison test.

Construct two candidates with identical required agent environment and separate .env.gateway files:
one sets provider anthropic, the other openrouter; neither sets its required provider API key. Use an
empty fake keyring. Select rows with source_class == "missing" and row.name == "provider_api_key";
assert:

~~~python
assert len(anthropic_missing) == 1
assert len(openrouter_missing) == 1
assert anthropic_missing[0] == openrouter_missing[0]
assert "ANTHROPIC_API_KEY" not in repr(anthropic_missing[0])
assert "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY" not in repr(anthropic_missing[0])
assert anthropic_missing[0].display_value == "**********"
~~~

Run:

~~~powershell
uv run --frozen pytest tests/unit/acp/test_launch_gate.py -k "missing or provider" -q
~~~

Expected: the new assertion fails until the fixed synthetic row exists; no existing missing-provider
behavior is changed.

- [ ] Step 2: Add the fixed-input golden digest test.

Use this exact fixture with an empty fake keyring and no .env.gateway file:

~~~python
_GOLDEN_DISPLAY_DIGEST = "f7af89af0acce664b27825e5af9823c25b11579490bccc73e8f82d4ec316f248"
_GOLDEN_ENV = {
    "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
    "OPTIMUS_API_KEY": "agent-key",
    "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
    "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "openrouter",
    "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "provider-key",
    "OPTIMUS_LOCAL_GATEWAY_BASE_URL": "https://api.openrouter.ai/v1",
    "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared-secret",
}
~~~

Wrap launch_gate's compute_security_snapshot_digest call, deep-copy its keyword arguments, and
delegate to the real function. After resolving the candidate, assert:

~~~python
assert candidate.security_snapshot_digest == _GOLDEN_DISPLAY_DIGEST
assert candidate.security_snapshot_digest == compute_security_snapshot_digest(**captured_args)
assert dict(candidate.security_literals) == dict(captured_args["security_literals"])
assert dict(candidate.secret_fingerprints) == dict(captured_args["secret_fingerprints"])
assert any(row.source_class == "environment" for row in candidate.display_rows)
~~~

Also assert effective rows exist for provider, provider key, base URL, and shared secret. Keep the
golden value and fixture in test source; do not calculate the expected value from the candidate.

- [ ] Step 3: Run invariant suite and changed-secret regressions.

Run:

~~~powershell
uv run --frozen pytest tests/unit/acp/test_launch_gate.py -k "golden or digest or missing" -q
uv run --frozen pytest tests/unit/acp/test_launch_gate.py -q
~~~

Expected: golden digest remains exactly
f7af89af0acce664b27825e5af9823c25b11579490bccc73e8f82d4ec316f248; changing a resolved provider
key or shared secret still changes the digest; display-only source labels do not change it.

---

### Task 4: Render source classes and preserve approval ordering

**Files:**
- Modify src/optimus/acp/launch_approval_cli.py:264-273.
- Test tests/unit/acp/test_launch_approval_cli.py.

**Interfaces:**
- _display_candidate(candidate) remains the only display entry point for optimus-trust approve.
- _confirm_approval() remains after _display_candidate(candidate) and before record construction,
  exactly as landed by Plan 10.1.

- [ ] Step 1: Add source-class output test.

Add a focused test using LaunchDisplayRow and SimpleNamespace:

~~~python
def test_display_candidate_prints_source_class(capsys) -> None:
    from types import SimpleNamespace

    from optimus.acp.launch_approval_cli import _display_candidate
    from optimus.acp.launch_gate import LaunchDisplayRow
    from optimus.acp.launch_policy import LaunchVariableTier

    candidate = SimpleNamespace(
        workspace_identity=SimpleNamespace(canonical_path="/tmp/workspace"),
        security_snapshot_digest="a" * 64,
        display_rows=(
            LaunchDisplayRow(
                name="OPTIMUS_LOCAL_GATEWAY_PROVIDER",
                tier=LaunchVariableTier.SECURITY,
                source_class="inherited",
                display_value="openrouter",
                decision="requires exact approval",
            ),
            LaunchDisplayRow(
                name="OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY",
                tier=LaunchVariableTier.SECRET,
                source_class="keyring",
                display_value="**********",
                decision="requires exact HMAC approval",
            ),
        ),
    )

    _display_candidate(candidate)
    output = capsys.readouterr().out
    assert "source: inherited" in output
    assert "source: keyring" in output
    assert "a" * 16 in output
~~~

Run:

~~~powershell
uv run --frozen pytest tests/unit/acp/test_launch_approval_cli.py -k "display_candidate and source" -q
~~~

Expected: FAIL because _display_candidate() currently omits source_class.

- [ ] Step 2: Add source rendering without changing confirmation gate.

After the existing decision line, print one source line for every row:

~~~python
print(f"  {'':>17} source: {row.source_class}")
~~~

Do not print CredentialProvenance.field_name, raw values, or any new digest field. Do not move or
alter _confirm_approval(); final order remains configuration header, all rows and source lines,
blank line, existing confirmation prompt, then record construction.

- [ ] Step 3: Run CLI display, confirmation, and secrecy tests.

Run:

~~~powershell
uv run --frozen pytest tests/unit/acp/test_launch_approval_cli.py -q
uv run --frozen pytest tests/unit/acp/test_launch_approval_cli.py -k "approve or confirmation or display or gateway" -q
uv run --frozen ruff check src/optimus/acp/launch_approval_cli.py tests/unit/acp/test_launch_approval_cli.py
~~~

Expected: source classes render for inherited and effective rows; Plan 10.1 confirmation behavior
remains green; approval output contains no secret, URI-userinfo, digest, or missing-probe canary;
Ruff is clean.

---

### Task 5: Reconcile stable-ID custody and record evidence

**Files:**
- Modify after implementation evidence:
  docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md.
- Modify after implementation evidence:
  docs/superpowers/plans/2026-07-01-phase-1-roadmap.md.
- Modify after implementation evidence: README.md.
- Modify only as a gitignored handoff record:
  docs/superpowers/reviews/plan-10-2-review-checkpoints.md.

**Interfaces:**
- The consolidated backlog remains the sole detailed catalog for P9.96-FU-7.
- The roadmap remains the sequencing/status source; README remains a short pointer.
- No frozen Plan 9.96 security/design document is edited.

- [ ] Step 1: Record task evidence before changing status text.

Append a newest-first checkpoint entry containing each literal verification command, result,
changed-file list, coverage percentage, Ruff result, and implementation commit SHA. Record the
higher-trust baseline path only as environment evidence, not as a repository workaround. Never stage
the checkpoint log.

- [ ] Step 2: Close only the original FU-7 row after tests pass.

Update the existing P9.96 follow-up row to state that the effective-row display provenance gap is
closed by Plan 10.2, while Plan 10.1's confirmation-gate half remains part of the same stable
finding. Name the implementation commit, named tests, frozen plan path, and evidence artifact. Do
not delete Plan 10.1 history or imply that Plan 10.2 changed the approval digest contract.

- [ ] Step 3: Add Plan 10.2 status without closing the Plan 10 pool.

Add a dated Plan 10.2 entry to the roadmap linking this plan, design spec, approval record,
implementation commit, and evidence. Keep the remaining Plan 10 pool tracked and unscheduled.
Update README with one concise sentence pointing to Plan 10.2 and the closed FU-7 effective-row
display gap; do not duplicate the full catalog.

- [ ] Step 4: Verify cross-document custody and scope.

Run:

~~~powershell
rg -n -i "Plan 10\.2|P9\.96-FU-7|effective-row|display provenance" README.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md docs/superpowers/specs/2026-07-23-plan-10-2-fu7-display-provenance-design.md docs/superpowers/plans/2026-07-23-plan-10-2-p9-96-fu7-effective-row-display-provenance.md
git diff --check
git diff --name-only -- docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md
~~~

Expected: original FU-7 row, Plan 10.2 link, and effective-row custody are consistent; diff check is
clean; frozen Plan 9.96 security design has no diff.

---

### Task 6: Repository-wide fitness and final handoff

**Files:**
- Inspect all intentional implementation and documentation changes.
- Modify only docs/superpowers/reviews/plan-10-2-review-checkpoints.md for final evidence; never stage it.

**Produces:** Evidence sufficient for reviewer/operator sign-off and later implementation handoff.

- [ ] Step 1: Run affected unit suites and default suite.

Run:

~~~powershell
uv run --frozen pytest tests/unit/acp/test_local_gateway_secrets.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_launch_approval_cli.py -q
uv run --frozen pytest -q
~~~

Expected: both commands pass. If default sandbox cache access fails, rerun exact commands with
approved higher-trust access and record denied paths and successful results.

- [ ] Step 2: Run coverage, Ruff, and diff hygiene.

Run:

~~~powershell
uv run --frozen pytest --cov=optimus --cov=optimus_gateway --cov=optimus_security --cov-report=term-missing --cov-fail-under=80 -q
uv run --frozen ruff check .
git diff --check
git status --short --branch
~~~

Expected: aggregate coverage is at least 80%, Ruff is clean, diff hygiene is clean, and final status
shows only intentional Plan 10.2 paths plus preserved uv.lock and .claude/ state. Do not stage the
checkpoint log, uv.lock, or .claude/.

- [ ] Step 3: Perform final security and scope audit.

Run:

~~~powershell
rg -n -i "provider_api_key|source_class|_append_effective_credential_display_rows|compute_security_snapshot_digest" src/optimus/acp/local_gateway_secrets.py src/optimus/acp/launch_gate.py src/optimus/acp/launch_approval_cli.py
rg -n -i "ANTHROPIC_API_KEY|OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY|shared-secret|provider-key" tests/unit/acp/test_local_gateway_secrets.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_launch_approval_cli.py
git diff --name-only -- docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md
~~~

Expected: effective rows are post-digest, missing output uses only fixed synthetic label, tests cover
both provider-key policies, and the frozen Plan 9.96 security design is absent from the diff.

- [ ] Step 4: Complete handoff.

Update the checkpoint log with final implementation SHA, frozen-plan SHA, approval-record path, all
passing commands, coverage percentage, Ruff result, golden digest, missing-label result, stable-ID
status, and preserved dirty paths. The implementation agent then presents the exact diff and evidence
for reviewer/operator sign-off. No merge, push, branch deletion, or history rewrite is authorized.

## Definition of Done

- Plan and approval record were digest-pinned before implementation began.
- Provider, base URL, provider API key, and shared secret effective rows display safe values and
  provenance source classes for environment, config file, keyring, default, and missing cases. The
  full effective view intentionally coexists with inherited rows.
- Every effective row has tier, policy-based display value, source class, and decision computed by
  _compute_decision(policy, raw_value).
- Missing provider-key output is the exact fixed provider_api_key row with fixed redaction and is
  identical for Anthropic and non-Anthropic missing cases.
- No provider key, shared secret, URI user information, raw digest, fingerprint, or provenance
  storage name reaches operator output or persisted state.
- security_snapshot_digest is byte-identical to the baseline golden value for the fixed fixture, and
  changing an effective secret still changes the digest as before.
- Plan 10.1 confirmation ordering, child propagation, approval schema, and fail-closed semantics
  remain unchanged.
- Affected tests, default tests, coverage >=80%, Ruff, diff hygiene, and scope audits pass.
- Original P9.96-FU-7 catalog row is closed by Plan 10.2 with named evidence; no new catalog ID or
  Plan 10 backlog document exists.
