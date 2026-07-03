# PR #8 Review — Plan Gap Audit

**PR:** [vibhanshu-agarwal/optimus-cost-agent#8](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/8) — Add gateway-only configuration and Optimus Gateway client (Plan 3)
**Branch:** `agent/cursor/gateway-only-configuration` → `main`
**Plan:** `docs/superpowers/plans/2026-07-02-gateway-only-configuration-gateway-client.md` (Tasks 1–9)
**Reviewed:** 2026-07-03
**Method:** Cloned the repo, diffed `main...pr8-branch` directly (13 commits, +1397/-50, 17 files), read every changed line in `src/` and `tests/`, then diffed the plan's prescribed code blocks (Tasks 1–9) against the merged implementation.

## Headline finding

The implementation is a faithful, near line-for-line execution of the plan. Every dispatcher, settings, model, client, and test code block in the PR matches what the plan prescribed, including exact exception-handling and validation logic. The only additions beyond the plan are inline comments (transport-seam note in `client.py`, origin-tuple note in `config/gateway.py`), which trace to a dedicated "Document gateway transport seams..." commit.

**Conclusion: every finding below is a gap in the plan's design, not a deviation introduced during implementation.** The implementing agent executed the approved plan correctly. Fixes belong in a plan amendment or follow-up task, not a silent patch to the merged code.

---

## Findings

### 1. `ValueError` from origin revalidation can escape the JSON-RPC dispatcher (Medium)

**Where:** Plan Task 6, Step 3 (dispatcher exception mapping) → implemented at `src/optimus/acp/dispatcher.py:87, 109-118`.

`GatewayClient.create_response()` calls `settings.validate_trusted_gateway()` as a defense-in-depth revalidation before every network call. That method raises a plain `ValueError` (`src/optimus/config/gateway.py`), not a `GatewayError`. The plan's Task 6 Step 3 only adds:

```python
except GatewayError as exc:
    return error_response(...)
```

There is no `except ValueError` (or equivalent) anywhere in `dispatch()`. If this revalidation ever trips — origin-trust config drift, a future feature that reconstructs settings at runtime, or a caller that builds `GatewayClient` from hand-built settings instead of `from_env()` — the exception propagates out of `dispatch()` uncaught instead of returning a structured JSON-RPC error.

Currently unreachable via the wired `from_env()` path (settings are frozen and validated once at bootstrap), so this is not an active bug, but the plan should either:
- have `validate_trusted_gateway()` raise a `GatewayError` subtype for consistency, or
- have the dispatcher catch `ValueError` alongside `GatewayError`.

### 2. "Gateway client not configured" maps to `METHOD_NOT_FOUND` (Low)

**Where:** Plan Task 6, Step 3 → implemented at `src/optimus/acp/dispatcher.py:65-69`.

The plan specifies `JsonRpcError(code=METHOD_NOT_FOUND, message="gateway client not configured")` verbatim. This reads as "this method doesn't exist" to a JSON-RPC caller rather than "this method exists but isn't wired up in this deployment." A distinct code (or reusing `INTERNAL_ERROR`/a new configuration-error code) would be clearer. Minor, but worth a plan-level decision since it's part of the public JSON-RPC error contract.

### 3. No non-empty check on `model` before forwarding to the gateway (Low)

**Where:** Plan Task 6, Step 3 → implemented at `src/optimus/acp/dispatcher.py:73`.

Validation is `isinstance(params.get("model"), str)`, so an empty string `""` passes through to `create_response()` and reaches the gateway. Plan doesn't call for a `min_length`/truthiness check here (compare: `optimus_api_key` does get `Field(min_length=1)` in the settings model). Likely fine since the gateway would reject it, but inconsistent with the fail-closed posture used elsewhere in the same plan.

### 4. Two dispatcher branches have no test coverage (Low)

**Where:** Plan Task 6, Step 1 (test list) → implemented at `tests/unit/acp/test_dispatcher.py`.

The plan's Task 6 Step 1 specifies exactly three new dispatcher tests: routing to the gateway client, Plan/Chat-mode allowance, and rejection of the `messages` shape. It does not include:
- a test for `self._gateway_client is None` (the `METHOD_NOT_FOUND` "not configured" branch), or
- a test for `metadata` present but not a dict (the second `INVALID_REQUEST` branch).

Both branches exist in the implemented code but are currently untested because the plan never asked for a failing test to drive them (this codebase follows strict TDD per `AGENTS.md`, so no plan-specified test meant no implementation-driven coverage).

### 5. Settings validation is opt-in rather than automatic (Low / documentation)

**Where:** Plan Task 2 (initial model) + Task 3 (provider-key policy) → implemented at `src/optimus/config/gateway.py:295-356`.

`validate_trusted_gateway()` and `validate_no_local_provider_keys()` are ordinary methods, not enforced by a `model_validator` at construction time — only `OptimusGatewaySettings.from_env()` chains both explicitly. The plan's `model_validator(mode="after")` (`validate_production_constraints`) only enforces the production-mode/`extra_trusted_origins`/`provider_key_policy` combination, not origin trust or provider-key presence.

Practical impact is low: `GatewayClient.create_response()` re-validates trust before every real network call, so the actual network path is protected. But any code that constructs `OptimusGatewaySettings(...)` directly (as most of the test suite does) gets an object that hasn't verified either invariant until those methods are called explicitly. Worth a docstring/comment in the plan or the class itself clarifying that construction is intentionally decoupled from these checks.

---

## Out of scope (confirmed, not gaps)

Cross-checked against AGENTS.md's global logging/persistence/retry requirements, which could otherwise look like omissions in this PR. The plan's own "Out of Scope" section explicitly defers these to later roadmap plans, so their absence here is expected:

- ProviderUsage persistence, Redis writes, EvidenceLedger reconciliation, observability export → Plan 7.
- Retry/backoff, transient/permanent failure classification, composite release gates → Plan 8.
- Staging gateway E2E, provider failover, cache pricing, server-side policy revalidation.
- Network egress instrumentation, secret scanning, tenant-profile signature verification.
- Environment-driven opt-in to `ProviderKeyPolicy.IGNORE` (intentionally not read from env in this slice).

## What worked well (carry forward into future plans)

- Decimal-safe cost parsing (`json.loads(parse_float=Decimal)`) avoids float rounding on `cost_usd` — directly tested.
- Layered secret masking: `SecretStr` on the settings model, a custom `GatewayRequest.__repr__` that redacts `Authorization`, and `safe_model_dump()` — all tested, and the raw gateway body never leaks into the JSON-RPC response.
- Fail-closed design: untrusted origins rejected before any network call; malformed/missing `gateway_usage` raises a typed error; production mode locks out `extra_trusted_origins`/`ProviderKeyPolicy.IGNORE` via a model validator.
- Clean transport seam (`GatewayTransport` Protocol + injectable fake) keeps unit tests network-free while still giving the stdlib `UrllibGatewayTransport` direct coverage.
- Explicit rejection of mixed Responses/Chat-Completions shapes (`"messages" in params`) prevents callers from hitting the wrong endpoint contract.

## Verdict

PR #8: **Approve**, no blocking issues. Findings 1–5 above are candidate inputs for a Plan 3 addendum or a small follow-up plan — not rework items for this PR.
