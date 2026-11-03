# ADR-036: A launch reuses a local Gateway only when it proves this launch's configuration

**Status:** Proposed. The operator approved Plan 12.10, including its decision D2, at its exact hash on 2026-11-03
(verbatim below). Codex reviews the mechanism at the plan's first checkpoint; operator acceptance of this record is
separate. Delivered by [#465](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/465) under Plan 12.10
([#469](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/469)). Drafted by Claude.

**Relationship:** adds one authenticated Gateway route beside those of ADR-032 and ADR-034 and keeps their boundary: the
host holds only its Gateway URL and key. Unchanged: alerts, not limits ([ADR-005](ADR-005-cost-alerts-not-limits.md));
models are configuration ([ADR-025](ADR-025-models-are-configuration-per-model-admission.md)). This record covers no memory
index decision; Plan 12.10's D3 and D4 get their own record when those mechanisms land.

## Context

`ensure_local_gateway` treated a reachable port as "this launch's Gateway". On 2026-11-02, during Plan 12.9's zero-paid
Zed proof, another configured entry's Gateway held `127.0.0.1:8765` with a real upstream. The launch approved for a stub
found the port reachable and attached, and its prompts went to OpenRouter: 26 requests, USD 0.01436675. Nothing warned
the operator. The approval bound an upstream the running Gateway was not using.

## The operator's decision (2026-11-03, verbatim, Claude's Plan 12.10 chat)

"Approve this hash", for Plan 12.10 at SHA-256 `f136397fe605d51bd6dfee1ab4ed8705e7c3a45d05eb52b6c5cf569a7d02adb1`, whose D2
recommends an authenticated compatibility identity and request binding. #465, as filed with the operator's approval on
2026-11-02, requires a confirmation that "must keep the credential boundary and must not make a paid call to find out", and
a real Zed proof with two configured entries.

## Options considered

| Option | Outcome | Reason |
|---|---|---|
| Authenticated identity route and request binding | Chosen | Two launches with the same configuration keep sharing a Gateway, including across workspaces. Nothing changes in ordinary configuration. |
| A port per launch | Rejected | Isolation is simple, but it loses reuse, starts a Gateway per Zed project, and changes ordinary configuration: `OPTIMUS_GATEWAY_URL` is approved environment. |
| Silently starting a second Gateway on a free port | Rejected | The running port would no longer be the approved one, and the operator would not know. |
| Comparing the workspace as well | Rejected | Two projects on one Gateway are ordinary use, and the workspace authorizes a host, not upstream behavior. No harm from sharing was found. |

## Decision

The mechanism below is an agent recommendation that the operator approved through the plan; the field list and the limits
are agent-selected.

- **Identity.** `optimus_security.gateway_identity` composes one keyed fingerprint per field: upstream URL, provider,
  upstream credential, Gateway key, model registry, composition (ordinary, Auto or a test profile), Stage C envelope,
  accounting, and tool configuration. The Gateway composes it at startup from the values just verified against its signed
  manifest. The host composes it from what it would start.
- **Excluded, with the reason:** workspace, branch, security snapshot, session, nonce and expiry authorize a host. The OTLP
  endpoint changes where this Gateway's traces go, not what a request calls or costs.
- **Route.** `POST /v1/local/identity`, bearer-authenticated before any body byte is read, with a fresh nonce. The reply
  carries only fingerprints, and a proof over the nonce under a key derived from the approval store's key. An older
  Gateway, another program, a wrong key, a malformed or late reply, or a replay cannot pass.
- **Request binding.** Every host request names the expected digest in `X-Optimus-Gateway-Identity`. A Gateway serving
  anything else answers 409 before dispatch, so a Gateway that took the port after the check gets no upstream call, ledger
  write or budget from it. Capture delivery starts only after the confirmation.
- **Refusal.** The launch stays up as a diagnostic-only ACP host that holds no Gateway client, Redis, model or tool path. The
  Agent Panel opens, and each prompt shows the reason and remedy and ends with `end_turn`, because Zed can show a `refusal`
  stop reason as a content-policy banner in place of the text. The listener is never terminated. `--check-config --strict`
  prints the reason and exits 2.
- **`optimus-trust run-gateway`** now serves the accounting a launch under the same approval would, so an agent with
  `--no-auto-start` can still reuse it. Its Gateway gains accounting when one is approved.

## Consequences and residuals

- **Scope is authenticated by key, not by caller.** All hosts on a Gateway share one key; the identity says what a Gateway
  serves, not who is asking.
- **A host with only a URL and a key** has no approved upstream to compare. It still requires a current Gateway that answers
  its key, and sends no binding.
- **A request with no binding is not refused,** because its caller has no expectation to protect. Every production host
  request carries one when the launch names a local upstream.
- **An older Gateway taking the port after the check** ignores the header. That needs an older install running beside a new
  one within one session; it is not closed here.
- **Mixed configurations on one port now refuse.** A person running differently configured entries gives each its own
  `OPTIMUS_GATEWAY_URL` port and approves it, as the refusal says.
- **Sibling attaches.** `ensure_local_redis` and `ensure_local_phoenix` have the same reachability shape, without the upstream
  billing gap. They are named residuals on #469 and do not hold #465 open.

## Evidence

`reports/plan12-memory-m1/gateway-attach.json` binds the native Gateway HTTP tests, the two-entry and two-workspace Zed
proof, and the zero-provider-call record.
