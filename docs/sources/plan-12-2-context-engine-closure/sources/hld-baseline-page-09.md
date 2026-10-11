Target contract after the named trusted-policy / Task 11 / coverage migration as applicable; the dated inactive production baseline is stated on the cover.

# 10.C Phase Evolution Diagram

Optimus is designed as a three-phase architecture. Phase 1 is mandatory before any later phase.

**PHASE 1 -> Python Local Agent + Optimus Gateway**
Current - Mandatory before Phase 2

**Release Gate:** the agent runs with only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; no upstream
key is resolvable in the agent process. The separate loopback Gateway receives only its approved
aggregator key and optional infrastructure configuration.

**PHASE 2 -> Rust Core Rewrite**
Trigger: Python performance ceiling or team scaling

**PHASE 3 -> Agentic Mesh Topology**
Trigger: Multi-repo / multi-team deployment

See: Optimus-Architecture-Roadmap.pdf

# 10.D Where Cost Control Happens

Cost control is not a single checkpoint - it is enforced at four distinct points in the request
lifecycle, each with a different mechanism.

| Control Point | Mechanism | What It Prevents |
|---|---|---|
| 1. Pre-prompt (Feedforward) | AST slicing + cache anchoring + ADL constraints | Unnecessary tokens sent to expensive models. |
| 2. Router (Triage Gate) | Explicit eligible fixed model from trusted registry; Auto classifier remains dormant | Over-routing simple tasks to ineligible or unnecessarily expensive route. |
| 3. Rigor Budget (Runtime) | LOW/MEDIUM/HIGH tier caps tool calls + reflection passes | Token-doubling on ceremonial planning loops. |
| 4. Post-call (Attribution) | Gateway usage object -> EvidenceLedger -> RedisTimeSeries | Silent cost accumulation; enables per-run audit. |

# 10.E Where Hallucination Control Happens

Hallucination is controlled through a defence-in-depth stack. No single gate is sufficient; all five
layers must be active simultaneously.

| Layer | Mechanism | What It Catches |
|---|---|---|
| 1. Context Constraint | ADL rules injected pre-prompt; AST slices only relevant code | Irrelevant context that confuses the model. |
| 2. Evidence Gate | Assumption Ledger: every architectural claim must be inspected or logged | Unverified claims promoted to implementation decisions. |
| 3. Tool Policy | ToolInvocationPolicy blocks casual web calls; reason codes required | Model hallucinating external facts without evidence. |
| 4. Fitness Functions | PyTestArch and static metrics gates | Structurally invalid or low-quality changes. |
| 5. Reflection Circuit | Bounded reflection with prior-failure summaries | Repeated failure without targeted replanning. |