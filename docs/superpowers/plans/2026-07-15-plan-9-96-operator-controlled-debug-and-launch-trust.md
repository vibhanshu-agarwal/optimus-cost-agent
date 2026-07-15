# Plan 9.96 Operator-Controlled Debug and Launch Trust Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILLS: Use `superpowers:executing-plans` to execute this
> plan task-by-task and `superpowers:test-driven-development` for every behavior change. Do not use
> `superpowers:subagent-driven-development` unless the operator explicitly authorizes subagents for
> the implementation session. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft for reviewer-agent and operator review. The security contract is approved and
frozen; this implementation plan is not yet approved, and no implementation work is authorized.

**Goal:** Close `P9.85-FU-7` and `P9.9-FU-1` by authorizing the exact effective launch configuration
outside workspace control, providing useful session-scoped credential diagnostics without a
literal-secret redaction bypass, and proving all project-controlled diagnostic artifacts are
sanitized before persistence or promotion.

**Architecture:** Capture the parent environment once, classify every Optimus setting through one
typed registry, resolve trusted paths without inherited user-directory variables, and compare the
complete effective security snapshot with an HMAC-protected OS-keyring approval bound to the
workspace. A separate interactive `optimus-trust` command authors durable or delete-before-use
one-shot approvals; the serving path only validates or consumes them and constructs explicit child
environments from the authorized snapshot. A neutral `optimus_security` package sanitizes agent,
Gateway, telemetry, stderr, state, and transcript boundaries; elevated diagnostics add only
allowlisted metadata and session-local correlation tags.

**Tech Stack:** Python 3.14+, standard-library `dataclasses`, `enum`, `Decimal`, `hashlib`, `hmac`,
`secrets`, `json`, `urllib.parse`, `ctypes`/Windows Known Folders, `pwd` on POSIX,
`msvcrt.locking`/`fcntl.flock`, existing `keyring>=25,<26`, Pydantic v2, `pytest`,
`pytest-asyncio`, `pytest-cov`, Ruff, `uv`, real Redis/Optimus Gateway, and independent `acpx`.

**Estimated implementation size:** 4-6 weeks for one implementation lane, including the
cross-platform approval store, launch integration, sanitizer audit, real-dependency evidence, and
review checkpoints.

**Security-contract approval:** The reviewer-agent and operator Vibhanshu (`vibhanshu-agarwal`)
approved
`docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md`
at SHA-256 `8B67FC187B92F0B66A9932AAAD9A013C476C19C165A1044F57F338245A01786C` on
2026-07-15. The authoritative approval state is
`docs/superpowers/reviews/2026-07-15-plan-9-96-security-contract-approval.md`. The embedded Draft
header is retained because it is part of the frozen bytes.

## Source Anchors and Conflict Check

- Frozen security contract and adjacent approval record named above.
- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, Plan 9.96, sole custody of
  `P9.85-FU-7` and `P9.9-FU-1`.
- Plan 9.9 implementation commit `f120a5afde39e3b3a8a405211ae71653b6e75665` and
  `reports/plan-9-9-operator-packaging-evidence.md`.
- Architecture v2.15, LLD v2.38, and Test Strategy v1.4: one-key boundary, secret-free
  logs/telemetry/serialized state, and real-dependency evidence.
- Launch seams: `src/optimus/acp/{__main__,operator_paths,local_gateway_secrets,local_infra,
  subprocess_env,bootstrap,spec}.py` and `src/optimus_gateway/{__main__,models}.py`.
- Diagnostic seams: `src/optimus/acp/{debug_trace,e2e_transcript,ndjson_subprocess_session,
  server,dispatcher}.py`, `src/optimus/telemetry/**`, `src/optimus/loops/ledger.py`,
  `src/optimus/agent/state_store.py`, `src/optimus/release/{runner,agent_smoke_transcript}.py`, and
  `src/optimus_gateway/responses.py`.
- Current raw-capture evidence: `tools/run_plan987_acpx_live_evidence.py` and
  `tools/run_plan988_fu4b_live_evidence.py` persist raw `proc.stdout`; both remain frozen and are
  explicitly excluded from Plan 9.96-qualified evidence.

No conflict is presently known. If implementation finds a conflict among the frozen contract,
HLD, LLD, Test Strategy, or live behavior, stop and request a reviewed contract/plan amendment.
Do not reinterpret the contract in code.

## Global Constraints

1. **Task 0 is a hard gate:** No production, test, tool, report, or living-document mutation may
   occur until the exact contract digest, approval record, and Plan 9.9 commit object pass Task 0.
2. **Frozen contract:** Never edit the security contract. Any byte change invalidates both approvals
   and this plan. The adjacent approval record is frozen now and may not be edited during planning
   or implementation.
3. **Exactly two follow-ups:** This plan implements only `P9.85-FU-7` and `P9.9-FU-1`.
4. **No secret-redaction bypass:** Ordinary and elevated modes never persist literal secrets,
   fragments, reversible encodings, raw hashes, URI user information, full environment mappings,
   or unsafe object representations.
5. **Content authorization, not provenance guessing:** Do not claim to recover whether a flattened
   environment value came from an IDE, workspace file, shell, or administrator. Approve exact
   effective content through the independent keyring channel.
6. **Single environment capture:** The operator entrypoint captures the inherited environment once
   before any Optimus config/path helper reads it. Gated code receives the immutable snapshot and
   performs no later `os.environ` reads.
7. **Single policy registry:** Every concrete source-referenced `OPTIMUS_*` name, the
   `OPTIMUS_LOCAL_GATEWAY_` prefix, and every provider-key name has one tier, parser, display rule,
   approval rule, and propagation rule. A new unclassified name fails tests and launch.
8. **Trusted bootstrap:** Approval/key/lock locations never depend on inherited `APPDATA`,
   `LOCALAPPDATA`, `HOME`, `XDG_CONFIG_HOME`, or gated `OPTIMUS_CONFIG_ROOT`.
9. **One-key child:** The agent child receives only the existing one-key contract plus explicitly
   classified non-secret controls. Provider credentials and Gateway-internal values reach only the
   authorized Gateway child.
10. **Internal-only launch values:** Inherited `OPTIMUS_LOCAL_GATEWAY_BIND_HOST`,
    `OPTIMUS_LOCAL_GATEWAY_PORT`, and the three current `OPTIMUS_ACP_*` names fail before startup.
    Reviewed code may construct their equivalents only after authorization.
11. **Redis is security-sensitive:** Compare the exact raw `OPTIMUS_REDIS_URL`; display/store the
    normalized URI without user information and HMAC the complete secret-bearing value.
12. **Monotonic controls:** Unapproved `OPTIMUS_LIVE_MAX_COST_USD <= 0.25` and
    `OPTIMUS_MAX_PLANNING_TURNS <= 3` may tighten defaults. Invalid values fail. Any increase
    requires exact approval. The live-cost variable remains an evidence ceiling; this plan does not
    replace `AgentRunRequest.max_cost_usd`'s existing runtime budget.
13. **Bounded model exception:** `OPTIMUS_AGENT_MODEL` remains ceremony-free only while Gateway
    routing, endpoint/provider/credential authorization, the Tier 3 ceiling, pricing recognition,
    and the existing request budget all pass.
14. **Approval record bound:** Compact canonical JSON is at most 1,800 UTF-8 bytes. Secret fields
    use domain-separated HMAC-SHA-256; non-secret security fields use exact normalized literals;
    secret-bearing URI raw values use HMAC only.
15. **One-shot semantics:** A 256-bit nonce derives the `p996_...` handle. The writer never prints
    it. The consumer locks per workspace, verifies, deletes before child startup, and never restores
    the record after failure.
16. **Headless semantics:** Headless processes consume an interactively authored durable approval
    read-only. They cannot create, expand, rotate, or silently renew one.
17. **Shared sanitizer:** `optimus_security.sanitization` is the only implementation that converts
    possibly sensitive runtime data to persistable/exportable diagnostics. Agent and Gateway
    wrappers may re-export it but may not fork its rules.
18. **Unsupported objects:** Sanitization returns safe type metadata without calling `repr`,
    `str`, arbitrary serializers, or user code.
19. **Streaming guarantee:** Project-controlled transcript capture sanitizes before disk with an
    overlap equal to the supported maximum secret length. Promotion scans logically joined content
    while current secrets remain in memory, then repeats with canaries/patterns and a signed
    sanitizer manifest.
20. **Legacy capture exclusion:** Do not edit the frozen Plan 9.87/9.88 helpers. Their raw-capture
    behavior cannot satisfy a Plan 9.96 evidence claim and must be named as excluded in the audit.
21. **Real evidence:** Unit fakes prove deterministic policy only. OS credential-store claims use a
    real keyring backend; `requires_redis` uses real TimeSeries Redis; `requires_gateway` uses real
    credentials; ACP protocol evidence uses independently authored `acpx` and the real agent.
22. **No secret-bearing evidence:** Reports contain fields, result codes, counts, digests, and
    locators only. Never paste prompts, responses, source bodies, environment values, credentials,
    approval nonces, or URI user information.
23. **Approval-gated commits:** At every task boundary, show the exact diff and named verification
    output, wait for explicit operator approval, then commit only that task's files. Never use
    `--no-verify`.
24. **Checkbox protocol:** Mark `- [x]` only after the literal verification command ran and passed.
25. **Final quality:** Focused tests, full default tests, aggregate coverage of all three production
    packages at least 80%, full Ruff, contract/audit verifiers, real-dependency evidence, secret
    scan, and `git diff --check` must pass before closure.

## Requirements Traceability

| Contract claim | Owning tasks | Mechanical evidence |
|---|---|---|
| Frozen contract precedes implementation | Task 0 | exact SHA-256, approval-field, and Git-object checks |
| Exhaustive fail-closed variable classification | Tasks 1 and 5 | AST inventory, registry completeness, unknown/internal rejection |
| Trusted roots and workspace binding | Task 2 | mocked OS API tests plus relocation/symlink/file-identity tests |
| Exact durable/one-shot approvals | Tasks 3 and 4 | record vectors, HMAC mismatch, size, TTY, expiry, delete-before-use tests |
| Immutable snapshot and explicit children | Task 5 | no-late-read tests, spawn-order probes, exact Gateway/agent env assertions |
| Monotonic limits and bounded model exception | Tasks 1 and 5 | boundary matrix and recognized-model/request-budget tests |
| No unredacted-secret mode | Tasks 6 and 7 | ordinary/elevated canary matrix and allowlist assertions |
| Broad sink audit | Task 7 | AST surface manifest verifier with no unclassified sink |
| Sanitized real-`acpx` transcript | Tasks 8 and 9 | streaming split-secret tests, joined scans, real transcript manifest |
| Honest Plan 9.96 closure only | Task 9 | claim-to-evidence report and unchanged Plan 9.97 isolation sentence |

## Fixed Launch-Variable Policy Table

This table is copied into `LAUNCH_VARIABLE_POLICIES`; Task 1 tests the code table against these exact
names and all literal source references.

| Tier | Exact names | Parent rule | Propagation |
|---|---|---|---|
| Secret | `ANTHROPIC_API_KEY`, `GLM_API_KEY`, `LANGCHAIN_API_KEY`, `LANGSMITH_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `TAVILY_API_KEY`, `ZHIPUAI_API_KEY` | exact HMAC approval; never display/store | only the selected provider credential reaches the Gateway child |
| Secret | `OPTIMUS_API_KEY` | exact HMAC approval | agent child as the one-key contract |
| Secret | `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY`, `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET` | exact HMAC approval | Gateway child only; shared secret is projected to agent as `OPTIMUS_API_KEY` |
| Security | `OPTIMUS_GATEWAY_URL`, `OPTIMUS_REDIS_URL`, `OPTIMUS_CONFIG_ROOT`, `OPTIMUS_PRODUCTION_MODE`, `OPTIMUS_EXTRA_GATEWAY_ORIGINS`, `OPTIMUS_LOCAL_GATEWAY_PROVIDER`, `OPTIMUS_LOCAL_GATEWAY_BASE_URL` | exact approval; URI user information is a secret subfield | registry-specific agent/Gateway/parent projection |
| Monotonic | `OPTIMUS_LIVE_MAX_COST_USD`, `OPTIMUS_MAX_PLANNING_TURNS` | tightening/equal allowed; loosening requires exact approval | validated agent/evidence control only |
| Operational | `OPTIMUS_AGENT_MODEL` | allowed only under the bounded-model predicate | agent child |
| Internal-only | `OPTIMUS_LOCAL_GATEWAY_BIND_HOST`, `OPTIMUS_LOCAL_GATEWAY_PORT`, `OPTIMUS_ACP_DEBUG_TRACE`, `OPTIMUS_ACP_DEBUG_LOG`, `OPTIMUS_ACP_PROVENANCE_ROOT` | reject when inherited | code-derived arguments or in-memory context only after authorization |
| Prefix rule | `OPTIMUS_LOCAL_GATEWAY_` | any non-enumerated member fails closed | none |

## Explicit Exceptions

- Plan 9.97 mechanical current-raw-evidence grounding is excluded and must still say it **must not
  absorb or be absorbed by Plan 11**.
- Plan 10 Gateway capability brokering and Plan 11 context optimization are excluded.
- Plan 9.87 FU-4B remains accepted-open. Plan 9.96 does not reopen or reinterpret its evidence.
- The frozen Plan 9.87 and Plan 9.88 capture helpers are not remediated in place; they are excluded
  from Plan 9.96-qualified capture.
- Arbitrary external `acpx` output created outside the Plan 9.96 controlled capture path is not
  guaranteed sanitized.
- Same-user malware, OS/session compromise, and deliberate approval of a malicious literal value
  remain outside the Phase 1 threat boundary.
- Approval write/read separation is code architecture, not an OS privilege boundary.
- This plan does not add provider plugins, change provider protocols, estimate usage/cost, or place
  vendor credentials in the agent.
- This plan does not redesign runtime mutation approval (`AwaitingApproval`/`MutationGuard`);
  launch authorization is an earlier, independent gate.
- This planning branch contains documentation only. Implementation starts from a fresh branch based
  on the latest `origin/main` after this plan merges and receives separate approval.

## File and Interface Map

### New production modules

- `src/optimus/acp/launch_policy.py`: canonical variable registry, parsing/display/propagation,
  immutable environment snapshot, monotonic decisions, and security-snapshot canonicalization.
- `src/optimus/acp/trusted_paths.py`: OS-derived config/runtime roots and canonical workspace
  identity independent of inherited user-directory variables.
- `src/optimus/acp/launch_approvals.py`: approval schema, HMACs, keyring reader/consumer,
  cross-platform workspace lock, one-shot deletion, durable validation, and diagnostic grants.
- `src/optimus/acp/launch_gate.py`: effective candidate resolution, two-phase config-root handling,
  approval comparison, TOCTOU revalidation, and authorized child inputs.
- `src/optimus/acp/launch_approval_cli.py`: interactive writer-only `optimus-trust` command.
- `src/optimus/acp/launch_audit.py`: append-only, value-safe authorization audit events under the
  trusted external runtime root; failure before spawn is fatal.
- `src/optimus_security/__init__.py` and `src/optimus_security/sanitization.py`: neutral shared
  structured/free-text/streaming sanitizer, rule counts, correlation tags, and promotion scan.
- `src/optimus_security/launch_manifest.py`: compact 60-second Gateway-child manifest signed by the
  approval-store HMAC key and independently verifiable by the Gateway process.

### New verification/evidence files

- `tests/unit/acp/test_launch_policy.py`
- `tests/unit/acp/test_trusted_paths.py`
- `tests/unit/acp/test_launch_approvals.py`
- `tests/unit/acp/test_launch_gate.py`
- `tests/unit/acp/test_launch_approval_cli.py`
- `tests/unit/acp/test_launch_audit.py`
- `tests/unit/security/test_sanitization.py`
- `tests/unit/security/test_launch_manifest.py`
- `tests/unit/tools/test_verify_plan996_logging_surfaces.py`
- `tests/unit/tools/test_run_plan996_acpx_security_evidence.py`
- `tests/integration/acp/test_launch_trust_flow.py`
- `tests/e2e/acp/test_plan996_authorized_launch.py`
- `tools/verify_plan996_logging_surfaces.py`
- `tools/run_plan996_acpx_security_evidence.py`
- `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json`
- `reports/plan-9-96-operator-debug-launch-trust-evidence.md`

### Existing integration targets

- `pyproject.toml`: add `optimus-trust` script and include `optimus_security` in coverage.
- `src/optimus/acp/__main__.py`: capture and gate before path/config/network/log mutation.
- `src/optimus/acp/operator_paths.py`: consume validated roots; remove inherited user-directory
  bootstrap.
- `src/optimus/acp/local_gateway_secrets.py`: return pre-resolved credential objects without a
  later config/keyring reread.
- `src/optimus/acp/local_infra.py`: accept authorized credentials/settings and construct the exact
  Gateway child.
- `src/optimus/acp/subprocess_env.py`: derive agent child keys from the canonical registry.
- `src/optimus/acp/spec.py`: consume the validated planning-turn value rather than ambient env.
- `src/optimus/acp/debug_trace.py`: process-local authorized debug context; no internal env toggles.
- `src/optimus/acp/e2e_transcript.py` and `ndjson_subprocess_session.py`: sanitize before retention.
- `src/optimus/acp/server.py` and `dispatcher.py`: sanitize stderr/JSON-RPC exception text.
- `src/optimus/telemetry/{redaction,jsonl,observability,serialization}.py`: compatibility wrapper
  and shared-sanitizer enforcement at storage/export.
- `src/optimus/loops/ledger.py`, `src/optimus/agent/state_store.py`, and
  `src/optimus/release/{runner,agent_smoke_transcript}.py`: audit-driven persistence fixes only.
- `src/optimus_gateway/{__main__,models,responses}.py`: reject inherited bind settings, accept only
  authorized parent construction, and use the neutral sanitizer.
- `tools/run_local_gateway.sh` and `tools/run_local_gateway.ps1`: stop sourcing/executing a
  repository-controlled `.env.gateway`; parse it as untrusted input through `optimus-trust` and
  preserve the explicit manual Gateway flow behind the same value-visible ceremony.

---

### Task 0: Verify the Frozen Security Contract Before Any Implementation Mutation

**Deliverable:** The implementation lane proves it is executing the exact approved contract and
foundation, or stops without changing a file.

**Files:** Read-only: frozen contract, approval record, roadmap, and Git object database.

- [ ] **Step 1: Verify the contract bytes**

Run:

```bash
uv run python -c "from pathlib import Path; import hashlib; p=Path('docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md'); print(hashlib.sha256(p.read_bytes()).hexdigest().upper())"
```

Expected exact output:

```text
8B67FC187B92F0B66A9932AAAD9A013C476C19C165A1044F57F338245A01786C
```

- [ ] **Step 2: Verify both approvals and foundation identity**

Run:

```bash
rg -n "Approved and frozen|8B67FC187B92F0B66A9932AAAD9A013C476C19C165A1044F57F338245A01786C|vibhanshu-agarwal|Reviewer-agent" docs/superpowers/reviews/2026-07-15-plan-9-96-security-contract-approval.md
git cat-file -t f120a5afde39e3b3a8a405211ae71653b6e75665
```

Expected: all four approval fields are present and Git prints `commit`.

- [ ] **Step 3: Prove the gate was read-only**

Run `git status --short` and compare with the pre-task status. Expected: no new or modified file.
If any verification fails, stop and request a reviewed correction; do not continue to Task 1.

---

### Task 1: Build the Canonical Launch-Variable Registry and Immutable Snapshot

**Deliverable:** One registry classifies every existing setting and rejects unknown/internal parent
values before resolution.

**Files:**
- Create: `src/optimus/acp/launch_policy.py`
- Create: `tests/unit/acp/test_launch_policy.py`

**Interfaces:**

```python
class LaunchVariableTier(StrEnum):
    SECRET = "secret"
    SECURITY = "security"
    MONOTONIC_LIMIT = "monotonic_limit"
    OPERATIONAL = "operational"
    INTERNAL_ONLY = "internal_only"


class PropagationTarget(StrEnum):
    PARENT_ONLY = "parent_only"
    AGENT_CHILD = "agent_child"
    GATEWAY_CHILD = "gateway_child"
    REVIEWED_INTERNAL = "reviewed_internal"
    NEVER = "never"


@dataclass(frozen=True)
class LaunchEnvironmentSnapshot:
    values: Mapping[str, str]

    @classmethod
    def capture(cls, environ: Mapping[str, str]) -> "LaunchEnvironmentSnapshot": ...


DEFAULT_LIVE_MAX_COST_USD = Decimal("0.25")
DEFAULT_MAX_PLANNING_TURNS = 3
LAUNCH_VARIABLE_POLICIES: Mapping[str, LaunchVariablePolicy]


@dataclass(frozen=True)
class LaunchVariablePolicy:
    name: str
    tier: LaunchVariableTier
    propagation: frozenset[PropagationTarget]
    parser: Callable[[str], object]
    display: Callable[[str], str]
    approval: str


@dataclass(frozen=True)
class LaunchPolicyError(ValueError):
    code: str
    variable_name: str | None = None
```

- [ ] **Step 1: Write failing registry-inventory tests**

Add exact nodes:

- `test_every_literal_optimus_source_name_has_one_policy`
- `test_local_gateway_prefix_literal_has_one_fail_closed_prefix_rule`
- `test_provider_key_registry_equals_local_provider_key_names`
- `test_every_policy_has_parser_display_approval_and_propagation`
- `test_unknown_optimus_name_fails_closed_by_name_only`
- `test_inherited_bind_and_acp_debug_names_fail_before_resolution`

The AST scan covers `src/**/*.py`; a concrete literal name ending in `_` is a prefix rule, not a
variable. Expected initial failure: `launch_policy` or the required registry is absent.

- [ ] **Step 2: Implement the exact five-tier table**

Enumerate the secret, security, monotonic, operational, and internal-only settings exactly as the
contract does. URI normalization must return `(masked_literal, secret_subfield_present,
full_value_hmac_required)`. Unknown `OPTIMUS_*` and unenumerated `OPTIMUS_LOCAL_GATEWAY_*` names
raise `LaunchPolicyError(code="LAUNCH_VARIABLE_UNCLASSIFIED", variable_name=name)` without value.

- [ ] **Step 3: Pin monotonic and model decisions**

Add boundary tests for absent, malformed, zero, negative, non-finite, below/equal/above default
values. Assert that a model is operational only when Gateway routing, pricing recognition,
protected Tier 3 ceiling, and the existing `AgentRunRequest.max_cost_usd` budget are present.

- [ ] **Step 4: Run and review Task 1**

```bash
uv run pytest tests/unit/acp/test_launch_policy.py tests/unit/config/test_gateway_settings.py -q
uv run ruff check src/optimus/acp/launch_policy.py src/optimus/config/gateway.py tests/unit/acp/test_launch_policy.py
git diff --check
```

Expected: all tests and Ruff pass; inventory reports zero missing/duplicate policies. Show the diff
and wait for operator approval. After approval only:

```bash
git add src/optimus/acp/launch_policy.py tests/unit/acp/test_launch_policy.py
git commit -m "Add launch variable policy registry"
```

---

### Task 2: Resolve Trusted Roots and Canonical Workspace Identity Without Inherited Paths

**Deliverable:** OS-derived roots and workspace identity cannot be redirected by workspace launch
environment values.

**Files:**
- Create: `src/optimus/acp/trusted_paths.py`
- Create: `tests/unit/acp/test_trusted_paths.py`
- Modify: `src/optimus/acp/operator_paths.py`
- Modify: `tests/unit/acp/test_operator_paths.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class TrustedOperatorRoots:
    default_config_root: Path
    approval_runtime_root: Path


@dataclass(frozen=True)
class WorkspaceIdentity:
    canonical_path: str
    device: int
    inode: int
    repository_root: str | None
    git_common_dir: str | None
    digest: str


def resolve_trusted_operator_roots(...) -> TrustedOperatorRoots: ...
def resolve_workspace_identity(workspace_root: Path) -> WorkspaceIdentity: ...
def revalidate_workspace_identity(identity: WorkspaceIdentity) -> None: ...
```

- [ ] **Step 1: Write failing Windows/POSIX root tests**

Mock Windows Known Folder results for RoamingAppData and LocalAppData, and POSIX authenticated
account home. Set hostile inherited `APPDATA`, `LOCALAPPDATA`, `HOME`, and `XDG_CONFIG_HOME`; assert
none changes the result. Missing OS resolution fails with `TRUSTED_OPERATOR_ROOT_UNAVAILABLE` and
does not create a workspace path.

- [ ] **Step 2: Implement platform-derived roots**

Use `SHGetKnownFolderPath(FOLDERID_RoamingAppData)` for Windows config and
`SHGetKnownFolderPath(FOLDERID_LocalAppData)` for Windows approval runtime through a small
injectable adapter; use `pwd.getpwuid(os.getuid()).pw_dir` on POSIX with `.config/optimus-cost-agent`
and `.local/state/optimus-cost-agent`. `OPTIMUS_CONFIG_ROOT` is not an input to this function.

- [ ] **Step 3: Implement identity and revalidation**

Canonicalize path plus `os.stat().st_dev/st_ino`; when Git is present, resolve repository root and
common dir with argument-list subprocess calls and `shell=False`. Tests cover relocation,
symlink/junction target change, repository common-dir change, missing workspace, Windows case
normalization, and non-Git workspaces.

- [ ] **Step 4: Refactor operator paths to require validated inputs**

`resolve_operator_paths()` receives `trusted_roots` and an already validated optional config-root
override. Remove inherited APPDATA/HOME/XDG bootstrap. Keep workspace `.optimus` debug/Gateway logs
separate from the external approval runtime root.

- [ ] **Step 5: Run and review Task 2**

```bash
uv run pytest tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_operator_paths.py -q
uv run ruff check src/optimus/acp/trusted_paths.py src/optimus/acp/operator_paths.py tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_operator_paths.py
git diff --check
```

Expected: all tests pass, including hostile inherited-path cases. Show the diff and wait for
approval. After approval only:

```bash
git add src/optimus/acp/trusted_paths.py src/optimus/acp/operator_paths.py tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_operator_paths.py
git commit -m "Add trusted operator paths and workspace identity"
```

---

### Task 3: Implement HMAC-Protected Keyring Approvals and Single-Use Consumption

**Deliverable:** Durable and one-shot records have fixed schema, size, integrity, workspace binding,
expiry/revocation, and concurrency semantics.

**Files:**
- Create: `src/optimus/acp/launch_approvals.py`
- Create: `tests/unit/acp/test_launch_approvals.py`

**Interfaces:**

```python
APPROVAL_SCHEMA_VERSION = 1
LAUNCH_POLICY_COMPATIBILITY = "P9.96-v1"
MAX_APPROVAL_RECORD_BYTES = 1800
ONE_SHOT_TTL_SECONDS = 300
DIAGNOSTIC_TTL_SECONDS = 900


@dataclass(frozen=True)
class ApprovalRecord:
    schema_version: int
    policy_compatibility: str
    approval_id: str
    mode: Literal["one-shot", "durable"]
    workspace_identity: WorkspaceIdentity
    created_at: datetime
    expires_at: datetime | None
    creator_identity: str
    ceremony_cli_version: str
    security_literals: Mapping[str, str]
    secret_fingerprints: Mapping[str, str]
    monotonic_grants: Mapping[str, str]
    model_observation: str | None
    registry_version: str
    security_snapshot_digest: str
    consumed: bool
    record_hmac: str


@dataclass(frozen=True)
class DiagnosticGrant:
    grant_id: str
    workspace_digest: str
    approval_id: str
    launch_session_id: str
    expires_at: datetime
    record_hmac: str


class KeyringApprovalStore:
    def read_durable(self, workspace_digest: str) -> ApprovalRecord | None: ...
    def write_durable(self, record: ApprovalRecord) -> None: ...
    def write_one_shot(self, record: ApprovalRecord, nonce: bytes) -> str: ...
    def consume_one_shot(self, handle: str, expected_snapshot_digest: str) -> ApprovalRecord: ...
    def write_diagnostic_grant(self, grant: DiagnosticGrant) -> None: ...
    def consume_diagnostic_grant(self, grant_id: str, launch_session_id: str) -> DiagnosticGrant: ...
    def revoke_workspace(self, workspace_digest: str) -> None: ...
    def rotate_hmac_key(self) -> None: ...
```

- [ ] **Step 1: Write failing record and fingerprint vectors**

Test canonical JSON, domain-separated secret HMACs, URI-userinfo HMAC, workspace/policy/version
binding, non-secret literal storage, no raw SHA, and an exact 1,800-byte acceptance/1,801-byte
rejection boundary. Inspect serialized JSON to prove canary secrets and URI user information are
absent.

- [ ] **Step 2: Implement the keyring namespace and integrity key**

Use a dedicated service namespace distinct from existing provider credentials. Store the HMAC key,
durable workspace record, and one-shot record as separate entries. Reader failures map to stable
value-free codes; never fall back to an unverified record.

- [ ] **Step 3: Implement nonce handle and lock**

Generate 32 random bytes and derive exactly `p996_` plus unpadded base64url SHA-256 over the contract
domain and nonce. Lock a workspace-digest file under `approval_runtime_root` with `msvcrt.locking`
on Windows or `fcntl.flock` on POSIX. Under the lock, verify handle/HMAC/snapshot/expiry, delete the
record, confirm deletion, then return it. Crash or deletion failure leaves startup unauthorized.

- [ ] **Step 4: Prove concurrency and replay behavior**

Tests synchronize two consumers and assert exactly one succeeds; cover expired, corrupt,
wrong-workspace, wrong-policy, rotated-key, revoked, already-consumed, failed-delete, and lock-failure
paths. A fake keyring is permitted only in this unit task.

- [ ] **Step 5: Run and review Task 3**

```bash
uv run pytest tests/unit/acp/test_launch_approvals.py -q
uv run ruff check src/optimus/acp/launch_approvals.py tests/unit/acp/test_launch_approvals.py
git diff --check
```

Expected: all record, size, race, and replay tests pass. Wait for approval. After approval only:

```bash
git add src/optimus/acp/launch_approvals.py tests/unit/acp/test_launch_approvals.py
git commit -m "Add durable and one-shot launch approvals"
```

---

### Task 4: Resolve the Exact Security Snapshot and Add the Interactive Writer CLI

**Deliverable:** The operator sees the complete display-safe effective configuration and can author
one exact durable or one-shot approval; headless launch remains read-only.

**Files:**
- Create: `src/optimus/acp/launch_gate.py`
- Create: `src/optimus/acp/launch_approval_cli.py`
- Create: `tests/unit/acp/test_launch_gate.py`
- Create: `tests/unit/acp/test_launch_approval_cli.py`
- Create: `src/optimus_security/__init__.py`
- Create: `src/optimus_security/sanitization.py`
- Create: `tests/unit/security/test_sanitization.py`
- Modify: `src/optimus/telemetry/redaction.py`
- Modify: `src/optimus/acp/local_gateway_secrets.py`
- Modify: `tests/unit/acp/test_local_gateway_secrets.py`
- Modify: `pyproject.toml`

**Interfaces:**

```python
@dataclass(frozen=True)
class LaunchCandidate:
    inherited: LaunchEnvironmentSnapshot
    workspace_identity: WorkspaceIdentity
    operator_paths: OperatorPaths
    security_snapshot_digest: str
    display_rows: tuple[LaunchDisplayRow, ...]
    gateway_environ: Mapping[str, str]
    agent_environ: Mapping[str, str]
    secret_inventory: tuple[str, ...]


@dataclass(frozen=True)
class LaunchDisplayRow:
    name: str
    tier: LaunchVariableTier
    source_class: str
    display_value: str
    decision: str


@dataclass(frozen=True)
class AuthorizedLaunch:
    candidate: LaunchCandidate
    approval_id: str
    approval_mode: str
    launch_session_id: str


def resolve_launch_candidate(...) -> LaunchCandidate: ...
def authorize_launch(...) -> AuthorizedLaunch: ...


MAX_SECRET_TEXT_CHARS = 65_536


@dataclass(frozen=True)
class SanitizationResult:
    value: object
    rule_counts: Mapping[str, int]


def sanitize_for_persistence(value: object, *, known_secrets: Sequence[str] = ()) -> SanitizationResult: ...
```

- [ ] **Step 1: Write failing candidate-resolution tests**

Cover environment > external `.env.gateway` > keyring > default precedence without rereading
ambient env. Exact provider/base URL are displayed; Redis/Gateway URI user information is masked;
secret rows show name/presence/provenance/length only. The complete snapshot digest changes when any
exact source representation, credential, workspace identity, registry version, or policy version
changes.

- [ ] **Step 2: Make config-root resolution two-phase**

Before reading a custom `OPTIMUS_CONFIG_ROOT`, compare its exact literal/identity with the selected
approval metadata. During interactive authoring, require a separate value-visible consent to read
the custom external root, then show the complete final snapshot for the one approval confirmation.
The default OS root needs no preliminary consent. Validate file type, containment, symlink target,
owner/current-user accessibility, and platform permissions before parsing `.env.gateway`. On POSIX,
require current UID ownership and reject any group/other permission bit (`st_mode & 0o077`). On
Windows, inspect the DACL through an injectable Win32 security adapter; allow the current user,
SYSTEM, and Administrators, and reject read/write allow ACEs for Everyone, Users, Authenticated
Users, or an unknown principal. A platform that cannot prove these checks fails closed with a
value-free remediation code.

- [ ] **Step 3: Refactor credential resolution to be single-read**

Return immutable provider/shared-secret resolution objects from `resolve_launch_candidate`.
Downstream Gateway startup receives those objects; it must not reread `.env.gateway`, keyring, or
ambient environment after authorization.

- [ ] **Step 4: Add the shared sanitizer core before any ceremony output**

Implement structured/free-text redaction, exact current-secret replacement, URI-userinfo masking,
rule counts, and safe unsupported-object type metadata in the neutral package. Keep
`redact_for_telemetry()` as a compatibility wrapper returning `.value`. The sanitizer accepts known
secrets explicitly and never reads ambient environment. Tests cover every Tier 1 name, nested
containers, bearer/header/assignment forms, URI schemes, and objects whose `__repr__`/`__str__`
raise or contain canaries. Add `src/optimus_security` to `[tool.coverage.run].source` in
`pyproject.toml` so the new production package participates in the 80% gate.

- [ ] **Step 5: Implement `optimus-trust` writer commands**

Add the console script:

```toml
optimus-trust = "optimus.acp.launch_approval_cli:main"
```

Commands are `setup-credentials`, `approve --mode durable`, `approve --mode one-shot -- <argv>`,
`inspect`, `revoke`, and `rotate-key`. Authoring and rotation require `stdin.isatty()` and
`stdout.isatty()`. One-shot target argv may contain the literal placeholders `{approval_id}` and
`{launch_session_id}`; replace them in-memory, invoke with `shell=False`, never print the
identifiers, and delete the one-shot record if spawning fails. Inspect prints metadata only.

`setup-credentials` preserves the existing provider-key setup flow but derives its location from
trusted OS roots, requires a TTY, and creates no launch approval. The legacy `optimus-agent --setup`
path delegates to this writer behavior or exits with the exact migration command; it may not use an
inherited unapproved config root.

- [ ] **Step 6: Prove headless and display behavior**

Tests assert piped input cannot author, headless can read an existing durable record, one-shot uses
dedicated argv fields and no environment token, provider/base are literal, URI userinfo is masked,
credentials never display, and CLI output/exception paths contain no canaries.

- [ ] **Step 7: Run and review Task 4**

```bash
uv run pytest tests/unit/security/test_sanitization.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_local_gateway_secrets.py tests/unit/acp/test_entrypoint.py -q
uv run ruff check src/optimus_security src/optimus/telemetry/redaction.py src/optimus/acp/launch_gate.py src/optimus/acp/launch_approval_cli.py src/optimus/acp/local_gateway_secrets.py tests/unit/security tests/unit/acp/test_launch_gate.py tests/unit/acp/test_launch_approval_cli.py
git diff --check
```

Expected: exact snapshot, TTY, display, and spawn tests pass. Wait for approval. After approval only:

```bash
git add pyproject.toml src/optimus_security/__init__.py src/optimus_security/sanitization.py src/optimus/telemetry/redaction.py src/optimus/acp/launch_gate.py src/optimus/acp/launch_approval_cli.py src/optimus/acp/local_gateway_secrets.py tests/unit/security/test_sanitization.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_local_gateway_secrets.py tests/unit/acp/test_entrypoint.py
git commit -m "Add operator launch approval ceremony"
```

---

### Task 5: Gate Every Operator Launch and Construct Exact Gateway/Agent Children

**Deliverable:** No Redis, Gateway, agent, debug file, preflight, or child starts before exact
authorization; only the trusted-root approval lock/keyring reads and mandatory value-safe launch
audit may occur inside the gate. No later ambient read or parent-env passthrough can reopen the
boundary.

**Files:**
- Modify: `src/optimus/acp/__main__.py`
- Modify: `src/optimus/acp/operator_paths.py`
- Modify: `src/optimus/acp/local_infra.py`
- Modify: `src/optimus/acp/subprocess_env.py`
- Modify: `src/optimus/acp/spec.py`
- Modify: `src/optimus/acp/bootstrap.py`
- Modify: `src/optimus/acp/operator_verify.py`
- Modify: `src/optimus/acp/debug_trace.py`
- Modify: `src/optimus/acp/launch_approval_cli.py`
- Create: `src/optimus/acp/launch_audit.py`
- Create: `tests/unit/acp/test_launch_audit.py`
- Modify: `tests/unit/acp/test_launch_approval_cli.py`
- Modify: `tests/unit/acp/test_debug_trace.py`
- Modify: `src/optimus_gateway/__main__.py`
- Modify: `src/optimus_gateway/models.py`
- Create: `src/optimus_security/launch_manifest.py`
- Create: `tests/unit/security/test_launch_manifest.py`
- Modify: `tools/run_local_gateway.sh`
- Modify: `tools/run_local_gateway.ps1`
- Modify corresponding existing unit tests under `tests/unit/acp/`
- Create: `tests/integration/acp/test_launch_trust_flow.py`

- [ ] **Step 1: Write the fail-before-side-effect matrix**

Parameterize unknown name, inherited internal name, unapproved provider/base/key/Redis/config root,
loosened cost/turn limit, corrupt/expired approval, changed workspace, and snapshot mismatch. Instrument
workspace/config writes, debug/telemetry file opens, Docker/socket/subprocess, Redis/preflight, and
server construction; assert every external probe remains untouched and the error contains only
stable code plus variable name. Separately assert keyring/lock/audit access is confined to the
trusted external root and the rejection audit contains no value.

- [ ] **Step 2: Capture once and thread typed inputs**

`main()` captures `LaunchEnvironmentSnapshot` immediately after parsing argv/workspace, accepts only
the internal `--launch-approval-id` and `--launch-session-id` as new internal arguments, resolves/authorizes,
revalidates the same candidate, then calls downstream helpers with `AuthorizedLaunch`. Replace
debug-trace env mutation and `_max_planning_turns_from_env()` ambient reads with typed validated
values. Task 5 establishes the ordinary process-local debug context; Task 6 adds elevated grant
behavior without restoring environment control.

- [ ] **Step 3: Replace duplicated child allowlists with registry projections**

Gateway child projection includes only authorized provider, one provider key, base URL when
applicable, shared secret, and code-derived loopback bind values. Agent projection includes only
Gateway URL, Optimus shared key, Redis URL, bounded model, validated limits, production/origin
settings when applicable, and existing system keys. Provider/Gateway-internal secrets remain absent.

- [ ] **Step 4: Close the standalone bind seam**

The standalone Gateway entrypoint rejects inherited `OPTIMUS_LOCAL_GATEWAY_BIND_HOST` and
`OPTIMUS_LOCAL_GATEWAY_PORT`. The authorized parent passes code-derived bind host/port as explicit
arguments plus a short-lived HMAC child manifest bound to the approved snapshot; Gateway validates
the manifest against its exact provider/base/credential inputs before constructing
`GatewayServiceConfig`. Direct unmanifested startup fails closed. Update both manual launcher scripts
to call a Task 5 `optimus-trust run-gateway` command; it parses the explicitly named repository
`.env.gateway` as data, displays the complete safe snapshot, and creates the authorized child
manifest. The scripts must not `source`, execute, or copy repository
`.env.gateway` values into the invoking shell. Tests prove the scripts preserve explicit
developer/admin launch while a non-interactive invocation fails with value-free approval remediation.

`GatewayChildManifest` contains schema/policy versions, workspace and security-snapshot digests,
exact non-secret provider/base/bind values, HMAC fingerprints of provider/shared credentials,
issued/expiry times no more than 60 seconds apart, and a random nonce. It contains no secret. Sign
with the approval-store HMAC key under a distinct domain; `optimus_gateway` reads that key from the
dedicated keyring namespace through the neutral module and rejects missing, expired, mismatched, or
invalid manifests. The same-user keyring limitation remains the contract's accepted boundary.

- [ ] **Step 5: Pin monotonic and model behavior**

Assert unapproved lower/equal cost/turn values pass, higher values require a matching approval,
invalid values fail, and a more expensive recognized model still runs under the existing request
budget and protected evidence ceiling. Do not make `OPTIMUS_LIVE_MAX_COST_USD` override
`AgentRunRequest.max_cost_usd`.

- [ ] **Step 6: Append the authorization audit before startup**

Before any child/network startup, append one `LaunchAuditEvent` under the trusted external runtime
root with timestamp, workspace digest, launch/session/approval metadata, registry/policy versions,
setting names/tiers/source classes, display-safe non-secret decisions, monotonic dispositions,
unknown/internal rejection names, child-propagation decisions, diagnostic-grant state, sanitizer
rule counts, and final value-free reason code. Open with append semantics and restrictive current-user
permissions. Audit path, permission, serialization, sanitization, or append failure stops startup;
there is no raw fallback.

- [ ] **Step 7: Prove TOCTOU and exact children**

Mutate `os.environ`, config bytes, keyring value, workspace identity, symlink target, and approval
record between candidate creation and spawn. Every case fails before spawn. Assert no gated helper
reads `os.environ` and exact child-key sets equal registry projections.

- [ ] **Step 8: Run and review Task 5**

```bash
uv run pytest tests/unit/security/test_launch_manifest.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_main_check_config.py tests/unit/acp/test_main_debug_trace.py tests/unit/acp/test_debug_trace.py tests/unit/acp/test_local_infra.py tests/unit/acp/test_acp_subprocess_env.py tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_bootstrap.py tests/unit/acp/test_launch_audit.py tests/integration/acp/test_launch_trust_flow.py -q
uv run ruff check src/optimus_security/launch_manifest.py src/optimus/acp src/optimus_gateway tests/unit/security/test_launch_manifest.py tests/unit/acp tests/integration/acp/test_launch_trust_flow.py
git diff --check
```

Expected: side-effect probes, TOCTOU, audit, and exact-child tests pass. Wait for approval. After
approval only:

```bash
git add src/optimus_security/launch_manifest.py src/optimus/acp/__main__.py src/optimus/acp/operator_paths.py src/optimus/acp/local_infra.py src/optimus/acp/subprocess_env.py src/optimus/acp/spec.py src/optimus/acp/bootstrap.py src/optimus/acp/operator_verify.py src/optimus/acp/debug_trace.py src/optimus/acp/launch_approval_cli.py src/optimus/acp/launch_audit.py src/optimus_gateway/__main__.py src/optimus_gateway/models.py tools/run_local_gateway.sh tools/run_local_gateway.ps1 tests/unit/security/test_launch_manifest.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_main_check_config.py tests/unit/acp/test_main_debug_trace.py tests/unit/acp/test_local_infra.py tests/unit/acp/test_acp_subprocess_env.py tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_bootstrap.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_launch_audit.py tests/unit/acp/test_debug_trace.py tests/integration/acp/test_launch_trust_flow.py
git commit -m "Gate operator launches before child startup"
```

---

### Task 6: Extend the Shared Sanitizer for Streams and Session-Scoped Diagnostics

**Deliverable:** The existing neutral sanitizer gains bounded streaming and session correlation;
elevated mode emits only approved metadata and non-derivable session tags.

**Files:**
- Modify: `src/optimus_security/sanitization.py`
- Modify: `tests/unit/security/test_sanitization.py`
- Modify: `src/optimus/acp/launch_gate.py`
- Modify: `src/optimus/acp/launch_approval_cli.py`
- Modify: `src/optimus/acp/__main__.py`
- Modify: `src/optimus/acp/debug_trace.py`
- Modify: `tests/unit/acp/test_launch_gate.py`
- Modify: `tests/unit/acp/test_launch_approval_cli.py`
- Modify: `tests/unit/acp/test_debug_trace.py`
- Modify: `tests/unit/acp/test_main_debug_trace.py`

**Interfaces:**

```python
MAX_SECRET_TEXT_CHARS = 65_536


def session_correlation_tag(secret: str, *, field_name: str, session_key: bytes) -> str: ...


class StreamingTextSanitizer:
    def feed(self, chunk: str) -> str: ...
    def finalize(self) -> str: ...
```

- [ ] **Step 1: Write the complete canary matrix**

Extend the core canary matrix with exceptions, same-secret reviewed comparison points, cross-session
tags, and secrets split at every chunk boundary. Reject configured secrets longer than
`MAX_SECRET_TEXT_CHARS` at launch so the overlap guarantee is complete.

- [ ] **Step 2: Implement streaming and correlation extensions**

Retain the Task 4 rules and wrapper. Add the bounded overlap stream and correlation-tag functions;
known current secrets are passed from `AuthorizedLaunch`, and neither function reads ambient env.

- [ ] **Step 3: Replace debug environment state with authorized context**

Generate the debug session ID and session HMAC key in memory. Ordinary mode emits no tags. A
consumed diagnostic grant enables only the contract's metadata allowlist and 128-bit truncated
session tags at predeclared comparison points; no arbitrary candidate API exists. Expiry/mismatch
downgrades to ordinary mode. Add `optimus-trust run --elevated-debug -- <argv>` for a previously
approved durable snapshot; it creates the grant in a TTY, substitutes `{approval_id}`,
`{launch_session_id}`, and `{diagnostic_grant_id}` argv placeholders without printing them, and the
serving path consumes the grant once through an internal `--diagnostic-grant-id` argument.
Extend `AuthorizedLaunch` with `diagnostic_grant: DiagnosticGrant | None`; ordinary and failed-grant
paths set `None` and emit no correlation tags.

- [ ] **Step 4: Prove no opt-out exists**

AST/tests fail if `acp_debug_log` exposes `redact=False`, `raw=True`, or any branch that writes the
unsanitized input. Sink serialization cannot use `default=str`.

- [ ] **Step 5: Run and review Task 6**

```bash
uv run pytest tests/unit/security/test_sanitization.py tests/unit/telemetry/test_serialization.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_debug_trace.py tests/unit/acp/test_main_debug_trace.py -q
uv run ruff check src/optimus_security src/optimus/acp/launch_gate.py src/optimus/acp/launch_approval_cli.py src/optimus/acp/__main__.py src/optimus/acp/debug_trace.py tests/unit/security tests/unit/acp/test_launch_gate.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_debug_trace.py
git diff --check
```

Expected: all canary, split, unsupported-object, correlation, and no-opt-out tests pass. Wait for
approval. After approval only:

```bash
git add src/optimus_security/sanitization.py src/optimus/acp/launch_gate.py src/optimus/acp/launch_approval_cli.py src/optimus/acp/__main__.py src/optimus/acp/debug_trace.py tests/unit/security/test_sanitization.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_debug_trace.py tests/unit/acp/test_main_debug_trace.py
git commit -m "Add shared sanitizer and elevated diagnostics"
```

---

### Task 7: Audit and Enforce Every Diagnostic Persistence/Export Surface

**Deliverable:** A machine-readable source audit has no unclassified sink; every diagnostic sink is
sanitized or mechanically justified as safe-by-construction.

**Files:**
- Create: `tools/verify_plan996_logging_surfaces.py`
- Create: `tests/unit/tools/test_verify_plan996_logging_surfaces.py`
- Create: `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json`
- Modify audit-driven sinks only: `src/optimus/acp/{server,dispatcher}.py`,
  `src/optimus/telemetry/{jsonl,observability,serialization}.py`,
  `src/optimus/loops/ledger.py`, `src/optimus/agent/state_store.py`,
  `src/optimus/release/{runner,agent_smoke_transcript}.py`, and
  `src/optimus_gateway/responses.py`
- Modify corresponding existing unit tests

- [ ] **Step 1: Write a failing AST surface verifier**

Inventory calls to `print`, logger methods, `open`/`Path.open`, `write`/`write_text`, JSON
serialization at a sink, Redis/state serialization, stderr/stdout retention, and `str(exc)` or
traceback flow into a persistence/export/protocol boundary. Key findings by stable
`module:function:sink_kind`, not line number. Fail when a discovered sink lacks exactly one manifest
entry or a manifest entry no longer resolves. Scan all `src/**/*.py` and `tools/**/*.py`; apply
explicit command/text patterns to `tools/**/*.sh` and `tools/**/*.ps1` so manual launchers and raw
capture cannot sit outside the inventory.

- [ ] **Step 2: Classify every live surface**

Each JSON manifest entry records `policy` (`shared-sanitize`, `safe-by-construction`,
`protocol-only`, or `frozen-nonqualifying`), rationale, sanitizer call/validator, named test node,
and evidence tier. The two frozen legacy capture helpers are `frozen-nonqualifying`; this is an
exclusion, not a pass.

- [ ] **Step 3: Apply the shared sanitizer at unsafe sinks**

Sanitize before JSONL append, observability export, JSON-RPC/stderr exception emission, progress
ledger append, serialized agent state write, release transcript/runner retention, and Gateway error
response. Preserve required protocol content that is safe-by-construction; do not sanitize source
mutation payloads as if they were diagnostic logs.

- [ ] **Step 4: Test fail-closed sink behavior**

For each changed sink, inject nested, free-text, URI, split, and unsupported-object canaries. Assert
the raw value is absent, rule identifiers/counts are content-free, and sanitizer/audit failure does
not fall back to raw `str(exc)` or `repr`.

- [ ] **Step 5: Run and review Task 7**

```bash
uv run python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
uv run pytest tests/unit/tools/test_verify_plan996_logging_surfaces.py tests/unit/telemetry tests/unit/loops tests/unit/agent/test_state_store.py tests/unit/release tests/unit/acp/test_outbound_errors.py tests/unit/acp/test_stdio_ndjson.py tests/unit/optimus_gateway -q
uv run ruff check src/optimus src/optimus_gateway tools/verify_plan996_logging_surfaces.py tests/unit
git diff --check
```

Expected: verifier reports zero unclassified/stale sinks and all targeted tests pass. Wait for
approval. After approval only:

```bash
git add tools/verify_plan996_logging_surfaces.py docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json src/optimus/acp/server.py src/optimus/acp/dispatcher.py src/optimus/telemetry/jsonl.py src/optimus/telemetry/observability.py src/optimus/telemetry/serialization.py src/optimus/loops/ledger.py src/optimus/agent/state_store.py src/optimus/release/runner.py src/optimus/release/agent_smoke_transcript.py src/optimus_gateway/responses.py tests/unit/tools/test_verify_plan996_logging_surfaces.py tests/unit/telemetry/test_jsonl.py tests/unit/telemetry/test_observability.py tests/unit/telemetry/test_serialization.py tests/unit/loops/test_ledger.py tests/unit/agent/test_state_store.py tests/unit/release/test_runner.py tests/unit/optimus_gateway/test_responses.py tests/unit/acp/test_outbound_errors.py tests/unit/acp/test_stdio_ndjson.py
git commit -m "Enforce sanitizer across diagnostic sinks"
```

---

### Task 8: Sanitize ACP/`acpx` Streams Before Disk and Gate Transcript Promotion

**Deliverable:** The Plan 9.96 capture path never creates a raw interim transcript and cannot
promote cross-line/chunk secret leakage.

**Files:**
- Modify: `src/optimus/acp/e2e_transcript.py`
- Modify: `src/optimus/acp/ndjson_subprocess_session.py`
- Modify: `tests/unit/acp/test_e2e_transcript.py`
- Create: `tools/run_plan996_acpx_security_evidence.py`
- Create: `tests/unit/tools/test_run_plan996_acpx_security_evidence.py`

**Tool CLI:**

```text
run_plan996_acpx_security_evidence.py capture
  --workspace PATH --output-dir PATH --mode ordinary|elevated
  [--agent-approval-id ID --launch-session-id ID --diagnostic-grant-id ID]
run_plan996_acpx_security_evidence.py verify
  --transcript PATH --manifest PATH
```

- [ ] **Step 1: Write failing pre-persistence transcript tests**

Assert inbound/outbound records and stderr are sanitized before entering retained lists. Keep the
process-environment structural rejection. Split one canary across every adjacent line/chunk pair and
assert no prefix or suffix reaches disk.

- [ ] **Step 2: Implement a streaming `acpx` capture**

Use `subprocess.Popen` with argument lists and `shell=False`. Feed stdout/stderr incrementally into
`StreamingTextSanitizer`; write only released sanitized text. Do not use `capture_output=True`,
`proc.stdout` whole-buffer persistence, a raw temp file, or either frozen legacy helper. Preflight
records installed `acpx --version` and accepts independently authored `acpx` 0.12.0 or a successor
whose provenance/version is explicitly reviewed and recorded; a project-authored ACP client fails
the evidence preflight.

- [ ] **Step 3: Add joined promotion scanning and signed manifest**

Before secrets leave memory, join decoded transcript records and scan exact known values plus
canaries/patterns. Write a compact manifest containing sanitizer version, rule counts, artifact
SHA-256, joined-scan result, and HMAC; never include secret material. The standalone verification
mode loads the approval HMAC key through the read-only keyring adapter and verifies the manifest
HMAC before rechecking artifact/manifest digests, JSON strings, canaries, patterns, and the recorded
promotion decision. Evidence cleanup occurs only after this verification; the durable report keeps
the artifact/manifest SHA-256s and observed HMAC-verification result. A hit quarantines the artifact
and exits nonzero.

- [ ] **Step 4: Prove the legacy exclusion**

The tool/verifier rejects a Plan 9.87/9.88 raw transcript locator as Plan 9.96 evidence and names the
controlled Plan 9.96 capture command. Assert neither frozen helper has a Git diff.

- [ ] **Step 5: Run and review Task 8**

```bash
uv run pytest tests/unit/acp/test_e2e_transcript.py tests/unit/acp/test_live_fixture_policy.py tests/unit/tools/test_run_plan996_acpx_security_evidence.py -q
uv run ruff check src/optimus/acp/e2e_transcript.py src/optimus/acp/ndjson_subprocess_session.py tools/run_plan996_acpx_security_evidence.py tests/unit/acp tests/unit/tools/test_run_plan996_acpx_security_evidence.py
git diff --quiet -- tools/run_plan987_acpx_live_evidence.py tools/run_plan988_fu4b_live_evidence.py
git diff --check
```

Expected: tests pass, frozen helpers have no diff, and no raw-output write path exists in the new
tool. Wait for approval. After approval only:

```bash
git add src/optimus/acp/e2e_transcript.py src/optimus/acp/ndjson_subprocess_session.py tests/unit/acp/test_e2e_transcript.py tools/run_plan996_acpx_security_evidence.py tests/unit/tools/test_run_plan996_acpx_security_evidence.py
git commit -m "Sanitize ACP evidence before persistence"
```

---

### Task 9: Prove Real Launch Trust, Produce Evidence, and Close Only Plan 9.96

**Deliverable:** Real Credential Manager/keyring, Redis, Gateway, agent, and independent `acpx`
evidence maps every Plan 9.96 claim to a named artifact; living docs close only the two owned FUs.

**Files:**
- Create: `tests/e2e/acp/test_plan996_authorized_launch.py`
- Create: `reports/plan-9-96-operator-debug-launch-trust-evidence.md`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Modify: this plan's checkboxes/status only after the corresponding gates pass

- [ ] **Step 1: Run the real OS-store one-shot/durable ceremony**

In an external scratch workspace, use the real installed `optimus-trust` and OS keyring. Prove:

1. unapproved provider/base/key/Redis/config override stops before network/process activity;
2. a one-shot launch succeeds once and replay fails;
3. an interactively authored durable approval supports a headless launch;
4. changing one exact security value invalidates the approval;
5. approval entries are cleaned up after evidence.

Record approval IDs/digests and result codes only, never values/nonces. A fake keyring cannot satisfy
this step.

- [ ] **Step 2: Run real Redis/Gateway/agent/`acpx` ordinary and elevated sessions**

Use only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` in the agent child, real TimeSeries Redis, real
Gateway credentials, and independently authored `acpx`. The controlled Task 8 helper captures both
sessions. Assert expected mode, tools, cost band, final state, zero pre-approval mutation, exact
child-key manifest, ordinary no-tags behavior, elevated allowlisted provenance/tags, and terminal
`end_turn`.

Run from a TTY, using an external scratch root:

```bash
optimus-trust approve --mode durable --workspace-root C:/tmp/optimus-plan996-evidence
uv run python tools/run_plan996_acpx_security_evidence.py capture --workspace C:/tmp/optimus-plan996-evidence --output-dir C:/tmp/optimus-plan996-artifacts/ordinary --mode ordinary
optimus-trust run --elevated-debug --workspace-root C:/tmp/optimus-plan996-evidence -- uv run python tools/run_plan996_acpx_security_evidence.py capture --workspace C:/tmp/optimus-plan996-evidence --output-dir C:/tmp/optimus-plan996-artifacts/elevated --mode elevated --agent-approval-id {approval_id} --launch-session-id {launch_session_id} --diagnostic-grant-id {diagnostic_grant_id}
uv run pytest tests/e2e/acp/test_plan996_authorized_launch.py -m e2e -q
```

Expected: both controlled sessions complete through real `acpx`; the elevated command substitutes
identifiers without printing them; the E2E node passes with the real process and dependencies.

- [ ] **Step 3: Verify promotion and secret absence**

Run the capture helper's standalone verify mode on every promoted transcript/manifest. Then scan the
log, transcript, audit, report draft, Gateway log, telemetry export fixture, and state/ledger
artifacts for the registered evidence canaries and known secret patterns. Expected: zero hits; no
raw interim file exists.

```bash
uv run python tools/run_plan996_acpx_security_evidence.py verify --transcript C:/tmp/optimus-plan996-artifacts/ordinary/transcript.ndjson --manifest C:/tmp/optimus-plan996-artifacts/ordinary/sanitizer-manifest.json
uv run python tools/run_plan996_acpx_security_evidence.py verify --transcript C:/tmp/optimus-plan996-artifacts/elevated/transcript.ndjson --manifest C:/tmp/optimus-plan996-artifacts/elevated/sanitizer-manifest.json
optimus-trust revoke --workspace-root C:/tmp/optimus-plan996-evidence
```

Expected: both verifications pass before revocation; revocation removes durable approval and
diagnostic residue without deleting evidence artifacts.

- [ ] **Step 4: Run focused and full automated gates**

```bash
uv run pytest tests/unit/acp tests/unit/security tests/unit/telemetry tests/unit/tools/test_verify_plan996_logging_surfaces.py tests/unit/tools/test_run_plan996_acpx_security_evidence.py tests/integration/acp/test_launch_trust_flow.py -q
uv run pytest -q
uv run pytest --cov=optimus --cov=optimus_gateway --cov=optimus_security --cov-branch --cov-report=term-missing --cov-fail-under=80 -q
uv run ruff check .
uv run python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
git diff --check
```

Expected: all selected/default tests pass, aggregate production coverage is at least 80%, Ruff and
audit verifier pass, and the diff is clean.

- [ ] **Step 5: Create the claim-to-evidence report**

Record the Task 0 digest/approvals, implementation SHA before report/docs closure, registry and sink
manifest digests, exact test nodes/commands/results, OS-store backend identity, one-shot/durable
outcomes, TOCTOU matrix, exact child-key names, real dependency provenance, transcript/debug/audit
locators and SHA-256s, joined promotion result, secret-scan command/result, coverage, Ruff, and
limitations. Do not include secret or workspace content.

- [ ] **Step 6: Update living custody only after evidence passes**

Close `P9.85-FU-7` and `P9.9-FU-1` in README/roadmap with the implementation SHA and evidence report.
Preserve Plan 9.97 and its exact isolation sentence. Do not edit the security contract, approval
record, Plan 9.87/9.88 plans/helpers, or later-plan scope.

- [ ] **Step 7: Run final custody/freeze checks**

```bash
uv run python -c "from pathlib import Path; import hashlib; p=Path('docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md'); print(hashlib.sha256(p.read_bytes()).hexdigest().upper())"
rg -n "P9\.85-FU-7|P9\.9-FU-1|P9\.87-FU-1|must not absorb or be absorbed by Plan 11" README.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md
git diff --quiet -- docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md docs/superpowers/reviews/2026-07-15-plan-9-96-security-contract-approval.md tools/run_plan987_acpx_live_evidence.py tools/run_plan988_fu4b_live_evidence.py
rg -n "^- \[ \]" docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md
git status --short
```

Expected: exact frozen digest, Plan 9.96 FUs closed with evidence, Plan 9.97 sentence present, frozen
paths unchanged, zero unchecked-checkbox matches, and status contains only reviewed Plan 9.96 files
plus separately disclosed operator-owned noise.

- [ ] **Step 8: Request final sign-off and commit only after approval**

Show the evidence report, exact diff, all gate outputs, and status to the reviewer-agent and
operator. Commit closure files only after both approve. Do not stage `.idea`, `.claude`, `.cursor`,
`.superpowers`, secret/env files, unrelated `uv.lock`, or operator scratch artifacts.

After both approvals only:

```bash
git add tests/e2e/acp/test_plan996_authorized_launch.py reports/plan-9-96-operator-debug-launch-trust-evidence.md README.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md
git commit -m "Record Plan 9.96 launch trust evidence"
```

## Definition of Done

- [ ] Task 0 proves the exact frozen contract, both approvals, and Plan 9.9 commit before mutation.
- [ ] Every source-referenced Optimus/provider setting has exactly one mechanically checked policy.
- [ ] Unknown and inherited internal-only settings fail before workspace/config writes,
  debug/telemetry persistence, network, Redis, Gateway, agent, or subprocess side effects; the
  mandatory value-safe rejection audit is the only persisted outcome.
- [ ] Trusted roots ignore inherited APPDATA/LOCALAPPDATA/HOME/XDG and gated config-root values.
- [ ] Workspace identity detects path, file identity, Git common-dir, symlink/junction, and relocation
  changes.
- [ ] Approval records contain no literal secret/URI userinfo, fit 1,800 bytes, and fail on integrity,
  expiry, revocation, version, workspace, or exact-value mismatch.
- [ ] One-shot records use 256-bit nonce handles, a real OS lock, delete-before-use, and no replay.
- [ ] Headless launches consume only previously interactive durable approvals.
- [ ] Provider/base URL are displayed literally; Redis and other URI user information is masked.
- [ ] Monotonic cost/turn controls tighten without approval and cannot loosen without exact approval.
- [ ] Agent model selection remains bounded by authorized routing/endpoint/credentials, recognized
  pricing, protected ceiling, and the existing runtime request budget.
- [ ] Gateway and agent children contain exactly registry-authorized names; the agent remains one-key.
- [ ] No gated startup path performs a late ambient-environment/config/keyring reread.
- [ ] Every launch decision appends the complete value-safe audit schema before child startup, and
  audit failure is fatal.
- [ ] No literal-secret debug opt-out exists; elevated diagnostics expose only allowlisted metadata
  and session-local tags.
- [ ] Every discovered persistence/export surface has one verified audit disposition and no stale or
  unclassified manifest entry.
- [ ] Structured, free-text, unsupported-object, URI, exception, line-split, and chunk-split canaries
  are sanitized before persistence.
- [ ] Controlled real-`acpx` capture writes no raw interim artifact and joined promotion scans pass.
- [ ] Frozen Plan 9.87/9.88 helpers remain unchanged and non-qualifying for Plan 9.96.
- [ ] Real OS keyring, Redis, Gateway, agent, and independent-`acpx` evidence maps every claim to a
  named sanitized artifact.
- [ ] Full default tests pass, aggregate coverage across all production packages is at least 80%,
  Ruff/audit/diff checks pass, and secret scans have zero hits.
- [ ] Only `P9.85-FU-7` and `P9.9-FU-1` close; Plan 9.97 retains its Plan 11 isolation sentence.
- [ ] Final reviewed commit excludes all unrelated worktree and operator-local artifacts.

## Implementation Handoff After Plan Approval

1. Merge the reviewed docs-only planning branch first.
2. Create a fresh implementation branch/worktree from the latest `origin/main`; never implement on
   this planning branch or fork from another feature branch.
3. Re-open the exact on-disk security contract, approval record, and this plan. Use
   `superpowers:executing-plans` plus `superpowers:test-driven-development`.
4. Run Task 0 before any mutation. Stop on a digest/approval/object mismatch.
5. Execute one task at a time. At every boundary show focused tests, Ruff, exact diff, and status;
   wait for explicit operator approval before committing.
6. Stop on any contract/HLD/LLD/Test Strategy/live-behavior conflict and request a reviewed
   amendment. Never improvise a security exception.

## Plan Self-Review Record

- **Contract coverage:** Every scope, threat, tier, approval, TOCTOU, diagnostics, sink, transcript,
  evidence, failure, and freeze section maps to a named task and evidence node.
- **Scope fidelity:** Only the two Plan 9.96 follow-ups are implemented; Plans 9.97/10/11 and frozen
  evidence lanes remain separate.
- **Registry fidelity:** All 18 concrete `OPTIMUS_*` variables plus the one prefix literal and eight
  provider-key names are covered by one source of truth and AST inventory.
- **Approval fidelity:** Writer/reader roles, keyring circularity, same-user limitation, record size,
  HMAC domains, durable/headless behavior, one-shot handoff, lock, deletion, and replay are explicit.
- **Launch fidelity:** Candidate resolution precedes side effects; credentials/config are read once;
  the same snapshot is revalidated; child key sets are exact.
- **Diagnostic fidelity:** Elevated mode is metadata-only; there is no redaction bypass or arbitrary
  correlation oracle.
- **Audit fidelity:** Static surface discovery, manifest ownership, shared neutral sanitizer, and
  sink-level canary tests replace narrative “audit logging” claims.
- **Transcript fidelity:** Streaming pre-disk sanitization and joined promotion scans are separate
  mandatory gates; frozen raw helpers are honestly excluded.
- **Evidence fidelity:** Unit fakes stay unit-only; final claims require real OS store, Redis,
  Gateway, agent, and independent `acpx`.
- **Placeholder scan:** No unresolved placeholder, cross-task shorthand, unspecified error handling,
  or unnamed evidence gate remains.
