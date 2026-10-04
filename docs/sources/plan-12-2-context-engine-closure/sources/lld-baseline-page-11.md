Target contract after the named trusted-policy / Task 11 / coverage migration as applicable; the dated inactive production baseline is stated on the cover.

# 4. Scope classification and strategy selection (continued)
The following retained prototype illustrates scope classification; it is not a new runtime activation or additional policy decision. Ordered branches:
| Priority | Condition | Scope |
|---|---|---|
| 1 | Shared module touched; multiple directory roots; structural create/delete across more than one file; or more than three files | MULTI_FILE_CHANGESET |
| 2 | Structural create/delete; or one file with more than 100 lines | FILE_MUTATION |
| 3 | More than 15 lines | PATCH_PROPOSAL |
| 4 | Otherwise | INLINE_SNIPPET |
Execution strategy remains harness-controlled. Start with at most five tool calls and zero reflection passes; a validation failure or shared-module change selects bounded Reflection with at most 15 calls and three passes. High task risk or a multi-file changeset selects Plan-and-Execute with at most ten calls and one reflection. High ambiguity otherwise selects ReAct with at most 12 calls. Other work uses Direct execution. No new mandatory reflection loop is introduced.
After approved trusted policy activation, all branches obtain the eligible fixed model from the trusted role/route registry and obey its actual request capacity, with a total context ceiling of 262144 including one output reserve. Retire the old branch-specific 100000/150000/250000 token ceilings and HAIKU/PRO aliases. History strategy allocations and final input/output packing are separate. Auto classification and struggle escalation are not activated.
Mutation enforcement continues in section 4: PLAN cannot perform WRITE or EXTERNAL_MUTATION and raises the typed validation error. The existing MutationGuard wraps that assertion before execution; the continuation on the next page retains its path-containment contracts.
