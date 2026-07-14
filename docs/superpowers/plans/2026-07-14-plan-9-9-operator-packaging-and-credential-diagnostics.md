# Plan 9.9 Operator Packaging and Credential Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Approved by the reviewer agent and operator on 2026-07-14. Implementation must start from a fresh worktree and branch from latest `main` per the handoff below.

**Goal:** Make `optimus-agent` safe and predictable from editable and non-editable installations by separating operator-owned configuration from workspace-owned runtime files, diagnosing provable provider/key mismatches before gateway spawn, and proving the packaged path with a real independently authored ACP client.

**Architecture:** Replace inferred repository roots with an explicit `OperatorPaths` contract: the workspace owns agent-visible files and `.optimus/` logs, while credentials come from an operator-owned configuration directory that can never resolve at or below the workspace. Credential resolution returns content-free provenance, fails only on provable keyring-pair conflicts or wrong-variable cases, and preserves compatible mixed-layer precedence. A checked-in verifier builds and installs a wheel outside the repository; its offline half runs in CI and its live half is an operator-run evidence tier using real Redis, the real local Gateway/model, and real `acpx`.

**Tech Stack:** Python 3.14+, standard-library `pathlib`, `PureWindowsPath`, `enum`, `dataclasses`, `keyring`, `pytest`, `pytest-asyncio`, `pytest-cov`, Ruff, `uv`, wheel/setuptools packaging, GitHub Actions, real `acpx` 0.12.0 or the repository-approved successor, real TimeSeries-capable Redis, and the real Optimus Gateway.

**Design approval:** Reviewer round 2 and operator approved the revised design on 2026-07-14. Requirements R1-R7 in that approval are mandatory plan content and map to the Requirements Traceability table below.

## Global Constraints

1. **Exactly two implementation seeds:** This plan implements only the roadmap's cross-layer provider/key diagnostics and non-editable-install root contract. Anything not under **Explicit Exceptions** remains in scope; anything added to implementation scope requires an approved plan amendment.
2. **Operator-owned credentials:** `workspace_root` must never be an implicit credential/configuration root. `.env.gateway` used by `optimus-agent` lives under the resolved operator config root, not in the opened repository.
3. **Config-root precedence:** Resolve `OPTIMUS_CONFIG_ROOT` first when it is a non-empty absolute path; otherwise use `%APPDATA%/optimus-cost-agent` on Windows, `$XDG_CONFIG_HOME/optimus-cost-agent` when set on POSIX, or `~/.config/optimus-cost-agent` as the POSIX fallback. `OPTIMUS_CONFIG_ROOT` is a non-secret path setting, not another credential.
4. **Containment is fail-closed:** Resolve both candidate config root and workspace root before comparing them. Use `Path.is_relative_to()` on POSIX and case-folded `PureWindowsPath.is_relative_to()` semantics on Windows. Reject equality and descendants. Never use string-prefix containment.
5. **Actionable migration:** A rejected or missing legacy `.env.gateway` path names the safe destination and remediation: move `.env.gateway` to the displayed operator config directory or set `OPTIMUS_CONFIG_ROOT` to an absolute directory outside the workspace. Messages name paths, layers, and variable names only.
6. **Credential conflict predicate:** Mixed layers are supported. Fail closed only when a key loaded from keyring conflicts with the provider stored alongside it, or when an explicitly configured provider (environment, config file, or keyring provenance) has only the wrong provider-specific environment/config variable available. The wrong-variable predicate never fires for `CredentialLayer.DEFAULT`. A keyring key with no stored provider is unprovable and warns rather than fails.
7. **No secret disclosure:** Provider keys, the local shared secret, authorization values, credentialed URLs, and raw keyring values must not appear in exceptions, warnings, `repr`, stderr, gateway-start messages, debug trace, packaging evidence, or committed reports.
8. **One-key agent boundary:** The spawned agent receives only Optimus credentials (`OPTIMUS_GATEWAY_URL`, `OPTIMUS_API_KEY`) plus non-secret runtime settings. Provider keys may enter only the local Gateway child environment and must be stripped before preflight, configured-server construction, ACP serving, telemetry, or `acpx` invocation.
9. **Root vocabulary is exact:** `workspace_root` is the code-operation boundary; `config_root` is the operator-owned `.env.gateway` boundary; `runtime_root` is `<workspace_root>/.optimus`; installed Python modules are package resources, not a `project_root`. Do not reuse `project_root` for two meanings.
10. **Gateway singleton semantics:** A gateway already reachable on the configured loopback port is reused and creates no log in the current workspace. When this process starts the singleton, its log is `<starting-workspace>/.optimus/local-gateway.log`; later workspaces reuse that process and therefore do not acquire a new gateway log.
11. **No editable-install dependency:** Product runtime code must not infer `Path(__file__).parents[3]`, prepend `<repo>/src` to `PYTHONPATH`, or assume `reports/` exists beside installed packages. Repo-only tooling receives its repository root explicitly from its wrapper.
12. **Evidence tiers are real:** Unit tests may use fake keyrings/processes. The packaging proof must use a wheel installed non-editably outside the checkout. Live sign-off must use real TimeSeries-capable Redis, the real local Gateway/model, and independently authored `acpx`; project-authored ACP clients cannot satisfy the live claim.
13. **CI/operator split:** The checked-in packaging verifier's offline wheel-build/install/import/path checks run in GitHub Actions. Its live `acpx` mode is operator-run only because it needs keyring state, Docker/Redis, Gateway credentials, a paid model call, and approval/mutation in a scratch workspace.
14. **Frozen history:** Do not edit the architectural Plan 9.6 file, Plan 9.7, Plan 9.8, Plan 9.85, Plan 9.87, Plan 9.88, or any existing `reports/*` artifact. `docs/superpowers/plans/2026-07-10-plan-9-6-phase-c-operator-runbook.md` is the living operator runbook and may be updated. Create a new Plan 9.9 report instead of rewriting prior evidence.
15. **Approval-gated commits:** At every task boundary, show the exact diff and named verification output, wait for explicit operator approval, then commit only the task's listed files. Never use `--no-verify`.
16. **Checkbox protocol:** Set `- [x]` only after that step's literal command ran and passed. A prose summary is not verification.
17. **Quality gates:** Before each code commit, run the task's focused tests, Ruff on changed Python, and `git diff --check`. Final sign-off requires the full non-live suite, aggregate production coverage at or above 80%, full Ruff, the offline packaging verifier, and disclosed live-tier outcomes.

---

## Requirements Traceability

| Approval obligation | Owning tasks | Mechanical evidence |
|---|---|---|
| R1: resolved, case-insensitive Windows containment using `is_relative_to` | Task 1 | `test_config_root_rejects_case_variant_workspace_descendant_on_windows`, no prefix comparison in source |
| R2: actionable migration; update living docs only | Tasks 1 and 6 | exact error-text tests; frozen-path diff gate; README/runbook/roadmap diff |
| R3: partial keyring state warns | Task 2 | `test_keyring_key_without_stored_provider_warns_and_resolves` |
| R4: `--setup` uses config root before secret resolution | Task 3 | `test_setup_uses_operator_config_root_not_workspace` |
| R5: gateway singleton log semantics and secret-free startup output | Task 3 | singleton/no-log and log-message redaction tests; runbook wording |
| R6: checked-in pinned packaging script and named live prerequisites | Tasks 4 and 5 | CI offline command plus real `acpx` report |
| R7: workspace-influenced environment residual risk remains tracked | Task 6 | `P9.9-FU-1` in this plan and roadmap |

## Explicit Exceptions

- `P9.87-FU-1` mechanical current-raw-evidence grounding guard remains unresolved, outside this packaging/credential lane, and owned by Plan 9.95; it must not absorb or be absorbed by Plan 11 and may split when scheduled.
- `P9.85-FU-6` billable failed-retry aggregation and unknown transport cost remains unresolved, outside this lane, and owned by Plan 9.95.
- `P9.88-FU-2` ledger digest specification/helper remains unresolved, outside this lane, and owned by Plan 9.95.
- `P9.88-FU-3` read-range telemetry ordering remains unresolved, outside this lane, and owned by Plan 9.95.
- `P9.85-FU-7` deliberate-access design for redacted debug traces remains outside this lane and owned by Plan 9.95; its redaction opt-out requires a separate security review at scheduling time. This plan relocates logs but does not add an unredacted mode or broaden trace content.
- Plan 9.87 FU-4B remains accepted-open under the Plan 9.88 exhaustion ceremony. Plan 9.9 neither retries nor reclassifies it.
- Plan 10 gateway capability brokering and provider-side capability secrets remain separate.
- Plan 11 context selection/compression remains separate.
- The repo-explicit manual launchers `tools/run_local_gateway.sh` and `tools/run_local_gateway.ps1` continue to load the checkout's `.env.gateway`; they are an explicit developer action, not `optimus-agent`'s implicit config discovery path.
- Linux/WSL keyring backend redesign, hosted-Gateway behavior changes, Docker Desktop auto-start, provider API redesign, and publishing the package to PyPI are not part of Plan 9.9.

## File and Responsibility Map

- Create `src/optimus/acp/operator_paths.py`: pure workspace/config/runtime root resolution, Windows-aware containment, and actionable path errors.
- Create `tests/unit/acp/test_operator_paths.py`: R1 containment, defaults, override, migration text, and no-I/O path tests.
- Modify `src/optimus/acp/local_gateway_secrets.py`: content-free credential provenance, exact mismatch predicate, wrong-variable diagnostics, partial-keyring warning, and `config_root` vocabulary.
- Modify `tests/unit/acp/test_local_gateway_secrets.py`: complete provider/key/source matrix and non-disclosure tests.
- Modify `src/optimus/acp/local_infra.py`: consume `config_root`/`runtime_root`, surface warnings before spawn, remove source-tree `PYTHONPATH`, and place the owned gateway log under `.optimus/`.
- Modify `tests/unit/acp/test_local_infra.py`: fail-before-spawn, singleton log ownership, child-env boundary, and secret-free startup-message tests.
- Modify `src/optimus/acp/__main__.py`: resolve `OperatorPaths` once, route `--setup` through `config_root`, and pass explicit roots to all consumers.
- Modify `tests/unit/acp/test_main_wiring.py`, `tests/unit/acp/test_main_check_config.py`, and `tests/unit/acp/test_main_debug_trace.py`: CLI root wiring and early path-failure coverage.
- Modify `src/optimus/acp/debug_trace.py` and `tests/unit/acp/test_debug_trace.py`: remove package-tree fallback and use explicit runtime/provenance roots without changing redaction semantics.
- Modify `src/optimus/acp/subprocess_env.py` and `tests/unit/acp/test_acp_subprocess_env.py`: remove editable-only `PYTHONPATH` injection and the ambiguous `project_root` argument.
- Modify `src/optimus/acp/operator_verify.py`, `tools/verify_live_agent.py`, and `tests/integration/release/test_verify_live_agent_cli.py`: inject the repository root explicitly only for repo-owned verification artifacts.
- Create `tools/verify_plan99_noneditable_install.py`: offline wheel/install/import/path verification plus operator-only real-`acpx` mode and sanitized report generation.
- Create `tests/unit/tools/test_verify_plan99_noneditable_install.py`: deterministic command construction, installed-path assertions, report redaction, and live-prerequisite rejection.
- Modify `.github/workflows/guardrails.yml`: run the verifier's offline mode after the existing dependency setup.
- Create `reports/plan-9-9-operator-packaging-evidence.md`: redacted wheel, path, config, log, `acpx`, Gateway, Redis, permission, mutation, and result evidence for this plan only.
- Modify `README.md`: non-editable install, safe `.env.gateway` location/migration, singleton logs, and the operator packaging command.
- Modify `docs/superpowers/plans/2026-07-10-plan-9-6-phase-c-operator-runbook.md`: living Phase C install/config/log commands only; do not alter historical evidence artifacts.
- Modify `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`: Plan 9.9 completion state, Plan 9.8 handoff, exact deferrals, and `P9.9-FU-1`.

---

### Task 1: Establish the Operator-Owned Path Contract

**Deliverable:** A pure, tested root resolver makes workspace/config/runtime ownership explicit and rejects workspace-contained configuration on Windows and POSIX.

**Files:**
- Create: `src/optimus/acp/operator_paths.py`
- Create: `tests/unit/acp/test_operator_paths.py`

**Interfaces:**
- Consumes: `--workspace-root` text and a `Mapping[str, str]` environment.
- Produces: `OperatorPaths(workspace_root: Path, config_root: Path, runtime_root: Path, debug_log_path: Path, gateway_log_path: Path)`, `OperatorPathConfigurationError(user_message: str, exit_code: int = 2)`, `resolve_operator_paths(...) -> OperatorPaths`, and `resolve_config_root(...) -> Path`.

- [x] **Step 1: Write failing default, override, and containment tests**

Evidence (2026-07-14): failing tests authored first in `tests/unit/acp/test_operator_paths.py` (TDD); landed in `0265f8e2bd6a8eaff80ecc578cc4fadae2c70ddc`.

Create tests with these exact behaviors:

```python
def test_windows_default_config_root_uses_appdata_outside_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    appdata = tmp_path / "operator" / "AppData" / "Roaming"
    paths = resolve_operator_paths(
        workspace_root=workspace,
        environ={"APPDATA": str(appdata)},
        platform_name="win32",
    )
    assert paths.workspace_root == workspace.resolve()
    assert paths.config_root == (appdata / "optimus-cost-agent").resolve()
    assert paths.runtime_root == (workspace / ".optimus").resolve()
    assert paths.debug_log_path == paths.runtime_root / "debug-acp.ndjson"
    assert paths.gateway_log_path == paths.runtime_root / "local-gateway.log"


def test_absolute_config_override_outside_workspace_wins(tmp_path):
    workspace = tmp_path / "workspace"
    config = tmp_path / "operator-config"
    paths = resolve_operator_paths(
        workspace_root=workspace,
        environ={"OPTIMUS_CONFIG_ROOT": str(config)},
        platform_name="win32",
    )
    assert paths.config_root == config.resolve()


@pytest.mark.parametrize("suffix", ["", "config", "nested/config"])
def test_config_root_rejects_workspace_or_descendant(tmp_path, suffix):
    workspace = tmp_path / "workspace"
    candidate = workspace / suffix
    with pytest.raises(OperatorPathConfigurationError, match="Move .env.gateway"):
        resolve_operator_paths(
            workspace_root=workspace,
            environ={"OPTIMUS_CONFIG_ROOT": str(candidate)},
            platform_name="win32",
        )


def test_config_root_rejects_case_variant_workspace_descendant_on_windows(tmp_path):
    workspace = tmp_path / "WorkSpace"
    candidate = tmp_path / "workspace" / "CONFIG"
    assert _is_at_or_below(candidate, workspace, windows=True)


def test_string_prefix_sibling_is_not_treated_as_descendant(tmp_path):
    workspace = tmp_path / "repo"
    sibling = tmp_path / "repo-safe-config"
    assert not _is_at_or_below(sibling, workspace, windows=False)
```

Also test: relative `OPTIMUS_CONFIG_ROOT` fails; missing `%APPDATA%` on simulated Windows fails with an action message; POSIX uses `XDG_CONFIG_HOME` then `~/.config`; symlink/`..` inputs are resolved before containment; no directory is created by resolution.

- [x] **Step 2: Run the tests and verify the contract is absent**

Evidence (2026-07-14): `uv run python -m pytest tests/unit/acp/test_operator_paths.py -v` failed collection with `ModuleNotFoundError: No module named 'optimus.acp.operator_paths'` before implementation (Task 1 implementer report).

Run:

```bash
python -m pytest tests/unit/acp/test_operator_paths.py -v
```

Expected: collection/import failure because `optimus.acp.operator_paths` does not exist.

- [x] **Step 3: Implement the pure resolver and exact remediation error**

Evidence (2026-07-14): `src/optimus/acp/operator_paths.py` matches the planned public shape (safe-default precompute before override validation); committed `0265f8e`.

Implement this public shape; keep `_is_at_or_below` injectable/testable so Windows semantics are exercised on non-Windows CI:

```python
from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath


class OperatorPathConfigurationError(ValueError):
    def __init__(self, user_message: str, *, exit_code: int = 2) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.exit_code = exit_code


@dataclass(frozen=True)
class OperatorPaths:
    workspace_root: Path
    config_root: Path
    runtime_root: Path
    debug_log_path: Path
    gateway_log_path: Path


def _is_at_or_below(candidate: Path, workspace: Path, *, windows: bool) -> bool:
    resolved_candidate = candidate.resolve()
    resolved_workspace = workspace.resolve()
    if windows:
        folded_candidate = PureWindowsPath(str(resolved_candidate).casefold())
        folded_workspace = PureWindowsPath(str(resolved_workspace).casefold())
        return folded_candidate.is_relative_to(folded_workspace)
    return resolved_candidate.is_relative_to(resolved_workspace)
```

`resolve_config_root(...)` must calculate the safe default before validating an override so the error can say:

```python
message = (
    f"Refusing to load local gateway configuration from {candidate} because it is inside "
    f"workspace {workspace}. Move .env.gateway to {safe_default} or set OPTIMUS_CONFIG_ROOT "
    "to an absolute directory outside the workspace."
)
```

Return paths only; do not call `mkdir`, open a file, read `.env.gateway`, or mutate `os.environ` in this module.

- [x] **Step 4: Run focused tests and Ruff**

Evidence (2026-07-14, operator-reverified): `uv run python -m pytest tests/unit/acp/test_operator_paths.py -v` → 13 passed, 1 skipped (symlink privileges); `ruff check` clean; `git diff --check` clean.

Run:

```bash
python -m pytest tests/unit/acp/test_operator_paths.py -v
python -m ruff check src/optimus/acp/operator_paths.py tests/unit/acp/test_operator_paths.py
git diff --check
```

Expected: all path tests PASS, Ruff clean, diff check clean.

- [x] **Step 5: Review and commit Task 1 after explicit approval**

Evidence: operator approval 2026-07-14; commit `0265f8e2bd6a8eaff80ecc578cc4fadae2c70ddc` — `Define safe operator path boundaries` (exactly the two Task 1 files).

```bash
git add src/optimus/acp/operator_paths.py tests/unit/acp/test_operator_paths.py
git diff --cached --name-status
git diff --cached --check
git commit -m "Define safe operator path boundaries"
```

Expected: exactly the two Task 1 files are committed.

---

### Task 2: Resolve Provider Credentials with Content-Free Provenance

**Deliverable:** Credential resolution preserves supported precedence, fails on provable incompatibility, warns on partial/unprovable state, and never exposes key values.

**Files:**
- Modify: `src/optimus/acp/local_gateway_secrets.py`
- Modify: `tests/unit/acp/test_local_gateway_secrets.py`

**Interfaces:**
- Consumes: environment mapping, `config_root/.env.gateway`, and the existing keyring service fields `model_provider`, `model_provider_api_key`, and `local_gateway_shared_secret`.
- Produces: `CredentialLayer`, `CredentialProvenance`, `ProviderCredentialResolution`, `ProviderCredentialConfigurationError`, `resolve_provider_credentials(...) -> ProviderCredentialResolution`, `resolve_shared_secret(..., config_root=...)`, and updated `run_setup_wizard(config_root=...)`.

- [x] **Step 1: Write the credential decision-table tests first**

Evidence (2026-07-14): matrix + named R3/unsupported/ambient tests added in `tests/unit/acp/test_local_gateway_secrets.py`; operator traced all 12 plan rows; landed in `174cb3145366d9fb2e3518cd2a8f5d2b4ca5a7d1`.

Add this matrix as named tests; every row asserts no raw key appears in warnings, exception text, or `repr(result)`:

| Effective provider source | Key source | Keyring provider | Expected |
|---|---|---|---|
| env `openai` | keyring | `openrouter` | fail closed: provider/keyring pair mismatch |
| config `openai` | keyring | `openai` | pass, no conflict |
| env `openrouter` | keyring | absent | pass with partial-state warning |
| env `openrouter` | config generic key | any | pass with unprovable split warning |
| config `anthropic` | config `ANTHROPIC_API_KEY` | any | pass |
| env `anthropic` | only generic env/config key | absent | fail with `ANTHROPIC_API_KEY` remediation |
| env `openai` | only `ANTHROPIC_API_KEY` | absent | fail with `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY` remediation |
| keyring `openrouter` | keyring | `openrouter` | pass |
| default `openrouter` | no key | absent | return `secrets=None`, existing setup pointer remains available |
| default `openrouter` | only ambient `ANTHROPIC_API_KEY` | absent | return `secrets=None`, existing setup pointer remains available; no wrong-variable or conflict error |
| env/config unsupported provider | any | any | fail with supported-provider set; no values |
| keyring unsupported provider | keyring or absent | same unsupported value | fail closed with supported-provider set and `optimus-agent --setup` remediation |

Pin those boundaries with named tests `test_default_provider_with_only_ambient_anthropic_key_returns_setup_pointer`, parametrized `test_explicit_unsupported_provider_names_supported_set` for environment and config-file provenance, and `test_unsupported_keyring_provider_fails_closed_with_setup_remediation`. Construct each layer through public resolver inputs and assert the full result or exception text, including the supported set `anthropic, openai, openrouter`.

Pin the required R3 case:

```python
def test_keyring_key_without_stored_provider_warns_and_resolves(tmp_path):
    fake_keyring = FakeKeyring()
    fake_keyring.set_password("optimus-cost-agent", "model_provider_api_key", "sk-private-value")

    result = resolve_provider_credentials(
        {"OPTIMUS_LOCAL_GATEWAY_PROVIDER": "openrouter"},
        config_root=tmp_path,
        keyring_backend=fake_keyring,
    )

    assert result.secrets == ProviderSecrets(provider="openrouter", model_provider_api_key="sk-private-value")
    assert result.api_key_provenance.layer is CredentialLayer.KEYRING
    assert result.warnings == (
        "optimus-agent: provider key came from keyring but keyring has no stored model_provider; "
        "run `optimus-agent --setup` to restore the provider/key pair.",
    )
    assert "sk-private-value" not in repr(result)
```

- [x] **Step 2: Run the focused tests and verify they fail on the old independent resolver**

Evidence (2026-07-14): TDD RED before provenance implementation — new imports/assertions failed against the pre-Task-2 resolver (Task 2 implementer path / subsequent GREEN at 25 passed).

```bash
python -m pytest tests/unit/acp/test_local_gateway_secrets.py -v
```

Expected: new imports/assertions FAIL because provenance and precise diagnostics do not exist.

- [x] **Step 3: Implement provenance and the exact conflict predicate**

Evidence (2026-07-14): `resolve_provider_credentials` + keyring-pair / wrong-variable / DEFAULT-skip predicates in `src/optimus/acp/local_gateway_secrets.py`; KEYRING provenance only when a key is loaded; committed `174cb31`.

Use these immutable types:

```python
class CredentialLayer(str, Enum):
    ENVIRONMENT = "environment"
    CONFIG_FILE = "config_file"
    KEYRING = "keyring"
    DEFAULT = "default"
    MISSING = "missing"


@dataclass(frozen=True)
class CredentialProvenance:
    layer: CredentialLayer
    field_name: str


@dataclass(frozen=True)
class ProviderCredentialResolution:
    secrets: ProviderSecrets | None
    provider_provenance: CredentialProvenance
    api_key_provenance: CredentialProvenance
    base_url_provenance: CredentialProvenance
    warnings: tuple[str, ...] = ()


class ProviderCredentialConfigurationError(ValueError):
    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message
```

Resolution remains env -> `config_root/.env.gateway` -> keyring -> provider default. Validate the selected provider before resolving its key. An unsupported environment/config provider raises `ProviderCredentialConfigurationError` naming `anthropic, openai, openrouter`; an unsupported keyring provider raises the same typed error and additionally says to run `optimus-agent --setup`. Neither diagnostic contains credential values.

The keyring-pair failure predicate is exactly:

```python
if api_key_provenance.layer is CredentialLayer.KEYRING and stored_keyring_provider:
    if stored_keyring_provider.casefold() != effective_provider.casefold():
        raise ProviderCredentialConfigurationError(
            "optimus-agent: local gateway provider resolves to "
            f"{effective_provider!r} from {provider_provenance.layer.value}, but the keyring API key is paired "
            f"with provider {stored_keyring_provider!r}; run `optimus-agent --setup` or remove the "
            "higher-precedence provider override."
        )
```

Evaluate the two wrong-variable cases only when `provider_provenance.layer` is `ENVIRONMENT`, `CONFIG_FILE`, or `KEYRING`; skip them when it is `DEFAULT`. Do not infer provider identity from key prefixes. Do not fail merely because provider and key layers differ. For wrong-variable diagnostics, name the expected and found variable names but never their values. Mark key-bearing dataclass fields `repr=False` or provide a redacted `__repr__` so `repr(result)` cannot disclose the key through nested `ProviderSecrets`.

- [x] **Step 4: Change the setup wizard from `project_root` to `config_root`**

Evidence (2026-07-14): `run_setup_wizard(config_root=...)` and `resolve_shared_secret(..., config_root=...)` replace `project_root`; committed `174cb31`.

Change the signature to:

```python
def run_setup_wizard(
    *,
    config_root: Path,
    keyring_backend: Any = keyring,
    input_fn: Callable[[str], str] = input,
    getpass_fn: Callable[[str], str] = getpass.getpass,
    print_fn: Callable[..., None] = print,
) -> int:
```

Its precedence warning checks only `config_root / ".env.gateway"` and says that operator config file and explicit environment values outrank keyring. It must not inspect the workspace.

Change `resolve_shared_secret` from `project_root` to the same explicit `config_root` contract. Remove the obsolete independent-provider override helper and any imports used only by it; `resolve_provider_credentials` must preserve and test its unsupported-provider diagnostics, so local-infra callers cannot reconstruct a second, drifting predicate.

- [x] **Step 5: Run the complete credential matrix and static checks**

Evidence (2026-07-14, operator-reverified): `uv run python -m pytest tests/unit/acp/test_local_gateway_secrets.py -v` → 25 passed; `ruff check` clean; `git diff --check` clean.

```bash
python -m pytest tests/unit/acp/test_local_gateway_secrets.py -v
python -m ruff check src/optimus/acp/local_gateway_secrets.py tests/unit/acp/test_local_gateway_secrets.py
git diff --check
```

Expected: all existing and new credential tests PASS; no warning/exception/repr contains fixture key values.

- [x] **Step 6: Review and commit Task 2 after explicit approval**

Evidence: operator approval 2026-07-14; commit `174cb3145366d9fb2e3518cd2a8f5d2b4ca5a7d1` — `Diagnose local gateway credential conflicts` (exactly the two Task 2 files).

```bash
git add src/optimus/acp/local_gateway_secrets.py tests/unit/acp/test_local_gateway_secrets.py
git diff --cached --name-status
git diff --cached --check
git commit -m "Diagnose local gateway credential conflicts"
```

Expected: exactly the resolver and its unit tests are committed.

---

### Task 3: Wire Explicit Roots Through Startup, Logs, and Repo-Only Verification

**Deliverable:** All product startup paths consume `OperatorPaths`; mismatch diagnostics stop before spawn, logs use `.optimus/`, and no product path relies on an editable checkout.

**Files:**
- Modify: `src/optimus/acp/__main__.py`
- Modify: `src/optimus/acp/local_infra.py`
- Modify: `src/optimus/acp/debug_trace.py`
- Modify: `src/optimus/acp/subprocess_env.py`
- Modify: `src/optimus/acp/operator_verify.py`
- Modify: `tools/verify_live_agent.py`
- Modify: `tests/unit/acp/test_main_wiring.py`
- Modify: `tests/unit/acp/test_main_check_config.py`
- Modify: `tests/unit/acp/test_main_debug_trace.py`
- Modify: `tests/unit/acp/test_local_infra.py`
- Modify: `tests/unit/acp/test_debug_trace.py`
- Modify: `tests/unit/acp/test_acp_subprocess_env.py`
- Modify: `tests/integration/release/test_verify_live_agent_cli.py`

**Interfaces:**
- Consumes: Task 1 `resolve_operator_paths`; Task 2 `resolve_provider_credentials`.
- Produces: `apply_local_defaults(environ, *, config_root)`, `ensure_local_gateway(environ, *, config_root, runtime_root, log)`, `configure_debug_trace(enabled, *, log_path, provenance_root)`, `build_acp_subprocess_env(operator_environ)`, and `operator_verify.main(..., repository_root)`.

- [x] **Step 1: Write failing main/setup/path-error wiring tests**

Evidence (2026-07-14): setup/config-root and containment-before-infra tests in `tests/unit/acp/test_main_wiring.py` (and related); landed in `f37d4efd9ed65fa085c1955fcbdb813ac7bf2bb0`.

Add tests proving:

```python
def test_setup_uses_operator_config_root_not_workspace(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    config = tmp_path / "operator-config"
    captured = {}

    def fake_setup(*, config_root):
        captured["root"] = config_root
        return 0

    monkeypatch.setenv("OPTIMUS_CONFIG_ROOT", str(config))
    monkeypatch.setattr(acp_main, "run_setup_wizard", fake_setup)
    assert acp_main.main(["--workspace-root", str(workspace), "--setup"]) == 0
    assert captured["root"] == config.resolve()


def test_workspace_contained_config_root_exits_before_setup_or_infra(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("OPTIMUS_CONFIG_ROOT", str(workspace / "config"))
    setup = Mock()
    redis = Mock()
    monkeypatch.setattr(acp_main, "run_setup_wizard", setup)
    monkeypatch.setattr(acp_main, "ensure_local_redis", redis)
    assert acp_main.main(["--workspace-root", str(workspace), "--setup"]) == 2
    setup.assert_not_called()
    redis.assert_not_called()
```

Also assert `apply_local_defaults`, `ensure_local_gateway`, and debug configuration receive the same resolved root object from one `resolve_operator_paths` call.

- [x] **Step 2: Write failing local-gateway mismatch, singleton, and non-disclosure tests**

Evidence (2026-07-14): conflict-before-spawn, reused-gateway no second log, and non-disclosure assertions in `tests/unit/acp/test_local_infra.py`; committed `f37d4ef`.

Add these exact properties:

```python
def test_credential_conflict_stops_before_log_or_spawn(tmp_path, monkeypatch):
    runtime_root = tmp_path / "workspace" / ".optimus"
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    monkeypatch.setattr(
        local_infra,
        "resolve_provider_credentials",
        Mock(side_effect=ProviderCredentialConfigurationError("sanitized mismatch")),
    )
    popen = Mock()
    monkeypatch.setattr(local_infra.subprocess, "Popen", popen)
    messages = []
    assert local_infra.ensure_local_gateway(
        environ={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        config_root=tmp_path / "config",
        runtime_root=runtime_root,
        log=messages.append,
    ) is None
    popen.assert_not_called()
    assert not runtime_root.exists()
    assert messages == ["sanitized mismatch"]


def test_reused_gateway_creates_no_log_in_second_workspace(tmp_path, monkeypatch):
    runtime_root = tmp_path / "second-workspace" / ".optimus"
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: True)
    assert local_infra.ensure_local_gateway(
        environ={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        config_root=tmp_path / "config",
        runtime_root=runtime_root,
    ) is None
    assert not (runtime_root / "local-gateway.log").exists()
```

Extend the existing spawn test to assert the actual log path is `<runtime_root>/local-gateway.log`, and join every emitted startup message to prove neither provider key nor shared secret is present.

- [x] **Step 3: Write failing tests for removal of package-root and `PYTHONPATH` assumptions**

Evidence (2026-07-14): subprocess-env / operator_verify / debug-trace tests updated; plus tracked e2e custody and `provenance_root` follow-up test; committed `f37d4ef`.

Update subprocess-env expectations to:

```python
env = build_acp_subprocess_env(operator_environ=os.environ)
assert "PYTHONPATH" not in env
assert env["OPTIMUS_GATEWAY_URL"] == "http://127.0.0.1:8765"
assert env["OPTIMUS_API_KEY"] == "shared-secret"
assert "OPENAI_API_KEY" not in env
```

Update operator-verifier tests so `tools/verify_live_agent.py` passes its `ROOT` explicitly into `operator_verify.main(repository_root=ROOT)`. Test that default scratch/report paths derive from that explicit repository root, not `operator_verify.__file__`.

- [x] **Step 4: Run the focused tests and observe the old wiring failures**

Evidence (2026-07-14): TDD expected pre-wiring failures; a clean pre-implementation RED transcript was not captured (sandbox blocked the first pytest invoke before implementation). Post-wiring GREEN for the focused suite is recorded under Step 9.

```bash
python -m pytest \
  tests/unit/acp/test_main_wiring.py \
  tests/unit/acp/test_main_check_config.py \
  tests/unit/acp/test_main_debug_trace.py \
  tests/unit/acp/test_local_infra.py \
  tests/unit/acp/test_debug_trace.py \
  tests/unit/acp/test_acp_subprocess_env.py \
  tests/integration/release/test_verify_live_agent_cli.py -v
```

Expected: new root/signature/log assertions FAIL against the old `project_root` and editable-only behavior.

- [x] **Step 5: Resolve paths once at the top of `main()` and route `--setup` through them**

Evidence (2026-07-14): `src/optimus/acp/__main__.py` resolves `OperatorPaths` once and passes `config_root` into setup; committed `f37d4ef`.

Replace `_project_root()` with this control flow:

```python
workspace_root = Path(args.workspace_root).resolve()
try:
    paths = resolve_operator_paths(workspace_root=workspace_root, environ=os.environ)
except OperatorPathConfigurationError as exc:
    print(exc.user_message, file=sys.stderr)
    return exc.exit_code

if args.setup:
    return run_setup_wizard(config_root=paths.config_root)
```

Pass `paths.config_root` to `apply_local_defaults`; pass `paths.config_root` and `paths.runtime_root` to `ensure_local_gateway`; pass `paths.debug_log_path` and `paths.workspace_root` to debug configuration. The path error must happen before Redis, keyring reads, Gateway calls, state persistence, or file creation.

- [x] **Step 6: Wire credential diagnostics and `.optimus` gateway logs**

Evidence (2026-07-14): `ensure_local_gateway(..., config_root=, runtime_root=)` writes `<runtime_root>/local-gateway.log` and fails closed before spawn on credential conflict; committed `f37d4ef`. Live singleton path later corroborated under Task 5 (`live-workspace/.optimus/local-gateway.log`).

Change local-infra signatures and ordering:

```python
def apply_local_defaults(environ: Mapping[str, str], *, config_root: Path) -> dict[str, str]:
    resolved = dict(environ)
    if not resolved.get("OPTIMUS_REDIS_URL", "").strip():
        resolved["OPTIMUS_REDIS_URL"] = _DEFAULT_REDIS_URL
    if not resolved.get("OPTIMUS_GATEWAY_URL", "").strip():
        resolved["OPTIMUS_GATEWAY_URL"] = _DEFAULT_GATEWAY_URL
    if not _is_loopback(urlparse(resolved["OPTIMUS_GATEWAY_URL"]).hostname):
        return resolved
    if not resolved.get("OPTIMUS_PRODUCTION_MODE", "").strip():
        resolved["OPTIMUS_PRODUCTION_MODE"] = "false"
    if not resolved.get("OPTIMUS_AGENT_MODEL", "").strip():
        resolved["OPTIMUS_AGENT_MODEL"] = _DEFAULT_LOCAL_AGENT_MODEL
    if not resolved.get("OPTIMUS_API_KEY", "").strip():
        shared_secret = resolve_shared_secret(resolved, config_root=config_root)
        if shared_secret:
            resolved["OPTIMUS_API_KEY"] = shared_secret
    return resolved


def ensure_local_gateway(
    *,
    environ: Mapping[str, str],
    config_root: Path,
    runtime_root: Path,
    log: Callable[[str], None] = _noop_log,
) -> LocalGatewayProcess | None:
    gateway_url = environ.get("OPTIMUS_GATEWAY_URL", "").strip()
    if not gateway_url:
        return None
    parsed = urlparse(gateway_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8765
    if not _is_loopback(host) or _tcp_reachable(host, port):
        return None

    try:
        resolution = resolve_provider_credentials(environ, config_root=config_root)
    except ProviderCredentialConfigurationError as exc:
        log(exc.user_message)
        return None
    for warning in resolution.warnings:
        log(warning)

    provider_secrets = resolution.secrets
    shared_secret = resolve_shared_secret(environ, config_root=config_root)
    if provider_secrets is None or not shared_secret:
        log(
            "optimus-agent: no compatible local gateway credentials found "
            f"(run `optimus-agent --setup` or configure {config_root / '.env.gateway'}); "
            "leaving Gateway pre-flight to fail closed."
        )
        return None

    child_env: dict[str, str] = {
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER": provider_secrets.provider,
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": shared_secret,
        "OPTIMUS_LOCAL_GATEWAY_BIND_HOST": host,
        "OPTIMUS_LOCAL_GATEWAY_PORT": str(port),
        **provider_secrets.as_gateway_child_env(),
    }
    for key in _SYSTEM_ENV_KEYS:
        value = environ.get(key, "")
        if value:
            child_env[key] = value

    log_path = runtime_root / "local-gateway.log"
    try:
        runtime_root.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "ab")
    except OSError as exc:
        log(f"optimus-agent: could not prepare local gateway log file ({exc}); leaving Gateway pre-flight to fail closed.")
        return None
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "optimus_gateway"],
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        log(f"optimus-agent: could not start local gateway process ({exc}); leaving Gateway pre-flight to fail closed.")
        return None
    finally:
        log_file.close()

    log(f"optimus-agent: starting local gateway (pid {process.pid}); logging to {log_path}")
    deadline = time.monotonic() + _GATEWAY_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log(f"optimus-agent: local gateway exited early (code {process.returncode}); see {log_path}")
            return None
        if _tcp_reachable(host, port):
            return LocalGatewayProcess(process=process, log_path=log_path)
        time.sleep(_POLL_INTERVAL_SECONDS)
    log(f"optimus-agent: local gateway did not become ready in time; see {log_path}")
    LocalGatewayProcess(process=process, log_path=log_path).stop()
    return None
```

After loopback/reuse checks and before `runtime_root.mkdir` or `Popen`, call `resolve_provider_credentials`. Catch `ProviderCredentialConfigurationError`, emit only `user_message`, and return `None`. Emit every sanitized resolution warning. Remove `child_env["PYTHONPATH"]`. Create `runtime_root` only immediately before opening `runtime_root / "local-gateway.log"`.

- [x] **Step 7: Remove debug-trace package-root fallbacks without weakening redaction**

Evidence (2026-07-14): `configure_debug_trace(..., log_path=, provenance_root=)` in `src/optimus/acp/debug_trace.py`; redaction tests remain green in focused suite; committed `f37d4ef`.

Delete `debug_trace._project_root()`. `configure_debug_trace` receives an explicit `provenance_root` and records it in a non-secret process setting used by `_git_sha`; `_log_path` uses the explicit configured log path. This intentionally changes `_git_sha` from an inferred agent-checkout SHA to the current workspace SHA. Label it `workspace_git_sha` in Plan 9.9 evidence and retain `package_version` as the installed agent-build identifier so provenance readers cannot confuse the two. The default CLI path remains `<workspace>/.optimus/debug-acp.ndjson`. `acp_debug_log` must continue passing `message` and `data` through `redact_for_telemetry` unconditionally; do not implement P9.85-FU-7.

- [x] **Step 8: Remove spawned-agent `PYTHONPATH` injection and make repo tooling explicit**

Evidence (2026-07-14): `build_acp_subprocess_env` omits `PYTHONPATH`; `tools/verify_live_agent.py` / `operator_verify.main(repository_root=...)` use explicit repo root; inventory clean for `parents[3]|PYTHONPATH` under `src`; committed `f37d4ef`.

Change:

```python
def build_acp_subprocess_env(
    *,
    operator_environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source = dict(operator_environ or os.environ)
    env: dict[str, str] = {}
    for key in _REQUIRED_AGENT_ENV_KEYS:
        value = source.get(key, "").strip()
        if not value:
            raise SubprocessEnvConfigurationError(_missing_env_message(key))
        env[key] = value
    env["OPTIMUS_PRODUCTION_MODE"] = source.get("OPTIMUS_PRODUCTION_MODE", "").strip() or "false"
    for key in (*_OPTIONAL_AGENT_ENV_KEYS, *_SYSTEM_ENV_KEYS):
        value = source.get(key, "").strip()
        if value:
            env[key] = value
    _assert_no_provider_or_gateway_secrets(env)
    return env
```

Delete `_ensure_src_on_pythonpath`. The calling Python environment must already contain the installed package, which is true for editable contributor environments and the non-editable wheel verifier. Change `operator_verify.main` to accept `repository_root: Path`; its tool wrapper passes `ROOT`. This explicit repo-only root may own verification reports but must never be used by `optimus-agent` credential or log discovery.

- [x] **Step 9: Run the focused startup/runtime suite and the mechanical inventory**

Evidence (2026-07-14): focused Task 3 suite → 104 passed, 1 skipped; `rg -n 'parents\[3\]|PYTHONPATH' src` clean; `ruff check` on named surfaces clean; `git diff --check` clean (Task 3 implementer report / operator approval).

```bash
python -m pytest \
  tests/unit/acp/test_main_wiring.py \
  tests/unit/acp/test_main_check_config.py \
  tests/unit/acp/test_main_debug_trace.py \
  tests/unit/acp/test_local_infra.py \
  tests/unit/acp/test_local_gateway_secrets.py \
  tests/unit/acp/test_operator_paths.py \
  tests/unit/acp/test_debug_trace.py \
  tests/unit/acp/test_acp_subprocess_env.py \
  tests/integration/release/test_verify_live_agent_cli.py -v
if rg -n 'parents\[3\]|PYTHONPATH' src; then
  echo "unexpected editable-install root dependency remains" >&2
  exit 1
fi
python -m ruff check src/optimus/acp tools/verify_live_agent.py tests/unit/acp tests/integration/release/test_verify_live_agent_cli.py
git diff --check
```

Expected: tests PASS; `rg` returns no matches in `src`; Ruff and diff check pass. Test-only/repo-wrapper `sys.path` handling is not a product `PYTHONPATH` dependency.

- [x] **Step 10: Review and commit Task 3 after explicit approval**

Evidence: operator approval 2026-07-14; commit `f37d4efd9ed65fa085c1955fcbdb813ac7bf2bb0` — `Remove editable runtime root assumptions`.

```bash
git add \
  src/optimus/acp/__main__.py \
  src/optimus/acp/local_infra.py \
  src/optimus/acp/debug_trace.py \
  src/optimus/acp/subprocess_env.py \
  src/optimus/acp/operator_verify.py \
  tools/verify_live_agent.py \
  tests/unit/acp/test_main_wiring.py \
  tests/unit/acp/test_main_check_config.py \
  tests/unit/acp/test_main_debug_trace.py \
  tests/unit/acp/test_local_infra.py \
  tests/unit/acp/test_debug_trace.py \
  tests/unit/acp/test_acp_subprocess_env.py \
  tests/integration/release/test_verify_live_agent_cli.py
git diff --cached --name-status
git diff --cached --check
git commit -m "Remove editable runtime root assumptions"
```

Expected: only the listed runtime/wiring files are committed.

---

### Task 4: Add the Checked-In Non-Editable Wheel Verification Gate

**Deliverable:** One script reproducibly proves the wheel, both packages, both entry points, safe root destinations, and source-checkout independence; offline mode runs in CI and live mode is explicitly gated.

**Files:**
- Create: `tools/verify_plan99_noneditable_install.py`
- Create: `tests/unit/tools/test_verify_plan99_noneditable_install.py`
- Modify: `.github/workflows/guardrails.yml`

**Interfaces:**
- Consumes: `--wheel-dir`, `--scratch-root`, optional `--live`, optional `--model`, optional `--report`, system `uv`, and (live only) real `acpx`, keyring, Redis, Gateway credentials/model.
- Produces: `select_wheel`, `installed_script_path`, `build_offline_commands`, `validate_live_prerequisites`, `assert_no_secret_values`, exit 0 plus sanitized JSON/Markdown evidence, and non-zero with one actionable failure; never an ACP client implementation.

- [x] **Step 1: Write failing verifier-unit tests**

Evidence (2026-07-14): `tests/unit/tools/test_verify_plan99_noneditable_install.py` authored first; later expanded for hostile-var names, live gateway-log path, and Windows regression pins; initial gate commit `55a6689`, Windows fix+tests `f120a5a`.

Test deterministic helpers rather than creating a real environment in unit tests:

```python
def test_select_wheel_requires_exactly_one_wheel(tmp_path):
    with pytest.raises(VerificationError, match="exactly one wheel"):
        select_wheel(tmp_path)
    first = tmp_path / "optimus_cost_agent-0.1.0-py3-none-any.whl"
    first.write_bytes(b"wheel-one")
    assert select_wheel(tmp_path) == first.resolve()
    (tmp_path / "second-0.1.0-py3-none-any.whl").write_bytes(b"wheel-two")
    with pytest.raises(VerificationError, match="exactly one wheel"):
        select_wheel(tmp_path)


def test_installed_script_path_uses_scripts_on_windows_and_bin_on_posix(tmp_path):
    assert installed_script_path(tmp_path / "venv", "optimus-agent", windows=True) == (
        tmp_path / "venv" / "Scripts" / "optimus-agent.exe"
    )
    assert installed_script_path(tmp_path / "venv", "optimus-agent", windows=False) == (
        tmp_path / "venv" / "bin" / "optimus-agent"
    )


def test_offline_commands_build_isolated_environment_without_editable_install(tmp_path):
    wheel = tmp_path / "optimus_cost_agent-0.1.0-py3-none-any.whl"
    venv = tmp_path / "venv"
    commands = build_offline_commands(
        uv_executable="uv",
        venv_root=venv,
        wheel_path=wheel,
        windows=True,
    )
    rendered = "\n".join(" ".join(command) for command in commands)
    assert "--editable" not in rendered
    assert " -e " not in f" {rendered} "
    assert commands[0] == ["uv", "venv", str(venv), "--python", "3.14", "--clear"]
    assert commands[1] == [
        "uv",
        "pip",
        "install",
        "--python",
        str(venv / "Scripts" / "python.exe"),
        str(wheel),
    ]


def test_live_mode_requires_real_acpx_and_explicit_report(tmp_path):
    with pytest.raises(VerificationError, match="--report"):
        validate_live_prerequisites(acpx_executable="acpx", report_path=None)
    with pytest.raises(VerificationError, match="acpx"):
        validate_live_prerequisites(
            acpx_executable=None,
            report_path=tmp_path / "plan99-evidence.md",
        )


def test_sanitized_evidence_rejects_secret_values():
    with pytest.raises(VerificationError, match="secret value"):
        assert_no_secret_values(
            "gateway startup accidentally included sk-private-value",
            secret_values=("sk-private-value", "shared-private-value"),
        )


def test_script_delegates_acp_protocol_to_acpx():
    source = Path("tools/verify_plan99_noneditable_install.py").read_text(encoding="utf-8")
    for required in ('"--format"', '"--approve-all"', '"--cwd"', '"--agent"', '"exec"'):
        assert required in source
    for forbidden in ('"initialize"', '"session/new"', '"session/prompt"', "Content-Length"):
        assert forbidden not in source
```

The source inspection test is the mechanical guard that the script delegates ACP protocol behavior to `acpx` rather than implementing `initialize`, `session/new`, `session/prompt`, JSON-RPC framing, or stdio parsing itself.

- [x] **Step 2: Run the unit tests and verify the script is absent**

Evidence (2026-07-14): RED collection failed because `tools.verify_plan99_noneditable_install` did not exist (Task 4 implementer report).

```bash
python -m pytest tests/unit/tools/test_verify_plan99_noneditable_install.py -v
```

Expected: import/collection failure because the verifier does not exist.

- [x] **Step 3: Implement offline wheel verification with pinned commands**

Evidence (2026-07-14): `tools/verify_plan99_noneditable_install.py` offline path (install, `--help`, roots, hostile ignore); committed `55a6689` (+ Windows path/env fixes in `f120a5a`).

The script must run these operations through argument lists with `shell=False`:

```bash
uv venv C:/tmp/optimus-plan99-package/venv --python 3.14 --clear
uv pip install \
  --python C:/tmp/optimus-plan99-package/venv/Scripts/python.exe \
  C:/tmp/optimus-plan99-dist/optimus_cost_agent-0.1.0-py3-none-any.whl
C:/tmp/optimus-plan99-package/venv/Scripts/optimus-agent.exe --help
C:/tmp/optimus-plan99-package/venv/Scripts/optimus-local-gateway.exe --help
C:/tmp/optimus-plan99-package/venv/Scripts/python.exe -c "from optimus.acp.operator_paths import resolve_operator_paths; print(resolve_operator_paths)"
```

The probe runs with `cwd=<scratch>/outside-repo/workspace`, an empty workspace `.optimus/`, a hostile fixture at `<workspace>/.env.gateway`, and `OPTIMUS_CONFIG_ROOT=<scratch>/operator-config`. It asserts:

- `optimus.__file__` and `optimus_gateway.__file__` are under the isolated environment and outside the repository checkout;
- config root equals `<scratch>/operator-config`, outside the workspace;
- runtime/debug/gateway-log paths equal `<workspace>/.optimus/...`;
- the hostile workspace `.env.gateway` is not read;
- neither child environment nor evidence contains `PYTHONPATH`, provider-key values, or shared-secret values.

Offline mode does not start Redis, Gateway, or a model call. It writes a content-free result containing wheel filename/SHA-256, package locations, command exit codes, config root, runtime root, and log destinations.

- [x] **Step 4: Implement the explicitly operator-only live mode**

Evidence (2026-07-14): `--live` mode fails closed on missing Redis/credentials/ACP predicates; real live PASS recorded in Task 5 evidence report; code in `55a6689`/`f120a5a`.

`--live` additionally requires:

- `acpx --version` succeeds and reports 0.12.0 or the repository-approved successor;
- a real TimeSeries-capable Redis is reachable;
- keyring contains a provider/key pair and shared secret, or the operator-owned config root contains the intended `.env.gateway`;
- no provider key is present in the agent environment passed to `acpx`;
- `--report reports/plan-9-9-operator-packaging-evidence.md` is explicit;
- the exact isolated `optimus-agent` executable is used in the generated wrapper.

The real invocation is:

```bash
acpx --format json --approve-all \
  --cwd C:/tmp/optimus-plan99-live/outside-repo/workspace \
  --agent C:/tmp/optimus-plan99-live/outside-repo/workspace/run-isolated-optimus-agent.cmd \
  exec "Add a module docstring to example.py. Modify only example.py."
```

The script validates `end_turn`, a permission request/approval, a positive post-approval mutation to `example.py`, package paths outside the repo, the safe config root, and the starting workspace's `.optimus/local-gateway.log`. It records content-free transcript predicates, not raw source or credentials.

- [x] **Step 5: Add the offline CI step**

Evidence (2026-07-14): `.github/workflows/guardrails.yml` step `optimus-check: noneditable-package` (no `--live`); committed `55a6689`.

Append after dependency installation in `.github/workflows/guardrails.yml`:

```yaml
      - name: "optimus-check: noneditable-package"
        run: |
          uv build --wheel --out-dir dist/plan99
          uv run python tools/verify_plan99_noneditable_install.py \
            --wheel-dir dist/plan99 \
            --scratch-root "${RUNNER_TEMP}/optimus-plan99-package"
```

Do not add `--live` to CI. CI owns the offline package regression only; the operator evidence tier remains Task 5.

- [x] **Step 6: Run unit tests, build a wheel, and execute offline mode locally**

Evidence (2026-07-14, Task 4): unit tests GREEN (8 then later 13 after Windows pins); `uv build --wheel --out-dir C:/tmp/optimus-plan99-dist` + offline verifier exit 0; `provider_secrets=False` / `shared_secret=False`; Ruff/`git diff --check` clean. Reconfirmed at Task 6 Step 6 on a fresh scratch tree.

Use a scratch path outside the checkout:

```bash
python -m pytest tests/unit/tools/test_verify_plan99_noneditable_install.py -v
uv build --wheel --out-dir C:/tmp/optimus-plan99-dist
python tools/verify_plan99_noneditable_install.py \
  --wheel-dir C:/tmp/optimus-plan99-dist \
  --scratch-root C:/tmp/optimus-plan99-package
python -m ruff check tools/verify_plan99_noneditable_install.py tests/unit/tools/test_verify_plan99_noneditable_install.py
git diff --check
```

Expected: unit tests PASS; exactly one wheel selected; both console scripts return help; both package paths are inside the isolated environment and outside the repo; path assertions PASS; Ruff/diff clean.

- [x] **Step 7: Review and commit Task 4 after explicit approval**

Evidence: operator approval 2026-07-14; commit `55a66893665f622b220bf8c3c8a4f7c5ca4a5d53` — `Gate noneditable Optimus package installs` (verifier + tests + CI). Follow-on Windows packaging-verifier fix `f120a5afde39e3b3a8a405211ae71653b6e75665`.

```bash
git add \
  tools/verify_plan99_noneditable_install.py \
  tests/unit/tools/test_verify_plan99_noneditable_install.py \
  .github/workflows/guardrails.yml
git diff --cached --name-status
git diff --cached --check
git commit -m "Gate noneditable Optimus package installs"
```

Expected: exactly the verifier, its tests, and CI workflow are committed.

---

### Task 5: Capture Real Non-Editable Operator Evidence

**Deliverable:** A new redacted report proves the installed wheel works from outside the checkout with real Redis, Gateway/model, keyring/config, and real `acpx`.

**Files:**
- Create: `reports/plan-9-9-operator-packaging-evidence.md`

**Interfaces:**
- Consumes: Task 4 verifier; the exact implementation commit SHA; real operator keyring/config; real Redis/Gateway/model; real `acpx`.
- Produces: one claim-to-evidence artifact that separates offline package proof from paid live proof.

- [x] **Step 1: Verify live prerequisites without exposing secret values**

Evidence (2026-07-14): Redis container `optimus-redis` on `127.0.0.1:6379` with TimeSeries (`MODULE LIST`); credential source recorded as keyring field names only; `acpx 0.12.0` / `uv 0.11.26`. Disclosed substitution: literal `pytest -m requires_redis tests/integration/agent/test_redis_live_agent.py` was not run (fixture requires parent-shell gateway creds); Redis capability instead proven via TCP + MODULE LIST and the live Gateway path. See `reports/plan-9-9-operator-packaging-evidence.md`.

Using Git Bash, run:

```bash
git rev-parse HEAD
uv --version
acpx --version
docker ps --filter name=optimus-redis
python -m pytest -m requires_redis tests/integration/agent/test_redis_live_agent.py -v
```

Expected: record the full implementation SHA, tool versions, a running TimeSeries-capable Redis, and the live Redis test PASS. Record credential source field names only; do not print or record values.

- [x] **Step 2: Build the exact implementation wheel outside the repo's normal `dist/`**

Evidence (2026-07-14): `uv build --wheel --out-dir C:/tmp/optimus-plan99-live-dist` → `optimus_cost_agent-0.1.0-py3-none-any.whl`; SHA-256 `1F7F9AD65C3BAC3F769C8A1BE52FA584E4A2CD4DF838794FEA6E7A91441E1DEE` (operator-recomputed).

```bash
uv build --wheel --out-dir C:/tmp/optimus-plan99-live-dist
```

Expected: exactly one wheel for `optimus-cost-agent`; record filename and SHA-256 in the new report.

- [x] **Step 3: Run the checked-in live verifier once**

Evidence (2026-07-14): live verifier against scratch `C:/tmp/optimus-plan99-live5` with real `acpx`, keyring, Redis, Gateway/`claude-haiku`; predicates_passed (`end_turn`, permission before mutation); `example.py` gained module docstring; gateway log owned by starting live workspace. Report: `reports/plan-9-9-operator-packaging-evidence.md` (Identity SHA `f120a5a...`).

```bash
python tools/verify_plan99_noneditable_install.py \
  --wheel-dir C:/tmp/optimus-plan99-live-dist \
  --scratch-root C:/tmp/optimus-plan99-live \
  --live \
  --model claude-haiku \
  --report reports/plan-9-9-operator-packaging-evidence.md
```

Expected: PASS with real `acpx`; exact installed `optimus-agent` path lies under the isolated environment; workspace lies outside repo; config root lies outside workspace; hostile workspace `.env.gateway` is ignored; Redis/Gateway/model call succeeds; approval precedes mutation; `example.py` alone changes; stop reason is `end_turn`; gateway log is under the workspace that started the singleton. Record `_git_sha` as `workspace_git_sha` and record `package_version` separately as the installed agent-build identifier. If the gateway was already running, the report must say it was reused and must not claim a new workspace log.

- [x] **Step 4: Scan the evidence and gateway startup output for secrets**

Evidence (2026-07-14, operator-reverified): hostile-fixture / trailing-whitespace scans clean on the report; acpx transcript greps found `end_turn`/`permission`/`approve` and no `sk-`-style secrets; gateway log content-free (`provider=openrouter` only).

Run a local script/test using the known fixture values in memory (never echo them) to assert they do not occur in the report, transcript summary, stderr capture, or gateway-start messages. Then run:

```bash
python -m pytest tests/unit/tools/test_verify_plan99_noneditable_install.py -v
if rg -n '[[:blank:]]+$' reports/plan-9-9-operator-packaging-evidence.md; then
  echo "trailing whitespace in Plan 9.9 evidence" >&2
  exit 1
fi
```

Expected: redaction assertions PASS; report has no placeholders, raw prompts/source, authorization values, credentialed URLs, or key material.

- [x] **Step 5: Review and commit the evidence after explicit approval**

Evidence: sequenced commits — verifier Windows fix `f120a5afde39e3b3a8a405211ae71653b6e75665`, then report-only `cde9cb9d22c32d0d0fe05b019543d6b1b5ba78a5` — `Record Plan 9.9 packaged operator evidence` (Identity points at `f120a5a`).

```bash
git add reports/plan-9-9-operator-packaging-evidence.md
git diff --cached --name-status
git diff --cached --check
git commit -m "Record Plan 9.9 packaged operator evidence"
```

Expected: report-only commit with the full evidence commit SHA recorded in the report or follow-on closure commit.

---

### Task 6: Migrate Living Operator Docs, Track Residual Risk, and Close Plan 9.9

**Deliverable:** Living docs point at the safe config and non-editable install; historical plans/reports remain unchanged; the roadmap records completion and the workspace-influenced-environment residual risk.

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-10-plan-9-6-phase-c-operator-runbook.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Modify: `docs/superpowers/plans/2026-07-14-plan-9-9-operator-packaging-and-credential-diagnostics.md` (checkboxes/results only after commands pass)

**Interfaces:**
- Consumes: Task 5 evidence SHA and outcomes.
- Produces: current operator instructions, Plan 9.8 non-editable handoff, closed Plan 9.9 roadmap status, and Plan 9.95 custody for `P9.9-FU-1`.

- [x] **Step 1: Update README non-editable installation and safe config migration**

Change operator installation from:

```bash
uv tool install --editable . --reinstall
```

to the non-editable checkout build:

```bash
uv tool install . --reinstall
```

Document the published-package future form separately without claiming it exists:

```bash
uv tool install optimus-cost-agent
```

For Windows auto-start configuration, document `%APPDATA%/optimus-cost-agent/.env.gateway`; for an explicit override, document an absolute `OPTIMUS_CONFIG_ROOT` outside the workspace. State that repo-root `.env.gateway` is no longer implicitly read by `optimus-agent`; the two manual gateway launcher scripts still use it only when the operator invokes them explicitly.

Document singleton log semantics exactly: the workspace that starts the loopback gateway owns `.optimus/local-gateway.log`; later workspaces reusing the same port do not receive a new log. Debug trace remains `<current-workspace>/.optimus/debug-acp.ndjson`.

- [x] **Step 2: Update the living Phase C operator runbook**

In `2026-07-10-plan-9-6-phase-c-operator-runbook.md` only:

- replace editable install commands with `uv tool install . --reinstall`;
- replace checkout-root `.env.gateway` rename/restore steps with inspection/migration of the resolved operator config root;
- update gateway log tail from `reports/local-gateway.log` to `.optimus/local-gateway.log`, qualified by singleton ownership;
- point troubleshooting at `optimus-agent --setup`, the displayed config-root remediation, and the Task 4 package verifier.

Do not edit its linked historical evidence report or the architectural Plan 9.6 plan.

- [x] **Step 3: Record Plan 9.9 completion and the Plan 9.8 handoff in the roadmap**

After Task 5 passes, change Plan 9.9 from tracked/not scheduled to implemented/live-verified with the exact implementation/evidence SHAs. Replace the temporary Plan 9.8 editable-install constraint with:

```text
Plan 9.9 established and live-verified the non-editable install contract. Future operator and Plan 9.8 regression runs use `uv tool install . --reinstall`; the historical Plan 9.8 evidence remains unchanged.
```

Preserve the existing Plan 9.87/9.88 closure and all explicit exclusions.

- [x] **Step 4: Update the residual environment-trust follow-up in this plan and its Plan 9.95 custody line**

Add exactly:

```markdown
### P9.9-FU-1: Workspace-influenced agent launch environment

**Status:** Open; owned by Plan 9.95 (security-design lane; may split into its own entry when scheduled).

**Risk:** The config-root containment guard prevents implicit or explicitly redirected config files
from resolving inside the workspace. It cannot prove that top-precedence environment values are
operator-authored when an IDE merges project-local settings into the external agent launch
environment. A malicious workspace could therefore influence provider, base-URL, or credential
environment fields even though `.env.gateway` discovery is safe.

**Acceptance criteria:** Define and implement a trust boundary that distinguishes operator-approved
agent environment overrides from workspace-provided launch settings; fail closed or require an
explicit approval ceremony before workspace-originated settings can affect local-Gateway provider,
base URL, or credentials. Preserve legitimate shell/admin deployment flows and do not log values.
```

Do not implement this follow-up inside Plan 9.9. The roadmap already contains exactly one Plan 9.95 custody line for `P9.9-FU-1`; update that line with Plan 9.9's final status/evidence pointer if needed, but do not add a duplicate entry.

- [x] **Step 5: Verify frozen history and cross-document consistency**

Evidence (run 2026-07-14 on `agent/cursor/plan-9-9-operator-paths`): `git diff --exit-code
origin/main -- <six frozen plan files>` exit 0; `git diff --exit-code origin/main -- reports
':(exclude)reports/plan-9-9-operator-packaging-evidence.md'` exit 0; the `rg` cross-document scan
found only current, consistent install/config/log guidance in `README.md` and the Phase C
runbook, plus one explicitly historical `uv tool install --editable .` reference in the roadmap's
Plan 9.6 closure note ("Already landed from the original closure list"); `git diff --check` exit
0.

Run:

```bash
git diff --exit-code origin/main -- \
  docs/superpowers/plans/2026-07-07-plan-9-6-live-verification-and-lld-alignment.md \
  docs/superpowers/plans/2026-07-08-plan-9-7-local-dev-infra-autostart-and-setup.md \
  docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md \
  docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md \
  docs/superpowers/plans/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md \
  docs/superpowers/plans/2026-07-13-plan-9-88-fu4b-evidence-remediation-and-plan-9-87-closure.md
git diff --exit-code origin/main -- \
  reports \
  ':(exclude)reports/plan-9-9-operator-packaging-evidence.md'
rg -n "Plan 9\.9|Plan 9\.95|P9\.9-FU-1|uv tool install --editable|\.env\.gateway|local-gateway\.log" \
  README.md \
  docs/superpowers/plans/2026-07-10-plan-9-6-phase-c-operator-runbook.md \
  docs/superpowers/plans/2026-07-01-phase-1-roadmap.md
git diff --check
```

Expected: every frozen-plan diff exits 0; the report command emits nothing except the one new Plan 9.9 report; living docs agree on install/config/log semantics; any remaining `--editable` occurrence is explicitly historical rather than current guidance.

- [x] **Step 6: Run final release-quality gates**

Evidence (run 2026-07-14 on `agent/cursor/plan-9-9-operator-paths`):
- `python -m pytest -q` → `922 passed, 2 skipped, 22 deselected` (PASS).
- `python -m pytest --cov=optimus --cov=optimus_gateway --cov-branch --cov-report=term-missing -q`
  → `TOTAL` coverage `85.02%` (>= 80% required); `922 passed, 2 skipped, 22 deselected`.
- `python -m ruff check .` → `All checks passed!`.
- `uv build --wheel --out-dir C:/tmp/optimus-plan99-final-dist` → built
  `optimus_cost_agent-0.1.0-py3-none-any.whl` successfully.
- `python tools/verify_plan99_noneditable_install.py --wheel-dir C:/tmp/optimus-plan99-final-dist
  --scratch-root C:/tmp/optimus-plan99-final-package` → exit 0; JSON result confirms both
  entry points exit 0, `optimus`/`optimus_gateway` resolve under the isolated `venv` outside the
  checkout, `provider_secrets=False` and `shared_secret=False` (hostile workspace config ignored).
- `rg -n 'parents\[3\]|PYTHONPATH' src` → no matches.
- `git diff --check` → exit 0. `git status --short` → only `README.md`, the roadmap, and the
  Phase C runbook modified among plan-owned files (plus pre-existing unrelated `uv.lock`/untracked
  scratch files from before this task).

```bash
python -m pytest -q
python -m pytest --cov=optimus --cov=optimus_gateway --cov-branch --cov-report=term-missing -q
python -m ruff check .
uv build --wheel --out-dir C:/tmp/optimus-plan99-final-dist
python tools/verify_plan99_noneditable_install.py \
  --wheel-dir C:/tmp/optimus-plan99-final-dist \
  --scratch-root C:/tmp/optimus-plan99-final-package
if rg -n 'parents\[3\]|PYTHONPATH' src; then
  echo "unexpected editable-install root dependency remains" >&2
  exit 1
fi
git diff --check
git status --short
```

Expected: default suite PASS; aggregate production coverage >=80%; Ruff clean; offline wheel verifier PASS; root-inventory `rg` has no matches; diff clean. Report live Task 5 separately and never substitute unit/offline success for the real `acpx` evidence.

- [x] **Step 7: Review and commit living-doc closure after explicit approval**

Evidence: operator approval 2026-07-14; commit message `Close Plan 9.9 operator packaging` (this commit; SHA recorded via `git rev-parse HEAD` after landing).

```bash
git add \
  README.md \
  docs/superpowers/plans/2026-07-10-plan-9-6-phase-c-operator-runbook.md \
  docs/superpowers/plans/2026-07-01-phase-1-roadmap.md \
  docs/superpowers/plans/2026-07-14-plan-9-9-operator-packaging-and-credential-diagnostics.md
git diff --cached --name-status
git diff --cached --check
git commit -m "Close Plan 9.9 operator packaging"
git rev-parse HEAD
```

Expected: only the three living docs and this Plan 9.9 tracker are committed; record the full closure SHA.

---

## Deferred Follow-Ups

### P9.9-FU-1: Workspace-influenced agent launch environment

**Status:** Open; owned by Plan 9.95 (security-design lane; may split into its own entry when scheduled).

**Risk:** The config-root containment guard prevents implicit or explicitly redirected config files
from resolving inside the workspace. It cannot prove that top-precedence environment values are
operator-authored when an IDE merges project-local settings into the external agent launch
environment. A malicious workspace could therefore influence provider, base-URL, or credential
environment fields even though `.env.gateway` discovery is safe.

**Acceptance criteria:** Define and implement a trust boundary that distinguishes operator-approved
agent environment overrides from workspace-provided launch settings; fail closed or require an
explicit approval ceremony before workspace-originated settings can affect local-Gateway provider,
base URL, or credentials. Preserve legitimate shell/admin deployment flows and do not log values.

## Definition of Done

- [x] Reviewer agent and operator approved this implementation plan before code implementation began. Evidence: plan approval before Task 1 (2026-07-14); branch `agent/cursor/plan-9-9-operator-paths` from `origin/main`.
- [x] `OperatorPaths` separates workspace, operator config, runtime logs, and installed-package concerns. Evidence: Task 1 — `src/optimus/acp/operator_paths.py` in `0265f8e`; unit suite 13 passed / 1 skipped.
- [x] Resolved, case-insensitive Windows containment rejects config roots equal to or below the workspace and does not reject prefix siblings. Evidence: Task 1 containment/sibling tests in `tests/unit/acp/test_operator_paths.py` (operator-reverified GREEN).
- [x] Migration failures name the safe config directory and both supported remediations without exposing values. Evidence: Task 1 remediation message template + safe-default precompute; committed `0265f8e`.
- [x] Compatible mixed-layer credentials resolve; provable keyring provider/key mismatch fails before log/spawn; partial keyring state warns. Evidence: Task 2 matrix (25 passed, `174cb31`) + Task 3 `test_credential_conflict_stops_before_log_or_spawn` (`f37d4ef`).
- [x] Anthropic/non-Anthropic wrong-variable cases produce distinct actionable diagnostics. Evidence: Task 2 wrong-variable tests naming `ANTHROPIC_API_KEY` vs `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY`; suite GREEN under `174cb31`.
- [x] Default provider provenance ignores an ambient wrong-provider variable and preserves the setup pointer; explicit unsupported environment/config/keyring providers fail with the supported set and required remediation. Evidence: Task 2 named tests (`test_default_provider_with_only_ambient_anthropic_key_returns_setup_pointer`, unsupported provider tests); `174cb31`.
- [x] `--setup` inspects only the operator config root for `.env.gateway` precedence. Evidence: Task 2 `config_root` API (`174cb31`) + Task 3 `test_setup_uses_operator_config_root_not_workspace` (`f37d4ef`).
- [x] Provider/shared secrets never appear in exceptions, warnings, repr, stderr, debug trace, startup output, packaging output, or committed evidence. Evidence: Task 2/3 non-disclosure assertions; Task 4/5 hostile-fixture scans; Task 5 report + operator transcript greps (no `sk-` leakage).
- [x] Product code under `src` contains no `parents[3]` or `PYTHONPATH` source-root injection. Evidence: Task 3/`rg` inventory at `f37d4ef`; Task 6 Step 5/6 re-runs clean (`rg 'parents\[3\]|PYTHONPATH' src`).
- [x] Gateway logs use the starting workspace's `.optimus/local-gateway.log`; singleton reuse semantics are documented and tested. Evidence: Task 3 unit tests (`f37d4ef`); live path in Task 5 evidence; Task 6 README/runbook documentation.
- [x] Debug logs use `<workspace>/.optimus/debug-acp.ndjson` without weakening unconditional redaction or absorbing P9.85-FU-7. Evidence: Task 3 `configure_debug_trace` wiring + redaction tests (`f37d4ef`); documented in Task 6 README.
- [x] Checked-in offline packaging verification builds/installs one wheel outside the repo and runs in CI. Evidence: Task 4 verifier + `optimus-check: noneditable-package` in `55a6689`; offline PASS reconfirmed Task 6 Step 6.
- [x] Operator-only live packaging evidence uses real Redis, real Gateway/model, and real independently authored `acpx`. Evidence: `reports/plan-9-9-operator-packaging-evidence.md` (`cde9cb9`); Identity implementation SHA `f120a5a`; operator independently corroborated scratch artifacts.
- [x] Future operator/Plan 9.8 regression guidance uses a non-editable install; historical plans/evidence remain unchanged. Evidence: Task 6 Step 5 frozen-history/`rg` scan (2026-07-14), all clean.
- [x] `P9.9-FU-1` records the workspace-influenced environment residual risk without implementing it. Evidence: Task 6 Step 4 — block already present in this plan's Deferred Follow-Ups (not duplicated) and the Plan 9.95 custody line updated with implementation SHA `f120a5afde39e3b3a8a405211ae71653b6e75665` and evidence pointer `reports/plan-9-9-operator-packaging-evidence.md`.
- [x] P9.87-FU-1, P9.85-FU-6/FU-7, P9.88-FU-2/FU-3, accepted-open FU-4B, Plan 10, and Plan 11 remain outside this lane. Evidence: no commits in this branch implement those plans; roadmap still tracks them under Plan 9.95 / later entries; Plan 9.9 scope limited to packaging/credential/paths/docs.
- [x] Default tests pass; aggregate production coverage is >=80%; Ruff and diff checks are clean. Evidence: Task 6 Step 6 (2026-07-14) — `922 passed, 2 skipped, 22 deselected`; coverage `85.02%`; `python -m ruff check .` clean; `git diff --check` clean.
- [x] Every checked task/DoD item cites the command and evidence that actually passed. Evidence: this Task 6 documentation pass fills Tasks 1–5 and remaining DoD rows with commit SHA and command/result citations from the landed work and operator-reverified gates.

## Plan Self-Review Record

- **R1-R7 coverage:** Every round-2 requirement maps to a named task, test, and DoD line in the traceability table.
- **Security boundary:** Workspace files cannot implicitly supply provider, base URL, key, or shared-secret configuration; environment-origin trust is honestly deferred as P9.9-FU-1.
- **Predicate precision:** Only provable keyring-pair mismatch and explicit-provider wrong-variable cases fail; default provider provenance preserves the setup path, unsupported-provider diagnostics remain typed and actionable, and compatible or unprovable mixed states retain the approved pass/warn behavior.
- **Packaging fidelity:** The offline claim uses a built wheel in an isolated environment; the live claim uses real `acpx`, not a project-authored ACP client.
- **Historical fidelity:** Only README, the Phase C living runbook, roadmap, this tracker, and a new Plan 9.9 report change; frozen plans and existing evidence do not.
- **Type consistency:** `config_root`, `runtime_root`, provenance types, and verifier arguments are named consistently across tasks.
- **Placeholder scan:** No `TBD`, `TODO`, unnamed error handling, generic test instruction, or unspecified follow-up owner/status remains.

## Implementation Handoff After Approval

After the reviewer agent and operator approve this document, create a fresh implementation worktree/branch from latest `main`; this planning branch is documentation-only. Execute with one of:

1. **Subagent-driven development (recommended):** fresh implementation agent per task with requirements and code-quality review between tasks.
2. **Inline executing-plans workflow:** task-by-task execution with explicit review checkpoints.

No implementation starts from `agent/codex/plan-9-9-operator-packaging`.
