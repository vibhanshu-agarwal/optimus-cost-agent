# 0. Purpose & Document Scope

This companion specification is the single canonical source for how the Optimus-Cost-Agent constrains what an agent is allowed to do at execution time, and how long-running agent work is bounded and made verifiable. It is deliberately maintained outside the core design documents so that the Architecture (HLD) and Low-Level Design (LLD) describe the cost-governance machine without being weighed down by the full guardrail and workflow policy surface. The core documents reference this document; they do not duplicate it.

The material here divides into two complementary halves that together describe the agent's execution contract:

- Safety controls — the permission model, the pre-tool guard / hook layer, shell command sanitization,

prompt-injection and MCP supply-chain defense, and pre-commit / CI gates. These decide whether a proposed action is permitted to reach execution at all.

- Execution controls — bounded goal-driven agent loops and curated workflow skills. These govern how

the agent performs large, well-bounded work without context bloat, and how repeatable procedural knowledge is loaded on demand under the same finite-work and trust discipline.

Both halves are governed by the existing Optimus control plane: the Operating Modes & Trust Framework (HLD §7), Tool Governance & Evidence Acquisition (HLD §8), the Adaptive Agent Execution Strategy & Rigor Policy (HLD §9), the Agent Lifecycle State Machine (LLD §4A), and the Optimus AI Gateway capacity, accounting and observability controls (HLD §11 / LLD §10, §10A). Nothing in this document weakens those guarantees; it extends them with explicit enforcement and workflow contracts.

## Cross-Reference Register

This document is anchored into the canonical set as follows. The corresponding insert text and version bumps are recorded in the document-control register (§13), before the added §14. This front cross-reference register retains the canonical anchors.

| Document | Anchor section | Relationship |
| --- | --- | --- |
| Architecture (HLD) | New §13 — Agent Execution Safety & Guardrails | Short cross-cutting reference; this document holds the detailed policy model. |
| Low-Level Design (LLD) | New §12 — Guardrail & Workflow Component Contracts | Detailed implementation contract for the Phase 1 enforcement and workflow components (§10 here). |
| Test Strategy | New §14 — Guardrail & Workflow Test Cases | Source for guardrail / security / loop / skill test categories (§11 here); adds traceability rows. |

# 1. Control-Plane Overview

Permissions and guardrails are the floor, not a nice-to-have. They are the baseline control over what the agent can do without asking a human each time. The premise is not that the agent is malicious — it is that the agent is a reward-hacky problem solver. When it is grinding toward "done," its own judgement is the