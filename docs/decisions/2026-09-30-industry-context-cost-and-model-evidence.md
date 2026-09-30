# Evidence: industry context and cost practice, and the model catalog (2026-09-30)

**What this is.** The evidence that decision records ADR-003 to ADR-009 rely on. It is a dated snapshot,
not a live document.

**How the evidence was collected, and how far to trust it:**

- **Agent practices:** Claude's research subagents read official docs and source code at HEAD on
  2026-09-30. They read pages through a summarizing fetch tool, so the key constants are sourced but not
  audited line by line. Anything a vendor does not document is marked "not documented".
- **Prices and windows:** OpenRouter's public `GET /api/v1/models` catalog, fetched 2026-09-30 (464
  models). Prices change often; re-check before relying on them.

## A. How coding agents manage the context window

| Agent | Compaction trigger (default) | Headroom | Default strategy | Summarizer model | Window of an unknown model | Dollar cap |
|---|---|---|---|---|---|---|
| Claude Code | Near the model's limit (about 967K on 1M models); `CLAUDE_CODE_AUTO_COMPACT_WINDOW` [1] | None documented | Clear old tool output, then summarize; `/compact` [2] | Same model, reusing the cache [3] | `CLAUDE_CODE_MAX_CONTEXT_TOKENS` override [1] | `--max-budget-usd` in print mode only, off by default [5] |
| Codex CLI | 90% of the window [7] | Effective window 95%: "headroom for system prompts, tool overhead, and model output" [7] | Summary + recent user messages up to 20K tokens; warns that repeated compactions reduce accuracy [8] | Same model [8] | Falls back to 272K [9] | None [10] |
| Copilot (VS Code) | Background at about 80%, emergency at 90% [14] | About 30% reserved for output [16] | Summarize older rounds, keep recent ones verbatim; `/compact` [12][15] | Same endpoint [15] | Not documented | GitHub billing budgets [17]; `chat.agent.maxRequests` = 25 [13] |
| Aider | History cap: window/16, clamped to 1K–8K tokens [18][19] | On overflow, error, then asks the user [21] | Recursive summary; about half the budget kept verbatim [20][21] | Cheaper "weak model" first, main model as fallback [21] | Warns, then uses defaults [19] | None; shows cost per message [21] |
| OpenHands | 80 events (keeps the first 4), or a token trigger [23] | Runs after context errors [23] | First events + summary + recent events [24] | Copy of the agent model; cost tagged separately [25] | 16K minimum; otherwise not documented [44] | V0 `max_budget_per_task`, default 0 (no limit) [26]; V1 none [27] |
| Cline | About 81% (0.9 × 0.9) [28] | Built into that 0.9 × 0.9 [28] | Summary + about 20K recent tokens; truncation as fallback [28][29] | Active model, or a configured summarizer [28] | 128K [28] | None documented |
| Goose | 80%, `GOOSE_AUTO_COMPACT_THRESHOLD` [33] | None documented | Summarize, then a strategy: summarize, truncate, clear or prompt [33] | Session model [34] | 128K [33] | None; `GOOSE_MAX_TURNS` = 1000 [33] |
| opencode | About 90% (10% buffer) [35] | 10% [35] | Summary + recent 15K tokens [35] | Session model: "no separate compaction model" [35] | 200K context, 32K output [36] | None documented |

**What the model makers say:**

- Anthropic: "As token count grows, accuracy and recall degrade", which it calls context rot [38]. Its
  API compaction triggers at 150,000 input tokens by default [39].
- No OpenAI headroom guidance was found beyond what Codex's source encodes [41].

**Patterns:**

- **Trigger:** among the eight surveyed agents, compaction triggers at a percentage of each model's own
  window, typically 80–90%. None of them was found to use one fixed number across models.
- **Headroom:** an explicit reserve of 5–30% is common.
- **Strategy:** a summary plus a verbatim recent tail of about 15–20K tokens. Truncation is a fallback or
  an option.
- **Summarizer:** usually the session's own model. Aider tries a cheap model first; Cline and OpenHands
  let you configure one.
- **Unknown models:** a fixed guess of 128K–272K. Wrong guesses fail silently, and open issues describe
  exactly that [32].
- **Dollar caps:** rare and off by default. Agents rely on billing budgets, request or turn caps, or
  showing the cost.

## B. OpenRouter controls used by the records

Checked 2026-09-30:

- **Provider routing** [45]:
  - `order`, `only` and `ignore`;
  - `allow_fallbacks`;
  - `data_collection: "allow" | "deny"`;
  - `zdr`;
  - `require_parameters`;
  - `sort`;
  - `max_price` in USD per million tokens, strictly enforced;
  - a separate `models` array for falling back from one model to another.
- **`max_tokens`** caps output tokens [45].
- **Automatic caching** [46]:
  - OpenAI, Grok, Moonshot AI, Groq, DeepSeek, Z.AI and Gemini 2.5+ cache without `cache_control`;
  - OpenAI GPT-5.6+ charges cache writes at 1.25× input "even with automatic caching";
  - DeepSeek charges cache writes at the input price;
  - Gemini adds storage;
  - Anthropic caches only with a `cache_control` field.
- **API keys** accept `limit` (USD) and `limit_reset` (daily, weekly or monthly) [47].

## C. Catalog snapshot of the tier models (USD per million tokens)

| Tier (ADR-004) | Model | Origin | Input | Output | Cache read | Cache write | Window | Max output | Structured outputs |
|---|---|---|---|---|---|---|---|---|---|
| Ultra-cheap | `qwen/qwen3.7-flash` | China | 0.03 | 0.13 | 0.006 | 0.038 | 1,000,000 | 65,536 | no |
| Ultra-cheap | `openai/gpt-6-luna` | US | 0.10 | 0.50 | 0.01 | 0.125 | 1,050,000 | 128,000 | yes |
| Cheap | `deepseek/deepseek-v4.1-flash` | China | 0.0198 | 0.396 | 0.0029 | — | 1,048,576 | 943,718 | yes |
| Cheap (candidate) | `z-ai/glm-5.3-flash` | China | 0.15 | 0.50 | 0.03 | — | 1,048,575 | 943,717 | yes |
| Cheap | `google/gemini-3.7-flash` | US | 0.75 | 3.75 | 0.075 | 0.042 | 1,048,576 | 65,536 | yes |
| Cheap | `z-ai/glm-5.3` | China | 1.40 | 4.40 | 0.26 | — | 1,048,575 | 943,717 | yes |
| Review | `anthropic/claude-sonnet-5.5` | US | 2.00 | 10.00 | 0.20 | 2.50 | 1,000,000 | 128,000 | yes |
| Review | `moonshotai/kimi-k3` | China | 3.00 | 15.00 | 0.30 | — | 1,048,576 | 943,718 | yes |
| Removed (ADR-003) | `anthropic/claude-haiku-4.5` | US | 1.00 | 5.00 | — | 1.25 | 200,000 | 64,000 | yes |
| Excluded (ADR-004) | `anthropic/claude-opus-5.5` | US | 4.00 | 20.00 | 0.20 | 5.00 | 1,000,000 | 128,000 | yes |
| Excluded (ADR-004) | `anthropic/claude-fable-5.1`, `openai/gpt-6-astra` | US | 10.00 | 50.00 | | 12.50 | about 1M | 128,000 | yes |

**Provider routes matter.** From OpenRouter's public `/api/v1/models/<id>/endpoints`, 2026-09-30:

- **DeepSeek V4.1 Flash**
  - 33 endpoints.
  - The cheapest, $0.0198 / $0.396, is a third-party **fp4** build.
  - DeepSeek's own endpoint is $0.15 / $0.60.
  - Most others are fp8 builds at $0.08–$0.30 input.
- **GLM 5.3 Flash**
  - 33 endpoints.
  - The cheapest, $0.02 / $0.2475, is a third-party **fp4** build.
  - Z.AI's own endpoint is fp8 at $0.15 / $0.50.
- **Headline prices:** the catalog prices in the table above are the cheapest route, not the first-party
  route.

**Jev entries:**

- `typesafe/jev-router` is listed with price `-1` (variable) and a 1,000,000 window. It "picks the best
  model and reasoning effort for each request", so its price is that of the model it picks.
- Jev itself, the System One decision model, is served through `/api/v1/systemone`, not chat
  completions. It returns typed answers only.

## D. Coding capability of the tier models (research sweep, 2026-09-30)

**Comparability warning:**

- V = vendor-reported, I = independent, nf = not found.
- Vendor Terminal-Bench scores use different versions (2.1, 3.0, 4.0) and different harnesses, so they
  cannot be compared across rows. Only the Artificial Analysis (AA) columns are like-for-like.
- SWE-bench Verified is now regarded as contaminated and saturated [D1], so vendors report DeepSWE
  instead.
- **Operator rule (2026-09-30, ADR-004 decision 3):** only coding-specific and software-architecture
  benchmarks guide model selection. Two sources used in sections D and D2 are **context only, not
  selection evidence**:
  - the **AA Intelligence Index**, which blends many domains;
  - **Terminal-Bench 4.0**, where only 18 of 66 tasks are software. It is a secondary check only.

  **Section H lists the qualifying benchmarks and supersedes the conclusions of sections D and D2** for
  selection.
- Several numbers come from secondary aggregators. Treat them as indicative until Optimus runs its own
  evaluation.

| Model | DeepSWE v1.1 | AA Terminal-Bench 4.0 (I) | AA Intelligence Index v4.3.2 (I) | AA Coding Agent Index (I, with harness) | AA cost per task |
|---|---|---|---|---|---|
| GLM 5.3 Flash | 63.4 V; 63.4 I (Together) [D2][D3] | 33% | 42 | nf | $0.25 [D4] |
| GLM 5.3 | 66.9 V; 69.0 I (Together) [D3][D5] | 42% | 45 | 53.6 (OpenCode) [D6] | $2.01 [D4] |
| DeepSeek V4.1 Flash | 74.2 V (mini-SWE, Max reasoning; vendor scaffold table, where other scaffolds score 65.5–72.6) [D7] | 27% | 39 | nf | $0.27 at DeepSeek's own list price [D8] |
| Gemini 3.7 Flash | 65.3 V [D9] | 14% | 39 | nf | $0.93 [D10] |
| Qwen 3.7 Flash | nf | not listed | not listed | nf | nf |
| GPT-6 Luna | 66.6 V [D11] | 13% | 37 | 41.1 (Codex) [D6] | $0.07 [D12] |
| Claude Sonnet 5.5 | 71.0 V | 64% | 56 | 68.4 (Claude Code) [D6] | $7.60 [D13] |
| Kimi K3 | 67.5 V | 13% | 44 | 51.9 (Kimi Code CLI) [D6] | $2.00 [D14] |

**Findings that matter for the records:**

- **GLM 5.3 Flash** is the strongest cheap-tier model on the independent numbers. It is about one
  eighth of GLM 5.3's cost per task. On average the gap to GLM 5.3 is modest: about 9 AA
  Terminal-Bench points, 3 index points and about 6 DeepSWE points.
  - The gap is wider on hard, flaky tasks. In Together's 900-rollout study, Flash gained less from
    reasoning longer (46% against 61%), and it broke already-passing tests more often (6.9% against
    4.4%) [D3].
  - **Together's cascade, Flash first then escalating to GLM 5.3 when tests fail, solved 80.9% of
    DeepSWE at $1.70 per task [D3].**
- **GLM 5.3 Flash has the most independent loop reports** among these models:
  - 220+ identical tool calls over about 25 minutes (Pi #9637, 2026-09-15);
  - announcing tool calls it never issues (kilocode #14475, open);
  - reasoning that degenerates into repeated characters on some self-hosted stacks.

  AA also rates it slow (44 tokens/s) and very verbose [D4].
- **Per-token price and per-task cost disagree.**
  - Verbosity and step counts differ between models. For example, Kimi K3 costs more per token than
    Sonnet 5.5 but less per task ($2.00 against $7.60).
  - "Cheaper" should therefore be measured per successful task where possible.
- **Qwen 3.7 Flash** has no coding benchmarks.
  - OpenRouter shows an 8.88% tool-call error rate.
  - One secondary source reports its $0.03/$0.13 price applies only to short contexts, rising to
    $0.20/$0.80 above 256K [D15]. That is unverified.
- **GPT-6 Luna** is the cheapest per task, but weak at agentic coding (13% on AA Terminal-Bench 4.0). It
  fits summarizing and easy tasks.
- **Gemini 3.7 Flash** is weak value at its price: 14% at $0.93 per task.
- **Kimi K3** scores 13% on AA Terminal-Bench 4.0, against Sonnet 5.5's 64%. Terminal-Bench measures
  agentic terminal work, not code review, so its relevance to the review role is limited.

## D2. Cheap-tier default and the non-Chinese slot (research sweep, 2026-09-30)

**Head-to-head for the everyday cheap-tier default.** AA figures are independent (I); DeepSWE boards
differ in harness.

| Metric | DeepSeek V4.1 Flash | GLM 5.3 Flash | GLM 5.3 (escalation) |
|---|---|---|---|
| Released | 2026-09-10 | 2026-08-26 | 2026-08-18 |
| AA Intelligence v4.3.2 | 39 | 42 | 45 |
| AA Terminal-Bench 4.0 | 27% | 33% | 42% |
| DeepSWE v1.1 (I) | 71.7% (Mercor) [G1] | 63%, $0.24/task (Datacurve) [G2] | 69%, $3.99/task (Datacurve) [G2] |
| AA output speed | 209 tokens/s | 44 tokens/s | 71 tokens/s |
| AA time per task | 319 s | 1,113 s | not found |
| AA cost per task | $0.27 | $0.25 | $2.01 |

Sources: [G3][G4][G5].

**Reliability reports.** These are independent but anecdotal; no failure rates are published.

- **DeepSeek V4.1 Flash.** Loops were reported through one gateway, while DeepSeek's own API was clean
  [G6]. There was also a ~35-minute first-party incident with no `tool_calls` on 2026-09-22 [G7], and a
  vLLM parser break [G8].
  - Reports cluster at gateways and parsers, not at the first-party API.
- **GLM 5.3 Flash.** More session-breaking tool-call failures:
  - announced but never-issued calls, through a third-party provider [G9];
  - raw `<tool_call>` markup on 100% of the traffic on one gateway route [G10];
  - reasoning degenerating into "!!!" on SGLang fp8 with 3+ tools [G11];
  - truncated arguments in 4 of 54 forced tool choices on vLLM [G12].

  One counter-report was withdrawn [G13].
- **No per-provider quality measurements** and no OpenRouter tool-call error rates were found.

**Non-Chinese cheap-tier candidates.**

| Model | Released | $/M input / output | AA Intelligence | AA TB 4.0 | AA Coding Agent Index (harness) | DeepSWE (I) | AA cost per task |
|---|---|---|---|---|---|---|---|
| Gemini 3.8 Flash (high) | 2026-09-02 | 0.75 / 3.75 | 41 | 20% | 41.9% (Antigravity SDK) | 74%, $2.36 | $1.24 |
| Gemini 3.7 Flash (reference) | 2026-08 | 0.75 / 3.75 | 39 | 14% | not found | 65%, $2.03 | $0.93 |
| GPT-6 Luna (max) | 2026-09 | 0.10 / 0.50 | 37 | 13% | 41.1% (Codex) | not found | $0.07 |
| GPT-6 Luna Pro | 2026-09-22 | 0.10 / 0.50 listed | not measured | not measured | not measured | not measured | "several times" a Luna request [G14] |
| Muse Spark 1.3 (Meta, max) | 2026-09 | 1.25 / 4.25 | 48 | 33% | 54.3% (Muse Code) | 75.4% (secondary source) | $1.60 |
| Grok 4.7 (xhigh) | 2026-09 | 2.00 / 6.00 | 46 | 26% | 56.3% (Grok Build) | not found | $3.74 |
| GPT-5.4 mini; Gemini 3.5 Flash-Lite; Mistral Small 4 | 2026 | 0.15–0.75 input | 11–24 | 0–2% | not found | not found | $0.02–$0.45 |

Sources: [G15]–[G20].

**Findings:**

- **Gemini 3.8 Flash is a real improvement on 3.7** at the same token price: +6 points on TB 4.0 and +9
  on independent DeepSWE.
  - It uses 65% more tokens, so it costs 33% more per task.
  - It returns `MALFORMED_FUNCTION_CALL` intermittently in forced-validated function-calling mode; AUTO
    mode fixed it [G21].
- **Muse Spark 1.3** was the only surveyed non-Chinese candidate matching GLM 5.3 Flash on TB 4.0 (33%),
  at about 6× its cost per task.
- **The sweep found no cheap xAI coding model that is generally available** [G22].
- **Muse Spark 1.3 Contributor** (`meta/muse-spark-1.3-contributor`), from the OpenRouter catalog and
  endpoints, 2026-09-30:
  - $0.10 / $0.20 per million, served only by Meta, 1M window, tools supported, released 2026-09-02;
  - described as the "cost-efficient contributor tier ... for experimentation, learning, and early-stage
    agentic, multi-agent, and coding workflows";
  - **not benchmarked**, and whether it uses the same weights as Muse Spark 1.3 is not documented.
  - Secondary sources report that the Contributor tier means "your prompts and outputs may be used to
    improve Meta's products" [G23][G24]. Retention, human review, deletion, and whether tool calls count
    as prompts are undocumented [G24].
  - **Meta's primary pricing page** [G25] lists `muse-spark-1.3` and `muse-spark-1.3-contributor` as
    separate model IDs and does not state that they share weights.
    - Data terms, verbatim: Standard, "your prompts and completions are not used to train Meta models";
      Contributor, "permission to use your prompts and completions to train future Meta models".
    - Rate limits: Standard 3,000 requests/min and 4,000,000 tokens/min; Contributor 100 requests/min and
      3,000,000 tokens/min.
    - No retention or opt-out terms are given.
  - **Secondary sources** say the two IDs are the same checkpoint with identical published specs
    [G26][G27]. However:
    - **Meta's Models page** [G29] says the `max` reasoning level is "available on Standard tier only",
      so the tiers do **not** expose identical settings.
    - The page states only that the Contributor variant "trades a lower price for permission to train on
      your prompts and completions".
    - It does not attest shared weights.
  - **Meta's best 1.3 benchmark results** came from a "max reasoning configuration" that is not broadly
    available [G28]. Results at `max` cannot qualify the Contributor tier.
- **Qwen 3.7 Flash** is served only by Alibaba at $0.03 / $0.13 (endpoints, 2026-09-30).

## H. Qualifying coding and software-architecture benchmarks (research sweep, 2026-09-30)

This section applies the operator's rule (ADR-004 decision 3): only the most up-to-date benchmarks that
are **specific to software coding and architecture** guide model selection.

**Main correction.** Terminal-Bench 4.0 is **not software-only.** Only 18 of its 66 tasks are in its
Software category [H6], and Google's own results table files it under "General agent capabilities"
[H29]. It is demoted to a secondary check. Sections D and D2 above leaned on it, so their conclusions
are superseded by this section.

**How far to trust these numbers.** V = vendor-reported, I = independent.

- **Mirrored:** the Artificial Analysis and Cognition FrontierCode figures were read from BenchLM mirrors
  (2026-09-29), because the primary pages load their data with JavaScript.
- **Calculated:** the SWE-Bench Pro V2 private-set percentages were computed from Scale's solved-task
  counts.
- **Inferred:** Scale's "Hard" figures appear to be a 51-task subset.

**Which benchmarks qualify:**

| Benchmark | Measures | Contamination resistance | Still separates models? | Verdict |
|---|---|---|---|---|
| **SWE-Bench Pro V2, private set** (2026-09-22) [H1][H2] | Bug fixes and features, agentic | 272 private commercial tasks; Scale calls the public set contaminated | Yes (~78–82%) | **Include** (private set only) |
| **DeepSWE v1.1** (2026-06-15) [H4] | Long-horizon feature work, 113 tasks, fixed harness | Tasks written from scratch, canary string | Yes (69–75%) | **Include** (independent board rows) |
| **FrontierCode 1.1** (2026-07-17) [H11] | Would a maintainer merge the PR: correctness, tests, scope, style, maintainability | 100 private tasks | Yes (top 54%) | **Include** (maintained by Cognition, which sells a coding agent) |
| **SWE-Atlas** (QnA, Refactoring, Test Writing) [H10] | Codebase comprehension, 35% of QnA being architecture and system design; refactoring graded on maintainability | Public repos; an LLM judge grades | Yes (49–63%) | **Include** (the architecture and refactoring proxy; few target models covered) |
| **Vals Code Migration** (2026-09-29) [H12] | Re-implementing programs in another language, including COBOL to Java | Private, hidden tests | Yes (top 70%) | Include (secondary) |
| **MacroscopeBench** (2026-09-22) [H13] | Finding bugs in PR review | Bugs mined from repo history | Yes | Include for the **review** role (maintained by a review-tool vendor) |
| Terminal-Bench 4.0 [H5][H6][H7] | Terminal work across 7 domains; only 18 of 66 tasks are software | Public tasks | Yes | **Secondary only** (mixed domain) |
| AA Coding Agent Index v1.5 [H8] | DeepSWE + TB 4.0 + SWE-Atlas QnA, per model and harness | Inherits from its parts | Yes | Use its components, not the blend |
| SWE-bench Verified; SWE-bench Multilingual; LiveCodeBench; Aider Polyglot; SWE-rebench; CodeClash; SWE-Lancer; Multi-SWE-bench; SWE-PolyBench; KernelBench; SAKE | Various | Contaminated, saturated, stale, niche, or no current results | — | **Exclude** [H3][H16]–[H23] |
| AA Intelligence Index; AA Coding Index (inside a general index); Vals Index; LMArena; HLE; GPQA | General or mixed-domain | — | — | **Exclude** [H9][H35] |

**Scores of the candidate models.**

Column key:

- Pro-priv = SWE-Bench Pro V2 private set (independent, mini-swe-agent, 2026-09-22).
- FrontierCode = FrontierCode 1.1 Main.
- CodeMig = Vals Code Migration (independent, 2026-09-29).
- nf = not found.

| Model | Pro-priv | DeepSWE v1.1 | FrontierCode | SWE-Atlas | CodeMig | MacroscopeBench | TB 4.0 (secondary) |
|---|---|---|---|---|---|---|---|
| Muse Spark 1.3 | nf | 75.4 V (`max`) [H24]; not on the board | nf | QnA 54.0 V (`xhigh`) / 59.4 V (`max`) [H24] | 40.4 (`max`) | nf | 33.3 I |
| **Muse Spark 1.3 Contributor** | **nf** (no results for this ID; it runs at up to `xhigh` [H25], so the `xhigh` figures are the proxy) | nf | nf | nf | nf | nf | nf |
| GLM 5.3 Flash | nf | 63±4 (board; who ran it is unconfirmed); 63.4 V [H26] | 31.8 | nf | 7.4 | nf | 32.8 I |
| GLM 5.3 | 77.6 (211 of 272) | 69±3 (board; runner unconfirmed); 66.9 V [H27] | 40.1 | nf | 35.6 | 77.4 | 41.9 I |
| DeepSeek V4.1 Flash | nf | 74.2 V (mini-SWE, Max reasoning; vendor scaffold table) [H28] | nf | nf | 37.5 | 72.0 | 26.8 I |
| **Gemini 3.8 Flash** | **77.6** (211 of 272) | **74±1 I** (high); 73.7 V [H29] | 41.2 | QnA 47.0; Refactoring 44.8; Test Writing 53.7 (I) | 25.9 | nf | 19.7 I |
| Qwen 3.7 Flash | nf | nf | nf | nf | nf | nf | nf. It is a vision-language SKU, and Alibaba published no coding benchmarks [H30] |
| GPT-6 Luna | nf | 66.6 V (`max`) [H31] | 42.4 (listed as self-reported) | nf | 37.2 | nf | 12.6 I |
| **Claude Sonnet 5.5** | nf (81.3 V; set not stated) [H32] | 71.0 V [H32] | **52.1** (listed as self-reported) | nf | **69.8** | nf | 63.6 I |
| Kimi K3 | **78.7** (214 of 272) | 69±5 I (`max`); 67.5 V [H33] | 44.2 | nf | 1.5 (anomalous) | 72.9 | 12.6 I |

**What changes from sections D and D2** (the Terminal-Bench-led picture):

- **GLM 5.3 Flash is the weakest cheap-tier model on software-specific benchmarks**: DeepSWE 63,
  FrontierCode 31.8, CodeMig 7.4. It is no longer "the strongest cheap model".
- **Gemini 3.8 Flash moves up sharply.** Independent DeepSWE 74 and Pro-priv 77.6 are level with or
  above GLM 5.3, the proposed escalation model. On FrontierCode it scores 41.2 against GLM 5.3's 40.1.
  It costs less per token ($0.75 / $3.75 against $1.40 / $4.40).
- **Kimi K3 moves up.** It has the best Pro-priv score (78.7), DeepSWE 69 and FrontierCode 44.2. Its
  Terminal-Bench (12.6) and CodeMig (1.5) results suggest harness or reliability problems.
- **GPT-6 Luna is understated by Terminal-Bench:** FrontierCode 42.4 and CodeMig 37.2.
- **Evidence for DeepSeek V4.1 Flash and Muse Spark 1.3 on software benchmarks is mostly vendor-reported.**
  **There is no result at all for the Contributor ID.**
- **Claude Sonnet 5.5 leads** every independent software benchmark where it appears.
- **Qwen 3.7 Flash has no coding evidence.**
- **Summarizing coding conversations:** no benchmark fits. The closest proxy is SWE-Atlas Codebase QnA.
  An in-house check is better, which supports the operator's decision to keep ADR-006's summarizer check.

## E. How coding agents handle unproductive loops (research sweep, 2026-09-30)

| Agent | Signals and thresholds | On detection | Default |
|---|---|---|---|
| OpenHands SDK | Same action and observation 4 times; the same action erroring 3 times; A–B alternation over 6 cycles; 3+ agent messages with no user input [E1][E2] | At an error streak of 3, one corrective message; otherwise status `STUCK` and the run halts. A new user message resets detection [E2] | On; `max_iteration_per_run=500` [E1] |
| Cline | Consecutive mistakes; an identical tool-call signature, soft at 3 and hard at 5 [E3][E4] | Soft: "try a different approach". Hard: counts to the mistake limit. The CLI asks "Try a different approach / Stop this run" [E4][E5] | On; retries 3 (CLI) or 6 (SDK) [E4] |
| Copilot (VS Code) | Request count only; no identical-call detector (open issue) [E6] | "Continue to iterate?": Continue raises the limit 1.5×, or Cancel. Autopilot raises it up to 200; Advanced Autopilot uses a completion classifier [E7][E8] | `chat.agent.maxRequests` (docs say 25; source falls back to 50) [E9] |
| Claude Code | Not documented; an open request for a `doom_loop` gate [E10] | `--max-turns` and `--max-budget-usd` in print mode only [E11] | No turn limit |
| Codex CLI | No repetition detector found; an open "infinite loop" issue [E12]. In goal mode it audits its own progress, and marks itself blocked after the same blocker in 3+ turns [E13] | The goal is blocked or budget-limited; `/goal resume` continues [E14] | Goal token budget |
| Goose | Turns without user input; identical consecutive tool calls [E15] | At max turns it asks "Would you like me to continue?"; repeated calls are denied [E15] | Max turns 1000; the repetition limit is off unless set |
| Aider | Lint, test and format errors fed back as "reflections" [E16] | After 3: "Only 3 reflections allowed, stopping." Control returns to the user [E16] | Hardcoded 3 |
| opencode | Same tool with identical input 3 times; misses A–B–A–B (open issue) [E17][E18] | A permission prompt: once / always / reject [E17] | `doom_loop` = "ask" |
| Gemini CLI | Identical tool call 5 times; repeated text 10 times. After 30 turns an LLM judge runs, needing ≥0.9 confidence confirmed by a second model [E19] | First: inject "take a step back". Second: abort the turn, and ask whether to keep detection on [E19] | On |
| SWE-agent | Format, blocklist or syntax errors; a linter rejects broken edits [E20] | After 3 requeries, exits and autosubmits [E20] | `max_requeries=3` |

**Research:**

- Hybrid structural and semantic cycle detection reached F1 0.72, against 0.08 for structural alone and
  0.28 for semantic alone [E21].
- Cheap per-step monitors caught 71% of failures at a 5% false-alarm rate. Rolling back and re-running
  raised task success from 52% to 73% [E22].
- In SWE-agent's analysis, 51.7% of trajectories had at least one failed edit, and after one failure
  eventual edit success fell from 90.5% to 57.2% [E23].

**Pattern:** a deterministic counter at 3–5, then a corrective nudge, then a pause that hands control to
the user with explicit options. Hard stops are kept for headless runs, and a new user message resumes.

## F. TypeSafe Jev (research sweep, 2026-09-30)

- **API.** `POST /api/v1/systemone`. `state` is text (a string, JSON or an array) with a keyed
  `questions` map. The question types are:
  - `noul` (yes/no, returning P(true));
  - `choice` (up to 255 options, with per-option probabilities and a confidence);
  - `score` (2–10 levels) [F1][F2][F3].
- **Confidence** measures how concentrated the probabilities are, not correctness [F4].
- **Context.** 32K on OpenRouter. TypeSafe says 64K, of which 32K is for state plus question [F2][F5].
- **Price and speed.**
  - $0.042 per million input tokens, output free.
  - Median about 175–217 ms, p95 about 339 ms (OpenRouter snapshot) [F2][F6][F7].
  - TypeSafe's direct API allows 100K tokens/s and 40 requests/s [F2].
- **Calibration is disputed.**
  - TypeSafe and OpenRouter's explainer say calibrated [F5][F8].
  - OpenRouter's benchmark says "not a calibrated probability", with overestimates in the mid-range. It
    ranks well: 96.3% accuracy at confidence ≥0.99, and 29.6% below 0.5.
  - Banking77: 81.0% for Jev, against 84.4% for Opus 5 [F7].
  - Answers vary by up to 0.08 across repeated calls [F9].
- **Documented uses:**
  - routing and triage;
  - classification;
  - gating agent tool calls: approve at ≥0.9, block at ≤0.1, send the rest to a human [F9];
  - auto-approving coding-agent *commands*, not diffs [F10];
  - the "Overseer" off-task and destructive-step checks [F11];
  - a verified cascade [F12].
- **Not evaluated:**
  - code or diff review. Community tools only, unvalidated [F13];
  - judging an agent's progress over a trajectory.
- **Limits.** No text output or explanations; no arithmetic or date maths; English primarily.
- **`jev-router`** is a chat-completions router.
  - It scores each turn's difficulty and whether the task changed, and chooses a model and effort level.
  - Its candidate models are undocumented, its price is variable (`-1`), and its claimed benchmark
    results are not public [F14][F15].

## Sources

- [1] https://code.claude.com/docs/en/model-config
- [2] https://code.claude.com/docs/en/how-claude-code-works
- [3] https://code.claude.com/docs/en/prompt-caching
- [5] https://code.claude.com/docs/en/cli-reference
- [7] https://raw.githubusercontent.com/openai/codex/main/codex-rs/protocol/src/openai_models.rs
- [8] https://raw.githubusercontent.com/openai/codex/main/codex-rs/core/src/compact.rs
- [9] https://raw.githubusercontent.com/openai/codex/main/codex-rs/models-manager/src/model_info.rs
- [10] https://learn.chatgpt.com/docs/config-file/config-reference
- [12] https://code.visualstudio.com/docs/agents/concepts/context
- [13] https://code.visualstudio.com/docs/copilot/reference/copilot-settings
- [14] https://raw.githubusercontent.com/microsoft/vscode/main/extensions/copilot/src/extension/prompts/node/agent/backgroundSummarizer.ts
- [15] `summarizedConversationHistory.tsx`, in the same directory as [14]
- [16] https://github.com/orgs/community/discussions/188691
- [17] https://docs.github.com/en/copilot/how-tos/manage-and-track-spending/manage-request-allowances
- [18] https://aider.chat/docs/config/options.html
- [19] https://raw.githubusercontent.com/Aider-AI/aider/main/aider/models.py
- [20] https://raw.githubusercontent.com/Aider-AI/aider/main/aider/history.py
- [21] https://raw.githubusercontent.com/Aider-AI/aider/main/aider/coders/base_coder.py
- [23] https://raw.githubusercontent.com/OpenHands/software-agent-sdk/main/openhands-sdk/openhands/sdk/context/condenser/llm_summarizing_condenser.py
- [24] https://docs.openhands.dev/sdk/arch/condenser
- [25] https://docs.openhands.dev/sdk/guides/context-condenser
- [26] https://docs.openhands.dev/openhands/usage/v0/advanced/V0_configuration-options
- [27] https://github.com/OpenHands/OpenHands/issues/17691
- [28] https://raw.githubusercontent.com/cline/cline/main/sdk/packages/core/src/extensions/context/compaction-shared.ts
- [29] https://docs.cline.bot/features/auto-compact
- [32] https://github.com/cline/cline/issues/14550
- [33] https://goose-docs.ai/docs/guides/sessions/smart-context-management
- [34] https://raw.githubusercontent.com/aaif-goose/goose/main/crates/goose/src/context_mgmt/mod.rs
- [35] https://opencode.ai/v2/docs/compaction/
- [36] https://opencode.ai/v2/docs/models/
- [38] https://platform.claude.com/docs/en/build-with-claude/context-windows
- [39] https://platform.claude.com/docs/en/build-with-claude/compaction-threshold
- [41] https://developers.openai.com/api/docs/guides/compaction
- [44] https://raw.githubusercontent.com/OpenHands/software-agent-sdk/main/openhands-sdk/openhands/sdk/llm/llm.py
- [45] https://openrouter.ai/docs/guides/routing/provider-selection
- [46] https://openrouter.ai/docs/guides/best-practices/prompt-caching
- [47] https://openrouter.ai/docs/api-reference/api-keys/create-api-key

**Section D:**

- [D1] https://benchlm.ai/benchmarks/swe-bench-verified
- [D2] https://docs.z.ai/guides/vlm/glm-5.3-flash
- [D3] https://www.together.ai/blog/glm-5-3-vs-glm-5-3-flash-on-deepswe-cost-coding-and-routing (2026-08-28)
- [D4] https://artificialanalysis.ai/models/comparisons/glm-5-3-flash-vs-glm-5-3
- [D5] https://docs.z.ai/guides/llm/glm-5.3
- [D6] https://benchlm.ai/benchmarks/aacodingagents (2026-09-29)
- [D7] https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash
- [D8] https://artificialanalysis.ai/models/comparisons/deepseek-v4-1-flash-vs-glm-5-3-flash
- [D9] https://storage.googleapis.com/deepmind-media/gemini/gemini_3-7_flash_model_evaluation.pdf
- [D10] https://artificialanalysis.ai/models/comparisons/glm-5-3-flash-vs-gemini-3-7-flash
- [D11] https://emergent.sh/learn/gpt-6-luna-benchmarks
- [D12] https://artificialanalysis.ai/articles/gpt-6-sol-and-luna-push-the-cost-efficiency-frontier
- [D13] https://artificialanalysis.ai/models/comparisons/glm-5-3-flash-vs-claude-sonnet-5-5
- [D14] https://artificialanalysis.ai/models/comparisons/glm-5-3-flash-vs-kimi-k3
- [D15] https://www.eesel.ai/blog/qwen-3-7-flash-review

**Section D2:**

- [G1] https://www.mercor.com/apex/oss-benchmarks/oss-deep-swe-leaderboard/
- [G2] https://deepswe.datacurve.ai/
- [G3] https://artificialanalysis.ai/models/comparisons/deepseek-v4-1-flash-vs-glm-5-3-flash
- [G4] https://artificialanalysis.ai/models/comparisons/glm-5-3-vs-glm-5-3-flash
- [G5] https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash
- [G6] https://github.com/anomalyco/opencode/issues/51839
- [G7] https://github.com/CommandCodeAI/command-code/issues/909
- [G8] https://github.com/vllm-project/vllm/issues/58640
- [G9] https://github.com/Kilo-Org/kilocode/issues/14475
- [G10] https://github.com/AuraHQ-ai/aura/issues/1515
- [G11] https://github.com/sgl-project/sglang/issues/36669
- [G12] https://github.com/vllm-project/vllm/issues/55541
- [G13] https://github.com/sgl-project/sglang/pull/37925
- [G14] https://openrouter.ai/api/v1/models/openai/gpt-6-luna-pro/endpoints
- [G15] https://deepmind.google/models/model-cards/gemini-3-8-flash/
- [G16] https://artificialanalysis.ai/models/comparisons/gemini-3-8-flash-vs-gemini-3-7-flash
- [G17] https://artificialanalysis.ai/models/comparisons/gpt-6-luna-vs-gemini-3-8-flash
- [G18] https://artificialanalysis.ai/models/comparisons/muse-spark-1-3-vs-gemini-3-8-flash
- [G19] https://artificialanalysis.ai/models/comparisons/grok-4-7-vs-gemini-3-8-flash
- [G20] https://benchlm.ai/benchmarks/aacodingagents (a mirror of the AA Coding Agent Index, 2026-09-29)
- [G21] https://github.com/heyhuynhgiabuu/pi-oauth-antigravity/issues/2
- [G22] https://docs.x.ai/developers/release-notes
- [G23] https://www.threads.com/@testingcatalog/post/DcUbco-DQv8/ (a secondary report of the Muse Spark 1.2
  Contributor launch)
- [G24] https://theaicareerlab.com/blog/meta-muse-spark-1-3-for-professionals-2026 and
  https://miraflow.ai/blog/meta-muse-spark-1-3-contributor-tier-explained-2026 (secondary sources)
- [G25] https://dev.meta.ai/docs/pricing-rate-limits (Meta, the primary source)
- [G26] https://www.orcarouter.ai/blog/muse-spark-1-3-contributor-vs-muse-spark-1-3 (secondary source)
- [G27] https://codersera.com/blog/muse-spark-1-3-complete-guide-2026/ (secondary source)
- [G28] https://venturebeat.com/technology/meta-says-muse-spark-1-3-has-frontier-performance-but-its-best-results-come-from-a-model-developers-cant-broadly-use-yet
- [G29] https://dev.meta.ai/docs/models (Meta, the primary source; checked 2026-09-30 by both Claude and
  Codex)

**Section H:**

- [H1] https://labs.scale.com/blog/swe-bench-pro-v2
- [H2] https://labs.scale.com/leaderboard/swe_bench_pro_public_v2
- [H3] https://www.vals.ai/benchmarks/swebench and https://www.latent.space/p/swe-bench-dead
- [H4] https://deepswe.datacurve.ai/ (with its changelog and blog)
- [H5] https://artificialanalysis.ai/evaluations/terminalbench-4-0
- [H6] https://snorkel.ai/leaderboard/terminal-bench-4-0/
- [H7] https://www.vals.ai/benchmarks/terminal-bench-4
- [H8] https://artificialanalysis.ai/methodology/coding-agents-benchmarking
- [H9] https://artificialanalysis.ai/articles/artificial-analysis-intelligence-index-v4-3
- [H10] https://labs.scale.com/leaderboard/sweatlas-qna (plus the refactoring and test-writing boards)
- [H11] https://cognition.com/frontiercode and https://benchlm.ai/benchmarks/frontiercode
- [H12] https://www.vals.ai/benchmarks/code-migration
- [H13] https://macroscope.com/content/ai-code-review-benchmark-best-models
- [H16] https://www.vals.ai/benchmarks/lcb
- [H17] https://aider.chat/docs/leaderboards/
- [H18] https://swe-rebench.com/
- [H19] https://codeclash.ai/
- [H20] https://llm-stats.com/benchmarks/swe-lancer
- [H21] https://llm-stats.com/benchmarks/multi-swe-bench
- [H22] https://amazon-science.github.io/SWE-PolyBench/
- [H23] https://benchlm.ai/benchmarks/kernelbenchhard
- [H24] https://research.meta.ai/static/muse-spark-1-3-multimodal-evaluation-methodology
- [H25] https://github.com/can1357/oh-my-pi/issues/11788
- [H26] https://huggingface.co/zai-org/GLM-5.3-Flash
- [H27] https://huggingface.co/zai-org/GLM-5.3
- [H28] https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash
- [H29] https://storage.googleapis.com/deepmind-media/gemini/gemini_3-8_flash_model_evaluation.pdf
- [H30] https://www.eesel.ai/blog/qwen-3-7-flash-review
- [H31] https://www.vellum.ai/blog/gpt-6-sol-and-luna-benchmarks-explained
- [H32] https://www.anthropic.com/claude-sonnet-5-5 and
  https://llm-stats.com/blog/research/claude-sonnet-5-5-launch
- [H33] https://huggingface.co/moonshotai/Kimi-K3
- [H35] https://www.vals.ai/benchmarks/vals_index

**Section E:**

- [E1] https://docs.openhands.dev/sdk/guides/agent-stuck-detector
- [E2] https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/stuck_detector.py
- [E3] https://github.com/cline/cline/blob/main/sdk/packages/core/src/runtime/safety/loop-detection.ts
- [E4] https://github.com/cline/cline/blob/main/sdk/packages/core/src/runtime/orchestration/session-runtime-orchestrator.ts
- [E5] https://github.com/cline/cline/blob/main/apps/cli/src/runtime/interactive/mistakes.ts
- [E6] https://github.com/microsoft/vscode/issues/336767
- [E7] https://github.com/microsoft/vscode/blob/main/extensions/copilot/src/extension/intents/node/toolCallingLoop.ts
- [E8] https://code.visualstudio.com/docs/agents/run/approvals
- [E9] https://code.visualstudio.com/docs/agents/reference/ai-settings
- [E10] https://github.com/anthropics/claude-code/issues/73307
- [E11] https://code.claude.com/docs/en/cli-reference
- [E12] https://github.com/openai/codex/issues/42444
- [E13] https://github.com/openai/codex/blob/main/codex-rs/ext/goal/templates/goals/continuation.md
- [E14] https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex
- [E15] https://github.com/aaif-goose/goose/blob/main/crates/goose/src/agents/state_machine/ops_maxturns.rs
- [E16] https://github.com/Aider-AI/aider/blob/main/aider/coders/base_coder.py
- [E17] https://opencode.ai/docs/permissions/
- [E18] https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/processor.ts
- [E19] https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/services/loopDetectionService.ts
- [E20] https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/agent/agents.py
- [E21] https://arxiv.org/abs/2511.10650
- [E22] https://arxiv.org/abs/2608.02464
- [E23] https://arxiv.org/abs/2405.15793

**Section F:**

- [F1] https://openrouter.ai/docs/api/api-reference/systemone/submit-a-system-one-request
- [F2] https://docs.typesafe.ai/models
- [F3] https://docs.typesafe.ai/primitives/choice
- [F4] https://docs.typesafe.ai/confidence
- [F5] https://openrouter.ai/blog/insights/what-is-jev/
- [F6] https://openrouter.ai/~typesafe/jev-latest
- [F7] https://openrouter.ai/blog/insights/jev-vs-claude-opus-5-classification/
- [F8] https://docs.typesafe.ai/concepts/system-one
- [F9] https://openrouter.ai/docs/cookbook/building-agents/gate-tool-calls-with-jev
- [F10] https://openrouter.ai/docs/cookbook/coding-agents/auto-approve-permission-prompts-with-jev
- [F11] https://openrouter.ai/labs/jev/overseer
- [F12] https://openrouter.ai/docs/cookbook/evaluate-and-optimize/jev-verified-cascade
- [F13] https://github.com/ty-machine/jev-pr-risk-evaluator
- [F14] https://openrouter.ai/typesafe/jev-router
- [F15] https://gigazine.net/gsc_news/en/20260928-openrouter-jev-router/

**Loop reports:**

- https://github.com/earendil-works/pi/issues/9637
- https://github.com/Kilo-Org/kilocode/issues/14475
- https://github.com/anomalyco/opencode/issues/45533
- https://github.com/vllm-project/vllm/issues/56868
