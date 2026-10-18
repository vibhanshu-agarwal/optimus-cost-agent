"""Apply the fresh-context review's fix pass (I1-I3, M1-M5) to the authoring script and bundle sources."""
from pathlib import Path

W = Path(r"C:/worktrees/optimus-cost-agent-worktrees/optimus-cost-agent-wt-claude-plan12-doccorr/.superpowers/sdd/claude-documentation-correction-plan")
B = Path(r"C:/worktrees/optimus-cost-agent-worktrees/optimus-cost-agent-wt-claude-plan12-doccorr/docs/sources/capability-evidence-correction")


def rep(path: Path, old: str, new: str) -> None:
    t = path.read_text(encoding="utf-8")
    assert t.count(old) == 1, (path.name, old[:70], t.count(old))
    path.write_text(t.replace(old, new), encoding="utf-8", newline="\n")


a = W / "tools" / "author_corrections.py"

# I1: LLD §4A execution pathway table (inherited lld["17"])
rep(
    a,
    'p = lld["20"]\np = replace(\n    p,\n    "the approved OpenAI-compatible upstream: OpenRouter by default, or Vercel AI Gateway if retained.",',
    'p = lld["17"]\np = replace(\n    p,\n    "| Feedforward assembly | Existing AST/Redis/ADL controls plus optional Context Engine; exact authority and bounded current workspace evidence |",\n    "| Feedforward assembly | Bounded workspace evidence and Redis state plus the optional Context Engine; exact authority. AST slicing and ADL constraint controls are intended, not established at " + PIN + " (§14) |",\n)\nlld["17"] = p\n\np = lld["20"]\np = replace(\n    p,\n    "the approved OpenAI-compatible upstream: OpenRouter by default, or Vercel AI Gateway if retained.",',
)

# M1 + M2: HLD §13 version pointer and test locations
rep(
    a,
    '    "Implemented at " + PIN + " with unit tests under `tests/unit/guardrails` and `tests/unit/agent`: `PermissionPolicy`, `PreToolGuard`, `CommandSafetyValidator` (in-process; Tirith is not a dependency), `ConfigTrustScanner`, `MCPTrustRegistry`, `GoalLoopController` with `LoopBudgetPolicy`, and `SkillRegistry` with `SkillTrustPolicy`. The classifier described here is a reserved architecture capability, not an active production route.",\n)\nhld["13"] = p',
    '    "Implemented at " + PIN + " with unit tests under `tests/unit/guardrails`, `tests/unit/agent`, `tests/unit/loops`, `tests/integration/loops` and `tests/unit/skills`: `PermissionPolicy`, `PreToolGuard`, `CommandSafetyValidator` (in-process; Tirith is not a dependency), `ConfigTrustScanner`, `MCPTrustRegistry`, `GoalLoopController` (`optimus/loops/controller.py`) with `LoopBudgetPolicy`, and `SkillRegistry` with `SkillTrustPolicy`. The classifier described here is a reserved architecture capability, not an active production route.",\n)\np = replace(p, "Coverage policy is authoritative in Test Strategy v1.8 §8A", "Coverage policy is authoritative in Test Strategy v1.9 §8A")\nhld["13"] = p',
)

# I3: §9C.4 body — restore the accepted sentence and the original "return"
rep(
    a,
    '"package and advisory routes. The separation below is a requirement that is specified and not yet implemented.\\n\\n"',
    '"package and advisory routes. That coupling must be removed regardless of the selected search backend. The separation below is that requirement: specified and not yet implemented.\\n\\n"',
)
rep(
    a,
    '"Do not delete the Tavily adapter until replacement acceptance tests and rollback review pass. A standalone search backend "\n    "may need to remain if the aggregator search path is withdrawn.',
    '"Do not delete the Tavily adapter until replacement acceptance tests and rollback review pass. Record that a standalone search backend "\n    "may need to return if the aggregator search path is withdrawn.',
)

# I2: §9E.1 body — separate implementation from the predecessor's evidence obligations
rep(a, '"# 9E.1 Protocol-visible USD rename (completed)\\n\\n"', '"# 9E.1 Protocol-visible USD rename (implementation complete; real-client evidence UNRUN)\\n\\n"')
rep(a, '"**Status at " + PIN + ":** the rename is complete. `optimus/acp/dispatcher.py` emits', '"**Status at " + PIN + ":** the rename is implemented. `optimus/acp/dispatcher.py` emits')
rep(
    a,
    '"`tavily_credits` used for Tavily usage, which is accounting metadata, not a charge.\\n\\n"\n    "The migration\'s required evidence, retained for the record:\\n\\n"',
    '"`tavily_credits` used for Tavily usage, which is accounting metadata, not a charge. Verified by code inspection and the unit and "\n    "integration tests (`tests/unit/acp/test_dispatcher.py`, `tests/integration/evidence/test_mocked_evidence_flow.py`); the "\n    "predecessor\'s real-client obligation is UNRUN because the `requires_acpx` tier was deselected in the sealed runs (Test Strategy §15.5, §16).\\n\\n"\n    "The migration\'s required evidence, with status at " + PIN + ":\\n\\n"',
)
rep(
    a,
    '"| Record | Required evidence |\\n|---|---|\\n"\n    "| Search/extract response | `GatewayUsage` and run-total USD reconcile |\\n"\n    "| Package/advisory response | Free operation remains non-fabricated and the run total is stable |\\n"\n    "| EvidenceLedger | Decimal-safe sum by run/session/request identity |\\n"\n    "| ACP schema | USD field documented; no compatibility shim for the credit-named field remains at " + PIN + " |\\n"\n    "| Real ACP client | Response parses without project-authored client assumptions (acpx tiers; see Test Strategy §15.5) |\\n\\n"',
    '"| Record | Required evidence | Status |\\n|---|---|---|\\n"\n    "| Search/extract response | `GatewayUsage` and run-total USD reconcile | Unit and integration tests |\\n"\n    "| Package/advisory response | Free operation remains non-fabricated and the run total is stable | Unit and integration tests |\\n"\n    "| EvidenceLedger | Decimal-safe sum by run/session/request identity | Unit tests |\\n"\n    "| ACP schema | USD field documented; no compatibility shim for the credit-named field remains at " + PIN + " | Code inspection |\\n"\n    "| Real ACP client | Response parses without project-authored client assumptions | UNRUN (`requires_acpx` tier deselected in the sealed runs; Test Strategy §15.5) |\\n\\n"',
)

# B. HLD §15: M4
h = B / "sources" / "hld-15-capability-status.md"
rep(
    h,
    "| Auto classification and automatic escalation (§6, §10.D) | Specified (ADR-007); not implemented | None | Deferred under existing owners |",
    "| Auto classification and automatic escalation (§6, §10.D) | Proposed (ADR-007, status Proposed); not implemented | None | Deferred under existing owners |",
)
rep(
    h,
    "| Final reviewer step (ADR-008) and net savings report (ADR-012) | Specified; not implemented (savings report: issue #248) | None | Deferred under existing owners |",
    "| Final reviewer step (ADR-008) and net savings report (ADR-012) | Reviewer step proposed (ADR-008, status Proposed); savings report specified (ADR-012 accepted with open items, issue #248); neither implemented | None | Deferred under existing owners |",
)

# C. LLD §14: M3, M5
lld_status = B / "sources" / "lld-14-capability-status.md"
rep(
    lld_status,
    "| Strict loopback settings (`OptimusGatewaySettings`, §9C) | Implemented (`optimus/config/gateway.py`, `validate_loopback_gateway`) | Unit tests | Active |",
    "| Strict loopback settings (`OptimusGatewaySettings`, §9C) | Implemented (`optimus/config/gateway.py`, `_validate_loopback_gateway_url`; the `validate_loopback_gateway` listing on the carried §9C page is illustrative) | Unit tests | Active |",
)
rep(
    lld_status,
    "| ExecutionMode PLAN/CHAT/AGENT and mutation assertion (§4) | Implemented (`optimus/runtime/modes.py`, `optimus/gates/mutation_flow.py`, `MutationGuard`) | Unit and integration tests | Active |",
    "| ExecutionMode PLAN/CHAT/AGENT and mutation assertion (§4) | Implemented (`optimus/runtime/modes.py`; `MutationGuard` and `assert_mutation_allowed` in `optimus/runtime/mutation.py`, used by `optimus/gates/mutation_flow.py`) | Unit and integration tests | Active |",
)
rep(
    lld_status,
    "| Borderline classifier and loop completion evaluator model calls (§12A, §12C) | `CompletionEvaluator` contract exists; classifier reserved | None live | Inactive |",
    "| Borderline classifier and loop completion evaluator model calls (§12A, §12C) | `GatewayCompletionEvaluator` implemented (`optimus/loops/completion.py`) behind `CompletionEvaluatorProtocol`; production composition uses `DeterministicCompletionEvaluator` and nothing in `src/` constructs the Gateway evaluator; classifier reserved | Unit tests (`tests/unit/loops/test_completion.py`); none live | Inactive (not composed in production) |",
)

# D. correction map
m = B / "correction-map.md"
rep(
    m,
    "| `src/optimus/acp/spec.py` (`build_usage_update`) | Code inspection only | None |",
    "| `src/optimus/acp/shapes.py` line 285 (`build_usage_update`), called from `src/optimus/acp/spec.py` | Code inspection only | None |",
)
rep(
    m,
    "| `src/optimus/gates/mutation_flow.py`; `src/optimus/runtime/__init__.py`; `tests/unit/gates` | Offline positive controls and attributable denials | None |",
    "| `src/optimus/runtime/mutation.py` lines 26, 40 (`MutationGuard`, `assert_mutation_allowed`); `src/optimus/gates/mutation_flow.py`; `tests/unit/gates`, `tests/unit/runtime` | Offline positive controls and attributable denials | None |",
)
rep(
    m,
    "| 26 | LLD §0A, §9E.1 (new body) | USD rename described as a future subtask removing `optimus_credits_debited`/`ledger_run_total_credits` | Complete: payloads carry `ledger_run_total_cost_usd` and `ledger_run_total_billing_units`; no credit-named ledger field remains (`tavily_credits` is a provider-native unit label) | `src/optimus/acp/dispatcher.py` lines 415-475; `src/optimus/evidence/acquisition.py` line 49 | Code inspection | None |",
    "| 26 | LLD §0A, §9E.1 (new body) | USD rename described as a future subtask removing `optimus_credits_debited`/`ledger_run_total_credits` | Implementation complete: payloads carry `ledger_run_total_cost_usd` and `ledger_run_total_billing_units`; no credit-named ledger field remains (`tavily_credits` is a provider-native unit label). The predecessor's real-client evidence obligation stays UNRUN (`requires_acpx` deselected in the sealed runs) and is marked so | `src/optimus/acp/dispatcher.py` lines 415-475; `src/optimus/evidence/acquisition.py` line 49; `tests/unit/acp/test_dispatcher.py`, `tests/integration/evidence/test_mocked_evidence_flow.py` | Code inspection plus unit/integration tests; real-client row UNRUN | None |",
)
rep(
    m,
    "| `src/optimus/retry/policy.py` line 146; `src/optimus_model_policy/binding.py` line 158; `src/optimus_gateway/providers.py` line 18 | Code inspection | None |",
    "| `src/optimus/retry/policy.py` line 146; `src/optimus_model_policy/binding.py` line 158; transport built in `src/optimus_gateway/providers.py` line 18 | Code inspection | None |",
)
rep(
    m,
    "| 12 | HLD §9, §10.D row 3, §10.E rows 2 and 5; LLD §4, §4A strategy table |",
    '| 12 | HLD §9, §10.D row 3, §10.E rows 2 and 5; LLD §4A execution-pathway table ("Existing AST/Redis/ADL controls" reclassified as intended, not established) |',
)
rep(
    m,
    "| 29 | LLD §11 checklist | Items read as open | Annotated:",
    '| 29 | LLD §9C.4 (new body), §11 checklist | §9C.4\'s accepted sentence "That coupling must be removed regardless of the selected search backend" is kept verbatim with its status; checklist items read as open | §9C.4 status paragraph added; checklist annotated:',
)
rep(
    m,
    "| 19 | HLD §13; LLD §12A, §12C; Test §14 | Guardrail components and Tirith | Components implemented with unit tests;",
    '| 19 | HLD §13 (also "Test Strategy v1.8 §8A" corrected to v1.9); LLD §12A, §12C; Test §14 | Guardrail components and Tirith | Components implemented with unit tests under `tests/unit/guardrails`, `tests/unit/agent`, `tests/unit/loops`, `tests/integration/loops`, `tests/unit/skills`;',
)
print("review fixes applied")
