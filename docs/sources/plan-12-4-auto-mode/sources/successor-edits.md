## Covers

### H1 — HLD v2.22

```markdown
# Optimus - Architecture (HLD)

**Version 2.22 — Plan 12.4 Auto mode, 2026-10-27; local filing — not activated.**

Predecessor: Optimus-Cost-Agent-Architecture-v2.21.pdf; SHA-256 44a11f53eb6c55b27fa369b5849e2c454f383c0604b4e62ce148f83b88e33b38. Retain the predecessor unchanged in `docs/archive/`.

Native carried page bodies originate from Optimus-Cost-Agent-Architecture-v2.18.pdf (SHA-256 0f8725765fecc9a93045fd26630457dfe7112508df164a3ec5bcc55dbc976807). This complete successor retains the predecessor's carried bodies and source corrections except for the changes identified below. Page keys remain those of the native baseline.

**What this edition changes.** It describes opt-in Auto routing, H's rules-then-Jev judge, per-turn model binding, routing notices and accounting, and the registry facts those paths require: active trusted enforcement, per-entry admission, the operator override and ADR-026's narrowly accepted guardrail stage. These statements describe main `bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1`, PR #428's merge of main `8713dcbfbc05f9372619dfe655f83b247dc3751a` and PR head `df7dc3c52dbc64ec5d18d27e05766c1953715853` (2026-10-27). ADR-028 accepts ADR-007 with H; automatic struggle escalation remains separate work under #397.

**Inspected production facts at bf440cb.** `ENFORCEMENT_ACTIVE` is True. Ordinary launch composes the enforced registry and constructs the ordinary Context Engine attachment when an eligible summarizer exists. Auto is selected only by `OPTIMUS_AGENT_MODEL=auto`, uses its separately approved composition, and binds one planning/answer model for each turn. The shipped Auto overlay admits Luna and Gemini through recorded empirical estimates; this is not proof of a universal token bound. Classifier calls use the Gateway and the turn's `classification` settlement stage. Reviewer/depth behavior and the savings-report surface are not delivered by Auto.

**Provenance and controlling Plan 12.2 amendment.** Unchanged baseline statements retain `91fd64ac78025efe1076bddb106ff89e6adb2030` provenance; localized EDIT and its execution-path corrections retain `57e2069414fef32c6a6e4de42bd0dc7fb9f4f1ac`. This is not a full current-state refresh. The 2026-10-18 amendment, `docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`, remains controlling for the unrefreshed Plan 12.2 material, including §14.2's source/compaction policy, profiles, maintenance and historical evidence. This edition supplies the newer registry, production-construction and Auto statements where expressly updated. It does not revise Guardrails. Retained interim loop limits and goal-loop descriptions are historical; ADR-024 governs the separately delivered interactive loop-control policy.

**Evidence stays attached to its source.** The prior offline and EDIT receipts retain their original pins. Auto's three live acpx slices are reported at PR head `df7dc3c`, not as merge-commit reruns (§15). Pilot acceptance, implementation, live evidence and launch authorization are distinct.

**Authority.** Codex's architecture wording; local filing by Claude under the operator's 2026-10-27 instruction: "Start the HLD v2.22 / LLD v2.45 successor for Plan 12.4 under #395, built from the baseline page keys with Codex authoring the replace-edits. SKIP=check-added-large-files is approved for its PDFs." Publication to main requires the operator's separate approval. The filing label does not disable Auto already shipped in the pinned code. This document grants no additional implementation, service-change, paid-call or publication authority. No product suite or live call was run to author this text.
```

### L1 — LLD v2.45

```markdown
# Optimus - Low-Level Design

**Version 2.45 — Plan 12.4 Auto mode, 2026-10-27; local filing — not activated.**

Predecessor: Optimus-Cost-Agent-LLD-v2.44.pdf; SHA-256 80305863042581aa1bde2517c3d9473923bcd20db2c939a2925163592c63f885. Retain the predecessor unchanged in `docs/archive/`.

Native carried page bodies originate from Optimus-Cost-Agent-LLD-v2.41.pdf (SHA-256 69400fd474eb30711fcc9a061243d6a4d2e35d39d7794d4aa69f5ff51b98109b). This complete successor retains the predecessor's carried bodies and source corrections except for the changes identified below. Page keys remain those of the native baseline.

**What this edition changes.** It specifies the Auto composition and approval binding, frozen classifier input, `AutoRouter`, H, the Gateway decisions route, classification settlement, per-launch model stops, per-turn notices and routing records (§13.10). It also corrects the registry and production-construction statements those contracts depend on. New implementation statements describe main `bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1`, PR #428's merge of main `8713dcbfbc05f9372619dfe655f83b247dc3751a` and PR head `df7dc3c52dbc64ec5d18d27e05766c1953715853` (2026-10-27). ADR-028 accepts ADR-007 with H; ADR-009 rung 2 remains deferred under #397.

**Inspected production facts at bf440cb.** Trusted registry enforcement is active. Ordinary bootstrap supplies the route policy and, with an eligible summarizer, the Context Engine attachment. Models carry their admission evidence as configuration; the trusted operator override participates in the approved effective hash. Auto adds its overlay and `_composition` binding. The classifier uses authenticated `POST /v1/decisions`, with independent admission and reply checks, and its attempts enter ordinary turn settlement as `classification`. An Auto turn's selected planning/answer model and context limits remain bound through planning and approved application; the summarizer retains its separate registry role.

**Provenance and controlling Plan 12.2 amendment.** Unchanged baseline statements retain `91fd64ac78025efe1076bddb106ff89e6adb2030` provenance; §4B and the localized EDIT corrections retain `57e2069414fef32c6a6e4de42bd0dc7fb9f4f1ac`. This is not a full current-state refresh. The 2026-10-18 amendment, `docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`, remains controlling for the unrefreshed Plan 12.2 material in §13 and §14, including compaction, profiles, maintenance and historical evidence. This edition supplies the newer registry, production-construction and Auto statements where expressly updated. Guardrails is unchanged. ADR-024 governs interactive loop control; retained numerical limits and legacy goal-loop descriptions do not override it.

**Evidence stays attached to its source.** The prior offline and EDIT receipts retain their original pins. Auto's three live acpx slices are reported at PR head `df7dc3c`, not as merge-commit reruns (§14). Pilot acceptance and source inspection do not establish every live failure path or a universal request-fit guarantee.

**Authority.** Codex's architecture wording; local filing by Claude under the operator's 2026-10-27 instruction: "Start the HLD v2.22 / LLD v2.45 successor for Plan 12.4 under #395, built from the baseline page keys with Codex authoring the replace-edits. SKIP=check-added-large-files is approved for its PDFs." Publication to main requires the operator's separate approval. The filing label does not disable Auto already shipped in the pinned code. This document grants no additional implementation, service-change, paid-call or publication authority. No product suite or live call was run to author this text.
```

## Edits

### H2 — hld/4

OLD:
```text
5. Emits minimal context prompt payload to the host-selected eligible fixed-model path under the curated registry. Auto classification and automatic escalation remain deferred.
```

NEW:
```text
5. Emits the bounded context payload to an eligible planning/answer model under the enforced curated registry. Ordinary launches use their configured fixed model. With `OPTIMUS_AGENT_MODEL=auto`, the approved Auto composition classifies the turn and selects its model before planning or answering; that model remains fixed for the turn (§14.7). Automatic struggle escalation during a turn remains deferred under #397.
```

### H3 — hld/8

OLD:
```text
Every generated executable candidate remains subject to feedforward context/trust constraints and feedback/approval gates. Haiku triage and a hard-coded GLM/Pro route are replaced by the explicit curated fixed-model path.
```

NEW:
```text
Every generated executable candidate remains subject to feedforward context/trust constraints and feedback/approval gates. Model selection uses the enforced registry: a configured fixed model in ordinary launches, or Auto's per-turn selection in an explicitly approved Auto launch (§14.7). The diagram abstracts that selection; it does not specify H's classifier or grant execution authority.
```

### H3 — hld/8

OLD:
```text
Trusted eligible fixed model and verified route
```

NEW:
```text
Trusted eligible turn model and admitted route
```

### H3 — hld/8

OLD:
```text
A failed fitness gate supplies targeted failure context only while the configured planning/time/repeated-failure bounds permit another round; otherwise report the stop truthfully. Plan/Chat never enters the mutation path. Current interim ACP bounds remain three planning rounds, 30 minutes and two repeated failures. No Auto classifier, product dollar stop or new recovery graph is activated. Figure 10.B retains the existing feedforward/feedback distinction and closes the approval/effect loop.
```

NEW:
```text
A failed fitness gate supplies targeted failure context only where that gate and bounded replanning are composed; otherwise report the stop truthfully. Plan/Chat never enters the mutation path. The predecessor's three-round/30-minute/two-repeated-failure statement described its interim baseline; ADR-024 governs current interactive loop control, which is outside this scoped refresh. At `bf440cb`, Auto classification is implemented and opt-in. Product dollar stops remain removed. Auto's confidence and availability route-ups occur before planning/answer dispatch; they do not implement ADR-009's deferred struggle-escalation rung (#397). Figure 10.B retains the feedforward/feedback distinction and approval/effect boundary.
```

### H4 — hld/9

OLD:
```text
| 2. Router (Triage Gate) | Explicit eligible fixed model from trusted registry; Auto classifier remains dormant | Over-routing simple tasks to ineligible or unnecessarily expensive route. |
```

NEW:
```text
| 2. Router (Triage Gate) | Enforced trusted registry; configured fixed model ordinarily, or H classification and cheapest eligible unstopped model in an approved opt-in Auto launch (§14.7) | Ineligible dispatch; Auto aims to reduce unnecessary routing cost, with the measured limitations in ADR-028. |
```

### H5 — hld/6

OLD:
```text
The min(262144, verified route window) request ceiling is implemented in `optimus_model_policy`, with production enforcement inactive (§14.4).
```

NEW:
```text
The min(262144, admitted route window) planning/answer request ceiling is enforced at `bf440cb` (§14.4). Route admission includes the explicitly approved empirical-estimator exceptions; it does not make their estimates proven bounds. The preceding runtime-limit description retains its `91fd64a` pin; ADR-024 governs current interactive loop control.
```

### H5 — hld/10

OLD:
```text
- Route explicitly eligible model IDs through the surviving OpenAI-compatible transport after trusted policy
  composition (trusted-policy enforcement is built and inactive at 91fd64a: `ENFORCEMENT_ACTIVE = False`).
```

NEW:
```text
- Route explicitly eligible model IDs under the enforced trusted registry at `bf440cb`
  (`ENFORCEMENT_ACTIVE = True`). Planning/answer requests use the OpenAI-compatible transport;
  classifier decisions use the separate authenticated `/v1/decisions` route (§14.7).
```

### H5 — hld/11

OLD:
```text
Independent evaluation dollar caps remain scoped to their authorized evaluations. Product dollar stops were removed at cf9bb9d and merged to `main` via PR #276 (`c509fc8`, 2026-10-08); production context enforcement remains inactive at 91fd64a. Evaluation ceilings remain scoped to independently authorized evaluations.
```

NEW:
```text
Independent evaluation dollar caps remain scoped to their authorized evaluations. Product dollar stops were removed at cf9bb9d and merged to `main` via PR #276 (`c509fc8`, 2026-10-08). Production registry enforcement is active at `bf440cb`; the predecessor's inactive-enforcement statement remains historical at `91fd64a`. Auto classification has its own typed Gateway route and usage receipt (§14.7); it adds no product dollar stop.
```

### H6 — hld-14-context-engine.md

OLD:
```text
# 14. Optional Context Engine and Plan 12 migration
```

NEW:
```text
# 14. Optional Context Engine and Plan 12 migration

**Edition scope.** Registry admission, enforcement, production construction and Auto statements explicitly refreshed below describe `bf440cb`. Other material retains its earlier provenance and is read with the controlling 2026-10-18 Plan 12.2 ordinary shipping amendment (`docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`). In particular, this edition does not replace the amendment's source/compaction policy, profiles, maintenance or historical evidence. ADR-024 controls interactive loop behavior; retained interim limits and legacy goal-loop descriptions are not current overrides.
```

### H6 — hld-14-context-engine.md

OLD:
```text
The estimator is a conservative verified byte-ratio estimate (`ceil(r * UTF8_bytes)` with non-negative overhead), not exact tokenization.
```

NEW:
```text
The estimator is the admitted route's byte-ratio profile (`ceil(r * UTF8_bytes)` with non-negative overhead), not exact tokenization. At `bf440cb`, ADR-025 permits an explicitly recorded per-model empirical admission with `verified: false`; `conservative-utf8` uses one token per UTF-8 byte of message/tool text, 16 tokens per message and 256 fixed. Those allowances are assumptions checked against each reply's reported input usage, not a proven universal token or framing bound.
```

### H6 — hld-14-context-engine.md

OLD:
```text
Unknown/expanding behavior remains ineligible.
```

NEW:
```text
Unknown route facts remain ineligible except for the explicit per-entry admissions ADR-025 permits. An empirical admission records its evidence, assumptions and limitations; it does not relabel unverified facts as verified. A first call can exceed its estimate or incur a charge before the reply check stops later calls to that model.
```

### H6 — hld-14-context-engine.md

OLD:
```text
The curated registry retains explicit role assignments, supported capabilities, exact endpoints, provenance and cheapest-per-token ordering among eligible assignments. Crossed prices need the accepted blend contract; no hidden scoring replaces policy. Contributor routes keep their filed disclosure. Haiku is excluded from the curated migration target. This does not claim active enforcement or a shipped-default change; normal bootstrap remains inactive until separately released. At 91fd64a: `ENFORCEMENT_ACTIVE = False` and `trusted_snapshot()` returns `None` (`optimus_model_policy/binding.py`); the shipped alias `claude-haiku` resolves to `anthropic/claude-haiku-4.5`. Auto classification, reviewer/depth behavior, savings-report surfaces and ADR-009's future recovery mechanism are not activated by this migration.
```

NEW:
```text
At `bf440cb`, trusted registry enforcement is active: `ENFORCEMENT_ACTIVE = True`, and `trusted_snapshot()` composes the packaged defaults plus the trusted operator override when present. The ordinary default planner is the cheapest eligible medium model, otherwise the cheapest eligible easy model; the shipped ordinary composition admits Haiku 5.5 as easy and summarizer. The old alias/default and exclusion statements describe earlier pins, not this composition.

Role assignments, capabilities, endpoint facts, provenance and eligible per-token price ordering remain explicit registry data. Crossed prices require the declared blend; Contributor routes retain their disclosure. ADR-025 replaces the one-model/code-pinned admission with each entry's independent `empirical_estimate` and `provider_family` evidence. A provider-family admission checks the reported provider, not an exact variant. The fixed `model-registry.yaml` in the trusted operator config root composes over the shipped policy; the operator's launch approval binds the resulting effective hash. Host and Gateway compose independently. Test profiles do not read that override.

Exception-route reply checks retain usage, finish, estimate and router-attempt requirements. ADR-026 accepts an empty pipeline or exactly one narrowly qualifying unflagged `guardrail` stage; any other stage or disallowed fact refuses. This does not prove unchanged content or data handling. A failed exception-route check stops that model for the Gateway's remaining life, without stopping every other model.

Auto classification is implemented in the separately approved opt-in composition (§14.7). Reviewer/depth behavior and savings-report surfaces remain outside that delivery. Auto's pre-dispatch route-ups do not implement automatic struggle escalation (#397).
```

### H6 — hld-14-context-engine.md

OLD:
```text
Production context enforcement remains inactive.
```

NEW:
```text
Production registry enforcement is active at `bf440cb`. Ordinary bootstrap constructs the Context Engine attachment when its registry has an eligible summarizer; the amendment remains controlling for the unrefreshed compaction and maintenance details.
```

### H6 — hld-14-context-engine.md

OLD:
```text
Complete product activation requires accepted measured policy, supported route/estimator/output facts, an exact qualified summary receipt, production-base effect/cancellation proof, trusted launch composition, finite repack behavior and real-client evidence. There is still no production constructor of ContextAttachment (verified at 91fd64a: no `src/` path constructs it, and its docstring records this); the reviewed named test composition supplies it only within its approved test process. Task 13 may use a separately approved ephemeral test composition through explicitly implemented and reviewed process-scoped dependency injection; that proves the named test configuration, not production bootstrap activation. v2.19 and the offline implementation were merged via PR #276; that merge activated nothing. Auto classification, the final reviewer step, the savings report and package publication keep their own implementation and activation status (§15).
```

NEW:
```text
The absence of a production `ContextAttachment` constructor was verified at `91fd64a`; it is not current at `bf440cb`. Ordinary bootstrap now composes the route policy and ordinary attachment, and Auto reuses that attachment machinery with the selected planning/answer model's limits. An eligible summarizer remains a prerequisite; without one the composition is absent-engine. The 2026-10-18 amendment supplies the unrefreshed Plan 12.2 contracts and historical evidence qualifications. Test-profile evidence remains evidence for its named composition, not authority for an ordinary or Auto launch.

Auto implementation, its pilot and its live slices have distinct evidence (§15). Luna's Auto admission is empirical; it does not discharge every historical Plan 12.2 route/estimator qualification obligation. The final reviewer step, savings report, automatic struggle escalation and package publication retain separate ownership and are not delivered by Auto.
```

### H7 — hld-14-context-engine.md

OLD:
```text
Once enforcement is active, capacity-specific text is selected only for INPUT_EXCEEDS_CAPACITY. The 80% request warning uses complete request size, while the separate storage notice preserves the source floor. A local Gateway dispatch reading is not proof of upstream delivery.
```

NEW:
```text
With enforcement active, capacity-specific text is selected only for INPUT_EXCEEDS_CAPACITY. The 80% request warning uses complete request size, while the separate storage notice preserves the source floor. A local Gateway dispatch reading is not proof of upstream delivery.

## 14.7 Auto mode: opt-in per-turn routing

**Launch boundary.** Only `OPTIMUS_AGENT_MODEL=auto` selects Auto. `--model auto` and an explicit model conflicting with that environment selection refuse. Auto composes packaged defaults, `auto_overlay.yaml`, then the trusted operator override. Approval binds both the effective registry literal and `_composition=auto`; ordinary and Auto approvals are not interchangeable, even if policy hashes coincide. A manually managed Auto Gateway is launched with `optimus-trust --workspace-root <workspace> run-gateway --auto`, under a durable approval binding that composition.

**Selection.** Before planning or answering, the host freezes a bounded sanitized prompt excerpt, captured mode, attachment metadata and the last committed routed tier. H applies its frozen rules; at rule confidence at least 0.8 it uses their answer, otherwise it asks the configured classifier through the Gateway. A valid answer below 0.95 moves up one tier, capped at complex. Missing/malformed confidence, abstention or classifier failure takes the failure rule, starting resolution at complex. These are routing heuristics, not calibrated safety guarantees.

The resolver selects the cheapest eligible unstopped model in the resulting task tier: easy, medium or complex. It tries another eligible model in the same role before moving upward when that role is unavailable; after exhausting tiers it tries the unstopped default planner, otherwise refuses recoverably without an answer call. The default fallback can be an easy or medium model. The chosen planning/answer model, route and context limits remain bound for the turn and its approved application. Maintenance retains the separately selected summarizer role.

**Shipped configuration.** Without an operator override, the Auto composition admits Luna then Haiku for easy, Gemini 3.8 Flash for medium/complex/escalation, Jev 1.14 as classifier and Haiku 5.5 as summarizer. These are registry assignments, not model-specific logic or a guarantee that a model can solve a task. The escalation role's assignment does not activate ADR-009 rung 2. The ordinary composition does not acquire the Auto overlay.

**Calls and visibility.** Jev uses authenticated `POST /v1/decisions` and the Gateway's System One adapter. The request has its own admission/reply checks and one upstream attempt with no resend. System One supplies no finish status or router-attempt/pipeline evidence; those absent checks remain disclosed. Every classifier attempt enters the turn's `classification` settlement stage; known costs remain charged and unknown costs remain unknown. An accounting-integrity failure refuses the turn instead of entering the routing-failure fallback. Cancellation prevents subsequent answer dispatch while retaining incurred receipts.

The host attempts one informational `Auto: <tier> → <model>` notice before the routed planning/answer work and emits a content-free `auto_routing` event at most once per admitted turn. The record distinguishes routed, refused, cancelled and abandoned outcomes and records whether the notice was delivered. Notice and telemetry failures are contained; neither is a durable-delivery guarantee. The Auto host shares one monotonically growing model-stop set across its resolver, runners and summarizer; the Gateway independently enforces its per-model stops.

**Authority and limits.** ADR-028 accepts ADR-007 with H; the frozen ADR-007 is unchanged. The accepted pilot does not establish population error rates below 5%, and its previous-tier signal was barely tested (#425). Savings depend on the configured models and workload. A different judge mechanism has separate ownership (#426); automatic struggle escalation remains #397. Auto grants no mutation authority and bypasses no exact-plan approval, guard, capacity or accounting control. §15 distinguishes source inspection, offline tests, pilot evidence and the three reported live slices.
```

### H8 — hld-15-capability-status.md

OLD:
```text
Agent-mode localized EDIT statements and the consequent execution-path corrections are at main `57e2069414fef32c6a6e4de42bd0dc7fb9f4f1ac` (2026-10-24), including the merged parser and failure-telemetry changes from PR #413 and PR #414. Other capabilities have not been reverified at this newer pin. EDIT implementation paths in the new row below are under `src/optimus/`. The 2026-10-18 Plan 12.2 ordinary shipping amendment (`docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`) still controls §14.2, §14.4–§14.6 and the §15 Context Engine and registry rows. It is not folded into this successor.
```

NEW:
```text
Agent-mode localized EDIT statements and their execution-path corrections retain main `57e2069414fef32c6a6e4de42bd0dc7fb9f4f1ac` provenance (2026-10-24, including PR #413 and PR #414). Registry, production-construction and Auto statements explicitly updated here describe main `bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1` (2026-10-27). Other rows retain their stated historical pins and have not been generally reverified at `bf440cb`.

The 2026-10-18 Plan 12.2 ordinary shipping amendment (`docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`) remains controlling for unrefreshed Plan 12.2 material, including source/compaction policy, profiles, maintenance and historical evidence. The refreshed registry/construction rows below supersede their inactive descriptions only. ADR-024 governs current interactive loop control; the retained loop rows and numerical limits are historical. Implementation presence, reported verification and authorization to launch remain separate.
```

### H8 — hld-15-capability-status.md

OLD:
```text
| Context Engine strategies, checkpoints and whole-turn packing (§14) | Implemented (`src/context_engine`, standard-library only) | Offline-verified at cf9bb9d (Windows 6830 passed, WSL 6641 passed, exit 0); unit tests at the pin | Production attachment inactive: no production constructor of `ContextAttachment` |
```

NEW:
```text
| Context Engine strategies, checkpoints and whole-turn packing (§14) | Engine implemented; production construction exists at `bf440cb` (`optimus/acp/bootstrap.py`, `context_attachment.py`) | Historical cf9bb9d suites retain their pins; Auto unit composition test exercises compaction. Other Plan 12.2 evidence remains under the amendment | Ordinary attachment when an eligible summarizer exists; Auto reuses it with per-model limits |
```

### H8 — hld-15-capability-status.md

OLD:
```text
| Trusted registry snapshot and complete-request capacity guard (§14.4) | Implemented (`optimus_model_policy`) | Offline-verified at cf9bb9d | Inactive: `ENFORCEMENT_ACTIVE = False`, `trusted_snapshot()` returns `None` |
```

NEW:
```text
| Trusted registry snapshot and complete-request capacity guard (§14.4) | Enforced at `bf440cb`; per-entry admission and trusted operator override (ADR-025), narrow guardrail-stage exception (ADR-026) | Code inspection; registry/override tests; PR #428 evidence below. Historical cf9bb9d results retain their pin | Active; approved effective hash required. Auto additionally binds its composition |
```

### H8 — hld-15-capability-status.md

OLD:
```text
| Luna route/estimator qualification, genuine summary-quality receipt, real-editor Task 13 (§14.6) | Prerequisites defined; profile A admits no model | Deferred, UNRUN (operator disposition 2026-10-08) | Held; owner Plan 12.2 (issue #237) |
```

NEW:
```text
| Luna admission in the shipped Auto composition (§14.7) | Implemented as configuration at `bf440cb`; `openai/fast`, `conservative-utf8`, explicit empirical limitations | Code inspection; overlay tests; one reported live easy slice at `df7dc3c` | Available in approved opt-in Auto launches; not added to shipped ordinary roles |
| Historical Plan 12.2 qualification, summary-quality and real-editor obligations (§14.6) | Retain their named contracts and composition identities | The 2026-10-08 deferred disposition is historical; consult the Plan 12.2 amendment and #237 for its evidence. Auto does not establish universal Luna estimator qualification | Separate from Luna's Auto admission; no historical receipt is promoted to this pin |
```

### H8 — hld-15-capability-status.md

OLD:
```text
| Auto classification and automatic escalation (§6, §10.D) | Proposed (ADR-007, status Proposed); not implemented | None | Deferred under existing owners |
```

NEW:
```text
| Auto classification and per-turn routing (§6, §10.D, §14.7) | Implemented at `bf440cb`; H accepted by ADR-028, which accepts ADR-007 | Unit tests, reported PR #428 suites/CI and three live acpx slices at `df7dc3c`; see Auto evidence below | Opt-in: `OPTIMUS_AGENT_MODEL=auto`, under an approved Auto composition |
| Automatic struggle escalation (ADR-009 rung 2) | Not implemented by Auto; pre-dispatch confidence/availability route-ups are distinct | No delivery evidence claimed here | Deferred under #397 |
```

### H8 — hld-15-capability-status.md

OLD:
```text
**EDIT evidence.**
```

NEW:
```text
**Auto evidence.** Source inspection for the refreshed statements is at main `bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1`. Named tests cover launch binding, per-turn routing, shared model stops, H, decisions, notices and records. `tests/unit/acp/test_auto_launch_end_to_end.py` drives the real configured server over NDJSON through the adapter and AgentRunner, with external dependencies replaced; it is unit composition evidence, not independent live ACP acceptance.

PR #428 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/428) reports the Windows full suite with coverage at `3420eb2`: 10,107 passed, 50 skipped, 101 deselected, 1 warning; required product coverage gates passed. That run predates the Linux test-isolation correction and merge of main. The PR also preserves the first Linux run's three test failures and the correction at `236a3c4`, plus two repository-layout failures while the merge index remained unmerged. These are not silently converted into final-head passes. At final PR head `df7dc3c52dbc64ec5d18d27e05766c1953715853`, guardrails run 40469959706 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40469959706) completed successfully. No workflow runs were returned for merge commit `bf440cb` during this authoring pass; no merge-commit CI pass or Windows rerun is inferred.

#395 comment 6437429914 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/395#issuecomment-6437429914) reports acpx 0.12.0 Agent-mode live slices at `df7dc3c`: easy to Luna, medium to Gemini, complex through Jev to Gemini; 3/3 passed, reported total USD 0.005858. The report identifies routing records, first-message notices, completed accounting, file outcomes and process cleanup. Haiku, easy's second model, was not exercised. Jev's dated resolved-model snapshot displayed as `unrecognized` in the Gateway log; the report distinguishes this diagnostic limitation from the accepted decision reply. These are reported PR-head results, not fresh runs or independent inspection of the external raw bundle. Its archival seal is identified in that repository-visible comment; the external folder is not an operating dependency.

The filed pilot evidence (https://github.com/vibhanshu-agarwal/optimus-cost-agent/tree/bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1/docs/sources/plan-12-4-auto-pilot) and ADR-028 record H's selection and limitations. Pilot acceptance is not a guarantee of population accuracy, task success or savings. Round 2 and the successor filing retain custody under #395; this evidence does not close the whole plan.

**EDIT evidence.**
```

### L2 — lld/10

OLD:
```text
| Model tier | ultra-cheap; cheap; review. Review role is dormant; use the trusted registry, not HAIKU/PRO aliases. |
```

NEW:
```text
| Registry price tier | ultra-cheap; cheap; review. These remain the registry's `Tier` values; they are not Auto's task classes. |
| Auto task tier / registry role | easy; medium; complex, mapped to the corresponding implementer roles. Other registry roles are escalation, summarizer, reviewer and classifier; reviewer remains dormant. An escalation assignment does not activate struggle escalation. |
```

### L3 — lld/11

OLD:
```text
After approved trusted policy activation, all branches obtain the eligible fixed model from the trusted role/route registry and obey its actual request capacity, with a total context ceiling of 262144 including one output reserve. Retire the old branch-specific 100000/150000/250000 token ceilings and HAIKU/PRO aliases. History strategy allocations and final input/output packing are separate. Auto classification and struggle escalation are not activated.
```

NEW:
```text
At `bf440cb`, trusted registry enforcement is active. Ordinary launches use a configured eligible fixed model; approved Auto launches classify and bind a planning/answer model per turn (§13.10). Both obey final complete-request capacity, with a planning/answer ceiling of 262144 including one output reserve and the admitted route's smaller bounds where applicable. Explicit empirical admission does not establish a universal token bound. Retire the old branch-specific 100000/150000/250000 token ceilings and HAIKU/PRO aliases. History strategy allocations and final packing remain separate. These retained scope/strategy prototypes do not implement H or determine its task tier. Automatic struggle escalation remains deferred under #397.
```

### L4 — lld/14

OLD:
```text
This figure does not activate Auto routing.
```

NEW:
```text
This figure abstracts lifecycle and approval; Auto's implemented opt-in selection is specified in §13.10. Selecting Auto does not bypass any mode or artifact-approval transition. Retained interim loop-limit labels are historical; ADR-024 governs current interactive loop control.
```

### L4 — lld/16

OLD:
```text
The retained pathway connects captured user intent/mode, explicit eligible model selection, mutation gating and telemetry through the Gateway boundary. Intent classification in the predecessor was a reserved capability; this successor does not activate Auto/classifier routing. Section 4A's revised pathway and state diagram preserve advisory ChatOnly, AwaitingApproval, Failed/replan, fitness and termination branches.
```

NEW:
```text
The retained pathway connects captured intent/mode, eligible model selection, mutation gating and telemetry through the Gateway boundary. At `bf440cb`, Auto/classifier routing exists in the separately approved opt-in composition (§13.10); these lifecycle and permission figures do not specify that classifier. Auto changes planning/answer model selection, not mutation authority. ChatOnly, AwaitingApproval and the applicable failure/fitness branches retain their execution boundaries; ADR-024 governs interactive loop recovery.
```

### L4 — lld/17

OLD:
```text
| Host selection | Explicit eligible role/model and trusted effective registry; Auto/Haiku triage removed |
```

NEW:
```text
| Host selection | Enforced trusted registry; configured fixed model ordinarily, or H and `AutoRouter` binding one eligible model per Auto turn (§13.10). The old hard-coded Haiku/Pro triage is not this mechanism |
```

### L4 — lld/17

OLD:
```text
This is the complete updated pathway. Existing lifecycle and mode-matrix sections remain. Attached test composition does not establish normal bootstrap activation; section 13 specifies the release prerequisites.
```

NEW:
```text
This table abstracts the planning/answer pathway. Auto's preceding classifier call and its separate accounting are specified in §13.10. Ordinary production construction exists at `bf440cb`; a test composition still proves only its own configuration. Existing mode and exact-approval boundaries remain. The Plan 12.2 amendment controls unrefreshed attachment details, and ADR-024 controls interactive loop behavior.
```

### L4 — lld/18

OLD:
```text
These descriptive strategies do not automatically activate Auto routing or override current three-round/30-minute/two-repeated-failure ACP limits. All obey final verified route capacity; HAIKU/PRO aliases and separate risk-tier context ceilings are retired.
```

NEW:
```text
These descriptive strategies do not select Auto. Auto is an independent opt-in launch composition (§13.10), and its task tiers are distinct from execution-strategy and rigor policy. The predecessor's three-round/30-minute/two-repeated-failure statement retains its historical pin; ADR-024 governs interactive loop control. Planning/answer work obeys final admitted route capacity, including explicit empirical-admission limitations; HAIKU/PRO aliases and separate risk-tier context ceilings remain retired.
```

### L5 — lld-13-context-integration.md

OLD:
```text
# 13. Context Engine, policy and cost integration contracts
```

NEW:
```text
# 13. Context Engine, policy and cost integration contracts

**Edition scope.** Registry admission, enforcement, production construction and Auto statements explicitly refreshed below describe `bf440cb`. Unrefreshed Plan 12.2 material retains its prior provenance and is read with the controlling 2026-10-18 ordinary shipping amendment (`docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`), including compaction, numeric policy, profiles, maintenance and historical evidence. The new §13.10 specifies Auto. ADR-024 controls interactive loop behavior; retained interim limits and legacy goal-loop descriptions do not override it.
```

### L5 — lld-13-context-integration.md

OLD:
```text
Supported production policy currently describes a verified conservative `ceil(r * UTF8_bytes)` profile with non-negative overhead.
```

NEW:
```text
Production policy uses the admitted route's conservative `ceil(r * UTF8_bytes)` profile with non-negative overhead. At `bf440cb`, ADR-025 also permits an explicitly recorded per-entry empirical admission whose estimator remains `verified: false`; its assumptions and per-reply checks do not establish a universal token or framing bound.
```

### L5 — lld-13-context-integration.md

OLD:
```text
Normal production bootstrap remains inactive at 91fd64a as at cf9bb9d: no production path constructs `ContextAttachment` (its docstring records this), `ENFORCEMENT_ACTIVE = False` and `trusted_snapshot()` returns `None`. Production activation requires, each with its own evidence and authority: an eligible route with verified estimator and output facts; a genuine summary-quality receipt; effect and cancellation evidence on the production base; trusted launch snapshot binding; bounded maintenance and repacking proof; and real-client evidence. Test-profile acceptance is not production bootstrap approval. At cf9bb9d the reviewed named test composition supplies explicit process-scoped construction through the real trusted entrypoint and passes attachment/route/receipt dependencies into AcpDuplexAdapter. GatewayModelPolicy is likewise mandatory for the test process. Normal bootstrap enforcement is inactive and the default maps to claude-haiku-4.5; production activation and default removal remain held. See test-composition-contract.md for profiles A/B and approval/hash binding.
```

NEW:
```text
At `bf440cb`, normal production bootstrap is implemented under active trusted registry enforcement. `build_configured_server` uses `trusted_snapshot()` and `ordinary_route_policy`, then `ordinary_attachment` when an eligible summarizer exists (`src/optimus/acp/bootstrap.py:267–320`; `src/optimus/acp/context_attachment.py:51–103`). `ordinary_attachment` constructs the plain ContextEngine and Gateway-backed maintenance; without an eligible summarizer it returns None. This is production construction, not a test-only constructor.

The ordinary default planner is the cheapest eligible medium model, otherwise the cheapest eligible easy model (`src/optimus/agent/defaults.py:19–29`). In the shipped ordinary policy that is Haiku 5.5; the former claude-haiku-4.5 alias is not the enforced default. Auto uses its separate composition and per-turn binding (§13.10). Historical test-profile evidence and approval identities stay attached to their named profiles; an ordinary or Auto launch does not inherit their authority. The amendment controls unrefreshed Plan 12.2 behavior and evidence; no historical pass is promoted to this pin.
```

### L5 — lld-13-context-integration.md

OLD:
```text
Per-role eligibility rejects verified window <262144 or maximum output below the role reserve (ROUTE_WINDOW_BELOW_CEILING / output-cap eligibility). It requires explicit assignment, capabilities, exact endpoint/quantization, verified window/output/parameter/estimator facts, and any required summary receipt/disclosure. Unknown route facts and unknown trusted snapshot mean zero upstream calls.
```

NEW:
```text
At `bf440cb`, eligibility requires explicit role assignment, capabilities, recorded endpoint/quantization and verified window/output facts, supported reasoning controls, the applicable reserve and any required summary receipt/disclosure. The window floor is 262144 for non-classifier roles and 8192 for classifier; the classifier remains subject to the validator's positive reserve requirement even though the decisions endpoint reserves no output (`src/optimus_model_policy/registry.py:98–117`; `src/optimus_model_policy/validation.py:80–170`).

ADR-025 permits two independent admission parts on each model entry: `empirical_estimate` admits its explicitly unverified empirical estimator; `provider_family` admits its recorded provider base slug while requiring the reply's provider name. Neither relaxes the other part's checks. `conservative-utf8` uses ratio 1, 16 tokens per message and 256 fixed, `verified: false`. Evidence, assumptions and limitations participate in the effective registry identity. A first call can exceed the estimate or be charged before reply validation stops later calls to that model.

The operator override is the regular file `model-registry.yaml` in the trusted operator config root. Ordinary composition applies it over defaults; Auto applies it over defaults plus the Auto overlay. Launch approval binds the resulting effective hash, and host/Gateway compose independently; test profiles never read the override (`src/optimus_model_policy/binding.py:111–170`; `src/optimus/acp/launch_gate.py:701–728`). Unknown facts outside those explicit admissions and an unknown trusted snapshot do not authorize upstream dispatch.

For completion replies on exception routes, retain usage/finish validation, reported input at most the estimate where empirically admitted, recorded-provider equality where family-admitted, and one router attempt. An empty pipeline passes; a nonempty pipeline passes only ADR-026's exact shape: one `guardrail`, one closed-facts record, `flagged` false, `detected` false or missing, `decision`/`action`/`guardrail_scope` missing and `verdict_conflict` false. Explicit nulls, wrong types, extra stages or other facts refuse. Acceptance proves neither unchanged content nor data handling. A failed check stops only that model for the Gateway's remaining life; stops cannot be cleared (`src/optimus_gateway/model_policy.py:87–101`, `:224–288`). Decisions have the distinct reply contract in §13.10 because System One does not supply completion finish/router facts.
```

### L6 — lld-13-context-integration.md

OLD:
```text
No run-gateway profile flag is needed.
```

NEW:
```text
No run-gateway profile flag is needed. That statement concerns the named test profiles; Auto's manually managed Gateway uses the separate `run-gateway --auto` option below.

## 13.10 Auto composition and per-turn routing

### 13.10.1 Selection and launch authority

`auto` is a composition selector, never an upstream model ID. Only `OPTIMUS_AGENT_MODEL=auto` selects it; `--model auto` and Auto combined with a different explicit `--model` refuse (`src/optimus/agent/defaults.py:32–42`, `:49–70`). Unsetting the variable, or selecting an eligible exact model ID, returns to ordinary fixed-model selection.

`auto_snapshot()` composes packaged defaults, `auto_overlay.yaml`, then the trusted operator override. `trusted_snapshot()` remains ordinary composition. The security literals bind both `_model_registry` and `_composition=auto`; an ordinary approval cannot authorize Auto, or conversely, even if hashes coincide. Auto and a named test profile are mutually exclusive (`src/optimus_model_policy/binding.py:73–84`, `:143–175`; `src/optimus/acp/launch_gate.py:701–728`).

After launch authorization, `compose_auto_composition` recomposes and compares the approved literal and composition. Startup validates the default planner and classifier before services start. A missing eligible classifier or one requiring Contributor disclosure refuses; the decisions route cannot verify that disclosure (`src/optimus/acp/auto_composition.py:212–236`; `src/optimus/acp/__main__.py:592–601`).

The auto-started Gateway receives `--auto-composition` and any trusted override path, composes independently and verifies the signed registry binding. A manually managed Gateway uses `optimus-trust --workspace-root <workspace> run-gateway --auto`. That command requires a durable workspace approval binding the registry literal and composition; it cannot authorize a changed override merely by signing it (`src/optimus/acp/local_infra.py:523–536`; `src/optimus_gateway/__main__.py:107–170`; `src/optimus/acp/launch_approval_cli.py:1068–1101`, `:1150–1155`).

The shipped overlay's effective composition, without an operator override, is the approved `f11dc3ab…`: easy Luna then Haiku; medium/complex/escalation Gemini 3.8 Flash; classifier Jev 1.14; summarizer Haiku 5.5. Price ordering is computed from eligible assignments, not YAML list order. Model IDs, prices, endpoints and admission evidence are configuration; no per-model task-success guarantee follows. Ordinary roles do not gain the overlay. The approved overlay retains historical ADR-027 evidence text inside its hash; its decision record is now ADR-028.

### 13.10.2 Frozen input and H

Before classification awaits, the adapter captures the sanitized prompt, turn mode, attachment metadata and last committed routed tier. `ClassifierInput` (`auto-input-v1`) serializes a prompt excerpt of at most 4096 UTF-8 bytes with a truncation flag, CHAT/AGENT mode, attachment count, size bucket, up to five sorted extensions and previous tier. It carries neither full history nor attachment contents. The previous tier is published from committed completed/rejected routed turns, not failed or cancelled work (`src/optimus/agent/auto_contract.py:26–67`, `:86–122`; `src/optimus/acp/spec.py:1787–1807`, `:2144–2148`).

`HybridClassifier` implements H, accepted by ADR-028:
- score the frozen input using the pilot's rules and cut points 0.5 and 4.5;
- at rule confidence ≥0.8, use the rules' answer without a classifier call;
- otherwise ask the configured classifier once using the frozen `choice` question;
- apply the final confidence threshold 0.95 to a valid answer: below it, move up one tier, capped at complex.

Confidence must be a finite non-boolean number in [0,1]. Missing/malformed confidence is abstention, not a confident answer. Abstention, invalid answer, classifier timeout/error or a stopped classifier yields no usable tier; resolution starts at complex. Accounting-integrity failure and cancellation do not take that routing fallback (`src/optimus/acp/auto_hybrid.py:52–64`, `:104–130`, `:157–186`; `src/optimus/acp/spec.py:1805–1841`).

The host fits the complete typed decision request to its bound by shrinking only the prompt excerpt; if no excerpt fits, no decision is sent (`src/optimus/acp/auto_hybrid.py:188–203`). The thresholds are the accepted mechanism, not calibrated probabilities or proof of task suitability.

### 13.10.3 Resolver, binding and stops

`AutoRouter` is constructed once per launch with the approved snapshot, eligible route policies, per-model context limits, classifier and one monotonically growing host `StopSet`. `resolve` selects the cheapest eligible unstopped model of the requested task tier. It falls through stopped models within that role, then unavailable tiers upward, then tries the unstopped default planner. The last fallback can be an easy or medium model. With none available it raises `AUTO_NO_ROUTABLE_MODEL`; the adapter refuses recoverably before any planning/answer call (`src/optimus/acp/auto_composition.py:239–300`).

The adapter captures the chosen route binder and rebinds the attached turn's limits before planning/answer work. The selected planning/answer model remains fixed through that turn and approved application; applying an old plan does not classify it again. The summarizer remains the separately eligible summarizer, not whichever implementer H selected (`src/optimus/acp/auto_composition.py:303–362`; `src/optimus/acp/spec.py:1844–1851`; `tests/unit/acp/test_auto_turn_routing.py:174`).

Every Auto runner and summarizer shares the launch's host stop set with the resolver. Proven exception-route stops are retained even if receipt reporting raises; the Gateway independently keeps permanent per-model stops for its process life. Ordinary failures do not automatically stop all models. No stop is cleared as a retry-to-green mechanism (`src/optimus/agent/runner.py:1067–1078`; `src/optimus/context/maintenance.py:291–320`; `src/optimus_gateway/model_policy.py:87–101`).

These confidence/availability route-ups happen before planning/answer dispatch. They do not switch models mid-turn or implement ADR-009 struggle escalation. The configured escalation role remains distinct; rung 2 is owned by #397.

### 13.10.4 Gateway decisions contract

Authenticated `POST /v1/decisions` accepts `{model, state, questions, route_binding}`. `model` is an exact registry ID, `state` an object and `questions` a nonempty typed question object; supported question kinds are `choice`, `noul` and `score`. Auto H uses its frozen `tier` choice question. Missing enforcement, absent/mismatched binding, ineligible/stopped model, unsupported disclosure or capacity overflow refuses before upstream dispatch (`src/optimus_gateway/decisions.py:32–83`).

`admit_decision` requires the approved effective hash, classifier eligibility and the route estimator. The complete canonical state/questions estimate must fit `min(8192, route windows)`, inclusive. Decisions reserve zero output tokens; the registry's positive classifier reserve remains a validation requirement. The route sends approved provider controls, including disabled fallback (`src/optimus_gateway/model_policy.py:291–341`).

The handler makes exactly one upstream attempt through `create_decision_once`, which posts to the aggregator's `/systemone` endpoint. There is no resend, including after rejection or uncertain delivery. Attempt outcomes and available usage are retained. The parser requires matching typed answers, valid choice/range values, IDs/model and nonnegative finite reported usage/cost; malformed choice types become unreadable uncertain replies (`src/optimus_gateway/decisions.py:85–117`; `src/optimus_gateway/upstream_client.py:303–342`, `:362–404`).

`check_decision_reply` accepts the requested model ID or its dated snapshot. An admitted provider-family route requires its recorded provider name; an empirically admitted route requires reported input no greater than the admitted estimate. System One supplies no finish status, router-attempt count or pipeline facts, so those completion-route checks cannot run here. The limitation is recorded in the classifier's admission data. A billed reply refusal preserves usage and stops that exception model; uncertain delivery also stops it. A proven rejected attempt does not acquire an invented charge (`src/optimus_gateway/model_policy.py:344–373`; `src/optimus_gateway/decisions.py:93–116`; `src/optimus_model_policy/auto_overlay.yaml:80–98`).

### 13.10.5 Classification settlement and cancellation

The classifier call runs in the turn's worker under its registered Gateway dispatch lease. A refused lease sends nothing. Every attributable physical attempt is offered as a `StageReceipt` with `stage="classification"` to that turn's existing settlement; receipt and integrity failures take precedence over the routing-failure rule. Known costs remain charged; unknown accounting stays unknown, including after teardown. Late receipts do not authorize an answer (`src/optimus/acp/auto_hybrid.py:205–285`; `src/optimus/usage/turn_settlement.py:38–39`).

The adapter refuses an accounting-integrity failure as `ACCOUNTING_INTEGRITY`. Cancellation or abandonment after classification prevents subsequent planning/answer dispatch and follows the existing turn settlement/finalization path. Classification is not part of the context meter's planning/answer input reading and adds no product monetary ceiling.

### 13.10.6 Notice and routing record

For a routed turn the host attempts one `Auto: <tier> → <model>` message before planning/answer work, with reasons for confidence route-up, unavailable tiers, classifier failure or default fallback. It requests confirmed flushing, records whether delivery succeeded and contains notification failure. The notice is informational and is not stored in canonical history (`src/optimus/acp/auto_composition.py:160–171`; `src/optimus/acp/spec.py:1876–1888`).

The `auto_routing` event records arm H, disposition (`routed`, `refused`, `cancelled`, `abandoned`), source of the answer, predicted/classified/final tier, confidence band, route-ups, fallback, selected model/role, classifier-attempt outcome, reason and notice delivery. Unknown fields remain null. It contains no prompt, contract, answer text or raw confidence. The adapter guards emission at most once per admitted turn, with first write winning; telemetry failure is contained, so durable delivery is not guaranteed (`src/optimus/acp/auto_composition.py:174–203`; `src/optimus/acp/spec.py:1890–1932`; `src/optimus/telemetry/events.py:569–588`).

The receipt owns the classifier's actual cost; the routing record is a projection, not a second debit. Auto grants no tool permission or mutation authority. Exact artifact approval, mode enforcement, request capacity, disclosure and existing guards remain required.

### 13.10.7 Evidence and limitations

§14 separates source inspection, unit composition tests, reported suites/CI, the classifier pilot and real acpx slices. ADR-028 accepts H with its limitations: the measured 4.7% rates do not establish population rates below 5%; the previous-tier signal is barely tested (#425); routing savings depend on models/workload. A different judge mechanism is separately owned by #426. Round 2 remains under #395; neither Auto's shipment nor these successor documents declare the whole plan complete.
```

### L7 — lld-14-capability-status.md

OLD:
```text
Agent-mode EDIT statements and the consequent execution-path corrections are at main `57e2069414fef32c6a6e4de42bd0dc7fb9f4f1ac` (2026-10-24), including the merged parser and failure-telemetry changes from PR #413 and PR #414. Other contracts have not been reverified at this newer pin. EDIT implementation paths in the new row below are under `src/optimus/`. The 2026-10-18 Plan 12.2 ordinary shipping amendment (`docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`) still supplies the controlling newer Plan 12.2 statements for §13 and the §14 status rows. It is not folded into this successor.
```

NEW:
```text
Agent-mode EDIT and its execution-path corrections retain main `57e2069414fef32c6a6e4de42bd0dc7fb9f4f1ac` provenance (2026-10-24, including PR #413 and PR #414). Registry, production-construction and Auto statements explicitly updated here describe main `bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1` (2026-10-27). Other contracts retain their historical pins and have not been generally reverified at `bf440cb`.

The 2026-10-18 Plan 12.2 ordinary shipping amendment (`docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`) remains controlling for unrefreshed §13/§14 material, including compaction, profiles, maintenance and historical evidence. The refreshed registry/construction rows below supersede their inactive descriptions only. ADR-024 governs current interactive loop control; retained loop types and numerical bounds are historical. Source presence, reported verification and launch authorization remain separate.
```

### L7 — lld-14-capability-status.md

OLD:
```text
| Retry policy: host initial attempt plus three retries; enabled Gateway at most two physical attempts (§4A, §6) | Implemented (`optimus/retry/policy.py` `max_retries = 3`; `MAX_ROUTE_ATTEMPTS = 2` in `optimus_model_policy/binding.py`) | Unit tests | Host policy active; the two-attempt rule applies once enforcement is active |
```

NEW:
```text
| Completion-request retry policy (§4A, §6, §13.4) | Existing host policy; enforced Gateway limit `MAX_ROUTE_ATTEMPTS = 2`, with the restricted resend conditions in §13.4 | Historical tests retain their pins; source limit inspected at `bf440cb` | Enforcement active. Auto's separate decisions route permits one upstream attempt and no resend |
```

### L7 — lld-14-capability-status.md

OLD:
```text
| `make_history_snapshot`, `HistoryRevision`, `ContextEngine.prepare_view`, `StrategyParameters`, `ViewLimits` (§13.1) | Implemented (`optimus/context/adapter.py`, `src/context_engine`) | Offline-verified at cf9bb9d; unit tests at the pin | Engine usable; production attachment inactive |
| Whole-turn maintenance, checkpoints, `maintenance_calls_remaining`, `summary_max_bytes` (§13.2) | Implemented (`context_engine/engine.py`, `checkpoints.py`, `contracts.py`) | Offline-verified at cf9bb9d | Inactive in production |
| `ContextAttachment`, `AttachedTurn`, `probe_floor`, `max_repacks` (§13.3) | Implemented (`optimus/context/assembly.py`); no production constructor of `ContextAttachment` | Offline-verified at cf9bb9d; named test composition only | Inactive |
```

NEW:
```text
| `make_history_snapshot`, `HistoryRevision`, `ContextEngine.prepare_view`, `StrategyParameters`, `ViewLimits` (§13.1) | Implemented; production attachment is composed at `bf440cb` | Historical cf9bb9d evidence retains its pin; other Plan 12.2 evidence remains under the amendment | Available through ordinary/Auto attachment when an eligible summarizer exists |
| Whole-turn maintenance and checkpoints (§13.2) | Existing engine and host maintenance reused by Auto; no new compaction strategy | Historical cf9bb9d evidence; Auto unit composition test exercises compaction | Production construction exists; unrefreshed policy/details remain under the amendment |
| `ContextAttachment`, `AttachedTurn`, `probe_floor`, `max_repacks` (§13.3) | Production constructor in `optimus/acp/context_attachment.py`; Auto supplies selected-model limits | Code inspection at `bf440cb`; unit composition evidence, separately qualified below | Ordinary/Auto construction; no test-profile authority is inherited |
```

### L7 — lld-14-capability-status.md

OLD:
```text
| Trusted `RegistrySnapshot`, `ROUTE_WINDOW_BELOW_CEILING`, final capacity guard (§13.4) | Implemented (`optimus_model_policy`) | Offline-verified at cf9bb9d | Inactive: `ENFORCEMENT_ACTIVE = False`, `trusted_snapshot()` is `None` |
```

NEW:
```text
| Trusted `RegistrySnapshot`, eligibility and final capacity guard (§13.4) | Enforcement active at `bf440cb`; per-entry admissions and trusted operator override (ADR-025); ADR-026 guardrail predicate | Code inspection; registry/override tests; reported PR #428 evidence below | Active under approved effective hash; classifier uses its separate 8192-token request bound |
```

### L7 — lld-14-capability-status.md

OLD:
```text
| Package extraction and publication of `context_engine` as a wheel (§13.1) | Buildable; independent wheel proof at cc6959b carried to cf9bb9d over unchanged inputs | Historical proof only; not rebuilt at the pin | Not published |
```

NEW:
```text
| Auto composition and launch binding (§13.10.1) | `auto_snapshot`, `compose_auto_composition`, `_model_registry` and `_composition`; independent Gateway composition | Launch/override unit tests; reported PR #428 CI | Opt-in Auto only; separate approved composition required |
| `AutoRouter`, frozen input and one host stop set per launch (§13.10.2–§13.10.3) | Implemented in `agent/auto_contract.py`, `acp/auto_composition.py`, adapter and runner | Routing/stop tests; real configured-server unit composition test | Active in approved Auto launches; planning/answer model fixed per turn |
| H judge (§13.10.2) | `acp/auto_hybrid.py`; rules then configured Jev; confidence validation and failure rule | Pilot accepted by ADR-028; unit tests; reported live complex slice at `df7dc3c` | Auto's shipped judge; no struggle-escalation implementation |
| `POST /v1/decisions`, `admit_decision`, `check_decision_reply` (§13.10.4) | Authenticated typed route; one upstream attempt; distinct System One limitations | Gateway decision/parser tests; reported live complex slice | Requires enforced classifier-eligible registry and exact binding |
| `classification` receipts and turn settlement (§13.10.5) | Registered dispatch lease; receipt-first accounting and integrity refusal | Classifier/accounting/cancellation tests; composition test | Active for Auto classifier attempts; no fabricated zero or duplicate debit |
| Auto notice and `auto_routing` event (§13.10.6) | Informational flushed-notice attempt; content-free first-write routing record | Notice/cancellation/concurrency tests; three reported live slices | Auto turns; notification/telemetry failures contained, no durable-delivery guarantee |
| `optimus-trust run-gateway --auto` (§13.10.1) | CLI flag; durable workspace approval must bind registry and composition | Launch CLI unit tests | Supported for a manually managed Auto Gateway |
| Package extraction and publication of `context_engine` as a wheel (§13.1) | Buildable; independent wheel proof at cc6959b carried to cf9bb9d over unchanged inputs | Historical proof only; not rebuilt at the pin | Not published |
```

### L7 — lld-14-capability-status.md

OLD:
```text
**EDIT evidence.**
```

NEW:
```text
**Auto evidence.** The refreshed implementation statements use main `bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1`. Unit sources cover composition/approval, override, routing, model stops, H, decisions, notices, accounting and cancellation. `tests/unit/acp/test_auto_launch_end_to_end.py:134–186` drives the real configured server over NDJSON through the adapter and AgentRunner, replacing external dependencies. Its stage-set assertions establish stage presence, not exact receipt counts or total costs. It is unit composition evidence, not an independently authored live ACP client.

PR #428 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/428) reports one Windows full suite with coverage at `3420eb2`: 10,107 passed, 50 skipped, 101 deselected, 1 warning; required product gates passed. This is not a Windows full-suite result for the later Linux test-isolation correction or merge of main. Preserve the PR's first Linux run with three failures, its correction at `236a3c4`, and the two repository-layout failures observed with unmerged index entries. At final PR head `df7dc3c52dbc64ec5d18d27e05766c1953715853`, guardrails run 40469959706 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/40469959706) completed successfully. No workflow runs were returned for merge `bf440cb` during this authoring pass; no post-merge CI pass is inferred.

#395 comment 6437429914 (https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/395#issuecomment-6437429914) reports real acpx 0.12.0 Agent-mode live slices at `df7dc3c`: easy through rules to Luna, medium through rules to Gemini, complex through Jev `/v1/decisions` to Gemini; 3/3 passed, reported total USD 0.005858. The comment records notices, routing records, completed accounting, file outcomes and cleanup. Haiku fallback was not exercised. It also records Jev's dated snapshot displaying as `unrecognized` in the Gateway log while the decision reply check accepted it. These are reported PR-head results; the external raw bundle was not independently inspected for this authoring pass and is archival provenance, not a project dependency.

The filed pilot bundle and ADR-028 retain the selected judge's evidence and limitations. They do not prove population error rates below 5%, universal task suitability or savings. Round 2 and the document successor retain custody under #395; this section does not close the whole plan.

**EDIT evidence.**
```

### L7 — lld-14-capability-status.md

OLD:
```text
**Activation prerequisites, restated.** Production attachment of the Context Engine requires, each with its own evidence and authority: an eligible route with verified estimator, output-cap and finish facts; a genuine summary-quality receipt; effect and cancellation evidence on the production base; trusted launch snapshot binding; bounded maintenance and repacking proof; and real-client evidence. Test-profile acceptance is not production bootstrap approval. Unimplemented integration points remain future work under their existing owners (Plan 12.2, issue #237); this edition commissions none of them.
```

NEW:
```text
**Activation and evidence boundaries.** The predecessor's production-absence checklist is historical; production construction and registry enforcement exist at `bf440cb`. The Plan 12.2 amendment remains controlling for unrefreshed qualification and evidence statements. Empirical admission remains explicitly unverified and retains its first-call risk. Auto requires its own approved registry/composition and launch prerequisites (§13.10); neither old test-profile acceptance nor this document authorizes a launch, paid call or service change. Reviewer behavior, savings reporting and automatic struggle escalation retain their separate owners.
```

## docs/README.md

### D1 / H1 — HLD index row

OLD:
```text
| [Architecture (HLD) v2.21](Optimus-Cost-Agent-Architecture-v2.21.pdf) | High-level design; Agent-mode localized EDIT and consequent execution-path corrections at `57e2069` (2026-10-24); carried statements and baseline status rows retain `91fd64a` provenance. The [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) still controls §14.2, §14.4–§14.6 and the §15 Context Engine and registry rows |
```

NEW:
```text
| [Architecture (HLD) v2.22](Optimus-Cost-Agent-Architecture-v2.22.pdf) | High-level design; opt-in Auto mode and its enforced-registry prerequisites at `bf440cb` (2026-10-27). Carried baseline and EDIT statements retain their earlier pins. The [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) still controls unrefreshed Plan 12.2 material; ADR-024 governs interactive loop control |
```

### D2 / L1 — LLD index row

OLD:
```text
| [LLD v2.44](Optimus-Cost-Agent-LLD-v2.44.pdf) | Low-level design; Agent-mode directive plan and localized EDIT (§4B), with consequent execution-path corrections at `57e2069` (2026-10-24); carried statements and baseline status rows retain `91fd64a` provenance. The [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) still supplies the controlling newer Plan 12.2 statements for §13 and the §14 status rows |
```

NEW:
```text
| [LLD v2.45](Optimus-Cost-Agent-LLD-v2.45.pdf) | Low-level design; Auto composition, H, decisions, routing/binding, stops, settlement and visibility (§13.10), with registry/construction corrections at `bf440cb` (2026-10-27). Prior baseline/EDIT pins remain. The [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) controls unrefreshed material; ADR-024 governs interactive loop control |
```

### D3 — Amendment scope in the index

OLD:
```text
| [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) | Scoped successor amendment for the Plan 12.2 ordinary shipping candidate: the controlling newer HLD, LLD, Guardrails, evidence and roadmap statements; the 2026-10-15 correction package below stays unchanged |
```

NEW:
```text
| [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) | Filed 2026-10-18 Plan 12.2 statements and historical evidence. HLD v2.22 / LLD v2.45 refresh registry, production-construction and Auto statements; this amendment remains controlling for their unrefreshed Plan 12.2 material and retains its Guardrails/evidence/roadmap scope. The frozen amendment and 2026-10-15 correction sources stay unchanged |
```

### D4 — Successor sources and predecessor provenance

OLD:
```text
| [Agent-mode localized EDIT successor sources](sources/agent-localized-edit/) | Sources, replaced page bodies, authoring driver and validation record for HLD v2.21 and LLD v2.44; preserves the mixed provenance and the separate Plan 12.2 ordinary shipping amendment |
```

NEW:
```text
| [Plan 12.4 Auto-mode successor sources](sources/plan-12-4-auto-mode/) | Codex's replacement text, assembled baseline-keyed sources and filing validation for HLD v2.22 and LLD v2.45; scoped to Auto and its registry prerequisites at `bf440cb` |
| [Agent-mode localized EDIT successor sources](sources/agent-localized-edit/) | Preserved predecessor sources and validation for HLD v2.21 and LLD v2.44; their baseline-keyed page bodies are the inputs to the Auto successor |
```

### D5 — ADR-023 index qualification

OLD:
```text
| [ADR-023: Plan 12.2 shipped admission and default planner](decisions/ADR-023-plan12-shipped-empirical-admission-and-default-planner.md) | One exact-snapshot empirical admission exception for Haiku 5.5 (`verified: false`) and the medium-then-easy default planner; operator policy approval recorded; ships with the Plan 12.2 delivery merge, and the ordinary proof is tracked in #237 |
```

NEW:
```text
| [ADR-023: Plan 12.2 shipped admission and default planner](decisions/ADR-023-plan12-shipped-empirical-admission-and-default-planner.md) | Historical exact-snapshot Haiku 5.5 empirical admission (`verified: false`) and the medium-then-easy default planner. ADR-025 supersedes the one-hash/one-model admission mechanism with per-entry evidence and the trusted operator override; ADR-023's other decisions and residuals remain |
```

### D6 — Plan 12.4 decision-record number

OLD:
```text
| [Plan 12.4 v9: Auto mode](superpowers/plans/2026-10-23-plan-12-4-auto-mode_v9.md) | Fixed tiers with models as configuration; the classifier pilot selected H, the rules then Jev (ADR-027); opt-in per-turn tier routing; round 2, a challenger round on fresh data. v6, v7 and v8 are in `archive/` |
```

NEW:
```text
| [Plan 12.4 v9: Auto mode](superpowers/plans/2026-10-23-plan-12-4-auto-mode_v9.md) | Fixed tiers with models as configuration; H, the rules then Jev, accepted by ADR-028 (filed as ADR-027 before the merge-time renumbering); opt-in per-turn routing and a separate round 2. Earlier editions are in `archive/`; #395 owns status and next gates |
```

### R1 — Root README.md documentation table: HLD

OLD:
```text
| [docs/Optimus-Cost-Agent-Architecture-v2.21.pdf](docs/Optimus-Cost-Agent-Architecture-v2.21.pdf) | High-level design |
```

NEW:
```text
| [docs/Optimus-Cost-Agent-Architecture-v2.22.pdf](docs/Optimus-Cost-Agent-Architecture-v2.22.pdf) | High-level design; scoped Auto/registry successor at `bf440cb` |
```

### R2 — Root README.md documentation table: LLD

OLD:
```text
| [docs/Optimus-Cost-Agent-LLD-v2.44.pdf](docs/Optimus-Cost-Agent-LLD-v2.44.pdf) | Low-level design |
```

NEW:
```text
| [docs/Optimus-Cost-Agent-LLD-v2.45.pdf](docs/Optimus-Cost-Agent-LLD-v2.45.pdf) | Low-level design; Auto composition and routing contracts at `bf440cb` |
```

## Author notes

- **r2 (2026-10-27):** Reviewed draft-1/draft-1b, the assembled sources, page maps and both tools; fixed F1 by changing only the seven Markdown links in rendered NEW text to label (URL), preserving their labels/URLs, all OLD blocks, covers and build strings. Source reconstruction, ordered normalized PDF text, native carry bodies and recorded hashes matched r1; r2 still requires a filing rebuild and render check.
- **D1 ruling: (a).** Author the Plan 12.4 successor together with the registry facts Auto rests on: active trusted enforcement and production construction, ADR-025's per-entry admission/operator override, ADR-026's narrow pipeline exception, and ADR-007 as accepted by ADR-028. Leaving inactive-enforcement rows beside active Auto would be contradictory. A full Plan 12.2/12.3 refresh is outside this instruction. The amendment remains controlling for unrefreshed compaction, numeric policy, profiles, maintenance, Guardrails and historical evidence. Brief ADR-024 qualifications prevent retained loop text from posing as current policy; they do not reproduce or redesign Plan 12.3.
- **Authority:** the operator's 2026-10-27 instruction is reproduced verbatim on both covers. It releases this text and Claude's local filing, including `SKIP=check-added-large-files` for these PDFs. Publication to main requires separate operator approval. The exemption is not authority to skip other hooks or run paid/live work. `LOCAL FILING - NOT ACTIVATED` describes the document filing; it does not imply the pinned product's Auto feature is disabled.
- **Source and tree identity:** inspected HEAD was `bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1`, branch `agent/claude/plan12-4-design-docs`, at the requested worktree. Its parents match `8713dcbfbc05f9372619dfe655f83b247dc3751a` and `df7dc3c52dbc64ec5d18d27e05766c1953715853`. No tracked changes were present. Git reported untracked `.claude/settings.local.json` and inability to read the user's global ignore file; that local file was not read or changed. Final HEAD/status matched the initial observations.
- **Predecessor custody:** read `docs/sources/agent-localized-edit/README.md`, `validation-record.md`, both covers, `sources/successor-edits.md`, the baseline-keyed `page-updates.json`, and all four appended chapter sources. Independently hashed the current predecessor PDFs and both archived native baselines; all four match the cover identities. The predecessor source bundle's narrative contains older pins; its actual assembled source text, not that narrative or extracted PDF text, supplies every OLD.
- **Mechanical anchors:** all 48 OLD blocks above were checked in memory for exactly one occurrence in their respective predecessor source or README. There are 40 document-body blocks and eight README blocks. Page keys are native-baseline keys, not rendered successor page numbers. No source assembly, PDF build or write was performed. Claude must retain sequential uniqueness assertions in the new assembler; the predecessor assembler's hard-coded 23-block count and paths are not the new build contract.
- **Filing destination:** `docs/sources/plan-12-4-auto-mode/` is the selected new assembly destination, not a claim that this folder already exists at the inspected pin. The D4 index row applies when Claude assembles that bundle and its validation record. Preserve the predecessor source bundle. Move v2.21/v2.44 PDFs unchanged to `docs/archive/` during authorized filing; use the existing document-discovery mechanism for references.
- **Inventory corrections:** the model-tier table is `lld/10`, not `lld/11` or `lld/12`. No Auto statement appears in `lld/12`, so its retained path-containment prototype is unchanged. The actual registry price-tier enum still contains `ultra-cheap`, `cheap`, `review`; replacing that enum with task tiers would be false. The successor adds the separate easy/medium/complex task-tier contract.
- **Additional enforcement drift checked:** `hld/6`, `hld/10` and `hld/11` also contained inactive-enforcement statements. These are corrected or explicitly qualified. The HLD governance figure's fixed-model wording is updated. The ordinary/Auto constructor descriptions and capability rows are refreshed because the old absence claims would conflict with the routing composition. Other baseline facts are not silently re-pinned.
- **Native-only pages:** no native-only baseline page is edited or assigned invented source. The adjacent replaced lifecycle/strategy pages qualify the inherited model/loop diagrams, and the covers state the historical provenance and governing ADR-024 boundary. The earlier native §8 qualification for EDIT remains unchanged.
- **Registry references:** `src/optimus_model_policy/binding.py:73–84` establishes enforcement/composition literals; `:111–170` establishes the fixed override, ordinary composition and Auto composition. `src/optimus_model_policy/registry.py:92–117` establishes price tiers, roles, dormant reviewer and classifier bound; `:306–353` establishes estimator/admission shapes. `src/optimus_model_policy/validation.py:80–170` establishes route, reserve, estimator and summarizer eligibility; `:213–269` establishes price ordering and eligible selection. `src/optimus_model_policy/experimental.py:1–25`, `:44–75` establishes per-entry admission and that retained hashes are review pins, not admission keys. `src/optimus_model_policy/defaults.yaml:9–30`, `:35–75` establishes the ordinary Haiku entry, empirical estimators and summary-receipt scope.
- **Configuration and defaults:** `src/optimus/agent/defaults.py:19–42`, `:49–75` establishes medium-then-easy default resolution, exact eligible IDs and environment-only Auto selection. `src/optimus_model_policy/auto_overlay.yaml:23–106` establishes Gemini/Luna/Jev entries, empirical/family limitations and Auto assignments. `tests/unit/model_policy/test_auto_overlay.py:27–50`, `:63–74` checks the resulting eligible order, separate summarizer and unchanged ordinary assignments. These tests were inspected, not executed. The complete Auto hash is present at `tests/unit/acp/test_auto_launch_composition.py:46`; the approval is recorded in Plan v9 and the pilot bundle.
- **Launch references:** `src/optimus/acp/launch_gate.py:701–728` establishes registry/composition/profile binding and override exclusion for test profiles. `src/optimus/acp/auto_composition.py:212–236` establishes classifier/default checks and approved recomposition. `src/optimus/acp/__main__.py:592–610` establishes validation before services. `src/optimus/acp/local_infra.py:523–536` establishes child flags. `src/optimus_gateway/__main__.py:107–170` establishes independent composition and the manifest-verification path. `src/optimus/acp/launch_approval_cli.py:195–210`, `:1068–1101`, `:1150–1155` establishes `run-gateway --auto`, its durable approval check and child composition flag.
- **Production construction and per-turn binding:** `src/optimus/acp/bootstrap.py:178–189`, `:267–335`; `src/optimus/acp/context_attachment.py:44–103`; `src/optimus/acp/auto_composition.py:239–362`; `src/optimus/acp/spec.py:1763–1851`. The summarizer remains independently selected; “one model per turn” means planning/answer requests, not every model call including maintenance/classification. `tests/unit/acp/test_auto_turn_routing.py:174` checks approved application using the selected model.
- **Classifier input and H:** `src/optimus/agent/auto_contract.py:26–67`, `:86–122`; `src/optimus/acp/auto_hybrid.py:52–64`, `:104–130`, `:157–203`; `src/optimus/acp/spec.py:1787–1841`, `:2144–2148`. Valid low confidence moves up once; invalid/missing confidence yields abstention and resolution at complex. The resolver does not apply confidence route-up a second time. Default fallback after exhausted tiers can route to an easy/medium default; it is not guaranteed to remain at complex.
- **Stops and accounting:** `src/optimus/acp/auto_composition.py:79–92`, `:261–294`, `:332–361`; `src/optimus/acp/auto_hybrid.py:205–285`; `src/optimus/agent/runner.py:1067–1078`; `src/optimus/context/maintenance.py:291–320`; `src/optimus/usage/turn_settlement.py:38–39`; `src/optimus_gateway/model_policy.py:87–101`. The shared host stop set and independent Gateway stop map are separate process-local structures. Accounting-integrity failure is not a classifier-failure fallback.
- **Decisions and guardrail references:** `src/optimus_gateway/server.py:95–110`, `:157–158`; `src/optimus_gateway/decisions.py:32–139`; `src/optimus_gateway/model_policy.py:224–373`; `src/optimus_gateway/upstream_client.py:303–342`, `:362–404`. The decisions route has one attempt and no resend; completion-request `MAX_ROUTE_ATTEMPTS = 2` remains at `src/optimus_model_policy/binding.py:216–219`. System One lacks completion finish/router facts, so the completion guardrail predicate is not claimed for decision replies. ADR-026's `detected=false` is allowed as well as missing; shorthand “no detection” must not exclude that accepted case.
- **Notice/record references:** `src/optimus/acp/auto_composition.py:160–203`; `src/optimus/acp/spec.py:1876–1932`; `src/optimus/telemetry/events.py:569–588`. Notice delivery and telemetry persistence are not unconditional guarantees: delivery failure is recorded/contained, the routing guard is first-write and the event sink can fail. The routing projection is content-free and does not own a second cost debit.
- **Decision authority:** read `docs/decisions/README.md` and ADR-007, ADR-024, ADR-025, ADR-026 and ADR-028. ADR-028's relationship and renumbering are explicit at `docs/decisions/ADR-028-accepts-adr-007-auto-judge-h.md:3–17`; H and its limitations are at `:41–77`. ADR-007's frozen Proposed header is not edited. The accepted decision is ADR-028; main's ADR-027 is the idle client-MCP record. The approved overlay's historical ADR-027 evidence remains unchanged because it participates in the approved hash.
- **Plan scope:** read `docs/superpowers/plans/2026-10-23-plan-12-4-auto-mode_v9.md`, including its decisions, prerequisites, composition and remaining round-2 scope. Its planning-time prerequisite descriptions are not treated as present implementation facts. No plan checkbox, issue status, frozen decision or amendment is changed by this text.
- **Test references inspected:** `tests/unit/acp/test_auto_launch_composition.py:72–192`; `tests/unit/acp/test_auto_turn_routing.py:62–105`, `:156–280`; `tests/unit/acp/test_auto_stop_set.py:62–117`; `tests/unit/acp/test_auto_hybrid.py:142–365`; `tests/unit/acp/test_auto_notice_and_record.py:110–290`; `tests/unit/acp/test_auto_launch_end_to_end.py:130–186`; `tests/unit/optimus_gateway/test_decisions.py:106–259`. They identify executable checks and their scope; no independent passing result is claimed from source inspection.
- **External evidence checked:** read PR #428 and #395 comments through the read-only GitHub connector. The PR body still says live slices were UNRUN; the later [live report](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/395#issuecomment-6437429914) and [merge report](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/395#issuecomment-6437446177) supersede that chronology. The three reported slice costs are USD 0.00054385, 0.0032445 and 0.002069736; the reported total USD 0.005858 is rounded. Raw external evidence was not opened or resealed. No content under `plan12-4-auto\task6\sealed` was read.
- **CI qualification:** the GitHub reader returned successful final-PR-head guardrails run 40469959706 at `df7dc3c`, plus successful Work status/Masterplan workflows. It returned no workflow runs for `bf440cb`; the successor therefore makes no post-merge CI-pass claim. Windows counts remain attributed to the PR's `3420eb2` report. Earlier failures and later test-only/merge deltas remain visible.
- **Intentionally unchanged:** the predecessor's EDIT semantics, historical EDIT receipts, native carried bodies, reviewer/savings status, and unrelated provider/tool/telemetry capabilities. No full Plan 12.2 amendment integration, full Plan 12.3 loop refresh, Guardrails rebuild, new model qualification, round-2 result or whole-plan closure is claimed. Root README changes above apply only to its documentation table.
- **Build handoff:** Claude must apply the exact edits, assemble from the predecessor baseline keys, preserve archived bytes, update the indexes with the resulting artifacts, verify every new file:line at the pin, and record the new PDF hashes/page maps/render checks. No rendered-layout or deterministic-build result is supplied by this authoring pass.

## Build strings

- Page-header `LABEL`: `LOCAL FILING - NOT ACTIVATED`
- Footer: `Plan 12.4 Auto mode | 2026-10-27`
- HLD PDF `/Title`: `Optimus - Architecture (HLD) v2.22 - Plan 12.4 Auto mode (local filing - not activated)`
- LLD PDF `/Title`: `Optimus - Low-Level Design v2.45 - Plan 12.4 Auto mode (local filing - not activated)`
- HLD PDF `/Subject`: `Scoped Auto-mode and registry-prerequisite successor at main bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1; mixed historical provenance; remaining Plan 12.2 amendment scope preserved. Local filing; publication requires separate operator approval.`
- LLD PDF `/Subject`: `Auto composition, H classifier, decisions, per-turn binding, stops, settlement and visibility at main bf440cba5c184f8bca7ed8af0a0ae6bb824f14f1; remaining Plan 12.2 amendment scope preserved. Local filing; publication requires separate operator approval.`

Not run: source assembly, PDF build/rendering, product tests or new live calls.  
Risk: Claude's filing build must establish pagination, table fit, rendered fidelity and fresh artifact hashes.
