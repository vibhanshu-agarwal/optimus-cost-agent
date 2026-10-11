# 4A. Execution strategy selection and tool policy
| Strategy | Trigger | Behavior / bounds |
|---|---|---|
| Direct | Low rigor, no mutation | Single result, up to five tool calls, zero reflection; eligible fixed model |
| Plan-and-Execute | High task risk or multi-file changeset (retained prototype) | Structured plan and exact approval; up to ten calls and one reflection |
| ReAct | High ambiguity | Interleave bounded reasoning/observations; preserve configured call/iteration bounds |
| Reflection | Gate failure or shared/core change | Targeted recovery, at most three reflection passes; never the default loop |
These descriptive strategies do not automatically activate Auto routing or override current three-round/30-minute/two-repeated-failure ACP limits. All obey final verified route capacity; HAIKU/PRO aliases and separate risk-tier context ceilings are retired.
Tool invocation is harness-controlled, first matching policy wins. Reject mutating tools in Plan/Chat with -32002 before I/O. WEB_SEARCH requires a current/external-fact, API or security signal and a valid reason code; local evidence remains first. WEB_EXTRACT requires the URL to belong to the prior authorized search result set. A mutation without current artifact approval is rejected before execution. Local read/inspect/analysis tools still pass the existing deterministic mode/permission rules. The model never selects the policy row or invents provenance.
