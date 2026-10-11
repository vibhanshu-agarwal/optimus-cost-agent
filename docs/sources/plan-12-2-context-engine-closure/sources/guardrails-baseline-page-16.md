integration; Bandit's role in Python security scanning; GitHub Actions concurrency support; the Ralph agent-loop pattern; Claude Code /goal and skills; and the SkillsBench evaluation.

- Claude Code Hooks — docs.anthropic.com/en/docs/claude-code/hooks

- OWASP LLM Top 10 — genai.owasp.org/llm-top-10

- pre-commit — pre-commit.com

- Ruff pre-commit integration — docs.astral.sh/ruff/integrations

- Bandit — bandit.readthedocs.io

- GitHub Actions concurrency — docs.github.com — workflow syntax · concurrency

- Ralph loop — github.com/snarktank/ralph

- Claude Code /goal — code.claude.com/docs/en/goal

- Claude Code skills — code.claude.com/docs/en/skills

- SkillsBench — arxiv.org/abs/2602.12670

# 13. Document Control & Cross-Reference Register

This companion document is referenced from the canonical set. The historical initial inserts below retain their original edition attribution. The v1.4 successor change record follows; historical numbers are not current successor allocations.

| Document | Was | Becomes | Insert |
| --- | --- | --- | --- |
| Architecture (HLD) | v2.14 | v2.15 | New §13 — Agent Execution Safety & Guardrails (short cross-cutting section + Figure 1 reference). |
| Low-Level Design (LLD) | v2.37 | v2.38 | New §12 — Guardrail & Workflow Component Contracts (full contracts from §10 here). |
| Test Strategy | v1.3 | v1.4 | New §14 — Guardrail & Workflow Test Cases (§11 here) + new rows in §4 traceability matrix. |
| This document | — | v1.0 | Initial issue. |

Change log — v1.0 (initial issue): first release of the consolidated agent execution safety and workflow strategy, linked from HLD §13, LLD §12, and Test Strategy §14.

Version 1.4 change record: preserves original tables/code and branches; adds optional context authority, bounded maintenance/repack, product/evaluation policy separation and shared coverage cross-reference. The document register remains at the front; publication follows acceptance and a non-draft rebuild.

| Review successor | Predecessor | Proposed edition |
|---|---|---|
| HLD | 2.18 | 2.19 |
| LLD | 2.41 | 2.42 |
| Test Strategy | 1.7 | 1.8 |
| Guardrails | 1.3 | 1.4 |
