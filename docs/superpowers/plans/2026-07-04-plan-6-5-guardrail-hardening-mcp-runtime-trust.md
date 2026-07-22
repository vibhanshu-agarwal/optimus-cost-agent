# Plan 6.5 Guardrail Hardening and MCP Runtime Trust Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Implemented (Phase 1). See README.md's "Phase 1 Plan 6.5 Guardrail Hardening" feature section and this plan's entry under Plan 6.5 in `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` for current build status. This plan predates this project's per-step checkbox-tracking convention, so its steps below were never intended to be individually ticked.

**Goal:** Close the actionable Plan 6 CI/review follow-ups before Plan 7 depends on stable guardrail, prompt-injection, command-safety, and MCP trust telemetry.

**Architecture:** Keep Plan 6.5 inside the guardrail/runtime trust boundary. Patch the existing Plan 6 scanner and MCP ingestion seams, add environment-aware shell/git bypass detection to the Plan 5/6 pre-tool boundary, replace the tiny hand-curated Unicode confusable set with a maintained TR39-style detector, and add a minimal runtime MCP trust context so loader, descriptor exposure, and tool execution paths use the same `MCPTrustRegistry` and `PreToolGuard` by default. MCP runtime execution must preserve the separation between one-time server/tool registration and per-call human approval. Plan 7 may persist the audit events these components emit, but Plan 7 must not implement these trust controls.

**Tech Stack:** Python >=3.14, pydantic >=2.8, pytest, pytest-asyncio, coverage.py, pytest-cov, stdlib `dataclasses`, stdlib `pathlib`, stdlib `typing`, existing `optimus.guardrails`, `optimus.runtime`, and `optimus.acp` modules. Runtime dependency addition: `confusable-homoglyphs` for maintained Unicode confusable detection.

---

## Source Anchors

- `docs/superpowers/plans/2026-07-04-prompt-injection-mcp-trust-ci-guardrail-parity.md`: Plan 6 added `ConfigTrustScanner`, `MCPTrustRegistry`, `MCPConfigIngestionGuard`, `MCPDescriptorExposureGuard`, command-safety bypass tests, and CI parity checks.
- `docs/superpowers/reviews/2026-07-04-plan-6-security-review.md` and `docs/superpowers/reviews/2026-07-04-plan-6-security-review-round-2.md`: Plan 6 follow-up review context that surfaced missing-path handling, git bypass gaps, Unicode confusable coverage limits, and runtime MCP wiring gaps.
- `docs/superpowers/reviews/2026-07-04-plan-6-5-architect-review.md`: Plan 6.5 architect review blocking the first draft because maintained confusable detection was overbroad, MCP runtime execution inferred approval from Agent mode, and autoload denial was present but not wired into registration.
- `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.0.pdf`, sections 5-6: repo config and MCP descriptors are untrusted input; MCP servers must never auto-load from cloned repositories; trusted registration, descriptor inspection, and local/CI parity are required.
- `docs/Optimus-Cost-Agent-LLD-v2.38.pdf`, section 12A: `PreToolGuard` runs after a tool call is assembled and before execution; deterministic checks run before classifiers for shell, file, MCP, and web surfaces.
- `docs/Optimus-Cost-Agent-LLD-v2.38.pdf`, section 12B: `MCPTrustRegistry` captures `server_id`, `manifest_hash`, `allowed_tools`, `permission_scope`, and `approved`; manifest changes force re-approval; descriptors are inspected before planner exposure.
- `docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf`, sections 14.1-14.7: shell bypasses, poisoned config, MCP autoload, descriptor injection, and local/CI guardrail parity must fail closed.
- `AGENTS.md`: tool output and web extract text are untrusted; mutation paths pass through `MutationGuard`/approval; no local provider or observability keys; safety-critical modules must not regress.

## Scope

### In Scope

- `MCPConfigIngestionGuard.scan_manifest_path()` fail-closed handling for missing, directory, or unreadable manifest paths, using the same `injection.unscannable_path` rule id as the config scanner for equivalent failures.
- Command safety support for git bypasses injected through inline `env GIT_CONFIG_* ... git ...` command prefixes.
- Pre-tool environment support so the shell execution boundary can pass an explicit environment mapping into `CommandSafetyValidator`.
- Blocking `GIT_CONFIG_*` git config injection, `alias.*` injection, and `core.hooksPath` / `--no-verify` values supplied through env dicts or inline env prefixes.
- Maintained Unicode confusable detection shared by `ConfigTrustScanner` and `CommandSafetyValidator`, replacing the tiny local `_CONFUSABLES` sets.
- Minimal MCP runtime trust context:
  - default registry bootstrap,
  - explicit manifest scan before registration,
  - autoload denial for workspace-bundled manifests,
  - descriptor exposure through `MCPDescriptorExposureGuard`,
  - MCP tool execution through `PreToolGuard` with registry-backed metadata,
  - explicit per-call approval passed into runtime execution instead of inferred from `ExecutionMode.AGENT`.
- Integration tests proving blocked MCP calls do not reach an injected runner and trusted calls use the default runtime registry.
- README or plan note clarifying that Plan 7 only records guardrail events and does not implement these trust controls.

### Out of Scope

- Redis, JSONL, ProviderUsage, EvidenceLedger cost reconciliation, and observability trace export. Those belong to Plan 7.
- Retry/backoff, golden tasks, composite fitness gates, and release-gate orchestration. Those belong to Plan 8.
- Full subprocess wrapper implementation or global process spawning. This plan adds the trust/runtime seam and tests it with injected runners.
- Reading or mutating user/global `.gitconfig` files. This plan blocks git config injection visible at the command/pre-tool boundary; full local gitconfig alias introspection can be a later hardening slice if needed.
- Real MCP server process startup in tests. Tests use injected manifest objects and fake runners.
- Local LLM classifiers for scanner decisions. Detection remains deterministic.

## File Structure

- Modify: `pyproject.toml` - add `confusable-homoglyphs` runtime dependency.
- Modify: `uv.lock` - refresh dependency lock.
- Create: `src/optimus/guardrails/unicode_confusables.py` - shared maintained confusable detection wrapper.
- Modify: `src/optimus/guardrails/prompt_injection.py` - replace local `_CONFUSABLES` with shared detection.
- Modify: `src/optimus/guardrails/command_safety.py` - replace local `_CONFUSABLES`, parse inline env prefixes, and validate explicit env mappings.
- Modify: `src/optimus/guardrails/pre_tool.py` - add `environment` to `PreToolRequest` and pass it to command validation.
- Modify: `src/optimus/guardrails/mcp_trust.py` - fail closed for unreadable manifest paths.
- Create: `src/optimus/mcp/__init__.py` - public MCP runtime trust exports.
- Create: `src/optimus/mcp/runtime.py` - runtime trust context, descriptor catalog, explicit approval plumbing, autoload enforcement, and injected runner execution seam.
- Modify: `src/optimus/guardrails/__init__.py` - export shared confusable helper if this package already exports guardrail surfaces.
- Modify: `README.md` - short Plan 6.5 guardrail hardening note.
- Modify: `tests/unit/guardrails/test_mcp_trust.py` - missing-path scan test.
- Modify: `tests/unit/guardrails/test_command_safety.py` - inline env and explicit env git bypass tests.
- Modify: `tests/unit/guardrails/test_pre_tool_guard.py` - pre-tool env mapping test and default registry behavior check.
- Modify: `tests/unit/guardrails/test_prompt_injection.py` - maintained Unicode confusable coverage tests.
- Create: `tests/unit/guardrails/test_unicode_confusables.py` - shared helper tests.
- Create: `tests/unit/mcp/test_runtime.py` - MCP runtime trust context and descriptor exposure tests.
- Modify: `tests/integration/guardrails/test_mcp_trust_blocks_side_effects.py` - prove runtime execution blocks before runner side effects.

## Human Agile Sizing

This plan is sized for roughly 1-2 weeks of human development effort:

- Day 1: missing-path fail-closed patch and narrow tests.
- Days 2-3: env-aware shell/git bypass hardening.
- Days 4-5: Unicode confusable dependency and scanner/command migration.
- Days 6-8: MCP runtime trust context, loader/exposure/execution seams, and integration tests.
- Days 9-10: focused coverage, README, review fixes, and final verification.

## Commit Policy for Execution

Each task includes a commit step because the Superpowers workflow favors small reviewable checkpoints. In this repository, commit steps are approval-gated: do not run `git commit`, push, delete branches, or rewrite history unless the user explicitly approves that action. If commit approval has not been granted, treat each commit step as a local checkpoint: run the narrow tests, inspect `git diff --check`, leave changes unstaged or stage only with explicit approval, and continue.

## Task 1: Fail Closed For Missing MCP Manifest Paths

**Files:**
- Modify: `src/optimus/guardrails/mcp_trust.py`
- Test: `tests/unit/guardrails/test_mcp_trust.py`

- [ ] **Step 1: Write the failing missing-path test**

Append to `tests/unit/guardrails/test_mcp_trust.py`:

```python
def test_config_ingestion_scan_blocks_missing_manifest_path(tmp_path):
    guard = MCPConfigIngestionGuard(workspace_root=tmp_path, scanner=ConfigTrustScanner())
    missing_manifest = tmp_path / ".cursor" / "missing-mcp.json"

    decision = guard.scan_manifest_path(missing_manifest)

    assert decision.allowed is False
    assert decision.rule_id == "injection.unscannable_path"
    assert "not a readable file" in decision.reason
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/unit/guardrails/test_mcp_trust.py::test_config_ingestion_scan_blocks_missing_manifest_path -v
```

Expected: FAIL with `FileNotFoundError` from `Path.read_text()`.

- [ ] **Step 3: Implement fail-closed path handling**

Modify `MCPConfigIngestionGuard.scan_manifest_path()` in `src/optimus/guardrails/mcp_trust.py`:

```python
    def scan_manifest_path(self, manifest_path: str | Path) -> MCPTrustDecision:
        path = Path(manifest_path)
        if not path.is_file():
            return MCPTrustDecision(
                False,
                "injection.unscannable_path",
                f"MCP config path is not a readable file: {path.as_posix()}",
            )
        text = path.read_text(encoding="utf-8", errors="replace")
        scan = self._scanner.scan_text(text, subject=TrustScanSubject.CONFIG_FILE, source_path=str(path))
        if not scan.allowed:
            rules = ",".join(finding.rule_id for finding in scan.findings)
            return MCPTrustDecision(False, "mcp.config_injection", f"MCP config rejected: {rules}")
        return MCPTrustDecision(True, "mcp.config_scan_clean", "MCP config may proceed to explicit registration")
```

- [ ] **Step 4: Run MCP trust tests**

Run:

```bash
pytest tests/unit/guardrails/test_mcp_trust.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/optimus/guardrails/mcp_trust.py tests/unit/guardrails/test_mcp_trust.py
git commit -m "Fail closed on unreadable MCP manifests."
```

## Task 2: Block Git Bypasses From Inline And Explicit Environments

**Files:**
- Modify: `src/optimus/guardrails/command_safety.py`
- Modify: `src/optimus/guardrails/pre_tool.py`
- Test: `tests/unit/guardrails/test_command_safety.py`
- Test: `tests/unit/guardrails/test_pre_tool_guard.py`

- [ ] **Step 1: Write failing command-safety env tests**

Append to `tests/unit/guardrails/test_command_safety.py`:

```python
def test_inline_env_git_config_alias_bypass_is_blocked(tmp_path):
    validator = CommandSafetyValidator(workspace_root=tmp_path, allowed_network_hosts=())

    result = validator.validate(
        (
            "env",
            "GIT_CONFIG_COUNT=1",
            "GIT_CONFIG_KEY_0=alias.ci",
            "GIT_CONFIG_VALUE_0=commit --no-verify",
            "git",
            "ci",
        )
    )

    assert result.verdict is ValidationVerdict.BLOCK
    assert result.rule_id == "shell.git_config_env_bypass"


def test_explicit_env_git_config_hooks_path_bypass_is_blocked(tmp_path):
    validator = CommandSafetyValidator(workspace_root=tmp_path, allowed_network_hosts=())

    result = validator.validate(
        ("git", "commit", "-m", "message"),
        env={
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": "NUL",
        },
    )

    assert result.verdict is ValidationVerdict.BLOCK
    assert result.rule_id == "shell.git_config_env_bypass"


def test_unrelated_env_does_not_change_allowed_git_status(tmp_path):
    validator = CommandSafetyValidator(workspace_root=tmp_path, allowed_network_hosts=())

    result = validator.validate(("git", "status"), env={"CI": "true"})

    assert result.verdict is ValidationVerdict.ALLOW
    assert result.rule_id == "shell.allowed"
```

- [ ] **Step 2: Write failing pre-tool env propagation test**

Append to `tests/unit/guardrails/test_pre_tool_guard.py`:

```python
def test_pre_tool_guard_passes_shell_environment_to_command_validator(tmp_path):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())

    result = guard.check(
        PreToolRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.SHELL,
            action="git commit",
            command=("git", "commit", "-m", "message"),
            approval_granted=True,
            environment={
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "alias.safe",
                "GIT_CONFIG_VALUE_0": "commit --no-verify",
            },
        )
    )

    assert result.verdict is PreToolVerdict.BLOCK
    assert result.rule_id == "shell.git_config_env_bypass"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/guardrails/test_command_safety.py::test_inline_env_git_config_alias_bypass_is_blocked tests/unit/guardrails/test_command_safety.py::test_explicit_env_git_config_hooks_path_bypass_is_blocked tests/unit/guardrails/test_pre_tool_guard.py::test_pre_tool_guard_passes_shell_environment_to_command_validator -v
```

Expected: FAIL because `CommandSafetyValidator.validate()` does not accept `env`, inline `env` prefixes are not parsed, and `PreToolRequest` has no `environment` field.

- [ ] **Step 4: Add env parsing and git config bypass detection**

Modify imports in `src/optimus/guardrails/command_safety.py`:

```python
from collections.abc import Mapping
```

Change the public validate method and the start of `_validate_command()`:

```python
    def validate(self, command: tuple[str, ...], *, env: Mapping[str, str] | None = None) -> ValidationResult:
        inline_env, effective_command = _extract_inline_env(command)
        merged_env = {**inline_env, **dict(env or {})}
        return self._validate_command(effective_command, env=merged_env, depth=0)

    def _validate_command(self, command: tuple[str, ...], *, env: Mapping[str, str], depth: int) -> ValidationResult:
        if not command:
            return ValidationResult(ValidationVerdict.HOLD, "shell.empty_command", "empty command requires review")
        git_config_result = _git_config_env_bypass(command, env)
        if git_config_result is not None:
            return git_config_result
```

Update the recursive interpreter validation call in `_validate_command()`:

```python
                payload_result = self._validate_command(tuple(parsed), env=env, depth=depth + 1)
```

Append helpers near the existing git helpers:

```python
def _extract_inline_env(command: tuple[str, ...]) -> tuple[dict[str, str], tuple[str, ...]]:
    if not command:
        return {}, command
    executable = Path(command[0]).name.lower()
    if executable != "env":
        return {}, command
    env: dict[str, str] = {}
    index = 1
    while index < len(command) and "=" in command[index] and not command[index].startswith("-"):
        key, value = command[index].split("=", 1)
        if key:
            env[key] = value
        index += 1
    return env, command[index:]


def _git_config_env_bypass(command: tuple[str, ...], env: Mapping[str, str]) -> ValidationResult | None:
    lowered_command = tuple(token.lower() for token in command)
    if not _is_git_command(lowered_command):
        return None
    lowered_env = {key.lower(): value for key, value in env.items()}
    git_config_keys = {key for key in lowered_env if key.startswith("git_config_")}
    if not git_config_keys:
        return None
    joined_values = "\n".join(str(value).lower() for value in lowered_env.values())
    joined_keys = "\n".join(git_config_keys)
    if "alias." in joined_values or "alias." in joined_keys:
        return ValidationResult(ValidationVerdict.BLOCK, "shell.git_config_env_bypass", "git alias injection through environment is denied")
    if "core.hookspath" in joined_values or "core.hookspath" in joined_keys:
        return ValidationResult(ValidationVerdict.BLOCK, "shell.git_config_env_bypass", "git hooksPath injection through environment is denied")
    if "--no-verify" in joined_values or "\n-n\n" in f"\n{joined_values}\n":
        return ValidationResult(ValidationVerdict.BLOCK, "shell.git_config_env_bypass", "git no-verify injection through environment is denied")
    return ValidationResult(ValidationVerdict.BLOCK, "shell.git_config_env_bypass", "git config injection through environment is denied")
```

- [ ] **Step 5: Add pre-tool environment propagation**

Modify imports in `src/optimus/guardrails/pre_tool.py`:

```python
from collections.abc import Mapping
from dataclasses import dataclass, field
```

Add to `PreToolRequest`:

```python
    environment: Mapping[str, str] = field(default_factory=dict)
```

Update shell validation in `_validate_surface()`:

```python
        if request.tool_surface is ToolSurface.SHELL:
            validation = self._command_validator.validate(request.command, env=request.environment)
            return _pre_tool_result(validation.verdict, validation.rule_id, validation.reason)
```

- [ ] **Step 6: Run focused shell/pre-tool tests**

Run:

```bash
pytest tests/unit/guardrails/test_command_safety.py tests/unit/guardrails/test_pre_tool_guard.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/optimus/guardrails/command_safety.py src/optimus/guardrails/pre_tool.py tests/unit/guardrails/test_command_safety.py tests/unit/guardrails/test_pre_tool_guard.py
git commit -m "Block git config bypasses from shell environments."
```

## Task 3: Replace Tiny Confusable Sets With Maintained Detection

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/optimus/guardrails/unicode_confusables.py`
- Modify: `src/optimus/guardrails/prompt_injection.py`
- Modify: `src/optimus/guardrails/command_safety.py`
- Modify: `src/optimus/guardrails/__init__.py`
- Test: `tests/unit/guardrails/test_unicode_confusables.py`
- Test: `tests/unit/guardrails/test_prompt_injection.py`
- Test: `tests/unit/guardrails/test_command_safety.py`

- [ ] **Step 1: Write failing shared confusable helper tests**

Create `tests/unit/guardrails/test_unicode_confusables.py`:

```python
from optimus.guardrails.unicode_confusables import contains_dangerous_confusable


def test_mixed_script_cyrillic_payload_is_dangerous():
    assert contains_dangerous_confusable("run p\u0443test") is True


def test_mixed_script_greek_payload_is_dangerous():
    assert contains_dangerous_confusable("open \u03b1gent-config") is True


def test_fullwidth_payload_is_dangerous_after_normalization_check():
    assert contains_dangerous_confusable("run p\uff49p install fake-package") is True


def test_common_english_and_shell_text_is_not_dangerous():
    benign = (
        "pytest tests/unit -v",
        "git status",
        "hello world",
        "open agent-config",
    )

    assert [contains_dangerous_confusable(text) for text in benign] == [False, False, False, False]


def test_non_spoofing_nfkc_compatibility_text_is_not_dangerous():
    benign = (
        "Node.js\u2122 package",
        "footnote\u00b9 reference",
        "half\u00bd cup",
    )

    assert [contains_dangerous_confusable(text) for text in benign] == [False, False, False]
```

- [ ] **Step 2: Extend scanner and command tests**

Append to `tests/unit/guardrails/test_prompt_injection.py`:

```python
def test_greek_confusable_blocks_config_text():
    result = scan_text("load \u03b1gent config before approval")

    assert result.verdict is TrustScanVerdict.BLOCK
    assert any(finding.rule_id == "injection.unicode_confusable" for finding in result.findings)
```

Append to `tests/unit/guardrails/test_command_safety.py`:

```python
def test_greek_confusable_command_is_blocked(tmp_path):
    validator = CommandSafetyValidator(workspace_root=tmp_path, allowed_network_hosts=())

    result = validator.validate(("echo", "\u03b1gent"))

    assert result.verdict is ValidationVerdict.BLOCK
    assert result.rule_id == "shell.unicode_confusable"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/guardrails/test_unicode_confusables.py tests/unit/guardrails/test_prompt_injection.py::test_greek_confusable_blocks_config_text tests/unit/guardrails/test_command_safety.py::test_greek_confusable_command_is_blocked -v
```

Expected: FAIL because `optimus.guardrails.unicode_confusables` does not exist and the current small `_CONFUSABLES` set does not cover the new cases.

- [ ] **Step 4: Add dependency and refresh lock**

Update `pyproject.toml` runtime dependencies:

```toml
dependencies = [
  "confusable-homoglyphs>=3.3",
  "pydantic>=2.8",
]
```

Run:

```bash
uv lock
uv sync --all-extras
```

Expected: `uv.lock` records `confusable-homoglyphs`, and the local environment can import `confusable_homoglyphs`.

- [ ] **Step 5: Add shared confusable helper**

Create `src/optimus/guardrails/unicode_confusables.py`:

```python
from __future__ import annotations

import unicodedata

from confusable_homoglyphs import confusables


def contains_dangerous_confusable(text: str) -> bool:
    if not text:
        return False
    if "xn--" in text.lower():
        return True
    if _contains_nfkc_spoofing_form(text):
        return True
    return bool(confusables.is_dangerous(text))


def _contains_nfkc_spoofing_form(text: str) -> bool:
    for char in text:
        name = unicodedata.name(char, "")
        if "FULLWIDTH" in name or "HALFWIDTH" in name:
            return True
    return False
```

Note: `confusable-homoglyphs` may not publish Python 3.14 classifiers even though it is pure Python and imports cleanly in review. Keep this dependency behind the small wrapper above so it can be replaced if Python-version support becomes a packaging issue.

- [ ] **Step 6: Use shared helper in prompt scanner**

Modify imports and remove `_CONFUSABLES` from `src/optimus/guardrails/prompt_injection.py`:

```python
from optimus.guardrails.unicode_confusables import contains_dangerous_confusable
```

Replace the confusable check:

```python
        if contains_dangerous_confusable(raw_text):
            findings.append(TrustScanFinding("injection.unicode_confusable", "Unicode confusable or punycode detected", "<confusable>"))
```

- [ ] **Step 7: Use shared helper in command validator**

Modify imports and remove `_CONFUSABLES` from `src/optimus/guardrails/command_safety.py`:

```python
from optimus.guardrails.unicode_confusables import contains_dangerous_confusable
```

Replace the confusable check:

```python
        if contains_dangerous_confusable(raw_text):
            return ValidationResult(ValidationVerdict.BLOCK, "shell.unicode_confusable", "Unicode confusable detected")
```

Remove `_contains_confusable()` and `_contains_punycode_host()` if no longer referenced.

- [ ] **Step 8: Export helper**

Add to `src/optimus/guardrails/__init__.py`:

```python
from optimus.guardrails.unicode_confusables import contains_dangerous_confusable
```

Append to `__all__`:

```python
    "contains_dangerous_confusable",
```

- [ ] **Step 9: Run focused Unicode tests**

Run:

```bash
pytest tests/unit/guardrails/test_unicode_confusables.py tests/unit/guardrails/test_prompt_injection.py tests/unit/guardrails/test_command_safety.py -v
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml uv.lock src/optimus/guardrails/unicode_confusables.py src/optimus/guardrails/prompt_injection.py src/optimus/guardrails/command_safety.py src/optimus/guardrails/__init__.py tests/unit/guardrails/test_unicode_confusables.py tests/unit/guardrails/test_prompt_injection.py tests/unit/guardrails/test_command_safety.py
git commit -m "Use maintained Unicode confusable detection."
```

## Task 4: Add MCP Runtime Trust Context And Guarded Execution Seam

**Files:**
- Modify: `src/optimus/guardrails/mcp_trust.py`
- Create: `src/optimus/mcp/__init__.py`
- Create: `src/optimus/mcp/runtime.py`
- Test: `tests/unit/mcp/test_runtime.py`
- Modify: `tests/integration/guardrails/test_mcp_trust_blocks_side_effects.py`

- [ ] **Step 1: Write failing runtime trust context tests**

Create `tests/unit/mcp/test_runtime.py`:

```python
import pytest

from optimus.guardrails.mcp_trust import MCPServerManifest, MCPToolDescriptor
from optimus.mcp.runtime import MCPRuntimeBlocked, MCPRuntimeTrustContext


def manifest() -> MCPServerManifest:
    return MCPServerManifest(
        server_id="packages",
        command=("uvx", "packages-mcp"),
        launch_args=("--stdio",),
        tools=(
            MCPToolDescriptor(
                name="search",
                description="Search approved package metadata.",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                side_effect_class="read",
            ),
            MCPToolDescriptor(
                name="details",
                description="Read package details.",
                input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
                side_effect_class="read",
            ),
        ),
    )


def test_runtime_context_bootstraps_registry_and_exposes_approved_descriptors(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=workspace, allowed_network_hosts=())
    current = manifest()

    context.register_explicit_manifest(
        current,
        manifest_path=tmp_path / "approved" / "packages.mcp.json",
        allowed_tools=("search",),
        permission_scope="read_only_metadata",
        approved_by="maintainer",
        manifest_text='{"mcpServers": {"packages": {"command": "uvx"}}}',
    )

    descriptors = context.expose_descriptors(server_id="packages", manifest=current)

    assert [descriptor.name for descriptor in descriptors] == ["search"]


def test_runtime_rejects_workspace_bundled_manifest_registration(tmp_path):
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())
    bundled_manifest_path = tmp_path / ".cursor" / "mcp.json"
    bundled_manifest_path.parent.mkdir()
    bundled_manifest_path.write_text('{"mcpServers": {"packages": {"command": "uvx"}}}', encoding="utf-8")

    with pytest.raises(MCPRuntimeBlocked, match="mcp.autoload.cloned_repo_denied"):
        context.register_explicit_manifest(
            manifest(),
            manifest_path=bundled_manifest_path,
            allowed_tools=("search",),
            permission_scope="read_only_metadata",
            approved_by="maintainer",
        )


def test_runtime_rejects_missing_manifest_input(tmp_path):
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())

    with pytest.raises(MCPRuntimeBlocked, match="injection.unscannable_path"):
        context.register_explicit_manifest(
            manifest(),
            manifest_path=tmp_path.parent / "missing" / "packages.mcp.json",
            allowed_tools=("search",),
            permission_scope="read_only_metadata",
            approved_by="maintainer",
        )


def test_runtime_registered_mcp_call_requires_per_call_approval(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=workspace, allowed_network_hosts=())
    current = manifest()
    context.register_explicit_manifest(
        current,
        manifest_path=tmp_path / "approved" / "packages.mcp.json",
        allowed_tools=("search",),
        permission_scope="read_only_metadata",
        approved_by="maintainer",
        manifest_text='{"mcpServers": {"packages": {"command": "uvx"}}}',
    )
    runner_called = False

    def runner(server_id: str, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        nonlocal runner_called
        runner_called = True
        return {"ok": True}

    with pytest.raises(MCPRuntimeBlocked, match="classifier.not_configured"):
        context.execute_tool(
            run_id="run-1",
            session_id="session-1",
            manifest=current,
            tool_name="search",
            arguments={"query": "pytest"},
            approval_granted=False,
            runner=runner,
        )

    assert runner_called is False


def test_runtime_registered_mcp_call_runs_after_explicit_per_call_approval(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=workspace, allowed_network_hosts=())
    current = manifest()
    context.register_explicit_manifest(
        current,
        manifest_path=tmp_path / "approved" / "packages.mcp.json",
        allowed_tools=("search",),
        permission_scope="read_only_metadata",
        approved_by="maintainer",
        manifest_text='{"mcpServers": {"packages": {"command": "uvx"}}}',
    )

    def runner(server_id: str, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        return {"server_id": server_id, "tool_name": tool_name, "arguments": arguments}

    result = context.execute_tool(
        run_id="run-1",
        session_id="session-1",
        manifest=current,
        tool_name="search",
        arguments={"query": "pytest"},
        approval_granted=True,
        runner=runner,
    )

    assert result["server_id"] == "packages"
    assert result["tool_name"] == "search"


def test_runtime_blocks_unregistered_mcp_call_before_runner(tmp_path):
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())
    runner_called = False

    def runner(server_id: str, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        nonlocal runner_called
        runner_called = True
        return {"ok": True}

    with pytest.raises(MCPRuntimeBlocked, match="mcp.server_not_registered"):
        context.execute_tool(
            run_id="run-1",
            session_id="session-1",
            manifest=manifest(),
            tool_name="search",
            arguments={"query": "pytest"},
            approval_granted=True,
            runner=runner,
        )

    assert runner_called is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/mcp/test_runtime.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'optimus.mcp'`.

- [ ] **Step 3: Add public in-memory config scan helper**

Add this method to `MCPConfigIngestionGuard` in `src/optimus/guardrails/mcp_trust.py`:

```python
    def scan_manifest_text(self, text: str, *, source_path: str) -> MCPTrustDecision:
        scan = self._scanner.scan_text(text, subject=TrustScanSubject.CONFIG_FILE, source_path=source_path)
        if not scan.allowed:
            rules = ",".join(finding.rule_id for finding in scan.findings)
            return MCPTrustDecision(False, "mcp.config_injection", f"MCP config rejected: {rules}")
        return MCPTrustDecision(True, "mcp.config_scan_clean", "MCP config may proceed to explicit registration")
```

Then update `scan_manifest_path()` to reuse it after the readable-file check:

```python
        text = path.read_text(encoding="utf-8", errors="replace")
        return self.scan_manifest_text(text, source_path=str(path))
```

- [ ] **Step 4: Add MCP runtime module**

Create `src/optimus/mcp/__init__.py`:

```python
from optimus.mcp.runtime import MCPRuntimeBlocked, MCPRuntimeTrustContext, MCPToolRunner

__all__ = [
    "MCPRuntimeBlocked",
    "MCPRuntimeTrustContext",
    "MCPToolRunner",
]
```

Create `src/optimus/mcp/runtime.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from optimus.guardrails.mcp_trust import (
    MCPConfigIngestionGuard,
    MCPDescriptorExposureGuard,
    MCPServerManifest,
    MCPTrustRegistry,
)
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolVerdict
from optimus.guardrails.prompt_injection import ConfigTrustScanner
from optimus.runtime.modes import ExecutionMode

MCPToolRunner = Callable[[str, str, dict[str, Any]], dict[str, Any]]


class MCPRuntimeBlocked(RuntimeError):
    pass


class MCPRuntimeTrustContext:
    def __init__(
        self,
        *,
        registry: MCPTrustRegistry,
        ingestion_guard: MCPConfigIngestionGuard,
        exposure_guard: MCPDescriptorExposureGuard,
        pre_tool_guard: PreToolGuard,
    ) -> None:
        self.registry = registry
        self.ingestion_guard = ingestion_guard
        self.exposure_guard = exposure_guard
        self.pre_tool_guard = pre_tool_guard

    @classmethod
    def for_workspace(cls, *, workspace_root: str | Path, allowed_network_hosts: tuple[str, ...]) -> "MCPRuntimeTrustContext":
        scanner = ConfigTrustScanner()
        registry = MCPTrustRegistry(scanner=scanner)
        return cls(
            registry=registry,
            ingestion_guard=MCPConfigIngestionGuard(workspace_root=workspace_root, scanner=scanner),
            exposure_guard=MCPDescriptorExposureGuard(registry=registry),
            pre_tool_guard=PreToolGuard.for_workspace(
                workspace_root=workspace_root,
                allowed_network_hosts=allowed_network_hosts,
                mcp_trust_registry=registry,
            ),
        )

    def deny_autoload_manifest(self, manifest_path: str | Path):
        return self.ingestion_guard.deny_autoload_path(manifest_path)

    def register_explicit_manifest(
        self,
        manifest: MCPServerManifest,
        *,
        manifest_path: str | Path,
        allowed_tools: tuple[str, ...],
        permission_scope: str,
        approved_by: str,
        manifest_text: str | None = None,
    ):
        path = Path(manifest_path)
        # Explicit registration is the approval path for external manifests.
        # Workspace-bundled cloned-repo manifests remain denied here.
        autoload_decision = self.ingestion_guard.deny_autoload_path(path)
        if autoload_decision.rule_id == "mcp.autoload.cloned_repo_denied":
            raise MCPRuntimeBlocked(f"{autoload_decision.rule_id}: {autoload_decision.reason}")
        if manifest_text is not None:
            decision = self.ingestion_guard.scan_manifest_text(manifest_text, source_path=path.as_posix())
            if not decision.allowed:
                raise MCPRuntimeBlocked(f"{decision.rule_id}: {decision.reason}")
        else:
            decision = self.ingestion_guard.scan_manifest_path(path)
            if not decision.allowed:
                raise MCPRuntimeBlocked(f"{decision.rule_id}: {decision.reason}")
        return self.registry.register(
            manifest,
            allowed_tools=allowed_tools,
            permission_scope=permission_scope,
            approved_by=approved_by,
        )

    def expose_descriptors(self, *, server_id: str, manifest: MCPServerManifest):
        return self.exposure_guard.expose_trusted_descriptors(server_id=server_id, manifest=manifest)

    def execute_tool(
        self,
        *,
        run_id: str,
        session_id: str | None,
        manifest: MCPServerManifest,
        tool_name: str,
        arguments: dict[str, Any],
        approval_granted: bool,
        runner: MCPToolRunner,
        execution_mode: ExecutionMode = ExecutionMode.AGENT,
    ) -> dict[str, Any]:
        result = self.pre_tool_guard.check(
            PreToolRequest(
                run_id=run_id,
                session_id=session_id,
                execution_mode=execution_mode,
                tool_surface=ToolSurface.MCP,
                action=f"mcp:{manifest.server_id}/{tool_name}",
                approval_granted=approval_granted,
                mcp_server_id=manifest.server_id,
                mcp_tool_name=tool_name,
                mcp_manifest=manifest,
            )
        )
        if result.verdict is not PreToolVerdict.ALLOW:
            raise MCPRuntimeBlocked(f"{result.rule_id}: {result.reason}")
        return runner(manifest.server_id, tool_name, arguments)
```

- [ ] **Step 5: Run runtime tests**

Run:

```bash
pytest tests/unit/mcp/test_runtime.py -v
```

Expected: PASS.

- [ ] **Step 6: Strengthen integration side-effect blocking test**

Modify `tests/integration/guardrails/test_mcp_trust_blocks_side_effects.py` so one test uses `MCPRuntimeTrustContext.execute_tool()` with an unregistered manifest and asserts the fake runner is not called:

```python
def test_runtime_mcp_call_is_blocked_before_runner_side_effect(tmp_path):
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())
    called = False

    def runner(server_id: str, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        nonlocal called
        called = True
        return {"ok": True}

    with pytest.raises(MCPRuntimeBlocked, match="mcp.server_not_registered"):
        context.execute_tool(
            run_id="run-1",
            session_id=None,
            manifest=manifest(),
            tool_name="search",
            arguments={"query": "pytest"},
            approval_granted=True,
            runner=runner,
        )

    assert called is False
```

Add imports:

```python
from optimus.mcp.runtime import MCPRuntimeBlocked, MCPRuntimeTrustContext
```

- [ ] **Step 7: Run MCP runtime and integration tests**

Run:

```bash
pytest tests/unit/mcp/test_runtime.py tests/integration/guardrails/test_mcp_trust_blocks_side_effects.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/optimus/guardrails/mcp_trust.py src/optimus/mcp/__init__.py src/optimus/mcp/runtime.py tests/unit/mcp/test_runtime.py tests/integration/guardrails/test_mcp_trust_blocks_side_effects.py
git commit -m "Wire MCP trust into runtime execution seams."
```

## Task 5: Documentation And Focused Verification

**Files:**
- Modify: `README.md`
- Verify: Plan 6.5 guardrail files

- [ ] **Step 1: Add README note**

Append after the existing Plan 6 guardrail note:

```markdown
### Phase 1 Plan 6.5 Guardrail Hardening

Plan 6.5 closes review and CI follow-ups from prompt-injection, MCP trust, and
CI parity work. MCP manifest ingestion now fails closed for unreadable paths,
shell validation inspects both argv and explicit environment mappings for git
config bypasses, Unicode spoofing uses maintained confusable detection, and MCP
runtime calls use a default trust context that wires manifest scanning,
workspace-bundled autoload denial, descriptor exposure, explicit per-call
approval, and pre-tool execution through the same registry. Usage accounting
and observability remain in Plan 7; Plan 6.5 only emits guardrail events for
that later telemetry layer to persist or export.
```

- [ ] **Step 2: Run focused Plan 6.5 tests**

Run:

```bash
pytest tests/unit/guardrails/test_mcp_trust.py tests/unit/guardrails/test_command_safety.py tests/unit/guardrails/test_pre_tool_guard.py tests/unit/guardrails/test_prompt_injection.py tests/unit/guardrails/test_unicode_confusables.py tests/unit/mcp/test_runtime.py tests/integration/guardrails/test_mcp_trust_blocks_side_effects.py -v
```

Expected: PASS.

- [ ] **Step 3: Run guardrail coverage**

Run:

```bash
pytest tests/unit/guardrails tests/integration/guardrails tests/unit/mcp --cov=optimus.guardrails --cov=optimus.mcp --cov-branch --cov-report=term-missing --cov-fail-under=80
```

Expected: PASS with safety-critical guardrail and MCP runtime modules above the aggregate threshold.

- [ ] **Step 4: Run full package coverage gate**

Run:

```bash
pytest --cov=optimus --cov-branch --cov-report=term-missing -v
```

Expected: PASS with aggregate Python production-code coverage at or above 80%.

- [ ] **Step 5: Verify local provider-key hygiene**

Run:

```bash
python -c "import os; from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES; found=[k for k in LOCAL_PROVIDER_KEY_NAMES if os.environ.get(k)]; print('FOUND=' + ','.join(found)); raise SystemExit(1 if found else 0)"
```

Expected: PASS with output `FOUND=`.

- [ ] **Step 6: Check diff hygiene**

Run:

```bash
git status --short
git diff --check
```

Expected: only intentional Plan 6.5 implementation, tests, lockfile, and README files are modified or added; no whitespace errors.

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "Document Plan 6.5 guardrail hardening."
```

## Self-Review

- Spec coverage: This plan maps all four actionable Plan 6 follow-ups to executable tasks: missing manifest path handling in Task 1, git env/alias bypass controls visible at the shell/pre-tool boundary in Task 2, maintained Unicode confusable detection in Task 3, and runtime MCP trust wiring in Task 4.
- Scope boundary: Redis, JSONL telemetry, ProviderUsage, EvidenceLedger cost reconciliation, and Gateway observability export are intentionally excluded and reserved for Plan 7.
- Plan 5/6 compatibility: `PreToolGuard` remains the authoritative before-execution gate; `MCPTrustRegistry` remains the trust source for MCP decisions; blocked MCP runtime calls do not reach injected runners.
- Architect-review fixes: `contains_dangerous_confusable()` uses `confusables.is_dangerous()` plus narrow fullwidth/halfwidth spoof detection, with benign shell/English regression tests; `MCPRuntimeTrustContext.execute_tool()` requires an explicit per-call `approval_granted`; `register_explicit_manifest()` fails closed for workspace-bundled autoload manifests and missing manifest input.
- Type consistency: `PreToolRequest.environment` is a mapping passed to `CommandSafetyValidator.validate(..., env=...)`; `MCPRuntimeTrustContext` owns one registry shared by descriptor exposure and execution; `contains_dangerous_confusable()` is shared by prompt and command scanners.
- Red-flag scan: The plan contains concrete test code, implementation code, commands, expected outcomes, and no unresolved placeholders.
- TDD compliance: Every production change starts with a failing unit or integration test, followed by the minimal implementation and focused verification.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-04-plan-6-5-guardrail-hardening-mcp-runtime-trust.md`. Two execution options:

**1. Subagent-Driven (recommended when available)** - dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - execute tasks in this session task-by-task with checkpoints. Use `superpowers:executing-plans` if available; otherwise follow this plan directly with the same red/green/refactor discipline.

Do not run `git commit`, push, or create/delete branches unless the user explicitly approves those actions. Plan 7 should start after this plan is accepted because Plan 7 records guardrail/MCP audit events but should not implement the trust controls above.
