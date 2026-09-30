# ADR-004: Curated model registry (YAML), tiers, origin rule, per-token selection among eligible models

**Status:** Accepted-with-open-items. **Date:** 2026-09-30.
**Decider:** the operator (requirements and selection policy). The mechanism was proposed by Claude and
reviewed by Codex on 2026-09-30.

**Authority boundary:**

- **Accepted by the operator:**
  - a curated, configurable list;
  - the named tiers and models;
  - the origin rule;
  - "per token among eligible models";
  - **eligibility by operator configuration, with no task-based qualification tests;**
  - **Muse Spark 1.3 Contributor treated as the same model as Muse Spark 1.3,** on the operator's
    judgment, used with a warning.
- **Proposed:**
  - the registry schema;
  - the structural validator;
  - the price-ceiling value;
  - the provider routes.
- **Not commissioned:** implementation and paid calls.

## Context

**Operator, verbatim (2026-09-30, source S1).** Where the first clause of a message restates Claude's
text, the record says so.

> "We absolutely need a curated model list  and a way to maintain it - probably yaml??
> 1. Ultra - Cheap tier - Summarizer + Easy tasks (GPT-6-Luna + Qwen 3.7 flash)
> 2. Cheap Tier - Medium + Complex tasks (GLM 5.3 + DeepSeek v4.1 Flash + Gemini 3.7 Flash)
> 3.  Medium Tier - Review (Sonnet 5.5 + Kimi K3, probably)
>
> So the "Auto" mode should classify into one of these three and assign from them, it is here I was
> thinking of Jev
> In order to keep cost under control  we will not have Opus 5.5/Fable/Astra price models"

> "4. I have given suggested model list - more than 1 model per task tier ( 1 chinese + 1 non-chinese
> min) - chinese can be the first-pref and non-chinese fallback"

> "3. if the non-chinese model is cheaper that should be the default"

> "1. I will need inputs from Codex and you on this - Can the flash handle medium to complex coding tasks
> ? If no then GLM 5.3"

> "My recommendation is both, as a cascade, rather than choosing one — GLM 5.3 Flash looks risky if it
> gets stuck; loop controls are for exceptional situations — should not be needed as an everyday
> occurrence.
> How is DeepSeek v4.1 Flash in comparison?"

The first clause restates Claude's recommendation.

> "The cheap tier's only non-Chinese model is its weakest value: How is Gemini 3.8 Flash?"

The first clause restates Claude.

> "I am assuming the model list shall be configurable - so we should be able to change as and when newer
> models become available."

> "Muse Spark also has a contributor option that is much cheaper I believe? if yes, we can gp with that
> too else Muse Spark 1.3; Measure cheaper per token, for now - defining a successful task is more
> involved IMO."

> "Confirm Muse Spark Contributor, knowing Meta may train on prompts. - We need to establish it is the
> same model as the non-contributor, if yes, we use it with a warning/notification. That should suffice -
> I am not expecting users to enter personal info in coding prompts."

The first sentence restates Claude's question.

> "Yes, per token among eligible models"

> "To my knowledge, both are essentially the same. Given the price difference, I would go with
> Contributor. Model selection will change throughout the life of the project and should be
> configurable, so tests are not needed just to check tasks - which also is not simple for medium to
> complex tasks"

This answers the question of whether the Contributor tier is the same model as Muse Spark 1.3 (decision
7), and whether models must pass tests on our own tasks before selection (decision 3).

> "We can use the newer benchmarks as a guide, specifically those benchmarks that target software coding
> and architecture tasks. Because if something is targeting all kinds of tasks — for example, the role
> in medicine, how well AI is performing in medicine, or video generation — that's not my use case for
> coding, right? So I'm only interested in what my use case is for coding. So the specific benchmarks
> that are most up-to-date and relevant to coding and software architecture should be considered."

This sets which evidence guides the operator's configuration (decision 3).

**An earlier operator decision** (2026-09-28, a paraphrase in the brainstorm diary, outside the
repository): "The user choice is the *model*, not a context strategy: either **Auto** (Optimus routes)
or **self-selected model**. Optimus prioritises cost, so only models with a good cost/value balance are
allowed at all. That was the requirement from the start."

**Facts on `main` at `e41b66d`:**

- **There is no allowed-model list.**
  - The launch policy's "bounded-model predicate" (`_parse_model`, `acp/launch_policy.py`) rejects only an
    empty value or embedded credentials.
  - The Gateway maps one alias, `claude-haiku`, and passes any `vendor/model` ID to OpenRouter
    (`optimus_gateway/model_mapping.py`).
- **The 2026-09-28 requirement was never built.** No backlog item owns it; the Plan 11 charter lists
  "model routing" under `P11-FEAT-GATEWAY-CORE`.

**Prices and routes, 2026-09-30.** USD per million tokens, input / output. The evidence file's sections C
and D2 give the details.

| Candidate tier | Model | Origin | First-party or pinned route | Cheapest listed route |
|---|---|---|---|---|
| Ultra-cheap | `qwen/qwen3.7-flash` | China | 0.03 / 0.13 (Alibaba, the only provider) | same |
| Ultra-cheap | `openai/gpt-6-luna` | US | 0.10 / 0.50 | same |
| Cheap | `deepseek/deepseek-v4.1-flash` | China | 0.15 / 0.60 (DeepSeek) | 0.0198 / 0.396 (third-party fp4) |
| Cheap | `z-ai/glm-5.3-flash` | China | 0.15 / 0.50 (Z.AI, fp8) | 0.02 / 0.2475 (third-party fp4) |
| Cheap (escalation) | `z-ai/glm-5.3` | China | 1.40 / 4.40 | |
| Cheap | `google/gemini-3.8-flash` (replaces 3.7) | US | 0.75 / 3.75 | same |
| Cheap | `meta/muse-spark-1.3-contributor` | US | 0.10 / 0.20 (Meta, the only provider) | same |
| Cheap | `meta/muse-spark-1.3` | US | 1.25 / 4.25 (Meta) | same |
| Review | `anthropic/claude-sonnet-5.5` | US | 2.00 / 10.00 | same |
| Review | `moonshotai/kimi-k3` | China | 3.00 / 15.00 | same |
| Excluded | Opus 5.5; Fable 5.x; GPT-6 Astra | US | 4 / 20; 10 / 50; 10 / 50 | |

## Options considered

**1. Where the list lives:**

| | A: Python constants | B: YAML in the repo (chosen) | C: live OpenRouter catalog | D: remote config service |
|---|---|---|---|---|
| Human-editable | Needs a developer | Yes | No curation | Yes |
| Reviewed and versioned | Yes | Yes | No | Depends |
| Cost and value curation | Yes | Yes | **No** | Yes |
| Complexity | Low | Low | Low | High |

C fails the requirement that "only models with a good cost/value balance are allowed at all".

**2. How the list changes when new models appear:**

| | A: shipped file, changed by PR and release | B: user file only | C: shipped defaults plus a validated operator override (chosen) |
|---|---|---|---|
| New model without a release | No | Yes | Yes |
| Rules still enforced | Yes | Only if validated | Yes, on the merged result |
| Tamper resistance | High | Low | High: the approved snapshot is hashed (below) |

**3. Which provider serves each model:**

| | A: OpenRouter's default routing (cheapest-weighted) | B: strict per-model routes (chosen) |
|---|---|---|
| Price | Lowest listed; often fp4 builds | The pinned route's price |
| Quality and loop risk | Uncontrolled; published loop reports cluster on particular routes | Controlled and reproducible |
| Our measurements comparable | No | Yes |

**4. How a model becomes eligible for a role:**

| | A: task-based qualification tests (proposed by Claude and Codex) | B: operator configuration plus a structural validator (the operator's decision) |
|---|---|---|
| Evidence before use | Measured on Optimus's own tasks | Operator judgment, informed by current coding and architecture benchmarks and observed telemetry |
| Cost and effort | Paid runs per model and role. **Hard to define for medium and complex tasks** (the operator's point) | None beyond editing the registry |
| Adopting new models | Slow: every new model needs a test cycle | Fast: "Model selection will change throughout the life of the project" |
| Risk | Lower chance of a weak default | A weaker model can become a default. This is mitigated by loop control (ADR-009), review (ADR-008), alerts (ADR-005), telemetry, and fast reconfiguration |

**5. Default selection within a tier and role:**

| | A: Chinese first | B: cheapest per token, unconditional | C: cheapest per token among role-eligible models (the operator's decision) |
|---|---|---|---|
| Cost | Can pick the pricier model | Lowest | Lowest among the models the operator configured as eligible |
| Everyday reliability | Not considered | Not considered | Through the operator's curation of eligibility (option 4B) |
| Operator principles kept | Origin preference only | Price only | Price, origin tie-break and curated eligibility |

## Decision

**1. One YAML registry is the single source of truth.** Its `policy` block holds:

- **The context ceiling and capacity formula,** from ADR-003. The output reserve is counted once.
- **A price ceiling,** replacing the named exclusions. The proposed value is at most $3/M input and $15/M
  output, which excludes Opus 5.5 at $4/$20. The operator confirms the value.
- **The origin rule.** Each tier *lists* at least one `china` and one `non_china` model. This is an
  inventory rule, not a statement about how well each model performs.
- **The selection rule** (item 3 below).
- Per-tier history targets (ADR-003) and alert thresholds (ADR-005).

**2. What each model entry records:**

- ID, tier, roles and origin.
- **The route.**
  - An explicit provider allow-set, such as OpenRouter `only`, with an explicit fallback policy. Provider
    `order` alone is only a preference, not a pin.
  - An explicit set of supported `quantizations`, for example fp8 and bf16, not a "greater than or equal"
    floor.
- The route's window and maximum output.
- The route's prices: input, output, cache read, cache write, and any other billable class.
- Capabilities: structured outputs, tools, reasoning settings.
- `data_use`, for example `may_train_on_prompts`.
- Documented provider rate limits. They are recorded as documented and are not assumed to equal the
  OpenRouter quota.
- `verified_on` and a source.
- **Per-role eligibility,** set by the operator (item 3 below).

**3. Eligibility is per role, set by operator configuration, and it comes before price.**

- **The roles:** summarizer, classifier, easy, medium, complex, escalation implementer, reviewer.
- **The operator marks which roles each model is eligible for.** The operator decided on 2026-09-30:
  "tests are not needed just to check tasks".
  - **No task-based qualification test is required.** This supersedes the per-role test gates that Claude
    and Codex proposed earlier the same day.
    - **One exception, chosen by the operator:** the summarizer role keeps its summary quality check
      (ADR-006). The operator said: "keep the summarizer check".
  - **What guides the choice: the most up-to-date benchmarks specific to software coding and software
    architecture, plus observed Optimus telemetry.** This is the operator's decision.
    - **Mixed-domain indexes are excluded from this guidance:** those that blend coding with medicine,
      general knowledge, maths, video and similar. The Artificial Analysis Intelligence Index is an
      example.
    - **The qualifying benchmark list lives in the evidence file.** Each is identified by name, version and
      date, and is chosen for being coding-specific, recent, contamination-resistant and still
      discriminating at the top. It is revised as benchmarks age: a saturated or contaminated benchmark,
      such as SWE-bench Verified, drops out.
    - **Each model entry records the benchmark evidence it relied on:** benchmark and version, date,
      harness, score, whether vendor-reported or independent, and the source. Scores taken with different
      harnesses are not compared as if they were like-for-like.
- **A structural validator still checks each eligible model against its role's hard requirements.**
  These are configuration facts, not task tests:
  - tool support for implementer roles;
  - structured output where a role's format needs it;
  - a verified route window of at least the context ceiling, with the maximum output covering the
    reserve (ADR-003);
  - a pinned route;
  - `data_use` recorded.
- **Automatic use is limited to eligibility.** The default, automatic fallback and automatic escalation
  select only models marked eligible for that role. A model listed without eligibility for a role is
  never used automatically for it.
- **Selection: the cheapest per token among role-eligible models, on their pinned routes.**
  - "Cheaper" means no more expensive on both input and output, and strictly cheaper on at least one.
  - Where input and output prices cross, use a declared role-specific input:output blend, recorded with
    its basis.
  - On a tie, the China-origin model comes first (the operator's original preference).
  - Cost per successful task is not the selection metric. It is a later reporting measure (ADR-012).
- **Initial eligibility** is the explicit per-role configuration in decision 8, subject to the summarizer
  check and structural requirements.
  - Tier membership alone grants no role eligibility.
  - Models listed without a role assignment, including GLM 5.3 Flash, remain disabled for that role.
  - Changes follow the approved-snapshot process in decision 4.
  - The operator can change this at any time: "Model selection will change throughout the life of the
    project and should be configurable".

**4. Configurable, with an approved snapshot.**

- Reviewed defaults ship with Optimus. An optional operator override file is merged over them.
- **The same validator runs on the merged result.** Eligibility and `data_use` conditions survive an
  override.
- The effective merged registry is snapshotted and **hashed into the Plan 9.96 launch approval.**
  - A change needs re-approval; drift after approval is refused.
  - Host and Gateway validate the same snapshot.
  - No in-memory runtime edit bypasses approval.

**5. Enforcement.**

- The Gateway accepts only models and routes in the approved snapshot.
- `OPTIMUS_AGENT_MODEL` must be a listed ID or `auto`.
- The IDE model picker offers "Auto" plus the eligible models.

**6. Maintenance.** A free script reads OpenRouter's public catalog and endpoints, and reports drift:
prices, windows, routes, new versions and `expiration_date`. It never edits the registry; changes go
through a reviewed PR.

**7. Muse Spark 1.3 Contributor is admitted, on the operator's judgment, with a warning.**

- **Operator decision (2026-09-30):** "To my knowledge, both are essentially the same. Given the price
  difference, I would go with Contributor."
  - The identity of the two tiers is therefore **accepted on the operator's judgment.** It is **not
    independently established**: Meta's pricing and Models pages list separate IDs and do not attest shared
    weights, and secondary sources claim the same checkpoint.
  - No equivalence test is required.
- **The one known difference is a setting.** Meta's Models page says the `max` reasoning level is
  "available on Standard tier only". The Contributor tier therefore runs at up to `xhigh`, and results
  published at `max` do not describe it. This corrects an earlier draft's "identical specs".
- **A warning comes before every Contributor request,** including routed, fallback and summarizer
  requests. The operator asked for "a warning/notification". It says the provider may use supplied code
  and tool content for training, not only personal information.
- **Meta's documented direct-API rate limits** (Contributor: 100 requests/min, 3,000,000 tokens/min) are
  per team. They are not assumed to be the OpenRouter quota.
- **Reconfigure if it disappoints.** If observed behaviour diverges from Muse Spark 1.3, the operator
  changes the configuration; the registry makes that a one-line change.

**8. The resulting initial configuration.** These are pinned-route prices in USD per million tokens,
input / output. The operator can change any of it.

This configuration reflects the operator's decisions on open items 5–7. The operator said, verbatim, on
2026-09-30: "Go with your recommendations on all three".

- **Cheap tier (medium tasks), in per-token order:**
  1. **Muse Spark 1.3 Contributor, $0.10 / $0.20: the default,** with a warning. This is the operator's
     explicit choice.
  2. DeepSeek V4.1 Flash, $0.15 / $0.60.
  3. Gemini 3.8 Flash, $0.75 / $3.75, replacing 3.7.
  4. Muse Spark 1.3 Standard, $1.25 / $4.25.

  **GLM 5.3 Flash is not eligible for medium tasks** (item 5). It is the weakest cheap-tier model on the
  qualifying benchmarks. It stays listed in the registry without eligibility, so the operator can
  re-enable it.
- **Cheap tier (complex tasks, and the escalation target):**
  1. **Gemini 3.8 Flash, $0.75 / $3.75** (item 6). On the qualifying benchmarks it is level with or above
     GLM 5.3, at a lower price.
  2. GLM 5.3, $1.40 / $4.40, as the fallback. It is the more expensive of the two.

  How complex tasks are told apart from medium ones is for ADR-007 and ADR-009.
- **Ultra-cheap tier:**
  - **Easy tasks: Luna** ($0.10 / $0.50). **Qwen 3.7 Flash is not eligible for easy coding tasks**
    (item 7): it has no coding evidence.
  - **Summarizer:** Qwen 3.7 Flash ($0.03 / $0.13), then Luna. Each must pass ADR-006's summary quality
    check. Qwen lists no structured-output support, so the validator bars it wherever the summary format
    requires structured output.
- **Review tier:** Sonnet 5.5 ($2 / $10), then Kimi K3 ($3 / $15).
- **Origin rule check (inventory).**
  - Cheap tier: DeepSeek (China), with Muse and Gemini (non-China).
  - Complex role: GLM 5.3 (China) and Gemini (non-China).
  - Ultra-cheap tier: Qwen (China) and Luna (non-China).
  - Review tier: Kimi K3 (China) and Sonnet (non-China).
- **Evidence the operator can use when reconfiguring:** evidence file **section H**, the qualifying
  coding and architecture benchmarks under decision 3. Sections D and D2 relied on Terminal-Bench 4.0,
  which is mixed-domain, and are context only.
  - **GLM 5.3 Flash is the weakest cheap-tier model on software-specific benchmarks** (DeepSWE 63,
    FrontierCode 31.8, Code Migration 7.4). This **reverses** the earlier Terminal-Bench-led reading, and
    it is why the model was made ineligible for medium tasks (item 5).
  - **Gemini 3.8 Flash is strong on software-specific benchmarks.** Independent DeepSWE 74 and SWE-Bench
    Pro private 77.6 are level with or above GLM 5.3, and it costs less per token. It is now the model for
    complex tasks and the escalation target (item 6).
  - **DeepSeek V4.1 Flash** has mostly vendor-reported software scores (DeepSWE 74.2 V). Independently it
    scores Code Migration 37.5 and MacroscopeBench 72.0.
  - **Muse Spark 1.3** has mostly vendor-reported software scores (SWE-Atlas QnA 54.0 at `xhigh`), and
    there are **no results for the Contributor ID.**
  - **Qwen 3.7 Flash has no coding evidence.** It is a vision-language SKU, and it is limited to
    summarizing (item 7).
  - **Sonnet 5.5 leads** every independent software benchmark where it appears. **Kimi K3** has the best
    SWE-Bench Pro private score (78.7), but anomalous Terminal-Bench and Code Migration results.
  - The published loop and tool-call reports are anecdotal incident counts, not failure rates.

## Open items

1. The price-ceiling value, and whether Kimi K3 stays listed ("probably").
2. The structural validator's exact per-role requirements. To be specified in the design spec.
3. Role-specific blend ratios for crossed prices. None cross today.
4. Fallback on a provider error versus escalation on struggle (ADR-009). Per-call attribution of which
   model answered is owned by `P11.26-CAND-2-TELEMETRY-CONTRACT`.
5. **Resolved:** GLM 5.3 Flash is not eligible for medium tasks.
6. **Resolved:** Gemini 3.8 Flash is the model for complex tasks and the escalation target, with GLM 5.3 as
   its fallback.
7. **Resolved:** Qwen 3.7 Flash is limited to summarizing, and Luna handles easy tasks.

   All three were resolved by the operator on 2026-09-30: "Go with your recommendations on all three".

## Consequences

- **Easier:**
  - cost control through model choice (the operator's preferred lever);
  - adopting new models is a configuration change;
  - Auto routing (ADR-007), capacity checks (ADR-003) and summarizer choice (ADR-006).
- **Harder:**
  - Someone maintains the registry; the drift script reduces that to reviewing a diff.
  - Without qualification tests, a weaker model can be a default until telemetry shows it. Loop control
    (ADR-009), review (ADR-008) and alerts (ADR-005) are the safety nets, and reconfiguring is quick.
- **Sequencing.** The operator's removal of Haiku (ADR-003) takes effect in the implementation that ships
  the registry. Until then the current code's default is unchanged. No implementation is commissioned by
  this record.
- **The registry is a prerequisite** for compaction, Auto routing and cost alerts. It is suggested as the
  first slice.
