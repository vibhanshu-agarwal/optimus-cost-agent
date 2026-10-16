"""Author the v2.20 / v2.43 / v1.9 successor page sources from the sealed v2.19 / v2.42 / v1.8 sources.

Reads the sealed packet copy (never the sealed original), applies asserted in-place edits to the
inherited page bodies, adds replacement bodies for LLD pages that were carried natively in v2.42,
and writes the complete editable sources into the repository bundle. Every edit is an exact
``replace(old, new)`` that fails loudly when the inherited text has drifted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PACKET = Path(sys.argv[1])  # working copy of the sealed plan12-closure-offline-review packet
BUNDLE = Path(sys.argv[2])  # docs/sources/capability-evidence-correction in the worktree
PIN = "91fd64a"
PIN_FULL = "91fd64ac78025efe1076bddb106ff89e6adb2030"  # pragma: allowlist secret


def replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise AssertionError(f"expected exactly one match for {old[:80]!r}, found {text.count(old)}")
    return text.replace(old, new)


updates = json.loads((PACKET / "sources" / "page-updates.json").read_text(encoding="utf-8"))
hld, lld, test = updates["hld"], updates["lld"], updates["test"]

STATUS_NOTE = (
    "Capability status at the inspected source " + PIN + " (origin/main, 2026-10-15) is stated locally where it matters and "
    "collected in the appended status section; it changes no accepted requirement."
)

# ----------------------------------------------------------------------------------------------
# HLD
# ----------------------------------------------------------------------------------------------
p = hld["2"]
p = replace(
    p,
    "Before a prompt payload hits the downstream model, the Context Optimization Node constructs structural boundaries. It strips code down to AST-based functional slices, structures static filesystem metadata layouts at the head of the prompt window to maximise verified route input caching, and injects succinct, unambiguous constraints using an Architecture Definition Language (ADL) dialect to minimise context attention allocation.",
    "Before a prompt payload hits the downstream model, the Context Optimization Node constructs structural boundaries. The intended controls are AST-based functional slices, static filesystem metadata placed at the head of the prompt window to maximise verified route input caching, and succinct constraints injected in an Architecture Definition Language (ADL) dialect. At the inspected source (" + PIN + ") the implemented controls are bounded workspace evidence assembly, the Redis structural state store and the optional Context Engine view (§14); an AST slicing component and an ADL constraint injector are specified but not established by inspection (no `ast` import and no ADL grammar under `src/`). See §15.",
)
p = replace(
    p,
    "It intercepts execution blocks and evaluates them via automated, triggered fitness functions before any source mutations are applied to the active working tree.",
    "It intercepts execution blocks and evaluates them via automated, triggered fitness functions before any source mutations are applied to the active working tree. The implemented gate is the composite fitness runner in `optimus.gates` (`FitnessGateRunner` over composition-supplied `FitnessCheck` callables, run against the shadow workspace by `ShadowWorkspaceMutationRunner`); the set of checks is supplied by the composition, not fixed by this document.",
)
p = replace(
    p,
    "Phase 1 implements highly targeted, local validation primitives organised across five operational planes: Scope (Atomic), Automation (Automated), Invocation (Triggered), Return (Static), and Activation (Proactive). These gates intercept code generations mid-flight to fix structural deviations before changes lock into local Git trees.",
    "Phase 1 specifies highly targeted, local validation primitives organised across five operational planes: Scope (Atomic), Automation (Automated), Invocation (Triggered), Return (Static), and Activation (Proactive). These gates intercept code generations mid-flight to fix structural deviations before changes lock into local Git trees. Implementation status: the composite fitness gate runner and shadow-workspace promotion exist and are unit/integration tested; the named architecture-metric checks (PyTestArch, maintainability index/complexity) are intended checks with no dependency, import or test at " + PIN + " (§15).",
)
p = replace(
    p,
    "Unparsed source code is strictly prohibited from entering persistent vector indexes. The storage engine uses standard Redis HASH structures to catalogue structural class signatures, summaries, and relative file paths. Numeric performance histories are channelled separately to a Redis TimeSeries cluster (tracking tokens_input, tokens_output, cost_usd) tagged by unique run_id strings and protected by a hard 30-day retention window policy.",
    "Unparsed source code is strictly prohibited from entering persistent vector indexes. This is a storage-boundary rule for persistent indexes; it does not by itself establish that no source text is disclosed through prompts, logs, conversation history, telemetry metadata or backups, and generated summaries can also carry sensitive content (§14.3). The storage engine uses standard Redis HASH structures to catalogue structural class signatures, summaries, and relative file paths. Numeric performance histories are channelled separately to RedisTimeSeries (tracking tokens_input, tokens_output, cost_usd) tagged by unique run_id strings with a 30-day retention (2,592,000,000 ms, `TS.CREATE` with `TS.ALTER` fallback in `optimus.telemetry.redis_adapter`).",
)
hld["2"] = p

p = hld["3"]
p = replace(
    p,
    "The Gateway process holds one developer-owned aggregator credential\nin its own local configuration or OS credential storage. OpenRouter is the default aggregator.\nVercel AI Gateway is an allowed second OpenAI-compatible endpoint when its Python integration is\nmodest.",
    "The Gateway process holds one developer-owned aggregator credential:\n`OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY`, a Gateway-child-only secret that the launch policy resolves from\n`.env.gateway`, the OS keyring or the ambient environment with recorded provenance and never projects to the\nagent child. OpenRouter is the default aggregator. Vercel AI Gateway is an allowed second OpenAI-compatible\nendpoint by design; no Vercel integration exists at the inspected source (" + PIN + ").",
)
p = replace(
    p,
    "Web search currently shares the OpenRouter credential and balance through a dedicated,\ndeterministic plugin request. Package registry and OSV calls are free public APIs and are not\nfunding paths.",
    "Web search: at the inspected source the Gateway's search provider is Tavily, configured with\n`TAVILY_API_KEY` in the Gateway process only (`optimus_gateway.providers.build_tool_dependencies`,\n`TavilyWebToolProvider`); a second, Gateway-held key and balance therefore exist for search today. The accepted\ntarget is a dedicated, deterministic OpenRouter plugin request sharing the aggregator credential. That target\nwas measured once by the 2026-07-27 architecture spike (`tools/run_openrouter_web_search_spike.py`, run against\nOpenRouter directly) and is not implemented in the Gateway. The one-key property holds for model completions\ntoday; for search it is a target, not a current fact. Package registry and OSV calls are free public APIs and\nare not funding paths.",
)
hld["3"] = p

p = hld["4"]
p = replace(
    p,
    "4. Processing inside the Context Optimization Node [FEEDFORWARD CONTROLS] executing AST Slicing,\n   Polyglot Fallbacks, ADL Constraint Prompt Injection, and Prompt Anchoring for Cache Tuning.",
    "4. Processing inside the Context Optimization Node [FEEDFORWARD CONTROLS]: intended AST Slicing,\n   Polyglot Fallbacks, ADL Constraint Prompt Injection, and Prompt Anchoring for Cache Tuning. At " + PIN + "\n   this step is bounded workspace evidence assembly plus the optional Context Engine view (§14); the AST and\n   ADL components are not established by inspection.",
)
p = replace(
    p,
    "7. Validation inside the Automated Fitness Function Engine [FEEDBACK SENSORS] conducting atomic\n   structural checks via PyTestArch and static code metrics gate assertions (MI / Complexity\n   Check). On FAIL: loops back to Step [6]; on PASS: approves code patch execution path.",
    "7. Validation inside the Automated Fitness Function Engine [FEEDBACK SENSORS]: the composite fitness\n   gate (`optimus.gates`) runs the composition-supplied checks against the shadow workspace. PyTestArch and\n   maintainability-index/complexity checks are intended check implementations; none is a dependency, import\n   or test at " + PIN + ". On FAIL: loops back to Step [6] while the finite planning bounds permit; on PASS:\n   approves the code patch execution path.",
)
p = replace(
    p,
    "9. Real-Time FinOps Console Panel display for IDE Cost Dashboard Live Update Screen.",
    "9. Cost and usage updates delivered to the ACP client as usage notifications; a dedicated IDE FinOps\n   dashboard panel is a client-side intent, not an Optimus component.",
)
p = replace(
    p,
    "Modifications apply to the working tree only after clearing all composite fitness\n  engine gates.",
    "Modifications reach the working tree only through the mediated path:\n  `assert_mutation_allowed` / `MutationGuard`, exact artifact approval and `ShadowWorkspaceMutationRunner`,\n  which promotes shadow changes only after the composition-supplied fitness checks pass. This guarantee\n  covers tool paths that use that runner and is verified by unit and integration tests; it is not a\n  host-wide guarantee over processes outside the agent.",
)
p = replace(
    p,
    "  - `IMPLEMENTATION_DELIVERABLE`: A multi-file change that requires Agent Mode and all release\n    gates.",
    "  - `IMPLEMENTATION_DELIVERABLE`: A multi-file change that requires Agent Mode and all release\n    gates.\n\n  The enumeration continues on the next page with the four-value classification the permission layer uses\n  (`MULTI_FILE_CHANGESET` is the implemented impact class in `optimus.guardrails.permissions`); a\n  `CodeGenerationScope` enum is not present as such at " + PIN + ".",
)
hld["4"] = p

p = hld["6"]
p = replace(
    p,
    "Optimus applies adaptive execution strategies to balance cost, rigor, and reliability. The agent selects Direct Execution, Plan-and-Execute, ReAct, or Reflection based on task ambiguity, mutation risk, and validation outcomes.",
    "Designed strategy policy: Optimus applies adaptive execution strategies to balance cost, rigor, and reliability. The agent selects Direct Execution, Plan-and-Execute, ReAct, or Reflection based on task ambiguity, mutation risk, and validation outcomes.",
)
p = replace(
    p,
    "cost-minimising chain: Provided Context → File Inspection → Plan → Execute → Validate → Targeted Reflection → User Escalation.",
    "cost-minimising chain: Provided Context → File Inspection → Plan → Execute → Validate → Targeted Reflection → User Escalation.\n\n**Implementation status (" + PIN + "):** the strategy names, the LOW/MEDIUM/HIGH rigor tiers with their tool-call and reflection caps, and the Assumption Ledger are design policy. No `RigorLevel`, `ExecutionStrategy` or `AssumptionLedger` type exists under `src/`; telemetry carries `rigor_level` and `generation_scope` as string fields. The active runtime bounds are the ACP planning limits (3 planning turns by default, `OPTIMUS_MAX_PLANNING_TURNS`; 30-minute wall clock; repeated-failure limit 2 for ACP planning), the Gateway per-tool call cap (5 calls per tool per run by default, `OPTIMUS_GATEWAY_TOOL_MAX_CALLS_PER_TOOL`) and the finite loop controls referenced in §13. The min(262144, verified route window) request ceiling is implemented in `optimus_model_policy`, with production enforcement inactive (§14.4).",
)
hld["6"] = p

p = hld["7"]
p = replace(
    p,
    "| Gateway -> OpenRouter | Default approved aggregator/model and separately authorized search path |\n| Gateway -> Vercel | Optional retained model endpoint; not an automatic route substitute |",
    "| Gateway -> OpenRouter | Default approved aggregator/model; the separately authorized search path is a target (see Tavily) |\n| Gateway -> Tavily | Implemented web-search provider at " + PIN + " with its own Gateway-only key; replacement by the aggregator plugin path is pending (§5A) |\n| Gateway -> Vercel | Design option; no integration at the inspected source |",
)
p = replace(
    p,
    "Figure 10.A preserves that boundary and retires the product-budget label.",
    "Figure 10.A preserves that boundary and retires the product-budget label. Separate processes on one loopback network namespace isolate the aggregator credential from the agent process; they do not by themselves confine either process from the rest of the host, and whole-host confinement is not claimed.",
)
hld["7"] = p

p = hld["8"]
p = replace(
    p,
    "AST slices + Redis metadata + ADL + bounded context view",
    "Workspace evidence + Redis metadata + bounded context view (AST/ADL intended)",
)
p = replace(
    p,
    "fitness|Complete candidate + shadow / metric fitness checks",
    "fitness|Complete candidate + shadow fitness checks (composition-supplied)",
)
hld["8"] = p

p = hld["9"]
p = replace(
    p,
    "**PHASE 2 -> Rust Core Rewrite**\nTrigger: Python performance ceiling or team scaling\n\n**PHASE 3 -> Agentic Mesh Topology**\nTrigger: Multi-repo / multi-team deployment\n\nSee: Optimus-Architecture-Roadmap.pdf",
    "**PHASE 2 -> Rust Core Rewrite** (proposed; no Rust source exists in the repository at " + PIN + ")\nTrigger: Python performance ceiling or team scaling\n\n**PHASE 3 -> Agentic Mesh Topology** (proposed)\nTrigger: Multi-repo / multi-team deployment\n\nSee: Optimus-Architecture-Roadmap-v11.pdf, which classifies each phase as implemented, approved requirement or proposed.",
)
p = replace(
    p,
    "| 1. Pre-prompt (Feedforward) | AST slicing + cache anchoring + ADL constraints | Unnecessary tokens sent to expensive models. |",
    "| 1. Pre-prompt (Feedforward) | Bounded workspace evidence and context view today; AST slicing and ADL constraints intended, not established | Unnecessary tokens sent to expensive models. |",
)
p = replace(
    p,
    "| 3. Rigor Budget (Runtime) | LOW/MEDIUM/HIGH tier caps tool calls + reflection passes | Token-doubling on ceremonial planning loops. |",
    "| 3. Rigor Budget (Runtime) | Finite work bounds: planning turns, wall clock, repeated failures and the per-tool call cap (rigor tiers are design policy, §9) | Token-doubling on ceremonial planning loops. |",
)
p = replace(
    p,
    "Hallucination is controlled through a defence-in-depth stack. No single gate is sufficient; all five\nlayers must be active simultaneously.",
    "Hallucination is controlled through a defence-in-depth stack. No single gate is sufficient; all five\nlayers are intended to be active simultaneously. §15 states which layers are implemented at " + PIN + ".",
)
p = replace(
    p,
    "| 1. Context Constraint | ADL rules injected pre-prompt; AST slices only relevant code | Irrelevant context that confuses the model. |\n| 2. Evidence Gate | Assumption Ledger: every architectural claim must be inspected or logged | Unverified claims promoted to implementation decisions. |",
    "| 1. Context Constraint | Bounded workspace evidence and context view (ADL rules and AST slices intended, not established) | Irrelevant context that confuses the model. |\n| 2. Evidence Gate | Evidence-bound decisions as a design rule; no Assumption Ledger artifact at the inspected source | Unverified claims promoted to implementation decisions. |",
)
p = replace(
    p,
    "| 4. Fitness Functions | PyTestArch and static metrics gates | Structurally invalid or low-quality changes. |\n| 5. Reflection Circuit | Bounded reflection with prior-failure summaries | Repeated failure without targeted replanning. |",
    "| 4. Fitness Functions | Composite fitness gate (`optimus.gates`); PyTestArch and static-metric checks intended, not integrated | Structurally invalid or low-quality changes. |\n| 5. Reflection Circuit | Bounded replanning with failure context within finite work limits (reflection passes are design policy) | Repeated failure without targeted replanning. |",
)
hld["9"] = p

p = hld["10"]
p = replace(
    p,
    "- Isolate the developer's aggregator credential in Gateway-owned local configuration or OS\n  credential storage.\n- Route explicitly eligible model IDs through the surviving OpenAI-compatible transport after trusted policy composition.",
    "- Isolate the developer's aggregator credential in the Gateway process: the launch policy resolves it from\n  `.env.gateway`, the OS keyring or the ambient environment with recorded provenance and projects it only to\n  the Gateway child.\n- Route explicitly eligible model IDs through the surviving OpenAI-compatible transport after trusted policy\n  composition (trusted-policy enforcement is built and inactive at " + PIN + ": `ENFORCEMENT_ACTIVE = False`).",
)
p = replace(
    p,
    "- Broker deterministic search, bounded extract, package lookup, and OSV advisory independently.",
    "- Broker web search (Tavily provider at " + PIN + "; the deterministic aggregator plugin is the target), bounded\n  extract, package lookup, and OSV advisory. Independence of the package/OSV routes from search configuration\n  is a requirement not yet met: one `GatewayToolDependencies` bundle is built, and it is `None` when\n  `TAVILY_API_KEY`, the tool Redis URL or the allowed-domain list is missing (LLD §9C.4).",
)
p = replace(
    p,
    "| `OPTIMUS_API_KEY=` | `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=` |",
    "| `OPTIMUS_API_KEY=` | `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=` |\n| | `TAVILY_API_KEY=` (Gateway-only; current search provider) |",
)
hld["10"] = p

p = hld["11"]
p = replace(
    p,
    "| Search | A separate authorized request and annotation path. Package and OSV routes do not depend on search availability. |",
    "| Search | A separate authorized tool request (Tavily provider at " + PIN + "; the aggregator-plugin annotation path is the target). Package and OSV routes are required not to depend on search configuration; at " + PIN + " they are constructed in the same dependency bundle and are unavailable when `TAVILY_API_KEY` is missing (LLD §9C.4). |",
)
p = replace(
    p,
    "Product dollar stops are removed on the reviewed cf9bb9d branch; production context enforcement remains inactive.",
    "Product dollar stops were removed at cf9bb9d and merged to `main` via PR #276 (`c509fc8`, 2026-10-08); production context enforcement remains inactive at " + PIN + ".",
)
hld["11"] = p

p = hld["12"]
p = replace(
    p,
    "| Code coverage | coverage.py, pytest-cov | Target: Optimus product group >=80%, context_engine >=80% and optimus_model_policy >=80% separately; all-source aggregate informational. Test Strategy v1.8 §8A governs. At cf9bb9d CI and the final CP4 gate enforce these floors; the interim hook remains Optimus-only. Safety-critical modules must not regress. |\n| Agent quality | DeepEval, Ragas | Task quality, correctness and groundedness |\n| Adversarial/red-team | PyRIT | Prompt injection, tool-control and trust-boundary validation |\n| Trace observability | OpenTelemetry + OTLP; Phoenix default | Debugging and regression analysis; not code coverage |",
    "| Code coverage | coverage.py, pytest-cov | Implemented and enforced in CI at " + PIN + ": `tools/check_product_coverage.py --run-full-suite` with `tools/product-coverage-groups.json` (Optimus group, context_engine and optimus_model_policy at 80%; Evidence Handoff and the aggregate informational) followed by `tools.testing.coverage_products validate`. The commit hook runs the coverage-free commit profile (`tools.testing.run_profile --profile commit`). Test Strategy v1.9 §8A governs. Safety-critical modules must not regress. |\n| Agent quality | DeepEval, Ragas | Intended; no dependency, import or test at " + PIN + "; UNRUN |\n| Adversarial/red-team | PyRIT | Intended; no dependency, import or test at " + PIN + "; UNRUN. The prompt-injection and MCP-trust fixtures in `tests/unit/guardrails` are offline positive controls for specific guards, not a red-team campaign |\n| Trace observability | OpenTelemetry + OTLP; Phoenix default | Implemented (`optimus_gateway.observability`); the live Phoenix tier is the `requires_phoenix` marked tier and is UNRUN unless a collector is present |",
)
hld["12"] = p

p = hld["13"]
p = replace(
    p,
    "a pre-tool guard that deterministically validates shell, file, MCP, and network calls, sandboxed execution, post-tool audit",
    "a pre-tool guard that deterministically validates shell, file, MCP, and network calls, sandboxed execution (the shadow workspace; OS-level sandboxing is not claimed), post-tool audit",
)
p = replace(
    p,
    "The classifier described here is a reserved architecture capability, not an active production route.",
    "Implemented at " + PIN + " with unit tests under `tests/unit/guardrails`, `tests/unit/agent`, `tests/unit/loops`, `tests/integration/loops` and `tests/unit/skills`: `PermissionPolicy`, `PreToolGuard`, `CommandSafetyValidator` (in-process; Tirith is not a dependency), `ConfigTrustScanner`, `MCPTrustRegistry`, `GoalLoopController` (`optimus/loops/controller.py`) with `LoopBudgetPolicy`, and `SkillRegistry` with `SkillTrustPolicy`. The classifier described here is a reserved architecture capability, not an active production route.",
)
p = replace(p, "Coverage policy is authoritative in Test Strategy v1.8 §8A", "Coverage policy is authoritative in Test Strategy v1.9 §8A")
hld["13"] = p

chapter = (PACKET / "sources" / "14-context-engine.md").read_text(encoding="utf-8")
chapter = replace(
    chapter,
    "It imports no Optimus host, Gateway, security, evidence-handoff, workspace, Redis or provider implementation.",
    "It imports no Optimus host, Gateway, security, evidence-handoff, workspace, Redis or provider implementation. Verified by import inspection at " + PIN + ": `src/context_engine` imports only the standard library, so the zero-dependency property belongs to `context_engine` alone; `optimus_model_policy` additionally imports PyYAML and pydantic.",
)
chapter = replace(
    chapter,
    "Compaction is the default. It retains a newest whole-turn exact tail and summarizes earlier ordinary history.",
    "Selection and packing are deterministic; only the summary text is generated. Compaction and Hybrid invoke the injected summarizer callback; Sliding never does. Compaction is the default. It retains a newest whole-turn exact tail and summarizes earlier ordinary history.",
)
chapter = replace(
    chapter,
    "These are adopted offline test values; production defaults and route activation remain held.",
    "These are adopted offline test values carried by the reviewed test profiles and fixtures (for example `optimus_model_policy/test_profile_qualification.yaml` output reserves 32768/8192), not shipped production defaults; production defaults and route activation remain held.",
)
chapter = replace(
    chapter,
    "Above that floor it refuses readably with OPEN disposition. Availability depends on the actual history, estimator and bounds.",
    "Above that floor it refuses readably with OPEN disposition; the refusal is recoverable and introduces no monetary latch or new fallback mechanism. Availability depends on the actual history, estimator and bounds.",
)
chapter = replace(
    chapter,
    "Recompute at the final Gateway boundary for every actual provider attempt.",
    "Recompute at the final Gateway boundary for every actual provider attempt. When a model has several permitted endpoints, the applicable smallest verified capacity governs. The estimator is a conservative verified byte-ratio estimate (`ceil(r * UTF8_bytes)` with non-negative overhead), not exact tokenization.",
)
chapter = replace(
    chapter,
    "The release implements this disclosed exception offline; its verbatim D7 record still needs saved transcript provenance at filing.",
    "The release implements this disclosed exception offline; its verbatim D7 record is filed in ADR-018 from registered ADR-011 source S4 (decision 2026-10-04, filed 2026-10-07).",
)
chapter = replace(
    chapter,
    "This does not claim active enforcement or a shipped-default change; normal bootstrap remains inactive until separately released.",
    "This does not claim active enforcement or a shipped-default change; normal bootstrap remains inactive until separately released. At " + PIN + ": `ENFORCEMENT_ACTIVE = False` and `trusted_snapshot()` returns `None` (`optimus_model_policy/binding.py`); the shipped alias `claude-haiku` resolves to `anthropic/claude-haiku-4.5`.",
)
chapter = replace(
    chapter,
    "Product dollar stops and remaining-dollar prompts are removed on the reviewed cf9bb9d branch. Independently capped evaluation remains capped. This branch result does not claim main is merged or production context enforcement is active.",
    "D6's requirement is preserved: there is no product dollar stop. Product dollar stops and remaining-dollar prompts were removed at cf9bb9d and merged to `main` via PR #276 (`c509fc8`, 2026-10-08). Independently capped evaluation remains capped, and such separately authorized evaluation spend caps are not product cost stops. Production context enforcement remains inactive.",
)
chapter = replace(
    chapter,
    "There is still no production constructor of ContextAttachment; the reviewed named test composition supplies it only within its approved test process.",
    "There is still no production constructor of ContextAttachment (verified at " + PIN + ": no `src/` path constructs it, and its docstring records this); the reviewed named test composition supplies it only within its approved test process.",
)
chapter = replace(
    chapter,
    "No publication or merge follows from draft acceptance.",
    "v2.19 and the offline implementation were merged via PR #276; that merge activated nothing. Auto classification, the final reviewer step, the savings report and package publication keep their own implementation and activation status (§15).",
)
HLD_CHAPTER = chapter

# ----------------------------------------------------------------------------------------------
# LLD
# ----------------------------------------------------------------------------------------------
p = lld["2"]
p = replace(
    p,
    "OpenRouter remains the default aggregator. Vercel is an optional second OpenAI-compatible endpoint only where its existing modest integration is retained; direct provider adapters remain removed.",
    "OpenRouter remains the default aggregator. Vercel is an optional second OpenAI-compatible endpoint by design; no Vercel integration exists at " + PIN + ". Direct provider adapters remain removed.",
)
p = replace(
    p,
    "| /v1/tools/web/search | Separate authorized search request; actual usage and compatibility gate |",
    "| /v1/tools/web/search | Separate authorized search request. Tavily-backed at " + PIN + " (Gateway-only `TAVILY_API_KEY`); the deterministic aggregator-plugin contract in §9C.1 is the target |",
)
p = replace(
    p,
    "| /v1/tools/package/lookup | Public PyPI/npm/Maven clients, independent of search |\n| /v1/tools/security/advisory | Public OSV client, independent of search |",
    "| /v1/tools/package/lookup | Public PyPI/npm/Maven clients; independence from search configuration is required by §9C.4 and not yet implemented |\n| /v1/tools/security/advisory | Public OSV client; same §9C.4 requirement |",
)
p = replace(
    p,
    "| OpenRouter | Approved default model transport and separately authorized search |\n| Vercel | Optional retained OpenAI-compatible transport; never an automatic substitute |",
    "| OpenRouter | Approved default model transport; separately authorized search is a target |\n| Tavily | Implemented web-search provider at " + PIN + "; Gateway-only key; replacement pending |\n| Vercel | Design option; no integration at the inspected source |",
)
lld["2"] = p

p = lld["3"]
p = replace(
    p,
    "- Broker deterministic search, bounded extract, package lookup, and OSV advisory independently.",
    "- Broker web search (Tavily at " + PIN + "; deterministic aggregator plugin is the target), bounded extract, package lookup, and OSV advisory; route independence from search configuration is a §9C.4 requirement not yet met.",
)
p = replace(
    p,
    "| `OPTIMUS_API_KEY` | `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY` |",
    "| `OPTIMUS_API_KEY` | `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY` |\n| | `TAVILY_API_KEY` (Gateway-only; current search provider) |",
)
lld["3"] = p

p = lld["4"]
p = replace(
    p,
    "| Deterministic search | separate minimal model call, structured citations, search-use accounting, provider-reported `cost_usd` |",
    "| Web search | Tavily provider at " + PIN + ": provider-native `tavily_credits` units recorded as `ProviderUsage` with request identity; the deterministic aggregator plugin (separate minimal model call, structured citations, search-use accounting) is the target |",
)
p = replace(
    p,
    "The separate USD rename removes `optimus_credits_debited` and other legacy credit-named fields\nwithout changing their existing USD semantics or introducing cross-run policy.",
    "The USD rename is complete at " + PIN + ": ACP result payloads carry `ledger_run_total_cost_usd` and\n`ledger_run_total_billing_units` (`optimus/acp/dispatcher.py`), and no credit-named ledger field remains under\n`src/`. The rename changed no USD semantics and introduced no cross-run policy.",
)
lld["4"] = p

p = lld["17"]
p = replace(
    p,
    "| Feedforward assembly | Existing AST/Redis/ADL controls plus optional Context Engine; exact authority and bounded current workspace evidence |",
    "| Feedforward assembly | Bounded workspace evidence and Redis state plus the optional Context Engine; exact authority. AST slicing and ADL constraint controls are intended, not established at " + PIN + " (§14) |",
)
lld["17"] = p

p = lld["20"]
p = replace(
    p,
    "the approved OpenAI-compatible upstream: OpenRouter by default, or Vercel AI Gateway if retained.",
    "the approved OpenAI-compatible upstream: OpenRouter by default (Vercel AI Gateway is a design option with no integration at " + PIN + ").",
)
p = replace(
    p,
    "- The surviving transport follows `UrllibOpenAICompatibleClient` in\n  `src/optimus_gateway/upstream_client.py`.",
    "- The surviving transport is `UrllibOpenAICompatibleClient` in\n  `src/optimus_gateway/upstream_client.py` (built by `optimus_gateway.providers.build_upstream_client`).",
)
p = replace(
    p,
    "The legacy host permits an initial attempt plus at most three retries.",
    "The legacy host permits an initial attempt plus at most three retries (`optimus/retry/policy.py`, `max_retries = 3`; the enforced-policy limit is `MAX_ROUTE_ATTEMPTS = 2` in `optimus_model_policy/binding.py`).",
)
lld["20"] = p

p = lld["33"]
p = replace(
    p,
    "```python\ndef record_usage(self, usage: GatewayUsage, *, context: RequestContext) -> None:",
    "```python\n# Illustrative shape. The implemented method is UsageAccountingService.record_gateway_usage\n# in src/optimus/usage/accounting.py; it enforces the same validation before appending.\ndef record_usage(self, usage: GatewayUsage, *, context: RequestContext) -> None:",
)
lld["33"] = p

p = lld["36"]
p = replace(
    p,
    "- Retain Vercel only if Python integration is modest; otherwise assign a named backlog entry.\n- Remove direct provider branches and `anthropic_client.py`.",
    "- Retain Vercel only if Python integration is modest; otherwise assign a named backlog entry. (Status at " + PIN + ": no Vercel integration exists.)\n- Remove direct provider branches and `anthropic_client.py`. (Done: no `anthropic_client` module at " + PIN + ".)",
)
p = replace(
    p,
    "- Separate package/OSV route construction from paid-search configuration.\n- Keep Tavily until replacement acceptance and rollback review pass.\n- Prove deterministic annotations, domains, URL revalidation, usage, and plugin live gate.",
    "- Separate package/OSV route construction from paid-search configuration. (Open at " + PIN + ": one bundle, gated by `TAVILY_API_KEY`, tool Redis URL and allowed domains.)\n- Keep Tavily until replacement acceptance and rollback review pass. (Tavily is the implemented provider at " + PIN + ".)\n- Prove deterministic annotations, domains, URL revalidation, usage, and plugin live gate. (Spike evidence only, 2026-07-27; no Gateway implementation of the plugin path.)",
)
lld["36"] = p

p = lld["38"]
p = replace(p, "The Test Strategy v1.8 is authoritative", "The Test Strategy v1.9 is authoritative")
lld["38"] = p

p = lld["39"]
p = replace(
    p,
    "Satisfiable by Tirith or an equivalent\nvalidator; the design takes no hard dependency on any one implementation.",
    "Satisfiable by Tirith or an equivalent\nvalidator; the design takes no hard dependency on any one implementation. Implemented in-process in\n`optimus/guardrails/command_safety.py` at " + PIN + "; Tirith is not a dependency.",
)
p = replace(
    p,
    "LoopBudgetPolicy (max_iterations, max_wall_clock_minutes, repeated_failure_limit; monetary policy only for explicitly capped evaluation callers), and",
    "LoopBudgetPolicy (max_iterations, max_wall_clock_minutes, repeated_failure_limit; `max_budget_usd` defaults to None and is set only by an explicitly capped evaluation caller; the model default for repeated_failure_limit is 3 in `optimus/loops/models.py` and ACP planning composes 2), and",
)
lld["39"] = p

# Replacement bodies for pages carried natively in v2.42 (text transcribed from v2.41 pages 27, 29, 32).
lld["27"] = (
    "# 9C.1 Deterministic search contract (target) and the implemented provider\n\n"
    "**Implemented at " + PIN + ":** the Gateway's `/v1/tools/web/search` route is served by `TavilyWebToolProvider` "
    "(`optimus_gateway/tool_providers.py`), configured with the Gateway-only `TAVILY_API_KEY`; its usage is recorded as "
    "provider-native `tavily_credits`. The contract below is the accepted target for replacing that provider with a "
    "dedicated aggregator request; it is not implemented in the Gateway.\n\n"
    "The target converts an authorized search request into a dedicated OpenRouter Chat Completions request using one cheap "
    "Flash/Haiku-class model, low `max_tokens`, and `plugins: [{\"id\": \"web\"}]`. Search is never attached to the primary "
    "generation call.\n\n"
    "```text\n{\n  \"model\": \"google/gemini-2.5-flash-lite\",\n  \"messages\": [{\"role\": \"user\", \"content\": \"<minimal search request>\"}],\n"
    "  \"max_tokens\": 16,\n  \"plugins\": [{\n    \"id\": \"web\",\n    \"max_results\": 3,\n    \"search_prompt\": \"<policy-bounded query>\"\n  }]\n}\n```\n\n"
    "The Gateway would forward the effective domain policy, parse only `annotations[].url_citation`, independently revalidate every "
    "returned URL, and copy upstream usage/cost. Assistant prose and annotation character offsets are not evidence.\n\n"
    "## Measured baseline (architecture spike, 2026-07-27)\n\n"
    "| Measurement | Value | Scope |\n|---|---|---|\n"
    "| Minimal-call annotations present | 3/3 | `tools/run_openrouter_web_search_spike.py`, run against OpenRouter directly |\n"
    "| Include-domain violations | 0 | same spike |\n| Exclude-domain violations | 0 | same spike |\n"
    "| Citations structurally complete | 9/9 | same spike |\n| Mean latency per search | 7,068.7 ms | same spike; one host, one day |\n"
    "| Mean reported cost | $0.0051584 | same spike; prices of that day |\n\n"
    "These values were produced by the spike tool, not by a Gateway test, and the spike is an experimental measurement harness, "
    "not production Gateway code. Three to five sequential searches would project to 21.2-35.3 seconds at that latency. The "
    "supplied Tavily comparison (about 1-2 seconds and $0.008/search) was not measured in this spike. The deterministic "
    "aggregator plugin is deprecated by OpenRouter (§9C.2), so the target itself is conditional.\n"
)

lld["29"] = (
    "# 9C.4 Independent tool dependency construction\n\n"
    "**Status at " + PIN + ":** `optimus_gateway.providers.build_tool_dependencies` builds one `GatewayToolDependencies` bundle "
    "(web, package, advisory providers, tool policy, Redis tool state and the per-tool call cap) and returns `None` when the "
    "Tavily key, the tool Redis URL or the allowed-domain list is missing. The search configuration therefore still gates the "
    "package and advisory routes. That coupling must be removed regardless of the selected search backend. The separation below is that requirement: specified and not yet implemented.\n\n"
    "```python\n@dataclass(frozen=True)\nclass ToolDependencies:\n    search: SearchBackend | None\n    extract: ExtractBackend\n"
    "    package: PackageRegistryBackend\n    advisory: AdvisoryBackend\n\n"
    "def build_tool_dependencies(settings: GatewaySettings) -> ToolDependencies:\n    return ToolDependencies(\n"
    "        search=build_search_backend_if_configured(settings),\n        extract=BoundedHttpExtract(...),\n"
    "        package=PublicPackageRegistries(...),\n        advisory=OsvAdvisoryClient(...),\n    )\n```\n\n"
    "Route registration is capability-specific:\n\n"
    "| Capability | Availability rule (target) | At " + PIN + " |\n|---|---|---|\n"
    "| Search | Selected backend configured and live acceptance gate passes | Tavily when `TAVILY_API_KEY`, tool Redis URL and allowed domains are set |\n"
    "| Extract | Bounded HTTPS fetch and prior-search provenance support available | Same bundle; unavailable without the search configuration |\n"
    "| Package lookup | Always available with public PyPI/npm/Maven clients | Same bundle; unavailable without the search configuration |\n"
    "| Security advisory | Always available with public OSV client | Same bundle; unavailable without the search configuration |\n\n"
    "Do not delete the Tavily adapter until replacement acceptance tests and rollback review pass. Record that a standalone search backend "
    "may need to return if the aggregator search path is withdrawn. This finding is recorded in the correction map for "
    "assignment to an owning GitHub issue; this edition commissions no implementation.\n"
)

lld["32"] = (
    "# 9E.1 Protocol-visible USD rename (implementation complete; real-client evidence UNRUN)\n\n"
    "The run-total field exposed in ACP result payloads for search, extract, package and advisory responses was a wire contract, "
    "so its rename from the credit-named `ledger_run_total_credits` was a contract migration, not an internal refactor.\n\n"
    "**Status at " + PIN + ":** the rename is implemented. `optimus/acp/dispatcher.py` emits `ledger_run_total_cost_usd` and "
    "`ledger_run_total_billing_units`; `EvidenceLedger` reconciles with `total_cost_usd()` and `total_billing_units()`; no "
    "credit-named ledger field remains under `src/`. The only remaining `credits` token is the provider-native unit label "
    "`tavily_credits` used for Tavily usage, which is accounting metadata, not a charge. Verified by code inspection and the unit and "
    "integration tests (`tests/unit/acp/test_dispatcher.py`, `tests/integration/evidence/test_mocked_evidence_flow.py`); the "
    "predecessor's real-client obligation is UNRUN because the `requires_acpx` tier was deselected in the sealed runs (Test Strategy §15.5, §16).\n\n"
    "The migration's required evidence, with status at " + PIN + ":\n\n"
    "| Record | Required evidence | Status |\n|---|---|---|\n"
    "| Search/extract response | `GatewayUsage` and run-total USD reconcile | Unit and integration tests |\n"
    "| Package/advisory response | Free operation remains non-fabricated and the run total is stable | Unit and integration tests |\n"
    "| EvidenceLedger | Decimal-safe sum by run/session/request identity | Unit tests |\n"
    "| ACP schema | USD field documented; no compatibility shim for the credit-named field remains at " + PIN + " | Code inspection |\n"
    "| Real ACP client | Response parses without project-authored client assumptions | UNRUN (`requires_acpx` tier deselected in the sealed runs; Test Strategy §15.5) |\n\n"
    "The ledger remains append-only and rejects a duplicate charge for the same `gateway_request_id`. The rename changed no USD "
    "semantics and added no cross-run policy.\n"
)

chapter = (PACKET / "sources" / "13-context-integration.md").read_text(encoding="utf-8")
chapter = replace(
    chapter,
    "### Released offline numeric set (verified route still required)",
    "### Released offline numeric set (verified route still required)\n\nWhere these values live at " + PIN + ": the reviewed test profiles and test fixtures (`optimus_model_policy/test_profile_qualification.yaml` output reserves 32768/8192; `tests/` fixtures), not shipped production defaults. `MAX_CONTEXT_CEILING_TOKENS = 262_144` (`optimus_model_policy/registry.py`) and `context_ceiling_tokens: 262144` (`defaults.yaml`) are the ceiling constants; `CONVERSATION_MAX_BYTES = 524_288` (`optimus/acp/conversation.py`) is the absent-engine source floor.",
)
chapter = replace(
    chapter,
    "The named D7 exception is proposed: keep the 524288-byte source floor/warning but refuse an over-capacity complete request readably with OPEN disposition, on absent-engine and attached full-history fallback. No provider guard exemption.",
    "The named D7 exception is accepted (ADR-018, operator source S4): keep the 524288-byte source floor/warning but refuse an over-capacity complete request readably with OPEN disposition, on absent-engine and attached full-history fallback. No provider guard exemption.",
)
chapter = replace(
    chapter,
    "Normal production bootstrap remains inactive. At cf9bb9d the reviewed named test composition supplies explicit process-scoped construction through the real trusted entrypoint and passes attachment/route/receipt dependencies into AcpDuplexAdapter.",
    "Normal production bootstrap remains inactive at " + PIN + " as at cf9bb9d: no production path constructs `ContextAttachment` (its docstring records this), `ENFORCEMENT_ACTIVE = False` and `trusted_snapshot()` returns `None`. Production activation requires, each with its own evidence and authority: an eligible route with verified estimator and output facts; a genuine summary-quality receipt; effect and cancellation evidence on the production base; trusted launch snapshot binding; bounded maintenance and repacking proof; and real-client evidence. Test-profile acceptance is not production bootstrap approval. At cf9bb9d the reviewed named test composition supplies explicit process-scoped construction through the real trusted entrypoint and passes attachment/route/receipt dependencies into AcpDuplexAdapter.",
)
chapter = replace(
    chapter,
    "Task 11 now satisfies those assertions at cf9bb9d and removes their markers; the final full runs verify the product/evaluation split.",
    "Task 11 now satisfies those assertions at cf9bb9d and removes their markers; the final full runs verify the product/evaluation split, and the change was merged to `main` via PR #276 (`c509fc8`).",
)
LLD_CHAPTER = chapter

# ----------------------------------------------------------------------------------------------
# Test Strategy
# ----------------------------------------------------------------------------------------------
p = test["2"]
p = replace(
    p,
    "- OpenRouter default and bounded Vercel option through the OpenAI-compatible transport;\n- deterministic search live compatibility and plugin deprecation gate;\n- include/exclude domain enforcement and returned-URL revalidation;\n- independent package/OSV routes without search configuration;",
    "- OpenRouter default through the OpenAI-compatible transport (the Vercel option is a design option with no implementation at " + PIN + ");\n- deterministic search live compatibility and plugin deprecation gate (a target path: the implemented provider is Tavily, and the gate has only 2026-07-27 spike evidence, §7A);\n- include/exclude domain enforcement and returned-URL revalidation;\n- independent package/OSV routes without search configuration (required; not implemented at " + PIN + ", LLD §9C.4);",
)
test["2"] = p

p = test["3"]
p = replace(
    p,
    "Every design claim maps to an executable unit, integration, E2E, eval, or release-gate check.",
    "Every design claim is required to map to an executable unit, integration, E2E, eval, or release-gate check; §16 records which material claims have evidence today and of what kind.",
)
test["3"] = p

p = test["6"]
p = replace(
    p,
    "- After replacement acceptance, the Gateway has no direct-provider, Tavily, or LangSmith key.",
    "- After replacement acceptance, the Gateway has no direct-provider, Tavily, or LangSmith key. (At " + PIN + " the Gateway still holds `TAVILY_API_KEY` as its implemented search provider key; replacement acceptance has not occurred.)",
)
test["6"] = p

p = test["7"]
p = replace(p, "Implemented interface at cf9bb9d:", "Implemented interface (cf9bb9d; present unchanged in purpose at " + PIN + "):")
p = replace(
    p,
    "Until the profiles lane lands, the hook entry is unchanged and keeps pyproject fail_under=80 (an Optimus-only interim floor). Only CI switches to --run-full-suite. The profiles lane later moves the hook to commit with no coverage gate. The released final CP4 gate also uses run mode. Retain hook ID optimus-pytest-coverage, optimus-check: pytest-coverage and existing ADR-016 skip custody; no new ad hoc waiver. Shared source-scope custody remains HARDENING-ITEM-COVERAGE-SOURCE-SCOPE.",
    "Status at " + PIN + ": the Plan 11.30 profiles lane has landed (PRs #279, #280 and #281 merged, ADR-020). The commit hook keeps its ID `optimus-pytest-coverage` and name `optimus-check: pytest-coverage` but runs `python -m tools.testing.run_profile --profile commit`: the tests this commit's staged changes select, without coverage. Its historical name does not make it a coverage run. CI (`.github/workflows/guardrails.yml`) runs `tools/check_product_coverage.py --run-full-suite` and then `tools.testing.coverage_products validate` against that export. Checkpoints run `run_profile --profile checkpoint --base <recorded SHA>`. `pyproject.toml` keeps `fail_under = 80` under `[tool.coverage.report]` for direct pytest-cov runs. The released final CP4 gate also uses run mode. Existing ADR-016 skip custody is retained; no new ad hoc waiver. Shared source-scope custody remains HARDENING-ITEM-COVERAGE-SOURCE-SCOPE (issue #299).",
)
test["7"] = p

p = test["8"]
p = replace(
    p,
    "| Tool | Category | Purpose | Counts toward code coverage |\n|---|---|---|---|\n| coverage.py / pytest-cov | Code coverage | Production-code execution | Yes |\n| DeepEval / Ragas | LLM quality | Correctness and groundedness | No |\n| PyRIT | Adversarial | Injection and tool-control safety | No |\n| OpenTelemetry / OTLP | Trace observability | Vendor-neutral span contract/export | No |",
    "| Tool | Category | Purpose | Counts toward code coverage | Status at " + PIN + " |\n|---|---|---|---|---|\n| coverage.py / pytest-cov | Code coverage | Production-code execution | Yes | Implemented; CI-enforced (§8A) |\n| DeepEval / Ragas | LLM quality | Correctness and groundedness | No | Intended; no dependency, import or test; UNRUN |\n| PyRIT | Adversarial | Injection and tool-control safety | No | Intended; no dependency, import or test; UNRUN. The guardrail fixtures in `tests/unit/guardrails` are offline positive controls for named guards, not a red-team campaign |\n| OpenTelemetry / OTLP | Trace observability | Vendor-neutral span contract/export | No | Implemented (`optimus_gateway.observability`); the live Phoenix tier (`requires_phoenix`) is UNRUN without a collector |",
)
test["8"] = p

p = test["9"]
p = replace(
    p,
    "The deterministic search compatibility gate uses one cheap Flash/Haiku-class model and one default\nengine request shape. The approved 2026-07-27 baseline is:",
    "The deterministic search compatibility gate uses one cheap Flash/Haiku-class model and one default\nengine request shape. Status at " + PIN + ": the Gateway's implemented search provider is Tavily; the aggregator\nplugin path this gate would exercise is not implemented in the Gateway, so this is a planned product gate whose only\nevidence is the 2026-07-27 architecture spike (`tools/run_openrouter_web_search_spike.py`, run against OpenRouter\ndirectly, not through the Gateway). As a Gateway gate it is UNRUN. The 2026-07-27 spike baseline is:",
)
test["9"] = p

p = test["13"]
p = replace(
    p,
    "Consistent with Objective 1 (§1), each control below traces to at least one executable test category; a control without a category is not considered validated for Phase 1.",
    "Consistent with Objective 1 (§1), each control below traces to at least one executable test category; a control without a category is not considered validated for Phase 1. Implementation status at " + PIN + ": each named component exists and has unit tests under `tests/unit/guardrails` (`test_permissions.py`, `test_pre_tool_guard.py`, `test_command_safety.py`, `test_unicode_confusables.py`, `test_prompt_injection.py`, `test_mcp_trust.py`, `test_ci_parity.py`, `test_network_safety.py`, `test_path_safety.py`) and `tests/unit/agent`; these are offline positive controls and attributable denials for the named guards.",
)
test["13"] = p

chapter = (PACKET / "sources" / "15-context-evidence.md").read_text(encoding="utf-8")
chapter = replace(
    chapter,
    "The proposed named ADR-014 exception retains 524288-byte source/admission and its warning but permits readable OPEN refusal when full history cannot fit. Record operator acceptance before claiming that disposition.",
    "The named ADR-014 exception retains 524288-byte source/admission and its warning but permits readable OPEN refusal when full history cannot fit. The operator's acceptance is recorded verbatim in ADR-018 (source S4; decision 2026-10-04, filed 2026-10-07).",
)
chapter = replace(
    chapter,
    "Task 13 uses independently authored acpx, the real Optimus process, real loopback Gateway, real TimeSeries-capable Redis and actual Zed rendering, under scoped credentials/TTY/service authority.",
    "Status: Task 13 is deferred and UNRUN by the operator's 2026-10-08 disposition (recorded in `docs/superpowers/reviews/2026-10-08-plan-12-2-cp4-offline-delivery-disposition.md`); its absent-engine cases may run before summary qualification once their own route, service and execution prerequisites are met. Task 13 uses independently authored acpx, the real Optimus process, real loopback Gateway, real TimeSeries-capable Redis and actual Zed rendering, under scoped credentials/TTY/service authority.",
)
chapter = replace(
    chapter,
    "CP4 clears only when all its required measured-value, route, quality, migration and real-client obligations have named passing evidence or a separately recorded operator disposition.",
    "The offline implementation and documentation through `2068366` were accepted by the operator on 2026-10-08 and merged to `main` via PR #276 (`c509fc8`); that acceptance is the offline merge gate, not a full CP4 pass. CP4 clears only when all its required measured-value, route, quality, migration and real-client obligations have named passing evidence or a separately recorded operator disposition.",
)
chapter = replace(
    chapter,
    "Windows: 6830 passed, 39 skipped, 111 deselected; WSL: 6641 passed, 228 skipped, 111 deselected; both exits 0.",
    "Windows (`final-gate-2`): 6830 passed, 0 failed, 39 skipped, 111 deselected, 1 warning, exit 0, 1:10:40; WSL (`wsl-full-1`): 6641 passed, 0 failed, 228 skipped, 111 deselected, 1 warning, exit 0, 40:09. Scope: the repository's full default marker selection at clean cf9bb9d; the 111 deselected tests are those the default marker selection excludes (live-dependency and other marked tiers). The failed `final-gate-1` attempt (3 failed, 6807 passed) preceded them and remains failed in the sealed evidence; its walker violation and two frozen-lane regressions were corrected before `final-gate-2`. Required coverage at cf9bb9d: Optimus group 89.4393% (Windows) / 88.9078% (WSL); context_engine 95.9243%; optimus_model_policy 96.9880%; Evidence Handoff 68.4165% / 65.9629%, BELOW its informational 80% threshold; the aggregate is informational. The limits and wheel proofs (zero proposal violations, max_repacks=1, planning material 43795 bytes, D7 upper bound 185581 bytes / 35.40%; wheel SHA-256 13b06132...ffd36, shipped effective registry hash unchanged) were produced at cc6959b and carried to cf9bb9d only because `src/`, `pyproject.toml` and the lockfile were unchanged between those commits; they were not rebuilt at cf9bb9d. All of these are historical measurements at their stated pins, not measurements at " + PIN + "; this correction reran only the documentation checks.",
)
TEST_CHAPTER = chapter

# ----------------------------------------------------------------------------------------------
# write the bundle
# ----------------------------------------------------------------------------------------------
out = BUNDLE / "sources"
out.mkdir(parents=True, exist_ok=True)
(out / "page-updates.json").write_text(
    json.dumps({"hld": hld, "lld": lld, "test": test}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
)
(out / "hld-14-context-engine.md").write_text(HLD_CHAPTER, encoding="utf-8", newline="\n")
(out / "lld-13-context-integration.md").write_text(LLD_CHAPTER, encoding="utf-8", newline="\n")
(out / "test-15-context-evidence.md").write_text(TEST_CHAPTER, encoding="utf-8", newline="\n")
print("wrote", out / "page-updates.json", "pages:", {k: len(v) for k, v in (("hld", hld), ("lld", lld), ("test", test))})
