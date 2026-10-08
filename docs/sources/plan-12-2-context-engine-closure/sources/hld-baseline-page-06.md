- Fitness gate fails → reflection or targeted local inspection.
- Plan/Chat mode active → read/search tools only, no mutation tools.

Each web-evidence request carries an explicit reason code (e.g. API_DOCS_OUTDATED, CURRENT_FACT, SECURITY_ADVISORY, USER_REQUESTED, PACKAGE_VERSION) plus an allowed-domain list, result cap, and search-depth setting, so external calls remain auditable and cost-bounded rather than ad hoc.

Web evidence acquisition is wrapped behind Optimus-owned typed tools rather than exposing a third-party search API directly to the model. This lets the harness enforce allowed domains, timeouts, retries, result caps, and cost telemetry uniformly. Key rule: local evidence first, external evidence only when policy-triggered, mutation only after mode and fitness gates pass.

# 9. Adaptive Agent Execution Strategy & Rigor Policy

Optimus applies adaptive execution strategies to balance cost, rigor, and reliability. The agent selects Direct Execution, Plan-and-Execute, ReAct, or Reflection based on task ambiguity, mutation risk, and validation outcomes. Reflection and deep planning are not default behaviours; they are exception-triggered circuit breakers invoked only when risk signals, failed validation, or insufficient evidence require additional rigor.

Low-Cost Hallucination Controls
- Evidence-Bound Decisions: No architectural claim may be promoted to an implementation

decision unless backed by inspected context or recorded as an explicit entry in a machine-readable Assumption Ledger.
- Rigor Budget Matrix: Bounded request tiers (LOW, MEDIUM, HIGH) prevent the agent from

spending tokens on ceremonial planning loops for simple edits:

– LOW: Cap at 5 tool calls, 0 reflection passes, min(262144, verified route window)-token total request ceiling including output; eligible fixed model.

– MEDIUM: Cap at 10 tool calls, 1 reflection pass, min(262144, verified route window)-token total request ceiling including output; eligible fixed model.

– HIGH: Cap at 15 tool calls, 3 reflection passes, min(262144, verified route window)-token total request ceiling including output; eligible fixed model.
- Trigger-Based Reflection: Reflection initialises only when validation loops trip a failure

signature or code touches shared/core architecture modules, preventing quiet token-doubling on every nominal request.
- Assumption Ledger: Bypasses token-heavy text summaries by generating an explicit JSON

ledger identifying unverified assumptions, confidence thresholds, and specific validation files needed to clear uncertainty.
- The Escalation Ladder: Bounds agent tool invocation paths to escalate strictly through a

cost-minimising chain: Provided Context → File Inspection → Plan → Execute → Validate → Targeted Reflection → User Escalation.

# 10. Architectural Control Flow

This section provides visual reference diagrams for the two primary control flow concerns in Optimus: where the system boundaries sit, how the governance loop operates end-to-end.