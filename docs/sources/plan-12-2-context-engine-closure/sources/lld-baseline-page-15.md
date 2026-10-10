# 4A. Valid and invalid transitions
Every transition is deterministic; model text cannot override a rejection. Existing mode and exact-approval checks remain required.
| From | To | Permitted / condition |
|---|---|---|
| Idle | Planning | Yes, user request |
| Planning | PlanReady | Yes, requirements and mode resolved |
| PlanReady | ChatOnly | Yes, Plan/Chat; no mutation |
| PlanReady | Executing directly | No; AwaitingApproval cannot be bypassed |
| PlanReady | AwaitingApproval | Yes, Agent needs exact artifact approval |
| AwaitingApproval | Executing | Yes, current approval and target checks pass |
| AwaitingApproval | ChatOnly | Yes, denied/timed-out approval returns advisory outcome |
| Executing | ToolCalling | Yes, ToolInvocationPolicy authorizes the call |
| Executing | Mutating ToolCalling | Only Agent mode plus approval/guard controls |
| ToolCalling | Validating | Yes, operation response received |
| Validating | Executing | Yes, applicable gates pass |
| Validating | Failed | Yes, record actual failure and count it |
| Failed | Planning | Only within configured count/time/failure controls; inject targeted failure context |
| Failed | Terminated | Finite work exhausted, cancellation or permanent failure; report cause. No product dollar exhaustion after migration. |
| Executing | Completed | All planned work/gates complete; actual effect evidence retained |
| Any | Executing by bypass | No, -32002; approval path remains mandatory |
Interim ACP defaults remain three planning rounds, 30 minutes and two repeated failures. Generic architecture diagrams do not override concrete configured execution limits. Independent evaluation budget exhaustion is a separate scoped stop, not product policy.
