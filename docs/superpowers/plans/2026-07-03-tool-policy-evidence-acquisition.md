# Tool Policy and Evidence Acquisition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic Phase 1 tool authorization and gateway-backed web evidence acquisition with auditable evidence ledger records.

**Architecture:** Add a focused tool-policy layer that decides whether an evidence tool call is allowed before any gateway action can occur, then records authorized calls atomically against per-run caps. Add an evidence package that models search/extract requests, builds and parses gateway web-evidence payloads, records gateway usage fields directly in immutable evidence entries, and wraps web search/extract through the existing Optimus Gateway transport seam instead of exposing Tavily or provider credentials locally. Keep the dependency direction one-way: `optimus.evidence` may depend on `optimus.gateway`, but `optimus.gateway` must not import or name evidence-domain types.

**Tech Stack:** Python >=3.14, pydantic >=2.8, pytest, pytest-asyncio, coverage.py, pytest-cov, stdlib `threading`, stdlib `decimal`, existing `optimus.gateway` client and `GatewayUsage` model.

---

## Source Anchors

- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, Plan 4: implement `ToolInvocationPolicy`, reason codes, local-first evidence policy, web search/extract request wrappers, URL provenance checks, per-run call caps, and `EvidenceLedgerEntry`.
- `docs/Optimus-Cost-Agent-Architecture-v2.15.pdf`, section 8: tool use is policy-driven first and model-requested second; local repo evidence is first-line; web evidence is gateway-wrapped and only policy-triggered.
- `docs/Optimus-Cost-Agent-Architecture-v2.15.pdf`, section 11: every model completion and tool call flows through the Optimus Gateway; gateway enforces domain allowlists, budgets, call caps, and tool policies server-side as defense in depth.
- `docs/Optimus-Cost-Agent-LLD-v2.38.pdf`, section 9E: `EvidenceLedgerEntry` records reason, policy signal, tool class, sources, and gateway usage fields populated from the gateway response envelope, never estimated post-hoc.
- `docs/Optimus-Cost-Agent-LLD-v2.38.pdf`, section 9E: `ToolRegistry.authorize_and_record_call()` enforces mode, policy trigger, and per-run call-count ceiling atomically.
- `docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf`, section 6: web search without a valid trigger rejects; `USER_REQUESTED` search with allowed domains allows; extract rejects URLs outside prior search results or outside trusted origins; max call caps are atomic.
- `docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf`, sections 10-11: malformed evidence schemas fail before gateway calls, and web extract output is untrusted text that must never be executed or promoted to policy.
- `docs/superpowers/plans/2026-07-02-gateway-only-configuration-gateway-client.md`: Plan 3 already introduced `OptimusGatewaySettings`, `GatewayClient`, `GatewayRequest`, and `GatewayUsage`; Plan 4 extends this gateway seam for web search and extract.
- `AGENTS.md`: local runtime credentials remain limited to `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; no local Tavily, OpenAI, OpenRouter, GLM, LangSmith, or provider keys.

## Scope

### In Scope

- `ToolClass`, `EvidenceReasonCode`, `ToolPolicySignal`, and typed allow/reject decisions.
- Deterministic `ToolInvocationPolicy` for web search, web extract, local repo read, and validation tool classes.
- Local-first policy behavior: code-change tasks default to local repo inspection, not web search.
- Web search authorization only when a valid trigger/reason exists and allowed domains are non-empty.
- Web search effective domains are the intersection of caller-requested domains and a local configured evidence-domain allowlist; caller input alone is never treated as trusted policy.
- Search response URLs are validated against the effective domain set before they can become provenance.
- Web extract authorization only when the URL came from an approved prior search result for the same run and the URL host matches the effective domain policy for the request.
- Evidence domain matching uses normalized host suffix semantics (`example.com` allows `docs.example.com`) and treats default HTTPS port 443 as equivalent to the portless host.
- Atomic per-run call counting with no record created on rejection.
- Plan 4 permits read-only web evidence in `PLAN`, `CHAT`, and `AGENT`; mode enforcement in this plan means rejecting unrecognized modes. Per-mode mutation gating remains with the mutation/agent-state plans.
- Evidence-owned gateway payload builders and response parsers for web search and web extract.
- Generic `GatewayClient.post_tool_json()` method using the existing Optimus bearer auth and trusted gateway validation, without importing `optimus.evidence`.
- `EvidenceLedgerEntry` and `EvidenceLedger` that carry gateway usage fields directly from `GatewayUsage`.
- Evidence acquisition service that authorizes, calls the gateway, records search provenance, and appends ledger entries with a locked ledger swap.
- Authorized gateway attempts consume the per-run cap before transport; gateway failures leave the cap record in place and do not append a ledger entry.
- ACP JSON-RPC methods for web search/extract evidence calls so the dispatcher can exercise the policy and evidence acquisition boundary.
- Unit and integration tests proving section 6 Tool Invocation Tests and section 10 schema-validation bullets for evidence requests.
- Focused coverage for safety-critical policy, registry, evidence, and gateway model seams.

### Out of Scope

- Direct Tavily, OpenAI, OpenRouter, GLM, LangSmith, OSV, PyPI, npm, Maven, or GitHub API clients in the local runtime.
- Durable `ProviderUsage` persistence, Redis HASH/TimeSeries writes, trace export, and full cost-ledger reconciliation. Those belong to Plan 7.
- Retry/backoff, transient/permanent failure classification, and release-gate runner behavior. Those belong to Plan 8.
- Full deny-before-allow permission engine, shell command safety validator, network egress validator, MCP trust, prompt-injection fixture handling, and CI guardrail parity. Those belong to Plans 5 and 6.
- Staging gateway integration tests that directly violate server-side policy. This plan creates local request seams and mocked gateway integration tests; staging revalidation remains a later release-gate item.
- Context-window selection, pruning, freshness scoring, and promotion gates. Plan 4 only provides evidence and tool-output trust signals for that later work.

## File Structure

- Create: `src/optimus/tools/policy.py` - tool classes, evidence reason codes, policy signals, request/decision types, and deterministic authorization matrix.
- Create: `src/optimus/tools/registry.py` - atomic per-run authorization and call recording, search-result provenance tracking, and cap enforcement.
- Modify: `src/optimus/tools/__init__.py` - export policy and registry surfaces.
- Create: `src/optimus/evidence/__init__.py` - public evidence exports.
- Create: `src/optimus/evidence/models.py` - `EvidenceRequest`, `EvidenceExtractRequest`, `EvidenceSearchResult`, `EvidenceSearchResponse`, and `EvidenceExtractResponse`.
- Create: `src/optimus/evidence/ledger.py` - `EvidenceLedgerEntry` and `EvidenceLedger` with run attribution and reconciliation totals.
- Create: `src/optimus/evidence/domain_policy.py` - configured evidence-domain allowlist, effective-domain intersection, and URL host validation.
- Create: `src/optimus/evidence/gateway_io.py` - evidence-owned web search/extract gateway payload builders and response parsers.
- Create: `src/optimus/evidence/acquisition.py` - policy-aware web search/extract orchestration through the gateway client.
- Modify: `src/optimus/gateway/client.py` - generic `post_tool_json()` method for gateway tool endpoints.
- Modify: `src/optimus/acp/dispatcher.py` - optional evidence acquisition dependency and JSON-RPC methods `optimus.evidence.search` and `optimus.evidence.extract`.
- Modify: `README.md` - short Phase 1 evidence acquisition note.
- Create: `tests/unit/tools/test_tool_policy.py` - deterministic policy matrix tests.
- Create: `tests/unit/tools/test_tool_registry.py` - atomic cap and provenance tests.
- Create: `tests/unit/evidence/test_models.py` - request validation and response model tests.
- Create: `tests/unit/evidence/test_ledger.py` - gateway usage propagation, totals, and append-only behavior tests.
- Create: `tests/unit/evidence/test_domain_policy.py` - configured-domain intersection, suffix matching, and default-port normalization tests.
- Create: `tests/unit/evidence/test_gateway_io.py` - gateway payload and response parser tests for web evidence.
- Modify: `tests/unit/gateway/test_client.py` - generic gateway tool-post method tests.
- Create: `tests/unit/evidence/test_acquisition.py` - service-level authorization, gateway call, provenance, and ledger tests.
- Modify: `tests/unit/acp/test_dispatcher.py` - ACP evidence method coverage.
- Create: `tests/integration/evidence/test_mocked_evidence_flow.py` - mocked search-then-extract flow with only Optimus credentials.

## Human Agile Sizing

This plan is sized for roughly 2-3 weeks of human development effort:

- Days 1-3: policy enums, deterministic authorization matrix, registry, atomic caps, and provenance.
- Days 4-6: evidence request/response models, ledger records, gateway payloads, and parsers.
- Days 7-9: gateway client web search/extract methods and service orchestration.
- Days 10-12: ACP dispatcher integration and mocked end-to-end evidence flow.
- Days 13-14: README, coverage, full test pass, and implementation review.

## Commit Policy for Execution

Each task includes a commit step because the Superpowers execution workflow favors small reviewable checkpoints. Those commit steps are approval-gated in this repository: do not run `git commit`, push, delete branches, or rewrite history unless the user explicitly approves that action. If commit approval has not been granted, treat each commit step as a local checkpoint: verify the narrow tests, inspect `git diff --check`, leave the working tree unstaged or stage only with explicit approval, and continue to the next task.

## Task 1: Tool Policy Reason Codes and Deterministic Decisions

**Files:**
- Create: `src/optimus/tools/policy.py`
- Modify: `src/optimus/tools/__init__.py`
- Test: `tests/unit/tools/test_tool_policy.py`

- [ ] **Step 1: Write failing policy matrix tests**

Create `tests/unit/tools/test_tool_policy.py`:

```python
from optimus.runtime.modes import ExecutionMode
from optimus.tools.policy import (
    EvidenceReasonCode,
    PolicyDecision,
    ToolClass,
    ToolInvocationPolicy,
    ToolInvocationRequest,
    ToolPolicySignal,
)


def test_web_search_without_trigger_rejects():
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.WEB_SEARCH,
            execution_mode=ExecutionMode.CHAT,
            policy_signal=ToolPolicySignal.LOCAL_CODE_CHANGE,
            reason=EvidenceReasonCode.NONE,
            allowed_domains=("docs.python.org",),
        )
    )

    assert decision.decision is PolicyDecision.REJECT
    assert decision.reason == "no policy trigger matched"


def test_user_requested_web_search_with_domains_allows():
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.WEB_SEARCH,
            execution_mode=ExecutionMode.PLAN,
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
            reason=EvidenceReasonCode.USER_REQUESTED,
            allowed_domains=("docs.python.org",),
        )
    )

    assert decision.decision is PolicyDecision.ALLOW
    assert decision.reason == "policy trigger matched"


def test_web_search_requires_allowed_domains():
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.WEB_SEARCH,
            execution_mode=ExecutionMode.PLAN,
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
            reason=EvidenceReasonCode.USER_REQUESTED,
            allowed_domains=(),
        )
    )

    assert decision.decision is PolicyDecision.REJECT
    assert decision.reason == "allowed_domains required for web search"


def test_unknown_execution_mode_rejects_before_tool_specific_policy():
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.WEB_SEARCH,
            execution_mode="SURPRISE",  # type: ignore[arg-type]
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
            reason=EvidenceReasonCode.USER_REQUESTED,
            allowed_domains=("docs.python.org",),
        )
    )

    assert decision.decision is PolicyDecision.REJECT
    assert decision.reason == "unknown execution mode"


def test_local_repo_read_is_allowed_in_plan_chat_mode():
    policy = ToolInvocationPolicy()

    decision = policy.authorize(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.LOCAL_REPO_READ,
            execution_mode=ExecutionMode.CHAT,
            policy_signal=ToolPolicySignal.LOCAL_CODE_CHANGE,
            reason=EvidenceReasonCode.NONE,
        )
    )

    assert decision.decision is PolicyDecision.ALLOW
```

- [ ] **Step 2: Run the policy tests to verify they fail**

Run:

```bash
pytest tests/unit/tools/test_tool_policy.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'optimus.tools.policy'`.

- [ ] **Step 3: Implement the deterministic policy matrix**

Create `src/optimus/tools/policy.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from optimus.runtime.modes import ExecutionMode


class ToolClass(StrEnum):
    LOCAL_REPO_READ = "local_repo_read"
    VALIDATION_GATE = "validation_gate"
    WEB_SEARCH = "web_search"
    WEB_EXTRACT = "web_extract"


class EvidenceReasonCode(StrEnum):
    NONE = "NONE"
    USER_REQUESTED = "USER_REQUESTED"
    CURRENT_FACT = "CURRENT_FACT"
    API_DOCS_OUTDATED = "API_DOCS_OUTDATED"
    PACKAGE_VERSION = "PACKAGE_VERSION"
    SECURITY_ADVISORY = "SECURITY_ADVISORY"


class ToolPolicySignal(StrEnum):
    LOCAL_CODE_CHANGE = "LOCAL_CODE_CHANGE"
    USER_REQUESTED_EXTERNAL_FACT = "USER_REQUESTED_EXTERNAL_FACT"
    CURRENT_OR_LATEST_FACT = "CURRENT_OR_LATEST_FACT"
    API_OR_FRAMEWORK_FACT_NOT_IN_REPO = "API_OR_FRAMEWORK_FACT_NOT_IN_REPO"
    DEPENDENCY_VERSION_CHECK = "DEPENDENCY_VERSION_CHECK"
    SECURITY_OR_CVE_CHECK = "SECURITY_OR_CVE_CHECK"
    APPROVED_SEARCH_RESULT_PROVENANCE = "APPROVED_SEARCH_RESULT_PROVENANCE"


class PolicyDecision(StrEnum):
    ALLOW = "ALLOW"
    REJECT = "REJECT"


@dataclass(frozen=True)
class ToolInvocationRequest:
    run_id: str
    tool_class: ToolClass
    execution_mode: ExecutionMode
    policy_signal: ToolPolicySignal
    reason: EvidenceReasonCode = EvidenceReasonCode.NONE
    allowed_domains: tuple[str, ...] = ()
    target_url: str | None = None
    prior_search_result_urls: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ToolInvocationDecision:
    decision: PolicyDecision
    reason: str
    tool_class: ToolClass
    policy_signal: ToolPolicySignal
    reason_code: EvidenceReasonCode

    @property
    def allowed(self) -> bool:
        return self.decision is PolicyDecision.ALLOW


class ToolInvocationPolicy:
    SUPPORTED_EXECUTION_MODES = frozenset(
        {ExecutionMode.PLAN, ExecutionMode.CHAT, ExecutionMode.AGENT}
    )

    WEB_SEARCH_TRIGGERS = frozenset(
        {
            (ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT, EvidenceReasonCode.USER_REQUESTED),
            (ToolPolicySignal.CURRENT_OR_LATEST_FACT, EvidenceReasonCode.CURRENT_FACT),
            (ToolPolicySignal.API_OR_FRAMEWORK_FACT_NOT_IN_REPO, EvidenceReasonCode.API_DOCS_OUTDATED),
            (ToolPolicySignal.DEPENDENCY_VERSION_CHECK, EvidenceReasonCode.PACKAGE_VERSION),
            (ToolPolicySignal.SECURITY_OR_CVE_CHECK, EvidenceReasonCode.SECURITY_ADVISORY),
        }
    )

    def authorize(self, request: ToolInvocationRequest) -> ToolInvocationDecision:
        if request.execution_mode not in self.SUPPORTED_EXECUTION_MODES:
            return _reject(request, "unknown execution mode")
        if request.tool_class in {ToolClass.LOCAL_REPO_READ, ToolClass.VALIDATION_GATE}:
            return _allow(request, "local deterministic tool allowed")
        if request.tool_class is ToolClass.WEB_SEARCH:
            return self._authorize_web_search(request)
        if request.tool_class is ToolClass.WEB_EXTRACT:
            return self._authorize_web_extract(request)
        return _reject(request, f"unsupported tool class: {request.tool_class}")

    def _authorize_web_search(self, request: ToolInvocationRequest) -> ToolInvocationDecision:
        if (request.policy_signal, request.reason) not in self.WEB_SEARCH_TRIGGERS:
            return _reject(request, "no policy trigger matched")
        if not request.allowed_domains:
            return _reject(request, "allowed_domains required for web search")
        return _allow(request, "policy trigger matched")

    def _authorize_web_extract(self, request: ToolInvocationRequest) -> ToolInvocationDecision:
        if (
            request.policy_signal != ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE
            or request.reason == EvidenceReasonCode.NONE
        ):
            return _reject(request, "web extract requires approved search-result provenance")
        if request.target_url is None:
            return _reject(request, "target_url required for web extract")
        if _origin(request.target_url) == "":
            return _reject(request, "https URL required for web extract")
        if request.target_url not in request.prior_search_result_urls:
            return _reject(request, "URL not in approved search-result set")
        return _allow(request, "approved search result provenance matched")

def _allow(request: ToolInvocationRequest, reason: str) -> ToolInvocationDecision:
    return ToolInvocationDecision(
        decision=PolicyDecision.ALLOW,
        reason=reason,
        tool_class=request.tool_class,
        policy_signal=request.policy_signal,
        reason_code=request.reason,
    )


def _reject(request: ToolInvocationRequest, reason: str) -> ToolInvocationDecision:
    return ToolInvocationDecision(
        decision=PolicyDecision.REJECT,
        reason=reason,
        tool_class=request.tool_class,
        policy_signal=request.policy_signal,
        reason_code=request.reason,
    )


def _origin(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc.lower()}"
```

Update `src/optimus/tools/__init__.py`:

```python
"""Tool wrappers that enforce runtime guardrails before side effects."""

from optimus.tools.policy import (
    EvidenceReasonCode,
    PolicyDecision,
    ToolClass,
    ToolInvocationDecision,
    ToolInvocationPolicy,
    ToolInvocationRequest,
    ToolPolicySignal,
)
from optimus.tools.mutation_tools import shell_exec, shadow_apply, write_file

__all__ = [
    "EvidenceReasonCode",
    "PolicyDecision",
    "shell_exec",
    "shadow_apply",
    "ToolClass",
    "ToolInvocationDecision",
    "ToolInvocationPolicy",
    "ToolInvocationRequest",
    "ToolPolicySignal",
    "write_file",
]
```

- [ ] **Step 4: Run policy tests**

Run:

```bash
pytest tests/unit/tools/test_tool_policy.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/optimus/tools/policy.py src/optimus/tools/__init__.py tests/unit/tools/test_tool_policy.py
git commit -m "Add deterministic tool invocation policy."
```

## Task 2: Atomic Tool Registry, Call Caps, and URL Provenance

**Files:**
- Create: `src/optimus/tools/registry.py`
- Modify: `src/optimus/tools/__init__.py`
- Test: `tests/unit/tools/test_tool_registry.py`

- [ ] **Step 1: Write failing registry tests**

Create `tests/unit/tools/test_tool_registry.py`:

```python
import pytest

from optimus.runtime.modes import ExecutionMode
from optimus.tools.policy import (
    EvidenceReasonCode,
    ToolClass,
    ToolInvocationPolicy,
    ToolInvocationRequest,
    ToolPolicySignal,
)
from optimus.tools.registry import ToolCallRejected, ToolRegistry


def search_request(run_id: str) -> ToolInvocationRequest:
    return ToolInvocationRequest(
        run_id=run_id,
        tool_class=ToolClass.WEB_SEARCH,
        execution_mode=ExecutionMode.PLAN,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        reason=EvidenceReasonCode.USER_REQUESTED,
        allowed_domains=("example.com",),
    )


def test_authorize_and_record_call_rejects_without_recording():
    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=10)

    with pytest.raises(ToolCallRejected, match="no policy trigger matched"):
        registry.authorize_and_record_call(
            ToolInvocationRequest(
                run_id="run-1",
                tool_class=ToolClass.WEB_SEARCH,
                execution_mode=ExecutionMode.CHAT,
                policy_signal=ToolPolicySignal.LOCAL_CODE_CHANGE,
                reason=EvidenceReasonCode.NONE,
                allowed_domains=("example.com",),
            )
        )

    assert registry.call_count("run-1") == 0


def test_max_calls_per_run_is_atomic_under_concurrent_calls():
    from concurrent.futures import ThreadPoolExecutor

    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=10)

    def attempt_call(index: int) -> bool:
        try:
            registry.authorize_and_record_call(search_request("run-1"))
            return True
        except ToolCallRejected:
            return False

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(attempt_call, range(50)))

    assert results.count(True) == 10
    assert results.count(False) == 40
    assert registry.call_count("run-1") == 10
    assert sorted(record.sequence_number for record in registry.records("run-1")) == list(range(1, 11))


def test_max_calls_per_run_is_atomic():
    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=2)

    registry.authorize_and_record_call(search_request("run-1"))
    registry.authorize_and_record_call(search_request("run-1"))

    with pytest.raises(ToolCallRejected, match="max_calls_per_run exceeded"):
        registry.authorize_and_record_call(search_request("run-1"))

    assert registry.call_count("run-1") == 2


def test_search_result_urls_are_tracked_per_run():
    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=10)

    registry.record_search_results(
        run_id="run-1",
        urls=("https://docs.example.com/a", "https://docs.example.com/b"),
    )

    assert registry.search_result_urls("run-1") == frozenset(
        {"https://docs.example.com/a", "https://docs.example.com/b"}
    )
    assert registry.search_result_urls("other-run") == frozenset()


def test_extract_uses_recorded_search_result_provenance():
    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=10)
    registry.record_search_results(run_id="run-1", urls=("https://docs.example.com/a",))

    registry.authorize_and_record_call(
        ToolInvocationRequest(
            run_id="run-1",
            tool_class=ToolClass.WEB_EXTRACT,
            execution_mode=ExecutionMode.PLAN,
            policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
            reason=EvidenceReasonCode.USER_REQUESTED,
            target_url="https://docs.example.com/a",
            prior_search_result_urls=registry.search_result_urls("run-1"),
        )
    )

    assert registry.call_count("run-1") == 1


def test_extract_rejects_url_not_from_prior_search():
    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=10)

    with pytest.raises(ToolCallRejected, match="URL not in approved search-result set"):
        registry.authorize_and_record_call(
            ToolInvocationRequest(
                run_id="run-1",
                tool_class=ToolClass.WEB_EXTRACT,
                execution_mode=ExecutionMode.PLAN,
                policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
                reason=EvidenceReasonCode.USER_REQUESTED,
                target_url="https://docs.example.com/a",
                prior_search_result_urls=registry.search_result_urls("run-1"),
            )
        )

    assert registry.call_count("run-1") == 0


def test_extract_requires_approved_provenance_signal():
    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=10)
    registry.record_search_results(run_id="run-1", urls=("https://docs.example.com/a",))

    with pytest.raises(ToolCallRejected, match="web extract requires approved search-result provenance"):
        registry.authorize_and_record_call(
            ToolInvocationRequest(
                run_id="run-1",
                tool_class=ToolClass.WEB_EXTRACT,
                execution_mode=ExecutionMode.PLAN,
                policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
                reason=EvidenceReasonCode.USER_REQUESTED,
                target_url="https://docs.example.com/a",
                prior_search_result_urls=registry.search_result_urls("run-1"),
            )
        )

    assert registry.call_count("run-1") == 0


def test_extract_rejects_non_https_url_before_provenance_match():
    registry = ToolRegistry(policy=ToolInvocationPolicy(), max_calls_per_run=10)
    registry.record_search_results(run_id="run-1", urls=("http://docs.example.com/a",))

    with pytest.raises(ToolCallRejected, match="https URL required for web extract"):
        registry.authorize_and_record_call(
            ToolInvocationRequest(
                run_id="run-1",
                tool_class=ToolClass.WEB_EXTRACT,
                execution_mode=ExecutionMode.PLAN,
                policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
                reason=EvidenceReasonCode.USER_REQUESTED,
                target_url="http://docs.example.com/a",
                prior_search_result_urls=registry.search_result_urls("run-1"),
            )
        )

    assert registry.call_count("run-1") == 0
```

- [ ] **Step 2: Run registry tests to verify they fail**

Run:

```bash
pytest tests/unit/tools/test_tool_registry.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'optimus.tools.registry'`.

- [ ] **Step 3: Implement atomic registry**

Create `src/optimus/tools/registry.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from optimus.tools.policy import (
    PolicyDecision,
    ToolClass,
    ToolInvocationDecision,
    ToolInvocationPolicy,
    ToolInvocationRequest,
)


@dataclass(frozen=True)
class ToolCallRecord:
    run_id: str
    sequence_number: int
    tool_class: ToolClass
    decision: ToolInvocationDecision


class ToolCallRejected(RuntimeError):
    def __init__(self, decision: ToolInvocationDecision) -> None:
        self.decision = decision
        super().__init__(decision.reason)


class ToolRegistry:
    def __init__(
        self,
        *,
        policy: ToolInvocationPolicy | None = None,
        max_calls_per_run: int = 10,
    ) -> None:
        if max_calls_per_run < 1:
            raise ValueError("max_calls_per_run must be >= 1")
        self._policy = policy or ToolInvocationPolicy()
        self._max_calls_per_run = max_calls_per_run
        self._lock = Lock()
        self._records_by_run: dict[str, list[ToolCallRecord]] = {}
        self._search_urls_by_run: dict[str, set[str]] = {}

    def authorize_and_record_call(self, request: ToolInvocationRequest) -> ToolCallRecord:
        decision = self._policy.authorize(request)
        with self._lock:
            if decision.decision is PolicyDecision.REJECT:
                raise ToolCallRejected(decision)

            records = self._records_by_run.setdefault(request.run_id, [])
            if len(records) >= self._max_calls_per_run:
                raise ToolCallRejected(
                    ToolInvocationDecision(
                        decision=PolicyDecision.REJECT,
                        reason="max_calls_per_run exceeded",
                        tool_class=request.tool_class,
                        policy_signal=request.policy_signal,
                        reason_code=request.reason,
                    )
                )

            record = ToolCallRecord(
                run_id=request.run_id,
                sequence_number=len(records) + 1,
                tool_class=request.tool_class,
                decision=decision,
            )
            records.append(record)
            return record

    def record_search_results(self, *, run_id: str, urls: tuple[str, ...]) -> None:
        with self._lock:
            self._search_urls_by_run.setdefault(run_id, set()).update(urls)

    def search_result_urls(self, run_id: str) -> frozenset[str]:
        with self._lock:
            return frozenset(self._search_urls_by_run.get(run_id, set()))

    def call_count(self, run_id: str) -> int:
        with self._lock:
            return len(self._records_by_run.get(run_id, []))

    def records(self, run_id: str) -> tuple[ToolCallRecord, ...]:
        with self._lock:
            return tuple(self._records_by_run.get(run_id, ()))
```

Update `src/optimus/tools/__init__.py`:

```python
"""Tool wrappers that enforce runtime guardrails before side effects."""

from optimus.tools.policy import (
    EvidenceReasonCode,
    PolicyDecision,
    ToolClass,
    ToolInvocationDecision,
    ToolInvocationPolicy,
    ToolInvocationRequest,
    ToolPolicySignal,
)
from optimus.tools.mutation_tools import shell_exec, shadow_apply, write_file
from optimus.tools.registry import ToolCallRecord, ToolCallRejected, ToolRegistry

__all__ = [
    "EvidenceReasonCode",
    "PolicyDecision",
    "shell_exec",
    "shadow_apply",
    "ToolCallRecord",
    "ToolCallRejected",
    "ToolClass",
    "ToolInvocationDecision",
    "ToolInvocationPolicy",
    "ToolInvocationRequest",
    "ToolPolicySignal",
    "ToolRegistry",
    "write_file",
]
```

- [ ] **Step 4: Run policy and registry tests**

Run:

```bash
pytest tests/unit/tools/test_tool_policy.py tests/unit/tools/test_tool_registry.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/optimus/tools tests/unit/tools/test_tool_registry.py
git commit -m "Record tool calls atomically."
```

## Task 3: Evidence Request Models and Ledger

**Files:**
- Create: `src/optimus/evidence/__init__.py`
- Create: `src/optimus/evidence/models.py`
- Create: `src/optimus/evidence/ledger.py`
- Test: `tests/unit/evidence/test_models.py`
- Test: `tests/unit/evidence/test_ledger.py`

- [ ] **Step 1: Write failing evidence model tests**

Create `tests/unit/evidence/test_models.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.evidence.models import (
    EvidenceExtractRequest,
    EvidenceExtractResponse,
    EvidenceRequest,
    EvidenceSearchResponse,
    EvidenceSearchResult,
)
from optimus.gateway.models import GatewayUsage
from optimus.tools.policy import EvidenceReasonCode, ToolPolicySignal


def test_evidence_request_preserves_query_verbatim():
    request = EvidenceRequest(
        run_id="run-1",
        session_id="session-1",
        query="latest pytest-asyncio release",
        reason=EvidenceReasonCode.PACKAGE_VERSION,
        policy_signal=ToolPolicySignal.DEPENDENCY_VERSION_CHECK,
        allowed_domains=("pypi.org",),
    )

    assert request.query == "latest pytest-asyncio release"
    assert request.session_id == "session-1"


def test_evidence_request_rejects_empty_query():
    with pytest.raises(ValidationError):
        EvidenceRequest(
            run_id="run-1",
            query="",
            reason=EvidenceReasonCode.USER_REQUESTED,
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
            allowed_domains=("example.com",),
        )


def test_extract_request_rejects_zero_max_chars():
    with pytest.raises(ValidationError):
        EvidenceExtractRequest(
            run_id="run-1",
            url="https://docs.example.com/a",
            reason=EvidenceReasonCode.USER_REQUESTED,
            policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
            allowed_domains=("docs.example.com",),
            max_chars_per_source=0,
        )


def test_search_and_extract_responses_carry_gateway_usage():
    usage = GatewayUsage(
        gateway_request_id="gw-search-1",
        provider="tavily",
        provider_request_id="provider-1",
        cache_hit=False,
        billing_units=2,
        cost_usd=Decimal("0.002"),
    )
    search_response = EvidenceSearchResponse(
        results=(
            EvidenceSearchResult(
                title="Docs",
                url="https://docs.example.com/a",
                snippet="Authoritative docs",
            ),
        ),
        gateway_usage=usage,
        credits_used=2,
    )
    extract_response = EvidenceExtractResponse(
        url="https://docs.example.com/a",
        title="Docs",
        content="Evidence text",
        gateway_usage=usage,
        credits_used=1,
    )

    assert search_response.results[0].url == "https://docs.example.com/a"
    assert extract_response.gateway_usage.cost_usd == Decimal("0.002")
    assert extract_response.trust == "untrusted"
    assert search_response.credits_used == 2
```

- [ ] **Step 2: Write failing ledger tests**

Create `tests/unit/evidence/test_ledger.py`:

```python
from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.evidence.ledger import EvidenceLedger, EvidenceLedgerEntry
from optimus.gateway.models import GatewayUsage
from optimus.tools.policy import EvidenceReasonCode, ToolClass, ToolPolicySignal


def usage() -> GatewayUsage:
    return GatewayUsage(
        gateway_request_id="gw-1",
        provider="tavily",
        provider_request_id="provider-1",
        cache_hit=False,
        billing_units=3,
        cost_usd=Decimal("0.003"),
    )


def test_entry_from_gateway_usage_copies_fields_verbatim():
    entry = EvidenceLedgerEntry.from_gateway_usage(
        run_id="run-1",
        session_id="session-1",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
        tool_class=ToolClass.WEB_SEARCH,
        sources=("https://docs.example.com/a",),
        gateway_usage=usage(),
        credits_used=3,
        queried_at=datetime(2026, 7, 3, tzinfo=UTC),
    )

    assert entry.run_id == "run-1"
    assert entry.session_id == "session-1"
    assert entry.gateway_request_id == "gw-1"
    assert entry.provider == "tavily"
    assert entry.provider_request_id == "provider-1"
    assert entry.cache_hit is False
    assert entry.billing_units == 3
    assert entry.cost_usd == Decimal("0.003")
    assert entry.credits_used == 3
    assert entry.sources == ("https://docs.example.com/a",)


def test_ledger_totals_reconcile_gateway_usage_fields():
    first = EvidenceLedgerEntry.from_gateway_usage(
        run_id="run-1",
        session_id=None,
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
        tool_class=ToolClass.WEB_SEARCH,
        sources=("https://docs.example.com/a",),
        gateway_usage=usage(),
        credits_used=3,
        queried_at=datetime(2026, 7, 3, tzinfo=UTC),
    )
    second = EvidenceLedgerEntry(
        run_id="run-1",
        session_id=None,
        reason=EvidenceReasonCode.CURRENT_FACT,
        policy_signal=ToolPolicySignal.CURRENT_OR_LATEST_FACT.value,
        tool_class=ToolClass.WEB_EXTRACT,
        queried_at=datetime(2026, 7, 3, 0, 0, 1, tzinfo=UTC),
        sources=("https://docs.example.com/a",),
        credits_used=4,
        gateway_request_id="gw-2",
        provider="tavily",
        provider_request_id=None,
        cache_hit=True,
        billing_units=5,
        cost_usd=Decimal("0.005"),
    )

    ledger = EvidenceLedger().record(first).record(second)

    assert ledger.total_credits() == 7
    assert ledger.total_billing_units() == 8
    assert ledger.total_cost_usd() == Decimal("0.008")
    assert ledger.total_credits(run_id="run-1") == 7
    assert ledger.total_cost_usd(run_id="run-1") == Decimal("0.008")
    assert ledger.total_cost_usd(run_id="other-run") == Decimal("0")


def test_ledger_record_returns_new_append_only_instance():
    ledger = EvidenceLedger()
    entry = EvidenceLedgerEntry.from_gateway_usage(
        run_id="run-1",
        session_id=None,
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
        tool_class=ToolClass.WEB_SEARCH,
        sources=("https://docs.example.com/a",),
        gateway_usage=usage(),
            queried_at=datetime(2026, 7, 3, tzinfo=UTC),
    )

    updated = ledger.record(entry)

    assert ledger.entries == ()
    assert updated.entries == (entry,)
    with pytest.raises(ValidationError):
        EvidenceLedgerEntry(
            run_id="run-1",
            session_id=None,
            reason=EvidenceReasonCode.USER_REQUESTED,
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
            tool_class=ToolClass.WEB_SEARCH,
            queried_at=datetime(2026, 7, 3, tzinfo=UTC),
            sources=(),
            billing_units=-1,
            cost_usd=Decimal("0"),
        )
```

- [ ] **Step 3: Run evidence tests to verify they fail**

Run:

```bash
pytest tests/unit/evidence/test_models.py tests/unit/evidence/test_ledger.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'optimus.evidence'`.

- [ ] **Step 4: Implement evidence models and ledger**

Create `src/optimus/evidence/models.py`:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from optimus.gateway.models import GatewayUsage
from optimus.tools.policy import EvidenceReasonCode, ToolPolicySignal


class EvidenceRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None = None
    query: str = Field(min_length=1)
    reason: EvidenceReasonCode
    policy_signal: ToolPolicySignal
    allowed_domains: tuple[str, ...] = Field(min_length=1)
    result_cap: int = Field(default=5, ge=1, le=10)
    search_depth: Literal["basic", "advanced"] = "basic"


class EvidenceExtractRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None = None
    url: HttpUrl
    reason: EvidenceReasonCode
    policy_signal: ToolPolicySignal
    allowed_domains: tuple[str, ...] = Field(min_length=1)
    max_chars_per_source: int = Field(default=6000, ge=1, le=20000)

    @property
    def url_text(self) -> str:
        return str(self.url)


class EvidenceSearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = ""
    url: HttpUrl
    snippet: str = ""

    @property
    def url_text(self) -> str:
        return str(self.url)


class EvidenceSearchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    results: tuple[EvidenceSearchResult, ...]
    gateway_usage: GatewayUsage
    credits_used: int = Field(default=0, ge=0)


class EvidenceExtractResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: HttpUrl
    title: str = ""
    content: str
    trust: Literal["untrusted"] = "untrusted"
    gateway_usage: GatewayUsage
    credits_used: int = Field(default=0, ge=0)

    @property
    def url_text(self) -> str:
        return str(self.url)
```

Create `src/optimus/evidence/ledger.py`:

```python
from __future__ import annotations

from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from optimus.gateway.models import GatewayUsage
from optimus.tools.policy import EvidenceReasonCode, ToolClass


class EvidenceLedgerEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None = None
    reason: EvidenceReasonCode
    policy_signal: str = Field(min_length=1)
    tool_class: ToolClass
    queried_at: datetime
    sources: tuple[str, ...] = ()
    credits_used: int = Field(default=0, ge=0)
    gateway_request_id: str = ""
    provider: str = ""
    provider_request_id: str | None = None
    cache_hit: bool = False
    billing_units: int = Field(default=0, ge=0)
    cost_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))

    @classmethod
    def from_gateway_usage(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        reason: EvidenceReasonCode,
        policy_signal: str,
        tool_class: ToolClass,
        sources: tuple[str, ...],
        gateway_usage: GatewayUsage,
        credits_used: int,
        queried_at: datetime,
    ) -> EvidenceLedgerEntry:
        return cls(
            run_id=run_id,
            session_id=session_id,
            reason=reason,
            policy_signal=policy_signal,
            tool_class=tool_class,
            queried_at=queried_at,
            sources=sources,
            credits_used=credits_used,
            gateway_request_id=gateway_usage.gateway_request_id,
            provider=gateway_usage.provider,
            provider_request_id=gateway_usage.provider_request_id,
            cache_hit=gateway_usage.cache_hit,
            billing_units=gateway_usage.billing_units,
            cost_usd=gateway_usage.cost_usd,
        )


class EvidenceLedger(BaseModel):
    model_config = ConfigDict(frozen=True)

    entries: tuple[EvidenceLedgerEntry, ...] = ()

    def record(self, entry: EvidenceLedgerEntry) -> EvidenceLedger:
        return EvidenceLedger(entries=(*self.entries, entry))

    def entries_for_run(self, run_id: str) -> tuple[EvidenceLedgerEntry, ...]:
        return tuple(entry for entry in self.entries if entry.run_id == run_id)

    def _matching_entries(self, run_id: str | None) -> tuple[EvidenceLedgerEntry, ...]:
        if run_id is None:
            return self.entries
        return self.entries_for_run(run_id)

    def total_credits(self, *, run_id: str | None = None) -> int:
        return sum(entry.credits_used for entry in self._matching_entries(run_id))

    def total_billing_units(self, *, run_id: str | None = None) -> int:
        return sum(entry.billing_units for entry in self._matching_entries(run_id))

    def total_cost_usd(self, *, run_id: str | None = None) -> Decimal:
        return sum((entry.cost_usd for entry in self._matching_entries(run_id)), Decimal("0"))
```

Create `src/optimus/evidence/__init__.py`:

```python
"""Evidence acquisition and ledger models."""

from optimus.evidence.ledger import EvidenceLedger, EvidenceLedgerEntry
from optimus.evidence.models import (
    EvidenceExtractRequest,
    EvidenceExtractResponse,
    EvidenceRequest,
    EvidenceSearchResponse,
    EvidenceSearchResult,
)

__all__ = [
    "EvidenceExtractRequest",
    "EvidenceExtractResponse",
    "EvidenceLedger",
    "EvidenceLedgerEntry",
    "EvidenceRequest",
    "EvidenceSearchResponse",
    "EvidenceSearchResult",
]
```

- [ ] **Step 5: Run evidence tests**

Run:

```bash
pytest tests/unit/evidence/test_models.py tests/unit/evidence/test_ledger.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/optimus/evidence tests/unit/evidence/test_models.py tests/unit/evidence/test_ledger.py
git commit -m "Add evidence request models and ledger."
```

## Task 4: Evidence-Owned Gateway Payloads and Parsers

**Files:**
- Create: `src/optimus/evidence/gateway_io.py`
- Modify: `src/optimus/evidence/__init__.py`
- Test: `tests/unit/evidence/test_gateway_io.py`

- [ ] **Step 1: Write failing evidence gateway IO tests**

Create `tests/unit/evidence/test_gateway_io.py`:

```python
from decimal import Decimal

import pytest

from optimus.evidence.gateway_io import (
    build_web_extract_payload,
    build_web_search_payload,
    parse_web_extract_response,
    parse_web_search_response,
)
from optimus.evidence.models import EvidenceExtractResponse
from optimus.gateway.errors import GatewayResponseError
from optimus.gateway.models import GatewayUsage
from optimus.tools.policy import EvidenceReasonCode


def test_web_search_payload_sends_query_verbatim():
    payload = build_web_search_payload(
        query="latest pytest-asyncio release",
        reason=EvidenceReasonCode.PACKAGE_VERSION,
        allowed_domains=("pypi.org",),
        result_cap=3,
        search_depth="basic",
        metadata={"run_id": "run-1", "session_id": "session-1"},
    )

    assert payload["query"] == "latest pytest-asyncio release"
    assert payload["reason"] == "PACKAGE_VERSION"
    assert payload["allowed_domains"] == ["pypi.org"]
    assert payload["result_cap"] == 3
    assert payload["metadata"] == {"run_id": "run-1", "session_id": "session-1"}


def test_web_extract_payload_uses_url_verbatim():
    payload = build_web_extract_payload(
        url="https://docs.example.com/a",
        reason=EvidenceReasonCode.USER_REQUESTED,
        max_chars_per_source=4000,
        metadata={"run_id": "run-1"},
    )

    assert payload == {
        "url": "https://docs.example.com/a",
        "reason": "USER_REQUESTED",
        "max_chars_per_source": 4000,
        "metadata": {"run_id": "run-1"},
    }


def test_parse_web_search_response_carries_gateway_usage_and_credits():
    parsed = parse_web_search_response(
        {
            "results": [
                {"title": "Docs", "url": "https://docs.example.com/a", "snippet": "A"},
            ],
            "credits_used": 2,
            "gateway_usage": {
                "gateway_request_id": "gw-search-1",
                "provider": "tavily",
                "provider_request_id": "provider-1",
                "cache_hit": False,
                "billing_units": 2,
                "cost_usd": "0.002",
            },
        }
    )

    assert parsed.results[0].url_text == "https://docs.example.com/a"
    assert parsed.credits_used == 2
    assert parsed.gateway_usage == GatewayUsage(
        gateway_request_id="gw-search-1",
        provider="tavily",
        provider_request_id="provider-1",
        cache_hit=False,
        billing_units=2,
        cost_usd=Decimal("0.002"),
    )
```

Append:

```python
def test_parse_web_extract_response_marks_content_untrusted():
    parsed = parse_web_extract_response(
        {
            "url": "https://docs.example.com/a",
            "title": "Docs",
            "content": "Extracted evidence",
            "credits_used": 1,
            "gateway_usage": {
                "gateway_request_id": "gw-extract-1",
                "provider": "tavily",
                "cache_hit": True,
                "billing_units": 1,
                "cost_usd": "0.001",
            },
        }
    )

    assert parsed == EvidenceExtractResponse(
        url="https://docs.example.com/a",
        title="Docs",
        content="Extracted evidence",
        trust="untrusted",
        gateway_usage=GatewayUsage(
            gateway_request_id="gw-extract-1",
            provider="tavily",
            cache_hit=True,
            billing_units=1,
            cost_usd=Decimal("0.001"),
        ),
        credits_used=1,
    )


def test_parse_web_search_response_wraps_malformed_result_as_gateway_response_error():
    with pytest.raises(GatewayResponseError, match="url"):
        parse_web_search_response(
            {
                "results": [{"title": "Bad", "url": "not-a-url", "snippet": "bad"}],
                "gateway_usage": {
                    "gateway_request_id": "gw-1",
                    "provider": "tavily",
                    "billing_units": 1,
                    "cost_usd": "0.01",
                },
            }
        )


def test_http_url_round_trip_preserves_provenance_string_for_path_urls():
    parsed = parse_web_search_response(
        {
            "results": [{"title": "Docs", "url": "https://docs.example.com/a", "snippet": "A"}],
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "tavily",
                "billing_units": 1,
                "cost_usd": "0.01",
            },
        }
    )

    assert parsed.results[0].url_text == "https://docs.example.com/a"


def test_parse_web_search_response_rejects_missing_results():
    with pytest.raises(GatewayResponseError, match="results missing"):
        parse_web_search_response(
            {
                "gateway_usage": {
                    "gateway_request_id": "gw-1",
                    "provider": "tavily",
                    "billing_units": 1,
                    "cost_usd": "0.01",
                }
            }
        )


def test_parse_web_search_response_rejects_missing_usage():
    with pytest.raises(GatewayResponseError, match="gateway_usage missing"):
        parse_web_search_response({"results": []})


def test_parse_web_extract_response_rejects_missing_usage():
    with pytest.raises(GatewayResponseError, match="gateway_usage missing"):
        parse_web_extract_response({"url": "https://docs.example.com/a", "content": "x"})
```

- [ ] **Step 2: Run evidence gateway IO tests to verify they fail**

Run:

```bash
pytest tests/unit/evidence/test_gateway_io.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'optimus.evidence.gateway_io'`.

- [ ] **Step 3: Implement evidence-owned payload builders and parsers**

Create `src/optimus/evidence/gateway_io.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from optimus.evidence.models import (
    EvidenceExtractResponse,
    EvidenceSearchResponse,
    EvidenceSearchResult,
)
from optimus.gateway.errors import GatewayResponseError
from optimus.gateway.models import GatewayUsage
from optimus.tools.policy import EvidenceReasonCode


def build_web_search_payload(
    *,
    query: str,
    reason: EvidenceReasonCode,
    allowed_domains: tuple[str, ...],
    result_cap: int,
    search_depth: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": query,
        "reason": reason.value,
        "allowed_domains": list(allowed_domains),
        "result_cap": result_cap,
        "search_depth": search_depth,
    }
    if metadata:
        payload["metadata"] = metadata
    return payload


def build_web_extract_payload(
    *,
    url: str,
    reason: EvidenceReasonCode,
    max_chars_per_source: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": url,
        "reason": reason.value,
        "max_chars_per_source": max_chars_per_source,
    }
    if metadata:
        payload["metadata"] = metadata
    return payload


def parse_web_search_response(body: dict[str, Any]) -> EvidenceSearchResponse:
    usage = _parse_gateway_usage(body)
    results_body = body.get("results")
    if not isinstance(results_body, list):
        raise GatewayResponseError("results missing")
    try:
        return EvidenceSearchResponse(
            results=tuple(EvidenceSearchResult.model_validate(item) for item in results_body),
            gateway_usage=usage,
            credits_used=int(body.get("credits_used", 0)),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise GatewayResponseError(str(exc)) from exc


def parse_web_extract_response(body: dict[str, Any]) -> EvidenceExtractResponse:
    usage = _parse_gateway_usage(body)
    try:
        return EvidenceExtractResponse(
            url=body["url"],
            title=str(body.get("title", "")),
            content=body["content"],
            trust="untrusted",
            gateway_usage=usage,
            credits_used=int(body.get("credits_used", 0)),
        )
    except KeyError as exc:
        raise GatewayResponseError(f"{exc.args[0]} missing") from exc
    except (TypeError, ValueError, ValidationError) as exc:
        raise GatewayResponseError(str(exc)) from exc


def _parse_gateway_usage(body: dict[str, Any]) -> GatewayUsage:
    usage_body = body.get("gateway_usage")
    if not isinstance(usage_body, dict):
        raise GatewayResponseError("gateway_usage missing")
    try:
        return GatewayUsage.model_validate(usage_body)
    except ValidationError as exc:
        raise GatewayResponseError(str(exc)) from exc
```

Update `src/optimus/evidence/__init__.py`:

```python
from optimus.evidence.gateway_io import (
    build_web_extract_payload,
    build_web_search_payload,
    parse_web_extract_response,
    parse_web_search_response,
)
```

Add those four names to `__all__`. Do not import `optimus.evidence` from `src/optimus/gateway/models.py`, `src/optimus/gateway/client.py`, or `src/optimus/gateway/__init__.py`; the gateway package stays below the evidence package in the dependency graph.

- [ ] **Step 4: Run evidence gateway IO tests**

Run:

```bash
pytest tests/unit/evidence/test_gateway_io.py tests/unit/evidence/test_models.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/optimus/evidence/gateway_io.py src/optimus/evidence/__init__.py tests/unit/evidence/test_gateway_io.py
git commit -m "Add evidence-owned gateway IO."
```

## Task 5: Generic Gateway Tool Post Method

**Files:**
- Modify: `src/optimus/gateway/client.py`
- Modify: `tests/unit/gateway/test_client.py`

- [ ] **Step 1: Add failing client tests**

Append to `tests/unit/gateway/test_client.py`:

```python
def test_post_tool_json_posts_to_gateway_tool_endpoint():
    transport = FakeTransport(response={"ok": True})
    client = GatewayClient(settings=settings(), transport=transport)

    response = client.post_tool_json(
        path="/v1/tools/web/search",
        payload={"query": "latest pytest release"},
    )

    assert response == {"ok": True}
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url == "https://gateway.optimus.ai/v1/tools/web/search"
    assert request.headers == {
        "Authorization": "Bearer opt_live_abc",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    assert request.payload == {"query": "latest pytest release"}


def test_post_tool_json_validates_trusted_gateway_before_transport():
    transport = FakeTransport()
    client = GatewayClient(
        settings=OptimusGatewaySettings(
            gateway_url="https://rogue.attacker.com",
            optimus_api_key="opt_live_abc",
        ),
        transport=transport,
    )

    with pytest.raises(ValueError, match="gateway origin not in trusted set"):
        client.post_tool_json(path="/v1/tools/web/search", payload={"query": "current fact"})

    assert transport.requests == []


def test_post_tool_json_rejects_non_tool_path():
    client = GatewayClient(settings=settings(), transport=FakeTransport())

    with pytest.raises(ValueError, match="tool path must start with /v1/tools/"):
        client.post_tool_json(path="/v1/responses", payload={})
```

- [ ] **Step 2: Run client tests to verify they fail**

Run:

```bash
pytest tests/unit/gateway/test_client.py -v
```

Expected: FAIL with missing `GatewayClient.post_tool_json`.

- [ ] **Step 3: Add generic gateway tool post method**

Add this method to `GatewayClient` after `create_response()` in `src/optimus/gateway/client.py`:

```python
    def post_tool_json(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not path.startswith("/v1/tools/"):
            raise ValueError("tool path must start with /v1/tools/")
        self._settings.validate_trusted_gateway()
        return self._transport.post_json(
            GatewayRequest(
                method="POST",
                url=self._url(path),
                headers=self._json_headers(),
                payload=payload,
                timeout_seconds=self._timeout_seconds,
            )
        )
```

Do not import `optimus.evidence` from `src/optimus/gateway/client.py`, `src/optimus/gateway/models.py`, or `src/optimus/gateway/__init__.py`. The gateway layer remains a generic transport/wire layer.

- [ ] **Step 4: Run gateway client and model tests**

Run:

```bash
pytest tests/unit/gateway/test_client.py tests/unit/gateway/test_models.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/optimus/gateway/client.py tests/unit/gateway/test_client.py
git commit -m "Add generic gateway tool posting."
```

## Task 6: Evidence Acquisition Service

**Files:**
- Create: `src/optimus/evidence/domain_policy.py`
- Create: `src/optimus/evidence/acquisition.py`
- Modify: `src/optimus/evidence/__init__.py`
- Test: `tests/unit/evidence/test_domain_policy.py`
- Test: `tests/unit/evidence/test_acquisition.py`

- [ ] **Step 1: Write failing evidence domain policy tests**

Create `tests/unit/evidence/test_domain_policy.py`:

```python
import pytest

from optimus.evidence.domain_policy import EvidenceDomainPolicy, EvidenceDomainRejected


def test_effective_domains_intersect_requested_with_configured_allowlist():
    policy = EvidenceDomainPolicy(configured_allowed_domains=("example.com", "pypi.org"))

    assert policy.effective_allowed_domains(("Example.COM", "evil.com")) == ("example.com",)


def test_effective_domains_reject_when_request_has_no_configured_domain():
    policy = EvidenceDomainPolicy(configured_allowed_domains=("example.com",))

    with pytest.raises(EvidenceDomainRejected, match="allowed_domains not in configured evidence allowlist"):
        policy.effective_allowed_domains(("evil.com",))


def test_effective_domains_do_not_widen_configured_subdomain():
    policy = EvidenceDomainPolicy(configured_allowed_domains=("docs.example.com",))

    with pytest.raises(EvidenceDomainRejected, match="allowed_domains not in configured evidence allowlist"):
        policy.effective_allowed_domains(("example.com",))


def test_domain_policy_allows_subdomains_and_default_https_port():
    policy = EvidenceDomainPolicy(configured_allowed_domains=("example.com",))
    effective = policy.effective_allowed_domains(("example.com",))

    assert policy.url_allowed("https://docs.example.com/a", effective) is True
    assert policy.url_allowed("https://example.com:443/a", effective) is True


def test_domain_policy_rejects_off_allowlist_urls():
    policy = EvidenceDomainPolicy(configured_allowed_domains=("example.com",))
    effective = policy.effective_allowed_domains(("example.com",))

    assert policy.url_allowed("https://evil.com/a", effective) is False
    with pytest.raises(EvidenceDomainRejected, match="URL host not in effective allowed domains"):
        policy.assert_url_allowed("https://evil.com/a", effective)
```

- [ ] **Step 2: Run domain policy tests to verify they fail**

Run:

```bash
pytest tests/unit/evidence/test_domain_policy.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'optimus.evidence.domain_policy'`.

- [ ] **Step 3: Implement configured evidence domain policy**

Create `src/optimus/evidence/domain_policy.py`:

```python
from __future__ import annotations

from urllib.parse import urlparse


class EvidenceDomainRejected(ValueError):
    """Raised when caller-requested or gateway-returned domains fail local policy."""


class EvidenceDomainPolicy:
    def __init__(self, *, configured_allowed_domains: tuple[str, ...]) -> None:
        self._configured_domains = frozenset(
            domain
            for domain in (_normalize_domain(value) for value in configured_allowed_domains)
            if domain
        )
        if not self._configured_domains:
            raise ValueError("configured_allowed_domains must not be empty")

    def effective_allowed_domains(self, requested_domains: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(
            domain
            for domain in (_normalize_domain(value) for value in requested_domains)
            if domain
        )
        effective = tuple(
            domain
            for domain in normalized
            if any(_domain_matches_configured(domain, configured) for configured in self._configured_domains)
        )
        if not effective:
            raise EvidenceDomainRejected("allowed_domains not in configured evidence allowlist")
        return effective

    def url_allowed(self, url: str, effective_allowed_domains: tuple[str, ...]) -> bool:
        host = _normalize_url_host(url)
        return bool(host) and any(_host_matches_domain(host, domain) for domain in effective_allowed_domains)

    def assert_url_allowed(self, url: str, effective_allowed_domains: tuple[str, ...]) -> None:
        if not self.url_allowed(url, effective_allowed_domains):
            raise EvidenceDomainRejected("URL host not in effective allowed domains")


def _domain_matches_configured(domain: str, configured: str) -> bool:
    return domain == configured or domain.endswith(f".{configured}")


def _host_matches_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def _normalize_url_host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname is None:
        return ""
    return parsed.hostname.lower().rstrip(".")


def _normalize_domain(value: str) -> str:
    parsed = urlparse(value)
    host = parsed.hostname if parsed.scheme and parsed.netloc else value.split("/", 1)[0]
    host = host.split(":", 1)[0]
    return host.lower().strip().rstrip(".")
```

This local domain policy is a defense-in-depth gate. The Optimus Gateway remains the authoritative trust boundary for provider keys, server-side domain allowlists, budgets, and policy revalidation, but local Plan 4 code must not convert caller-supplied domains into trusted provenance without intersecting them against this configured allowlist.

Origin and host trust for evidence URLs is enforced by `EvidenceDomainPolicy`, not by `ToolInvocationPolicy`. `ToolInvocationPolicy` remains responsible for trigger/reason/mode/provenance/cap authorization and rejects non-HTTPS extract URLs as a direct-call guard.

- [ ] **Step 4: Write failing acquisition service tests**

Create `tests/unit/evidence/test_acquisition.py`:

```python
from decimal import Decimal

import pytest

from optimus.evidence.acquisition import EvidenceAcquisitionService
from optimus.evidence.domain_policy import EvidenceDomainPolicy, EvidenceDomainRejected
from optimus.evidence.ledger import EvidenceLedger
from optimus.evidence.models import (
    EvidenceExtractRequest,
    EvidenceRequest,
)
from optimus.gateway.errors import GatewayHttpError
from optimus.runtime.modes import ExecutionMode
from optimus.tools.policy import EvidenceReasonCode, ToolClass, ToolPolicySignal
from optimus.tools.registry import ToolCallRejected, ToolRegistry


def domain_policy() -> EvidenceDomainPolicy:
    return EvidenceDomainPolicy(configured_allowed_domains=("docs.example.com",))


class FakeGatewayClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def post_tool_json(self, *, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append({"path": path, "payload": payload})
        if path == "/v1/tools/web/search":
            return {
                "results": [
                    {"title": "Docs", "url": "https://docs.example.com/a", "snippet": "A"},
                ],
                "credits_used": 2,
                "gateway_usage": {
                    "gateway_request_id": "gw-search-1",
                    "provider": "tavily",
                    "provider_request_id": "provider-search-1",
                    "cache_hit": False,
                    "billing_units": 2,
                    "cost_usd": "0.002",
                },
            }
        if path == "/v1/tools/web/extract":
            return {
                "url": "https://docs.example.com/a",
                "title": "Docs",
                "content": "Evidence text",
                "credits_used": 1,
                "gateway_usage": {
                    "gateway_request_id": "gw-extract-1",
                    "provider": "tavily",
                    "cache_hit": True,
                    "billing_units": 1,
                    "cost_usd": "0.001",
                },
            }
        raise AssertionError(f"unexpected path: {path}")


class OffAllowlistGatewayClient(FakeGatewayClient):
    def post_tool_json(self, *, path: str, payload: dict[str, object]) -> dict[str, object]:
        body = super().post_tool_json(path=path, payload=payload)
        if path == "/v1/tools/web/search":
            body["results"] = [{"title": "Bad", "url": "https://evil.com/a", "snippet": "bad"}]
        return body


class FailingGatewayClient(FakeGatewayClient):
    def post_tool_json(self, *, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append({"path": path, "payload": payload})
        raise GatewayHttpError(502, "gateway unavailable")


def test_search_authorizes_gateway_call_and_records_ledger_entry():
    gateway = FakeGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = EvidenceRequest(
        run_id="run-1",
        query="latest pytest release",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        allowed_domains=("docs.example.com",),
    )

    response, ledger = service.search(request, execution_mode=ExecutionMode.PLAN)

    assert response.results[0].url_text == "https://docs.example.com/a"
    assert gateway.calls[0]["path"] == "/v1/tools/web/search"
    assert gateway.calls[0]["payload"]["query"] == "latest pytest release"
    assert service.registry.search_result_urls("run-1") == frozenset({"https://docs.example.com/a"})
    assert ledger.entries[0].tool_class is ToolClass.WEB_SEARCH
    assert ledger.entries[0].run_id == "run-1"
    assert ledger.entries[0].gateway_request_id == "gw-search-1"
    assert ledger.total_cost_usd() == Decimal("0.002")
    assert ledger.total_credits() == 2


def test_search_intersects_request_domains_with_configured_allowlist():
    gateway = FakeGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = EvidenceRequest(
        run_id="run-1",
        query="latest pytest release",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        allowed_domains=("docs.example.com", "evil.com"),
    )

    service.search(request, execution_mode=ExecutionMode.PLAN)

    assert gateway.calls[0]["payload"]["allowed_domains"] == ["docs.example.com"]


def test_search_rejects_unconfigured_requested_domain_before_gateway_call():
    gateway = FakeGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = EvidenceRequest(
        run_id="run-1",
        query="look this up",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        allowed_domains=("evil.com",),
    )

    with pytest.raises(EvidenceDomainRejected, match="allowed_domains not in configured evidence allowlist"):
        service.search(request, execution_mode=ExecutionMode.PLAN)

    assert gateway.calls == []
    assert service.registry.call_count("run-1") == 0


def test_search_rejects_off_allowlist_gateway_result_before_provenance_recording():
    gateway = OffAllowlistGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = EvidenceRequest(
        run_id="run-1",
        query="latest pytest release",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        allowed_domains=("docs.example.com",),
    )

    with pytest.raises(EvidenceDomainRejected, match="URL host not in effective allowed domains"):
        service.search(request, execution_mode=ExecutionMode.PLAN)

    assert service.registry.search_result_urls("run-1") == frozenset()
    assert service.ledger.entries == ()


def test_gateway_failure_consumes_authorized_attempt_without_ledger_entry():
    gateway = FailingGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = EvidenceRequest(
        run_id="run-1",
        query="latest pytest release",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
        allowed_domains=("docs.example.com",),
    )

    with pytest.raises(GatewayHttpError):
        service.search(request, execution_mode=ExecutionMode.PLAN)

    assert service.registry.call_count("run-1") == 1
    assert service.ledger.entries == ()


def test_search_rejects_without_policy_trigger_before_gateway_call():
    gateway = FakeGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = EvidenceRequest(
        run_id="run-1",
        query="look this up",
        reason=EvidenceReasonCode.NONE,
        policy_signal=ToolPolicySignal.LOCAL_CODE_CHANGE,
        allowed_domains=("docs.example.com",),
    )

    with pytest.raises(ToolCallRejected, match="no policy trigger matched"):
        service.search(request, execution_mode=ExecutionMode.PLAN)

    assert gateway.calls == []


def test_concurrent_successful_search_calls_do_not_drop_ledger_entries():
    from concurrent.futures import ThreadPoolExecutor

    gateway = FakeGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )

    def search_once(index: int) -> None:
        request = EvidenceRequest(
            run_id="run-1",
            query=f"latest pytest release {index}",
            reason=EvidenceReasonCode.USER_REQUESTED,
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT,
            allowed_domains=("docs.example.com",),
        )
        service.search(request, execution_mode=ExecutionMode.PLAN)

    with ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(search_once, range(5)))

    assert service.registry.call_count("run-1") == 5
    assert len(service.ledger.entries_for_run("run-1")) == 5


def test_extract_requires_prior_search_result_and_records_separate_usage():
    gateway = FakeGatewayClient()
    registry = ToolRegistry(max_calls_per_run=10)
    registry.record_search_results(run_id="run-1", urls=("https://docs.example.com/a",))
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=registry,
        ledger=EvidenceLedger(),
    )
    request = EvidenceExtractRequest(
        run_id="run-1",
        url="https://docs.example.com/a",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
        allowed_domains=("docs.example.com",),
    )

    response, ledger = service.extract(request, execution_mode=ExecutionMode.CHAT)

    assert response.content == "Evidence text"
    assert response.trust == "untrusted"
    assert gateway.calls[0]["path"] == "/v1/tools/web/extract"
    assert gateway.calls[0]["payload"]["url"] == "https://docs.example.com/a"
    assert ledger.entries[0].tool_class is ToolClass.WEB_EXTRACT
    assert ledger.entries[0].gateway_request_id == "gw-extract-1"
    assert ledger.total_billing_units() == 1
    assert ledger.total_credits() == 1


def test_extract_rejects_unapproved_url_before_gateway_call():
    gateway = FakeGatewayClient()
    service = EvidenceAcquisitionService(
        gateway_client=gateway,
        domain_policy=domain_policy(),
        registry=ToolRegistry(max_calls_per_run=10),
        ledger=EvidenceLedger(),
    )
    request = EvidenceExtractRequest(
        run_id="run-1",
        url="https://docs.example.com/a",
        reason=EvidenceReasonCode.USER_REQUESTED,
        policy_signal=ToolPolicySignal.APPROVED_SEARCH_RESULT_PROVENANCE,
        allowed_domains=("docs.example.com",),
    )

    with pytest.raises(ToolCallRejected, match="URL not in approved search-result set"):
        service.extract(request, execution_mode=ExecutionMode.PLAN)

    assert gateway.calls == []
```

- [ ] **Step 5: Run acquisition tests to verify they fail**

Run:

```bash
pytest tests/unit/evidence/test_acquisition.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'optimus.evidence.acquisition'`.

- [ ] **Step 6: Implement evidence acquisition service**

Create `src/optimus/evidence/acquisition.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock

from optimus.evidence.domain_policy import EvidenceDomainPolicy
from optimus.evidence.gateway_io import (
    build_web_extract_payload,
    build_web_search_payload,
    parse_web_extract_response,
    parse_web_search_response,
)
from optimus.evidence.ledger import EvidenceLedger, EvidenceLedgerEntry
from optimus.evidence.models import (
    EvidenceExtractRequest,
    EvidenceExtractResponse,
    EvidenceRequest,
    EvidenceSearchResponse,
)
from optimus.gateway.client import GatewayClient
from optimus.runtime.modes import ExecutionMode
from optimus.tools.policy import ToolClass, ToolInvocationRequest
from optimus.tools.registry import ToolRegistry


class EvidenceAcquisitionService:
    def __init__(
        self,
        *,
        gateway_client: GatewayClient,
        domain_policy: EvidenceDomainPolicy,
        registry: ToolRegistry | None = None,
        ledger: EvidenceLedger | None = None,
    ) -> None:
        self.gateway_client = gateway_client
        self.domain_policy = domain_policy
        self.registry = registry or ToolRegistry()
        self.ledger = ledger or EvidenceLedger()
        self._ledger_lock = Lock()

    def search(
        self,
        request: EvidenceRequest,
        *,
        execution_mode: ExecutionMode,
    ) -> tuple[EvidenceSearchResponse, EvidenceLedger]:
        effective_allowed_domains = self.domain_policy.effective_allowed_domains(request.allowed_domains)
        self.registry.authorize_and_record_call(
            ToolInvocationRequest(
                run_id=request.run_id,
                tool_class=ToolClass.WEB_SEARCH,
                execution_mode=execution_mode,
                policy_signal=request.policy_signal,
                reason=request.reason,
                allowed_domains=effective_allowed_domains,
            )
        )
        body = self.gateway_client.post_tool_json(
            path="/v1/tools/web/search",
            payload=build_web_search_payload(
                query=request.query,
                reason=request.reason,
                allowed_domains=effective_allowed_domains,
                result_cap=request.result_cap,
                search_depth=request.search_depth,
                metadata={
                    "run_id": request.run_id,
                    "session_id": request.session_id,
                    "policy_signal": request.policy_signal.value,
                },
            ),
        )
        response = parse_web_search_response(body)
        urls = tuple(result.url_text for result in response.results)
        for url in urls:
            self.domain_policy.assert_url_allowed(url, effective_allowed_domains)
        self.registry.record_search_results(run_id=request.run_id, urls=urls)
        ledger = self._record_ledger_entry(
            EvidenceLedgerEntry.from_gateway_usage(
                run_id=request.run_id,
                session_id=request.session_id,
                reason=request.reason,
                policy_signal=request.policy_signal.value,
                tool_class=ToolClass.WEB_SEARCH,
                sources=urls,
                gateway_usage=response.gateway_usage,
                credits_used=response.credits_used,
                queried_at=_utc_now(),
            )
        )
        return response, ledger

    def extract(
        self,
        request: EvidenceExtractRequest,
        *,
        execution_mode: ExecutionMode,
    ) -> tuple[EvidenceExtractResponse, EvidenceLedger]:
        target_url = request.url_text
        effective_allowed_domains = self.domain_policy.effective_allowed_domains(request.allowed_domains)
        self.domain_policy.assert_url_allowed(target_url, effective_allowed_domains)
        self.registry.authorize_and_record_call(
            ToolInvocationRequest(
                run_id=request.run_id,
                tool_class=ToolClass.WEB_EXTRACT,
                execution_mode=execution_mode,
                policy_signal=request.policy_signal,
                reason=request.reason,
                target_url=target_url,
                prior_search_result_urls=self.registry.search_result_urls(request.run_id),
            )
        )
        body = self.gateway_client.post_tool_json(
            path="/v1/tools/web/extract",
            payload=build_web_extract_payload(
                url=target_url,
                reason=request.reason,
                max_chars_per_source=request.max_chars_per_source,
                metadata={
                    "run_id": request.run_id,
                    "session_id": request.session_id,
                    "policy_signal": request.policy_signal.value,
                },
            ),
        )
        response = parse_web_extract_response(body)
        ledger = self._record_ledger_entry(
            EvidenceLedgerEntry.from_gateway_usage(
                run_id=request.run_id,
                session_id=request.session_id,
                reason=request.reason,
                policy_signal=request.policy_signal.value,
                tool_class=ToolClass.WEB_EXTRACT,
                sources=(target_url,),
                gateway_usage=response.gateway_usage,
                credits_used=response.credits_used,
                queried_at=_utc_now(),
            )
        )
        return response, ledger

    def _record_ledger_entry(self, entry: EvidenceLedgerEntry) -> EvidenceLedger:
        with self._ledger_lock:
            self.ledger = self.ledger.record(entry)
            return self.ledger


def _utc_now() -> datetime:
    return datetime.now(UTC)
```

Update `src/optimus/evidence/__init__.py`:

```python
from optimus.evidence.acquisition import EvidenceAcquisitionService
from optimus.evidence.domain_policy import EvidenceDomainPolicy, EvidenceDomainRejected
```

Add `"EvidenceAcquisitionService"`, `"EvidenceDomainPolicy"`, and `"EvidenceDomainRejected"` to `__all__`.

- [ ] **Step 7: Run evidence service tests**

Run:

```bash
pytest tests/unit/evidence/test_domain_policy.py tests/unit/evidence/test_acquisition.py tests/unit/evidence/test_models.py tests/unit/evidence/test_ledger.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/optimus/evidence tests/unit/evidence/test_domain_policy.py tests/unit/evidence/test_acquisition.py
git commit -m "Add policy-aware evidence acquisition."
```

## Task 7: ACP Evidence Dispatch Methods

**Files:**
- Modify: `src/optimus/acp/dispatcher.py`
- Modify: `tests/unit/acp/test_dispatcher.py`

- [ ] **Step 1: Add failing dispatcher tests**

Append to `tests/unit/acp/test_dispatcher.py`:

```python
from optimus.evidence.domain_policy import EvidenceDomainRejected
from optimus.evidence.ledger import EvidenceLedger
from optimus.evidence.models import (
    EvidenceExtractResponse,
    EvidenceSearchResponse,
    EvidenceSearchResult,
)
from optimus.gateway.models import GatewayUsage
from optimus.tools.policy import EvidenceReasonCode, ToolClass, ToolPolicySignal
from optimus.tools.registry import ToolCallRejected


class FakeEvidenceService:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, object]] = []
        self.extract_calls: list[dict[str, object]] = []

    def search(self, request, *, execution_mode):
        self.search_calls.append({"request": request, "execution_mode": execution_mode})
        response = EvidenceSearchResponse(
            results=(
                EvidenceSearchResult(
                    title="Docs",
                    url="https://docs.example.com/a",
                    snippet="A",
                ),
            ),
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-search-1",
                provider="tavily",
                cache_hit=False,
                billing_units=2,
                cost_usd=Decimal("0.002"),
            ),
        )
        return response, EvidenceLedger()

    def extract(self, request, *, execution_mode):
        self.extract_calls.append({"request": request, "execution_mode": execution_mode})
        response = EvidenceExtractResponse(
            url="https://docs.example.com/a",
            title="Docs",
            content="Evidence text",
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-extract-1",
                provider="tavily",
                cache_hit=True,
                billing_units=1,
                cost_usd=Decimal("0.001"),
            ),
        )
        return response, EvidenceLedger()


def test_dispatcher_routes_evidence_search_to_service():
    evidence_service = FakeEvidenceService()
    dispatcher = JsonRpcDispatcher(evidence_service=evidence_service)

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-search-1",
            "method": "optimus.evidence.search",
            "params": {
                "run_id": "run-1",
                "query": "latest pytest release",
                "reason": "USER_REQUESTED",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert "error" not in response
    assert response["result"]["results"][0]["url"] == "https://docs.example.com/a"
    assert response["result"]["gateway_usage"]["gateway_request_id"] == "gw-search-1"
    assert response["result"]["ledger_run_total_cost_usd"] == "0"
    assert response["result"]["ledger_run_total_credits"] == 0
    assert evidence_service.search_calls[0]["request"].query == "latest pytest release"


def test_dispatcher_routes_evidence_extract_to_service():
    evidence_service = FakeEvidenceService()
    dispatcher = JsonRpcDispatcher(evidence_service=evidence_service)

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-extract-1",
            "method": "optimus.evidence.extract",
            "params": {
                "run_id": "run-1",
                "url": "https://docs.example.com/a",
                "reason": "USER_REQUESTED",
                "policy_signal": "APPROVED_SEARCH_RESULT_PROVENANCE",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert "error" not in response
    assert response["result"]["url"] == "https://docs.example.com/a"
    assert response["result"]["content"] == "Evidence text"
    assert response["result"]["gateway_usage"]["gateway_request_id"] == "gw-extract-1"
    assert response["result"]["ledger_run_total_cost_usd"] == "0"
    assert response["result"]["ledger_run_total_credits"] == 0


def test_dispatcher_rejects_malformed_evidence_search_request():
    dispatcher = JsonRpcDispatcher(evidence_service=FakeEvidenceService())

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-search-2",
            "method": "optimus.evidence.search",
            "params": {
                "run_id": "run-1",
                "query": "",
                "reason": "USER_REQUESTED",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert response["error"]["code"] == -32600
    assert response["error"]["message"] == "invalid request"


def test_dispatcher_reports_evidence_search_service_not_configured():
    dispatcher = JsonRpcDispatcher()

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-search-missing",
            "method": "optimus.evidence.search",
            "params": {
                "run_id": "run-1",
                "query": "latest pytest release",
                "reason": "USER_REQUESTED",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert response["error"]["code"] == -32601
    assert response["error"]["message"] == "evidence service not configured"


def test_dispatcher_reports_evidence_extract_service_not_configured():
    dispatcher = JsonRpcDispatcher()

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-extract-missing",
            "method": "optimus.evidence.extract",
            "params": {
                "run_id": "run-1",
                "url": "https://docs.example.com/a",
                "reason": "USER_REQUESTED",
                "policy_signal": "APPROVED_SEARCH_RESULT_PROVENANCE",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert response["error"]["code"] == -32601
    assert response["error"]["message"] == "evidence service not configured"


class RejectedEvidenceService(FakeEvidenceService):
    def search(self, request, *, execution_mode):
        from optimus.tools.policy import PolicyDecision, ToolInvocationDecision

        raise ToolCallRejected(
            ToolInvocationDecision(
                decision=PolicyDecision.REJECT,
                reason="no policy trigger matched",
                tool_class=ToolClass.WEB_SEARCH,
                policy_signal=ToolPolicySignal.LOCAL_CODE_CHANGE,
                reason_code=EvidenceReasonCode.NONE,
            )
        )


def test_dispatcher_maps_tool_call_rejected_to_invalid_request():
    dispatcher = JsonRpcDispatcher(evidence_service=RejectedEvidenceService())

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-search-rejected",
            "method": "optimus.evidence.search",
            "params": {
                "run_id": "run-1",
                "query": "look this up",
                "reason": "USER_REQUESTED",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert response["error"]["code"] == -32600
    assert response["error"]["message"] == "no policy trigger matched"


class DomainRejectedEvidenceService(FakeEvidenceService):
    def search(self, request, *, execution_mode):
        raise EvidenceDomainRejected("allowed_domains not in configured evidence allowlist")


def test_dispatcher_maps_evidence_domain_rejected_to_invalid_request():
    dispatcher = JsonRpcDispatcher(evidence_service=DomainRejectedEvidenceService())

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-search-domain-rejected",
            "method": "optimus.evidence.search",
            "params": {
                "run_id": "run-1",
                "query": "look this up",
                "reason": "USER_REQUESTED",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "allowed_domains": ["evil.com"],
            },
        }
    )

    assert response["error"]["code"] == -32600
    assert response["error"]["message"] == "allowed_domains not in configured evidence allowlist"


class ValueErrorEvidenceService(FakeEvidenceService):
    def search(self, request, *, execution_mode):
        raise ValueError("gateway origin not in trusted set: https://rogue.attacker.com")


def test_dispatcher_maps_gateway_trust_value_error_to_json_rpc_error():
    dispatcher = JsonRpcDispatcher(evidence_service=ValueErrorEvidenceService())

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "ev-search-3",
            "method": "optimus.evidence.search",
            "params": {
                "run_id": "run-1",
                "query": "current fact",
                "reason": "USER_REQUESTED",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert response["error"]["code"] == -32603
    assert "gateway origin not in trusted set" in response["error"]["message"]
```

- [ ] **Step 2: Run dispatcher tests to verify they fail**

Run:

```bash
pytest tests/unit/acp/test_dispatcher.py -v
```

Expected: FAIL with unexpected `evidence_service` argument.

- [ ] **Step 3: Add evidence service dispatch wiring**

Update imports in `src/optimus/acp/dispatcher.py`:

```python
from pydantic import ValidationError

from optimus.evidence.acquisition import EvidenceAcquisitionService
from optimus.evidence.domain_policy import EvidenceDomainRejected
from optimus.evidence.ledger import EvidenceLedger
from optimus.evidence.models import (
    EvidenceExtractRequest,
    EvidenceExtractResponse,
    EvidenceRequest,
    EvidenceSearchResponse,
)
from optimus.gateway.models import GatewayUsage
from optimus.tools.registry import ToolCallRejected
```

Update `JsonRpcDispatcher.__init__`:

```python
    def __init__(
        self,
        request_ids: RequestIdTracker | None = None,
        runtime_context: RuntimeContext | None = None,
        gateway_client: GatewayClient | None = None,
        evidence_service: EvidenceAcquisitionService | None = None,
    ) -> None:
        self._request_ids = request_ids or RequestIdTracker()
        self._runtime_context = runtime_context or RuntimeContext(
            execution_mode=ExecutionMode.PLAN,
            state=AgentState.CHAT_ONLY,
        )
        self._gateway_client = gateway_client
        self._evidence_service = evidence_service
```

Add branches inside `dispatch()` after `optimus.gateway.responses`:

```python
            if method == "optimus.evidence.search":
                if self._evidence_service is None:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=METHOD_NOT_FOUND, message="evidence service not configured"),
                    )
                try:
                    evidence_request = EvidenceRequest.model_validate(request.get("params"))
                except ValidationError:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                response, ledger = self._evidence_service.search(
                    evidence_request,
                    execution_mode=self._runtime_context.execution_mode,
                )
                return success_response(
                    request_id=request_id,
                    result=_evidence_search_payload(response, ledger, evidence_request.run_id),
                )

            if method == "optimus.evidence.extract":
                if self._evidence_service is None:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=METHOD_NOT_FOUND, message="evidence service not configured"),
                    )
                try:
                    extract_request = EvidenceExtractRequest.model_validate(request.get("params"))
                except ValidationError:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                response, ledger = self._evidence_service.extract(
                    extract_request,
                    execution_mode=self._runtime_context.execution_mode,
                )
                return success_response(
                    request_id=request_id,
                    result=_evidence_extract_payload(response, ledger, extract_request.run_id),
                )
```

Add exception handling next to `GatewayError`:

```python
        except ToolCallRejected as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INVALID_REQUEST, message=str(exc)),
            )
        except EvidenceDomainRejected as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INVALID_REQUEST, message=str(exc)),
            )
        except ValueError as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INTERNAL_ERROR, message=str(exc)),
            )
```

Add helpers at the bottom:

```python
def _gateway_usage_payload(usage: GatewayUsage) -> dict[str, Any]:
    return {
        "gateway_request_id": usage.gateway_request_id,
        "provider": usage.provider,
        "provider_request_id": usage.provider_request_id,
        "cache_hit": usage.cache_hit,
        "billing_units": usage.billing_units,
        "cost_usd": str(usage.cost_usd),
    }


def _evidence_search_payload(
    response: EvidenceSearchResponse,
    ledger: EvidenceLedger,
    run_id: str,
) -> dict[str, Any]:
    return {
        "results": [
            {"title": result.title, "url": result.url_text, "snippet": result.snippet}
            for result in response.results
        ],
        "gateway_usage": _gateway_usage_payload(response.gateway_usage),
        "ledger_run_total_cost_usd": str(ledger.total_cost_usd(run_id=run_id)),
        "ledger_run_total_credits": ledger.total_credits(run_id=run_id),
    }


def _evidence_extract_payload(
    response: EvidenceExtractResponse,
    ledger: EvidenceLedger,
    run_id: str,
) -> dict[str, Any]:
    return {
        "url": response.url_text,
        "title": response.title,
        "content": response.content,
        "trust": response.trust,
        "gateway_usage": _gateway_usage_payload(response.gateway_usage),
        "ledger_run_total_cost_usd": str(ledger.total_cost_usd(run_id=run_id)),
        "ledger_run_total_credits": ledger.total_credits(run_id=run_id),
    }
```

If `_gateway_response_payload()` already serializes gateway usage inline, refactor it to call `_gateway_usage_payload()` to avoid duplication.

- [ ] **Step 4: Run ACP dispatcher tests**

Run:

```bash
pytest tests/unit/acp/test_dispatcher.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/optimus/acp/dispatcher.py tests/unit/acp/test_dispatcher.py
git commit -m "Expose evidence acquisition over ACP."
```

## Task 8: Mocked Search-Then-Extract Integration Flow

**Files:**
- Create: `tests/integration/evidence/test_mocked_evidence_flow.py`
- Verify: `src/optimus/evidence/*`, `src/optimus/gateway/*`, `src/optimus/acp/dispatcher.py`

- [ ] **Step 1: Write mocked integration test**

Create `tests/integration/evidence/test_mocked_evidence_flow.py`:

```python
from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES, OptimusGatewaySettings
from optimus.evidence.acquisition import EvidenceAcquisitionService
from optimus.evidence.domain_policy import EvidenceDomainPolicy
from optimus.evidence.ledger import EvidenceLedger
from optimus.gateway.client import GatewayClient, GatewayRequest
from optimus.tools.registry import ToolRegistry


class CapturingEvidenceTransport:
    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict[str, object]:
        self.requests.append(request)
        if request.url.endswith("/v1/tools/web/search"):
            return {
                "results": [
                    {
                        "title": "Docs",
                        "url": "https://docs.example.com/a",
                        "snippet": "Authoritative docs",
                    },
                ],
                "credits_used": 2,
                "gateway_usage": {
                    "gateway_request_id": "gw-search-1",
                    "provider": "tavily",
                    "provider_request_id": "provider-search-1",
                    "cache_hit": False,
                    "billing_units": 2,
                    "cost_usd": "0.002",
                },
            }
        if request.url.endswith("/v1/tools/web/extract"):
            return {
                "url": "https://docs.example.com/a",
                "title": "Docs",
                "content": "Evidence text must be treated as untrusted text.",
                "credits_used": 1,
                "gateway_usage": {
                    "gateway_request_id": "gw-extract-1",
                    "provider": "tavily",
                    "cache_hit": True,
                    "billing_units": 1,
                    "cost_usd": "0.001",
                },
            }
        raise AssertionError(f"unexpected URL: {request.url}")


def test_mocked_search_then_extract_flow_uses_only_optimus_credentials(monkeypatch):
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.optimus.ai")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt_live_test")
    for key in LOCAL_PROVIDER_KEY_NAMES:
        monkeypatch.delenv(key, raising=False)

    settings = OptimusGatewaySettings.from_env()
    assert settings.validate_no_local_provider_keys() == ()

    transport = CapturingEvidenceTransport()
    registry = ToolRegistry(max_calls_per_run=10)
    service = EvidenceAcquisitionService(
        gateway_client=GatewayClient(settings=settings, transport=transport),
        domain_policy=EvidenceDomainPolicy(configured_allowed_domains=("docs.example.com",)),
        registry=registry,
        ledger=EvidenceLedger(),
    )
    dispatcher = JsonRpcDispatcher(evidence_service=service)

    search_response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "search-1",
            "method": "optimus.evidence.search",
            "params": {
                "run_id": "run-1",
                "query": "latest pytest release",
                "reason": "USER_REQUESTED",
                "policy_signal": "USER_REQUESTED_EXTERNAL_FACT",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )
    extract_response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "extract-1",
            "method": "optimus.evidence.extract",
            "params": {
                "run_id": "run-1",
                "url": "https://docs.example.com/a",
                "reason": "USER_REQUESTED",
                "policy_signal": "APPROVED_SEARCH_RESULT_PROVENANCE",
                "allowed_domains": ["docs.example.com"],
            },
        }
    )

    assert "error" not in search_response
    assert "error" not in extract_response
    assert search_response["result"]["gateway_usage"]["gateway_request_id"] == "gw-search-1"
    assert extract_response["result"]["gateway_usage"]["gateway_request_id"] == "gw-extract-1"
    assert extract_response["result"]["trust"] == "untrusted"
    assert extract_response["result"]["ledger_run_total_cost_usd"] == "0.003"
    assert extract_response["result"]["ledger_run_total_credits"] == 3
    assert [request.url for request in transport.requests] == [
        "https://gateway.optimus.ai/v1/tools/web/search",
        "https://gateway.optimus.ai/v1/tools/web/extract",
    ]
    assert transport.requests[0].headers["Authorization"] == "Bearer opt_live_test"
    assert transport.requests[0].payload["query"] == "latest pytest release"
    assert transport.requests[1].payload["url"] == "https://docs.example.com/a"
    assert registry.call_count("run-1") == 2
```

- [ ] **Step 2: Run integration test**

Run:

```bash
pytest tests/integration/evidence/test_mocked_evidence_flow.py -v
```

Expected: PASS with no provider key configured in the test environment.

- [ ] **Step 3: Run focused evidence/tool/gateway suite**

Run:

```bash
pytest tests/unit/tools tests/unit/evidence tests/unit/gateway tests/unit/acp/test_dispatcher.py tests/integration/evidence -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/evidence/test_mocked_evidence_flow.py
git commit -m "Verify mocked evidence acquisition flow."
```

## Task 9: README Evidence Foundation Note

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the README evidence note**

Append under the existing Phase 1 gateway configuration note:

```markdown
### Phase 1 Tool Policy and Evidence Foundation

Tool calls are authorized by `ToolInvocationPolicy` before execution and are
recorded through `ToolRegistry.authorize_and_record_call()` so per-run caps are
enforced atomically. Web search and extract have local defense-in-depth checks
and remote gateway policy enforcement: the local runtime intersects requested
domains with the configured evidence allowlist, validates returned URLs before
they become provenance, sends only authenticated Optimus Gateway requests, keeps
URL provenance per run, and records `GatewayUsage` fields into
`EvidenceLedgerEntry` objects without estimating cost locally. Extracted web
content is untrusted evidence text and must not be executed or promoted to
policy without a separate harness decision.
```

- [ ] **Step 2: Run focused smoke tests**

Run:

```bash
pytest tests/unit/tools tests/unit/evidence tests/integration/evidence -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document tool policy and evidence foundation."
```

## Task 10: Coverage and Final Verification

**Files:**
- Verify: all files from Tasks 1-9

- [ ] **Step 1: Run focused coverage for safety-critical Plan 4 modules**

Run:

```bash
pytest tests/unit/tools tests/unit/evidence tests/unit/gateway/test_models.py tests/unit/gateway/test_client.py tests/unit/acp/test_dispatcher.py tests/integration/evidence --cov=optimus.tools.policy --cov=optimus.tools.registry --cov=optimus.evidence --cov=optimus.gateway.models --cov=optimus.gateway.client --cov=optimus.acp.dispatcher --cov-branch --cov-report=term-missing --cov-fail-under=80
```

Expected: PASS with focused coverage at or above 80%. `optimus.tools.policy`, `optimus.tools.registry`, and `optimus.evidence.ledger` should trend materially higher because they are safety-critical for authorization and reconciliation.

- [ ] **Step 2: Run the full package coverage gate**

Run:

```bash
pytest --cov=optimus --cov-branch --cov-report=term-missing -v
```

Expected: PASS with aggregate Python production-code coverage at or above the `pyproject.toml` `fail_under = 80` gate.

- [ ] **Step 3: Run the full test suite without coverage instrumentation**

Run:

```bash
pytest -v
```

Expected: PASS.

- [ ] **Step 4: Verify provider keys are absent from the implementation environment**

Run:

```bash
python -c "import os; from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES; found=[k for k in LOCAL_PROVIDER_KEY_NAMES if os.environ.get(k)]; print('FOUND=' + ','.join(found)); raise SystemExit(1 if found else 0)"
```

Expected: PASS with output `FOUND=`. If this fails on a developer workstation, unset provider key variables before running the release-gate subset. Do not add those keys to local config.

- [ ] **Step 5: Check working tree**

Run:

```bash
git status --short
```

Expected: only intentional Plan 4 implementation files are modified or added. Pre-existing unrelated IDE files, caches, extracted docs, or prior plan artifacts must not be staged.

- [ ] **Step 6: Commit final verification adjustments if needed**

If Task 10 required code or docs adjustments after verification, commit only those intentional files:

```bash
git add README.md src/optimus/tools src/optimus/evidence src/optimus/gateway src/optimus/acp/dispatcher.py tests/unit tests/integration
git commit -m "Complete tool policy and evidence acquisition foundation."
```

Skip this commit if Tasks 1-9 already committed all implementation changes and Task 10 made no edits.

## Self-Review

- Spec coverage: This plan implements the roadmap Plan 4 deliverables: `ToolInvocationPolicy`, reason codes, local-first policy, gateway web search/extract wrappers, URL provenance checks, per-run call caps, and `EvidenceLedgerEntry`.
- HLD section 8 coverage: Web evidence requires explicit trigger/reason/allowed domains, requested domains are intersected with a configured evidence allowlist before gateway calls, local repo reads remain allowed in Plan/Chat, and shell/patch safety remains deferred to Plans 5 and 8.
- LLD section 9E coverage: `ToolRegistry.authorize_and_record_call()` authorizes and records atomically, `execution_mode` is rejected when unknown, `EvidenceLedgerEntry` carries gateway usage fields directly, and evidence/cost records remain separable by `run_id` and `gateway_request_id`.
- Test Strategy section 6 coverage: Tests prove web search rejects without a valid trigger, `USER_REQUESTED` search with configured domains allows, search rejects off-allowlist gateway URLs before provenance recording, extract rejects out-of-set and non-HTTPS URLs, extract validates approved provenance signals, domain policy owns URL host trust, gateway usage propagates into evidence entries, sequential cap overflow is rejected without incrementing the counter, concurrent cap enforcement records exactly the configured maximum, and concurrent ledger writes do not drop entries.
- Boundary consistency: Plan 4 extends the existing Plan 3 gateway client. It does not add local Tavily/provider keys, durable usage persistence, retry/backoff, or staging gateway policy revalidation.
- Type consistency: `EvidenceReasonCode`, `ToolPolicySignal`, `ToolClass`, `GatewayUsage`, `EvidenceRequest`, `EvidenceExtractRequest`, `EvidenceLedgerEntry`, and `ToolRegistry` are defined before use and reused consistently across tasks.
- Red-flag scan: This plan contains no unexpanded work items. Later roadmap work is named only in Out of Scope with the owning plan.
- TDD compliance: Every production change starts with a failing test, then minimal implementation, then focused verification.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-03-tool-policy-evidence-acquisition.md`. Two execution options:

**1. Subagent-Driven (recommended when available)** - dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - execute tasks in this session task-by-task with checkpoints. Use `superpowers:executing-plans` if available; otherwise follow this plan directly with the same red/green/refactor discipline.

Before implementation, create or switch to a dedicated branch from latest `main`, for example `agent/codex/tool-policy-evidence-acquisition`, or create a separate worktree if the current Plan 3 implementation branch must remain untouched. Do not run `git commit`, push, or create/delete branches unless the user explicitly approves those actions.
