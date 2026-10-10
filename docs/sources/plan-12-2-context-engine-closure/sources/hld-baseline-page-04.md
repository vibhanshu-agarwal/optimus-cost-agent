Target contract after the named trusted-policy / Task 11 / coverage migration as applicable; the dated inactive production baseline is stated on the cover.

# 6. Deterministic Data-Flow Architecture (Phase 1 MVP)

The updated system design integrates closed-loop Harness Engineering directly into the
orchestration sequence:

1. User Request Initiated (IntelliJ IDEA Client).
2. Ingress over ACP Protocol over StdIn JSON-RPC to the Optimus ACP Server Daemon (Asyncio
   Pipeline).
3. Read Topology & Structural Memory Maps from Local Redis State Store (HASH Schema Core Pull),
   which returns active code signatures and cached map assets.
4. Processing inside the Context Optimization Node [FEEDFORWARD CONTROLS] executing AST Slicing,
   Polyglot Fallbacks, ADL Constraint Prompt Injection, and Prompt Anchoring for Cache Tuning.
5. Emits minimal context prompt payload to the host-selected eligible fixed-model path under the curated registry. Auto classification and automatic escalation remain deferred.
6. **Delivery to the loopback Optimus Gateway -> approved upstream aggregator (OpenRouter by
   default; Vercel AI Gateway if retained), returning the model output and provider-reported usage
   and USD cost. Model aliases remain policy inputs, but the agent never selects or contacts a
   direct provider adapter.**
7. Validation inside the Automated Fitness Function Engine [FEEDBACK SENSORS] conducting atomic
   structural checks via PyTestArch and static code metrics gate assertions (MI / Complexity
   Check). On FAIL: loops back to Step [6]; on PASS: approves code patch execution path.
8. Storage inside the Local Storage Engine Persistence Layer via Async TS.ADD Numeric Telemetry
   Tracking (RedisTimeSeries) and Async HSET Workspace Metrics Serialisation (Redis HASH
   Architecture Indexes).
9. Real-Time FinOps Console Panel display for IDE Cost Dashboard Live Update Screen.

# 7. Agent Operating Modes & Trust Framework

To guarantee user trust and operational predictability, the control plane implements strict
execution state isolation:

- **Plan/Chat Mode:** Advisory-only mode. The agent may inspect context, discuss requirements,
  propose plans, and produce diffs or snippets for review, but it must not mutate the repository,
  filesystem, external services, or user/project state. Internal cost, audit, and performance
  telemetry is append-only and explicitly allowed.
- **Agent Mode:** Execution mode. The agent is write-authorised and empowered to actively modify
  code, run tools, create files, update tests, and apply patches within approved workspace
  boundaries. Modifications apply to the working tree only after clearing all composite fitness
  engine gates.
- **Code Generation Scope Classification:** Delineates advisory inline fragments from
  implementation deliverables based on clear architectural criteria:
  - `INLINE_SNIPPET`: Explanatory text fragments under 15 lines that touch zero core packages and
    create/delete no files.
  - `PATCH_PROPOSAL`: A bounded diff or file mutation proposal for review.
  - `IMPLEMENTATION_DELIVERABLE`: A multi-file change that requires Agent Mode and all release
    gates.