# 14. Guardrail & Workflow Test Cases

LLD reference: §12 (Guardrail & Workflow Component Contracts). Companion reference: Agent Execution Guardrails & Workflow Strategy v1.4 §11. Consistent with Objective 1 (§1), each control below traces to at least one executable test category; a control without a category is not considered validated for Phase 1.

14.1 Permission policy tests — deny precedence over allow; mode short-circuit; impact-class HOLD; classifier cannot overturn a deny.

14.2 Shell validator tests — destructive, pipe-to-shell, environment/credential access, ANSI, insecure-transport, and egress patterns all BLOCK before any subprocess is spawned.

14.3 Unicode / homoglyph tests — Cyrillic-vs-Latin confusables in hostnames and paths (e.g. U+0456 vs U+0069) are detected and held/blocked.

14.4 Prompt-injection fixture tests prove poisoned agent config and poisoned MCP tool metadata are caught by ConfigTrustScanner / MCPTrustRegistry on ingest.

14.5 MCP autoload denial tests — a server bundled in a cloned repo does not auto-load; a manifest-hash change forces re-approval; allowed_tools are enforced.

14.6 Pre-commit / CI parity tests — the same rule set (Ruff, Bandit, AST-grep, hygiene hooks) fails identically locally and in a clean CI checkout.

14.7 Bypass tests — --no-verify, force-push to main, unsafe .env reads, and unsafe network commands are all blocked.

14.8 Loop control tests — the loop stops on completion, on max_iterations, on wall-clock exhaustion and repeated-failure detection; it never bypasses §14.1/§14.2 enforcement.

14.9 Skill loading & trust tests — a skill loads only when matched; an untrusted/draft skill is blocked; declared allowed_tools are enforced; a skill cannot override project/user deny rules.

## 14.10 Additions to the §4 Requirements-to-Test Traceability Matrix

| LLD Section | Design Claim | Test Category (§) | Tier |
| --- | --- | --- | --- |
| §12A — Permission | Deny precedes allow; classifier cannot overturn deny | §14 — Guardrails | Unit |
| §12A — Pre-Tool Guard | Bad tool call blocked before execution | §14 — Guardrails | Unit + Integration |
| §12A — Shell Validator | Homoglyph / pipe-to-shell / egress blocked pre-spawn | §14 — Guardrails | Unit |
| §12B — MCP Trust | No auto-load from cloned repo; hash change re-approves | §14 — Guardrails | Unit + Integration |
| §12B — Config Scan | Poisoned config / tool metadata caught on ingest | §14 — Guardrails | Unit |
| §6 / §12 — CI Parity | Local and clean-CI checks fail identically | §14 — Guardrails | Integration |