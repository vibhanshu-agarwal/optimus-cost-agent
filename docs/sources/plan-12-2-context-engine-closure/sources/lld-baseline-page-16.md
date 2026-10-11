# Mode-specific permission matrix
Permissions are enforced by the harness, not model instruction. Agent permissions still require the current artifact, approval and tool-specific guard; a Yes cell is not unconditional authority.
| Capability | Plan/Chat | Agent | Enforcement |
|---|---|---|---|
| Read repo / inspect files | Yes | Yes | Existing eligible workspace / read controls |
| Read-only analysis tools | Yes | Yes | Existing read controls |
| Policy-gated web search / extract | Yes | Yes | ToolInvocationPolicy and provenance |
| Produce diffs / snippets as text | Yes | Yes | Text payload only, not applied |
| Shadow apply patch | No | Yes | assert_mutation_allowed gate |
| Mutate working tree | No | Yes | assert_mutation_allowed + MutationGuard + approval |
| Shell / build / test | No | Yes | Agent mode and applicable fitness/approval gates |
| Append cost / audit telemetry | Yes | Yes | Append-only |
| Modify telemetry / ledger entries | No | No | Immutable after write |

## Execution pathway
The retained pathway connects captured user intent/mode, explicit eligible model selection, mutation gating and telemetry through the Gateway boundary. Intent classification in the predecessor was a reserved capability; this successor does not activate Auto/classifier routing. Section 4A's revised pathway and state diagram preserve advisory ChatOnly, AwaitingApproval, Failed/replan, fitness and termination branches.
