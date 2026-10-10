# 4A. Agent lifecycle state machine
:::graph
Idle
Planning
ready|PlanReady
approval|AwaitingApproval (Agent only)
Executing
ToolCalling
validating|Validating / fitness gate
Completed
branch|ready|Plan/Chat -> ChatOnly (read-only)
branch|approval|Denied / timeout -> ChatOnly
branch|validating|FAIL -> Failed -> bounded Planning
branch|validating|Limit / halt -> Terminated
:::end
| Branch | Required transition |
|---|---|
| Plan/Chat | PlanReady -> ChatOnly; no mutation |
| Agent | PlanReady -> AwaitingApproval; current exact approval -> Executing |
| Tool result | ToolCalling -> Validating; PASS -> Executing or Completed |
| Fitness failure | Failed -> Planning only within finite count/time/failure bounds |
| Exhaustion / cancellation | Failed -> Terminated with true reason and retained effects/receipts |
No direct PlanReady -> Executing transition is allowed. Historical approval and model prose cannot bypass the current artifact gate. This figure does not activate Auto routing.
