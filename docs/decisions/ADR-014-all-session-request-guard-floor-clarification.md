# ADR-014: Clarify ADR-003's all-session request guard and unchanged source floor

**Status:** Accepted-with-open-items. **Decision date:** 2026-10-01. **Decider:** operator, evidenced by the verbatim selected option and cross-checked question-tool answer. **Publication:** Repository-form record; editable in pre-merge review, frozen byte for byte on first merge to `main`.

**Relationship:** Completes [ADR-003](ADR-003-context-ceiling-and-history-limits.md)'s absent-engine admission versus whole-request-guard interpretation (D7). Other ADR-003 open measurements remain open; its frozen bytes stay unchanged.

## Provenance

Source **S2**, indexed in the [decision log](README.md#rules-for-every-record): the operator's Claude Code session "PYTHON - [PLAN 12] Context Engine compaction", session `4162c45b-36f9-4cec-adb6-722ec3b28cb2`, exported on 2026-10-01 to `optimus-handoff\decisions-sources\2026-10-01-claude-session-context-engine-decisions-export.zip`; SHA-256 `8769D433CB869362305E91525273E8CA7A19EBC2807B1CA726F5DC9D4A81F5C2`. The archive is external raw provenance, never an operating, test or release dependency. The verbatim questions, options, selected labels and typed response reproduced below are the repository-visible decision evidence. Codex verified the archive checksum and the exact Q1–Q3 selections against the original question-tool records; Claude checked the export. Question/option wording is Claude's; selected labels and typed responses are the operator's. Agent relay summaries are context only.

**Question shown, verbatim:**

> Q2: Should the new request-size limit (~256K tokens) also apply to sessions without the Context Engine, recorded as a clarification of ADR-003?

**Operator selected, verbatim:**

> Yes, as clarification (Recommended)

**Selected description shown, verbatim:**

> The 512 KiB history limit stays as it is. Before release, tests must show a full 512 KiB history is still accepted on every model. If they fail, it comes back to you as an exception to your 'unchanged' decision. Too-large requests get a readable refusal, with no charge, and the thread stays open.

## Context

ADR-003 accepts a 262144-token whole-request ceiling including output reserve exactly once, while preserving engine-absent 524288-byte source admission. Main does not enforce a complete pre-call token guard. Its post-call dollar check cannot establish request-size compatibility: prices, cached input, output and framing differ. A needlessly loose byte estimate could reject ordinary full-floor histories that a validated tokenizer would admit.

## Options and trade-offs

| Exact option shown | Exact description shown |
|---|---|
| Yes, as clarification (Recommended) | The 512 KiB history limit stays as it is. Before release, tests must show a full 512 KiB history is still accepted on every model. If they fail, it comes back to you as an exception to your 'unchanged' decision. Too-large requests get a readable refusal, with no charge, and the thread stays open. |
| Treat as an exception | Record it as a deliberate change to the 'unchanged' decision, not a clarification. |
| Exempt those sessions | Sessions without the engine skip the check. Oversized requests go to the model provider and fail there, as they do today. |

The selected option retains the source floor and requires capacity proof before release. Treating it as an exception would knowingly change the floor decision; exempting absent sessions would omit pre-call safety. The actual selected clarification adds measurement obligations without silently accepting a floor reduction.

**Decision, paraphrased:** D7 is a clarification, not an accepted floor reduction. Preserve inclusive 524288-byte source admission/full history and its warning calculations, subject to the already accepted narrow presentation/order/model exceptions. Every final model request, including engine-absent, attached, maintenance and fallback paths, passes the complete-input-plus-one-output-reserve guard at the final provider boundary. Output reserve is the actual verified generation cap.

Before release, representative full-floor English/code histories at exactly 524288 projected source bytes must fit on every enabled absent-engine route, for both actual request paths, with maximum allowed workspace/tool/evidence material, framing and measured output reserve. Every enabled route must have its own verified evidence; a broad alias does not substitute for endpoint proof. Separate Unicode/adversarial fixtures verify estimator safety. Representative fixture success is not a universal token-per-byte claim.

If those acceptance tests fail, improve/verify estimator tightness without undercounting, or return the route/floor conflict to the operator as an exception before release. Do not silently halve the floor, exempt requests from safety or label failed/unrun evidence a pass. A genuine complete-request refusal remains readable, recoverable and OPEN, with zero upstream calls for the refused request.

## Open items and authority

Exact tokenizer/estimator/framing profiles, reserves, endpoint evidence, transient bounds and SOURCE_MAX_BYTES still require measurement/review; no 128K fallback or universal bytes/4 estimator is introduced. Source-floor meter approximation remains distinct from safety estimation. Compaction-trigger choices remain Proposed under ADR-003.

Codex drafts the clarification and design; Claude reviews and later implements authorized scope. This record does not itself authorize implementation, provider calls or delivery. The separate S2 docs-first selection authorizes filing; its Package A selection does not release these later request-guard tasks. It freezes only on its first merge. See [spec section 9.4](../superpowers/specs/2026-10-01-plan-12-2-context-engine-design.md) and plan Tasks 4/5/12 for producing evidence.
