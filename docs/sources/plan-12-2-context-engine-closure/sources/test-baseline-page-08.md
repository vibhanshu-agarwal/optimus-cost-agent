# 8B. Observability test strategy
| Tool | Category | Purpose | Counts toward code coverage |
|---|---|---|---|
| coverage.py / pytest-cov | Code coverage | Production-code execution | Yes |
| DeepEval / Ragas | LLM quality | Correctness and groundedness | No |
| PyRIT | Adversarial | Injection and tool-control safety | No |
| OpenTelemetry / OTLP | Trace observability | Vendor-neutral span contract/export | No |

Run the real Phoenix evidence tier and assert required span attributes and request correlation, parent/child relationships, secret redaction, batching/retry outcome, validation/policy disposition and final failure/success disposition. A missing real collector/exporter makes that claim UNRUN.

Phoenix is the documented default, not an API dependency. No LangSmith dependency, endpoint, credential or amortized per-request charge exists. These observability claims are separate from §8A's source coverage gates.
