# Plan 11 open-work root-cause audit

**Status:** Investigation only. No pool status, source, frozen artifact, or live service was changed.

**Working baseline:** `6edd0e2` (`origin/main` at branch creation, 2026-08-18).

## Scope and method

This audit reads the owning entry's own `**Status:**` line, not a roadmap or README
projection. It covers every non-closed Plan-11 follow-up/feature in the consolidated pool,
plus `P9.8-FU-5` and `P9.87-FU-1` because their designated custody is Plan 11. It excludes
items designated only to Plan 12 or another future lane.

The pool's own closure rule is important: only `Closed` and `Reviewed disposition` satisfy
the v1.0 pool-closure gate; `Open`, `Promoted`, and `Partially implemented` do not
([pool:30-41](../docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md)).
Accordingly, “blocks closing 11.x” below distinguishes the formal current gate from a
technical/product blocker. A conditional or uninvestigated row should not silently retain
that formal veto merely because it was once placed in the pool.

### Search record

All searches below ran at `6edd0e2` and are recorded so absence and already-satisfiable
claims are reproducible.

| Check | Command | Result | Use in this audit |
|---|---|---|---|
| Client-MCP adapter construction | `rg -n --glob '*.py' 'ClientMcpSdkAdapter\(' src` | 0 matches | Confirms P11-FU-20's production runtime remains absent. |
| Concrete client-MCP dispatch service | `rg -n --glob '*.py' 'class .+\(ClientMcpToolService\)' src` | 0 matches | Confirms the same runtime has no production dispatch implementation. |
| Materialization caller | `rg -n --glob '*.py' 'materialize_tool_service\(' src` | Definition only: `src/optimus/mcp/client_disposition.py:209` | Confirms no production composition caller exists. |
| P11.7-FU-3 source condition | `rg -n -i -C 3 'docstring|replacement|corrupt|\uFFFD|em dash|em-dash|—|�' tools/plan117_custody_relay.py` | U+2014 remains at lines 5-8, 164, and 843; no replacement-character match | Confirms the item is a small, present hygiene change, not an unavailable external tier. |
| Resume surface | `rg -n 'session/load|loadSession|sessionCapabilities' src/optimus/acp/spec.py src/optimus/acp/server.py` | `spec.py:277-278` explicitly leaves `session/load` unadvertised and capabilities empty | Confirms P11-FU-1 is still a real missing capability. |

The first three results agree with the independent WP-4 investigation
([report](p11-fu-20-client-mcp-runtime-gap-investigation.md), §§1, 4, and 6), which also
established that the missing runtime is an absent subsystem rather than an `acpx` problem.

## Classification ledger

| Item | Own status read | Classification | Root cause or remaining unknown | Does it actually block closing 11.x? | Recommendation |
|---|---|---|---|---|---|
| `P9.8-FU-5` | Promoted to Plan 11.7 | Genuine blocker, root cause established | A real Zed client panicked after rendering the refusal; project ACP wire evidence is distinct. | **Formal yes**; technically it needs an explicit external-Zed disposition or new authorized live evidence, not a repository workaround. | Ask the operator to disposition the external defect or authorize a bounded new Zed lane. |
| `P9.87-FU-1` | Open | Deferred assumption, cause never established | The trigger is only a future observation that policy bytes can pass through; no such triggering evidence is cited. | **Formal yes**, but no: it is not a demonstrated Plan-11 release blocker. | Move to its named future feature/Plan 12 custody unless a trigger is produced. |
| `P11-FU-1` | Promoted to Plan 11.7 | Genuine blocker, root cause established | `session/load` is unimplemented and unadvertised; the pool also records a process-local store with no approved durable session design. | **Yes**: it is a stated Plan-11 capability and the formal gate remains unsatisfied. | Resolve alongside the parent Zed disposition: implement under a new authorized design, or obtain an explicit reviewed scope/disposition. |
| `P11-FU-4` | Open | Genuine blocker, root cause established | Its own entry identifies implementation drift between historical FU-4A/FU-5 evidence and current code. | **Yes under the pool gate**; it is an evidence-freshness requirement rather than a new product defect. | Schedule a credentialed real-`acpx` recapture/disposition package with cost authority; do not treat prior evidence as current. |
| `P11-FU-5` | Open | Deferred assumption, cause never established | Windows `DuplicateHandle` is reproduced, but the pool says its recurrence rate and deterministic causal edge remain unknown. | **Formal yes**, but no current product-effect blocker is established. | Keep separate from FU-29; obtain a bounded root-cause or reviewed non-reproduction disposition before allocating a fix. |
| `P11-FU-6` | Open | Deferred assumption, cause never established | Full-suite Windows recurrence is real, but readiness, shutdown, and server-thread propagation have not been discriminated. | **Formal yes**, but its own triage says test-harness-only and no product effect. | Run the already-required feasibility/root-cause lane; do not keep it as an unqualified v1 product blocker. |
| `P11-FU-7` | Promoted to Plan 11.16 | Genuine blocker, root cause established | The coverage/`sys.settrace` timing diagnosis is established and the test-only correction landed; its final Windows coverage gate stopped only because FU-6 recurred. | **Formal yes**; technically its remaining closure condition is shared evidence, not unfinished product code. | Decide whether the FU-6 gate can be decoupled or run it only with FU-6's own disposition; do not call FU-7 closed first. |
| `P11-FU-8` | Open | Deferred assumption, cause never established | The current variable works; a rename needs an unchosen compatibility-alias and durable-approval migration design. | **Formal yes**, but no current runtime failure blocks 11.x. | Move to a future migration plan or explicitly disposition it from Plan 11; never silently rename. |
| `P11.7-FU-3` | Open | Stale / already satisfiable | The owned file still contains U+2014, while its own acceptance criterion is an isolated codepoint cleanup. The recorded search above proves the condition is present and local. | **Formal yes**; technically no external dependency or unresolved cause blocks the edit. | Schedule as a tiny isolated hygiene change with a byte/codepoint test, or close after that proof. |
| `P11-FU-11` | Partially implemented | Genuine blocker, root cause established | Path A safely stopped because no live proof could be acquired from the dead origin-A session; accepted same-session retry was not obtained and a new launch needs separately authorized budget. | **Yes** for the Zed-resume lane; it is not a generic code defect. | Seek a reviewed Zed/budget disposition before another live attempt; retain the safe terminal result. |
| `P11-FU-16` | Open | Deferred assumption, cause never established | It names a future generalized documentation gate but cites no current missing authoritative learning. | **Formal yes**, but no: it is future cross-cutting capability work. | Move it out of the Plan-11 closure inventory or obtain an operator reviewed disposition. |
| `P11-FU-20` | Promoted to Plan 11.20 | Genuine blocker, root cause established | The production discovery → composition subsystem is absent: no adapter construction, concrete service, or materialization caller (search record above). | **Yes**: Plan 11.20 explicitly keeps it open without the real tier. | Review the post-baseline [Plan 11.23 draft PR #169](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/169), then implement its buildable runtime tasks and pursue separately authorized live proof. This pending proposal is not baseline evidence. |
| `P11-FU-23` | Open | Deferred assumption, cause never established | Optional second-stage descriptor pinning/allowlists have no demonstrated first-release trigger. | **Formal yes**, but no base client-MCP path requires it. | Retain only in future client-MCP trust custody; do not treat it as a Plan-11 closure prerequisite. |
| `P11-FU-24` | Open | Deferred assumption, cause never established | It is a future proposal to relax the current equal-ceremony model; no materially safer alternative is specified. | **Formal yes**, but no: the stricter shipped posture is a valid baseline. | Disposition to future client-MCP trust work unless a concrete relaxation design is requested. |
| `P11-FU-25` | Open | Deferred assumption, cause never established | Authenticated-upstream evidence is explicitly after the base client path and needs an operator-approved non-secret credential and independent server. | **Formal yes**, but it cannot be a prerequisite to fixing P11-FU-20's unauthenticated base runtime. | Move to a later authenticated-client-MCP evidence lane; do not block the base runtime package. |
| `P11-FEAT-ZED-RESUME` | Partially implemented | Genuine blocker, root cause established | The feature row records an unimplemented resume capability and blocked live path, while the re-probe established only an agent gate, not Zed support. | **Yes**: it is an expressly live Plan-11 feature slice. | Make one operator ruling: new authorized evidence/design lane or reviewed external/conditional disposition. |
| `P11-FEAT-REGISTRY` | Open | Deferred assumption, cause never established | The public registry process is known, but the external Agent/Terminal Auth admission rule still needs live validation before scope is frozen. | **Formal yes** because it is listed as the last primary slice; technically its external prerequisite is unverified. | Run a no-release-impact admission probe first, then decide Plan-11-last versus a later publication split. |
| `P11-FEAT-IDE` | Open | Deferred assumption, cause never established | The row is explicitly conditional on Registry exposing an unmet multi-IDE expectation. | **No technical blocker now**; formal pool status should not override its own unmet condition. | Record a reviewed conditional disposition or move it out of Plan 11 until Registry supplies the trigger. |

## What genuinely remains for Plan 11 closure

The current pool makes all 18 rows formal closure blockers. That is truthful as a description
of the current bookkeeping rule, but not a useful execution order. The evidence supports this
ranked disposition for the operator:

1. **P11-FU-20 — implement the absent runtime now.** It is a bounded source-and-hermetic-test
   package; the pending post-baseline Plan 11.23 draft PR #169 separates it from the two genuinely
   hard live prerequisites (paid Gateway authority and an independently authored write-capable MCP
   server).
2. **Zed-resume decision — P11-FEAT-ZED-RESUME, P11-FU-1, P11-FU-11, and P9.8-FU-5.** These are
   one externally constrained capability/evidence cluster, not four independent code fixes. A
   reviewed external disposition or an operator-authorized renewed live/budget lane is required.
3. **P11-FU-4 and P11-FU-7 evidence closure.** FU-4 needs fresh real evidence; FU-7 needs a
   decision about its shared FU-6 coverage gate. Neither should be closed from historic or fake
   evidence.
4. **P11-FU-5 and P11-FU-6 root-cause work.** They are real test-harness recurrences but neither
   has a causal diagnosis or product impact. They need a bounded investigation/disposition, not
   speculative fixes or indefinite v1 veto power.
5. **Immediate low-risk cleanup: P11.7-FU-3.** The source scan proves this is ready for a focused
   hygiene patch and test.
6. **Disposition/move out of Plan 11 unless a new trigger appears:** P9.87-FU-1, P11-FU-8,
   P11-FU-16, P11-FU-23, P11-FU-24, P11-FU-25, and P11-FEAT-IDE. These are future policy,
   migration, or conditional capabilities, not demonstrated defects in the release path.
7. **P11-FEAT-REGISTRY needs a prereq probe, then a scope ruling.** Its external rule is unknown;
   no implementation commitment should precede that answer.

## Counts and operator decision requested

- **Genuine blockers with established root cause:** 7
- **Deferred assumptions with no established causal need:** 10
- **Stale / already satisfiable:** 1

The operator should decide whether the seven current formal-but-nontechnical-veto rows in rank 6
(including the conditional IDE slice) are dispositioned out of Plan 11. Without that decision, the
pool's literal closure rule keeps them as blockers even though their own entries do not establish a
current Plan-11 requirement.

## Audit self-review

- Every row above is an active pool item or explicitly designated to Plan 11; each classification
  states the entry's own status rather than inferring it from the index.
- No pool state is changed. Recommendations identify owner/action but leave disposition to the
  operator.
- The only absence and already-satisfiable conclusions are backed by the reproducible search table.
- P11-FU-20 preserves the WP-4 classification: absent runtime subsystem, buildable source work
  now, and separately authority-gated live evidence later.
