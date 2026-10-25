# Plan 12.4 — Auto mode: classify each turn into a tier

- **Goal:** an opt-in Auto mode. Each turn is classified easy, medium or complex, and sent to an eligible model for that tier. The classifier is chosen by a pre-registered pilot experiment run first: rules, Jev, Haiku with a written prompt, Haiku optimised by DSPy, and a rules-first hybrid.
- **Authority:**
  - **The operator, 2026-10-23, verbatim:** "I think I did not read your message correctly - for Auto we need to research Jev vs DSPy first. Make "Auto" a separate plan and loop control another".
  - **The operator, 2026-09-30, verbatim** (ADR-007): "So the "Auto" mode should classify into one of these three and assign from them, it is here I was thinking of Jev".
  - **ADR-007 is Proposed and frozen.** Its acceptance is a new record, written after the experiment.
- **Workflow** (operator, 2026-10-23):
  - Claude implements, and Codex reviews through the CLI at two checkpoints. Fable is consulted only if Claude judges a point complex.
  - Each task runs only its own tests; the full suite runs once at the end. There is no WSL run: Linux CI failures are fixed in the PR.
- **Base:** current main. It is independent of loop control Phase 1, except that escalation on a misroute is loop control Phase 3, after this plan.
- **Estimate:** **10–14 active days**, toward the upper end (Codex's figure, accepted). It excludes approval, service and paid-run waits.
- **Research:** the Jev-versus-DSPy research report, posted verbatim on #395. Its repository claims were checked by Claude, with one corrected: origin is only a price tie-breaker (`src/optimus_model_policy/validation.py:182-184`).
- **Revisions:** Codex's reviews are posted verbatim on #395. Each version was checked by Claude against main.

| Version | Codex verdict | Findings | Review |
|---|---|---|---|
| v1 (`c32dc1cf…`) | rework | 9; v2 addressed them, and its mapping table still applies | posted on #395 (`c404c3bd…`) |
| v2 (`aa7ac3dc…`) | rework | 6 remaining; v3 addressed them, and its mapping table still applies | posted on #395 (`ac9ec184…`) |
| v3 (`d731c059…`) | **approve with changes** | 2 bounded corrections; v4 applied them as specified | posted on #395 (`2bae3d03…`) |
| v4 (`6a11703b…`) | — | v5 adds the operator's decisions and the A4 sources, and sets the plan number (P1) | — |
| v5, as reviewed (`296a724d…`) | **approve with changes** | 6; this version applies them as specified (mapping at the end) | posted on #395 (`9a893918…`) |

## What the research and the reviews change

1. **"Jev versus DSPy" is two separate questions.** One is which model backs the classifier (Jev, or Haiku 5.5). The other is how its prompt is made (by hand, or optimised by DSPy). The pilot tests both, plus rules and a hybrid.
2. **Misroute cost decides, not classifier price.** Even the dearest arm costs at most about 5% of a cheap coding turn.
3. **Auto saves nothing today.** Only Haiku 5.5 is eligible, and no medium model is (`src/optimus_model_policy/defaults.yaml:16-17`, `:195`). A second-tier model must be qualified. **No implementer qualification procedure exists:** Haiku's evidence covers summaries only (`tools/evaluate_context_summarizer.py:1-24`; ADR-023:25-35). This plan defines a small one (Design 2).
4. **The registry machinery needs these extensions:**
   - **Empirical admission is keyed by one model per hash** (`src/optimus_model_policy/experimental.py:67-88`).
   - **The classifier role is dormant** (`registry.py:106`; `validation.py:226-228`, `:255-258`).
   - **Every active role's window must reach the global ceiling** of 262,144 tokens (`validation.py:123-130`; `defaults.yaml:25`). Jev's window is 32K, so the classifier needs its own capacity rule.
   - **Settlement has no classification stage** (`src/optimus/usage/turn_settlement.py:38`, `:92-93`).
   - **The Gateway refuses any snapshot that has not been approved** (`src/optimus_gateway/model_policy.py:158-166`; `src/optimus_model_policy/test_profiles.py:104-105`). So every snapshot that makes a call is approved before its calls.
5. **Context capacity is captured at launch** (`src/optimus/acp/context_attachment.py:72-85`; `src/optimus/acp/spec.py:993-1022`). Binding per turn must capture both the route and the context limits per turn.
6. **The existing test profiles pin one planner** (`src/optimus/acp/test_composition.py:37-55`) **and ordinarily omit the Context Engine** (`src/optimus/acp/bootstrap.py:255-294`). So Auto must be a production composition, not a test profile.
7. **Admitting a medium model changes launches without Auto.** The default planner picks the first eligible medium model before easy (`src/optimus/agent/defaults.py:25-28`). Admitting Gemini in the ordinary snapshot would move ordinary launches from Haiku to Gemini (decision A5).
8. **Jev needs a Gateway route even for the pilot.** The Gateway serves only responses, chat completions, traces and tools (`src/optimus_gateway/server.py:94`, `:109-113`), and Claude never holds a provider key.
9. **DSPy stays out of the product.** It pulls in LiteLLM, which had a compromised PyPI release (reported 2026-03-24), and about 20 other dependencies. DSPy runs only in the pilot's own hash-locked environment. If a DSPy arm wins, the product ships its compiled prompt and examples as data, through the existing chat-completions route.

## Decisions (operator, 2026-10-23)

**The operator's words, verbatim:** "P1(a), A1, A2, A3, A5 are approved
A4 - I don't have a prompt library, we could get some samples by searching through archived chats and downloading prompts from a prompt library(ies) from the internet"

| # | Decision | Status |
|---|---|---|
| P1 | Loop control first as Plan 12.3, then Auto as Plan 12.4 | **Approved (a)** |
| A1 | **Paid-call caps:**<br>- the pilot: about $4.4–7 estimated, **$15 cap**, which includes the Jev reachability check;<br>- the Gemini qualification: 10 turns, about $1 estimated, **$5 cap**;<br>- one live acpx slice per routable tier at Checkpoint B: **$2 cap**.<br>ADR-007:78 had authorized no evaluation | **Approved** |
| A2 | Qualify `google/gemini-3.8-flash` (Design 2; the table below) | **Approved** |
| A3 | `OPTIMUS_AGENT_MODEL=auto` as the opt-in, with a one-line notice per turn of the tier and model. The Zed model picker comes later | **Approved** |
| A4 | **The real prompts in the labelled set** come from archived chats and public prompt sets (Design 3, the labelled set) | **Sources set by the operator.** The specific public set (A4-i) and each download (A4-ii) await approval |
| A5 | **(a)** Gemini is admitted only in a separate `auto` snapshot. Ordinary launches keep today's snapshot, so the default stays Haiku. Option (b), not chosen, would have admitted it in the ordinary snapshot | **Approved (a)** |

**The basis for A2** (`defaults.yaml`; every endpoint below is `verified: false`):

| Model | Roles on main | $ in / out per M | Origin | Trains on inputs |
|---|---|---|---|---|
| `google/gemini-3.8-flash` (**Claude's recommendation**) | complex 1st, escalation 1st, medium 3rd (`:192-194`) | 0.75 / 3.75 | non-China | unverified |
| `deepseek/deepseek-v4.1-flash` | medium 2nd | 0.15 / 0.60 | China | unverified |
| `meta/muse-spark-1.3-contributor` (not recommended by Claude) | medium 1st | 0.10 / 0.20 | non-China | **yes** (`:143`) |
| `z-ai/glm-5.3` | complex 2nd, escalation 2nd | 1.40 / 4.40 | China | unverified |
| `meta/muse-spark-1.3` | medium 4th | 1.25 / 4.25 | non-China | unverified |

**Why Gemini 3.8 Flash:**
- **One qualification covers two tiers:** it would be the only eligible model for both medium and complex.
- **It is first for escalation** (loop control Phase 3).
- **Its data use is not known to include training.**
- **It keeps easy as the cheapest tier.**

**What it costs:** about 1.5 times Haiku's price, and about 37% of Sonnet 5.5's ($2 / $10, `:168`). Its quality and data handling are unqualified. Its endpoint's window, output cap and quantization are unrecorded (`:123`); qualification records them (Design 2).

**Why not the others:**
- **Muse Contributor** trains on your code.
- **DeepSeek Flash** is the cheapest model not known to train on inputs, but it is China-origin and its data use is unverified.

## Prerequisites

| Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| Decisions P1, A1–A3 and A5 | yes | The operator, 2026-10-23 | — |
| The decision source: the app's export of this session, registered as Source S10 | yes | Claude, at filing | — |
| **A4-i:** the public prompt set (Design 3): SWE-chat | yes | The operator, at filing | — |
| **A4-ii:** each download, approved by name, source and size (Design 3) | yes | The operator, at filing | — For SWE-chat, the operator also accepts the dataset's conditions and downloads the file, since Claude never signs in or handles a token |
| The operator's archived prompts: 4,977 distinct typed prompts in 1,444 local Claude Code transcripts (counted 2026-10-23, without reading their text) | yes | Claude extracts them at Task 3 | — |
| **Code/state:** empirical admission keyed by snapshot hash and model, preserving Haiku's admission and summarizer receipt | no | Claude, Task 1 | Genuinely absent: buildable now |
| **Code/state:** the classifier role activated narrowly, with its own capacity, estimator and output-reserve rules; a `classification` settlement stage; the Jev Gateway adapter | no | Claude, Task 1 | Genuinely absent: buildable now |
| **Code/state:** a production Auto composition, with per-turn route and context capture and ordinary compaction | no | Claude, Task 4 | Genuinely absent: buildable now |
| **Code/state:** an implementer qualification procedure | no | Claude, Task 2 | Genuinely absent: buildable now (Design 2) |
| The operator's approval of each snapshot hash before its calls: the `evaluation` and `gemini-qualification` snapshots after Task 1, and the finalised `auto` snapshot at Checkpoint A | no | The operator | Merely unauthorized: approvals of reviewed hashes |
| OpenRouter's Jev decision API is reachable through the Gateway's adapter, with the Gateway's existing credentials | unknown | The operator (credentials; Claude never reads or handles a key). Claude probes it after Task 1 and the `evaluation` approval, inside the pilot cap | Genuinely hard: an external dependency. If the provider is unreachable through the working adapter, the Jev arms are dropped and the pilot runs without them. A missing adapter is never a reason to drop them |
| The Gateway and its services (the shared Redis, never stopped by Claude) running for the pilot, the qualification and the live slices | unknown | The operator (machine state) | Merely unauthorized: the operator starts them |
| An isolated pilot environment: Python 3.14 with DSPy 3.4.1 and LiteLLM, pinned by hash, outside the product's `pyproject.toml` | no | Claude, at Task 0 | Genuinely absent: buildable now from PyPI |
| An execution checkout from current main, with its own `.venv` | unknown | Claude inventories it at Task 0 | Merely unauthorized: created when execution is released |
| A second rater for the labelled set: a Codex CLI session, independent of Claude | yes | Claude runs it | — |
| `acpx` 0.12.0, for the qualification's Agent checks and the live slices | unknown | The operator (machine state); Claude checks `acpx --version` at Task 0 | Merely unauthorized: the operator installs or updates it |

**Task 0 settles every `unknown` row it can.** The Jev row is settled after Task 1, before any pilot call depends on it.

## Design

### 1. Registry and admission mechanics (Task 1)

**Admission:**
- **Lookup is by snapshot hash and model,** not by hash alone. Haiku's admission and its summarizer receipt are preserved unchanged.
- **Route stops stay per route and per launch,** as today (ADR-023). A refusal on Gemini's route stops only Gemini's route. Auto then treats that tier as unroutable (Design 4).

**The snapshots** (each with its own hash, approved by the operator before any call it makes; the ordinary snapshot is untouched):

| Snapshot | Kind | What it admits | Approved |
|---|---|---|---|
| `evaluation` | Test profile, used by the pilot harness as a Gateway client | The classifier role, for Jev and Haiku. Jev gets a provisional empirical estimator (as below) | After Task 1, before any pilot call |
| `gemini-qualification` | Test profile, pinned to the one planner Gemini | Gemini for medium and complex:<br>- its route facts come from the provider's published catalogue (a free read);<br>- **its estimator is a provisional empirical one,** pinned before approval, because main refuses a call without one (`src/optimus_model_policy/capacity.py:84-90`; Gemini names `unmeasured` at `defaults.yaml:121`). It has Haiku's conservative shape: 1 token per UTF-8 byte, 16 per message, 256 fixed (`defaults.yaml:28`), and `verified: false` | After Task 1, before any qualification call |
| `auto` | **Production** (Design 4) | Haiku as today; Gemini with the route facts its qualification **observed**; the classifier role for the winning arm, if that arm uses a model | At Checkpoint A, after qualification and the pilot |

**The classifier's own rules,** which leave the implementer and summarizer rules unchanged:
- **A classifier context ceiling,** set from the complete-request bound (Design 3), not the global 262,144.
- **A classifier output reserve:** none for Jev, which returns no free text, and 256 tokens for a Haiku classifier.
- **An empirical estimator for Jev,** kept `verified: false`. The Gateway rechecks each request with the same estimator, as it does for other routes.

**The classifier role stays dormant in every other snapshot.**

**Settlement and the adapter:**
- **Settlement:** a `classification` stage is added, so the classifier's cost is its own stage (ADR-007).
- **The adapter:** the Gateway gains an adapter for Jev's decision API. Usage is recorded, and a typed-request capacity check runs before the provider call.

### 2. Implementer qualification v1 (Task 2)

**The procedure** runs on the approved `gemini-qualification` snapshot. It is scoped to its own model, route and fixtures, and it is never a general quality claim:
- **Route facts:** observe the endpoint's context window, output cap, quantization and provider name. The observed values go into the `auto` snapshot.
- **Estimator:** qualification checks the provisional estimator pinned in the snapshot (Design 1). Its estimate must be at least the billed input on every call. It stays `verified: false`, as Haiku's is.
  - **If the parameters must change,** the changed values go into the `auto` snapshot, whose hash is approved separately at Checkpoint A. They are never adjusted inside the approved qualification snapshot.
- **Grammar:** the planning grammar parses on every Agent fixture.
- **Real checks:** 5 Chat and 5 Agent turns from existing fixtures, through acpx. A cap is checked before each call, and there is no retry until a pass.
  - **Mechanical checks:** a complete finish, no capacity breach, and a valid plan for each Agent turn.
- **The receipt:** Claude and Codex each review the sealed run independently. The receipt is issued only if both pass every item.

### 3. The pilot experiment (Task 3)

**The classifier's input contract, frozen before any labelling or optimisation.** One bounded representation is shared by the dataset, the optimisers and production (ADR-007:73-74):

| Field | What it carries |
|---|---|
| `prompt` | The current prompt's text, cut to the excerpt budget (below), at most its first 4 KB |
| `truncated` | `true` if the prompt was cut |
| `mode` | Chat or Agent |
| `attachments` | The count of attached files or ranges, a total-size bucket (<4 KB, <64 KB, larger), and up to 5 distinct file extensions |
| `previous_tier` | The previous turn's routed tier, if any |

- **Never included:** history or file contents.
- **Raters label the full request,** after redaction and the confidentiality review. The classifier sees only this representation.

**The complete-request bound, frozen with the contract:**
- **One bound for the whole serialized classifier request:** 8,192 estimated tokens, by the route's own estimator. It covers the instructions or template, any few-shot examples, the contract fields, the framing, and the output reserve. Haiku's estimator counts 1 token per byte (`defaults.yaml:28`; `capacity.py:62-67`), so the bound is in estimated tokens, not bytes.
- **The excerpt budget:** for each frozen configuration, the fixed parts are measured once. The prompt excerpt gets what remains, up to 4 KB.
- **Overflow, identical in the pilot and in production:**
  - **Fixed parts that leave no excerpt budget make a configuration invalid.** An example is a DSPy program with too many examples. It is rejected when it is frozen, never at run time.
  - **A longer prompt is cut to the budget,** with `truncated: true`.

**The arms, all through the Gateway on the `evaluation` snapshot:**

| Arm | What it is |
|---|---|
| A | Rules only |
| B | Jev; its variant (`choice` or ordinal `score`) is frozen on dev |
| C | Haiku 5.5 with a hand-written prompt |
| D | Haiku 5.5 optimised by DSPy; the optimiser (BootstrapFewShotWithRandomSearch, MIPROv2 light or GEPA light) is frozen on dev. **Its few-shot examples come only from the hand-written train items,** so that a winning program can ship without any archived or public prompt text |
| H | Rules first; a learned arm decides only the uncertain middle. Its backend and rule thresholds are frozen on dev |

**Two rules apply to every arm:**
- **Low confidence or abstention routes one tier up** (ADR-007). The confidence thresholds are frozen on dev.
- **The test split is evaluated once per frozen configuration,** in 3 repeats.

**The labelled set (a pilot, not a definitive benchmark):**
- **Size and mix:** 300 requests, roughly 30/40/30 easy/medium/complex, so about 45 complex items reach the test split.
  - **120 from the operator's archived chats** (A4):
    - **Which prompts:** only prompts the operator typed, from local Claude Code transcripts, and from Codex's interactive sessions.
    - **Extraction filters:** these are excluded:
      - subagent and sidechain records, and tool results;
      - meta records, and harness-injected messages (anything opening with a tag, and system reminders);
      - compaction summaries and interruption markers;
      - pasted material (pasted-content blocks, and agent text the operator relayed, such as signed Claude or Codex reports);
      - every Codex `codex exec` session, since those carry briefs written by Claude.

      **A record whose authorship is uncertain is excluded.**
    - **Preparation:** deduplicated, sampled across projects and months, and then:
      1. redacted by the existing redaction gate;
      2. **given a local confidentiality review by Claude:** any prompt naming people, clients or confidential matters that the gate cannot catch is dropped, and not edited;
      3. labelled only after both steps.
  - **60 real prompts to coding agents from a public set** (A4-i):
    - **SWE-chat** (Claude's recommendation): prompts to Claude Code, Codex and Gemini CLI from 2026, licensed ODC-BY.
      - **Access:** it is gated, so the operator accepts its conditions on Hugging Face and downloads `conversations.parquet`. The files total 47 GB, but only this one is needed.
      - **Records used:** only those with `turn_type == 'user_prompt'`, never `system_injected`.
      - **The conditions** are read when they are accepted, and must allow sending the excerpts to the pilot's model providers. If they do not, DevGPT is used instead.
    - **The alternative, DevGPT:** developer–ChatGPT conversations from 2023, licensed CC BY 4.0, and open. Its archive, `DevGPT.zip`, is 926.8 MB (Zenodo record 8303722); Claude downloads it, after approval. It is evidence about developer chat, not about coding-agent use, and is reported as such.
    - **The public items get the same confidentiality review** as the archived ones.
  - **60 SWE-bench Verified items:** the 500-row test split, 2.1 MB, downloaded by Claude after approval. Its `difficulty` column (time-to-fix buckets) is an independent check on the labels.
  - **60 hand-written edge cases:** short but dangerous, long but trivial, questions, and review requests.
- **Handling:**
  - **Downloaded files** go into their own empty folder, and are read only by scripts run in isolated mode.
  - **The prompt text stays outside the repository,** in the local review kit beside the worktrees.
  - **The repository gets the aggregate results and a content-free manifest.** For each item, the manifest holds:
    - its SHA-256 digest;
    - its source and provenance class;
    - its source version and licence;
    - any modification (cut or redacted);
    - its split and group;
    - both raters' labels;
    - every arm's prediction.

    That is enough to recompute every metric without the private text.
  - **What leaves the machine, in full:**
    - **The raters:** each redacted, reviewed request goes in full to Claude (Anthropic) and to Codex (OpenAI).
    - **The pilot's calls:** the contract representation, with at most 4 KB of prompt excerpt, goes through the Gateway to Jev's provider (no training on it; retention is not stated) and to Anthropic (Haiku).
  - **Licences:**
    - **Kept:** each public item's source, version, licence notice and modification record.
    - **ODC-BY** covers the SWE-chat database, not the individual prompts. CC BY attribution applies to anything from DevGPT that is published.
    - **Publication:** no public or private prompt text is published, other than the shipped examples below.
- **The rubric:**
  - **easy:** one file, explicit and mechanical;
  - **medium:** 2–5 files or one module, or a bounded investigation;
  - **complex:** crosses modules, open-ended debugging, or touches security, data or concurrency.
- **Raters:** two independent raters, Claude and Codex, with Cohen's kappa reported. **Disagreements take the higher label,** since routing up is the safe direction.
- **Deduplication** runs across all sources, before the split.
- **The split:** 100 train / 50 dev / 150 test, stratified by class and source.
  - **It is grouped,** so that prompts from the same conversation or task never cross splits.
  - **Optimisation and every threshold** see train and dev only.

**The metrics.** Each is computed on the final routed tier, after any route-up, with requests as the sampling unit:
- **The penalty score:** under-routing costs 3 per tier, over-routing 1 per tier. Sensitivity runs at 2× and 5×. It is a penalty, not dollars.
- **The registry-weighted cost:** reported separately, at the eligible models' real prices.
- **The under-route rate:** the fraction of test requests whose first repeat routes below their label.
- **The flip rate:** the fraction of test requests whose final routed tier is not the same in all 3 repeats, with caching off.
- **Per source:** every metric is reported for each source alongside the pooled figure.
- **The rest:** accuracy and macro-F1; the route-up rate; latency p50 and p95 through the Gateway; classifier cost per 1,000 requests, from Gateway accounting; expected calibration error.
- **How they are reported:** each gate is an observed rate, with a Wilson interval. Paired differences use a bootstrap over requests.

**The decision rule (pre-registered, fixed before any run):**
1. **The gates apply to every arm, A and H included.** An arm passes if its observed under-route rate is at most 5%, and its observed flip rate is at most 5%.
2. **Among the passing arms, the lowest mean penalty score wins.** A learned arm (B, C, D or H) must beat A on penalty, with a 95% paired-bootstrap interval that excludes zero. Otherwise A wins, if A passes.
3. **Ties** (two passing learned arms whose paired difference has an interval that includes zero) go to the lower measured cost per 1,000 requests, then to the lower p95 latency. So C wins only by passing, beating A, and winning on these rules.
4. **No arm passes:** there is no winner. Phase B does not start, and the evidence goes to the operator.

**Budget enforcement:**
- **Per-call caps:** the complete-request bound. That is 8,192 estimated tokens, with 256 output tokens reserved inside it for Haiku and none for Jev. The cap is reconciled with the bound before any run.
- **Reservations versus spend:** reservations use the estimate, which runs high, and are released at settlement. The cap applies to billed spend.
- **Fixed ceilings:** the optimiser trials and the GEPA metric calls are fixed.
- **Proposer calls** count against the cap.
- **Retries:** only the Gateway's existing ones.
- **Calls run sequentially,** each with a cost reservation before it. **An unknown cost stops the run.**

**The first calls:**
- **The Jev reachability probe** (Prerequisites).
- **Then a smoke test:** 10 calls per arm through the real Gateway. It checks the DSPy binding and parsing, and that repeats really run with caching off, all inside the cap.

**The output:** an evidence report with the content-free manifest, and a draft acceptance record for ADR-007 naming the arm that the rule selects, or "no winner".

### 4. Minimal opt-in Auto (Tasks 4–5)

**A production composition:**
- **The bootstrap:** `OPTIMUS_AGENT_MODEL=auto` (today refused at `src/optimus/agent/defaults.py:50-51`) extends the ordinary path (`src/optimus/acp/bootstrap.py:255-294`) to load the approved `auto` snapshot. It keeps the Context Engine and ordinary compaction.
- **Not a test profile:** it is not built on the test profiles, which pin one planner.
- **Testing:** it is tested through the real launch path.

**Each turn:**
1. **Classify the turn** from the input contract.
2. **Map the tier to its role.**
3. **Pick the cheapest eligible model,** using the existing selection.
4. **Capture that model's route and context limits** for this turn.

**Routing up:**
- **Low confidence or abstention** routes one tier up.
- **A tier with no eligible model, or a stopped route,** routes up to the next routable tier.
- **If no tier at or above is routable,** the default planner (ADR-023) is used, and the notice says so.

**Classifier failure:** a failure or timeout counts as an abstention on the medium tier, so the turn routes up, and the notice says why.

**Binding per turn:**
- **Frozen for the turn:** the turn's model, route and context limits (ADR-007).
- **No shared state changes:** the runner sends the turn's bound model, not a launch-time one (`src/optimus/agent/runner.py:349-353`), and no runner or session state is mutated.
- **Unchanged:** the summarizer stays Haiku.

**The classifier backend is whichever arm won:**
- rules need no call;
- Jev uses the production Gateway adapter;
- DSPy ships its compiled prompt as data, through chat completions.

**The record and the notice:**
- **The record:** a content-free routing record per turn (arm, tier, confidence band, model). The classifier's cost goes in the `classification` stage.
- **The notice:** one line per turn in the ACP session, for example "Auto: medium → google/gemini-3.8-flash".

**Without `auto`, nothing changes,** under A5(a).

## Tasks and checkpoints

| Task | Work | Targeted tests |
|---|---|---|
| 0 | **Records:** none beyond Source S10.<br>**Checks:** settle the `unknown` prerequisites it can; build the pilot environment; freeze the input contract (Design 3) | `tests/unit/docs`, after staging |
| 1 | **The registry and admission mechanics (Design 1):**<br>- admission by hash and model;<br>- the classifier's capacity, estimator and reserve rules;<br>- the narrow activation of the classifier role;<br>- the `classification` stage;<br>- the Jev adapter;<br>- the `evaluation` and `gemini-qualification` snapshots.<br>**Then the operator approves those two hashes** | the model-policy, settlement and Gateway unit tests, including Haiku's admission and implementer capacity unchanged |
| 2 | **Qualify Gemini (Design 2),** alongside Task 3; record its observed route facts | the qualification checks; the model-policy tests |
| 3 | **The pilot (Design 3):** the Jev probe, the smoke test, the labelled set and kappa, the harness, the runs, the analysis, the evidence report and the draft ADR-007 acceptance | the harness's own self-checks |
| **Checkpoint A** | **Codex CLI review** of Tasks 0–3 and the evidence.<br>**The operator decides** the ADR-007 acceptance, and approves the finalised `auto` hash. If there is no winner, the plan stops here | — |
| 4 | **The production Auto composition:** the resolver, routing up, capture of the route and context limits per turn, ordinary compaction, and failure handling | `tests/unit/agent` and `tests/unit/acp`: through the real launch path; successive turns on different models; concurrent sessions; no shared-state mutation |
| 5 | The production classifier backend, the routing record, the per-turn notice, and the opt-in | the backend's tests; `tests/unit/acp` (the notice) |
| **Checkpoint B** | **The full suite once,** plus Ruff; the PR; fix Linux CI in the PR; a **Codex CLI review** of the full diff; one live acpx slice per routable tier, within the A1 cap | — |

## Acceptance

**The pilot:**
- It ran under the pre-registered rule and the frozen input contract, within its cap.
- The evidence report shows every arm's metrics on the test split, with intervals.
- The operator accepted the result: the selected arm, or no winner.

**Gemini:**
- It holds a qualification receipt under Design 2, taken on the approved `gemini-qualification` snapshot.
- It is admitted only in the approved `auto` snapshot, under A5(a), with its observed route facts.
- Haiku's admission, its summarizer receipt and implementer capacity are unchanged.

**The resolver**, with `OPTIMUS_AGENT_MODEL=auto`, through the real launch path:
- each turn is classified and sent to the cheapest eligible model of its tier, with that model's route and context limits captured for the turn;
- ordinary compaction still works;
- it routes up as specified;
- concurrent sessions do not interfere.

**The record and the notice:** every Auto turn records its routing decision, with the classifier's cost in the `classification` stage, and shows its notice.

**No change without Auto:** without `auto`, the snapshot, the default model and behaviour are unchanged.

**Live:** one live acpx slice per routable tier passes, or is recorded as UNRUN if not released.

**Final checks:** the full suite and Ruff pass once at the end, and CI is green.

## Explicit Exceptions

Each row names its owning issue.

| Deferred | Owning issue |
|---|---|
| Escalation to a stronger model after a misroute (ADR-009, rung 2) | #397 (loop control Phase 3, shared with Plan 12.3) |
| The ACP model picker in Zed (ADR-004) | #398 |
| Auto as the default | #398 |
| Qualifying further models, and a general (not fixture-scoped) quality evaluation | #398 |
| The user-facing savings report (the Auto / Sonnet 5.5 / Opus 5.5 table, with the benchmark footnote) | #248 |
| The typed telemetry boundary for the routing record | #303 |

## Codex review (v5) corrections mapping

| # | Correction | Applied in |
|---|---|---|
| 1 | Confidentiality review; full disclosure of what the raters see | Design 3 (preparation; what leaves the machine) |
| 2 | Extraction filters for authorship | Design 3 (extraction filters; SWE-chat's records) |
| 3 | Licences, and shipping DSPy examples | Design 3 (licences; arm D's examples) |
| 4 | Deduplication across sources, grouped splits, per-source results | Design 3 (the split; per source) |
| 5 | A content-free manifest | Design 3 (handling; the output) |
| 6 | The `yes/no/unknown` cell | Prerequisites (the archived-prompts row) |

## Codex re-review (v3) corrections mapping

| # | Correction | Applied in |
|---|---|---|
| 1 | Gemini's bootstrap estimator | Design 1 (the `gemini-qualification` row); Design 2 (estimator) |
| 2 | The complete-request bound | Design 3 (the input contract, the complete-request bound, budget enforcement) |

## Codex re-review (v2) findings mapping

| # | Finding | Addressed in |
|---|---|---|
| 1 | Qualification's approval cycle | Design 1 (the `gemini-qualification` snapshot); Design 2; Task 1; Prerequisites |
| 2 | Classifier capacity below the global ceiling | What changes, item 4; Design 1 (the classifier's own rules) |
| 3 | The Jev probe needs the adapter first | Prerequisites (the Jev row); Design 3 (the first calls); Task 3 |
| 4 | Auto is a production composition | What changes, item 6; Design 4; Task 4; Acceptance |
| 5 | The classifier's input contract | Design 3 (the input contract); Task 0 |
| 6 | The flip gate, defined | Design 3 (the metrics, the decision rule) |
