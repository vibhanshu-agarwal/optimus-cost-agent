# Plan 4 Review — Tool Policy and Evidence Acquisition (Architect / Auditor)

> **Re-review 2026-07-03 (amended plan):** All findings below (B1, M1–M5, L1–L7, and the nits) are **resolved** in the amended plan. The `gateway ↔ evidence` cycle is gone — payload/parsing moved to `optimus.evidence.gateway_io`, `GatewayClient` gained a generic `post_tool_json()` that never imports evidence, and the dependency graph is now a clean DAG (`acp → evidence → gateway → config`). One **new** defect was introduced and one prior coverage pattern recurs; both are captured in the "Re-review addendum" at the end of this document. Net verdict moves from *request changes* to **approve with one required test fix.**

**Plan:** `docs/superpowers/plans/2026-07-03-tool-policy-evidence-acquisition.md`
**Roadmap slot:** Plan 4 of `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
**Reviewed:** 2026-07-03 (original) · re-reviewed 2026-07-03 (amended)
**Reviewer role:** Senior Architect and Auditor
**Method:** Read the plan end-to-end (2,447 lines), then verified every cross-module claim against the actual tree it builds on — `src/optimus/gateway/{models,client,errors,__init__}.py`, `src/optimus/config/gateway.py`, `src/optimus/runtime/modes.py`, `src/optimus/tools/__init__.py`, `src/optimus/acp/dispatcher.py`, the existing `tests/unit/{gateway,acp}/…`, `AGENTS.md`, `pyproject.toml`, the roadmap Plan 4 charter, and the prior PR #8 gap audit. Import graphs and coverage-scope claims were traced by hand.

## Headline

The plan is a strong, disciplined TDD hand-off: red-before-green on every production change, verbatim reuse of the Plan 3 `GatewayUsage` model, correct atomic-cap locking, and a genuinely fail-closed provenance rule for web extract. Type reuse and Out-of-Scope discipline mirror the well-executed Plan 3.

**However, it ships one blocking architectural defect: the plan makes the low-level `optimus.gateway` package depend on the higher-level `optimus.evidence` domain, creating a circular import that will deterministically fail the plan's own Task 4 and Task 5 verification commands.** Fix the layering and the rest is largely sound. Below, findings are ordered by severity. Everything here is a defect in the plan's design to be resolved by amendment *before* execution — not a critique of an implementer.

---

## Blocking

### B1. Circular import + layering inversion between `gateway` and `evidence` (High)

**Where:** Task 4, Step 3 (append to `src/optimus/gateway/models.py`) and Task 5, Step 3 (imports in `src/optimus/gateway/client.py`).

The plan adds, at the bottom of `gateway/models.py`:

```python
from optimus.evidence.models import (
    EvidenceExtractResponse, EvidenceSearchResponse, EvidenceSearchResult,
)
```

But `evidence/models.py` and `evidence/ledger.py` both begin with `from optimus.gateway.models import GatewayUsage`, and Task 5 additionally makes `gateway/client.py` import `EvidenceExtractResponse, EvidenceSearchResponse`. That is a dependency cycle **and** an inversion: the transport/wire layer (`gateway`) should never import the evidence domain that sits above it.

This is not merely theoretical — it breaks the plan's own commands. `src/optimus/gateway/__init__.py` eagerly imports the client (`from optimus.gateway.client import GatewayClient, …`). Trace Task 4, Step 4 (`pytest tests/unit/gateway/test_evidence_models.py …`) in a fresh interpreter:

1. The test's first line is `from optimus.evidence.models import EvidenceExtractResponse, EvidenceSearchResponse`.
2. `evidence/models.py` starts, hits `from optimus.gateway.models import GatewayUsage`.
3. Importing `optimus.gateway.models` first runs the package `__init__`, which imports `gateway.client`, which imports `gateway.models`, whose appended bottom line does `from optimus.evidence.models import EvidenceSearchResponse` — but `evidence.models` is still mid-import (only line 1 executed, no classes defined yet).
4. Result: `ImportError: cannot import name 'EvidenceSearchResponse' from partially initialized module 'optimus.evidence.models' (most likely due to a circular import)`.

The plan's note to "place the evidence-model imports after `GatewayUsage` is defined" does not save it: whether it works becomes dependent on which test module pytest imports first in a given process, so it will pass in some invocations and fail in isolated ones (`pytest <one file>`), which is exactly what CI and the per-task steps do.

**Fix (pick one, keep the dependency one-way `evidence → gateway`):**
- Preferred: move `build_web_search_payload` / `build_web_extract_payload` / `parse_web_search_response` / `parse_web_extract_response` out of `gateway/models.py` into the evidence layer (e.g. `src/optimus/evidence/gateway_io.py`). Give `GatewayClient` a thin generic `post_tool(path, payload) -> dict` (or reuse the existing transport seam) and let the evidence acquisition service own parsing into `EvidenceSearchResponse` / `EvidenceExtractResponse`. The gateway client then never names an evidence type.
- Alternative: keep the methods on `GatewayClient` but have them return raw `dict` / a gateway-local DTO, and adapt to evidence types in `acquisition.py`.

Either way, `gateway/models.py` and `gateway/client.py` must not `import optimus.evidence.*`. This also removes the inverted coupling of the reusable gateway client to a single consumer's domain models.

---

## High / Medium

### M1. Focused-coverage gate (Task 10, Step 1) is likely to fail on gateway.models (Medium)

**Where:** Task 10, Step 1.

The command measures whole modules — `--cov=optimus.gateway.models --cov=optimus.gateway.client --cov=optimus.acp.dispatcher` — but the selected tests **exclude `tests/unit/gateway/test_models.py`**. That test is the only exercise of `build_chat_completions_payload` and the `_extract_text_from_output` list-walking branches in `gateway/models.py`; `create_response`-based tests never hit them (the fakes always supply `output_text`). With `--cov-branch --cov-fail-under=80`, those dead-in-this-subset lines drag `gateway.models` coverage down and can trip the gate even though the new evidence modules are near-100%.

**Fix:** add `tests/unit/gateway/test_models.py` to the Step 1 command, or narrow the `--cov` targets to the modules this slice actually introduces (`optimus.tools.policy`, `optimus.tools.registry`, `optimus.evidence.*`, and only the *new* functions in `gateway.models`).

### M2. Evidence ledger entry has no `run_id` / session linkage (Medium)

**Where:** Task 3 (`EvidenceLedgerEntry`) and Task 6 (`acquisition.py`).

`AGENTS.md` (Implementation Rules) requires persisting cost/usage "with `gateway_request_id`, provider, cache_hit, billing_units, cost_usd, model/version, **and run/session IDs**." The ledger entry captures the gateway usage fields and `sources`, but **not `run_id`** — even though `EvidenceRequest.run_id` is in hand at record time and the registry keys everything by run. An audit ledger whose entries can't be attributed to the run that produced them undercuts the ledger's purpose. Durable `ProviderUsage` persistence is correctly deferred to Plan 7, but the in-memory record should still carry `run_id` (and, where available, session ID) now.

**Fix:** add `run_id: str` (and optionally `session_id`) to `EvidenceLedgerEntry`; thread `request.run_id` through `from_gateway_usage(...)` in both `search()` and `extract()`.

### M3. `credits_used` is dead on the real code path (Medium)

**Where:** Task 3 (`EvidenceLedgerEntry.from_gateway_usage`, `EvidenceLedger.total_credits`).

`from_gateway_usage()` never sets `credits_used`, so every entry the acquisition service creates has `credits_used == 0`. `total_credits()` therefore only ever reflects hand-built entries (as in the ledger unit test) and is always 0 in production. Either `credits_used` should be populated from a gateway usage field (and the mapping made explicit vs. `billing_units`), or it should be removed. As written it's an untethered field with a reconciliation total that means nothing for real traffic, which is a trap for later cost work.

### M4. Shell / patch authorization is scope creep into Plans 5 and 8 (Medium)

**Where:** Task 1 (`ToolClass.SHELL_EXECUTION`, `ToolClass.PATCH_WORKSPACE`, `_authorize_shell_execution`, `composite_fitness_gate_passed`).

The roadmap assigns shell safety to **Plan 5** ("Permission Engine, Pre-Tool Guard, and Shell Safety" — `CommandSafetyValidator`, destructive-command handling) and fitness gates to **Plan 8**. Plan 4's own Out-of-Scope explicitly disclaims "shell command safety validator … belong to Plans 5 and 6," yet Task 1 implements *and tests* shell-execution authorization (`test_shell_execution_rejected_in_plan_chat_mode`, `test_shell_execution_in_agent_requires_fitness_gate`) and gates it on a `composite_fitness_gate_passed` precondition that Plan 8 owns. This is an internal contradiction and cross-plan double-ownership.

**Fix:** either drop `SHELL_EXECUTION` / `PATCH_WORKSPACE` from this plan (return the policy matrix to web-search / web-extract / local-read / validation, per the Plan 4 charter), or reconcile the Out-of-Scope wording and add a Source Anchor citing the exact HLD/LLD clause that defines the fitness-gate precondition. Right now no anchor grounds the "shell requires Agent mode + composite fitness gate" rule.

### M5. `ValueError` from `validate_trusted_gateway()` still escapes the dispatcher — repeat of PR #8 Finding 1 (Medium)

**Where:** Task 5 (client methods call `self._settings.validate_trusted_gateway()`) and Task 7 (dispatcher wiring).

`validate_trusted_gateway()` raises a plain `ValueError` (`config/gateway.py`), not a `GatewayError`. The new `search_web_evidence` / `extract_web_evidence` both call it, and the plan's Task 7 only adds `except ToolCallRejected` — there is still no `except ValueError` (or `GatewayError` subtype) in `dispatch()`. A dispatcher wired with a rogue-origin client would let that `ValueError` propagate uncaught, exactly as the prior PR #8 audit (Finding 1) already warned for `optimus.gateway.responses`. The recurring pattern suggests fixing it at the source.

**Fix:** make `validate_trusted_gateway()` raise a `GatewayError` subtype (so the existing `except GatewayError` catches it everywhere), or add `except ValueError` to `dispatch()`. Prefer the former for consistency across both the gateway and evidence methods.

---

## Low

### L1. Response parsers leak raw `ValidationError` on malformed results (Low)

`parse_web_search_response` calls `EvidenceSearchResult.model_validate(item)` uncaught; a malformed/`non-https` result `url` raises a bare pydantic `ValidationError` rather than the module's `GatewayResponseError`. Inconsistent with `_parse_gateway_usage`, which wraps. Test Strategy §§10–11 emphasize clean schema-failure typing. Wrap result/response validation in `GatewayResponseError`.

### L2. Provider-key clear-list drifts from `LOCAL_PROVIDER_KEY_NAMES` (Low)

The Task 8 integration test and Task 10, Step 4 enumerate provider keys manually and **omit `LANGCHAIN_API_KEY`**, which *is* in `config/gateway.py::LOCAL_PROVIDER_KEY_NAMES`. On a developer machine with `LANGCHAIN_API_KEY` set, `OptimusGatewaySettings.from_env()` inside the integration test raises `ProviderKeyViolation` and the test fails for an unrelated reason. Derive the clear-list from `LOCAL_PROVIDER_KEY_NAMES` instead of hardcoding a divergent copy.

### L3. `tools/__init__.py` is replaced wholesale, dropping existing exports (Low)

Tasks 1–2 give full-file contents for `src/optimus/tools/__init__.py` that export only the policy/registry surface, silently removing the current `shell_exec, shadow_apply, write_file` exports. No module imports those via the package namespace today (all importers use `optimus.tools.mutation_tools` directly, confirmed by grep), so there's no runtime break — but it's an unintended public-API reduction. Make the edit additive (extend `__all__`), not a replacement.

### L4. No trust marker on extracted web content (Low)

`AGENTS.md` and Test Strategy §11 require treating web-extract text as untrusted, and this plan's In-Scope claims it provides "tool-output trust signals." But `EvidenceExtractResponse.content` is a bare `str` with no accompanying trust/provenance flag. Add an explicit marker (e.g. `trust: Literal["untrusted"]` or a typed wrapper) so downstream selection/promotion code (Plan 11) cannot accidentally treat it as trusted. The integration fixture only asserts the *string* "must be treated as untrusted" — that is a comment, not an enforced signal.

### L5. Per-task `git commit` steps contradict the plan's own commit policy (Low)

Every task ends with `git add … && git commit …`, but the Execution Handoff and `AGENTS.md` both say do not commit without explicit user approval. As written, an executing agent would auto-commit ~10 times against a standing "don't commit" rule. Reconcile: either gate commits behind approval or make the steps stage-only with a single approval checkpoint.

### L6. Ledger timestamp and search-depth are unvalidated free-form strings (Low)

`EvidenceLedgerEntry.queried_at` is a plain `str` (via `_utc_now()`), and `EvidenceRequest.search_depth` is an unconstrained `str`. For an audit ledger and a gateway-bound parameter, a validated `datetime` and a `Literal["basic","advanced"]` would fail closed on bad input rather than forwarding it.

### L7. "Atomic" cap is correct but untested under concurrency (Low)

The lock discipline is right — the pure policy check runs outside the lock, and reject/cap/append run inside it — so `authorize_and_record_call` is genuinely atomic. But `threading` is named in the tech stack and the plan claims atomicity, yet no test spins concurrent threads against a shared registry. Add one stress test (N threads, cap=K, assert exactly K recorded) to make the safety-critical claim executable, per `AGENTS.md` ("every major design claim needs an executable check").

---

## Nits

- **N1.** Self-Review says the cap test proves "the 11th call on a cap-of-10 run is rejected," but the actual test uses cap-2 / 3rd-call. Equivalent behavior; align the prose.
- **N2.** `trigger_pairs` is rebuilt as a set literal on every `_authorize_web_search` call; hoist to a module constant.
- **N3.** Task 7's appended dispatcher test re-imports `GatewayUsage`, already imported at the top of the existing `test_dispatcher.py` (harmless duplicate).
- **N4.** `HttpUrl` normalization: provenance equality relies on `str(HttpUrl(...))` being stable across search-result storage and extract lookup. It is consistent within the system for path URLs, but host-root URLs gain a trailing slash — worth one explicit test asserting round-trip equality so a future pydantic bump can't silently break provenance matching.

---

## Out of scope (confirmed, not gaps)

Cross-checked against `AGENTS.md`'s global logging/persistence/retry requirements; the plan's Out-of-Scope correctly defers these, consistent with the Plan 3 precedent:

- Durable `ProviderUsage` persistence, Redis writes, trace export, full cost reconciliation → Plan 7.
- Retry/backoff, transient/permanent classification, release-gate runner → Plan 8.
- Deny-before-allow permission engine, network egress validator, MCP trust, prompt-injection fixtures, CI parity → Plans 5/6 (but see M4 re: shell authorization leaking in).
- Context selection, freshness/promotion gates → Plan 11.
- Staging-gateway E2E that would violate server-side policy.

## What worked well (carry forward)

- **Correct atomic-cap locking:** pure policy computed outside the lock; reject + cap-check + append inside a single critical section; no record on rejection (`test_authorize_and_record_call_rejects_without_recording`).
- **Verbatim usage reuse:** `EvidenceLedgerEntry.from_gateway_usage` copies gateway fields directly with no post-hoc estimation, honoring the "parse cost from gateway, don't estimate" rule; no second usage model introduced.
- **Fail-closed provenance:** web extract requires membership in the run's approved search-result set **and** a trusted https origin, and the trusted set is derived per request — a genuine defense-in-depth local check ahead of the server-side gateway policy.
- **Strict TDD framing:** every production change has an explicit failing-test step with the expected error message, then minimal implementation, then focused verification.
- **One-key posture preserved and asserted:** local path uses only `OPTIMUS_*`; the mocked integration test asserts no provider key resolves locally and that both calls carry the Optimus bearer token.

## Verdict

**Request changes (plan amendment) before execution.** B1 is blocking — it must be resolved by re-layering so `evidence` depends on `gateway` and never the reverse, or the plan cannot execute past Task 4/5 as written. Fold in M1–M5 (coverage scope, ledger `run_id`, dead `credits_used`, shell-scope reconciliation, dispatcher `ValueError` mapping) in the same amendment. L1–L7 and the nits are cheap hardening. Net: the design intent and TDD craft are sound; the layering direction and a handful of grounding/scope details need correction first.

---

## Re-review addendum (amended plan, 2026-07-03)

Re-verified the amended plan line-by-line against the same modules. Resolution summary:

| Finding | Status | How it was fixed |
| --- | --- | --- |
| **B1** circular import / layering | Resolved | Payload builders + parsers moved to new `src/optimus/evidence/gateway_io.py`; `gateway/models.py` is no longer modified; `GatewayClient.post_tool_json(path, payload) -> dict` is generic and imports no evidence type; plan states the one-way rule twice and `post_tool_json` guards `path.startswith("/v1/tools/")`. Dependency graph verified acyclic. |
| **M1** coverage scope | Resolved | Task 10 Step 1 now includes `tests/unit/gateway/test_models.py` and `test_client.py`, so `build_chat_completions_payload`/`_extract_text_from_output` are exercised under the focused gate. |
| **M2** ledger `run_id` | Resolved | `run_id` + optional `session_id` added to `EvidenceRequest`, `EvidenceExtractRequest`, `EvidenceLedgerEntry`, and threaded through `from_gateway_usage()` in both `search()` and `extract()`. |
| **M3** dead `credits_used` | Resolved | Responses carry `credits_used`; parsers read it from the body; `from_gateway_usage()` takes and stores it; `total_credits()` now reconciles real traffic (tests assert 2 / 1 / 7). |
| **M4** shell/patch scope creep | Resolved | `ToolClass` reduced to `LOCAL_REPO_READ`, `VALIDATION_GATE`, `WEB_SEARCH`, `WEB_EXTRACT`; `composite_fitness_gate_passed` and the shell tests removed; In/Out-of-Scope and Self-Review reconciled. |
| **M5** dispatcher `ValueError` | Resolved | `except ValueError -> INTERNAL_ERROR` added to `dispatch()`, with `test_dispatcher_maps_gateway_trust_value_error_to_json_rpc_error` (−32603). |
| **L1** parser error typing | Resolved | `parse_web_search_response` wraps result validation in `GatewayResponseError`; covered by a malformed-URL test. |
| **L2** provider-key drift | Resolved | Integration test and Task 10 Step 4 now import and iterate `LOCAL_PROVIDER_KEY_NAMES` instead of a hand-copied list. |
| **L3** `tools/__init__.py` overwrite | Resolved | Edit is additive; `shell_exec`/`shadow_apply`/`write_file` retained alongside the new policy/registry exports. |
| **L4** trust marker | Resolved | `EvidenceExtractResponse.trust: Literal["untrusted"]`; surfaced in the ACP extract payload and asserted end-to-end. |
| **L5** commit policy | Resolved | New "Commit Policy for Execution" section makes every per-task commit approval-gated. |
| **L6** timestamp / search_depth | Resolved | `queried_at` is a `datetime`; `search_depth` is `Literal["basic","advanced"]`. |
| **L7** concurrency test | Added — but see R1 | Real `ThreadPoolExecutor` stress test added (50 attempts, cap 10). Contains a contradictory assertion; see below. |
| **N4** HttpUrl round-trip | Resolved | `test_http_url_round_trip_preserves_provenance_string_for_path_urls` added. |

### New / residual items

**R1. The new concurrency test will fail as written (Medium — required fix before Task 2).**
`tests/unit/tools/test_tool_registry.py::test_max_calls_per_run_is_atomic_under_concurrent_calls` asserts both:

```python
assert registry.call_count("run-1") == 10
assert registry.records("run-1") == ()
```

These contradict each other. After 10 successful records, `records("run-1")` returns a 10-tuple (`tuple(self._records_by_run.get(run_id, ()))`), so `== ()` is false and the assertion raises — yet Task 2, Step 4 says "Expected: PASS." This is a copy/paste remnant of the old rejection test's `records == ()` line. **Fix:** replace it with a check that actually strengthens the atomicity claim, e.g.

```python
records = registry.records("run-1")
assert len(records) == 10
assert sorted(r.sequence_number for r in records) == list(range(1, 11))  # gapless, no dupes
```

**R2. `from_gateway_usage(..., queried_at: str)` annotation is now inaccurate (Low).** The field is `datetime` and `acquisition.py` passes `_utc_now()` (a `datetime`); the tests pass an ISO string. Both coerce fine, but the parameter should be typed `str | datetime` (or `datetime`) to stop lying to readers and type-checkers.

**R3. Dispatcher error-branch coverage gaps recur (Low — repeat of original PR #8 Finding 4).** No dispatcher test drives the `evidence_service is None` "not configured" branches or the `except ToolCallRejected -> INVALID_REQUEST` branch. Both are meaningful parts of the ACP error contract (policy rejection over the wire). Add a not-configured test and a rejection test (a `FakeEvidenceService` whose `search` raises `ToolCallRejected`) so the −32600 policy-rejection contract is executable, not just implied.

**R4. Credit totals aren't surfaced over ACP (Low / optional).** The ledger now tracks credits, but `_evidence_search_payload` / `_evidence_extract_payload` expose only `ledger_total_cost_usd`. Consider adding `ledger_total_credits` for parity now that the field is live.

### Updated verdict

**Approve, with R1 as the one required fix before running Task 2.** B1 and all Medium/Low findings from the original review are correctly resolved, and the re-layering is clean rather than a patch-over. R2–R4 are optional polish. TDD craft, dependency direction, provenance, and one-key posture are all in good shape.
