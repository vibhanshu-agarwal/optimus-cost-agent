# Agent Evaluation Tooling Research

Status: Draft for review
Date: 2026-07-02
Scope: Phase 1 golden-task tool-trajectory evaluation only

## Decision Summary

Do not adopt `agentevals` for Optimus Phase 1. Its Python package is still
`0.0.9`, released on 2025-07-24, which is too stale for a new evaluation
dependency in a project that currently keeps runtime dependencies deliberately
small.

Prefer DeepEval's `ToolCorrectnessMetric` for the deterministic tool-trajectory
slice because DeepEval is already named in the Test Strategy measurement-tool
taxonomy. Use OpenEvals only as a secondary option if Optimus needs
strict/unordered/subset/superset message-trajectory matching that DeepEval does
not cover ergonomically.

## Scope Boundary

This recommendation covers only tool-call correctness and tool-trajectory
matching.

The following remain Optimus-owned assertions:

- execution mode
- cost band
- final state
- release gate pass/fail
- one-key local credential verification
- gateway usage and pricing reconciliation

## Recommended Path

1. Use DeepEval `ToolCorrectnessMetric` for M1 deterministic tool-call
   evaluation.
2. Configure it without `available_tools` for keyless deterministic scoring.
3. Keep LLM-judge evaluation as a later spike through the Optimus Gateway.
4. Reject `agentevals` unless the Python package becomes active and materially
   better than alternatives.
5. Consider OpenEvals only if strict/unordered/subset/superset trajectory
   matching becomes a real requirement.

## DeepEval Caveat

`ToolCorrectnessMetric` is deterministic for `tools_called` vs `expected_tools`
when `available_tools` is not supplied. If `available_tools` is supplied,
DeepEval adds an LLM optimality layer and takes the minimum of the deterministic
tool-match score and the LLM judgment score. That path is therefore no longer
keyless or deterministic and must use the Gateway-backed judge path.

## Gateway Constraint

Any LLM-scored path must route through the Optimus Gateway using the Plan 3
`GatewayClient` and `/v1/responses` shape. Local `OPENAI_API_KEY`,
`LANGSMITH_API_KEY`, or other provider credentials are not allowed.

## Alternatives

### DeepEval

Preferred for deterministic tool correctness. DeepEval is already sanctioned in
Test Strategy Section 8A for agent-quality evaluation, and
`ToolCorrectnessMetric` provides the closest fit for Optimus golden-task
tool-call checks.

This is a same-tool extension: the tool is already in the taxonomy, but
`ToolCorrectnessMetric` for tool-call correctness is a new, more specific use
that should be recorded when the authoritative test strategy is revised.

### OpenEvals

OpenEvals is the maintained fallback if Optimus needs richer trajectory matching
semantics. Its Python package documents and exposes
`create_trajectory_match_evaluator` with strict, unordered, subset, and superset
matching modes.

Adopting OpenEvals would still require dependency and taxonomy review because it
is not currently named in Test Strategy Section 8A.

### AgentEvals

Rejected for now. AgentEvals is a direct conceptual fit for agent trajectory
evaluation, but the Python distribution is stale for a new Phase 1 dependency:
PyPI still lists `agentevals` as `0.0.9`, released on 2025-07-24.

### LangSmith-Native Evals

Not suitable for local Phase 1 execution. LangSmith remains useful as a trace
observability destination when routed through Optimus-owned infrastructure, but
local LangSmith credentials conflict with the one-key rule.

### Ragas

Keep Ragas focused on retrieval and evidence quality. It is not the right tool
for tool-trajectory matching.

## Governance Destination

This standalone research note is not the final authoritative home. If Optimus
adopts this recommendation, Test Strategy Section 8A should be revised to record
DeepEval `ToolCorrectnessMetric` as an approved same-tool extension for
tool-call correctness, and Plan 8 should fold the adopt/reject outcome into the
golden-task and release-gate work.

## Review Bar

The alternatives section must lead with DeepEval `ToolCorrectnessMetric`, treat
`agentevals` as rejected-on-staleness, keep OpenEvals as a secondary maintained
matcher option, and preserve Gateway-only judge execution for any LLM-scored
path.

## Sources

- DeepEval Tool Correctness:
  https://deepeval.com/docs/metrics-tool-correctness
- DeepEval Task Completion:
  https://deepeval.com/docs/metrics-task-completion
- DeepEval PyPI:
  https://pypi.org/project/deepeval/
- OpenEvals README:
  https://raw.githubusercontent.com/langchain-ai/openevals/main/python/README.md
- OpenEvals trajectory matcher:
  https://raw.githubusercontent.com/langchain-ai/openevals/main/python/openevals/trajectory/match.py
- AgentEvals PyPI:
  https://pypi.org/project/agentevals/
