# 13. Context Engine, policy and cost integration contracts

**Edition scope.** Registry admission, enforcement, production construction and Auto statements explicitly refreshed below describe `bf440cb`. Unrefreshed Plan 12.2 material retains its prior provenance and is read with the controlling 2026-10-18 ordinary shipping amendment (`docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`), including compaction, numeric policy, profiles, maintenance and historical evidence. Section 13.10 specifies Auto's original routing at that pin. Sections 13.11–13.12 add escalation and host/Gateway timing at main `5977155c2bce9728156ee5898ff9e17d0ae08750` (2026-10-29). ADR-024 controls interactive detection, one nudge and the Continue/Stop check-in; ADR-029 adds the single Auto escalation. Retained interim limits and legacy goal-loop descriptions do not override those decisions; this is not a full Plan 12.3 refresh.

## 13.1 Source-to-view boundary

Canonical `ConversationTurn` records remain host-owned and sanitized. `make_history_snapshot` in `optimus.context.adapter` creates immutable ordinary turns and protected host projections from committed records. Supply the current sanitized prompt separately. `HistoryRevision` binds session, committed generation, last sequence and source digest. No summary changes canonical records or manufactures effects/approval facts.

`ContextEngine.prepare_view(snapshot, *, strategy, parameters, limits, checkpoint, maintenance, cancelled)` returns a bounded `PreparedView`. `StrategyParameters` carries compaction tail, hybrid anchor/tail, summary output cap, max_maintenance_calls, prompt_version and format_version; all fields participate in its digest. `ViewLimits` carries explicit source, history/maintenance token and transient byte bounds, including required `summary_max_bytes` and optional `maintenance_calls_remaining` (None for standalone use, a finite nonnegative integer supplied by the host; booleans rejected). A valid summary byte bound is at least one and strictly below the transient bound. No deployment values are inferred from dataclass defaults.

The injected estimator is subadditive over any strings the engine concatenates: `estimate(a + b) <= estimate(a) + estimate(b)`. Production policy uses the admitted route's conservative `ceil(r * UTF8_bytes)` profile with non-negative overhead. At `bf440cb`, ADR-025 also permits an explicitly recorded per-entry empirical admission whose estimator remains `verified: false`; its assumptions and per-reply checks do not establish a universal token or framing bound. The complete engine-assembled text is checked before each callback. ViewLimits.maintenance_input_tokens=131072 bounds that text only; the host summary prompt and wire framing are additional, and the complete Gateway request plus reserved output has its own route-capacity check. A downloaded tokenizer or fixture ratio does not silently become a new registry estimator mechanism.

### Released offline numeric set (verified route still required)

Where these values live at 91fd64a: the reviewed test profiles and test fixtures (`optimus_model_policy/test_profile_qualification.yaml` output reserves 32768/8192; `tests/` fixtures), not shipped production defaults. `MAX_CONTEXT_CEILING_TOKENS = 262_144` (`optimus_model_policy/registry.py`) and `context_ceiling_tokens: 262144` (`defaults.yaml`) are the ceiling constants; `CONVERSATION_MAX_BYTES = 524_288` (`optimus/acp/conversation.py`) is the absent-engine source floor.
| Field | Proposed value / unit |
|---|---|
| Absent / attached source | 524288 / 1048576 UTF-8 bytes |
| Prompt-time record reservation | 131072 bytes; not a reply cap |
| Transient engine input | 524288 bytes |
| History allowance | min(131072 tokens, floor(0.8 * usable_input)); protected state first |
| Engine maintenance text | 131072 estimated tokens; host prompt/wire framing extra |
| Summary output / bytes | S <=8192 tokens; summary_max_bytes=floor(S/r) |
| Compaction tail | 32768 tokens |
| Hybrid anchor / tail | 16384 / 65536 tokens, deduplicate overlap |
| Implementer output | 32768 tokens, enforced actual route cap |
| Effective total | min(262144, verified window), includes output once |
| Maintenance / repacks | 18 shared logical callbacks; at most one repack after initial view |
Compaction summarizes outside its exact whole-turn tail; 131072 is a history ceiling, not a delayed trigger. At verified r=1 these budgets behave largely as byte budgets, less estimator/framing overhead; exact counting is deferred. The named D7 exception is accepted (ADR-018, operator source S4): keep the 524288-byte source floor/warning but refuse an over-capacity complete request readably with OPEN disposition, on absent-engine and attached full-history fallback. No provider guard exemption.


## 13.2 Whole-turn maintenance and checkpoints

Pack complete rendered turns against both conservative per-piece token sums and exact UTF-8 bytes. Count every separator and header. Reserve actual bytes/tokens for a reused prior summary; reserve the effective summary token cap and maximum summary bytes for each future rolling summary. Admit equality, close a chunk before either bound is exceeded, and preflight the entire finite chunk plan before the first callback. If even one required whole turn cannot fit, fail without starting maintenance for that plan.

Fresh and reused summaries pass the same token/byte/format validation. Rebuild an over-bound checkpoint from canonical source; a rejected rebuild publishes nothing. For supported byte-ratio profiles derive `S = min(summary_output_tokens, maintenance_output_tokens)` and `summary_max_bytes = floor(S / r)` with exact arithmetic. Invalid field relationships are configuration conflicts, not reasons to increase admission silently.

Checkpoints contain host-issued covered turn IDs/digests, strategy/parameter/prompt/format identity and source revision. Reuse requires an unchanged covered prefix, checked turn by turn. Cancellation, stale revisions, changed source/configuration, malformed summaries and partial results never publish a checkpoint. Coverage metadata is created by the host, not trusted from model prose.

Typed unavailable/unsupported maintenance status maps to `maintenance unavailable`; actual failure and rejected output retain attempt receipts and their own failure reasons. The filed C1 message map, common OPEN ending, fallback notice and capacity-recovery wording remain exact. A maintenance cancellation can still yield the older internal `maintenance_failed` diagnostic while the host returns cancelled; record this nonblocking residual without commissioning a diagnostic-code change in C1/C2.

## 13.3 Host attachment and final request

`ContextAttachment` in `optimus.context.assembly` is frozen and requires the engine, parameters, limits, captured source/route identity, receipt sink and finite max_repacks. The released offline setting is one repack after initial packing. Keep StrategyParameters and its checkpoint digest unchanged across the turn. Pass ViewLimits.maintenance_calls_remaining = max(0, 18 - callbacks_already_consumed) for initial preparation and each repack; this execution-state field is outside summary identity. The engine preflights the complete chunk plan against min(parameters.max_maintenance_calls, remaining) before any callback. Zero remaining permits a valid zero-call reused/sliding view and refuses a plan needing calls. Reuse still requires matching source, coverage, estimator and token/byte bounds. Retain the host defensive counter and allowance classification; repack checkpoints remain unpublished.

At `bf440cb`, normal production bootstrap is implemented under active trusted registry enforcement. `build_configured_server` uses `trusted_snapshot()` and `ordinary_route_policy`, then `ordinary_attachment` when an eligible summarizer exists (`src/optimus/acp/bootstrap.py:267–320`; `src/optimus/acp/context_attachment.py:51–103`). `ordinary_attachment` constructs the plain ContextEngine and Gateway-backed maintenance; without an eligible summarizer it returns None. This is production construction, not a test-only constructor.

The ordinary default planner is the cheapest eligible medium model, otherwise the cheapest eligible easy model (`src/optimus/agent/defaults.py:19–29`). In the shipped ordinary policy that is Haiku 5.5; the former claude-haiku-4.5 alias is not the enforced default. Auto uses its separate composition and per-turn binding (§13.10). Historical test-profile evidence and approval identities stay attached to their named profiles; an ordinary or Auto launch does not inherit their authority. The amendment controls unrefreshed Plan 12.2 behavior and evidence; no historical pass is promoted to this pin.

An `AttachedTurn` captures history/revision, mode/strategy/parameters, route/model/registry and request identity before any interleaving await. Setters affect later turns. It exposes separate `current_prompt`, exact `selection_text` and inert `conversation_envelope`. Do not hold a configuration lock across provider calls or approval.

`probe_floor` measures full committed canonical history plus provisional prompt without changing disposition. If the engine is unavailable and that projection is <=524288 bytes, prepare full-history fallback with the filed notice and still apply the final complete-request capacity guard. Above the floor, refuse before answer/planning dispatch and keep the thread OPEN. Attached storage class persists through health faults; repeated faults never latch CAP_CLOSED.

Bind the admitted request/view digest to the stored plan. Approved application reuses it and the exact artifact hash; it neither summarizes again nor reselects a model. ADR-029's recovery move occurs during interactive Auto planning, before that application: it updates the active model, binder and target limits while preserving the captured admission as historical identity (§13.11). Application uses the model and binder the turn moved to. A changed target requires existing freshness/replan/approval handling. Projection of an old approval never approves a revised plan.

## 13.4 Registry and final Gateway enforcement

Strict YAML rejects duplicate/non-string keys, aliases, anchors, merge keys and custom tags. Packaged defaults plus operator overrides yield one immutable, canonically hashed `RegistrySnapshot`. Formatting changes alone do not alter its effective identity. Neutral policy code imports no host runtime. Trusted launch composition supplies the actual validated object to host and Gateway; a caller-supplied hash is not authority.

At `bf440cb`, eligibility requires explicit role assignment, capabilities, recorded endpoint/quantization and verified window/output facts, supported reasoning controls, the applicable reserve and any required summary receipt/disclosure. The window floor is 262144 for non-classifier roles and 8192 for classifier; the classifier remains subject to the validator's positive reserve requirement even though the decisions endpoint reserves no output (`src/optimus_model_policy/registry.py:98–117`; `src/optimus_model_policy/validation.py:80–170`).

ADR-025 permits two independent admission parts on each model entry: `empirical_estimate` admits its explicitly unverified empirical estimator; `provider_family` admits its recorded provider base slug while requiring the reply's provider name. Neither relaxes the other part's checks. `conservative-utf8` uses ratio 1, 16 tokens per message and 256 fixed, `verified: false`. Evidence, assumptions and limitations participate in the effective registry identity. A first call can exceed the estimate or be charged before reply validation stops later calls to that model.

The operator override is the regular file `model-registry.yaml` in the trusted operator config root. Ordinary composition applies it over defaults; Auto applies it over defaults plus the Auto overlay. Launch approval binds the resulting effective hash, and host/Gateway compose independently; test profiles never read the override (`src/optimus_model_policy/binding.py:111–170`; `src/optimus/acp/launch_gate.py:701–728`). Unknown facts outside those explicit admissions and an unknown trusted snapshot do not authorize upstream dispatch.

For completion replies on exception routes, retain usage/finish validation, reported input at most the estimate where empirically admitted, recorded-provider equality where family-admitted, and one router attempt. An empty pipeline passes; a nonempty pipeline passes only ADR-026's exact shape: one `guardrail`, one closed-facts record, `flagged` false, `detected` false or missing, `decision`/`action`/`guardrail_scope` missing and `verdict_conflict` false. Explicit nulls, wrong types, extra stages or other facts refuse. Acceptance proves neither unchanged content nor data handling. A failed check stops only that model for the Gateway's remaining life; stops cannot be cleared (`src/optimus_gateway/model_policy.py:87–101`, `:224–288`). Decisions have the distinct reply contract in §13.10 because System One does not supply completion finish/router facts. Fixing model aliases does not permit direct provider keys. The legacy host permits an initial attempt plus at most three retries. The inactive-policy Gateway separately permits at most three upstream attempts, including its legacy transient timeout/URL/5xx retries. Once enforcement is active, the Gateway permits one primary attempt and at most one identical-payload resend on the same route, only after a definitely NOT_SENT result (including a proven pre-connection timeout) or rejected HTTP 429. A timeout after connection, uncertain delivery, 5xx or unknown accounting is not resent. The host honors non-retryable classifications so it cannot multiply attempts. This resend policy adds no alternative-model recovery. ADR-029's single later recovery move is a separate interactive Auto planning action (§13.11), not a resend of an uncertain or failed provider attempt. The per-request timing budget is specified in §13.12. Each physical attempt retains its own receipt.

At the final provider boundary enforce `complete_input_estimate + output_reserve <= min(262144, verified_route_window)`, `0 < output_reserve <= verified_route_max_output`, and the exact upstream cap/finish semantics. Count all messages, framing, tools/files/evidence and reasoning reservations; count output once. A complete-request tokenizer may inform route verification, but production use requires a registered supported and reviewed mechanism; neither sample ratios nor broad tokenizer-family labels suffice.

A WRITE- or EDIT-bearing result is usable only with a verified complete successful finish. Length-limit, missing or unknown finish fails before parse/store/approval/execution, even if the prefix parses. Chat incomplete output is visibly incomplete. Preserve receipts for rejected/discarded/cancelled work.

## 13.5 Exactly-once settlement and D6

`StageReceipt` identifies session, turn, stage, attempt, available Gateway/provider request IDs, requested/resolved model/provider, captured configuration/registry, cost or explicit unknown, token/cache data and time. Turn/scope summaries retain known subtotal, unknown IDs, receipt identities and completeness. Duplicate identical receipts are idempotent; conflicting duplicates are integrity errors. Actual attempts count once even when their summary/view/result is stale or discarded. Applying a stored plan never charges its old planning again.

Strict Gateway usage validation remains: invalid cost is not a valid zero-cost `ProviderUsage`. Record the attempted stage as unknown and refuse its unverified successful result as required; keep known subtotals before/after it. Unknown accounting does not introduce a session-wide product monetary stop or automatic retry. Telemetry must not debit an `agent_run` projection a second time.

Configured per-turn/session alerts emit once per actual threshold crossing, with stable scope/crossing identity. This draft invents no operator alert amount. Daily totals require durable reconciliation and explicit IANA timezone/day identity; absent prerequisites make that scope unavailable. P9.85-FU-3 and P11.26-CAND-2 retain existing ownership. Operational public requests and trace export do not acquire fabricated provider charges.

## 13.6 Product/evaluation policy migration

The reviewed Task 11 implementation removes product dollar predicates from Agent planner/runner and non-ACP goal-loop paths, positive-dollar construction requirements and stop-bearing telemetry/planner prompts. Use an explicit optional evaluation monetary policy only for independently capped callers. Keep product accounting and count/time/failure/cancellation/security/capacity controls. No renamed limit, hidden maintenance subtraction or large/infinite sentinel is acceptable.

The three strict xfails at dea4624 were held cost-stop-removal evidence. Task 11 now satisfies those assertions at cf9bb9d and removes their markers; the final full runs verify the product/evaluation split, and the change was merged to `main` via PR #276 (`c509fc8`). A result costing more than the former $0.05 must still be delivered successfully on a product path; an independently capped evaluation must stop under its separate envelope. Preserve the current three planning rounds, 30-minute limit, repeated-failure limit two and single-call Chat.

## 13.7 ACP projection and meter

Publish one full-set configOptions projection that preserves model/mode/strategy options and pinned option/setter IDs. Show the strategy picker only when configured attached, retaining it through engine faults. Capture each turn's configuration before awaits; use one revision/resync mechanism so an old publication cannot clear newer pending state. Sliding's filed omission disclosure appears on the first admitted sliding turn and reports actual delivery.

The meter records at local Gateway dispatch before its response, using the largest dispatched planning/answer input with that request's usable capacity, choosing smaller capacity on ties. Maintenance cost contributes to cost records, not the ring. A host capacity refusal yields no fabricated reading. A non-capacity Gateway preflight rejection can leave a reading for a request sent locally but never sent upstream; this meter is not proof of provider delivery. Distinguish storage warnings, strategy-unavailable fallback and whole-request capacity refusal.

## 13.8 Effect proof and rollout

Maintain Task 2's real WRITE/TEST registration, start gates, terminal evidence and cancellation behavior. At `57e2069`, EDIT registers and settles as the plan's WRITE operation, plus its read-before-write READ. During execution, `EDIT_NOT_APPLICABLE` settles WRITE as `suppressed`, or `failed_no_effect` after the post-guard digest re-check; every TEST is `suppressed`. Binding failure is before approval. Applicability failure stops the run without fitness-driven replanning (§4B). A normally returned TEST is executed even when its test exit is nonzero; test verdict and operation terminal are distinct. Denied/not-started work is reflected in a fresh consistent effect snapshot before commit. Already-started operations are not promised to be interrupted. Never reconstruct authority from mutation counts or model prose.

Verify fresh-session rollout on the actual production base. If durable replay/resume arrives before rollout, its owner must supply reviewed provenance before old placeholder effects are treated as authoritative. Keep the sandbox's unsynchronized repair gap disclosed until its separately authorized synchronization. The migration adds no durable-history mechanism.


## 13.9 Implemented capacity outcomes and test launch

Once trusted enforcement is active, only INPUT_EXCEEDS_CAPACITY selects the absent-engine capacity text; CAPACITY_REFUSED without a known reason stays generic. Preserve known costs from earlier requests in the turn. The rejected request itself has zero upstream attempts.

> Chat could not answer because this request exceeds the model's input capacity. This request was not sent to a model. A shorter prompt or a narrower request involving fewer workspace files may help. If earlier conversation history is the cause, start a new thread. This thread stays open.

> Planning stopped because its next request exceeds the model's input capacity. That request was not sent to a model. A shorter prompt or a narrower request involving fewer workspace files may help. If earlier conversation history is the cause, start a new thread. This thread stays open.

The request meter uses complete packed input/usable capacity from the final policy estimator. Warn at 80% once per session; a jump over capacity emits refusal directly. Storage’s 80% notice remains separately labelled storage.

The source-owned qualification/attached profiles are selected by name only. HMAC launch authorization binds the security snapshot containing the effective profile hash; host and Gateway independently compose it, and the authenticated child manifest binds the same identity. The host literal check is internal consistency, not a separate operator approval. A profiled host must spawn its own profiled Gateway. Already-listening/external Gateway, no child, --no-auto-start, --framed and --strict are refused; a mismatched explicit model refuses before Redis/Gateway/server. No run-gateway profile flag is needed. That statement concerns the named test profiles; Auto's manually managed Gateway uses the separate `run-gateway --auto` option below.

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

The adapter captures the chosen route binder and rebinds the attached turn's limits before planning/answer work. At `5977155`, the selected planning/answer model remains bound except for ADR-029's one interactive recovery move (§13.11). Subsequent planning and approved application use the moved-to model and binder; applying an old plan does not classify it again. Maintenance retains its separately selected summarizer (`src/optimus/acp/spec.py:2040–2047`, `:1812–1836`, `:2667–2729`; `src/optimus/acp/auto_composition.py:348–382`).

Every Auto runner and summarizer shares the launch's host stop set with the resolver. Proven exception-route stops are retained even if receipt reporting raises; the Gateway independently keeps permanent per-model stops for its process life. Ordinary failures do not automatically stop all models. No stop is cleared as a retry-to-green mechanism (`src/optimus/agent/runner.py:1067–1078`; `src/optimus/context/maintenance.py:291–320`; `src/optimus_gateway/model_policy.py:87–101`).

These confidence/availability route-ups remain pre-dispatch selection. ADR-029's distinct rung 2 is implemented at `5977155`: one mid-turn recovery move to the escalation role's first routable model in interactive Auto planning (§13.11). The classifier is not rerun for that move.

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

## 13.11 ADR-029: one mid-turn Auto recovery move

### 13.11.1 Entry, trigger and graph

At `5977155`, the adapter supplies `recovery_escalation` only when interactive recovery is enabled and the turn has an Auto decision (`src/optimus/acp/spec.py:1658–1665`). Fixed-model launches and headless callers gain no move; `OPTIMUS_LOOP_RECOVERY=headless` retains the existing hard caps. This extends ADR-024's recovery episode only as ADR-029 scopes it.

After an episode's nudge, a second detection, an allowance ending without a plan or refusal, or a settled REFUSE can request a `PlanningEscalation`. A grant sets aside that refusal; without a grant, the refusal remains for the check-in. A first refusal outside an episode is terminal, a final plan after the nudge goes directly to the check-in, and an exhausted allowance without a detection has no escalation edge (`src/optimus/agent/planning_loop.py:1415–1447`, `:1461–1484`; `tests/unit/agent/test_planning_loop_escalation.py:96–174`, `:240–290`).

`AutoRouter.escalation_target(current_model_id)` selects the first eligible unstopped model of `Role.ESCALATION`. An empty role, all-stopped role, current model equal to that first routable target, or target with less usable input yields no target; it does not skip that target to invent another rung. Later role entries substitute for stopped earlier ones. `escalation` is an implementer role, with native-tool, planning-grammar, route, capacity and reserve checks. Launch constructs its route policies and attachments in advance (`src/optimus/acp/auto_composition.py:311–322`, `:348–382`; `src/optimus_model_policy/registry.py:98–123`; `src/optimus_model_policy/validation.py:67–78`, `:110–150`).

### 13.11.2 Grant, attachment and accounting

The bridge prepares the target binder, attachment and notice before publishing the switch. It checks halt before selection and again after the notice; preparation failure returns `failed` without publishing a move. An absent target returns `no_target`. The notice is attempted with confirmed flushing under the existing bounded notice wait; failure is recorded as undelivered and does not gate the move. The line names the cause, target and configured input/output prices per million tokens, with the previous prices. It is an informational cost alert, not a spend limit or approval. Contributor disclosure remains required per request (`src/optimus/acp/auto_composition.py:175–186`; `src/optimus/acp/spec.py:2667–2729`).

A grant publishes the target binder and `escalated_model`. `turn_model` then resolves to that model while `auto_decision` remains the initial classifier routing. The new binder adopts all earlier dispatch readings, each with its original capacity; the meter still chooses the largest input, smaller capacity on a tie. `AttachedTurn.escalate_attachment` changes model, request estimator, usable input and target history limits together. It preserves captured history, admission identity, strategy parameters/checkpoint identity, summarizer, maintenance allowance, repack count and earlier readings. Existing final fit/repack and Gateway admission still apply; a usable-input comparison alone does not establish that a particular request fits (`src/optimus/acp/spec.py:424–434`, `:2719–2727`; `src/optimus/gateway/route_binding.py:161–176`; `src/optimus/context/assembly.py:510–522`; `tests/unit/acp/test_auto_escalation.py:218–238`).

`AgentRunner` replaces its active model/route scope before later request reports are made; earlier receipts retain their original routes. The final plan names the producing model, and the adapter passes the moved-to model and binder into the separately approved application. No classification or extra maintenance is performed merely to apply the stored plan (`src/optimus/agent/runner.py:644–704`; `src/optimus/acp/spec.py:1812–1836`; `tests/unit/acp/test_auto_escalation.py:321–347`).

### 13.11.3 Bounds, check-in and records

The planning loop marks the episode's move tried even on a refusal. A grant disables further escalation for the turn, resets the detector and carries an explanation to the target's first request. The episode stays open. The target gets `continue_grant_steps` and a fresh wall-clock allowance: three steps and 30 minutes by default. A later Continue starts a new episode on the moved-to model but cannot enable another switch. A halt or typed failure remains terminal (`src/optimus/agent/planning_loop.py:187–206`, `:1206–1245`, `:1415–1489`).

The subsequent Continue/Stop check-in identifies the move, or says `Auto had no stronger eligible model to try.` when appropriate. Nothing is dispatched while it is pending. Continue grants only planning work; if a final plan is waiting, Continue presents it for its own exact approval. Stop ends the turn with its cause or retains a pending refusal. The one-move bound adds no WRITE/TEST authority (`src/optimus/agent/planning_loop.py:1517–1542`; `tests/unit/acp/test_auto_escalation_end_to_end.py:49–118`, `:121–148`).

The content-free `loop_recovery` event adds `record="escalation"`, the signal, planning step and decision (`granted`, `no_target`, `failed` or `halted`). A grant adds `from_model`, `to_model` and `notice_delivered`. It carries no path, tool arguments or reply text. The initial `auto_routing` projection is not rewritten, and neither event owns a second debit. Actual attempts retain ordinary receipt-first settlement with explicit unknown costs (`src/optimus/agent/planning_loop.py:1461–1478`, `:1544–1568`; `src/optimus/telemetry/events.py:540–568`; `tests/unit/agent/test_planning_loop_escalation.py:213–231`).

## 13.12 Host/Gateway timing contract

### 13.12.1 Shared clocks and dispatch admission

At `5977155`, `UPSTREAM_ATTEMPT_TIMEOUT_SECONDS = 60.0`, `GATEWAY_REQUEST_BUDGET_SECONDS = MAX_ROUTE_ATTEMPTS * 60.0 = 120.0`, and `HOST_GATEWAY_TIMEOUT_SECONDS = 135.0`. `GatewayClient` uses the host constant by default. The CLI accepts a positive finite `--gateway-timeout-seconds` override for this process and warns below that default. A shorter wait can abandon a billed reply and leave planning stopped as `PLANNING_GATEWAY_COST_UNKNOWN`; it changes no resend or accounting rule (`src/optimus_model_policy/binding.py:219–237`; `src/optimus/gateway/client.py:24–41`, `:124–133`; `src/optimus/acp/__main__.py:303–320`, `:968–971`).

The server calls `begin_request_budget` before handling an accepted route and clears its thread-local deadline in `finally`. `request_budget_admits(seconds)` requires the whole proposed wait to fit before the monotonic request deadline. Completion and decision handlers check immediately before upstream dispatch. Completion recovery must also fit its delay plus an entire attempt, with admission rechecked at dispatch after backoff. Tool-provider retries use the same budget; a failed retry candidate whose backoff consumes the remaining time leaves the previous attempt as the final failure. Retry observers run only after the retry dispatch, so reporting cannot delay it beyond the last budget check (`src/optimus_gateway/server.py:108–123`; `src/optimus_gateway/upstream_client.py:48–66`, `:278–334`; `src/optimus_gateway/responses.py:178–218`; `src/optimus_gateway/decisions.py:86–103`; `src/optimus_gateway/tool_provider_http.py:65–73`, `:102–119`).

The enforced completion limit stays one primary attempt plus at most one identical-payload recovery attempt on the same route, only after definitely not sent or rejected HTTP 429. Uncertain delivery, 5xx or unknown accounting is not resent. The decisions route remains one attempt with no resend. A budget permits fewer attempts than the numerical maximum; it creates no entitlement to a retry.

### 13.12.2 Attempt deadline and failure facts

`AttemptDeadline.run` executes upstream I/O on a daemon worker and waits no longer than that attempt's timeout. This bounds the wait through name lookup, multi-address connect, proxy tunnel, TLS, send and response reads, including a peer that keeps dripping bytes. At expiry it abandons the attempt, shuts down an available socket and rejects a connection completed later before any request byte leaves. The raw socket is handed over before tunnel/TLS work. Setup that cannot be interrupted can leave the worker alive; one of 32 process-wide slots remains held until that worker actually exits. A full pool refuses new work immediately (`src/optimus_gateway/upstream_client.py:76–174`).

Production completions, decisions and tool-provider HTTP calls use that deadline machinery. The watched opener connects their sockets to it. Enforced model/decision expiry is `not_sent` if no connection was accepted, otherwise `uncertain`; worker-capacity refusal starts nothing. Structured failure kinds are `attempt_deadline`, `attempt_capacity` and `request_budget`; delivery outcome remains separately attributable (`src/optimus_gateway/upstream_client.py:370–385`, `:439–448`, `:492–500`; `src/optimus_gateway/tool_provider_http.py:113–119`; `src/optimus_gateway/responses.py:188–194`).

### 13.12.3 Delivery limitation and evidence

The dispatch budget starts before request-body handling, so Gateway processing can consume time and leave less room for dispatch. It does not impose an end-to-end deadline on request reading, Stage C ledger work, logging or reply writing. The host's additional 15 seconds is slack, not proof of delivery through stalled storage/processing. These controls bound waits and outstanding attempts; they do not promise immediate termination of every abandoned worker or prompt cancellation of an in-flight host call. Both prompt in-flight cancellation and a Gateway-processing deadline remain owed in #397.

When reply writing encounters `BrokenPipeError`, `ConnectionAbortedError` or `ConnectionResetError`, the server closes the connection and emits sanitized `reply_undeliverable` with known route and status, after its ordinary outcome log; it does not turn the lost reply into a fresh model attempt (`src/optimus_gateway/server.py:210–228`). Tests in `tests/unit/optimus_gateway/test_upstream_retry.py`, `test_responses.py`, `test_decisions.py` and `test_server.py` cover the budget, deadline, late connection, cap and lost-reply paths. Section 14 distinguishes this inspected test coverage from reported execution, live evidence and remaining obligations.
