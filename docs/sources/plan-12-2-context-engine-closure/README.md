# Plan 12.2 Context Engine closure publication sources

This package holds the sources for HLD (Architecture) v2.19, LLD v2.42, Guardrails v1.4 and Test Strategy v1.8. They succeed HLD v2.18, LLD v2.41, Guardrails v1.3 and Test Strategy v1.7, which are archived unchanged in `docs/archive/`.

Codex prepared the documents as architect and reviewer. Claude filed them locally on 2026-10-05 under the operator's offline release of 2026-10-04. They are reviewed local filing candidates: they grant no paid or live calls, activation, push, PR or merge, and filing them does not close CP4.

## Provenance

- **Reviewed packet:** `plan12-closure-offline-review`, kept outside the repository in Codex's output folder.
  - Its `SHA256SUMS.txt` (SHA-256 `c3ce7da3971ced9cab1e1e16a2dd9dc087a6ab79c25dd7e99c42eafaa72b324a`) seals 95 payloads.
  - Claude verified all 95 before filing.
- **Implementation candidate:** `cf9bb9d73ac6c8c3be508966245e0db7cdaaa503`.
  - Codex's review record is [the CP4 offline review disposition](../../superpowers/reviews/2026-10-04-plan-12-2-cp4-offline-review-disposition.md).
- **Predecessor inputs:** the packet's baseline PDFs and Markdown are byte-identical to the archived predecessors, so they are not duplicated here.
  - The PDFs are `docs/archive/Optimus-Cost-Agent-*-v{2.18,2.41,1.3,1.7}.pdf`.
  - The Markdown files are the archived Plan 12.2 design v2, implementation plan v3 and Task 1 contracts v2.
- **Byte identity of the filed files:** every file here copied from the packet (all but this README), the four PDFs, the plan, the specs and the review disposition match their sealed hashes, with two exceptions.
  - ADR-018 and ADR-019 differ from the packet's drafts only in their ID-allocation lines.
  - `sources/replacement-audit.json` and `sources/structural-repair-map.json` are CRLF in the packet. The repository's `.gitattributes` (`text=auto eol=lf`) stores them with LF, so their blobs differ from the sealed bytes only in line endings; removing the CRs reproduces each blob exactly.

## Contents

- `migration-map.md`: the requirement and implementation migration map, mapping predecessor pages to successors.
- `closure-proposal.md`: the current closure proposal.
- `test-composition-contract.md`: the trusted test-composition contract.
- `coverage-decision-provenance.md`: provenance of the coverage decision.
- `sources/page-updates.json`: complete replacement bodies.
- The four `sources/1[345]-context-*.md` files: the new context chapters.
- The `sources/*-baseline-page-*.md` files: extracted predecessor page text.
- `sources/replacement-audit.json` (historical v1 edit provenance, not the current build verdict) and `sources/structural-repair-map.json`.

## Kept only in the sealed packet

These files carry SHA-256 digests on many lines (the build manifest, validation records, audits and the baseline list), or are authoring scripts not written to this repository's lint rules. They stay in the packet, verified against its seal above. The operator chose this on 2026-10-05, rather than changing the secret-scan or lint configuration.

- `evidence-verification.json`: Codex's independent checks of the CP4 evidence.
- `document-validation.json` and `visual-review.json`: the document checks and the rendered-review scope.
- `sources/build-manifest.json`: maps every predecessor page position to its physical successor pages, with hashes.
- `sources/plan-successor-audit.json` and `sources/v2-revision-audit.json`.
- `sources/baselines/` (the baseline list and page maps) and the baseline PDFs.
- `sources/tools/`: the document builder and validators. They are not product configuration.

## Rebuilding

A rebuild runs from the sealed packet, not from this folder.

1. Verify the packet against its `SHA256SUMS.txt`.
2. Run `python sources/tools/build_drafts.py` there, in an environment with reportlab, pypdf and the Windows Arial fonts.

A rebuild changes bytes, so it needs new hashes and a new rendered review. Never commit a rebuilt PDF over a filed edition.

## Boundary

- **ADR-018 (numeric policy and D7)** and **ADR-019 (Task 1 and D6 integration)** are the decision records filed with these documents.
- ADR-018 keeps its D7 operator-decision placeholder until the operator's saved session export is registered. The placeholder is not an approval record.
- Still required before full CP4: real route and estimator eligibility, a genuine summary-quality receipt, and the real-editor Task 13. They remain UNRUN unless the operator separately records a disposition.
- Still held: paid and live work, activation, shipped Haiku-default removal, sandbox synchronization, push, PR and merge.
