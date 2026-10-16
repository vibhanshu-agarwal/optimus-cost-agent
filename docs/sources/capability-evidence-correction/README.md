# Capability and evidence correction sources (HLD v2.20, LLD v2.43, Roadmap v11, Test Strategy v1.9, Guardrails v1.5 cover)

This bundle holds the complete editable sources, the correction map and the validation record for the four successor editions filed on 2026-10-15. They succeed HLD v2.19, LLD v2.42, Roadmap v10 and Test Strategy v1.8, which move to `docs/archive/` unchanged. The Guardrails body is unchanged and keeps its source in [`../plan-12-2-context-engine-closure/`](../plan-12-2-context-engine-closure/); under the operator's 2026-10-15 confirmation of the one-page scope expansion (correction map, section 5), Guardrails v1.5 replaces only the v1.4 cover, and v1.4 moves to `docs/archive/` unchanged.

Claude prepared the correction under the operator's documentation-correction request and the plan it handed over (`claude-documentation-correction-plan.md`, SHA-256 `f5b86db06371dabee47417e4eab00fc8cbfa53db94d59b62a8b032a834899498`, kept outside the repository). Fable 5.1 reviews and a consolidated Codex review are the plan's three checkpoints. The Codex checkpoint 3 review (`checkpoint-3-documentation-review.md`, 2026-10-16, SHA-256 `a0811167b6b0d4f3e70056a9391618d16355ebbe5a5fce7b70fe7fd195a729f2`, kept outside the repository) requested five corrections, R1-R5; this revision applies them and the HLD, Test Strategy and Roadmap editions were rebuilt (the revision section of [`validation-record.md`](validation-record.md) lists every post-seal change). The editions are reviewed local filing candidates: they grant no paid or live calls, activation, push, PR or merge, and filing them changes no accepted requirement, number or historical record.

## What this correction does

For every material capability the four documents name, it separates what is implemented, what has been verified and how, and what is active, at the inspected source `91fd64ac78025efe1076bddb106ff89e6adb2030` (origin/main, fetched 2026-10-15). Material claims are qualified where they appear, and each document ends with a compact status section (HLD §15, LLD §14, Test Strategy §16, Roadmap §4). Every change is listed once, with its source or test reference, in [`correction-map.md`](correction-map.md). The map also lists the findings about missing implementation (F1-F4) for existing or future owners; nothing was implemented.

## Contents

- [`correction-map.md`](correction-map.md): the single correction and evidence map, the predecessor section accounting rule, the findings and the held scope.
- [`validation-record.md`](validation-record.md): successor file identities, predecessor and baseline identities, the generated page map, the assembly checks, the rendered-review scope and the repository checks that ran, with their actual results.
- `sources/page-updates.json`: every replaced page body for the HLD, LLD and Test Strategy (the v2.19/v2.42/v1.8 bodies from the sealed Plan 12.2 sources, edited as the map records, plus the new LLD §9C.1, §9C.4 and §9E.1 bodies).
- `sources/hld-14-context-engine.md`, `sources/lld-13-context-integration.md`, `sources/test-15-context-evidence.md`: the corrected appended chapters.
- `sources/hld-15-capability-status.md`, `sources/lld-14-capability-status.md`, `sources/test-16-capability-status.md`: the new status sections.
- `sources/guardrails-v15-cover.md`: the Guardrails v1.5 cover page (the only page that differs from v1.4; added after the operator confirmed the scope expansion on 2026-10-15).
- `sources/roadmap-v11.md`: the complete Roadmap v11 source. Roadmap v10 was a WeasyPrint rendering with no source in the repository; v11 is rendered entirely from this file.

## Provenance

- **Predecessors** (archived unchanged; filesystem bytes and Git blobs recorded in the validation record): `Optimus-Cost-Agent-Architecture-v2.19.pdf`, `Optimus-Cost-Agent-LLD-v2.42.pdf`, `Optimus-Architecture-Roadmap-v10.pdf`, `Optimus-Cost-Agent-Test-Strategy-v1.8.pdf`.
- **Native carried pages** come from the v2.18, v2.41 and v1.7 baselines in `docs/archive/`, exactly as the predecessors carried them; the validator checks their body text against the baseline page.
- **Sealed inputs reused**: the Plan 12.2 packet `plan12-closure-offline-review` (its `SHA256SUMS.txt` has SHA-256 `c3ce7da3971ced9cab1e1e16a2dd9dc087a6ab79c25dd7e99c42eafaa72b324a`; all 95 payloads verified before use on 2026-10-15). It was copied to a working directory and never modified; its `page-updates.json` and chapter sources are the inherited bodies here, and its `build_drafts.py` is the ancestor of the builder.
- **Historical evidence anchors retained**: implementation candidate `cf9bb9d73ac6c8c3be508966245e0db7cdaaa503`; documentation filing `5ee081e`; acceptance boundary `2068366` (operator disposition 2026-10-08); merge `c509fc8` (PR #276). The dispositions are `docs/superpowers/reviews/2026-10-04-plan-12-2-cp4-offline-review-disposition.md` and `2026-10-08-plan-12-2-cp4-offline-delivery-disposition.md`. No previous pass is transferred to `91fd64a`.
- **Tools used**: reportlab 5.0.0 and pypdf 6.10.2 (system Python 3.14.4) for assembly; Poppler pdftoppm/pdftotext 25.07.0 for rendering and text extraction; Windows Arial fonts. The derived builder (`build_corrections.py`), the authoring script (`author_corrections.py`, whose asserted `replace` edits are the exact changes), the validator (`validate_corrections.py`) and the contact-sheet renderer are filed in `tools/` (see below); their sealed-packet copies are identified in the validation record.

## Authoring tools (filed in `tools/`, R2 disposition of 2026-10-16)

The build and validation tools are in [`tools/`](tools/). The checkpoint 3 review (R2) found that a rebuild procedure resting on scripts held only in sealed packets did not meet the evidence policy's contributor-accessibility rule, and the operator chose on 2026-10-16 to file the tools rather than record an exception. They are the packet scripts with `# pragma: allowlist secret` on the lines that hold recorded SHA-256 constants, one ruff rename and one unused-import removal; their filed identities, and the sealed packet identities they derive from, are in the validation record. On 2026-10-16 the filed builder reproduced all five editions byte for byte from this bundle and the archived baselines.

| Tool | Purpose |
|---|---|
| `build_corrections.py` | Assembles HLD, LLD and Test Strategy from the archived baselines and this bundle; renders the Roadmap from Markdown; fixed PDF creation date |
| `build_guardrails_v15.py` | Wrapper over the builder for Guardrails v1.5 (cover only; bodies from the Plan 12.2 bundle) |
| `validate_corrections.py` | Manifest, page-count, carried-text, predecessor-coverage, label/footer and artifact checks |
| `contact_sheets.py` | Renders every page (Poppler) into contact sheets for review |
| `author_corrections.py`, `apply_review_fixes.py`, `apply_checkpoint3_fixes.py`, `apply_consolidated_update.py`, `apply_platform_accounting_update.py`, `apply_record_corrections.py` | The asserted `replace` edits that produced the sources from the sealed Plan 12.2 bodies, then the review, checkpoint 3, post-gate, platform-accounting and final record corrections |
| `write_validation_record.py`, `compose_validation_record.py` | Generate and compose the mechanical parts of `validation-record.md` |

The build manifests, validation JSON, contact sheets, text extracts, check and gate logs, WSL evidence and the ledger of rulings stay in three sealed packets under `C:\worktrees\optimus-cost-agent-worktrees\_handoff\` on the operator's workstation: `2026-10-15-capability-evidence-correction` (37 payloads; `SHA256SUMS.txt` SHA-256 `ed690972898d21b48352b8f74b811a2dd4f36423220cda5fd1a91f47cc937996`), `2026-10-16-capability-evidence-correction-supplement` (59 payloads; `fdbf972f35b04901cf6627ce7ccf2d3da2aba776e5f844a5814d3fdf5063637e`) `2026-10-16-capability-evidence-correction-gates` (`1fdf44bfef3de9501877c24dd5c1e1e4d13df040c0932f78e56aa1297e43a6fc`) and `2026-10-16-capability-evidence-correction-platform` (`20ba21e5c76a79ba09db1f0305773b89e920f125b666002fd86707b9ca749b62`; the corrected platform accounting, the bounded WSL remainder run and the rebuild-procedure verification). The first three are unchanged. Raw logs and contact sheets stay out of the repository under the evidence policy; the record in this bundle carries the compact summary a reviewer needs, and the tools make the editions reproducible.

## Rebuilding

Prerequisites: Python 3.14 with reportlab 5.0.0, pypdf 6.10.2 and Pillow (12.3.0 was used); the Windows Arial fonts; Poppler 25.07.0 (`pdftoppm`, `pdftotext`) on `PATH` for rendering and text extraction. Both builders write a `build-manifest.json` and the validator reads the manifest of the directory it is given, so the four-document build and the Guardrails build need **separate output directories**, each validated and rendered on its own. From a checkout of this candidate (or the commit that files it), at the checkout root:

```
python docs/sources/capability-evidence-correction/tools/build_corrections.py . <out-four>
python docs/sources/capability-evidence-correction/tools/validate_corrections.py . <out-four>
python docs/sources/capability-evidence-correction/tools/build_guardrails_v15.py . <out-guardrails>
python docs/sources/capability-evidence-correction/tools/validate_corrections.py . <out-guardrails>
python docs/sources/capability-evidence-correction/tools/contact_sheets.py <out-four> <sheets-four>
python docs/sources/capability-evidence-correction/tools/contact_sheets.py <out-guardrails> <sheets-guardrails>
```

Expected: `<out-four>/document-validation.json` lists `hld`, `lld`, `test` and `roadmap` with status PASS; `<out-guardrails>/document-validation.json` lists `guardrails` with status PASS; the five PDFs hash equal to the filed editions (the builder fixes the PDF creation date, so the same tools, fonts and sources reproduce the recorded hashes; verified on 2026-10-16, see the validation record). The product code at the inspected pin `91fd64ac78025efe1076bddb106ff89e6adb2030` is read only by the record writer's `git rev-parse` blob checks; the PDFs read no product code. A rebuild with different inputs changes bytes and needs a new validation record and a new rendered review. Never commit a rebuilt PDF over a filed edition.

## Work record

GitHub Issues are the work register (ADR-022). No issue existed for this correction at the pin. Issue #360 is this correction's work record, created on 2026-10-15 through the operator's GitHub account under the operator's per-issue chat approval; the findings have their own issues, created the same way: F1 #361, F2 #362, F3 #363 (F4 needs none). #360 was updated on 2026-10-16 (2026-10-16T01:09:12Z) under the operator's approval to the five-document scope, the actual gate state and the candidate identities (checkpoint 3, R1 and R3); #363 was corrected the same day (2026-10-16T01:09:14Z) so that Tirith is an optional candidate, not adopted (R5). The applied texts are in the third packet. Issue text as created for #360 on 2026-10-15:

> **Documentation: capability and evidence correction (HLD v2.20, LLD v2.43, Roadmap v11, Test Strategy v1.9).** Separate implementation, verification and activation status for every material capability at origin/main `91fd64a`; preserve sealed evidence and predecessors; file successor editions with a source-bound correction map. Documentation only. Findings F1-F4 in `docs/sources/capability-evidence-correction/correction-map.md` need their own issues or an owner decision. Labels: ADR-021 defaults (priority medium, difficulty medium, estimate NA, handler unassigned, product optimus, kind follow-up).

The deferred Plan 12.2 obligations (Luna route/estimator qualification, genuine summary-quality receipt, real-editor Task 13) keep their owner, issue #237, and are not restarted here.

## Boundary

Filed locally as reviewed candidates in the worktree branch `agent/claude/plan12-capability-evidence-correction`; the plan's authorization covers preparation and local filing readiness. Checkpoint 3 (Codex, 2026-10-16) requested changes; the revision and this post-gate update answer them and return to the same checkpoint, not a new one. On 2026-10-16, from a scoped pre-commit environment, the ast-grep gate and the commit profile passed on Windows against the frozen candidate `005cdab0...`, and on real WSL the commit profile passed and a bounded run covered the remaining platform-tagged nodes, so all 1,629 platform-tagged nodes of the candidate's collection have WSL execution records (validation record, corrected accounting section); only `check-added-large-files` fails, on the four PDFs over 500 KB (validation record, gate-rerun section). The 2026-10-15 failures stand as dated history. The commit remains held for the operator's file-size decision and ADR-020 acceptance of the WSL evidence. Issues #360-#363 were created on 2026-10-15 under per-issue operator approval. Commit, push, PR, merge, publication and every activation remain held for the operator. Offline acceptance is not production acceptance, a full CP4 pass or permission to remove the shipped model default.
