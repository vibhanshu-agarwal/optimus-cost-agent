# Optimus decision log (ADRs)

**Why this exists.** On 2026-09-30 the operator said:

> "Importantly, I hope this context can be saved in some way - often my requirements gets lost or
> oversimplified losing the original context and reasoning. Architectural decisions should not be binary
> - must be supported by proper reasoning and tradeoff analysis"

Three recent examples show the problem. Agents set each of these values, and each was later treated as if
the operator had required it:

- the $0.05 per-turn budget;
- the "100K inside 128K" headroom;
- the 3-planning-turn cap.

Meanwhile a real operator requirement, "curbing unnecessary agent loops", survived only as one line in a
brainstorm diary.

**Where this log lives.** Here, in the repository, as the operator required on 2026-09-30: "These should be
in the repo and agreed by both you and Codex". Every agent reads the same versioned copy, and every change
goes through review. Earlier drafts in the operator's handoff folder (outside the repository) are superseded
by this folder.

## Rules for every record

1. **Keep the operator's words verbatim,** with the date and a shared source. A paraphrase is labelled as
   a paraphrase, with its source. An agent's private memory or paraphrase is never a verbatim source.
   - **Source S1.** Unless a record says otherwise, operator quotes dated 2026-09-30 come from the
     operator's messages in the Claude Code session "PYTHON - [PLAN 12] Context Engine compaction".
     - Its transcript export is kept outside the repository in the operator's handoff folder, at
       `optimus-handoff\decisions-sources\2026-09-30-claude-session-context-engine-compaction-export-4.zip`.
     - Its SHA-256 is `E3BCB3F6A9F0C706FF3E0BC46BE791490D871017D753ADB3B34BA44F33DC8A0F`.
     - This fourth export supersedes three earlier ones, which predate the operator's later messages:
       `...-export.zip` (SHA-256 `87CB74E5…`), `...-export-2.zip` (`1BC23372…`) and `...-export-3.zip`
       (`063BC3AF…`).
     - Quotes given after an export was taken need a fresh export, which is recorded the same way.
   - **Source S2.** Operator selections dated 2026-10-01 come from a later export of the same
     Claude Code session, `4162c45b-36f9-4cec-adb6-722ec3b28cb2`.
     - External raw transcript archive: `optimus-handoff\decisions-sources\2026-10-01-claude-session-context-engine-decisions-export.zip`.
     - SHA-256: `8769D433CB869362305E91525273E8CA7A19EBC2807B1CA726F5DC9D4A81F5C2`.
     - Covers Q1’s typed effort question and later Fold into Plan 12 selection; Q2’s guard/floor
       clarification; Q3’s removal-after-accounting sequence; and the later Package A and Docs PR first
       selections (`2026-10-01T06:09:37.747Z`). ADR-013–015 reproduce the decision evidence in tracked
       text. Codex verified the archive checksum and the scope/filing question-tool answers; Claude
       checked the exported selections. Raw S2 is archival provenance, not an operating/test/release input.
     - S1 remains the cited provenance for the frozen 2026-09-30 records; S2 adds later selections.
   - **Source S3.** Fresh Package A/cadence export, session `4162c45b-36f9-4cec-adb6-722ec3b28cb2`,
     taken on 2026-10-02 (Asia/Calcutta): `optimus-handoff\decisions-sources\2026-10-02-claude-session-context-engine-package-a-export.zip`.
     - SHA-256 `9B89272060555D1542B14F25C37807F21C5763222D0A93CF2C1ECC791D642A66`.
     - Covers the post-S2 local-commit selection, Task 3's narrow exception, standing checkpoint
       cadence and Package A PR then CP1 selections. Operator text/tool-result selections were
       checked directly inside the archive. Original UTC times are retained; the cadence/next-step
       answers on October 1 UTC occurred on October 2 in the operator's timezone.
     - S1/S2 remain the provenance of their frozen records. S3 is external archival provenance,
       not a build/test/runtime input; no raw transcript is added to the repository.
   - **Source S4.** CP4 offline-release export of session `4162c45b-36f9-4cec-adb6-722ec3b28cb2`,
     taken on 2026-10-07: `optimus-handoff\decisions-sources\2026-10-07-claude-session-context-engine-cp4-d7-export.zip`.
     - SHA-256 `4E1EA17C35BF0E0C6B744A579A911E9B769313969C19430CDCEF47F3FA20A862`.
     - It is a single-file ZIP of the session's raw transcript JSONL (71,505 records), made by the
       operator. The app's Export refuses sessions over 200 MB, and this one was 238 MB. Codex
       confirmed that the single-file ZIP is sufficient provenance (2026-10-07).
     - It covers the operator's 2026-10-04 offline release (`2026-10-04T11:26:55.284Z`, 16:56:55 IST;
       record `b34978ea-d159-41c0-bee3-ad74a26a5bb2`, line 57140), quoted in ADR-018.
       - Claude checked inside the archive that the message equals, unchanged, the "Offline and free
         release" block of Codex's sealed release text (SHA-256 `404354cf…`).
       - Codex independently confirmed the message.
     - S4 is external archival provenance, not a build/test/runtime input. No raw transcript is
       added to the repository.
   - **Source S5.** Plan 11.30 operator messages dated 2026-10-04 in Codex chat
     `01a10617-9940-72c0-a5e2-e3f8c3241055` (drafted as S3 on the Plan 11.30 branch before main filed S3/S4).
     - External transcript excerpt: `optimus-handoff\decisions-sources\2026-10-04-codex-plan-11-30-operator-decisions-export.json`.
     - SHA-256: `3DDD90F7FCB52DE88059E8A4582CFF37A6EF27BDA816A32A34E986E39CFB20D5`.
     - Four exact original messages: review/simplicity instruction (`10:02:14.535Z`), Codex approval
       question (`10:11:16.427Z`), operator approval (`10:14:05.341Z`) and Claude assignment
       (`10:17:01.533Z`), all 2026-10-04 UTC. Explicitly scoped excerpt, not a full export.
       ADR-020 reproduces operator words and authority boundaries. Raw S5 is archival provenance,
       never an operating, test or release dependency; S1–S4 retain their existing meanings.
   - **Source S6.** Plan 11.29 cutover-proposal request, operator message dated 2026-10-11 (23:29:18.943 IST;
     UTC 17:59:18.943) in Codex chat `01a1027e-9c55-7952-979b-af01fd93aa9f`.
     - External transcript excerpt: `optimus-handoff\decisions-sources\2026-10-11-codex-cutover-operator-excerpt.json`.
     - SHA-256: `D79F6A29713E7EC054F5BE567634F07D57001193269FEE171234364747964AF8`.
     - One exact original message (source line 3184, `2026-10-11T17:59:18.943Z`), extracted by Codex and checked
       by Claude against the quoted text. Explicitly scoped excerpt, not a full export. ADR-021 reproduces the
       operator's words and authority boundaries. Raw S6 is archival provenance, never an operating, test or
       release dependency; S1–S5 retain their existing meanings.
   - **Source S7.** Plan 11.29 mechanism acceptance, operator message dated 2026-10-12 (14:09:30.351 IST;
     UTC 08:39:30.351) in the Claude Desktop session `7c7198ea-e124-4199-ab9c-49de5eda155d`.
     - External transcript excerpt: `optimus-handoff\decisions-sources\2026-10-12-claude-cutover-mechanism-acceptance-excerpt.json`.
     - SHA-256: `7D199F098C4AF58BB588467D56E576589066DBD5D3816116BE7843FB85BB289A`.
     - One exact original record (source line 10327, `2026-10-12T08:39:30.351Z`): the operator's typed
       "Accepted per wording above", sent with Codex's pasted acceptance wording, which it adopts by
       reference. The pasted wording is agent text and the typed sentence is operator text. Extracted by
       Codex and checked by Claude against the session transcript (text, times, ids). Explicitly scoped
       excerpt, not a full export. ADR-021's index row records the acceptance and its limits. Raw S7 is
       archival provenance, never an operating, test or release dependency; S1–S6 retain their existing meanings.
   - **Source S8.** Plan 11.29 work-register clarification, operator message dated 2026-10-13 (02:41:22.999 IST;
     UTC 2026-10-12 21:11:22.999) in Codex chat `01a1027e-9c55-7952-979b-af01fd93aa9f`.
     - External transcript excerpt: `optimus-handoff\decisions-sources\2026-10-13-codex-work-register-operator-excerpt.json`.
     - SHA-256: `A5E20507490AC8A6D3258DB9C94BCD3EB54A4A845EB644EAE1A19106738D9AEC`.
     - One exact original message (source line 5653, `2026-10-12T21:11:22.999Z`, message `msg_01a131f4-b477-7df2-ad6d-30c73c402069`), extracted by Codex and checked by
       Claude against the original Codex session file (line, text, time and ids; the excerpt's record equals the session line in every field).
       Explicitly scoped excerpt, not a full export. ADR-022 reproduces the operator's words and authority boundaries. Raw S8 is
       archival provenance, never an operating, test or release dependency; S1–S7 retain their existing meanings.
   - **Source S9.** Plan 12.2 plan agreement and offline approval, operator messages dated 2026-10-18 (13:33:57.072 and
     16:37:49.501 IST; UTC 08:03:57.072 and 11:07:49.501) in Codex chat `01a102cf-53c7-7cb1-b470-0f0f4efcbb0e`.
     - External excerpt: `optimus-handoff\decisions-sources\2026-10-18-plan12-offline-approval-direct-chat-excerpt.md`.
     - SHA-256: `3609DCE2EDD757CA6993C33A41A2113ED0E31B161D6663C92C1FFFA1B5E871DF`.
     - A Codex-produced excerpt of two direct operator messages, the planning instruction and the answer "Approved", with
       Codex's approval question as recorded in its saved coordination state. It is not a raw transcript export or a signed
       operator receipt. The excerpt gives no message time or identifier; its `2026-10-18T11:10:02.175974Z` is Codex's
       recording time, not a message time.
     - Claude copied it byte-identically and checked both messages, read-only, against the original Codex session file: the
       instruction at line 52221 (`2026-10-18T08:03:57.072Z`, message `msg_01a14e09-f210-7413-ba88-5b28b5984d09`) and
       "Approved" at line 52406 (`2026-10-18T11:07:49.501Z`, message `msg_01a14eb2-497d-79f3-aa33-ff076ec5ad97`). Each text
       equals its quote apart from a trailing newline. Codex asked the question in chat at `2026-10-18T08:15:10.571Z`, and no
       other human message came before the answer.
     - The relay to Claude (#237 comment 6249169293, with its handoff and readback) is coordination evidence, not a direct
       source or a new approval. Explicitly scoped excerpt, not a full export. ADR-023 reproduces the operator's words and
       authority boundaries. Raw S9 is archival provenance, never an operating, test or release dependency; S1–S8 retain
       their existing meanings.
   - **Source S10.** Plan 12 decisions, operator messages dated 2026-10-22 and 2026-10-23 in the Claude session for
     the Plan 12 next-item thread (session `817f38ae-e1fb-432b-a2e9-d7827bd97aa3`): the memory discovery answers,
     scope freeze, M0a split, spec and plan approvals and memory filing approval; the loop-control decisions D1–D3;
     the Auto research request; the priority and Auto decisions P1 and A1–A5; and the filing approval for Plans 12.3
     and 12.4.
     - External transcript export: `optimus-handoff\decisions-sources\2026-10-23-claude-session-plan12-export.zip`, produced by the app's
       session Export, 16,998,203 bytes.
     - SHA-256: `B3B52E66E3E3AFA99034125AD690914B7F03610C41F5BDC63F27331EA1FAC2E1`.
     - Claude checked, read-only, that each quoted decision appears verbatim in a user turn of the export's main
       transcript. A full app export, not an excerpt. Raw S10 is archival provenance, never an operating, test or
       release dependency; S1–S9 retain their existing meanings.
   - **Source S11.** Plan 12.4 v7 decisions, operator messages dated 2026-10-25 in the Claude session for the Plan 12.4
     Auto thread (session `bbe75542-b5c9-4de6-92d1-5e865d05eece`): the request that tiers stay fixed and models be
     configuration, the instruction to draft v7, and the approval of v7 with decisions N1(a) and N2(a).
     - External transcript export: `optimus-handoff\decisions-sources\2026-10-25-claude-session-plan12-4-v7-export.zip`, produced
       by the app's session Export, 3,258,517 bytes.
     - SHA-256: `F72D0A6D3C3BEA81DEA5EEAB57BA714E16D3F2A591B65F8BE3AB763EB0623504`.
     - Claude checked, read-only, that each quoted decision appears verbatim in a user turn of the export's main
       transcript. A full app export, not an excerpt. Raw S11 is archival provenance, never an operating, test or
       release dependency; S1–S10 retain their existing meanings.
   - **Source S12.** The #400 (R-15) decision N3, the operator's message of 2026-10-26 in the Claude session for the
     Plan 12.4 Auto thread (session `bbe75542-b5c9-4de6-92d1-5e865d05eece`): the approval of option b1 with Codex round
     58's conditions and its residual risk, main-first delivery, and posting the round-58 review to #400.
     - External transcript export: `optimus-handoff\decisions-sources\2026-10-26-claude-session-400-b1-export.zip`, produced
       by the app's session Export, 10,476,954 bytes.
     - SHA-256: `08947E807171B0C3259BED316490567CE1E2B4A27867200DFDF6345029753618`.
     - Claude checked, read-only, that the quoted decision appears verbatim in a human user turn of the export's main
       transcript (`2026-10-26T04:17:04.480Z`). A full app export, not an excerpt. Raw S12 is archival provenance, never
       an operating, test or release dependency; S1–S11 retain their existing meanings.
   - **Source S13.** Two operator messages of 2026-10-26 in the Claude session for the Plan 12.4 Auto thread (session
     `bbe75542-b5c9-4de6-92d1-5e865d05eece`):
     - **Pilot deviation N4:** the classifier output reserve of 1,024, the unknown-cost call carried as a provision,
       and the follow-up issue.
     - **The ADR-007 acceptance:** arm H as Auto mode's judge per the pre-registered rule and Codex round 62, with its
       limitations, and the instruction to draft round 2.

     The source record:
     - External transcript export: `optimus-handoff\decisions-sources\2026-10-26-claude-session-plan12-4-adr027-export.zip`,
       produced by the app's session Export, 14,044,749 bytes.
     - SHA-256: `35187F1129264F5622926FA788747312B65EA11536337307288A9D9DA38FCECB`.
     - Claude checked, read-only, that each quoted decision appears verbatim in a human user turn of the export's main
       transcript (N4 `2026-10-26T06:54:23.146Z`; the acceptance `2026-10-26T12:49:38.157Z`). A full app export, not an
       excerpt. Raw S13 is archival provenance, never an operating, test or release dependency; S1–S12 retain their
       existing meanings.
   - **Source S14.** Two operator messages of 2026-10-26 in the same session:
     - **Plan 12.4 Checkpoint A:** the approval of the `auto` hash, manifest option (ii), and round 2's R1(a), R2(a)
       and R3, with the instruction to draft Plan 12.4 v9.
     - **The GitHub writes:** the approval to file the two Plan 12.4 follow-up issues and to post the v9 note on #395.

     The source record:
     - External transcript export: `optimus-handoff\decisions-sources\2026-10-26-claude-session-plan12-4-v9-export.zip`,
       produced by the app's session Export, 15,102,277 bytes.
     - SHA-256: `031879BDA071E83A75D986272B7DFCA94149CAA35E36AF82284377819749F8F2`.
     - Claude checked, read-only, that each quoted decision appears verbatim in a human user turn of the export's main
       transcript (`2026-10-26T13:16:56.400Z` and `2026-10-26T13:38:04.632Z`). A full app export, not an excerpt. Raw
       S14 is archival provenance, never an operating, test or release dependency; S1–S13 retain their existing
       meanings.
   - **Source S15.** Four operator messages of 2026-10-27 in the same session:
     - **Plan 12.4 Checkpoint B:** the live acpx slices, one per routable tier, and the merge after they pass (CB1);
       the HLD v2.22 / LLD v2.45 successor with `SKIP=check-added-large-files` for its PDFs (CB2).
     - **Round 2:** option (c), dropping the L and HL arms (R4); the turn sizes from the operator's Claude Code usage
       counts (N6); the reused two-call round-1 row (N7); the paid release.
     - **Checkpoint R2:** the acceptance of round 2, H staying, and #426 closed as not needed (CR2), with the
       close-out instruction.

     The source record:
     - External transcript export: `optimus-handoff\decisions-sources\2026-10-27-claude-session-plan12-4-r2-export.zip`,
       produced by the app's session Export, 34,129,684 bytes.
     - SHA-256: `8BFA4F333B462C157363A7E897639AD1DFE7322F899457E89343D6A03F1EDD85`.
     - Claude checked, read-only, that each quoted decision appears verbatim in a human user turn of the export's main
       transcript (`2026-10-27T06:54:07.529Z`, `2026-10-27T08:57:44.918Z`, `2026-10-27T13:47:50.587Z` and
       `2026-10-27T16:35:31.612Z`). A full app export, not an excerpt. Raw S15 is archival provenance, never an
       operating, test or release dependency; S1–S14 retain their existing meanings.
   - **Source S16.** Two operator messages of 2026-10-27 in the same session, for #397 (ADR-029):
     - **The priority:** "#397 - can we get this done first? Then test auto live inside Zed".
     - **E1, ADR-009 open item 4:** the answer "(a) Automatic (Recommended)", given through AskUserQuestion.

     The source record:
     - External transcript export: `optimus-handoff\decisions-sources\2026-10-29-claude-session-p397-adr029-export.zip`,
       produced by the app's session Export, 80,115,213 bytes.
     - SHA-256: `D7577AA62433E428207181BE3C9256101B3B1AC52421B417E2667B589884BE5C`.
     - Claude checked, read-only, that each quoted decision appears verbatim in a human user turn of the export's main
       transcript (`2026-10-27T17:55:19.733Z`, typed; `2026-10-27T18:39:44.925Z`, the AskUserQuestion answer). The
       question and each option's description, as shown to the operator, are in the assistant turn that asked it
       (`2026-10-27T18:38:35.950Z`). A full app export, not an excerpt. Raw S16 is archival provenance, never an
       operating, test or release dependency; S1–S15 retain their existing meanings.
2. **Label the decider.** Each record says who decided: the operator, an agent (Claude or Codex), or an
   agent proposal still awaiting the operator. A value an agent chose must never read as an operator
   requirement.
3. **No binary decisions.** Every record lists the options considered, with their pros and cons, and the
   trade-off reasoning.
4. **Status** is one of Proposed, Accepted, Accepted-with-open-items, Deferred or Superseded.
5. **A record never changes once it has merged. A change is a new record.**
   - **Where this came from.** The operator assumed, on 2026-09-30: "I am assuming ADR will not change
     once written, we only have a new one that supersedes it?" Claude and Codex agreed to make that the
     rule.
   - **One publication-freeze rule:**
     - **Before its first merge to `main`,** a record is an unpublished draft. It may be revised during
       review, including when it records an operator decision that is already accepted.
     - **On first merge, every record is frozen byte for byte,** including records whose decision status is
       Proposed.
     - **After that,** corrections, completions, acceptance and supersession all use a **new** record that
       names what it affects ("Completes ADR-00N item X", "Accepts ADR-00N", "Corrects ADR-00N",
       "Supersedes ADR-00N").
     - The mutable index records the effective decision status and preserves links to unchanged
       predecessors.
   - Freezing defines when bytes stop changing. It does **not** turn a Proposed mechanism into an accepted
     decision.
   - The first batch (ADR-001 to 012) was revised in review before its first merge, after Codex's reviews
     on 2026-09-30.
   - **A fully superseded record moves unchanged to `archive/`** beside this folder's records, following
     the repository convention in `docs/README.md`.
     - This index, the only mutable part of the log, keeps its row, **links to its archived location** so
       the published link still resolves, and marks it "Superseded by ADR-0NN".
     - Its line in `docs/README.md` is removed, as the docs-index test requires.
     - Tools find documents by file name (`tools/doc_paths.py`), but a Markdown link in another document
       that points at the old path will not follow the move in a browser. Link to a record through this
       index where practical.
   - **The index Status column is mutable and shows the effective state,** for example
     "Accepted-with-open-items; item 1 completed by ADR-013". A frozen file keeps the status it had when
     it merged.
6. **Read before proposing.** Any agent working in an area reads the relevant records first and does not
   re-derive or contradict an Accepted one. If new evidence conflicts, raise it explicitly with the
   operator.
7. **Keep evidence separate from interpretation.** Facts carry their source: a file and line, a commit, a
   URL and date. Interpretations are labelled as such. Survey findings are stated as what the surveyed
   sources show, never as universal claims.
8. **State the authority boundary.** Keep these apart:
   - an operator's acceptance of a requirement or policy;
   - a proposed mechanism, default or number;
   - authority to implement, commit, publish, merge or make paid calls.

   A record accepted "with open items" may accept the requirement while its mechanism stays proposed.
   **No record commissions implementation** on its own.
9. **Work lives in its GitHub issue, not here.** GitHub Issues are the work register ([ADR-022](ADR-022-github-issues-as-the-work-register.md)); the consolidated
   deferred-followups backlog is transitional and holds work, owners, statuses and next gates only for records not yet marked `Moved`,
   whose GitHub issues own them. Filing a record does not close an existing owner or authorize implementation or paid calls.

## Index

| ADR | Title | Status | Decider | Date |
|---|---|---|---|---|
| [001](ADR-001-context-engine-separate-product.md) | The Context Engine is a separate, loosely coupled product; the Optimus floor stays | Accepted | Operator; details agreed by Claude and Codex | 2026-09-28 to 09-30 |
| [002](ADR-002-history-strategies-and-picker.md) | History strategies (compaction default, hybrid, sliding window) and the IDE picker | Accepted; effect-repair placement clarified by [ADR-013](ADR-013-plan12-effect-producer-repair.md); offline repair evidence accepted in Package A; main publication/live gates remain | Operator; definitions agreed by Claude and Codex | 2026-09-29 to 09-30 |
| [003](ADR-003-context-ceiling-and-history-limits.md) | Context ceiling of about 256K for all models; history may exceed 512 KiB while the engine is attached; Haiku removed | Accepted-with-open-items; D7 interpretation completed by [ADR-014](ADR-014-all-session-request-guard-floor-clarification.md); measurement obligations remain | Operator | 2026-09-30 |
| [004](ADR-004-curated-model-registry.md) | Curated model registry (YAML), tiers, origin rule, per-token selection among eligible models | Accepted-with-open-items; option C (the operator override) completed by [ADR-025](ADR-025-models-are-configuration-per-model-admission.md) | Operator; mechanism proposed by Claude, reviewed by Codex | 2026-09-30 |
| [005](ADR-005-cost-alerts-not-limits.md) | Cost policy: alerts and warnings, not limits | Accepted; sequencing completed by [ADR-015](ADR-015-cost-stop-removal-sequencing.md); runtime migration still owed | Operator | 2026-09-30 |
| [006](ADR-006-summarizer-model.md) | The summarizer comes from the ultra-cheap tier | Accepted-with-open-items | Operator | 2026-09-30 |
| [007](ADR-007-auto-mode-tier-routing.md) | Auto mode: classify each request into a tier | Accepted by [ADR-028](ADR-028-accepts-adr-007-auto-judge-h.md), with arm H (rules, then Jev) as the judge; ADR-009's bounded escalation, the exception to the turn binding that ADR-007 anticipates, is a present safeguard since [ADR-029](ADR-029-accepts-adr-009-rung-2-one-escalation.md) | Operator direction; design by Claude; pilot reviewed by Codex | 2026-09-30 |
| [008](ADR-008-final-review-step-and-modes.md) | A final review step, with Standard and Thorough modes | Proposed | Operator idea; design pending | 2026-09-30 |
| [009](ADR-009-loop-control-without-stopping-the-user.md) | Loop control that is never open-ended and never silently stops the user | Accepted as scoped by [ADR-024](ADR-024-accepts-adr-009-loop-control-phase-1-scope.md) (detector, one nudge, check-in; escalation after Auto); rung 2 (one move to the escalation model, in Auto) accepted by [ADR-029](ADR-029-accepts-adr-009-rung-2-one-escalation.md); interim cost-removal dependency clarified by [ADR-015](ADR-015-cost-stop-removal-sequencing.md) | Operator requirement; architecture by Claude, awaiting Codex | 2026-09-30 |
| [010](ADR-010-data-handling-for-chinese-model-routes.md) | Data handling on Chinese-model routes: no restriction now | Deferred | Operator | 2026-09-30 |
| [011](ADR-011-how-decisions-are-recorded.md) | How decisions are recorded | Accepted | Operator (requirement and repository home); mechanism agreed by Claude and Codex | 2026-09-30 |
| [012](ADR-012-cost-savings-report.md) | A cost-savings report is a Plan 12 feature | Accepted-with-open-items (requirement accepted; design proposed) | Operator; design by Claude, awaiting Codex | 2026-09-30 |
| [013](ADR-013-plan12-effect-producer-repair.md) | Effect/cancellation repair as Plan 12’s first code step; completes [ADR-002](ADR-002-history-strategies-and-picker.md) delivery prerequisite, relates to [ADR-001](ADR-001-context-engine-separate-product.md) | Accepted-with-open-items; Package A offline repair accepted; main publication/live gates remain | Operator; narrow mechanisms agreed by Claude/Codex | 2026-10-01 |
| [014](ADR-014-all-session-request-guard-floor-clarification.md) | All-session request guard and unchanged source floor; completes [ADR-003](ADR-003-context-ceiling-and-history-limits.md) D7 interpretation | Accepted-with-open-items; full-floor/estimator evidence owed | Operator | 2026-10-01 |
| [015](ADR-015-cost-stop-removal-sequencing.md) | Cost-stop removal after accounting/D6; completes [ADR-005](ADR-005-cost-alerts-not-limits.md) sequencing, clarifies [ADR-009](ADR-009-loop-control-without-stopping-the-user.md) dependency | Accepted-with-open-items; D6 and migration owed | Operator | 2026-10-01 |
| [016](ADR-016-checkpoint-review-cadence.md) | At most four checkpoint reviews; Fable then Codex; local focused-test commits and Package A publication | Accepted | Operator | 2026-10-02 |
| [017](ADR-017-package-a-coverage-exception.md) | Exact four-statement coverage residual at 38a465f | Accepted; terminal result remains NOT MET | Operator | 2026-10-01 |
| [018](ADR-018-plan12-cp4-numeric-policy.md) | Plan 12 CP4 measured numeric policy, whole-turn availability limitation and the D7 request-capacity exception; completes [ADR-003](ADR-003-context-ceiling-and-history-limits.md) numeric policy within Plan 12.2 | Accepted-with-open-items; numeric policy, one repack and whole-turn/D7 limitation accepted on 2026-10-04 (S4); on that date route qualification, summary-quality evidence and real-editor Task 13 remained open and activation/publication was held. Published through PR #276 (`c509fc8`, 2026-10-08); the shipped ordinary activation is decided by [ADR-023](ADR-023-plan12-shipped-empirical-admission-and-default-planner.md), which partially supersedes the earlier activation portions, and the current gates are tracked in #237 | Operator (2026-10-04, source S4); drafted by Codex, filed by Claude | 2026-10-04 |
| [019](ADR-019-plan12-task1-policy-integration.md) | Plan 12 accepted Task 1 mechanisms and governed integration; partial completion/clarification of [ADR-003](ADR-003-context-ceiling-and-history-limits.md) to [ADR-006](ADR-006-summarizer-model.md) | Proposed governed integration; the Task 1 mechanisms keep their 2026-10-02 acceptance in the archived first editions | Operator (2026-10-02 acceptance); integration proposed by Codex | 2026-10-04 |
| [020](ADR-020-test-cadence-product-coverage-and-staged-delivery.md) | Test cadence, product coverage, registry mechanisms and staged turnaround delivery | Accepted-with-open-items; Tasks 0–3 locally accepted/delivered; progress/command dispositions approved; local Task 6 accepted with approved checkout exception; report/docs delivered at 1c7be2d; Stage B Task 4/C/G accepted and local delivery verified at `43eb190`; Task 5/D accepted and local delivery verified at `66ddabf`; Stage B governance and local Task 6 accepted at measured `3cece0a`; results delivered at `26bd667`; Claude/Codex shared coverage responsibility clarified; v5 approved; I1 bootstrap local delivery verified at `6f1935d`; PR279 main-push baseline accepted at `4ed9b25`; current (2026-10-11): I1 merged on main via PR #279 (`4ed9b25`) and its main-push baseline accepted; I2/I3 integration merge committed locally at `ea88814e` (tree `9048bc8d`) and accepted, with I3 evidence including the WSL platform discharge; I4 exact-source finals accepted at `ea88814e` (Windows/WSL canonical gates and validation pass); S1 reader correction delivered at `343b233a` and accepted, with corrected-source I4 finals accepted at that pin (Windows/WSL canonical gates and validation pass; WSL platform obligation discharged at that pin only); documentary delivery `281f8ce7` accepted and its forward WSL platform obligation discharged; PR #280 published at `281f8ce7`, with its candidate Linux CI and seven-module safety comparison (no regression) accepted at merge ref `1946713e`; D3 documentary delivery `228b5f6f` accepted and its WSL platform obligation discharged; new-head CI accepted at merge ref `789586d7`; **effective status (2026-10-11, after Codex's 13:19:00 UTC acceptance): first merged to main by PR #280 at `3dc85529`, with its actual main-push CI and seven-module safety comparison accepted; the record is now byte-frozen.** Its dated "unpublished review draft until first merge" and status wording is historical and is not edited; a later policy or decision correction needs a new record. Current (2026-10-11, after Codex's 17:11:44 UTC acceptance): the terminal-docs PR #281 merged to main at `d5b4bec3` and its main-push CI accepted; the record's bytes are unchanged; Plan 11.30 v5 completed and archived (operator grant "YES", a direct operator reply in Codex chat on client date 2026-10-12, recorded by Codex at 2026-10-11 19:05:47 UTC, answering the exact question that approved closing Plan 11.30, archiving v5 and the kickoff, Checkpoint A, Checkpoint B dated 2026-10-05 and Task 3 records byte-for-byte, and one normal-hook closing commit). Cleanup held | Operator policy; mechanisms agreed by Claude/Codex | 2026-10-04 |
| [021](ADR-021-bounded-github-authority-switch.md) | Bounded GitHub authority switch for 49 Optimus work records; no frozen ADR is changed | Accepted. The operator accepted the mechanism on 2026-10-12 at 14:09:30 IST (source S7: "Accepted per wording above", adopting the pasted wording): GitHub issues become authoritative at the separately approved cutover merge, the backlog keeps compact pointers and pinned history, unmigrated work keeps its existing authority, and the reviewed 49 pre-merge and 49 post-merge update sequence is accepted. The acceptance authorizes no further writes, merge, A2A, P11-FU-42 delivery or cleanup. The 49 pre-merge issue updates were published and verified on 2026-10-12. Activated by the merge of PR #285 at `f4f0e2f8` (2026-10-12 19:39:01 IST); the 49 post-merge issue updates were then published and verified the same day, so the 98 updates are complete (release record: [`reports/github-work-tracking-migration.md`](../../reports/github-work-tracking-migration.md)). The 87 pending records, #33 and the A2A pilot (#225) were outside this decision and keep their existing authority. **Correction (2026-10-13, proposed):** its retained pool-first intake for new work is superseded by [ADR-022](ADR-022-github-issues-as-the-work-register.md); the rest of this record stands | Operator (requirements and activation authority; words verbatim, source S6; mechanism accepted 2026-10-12, source S7); mechanism proposed by Claude and accepted by Codex with clarifications; drafted by Codex, filed by Claude | 2026-10-12 |
| [022](ADR-022-github-issues-as-the-work-register.md) | GitHub Issues are the work register for all non-A2A Optimus work; the backlog is transitional; corrects only ADR-021's pool-first intake paragraph and sets the migration rules for the remaining open work | Operator requirement accepted. The operator's own message (source S8, verbatim in the record) says that open items migrate to GitHub Issues and that new plans and follow-ups are not recorded in the backlog; the rest of the relayed directive (documents keep scope, design, history and pointers; A2A stays deferred) is Codex's relay. The mechanism (unfinished work only, ownership-based exclusions, dependency-bounded execution groups) is agent-proposed by Claude; Codex reviewed the delivery and technically accepted it on 2026-10-13, subject to wording corrections made in the same delivery. The operator's acceptance of the mechanism is not recorded here; the executed migration groups ran under the operator's typed write approvals (see the record's migration record). Unpublished until its delivery merges; this record grants no further migration, write, commit, archival or cleanup | Operator (requirement; words verbatim in source S8 for the migration of open items and for keeping new plans and follow-ups out of the backlog); mechanism proposed by Claude, reviewed by Codex | 2026-10-13 |
| [023](ADR-023-plan12-shipped-empirical-admission-and-default-planner.md) | Plan 12.2 shipped empirical admission exception (Haiku 5.5, exact registry hash, `verified: false`) and medium-then-easy default planner; partially supersedes the verified-only admission and medium-only default/activation portions of earlier contracts and the related [ADR-003](ADR-003-context-ceiling-and-history-limits.md), [ADR-004](ADR-004-curated-model-registry.md) and [ADR-006](ADR-006-summarizer-model.md) integration claims | Accepted-with-open-items: the policy is accepted for the approved offline implementation, which ships with the Plan 12.2 delivery merge; the ordinary-launch proof for the shipped candidate is tracked in #237. The exception's binding to one hash and one model is superseded by [ADR-025](ADR-025-models-are-configuration-per-model-admission.md) | Operator (policy: the direct answer "Approved" in Codex chat, source S9; relayed to Claude in #237 6249169293, which is coordination evidence, not a new approval); drafted by Codex, filed by Claude | 2026-10-18 |
| [024](ADR-024-accepts-adr-009-loop-control-phase-1-scope.md) | Accepts [ADR-009](ADR-009-loop-control-without-stopping-the-user.md) as scoped for loop control Phase 1 (Plan 12.3): a detector, one nudge and a Continue/Stop check-in; thresholds 3, one nudge, Continue +3; the legacy goal loop retired; escalation after Auto | Accepted | Operator (D1–D3, source S10); mechanism details by Claude, reviewed by Codex | 2026-10-23 |
| [025](ADR-025-models-are-configuration-per-model-admission.md) | Models are configuration: per-model admission evidence in each registry entry, a conservative default estimator, per-model stops and the operator override; partially supersedes [ADR-023](ADR-023-plan12-shipped-empirical-admission-and-default-planner.md) and completes [ADR-004](ADR-004-curated-model-registry.md) option C | Accepted | Operator (N1(a) and N2(a), source S11); mechanism details by Claude, reviewed by Codex | 2026-10-25 |
| [026](ADR-026-exception-routes-accept-one-unflagged-guardrail-stage.md) | Exception routes accept exactly one unflagged `guardrail` router stage (`flagged` false; no detection, decision, action, conflict or scope); every other stage and fact still refuses; residual risk accepted (#400 option b1) | Accepted | Operator (decision N3, source S12); recommended by Codex (round 58); drafted and filed by Claude | 2026-10-26 |
| [027](ADR-027-idle-client-mcp-lifetime-contract.md) | Idle client-MCP suspension with in-memory ACP continuity and fresh identity-bound renewal of the former permission set | Operator-approved policy; core delivered via [#429](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/429); the [ordering contract](2026-10-27-ordering-lifecycle-signals-queue-contract.md) partially supersedes ADR-027's secondary-failure chaining. Remaining issue-specific work is tracked in [#427](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/427) | Operator (policy); Codex (delivery); Claude (review) | 2026-10-26 |
| [028](ADR-028-accepts-adr-007-auto-judge-h.md) | Accepts [ADR-007](ADR-007-auto-mode-tier-routing.md) with arm H as Auto mode's per-turn judge: the rules when confident (≥ 0.8), otherwise Jev `choice`, routing one tier up below 0.95; selected by the Plan 12.4 pilot's pre-registered rule, with its limitations; round 2 (2026-10-27) kept H under the same rule (Checkpoint R2, source S15; [plan v10](../superpowers/plans/archive/2026-10-23-plan-12-4-auto-mode_v10.md)) | Accepted | Operator (source S13); recommended by Codex (round 62); drafted and filed by Claude | 2026-10-26 |
| [029](ADR-029-accepts-adr-009-rung-2-one-escalation.md) | Accepts [ADR-009](ADR-009-loop-control-without-stopping-the-user.md)'s rung 2 and settles its open item 4: in an interactive Auto session, once a recovery episode's nudge has not helped, the turn moves once to the escalation role's first routable model, with a live notice and price line, before the Continue/Stop check-in; the exception to the turn binding that [ADR-007](ADR-007-auto-mode-tier-routing.md) anticipates (#397) | Accepted; a real model stuck enough to escalate is still owed in #397 (scripted evidence stands in) | Operator (E1 option (a) and the priority, source S16); mechanism by Claude, reviewed by Codex (round 75 and follow-ups) | 2026-10-27 |
| [030](ADR-030-approval-records-in-bounded-keyring-parts.md) | Approval records larger than one Windows credential blob (2,560 UTF-16-LE bytes) are stored as at most two authenticated, generation-specific parts; the 1,800-byte policy and its rejection stay; one service-wide lock serializes the approvals keyring service (#433) | Accepted | Operator (2026-10-28, AskUserQuestion in the Plan 12.4 session); recommended by Codex (rounds 76 and 78); drafted by Claude | 2026-10-28 |
| [031](ADR-031-project-memory-and-evidence.md) | Plan 12.x memory architecture as designed in v4; one includable-files policy for automatic context, indexing and anchor reads (security denials including #385's secret rule first, then `.gitignore`/`.optimusignore` via a pinned `pathspec`, no negation of a denial); registered project identity per Git common directory (Plan 12.6, #390) | Accepted | Operator (product decisions, source S10; #385 absorption and plan approval 2026-10-30); mechanisms by Claude, reviewed by Codex | 2026-10-30 |
| [032](ADR-032-durable-usage-capture-and-gateway-drain.md) | Durable usage capture (memory design v4 section 7): an fsynced host outbox uploaded with the existing Gateway URL and key; only the Gateway holds the Postgres credential and drains into an Optimus-owned, database-immutable ledger with committed cursors and per-turn coverage epochs (Plan 12.8, #454) | Proposed | Operator (credential boundary, 2026-10-31, with the Plan 12.8 plan-hash approval); mechanisms by Claude, reviewed by Codex | 2026-10-31 |
| [Ordering/lifecycle/signals and queue contract](2026-10-27-ordering-lifecycle-signals-queue-contract.md) | Progress admission, owned stop and later finite queues; supersedes only ADR-027 secondary chaining | Operator-approved mechanisms; checkpoint review pending; unpublished draft | Operator; Codex developer, actual Claude reviewer | 2026-10-27 |

**Package A delivery:** [local accepted implementation and evidence](../superpowers/reviews/2026-10-02-plan-12-2-package-a-delivery.md);
the Plan 12.2 issue (#237), to which the backlog row now points, records current publication/next gates. The frozen ADR-013 repair decision and
Plan 11.25 correction remain unchanged; the repair reached `main` with Package A through PR #276 (`c509fc8`, 2026-10-08).

**Evidence in the repository:** [industry practice and model catalog, 2026-09-30](2026-09-30-industry-context-cost-and-model-evidence.md).
It holds the survey of how eight coding agents handle context and spend, the OpenRouter catalog snapshot
of the tier models, and their sources.

**Related filed contract:** [Plan 12.2 design](../superpowers/specs/2026-10-01-plan-12-2-context-engine-design_v3.md) (v3), [implementation plan](../superpowers/plans/archive/2026-10-01-plan-12-2-context-engine-implementation_v4.md) (v4; archived with its earlier editions after Plan 12.2 closed on 2026-10-22), [Task 1 contracts](../superpowers/specs/2026-10-02-plan-12-2-task1-contracts_v3.md) (v3; the operator's 2026-10-02 acceptance belongs to the archived [first contracts](../superpowers/specs/archive/2026-10-02-plan-12-2-task1-contracts.md) and [v2 plan](../superpowers/plans/archive/2026-10-01-plan-12-2-context-engine-implementation_v2.md)) and [Plan 11.25 correction note](../superpowers/reviews/2026-10-01-plan-11-25-effect-instrumentation-correction.md). The predecessors are only partially completed/clarified, so ADR-001–012 remain current and unchanged; none moves to archive.

**Working papers outside the repository** (the operator's handoff folder,
`optimus-handoff\plan-12-discovery\`). They are kept for provenance only; the records above are
authoritative.

- `2026-09-30-claude-review-context-engine-direction.md`, `...-claude-reply-2-...` and
  `...-claude-reply-3-...`, with Codex's replies under `Documents\Codex\2026-09-30\...\outputs\`:
  rounds 1–3 of the Context Engine direction.
- `2026-09-30-claude-four-decisions-pros-cons.md`.
- `2026-09-30-claude-model-registry-and-cost-alerts-input.md`.

## Idle client-MCP policy, 2026-10-26

[ADR-027](ADR-027-idle-client-mcp-lifetime-contract.md) records #427: retained in-memory ACP continuity, standalone idle limit and fresh atomic permission renewal. The linked receipt preserves the direct operator role assignment and review qualifications.
