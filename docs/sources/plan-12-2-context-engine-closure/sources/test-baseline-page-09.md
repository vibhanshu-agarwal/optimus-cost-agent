# 7A. Deterministic Search Compatibility Gate

The deterministic search compatibility gate uses one cheap Flash/Haiku-class model and one default
engine request shape. The approved 2026-07-27 baseline is:

- max_tokens=16;
- 3 annotations on the minimal-output probe;
- 3/3 include-domain results allowed and 0 violations;
- 0/3 excluded-domain results forbidden and 0 violations;
- 9/9 annotations with HTTPS URL, title, and non-empty content;
- mean latency 7,068.7 ms/search;
- provider-reported mean cost $0.0051584/search;
- direct extract 270,008 bytes -> 60,077 text characters in 589.5 ms.

These are evidence values, not permanent performance thresholds. Each run reports fresh values and
fails on missing search execution, annotations, domain enforcement, or provider usage/cost. Engine
and model comparison matrices are out of scope. A verified-or-fail server-tool successor requires a
separate live test proving max_uses: 1, exactly one search, search-use accounting, valid
annotations, domain enforcement, and fail-closed behavior when execution evidence is absent.

# 9. Error, Retry, and Failure Injection Tests

LLD reference: §6 Resilient Provider Calling Layer, §4A Failure and Retry Lifecycle. These tests
prove that transient failures are retried with backoff and permanent failures abort cleanly without
side effects.

## Unit Tests - RetryPolicy

- Current RetryPolicy: initial call plus up to three retries; pin third-attempt success and escalation after the fourth attempt. Under enabled Gateway policy, pin a maximum of two physical attempts only after not-sent/429 with identical payload/route and host non-retryable propagation.
- HTTP 429 under enforced policy: at most one identical payload resend on the same route; all physical attempts count.
- PermanentGatewayError: ABORT_WITH_REPORT returned immediately; no retry; failure report emitted.
- PolicyViolationError: ABORT_WITH_REPORT; escalation signal emitted.
- Independent evaluation budget exhaustion stops that evaluation and preserves receipts. A successful product response above the former $0.05 is delivered; no product dollar stop remains after migration.
- Finite configured attempts exhausted: report the true failure and all attempt identities; no retry-until-pass.

## Integration Tests - Failure Injection

- The legacy host permits an initial attempt plus at most three retries. The inactive-policy Gateway separately permits at most three upstream attempts, including its legacy transient timeout/URL/5xx retries. Once enforcement is active, the Gateway permits one primary attempt and at most one identical-payload resend on the same route, only after a definitely NOT_SENT result (including a proven pre-connection timeout) or rejected HTTP 429. A timeout after connection, uncertain delivery, 5xx or unknown accounting is not resent. The host honors non-retryable classifications so it cannot multiply attempts. No alternative-model recovery is added. Each physical attempt retains its own receipt. Tests cover third-attempt success and escalation after the fourth attempt in the legacy policy, and separately the enabled Gateway maximum of two physical attempts with host non-retryable propagation.
- Fitness failures use configured planning/time/repeated-failure boundaries; targeted replan context is supplied only while those bounds permit continuation. Pin the actual stop and effect evidence.
- Evaluation cap exhaustion stops only its approved evaluation. Product count/time/cancellation/permission failures preserve truthful telemetry and effect state; do not relabel them as dollar exhaustion.

# 10. Schema Validation Tests

LLD reference: §1 ACP Protocol Framing, §9 Tool Registry. These tests prove malformed inputs are
rejected before processing and Pydantic v2 validators enforce invariants at the boundary.

## Unit Tests - ACP Framing

- Content-Length: 0 with non-empty body: rejected with -32700 Parse Error.
- Content-Length > MAX_HEADER_SIZE: rejected with -32600 Invalid Request.
- Non-numeric Content-Length: rejected with -32700 Parse Error.
- Body larger than declared Content-Length: truncated; remaining bytes are not leaked into the
  next message.
- JSON-RPC body missing method: rejected with -32600 Invalid Request.
- JSON-RPC body with unknown method: rejected with -32601 Method Not Found.

## Unit Tests - Pydantic Models

- EvidenceRequest with an empty query string: ValidationError before any Gateway call.
- EvidenceExtractRequest with max_chars_per_source=0: ValidationError.
- OptimusGatewaySettings with empty optimus_api_key: ValidationError.
- GatewayUsage with negative billing_units: ValidationError.
- GatewayUsage with negative cost_usd: ValidationError.