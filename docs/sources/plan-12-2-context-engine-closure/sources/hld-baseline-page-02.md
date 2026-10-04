# 1. Executive Summary

Conceptual framing adapted from evolutionary software boundaries formulated by Neal Ford, Rebecca Parsons, and Patrick Kua (O'Reilly, 2026). The Optimus-Cost-Agent transitions from a basic token-routing utility to a formal Harness Engineering framework designed to govern non-deterministic generation via deterministic software boundaries. Standard AI agents are fundamentally bounded by the Dreyfus model's skill acquisition ceiling; they cannot brute-force their way past the competent or proficient barrier into true architectural consistency through raw scaling alone. Optimus raises the agent's effective architectural competence through deterministic constraints and feedback by wrapping logical model abstraction inside an opinionated local-first Python ACP server governed by automated, multi-tier architectural fitness functions and explicit request-level cost attribution.

# 2. Harness Engineering & Context Optimization

To protect the token window from context bloat while systematically mitigating hallucination, the agent structure enforces a strict division between Feedforward Controls and Feedback Sensors:
- **Feedforward Controls (Pre-Generation):** Before a prompt payload hits the downstream model, the Context Optimization Node constructs structural boundaries. It strips code down to AST-based functional slices, structures static filesystem metadata layouts at the head of the prompt window to maximise verified route input caching, and injects succinct, unambiguous constraints using an Architecture Definition Language (ADL) dialect to minimise context attention allocation.
- **Feedback Sensors (Post-Generation Evaluation):** Once the primary model provider emits a candidate patch, the engine catches the text stream inside a validation loop. It intercepts execution blocks and evaluates them via automated, triggered fitness functions before any source mutations are applied to the active working tree.

# 3. Automated Architectural Fitness Functions

Optimus treats system governance not as a passive logging layer, but as an active, objective integrity check on core architectural traits. Phase 1 implements highly targeted, local validation primitives organised across five operational planes: Scope (Atomic), Automation (Automated), Invocation (Triggered), Return (Static), and Activation (Proactive). These gates intercept code generations mid-flight to fix structural deviations before changes lock into local Git trees.

# 4. Data Governance Plane & Local Storage Boundaries

To support enterprise compliance review, data within the local container is sharply bounded. Unparsed source code is strictly prohibited from entering persistent vector indexes. The storage engine uses standard Redis HASH structures to catalogue structural class signatures, summaries, and relative file paths. Numeric performance histories are channelled separately to a Redis TimeSeries cluster (tracking tokens_input, tokens_output, cost_usd) tagged by unique run_id strings and protected by a hard 30-day retention window policy.

# 5. Request-Level Cost Attribution