# 11A. OpenTelemetry trace observability

Phase 1 uses OpenTelemetry spans and OTLP as the vendor-neutral trace contract across planning, Gateway calls, tool invocation, validation, retries and final response generation. The local agent sends authenticated structured trace ingress to the Gateway; it validates/redacts fields, maps them to OTel spans/events and exports OTLP. Arize Phoenix is the documented local default. Any OTLP-compatible backend may replace it without changing Optimus instrumentation; Langfuse may be considered for team-scale deployments.

Trace export records operational telemetry, not an invented billable provider request. No allocated/amortized observability cost_usd is added to the usage ledger. Infrastructure cost is an operator concern outside per-request accounting.

Required attributes retain run, session, request, Gateway/provider request, execution mode, generation scope, model/provider, cache, cost_usd, billing units, policy/tool, validation, retry and failure attribution. Secrets are redacted before export.

# 12. Testing and quality gates
| Concern | Tooling | Role in gates |
|---|---|---|
| Code coverage | coverage.py, pytest-cov | Target: Optimus product group >=80%, context_engine >=80% and optimus_model_policy >=80% separately; all-source aggregate informational. Test Strategy v1.8 §8A governs. At cf9bb9d CI and the final CP4 gate enforce these floors; the interim hook remains Optimus-only. Safety-critical modules must not regress. |
| Agent quality | DeepEval, Ragas | Task quality, correctness and groundedness |
| Adversarial/red-team | PyRIT | Prompt injection, tool-control and trust-boundary validation |
| Trace observability | OpenTelemetry + OTLP; Phoenix default | Debugging and regression analysis; not code coverage |

OTel/OTLP trace validation is tracked separately from production-code coverage. LangSmith is not part of the architecture or dependency set.
