# Plan 9.99: Credential URI Security-Snapshot Canonicalization Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make every credential-bearing SECURITY-tier URI display-safe and persistence-safe while ensuring URI-userinfo changes and presence transitions invalidate the Plan 9.99 security snapshot.

**Architecture:** Add one original-text URI canonicalizer in src/optimus_security/sanitization.py, expose explicit URI metadata through the launch policy registry, and route both registry values and _resolved_base_url through one launch-gate recording helper. Store normalized credential-free URI literals plus keyed URI fingerprints in the existing approval maps; preserve raw values only in the authorized child transport path.

**Tech Stack:** Python >=3.14, urllib.parse, frozen dataclasses, keyed HMAC-SHA-256, canonical JSON approval records, pytest, pytest-cov, coverage.py, Ruff, and uv.

## Global Constraints

- The four current value sources are OPTIMUS_GATEWAY_URL, OPTIMUS_REDIS_URL, OPTIMUS_LOCAL_GATEWAY_BASE_URL, and resolved _resolved_base_url; implementation must use value-kind metadata rather than a fixed allowlist.
- Presence detection is parsed.username is not None or parsed.password is not None, including scheme://@host.
- URI canonicalization locates userinfo in the original stripped authority and slices or replaces only that substring; it must not reconstruct output through urlunparse, parsed.hostname, or parsed.port.
- normalized_uri removes userinfo; display_uri replaces userinfo with **********; no raw userinfo enters display rows, security_literals, approval JSON, logs, or direct run-gateway output.
- URI-userinfo fingerprint keys are exactly f"{field_name}::uri_userinfo"; the HMAC input is the complete stripped raw URI and the same key is the HMAC field name.
- LAUNCH_POLICY_COMPATIBILITY becomes exactly P9.99-v1; the security snapshot domain becomes security-snapshot-v3; APPROVAL_SCHEMA_VERSION remains 1.
- Raw effective URI values remain unchanged in LaunchEnvironmentSnapshot, ProviderSecrets.base_url, child environments, and authorized Gateway transport.
- No ApprovalRecord fields, serialized schema shape, migration path, or Gateway manifest transport behavior may be added or changed.
- Test canaries are synthetic only and must never be real credentials or local credential values.
- Use TDD: add or update a failing test, run it to prove the failure, make the minimum implementation change, then rerun focused tests and Ruff.
- Do not edit frozen Plan 9.96 files, Plan 9.96 approval records, uv.lock, .claude/, or unrelated user changes.
- Execute implementation only from a dedicated branch/worktree created from the latest main, following CONTRIBUTING.md; do not stack this work on the current Plan 9.98 branch.
- Do not commit, push, or create a PR without explicit user authorization; stop at the final verification handoff with the tested changes unstaged.

## Explicit Exceptions

- This plan changes the launch-policy compatibility version and therefore intentionally invalidates existing P9.96-v1 approvals; no old-record migration is permitted.
- The URI canonicalizer changes mask_uri_userinfo display behavior from dropping userinfo to showing the fixed ********** marker, as required by the approved security design.
- Hardcoded P9.96-v1 strings in unrelated manifest/audit fixture tests remain unchanged when they test arbitrary manifest/audit values rather than LAUNCH_POLICY_COMPATIBILITY; update only tests that assert the live compatibility constant or the new approval behavior.
- No live Redis, Gateway credential, or ACPX evidence is required for this plan; the changed claims are deterministic canonicalization, HMAC, display, serialization, authorization, and raw-value preservation.

---

## File Map

| File | Responsibility |
|---|---|
| src/optimus_security/sanitization.py | Original-text URI canonicalization and safe mask_uri_userinfo wrapper. |
| src/optimus/acp/launch_policy.py | Required uri_userinfo metadata on policy registrations and URI-safe policy display descriptors. |
| src/optimus/acp/launch_gate.py | Shared _record_security_value helper and registry/resolved-URL integration. |
| src/optimus/acp/launch_approvals.py | P9.99-v1 compatibility and security-snapshot-v3 digest namespace. |
| src/optimus/acp/launch_approval_cli.py | Safe resolved base-URL output for optimus-trust run-gateway. |
| tests/unit/security/test_sanitization.py | Five userinfo shapes, IPv6/case preservation, and display/normalization behavior. |
| tests/unit/acp/test_launch_policy.py | Registry-wide URI metadata invariant. |
| tests/unit/acp/test_launch_gate.py | Four-source digest transitions, canary absence, raw propagation, and authorization regressions. |
| tests/unit/acp/test_launch_approvals.py | Compatibility rejection, digest namespace, and serialized approval behavior. |
| tests/unit/acp/test_launch_approval_cli.py | Direct run-gateway output redaction. |
| tests/integration/acp/test_launch_trust_flow.py | Candidate/record/authorization integration with credential-bearing URI values. |
| docs/superpowers/specs/2026-07-22-plan-9-99-credential-uri-security-snapshot-canonicalization-design.md | Approved security design; byte-stable after plan approval. |
| docs/superpowers/reviews/plan-9-99-review-checkpoints.md | Gitignored reviewer handoff log; never stage it. |

## Implementation Tasks

### Task 1: Add the original-text credential URI canonicalizer

Files:
- Modify: src/optimus_security/sanitization.py
- Test: tests/unit/security/test_sanitization.py

Interfaces:
- Produces CredentialUriCanonicalization(normalized_uri: str, display_uri: str, userinfo_present: bool).
- Produces canonicalize_credential_uri(uri: str) -> CredentialUriCanonicalization.
- Keeps mask_uri_userinfo(uri: str) -> str as the public wrapper returning display_uri.

- [x] Step 1: Write the failing canonicalizer tests

Add a parameterized test covering every required authority shape:

~~~python
@pytest.mark.parametrize(
    ("uri", "normalized", "display", "present"),
    [
        ("redis://user:pass@host:6379/0", "redis://host:6379/0", "redis://**********@host:6379/0", True),
        ("redis://@host:6379/0", "redis://host:6379/0", "redis://**********@host:6379/0", True),
        ("redis://:pass@host:6379/0", "redis://host:6379/0", "redis://**********@host:6379/0", True),
        ("redis://user:@host:6379/0", "redis://host:6379/0", "redis://**********@host:6379/0", True),
        ("redis://user@host:6379/0", "redis://host:6379/0", "redis://**********@host:6379/0", True),
        ("redis://host:6379/0", "redis://host:6379/0", "redis://host:6379/0", False),
    ],
)
def test_canonicalize_credential_uri_preserves_presence_and_display(uri: str, normalized: str, display: str, present: bool) -> None:
    result = canonicalize_credential_uri(uri)
    assert result.normalized_uri == normalized
    assert result.display_uri == display
    assert result.userinfo_present is present
~~~

Add explicit regression tests:

~~~python
def test_canonicalize_credential_uri_preserves_ipv6_brackets() -> None:
    result = canonicalize_credential_uri("redis://user:pass@[::1]:6379/0")
    assert result.normalized_uri == "redis://[::1]:6379/0"
    assert result.display_uri == "redis://**********@[::1]:6379/0"


def test_canonicalize_credential_uri_preserves_mixed_case_host() -> None:
    result = canonicalize_credential_uri("redis://user:pass@MyHost.EXAMPLE.com/0")
    assert result.normalized_uri == "redis://MyHost.EXAMPLE.com/0"
    assert result.display_uri == "redis://**********@MyHost.EXAMPLE.com/0"
~~~

Retain the no-userinfo mask_uri_userinfo test and assert byte-for-byte equality. Import the new type and helper before implementation so the first run fails.

- [x] Step 2: Run the canonicalizer tests to verify failure

Run:

~~~bash
uv run pytest tests/unit/security/test_sanitization.py -q
~~~

Expected: FAIL during collection or assertions because canonicalize_credential_uri and CredentialUriCanonicalization do not exist and the current masking helper drops the marker.

- [x] Step 3: Implement the minimum original-text canonicalizer

Add the frozen result type and helper. The implementation must:

1. strip only surrounding whitespace;
2. parse once with urlparse to determine parsed.netloc and use parsed.username is not None or parsed.password is not None;
3. when userinfo exists, split the original parsed.netloc with rpartition("@") and replace only that authority substring in the original stripped URI;
4. preserve IPv6 brackets, host case, port spelling, path, query, fragment, and other non-userinfo bytes; and
5. return the stripped input unchanged when userinfo is absent.

Change mask_uri_userinfo to return canonicalize_credential_uri(uri).display_uri. Do not call urlunparse, parsed.hostname, or parsed.port in the new output path.

- [x] Step 4: Run the canonicalizer tests to verify success

Run:

~~~bash
uv run pytest tests/unit/security/test_sanitization.py -q
~~~

Expected: all sanitization tests pass, including all five userinfo forms, the bare-empty case, IPv6 brackets, mixed-case host, and no-userinfo identity.

- [x] Step 5: Run the task lint gate

Run:

~~~bash
uv run ruff check src/optimus_security/sanitization.py tests/unit/security/test_sanitization.py
~~~

Expected: clean Ruff result.

### Task 2: Make URI handling explicit in the launch policy registry

Files:
- Modify: src/optimus/acp/launch_policy.py
- Test: tests/unit/acp/test_launch_policy.py

Interfaces:
- LaunchVariablePolicy gains required uri_userinfo: bool metadata.
- _register requires the same keyword so every policy entry is explicit.
- The three current URL entries set uri_userinfo=True; every other policy sets False.

- [x] Step 1: Write the failing registry invariant test

Add this test beside test_every_policy_has_parser_display_approval_and_propagation:

~~~python
def test_every_url_named_security_variable_declares_uri_userinfo() -> None:
    for name, policy in LAUNCH_VARIABLE_POLICIES.items():
        if policy.tier == LaunchVariableTier.SECURITY and (name.endswith("_URL") or name.endswith("_URI")):
            assert policy.uri_userinfo is True, f"URI policy metadata missing for {name}"
~~~

Also extend the existing all-policy test to assert isinstance(policy.uri_userinfo, bool).

- [x] Step 2: Run the registry tests to verify failure

Run:

~~~bash
uv run pytest tests/unit/acp/test_launch_policy.py -q
~~~

Expected: FAIL because LaunchVariablePolicy has no uri_userinfo field and registrations do not provide the required metadata.

- [x] Step 3: Add required URI metadata to every registration

Add the required frozen dataclass field and make _register require the uri_userinfo: bool keyword argument for every registration. Set uri_userinfo=True and URI-safe display/approval descriptors for:

~~~text
OPTIMUS_GATEWAY_URL
OPTIMUS_REDIS_URL
OPTIMUS_LOCAL_GATEWAY_BASE_URL
~~~

Set uri_userinfo=False for every non-URI registration. Do not use a launch-path condition such as "url" in name.lower().

- [x] Step 4: Run the registry tests to verify success

Run:

~~~bash
uv run pytest tests/unit/acp/test_launch_policy.py -q
~~~

Expected: all registry, fail-closed, parser, and policy metadata tests pass.

- [x] Step 5: Run the task lint gate

Run:

~~~bash
uv run ruff check src/optimus/acp/launch_policy.py tests/unit/acp/test_launch_policy.py
~~~

Expected: clean Ruff result.

### Task 3: Route registry and resolved URLs through one security recorder

Files:
- Modify: src/optimus/acp/launch_gate.py
- Test: tests/unit/acp/test_launch_gate.py

Interfaces:
- Add private _record_security_value(*, field_name: str, value: str, uri_userinfo: bool, security_literals: dict[str, str], secret_fingerprints: dict[str, str], hmac_key: bytes) -> None.
- The helper mutates only the two maps supplied by the caller and never returns raw URI data.
- The URI fingerprint map key and HMAC field name are exactly f"{field_name}::uri_userinfo".

- [x] Step 1: Write failing four-source digest and leak-canary tests

Add parameterized candidate tests for each registry URI variable. For each source, construct candidates for:

~~~text
scheme://host:port/path
scheme://user:old-pass@host:port/path
scheme://user:new-pass@host:port/path
scheme://@host:port/path
~~~

Assert that the no-userinfo normalized literal is equal to the with-userinfo normalized literal, that the fingerprint key is absent/present as appropriate, that old/new fingerprints and digests differ, and that the synthetic canary is absent from candidate security_literals and all display row values.

Add the same transition test for _resolved_base_url by creating two owner-only .env.gateway files with the same provider/key and different synthetic URI userinfo, then resolving each with the existing fake keyring seam. Assert the raw candidate.provider_credentials.secrets.base_url remains the configured effective value while the normalized approval literal is credential-free.

Add a child-propagation regression asserting candidate.inherited.values, candidate.agent_environ, and candidate.provider_credentials.secrets.base_url retain the raw effective URI. Add a record-building test that serializes the candidate approval and asserts the URI canary is absent from the complete JSON string.

- [x] Step 2: Run the launch-gate tests to verify failure

Run:

~~~bash
uv run pytest tests/unit/acp/test_launch_gate.py -q
~~~

Expected: FAIL because the current gate masks URI literals without adding a userinfo fingerprint, directly stores _resolved_base_url, and cannot satisfy the new transition/canary assertions.

- [x] Step 3: Implement the shared recorder and integrate both call sites

Implement _record_security_value so that:

~~~text
if uri_userinfo is False:
    security_literals[field_name] = value.strip()
else:
    canonical = canonicalize_credential_uri(value)
    security_literals[field_name] = canonical.normalized_uri
    if canonical.userinfo_present:
        key = f"{field_name}::uri_userinfo"
        secret_fingerprints[key] = compute_secret_fingerprint(
            value.strip(), field_name=key, hmac_key=hmac_key
        )
~~~

Replace the current SECURITY-tier "url" in name.lower() branch with the helper using policy.uri_userinfo. Replace the direct _resolved_base_url assignment with the same helper using field_name="_resolved_base_url" and uri_userinfo=True. Remove imports that are no longer used.

- [x] Step 4: Run the launch-gate tests to verify success

Run:

~~~bash
uv run pytest tests/unit/acp/test_launch_gate.py -q
~~~

Expected: all candidate resolution, authorization, digest-transition, canary, and raw-child-propagation tests pass.

- [x] Step 5: Run the task lint gate

Run:

~~~bash
uv run ruff check src/optimus/acp/launch_gate.py tests/unit/acp/test_launch_gate.py
~~~

Expected: clean Ruff result.

### Task 4: Version the approval contract and reject legacy records

Files:
- Modify: src/optimus/acp/launch_approvals.py
- Test: tests/unit/acp/test_launch_approvals.py
- Test: tests/unit/acp/test_launch_gate.py

Interfaces:
- LAUNCH_POLICY_COMPATIBILITY == "P9.99-v1".
- compute_security_snapshot_digest uses the security-snapshot-v3 domain.
- APPROVAL_SCHEMA_VERSION == 1 remains unchanged.

- [x] Step 1: Write failing compatibility and digest-version tests

Add a current-version assertion:

~~~python
def test_plan_999_compatibility_version_is_current() -> None:
    assert LAUNCH_POLICY_COMPATIBILITY == "P9.99-v1"
~~~

Add a legacy-record test using the existing fake keyring and sample record helpers: build a valid current record, replace its policy_compatibility with "P9.96-v1", recompute its record HMAC with the test key, write it to the store, then assert read_durable() raises ApprovalError with code POLICY_MISMATCH.

Add a digest regression that computes the same input twice and asserts byte-identical output, while a URI-userinfo fingerprint value or key change produces a different digest. Do not assert a hardcoded digest tied to a canary.

- [x] Step 2: Run approval tests to verify failure

Run:

~~~bash
uv run pytest tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py -q
~~~

Expected: FAIL because the compatibility constant and digest domain remain at their Plan 9.96 values.

- [x] Step 3: Update only the compatibility and digest namespace

Change the constant and digest domain exactly as specified. Keep the sorted security_literals and secret_fingerprints serialization, HMAC field list, schema version, size limit, and deserialization structure unchanged.

- [x] Step 4: Run approval and launch-gate tests to verify success

Run:

~~~bash
uv run pytest tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py -q
~~~

Expected: current records authorize, legacy records fail with POLICY_MISMATCH, and all existing record integrity/size/one-shot tests pass.

- [x] Step 5: Run the task lint gate

Run:

~~~bash
uv run ruff check src/optimus/acp/launch_approvals.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py
~~~

Expected: clean Ruff result.

### Task 5: Redact the direct run-gateway base-URL display

Files:
- Modify: src/optimus/acp/launch_approval_cli.py
- Test: tests/unit/acp/test_launch_approval_cli.py

Interfaces:
- Direct run-gateway output prints mask_uri_userinfo(provider_secrets.base_url) when a base URL exists.
- ProviderSecrets.base_url, the child environment, and serialized Gateway manifest transport remain raw and unchanged.

- [x] Step 1: Write the failing output leak-canary test

Extend TestRunGatewayCommand with a successful synthetic .env.gateway case whose base URL contains a distinctive synthetic userinfo canary. Capture stdout around _cmd_run_gateway() while keeping the existing fake subprocess/keyring seams. Assert:

~~~python
output = captured_stdout.getvalue()
assert canary not in output
assert "**********" in output
~~~

Also assert the captured child environment or manifest transport still contains the raw effective base URL where the current transport contract requires it; distinguish display redaction from transport normalization.

- [x] Step 2: Run the CLI test to verify failure

Run:

~~~bash
uv run pytest tests/unit/acp/test_launch_approval_cli.py::TestRunGatewayCommand -q
~~~

Expected: FAIL because the current code prints provider_secrets.base_url literally.

- [x] Step 3: Apply the display-only fix

Import mask_uri_userinfo and change only the display expression. Do not modify manifest construction, child environment construction, provider credential resolution, or subprocess arguments.

- [x] Step 4: Run the CLI tests to verify success

Run:

~~~bash
uv run pytest tests/unit/acp/test_launch_approval_cli.py -q
~~~

Expected: all CLI tests pass and the synthetic URI userinfo canary is absent from direct operator output.

- [x] Step 5: Run the task lint gate

Run:

~~~bash
uv run ruff check src/optimus/acp/launch_approval_cli.py tests/unit/acp/test_launch_approval_cli.py
~~~

Expected: clean Ruff result.

### Task 6: Prove end-to-end candidate and approval behavior with URI credentials

Files:
- Modify: tests/integration/acp/test_launch_trust_flow.py

Interfaces:
- Use the existing real candidate -> approval-record -> keyring-store -> authorize_launch() seams.
- Use only synthetic in-memory/fake-keyring data; no live Redis, Gateway, or ACPX process is introduced.

- [x] Step 1: Write the failing integration regressions

Add one test that authors a durable approval for a candidate containing a credential-bearing URI, independently re-resolves the identical URI, and asserts authorization succeeds. Add a second test that changes only URI userinfo after authoring and asserts authorize_launch() raises LaunchGateError with code SNAPSHOT_MISMATCH before any audit or child side effect. Assert the serialized record and audit-safe fields contain no canary.

- [x] Step 2: Run the integration selectors to verify failure

Run:

~~~bash
uv run pytest tests/integration/acp/test_launch_trust_flow.py -q
~~~

Expected: the new userinfo mutation or serialization assertions fail against the current masking-only implementation.

- [x] Step 3: Align the integration fixtures with the completed implementation

Use the existing _real_launch_pipeline() and build_approval_record() helpers. Do not stub resolve_launch_candidate(), authorize_launch(), digest computation, or record HMAC verification. Keep synthetic URI canaries local to test memory and output assertions.

- [x] Step 4: Run the integration selectors to verify success

Run:

~~~bash
uv run pytest tests/integration/acp/test_launch_trust_flow.py -q
~~~

Expected: unchanged URI inputs authorize, userinfo-only changes fail with SNAPSHOT_MISMATCH, and no side-effect seam is reached on rejection.

- [x] Step 5: Run the integration lint gate

Run:

~~~bash
uv run ruff check tests/integration/acp/test_launch_trust_flow.py
~~~

Expected: clean Ruff result.

### Task 7: Run repository-wide verification and hand off for review

Files:
- Verify: all files listed in this plan
- Modify: this plan's checkboxes only after each named verification command passes
- Do not stage: docs/superpowers/reviews/plan-9-99-review-checkpoints.md

- [ ] Step 1: Run the complete focused suite

Run:

~~~bash
uv run pytest tests/unit/security/test_sanitization.py tests/unit/acp/test_launch_policy.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_approval_cli.py tests/integration/acp/test_launch_trust_flow.py -q
~~~

Expected: all focused tests pass.

- [ ] Step 2: Run the full default suite

Run:

~~~bash
uv run pytest -q
~~~

Expected: zero failures and no new skips or deselections attributable to Plan 9.99.

- [ ] Step 3: Run the coverage gate

Run:

~~~bash
uv run pytest --cov=optimus --cov=optimus_gateway --cov=optimus_security --cov-branch --cov-report=term-missing --cov-fail-under=80 -q
~~~

Expected: aggregate production coverage is at least 80% and the command exits successfully.

- [x] Step 4: Run Ruff and whitespace verification

Run:

~~~bash
uv run ruff check .
git diff --check
~~~

Expected: Ruff is clean and git diff --check produces no output.

- [x] Step 5: Verify scope and working-tree safety

Run:

~~~bash
git status --short --branch
git diff --name-only
rg -n 'P9\.96-v1|security-snapshot-v2|urlunparse|parsed\.hostname|parsed\.port' src/optimus_security/sanitization.py src/optimus/acp/launch_gate.py src/optimus/acp/launch_approvals.py
~~~

Expected: only planned source/test/spec/plan files are changed; existing uv.lock and .claude/ state remains untouched; no forbidden component-reconstruction path remains in the new canonicalization/recording implementation; and no frozen Plan 9.96 file is modified.

- [x] Step 6: Update the reviewer checkpoint log and stop for explicit commit authorization

Record focused/full/coverage/Ruff results, changed-file scope, and remaining handoff state in docs/superpowers/reviews/plan-9-99-review-checkpoints.md. Do not stage or commit the log. Do not claim Plan 9.99 complete until the user reviews the implementation diff and explicitly authorizes any commit or PR action.

## Definition of Done

Plan 9.99 is ready for implementation review only when every checkbox above is ticked after its stated command passes, the approved security spec remains byte-stable, the four URI sources share the same canonicalization and recording path, all five URI-userinfo shapes and IPv6/case regressions pass, the P9.99-v1 compatibility boundary is enforced, raw child transport is unchanged, and the complete repository gates are green.

## Implementation handoff

This is a docs-only plan draft. After the user approves this exact plan, an implementing agent must read the Current State section of docs/superpowers/reviews/plan-9-99-review-checkpoints.md, verify it against git status and the approved spec, create a fresh branch/worktree from the latest main, and execute Tasks 1–7 in order. Any newly discovered scope must stop execution and receive a reviewed plan amendment; the frozen design and this plan must not be silently narrowed or widened.
