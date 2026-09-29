# Plan 11.9: P11.7-FU-1 Configurable Gateway Request Timeout Design Specification

**Status:** Draft for operator/reviewer approval. This document authorizes no source or test
implementation, release claim, or change to the fail-closed planning policy.

**Stable follow-up:** `P11.7-FU-1` — Configurable Gateway request timeout for debug/investigation
workflows.

**Plan number:** 11.9, the next unused Plan 11 single-decimal slot at pickup.

**Baseline:** `origin/main` at `cb820684cfea1b68f3b7e9e5341508977e77aa58`.

**Branch:** `agent/codex/plan-11-9-gateway-timeout`, created from the baseline in the sibling
worktree `optimus-cost-agent-wt-plan-11-9`.

**Scope posture:** This is a small, CLI-first design for the deferred timeout override. The
implementation plan deliberately leaves the inherited environment-policy registry unchanged by
deferring an environment-variable override; the user-visible override is explicit, per-process,
and discoverable through `optimus-agent --help`.

## 1. Authoritative source and current-state evidence

The consolidated follow-up pool is the acceptance authority for this pickup:
`docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`, section
`P11.7-FU-1`. The current baseline confirms the pool's substance:

- `src/optimus/gateway/client.py:100` already exposes `timeout_seconds: float = 30.0` on
  `GatewayClient.__init__`.
- `src/optimus/acp/bootstrap.py:73` and `:130` construct `GatewayClient(settings=settings)`
  without an override.
- `src/optimus/acp/__main__.py:50-52` establishes the public `argparse` flag pattern.
- `pyproject.toml:22-23` maps the `optimus-agent` entry point to
  `optimus.acp.__main__:main`.
- The fail-closed unknown-cost behavior remains in `src/optimus/agent/planning_loop.py:907-912`
  and `:953-956`; it must not change in this slice.

The HLD, LLD, Guardrails, and Test Strategy do not define a competing client timeout interface.
If implementation-time inspection finds a conflict with an authoritative document, implementation
stops for review rather than widening this plan.

## 2. Goal

Allow an operator to raise the Gateway request timeout for one `optimus-agent` process using a
documented `--gateway-timeout-seconds SECONDS` flag, while preserving the existing 30-second
default and all fail-closed cost/retry behavior when the flag is absent.

## 3. Problem statement

The Gateway client already has the correct injection seam, but both ACP bootstrap paths discard it
by constructing the client with the default. A slow model response can therefore reach the
transport timeout and surface as `PLANNING_GATEWAY_COST_UNKNOWN`. That stop is intentional: the
planning loop must not retry a request when the Gateway cannot report whether the first attempt was
billable. The missing capability is operator control over how long the first request is allowed to
finish, not a change to retry or cost policy.

## 4. Authoritative acceptance criteria

The following is copied from the pool entry and remains authoritative:

- A documented override raises `GatewayClient`'s effective `timeout_seconds` for a single
  invocation/session.
- Default behavior (30s timeout, fail-closed/no-retry on unknown cost) is unchanged when the
  override is not set.
- The override is discoverable (e.g. `optimus-agent --help`), not just a source-level constant.

**Evidence anchors:** `src/optimus/gateway/client.py:96`; `src/optimus/acp/bootstrap.py:72,129`;
`src/optimus/agent/planning_loop.py:907-912,953-956`; live Task 0 Case 1 Zed captures 2026-07-30
(two consecutive `PLANNING_GATEWAY_COST_UNKNOWN` timeouts on `z-ai/glm-5.2`, ~30s each, vs. a
prior successful ~16s response on the identical fixture/task, same worktree).

## 5. Design choices

### 5.1 Recommended: CLI-only, explicit per-process override

Add `--gateway-timeout-seconds SECONDS` to `optimus-agent`. `argparse` parses and rejects values
that are not positive, finite numbers. `main()` forwards a non-`None` value to
`build_configured_server()`, which forwards it to both GatewayClient construction sites:

```text
optimus-agent --gateway-timeout-seconds 90
        |
        v
parse_args -> optional float
        |
        v
build_configured_server(..., gateway_timeout_seconds=90.0)
        |
        +--> build_agent_runner_for_harness -> AgentRunner GatewayClient(timeout_seconds=90.0)
        |
        +--> JsonRpcDispatcher GatewayClient(timeout_seconds=90.0)
```

When the flag is absent, the bootstrap preserves the existing constructor call shape and the
client continues to use its 30-second default. The existing `GatewayRequest.timeout_seconds`
field and transport behavior are reused; no retry, budget, cost, or response parsing code changes.

Validation is positive and finite (`> 0`, not `NaN`, not positive/negative infinity). The plan does
not invent an upper bound that is absent from the follow-up acceptance criteria. A future resource
governance plan may add an approved ceiling if operators need one.

### 5.2 Rejected for this pickup: inherited environment variable

An `OPTIMUS_GATEWAY_TIMEOUT_SECONDS` variable would work for non-CLI harnesses, but every new
`OPTIMUS_*` literal is subject to the launch-policy registry and fail-closed source audit. Adding
the variable would require deciding its policy tier, parser, approval semantics, display behavior,
and inherited-environment documentation. That is disproportionate to this debug-only request and
could accidentally turn a timeout change into a launch-approval contract. The implementation plan
therefore defers this interface explicitly.

### 5.3 Rejected: environment-only configuration

An environment-only setting would not satisfy the strongest discoverability requirement without
additional help/documentation plumbing, and it would have the same launch-policy blast radius as
5.2. It is not part of Plan 11.9.

## 6. Components and boundaries

### CLI boundary

`src/optimus/acp/__main__.py` owns user-facing syntax and `argparse` diagnostics. The flag is
optional, has a `SECONDS` metavar, and appears in `--help`. Invalid values fail during argument
parsing before startup side effects.

### Bootstrap boundary

`src/optimus/acp/bootstrap.py` adds an optional `gateway_timeout_seconds` parameter to
`build_agent_runner_for_harness()` and `build_configured_server()`. A small shared construction
helper may preserve the current no-override call shape while passing the explicit keyword only when
the value is set. Both clients in a configured ACP server receive the same effective value.

### Client boundary

`src/optimus/gateway/client.py` remains the owner of the existing timeout injection seam and should
centralize positive-finite validation if implementation needs to protect direct Python callers.
The default remains exactly `30.0`; `GatewayRequest` and `UrllibGatewayTransport` retain their
current semantics.

### Documentation boundary

`README.md` adds the flag to the operator flags table and gives one debug invocation. The wording
must state that the override is process-scoped, defaults to 30 seconds when absent, and does not
enable retry or alter unknown-cost fail-closed behavior.

## 7. Security and failure behavior

- The flag cannot change `OPTIMUS_GATEWAY_URL`, credentials, provider routing, model selection,
  tool authorization, or workspace policy.
- It is not inserted into the inherited environment and does not change launch-policy registry
  membership, security snapshots, approval records, or secret handling.
- Invalid values fail closed at CLI parsing (or typed bootstrap/client validation for direct
  callers); they never silently fall back to 30 seconds.
- A transport timeout still produces the same Gateway error and unknown-cost state. The planning
  loop still stops without retry when cost is unknown.
- No timeout value, credential, prompt, response, or new telemetry field is required by this
  feature. Existing request/telemetry logging remains unchanged.

## 8. Test and evidence strategy

Unit coverage must prove:

1. The existing client default remains 30 seconds and an explicit value reaches the transport.
2. Invalid explicit values are rejected.
3. Both bootstrap-created clients receive the same explicit override.
4. The CLI accepts the flag, rejects invalid values, forwards the value, and lists it in help.
5. The absent-flag path preserves the old bootstrap call shape and does not change planning-loop
   fail-closed behavior.

The implementation plan maps these claims to `tests/unit/gateway/test_client.py`,
`tests/unit/acp/test_bootstrap.py`, and `tests/unit/acp/test_main_wiring.py`. Focused unit tests,
Ruff, the full test suite, production coverage, and the documentation freshness audit are required
before the implementation branch can be considered complete. This design PR itself changes no
production code.

## 9. Explicit non-goals

- Do not modify `PLANNING_GATEWAY_COST_UNKNOWN` or any no-retry/fail-closed decision.
- Do not add retry, cost estimation, budget changes, asynchronous transport, or provider keys.
- Do not add an inherited environment variable in Plan 11.9.
- Do not change the Gateway API, response schemas, MCP routes, ACP protocol behavior, or local
  Gateway process startup.
- Do not fold this work into frozen Plan 11.7 or any other in-flight plan.

## 10. Design approval boundary

This design is intentionally narrow and ready for operator/reviewer review. After approval, the
implementation plan may be executed in the same fresh branch with TDD. The Plan 11.9 PR should
remain a draft until the operator accepts the design and the implementation branch passes its
required gates.
