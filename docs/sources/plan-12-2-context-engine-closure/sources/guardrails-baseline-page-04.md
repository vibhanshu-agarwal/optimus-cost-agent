# Figure 1. Agent execution control plane
:::graph
User request / IDE ACP ingress
Mode policy - Plan/Chat versus Agent
Planner - trusted fixed model; bounded loops / matched skills
Tool-call proposal - model requested, policy decided
permission|Permission: mode / deny / allow / impact
guard|Pre-tool deterministic validators
Sandboxed tool execution - only approved Agent operations
Post-tool audit / cost receipts / trace
Commit and CI gates - actual applicable independent re-check
branch|permission|DENY -> rejected; HOLD -> human review
branch|guard|BLOCK -> rejected; HOLD -> human review
:::end
A denied or ambiguous action diverts to rejection or the existing human-review path before execution. The reserved classifier cannot overturn a deny; this figure does not activate it. Every loop/skill inherits these controls.

# 2. Permission model
Permissions remain two-layer allow/deny rules with a mode overlay and an explicit human-approval path. Shared project allow rules cover understood recurring operations; user/deployment deny rules take precedence. Guardrails remove unsafe shortcuts without asking humans to approve every harmless inspection. The following sections retain their project rules, deny rules and mode mapping.
