# Local Gateway v3 Publication Completeness Audit

**Status:** Blocking defect confirmed; PDF re-authoring has not started.

**Date:** 2026-07-27

**Scope:** Compare the pinned v2/v1 PDFs with the published v3 PDFs before any traceability
inventory or section-map refresh is treated as authoritative.

## Method and reproducibility

The old and new PDFs were independently opened with `pypdf` and compared page by page. The local
bundled runtime does not include `pdftotext`; the WSL2 Poppler command was attempted and failed with
`E_ACCESSDENIED`, so the measured values below are the equivalent `pypdf` extraction values, not
claimed Poppler values. No PDF, source page, or production/test file was changed during this audit.

The source redline was also read to distinguish an authorized section rewrite from an accidental
loss. The redline contains 33 entries: 8 HLD, 14 LLD, 8 Test Strategy, and 3 Guardrails. None of
those entries authorizes deleting the sections listed below.

## Aggregate extraction evidence

| Document | Pinned pages | Published pages | Pinned extracted chars | Published extracted chars | Delta |
|---|---:|---:|---:|---:|---:|
| HLD | 13 | 13 | 23,882 | 21,861 | -2,021 |
| LLD | 40 | 40 | 26,911 | 26,813 | -98 |
| Guardrails | 16 | 16 | 30,421 | 26,802 | -3,619 |
| Test Strategy | 14 | 14 | 30,059 | 17,195 | -12,864 |

The unchanged page counts therefore do not establish content preservation. The LLD aggregate is
also non-diagnostic because the published replacement pages add enough new text to mask the loss of
the old component-contract pages.

## Section and marker inventory diff

### HLD v2.16

The following content was present in the pinned v2.15 PDF but is absent or materially incomplete in
the v2.16 output:

- The full body of §6, including the original steps [1]-[9]. The redline HLD-2 authorizes changing
  step [6] only; the other steps and their surrounding prose must survive.
- §7, `Agent Operating Modes & Trust Framework`, is absent from the regenerated page 4.
- The original §10.C `Phase Evolution Diagram` body is replaced by a new release-gate table. HLD-4
  authorizes changing the release-gate label inside §10.C, not deleting the phase diagram.
- The §10.D `Where Cost Control Happens` table is absent.
- The §10.E `Where Hallucination Control Happens` table is absent.

The §5A, §10.A, §11, §11.1, §11A, and §12 changes are within the named redline surfaces. Their
co-located losses on pages 4 and 9 are not.

### LLD v2.39

The old page 39/40 guardrail contract inventory is not preserved:

- §12A `Permission & Pre-Tool Enforcement` is absent. Markers lost: `PreToolGuard` and
  `CommandSafetyValidator`.
- §12B `Prompt-Injection & MCP Supply-Chain Trust` is absent. Markers lost: `MCPTrustRegistry`
  and `ConfigTrustScanner`.
- §12C `Bounded Agent Loops` is absent. Marker lost: `GoalLoopController`.
- §12D remains as a heading, but its normative `SkillRegistry`, `SkillManifest`,
  `SkillTrustPolicy`, and `SkillInvocationPolicy` contract body was replaced by a short summary.

LLD-14 authorizes the §11A and §12 cross-reference changes; it does not authorize deleting the
§12A-§12D component contracts. The final source must preserve those contracts and apply only the
settled USD/MCP wording to the portions explicitly covered by the redline.

### Guardrails v1.1

The regenerated pages 10-11 omit co-located sections and controls:

- §7.1 `Phase 1 Stance` is absent.
- §7.2 remains as a heading and contains the new `max_budget_usd` row, but the original normative
  loop controls (`per-iteration evidence`, clean git-diff check, pre-tool guard, human approval,
  persistent-state rule, and related bounded-loop prose) are absent. GR-1 authorizes the
  `max_budget_credits` to `max_budget_usd` row rewrite, not removal of the other controls.
- §8.1 `Skill Rules` is absent.
- §8.2 `Trust & Invocation` is absent.
- The original §8 explanatory contract is reduced to a short summary.

GR-2 correctly supplies the completion-evaluator rewrite, but it does not supersede the §7.1,
§7.2, §8, §8.1, or §8.2 material that shared those pages.

### Test Strategy v1.5

The regenerated page 9 replaces two unmodified normative sections:

- §9 `Error, Retry, and Failure Injection Tests` is absent. Marker `RetryPolicy` goes from 1 to 0.
- §10 `Schema Validation Tests` is absent. Marker `Pydantic` goes from 1 to 0.

TS-7 authorizes adding the deterministic search compatibility gate as §7A; it does not authorize
removing §9 or §10. The carried §4, §8, and §14 pages remain present, so this is a page-level loss,
not a whole-document extraction failure.

## Root cause

The regenerated Markdown sheets for changed pages contain the replacement section(s) but not every
old section that shared those physical pages. The assembly process then preserved page count,
headers, metadata, and geometry while silently dropping content. The affected replacement sheets
are:

| Document | Affected published pages | Omitted co-located content |
|---|---|---|
| HLD | 4, 9 | §6 remainder, §7, §10.C phase diagram, §10.D, §10.E |
| LLD | 39, 40 | §12A, §12B, §12C, old §12D contract body |
| Guardrails | 10, 11 | §7.1, most unchanged §7.2 controls, §8 prose, §8.1, §8.2 |
| Test Strategy | 9 | §9 and §10 |

The existing validator is output-relative: it checks page count, geometry, metadata, versions,
critical anchors, hashes, and SVG geometry. It has no source-to-output completeness assertion, so it
cannot detect an omitted heading or identifier.

## Required disposition

The published v3 PDFs and the current Task 1 map are invalidated for traceability use. The current
map statements that treat §12A-§12C, §8.1/§8.2, and Test Strategy §§9-10 as superseded are false and
must not be carried forward.

The repair sequence is:

1. Re-author every affected changed-page source, preserving all unmodified co-located content and
   applying only explicit redline entries.
2. Add a mandatory source-to-output completeness gate to
   `docs/sources/local-gateway-architecture-v3/tools/validate_publication.py`. The gate must compare
   normalized section-heading and component/identifier inventories from each pinned source PDF and
   candidate output, with any authorized removal referenced by a redline entry ID.
3. Rebuild all four PDFs and rerun the existing metadata, geometry, digest, version, anchor, and SVG
   checks plus the completeness gate.
4. Redo the authoritative section map against the repaired PDF bytes.
5. Only then resume the deep requirement inventory.

No production code, tests, commit, push, or PR is authorized by this audit.
