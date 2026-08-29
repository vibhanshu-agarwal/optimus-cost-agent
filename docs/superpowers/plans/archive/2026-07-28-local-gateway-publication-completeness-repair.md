# Local Gateway Publication Completeness Repair

**Status:** Approved by operator on 2026-07-28; execute through rebuild + gate, then stop for review.

## Objective

Repair the four v3 publication inputs that dropped co-located source content or introduced an
unauthorized control, and make the publication validator prove bidirectional source-to-output
completeness before any downstream traceability refresh resumes.

## Scope boundary

In scope:

- `hld-v2.16-changed-pages.md`, `lld-v2.39-changed-pages.md`,
  `test-strategy-v1.5-changed-pages.md`, and `guardrails-v1.1-changed-pages.md`.
- `tools/validate_publication.py`, its focused tests, and manifest metadata needed to express
  explicit redline-authorized replacements/removals/additions.
- Rebuilding the four PDFs with the already-approved WSL2 Pandoc/WeasyPrint toolchain.
- Existing PDF/SVG checks plus the new completeness gate.

Out of scope until Task 1 is re-reviewed:

- README version/hash refresh, authoritative section-map re-pin, deep-requirement inventory,
  `.env.example`, backlog dispositions, PR creation, and Task 2 of the post-publication plan.
- Installing Pandoc, WeasyPrint, or any other dependency.

## Evidence and invariants

- The independently verified audit is
  `docs/superpowers/reports/2026-07-27-local-gateway-publication-completeness-audit.md`.
- Only the exact content authorized by an entry in
  `docs/superpowers/reports/2026-07-27-local-gateway-architecture-document-redline-v3.md`
  may change on a changed page.
- HLD §6 co-located steps [1]-[9] and §7, HLD §10.C diagram body plus §10.D/§10.E, LLD §§12A-
  12C and §12D contract bodies, Test Strategy §§9-10, and Guardrails §§7.1/7.2/8/8.1/8.2 must
  survive unless an explicit redline entry authorizes the exact change.
- Guardrails `max_budget_tokens` is an unauthorized additive defect and must be absent; the
  existing `max_budget_credits` -> `max_budget_usd` rename remains the only row change in GR-1.
- MCP remains outside this correction: no MCP endpoint, route, contract, or diagram branch.

## Tasks

### 1. Re-author changed-page sources

For each affected changed-page sheet, recover all co-located source content from the pinned v1/v2
PDF page(s), then reapply only the relevant redline entry. Preserve headings, tables, lists,
contract identifiers, and explanatory prose that have no explicit entry. Keep the corrected
architecture decisions (OpenRouter default, optional Vercel backlog, one OpenAI-compatible
transport, deterministic search gate, OTel/Phoenix, strict loopback, USD rename) in their licensed
locations. Remove the unauthorized Guardrails `max_budget_tokens` row.

Verification: page-local extraction inventories show no unauthorized loss or addition before
rendering, and `git diff --check` passes.

### 2. Add a bidirectional completeness gate

Extend `validate_publication.py` with a source-to-candidate inventory check. The gate must compare
each output against its pinned source document using normalized headings and stable component /
identifier markers, in both directions:

- source marker missing from candidate => fail unless a manifest exception names the redline entry;
- candidate marker absent from source => fail unless a manifest exception names the redline entry;
- every exception is keyed to an explicit redline entry ID and scoped to a document/section;
- the gate reports missing, added, and authorized changes separately and fails on an unowned item.

Keep the existing page/version/hash/anchor and SVG checks unchanged. Add focused tests that first
fail against the current invalid PDFs and then pass only after repaired inventories and exceptions
are present.

### 3. Rebuild and verify

Use the existing WSL2 build commands; do not install missing tools. Re-render all four changed-page
fragments, run `build_publication.py`, and run the full validator including the new completeness
gate. Record fresh page counts, SHA-256 digests, per-page version assertions, heading/component
inventory results, and SVG geometry results. If WSL2 Pandoc/WeasyPrint cannot be invoked, stop and
report the exact blocker for operator direction.

### 4. Stop for operator review

Report only the rebuild + gate evidence. Do not redo Task 1 traceability or resume the downstream
README/map/inventory/backlog work until this repair lane is reviewed and accepted.
