# Optimus - Architecture (HLD)

**Version 2.21 — Agent-mode localized EDIT, 2026-10-24; local filing — not activated.**

Predecessor: Optimus-Cost-Agent-Architecture-v2.20.pdf; SHA-256 52c35442a0d9027dc4b18a693284c45406cf02913001a59f2df364c77a2e176a. The predecessor is retained unchanged in `docs/archive/`.

Native carried page bodies originate from Optimus-Cost-Agent-Architecture-v2.18.pdf (SHA-256 0f8725765fecc9a93045fd26630457dfe7112508df164a3ec5bcc55dbc976807). This complete successor retains the predecessor's carried bodies and source corrections except for the approved localized EDIT changes. Sources are in `docs/sources/agent-localized-edit/`.

**What this edition changes.** It describes Agent-mode localized EDIT (#407, PR #411, merged as `d13fd34`) and corrects the consequent ACP WRITE/EDIT execution-path statements at main `57e2069414fef32c6a6e4de42bd0dc7fb9f4f1ac`, including the merged parser and failure-telemetry changes from PR #413 and PR #414. Carried statements and baseline status rows retain their inspected source `91fd64ac78025efe1076bddb106ff89e6adb2030` (origin/main, 2026-10-15). They have not been reverified at the newer pin. Accepted requirements and historical evidence retain their original authority and pins.

**Inspected production facts at 91fd64a.** ENFORCEMENT_ACTIVE is False and trusted_snapshot() returns None; no production path constructs ContextAttachment; the shipped alias claude-haiku resolves to anthropic/claude-haiku-4.5; the Gateway web-search provider is Tavily with a Gateway-only key; package/OSV routes still depend on that search configuration; no PyTestArch, maintainability-index, DeepEval, Ragas, PyRIT, Tirith or Vercel dependency, import or test exists; no Rust source exists.

**Historical acceptance stays attached to its pins.** Offline implementation candidate cf9bb9d (Codex review 2026-10-04); documentation filing 5ee081e; operator acceptance of the offline delivery through 2068366 (2026-10-08); merge c509fc8 (PR #276). The deferred live obligations (Luna route/estimator qualification, genuine summary-quality receipt, real-editor Task 13) remain UNRUN under Plan 12.2 ownership (issue #237). Offline acceptance is not production acceptance, a full CP4 pass or permission to remove the shipped model default.

**Controlling Plan 12.2 amendment.** The two preceding paragraphs are carried unchanged from v2.20 and retain their stated pins. The filed 2026-10-18 ordinary shipping amendment, `docs/sources/plan-12-2-ordinary-shipping/architecture-amendment.md`, still controls §14.2, §14.4–§14.6 and the §15 Context Engine and registry rows. It is not folded into this successor.

**Authority.** Codex's architecture wording; local filing by Claude under the operator's 2026-10-24 approval of change list r3 and decisions D1–D4, with the same unpublished editions re-pinned under the operator's 2026-10-24 decision. Local filing is separate from publication to main. This document grants no build, commit, paid or live call, activation, push, PR or merge authority. No product suite was run to author this text.
