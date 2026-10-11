# 13. Context Engine, policy and cost integration contracts

## 13.1 Source-to-view boundary

Canonical `ConversationTurn` records remain host-owned and sanitized. `make_history_snapshot` in `optimus.context.adapter` creates immutable ordinary turns and protected host projections from committed records. Supply the current sanitized prompt separately. `HistoryRevision` binds session, committed generation, last sequence and source digest. No summary changes canonical records or manufactures effects/approval facts.

`ContextEngine.prepare_view(snapshot, *, strategy, parameters, limits, checkpoint, maintenance, cancelled)` returns a bounded `PreparedView`. `StrategyParameters` carries compaction tail, hybrid anchor/tail, summary output cap, max_maintenance_calls, prompt_version and format_version; all fields participate in its digest. `ViewLimits` carries explicit source, history/maintenance token and transient byte bounds, including required `summary_max_bytes` and optional `maintenance_calls_remaining` (None for standalone use, a finite nonnegative integer supplied by the host; booleans rejected). A valid summary byte bound is at least one and strictly below the transient bound. No deployment values are inferred from dataclass defaults.

The injected estimator is subadditive over any strings the engine concatenates: `estimate(a + b) <= estimate(a) + estimate(b)`. Supported production policy currently describes a verified conservative `ceil(r * UTF8_bytes)` profile with non-negative overhead. The complete engine-assembled text is checked before each callback. ViewLimits.maintenance_input_tokens=131072 bounds that text only; the host summary prompt and wire framing are additional, and the complete Gateway request plus reserved output has its own route-capacity check. A downloaded tokenizer or fixture ratio does not silently become a new registry estimator mechanism.

### Released offline numeric set (verified route still required)
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
Compaction summarizes outside its exact whole-turn tail; 131072 is a history ceiling, not a delayed trigger. At verified r=1 these budgets behave largely as byte budgets, less estimator/framing overhead; exact counting is deferred. The named D7 exception is proposed: keep the 524288-byte source floor/warning but refuse an over-capacity complete request readably with OPEN disposition, on absent-engine and attached full-history fallback. No provider guard exemption.


## 13.2 Whole-turn maintenance and checkpoints

Pack complete rendered turns against both conservative per-piece token sums and exact UTF-8 bytes. Count every separator and header. Reserve actual bytes/tokens for a reused prior summary; reserve the effective summary token cap and maximum summary bytes for each future rolling summary. Admit equality, close a chunk before either bound is exceeded, and preflight the entire finite chunk plan before the first callback. If even one required whole turn cannot fit, fail without starting maintenance for that plan.

Fresh and reused summaries pass the same token/byte/format validation. Rebuild an over-bound checkpoint from canonical source; a rejected rebuild publishes nothing. For supported byte-ratio profiles derive `S = min(summary_output_tokens, maintenance_output_tokens)` and `summary_max_bytes = floor(S / r)` with exact arithmetic. Invalid field relationships are configuration conflicts, not reasons to increase admission silently.

Checkpoints contain host-issued covered turn IDs/digests, strategy/parameter/prompt/format identity and source revision. Reuse requires an unchanged covered prefix, checked turn by turn. Cancellation, stale revisions, changed source/configuration, malformed summaries and partial results never publish a checkpoint. Coverage metadata is created by the host, not trusted from model prose.

Typed unavailable/unsupported maintenance status maps to `maintenance unavailable`; actual failure and rejected output retain attempt receipts and their own failure reasons. The filed C1 message map, common OPEN ending, fallback notice and capacity-recovery wording remain exact. A maintenance cancellation can still yield the older internal `maintenance_failed` diagnostic while the host returns cancelled; record this nonblocking residual without commissioning a diagnostic-code change in C1/C2.

## 13.3 Host attachment and final request

`ContextAttachment` in `optimus.context.assembly` is frozen and requires the engine, parameters, limits, captured source/route identity, receipt sink and finite max_repacks. The released offline setting is one repack after initial packing. Keep StrategyParameters and its checkpoint digest unchanged across the turn. Pass ViewLimits.maintenance_calls_remaining = max(0, 18 - callbacks_already_consumed) for initial preparation and each repack; this execution-state field is outside summary identity. The engine preflights the complete chunk plan against min(parameters.max_maintenance_calls, remaining) before any callback. Zero remaining permits a valid zero-call reused/sliding view and refuses a plan needing calls. Reuse still requires matching source, coverage, estimator and token/byte bounds. Retain the host defensive counter and allowance classification; repack checkpoints remain unpublished.

Normal production bootstrap remains inactive. At cf9bb9d the reviewed named test composition supplies explicit process-scoped construction through the real trusted entrypoint and passes attachment/route/receipt dependencies into AcpDuplexAdapter. GatewayModelPolicy is likewise mandatory for the test process. Normal bootstrap enforcement is inactive and the default maps to claude-haiku-4.5; production activation and default removal remain held. See test-composition-contract.md for profiles A/B and approval/hash binding.

An `AttachedTurn` captures history/revision, mode/strategy/parameters, route/model/registry and request identity before any interleaving await. Setters affect later turns. It exposes separate `current_prompt`, exact `selection_text` and inert `conversation_envelope`. Do not hold a configuration lock across provider calls or approval.

`probe_floor` measures full committed canonical history plus provisional prompt without changing disposition. If the engine is unavailable and that projection is <=524288 bytes, prepare full-history fallback with the filed notice and still apply the final complete-request capacity guard. Above the floor, refuse before answer/planning dispatch and keep the thread OPEN. Attached storage class persists through health faults; repeated faults never latch CAP_CLOSED.

Bind the admitted request/view digest to the stored plan. Approved application reuses it and the exact artifact hash; it neither summarizes again nor reselects a model. A changed target requires existing freshness/replan/approval handling. Projection of an old approval never approves a revised plan.

## 13.4 Registry and final Gateway enforcement

Strict YAML rejects duplicate/non-string keys, aliases, anchors, merge keys and custom tags. Packaged defaults plus operator overrides yield one immutable, canonically hashed `RegistrySnapshot`. Formatting changes alone do not alter its effective identity. Neutral policy code imports no host runtime. Trusted launch composition supplies the actual validated object to host and Gateway; a caller-supplied hash is not authority.

Per-role eligibility rejects verified window <262144 or maximum output below the role reserve (ROUTE_WINDOW_BELOW_CEILING / output-cap eligibility). It requires explicit assignment, capabilities, exact endpoint/quantization, verified window/output/parameter/estimator facts, and any required summary receipt/disclosure. Unknown route facts and unknown trusted snapshot mean zero upstream calls. Fixing model aliases does not permit direct provider keys. The legacy host permits an initial attempt plus at most three retries. The inactive-policy Gateway separately permits at most three upstream attempts, including its legacy transient timeout/URL/5xx retries. Once enforcement is active, the Gateway permits one primary attempt and at most one identical-payload resend on the same route, only after a definitely NOT_SENT result (including a proven pre-connection timeout) or rejected HTTP 429. A timeout after connection, uncertain delivery, 5xx or unknown accounting is not resent. The host honors non-retryable classifications so it cannot multiply attempts. No alternative-model recovery is added. Each physical attempt retains its own receipt.

At the final provider boundary enforce `complete_input_estimate + output_reserve <= min(262144, verified_route_window)`, `0 < output_reserve <= verified_route_max_output`, and the exact upstream cap/finish semantics. Count all messages, framing, tools/files/evidence and reasoning reservations; count output once. A complete-request tokenizer may inform route verification, but production use requires a registered supported and reviewed mechanism; neither sample ratios nor broad tokenizer-family labels suffice.

A WRITE-bearing result is usable only with a verified complete successful finish. Length-limit, missing or unknown finish fails before parse/store/approval/execution, even if the prefix parses. Chat incomplete output is visibly incomplete. Preserve receipts for rejected/discarded/cancelled work.

## 13.5 Exactly-once settlement and D6

`StageReceipt` identifies session, turn, stage, attempt, available Gateway/provider request IDs, requested/resolved model/provider, captured configuration/registry, cost or explicit unknown, token/cache data and time. Turn/scope summaries retain known subtotal, unknown IDs, receipt identities and completeness. Duplicate identical receipts are idempotent; conflicting duplicates are integrity errors. Actual attempts count once even when their summary/view/result is stale or discarded. Applying a stored plan never charges its old planning again.

Strict Gateway usage validation remains: invalid cost is not a valid zero-cost `ProviderUsage`. Record the attempted stage as unknown and refuse its unverified successful result as required; keep known subtotals before/after it. Unknown accounting does not introduce a session-wide product monetary stop or automatic retry. Telemetry must not debit an `agent_run` projection a second time.

Configured per-turn/session alerts emit once per actual threshold crossing, with stable scope/crossing identity. This draft invents no operator alert amount. Daily totals require durable reconciliation and explicit IANA timezone/day identity; absent prerequisites make that scope unavailable. P9.85-FU-3 and P11.26-CAND-2 retain existing ownership. Operational public requests and trace export do not acquire fabricated provider charges.

## 13.6 Product/evaluation policy migration

The reviewed Task 11 implementation removes product dollar predicates from Agent planner/runner and non-ACP goal-loop paths, positive-dollar construction requirements and stop-bearing telemetry/planner prompts. Use an explicit optional evaluation monetary policy only for independently capped callers. Keep product accounting and count/time/failure/cancellation/security/capacity controls. No renamed limit, hidden maintenance subtraction or large/infinite sentinel is acceptable.

The three strict xfails at dea4624 were held cost-stop-removal evidence. Task 11 now satisfies those assertions at cf9bb9d and removes their markers; the final full runs verify the product/evaluation split. A result costing more than the former $0.05 must still be delivered successfully on a product path; an independently capped evaluation must stop under its separate envelope. Preserve the current three planning rounds, 30-minute limit, repeated-failure limit two and single-call Chat.

## 13.7 ACP projection and meter

Publish one full-set configOptions projection that preserves model/mode/strategy options and pinned option/setter IDs. Show the strategy picker only when configured attached, retaining it through engine faults. Capture each turn's configuration before awaits; use one revision/resync mechanism so an old publication cannot clear newer pending state. Sliding's filed omission disclosure appears on the first admitted sliding turn and reports actual delivery.

The meter records at local Gateway dispatch before its response, using the largest dispatched planning/answer input with that request's usable capacity, choosing smaller capacity on ties. Maintenance cost contributes to cost records, not the ring. A host capacity refusal yields no fabricated reading. A non-capacity Gateway preflight rejection can leave a reading for a request sent locally but never sent upstream; this meter is not proof of provider delivery. Distinguish storage warnings, strategy-unavailable fallback and whole-request capacity refusal.

## 13.8 Effect proof and rollout

Maintain Task 2's real WRITE/TEST registration, start gates, terminal evidence and cancellation behavior. A normally returned TEST is executed even when its test exit is nonzero; test verdict and operation terminal are distinct. Denied/not-started work is reflected in a fresh consistent effect snapshot before commit. Already-started operations are not promised to be interrupted. Never reconstruct authority from mutation counts or model prose.

Verify fresh-session rollout on the actual production base. If durable replay/resume arrives before rollout, its owner must supply reviewed provenance before old placeholder effects are treated as authoritative. Keep the sandbox's unsynchronized repair gap disclosed until its separately authorized synchronization. The migration adds no durable-history mechanism.


## 13.9 Implemented capacity outcomes and test launch

Once trusted enforcement is active, only INPUT_EXCEEDS_CAPACITY selects the absent-engine capacity text; CAPACITY_REFUSED without a known reason stays generic. Preserve known costs from earlier requests in the turn. The rejected request itself has zero upstream attempts.

> Chat could not answer because this request exceeds the model's input capacity. This request was not sent to a model. A shorter prompt or a narrower request involving fewer workspace files may help. If earlier conversation history is the cause, start a new thread. This thread stays open.

> Planning stopped because its next request exceeds the model's input capacity. That request was not sent to a model. A shorter prompt or a narrower request involving fewer workspace files may help. If earlier conversation history is the cause, start a new thread. This thread stays open.

The request meter uses complete packed input/usable capacity from the final policy estimator. Warn at 80% once per session; a jump over capacity emits refusal directly. Storage’s 80% notice remains separately labelled storage.

The source-owned qualification/attached profiles are selected by name only. HMAC launch authorization binds the security snapshot containing the effective profile hash; host and Gateway independently compose it, and the authenticated child manifest binds the same identity. The host literal check is internal consistency, not a separate operator approval. A profiled host must spawn its own profiled Gateway. Already-listening/external Gateway, no child, --no-auto-start, --framed and --strict are refused; a mismatched explicit model refuses before Redis/Gateway/server. No run-gateway profile flag is needed.
