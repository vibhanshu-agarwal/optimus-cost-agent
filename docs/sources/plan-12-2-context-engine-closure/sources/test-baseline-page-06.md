# 7.1 Integration, E2E, and egress gates

- Direct policy-violation tests target the real loopback Gateway.
- Aggregator routing/fallback evidence records the returned provider and model.
- The agent and ACP child may egress only to the loopback Gateway.
- The Gateway may egress only to the configured aggregator, approved package/OSV hosts, approved
  extract targets, Redis, and configured OTLP endpoint.
- Agent and Gateway environments are scanned separately.
- The agent has no upstream key; the Gateway has the approved aggregator key by design.
- After replacement acceptance, the Gateway has no direct-provider, Tavily, or LangSmith key.
- Crafted tool output cannot cause direct agent egress.
- WSL2 evidence proves both processes share one network namespace.

## Failure behavior

Malformed or missing successful provider usage/cost remains invalid; the stage records explicit unknown cost and preserves known subtotals without latching the product session closed. Permanent authentication, policy, schema,
and validation failures do not retry. Transient faults have a bounded retry budget and record every
attempt.

For enforced model requests, the following bounded retry policy supersedes generic transient-retry examples: The legacy host permits an initial attempt plus at most three retries. The inactive-policy Gateway separately permits at most three upstream attempts, including its legacy transient timeout/URL/5xx retries. Once enforcement is active, the Gateway permits one primary attempt and at most one identical-payload resend on the same route, only after a definitely NOT_SENT result (including a proven pre-connection timeout) or rejected HTTP 429. A timeout after connection, uncertain delivery, 5xx or unknown accounting is not resent. The host honors non-retryable classifications so it cannot multiply attempts. No alternative-model recovery is added. Each physical attempt retains its own receipt.
